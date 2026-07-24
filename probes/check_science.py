"""How fast is science actually moving, and how far is Horseback Riding?
The whole plan gates on HBR, so if this is crawling the strategy needs to adapt."""
import json
import urllib.request

D = "http://127.0.0.1:8321"


def ex(lua, ctx="InGame", wait=4.0):
    b = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    r = urllib.request.Request(D + "/exec", b, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=120)).get("output", [])


def run(lua, tries=4):
    for _ in range(tries):
        out = [l.split("S:", 1)[1].strip() for l in ex(lua) if "S:" in l]
        out = [o for o in out if o not in ("START", "END")]
        if out:
            return out
    return []


for l in run('''
print("S:START")
local pid = Game.GetLocalPlayer()
local p = Players[pid]
local t = p:GetTechs()
local row = GameInfo.Technologies["TECH_HORSEBACK_RIDING"]
pcall(function() print("S:sci_per_turn="..string.format("%.1f", t:GetScienceYield())) end)
pcall(function() print("S:progress="..string.format("%.1f", t:GetResearchProgress(row.Index))) end)
pcall(function() print("S:cost="..string.format("%.1f", t:GetResearchCost(row.Index))) end)
pcall(function() print("S:turns_left="..tostring(t:GetTurnsLeft())) end)
local cul = p:GetCulture()
pcall(function() print("S:culture_per_turn="..string.format("%.1f", cul:GetCultureYield())) end)
local nc = 0
for _, c in p:GetCities():Members() do nc = nc + 1 end
print("S:cities="..nc)
print("S:END")
'''):
    print("  ", l)
