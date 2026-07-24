"""Do we actually HAVE horses? Horseman and the Saka both require the Horses
strategic resource — without it the entire domination plan is unbuildable and
needs to change. Also: what can each city legally build right now?"""
import json
import urllib.request

D = "http://127.0.0.1:8321"


def ex(lua, ctx="InGame", wait=5.0):
    b = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=150)).get("output", [])


def run(lua, tries=4):
    for _ in range(tries):
        out = [l.split("H:", 1)[1].strip() for l in ex(lua) if "H:" in l]
        out = [o for o in out if o not in ("START", "END")]
        if out:
            return out
    return []


for l in run('''
print("H:START")
local pid = Game.GetLocalPlayer()
local p = Players[pid]
local t = p:GetTechs()
print("H:has_HBR="..tostring(t:HasTech(GameInfo.Technologies["TECH_HORSEBACK_RIDING"].Index)))
local res = p:GetResources()
for _, n in ipairs({"RESOURCE_HORSES","RESOURCE_IRON","RESOURCE_NITER"}) do
  local row = GameInfo.Resources[n]
  if row then
    local amt, has = -1, false
    pcall(function() amt = res:GetResourceAmount(row.Index) end)
    pcall(function() has = res:HasResource(row.Index) end)
    print("H:RES "..n.." amount="..tostring(amt).." has="..tostring(has))
  end
end
for _, c in p:GetCities():Members() do
  local names = {}
  for _, un in ipairs({"UNIT_HORSEMAN","UNIT_SCYTHIAN_HORSE_ARCHER","UNIT_ARCHER",
                       "UNIT_SETTLER","UNIT_WARRIOR","UNIT_SLINGER","UNIT_BUILDER"}) do
    local row = GameInfo.Units[un]
    local tp = {}
    tp[CityOperationTypes.PARAM_UNIT_TYPE] = row.Hash
    tp[CityOperationTypes.PARAM_INSERT_MODE] = CityOperationTypes.VALUE_EXCLUSIVE
    local ok = CityManager.CanStartOperation(c, CityOperationTypes.BUILD, tp)
    if ok then names[#names+1] = un end
  end
  print("H:CITY "..tostring(c:GetName()).." pop="..c:GetPopulation()
        .." canbuild="..table.concat(names, ","))
end
print("H:END")
'''):
    print("  ", l)
