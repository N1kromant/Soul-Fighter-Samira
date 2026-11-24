"""Exercise Miss Fortune HUD placement and its Isaac draw calls in Lua 5.4."""

from pathlib import Path
from hashlib import sha256
import json
from xml.etree import ElementTree

from lupa.lua54 import LuaRuntime
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
MOD = ROOT / 'src/samira-testroom/mod'
lua = LuaRuntime()
lua.globals().sources = lua.table_from({p.stem: p.read_text(encoding='utf-8') for p in MOD.glob('*.lua')})
lua.execute(r'''
function include(name)
    return assert(load(assert(sources[name], 'Missing HUD implementation: ' .. name)))()
end
local width, height = 480, 270
local art, labels, diagonals, tooltipLines, rectangles = {}, {}, {}, {}, {}
local mouseX, mouseY = -1000, -1000
function Vector(x, y) return {X=x, Y=y} end
function Color(...) return {...} end
KColor = Color
function Sprite()
    return {
        SetFrame=function(self, frame) self.frame=frame end,
        Render=function(self, point) art[self.frame]=point end,
    }, true
end
function Font(path)
    assert(path:find('/resources/font/samira_items_ru.fnt', 1, true))
    return {
        GetStringWidthUTF8=function(_, text) return utf8.len(text) * 7 end,
        DrawStringScaledUTF8=function(_, text, x, y, scale)
            tooltipLines[#tooltipLines+1] = {text=text, x=x, y=y, right=x+utf8.len(text)*7*scale}
        end,
    }, true
end
Input = {GetMousePosition=function(world)
    assert(world == false)
    return Vector(mouseX, mouseY)
end}
Isaac = {
    GetScreenWidth=function() return width end,
    GetScreenHeight=function() return height end,
    GetTextWidth=function(text) return #text * 6 end,
    RenderScaledText=function(text, x, y, scale) labels[text]={X=x,Y=y,Scale=scale} end,
    ScreenToWorld=function(point) return Vector(900 - point.X * 2, point.Y * 3 + 50) end,
    WorldToScreen=function(point) return Vector(point.X / 4 + 10, (point.Y - 50) / 6 + 5) end,
    DrawLine=function(a, b, _, _, thickness)
        if a.Y ~= b.Y then diagonals[#diagonals+1]=a
        else rectangles[#rectangles+1]={a.X, a.Y-thickness/2, b.X, a.Y+thickness/2} end
    end,
}

local hud = include('miss_fortune_hud')
local combat = include('miss_fortune_combat')
local runes = include('miss_fortune_runes')
local bounds = assert(hud.bounds(1, {x=6, y=220, width=146, height=46, scale=1}))
assert(bounds.x >= 152 and bounds.bottom > 260, 'HUD should sit beside backpack at the bottom')
assert(hud.bounds(.8).scale == .8, 'HUD should respect configured scale')
assert(bounds.height <= 40, 'HUD must fit in one row without a footer')
width = 255
local wideBackpack = {x=6, y=239.6, width=176.4, height=26.4, scale=1.2}
local narrow = assert(hud.bounds(1.2, wideBackpack))
assert(narrow.right <= width - 6 and narrow.bottom <= 216.2 and narrow.y >= 3,
    'HUD must stay above backpack header if beside it would overflow')
width = 480

local clock = 120
local state = combat.new(clock)
state.ready.q = clock + 69
state.ready.w = clock + 180
state.wUntil = clock + 51
local stats = {damage=4.25, crit=.2, attacks=3.15, haste=12, move=1.15, range=275}
local progress = {rune='arcane_comet', cometReady=clock + 120}
hud.render(bounds, state, clock, stats, runes, progress)
assert(art.Portrait.X < labels['4.25'].X and labels['4.25'].X < art.Q.X, 'Stats belong between portrait and abilities')
assert(#diagonals > 5 and diagonals[1].X < labels['4.25'].X, 'Visible stat glyphs should precede their values')
assert(art.Q.X < art.W.X and art.W.X < art.E.X and art.E.X < art.R.X, 'Art should show all abilities in QWER order')
assert(labels['6s'].Y < labels['W 1.7s'].Y and labels['W 1.7s'].X >= art.W.X
    and labels['W 1.7s'].X < art.E.X, 'Active W timer must sit in the W slot independently of its cooldown')
assert(not labels['Arcane Comet'] and art.arcane_comet.X > art.Portrait.X
    and art.arcane_comet.X < labels['4.25'].X, 'A rune icon by the portrait replaces the footer name')
assert(labels['4s'].X >= art.arcane_comet.X and labels['4s'].Y >= art.arcane_comet.Y,
    'Rune cooldown belongs on its icon')
labels = {}
art.arcane_comet = nil
hud.render(bounds, state, clock, stats, runes, {rune='arcane_comet'})
assert(art.arcane_comet and not labels['4s'] and not labels['Arcane Comet'],
    'Ready Arcane Comet uses its icon alone')
labels = {}
hud.render(bounds, state, clock + 51, stats, runes, progress)
assert(not labels['W 1.7s'], 'Expired W timer should disappear')
labels = {}
hud.render(bounds, state, clock, stats, runes,
    {rune='press_the_attack', pressHits=2, pressExpires=clock + 30})
assert(art.press_the_attack and labels['2'] and not labels['Press the Attack'],
    'Stack runes show the count on their icon without a name')

local function hover(b, dx, dy)
    mouseX, mouseY = (235 - (b.x + dx*b.scale)) * 2, (b.y + dy*b.scale - 5) * 2
    tooltipLines, rectangles = {}, {}
    hud.render(b, state, clock, stats, runes, progress)
end
assert(#tooltipLines == 0, 'Tooltip shown without a hovered stat')
width, height = 170, 95
local compact = assert(hud.bounds(1.4))
local titles = {'Урон', 'Шанс критического удара', 'Темп автоатак', 'Ускорение умений',
    'Скорость передвижения', 'Дальность автоатак'}
for _, b in ipairs({bounds, compact}) do
    if b == bounds then width, height = 480, 270 else width, height = 170, 95 end
    for i, title in ipairs(titles) do
        local dx = (i % 2 == 1) and 68.9 or 69.1
        hover(b, dx, 7 + math.floor((i-1)/2)*10)
        assert(#tooltipLines == 2 and tooltipLines[1].text == title and utf8.len(tooltipLines[2].text) > 20,
            'Each adjacent stat should show only its own title and definition')
        local box = rectangles[#rectangles-1]
        assert(box[1] >= 2.99 and box[2] >= 2.99 and box[3] <= width-2.99 and box[4] <= b.y,
            'Tooltip should fit in the viewport above the HUD')
        for _, line in ipairs(tooltipLines) do
            assert(line.x > box[1] and line.right < box[3] and line.y > box[2] and line.y < box[4],
                'Tooltip text should fit inside the box')
        end
    end
    hover(b, 98, 7)
    assert(#tooltipLines == 0, 'Hovering beside the stats should dismiss the tooltip')
end
''')

actor = MOD / 'resources/gfx/mf/hud_icons.anm2'
tree = ElementTree.parse(actor)
sheet = actor.with_name(tree.find('.//Spritesheet').attrib['Path'])
with Image.open(sheet) as atlas:
    frames = {}
    for animation in tree.findall('.//Animation'):
        frame = animation.find('./LayerAnimations/LayerAnimation/Frame').attrib
        x, y, w, h = [int(frame[key]) for key in ('XCrop', 'YCrop', 'Width', 'Height')]
        assert 0 <= x < x + w <= atlas.width and 0 <= y < y + h <= atlas.height
        frames[animation.attrib['Name']] = atlas.crop((x, y, x + w, y + h)).tobytes()
    assert set(frames) == {'Portrait', 'Q', 'W', 'E', 'R', 'conqueror', 'lethal_tempo', 'electrocute',
                           'press_the_attack', 'arcane_comet', 'first_strike'}
    assert len(set(frames.values())) == len(frames)
manifest = json.loads((ROOT / 'docs/miss-fortune-hud.lock.json').read_text(encoding='utf-8'))
for output, digest in manifest['outputs'].items():
    assert sha256((ROOT / output).read_bytes()).hexdigest() == digest, output

print('Miss Fortune HUD layout, stat tooltips, combat indicators, and icon atlas checks passed')
