# claude-civ-build

A bridge that lets Claude play Sid Meier's Civilization VI, and the runners that use it.

## How it works

Civ 6 ships a FireTuner debug socket (port 4318) that accepts **exactly one** client.
`bridge_daemon.py` owns that socket and re-exposes it as HTTP on `127.0.0.1:8321`. Bridge Lua is
**injected at runtime** into the game's live `InGame` context — there is no mod to install.

```
Civ 6  <--4318-->  bridge_daemon.py  <--8321 HTTP-->  runner (win_science.py)
```

## Running

```bash
python bridge_daemon.py          # 1. start the daemon (game must be running)
python win_science.py 500        # 2. start the player
```

## Non-negotiable rules

These were each learned the expensive way. Do not relax them.

1. **Verify by state change, never by the ack.** Civ 6's `CanStart*` calls are *permissive* —
   they return true for actions that then silently do nothing. `ok=true` means nothing. Check
   that the city count, gold, or production hash actually moved.
2. **One tuner client.** Never probe Lua while a runner is live — they share the single socket
   and corrupt each other's output. Stop the runner first.
3. **Stopping a runner:** `TaskStop` kills the wrapper and leaves Python running. Kill the
   process itself, or you will get two runners fighting over the game.
4. **Syntax-check any file whose process is still running.** A running process cannot tell you
   the file on disk has stopped parsing.
5. **Mods load from `%LOCALAPPDATA%\Firaxis Games\...\Mods`; saves from
   `Documents\My Games\...\Saves`.** The directories split by purpose, not as a unit.

## Layout

| Path | What |
|---|---|
| `bridge_daemon.py` | Holds the tuner socket, serves HTTP |
| `win_science.py` | Current runner — science victory, defense-only |
| `play_to_end.py`, `play_batch.py` | Older runners; still the source of shared helpers |
| `lua/` | Vendored bridge Lua (injected at runtime) |
| `probes/` | One-off diagnostics. `test_daemon.py` runs with no game |
| `PLAN-two-tier-brain.md` | Spec for the Sonnet/Opus two-tier player |
| `research-report.md` | Strategy research — **note: written for Gathering Storm; we play base game** |
| `SHORTCOMINGS-2026-07-23.md` | Post-mortem of the two lost campaigns |

## Ruleset

Verified live 2026-07-24: `RULESET_STANDARD` (base Civ VI — no Rise & Fall, no Gathering Storm).
Governors, loyalty, grievances and era score **do not exist**. Science victory is the Mars
colony, not Exoplanet/laser stations.

## Status

Bridge working. Two campaigns lost (score defeat, then a collapse under invasion). Third running.
See `PLAN-two-tier-brain.md` for where this is going.
