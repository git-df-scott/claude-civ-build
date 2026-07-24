"""Per-unit positions WITH IDs and true engine distances to the target/rally.
The unit list order is not stable, so row-by-row comparison between snapshots is
meaningless — only ID-keyed tracking shows whether a given unit is closing."""
import json
import sys
import urllib.request

D = "http://127.0.0.1:8321"
TX, TY = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (19, 20)
RX, RY = (int(sys.argv[3]), int(sys.argv[4])) if len(sys.argv) > 4 else (17, 21)


def ex(lua, wait=4.5):
    b = json.dumps({"state": "InGame", "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=150)).get("output", [])


for _ in range(4):
    out = [l.split("T:", 1)[1].strip() for l in ex(f'''
print("T:START")
local pid = Game.GetLocalPlayer()
for _, u in Players[pid]:GetUnits():Members() do
  local info = GameInfo.Units[u:GetType()]
  local cls = info and tostring(info.PromotionClass) or "nil"
  if cls ~= "nil" and cls ~= "PROMOTION_CLASS_RECON" then
    print("T:"..tostring(info.UnitType).." id="..u:GetID()
      .." at="..u:GetX()..","..u:GetY()
      .." dTgt="..Map.GetPlotDistance(u:GetX(), u:GetY(), {TX}, {TY})
      .." dRally="..Map.GetPlotDistance(u:GetX(), u:GetY(), {RX}, {RY})
      .." mv="..u:GetMovesRemaining().." dmg="..u:GetDamage())
  end
end
print("T:END")
''') if "T:" in l]
    out = [o for o in out if o not in ("START", "END")]
    if out:
        near = 0
        for line in out:
            print("  ", line)
            try:
                d = int(line.split("dTgt=")[1].split()[0])
                if d <= 4:
                    near += 1
            except (IndexError, ValueError):
                pass
        print(f"\n  units within 4 of target ({TX},{TY}): {near}")
        break
else:
    print("  no output")
