local ShopCrafting = {}
local Crafting = include('samira_crafting_ui')
local Description = include('samira_item_description')
local ItemIcons = include('samira_item_icons')

local items = {}
for _, row in ipairs(include('samira_items_data')) do items[row.riotId] = row end

local panelWidth, panelHeight, pageSize = 358, 184, 7
local inventory, owner, font, colors, artwork
local page, selected, feedback, feedbackOK
local metadata = XMLData and XMLData.GetCurrentMod and XMLData.GetCurrentMod()
local modDirectory = metadata and metadata.fulldirectory or 'mods/samira_testroom'

local function setup()
    if font then return true end
    -- Font:Load does not search the mod's resources like Sprite:Load does.
    local candidate, loaded = Font(modDirectory .. '/resources/font/samira_items_ru.fnt')
    if not loaded then candidate, loaded = Font('font/pftempestasevencondensed.fnt') end
    if not loaded then return false end
    font = candidate
    colors = {
        paper = KColor(.026, .058, .085, 1), rim = KColor(.61, .48, .29, 1),
        row = KColor(.052, .105, .14, 1), hover = KColor(.10, .22, .26, 1),
        gold = KColor(.94, .78, .48, 1), white = KColor(.94, .91, .83, 1),
        muted = KColor(.65, .70, .72, 1), ready = KColor(.53, .88, .79, 1),
    }
    local sprite, hasArtwork = Sprite('gfx/league_shop/shop_ui.anm2', true)
    if hasArtwork then artwork = sprite end
    return true
end

local function inside(pointer, rect)
    return pointer.X >= rect.x and pointer.X < rect.x + rect.width
        and pointer.Y >= rect.y and pointer.Y < rect.y + rect.height
end

local function fill(rect, color)
    local mid = rect.y + rect.height / 2
    Isaac.DrawLine(Vector(rect.x, mid), Vector(rect.x + rect.width, mid), color, color, rect.height)
end

local function text(label, rect, scale, color)
    local s = math.min(scale, rect.width / math.max(1, font:GetStringWidthUTF8(label)))
    font:DrawStringScaledUTF8(label, rect.x, rect.y, s, s, color, 0, false)
end

local function button(rect, label, scale, pointer, enabled)
    fill(rect, enabled and inside(pointer, rect) and colors.hover or colors.row)
    text(label, {x = rect.x + 4 * scale, y = rect.y + 2 * scale, width = rect.width - 8 * scale},
        .76 * scale, enabled and colors.gold or colors.muted)
end

local function drawArt(animation, rect, width, height)
    if not artwork then return end
    artwork:SetFrame(animation, 0)
    artwork.Scale = Vector(rect.width / width, rect.height / height)
    artwork:Render(Vector(rect.x + rect.width / 2, rect.y + rect.height / 2))
end

local function icon(item, rect, s)
    if item and item.icon then
        ItemIcons.render(item.icon, Vector(rect.x + rect.width / 2, rect.y + rect.height / 2), s)
    end
end

local function pageData()
    local recipes = {}
    for _, recipe in ipairs(inventory.recipes(owner)) do
        if not recipe.row.component then recipes[#recipes + 1] = recipe end
    end
    local pages = math.max(1, math.ceil(#recipes / pageSize))
    page = math.min(page, pages)
    local visible, active = {}, nil
    local first = (page - 1) * pageSize
    for i = 1, pageSize do
        local recipe = recipes[first + i]
        if not recipe then break end
        visible[i] = recipe
        if recipe.row.riotId == selected then active = recipe end
    end
    active = active or visible[1]
    selected = active and active.row.riotId
    return visible, active, pages
end

local function geometry()
    local w, h = Isaac.GetScreenWidth(), Isaac.GetScreenHeight()
    local s = math.min(1.2, (w - 12) / panelWidth, (h - 44) / panelHeight)
    if s <= 0 then return end
    local x, y = (w - panelWidth * s) / 2, (h - panelHeight * s) / 2 - 8
    local function rect(left, top, width, height)
        return {x = x + left * s, y = y + top * s, width = width * s, height = height * s}
    end
    return {
        s = s, rect = rect,
        previous = rect(9, 160, 20, 15), next = rect(99, 160, 20, 15),
        close = rect(331, 8, 17, 15), craft = rect(135, 160, 58, 15),
        row = function(index) return rect(9, 27 + (index - 1) * 19, 110, 17) end,
    }
end

local function canCraft(recipe, coins)
    return #recipe.missing == 0 and coins >= recipe.combinePrice
end

function ShopCrafting.init(itemsInventory)
    inventory = itemsInventory
    ShopCrafting.close()
end

function ShopCrafting.open(player)
    if not inventory or not player or not setup() then return false end
    owner, page, selected, feedback = player, 1, nil, nil
    return true
end

function ShopCrafting.isOpen()
    return owner ~= nil
end

function ShopCrafting.close()
    owner, selected, feedback = nil, nil, nil
end

function ShopCrafting.onMousePressed(pointer, mouseButton)
    if not owner then return false end
    if mouseButton == 1 then
        ShopCrafting.close()
        return true
    end
    if mouseButton ~= 0 then return false end
    local view = geometry()
    if not view then return true end
    local visible, active, pages = pageData()
    if inside(pointer, view.close) then
        ShopCrafting.close()
    elseif page > 1 and inside(pointer, view.previous) then
        page, selected, feedback = page - 1, nil, nil
    elseif page < pages and inside(pointer, view.next) then
        page, selected, feedback = page + 1, nil, nil
    elseif active and inside(pointer, view.craft) and canCraft(active, owner:GetNumCoins()) then
        local ok, reason = inventory.craft(owner, selected)
        feedback, feedbackOK = Crafting.result(selected, ok, reason), ok
    else
        for i, recipe in ipairs(visible) do
            if inside(pointer, view.row(i)) then
                selected, feedback = recipe.row.riotId, nil
                break
            end
        end
    end
    return true
end

local function markMissing(recipe)
    -- Match missing copies from the end so repeated ingredients show owned copies first.
    local missing, marks = {}, {}
    for _, id in ipairs(recipe.missing) do missing[id] = (missing[id] or 0) + 1 end
    for i = #recipe.row.components, 1, -1 do
        local id = recipe.row.components[i]
        local count = missing[id] or 0
        if count > 0 then marks[i], missing[id] = true, count - 1 end
    end
    return marks
end

function ShopCrafting.render(pointer)
    if not owner then return end
    local view = geometry()
    if not view then return end
    local rect, s = view.rect, view.s
    local function label(value, x, y, width, color, scale)
        text(value, rect(x, y, width, 0), (scale or .75) * s, color or colors.white)
    end

    local visible, active, pages = pageData()
    local coins = owner:GetNumCoins()
    if artwork then
        drawArt('Panel', rect(0, 0, panelWidth, panelHeight), 320, 252)
    else
        fill(rect(0, 0, panelWidth, panelHeight), colors.rim)
        fill(rect(1, 1, panelWidth - 2, panelHeight - 2), colors.paper)
    end
    drawArt('Shop', rect(9, 8, 13, 13), 18, 18)
    label('Рецепты', 26, 8, 90, colors.gold, .86)
    drawArt('Coin', rect(266, 8, 12, 11), 16, 15)
    label(('Монеты %d'):format(coins), 280, 8, 48, colors.gold)
    button(view.close, 'X', s, pointer, true)

    for i, recipe in ipairs(visible) do
        local row = view.row(i)
        fill(row, (recipe == active or inside(pointer, row)) and colors.hover or colors.row)
        local y = 27 + (i - 1) * 19
        icon(recipe.row, rect(11, y + 1, 15, 15), .44 * s)
        label(recipe.row.name, 29, y + 3, 86, canCraft(recipe, coins) and colors.ready or colors.white)
    end
    button(view.previous, '<', s, pointer, page > 1)
    button(view.next, '>', s, pointer, page < pages)
    label(('%d / %d'):format(page, pages), 47, 162, 50, colors.muted)
    if not active then
        label('Нет доступных рецептов', 135, 30, 207)
        return
    end

    icon(active.row, rect(135, 26, 24, 24), .72 * s)
    label(active.row.name, 164, 28, 176, colors.gold, .90)
    label(('Доплата %d мон.'):format(active.combinePrice), 164, 40, 176, colors.muted)
    local stats, passive = Description.lines(font, active.row, 300)
    local y = 53
    local lineHeight = math.min(10, 48 / math.max(1, #stats + #passive))
    local detailScale = math.min(.70, lineHeight / 14)
    for _, line in ipairs(stats) do
        label(line, 135, y, 214, colors.ready, detailScale)
        y = y + lineHeight
    end
    for _, line in ipairs(passive) do
        label(line, 135, y, 214, colors.white, detailScale)
        y = y + lineHeight
    end

    local missing = markMissing(active)
    label('Компоненты', 135, 102, 105, colors.gold)
    for i, id in ipairs(active.row.components) do
        local item = items[id]
        y = 114 + (i - 1) * 13
        icon(item, rect(135, y, 12, 12), .35 * s)
        label(item and item.name or tostring(id), 150, y, 145, colors.white, .70)
        label(missing[i] and 'Нет' or 'Есть', 298, y, 48, missing[i] and colors.muted or colors.ready, .70)
    end

    button(view.craft, 'Собрать', s, pointer, canCraft(active, coins))
    if feedback then
        label(feedback, 200, 163, 146, feedbackOK and colors.ready or colors.gold)
    elseif #active.missing > 0 then
        label('Не хватает компонентов', 200, 163, 146, colors.muted)
    elseif coins < active.combinePrice then
        label('Не хватает монет', 200, 163, 146, colors.muted)
    end
end

return ShopCrafting
