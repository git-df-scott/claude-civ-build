"""Can we put 18 idle Builders to work? Our production base is the binding
constraint on the whole campaign and these units have never been given an order.
Look for engine-side automation first (cheapest), then the manual op."""
import json
import urllib.request

D = "http://127.0.0.1:8321"


def ex(lua, ctx="InGame", wait=4.0):
    b = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=120)).get("output", [])


def run(lua, tries=4):
    for _ in range(tries):
        out = [l.split("B:", 1)[1].strip() for l in ex(lua) if "B:" in l]
        out = [o for o in out if o not in ("START", "END")]
        if out:
            return out
    return []


for l in run('''
print("B:START")
print("B:AutomateTypes="..type(AutomateTypes))
if type(AutomateTypes) == "table" then
  for k, v in pairs(AutomateTypes) do print("B:AUTO "..tostring(k).."="..tostring(v)) end
end
print("B:PARAM_DIRECTIVE="..tostring(UnitOperationTypes.PARAM_DIRECTIVE))
print("B:BUILD_IMPROVEMENT="..tostring(UnitOperationTypes.BUILD_IMPROVEMENT))
local pid = Game.GetLocalPlayer()
local n = 0
for _, u in Players[pid]:GetUnits():Members() do
  local info = GameInfo.Units[u:GetType()]
  if info and info.UnitType == "UNIT_BUILDER" then
    n = n + 1
    if n == 1 then
      print("B:first_builder at "..u:GetX()..","..u:GetY()
            .." charges="..tostring(u:GetBuildCharges()))
      local can = false
      pcall(function()
        can = UnitManager.CanStartCommand(u, UnitCommandTypes.AUTOMATE, nil)
      end)
      print("B:can_automate_nil_params="..tostring(can))
    end
  end
end
print("B:builders="..n)
print("B:END")
'''):
    print("  ", l)
