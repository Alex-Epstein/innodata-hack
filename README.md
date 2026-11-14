# Innodata Hackathon: Visual Task Factory

> **Team / agents: start at `AGENTS.md`** (new here: `docs/SETUP.md`). This README is the submission README;
> the headings below are the ones the organizers' format checker requires.

## Problem statement
We generated ten kinds of images in code (circuits, ECG strips, Gantt charts, two calendars, subway maps, power
diagrams, topographic maps) and ran the same quick test on each. The two models solved almost all of them: they
read labels and do arithmetic well. They are much weaker when the answer depends on **following a
line through clutter**: a trail across dozens of contour lines, water running downhill, a feeder across a busy
one-line diagram. We built a factory that makes such tasks on demand: it writes structured data, draws a realistic
image from it by code, asks a question that needs several chained steps, computes the answer from the same data
two independent ways, checks every task automatically, and scores `anthropic/claude-haiku-5.5` and
`openai/gpt-6-luna` on them.

## How the pipeline works
One command line, `python -m factory`, with one plug-in package per image family under `gen/`
(contract: `contracts/FAMILY.md`).

| Step | Command | What happens |
|---|---|---|
| Generate | `factory generate --family F --template T --difficulty D --seeds 0-9 --out DIR` | The seed draws the structured data. The data JSON is written **first**; the PNG is drawn from that file only (matplotlib, fixed size, no timestamps); the question, the answer and the reasoning chain (`steps`) are computed from the same data. A seed that cannot make a fair task is rejected with its reason (`generation_log.json`). |
| Validate | `factory validate --tasks DIR` | Seven checks per task (below). Results go into `checks` in `tasks.jsonl` and into `validation_report.json`. An invalid task is dropped, never counted as a model failure. |
| Evaluate | `factory eval --tasks DIR --out DIR` | Both models through OpenRouter with the same prompt: temperature 0, reasoning effort high, max_tokens 64000, retries with backoff, one stored reply per (model, prompt, image, settings). Writes `responses.csv`, `summary.json`, `run_config.json` and every raw reply. Scoring is exact and identical for both models (`eval/scoring.py`). |
| Rebuild | `factory rebuild --tasks DIR` | Regenerates every task from its seed and compares the SHA-256 of the PNG and the data JSON, plus the question and the answer. |
| Fresh | `factory fresh --seed N` | Builds one new task, runs every check and asks both models, live. |
| Export | `factory export --format rl` | Packs checked tasks for training: one environment per task (prompt, image, exact verifier) and the verified worked steps. Described in `product/DATASHEET.md`. |

After the automatic checks come two reviews that never set an answer: an advisory reviewer model
(`validate/review.py`, Claude Sonnet) that reads each task and flags anything ambiguous or hard to see, and a
person's hand check of every reported task. A report page (`report/`), a one-page explainer of the factory (`explainer/`) and a playable demo (`site/`, "Beat
the AI": answer from the flat map, then watch the truth on the 3D terrain) are built from the same result files.

The checks (`validate/checks.py`):

| Check | Passes when |
|---|---|
| `schema` | every required field and type is present; the image exists |
| `data_first` | the data JSON exists, is unchanged since generation and was written before the PNG |
| `two_solvers` | a second, independent solver gets the same answer from the data JSON |
| `render_matches_data` | the pixels at the places the data says hold a marker, a line or a box have that color |
| `legibility` | every label is at least 8 px tall, no two labels overlap, none is cut off |
| `answer_not_in_question` | the answer cannot be read from the question text |
| `reproducible` | a rebuild gives the same PNG and data bytes, question and answer |

### Family: topographic maps of real places (`gen/topo`, details in `gen/topo/README.md`)
The map is drawn from real elevation (USGS 3D Elevation Program, public domain; 16 tiles stored in
`gen/topo/tiles/` with their sources and checksums) in the style of a USGS 7.5-minute quadrangle. Each task is a
mission with a marked scenario:

| Template | Chain of reasoning | Answer |
|---|---|---|
| `crossings` | follow the trail from S to E through the contours → count every line it crosses | integer |
| `sunset` | read now, sunset and flat walking time from the incident box → count the contour lines crossed going uphill → Naismith's rule → minutes to spare before dark | integer |
| `flood` | find downhill at the failed dam → follow the water at right angles to every contour as the slope turns → name the one camp in its path | camp name |

### Family: switchgear single-line diagrams (`gen/power`, details in `gen/power/README.md`)
A 480 V main-tie-main switchgear drawn as found (IEEE Std 141, IEEE Std 315 / ANSI C37.2 symbols): two utility
services through transformers, a standby generator, buses and sub-buses, ANSI 52 breakers (filled = closed, hollow
= open) and alternate feeds that cross other feeders without junction dots.

| Template | Chain of reasoning | Answer |
|---|---|---|
| `trip` | read every breaker state → find what is live after a main trips → shed largest loads first to the generator rating → close the tie → sum the loads that were running and are not at the end | integer kW |
| `dbl` | two breakers trip together → follow every feed, the crossing alternates included → list the running loads that lose power | load tags |
| `iso` | find every source that can feed a sub-bus, back-feeds included → open the fewest breakers that isolate it without dropping other loads | breaker IDs |

## Reported folders
- Tasks: `tasks/final/`
- Results: `results/final/`

The rule for the reported 10 was written down before the final run (`docs/DECISIONS.md`, 13:45): topographic maps
only, generator 2.1, difficulty 3, generated inside Docker; `crossings` seeds 100 to 102, `sunset` seeds 100 to
102, `flood` seeds 100 to 103; a rejected seed is replaced by the next seed of that mission; one evaluation run on
both models; no reselection after seeing results.

## Pilot results
Every pilot is 10 seeds (0 to 9) at difficulty 3 on both models. Rule: keep a template only if at most 5 of 10
are right for at least one model and the misses come from reasoning.

| Pilot | Template | Haiku | Luna |
|---|---|---|---|
| 1. Synthetic field, `topo-1.0.0` | `crossings` | 2/10 | 2/10 |
| | `sunset` | 0/10 | 1/10 |
| | `flood` | 4/10 | 3/10 |
| | `wildfire` | 8/10 | 7/10 |
| 2. Synthetic field, `topo-1.0.1` | `crossings` | 1/10 | 0/10 |
| | `sunset` | 1/10 | 1/10 |
| 3. Real terrain, `topo-2.0.0` | `crossings` | 1/10 | 0/10 |
| | `sunset` | 0/10 | 0/10 |
| | `flood` | 2/10 | 3/10 |
| 4. Real terrain, `topo-2.1.0` | `crossings` | 1/10 | 0/10 |
| | `sunset` | 0/10 | 1/10 |
| | `flood` | 3/10 | 3/10 |

Where the numbers come from: pilots 1 and 2 are stored with the idea spikes (`results/spikes/topo_synthetic/README.md`
lists each run); pilot 4 is in the `pilot_topo_<template>` folders under `results/`, with its task sets under
`tasks/` (pilot 3's files are in git history at commit `9d1d06a`). Each folder has `responses.csv`, `summary.json`, `run_config.json` and the raw replies.
`PYTHONPATH=. uv run python -m gen.topo.pilot_report` prints the pilot 4 table from those files.

Power family pilots (10 seeds, difficulty 3; the `pilot<N>_power_<template>` folders under `results/`):

| Pilot | `trip` Haiku · Luna | `dbl` Haiku · Luna | `iso` Haiku · Luna |
|---|---|---|---|
| 1. `power-1.0.0` | 10/10 · 9/10 | 6/10 · 8/10 | 7/10 · 9/10 |
| 2. `power-1.1.0` (current) | 9/10 · 9/10 | 6/10 · 7/10 | 7/10 · 7/10 |
| 3. `power-1.2.0` (reverted) | 8/10 · 9/10 | 9/10 · 10/10 | 9/9 · 7/9 |

Generator changes the pilots caused:
- **Power:** the spike's low scores came partly from ambiguous wording. With the wording fixed (1.0.0) both models
  trace these diagrams well. 1.1.0 requires a cross-feed trap in every task; 1.2.0 (more traps, larger answer
  sets) did not make it harder and was reverted. No power template meets the keep rule; we report that as it is.
- **Pilot 0 (idea spikes, 3 tasks per level, `results/spikes/README.md`)** ruled out circuits, Gantt charts, ECG
  strips and calendars (too easy) and showed that max_tokens 16000 cut off replies; it was raised to 64000 for
  every run after that.
- **After pilot 1:** `wildfire` was dropped (8/10 and 7/10, too easy). In `crossings` 4 of 10 answers were 14, so
  the generator now draws a target count first (`topo-1.0.1`; answers then ran from 15 to 23).
- **After pilot 2:** the made-up terrain was replaced by real elevation (`topo-2.0.0`), with the trail fairness
  rules from the lead's real-terrain spike. `flood` was rebuilt on real terrain with 6
  camps instead of 4 and a water route that must bend.
- **After pilot 3:** an automatic reviewer pass flagged that a dashed red trail could hide a crossing in a dash
  gap and that an end marker could sit on a contour. `topo-2.1.0` draws a solid magenta trail with a white casing,
  keeps both end markers 20 m clear of every contour and says so in the question. The scores did not move
  (pilot 4), so the misses are not a legibility effect.
- Line of sight and base camp missions were tried in spikes and not built: no tracing step, models got them right.

## What makes the tasks hard, and why the models failed
The hard step is tracing, not reading or arithmetic (pilot 4, checked against each task's `steps`):
- `crossings`: every miss is a miscount. Haiku counted too few lines in 8 of 9 misses; Luna was within two lines
  in 8 of 10 tasks but never exact.
- `sunset`: all 20 replies apply the stated rule correctly to their own count (daylight − flat time − 4 × count
  gives exactly their answer). The count of uphill crossings is wrong in 19 of 20, too low in 17.
- `flood`: of 14 misses, 10 name the dry camp most directly below the dam (6) or the camp nearest the dam (8; 4
  are both). The water was not followed around the bends of the slope.

The tasks stay fair to a careful person: crossings are at least 40 m apart, the trail never runs along a contour
and crosses every line at 25° or more; only one camp is within 40 m of the water route and every other camp is at
least 250 m from it.

## Final results
The 10 reported tasks, one run, both models (written by `scripts/package --fill-readme` from the two reported
folders):

<!-- final-results:start -->
| Task | Mission | Reference answer | Haiku | Luna |
|---|---|---|---|---|
| `topo-crossings-000100` | crossings | 11 | 7 ✗ | 5 ✗ |
| `topo-crossings-000101` | crossings | 11 | 5 ✗ | 11 ✓ |
| `topo-crossings-000102` | crossings | 16 | 12 ✗ | 10 ✗ |
| `topo-sunset-000100` | sunset | 37 | 45 ✗ | 45 ✗ |
| `topo-sunset-000101` | sunset | 9 | 13 ✗ | 25 ✗ |
| `topo-sunset-000102` | sunset | 29 | 49 ✗ | 57 ✗ |
| `topo-flood-000100` | flood | C4 | C4 ✓ | C4 ✓ |
| `topo-flood-000101` | flood | C5 | C5 ✓ | C5 ✓ |
| `topo-flood-000102` | flood | C1 | C6 ✗ | C6 ✗ |
| `topo-flood-000103` | flood | C1 | C3 ✗ | C3 ✗ |
| **Total** | | | **2/10** | **3/10** |

By mission: crossings Haiku 0/3, Luna 1/3; flood Haiku 2/4, Luna 2/4; sunset Haiku 0/3, Luna 0/3.
Facts: 20 of 20 replies are complete (`finish_reason` stop, no error); the run cost $0.0502; 10 of 10 tasks pass every automatic check; generator `topo-2.1.0`, seeds 100, 101, 102, 100, 101, 102, 100, 101, 102, 103.
<!-- final-results:end -->

## Key findings
- The same models that trace a breaker diagram well (6/10 to 9/10 on the power pilots) cannot count the contour
  lines along a trail (0/10 or 1/10). Discrete symbols joined by straight wires are followed; a path through dense,
  similar, curved lines is not.
- Single reads (one elevation, one label, the scale bar) and the arithmetic are reliably right; counting or
  following along a path through many lines is reliably wrong.
- A wide tolerance or a 3 or 4 way choice hides a tracing miss, so answers are exact integers or one of 6 names.
- With 3 tasks per type the scores are noise (5 of 18 results changed between two runs of the same images at
  different max_tokens), so every decision here uses 10 seeds.
- Answer format is not stable across runs even at temperature 0; every question shows one example answer in the
  exact expected form, and each reply is stored once and never re-asked.

- Two worked examples in the prompt did not help: on the same 48 pilot test calls the models got 8/48 right
  zero-shot and 6/48 with two examples (the few-shot experiment, `fewshot/summary.md` in the `extra` results
  folder). The skill is not picked up from a couple of demonstrations.

More notes with their sources: `NOTES.md`.

## Hand check
A person solved every reported task from the image alone, timed, and compared with the computed answer
(`results/human/`). One line per task:

<!-- hand-check:start -->
- `topo-crossings-000100`: hand check pending.
- `topo-crossings-000101`: hand check pending.
- `topo-crossings-000102`: hand check pending.
- `topo-sunset-000100`: hand check pending.
- `topo-sunset-000101`: hand check pending.
- `topo-sunset-000102`: hand check pending.
- `topo-flood-000100`: hand check pending.
- `topo-flood-000101`: hand check pending.
- `topo-flood-000102`: hand check pending.
- `topo-flood-000103`: hand check pending.
<!-- hand-check:end -->

## Run in Docker
Only Docker is needed. The key is passed at run time and never stored in the image. Everything a run produces is
written to `./out` on your machine (mounted at `/out` in the container).

```bash
docker build -t visual-task-factory .
mkdir -p out
export OPENROUTER_API_KEY=<your OpenRouter key>

# 1. Rebuild the 10 reported tasks from their seeds (same images, questions and reference answers; each file is
#    compared by SHA-256), then evaluate both models on the rebuilt tasks and score the answers.
docker run --rm -e OPENROUTER_API_KEY -v "$(pwd)/out:/out" --entrypoint sh visual-task-factory -c "python -m factory rebuild --tasks tasks/final --out /out/rebuilt && python -m factory eval --tasks /out/rebuilt --out /out/results"

# 2. Build, check, evaluate and score one fresh task.
docker run --rm -e OPENROUTER_API_KEY -v "$(pwd)/out:/out" visual-task-factory fresh --seed 4242
```

- **Outputs:** `out/rebuilt/` (the rebuilt `tasks.jsonl`, `images/`, `data/`), `out/results/` (`responses.csv`,
  `summary.json`, `run_config.json`, `raw/`), `out/fresh/` (the fresh task and its results).
- **Seed:** `--seed N` takes any whole number; the same seed always builds the same task. Add `--family topo`,
  `--template crossings|sunset|flood` or `--difficulty 1|2|3` to choose more than the seed.
- **Model:** both models are evaluated by default (`anthropic/claude-haiku-5.5` and `openai/gpt-6-luna`). To pick
  one, add `--model anthropic/claude-haiku-5.5` (repeatable) to the `eval` part of command 1.
- **Settings** are fixed in `eval/client.py`: temperature 0, reasoning effort high, max_tokens 64000.
- **Other commands:** `docker run --rm visual-task-factory --help`.
- The reported tasks were generated inside this image. On another operating system the same pixels are produced
  but the PNG compression can differ, so compare hashes inside Docker.

## Reused components
- Python libraries: matplotlib (drawing), NumPy, Pillow, contourpy (contour tracing), all pinned in `uv.lock`;
  `uv` to install them.
- Elevation data: USGS 3D Elevation Program (public domain) through AWS Open Data Terrain Tiles; the 16 tiles
  used are in `gen/topo/tiles/` with `SOURCES.md` and `SHA256SUMS`.
- Map conventions: USGS 7.5-minute topographic quadrangles and USGS Topographic Map Symbols. Rules: Naismith's
  rule (1892) for walking time; water follows the line of steepest descent.
- The organizers' format checker (`tools/track2-format-check/`), unchanged.
- Anthropic's API for the advisory reviewer (Claude Sonnet), and three.js for the demo site.
- OpenRouter's chat completions API for both models. No model output is used to make an image or an answer.
- The code was written during the event with AI coding agents working under each team member's direction.

## Manual interventions
- No image, question or reference answer was edited by hand. Every task is rebuilt from its seed by the commands
  above.
- The advisory reviewer model's flags on the first real-terrain maps led to two generator changes (solid trail,
  end markers clear of contours). It never changes an answer and never drops a task.
- People chose the four map areas, the fairness thresholds, and which templates to keep or drop after each pilot
  (rule and numbers under "Pilot results").
- The hand check of the reported tasks is done by a person from the image alone (see "Hand check").

## Limitations
- Four real places. Every seed takes a different window, but the same hills come back.
- In `sunset` most real trails climb one way, so the uphill count often equals the total count.
- `flood` answers are one of 6 camp names, so a guess is right 1 time in 6.
- PNG bytes are identical inside Docker on ARM and on x86-64 (tested), but differ from a build on macOS, where
  the pixels are identical and only the compression differs.
- Scores come from one run per task at temperature 0; replies are not perfectly repeatable across runs.
- Pilot sets are 10 tasks per template; differences of one or two tasks between models mean little.

## Slides
`slides/presentation.pptx`, the organizers' 5-slide template filled in by `slides/build.py` from the same result files.

## Team contributions
- **Alex Epstein (`Alex-Epstein`)**, team lead: plan and decisions, the core command line (`factory/`), the
  checks and the reviewer (`validate/`), the real-terrain spike, the report page and the demo site.
- **Shivam Raj (`tech-cosmos`)**: the evaluation client and scoring (`eval/`), the topographic family
  (`gen/topo`) and its pilots, Docker and packaging.
- **`WindHurtLZ`**: the power single-line family (`gen/power`) and its three pilots; subway spikes.
- **`dl3832`**: Gantt spike; the human baseline and the hand check of every reported task.
