# CivAgentBridge — Retrospective after the first full autonomous game

Written 2026-07-19, after playing a loaded save (turn 174) to a decision with no
human input except one unavoidable mouse click. Supersedes
`report-2026-07-17.md` (archived); the operational recipes live in the
`civ6-bridge` memory file. This is the honest assessment.

**Outcome: DEFEAT at turn 464. Vietnam won a Science Victory. Kongo finished with 1 city.**

---

## 1. The game

### Arc

| Turn | Our cities | Vietnam (p3) | Note |
|---|---|---|---|
| 174 | 3 | 7 | start of session |
| 250 | **7** | 9 | peak — expansion bugs fixed |
| 300 | 4 | 13 | invasion; 3 cities and 13 units lost in one cycle |
| 320 | **1** | 17 | collapse complete |
| 464 | 1 | 18 | Vietnam science victory |

### What worked, game-wise

- **Expansion, once it was actually functional.** 3 → 7 cities in ~70 turns. The
  legal-site finder (real hex distance, all players including city-states) turned
  a settler fleet that had founded nothing for 40+ turns into steady growth.
- **Infrastructure.** Campuses in 5 of 7 cities plus libraries, a university,
  commercial hubs and markets — once districts could actually be placed.
- **Never idling.** Research and civics never stalled; production never wedged
  after the engine-validated chooser replaced the fixed queue.

### What failed, game-wise

- **No military logic at all.** The policy never built or bought defenders, never
  detected threat, never reacted to cities falling. This is the direct cause of
  the loss. A civ that cannot notice it is being invaded cannot survive one.
- **~50 turns of hoarded gold.** Peaked at 1387 unspent while the purchase code
  silently failed (below). That gold was the one real chance at a defence and it
  was still sitting there when the invasion landed.
- **The war footing arrived too late.** Defenders-first priority and gold-delta
  verification went in at t303, after the invasion had started. It bought exactly
  two units before income (~4 gold/turn) made further purchases impossible.
- **Strategy was mis-chosen for the position.** Science-lean tall play was picked
  at t174 while five AI civs had a 170-turn head start and we sat on 3 cities.
  Survival should have outranked science from the first turn, not from t303.
- **Stranded settlers.** Two settlers spent ~40 turns reporting "no legal site"
  because the map was full — pure waste that a "disband or join city" rule fixes.

---

## 2. The backend

### What worked

- **Transport and daemon.** The tuner connection, injection recipe, and HTTP
  daemon held for ~5 hours of continuous play without a reconnect. The
  single-instance lock (`SO_EXCLUSIVEADDRUSE`) refused a second daemon instantly
  — the 2026-07-17 fix, re-verified live.
- **The three pending verification items all passed.** Settler tile scan (105–112
  tiles/settler, ~9 KB each, pcall never degraded), `set_production` gate with no
  DISTRICT_CAMPUS regression, and `purchase` working once its real gate was found.
- **Popup dismissal — a stall class the project had never solved.** Blocking
  full-screen popups (natural wonder, era complete, etc.) halt the turn cycle like
  diplo modals but are not diplomacy sessions. Each has its own Lua context
  exposing `Close()`; calling it there dismisses the popup. Turn 258 unwedged
  instantly. Now swept automatically in both the `A=true` and `A=false` branches.
- **District placement.** `CityManager.GetOperationTargets` returns the legal
  plots (13 for the capital's campus); passing one as `PARAM_X/PARAM_Y` makes
  districts stick.
- **Verify-by-state-change as a discipline.** Every action now confirms via
  production hash, city count, or treasury delta. This is what caught all five
  silent-failure sites.

### What broke

The dominant defect, found in **five separate places**:

> **Every "can I do this?" boolean in the Civ 6 API is permissive. It returns
> `true` for illegal actions, the request acks `ok=true`, and nothing happens.**

| Site | Lies about |
|---|---|
| `CanStartCommand(PURCHASE, bTestOnly=true)` | already purchased this turn; tile stacking; pop requirements |
| `CanStartOperation(FOUND_CITY)` | founding within 3 hexes of any city |
| `CanStartOperation(BUILD)` | district the city already has |
| `set_production` ack | accepts a district, then drops it before the turn rolls |
| `purchase` ack | duplicate building — gold never moves |

Other backend breakage:

- **`FailureReasons` was dead code.** `bTestOnly=true` never returns a results
  table, so the 2026-07-17 "reasons now reported" fix could never fire. The
  `bTestOnly=false` form carries the real validation. **Reasons, not the boolean,
  are the gate** — that rewrite is live-verified.
- **`RequestCommand` is asynchronous.** Gold does not move in the same Lua tick.
  Any same-tick before/after check false-negatives on real purchases; verification
  must be Python-side after a re-dump.
- **`play_batch.py`'s fallback production is `UNIT_WARRIOR`** — obsolete by the
  mid-game, so every city that exhausted its queue would idle forever.
- **Chebyshev distance is not hex distance.** `max(|dx|,|dy|)` silently produced
  illegal settle sites; `Map.GetPlotDistance` is required.
- **`GetAliveMajorIDs()` excludes city-states**, which block founding identically.
  A p7 city-state 3 hexes out silently blocked every found attempt.
- **Loading a save needs a human click.** The leader-intro splash ("CONTINUE
  GAME") parks the load; the state list freezes at 3 states and `InGame` never
  appears. Synthetic input cannot dismiss it (re-verified: cursor landed dead-on
  the button, no effect). **This is the single unautomatable step.**
- **`pkill -f` does not kill Windows Python.** Left a stale runner racing the new
  one over the shared socket. Use `Get-CimInstance Win32_Process` + `Stop-Process`.
- **Concurrent probing corrupts the runner.** One tuner socket is shared, so
  ad-hoc Lua execs interleave with the runner's output and can poison its parsing.
  Stop the runner first — it never touches the game process.

---

## 3. What to learn from this

Ranked by how much they'd have changed the outcome.

1. **Trust no ack. Verify by state change.** This single principle would have
   caught all five silent-failure sites, three of which were individually fatal to
   the strategy. It is now the codebase default and should stay non-negotiable.
2. **Learn the silent-failure signatures.** "Gold rising while purchases report
   success" was visible for ~50 turns before it was read correctly. A monitor
   should alarm on *invariants that should be moving and aren't* — gold, city
   count, production progress — not just on errors. Errors were never emitted;
   that was the whole problem.
3. **Screenshot the game first when anything stalls.** Twice a stall was
   diagnosed by theorising (backgrounded window, reconnect timing) when the screen
   showed the blocker in seconds. Logs and state lists looked *normal* in both
   cases. Cost: ~25 minutes and one unnecessary game restart.
4. **A game-playing policy needs a threat model.** Build/buy priority must respond
   to conditions — rival units near territory, city count dropping — not follow a
   static list. Survival outranks development whenever both are contested.
5. **Match the engine's own math and its own definition of "everyone".** Two
   separate expansion bugs came from using the wrong distance metric and from
   asking for majors when the rule applies to all players. When mirroring an
   engine rule, use the engine's function.
6. **Distinguish "no listener" from "client attached".** Port 4318 showing no
   LISTENING socket is *normal* while the daemon is connected — the game stops
   listening when a client attaches. The genuine dead-listener signature is the
   daemon stuck in **SYN_SENT**. Conflating these cost a game restart.

### Closing the 2026-07-17 open items

| # | Item | Status |
|---|---|---|
| 1 | Fix `purchase` FailureReasons | **Done** — gate on reasons, not the boolean |
| 2 | Settle-site quality from tile yields | **Done** — engine-side scoring, legal sites only |
| 3 | Faster turn loop | Partial — ~23–60s/turn depending on empire size |
| 4 | Builder actions (BUILD_IMPROVEMENT) | **Not done** — builders still idle |
| 5 | Ranged/city attack live test | **Not done** — never exercised |
| 6 | Daemon lockfile / watchdog | Lock **done** and verified; no watchdog |

### Next open items (ranked)

1. **Threat response in the policy** — the actual reason we lost.
2. **Invariant alarms** — flag gold/city/production not moving when they should.
3. **Builder improvements and unit promotions** — both still entirely unused.
4. **Tactical combat** — attack logic exists but was never exercised in anger.
5. **Auto-dismiss popups proactively**, not only on stall, to reclaim wall-clock.

### Scoreboard

| Metric | Value |
|---|---|
| Turns played autonomously | 290 (t174 → t464) |
| Wall-clock | ~5 hours, one continuous session |
| Human interventions required | 1 (the CONTINUE GAME click) |
| Game restarts burned | 1 (misdiagnosed dead listener) |
| Silent-failure sites found and fixed | 5 |
| Stall classes solved | 1 (blocking popups) |
| Result | Defeat — Vietnam Science Victory, t464 |
