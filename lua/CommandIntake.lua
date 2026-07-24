-- CommandIntake.lua — execute one agent command and report the result.
-- The Python driver calls Bridge_Execute('<json>') over the tuner socket
-- (queued-file polling is done on the Python side; io is nil in this sandbox).
-- Result is emitted as "BRIDGE_RESULT:<json>".

local function result(id, ok, detail)
  print("BRIDGE_RESULT:" .. BridgeJSON.encode({ id = id, ok = ok, detail = detail }))
end

local handlers = {}

handlers.move_unit = function(cmd)
  local pid = Game.GetLocalPlayer()
  local unit = UnitManager.GetUnit(pid, cmd.unit_id)
  if not unit then return false, "no unit " .. tostring(cmd.unit_id) end
  local tParameters = {}
  tParameters[UnitOperationTypes.PARAM_X] = cmd.x
  tParameters[UnitOperationTypes.PARAM_Y] = cmd.y
  if UnitManager.CanStartOperation(unit, UnitOperationTypes.MOVE_TO, nil, tParameters) then
    UnitManager.RequestOperation(unit, UnitOperationTypes.MOVE_TO, tParameters)
    return true, "moving to " .. cmd.x .. "," .. cmd.y
  end
  return false, "MOVE_TO not startable"
end

handlers.set_production = function(cmd)
  local pid = Game.GetLocalPlayer()
  local city = CityManager.GetCity(pid, cmd.city_id)
  if not city then return false, "no city " .. tostring(cmd.city_id) end
  local row = GameInfo.Units[cmd.item] or GameInfo.Buildings[cmd.item] or GameInfo.Districts[cmd.item] or GameInfo.Projects[cmd.item]
  if not row then return false, "unknown item " .. tostring(cmd.item) end
  local tParameters = {}
  if GameInfo.Units[cmd.item] then
    tParameters[CityOperationTypes.PARAM_UNIT_TYPE] = row.Hash
  elseif GameInfo.Buildings[cmd.item] then
    tParameters[CityOperationTypes.PARAM_BUILDING_TYPE] = row.Hash
  elseif GameInfo.Districts[cmd.item] then
    tParameters[CityOperationTypes.PARAM_DISTRICT_TYPE] = row.Hash
  else
    tParameters[CityOperationTypes.PARAM_PROJECT_TYPE] = row.Hash
  end
  tParameters[CityOperationTypes.PARAM_INSERT_MODE] = CityOperationTypes.VALUE_EXCLUSIVE
  -- gate like the other handlers: without this, un-buildable items (district
  -- already placed, missing prereq) ack ok=true and silently do nothing.
  if not CityManager.CanStartOperation(city, CityOperationTypes.BUILD, tParameters) then
    return false, "BUILD not startable: " .. cmd.item
  end
  CityManager.RequestOperation(city, CityOperationTypes.BUILD, tParameters)
  return true, "production -> " .. cmd.item
end

handlers.found_city = function(cmd)
  local pid = Game.GetLocalPlayer()
  local unit = UnitManager.GetUnit(pid, cmd.unit_id)
  if not unit then return false, "no unit " .. tostring(cmd.unit_id) end
  -- FOUND_CITY founds at the settler's CURRENT tile; position it with move_unit first.
  if UnitManager.CanStartOperation(unit, UnitOperationTypes.FOUND_CITY, nil, true) then
    UnitManager.RequestOperation(unit, UnitOperationTypes.FOUND_CITY)
    return true, "founding city at " .. unit:GetX() .. "," .. unit:GetY()
  end
  return false, "FOUND_CITY not startable (not a settler, or invalid tile)"
end

handlers.attack = function(cmd)
  -- Melee: MOVE_TO onto the enemy tile (engine resolves the attack).
  -- Ranged: RANGE_ATTACK with target x,y (pass {"ranged":true}).
  local pid = Game.GetLocalPlayer()
  local unit = UnitManager.GetUnit(pid, cmd.unit_id)
  if not unit then return false, "no unit " .. tostring(cmd.unit_id) end
  local tp = {}
  tp[UnitOperationTypes.PARAM_X] = cmd.x
  tp[UnitOperationTypes.PARAM_Y] = cmd.y
  local op = UnitOperationTypes.MOVE_TO
  if cmd.ranged then
    op = UnitOperationTypes.RANGE_ATTACK
  else
    -- melee = MOVE_TO onto the enemy tile WITH the ATTACK modifier;
    -- without it the move is silently ignored (verified in-engine).
    tp[UnitOperationTypes.PARAM_MODIFIERS] = UnitOperationMoveModifiers.ATTACK
  end
  if UnitManager.CanStartOperation(unit, op, nil, tp) then
    UnitManager.RequestOperation(unit, op, tp)
    return true, (cmd.ranged and "range attack " or "melee attack ") .. cmd.x .. "," .. cmd.y
  end
  return false, "attack not startable at " .. cmd.x .. "," .. cmd.y
end

-- Turn-blocker: idle units are cleared by Bridge_FinishIdle(pid), which the
-- driver injects into the GameCore_Tuner context (UnitManager.FinishMoves is
-- nil here in the UI context). The driver runs it before every end_turn.
-- Verified 2026-07-16: 6 idle units cleared, turn advanced 23->24.

-- Diplomacy modals (AI meets/denounces mid-round) halt the ENTIRE AI turn cycle
-- until dismissed — verified 2026-07-16 (10-minute stall). Events aren't
-- enumerable in this sandbox, so the driver polls this instead.
function Bridge_ClearDiplo()
  local closed = 0
  for id = 0, 300 do
    if DiplomacyManager.IsSessionIDOpen(id) then
      DiplomacyManager.CloseSession(id)
      closed = closed + 1
    end
  end
  if closed > 0 then
    print("BRIDGE_DIPLO_CLEARED:" .. closed)
  end
  return closed
end

handlers.clear_diplo = function(cmd)
  return true, "closed " .. Bridge_ClearDiplo() .. " diplo sessions"
end

handlers.purchase = function(cmd)
  local pid = Game.GetLocalPlayer()
  local city = CityManager.GetCity(pid, cmd.city_id)
  if not city then return false, "no city " .. tostring(cmd.city_id) end
  local tp = {}
  local u = GameInfo.Units[cmd.item]
  local b = GameInfo.Buildings[cmd.item]
  if u then
    tp[CityCommandTypes.PARAM_UNIT_TYPE] = u.Hash
  elseif b then
    tp[CityCommandTypes.PARAM_BUILDING_TYPE] = b.Hash
  else
    return false, "unknown item " .. tostring(cmd.item)
  end
  if u then
    -- base-game ProductionPanel always sets a formation for unit purchases;
    -- without it CanStartCommand returns false.
    tp[CityCommandTypes.PARAM_MILITARY_FORMATION_TYPE] = MilitaryFormationTypes.STANDARD_MILITARY_FORMATION
  end
  tp[CityCommandTypes.PARAM_YIELD_TYPE] = GameInfo.Yields["YIELD_GOLD"].Index
  -- FAILURE_REASONS is the gate, NOT the boolean. Verified in-engine 2026-07-19:
  -- CanStartCommand with bTestOnly=true is PERMISSIVE — it returned can=true for a
  -- settler in a pop-1 city and for units blocked by tile stacking, both of which
  -- then silently no-op (ack ok=true, gold unchanged, no unit created). It also
  -- returns can=true for a city that already purchased this turn. The bTestOnly=false
  -- form carries the real validation, and it caught every one of those cases.
  -- The 2026-07-17 version trusted the boolean and only asked for reasons when it
  -- was false — which never happened, so the reasons branch was dead code and the
  -- action reported success while doing nothing.
  local _, results = CityManager.CanStartCommand(city, CityCommandTypes.PURCHASE, false, tp, true)
  local raw = results and results[CityCommandResults.FAILURE_REASONS]
  if raw and #raw > 0 then
    local reasons = {}
    for _, r in ipairs(raw) do
      table.insert(reasons, Locale.Lookup(r))
    end
    return false, "cannot purchase " .. cmd.item .. ": " .. table.concat(reasons, "; ")
  end
  CityManager.RequestCommand(city, CityCommandTypes.PURCHASE, tp)
  return true, "purchased " .. cmd.item
end

handlers.end_turn = function(cmd)
  Bridge_ClearDiplo()
  UI.RequestAction(ActionTypes.ACTION_ENDTURN)
  return true, "end turn requested"
end

handlers.set_research = function(cmd)
  local pid = Game.GetLocalPlayer()
  local row = GameInfo.Technologies[cmd.tech]
  if not row then return false, "unknown tech " .. tostring(cmd.tech) end
  local tp = {}
  tp[PlayerOperations.PARAM_TECH_TYPE] = row.Hash
  tp[PlayerOperations.PARAM_INSERT_MODE] = PlayerOperations.VALUE_EXCLUSIVE
  UI.RequestPlayerOperation(pid, PlayerOperations.RESEARCH, tp)
  return true, "research -> " .. cmd.tech
end

handlers.set_civic = function(cmd)
  local pid = Game.GetLocalPlayer()
  local row = GameInfo.Civics[cmd.civic]
  if not row then return false, "unknown civic " .. tostring(cmd.civic) end
  local tp = {}
  tp[PlayerOperations.PARAM_CIVIC_TYPE] = row.Hash
  tp[PlayerOperations.PARAM_INSERT_MODE] = PlayerOperations.VALUE_EXCLUSIVE
  UI.RequestPlayerOperation(pid, PlayerOperations.PROGRESS_CIVIC, tp)
  return true, "civic -> " .. cmd.civic
end

function Bridge_Execute(jsonStr)
  local cmd = BridgeJSON.decode(jsonStr)
  if not cmd or not cmd.action then
    result(cmd and cmd.id or -1, false, "bad command json")
    return
  end
  local h = handlers[cmd.action]
  if not h then
    result(cmd.id or -1, false, "unknown action " .. tostring(cmd.action))
    return
  end
  local ok, res, detail = pcall(h, cmd)
  if ok then
    result(cmd.id or -1, res, detail)
  else
    result(cmd.id or -1, false, "lua error: " .. tostring(res))
  end
end

print("BRIDGE_INTAKE_READY")
