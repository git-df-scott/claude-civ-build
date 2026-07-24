"""start_science_game.py — host a fresh standard game: Prince difficulty,
barbarians ON, standard map/speed (engine defaults), verified in-engine.

Recipe proven in new_game.py (2026-07-16/22), reused verbatim: SetToDefaults()
first (wipes overrides), then SetValue overrides, then HostGame while in the
Lobby context; wait for the LoadScreen marker in the async drain before
/reconnect (reconnecting during JoiningRoom cancels hosting); poll for InGame;
re-verify every setting AFTER the game is actually running, never trust the
pre-host readback or any ack.

PRINCE_HASH found live 2026-07-24 via GameInfo.Types() scan (DIFFICULTY_PRINCE).
"""
import json
import sys
import time
import urllib.request

DAEMON = "http://127.0.0.1:8321"
PRINCE_HASH = -179952465


def http_get(path, timeout=60):
    return json.load(urllib.request.urlopen(DAEMON + path, timeout=timeout))


def ex(lua, wait=1.5, ctx="Lobby"):
    body = json.dumps({"state": ctx, "lua": lua, "wait": wait}).encode()
    req = urllib.request.Request(DAEMON + "/exec", body, {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=90)).get("output", [])


def tagged(lines, tag="NG:"):
    out = []
    for l in lines:
        if tag in l:
            s = l.split(tag, 1)[1].strip()
            if s not in ("START", "END"):
                out.append(s)
    return out


READBACK = '''
print("NG:START")
print("NG:handicap="..tostring(GameConfiguration.GetValue("GAME_HANDICAP")))
print("NG:nobarb="..tostring(GameConfiguration.GetValue("GAME_NO_BARBARIANS")))
print("NG:speed="..tostring(GameConfiguration.GetValue("GAME_SPEED_TYPE")))
print("NG:map="..tostring(GameConfiguration.GetValue("MAP_SCRIPT")))
print("NG:END")
'''


def readback(ctx="Lobby", tries=4):
    for i in range(tries):
        res = tagged(ex(READBACK, wait=2.0 + 1.5 * i, ctx=ctx))
        kv = dict(p.split("=", 1) for p in res if "=" in p)
        if "handicap" in kv:
            return kv
        print(f"   (readback attempt {i+1} captured nothing; retrying)")
    return {}


print("stage 1: configure new game (Lobby ctx) — Prince, barbarians ON, standard defaults")
ex('''
GameConfiguration.SetToDefaults()
GameConfiguration.SetValue("GAME_HANDICAP", %d)
GameConfiguration.SetValue("GAME_NO_BARBARIANS", false)
''' % PRINCE_HASH, wait=2.0)

got = readback()
print("pre-host config:", got)
if not got:
    sys.exit("ABORT: could not read config back at all after retries")
if got.get("handicap") != str(PRINCE_HASH):
    sys.exit(f"ABORT: difficulty did not stick (got {got.get('handicap')!r}, want {PRINCE_HASH})")
if got.get("nobarb") not in ("false", "0", "nil", "None"):
    sys.exit(f"ABORT: barbarians did not turn on (got nobarb={got.get('nobarb')!r})")
print("  -> Prince + barbarians-ON confirmed set pre-host.")

print("\nstage 2: host game")
http_get("/drain")
ex('Network.HostGame(ServerType.SERVER_TYPE_NONE)', wait=1.0)

print("stage 3: waiting for LoadScreen marker before reconnecting...")
saw_load, t0 = False, time.time()
while time.time() - t0 < 300:
    out = http_get("/drain").get("output", [])
    for l in out:
        if "LoadScreen" in l:
            saw_load = True
    if out:
        print(f"   [{time.time()-t0:5.1f}s] {len(out)} lines; last: {out[-1][:110]}")
    if saw_load:
        print(f"   -> LoadScreen seen at {time.time()-t0:.1f}s")
        break
    time.sleep(2)

if not saw_load:
    print("   !! never saw LoadScreen; states now:", json.dumps(http_get("/states")["states"])[:400])
    sys.exit(2)

print("\nstage 4: reconnect into the in-game Lua state set")
time.sleep(2)
print("   ", http_get("/reconnect", timeout=90))

for i in range(60):
    st = http_get("/states")["states"]
    if "InGame" in st:
        print(f"   -> InGame present after {i*3}s ({len(st)} states)")
        break
    time.sleep(3)
else:
    st = http_get("/states")["states"]
    print(f"   !! InGame never appeared. {len(st)} states: {sorted(st)[:12]}")
    sys.exit(3)

print("\nstage 5: verify settings inside the running game")
live = readback(ctx="InGame")
print("in-game config:", live)

ok = True
if live.get("handicap") != str(PRINCE_HASH):
    print(f"   !! FAIL difficulty in-game = {live.get('handicap')!r}, expected {PRINCE_HASH} (Prince)")
    ok = False
else:
    print("   OK difficulty = DIFFICULTY_PRINCE")
if live.get("nobarb") not in ("false", "0"):
    print(f"   !! FAIL barbarians-off flag in-game = {live.get('nobarb')!r} (want false/0)")
    ok = False
else:
    print("   OK barbarians ON")

extra = tagged(ex('''
print("NG:START")
print("NG:turn="..tostring(Game.GetCurrentGameTurn()))
print("NG:leader="..tostring(PlayerConfigurations[Game.GetLocalPlayer()]:GetLeaderTypeName()))
print("NG:civ="..tostring(PlayerConfigurations[Game.GetLocalPlayer()]:GetCivilizationTypeName()))
print("NG:cities="..tostring(#Players[Game.GetLocalPlayer()]:GetCities():GetIDs and 0 or 0))
print("NG:END")
''', wait=2.5, ctx="InGame"))
print("player info:", extra)

print("\ndone — game is running." if ok else "\ndone, but settings did NOT verify in-game.")
sys.exit(0 if ok else 4)
