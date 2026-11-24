"""MF native damage contracts using the real Weapons, Items and Combat modules.

Reuse the existing item callback fixture; add numeric native-damage and persistent
Ludovico contracts. Isaac's Proptosis distance curve and item engine are not mocked.
"""
import ast
from pathlib import Path
from lupa.lua54 import LuaRuntime

ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / 'src/samira-testroom/mod'
tree = ast.parse((ROOT / 'tools/check_samira_items.py').read_text(encoding='utf-8'))
chunk = next(n.value.args[0].value for n in tree.body
             if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
             and isinstance(n.value.func, ast.Attribute) and n.value.func.attr == 'execute')
lua = LuaRuntime()
for variable, module in {
    'itemsSource': 'samira_items', 'catalogSource': 'samira_items_data',
    'styleSource': 'samira_style', 'yoneCombatSource': 'yone_combat',
    'yoneArtifactsSource': 'yone_artifacts', 'yoneWeaponArtifactsSource': 'yone_artifact_weapons',
    'yoneProgressSource': 'yone_progression', 'missFortuneRunesSource': 'miss_fortune_runes',
    'missFortuneCombatSource': 'miss_fortune_combat', 'nativeWeaponsSource': 'samira_weapons',
    'navigationSource': 'samira_navigation',
}.items():
    lua.globals()[variable] = (MOD / (module + '.lua')).read_text(encoding='utf-8')

extra = r'''
    -- Proptosis-like native damage is an engine input, not p.Damage.
    -- This checks the handoff at two values; it does not model the distance curve.
    for _, incoming in ipairs({3,17}) do
        weapons.reset()
        start({})
        function p:GetWeapon(slot) assert(slot==1); return weapon end
        p.corsair, random = true, .99
        list, state, volleys = {}, combat.new(clock), {}
        function weapon:GetWeaponType() return WeaponType.WEAPON_TEARS end
        function weapon:GetMainEntity() return nil end
        beginDoubleUp()
        local tear = newNativeTear(300,TearVariant.BLUE,TearFlags.TEAR_POISON,Vector(9,0))
        tear.CollisionDamage=incoming
        nativeCallbacks.MC_POST_FIRE_TEAR(nil,tear)
        weapon.fired=weapon.fired+1
        nativeCallbacks.MC_POST_TRIGGER_WEAPON_FIRED(nil,Vector(1,0),1,p,weapon)
        nativeCallbacks.MC_POST_PLAYER_UPDATE(nil,p)
        local lead,secondary=enemy(301,60,60),enemy(302,120,120)
        assert(lead:TakeDamage(incoming,0,EntityRef(tear),0))
        close(lead.hits[1],incoming*1.5*1.35,'native damage survives primary Q and Love Tap')
        assert(tear.CollisionDamage==incoming and tear.TearFlags==TearFlags.TEAR_POISON)
        assert(#state.pendingBounce==1 and state.pendingBounce[1].baseDamage==incoming,
            'ricochet retains pre-multiplier native damage rather than player Damage')
        for _=1,5 do step(); combat.update(state,p,clock,game:GetRoom(),Items) end
        close(secondary.hits[1],incoming*1.5*1.35,'native damage survives one ricochet')
        assert(#secondary.hits==1 and #state.pendingBounce==0)
    end

    weapons.reset()
    start({})
    function p:GetWeapon(slot) assert(slot==1); return weapon end
    p.corsair, random = true,.99
    list,state,volleys={},combat.new(clock),{}
    WeaponType.WEAPON_LUDOVICO_TECHNIQUE=77
    TearFlags.TEAR_LUDOVICO=1<<27
    local orb=newNativeTear(303,TearVariant.BLUE,TearFlags.TEAR_LUDOVICO|TearFlags.TEAR_POISON,Vector(0,0))
    orb.Position=Vector(0,0)
    function orb:HasTearFlags(flag) return self.TearFlags & flag == flag end
    function orb:GetColor() return Color(1,1,1,1,0,0,0) end
    function weapon:GetWeaponType() return WeaponType.WEAPON_LUDOVICO_TECHNIQUE end
    function weapon:GetMainEntity() return orb end
    beginDoubleUp()
    nativeCallbacks.MC_POST_PLAYER_UPDATE(nil,p)
    assert(#volleys==1 and volleys[1].ctx.persistentPulse and not weapons.hasPendingQ(p))
    local lead,secondary=enemy(304,60,60),enemy(305,120,120)
    assert(lead:TakeDamage(7,0,EntityRef(orb),0))
    close(lead.hits[1],7*1.5*1.35,'Ludovico Q enhances the accepted pulse')
    assert(#state.pendingBounce==1 and state.pendingBounce[1].baseDamage==7)
    assert(lead:TakeDamage(7,0,EntityRef(orb),0))
    close(lead.hits[2],7,'the consumed Ludovico pulse returns to normal native damage')
    assert(#state.pendingBounce==1 and orb.Scale==1)
    for _=1,5 do step(); combat.update(state,p,clock,game:GetRoom(),Items) end
    assert(#secondary.hits==1 and #state.pendingBounce==0)
    close(secondary.hits[1],7*1.5*1.35,'Ludovico pulse ricochets exactly once')
    function weapon:GetMainEntity() return nil end
    print('PASS MF native damage preservation and Ludovico accepted-pulse contracts')
'''
marker = '    -- Exercise C Section through the native tear path.'
assert chunk.count(marker) == 1, 'item integration fixture boundary changed'
lua.execute(chunk.replace(marker, extra + '\n' + marker, 1))
