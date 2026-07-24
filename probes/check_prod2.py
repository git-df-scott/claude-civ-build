"""Per-city production, printed one city per exec so the console-capture race
cannot swallow the later lines (check_prod.py kept losing all but the first)."""
import json
import urllib.request

D = "http://127.0.0.1:8321"


def ex(lua, ctx="InGame", wait=3.0):
    b = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=90)).get("output", [])


def run(lua, tries=4):
    for _ in range(tries):
        out = [l.split("Q:", 1)[1].strip() for l in ex(lua) if "Q:" in l]
        out = [o for o in out if o not in ("START", "END")]
        if out:
            return out
    return []


NAME_FN = '''
local function nameOfHash(h)
  if h == 0 then return "IDLE" end
  for r in GameInfo.Units() do if r.Hash == h then return r.UnitType end end
  for r in GameInfo.Buildings() do if r.Hash == h then return r.BuildingType end end
  for r in GameInfo.Districts() do if r.Hash == h then return r.DistrictType end end
  return "hash:"..tostring(h)
end
'''

n = run('print("Q:START") local c=0 for _,x in Players[Game.GetLocalPlayer()]:GetCities():Members() do c=c+1 end print("Q:n="..c) print("Q:END")')
print(" ", n)
count = 0
for line in n:
    if line.startswith("n="):
        count = int(line.split("=")[1])

for i in range(count):
    out = run(f'''
print("Q:START")
{NAME_FN}
local k = 0
for _, c in Players[Game.GetLocalPlayer()]:GetCities():Members() do
  if k == {i} then
    local q = c:GetBuildQueue()
    print("Q:"..tostring(c:GetName()).." pop="..c:GetPopulation()
      .." prod="..string.format("%.1f", c:GetYield(YieldTypes.YIELD_PRODUCTION))
      .." building="..nameOfHash(q:GetCurrentProductionTypeHash()))
  end
  k = k + 1
end
print("Q:END")
''')
    for l in out:
        print("  ", l)
