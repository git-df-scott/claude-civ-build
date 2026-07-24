"""Wait for InGame context, then run the two verification probes."""
import time
from tuner import Tuner

import sys
t = Tuner(port=int(sys.argv[1]) if len(sys.argv) > 1 else 4318)
msgs = t.handshake()

def states_from(msgs):
    """Parse latest 'L' state list into {name: index}."""
    latest = None
    for tag, p in msgs:
        if p.startswith("L\x00") or (tag == 4 and "\x00" in p and p[0].isdigit()):
            latest = p[2:] if p.startswith("L\x00") else p
    if latest is None:
        return {}
    parts = latest.split("\x00")
    d = {}
    for i in range(0, len(parts) - 1, 2):
        d[parts[i + 1]] = int(parts[i])
    return d

states = states_from(msgs)
print("initial states:", states)

# wait for InGame
deadline = time.time() + 180
while "InGame" not in states and time.time() < deadline:
    m = t.recv_msgs(3.0)
    if m:
        s = states_from(m)
        if s:
            states = s
print("states now:", states)
if "InGame" not in states:
    raise SystemExit("InGame context never appeared")

idx = states["InGame"]
print(f"InGame index = {idx}")

def run(lua, wait=3.0):
    out = []
    for tag, p in t.cmd(idx, lua, wait):
        if p.startswith("O\x00"):
            out.append(p[2:])
    return out

time.sleep(5)

print("== basic ==")
for line in run('print("turn=" .. tostring(Game.GetCurrentGameTurn()) .. " me=" .. tostring(Game.GetLocalPlayer()))'):
    print(line)

print("== Q1: io/os availability ==")
for line in run(
    'print("io=" .. type(io) .. " os=" .. type(os) .. " loadfile=" .. type(loadfile) .. " dofile=" .. type(dofile))'
):
    print(line)

for line in run(
    'if type(io)=="table" then '
    'local ok,err = pcall(function() local f=assert(io.open("C:/Users/Duncan/civ_bridge/probe_io_test.txt","w")) f:write("hello") f:close() end) '
    'print("io_write ok=" .. tostring(ok) .. " err=" .. tostring(err)) '
    'else print("io not a table") end'
):
    print(line)

print("== alternative channels ==")
for line in run(
    'local n={} for k in pairs(_G) do n[#n+1]=k end table.sort(n) print(table.concat(n, ","))', wait=4.0
):
    print(line)
