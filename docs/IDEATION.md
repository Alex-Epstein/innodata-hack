# Visual track ideation (pick by ~10:30)

How this works (the HackPrinceton way, sped up):
1. **Read the criteria** (2 min). They come straight from the judging rubric.
2. **Silent add** (5 min): everyone adds 1 or 2 ideas to "Team ideas" and stars their top 3 from the list.
3. **Score the top 5 together** (8 min) with the table below.
4. **Spike test the top 3** (15 min, under $1): render one rough image for each, ask a teammate to solve it,
   ask both models. **Pick the one where people get it and models don't.** Evidence beats debate.

---

## 1. Criteria

### Rubric (this is how we're scored; weight in brackets)
| Criterion | Ask of each idea |
|---|---|
| **Realism + usefulness** [20%] | Does this image exist in real work or teaching? Can we name 2 real sources it copies (software, a textbook, a public report)? Would a wrong answer cost someone something? |
| **Generator reliability** [20%] | Can we render it cleanly from data in matplotlib (or a library) within ~1 hour, with no overlapping labels across hundreds of seeds? |
| **Verifiable** [15%] | Is the answer exactly computable from the data? Unique (no ties)? Checkable from the pixels? Is a fair tolerance obvious? |
| **Difficulty** [15%] | Will Haiku 5.5 and GPT-6 Luna fail because of **reasoning** (multi-step, tracing, counting, combining) rather than because the image is unreadable? |
| **Variation** [10%] | Can one image family ask at least 3 questions that need genuinely different reasoning? |
| **Eval story** [10%] | Will the failures be interesting to explain (misread vs misreasoned, which step breaks)? |
| **Runnable** [10%] | Pure Python, deterministic, no browser or GPU inside Docker? |

### Not scored, but decides who wins
- **Distinctive**: other teams won't do it. The speaker's own example (a social-network graph) and plain bar charts will be everywhere.
- **Demo punch**: a judge understands the image and question in 10 seconds and can try it themselves.
- **Splits 5 ways** from hour 1 without people blocking each other.

### What these models are known to be weak at (lean into it)
Tracing lines through crossings and connectivity in diagrams · counting many similar marks · reading precise positions
on dense grids or between gridlines · multi-hop reasoning across many elements · combining two sources (an image
plus a rule, or two panels) · spatial relations in cluttered layouts. They're **strong** at reading clear text and
simple labeled charts, so avoid tasks that are just OCR.

---

## 2. Options (21 ideas, scored)

Scores are 1 to 5 per rubric criterion. **Fit** = the rubric-weighted score out of 5. Dist = distinctive, Demo = demo punch.

| # | Idea | Real image it copies | The question (reasoning) | Real | Gen | Ver | Hard | Var | Eval | Run | **Fit** | Dist | Demo |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | **Circuit schematics** | Textbook / EE homework schematics (`schemdraw` lib) | equivalent resistance · current through R3 · which bulb is brightest | 5 | 4 | 5 | 5 | 4 | 4 | 5 | **4.60** | 3 | 4 |
| 2 | **Team calendar** | Outlook Scheduling Assistant, Google Calendar week view | earliest common free slot of D min · hours booked · which meeting conflicts if moved | 5 | 4 | 5 | 4 | 4 | 4 | 5 | **4.45** | 4 | 5 |
| 3 | **Project Gantt** | MS Project, Smartsheet | finish date (critical path) · finish if task K slips N days · zero-slack tasks | 5 | 4 | 5 | 4 | 4 | 4 | 5 | **4.45** | 3 | 4 |
| 4 | **Topographic map** | USGS quad maps, trail maps | elevation at a marked point · which route climbs more · is peak A visible from B | 5 | 4 | 4 | 5 | 4 | 4 | 5 | **4.45** | 4 | 4 |
| 5 | **Pedigree chart** | Genetics textbooks, clinical genetics | inheritance mode · probability III-2 is a carrier · which individual is an obligate carrier | 4 | 4 | 5 | 5 | 4 | 4 | 5 | **4.40** | 5 | 4 |
| 6 | **ECG strip** | Standard 12-lead printouts, 25 mm/s grid | heart rate from R-R boxes · regular or irregular · PR interval in ms | 5 | 4 | 4 | 5 | 3 | 4 | 5 | **4.35** | 4 | 5 |
| 7 | Stacked / grouped business chart | Annual reports, BI dashboards | which segment's share grew most · year the total first exceeded X | 5 | 5 | 5 | 3 | 3 | 3 | 5 | **4.30** | 1 | 3 |
| 8 | **Ternary diagram** | Geology / materials science papers (soil texture triangle) | composition at point P · which sample has the most of component C | 4 | 4 | 5 | 5 | 3 | 4 | 5 | **4.30** | 5 | 3 |
| 9 | **Transit map + service notice** | NYC subway map style, weekend service changes | fewest stops A to B given a closure · transfers needed | 5 | 3 | 5 | 4 | 4 | 4 | 5 | **4.25** | 3 | 5 |
| 10 | **Power one-line diagram** | IEEE / utility single-line diagrams | which loads lose power if breaker X trips · loads with a backup path | 4 | 3 | 5 | 5 | 4 | 4 | 5 | **4.20** | 5 | 4 |
| 11 | **P&ID valves** | ISA-5.1 process diagrams | close valve V-12: which tanks still get flow · which valve isolates pump P2 | 4 | 3 | 5 | 5 | 4 | 4 | 5 | **4.20** | 5 | 3 |
| 12 | **Warehouse pick path** | Warehouse slotting maps | shortest route to pick bins A12, C3, F7 · aisles crossed | 4 | 4 | 5 | 5 | 3 | 3 | 5 | **4.20** | 4 | 3 |
| 13 | Gauge / instrument panel | Plant control rooms | which gauges are out of their green band · pressure difference between two gauges | 4 | 5 | 5 | 4 | 2 | 3 | 5 | **4.15** | 2 | 3 |
| 14 | **Invoice vs purchase order** | Scanned AP documents (Innodata's roots) | which line doesn't match the PO and by how much · corrected total | 5 | 4 | 5 | 3 | 3 | 3 | 5 | **4.10** | 3 | 3 |
| 15 | IT network topology | Visio network diagrams | if switch S3 fails, which servers lose the internet | 4 | 4 | 5 | 4 | 3 | 3 | 5 | **4.05** | 3 | 3 |
| 16 | **Engineering drawing** | CAD shop drawings with dimension chains | length of an undimensioned edge · hole center distance | 4 | 3 | 5 | 4 | 3 | 4 | 5 | **3.95** | 5 | 3 |
| 17 | Org chart | HR org charts | lowest common manager of A and B · size of X's reporting chain | 4 | 4 | 5 | 3 | 3 | 3 | 5 | **3.90** | 2 | 2 |
| 18 | App screenshots (UI state) | Settings pages, dashboards (rendered with a browser) | which toggles are on · what to click to do X | 5 | 3 | 5 | 3 | 4 | 4 | 3 | **3.90** | 4 | 4 |
| 19 | Social network graph | The speaker's example | second-degree connections of Adam | 2 | 5 | 5 | 4 | 3 | 3 | 5 | **3.85** | **1** | 2 |
| 20 | Floor-plan egress | Architectural plans with a scale bar | shortest route to an exit in meters · nearest exit from room R | 4 | 3 | 4 | 4 | 3 | 3 | 5 | **3.70** | 3 | 4 |
| 21 | Lab titration curve | Chemistry lab manuals | equivalence-point volume · pKa from the half-equivalence point | 4 | 5 | 4 | 3 | 2 | 3 | 5 | **3.80** | 3 | 2 |

**Avoid:** #19 (everyone copies the speaker's example), #7 (well-known chart benchmarks already exist; low
distinctiveness), and anything that's a toy puzzle (the brief says real material only).

---

## 3. Ways to package it (pick one shape)

The rubric gives 20% to reliability and only 10% to variation. So **one family done deep** can beat three done
shallow, as long as the questions really need different reasoning.

| Shape | What | Families | Pros | Cons |
|---|---|---|---|---|
| **A. Ops Desk** | Visuals an AI assistant at work reads | Calendar (2) + Gantt (3) + one-line (10) | Clear business value, matches Innodata's agent work, great opener | 3 generators to build |
| **B. The Exam Room** | Figures students are tested on, where the model is the tutor | Circuits (1) + pedigree (5) + ECG (6) | Highest difficulty, textbook-level rules (the brief asks for that), "training & education" value is explicit | Slightly less "business" |
| **C. Field Engineer** | Diagrams that cause outages when misread | One-line (10) + P&ID (11) + engineering drawing (16) | Most distinctive, high stakes, graph tracing stumps models | Hardest to render realistically fast |
| **D. One deep family** | e.g. only circuits, or only calendars, with 4 or 5 question types | 1 | Most reliable, every person polishes one thing | Variation capped; less wow |
| **E. NYC Commuter** | Transit map + timetable + floor plan | 9 + 3-like timetable + 20 | Hometown hook for NYC judges, great demo | Transit map layout is hard to make look real |

**Two families + a strong validator** is probably the sweet spot for 5 people in ~4 hours: two generator owners,
one validator, one eval, one on packaging and the pitch.

---

## 4. Spike test (15 min, decides it)
For each of the top 3 ideas, one person (with Claude) makes **one** rough image at medium difficulty plus a question.
- Can a teammate who didn't make it answer it in under 2 minutes? (fair)
- Does at least one model get it wrong at temperature 0? (hard). That costs 6 calls, a few cents.
- Did it take under 15 minutes to render something believable? (reliable)

Pick the idea that passes all three. If two pass, pick the more distinctive one.

---

## 5. Team ideas (add yours)
- Alex:
- tech-cosmos:
- dl3832:
- WindHurtLZ:
- (5th):
