# Findings from the live control run (Germany, science, base ruleset, Settler)

Observations from the game left running as the control for the two-tier rebuild.
Deliberately NOT fixed mid-run — see "Why not fixed now" at the bottom.

---

## F1 — The purchase list has no science buildings (t250)

`win_science.py` buys from:

```python
wants = ["UNIT_SETTLER"] if expanding else []
wants += ["BUILDING_ANCIENT_WALLS", "BUILDING_WALLS", "UNIT_BUILDER",
          "BUILDING_MARKET", "BUILDING_GRANARY"]
```

**There is no `BUILDING_LIBRARY`, `BUILDING_UNIVERSITY`, `DISTRICT_CAMPUS` or
`BUILDING_RESEARCH_LAB` in the list.** This is a *science victory* run, and gold — our second
biggest lever after production — is never once spent on science.

Observed: 7 purchases in 250 turns, **5 of them Builders**:

```
t105 BUILDER (254->9)    t129 BUILDER (302->42)   t150 BUILDER (308->28)
t174 BUILDER (306->11)   t223 GRANARY (304->44)
```

Note this is a milder replay of the documented campaign-#2 trap ("19 builders"): a preference
list that keeps re-buying the same cheap thing because nothing higher-value is listed.

**Fix for the rebuild:** the buy list must be derived from the victory condition, not hand-written.
For science: Campus > Library > University > Research Lab, ahead of Builders/Granary. Under the
two-tier design this becomes a doctrine field rather than a literal, so Tier A can re-weight it
mid-game without a code edit.

## F2 — Gold sawtooth is by design, and reads like a crisis

Gold oscillates ~300 -> ~10 because the buy gate is `gold > 300` and the buy drains it. A
snapshot taken at the trough (gold 4, 22 units, t250) looks exactly like the campaign-#2 death
spiral where the treasury hit zero and the engine auto-disbanded the army.

**Distinguishing signature — worth encoding as an escalation trigger:**

- healthy sawtooth: gold hits ~0 *immediately after* a logged successful purchase, then recovers
- real spiral: gold trends to 0 with **no purchases**, and unit count *falls* while at peace

The second is the one that lost campaign #2 and must page Tier A. The first is normal.

## F3 — Expansion recovered on its own; do not over-react to a flat window

City count: 3 (t56) -> 5 (t100) -> **10 (t150)** -> 12 (t200) -> 13 (t250).

At t100 this looked like the known stall-at-5 failure and was flagged as such. It was actually
settlers in flight — production *starts* were in the log, completions were not. Doubling to 10
happened within 50 turns.

**Lesson for the escalation triggers:** "city count flat for 15 turns" would have fired a false
alarm here. The trigger must also check whether settlers are in production or in the field before
escalating. Measure the pipeline, not just the output.

## F4 — Turn pace held far better than expected

~50s/turn at t250, against the historical "6-8 min/turn by t280" from the previous campaign.
Attributable to the 2026-07-24 fixes (one-shot buy scan, injected-once helpers, no governor
round-trip). Roughly a 7x improvement over the previous campaign at comparable turn counts, which
is what makes a full game viable in a single sitting.

## F5 — Unit spam is choking the economy (t300)

Unit count: 11 (t150) -> 16 (t200) -> 22 (t250) -> **35 (t300)**, in a *defense-only* game with
zero war declarations all run.

Cause is the known "caps must be applied to the FINAL list" defect, still live in
`set_production_science`:

```python
ordered  = [w for w in want if w in opts]
ordered += [o for o in opts if o not in ordered and o != "UNIT_SETTLER"]   # <- re-adds everything
```

Only `UNIT_SETTLER` is filtered from the catch-all. Once a city has built everything on the
priority list, it falls through to whatever remains — which is mostly military units. Fourteen
cities doing that produces 35 units nobody asked for.

**Consequence, and this is the real damage: no purchase has succeeded since t223** — 77 turns.
Gold sits at 4-8 and never again reaches the 300 buy threshold, because unit maintenance consumes
the entire surplus. The gold lever is effectively dead for the rest of the game.

This is a slow-motion replay of the campaign-#2 economy failure ("Gold 0 -> Civ 6 auto-disbands
units; the army fell 22->7 AT PEACE"). We have not started auto-disbanding, because unit count is
still *rising*, but the treasury is choked and cannot fund the science buildings from F1.

**Fix for the rebuild:**
- apply caps to the FINAL ordered list, never to a pre-catch-all copy
- hard cap military units as a function of city count (defense-only needs ~1/city, not 2.5)
- suspend unit production below a gold-income floor
- treat "no successful purchase in N turns while gold < threshold" as an escalation trigger —
  it is the early, survivable warning that F2's death spiral is approaching

## F6 — "Cheapest fallback" is still not goal-directed (invalidates part of the 2026-07-24 fix)

Research picks t223-t294:

```
METAL_CASTING, CASTLES, SIEGE_TACTICS, CARTOGRAPHY, SQUARE_RIGGING,
MASS_PRODUCTION, BANKING, PRINTING, INDUSTRIALIZATION, STEAM_POWER,
ELECTRICITY, SCIENTIFIC_THEORY
```

CASTLES, SIEGE_TACTICS, CARTOGRAPHY and SQUARE_RIGGING are militarily/naval oriented and are not
on the path to `TECH_ROCKETRY`. The tree is wandering.

This morning's fix replaced `options[0]` (arbitrary engine order) with cheapest-available, which
was a genuine improvement — but **cheapest is not the same as goal-directed.** When `RESEARCH_QUEUE`
offers nothing currently researchable, "cheapest" happily buys a detour.

**Fix for the rebuild — this is the single highest-value research change:**
compute the actual prerequisite chain to the victory techs from `GameInfo.TechnologyPrereqs`
(`ROCKETRY` -> `SATELLITES` -> `NUCLEAR_FISSION` / `NANOTECHNOLOGY` / `ROBOTICS`) and always
research the next unresearched tech *on that path*. Fall back to cheapest only when the path is
complete. The prereq table is already known to be authoritative and ruleset-specific — the
Scythia campaign found `HORSEBACK_RIDING` requires `ARCHERY` in this build, contradicting the wiki.

Estimated cost of the wander: roughly 4 detour techs, plausibly 25-40 turns of delay to the
spaceport in a game where max_turns is 500 and we reached SCIENTIFIC_THEORY only at t294.

## F7 — RETRACTED. See F8. Its central factual claim was false.

> **F7 claimed no Spaceport existed at t400 and that the victory condition was structurally
> unreachable. That was wrong.** Five cities queued `DISTRICT_SPACEPORT` at t393, t396, t400,
> t408 and t411 — before and during the very check that concluded none existed. The analysis
> error is documented in F8; the original text is kept below unedited so the mistake is legible.

**This is the most important finding of the run, and it corrects F6's pessimism.**

The tech tree did NOT fail to arrive. Verified from the log:

```
t355: research -> TECH_ROCKETRY        <- unlocks DISTRICT_SPACEPORT + Earth Satellite
t366: research -> TECH_COMPUTERS
t377: research -> TECH_SATELLITES      <- unlocks Moon Landing
t388: research -> TECH_ROBOTICS        <- unlocks Mars Hydroponics
```

We have held Rocketry since **t355**. At t400 — 45 turns later — `space_check()` has still never
once returned a buildable project, and no Spaceport exists.

### Why

`DISTRICT_SPACEPORT` is in `BUILD_PRIORITY`, and with the five projects above it unbuildable it
is effectively the top buildable entry. So it *should* be queued. But it is only ever considered
inside:

```python
for city in me["cities"]:
    if not city.get("production"):        # <- ONLY when a city falls idle
        set_production_science(city, ...)
```

And per F5, **cities never fall idle** — the catch-all keeps them building military units
forever. 53 units and climbing. So the branch that would queue the Spaceport is never reached.

Meanwhile the space-race override added on 2026-07-24 pre-empts current production, but it only
tests `SPACE_PROJECTS` — **it does not test `DISTRICT_SPACEPORT`.** So the one thing that would
break the deadlock is outside the one mechanism designed to force the endgame.

Three individually survivable defects interlock into a hard block:

1. F5 catch-all -> cities never idle
2. production only re-tasked when idle -> Spaceport never queued
3. space override covers projects but not the Spaceport -> nothing forces it

**Net effect: the victory condition is unreachable despite holding the required techs for 45+
turns.** Structurally the same class of bug as this morning's `GameInfo.Projects()` omission — the
capability exists, the discovery path does not.

### Fix for the rebuild

- the space-race override must include `DISTRICT_SPACEPORT` (and its prerequisites), not just
  the projects
- production must be re-evaluated on a cadence, not only on idle. A city building a Musketman is
  not a reason to skip the spaceport
- add a victory-condition watchdog: *"we hold the tech for a victory building/project and have
  not started it within N turns"* -> escalate to Tier A. This single trigger would have caught it
  at t365 instead of never

### Correction to F6

F6 claimed the research wander would cost the game. That was wrong: despite the detours, every
required tech arrived with ~145 turns to spare. **The tech path was not the blocker — production
was.** F6's prereq-planner fix is still worth doing, but it is an optimisation, not the fix.
Recorded here rather than edited above, because being able to see a wrong call and its correction
is more useful than a tidy document.

## F8 — R6 CLOSED POSITIVE: space projects DO queue. And an analyst error worth keeping.

### The result

```
t355: TECH_ROCKETRY researched
t393: Nuremberg builds DISTRICT_SPACEPORT      (also t396, t400, t408, t411 - five cities)
t467: Aachen builds PROJECT_LAUNCH_EARTH_SATELLITE
t467: *** SPACE RACE *** city 65536 -> PROJECT_LAUNCH_EARTH_SATELLITE
```

**R6 — the single biggest unknown in `PLAN.md` — is closed, positively.** The whole chain works
end to end:

1. `BUILDABLE_PROJECTS_LUA` (the `GameInfo.Projects()` enumeration added 2026-07-24) surfaces
   projects
2. `Bridge_SpaceCheck` detects them across all cities in one round trip
3. the space-race override pre-empts current production
4. `prod_hash != 0` confirms it stuck — verified by state change, not by the ack

This was the one link in the victory chain that could not be proven until a Spaceport existed.
It is now proven in a live game. **The rebuild does not need to solve the victory path — it
already works.**

### The analyst error

At t400 I ran:

```bash
grep -ciE "rocketry|spaceport|SPACE RACE" win_science.log   # returned 11
```

I then wrote F7 asserting no Spaceport existed. **The command had already returned 11 matches.**
I had conflated it with a separate `grep -c "SPACE RACE"` that returned 0, treated the absence of
*projects* as the absence of *Spaceports*, and reported a structural block that was not there.

The project's core discipline — **verify by state change, never trust an assumption** — exists
precisely to prevent this, and it applies to analysis exactly as it applies to code. A conflated
grep is the analytical form of trusting `ok=true`. The correct check was one command:

```bash
grep -c "DISTRICT_SPACEPORT" win_science.log      # the actual question
```

Kept rather than quietly deleted, because a retracted finding with its cause is worth more than a
document that only ever looks correct.

### What was actually true

F5's mechanism was real but its severity was overstated: cities being busy with units **delayed**
the Spaceport ~38 turns after Rocketry (t355 -> t393), it did not prevent it. "Late", not "never".

The genuine remaining defect is narrower than F7 claimed, and still worth fixing:

- the space-race override tests `SPACE_PROJECTS` but **not `DISTRICT_SPACEPORT`**, so the
  Spaceport still depends on a city happening to fall idle. That cost ~38 turns here and in a
  tighter game would cost the win.
- **victory-condition watchdog** remains the right general fix: *"we hold the tech for a victory
  building/project and have not started it within N turns"* -> escalate. It would have fired at
  ~t365 and saved those turns.

### Outcome for this game

Earth Satellite queued at t467 with ~33 turns to the 500-turn ceiling. The remaining four
projects (Moon Landing + three Mars components) cannot all complete in that window, so this game
still ends without a victory — but it ends having **proven the victory machinery works**, which
is worth considerably more to the rebuild than a win would have been.

---

## Why not fixed now

The run is healthy and leading (13 cities vs. rivals' 6-9, at peace, on pace). Its value is as a
**control** to measure the two-tier rebuild against, and editing it mid-flight would both
compromise that and risk destabilising a winning position.

Also decisive: the live runner holds its code in memory, so an edit would not take effect without
a restart — and an edit-while-running is precisely what produced today's unparseable-file
landmine. F1 costs perhaps 4-5 sub-optimal purchases over the remainder. Not worth the risk.

**All of these are inputs to the rebuild, not emergencies.**
