"""Offline checks for bridge_daemon: line cap, frame-log rotation, mark clamp."""
import os
import sys
import tempfile

sys.path.insert(0, r"C:\Users\Duncan\civ_bridge")
os.chdir(tempfile.mkdtemp())  # frame log writes go here, not the real one

import bridge_daemon as bd

d = bd.TunerDaemon()

# 1. line cap: feed 6000 output frames, buffer must stay <= MAX_LINES
for i in range(6000):
    d.handle(3, "O\x00line %d" % i)
assert len(d.lines) <= bd.MAX_LINES, len(d.lines)
assert d.lines[-1] == "line 5999"
print("line cap OK: %d lines buffered" % len(d.lines))

# 2. mark clamp: simulate exec_lua's slice after a trim
mark = 10_000  # stale mark bigger than buffer
mark = min(mark, len(d.lines))
assert d.lines[mark:] == []
print("mark clamp OK")

# 3. frame-log rotation: shrink threshold, force rotation
bd.FRAME_LOG_MAX = 2000
for i in range(200):
    d.handle(3, "O\x00" + "x" * 100)
assert os.path.exists(bd.FRAME_LOG + ".1"), "rotation did not happen"
assert os.path.getsize(bd.FRAME_LOG) < 2000 + 200
print("rotation OK: %s.1 = %d bytes, live = %d bytes" % (
    bd.FRAME_LOG, os.path.getsize(bd.FRAME_LOG + ".1"), os.path.getsize(bd.FRAME_LOG)))

# 4. state-list parse still works
d.handle(4, "0\x00MainMenu\x001\x00InGame")
assert d.states == {"MainMenu": 0, "InGame": 1}, d.states
print("state parse OK")
print("ALL OK")
