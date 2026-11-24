"""Verify roster selection and the real Yone callback/renderer boundary."""

from pathlib import Path
import sys
import xml.etree.ElementTree as ET

from check_samira_navigation import mock_prelude
from lupa.lua54 import LuaRuntime


ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / "src/samira-testroom/mod"


def main():
    roster = ET.parse(MOD / "content/players.xml").getroot()
    assert [player.get("name") for player in roster] == ["Samira", "Yone", "Miss Fortune"]
    for attribute in ("nameimage", "portrait"):
        path = MOD / "resources" / roster.get(f"{attribute}root") / roster[1].get(attribute)
        assert path.is_file(), path
    lua = LuaRuntime()
    lua.globals().sourceFiles = lua.table_from({
        file.stem: file.read_text(encoding="utf-8") for file in MOD.glob("*.lua")
    })
    prelude = mock_prelude().replace("include('main')", """
local originalInclude = include
function include(name)
    local module = originalInclude(name)
    if name == 'samira_inventory_hud' then
        module.bounds = assert(load(sourceFiles[name], '@' .. name .. '.lua'))().bounds
    end
    return module
end
include('main')
""", 1)
    lua.execute(prelude + r"""
start()
local kind = 130
Options.Fullscreen, Options.UseBorderlessFullscreen = false, false
Isaac.GetPlayerTypeByName = function(name)
    assert(name == 'Yone' or name == 'Miss Fortune')
    return name == 'Yone' and 130 or 131
end
function player:GetPlayerType() return kind end
function player:IsFlying() return self.CanFly == true end
function player:GetTrinket(slot) return slot == 0 and 1 or 0 end
local itemUpdates, lastCast = 0, nil
noItems.update = function(owner) assert(owner == player); itemUpdates = itemUpdates + 1 end
noItems.onCast = function(owner, skill) assert(owner == player); lastCast = skill end
Isaac.RenderText = function() end
Isaac.RenderScaledText = function() end
Isaac.GetTextWidth = function(text) return #text * 6 end
Isaac.DrawLine = function() end
KColor = Color
local draws, progressionDraws = {}, {}
local function captureHud(cursor)
    local originalRender, originalScaled, originalLine = Isaac.RenderText, Isaac.RenderScaledText, Isaac.DrawLine
    local originalCursor = input.cursor
    if cursor then input.cursor = cursor end
    local text = {pips = 0, ring = 0, qRing = 0, icons = {}, statMarks = {}, shield = 0, upgradeArrows = 0}
    text.conquerorPips, text.tempoPips, text.electroBolt, text.electroFill = 0, 0, 0, 0
    draws = text.icons
    text.art = {}
    progressionDraws = text.art
    Isaac.RenderText = function(label, x, y, r, g, b, a)
        text[label] = {x = x, y = y, scale = 1, color = {r, g, b, a}}
    end
    Isaac.RenderScaledText = function(label, x, y, sx, sy, r, g, b, a)
        assert(sx == sy)
        text[label] = {x = x, y = y, scale = sx, color = {r, g, b, a}}
    end
    Isaac.DrawLine = function(a, b, color, endColor, thickness)
        originalLine(a, b, color, endColor, thickness)
        if thickness == 3 and (color[1] == 1 and color[2] == .78 or color[1] == .22 and color[2] == .20)
            then text.pips = text.pips + 1 end
        if color[1] == 1 and color[2] == .38 then text.ring = text.ring + a:Distance(b) end
        if color[1] == .60 and color[2] == .93
            and text.icons[1] and b.Y <= text.icons[1].y + text.icons[1].size + thickness then
            text.qRing = text.qRing + a:Distance(b)
        end
        if color[1] == .74 and color[2] == .65 or color[1] == .97 and color[2] == .78 then
            text.statMarks[#text.statMarks + 1] = a
        end
        if color[1] == .55 and color[2] == .87 then
            local w = assert(text.icons[2], 'shield marker drawn away from W')
            local s = w.size / 26
            assert(a.X >= w.x + 17 * s and a.X <= w.x + w.size and a.Y >= w.y + 21 * s and a.Y <= w.y + 30 * s,
                'shield marker fell outside the W corner badge')
            text.shield = text.shield + 1
        end
        if color[1] == .76 and color[2] == .57 and a.Y ~= b.Y then
            text.upgradeArrows = text.upgradeArrows + 1
        end
        if color[1] == 1 and color[2] == .73 then text.conquerorPips = text.conquerorPips + 1 end
        if color[1] == .47 and color[2] == .85 then text.tempoPips = text.tempoPips + 1 end
        if color[1] == 1 and color[2] == .40 and a.Y ~= b.Y then text.electroBolt = text.electroBolt + 1 end
        if color[1] == .54 and color[2] == .30 then text.electroFill = b.X - a.X end
    end
    event('POST_RENDER')
    Isaac.RenderText, Isaac.RenderScaledText, Isaac.DrawLine = originalRender, originalScaled, originalLine
    input.cursor = originalCursor
    draws = {}
    progressionDraws = {}
    local previousX = -1
    for _, key in ipairs({'Q', 'W', 'E', 'R'}) do
        local slot = assert(text[key], 'native HUD did not draw a separate ' .. key .. ' slot')
        assert(slot.x > previousX and slot.x + 6 * slot.scale <= Isaac.GetScreenWidth(), 'ability slot fell outside the row')
        assert(slot.y == text.Q.y and slot.y >= 0 and slot.y + 8 * slot.scale <= Isaac.GetScreenHeight(),
            'ability slot fell outside the viewport')
        previousX = slot.x
    end
    assert(#text.icons == 4, 'the HUD did not draw four native ability icons')
    for _, icon in ipairs(text.icons) do
        assert(icon.x >= 0 and icon.x + icon.size <= Isaac.GetScreenWidth()
            and icon.y >= 0 and icon.y + icon.size <= Isaac.GetScreenHeight(), 'ability image was clipped')
    end
    return text
end

local function checkStatGrid(hud, values)
    local q = hud.icons[1]
    local s = q.size / 26
    local marks = {}
    for _, start in ipairs(hud.statMarks) do
        local col = math.floor((start.X - (q.x - 71 * s)) / (33 * s))
        local row = math.floor((start.Y - (q.y - .5 * s)) / (10 * s))
        assert(col >= 0 and col <= 1 and row >= 0 and row <= 2, 'stat icon fell outside the side panel')
        marks[row * 2 + col + 1] = true
    end
    for i, label in ipairs(values) do
        local value = assert(hud[label], 'missing Yone stat value ' .. label)
        local col, row = (i - 1) % 2, math.floor((i - 1) / 2)
        assert(marks[i], 'missing icon for stat cell ' .. i)
        assert(math.abs(value.y - (q.y + (.6 + row * 10) * s)) < .001, 'stat value is on the wrong row')
        local right = value.x + Isaac.GetTextWidth(label) * value.scale
        assert(value.x >= right - 20 * s - .001 and value.x >= 0
            and math.abs(right - (q.x - (41 - col * 33) * s)) < .001,
            'stat value fell outside its cell')
    end
end
local function statusOver(hud, label, index)
    local status, icon = hud[label], hud.icons[index]
    return status and status.x >= icon.x and status.x + Isaac.GetTextWidth(label) * status.scale <= icon.x + icon.size
end
local function sameSlots(before, after)
    for _, key in ipairs({'Q', 'W', 'E', 'R'}) do
        assert(before[key].x == after[key].x and before[key].y == after[key].y, key .. ' slot moved')
    end
end
local pressed = Input.IsButtonPressed
Input.IsButtonPressed = function(key, ...) return key == input.ctrl or pressed(key, ...) end
local nativeShows, nativeBadge = 0, nil
Sprite = function(path)
    if path == 'gfx/yone/ability_icons.anm2' then
        return {
            SetFrame=function(self, animation, frame) assert(frame == 0); self.animation = animation end,
            Render=function(self, pos)
                draws[#draws + 1] = {name = self.animation, x = pos.X, y = pos.Y, size = self.Scale.X * 64}
            end,
        }, true
    end
    if path == 'gfx/yone/progression_hud.anm2' then
        return {
            SetFrame = function(self, animation, frame) assert(frame == 0); self.animation = animation end,
            Render = function(self, pos)
                local positions = progressionDraws[self.animation] or {}
                positions[#positions + 1] = pos
                progressionDraws[self.animation] = positions
            end,
        }, true
    end
    assert(path == 'gfx/hero_mastery/badge.anm2')
    return {
        SetFrame=function() end, Render=function(_, pos)
            nativeShows, nativeBadge = nativeShows + 1, pos
        end,
    }, true
end
event('POST_GAME_STARTED', false)
tick()
assert(packet.active and packet.hero == 'yone' and packet.clip == 'idle')
assert(Options.UseBorderlessFullscreen and packet.display.mode == 'windowed')
assert(itemDriver() == player and itemUpdates > 0, 'ordinary Yone run did not bind shared items')
assert(controlsOwner() == player, 'Yone could not open the shared F9 settings')
local glyphLines = 0
Isaac.DrawLine = function() glyphLines = glyphLines + 1 end
local readyHud = captureHud(Vector(0, 0))
assert(glyphLines >= 8, 'ability panel did not draw its plate')
assert(readyHud.icons[1].name == 'Q' and readyHud.icons[2].name == 'W'
    and readyHud.icons[3].name == 'E' and readyHud.icons[4].name == 'R' and readyHud.pips == 0)
checkStatGrid(readyHud, {'4.00', '0%', '2.00', '0', '1.00', '104'})
assert(not readyHud.CRIT and not readyHud.DMG and not readyHud['Critical strike chance'] and readyHud.shield == 0,
    'idle HUD leaked labels or a W shield indicator')
noItems.combatStats = function(owner)
    assert(owner == player)
    return .52, 17
end
player.MaxFireDelay, player.Damage, player.MoveSpeed, player.TearRange = 5, 7.25, 1.23, 365
local boosted = captureHud(Vector(0, 0))
checkStatGrid(boosted, {'7.25', '52%', '3.33', '17', '1.23', '116'})
assert(not boosted['0%'] and boosted['52%'].color[1] > readyHud['0%'].color[1],
    'current critical chance did not update or pick up its accent')
noItems.combatStats = nil
player.MaxFireDelay, player.Damage, player.MoveSpeed, player.TearRange = 9, 4, 1, 250
Isaac.DrawLine = function() end
do
    local width, height = Isaac.GetScreenWidth, Isaac.GetScreenHeight
    local inventoryBounds = include('samira_inventory_hud').bounds
    local values = {'4.00', '0%', '2.00', '0', '1.00', '104'}
    local statLabels = {'Attack damage', 'Critical strike chance', 'Attacks per second',
        'Ability haste', 'Movement speed', 'Attack range'}
    local function checkHover(hud, i)
        local value, label = hud[values[i]], statLabels[i]
        local tooltip = captureHud(Vector(value.x + 1, value.y + 2))[label]
        assert(tooltip, 'wrong tooltip for ' .. label)
        assert(tooltip.x >= 3 and tooltip.x + Isaac.GetTextWidth(label) * tooltip.scale <= Isaac.GetScreenWidth() - 3
            and tooltip.y >= 0 and tooltip.y + 8 * tooltip.scale < hud.icons[1].y - 5 * hud.icons[1].size / 26,
            'stat tooltip overlapped the viewport edge or ability panel')
    end
    local function checkBackpackClearance(hud, wraps)
        local backpack, q = inventoryBounds(player, hudScale), hud.icons[1]
        local s = q.size / 26
        if wraps then
            assert(q.y + 34 * s <= backpack.y - 17 * backpack.scale - 3,
                'ability panel collided with backpack drop hint while wrapped')
        else
            assert(q.x - 76 * s >= backpack.x + backpack.width + 6 and q.y + 34 * s >= backpack.y,
                'ability panel did not clear the backpack beside it')
        end
    end
    checkBackpackClearance(readyHud, true)
    for i = 1, #values do checkHover(readyHud, i) end
    hudScale = .75
    noItems.combatStats = function() return 1, 17.5 end
    local saturated = captureHud(Vector(0, 0))
    checkStatGrid(saturated, {'4.00', '100%', '2.00', '17.5', '1.00', '104'})
    assert(saturated.icons[1].size == 19.5 and saturated['100%'].scale > .5)
    noItems.combatStats, hudScale = nil, 1
    Isaac.GetScreenWidth, Isaac.GetScreenHeight = function() return 688 end, function() return 288 end
    local wideHud = captureHud()
    checkBackpackClearance(wideHud, false)
    hudScale = 1.5
    local largeHud = captureHud()
    checkStatGrid(largeHud, values)
    checkBackpackClearance(largeHud, false)
    assert(largeHud.icons[1].size == 39 and largeHud.Q.scale == .94 * 1.5)
    mirror = true
    checkHover(largeHud, 2)
    mirror = false
    Isaac.GetScreenWidth = function() return 480 end
    Options.Fullscreen = true
    largeHud = captureHud()
    checkBackpackClearance(largeHud, true)
    checkHover(largeHud, 6)
    Options.Fullscreen, hudScale = false, 1
    Isaac.GetScreenWidth, Isaac.GetScreenHeight = width, height
end
local marker = Vector(75, 65)
local function checkHeartsteelMarker(fraction, reflected, green)
    local originalLine = Isaac.DrawLine
    local filled = 0
    mirror = reflected
    noItems.heartsteelTargets = function() return {{position = marker, fraction = fraction}} end
    Isaac.DrawLine = function(a, b, color, _, thickness)
        if thickness == 2 and color[2] == green then
            local x = reflected and Isaac.GetScreenWidth() - marker.X * projection or marker.X * projection
            assert(math.abs(a.X - (x - 7)) < .001 and math.abs(a.Y - (marker.Y * projection + 6)) < .001)
            assert(math.abs((b.X - a.X) - 14 * fraction) < .001)
            filled = filled + 1
        end
    end
    event('POST_RENDER')
    assert(filled == 1, 'Heartsteel did not draw one progress indicator under the target')
    mirror, noItems.heartsteelTargets, Isaac.DrawLine = false, nil, originalLine
end
checkHeartsteelMarker(.5, false, .27)
checkHeartsteelMarker(1, true, .76)
local session = packet.session
assert(callAction('ACTION_SHOOTRIGHT') == 0)
assert(callAction('ACTION_RESTART', 'IS_ACTION_PRESSED') == nil, 'unheld R blocked restart')
input.key = 'KEY_R'
assert(callAction('ACTION_RESTART', 'IS_ACTION_PRESSED') == false, 'held R allowed restart')
assert(callAction('ACTION_RESTART', 'IS_ACTION_PRESSED', makeEntity('enemy', 0, 0, 71)) == false)
player.ControllerIndex = 1
assert(callAction('ACTION_RESTART', 'IS_ACTION_PRESSED', player) == false)
player.ControllerIndex = 0
kind = 999
assert(callAction('ACTION_RESTART', 'IS_ACTION_PRESSED') == nil, 'other character restart blocked')
kind, input.key = 130, nil
assert(callAction('ACTION_LEFT') == 0)
tick('KEY_RIGHT')
assert(callAction('ACTION_RIGHT') > .9, 'arrow did not start movement')
tick()
assert(callAction('ACTION_RIGHT') == 0, 'movement continued after arrow release')
local qTarget = makeEntity('enemy', player.Position.X + 25, player.Position.Y, 11)
entities = {qTarget}
local function castKey(key)
    tick(key)
    tick()
end
local rangeLines = 0
local oldDrawLine = Isaac.DrawLine
Isaac.DrawLine = function(a, b, ...)
    if a.Y < 65 and b.Y < 65 then rangeLines = rangeLines + 1 end
end
tick('KEY_Q', false, player.Position + Vector(100, -80))
assert(lastCast == nil, 'holding Q should show its hitbox before casting')
assert(rangeLines >= 4, 'holding Q did not draw its world-space range')
Isaac.DrawLine = oldDrawLine
tick(nil, false, player.Position + Vector(100, 0))
assert(packet.clip == 'q' and packet.hero == 'yone')
assert(packet.yoneTiming.hit == 6 and packet.yoneTiming.length == 16, 'Q timing was not exported to Companion')
assert(lastCast == 'q', 'Yone ability did not reach item cast hooks')
local locked = {}
local originalLine = Isaac.DrawLine
Isaac.DrawLine = function(a, b, color)
    if color and color[1] == .60 and color[2] == .93 and color[3] == 1 then
        locked[#locked + 1] = {a.X, a.Y, b.X, b.Y}
    end
end
renderOnly(nil, false, player.Position + Vector(0, -100))
assert(#locked > 4, 'committed Q lost its own colored footprint')
local firstLocked = locked
locked = {}
renderOnly(nil, false, player.Position + Vector(-100, 0))
assert(#locked == #firstLocked, 'committed footprint changed after cursor movement')
for i, line in ipairs(locked) do
    for j = 1, 4 do assert(math.abs(line[j] - firstLocked[i][j]) < .001,
        'committed footprint followed the cursor') end
end
Isaac.DrawLine = originalLine
local committedPosition = player.Position
tick('KEY_RIGHT', false, player.Position + Vector(0, -100))
assert(callAction('ACTION_RIGHT') == 0 and player.Position:Distance(committedPosition) < .001,
    'movement resumed during a committed Q windup')
for _ = 1, 7 do tick() end
local stackedHud = captureHud()
sameSlots(readyHud, stackedHud)
assert(stackedHud.pips == 0 and stackedHud.qRing == 0 and statusOver(stackedHud, '2s', 1),
    'Q one-stack HUD had charge markers or lost its cooldown')
assert(stackedHud.Q.color[1] < readyHud.Q.color[1], 'cooldown did not dim the ability key')
for _ = 1, 54 do tick() end
castKey('KEY_Q')
for _ = 1, 7 do tick() end
local doubleStackHud = captureHud()
sameSlots(readyHud, doubleStackHud)
assert(doubleStackHud.pips == 0 and doubleStackHud.qRing > 100 and doubleStackHud.icons[1].name == 'Q3',
    'Q3 did not replace the pips with its duration outline')
assert(packet.yone.qReady == true, 'charged Q state was omitted from the visual packet')
entities = {}
for _ = 1, 30 do tick() end
local fadingQ = captureHud()
assert(fadingQ.qRing > 0 and fadingQ.qRing < doubleStackHud.qRing, 'Q3 duration outline did not shrink')
for _ = 1, 24 do tick() end
DamageFlag = {DAMAGE_FAKE = 1, DAMAGE_IV_BAG = 2}
local dashAttacker = makeEntity('enemy', player.Position.X + 25, player.Position.Y, 89)
qTarget.Position = player.Position + Vector(25, 0)
entities = {qTarget}
local qAim = player.Position + Vector(120, 0)
tick('KEY_Q', false, qAim)
tick(nil, false, qAim)
assert(packet.kind == 'q3', 'charged Q did not begin dash')
for _ = 1, 7 do tick() end
assert(event('ENTITY_TAKE_DMG', player, 1, 0, EntityRef(dashAttacker)) == false,
    'Q3 did not block hostile damage on dash')
assert(event('ENTITY_TAKE_DMG', player, 1, 0, nil) == false, 'Q3 did not block environmental damage')
assert(event('ENTITY_TAKE_DMG', player, 1, DamageFlag.DAMAGE_FAKE, EntityRef(dashAttacker)) == nil,
    'Q3 blocked fake damage')
assert(event('ENTITY_TAKE_DMG', player, 1, DamageFlag.DAMAGE_IV_BAG, EntityRef(player)) == nil,
    'Q3 blocked payment or self-inflicted damage')
for _ = 1, 5 do tick() end
assert(event('ENTITY_TAKE_DMG', player, 1, 0, EntityRef(dashAttacker)) == false,
    'Q3 lost its first extra frame of immunity after the dash')
tick()
assert(event('ENTITY_TAKE_DMG', player, 1, 0, EntityRef(dashAttacker)) == false,
    'Q3 lost its second extra frame of immunity after the dash')
tick()
assert(event('ENTITY_TAKE_DMG', player, 1, 0, EntityRef(dashAttacker)) == nil,
    'Q3 invulnerability lasted past the landing window')
assert(event('ENTITY_TAKE_DMG', player, 1, 0, EntityRef(qTarget)) == false,
    'lifted target dealt contact damage after the dash protection ended')
local liftedShot = makeEntity(EntityType.ENTITY_PROJECTILE, player.Position.X, player.Position.Y, 92)
liftedShot.SpawnerEntity = qTarget
local liftedLaser = makeEntity('ENTITY_LASER', player.Position.X, player.Position.Y, 93)
liftedLaser.Parent = qTarget
assert(event('ENTITY_TAKE_DMG', player, 1, 0, EntityRef(liftedShot)) == false,
    'lifted target projectile dealt damage after the dash protection ended')
assert(event('ENTITY_TAKE_DMG', player, 1, 0, nil, 0, EntityRef(liftedLaser)) == false,
    'damage through REPENTOGON ExtraSource ignored knockup')
assert(event('ENTITY_TAKE_DMG', player, 1, 0, nil) == nil, 'knockup blocked unrelated environmental damage')
for _ = 1, 22 do tick() end
assert(event('ENTITY_TAKE_DMG', player, 1, 0, EntityRef(qTarget)) == false,
    'knockup protection expired before one second')
tick()
assert(event('ENTITY_TAKE_DMG', player, 1, 0, EntityRef(qTarget)) == nil
    and event('ENTITY_TAKE_DMG', player, 1, 0, EntityRef(liftedShot)) == nil,
    'knockup protection outlasted landing')
entities = {}
player.Position = Vector(60, 100)

input.ctrl = 'KEY_LEFT_CONTROL'
tick('KEY_4')
assert(packet.clip == 'laugh' and packet.actionFrame == 0)
assert(callAction('ACTION_PILLCARD', 'IS_ACTION_TRIGGERED') == false)
input.ctrl = nil
assert(callAction('ACTION_PILLCARD', 'IS_ACTION_PRESSED') == false, 'Ctrl released before 4')
tick()
tick('KEY_4')
assert(callAction('ACTION_PILLCARD', 'IS_ACTION_TRIGGERED') == true, 'clean 4 was blocked')
input.ctrl = 'KEY_RIGHT_CONTROL'
tick('KEY_6')
assert(packet.mastery and packet.mastery.at == 0 and packet.clip == 'laugh')
assert(packet.mastery.position[1] == packet.position[1] and packet.mastery.position[2] == packet.position[2] - 72
    and packet.mastery.rise == 72, 'the external crest lost its position just above the head')
assert(nativeBadge and nativeBadge.X == packet.position[1] and nativeBadge.Y == packet.position[2] - 53,
    'the native crest did not appear above the visible actor')
player.SpriteScale, player.SpriteOffset, mirror = Vector(1.5, 1.5), Vector(6, -8), true
tick()
assert(packet.mastery.position[1] == Isaac.GetScreenWidth() - player.Position.X * projection
    and packet.mastery.position[2] == packet.position[2] - 95,
    'the external crest lost its anchor under reflection or a larger body')
assert(nativeBadge.X == packet.position[1] - 6 and nativeBadge.Y == packet.position[2] - 76.5,
    'the native crest used the wrong sprite offset under reflection or a larger body')
player.SpriteScale, player.SpriteOffset, mirror = Vector(1, 1), nil, false
assert(event('PRE_PLAYER_RENDER', player, Vector.Zero) == nil)
ack = {version=1, session=session, room=packet.room, time=now, ready=true, visible=true, display=packet.display.id,
    capabilities={mastery=true}}
tick()
assert(event('PRE_PLAYER_RENDER', player, Vector.Zero) == nil, 'crest ACK hid the native body')
ack.capabilities.yoneModel = true
tick(); tick()
assert(event('PRE_PLAYER_RENDER', player, Vector.Zero) == false, 'Yone model ACK did not hide the native body')
ack.capabilities.yoneModel, ack.ready, ack.visible = nil, false, false
tick(); tick()
assert(event('PRE_PLAYER_RENDER', player, Vector.Zero) == nil, 'active crest retained the previous model lease')
local previousShows = nativeShows
tick()
assert(nativeShows == previousShows, 'crest-only Companion frame also drew the native badge')
ack.capabilities.yoneModel, ack.ready, ack.visible = true, true, true
local oldDisplay = packet.display.id
Options.Fullscreen = true
assert(event('PRE_PLAYER_RENDER', player, Vector(0, -80)) == nil,
    'the previous window ACK hid the native body after entering fullscreen')
tick()
assert(packet.display.id ~= oldDisplay and packet.display.mode == 'borderless')
assert(packet.position[2] == player.Position.Y * projection, 'room-pass offset moved the external actor')
assert(packet.mastery.position[2] == packet.position[2] - 72, 'room-pass offset moved the external crest')
ack.display, ack.time = packet.display.id, now
tick(); tick()
assert(event('PRE_PLAYER_RENDER', player, Vector.Zero) == false, 'borderless display never reacquired the model')
event('PRE_CHANGE_ROOM')
event('POST_NEW_ROOM')
tick('KEY_6')
assert(packet.hero == 'yone' and packet.mastery == nil and packet.clip == 'idle', 'room transition kept an emote')

input.ctrl = nil
DamageFlag = {DAMAGE_FAKE = 1}
local attacker = makeEntity('enemy', player.Position.X + 25, player.Position.Y, 12)
entities = {attacker}
function player:SetMinDamageCooldown(frames) self.shieldCooldown = frames end
castKey('KEY_W')
assert(event('ENTITY_TAKE_DMG', player, 1, 0, nil) == false and player.shieldCooldown == nil,
    'W windup took damage or consumed a shield too early')
for _ = 1, 9 do tick() end
local cleave = packet.yone.fx[#packet.yone.fx]
assert(cleave.kind == 'w' and #cleave.arc == 13, 'W had no projected cleave arc')
assert(math.abs(cleave.arc[7][1] - cleave.target[1]) < .001
    and math.abs(cleave.arc[7][2] - cleave.target[2]) < .001, 'W arc and axial endpoint disagreed')
local shieldHud = captureHud()
sameSlots(readyHud, shieldHud)
assert(statusOver(shieldHud, '7s', 2) and shieldHud.shield > 0,
    'W lost its cooldown or shield display')
do
    local w = shieldHud.icons[2]
    local s = w.size / 26
    assert(captureHud(Vector(w.x + 21 * s, w.y + 25 * s))['W shield active'], 'W shield lost its tooltip')
end
assert(event('ENTITY_TAKE_DMG', player, 1, DamageFlag.DAMAGE_FAKE, EntityRef(attacker)) == nil)
assert(event('ENTITY_TAKE_DMG', player, 1, 0, EntityRef(attacker)) == false)
assert(player.shieldCooldown == 15)
assert(event('ENTITY_TAKE_DMG', player, 1, 0, EntityRef(attacker)) == nil)

local positionBeforeE = player.Position
castKey('KEY_E')
for _ = 1, 4 do tick() end
local spiritHud = captureHud()
sameSlots(readyHud, spiritHud)
assert(spiritHud.icons[3].name == 'E2' and spiritHud.ring > 0, 'E lost its active frame or recast icon')
assert(spiritHud['4.9s'] or spiritHud['5.0s'], 'E did not show remaining spirit time')
hudScale = .75
local smallSpirit = captureHud()
local spiritTime = smallSpirit['4.9s'] and '4.9s' or '5.0s'
assert(smallSpirit.icons[3].size == 19.5 and smallSpirit[spiritTime].scale <= 1.05 * .75
    and statusOver(smallSpirit, spiritTime, 3), 'E timer did not scale with the icon')
hudScale = 1
assert(packet.yone.spirit.anchor[1] == positionBeforeE.X * projection)
assert(packet.yone.spirit.anchor[1] < packet.position[1])
attacker.Position = player.Position + Vector(21, 0)
local itemKinds = {}
noItems.newAttack = function(_, skill) return {kind = skill} end
function attacker:TakeDamage(amount, _, source)
    itemKinds[#itemKinds + 1] = itemContextNow and itemContextNow.kind or 'echo'
    event('POST_ENTITY_TAKE_DMG', self, amount, 0, source)
    self.HitPoints = self.HitPoints - amount
    return true
end
tick('KEY_A')
for _ = 1, 8 do tick() end
local mark = packet.yone.spirit.marks[1]
assert(mark and mark.position[1] == attacker.Position.X * projection and mark.amount > 0)
assert(captureHud().ring < spiritHud.ring, 'the E duration ring did not shrink')
local nativeMarkLines = 0
local drawLineBeforeMark = Isaac.DrawLine
Isaac.DrawLine = function(a, b, ...)
    local mx, my = attacker.Position.X * projection, attacker.Position.Y * projection - 25
    if math.abs(a.X - mx) <= 6 and math.abs(a.Y - my) <= 7
        and math.abs(b.X - mx) <= 6 and math.abs(b.Y - my) <= 7 then
        nativeMarkLines = nativeMarkLines + 1
    end
end
ack.room, ack.time, ack.display = packet.room, now, packet.display.id
ack.capabilities.yoneVfx = false
tick()
assert(nativeMarkLines >= 5, 'native mark did not follow the damaged enemy')
Isaac.DrawLine = drawLineBeforeMark
local rendered = {}
Isaac.RenderText = function(text) rendered[text] = true end
ack.room, ack.time, ack.display = packet.room, now, packet.display.id
ack.capabilities.yoneVfx, ack.capabilities.yoneModel = true, nil
event('PRE_PLAYER_RENDER', player, Vector.Zero)
tick()
assert(rendered.BODY and rendered.SPIRIT and not rendered['*'],
    'VFX-only Companion lease suppressed the native E body or duplicated a mark')
ack.capabilities.yoneModel = true
tick()
event('PRE_PLAYER_RENDER', player, Vector.Zero)
rendered = {}
tick()
assert(not rendered.BODY and not rendered.SPIRIT, 'native E body overlapped the Companion rig')
mirror = true
tick()
assert(packet.yone.spirit.marks[1].position[1] == Isaac.GetScreenWidth() - mark.position[1])
assert(packet.yone.spirit.face[1] == -1)
assert(packet.yone.spirit.viewFace[1] < 0 and packet.yone.spirit.viewFace[2] == 0,
    'the renderer lost the mirrored heading of the detached body')
mirror = false
local returnStart = player.Position
local returnCollision = player.GridCollisionClass
castKey('KEY_E')
assert(packet.yone.spirit.returning and packet.yone.fx[#packet.yone.fx].kind == 'e_return')
local recall = packet.yone.fx[#packet.yone.fx]
assert(recall.bodyFace[1] > 0 and recall.bodyRemaining > 0, 'the recall packet lost the original body pose')
assert(recall.travel == 8 and packet.yoneTiming.travel == 8 and player.Position:Distance(returnStart) == 0)
assert(player.GridCollisionClass == EntityGridCollisionClass.GRIDCOLL_NONE)
for _ = 1, 4 do tick('KEY_RIGHT') end
assert(player.Position.X < returnStart.X and player.Position.X > positionBeforeE.X)
assert(callAction('ACTION_RIGHT') == 0 and #itemKinds == 1, 'movement or echo interrupted the return')
assert(event('ENTITY_TAKE_DMG', player, 1, 0, EntityRef(attacker)) == false, 'E return lost invulnerability')
for _ = 1, 4 do tick() end
assert(player.Position:Distance(positionBeforeE) < .001 and player.GridCollisionClass == returnCollision)
assert(event('ENTITY_TAKE_DMG', player, 1, 0, EntityRef(attacker)) == nil, 'E return kept invulnerability at the body')
local echo = packet.yone.fx[#packet.yone.fx]
assert(not packet.yone.spirit and echo.kind == 'e_echo' and #echo.contacts == 1
    and echo.contacts[1][1] == attacker.Position.X * projection, 'E lost the detonation point on arrival')
assert(#itemKinds == 2 and itemKinds[1] == 'attack' and itemKinds[2] == 'echo',
    'E replay repeated a shared on-hit effect')

-- Floor exits have their own player-exit callback, and new-room can fire
-- before the new-level callback while the old cutscene is still rendering.
local doorRoom = packet.room
local playerAnimation, animationPlaying = 'Trapdoor', true
function player:GetSprite()
    return {
        GetAnimation = function() return playerAnimation end,
        IsPlaying = function(_, clip) return clip == playerAnimation and animationPlaying end,
    }
end
event('PRE_ROOM_EXIT', player, true)
event('POST_NIGHTMARE_SCENE_SHOW')
assert(packet.active and packet.transition and packet.yone == nil,
    'floor exit did not hide combat visuals and audio')
kind = 0
tick()
assert(packet.active and packet.session == session, 'temporary player rebinding stopped the Yone session')
event('POST_NEW_ROOM')
kind = 130
event('POST_NIGHTMARE_SCENE_RENDER')
assert(packet.room == doorRoom and packet.occluded, 'published the floor room before level arrival')
kind = 0
frame = 1 -- a new scene can report a backwards game clock
event('POST_NEW_LEVEL')
for _ = 1, 30 do tick() end -- longer than the former 650 ms lease
assert(packet.active, 'new level callback raced player rebinding')
kind = 130
event('POST_NIGHTMARE_SCENE_RENDER')
assert(packet.occluded, 'model painted over the last nightmare frame')
animationPlaying = false
tick()
assert(packet.session == session and packet.room == doorRoom + 1 and not packet.occluded
    and not packet.transition, 'Yone did not resume after the floor and finished trapdoor clip')
assert(event('PRE_PLAYER_RENDER', player, Vector.Zero) == nil, 'old level ACK hid the native body')
ack.room, ack.time, ack.display = packet.room, now, packet.display.id
tick(); tick()
assert(event('PRE_PLAYER_RENDER', player, Vector.Zero) == false, 'new level never acquired the model lease')
playerAnimation = 'Walk'
castKey('KEY_W')
assert(packet.clip == 'idle', 'W cooldown was lost during floor rebinding')
castKey('KEY_Q')
assert(packet.clip == 'q', 'combat input did not recover after the floor')

-- The level callback is sufficient even if room entry did not reach this
-- update path and Isaac briefly reports that the run is unavailable.
local firstFloorRoom = packet.room
local inGame = Isaac.IsInGame
renderOnly('KEY_R')
event('PRE_ROOM_EXIT', player, true)
Isaac.IsInGame = function() return false end
tick()
event('POST_NEW_LEVEL')
tick()
Isaac.IsInGame = inGame
tick()
assert(packet.active and packet.session == session and packet.room == firstFloorRoom + 1
    and not packet.occluded, 'direct level arrival did not rebind the same run')
assert(packet.clip == 'idle', 'a queued ability leaked to the next floor')
-- The reverse callback order must retain the same run and require a fresh
-- renderer acknowledgement even after a long period with no player object.
local oldGetPlayer = Isaac.GetPlayer
event('PRE_ROOM_EXIT', player, true)
Isaac.GetPlayer = function() return nil end
event('POST_NEW_LEVEL')
for _ = 1, 30 do tick() end
event('POST_NEW_ROOM')
Isaac.GetPlayer = oldGetPlayer
tick()
assert(packet.active and packet.session == session and not packet.occluded,
    'level-first transition lost the Yone session')
assert(event('PRE_PLAYER_RENDER', player, Vector.Zero) == nil,
    'level-first transition reused the previous renderer acknowledgement')
ack.room, ack.time, ack.display = packet.room, now, packet.display.id
tick(); tick()
assert(event('PRE_PLAYER_RENDER', player, Vector.Zero) == false,
    'level-first transition failed to acquire a fresh renderer acknowledgement')
local rCasts = 0
local previousOnCast = noItems.onCast
noItems.onCast = function(owner, skill, clock)
    if skill == 'r' then rCasts = rCasts + 1 end
    return previousOnCast(owner, skill, clock)
end
input.held = 'KEY_RIGHT_SHIFT'
for _ = 1, 45 do
    tick('KEY_R')
    assert(callAction('ACTION_RESTART', 'IS_ACTION_PRESSED') == true, 'held Shift+R did not request the native restart')
    assert(rCasts == 0, 'Shift+R cast the ultimate')
end
input.held = nil
tick('KEY_R')
assert(callAction('ACTION_RESTART', 'IS_ACTION_PRESSED') == false)
tick()
assert(rCasts == 0, 'releasing Shift before R queued an ultimate')
for _ = 1, 45 do
    tick('KEY_R')
    assert(callAction('ACTION_RESTART', 'IS_ACTION_PRESSED') == false, 'long R hold allowed restart')
    assert(rCasts == 0, 'R cast before release')
    assert(event('ENTITY_TAKE_DMG', player, 1, 0, nil) == nil, 'holding R gave immunity before cast')
end
tick()
assert(rCasts == 1, 'R release did not cast exactly once')
assert(event('ENTITY_TAKE_DMG', player, 1, 0, nil) == false, 'R cast did not prevent environmental damage')
assert(event('ENTITY_TAKE_DMG', player, 1, DamageFlag.DAMAGE_FAKE, EntityRef(attacker)) == nil,
    'R immunity swallowed fake damage')
local ultimateHud = captureHud()
sameSlots(readyHud, ultimateHud)
assert(statusOver(ultimateHud, '30s', 4), 'R lost its cooldown display')
for _ = 1, 40 do tick() end
assert(event('ENTITY_TAKE_DMG', player, 1, 0, nil) == false,
    'R no longer protects from contact once the animation ends')

local roomKey, claimed = 1, {[1] = true}
noItems.claimCombatRoomReset = function()
    if #entities == 0 or claimed[roomKey] then return false end
    claimed[roomKey] = true
    return true
end
renderOnly('KEY_E')
event('PRE_CHANGE_ROOM')
roomKey, entities = 2, {attacker}
local hpOnEntry = attacker.HitPoints
event('POST_NEW_ROOM')
assert(event('ENTITY_TAKE_DMG', player, 1, 0, nil) == nil, 'R immunity remained in the next room')
tick('KEY_E')
tick()
assert(packet.clip == 'idle', 'held E leaked into the new room')
assert(attacker:Exists() and attacker.HitPoints == hpOnEntry, 'room transition removed or damaged returning enemy')
assert(claimed[2] and not captureHud()['30s'], 'first combat in a new room did not refresh R')
castKey('KEY_W')
assert(captureHud()['7s'], 'fresh W did not go on cooldown')
event('PRE_CHANGE_ROOM')
event('POST_NEW_ROOM')
tick()
assert(captureHud()['7s'], 're-entering an already claimed room refreshed W again')

event('POST_GAME_STARTED', false)
player.Position, player.Velocity, wall = Vector(60, 100), Vector.Zero, {}
entities = {makeEntity('enemy', 91, 100, 751)}
for _ = 1, 2 do
    castKey('KEY_Q')
    for _ = 1, 60 do tick() end
end
assert(packet.yone.qReady, 'E-Q3 integration could not charge Q')
local comboOrigin = player.Position
castKey('KEY_E')
tick('KEY_Q', false, Vector(100, 100))
tick(nil, false, Vector(100, 100))
assert(packet.clip == 'e' and player.Position:Distance(comboOrigin) == 0)
tick()
assert(packet.clip == 'q3' and math.abs(player.Position.X - comboOrigin.X - 84) < .001,
    'Q3 input during E windup was lost or started at the body')
for _ = 1, 8 do tick() end
assert(math.abs(player.Position.X - comboOrigin.X - 240) < .001, 'E-Q3 did not travel 84 + 156 in open space')
castKey('KEY_E')
for _ = 1, 4 do tick() end
assert(player.GridCollisionClass == EntityGridCollisionClass.GRIDCOLL_NONE, 'recall did not start before room change')
event('PRE_CHANGE_ROOM')
assert(player.GridCollisionClass == returnCollision, 'departing during recall left grid collision disabled')
event('POST_NEW_ROOM')
tick()
assert(not packet.yone.spirit and packet.clip == 'idle', 'recall leaked into next room')

kind = 0
tick()
assert(packet.active == false, 'fallback scene was not closed on character change')
assert(Options.Fullscreen and not Options.UseBorderlessFullscreen,
    'the original fullscreen preference was not restored')

local warnings, warningStops = {}, 0
Isaac.GetSoundIdByName = function(name) return name == 'Yone E Warning' and 91 or -1 end
SFXManager = function()
    return {
        Play = function(_, id)
            assert(id == 91, 'E countdown did not play the registered cue')
            warnings[#warnings + 1] = frame
        end,
        Stop = function(_, id)
            assert(id == 91, 'E countdown stopped an unrelated sound')
            warningStops = warningStops + 1
        end,
    }
end
local bodySprite, bodyTint, bodyX, bodyY
bodySprite = {
    Color = Color(1, 1, 1, 1),
    GetAnimation = function() return 'Walk' end,
    Render = function(self, where)
        bodyTint, bodyX, bodyY = self.Color, where.X, where.Y
    end,
}
function player:GetSprite() return bodySprite end

local function startCountdown()
    kind, ack, entities = 130, nil, {}
    player.Position = Vector(85, 105)
    event('POST_GAME_STARTED', false)
    tick()
    castKey('KEY_E')
    for _ = 1, 6 do
        if packet.yone.spirit then break end
        tick()
    end
    assert(packet.yone.spirit and packet.yone.spirit.remaining == 1)
    return frame
end

local function measureCountdown()
    local minX, maxX, rings = math.huge, -math.huge, 0
    local originalLine = Isaac.DrawLine
    Isaac.DrawLine = function(a, b, color, _, thickness)
        if thickness == 1.5 and color[1] == 1 and color[4] == .95 then
            minX, maxX = math.min(minX, a.X, b.X), math.max(maxX, a.X, b.X)
            rings = rings + 1
        end
    end
    local originalColor = bodySprite.Color
    now = now + 30
    renderOnly()
    Isaac.DrawLine = originalLine
    assert(bodySprite.Color == originalColor, 'E left the active sprite tinted')
    assert(bodyX == packet.yone.spirit.anchor[1] and bodyY == packet.yone.spirit.anchor[2],
        'native body is away from its projected anchor')
    assert(rings == 24 and math.abs((maxX + minX) / 2 - bodyX) < .001,
        'E time circle is not complete or centered on the body')
    return maxX - minX, bodyTint[4]
end

local castFrame = startCountdown()
local fullWidth, fullAlpha = measureCountdown()
for _ = 1, 75 do tick() end
local halfWidth, halfAlpha = measureCountdown()
assert(math.abs(halfWidth * 2 - fullWidth) < .001 and halfAlpha < fullAlpha,
    'native E body and circle did not drain with the duration')
mirror = true
assert(math.abs(measureCountdown() - halfWidth) < .001
    and bodyX == Isaac.GetScreenWidth() - 85 * projection, 'mirror displaced the native E circle')
mirror = false
for _ = 1, 14 do tick() end
assert(#warnings == 0, 'E warning played more than two seconds before auto-return')
tick()
assert(#warnings == 1 and warnings[1] == castFrame + 90, 'E warning missed the two-second threshold')
for _ = 1, 5 do renderOnly(); tick() end
assert(#warnings == 1, 'E warning replayed between updates and renders')
castKey('KEY_E')
assert(warningStops == 1 and #warnings == 1, 'early recall did not stop the active E warning')

castFrame = startCountdown()
for _ = 1, 90 do tick() end
assert(#warnings == 2 and warnings[2] == castFrame + 90, 'new E cast did not get its own warning')
event('PRE_ROOM_EXIT', player, true)
event('POST_NEW_ROOM')
event('POST_NEW_LEVEL')
tick()
assert(warningStops == 2 and #warnings == 2 and not packet.yone.spirit,
    'floor transition kept or replayed the E warning')

castFrame = startCountdown()
for _ = 1, 150 do tick() end
assert(#warnings == 3 and warnings[3] == castFrame + 90 and warningStops == 3,
    'expiry did not play and clean up the E warning once')

castFrame = startCountdown()
for _ = 1, 140 do tick() end
castKey('KEY_R')
for _ = 1, 8 do tick() end
assert(packet.kind == 'r' and packet.yone.spirit and packet.yone.spirit.remaining == 0,
    'R did not defer the expired E return for the warning check')
assert(#warnings == 4 and warnings[4] == castFrame + 90 and warningStops == 3,
    'deferral replayed or restarted the E countdown warning')
for _ = 1, 45 do tick() end
assert(#warnings == 4 and warningStops == 4, 'deferred return did not clean up the warning once')
event('PRE_GAME_EXIT')

-- Exercise the public console commands through the genuine mod callback.
local messages = {}
Isaac.ConsoleOutput = function(line) messages[#messages + 1] = line end
kind, selected, entities, ack = 0, true, {}, nil
event('POST_GAME_STARTED', false)
tick()
assert(packet.active and packet.hero ~= 'yone', 'precondition: Samira was not active')
console = true
event('EXECUTE_CMD', 'yonetest', '')
assert(messages[#messages]:find('testing enabled', 1, true) and player:GetPlayerType() == 0)
event('EXECUTE_CMD', 'yoneq3', '')
tick()
assert(packet.occluded, 'test command ran its presentation while the console was open')
console = false
tick()
assert(packet.hero == 'yone' and packet.yone.qReady, 'yonetest did not activate the test hero or charge Q3')
local testSession = packet.session
event('EXECUTE_CMD', 'yoneanim', 'q3')
tick()
assert(packet.session == testSession and packet.clip == 'q3' and packet.yone.qReady,
    'yoneanim was not a visual-only preview')
event('EXECUTE_CMD', 'yonecast', 'invalid')
assert(messages[#messages]:find('Usage: yonecast', 1, true))
event('EXECUTE_CMD', 'yonereset', '')
event('EXECUTE_CMD', 'yonecast', 'q3')
tick()
assert(packet.yoneTiming.hit == 7, 'yonecast did not queue a real Q3')
for _ = 1, 8 do tick() end
assert(not packet.yone.qReady and lastCast == 'q', 'test cast did not consume Q stacks')
event('EXECUTE_CMD', 'yonemastery', '')
tick()
assert(packet.mastery, 'yonemastery did not display the badge')
event('EXECUTE_CMD', 'yoneweapon', '')
assert(messages[#messages]:find('next blade steel', 1, true))
event('EXECUTE_CMD', 'yonehelp', '')
assert(messages[#messages]:find('yoneitem <Riot item ID>', 1, true))
event('EXECUTE_CMD', 'yonetest', 'off')
tick()
assert(packet.active and packet.hero ~= 'yone', 'yonetest off did not restore Samira')

kind, selected = 130, false
event('POST_GAME_STARTED', false)
tick()
local nativeSession = packet.session
castKey('KEY_W')
event('EXECUTE_CMD', 'yonetest', '')
tick()
assert(packet.session == nativeSession and captureHud()['7s'],
    'yonetest reset the selected hero or discarded cooldowns')
event('PRE_GAME_EXIT')

-- Door art extends outside the floor. The native doorway requires a centered
-- approach, and a receiving room can briefly place the player outside its grid.
for _, slot in ipairs({0, 2, 4, 6}) do
    event('POST_GAME_STARTED', false)
    mirror, entities, wall, doors = slot >= 4, {}, {}, {}
    local left = slot % 4 == 0
    local normal = Vector(left and -1 or 1, 0)
    local door = Vector(left and 0 or 400, slot >= 4 and 140 or 100)
    doors[slot] = {Position = door, IsOpen = function() return true end}
    player.Position, player.Velocity = door - normal * 36 + Vector(0, 17), Vector.Zero
    local click = door + normal * 48
    if mirror then click.X = Isaac.GetScreenWidth() / projection - click.X end
    tick(nil, true, click)
    local function horizontal()
        return callAction('ACTION_RIGHT') - callAction('ACTION_LEFT')
    end
    assert(horizontal() * normal.X > .8 and callAction('ACTION_UP') > 0,
        'side door did not use the native approach and center its movement')
    for _ = 1, 40 do
        tick(nil, false, nil, function()
            local along = (player.Position - door):Dot(normal)
            if along > -8 and math.abs(player.Position.Y - door.Y) > 10 then
                player.Position = Vector(door.X - normal.X * 8, player.Position.Y)
            end
        end)
        if (player.Position - door):Dot(normal) > 0 then break end
    end
    assert((player.Position - door):Dot(normal) > 0 and math.abs(player.Position.Y - door.Y) <= 10,
        'Yone got stuck on the side of the doorway')

    event('POST_NEW_ROOM')
    player.Position, player.Velocity = door + normal * 8, Vector.Zero
    doors[slot].IsOpen = function() return false end
    local inside = Vector(200, 104)
    if mirror then inside.X = Isaac.GetScreenWidth() / projection - inside.X end
    tick(nil, true, inside)
    assert(horizontal() * normal.X < -.95, 'incoming side door trapped Yone outside the navigation grid')
    for _ = 1, 15 do tick() end
    assert((player.Position - door):Dot(normal) < -24)
    event('PRE_GAME_EXIT')
end
event('POST_GAME_STARTED', false)
mirror, entities, wall, doors = false, {}, {}, {}
doors[2] = {Position = Vector(400, 100), IsOpen = function() return true end}
wall[room:GetGridIndex(Vector(220, 100))] = GridCollisionClass.COLLISION_WALL
player.Position, player.Velocity = Vector(76, 100), Vector.Zero
tick(nil, true, Vector(448, 100))
for _ = 1, 170 do
    tick()
    if player.Position.X > 400 then break end
    assert(room:GetGridCollision(room:GetGridIndex(player.Position)) == GridCollisionClass.COLLISION_NONE,
        'door order walked into the interior obstacle')
end
assert(player.Position.X > 400 and math.abs(player.Position.Y - 100) < 10,
    'Yone did not detour around the obstacle before reaching the door')
event('PRE_GAME_EXIT')
-- Arrival can precede a missing or late level callback.
event('POST_GAME_STARTED', false)
tick()
local recoveredSession, recoveredRoom = packet.session, packet.room
function player:GetSprite()
    return {GetAnimation = function() return playerAnimation end,
        IsPlaying = function(_, clip) return clip == playerAnimation and animationPlaying end}
end
event('PRE_ROOM_EXIT', player, true)
playerAnimation, animationPlaying = 'Trapdoor', true
event('POST_NEW_ROOM')
for _ = 1, 5 do tick() end
assert(packet.room == recoveredRoom and packet.occluded,
    'floor recovery exposed the trapdoor animation')
animationPlaying = false
for _ = 1, 5 do tick() end
assert(packet.active and packet.session == recoveredSession and packet.room == recoveredRoom + 1
    and not packet.transition and not packet.occluded, 'floor arrival did not recover without new-level callback')
assert(event('PRE_PLAYER_RENDER', player, Vector.Zero) == nil,
    'floor recovery reused the previous room renderer lease')
ack = {version = 1, session = recoveredSession, room = packet.room, time = now,
    display = packet.display.id, ready = true, visible = true,
    capabilities = {yoneModel = true, yoneVfx = true, mastery = true}}
tick(); tick()
assert(event('PRE_PLAYER_RENDER', player, Vector.Zero) == false,
    'floor recovery did not acquire a fresh renderer lease')
event('POST_NEW_LEVEL')
tick()
assert(packet.room == recoveredRoom + 1 and not packet.occluded,
    'late new-level callback duplicated or hid the recovered room')
local seed = 101
function room:GetSpawnSeed() return seed end
event('PRE_ROOM_EXIT', player, true)
for _ = 1, 3 do tick() end
assert(packet.room == recoveredRoom + 1 and packet.occluded,
    'floor recovery fired while still physically in the departure room')
seed = 102
for _ = 1, 5 do tick() end
assert(packet.session == recoveredSession and packet.room == recoveredRoom + 2 and not packet.occluded,
    'floor recovery required a room callback despite observing the new room')

-- Cellar II live trace: the room and game clock advance, but the transition
-- gate keeps publishing an occluded session after the nightmare scene.
local transitionMode = RoomTransition.GetTransitionMode
local mode = 1
RoomTransition.GetTransitionMode = function() return mode end
event('PRE_ROOM_EXIT', player, true)
seed = 103
player.ControlsEnabled = false
event('POST_NEW_ROOM')
event('POST_NEW_LEVEL')
tick()
local arrivalSeq = packet.seq
event('PRE_CHANGE_ROOM')
assert(packet.seq == arrivalSeq, 'late PRE_CHANGE_ROOM restarted a confirmed floor arrival')
event('PRE_ROOM_EXIT', player, true)
assert(packet.seq == arrivalSeq, 'late PRE_ROOM_EXIT restarted a confirmed floor arrival')
for _ = 1, 10 do tick() end
assert(packet.transition and packet.occluded, 'floor camera opened before the player regained controls')
player.ControlsEnabled = true
for _ = 1, 10 do tick() end
assert(packet.active and packet.session == recoveredSession and packet.room == recoveredRoom + 3
    and not packet.transition and not packet.occluded,
    'stale transition hid Yone after the new floor was playable')
captureHud()
castKey('KEY_Q')
assert(packet.clip == 'q', 'QWER remained blocked after a stale floor transition')
mode = 0
tick()
mode = 1
event('PRE_CHANGE_ROOM')
assert(packet.transition and packet.occluded, 'the next real transition did not hide Yone')
event('PRE_ROOM_EXIT', player, true)
seed = 104
event('POST_NEW_ROOM')
event('POST_NEW_LEVEL')
RoomTransition.GetTransitionMode = transitionMode
for _ = 1, 3 do tick() end
assert(packet.session == recoveredSession and packet.room == recoveredRoom + 4
    and not packet.transition and not packet.occluded, 'the next real floor departure did not recover exactly once')
player.ControlsEnabled = nil
event('PRE_GAME_EXIT')

-- Use the production progression module behind the items boundary. Run-save
-- and Hourglass ownership are tested with the real Items module elsewhere.
do
    local progress = include('yone_progression')
    local run, chosen, casts
    noItems.startYoneProgress = function(continued)
        assert(not continued)
        run, chosen = progress.restore(), nil
    end
    noItems.yoneProgress = function() return run end
    noItems.chooseYoneRune = function(key)
        chosen = key
        return progress.choose(run, key, 0)
    end
    noItems.onCast = function(_, key) casts[#casts + 1] = key end
    local function pickerText()
        local labels, original = {}, Isaac.RenderScaledText
        Isaac.RenderScaledText = function(label, x, y, _, _, r, g)
            labels[label] = {r, g, cursor = Vector(x + 2, y + 2) * (1 / projection)}
        end
        event('POST_RENDER')
        Isaac.RenderScaledText = original
        return labels
    end

    casts, ack, roomClear, playerAnimation = {}, nil, true, 'Walk'
    player.Position, player.Velocity, wall, doors = Vector(60, 100), Vector.Zero, {}, {}
    local target = makeEntity('enemy', 91, 100, 901)
    entities = {target}
    event('POST_GAME_STARTED', false)
    event('POST_NEW_ROOM')
    tick('KEY_ENTER')
    assert(run.rune == nil, 'held menu confirmation chose a rune on entry')
    tick()
    local menu = pickerText()
    assert(menu['Choose a keystone'] and menu.Conqueror and menu['Lethal Tempo']
        and menu.Electrocute and menu.Random and not menu.Q,
        'spawn-room picker did not render all choices or concealed the regular HUD incorrectly')
    local before = player.Position
    tick('KEY_A', false, target.Position)
    tick('KEY_Q', false, target.Position)
    tick(nil, true, Vector(200, 100))
    tick('KEY_LEFT')
    menu = pickerText()
    assert(menu.Random[2] < menu.Conqueror[2], 'left did not wrap the highlight to Random')
    assert(callAction('ACTION_LEFT') == 0 and player.Position:Distance(before) == 0
        and #casts == 0 and #target.damage == 0, 'picker leaked movement or combat input')
    assert(callAction('ACTION_ITEM', 'IS_ACTION_TRIGGERED') == false
        and callAction('ACTION_DROP', 'IS_ACTION_PRESSED') == false, 'picker leaked a native item action')
    input.held = 'KEY_Q'
    tick('KEY_ENTER')
    assert(chosen == 'random' and run.rune == 'conqueror', 'Enter did not lock the seeded Random choice')
    input.held = nil
    tick()
    assert(#casts == 0 and not pickerText()['Choose a keystone'], 'picker confirm leaked held Q or left the menu open')
    local startHud = captureHud()
    assert(startHud['LVL 1  0/60 XP'] and startHud['Q1 W1 E1 R1'] and startHud.Conqueror
        and #startHud.art.Conqueror == 1 and not startHud.art.Upgrade and not startHud.art.XP,
        'fresh progression HUD lost XP, rune name, or a starting rank')

    assert(progress.award(run, 65) == 1)
    local earned = captureHud()
    local bounds = include('yone_hud').bounds(hudScale, include('samira_inventory_hud').bounds(player, hudScale), true)
    local xp = earned['LVL 2  5/72 XP']
    assert(xp.x >= bounds.progress.x
        and xp.x + Isaac.GetTextWidth('LVL 2  5/72 XP') * xp.scale <= bounds.combat.x
        and bounds.progress.y == bounds.combat.y and bounds.height == 39 * bounds.scale
        and earned['Alt+QWER: 1 pt'] and #earned.art.Upgrade == 3 and #earned.art.XP == 1 and #earned.art.AbilityFrame == 4,
        'XP must stay left of the combat HUD without increasing its height')
    do
        local width, height = Isaac.GetScreenWidth, Isaac.GetScreenHeight
        Isaac.GetScreenWidth, Isaac.GetScreenHeight = function() return 688 end, function() return 288 end
        for _, scale in ipairs({1, 1.5}) do
            hudScale = scale
            local bag = include('samira_inventory_hud').bounds(player, scale)
            local wide = include('yone_hud').bounds(scale, bag, true)
            assert(wide.progress.x > bag.x + bag.width and wide.combat.x > wide.progress.x + wide.progress.width
                and wide.combat.y + wide.combat.height >= Isaac.GetScreenHeight() - 5
                and wide.combat.x + wide.combat.width <= Isaac.GetScreenWidth() - 5,
                'wide HUD did not fit the left panel and the skills beside the backpack')
            local hud = captureHud()
            assert(hud['LVL 2  5/72 XP'].x < hud.icons[1].x and #hud.art.Upgrade == 3)
        end
        Isaac.GetScreenWidth, Isaac.GetScreenHeight, hudScale = width, height, 1
    end
    input.held = 'KEY_LEFT_ALT'
    tick('KEY_Q')
    tick('KEY_Q')
    input.held = nil
    tick('KEY_Q')
    tick()
    local ranked = captureHud()
    assert(ranked['Q2 W1 E1 R1'] and not ranked['Alt+QWER: 1 pt'] and #casts == 0,
        'Alt+Q did not spend one point cleanly or leaked a cast')

    tick('KEY_A', false, target.Position)
    for _ = 1, 16 do tick() end
    assert(#target.damage == 1 and progress.damage(run, 'attack', frame) > 1,
        'the first accepted autoattack did not grant a Conqueror stack')
    tick('KEY_Q', false, target.Position)
    tick(nil, false, target.Position)
    for _ = 1, 7 do tick() end
    local expected = player.Damage * 1.4 * 1.08 * 1.02
    assert(casts[1] == 'q' and #target.damage == 2 and math.abs(target.damage[2] - expected) < .001,
        'the real Q impact did not combine skill rank with the prior rune stack')
    local stacked = captureHud()
    assert(stacked.conquerorPips == 2 and #stacked.art.Conqueror == 2, 'Conqueror stacks did not render at player and HUD')
    local anchor = stacked.art.Conqueror[1]
    assert(anchor.X == player.Position.X * projection - 16 and anchor.Y == player.Position.Y * projection + 10)
    mirror = true
    anchor = captureHud().art.Conqueror[1]
    assert(anchor.X == Isaac.GetScreenWidth() - player.Position.X * projection - 16
        and anchor.Y == player.Position.Y * projection + 10, 'mirror displaced the Conqueror player indicator')
    mirror = false
    event('PRE_GAME_EXIT')

    local nativeMouse = Input.IsMouseBtnPressed
    local mouseDown = true
    Input.IsMouseBtnPressed = function(button)
        if button == 0 then return mouseDown end
        return nativeMouse(button)
    end
    event('POST_GAME_STARTED', false)
    event('POST_NEW_ROOM')
    menu = pickerText()
    tick(nil, false, menu.Confirm.cursor)
    assert(not run.rune, 'held click from the previous menu confirmed a rune')
    mouseDown = false
    tick()
    hudScale = 1.5
    menu = pickerText()
    mouseDown = true
    tick(nil, false, menu['Lethal Tempo'].cursor)
    assert(pickerText()['Lethal Tempo'][2] < pickerText().Conqueror[2] and not chosen,
        'mouse click did not select the visible rune without committing it')
    tick(nil, false, menu.Confirm.cursor)
    assert(not chosen, 'holding a click across the picker confirmed the choice')
    mouseDown = false
    tick()
    mouseDown = true
    tick(nil, false, menu.Confirm.cursor)
    assert(chosen == 'lethal_tempo' and not pickerText()['Choose a keystone'], 'mouse confirmation failed')
    assert(progress.award(run, 132) == 2)
    local upgraded = captureHud()
    local q, r = upgraded.icons[1], upgraded.icons[4]
    local function arrow(icon)
        return Vector(icon.x + icon.size / 2, icon.y - 7 * icon.size / 26) * (1 / projection)
    end
    mouseDown = false
    tick()
    mouseDown = true
    tick(nil, false, arrow(r))
    assert(progress.rank(run, 'r') == 1 and progress.points(run) == 2, 'locked R accepted a click')
    mouseDown = false
    tick()
    mouseDown = true
    tick(nil, false, arrow(q))
    tick(nil, false, arrow(q))
    assert(progress.rank(run, 'q') == 2 and progress.points(run) == 1, 'Q arrow click did not spend exactly one point')
    for _ = 1, 7 do progress.onStrike(run, 'attack', frame) end
    stacked = captureHud()
    assert(stacked.tempoPips == 6 and #stacked.art.Tempo == 2, 'Lethal Tempo pips did not show the stack cap')
    frame = frame + 120
    assert(#captureHud().art.Tempo == 1, 'Lethal Tempo player indicator survived expiration')
    progress.resetRoom(run)
    assert(captureHud().tempoPips == 0, 'Lethal Tempo pips survived a room reset')
    event('PRE_GAME_EXIT')
    Input.IsMouseBtnPressed = nativeMouse
    hudScale = 1

    event('POST_GAME_STARTED', false)
    event('POST_NEW_ROOM')
    assert(progress.choose(run, 'electrocute', 0))
    tick()
    local electro = captureHud()
    local runeCursor = Vector(electro.Electrocute.x + 2, electro.Electrocute.y + 3)
    assert(#electro.art.Electrocute == 1 and captureHud(runeCursor)['Electrocute ready'])
    for _, hit in ipairs({'attack', 'q', 'w'}) do progress.onStrike(run, hit, frame) end
    electro = captureHud(runeCursor)
    assert(#electro.art.ElectrocuteDark == 1 and electro.electroFill == 0 and electro['Electrocute  8.0s'])
    frame = frame + 120
    electro = captureHud(runeCursor)
    assert(#electro.art.ElectrocuteDark == 1 and math.abs(electro.electroFill - 22 * bounds.scale) < .001
        and electro['Electrocute  4.0s'], 'Electrocute cooldown fill did not track time')
    frame = frame + 120
    assert(captureHud(runeCursor)['Electrocute ready'])
    event('PRE_GAME_EXIT')
end
""")
    print("PASS Yone registration, input, emotes, leases, HUD, floor lifecycle, console and progression")


if __name__ == "__main__":
    sys.exit(main())
