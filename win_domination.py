"""win_domination.py — play Scythia (Tomyris) to a DOMINATION victory.

=============================== THE PLAN ===============================
Setup: Settler difficulty, barbarians OFF, standard map (74x46), 5 rivals.

Why domination:
  * Scythia's "People of the Steppe" gives TWO units per light-cavalry or Saka
    train — a half-price army, which is the single biggest military multiplier
    available this early.
  * Tomyris "Killer of Cyrus": +5 CS attacking wounded units, and heals up to
    50 HP on a kill. An attacking stack sustains itself without retreating.
  * Engine-checked unit maths: UNIT_HORSEMAN = 36 CS / 4 moves at Horseback
    Riding. Everything else in the ancient era is Warrior 20, Archer 15/25,
    Spearman 25. A horseman doomstack is simply unanswerable at this era.
  * Settler difficulty gives the AI its weakest bonuses, and barbarians-off
    means zero production spent on defence — all of it goes into offence.

Phases:
  1. t1-25   Found capital immediately. Beeline TECH_ANIMAL_HUSBANDRY ->
             TECH_HORSEBACK_RIDING. Civics Code of Laws -> Craftsmanship ->
             Military Tradition. Expand to 3-4 cities. Scout to FIND rivals
             (can't conquer what we haven't met).
  2. t25-60  Mass Horsemen + Scythian Horse Archers. Policy MANEUVER (+50%
             light cavalry production) and AGOGE (+50% ranged — the Saka is
             RANGED class, engine-verified, so Agoge boosts it, NOT Maneuver).
             Target ~12 horsemen before opening.
  3. t60+    Conquest loop: nearest rival capital -> declare war -> stack moves
             as one -> horse archers soften, horsemen finish -> capture ->
             next capital. Repeat until every original capital is ours.

Mistakes from the turn-464 defeat that this run must not repeat:
  * ~50 turns of hoarded gold while purchases silently failed. Here: every buy
    is confirmed by the treasury actually dropping, one purchase per city per
    turn (the real engine limit), and gold above a threshold is always spent.
  * Zero military/tactical logic. Here: the war layer IS the strategy.
  * Trusting ok=true. Here: every action is verified by a state change —
    war by IsAtWarWith, policies by IsPolicyActive, production by the build
    hash, founding by city count, purchases by gold delta.
  * POLICY_DISCIPLINE (+5 CS vs barbarians) is a DEAD CARD in this game
    because we turned barbarians off. It is explicitly never slotted.
========================================================================

Usage: python win_domination.py [max_turns]
"""
import json
import sys
import time
import traceback
from pathlib import Path

from play_batch import cmd, ex, get_state, http, load_policy, me_of, save_policy
from play_to_end import buildable, clear_popups, found_spot, gold_now, prod_hash

LOG_FILE = Path(__file__).parent / "win_domination.log"

# Beeline to horses, then the supporting military/economy techs.
# ENGINE-CHECKED, and not what the guides say: in this ruleset
# TECH_HORSEBACK_RIDING's prereq is TECH_ARCHERY (verified via
# GameInfo.TechnologyPrereqs at t20 — CanResearch was false with Animal
# Husbandry already done). Archery therefore sits second, or the entire horse
# plan is unreachable and the queue quietly wanders off into Bronze Working.
RESEARCH_QUEUE = [
    "TECH_ANIMAL_HUSBANDRY", "TECH_ARCHERY", "TECH_HORSEBACK_RIDING",
    "TECH_MINING", "TECH_BRONZE_WORKING", "TECH_POTTERY", "TECH_WRITING",
    "TECH_IRON_WORKING", "TECH_THE_WHEEL", "TECH_MASONRY", "TECH_CURRENCY",
    "TECH_MATHEMATICS", "TECH_CONSTRUCTION", "TECH_STIRRUPS",
    "TECH_MILITARY_TACTICS", "TECH_APPRENTICESHIP", "TECH_MACHINERY",
    "TECH_ENGINEERING", "TECH_EDUCATION", "TECH_GUNPOWDER",
]
# Craftsmanship -> Agoge, Military Tradition -> Maneuver, State Workforce ->
# Conscription. Political Philosophy for a real government.
CIVIC_QUEUE = [
    "CIVIC_CODE_OF_LAWS", "CIVIC_CRAFTSMANSHIP", "CIVIC_MILITARY_TRADITION",
    "CIVIC_STATE_WORKFORCE", "CIVIC_POLITICAL_PHILOSOPHY", "CIVIC_EARLY_EMPIRE",
    "CIVIC_FOREIGN_TRADE", "CIVIC_MILITARY_TRAINING", "CIVIC_DEFENSIVE_TACTICS",
    "CIVIC_RECORDED_HISTORY", "CIVIC_FEUDALISM", "CIVIC_MERCENARIES",
]
# Highest priority first. The engine decides which slot each can occupy, so one
# flat list covers military/economic/wildcard. DISCIPLINE and SURVEY are
# deliberately absent: Discipline only helps against barbarians (disabled) and
# Survey only boosts recon XP.
# AGOGE outranks MANEUVER: verified at t80 that we hold ZERO horses, so no
# light/heavy cavalry is buildable at all and Maneuver boosts literally nothing.
# The Saka Horse Archer is RANGED and needs no horses, so Agoge is the card that
# actually multiplies our only army.
POLICY_PRIORITY = [
    "POLICY_AGOGE",             # +50% prod: melee/anti-cav/RANGED (the Saka)
    "POLICY_MANEUVER",          # cavalry — dead while we have no horses
    "POLICY_URBAN_PLANNING",    # +1 production per city
    "POLICY_CONSCRIPTION",      # -1 gold maintenance per unit
    "POLICY_COLONIZATION",      # +50% settler production (expansion phase)
    "POLICY_ILKUM", "POLICY_AGRARIAN_REVOLUTION", "POLICY_GOD_KING",
    "POLICY_VETERANCY", "POLICY_RAID", "POLICY_PROFESSIONAL_ARMY",
    "POLICY_CARAVANSARIES", "POLICY_LAND_SURVEYORS",
]
# BANKRUPTCY ORDER. At t176-185 the army fell 11 -> 7 while AT PEACE: gold was
# 0, so Civ 6 was auto-disbanding units we could not pay maintenance for. That
# is not a war problem, it is a budget problem, and no amount of production
# fixes it. Conscription (-1 gold per unit per turn) is worth more than Agoge's
# production bonus when units are being disbanded — with ~15 units it swings
# the treasury by 15 gold a turn.
POLICY_PRIORITY_BROKE = [
    "POLICY_CONSCRIPTION", "POLICY_URBAN_PLANNING", "POLICY_CARAVANSARIES",
    "POLICY_AGOGE", "POLICY_MANEUVER", "POLICY_ILKUM", "POLICY_GOD_KING",
]
# Hysteresis, same reason as the regroup thresholds: a single cutoff makes the
# state flip every few turns. At t200 gold reached 30, one above a 25 cutoff,
# and Conscription was immediately dropped for Agoge — which restarts the very
# maintenance spiral that emptied the treasury. Enter broke mode at 25, leave
# it only once genuinely solvent at 150.
BROKE_GOLD = 25
SOLVENT_GOLD = 150
# Smallest treasury drop that can only be a real purchase. Anything less is
# ordinary per-turn income/maintenance drift, which was being logged as a
# successful buy — a false positive in the very check meant to catch the
# silent-purchase-failure bug that lost the previous campaign.
MIN_PURCHASE_DROP = 25

# Early we need settlers; from EXPAND_UNTIL cities on it is all army.
# Raised 4 -> 6 at t60. The expansion race is being won uncontested (we had 3
# cities to the AI's 1-2) and Horseback Riding was crawling because science is
# population-driven and we had none. With barbarians off there is no risk to
# undefended settlers, and every extra city compounds BOTH the science that
# unlocks horsemen and the production that builds them. Going wide is simply
# the stronger line here; the army phase starts from a much bigger base.
EXPAND_UNTIL = 6
# Lowered 10 -> 8 at t102. The AI is now out-expanding us (4 cities to our 5,
# and climbing) so waiting compounds THEIR advantage, not ours. At Settler
# difficulty their cities are held by a warrior or two, and Saka outrange them
# entirely — 8 units is already overwhelming for the nearest target.
ARMY_OPEN_WAR = 8
# Break off a losing siege instead of feeding it. The runner had no doctrine for
# this: it attacked for as long as it was at war, whatever its strength, and the
# army fell 23 -> 9 besieging one city. Below REGROUP_BELOW the army falls back
# to a friendly city (healing on the way, still fighting anything that closes)
# and does not resume offensive operations until RESUME_AT.
REGROUP_BELOW = 7
# Lowered 16 -> 12 at t275. The threshold was set when the army was Saka (25
# ranged, 20 defence); we now field Crossbowmen (40 ranged) and Catapults that
# actually break walls, with Gunpowder coming. Twelve of these are worth far
# more than sixteen Saka, and at ~6 minutes of wall time per turn, waiting for
# a number chosen for weaker units costs hours for no gain.
RESUME_AT = 12
# Mass before assaulting. Units arrive at a distant target one at a time — our
# fast Saka reach the walls turns ahead of 2-movement Trebuchets and Rams — and
# a lone vanguard just dies: at t291-t299 the army fell 12 -> 9 while landing
# ONE attack per turn. Gather this many within RALLY_RADIUS of the target
# before advancing on it.
MASS_BEFORE_ASSAULT = 8
RALLY_RADIUS = 4
MIL_CLASSES = ("UNIT_HORSEMAN", "UNIT_SCYTHIAN_HORSE_ARCHER", "UNIT_WARRIOR",
               "UNIT_ARCHER", "UNIT_SWORDSMAN", "UNIT_SPEARMAN", "UNIT_KNIGHT",
               "UNIT_CROSSBOWMAN", "UNIT_PIKEMAN", "UNIT_MAN_AT_ARMS",
               # Siege counts as army. Engineering landed at ~t265 and cities
               # began building Catapults — the units that actually break the
               # Ancient Walls that stopped us at Nagara Jayasri — but they were
               # missing here, so they added nothing to the army total and the
               # RESUME_AT=16 gate could never be reached however many we built.
               "UNIT_CATAPULT", "UNIT_TREBUCHET", "UNIT_BOMBARD",
               "UNIT_HEAVY_CHARIOT")
# Never build these: religious/civilian units that cost production and do
# nothing for a war. They arrive through the "everything else buildable"
# fallback — a Missionary got built at t268 exactly that way.
NEVER_BUILD = {"UNIT_MISSIONARY", "UNIT_APOSTLE", "UNIT_INQUISITOR", "UNIT_GURU",
               "UNIT_NATURALIST", "UNIT_ROCK_BAND", "UNIT_ARCHAEOLOGIST",
               "UNIT_SPY", "UNIT_MEDIC"}

BUILD_WAR = [
    "UNIT_CATAPULT",           # breaks the walls that stopped the first siege
    "UNIT_SCYTHIAN_HORSE_ARCHER", "UNIT_HORSEMAN", "UNIT_KNIGHT",
    "UNIT_HEAVY_CHARIOT", "UNIT_ARCHER", "UNIT_SWORDSMAN",
    "BUILDING_MONUMENT", "BUILDING_GRANARY", "BUILDING_WATER_MILL", "UNIT_BUILDER",
]
# ANCIENT WALLS ARE WHY THE SIEGE STALLED. In Civ 6 ranged units chip Outer
# Defenses and cannot touch city HP while walls stand — so 23 Saka with five
# adjacent to Nagara Jayasri achieved nothing for five straight turns while
# taking almost no damage themselves. Battering Ram / Siege Tower let ADJACENT
# MELEE bypass walls; both are already unlocked (Masonry / Construction).
SIEGE_SUPPORT = ("UNIT_BATTERING_RAM", "UNIT_SIEGE_TOWER")
MIN_SIEGE_SUPPORT = 2
# RANGED UNITS CANNOT CAPTURE CITIES IN CIV 6. A pure Saka army can grind any
# city to zero HP and then take nothing at all. These are the classes that can
# actually walk in and claim it, and the runner keeps a minimum of them.
CAPTURE_CLASSES = ("UNIT_WARRIOR", "UNIT_SWORDSMAN", "UNIT_SPEARMAN",
                   "UNIT_HORSEMAN", "UNIT_KNIGHT", "UNIT_MAN_AT_ARMS",
                   "UNIT_PIKEMAN", "UNIT_HEAVY_CHARIOT")
MIN_CAPTURE_UNITS = 4
# Scout sits above Monument on purpose: while the city is pop 1 a Settler is not
# buildable, and the fallback should be something that finds rivals (3 moves, no
# barbarian risk this game) rather than culture we cannot yet spend.
# Saka sits directly behind Settler. It used to sit BEHIND Monument, which meant
# that while we were under the expand target every city built Monuments and
# Builders — the army sat flat at 6 units from t90 to t110 while the AI grew to
# 4 cities apiece. Expansion should cost us settler production, not our army.
BUILD_EXPAND = ["UNIT_SETTLER", "UNIT_SCYTHIAN_HORSE_ARCHER", "UNIT_SCOUT",
                "UNIT_HORSEMAN", "BUILDING_MONUMENT", "UNIT_BUILDER", "UNIT_WARRIOR"]
# Hard deadline on the expansion phase. We stalled at 5 cities with no settler
# anywhere and no legal sites left, so `len(cities) < EXPAND_UNTIL` would have
# held us in expand mode — building Monuments — for the rest of the game.
EXPAND_DEADLINE_TURN = 115

# ----------------------------------------------------------------- Lua helpers
WAR_LUA = """
function Bridge_Enemies()
  local pid = Game.GetLocalPlayer()
  local dip = Players[pid]:GetDiplomacy()
  local out = {}
  for _, opid in ipairs(PlayerManager.GetAliveIDs()) do
    if opid ~= pid and opid < 62 then
      local pl = Players[opid]
      local met, war, major = false, false, false
      pcall(function() met = dip:HasMet(opid) end)
      pcall(function() war = dip:IsAtWarWith(opid) end)
      pcall(function() major = pl:IsMajor() end)
      local cities = {}
      pcall(function()
        for _, c in pl:GetCities():Members() do
          local cap = false
          pcall(function() cap = c:IsCapital() end)
          cities[#cities+1] = string.format('{"x":%d,"y":%d,"cap":%s}', c:GetX(), c:GetY(), tostring(cap))
        end
      end)
      out[#out+1] = string.format('{"pid":%d,"met":%s,"war":%s,"major":%s,"cities":[%s]}',
        opid, tostring(met), tostring(war), tostring(major), table.concat(cities, ","))
    end
  end
  print("BRIDGE_ENEMIES:[" .. table.concat(out, ",") .. "]")
end

-- Move a unit toward (tx,ty) even when that plot is NOT yet revealed.
-- Bridge_Enemies reports a met rival's cities straight from the engine whether
-- or not we have actually laid eyes on them, so the war target is usually an
-- unrevealed plot — and MOVE_TO into the unknown silently no-ops (the same
-- trap that froze every explorer from t16 to t40). Falls back to the farthest
-- revealed passable plot along the bearing, which closes the distance each
-- turn until the city itself becomes visible and directly targetable.
-- Sue for peace. Fighting three majors at once with four units is how the
-- previous campaign ended too: committed against p3/p5 in the south, p1 walked
-- in and took Myriv, Solokha and Pazyryk. Peace buys the turns to rebuild.
function Bridge_MakePeace(target)
  local pid = Game.GetLocalPlayer()
  local tp = {}
  tp[PlayerOperations.PARAM_PLAYER_ONE] = pid
  tp[PlayerOperations.PARAM_PLAYER_TWO] = target
  local ok = pcall(function()
    UI.RequestPlayerOperation(pid, PlayerOperations.DIPLOMACY_MAKE_PEACE, tp)
  end)
  print("BRIDGE_PEACE:" .. tostring(ok))
end

-- Wake every unit before ordering it. Units that end a turn with no orders get
-- fortified/slept, and Bridge_FinishIdle has been putting the whole army into
-- that state every turn for hundreds of turns. A slept unit ignores MOVE_TO:
-- CanStartOperation still returns true (confirmed for a Trebuchet ordered onto
-- revealed, passable, reachable grassland) and RequestOperation silently does
-- nothing — which is exactly the freeze we could not explain.
function Bridge_WakeAll()
  local pid = Game.GetLocalPlayer()
  local n = 0
  for _, u in Players[pid]:GetUnits():Members() do
    pcall(function()
      if UnitManager.CanStartCommand(u, UnitCommandTypes.WAKE, nil) then
        UnitManager.RequestCommand(u, UnitCommandTypes.WAKE, nil)
        n = n + 1
      end
    end)
  end
  print("BRIDGE_WAKE:" .. n)
end

function Bridge_MoveToward(u, tx, ty)
  local pid = Game.GetLocalPlayer()
  local vis = nil
  pcall(function() vis = PlayersVisibility[pid] end)
  local ux, uy = u:GetX(), u:GetY()
  local w, h = Map.GetGridSize()
  -- NEVER order a move further than this unit can travel THIS TURN.
  -- Bridge_FinishIdle runs before every end_turn (it is what stops the turn
  -- cycle stalling on idle units) and it CANCELS pending multi-turn paths. So a
  -- unit ordered 10 hexes away has its path wiped before it executes and never
  -- moves at all: the army sat on identical tiles from t296 to t310 while the
  -- log reported moved=14 every single turn. Short hops complete within the
  -- turn, which is why explorers and settlers always worked.
  local reach = 1
  pcall(function() reach = math.max(1, math.floor(u:GetMovesRemaining())) end)
  -- Prefer a DIRECT order to the real destination: that uses the engine's own
  -- pathfinder, which routes around water, mountains and other units. The
  -- straight-line fallback below cannot, so 2-movement units kept finding
  -- nothing passable within reach and stood still. This only works because the
  -- unconditional pre-end_turn FinishIdle was removed — it used to cancel these
  -- multi-turn paths every turn.
  local revealed = true
  if vis then pcall(function() revealed = vis:IsRevealed(tx, ty) end) end
  if revealed then
    local tp = {}
    tp[UnitOperationTypes.PARAM_X] = tx
    tp[UnitOperationTypes.PARAM_Y] = ty
    if UnitManager.CanStartOperation(u, UnitOperationTypes.MOVE_TO, nil, tp) then
      UnitManager.RequestOperation(u, UnitOperationTypes.MOVE_TO, tp)
      return true
    end
  end
  -- Straight-line fallback, capped at ONE step. It cannot route around terrain,
  -- so letting it run several tiles per turn walked units into dead ends far
  -- from any sensible path — a Trebuchet ended up at (11,13), ten hexes past
  -- the rally in the wrong direction. One cautious step keeps a blocked unit
  -- nudging forward without letting a bad heading compound across turns.
  local dx, dy = tx - ux, ty - uy
  local sx = (dx > 0 and 1) or ((dx < 0) and -1 or 0)
  local sy = (dy > 0 and 1) or ((dy < 0) and -1 or 0)
  local bx, by = nil, nil
  for step = 1, 1 do
    local x = (ux + sx * step) % w
    local y = uy + sy * step
    if y < 0 or y >= h then break end
    local plot = Map.GetPlot(x, y)
    if not plot then break end
    local r = true
    if vis then pcall(function() r = vis:IsRevealed(x, y) end) end
    if not r then break end
    if not plot:IsWater() and not plot:IsImpassable() then bx, by = x, y end
  end
  if bx and (bx ~= ux or by ~= uy) then
    local tp2 = {}
    tp2[UnitOperationTypes.PARAM_X] = bx
    tp2[UnitOperationTypes.PARAM_Y] = by
    if UnitManager.CanStartOperation(u, UnitOperationTypes.MOVE_TO, nil, tp2) then
      UnitManager.RequestOperation(u, UnitOperationTypes.MOVE_TO, tp2)
      return true
    end
  end
  return false
end

function Bridge_DeclareWar(target)
  local pid = Game.GetLocalPlayer()
  local tp = {}
  tp[PlayerOperations.PARAM_PLAYER_ONE] = pid
  tp[PlayerOperations.PARAM_PLAYER_TWO] = target
  local ok = pcall(function()
    UI.RequestPlayerOperation(pid, PlayerOperations.DIPLOMACY_DECLARE_WAR, tp)
  end)
  print("BRIDGE_WARDEC:" .. tostring(ok))
end

-- One tactical step for every military unit. Doing this in Lua (not Python)
-- keeps hex distance, unit range and engine validation on the engine side.
-- Target choice prefers WOUNDED enemies: Tomyris gets +5 CS against them and
-- heals up to 50 HP on a kill, so hitting the hurt ones compounds.
function Bridge_WarStep(tx, ty, homeX, homeY)
  local pid = Game.GetLocalPlayer()
  local dip = Players[pid]:GetDiplomacy()
  local targets = {}
  for _, opid in ipairs(PlayerManager.GetAliveIDs()) do
    if opid ~= pid then
      local atwar = false
      pcall(function() atwar = dip:IsAtWarWith(opid) end)
      if atwar then
        local pl = Players[opid]
        pcall(function()
          for _, c in pl:GetCities():Members() do
            targets[#targets+1] = {x=c:GetX(), y=c:GetY(), hp=0, city=true}
          end
        end)
        pcall(function()
          for _, u in pl:GetUnits():Members() do
            targets[#targets+1] = {x=u:GetX(), y=u:GetY(), hp=u:GetDamage(), city=false}
          end
        end)
      end
    end
  end
  local attacked, moved, pulled = 0, 0, 0
  for _, u in Players[pid]:GetUnits():Members() do
    if u:GetMovesRemaining() > 0 then
      local info = GameInfo.Units[u:GetType()]
      local cls = info and tostring(info.PromotionClass) or "nil"
      local isMil = cls ~= "nil" and cls ~= "PROMOTION_CLASS_RECON"
      -- PULL BADLY HURT UNITS OUT. A Saka has 20 defence and takes the city's
      -- ranged attack every turn it stands adjacent; Tomyris only heals on a
      -- KILL, so grinding a city's walls gives no healing back at all. Feeding
      -- wounded units into that is why the army fell 22 -> 13 while winning.
      if isMil and info and u:GetDamage() >= 60 and homeX and homeX >= 0 then
        if Bridge_MoveToward(u, homeX, homeY) then
          pulled = pulled + 1
          isMil = false          -- withdrawn this turn; do not also order it forward
        end
      end
      if isMil and info then
        local ux, uy = u:GetX(), u:GetY()
        local isRanged = (cls == "PROMOTION_CLASS_RANGED")
        local rng = 1
        if isRanged and info.Range and info.Range > 0 then rng = info.Range end
        local best, bestScore = nil, -1
        for _, t in ipairs(targets) do
          local d = Map.GetPlotDistance(ux, uy, t.x, t.y)
          if d <= rng then
            local s = t.hp + (t.city and 0 or 15)
            if s > bestScore then bestScore = s; best = t end
          end
        end
        if best then
          local tp = {}
          tp[UnitOperationTypes.PARAM_X] = best.x
          tp[UnitOperationTypes.PARAM_Y] = best.y
          local op = UnitOperationTypes.MOVE_TO
          if isRanged then
            op = UnitOperationTypes.RANGE_ATTACK
          else
            tp[UnitOperationTypes.PARAM_MODIFIERS] = UnitOperationMoveModifiers.ATTACK
          end
          if UnitManager.CanStartOperation(u, op, nil, tp) then
            UnitManager.RequestOperation(u, op, tp)
            attacked = attacked + 1
          end
        elseif tx >= 0 then
          -- The ring exists ONLY to avoid ordering a plain MOVE_TO onto an enemy
          -- CITY tile (silently discarded without the ATTACK modifier). Applied
          -- to an ordinary destination it does the opposite of what is wanted:
          -- spreading units around a RALLY point by unit ID scatters the army
          -- instead of gathering it, which is why massing sat at 0/8 for 40
          -- turns while units drifted 11-20 hexes away. Ring only for cities.
          local isCityTarget = false
          for _, t in ipairs(targets) do
            if t.city and t.x == tx and t.y == ty then isCityTarget = true end
          end
          if not isCityTarget then
            -- Open ground (e.g. a rally point): head straight for it so the
            -- army actually concentrates. No goto here — Civ 6 runs Lua 5.1,
            -- which has no goto, and a syntax error would silently kill the
            -- entire injected war module.
            if Bridge_MoveToward(u, tx, ty) then moved = moved + 1 end
          else
          -- Spread the army around the city instead of all funnelling to the
          -- single closest adjacent plot. Civ 6 allows one unit per tile, so a
          -- shared destination makes 15 units queue behind the one that got
          -- there first: at t134 a 16-unit army landed exactly ONE attack per
          -- turn. Indexing the ring by unit ID puts a different unit on each
          -- face of the city, so up to six can strike at once.
          local ring = {}
          for dir = 0, 5 do
            local ok, ap = pcall(function() return Map.GetAdjacentPlot(tx, ty, dir) end)
            if ok and ap and not ap:IsWater() and not ap:IsImpassable() then
              ring[#ring + 1] = ap
            end
          end
          local gx, gy = tx, ty
          if #ring > 0 then
            local pick = ring[(u:GetID() % #ring) + 1]
            gx, gy = pick:GetX(), pick:GetY()
          end
          if Bridge_MoveToward(u, gx, gy) then moved = moved + 1 end
          end
        end
      end
    end
  end
  print("BRIDGE_WAR:" .. attacked .. "," .. moved .. "," .. pulled)
end

-- Fill every policy slot with the best unlocked card. CanSlotPolicy decides
-- which slot accepts which card, so a single priority list covers all types.
function Bridge_AutoPolicy(csv)
  local pid = Game.GetLocalPlayer()
  local c = Players[pid]:GetCulture()
  local want = {}
  for name in string.gmatch(csv, "[^,]+") do want[#want+1] = name end
  local n = 0
  pcall(function() n = c:GetNumPolicySlots() end)
  local changed, report = 0, {}
  for slot = 0, n - 1 do
    -- Only ever REPLACE a slot with a strictly higher-priority card. Skipping
    -- "already active" cards instead made the filler evict its own best pick
    -- every pass: t40 held [ILKUM, MANEUVER], t45 had thrashed to
    -- [AGOGE, URBAN_PLANNING]. Policy swaps also cost gold, so the churn was
    -- paying to get worse.
    local cur = -1
    pcall(function() cur = c:GetSlotPolicy(slot) end)
    local curName = nil
    if cur and cur >= 0 and GameInfo.Policies[cur] then
      curName = GameInfo.Policies[cur].PolicyType
    end
    local curRank = 9999
    for idx, name in ipairs(want) do
      if name == curName then curRank = idx break end
    end
    for idx, name in ipairs(want) do
      if idx >= curRank then break end     -- nothing better available for this slot
      local row = GameInfo.Policies[name]
      if row then
        local unlocked, active, canslot = false, false, false
        pcall(function() unlocked = c:IsPolicyUnlocked(row.Index) end)
        pcall(function() active = c:IsPolicyActive(row.Index) end)
        pcall(function() canslot = c:CanSlotPolicy(row.Index, slot) end)
        if unlocked and not active and canslot then
          local ok = pcall(function() c:RequestEnactPolicy(row.Index, slot) end)
          report[#report+1] = slot .. ":" .. tostring(curName) .. "->" .. name .. "=" .. tostring(ok)
          changed = changed + 1
          break
        end
      end
    end
  end
  print("BRIDGE_POLICY:" .. changed .. "|" .. table.concat(report, ";"))
end

-- Exploration. Domination needs targets, and pick_target ignores civs we have
-- not MET — so without this the army masses forever and never finds anyone.
-- Barbarians are off, so scattering the early army to explore costs nothing.
-- Prefer the engine's own auto-explore; fall back to fanning units out on
-- compass headings if AutomateTypes is not exposed in this context.
-- CRITICAL: you cannot MOVE_TO an UNREVEALED plot. CanStartOperation happily
-- returns true for one (permissive, like every other Civ 6 "can I?" check) and
-- RequestOperation is then a silent no-op because no path can be built into
-- the unknown. That is why scout 196608 sat on the capital tile from t16 to
-- t40 while the log cheerfully reported orders issued. The settler moved fine
-- only because found_spot targets revealed plots.
-- So: march to the FARTHEST REVEALED passable plot along the unit's heading.
-- Each turn that walk reveals more ground, pushing the frontier outward.
function Bridge_Explore()
  local pid = Game.GetLocalPlayer()
  local w, h = Map.GetGridSize()
  local vis = nil
  pcall(function() vis = PlayersVisibility[pid] end)
  local dirs = {{1,0},{-1,0},{0,1},{0,-1},{1,1},{-1,-1},{1,-1},{-1,1}}
  local n_move, n_fail = 0, 0
  for _, u in Players[pid]:GetUnits():Members() do
    if u:GetMovesRemaining() > 0 then
      local info = GameInfo.Units[u:GetType()]
      local cls = info and tostring(info.PromotionClass) or "nil"
      if cls ~= "nil" then          -- military/recon only; never settlers/builders
        local ux, uy = u:GetX(), u:GetY()
        local base = u:GetID() % 8  -- stable per-unit heading (not loop order)
        local moved = false
        for attempt = 0, 7 do
          local d = dirs[((base + attempt) % 8) + 1]
          local bx, by = nil, nil
          for step = 1, 12 do
            local x = (ux + d[1] * step) % w
            local y = uy + d[2] * step
            if y < 0 or y >= h then break end
            local plot = Map.GetPlot(x, y)
            if not plot then break end
            local revealed = true
            if vis then pcall(function() revealed = vis:IsRevealed(x, y) end) end
            if not revealed then break end
            if not plot:IsWater() and not plot:IsImpassable() then bx, by = x, y end
          end
          if bx and (bx ~= ux or by ~= uy) then
            local tp = {}
            tp[UnitOperationTypes.PARAM_X] = bx
            tp[UnitOperationTypes.PARAM_Y] = by
            if UnitManager.CanStartOperation(u, UnitOperationTypes.MOVE_TO, nil, tp) then
              UnitManager.RequestOperation(u, UnitOperationTypes.MOVE_TO, tp)
              n_move = n_move + 1
              moved = true
              break
            end
          end
        end
        if not moved then n_fail = n_fail + 1 end
      end
    end
  end
  print("BRIDGE_EXPLORE:" .. n_move .. "," .. n_fail)
end

-- Automated units ignore war orders, so automation must be cleared before the
-- army is asked to march on a city.
-- Put idle Builders to work. Our production base is the binding constraint on
-- the entire campaign — six cities at 6-14 production cannot field an army —
-- and we were carrying NINETEEN builders with 3 charges each (~57 tile
-- improvements) that had never been given a single order. There is no
-- AutomateTypes in this context, so drive BUILD_IMPROVEMENT directly and let
-- CanStartOperation decide which improvement is legal on the tile.
function Bridge_Improve()
  local pid = Game.GetLocalPlayer()
  local IMPS = {"IMPROVEMENT_FARM", "IMPROVEMENT_MINE", "IMPROVEMENT_PASTURE",
                "IMPROVEMENT_QUARRY", "IMPROVEMENT_PLANTATION", "IMPROVEMENT_CAMP",
                "IMPROVEMENT_LUMBER_MILL", "IMPROVEMENT_FISHING_BOATS"}
  local built, walked = 0, 0
  local w, h = Map.GetGridSize()
  for _, u in Players[pid]:GetUnits():Members() do
    local info = GameInfo.Units[u:GetType()]
    if info and tostring(info.UnitType) == "UNIT_BUILDER" and u:GetMovesRemaining() > 0 then
      local ux, uy = u:GetX(), u:GetY()
      local done = false
      for _, n in ipairs(IMPS) do
        local row = GameInfo.Improvements[n]
        if row and not done then
          local tp = {}
          tp[UnitOperationTypes.PARAM_X] = ux
          tp[UnitOperationTypes.PARAM_Y] = uy
          tp[UnitOperationTypes.PARAM_IMPROVEMENT_TYPE] = row.Hash
          local ok = false
          pcall(function()
            ok = UnitManager.CanStartOperation(u, UnitOperationTypes.BUILD_IMPROVEMENT, nil, tp)
          end)
          if ok then
            pcall(function()
              UnitManager.RequestOperation(u, UnitOperationTypes.BUILD_IMPROVEMENT, tp)
            end)
            built = built + 1
            done = true
          end
        end
      end
      if not done then
        -- NEAREST valid tile, not merely the last one found. Keeping whichever
        -- plot the scan happened to end on meant the choice changed every turn
        -- as the builder moved, so builders wandered forever and built nothing:
        -- 13 walking, 0 built, turn after turn.
        local best, bestd = nil, 9999
        for dy = -3, 3 do
          for dx = -3, 3 do
            if not (dx == 0 and dy == 0) then
              local x, y = (ux + dx) % w, uy + dy
              if y >= 0 and y < h then
                local plot = Map.GetPlot(x, y)
                local okp = false
                pcall(function()
                  okp = plot and plot:GetOwner() == pid and not plot:IsWater()
                        and not plot:IsImpassable()
                        and plot:GetImprovementType() == -1
                end)
                if okp then
                  local d = Map.GetPlotDistance(ux, uy, x, y)
                  if d < bestd then bestd = d; best = { x = x, y = y } end
                end
              end
            end
          end
        end
        if best then
          local tp2 = {}
          tp2[UnitOperationTypes.PARAM_X] = best.x
          tp2[UnitOperationTypes.PARAM_Y] = best.y
          local ok2 = false
          pcall(function()
            ok2 = UnitManager.CanStartOperation(u, UnitOperationTypes.MOVE_TO, nil, tp2)
          end)
          if ok2 then
            pcall(function()
              UnitManager.RequestOperation(u, UnitOperationTypes.MOVE_TO, tp2)
            end)
            walked = walked + 1
          end
        end
      end
    end
  end
  print("BRIDGE_IMPROVE:" .. built .. "," .. walked)
end

function Bridge_StopAuto()
  local pid = Game.GetLocalPlayer()
  local n = 0
  for _, u in Players[pid]:GetUnits():Members() do
    pcall(function()
      if UnitManager.CanStartCommand(u, UnitCommandTypes.STOP_AUTOMATION, nil) then
        UnitManager.RequestCommand(u, UnitCommandTypes.STOP_AUTOMATION, nil)
        n = n + 1
      end
    end)
  end
  print("BRIDGE_STOPAUTO:" .. n)
end

-- Once the expansion phase is over, any city still grinding out a Settler is
-- burning ~80 production on a unit with nowhere legal to found. The runner
-- never interrupts in-flight production, so at t120 FOUR of six cities were
-- still on Settlers queued before the switch — roughly five Saka pairs of
-- production. Civ 6 banks progress per item, so swapping is not a loss.
function Bridge_SwitchFromSettlers(itemName)
  local pid = Game.GetLocalPlayer()
  local row = GameInfo.Units[itemName]
  local settler = GameInfo.Units["UNIT_SETTLER"]
  if not row or not settler then print("BRIDGE_SWITCH:0") return end
  local n = 0
  for _, c in Players[pid]:GetCities():Members() do
    local ok = pcall(function()
      local q = c:GetBuildQueue()
      if q:GetCurrentProductionTypeHash() == settler.Hash then
        local tp = {}
        tp[CityOperationTypes.PARAM_UNIT_TYPE] = row.Hash
        tp[CityOperationTypes.PARAM_INSERT_MODE] = CityOperationTypes.VALUE_EXCLUSIVE
        if CityManager.CanStartOperation(c, CityOperationTypes.BUILD, tp) then
          CityManager.RequestOperation(c, CityOperationTypes.BUILD, tp)
          n = n + 1
        end
      end
    end)
  end
  print("BRIDGE_SWITCH:" .. n)
end

-- Swap cities off an over-queued item, keeping only `keep` of them. The
-- scarce-unit minimum was evaluated per city against completed units, so seven
-- cities simultaneously started Battering Rams to satisfy a minimum of two.
function Bridge_SwitchExcess(fromName, toName, keep)
  local pid = Game.GetLocalPlayer()
  local from = GameInfo.Units[fromName]
  local to = GameInfo.Units[toName]
  if not from or not to then print("BRIDGE_SWITCHEX:0/0") return end
  local seen, switched = 0, 0
  for _, c in Players[pid]:GetCities():Members() do
    pcall(function()
      if c:GetBuildQueue():GetCurrentProductionTypeHash() == from.Hash then
        seen = seen + 1
        if seen > keep then
          local tp = {}
          tp[CityOperationTypes.PARAM_UNIT_TYPE] = to.Hash
          tp[CityOperationTypes.PARAM_INSERT_MODE] = CityOperationTypes.VALUE_EXCLUSIVE
          if CityManager.CanStartOperation(c, CityOperationTypes.BUILD, tp) then
            CityManager.RequestOperation(c, CityOperationTypes.BUILD, tp)
            switched = switched + 1
          end
        end
      end
    end)
  end
  print("BRIDGE_SWITCHEX:" .. switched .. "/" .. seen)
end

function Bridge_ActivePolicies()
  local pid = Game.GetLocalPlayer()
  local c = Players[pid]:GetCulture()
  local out = {}
  for row in GameInfo.Policies() do
    local active = false
    pcall(function() active = c:IsPolicyActive(row.Index) end)
    if active then out[#out+1] = row.PolicyType end
  end
  print("BRIDGE_ACTIVEPOL:" .. table.concat(out, ","))
end
print("BRIDGE_WAR_READY")
"""


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _grab(lines, prefix):
    for l in lines:
        if prefix in l:
            return l[l.find(prefix) + len(prefix):].strip()
    return None


def ex_grab(lua, prefix, wait=3.0, tries=3):
    """Run Lua and pull one tagged line back, retrying.

    The tuner console capture is a race: the game prints, but the exec window
    can close before the line lands. An empty capture means "didn't see it",
    never "it didn't happen" — so retry rather than treating [] as fact.
    """
    for i in range(tries):
        body = _grab(ex(lua, wait + i), prefix)
        if body is not None:
            return body
    return None


def enemies():
    body = ex_grab("Bridge_Enemies()", "BRIDGE_ENEMIES:", 3.5)
    if not body:
        return []
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        return []


def active_policies():
    body = ex_grab("Bridge_ActivePolicies()", "BRIDGE_ACTIVEPOL:", 3.0)
    return [p for p in (body or "").split(",") if p]


def hexdist(x1, y1, x2, y2):
    """Odd-r offset hex distance (matches Map.GetPlotDistance closely enough
    for choosing WHICH city to march on; the engine does the real pathing)."""
    def to_cube(col, row):
        x = col - (row - (row & 1)) // 2
        z = row
        return x, -x - z, z
    ax, ay, az = to_cube(x1, y1)
    bx, by, bz = to_cube(x2, y2)
    return max(abs(ax - bx), abs(ay - by), abs(az - bz))


def pick_target(me, ens, pol):
    """Nearest enemy city to the ARMY, sticky until it falls.

    Two failures this replaces, both seen live at t145:
      * distance was measured from our capital, so a target could look "near"
        while the army was nowhere near it;
      * with no stickiness the pick flipped the instant a city was captured —
        it jumped straight from the p5 front to p3's capital 14 hexes away,
        which would have marched a besieging army off its own siege.
    """
    # Stay on the current target for as long as the enemy still holds it.
    cur = pol.get("target")
    if cur:
        for e in ens:
            if e["pid"] == cur["pid"] and e.get("met"):
                for c in e.get("cities", []):
                    if c["x"] == cur["x"] and c["y"] == cur["y"]:
                        return cur
    if not me["cities"]:
        return None
    # Measure from the army's centre of mass, falling back to the capital.
    mil = [u for u in me["units"] if u["type"] in MIL_CLASSES]
    if mil:
        hx = sum(u["x"] for u in mil) // len(mil)
        hy = sum(u["y"] for u in mil) // len(mil)
    else:
        hx, hy = me["cities"][0]["x"], me["cities"][0]["y"]
    best, bestscore = None, 10 ** 9
    for e in ens:
        if not e.get("major") or not e.get("met"):
            continue
        # Finish one enemy before opening another front. Without this the -6
        # capital bonus produced an exact scoring TIE at t146 between p5's city
        # 6 hexes away and p3's capital 12 hexes away; the tie broke on list
        # order and sent the army 13 hexes off its own siege.
        war_bonus = 4 if e.get("war") else 0
        for c in e.get("cities", []):
            d = hexdist(hx, hy, c["x"], c["y"])
            # Capitals are the win condition, but a -25 bonus made the army walk
            # PAST two adjacent rival cities to reach a capital 14 hexes away
            # (t102: p5's city sat 4 hexes off, its capital 14). A modest tilt
            # keeps capitals preferred among comparable targets while still
            # rolling up the near cities first — each one taken is a forward
            # base and removes production the enemy would defend the capital with.
            score = d - (2 if c.get("cap") else 0) - war_bonus
            if score < bestscore:
                bestscore, best = score, {"pid": e["pid"], "x": c["x"], "y": c["y"],
                                          "cap": c.get("cap", False), "dist": d}
    if best and best != pol.get("target"):
        log(f"target -> p{best['pid']} @({best['x']},{best['y']}) "
            f"dist {best['dist']} cap={best['cap']}")
    pol["target"] = best
    return best


def army_size(me):
    return sum(1 for u in me["units"] if u["type"] in MIL_CLASSES)


def prod_is(city, unit_types):
    """Is this city already building one of these units?

    The state dump stores a localisation KEY (LOC_UNIT_BATTERING_RAM_NAME),
    not the UnitType, so match on the distinctive middle section.
    """
    p = (city.get("production") or "").upper()
    return any(t.replace("UNIT_", "") in p for t in unit_types)


def set_production_war(city, turn, pol, i, expanding, me, tally):
    bl = pol.setdefault("build_blacklist", {}).setdefault(str(city["id"]), [])
    opts = [o for o in buildable(city["id"]) if o not in bl]
    if not opts:
        return None
    want = list(BUILD_EXPAND if expanding else BUILD_WAR)
    # Under invasion, defence outranks offence. Walls and anti-cavalry keep
    # cities; more Saka thrown at a distant siege do not. Every city we lose is
    # production we never get back.
    if pol.get("regrouping"):
        want = ["BUILDING_ANCIENT_WALLS", "BUILDING_WALLS", "UNIT_SPEARMAN",
                "UNIT_ARCHER"] + want
    # Broke: build commerce, and stop adding units we cannot pay for. Queuing
    # more Saka while the treasury is empty just feeds the auto-disband.
    if pol.get("broke"):
        want = ["DISTRICT_COMMERCIAL_HUB", "BUILDING_MARKET", "BUILDING_GRANARY",
                "BUILDING_WATER_MILL", "BUILDING_MONUMENT"] + \
               [w for w in want if not w.startswith("UNIT_")]
    # Scout is the pop-1 fallback, but it must not become an infinite one: while
    # the capital sits at pop 1 (it drops there every time it finishes a Settler)
    # Settler is illegal, so without a cap the city would pump scouts forever.
    # BANNED, not merely de-prioritised. Removing an item from `want` did
    # nothing, because the fallback line below appends every remaining buildable
    # option — silently re-adding exactly what the cap had just excluded. That is
    # why we still had NINE builders and were queuing more at t252 with the cap
    # supposedly in force. Caps have to be applied to the FINAL list.
    banned = set(NEVER_BUILD)
    if sum(1 for u in me["units"] if u["type"] == "UNIT_SCOUT") >= 2:
        banned.add("UNIT_SCOUT")
    if sum(1 for u in me["units"] if u["type"] == "UNIT_BUILDER") >= 3:
        banned.add("UNIT_BUILDER")
    if tally["siege"] >= MIN_SIEGE_SUPPORT:
        banned.update(SIEGE_SUPPORT)
    want = [w for w in want if w not in banned]
    # Scarce-unit minimums count what is ALREADY IN PRODUCTION as well as what
    # exists. Comparing against completed units only meant that, with no ram
    # finished yet, every idle city independently decided it had to build one:
    # at t158 SEVEN of nine cities were building Battering Rams when we wanted
    # two, and rams do not fight — which is exactly why the army bled from 22
    # to 16 while we were "winning".
    if tally["siege"] < MIN_SIEGE_SUPPORT:
        for s in SIEGE_SUPPORT:
            if s in opts:
                want = [s] + [w for w in want if w != s]
                break
    # Then enough city-takers. Ranged units cannot occupy a city, so without
    # these the army wins every fight and captures nothing.
    elif tally["capture"] < MIN_CAPTURE_UNITS:
        for melee in ("UNIT_HEAVY_CHARIOT", "UNIT_SWORDSMAN", "UNIT_WARRIOR"):
            if melee in opts:
                want = [melee] + [w for w in want if w != melee]
                break
    ordered = [w for w in want if w in opts and w not in banned]
    ordered += [o for o in opts
                if o not in ordered and o != "UNIT_SETTLER" and o not in banned]
    for item in ordered[:5]:
        cmd({"id": 920 + i, "action": "set_production", "city_id": city["id"], "item": item})
        if prod_hash(city["id"]) != 0:
            log(f"t{turn}: {city['name']} builds {item}")
            return item
        bl.append(item)
        log(f"t{turn}: {city['name']} silently refused {item} — blacklisted")
    return None


def play_turn(i, pol):
    state = get_state()
    if state is None:
        time.sleep(5)
        return None
    turn = state["turn"]
    me = me_of(state)

    # ---- game over?
    out = ex('print("ALIVE="..tostring(Players[0]:IsAlive())'
             '.." MAJORS="..#PlayerManager.GetAliveMajorIDs())', 2.5)
    line = _grab(out, "ALIVE=")
    if line is None and "InGame" not in http("/states").get("states", {}):
        log(f"t{turn}: InGame context gone — end-game screen (victory or defeat)")
        return "OVER"
    if line and "false" in line.split("MAJORS")[0]:
        log(f"t{turn}: LOCAL PLAYER ELIMINATED")
        return "OVER"
    if line and "MAJORS=1" in line:
        log(f"t{turn}: only one major civ left — DOMINATION ACHIEVED")
        return "OVER"

    # Movement verified by STATE CHANGE, not by the order being accepted.
    # Bridge_WarStep reported moved=8 for seven straight turns while every unit
    # stood still; only comparing positions turn-over-turn exposes that.
    prev_pos = pol.get("last_unit_pos") or {}
    now_pos = {str(u["id"]): [u["x"], u["y"]] for u in me["units"]}
    if prev_pos:
        shared = [k for k in now_pos if k in prev_pos]
        stuck = [k for k in shared if now_pos[k] == prev_pos[k]]
        if shared and len(stuck) == len(shared):
            pol["all_stuck"] = pol.get("all_stuck", 0) + 1
            if pol["all_stuck"] >= 3:
                log(f"t{turn}: WARNING no unit has changed position for "
                    f"{pol['all_stuck']} turns — orders are being discarded")
        else:
            pol["all_stuck"] = 0
    pol["last_unit_pos"] = now_pos

    if pol.get("capital_id") is None and me["cities"]:
        pol["capital_id"] = me["cities"][0]["id"]
        pol["capital_xy"] = [me["cities"][0]["x"], me["cities"][0]["y"]]

    # ---- never idle research/civics
    r = me.get("research", {})
    if not r.get("current") and r.get("options"):
        pick = next((t for t in RESEARCH_QUEUE if t in r["options"]), r["options"][0])
        cmd({"id": 900 + i, "action": "set_research", "tech": pick}, 2.0)
        log(f"t{turn}: research -> {pick}")
    c = me.get("civics", {})
    if not c.get("current"):
        if c.get("options"):
            pick = next((cv for cv in CIVIC_QUEUE if cv in c["options"]), c["options"][0])
            cmd({"id": 910 + i, "action": "set_civic", "civic": pick}, 2.0)
            log(f"t{turn}: civic -> {pick}")
        elif turn % 10 == 0:
            # Idle civics are silent lost culture; surface it rather than
            # letting it sit (seen at t241 with current='-' and no options).
            log(f"t{turn}: WARNING civics idle and no options offered")

    # ---- policies: re-slot every few turns (cards unlock as civics complete)
    if pol.get("broke"):
        if me["gold"] >= SOLVENT_GOLD:
            pol["broke"] = False
            log(f"t{turn}: treasury recovered to {me['gold']} — back to war economy")
    elif me["gold"] <= BROKE_GOLD:
        pol["broke"] = True
        log(f"t{turn}: treasury at {me['gold']} — BROKE, switching to Conscription/commerce")
    broke = pol.get("broke", False)

    if turn % 5 == 0 or turn < 3:
        before = set(active_policies())
        prio = POLICY_PRIORITY_BROKE if broke else POLICY_PRIORITY
        ex(f'Bridge_AutoPolicy("{",".join(prio)}")', 3.0)
        after = set(active_policies())
        if after != before:
            log(f"t{turn}: policies now {sorted(after)}")

    # ---- production
    if turn % 25 == 0:
        pol["build_blacklist"] = {}
    expanding = len(me["cities"]) < EXPAND_UNTIL and turn < EXPAND_DEADLINE_TURN
    if not expanding:
        n = ex_grab('Bridge_SwitchFromSettlers("UNIT_SCYTHIAN_HORSE_ARCHER")',
                    "BRIDGE_SWITCH:", 2.5)
        if n and n != "0":
            log(f"t{turn}: switched {n} city/cities off Settler onto Saka")
        ex_msg = ex_grab(
            f'Bridge_SwitchExcess("UNIT_BATTERING_RAM","UNIT_SCYTHIAN_HORSE_ARCHER",'
            f'{MIN_SIEGE_SUPPORT})', "BRIDGE_SWITCHEX:", 2.5)
        if ex_msg and not ex_msg.startswith("0/"):
            log(f"t{turn}: excess rams switched to Saka ({ex_msg})")
    tally = {
        "siege": sum(1 for u in me["units"] if u["type"] in SIEGE_SUPPORT)
                 + sum(1 for c in me["cities"] if prod_is(c, SIEGE_SUPPORT)),
        "capture": sum(1 for u in me["units"] if u["type"] in CAPTURE_CLASSES)
                   + sum(1 for c in me["cities"] if prod_is(c, CAPTURE_CLASSES)),
    }
    for city in me["cities"]:
        if not city.get("production"):
            got = set_production_war(city, turn, pol, i, expanding, me, tally)
            if got in SIEGE_SUPPORT:
                tally["siege"] += 1        # so the NEXT city sees this decision
            elif got in CAPTURE_CLASSES:
                tally["capture"] += 1

    # ---- settlers found cities (verify by city count, never by ok=true)
    for u in me["units"]:
        if u["type"] != "UNIT_SETTLER" or u["moves"] <= 0:
            continue
        # THE CAPITAL IS FOUNDED WHERE WE STAND, TURN 1, FULL STOP.
        # Civ 6 start positions are pre-vetted by the map generator, so hunting
        # for a "better" tile is pure loss: on the first run the settler walked
        # (17,35)->(16,33) and we still had ZERO cities on turn 4 while all five
        # AIs founded on turn 1. Three turns of empire lost to a yield score.
        if not me["cities"]:
            tries = pol.get("capital_found_tries", 0)
            if tries < 3:
                cmd({"id": 929 + i, "action": "found_city", "unit_id": u["id"]})
                pol["capital_found_tries"] = tries + 1
                log(f"t{turn}: founding CAPITAL in place at ({u['x']},{u['y']}) "
                    f"(attempt {tries + 1})")
                continue
            # in-place genuinely illegal (rare) — fall through to the site search
        spot = found_spot(u["id"])
        if spot is None:
            continue
        sx, sy, sdist = spot
        if sdist == 0:
            cmd({"id": 930 + i, "action": "found_city", "unit_id": u["id"]})
            log(f"t{turn}: founding city at ({sx},{sy})")
        else:
            cmd({"id": 931 + i, "action": "move_unit", "unit_id": u["id"], "x": sx, "y": sy})

    # ---- gold: never hoard. Buy army, confirm by the treasury dropping.
    # While expanding, a bought Settler is worth far more than a bought unit:
    # every extra city compounds production for the rest of the game. Threshold
    # drops too — gold sitting in the treasury does nothing, and hoarding it is
    # precisely what lost the last campaign.
    expand_buy = len(me["cities"]) < EXPAND_UNTIL
    # Under invasion, gold in the bank defends nothing. At t250 we sat on 177
    # gold with the army down to 8 and losing cities, because the peacetime
    # threshold was 220. Buying a defender now beats affording a better one
    # after the city has fallen.
    threshold = 150 if expand_buy else (120 if pol.get("regrouping") else 220)
    if me["gold"] > threshold:
        # UNITS ONLY. Buildings are what cities produce; gold is for the things
        # production cannot deliver fast enough. Buying a 240g Monument (t36,
        # Gelonus, 245 -> 5) emptied the treasury on a 60-production building
        # while horsemen were the actual bottleneck. If nothing here is legal
        # yet the gold banks instead — which is correct, not hoarding: the
        # last campaign's failure was purchases silently NOT happening, and
        # every buy below is still confirmed by the treasury dropping.
        if pol.get("regrouping"):
            # Defenders and walls first while we are being invaded.
            wants = ["UNIT_SPEARMAN", "UNIT_ARCHER", "UNIT_SCYTHIAN_HORSE_ARCHER",
                     "UNIT_SWORDSMAN", "UNIT_WARRIOR", "BUILDING_ANCIENT_WALLS",
                     "BUILDING_WALLS"]
        else:
            wants = ["UNIT_BATTERING_RAM", "UNIT_HEAVY_CHARIOT",
                     "UNIT_SCYTHIAN_HORSE_ARCHER", "UNIT_HORSEMAN", "UNIT_KNIGHT",
                     "UNIT_SWORDSMAN", "UNIT_ARCHER", "UNIT_WARRIOR"]
        if expand_buy:
            wants = ["UNIT_SETTLER"] + wants
        spent = 0
        for city in me["cities"]:
            if spent >= 3:
                break
            for item in wants:
                # Read the treasury immediately BEFORE the attempt: me["gold"]
                # is from the turn-start dump and drifts as income accrues.
                before = gold_now()
                if before is None:
                    break
                cmd({"id": 935 + i, "action": "purchase",
                     "city_id": city["id"], "item": item}, 2.0)
                now = gold_now()
                # "Gold went down" is NOT proof of a purchase — at t257 a 2-gold
                # drift was logged as a bought Archer (they cost ~150). Require a
                # drop big enough that only a real transaction explains it.
                if now is not None and before - now >= MIN_PURCHASE_DROP:
                    log(f"t{turn}: BOUGHT {item} in {city['name']} ({before} -> {now})")
                    me["gold"] = now
                    spent += 1
                    break

    # Wake the army before any orders are issued this turn.
    woke = ex_grab("Bridge_WakeAll()", "BRIDGE_WAKE:", 2.5)
    if woke and woke != "0" and turn % 10 == 0:
        log(f"t{turn}: woke {woke} units")

    # ---- builders improve tiles every turn (economy is the real constraint)
    imp = ex_grab("Bridge_Improve()", "BRIDGE_IMPROVE:", 3.0)
    if imp and not imp.startswith("0,0") and turn % 5 == 0:
        log(f"t{turn}: builders improving (built,walked={imp})")

    # ---- war
    ens = enemies()
    tgt = pick_target(me, ens, pol)
    army = army_size(me)
    # SURVIVAL FIRST. Multi-front war with a broken army loses cities faster
    # than any siege gains them — at t170 we were at war with p1, p3 and p5 with
    # four units and had just lost three cities to p1. Sue for peace with
    # everyone while regrouping; wars can be restarted from strength later.
    wars = [e["pid"] for e in ens if e.get("war") and e.get("major")]
    if wars and army <= REGROUP_BELOW:
        for pid_ in wars:
            ex(f"Bridge_MakePeace({pid_})", 2.0)
        after = enemies()
        still = [e["pid"] for e in after if e.get("war") and e.get("major")]
        if still != wars:
            log(f"t{turn}: peace sued with {wars} -> still at war with {still}")
        ens = after

    at_war_any = any(e.get("war") for e in ens)

    # Regroup state is decided BEFORE anything else, because it gates whether we
    # may start OR continue a war. Previously the declaration happened first, so
    # a rebuilding army would re-declare at ARMY_OPEN_WAR (8) and march straight
    # back out while RESUME_AT (16) was still the stated policy — walking back
    # into the multi-front collapse it had just escaped.
    if pol.get("regrouping"):
        if army >= RESUME_AT:
            pol["regrouping"] = False
            log(f"t{turn}: army rebuilt to {army} — resuming the offensive")
    elif army <= REGROUP_BELOW:
        pol["regrouping"] = True
        log(f"t{turn}: army down to {army} — BREAKING OFF, falling back to heal")
    regrouping = pol.get("regrouping", False)

    if regrouping:
        # Hold on home ground and heal, at war or at peace. Units still strike
        # anything that comes into range, so this is a defensive posture, not a
        # passive one.
        ref = tgt or (me["cities"][0] if me["cities"] else None)
        hx, hy = (pol.get("capital_xy") or [-1, -1])
        if me["cities"] and ref:
            near = min(me["cities"],
                       key=lambda c: hexdist(c["x"], c["y"], ref["x"], ref["y"]))
            hx, hy = near["x"], near["y"]
        res = _grab(ex(f"Bridge_WarStep({hx},{hy},{hx},{hy})", 3.5), "BRIDGE_WAR:")
        log(f"t{turn}: regrouping at ({hx},{hy}) army={army}/{RESUME_AT} -> {res}")
    elif tgt and (at_war_any or army >= ARMY_OPEN_WAR):
        at_war = next((e["war"] for e in ens if e["pid"] == tgt["pid"]), False)
        if not at_war:
            # automated explorers refuse march orders — clear automation first
            ex("Bridge_StopAuto()", 2.5)
            ex(f"Bridge_DeclareWar({tgt['pid']})", 3.0)
            after = enemies()
            now_war = next((e["war"] for e in after if e["pid"] == tgt["pid"]), False)
            log(f"t{turn}: DECLARE WAR on player {tgt['pid']} "
                f"(army {army}) -> at war: {now_war}")
            ens, at_war = after, now_war
        if at_war:
            ex("Bridge_StopAuto()", 2.0)
            # Wounded units fall back to our nearest city to heal.
            hx, hy = (pol.get("capital_xy") or [-1, -1])
            if me["cities"]:
                near = min(me["cities"],
                           key=lambda c: hexdist(c["x"], c["y"], tgt["x"], tgt["y"]))
                hx, hy = near["x"], near["y"]
            mil = [u for u in me["units"] if u["type"] in MIL_CLASSES]
            massed = sum(1 for u in mil
                         if hexdist(u["x"], u["y"], tgt["x"], tgt["y"]) <= RALLY_RADIUS)
            if massed < MASS_BEFORE_ASSAULT and len(mil) >= MASS_BEFORE_ASSAULT:
                # Gather short of the city: two thirds of the way from home,
                # close enough to strike next turn, far enough not to be picked
                # off piecemeal by the city and its garrison.
                gx = (tgt["x"] * 2 + hx) // 3
                gy = (tgt["y"] * 2 + hy) // 3
                res = _grab(ex(f"Bridge_WarStep({gx},{gy},{hx},{hy})", 3.5),
                            "BRIDGE_WAR:")
                log(f"t{turn}: massing at ({gx},{gy}) {massed}/{MASS_BEFORE_ASSAULT} "
                    f"in range of p{tgt['pid']} @({tgt['x']},{tgt['y']}) -> {res}")
            else:
                res = _grab(ex(f"Bridge_WarStep({tgt['x']},{tgt['y']},{hx},{hy})", 3.5),
                            "BRIDGE_WAR:")
                log(f"t{turn}: ASSAULT p{tgt['pid']} @({tgt['x']},{tgt['y']}) "
                    f"massed={massed} army={army} -> attacked,moved,pulled={res}")
    else:
        # Pre-war: explore. We cannot conquer civs we have not met.
        res = ex_grab("Bridge_Explore()", "BRIDGE_EXPLORE:", 3.0)
        met = [e["pid"] for e in ens if e.get("met") and e.get("major")]
        if turn % 5 == 0:
            log(f"t{turn}: exploring (auto,move={res}) | met majors {met} | army {army}")
    pol["last_army"] = army

    save_policy(pol)
    time.sleep(4)

    # ---- end turn. NOTE: Bridge_FinishIdle is deliberately NOT called here.
    # It clears unspent movement so the turn can end, but it also CANCELS
    # pending multi-turn paths — which froze the army in place from t296 to
    # t310 while the log reported orders issued every turn. It is still fired
    # in the retry branch below, where it is genuinely needed to break a stall.
    cmd({"id": 950 + i, "action": "end_turn"}, 2.0)
    deadline = time.time() + 150
    last_kick = time.time()
    while time.time() < deadline:
        time.sleep(2)
        out = ex('print("T="..Game.GetCurrentGameTurn()'
                 '.." A="..tostring(Players[0]:IsTurnActive()))', 1.5)
        line = _grab(out, "T=")
        if line is None:
            continue
        # Accept ANY forward turn, not exactly turn+1. The strict equality here
        # was a real campaign-killer: the insistent end_turn retries below can
        # advance the game by more than one turn, and once the game passed
        # turn+1 the check could never match again. The loop then spun for the
        # full 150s, force-ending turns while SKIPPING every per-turn action —
        # turns 10-15 went by with research idle and nothing built.
        try:
            cur = int(line.split()[0])
        except (ValueError, IndexError):
            continue
        if cur > turn and "A=true" in line:
            if cur > turn + 1:
                log(f"t{turn}: game had already advanced to t{cur}")
            return cur
        if "A=true" in line and time.time() - last_kick > 20:
            cmd({"id": 960 + i, "action": "clear_diplo"}, 1.5)
            n = clear_popups()
            if n:
                log(f"t{turn}: dismissed {n} popup(s)")
            ex("Bridge_FinishIdle(0)", 1.5, "GameCore_Tuner")
            cmd({"id": 961 + i, "action": "end_turn"}, 1.5)
            last_kick = time.time()
        elif "A=false" in line and time.time() - last_kick > 20:
            cmd({"id": 962 + i, "action": "clear_diplo"}, 1.5)
            n = clear_popups()
            if n:
                log(f"t{turn}: dismissed {n} popup(s) during AI round")
            last_kick = time.time()
    log(f"t{turn}: TIMEOUT waiting for next turn")
    return None


def main():
    max_turns = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    log("=" * 70)
    log(f"win_domination starting (max {max_turns} turns) — Scythia, Settler, no barbs")
    from driver import inject_bridge
    inject_bridge()
    from play_to_end import BUILDABLE_LUA, FOUNDSPOT_LUA, DISTRICT_LUA
    for name, blob in (("buildable", BUILDABLE_LUA), ("foundspot", FOUNDSPOT_LUA),
                       ("district", DISTRICT_LUA), ("war", WAR_LUA)):
        out = ex(blob, 3.0)
        log(f"injected {name}: {[l for l in out if 'READY' in l]}")

    pol = load_policy()
    pol.setdefault("build_blacklist", {})
    stalls = 0
    for i in range(max_turns):
        try:
            nt = play_turn(i, pol)
        except Exception as e:
            log(f"turn error: {e}\n{traceback.format_exc(limit=3)}")
            time.sleep(5)
            continue
        if nt == "OVER":
            log("stopping: game decided")
            return
        if nt is None:
            stalls += 1
            log(f"stall {stalls}")
            if stalls >= 10:
                log("10 consecutive stalls — needs a human look")
                return
            continue
        stalls = 0
        if nt % 10 == 0:
            st = get_state()
            if st:
                m = me_of(st)
                log(f"--- t{nt}: gold {m['gold']} | {len(m['cities'])} cities | "
                    f"{len(m['units'])} units (army {army_size(m)}) | rivals "
                    f"{[(p['id'], len(p.get('cities', []))) for p in st['players'] if not p.get('isLocal')]}")


if __name__ == "__main__":
    main()
