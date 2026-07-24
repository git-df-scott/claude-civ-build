-- StateDump.lua — on local turn start, emit a compact JSON snapshot of game state.
-- Transport: print() to the tuner console as "BRIDGE_STATE:<json>"; the Python
-- daemon captures the line and writes state.json (io is nil in this sandbox).
-- Hook choice (verified in-engine 2026-07-16, turn 23->24): only
-- Events.LocalPlayerTurnBegin / LocalPlayerTurnEnd / PlayerTurnActivated fire;
-- TurnBegin/TurnEnd/RemotePlayerTurnBegin never did. We use LocalPlayerTurnBegin.

-- Tile scan around a settler for settle-site scoring. pcall'd by the caller:
-- if any API name is wrong in this sandbox, the dump degrades to no tiles
-- rather than dying. UNVERIFIED in-engine as of 2026-07-17.
local TILE_SCAN_RADIUS = 5
local function Bridge_ScanTiles(cx, cy)
  local tiles = {}
  local w, h = Map.GetGridSize()
  for dy = -TILE_SCAN_RADIUS, TILE_SCAN_RADIUS do
    for dx = -TILE_SCAN_RADIUS, TILE_SCAN_RADIUS do
      local x, y = (cx + dx) % w, cy + dy
      if y >= 0 and y < h then
        local plot = Map.GetPlot(x, y)
        if plot and not plot:IsWater() and not plot:IsImpassable() then
          tiles[#tiles + 1] = {
            x = x, y = y,
            food = plot:GetYield(YieldTypes.YIELD_FOOD),
            prod = plot:GetYield(YieldTypes.YIELD_PRODUCTION),
            water = plot:IsFreshWater(),
            river = plot:IsRiver(),
            owner = plot:GetOwner(),
          }
        end
      end
    end
  end
  return tiles
end

function Bridge_BuildState()
  local state = { turn = Game.GetCurrentGameTurn(), players = {} }
  for _, pid in ipairs(PlayerManager.GetAliveIDs()) do
    local player = Players[pid]
    if player and player:IsMajor() then
      local p = {
        id = pid,
        isLocal = (pid == Game.GetLocalPlayer()),
        gold = math.floor(player:GetTreasury():GetGoldBalance()),
        cities = {},
        units = {},
      }
      if p.isLocal then
        -- research/civic status + choosable options (for set_research/set_civic)
        local techs = player:GetTechs()
        local culture = player:GetCulture()
        local cur = techs:GetResearchingTech()
        p.research = { current = (cur >= 0 and GameInfo.Technologies[cur].TechnologyType or nil), options = {} }
        for row in GameInfo.Technologies() do
          if techs:CanResearch(row.Index) then
            p.research.options[#p.research.options + 1] = row.TechnologyType
          end
        end
        local curc = culture:GetProgressingCivic()
        p.civics = { current = (curc >= 0 and GameInfo.Civics[curc].CivicType or nil), options = {} }
        for row in GameInfo.Civics() do
          if culture:CanProgress(row.Index) then
            p.civics.options[#p.civics.options + 1] = row.CivicType
          end
        end
      end
      for _, city in player:GetCities():Members() do
        local bq = city:GetBuildQueue()
        local hash = bq:GetCurrentProductionTypeHash()
        local prod = nil
        if hash and hash ~= 0 then
          local entry = GameInfo.Units[hash] or GameInfo.Buildings[hash] or GameInfo.Districts[hash] or GameInfo.Projects[hash]
          prod = entry and entry.Name or tostring(hash)
        end
        p.cities[#p.cities + 1] = {
          id = city:GetID(),
          name = Locale.Lookup(city:GetName()),
          x = city:GetX(), y = city:GetY(),
          population = city:GetPopulation(),
          production = prod,
        }
      end
      for _, unit in player:GetUnits():Members() do
        local u = {
          id = unit:GetID(),
          type = GameInfo.Units[unit:GetType()].UnitType,
          x = unit:GetX(), y = unit:GetY(),
          moves = unit:GetMovesRemaining(),
          damage = unit:GetDamage(),
        }
        if p.isLocal and u.type == "UNIT_SETTLER" then
          local okScan, tiles = pcall(Bridge_ScanTiles, u.x, u.y)
          if okScan then u.tiles = tiles end
        end
        p.units[#p.units + 1] = u
      end
      state.players[#state.players + 1] = p
    end
  end
  return state
end

function Bridge_DumpState()
  local ok, err = pcall(function()
    print("BRIDGE_STATE:" .. BridgeJSON.encode(Bridge_BuildState()))
  end)
  if not ok then
    print("BRIDGE_ERROR:" .. tostring(err))
  end
end

Events.LocalPlayerTurnBegin.Add(Bridge_DumpState)
Events.LoadGameViewStateDone.Add(Bridge_DumpState) -- initial dump on save load

print("BRIDGE_STATEDUMP_READY")
