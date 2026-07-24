"""Find the API that actually reports a city's health, then read the target's.
GetDamage(DefenseTypes.DISTRICT_GARRISON) returned -1, so it is the wrong call."""
import json
import urllib.request

D = "http://127.0.0.1:8321"


def ex(lua, ctx="InGame", wait=4.0):
    b = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=120)).get("output", [])


def run(lua, tries=4):
    for _ in range(tries):
        out = [l.split("C:", 1)[1].strip() for l in ex(lua) if "C:" in l]
        out = [o for o in out if o not in ("START", "END")]
        if out:
            return out
    return []


for l in run('''
print("C:START")
local pid = Game.GetLocalPlayer()
local dip = Players[pid]:GetDiplomacy()
for _, opid in ipairs(PlayerManager.GetAliveIDs()) do
  local atwar = false
  pcall(function() atwar = dip:IsAtWarWith(opid) end)
  if atwar and opid ~= pid then
    pcall(function()
      for _, c in Players[opid]:GetCities():Members() do
        if c:GetX() == 19 and c:GetY() == 30 then
          for _, m in ipairs({"GetDamage","GetMaxDamage","GetHitPoints","GetMaxHitPoints"}) do
            local v = "nil"
            pcall(function() if c[m] then v = tostring(c[m](c)) end end)
            print("C:city."..m.."="..v)
          end
          local d = nil
          pcall(function() d = c:GetDistricts() end)
          print("C:GetDistricts="..type(d))
          if d then
            for _, m in ipairs({"GetDefenseStrength","GetDefenseHitPoints","GetWallHitPoints"}) do
              local v = "nil"
              pcall(function() if d[m] then v = tostring(d[m](d)) end end)
              print("C:districts."..m.."="..v)
            end
          end
          local nu = 0
          pcall(function()
            local plot = Map.GetPlot(19, 30)
            nu = Map.GetUnitCount(19, 30)
          end)
          print("C:units_on_city_tile="..tostring(nu))
        end
      end
    end)
  end
end
print("C:END")
'''):
    print("  ", l)
