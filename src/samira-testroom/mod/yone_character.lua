local Yone = {}
local Combat = include('yone_combat')
local Artifacts = include('yone_artifacts')
local Debug = include('yone_debug')
local Emotes = include('yone_emotes')
local Navigation = include('samira_navigation')
local HUD = include('yone_hud')
local Progress = include('yone_progression')
local json = require('json')
local playerType
local testMode = false
local badge
local Display
local fps, leaseMs = 30, 500
-- Crest clearance and the on-screen body height for each renderer.
local masteryCrestRise, masteryModelHeight = 26, 46
local masteryAtlasRise, masteryNativeHeight = 22, 31
local spiritWarningTicks = 2 * fps
local aimColors = {
    q = {.60, .93, 1}, w = {.99, .49, .60}, e = {.99, .39, .65}, r = {1, .53, .73},
}
local numberKeys = {Keyboard.KEY_1, Keyboard.KEY_2, Keyboard.KEY_3, Keyboard.KEY_4, Keyboard.KEY_5, Keyboard.KEY_6}
local upgradeKeys = {q = Keyboard.KEY_Q, w = Keyboard.KEY_W, e = Keyboard.KEY_E, r = Keyboard.KEY_R}
local controls = {
    {'q', Keyboard.KEY_Q}, {'w', Keyboard.KEY_W}, {'e', Keyboard.KEY_E}, {'r', Keyboard.KEY_R},
    {'attack', Keyboard.KEY_A}, {'stop', Keyboard.KEY_S}, {'mouse'},
}
local axes = {
    [ButtonAction.ACTION_LEFT] = Vector(-1, 0), [ButtonAction.ACTION_RIGHT] = Vector(1, 0),
    [ButtonAction.ACTION_UP] = Vector(0, -1), [ButtonAction.ACTION_DOWN] = Vector(0, 1),
}
local blocked = {
    [ButtonAction.ACTION_SHOOTLEFT] = true, [ButtonAction.ACTION_SHOOTRIGHT] = true,
    [ButtonAction.ACTION_SHOOTUP] = true, [ButtonAction.ACTION_SHOOTDOWN] = true,
}
local rebound = {[ButtonAction.ACTION_BOMB] = Keyboard.KEY_G, [ButtonAction.ACTION_PILLCARD] = Keyboard.KEY_4}

function Yone.isNative(player)
    if not player or not player.GetPlayerType then return false end
    if not playerType then
        local result = Isaac.GetPlayerTypeByName('Yone', false)
        if result >= 0 then playerType = result end
    end
    return playerType ~= nil and player:GetPlayerType() == playerType
end

function Yone.is(player)
    if testMode and player and player.GetPlayerType and Isaac.IsInGame() then
        local owner = Isaac.GetPlayer(0)
        if owner and player.Index == owner.Index then return true end
    end
    return Yone.isNative(player)
end

function Yone.player(game)
    if not Isaac.IsInGame() or game:GetNumPlayers() ~= 1 then return end
    local player = Isaac.GetPlayer(0)
    if Yone.is(player) then return player end
end

local function pressed(key)
    return Input.IsButtonPressed(key, 0)
end

local function upgrading()
    return pressed(Keyboard.KEY_LEFT_ALT) or pressed(Keyboard.KEY_RIGHT_ALT)
end

local function packet(payload)
    Isaac.DebugString('[SAMIRA_EXTERNAL] ' .. json.encode(payload))
end

local function roomTransition(state)
    return RoomTransition.GetTransitionMode() ~= 0 and not state.staleTransitionMode
end

local function obscured(game, state, player, checkingArrival)
    local sprite = player:GetSprite()
    local name = sprite:GetAnimation()
    local travel = name:find('Trapdoor', 1, true) ~= nil or name:find('Teleport', 1, true) ~= nil
        or name == 'LightTravel' or name == 'HoleIn' or name == 'FallIn'
    return game:IsPaused() or ImGui.IsVisible()
        or not checkingArrival and (state.leaving or roomTransition(state))
        or RoomTransition.IsRenderingBossIntro()
        or state.coverFrame == game:GetFrameCount() or player:IsDead()
        or travel and sprite:IsPlaying(name)
end

local function canControl(game, state, player)
    return player.ControlsEnabled ~= false and not obscured(game, state, player)
end

local function playMasterySound()
    local sound = Isaac.GetSoundIdByName and Isaac.GetSoundIdByName('Yone Mastery')
    if sound and sound > 0 then SFXManager():Play(sound, .8, 0, false, 1) end
end

local function stopSpiritWarning(state)
    local sound = state.spiritWarningSound
    if sound then SFXManager():Stop(sound) end
    state.spiritWarning, state.spiritWarningSound = nil, nil
end

local function updateSpiritWarning(state, clock)
    local spirit = state.combat.spirit
    if state.spiritWarning and state.spiritWarning ~= spirit then stopSpiritWarning(state) end
    if not spirit or state.spiritWarning == spirit then return end
    local ticks = spirit.untilFrame - clock
    if ticks <= 0 or ticks > spiritWarningTicks then return end
    state.spiritWarning = spirit
    local sound = Isaac.GetSoundIdByName and Isaac.GetSoundIdByName('Yone E Warning')
    if sound and sound > 0 then
        state.spiritWarningSound = sound
        SFXManager():Play(sound, .8, 0, false, 1)
    end
end

local function sampleExpressions(state, clock, allowed, interrupted)
    local keys = {ctrl = pressed(Keyboard.KEY_LEFT_CONTROL) or pressed(Keyboard.KEY_RIGHT_CONTROL),
        disabled = not allowed}
    for index, key in ipairs(numberKeys) do keys[index] = pressed(key) end
    local previousStart = state.emotes.masteryAt
    Emotes.update(state.emotes, clock, keys, interrupted)
    if state.emotes.masteryAt ~= previousStart and state.emotes.masteryAt == clock then playMasterySound() end
end

local function sampleCommands(state, room, allowed, ultimateHeld)
    if not allowed then state.commands, state.intent, state.aimAbility, state.qAfterE = {}, nil, nil, nil end
    for _, control in ipairs(controls) do
        local action, key = table.unpack(control)
        local down
        if action == 'r' then
            down = ultimateHeld
        elseif key then
            down = pressed(key)
        else
            down = Input.IsMouseBtnPressed(1)
        end
        local activate = down and not state.held[action]
        if aimColors[action] then
            if allowed and activate then state.aimAbility = action end
            activate = not down and state.held[action] and state.aimAbility == action
            if activate then state.aimAbility = nil end
        end
        if allowed and activate and #state.commands < #controls then
            state.commands[#state.commands + 1] = {kind = action, aim = Navigation.worldCursor(room)}
        end
        state.held[action] = down
    end
end

local function stopMoving(state)
    state.goal, state.target, state.path, state.door, state.intent = nil, nil, nil, nil, nil
end

local function targetAt(enemies, point)
    local target, nearest
    for _, enemy in ipairs(enemies) do
        if Combat.attackable(enemy) then
            local distance = enemy.Position:Distance(point)
            if distance <= math.max(16, enemy.Size + 8) and (nearest == nil or distance < nearest) then
                target, nearest = enemy, distance
            end
        end
    end
    return target
end

local function setGoal(state, room, aim)
    state.door = Navigation.doorAt(room, aim)
    state.goal = room:GetClampedPosition(aim, 12)
end

local function updateMovement(state, room, player, clock)
    local dx = (pressed(Keyboard.KEY_RIGHT) and 1 or 0) - (pressed(Keyboard.KEY_LEFT) and 1 or 0)
    local dy = (pressed(Keyboard.KEY_DOWN) and 1 or 0) - (pressed(Keyboard.KEY_UP) and 1 or 0)
    if room:IsMirrorWorld() then dx = -dx end
    if dx ~= 0 or dy ~= 0 then
        stopMoving(state)
        state.intent = Vector(dx, dy):Normalized()
        return
    end

    local target = state.target
    if target and not Combat.attackable(target) then stopMoving(state); return end
    if target and Combat.inMeleeRange(room, player, target, state.combat.items) then
        state.intent = nil
        Combat.cast(state.combat, 'attack', player, target.Position, clock, room)
        return
    end
    local goal = target and target.Position or state.goal
    if not goal then state.intent = nil; return end
    local doorHeading, approach = Navigation.doorHeading(room, player.Position, state.door)
    if doorHeading then state.intent = doorHeading; return end
    goal = approach or goal
    if not target and not state.door and player.Position:Distance(goal) <= 6 then
        stopMoving(state)
        return
    end
    local waypoint = Navigation.waypoint(state, room, player, goal, clock, Combat.clearPoint, Combat.clearSegment)
    state.intent = waypoint and (waypoint - player.Position):Normalized() or nil
end

local function mirrorPosition(room, position)
    local x = room:IsMirrorWorld() and Isaac.GetScreenWidth() - position.X or position.X
    return x, position.Y
end

local function screenPoint(room, world)
    return Vector(mirrorPosition(room, Isaac.WorldToScreen(world)))
end

local function screenHeading(room, world, facing)
    local direction = screenPoint(room, world + facing * 40) - screenPoint(room, world)
    return {direction.X, direction.Y}
end

local function sectorArc(area, project)
    local halfAngle = math.deg(math.acos(area.cosine))
    local edge = area.facing * area.reach
    local points = {}
    for i = 0, 12 do
        points[i + 1] = project(area.origin + edge:Rotated((i / 6 - 1) * halfAngle))
    end
    return points
end

local function drawAim(room, combat, player, clock, key)
    if not Isaac.DrawLine or not KColor then return end
    local area, castKey = Combat.activeFootprint(combat, player, room)
    local casting = area ~= nil
    if casting then
        key = castKey or 'r'
    elseif key then
        area = Combat.footprint(combat, player, key, Navigation.worldCursor(room), room)
    end
    if not area or area.reach < 1 then return end
    local r, g, b = table.unpack(aimColors[key])
    local ready = casting or (clock >= (combat.ready[key] or 0))
        or key == 'e' and combat.spirit and clock >= combat.spirit.recastAt
    local edge = KColor(r, g, b, ready and .93 or .35)
    local fill = KColor(r, g, b, casting and .25 or (ready and .15 or .06))
    local function project(point) return screenPoint(room, point) end
    local function line(a, b, color)
        Isaac.DrawLine(a, b, color, color, casting and color == edge and 2 or 1)
    end
    local start = project(area.origin)
    if area.shape == 'sector' then
        local arc = sectorArc(area, project)
        line(start, arc[1], edge)
        local halfAngle = math.deg(math.acos(area.cosine))
        for i = 0, 48 do
            local endpoint = area.origin + (area.facing * area.reach):Rotated((i / 24 - 1) * halfAngle)
            line(start, project(endpoint), fill)
        end
        for i = 2, #arc do line(arc[i - 1], arc[i], edge) end
        line(arc[#arc], start, edge)
    else
        local side = area.facing:Rotated(90) * area.width
        local target = area.origin + area.facing * area.reach
        local a, b = project(area.origin + side), project(target + side)
        local c, d = project(target - side), project(area.origin - side)
        line(a, b, edge)
        line(b, c, edge)
        line(c, d, edge)
        line(d, a, edge)
        for i = -12, 12 do
            local offset = side * (i / 12)
            line(project(area.origin + offset), project(target + offset), fill)
        end
    end
end

local function visualSnapshot(room, picture, pendingUltimate)
    local function point(world)
        return {mirrorPosition(room, Isaac.WorldToScreen(world))}
    end
    local snapshot = {shield = picture.shield, qReady = picture.qReady, qRemaining = picture.qRemaining, fx = {}}
    local function ultimateTelegraph(area)
        local side = area.facing:Rotated(90) * area.width
        local start, finish = area.origin, area.origin + area.facing * area.reach
        if area.reach > 0 then
            return {corners = {point(start + side), point(finish + side),
                point(finish - side), point(start - side)}}
        end
    end
    if pendingUltimate then snapshot.rTelegraph = ultimateTelegraph(pendingUltimate) end
    for i, event in ipairs(picture.fx) do
        snapshot.fx[i] = {id = event.id, kind = event.kind, age = event.age,
            origin = point(event.origin), target = point(event.target), travel = event.travel}
        if event.landing then snapshot.fx[i].landing = point(event.landing) end
        if event.contacts then
            local contacts = {}
            for index, position in ipairs(event.contacts) do contacts[index] = point(position) end
            snapshot.fx[i].contacts = contacts
        end
        if event.bodyFace then
            snapshot.fx[i].bodyFace = screenHeading(room, event.target, event.bodyFace)
            snapshot.fx[i].bodyRemaining = event.bodyRemaining
        end
        if event.footprint then
            local area = event.footprint
            if event.kind == 'r' and event.age < .1 and not snapshot.rTelegraph then
                snapshot.rTelegraph = ultimateTelegraph(area)
            end
            if area.shape == 'sector' then
                snapshot.fx[i].arc = sectorArc(area, point)
            else
                local edge = point(area.origin + area.facing:Rotated(90) * area.width)
                local center = snapshot.fx[i].origin
                snapshot.fx[i].halfWidth = Vector(edge[1] - center[1], edge[2] - center[2]):Length()
            end
        end
        if event.rays then
            local rays = {}
            for j, endpoint in ipairs(event.rays) do rays[j] = point(endpoint) end
            snapshot.fx[i].rays = rays
        end
    end
    local spirit = picture.spirit
    if spirit then
        local marks = {}
        for i, mark in ipairs(spirit.marks) do marks[i] = {position = point(mark.position), amount = mark.amount, lethal = mark.lethal == true} end
        local x = room:IsMirrorWorld() and -spirit.face.X or spirit.face.X
        snapshot.spirit = {anchor = point(spirit.anchor), face = {x, spirit.face.Y},
            viewFace = screenHeading(room, spirit.anchor, spirit.face),
            remaining = spirit.remaining, returning = spirit.returning, marks = marks}
    end
    return snapshot
end

local function readAck(state, now, display)
    if state.ackDisplay ~= display.id then
        state.ackDisplay, state.ackAt, state.pollAt = display.id, nil, nil
    end
    if state.pollAt and now < state.pollAt then return end
    state.pollAt = now + 40
    local ok, raw = pcall(Isaac.LoadModDataFromFolder, 'samira_testroom_link')
    if not ok or type(raw) ~= 'string' or #raw > 4096 then return end
    local decoded, ack = pcall(json.decode, raw)
    if not decoded or type(ack) ~= 'table' then return end
    if ack.version == 1 and ack.session == state.id and ack.room == state.room and ack.display == display.id
        and type(ack.time) == 'number' and ack.time <= now + 100 and now - ack.time < leaseMs
        and type(ack.capabilities) == 'table' then
        state.ackAt = math.min(now, ack.time)
        state.masteryReady = ack.capabilities.mastery == true
        state.modelReady = ack.ready == true and ack.visible == true and ack.capabilities.yoneModel == true
        state.vfxReady = ack.capabilities.yoneVfx == true
    else
        state.ackAt = nil
    end
end

local function leased(state, capability, now)
    return state[capability] and state.ackAt and now - state.ackAt < leaseMs
end

local function emit(game, state, player, force, picture)
    local now = Isaac.GetTime()
    local width, height, display = Display.sample()
    local hidden = obscured(game, state, player)
    if not force and state.emitAt and now - state.emitAt < 30 and hidden == state.wasHidden
        and state.emitDisplay == display.id then return end
    state.emitAt, state.wasHidden, state.emitDisplay = now, hidden, display.id
    state.seq = state.seq + 1
    local clock = game:GetFrameCount()
    local room = game:GetRoom()
    -- Do not combine a room render-pass offset with screen-space marks/FX.
    local x, y = mirrorPosition(room, Isaac.WorldToScreen(player.Position))
    local face = state.combat.face
    local fx = room:IsMirrorWorld() and -face.X or face.X
    local action, phase, hit, length, travel = Combat.presentation(state.combat, clock)
    local expression, actionFrame = Emotes.action(state.emotes, clock)
    if expression then action, phase = expression, 0 end
    local preview = state.debugAnimation
    if not action and preview and clock < preview.finish then
        action, phase = preview.clip, (clock - preview.start) / (preview.finish - preview.start)
    end
    local looping = not action
    if not action then
        action = player.Velocity:Length() > .6 and 'run' or 'idle'
        phase = clock / (action == 'run' and 38 or 60) % 1
    end
    local mastery = not hidden and Emotes.mastery(state.emotes, clock)
    local footprint, activeKey = Combat.activeFootprint(state.combat, player, room)
    local bodyScale = player.SpriteScale
    local masteryRise = mastery and (masteryCrestRise + masteryModelHeight * math.abs(bodyScale and bodyScale.Y or 1))
    packet({
        version = 1, companionProtocol = 1, active = true, preview = false, hero = 'yone',
        presentation = 2, hudVisible = false, renderCaptured = not hidden,
        session = state.id, room = state.room, seq = state.seq, time = now, clock = clock,
        screen = {width, height}, display = display, position = {x, y}, face = {fx, face.Y},
        viewFace = screenHeading(room, player.Position, face),
        kind = action, clip = action, phase = phase, looping = looping,
        yoneTiming = not expression and hit and {hit = hit, length = length, travel = travel} or nil,
        yoneMoving = player.Velocity:Length() > .6,
        actionFrame = actionFrame, actionId = expression and (clock - actionFrame) or nil,
        bodyScale = bodyScale and {bodyScale.X, bodyScale.Y} or {1, 1},
        paused = game:IsPaused(), transition = state.leaving or roomTransition(state),
        occluded = hidden, hurt = clock < (state.hurtUntil or 0),
        nativeCursor = Options.MouseControl == true, sfxVolume = Options.SFXVolume,
        mastery = mastery and {at = mastery, position = {x, y - masteryRise}, rise = masteryRise} or nil,
        yone = not hidden and visualSnapshot(room, picture or Combat.visual(state.combat, clock),
            activeKey == 'r' and footprint or nil) or nil,
    })
end

local function drawNativeEffects(room, player, picture, x, y, geometry, clock)
    local function point(world)
        return Vector(mirrorPosition(room, Isaac.WorldToScreen(world)))
    end
    local function line(a, b, thickness, red, green, blue, alpha)
        if not Isaac.DrawLine or not KColor then return end
        local color = KColor(red, green, blue, alpha)
        Isaac.DrawLine(a, b, color, color, thickness)
    end
    local spirit = picture.spirit
    if geometry and picture.qReady then
        local opacity = .72 + .18 * math.sin(clock * .16)
        for layer = 1, 2 do
            local center = Vector(x, y - 4 - (layer - 1) * 12)
            local begin = clock * 8 + (layer - 1) * 185
            local previous
            for index = 0, 9 do
                local offset = Vector(25 - (layer - 1) * 3, 0):Rotated(begin + index * 17)
                local nextPoint = center + Vector(offset.X, offset.Y * .40)
                if previous then
                    line(previous, nextPoint, 4, .20, .72, .92, opacity * .52)
                    line(previous, nextPoint, 1, .85, .98, 1, opacity)
                end
                previous = nextPoint
            end
        end
    end
    if geometry and picture.shield then
        local center = Vector(x, y - 12)
        local radius = Vector(18, 0)
        for angle = 0, 315, 45 do
            line(center + radius:Rotated(angle), center + radius:Rotated(angle + 45), 1, .56, .83, 1, .55)
        end
    end
    if spirit then
        local body = point(spirit.anchor)
        local remaining = spirit.remaining
        local pulse = math.max(0, 1 - 4 * remaining) * (.5 - .5 * math.cos(20 * math.pi * remaining))
        if geometry then
            local active = Vector(x, y)
            local delta = active - body
            local side = delta:Normalized():Rotated(90)
            local previous = body
            for i = 1, 12 do
                local t = i / 12
                local wave = math.sin(math.pi * t) * math.sin(8 * t - clock * .18) * 5
                local nextPoint = body + delta * t + side * wave
                line(previous, nextPoint, 3, .63, .09, .23, .35)
                line(previous, nextPoint, 1, 1, .44, .60, .90)
                previous = nextPoint
            end
            if remaining > 0 then
                local center = body + Vector(0, 2)
                for i = 0, 23 do
                    local angle = i * math.pi / 12
                    local nextAngle = (i + 1) * math.pi / 12
                    local a = Vector(16 * math.cos(angle), 6.4 * math.sin(angle))
                    local b = Vector(16 * math.cos(nextAngle), 6.4 * math.sin(nextAngle))
                    line(center + a, center + b, 1, .55, .20, .30, .40)
                    line(center + a * remaining, center + b * remaining, 3, .30, .04, .09, .90)
                    line(center + a * remaining, center + b * remaining,
                        1.5, 1, .62 - .30 * pulse, .75 - .28 * pulse, .95)
                end
            end
        end
        local opacity = (.42 + .49 * remaining) * (1 - .58 * pulse)
        local sprite = player:GetSprite()
        if sprite.Render and sprite.Color then
            local previous = sprite.Color
            sprite.Color = Color(.92 + .08 * pulse, .48 - .15 * pulse, .57 - .10 * pulse, opacity)
            sprite:Render(body, Vector.Zero, Vector.Zero)
            sprite.Color = previous
        else
            Isaac.RenderText('BODY', body.X - 10, body.Y - 9, 1, .57, .64, opacity)
        end
        Isaac.RenderText('SPIRIT', x - 14, y - 31, 1, .52, .67, .90)
        if geometry then
            for _, mark in ipairs(spirit.marks) do
                local enemy = point(mark.position)
                local c = enemy + Vector(0, -25)
                local top, right, bottom, left = c + Vector(0, -6), c + Vector(5, 0),
                    c + Vector(0, 6), c + Vector(-5, 0)
                local lethal = mark.lethal == true
                local green, blue = lethal and .84 or .36, lethal and .55 or .54
                line(top, right, 2, 1, green, blue, .95)
                line(right, bottom, 2, 1, green, blue, .95)
                line(bottom, left, 2, 1, green, blue, .95)
                line(left, top, 2, 1, green, blue, .95)
                line(c + Vector(-2, 2), c + Vector(2, -2), 1, 1, .83, .88, 1)
                if lethal then line(c + Vector(-4, -9), c + Vector(4, -9), 2, 1, .84, .55, 1) end
            end
        end
    end
    for _, event in ipairs(picture.fx) do
        if event.age < .28 and (geometry or event.kind == 'electrocute') then
            local opacity = 1 - event.age / .28
            if event.kind == 'electrocute' then
                local center = point(event.origin) + Vector(0, -10)
                local forks = {center + Vector(5, -24), center + Vector(-3, -13),
                    center + Vector(3, -11), center + Vector(-5, 1)}
                for step = 2, #forks do
                    line(forks[step - 1], forks[step], 4, .95, .26, .47, opacity * .7)
                    line(forks[step - 1], forks[step], 1, 1, .87, .92, opacity)
                end
            elseif event.kind == 'w' and event.footprint then
                local arc = sectorArc(event.footprint, point)
                for i = 2, #arc do
                    line(arc[i - 1], arc[i], 5, .81, .09, .24, opacity * .65)
                    line(arc[i - 1], arc[i], 1, 1, .76, .76, opacity)
                end
            elseif event.kind == 'r' and event.footprint then
                local area = event.footprint
                local side = area.facing:Rotated(90) * area.width
                for _, scale in ipairs({-.85, 0, .85}) do
                    local offset = side * scale
                    line(point(event.origin + offset), point(event.target + offset), 2, .98, .59, .64, opacity)
                end
            elseif event.kind == 'q' or event.kind == 'q3' then
                local start, finish = point(event.origin), point(event.target)
                local side = (finish - start):Normalized():Rotated(90)
                local width = event.kind == 'q3' and 4 or 1
                local r, g, b = table.unpack(Artifacts.bladeHue(event.kind))
                for _, offset in ipairs({-width, width}) do
                    local shift = side * offset
                    line(start + shift, finish + shift, 2, r, g, b, opacity)
                end
            elseif event.kind == 'attack' or event.kind == 'attack2' then
                local area = event.footprint
                if area then
                    local side = area.facing:Rotated(event.kind == 'attack2' and -90 or 90)
                    local start = point(event.origin)
                    local middle = point(event.origin + area.facing * (area.reach * .6) + side * (area.width * .7))
                    local tip = point(event.target)
                    local r, g, b = table.unpack(Artifacts.bladeHue(event.kind))
                    line(start, middle, 2, r, g, b, opacity * .7)
                    line(middle, tip, 2, r, g, b, opacity * .85)
                end
            elseif event.kind == 'cricket' then
                local start = point(event.origin)
                for _, endpoint in ipairs(event.rays or {}) do
                    local tip = point(endpoint)
                    line(start, tip, 3, .84, .29, .63, opacity * .7)
                    line(start, tip, 1, 1, .79, .88, opacity)
                end
            elseif event.kind == 'e_echo' then
                for _, contact in ipairs(event.contacts or {}) do
                    local center = point(contact) + Vector(0, -9)
                    local radius = 3 + event.age * 26
                    line(center + Vector(-radius, radius), center + Vector(radius, -radius), 3, 1, .44, .60, opacity)
                    line(center + Vector(-radius, -radius), center + Vector(radius, radius), 1, 1, .81, .87, opacity)
                end
            end
        end
    end
end

local function drawHeartsteel(room, items)
    if not items or not items.heartsteelTargets or not Isaac.DrawLine or not KColor then return end
    local targets = items.heartsteelTargets()
    if not targets or #targets == 0 then return end
    local shadow = KColor(.13, .045, .065, .94)
    local charging, ready = KColor(.89, .27, .39, .94), KColor(1, .76, .34, 1)
    for _, target in ipairs(targets) do
        local start = screenPoint(room, target.position) + Vector(-7, 6)
        local length = Vector(14, 0)
        Isaac.DrawLine(start, start + length, shadow, shadow, 4)
        local fill = target.fraction >= 1 and ready or charging
        Isaac.DrawLine(start, start + length * target.fraction, fill, fill, 2)
    end
end

local function drawRoomEffects(game, state, player, clock, picture)
    local room = game:GetRoom()
    local pos = Isaac.WorldToScreen(player.Position)
    local x, y = mirrorPosition(room, pos)
    local now = Isaac.GetTime()
    local vfx, model = leased(state, 'vfxReady', now), leased(state, 'modelReady', now)
    if not vfx or not model then
        drawNativeEffects(room, player, picture, x, y, not vfx, clock)
    end
    local phase = Emotes.mastery(state.emotes, clock)
    if phase and not leased(state, 'masteryReady', now) then
        if badge == nil then
            local sprite, loaded = Sprite('gfx/hero_mastery/badge.anm2', true)
            badge = loaded and sprite or false
        end
        local scale, offset = player.SpriteScale, player.SpriteOffset
        local badgeX, badgeY = mirrorPosition(room, offset and pos + offset or pos)
        badgeY = badgeY - masteryAtlasRise - masteryNativeHeight * math.abs(scale and scale.Y or 1)
        local alpha = math.min(1, (phase * 120 + 1) / 6, (1 - phase) * 12)
        if badge then
            badge:SetFrame('Play', math.floor(phase * 120))
            badge.Scale, badge.Color = Vector(.5, .5), Color(1, 1, 1, alpha)
            badge:Render(Vector(badgeX, badgeY))
        else
            Isaac.RenderText('* M *', badgeX - 13, badgeY + 13, 1, .75, .28, alpha)
        end
    end
    if not model then
        local expression = Emotes.action(state.emotes, clock)
        if expression then
            Isaac.RenderText(expression:upper(), x - 15, y - 35, 1, .88, .72, 1)
        end
    end
end

function Yone.init(mod, game, items, inventory, inventoryBounds, display, readHudScale, readR, switchTestHero, isCrafting)
    Display = display
    local state, serial = nil, 0

    local function driver()
        return Yone.player(game)
    end

    mod:AddCallback(ModCallbacks.MC_PRE_NPC_UPDATE, function(_, npc)
        if state then return Combat.preNpcUpdate(state.combat, npc, game:GetFrameCount()) end
    end)
    if ModCallbacks.MC_PRE_NPC_RENDER then
        mod:AddCallback(ModCallbacks.MC_PRE_NPC_RENDER, function(_, npc, offset)
            if state then return Combat.preNpcRender(state.combat, npc, offset, game:GetFrameCount()) end
        end)
    end

    local function sampleInput(room, allowed)
        sampleCommands(state, room, allowed and not upgrading(), readR() == true)
    end

    local function progress()
        return items and items.yoneProgress and items.yoneProgress()
    end

    local function selectionPending()
        local active = progress()
        return active and not active.rune
    end

    function Yone.hudBounds(scale, backpack)
        return HUD.bounds(scale, backpack, progress() ~= nil)
    end

    local function sampleRunePicker(allowed, clicked)
        local left, right, confirm = pressed(Keyboard.KEY_LEFT), pressed(Keyboard.KEY_RIGHT), pressed(Keyboard.KEY_ENTER)
        if allowed then
            local scale = readHudScale and readHudScale() or 1
            local hit = clicked and HUD.runePickerHit(Progress.choices, scale)
            local delta = (right and not state.runeRight and 1 or 0) - (left and not state.runeLeft and 1 or 0)
            state.runeSelection = type(hit) == 'number' and hit
                or (state.runeSelection - 1 + delta) % #Progress.choices + 1
            if hit == 'confirm' or confirm and not state.runeConfirm then
                items.chooseYoneRune(Progress.choices[state.runeSelection].id)
            end
        end
        state.runeLeft, state.runeRight, state.runeConfirm = left, right, confirm
    end

    local function combatHudBounds(player, scale)
        return Yone.hudBounds(scale, inventoryBounds and inventoryBounds(player, scale))
    end

    local function sampleUpgrades(clicked, player)
        local current = progress()
        if not current then return end
        local hit
        if clicked and Progress.points(current) > 0 then
            local scale = readHudScale and readHudScale() or 1
            hit = HUD.upgradeHit(combatHudBounds(player, scale), current)
        end
        local modifier = upgrading()
        for _, key in ipairs({'q', 'w', 'e', 'r'}) do
            local down = modifier and pressed(upgradeKeys[key])
            if hit == key or down and not state.upgradeHeld[key] then Progress.upgrade(current, key) end
            state.upgradeHeld[key] = down
        end
    end

    function Yone.canUseItems(player)
        return state ~= nil and not selectionPending() and canControl(game, state, player)
    end

    function Yone.exportCooldowns(clock)
        if state then return Combat.exportCooldowns(state.combat, clock) end
        return {}
    end

    function Yone.reset(keepCooldowns)
        if not state then return end
        stopSpiritWarning(state)
        Combat.resetRoom(state.combat, game:GetFrameCount())
        if not keepCooldowns then state.combat = Combat.new(items) end
        Emotes.cancel(state.emotes, true)
    end

    function Yone.restoreCooldowns(saved, clock)
        if state then Combat.restoreCooldowns(state.combat, saved, clock) end
    end

    function Yone.reduceCooldowns(fraction, clock)
        if state then Combat.reduceCooldowns(state.combat, fraction, clock) end
    end

    function Yone.reduceUltimateCooldown(fraction, clock)
        if state then Combat.reduceUltimateCooldown(state.combat, fraction, clock) end
    end

    local function stop()
        if state then
            stopSpiritWarning(state)
            Combat.resetRoom(state.combat, game:GetFrameCount(), true)
            packet({version = 1, active = false})
            state = nil
            Display.release('yone')
        end
    end

    local function start(player, continued)
        serial = serial + 1
        Display.acquire('yone')
        state = {id = tostring(Isaac.GetNanoTime()) .. ':yone:' .. serial, room = 1, seq = 0,
            combat = Combat.new(items), emotes = Emotes.new(), commands = {}, held = {},
            continuingRoom = continued == true, runeSelection = 1, runeConfirm = true, leftClick = true, upgradeHeld = {}}
        if Yone.isNative(player) and items and items.startYoneProgress then items.startYoneProgress(continued) end
        if items and items.activate then items.activate(player) end
        if continued and items and items.restoreCombatCooldowns then items.restoreCombatCooldowns() end
        sampleExpressions(state, game:GetFrameCount(), false, false)
        sampleInput(game:GetRoom(), false)
    end

    local function runDebugCommands(player, room, clock)
        local queued = state.debugCommands
        state.debugCommands = nil
        for _, command in ipairs(queued or {}) do
            local operation, arg = command[1], command[2]
            if operation == 'reset' then
                Combat.reduceCooldowns(state.combat, 1, clock)
            elseif operation == 'charge' then
                Combat.chargeQ3(state.combat, clock)
            elseif operation == 'cast' then
                if arg == 'q3' then
                    Combat.chargeQ3(state.combat, clock)
                    arg = 'q'
                end
                if Combat.cast(state.combat, arg, player, Navigation.worldCursor(room), clock, room) then
                    state.debugAnimation = nil
                    stopMoving(state)
                else
                    Isaac.ConsoleOutput('Yone cast unavailable. Check cooldowns or use yonereset.\n')
                end
            elseif arg == 'mastery' then
                if Emotes.trigger(state.emotes, clock, arg) then
                    playMasterySound()
                else
                    Isaac.ConsoleOutput('Yone mastery is on cooldown.\n')
                end
            elseif not Emotes.trigger(state.emotes, clock, arg) then
                state.debugAnimation = {clip = arg, start = clock, finish = clock + 30}
            end
        end
    end

    mod:AddCallback(ModCallbacks.MC_POST_GAME_STARTED, function(_, continued)
        testMode = false
        stop()
        local player = driver()
        if player then start(player, continued) end
    end)
    mod:AddCallback(ModCallbacks.MC_PRE_GAME_EXIT, function()
        testMode = false
        stop()
    end)
    mod:AddCallback(ModCallbacks.MC_PRE_MOD_UNLOAD, function(_, unloading)
        if unloading == mod then
            testMode = false
            stop()
        end
    end)

    local enterRoom
    mod:AddCallback(ModCallbacks.MC_POST_UPDATE, function()
        local player = driver()
        if not player then
            -- A missing player or a temporarily unavailable run is not a
            -- character switch. Floor rebinding can outlast any wall timer.
            if state and not state.leaving and not state.floorRebinding and Isaac.IsInGame()
                and game:GetNumPlayers() > 0 and Isaac.GetPlayer(0) then stop() end
            return
        end
        if not state then start(player) end
        local room, clock = game:GetRoom(), game:GetFrameCount()
        -- A floor arrival may be observed without POST_NEW_LEVEL (or that
        -- callback can arrive late). Never let the departure flag itself
        -- prevent recovery once the new room is playable.
        local roomChanged = state.departureRoomSeed ~= nil and room:GetSpawnSeed() ~= state.departureRoomSeed
        local arrived = state.floorRoomArrived or roomChanged or state.floorLevelArrived
        if (state.floorRebinding and arrived) or (state.leaving and roomChanged) then
            if player.ControlsEnabled ~= false and not obscured(game, state, player, true) then
                if clock ~= state.floorReadyFrame then
                    state.floorReadyFrame = clock
                    state.floorReadyTicks = (state.floorReadyTicks or 0) + 1
                end
                -- The engine can retain its transition mode after the floor
                -- arrives. Require several unblocked gameplay frames before
                -- ignoring it, and only for the room that just arrived.
                local transitioning = roomTransition(state)
                local requiredTicks = transitioning and 6 or (state.leaving and 2 or 1)
                if state.floorReadyTicks >= requiredTicks then
                    if state.leaving then
                        if state.floorLevelArrived then
                            state.leaving, state.departureRoomSeed = nil, nil
                        else
                            enterRoom()
                            state.floorRecovered = state.floorRebinding or nil
                        end
                    end
                    state.floorPending, state.floorRoomArrived, state.floorLevelArrived = nil, nil, nil
                    state.floorReadyTicks, state.floorReadyFrame = nil, nil
                    state.floorArrivalSeed = nil
                    state.staleTransitionMode = transitioning or nil
                end
            else
                state.floorReadyTicks, state.floorReadyFrame = nil, nil
            end
        end
        if state.staleTransitionMode and RoomTransition.GetTransitionMode() == 0 then
            state.staleTransitionMode = nil
        end
        if items and items.applyCooldownCheckpoint then items.applyCooldownCheckpoint(clock) end
        local shopping = isCrafting and isCrafting()
        local allowed = canControl(game, state, player) and not shopping
        local mouse = Input.IsMouseBtnPressed(0)
        local clicked = mouse and not state.leftClick
        state.leftClick = mouse
        if selectionPending() then
            sampleInput(room, false)
            sampleRunePicker(allowed, clicked)
            return
        end
        sampleInput(room, allowed)
        if not allowed then
            if shopping then stopMoving(state) end
            sampleExpressions(state, clock, false, player:IsDead())
            if player:IsDead() then
                stopSpiritWarning(state)
                Combat.resetRoom(state.combat, clock)
                Emotes.cancel(state.emotes, true)
            end
            return
        end
        if not state.floorPending and not state.floorLevelArrived then state.floorRebinding = nil end
        sampleUpgrades(clicked, player)

        if inventory then inventory.update(player, clock) end
        if items and items.update then items.update(player, clock) end
        if items and items.claimCombatRoomReset and items.claimCombatRoomReset() and not state.continuingRoom then
            Combat.reduceCooldowns(state.combat, 1, clock)
        end
        local enemies = Isaac.GetRoomEntities()
        Combat.update(state.combat, room, player, enemies, clock)
        if state.debugCommands then runDebugCommands(player, room, clock) end
        if state.qAfterE and not state.combat.pending then
            local aim = player.Position + state.qAfterE
            if Combat.cast(state.combat, 'q', player, aim, clock, room) then stopMoving(state) end
            state.qAfterE = nil
        end
        for _, command in ipairs(state.commands) do
            local kind, aim = command.kind, command.aim
            if kind == 'stop' then
                stopMoving(state)
            elseif kind == 'mouse' then
                stopMoving(state)
                state.target = targetAt(enemies, aim)
                if not state.target then setGoal(state, room, aim) end
            elseif kind == 'q' and state.combat.pending and state.combat.pending.kind == 'e' then
                local heading = aim - player.Position
                state.qAfterE = state.qAfterE or (heading:Length() > .01 and heading or state.combat.pending.facing)
            elseif Combat.cast(state.combat, kind, player, aim, clock, room) then
                stopMoving(state)
            end
        end
        state.commands = {}
        -- Resolve zero-windup recasts on the press, after issuing the action.
        Combat.update(state.combat, room, player, enemies, clock)
        updateSpiritWarning(state, clock)
        local action = Combat.presentation(state.combat, clock)
        local windup = Combat.activeFootprint(state.combat, player, room)
        if action == 'r' or state.combat.returning or windup then
            state.intent = nil
            player.Velocity = Vector.Zero
        else
            updateMovement(state, room, player, clock)
        end
        if not action and state.intent then state.combat.face = state.intent end
        local moving = state.intent ~= nil or player.Velocity:Length() > .6
        sampleExpressions(state, clock, true, action ~= nil or moving)
    end)

    mod:AddCallback(ModCallbacks.MC_INPUT_ACTION, function(_, entity, hook, action)
        local direction, key = axes[action], rebound[action]
        local shopping = isCrafting and isCrafting()
        local pickerAction = (action == ButtonAction.ACTION_ITEM or action == ButtonAction.ACTION_DROP)
            and (selectionPending() or shopping)
        if not direction and not key and not blocked[action] and not pickerAction then return end
        local player = state and driver()
        local owner = entity and entity:ToPlayer()
        if not player or entity and (not owner or owner.Index ~= player.Index)
            or (player.ControllerIndex or 0) ~= 0 then return end
        local value = 0
        local allowed = canControl(game, state, player) and not selectionPending() and not shopping
        if action == ButtonAction.ACTION_PILLCARD then
            local clock = game:GetFrameCount()
            local combatAction = Combat.presentation(state.combat, clock)
            sampleExpressions(state, clock, allowed, combatAction ~= nil or player.Velocity:Length() > .6)
        end
        if allowed then
            if key and not (action == ButtonAction.ACTION_PILLCARD and Emotes.blocksPocket(state.emotes)) then
                local down
                if hook == InputHook.IS_ACTION_TRIGGERED then down = Input.IsButtonTriggered(key, 0)
                else down = pressed(key) end
                value = down and 1 or 0
            elseif direction and state.intent then
                value = math.max(0, state.intent:Dot(direction))
            end
        end
        if hook == InputHook.GET_ACTION_VALUE then return value end
        return value > 0
    end)

    mod:AddCallback(ModCallbacks.MC_PRE_PLAYER_RENDER, function(_, player)
        local current = state and driver()
        if not current or current.Index ~= player.Index then return end
        local now = Isaac.GetTime()
        local _, _, display = Display.sample()
        if obscured(game, state, player) or display.mode == 'exclusive' then state.ackAt = nil; return end
        readAck(state, now, display)
        if leased(state, 'modelReady', now) then return false end
    end)

    mod:AddCallback(ModCallbacks.MC_POST_RENDER, function()
        local player = state and driver()
        if not player then return end
        local clock = game:GetFrameCount()
        local selectable = canControl(game, state, player)
        local picking = selectionPending()
        local allowed = selectable and not picking
        local scale = readHudScale and readHudScale() or 1
        if selectable and picking then HUD.renderRunePicker(Progress.choices, state.runeSelection, scale) end
        sampleInput(game:GetRoom(), allowed)
        local action = Combat.presentation(state.combat, clock)
        sampleExpressions(state, clock, allowed and not (isCrafting and isCrafting()), action ~= nil or player.Velocity:Length() > .6)
        local picture = allowed and Combat.visual(state.combat, clock) or nil
        if picture then
            local room, activeProgress = game:GetRoom(), progress()
            drawAim(room, state.combat, player, clock, state.aimAbility)
            drawRoomEffects(game, state, player, clock, picture)
            drawHeartsteel(room, items)
            HUD.renderPlayerRune(screenPoint(room, player.Position), activeProgress, clock)
            local bounds = combatHudBounds(player, scale)
            HUD.render(bounds, state.combat, clock, state.aimAbility, picture,
                Combat.hudStats(state.combat, player, clock), aimColors, activeProgress)
        end
        emit(game, state, player, false, picture)
    end)

    mod:AddCallback(ModCallbacks.MC_ENTITY_TAKE_DMG, function(_, target, _, flags, source, _, extraSource)
        local player = state and driver()
        local attacker = source and source.Entity
        if not player or target.Type ~= EntityType.ENTITY_PLAYER or target.Index ~= player.Index then return end
        if flags & (DamageFlag.DAMAGE_FAKE or 0) ~= 0 then return end
        local bypass = (DamageFlag.DAMAGE_IV_BAG or 0) | (DamageFlag.DAMAGE_CHEST or 0)
            | (DamageFlag.DAMAGE_CURSED_DOOR or 0) | (DamageFlag.DAMAGE_INVINCIBLE or 0)
        local clock = game:GetFrameCount()
        if flags & bypass == 0 and (Combat.invulnerable(state.combat, clock)
            or Combat.airborneDamage(state.combat, attacker, extraSource and extraSource.Entity, clock)) then
            return false
        end
        if not attacker or (attacker.Type ~= EntityType.ENTITY_PROJECTILE and not Combat.hostile(attacker)) then return end
        if Combat.absorb(state.combat, clock, player.Position) then
            player:SetMinDamageCooldown(15)
            return false
        end
    end)
    mod:AddCallback(ModCallbacks.MC_POST_ENTITY_TAKE_DMG, function(_, target, amount, _, source)
        local player = state and driver()
        if not player then return end
        if target.Type == EntityType.ENTITY_PLAYER and target.Index == player.Index then
            state.hurtUntil = game:GetFrameCount() + 6
            Emotes.cancel(state.emotes, false)
        else
            Combat.confirmDamage(state.combat, target, amount, source)
        end
    end)

    local function roomSeed()
        local room = game:GetRoom()
        return room.GetSpawnSeed and room:GetSpawnSeed() or nil
    end

    local function isLateDeparture()
        -- The engine can report an old exit after loading the destination.
        return state.floorArrivalSeed ~= nil and roomSeed() == state.floorArrivalSeed
    end

    local function beginDeparture(player)
        if state.leaving then return end
        state.staleTransitionMode, state.floorRecovered, state.floorArrivalSeed = nil, nil, nil
        state.leaving, state.ackAt = true, nil
        state.departureRoomSeed = roomSeed()
        state.debugCommands, state.debugAnimation = nil, nil
        stopSpiritWarning(state)
        stopMoving(state)
        sampleInput(game:GetRoom(), false)
        Combat.resetRoom(state.combat, game:GetFrameCount(), true)
        Emotes.cancel(state.emotes, true)
        emit(game, state, player, true)
    end

    mod:AddCallback(ModCallbacks.MC_PRE_CHANGE_ROOM, function()
        local player = state and driver()
        if player and not isLateDeparture() then beginDeparture(player) end
    end)

    mod:AddCallback(ModCallbacks.MC_PRE_ROOM_EXIT, function(_, player, newLevel)
        if state and newLevel and Yone.is(player) and not isLateDeparture() then
            state.floorPending = true
            state.floorRebinding = true
            beginDeparture(player)
        end
    end)

    enterRoom = function()
        stopSpiritWarning(state)
        state.room = state.room + 1
        state.leaving, state.ackAt, state.emitAt, state.pollAt = nil, nil, nil, nil
        state.departureRoomSeed, state.floorRoomArrived, state.floorReadyTicks = nil, nil, nil
        state.floorArrivalSeed = nil
        state.staleTransitionMode, state.floorReadyFrame, state.floorRecovered = nil, nil, nil
        state.coverFrame, state.hurtUntil = nil, nil
        state.continuingRoom = nil
        state.debugCommands, state.debugAnimation = nil, nil
        sampleInput(game:GetRoom(), false)
        stopMoving(state)
        Combat.resetRoom(state.combat, game:GetFrameCount())
        Emotes.cancel(state.emotes, true)
    end

    mod:AddCallback(ModCallbacks.MC_POST_NEW_ROOM, function()
        -- On a floor change this arrives before POST_NEW_LEVEL. Keep the old
        -- scene hidden while the new player and room are being bound.
        if not state then return end
        if state.floorPending then
            state.floorRoomArrived = true
            state.floorArrivalSeed = roomSeed()
        else
            enterRoom()
        end
    end)

    mod:AddCallback(ModCallbacks.MC_POST_NEW_LEVEL, function()
        if not state then return end
        if state.floorRecovered then return end
        if state.floorPending or state.leaving then enterRoom() end
        state.floorPending, state.floorRoomArrived, state.floorReadyTicks, state.coverFrame = nil, nil, nil, nil
        state.floorRebinding, state.floorLevelArrived = true, true
        state.floorArrivalSeed = roomSeed()
    end)

    Debug.init(mod, function(enable)
        if not enable then
            if testMode then
                testMode = false
                stop()
                switchTestHero(false)
            end
            return 'Yone test mode off.'
        end
        if not Isaac.IsInGame() or game:GetNumPlayers() ~= 1 or not Isaac.GetPlayer(0) then
            return 'Start a single-player run first.'
        end
        local player = Isaac.GetPlayer(0)
        if not Yone.isNative(player) and not testMode then
            testMode = true
            switchTestHero(true)
        end
        if not state then
            start(player)
        elseif state.leaving or state.floorPending then
            state.floorPending, state.floorRebinding = nil, nil
            enterRoom()
        else
            state.ackAt, state.pollAt, state.emitAt = nil, nil, nil
        end
        return testMode and 'Yone testing enabled. Close the console.' or 'Yone reconnected. Close the console.'
    end, function(operation, arg)
        if not (driver() and state) then return 'Select Yone or run yonetest first.' end
        state.debugCommands = state.debugCommands or {}
        if #state.debugCommands >= 12 then return 'Close the console to run queued Yone commands.' end
        state.debugCommands[#state.debugCommands + 1] = {operation, arg}
        return 'Close the console to run the command.'
    end, function()
        local player = driver()
        if not player or not state then return 'Select Yone or run yonetest first.' end
        local remaining = Combat.exportCooldowns(state.combat, game:GetFrameCount())
        return ('Yone %s | next blade %s | damage %.2f | Q stacks %d | Q %.1fs W %.1fs E %.1fs R %.1fs')
            :format(testMode and 'test' or 'selected', state.combat.secondBlade and 'Azakana' or 'steel',
                player.Damage, state.combat.qStacks, (remaining.q or 0) / fps, (remaining.w or 0) / fps,
                (remaining.e or 0) / fps, (remaining.r or 0) / fps)
    end)
    local function hideDuringCutscene()
        local player = state and driver()
        if not player then return end
        -- The game clock is held during the nightmare. A final render can
        -- arrive after level entry, but must not hide the first gameplay tick.
        state.coverFrame, state.ackAt = game:GetFrameCount(), nil
        emit(game, state, player)
    end
    mod:AddCallback(ModCallbacks.MC_POST_NIGHTMARE_SCENE_SHOW, hideDuringCutscene)
    mod:AddCallback(ModCallbacks.MC_POST_NIGHTMARE_SCENE_RENDER, hideDuringCutscene)
end

return Yone
