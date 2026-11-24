"""Verify the six inventory slots and input edges under the native projection."""
from pathlib import Path
import sys
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'work/python-deps'))
from lupa.lua54 import LuaRuntime

lua = LuaRuntime()
MOD = ROOT / 'src/samira-testroom/mod'
ASSET = MOD / 'resources/gfx/items/collectibles/samira_hud_icon.anm2'
frame = ElementTree.parse(ASSET).find('.//LayerAnimation/Frame')
assert (frame.get('Width'), frame.get('Height'), frame.get('XPivot'), frame.get('YPivot')) == ('32', '32', '16', '16')
lua.globals().sources = lua.table_from({name: (MOD / f'{name}.lua').read_text(encoding='utf-8')
                                      for name in ('samira_inventory_hud', 'samira_item_icons',
                                                   'samira_item_description', 'samira_items_data',
                                                   'samira_crafting_ui', 'samira_shop_crafting')})
lua.globals().texture_exists = lambda path: (MOD / 'resources' / path).is_file()
lua.execute(r'''
function include(name) return assert(load(sources[name], name))() end
local vec = {}
vec.__index = vec
Vector = setmetatable({}, {__call = function(_, x, y) return setmetatable({X = x, Y = y}, vec) end})
Vector.Zero = Vector(0, 0)
function vec.__sub(a, b) return Vector(a.X - b.X, a.Y - b.Y) end
function vec.__mul(a, b) return Vector(a.X * b, a.Y * b) end
function KColor(...) return {...} end
local hud = include('samira_inventory_hud')
local width, height, mouse, left, xKey, paused = 640, 270, Vector.Zero
local rectangles, icons, words, textureLoads = {}, {}, {}, 0
Options = {HUDOffset = 0}
Keyboard = {KEY_X = 88}
Input = {
    IsMouseBtnPressed = function(button) assert(button == 0); return left end,
    IsButtonPressed = function(key) assert(key == 88); return xKey end,
    GetMousePosition = function(inWorld) assert(not inWorld); return mouse end,
}
Isaac = {
    GetScreenWidth = function() return width end,
    GetScreenHeight = function() return height end,
    ScreenToWorld = function(v) return Vector(v.X * 0.7 + 10, v.Y * 0.8 + 20) end,
    WorldToScreenDistance = function(v) return Vector(v.X / 2, v.Y / 2) end,
    DrawLine = function(start, finish, color, _, thickness)
        rectangles[#rectangles + 1] = {start.X, start.Y - thickness / 2, finish.X, start.Y + thickness / 2, color}
    end,
}
function Sprite(path, loadGraphics)
    if path == 'gfx/league_shop/shop_ui.anm2' then
        return {
            SetFrame = function(self, name, index)
                assert((name == 'Panel' or name == 'Coin' or name == 'Shop') and index == 0)
                self.frame = name
            end,
            Render = function(self, pos)
                icons[#icons + 1] = {self.frame, pos.X, pos.Y, self.Scale.X}
            end,
        }, true
    end
    assert(path == 'gfx/items/collectibles/samira_hud_icon.anm2' and not loadGraphics)
    return {
        ReplaceSpritesheet = function(self, layer, texture, reload)
            assert(layer == 0 and reload and texture_exists(texture))
            self.texture = texture
            textureLoads = textureLoads + 1
        end,
        SetFrame = function(_, name, index) assert(name == 'Idle' and index == 0) end,
        Render = function(self, pos)
            assert(self.Scale.X == self.Scale.Y)
            icons[#icons + 1] = {self.texture, pos.X, pos.Y, self.Scale.X}
        end,
    }, true
end
function Font(path)
    if path == 'mods/samira_testroom/resources/font/samira_items_ru.fnt' then return nil, false end
    assert(path == 'font/samira_items_ru.fnt' or path == 'font/pftempestasevencondensed.fnt')
    return {
        GetStringWidthUTF8 = function(_, text) return utf8.len(text) * 7 end,
        DrawStringScaledUTF8 = function(_, text, x, y) words[#words + 1] = {text, x, y} end,
    }, true
end
local slots, selected, selections, drops = {}, 1, {}, {}
local inventory = {
    slots = function() return slots end,
    selected = function() return selected end,
    select = function(i) selected = i; selections[#selections + 1] = i end,
    drop = function(_, i) drops[#drops + 1] = i; slots[i] = nil end,
}
local trinket
local player = {GetTrinket = function(_, slot) return slot == 0 and trinket or 0 end}
local game = {IsPaused = function() return paused end}
hud.init(game, inventory)

local function hover(index, x, scale)
    local b = hud.bounds(player, scale)
    mouse = Vector((b.x + ((index - 1) * 25 + (x or 10)) * b.scale) / 0.35, (b.y + 10 * b.scale) / 0.4)
end
hud.render(player)
assert(#rectangles == 12 and #icons == 0 and #words == 0)
assert(rectangles[1][5][1] == 1 and rectangles[3][5][1] < 1)
left = true
hover(4)
hud.input(player, true)
assert(#selections == 1 and selected == 4)
hover(2)
hud.input(player, true)
assert(#selections == 1 and selected == 4)
left = false
hud.input(player, true)
left = true
hover(4, 23)
hud.input(player, true)
assert(#selections == 1)
left = false
hud.input(player, true)
left, xKey = true, true
hover(2)
hud.input(player, false)
hud.input(player, true)
assert(#selections == 1 and #drops == 0)
left, xKey = false, false
hud.input(nil, false)
local icon = 'gfx/items/collectibles/samira_item_3072.png'
slots[4] = {collectibleId = 900, icon = icon, name = 'Кровопийца', descriptionRu = 'Шанс восстановить ½ красного сердца.',
    stats = {damage_flat = 3.2, lifesteal_chance_pct = 3.75}}
rectangles, icons, words = {}, {}, {}
hover(4)
hud.render(player)
assert(#icons == 1 and icons[1][1] == icon and icons[1][4] == .55 and #words >= 3)
assert(words[1][1] == 'Кровопийца' and words[#words][1] == 'X · выбросить выбранное')
local observed = {}
for _, word in ipairs(words) do observed[#observed + 1] = word[1] end
assert(table.concat(observed, ' '):find('Урон +3,2 · Шанс вампиризма автоатак +3,75%', 1, true))
mouse = Vector.Zero
rectangles, icons, words = {}, {}, {}
hud.render(player)
observed = {}
for _, word in ipairs(words) do observed[#observed + 1] = word[1] end
local compact = table.concat(observed, ' ')
assert(compact:find('Кровопийца', 1, true) and compact:find('Урон +3,2', 1, true))
assert(not compact:find('восстановить', 1, true), 'passive should be expanded only on hover')
local oldTop, oldBottom = rectangles[13][2], rectangles[13][4]
local combatPanel = {x = 120, y = oldBottom - 8, width = 174}
rectangles = {}
hud.render(player, 1, combatPanel)
assert(rectangles[13][4] == combatPanel.y - 3 and rectangles[13][2] < oldTop,
    'selected tooltip overlapped the combat panel')
combatPanel.x = 170
rectangles = {}
hud.render(player, 1, combatPanel)
assert(rectangles[13][4] == oldBottom, 'separate combat panel moved the selected tooltip')
slots[1] = slots[4]
slots[6] = {name='Ботинки', stats={move_speed_flat=.075}, icon=icon}
local summary = hud.statsSummary(player)
assert(summary:find('Урон +6,4',1,true) and summary:find('Шанс вампиризма автоатак +7,5%',1,true))
assert(summary:find('Скорость движения +0,075',1,true))
assert(summary:find('1. Кровопийца',1,true) and summary:find('4. Кровопийца',1,true))
assert(summary:find('2. Пусто',1,true) and summary:find('6. Ботинки',1,true))
slots[1], slots[6] = nil, nil
assert(not hud.statsSummary(player):find('Урон +6,4',1,true))
assert(hud.statsSummary(nil):find('забеге',1,true))
for _, size in ipairs({480, 640}) do
    width = size
    for _, offset in ipairs({0, 1}) do
        Options.HUDOffset = offset
        hover(4)
        rectangles, icons, words = {}, {}, {}
        hud.render(player)
        assert(#rectangles >= 14 and #icons == 1)
        local b = hud.bounds(player)
        assert(b.x == 6 + offset * 16 and b.y + b.height == height - 4)
        for _, r in ipairs(rectangles) do
            assert(r[1] >= b.x and r[3] <= b.x + b.width)
            assert(r[2] >= 0 and r[4] <= height - 4)
        end
        trinket = 42
        assert(hud.bounds(player).x == 70 + offset * 16)
        trinket = nil
    end
end
assert(textureLoads == 1)
local stored = slots[4]
for _, item in ipairs(include('samira_items_data')) do
    slots[4] = item
    hover(4)
    rectangles, icons, words = {}, {}, {}
    hud.render(player)
    assert(rectangles[13][2] >= 0, item.name)
    assert(#words > 2 and table.concat(words[1], ' '):find(item.name:match('^[^ ]+'), 1, true), item.name)
end
slots[4] = stored
width, height, trinket = 480, 160, 42
for _, scale in ipairs({.75, 1.5}) do
    local b = hud.bounds(player, scale)
    assert(b.x == 86 and b.width == 147 * scale and b.y + b.height == height - 4)
    left = true
    hover(5, 23, scale)
    hud.input(player, true, scale)
    assert(selected == 4, 'click in a scaled slot gap changed the selection')
    left = false
    hud.input(player, true, scale)
    left = true
    hover(6, 21, scale)
    hud.input(player, true, scale)
    assert(selected == 6, 'click near the right edge of the scaled bag missed the slot')
    left = false
    hud.input(player, true, scale)
    left = true
    hover(4, 10, scale)
    hud.input(player, true, scale)
    assert(selected == 4)
    left = false
    hud.input(player, true, scale)
    rectangles, icons, words = {}, {}, {}
    hud.render(player, scale)
    assert(#icons == 1 and icons[1][4] == .55 * scale and #words >= 3)
    for _, r in ipairs(rectangles) do
        assert(r[2] >= 0 and r[4] <= height and r[3] <= width)
    end
end
width = 240
local narrow = hud.bounds(player, 1.5)
assert(narrow.width + narrow.x <= width - 4 and narrow.scale < 1.5)
paused, xKey = true, true
hud.input(player, true)
paused = false
hud.input(player, true)
assert(#drops == 0)
xKey = false
hud.input(player, true)
xKey = true
hud.input(player, true)
hud.input(player, true)
assert(#drops == 1 and drops[1] == 4 and not slots[4])

do
    local craft = include('samira_shop_crafting')
    local rows = {}
    for _, row in ipairs(include('samira_items_data')) do rows[row.riotId] = row end
    local coins, daggers, purchases = 5, 1, 0
    function player:GetNumCoins() return coins end
    inventory.recipes = function(owner)
        assert(owner == player)
        local recipes = {}
        local missing = {{1042, 3086, 1042}, {1042}, {}}
        for _, id in ipairs({6696, 1053, 6675, 3031, 3046, 6673, 3179, 3181, 6692}) do
            local row = rows[id]
            recipes[#recipes + 1] = {row = row, combinePrice = row.combinePrice,
                missing = id == 6675 and missing[daggers + 1] or row.components}
        end
        return recipes
    end
    inventory.craft = function(owner, id)
        assert(owner == player and id == 6675 and coins == 6 and daggers == 2)
        coins, daggers, purchases = 0, 0, purchases + 1
        return true
    end
    craft.init(inventory)
    width, height, left = 640, 270, false
    local pointer = Vector.Zero
    local function render()
        words, rectangles, icons = {}, {}, {}
        craft.render(pointer)
    end
    local function find(label)
        for _, row in ipairs(words) do
            if row[1]:find(label, 1, true) then return row end
        end
    end
    local function click(label)
        render()
        local target = assert(find(label), label)
        pointer = Vector(target[2] + 1, target[3] + 1)
        assert(craft.onMousePressed(pointer, 0))
        render()
    end
    render()
    assert(#words == 0 and not craft.isOpen())
    assert(craft.open(player))
    render()
    assert(craft.isOpen() and find('Рецепты') and find('1 / 2'))
    assert(icons[1][1] == 'Panel' and icons[2][1] == 'Shop' and icons[3][1] == 'Coin')
    assert(not find('Вампирский скипетр'), 'floor component appeared in recipe catalog')
    click('>')
    assert(find('2 / 2'), 'second recipe page is unreachable')
    click('<')
    click('Летающий нож Навори')
    assert(find('Темп автоатак') and find('Успешные автоатаки') and find('Доплата 6 мон.'))
    local ingredientNames, ingredientStatus = {}, {}
    for _, word in ipairs(words) do
        if word[1] == 'Кинжал' or word[1] == 'Рвение' then
            ingredientNames[#ingredientNames + 1] = word[1]
        elseif word[1] == 'Есть' or word[1] == 'Нет' then
            ingredientStatus[#ingredientStatus + 1] = word[1]
        end
    end
    assert(table.concat(ingredientNames, ',') == 'Кинжал,Рвение,Кинжал')
    assert(table.concat(ingredientStatus, ',') == 'Есть,Есть,Нет')
    coins = 6
    click('Собрать')
    assert(purchases == 0, 'recipe with a missing duplicate was submitted')
    coins, daggers = 5, 2
    click('Собрать')
    assert(purchases == 0 and find('Не хватает монет'), 'unaffordable recipe was submitted')
    coins = 6
    click('Собрать')
    assert(purchases == 1 and find('Собран предмет'))
    click('Собрать')
    assert(purchases == 1, 'missing material allowed another purchase')
    assert(craft.onMousePressed(pointer, 1))
    render()
    assert(not craft.isOpen() and #words == 0)
    width, height = 240, 120
    assert(craft.open(player))
    render()
    assert(craft.isOpen() and find('Собрать'), 'scaled compact shop lost crafting controls')
    for _, row in ipairs(rectangles) do
        assert(row[1] >= 0 and row[2] >= 0 and row[3] <= width and row[4] <= height)
    end
    click('X')
    assert(not craft.isOpen())
end
''')
print('Passed inventory HUD, scaling, input and mouse-driven shop crafting.')
