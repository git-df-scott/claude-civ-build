from tuner import Tuner

t = Tuner()
print(t.handshake()[-1][1][:200])

lua = (
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
for tag, m in t.cmd(24, lua, wait=4.0):
    print(f"[{tag}] {m!r}")
