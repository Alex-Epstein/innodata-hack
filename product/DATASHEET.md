# Datasheet: Terrain Reasoning on Topographic Maps

A dataset card in the style of *Datasheets for Datasets* (Gebru et al.). The sample pack is `product/sample_pack/`;
rebuild it with the command at the bottom. Every number here comes from a file named next to it.

## What it is
Visual reasoning tasks on topographic maps of real places. Each task is one map image, one question and one exact
answer computed in code from the elevation data. A model has to do what a person does with a finger on the map:
trace a path through dozens of contour lines, count level changes along it, follow water downhill, and turn what
it reads into a time budget.

| Mission | The question | Skill it tests | Answer |
|---|---|---|---|
| `crossings` (rescue carry) | How many contour lines does the trail cross between S and E? | trace a path across contours, count every crossing | whole number |
| `sunset` (lost hiker) | How many minutes before sunset does the hiker reach the hut? | count only uphill crossings, then Naismith's rule and clock arithmetic | whole number of minutes, may be negative |
| `flood` (dam break) | Which of 6 campsites does the water from the failed dam reach? | follow steepest descent at right angles to the contours, around bends | campsite name |

The maps follow USGS 7.5-minute quadrangle conventions (brown contours, heavy labeled index contours, scale bar,
latitude and longitude ticks). The sample pack covers Bear Mountain, Breakneck Ridge and Harriman State Park (New
York) and Mount Tamalpais (California).

## Who it is for
Teams training or evaluating vision-language models on spatial reasoning over maps and other contour drawings:
RL with verifiable rewards, supervised fine-tuning on worked solutions, and held-out evaluation.

## Measured baseline
Pilot runs, generator `topo-2.1.0`, difficulty 3, 10 tasks per mission, temperature 0, reasoning effort high,
64,000 max tokens, every reply complete. Counted from `results/pilot_topo_{crossings,sunset,flood}/responses.csv`
(the same counts are in each folder's `summary.json`).

| Mission | Claude Haiku 5.5 | GPT-6 Luna |
|---|---|---|
| crossings | 1/10 | 0/10 |
| sunset | 0/10 | 1/10 |
| flood | 3/10 | 3/10 |
| **all** | **4/30** | **4/30** |

Where they break, from their written reasoning (`gen/topo/README.md`, checked against each task's `steps`): they
read the labels and do the arithmetic correctly, and lose count while tracing. On `sunset`, all 20 replies applied
the stated rule correctly to their own count, and the uphill count was wrong in 19 of 20. On `flood`, 10 of 14
misses named a planted decoy (the camp most directly below the dam, or the nearest camp). Flood has 6 options, so a
guess is right 1 time in 6.

## How answers are guaranteed
1. **Computed in code.** The answer comes from the elevation grid. No model and no person reads the
   image to set it.
2. **Seven automatic checks** (`validate/`) on every task; a task is kept only if all pass: `schema`, `data_first`
   (data written before the picture), `two_solvers` (an independent second method agrees), `render_matches_data`
   (pixels sampled where the data says the trail and markers are), `legibility` (label size, no overlaps),
   `answer_not_in_question`, `reproducible` (rebuild from the seed, byte-identical picture).
3. **Fairness rules in the generator**: crossings at least 40 m apart and at 25 degrees or more, end markers clear of
   every contour, the trail never runs along a contour, decoy camps far from the water's route.
4. **A reviewer agent** (Claude Sonnet, `validate/review.py`) reads each task like a careful person and flags
   ambiguity. It never sets the answer.
5. **A human hand check** of every reported task.
6. **In the pack:** only tasks with all checks passing are exported (`MANIFEST.json` lists anything dropped), and
   every worked solution is scored by the shipped verifier before it is written.

## Knobs a buyer controls
- **Region:** any place with USGS 3DEP elevation. Four places ship today in `gen/topo/tiles/`; adding one means adding
  its terrain tiles and one line in `gen/topo/real.py` (`AREAS`).
- **Mission:** `crossings`, `sunset`, `flood`, alone or mixed.
- **Difficulty 1 to 3:** number of crossings (3 to 6, 7 to 10, 11 to 20), trail length, number of camps (3, 4, 6),
  how far the water runs and how much the route bends.
- **Count:** one task per seed; seed N always gives the same task.
- **Procedural or real terrain:** the shipping generator uses real terrain. An earlier version drew the same
  missions on procedural terrain (a tilted plane plus hills, `results/spikes/topo_synthetic/`, code at commit
  `6730b40`), which gives unlimited maps of places that exist nowhere online, for contamination-free evaluation.
  It is not wired into `topo-2.1.0` today.

## Formats
`uv run python -m factory export --format rl` writes:
- `envs.jsonl`: one RL environment per task: `env_id`, `prompt` (the question plus the answer-format instruction,
  exactly as our evaluation sends it), `image`, `reward_spec` (answer type, reference, tolerance, order),
  `difficulty`, `mission`, `region`, `seed`, `generator_version`, the checks passed, the image's SHA-256.
- `verifier.py`: `reward(env, model_output) -> 1.0 or 0.0`, standard library only, with the evaluation scorer
  (`eval/scoring.py`) vendored verbatim. `python verifier.py` self-tests the pack. **Official scoring is exact.**
  `shaped=True` adds optional 0.5 partial credit for training: a crossing count off by one, a sunset answer off by
  one uphill line or with its sign flipped. Known wrong methods (index contours left out, climb ignored) score 0.
- `sft.jsonl`: process-supervised examples: the same prompt and image plus a step-by-step worked solution
  generated in code from the task's computed `steps`, ending in `FINAL ANSWER:`. Every intermediate value (each
  contour crossed and its elevation, the uphill count, the climb minutes, each camp's distance from the water's
  route) comes from the data.
- `images/` and `MANIFEST.json` (counts per mission, difficulty and region, generator version, license, SHA-256 of
  every file).
- The evaluation-set format (`tasks.jsonl` plus `responses.csv`) is the factory's native output.

## Cost
Generating a task makes no API calls: it runs locally from the seed and the bundled terrain tiles. The only spend is
measuring models on it. **Model-eval cost per task**, both models, from `results/pilot_topo_*/summary.json`:
$0.1690556 for 60 calls on 30 tasks, so about $0.0056 per task (both models) or $0.0028 per model call.
`scripts/budget` reports the team's running spend.

## Limitations
- The sample pack is small: 30 tasks, one difficulty level, four places, all in the United States.
- Two models measured, one run each at temperature 0. 10 tasks per mission is a pilot; differences of one or two
  tasks are noise.
- The worked solutions are written by code from computed facts. They are correct and step-by-step, but they read
  as templates and do not show how to look at the image.
- Flood answers are one of up to 6 names, so guessing scores about 1 in 6.
- Pictures rebuilt on a different machine can differ in the last bytes (font rendering); the reported set is built
  in Docker so rebuilds match.
- Real terrain is public, so a determined model could have seen these places; the procedural option addresses that.

## License
- Elevation: USGS 3D Elevation Program (3DEP), public domain (a US Government work), via AWS Open Data Terrain
  Tiles. Every tile URL and checksum is in `gen/topo/tiles/SOURCES.md` and `gen/topo/tiles/SHA256SUMS`.
- Task text, answers, worked solutions and images are generated by this factory.

## Rebuild the sample pack
```bash
uv run python -m factory export --tasks tasks/pilot_topo_crossings --tasks tasks/pilot_topo_sunset \
    --tasks tasks/pilot_topo_flood --format rl --out product/sample_pack
python product/sample_pack/verifier.py        # 30/30 environments: reference scores 1.0, empty reply 0.0
```
