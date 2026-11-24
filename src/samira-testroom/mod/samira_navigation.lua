-- The room graph supplies a corridor. Isaac still owns speed and collision.
local Navigation = {}
local offsets = {{1,0},{0,1},{-1,0},{0,-1}}

function Navigation.screenAxes()
    return (Isaac.WorldToScreen(Vector(1000, 1000)) - Isaac.WorldToScreen(Vector.Zero)) * .001
end

function Navigation.worldCursor(room)
    -- Let Isaac account for both the viewport origin and its axis scales.
    local cursor = Isaac.ScreenToWorld(Input.GetMousePosition(false))
    if not room:IsMirrorWorld() then return cursor end
    local screen = Isaac.WorldToScreen(cursor)
    screen.X = Isaac.GetScreenWidth() - screen.X
    if Isaac.RenderToWorld then return Isaac.RenderToWorld(screen) end
    local delta, axis = screen - Isaac.WorldToScreen(Vector.Zero), Navigation.screenAxes()
    return Vector(delta.X / axis.X, delta.Y / axis.Y)
end

function Navigation.clearPoint(room, player, point)
    local radius = math.min(14, math.max(6, player.Size * .6))
    if not room:IsPositionInRoom(point, radius) then return false end
    for _, offset in ipairs({Vector.Zero, Vector(radius, 0), Vector(-radius, 0),
        Vector(0, radius), Vector(0, -radius)}) do
        local cell = room:GetGridCollision(room:GetGridIndex(point + offset))
        if cell ~= GridCollisionClass.COLLISION_NONE
            and (not player:IsFlying() or cell >= GridCollisionClass.COLLISION_WALL) then return false end
    end
    return true
end

function Navigation.safeDestination(room, player, start, goal)
    local delta, lastSafe = goal - start, start
    local steps = math.max(1, math.ceil(delta:Length() / 4))
    for step = 1, steps do
        local nextPosition = start + delta * (step / steps)
        if not Navigation.clearPoint(room, player, nextPosition) then break end
        lastSafe = nextPosition
    end
    return lastSafe
end

function Navigation.clearSegment(room, player, start, goal)
    return Navigation.safeDestination(room, player, start, goal):Distance(goal) < .5
end

local function doorNormal(slot)
    return Vector(-1, 0):Rotated((slot % 4) * 90)
end

function Navigation.doorAt(room, destination)
    local chosen, best
    for slot = 0, 7 do
        local door = room:GetDoor(slot)
        if door then
            local normal = doorNormal(slot)
            local delta = destination - door.Position
            local along = math.abs(delta:Dot(normal))
            local across = math.abs(delta:Dot(normal:Rotated(90)))
            if along <= 56 and across <= 28 then
                local score = along + across * 2
                if not best or score < best then
                    chosen, best = {door = door, slot = slot, normal = normal}, score
                end
            end
        end
    end
    return chosen
end

function Navigation.doorHeading(room, position, doorway)
    -- A receiving doorway can be outside the pathfinding grid, including
    -- when the destination room closes the door before the player walks in.
    for slot = 0, 7 do
        local door = room:GetDoor(slot)
        if door and (not doorway or doorway.slot ~= slot) then
            local normal = doorNormal(slot)
            local tangent = normal:Rotated(90)
            local delta = position - door.Position
            local along, across = delta:Dot(normal), delta:Dot(tangent)
            if along >= -24 and along <= 60 and math.abs(across) <= 26 then
                return (normal * -1 - tangent * (across / 32)):Normalized()
            end
        end
    end
    if doorway then
        local door, normal = doorway.door, doorway.normal
        local tangent = normal:Rotated(90)
        local delta = position - door.Position
        local along, across = delta:Dot(normal), delta:Dot(tangent)
        if along >= -46 and along <= 60 and math.abs(across) <= 18 then
            -- Isaac handles unlocking, damage and crossing the threshold.
            return (normal - tangent * (across / 24)):Normalized()
        end
        return nil, door.Position - normal * 40
    end
end

local function build(room, p, goal, destination, clearPoint, clearSegment, canAttack)
    local width, size = room:GetGridWidth(), room:GetGridSize()
    local start = room:GetGridIndex(p.Position)
    if start < 0 or start >= size or not room:IsPositionInRoom(p.Position, 0) then return {} end
    local queue, previous = {start}, {[start] = start}
    local head, best, nearest = 1, start, p.Position:Distance(destination)
    while head <= #queue do
        local index = queue[head]
        local center = room:GetGridPosition(index)
        head = head + 1
        if index ~= start and canAttack and canAttack(center) then best = index; break end
        local distance = center:Distance(destination)
        if distance < nearest then best, nearest = index, distance end
        if index == goal then best = index; break end
        for _, offset in ipairs(offsets) do
            local x = index % width + offset[1]
            local nextIndex = index + offset[1] + offset[2] * width
            if x >= 0 and x < width and nextIndex >= 0 and nextIndex < size and not previous[nextIndex] then
                local point = room:GetGridPosition(nextIndex)
                if clearPoint(room, p, point) then
                    previous[nextIndex] = index
                    queue[#queue + 1] = nextIndex
                end
            end
        end
    end
    -- Store from the end backwards so advancing only pops the last entry.
    local points = {}
    while best ~= start do
        points[#points + 1] = room:GetGridPosition(best)
        best = previous[best]
    end
    -- At an off-centre start a line to the next cell can graze a corner.
    local center = room:GetGridPosition(start)
    if #points > 0 and not clearSegment(room, p, p.Position, points[#points])
        and clearSegment(room, p, p.Position, center) then points[#points + 1] = center end
    return points
end

function Navigation.waypoint(state, room, p, destination, clock, clearPoint, clearSegment, canAttack)
    local goal = room:GetGridIndex(room:GetClampedPosition(destination, 0))
    local path = state.path
    if not path or path.goal ~= goal or path.fly ~= p.CanFly or clock >= path.sightAt then
        if clearSegment(room, p, p.Position, destination) then
            state.path = nil
            return destination, true
        end
        if path then path.sightAt = clock + 5 end
    end
    if not path or path.goal ~= goal or path.fly ~= p.CanFly or clock >= path.retryAt then
        path = {points = build(room, p, goal, destination, clearPoint, clearSegment, canAttack),
            goal = goal, fly = p.CanFly, sightAt = clock + 5, retryAt = math.huge}
        state.path = path
    end
    local points = path.points
    while #points > 0 and p.Position:Distance(points[#points]) <= 4 do points[#points] = nil end
    if #points == 0 then
        -- Moving enemies and breakable barriers can open a new firing lane.
        path.retryAt = math.min(path.retryAt, clock + 10)
        return nil, true
    end
    -- Take the furthest visible bend without cutting across solid corners.
    if not path.smoothAt or clock >= path.smoothAt then
        for i = math.max(1, #points - 6), #points - 1 do
            if clearSegment(room, p, p.Position, points[i]) then
                for j = #points, i + 1, -1 do points[j] = nil end
                break
            end
        end
        path.smoothAt = clock + 4
    end
    local nextPoint = points[#points]
    if not clearSegment(room, p, p.Position, nextPoint) then
        state.path = nil
        return nil, false
    end
    return nextPoint, #points == 1
end

return Navigation
