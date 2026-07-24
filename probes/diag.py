import json
import urllib.request

D = "http://127.0.0.1:8321"

st = json.load(urllib.request.urlopen(D + "/states", timeout=30))
print("connected:", st["connected"], "nstates:", len(st["states"]))
print("Lobby idx:", st["states"].get("Lobby"), " InGame idx:", st["states"].get("InGame"))
print("states:", sorted(st["states"])[:40])


def ex(lua, ctx="Lobby", wait=2.0):
    b = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=60))


print("\nA plain print:", ex('print("NG:hello")'))
print("\nB getvalue   :", ex('print("NG:h="..tostring(GameConfiguration.GetValue("GAME_HANDICAP")))'))
print("\nC settodefaults:", ex('local ok,err = pcall(function() GameConfiguration.SetToDefaults() end) print("NG:sd_ok="..tostring(ok).." err="..tostring(err))'))
