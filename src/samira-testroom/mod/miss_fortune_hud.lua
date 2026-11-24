local HUD = {}
local SharedHUD = include('yone_hud')
local abilities = {'q', 'w', 'e', 'r'}
local width, height, margin = 215, 39, 6
local inset, iconSize, iconStep = 99, 24, 28
local statWidth, statHeight = 27, 10
local statsLayout = {
    {'damage', '%.2f', 'Урон', 'Базовый урон попадания автоатакой.'},
    {'crit', '%.0f%%', 'Шанс критического удара', 'Вероятность нанести повышенный урон.'},
    {'attacks', '%.2f', 'Темп автоатак', 'Количество автоатак в секунду.'},
    {'haste', '%g', 'Ускорение умений', 'Сокращает время перезарядки умений.'},
    {'move', '%.2f', 'Скорость передвижения', 'Влияет на скорость движения по комнате.'},
    {'range', '%.0f', 'Дальность автоатак', 'Расстояние, на котором можно попасть автоатакой.'},
}
local warm, muted, light = {1, .83, .60, 1}, {.72, .75, .79, 1}, {1, .94, .84, 1}
local shadow = {.025, .033, .052, 1}
local icons, colors, tooltipFont
local metadata = XMLData and XMLData.GetCurrentMod and XMLData.GetCurrentMod()
local modDirectory = metadata and metadata.fulldirectory or 'mods/samira_testroom'

function HUD.bounds(requestedScale, backpack)
    local sw, sh = Isaac.GetScreenWidth(), Isaac.GetScreenHeight()
    local scale = math.min(requestedScale or 1, (sw - 2 * margin) / width, (sh - 10) / height)
    local x, bottom = (sw - width * scale) / 2, sh - 4
    if backpack then
        local beside = backpack.x + backpack.width + 7
        if beside + width * scale + margin <= sw then
            x = math.max(x, beside)
        else
            local header = 17 * backpack.scale
            bottom = backpack.y - header - 3
            scale = math.min(scale, (bottom - 3) / height)
            x = sw - width * scale - margin
        end
    end
    if scale <= 0 then return end
    local w, h = width * scale, height * scale
    x = math.floor(x)
    local y = math.floor(bottom - h)
    return {x=x, y=y, width=w, height=h, left=x, top=y, right=x+w, bottom=y+h, scale=scale}
end

local function setUp()
    if icons == nil then
        local sprite, loaded = Sprite('gfx/mf/hud_icons.anm2', true)
        icons = loaded and sprite or false
    end
    if colors then return end
    colors = {
        shell=KColor(.18, .20, .24, 1), panel=KColor(.054, .082, .13, .98),
        keyBackground=KColor(.033, .06, .096, .98), cell=KColor(.13, .15, .21, 1),
        gold=KColor(.65, .49, .31, 1), bright=KColor(.87, .69, .44, 1),
        glyph=KColor(.80, .67, .47, 1), dim=KColor(.34, .36, .42, 1),
        shade=KColor(.034, .040, .068, .59),
        hover=KColor(.17, .19, .26, 1), tooltip=KColor(.033, .06, .096, 1),
        tooltipText=KColor(1, .94, .84, 1),
    }
end

local function fill(x, y, w, h, color)
    if w <= 0 then return end
    Isaac.DrawLine(Vector(x, y + h / 2), Vector(x + w, y + h / 2), color, color, h)
end

local function label(value, x, y, size, color)
    Isaac.RenderScaledText(value, x, y, size, size, table.unpack(color))
end

local function center(value, x, y, size, color)
    local left = x - Isaac.GetTextWidth(value) * size / 2
    label(value, left + size, y + size, size, shadow)
    label(value, left, y, size, color)
end

local function art(name, x, y, size)
    if not icons then return end
    icons:SetFrame(name, 0)
    icons.Scale = Vector(size / 64, size / 64)
    icons:Render(Vector(x, y))
end

local function mousePosition()
    if not (Input and Input.GetMousePosition and Isaac.ScreenToWorld and Isaac.WorldToScreen) then return end
    return Isaac.WorldToScreen(Isaac.ScreenToWorld(Input.GetMousePosition(false)))
end

local function drawStats(x, y, s, stats, pointer)
    local hovered, anchor
    for i, stat in ipairs(statsLayout) do
        local value = stats and stats[stat[1]]
        if value ~= nil then
            if stat[1] == 'crit' then value = value * 100 end
            local col = x + (i - 1) % 2 * statWidth * s
            local row = y + math.floor((i - 1) / 2) * statHeight * s
            if pointer and pointer.X >= col and pointer.X < col + statWidth * s
                and pointer.Y >= row and pointer.Y < row + statHeight * s then
                fill(col, row, statWidth * s, statHeight * s, colors.hover)
                hovered, anchor = stat, col
            end
            SharedHUD.drawStatGlyph(stat[1], col, row + .9 * s, .77 * s, colors.glyph)
            local text = stat[2]:format(value)
            local size = math.min(.88, 18 / math.max(1, Isaac.GetTextWidth(text))) * s
            label(text, col + 8 * s, row, size, light)
        end
    end
    return hovered, anchor
end

local function drawTooltip(b, stat, anchor)
    if not stat or not Font then return end
    if tooltipFont == nil then
        local candidate, loaded = Font(modDirectory .. '/resources/font/samira_items_ru.fnt')
        if not loaded then candidate, loaded = Font('font/pftempestasevencondensed.fnt') end
        tooltipFont = loaded and candidate or false
    end
    if not tooltipFont then return end

    local sw, sh = Isaac.GetScreenWidth(), Isaac.GetScreenHeight()
    local title, definition = stat[3], stat[4]
    local textWidth = math.max(tooltipFont:GetStringWidthUTF8(title), tooltipFont:GetStringWidthUTF8(definition))
    local above, below = b.y - 6, sh - b.bottom - 6
    local s = math.min(math.max(.75, b.scale), (sw - 6) / (textWidth * .68 + 12))
    local showAbove = above >= 34 * s or above >= below
    s = math.min(s, (showAbove and above or below) / 34)
    if s <= 0 then return end

    local w, h = (textWidth * .68 + 12) * s, 34 * s
    local x = math.max(3, math.min(anchor, sw - w - 3))
    local y = showAbove and b.y - h - 3 or b.bottom + 3
    fill(x, y, w, h, colors.gold)
    fill(x + s, y + s, w - 2 * s, h - 2 * s, colors.tooltip)
    tooltipFont:DrawStringScaledUTF8(title, x + 6 * s, y + 4 * s, .68 * s, .68 * s, colors.bright, 0, false)
    tooltipFont:DrawStringScaledUTF8(definition, x + 6 * s, y + 18 * s, .68 * s, .68 * s, colors.tooltipText, 0, false)
end

local function drawAbilities(b, combat, clock)
    local s, y = b.scale, b.y + 4 * b.scale
    local size = iconSize * s
    for i, key in ipairs(abilities) do
        local x = b.x + (inset + (i - 1) * iconStep) * s
        local remaining = (combat.ready[key] or 0) - clock
        local strut = key == 'w' and (combat.wUntil or clock) - clock or 0
        local border = remaining > 0 and strut <= 0 and colors.dim or colors.bright
        fill(x - s, y - s, size + 2 * s, size + 2 * s, border)
        fill(x, y, size, size, colors.cell)
        art(key:upper(), x, y, size)
        if remaining > 0 then
            fill(x, y, size, size, colors.shade)
            center(('%ds'):format(math.ceil(remaining / 30)), x + size / 2, y + 7 * s, 1.05 * s, light)
        end
        fill(x, y + size, size, 7 * s, colors.keyBackground)
        local caption = strut > 0 and ('W %.1fs'):format(math.ceil(strut / 3) / 10) or key:upper()
        local scale = math.min(.91, (iconSize - 2) / math.max(1, Isaac.GetTextWidth(caption))) * s
        center(caption, x + size / 2, y + size, scale, remaining > 0 and strut <= 0 and muted or warm)
    end
end

local function drawRune(x, y, s, rules, progress, clock)
    if not rules or not progress then return end
    local status = rules.runeStatus(progress, clock)
    if not status then return end
    local size = 14 * s
    local cooling = not status.limit and not status.active and status.remaining > 0
    fill(x - s, y - s, size + 2 * s, size + 2 * s, cooling and colors.dim or colors.gold)
    fill(x, y, size, size, colors.keyBackground)
    art(progress.rune, x, y, size)
    if cooling then fill(x, y, size, size, colors.shade) end
    local caption
    if status.limit then
        if status.stacks > 0 then caption = tostring(status.stacks) end
    elseif status.remaining > 0 then
        caption = ('%ds'):format(math.ceil(status.remaining / 30))
    end
    if caption then
        local maxWidth = size - 2 * s
        local scale = math.min(.77 * s, maxWidth / math.max(1, Isaac.GetTextWidth(caption)))
        local top = y + size - 7 * s
        if not cooling then fill(x, top, size, 7 * s, colors.shade) end
        center(caption, x + size / 2, cooling and y + 3 * s or top, scale, light)
    end
end

function HUD.render(b, combat, clock, stats, runeRules, runeProgress)
    if not b or not Isaac.DrawLine or not KColor then return end
    setUp()
    local x, y, s = b.x, b.y, b.scale
    fill(x + 2 * s, y, b.width - 4 * s, b.height, colors.shell)
    fill(x, y + 2 * s, b.width, b.height - 4 * s, colors.shell)
    fill(x + 2 * s, y + s, b.width - 4 * s, b.height - 2 * s, colors.panel)
    fill(x + 4 * s, y, b.width - 8 * s, s, colors.gold)
    art('Portrait', x + 3 * s, y + 1.5 * s, 36 * s)
    drawRune(x + 25 * s, y + 23 * s, s, runeRules, runeProgress, clock)
    local hovered, anchor = drawStats(x + 42 * s, y + 6 * s, s, stats, mousePosition())
    drawAbilities(b, combat, clock)
    drawTooltip(b, hovered, anchor)
end

return HUD
