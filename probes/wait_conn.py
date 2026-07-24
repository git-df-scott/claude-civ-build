"""Poll the daemon until the tuner reconnects (or give up), printing state changes.

The daemon's connect loop redials 4318 every 0.5s. If the game is merely mid-load,
the listener re-opens and this returns quickly. If the listener is truly dead,
nothing changes and only a game restart recovers it.
"""
import json
import sys
import time
import urllib.request

D = "http://127.0.0.1:8321"
LIMIT = float(sys.argv[1]) if len(sys.argv) > 1 else 120.0

last = None
t0 = time.time()
while time.time() - t0 < LIMIT:
    try:
        st = json.load(urllib.request.urlopen(D + "/states", timeout=30))
    except OSError as e:
        print(f"[{time.time()-t0:5.1f}s] daemon unreachable: {e}")
        time.sleep(3)
        continue
    key = (st["connected"], len(st["states"]))
    if key != last:
        names = sorted(st["states"])
        print(f"[{time.time()-t0:5.1f}s] connected={st['connected']} n={len(st['states'])}")
        print(f"          {names if len(names) <= 12 else names[:12] + ['...']}")
        last = key
    if st["connected"] and "InGame" in st["states"]:
        print("  -> IN GAME, full state set available.")
        break
    time.sleep(2)
else:
    print("  -> gave up waiting.")
