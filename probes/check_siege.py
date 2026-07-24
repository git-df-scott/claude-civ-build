"""What siege / anti-wall options do we have, and what can our cities build now?
Ranged units cannot reduce city HP while Outer Defenses stand, so a walled city
needs siege units or melee. Find the real unlock path from the engine."""
import json
import urllib.request

D = "http://127.0.0.1:8321"


def ex(lua, ctx="InGame", wait=4.5):
    b = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=150)).get("output", [])


def run(lua, tries=4):
    for _ in range(tries):
        out = [l.split("Z:", 1)[1].strip() for l in ex(lua) if "Z:" in l]
        out = [o for o in out if o not in ("START", "END")]
        if out:
            return out
    return []


print("--- siege-capable / support units in this ruleset ---")
for l in run('''
print("Z:START")
for r in GameInfo.Units() do
  local t = tostring(r.UnitType)
  local cls = tostring(r.PromotionClass)
  if cls == "PROMOTION_CLASS_SIEGE" or cls == "PROMOTION_CLASS_SUPPORT"
     or string.find(t, "CATAPULT") or string.find(t, "RAM") or string.find(t, "SIEGE_TOWER") then
    print("Z:U "..t.." class="..cls.." tech="..tostring(r.PrereqTech)
      .." cost="..tostring(r.Cost))
  end
end
print("Z:END")
''')[:25]:
    print("  ", l)

print("\n--- what the capital can build RIGHT NOW ---")
for l in run('''
print("Z:START")
local pid = Game.GetLocalPlayer()
for _, c in Players[pid]:GetCities():Members() do
  local names = {}
  for r in GameInfo.Units() do
    local tp = {}
    tp[CityOperationTypes.PARAM_UNIT_TYPE] = r.Hash
    tp[CityOperationTypes.PARAM_INSERT_MODE] = CityOperationTypes.VALUE_EXCLUSIVE
    local ok = false
    pcall(function() ok = CityManager.CanStartOperation(c, CityOperationTypes.BUILD, tp) end)
    if ok then names[#names+1] = tostring(r.UnitType) end
  end
  print("Z:"..tostring(c:GetName()).." => "..table.concat(names, ","))
  break
end
local t = Players[pid]:GetTechs()
for _, n in ipairs({"TECH_BRONZE_WORKING","TECH_MASONRY","TECH_ENGINEERING","TECH_MATHEMATICS"}) do
  local row = GameInfo.Technologies[n]
  if row then
    print("Z:TECH "..n.." has="..tostring(t:HasTech(row.Index))
      .." can="..tostring(t:CanResearch(row.Index)))
  end
end
print("Z:END")
''')[:20]:
    print("  ", l)
