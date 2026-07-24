"""Does the engine expose an auto-explore operation? If so, exploration becomes
one call per unit instead of hand-rolled pathing."""
import json
import urllib.request

D = "http://127.0.0.1:8321"


def ex(lua, ctx="InGame", wait=4.0):
    b = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=120)).get("output", [])


def run(label, lua, tries=3):
    for _ in range(tries):
        out = [l.split("E:", 1)[1].strip() for l in ex(lua) if "E:" in l]
        out = [o for o in out if o not in ("START", "END")]
        if out:
            print(f"\n### {label}")
            for o in out:
                print("   ", o)
            return out
    print(f"\n### {label}\n    (no output)")
    return []


run("UnitOperationTypes keys", '''
print("E:START")
local ks = {}
for k, v in pairs(UnitOperationTypes) do ks[#ks+1] = tostring(k) end
table.sort(ks)
local line = ""
for _, k in ipairs(ks) do
  line = line .. k .. " "
  if #line > 110 then print("E:OP "..line) line = "" end
end
if #line > 0 then print("E:OP "..line) end
print("E:END")
''')

run("UnitCommandTypes keys", '''
print("E:START")
if type(UnitCommandTypes) == "table" then
  local ks = {}
  for k, v in pairs(UnitCommandTypes) do ks[#ks+1] = tostring(k) end
  table.sort(ks)
  local line = ""
  for _, k in ipairs(ks) do
    line = line .. k .. " "
    if #line > 110 then print("E:CMD "..line) line = "" end
  end
  if #line > 0 then print("E:CMD "..line) end
else
  print("E:no UnitCommandTypes")
end
print("E:END")
''')
