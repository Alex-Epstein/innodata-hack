# The whole project, explained from zero (read this to know it inside out)

## 1. The challenge
Innodata's Visual Task Factory track: build a **factory** (a pipeline, not a one-off) that generates realistic images,
asks questions about them, computes the correct answer **in code** (never by a model or a person), proves each task is
fair, and measures where two frontier vision models fail: **Claude Haiku 5.5** and **GPT-6 Luna**. A task is good when
a careful person can solve it, the answer is provably right, and the models get it wrong because of the reasoning, not
because the image is unreadable. Why it matters: labs train and test models on tasks like these ("RL environments": a
task plus an automatic checker that gives a reward). Tasks a model sometimes fails are the ones that teach it something.

## 2. How we found our topic (the story)
We tested **ten image families** with the same quick experiment (3 difficulty levels x 3 seeds x both models), for under $1:
| Family | Result | Why it failed as a test |
|---|---|---|
| Circuits (equivalent resistance) | 18/18 right | labels are printed, the rest is algebra |
| ECG strips (heart rate, intervals) | 12/12 | sharp marks on a grid are read to the pixel |
| Gantt charts (critical path) | 9/9 and 8/9 | bars on a day grid plus arithmetic |
| Team calendars (free slots) | at first 1/3 on the hard level... | ...but 9/9 once the models got enough thinking tokens |
| Calendar v2 (chained rules: time zones, required attendees) | 9/9, 8/9 | rule chains on a clean grid are easy |
| Subway maps (routes, closures) | mostly right | only one trick question worked |
| Power one-line diagrams | 9/9 clean; 6/9 and 5/9 with dense crossings | after making the wording fair: 60 to 100% right |
| **Topographic maps** | **0/3 on both models from the start** | **this is the one** |
We got stuck: even the small models read labels and do math perfectly, and making the rules more complex didn't help.
The pattern we found: **they can read, but they can't trace.** Following a path through clutter (a trail across dozens of
contour lines, water flowing down a slope) is where they break. Topographic maps are exactly that, and they're real:
hikers, search-and-rescue teams, wildland firefighters and flood planners read them. Evidence: `results/spikes/README.md`.

## 3. How to read a topographic map (30 seconds, also for the pitch)
- Each brown line (a **contour**) joins points of the **same height**. Here, neighbouring lines are **20 m apart** in height.
- Every 5th line is heavier and labelled (an **index contour**: 100, 200, 300 m), so you can tell up from down.
- Lines **close together = steep**, far apart = flat.
- Walking along a trail, **every line you cross is 20 m of climb or descent.**
- Water flows **downhill, at right angles to the lines** (the direction of steepest descent).

## 4. Our three question types ("missions"), each a chain of reasoning
All on **real terrain**: real US elevation data (USGS 3DEP, public domain) around Bear Mountain, Breakneck Ridge and
Harriman (NY) and Mt Tamalpais (CA), drawn in the style of a USGS 7.5-minute map.
1. **Crossings (rescue carry):** "How many contour lines does the trail cross between S and E?" Trace the trail, find
   every crossing, count them all (index lines too, repeats too). Answer: a whole number.
2. **Sunset (lost hiker):** "How many minutes before sunset does the hiker reach the hut?" Read the flat walking time and
   the sunset time from the incident box, count **only the uphill** crossings, add 4 minutes per uphill crossing
   (Naismith's rule, stated), and subtract from the daylight left. Answer: minutes (negative if after dark).
3. **Flood (dam break):** "The dam at D fails. Water follows the steepest way downhill. Which of 6 campsites does it
   reach?" Trace the water perpendicular to the contours from D. Decoys are planted on purpose: a camp straight below
   the dam, the nearest camp, the lowest camp. Answer: C1 to C6.

## 5. Results so far (pilots: 10 seeds per mission, hardest level, generator 2.0)
| Mission | Claude Haiku 5.5 | GPT-6 Luna | Where they break (from their written reasoning) |
|---|---|---|---|
| Crossings | 1/10 | 0/10 | lose count along the trail; usually undercount (said 6, truth 12; said 8, truth 11) |
| Sunset | 0/10 | 1/10 | miscount the uphill crossings, so the climb time is wrong (said 83, truth 63; said 46, truth 14) |
| Flood | 3/10 | 3/10 | stop tracing early and pick a decoy, usually the camp straight below the dam (said C1, truth C6) |
| **All** | **4/30** | **4/30** | 30/30 tasks passed every check; every reply complete |
(The report page and `report/evidence.md` hold the exact numbers; the final 10 are generated and scored at 2:15.)
**The headline:** they read the map's labels and do the arithmetic fine. They fail at the step a person does with a
finger: tracing. Same pattern in power diagrams: 9/9 on clean ones, worse with crossings.

## 6. How the factory works (the technical part)
```
seed ─► gen/topo.build()                                   validate/ (7 checks)        eval/              report/ + site/
        1. pick a real place, crop its elevation grid        schema                     both models,       numbers, failure
        2. place a trail / dam / campsites from the seed     data_first                 temperature 0,     gallery, 3D demo
        3. save the data JSON first                          two_solvers                reasoning high,
        4. draw the map from it (matplotlib)                 render_matches_data        64k tokens,
        5. compute the answer from the data                  legibility                 cached, parsed,
           (walk the trail and count height changes;         answer_not_in_question     scored
            flow water downhill on the grid)                 reproducible
```
- **Generator (`gen/topo/`):** everything is decided by the seed, so seed N always gives the same task. The answer is
  computed from the elevation grid, never read off the picture.
- **The 7 checks (`validate/`), run on every task. A task is kept only if all pass:**
  1. **schema:** every required field is there and well formed (and any tolerance is stated in the question)
  2. **data_first:** the data file was written before the picture (the picture is drawn from the data, not the reverse)
  3. **two_solvers:** a second, independent method recomputes the answer from the data; both must agree
  4. **render_matches_data:** we sample pixels in the picture where the data says something is (trail, markers) and confirm they're really there
  5. **legibility:** every label is big enough and no two labels overlap
  6. **answer_not_in_question:** the question text doesn't give the answer away
  7. **reproducible:** rebuild the task from its seed and get a byte-identical picture
  "30/30 pass every check" means: of the 30 pilot tasks (10 per mission), all 30 passed all 7 checks, and none was rejected.
- **Plus two review layers:** a **reviewer agent** (Claude Sonnet) reads each task like a careful person and flags
  ambiguity or anything hard to see (it never sets the answer), and a **human hand check** of every reported task.
  The reviewer's first flags led to real fixes in v2.1 (trail drawn solid magenta with a white casing, start and end
  squares kept off contour lines).
- **Model runs (`eval/`):** one client for all calls, the organizers' required settings, every response saved raw and
  cached (reruns cost $0). The whole day cost about $2 of the $100 budget.
- **Docker:** judges run our Docker image to rebuild the same 10 tasks from their seeds and re-score them. Pictures
  rendered on different machines differ in the last bytes (font rendering), so **the final set is generated inside
  Docker**, the same environment the judges use, so their rebuild matches ours byte for byte.
  - `docker build -t topo-factory .`
  - `docker run --rm -e OPENROUTER_API_KEY -v "$PWD/out:/out" topo-factory rebuild --tasks tasks/final --out /out/rebuilt` (+ score)
  - `docker run --rm -e OPENROUTER_API_KEY -v "$PWD/out:/out" topo-factory fresh --seed 4242 --out /out/fresh`
- **Demo site (`site/`, live on GitHub Pages):** "Beat the AI": you answer from the same flat map the model saw, then the
  map lifts into the real 3D terrain and the truth plays out (blue water, the trail's crossings ticking up) next to the
  models' wrong answers (red). Press S for the hands-free tour. Every number on it comes from the result files.

## 7. Questions judges will ask
- **How do you know the answers are right?** Computed from the elevation data, recomputed by a second independent
  method, picture checked against the data at the pixel level, reviewer agent plus a human hand check.
- **Is it fair or just hard to see?** A person solves each in about [human baseline] (we timed ourselves). Labels are a
  minimum size, and the trail is drawn so every crossing is visible. The reviewer agent hunts for ambiguity.
- **Isn't it synthetic?** The tasks are synthetic and unlimited, but the terrain can be real (any place with USGS data)
  and the look follows USGS conventions. Procedural terrain also works, for unlimited contamination-proof tasks.
- **Why only topo?** We tested ten families, and the models solved the others. Narrowing to the one that reliably breaks
  them, with three different reasoning chains, is the finding.
- **Cost and scale?** About half a cent per model call, the whole day about $2. New seed = new task, checked automatically.
- **What's next?** More real places and missions (line of sight, wildfire), harder chains, and using these as RL
  environments to train map reading.
