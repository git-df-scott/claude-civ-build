"""test_pending.py — in-game verification of the 3 items left pending by the
2026-07-17 static hardening pass:

  1. purchase        — PARAM_MILITARY_FORMATION_TYPE fix + FailureReasons surfacing
  2. settler tiles   — StateDump tile scan (pcall-guarded)
  3. set_production  — new CanStartOperation gate; REGRESSION RISK on DISTRICT_CAMPUS,
                       which auto-placed fine when ungated

Every check verifies an actual state change, never just ok=true — a bridge action
acking ok=true while silently doing nothing is the failure mode this project has
already been bitten by twice (found_city, purchase).

Run with the game in-game and the bridge injected.
"""
import json
import sys

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent.parent))

from driver import drain_lines, exec_lua, extract, run_action  # noqa: E402


def dump():
    """Force a state dump and return the local player's slice."""
    drain_lines()
    exec_lua("Bridge_DumpState()", 3.0)
    st = extract(drain_lines(), "BRIDGE_STATE:")
    if st is None:
        raise RuntimeError("no state dump returned")
    return st, next(p for p in st["players"] if p.get("isLocal"))


def city_by_id(loc, cid):
    return next((c for c in loc["cities"] if c["id"] == cid), None)


def valid_items(city_id):
    """Ask the engine which units this city can actually build / buy right now.

    Hardcoding a unit is a trap: UNIT_WARRIOR is obsolete by the mid-game, so a
    correct refusal looks exactly like a broken gate. Always test with something
    the engine agrees is legal.
    """
    lua = f"""
local city = CityManager.GetCity(Game.GetLocalPlayer(), {city_id})
local b, p = {{}}, {{}}
for row in GameInfo.Units() do
  local tp = {{}}
  tp[CityOperationTypes.PARAM_UNIT_TYPE] = row.Hash
  tp[CityOperationTypes.PARAM_INSERT_MODE] = CityOperationTypes.VALUE_EXCLUSIVE
  if CityManager.CanStartOperation(city, CityOperationTypes.BUILD, tp) then
    b[#b+1] = row.UnitType end
  local tq = {{}}
  tq[CityCommandTypes.PARAM_UNIT_TYPE] = row.Hash
  tq[CityCommandTypes.PARAM_MILITARY_FORMATION_TYPE] = MilitaryFormationTypes.STANDARD_MILITARY_FORMATION
  tq[CityCommandTypes.PARAM_YIELD_TYPE] = GameInfo.Yields["YIELD_GOLD"].Index
  if CityManager.CanStartCommand(city, CityCommandTypes.PURCHASE, true, tq, true) then
    p[#p+1] = row.UnitType end
end
print("BUILDABLE:"..table.concat(b, ","))
print("PURCHASABLE:"..table.concat(p, ","))
"""
    out = exec_lua(lua, 6.0)
    build, buy = [], []
    for line in out.get("output", []):
        if "BUILDABLE:" in line:
            build = line.split("BUILDABLE:")[1].strip().split(",")
        elif "PURCHASABLE:" in line:
            buy = line.split("PURCHASABLE:")[1].strip().split(",")
    # settlers/builders cost population or have odd rules — prefer a plain unit
    pref = lambda xs: next((x for x in xs if x not in
                            ("UNIT_SETTLER", "UNIT_BUILDER", "UNIT_TRADER")), xs[0] if xs else None)
    return pref(build), pref(buy)


RESULTS = []


def record(name, passed, detail):
    RESULTS.append((name, passed, detail))
    print(f"[{'PASS' if passed else 'FAIL'}] {name}\n       {detail}\n", flush=True)


def main():
    st, loc = dump()
    print(f"turn {st['turn']} | gold {loc['gold']} | "
          f"{len(loc['cities'])} cities | {len(loc['units'])} units\n", flush=True)

    cities = loc["cities"]
    if not cities:
        print("no cities — cannot test"); return 1

    # ---------------- ITEM 2: settler tile scan ----------------
    settlers = [u for u in loc["units"] if u["type"] == "UNIT_SETTLER"]
    if not settlers:
        record("item2/settler-tiles", False, "no settlers alive to test with")
    else:
        scanned = [u for u in settlers if "tiles" in u]
        if not scanned:
            record("item2/settler-tiles", False,
                   f"{len(settlers)} settlers, none carry a tiles array — pcall degraded")
        else:
            t = scanned[0]["tiles"]
            keys = sorted(t[0].keys()) if t else []
            owned = sum(1 for x in t if x.get("owner", -1) != -1)
            fresh = sum(1 for x in t if x.get("water"))
            record("item2/settler-tiles", True,
                   f"{len(scanned)}/{len(settlers)} settlers scanned; "
                   f"{len(t)} tiles on unit {scanned[0]['id']}; keys={keys}; "
                   f"{owned} owned, {fresh} fresh-water")
            # size cost: memory warned ~7 KB per settler
            per = len(json.dumps(scanned[0]["tiles"]))
            record("item2/dump-size", per < 20000,
                   f"tile payload {per} B/settler, total dump "
                   f"{len(json.dumps(st))} B (watch the tuner line cap)")

    # ---------------- ITEM 3: set_production gate ----------------
    target = cities[0]
    build_item, buy_item = valid_items(target["id"])
    print(f"engine says buildable={build_item!r} purchasable={buy_item!r}\n", flush=True)
    if not build_item or not buy_item:
        record("precondition/valid-items", False,
               f"engine offers nothing to test with (build={build_item}, buy={buy_item})")
        return 1

    # 3a. control: a plain unit must still queue (gate must not break the normal path)
    before = city_by_id(loc, target["id"]).get("production")
    res = run_action({"action": "set_production", "city_id": target["id"],
                      "item": build_item}, 901)
    _, loc2 = dump()
    after = city_by_id(loc2, target["id"]).get("production")
    record("item3a/set_production-unit",
           bool(res and res.get("ok")) and after != before,
           f"{target['name']}: prod {before!r} -> {after!r} | ack={res}")

    # 3b. THE REGRESSION CHECK: district must still be accepted through the gate
    #     (no plot param is passed; the engine auto-places). Try each city until
    #     one accepts — a city that already has a Campus will legitimately refuse.
    campus_detail, campus_ok = [], False
    for c in cities:
        b = city_by_id(loc2, c["id"]).get("production")
        r = run_action({"action": "set_production", "city_id": c["id"],
                        "item": "DISTRICT_CAMPUS"}, 902)
        _, l3 = dump()
        a = city_by_id(l3, c["id"]).get("production")
        campus_detail.append(f"{c['name']}: {b!r}->{a!r} ack={r and r.get('ok')} "
                             f"({r and r.get('detail')})")
        if r and r.get("ok") and a != b:
            campus_ok = True
            loc2 = l3
            break
        loc2 = l3
    record("item3b/set_production-DISTRICT_CAMPUS", campus_ok,
           " | ".join(campus_detail))

    # 3c. the gate must actually reject something un-buildable, with a reason
    r = run_action({"action": "set_production", "city_id": cities[0]["id"],
                    "item": "BUILDING_NOT_A_REAL_THING"}, 903)
    record("item3c/gate-rejects-bogus",
           bool(r) and not r.get("ok"),
           f"ack={r}")

    # ---------------- ITEM 1: purchase ----------------
    _, loc4 = dump()
    gold_before = loc4["gold"]
    units_before = len(loc4["units"])
    r = run_action({"action": "purchase", "city_id": cities[0]["id"],
                    "item": buy_item}, 904)
    _, loc5 = dump()
    gold_after = loc5["gold"]
    units_after = len(loc5["units"])
    bought = units_after > units_before and gold_after < gold_before
    record("item1/purchase-unit", bought,
           f"gold {gold_before}->{gold_after}, units {units_before}->{units_after} | ack={r}")
    if not bought and r and not r.get("ok"):
        # the whole point of the fix: a refusal must now explain itself
        detail = r.get("detail", "")
        record("item1/failure-reasons-surfaced", ":" in detail and len(detail) > 24,
               f"detail={detail!r}")

    print("=" * 66)
    for name, passed, _ in RESULTS:
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
    print("=" * 66)
    return 0 if all(p for _, p, _ in RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
