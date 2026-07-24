"""Enumerate PlayerOperations / related tables to find the exact keys for
declaring war and changing policy cards."""
import json
import urllib.request

D = "http://127.0.0.1:8321"


def ex(lua, ctx="InGame", wait=4.0):
    b = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=150)).get("output", [])


def run(label, lua, ctx="InGame", wait=4.0, tries=3):
    for _ in range(tries):
        out = [l.split("W:", 1)[1].strip() for l in ex(lua, ctx, wait) if "W:" in l]
        out = [o for o in out if o not in ("START", "END")]
        if out:
            print(f"\n### {label}")
            for o in out:
                print("   ", o)
            return out
    print(f"\n### {label}\n    (no output)")
    return []


run("ALL PlayerOperations keys", '''
print("W:START")
local ks = {}
for k, v in pairs(PlayerOperations) do ks[#ks+1] = k end
table.sort(ks)
local line = ""
for _, k in ipairs(ks) do
  line = line .. k .. " "
  if #line > 120 then print("W:PO "..line) line = "" end
end
if #line > 0 then print("W:PO "..line) end
print("W:count="..#ks)
print("W:END")
''')

run("global tables mentioning POLICY / GOVERNMENT", '''
print("W:START")
for k, v in pairs(_G) do
  local u = string.upper(tostring(k))
  if string.find(u, "POLIC") or string.find(u, "GOVERN") then
    print("W:GLOBAL "..tostring(k).."="..type(v))
  end
end
print("W:END")
''')

run("Culture read-only slot info (what we CAN see)", '''
print("W:START")
local pid = Game.GetLocalPlayer()
local c = Players[pid]:GetCulture()
local ok, n = pcall(function() return c:GetNumPolicySlots() end)
print("W:num_slots="..tostring(ok and n or "ERR"))
if ok and n then
  for i = 0, n - 1 do
    local ok2, s = pcall(function() return c:GetSlotType(i) end)
    print("W:slot "..i.." type="..tostring(ok2 and s or "ERR"))
  end
end
print("W:END")
''')

run("Culture full method list", '''
print("W:START")
local pid = Game.GetLocalPlayer()
local c = Players[pid]:GetCulture()
local ks = {}
for k, v in pairs(getmetatable(c) and getmetatable(c).__index or c) do ks[#ks+1] = tostring(k) end
table.sort(ks)
local line = ""
for _, k in ipairs(ks) do
  line = line .. k .. " "
  if #line > 120 then print("W:CUL "..line) line = "" end
end
if #line > 0 then print("W:CUL "..line) end
print("W:END")
''')
