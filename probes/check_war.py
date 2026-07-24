"""Battlefield state: where our army is, and the health of the target city."""
import json
import urllib.request

D = "http://127.0.0.1:8321"


def ex(lua, ctx="InGame", wait=4.0):
    b = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=120)).get("output", [])


def run(lua, tries=4):
    for _ in range(tries):
        out = [l.split("W:", 1)[1].strip() for l in ex(lua) if "W:" in l]
        out = [o for o in out if o not in ("START", "END")]
        if out:
            return out
    return []


for l in run('''
print("W:START")
local pid = Game.GetLocalPlayer()
local p = Players[pid]
local TX, TY = 19, 30
for _, u in p:GetUnits():Members() do
  local info = GameInfo.Units[u:GetType()]
  local cls = info and tostring(info.PromotionClass) or "nil"
  if cls ~= "nil" and cls ~= "PROMOTION_CLASS_RECON" then
    print("W:MY "..(info and info.UnitType or "?")
      .." at "..u:GetX()..","..u:GetY()
      .." dist_to_target="..Map.GetPlotDistance(u:GetX(), u:GetY(), TX, TY)
      .." dmg="..u:GetDamage().." moves="..u:GetMovesRemaining())
  end
end
local dip = p:GetDiplomacy()
for _, opid in ipairs(PlayerManager.GetAliveIDs()) do
  if opid ~= pid then
    local atwar = false
    pcall(function() atwar = dip:IsAtWarWith(opid) end)
    if atwar then
      pcall(function()
        for _, c in Players[opid]:GetCities():Members() do
          local hp, def = -1, -1
          pcall(function() hp = c:GetDamage(DefenseTypes.DISTRICT_GARRISON) end)
          pcall(function() def = c:GetDefenseStrength() end)
          print("W:ENEMYCITY p"..opid.." "..tostring(c:GetName())
            .." at "..c:GetX()..","..c:GetY().." dmg="..tostring(hp).." def="..tostring(def))
        end
        local n = 0
        for _, u in Players[opid]:GetUnits():Members() do n = n + 1 end
        print("W:ENEMYUNITS p"..opid.."="..n)
      end)
    end
  end
end
print("W:END")
'''):
    print("  ", l)
