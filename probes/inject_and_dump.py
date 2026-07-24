"""Inject the bridge Lua into the running game and print the first state dump.

Validates the whole chain (tuner -> InGame ctx -> mod Lua -> state JSON) before
the campaign runner depends on it.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from driver import inject_bridge  # noqa: E402
from play_batch import get_state  # noqa: E402

inject_bridge()

st = get_state()
if st is None:
    sys.exit("no state dump")

print("\n=== state keys ===", sorted(st))
print("turn:", st.get("turn"))
me = next(p for p in st["players"] if p.get("isLocal"))
print("\n=== me ===")
print("  keys:", sorted(me))
print("  gold:", me.get("gold"), " cities:", len(me.get("cities", [])),
      " units:", len(me.get("units", [])))
print("  research:", json.dumps(me.get("research", {}))[:300])
print("  civics:", json.dumps(me.get("civics", {}))[:300])
for u in me.get("units", []):
    print("  UNIT", {k: v for k, v in u.items() if k != "tiles"})
for c in me.get("cities", []):
    print("  CITY", {k: v for k, v in c.items()})

print("\n=== other players ===")
for p in st["players"]:
    if not p.get("isLocal"):
        print("  ", {k: v for k, v in p.items() if k not in ("units", "cities")},
              "cities:", len(p.get("cities", [])), "units:", len(p.get("units", [])))
