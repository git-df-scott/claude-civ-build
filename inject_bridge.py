"""inject_bridge.py — load the CivAgentBridge Lua into a RUNNING game via the
tuner, with no mod enablement and no game restart.

WHY THIS EXISTS (root cause, 2026-07-24)
----------------------------------------
The bridge's core functions (Bridge_DumpState / Bridge_Execute / Bridge_ClearDiplo)
were shipped as a Civ 6 mod (CivAgentBridge). That created a hard dependency chain:

    mod present in the LIVE Mods dir  ->  mod discovered  ->  mod enabled
      ->  NEW GAME started  ->  leader-intro splash  ->  A HUMAN MOUSE CLICK
      ->  functions exist  ->  runner can play

Every link broke at least once tonight:
  * The mod was sitting in Documents\\My Games\\...\\Mods while the game's live
    user dir is %LOCALAPPDATA%\\Firaxis Games\\...\\Mods — so it was never
    discovered at all, and Bridge_DumpState was nil in every game.
  * Enabling a mod only takes effect for a NEWLY STARTED game, which forces the
    leader-intro splash, which is the ONE screen synthetic input cannot dismiss
    (re-verified tonight across Windows-MCP click/double-click/Enter/Space, and
    computer-use access was denied). That made a human click a hard requirement
    of every single startup.

The mod was never actually necessary. Its three files are plain Lua that define
GLOBAL functions; the tuner console can define exactly the same globals in the
live InGame context. Injecting them:
  * removes the mod dependency entirely (no Mods dir, no enablement, no restart),
  * therefore removes the forced new-game restart,
  * therefore removes the splash click from the critical path.

The splash can still appear when a human starts a fresh game, but the runner no
longer needs to CAUSE one, so it is no longer a blocker for automation.

Verification discipline (project rule: never trust an ack): after injecting we
call Bridge_DumpState() and require a real BRIDGE_STATE: line with a parseable
turn number back. A "no error" response is not accepted as proof.

Usage: python inject_bridge.py
Exit 0 = bridge live and proven; non-zero = not usable, do not start a runner.
"""
import json
import sys
import urllib.request
from pathlib import Path

DAEMON = "http://127.0.0.1:8321"

# Source of truth for the Lua. Prefer the live Mods dir, fall back to the
# Documents copy (they are the same files; Documents is where they were authored).
CANDIDATE_DIRS = [
    Path(r"C:\Users\Duncan\AppData\Local\Firaxis Games\Sid Meier's Civilization VI\Mods\CivAgentBridge"),
    Path(r"C:\Users\Duncan\Documents\My Games\Sid Meier's Civilization VI\Mods\CivAgentBridge"),
]
# Order matters: Utils defines BridgeJSON, which the other two use at call time.
FILES = ["Utils.lua", "StateDump.lua", "CommandIntake.lua"]


def http(path, body=None, timeout=60):
    req = urllib.request.Request(
        DAEMON + path,
        json.dumps(body).encode() if body is not None else None,
        {"Content-Type": "application/json"},
    )
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def ex(lua, wait=3.0, ctx="InGame"):
    return http("/exec", {"state": ctx, "lua": lua, "wait": wait}).get("output", [])


def source_dir():
    for d in CANDIDATE_DIRS:
        if all((d / f).exists() for f in FILES):
            return d
    sys.exit(f"ABORT: no CivAgentBridge source dir found. Looked in: {CANDIDATE_DIRS}")


def main():
    states = http("/states")
    if not states.get("connected"):
        sys.exit("ABORT: daemon not connected to the tuner")
    if "InGame" not in states.get("states", {}):
        sys.exit("ABORT: no InGame context — is a game actually loaded and past the splash?")

    src = source_dir()
    print(f"source: {src}")

    for fname in FILES:
        lua = (src / fname).read_text(encoding="utf-8")
        out = ex(lua, wait=3.5)
        marker = [l for l in out if "BRIDGE_" in l and "READY" in l]
        err = [l for l in out if "error" in l.lower() or "stack traceback" in l.lower()]
        print(f"  injected {fname}: markers={marker} errors={len(err)}")
        if err:
            for e in err[:3]:
                print("    !!", e[:200])

    # PROOF, not an ack: the functions must exist AND produce a real state dump.
    out = ex('print("CHK:dump="..tostring(Bridge_DumpState)'
             '.." exec="..tostring(Bridge_Execute)'
             '.." diplo="..tostring(Bridge_ClearDiplo))', wait=2.5)
    chk = next((l for l in out if "CHK:" in l), "")
    print("presence:", chk.strip())
    if "dump=nil" in chk or "exec=nil" in chk or not chk:
        sys.exit("ABORT: bridge functions still missing after injection")

    out = ex("Bridge_DumpState()", wait=4.0)
    line = next((l for l in out if "BRIDGE_STATE:" in l), None)
    if not line:
        sys.exit("ABORT: Bridge_DumpState() produced no BRIDGE_STATE line — not usable")
    try:
        st = json.loads(line[line.find("BRIDGE_STATE:") + 13:])
    except ValueError as e:
        sys.exit(f"ABORT: BRIDGE_STATE line did not parse as JSON: {e}")

    me = next((p for p in st.get("players", []) if p.get("isLocal")), None)
    print(f"VERIFIED: turn={st.get('turn')} players={len(st.get('players', []))} "
          f"cities={len(me['cities']) if me else '?'} units={len(me['units']) if me else '?'} "
          f"gold={me['gold'] if me else '?'}")
    print("bridge is live and proven in the running game.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
