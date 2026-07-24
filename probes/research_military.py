"""Engine-authoritative military research: which policy cards exist, what unlocks
them, and how Scythia's units are actually classified.

Wiki guides drift between game versions; the live DB is the source of truth.
Read-only.
"""
import json
import urllib.request

D = "http://127.0.0.1:8321"


def ex(lua, ctx="InGame", wait=3.0):
    b = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=120)).get("output", [])


def run(label, lua, ctx="InGame", wait=3.0, tries=3):
    for _ in range(tries):
        out = [l.split("M:", 1)[1].strip() for l in ex(lua, ctx, wait) if "M:" in l]
        out = [o for o in out if o not in ("START", "END")]
        if out:
            print(f"\n### {label}")
            for o in out:
                print("   ", o)
            return out
    print(f"\n### {label}\n    (no output)")
    return []


# Scythia's units: what class are they, what tech unlocks them, what do they cost?
run("Scythia unique + cavalry units", '''
print("M:START")
for _, n in ipairs({"UNIT_SCYTHIA_SAKA_HORSE_ARCHER","UNIT_HORSEMAN","UNIT_HEAVY_CHARIOT","UNIT_WARRIOR","UNIT_ARCHER","UNIT_SLINGER","UNIT_SETTLER","UNIT_BUILDER"}) do
  local u = GameInfo.Units[n]
  if u then
    print("M:UNIT "..n.." cost="..tostring(u.Cost)
      .." tech="..tostring(u.PrereqTech)
      .." class="..tostring(u.PromotionClass)
      .." cs="..tostring(u.Combat).." rcs="..tostring(u.RangedCombat)
      .." rng="..tostring(u.Range).." move="..tostring(u.BaseMoves))
  else
    print("M:UNIT "..n.." MISSING")
  end
end
print("M:END")
''')

# Every military policy card the ruleset actually has, with its unlocking civic.
run("military policy cards + unlock civic", '''
print("M:START")
for row in GameInfo.Policies() do
  local slot = tostring(row.GovernmentSlotType)
  if slot == "SLOT_MILITARY" then
    print("M:POL "..tostring(row.PolicyType).." civic="..tostring(row.PrereqCivic))
  end
end
print("M:END")
''', wait=4.0)

# Which policies are unlocked RIGHT NOW, and what slots does our government have?
run("current government + available policies", '''
print("M:START")
local pid = Game.GetLocalPlayer()
local culture = Players[pid]:GetCulture()
print("M:gov="..tostring(culture:GetCurrentGovernment()))
local n = 0
for row in GameInfo.Policies() do
  if culture:IsPolicyUnlocked(row.Index) then
    n = n + 1
    print("M:UNLOCKED "..tostring(row.PolicyType).." slot="..tostring(row.GovernmentSlotType))
  end
end
print("M:unlocked_count="..tostring(n))
print("M:END")
''', wait=4.0)

# Early civics: what is available to research now (policy cards come from civics).
run("civic options now", '''
print("M:START")
local pid = Game.GetLocalPlayer()
local culture = Players[pid]:GetCulture()
print("M:current_civic="..tostring(culture:GetProgressingCivic()))
for row in GameInfo.Civics() do
  if culture:CanProgress(row.Index) then
    print("M:CIVIC_AVAIL "..tostring(row.CivicType))
  end
end
print("M:END")
''', wait=4.0)

# Early techs available now.
run("tech options now", '''
print("M:START")
local pid = Game.GetLocalPlayer()
local techs = Players[pid]:GetTechs()
print("M:current_tech="..tostring(techs:GetResearchingTech()))
for row in GameInfo.Technologies() do
  if techs:CanResearch(row.Index) then
    print("M:TECH_AVAIL "..tostring(row.TechnologyType))
  end
end
print("M:END")
''', wait=4.0)
