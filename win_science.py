"""win_science.py — play a standard game (Prince, barbarians ON, standard
map/speed) to a SCIENCE VICTORY, defense-only military.

=============================== THE PLAN ===============================
Rebuilt 2026-07-24 after two losses: loss #1 (Kongo, science-tall from 3
cities, no military at all, defeated by Vietnam's science win at t464) and
loss #2 (Scythia, domination, army deadlocked massing 1-2/8, treasury hit 0,
engine auto-disbanded the army). Full analysis: SHORTCOMINGS-2026-07-23.md
and research-report.md in this directory.

Why science, why defense-only:
  * Our tactical-combat layer is the weakest part of this codebase and the
    direct cause of both losses. Domination needs that layer to work every
    turn against a moving enemy. Science is a macro race — expansion,
    production, research — which is what this engine already does well.
  * At Prince, combat modifiers are neutral (AI +0 CS, player +0 CS) and the
    AI starts with the same 1 Settler/1 Warrior/0 Builders we do. We do not
    need to out-fight anyone, only out-build them and hold walls.

Top fixes from the research (lean rebuild — not the full 8-system doctrine):
  1. Expansion pacing: 7-12 cities by turn 100 (both losses sat at ~3).
  2. Standing defense: walls + a defender queued the turn a city is founded,
     not after it is threatened.
  3. Governors: Pingala first (capital, GPP), then Magnus (best chop city).
  4. Chopping: builders harvest forest/features into current production.
  5. Boost-aware-ish research/civic queue: ordered toward the space race,
     re-picked from whatever the engine currently offers (never idle).
  6. Envoys sent to city-states as they accumulate.
  7. Pantheon founded once faith allows.
  8. Checkpoint saves every ~25-30 turns under clear names so Duncan can see
     progression, independent of the engine's rotating AutoSave slots.

Every new system (5-8) is best-effort and defensively wrapped: this codebase's
non-negotiable rule is verify-by-state-change, never trust an assumption or an
ack, and a best-effort system failing must never crash or stall the core loop
(expansion/production/research), which is what actually wins the game.
========================================================================

Usage: python win_science.py [max_turns]
"""
import json
import sys
import time
import traceback
from pathlib import Path

from play_batch import cmd, ex, get_state, http, load_policy, me_of, save_policy
from play_to_end import (BUILDABLE_LUA, DISTRICT_LUA, FOUNDSPOT_LUA,
                          POPUP_CONTEXTS, buildable, found_spot, gold_now,
                          prod_hash)
# NB: clear_popups is deliberately NOT imported — this module defines its own
# cheaper version below.

LOG_FILE = Path(__file__).parent / "win_science.log"
SAVES_DIR = Path(r"C:\Users\Duncan\Documents\My Games\Sid Meier's Civilization VI\Saves\Single")

PRINCE_HASH = -179952465

# Science spine: early boosts -> classical infra -> to the space race. Picked
# from whatever GameConfiguration currently offers; never idle. Not a strict
# eureka engine (out of lean scope) but ordered so the cheap/foundational
# techs land first and the tree doesn't wander.
RESEARCH_QUEUE = [
    "TECH_MINING", "TECH_POTTERY", "TECH_ANIMAL_HUSBANDRY", "TECH_WRITING",
    "TECH_ASTROLOGY", "TECH_BRONZE_WORKING", "TECH_IRRIGATION", "TECH_CURRENCY",
    "TECH_HORSEBACK_RIDING", "TECH_MASONRY", "TECH_CONSTRUCTION", "TECH_IRON_WORKING",
    "TECH_MATHEMATICS", "TECH_ENGINEERING", "TECH_EDUCATION", "TECH_APPRENTICESHIP",
    "TECH_MACHINERY", "TECH_ECONOMICS", "TECH_METAL_CASTING", "TECH_GUNPOWDER",
    "TECH_SQUARE_RIGGING", "TECH_SIEGE_TACTICS", "TECH_CHEMISTRY", "TECH_ARCHITECTURE",
    "TECH_ASTRONOMY", "TECH_METALLURGY", "TECH_STEAM_POWER", "TECH_SANITATION",
    "TECH_ELECTRICITY", "TECH_REFINING", "TECH_FLIGHT", "TECH_RADIO",
    "TECH_ADVANCED_FLIGHT", "TECH_ROCKETRY", "TECH_COMPUTERS", "TECH_SATELLITES",
    "TECH_NUCLEAR_FISSION", "TECH_NANOTECHNOLOGY", "TECH_ROBOTICS", "TECH_SMART_MATERIALS",
]
CIVIC_QUEUE = [
    "CIVIC_CODE_OF_LAWS", "CIVIC_FOREIGN_TRADE", "CIVIC_CRAFTSMANSHIP",
    "CIVIC_EARLY_EMPIRE", "CIVIC_MYSTICISM", "CIVIC_STATE_WORKFORCE",
    "CIVIC_POLITICAL_PHILOSOPHY", "CIVIC_DEFENSIVE_TACTICS", "CIVIC_RECORDED_HISTORY",
    "CIVIC_MILITARY_TRAINING", "CIVIC_GUILDS", "CIVIC_MEDIEVAL_FAIRS",
    "CIVIC_NATURAL_HISTORY", "CIVIC_HUMANISM", "CIVIC_THEOLOGY",
]
# Science-lean build order: expand hard, campus everywhere, walls for safety.
# DISTRICT_HANSA is Germany's Industrial Zone replacement and is listed ahead of
# the generic one: this game is Germany (Barbarossa), whose Free Imperial Cities
# ability grants an EXTRA district slot per city beyond the population cap — so
# districts are unusually cheap in opportunity cost here, and the space race is
# ultimately a production race (see research-report.md §3: the science endgame is
# dominated by building laser stations, not by further tech).
#
# SPACE RACE FIRST. Verified live 2026-07-24 in this very game: the ruleset is
# RULESET_STANDARD (base Civ VI — no Rise & Fall, no Gathering Storm), and
# VICTORY_TECHNOLOGY is enabled. GameInfo.Projects() holds 22 rows including the
# five that ARE the science victory:
#   PROJECT_LAUNCH_EARTH_SATELLITE -> PROJECT_LAUNCH_MOON_LANDING ->
#   PROJECT_LAUNCH_MARS_{REACTOR,HABITATION,HYDROPONICS}
# Completing the three Mars components wins. They are built in DISTRICT_SPACEPORT.
#
# These sit at the very top of the priority list because by the time they are
# buildable at all, nothing else matters — every hammer spent elsewhere is a
# hammer not spent on winning.
SPACE_PROJECTS = [
    "PROJECT_LAUNCH_EARTH_SATELLITE", "PROJECT_LAUNCH_MOON_LANDING",
    "PROJECT_LAUNCH_MARS_REACTOR", "PROJECT_LAUNCH_MARS_HABITATION",
    "PROJECT_LAUNCH_MARS_HYDROPONICS",
]
BUILD_PRIORITY = SPACE_PROJECTS + [
    "DISTRICT_SPACEPORT",
    "UNIT_SETTLER",
    "BUILDING_ANCIENT_WALLS", "BUILDING_WALLS",
    "DISTRICT_CAMPUS", "BUILDING_LIBRARY", "BUILDING_UNIVERSITY",
    "BUILDING_RESEARCH_LAB",
    "DISTRICT_HANSA", "DISTRICT_INDUSTRIAL_ZONE", "BUILDING_WORKSHOP",
    "DISTRICT_COMMERCIAL_HUB", "BUILDING_MARKET", "BUILDING_BANK",
    "BUILDING_MONUMENT", "BUILDING_GRANARY", "BUILDING_WATER_MILL",
    "UNIT_WARRIOR", "UNIT_SLINGER", "UNIT_ARCHER", "UNIT_SPEARMAN",
    "UNIT_BUILDER", "UNIT_TRADER",
    "DISTRICT_HARBOR", "DISTRICT_THEATER", "BUILDING_AMPHITHEATER",
]
EXPAND_UNTIL = 10          # stop hard-prioritising settlers past this many cities
EXPAND_DEADLINE_TURN = 120
CHECKPOINT_EVERY = 27      # ~25-30 turns, an off-round number per project convention


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


# Shadows play_to_end.clear_popups (imported above) for this runner only.
#
# The original swept all 15 known popup contexts unconditionally at 0.5s each
# (~8s a sweep) and counted a context whose Close() pcall succeeded — not a
# popup that was actually open. That is why the log read a suspiciously
# identical "dismissed 7 popup(s)" on turn after turn: the same 7 contexts are
# permanently loaded and their Close() always succeeds. The count was noise.
#
# This version asks the daemon which contexts are loaded (one call) and only
# sweeps that intersection, at a shorter wait.
def clear_popups():
    try:
        loaded = set(http("/states").get("states", {}))
    except Exception:
        loaded = None
    targets = [c for c in POPUP_CONTEXTS if loaded is None or c in loaded]
    n = 0
    for ctx in targets:
        try:
            out = http("/exec", {"state": ctx, "wait": 0.25,
                                 "lua": 'if Close ~= nil then local ok = pcall(Close) '
                                        'print("BRIDGE_POP:" .. tostring(ok)) end'})
            if any("BRIDGE_POP:true" in l for l in out.get("output", [])):
                n += 1
        except Exception:
            pass  # a context that is not loaded just errors; keep sweeping
    return n


def ex_grab(lua, prefix, wait=3.0, tries=2):
    for _ in range(tries):
        for l in ex(lua, wait):
            if prefix in l:
                return l.split(prefix, 1)[1].strip()
    return None


# ----------------------------------------------------------------- Lua helpers
# Best-effort systems. Every candidate API call is pcall-wrapped; a wrong guess
# degrades to "0 done" and gets logged, never a crash or a stalled turn.

# GOVERNOR_LUA deleted 2026-07-24 — see the note in play_turn(). Governors are a
# Rise & Fall feature; this game is RULESET_STANDARD and GameInfo.Governors is
# false, so there was never anything for this code to appoint.

CHOP_LUA = '''
function Bridge_Chop()
  local pid = Game.GetLocalPlayer()
  local n = 0
  for _, u in Players[pid]:GetUnits():Members() do
    local info = GameInfo.Units[u:GetType()]
    if info and tostring(info.UnitType) == "UNIT_BUILDER" and u:GetMovesRemaining() > 0 then
      local plot = Map.GetPlot(u:GetX(), u:GetY())
      if plot and plot:GetFeatureType() ~= -1 then
        local ok = false
        pcall(function()
          ok = UnitManager.CanStartOperation(u, UnitOperationTypes.HARVEST_RESOURCE, nil)
        end)
        if ok then
          pcall(function()
            UnitManager.RequestOperation(u, UnitOperationTypes.HARVEST_RESOURCE, nil)
          end)
          n = n + 1
        end
      end
    end
  end
  print("BRIDGE_CHOP:" .. n)
end
'''

# Envoys live on GetInfluence(), NOT GetDiplomacy(). Probed live 2026-07-24:
# Players[pid]:GetInfluence() exists and carries GetTokensToGive; the
# GetDiplomacy() version this used to call has no such method, so the whole
# envoy system was silently doing nothing every turn.
# (These four lines were Lua "--" comments at Python module level from an edit
# made 2026-07-24 10:51 WHILE the runner was live — the file on disk stopped
# parsing and only the already-loaded in-memory copy kept running. Any restart
# would have died instantly with SyntaxError. Always syntax-check after editing
# a file whose process is still running.)
ENVOY_LUA = '''
function Bridge_SendEnvoys()
  local pid = Game.GetLocalPlayer()
  local n = 0
  local dip = Players[pid]:GetInfluence()
  if dip and dip.GetTokensToGive then
    local tokens = 0
    pcall(function() tokens = dip:GetTokensToGive() end)
    for _, other in ipairs(PlayerManager.GetAliveMinorIDs and PlayerManager.GetAliveMinorIDs() or {}) do
      if tokens <= 0 then break end
      local ok = false
      pcall(function() ok = dip:CanGiveTokensToPlayer(other) end)
      if ok then
        pcall(function() dip:GiveTokensToPlayer(other, 1) end)
        n = n + 1
        tokens = tokens - 1
      end
    end
  end
  print("BRIDGE_ENVOY:" .. n)
end
'''

PANTHEON_LUA = '''
function Bridge_Pantheon()
  local pid = Game.GetLocalPlayer()
  local rel = Players[pid]:GetReligion()
  if not rel then print("BRIDGE_PANTHEON:no_religion_api") return end
  local can = false
  pcall(function() can = rel:CanCreatePantheon() end)
  if not can then print("BRIDGE_PANTHEON:not_yet") return end
  local beliefs = {}
  pcall(function() beliefs = rel:GetAvailablePantheonBeliefs() end)
  if beliefs and #beliefs > 0 then
    local ok = pcall(function() rel:CreatePantheon(beliefs[1]) end)
    print("BRIDGE_PANTHEON:" .. tostring(ok) .. ",belief=" .. tostring(beliefs[1]))
  else
    print("BRIDGE_PANTHEON:no_beliefs_available")
  end
end
'''

# Checkpoint save. API VERIFIED LIVE 2026-07-24 by probing the running game:
# Network.SaveGame exists (pairs() does NOT list it — it is C-bound behind the
# table, so it must be probed by direct reference, not enumeration) and takes a
# save-descriptor TABLE, not a name string. SaveLocations.LOCAL_STORAGE=1,
# SaveTypes.SINGLE_PLAYER=1. Proven end-to-end: TESTPROBE_t003.Civ6Save landed in
# Documents\My Games\...\Saves\Single. The ack is still not trusted — the Python
# side confirms the file on disk before logging success.
SAVE_LUA = '''
function Bridge_SaveCheckpoint(name)
  local sg = {}
  sg.Name = name
  sg.Location = SaveLocations.LOCAL_STORAGE
  sg.Type = SaveTypes.SINGLE_PLAYER
  sg.IsAutosave = false
  sg.IsQuicksave = false
  local ok, err = pcall(function() Network.SaveGame(sg) end)
  print("BRIDGE_SAVE:" .. tostring(ok) .. "|" .. tostring(err))
end
'''


# ---------------------------------------------------------------------------
# THE BUG THAT MADE A SCIENCE VICTORY IMPOSSIBLE (found + fixed 2026-07-24).
#
# play_to_end.BUILDABLE_LUA enumerates GameInfo.Units(), .Buildings() and
# .Districts() — and nothing else. GameInfo.Projects() is never asked about, so
# buildable() could never return a space project, so set_production_science()
# could never choose one, so the runner could research the entire tree and then
# sit there building Granaries forever. The CommandIntake set_production handler
# has supported PARAM_PROJECT_TYPE the whole time; only the discovery side was
# blind. This override adds the one missing loop.
#
# Injected AFTER play_to_end's version so this definition wins.
BUILDABLE_PROJECTS_LUA = """
function Bridge_Buildable(cid)
  local city = CityManager.GetCity(Game.GetLocalPlayer(), cid)
  if not city then print("BRIDGE_BUILDABLE:") return end
  local out = {}
  local function try(hash, kind, name)
    local tp = {}
    tp[kind] = hash
    tp[CityOperationTypes.PARAM_INSERT_MODE] = CityOperationTypes.VALUE_EXCLUSIVE
    local ok = false
    pcall(function()
      ok = CityManager.CanStartOperation(city, CityOperationTypes.BUILD, tp)
    end)
    if ok then out[#out+1] = name end
  end
  for row in GameInfo.Units() do try(row.Hash, CityOperationTypes.PARAM_UNIT_TYPE, row.UnitType) end
  for row in GameInfo.Buildings() do try(row.Hash, CityOperationTypes.PARAM_BUILDING_TYPE, row.BuildingType) end
  for row in GameInfo.Districts() do try(row.Hash, CityOperationTypes.PARAM_DISTRICT_TYPE, row.DistrictType) end
  for row in GameInfo.Projects() do try(row.Hash, CityOperationTypes.PARAM_PROJECT_TYPE, row.ProjectType) end
  print("BRIDGE_BUILDABLE:" .. table.concat(out, ","))
end
print("BRIDGE_BUILDABLE_PROJECTS_READY")
"""

# One-round-trip purchase scan. REPLACES a loop that cost ~108 seconds a turn.
#
# The old code did, for every city x every wanted item: gold_now() (2s wait) +
# purchase cmd (2s) + gold_now() (2s) = 6s, for up to 3 cities x 6 items = 108s
# of a ~180s turn, essentially all of it spent discovering that we could not
# afford a Settler. This asks the engine once, in-Lua, which (city, item) pairs
# are genuinely purchasable right now and what they cost.
#
# The gate is FAILURE_REASONS, never the boolean — copied verbatim from the
# handlers.purchase call proven in-engine 2026-07-19, including the
# bTestOnly-style 5th argument and the STANDARD_MILITARY_FORMATION parameter
# that unit purchases need before CanStartCommand will even consider them.
BUYSCAN_LUA = """
function Bridge_BuyScan(wants)
  local pid = Game.GetLocalPlayer()
  local gold = math.floor(Players[pid]:GetTreasury():GetGoldBalance())
  local out = {}
  for _, city in Players[pid]:GetCities():Members() do
    for w in string.gmatch(wants, "[^,]+") do
      local u = GameInfo.Units[w]
      local b = GameInfo.Buildings[w]
      if u or b then
        local tp = {}
        if u then
          tp[CityCommandTypes.PARAM_UNIT_TYPE] = u.Hash
          tp[CityCommandTypes.PARAM_MILITARY_FORMATION_TYPE] = MilitaryFormationTypes.STANDARD_MILITARY_FORMATION
        else
          tp[CityCommandTypes.PARAM_BUILDING_TYPE] = b.Hash
        end
        tp[CityCommandTypes.PARAM_YIELD_TYPE] = GameInfo.Yields["YIELD_GOLD"].Index
        local blocked = true
        pcall(function()
          local _, results = CityManager.CanStartCommand(city, CityCommandTypes.PURCHASE, false, tp, true)
          local raw = results and results[CityCommandResults.FAILURE_REASONS]
          blocked = (raw ~= nil and #raw > 0)
        end)
        -- FAILURE_REASONS does NOT include affordability (verified live
        -- 2026-07-24: a 560g Settler passed the gate on a 208g treasury), so
        -- price it explicitly. cost -1 means "unknown" -> still worth an
        -- attempt rather than silently skipping something buyable.
        local cost = -1
        pcall(function()
          local g = city:GetGold()
          if u then
            cost = g:GetPurchaseCost(GameInfo.Yields["YIELD_GOLD"].Index, u.Hash,
                                     MilitaryFormationTypes.STANDARD_MILITARY_FORMATION)
          else
            cost = g:GetPurchaseCost(GameInfo.Yields["YIELD_GOLD"].Index, b.Hash)
          end
        end)
        if not blocked then
          out[#out+1] = city:GetID() .. ":" .. w .. ":" .. tostring(math.floor(cost))
        end
      end
    end
  end
  print("BRIDGE_BUYSCAN:" .. gold .. "|" .. table.concat(out, ","))
end
print("BRIDGE_BUYSCAN_READY")
"""

# Cheapest available tech/civic, so the fallback when nothing in our queue is
# offered still makes real progress instead of taking options[0] (arbitrary
# engine order, which lets the tree wander off the space-race path).
COSTPICK_LUA = """
function Bridge_CostPick()
  local pid = Game.GetLocalPlayer()
  local t, c = {}, {}
  pcall(function()
    local techs = Players[pid]:GetTechs()
    for row in GameInfo.Technologies() do
      if techs:CanResearch(row.Index) then t[#t+1] = row.TechnologyType .. "=" .. tostring(row.Cost) end
    end
  end)
  pcall(function()
    local cul = Players[pid]:GetCulture()
    for row in GameInfo.Civics() do
      if cul:CanProgress(row.Index) then c[#c+1] = row.CivicType .. "=" .. tostring(row.Cost) end
    end
  end)
  print("BRIDGE_COSTPICK:" .. table.concat(t, ",") .. "|" .. table.concat(c, ","))
end
print("BRIDGE_COSTPICK_READY")
"""


# Cheap space-race check for EVERY city in one round trip. The full
# Bridge_Buildable enumerates every unit, building, district and project row in
# the database per city (hundreds of CanStartOperation calls, 4s wait); running
# that per city per turn from turn 150 on would have cost ~40s a turn at ten
# cities. This tests only the five rows that can win the game.
SPACECHECK_LUA = """
function Bridge_SpaceCheck(list)
  local pid = Game.GetLocalPlayer()
  local out = {}
  for _, city in Players[pid]:GetCities():Members() do
    for w in string.gmatch(list, "[^,]+") do
      local row = GameInfo.Projects[w]
      if row then
        local tp = {}
        tp[CityOperationTypes.PARAM_PROJECT_TYPE] = row.Hash
        tp[CityOperationTypes.PARAM_INSERT_MODE] = CityOperationTypes.VALUE_EXCLUSIVE
        local ok = false
        pcall(function()
          ok = CityManager.CanStartOperation(city, CityOperationTypes.BUILD, tp)
        end)
        if ok then out[#out+1] = city:GetID() .. ":" .. w end
      end
    end
  end
  print("BRIDGE_SPACE:" .. table.concat(out, ","))
end
print("BRIDGE_SPACECHECK_READY")
"""


def space_check():
    """[(city_id, project)] buildable right now, cheapest possible probe."""
    body = ex_grab(f'Bridge_SpaceCheck("{",".join(SPACE_PROJECTS)}")', "BRIDGE_SPACE:", 2.5)
    if not body:
        return []
    res = []
    for tok in body.split(","):
        cid, _, item = tok.partition(":")
        if cid and item:
            try:
                res.append((int(cid), item))
            except ValueError:
                pass
    return res


def buy_scan(wants):
    """(gold, [(city_id, item), ...]) of genuinely purchasable things, one call."""
    body = ex_grab(f'Bridge_BuyScan("{",".join(wants)}")', "BRIDGE_BUYSCAN:", 3.0)
    if not body:
        return None, []
    gold_s, _, rest = body.partition("|")
    try:
        gold = int(gold_s)
    except ValueError:
        return None, []
    pairs = []
    for tok in rest.split(","):
        bits = tok.split(":")
        if len(bits) != 3:
            continue
        try:
            cid, item, cost = int(bits[0]), bits[1], int(bits[2])
        except ValueError:
            continue
        # cost -1 = engine would not price it; attempt anyway.
        if cost < 0 or cost <= gold:
            pairs.append((cid, item, cost))
    return gold, pairs


def probe_saved(name_fragment, since_ts, timeout=45):
    """Verify a checkpoint save actually landed on disk — never trust the Lua ack.

    Network.SaveGame is asynchronous: the ack returns immediately and the file
    appears seconds later, so this polls. (A previous version of this check used
    a mis-quoted raw-string path and reported a WORKING save as failed — hence
    SAVES_DIR is a pathlib Path built once, never a hand-escaped literal.)
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            for f in SAVES_DIR.glob("*.Civ6Save"):
                if f.stat().st_mtime >= since_ts and name_fragment in f.name:
                    return f.name
        except OSError:
            pass
        time.sleep(1)
    return None


def ensure_bridge(verbose=False):
    """Guarantee Bridge_DumpState/Bridge_Execute exist in the running game.

    ROOT-CAUSE FIX (2026-07-24). These functions used to come from the
    CivAgentBridge MOD, which meant they only existed if the mod was in the live
    Mods dir AND enabled AND the game had been restarted — and a restart forces
    the leader-intro splash, the one screen synthetic input cannot dismiss. That
    chain made a human mouse click a hard prerequisite of every run, and it broke
    tonight (mod was in the wrong user dir entirely, so the functions were nil in
    every game).

    The mod was never necessary: its files are plain Lua defining globals, so the
    tuner can define them directly in the live InGame context. Injecting on demand
    removes the mod, the restart, and the click from the critical path, and lets
    the runner self-heal if the game reloads mid-campaign.
    """
    out = ex('print("CHK:"..tostring(Bridge_DumpState))', 2.0)
    if any("CHK:function" in l for l in out):
        return True
    log("bridge functions missing — injecting Lua directly (no mod, no restart)")
    src = None
    for d in (Path(r"C:\Users\Duncan\AppData\Local\Firaxis Games\Sid Meier's Civilization VI\Mods\CivAgentBridge"),
              Path(r"C:\Users\Duncan\Documents\My Games\Sid Meier's Civilization VI\Mods\CivAgentBridge")):
        if (d / "Utils.lua").exists():
            src = d
            break
    if src is None:
        log("FATAL: no CivAgentBridge Lua source found to inject")
        return False
    for fname in ("Utils.lua", "StateDump.lua", "CommandIntake.lua"):
        ex((src / fname).read_text(encoding="utf-8"), 3.5)
    out = ex('print("CHK:"..tostring(Bridge_DumpState))', 2.0)
    ok = any("CHK:function" in l for l in out)
    log(f"bridge injection {'succeeded' if ok else 'FAILED'}")
    return ok


def enemies():
    out = ex('''
    local pid = Game.GetLocalPlayer()
    print("EN:START")
    for _, opid in ipairs(PlayerManager.GetAliveMajorIDs()) do
      if opid ~= pid then
        local war, met = false, false
        pcall(function() war = Players[pid]:GetDiplomacy():IsAtWarWith(opid) end)
        pcall(function() met = Players[pid]:GetDiplomacy():HasMet(opid) end)
        print("EN:" .. opid .. "," .. tostring(war) .. "," .. tostring(met))
      end
    end
    print("EN:END")
    ''', 3.0)
    res = []
    for l in out:
        if l.startswith("EN:") and l not in ("EN:START", "EN:END"):
            parts = l[3:].split(",")
            if len(parts) == 3:
                res.append({"pid": int(parts[0]), "war": parts[1] == "true", "met": parts[2] == "true"})
    return res


def set_production_science(city, turn, pol, expanding, i):
    bl = pol.setdefault("build_blacklist", {}).setdefault(str(city["id"]), [])
    opts = [o for o in buildable(city["id"]) if o not in bl]
    if not opts:
        return None
    want = list(BUILD_PRIORITY)
    if not expanding and "UNIT_SETTLER" in want:
        want = [w for w in want if w != "UNIT_SETTLER"]
    ordered = [w for w in want if w in opts]
    ordered += [o for o in opts if o not in ordered and o != "UNIT_SETTLER"]
    for item in ordered[:5]:
        if item.startswith("DISTRICT_"):
            ex(f'Bridge_BuildDistrict({city["id"]}, "{item}")', 3.0)
        else:
            cmd({"id": 920 + i, "action": "set_production", "city_id": city["id"], "item": item})
        if prod_hash(city["id"]) != 0:
            log(f"t{turn}: {city['name']} builds {item}")
            return item
        bl.append(item)
        log(f"t{turn}: {city['name']} silently refused {item} — blacklisted")
    return None


def check_game_over(state):
    out = ex('print("ALIVE="..tostring(Players[0]:IsAlive())'
             '.." MAJORS="..#PlayerManager.GetAliveMajorIDs())', 2.5)
    line = next((l for l in out if "ALIVE=" in l), None)
    if line is None:
        if "InGame" not in http("/states").get("states", {}):
            return "InGame context vanished — end-game screen (victory or defeat)"
        return None
    if "ALIVE=false" in line:
        return "LOCAL PLAYER ELIMINATED — defeat"
    if state and not me_of(state)["cities"]:
        return "we hold zero cities — effectively defeated"
    return None


def play_turn(i, pol):
    state = get_state()
    if state is None:
        # A missing dump used to mean 10 stalls and a dead run. The usual cause is
        # the bridge globals being gone (fresh game / reload), which is now
        # self-healing rather than fatal.
        log("no state dump; checking bridge and retrying")
        ensure_bridge()
        time.sleep(3)
        return None
    turn = state["turn"]
    me = me_of(state)

    over = check_game_over(state)
    if over:
        log(f"GAME OVER at turn {turn}: {over}")
        return "OVER"

    if pol.get("capital_id") is None and me["cities"]:
        pol["capital_id"] = me["cities"][0]["id"]
        pol["capital_xy"] = [me["cities"][0]["x"], me["cities"][0]["y"]]

    # ---- never idle research/civics
    # Prefer our ordered spine; when the engine offers nothing from it, take the
    # CHEAPEST option rather than options[0]. options[0] is arbitrary engine
    # order, which is how a "science" run wanders into unrelated branches and
    # arrives at the space race twenty turns late.
    r = me.get("research", {})
    c = me.get("civics", {})
    cheap_t, cheap_c = {}, {}
    if (not r.get("current") and r.get("options")) or (not c.get("current") and c.get("options")):
        try:
            body = ex_grab("Bridge_CostPick()", "BRIDGE_COSTPICK:", 2.5) or ""
            tpart, _, cpart = body.partition("|")
            for blob, dest in ((tpart, cheap_t), (cpart, cheap_c)):
                for tok in blob.split(","):
                    k, _, v = tok.partition("=")
                    if k and v.isdigit():
                        dest[k] = int(v)
        except Exception as e:
            log(f"t{turn}: costpick errored: {e}")

    def _pick(queue, opts, costs):
        hit = next((x for x in queue if x in opts), None)
        if hit:
            return hit
        return min(opts, key=lambda o: costs.get(o, 10 ** 9))

    if not r.get("current") and r.get("options"):
        pick = _pick(RESEARCH_QUEUE, r["options"], cheap_t)
        cmd({"id": 900 + i, "action": "set_research", "tech": pick}, 2.0)
        log(f"t{turn}: research -> {pick}")
    if not c.get("current") and c.get("options"):
        pick = _pick(CIVIC_QUEUE, c["options"], cheap_c)
        cmd({"id": 910 + i, "action": "set_civic", "civic": pick}, 2.0)
        log(f"t{turn}: civic -> {pick}")

    # ---- production
    if turn % 25 == 0:
        pol["build_blacklist"] = {}
    expanding = len(me["cities"]) < EXPAND_UNTIL and turn < EXPAND_DEADLINE_TURN
    for city in me["cities"]:
        if not city.get("production"):
            set_production_science(city, turn, pol, expanding, i)

    # ---- SPACE RACE OVERRIDE. Cities are otherwise only re-tasked when they
    # fall idle, which in the endgame means a city can spend 15 turns on a Bank
    # while a Mars component sits available. Once a space project is buildable,
    # pre-empt whatever the city is doing: PARAM_INSERT_MODE is VALUE_EXCLUSIVE,
    # so set_production replaces the queue. Cheap to check (one call per city)
    # and only ever fires very late, when it is the whole point of the run.
    if turn >= 150 or pol.get("space_race_open"):
        try:
            for city_id, item in space_check():
                pol["space_race_open"] = True
                cmd({"id": 940 + i, "action": "set_production",
                     "city_id": city_id, "item": item})
                if prod_hash(city_id) != 0:
                    log(f"t{turn}: *** SPACE RACE *** city {city_id} -> {item}")
        except Exception as e:
            log(f"t{turn}: space check errored: {e}")

    # ---- settlers found cities (verify by city count, never by ok=true)
    for u in me["units"]:
        if u["type"] != "UNIT_SETTLER" or u["moves"] <= 0:
            continue
        if not me["cities"]:
            tries = pol.get("capital_found_tries", 0)
            if tries < 3:
                cmd({"id": 929 + i, "action": "found_city", "unit_id": u["id"]})
                pol["capital_found_tries"] = tries + 1
                log(f"t{turn}: founding CAPITAL in place at ({u['x']},{u['y']})")
                continue
        spot = found_spot(u["id"])
        if spot is None:
            if pol.get("capital_xy"):
                cmd({"id": 932 + i, "action": "move_unit", "unit_id": u["id"],
                     "x": pol["capital_xy"][0], "y": pol["capital_xy"][1]}, 2.0)
            continue
        sx, sy, sdist = spot
        if sdist == 0:
            cmd({"id": 930 + i, "action": "found_city", "unit_id": u["id"]})
            log(f"t{turn}: founding city at ({sx},{sy})")
        else:
            cmd({"id": 931 + i, "action": "move_unit", "unit_id": u["id"], "x": sx, "y": sy})

    # ---- gold: never hoard, but no war spending. ONE scan, then buy.
    threshold = 150 if expanding else 300
    if me["gold"] > threshold:
        wants = ["UNIT_SETTLER"] if expanding else []
        wants += ["BUILDING_ANCIENT_WALLS", "BUILDING_WALLS", "UNIT_BUILDER",
                  "BUILDING_MARKET", "BUILDING_GRANARY"]
        try:
            scan_gold, candidates = buy_scan(wants)
            if scan_gold is not None and candidates:
                rank = {w: n for n, w in enumerate(wants)}
                candidates.sort(key=lambda p: rank.get(p[1], 99))
                bought = set()
                for city_id, item, cost in candidates:
                    # One purchase per city per turn is the engine's practical
                    # limit (2026-07-19): a second buy acks fine and no-ops.
                    if city_id in bought or len(bought) >= 2:
                        continue
                    before = gold_now()
                    if before is None:
                        break
                    cmd({"id": 935 + i, "action": "purchase",
                         "city_id": city_id, "item": item}, 2.0)
                    now = gold_now()
                    if now is not None and before - now >= 20:
                        log(f"t{turn}: BOUGHT {item} in city {city_id} ({before} -> {now})")
                        me["gold"] = now
                        bought.add(city_id)
        except Exception as e:
            log(f"t{turn}: buy scan errored: {e}")

    # ---- best-effort systems (chop, envoys, pantheon). Every failure is
    # logged, never fatal to the turn.
    #
    # GOVERNORS REMOVED 2026-07-24. Not a wrong API name — probed live and
    # GameInfo.Governors itself is false, because governors are a Rise & Fall
    # feature and this game is RULESET_STANDARD. The system could never have
    # worked here; it just burned ~3s of every turn re-sending a large Lua blob
    # to be told "no_governors_manager_found". Resolves the long-standing
    # "Governors: UNRESOLVED" note in the project memory.
    try:
        chopped = ex_grab("Bridge_Chop()", "BRIDGE_CHOP:", 2.0)
        if chopped and chopped != "0":
            log(f"t{turn}: chopped {chopped} tile(s)")
    except Exception as e:
        log(f"t{turn}: chop attempt errored: {e}")

    if turn % 5 == 0:
        try:
            env = ex_grab("Bridge_SendEnvoys()", "BRIDGE_ENVOY:", 2.0)
            if env and env != "0":
                log(f"t{turn}: sent {env} envoy token(s)")
        except Exception as e:
            log(f"t{turn}: envoy attempt errored: {e}")

    if not pol.get("pantheon_founded") and turn % 3 == 0:
        try:
            pan = ex_grab("Bridge_Pantheon()", "BRIDGE_PANTHEON:", 2.0)
            if pan and pan.startswith("true"):
                pol["pantheon_founded"] = True
                log(f"t{turn}: PANTHEON FOUNDED ({pan})")
            elif pan and pan not in ("not_yet",):
                log(f"t{turn}: pantheon attempt -> {pan}")
        except Exception as e:
            log(f"t{turn}: pantheon attempt errored: {e}")

    # ---- checkpoint save every ~25-30 turns, verified on disk
    last_ckpt = pol.get("last_checkpoint_turn", 0)
    if turn - last_ckpt >= CHECKPOINT_EVERY:
        name = f"Progress_t{turn:03d}"
        since = time.time()
        try:
            res = ex_grab(SAVE_LUA + f'\nBridge_SaveCheckpoint("{name}")', "BRIDGE_SAVE:", 3.0)
            landed = probe_saved(f"t{turn:03d}", since - 5, timeout=45)
            if landed:
                log(f"t{turn}: CHECKPOINT SAVED -> {landed} (lua: {res})")
                pol["last_checkpoint_turn"] = turn
            else:
                log(f"t{turn}: checkpoint save NOT verified on disk (lua said: {res}) — will retry next cadence")
        except Exception as e:
            log(f"t{turn}: checkpoint save errored: {e}")

    # ---- defense-only: never declare war; sue for peace if somehow at war;
    # units with moves left just hold position / clear_diplo keeps modals down.
    ens = enemies()
    at_war = [e["pid"] for e in ens if e.get("war")]
    if at_war:
        for pid_ in at_war:
            ex(f'''
            local pid = Game.GetLocalPlayer()
            pcall(function() UI.RequestPlayerOperation(pid, PlayerOperations.DIPLOMACY_MAKE_PEACE,
              {{ [PlayerOperations.PARAM_PLAYER_ONE] = pid, [PlayerOperations.PARAM_PLAYER_TWO] = {pid_} }}) end)
            ''', 2.0)
        log(f"t{turn}: at war with {at_war} — sued for peace (defense-only doctrine)")

    save_policy(pol)
    time.sleep(2)

    # ---- end turn
    cmd({"id": 950 + i, "action": "end_turn"}, 2.0)
    deadline = time.time() + 150
    last_kick = time.time()
    while time.time() < deadline:
        time.sleep(2)
        out = ex('print("T="..Game.GetCurrentGameTurn()'
                 '.." A="..tostring(Players[0]:IsTurnActive()))', 1.5)
        line = next((l for l in out if "T=" in l), "")
        # Parse from the "T=" MARKER, not by whitespace position. The tuner
        # prefixes every console line with its context ("InGame: T=37 A=true"),
        # so line.split()[0] is "InGame:" — which has no "=" and threw IndexError
        # on every single poll. The turn was advancing normally the whole time
        # and the runner reported TIMEOUT anyway (t36, 2026-07-24).
        try:
            idx = line.index("T=")
            cur = int(line[idx + 2:].split()[0])
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
    max_turns = int(sys.argv[1]) if len(sys.argv) > 1 else 500
    log("=" * 60)
    log(f"win_science starting (max {max_turns} turns) — science victory, defense-only")
    if not ensure_bridge(verbose=True):
        log("FATAL: bridge unavailable, refusing to start (would stall every turn)")
        return
    # Inject every helper ONCE, at startup, instead of re-sending the whole
    # function body down the tuner socket on every single turn (the governor,
    # chop, envoy and pantheon blobs were each being redefined ~every turn).
    # Order matters: BUILDABLE_PROJECTS_LUA must come after BUILDABLE_LUA so its
    # project-aware definition of Bridge_Buildable is the one that survives.
    helpers = (
        (BUILDABLE_LUA, "buildable"),
        (BUILDABLE_PROJECTS_LUA, "buildable+projects"),
        (FOUNDSPOT_LUA, "foundspot"),
        (DISTRICT_LUA, "district"),
        (BUYSCAN_LUA, "buyscan"),
        (SPACECHECK_LUA, "spacecheck"),
        (COSTPICK_LUA, "costpick"),
        (CHOP_LUA, "chop"),
        (ENVOY_LUA, "envoy"),
        (PANTHEON_LUA, "pantheon"),
        (SAVE_LUA, "save"),
    )
    for helper, name in helpers:
        ready = ex(helper, 3.0)
        log(f"{name} helper: {[l for l in ready if 'BRIDGE' in l] or 'defined'}")

    # Prove the fix that makes a science victory reachable at all: ask a real
    # city what it can build and confirm PROJECT_ rows can now appear. Verify by
    # state change, never by 'no error'.
    probe = ex('Bridge_Buildable(65536)', 4.0)
    body = next((l.split("BRIDGE_BUILDABLE:")[1] for l in probe if "BRIDGE_BUILDABLE:" in l), "")
    log(f"buildable probe: {len([x for x in body.split(',') if x])} items, "
        f"projects visible={'PROJECT_' in body}")
    live = ex('print("CFG:handicap="..tostring(GameConfiguration.GetValue("GAME_HANDICAP"))'
              '.." nobarb="..tostring(GameConfiguration.GetValue("GAME_NO_BARBARIANS"))'
              '.." civ="..tostring(PlayerConfigurations[Game.GetLocalPlayer()]:GetCivilizationTypeName()))', 2.5)
    log(f"live config: {[l for l in live if 'CFG:' in l]}")

    pol = load_policy()
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
                log("10 consecutive stalls — giving up, needs a human look")
                return
            continue
        stalls = 0
        if nt % 10 == 0:
            st = get_state()
            if st:
                m = me_of(st)
                log(f"--- turn {nt}: gold {m['gold']}, {len(m['cities'])} cities, "
                    f"{len(m['units'])} units | rivals "
                    f"{[(p['id'], len(p['cities'])) for p in st['players'] if not p.get('isLocal')]}")
    log(f"reached max_turns ({max_turns}) without a decision")


if __name__ == "__main__":
    main()
