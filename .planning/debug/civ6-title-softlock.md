# Debug session: Civ 6 title-screen soft-lock

**Status:** root cause identified, fix in progress
**Date:** 2026-07-23
**Symptom:** Game stuck on post-launcher title screen; "Play Now" unresponsive; user cannot reach main menu or exit.

## Timeline (all 2026-07-23)

- ~23:00 Jul 22 → 10:55: `win_domination.py` campaign running (Scythia, t1→t361, 11h)
- 10:51: campaign report written (t359)
- 10:55:48: last runner log entry (t361)
- 10:58:32: **winlogon.exe initiated forced restart (Windows Update, NT AUTHORITY\SYSTEM)** — Event 1074
- 11:05:59: boot (Kernel-Power 41: previous shutdown unclean — Event 6008/41)
- 11:06:47: Steam auto-started; 11:08:44: game relaunched
- 11:09:0x: user clicked Play Now — `MainMenu::OnPlayCiv6() PlayNowSave leaving the network session` (Lua.log)
- 11:09:28: logs go silent; shell wedged; all input ignored since

## Root cause

`AppOptions.txt` (in the **AppData** user dir — see "dual user dir" below) contains the
**debug forcing option**:

```
;Forces the game to load only that save file.
PlayNowSave AutoSave_0023
```

Set during Jul 15 bridge experiments and never removed. "Play Now" therefore attempts to
force-load `AutoSave_0023` — which no longer resolves (active save root is the Documents
dir, whose autosave numbering is now 03xx; the AppData copy of AutoSave_0023 is a stale
Jul 15 save). The load flow runs content-reconfigure (Modding.log: "Successfully
reconfigured game" → "Set Default Enabled Mods" = load abandoned, shell reset), then dies,
leaving `g_waitingForContentConfigure=true` dangling in the JoiningRoom layer (last
Lua.log lines). While that flag is set the shell ignores all further input → soft-lock.

Same wedge signature existed pre-reboot (tuner_frames.log 10:57–10:58: repeated
`JoiningRoom: OnFinishedGameplayContentConfigure() g_waitingForContentConfigure=true` with
frontend context list) — the Windows-Update shutdown pulled the game to the frontend and
it wedged there too.

## Evidence

- `AppData\...\Logs\Lua.log` (this boot): OnPlayCiv6 → LoadScreen → 2× content-configure wait → silence
- `AppData\...\Logs\Modding.log` tail: second configure SUCCEEDS then "Set Default Enabled Mods" (= flow abandoned)
- `AppData\...\AppOptions.txt:114`: `PlayNowSave AutoSave_0023`
- AppData saves: newest = AutoSave_0023 **Jul 15 23:14** (997KB, well-formed, stale)
- Documents saves: AutoSave_0352–0361, **10:34–10:54 today** — campaign survived to t361
- netstat: tuner 4318 LISTENING, no connections — no bridge process interfering
- Event log: 1074 (winlogon restart 10:58), 41+6008 (unclean shutdown)

## Dual user dir (secondary finding)

Game splits data: options/logs/cache/Mods.sqlite + mod dir → `AppData\Local\Firaxis Games\...`;
autosaves + HallofFame.sqlite → `Documents\My Games\...`. Both touched by the live process
this boot. Bridge mods: `BridgeProbe` in AppData Mods (live), `CivAgentBridge` only in
Documents Mods (stale copy, never loaded — bridge is tuner-based, no mod needed).

## Fix (applied)

1. Backup: `civ_bridge\backups\2026-07-23\` — both save dirs + AppOptions.txt
2. Hard-kill wedged game PID 1568 (hard kill also prevents AppOptions rewrite-on-exit)
3. Comment out `PlayNowSave AutoSave_0023` in AppData AppOptions.txt
4. Relaunch via Steam; verify title → Play Now → main menu responds
5. Verify campaign resumable: Load Game shows/loads Documents AutoSave_0361

## Verification results

(pending)

## Prevention

- Runner must write its own periodic named saves (campaign had zero saves in its own root
  until engine autosave saved it by luck — actually engine autosave DID run; runner-side
  named saves still wanted for cross-era resilience)
- Windows Update forced restarts mid-campaign: advise Duncan on active hours / pause
  updates before long runs (system setting — Duncan's call, not automated)
- Never leave PlayNowSave set outside a deliberate experiment
