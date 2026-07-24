"""One persistent tuner session: wait for menu, load save, wait for InGame, probe."""
import sys
import time
from tuner import Tuner

t = Tuner(retries=80)  # waits up to ~4 min for 4318
print("connected", flush=True)
msgs = t.handshake()

def merge_states(msgs, states):
    for tag, p in msgs:
        body = None
        if p.startswith("L\x00"):
            body = p[2:]
        elif tag == 4 and "\x00" in p and p[:1].isdigit():
            body = p
        if body is not None:
            parts = body.split("\x00")
            states = {parts[i + 1]: int(parts[i]) for i in range(0, len(parts) - 1, 2)}
    return states

states = merge_states(msgs, {})
print("states:", states, flush=True)

# Wait for MainMenu context (actively re-query)
deadline = time.time() + 180
while "MainMenu" not in states and time.time() < deadline:
    t.send(4, "LSQ:")
    states = merge_states(t.recv_msgs(3.0), states)
if "MainMenu" not in states:
    sys.exit("MainMenu never appeared")

lua_load = (
    'local p = {'
    'Location = SaveLocations.LOCAL_STORAGE,'
    'Type = SaveTypes.SINGLE_PLAYER,'
    'FileType = SaveFileTypes.GAME_STATE,'
    'IsAutosave = true,'
    'IsQuicksave = false,'
    'Directory = SaveDirectories.DEFAULT,'
    'Name = "AutoSave_0023"};'
    'print("LOADRESULT=" .. tostring(Network.LoadGame(p, ServerType.SERVER_TYPE_NONE)))'
)
time.sleep(8)  # let the menu settle
msgs = t.cmd(states["MainMenu"], lua_load, wait=5.0)
for tag, p in msgs:
    if p.startswith("O\x00"):
        print("OUT:", p[2:], flush=True)
states = merge_states(msgs, states)

# Keep the socket alive through the load; wait for InGame (re-query too)
deadline = time.time() + 300
while "InGame" not in states and time.time() < deadline:
    t.send(4, "LSQ:")
    states = merge_states(t.recv_msgs(3.0), states)
print("states after load:", states, flush=True)
if "InGame" not in states:
    sys.exit("InGame never appeared")

idx = states["InGame"]
print("InGame idx", idx, flush=True)
time.sleep(10)  # let the map finish

def run(lua, wait=4.0):
    for tag, p in t.cmd(idx, lua, wait):
        if p.startswith("O\x00"):
            print("OUT:", p[2:], flush=True)

print("== basic ==", flush=True)
run('print("turn=" .. tostring(Game.GetCurrentGameTurn()) .. " me=" .. tostring(Game.GetLocalPlayer()))')

print("== Q1 io/os ==", flush=True)
run('print("io=" .. type(io) .. " os=" .. type(os) .. " loadfile=" .. type(loadfile) .. " require=" .. type(require))')
run(
    'if type(io)=="table" then '
    'local ok,err = pcall(function() local f=assert(io.open("C:/Users/Duncan/civ_bridge/probe_io_test.txt","w")) f:write("hello from ingame") f:close() end) '
    'print("io_write ok=" .. tostring(ok) .. " err=" .. tostring(err)) '
    'else print("NO io table") end'
)

print("== globals ==", flush=True)
run('local n={} for k in pairs(_G) do n[#n+1]=k end table.sort(n) print(table.concat(n,","))', wait=5.0)

print("== Q2 events: register hooks, then end turn remotely later ==", flush=True)
run(
    'BP = {} '
    'local function hk(name, ev) '
    'if ev == nil then print("MISSING " .. name) return end '
    'ev.Add(function(a,b) print("FIRED " .. name .. " a=" .. tostring(a) .. " b=" .. tostring(b)) end) '
    'print("hooked " .. name) end '
    'hk("TurnBegin", Events.TurnBegin) '
    'hk("TurnEnd", Events.TurnEnd) '
    'hk("LocalPlayerTurnBegin", Events.LocalPlayerTurnBegin) '
    'hk("LocalPlayerTurnEnd", Events.LocalPlayerTurnEnd) '
    'hk("PlayerTurnActivated", Events.PlayerTurnActivated) '
    'hk("PlayerTurnDeactivated", Events.PlayerTurnDeactivated) '
    'hk("RemotePlayerTurnBegin", Events.RemotePlayerTurnBegin) '
    'hk("RemotePlayerTurnEnd", Events.RemotePlayerTurnEnd)'
)

print("== end the local player turn to watch events ==", flush=True)
run('UI.RequestAction(ActionTypes.ACTION_ENDTURN) print("endturn requested")', wait=2.0)
# collect event traffic for a while (AI turns run)
end = time.time() + 45
while time.time() < end:
    for tag, p in t.recv_msgs(3.0):
        if p.startswith("O\x00"):
            print("OUT:", p[2:], flush=True)

print("done — keeping socket open, sleeping 5s", flush=True)
time.sleep(5)
