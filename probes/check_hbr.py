"""Why isn't Horseback Riding being picked? Check its prereqs and availability,
plus the capital's actual production/yields."""
import json
import urllib.request

D = "http://127.0.0.1:8321"


def ex(lua, ctx="InGame", wait=3.5):
    b = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=120)).get("output", [])


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
local techs = Players[pid]:GetTechs()
local row = GameInfo.Technologies["TECH_HORSEBACK_RIDING"]
print("H:HBR_index="..tostring(row and row.Index))
print("H:HBR_canresearch="..tostring(row and techs:CanResearch(row.Index)))
print("H:HBR_has="..tostring(row and techs:HasTech(row.Index)))
local ah = GameInfo.Technologies["TECH_ANIMAL_HUSBANDRY"]
print("H:AH_has="..tostring(ah and techs:HasTech(ah.Index)))
for r2 in GameInfo.TechnologyPrereqs() do
  if r2.Technology == "TECH_HORSEBACK_RIDING" then
    print("H:HBR_prereq="..tostring(r2.PrereqTech))
  end
end
local cur = techs:GetResearchingTech()
print("H:current="..tostring(cur >= 0 and GameInfo.Technologies[cur].TechnologyType or "IDLE"))
local avail = {}
for r3 in GameInfo.Technologies() do
  if techs:CanResearch(r3.Index) then avail[#avail+1] = r3.TechnologyType end
end
print("H:available="..table.concat(avail, ","))
local p = Players[pid]
for _, c in p:GetCities():Members() do
  local q = c:GetBuildQueue()
  print("H:CITY pop="..c:GetPopulation()
    .." prodhash="..tostring(q:GetCurrentProductionTypeHash())
    .." food="..string.format("%.1f", c:GetYield(YieldTypes.YIELD_FOOD))
    .." prod="..string.format("%.1f", c:GetYield(YieldTypes.YIELD_PRODUCTION)))
end
print("H:END")
'''):
    print("  ", l)
