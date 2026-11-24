local Shopkeeper = {}
local browser, game, owner, available
local keeper, icon
local anchor, roomSeed
local heldRight, heldLeft, captured = false, false, false
local modelScale = .72

local function screen(room, point)
    local result = Isaac.WorldToScreen(point)
    if room:IsMirrorWorld() then result.X = Isaac.GetScreenWidth() - result.X end
    return result
end

local function mousePosition()
    -- Keep the viewport origin when converting the cursor from client pixels.
    return Isaac.WorldToScreen(Isaac.ScreenToWorld(Input.GetMousePosition(false)))
end

local function shopRoom()
    if not Isaac.IsInGame() then return end
    local room = game:GetRoom()
    if room:GetType() == RoomType.ROOM_SHOP then return room end
end

local function canShop(room, player)
    return room and room:IsClear() and player and available(player)
end

local function traceClick(result, pointer, position)
    if not Isaac.DebugString then return end
    local coordinates = pointer and string.format(' cursor=(%.1f,%.1f) vendor=(%.1f,%.1f)',
        pointer.X, pointer.Y, position.X, position.Y) or ''
    Isaac.DebugString('[Soul Fighter shop] RMB ' .. result .. coordinates)
end

local function reservePositions(room, player)
    local occupied = {player.Position}
    for _, entity in ipairs(Isaac.GetRoomEntities()) do
        if entity.Type == EntityType.ENTITY_PICKUP or entity.Type == EntityType.ENTITY_SHOPKEEPER then
            occupied[#occupied + 1] = entity.Position
        end
    end
    for slot = 0, 7 do
        local door = room:GetDoor(slot)
        if door then occupied[#occupied + 1] = door.Position end
    end
    return occupied
end

local function availableSpace(point, occupied)
    for _, position in ipairs(occupied) do
        if point:Distance(position) < 35 then return false end
    end
    return true
end

local function chooseAnchor(room, player)
    local center, top = room:GetCenterPos(), room:GetTopLeftPos()
    local goal = Vector(center.X, top.Y + 44)
    local occupied = reservePositions(room, player)
    local found, minimum
    for i = 0, room:GetGridSize() - 1 do
        local point = room:GetGridPosition(i)
        if room:IsPositionInRoom(point, 27) and room:GetGridCollision(i) == GridCollisionClass.COLLISION_NONE
            and not room:GetGridEntity(i) and availableSpace(point, occupied) then
            local distance = point:Distance(goal)
            if minimum == nil or distance < minimum then found, minimum = point, distance end
        end
    end
    return found or room:GetClampedPosition(goal, 24)
end

local function sprite(path, animation, scale)
    local value, loaded = Sprite(path, true)
    if not loaded then return false end
    value.Scale = Vector(scale, scale)
    value:Play(animation, true)
    return value
end

local function hit(pointer, position, halfWidth, height)
    local delta = pointer - position
    return math.abs(delta.X) <= halfWidth and delta.Y >= -height and delta.Y <= 7
end

local function hoveredVendor(room, pointer, position)
    if hit(pointer, position, 48 * modelScale + 4, 92 * modelScale + 4) then return position end
    for _, entity in ipairs(Isaac.GetRoomEntities()) do
        if entity.Type == EntityType.ENTITY_SHOPKEEPER then
            local native = screen(room, entity.Position)
            if hit(pointer, native, 22, 34) then return native end
        end
    end
end

local function resetRoom()
    if browser and browser.isOpen() then browser.close() end
    anchor, roomSeed, keeper = nil, nil, nil
end

local function place(room, player)
    if roomSeed ~= room:GetSpawnSeed() then resetRoom() end
    if anchor then return end
    roomSeed = room:GetSpawnSeed()
    anchor = chooseAnchor(room, player)
    local side = roomSeed % 2 == 0 and 'south' or 'north'
    keeper = sprite('gfx/league_shop/shopkeeper_' .. side .. '.anm2', 'Idle', modelScale)
    if icon == nil then icon = sprite('gfx/league_shop/shop_ui.anm2', 'Shop', .7) end
end

local function sampleInput()
    local right, left = Input.IsMouseBtnPressed(1), Input.IsMouseBtnPressed(0)
    local rightClick, leftClick = right and not heldRight, left and not heldLeft
    heldRight, heldLeft = right, left
    if not right and not left then captured = false end
    if not rightClick and not leftClick then return end

    local room, player = shopRoom(), owner()
    if not canShop(room, player) then
        if room and rightClick then
            traceClick(not room:IsClear() and 'room not clear' or 'player unavailable')
        end
        return
    end
    place(room, player)

    local pointer = mousePosition()
    if browser.isOpen() then
        captured = true
        browser.onMousePressed(pointer, rightClick and 1 or 0)
    elseif rightClick then
        local position = screen(room, anchor)
        local hovered = hoveredVendor(room, pointer, position)
        if hovered then
            captured = true
            local opened = browser.open(player)
            traceClick(opened and 'opened' or 'panel unavailable', pointer, hovered)
        else
            traceClick('missed', pointer, position)
        end
    end
end

function Shopkeeper.isOpen()
    return browser ~= nil and browser.isOpen()
end

function Shopkeeper.isBlocking()
    if not browser then return false end
    -- Isaac can ask for a movement action before MC_POST_UPDATE. Let the
    -- merchant claim the current edge before any gameplay caller reads it.
    sampleInput()
    return Shopkeeper.isOpen() or captured
end

local function update()
    sampleInput()
    local room, player = shopRoom(), owner()
    if not canShop(room, player) then
        if browser.isOpen() then browser.close() end
        return
    end
    if keeper then keeper:Update() end
end

function Shopkeeper.render()
    local room, player = shopRoom(), owner()
    if not canShop(room, player) then return end
    place(room, player)
    local position = screen(room, anchor)
    local pointer = mousePosition()
    if keeper then keeper:Render(position)
    else Isaac.RenderText('Merchant', position.X - 18, position.Y - 18, 1, .82, .47, 1) end
    if browser.isOpen() then
        browser.render(pointer)
    else
        local hovered = hoveredVendor(room, pointer, position)
        if not hovered then return end
        if icon then icon:Render(hovered + Vector(-34, -60)) end
        Isaac.RenderText('RMB - Recipes', hovered.X - 22, hovered.Y - 64, 1, .85, .5, 1)
    end
end

function Shopkeeper.init(mod, currentGame, player, canInteract, panel)
    game, owner, available, browser = currentGame, player, canInteract, panel
    mod:AddPriorityCallback(ModCallbacks.MC_POST_UPDATE, CallbackPriority.EARLY, update)
    mod:AddCallback(ModCallbacks.MC_POST_NEW_ROOM, resetRoom)
    mod:AddCallback(ModCallbacks.MC_PRE_GAME_EXIT, resetRoom)
end

return Shopkeeper
