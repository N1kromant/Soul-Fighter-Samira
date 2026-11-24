from pathlib import Path
import re
import sys
from types import SimpleNamespace
from xml.etree import ElementTree as ET
from lupa.lua54 import LuaRuntime
from PIL import Image
root = Path(__file__).resolve().parents[1]
lua = LuaRuntime()
lua.globals().sources = lua.table_from({p.stem:p.read_text(encoding='utf-8') for p in (root/'src/samira-testroom/mod').glob('*.lua')})
lua.execute(r'''
local mt={}; mt.__index=mt
function mt.__add(a,b) return Vector(a.X+b.X,a.Y+b.Y) end
function mt.__sub(a,b) return Vector(a.X-b.X,a.Y-b.Y) end
function mt.__mul(a,b) return Vector(a.X*b,a.Y*b) end
function mt.__div(a,b) return Vector(a.X/b,a.Y/b) end
function mt:Length() return math.sqrt(self.X*self.X+self.Y*self.Y) end
function mt:Distance(other) return (self-other):Length() end
function mt:Normalized() local n=self:Length(); return self/n end
function mt:Dot(b) return self.X*b.X+self.Y*b.Y end
function mt:GetAngleDegrees() return math.deg(math.atan(self.Y,self.X)) end
function mt:Rotated(a) local r=math.rad(a); return Vector(self.X*math.cos(r)-self.Y*math.sin(r),self.X*math.sin(r)+self.Y*math.cos(r)) end
Vector=setmetatable({}, {__call=function(_,x,y) return setmetatable({X=x,Y=y},mt) end})
Vector.Zero=Vector(0,0)
local idleRoll,idleRandomCalls=99,0
function RNG()
 return {SetSeed=function() end, RandomInt=function(_,limit)
  assert(limit==100); idleRandomCalls=idleRandomCalls+1; return idleRoll
 end}
end
Keyboard={KEY_Q=1,KEY_W=2,KEY_E=3,KEY_A=4,KEY_RIGHT=5,KEY_LEFT=6,KEY_UP=7,KEY_DOWN=8,
 KEY_ENTER=9,KEY_LEFT_CONTROL=10,KEY_RIGHT_CONTROL=11,KEY_1=12,KEY_2=13,KEY_3=14,KEY_4=15,KEY_5=16,KEY_6=17,
 KEY_LEFT_SHIFT=18,KEY_RIGHT_SHIFT=19}
ButtonAction={ACTION_LEFT=1,ACTION_RIGHT=2,ACTION_UP=3,ACTION_DOWN=4,
 ACTION_SHOOTLEFT=5,ACTION_SHOOTRIGHT=6,ACTION_SHOOTUP=7,ACTION_SHOOTDOWN=8}
WeaponType={WEAPON_TEARS=1,WEAPON_KNIFE=2}
InputHook={GET_ACTION_VALUE=1}; CacheFlag={CACHE_SPEED=1,CACHE_FIREDELAY=2}; EntityType={ENTITY_PLAYER=1}
ModCallbacks={}; for i,k in ipairs({'MC_POST_GAME_STARTED','MC_PRE_GAME_EXIT','MC_POST_UPDATE','MC_INPUT_ACTION','MC_PRE_PLAYER_RENDER','MC_POST_RENDER','MC_POST_ENTITY_TAKE_DMG','MC_PRE_CHANGE_ROOM','MC_POST_NEW_ROOM','MC_POST_NEW_LEVEL','MC_PRE_ROOM_EXIT','MC_EXECUTE_CMD','MC_PRE_TEAR_RENDER'}) do ModCallbacks[k]=i end
local held={}; Input={IsButtonPressed=function(k) return held[k]==true end,IsMouseBtnPressed=function(k) return held['mouse'..k]==true end}
function key(k,v) held[k]=v end
RoomTransition={GetTransitionMode=function() return 0 end,IsRenderingBossIntro=function() return false end}
ImGui={IsVisible=function() return false end}; Options={MouseControl=false,SFXVolume=1}
local callbacks={}; mod={AddCallback=function(_,k,f) callbacks[k]=f end}
local callbackName
function call(k,...)
 local outer=callbackName
 callbackName=k
 local result=callbacks[ModCallbacks[k]](mod,...)
 callbackName=outer
 return result
end
player={Index=0,Position=Vector(0,0),Velocity=Vector(0,0),ControllerIndex=0,Damage=4,MaxFireDelay=13,
 MoveSpeed=1.15,SpriteScale=Vector(1,1)}
local playerKind=42
local deadPlayer,deathSprite=false,false
function player:GetPlayerType() return playerKind end
function player:GetSprite()
 return {Color={1,1,1,1},IsPlaying=function(_,name) return name=='Death' and deathSprite end}
end
function player:IsDead() return deadPlayer end
function player:ToPlayer() return self end
function player:AddCacheFlags() end
function player:EvaluateItems() end
room={seed=1,clear=false,index=4}; function room:IsMirrorWorld() return self.mirrored==true end; function room:GetSpawnSeed() return self.seed end
function room:GetClampedPosition(point) return point end
function room:CheckLine() return true end
function room:IsClear() return self.clear end
local level={GetStartingRoomIndex=function() return 4 end,GetCurrentRoomIndex=function() return room.index end}
clock=0; game={GetNumPlayers=function() return 1 end,GetRoom=function() return room end,GetLevel=function() return level end,
 GetFrameCount=function() return clock end,IsPaused=function() return false end}
local targets={}
Console={RegisterCommand=function(name) assert(name=='mftest') end}; AutocompleteType={NONE=0}
Color=function(...) return {...} end
KColor=Color
local art={}
local labels={}
local lines={}
local nativeLoads={}
local missingClip
local jokeLoadCallback,danceLoadCallback
local function rendered(path, name)
 for _,frame in ipairs(art) do
  if frame[1]==path and frame[2]==name then return frame end
 end
end
local renders=rendered
function Sprite(path)
 assert(path~='gfx/mf/actions.anm2','native fallback must never load the atlas from the crash stack')
 if path=='gfx/mf/joke_effects.anm2' then jokeLoadCallback=callbackName end
 if path=='gfx/mf/dance_effects.anm2' then danceLoadCallback=callbackName end
 if path:find('gfx/mf/action-',1,true)==1 then
  nativeLoads[path]=(nativeLoads[path] or 0)+1
  nativeLoads.lastCallback=callbackName
  if missingClip==path then return nil,false end
 end
 return {SetFrame=function(_,name,frame) art[#art+1]={path,name,frame} end,
   Render=function(self,position)
     local entry=art[#art]
     if entry then entry.position,entry.rotation,entry.scale,entry.color=position,self.Rotation,self.Scale,self.Color end
   end},true
end
TearFlags={TEAR_NORMAL=0}; TearVariant={BLUE=1,BLOOD=2}
SoundEffect={SOUND_BULLET_SHOT=482}
local sounds={}
local ids={}
local function audioId(name)
 ids[name]=ids[name] or #sounds+500
 return ids[name]
end
local missingAudio=false
local renderMillis=0
local stopped={}
local looping={}
function SFXManager()
 return {Play=function(_,id,volume,delay,loop,pitch)
  assert(delay==0)
  assert(volume>0 and pitch>0)
  sounds[#sounds+1]=id
  if loop then looping[id]=true end
 end,Stop=function(_,id) stopped[#stopped+1]=id end}
end
Isaac={IsInGame=function() return true end,GetPlayer=function() return player end,GetPlayerTypeByName=function() return 42 end,
 GetNanoTime=function() return 100 end,GetTime=function() return clock*34+renderMillis end,GetRoomEntities=function() return targets end,
 DebugString=function() end, WorldToScreen=function(v) return Vector(v.X,v.Y) end,GetScreenWidth=function() return 800 end,
 GetScreenHeight=function() return 600 end, GetSoundIdByName=function(name) return missingAudio and -1 or audioId(name) end,
 DrawLine=function(a,b) lines[#lines+1]={a,b} end, GetTextWidth=function(value) return #value*6 end,
 RenderScaledText=function(value) labels[value]=true end,
 WorldToRenderPosition=function(v) return Vector(v.X,v.Y) end, LoadModDataFromFolder=function() return '' end,
 ConsoleOutput=function(msg) consoleMessage=msg end,RenderText=function() end}
function EntityRef(p) return p end
function GetPtrHash(entity) return entity end
local lease
package.preload.json=function() return {encode=function(value) packet=value; return '{}' end,decode=function() return lease end} end
local cursor=Vector(100,0)
local selectedRune, pickerClicked
local cache={}; function include(name)
 if name=='samira_navigation' then
  return {worldCursor=function() return cursor end, doorAt=function(_,point) return point.X<0 and 'left' or nil end,
   doorHeading=function(_,_,door) return door and Vector(-1,0) end,
   waypoint=function(_,_,_,point) return point,true end}
 end
 if not cache[name] then
  cache[name]=assert(load(sources[name],name))()
  if name=='yone_hud' then
   cache[name].runePickerHit=function() return pickerClicked end
   cache[name].renderRunePicker=function() end
  end
 end
 return cache[name]
end
weapons={requests=0,requestQ=function() weapons.requests=weapons.requests+1; return true end,
 update=function(p,c,a,enabled) weapons.aim=a; weapons.enabled=enabled end,reset=function() end,
 input=function() return weapons.enabled and weapons.aim and weapons.aim.X or 0 end}
items={newAttack=function(p,k,t) return {kind=k,origin=p.Position} end,onCast=function() end,
 withContext=function(_,f) return f() end, combatStats=function() return .25,15 end}
local displayId,displayMode=1,'windowed'
display={acquire=function() end,release=function() end,sample=function() return 800,600,{id=displayId,mode=displayMode} end}
Isaac.LoadModDataFromFolder=function() return lease and 'ack' or '' end
mf=include('miss_fortune_character'); mf.init(mod,game,items,nil,weapons,function() return 1 end,function() return held.r end,display)
call('MC_POST_GAME_STARTED',false); assert(mf.player(game)==player and mf.canUseItems(player))
local bounds=mf.hudBounds(.8, {x=10,y=545,right=330,bottom=598,width=320,height=53})
assert(bounds.y>480 and bounds.x>=0 and bounds.right<=800 and bounds.bottom<=600,
 'MF combat HUD belongs along the bottom at non-default scales')
call('MC_POST_RENDER')
local icons={}
for _,frame in ipairs(art) do
 if frame[1]=='gfx/mf/hud_icons.anm2' then icons[frame[2]]=true end
end
assert(icons.Portrait and icons.Q and icons.W and icons.E and icons.R,
 'MF post-render must draw the custom portrait and all ability icons')
assert(labels['25%'] and labels['2.14'],'MF panel must show live item crit and native attack speed')
local tearContext={kind='q',nativeWeapon=true,player=player}
local nativeTag={context=tearContext}
local qtear={Position=Vector(10,0),Velocity=Vector(4,0),TearFlags=0,Variant=TearVariant.BLUE,
 GetData=function() return {SamiraNativeWeapon=nativeTag} end}
local shotAtlas='gfx/mf/shot_effects.anm2'
assert(call('MC_PRE_TEAR_RENDER',qtear,Vector.Zero)==false)
local qBullet=rendered(shotAtlas,'QBullet')
assert(qBullet and renders(shotAtlas,'QGlow'),'Double Up uses its own source glow and red shell')
tearContext.kind='aa'; art={}
assert(call('MC_PRE_TEAR_RENDER',qtear,Vector.Zero)==false and renders('gfx/mf/projectiles.anm2','Bullet'),
 'ordinary native autoattacks use the same real Skin69 shell mesh as Double Up')
local aaBullet=rendered('gfx/mf/projectiles.anm2','Bullet')
assert(aaBullet.scale.X<qBullet.scale.X and qBullet.scale.X<.6 and renders(shotAtlas,'AATrail')
 and not renders(shotAtlas,'QGlow'),
 'standard shots use a compact source-colored shell, with a slightly larger Double Up')
qtear.TearFlags=1; assert(call('MC_PRE_TEAR_RENDER',qtear,Vector.Zero)==nil)
TearFlags.TEAR_QUADSPLIT=1<<18
qtear.TearFlags=TearFlags.TEAR_QUADSPLIT
for _,kind in ipairs({'aa','q'}) do
 tearContext.kind=kind; art={}
 assert(call('MC_PRE_TEAR_RENDER',qtear,Vector.Zero)==false,
  "Cricket's Body keeps the T1 shell on the parent projectile")
end
qtear.TearFlags=TearFlags.TEAR_QUADSPLIT|1
assert(call('MC_PRE_TEAR_RENDER',qtear,Vector.Zero)==nil,'another effect keeps its own native art')
qtear.TearFlags=0; nativeTag.split=true
assert(call('MC_PRE_TEAR_RENDER',qtear,Vector.Zero)==nil,'split keeps the native tear sprite even without additional flags')
nativeTag.split=nil
qtear.TearFlags=0; tearContext.persistentPulse=true
assert(call('MC_PRE_TEAR_RENDER',qtear,Vector.Zero)==nil,'persistent artifact art stays native')
key(Keyboard.KEY_Q,true); clock=1; call('MC_POST_UPDATE'); assert(weapons.requests==1 and mf.exportCooldowns(clock).q>0)
assert(#sounds==0,'charging must not play the resolved Q sound')
mf.weaponFired('q',Vector(1,0),{origin=player.Position},clock)
assert(#sounds==2 and sounds[1]==audioId('Miss Fortune Q') and sounds[2]==audioId('Miss Fortune Q Voice'),
 'resolved Q should play the loaded Skin69 SFX and voice')
missingAudio=true
mf.weaponFired('q',Vector(1,0),{origin=player.Position},clock)
assert(#sounds==3 and sounds[3]==SoundEffect.SOUND_BULLET_SHOT,'missing audio still has a bullet cue')
missingAudio=false
key(Keyboard.KEY_Q,false); key(Keyboard.KEY_A,true); clock=2; call('MC_POST_UPDATE'); assert(weapons.aim.X>0 and weapons.enabled)
local barrageTarget={Position=Vector(30,0),Exists=function() return true end,IsDead=function() return false end,
 IsActiveEnemy=function() return true end,IsVulnerableEnemy=function() return true end,TakeDamage=function() return true end}
targets={barrageTarget}
local ultimateAtlas='gfx/mf/ultimate_effects.anm2'
art={}
key(Keyboard.KEY_RIGHT,true); held.r=true; clock=3; call('MC_POST_UPDATE')
assert(not weapons.enabled,'starting Bullet Time takes priority over held attack and same-frame movement')
call('MC_POST_RENDER')
assert(#sounds==5 and sounds[4]==audioId('Miss Fortune R') and sounds[5]==audioId('Miss Fortune R Voice')
 and not packet.mfBarrage and packet.clip=='r_in','windup plays cast audio without barraging yet')
assert(renders(ultimateAtlas,'RCone') and not renders(shotAtlas,'RCore'),
 'the authored R cone indicates aim before the first wave')
local aimingOpacity=rendered(ultimateAtlas,'RCone').color[4]
assert(call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)==false)
assert(art[#art][1]=='gfx/mf/fallback.anm2' and art[#art][2]=='Idle2','native rendering uses the preloaded small atlas')
assert(art[#art].scale.X<.65 and player.SpriteScale.X==1,'only the drawn model shrinks')
assert(not nativeLoads['gfx/mf/action-r_in.anm2'],'an unsettled display must not load a clip from the render callback')
held.r=false; clock=4; call('MC_POST_UPDATE'); assert(#sounds==5)
art={}; clock=5; call('MC_POST_UPDATE'); call('MC_POST_RENDER')
assert(#sounds==7 and sounds[6]==audioId('Miss Fortune R Barrage') and sounds[7]==audioId('Miss Fortune R Wave'))
assert(packet.clip=='r' and packet.actionFrame==8 and packet.actionId==5
 and packet.mfBarrage.start==5 and packet.mfBarrage.interval==6)
assert(packet.mfMuzzle.kind=='r' and packet.mfMuzzle.start==5 and packet.mfMuzzle.finish==7 and packet.mfMuzzle.gun==1,
 'the first R wave exports the authored right gun on the shared pose clock')
assert(renders(shotAtlas,'RCore') and renders(ultimateAtlas,'RTrail')
 and renders(ultimateAtlas,'RMuzzle') and renders(ultimateAtlas,'RImpact'),
 'each launched wave uses the R art, and accepted damage plays the R impact')
assert(rendered(ultimateAtlas,'RCone').color[4]<aimingOpacity
 and rendered(ultimateAtlas,'RTrail').scale.Y<.1 and rendered(shotAtlas,'RCore').scale.X<.5,
 'the R indicator fades during combat while the authored bullet lanes stay narrow')
local lanes={}
for _,frame in ipairs(art) do
 if frame[1]==shotAtlas and frame[2]=='RCore' then lanes[#lanes+1]=math.floor(frame.rotation+.5) end
end
assert(table.concat(lanes,',')=='-15,-9,-3,3,9,15','R uses six fixed authored bullet lanes')
assert(call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)==false and art[#art][1]=='gfx/mf/action-r.anm2'
 and art[#art][2]=='r2' and art[#art][3]==4 and nativeLoads.lastCallback=='MC_POST_UPDATE',
 'the first R wave draws the directional source clip that was loaded in update')
art={}
key(Keyboard.KEY_UP,true); clock=6; call('MC_POST_UPDATE')
assert(weapons.enabled,'a fresh arrow interrupts Bullet Time even while another arrow is held')
key(Keyboard.KEY_A,false); key(Keyboard.KEY_UP,false)
call('MC_POST_RENDER')
assert(#sounds==7 and stopped[1]==audioId('Miss Fortune R Barrage') and not packet.mfBarrage,
 'cancel must stop barrage sound and recoil telemetry')
assert(not packet.mfMuzzle,'cancel also stops the GPU muzzle cue')
assert(not renders(ultimateAtlas,'RCone') and not renders(ultimateAtlas,'RMuzzle') and renders(shotAtlas,'RCore'),
 'cancelling removes the cone while already fired bullets are still rendered')
targets={}
local saved=mf.exportCooldowns(clock); call('MC_POST_NEW_ROOM'); assert(mf.exportCooldowns(clock).q==saved.q)
mf.reduceCooldowns(1,clock); assert(mf.exportCooldowns(clock).q==0); mf.restoreCooldowns(saved,clock); assert(mf.exportCooldowns(clock).q==saved.q)
local function tick(frame) clock=frame+1; call('MC_POST_UPDATE') end
local function intent(action) return call('MC_INPUT_ACTION',player,InputHook.GET_ACTION_VALUE,ButtonAction[action]) end
key(Keyboard.KEY_RIGHT,false)
key('mouse1',true); tick(6); assert(intent('ACTION_RIGHT')==1 and not weapons.aim,'ground click must walk')
cursor=Vector(0,100); tick(7); assert(intent('ACTION_DOWN')==1,'held click did not steer')
key('mouse1',false); tick(8); assert(intent('ACTION_DOWN')==1,'released click lost its movement goal')
cursor=Vector(-25,0); key('mouse1',true); tick(9); assert(intent('ACTION_LEFT')==1,'door order lost')
key('mouse1',false); tick(10)
local target={Position=Vector(400,0),Size=10,Exists=function() return true end,IsDead=function() return false end,
 IsVulnerableEnemy=function() return true end}
targets={target}; cursor=target.Position; key('mouse1',true); tick(11)
assert(intent('ACTION_RIGHT')==1 and weapons.aim==nil,'distant target must be approached first')
target.Position=Vector(120,0); key('mouse1',false); tick(12)
assert(weapons.aim.X==1 and intent('ACTION_RIGHT')==0,'target in range must be attacked')
assert(intent('ACTION_SHOOTRIGHT')==1,'MF native shot did not reach the Isaac weapon driver')
targets={}
lines={}
key(Keyboard.KEY_W,true); tick(13); call('MC_POST_RENDER'); assert(packet.mfW==1 and mf.speed(player,clock)>1)
assert(sounds[#sounds]==audioId('Miss Fortune W'))
assert(labels['W 4.0s'],'W HUD duration must appear when the buff starts')
local wHud=mf.hudBounds(1)
for _,line in ipairs(lines) do
 assert(line[1].Y>=wHud.y and line[2].Y>=wHud.y,
  'W must not draw a second duration bar under the character')
end
key(Keyboard.KEY_W,false)
call('MC_PRE_ROOM_EXIT',player,true); playerKind=99; tick(14)
room.seed=2; call('MC_POST_NEW_ROOM'); call('MC_POST_NEW_LEVEL')
playerKind=42; tick(15); call('MC_POST_RENDER')
assert(packet.active and packet.room==3 and not packet.transition,'floor rebind did not recover')
key(Keyboard.KEY_LEFT_CONTROL,true); key(Keyboard.KEY_2,true); tick(16); call('MC_POST_RENDER')
assert(packet.expression=='taunt_spam' and packet.actionFrame==0)
assert(sounds[#sounds]==audioId('Miss Fortune Taunt'))
assert(call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)==false)
assert(art[#art][1]=='gfx/mf/action-taunt_spam.anm2','alternate taunt resumes after the floor rebind')
key(Keyboard.KEY_LEFT_CONTROL,false); key(Keyboard.KEY_2,false)
items.missFortuneRunes=function() return {rune=selectedRune} end
items.chooseMissFortuneRune=function(id) selectedRune=id end
tick(17); assert(not mf.canUseItems(player) and not weapons.enabled)
assert(intent('ACTION_SHOOTRIGHT')==0,'rune picker leaked a native shot')
for i, option in ipairs(include('miss_fortune_runes').choices) do
 if option.id=='first_strike' then pickerClicked=i end
end
assert(type(pickerClicked)=='number')
key('mouse0',true); tick(18); key('mouse0',false); tick(19)
pickerClicked='confirm'; key('mouse0',true); tick(20)
assert(selectedRune=='first_strike' and mf.canUseItems(player))
call('MC_EXECUTE_CMD','mftest',''); assert(consoleMessage:find('connected'))
call('MC_EXECUTE_CMD','mftest','anim homeguard'); tick(21); call('MC_POST_RENDER')
assert(packet.clip=='homeguard' and not packet.actionLength,'source preview must use authored timing')
call('MC_EXECUTE_CMD','mftest',''); key('mouse0',false); tick(22)
key(Keyboard.KEY_LEFT_CONTROL,true); key(Keyboard.KEY_5,true); tick(23); call('MC_POST_RENDER')
assert(packet.expression=='recall_cinematic' and packet.actionFrame==0)
local frames=include('miss_fortune_sprite')
local danceLoop, firstFrame=frames.sample('dance',frames.duration('dance'),nil,'dance')
assert(danceLoop=='dance_loop' and firstFrame==0)
key(Keyboard.KEY_LEFT_CONTROL,false); key(Keyboard.KEY_5,false)
call('MC_PRE_GAME_EXIT'); playerKind=99
call('MC_EXECUTE_CMD','mftest','on'); assert(mf.player(game)==player)
call('MC_EXECUTE_CMD','mftest','off'); assert(mf.player(game)==nil)
call('MC_POST_RENDER'); call('MC_PRE_GAME_EXIT'); assert(not mf.canUseItems(player))

playerKind=42; room.clear=true; player.Velocity=Vector.Zero
call('MC_POST_GAME_STARTED',false)
local function advance(t)
 for frame=clock+1,t do clock=frame; call('MC_POST_UPDATE') end
 call('MC_POST_RENDER')
end
local function renderedSpecial(name) return renders('gfx/mf/special_effects.anm2',name) end
advance(29); assert(packet.clip=='base_idle','starting a floor without moving keeps the idle pose')
key(Keyboard.KEY_RIGHT,true); player.Velocity=Vector(3,0)
advance(30)
assert(packet.clip=='homeguard_in' and sounds[#sounds]==audioId('Miss Fortune Homeguard Start'),
 'first movement in the starting room uses the authored Homeguard intro')
advance(39); assert(sounds[#sounds]==audioId('Miss Fortune Homeguard Onboard'))
advance(54)
assert(packet.clip=='homeguard' and looping[audioId('Miss Fortune Homeguard Loop')],
 'the mounted running clip and authored loop start after the intro')
assert(renderedSpecial('HomeguardTrail') and renderedSpecial('HomeguardGlow'),
 'mounted movement draws both original trail elements')
key(Keyboard.KEY_RIGHT,false); player.Velocity=Vector.Zero
local soundsAtStop=#sounds
advance(55)
assert(packet.clip=='idle_in' and packet.actionFrame==0 and #sounds==soundsAtStop,
 'Homeguard leads to the source idle transition at a stop, with no running cue')
local loopStopped=false
for _,id in ipairs(stopped) do if id==audioId('Miss Fortune Homeguard Loop') then loopStopped=true end end
assert(loopStopped,'Homeguard loop stops at dismount')
advance(55+frames.duration('idle_in')+1); assert(packet.clip=='base_idle')
key(Keyboard.KEY_RIGHT,true); player.Velocity=Vector(3,0); advance(clock+1)
assert(packet.clip~='homeguard_in','the same floor cannot restart Homeguard')
key(Keyboard.KEY_RIGHT,false); player.Velocity=Vector.Zero
call('MC_POST_NEW_LEVEL'); call('MC_POST_NEW_ROOM'); key(Keyboard.KEY_RIGHT,true)
player.Velocity=Vector(3,0); advance(clock+1); assert(packet.clip=='homeguard_in','new floor rearms Homeguard')
room.index=5; room.clear=false; call('MC_POST_NEW_ROOM'); advance(clock+1)
assert(not packet.clip:find('homeguard',1,true),'a room transition must clear the travelling pose')
key(Keyboard.KEY_RIGHT,false); player.Velocity=Vector.Zero

for _=1,4 do mf.recordTakedown(player,clock) end
advance(clock+1); assert(packet.clip=='idle_in','four credited kills leave the locomotion-to-idle transition available')
key(Keyboard.KEY_A,true); mf.recordTakedown(player,clock)
advance(clock+1); assert(packet.clip~='pentakill','held fire takes priority over the pentakill')
key(Keyboard.KEY_A,false); advance(clock+1); assert(packet.clip=='pentakill')
advance(clock+frames.duration('pentakill'))
assert(packet.clip=='pentakill_bonus' and packet.actionFrame==0,'the authored bonus follows its intro')
assert(renderedSpecial('PentakillSignature'),'the original effect appears with the bonus clip')
key(Keyboard.KEY_A,true); advance(clock+1)
assert(packet.clip~='pentakill_bonus' and weapons.enabled,'attack must interrupt the celebration immediately')
key(Keyboard.KEY_A,false)
for _=1,4 do mf.recordTakedown(player,clock) end
call('MC_POST_NEW_ROOM'); mf.recordTakedown(player,clock); advance(clock+1)
assert(packet.clip=='base_idle','kills from a different room cannot complete the streak')

local hits={}
local rainTarget={Position=Vector(100,0), Exists=function() return true end,
 IsDead=function() return false end, IsActiveEnemy=function() return true end,
 IsVulnerableEnemy=function() return true end}
function rainTarget:TakeDamage() hits[#hits+1]=clock; return true end
targets={rainTarget}; cursor=Vector(100,0)
local function sawRainArt(name) return renders(shotAtlas,name) end
local function rainCup()
 for _,name in ipairs({'RecallTrophy2024','RecallTrophy2025','RecallTrophyFMVP'}) do
  local entry=rendered('gfx/mf/recall_effects.anm2',name)
  if entry then return entry end
 end
end
local eCast=clock+1
key(Keyboard.KEY_E,true); art={}; advance(eCast)
assert(renders('gfx/mf/projectiles.anm2','Ring') and sawRainArt('RainGround') and sawRainArt('RainGold')
 and sawRainArt('RainRingGlow') and sawRainArt('RainStreak') and sawRainArt('RainCore')
 and not sawRainArt('RainImpact'),
 'Make It Rain starts with its original zone effects and descending bullets')
key(Keyboard.KEY_E,false); art={}; advance(eCast+2)
local inAir=rainCup()
assert(inAir and inAir.position.X==cursor.X and inAir.position.Y<cursor.Y,
 'the source trophy enters above the center of the rain')
art={}; advance(eCast+7)
assert(#hits==0 and not sawRainArt('RainImpact') and not sawRainArt('RainImpactGlow'),
 'damage and ground impacts wait for the bullets to arrive')
assert(rainCup()[2]==inAir[2] and rainCup().position.Y>inAir.position.Y,
 'the same trophy descends toward the ground during the cast')
art={}; advance(eCast+8)
assert(#hits==1 and hits[1]==clock and sawRainArt('RainImpact') and sawRainArt('RainImpactGlow'),
 'a damage pulse and its ground impacts must happen on the same frame')
assert(rainCup().position.Y==cursor.Y and rainCup().color[4]<=.6,'the trophy settles as a translucent prop')
player.ControlsEnabled=false
advance(eCast+15)
assert(not weapons.enabled and #hits==2 and hits[2]==eCast+15,
 'already cast rain continues on schedule during a temporary input lock')
player.ControlsEnabled=true
advance(eCast+23)
assert(#hits==3 and hits[3]==eCast+23,'unlocking controls must not shift rain pulses')

targets={}; art={}; advance(eCast+90)
assert(not sawRainArt('RainGround') and not rainCup(),'the source projection and trophy end with the rain')
local recallAt=clock+1
local recallAtlas='gfx/mf/recall_effects.anm2'
art={}; key(Keyboard.KEY_LEFT_CONTROL,true); key(Keyboard.KEY_5,true); advance(recallAt)
assert(packet.expression=='recall_cinematic' and sounds[#sounds]==audioId('Miss Fortune Recall'),
 'Ctrl+5 plays the authored Recall soundtrack once from frame zero')
assert(call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)==false)
assert(renders(recallAtlas,'RecallFloor') and renders(recallAtlas,'RecallRune')
 and renders(recallAtlas,'RecallRoad') and not renders(recallAtlas,'RecallLogo'),
 'floor, road and glyph begin with the pose while the logo waits for its authored frame')
local propAtlas='gfx/mf/recall_props.anm2'
local burstAtlas='gfx/mf/recall_bursts.anm2'
local function recallMuzzles()
 local positions={}
 for _,entry in ipairs(art) do
  if entry[1]==burstAtlas and entry[2]=='RecallMuzzle' then positions[#positions+1]=entry.position end
 end
 return positions
end
key(Keyboard.KEY_5,false); art={}; advance(recallAt+8); call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)
assert(not renders(propAtlas,'RecallSpear'))
art={}; advance(recallAt+9); call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)
local spears=0
for _,entry in ipairs(art) do if entry[1]==propAtlas and entry[2]=='RecallSpear' then spears=spears+1 end end
assert(spears==3,'three source spears appear at frame 9')
art={}; advance(recallAt+34); call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)
assert(#recallMuzzles()==0)
art={}; advance(recallAt+35); call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)
local firstPair=recallMuzzles()
assert(#firstPair==2 and (firstPair[1]-firstPair[2]):Length()>1,
 'both authored barrels fire at frame 35')
art={}; advance(recallAt+38); call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)
assert(#recallMuzzles()==0 and renders(burstAtlas,'RecallShotSpark'),
 'the three-tick flash expires while sparks continue')
art={}; advance(recallAt+57); call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)
assert(renders(propAtlas,'RecallArrow') and not renders(propAtlas,'RecallSpear'))
art={}; advance(recallAt+68); call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)
assert(#recallMuzzles()==1,'the second authored gunshot fires at frame 68')
art={}; advance(recallAt+103); call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)
assert(renders(propAtlas,'RecallBalloon') and renders(propAtlas,'RecallWaterTrail'))
assert(#recallMuzzles()==0 and not renders(burstAtlas,'RecallBalloonHit'))
art={}; advance(recallAt+105); call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)
local thirdShot=recallMuzzles()
assert(#thirdShot==1 and renders(burstAtlas,'RecallBalloonHit'),'the shot and first balloon impact share frame 105')
art={}; advance(recallAt+110); call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)
local fourthShot=recallMuzzles()
assert(#fourthShot==1 and (fourthShot[1]-thirdShot[1]):Length()>1,
 'the second balloon shot uses the opposite source attachment')
art={}; advance(recallAt+129)
assert(not renders(recallAtlas,'RecallLogo'))
art={}; advance(recallAt+130); call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)
assert(renders(recallAtlas,'RecallLogo') and renders(recallAtlas,'RecallFlourish'),
 'the authored logo and sky beam start together at frame 130')
assert(renders(burstAtlas,'RecallBalloonSplash') and renders(burstAtlas,'RecallBalloonDroplet')
 and not renders(propAtlas,'RecallBalloon'),'the balloon bursts when the T1 logo appears')
local petAtlas='gfx/mf/recall_pet.anm2'
local function petFrame()
 for _,entry in ipairs(art) do
  if entry[1]==petAtlas and entry[2]:match('^RecallDog%d$') then return entry[3] end
 end
end
art={}; advance(recallAt+135); call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)
assert(petFrame()==nil and not renders(recallAtlas,'RecallTrophyFMVP'))
art={}; advance(recallAt+136); call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)
assert(petFrame()==0 and not renders(recallAtlas,'RecallTrophyFMVP'), 'the authored pet starts on frame 136')
art={}; advance(recallAt+138); call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)
assert(petFrame()==2 and renders(recallAtlas,'RecallTrophyFMVP'),'FMVP joins the animated pet at frame 138')
art={}; advance(recallAt+229); call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)
assert(not renders(recallAtlas,'RecallTrophy2024') and not renders(recallAtlas,'RecallTrophy2025'))
art={}; advance(recallAt+230); call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)
local earlierCups={}
for _,entry in ipairs(art) do
 if entry[1]==recallAtlas and entry[2]=='RecallTrophy2024' then earlierCups[#earlierCups+1]=entry.position end
end
assert(#earlierCups==2 and (earlierCups[1]-earlierCups[2]):Length()>1
 and renders(recallAtlas,'RecallTrophy2025') and renders(recallAtlas,'RecallTrophyFMVP'),
 'the three late trophies appear at their own anchors alongside the FMVP cup')
local beforeNaturalFinish=#stopped
advance(recallAt+frames.duration('recall_cinematic')+1)
assert(not packet.expression and #stopped==beforeNaturalFinish,'the Recall audio can finish its tail after a complete emote')
key(Keyboard.KEY_5,true); advance(clock+1)
assert(packet.expression=='recall_cinematic' and packet.actionFrame==0,'finished Recall can immediately restart')
key(Keyboard.KEY_5,false); advance(clock+34)
key(Keyboard.KEY_RIGHT,true); art={}; advance(clock+1)
call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)
assert(not packet.expression and stopped[#stopped]==audioId('Miss Fortune Recall')
 and not renders(recallAtlas,'RecallFloor') and not renders(recallAtlas,'RecallLogo') and #recallMuzzles()==0,
 'movement cancels both the timed audio and stage')
call('MC_PRE_GAME_EXIT')

key(Keyboard.KEY_RIGHT,false); key(Keyboard.KEY_LEFT_CONTROL,false)
call('MC_POST_GAME_STARTED',false)
local fireAt=clock
local facing=Vector(1,0)
local volley={origin=player.Position}
call('MC_POST_ENTITY_TAKE_DMG',{Type=EntityType.ENTITY_PLAYER,Index=player.Index},1,0)
mf.weaponFired('aa',facing,volley,fireAt)
advance(fireAt+12)
mf.weaponFired('aa',facing,volley,clock)
player.Velocity=Vector(2,0); advance(clock+12)
assert(packet.clip=='attack2_run','second shot returns directly to the authored run transition')
local wAt=clock+1
key(Keyboard.KEY_W,true); advance(wAt); key(Keyboard.KEY_W,false); advance(wAt+16)
mf.weaponFired('aa',facing,volley,clock); advance(clock+12)
mf.weaponFired('aa',facing,volley,clock); advance(clock+12)
assert(packet.clip=='attack2_strut','second shot has the distinct authored max-Strut return')
player.Velocity=Vector.Zero
mf.weaponFired('q',facing,volley,clock); advance(clock+18)
assert(packet.clip=='q_out','stationary Double Up plays the authored transition to idle')
local critAt=clock+1
mf.weaponFired('aa',facing,{crit=true},critAt); advance(critAt)
assert(packet.clip=='crit','a confirmed critical volley chooses the Skin69 critical-shot clip')
advance(critAt+12)
assert(packet.clip=='crit_out','a stationary critical volley uses its own authored recovery')
assert(call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)==false and art[#art][1]=='gfx/mf/action-crit_out.anm2',
 'the native renderer plays the distinct critical-shot recovery')
call('MC_PRE_GAME_EXIT')

idleRoll=20
call('MC_POST_GAME_STARTED',false)
local idleAt=clock+1
advance(idleAt)
assert(packet.clip=='base_idle' and packet.actionFrame==0,'the authored idle sequence begins with idle01')
local draws=idleRandomCalls
call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)
assert(idleRandomCalls==draws,'the native fallback and companion share one idle roll')
local alternateAt=idleAt+frames.duration('base_idle')
advance(alternateAt)
assert(packet.clip=='idle' and packet.actionFrame==0,'the alternate branch starts idle02 after idle01')
idleRoll=95
advance(alternateAt+frames.duration('idle'))
assert(packet.clip=='base_idle' and packet.actionFrame==0,'an idle sequence restarts at the source boundary')
advance(clock+frames.duration('base_idle'))
assert(packet.clip=='base_idle' and packet.actionFrame==0,'the base-only branch does not enter idle02')
player.Velocity=Vector(2,0); advance(clock+1)
assert(packet.clip=='run_in' or packet.clip=='run' or packet.clip=='w' or packet.clip=='strut_run_loop')
player.Velocity=Vector.Zero; advance(clock+1)
assert(packet.clip=='idle_in' and packet.actionFrame==0,'stopping uses the authored locomotion-to-idle transition')
advance(clock+frames.duration('idle_in'))
assert(packet.clip=='base_idle' and packet.actionFrame==0)

local function expressionClip()
 return frames.sample(packet.clip,packet.actionFrame,packet.actionLength,packet.expression)
end
local jokeAt=clock+1
key(Keyboard.KEY_LEFT_CONTROL,true); key(Keyboard.KEY_1,true); advance(jokeAt)
assert(packet.expression=='joke' and expressionClip()=='joke_in','Ctrl+1 enters Joke through the authored transition')
assert(sounds[#sounds]==audioId('Miss Fortune Joke Cast'),'JokeIn plays the source cast sound')
key(Keyboard.KEY_1,false)
local jokeAtlas='gfx/mf/joke_effects.anm2'
local function showEmote(t)
 advance(t)
 art={}; call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)
end
assert(jokeLoadCallback=='MC_POST_UPDATE','Joke art is loaded outside the player-render callback')
showEmote(jokeAt+19); assert(not renders(jokeAtlas,'JokeIntroRing'))
showEmote(jokeAt+20)
assert(renders(jokeAtlas,'JokeIntroRing') and not renders(jokeAtlas,'JokeIntroFlash'),
 'intro ring and delayed muzzle flash keep distinct source cues')
showEmote(jokeAt+28); assert(renders(jokeAtlas,'JokeIntroFlash'))
showEmote(jokeAt+35)
assert(not renders(jokeAtlas,'JokeIntroFlash') and not renders(jokeAtlas,'JokeIntroRing'))
local jokeBody=jokeAt+frames.duration('joke_in')
advance(jokeBody)
assert(expressionClip()=='joke' and sounds[#sounds]==audioId('Miss Fortune Joke'))
showEmote(jokeBody+7); assert(not renders(jokeAtlas,'JokeSpamBeam'))
showEmote(jokeBody+8)
assert(renders(jokeAtlas,'JokeSpamBeam') and renders(jokeAtlas,'JokeSpamGold')
 and not renders(jokeAtlas,'JokeLoopLogo'),'the spotlight starts at the source Joke Spam cue')
showEmote(jokeBody+frames.duration('joke'))
local jokeLoop=audioId('Miss Fortune Joke Loop')
assert(expressionClip()=='joke_loop' and sounds[#sounds]==jokeLoop and looping[jokeLoop],
 'the original loop begins with the loop clip, independently of the joke voice')
assert(renders(jokeAtlas,'JokeLoopLogo') and renders(jokeAtlas,'JokeLoopBeam')
 and renders(jokeAtlas,'JokeLoopConfetti'),'the source logo, moving light and petals appear with the loop')
local firstPetal=rendered(jokeAtlas,'JokeLoopConfetti').position
showEmote(clock+6)
assert(rendered(jokeAtlas,'JokeLoopConfetti').position.Y>firstPetal.Y)
key(Keyboard.KEY_RIGHT,true); showEmote(clock+1)
assert(not packet.expression and stopped[#stopped]==jokeLoop,'moving stops the Joke loop')
assert(not renders(jokeAtlas,'JokeLoopLogo') and not renders(jokeAtlas,'JokeLoopConfetti'),
 'movement ends the effect on the interrupt frame')
key(Keyboard.KEY_RIGHT,false); key(Keyboard.KEY_1,true); advance(clock+1); key(Keyboard.KEY_1,false)
local secondJoke=clock
showEmote(secondJoke+20); assert(renders(jokeAtlas,'JokeIntroRing'))
key(Keyboard.KEY_A,true); showEmote(clock+1); key(Keyboard.KEY_A,false)
assert(not packet.expression and not renders(jokeAtlas,'JokeIntroRing'),
 'a confirmed attack intent interrupts the intro without waiting for its visual lifetime')

local danceAt=clock+1
local danceAtlas='gfx/mf/dance_effects.anm2'
key(Keyboard.KEY_3,true); showEmote(danceAt); key(Keyboard.KEY_3,false)
local danceSound=audioId('Miss Fortune Dance')
assert(packet.expression=='dance' and expressionClip()=='dance' and sounds[#sounds]==danceSound)
assert(danceLoadCallback=='MC_POST_UPDATE' and not renders(danceAtlas,'DanceLogoGold'),
 'the effect atlas is prepared during update and the logo rises from zero')
showEmote(danceAt+4)
assert(renders(danceAtlas,'DanceLogoGold') and renders(danceAtlas,'DanceLogoRed')
 and renders(danceAtlas,'DanceHalo') and renders(danceAtlas,'DanceFlash')
 and renders(danceAtlas,'DanceSpark') and renders(danceAtlas,'DanceFeather'),
 'all six source Dance layers appear during the authored intro')
local danceLoopAt=danceAt+frames.duration('dance')
showEmote(danceLoopAt-1)
local oldGlow=rendered(danceAtlas,'DanceLogoGold').color[4]
showEmote(danceLoopAt)
assert(expressionClip()=='dance_loop' and renders('gfx/mf/action-dance_loop.anm2','dance_loop2'))
assert(rendered(danceAtlas,'DanceLogoGold').color[4]>=oldGlow,
 'the floor effect stays active through the switch to the loop')
showEmote(danceLoopAt+frames.duration('dance_loop')+30)
assert(expressionClip()=='dance_loop' and renders(danceAtlas,'DanceLogoGold')
 and renders(danceAtlas,'DanceFeather'),'the sustained root stays alive past the first loop')
key(Keyboard.KEY_3,true); showEmote(clock+1); key(Keyboard.KEY_3,false)
assert(not packet.expression and not renders(danceAtlas,'DanceLogoGold') and stopped[#stopped]==danceSound,
 'toggling off stops the stage and audio on the same frame')

local dud={kind='qDud',from=Vector(40,0),to=Vector(100,0),startFrame=clock,travel=13,untilFrame=clock+17}
art={}
local effects=include('miss_fortune_effects')
local function renderCue(cue,tick)
 effects.render({fx={cue}},tick,function(point) return point end)
end
renderCue(dud,clock+13)
assert(renders(shotAtlas,'QDud') and not renders(shotAtlas,'QSecondImpact'),
 'a Q dud visibly reaches the floor without drawing a successful hit impact')
art={}
local qFlash={fx={}}
effects.fireMuzzle(qFlash,'q',Vector.Zero,Vector(1,0),clock,18)
effects.render(qFlash,clock,function(point) return point end)
assert(renders(shotAtlas,'QCast'),'Double Up uses its own cast flash')
art={}
renderCue({kind='qImpact',point=Vector(35,0),untilFrame=clock+6},clock)
assert(renders(shotAtlas,'QImpact') and renders('gfx/mf/projectiles.anm2','Impact'),
 'the first target receives the source ground wave and hit flash')
local bounce={kind='bounce',from=Vector(40,0),to=Vector(100,0),startFrame=clock,travel=4,untilFrame=clock+8}
art={}; renderCue(bounce,clock+4)
assert(not renders(shotAtlas,'QSecondImpact'),'unconfirmed bounce damage has no hit flash')
bounce.hit=true; renderCue(bounce,clock+4)
assert(renders(shotAtlas,'QSecondImpact'),'confirmed bounce has the source secondary target flash')
call('MC_PRE_GAME_EXIT')

DamageFlag={DAMAGE_FAKE=1<<21,DAMAGE_POISON_BURN=1<<15,DAMAGE_FIRE=1<<1}
key(Keyboard.KEY_RIGHT,false); key(Keyboard.KEY_LEFT_CONTROL,false)
player.Velocity=Vector.Zero
call('MC_POST_GAME_STARTED',false)
assert(mf.speed(player,clock)==1.2,'a new run starts with fully charged Strut')
local wCast=clock+1
art={}
key(Keyboard.KEY_W,true); advance(wCast); key(Keyboard.KEY_W,false)
assert(packet.clip=='base_idle' and packet.mfW==1,'standing W is an instant buff without a forced running pose')
local strutAtlas='gfx/mf/strut_effects.anm2'
local anchors={}
for _,entry in ipairs(art) do
 if entry[1]==strutAtlas and entry[2]=='GunSpark' then anchors[#anchors+1]=entry.position end
end
assert(#anchors==2 and (anchors[1]-anchors[2]):Length()>3 and not renders(strutAtlas,'GroundWisp'),
 'active W has two distinct gun anchors and no moving ground trail at rest')
art={}; player.Velocity=Vector(3,0); advance(wCast+1)
assert(packet.clip=='w' and packet.actionFrame==0,'max Strut starts the source Run2_In at the first step')
assert(renders(strutAtlas,'Feather') and renders(strutAtlas,'GroundWisp'),
 'running with max Strut displays the proper ground effects')
advance(wCast+1+frames.duration('w'))
assert(packet.clip=='strut_run_loop' and packet.actionFrame==0,'Run2 begins when its entry clip finishes')
local target={Type=EntityType.ENTITY_PLAYER,Index=player.Index}
local direct=clock
call('MC_POST_ENTITY_TAKE_DMG',target,1,DamageFlag.DAMAGE_FAKE)
assert(mf.speed(player,clock)==1.2)
call('MC_POST_ENTITY_TAKE_DMG',target,1,DamageFlag.DAMAGE_POISON_BURN)
assert(mf.speed(player,clock)==1.2,'periodic poison and burn retain the passive speed')
call('MC_POST_ENTITY_TAKE_DMG',target,1,DamageFlag.DAMAGE_FIRE)
assert(mf.speed(player,clock)==1 and mf.attackSpeed(player,clock)>1,'direct fire resets movement speed only')
art={}; advance(clock+1)
assert(not renders(strutAtlas,'GroundWisp') and renders(strutAtlas,'GunSpark'),
 'direct damage clears the passive trail without removing the active gun effect')
assert(mf.speed(player,direct+120)==1.1 and mf.speed(player,direct+210)==1.2)
call('MC_PRE_GAME_EXIT')

player.Position,player.Velocity=Vector.Zero,Vector.Zero
cursor=Vector(100,0)
call('MC_POST_GAME_STARTED',false)
local rAt=clock+1
held.r=true; advance(rAt); held.r=false
cursor=Vector(0,150)
player.Position,player.Velocity=Vector(0,60),Vector(0,5); art={}; advance(rAt+1)
assert(player.Velocity.Y==5 and intent('ACTION_DOWN')==0,
 'Bullet Time blocks voluntary input while preserving native knockback velocity')
local function ultimatePosition(name)
 local atlas=name=='RBullet' and shotAtlas or ultimateAtlas
 if name=='RBullet' then name='RCore' end
 for _,entry in ipairs(art) do
  if entry[1]==atlas and entry[2]==name then return entry.position end
 end
end
assert(ultimatePosition('RCone').Y==60 and not ultimatePosition('RBullet'),
 'the aiming cone follows the player when displaced during windup')
art={}; advance(rAt+2)
assert(ultimatePosition('RBullet').Y>20 and ultimatePosition('RBullet').X>40
 and packet.face[1]==1 and packet.clip=='r','first wave follows displacement and retains the cast heading')
local firstBullet=ultimatePosition('RBullet')
local firstGun=ultimatePosition('RMuzzle')
local function countMuzzles()
 local count=0
 for _,entry in ipairs(art) do
  if entry[1]==ultimateAtlas and entry[2]=='RMuzzle' then count=count+1 end
 end
 return count
end
assert(countMuzzles()==1,'the first barrel fires at the wave start')
renderMillis=20; art={}; call('MC_POST_RENDER'); renderMillis=0
assert(ultimatePosition('RBullet').X>firstBullet.X and clock==rAt+2,
 'R visuals travel between simulation ticks')
assert(countMuzzles()==1,'the same gun fires throughout this wave')
player.Position=Vector(0,95); art={}; call('MC_POST_RENDER')
assert(ultimatePosition('RCone').Y==95 and ultimatePosition('RBullet').Y<65,
 'late position changes move the guide without moving launched visuals')
assert(math.abs(ultimatePosition('RMuzzle').Y-firstGun.Y-35)<.001,
 'the muzzle follows the weapon pose after displacement during the same wave')
player.Position=Vector(0,140); art={}; advance(rAt+3)
assert(ultimatePosition('RCone').Y==140 and ultimatePosition('RBullet').Y<90,
 'the active cone and already launched visual bullets keep separate origins')
art={}; advance(rAt+8)
assert(packet.actionFrame==12 and packet.actionId==rAt+8 and countMuzzles()==1,
 'the next wave presents the left gun firing pose immediately')
assert(packet.mfMuzzle.kind=='r' and packet.mfMuzzle.gun==2)
assert(ultimatePosition('RMuzzle').Y-player.Position.Y>firstGun.Y-60+8,
 'successive waves start from opposite barrels')
advance(rAt+38)
assert(packet.actionFrame==38 and packet.actionId==rAt+38,
 'the Companion frame clock advances through the original loop seam')
assert(call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)==false and art[#art][3]==4,
 'native animation returns to the same right gun shot frame after a full cycle')
call('MC_PRE_GAME_EXIT')

for _,interrupt in ipairs({Keyboard.KEY_A,'mouse1'}) do
 player.Position,player.Velocity=Vector.Zero,Vector.Zero
 call('MC_POST_GAME_STARTED',false)
 key(interrupt,true); held.r=true; advance(clock+1); held.r=false
 advance(clock+2)
 assert(packet.mfBarrage,'same-frame attack or mouse input does not preempt Bullet Time')
 key(interrupt,false); advance(clock+1)
 key(interrupt,true); advance(clock+1); key(interrupt,false)
 assert(not packet.mfBarrage and weapons.enabled,'a new attack or mouse order interrupts the channel')
 call('MC_PRE_GAME_EXIT')
end

-- A new ability order cancels the channel and actually casts on the same key edge.
call('MC_POST_GAME_STARTED',false)
held.r=true; advance(clock+1); held.r=false; advance(clock+2)
assert(packet.mfBarrage)
key(Keyboard.KEY_E,true); advance(clock+1); key(Keyboard.KEY_E,false)
assert(not packet.mfBarrage and packet.clip=='e','R to E swallowed the new spell order')
call('MC_PRE_GAME_EXIT')

player.Position,player.Velocity=Vector.Zero,Vector.Zero
call('MC_POST_GAME_STARTED',false)
advance(clock+6)
local oldAttackLoads=nativeLoads['gfx/mf/action-attack.anm2']
displayId=2
call('MC_EXECUTE_CMD','mftest','anim attack')
advance(clock+1)
assert(call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)==false and art[#art][1]=='gfx/mf/fallback.anm2'
 and nativeLoads['gfx/mf/action-attack.anm2']==oldAttackLoads,
 'a changed viewport uses the small actor until its new projection settles')
advance(clock+4)
assert(call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)==false and art[#art][1]=='gfx/mf/action-attack.anm2'
 and art[#art].scale.X>1 and nativeLoads['gfx/mf/action-attack.anm2']==1,
 'cached source atlas resumes at the projected scale and is never reloaded')

local laughAtlas='gfx/mf/action-laugh.anm2'
assert(nativeLoads[laughAtlas]==nil)
call('MC_EXECUTE_CMD','mftest','anim laugh')
call('MC_POST_RENDER')
lease={version=1,hero='mf',session=packet.session,room=packet.room,display=displayId,ready=true,visible=true,
 time=Isaac.GetTime(),capabilities={mfModel=true}}
advance(clock+3)
art={}; assert(call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)==false)
assert(#art==0 and not nativeLoads[laughAtlas],'healthy Companion owns the visual without opening a native shard')
lease=nil; displayId=3; displayMode='exclusive'; missingClip=laughAtlas
advance(clock+6); art={}
assert(call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)==false and art[#art][1]=='gfx/mf/fallback.anm2'
 and nativeLoads[laughAtlas]==1 and nativeLoads.lastCallback=='MC_POST_UPDATE',
 'missing native resource stays playable in exclusive fullscreen')
advance(clock+4)
assert(nativeLoads[laughAtlas]==1,'a missing clip must not retry on every frame')
call('MC_PRE_GAME_EXIT')

local lifeAtlas='gfx/mf/lifecycle_effects.anm2'
local function lifeArt(name)
 local entries={}
 for _,entry in ipairs(art) do
  if entry[1]==lifeAtlas and entry[2]==name then entries[#entries+1]=entry end
 end
 return entries
end
player.Position,player.Velocity=Vector.Zero,Vector.Zero
call('MC_POST_GAME_STARTED',false)
local diedAt=clock+1
local soundsBeforeDeath=#sounds
deadPlayer,deathSprite=true,true
showEmote(diedAt)
assert(packet.clip=='death' and packet.actionFrame==0 and #sounds==soundsBeforeDeath+2)
assert(sounds[#sounds-1]==audioId('Miss Fortune Death') and sounds[#sounds]==audioId('Miss Fortune Death Voice'),
 'native death starts the independent authored sound and voice once')
showEmote(diedAt+2)
assert(#lifeArt('DeathEmbers')==2 and #lifeArt('DeathBand')==1 and #lifeArt('DeathGroundFlash')==0)
showEmote(diedAt+21)
assert(#lifeArt('DeathGroundFlash')==1)
showEmote(diedAt+30)
assert(#lifeArt('DeathGroundFlash')==2 and #sounds==soundsBeforeDeath+2,
 'the two authored death impacts have separate timings without repeating the sound')

call('MC_PRE_CHANGE_ROOM'); call('MC_POST_NEW_ROOM')
showEmote(clock+1)
assert(#lifeArt('DeathGroundFlash')==0 and #sounds==soundsBeforeDeath+2
 and stopped[#stopped-1]==audioId('Miss Fortune Death') and stopped[#stopped]==audioId('Miss Fortune Death Voice'),
 'room changes clear the old death cues without restarting them on the same dead actor')
deadPlayer,deathSprite=false,false
local revivedAt=clock+1
showEmote(revivedAt)
assert(packet.clip=='respawn' and packet.actionLength==frames.duration('respawn')+1
 and sounds[#sounds-1]==audioId('Miss Fortune Respawn') and sounds[#sounds]==audioId('Miss Fortune Respawn Voice'),
 'revival uses the full source clip and the separate revival audio events')
local reviveSoundCount=#sounds
local firstMuzzle
for _,cue in ipairs({10,28,44}) do
 showEmote(revivedAt+cue-1)
 assert(#lifeArt('RespawnMuzzle')==0)
 showEmote(revivedAt+cue)
 local muzzles=lifeArt('RespawnMuzzle')
 assert(#muzzles==2 and #lifeArt('RespawnFlash')==2
  and (muzzles[1].position-muzzles[2].position):Length()>1,
  'each authored burst spawns at both distinct gun sockets')
 if firstMuzzle then assert((muzzles[1].position-firstMuzzle):Length()>1) end
 firstMuzzle=muzzles[1].position
end
assert(#sounds==reviveSoundCount,'burst rendering must not repeat the start audio')
key(Keyboard.KEY_RIGHT,true); showEmote(clock+1); key(Keyboard.KEY_RIGHT,false)
assert(packet.clip~='respawn' and #lifeArt('RespawnMuzzle')==0
 and stopped[#stopped-1]==audioId('Miss Fortune Respawn') and stopped[#stopped]==audioId('Miss Fortune Respawn Voice'),
 'player movement cancels the revival presentation and audio')

key(Keyboard.KEY_LEFT_CONTROL,true); key(Keyboard.KEY_2,true)
local tauntAt=clock+1
showEmote(tauntAt)
assert(packet.expression=='taunt_spam' and expressionClip()=='taunt_spam')
local tauntAtlas='gfx/mf/taunt_effects.anm2'
assert(renders(tauntAtlas,'TauntRing') and renders(tauntAtlas,'TauntFeather')
 and not renders(tauntAtlas,'TauntArrow') and not renders(tauntAtlas,'TauntBlast'),
 'the source arrival effect starts with the taunt')
key(Keyboard.KEY_2,false)
local tauntSounds=#sounds
local sourceIntro=frames.duration('taunt_spam')
showEmote(tauntAt+14)
assert(not renders(tauntAtlas,'TauntArrow'))
showEmote(tauntAt+15)
local arrow=rendered(tauntAtlas,'TauntArrow')
assert(arrow and arrow.position.Y<player.Position.Y-8,'the arrow starts at the source upper-body joint')
showEmote(tauntAt+24)
assert(not renders(tauntAtlas,'TauntArrow'),'the arrow uses a nine-tick source lifetime')
showEmote(tauntAt+69)
assert(not renders(tauntAtlas,'TauntBlast'))
showEmote(tauntAt+70)
assert(renders(tauntAtlas,'TauntBlast'),'the source shockwave starts on frame 70')
showEmote(tauntAt+sourceIntro+1)
assert(packet.expression=='taunt_spam' and expressionClip()=='taunt_spam_loop'
 and renders('gfx/mf/action-taunt_spam_loop.anm2','taunt_spam_loop2') and renders(tauntAtlas,'TauntBlast'),
 'the default taunt continues into the authored body and doll loop')
showEmote(tauntAt+sourceIntro+2*frames.duration('taunt_loop')+1)
assert(expressionClip()=='taunt_spam_loop' and #sounds==tauntSounds,
 'the looping taunt does not replay the start sound')
key(Keyboard.KEY_2,true); showEmote(clock+1); key(Keyboard.KEY_2,false); showEmote(clock+1)
assert(not packet.expression and stopped[#stopped]==audioId('Miss Fortune Taunt'))

key(Keyboard.KEY_LEFT_CONTROL,true); key(Keyboard.KEY_LEFT_SHIFT,true); key(Keyboard.KEY_2,true)
showEmote(clock+1)
assert(packet.expression=='taunt' and sounds[#sounds-1]==audioId('Miss Fortune Taunt')
 and sounds[#sounds]==audioId('Miss Fortune Taunt Intro') and not renders(tauntAtlas,'TauntRing'),
 'ordinary taunt uses the dedicated source intro cue')
key(Keyboard.KEY_2,false); key(Keyboard.KEY_LEFT_SHIFT,false); key(Keyboard.KEY_LEFT_CONTROL,false)
showEmote(clock+frames.duration('taunt')+1)
assert(packet.expression=='taunt' and expressionClip()=='taunt_loop'
 and renders('gfx/mf/action-taunt_loop.anm2','taunt_loop2'),
 'Shift+Ctrl+2 keeps the alternate intro and plain loop')
call('MC_EXECUTE_CMD','mftest','anim death'); showEmote(clock+1)
local previewDeath=clock
assert(packet.clip=='death' and not player:IsDead())
showEmote(previewDeath+21)
assert(#lifeArt('DeathGroundFlash')==1,'mftest can preview the source death effect with a living actor')
call('MC_PRE_GAME_EXIT')

room.index=4; room.clear=true
player.Position,player.Velocity=Vector.Zero,Vector.Zero
local function expectHomeguardExit(continued, expected)
    call('MC_POST_GAME_STARTED',continued)
    if continued then call('MC_POST_NEW_LEVEL'); call('MC_POST_NEW_ROOM') end
    local rideAt=clock+1
    key(Keyboard.KEY_RIGHT,true); player.Velocity=Vector(3,0)
    advance(rideAt)
    assert(packet.clip=='homeguard_in')
    advance(rideAt+73)
    assert(packet.clip=='homeguard')
    advance(rideAt+74)
    assert(packet.clip==expected and packet.actionFrame==0
        and packet.actionLength==frames.duration(expected)+1 and sounds[#sounds]==audioId('Miss Fortune Homeguard Exit'),
        'Homeguard selects an authored exit for the actual running gait')
    art={}; call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)
    assert(renders('gfx/mf/action-'..expected..'.anm2',expected..'2'),'the native renderer uses the same exit')
    key(Keyboard.KEY_A,true); advance(clock+1)
    assert(packet.clip~=expected and weapons.enabled and stopped[#stopped]==audioId('Miss Fortune Homeguard Exit'),
        'attacking interrupts the exit and stops the attached sound')
    key(Keyboard.KEY_A,false); key(Keyboard.KEY_RIGHT,false); player.Velocity=Vector.Zero
    call('MC_PRE_GAME_EXIT')
end
expectHomeguardExit(false,'homeguard_out')
expectHomeguardExit(true,'homeguard_out_run')

player.Position,player.Velocity=Vector(20,10),Vector.Zero
call('MC_POST_GAME_STARTED',false)
local function castArt(name)
 local rows={}
 for _,entry in ipairs(art) do
  if entry[1]==shotAtlas and entry[2]==name then rows[#rows+1]=entry end
 end
 return rows
end
local function fireAA(weaponType,crit,heading)
 local fireAt=clock+1
 mf.weaponFired('aa',heading or Vector(1,0),{origin=player.Position,weaponType=weaponType,crit=crit},fireAt)
 art={}; advance(fireAt)
end
fireAA(WeaponType.WEAPON_TEARS)
local first=castArt('AACast')
assert(#first==1 and packet.clip=='attack')
assert(math.abs(packet.actionFrame/(packet.actionLength-1)-7/75)<.00001,
 'the confirmed weapon discharge starts on the source fire pose')
advance(clock+5)
fireAA(WeaponType.WEAPON_TEARS)
local second=castArt('AACast')
assert(#second==1 and packet.clip=='attack2' and (first[1].position-second[1].position):Length()>1,
 'ordinary native volleys follow the two alternating source barrel sockets')
advance(clock+5)
fireAA(WeaponType.WEAPON_TEARS,true)
local critFlashes=castArt('AACritCast')
assert(#critFlashes==2 and #castArt('AACritSpark')==2
 and (critFlashes[1].position-critFlashes[2].position):Length()>1,'critical fire uses both source sockets')
advance(clock+5)
fireAA(WeaponType.WEAPON_KNIFE)
assert(#castArt('AACast')==0 and #castArt('AACritCast')==0,'the native knife does not gain a gun muzzle flash')

local qAt=clock+1
mf.weaponFired('q',Vector(1,0),{origin=player.Position,weaponType=WeaponType.WEAPON_TEARS},qAt)
advance(qAt)
assert(packet.clip=='q' and math.abs(packet.actionFrame/(packet.actionLength-1)-6/22)<.00001,
 'Double Up shows the source discharge pose on actual release')
player.MaxFireDelay=2
advance(qAt+2)
fireAA(WeaponType.WEAPON_TEARS,false,Vector(0,1))
assert((packet.clip=='attack' or packet.clip=='attack2') and #castArt('QCast')==0,
 'a confirmed native shot immediately replaces the Q pose and old flash')
assert(math.abs(packet.actionLength-packet.actionFrame-3)<.00001 and #castArt('AACast')==1,
 'fast native tear weapons fit the post-shot pose to their fire interval')
art={}; advance(clock+3)
assert(#castArt('AACast')==0 and (packet.clip=='attack_out' or packet.clip=='attack2_out'),
 'short attacks clear the flash as they enter recovery')

 qAt=clock+1
mf.weaponFired('q',Vector(1,0),{origin=player.Position,weaponType=WeaponType.WEAPON_TEARS},qAt)
advance(qAt)
key(Keyboard.KEY_A,true); cursor=player.Position+Vector(0,100)
art={}; advance(qAt+1)
assert(packet.clip=='q' and packet.face[1]==1 and packet.face[2]==0 and weapons.aim.Y==1,
 'moving the cursor steers the next shot while Q and its muzzle retain the actual shot heading')
assert(call('MC_PRE_PLAYER_RENDER',player,Vector.Zero)==false and art[#art][2]=='q2',
 'the native directional atlas also retains the firing direction')
room.mirrored=true; advance(qAt+2)
assert(packet.face[1]==-1 and packet.face[2]==0 and weapons.aim.Y==1,
 'the mirrored packet reflects the locked direction while native aim stays world-space')
room.mirrored=false
key(Keyboard.KEY_A,false)
key(Keyboard.KEY_E,true); advance(clock+1); key(Keyboard.KEY_E,false)
assert(packet.clip=='e')
fireAA(WeaponType.WEAPON_TEARS,false,Vector(0,1))
assert((packet.clip=='attack' or packet.clip=='attack2') and #castArt('AACast')==1 and renders(shotAtlas,'RainGround'),
 'a native volley after E shows its own firing pose while the ground effect continues')
weapons.hasPendingQ=function() return true end
key(Keyboard.KEY_Q,true); art={}; advance(clock+1); key(Keyboard.KEY_Q,false)
assert(packet.clip=='q_in' and #castArt('AACast')==0 and #castArt('QCast')==0,
 'beginning the next Q windup clears the preceding volley flash')
weapons.hasPendingQ=nil
advance(clock+3)
player.MaxFireDelay=13
call('MC_EXECUTE_CMD','mftest','anim attack'); advance(clock+1)
assert(packet.clip=='attack' and packet.actionFrame==0 and not packet.actionLength,
 'animation preview still starts from the original first frame')

local qRig={modelScale=.26,scale=Vector(1,1),mirrored=false}
local flash={fx={}}
effects.fireMuzzle(flash,'q',player.Position,Vector(1,0),clock,18)
art={}; effects.render(flash,clock,function(v) return v end,player.Position,0,qRig)
local ordinaryQ=castArt('QCast')[1].position
qRig.mirrored=true
art={}; effects.render(flash,clock,function(v) return Vector(800-v.X,v.Y) end,player.Position,0,qRig)
local mirroredQ=castArt('QCast')[1].position
assert(math.abs(ordinaryQ.X+mirroredQ.X-800)<.001 and ordinaryQ.Y==mirroredQ.Y,
 'native muzzle projection reflects with the actor in mirror rooms')

displayMode='windowed'
qAt=clock+1
mf.weaponFired('q',Vector(1,0),{origin=player.Position,weaponType=WeaponType.WEAPON_TEARS},qAt)
art={}; advance(qAt)
assert(packet.mfMuzzle.kind=='q' and packet.mfMuzzle.start==qAt and packet.mfMuzzle.finish==qAt+4
 and #castArt('QCast')==1,'the unsuppressed native flash and Companion share the confirmed shot clock')
lease={version=1,hero='mf',session=packet.session,room=packet.room,display=displayId,ready=true,visible=true,
 time=Isaac.GetTime(),capabilities={mfModel=true,mfMuzzle=true}}
art={}; advance(qAt+2)
assert(packet.mfMuzzle and #castArt('QCast')==0,'acknowledged GPU muzzle replaces the native flash')
lease.capabilities.mfMuzzle=nil
lease.time=Isaac.GetTime()
qAt=clock+1
mf.weaponFired('q',Vector(1,0),{origin=player.Position,weaponType=WeaponType.WEAPON_TEARS},qAt)
art={}; advance(qAt+2)
assert(packet.mfMuzzle and #castArt('QCast')==1,'a live renderer without muzzle support keeps the native flash')
lease=nil
call('MC_PRE_GAME_EXIT')
''')
mod = root / 'src/samira-testroom/mod'
native = mod / 'resources/gfx/mf'
clip_counts = dict(re.findall(r'(\w+) = (\d+),', (mod / 'miss_fortune_sprite_frames.lua').read_text()))
assert not (native / 'actions.anm2').exists(), 'do not ship the monolithic actor'
assert {file.stem.removeprefix('action-') for file in native.glob('action-*.anm2')} == clip_counts.keys()
sheet_sizes = {}
for clip, count in clip_counts.items():
    actor = ET.parse(native / f'action-{clip}.anm2')
    sheet, = actor.findall('./Content/Spritesheets/Spritesheet')
    layer, = actor.findall('./Content/Layers/Layer')
    assert (sheet.get('Id'), layer.get('Id'), layer.get('SpritesheetId')) == ('0', '0', '0')
    texture = native / sheet.get('Path')
    if texture not in sheet_sizes:
        with Image.open(texture) as image:
            sheet_sizes[texture] = image.size
    width, height = sheet_sizes[texture]
    animations = actor.findall('./Animations/Animation')
    assert [animation.get('Name') for animation in animations] == [f'{clip}{i}' for i in range(8)]
    for animation in animations:
        frames = animation.findall('./LayerAnimations/LayerAnimation[@LayerId="0"]/Frame')
        assert len(frames) == int(count) == int(animation.get('FrameNum'))
        for frame in frames:
            x, y, w, h = (int(frame.get(key)) for key in ('XCrop', 'YCrop', 'Width', 'Height'))
            assert 0 <= x < x + w <= width and 0 <= y < y + h <= height, (clip, x, y, w, h)

sys.path.insert(0, str(root / 'src/samira/external'))
from mf_renderer import MissFortuneRenderer


class RecordedActor:
    def __init__(self):
        self.model = SimpleNamespace(durations=dict(crit=70/30, crit_out=80/30, base_idle=4, attack=75/30,
                                                    attack2=2.5, q=22/30, e=37/30, r=1),
                                     rig_events={})
        self.kind = 'crit'
        self.calls = []

    def draw(self, kind, phase, *args, blend_seconds, **kwargs):
        self.kind = kind
        self.calls.append((kind, phase, blend_seconds))


renderer = MissFortuneRenderer(None, root / 'test-model-not-present.glb')
renderer.actor = RecordedActor()
for clip in ('crit_out', 'crit_out', 'base_idle', 'base_idle', 'attack'):
    packet = dict(clip=clip, kind=clip, actionFrame=0, position=[0, 0], screen=[800, 600], face=[1, 0])
    assert renderer.draw(packet, 1/60)[0]
assert [blend for _, _, blend in renderer.actor.calls] == [.10, .10, .10, .10, .04]
for action_frame, source_frame in [(8, 8), (12, 12), (18, 18), (22, 22), (28, 28), (32, 2), (38, 8)]:
    assert renderer.draw(dict(packet, kind='r', clip='r', actionFrame=action_frame,
                              mfBarrage=dict(start=5, interval=6)), 1/60)[0]
    assert renderer.actor.calls[-1] == ('r', source_frame/30, .001)
for clip in ('q', 'attack', 'attack2', 'crit'):
    assert renderer.draw(dict(packet, kind='e', clip='e'), 1/60)[0]
    assert renderer.draw(dict(packet, kind=clip, clip=clip, actionFrame=1, actionLength=4), 1/60)[0]
    assert renderer.actor.calls[-1] == (clip, 1/3, .001), 'a confirmed shot immediately reaches the matching pose'
assert renderer.draw(dict(packet, kind='q', clip='q'), 1/60)[0]
assert renderer.actor.calls[-1] == ('q', 0, .04), 'an animation preview keeps the normal blend'
print('Miss Fortune character checks passed')
