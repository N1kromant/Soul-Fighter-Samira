local MF = {}
local Combat = include('miss_fortune_combat')
local Navigation = include('samira_navigation')
local Effects = include('miss_fortune_effects')
local Emotes = include('yone_emotes')
local Runes = include('miss_fortune_runes')
local HUD = include('yone_hud')
local CombatHUD = include('miss_fortune_hud')
local Sprites = include('miss_fortune_sprite')
local Special = include('miss_fortune_special_animations')
local json = require('json')
local playerType, state, game, items, weapons, display, readScale, readUltimate, fallbackSprite, badge
local isCrafting, isOtherChampion, testMode, inventoryBounds
local modelScale = .26
local bodyScale = modelScale / .42
-- The action baker renders at .9 model scale and downsamples by 4.15.
local nativeActionScale = modelScale / (.9 / 4.15)
local displaySettleMillis = 125
local keys = {q=Keyboard.KEY_Q, w=Keyboard.KEY_W, e=Keyboard.KEY_E}
local expressionKeys = {Keyboard.KEY_1, Keyboard.KEY_2, Keyboard.KEY_3, Keyboard.KEY_4, Keyboard.KEY_5, Keyboard.KEY_6}
local ordinaryTaunt = {action='taunt',toggle=true}
local spamDuration = Sprites.duration('taunt_spam')
local primaryTaunt = spamDuration and {action='taunt_spam',toggle=true} or ordinaryTaunt
local recallDuration = Sprites.duration('recall_cinematic')
local respawnDuration = Sprites.duration('respawn') or 42
local jokeIntroDuration = Sprites.duration('joke_in')
local jokeBodyDuration = Sprites.duration('joke')
local idleIntroDuration = Sprites.duration('idle_in')
local strutIntroDuration = Sprites.duration('w')
local strutRunDuration = Sprites.duration('strut_run_loop')
local baseIdleDuration, alternateIdleDuration = Sprites.duration('base_idle'), Sprites.duration('idle')
local emoteSounds = {joke=jokeIntroDuration and 'Joke Cast' or 'Joke', taunt='Taunt', taunt_spam='Taunt', dance='Dance', laugh='Laugh',
    recall_cinematic='Recall'}
local expressions = {
    {action='joke',toggle=true}, primaryTaunt, {action='dance',toggle=true},
    {action='laugh',duration=113},
    recallDuration and {action='recall_cinematic',duration=recallDuration + 1,toggle=true}
        or {action='recall',duration=240,toggle=true},
}
local animationPreviews = {}
for clip in ('idle idle_in run run_in attack attack2 attack_out attack2_out attack_run attack_strut attack2_run attack2_strut '
    ..'crit crit_out q_in q q_out q_run w e e_out e_run '
    ..'r_in r r_out r_run joke_in joke joke_loop taunt taunt_loop dance laugh recall recall_loop recall_out '
    ..'homeguard_in homeguard homeguard_out homeguard_out_run pentakill pentakill_bonus death respawn base_idle strut_run_loop dance_loop '
    ..'recall_cinematic taunt_spam'):gmatch('%S+') do
    animationPreviews[clip]=true
end
local axes = {[ButtonAction.ACTION_LEFT]=Vector(-1,0), [ButtonAction.ACTION_RIGHT]=Vector(1,0),
    [ButtonAction.ACTION_UP]=Vector(0,-1), [ButtonAction.ACTION_DOWN]=Vector(0,1)}
local shootActions = {
    [ButtonAction.ACTION_SHOOTLEFT]=true, [ButtonAction.ACTION_SHOOTRIGHT]=true,
    [ButtonAction.ACTION_SHOOTUP]=true, [ButtonAction.ACTION_SHOOTDOWN]=true,
}
local function pressed(k) return Input.IsButtonPressed(k,0) end
local function sampleButton(key)
    local down = pressed(key)
    local triggered = down and not state.held[key]
    state.held[key] = down
    return down, triggered
end
function MF.isNative(p)
    if not p or not p.GetPlayerType then return false end
    if not playerType then local id = Isaac.GetPlayerTypeByName('Miss Fortune',false); if id >= 0 then playerType=id end end
    return playerType ~= nil and p:GetPlayerType()==playerType
end
function MF.is(p)
    if testMode and p and p.GetPlayerType and Isaac.IsInGame() then
        local first = Isaac.GetPlayer(0)
        if first and p.Index == first.Index then return true end
    end
    return MF.isNative(p)
end
function MF.player(g)
    if Isaac.IsInGame() and g:GetNumPlayers()==1 then local p=Isaac.GetPlayer(0); if MF.is(p) then return p end end
end
local function owner() return game and MF.player(game) end
local function deathAnimating(p)
    local sprite=p.GetSprite and p:GetSprite()
    return sprite and sprite.IsPlaying and sprite:IsPlaying('Death')
end
local function combatSuspended()
    return game:IsPaused() or state.leaving
        or (RoomTransition and (RoomTransition.GetTransitionMode()~=0 or RoomTransition.IsRenderingBossIntro()))
end
local function hidden(p,death)
    return combatSuspended() or not death and (p:IsDead() or p.ControlsEnabled==false)
        or (ImGui and ImGui.IsVisible())
end
local function runes()
    return items and items.missFortuneRunes and items.missFortuneRunes()
end
local function picking()
    local progress = runes()
    return progress and not progress.rune
end
function MF.canUseItems(p)
    return state ~= nil and MF.is(p) and not hidden(p) and not picking()
end
function MF.speed(p,clock) return state and MF.is(p) and Combat.speed(state.combat,clock) or 1 end
function MF.attackSpeed(p,clock)
    if not state or not MF.is(p) then return 1 end
    local runeSpeed = items and items.missFortuneRuneAttackSpeed and items.missFortuneRuneAttackSpeed(clock) or 1
    return Combat.attackSpeed(state.combat,clock) * runeSpeed
end
function MF.recordTakedown(p, clock)
    if state and MF.is(p) and not state.leaving and not p:IsDead() then Special.takedown(state.special,clock) end
end
local function stopMoving()
    state.goal,state.target,state.path,state.door,state.intent,state.drag=nil,nil,nil,nil,nil,nil
end
local function refresh(p)
    if p and p.AddCacheFlags and p.EvaluateItems then
        p:AddCacheFlags(CacheFlag.CACHE_SPEED | CacheFlag.CACHE_FIREDELAY); p:EvaluateItems()
    end
end
local function animation(clip,clock,duration,facing)
    state.action={clip=clip,start=clock,finish=clock+duration,facing=facing}
    state.combat.muzzle=nil
end
local function displayedFacing(clock)
    local action=state.action
    if not state.qWindupAt and action and action.facing and clock<action.finish then return action.facing end
    return state.face
end
function MF.weaponFired(kind,heading,ctx,clock)
    if not state then return end
    Emotes.cancel(state.emotes,false)
    if heading and heading:Length()>.001 then state.face=heading:Normalized() end
    if kind=='q' then
        state.qWindupAt=nil
        animation('q',clock,18,state.face)
        Effects.playBulletSound('q')
        Effects.playSound('Q Voice',.57)
        if ctx.origin then Effects.fireMuzzle(state.combat,'q',ctx.origin,state.face,clock,18) end
    else
        Effects.playSound('Attack',.34)
        state.shot=(state.shot or 0)+1
        local clip=state.shot%2==0 and 'attack2' or 'attack'
        if ctx.crit and Sprites.duration('crit') then clip='crit' end
        local tearVolley=WeaponType and ctx.weaponType==WeaponType.WEAPON_TEARS and not ctx.persistentPulse
        local player=tearVolley and owner()
        local duration=player and math.max(2,math.min(12,math.ceil(player.MaxFireDelay+1))) or 12
        animation(clip,clock,duration,state.face)
        if ctx.origin and tearVolley then
            Effects.fireMuzzle(state.combat,clip,ctx.origin,state.face,clock,duration)
        end
    end
end
function MF.acceptHit(ctx,clock,target,amount,baseDamage,shot)
    local p=owner()
    if not state or not p or not ctx then return end
    if not (shot and shot.split) and ctx.kind=='q' and target and amount and amount>0 then
        local cue=ctx.corsairSecondary and 'mfBounceSound' or 'mfHitSound'
        if not ctx[cue] then
            ctx[cue]=true
            Effects.playSound('Q Hit',.56)
        end
    end
    Combat.acceptHit(state.combat,ctx,clock,target,amount,p,game:GetRoom(),items,baseDamage,shot)
end
function MF.damageMultiplier(ctx,target,clock,split)
    return state and Combat.damageMultiplier(state.combat,ctx,target,clock,split) or 1
end
function MF.exportCooldowns(clock)
    local result={}
    if state then for _,k in ipairs({'q','w','e','r'}) do result[k]=math.max(0,(state.combat.ready[k] or 0)-clock) end end
    return result
end
function MF.restoreCooldowns(saved,clock)
    if state and type(saved)=='table' then
        for _,k in ipairs({'q','w','e','r'}) do local n=saved[k]; if type(n)=='number' and n>=0 then state.combat.ready[k]=clock+math.min(n,900) end end
    end
end
function MF.reduceCooldowns(fraction,clock)
    if not state then return end
    for _,k in ipairs({'q','w','e','r'}) do local n=math.max(0,(state.combat.ready[k] or clock)-clock); state.combat.ready[k]=clock+math.ceil(n*(1-math.max(0,math.min(1,fraction)))) end
end
function MF.reduceUltimateCooldown(fraction,clock)
    if not state then return end
    local remain=math.max(0,(state.combat.ready.r or clock)-clock)
    local total=state.rDuration or remain
    state.combat.ready.r=clock+math.max(0,remain-math.floor(total*math.max(0,math.min(1,fraction))+.5))
end
local function stopCombatAudio()
    Effects.stopSound(state.barrageSound)
    Effects.stopSound(state.rainSound)
    state.barrageSound, state.rainSound = nil, nil
end
local function stopLifecycleSound()
    Effects.stopSound(state.lifecycleSound)
    Effects.stopSound(state.lifecycleVoice)
    state.lifecycleSound,state.lifecycleVoice,state.lifecycleClip,state.lifecycleUntil=nil,nil,nil,nil
end
local function startLifecycleSound(clip)
    stopLifecycleSound()
    Effects.prepareLifecycle()
    local cue=clip=='death' and 'Death' or 'Respawn'
    state.lifecycleSound=Effects.playSound(cue,.58)
    state.lifecycleVoice=Effects.playSound(cue..' Voice',.62)
    state.lifecycleClip=clip
    local action=state.action
    state.lifecycleUntil=action and action.clip==clip and action.finish
end
function MF.reset(keepCooldowns)
    if not state then return end
    stopCombatAudio()
    stopLifecycleSound()
    Special.reset(state.special)
    Combat.resetRoom(state.combat)
    if not keepCooldowns then state.combat=Combat.new(game:GetFrameCount()) end
    state.action,state.deathRoom=nil,nil
    stopMoving()
end
function MF.hudBounds(scale,backpack)
    return CombatHUD.bounds(scale,backpack)
end
local function sampleRunePicker(allowed)
    local held = state.held
    local left,right = pressed(Keyboard.KEY_LEFT),pressed(Keyboard.KEY_RIGHT)
    local confirm,mouse = pressed(Keyboard.KEY_ENTER),Input.IsMouseBtnPressed(0)
    if allowed then
        local hit = mouse and not held.click and HUD.runePickerHit(Runes.choices,readScale and readScale() or 1)
        local delta = (right and not held.nextRune and 1 or 0) - (left and not held.prevRune and 1 or 0)
        state.runeSelection = type(hit) == 'number' and hit
            or (state.runeSelection - 1 + delta) % #Runes.choices + 1
        if hit == 'confirm' or confirm and not held.confirm then
            items.chooseMissFortuneRune(Runes.choices[state.runeSelection].id)
        end
    end
    held.prevRune,held.nextRune,held.confirm,held.click=left,right,confirm,mouse
end
local function stopExpressionSound()
    Effects.stopSound(state.expressionSound)
    Effects.stopSound(state.tauntIntroSound)
    Effects.stopSound(state.jokeBodySound)
    Effects.stopSound(state.jokeLoopSound)
    state.expressionSound, state.expressionCue, state.expressionSoundAt = nil, nil, nil
    state.tauntIntroSound=nil
    state.jokeAudioPhase, state.jokeBodySound, state.jokeLoopSound = nil, nil, nil
end
local function sampleExpressions(clock,allowed,interrupted)
    local keys = {ctrl=pressed(Keyboard.KEY_LEFT_CONTROL) or pressed(Keyboard.KEY_RIGHT_CONTROL),
        disabled=not allowed}
    for index,key in ipairs(expressionKeys) do keys[index]=pressed(key) end
    local shift=pressed(Keyboard.KEY_LEFT_SHIFT) or pressed(Keyboard.KEY_RIGHT_SHIFT)
    state.emotes.expressions[2]=shift and ordinaryTaunt or primaryTaunt
    local before = state.emotes.masteryAt
    Emotes.update(state.emotes,clock,keys,interrupted)
    if state.emotes.masteryAt == clock and state.emotes.masteryAt ~= before then
        local sound = Isaac.GetSoundIdByName and Isaac.GetSoundIdByName('Yone Mastery')
        if sound and sound > 0 then SFXManager():Play(sound,.8,0,false,1) end
    end
    local action,frame=Emotes.action(state.emotes,clock)
    if action~=state.expressionCue or allowed and frame==0 then
        local recallEnded=allowed and not interrupted and not action and state.expressionCue=='recall_cinematic'
            and clock-state.expressionSoundAt>=recallDuration+1
        if recallEnded then
            -- The recorded end flourish continues briefly after the last pose.
            state.expressionCue, state.expressionSoundAt=nil,nil
        else
            stopExpressionSound()
        end
        if allowed and frame==0 and emoteSounds[action] then
            if action=='joke' then Effects.prepareJoke() end
            if action=='dance' then Effects.prepareDance() end
            if action=='taunt_spam' then Effects.prepareTaunt() end
            if action=='recall_cinematic' then Effects.prepareRecallBursts() end
            state.expressionCue=action
            state.expressionSoundAt=clock
            state.expressionSound=Effects.playSound(emoteSounds[action],.55)
            if action=='taunt' then state.tauntIntroSound=Effects.playSound('Taunt Intro',.53) end
        end
    end
    if allowed and action=='joke' and jokeIntroDuration and jokeBodyDuration then
        if frame>=jokeIntroDuration and not state.jokeAudioPhase then
            state.jokeBodySound=Effects.playSound('Joke',.55)
            state.jokeAudioPhase='body'
        end
        if frame>=jokeIntroDuration+jokeBodyDuration and state.jokeAudioPhase=='body' then
            state.jokeLoopSound=Effects.playSound('Joke Loop',.42,true)
            state.jokeAudioPhase='loop'
        end
    end
end
local function packet(data) Isaac.DebugString('[SAMIRA_EXTERNAL] '..json.encode(data)) end
local function stop()
    if not state then return end
    stopExpressionSound()
    stopCombatAudio()
    stopLifecycleSound()
    Special.reset(state.special)
    packet({version=1,active=false,hero='mf',session=state.id,room=state.room})
    if weapons and weapons.reset then weapons.reset() end
    if display then display.release('mf') end
    state=nil
end
local serial=0
local function start(p,continued)
    serial=serial+1
    local clock=game:GetFrameCount()
    if fallbackSprite == nil then
        local sprite, loaded = Sprite('gfx/mf/fallback.anm2', true)
        fallbackSprite = loaded and sprite or false
    end
    Effects.prepareShots()
    state={id=tostring(Isaac.GetNanoTime())..':mf:'..serial,room=1,seq=0,combat=Combat.new(clock),
        face=Vector(1,0),held={click=true,confirm=true},continuing=continued==true,
        runeSelection=1,emotes=Emotes.new({table.unpack(expressions)}),
        special=Special.new(not continued and MF.isNative(p))}
    if not continued then Combat.grantStrut(state.combat,clock) end
    display.acquire('mf')
    if items and items.activate then items.activate(p) end
    if items and items.startMissFortuneRunes then items.startMissFortuneRunes(continued) end
    if continued and items and items.restoreCombatCooldowns then items.restoreCombatCooldowns() end
end
local function readAck(now,d)
    if state.ackDisplay~=d.id then state.ackDisplay,state.ackAt,state.ackMuzzle,state.pollAt=d.id,nil,nil,nil end
    if state.pollAt and now<state.pollAt then return end
    state.pollAt=now+40
    local ok,raw=pcall(Isaac.LoadModDataFromFolder,'samira_testroom_link')
    if not ok or type(raw)~='string' or #raw>4096 then return end
    local parsed,a=pcall(json.decode,raw)
    if parsed and type(a)=='table' and a.version==1 and a.hero=='mf' and a.session==state.id and a.room==state.room
        and a.display==d.id and a.ready==true and a.visible==true and type(a.time)=='number'
        and a.time<=now+100 and now-a.time<500 and type(a.capabilities)=='table' and a.capabilities.mfModel==true then
        state.ackAt=math.min(now,a.time)
        state.ackMuzzle=a.capabilities.mfMuzzle==true
    else state.ackAt,state.ackMuzzle=nil,nil end
end
local function companionReady(now,d)
    if d.mode=='exclusive' then
        state.ackAt,state.ackMuzzle,state.pollAt=nil,nil,nil
        return false
    end
    readAck(now,d)
    return state.ackAt and now-state.ackAt<500
end
local afterShot = {
    attack={idle='attack_out',moving='attack_run',strut='attack_strut'},
    attack2={idle='attack2_out',moving='attack2_run',strut='attack2_strut',movingFallback='run_in'},
    crit={idle='crit_out'},
    q={idle='q_out',moving='q_run'},
    e={idle='e_out',moving='e_run'},
}
local locomotion = {run_in=true,run=true,w=true,strut_run_loop=true}
local function idlePose(clock)
    if not baseIdleDuration then return 'idle',clock,true end
    if state.idleIntroAt and clock>=state.idleIntroAt and clock-state.idleIntroAt<idleIntroDuration then
        return 'idle_in',clock-state.idleIntroAt,false,nil,state.idleIntroAt
    end
    local period=baseIdleDuration+(state.idleAlternate and alternateIdleDuration or 0)
    if not state.idleAt or clock<state.idleAt or clock-state.idleAt>=period then
        if not state.idleRng then
            state.idleRng=RNG()
            local seed=game:GetRoom():GetSpawnSeed()
            state.idleRng:SetSeed(seed~=0 and seed or 1,35)
        end
        state.idleAt=clock
        -- The Skin69 selector chooses idle01 (60%) or idle01 then idle02 (40%).
        state.idleAlternate=alternateIdleDuration and state.idleRng:RandomInt(100)<40
    end
    local elapsed=clock-state.idleAt
    if state.idleAlternate and elapsed>=baseIdleDuration then
        return 'idle',elapsed-baseIdleDuration,true,nil,state.idleAt+baseIdleDuration
    end
    return 'base_idle',elapsed,true,nil,state.idleAt
end
local function pose(clock,death,moving,expression,expressionFrame)
    local action=state.action
    local barrage=state.combat.r
    if death then
        local started=state.deathAt or clock
        return 'death',math.max(0,clock-started),false,nil,started
    end
    if barrage and barrage.waves then
        local launched=barrage.nextTick-barrage.interval
        return 'r',Sprites.barrageFrame(barrage.waves,clock-launched,barrage.interval),true,nil,launched
    end
    if state.qWindupAt then return 'q_in',clock-state.qWindupAt,false,nil,state.qWindupAt end
    if action and clock<action.finish then
        local clip=moving and action.clip=='r_out' and 'r_run' or action.clip
        local duration=not action.preview and action.finish-action.start or nil
        local frame,length=Sprites.discharge(clip,clock-action.start,duration)
        return clip,frame,false,length,action.start
    end
    if expression then return expression,expressionFrame,false,nil,state.emotes.expressionAt end
    local specialClip, specialFrame, specialLoop, specialLength, specialAt=Special.pose(state.special,clock)
    if specialClip then return specialClip,specialFrame,specialLoop,specialLength,specialAt end
    local recovery=action and not action.preview and afterShot[action.clip]
    local strutting=state.strutMoveAt~=nil
    if recovery and clock<action.finish+7 then
        local bridge=moving and ((strutting and recovery.strut) or recovery.moving)
            or not moving and recovery.idle
        if bridge and not Sprites.duration(bridge) then bridge=moving and recovery.movingFallback end
        if bridge then return bridge,clock-action.finish,false,7,action.finish end
    end
    if moving then
        if strutting then
            local elapsed=clock-state.strutMoveAt
            if strutIntroDuration and elapsed<strutIntroDuration then
                return 'w',elapsed,false,nil,state.strutMoveAt
            end
            return 'strut_run_loop',elapsed-(strutIntroDuration or 0),true,nil,
                state.strutMoveAt+(strutIntroDuration or 0)
        end
        if clock-state.movingAt<7 then return 'run_in',clock-state.movingAt,false,7,state.movingAt end
        return 'run',clock,true
    end
    return idlePose(clock)
end
local function currentPose(p,clock,death)
    local moving=p.Velocity:Length()>.6
    if not moving and idleIntroDuration and locomotion[state.lastPose] then state.idleIntroAt=clock end
    state.movingAt=moving and (state.movingAt or clock) or nil
    local strutting=moving and Combat.speed(state.combat,clock)>=1.2 and strutRunDuration
    state.strutMoveAt=strutting and (state.strutMoveAt or clock) or nil
    local expression, expressionFrame=Emotes.action(state.emotes,clock)
    local clip,frame,loop,duration,actionId=pose(clock,death,moving,expression,expressionFrame)
    if clip~='base_idle' and clip~='idle' then state.idleAt,state.idleAlternate=nil,nil end
    if clip~='idle_in' then state.idleIntroAt=nil end
    state.lastPose=clip
    return clip,frame,loop,duration,actionId,clip==expression and expression or nil,moving
end
local function prepareNativePose(p,clock)
    state.nativeClip=nil
    local death=deathAnimating(p)
    if hidden(p,death) then return end
    local now=Isaac.GetTime()
    local _,_,d=display.sample()
    if state.nativeDisplay~=d.id then
        state.nativeDisplay,state.nativeAfter=d.id,now+displaySettleMillis
    end
    if now<state.nativeAfter or companionReady(now,d) then return end
    local clip,frame,_,duration,_,expression=currentPose(p,clock,death)
    state.nativeClip,state.nativeFrame=Sprites.sample(clip,frame,duration,expression)
    state.nativeDeath=death
    if state.nativeClip then Sprites.prepare(state.nativeClip) end
end
local function muzzlePacket(combat,clock)
    local flash=combat.muzzle
    if flash and clock>=flash.startFrame and clock<flash.untilFrame then
        return {kind=flash.clip,start=flash.startFrame,finish=flash.untilFrame}
    end
    local wave=combat.barrageWave
    if wave and wave.channel==combat.r and clock>=wave.launchedAt and clock<wave.launchedAt+2 then
        return {kind='r',start=wave.launchedAt,finish=wave.launchedAt+2,gun=(wave.number-1)%2+1}
    end
end
local function emit(p,clock)
    local now=Isaac.GetTime(); local width,height,d=display.sample()
    local death=deathAnimating(p)
    local occluded=hidden(p,death)
    if state.emitAt and now-state.emitAt<30 and state.lastHidden==occluded and state.emitDisplay==d.id then return end
    state.emitAt,state.lastHidden,state.emitDisplay=now,occluded,d.id
    state.seq=state.seq+1
    local room=game:GetRoom(); local pos=Isaac.WorldToScreen(p.Position)
    local face=displayedFacing(clock); local fx=face.X
    if room:IsMirrorWorld() then pos.X=width-pos.X; fx=-fx end
    local clip,frame,loop,duration,actionId,expression,moving=currentPose(p,clock,death)
    local scale=p.SpriteScale
    local barrage=state.combat.r
    packet({version=1,companionProtocol=1,active=true,preview=false,hero='mf',presentation=2,hudVisible=false,
        renderCaptured=not occluded,session=state.id,room=state.room,seq=state.seq,time=now,clock=clock,
        screen={width,height},display=d,position={pos.X,pos.Y},face={fx,face.Y},viewFace={fx,face.Y},
        kind=clip,clip=clip,phase=loop and (frame/30)%1 or math.min(1,frame/18),looping=loop,
        actionFrame=frame,actionId=actionId,actionLength=duration,mfMoving=moving,
        expression=expression,mfW=Combat.strut(state.combat,clock),
        mfMuzzle=muzzlePacket(state.combat,clock),
        mfBarrage=barrage and barrage.waves and {start=barrage.startFrame,interval=barrage.interval} or nil,
        bodyScale=scale and {scale.X,scale.Y} or {1,1},
        paused=game:IsPaused(),transition=state.leaving==true,occluded=occluded,hurt=clock<(state.hurtUntil or 0),
        nativeCursor=Options.MouseControl==true,sfxVolume=Options.SFXVolume})
end
local function project(point)
    local screen = Isaac.WorldToScreen(point)
    if game:GetRoom():IsMirrorWorld() then screen.X=Isaac.GetScreenWidth()-screen.X end
    return screen
end
local function drawEffects(p,clock)
    Special.render(state.special,clock,p,project)
    local waveFraction = 0
    if state.waveRenderAt and not game:IsPaused() then
        waveFraction = math.max(0,math.min(1,(Isaac.GetTime()-state.waveRenderAt)*.03))
    end
    local mirror=game:GetRoom():IsMirrorWorld()
    local companion=state.ackAt and state.ackDisplay==state.emitDisplay and Isaac.GetTime()-state.ackAt<500
    local rig={scale=p.SpriteScale or Vector(1,1),mirrored=mirror,companion=companion,modelScale=modelScale,
        companionMuzzle=companion and state.ackMuzzle}
    Effects.render(state.combat,clock,project,p.Position,waveFraction,rig)
    local active=Combat.strut(state.combat,clock)
    local maxStrut=Combat.speed(state.combat,clock)>=1.2
    if active>0 or maxStrut then
        local pose,index
        if active>0 then
            local clip,frame,_,duration,_,expression=currentPose(p,clock,false)
            pose,index=Sprites.sample(clip,frame,duration,expression)
        end
        Effects.renderStrut(p,clock,project,{active=active,maxStrut=maxStrut,chargedAt=state.strutChargedAt,
            pose=pose,index=index,face=displayedFacing(clock),mirrored=mirror,modelScale=modelScale})
    end
    local expression, frame=Emotes.action(state.emotes,clock)
    if expression=='recall_cinematic' then Effects.renderRecallFinale(project(p.Position),frame,recallDuration+1) end
    local marked,markedAt=Combat.loveTapTarget(state.combat)
    if marked then
        local age=math.max(0,clock-markedAt)
        Effects.renderLoveTap(project(marked.Position), .72+.28*math.max(0,1-age/12))
    end
    local phase = Emotes.mastery(state.emotes,clock)
    if phase then
        if badge == nil then
            local sprite,loaded = Sprite('gfx/hero_mastery/badge.anm2',true)
            badge=loaded and sprite or false
        end
        if badge then
            local scale = p.SpriteScale and math.abs(p.SpriteScale.Y) or 1
            local position = project(p.Position+(p.SpriteOffset or Vector.Zero))-Vector(0,20+30*scale*bodyScale)
            badge:SetFrame('Play',math.floor(120*phase))
            badge.Scale,badge.Color=Vector(.5,.5),Color(1,1,1,math.min(1,(120*phase+1)/6,(1-phase)*12))
            badge:Render(position)
        end
    end
end
local function renderFacing(clock)
    return math.floor((90-displayedFacing(clock):GetAngleDegrees())/45+.5)%8
end
local function drawFallback(p,offset,death,displayId)
    local clock=game:GetFrameCount()
    local direction=renderFacing(clock)
    local position=Isaac.WorldToRenderPosition(p.Position)+offset
    local scale=p.SpriteScale or Vector(1,1)
    local fill=Combat.strut(state.combat,clock)
    local color=fill>0 and Color(1,.83,.68,1,.08,.015,0) or p:GetSprite().Color
    if state.nativeClip and state.nativeDeath==death and state.nativeDisplay==displayId and Sprites.drawPrepared(
        state.nativeClip,state.nativeFrame,direction,position,scale*nativeActionScale,color) then return true end
    if death or not fallbackSprite then return false end
    local moving=p.Velocity:Length()>.6
    local walkingFrame=moving and math.floor(clock/7.5)%4 or 0
    fallbackSprite:SetFrame((moving and 'Walk' or 'Idle') .. direction, walkingFrame)
    fallbackSprite.Scale, fallbackSprite.Color=scale*bodyScale,color
    fallbackSprite:Render(position)
    return true
end
local function attackable(target)
    return target and target:Exists() and not target:IsDead() and target:IsVulnerableEnemy()
        and (not target.HasEntityFlags or not target:HasEntityFlags(EntityFlag.FLAG_FRIENDLY))
end
local function targetAt(aim)
    local closest,distance
    for _,entity in ipairs(Isaac.GetRoomEntities()) do
        if attackable(entity) then
            local offset = (entity.Position-aim):Length()
            if offset<=math.max(16,(entity.Size or 0)+8) and (not distance or offset<distance) then
                closest,distance=entity,offset
            end
        end
    end
    return closest
end
local function setGroundGoal(room,aim)
    state.door=Navigation.doorAt(room,aim)
    state.goal=room:GetClampedPosition(aim,12)
end
local function attackRange(p)
    local base=math.max(56,math.min(165,(p.TearRange or 260)*.55))
    if weapons and weapons.attackRange then base=weapons.attackRange(p,base) end
    if items and items.attackRange then base=items.attackRange(p,base) end
    return base
end
local function firingPosition(p,room,target,from)
    if (target.Position-from):Length()>attackRange(p)+(target.Size or 0) then return false end
    local spectral=weapons and weapons.passesGrid and weapons.passesGrid(p)
        or items and items.spectral and items.spectral(p)
    return spectral or room:CheckLine(from,target.Position,3,0,false,false)
end
local function move(p,room,clock,manual,attack)
    state.intent=nil
    if manual then
        stopMoving()
        state.intent=manual
        return
    end
    if attack then
        stopMoving()
        return
    end
    if state.target and not attackable(state.target) then stopMoving() end
    local target=state.target
    if target and firingPosition(p,room,target,p.Position) then return target.Position end
    local goal=target and target.Position or state.goal
    if not goal then return end
    local direction,approach=Navigation.doorHeading(room,p.Position,state.door)
    if direction then state.intent=direction; return end
    goal=approach or goal
    if not target and not state.door and (goal-p.Position):Length()<=6 then stopMoving(); return end
    local function nextShot(point) return firingPosition(p,room,target,point) end
    local waypoint,final=Navigation.waypoint(state,room,p,goal,clock,Navigation.clearPoint,Navigation.clearSegment,
        target and nextShot)
    if waypoint then
        local delta=waypoint-p.Position
        local throttle=final and not target and not state.door and math.max(.32,math.min(1,delta:Length()/16)) or 1
        if delta:Length()>.001 then state.intent=delta:Normalized()*throttle end
    elseif final and not target then stopMoving() end
end
function MF.init(mod,g,itemModule,inventory,weaponModule,readHudScale,readR,sharedDisplay,crafting,otherChampion,readInventoryBounds)
    game,items,weapons,readScale,readUltimate=g,itemModule,weaponModule,readHudScale,readR
    display=sharedDisplay or include('samira_display')
    isCrafting,isOtherChampion,inventoryBounds=crafting,otherChampion,readInventoryBounds
    mod:AddCallback(ModCallbacks.MC_POST_GAME_STARTED,function(_,continued)
        stop()
        testMode=false
        local p=owner()
        if p then start(p,continued) end
    end)
    mod:AddCallback(ModCallbacks.MC_PRE_GAME_EXIT,function() stop(); testMode=false end)
    if ModCallbacks.MC_PRE_MOD_UNLOAD then mod:AddCallback(ModCallbacks.MC_PRE_MOD_UNLOAD,function(_,m) if m==mod then stop() end end) end
    mod:AddCallback(ModCallbacks.MC_POST_UPDATE,function()
        local p=owner()
        if not p then
            if state and not state.leaving and not state.floorRebinding and Isaac.IsInGame()
                and game:GetNumPlayers()>0 and Isaac.GetPlayer(0) then stop() end
            return
        end
        if not state then start(p,false) end
        local clock=game:GetFrameCount(); local room=game:GetRoom()
        if state.leaving and (state.floorArrived or room:GetSpawnSeed()~=state.departureSeed)
            and not p:IsDead() and p.ControlsEnabled~=false
            and (not RoomTransition or RoomTransition.GetTransitionMode()==0 and not RoomTransition.IsRenderingBossIntro()) then
            state.leaving,state.floorRebinding,state.floorArrived,state.ackAt,state.emitAt=nil,nil,nil,nil,nil
            state.room=state.room+1
        end
        if items and items.applyCooldownCheckpoint then items.applyCooldownCheckpoint(clock) end
        if inventory and inventory.update then inventory.update(p,clock) end
        if items and items.update then items.update(p,clock) end
        if items and items.claimCombatRoomReset and items.claimCombatRoomReset() and not state.continuing then MF.reduceCooldowns(1,clock) end
        sampleRunePicker(not hidden(p) and picking())
        local death=deathAnimating(p)
        local dead=p:IsDead() or death
        local allowed=not dead and MF.canUseItems(p) and not (isCrafting and isCrafting())
        if dead then
            if not state.awaitingRevive then
                state.action=nil
                stopLifecycleSound()
                stopCombatAudio()
                Combat.resetRoom(state.combat)
            end
            state.awaitingRevive=true
            Special.reset(state.special)
            if death and not state.deathAt and not combatSuspended() then
                state.deathAt,state.deathRoom=clock,state.room
                startLifecycleSound('death')
            end
        elseif allowed and state.awaitingRevive then
            state.awaitingRevive,state.deathAt,state.deathRoom=nil,nil,nil
            Combat.grantStrut(state.combat,clock)
            animation('respawn',clock,respawnDuration+1)
            startLifecycleSound('respawn')
        end
        if allowed and state.previewClip then
            Emotes.cancel(state.emotes,false)
            animation(state.previewClip,clock,math.max(180,(Sprites.duration(state.previewClip) or 0)+1))
            if state.previewClip=='death' or state.previewClip=='respawn' then startLifecycleSound(state.previewClip) end
            state.action.preview,state.previewClip=true,nil
        end
        local aim=Navigation.worldCursor(room)
        local moveRight,rightPressed=sampleButton(Keyboard.KEY_RIGHT)
        local moveLeft,leftPressed=sampleButton(Keyboard.KEY_LEFT)
        local moveDown,downPressed=sampleButton(Keyboard.KEY_DOWN)
        local moveUp,upPressed=sampleButton(Keyboard.KEY_UP)
        local movePressed=rightPressed or leftPressed or downPressed or upPressed
        local dx=(moveRight and 1 or 0)-(moveLeft and 1 or 0)
        local dy=(moveDown and 1 or 0)-(moveUp and 1 or 0)
        if room:IsMirrorWorld() then dx=-dx end
        local manual=(dx~=0 or dy~=0) and Vector(dx,dy):Normalized() or nil
        local attack,attackPressed=sampleButton(Keyboard.KEY_A)
        local right=Input.IsMouseBtnPressed(1)
        local click=right and not state.held.mouse
        if not allowed then stopMoving()
        elseif click then
            stopMoving()
            state.target=targetAt(aim)
            if not state.target then setGroundGoal(room,aim); state.drag=true end
        elseif right and state.drag then
            setGroundGoal(room,aim)
        elseif not right then
            state.drag=nil
        end
        state.held.mouse=right
        local down={q=pressed(keys.q),w=pressed(keys.w),e=pressed(keys.e),r=readUltimate and readUltimate()==true}
        for _,key in ipairs({'q','w','e','r'}) do
            local trigger=down[key] and not state.held[key]
            state.held[key]=down[key]
            if allowed and trigger then
                local interrupted = state.combat.r ~= nil
                if interrupted then
                    Combat.cancelUltimate(state.combat)
                    animation('r_out',clock,12)
                end
                if not (interrupted and key=='r') and Combat.cast(state.combat,key,p,aim,clock,room,items,weapons) then
                    if key~='w' then
                        state.face=(aim-p.Position):Length()>.001 and (aim-p.Position):Normalized() or state.face
                    end
                    Emotes.cancel(state.emotes,false)
                    if key=='e' then
                        Effects.prepareStageEffects()
                        animation(key,clock,15,state.face)
                    elseif key=='q' then
                        state.combat.muzzle=nil
                    end
                    if key=='r' then
                        animation('r_in',clock,state.combat.r.startFrame-clock)
                        stopMoving()
                        state.rStarted=clock; state.rDuration=state.combat.ready.r-clock; p.Velocity=Vector.Zero
                        Effects.playSound('R',.47)
                        Effects.playSound('R Voice',.65)
                    elseif key=='e' then
                        Effects.playSound('E',.63)
                        Effects.playSound('E Voice',.56)
                    elseif key=='w' then
                        Effects.playSound('W',.61)
                    end
                end
            end
        end
        if state.combat.r and (not allowed or state.rStarted~=clock and (movePressed or attackPressed or click)) then
            Combat.cancelUltimate(state.combat)
            animation('r_out',clock,12)
        end
        local barrage,rain=state.combat.r,state.combat.rain
        if not dead and not combatSuspended() then
            local waves=barrage and barrage.waves
            local ticks=rain and rain.ticks
            Combat.update(state.combat,p,clock,room,items)
            state.waveRenderAt=state.combat.barrageWave and Isaac.GetTime() or nil
            if barrage and barrage.waves~=waves then
                if not waves then state.barrageSound=Effects.playSound('R Barrage',.35) end
                Effects.playBulletSound('r',barrage.waves)
            end
            if rain and rain.ticks~=ticks then
                if rain.ticks==1 then state.rainSound=Effects.playSound('E Rain',.41) end
                if not state.rainSound then Effects.playBulletSound('e') end
            end
        end
        if barrage and not state.combat.r then animation('r_out',clock,12) end
        if not state.combat.r and state.barrageSound then
            Effects.stopSound(state.barrageSound)
            state.barrageSound=nil
        end
        if (not state.combat.rain or p:IsDead()) and state.rainSound then
            Effects.stopSound(state.rainSound)
            state.rainSound=nil
        end
        local armed=allowed and not state.combat.r
        local target=armed and move(p,room,clock,manual,attack) or nil
        if state.combat.r then state.intent=nil end
        local shot=armed and (target or attack and aim)
        if shot and (shot-p.Position):Length()>.001 then state.face=(shot-p.Position):Normalized()
        elseif state.intent and not (state.action and clock<state.action.finish) then state.face=state.intent:Normalized() end
        sampleExpressions(clock,allowed,state.intent~=nil or shot or state.combat.r~=nil
            or state.action and clock<state.action.finish or p.Velocity:Length()>.6)
        if weapons then
            if armed and weapons.trackCursor then weapons.trackCursor(p,aim) end
            weapons.update(p,clock,shot and state.face or nil,armed,target or aim)
        end
        local windingUp=armed and weapons and weapons.hasPendingQ and weapons.hasPendingQ(p)
        state.qWindupAt=windingUp and (state.qWindupAt or clock) or nil
        if state.action and state.action.clip=='respawn' and (shot or state.intent) then state.action=nil end
        if state.lifecycleUntil and clock<state.lifecycleUntil
            and (not state.action or state.action.clip~=state.lifecycleClip) then stopLifecycleSound() end
        local speed,as=MF.speed(p,clock),MF.attackSpeed(p,clock)
        Special.update(state.special,clock,game,allowed,state.intent~=nil or p.Velocity:Length()>.6,
            shot or windingUp or state.combat.r or state.action and clock<state.action.finish
            or Emotes.action(state.emotes,clock) or clock<(state.hurtUntil or 0),speed>=1.2 and strutRunDuration)
        if speed>=1.2 and (not state.speed or state.speed<1.2) then state.strutChargedAt=clock end
        if state.speed~=speed or state.as~=as then state.speed,state.as=speed,as; refresh(p) end
        prepareNativePose(p,clock)
    end)
    mod:AddCallback(ModCallbacks.MC_INPUT_ACTION,function(_,entity,hook,action)
        if not state then return end
        local axis,shoot,key=axes[action],shootActions[action],nil
        if action==ButtonAction.ACTION_BOMB then key=Keyboard.KEY_G
        elseif action==ButtonAction.ACTION_PILLCARD then key=Keyboard.KEY_4 end
        local active=action==ButtonAction.ACTION_ITEM or action==ButtonAction.ACTION_DROP
        if not axis and not shoot and not key and not (active and picking()) then return end
        local p=owner(); local ep=entity and entity:ToPlayer()
        if not p or entity and (not ep or ep.Index~=p.Index) or (p.ControllerIndex or 0)~=0 then return end
        local allowed=MF.canUseItems(p) and not (isCrafting and isCrafting())
        if shoot then
            if allowed and weapons and weapons.input then return weapons.input(p,hook,action) end
            return hook==InputHook.GET_ACTION_VALUE and 0 or false
        end
        local value=0
        if allowed and key and not (action==ButtonAction.ACTION_PILLCARD and Emotes.blocksPocket(state.emotes)) then
            if hook==InputHook.IS_ACTION_TRIGGERED then return Input.IsButtonTriggered(key,0) end
            value=pressed(key) and 1 or 0
        elseif allowed and axis and state.intent then
            local intent=items and items.movementInput and items.movementInput(p,state.intent) or state.intent
            value=math.max(0,intent:Dot(axis))
        end
        if hook==InputHook.GET_ACTION_VALUE then return value end
        return value>0
    end)
    mod:AddCallback(ModCallbacks.MC_PRE_PLAYER_RENDER,function(_,p,offset)
        if not state or not MF.is(p) then return end
        local death=deathAnimating(p)
        if hidden(p,death) then return end
        local clock=game:GetFrameCount()
        local expression, frame=Emotes.action(state.emotes,clock)
        local action=state.action
        local lifeClip, lifeStart
        if death and state.deathRoom==state.room then
            lifeClip,lifeStart='death',state.deathAt
        elseif action and clock<action.finish and (action.clip=='respawn' or action.clip=='death') then
            lifeClip,lifeStart=action.clip,action.start
        end
        if lifeClip then
            local pos=Isaac.WorldToRenderPosition(p.Position)+(offset or Vector.Zero)
            Effects.renderLifecycle(lifeClip,pos,clock-lifeStart,renderFacing(clock),p.SpriteScale or Vector(1,1),modelScale)
        elseif expression=='joke' and jokeIntroDuration and jokeBodyDuration then
            local pos=Isaac.WorldToRenderPosition(p.Position)+(offset or Vector.Zero)
            Effects.renderJoke(pos,frame,renderFacing(clock),jokeIntroDuration,jokeBodyDuration)
        elseif expression=='dance' then
            local pos=Isaac.WorldToRenderPosition(p.Position)+(offset or Vector.Zero)
            Effects.renderDance(pos,frame)
        elseif expression=='taunt_spam' then
            local pos=Isaac.WorldToRenderPosition(p.Position)+(offset or Vector.Zero)
            Effects.renderTaunt(pos,frame,renderFacing(clock),p.SpriteScale or Vector(1,1),modelScale)
        elseif expression=='recall_cinematic' then
            local pos=Isaac.WorldToRenderPosition(p.Position)+(offset or Vector.Zero)
            Effects.renderRecallStage(pos,frame,recallDuration+1,renderFacing(clock),
                p.SpriteScale or Vector(1,1),bodyScale,modelScale)
        end
        local now=Isaac.GetTime(); local _,_,d=display.sample()
        if companionReady(now,d) then return false end
        if offset and drawFallback(p,offset,death,d.id) then return false end
    end)
    if ModCallbacks.MC_PRE_TEAR_RENDER then
        mod:AddCallback(ModCallbacks.MC_PRE_TEAR_RENDER,function(_,tear,offset)
            local p=state and owner()
            if not p or hidden(p) or tear.Variant~=TearVariant.BLUE and tear.Variant~=TearVariant.BLOOD then return end
            -- Cricket's Body changes the impact. The parent still flies like a normal shot.
            local flags=tear.TearFlags
            if flags~=TearFlags.TEAR_NORMAL and flags~=TearFlags.TEAR_QUADSPLIT then return end
            local tag=tear:GetData().SamiraNativeWeapon
            local ctx=tag and tag.context
            if not ctx or tag.split or (ctx.kind~='q' and ctx.kind~='aa') or not ctx.nativeWeapon or ctx.persistentPulse
                or not ctx.player or ctx.player.Index~=p.Index then return end
            if Effects.renderTear(tear,offset,ctx.kind) then return false end
        end)
    end
    mod:AddCallback(ModCallbacks.MC_POST_RENDER,function()
        local p=state and owner(); if not p then return end
        local clock=game:GetFrameCount(); emit(p,clock)
        if not hidden(p) then
            local scale=readScale and readScale() or 1
            if picking() then
                HUD.renderRunePicker(Runes.choices,state.runeSelection,scale)
                return
            end
            drawEffects(p,clock)
            local bounds=MF.hudBounds(scale,inventoryBounds and inventoryBounds(p,scale))
            local crit,haste
            if items and items.combatStats then crit,haste=items.combatStats(p) end
            CombatHUD.render(bounds,state.combat,clock,{
                damage=p.Damage, crit=crit or 0, haste=haste or 0, move=p.MoveSpeed,
                attacks=30/math.max(1,p.MaxFireDelay+1), range=attackRange(p),
            },Runes,runes())
        end
    end)
    mod:AddCallback(ModCallbacks.MC_POST_ENTITY_TAKE_DMG,function(_,target,amount,flags)
        local p=state and owner(); if p and target.Type==EntityType.ENTITY_PLAYER and target.Index==p.Index and amount>0 then
            local fake=DamageFlag and DamageFlag.DAMAGE_FAKE or 0
            if (flags or 0)&fake~=0 then return end
            local clock=game:GetFrameCount(); state.hurtUntil=clock+6
            Emotes.cancel(state.emotes,false)
            local periodic=DamageFlag and DamageFlag.DAMAGE_POISON_BURN or 0
            if (flags or 0)&periodic==0 then Combat.tookDamage(state.combat,clock); refresh(p) end
        end
    end)
    local function resetRoom()
        if not state then return end
        Combat.resetRoom(state.combat)
        Special.reset(state.special)
        stopMoving()
        stopCombatAudio()
        stopLifecycleSound()
        stopExpressionSound()
        Emotes.cancel(state.emotes,true)
        state.action,state.ackAt,state.emitAt,state.pollAt,state.continuing=nil,nil,nil,nil,nil
        state.ackMuzzle=nil
        state.previewClip,state.movingAt,state.strutMoveAt,state.qWindupAt=nil,nil,nil,nil
        state.idleAt,state.idleAlternate,state.idleIntroAt,state.lastPose=nil,nil,nil,nil
        state.nativeClip=nil
        state.deathRoom=nil
    end
    mod:AddCallback(ModCallbacks.MC_PRE_CHANGE_ROOM,function()
        if state then state.leaving=true; state.departureSeed=game:GetRoom():GetSpawnSeed(); resetRoom() end
    end)
    mod:AddCallback(ModCallbacks.MC_POST_NEW_ROOM,function()
        if not state then return end
        resetRoom()
        if state.floorRebinding then state.floorArrived=true
        else state.leaving=nil; state.room=state.room+1 end
    end)
    if ModCallbacks.MC_PRE_ROOM_EXIT then
        mod:AddCallback(ModCallbacks.MC_PRE_ROOM_EXIT,function(_,p,newLevel)
            if state and newLevel and MF.is(p) then
                resetRoom()
                state.leaving,state.floorRebinding=true,true
                state.departureSeed=game:GetRoom():GetSpawnSeed()
            end
        end)
    end
    mod:AddCallback(ModCallbacks.MC_POST_NEW_LEVEL,function()
        if state then
            resetRoom()
            state.special.homeguardReady=true
            if state.leaving then state.floorArrived=true end
        end
    end)
    if Console and Console.RegisterCommand and ModCallbacks.MC_EXECUTE_CMD then
        Console.RegisterCommand('mftest','Activate, reconnect or preview Miss Fortune','mftest [off|anim CLIP]',false,AutocompleteType.NONE)
        mod:AddCallback(ModCallbacks.MC_EXECUTE_CMD,function(_,name,args)
            if name~='mftest' then return end
            local arg=(args or ''):match('^%s*(.-)%s*$'):lower()
            local preview=arg:match('^anim%s+(%w[%w_]*)$')
            if preview and not animationPreviews[preview] then Isaac.ConsoleOutput('Unknown MF animation.\n'); return end
            if arg=='off' then
                if testMode then stop(); testMode=false end
                Isaac.ConsoleOutput('Miss Fortune test mode off.\n')
                return
            end
            local p=Isaac.IsInGame() and game:GetNumPlayers()==1 and Isaac.GetPlayer(0)
            if arg~='' and arg~='on' and not preview then Isaac.ConsoleOutput('Usage: mftest [off|anim CLIP]\n'); return end
            if not p then Isaac.ConsoleOutput('Start a single-player run first.\n'); return end
            if isOtherChampion and isOtherChampion(p) then
                Isaac.ConsoleOutput('Start a Miss Fortune or Isaac run to use mftest.\n')
                return
            end
            if not MF.isNative(p) then testMode=true end
            if state then
                resetRoom()
                state.leaving,state.floorRebinding,state.floorArrived=nil,nil,nil
                state.room=state.room+1
                if weapons and weapons.reset then weapons.reset() end
            else start(p,true) end
            state.previewClip=preview
            Isaac.ConsoleOutput('Miss Fortune connected. Close the console.\n')
        end)
    end
end
return MF
