"""Is the Python hexdist() used for massing/targeting consistent with the
engine's Map.GetPlotDistance? If not, the massing gate can never open and
target selection has been scoring the wrong cities all game."""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from win_domination import hexdist  # noqa: E402

D = "http://127.0.0.1:8321"
PAIRS = [(18, 20, 19, 20), (17, 21, 19, 20), (18, 28, 19, 20),
         (16, 33, 19, 20), (12, 35, 19, 20), (19, 30, 19, 20),
         (13, 31, 15, 23)]


def ex(lua, wait=4.0):
    b = json.dumps({"state": "InGame", "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=120)).get("output", [])


calls = "\n".join(
    f'print("H:{a},{b},{c},{d}="..Map.GetPlotDistance({a},{b},{c},{d}))'
    for a, b, c, d in PAIRS)

for _ in range(4):
    out = [l.split("H:", 1)[1].strip() for l in ex(calls) if "H:" in l]
    if out:
        print(f"{'pair':<22}{'engine':>8}{'python':>8}   match")
        for line in out:
            key, val = line.split("=")
            a, b, c, d = (int(v) for v in key.split(","))
            eng = int(val)
            py = hexdist(a, b, c, d)
            print(f"({a},{b})->({c},{d})".ljust(22)
                  + str(eng).rjust(8) + str(py).rjust(8)
                  + ("   OK" if eng == py else "   *** MISMATCH ***"))
        break
else:
    print("no output")
