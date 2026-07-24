"""research_config2.py — round 2: MapConfiguration, GameModes, player count,
and a SET/GET round-trip to confirm how barbarians are disabled.

Setting config values here is harmless: the new-game path calls
GameConfiguration.SetToDefaults() first, which wipes anything we set now.
"""
import json
import urllib.request

DAEMON = "http://127.0.0.1:8321"


def ex(lua, wait=1.5, ctx="Lobby"):
    body = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    req = urllib.request.Request(DAEMON + "/exec", body, {"Content-Type": "application/json"})
    out = json.load(urllib.request.urlopen(req, timeout=30)).get("output", [])
    return [l for l in out if "RC:" in l]


def probe(label, lua):
    print(f"\n### {label}")
    for l in ex(f'print("RC:START")\n{lua}\nprint("RC:END")'):
        s = l.split("RC:", 1)[1] if "RC:" in l else l
        if s.strip() not in ("START", "END"):
            print("   ", s)


# 1. MapConfiguration — where map size/script actually live.
probe("MapConfiguration surface", '''
print("RC:MapConfiguration="..type(MapConfiguration))
if MapConfiguration then
  for _,k in ipairs({"MAP_SIZE","MAP_SCRIPT","MapSize","Script"}) do
    local ok,v = pcall(function() return MapConfiguration.GetValue(k) end)
    print("RC:MAPCFG "..k.."="..tostring(ok and v or "ERR"))
  end
  local ok,s = pcall(function() return MapConfiguration.GetScript() end)
  print("RC:GetScript="..tostring(ok and s or "ERR"))
end
''')

# 2. Player-count / participant methods on GameConfiguration.
probe("player count methods", '''
for _,m in ipairs({"GetPlayerCount","GetHumanCount","GetParticipatingPlayerCount","GetMaxMajorPlayers"}) do
  local ok,v = pcall(function() return GameConfiguration[m](GameConfiguration) end)
  print("RC:PC "..m.."="..tostring(ok and v or "ERR"))
end
''')

# 3. GameModes — is "no barbarians" a mode?
probe("GameModes enumerate", '''
local ok = pcall(function()
  for row in GameInfo.GameModes() do print("RC:MODE "..tostring(row.GameModeType)) end
end)
if not ok then print("RC:MODE no GameModes table") end
''')

# 4. Barbarian SET/GET round-trip (harmless; SetToDefaults wipes it later).
probe("barbarian set/get roundtrip", '''
GameConfiguration.SetValue("GAME_NO_BARBARIANS", true)
local ok,v = pcall(function() return GameConfiguration.GetValue("GAME_NO_BARBARIANS") end)
print("RC:AFTER_SET GAME_NO_BARBARIANS="..tostring(ok and v or "ERR"))
GameConfiguration.SetValue("GAME_NO_BARBARIANS", false)
local ok2,v2 = pcall(function() return GameConfiguration.GetValue("GAME_NO_BARBARIANS") end)
print("RC:AFTER_UNSET GAME_NO_BARBARIANS="..tostring(ok2 and v2 or "ERR"))
''')

# 5. Confirm difficulty set/get roundtrip with the Settler hash.
probe("difficulty set/get roundtrip (then restore)", '''
local before = GameConfiguration.GetValue("GAME_HANDICAP")
GameConfiguration.SetValue("GAME_HANDICAP", 1078608846)  -- DIFFICULTY_SETTLER
print("RC:AFTER_SET GAME_HANDICAP="..tostring(GameConfiguration.GetValue("GAME_HANDICAP")))
GameConfiguration.SetValue("GAME_HANDICAP", before)      -- restore
print("RC:RESTORED GAME_HANDICAP="..tostring(GameConfiguration.GetValue("GAME_HANDICAP")))
''')

print("\ndone.")
