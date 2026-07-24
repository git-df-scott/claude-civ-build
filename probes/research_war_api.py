"""Find the real API for (a) declaring war and (b) slotting policy cards.

The bridge has no handler for either, and both are essential to a domination
plan. Civ 6 splits its API across the UI (InGame) and gameplay (GameCore_Tuner)
contexts with non-overlapping surfaces, so probe BOTH. Read-only: this only
reports what exists, it does not declare anything.
"""
import json
import urllib.request

D = "http://127.0.0.1:8321"


def ex(lua, ctx, wait=3.0):
    b = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=120)).get("output", [])


def run(label, lua, ctx, wait=3.0, tries=3):
    for _ in range(tries):
        out = [l.split("W:", 1)[1].strip() for l in ex(lua, ctx, wait) if "W:" in l]
        out = [o for o in out if o not in ("START", "END")]
        if out:
            print(f"\n### {label}  [{ctx}]")
            for o in out:
                print("   ", o)
            return out
    print(f"\n### {label}  [{ctx}]\n    (no output)")
    return []


WAR_SURFACE = '''
print("W:START")
local pid = Game.GetLocalPlayer()
print("W:DiplomacyManager="..type(DiplomacyManager))
if type(DiplomacyManager) == "table" then
  for _, m in ipairs({"RequestSession","AddSession","CloseSession","IsSessionIDOpen"}) do
    print("W:DM."..m.."="..type(DiplomacyManager[m]))
  end
end
local p = Players[pid]
print("W:GetDiplomacy="..type(p.GetDiplomacy))
if p.GetDiplomacy then
  local d = p:GetDiplomacy()
  for _, m in ipairs({"DeclareWar","IsAtWarWith","CanDeclareWar","GetDiplomaticState","HasMet"}) do
    print("W:DIP."..m.."="..type(d[m]))
  end
end
print("W:PlayerOperations="..type(PlayerOperations))
if type(PlayerOperations) == "table" then
  print("W:PO.DIPLOMACY_DECLARE_WAR="..tostring(PlayerOperations.DIPLOMACY_DECLARE_WAR))
end
print("W:UI="..type(UI))
if type(UI) == "table" then print("W:UI.RequestPlayerOperation="..type(UI.RequestPlayerOperation)) end
print("W:END")
'''

POLICY_SURFACE = '''
print("W:START")
local pid = Game.GetLocalPlayer()
local c = Players[pid]:GetCulture()
print("W:GetCulture="..type(c))
for _, m in ipairs({"GetCurrentGovernment","IsPolicyUnlocked","CanChangeGovernmentAtAll",
                    "GetNumPolicySlots","GetSlotType","GetPolicyInSlot","SetGovernmentAndPolicies",
                    "RequestPolicyChange","ChangePolicy","GetNumPolicySlotsForType"}) do
  print("W:CUL."..m.."="..type(c[m]))
end
print("W:PlayerOperations="..type(PlayerOperations))
if type(PlayerOperations) == "table" then
  for _, k in ipairs({"CHANGE_GOVERNMENT","PARAM_POLICY_ADD","PARAM_POLICY_REMOVE",
                      "PARAM_GOVERNMENT_TYPE"}) do
    print("W:PO."..k.."="..tostring(PlayerOperations[k]))
  end
end
print("W:END")
'''

for ctx in ("InGame", "GameCore_Tuner"):
    run("war API surface", WAR_SURFACE, ctx)
    run("policy API surface", POLICY_SURFACE, ctx)
