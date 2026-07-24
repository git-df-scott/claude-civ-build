"""load_save_daemon.py <SaveName> — headless save load with the reconnect-timing dance.

Goes through the running bridge_daemon (HTTP 8321). Do NOT use the older
probes/load_save.py: it opens its OWN tuner socket, and the game accepts exactly
one client — connecting a second one kills the daemon's connection, and the game
never re-listens after a client close, so recovery costs a full game restart.

The tuner connection made at the main menu goes DEAF after a save load (the game
stops reading the socket). The ONLY window in which the listener re-opens is the
load transition itself, so this watches /drain for the LoadScreen marker and hits
/reconnect the moment it appears. Reconnecting after the load completes leaves
the listener dead until a game restart.

Usage: python probes/load_save_daemon.py AutoSave_0174
"""
import json
import sys
import time
import urllib.request

DAEMON = "http://127.0.0.1:8321"


def http(path, body=None, timeout=60):
    req = urllib.request.Request(
        DAEMON + path,
        json.dumps(body).encode() if body is not None else None,
        {"Content-Type": "application/json"},
    )
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def exec_lua(ctx, lua, wait=2.0):
    return http("/exec", {"state": ctx, "lua": lua, "wait": wait}, timeout=wait + 60)


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "AutoSave_0174"
    is_auto = "true" if name.lower().startswith("autosave") else "false"

    http("/drain")  # clear stale lines so the LoadScreen match is fresh
    lua = (
        "Network.LoadGame({Location=SaveLocations.LOCAL_STORAGE,"
        "Type=SaveTypes.SINGLE_PLAYER,FileType=SaveFileTypes.GAME_STATE,"
        f"IsAutosave={is_auto},IsQuicksave=false,"
        f'Directory=SaveDirectories.DEFAULT,Name="{name}"}}, ServerType.SERVER_TYPE_NONE)'
    )
    print(f"loading {name} (IsAutosave={is_auto})...", flush=True)
    exec_lua("Lobby", lua, wait=1.0)

    # Drop the (now doomed) menu-born connection IMMEDIATELY and let the daemon's
    # 0.5s redial loop hammer 4318 for the whole load. Waiting for the LoadScreen
    # marker before reconnecting missed the rebuild window on 2026-07-19 and cost
    # a game restart; closing up-front means we are already dialing when it opens.
    print("  -> /reconnect (immediate)", flush=True)
    print("  reconnect:", http("/reconnect", timeout=90), flush=True)

    # Let the map finish loading, then confirm CMD actually works in-game.
    for attempt in range(20):
        time.sleep(5)
        st = http("/states")
        if "InGame" in st.get("states", {}):
            out = exec_lua("InGame", 'print("MIDLOAD_TEST TURN="..Game.GetCurrentGameTurn())', 3.0)
            hit = [l for l in out.get("output", []) if "MIDLOAD_TEST" in l]
            if hit:
                print(f"IN-GAME AND ALIVE: {hit[0]}", flush=True)
                return 0
            print(f"  attempt {attempt}: InGame present but CMD mute", flush=True)
        else:
            print(f"  attempt {attempt}: {len(st.get('states', {}))} states, no InGame yet", flush=True)
    print("!! failed to get a working in-game CMD channel", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
