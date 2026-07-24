import json
import urllib.request

D = "http://127.0.0.1:8321"


def ex(lua, ctx="InGame", wait=4.0):
    b = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=120)).get("output", [])


def run(lua, tries=4):
    for _ in range(tries):
        out = [l.split("U:", 1)[1].strip() for l in ex(lua) if "U:" in l]
        out = [o for o in out if o not in ("START", "END")]
        if out:
            return out
    return []


for l in run('''
print("U:START")
local pid = Game.GetLocalPlayer()
local p = Players[pid]
for _, u in p:GetUnits():Members() do
  local info = GameInfo.Units[u:GetType()]
  print("U:UNIT "..(info and info.UnitType or "?").." id="..u:GetID()
        .." at "..u:GetX()..","..u:GetY()
        .." moves="..u:GetMovesRemaining())
end
for _, c in p:GetCities():Members() do
  print("U:CITY "..c:GetX()..","..c:GetY().." pop="..c:GetPopulation()
        .." food="..string.format("%.1f", c:GetYield(YieldTypes.YIELD_FOOD)))
end
print("U:END")
'''):
    print("  ", l)
