"""research_config.py — READ-ONLY probe of the new-game configuration API.

Runs against a LIVE main-menu connection (Lobby context) to answer, for real,
how to set difficulty=Settler and barbarians=off before HostGame — the single
biggest unverified gap for the "start a new game with custom settings" step.

Does NOT mutate anything: only enumerates API surface and reads current values.
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
        if l.strip() not in ("RC:START", "RC:END"):
            print("   ", l)


# 1. Does GameConfiguration exist here and what shape is it?
probe("GameConfiguration presence", '''
print("RC:GameConfiguration="..type(GameConfiguration))
print("RC:PlayerConfigurations="..type(PlayerConfigurations))
print("RC:has_SetToDefaults="..tostring(GameConfiguration.SetToDefaults ~= nil))
print("RC:has_SetValue="..tostring(GameConfiguration.SetValue ~= nil))
print("RC:has_GetValue="..tostring(GameConfiguration.GetValue ~= nil))
''')

# 2. Enumerate the difficulty (handicap) types the engine knows.
probe("Difficulties table", '''
for row in GameInfo.Difficulties() do
  print("RC:DIFF "..row.Index.." "..row.DifficultyType.." hash="..tostring(row.Hash))
end
''')

# 3. Read current difficulty-related config values (several candidate keys).
probe("current difficulty config", '''
for _,k in ipairs({"GAME_DIFFICULTY","DIFFICULTY","GAME_HANDICAP"}) do
  local ok,v = pcall(function() return GameConfiguration.GetValue(k) end)
  print("RC:CFG "..k.."="..tostring(ok and v or "ERR"))
end
local ok,h = pcall(function() return PlayerConfigurations[0]:GetHandicapLevel() end)
print("RC:P0_Handicap="..tostring(ok and h or "ERR"))
print("RC:has_SetHandicapLevel="..tostring(PlayerConfigurations[0].SetHandicapLevel ~= nil))
''')

# 4. Barbarian setting — probe candidate keys and any barbarian game mode.
probe("barbarian config keys", '''
for _,k in ipairs({"GAME_NO_BARBARIANS","NO_BARBARIANS","GAME_BARBARIANS","BARBARIANS","GAME_START_BARBARIAN"}) do
  local ok,v = pcall(function() return GameConfiguration.GetValue(k) end)
  print("RC:BARB "..k.."="..tostring(ok and v or "ERR"))
end
''')

# 5. Map + opponents config (so we can pick a small/fast map).
probe("map & players config", '''
for _,k in ipairs({"GAME_MAP_SCRIPT","MAP_SCRIPT","GAME_MAP_SIZE","MAP_SIZE","GAME_SPEED_TYPE","GAME_SPEED"}) do
  local ok,v = pcall(function() return GameConfiguration.GetValue(k) end)
  print("RC:MAP "..k.."="..tostring(ok and v or "ERR"))
end
local ok,n = pcall(function() return GameConfiguration.GetParticipantCount() end)
print("RC:Participants="..tostring(ok and n or "ERR"))
''')

# 6. Enumerate map sizes and game speeds available.
probe("MapSizes & GameSpeeds", '''
for row in GameInfo.Maps() do print("RC:MAPSIZE "..row.MapSizeType) end
for row in GameInfo.GameSpeeds() do print("RC:SPEED "..row.GameSpeedType) end
''')

print("\ndone.")
