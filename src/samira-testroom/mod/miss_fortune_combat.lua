-- Miss Fortune: frame timings assume the game's 30 updates/second.
-- ready holds absolute frames. fx entries: {kind, from, to, untilFrame};
-- Rain records scheduled and actual impact frames. R keeps an in-flight wave.
local Combat = {}
local cooldowns = {q=120, w=360, e=300, r=900}
local baseQWindup, baseAttackInterval = 8, 11
local strutFrames = 120
local bounceTravel = 4
local bounceRange = 180
local bounceCosines = {math.cos(math.rad(10)), math.cos(math.rad(20)), math.cos(math.rad(55)), math.cos(math.rad(80))}
local dudRange, dudTravel = 63, 13
local rainDelay, rainFrames, rainTicks = 8, 60, 8
local rainRange = 260
local rainSlowFrames, rainSlowRefresh = 8, 4
local barrageFrames, barrageInterval, barrageRange = 90, 6, 300
local barrageWindup = 2
local barrageHalfAngle = 17 -- Half-angle of the source Bullet Time range indicator.
local barrageRays = {-15, -9, -3, 3, 9, 15}
local function length(v) return math.sqrt(v.X*v.X + v.Y*v.Y) end
local function unit(v)
    local n = length(v)
    if n < .001 then return nil end
    return v / n
end
local function copy(v) return Vector(v.X, v.Y) end
local function fireplace(e)
    local kind = EntityType and EntityType.ENTITY_FIREPLACE
    return e and kind and e.Type == kind
end
local function valid(e)
    return e and not fireplace(e) and e:Exists() and not e:IsDead() and e:IsActiveEnemy(false) and e:IsVulnerableEnemy()
        and (not EntityFlag or not e.HasEntityFlags or not e:HasEntityFlags(EntityFlag.FLAG_FRIENDLY))
end
local function tearDamageableFire(e)
    return fireplace(e) and (e.Variant == 0 or e.Variant == 1)
        and e:Exists() and not e:IsDead() and e.HitPoints > 0
end
local function identity(e) return GetPtrHash(e) end
local function enemies()
    return Isaac.GetRoomEntities()
end
local function context(items, p, kind, clock)
    return items and items.newAttack and items.newAttack(p, kind, clock) or {kind=kind, hit={}}
end
local function deal(items, ctx, p, enemy, amount)
    local function hit() return enemy:TakeDamage(amount, 0, EntityRef(p), 0) end
    if items and items.withContext then return items.withContext(ctx, hit) end
    return hit()
end
local function hitGrid(room, p, contains)
    if not GridEntityType or not room or not room.GetGridSize then return end
    local source = EntityRef(p)
    for index = 0, room:GetGridSize() - 1 do
        local grid = room:GetGridEntity(index)
        if grid then
            local kind = grid:GetType()
            local intactPoop = kind == GridEntityType.GRID_POOP and grid.State < 1000
            local intactTnt = kind == GridEntityType.GRID_TNT and grid.CollisionClass ~= GridCollisionClass.COLLISION_NONE
            if (intactPoop or intactTnt) and contains(grid.Position) then
                if grid.HurtWithSource then grid:HurtWithSource(1, source)
                else grid:Hurt(1) end
            end
        end
    end
end
local function cd(items, p, key)
    if items and items.cooldown then return items.cooldown(p, key, cooldowns[key]) end
    return cooldowns[key]
end
function Combat.new(clock)
    return {ready={q=0,w=0,e=0,r=0}, lastDamage=clock or 0, fx={}, pendingBounce={}}
end
function Combat.grantStrut(s, clock)
    s.lastDamage = math.min(s.lastDamage, clock - 210)
end
function Combat.cast(s, key, p, aim, clock, room, items, weapons)
    if not cooldowns[key] or s.r or clock < (s.ready[key] or 0) then return false end
    local delta = aim and aim - p.Position
    local directional = key == 'q' or key == 'r'
    local facing = directional and delta and unit(delta)
    if (directional and not facing) or (key == 'e' and not delta) then return false end
    if key == 'q' then
        -- Scale the stock windup with the native attack interval. The weapon
        -- adapter still waits for the actual release of charged weapons.
        local attackInterval = p.MaxFireDelay and p.MaxFireDelay + 1 or baseAttackInterval
        local windup = math.max(2, math.min(24, math.floor(baseQWindup * attackInterval / baseAttackInterval + .5)))
        if not weapons or not weapons.requestQ
            or not weapons.requestQ(p, facing, clock, aim, clock+windup, true, true) then return false end
    elseif key == 'w' then
        s.wUntil = clock + strutFrames
        Combat.grantStrut(s, clock)
    elseif key == 'e' then
        local distance = length(delta)
        local center = distance > rainRange and p.Position + delta * (rainRange / distance) or copy(aim)
        local impactFrames={}
        for i=1,rainTicks do impactFrames[i]=clock+rainDelay+math.floor((i-1)*rainFrames/rainTicks) end
        s.rain = {center=center, radius=85, startFrame=clock,
            untilFrame=clock+rainDelay+rainFrames, impactFrames=impactFrames, landedAt={}, slowRefreshAt={},
            ticks=0, context=context(items,p,'e',clock)}
    elseif key == 'r' then
        local firstWave=clock+barrageWindup
        s.r = {origin=copy(p.Position), facing=facing, startFrame=firstWave, untilFrame=clock+barrageFrames,
            nextTick=firstWave, interval=barrageInterval, travel=3, range=barrageRange, halfAngle=barrageHalfAngle,
            rays=barrageRays, context=context(items,p,'r',clock)}
    end
    s.ready[key] = clock + cd(items, p, key)
    if items and items.onCast then items.onCast(p, key, clock) end
    return true
end
-- Preview only: confirmation is performed by acceptHit, never by this callback.
local function canApplyLoveTap(ctx)
    return (ctx.kind == 'aa' or ctx.kind == 'q') and (ctx.corsairSecondary or not ctx.mfTapPrimary)
end

function Combat.damageMultiplier(s, ctx, target, clock, split)
    if not split and ctx and target and not fireplace(target)
        and canApplyLoveTap(ctx) and s.lastTarget ~= identity(target) then return 1.35 end
    return 1
end
function Combat.acceptHit(s, ctx, clock, target, amount, p, room, items, baseDamage, shot)
    if not ctx or not target or fireplace(target) or not amount or amount <= 0
        or (ctx.kind ~= 'aa' and ctx.kind ~= 'q') then return end
    local id = identity(target)
    local split = shot and shot.split
    if not split and canApplyLoveTap(ctx) then
        if not ctx.corsairSecondary then ctx.mfTapPrimary = true end
        if s.lastTarget ~= id then
            s.lastTarget, s.loveTapTarget, s.loveTapAt = id, target, clock
            s.ready.w = math.max(clock, (s.ready.w or 0) - 60)
        end
    end
    if ctx.kind ~= 'q' or ctx.corsairSecondary then return end
    local hit = ctx.mfNativeTargets or {}
    ctx.mfNativeTargets = hit
    hit[id] = true
    -- A context is shared across the native volley, including piercing and multi-shot.
    if not split and not ctx.corsairBounceQueued then
        ctx.corsairBounceQueued = true
        s.fx[#s.fx+1]={kind='qImpact',point=copy(target.Position),untilFrame=clock+6}
        local origin = ctx.origin or p.Position
        local heading = shot and shot.heading
        local direction = heading and unit(heading) or unit(target.Position - origin) or ctx.shotHeading
        if direction then
            local lethal = shot and shot.lethal
            if lethal == nil then lethal = amount >= (target.HitPoints or math.huge) end
            s.pendingBounce[#s.pendingBounce+1] = {point=copy(target.Position), facing=direction,
                lethal=lethal, resolveAt=clock+1, context=ctx, baseDamage=baseDamage or p.Damage,
                tearFlags=shot and shot.flags, throughGrid=shot and shot.throughGrid}
        end
    end
end
function Combat.loveTapTarget(s)
    if valid(s.loveTapTarget) then return s.loveTapTarget, s.loveTapAt end
end
function Combat.tookDamage(s, clock) s.lastDamage = clock end
function Combat.speed(s, clock)
    local elapsed = clock - (s.lastDamage or 0)
    if elapsed >= 210 then return 1.2 end
    if elapsed >= 120 then return 1.1 end
    return 1
end
function Combat.attackSpeed(s, clock) return s.wUntil and clock < s.wUntil and 1.35 or 1 end
function Combat.strut(s, clock) return math.max(0, math.min(1, ((s.wUntil or clock) - clock) / strutFrames)) end
function Combat.cancelUltimate(s) s.r = nil end
function Combat.resetRoom(s)
    s.r, s.rain, s.barrageWave, s.lastTarget = nil, nil, nil, nil
    s.muzzle = nil
    s.loveTapTarget, s.loveTapAt = nil, nil
    s.pendingBounce, s.fx = {}, {}
end
local function bouncePath(b, room, origin, target)
    if b.throughGrid or not room or not room.CheckLine then return true end
    return room:CheckLine(origin, target, 3, 0, false, false)
end

local function findBounceTarget(b, room)
    local chosen, bestTier, bestDistance
    for _, e in ipairs(enemies()) do
        if valid(e) and not b.context.mfNativeTargets[identity(e)] then
            local offset = e.Position - b.point
            local dist = length(offset)
            if dist > .001 and dist <= bounceRange then
                local along = (offset.X*b.facing.X + offset.Y*b.facing.Y)/dist
                for tier, cosine in ipairs(bounceCosines) do
                    if along >= cosine and (tier < #bounceCosines or dist <= bounceRange * .3) then
                        if (not bestTier or tier < bestTier or tier == bestTier and dist < bestDistance)
                            and bouncePath(b,room,b.point,e.Position) then
                            chosen, bestTier, bestDistance = e, tier, dist
                        end
                        break
                    end
                end
            end
        end
    end
    return chosen
end

local function showDud(s,b,clock,room)
    local destination=b.point+b.facing*dudRange
    local clear, collision=bouncePath(b,room,b.point,destination)
    if not clear then destination=collision or b.point end
    s.fx[#s.fx+1]={kind='qDud',from=b.point,to=copy(destination),travel=dudTravel,
        startFrame=clock,untilFrame=clock+dudTravel+4}
end
local function aimBounce(s,b,target,clock)
    local cue=b.effect
    local origin=b.point
    if cue then
        local progress=math.min(1,(clock-cue.startFrame)/bounceTravel)
        origin=cue.from+(cue.to-cue.from)*progress
    else
        cue={kind='bounce',travel=bounceTravel}
        b.effect=cue
        s.fx[#s.fx+1]=cue
    end
    cue.from, cue.to=origin,copy(target.Position)
    cue.startFrame, cue.untilFrame=clock,clock+bounceTravel+4
    b.destination,b.resolveAt=target,clock+bounceTravel
end
local function updateBounce(s,b,p,clock,room,items)
    local chosen=b.destination
    if not chosen then
        if clock < b.resolveAt then return true end
        chosen=findBounceTarget(b,room)
        if not chosen then showDud(s,b,clock,room); return false end
        aimBounce(s,b,chosen,clock)
        return true
    end
    if not valid(chosen) or b.context.mfNativeTargets[identity(chosen)] then
        local replacement=findBounceTarget(b,room)
        if not replacement then b.effect.untilFrame=clock; return false end
        aimBounce(s,b,replacement,clock)
        return true
    end
    local clear, collision=bouncePath(b,room,b.effect.from,chosen.Position)
    if not clear then
        b.effect.kind='qDud'
        b.effect.to=copy(collision or b.effect.from)
        b.effect.travel=math.max(1,clock-b.effect.startFrame)
        b.effect.untilFrame=clock+4
        return false
    end
    b.effect.to=copy(chosen.Position)
    if clock < b.resolveAt then return true end
    local ctx=b.context
    local previousCrit=ctx.crit
    ctx.corsairSecondary=true
    if b.lethal then ctx.crit=true
    elseif items and items.rerollCrit then items.rerollCrit(ctx) end
    local landed=deal(items,ctx,p,chosen,b.baseDamage)
    ctx.crit,ctx.corsairSecondary=previousCrit,nil
    b.effect.hit=landed
    if landed and b.tearFlags and TearFlags and b.tearFlags~=TearFlags.TEAR_NORMAL
        and valid(chosen) and chosen.ToNPC then
        local npc=chosen:ToNPC()
        if npc and npc.ApplyTearflagEffects then npc:ApplyTearflagEffects(chosen.Position,b.tearFlags,p,b.baseDamage) end
    end
    return false
end
local function updateBarrageWave(s,p,clock,room,items)
    local wave=s.barrageWave
    if not wave then return end
    local r=wave.channel
    local age=clock-wave.launchedAt
    local front=r.range*math.min(1,(age+.65)/r.travel)
    if front>wave.front then
        local coneEdge=math.cos(math.rad(r.halfAngle))
        local function contains(point)
            local d=point-wave.origin
            local dist=length(d)
            return (wave.front==0 or dist>wave.front) and dist<=front
                and (dist<.001 or (d.X*wave.facing.X+d.Y*wave.facing.Y)/dist>=coneEdge-.000001)
        end
        local amount=p.Damage*.22
        for _,e in ipairs(enemies()) do
            local fire=tearDamageableFire(e)
            if (fire or valid(e)) and contains(e.Position) then
                local id=identity(e)
                if not wave.hit[id] then
                    wave.hit[id]=true
                    local landed
                    if fire then landed=e:TakeDamage(amount,0,EntityRef(p),0)
                    else landed=deal(items,r.context,p,e,amount) end
                    if landed then
                        s.fx[#s.fx+1]={kind='rImpact',point=copy(e.Position),startFrame=clock,untilFrame=clock+6}
                    end
                end
            end
        end
        hitGrid(room,p,contains)
        wave.front=front
    end
    if age>r.travel then s.barrageWave=nil end
end

local function updateRain(rain,p,clock,room,items)
    if clock < rain.impactFrames[1] then return end
    local pulse = rain.ticks + 1
    local impact = rain.impactFrames[pulse]
    local damagePulse = impact and clock >= impact
    if damagePulse then rain.ticks,rain.landedAt[pulse]=pulse,clock end
    local amount = p.Damage * (1.5 / rainTicks)
    local center, radiusSquared = rain.center, rain.radius * rain.radius
    local function contains(point)
        local dx, dy = point.X - center.X, point.Y - center.Y
        return dx * dx + dy * dy <= radiusSquared
    end
    for _,enemy in ipairs(enemies()) do
        if contains(enemy.Position) then
            if valid(enemy) then
                local id = identity(enemy)
                if enemy.AddSlowing and clock >= (rain.slowRefreshAt[id] or 0) then
                    enemy:AddSlowing(EntityRef(p), rainSlowFrames, .6, Color(1,1,1,1,0,0,0))
                    rain.slowRefreshAt[id] = clock + rainSlowRefresh
                end
                if damagePulse then deal(items,rain.context,p,enemy,amount) end
            elseif damagePulse and tearDamageableFire(enemy) then
                enemy:TakeDamage(amount,0,EntityRef(p),0)
            end
        end
    end
    if damagePulse then hitGrid(room,p,contains) end
end

function Combat.update(s, p, clock, room, items)
    local keep = {}
    for _, b in ipairs(s.pendingBounce) do
        if updateBounce(s,b,p,clock,room,items) then keep[#keep+1]=b end
    end
    s.pendingBounce = keep
    local rain = s.rain
    if rain then
        if clock >= rain.untilFrame then s.rain = nil
        else updateRain(rain,p,clock,room,items) end
    end
    local r = s.r
    if r then
        r.origin = copy(p.Position)
        if clock >= r.untilFrame then s.r = nil
        elseif clock >= r.nextTick then
            r.nextTick = clock + r.interval
            local ctx = r.context
            if r.waves and items and items.rerollCrit then items.rerollCrit(ctx) end
            r.waves = (r.waves or 0) + 1
            s.barrageWave={channel=r, origin=copy(r.origin), facing=copy(r.facing),
                launchedAt=clock, number=r.waves, front=0, hit={}}
        end
    end
    updateBarrageWave(s,p,clock,room,items)
    local fx = {}
    for _, cue in ipairs(s.fx) do if clock < cue.untilFrame then fx[#fx+1] = cue end end
    s.fx = fx
end
return Combat
