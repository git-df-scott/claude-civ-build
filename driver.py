"""driver.py — external agent driver for CivAgentBridge.

SUPERSEDED by play_batch.py for actual play (decide() below is a stub that only
ends turns). Kept because it documents the mod-injection recipe (inject_mod)
and the bridge_files/ audit-trail flow.

Flow per turn:
  1. Daemon console lines are polled via GET /drain; a "BRIDGE_STATE:{...}" line
     is written to bridge_files/state.json (the mod cannot write files itself —
     verified in-engine: io is nil in Civ 6 UI Lua).
  2. decide(state, history) returns ONE action dict (stub — wire Claude in here).
  3. The action is sent as bridge_files/command.json for audit, then executed in
     the game via POST /exec calling Bridge_Execute('<json>'); the result line
     "BRIDGE_RESULT:{...}" is written to bridge_files/result.json and the
     consumed command.json is deleted.
  4. Hard cap: MAX_ACTIONS_PER_TURN actions, then end_turn is forced regardless.
"""
import json
import time
import urllib.request
from pathlib import Path

DAEMON = "http://127.0.0.1:8321"
BRIDGE_DIR = Path(__file__).parent / "bridge_files"
STATE_FILE = BRIDGE_DIR / "state.json"
COMMAND_FILE = BRIDGE_DIR / "command.json"
RESULT_FILE = BRIDGE_DIR / "result.json"
MAX_ACTIONS_PER_TURN = 15
GAME_CONTEXT = "InGame"  # verified working context; ActionPanel is mute in some sessions
MOD_DIR = Path.home() / "Documents/My Games/Sid Meier's Civilization VI/Mods/CivAgentBridge"


def http(path, body=None, timeout=30):
    req = urllib.request.Request(
        DAEMON + path,
        json.dumps(body).encode() if body is not None else None,
        {"Content-Type": "application/json"},
    )
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def drain_lines():
    return http("/drain").get("output", [])


def extract(lines, prefix):
    """Last JSON payload for a given BRIDGE_ prefix among console lines."""
    found = None
    for line in lines:
        # lines look like "CivAgentBridge: BRIDGE_STATE:{...}"
        i = line.find(prefix)
        if i != -1:
            payload = line[i + len(prefix):]
            try:
                found = json.loads(payload)
            except json.JSONDecodeError:
                pass
    return found


GAMECORE_CONTEXT = "GameCore_Tuner"  # gameplay-side Lua; has FinishMoves (UI ctx does not)


def exec_lua(lua, wait=2.0, ctx=GAME_CONTEXT):
    return http("/exec", {"state": ctx, "lua": lua, "wait": wait})


def finish_idle_units(local_pid):
    """Clear unspent moves on every local unit via the GameCore-context helper.

    This is the turn-blocker fix: end_turn silently stalls if any unit still has
    moves. FinishMoves exists only in GameCore_Tuner (nil in the UI context where
    Bridge_Execute runs), so the clear must be issued there, before the UI end_turn.
    """
    out = exec_lua(f"Bridge_FinishIdle({local_pid})", wait=2.0, ctx=GAMECORE_CONTEXT)
    for line in out.get("output", []):
        if "BRIDGE_FINISHIDLE:" in line:
            return int(line.split("BRIDGE_FINISHIDLE:")[1].strip())
    return None


def run_action(action, action_id, local_pid=0):
    """Send one command to the mod; return the result dict (or None on timeout)."""
    # Before ending the turn, clear idle units so the turn actually advances.
    if action.get("action") == "end_turn":
        n = finish_idle_units(local_pid)
        print(f"  finished {n} idle units before end_turn")
    cmd = dict(action, id=action_id)
    COMMAND_FILE.write_text(json.dumps(cmd, indent=2))
    payload = json.dumps(cmd).replace("\\", "\\\\").replace("'", "\\'")
    out = exec_lua("Bridge_Execute('" + payload + "')", wait=3.0)
    res = extract(out.get("output", []), "BRIDGE_RESULT:")
    deadline = time.time() + 15
    while res is None and time.time() < deadline:
        time.sleep(1)
        res = extract(drain_lines(), "BRIDGE_RESULT:")
    if res is not None:
        RESULT_FILE.write_text(json.dumps(res, indent=2))
    COMMAND_FILE.unlink(missing_ok=True)  # command consumed
    return res


def decide(state, history):
    """STUB — replace with the Claude call.

    Gets the full state snapshot plus this turn's action/result history.
    Must return ONE action dict:
      {"action": "move_unit", "unit_id": N, "x": X, "y": Y}
      {"action": "set_production", "city_id": N, "item": "UNIT_WARRIOR"}
      {"action": "end_turn"}
    """
    return {"action": "end_turn"}


def inject_bridge():
    """Load the bridge Lua into the running game via the tuner.

    The save force-disables third-party mods ('Set Default Enabled Mods'), so
    the mod files are injected at runtime instead — verified equivalent.
    """
    probe = exec_lua('print("BRIDGE_PRESENT="..tostring(type(Bridge_Execute)=="function"))', 2.0)
    if any("BRIDGE_PRESENT=true" in l for l in probe.get("output", [])):
        print("bridge already present in game")
    else:
        for name in ("Utils.lua", "StateDump.lua", "CommandIntake.lua"):
            out = exec_lua((MOD_DIR / name).read_text(), 2.5)
            print(f"injected {name}: {[l for l in out.get('output', []) if 'BRIDGE' in l]}")
    # GameCore-context helper for the turn-blocker fix (FinishMoves lives here, not UI).
    gc_helper = (
        "function Bridge_FinishIdle(pid) "
        "local n=0 for _,u in Players[pid]:GetUnits():Members() do "
        "if u:GetMovesRemaining()>0 then UnitManager.FinishMoves(u) n=n+1 end end "
        'print("BRIDGE_FINISHIDLE:"..n) return n end '
        'print("BRIDGE_GCHELPER_READY")'
    )
    out = exec_lua(gc_helper, 2.0, ctx=GAMECORE_CONTEXT)
    print(f"injected GameCore helper: {[l for l in out.get('output', []) if 'BRIDGE' in l]}")
    exec_lua("Bridge_DumpState()", 2.0)  # prime the first state snapshot


def local_pid_of(state):
    for p in state.get("players", []):
        if p.get("isLocal"):
            return p.get("id", 0)
    return 0


def main():
    BRIDGE_DIR.mkdir(exist_ok=True)
    print(f"driver up; bridge dir = {BRIDGE_DIR}")
    inject_bridge()
    last_turn = None
    while True:
        state = extract(drain_lines(), "BRIDGE_STATE:")
        if state is None:
            time.sleep(2)
            continue
        STATE_FILE.write_text(json.dumps(state, indent=2))
        turn = state.get("turn")
        if turn == last_turn:
            time.sleep(2)
            continue
        last_turn = turn
        pid = local_pid_of(state)
        print(f"=== turn {turn} (local player {pid}) ===")

        history = []
        for n in range(1, MAX_ACTIONS_PER_TURN + 1):
            action = decide(state, history)
            print(f"action {n}/{MAX_ACTIONS_PER_TURN}: {action}")
            res = run_action(action, n, local_pid=pid)
            print(f"  result: {res}")
            history.append({"action": action, "result": res})
            if action.get("action") == "end_turn":
                break
        else:
            print("action cap hit — forcing end_turn")
            run_action({"action": "end_turn"}, MAX_ACTIONS_PER_TURN + 1, local_pid=pid)


if __name__ == "__main__":
    main()
