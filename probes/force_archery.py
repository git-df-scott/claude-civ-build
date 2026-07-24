"""Switch research to Archery now (Civ 6 keeps partial progress on the old tech).
Archery is the gate on Horseback Riding in this ruleset."""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from play_batch import cmd, ex  # noqa: E402


def current():
    for _ in range(4):
        out = ex('local t=Players[Game.GetLocalPlayer()]:GetTechs():GetResearchingTech() '
                 'print("R:"..tostring(t >= 0 and GameInfo.Technologies[t].TechnologyType or "IDLE"))', 3.0)
        for l in out:
            if "R:" in l:
                return l.split("R:", 1)[1].strip()
    return "?"


print("before:", current())
print("ack:", cmd({"id": 8801, "action": "set_research", "tech": "TECH_ARCHERY"}, 3.0))
print("after:", current())
