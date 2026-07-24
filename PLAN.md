# PLAN — Two-tier Claude brain for Civ 6

Spec + build plan. Written 2026-07-24, during the live Germany/science run.
**Status: awaiting Duncan's requirements (§7). No research or building started yet.**

---

## 1. What we're building, in one paragraph

Today a hard-coded Python script plays Civ 6 through a bridge into the game's debug socket. It
executes strategy but has no judgement — it can't notice it's losing, can't read a threat, can't
tell a good position from a bad one. That's why the last two campaigns were lost. We're replacing
the decision-making with two tiers of Claude: **Sonnet 5** making tactical calls turn to turn, and
**Opus 5** (me, in session) setting strategy every ~50 turns or when something important happens.

---

## 2. Research status — the important correction

### 2.1 The existing research targets the wrong ruleset

`research-report.md` is written for **Gathering Storm at Prince**. Verified live in the running
game on 2026-07-24:

| | Research assumed | Actually true |
|---|---|---|
| Ruleset | Gathering Storm | **Base Civ VI (`RULESET_STANDARD`)** |
| Difficulty | Prince | **Settler** |
| Barbarians | on | **off** |
| Science win | Exoplanet + laser stations | **Mars colony (3 components)** |

**Do not implement these — the features do not exist in our game:**

- **Governors** (`GameInfo.Governors` is `false` — Rise & Fall feature)
- **Loyalty & grievances** (Rise & Fall)
- **Era score / Golden Ages** (Rise & Fall)
- **Gathering Storm constants** (wrong ruleset's numbers throughout)
- **Laser-station endgame** (Gathering Storm)

**Still valid:** opening build order, expansion pacing, districts/adjacency, chopping/overflow,
eurekas, policy cards, trade routes, envoys, pantheon, per-era checklist.

Settler difficulty makes every benchmark **easier** than the research assumed. The plan is
conservative, not optimistic.

### 2.2 What still needs researching

| # | Unknown | Why it matters |
|---|---|---|
| **R6** | **Do space projects actually queue?** | **The victory condition itself.** Unprovable until we own a Spaceport (~t150) |
| **R7** | **Rival victory progress** | No runaway detection — exactly how campaign #1 was lost |
| **R5** | **Does `Bridge_Chop` work?** | Returns `0` every turn. Claimed working, zero evidence |
| R1 | Full eureka list (`GameInfo.Boosts`) | A 40% research discount we ignore entirely |
| R2 | Base-game constants | All current numbers are Gathering Storm's |
| R3 | Policy-card API | Never implemented; free compounding power |
| R4 | Trade-route API | Traders get built, never routed |
| R8 | Creator build orders | Was rate-limited on 2026-07-23 |

**R5, R6, R7 come first.** If R6 fails, the current game is unwinnable no matter which brain
drives it — better to know at t100 than t300.

---

## 3. Architecture

```
Opus 5 (session)  ──writes──>  doctrine.json      strategy, rare
       ^               <──reads──  escalation.json   only on triggers
       │  (async — never blocks the game)
       v
runner (win_science.py)
       ├──> claude -p (Sonnet 5) ──> action JSON     per DECISION, not per turn
       │      prompt = doctrine + engine-validated LEGAL MOVES
       v
   Civ 6  ──> verified by state change
```

### 3.1 Tier D — tactical (Sonnet 5, headless)

- Runs via `claude -p --output-format json`. **No API key needed** — reuses your existing
  subscription auth, preserving the project's locked "no API key" decision.
- Gets: doctrine, a compact state digest, and **the legal moves the engine already validated**.
- Returns: chosen action + one-line rationale, as strict JSON.
- Called **only when a real choice exists**. Most turns have none.

### 3.2 Tier A — strategic (Opus 5, in session)

Owns `doctrine.json`. Fires on triggers and every 50 turns. Makes the calls a per-turn view
can't: *"expansion has stalled, settlers outrank districts until 8 cities"*, *"p3 is running
away on science, change the tech path"*.

### 3.3 Why we send legal moves, not raw state

1. **Cost** — a full dump is ~37 KB; a digest plus ~20 options is a fraction of that.
2. **Correctness** — the silent-no-op bug class (this project's most expensive recurring failure,
   responsible for both losses) becomes *structurally impossible*, because an illegal move is
   never offered in the first place.

### 3.4 The checker is the engine, not a model

Every action is verified by state change — city count moved, gold moved, production hash moved.
The engine cannot be fooled; a reviewing model can. **A model claiming it founded a city is
exactly as untrustworthy as `ok=true` was.**

---

## 4. Control channel — how you drive this from your phone

**The game runs on the PC.** Nothing in the cloud can reach it. So remote control means sending
*instructions* to the PC, not moving the work.

**Chosen approach — git as the control plane:**

1. You edit `doctrine.json` in the GitHub mobile app and commit.
2. The runner does `git pull` every N turns and applies the new doctrine.
3. No open ports, no tunnel, no attack surface. Latency of one poll interval, which is fine for
   strategy.

Optional later: **Tailscale**, if you want live interactive control at 2am rather than async.

`doctrine.json` sketch:

```json
{
  "version": 3,
  "set_at_turn": 100,
  "intent": "Expansion stalled at 5 cities. Settlers outrank districts until 8.",
  "build_priority_override": ["UNIT_SETTLER", "DISTRICT_CAMPUS", "BUILDING_LIBRARY"],
  "thresholds": {"expand_until": 8, "buy_gold_floor": 120},
  "escalate_if": ["city_count_flat_15", "war_declared", "space_project_available"]
}
```

---

## 5. Escalation triggers (Tier D wakes Tier A)

- war declared, or a city lost
- first space project available (the victory handoff)
- city count flat 15+ turns *(would be firing right now — 5 cities, t90→t100)*
- gold above threshold with nothing purchasable for 10 turns
  *(the exact silent-failure signature that lost campaign #1)*
- a rival's victory progress crosses a runaway threshold (needs R7)
- every 50 turns — routine review

**Escalation never blocks.** The runner keeps playing on the last doctrine and applies the answer
when it lands. A blocking escalation turns one distracted hour into a dead run.

---

## 6. Build phases

| Phase | Work | Risk |
|---|---|---|
| **0** | Close R5/R6/R7 — the unknowns that decide the game | Low |
| **1** | Runner reads `doctrine.json`; hard-coded policy honours overrides. **No model calls yet** | Low |
| **2** | Tier D: `decide_tactical()` shelling to `claude -p`, gated, fallback to script on any failure | **Medium** |
| **3** | Escalation triggers + `escalation.json` | Low |
| **4** | `civ6-doctrine` skill so Tier D reloads rules per call instead of starting cold | Low |
| **5** | Shakedown vs. the current run as control | Low |

**Phase 2 is the only genuinely risky step** — it puts an external process in the turn loop. Built
fallback-first: script policy stays the default; the model's answer is an *override* that must
parse, validate against the legal-move list, and verify by state change. Anything less and one
bad call stalls the game.

**On "one session":** writing the code in one session is realistic. **Validating it is not** —
behaviour needs game hours, which can't be compressed. Expect one session to build, then
unattended time to prove it.

---

## 7. AWAITING YOUR SPEC — the decisions I need

Edit this section on GitHub and commit; I'll read it.

### 7.1 Doctrine — how should it play?

- **Expansion aggression:** how hard, and until how many cities?
- **Defense-only — absolute?** Or do we take a free city if one sits undefended next to us?
- **Wonders:** ignore entirely, or chase the science ones?
- **City-states:** ignore, or actively court suzerainty?
- **Risk posture:** grind out a safe win slowly, or play fast and risk a collapse?

### 7.2 Operational

- **Overnight usage ceiling** — give me a number I can enforce in code, so it degrades to
  script-only instead of stranding you at 80% before breakfast.
- **How autonomous overnight?** Should Tier A act on escalations unattended, or queue them for
  your morning review?
- **Failure policy** — if the game stalls at 3am: auto-restart from the last checkpoint, or stop
  and wait for you?

### 7.3 Scope

- Two-tier brain **only**, or also implement the unused systems (eurekas, policy cards, trade
  routes)? Those are worth a lot mechanically but are separate work.

---

## 8. Overnight infrastructure — the unglamorous list

These are what actually kill unattended runs.

| # | Item | Why |
|---|---|---|
| 1 | **Disable sleep/hibernate** | The single most common overnight-run killer |
| 2 | **Runner watchdog** | `TaskStop` kills the wrapper and leaves Python alive — check the *process* |
| 3 | **Log rotation** | `tuner_frames.log` hit 10 MB in one session |
| 4 | **Usage budget guard** | Must degrade to script-only, never stop the game |
| 5 | **Steam auto-update off** | A mid-run patch kills the process and maybe the tuner API |
| 6 | **Windows Update deferral** | A forced 3am reboot ends everything |
| 7 | **Resume runbook** | Exact steps from `Progress_tNNN`, including the splash click |

No secrets management needed — `claude -p` uses your subscription, so there is no API key to leak.

---

## 9. Open workstream — computer use / the splash click

**The last hard human dependency.** Starting a new game (and often loading a save) stops on the
leader-intro splash, which needs a physical click. That's why the current game was continued
rather than restarted.

Project history says Windows-MCP's click failed — cursor landed dead-on the button, screen
unchanged, because Civ 6 reads raw device input. **But the separate `computer-use` MCP appears
never to have been tried.** Worth one real test.

Sequencing: prove screenshot + input reach the game safely first; save the decisive splash test
for when we deliberately start a fresh game.

Second payoff regardless of clicking: **screenshot diagnosis**. The notes flag this twice — the
logs looked normal while the screen showed the blocker instantly.

---

## 10. Current state

- **Game running:** Germany, science, base ruleset, Settler, no barbs. Kept alive as the
  **control** to compare the two-tier build against.
- **Bridge:** healthy. Seven bugs fixed 2026-07-24 (see README and git history).
- **Checkpoints:** `Progress_tNNN.Civ6Save` every 27 turns.
- **Known weak spot:** expansion — 5 cities at t100 against a 7–12 benchmark, though level with
  every rival.
