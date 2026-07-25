"""recover_game.py — bring Civ 6 back from a crash or cold start, unattended.

Built 2026-07-24 after the control run's game died at turn 500 with an
EXCEPTION_ACCESS_VIOLATION and had to be recovered by hand.

WHY THIS EXISTS / THE TWO TRAPS IT ENCODES
------------------------------------------
1. **The tuner listener only re-opens during the load transition.** Civ 6's
   tuner (port 4318) accepts exactly ONE client, and if that client closes
   while the game sits idle, the game NEVER listens again — only a restart
   recovers it. The single exception is the brief rebuild window while a save
   is loading. So the recipe is: connect at the menu, issue the load, and the
   moment `LoadScreen` appears in the state list, force a client-side
   reconnect. The redial lands in that window and yields an **in-game-born**
   connection, which is the only kind that can execute commands.

   A connection made at the MENU and carried through a load goes **deaf**: the
   state list still answers (so everything looks healthy — 99 states, InGame
   present) but no Lua ever executes and every exec returns []. That is the
   failure this script exists to avoid, and it costs a full game restart.

   Reconnecting AFTER the load completes is too late — the listener is then
   dead permanently.

2. **The Firaxis Crash Reporter blocks relaunch.** After a crash, a
   "Firaxis Crash Reporter" dialog sits on screen and the game will not start
   while it is up. We kill it rather than clicking it, so no synthetic input is
   needed (Civ 6 ignores injected clicks anyway, but this dialog is a plain
   Win32 window and killing its process is deterministic).

Usage:
    python recover_game.py                 # load the newest autosave
    python recover_game.py AutoSave_0500   # load a specific save
    python recover_game.py Progress_t090 --named   # a named (non-auto) save
"""
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

DAEMON = "http://127.0.0.1:8321"
EXE = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization VI"
           r"\Base\Binaries\Win64Steam\CivilizationVI_DX12.exe")
AUTO_DIR = Path(r"C:\Users\Duncan\Documents\My Games\Sid Meier's Civilization VI\Saves\Single\auto")


def log(m):
    print(f"[{time.strftime('%H:%M:%S')}] {m}", flush=True)


def get(path, timeout=20):
    return json.load(urllib.request.urlopen(DAEMON + path, timeout=timeout))


def post(path, body, timeout=60):
    req = urllib.request.Request(DAEMON + path, json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def ps(script):
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                          capture_output=True, text=True, timeout=180).stdout.strip()


def civ_running():
    return ps("(Get-Process CivilizationVI_DX12 -ErrorAction SilentlyContinue | "
              "Measure-Object).Count") .strip() not in ("0", "")


def kill_civ_and_crash_dialog():
    """Kill the game AND the Firaxis Crash Reporter that blocks relaunch."""
    ps("Get-Process CivilizationVI_DX12 -ErrorAction SilentlyContinue | Stop-Process -Force")
    ps("Get-Process | Where-Object { $_.MainWindowTitle -like '*Crash*' -or "
       "$_.Name -like '*CrashRep*' } | Stop-Process -Force -ErrorAction SilentlyContinue")
    time.sleep(4)


def launch_civ():
    # Launch through Steam, NOT the exe directly: the exe exits immediately
    # under Steam DRM. Steam's DX11/DX12 chooser does not appear for this
    # appid launch, so no click is required.
    ps('Start-Process "steam://rungameid/289070"')
    for _ in range(48):
        if civ_running():
            return True
        time.sleep(5)
    return False


def wait_daemon_connected(timeout=240):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if get("/states").get("connected"):
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def wait_for_lobby(timeout=300):
    """Wait until the MENU is actually ready, not merely until the socket opened.

    The daemon connects while the game is still booting, at which point the
    state list is just {FrontEnd, Main State, ...} with no `Lobby` context.
    Firing Network.LoadGame into `Lobby` then goes nowhere — silently, with no
    error — and the script waits forever for an InGame that will never come.
    Observed 2026-07-24: load issued at FrontEnd, 6 states, nothing happened.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            d = get("/states", timeout=8)
            st = d.get("states", {})
            if d.get("connected") and "Lobby" in st:
                return True
        except Exception:
            pass
        time.sleep(3)
    return False


def newest_autosave():
    saves = sorted(AUTO_DIR.glob("AutoSave_*.Civ6Save"), key=lambda f: f.stat().st_mtime)
    return saves[-1].stem if saves else None


def load_save(name, is_auto=True):
    """Issue the load, then reconnect the INSTANT LoadScreen appears."""
    lua = (f'Network.LoadGame({{Location=SaveLocations.LOCAL_STORAGE,'
           f'Type=SaveTypes.SINGLE_PLAYER,FileType=SaveFileTypes.GAME_STATE,'
           f'IsAutosave={"true" if is_auto else "false"},IsQuicksave=false,'
           f'Directory=SaveDirectories.DEFAULT,Name="{name}"}}, ServerType.SERVER_TYPE_NONE)')
    post("/exec", {"state": "Lobby", "lua": lua, "wait": 2.0})
    log(f"load issued for {name}; watching for LoadScreen")

    # The reconnect must land DURING the load, not after. Poll fast.
    fired = False
    deadline = time.time() + 180
    while time.time() < deadline:
        try:
            st = get("/states", timeout=8).get("states", {})
        except Exception:
            time.sleep(0.5)
            continue
        if not fired and "LoadScreen" in st:
            log("LoadScreen seen -> forcing reconnect INTO the rebuild window")
            try:
                urllib.request.urlopen(DAEMON + "/reconnect", timeout=3)
            except Exception:
                pass          # the request usually times out by design; the close is what matters
            fired = True
        if fired and "InGame" in st and get("/states").get("connected"):
            return True
        time.sleep(0.5)
    return False


def verify():
    """Prove the connection can actually EXECUTE, not merely that it looks healthy.

    This is the whole point: a deaf connection still reports connected=True and
    lists ~99 states. Only a real round-tripped print proves anything.
    """
    for _ in range(8):
        out = post("/exec", {"state": "InGame", "wait": 3.0,
                             "lua": 'print("RECOVER_OK="..Game.GetCurrentGameTurn())'}).get("output", [])
        for line in out:
            if "RECOVER_OK=" in line:
                return int(line.split("RECOVER_OK=")[1].split()[0])
        time.sleep(2)
    return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    is_auto = "--named" not in sys.argv
    name = args[0] if args else None

    log("=" * 55)
    if civ_running():
        log("Civ is running; killing it for a clean recovery")
    kill_civ_and_crash_dialog()

    if not launch_civ():
        log("FATAL: Civ did not start")
        return 1
    log("Civ process up; waiting for the daemon to connect at the menu")

    if not wait_daemon_connected():
        log("FATAL: daemon never connected (is bridge_daemon.py running?)")
        return 1
    log("daemon connected; waiting for the Lobby context to exist")
    if not wait_for_lobby():
        log("FATAL: menu never produced a Lobby context")
        return 1
    log("Lobby ready")

    if name is None:
        name = newest_autosave()
        is_auto = True
        if not name:
            log("FATAL: no autosave found")
            return 1
    log(f"loading {name}")

    if not load_save(name, is_auto):
        log("FATAL: never reached InGame with a live connection")
        return 1

    turn = verify()
    if turn is None:
        log("FATAL: in game but the connection is DEAF (exec returns nothing).")
        log("       The reconnect missed the rebuild window. Re-run this script.")
        return 1
    log(f"RECOVERED — in game at turn {turn}, connection verified by round-trip")
    return 0


if __name__ == "__main__":
    sys.exit(main())
