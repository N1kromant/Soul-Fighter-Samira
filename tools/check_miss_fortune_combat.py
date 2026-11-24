from pathlib import Path
from lupa.lua54 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
lua = LuaRuntime()
lua.execute(r'''
local mt = {}
mt.__index = mt
function mt.__add(a,b) return Vector(a.X+b.X,a.Y+b.Y) end
function mt.__sub(a,b) return Vector(a.X-b.X,a.Y-b.Y) end
function mt.__mul(a,b) if type(a)=='number' then a,b=b,a end return Vector(a.X*b,a.Y*b) end
function mt.__div(a,b) return Vector(a.X/b,a.Y/b) end
function Vector(x,y) return setmetatable({X=x,Y=y},mt) end
function EntityRef(e) return e end
function Color(...) return {} end
function GetPtrHash(e) return e.id end
TearFlags={TEAR_NORMAL=0,TEAR_POISON=1}
EntityType={ENTITY_FIREPLACE=33}
GridEntityType={GRID_TNT=12,GRID_POOP=14,GRID_ROCK=2}
GridCollisionClass={COLLISION_NONE=0,COLLISION_SOLID=3}
all = {}
Isaac = {GetRoomEntities=function() return all end}
function enemy(id,x,y,hp)
 local e={id=id,Position=Vector(x,y),HitPoints=hp or 100, hits=0}
 function e:Exists() return self.HitPoints>0 end
 function e:IsDead() return self.HitPoints<=0 end
 function e:IsActiveEnemy() return true end
 function e:IsVulnerableEnemy() return true end
 function e:TakeDamage(n) self.hits=self.hits+1; self.HitPoints=self.HitPoints-n; return true end
 function e:AddSlowing(_,duration,strength)
    self.slow=true
    self.slowCalls=(self.slowCalls or 0)+1
    self.slowDuration,self.slowStrength=duration,strength
 end
 function e:ToNPC() return self end
 function e:ApplyTearflagEffects(position, flags, player, damage)
    self.effect = {position=position,flags=flags,player=player,damage=damage}
 end
 return e
end
p={Position=Vector(0,0),Damage=4}
items={newAttack=function(p,k,t) return {kind=k, origin=p.Position} end,
 withContext=function(c,f) return f() end, onCast=function() end}
weapons={requestQ=function(_,_,_,_,releaseAt,chargeDuringWindup,lockAim)
    qReleaseAt,qPrecharge,qLockAim=releaseAt,chargeDuringWindup,lockAim
    return true
end}
''')
combat = lua.execute((ROOT / 'src/samira-testroom/mod/miss_fortune_combat.lua').read_text(encoding='utf-8'))
lua.globals().Combat = combat
lua.execute(r'''
local function cue(state,kind)
    for _,effect in ipairs(state.fx) do
        if effect.kind==kind then return effect end
    end
end
local s=Combat.new(0)
local doubleUp=Combat.new(0)
assert(Combat.cast(doubleUp,'q',p,Vector(100,0),10,nil,items,weapons))
assert(qReleaseAt==18 and qPrecharge and qLockAim,'Double Up schedules its eight-tick cast and parallel weapon charge')
do
    p.MaxFireDelay=3
    local fast=Combat.new(0)
    assert(Combat.cast(fast,'q',p,Vector(100,0),10,nil,items,weapons))
    assert(qReleaseAt==13 and fast.ready.q==130,'attack speed shortens the cast and leaves cooldown intact')
    local haste={cooldown=function(_,_,base) return base/2 end}
    local fastHaste=Combat.new(0)
    assert(Combat.cast(fastHaste,'q',p,Vector(100,0),10,nil,haste,weapons))
    assert(qReleaseAt==13 and fastHaste.ready.q==70,'ability haste reduces the cooldown only')
    p.MaxFireDelay=120
    assert(Combat.cast(Combat.new(0),'q',p,Vector(100,0),10,nil,items,weapons) and qReleaseAt==34,
        'very slow fire can extend the windup only to the Isaac cap')
    p.MaxFireDelay=nil
end
local a,b,c,d=enemy(1,30,0,3),enemy(2,60,0),enemy(3,-20,0),enemy(7,100,0)
all={a,b,c,d}
local ctx={kind='q',origin=p.Position}
assert(Combat.damageMultiplier(s,ctx,a,1)==1.35)
assert(Combat.damageMultiplier(s,ctx,a,1)==1.35) -- preview must not mutate
s.ready.w=200
Combat.acceptHit(s,ctx,1,a,4,p,nil,items,5,{flags=TearFlags.TEAR_POISON,lethal=true})
assert(s.ready.w==140 and Combat.damageMultiplier(s,ctx,a,1)==1)
assert(cue(s,'qImpact').point.X==a.Position.X,'the confirmed native Q creates its primary impact')
Combat.acceptHit(s,ctx,1,b,4,p,nil,items)
assert(#s.pendingBounce==1 and s.ready.w==140)
assert(Combat.loveTapTarget(s)==a and Combat.damageMultiplier(s,ctx,b,1)==1,
    'Extra tears in a native volley cannot replace the real Love Tap mark')
Combat.update(s,p,2,nil,items)
assert(b.hits==0 and d.hits==0 and cue(s,'bounce').to.X==100 and not cue(s,'bounce').hit)
d.Position=Vector(102,0)
Combat.update(s,p,5,nil,items)
assert(d.hits==0 and cue(s,'bounce').to.X==102)
local bounceCrit
items.withContext=function(action,fn)
    bounceCrit=action.crit and action.corsairSecondary
    local dealt=fn()
    Combat.acceptHit(s,action,6,d,5,p,nil,items)
    return dealt
end
Combat.update(s,p,6,nil,items)
assert(bounceCrit and b.hits==0 and c.hits==0 and d.hits==1 and d.HitPoints==95)
assert(cue(s,'bounce').hit,'show the secondary impact on confirmed damage only')
assert(d.effect.flags==TearFlags.TEAR_POISON and d.effect.damage==5 and d.effect.player==p)
assert(not ctx.crit and not ctx.corsairSecondary and #s.pendingBounce==0)
assert(Combat.loveTapTarget(s)==d and s.ready.w==80,'Q bounce applies Love Tap to its own target')
do
    local multi=Combat.new(0)
    local lead,nearby,spare=enemy(20,25,0),enemy(21,70,0),enemy(22,110,24)
    local volley={kind='q',origin=p.Position}
    all={lead,nearby,spare}
    items.withContext=function(_,f) return f() end
    Combat.acceptHit(multi,volley,1,lead,4,p,nil,items)
    Combat.update(multi,p,2,nil,items)
    assert(cue(multi,'bounce').to.X==70)
    Combat.acceptHit(multi,volley,3,nearby,4,p,nil,items)
    for frame=3,8 do Combat.update(multi,p,frame,nil,items) end
    assert(nearby.hits==0 and spare.hits==1 and #multi.pendingBounce==0,
        'Q ricochet should divert to an untouched enemy if multishot beats it to the target')
end
all={a,b,c,d}
local solid={CheckLine=function() return false end}
local blocked=Combat.new(0)
Combat.acceptHit(blocked,{kind='q',origin=p.Position},10,a,4,p,solid,items)
Combat.update(blocked,p,11,solid,items)
assert(#blocked.pendingBounce==0 and cue(blocked,'qDud') and not cue(blocked,'bounce'),
    'a blocked bounce ends as a non-damaging dud')
local spectral=Combat.new(0)
Combat.acceptHit(spectral,{kind='q',origin=p.Position},10,a,4,p,solid,items,5,{throughGrid=true})
Combat.update(spectral,p,11,solid,items)
assert(#spectral.pendingBounce==1 and cue(spectral,'bounce').to.X==60)
do
    local straight, side, lead=enemy(41,135,0),enemy(42,49,16),enemy(43,30,0)
    local state=Combat.new(0)
    all={lead,side,straight}
    Combat.acceptHit(state,{kind='q',origin=p.Position},1,lead,4,p,nil,items)
    Combat.update(state,p,2,nil,items)
    assert(state.pendingBounce[1].destination==straight,'Q prefers the straight path over a nearer side target')

    local inFlight=Combat.new(0)
    local room={CheckLine=function(_,_,target) return target.Y<15 end}
    all={lead,straight}
    Combat.acceptHit(inFlight,{kind='q',origin=p.Position},1,lead,4,p,room,items)
    Combat.update(inFlight,p,2,room,items)
    straight.Position=Vector(135,25)
    for frame=3,6 do Combat.update(inFlight,p,frame,room,items) end
    assert(straight.hits==0 and #inFlight.pendingBounce==0,'an ordinary ricochet cannot follow its target through a wall')

    local closeSide, farSide=enemy(44,38,38),enemy(45,48,-80)
    local wide=Combat.new(0)
    all={lead,closeSide,farSide}
    Combat.acceptHit(wide,{kind='q',origin=p.Position},1,lead,4,p,nil,items)
    Combat.update(wide,p,2,nil,items)
    assert(wide.pendingBounce[1].destination==closeSide,'the widest ricochet angle is reserved for very close targets')
end
assert(Combat.cast(s,'w',p,Vector(1,0),140,nil,items,weapons))
assert(Combat.attackSpeed(s,141)>1 and Combat.attackSpeed(s,260)==1)
assert(Combat.speed(s,140)==1.2 and Combat.strut(s,140)==1 and Combat.strut(s,260)==0)
local waiting=Combat.new(0)
assert(Combat.speed(waiting,119)==1 and Combat.speed(waiting,120)==1.1 and Combat.speed(waiting,210)==1.2)
Combat.tookDamage(s,200); assert(Combat.speed(s,201)==1)
local e=Combat.new(0); a,b,c=enemy(4,100,0),enemy(5,100,120),enemy(6,-20,0); all={a,b,c}
assert(Combat.cast(e,'e',p,Vector(100,0),1,nil,items,weapons))
for frame=1,8 do Combat.update(e,p,frame,nil,items) end
assert(a.hits==0 and not a.slow)
for frame=9,69 do Combat.update(e,p,frame,nil,items) end
assert(a.hits==8 and a.HitPoints==94 and b.hits==0 and a.slow and not e.rain)
do
    local field=Combat.new(0)
    local entering=enemy(56,100,0)
    all={entering}
    assert(Combat.cast(field,'e',p,p.Position,1,nil,items,weapons),'E can be centered at the caster')
    assert(field.rain.center.X==p.Position.X and field.rain.center.Y==p.Position.Y)
    for frame=1,9 do Combat.update(field,p,frame,nil,items) end
    assert(entering.hits==0 and not entering.slow)
    entering.Position=Vector(80,0)
    Combat.update(field,p,10,nil,items)
    assert(entering.slow and entering.hits==0 and entering.slowStrength==.6,
        'E immediately slows enemies entering between damage pulses')
    for frame=11,15 do Combat.update(field,p,frame,nil,items) end
    assert(entering.slowCalls>1 and entering.slowCalls<6 and entering.hits==0,
        'the field refreshes slow on its own cadence')
    Combat.update(field,p,16,nil,items)
    assert(entering.hits==1,'the next scheduled pulse deals damage once')
    entering.Position=Vector(90,0)
    local previousCalls=entering.slowCalls
    for frame=17,69 do Combat.update(field,p,frame,nil,items) end
    assert(entering.slowCalls==previousCalls and entering.hits==1 and not field.rain,
        'enemies outside the circle stop receiving slow or damage')

    local ranged=Combat.new(0)
    assert(Combat.cast(ranged,'e',p,Vector(400,0),1,nil,items,weapons) and ranged.rain.center.X==260,
        'a distant ground cast snaps to maximum range')
    assert(not Combat.cast(Combat.new(0),'q',p,p.Position,1,nil,items,weapons)
        and not Combat.cast(Combat.new(0),'r',p,p.Position,1,nil,items,weapons),
        'directional spells still require a valid heading')
end

local function fireplace(id,x,y,variant)
    local f=enemy(id,x,y)
    f.Type,f.Variant=EntityType.ENTITY_FIREPLACE,variant
    function f:TakeDamage(amount, flags, source)
        assert(not inItemContext and flags==0 and source==p,'scenery must not activate champion or item hit effects')
        self.HitPoints,self.hits=self.HitPoints-amount,self.hits+1
        return true
    end
    return f
end
local function grid(x,y,kind,state,collision)
    local g={Position=Vector(x,y),kind=kind,State=state or 0,CollisionClass=collision or 3,hits=0}
    function g:GetType() return self.kind end
    function g:HurtWithSource(amount,source)
        assert(not inItemContext and amount==1 and source==p,'grid damage should be a native chip from the caster')
        self.hits=self.hits+1
        return true
    end
    return g
end
local function roomWith(...)
    local cells={...}
    return {GetGridSize=function() return #cells end,GetGridEntity=function(_,index) return cells[index+1] end}
end
local originalContext=items.withContext
items.withContext=function(_,hit)
    inItemContext=true
    local accepted=hit()
    inItemContext=false
    return accepted
end
local ordinary,red,blue,outsideFire=fireplace(31,115,0,0),fireplace(32,100,0,1),fireplace(33,100,0,2),fireplace(34,100,86,0)
local poop=grid(100,0,GridEntityType.GRID_POOP)
local tnt=grid(80,0,GridEntityType.GRID_TNT)
local rock=grid(110,0,GridEntityType.GRID_ROCK)
local brokenPoop=grid(110,0,GridEntityType.GRID_POOP,1000)
local brokenTnt=grid(110,0,GridEntityType.GRID_TNT,0,GridCollisionClass.COLLISION_NONE)
local distant=grid(100,86,GridEntityType.GRID_POOP)
local sceneryRoom=roomWith(poop,tnt,rock,brokenPoop,brokenTnt,distant)
all={ordinary,red,blue,outsideFire}
local rainfall=Combat.new(0)
assert(Combat.cast(rainfall,'e',p,Vector(100,0),1,sceneryRoom,items,weapons))
for frame=1,8 do Combat.update(rainfall,p,frame,sceneryRoom,items) end
assert(ordinary.hits==0 and poop.hits==0 and tnt.hits==0,'E props must wait for the rain impact')
for frame=9,69 do Combat.update(rainfall,p,frame,sceneryRoom,items) end
assert(ordinary.hits==8 and red.hits==8 and not ordinary.slow and not red.slow,'E hits normal and red fires on each pulse')
assert(blue.hits==0 and outsideFire.hits==0 and poop.hits==8 and tnt.hits==8
    and rock.hits==0 and brokenPoop.hits==0 and brokenTnt.hits==0 and distant.hits==0,
    'E chips intact tear-damageable grids within its radius and respects protected props')
local fireTap=Combat.new(0)
assert(Combat.damageMultiplier(fireTap,{kind='q'},ordinary,10)==1)
Combat.acceptHit(fireTap,{kind='q',origin=p.Position},10,ordinary,3,p,sceneryRoom,items)
assert(not Combat.loveTapTarget(fireTap) and #fireTap.pendingBounce==0,'Q props do not open Love Tap or a ricochet')
local nearPoop=grid(65,0,GridEntityType.GRID_POOP)
local farTnt=grid(240,0,GridEntityType.GRID_TNT)
local behind=grid(-40,0,GridEntityType.GRID_POOP)
local beyond=grid(301,0,GridEntityType.GRID_POOP)
local offCone=grid(30,40,GridEntityType.GRID_POOP)
sceneryRoom=roomWith(nearPoop,farTnt,behind,beyond,offCone,rock)
local spray=Combat.new(0)
assert(Combat.cast(spray,'r',p,Vector(100,0),1,sceneryRoom,items,weapons))
Combat.update(spray,p,3,sceneryRoom,items)
assert(nearPoop.hits==1 and farTnt.hits==0 and ordinary.hits==8,'R props track the traveling wave')
Combat.update(spray,p,4,sceneryRoom,items)
assert(nearPoop.hits==1 and farTnt.hits==0 and ordinary.hits==9,'a grid on the front boundary is hit once')
Combat.update(spray,p,5,sceneryRoom,items)
assert(nearPoop.hits==1 and farTnt.hits==1 and behind.hits==0 and beyond.hits==0 and offCone.hits==0 and rock.hits==0)
items.withContext=originalContext
a,b,c=enemy(8,45,0),enemy(9,230,70),enemy(10,-20,0)
local far=enemy(11,240,0)
local outside=enemy(12,230,72)
local rejected=enemy(13,35,-9)
function rejected:TakeDamage() return false end
all={a,b,c,far,outside,rejected}
local r=Combat.new(0); assert(Combat.cast(r,'r',p,Vector(100,0),1,nil,items,weapons))
assert(r.r.halfAngle==17,'the hitbox follows the Skin69 Bullet Time indicator half-angle')
Combat.update(r,p,1,nil,items); Combat.update(r,p,2,nil,items)
assert(a.hits==0 and r.r.waves==nil and r.barrageWave==nil,'R preparation must not fire a wave')
Combat.update(r,p,3,nil,items)
assert(a.hits==1 and far.hits==0,'R cannot hit a distant enemy before the bullet front arrives')
assert(#r.fx==1 and r.fx[1].kind=='rImpact' and r.fx[1].point.X==a.Position.X,
    'R draws an impact only on an enemy that accepted damage')
Combat.update(r,p,4,nil,items); assert(a.hits==1 and far.hits==0)
Combat.update(r,p,5,nil,items); assert(a.hits==1 and far.hits==1)
assert(r.r.interval==6 and r.r.travel==3)
for frame=6,90 do Combat.update(r,p,frame,nil,items) end
assert(a.hits==15 and far.hits==15 and b.hits==15 and c.hits==0 and outside.hits==0,
    'expected fifteen waves in the cone')
Combat.cancelUltimate(r); Combat.update(r,p,91,nil,items); assert(a.hits==15)
local cancelled=Combat.new(0)
assert(Combat.cast(cancelled,'r',p,Vector(100,0),1,nil,items,weapons))
Combat.update(cancelled,p,3,nil,items); Combat.cancelUltimate(cancelled)
for frame=4,10 do Combat.update(cancelled,p,frame,nil,items) end
assert(a.hits==16 and far.hits==16,'cancel stops new waves while fired bullets still arrive')
local interrupted=Combat.new(0)
assert(Combat.cast(interrupted,'r',p,Vector(100,0),1,nil,items,weapons))
Combat.update(interrupted,p,1,nil,items); Combat.cancelUltimate(interrupted)
for frame=2,10 do Combat.update(interrupted,p,frame,nil,items) end
assert(a.hits==16 and far.hits==16,'cancel during preparation must never launch')
local crossed=Combat.new(0)
assert(Combat.cast(crossed,'r',p,Vector(100,0),1,nil,items,weapons))
Combat.update(crossed,p,3,nil,items); Combat.resetRoom(crossed)
Combat.update(crossed,p,4,nil,items); Combat.update(crossed,p,5,nil,items)
assert(a.hits==17 and far.hits==16,'room transition clears in-flight waves')
do
    local fromFirst, fromSecond = enemy(51,240,0), enemy(52,45,80)
    all={fromFirst,fromSecond}
    local displaced=Combat.new(0)
    assert(Combat.cast(displaced,'r',p,Vector(100,0),1,nil,items,weapons))
    Combat.update(displaced,p,3,nil,items)
    assert(fromFirst.hits==0 and fromSecond.hits==0)
    p.Position=Vector(0,80)
    Combat.update(displaced,p,4,nil,items)
    assert(displaced.r.origin.Y==80,'guide and next wave follow a forced displacement during R')
    assert(displaced.barrageWave.origin.Y==0,'already fired waves retain their own launch origin')
    Combat.update(displaced,p,5,nil,items)
    assert(fromFirst.hits==1 and fromSecond.hits==0,'first wave lands on the original path')
    for frame=6,9 do Combat.update(displaced,p,frame,nil,items) end
    assert(displaced.barrageWave.origin.Y==80 and fromSecond.hits==1 and fromFirst.hits==1,
        'next wave fires from the new position along the locked direction')
    p.Position=Vector(0,0)
end
assert(Combat.cast(r,'q',p,Vector(100,0),92,nil,items,weapons))
Combat.acceptHit(r,{kind='q',origin=p.Position},92,a,4,p,nil,items)
Combat.resetRoom(r); Combat.update(r,p,93,nil,items)
assert(#r.pendingBounce==0 and r.rain==nil and r.lastTarget==nil and not Combat.loveTapTarget(r))
''')
print('Miss Fortune combat checks passed')

# Reuse the native adapter's callback fixture, before its scenario section.
# Run these regressions in the same Lua chunk so the fixture's locals stay local.
import ast
adapter_tree = ast.parse((ROOT / 'tools/check_samira_weapons.py').read_text(encoding='utf-8'))
adapter_chunk = next(
    node.value.args[0].value for node in adapter_tree.body
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)
    and isinstance(node.value.func, ast.Attribute) and node.value.func.attr == 'execute'
)
fixture = adapter_chunk.split('-- Miss Fortune\'s cast timer', 1)[0]
assert fixture != adapter_chunk, 'native adapter fixture boundary must exist'
adapter_lua = LuaRuntime()
adapter_lua.globals().weaponSource = (ROOT / 'src/samira-testroom/mod/samira_weapons.lua').read_text(encoding='utf-8')
adapter_lua.execute(fixture + r'''
-- Slow charged Q retains MF's cast direction after the windup.
p.Position=Vector(0,0)
reset('brimstone',20)
assert(Weapons.requestQ(p,Vector(1,0),ticks,Vector(100,0),2,true,true))
for _=1,3 do begin(nil); endFrame() end
Weapons.trackCursor(p,Vector(0,100))
begin(nil)
assert(input('GET_ACTION_VALUE','RIGHT')==1 and input('GET_ACTION_VALUE','DOWN')==0,
    'Miss Fortune Q must keep its heading throughout a slow native charge')
endFrame()
-- Ordinary Samira requests retain their existing cursor tracking.
reset('brimstone',20)
assert(Weapons.requestQ(p,Vector(1,0),ticks,Vector(100,0),2,true))
for _=1,3 do begin(nil); endFrame() end
p.Position=Vector(0,0)
Weapons.trackCursor(p,Vector(0,100))
begin(nil)
assert(input('GET_ACTION_VALUE','DOWN')==1 and input('GET_ACTION_VALUE','RIGHT')==0)
endFrame()

-- Delayed children retain the original attack after losing engine ancestry.
-- These are carrier-level simulations, not item-specific engine validation.
for _,kind in ipairs({'TEAR','BOMB','LASER'}) do
    reset('tears',0)
    assert(Weapons.requestQ(p,Vector(1,0),ticks))
    begin(Vector(1,0))
    local root=object('TEAR',p)
    event('MC_POST_FIRE_TEAR',root)
    trigger(); endFrame()
    local original=Weapons.context(p,ref(root))
    local child=object(kind,root)
    event(kind=='TEAR' and 'MC_POST_FIRE_TEAR' or kind=='BOMB' and 'MC_POST_FIRE_BOMB'
        or 'MC_POST_FIRE_TECH_LASER',child)
    child.SpawnerEntity=nil
    assert(Weapons.context(p,ref(child))==original,
        kind .. ' delayed output must retain Q when its engine parent is detached')
    local split=object('TEAR',root)
    event('MC_POST_FIRE_SPLIT_TEAR',split,root)
    local descendant=object(kind,split)
    event(kind=='TEAR' and 'MC_POST_FIRE_TEAR' or kind=='BOMB' and 'MC_POST_FIRE_BOMB'
        or 'MC_POST_FIRE_TECH_LASER',descendant)
    descendant.SpawnerEntity=nil
    local inherited,_,_,isSplit=Weapons.context(p,ref(descendant))
    assert(inherited==original and isSplit,kind .. ' delayed descendant must retain split exclusion')
    Weapons.reset()
    assert(not Weapons.context(p,ref(child)), 'room reset invalidates retained ancestry')
end
''')
print('Miss Fortune charged-aim and delayed-carrier regression checks passed')
