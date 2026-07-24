"""Compact campaign snapshot — safe to run between runner turns.

NOTE: do not run this while the runner is mid-turn if you can avoid it; both
share the single tuner socket and the runner's console output can drown this
one's (documented 2026-07-19). It is read-only, so the worst case is no output.
"""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

D = "http://127.0.0.1:8321"


def ex(lua, ctx="InGame", wait=3.0):
    b = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=90)).get("output", [])


def run(lua, tag="S:", tries=3):
    for _ in range(tries):
        out = [l.split(tag, 1)[1].strip() for l in ex(lua) if tag in l]
        out = [o for o in out if o not in ("START", "END")]
        if out:
            return out
    return []


for line in run('''
print("S:START")
local pid = Game.GetLocalPlayer()
local p = Players[pid]
local dip = p:GetDiplomacy()
print("S:turn="..Game.GetCurrentGameTurn().." active="..tostring(p:IsTurnActive()))
print("S:gold="..math.floor(p:GetTreasury():GetGoldBalance()))
local nc = 0
for _, c in p:GetCities():Members() do
  nc = nc + 1
  local prod = "?"
  pcall(function() prod = tostring(c:GetBuildQueue():GetCurrentProductionTypeName()) end)
  print("S:CITY "..tostring(c:GetName()).." ("..c:GetX()..","..c:GetY()..") pop="..tostring(c:GetPopulation()).." building="..prod)
end
print("S:cities="..nc)
local counts = {}
local nu = 0
for _, u in p:GetUnits():Members() do
  nu = nu + 1
  local info = GameInfo.Units[u:GetType()]
  local t = info and tostring(info.UnitType) or "?"
  counts[t] = (counts[t] or 0) + 1
end
for t, n in pairs(counts) do print("S:UNITS "..t.." x"..n) end
print("S:units="..nu)
local tech, civic = "-", "-"
pcall(function() local i = p:GetTechs():GetResearchingTech()
  if i and i >= 0 then tech = GameInfo.Technologies[i].TechnologyType end end)
pcall(function() local i = p:GetCulture():GetProgressingCivic()
  if i and i >= 0 then civic = GameInfo.Civics[i].CivicType end end)
print("S:researching="..tech.." civic="..civic)
local pol = {}
for row in GameInfo.Policies() do
  local a = false
  pcall(function() a = p:GetCulture():IsPolicyActive(row.Index) end)
  if a then pol[#pol+1] = row.PolicyType end
end
print("S:policies="..table.concat(pol, ","))
for _, opid in ipairs(PlayerManager.GetAliveIDs()) do
  if opid ~= pid and opid < 62 then
    local met, war, major, ncity = false, false, false, 0
    pcall(function() met = dip:HasMet(opid) end)
    pcall(function() war = dip:IsAtWarWith(opid) end)
    pcall(function() major = Players[opid]:IsMajor() end)
    pcall(function() for _, c in Players[opid]:GetCities():Members() do ncity = ncity + 1 end end)
    if major then
      print("S:RIVAL p"..opid.." met="..tostring(met).." war="..tostring(war).." cities="..ncity)
    end
  end
end
print("S:END")
'''):
    print(" ", line)
