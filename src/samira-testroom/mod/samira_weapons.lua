local Weapons = {}

local game, playerProvider, items, fired
local request, direction, aimPoint, allow, frame, lastHeld, currentHeld, lastAim
local lastVolley
local generation, firedCount = 0, 0
local shootAxes
local armPulse
local restorePulse
local releasedWeapon
local releasedAt, releasedCount
local qTearSpeed = 4 / 3

local function same(a, b)
    return a and b and GetPtrHash(a) == GetPtrHash(b)
end

local function weaponOf(p)
    return p and p:GetWeapon(1)
end

local function isRocketWeapon(weapon)
    return WeaponType and weapon:GetWeaponType() == WeaponType.WEAPON_ROCKETS
end

local function ludovico(weapon, entity)
    if WeaponType and weapon:GetWeaponType() == WeaponType.WEAPON_LUDOVICO_TECHNIQUE then return true end
    if not entity then return false end
    if entity.Type == EntityType.ENTITY_TEAR and TearFlags then
        return entity:ToTear():HasTearFlags(TearFlags.TEAR_LUDOVICO)
    end
    return entity.Type == EntityType.ENTITY_LASER and LaserSubType
        and entity.SubType == LaserSubType.LASER_SUBTYPE_RING_LUDOVICO
end

local function currentPulse(weapon)
    local primary = weapon:GetMainEntity()
    if not ludovico(weapon, primary) then return nil, false end
    return primary and primary:Exists() and primary or nil, true
end

local function pulseAvailable(pulse)
    if not pulse then return false end
    local tag = pulse:GetData().SamiraNativeWeapon
    return not (tag and tag.generation == generation and tag.context.persistentPulse and not tag.context.accepted)
end

local function activePulse(context)
    local weapon = weaponOf(context.player)
    return weapon and same(currentPulse(weapon), context.pulse)
end

function Weapons.attackRange(p, base)
    local weapon = weaponOf(p)
    if not weapon or not WeaponType then return base end
    local kind = weapon:GetWeaponType()
    if kind == WeaponType.WEAPON_BRIMSTONE or kind == WeaponType.WEAPON_LASER
        or kind == WeaponType.WEAPON_ROCKETS or ludovico(weapon, weapon:GetMainEntity()) then return 800 end
    if kind == WeaponType.WEAPON_SPIRIT_SWORD or kind == WeaponType.WEAPON_BONE
        or kind == WeaponType.WEAPON_NOTCHED_AXE then return 48 end
    return math.max(base, (p.TearRange or 0) * .8)
end

function Weapons.passesGrid(p)
    local weapon = weaponOf(p)
    if not weapon then return false end
    if WeaponType then
        local kind = weapon:GetWeaponType()
        if kind == WeaponType.WEAPON_BRIMSTONE or kind == WeaponType.WEAPON_LASER
            or kind == WeaponType.WEAPON_TECH_X or kind == WeaponType.WEAPON_ROCKETS then return true end
    end
    local flag = TearFlags and TearFlags.TEAR_SPECTRAL
    return flag ~= nil and p.TearFlags ~= nil and p.TearFlags & flag == flag
end

local function stopCharge(p)
    local weapon = weaponOf(p)
    if lastAim and weapon and weapon:GetCharge() > 0 then weapon:SetCharge(0) end
end

function Weapons.reset()
    releasedWeapon = nil
    if playerProvider then stopCharge(playerProvider()) end
    generation = generation + 1
    request, direction, aimPoint, allow, frame, lastAim = nil, nil, nil, false, nil, nil
    lastHeld, currentHeld, lastVolley = nil, nil, nil
end

function Weapons.update(p, _, aim, enabled, point)
    if not enabled then
        releasedWeapon = nil
        stopCharge(p)
        request, frame, lastAim, lastHeld, currentHeld = nil, nil, nil, nil, nil
    end
    direction, aimPoint, allow = aim, point, enabled
end

function Weapons.requestQ(p, aim, clock, point, releaseAt, chargeDuringWindup, lockAim)
    local weapon = weaponOf(p)
    if request or not weapon or not aim or aim:Length() <= .001 then return false end
    local pulse, remote = currentPulse(weapon)
    if remote and not pulseAvailable(pulse) then return false end
    request = {player = p, heading = aim:Normalized(), clock = clock, pulse = pulse, point = point,
        releaseAt = releaseAt or clock, chargeDuringWindup = chargeDuringWindup == true, lockAim = lockAim == true}
    currentHeld, lastHeld, frame = nil, nil, nil
    return true
end

function Weapons.isChargeWeapon(p)
    local weapon = weaponOf(p)
    return weapon and weapon:GetMaxCharge() > 0
end

function Weapons.hasPendingQ(p)
    return request ~= nil and same(request.player, p)
end

function Weapons.trackCursor(p, point)
    if request and not request.lockAim and same(request.player, p) and not request.pulse and game:GetFrameCount() > request.releaseAt
        and Weapons.isChargeWeapon(p) then
        if request.chargeDuringWindup and isRocketWeapon(weaponOf(p)) then return end
        local delta = point - p.Position
        if delta:Length() > .001 then request.heading = delta:Normalized() end
        request.point = point
    end
end

local function remoteAim(weapon, point, aim)
    if not point then return aim, false end
    local remote = weapon:GetMainEntity()
    if not remote or not remote:Exists() or not remote.Position then return aim, false end
    local rocketMarker = isRocketWeapon(weapon)
        and EffectVariant and remote.Type == EntityType.ENTITY_EFFECT and remote.Variant == EffectVariant.TARGET
    if not ludovico(weapon, remote) and not rocketMarker then
        return aim, false
    end
    local offset = point - remote.Position
    if offset:Length() <= 4 then return nil, true, true end
    return offset:Normalized(), false, true
end

local function beginFrame(p)
    if not allow or not same(p, playerProvider()) then return end
    local weapon = weaponOf(p)
    if not weapon then return end
    local clock = game:GetFrameCount()
    if request and not same(request.player, p) then request = nil end
    local maxCharge, charge = weapon:GetMaxCharge(), weapon:GetCharge()
    if charge < maxCharge - .001 then releasedWeapon = nil end
    if request and clock - request.clock > math.max(240, math.ceil(maxCharge * 2) + 30) then
        stopCharge(p)
        request = nil
    end
    if request then
        local pulse, remote = currentPulse(weapon)
        request.pulse = pulse
        if remote and not pulseAvailable(pulse) then
            lastHeld, currentHeld, frame = currentHeld, nil, nil
            return
        end
    end
    if request and clock < request.releaseAt then
        -- Charge by holding the native input. The firing batch opens at releaseAt.
        local precharge = request.chargeDuringWindup and maxCharge > 0 and not request.pulse
            and not isRocketWeapon(weapon)
        lastHeld, currentHeld, frame = currentHeld, precharge and request.heading or nil, nil
        if precharge then lastAim = request.heading end
        return
    end
    local aimingRequest = request
    if request and request.pulse then armPulse(p, clock) end
    local aim = aimingRequest and aimingRequest.heading or direction
    local point = aimPoint
    if aimingRequest then point = aimingRequest.point end
    local aligned, remote
    aim, aligned, remote = remoteAim(weapon, point, aim)
    -- Release once at full charge, then let the native weapon finish its
    -- discharge while the button is held again. Releasing on every full
    -- charge frame interrupts weapons that keep charge during their beam.
    if releasedWeapon and releasedCount == firedCount and clock - releasedAt >= 6 then
        releasedWeapon = nil
    end
    local release = not remote and maxCharge > 0 and charge >= maxCharge - .001
        and releasedWeapon ~= weapon:GetWeaponType()
    if release then
        releasedWeapon, releasedAt, releasedCount = weapon:GetWeaponType(), clock, firedCount
    end
    if aim and aim:Length() > .001 then
        aim = aim:Normalized()
    else
        aim = nil
    end
    if not aim and not (lastAim and charge > 0) and not (aligned and request) then
        lastHeld, currentHeld, lastAim, frame = currentHeld, nil, nil, nil
        return
    end

    lastHeld, currentHeld = currentHeld, not release and aim or nil
    frame = {
        player = p, weapon = weapon, clock = clock, request = request,
        heading = aim or lastAim or request and request.heading, count = weapon:GetNumFired(),
        outputs = {}, remote = remote or ludovico(weapon, weapon:GetMainEntity())
            or isRocketWeapon(weapon),
    }
    lastAim = aim or lastAim
end

function Weapons.chargeStatus(p)
    local weapon = weaponOf(p)
    if not weapon then return end
    local maximum = weapon:GetMaxCharge()
    if maximum <= 0 then return end
    local charge = math.max(0, weapon:GetCharge())
    return {progress = math.min(1, charge / maximum),
        visible = allow and (currentHeld ~= nil or request ~= nil or charge > 0),
        firing = releasedWeapon == weapon:GetWeaponType()}
end

function Weapons.input(p, hook, action)
    local axis = shootAxes[action]
    if not axis then return end
    local heading = currentHeld
    if not heading or not allow or not same(p, playerProvider()) then
        return hook == InputHook.GET_ACTION_VALUE and 0 or false
    end
    local value = math.max(0, heading[axis[1]] * axis[2])
    if hook == InputHook.GET_ACTION_VALUE then return value end
    if hook == InputHook.IS_ACTION_PRESSED then return value > .001 end
    if hook == InputHook.IS_ACTION_TRIGGERED then
        return value > .001 and (not lastHeld or lastHeld[axis[1]] * axis[2] <= .001)
    end
end

local function newContext(batch)
    if not batch.context then
        local kind = batch.request and 'q' or 'aa'
        local context = items.newAttack(batch.player, kind, batch.clock)
        context.nativeWeapon = true
        context.weaponType = batch.weapon and batch.weapon:GetWeaponType()
        context.shotHeading = kind == 'q' and batch.heading or nil
        context.damageMultiplier = kind == 'q' and 1.5 or 1
        batch.context = context
    end
    return batch.context
end

local function shotTag(entity, depth)
    if not entity or entity.Type == EntityType.ENTITY_PLAYER then return end
    local tag = entity:GetData().SamiraNativeWeapon
    if tag and tag.generation == generation then return tag end
    if depth == 0 then return end
    if entity.Type == EntityType.ENTITY_KNIFE then
        -- Native melee hitboxes can reference the swing through the knife API.
        local knife = entity:ToKnife()
        local mainKnife = knife.GetHitboxParentKnife and knife:GetHitboxParentKnife()
        local inherited = shotTag(mainKnife, depth - 1)
        if inherited then return inherited end
    end
    return shotTag(entity.Parent, depth - 1) or shotTag(entity.SpawnerEntity, depth - 1)
end

local function ownerMatches(p, entity)
    local owner = entity.SpawnerEntity or entity.Parent
    for _ = 1, 4 do
        if not owner then return false end
        if same(p, owner) then return true end
        if owner.Type == EntityType.ENTITY_FAMILIAR and same(p, owner:ToFamiliar().Player) then return true end
        owner = owner.SpawnerEntity or owner.Parent
    end
    return false
end

local function mirrorsPlayer(entity)
    return FamiliarVariant and (entity.Variant == FamiliarVariant.INCUBUS
        or entity.Variant == FamiliarVariant.TWISTED_BABY)
end

local function rotateOutput(batch, entity)
    if not batch.turn or not entity:Exists() then return end
    local data = entity:GetData()
    if data.SamiraSplitTear == generation then return end
    local previous = data.SamiraAim
    local speed = entity.Type == EntityType.ENTITY_TEAR and batch.context.kind == 'q' and qTearSpeed or 1
    if speed == 1 and math.abs(batch.turn) < .001 and not previous and entity.Type ~= EntityType.ENTITY_LASER then return end
    if previous and previous.context == batch.context then return end
    local state = {context = batch.context}
    data.SamiraAim = state
    local turn, kind = batch.turn, entity.Type
    if kind == EntityType.ENTITY_TEAR or kind == EntityType.ENTITY_BOMB or kind == EntityType.ENTITY_EFFECT then
        if entity.Velocity and entity.Velocity:Length() > .001 then
            local velocity = entity.Velocity
            if kind == EntityType.ENTITY_TEAR and batch.player.GetTearMovementInheritance
                and same(entity.SpawnerEntity, batch.player) then
                local nativeMove = batch.player:GetTearMovementInheritance(batch.nativeHeading)
                local aimedMove = batch.player:GetTearMovementInheritance(batch.heading)
                velocity = (velocity - nativeMove):Rotated(turn) * speed + aimedMove
            else
                velocity = velocity:Rotated(turn) * speed
            end
            entity.Velocity = velocity
        end
        if kind == EntityType.ENTITY_TEAR then
            local tear = entity:ToTear()
            if tear.ContinueVelocity and tear.ContinueVelocity:Length() > .001 then
                tear.ContinueVelocity = tear.ContinueVelocity:Rotated(turn) * speed
            end
        end
    elseif kind == EntityType.ENTITY_LASER then
        local laser = entity:ToLaser()
        if laser:IsCircleLaser() then
            if laser.Velocity then laser.Velocity = laser.Velocity:Rotated(turn) end
            return
        end
        -- LastAngleDegrees is the engine's previous trace. Let it see our
        -- angle change so it can refresh cached geometry itself.
        for _, key in ipairs({'AngleDegrees', 'StartAngleDegrees'}) do
            local angle = laser[key]
            if angle ~= nil then
                local base = previous and previous[key]
                if base and math.abs(angle - base.corrected) < .001 then angle = base.original end
                state[key] = {original = angle, corrected = angle + turn}
                laser[key] = angle + turn
            end
        end
    elseif kind == EntityType.ENTITY_KNIFE then
        local knife = entity:ToKnife()
        local angle = knife.Rotation
        local base = previous and previous.Rotation
        if base and math.abs(angle - base.corrected) < .001 then angle = base.original end
        state.Rotation = {original = angle, corrected = angle + turn}
        knife.Rotation = angle + turn
    end
end

local function setNativeAim(batch, heading)
    if batch.remote or batch.nativeHeading or not batch.heading or not heading or heading:Length() < .001 then return end
    batch.nativeHeading = heading:Normalized()
    batch.turn = math.deg(math.atan(batch.heading.Y, batch.heading.X) - math.atan(heading.Y, heading.X))
    for _, entity in ipairs(batch.outputs) do rotateOutput(batch, entity) end
    batch.outputs = nil
end

local function aimOutput(batch, entity)
    if batch.remote then return end
    if batch.nativeHeading then rotateOutput(batch, entity)
    else batch.outputs[#batch.outputs + 1] = entity end
end

local function tintShot(entity, context, split)
    local brimstone = WeaponType and WeaponType.WEAPON_BRIMSTONE
    local q = context.kind == 'q'
    if context.missFortune and brimstone and context.weaponType == brimstone
        and entity.Type == EntityType.ENTITY_LASER and not split and not context.persistentPulse then
        local native = entity:GetColor()
        if native.R == 1 and native.G == 1 and native.B == 1 and native.RO == 0 and native.GO == 0 and native.BO == 0 then
            local color = q and Color(1, .88, .57, native.A, .14, .35, .12)
                or Color(.98, .74, .45, native.A, .06, .26, .11)
            entity:SetColor(color, math.max(1, entity.Timeout or 90), 5, false, false)
        end
    elseif q then
        local seconds = entity.Type == EntityType.ENTITY_KNIFE and 1 or 3
        entity:SetColor(Color(.9, .55, .62, 1, .18, .04, .1), seconds * 30, 5, false, false)
    end
end

local function tag(p, entity, context, split, derived)
    if not entity or not entity:Exists() then return end
    local data = entity:GetData()
    if data.SamiraSplitTear == generation and not split then return end
    local old = data.SamiraNativeWeapon
    if old and old.context == context then
        old.split = old.split or split
        old.derived = old.derived or derived
        return
    end
    if old and old.generation == generation and old.context.persistentPulse and not old.context.accepted then return end
    local tagged = {context = context, generation = generation, split = split, derived = derived}
    data.SamiraNativeWeapon = tagged
    if context.persistentPulse then
        tagged.previous, tagged.preColor = old, entity:GetColor()
    end
    if entity.Type == EntityType.ENTITY_TEAR then items.tagTear(p, entity:ToTear(), context, split) end
    tintShot(entity, context, split)
    if context.kind ~= 'q' then
        if old and old.preScale then entity.SpriteScale = old.preScale end
        return
    end
    if entity.Type == EntityType.ENTITY_TEAR then
        entity = entity:ToTear()
        if context.persistentPulse then tagged.preTearScale = entity.Scale end
        entity.Scale = entity.Scale * 1.18
    elseif not old or old.context.kind ~= 'q' then
        data.SamiraNativeWeapon.preScale = entity.SpriteScale
        entity.SpriteScale = entity.SpriteScale * 1.12
    else
        data.SamiraNativeWeapon.preScale = old.preScale
    end
end

local function mirroredOutput(entity, familiar)
    local volley = frame or lastVolley
    if not volley or volley.clock ~= game:GetFrameCount() or not entity or not familiar
        or familiar.Type ~= EntityType.ENTITY_FAMILIAR or not mirrorsPlayer(familiar)
        or not same(familiar:ToFamiliar().Player, volley.player) then return end
    if entity:GetData().SamiraSplitTear == generation then return true end
    if volley.completed then
        tag(volley.player, entity, volley.context)
        aimOutput(volley, entity)
    else
        volley.mirrored = volley.mirrored or {}
        volley.mirrored[#volley.mirrored + 1] = entity
    end
    return true
end

local function inheritOutput(entity)
    local data = entity:GetData()
    local tagAtSpawn = data.SamiraNativeWeapon
    if tagAtSpawn and tagAtSpawn.generation == generation and tagAtSpawn.derived then return true end
    local inherited = shotTag(entity.Parent, 3) or shotTag(entity.SpawnerEntity, 3)
    if not inherited then return false end
    if inherited.split and entity.Type == EntityType.ENTITY_TEAR then
        data.SamiraSplitTear = generation
    end
    tag(inherited.context.player, entity, inherited.context, inherited.split, true)
    return true
end

local function claimOutput(batch, entity)
    if inheritOutput(entity) then return end
    if mirroredOutput(entity, entity.SpawnerEntity or entity.Parent) then return end
    tag(batch.player, entity, newContext(batch))
    aimOutput(batch, entity)
    batch.hadOutput = true
end

local function output(entity)
    if not entity then return end
    local batch = frame
    if not batch or not ownerMatches(batch.player, entity) then
        -- Delayed native children can spawn outside the player update.
        -- Snapshot ancestry before the engine drops the parent, for every
        -- carrier (including tears and bombs), not only child lasers.
        inheritOutput(entity)
        return
    end
    local data = entity:GetData()
    if data.SamiraSplitTear == generation then return end
    if entity.Type == EntityType.ENTITY_TEAR then
        -- The generic callback can arrive before MC_POST_FIRE_SPLIT_TEAR.
        if data.SamiraPendingTear == batch then return end
        batch.tears = batch.tears or {}
        batch.tears[#batch.tears + 1] = entity
        data.SamiraPendingTear = batch
    else
        claimOutput(batch, entity)
    end
end

local function resolveTear(batch, tear)
    local data = tear:GetData()
    if data.SamiraPendingTear ~= batch then return end
    data.SamiraPendingTear = nil
    claimOutput(batch, tear)
end

local function resolveTears(batch)
    for _, tear in ipairs(batch.tears or {}) do
        if tear:Exists() then resolveTear(batch, tear) end
    end
    batch.tears = nil
end

local function inheritedOutput(tear, source)
    if not tear or tear.Type ~= EntityType.ENTITY_TEAR then return end
    local data = tear:GetData()
    data.SamiraSplitTear, data.SamiraPendingTear = generation, nil
    local inherited = shotTag(source, 3)
    if frame and source:Exists() and source:GetData().SamiraPendingTear == frame then
        resolveTear(frame, source)
        inherited = shotTag(source, 3)
    end
    if inherited and inherited.generation == generation then
        tag(inherited.context.player, tear, inherited.context, true)
    end
end

local function complete(batch, heading, weapon)
    if batch.outputs then setNativeAim(batch, heading) end
    if weapon then
        local entity = weapon:GetMainEntity()
        -- Reused knives and beam handles are only claimed on real discharge.
        if entity and ownerMatches(batch.player, entity) then
            local data = entity:GetData()
            if data.SamiraSplitTear ~= generation and data.SamiraPendingTear ~= batch then
                tag(batch.player, entity, newContext(batch))
                aimOutput(batch, entity)
            end
        end
    end
    if batch.completed then return end
    batch.completed = true
    local context = newContext(batch)
    if batch.mirrored then
        for _, entity in ipairs(batch.mirrored) do
            if entity:Exists() then
                tag(batch.player, entity, context)
                aimOutput(batch, entity)
            end
        end
        batch.mirrored = nil
    end
    if not context.persistentPulse then lastVolley = batch end
    if batch.rocketMarker then tag(batch.player, batch.rocketMarker, context) end
    if request == batch.request then request = nil end
    firedCount = firedCount + 1
    if fired then fired(context.kind, batch.heading or heading, context) end
end

local function rocketEffect(effect)
    if not EffectVariant then return end
    local variant = effect.Variant
    if variant ~= EffectVariant.TARGET and variant ~= EffectVariant.ROCKET and variant ~= EffectVariant.SMALL_ROCKET then
        return
    end
    if shotTag(effect, 0) then return end
    local inherited = shotTag(effect.Parent, 3) or shotTag(effect.SpawnerEntity, 3)
    if inherited then
        tag(inherited.context.player, effect, inherited.context, inherited.split)
        return
    end
    local batch = frame
    if variant == EffectVariant.TARGET and batch and isRocketWeapon(batch.weapon)
        and ownerMatches(batch.player, effect) then
        if batch.completed then
            tag(batch.player, effect, batch.context)
        else
            batch.rocketMarker = effect
        end
    end
end

armPulse = function(p, clock)
    local pulse, heading = request.pulse, request.heading
    if not pulse:Exists() then
        request = nil
        return
    end
    local batch = {player = p, clock = clock, request = request, heading = heading}
    local context = newContext(batch)
    context.persistentPulse, context.pulse = true, pulse
    restorePulse(pulse)
    tag(p, pulse, context)
    complete(batch, heading)
end

local function trigger(_, heading, amount, owner, weapon)
    local batch = frame
    if amount < 1 then return end
    if batch and same(owner, batch.player) then
        complete(batch, heading, weapon)
    elseif weapon and owner and owner.Type == EntityType.ENTITY_FAMILIAR then
        -- Incubus-like copies share the current action but cannot consume Q first.
        mirroredOutput(weapon:GetMainEntity(), owner)
    end
end

local function endFrame(p)
    local batch = frame
    if not batch or not same(batch.player, p) then return end
    resolveTears(batch)
    if not batch.completed and (batch.hadOutput or batch.weapon:GetNumFired() > batch.count) then
        complete(batch, batch.reportedHeading or batch.weapon:GetDirection(), batch.weapon)
    end
    if not currentHeld then lastAim = nil end
    frame = nil
end

function Weapons.context(p, source, extraSource)
    local entity = extraSource and extraSource.Entity or source and source.Entity
    if not entity then return end
    local tag = shotTag(entity, 3)
    local weapon = weaponOf(p)
    if weapon and same(weapon:GetMainEntity(), entity) and ludovico(weapon, entity)
        and (not tag or not tag.context.persistentPulse or tag.context.accepted) then
        restorePulse(entity)
        local clock = game:GetFrameCount()
        tag = shotTag(entity, 0)
        if not tag or clock >= (tag.context.continuousUntil or 0) then
            local context = items.newAttack(p, 'aa', clock)
            context.nativeWeapon, context.damageMultiplier = true, 1
            context.continuousUntil = clock + math.max(1, math.ceil(p.MaxFireDelay + 1))
            tag = {context = context, generation = generation}
            entity:GetData().SamiraNativeWeapon = tag
        end
    elseif tag and tag.context.persistentPulse and same(entity, tag.context.pulse)
        and (tag.context.accepted or not activePulse(tag.context)) then
        restorePulse(entity)
        tag = tag.previous
    end
    if tag and tag.generation == generation and same(tag.context.player, p) then
        return tag.context, entity.Type ~= EntityType.ENTITY_KNIFE, entity.Type, tag.split == true
    end
end

restorePulse = function(entity)
    local data = entity:GetData()
    local tag = data.SamiraNativeWeapon
    if not tag or not tag.context.persistentPulse then return end
    -- Children inherit the pulse as a shot context, but are not the reused orb.
    if not same(entity, tag.context.pulse) then return end
    if tag.generation == generation and not tag.context.accepted and activePulse(tag.context) then return end
    if tag.preTearScale then entity:ToTear().Scale = tag.preTearScale end
    if tag.preScale then entity.SpriteScale = tag.preScale end
    if tag.preColor then entity:SetColor(tag.preColor, 1, 5, false, false) end
    data.SamiraNativeWeapon = tag.previous
end

local function status()
    local p = playerProvider()
    local weapon = weaponOf(p)
    if not weapon then
        Isaac.ConsoleOutput('Samira has no active primary weapon.\n')
        return
    end
    Isaac.ConsoleOutput(('Weapon %s, charge %.2f / %.2f, native axis aligned %s, pending Q %s, fired %d.\n')
        :format(tostring(weapon:GetWeaponType()), weapon:GetCharge(), weapon:GetMaxCharge(),
            tostring(weapon:IsAxisAligned()), tostring(request ~= nil), firedCount))
    if lastVolley and lastVolley.turn then
        Isaac.ConsoleOutput(('Last volley cursor correction %.2f degrees.\n'):format(lastVolley.turn))
    end
end

function Weapons.init(mod, currentGame, getPlayer, itemModule, onFired)
    game, playerProvider, items, fired = currentGame, getPlayer, itemModule, onFired
    shootAxes = {
        [ButtonAction.ACTION_SHOOTLEFT] = {'X', -1}, [ButtonAction.ACTION_SHOOTRIGHT] = {'X', 1},
        [ButtonAction.ACTION_SHOOTUP] = {'Y', -1}, [ButtonAction.ACTION_SHOOTDOWN] = {'Y', 1},
    }
    local function callback(name, action)
        if ModCallbacks[name] then mod:AddCallback(ModCallbacks[name], action) end
    end
    callback('MC_PRE_PLAYER_UPDATE', function(_, p) beginFrame(p) end)
    callback('MC_POST_PLAYER_UPDATE', function(_, p) endFrame(p) end)
    callback('MC_POST_TEAR_UPDATE', function(_, tear) restorePulse(tear) end)
    callback('MC_POST_LASER_INIT', function(_, laser) inheritOutput(laser) end)
    callback('MC_POST_LASER_UPDATE', function(_, laser)
        restorePulse(laser)
        local data = laser:GetData()
        local tag, aim = data.SamiraNativeWeapon, data.SamiraAim
        -- Attached native beams can reapply the player's head direction on
        -- every update. Keep the corrected volley angle throughout discharge.
        if tag and tag.generation == generation and aim and aim.context == tag.context
            and not laser:IsCircleLaser() then
            if aim.AngleDegrees then laser.AngleDegrees = aim.AngleDegrees.corrected end
            if aim.StartAngleDegrees then laser.StartAngleDegrees = aim.StartAngleDegrees.corrected end
        end
    end)
    callback('MC_POST_EFFECT_INIT', function(_, effect) rocketEffect(effect) end)
    callback('MC_POST_EFFECT_UPDATE', function(_, effect) rocketEffect(effect) end)
    callback('MC_POST_TRIGGER_WEAPON_FIRED', trigger)
    callback('MC_POST_WEAPON_FIRE', function(_, weapon, heading)
        local batch = frame
        if batch and same(weapon:GetOwner(), batch.player) then
            if batch.hadOutput then setNativeAim(batch, heading)
            elseif batch.tears then batch.reportedHeading = heading end
        end
    end)
    for _, name in ipairs({
        'MC_POST_FIRE_TEAR', 'MC_POST_FIRE_BOMB', 'MC_POST_FIRE_BRIMSTONE',
        'MC_POST_FIRE_BRIMSTONE_BALL', 'MC_POST_FIRE_TECH_LASER', 'MC_POST_FIRE_TECH_X_LASER',
        'MC_POST_FAMILIAR_FIRE_PROJECTILE', 'MC_POST_FAMILIAR_FIRE_BRIMSTONE', 'MC_POST_FAMILIAR_FIRE_TECH_LASER',
    }) do
        if name:find('FAMILIAR', 1, true) then
            callback(name, function(_, entity)
                if entity then mirroredOutput(entity, entity.SpawnerEntity or entity.Parent) end
            end)
        else
            callback(name, function(_, entity) output(entity) end)
        end
    end
    callback('MC_POST_FIRE_SPLIT_TEAR', function(_, child, source)
        -- The sword callback has shared this numeric ID on some releases.
        if source then inheritedOutput(child, source)
        elseif child and child.Type == EntityType.ENTITY_KNIFE then output(child) end
    end)
    if ModCallbacks.MC_POST_FIRE_SWORD ~= ModCallbacks.MC_POST_FIRE_SPLIT_TEAR then
        callback('MC_POST_FIRE_SWORD', function(_, knife) output(knife) end)
    end
    callback('MC_POST_KNIFE_UPDATE', function(_, knife)
        local data = knife:GetData()
        local tag = data.SamiraNativeWeapon
        local releaseGrace = (not KnifeVariant or knife.Variant == KnifeVariant.MOMS_KNIFE) and 2 or 30
        if tag and tag.context.kind == 'q' and game:GetFrameCount() > tag.context.clock + releaseGrace and not knife:IsFlying() then
            if tag.preScale then knife.SpriteScale = tag.preScale end
            data.SamiraNativeWeapon = nil
        end
    end)
    callback('MC_POST_GAME_STARTED', function()
        Weapons.reset()
        firedCount = 0
    end)
    callback('MC_POST_NEW_ROOM', Weapons.reset)
    callback('MC_EXECUTE_CMD', function(_, command)
        if command == 'samiraweapon' then status() end
    end)
    if Console and Console.RegisterCommand then
        Console.RegisterCommand('samiraweapon', 'Show the active Samira weapon and charge',
            'samiraweapon', false, AutocompleteType.NONE)
    end
    Weapons.reset()
end

return Weapons
