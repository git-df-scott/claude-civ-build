"""ex.py <state> <wait> <lua...> — send Lua via bridge daemon, print output lines."""
import json
import sys
import urllib.request

state, wait, lua = sys.argv[1], float(sys.argv[2]), " ".join(sys.argv[3:])
r = urllib.request.urlopen(
    urllib.request.Request(
        "http://127.0.0.1:8321/exec",
        json.dumps({"state": state, "lua": lua, "wait": wait}).encode(),
        {"Content-Type": "application/json"},
    ),
    timeout=wait + 30,
)
for line in json.load(r).get("output", []):
    print(line)
