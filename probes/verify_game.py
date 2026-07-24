"""Verify the running game really has Settler difficulty + barbarians off,
and dump the opening position (civ, leader, units, map) to plan from.

Ack-free: every claim is read out of the live engine.
"""
import json
import urllib.request

D = "http://127.0.0.1:8321"
SETTLER = 1078608846


def ex(lua, ctx="InGame", wait=2.5):
    b = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=90)).get("output", [])


def run(lua, ctx="InGame", wait=2.5, tries=3):
    for _ in range(tries):
        out = [l.split("V:", 1)[1].strip() for l in ex(lua, ctx, wait) if "V:" in l]
        out = [o for o in out if o not in ("START", "END")]
        if out:
            return out
    return []


print("=== config as the RUNNING game sees it ===")
for l in run('''
print("V:START")
print("V:handicap="..tostring(GameConfiguration.GetValue("GAME_HANDICAP")))
print("V:nobarb="..tostring(GameConfiguration.GetValue("GAME_NO_BARBARIANS")))
print("V:speed="..tostring(GameConfiguration.GetValue("GAME_SPEED_TYPE")))
print("V:turn="..tostring(Game.GetCurrentGameTurn()))
print("V:END")
'''):
    print("  ", l)

print("\n=== who we are + opening units ===")
for l in run('''
print("V:START")
local pid = Game.GetLocalPlayer()
print("V:local_player="..tostring(pid))
local pc = PlayerConfigurations[pid]
print("V:civ="..tostring(pc:GetCivilizationTypeName()).." leader="..tostring(pc:GetLeaderTypeName()))
local p = Players[pid]
for u in p:GetUnits():Members() do
  print("V:UNIT "..tostring(u:GetType()).." id="..tostring(u:GetID())
        .." at "..tostring(u:GetX())..","..tostring(u:GetY()))
end
print("V:END")
'''):
    print("  ", l)

print("\n=== rivals (major players alive) ===")
for l in run('''
print("V:START")
local n = 0
for _, p in ipairs(PlayerManager.GetAliveMajors()) do n = n + 1 end
print("V:alive_majors="..tostring(n))
local ok, cnt = pcall(function()
  local c = 0
  for _ in Players[63]:GetUnits():Members() do c = c + 1 end
  return c
end)
print("V:barb_units="..tostring(ok and cnt or "unreadable"))
print("V:END")
'''):
    print("  ", l)
