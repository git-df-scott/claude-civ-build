"""Round 2: find Scythia's real unique-unit id and read the actual policy effects."""
import json
import urllib.request

D = "http://127.0.0.1:8321"


def ex(lua, ctx="InGame", wait=3.5):
    b = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=120)).get("output", [])


def run(label, lua, wait=3.5, tries=3):
    for _ in range(tries):
        out = [l.split("M:", 1)[1].strip() for l in ex(lua, wait=wait) if "M:" in l]
        out = [o for o in out if o not in ("START", "END")]
        if out:
            print(f"\n### {label}")
            for o in out:
                print("   ", o)
            return out
    print(f"\n### {label}\n    (no output)")
    return []


run("units whose id mentions SAKA / SCYTHIA / HORSE", '''
print("M:START")
for row in GameInfo.Units() do
  local t = tostring(row.UnitType)
  if string.find(t, "SAKA") or string.find(t, "SCYTHIA") or string.find(t, "HORSE") then
    print("M:U "..t.." cost="..tostring(row.Cost).." tech="..tostring(row.PrereqTech)
      .." class="..tostring(row.PromotionClass).." cs="..tostring(row.Combat)
      .." rcs="..tostring(row.RangedCombat).." rng="..tostring(row.Range)
      .." move="..tostring(row.BaseMoves).." replaces="..tostring(row.TraitType))
  end
end
print("M:END")
''', wait=5.0)

run("early military policy effects (description text)", '''
print("M:START")
for _, n in ipairs({"POLICY_MANEUVER","POLICY_AGOGE","POLICY_DISCIPLINE","POLICY_SURVEY",
                    "POLICY_CONSCRIPTION","POLICY_VETERANCY","POLICY_RAID","POLICY_PROFESSIONAL_ARMY"}) do
  local p = GameInfo.Policies[n]
  if p then
    print("M:P "..n.." | "..tostring(Locale.Lookup(p.Description or "")))
  end
end
print("M:END")
''', wait=5.0)

run("governments and their slots", '''
print("M:START")
for row in GameInfo.Governments() do
  print("M:GOV "..tostring(row.GovernmentType).." civic="..tostring(row.PrereqCivic))
end
print("M:END")
''', wait=4.0)

run("our start: capital site yields + nearby horses", '''
print("M:START")
local pid = Game.GetLocalPlayer()
local p = Players[pid]
local n = 0
for _, u in p:GetUnits():Members() do
  n = n + 1
  print("M:MYUNIT "..tostring(u:GetType()).." id="..tostring(u:GetID())
        .." at "..tostring(u:GetX())..","..tostring(u:GetY()))
end
print("M:unit_count="..tostring(n))
local w,h = Map.GetGridSize()
print("M:gridsize="..tostring(w).."x"..tostring(h))
print("M:END")
''', wait=4.0)
