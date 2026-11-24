local Effects = {}
local Sprites = include('miss_fortune_sprite')
local recallTracks = include('miss_fortune_recall_tracks')
local strutTracks = include('miss_fortune_strut_tracks')
local lifecycleTracks = include('miss_fortune_lifecycle_tracks')
local muzzleTracks = include('miss_fortune_muzzle_tracks')
local particle, ultimateParticle, recallParticle, recallPropParticle, recallPetParticle
local recallBurstParticle
local strutParticle, jokeParticle, shotParticle, danceParticle, lifecycleParticle, tauntParticle
local bounceFrames = 8
local bulletHeightScale = .55

function Effects.playSound(cue, volume, loop)
    if not SFXManager or not Isaac.GetSoundIdByName then return end
    local sound = Isaac.GetSoundIdByName('Miss Fortune '..cue)
    if not sound or sound <= 0 then return end
    SFXManager():Play(sound, volume, 0, loop == true, 1)
    return sound
end

function Effects.stopSound(sound)
    if sound and SFXManager then SFXManager():Stop(sound) end
end

function Effects.playBulletSound(kind, wave)
    if kind=='q' and Effects.playSound('Q',.64) then return end
    if kind=='r' and Effects.playSound('R Wave',.27) then return end
    local sound = SoundEffect and SoundEffect.SOUND_BULLET_SHOT
    if not sound or not SFXManager then return end
    if kind == 'r' then
        SFXManager():Play(sound, .37, 0, false, wave % 2 == 0 and 1.02 or .9)
    elseif kind == 'q' then
        SFXManager():Play(sound, .53, 0, false, 1.17)
    elseif kind == 'e' then
        SFXManager():Play(sound, .19, 0, false, 1.42)
    end
end

local function sprite()
    if particle == nil and Sprite then
        local candidate, loaded = Sprite("gfx/mf/projectiles.anm2", true)
        particle = loaded and candidate or false
    end
    return particle
end

local function drawSprite(art, name, pos, rotation, sx, sy, color, frame)
    if not art then return false end
    art:SetFrame(name, frame or 0)
    art.Rotation = rotation
    art.Scale = Vector(sx, sy)
    art.Color = color
    art:Render(pos)
    return true
end

local function draw(name, pos, rotation, sx, sy, color)
    return drawSprite(sprite(), name, pos, rotation, sx, sy, color)
end

function Effects.prepareShots()
    if shotParticle == nil and Sprite then
        local candidate, loaded = Sprite('gfx/mf/shot_effects.anm2', true)
        shotParticle = loaded and candidate or false
    end
end

local function drawShotSprite(name, pos, angle, sx, sy, alpha)
    return drawSprite(shotParticle, name, pos, angle, sx, sy, Color(1,1,1,alpha))
end

function Effects.prepareJoke()
    if jokeParticle == nil and Sprite then
        local candidate, loaded = Sprite('gfx/mf/joke_effects.anm2', true)
        jokeParticle = loaded and candidate or false
    end
end

local function jokeFade(age, duration)
    if age < 0 or age >= duration then return 0 end
    return math.min(1, (age + 1) / 3, (duration - age) / 5)
end

local function drawJoke(name, pos, rotation, sx, sy, alpha)
    if alpha > 0 then drawSprite(jokeParticle,name,pos,rotation,sx,sy,Color(1,1,1,alpha)) end
end

function Effects.renderJoke(pos, frame, direction, introDuration, bodyDuration)
    if not jokeParticle then return end

    -- Skin69 starts the intro ring at frame 20 and the flash eight ticks later.
    local ringAge = frame - 20
    local ringScale = .42 + .012 * math.max(0, ringAge)
    drawJoke('JokeIntroRing',pos,0,ringScale,ringScale*.58,.48*jokeFade(ringAge,15))
    local yaw = direction * math.pi / 4
    local flashPos = pos + Vector(24*math.cos(yaw),-44-18*math.sin(yaw))
    drawJoke('JokeIntroFlash',flashPos,0,.46,.46,.88*jokeFade(frame-28,5))

    -- The source intro ends before its frame-64 cue. Joke Spam repeats it at frame 8.
    local punchAge = frame - introDuration - 8
    drawJoke('JokeSpamBeam',pos+Vector(0,-21),0,.64,.65,.82*jokeFade(punchAge,21))
    drawJoke('JokeSpamGold',pos+Vector(0,-7),0,.48,.35,.66*jokeFade(punchAge,18))

    local loopAge = frame - introDuration - bodyDuration
    if loopAge < 0 then return end
    local rise = math.min(1,(loopAge+1)/6)
    local pulse = (.78+.22*math.sin(loopAge*.16))*rise
    drawJoke('JokeLoopLogo',pos+Vector(0,3),0,.54,.39,.88*rise)
    drawJoke('JokeLoopBeam',pos+Vector(0,-21),0,.58,.65,.58*pulse)
    for i=0,3 do
        local age = (loopAge+i*5)%18
        local x = (i-1.5)*11 + math.sin((loopAge+i*7)*.19)*7
        drawJoke('JokeLoopConfetti',pos+Vector(x,-52+age*2.6),i*55+age*11,
            .28,.28,.8*rise*jokeFade(age,18))
    end
end

function Effects.prepareDance()
    if danceParticle == nil and Sprite then
        local candidate, loaded = Sprite('gfx/mf/dance_effects.anm2', true)
        danceParticle = loaded and candidate or false
    end
end

local function drawDance(name,pos,rotation,sx,sy,alpha)
    if alpha>0 then drawSprite(danceParticle,name,pos,rotation,sx,sy,Color(1,1,1,alpha)) end
end

function Effects.renderDance(pos,frame)
    if not danceParticle then return end
    local stage = pos + Vector(0,5)
    -- Four overlapping logo particles, emitted twice a second and alive for two seconds.
    local glow = 0
    for age=frame%15,math.min(frame,59),15 do
        glow = glow + 1 - math.abs(age/30-1)
    end
    glow = math.min(1,glow/2)
    drawDance('DanceHalo',stage,0,.65,.43,.40*glow)
    drawDance('DanceLogoRed',stage,0,.66,.55,.24*glow)
    drawDance('DanceLogoGold',stage,0,.66,.55,.70*glow)

    local beat = frame - 4
    if beat>=0 then
        local age = beat%15
        if age<9 then
            local phase = age/9
            local alpha = phase<.25 and 1-.73*phase/.25 or .27*(1-phase)/.75
            local side = math.floor(beat/15)%2==0 and -1 or 1
            drawDance('DanceFlash',pos+Vector(side*25,-22),side*18,.43,.43,.72*alpha)
        end
    end

    for age=frame%6,math.min(frame,29),6 do
        local seed = (frame-age)/6
        local angle = seed*137.507764
        local drift = Vector(10+age*.65,0):Rotated(angle)
        local alpha = math.min(1,age/2,(30-age)/7)
        local point = pos+Vector(drift.X,drift.Y*.37-10-age*.7)
        drawDance('DanceFeather',point,angle+age*5,.37,.37,.50*alpha)
        local spark = pos+Vector(-drift.X,drift.Y*.34-5-age*.82)
        drawDance('DanceSpark',spark,angle,.28,.28,.48*alpha)
    end
end

local function drawUltimateEffect(name, pos, rotation, sx, sy, color)
    if ultimateParticle == nil and Sprite then
        local candidate, loaded = Sprite('gfx/mf/ultimate_effects.anm2', true)
        ultimateParticle = loaded and candidate or false
    end
    return drawSprite(ultimateParticle, name, pos, rotation, sx, sy, color)
end

function Effects.prepareStageEffects()
    if recallParticle == nil and Sprite then
        local candidate, loaded = Sprite('gfx/mf/recall_effects.anm2', true)
        recallParticle = loaded and candidate or false
    end
end
function Effects.prepareRecallBursts()
    if recallBurstParticle == nil and Sprite then
        local candidate, loaded = Sprite('gfx/mf/recall_bursts.anm2', true)
        recallBurstParticle = loaded and candidate or false
    end
end

local function drawRecallEffect(name, pos, sx, sy, color, angle)
    Effects.prepareStageEffects()
    return drawSprite(recallParticle, name, pos, angle or 0, sx, sy, color)
end

local function drawRecallProp(name, pos, rotation, sx, sy, color)
    if recallPropParticle == nil and Sprite then
        local candidate, loaded = Sprite('gfx/mf/recall_props.anm2', true)
        recallPropParticle = loaded and candidate or false
    end
    return drawSprite(recallPropParticle, name, pos, rotation, sx, sy, color)
end

local function rigOffset(x,y,z,orientation,scale,pixelScale)
    -- The native actor and Companion use the same 50-degree view elevation.
    local screenX = x*orientation.cos+z*orientation.sin
    local depth = z*orientation.cos-x*orientation.sin
    return Vector(screenX*pixelScale*scale.X,(depth*.766044-y*.642788)*pixelScale*scale.Y)
end

function Effects.prepareTaunt()
    if tauntParticle == nil and Sprite then
        local candidate, loaded = Sprite('gfx/mf/taunt_effects.anm2', true)
        tauntParticle = loaded and candidate or false
    end
end

function Effects.renderTaunt(origin,frame,direction,scale,pixelScale)
    if not tauntParticle then return end
    local sx,sy=math.abs(scale.X),math.abs(scale.Y)
    if frame<39 then
        local age=frame/39
        local size=.71+.32*age
        drawSprite(tauntParticle,'TauntRing',origin,0,size*sx,.62*size*sy,Color(1,1,1,1-age))
    end
    if frame<30 then
        local age=frame/30
        for i=1,5 do
            local angle=direction*45+i*72
            local drift=Vector((9+17*age)*sx,0):Rotated(angle)
            local point=origin+Vector(drift.X,drift.Y*.48-(6+17*age)*sy)
            drawSprite(tauntParticle,'TauntFeather',point,angle+22*age,.44*sx,.44*sy,Color(1,1,1,.82*(1-age)))
        end
    end
    if frame>=15 and frame<24 then
        local yaw=direction*math.pi/4
        local orientation={cos=math.cos(yaw),sin=math.sin(yaw)}
        -- VFX_buffbone01 and its forward axis sampled at the authored frame 15.
        local socket=rigOffset(16.8672,133.8197,21.9726,orientation,scale,pixelScale)
        local forward=rigOffset(.271429,.296533,.915640,orientation,scale,pixelScale)
        if forward:Length()>.001 then
            local age=frame-15
            local point=origin+socket+forward:Normalized()*(age*5.1*sx)
            drawSprite(tauntParticle,'TauntArrow',point,forward:GetAngleDegrees()-90,
                .69*sx,.69*sy,Color(1,1,1,1-age/9))
        end
    end
    if frame>=70 and frame<100 then
        local age=(frame-70)/30
        local size=.68+.53*age
        drawSprite(tauntParticle,'TauntBlast',origin,0,size*sx,.63*size*sy,Color(1,1,1,.9*(1-age)))
    end
end

local function gunSockets(clip,frame,length,origin,heading,rig)
    local track=muzzleTracks[clip]
    if not rig or not track then return end
    local _,index=Sprites.sample(clip,frame,length)
    local pose=index and track[index+1]
    if not pose then return end
    local angle,scale=heading:GetAngleDegrees(),rig.scale
    if rig.companion then
        local x=(rig.mirrored and -heading.X or heading.X)/(scale.X~=0 and scale.X or 1)
        local y=heading.Y/(.766044*(scale.Y~=0 and scale.Y or 1))
        angle=math.deg(math.atan(y,x))
    elseif rig.mirrored then
        scale=Vector(-scale.X,scale.Y)
    end
    local yaw=(rig.companion and 90-angle or math.floor((90-angle)/45+.5)*45)*math.pi/180
    local orientation={cos=math.cos(yaw),sin=math.sin(yaw)}
    local sockets={}
    for i,gun in ipairs(pose) do
        local x,y,z,dx,dy,dz=table.unpack(gun)
        local offset=rigOffset(x,y,z,orientation,scale,rig.modelScale)
        local forward=rigOffset(dx,dy,dz,orientation,scale,rig.modelScale)
        sockets[i]={position=origin+offset,angle=forward:GetAngleDegrees()}
    end
    return sockets
end

local function recallAnchor(track, frame, origin, orientation, scale, pixelScale)
    local point = track.positions[frame-track.first+1]
    if not point then return end
    local position=origin+rigOffset(point[1],point[2],point[3],orientation,scale,pixelScale or .22)
    local forward=point[4] and rigOffset(point[4],point[5],point[6],orientation,scale,1)
    return position,forward
end

function Effects.prepareLifecycle()
    if lifecycleParticle == nil and Sprite then
        local candidate, loaded = Sprite('gfx/mf/lifecycle_effects.anm2', true)
        lifecycleParticle = loaded and candidate or false
    end
end

local deathBlasts = {{21,-127.23,1.54,98.45},{30,-69.64,1.54,22.97}}
local function drawDeath(pos,frame,orientation,scale,pixelScale)
    if frame<30 then
        local phase=frame/30
        local alpha=math.min(1,phase/.10,(1-phase)/.50)
        drawSprite(lifecycleParticle,'DeathRibbon',pos+Vector(0,-14-12*phase),0,
            .44+phase*.16,.56+phase*.20,Color(1,.43,.08,.69*alpha))
        for side=-1,1,2 do
            local drift=Vector(side*(9+17*phase),-8-26*phase)
            drawSprite(lifecycleParticle,'DeathEmbers',pos+drift,side*(12+40*phase),
                .40,.44,Color(1,.84,.46,.64*alpha))
        end
    end
    local bandFrame=frame-2
    if bandFrame>=0 and bandFrame<39 then
        local phase=bandFrame/39
        local alpha=math.min(1,(bandFrame+1)/4,(1-phase)/.55)
        drawSprite(lifecycleParticle,'DeathBand',pos+Vector(0,3),0,
            .47+.16*phase,.44+.12*phase,Color(1,.726,.278,.56*alpha))
    end
    for _,blast in ipairs(deathBlasts) do
        local age=frame-blast[1]
        if age>=0 and age<30 then
            local point=pos+rigOffset(blast[2],blast[3],blast[4],orientation,scale,pixelScale)
            local alpha=math.min(1,(30-age)/24)
            drawSprite(lifecycleParticle,'DeathGroundFlash',point,0,
                .57+age*.009,.42+age*.007,Color(1,.63,.28,.48*alpha))
        end
    end
end

local respawnCues = {10,28,44}
local function drawRespawn(pos,frame,orientation,scale,pixelScale)
    for _,cue in ipairs(respawnCues) do
        local age=frame-cue
        if age>=0 and age<5 then
            for _,gun in ipairs(lifecycleTracks.respawn[cue]) do
                local x,y,z,dx,dy,dz=table.unpack(gun)
                local point=pos+rigOffset(x,y,z,orientation,scale,pixelScale)
                local forward=rigOffset(dx,dy,dz,orientation,scale,pixelScale)
                local angle=forward:GetAngleDegrees()
                if age<3 then
                    drawSprite(lifecycleParticle,'RespawnMuzzle',point+forward*15,angle,.20,.18,
                        Color(1,.27,.10,.78*(1-age/3)))
                end
                drawSprite(lifecycleParticle,'RespawnFlash',point+forward*10,angle,.18,.18,
                    Color(1,.70,.21,.89*(1-age/5)))
            end
        end
    end
end

function Effects.renderLifecycle(clip,pos,frame,direction,scale,pixelScale)
    if not lifecycleParticle or frame<0 then return end
    local yaw=direction*math.pi/4
    local orientation={cos=math.cos(yaw),sin=math.sin(yaw)}
    if clip=='death' then drawDeath(pos,frame,orientation,scale,pixelScale)
    elseif clip=='respawn' then drawRespawn(pos,frame,orientation,scale,pixelScale) end
end

local recallCups = {
    {recallTracks.fmvp,'RecallTrophyFMVP'},
    {recallTracks.cup2023,'RecallTrophy2024'},
    {recallTracks.cup2024,'RecallTrophy2024'},
    {recallTracks.cup2025,'RecallTrophy2025'},
}
local recallGunshots = {
    recallTracks.shot35Left, recallTracks.shot35Right, recallTracks.shot68,
    recallTracks.shot105, recallTracks.shot110,
}

local function drawRecallBursts(origin,frame,orientation,scale,modelScale)
    if not recallBurstParticle then return end
    for _, track in ipairs(recallGunshots) do
        local elapsed = frame-track.first
        if elapsed>=0 and elapsed<15 then
            if elapsed<3 then
                local point,axis=recallAnchor(track,frame,origin,orientation,scale,modelScale)
                local size=.45+.065*elapsed
                drawSprite(recallBurstParticle,'RecallMuzzle',point,axis:GetAngleDegrees(),
                    size*scale.X,size*scale.Y,Color(1,1,1,1-elapsed/3))
            end
            local muzzle,axis=recallAnchor(track,track.first,origin,orientation,scale,modelScale)
            if axis:Length()>.001 then
                local forward=axis:Normalized()
                for i=-1,1 do
                    local direction=forward:Rotated(i*19)
                    local point=muzzle+direction*(elapsed*(1.8+.5*math.abs(i)))
                    drawSprite(recallBurstParticle,'RecallShotSpark',point,direction:GetAngleDegrees(),
                        .22,.22,Color(1,1,1,.62*(1-elapsed/15)))
                end
            end
        end
    end
    if frame>=105 and frame<111 then
        local age=(frame-105)/6
        local point=recallAnchor(recallTracks.balloon,frame,origin,orientation,scale)
        local size=.44+.16*age
        drawSprite(recallBurstParticle,'RecallBalloonHit',point,0,size*scale.X,size*scale.Y,Color(1,1,1,1-age))
    end
    if frame>=130 and frame<142 then
        local age=(frame-130)/12
        local point=recallAnchor(recallTracks.balloon,130,origin,orientation,scale)
        local size=.48+.42*age
        drawSprite(recallBurstParticle,'RecallBalloonSplash',point,0,
            size*scale.X,size*scale.Y,Color(1,1,1,1-age))
        for i=1,5 do
            local angle=i*72
            local drift=Vector((7+22*age)*scale.X,0):Rotated(angle)
            drawSprite(recallBurstParticle,'RecallBalloonDroplet',point+drift+Vector(0,6*age*age),angle,
                .34*scale.X,.34*scale.Y,Color(1,1,1,.92*(1-age)))
        end
    end
end

function Effects.renderRecallStage(pos, frame, duration, direction, scale, nativeBodyScale, modelScale)
    local fade = math.min(1,(frame+1)/8,(duration-frame)/16)
    local yaw = direction*math.pi/4
    local orientation = {cos=math.cos(yaw),sin=math.sin(yaw)}
    local road = recallAnchor(recallTracks.road,frame,pos,orientation,scale)
    if road then
        local axis=Vector(orientation.cos*scale.X,-orientation.sin*.766044*scale.Y)
        drawRecallEffect('RecallRoad',road,.38*axis:Length(),.57,
            Color(1,1,1,.68*math.min(fade,(240-frame)/14)),axis:GetAngleDegrees())
    end
    drawRecallEffect('RecallFloor',pos+Vector(0,6),1.7,1.2,Color(1,1,1,.92*fade))
    if frame < 150 then
        local runeFade = math.min(fade,(150-frame)/18)
        drawRecallEffect('RecallRune',pos+Vector(0,5),.49,.34,Color(1,.78,.48,.53*runeFade))
    end
    local spear = recallAnchor(recallTracks.spear,frame,pos,orientation,scale)
    if spear then
        local opacity=math.min(1,(frame-8)/3,(39-frame)/4)
        for i=-1,1 do
            drawRecallProp('RecallSpear',spear+Vector(4*orientation.cos,-5*i),-i*7,
                .48,.9,Color(1,1,1,opacity))
        end
    end
    local arrow = recallAnchor(recallTracks.arrow,frame,pos,orientation,scale)
    if arrow then
        local opacity=math.min(1,(frame-56)/4,(77-frame)/6)
        drawRecallProp('RecallArrow',arrow,-90,.42,.42,Color(1,1,1,opacity))
    end
    local balloon = recallAnchor(recallTracks.balloon,frame,pos,orientation,scale)
    local balloonEnd=recallBurstParticle and 130 or 138
    if balloon and frame<balloonEnd then
        local age = frame-103
        local opacity=math.min(1,(age+1)/5,(balloonEnd-frame)/7)
        local stretch=1+.3*math.sin(age*math.pi/35)
        drawRecallProp('RecallWaterTrail',balloon+Vector(-7,5),0,.32,.20,Color(.82,.93,1,.72*opacity))
        drawRecallProp('RecallBalloon',balloon,0,.26,.26*stretch,Color(1,1,1,opacity))
    end
    for _, cup in ipairs(recallCups) do
        local track, art = table.unpack(cup)
        local anchor = recallAnchor(track,frame,pos,orientation,scale)
        if anchor then
            local opacity = math.min(fade,(frame-track.first+1)/7)
            drawRecallEffect(art,anchor,.38*scale.X,.38*scale.Y,Color(1,1,1,opacity))
        end
    end
    if frame>=136 then
        if recallPetParticle == nil and Sprite then
            local candidate, loaded = Sprite('gfx/mf/recall_pet.anm2', true)
            recallPetParticle = loaded and candidate or false
        end
        drawSprite(recallPetParticle,'RecallDog'..direction,pos,0,
            nativeBodyScale*scale.X,nativeBodyScale*scale.Y,Color(1,1,1,fade),math.min(124,frame-136))
    end
    drawRecallBursts(pos,frame,orientation,scale,modelScale)
end

function Effects.renderRecallFinale(pos, frame, duration)
    local age = frame-130
    if age < 0 then return end
    local fade = math.min(1,(age+1)/10,(duration-frame)/16)
    local lift = math.min(age,12)*.65
    drawRecallEffect('RecallFlourish',pos-Vector(0,45+lift),.74,.75,Color(1,.62,.29,.68*fade))
    drawRecallEffect('RecallLogo',pos-Vector(0,64+lift),.34,.34,Color(1,.84,.56,fade))
end

local function gold(alpha)
    return Color(1, .82, .5, alpha, .14, .065, .015)
end

local function light(alpha)
    return Color(1, .94, .72, alpha, .15, .08, .02)
end

local function shell(pos, angle, size, alpha)
    return draw("Bullet", pos, angle, size, size, Color(1, 1, 1, alpha))
end

local function doubleUpShell(pos, angle, size, alpha, dud)
    if not dud then drawShotSprite('QGlow',pos,angle,size*.91,size*.83,alpha*.58) end
    return drawShotSprite(dud and 'QDud' or 'QBullet',pos,angle,size,size,alpha)
        or shell(pos,angle,size,alpha)
end

local function trail(pos, angle, length, width, alpha)
    draw("Trail", pos, angle, length / 53, width, gold(alpha))
end

local function muzzle(pos, angle, size, alpha)
    draw("Muzzle", pos, angle + 90, size, size, gold(alpha))
end

local passiveMark

function Effects.renderLoveTap(position, alpha)
    local opacity = math.max(0, math.min(1, alpha or 1))
    if opacity == 0 then return end
    if passiveMark == nil and Sprite then
        local candidate, loaded = Sprite("gfx/mf/passive.anm2", true)
        passiveMark = loaded and candidate or false
    end
    if passiveMark then
        passiveMark:SetFrame("Mark", 0)
        passiveMark.Scale = Vector(.26, .19)
        passiveMark.Color = Color(1, .74, .35, opacity)
        passiveMark:Render(position + Vector(0, 6))
        return
    end

    if not Isaac.DrawLine or not KColor then return end

    local shade = KColor(.18, .07, .22, .85 * opacity)
    local glow = KColor(1, .74, .35, opacity)
    for _, side in ipairs({-1, 1}) do
        local outer = position + Vector(side * 15, 2)
        local bend = position + Vector(side * 11, 6)
        local inner = position + Vector(side * 6, 6)
        Isaac.DrawLine(outer, bend, shade, shade, 3.5)
        Isaac.DrawLine(bend, inner, shade, shade, 3.5)
        Isaac.DrawLine(outer, bend, glow, glow, 1.5)
        Isaac.DrawLine(bend, inner, glow, glow, 1.5)
    end
end

function Effects.fireMuzzle(state,clip,origin,heading,clock,length)
    state.muzzle = {
        clip=clip, origin=origin, heading=heading, length=length,
        startFrame=clock, untilFrame=clock+math.min(4,length),
    }
end

function Effects.renderTear(tear, offset, kind)
    if not sprite() then return false end
    local project = Isaac.WorldToRenderPosition
    -- Keep the launch at its original height, then lower the rendered arc.
    -- The engine still owns the tear height, flight time and collisions.
    local flight = math.min(1, (tear.FrameCount or 0) / 3)
    local height = (tear.Height or 0) * (1 - (1 - bulletHeightScale) * flight)
    local pos = project(tear.Position + Vector(0, height))
    if offset then pos = pos + offset end
    if tear.PositionOffset then pos = pos + tear.PositionOffset end
    if tear.SpriteOffset then pos = pos + tear.SpriteOffset end
    local face = project(tear.Position + tear.Velocity) - project(tear.Position)
    local angle = face:GetAngleDegrees()
    local size = math.min(2, math.max(.65, tear.Scale or 1))
    if kind == 'aa' then
        local tailPos = pos - Vector(7 * size, 0):Rotated(angle)
        if not drawShotSprite('AATrail',tailPos,angle,11*size/64,.28*size,.71) then
            trail(tailPos,angle,11*size,.28*size,.64)
        end
        return shell(pos,angle,.43*size,1)
    end
    trail(pos - Vector(9 * size, 0):Rotated(angle), angle, 15 * size, .33 * size, .68)
    return doubleUpShell(pos,angle,.53*size,1)
end

local function drawMuzzle(cue,frame,project,playerPosition,rig)
    local origin=project(playerPosition or cue.origin)
    local age=frame-cue.startFrame
    local alpha=(cue.untilFrame-frame)/(cue.untilFrame-cue.startFrame)
    local poseFrame,poseLength=Sprites.discharge(cue.clip,age,cue.length)
    local sockets=gunSockets(cue.clip,poseFrame,poseLength,origin,cue.heading,rig)
    if not sockets or #sockets==0 then
        local angle=(project(cue.origin+cue.heading*30)-project(cue.origin)):GetAngleDegrees()
        sockets={{position=origin+Vector(8,0):Rotated(angle)+Vector(0,-8),angle=angle}}
    end
    local image,size='AACast',.40
    if cue.clip=='q' then image,size='QCast',.53
    elseif cue.clip=='crit' then image,size='AACritCast',.43 end
    for _,socket in ipairs(sockets) do
        if not drawShotSprite(image,socket.position,socket.angle,size,size,alpha) and cue.clip=='q' then
            muzzle(socket.position,socket.angle,.52,alpha)
        end
        if cue.clip=='crit' then
            drawShotSprite('AACritSpark',socket.position,socket.angle,.28,.28,.68*alpha)
        end
    end
end

local function drawShot(cue, frame, project)
    local from = project(cue.from) + Vector(0, -8)
    local dud = cue.kind == 'qDud'
    local to = project(cue.to) + Vector(0, dud and 0 or -8)
    local delta = to - from
    local angle = delta:GetAngleDegrees()
    local elapsed = frame - (cue.startFrame or cue.untilFrame - bounceFrames)
    local duration = cue.travel or 4
    if elapsed < duration then
        local hit = from + delta * math.min(1, (elapsed + 1) / duration)
        local length = math.min(19, (hit - from):Length())
        local behind = hit - Vector(length, 0):Rotated(angle)
        if length > 0 then trail((hit + behind) / 2, angle, length, .37, .73) end
        doubleUpShell(hit,angle,dud and .39 or .53,1,dud)
    else
        local alpha = math.min(1, (cue.untilFrame - frame) / 4)
        if dud then doubleUpShell(to,angle,.36,alpha,true)
        elseif cue.hit and not drawShotSprite('QSecondImpact',to,angle,.41,.41,alpha) then
            draw("Impact",to,angle+90,.56,.56,gold(alpha))
        end
    end
end

local function drawQImpact(cue,frame,project)
    local point = project(cue.point)
    local alpha = math.min(1,(cue.untilFrame-frame)/5)
    draw('Impact',point,0,.71,.41,Color(1,1,1,.7*alpha))
    drawShotSprite('QImpact',point+Vector(0,-8),0,.46,.46,alpha)
end

local rainTrophies = {'RecallTrophy2024','RecallTrophy2025','RecallTrophyFMVP'}
local function drawRain(rain, frame, project)
    local age = frame - rain.startFrame
    if age<0 then return end
    local center = project(rain.center)
    local rx = math.abs((project(rain.center + Vector(rain.radius, 0)) - center).X)
    local ry = math.abs((project(rain.center + Vector(0, rain.radius)) - center).Y)
    local fade = math.min(1, (age + 2) / 5, (rain.untilFrame - frame) / 7)
    drawShotSprite('RainGround',center,0,rx/64,ry/64,.8*fade)
    drawShotSprite('RainGold',center,0,rx/64,ry/64,.54*fade)
    drawShotSprite('RainRingGlow',center,0,rx*1.12/64,ry/64,.59*fade)
    draw("Ring", center, 0, rx / 85, ry / 85, Color(1, 1, 1, .92 * fade))

    local phase = age/(rain.untilFrame-rain.startFrame)
    local trophyFade = math.min(1,phase/.10,(1-phase)/.20)
    if trophyFade>0 then
        local trophy = rainTrophies[math.floor(rain.startFrame/30)%#rainTrophies+1]
        local descent = math.max(0,1-phase/.10)
        drawRecallEffect(trophy,center-Vector(0,68*descent*descent),.46,.46,Color(1,1,1,.6*trophyFade))
    end

    local flightFrames, flashFrames, glowFrames = 8, 4, 8
    for pulse, expected in ipairs(rain.impactFrames) do
        local landed = rain.landedAt[pulse]
        local elapsed = frame - (landed or expected)
        local falling = not landed and elapsed >= -flightFrames and elapsed <= 0
        local flashing = landed and elapsed >= 0 and elapsed < glowFrames
        if falling or flashing then
            for i = 1, 6 do
                local seed = (pulse - 1) * 6 + i
                local angle = seed * 137.507764
                local distance = rain.radius * .89 * math.sqrt(((seed * 37) % 101 + .5) / 101)
                local ground = project(rain.center + Vector(distance, 0):Rotated(angle))
                if falling then
                    local altitude = (105 + i * 4) * (-elapsed / flightFrames)
                    local wind = i % 3 - 1
                    local pos = ground + Vector(wind * altitude * .19, -altitude)
                    local fall = Vector(-wind * .19, 1):GetAngleDegrees()
                    local tail = pos - Vector(10, 0):Rotated(fall)
                    if not drawShotSprite('RainStreak',tail,fall,.37,.32,.88*fade) then
                        draw("Rain",tail,fall,.62,.50,light(fade))
                    end
                    if not drawShotSprite('RainCore',pos,fall,.38,.38,fade) then shell(pos,fall,.41,fade) end
                else
                    local point = ground + Vector(0,-4)
                    drawShotSprite('RainImpactGlow',point,0,.47,.32,fade*(1-elapsed/glowFrames))
                    if elapsed<flashFrames then
                        local alpha = fade*(1-elapsed/flashFrames)
                        if not drawShotSprite('RainImpact',point,0,.42,.42,alpha) then
                            draw("Impact",point,0,.48,.48,gold(alpha))
                        end
                    end
                end
            end
        end
    end
end

local function drawUltimateCone(r, frame, project, anchor)
    local origin = project(anchor)
    local axis = project(anchor+r.facing*r.range)-origin
    local span = axis:Length()
    if span <= .001 then return end
    local side = project(anchor+r.facing:Rotated(90)*r.range)-origin
    local normalLength = math.abs(side.X*axis.Y-side.Y*axis.X)/span
    local halfWidth = normalLength*math.sin(math.rad(r.halfAngle))
    local fade = math.min(1,(r.untilFrame-frame)/7)
    local opacity = r.waves and .23 or .49
    drawUltimateEffect('RCone',origin,axis:GetAngleDegrees(),span/894,halfWidth/256,Color(1,1,1,opacity*fade))
end

local function drawUltimateImpact(cue, frame, project)
    local alpha = (cue.untilFrame-frame)/(cue.untilFrame-cue.startFrame)
    local size = .19+.12*(1-alpha)
    drawUltimateEffect('RImpact',project(cue.point)+Vector(0,-8),0,size,size,Color(1,1,1,.74*alpha))
end

local function drawUltimate(wave,frame,project,frameFraction,playerPosition,rig,muzzlesActive)
    local r = wave.channel
    local age = frame - wave.launchedAt
    local phase = age + frameFraction
    local origin=project(wave.origin)
    local from=origin+Vector(0,-10)
    local gun=(wave.number-1)%2+1
    local launchFrame=Sprites.barrageFrame(wave.number,0,r.interval)
    local launchSockets=gunSockets('r',launchFrame,nil,origin,wave.facing,rig)
    local launchSocket=launchSockets and launchSockets[gun]
    local barrel=launchSocket and launchSocket.position-from or Vector.Zero
    if muzzlesActive and phase<2 then
        local playerOrigin=project(playerPosition or wave.origin)
        local poseFrame=Sprites.barrageFrame(wave.number,age,r.interval)
        local sockets=gunSockets('r',poseFrame,nil,playerOrigin,wave.facing,rig)
        local socket=sockets and sockets[gun]
        if not socket then
            local point=project((playerPosition or wave.origin)+wave.facing:Rotated(gun==1 and -14 or 14)*19)
            socket={position=point+Vector(0,-10),angle=(point-playerOrigin):GetAngleDegrees()}
        end
        local alpha=.88*(1-phase/2)
        if not drawUltimateEffect('RMuzzle',socket.position,socket.angle,.20,.18,Color(1,1,1,alpha)) then
            muzzle(socket.position,socket.angle,.62,alpha)
        end
    end
    local progress = math.min(1,wave.front/r.range+frameFraction/r.travel)
    local back = math.max(0, progress - .13)
    local alpha = math.min(1, math.max(0, r.travel + 1 - phase))
    for _, offset in ipairs(r.rays) do
        local ray = wave.facing:Rotated(offset)
        local endPos = project(wave.origin + ray * r.range) + Vector(0, -10)
        local span = endPos - from
        -- The tracer meets its unchanged gameplay lane after leaving the barrel.
        local tip=from+span*progress+barrel*math.max(0,1-progress/.33)
        local rear=from+span*back+barrel*math.max(0,1-back/.33)
        local angle = span:GetAngleDegrees()
        local middle, length = (tip+rear)/2, math.max(7,(tip-rear):Length())
        if not drawUltimateEffect('RTrail',middle,angle,length/128,.095,Color(1,.79,.52,.75*alpha)) then
            trail(middle,angle,length,.52,.75*alpha)
        end
        if not drawShotSprite('RCore',tip,angle,.46,.38,alpha)
            and not drawUltimateEffect('RBullet',tip,angle,.46,.38,Color(1,.96,.85,alpha)) then
            shell(tip,angle,.46,alpha)
        end
    end
end

local function drawStrutSprite(name, position, angle, sx, sy, color)
    if strutParticle == nil and Sprite then
        local candidate, loaded = Sprite('gfx/mf/strut_effects.anm2', true)
        strutParticle = loaded and candidate or false
    end
    drawSprite(strutParticle,name,position,angle,sx,sy,color)
end

function Effects.renderStrut(player, frame, project, strut)
    local origin=project(player.Position)
    local velocity = player.Velocity
    if strut.maxStrut and velocity:Length()>.6 then
        local back=project(player.Position-velocity*4)
        local axis=origin-back
        local angle=axis:GetAngleDegrees()
        drawStrutSprite('GroundWisp',(origin+back)/2,angle,math.max(.14,axis:Length()/100),.13,
            Color(.95,.69,.22,.58+.12*math.sin(frame*.4)))
        for side=-1,1,2 do
            local age=((frame+side*6)%24)/24
            local scatter=Vector(0,side*(5+9*age)):Rotated(angle)
            local point=origin-axis*(.2+age)+scatter+Vector(0,-7*age)
            drawStrutSprite('Feather',point,angle+side*(35+65*age),.23,.23,Color(.92,.72,.40,.6*(1-age)))
        end
    end
    local age=strut.chargedAt and frame-strut.chargedAt
    if strut.maxStrut and age and age>=0 and age<24 then
        local alpha=.6*math.min(1,(age+1)/5,(24-age)/19)
        drawStrutSprite('Activation',origin+Vector(0,-18),0,.70,.70,Color(.864,.126,.184,alpha))
    end
    if strut.active<=0 or not strut.pose then return end
    local points=strutTracks[strut.pose] and strutTracks[strut.pose][strut.index+1]
    if not points then return end
    local scale=player.SpriteScale or Vector(1,1)
    local yaw=math.floor((90-strut.face:GetAngleDegrees())/45+.5)*math.pi/4
    local cs,sn=math.cos(yaw),math.sin(yaw)
    local mirror=strut.mirrored and -1 or 1
    local axis=project(player.Position+strut.face)-origin
    local angle=axis:GetAngleDegrees()
    local fade=math.min(1,strut.active*12)
    for index=1,4,3 do
        local x,y,z=points[index],points[index+1],points[index+2]
        local anchor=origin+Vector((x*cs+z*sn)*strut.modelScale*scale.X*mirror,
            ((z*cs-x*sn)*.766044-y*.642788)*strut.modelScale*scale.Y)
        local pulse=.70+.30*math.sin(frame*.55+index)
        drawStrutSprite('GunTrail',anchor,angle,.18,.13,Color(.94,.65,.26,.60*pulse*fade))
        drawStrutSprite('GunSpark',anchor,-angle,.28,.28,Color(.72,.10,.03,.50*fade))
    end
end

function Effects.render(combat, frame, project, playerPosition, waveFraction, rig)
    local rain, wave = combat.rain, combat.barrageWave
    local barrage = combat.r
    if barrage and frame < barrage.untilFrame then
        drawUltimateCone(barrage,frame,project,playerPosition or barrage.origin)
    end
    if rain and frame < rain.untilFrame then drawRain(rain, frame, project) end
    local companionMuzzle = rig and rig.companionMuzzle
    local discharge = combat.muzzle
    if not companionMuzzle and discharge and frame >= discharge.startFrame and frame < discharge.untilFrame then
        drawMuzzle(discharge,frame,project,playerPosition,rig)
    end
    for _, cue in ipairs(combat.fx) do
        if frame < cue.untilFrame then
            if cue.kind == 'rImpact' then drawUltimateImpact(cue,frame,project)
            elseif cue.kind == 'qImpact' then drawQImpact(cue,frame,project)
            elseif cue.kind == 'bounce' or cue.kind == 'qDud' then drawShot(cue,frame,project) end
        end
    end
    if wave and frame - wave.launchedAt <= wave.channel.travel then
        drawUltimate(wave,frame,project,waveFraction or 0,playerPosition,rig,barrage==wave.channel and not companionMuzzle)
    end
end

return Effects
