# Every shortcoming in how the bridge plays Civ 6

Compiled 2026-07-23 from: loss #1 retrospective (Kongo, t174–464, science-victory defeat),
loss #2 report (Scythia, t1–361, 5th of 6 at stop), win_domination.py source autopsy,
play logs, and policy state. This is the checklist the research + rebuild must clear.

## A. Strategic layer (why the games were actually lost)

- **A1. No threat model until it is too late.** Loss #1: zero military logic, invasion
  unnoticed, 3 cities + 13 units gone in one cycle. Loss #2: whole army committed to one
  siege, three open cities behind it. Defense was always reactive, added mid-campaign.
- **A2. Economy is an afterthought.** Loss #1: 1387 gold hoarded while purchases silently
  failed. Loss #2: treasury hit 0 → engine auto-disbanded 16 units AT PEACE (army 23→7).
  No gold-per-turn management, no maintenance awareness, no deficit projection.
- **A3. Wrong strategy for the position, never re-evaluated.** Science-tall from 3 cities
  with a 170-turn deficit (loss #1); domination pushed while 5th in cities (loss #2).
  No periodic "are we winning this way?" assessment, no victory-progress tracking of rivals
  (Vietnam's science win was never seen coming).
- **A4. Overextension without consolidation.** Loss #2 peak: 9 cities, largest empire,
  immediately followed by collapse — new conquests never garrisoned/walled/loyalty-managed.
- **A5. Single-front thinking.** War targeting picks one target; no border watch on the
  other neighbors, no standing home guard (doctrine now exists as regroup/hysteresis but
  is reactive — triggers at army<=REGROUP_BELOW, i.e. after the bleeding).
- **A6. No win-condition pacing.** No benchmarks (cities by t50, science by t100, army CS
  by era). Drift is invisible until the scoreboard says 5th of 6.

## B. Unused game systems (entire subsystems the runner never touches)

- **B1. Governors** — never assigned. Magnus (+chops/settler pump), Pingala (science/culture),
  Victor (defense), Liang. Free, compounding, unused.
- **B2. Eurekas/Inspirations** — 40% tech / civic discounts, many cheaply engineerable
  (meet civ, 3 cities, kill with slinger, build X). Static queues ignore boosts entirely.
- **B3. Builder improvements** — built=0 across two campaigns (defect D1). Tile yields,
  the entire terrain economy, forfeited.
- **B4. Unit promotions** — never taken. Veteran units fight at base strength; promotion
  points expire unused.
- **B5. Trade routes** — never run. Gold/food/production per route + roads, forfeited.
- **B6. City-states / envoys** — never sent. Free yields per envoy, suzerain bonuses
  (including unique luxuries/military), forfeited. City-states even blocked settling once.
- **B7. Religion/pantheon** — never founded, never picked a pantheon. A free permanent
  yield bonus (e.g. +1 prod per mine) left on the table every game.
- **B8. Great People** — points accrue, never spent/earned deliberately; rivals harvest them.
- **B9. Chops/harvests** — never used. The single biggest production accelerator in the
  game (forest/stone/jungle into settlers, wonders, army) unavailable.
- **B10. Amenities/housing** — invisible to the state dump; growth silently caps, war
  weariness silently compounds.
- **B11. Loyalty** — invisible; conquered cities can flip; free-city rebellions unmodeled.
- **B12. Era score / ages** — invisible; dark-age loyalty spirals and golden-age boosts
  both ignored.
- **B13. Navy** — nothing. Loss #2's domination plan was mathematically unwinnable:
  2 rival capitals across water, zero naval capability planned or built.
- **B14. Barbarians** — last game had them OFF (a crutch). Standard settings have them ON:
  no camp-clearing logic, no early-defense doctrine, no scout-report reaction exists.
- **B15. Diplomacy beyond war/peace** — no grievance management, no casus belli (surprise
  wars taken by default = max warmonger penalties), no alliances/friendships, no trading
  (luxury-for-luxury, gold deals — the AI pays real gold for duplicate luxuries).
- **B16. Spies** — never used; late-game rivals' spaceports can be sabotaged (the direct
  counter to the loss-#1 scenario).

## C. Code defects (found by source autopsy, confirmed by logs)

- **C1. Builders built=0 (Bridge_Improve).** Only attempts to build on the tile the
  builder stands on; the fallback walks to "nearest unimproved owned tile" with NO check
  that any improvement is legal there, and re-decides every turn. Builders wander
  perpetually. Missing: (tile, improvement) pair planning, persistence of the plan,
  REPAIR for pillaged tiles, charge awareness, danger avoidance.
- **C2. Massing deadlock 1–2/8 (play_turn war branch).** Army gathers at staging point
  (2/3 toward target) but `massed` counts units within RALLY_RADIUS of the TARGET.
  Units reaching the staging point never satisfy the assault trigger → permanent
  "massing" state. The t291+ siege of Manaus ran 70 turns in this state.
- **C3. Funnel/spread pathology (Bridge_WarStep).** Historical: all units to one adjacent
  tile (1 attack/turn from 16 units); the ring-spread fix then scattered the rally.
  Needs deterministic ring assignment around the objective with per-unit slots.
- **C4. Static tech/civic queues.** Fixed lists in code; no boost adaptation, no
  era-appropriate re-planning, wanders into fallback (`options[0]`) once the list is
  exhausted (~Gunpowder). Loss #1's fallback was literally UNIT_WARRIOR-era items.
- **C5. Turn pace 60–150s, degrading to ~2.5 min/turn late.** ~11h for 361 turns. Sleeps
  are conservative and serial; end-turn poll is 2s×150s worst-case; every ex() pays a
  fixed wait. A full 500-turn game at late-game pace is a full day of wall clock.
- **C6. No runner-side saves.** The 11h campaign wrote zero saves from the runner; only
  engine autosave (to the OTHER user dir, by luck) saved the campaign when Windows Update
  killed the machine mid-turn. Need: periodic named save via tuner + verified on disk.
- **C7. No watchdog / crash recovery.** Runner dies with the game/reboot; nothing restarts
  or resumes it. (TaskStop also leaves orphan runners — kill-by-cmdline is manual lore.)
- **C8. pick_target ignores reachability.** Targets nearest rival capital by hex distance —
  including across water (loss #2's impossible p2/p4 targets) — no landmass/embark check.
- **C9. Purchase loop caps at 3/turn globally** and only buys units/walls; can't gold-buy
  builders/settlers/districts when that is optimal; MIN_PURCHASE_DROP heuristic can
  false-negative cheap items (warrior ~40g < threshold?) — verify threshold vs cheapest buy.
- **C10. No citizen/tile management** — cities work whatever the engine defaults to;
  no district adjacency optimization on placement (Bridge_BuildDistrict takes first legal
  plot from GetOperationTargets, not the best-adjacency plot).
- **C11. End-turn blockers are handled by force** (FinishIdle in retry branch cancels
  multi-turn paths — a known campaign-killer, mitigated but the root remains: no
  distinction between "unit needs orders" and "path in progress").
- **C12. State dump gaps** (driver-side): no yields/turn, no housing/amenities/loyalty,
  no boost status, no era score, no rival victory progress, no tile data cache, no
  promotion availability, no charges. The policy is blind to most of section B.

## D. Process/infrastructure

- **D1. Windows Update killed the last campaign** mid-turn (forced restart 10:58 AM).
  Mitigation is a Duncan decision (active hours / pause during runs); runner-side
  mitigation is C6 (frequent saves) + C7 (resume).
- **D2. Single tuner socket, single consumer.** Ad-hoc probing during a run corrupts the
  runner's parsing (documented). Any new telemetry must go through the daemon queue, not
  a second connection.
- **D3. The one unautomatable click.** Save-load leader splash "CONTINUE GAME" needs a
  physical click (re-verified twice). New-game flow avoids it (hosted via Lua) — keep
  preferring the new-game path for autonomy; save-resume needs Duncan for one click.
- **D4. Dual user dirs** (AppData = options/logs/cache, Documents = saves/HoF) — now
  documented; all tooling must reference the right root (engine autosaves land in
  Documents\My Games\...\Saves\Single\auto).

## E. What already works (do not break)

- Tuner transport + daemon (single-instance lock), reconnect-on-load recipe
- Verify-by-state-change discipline (production hash, treasury delta, IsAtWarWith,
  position diffs) — non-negotiable, extend to every new system
- Popup/diplo modal sweeping in both turn-active and AI-round branches
- Engine-validated production chooser + blacklist on silent refusal
- Hysteresis on all mode switches (broke/solvent, regroup/resume)
- Settler legality via engine ops targets + real hex distance + all-players blocking
- War/peace via PlayerOperations verified by IsAtWarWith
- Capital founded in place on t1

## F. Fix priority (impact-ranked, pre-research; research may reorder)

1. C2+C3 (army actually fights) — or choose a victory path that de-emphasizes tactics
2. C1+B3 (builders/economy) + B1 governors + B9 chops — the production engine
3. B2+C4 (boost-aware dynamic tech/civic planning)
4. A1/A5 (standing defense doctrine: walls at borders, garrison minimums, threat radar)
5. A2 (economy model: GPT floor, maintenance projection, spend rules)
6. B5/B6/B7 (trade routes, envoys, pantheon — cheap compounding yields)
7. C6+C7 (saves + resume — no more lost campaigns)
8. A3/A6 (victory pacing dashboard + rival progress tracking)
9. C8 (reachability-aware targeting) + B13 (navy or land-only victory condition)
10. C5 (turn pace)
