import time
from tuner import Tuner

t = Tuner(retries=5)
msgs = t.handshake()
latest = None
for tag, p in msgs:
    if tag == 4 and "\x00" in p and p[:1].isdigit():
        latest = p
parts = latest.split("\x00")
states = {parts[i + 1]: int(parts[i]) for i in range(0, len(parts) - 1, 2)}
idx = states["InGame"]
print("InGame idx:", idx, flush=True)

def run(lua, wait=4.0, label=""):
    print(f"--- {label}", flush=True)
    for tag, p in t.cmd(idx, lua, wait):
        if p.startswith("O\x00"):
            print("OUT:", p[2:], flush=True)

run('print("turn=" .. tostring(Game.GetCurrentGameTurn()) .. " me=" .. tostring(Game.GetLocalPlayer()))', label="basic")
run('print("io=" .. type(io) .. " os=" .. type(os) .. " loadfile=" .. type(loadfile) .. " require=" .. type(require))', label="io types")
run(
    'if type(io)=="table" then '
    'local ok,err = pcall(function() local f=assert(io.open("C:/Users/Duncan/civ_bridge/probe_io_test.txt","w")) f:write("hello from ingame") f:close() end) '
    'print("io_write ok=" .. tostring(ok) .. " err=" .. tostring(err)) '
    'else print("NO io table") end',
    label="io write",
)
run('local n={} for k in pairs(_G) do n[#n+1]=k end table.sort(n) print(table.concat(n,","))', wait=5.0, label="globals")
