# Civ 6 doctrine — BASE GAME (RULESET_STANDARD), science victory

Compiled 2026-07-24. **Replaces `research-report.md` for this project**, which was written for
Gathering Storm at Prince and is wrong about our ruleset in ways that matter (see §0).

Everything here is written as **rules a bot can execute**, not prose.

---

## 0. Ruleset — verified live in-engine, not assumed

| | `research-report.md` assumed | Verified true |
|---|---|---|
| Ruleset | Gathering Storm | **`RULESET_STANDARD`** (base game) |
| Difficulty | Prince | **Settler** |
| Barbarians | on | **off** |
| Science win | Exoplanet + laser stations | **Mars colony** |

**Do not implement — these features do not exist here:** Governors, Loyalty, Grievances, Era
Score / Golden Ages, Diplomatic Favor, World Congress, Climate/CO2, Power/Resources consumption.

Golden-Age dedications (`Free Inquiry`, `Pen Brush and Voice`) are also R&F — the +10% boost
uplift below **does not apply to us**. Our boosts are a flat 40%.

---

## 1. The victory condition, exactly

```
TECH_ROCKETRY        -> DISTRICT_SPACEPORT + PROJECT_LAUNCH_EARTH_SATELLITE
TECH_SATELLITES      -> PROJECT_LAUNCH_MOON_LANDING
TECH_NUCLEAR_FISSION -> PROJECT_LAUNCH_MARS_REACTOR
TECH_NANOTECHNOLOGY  -> PROJECT_LAUNCH_MARS_HABITATION
TECH_ROBOTICS        -> PROJECT_LAUNCH_MARS_HYDROPONICS
```

Completing the **three Mars components** wins. Projects are built in a city that has a Spaceport.
Verified live 2026-07-24: all five rows exist in `GameInfo.Projects()`, and the queueing path
works end to end (t467, control run).

**Benchmark:** strong human players report **T150–T160** science victories. Our control run did
not win by **T500**. The gap is not knowledge — it is execution, and specifically production.

---

## 2. THE key insight, which our control run proved the hard way

> **Science victory is a PRODUCTION race, not a science race.**

Community guidance is explicit: *"in the early-to-mid game, the actual most important resource
for science victories is production… you cannot win a science victory without a strong industrial
base."*

Our control run is the empirical proof. It researched **every** required tech — Rocketry by t355,
Satellites t377, Robotics t388 — and still could not win, because:

- cities were busy building military units, so nothing built the Spaceport (F5/F7)
- gold could never buy science buildings, because unit maintenance ate the treasury (F1/F5)

**Rule: from the moment Rocketry lands, production allocation IS the game.** Everything else is
a supporting argument.

---

## 3. Settling (executable rules)

| Rule | Value | Why |
|---|---|---|
| Capital on fresh water | **mandatory** | 5 Housing vs 3; early growth is compounding |
| Preferred terrain | **Plains Hills** | 2 food + **2 production** — every other tile is 2/1 |
| Hills in rings 1–2 | maximise | production base |
| City spacing | **4–6 tiles** | >7 leaves indefensible gaps; <4 wastes tiles |
| Minimum site quality | **≥4 combined yield**, at least one 5-yield tile | |
| Campus adjacency | **+1 per adjacent mountain** | drives the whole science engine |

Current `Bridge_FoundSpot` scores `2*food + prod + 3*fresh_water − distance`. **Missing: hills
preference, mountain adjacency for a future Campus, and the 4–6 spacing band** (it only enforces
a hard minimum of 4). Those are cheap additions with real compounding value.

---

## 4. Expansion pacing

- **7–12 cities by t100.** Control run: 5 at t100, 10 at t150, 13 by t250 — late, but it did get
  there. Late expansion is survivable; *no* expansion is not.
- Do not stop expanding because a counter says 10. Stop when land runs out or settlers cost more
  than a Campus is worth.

---

## 5. Eurekas / Inspirations — the biggest unexploited lever

- Every tech/civic has a boost worth **40%** of its cost.
- Base game: flat 40%, no dedication uplift (that is R&F).
- **Technique:** switch off a tech before completing it, take the boost, come back. A player
  reliably taking boosts researches ~40% faster than one who ignores them.
- **We currently exploit exactly zero of these.** `GameInfo.Boosts` has never been dumped.

**Action:** dump `GameInfo.Boosts`, map each to a scriptable trigger (build a quarry, meet a civ,
kill a unit, found a district), and steer builds toward the boosts on the Rocketry path.

---

## 6. Policy cards — also entirely unimplemented

| Card | Effect | Priority |
|---|---|---|
| **Five-Year Plan** | **+100% Campus and Industrial Zone adjacency** | highest — doubles the science engine AND production |
| **Rationalism** | major Campus building science bonus | highest |
| Natural Philosophy | Campus adjacency boost (early equivalent) | high, early |
| Inspiration | +2 Great Scientist points/turn | medium |
| Market Economy | +2 science from international trade routes | medium |

**Rule: re-slot cards on every civic unlock.** Cards are free to swap at a civic change and we
have never swapped one. This is pure unclaimed value.

---

## 7. Trade routes

Traders were built in the control run and **never routed** — the API was never implemented.
Internal routes give food+production (helps the production race); international give gold and,
with Market Economy, science. Rule: **never leave a Trader idle.**

---

## 8. Per-era checklist (base game)

**Ancient (t1–40)**
Settle capital in place t1 on fresh water. Scout → Settler. Research Pottery → Writing (Campus).
Civics: Code of Laws → Craftsmanship → Foreign Trade → Early Empire. Place the first Campus base
early (cost locks at placement). Meet civs and city-states (boosts).

**Classical–Medieval (t40–150)**
Expand to 7–12 cities. **Campus in every city**, prioritising mountain adjacency. Library
everywhere. Government Plaza. Slot Natural Philosophy. Keep every Trader routed. Take boosts.

**Renaissance–Industrial (t150–260)**
University everywhere. Industrial Zones / Hansa for the production base. Swap in Rationalism and
Five-Year Plan. **Cap military at ~1 defender per city** — this is where the control run lost the
game by drifting to 53 units.

**Modern+ (t260 →)**
Beeline Rocketry. **Build the Spaceport the turn Rocketry lands, in the highest-production city,
pre-empting whatever that city is doing.** Then Research Labs, then run the projects. Buy with
gold wherever legal.

---

## 9. Direct mapping to our findings

| Finding | Doctrine fix |
|---|---|
| F1 buy list has no science buildings | buy priority: Campus > Library > University > Research Lab |
| F5 unit spam chokes economy | hard cap ~1 defender/city; suspend unit production below a gold-income floor |
| F6 research wanders | prereq-chain planner toward Rocketry, boost-aware |
| F7 Spaceport never queued | build it the turn Rocketry lands; pre-empt production; victory-condition watchdog |
| F9 override thrashes | idempotence guard on every pre-emption |
| — | eurekas, policy cards, trade routes: all unimplemented, all free value |

---

## 9b. From the PotatoMcWhiskey transcript (R8 CLOSED)

Source: *"The only guide to Settling in Civ 6 a new player will ever need — Ancient Era"*
(52:33, 1.5M views). Full transcript extracted 2026-07-24.

**Filter applied:** the video is Rise & Fall era — it discusses Governors (Pingala, Magnus) and
Loyalty at length. **Those do not exist in our base-game ruleset and are excluded below.** Note
this costs us the Magnus +50% chop bonus, so chopping is worth proportionally less to us than to
him, though still positive.

### 9b.1 The tile-profit model — replaces our settle scoring

This is the single most valuable idea in the video and our current scorer gets it wrong.

> **Every citizen eats 2 food. A tile's value is its yield MINUS 2.**

| Tile | Raw yield | Profit | Verdict |
|---|---|---|---|
| 1 food | 1 | **−1** | actively harmful |
| 2 food | 2 | **0** | break-even, worthless |
| 3 food | 3 | **+1** | fine |
| 4 food | 4 | **+2** | **twice as good as the 3-food tile** |
| 2 food 2 prod | 4 | **+2** | *"the perfect profit tile"* for the ancient era |

The consequence is non-obvious and important: a 4-yield tile is **twice** as good as a 3-yield
tile, not 33% better. Our `Bridge_FoundSpot` scores `2*food + prod + 3*fresh − dist`, which is
linear in raw yield and therefore systematically undervalues high tiles and overvalues mediocre
ones.

**Action:** rescore as `sum(max(0, yield − 2))` across the workable ring, not raw yields.

### 9b.2 Era-dependent yield weighting

> Ancient + Classical: **food > production.** Medieval onward: **production > food.**

Our scorer weights food `2x` at all times. It should flip around the Medieval era. This dovetails
with §2 — the late game is a production race.

### 9b.3 Settling rules (executable)

- **Settle by turn 3; turn 4 at the absolute latest.** Never move the settler more than 2 turns
  looking for a better spot. Our runner has no settle deadline at all.
- **Settling ON a resource keeps the resource** and upgrades the city centre from the default
  2f/1p to e.g. 3f/1p. **Woods are destroyed by settling; resources are not.**
- City centre always yields 2f/1p regardless of terrain **unless** the tile has a resource or
  bonus yield — so settling on a bonus resource is free value.
- Growth maths: a city netting 4 food grows in 8 turns; **5 food grows in 5 turns.** Small food
  deltas are large growth deltas early.
- **Minimum 3 tiles between cities** (engine rule). He settles ~4 apart so the new city does not
  steal the capital's worked tiles — adjacent tiles are gobbled on founding.
- The engine's **settler lens** ranks spots (brighter green = better). Worth probing: the engine
  may already expose a recommendation we can read instead of scoring by hand.

### 9b.4 Opening build order

- **Scout → Slinger** is the recommended safe opener; **double Scout** is the greedy standard.
- **Explicitly do NOT open with Monument or Builder** — called "advanced plays".
- Warrior 40 production, Slinger 35.
- **Settlers over wonders**: *"between building settlers and building other stuff it's almost
  always the correct play to build more settlers."*

### 9b.5 Mines are the production engine

> *"The most important thing you do with your production is building mines."*

Mines go on any hill (all hill variants) and scale with tech as the tree unlocks mine bonuses.
Our runner builds Builders and then **never directs them** — no mine logic exists at all. Given
§2 (science victory is a production race), this is a large miss.

### 9b.6 Chopping

> *"If you have the option to chop a tile it is almost always the correct choice."*

Chop yield scales with science/culture accumulated, so **later chops are worth more**. Confirms
R5 is worth fixing — our `Bridge_Chop` returns 0 every turn and has never been observed to work.

### 9b.7 Policy cards (base-game relevant)

| Card | Effect | When |
|---|---|---|
| **Colonization** (Early Empire) | **+50% production toward Settlers** | the expansion fix |
| God King | +1 gold/turn, enables early Pantheon | opening |
| Discipline | big bonus vs barbarians | only if barbs on — **ours are off, skip** |
| Urban Planning | +1 production | once faith is covered |
| Monument to the Gods | +15% production toward ancient/classical wonders | wonder play |
| Conscription | cheaper unit maintenance | when broke (see F5) |

**Colonization is the direct fix for our expansion problem** (5 cities at t100 vs a 7–12 target).

### 9b.8 Cheap boosts we can script

- kill 3 barbarians → **Bronze Working** (n/a, barbs off)
- kill a Slinger → **Archery**
- improve 3 tiles → **Craftsmanship**
- found a Pantheon → **Mysticism**
- meet another continent → **Foreign Trade**
- farm a resource → **Irrigation**
- mine a resource → **The Wheel**
- 6 total population → **State Workforce**

A boost is worth ~1/3–40% of the item's cost. **Technique: deliberately delay finishing a
tech/civic until its boost lands.** We do none of this.

### 9b.9 Other mechanics we ignore

- **Amenities:** 1 amenity feeds 2 population; each luxury gives 1 amenity to up to 4 cities.
  +3 amenities = **+10% yields**, +5 = **+20% yields**. Empire-wide multiplier, entirely unused.
- **Housing:** fresh water 5, palace +1, farms +0.5 each. Caps growth when hit.
- **Builder charges should roughly equal population** — every tile wants improving.
- Early gold is best spent **buying high-value tiles**, not units.

---

## 10. Sources

- [Civ 6 science victory tips — GameRant](https://gamerant.com/civ-6-tips-science-victory/)
- [Science victory — TheGamer](https://www.thegamer.com/civilization-6-science-victory-tips/)
- [Science victory in 140 turns or less — CivFanatics](https://forums.civfanatics.com/threads/strategy-for-science-victory-in-140-turns-or-less.623393/)
- [List of boosts in Civ6 — Civilization Wiki](https://civilization.fandom.com/wiki/List_of_boosts_in_Civ6)
- [Boost (Civ6) — Civilization Wiki](https://civilization.fandom.com/wiki/Boost_(Civ6))
- [Best Civ VI policy cards — KeenGamer](https://www.keengamer.com/articles/guides/7-of-the-best-civilization-vi-policy-cards/)
- [Best start position — GameRant](https://gamerant.com/civilization-6-best-start-position-location-tile-spot-terrain-capital-city/)
- [City placement for optimal growth — HogoGame](https://hogogame.com/how-to-plan-your-civilization-6-city-placement-for-optimal-growth/)
- [What to prioritise in settling — CivFanatics](https://forums.civfanatics.com/threads/what-should-you-look-for-and-prioritize-in-settling.601811/)

### Creator research (R8) — partially closed

Channel identified: **PotatoMcWhiskey** (542K subs), the channel Duncan linked and the one
`research-report.md` failed to scrape on 2026-07-23.

- [How to Analyze Start Locations in Civ 6](https://www.youtube.com/watch?v=BKZmRBy2QrY) — 2.4M views, R&F-era
- "The only guide to Settling in Civ 6 a new player will ever need — Ancient Era, Rome" (52:33, 1.5M)
- "Civ 6 beginners guide — Where to Settle your Capital, Aztec Overexplained" (45:24, 809K)

**Transcripts not obtainable.** `timedtext` returns empty (YouTube now gates it), the
transcript panel renders empty for this 8-year-old video, and third-party mirrors 403. The
settling doctrine in §3 was reconstructed from text sources instead and is base-game-correct,
which the R&F-era videos would not have been. Not worth further spend.
