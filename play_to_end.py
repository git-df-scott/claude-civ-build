"""play_to_end.py — play the campaign autonomously until the game is decided.

Differs from play_batch.py (which runs N turns then stops for human review):
  * runs until win/loss/elimination instead of a fixed batch
  * production is chosen from what the ENGINE says is buildable right now, not a
    fixed queue. play_batch's queue fell back to UNIT_WARRIOR when exhausted, and
    the warrior is obsolete by the mid-game — the CanStartOperation gate rejects
    it, so every city would sit idle forever.
  * survives errors: a bad turn is logged and retried, never fatal
  * detects game over (see check_game_over)

Usage: python play_to_end.py [max_turns]
"""
import json
import sys
import time
import traceback
from pathlib import Path

from play_batch import cmd, ex, get_state, http, load_policy, me_of, save_policy

LOG_FILE = Path(__file__).parent / "play_to_end.log"

# What to build, best first. Science-lean: we are behind on cities (3 v 6-7), so
# grow tall on campuses rather than trying to out-expand the AI from behind.
# Survival first: player 3 is actively taking our cities, so defenders and walls
# outrank science now. Settlers are deliberately absent — the map is full (both
# remaining settlers reported "no legal site within 7 hexes" for ~40 turns).
BUILD_PRIORITY = [
    "UNIT_MUSKETMAN", "UNIT_CROSSBOWMAN", "UNIT_PIKEMAN", "UNIT_KNIGHT",
    "BUILDING_ANCIENT_WALLS", "BUILDING_WALLS",
    "UNIT_SWORDSMAN", "UNIT_ARCHER", "UNIT_SPEARMAN",
    "DISTRICT_CAMPUS", "BUILDING_LIBRARY", "BUILDING_UNIVERSITY",
    "DISTRICT_COMMERCIAL_HUB", "BUILDING_MARKET",
    "BUILDING_MONUMENT", "BUILDING_GRANARY", "BUILDING_WATER_MILL",
    "UNIT_BUILDER",
]

# Injected once: ask the engine what this city can legally start building.
BUILDABLE_LUA = """
function Bridge_Buildable(cid)
  local city = CityManager.GetCity(Game.GetLocalPlayer(), cid)
  if not city then print("BRIDGE_BUILDABLE:") return end
  local out = {}
  local function try(hash, kind, name)
    local tp = {}
    tp[kind] = hash
    tp[CityOperationTypes.PARAM_INSERT_MODE] = CityOperationTypes.VALUE_EXCLUSIVE
    if CityManager.CanStartOperation(city, CityOperationTypes.BUILD, tp) then
      out[#out+1] = name
    end
  end
  for row in GameInfo.Units() do try(row.Hash, CityOperationTypes.PARAM_UNIT_TYPE, row.UnitType) end
  for row in GameInfo.Buildings() do try(row.Hash, CityOperationTypes.PARAM_BUILDING_TYPE, row.BuildingType) end
  for row in GameInfo.Districts() do try(row.Hash, CityOperationTypes.PARAM_DISTRICT_TYPE, row.DistrictType) end
  print("BRIDGE_BUILDABLE:" .. table.concat(out, ","))
end
print("BRIDGE_BUILDABLE_READY")
"""

# Find a LEGAL settle spot. Civ 6 forbids founding within 3 hexes of ANY city,
# including rivals' — and UnitManager.CanStartOperation(FOUND_CITY) returns true
# anyway, so the request just silently no-ops (verified 2026-07-19: a settler sat
# 3 hexes from a player-1 city reporting can=true and founding nothing for 3 turns).
# Chebyshev max(|dx|,|dy|) is NOT hex distance either — must use Map.GetPlotDistance.
FOUNDSPOT_LUA = """
function Bridge_FoundSpot(uid)
  local pid = Game.GetLocalPlayer()
  local u = UnitManager.GetUnit(pid, uid)
  if not u then print("BRIDGE_SPOT:") return end
  local ux, uy = u:GetX(), u:GetY()
  -- ALL alive players, not just majors: city-states block founding exactly the
  -- same way, and using GetAliveMajorIDs missed a p7 city-state 3 hexes out,
  -- which silently blocked every found attempt for several turns (2026-07-19).
  local cities = {}
  for _, opid in ipairs(PlayerManager.GetAliveIDs()) do
    local pl = Players[opid]
    if pl and pl:GetCities() then
      for _, c in pl:GetCities():Members() do
        cities[#cities+1] = { x = c:GetX(), y = c:GetY() }
      end
    end
  end
  local w, h = Map.GetGridSize()
  local best, bestScore = nil, -999
  for dy = -7, 7 do
    for dx = -7, 7 do
      local x, y = (ux + dx) % w, uy + dy
      if y >= 0 and y < h then
        local plot = Map.GetPlot(x, y)
        if plot and not plot:IsWater() and not plot:IsImpassable() and plot:GetOwner() == -1 then
          local ok = true
          for _, c in ipairs(cities) do
            if Map.GetPlotDistance(x, y, c.x, c.y) < 4 then ok = false break end
          end
          if ok then
            local s = 2 * plot:GetYield(YieldTypes.YIELD_FOOD)
                        + plot:GetYield(YieldTypes.YIELD_PRODUCTION)
            if plot:IsFreshWater() then s = s + 3 end
            s = s - Map.GetPlotDistance(ux, uy, x, y)   -- prefer closer sites
            if s > bestScore then bestScore = s; best = { x = x, y = y } end
          end
        end
      end
    end
  end
  if best then
    print("BRIDGE_SPOT:" .. best.x .. "," .. best.y .. "," ..
          Map.GetPlotDistance(ux, uy, best.x, best.y))
  else
    print("BRIDGE_SPOT:")
  end
end
print("BRIDGE_FOUNDSPOT_READY")
"""

# Districts need an EXPLICIT plot. set_production with only a district type is
# accepted (hash goes non-zero) and then silently dropped before the turn rolls,
# so every city blacklisted every district and the science plan died quietly —
# verified 2026-07-19 across all 7 cities. CityManager.GetOperationTargets returns
# the legal plots (13 for the capital's campus); pass one as PARAM_X/PARAM_Y.
DISTRICT_LUA = """
function Bridge_BuildDistrict(cid, dtype)
  local city = CityManager.GetCity(Game.GetLocalPlayer(), cid)
  local row = GameInfo.Districts[dtype]
  if not city or not row then print("BRIDGE_DIST:0") return end
  local tp = {}
  tp[CityOperationTypes.PARAM_DISTRICT_TYPE] = row.Hash
  local targets = CityManager.GetOperationTargets(city, CityOperationTypes.BUILD, tp)
  local plots = targets and targets[CityOperationResults.PLOTS]
  if not plots or #plots == 0 then print("BRIDGE_DIST:0") return end
  local p = Map.GetPlotByIndex(plots[1])
  local bp = {}
  bp[CityOperationTypes.PARAM_DISTRICT_TYPE] = row.Hash
  bp[CityOperationTypes.PARAM_X] = p:GetX()
  bp[CityOperationTypes.PARAM_Y] = p:GetY()
  bp[CityOperationTypes.PARAM_INSERT_MODE] = CityOperationTypes.VALUE_EXCLUSIVE
  CityManager.RequestOperation(city, CityOperationTypes.BUILD, bp)
  print("BRIDGE_DIST:" .. #plots .. "," .. p:GetX() .. "," .. p:GetY())
end
print("BRIDGE_DISTRICT_READY")
"""


def log(msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def buildable(city_id):
    for l in ex(f"Bridge_Buildable({city_id})", 4.0):
        if "BRIDGE_BUILDABLE:" in l:
            body = l.split("BRIDGE_BUILDABLE:")[1].strip()
            return [x for x in body.split(",") if x]
    return []


def gold_now():
    """Live treasury. Purchases ack ok=true even when nothing happens, so the
    only trustworthy signal that a buy landed is the gold actually moving."""
    for l in ex('print("BRIDGE_GOLD:"..math.floor('
                'Players[Game.GetLocalPlayer()]:GetTreasury():GetGoldBalance()))', 2.0):
        if "BRIDGE_GOLD:" in l:
            try:
                return int(l.split("BRIDGE_GOLD:")[1].strip())
            except ValueError:
                return None
    return None


def prod_hash(city_id):
    """0 means the city is genuinely idle."""
    for l in ex(f'local c=CityManager.GetCity(Game.GetLocalPlayer(),{city_id}) '
                f'print("BRIDGE_PH:"..tostring(c and c:GetBuildQueue():GetCurrentProductionTypeHash() or 0))', 2.5):
        if "BRIDGE_PH:" in l:
            try:
                return int(l.split("BRIDGE_PH:")[1].strip())
            except ValueError:
                return 0
    return 0


def set_production_verified(city_id, city_name, turn, pol, i):
    """Queue the best thing that ACTUALLY sticks.

    CanStartOperation(BUILD) is permissive in the same way CanStartCommand and
    FOUND_CITY are: it returns true for districts the city already has, the request
    acks ok=true, and the city stays idle. Verified 2026-07-19 — Kabasa re-queued
    DISTRICT_CAMPUS every turn for 10+ turns with production hash stuck at 0.
    So: issue, then confirm the hash went non-zero; blacklist whatever doesn't take.
    """
    bl = pol.setdefault("build_blacklist", {}).setdefault(str(city_id), [])
    opts = [o for o in buildable(city_id) if o not in bl]
    if not opts:
        return None
    ordered = [w for w in BUILD_PRIORITY if w in opts]
    ordered += [o for o in opts if o not in ordered and o != "UNIT_SETTLER"]
    for item in ordered[:5]:  # cap attempts so a wedged city can't eat the turn
        if item.startswith("DISTRICT_"):
            ex(f'Bridge_BuildDistrict({city_id}, "{item}")', 3.0)
        else:
            cmd({"id": 920 + i, "action": "set_production", "city_id": city_id, "item": item})
        if prod_hash(city_id) != 0:
            log(f"t{turn}: {city_name} builds {item}")
            return item
        bl.append(item)
        log(f"t{turn}: {city_name} silently refused {item} — blacklisted")
    return None


# Blocking full-screen popups halt the turn cycle exactly like diplo modals, but
# they are NOT diplomacy sessions so Bridge_ClearDiplo never touched them. A
# "NATURAL WONDER DISCOVERED" popup wedged turn 258 for ~9 minutes (2026-07-19).
# Each popup context exposes its own Close() — calling it in that context dismisses
# the popup. Synthetic clicks cannot (Civ 6 ignores injected input).
POPUP_CONTEXTS = [
    "NaturalWonderPopup", "EraCompletePopup", "WonderBuiltPopup", "ProjectBuiltPopup",
    "GreatPeoplePopup", "BoostUnlockedPopup", "TechCivicCompletedPopup",
    "UnitPromotionPopup", "EspionagePopup", "EventPopup", "GlobalResourcePopup",
    "PBCNotificationPopup", "DeclareWarPopup", "InGamePopup", "AdvisorPopup",
]


def clear_popups():
    """Close every dismissible popup. Returns how many contexts reported a close."""
    n = 0
    for ctx in POPUP_CONTEXTS:
        try:
            out = http("/exec", {"state": ctx, "wait": 0.5,
                                 "lua": 'if Close ~= nil then local ok = pcall(Close) '
                                        'print("BRIDGE_POP:" .. tostring(ok)) end'})
            if any("BRIDGE_POP:true" in l for l in out.get("output", [])):
                n += 1
        except Exception:
            pass  # a context that is not loaded just errors; keep sweeping
    return n


def found_spot(unit_id):
    """(x, y, hex_distance) of the best legal settle site, or None."""
    for l in ex(f"Bridge_FoundSpot({unit_id})", 4.0):
        if "BRIDGE_SPOT:" in l:
            body = l.split("BRIDGE_SPOT:")[1].strip()
            if not body:
                return None
            try:
                x, y, d = (int(v) for v in body.split(","))
                return x, y, d
            except ValueError:
                return None
    return None


def check_game_over(state):
    """Return a reason string if the game is decided, else None."""
    out = ex('print("ALIVE="..tostring(Players[0]:IsAlive())'
             '.." MAJORS="..#PlayerManager.GetAliveMajorIDs()'
             '.." TURN="..Game.GetCurrentGameTurn())', 2.5)
    line = next((l for l in out if "ALIVE=" in l), None)
    if line is None:
        # InGame context gone usually means an end-game screen took over
        states = http("/states").get("states", {})
        if "InGame" not in states:
            return "InGame context vanished — end-game screen (victory or defeat)"
        return None
    if "ALIVE=false" in line:
        return "LOCAL PLAYER ELIMINATED — defeat"
    if "MAJORS=1" in line:
        return "only one major civ left — game decided by conquest"
    if state and not me_of(state)["cities"]:
        return "we hold zero cities — effectively defeated"
    return None


def play_turn(i, pol):
    state = get_state()
    if state is None:
        log("no state dump; retrying")
        time.sleep(5)
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

    # never let research or civics idle
    r = me.get("research", {})
    if not r.get("current") and r.get("options"):
        pick = r["options"][0]
        cmd({"id": 900 + i, "action": "set_research", "tech": pick}, 2.0)
        log(f"t{turn}: research -> {pick}")
    c = me.get("civics", {})
    if not c.get("current") and c.get("options"):
        pick = c["options"][0]
        cmd({"id": 910 + i, "action": "set_civic", "civic": pick}, 2.0)
        log(f"t{turn}: civic -> {pick}")

    # production: engine-validated choice, so it can never wedge on an obsolete item
    # Blacklists go stale as prereqs complete (a library unlocks a university),
    # so wipe them periodically and let the city re-probe.
    if turn % 25 == 0:
        pol["build_blacklist"] = {}
    last_set = pol.setdefault("last_set", {})
    for city in me["cities"]:
        cid = str(city["id"])
        if city.get("production"):
            last_set.pop(cid, None)
            continue
        # Idle again after we queued something last turn means the engine ACCEPTED
        # the item (hash went non-zero) and then quietly dropped it before the turn
        # rolled — e.g. a district with nowhere legal to be placed. Immediate
        # verification can't see that, so catch it on the rebound.
        # An item that COMPLETED also leaves the city idle, and blacklisting it
        # then is wrong — that wrongly banned a library the moment we bought it.
        # A genuine silent-drop repeats, a completion doesn't, so require two.
        stale = last_set.get(cid)
        if stale:
            lost = pol.setdefault("lost_count", {}).setdefault(cid, {})
            lost[stale] = lost.get(stale, 0) + 1
            if lost[stale] >= 2:
                pol.setdefault("build_blacklist", {}).setdefault(cid, []).append(stale)
                log(f"t{turn}: {city['name']} lost {stale} twice — blacklisted")
            last_set.pop(cid, None)
        got = set_production_verified(city["id"], city["name"], turn, pol, i)
        if got:
            last_set[cid] = got

    # settlers: ask the engine for a legal site (see FOUNDSPOT_LUA), stand on it,
    # then found. Verify by city count — found_city's ok=true means nothing.
    cities_before = len(me["cities"])
    for u in me["units"]:
        if u["type"] != "UNIT_SETTLER" or u["moves"] <= 0:
            continue
        spot = found_spot(u["id"])
        if spot is None:
            # Map is full. Park the settler in the capital instead of re-probing
            # (and re-logging) every turn for the rest of the game.
            if pol.get("capital_xy"):
                cmd({"id": 932 + i, "action": "move_unit", "unit_id": u["id"],
                     "x": pol["capital_xy"][0], "y": pol["capital_xy"][1]}, 2.0)
            continue
        sx, sy, sdist = spot
        if sdist == 0:
            cmd({"id": 930 + i, "action": "found_city", "unit_id": u["id"]})
            log(f"t{turn}: founding at ({sx},{sy})")
        else:
            cmd({"id": 931 + i, "action": "move_unit", "unit_id": u["id"], "x": sx, "y": sy})

    # gold: one purchase per city per turn is the real engine limit (verified
    # 2026-07-19) — extra attempts silently no-op, so only ever try once each.
    # WAR FOOTING. We lost 3 cities and 13 units in one turn to player 3 while
    # sitting on 1351 unspent gold, "buying" libraries that the cities already had
    # (ok=true, gold never moved — the FAILURE_REASONS gate does not catch a
    # duplicate building). Defenders first, and verify by GOLD ACTUALLY DROPPING
    # rather than trusting the ack, same as everything else in this codebase.
    if me["gold"] > 200:
        wants = ["UNIT_MUSKETMAN", "UNIT_CROSSBOWMAN", "UNIT_PIKEMAN", "UNIT_KNIGHT",
                 "UNIT_SWORDSMAN", "UNIT_ARCHER", "UNIT_SPEARMAN",
                 "BUILDING_ANCIENT_WALLS", "BUILDING_WALLS", "UNIT_BUILDER"]
        spent = 0
        for city in me["cities"]:
            if spent >= 3:      # one purchase per city per turn is the engine limit
                break
            for item in wants:
                cmd({"id": 935 + i, "action": "purchase",
                     "city_id": city["id"], "item": item}, 2.0)
                now = gold_now()
                if now is not None and now < me["gold"]:
                    log(f"t{turn}: BOUGHT {item} in {city['name']} "
                        f"(gold {me['gold']} -> {now})")
                    me["gold"] = now
                    spent += 1
                    break

    # scouts keep exploring; wounded units retreat toward the capital
    for u in me["units"]:
        if u["moves"] <= 0:
            continue
        if u["type"] == "UNIT_SCOUT":
            cmd({"id": 941 + i, "action": "move_unit", "unit_id": u["id"],
                 "x": u["x"] + 2, "y": u["y"] + 1}, 2.0)
        elif u.get("damage", 0) > 50 and pol.get("capital_xy"):
            cmd({"id": 942 + i, "action": "move_unit", "unit_id": u["id"],
                 "x": pol["capital_xy"][0], "y": pol["capital_xy"][1]}, 2.0)

    save_policy(pol)
    time.sleep(5)  # let MOVE_TO orders execute before FinishIdle zeroes moves

    # end turn — insist (diplo modals and idle units both stall the tick)
    ex("Bridge_FinishIdle(0)", 2.0, "GameCore_Tuner")
    cmd({"id": 950 + i, "action": "end_turn"}, 2.0)
    deadline = time.time() + 150
    last_kick = time.time()
    while time.time() < deadline:
        time.sleep(2)
        out = ex('print("T="..Game.GetCurrentGameTurn().." A="..tostring(Players[0]:IsTurnActive()))', 1.5)
        line = next((l for l in out if "T=" in l), "")
        if f"T={turn + 1}" in line and "A=true" in line:
            return turn + 1
        if "A=true" in line and time.time() - last_kick > 20:
            cmd({"id": 960 + i, "action": "clear_diplo"}, 1.5)
            npop = clear_popups()
            if npop:
                log(f"t{turn}: dismissed {npop} blocking popup(s)")
            ex("Bridge_FinishIdle(0)", 1.5, "GameCore_Tuner")
            cmd({"id": 961 + i, "action": "end_turn"}, 1.5)
            last_kick = time.time()
        elif "A=false" in line:
            # AI round: a popup here blocks the whole cycle, and our turn is not
            # active so end_turn can't help — sweeping popups is the only recovery.
            cmd({"id": 962 + i, "action": "clear_diplo"}, 1.5)
            if time.time() - last_kick > 20:
                npop = clear_popups()
                if npop:
                    log(f"t{turn}: dismissed {npop} popup(s) during AI round")
                last_kick = time.time()
    log(f"t{turn}: TIMEOUT waiting for next turn")
    return None


def main():
    max_turns = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    log("=" * 60)
    log(f"play_to_end starting (max {max_turns} turns)")
    ready = ex(BUILDABLE_LUA, 3.0)
    log(f"buildable helper: {[l for l in ready if 'BRIDGE' in l]}")
    ready = ex(FOUNDSPOT_LUA, 3.0)
    log(f"foundspot helper: {[l for l in ready if 'BRIDGE' in l]}")
    ready = ex(DISTRICT_LUA, 3.0)
    log(f"district helper: {[l for l in ready if 'BRIDGE' in l]}")

    pol = load_policy()
    stalls = 0
    for i in range(max_turns):
        try:
            nt = play_turn(i, pol)
        except Exception as e:  # never die mid-campaign
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
