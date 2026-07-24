import json
import urllib.request

D = "http://127.0.0.1:8321"


def ex(lua, ctx="InGame", wait=3.0):
    b = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=90)).get("output", [])


for _ in range(3):
    out = ex('''
print("C:turn="..Game.GetCurrentGameTurn())
print("C:active="..tostring(Players[0]:IsTurnActive()))
for _, n in ipairs({"Bridge_Execute","Bridge_DumpState","Bridge_Enemies","Bridge_WarStep",
                    "Bridge_AutoPolicy","Bridge_ActivePolicies","Bridge_Buildable","Bridge_FoundSpot"}) do
  print("C:"..n.."="..type(_G[n]))
end
local p = Players[0]
local nc, nu = 0, 0
for _, c in p:GetCities():Members() do nc = nc + 1 end
for _, u in p:GetUnits():Members() do nu = nu + 1 end
print("C:cities="..nc.." units="..nu.." gold="..math.floor(p:GetTreasury():GetGoldBalance()))
''')
    got = [l.split("C:", 1)[1].strip() for l in out if "C:" in l]
    if got:
        for g in got:
            print("  ", g)
        break
else:
    print("  no output")
