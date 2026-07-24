"""Is the rally point actually reachable land? If MOVE_TO has no valid path the
order is accepted and silently does nothing — which looks exactly like the
freeze we are seeing."""
import json
import urllib.request

D = "http://127.0.0.1:8321"


def ex(lua, ctx="InGame", wait=4.0):
    b = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=120)).get("output", [])


def run(lua, tries=4):
    for _ in range(tries):
        out = [l.split("P:", 1)[1].strip() for l in ex(lua) if "P:" in l]
        out = [o for o in out if o not in ("START", "END")]
        if out:
            return out
    return []


for l in run('''
print("P:START")
local pid = Game.GetLocalPlayer()
local vis = nil
pcall(function() vis = PlayersVisibility[pid] end)
for _, c in ipairs({{17,21},{19,20},{18,21},{16,22},{18,28},{17,28}}) do
  local x, y = c[1], c[2]
  local plot = Map.GetPlot(x, y)
  if plot then
    local rev = "?"
    if vis then pcall(function() rev = tostring(vis:IsRevealed(x, y)) end) end
    print("P:("..x..","..y..") water="..tostring(plot:IsWater())
      .." impass="..tostring(plot:IsImpassable())
      .." owner="..tostring(plot:GetOwner())
      .." revealed="..rev
      .." terrain="..tostring(GameInfo.Terrains[plot:GetTerrainType()] and GameInfo.Terrains[plot:GetTerrainType()].TerrainType))
  else
    print("P:("..x..","..y..") NO PLOT")
  end
end
-- can a specific stuck unit actually path to the rally point?
for _, u in Players[pid]:GetUnits():Members() do
  local info = GameInfo.Units[u:GetType()]
  if info and tostring(info.UnitType) == "UNIT_TREBUCHET" then
    local tp = {}
    tp[UnitOperationTypes.PARAM_X] = 17
    tp[UnitOperationTypes.PARAM_Y] = 21
    local can = false
    pcall(function()
      can = UnitManager.CanStartOperation(u, UnitOperationTypes.MOVE_TO, nil, tp)
    end)
    print("P:TREB at "..u:GetX()..","..u:GetY().." moves="..u:GetMovesRemaining()
          .." can_move_to_rally="..tostring(can))
    break
  end
end
print("P:END")
'''):
    print("  ", l)
