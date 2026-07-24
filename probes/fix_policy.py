"""Repair civ_policy_state.json after a BOM was written into it, and drop the
stale sticky war target. PowerShell 5.1's Set-Content -Encoding utf8 emits a
BOM that json.loads rejects at char 0."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent.parent / "civ_policy_state.json"
raw = p.read_bytes()
print("first bytes:", raw[:8])
text = raw.decode("utf-8-sig")          # utf-8-sig strips the BOM if present
data = json.loads(text)
removed = data.pop("target", None)
print("removed stale target:", removed)
p.write_text(json.dumps(data, indent=2), encoding="utf-8")
print("rewrote clean, keys:", sorted(data)[:12])
json.loads(p.read_text())               # prove it parses back
print("verified: file parses")
