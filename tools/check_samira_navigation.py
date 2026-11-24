"""Replay mouse navigation against the upstream Isaac API double, without starting Isaac."""
import ast
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work/python-deps"))
from lupa.lua54 import LuaError, LuaRuntime


def mock_prelude():
    path = ROOT / "tools/check_samira_combat.py"
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
            lua = ast.literal_eval(node.args[0])
            prelude, marker, _ = lua.partition("-- Mouse door entry")
            if marker:
                return prelude
    raise RuntimeError(f"Could not locate Isaac API double in {path}")


HELPERS = """
start()
local function block(col, row, kind)
    wall[row * room:GetGridWidth() + col] = kind or 4
end
local function walk(ticks)
    for i=1,ticks do
        tick()
        -- The mock does not simulate wall collision. Independently check the
        -- eight directions around a small player's collision footprint.
        for angle=0,315,45 do
            local edge=player.Position + Vector(8,0):Rotated(angle)
            assert(room:IsPositionInRoom(edge,0) and room:GetGridCollision(room:GetGridIndex(edge))==0,
                ('clipped obstacle at %.1f, %.1f'):format(edge.X,edge.Y))
        end
    end
end
local function arrived(goal)
    assert(player.Position:Distance(goal) < 6,
        ('stopped at %.1f, %.1f instead of %.1f, %.1f'):format(player.Position.X,player.Position.Y,goal.X,goal.Y))
    assert(packet.visual.moveGoal == nil, 'stale move order at destination')
end
"""

CASES = {
    "symmetric cursor aiming under an offset viewport": """
        local navigation = include('samira_navigation')
        local width, window = 688, Vector.Zero
        local function project(point)
            return Vector(point.X*.75+40, point.Y*.5+84)
        end
        local function unproject(point)
            return Vector((point.X-40)/.75, (point.Y-84)/.5)
        end
        Isaac.GetScreenWidth = function() return width end
        Isaac.WorldToScreen = project
        Isaac.WorldToScreenDistance = function(point) return project(point)-project(Vector.Zero) end
        Isaac.RenderToWorld = unproject
        Isaac.ScreenToWorld = function(point) return unproject(Vector(point.X/5+19,point.Y/4-11)) end
        Input.GetMousePosition = function(world) assert(not world); return window end
        local function aim(point, mirrored)
            local screen = project(point)
            local x = mirrored and width-screen.X or screen.X
            window = Vector((x-19)*5,(screen.Y+11)*4)
            room.IsMirrorWorld = function() return mirrored end
            return navigation.worldCursor(room)
        end
        for _, mirror in ipairs({false,true}) do
            local origin = Vector(260,140)
            local left, right = Vector(-80,-20), Vector(80,-20)
            assert(aim(origin+left,mirror):Distance(origin+left)<.001, 'the left cursor missed')
            assert(aim(origin+right,mirror):Distance(origin+right)<.001, 'the right cursor missed')
        end
        Isaac.RenderToWorld = nil
        assert(aim(Vector(180,120),true):Distance(Vector(180,120))<.001, 'mirror fallback missed')
    """,
    "scaled native acceleration with turn, stop, knockback and rollback": """
        -- Our usual tick double ignores carried velocity. This regression
        -- explicitly applies both inertia and current input as the engine can.
        local function physics(key, right, cursor)
            local pos, v = player.Position, player.Velocity
            local x = callAction('ACTION_RIGHT')-callAction('ACTION_LEFT')
            local y = callAction('ACTION_DOWN')-callAction('ACTION_UP')
            local nextV = v*.8 + Vector(x,y)*(2*player.MoveSpeed)
            tick(key,right,cursor,function()
                player.Velocity=nextV
                player.Position=pos+nextV
            end)
            return player.Velocity
        end
        local function straight(percent,native)
            start(); combat.setInertia(native); combat.setWalkSpeed(percent)
            physics(nil,true,Vector(370,100))
            assert(player.Velocity:Length()==0, 'start injected extra velocity')
            for i=1,12 do physics() end
            return player.Velocity.X
        end
        local baseline=straight(100,true)
        assert(math.abs(straight(100,false)-baseline)<.001)
        assert(math.abs(straight(70,false)/baseline-.70)<.001)
        assert(math.abs(straight(85,false)/baseline-.85)<.001)
        player.Velocity=Vector(player.Velocity.X,1.5)
        local before=player.Velocity*.8+Vector(1.7,0)
        local reversed=physics(nil,true,Vector(20,player.Position.Y+1.2))
        assert(reversed.X<0 and reversed:Length()<=before:Length()+.001)
        assert(math.abs(reversed.Y-1.2)<.001,'turn erased transverse impulse')
        local stopped=physics('KEY_S')
        assert(math.abs(stopped.X)<.001 and stopped.Y>0,'stop erased external push or coasted')
        combat.setInertia(true); combat.setWalkSpeed(100)
        physics(nil,true,Vector(350,100)); physics(); assert(physics('KEY_S').X>0)
        combat.setInertia(false); physics(nil,true,Vector(350,100)); physics()
        local flags=player.HasEntityFlags
        player.HasEntityFlags=function(_,flag) return flag==EntityFlag.FLAG_KNOCKED_BACK end
        assert(physics('KEY_S').X>0,'forced knockback was cancelled')
        player.HasEntityFlags=flags
    """,
    "held ground click steers past enemies": """
        local enemy=makeEntity('enemy',60,180,21)
        entities={enemy}
        tick(nil,true,Vector(250,100))
        for i=1,12 do tick(nil,true,enemy.Position) end
        assert(packet.visual.target==nil and callAction('ACTION_DOWN')>.5)
        walk(100); arrived(enemy.Position)
    """,
    "retreat takes priority over held A": """
        combat.setAttackMove(false)
        input.held='KEY_A'; tick(nil,false,Vector(200,100))
        tick(nil,true,Vector(60,180))
        for i=1,15 do tick(nil,false,Vector(60,180)) end
        assert(player.Position.Y>125 and #shots==1, 'held A ate retreat order')
        input.held=nil; tick()
        tick('KEY_A'); assert(#shots==2, 'fresh A press failed')
    """,
    "one A tap acquires a foe en route then resumes": """
        local goal=Vector(340,100)
        tick('KEY_A',false,goal); walk(10)
        assert(player.Position.X>75 and #shots==0, 'empty ground should issue a move order')
        local enemy=makeEntity('enemy',220,118,31)
        entities={enemy}; walk(60)
        assert(packet.visual.target and packet.visual.target[1]==enemy.Position.X*projection)
        assert(#shots>0 and player.Position:Distance(goal)>50, 'failed to stop and attack on the route')
        enemy.dead=true; walk(180); arrived(goal)
    """,
    "ground attack selects eligible hostile nearest original cursor": """
        local nearPlayer=makeEntity('enemy',100,100,32)
        local nearClick=makeEntity('enemy',175,105,33)
        local friendly=makeEntity('enemy',185,110,34); friendly.friendly=true
        local dead=makeEntity('enemy',185,100,35); dead.dead=true
        entities={nearPlayer,dead,friendly,nearClick}
        tick('KEY_A',false,Vector(210,105))
        for i=1,12 do tick(nil,false,nearPlayer.Position) end
        assert(packet.visual.target and packet.visual.target[1]==nearClick.Position.X*projection,
            'cursor drift or entity ordering stole the target')
    """,
    "attack-move ignores an occluded incidental enemy": """
        block(2,2)
        local goal=Vector(60,180)
        entities={makeEntity('enemy',142,100,40)}
        tick('KEY_A',false,goal)
        assert(packet.visual.target==nil and callAction('ACTION_DOWN')>.5)
    """,
    "enemy under cursor takes priority and is approached": """
        local incidental=makeEntity('enemy',110,95,36)
        local aimed=makeEntity('enemy',310,100,37)
        entities={incidental,aimed}
        tick('KEY_A',false,aimed.Position); walk(90)
        assert(packet.visual.target and packet.visual.target[1]==aimed.Position.X*projection)
        assert(player.Position.X>140 and #shots>0, 'explicit target outside initial weapon range was ignored')
    """,
    "incidental target escaping range does not redirect the route": """
        local goal=Vector(270,100)
        local enemy=makeEntity('enemy',150,100,38)
        entities={enemy}; tick('KEY_A',false,goal); walk(12)
        assert(packet.visual.target)
        enemy.Position=Vector(390,230)
        walk(160); arrived(goal)
    """,
    "stop cancels held attack-move until a fresh press": """
        input.held='KEY_A'; tick(nil,false,Vector(300,100))
        tick('KEY_S',false,Vector(300,100))
        for i=1,12 do tick(nil,false,Vector(150,180)) end
        assert(packet.visual.moveGoal==nil and packet.visual.target==nil)
        input.held=nil; tick(); tick('KEY_A',false,Vector(60,180)); walk(100)
        arrived(Vector(60,180))
    """,
    "mode switch clears A and requires a fresh press in either mode": """
        input.held='KEY_A'; tick(nil,false,Vector(300,100))
        combat.setAttackMove(false)
        for i=1,16 do tick(nil,false,Vector(300,100)) end
        assert(packet.visual.moveGoal==nil and #shots==0)
        input.held=nil; tick(); input.held='KEY_A'; tick(nil,false,Vector(300,100))
        assert(#shots==1, 'direct fire mode did not accept fresh A')
        combat.setAttackMove(true); walk(16)
        assert(#shots==1 and packet.visual.moveGoal==nil)
        input.held=nil; tick(); tick('KEY_A',false,Vector(60,180)); walk(100)
        arrived(Vector(60,180))
    """,
    "detour around rocks": """
        block(3,1); block(3,2); block(3,3)
        local goal=Vector(260,100)
        tick(nil,true,goal)
        walk(240)
        arrived(goal)
    """,
    "sealed target cell ends on reachable side": """
        for row=0,5 do block(4,row) end
        tick(nil,true,Vector(260,100))
        walk(150)
        assert(player.Position.X>=132 and player.Position.X<160, 'did not approach reachable side')
        assert(packet.visual.moveGoal==nil, 'unreachable move order kept retrying')
    """,
    "wall click ends nearby and outside the wall": """
        block(4,2)
        local goal=Vector(180,100)
        tick(nil,true,goal)
        walk(150)
        assert(player.Position:Distance(goal)<=47, 'stopped far from clicked wall')
        assert(packet.visual.moveGoal==nil, 'wall click kept retrying')
    """,
    "diagonal corner clearance": """
        block(3,2); block(2,3)
        player.Position=Vector(100,100)
        local goal=Vector(140,140)
        tick(nil,true,goal); walk(240); arrived(goal)
    """,
    "attack from reachable line of sight across pit": """
        -- The wall hides the target from the nearest reachable cell. The
        -- rest of the barrier is a pit, so a diagonal firing position works.
        for row=0,5 do block(4,row,row==2 and 4 or 1) end
        local enemy=makeEntity('enemy',258,100,11)
        entities={enemy}
        tick(nil,true,enemy.Position); walk(240)
        assert(#shots>0,'never acquired a reachable firing position')
        assert(player.Position.X<160 and room:CheckLine(player.Position,enemy.Position,3),
            'fired without a clear line')
        assert(packet.visual.target~=nil, 'lost explicit target')
    """,
    "replace mid-route click": """
        block(3,2)
        tick(nil,true,Vector(300,100)); walk(10)
        local replacement=Vector(60,180)
        tick(nil,true,replacement); walk(120); arrived(replacement)
    """,
    "redirect route into native doorway": """
        block(3,2)
        tick(nil,true,Vector(300,100)); walk(10)
        local center=Vector(0,100)
        doors[0]={Position=center,IsOpen=function() return true end}
        tick(nil,true,Vector(-20,100))
        for i=1,130 do
            tick()
            if player.Position.X<0 then break end
        end
        assert(player.Position.X<0 and math.abs(player.Position.Y-center.Y)<18,
            'replacement door order did not exit through native corridor')
    """,
}


def main():
    files = {p.stem: p.read_text(encoding="utf-8") for p in (ROOT / "src/samira-testroom/mod").glob("*.lua")}
    base = mock_prelude() + HELPERS
    failures = 0
    for name, scenario in CASES.items():
        runtime = LuaRuntime()
        runtime.globals().sourceFiles = runtime.table_from(files)
        try:
            runtime.execute(base + scenario)
        except LuaError as error:
            print(f"FAIL {name}: {str(error).splitlines()[0]}")
            failures += 1
        else:
            print(f"PASS {name}")
    return int(failures != 0)


if __name__ == "__main__":
    sys.exit(main())
