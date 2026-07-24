"""new_game.py — start a fresh Civ 6 game headlessly with explicit settings.

Recipe (verified 2026-07-16, refined here):
  Lobby ctx: GameConfiguration.SetToDefaults()  <- must come FIRST, it wipes all
             SetValue(...) for our overrides    <- so overrides come AFTER
             Network.HostGame(SERVER_TYPE_NONE) <- the "Play Now" flow
  then: wait for 'LoadScreen' in the async drain, THEN /reconnect.
        Reconnecting during 'JoiningRoom' CANCELS hosting (verified 2026-07-16).

Config keys proven live 2026-07-22 by probes/research_barb.py:
  GAME_HANDICAP        -> StandardDifficulties, DIFFICULTY_SETTLER hash 1078608846
  GAME_NO_BARBARIANS   -> bool (Parameters.ConfigurationGroup='Game')

Every setting is read back after the game is actually running; an ack is never
trusted as proof (see civ6-bridge memory: Civ 6 booleans are permissive).
"""
import json
import sys
import time
import urllib.request

DAEMON = "http://127.0.0.1:8321"
SETTLER_HASH = 1078608846


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


def show(label, lines):
    print(f"\n### {label}")
    for l in lines:
        print("   ", l)


READBACK = '''
print("NG:START")
print("NG:handicap="..tostring(GameConfiguration.GetValue("GAME_HANDICAP")))
print("NG:nobarb="..tostring(GameConfiguration.GetValue("GAME_NO_BARBARIANS")))
print("NG:speed="..tostring(GameConfiguration.GetValue("GAME_SPEED_TYPE")))
print("NG:ruleset="..tostring(GameConfiguration.GetValue("RULESET")))
print("NG:END")
'''


def readback(ctx="Lobby", tries=4):
    """Read the settings back, retrying.

    The console-capture window is a race: on 2026-07-22 the values were set
    correctly and printed by the game, but the exec returned an empty list and
    the script aborted spuriously. An empty capture means 'didn't see it',
    never 'not set' — so retry before believing anything.
    """
    for i in range(tries):
        res = tagged(ex(READBACK, wait=2.0 + 1.5 * i, ctx=ctx))
        kv = dict(p.split("=", 1) for p in res if "=" in p)
        if "handicap" in kv:
            return kv
        print(f"   (readback attempt {i+1} captured nothing; retrying)")
    return {}


# ---------------------------------------------------------------- stage 1
print("stage 1: configure new game (Lobby ctx)")
ex('''
GameConfiguration.SetToDefaults()
GameConfiguration.SetValue("GAME_HANDICAP", %d)
GameConfiguration.SetValue("GAME_NO_BARBARIANS", true)
''' % SETTLER_HASH, wait=2.0)

got = readback()
show("pre-host config readback", [f"{k}={v}" for k, v in got.items()])
if not got:
    sys.exit("ABORT: could not read config back at all after retries")
if got.get("handicap") != str(SETTLER_HASH):
    sys.exit(f"ABORT: difficulty did not stick (got {got.get('handicap')!r})")
if got.get("nobarb") not in ("true", "1"):
    sys.exit(f"ABORT: no-barbarians did not stick (got {got.get('nobarb')!r})")
print("\n  -> Settler + barbarians-off both confirmed set pre-host.")

# ---------------------------------------------------------------- stage 2
print("\nstage 2: host game")
http_get("/drain")                       # clear the async buffer first
ex('Network.HostGame(ServerType.SERVER_TYPE_NONE)', wait=1.0)

# ---------------------------------------------------------------- stage 3
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
    print("   !! never saw LoadScreen; reconnecting anyway is risky — stopping here.")
    print("   states now:", json.dumps(http_get("/states")["states"])[:400])
    sys.exit(2)

# ---------------------------------------------------------------- stage 4
print("\nstage 4: reconnect into the in-game Lua state set")
time.sleep(2)
print("   ", http_get("/reconnect", timeout=90))

for i in range(60):
    st = http_get("/states")["states"]
    if "InGame" in st:
        print(f"   -> InGame present after {i*3}s "
              f"({len(st)} states, InGame={st['InGame']}, "
              f"GameCore_Tuner={st.get('GameCore_Tuner')})")
        break
    time.sleep(3)
else:
    st = http_get("/states")["states"]
    print(f"   !! InGame never appeared. {len(st)} states: {sorted(st)[:12]}")
    print("   If the list is ~3 states {Main State, DebugHotloadCache, LoadScreen},")
    print("   the game is parked on the leader-intro splash and needs one human click.")
    sys.exit(3)

# ---------------------------------------------------------------- stage 5
# The pre-host readback proves only what the setup screen accepted. The claim
# that matters is what the RUNNING game has, so re-verify in the InGame ctx.
print("\nstage 5: verify settings inside the running game")
live = readback(ctx="InGame")
show("in-game config", [f"{k}={v}" for k, v in live.items()])

ok = True
if live.get("handicap") != str(SETTLER_HASH):
    print(f"   !! FAIL difficulty in-game = {live.get('handicap')!r}, expected {SETTLER_HASH} (Settler)")
    ok = False
else:
    print("   OK difficulty = DIFFICULTY_SETTLER")
if live.get("nobarb") not in ("true", "1"):
    print(f"   !! FAIL no-barbarians in-game = {live.get('nobarb')!r}")
    ok = False
else:
    print("   OK barbarians disabled")

# Independent check: the barbarian player (63) should own no units.
barb = tagged(ex('''
print("NG:START")
local n = 0
local ok = pcall(function()
  for _, u in Players[63]:GetUnits():Members() do n = n + 1 end
end)
print("NG:barb_units="..tostring(n).." readable="..tostring(ok))
print("NG:turn="..tostring(Game.GetCurrentGameTurn()))
print("NG:END")
''', wait=2.5, ctx="InGame"))
show("barbarian player state", barb)

print("\ndone — game is running." if ok else "\ndone, but settings did NOT verify in-game.")
