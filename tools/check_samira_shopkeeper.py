"""Check merchant placement and right-click routing without starting Isaac."""

from pathlib import Path

from check_samira_navigation import mock_prelude
from lupa.lua54 import LuaRuntime


MOD = Path(__file__).resolve().parents[1] / "src/samira-testroom/mod"
lua = LuaRuntime()
lua.globals().merchantSource = (MOD / "samira_shopkeeper.lua").read_text(encoding="utf-8")
lua.execute(r"""
local vector = {}
vector.__index = vector
function Vector(x, y) return setmetatable({X=x, Y=y}, vector) end
function vector.__add(a, b) return Vector(a.X + b.X, a.Y + b.Y) end
function vector.__sub(a, b) return Vector(a.X - b.X, a.Y - b.Y) end
function vector:Distance(other)
    return math.sqrt((self.X - other.X)^2 + (self.Y - other.Y)^2)
end

local callbacks, buttons, sprites = {}, {}, {}
ModCallbacks = {MC_POST_UPDATE=1, MC_POST_NEW_ROOM=2, MC_PRE_GAME_EXIT=3}
CallbackPriority = {EARLY=-100}
local mod = {}
function mod:AddPriorityCallback(event, priority, callback)
    assert(priority == CallbackPriority.EARLY)
    self:AddCallback(event, callback)
end
function mod:AddCallback(event, callback) callbacks[event] = callback end
RoomType = {ROOM_SHOP=2}
EntityType = {ENTITY_PICKUP=5, ENTITY_SHOPKEEPER=17}
GridCollisionClass = {COLLISION_NONE=0}
local tiles = {Vector(100, 50), Vector(140, 50), Vector(80, 75)}
local room, player = {shop=true, clear=true, seed=2}, {Position=Vector(100, 120)}
function room:GetType() return self.shop and RoomType.ROOM_SHOP or 1 end
function room:IsClear() return self.clear end
function room:GetSpawnSeed() return self.seed end
function room:IsMirrorWorld() return self.mirror end
function room:GetCenterPos() return Vector(100, 100) end
function room:GetTopLeftPos() return Vector(20, 6) end
function room:GetGridSize() return #tiles end
function room:GetGridPosition(index) return tiles[index + 1] end
function room:IsPositionInRoom() return true end
function room:GetGridCollision() return 0 end
function room:GetGridEntity() return nil end
function room:GetDoor() return nil end

local cursor = Vector(140, 50)
local viewportOrigin = Vector(0, 0)
Input = {
    IsMouseBtnPressed=function(button) return buttons[button] == true end,
    GetMousePosition=function(world)
        assert(not world)
        return Vector((cursor.X - viewportOrigin.X) * 4, (cursor.Y - viewportOrigin.Y) * 4)
    end,
}
local passing = false
local game = {GetRoom=function() return room end}
Isaac = {
    IsInGame=function() return true end,
    GetRoomEntities=function()
        return {{Type=5, Position=tiles[1]}, {Type=17, Position=Vector(224, 60)}}
    end,
    ScreenToWorld=function(point) return Vector(point.X / 4, point.Y / 4) + viewportOrigin end,
    WorldToScreen=function(point) return Vector(point.X, point.Y) end,
    GetScreenWidth=function() return 300 end,
    RenderText=function() end,
}
function Sprite(path)
    local sprite = {path=path}
    function sprite:Play(animation) self.animation=animation end
    function sprite:Render(position) self.position=position end
    function sprite:Update() end
    sprites[#sprites + 1] = sprite
    return sprite, true
end

local panel = {opened=false}
function panel.open(owner) assert(owner == player); panel.opened=true; return true end
function panel.isOpen() return panel.opened end
function panel.close() panel.opened=false end
function panel.render(pointer) panel.pointer=pointer end
function panel.onMousePressed(pointer, button)
    panel.pointer, panel.button = pointer, button
    if button == 1 then panel.close() end
end
local merchant = assert(load(merchantSource, '@samira_shopkeeper.lua'))()
merchant.init(mod, game, function() return player end, function() return passing end, panel)
local function tick(right, left) buttons[1], buttons[0] = right, left; callbacks[ModCallbacks.MC_POST_UPDATE]() end
local function roomChanged() callbacks[ModCallbacks.MC_POST_NEW_ROOM]() end

merchant.render()
assert(#sprites == 0 and not merchant.isBlocking())
passing = true
merchant.render()
local vendor = sprites[1]
assert(vendor.path:find('shopkeeper_south', 1, true) and vendor.animation == 'Idle')
assert(vendor.position.X == 140, 'Merchant must avoid component pedestals')
cursor = Vector(220, 210)
tick(true, false)
assert(not panel.opened and not merchant.isBlocking(), 'Ground click must stay available for movement')
tick(false, false)
cursor = Vector(140, 30)
tick(true, false)
assert(panel.opened and merchant.isBlocking(), 'Right-click on vendor must capture combat input')
tick(true, false)
assert(panel.opened, 'Holding the opening click must not close the browser')
tick(false, false)
cursor = Vector(190, 170)
tick(false, true)
assert(panel.button == 0 and panel.pointer.X == 190)
tick(false, false)
tick(true, false)
assert(not panel.opened and merchant.isBlocking(), 'Closing click must remain captured until release')
tick(false, false)
assert(not merchant.isBlocking())

cursor = Vector(224, 39)
buttons[1] = true
assert(merchant.isBlocking() and panel.opened, 'The stock Isaac shopkeeper must also open the recipe panel')
tick(false, false)
tick(true, false)
tick(false, false)

room.mirror, room.seed = true, 3
roomChanged()
viewportOrigin = Vector(-48, -20)
cursor = Vector(160, 30)
merchant.render()
assert(sprites[#sprites].path:find('shopkeeper_north', 1, true))
assert(sprites[#sprites].position.X == 160)
tick(true, false)
assert(panel.opened, 'Merchant click must include the viewport origin in a scaled mirror room')
tick(false, false)
cursor = Vector(190, 170)
tick(false, true)
assert(panel.pointer.X == 190 and panel.pointer.Y == 170, 'Recipe clicks must use the same render coordinates')
roomChanged()
assert(not panel.opened)
room.shop = false
tick(false, false)
tick(true, false)
assert(not panel.opened and not merchant.isBlocking())
""")
print("Passed merchant placement, click ownership, mirroring and room lifecycle.")

lua = LuaRuntime()
lua.globals().sourceFiles = lua.table_from({
    file.stem: file.read_text(encoding="utf-8") for file in MOD.glob("*.lua")
})
prelude = mock_prelude().replace("include('main')", r"""
local baseGame = Game
local level = {GetCurrentRoomIndex=function() return 12 end, GetStartingRoomIndex=function() return 0 end}
function Game()
    local game = baseGame()
    function game:GetLevel() return level end
    return game
end
local actualInclude = include
local shop
local modDirectory = 'C:/Isaac/mods/renamed_samira_testroom'
XMLData = {GetCurrentMod = function() return {fulldirectory = modDirectory} end}
function include(name)
    local module = actualInclude(name)
    if name == 'samira_shop_crafting' then shop = module end
    if name == 'samira_inventory' then module.recipes = function() return {} end end
    return module
end
include('main')
""", 1)
lua.execute(prelude + r"""
function RNG()
    return {SetSeed=function() end, RandomInt=function() return 99 end}
end
local fixtureVector=getmetatable(Vector(0,0))
function fixtureVector:GetAngleDegrees() return math.deg(math.atan(self.Y,self.X)) end
function fixtureVector.__div(v,n) return Vector(v.X/n,v.Y/n) end
start()
function room:GetCenterPos() return Vector(200,120) end
function room:GetTopLeftPos() return Vector.Zero end
function room:GetSpawnSeed() return 2 end
function player:GetNumCoins() return 0 end
local renderedRecipes = false
Isaac.DrawLine = function() end
Isaac.RenderText = function() end
KColor = function(...) return {...} end
function Font(path)
    if path ~= modDirectory .. '/resources/font/samira_items_ru.fnt' then return nil, false end
    return {
        GetStringWidthUTF8 = function(_, label) return #label end,
        DrawStringScaledUTF8 = function(_, label)
            if label == 'Рецепты' then renderedRecipes = true end
        end,
    }, true
end
function Sprite() return nil, false end
roomKind, roomClear = RoomType.ROOM_SHOP, true
event('POST_NEW_ROOM')
local merchant = Vector(180,60)
renderOnly(nil, false, merchant)

console = true
renderOnly(nil, true, merchant)
console = false
renderOnly(nil, true, merchant)
assert(not shop.isOpen(), 'a press begun in ImGui opened the shop after ImGui closed')
renderOnly(nil, false, merchant)

-- The engine queries movement before simulation callbacks. A merchant press
-- must already be claimed at that point, even with a pending ground order.
tick(nil, true, Vector(360,160))
setInput(nil, true, merchant)
callAction('ACTION_RIGHT')
assert(not shop.isOpen(), 'a held ground press became a merchant click after moving the cursor')
tick()
assert(callAction('ACTION_RIGHT') > 0, 'ground RMB stopped issuing walk orders in the shop')
setInput(nil, true, merchant)
assert(callAction('ACTION_RIGHT') == 0 and shop.isOpen(),
    'native movement query before POST_UPDATE did not give the merchant the press')
tick(nil, true, merchant)
assert(shop.isOpen(), 'multiple callbacks interpreted a held opening click again')
tick(nil, false, merchant)
tick(nil, true, merchant)
assert(not shop.isOpen() and callAction('ACTION_RIGHT') == 0,
    'closing by RMB leaked movement on the same press')
tick(nil, false, merchant)

-- At high render rate the complete press can occur between simulation ticks.
renderOnly(nil, true, merchant)
assert(shop.isOpen() and renderedRecipes, 'render-side RMB missed the real crafting panel')
renderOnly(nil, false, merchant)
assert(shop.isOpen())
event('POST_NEW_ROOM')
assert(not shop.isOpen())

Isaac.GetPlayerTypeByName = function(name) return name == 'Yone' and 130 or 131 end
Isaac.GetTextWidth = function(label) return #label end
Isaac.RenderScaledText = function() end
function player:IsFlying() return false end
event('EXECUTE_CMD', 'samiratest', 'off')
for _, champion in ipairs({{130, 'Yone'}, {131, 'Miss Fortune'}}) do
    function player:GetPlayerType() return champion[1] end
    player.Position, player.Velocity = Vector(60,100), Vector.Zero
    event('POST_GAME_STARTED', false)
    event('POST_NEW_ROOM')
    tick()
    tick(nil, true, Vector(360,160))
    tick()
    assert(callAction('ACTION_RIGHT') > 0, champion[2] .. ' lost ground RMB in shops')
    setInput(nil, true, merchant)
    assert(callAction('ACTION_RIGHT') == 0 and shop.isOpen(),
        champion[2] .. ' movement query did not give the merchant first refusal')
    tick(nil, true, merchant)
    assert(shop.isOpen())
    event('PRE_GAME_EXIT')
    assert(not shop.isOpen())
end
""")
print("Passed all hero/merchant/crafting callback order and render-only RMB.")
