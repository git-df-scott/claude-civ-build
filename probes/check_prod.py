"""What is each city actually building, and is a Settler even legal right now?"""
import json
import urllib.request

D = "http://127.0.0.1:8321"


def ex(lua, ctx="InGame", wait=4.0):
    b = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=120)).get("output", [])


def run(lua, tries=4):
    for _ in range(tries):
        out = [l.split("P:", 1)[1].strip() for l in ex(lua) if "P:" in l]
        out = [o for o in out if o not in ("START", "END")]
        if out:
            return out
    return []


for l in run('''
print("P:START")
local pid = Game.GetLocalPlayer()
local p = Players[pid]
local function nameOfHash(h)
  for r in GameInfo.Units() do if r.Hash == h then return r.UnitType end end
  for r in GameInfo.Buildings() do if r.Hash == h then return r.BuildingType end end
  for r in GameInfo.Districts() do if r.Hash == h then return r.DistrictType end end
  return "hash:"..tostring(h)
end
for _, c in p:GetCities():Members() do
  local q = c:GetBuildQueue()
  local h = q:GetCurrentProductionTypeHash()
  print("P:CITY "..tostring(c:GetName()).." pop="..c:GetPopulation()
        .." building="..(h ~= 0 and nameOfHash(h) or "IDLE"))
  -- is a settler legal here right now?
  local tp = {}
  tp[CityOperationTypes.PARAM_UNIT_TYPE] = GameInfo.Units["UNIT_SETTLER"].Hash
  tp[CityOperationTypes.PARAM_INSERT_MODE] = CityOperationTypes.VALUE_EXCLUSIVE
  print("P:settler_buildable="..tostring(CityManager.CanStartOperation(c, CityOperationTypes.BUILD, tp)))
  local tp2 = {}
  tp2[CityOperationTypes.PARAM_UNIT_TYPE] = GameInfo.Units["UNIT_SETTLER"].Hash
  tp2[CityOperationTypes.PARAM_YIELD_TYPE] = GameInfo.Yields["YIELD_GOLD"].Index
  local can, res = CityManager.CanStartCommand(c, CityCommandTypes.PURCHASE, false, tp2, true)
  print("P:settler_purchase_can="..tostring(can))
end
print("P:gold="..math.floor(p:GetTreasury():GetGoldBalance()))
print("P:END")
'''):
    print("  ", l)
