"""research_barb.py — find the REAL config key that disables barbarians.

research_config.py proved none of the guessed keys (GAME_NO_BARBARIANS,
NO_BARBARIANS, GAME_BARBARIANS, ...) exist. The authoritative source is the
configuration database's Parameters table, which is what the Advanced Setup
screen itself reads. Query it directly instead of guessing.

Read-only.
"""
import json
import urllib.request

DAEMON = "http://127.0.0.1:8321"


def ex(lua, wait=2.0, ctx="Lobby"):
    body = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    req = urllib.request.Request(DAEMON + "/exec", body, {"Content-Type": "application/json"})
    out = json.load(urllib.request.urlopen(req, timeout=40)).get("output", [])
    return [l for l in out if "RC:" in l]


def probe(label, lua, wait=2.0):
    print(f"\n### {label}")
    for l in ex(f'print("RC:START")\n{lua}\nprint("RC:END")', wait=wait):
        s = l.split("RC:", 1)[1] if "RC:" in l else l
        if s.strip() not in ("START", "END"):
            print("   ", s)


# 1. Which config-DB query entry points exist here?
probe("config DB entry points", '''
print("RC:DB="..type(DB))
if DB then
  for _,m in ipairs({"ConfigurationQuery","Query","CreateQuery"}) do
    print("RC:DB."..m.."="..type(rawget(DB,m) or DB[m]))
  end
end
print("RC:Configuration="..type(Configuration))
''')

# 2. Every Parameter whose id/name smells of barbarians.
probe("Parameters matching BARBARIAN", '''
local ok, err = pcall(function()
  local rows = DB.ConfigurationQuery("SELECT ParameterId, Name, ConfigurationGroup, ConfigurationId, Domain, DefaultValue FROM Parameters")
  local n = 0
  for _, r in ipairs(rows) do
    n = n + 1
    local blob = tostring(r.ParameterId).." "..tostring(r.Name).." "..tostring(r.ConfigurationId)
    if string.find(string.upper(blob), "BARB") then
      print("RC:PARAM id="..tostring(r.ParameterId)
        .." grp="..tostring(r.ConfigurationGroup)
        .." cfgid="..tostring(r.ConfigurationId)
        .." domain="..tostring(r.Domain)
        .." default="..tostring(r.DefaultValue))
    end
  end
  print("RC:TOTAL_PARAMS="..n)
end)
if not ok then print("RC:ERR "..tostring(err)) end
''', wait=3.0)

# 3. Full parameter list for the Game group (so we can see the real naming style).
probe("Game-group parameters", '''
local ok, err = pcall(function()
  local rows = DB.ConfigurationQuery("SELECT ParameterId, ConfigurationGroup, ConfigurationId, Domain FROM Parameters WHERE ConfigurationGroup = 'Game'")
  for _, r in ipairs(rows) do
    print("RC:GAMEP "..tostring(r.ParameterId).." -> "..tostring(r.ConfigurationId).." ["..tostring(r.Domain).."]")
  end
end)
if not ok then print("RC:ERR "..tostring(err)) end
''', wait=3.0)

# 4. GameModes (Barbarian Clans lives here on newer builds).
probe("GameModes", '''
local ok = pcall(function()
  for row in GameInfo.GameModes() do
    print("RC:MODE "..tostring(row.GameModeType).." hash="..tostring(row.Hash))
  end
end)
if not ok then print("RC:MODE_TABLE_MISSING") end
''')

# 5. What ruleset / expansions are active (determines which options exist).
probe("installed content", '''
local ok = pcall(function()
  local rows = DB.ConfigurationQuery("SELECT ModId, Name FROM Mods WHERE Official = 1")
  for _, r in ipairs(rows) do print("RC:OFFMOD "..tostring(r.Name)) end
end)
if not ok then print("RC:no Mods table via ConfigurationQuery") end
print("RC:RULESET="..tostring(GameConfiguration.GetValue("RULESET")))
''', wait=3.0)

print("\ndone.")
