# Two-tier Claude brain for the Civ 6 bridge

Spec + build plan. Written 2026-07-24 (during the live Germany/science run, t100).
Supersedes the "script-only policy" model used by `win_science.py`.

---

## 0. Research status — READ THIS FIRST

### 0.1 The research was compiled for the WRONG RULESET

`research-report.md` (2026-07-23) is titled **"Civ 6 Gathering Storm"** and is written for
**Gathering Storm at Prince difficulty**. Verified live in the running game 2026-07-24:

| Thing | Research assumed | Actually true in our game |
|---|---|---|
| Ruleset | Gathering Storm | **RULESET_STANDARD (base Civ VI)** |
| Difficulty | Prince | **DIFFICULTY_SETTLER** |
| Barbarians | on | **off** |
| Science win | Exoplanet + Terrestrial Laser Stations | **Mars colony (3 components)** |

**Sections invalidated by the ruleset mismatch — do not implement:**

- **§2.6 Governors** — `GameInfo.Governors` is `false`. Governors are Rise & Fall. There is
  nothing to appoint. (Already deleted from the runner.)
- **§5 Loyalty & grievances** — Rise & Fall. No loyalty pressure, no grievance system.
- **§6 Era score / Golden Ages** — Rise & Fall.
- **§9.1 GS v1.0.12.68 constants** — wrong ruleset's numbers entirely.
- **§7 "laser stations" endgame** — Gathering Storm. Our endgame is
  `PROJECT_LAUNCH_EARTH_SATELLITE` → `..._MOON_LANDING` → `..._MARS_{REACTOR,HABITATION,HYDROPONICS}`.

**Sections that survive** (ruleset-independent or base-game-valid): §2.1 opening build order,
§2.2 expansion pacing, §2.3 districts/adjacency, §2.4 chopping/overflow, §2.5 eurekas,
§2.7 policy cards, §2.8 trade routes/envoys/pantheon, §4 military basics, §8 per-era checklist.

Difficulty being Settler rather than Prince makes every benchmark in §1 and §3 **easier**, not
harder — the plan is conservative, not optimistic.

### 0.2 Research completed

- Victory-path choice and justification (science, defense-only) — solid
- Expansion benchmarks (7–12 cities by t100) — solid, and we are failing it (5 at t100)
- District cost/adjacency, chop mechanics, overflow — solid
- Eureka/inspiration concept and the 40% discount — solid
- AI behavioural weaknesses at low difficulty — solid
- Per-era executable checklist (§8) — solid, minus the R&F items

### 0.3 Research NOT done / still unknown

| # | Unknown | Why it matters | How to close it |
|---|---|---|---|
| R1 | Full eureka/inspiration list | 40% research discount, entirely unexploited | Dump `GameInfo.Boosts` live via tuner |
| R2 | Base-game (not GS) constants: district cost, chop multiplier, amenity/housing thresholds | All current numbers are GS numbers | `DB.ConfigurationQuery` / `GameInfo` dump |
| R3 | Policy-card system | Never implemented at all; free compounding power | Probe `GetCulture():...` slot API |
| R4 | Trade-route API | Traders built but never routed | Probe route-assignment API |
| R5 | Does `Bridge_Chop` actually work? | Returns `0` every turn; never observed a real harvest | Test with a builder on a forest tile |
| R6 | Do space projects actually queue? | THE victory condition; unprovable until we own a Spaceport | Verify at first Spaceport (~t150+) |
| R7 | Rival victory progress | No runaway detection; lost campaign #1 exactly this way | Probe per-player science/culture progress API |
| R8 | Creator build-order transcripts | Depth on settling/timing | Re-scrape (was rate-limited 2026-07-23) |

**R5, R6 and R7 are the highest value.** R6 is the victory condition itself; R7 is the failure
mode that lost campaign #1; R5 is a claimed-working system with zero evidence behind it.

---

## 1. Architecture

```
Opus 5 (this session)  ──writes──>  doctrine.json      strategic intent, rare
        ^                <──reads──  escalation.json    only on triggers
        │
        │ (async, never blocks the game)
        v
runner (win_science.py)
        │  per DECISION (not per turn):
        ├──> claude -p (Sonnet 5) ──> action JSON
        │       prompt = doctrine + engine-validated LEGAL MOVES
        v
    engine  ──> verify by state change (never trust the ack, never trust the model)
```

### 1.1 Tier D — tactical (headless Sonnet 5)

- Invoked via `claude -p --output-format json`. **No API key** — the CLI reuses the existing
  subscription auth, preserving the project's locked "NO API key" decision.
- Receives: current doctrine, a compact state digest, and **the list of legal moves the engine
  already validated** (`buildable()`, `found_spot()`, `buy_scan()`, `space_check()`).
- Returns: a chosen action + one-line rationale, as strict JSON.
- **Only called when a real choice exists.** Most turns have none.

### 1.2 Tier A — strategic (Opus 5, this session)

- Owns `doctrine.json`: the standing intent the tactical tier executes.
- Invoked rarely — on escalation triggers and a 50-turn review.
- Judgements only Tier A can make: "we're behind on cities, prioritise settlers over districts",
  "p3 is running away on science, change the tech path", "abandon expansion, pivot to spaceport".

### 1.3 Why send legal moves rather than raw state

Two reasons, both load-bearing:

1. **Cost** — a full dump is ~37 KB. A digest plus ~20 legal options is a fraction of that.
2. **Correctness** — the entire silent-no-op bug class (this project's most expensive recurring
   failure) becomes *structurally impossible*, because an illegal move is never offered.

---

## 2. Loop-engineering blocks

| Block | Implementation |
|---|---|
| **State** | `doctrine.json` (Tier A intent, versioned), `civ_policy_state.json` (queues/blacklists), `Progress_tNNN.Civ6Save` (engine state), `win_science.log` (audit trail) |
| **Scheduling** | Event-driven, not cron. Tier D fires on decision points; Tier A on escalation triggers + every 50 turns |
| **Sub-agents** | Maker = Tier D. **Checker = the engine itself** — every action verified by state change. Stronger than a second model, because the engine cannot be fooled |
| **Skills** | A `civ6-doctrine` skill holding the surviving research (§2, §4, §8) so each headless call reloads domain rules instead of starting at context zero |
| **Worktrees** | N/A — one game, one process, no parallel writers |

Closest production patterns: **incident-responder** (event-driven escalation to a higher tier,
never auto-remediating the big calls) composed with **backlog-groomer** (two-tier autonomy —
mechanical decisions apply directly, ambiguous ones escalate).

### 2.1 Readiness checklist

1. **Idempotent** — every command verified by state change; re-issuing is safe (already true).
2. **Bounded** — max turns, max Tier-D calls per turn (1), max escalations per 50 turns (1),
   and a hard token budget that degrades to script-only when exhausted.
3. **Observable** — every Tier-D decision logged with its rationale; `doctrine.json` versioned
   so strategy changes are auditable after the fact.
4. **Safe on failure** — a crashed `claude -p` falls back to the existing hard-coded policy.
   **The game must never stall waiting on a model.**
5. **Scoped** — Tier D can only choose among engine-legal moves. It cannot invent an action,
   and it has no access to anything outside the bridge.

---

## 3. Escalation triggers (Tier D → Tier A)

- war declared, or a city lost
- first space project becomes available (R6 — the victory handoff)
- city count flat for 15+ turns *(currently firing: 5 cities, t90→t100)*
- gold above threshold with nothing purchasable for 10 turns
  *(the exact silent-failure signature that lost campaign #1)*
- a rival's science/culture progress crosses a runaway threshold (needs R7)
- every 50 turns — routine doctrine review

**Escalation is asynchronous.** The runner keeps playing on the last-known doctrine and applies
Tier A's answer when it lands. A blocking escalation turns one distracted hour into a dead run.

---

## 4. File protocol

```
bridge_files/
  doctrine.json     # Tier A -> runner.  {version, intent, priorities, thresholds, notes}
  escalation.json   # runner -> Tier A.  {turn, trigger, digest, question}
  decisions.jsonl   # append-only audit: every Tier D call, its input and its choice
```

`doctrine.json` sketch:

```json
{
  "version": 3,
  "set_at_turn": 100,
  "intent": "Expansion is stalled at 5 cities. Settlers outrank districts until 8 cities.",
  "build_priority_override": ["UNIT_SETTLER", "DISTRICT_CAMPUS", "BUILDING_LIBRARY"],
  "thresholds": {"expand_until": 8, "buy_gold_floor": 120},
  "escalate_if": ["city_count_flat_15", "war_declared", "space_project_available"]
}
```

---

## 5. Build plan

| Phase | Work | Verify by | Risk |
|---|---|---|---|
| **0** | Close R5/R6/R7 — the three unknowns that decide the game. Probe chop, rival progress, and project queueing | Live tuner probes, runner stopped | Low |
| **1** | `doctrine.json` read path in the runner; hard-coded policy reads overrides from it. **No model calls yet** | Change doctrine, observe behaviour change in log | Low |
| **2** | Tier D: `decide_tactical()` shelling to `claude -p` (Sonnet 5), gated to decision points, fallback to script on any failure | Force a decision, inspect `decisions.jsonl`; kill the CLI mid-call and confirm graceful fallback | **Medium — the new failure mode** |
| **3** | Escalation triggers + `escalation.json`; Tier A responds by rewriting doctrine | Trip a trigger deliberately | Low |
| **4** | `civ6-doctrine` skill carrying the surviving research so Tier D reloads rules per call | A/B the same position with and without the skill | Low |
| **5** | Shakedown: 20 turns two-tier vs. the current script-only run as control | Compare cities/science/gold at equal turns | Low |

**Phase 2 is the only genuinely risky step** — it introduces an external process into the turn
loop. It must be built fallback-first: the script policy stays the default, and the model's
answer is an *override* that has to parse, validate against the legal-move list, and verify by
state change. Anything less and a bad model call stalls the game.

---

## 6. Cost shape

| Design | Model calls / 300-turn game |
|---|---|
| Pure Tier A (session decides every turn) | ~300 Opus turns — prohibitive |
| **Two-tier (this plan)** | **~60–100 Sonnet + 6–10 Opus** |
| Script-only (today) | 0 |

Roughly an order of magnitude cheaper than session-as-brain, and it should *play better* —
tactical calls get fresh eyes each time while strategy stays coherent across the whole game.

---

## 7. Recommendation

Do **Phase 0 first, regardless of whether the two-tier build goes ahead.** R5/R6/R7 are unknowns
in the *current* run: if space projects do not queue, this game cannot be won no matter which
brain is driving, and we would rather find out at t100 than t300.
