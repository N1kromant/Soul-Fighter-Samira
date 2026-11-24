"""Exercise the native weapon adapter against Isaac-style input and fire callbacks."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'work/python-deps'))
from lupa.lua54 import LuaRuntime

lua = LuaRuntime()
lua.globals().weaponSource = (ROOT / 'src/samira-testroom/mod/samira_weapons.lua').read_text(encoding='utf8')
lua.execute(r'''
local function names()
    return setmetatable({}, {__index = function(_, name) return name end})
end
ButtonAction, InputHook, EntityType, ModCallbacks = names(), names(), names(), names()
FamiliarVariant = {INCUBUS = 23, TWISTED_BABY = 238}
WeaponType = {WEAPON_LUDOVICO_TECHNIQUE = 'ludo', WEAPON_ROCKETS = 'rockets', WEAPON_BRIMSTONE = 'brimstone',
    WEAPON_LASER = 'laser', WEAPON_TECH_X = 'techx', WEAPON_BONE = 'bone', WEAPON_SPIRIT_SWORD = 'sword',
    WEAPON_NOTCHED_AXE = 'axe'}
EffectVariant = {TARGET = 30, ROCKET = 31, SMALL_ROCKET = 118}
local vec = {}
vec.__index = vec
function Vector(x, y) return setmetatable({X=x,Y=y}, vec) end
function vec:Length() return math.sqrt(self.X * self.X + self.Y * self.Y) end
function vec:Normalized() return self * (1 / self:Length()) end
function vec:GetAngleDegrees() return math.deg(math.atan(self.Y, self.X)) end
function vec:Rotated(degrees)
    local radians = math.rad(degrees)
    return Vector(self.X * math.cos(radians) - self.Y * math.sin(radians),
        self.X * math.sin(radians) + self.Y * math.cos(radians))
end
function vec.__add(a, b) return Vector(a.X + b.X, a.Y + b.Y) end
function vec.__mul(a, b) return Vector(a.X * b, a.Y * b) end
function vec.__sub(a, b) return Vector(a.X - b.X, a.Y - b.Y) end
function Color(...) return {...} end
function GetPtrHash(entity) return entity end
local ticks, attacks, consoleLines, announced, p = 0, 0, {}, {}, {Type = EntityType.ENTITY_PLAYER, MaxFireDelay = 4}
local callbacks = {}
local weapon = {id = 'tears', charge = 0, max = 0, fired = 0}
function p:GetWeapon(slot) assert(slot == 1); return weapon end
function weapon:GetCharge() return self.charge end
function weapon:GetMaxCharge() return self.max end
function weapon:SetCharge(charge) self.charge = charge end
function weapon:GetNumFired() return self.fired end
function weapon:GetMainEntity() return self.entity end
function weapon:GetWeaponType() return self.id end
function weapon:GetDirection() return self.direction or Vector(1, 0) end
function weapon:GetOwner() return p end
function weapon:IsAxisAligned() return self.id == 'brimstone' end
local function object(kind, owner)
    local entity = {Type = EntityType['ENTITY_' .. kind], SpawnerEntity = owner, Scale = 1,
        SpriteScale = Vector(1, 1), data = {}}
    function entity:GetData() return self.data end
    function entity:Exists() return true end
    function entity:ToTear() return self end
    function entity:ToLaser() return self end
    function entity:ToKnife() return self end
    function entity:ToFamiliar() return self end
    function entity:IsFlying() return self.flying == true end
    function entity:IsCircleLaser() return self.ring == true end
    function entity:GetColor() return self.tint or self.nativeColor or 'native' end
    function entity:SetColor(color, ...) self.tint = color end
    return entity
end
local function event(name, ...)
    return callbacks[name](nil, ...)
end
Isaac = {ConsoleOutput = function(message) consoleLines[#consoleLines + 1] = message end}
local Weapons = assert(load(weaponSource))()
Weapons.init({AddCallback = function(_, name, cb) assert(not callbacks[name]); callbacks[name] = cb end},
    {GetFrameCount = function() return ticks end}, function() return p end, {
        newAttack = function(player, kind, clock)
            attacks = attacks + 1
            return {player = player, kind = kind, clock = clock, id = attacks, missFortune = player.missFortune}
        end,
        tagTear = function(player, entity, context, split)
            assert(player == p)
            entity.data.SamiraItemContext = context
            entity.data.SamiraItemTaggedSplit = split
            if not split then entity.TearFlags = (entity.TearFlags or 0) | 0x40 end
        end,
    }, function(kind, heading, ctx)
        announced[#announced + 1] = {kind = kind, heading = heading, ctx = ctx}
    end)
local function reset(id, max)
    Weapons.reset()
    ticks, attacks, announced, consoleLines = 0, 0, {}, {}
    weapon.id, weapon.max, weapon.charge, weapon.fired, weapon.entity = id, max, 0, 0, nil
end
local aim = Vector(3, -4)
local function begin(aa, enabled, point)
    Weapons.update(p, ticks, aa, enabled ~= false, point)
    ticks = ticks + 1
    event('MC_PRE_PLAYER_UPDATE', p)
end
local function input(mode, direction)
    return Weapons.input(p, InputHook[mode], ButtonAction['ACTION_SHOOT' .. direction])
end
local function trigger(owner, nativeHeading)
    weapon.fired = weapon.fired + 1
    event('MC_POST_TRIGGER_WEAPON_FIRED', nativeHeading or aim:Normalized(), 1, owner or p, weapon)
end
local function endFrame() event('MC_POST_PLAYER_UPDATE', p) end
local function ref(entity) return {Entity = entity} end

-- Miss Fortune's cast timer and the native charge must run in parallel.
local qDelay = 8
for _, kind in ipairs({'brimstone','techx','knife'}) do
    reset(kind, 3)
    assert(Weapons.requestQ(p, aim, ticks, Vector(80,0), qDelay, true))
    for i=1,qDelay-1 do
        begin(nil)
        assert(input('IS_ACTION_PRESSED','RIGHT'), kind .. ' must charge before the Q release gate')
        weapon.charge = math.min(i, 3)
        endFrame()
        assert(#announced == 0 and Weapons.hasPendingQ(p))
    end
    begin(nil)
    assert(not input('IS_ACTION_PRESSED','RIGHT'), kind .. ' releases on the first eligible tick')
    local outputKind=kind=='knife' and 'KNIFE' or 'LASER'
    local projectile=object(outputKind,p)
    projectile.Rotation=0
    weapon.entity=projectile
    weapon.charge=0
    trigger()
    endFrame()
    assert(#announced==1 and announced[1].kind=='q' and Weapons.context(p, ref(projectile))==announced[1].ctx)
    assert(not Weapons.hasPendingQ(p))
end

reset('brimstone',10)
assert(Weapons.requestQ(p,aim,ticks,nil,qDelay,true))
for i=1,10 do
    begin(nil)
    assert(input('IS_ACTION_PRESSED','RIGHT'),'a slow charge must keep holding past the windup')
    weapon.charge=i
    endFrame()
end
begin(nil)
assert(not input('IS_ACTION_PRESSED','RIGHT') and Weapons.hasPendingQ(p))
trigger(); endFrame()
assert(#announced==1 and announced[1].kind=='q')

p.Position = Vector(0, 0)
for _, lockAim in ipairs({true, false}) do
    reset('brimstone', qDelay + 2)
    assert(Weapons.requestQ(p, Vector(1, 0), ticks, Vector(80, 0), qDelay, true, lockAim))
    for i = 1, qDelay + 2 do
        Weapons.trackCursor(p, Vector(0, -80))
        begin(nil)
        if i == qDelay + 2 then
            assert(input('IS_ACTION_PRESSED', lockAim and 'RIGHT' or 'UP'))
        end
        weapon.charge = i
        endFrame()
    end
    begin(nil)
    assert(not input('IS_ACTION_PRESSED', 'RIGHT') and not input('IS_ACTION_PRESSED', 'UP'))
    trigger(); endFrame()
    local heading = announced[1].heading
    assert(heading.X == (lockAim and 1 or 0) and heading.Y == (lockAim and 0 or -1),
        'only MF keeps her cast direction through the full charge')
end

for _, mode in ipairs({{kind='tears', charge=0, precharge=true},{kind='brimstone', charge=3}}) do
    reset(mode.kind,mode.charge)
    assert(Weapons.requestQ(p,aim,ticks,nil,qDelay,mode.precharge))
    for _=1,qDelay-1 do
        begin(Vector(-1,0))
        assert(input('GET_ACTION_VALUE','LEFT')==0 and input('GET_ACTION_VALUE','RIGHT')==0,
            'ordinary weapons and the existing Samira cast must wait')
        endFrame()
    end
    begin(nil)
    assert(input('IS_ACTION_PRESSED','RIGHT') and Weapons.hasPendingQ(p))
    endFrame()
end

reset('brimstone',4)
assert(Weapons.requestQ(p,aim,ticks,nil,qDelay,true))
begin(nil); weapon.charge=1; endFrame()
begin(nil,false)
assert(weapon.charge==0 and not Weapons.hasPendingQ(p),'cancelling the cast clears precharge')

reset('brimstone', 4)
begin(aim)
weapon.charge = 2
Weapons.stopAttack(p)
assert(weapon.charge == 0 and not input('IS_ACTION_PRESSED', 'RIGHT'))
endFrame()
assert(#announced == 0, 'Stop drops an automatic attack and its held charge')
assert(Weapons.requestQ(p, aim, ticks, nil, ticks + qDelay, true, true))
begin(nil)
weapon.charge = 2
Weapons.stopAttack(p)
assert(weapon.charge == 2 and Weapons.hasPendingQ(p) and input('IS_ACTION_PRESSED', 'RIGHT'),
    'Stop leaves an accepted Q and its preparation intact')
endFrame()

reset('ludo',0)
local windupOrb=object('TEAR',p)
weapon.entity=windupOrb
assert(Weapons.requestQ(p,aim,ticks,nil,qDelay,true))
for _=1,qDelay-1 do
    begin(nil); endFrame()
    assert(#announced==0 and Weapons.hasPendingQ(p),'Ludovico cannot pulse during preparation')
end
begin(nil); endFrame()
assert(#announced==1 and announced[1].ctx.persistentPulse)

-- A pending cast can survive an Isaac weapon change during its windup.
reset('ludo',0)
local switchedOrb=object('TEAR',p)
weapon.entity=switchedOrb
assert(Weapons.requestQ(p,aim,ticks,Vector(70,40),qDelay,true))
begin(nil); endFrame()
weapon.id,weapon.entity='tears',nil
for _=2,qDelay-1 do begin(nil); endFrame() end
begin(nil)
local replacementShot=object('TEAR',p)
event('MC_POST_FIRE_TEAR',replacementShot); trigger(); endFrame()
assert(#announced==1 and announced[1].kind=='q' and not announced[1].ctx.persistentPulse
    and Weapons.context(p,ref(replacementShot))==announced[1].ctx,
    'swapping away from Ludovico transfers queued Q to the current weapon')
assert(not Weapons.context(p,ref(switchedOrb)) and switchedOrb.Scale==1,
    'the obsolete orb cannot consume or retain the queued charge')

reset('tears',0)
assert(Weapons.requestQ(p,aim,ticks,Vector(80,40),qDelay,true))
begin(nil); endFrame()
weapon.id='ludo'
for _=2,qDelay+2 do begin(nil); endFrame() end
assert(#announced==0 and Weapons.hasPendingQ(p),'Q waits for the active Ludovico orb to exist')
local newOrb=object('TEAR',p)
weapon.entity=newOrb
begin(nil); endFrame()
local switchedPulse=Weapons.context(p,ref(newOrb))
assert(#announced==1 and switchedPulse.kind=='q' and switchedPulse.persistentPulse and newOrb.Scale==1.18,
    'the new Ludovico orb receives the original queued Q once')
weapon.id,weapon.entity='tears',nil
event('MC_POST_TEAR_UPDATE',newOrb)
assert(not Weapons.context(p,ref(newOrb)) and newOrb.Scale==1,
    'an already-armed orb restores its art and loses Q if its weapon is removed')

reset('rockets',3)
local windupMarker=object('EFFECT',p)
windupMarker.Variant,windupMarker.Position=EffectVariant.TARGET,Vector(30,20)
weapon.entity=windupMarker
assert(Weapons.requestQ(p,aim,ticks,Vector(30,40),qDelay,true))
for _=1,qDelay-1 do
    begin(nil)
    assert(input('GET_ACTION_VALUE','DOWN')==0 and #announced==0,'remote marker waits for the Q release gate')
    endFrame()
end
begin(nil); endFrame()
Weapons.trackCursor(p,Vector(90,20))
begin(nil)
assert(input('GET_ACTION_VALUE','RIGHT')==0 and input('GET_ACTION_VALUE','DOWN')==1,
    'Epic Fetus keeps steering to the Q point through projectile preparation')
trigger(); endFrame()
assert(#announced==1 and announced[1].kind=='q' and announced[1].ctx.weaponType==WeaponType.WEAPON_ROCKETS)

reset('tears', 0)
begin(aim)
assert(math.abs(input('GET_ACTION_VALUE', 'RIGHT') - .6) < 1e-8 and input('GET_ACTION_VALUE', 'UP') == .8)
assert(input('GET_ACTION_VALUE', 'LEFT') == 0 and input('IS_ACTION_TRIGGERED', 'RIGHT'))
assert(attacks == 0 and #announced == 0, 'input alone is not an attack')
local first, second = object('TEAR', p), object('TEAR', p)
event('MC_POST_FIRE_TEAR', first)
trigger()
event('MC_POST_FIRE_TEAR', second)
endFrame()
assert(attacks == 1 and #announced == 1 and announced[1].kind == 'aa')
assert(Weapons.context(p, ref(first)) == Weapons.context(p, ref(second)))
assert(first.Scale == 1 and not first.tint)
local fam = object('FAMILIAR', p)
fam.Player, fam.Variant = p, FamiliarVariant.INCUBUS
local child = object('TEAR', fam)
event('MC_POST_FAMILIAR_FIRE_PROJECTILE', child)
assert(Weapons.context(p, ref(child)) == announced[1].ctx)

begin(aim)
assert(input('IS_ACTION_PRESSED', 'RIGHT') and not input('IS_ACTION_TRIGGERED', 'RIGHT'))
endFrame()

assert(Weapons.requestQ(p, aim, ticks) and not Weapons.requestQ(p, Vector(0, 1), ticks))
begin(Vector(-1, 0))
assert(math.abs(input('GET_ACTION_VALUE', 'RIGHT') - .6) < 1e-8, 'Q should preserve its aim')
local enhanced = object('TEAR', p)
event('MC_POST_FIRE_TEAR', enhanced)
trigger()
endFrame()
local ctx = Weapons.context(p, ref(enhanced))
assert(ctx.kind == 'q' and ctx.damageMultiplier == 1.5 and enhanced.Scale == 1.18 and enhanced.tint)
assert(#announced == 2)
local split = object('TEAR', enhanced)
event('MC_POST_FIRE_SPLIT_TEAR', split, enhanced)
local splitContext, ranged, outputType, isSplit = Weapons.context(p, ref(split))
assert(splitContext == ctx and ranged and outputType == EntityType.ENTITY_TEAR and isSplit and split.Scale == 1.18)
local descendant = object('TEAR', split)
local ordinaryChild = object('TEAR', enhanced)
local splitFirst = object('TEAR', p)
local genericFirst = object('TEAR', p)
assert(Weapons.requestQ(p, Vector(0, 1), ticks))
begin(nil)
for _, tear in ipairs({splitFirst, genericFirst, descendant}) do
    tear.Velocity, tear.ContinueVelocity, tear.TearFlags = Vector(3, -4), Vector(-4, 3), 0x28
end
event('MC_POST_FIRE_SPLIT_TEAR', splitFirst, enhanced)
event('MC_POST_FIRE_TEAR', splitFirst)
event('MC_POST_FIRE_TEAR', genericFirst)
event('MC_POST_WEAPON_FIRE', weapon, Vector(1, 0))
event('MC_POST_FIRE_SPLIT_TEAR', genericFirst, enhanced)
event('MC_POST_FIRE_TEAR', descendant)
event('MC_POST_FIRE_TEAR', ordinaryChild)
local splitBeam = object('LASER', split)
event('MC_POST_FIRE_TECH_LASER', splitBeam)
local splitRocket = object('EFFECT', split)
splitRocket.Variant = EffectVariant.SMALL_ROCKET
event('MC_POST_EFFECT_INIT', splitRocket)
endFrame()
assert(Weapons.hasPendingQ(p) and #announced == 2 and attacks == 2,
    'children from an old attack must not consume the next Q')
for _, tear in ipairs({splitFirst, genericFirst, descendant}) do
    local sourceContext, _, _, splitOutput = Weapons.context(p, ref(tear))
    assert(sourceContext == ctx and splitOutput and tear.data.SamiraItemTaggedSplit)
    assert(tear.Velocity.X == 3 and tear.Velocity.Y == -4 and tear.ContinueVelocity.X == -4
        and tear.ContinueVelocity.Y == 3 and tear.TearFlags == 0x28 and tear.Scale == 1.18)
end
local inheritedContext, _, _, inheritedSplit = Weapons.context(p, ref(ordinaryChild))
assert(inheritedContext == ctx and inheritedSplit == false and ordinaryChild.TearFlags == 0x40,
    'other inherited weapon outputs keep their original classification')
for _, carrier in ipairs({splitBeam, splitRocket}) do
    local inheritedContext, _, _, inheritedSplit = Weapons.context(p, ref(carrier))
    assert(inheritedContext == ctx and inheritedSplit, 'a different carrier preserves split ancestry')
end
begin(nil)
local nextQ = object('TEAR', p)
local interleaved = object('TEAR', p)
interleaved.Velocity, interleaved.TearFlags = Vector(-3, 4), 0x28
event('MC_POST_FIRE_TEAR', interleaved)
event('MC_POST_FIRE_TEAR', nextQ)
trigger()
event('MC_POST_FIRE_SPLIT_TEAR', interleaved, enhanced)
endFrame()
assert(not Weapons.hasPendingQ(p) and #announced == 3 and Weapons.context(p, ref(nextQ)) == announced[3].ctx)
assert(Weapons.context(p, ref(interleaved)) == ctx and interleaved.Scale == 1.18
    and interleaved.Velocity.X == -3 and interleaved.Velocity.Y == 4 and interleaved.TearFlags == 0x28)
event('MC_POST_NEW_ROOM')
assert(not Weapons.context(p, ref(enhanced)))

reset('tears', 0)
local twin = object('FAMILIAR', p)
twin.Player, twin.Variant = p, FamiliarVariant.TWISTED_BABY
assert(Weapons.requestQ(p, aim, ticks))
begin(nil)
local solo = object('TEAR', twin)
event('MC_POST_FAMILIAR_FIRE_PROJECTILE', solo)
event('MC_POST_FIRE_TEAR', solo)
endFrame()
assert(not Weapons.context(p, ref(solo)) and attacks == 0 and Weapons.hasPendingQ(p),
    'a mirror firing on its own must not consume Q or create an attack')

begin(nil)
local earlyTear, earlyBeam = object('TEAR', fam), object('LASER', twin)
earlyTear.Velocity, earlyBeam.AngleDegrees = Vector(10, 0), 0
event('MC_POST_FAMILIAR_FIRE_PROJECTILE', earlyTear)
event('MC_POST_FIRE_TEAR', earlyTear)
event('MC_POST_TRIGGER_WEAPON_FIRED', Vector(1, 0), 1, twin,
    {GetMainEntity = function() return earlyBeam end})
assert(attacks == 0 and Weapons.hasPendingQ(p))
trigger(p, Vector(1, 0))
endFrame()
local shared = announced[1].ctx
assert(attacks == 1 and #announced == 1 and shared.kind == 'q' and not Weapons.hasPendingQ(p))
assert(Weapons.context(p, ref(earlyTear)) == shared and Weapons.context(p, ref(earlyBeam)) == shared,
    'early mirrored outputs must bind to the confirmed Q')
assert(earlyTear.Scale == 1.18, 'overlapping callbacks must not apply Q scaling twice')
assert(math.abs(earlyTear.Velocity.X - 8) < 1e-6, 'mirrored tear rotates and accelerates once')
assert(math.abs(earlyBeam.AngleDegrees - aim:GetAngleDegrees()) < 1e-6, 'mirrored beam follows the player heading')
assert(not Weapons.context(p, ref(solo)), 'an abandoned previous-frame copy must stay independent')

reset('brimstone', 3)
p.missFortune = true
local defaultBeam = {R=1, G=1, B=1, A=1, RO=0, GO=0, BO=0}
assert(Weapons.requestQ(p, aim, ticks))
for i=1,3 do
    begin(nil)
    assert(input('IS_ACTION_PRESSED', 'RIGHT'))
    weapon.charge = i
    endFrame()
    assert(attacks == 0)
end
begin(nil)
assert(input('GET_ACTION_VALUE', 'RIGHT') == 0 and not input('IS_ACTION_PRESSED', 'RIGHT'))
local laser = object('LASER', p)
laser.nativeColor = defaultBeam
weapon.entity = laser
event('MC_POST_FIRE_BRIMSTONE', laser)
weapon.charge = 0
trigger()
endFrame()
local brim, ranged, entityType = Weapons.context(p, ref(p), ref(laser))
assert(brim.kind == 'q' and ranged and entityType == EntityType.ENTITY_LASER and #announced == 1)
assert(laser.tint[2] == .88 and laser.tint[6] == .35,
    'Miss Fortune Q applies the warm T1 accent to the native Brimstone beam')
for _ = 1,10 do assert(Weapons.context(p, ref(p), ref(laser)) == brim) end

for repeatIndex=1,2 do
    for i=1,3 do
        begin(aim)
        assert(input('IS_ACTION_PRESSED', 'RIGHT'))
        weapon.charge = i
        endFrame()
    end
    begin(aim)
    assert(input('GET_ACTION_VALUE', 'RIGHT') == 0)
    weapon.entity = object('LASER', p)
    weapon.entity.nativeColor = repeatIndex == 1 and defaultBeam or {R=.5, G=1, B=.5, A=1, RO=0, GO=0, BO=0}
    event('MC_POST_FIRE_BRIMSTONE', weapon.entity)
    weapon.charge = 0
    trigger()
    endFrame()
    assert(announced[repeatIndex + 1].kind == 'aa')
    if repeatIndex == 1 then
        assert(weapon.entity.tint and weapon.entity.tint[2] == .74,
            'ordinary Miss Fortune Brimstone fires with the T1 accent')
    else
        assert(not weapon.entity.tint, 'native combo tints are preserved')
    end
end
p.missFortune = nil
assert(attacks == 3)
begin(aim)
weapon.charge = 2
endFrame()
assert(Weapons.requestQ(p, aim, ticks))
begin(nil, false)
assert(weapon.charge == 0 and input('GET_ACTION_VALUE', 'RIGHT') == 0)
event('MC_EXECUTE_CMD', 'samiraweapon')
assert(consoleLines[1]:find('pending Q false'))

reset('knife', 2)
assert(Weapons.requestQ(p, aim, ticks))
begin(nil)
weapon.charge = 2
endFrame()
begin(nil)
local knife = object('KNIFE', p)
knife.flying = true
weapon.entity = knife
trigger()
endFrame()
ctx, ranged = Weapons.context(p, ref(p), ref(knife))
assert(ctx.kind == 'q' and not ranged and knife.tint and knife.SpriteScale.X == 1.12)
ticks = ticks + 3
knife.flying = false
event('MC_POST_KNIFE_UPDATE', knife)
assert(not Weapons.context(p, ref(knife)) and knife.SpriteScale.X == 1)

reset('knife', 2)
assert(Weapons.requestQ(p, aim, ticks))
begin(nil)
weapon.charge = 2
endFrame()
begin(nil)
local hybridKnife, hybridBeam = object('KNIFE', p), object('LASER', p)
hybridKnife.flying, hybridKnife.Rotation = true, 5
hybridBeam.AngleDegrees = -7
weapon.entity = hybridKnife
trigger(p, Vector(1, 0))
event('MC_POST_FIRE_BRIMSTONE', hybridBeam)
endFrame()
local hybrid = Weapons.context(p, ref(hybridKnife))
assert(hybrid.kind == 'q' and Weapons.context(p, ref(hybridBeam)) == hybrid and #announced == 1,
    'knife and beam outputs from one native discharge must share Q')
assert(math.abs(hybridKnife.Rotation - 5 - aim:GetAngleDegrees()) < 1e-6)
assert(math.abs(hybridBeam.AngleDegrees + 7 - aim:GetAngleDegrees()) < 1e-6)

reset('bombs', 0)
assert(Weapons.requestQ(p, aim, ticks))
begin(nil)
local launchBomb = object('BOMB', p)
launchBomb.Velocity = Vector(7, 0)
event('MC_POST_FIRE_BOMB', launchBomb)
trigger(p, Vector(1, 0))
endFrame()
local bombQ = Weapons.context(p, ref(launchBomb))
assert(bombQ.kind == 'q' and #announced == 1)

assert(Weapons.requestQ(p, Vector(0, -1), ticks))
local detachedBeam
for _, notification in ipairs({'MC_POST_FIRE_BRIMSTONE', 'MC_POST_LASER_INIT'}) do
    local delayed = object('LASER', p)
    delayed.Parent, delayed.AngleDegrees = launchBomb, 57
    delayed.TearFlags = 0x20
    event(notification, delayed)
    delayed.Parent = nil
    local retained, isRanged = Weapons.context(p, ref(p), ref(delayed))
    assert(retained == bombQ and isRanged, 'a delayed beam keeps its Q after losing its source bomb')
    assert(delayed.AngleDegrees == 57 and delayed.TearFlags == 0x20,
        'inheriting a volley preserves the child beam direction and status')
    event('MC_POST_FIRE_BRIMSTONE', delayed)
    assert(delayed.SpriteScale.X == 1.12 and Weapons.hasPendingQ(p) and #announced == 1,
        'updating the child cannot consume the next Q or scale twice')
    detachedBeam = delayed
end
local independent = object('LASER', p)
event('MC_POST_LASER_INIT', independent)
event('MC_POST_FIRE_BRIMSTONE', independent)
assert(not Weapons.context(p, ref(independent)) and not independent.tint and Weapons.hasPendingQ(p),
    'a player-owned beam without a tagged origin remains independent')
begin(nil)
event('MC_POST_FIRE_BRIMSTONE', detachedBeam)
endFrame()
assert(Weapons.hasPendingQ(p) and #announced == 1 and Weapons.context(p, ref(detachedBeam)) == bombQ,
    'a repeated callback during the next player update still belongs to the original bomb')

local delayedTear, delayedBomb = object('TEAR', p), object('BOMB', p)
local delayedSplit, unrelatedTear = object('TEAR', p), object('TEAR', p)
for _, delayed in ipairs({delayedTear, delayedBomb, delayedSplit, unrelatedTear}) do
    if delayed ~= unrelatedTear then delayed.Parent = launchBomb end
    delayed.Velocity = Vector(0, 5)
    local notification = delayed == delayedBomb and 'MC_POST_FIRE_BOMB' or 'MC_POST_FIRE_TEAR'
    event(notification, delayed)
    delayed.Parent = nil
end
event('MC_POST_FIRE_SPLIT_TEAR', delayedSplit, launchBomb)
begin(nil)
event('MC_POST_FIRE_TEAR', delayedTear)
event('MC_POST_FIRE_BOMB', delayedBomb)
endFrame()
assert(Weapons.hasPendingQ(p) and #announced == 1 and attacks == 1)
event('MC_POST_TEAR_UPDATE', delayedTear)
for _, delayed in ipairs({delayedTear, delayedBomb, delayedSplit}) do
    local inherited, _, _, split = Weapons.context(p, ref(delayed))
    assert(inherited == bombQ and split == (delayed == delayedSplit) and delayed.Velocity.Y == 5,
        'a detached carrier retains its volley and travels along its native heading')
end
assert(delayedTear.Scale == 1.18 and delayedBomb.SpriteScale.X == 1.12
    and delayedSplit.Scale == 1.18 and delayedSplit.data.SamiraItemTaggedSplit and not delayedSplit.TearFlags,
    'split classification arrives before normal tear modifiers, and callbacks scale each output once')
assert(not Weapons.context(p, ref(unrelatedTear)) and unrelatedTear.Scale == 1,
    'mere ownership does not associate a tear with an earlier volley')
local staleTear = object('TEAR', launchBomb)
event('MC_POST_FIRE_TEAR', staleTear)
begin(nil)
local freshBomb = object('BOMB', p)
weapon.entity = delayedBomb
event('MC_POST_FIRE_BOMB', freshBomb)
trigger(p, Vector(1, 0))
endFrame()
assert(#announced == 2 and attacks == 2 and Weapons.context(p, ref(freshBomb)) == announced[2].ctx
    and Weapons.context(p, ref(delayedBomb)) == bombQ and delayedBomb.SpriteScale.X == 1.12,
    'a genuine new discharge claims its fresh output and preserves the previously inherited handle')
Weapons.reset()
assert(not Weapons.context(p, ref(staleTear)) and staleTear.Scale == 1)

for _, kind in ipairs({'sword', 'bone', 'axe'}) do
    reset(kind, 0)
    local melee = object('KNIFE', p)
    melee.Rotation = 0
    weapon.entity = melee
    assert(Weapons.requestQ(p, aim, ticks))
    begin(nil)
    trigger(p, Vector(1, 0))
    endFrame()
    local hitbox = object('KNIFE', p)
    function hitbox:GetHitboxParentKnife() return melee end
    local meleeContext = Weapons.context(p, ref(melee))
    local hitContext, hitRanged, hitType = Weapons.context(p, ref(p), ref(hitbox))
    assert(hitContext == meleeContext and hitContext.kind == 'q' and not hitRanged
        and hitType == EntityType.ENTITY_KNIFE, kind .. ' swing hitbox must inherit the melee Q')
    local unrelated = object('KNIFE', p)
    function unrelated:GetHitboxParentKnife() return nil end
    assert(not Weapons.context(p, ref(unrelated)), 'unrelated knife must not inherit Q from a shared player')
end

reset('fetus', 0)
assert(Weapons.requestQ(p, aim, ticks))
begin(nil)
local bomb = object('BOMB', p)
event('MC_POST_FIRE_BOMB', bomb)
trigger()
endFrame()
assert(Weapons.context(p, ref(bomb)).damageMultiplier == 1.5 and bomb.tint)
local ordinaryBomb = object('BOMB', p)
assert(not Weapons.context(p, ref(ordinaryBomb)))

reset('rockets', 0)
assert(Weapons.requestQ(p, aim, ticks))
begin(nil)
local marker = object('EFFECT', p)
marker.Variant = EffectVariant.TARGET
event('MC_POST_EFFECT_INIT', marker)
assert(not Weapons.context(p, ref(marker)), 'the marker alone must not count as firing')
trigger()
endFrame()
local rocketCtx = Weapons.context(p, ref(marker))
assert(rocketCtx.kind == 'q' and rocketCtx.weaponType == WeaponType.WEAPON_ROCKETS)
ticks = ticks + 25
local rocket = object('EFFECT', p)
rocket.Variant, rocket.Parent = EffectVariant.ROCKET, marker
event('MC_POST_EFFECT_INIT', rocket)
local explosion = object('BOMB', rocket)
assert(Weapons.context(p, ref(rocket)) == rocketCtx and Weapons.context(p, ref(explosion)) == rocketCtx)
local unrelatedRocket = object('EFFECT', p)
unrelatedRocket.Variant = EffectVariant.ROCKET
event('MC_POST_EFFECT_INIT', unrelatedRocket)
assert(not Weapons.context(p, ref(unrelatedRocket)), 'shared player spawner must not link unrelated rockets')

reset('ludo', 0)
assert(not Weapons.requestQ(p, aim, ticks), 'no orb means no charge or Q cooldown')
local orb = object('TEAR', p)
weapon.entity = orb
local baseline = Weapons.context(p, ref(orb))
assert(baseline.kind == 'aa' and baseline.damageMultiplier == 1)
assert(Weapons.context(p, ref(orb)) == baseline)
assert(Weapons.requestQ(p, aim, ticks))
begin(nil)
endFrame()
local pulse = Weapons.context(p, ref(orb))
assert(pulse.persistentPulse and pulse.kind == 'q' and pulse.damageMultiplier == 1.5 and orb.Scale == 1.18)
assert(not Weapons.requestQ(p, aim, ticks), 'a pending pulse cannot be stacked')
assert(Weapons.context(p, ref(orb)) == pulse, 'unaccepted hit attempts do not spend the pulse')
local pulseChild = object('TEAR', orb)
event('MC_POST_FIRE_SPLIT_TEAR', pulseChild, orb)
local childContext, _, _, childSplit = Weapons.context(p, ref(pulseChild))
assert(childContext == pulse and childSplit, 'a split child inherits the pending Q pulse')
pulse.accepted = true
assert(Weapons.context(p, ref(orb)) == baseline and orb.Scale == 1 and orb.tint == 'native')
event('MC_POST_TEAR_UPDATE', pulseChild)
childContext, _, _, childSplit = Weapons.context(p, ref(pulseChild))
assert(childContext == pulse and childSplit and childContext.damageMultiplier == 1.5,
    'a late split keeps its Q context after the orb consumes the pulse')
ticks = ticks + 5
local nextPulse = Weapons.context(p, ref(orb))
assert(nextPulse.kind == 'aa' and nextPulse ~= baseline and Weapons.context(p, ref(orb)) == nextPulse)

orb.Position = Vector(30, 20)
begin(Vector(-1, 0), true, Vector(30, 40))
assert(input('GET_ACTION_VALUE', 'RIGHT') == 0 and input('GET_ACTION_VALUE', 'DOWN') == 1)
endFrame()
orb.Position = Vector(30, 37)
begin(Vector(-1, 0), true, Vector(30, 40))
assert(input('GET_ACTION_VALUE', 'LEFT') == 0 and input('GET_ACTION_VALUE', 'DOWN') == 0)
endFrame()

reset('rockets', 4)
assert(not Weapons.context(p, ref(pulseChild)), 'a split child cannot retain its context after reset')
marker = object('EFFECT', p)
marker.Variant, marker.Position = EffectVariant.TARGET, Vector(30, 20)
weapon.entity = marker
assert(Weapons.requestQ(p, Vector(-1, 0), ticks, Vector(30, 40)))
weapon.charge = 4
begin(Vector(1, 0), true, Vector(90, 20))
assert(input('GET_ACTION_VALUE', 'RIGHT') == 0 and input('GET_ACTION_VALUE', 'DOWN') == 1,
    'Epic Fetus must keep steering toward the locked Q point, even with full charge')
endFrame()
marker.Position = Vector(30, 37)
begin(Vector(1, 0), true, Vector(90, 20))
assert(input('GET_ACTION_VALUE', 'RIGHT') == 0 and input('GET_ACTION_VALUE', 'DOWN') == 0)
trigger()
endFrame()
assert(#announced == 1 and announced[1].kind == 'q' and Weapons.context(p, ref(marker)) == announced[1].ctx)

reset('tears', 0)
p.TearRange = 375
assert(Weapons.attackRange(p, 165) == 300 and not Weapons.passesGrid(p))
TearFlags, p.TearFlags = {TEAR_SPECTRAL = 8, TEAR_LUDOVICO = 16}, 8
assert(Weapons.passesGrid(p))
p.TearFlags = 0
for _, kind in ipairs({'brimstone', 'laser', 'rockets'}) do
    weapon.id = kind
    assert(Weapons.attackRange(p, 165) == 800 and Weapons.passesGrid(p))
end
weapon.id = 'sword'
assert(Weapons.attackRange(p, 165) == 48 and not Weapons.passesGrid(p))

local function near(actual, expected)
    assert(math.abs(actual - expected) < 1e-6, ('got %.6f, expected %.6f'):format(actual, expected))
end

-- The fake engine rounds to right, then creates two tears at fixed spread
-- angles. Verify trajectories, not just the values we handed to input hooks.
reset('tears', 0)
local diagonal = Vector(1, 1)
function p:GetTearMovementInheritance() return Vector(1, -1) end
begin(diagonal)
local lead, follow = object('TEAR', p), object('TEAR', p)
lead.Velocity = Vector(10, 0):Rotated(-12) + Vector(1, -1)
lead.ContinueVelocity = Vector(10, 0):Rotated(-12)
follow.Velocity = Vector(10, 0):Rotated(12) + Vector(1, -1)
event('MC_POST_FIRE_TEAR', lead)
trigger(nil, Vector(1, 0))
event('MC_POST_FIRE_TEAR', follow)
endFrame()
near((lead.Velocity - Vector(1, -1)):GetAngleDegrees(), 33)
near((follow.Velocity - Vector(1, -1)):GetAngleDegrees(), 57)
near((lead.Velocity - Vector(1, -1)):Length(), 10)
near(lead.ContinueVelocity:GetAngleDegrees(), 33)
near(announced[1].heading:GetAngleDegrees(), 45)
local lateral = object('TEAR', lead)
lateral.Velocity = Vector(0, -4)
event('MC_POST_FIRE_SPLIT_TEAR', lateral, lead)
near(lateral.Velocity:GetAngleDegrees(), -90)

-- Exercise cardinal (zero rotation) and diagonal (rotated) native volleys.
-- Flight time is set by the native spawn's own vertical parameters.
for _,angle in ipairs({0,45,90,135,180,225,270,315}) do
    local aimed = Vector(1,0):Rotated(angle)
    local native = Vector(1,0):Rotated(math.floor((angle+45)/90)*90)
    local ranges = {}
    for _,kind in ipairs({'aa','q'}) do
        reset('tears',0)
        if kind=='q' then assert(Weapons.requestQ(p,aimed,ticks)) end
        begin(aimed)
        local tear = object('TEAR',p)
        tear.Velocity = native*9 + p:GetTearMovementInheritance(native)
        tear.ContinueVelocity = native*9
        tear.Height, tear.FallingSpeed, tear.FallingAcceleration = -22,-1,.25
        weapon.entity = tear -- The fire callback and weapon main entity report the same tear.
        event('MC_POST_FIRE_TEAR',tear)
        trigger(nil,native)
        endFrame()
        local intrinsic = tear.Velocity - p:GetTearMovementInheritance(aimed)
        near((intrinsic - aimed*(kind=='q' and 12 or 9)):Length(),0)
        near((tear.ContinueVelocity - intrinsic):Length(),0)
        local height,fallSpeed,ticksInAir = tear.Height,tear.FallingSpeed,0
        while height < 0 do
            height = height + fallSpeed
            fallSpeed = fallSpeed + tear.FallingAcceleration
            ticksInAir = ticksInAir + 1
        end
        ranges[kind] = tear.Velocity:Length()*ticksInAir
    end
    assert(ranges.q > ranges.aa, 'ranged Q fell short of an AA at angle '..angle)
end

reset('laser', 0)
assert(Weapons.requestQ(p, Vector(-1, 1), ticks))
begin(Vector(1, 0))
local beam = object('LASER', p)
beam.AngleDegrees, beam.StartAngleDegrees, beam.LastAngleDegrees = 190, 188, 190
event('MC_POST_FIRE_TECH_LASER', beam)
trigger(nil, Vector(-1, 0))
endFrame()
near(beam.AngleDegrees, 145)
near(beam.StartAngleDegrees, 143)
assert(Weapons.context(p, ref(p), ref(beam)).kind == 'q')

reset('knife', 0)
begin(Vector(-1, 1))
knife = object('KNIFE', p)
knife.Rotation = 90
weapon.entity = knife
trigger(nil, Vector(0, 1))
endFrame()
near(knife.Rotation, 135)

reset('fetus', 0)
assert(Weapons.requestQ(p, Vector(-1,-1), ticks))
begin(Vector(-1, -1))
local chargedBomb = object('BOMB', p)
chargedBomb.Velocity = Vector(-8, 0)
event('MC_POST_FIRE_BOMB', chargedBomb)
trigger(nil, Vector(-1, 0))
endFrame()
near(chargedBomb.Velocity:GetAngleDegrees(), -135)
near(chargedBomb.Velocity:Length(), 8)

reset('techx', 0)
assert(Weapons.requestQ(p, diagonal, ticks))
begin(diagonal)
local ring = object('LASER', p)
ring.ring, ring.Velocity = true, Vector(8, 0)
event('MC_POST_FIRE_TECH_X_LASER', ring)
trigger(nil, Vector(1, 0))
endFrame()
near(ring.Velocity:GetAngleDegrees(), 45)
near(ring.Velocity:Length(), 8)

print('Passed native charge, grouped volleys, melee hitboxes, cardinal-to-cursor rotation, rockets and Ludovico.')
''')
