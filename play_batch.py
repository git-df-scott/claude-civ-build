"""play_batch.py — execute my per-turn policy for N turns, then stop for review.

Strategy (set by the session, reviewed between batches): expand to 4+ cities,
science-lean tech path, never let research/civics/production idle. State that
must survive between batches (queue positions, settle targets) lives in
civ_policy_state.json next to this file.
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

DAEMON = "http://127.0.0.1:8321"
POLICY_FILE = Path(__file__).parent / "civ_policy_state.json"

RESEARCH_QUEUE = [
    "TECH_ANIMAL_HUSBANDRY", "TECH_MINING", "TECH_POTTERY", "TECH_BRONZE_WORKING",
    "TECH_WRITING", "TECH_ARCHERY", "TECH_IRRIGATION", "TECH_MASONRY",
    "TECH_CURRENCY", "TECH_HORSEBACK_RIDING", "TECH_IRON_WORKING", "TECH_MATHEMATICS",
    "TECH_CONSTRUCTION", "TECH_ENGINEERING", "TECH_EDUCATION", "TECH_APPRENTICESHIP",
]
CIVIC_QUEUE = [
    "CIVIC_CODE_OF_LAWS", "CIVIC_CRAFTSMANSHIP", "CIVIC_FOREIGN_TRADE",
    "CIVIC_EARLY_EMPIRE", "CIVIC_STATE_WORKFORCE", "CIVIC_POLITICAL_PHILOSOPHY",
    "CIVIC_CURRENCY", "CIVIC_RECORDED_HISTORY",
]
# per-city positional build queues; "capital" for city id seen first, "new" for later cities
CAPITAL_QUEUE = ["UNIT_SETTLER", "UNIT_WARRIOR", "UNIT_SETTLER", "BUILDING_MONUMENT",
                 "UNIT_BUILDER", "DISTRICT_CAMPUS", "BUILDING_GRANARY", "UNIT_SETTLER",
                 "BUILDING_WALLS", "DISTRICT_COMMERCIAL_HUB"]
NEW_CITY_QUEUE = ["BUILDING_MONUMENT", "UNIT_BUILDER", "BUILDING_GRANARY",
                  "DISTRICT_CAMPUS", "BUILDING_WALLS"]
# settle targets: offsets from capital, tried in order — fallback only, used
# when the state dump carries no tile data (old mod version loaded)
SETTLE_OFFSETS = [(5, 2), (-5, -2), (4, -4), (-3, 5), (7, 0), (0, 6)]
HEADINGS = {"UNIT_SCOUT": (2, 1)}


def http(path, body=None, timeout=45):
    req = urllib.request.Request(DAEMON + path,
        json.dumps(body).encode() if body is not None else None,
        {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def ex(lua, wait=3.0, ctx="InGame"):
    return http("/exec", {"state": ctx, "lua": lua, "wait": wait}).get("output", [])


def cmd(d, wait=3.0):
    payload = json.dumps(d).replace('\\', '\\\\').replace('"', '\\"')
    out = ex(f'Bridge_Execute("{payload}")', wait)
    for l in out:
        if "BRIDGE_RESULT:" in l:
            return json.loads(l[l.find("BRIDGE_RESULT:") + 14:])
    return None


CACHED_STATE = None  # auto-dump captured during the end-turn wait loop


def get_state():
    global CACHED_STATE
    if CACHED_STATE is not None:
        st, CACHED_STATE = CACHED_STATE, None
        return st
    out = ex("Bridge_DumpState()", 4.0)
    for l in out:
        if "BRIDGE_STATE:" in l:
            return json.loads(l[l.find("BRIDGE_STATE:") + 13:])
    return None


def me_of(state):
    for p in state["players"]:
        if p.get("isLocal"):
            return p
    return None


def load_policy():
    if POLICY_FILE.exists():
        return json.loads(POLICY_FILE.read_text())
    return {"city_queues": {}, "settle_idx": 0, "capital_id": None, "capital_xy": None}


def save_policy(p):
    POLICY_FILE.write_text(json.dumps(p, indent=2))


def step_toward(ux, uy, tx, ty, span=2):
    dx = max(-span, min(span, tx - ux))
    dy = max(-span, min(span, ty - uy))
    return ux + dx, uy + dy


def play_turn(i, log, pol):
    state = get_state()
    if state is None:
        log.append("no state dump; skipping cycle")
        time.sleep(5)
        return None
    turn = state["turn"]
    me = me_of(state)

    # regression check (the FinishIdle bug cost ~100 turns unseen): if every
    # unit we ordered to move last turn is still exactly where it was, twice
    # in a row, something is eating orders — stop and surface it for review.
    prev = pol.get("last_positions") or {}
    if prev:
        now = {str(u["id"]): [u["x"], u["y"]] for u in me["units"]}
        unmoved = [uid for uid, xy in prev.items() if now.get(uid) == xy]
        pol["stall_count"] = pol.get("stall_count", 0) + 1 if len(unmoved) == len(prev) else 0
        if pol["stall_count"] >= 2:
            log.append(f"t{turn}: REGRESSION: no ordered unit moved for 2 turns — investigate FinishIdle/transport")
            save_policy(pol)
            return None
    moved_ids = set()  # units given a move order this turn

    # remember capital
    if pol["capital_id"] is None and me["cities"]:
        cap = me["cities"][0]
        pol["capital_id"] = cap["id"]
        pol["capital_xy"] = [cap["x"], cap["y"]]

    # research: queue first, else first available option (never idle)
    r = me.get("research", {})
    if not r.get("current") and r.get("options"):
        pick = next((t for t in RESEARCH_QUEUE if t in r["options"]), r["options"][0])
        log.append(f"t{turn}: research -> {pick}")
        cmd({"id": 900 + i, "action": "set_research", "tech": pick}, 2.0)
    c = me.get("civics", {})
    if not c.get("current") and c.get("options"):
        pick = next((cv for cv in CIVIC_QUEUE if cv in c["options"]), c["options"][0])
        log.append(f"t{turn}: civic -> {pick}")
        cmd({"id": 910 + i, "action": "set_civic", "civic": pick}, 2.0)

    # production: positional queue per city
    for city in me["cities"]:
        key = str(city["id"]) + "@" + str(city["x"]) + "," + str(city["y"])
        if key not in pol["city_queues"]:
            is_cap = city["id"] == pol["capital_id"] and [city["x"], city["y"]] == pol["capital_xy"]
            pol["city_queues"][key] = {"queue": (CAPITAL_QUEUE if is_cap else NEW_CITY_QUEUE)[:], "pos": 0}
        q = pol["city_queues"][key]
        if not city.get("production"):
            while q["pos"] < len(q["queue"]):
                item = q["queue"][q["pos"]]
                res = cmd({"id": 920 + i, "action": "set_production", "city_id": city["id"], "item": item})
                q["pos"] += 1
                if res and res.get("ok"):
                    log.append(f"t{turn}: {city['name']} builds {item}")
                    break
            else:
                # queue exhausted: repeatable fallback
                cmd({"id": 921 + i, "action": "set_production", "city_id": city["id"], "item": "UNIT_WARRIOR"})

    # settlers: walk to the settle target; found only when clear of own cities.
    # NOTE: found_city's ok=true only means "request accepted" — founding on/near
    # a city tile is silently ignored, so success = city count increased next turn.
    if len(me["cities"]) > pol.get("last_city_count", 0):
        if pol.get("last_city_count", 0) > 0:
            log.append(f"t{turn}: CITY COUNT NOW {len(me['cities'])}")
            pol["settle_idx"] += 1
    pol["last_city_count"] = len(me["cities"])
    for u in me["units"]:
        if u["type"] == "UNIT_SETTLER" and u["moves"] > 0 and pol["capital_xy"]:
            key = f"settler_{u['id']}"
            prevxy = pol.get(key)
            stuck = prevxy == [u["x"], u["y"]]
            pol[key] = [u["x"], u["y"]]
            min_city_dist = min(max(abs(u["x"] - ct["x"]), abs(u["y"] - ct["y"])) for ct in me["cities"])
            if stuck and min_city_dist >= 4:
                # can't reach target — settle right here if legal
                cmd({"id": 929 + i, "action": "found_city", "unit_id": u["id"]})
                pol["settle_idx"] += 1
                continue
            if stuck:
                pol["settle_idx"] += 1  # unreachable target; rotate
            # scored settle target from the dump's tile scan; blind offsets as fallback
            tx = ty = None
            cand = [t for t in u.get("tiles") or []
                    if t["owner"] == -1
                    and min(max(abs(t["x"] - ct["x"]), abs(t["y"] - ct["y"])) for ct in me["cities"]) >= 4]
            if cand:
                best = max(cand, key=lambda t: 2 * t["food"] + t["prod"] + (3 if t["water"] else 0))
                tx, ty = best["x"], best["y"]
                log.append(f"t{turn}: settle target ({tx},{ty}) f{best['food']}/p{best['prod']}" + ("/fresh" if best["water"] else ""))
            else:
                off = SETTLE_OFFSETS[pol["settle_idx"] % len(SETTLE_OFFSETS)]
                tx, ty = pol["capital_xy"][0] + off[0], pol["capital_xy"][1] + off[1]
            at_target = abs(u["x"] - tx) <= 1 and abs(u["y"] - ty) <= 1
            if at_target and min_city_dist >= 4:
                cmd({"id": 930 + i, "action": "found_city", "unit_id": u["id"]})
            elif at_target:
                pol["settle_idx"] += 1
            else:
                r = cmd({"id": 931 + i, "action": "move_unit", "unit_id": u["id"], "x": tx, "y": ty})
                if r and r.get("ok"):
                    moved_ids.add(u["id"])
                elif not cand:
                    pol["settle_idx"] += 1  # blind target not pathable; next

    # spend gold: buy a settler (or builder) in the capital when rich
    if me["gold"] > 500 and pol.get("capital_id"):
        r = cmd({"id": 935 + i, "action": "purchase", "city_id": pol["capital_id"], "item": "UNIT_SETTLER"})
        if r and r.get("ok"):
            log.append(f"t{turn}: PURCHASED SETTLER (gold {me['gold']})")
        else:
            # surface FailureReasons (now emitted by the Lua handler) once per distinct reason
            why = f"purchase failed: {(r or {}).get('detail')}"
            if not any(l.endswith(why) for l in log):
                log.append(f"t{turn}: {why}")
            if me["gold"] > 700:
                r2 = cmd({"id": 936 + i, "action": "purchase", "city_id": pol["capital_id"], "item": "UNIT_BUILDER"})
                if r2 and r2.get("ok"):
                    log.append(f"t{turn}: PURCHASED BUILDER")

    # military: warriors guard home turf; scouts keep exploring
    for u in me["units"]:
        if u["moves"] <= 0:
            continue
        if u["type"] == "UNIT_WARRIOR" and pol["capital_xy"]:
            cx, cy = pol["capital_xy"]
            if max(abs(u["x"] - cx), abs(u["y"] - cy)) > 6:
                r = cmd({"id": 940 + i, "action": "move_unit", "unit_id": u["id"], "x": cx, "y": cy})
                if r and r.get("ok"):
                    moved_ids.add(u["id"])
        elif u["type"] == "UNIT_SCOUT":
            h = HEADINGS["UNIT_SCOUT"]
            res = cmd({"id": 941 + i, "action": "move_unit", "unit_id": u["id"], "x": u["x"] + h[0], "y": u["y"] + h[1]})
            if not (res and res.get("ok")):
                res = cmd({"id": 942 + i, "action": "move_unit", "unit_id": u["id"], "x": u["x"], "y": u["y"] + 2})
            if res and res.get("ok"):
                moved_ids.add(u["id"])

    # snapshot ordered units for next turn's regression check
    pol["last_positions"] = {str(u["id"]): [u["x"], u["y"]] for u in me["units"] if u["id"] in moved_ids}
    save_policy(pol)

    # let issued MOVE_TO orders actually execute before zeroing moves —
    # FinishIdle right after move commands cancels them (units barely moved
    # for ~100 turns until this pause was added).
    time.sleep(6)

    # end turn — insist
    ex("Bridge_FinishIdle(0)", 2.0, "GameCore_Tuner")
    cmd({"id": 950 + i, "action": "end_turn"}, 2.0)
    deadline = time.time() + 120
    last_kick = time.time()
    global CACHED_STATE
    while time.time() < deadline:
        time.sleep(2)
        out = ex('print("T="..Game.GetCurrentGameTurn().." A="..tostring(Players[0]:IsTurnActive()))', 1.5)
        # the mod auto-dumps on LocalPlayerTurnBegin; if the dump for the next
        # turn shows up in this window, the turn has started — reuse it and
        # skip next cycle's explicit Bridge_DumpState() round-trip.
        for l in out:
            if "BRIDGE_STATE:" in l:
                try:
                    st = json.loads(l[l.find("BRIDGE_STATE:") + 13:])
                except ValueError:
                    continue
                if st.get("turn") == turn + 1:
                    CACHED_STATE = st
                    return turn + 1
        line = next((l for l in out if "T=" in l), "")
        if f"T={turn + 1}" in line and "A=true" in line:
            return turn + 1
        if "A=true" in line and time.time() - last_kick > 20:
            cmd({"id": 960 + i, "action": "clear_diplo"}, 1.5)
            ex("Bridge_FinishIdle(0)", 1.5, "GameCore_Tuner")
            cmd({"id": 961 + i, "action": "end_turn"}, 1.5)
            last_kick = time.time()
        elif "A=false" in line:
            cmd({"id": 962 + i, "action": "clear_diplo"}, 1.5)
    log.append(f"t{turn}: TIMEOUT waiting for next turn")
    return None


def main(n_turns):
    log = []
    pol = load_policy()
    for i in range(n_turns):
        nt = play_turn(i, log, pol)
        if nt is None:
            break
        print(f"now at turn {nt}", flush=True)
    print("---- batch log ----")
    for l in log:
        print(l)
    st = get_state()
    if st:
        me = me_of(st)
        print("---- state ----")
        print(f"turn {st['turn']}, gold {me['gold']}, cities {[(c['name'], c['population'], c.get('production')) for c in me['cities']]}")
        print(f"units {[(u['type'], u['x'], u['y'], u['damage']) for u in me['units']]}")
        print(f"research {me.get('research',{}).get('current')} options {me.get('research',{}).get('options')}")
        print(f"civic {me.get('civics',{}).get('current')}")
        others = [(p['id'], len(p['cities']), len(p['units'])) for p in st['players'] if not p.get('isLocal')]
        print(f"rivals (id,cities,units): {others}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 10)
