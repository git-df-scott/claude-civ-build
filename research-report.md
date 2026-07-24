# Civ 6 Gathering Storm — Win Research Report
### How the bridge wins its next game. Compiled 2026-07-23.

**Game build:** Sid Meier's Civilization VI — Gathering Storm, v1.0.12.68 (1023995), all DLC.
**Target conditions (per Duncan):** standard game, no special conditions. Interpreted as
standard speed, standard map, ~Prince difficulty, barbarians ON, 5–7 AI rivals, all victory
types enabled.

**Record so far:** 0 wins, 2 losses.
- Loss #1 (Kongo, science-tall): DEFEAT t464, Vietnam science victory. Cause: no military
  logic, no threat model, 1387 gold hoarded while purchases silently failed.
- Loss #2 (Scythia, domination, barbarians OFF crutch): 5th of 6 at stop (t361). Cause:
  overextension, whole army on one siege, economy hit 0 → engine auto-disbanded the army,
  domination mathematically unwinnable (2 rival capitals across water, no navy).

**Sources:** CivFanatics forum threads (benchmarks, build orders, chop/overflow/district
mechanics), Civilization Fandom wiki (loyalty, grievances, victory, difficulty), a timing-push
strategy blog, and identified PotatoMcWhiskey creator videos. Research ran via the deep-research
harness (5 angles, 16 sources, 79 claims extracted). The adversarial verification pass and the
YouTube-transcript scrape were cut off by a shared web-session rate limit (resets 14:10 today);
however every load-bearing claim below is standard, well-documented Civ 6 mechanics that
corroborate directly against known game behavior. Version-sensitive numbers are flagged
[VERIFY-IN-ENGINE] — the bridge will confirm them live via the tuner DB before relying on them,
consistent with the project's verify-by-state-change discipline.

---

## 0. The central decision: which victory, and why

**Recommendation: peaceful SCIENCE victory as the primary path, with CULTURE as the
opportunistic secondary, and a purely DEFENSIVE military posture. Do NOT pursue domination.**

Rationale, tied directly to our two losses and our known defects:

1. **Our tactical-combat layer is our single weakest component and the direct cause of both
   losses.** Loss #1 had no military at all; loss #2 had a military that deadlocked massing
   1–2/8, sieged one city for 70 turns, and bankrupted us. Domination *requires* that layer to
   work turn after turn against a moving enemy. Science/Culture require it to do exactly one
   thing we can already do well: hold walls and kill what walks into range.
2. **The macro layer — expansion, districts, production chooser, research/civics, verify-by-
   state — already works.** Science victory is a macro race. It plays to our strengths.
3. **Prince combat is neutral (AI +0 CS, player +0 CS — §4), and the Prince AI starts with the
   same 1 Settler / 1 Warrior / 0 Builders we do (§4).** We are not out-gunned at the start; we
   do not *need* to out-fight anyone. We need to out-build them and defend.
4. Domination on a standard map means taking *every* original capital including across-water
   civs — the exact wall we hit in loss #2. Science needs no navy, no enemy territory, no siege.

The benchmark data (§3) says domination/religion are *faster* for an expert human. Irrelevant:
we are not optimizing turn count, we are optimizing **P(win)** for a bot that loses when forced
to micro a war. Slow-and-peaceful is the highest-probability line for us.

---

## 1. Prince difficulty — the exact numbers we're playing against

[Source: Fandom Difficulty_level wiki. VERIFY-IN-ENGINE for GS-specific values.]

- **AI yield bonus at Prince:** +8% Science/Culture/Faith, +20% Production/Gold. Small but real
  economic head start. (Scales to +40%/+100% at Deity; 0% at Warlord and below.)
- **Combat modifiers at Prince: both 0.** AI combat bonus 0, player combat bonus 0. Unit-for-unit
  math needs no difficulty correction. (Below Prince the AI fights at −1; above, +1 to +4.)
- **AI starting units at Prince: 1 Settler, 1 Warrior, 0 Builders — identical to ours.** Extra AI
  units only begin at King (2nd Warrior), Emperor (2nd Settler), up to Deity (3 Settlers/5
  Warriors/2 Builders). **An early window is not pre-empted by a bonus AI army.**
- **AI free boosts at Prince:** 1 free eureka/inspiration, +10% combat XP. (Deity: 5 boosts,
  +50% XP.) Player XP bonus is 0 at Prince and above.
- **Barbarian camp clear at Prince: 50 gold each.** City-states start UNWALLED at Prince (free
  Ancient Walls for city-states begin only at Immortal/Deity). Camp-clearing is worth real gold
  and early XP to us.

Implication: at Prince the game is close to symmetric. A clean macro game beats the AI's small
percentage bonuses. We do not need exploits; we need to not lose to ourselves.

---

## 2. The macro engine — what a bot must execute, per era

### 2.1 Opening build order (turns 1–~30)
[Sources: CivFanatics deity-build-order thread; PotatoMcWhiskey settling guide.]

- **Found the capital in place, turn 1.** (Already our doctrine — keep it. Map starts are pre-
  vetted; wandering cost us 3 turns in loss #2.)
- **Standard opener: Scout → Slinger → Settler (or Builder).** The Slinger is built specifically
  to **trigger the Archery eureka by getting a kill** (barb or unit), then later upgraded to an
  Archer — never hard-build Archers (slingers are cheaper and feed the tech path). Build 3–4
  slingers if going for any early military.
- **Buy a Scout the moment gold hits ~120** — early gold is tempo/scouting currency.
- **Campus is the first district in most games**, placed on the best adjacency tile.

### 2.2 Expansion pacing — the benchmark that we have failed twice
[Sources: CivFanatics benchmarks thread; multiple deity players.]

- **3–4 cities by turn 50.**
- **7–12 cities by turn 100** (deity players: greenOak "at least 7–8", Victoria "10 by T100";
  one sub-200 science win was built on **14 cities by turn 100**).
- Both our losses had ~3 cities deep into the game. **This is the number-one macro failure.**
  Expansion must be relentless and early: settlers and Ancestral-Hall-boosted settler production
  are the top priority through ~turn 100 unless physically threatened.

### 2.3 Districts — cost, discount, adjacency
[Sources: CivFanatics district-cost & district-discount threads. GS constants VERIFY-IN-ENGINE.]

- **District cost scales with research progress, not turn count or district count:**
  `cost = FLOOR(base * (1 + 9 * max(techs_done/total_techs, civics_done/total_civics)))`.
  Rises to ~10× base by end of tree. Base ≈ **54** production for most districts, 36 Aqueduct,
  30 Government Plaza (GS-era figures; vanilla was 60 — [VERIFY-IN-ENGINE]).
- **Cost is LOCKED at the moment of placement.** → **Place the district base as early as
  possible, the turn the unlocking tech/civic lands, before further research inflates it.** A bot
  can bank a huge discount just by placing bases early even if it can't finish them yet.
- **Discount mechanic:** a district costs **60% of normal (40% off)** — Government Plaza 75%
  (25% off) — when you own **fewer of that type than average across your unlocked districts**.
  Formula: with `a` = number of researched district-unlocking techs/civics and `b` = fully
  completed districts, a type is discounted when `b >= a` and `b/a >` your count of that type.
  Recomputed only when a tech/civic completes. **Trap: Reyna's gold-purchase does NOT get the
  discount even though the UI shows the lower price — full cost is charged.** [VERIFY-IN-ENGINE]
- **Adjacency: place Campus/Holy Site/Hansa next to mountains/districts for the yield bonus.**
  Our current `Bridge_BuildDistrict` takes the first legal plot from `GetOperationTargets` — it
  must instead score plots by adjacency and pick the best. (Defect C10.)

### 2.4 Chopping & overflow — the biggest production accelerator we don't use
[Sources: CivFanatics chop thread + overflow thread; PotatoMcWhiskey Magnus guide. GS values
VERIFY-IN-ENGINE — the threads mix vanilla (+100% Magnus) and GS (+50%) numbers.]

- **Chop (harvest) yield scales with research %, not turns:**
  `yield = FLOOR(20 * (1 + 9 * max(tech%, civic%)))` — ~20 base, up to ~10× late. **Time chops
  against research progress, not turn number.** Early chops are weak; mid-game chops are huge.
- **First chops → only Settlers or military units** (they get +50% from Ancestral Hall / Agoge /
  Ilkum cards; everything else is more gold-efficiently bought).
- **Magnus (Groundbreaker promotion, +50% harvest yield) makes chops bigger.** Only worth moving
  Magnus to a city with **>3 available chops**. Bank builders with 1–2 charges for Magnus chop
  tours.
- **Overflow is scaled exactly once**, by the modifiers on the item that generated it, and
  carries unchanged to the next item. Worked exploit: park two cheap units near completion
  (Slinger 33/35, Warrior 39/40), establish Magnus, chop both in one turn with Agoge slotted,
  then immediately switch production to a wonder — both policy-amplified overflows dump into the
  wonder. The game's turns-to-complete display already accounts for stored overflow, so a bot
  needn't track it manually for scheduling.
- **Bulk chopping window: from Feudalism civic until ~100 turns before projected victory.**

### 2.5 Eurekas / Inspirations — the 40% discount we ignore entirely
Every boosted tech/civic costs 40% less. Many are cheaply, deliberately triggerable. The bot
should maintain a **boost-target table** and steer builds/actions to trip them. High-value,
reliably-scriptable ones (standard list — [VERIFY-IN-ENGINE against GameInfo.Boosts]):
- Archery ← kill a unit with a Slinger. Bronze Working ← kill 3 barbarians.
- Writing ← meet another civ. Sailing ← found a coastal city. Pottery ← build a farm.
- Animal Husbandry ← build a pasture. Masonry ← build a quarry. Wheel ← build a mine.
- Currency ← make a trade route. Irrigation ← farm a resource. Iron Working ← build a mine on iron.
- Foreign Trade (civic) ← meet a civ. Early Empire (civic) ← reach 6 population.
  Political Philosophy ← meet 3 city-states. State Workforce ← build any district.
  Military Tradition ← clear a barb camp. Games & Recreation ← build an entertainment complex.
- **Our static queues currently ignore all of this.** Dynamic, boost-aware planning is defect C4.

### 2.6 Governors — free, compounding, currently unused (defect B1)
[Sources: PotatoMcWhiskey governor guide; CivFanatics.]
- **Pingala first, all early titles into him, to the +100% Great-Person-points promotion** (also
  gives flat science/culture in his city). This directly feeds a science game.
- **Magnus (Groundbreaker) for the chop economy** — the second governor for our best production
  city.
- **Every governor assigned gives +8 loyalty/turn, active immediately on assignment** — the
  first response to any loyalty-threatened city.
- **Liang** (builder charges / district building), **Victor** (defense +garrison CS) situational.
- Governor titles arrive on a civic cadence; the bot must spend them, not bank them.

### 2.7 Policy-card cycling — free power swapped every civic
[Sources: timing-push blog; overflow thread.]
- **Swap cards freely whenever a civic completes** (no cost outside anarchy). The bot must
  re-slot every civic, not run a static set.
- Production-wave pattern: slot the +production card for what you're mass-producing *this* wave
  (**Ilkum** +30% builders; **Agoge** +50% ancient/classical melee+ranged; **Maneuver** +50%
  light cavalry; **Colonization** +50% settlers), then swap next wave. Economy cards
  (God King → Urban Planning → later economic cards) fill the remaining slots.
- **Never slot cards that do nothing** (our Discipline-with-barbarians-off dead card in loss #2;
  with barbarians ON this game Discipline is at least live early).

### 2.8 Trade routes, envoys, pantheon — cheap compounding yields (defects B5/B6/B7)
- **Trade routes:** run them as soon as available (Currency + Commercial Hub or a Trader).
  Domestic routes give food+production and build roads; international give gold. Never leave a
  Trader idle. Currency eureka is a route itself.
- **City-states / envoys:** send every envoy. 1/3/6 envoys give escalating yield bonuses;
  suzerainty (most envoys) grants a unique bonus and lets you levy their military. Scientific and
  cultural city-states directly accelerate our path. **This is free and we have never done it.**
- **Pantheon:** found one early (accumulate ~25 faith). Pick a permanent yield pantheon fitting
  the map — e.g. **God of the Open Sky** (+1 culture per pasture), **Divine Spark** (+GPP in
  Campus/Holy Site/Theater), **City Patron Goddess**, **Goddess of the Harvest** (chop → faith).
  We have never picked one; it's a free permanent multiplier.

---

## 3. Victory-path benchmarks (to set our KPI bars)
[Sources: CivFanatics fastest-victory, benchmarks, and SV-discussion threads. Mostly Deity;
Prince is easier, so these are conservative ceilings for us.]

| Path | Expert turn (Deity/standard) | Notes for our bot |
|---|---|---|
| Religion | <100 (t84 duel; collapses with fewer foes) | Needs Holy Sites + apostle micro; skip |
| Domination | ~97–157 std map | Needs the tactical layer we lack; **skip** |
| Culture | ~83–220 | Relative to best rival; opportunistic secondary |
| **Science** | ~134–250 (record t98–99 under contrived conquest-snowball) | **Our primary**; macro race, defense-only |
| Diplomatic | slow, vote-dependent | Not schedulable by a bot; ignore |
| Score (fallback) | t500 hard cap (2050 AD) | The clock we must beat regardless |

**KPI bars for us at Prince (looser than the Deity numbers above):**
- Pacing check: **100 science + 100 culture/turn by turn 100** is sufficient for a science win
  ~turn 200 on Deity; at Prince we can be slower and still win comfortably. Target science
  victory **by ~turn 250–300**, well inside the turn-500 score cap.
- Tech pacing for science: **Apprenticeship, Machinery, Education researched and Political
  Philosophy completed by ~turn 100**; then loop high/low-cost techs to sustain ~1 tech/turn to
  the end of the tree.
- **Science victory sequence (GS):** Earth Satellite (Rocketry + Spaceport) → Moon Landing
  (Satellites) → Mars Colony (Nanotechnology) → Exoplanet Expedition (Smart Materials) → travel
  50 light-years at 1 LY/turn base, **+1 LY/turn per Terrestrial/Lagrange Laser Station project**
  (repeatable, multi-city). Endgame is a **production** race for laser stations, not a tech race;
  buy the spaceport buildings with gold/faith and run laser projects in 2+ cities to compress the
  50-LY leg to ~5 turns.

**Rival-progress tracking is mandatory (defect A3/A6).** Loss #1 never saw Vietnam's science win
coming. The bot must read every rival's victory progress each turn and, if a rival is within ~15
turns of any victory, react (spy sabotage of their spaceport, targeted war, or racing harder).

---

## 4. Military — but only the parts a defensive science game needs

We are NOT fighting for the win. We fight to (a) survive to it, (b) clear barb camps for gold/XP,
(c) optionally sabotage a runaway rival. The doctrine is **defense in depth**, which our engine
can already largely execute (hold position, strike in range, walls).

- **Standing home guard from turn 1.** Every border city gets **Ancient Walls** and at least one
  defender before it is threatened, not after (defects A1/A5). Prince AI has no combat bonus and
  no bonus starting army, so a walled city with one ranged unit repels early aggression cheaply.
- **Walls/siege math:** city ranged strength and wall HP mean **melee/anti-cavalry units cannot
  meaningfully damage walls** without support; we don't besiege, so this only matters defensively
  — our cities behind walls are very hard for a Prince AI to take. Battering rams (vs walls) and
  siege towers are attacker tools we won't need.
- **Promotions (defect B4):** take them — a promoted defender is far above base strength. Free.
- **Pillage economy:** if forced into a defensive war, pillaging the attacker's tiles heals our
  units and yields gold/science/faith; it's a defensive tool, not a campaign.
- **If we ever do take a city** (opportunistic, e.g. a weak neighbor's undefended border city):
  **loyalty rules are non-negotiable (§5)** or it flips right back — the collapse pattern of
  loss #2.

### AI behavioral weaknesses worth scripting (Prince)
- AI accepts friendship/peace even after heavy losses (Gilgamesh accepted friendship after losing
  ~5 cities) → we can usually buy peace out of a bad war cheaply.
- AI starts unwalled city-states at Prince and has no combat bonus → early camp-clearing and
  self-defense are low-risk.
- AI over-values duplicate luxuries → we can sell spare luxuries for real per-turn gold (defect
  B15) to fund our macro.

---

## 5. Loyalty & grievances — the rules that turn conquest from a trap into a tool
[Source: Fandom Loyalty & Grievances wikis. VERIFY-IN-ENGINE.]

Even as a peaceful civ these govern forward-settling and any opportunistic capture.

**Loyalty (0–100), penalty bands:** Loyal 76–100 (no penalty); Wavering 51–75 (−25% yields, 75%
growth); Disloyal 26–50 (−50% yields, 25% growth); Unrest 1–25 (−100% yields, no growth); at 0
with negative pressure the city revolts to a **Free City**. **Keep every city ≥76; treat <26 as
an emergency.**
- **Pressure formula:** each pop within 9 tiles contributes `(10 − distance)` × Age Factor (Normal
  1.0, Dark 0.5, Golden/Heroic 1.5); `net = 10 × (Domestic − Foreign) / (min(Dom,For) + 0.5)`,
  capped ±20/turn. A bot can compute this **before** settling or capturing to predict if a city
  holds.
- **Any governor assigned = +8 loyalty/turn, immediately.** First response to a wobbling city.
- **Occupied (just-captured, pre-peace) city = −5/turn, negated by a garrisoned unit.** Starving
  city = −4/turn. → **Always garrison a captured city and never let it starve** (pillaged farms
  starve it — the loss-#2 death spiral).
- **Happiness → loyalty:** Ecstatic +6, Happy +3, Displeased −3, Unhappy or worse −6/turn.
  Amenities feed loyalty, not just growth.

**Grievances (GS diplomacy) — casus belli cost:** Surprise War **150**, Formal War 100,
Holy/Colonial/Retribution/Ideological **50**, Golden Age War **25**. **Never surprise-war** — wait
for a casus belli (our loss campaigns took max warmonger penalties by declaring blind). Decay:
10/turn in Ancient falling ~1 per era to 2/turn in Future, **paused while at war** → early
aggression is diplomatically cheap and quickly forgotten.
- Conquest cost: capturing ≈50 base grievances (scales with pop), razing 3× (≤150), keeping in a
  peace deal costs the capture amount again, **taking a civ's last city = +150 with everyone.**
- **Exploits a bot can script:** eliminate a civ by letting its last city **flip via loyalty**
  (avoids the 150 penalty AND wipes accumulated grievances with them); razing **Free Cities**
  costs zero grievances with anyone; **liberating** a city is the only wartime action that
  *reduces* grievances, with all civs at once.
- Promise popups: refusing = 25 grievances; making-then-breaking = 100 first time. **Default to
  agreeing to promises we can keep.**

---

## 6. Amenities, housing, era score (the invisible systems — defects B10/B12)
[Fandom + CivFanatics. VERIFY-IN-ENGINE.]

- **Housing** caps growth: approaching the housing cap slows growth, at cap it nearly stops.
  Sources: fresh water (+ up to housing), Aqueduct, Granary/Sewer, farms, Neighborhoods late.
  The state dump must expose housing per city so the bot builds ahead of the cap.
- **Amenities:** each city needs amenities scaling with population (~1 per 2 pop past the first
  few). Deficit → yield penalties and eventually revolt + barb spawns. Sources: luxuries (1 lux =
  +1 amenity to up to 4 cities), Entertainment Complex, some policies/wonders, Bread & Circuses
  project. **Spread luxuries across cities; don't stockpile duplicates — sell them (§4).**
- **Era score / Ages:** accumulate era score (first-to milestones, clearing camps, founding
  cities, wonders, etc.) to hit **Golden Age** thresholds; falling short → **Dark Age** (loyalty
  penalties, the loss-#2-style spiral). The bot should track era score and prefer easy
  era-score actions near an age transition. Golden Age loyalty factor (1.5×) also makes our own
  cities stickier and enemy cities flippable.

---

## 7. Mapping every claim to our defects — the rebuild checklist

| Research finding | Our defect it fixes | Action in the runner |
|---|---|---|
| 7–12 cities by t100 | A(expansion), loss #1&2 root | Expansion top-priority to ~t100; settler pump via Magnus/Ancestral Hall |
| Campus-first, adjacency placement | C10, B(science) | Score district plots by adjacency; Campus first |
| District cost locked at placement | C10 | Place bases the turn the tech lands, even unfinished |
| Chop scales with research %, first chops → settlers/units | B9, C1 | Add chop logic gated on research %, Magnus-aware |
| Overflow scaled once, dump into wonders | B9 | Overflow-funnel technique for wonders/spaceport |
| Eureka/inspiration table (40% off) | B2, C4 | Boost-target table; steer builds/actions; dynamic tech/civic planner |
| Pingala-first, then Magnus; +8 loyalty on assign | B1 | Governor assignment logic; spend titles every civic |
| Swap policy cards every civic; production waves | B(policy) | Re-slot every civic; wave cards to current production |
| Trade routes always running | B5 | Never idle a Trader; auto-route |
| Send every envoy; suzerain bonuses | B6 | Envoy spend logic |
| Found pantheon early | B7 | Faith → pantheon at ~25 |
| Walls+defender before threatened; Prince AI has no bonus army | A1, A5 | Standing home guard; border walls proactively |
| Loyalty formula + garrison + governor | B11, A4 | Loyalty in state dump; garrison captures; loyalty-predict before settle/capture |
| Never surprise-war; casus belli costs | B15 | Wait for casus belli; grievance-aware diplomacy |
| Rival victory progress tracking | A3, A6 | Read rival victory progress each turn; react to runaways |
| Amenities/housing/era-score in state | B10, B12, C12 | Expand driver state dump |
| Science victory = production race for laser stations | B(endgame) | Buy spaceport w/ gold+faith; multi-city laser projects |
| Periodic named saves; resume | C6, C7, D1 | Runner writes verified saves every N turns; watchdog |
| Reachability-aware targeting; land-only path | C8, B13 | Only relevant if we ever fight — de-prioritized under peaceful plan |

---

## 8. Per-era executable checklist (the doctrine a bot runs)

**Ancient (t1–~40):**
- Found capital in place t1. Build Scout → Slinger (get a kill → Archery eureka) → Settler.
- Beeline Pottery/Animal Husbandry/Writing/Bronze Working tripping eurekas; Campus tech early.
- Civics: Code of Laws → Craftsmanship (Agoge/Ilkum) → Foreign Trade → Early Empire (6 pop).
- Found pantheon at ~25 faith. Buy a 2nd Scout at 120 gold. Meet civs (Writing/Foreign Trade
  boosts) and city-states (send first envoys; Political Philosophy inspiration at 3 met).
- Place first Campus base ASAP (lock the cost). Start Government Plaza → Ancestral Hall for
  settler production + free Magnus.
- **Target: 3–4 cities by t50.** Every city walls + 1 defender as it's founded.

**Classical–Medieval (t40–~120):**
- Pingala in capital, titles to +100% GPP. Magnus to best-chop city.
- Expansion continues to **7–12 cities by t100** (settler pump, chops into settlers).
- Campus + Library + University line in every city; Commercial Hub + market + Trader (trade
  routes running). Send envoys every time; take suzerainties.
- Civics to Political Philosophy (good government), Feudalism (Serfdom, begin bulk chopping).
- Tech to Apprenticeship/Machinery/Education by ~t100. Swap policy cards every civic.
- Track era score toward a Golden Age. Keep amenities/housing ahead of growth.
- Defensive posture only; buy peace if attacked; clear barb camps for gold/XP.

**Renaissance–Industrial (t120–~200):**
- Science/culture compounding: universities, then research-boost buildings; Theater Squares if
  culture-secondary is live. Great Scientists/Engineers via Pingala GPP.
- Rationalism-era science cards; keep swapping. Bulk chops into districts/wonders via overflow.
- Watch rival victory progress; if a rival threatens, spy their spaceport or race harder.
- Keep every city ≥76 loyalty; garrison anything captured opportunistically.

**Modern–Information (t200–~300):**
- Beeline the science-victory tech spine: Rocketry → Satellites → Nanotech → Smart Materials.
- Build Spaceport(s); buy spaceport buildings with gold/faith. Run space projects.
- Compress the 50-LY exoplanet leg with Terrestrial/Lagrange Laser Stations in 2+ cities.
- **Win by ~t250–300, comfortably inside the t500 score cap.**

---

## 9. Confidence statement & what's still open

**Am I 100% confident the bot can win as currently coded? No — and that's the honest answer the
two losses demand.** The *research* is win-confident: at Prince, a relentless-expansion,
strong-economy, defensive science game is a high-probability win, and every mechanic needed is
documented and bot-executable. But **the runner does not yet implement most of §7** — it's built
for domination (loss #2's plan), with no governors, chops, eurekas, envoys, pantheon, trade
routes, loyalty model, rival-progress tracking, or the expanded state dump. Confidence becomes
real only after that rebuild.

**Open / to confirm before or during the game (verify-in-engine, our discipline):**
1. GS v1.0.12.68 exact constants: district base cost (54 vs 60), chop/Magnus multiplier (+50%),
   discount % (40% vs 25%), amenity/housing thresholds, era-score table — confirm via tuner DB.
2. Full eureka/inspiration list from `GameInfo.Boosts` (the §2.5 list is standard but must be
   dumped live and matched to scriptable triggers).
3. Civ choice for the game. If Duncan lets us pick: **Korea (Seondeok)** — Seowon flat science,
   simplest possible science-race macro, low micro, forgiving — is the best fit for a bot on a
   science plan. Alternatives: **Russia (Peter)** (faith/tundra sprawl, fast expansion),
   **Germany (Frederick)** (extra district + Hansa, resilient wide), **Rome (Trajan)** (free
   monument + road, easiest expansion/defense). If the civ is fixed/random, the doctrine holds
   regardless.
4. YouTube creator transcripts (PotatoMcWhiskey settling/war/governor guides were located but not
   scraped before the rate limit reset at 14:10). Re-run after reset to deepen §2 with exact
   creator build orders — not blocking, the forum + wiki doctrine already covers the essentials.

**Recommended next step (pending Duncan's go-ahead to touch code, and separately to start a
game):** implement §7 in priority order 1–8 as an upgraded runner (`win_science.py`), validating
each system live against the tuner before trusting it, then a short shakedown before a full game.

*No game will be started until Duncan gives the explicit go-ahead.*
