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

---

## Why not fixed now

The run is healthy and leading (13 cities vs. rivals' 6-9, at peace, on pace). Its value is as a
**control** to measure the two-tier rebuild against, and editing it mid-flight would both
compromise that and risk destabilising a winning position.

Also decisive: the live runner holds its code in memory, so an edit would not take effect without
a restart — and an edit-while-running is precisely what produced today's unparseable-file
landmine. F1 costs perhaps 4-5 sub-optimal purchases over the remainder. Not worth the risk.

**All of these are inputs to the rebuild, not emergencies.**
