# Innodata Hackathon: Visual Task Factory

> **Team / agents: start at `AGENTS.md`** (new here: `docs/SETUP.md`). This README is the submission README;
> the headings below are the ones the organizers' format checker requires.

## Problem statement
Vision models read labels and do arithmetic well. They are much weaker when the answer depends on **following a
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

## Reported folders
- Tasks: `tasks/final/`
- Results: `results/final/`

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

Where the numbers come from: pilots 1 and 2 are stored with the idea spikes (`results/spikes/topo_synthetic/README.md`
lists each run); pilot 3 is in the `pilot_topo_<template>` folders under `results/`, with its task sets under
`tasks/`. Each folder has `responses.csv`, `summary.json`, `run_config.json` and the raw replies.
`PYTHONPATH=. uv run python -m gen.topo.pilot_report` prints the pilot 3 table from those files.

Generator changes the pilots caused:
- **Pilot 0 (idea spikes, 3 tasks per level, `results/spikes/README.md`)** ruled out circuits, Gantt charts, ECG
  strips and calendars (too easy) and showed that max_tokens 16000 cut off replies; it was raised to 64000 for
  every run after that.
- **After pilot 1:** `wildfire` was dropped (8/10 and 7/10, too easy). In `crossings` 4 of 10 answers were 14, so
  the generator now draws a target count first (`topo-1.0.1`; answers then ran from 15 to 23).
- **After pilot 2:** the made-up terrain was replaced by real elevation (`topo-2.0.0`), with the trail fairness
  rules from the lead's real-terrain spike. `flood` was rebuilt on real terrain with 6
  camps instead of 4 and a water route that must bend.
- Line of sight and base camp missions were tried in spikes and not built: no tracing step, models got them right.

## What makes the tasks hard, and why the models failed
The hard step is tracing, not reading or arithmetic (pilot 3, checked against each task's `steps`):
- `crossings`: every miss is a miscount. Haiku counted too few lines in 8 of 9 misses; Luna too few in 6 and too
  many in 4.
- `sunset`: all 20 replies apply the stated rule correctly to their own count (daylight − flat time − 4 × count
  gives exactly their answer). The count of uphill crossings is wrong in all 20, too low in 17.
- `flood`: of 15 misses, 10 name the dry camp most directly below the dam (6) or the camp nearest the dam (8; 4
  are both). The water was not followed around the bends of the slope.

The tasks stay fair to a careful person: crossings are at least 40 m apart, the trail never runs along a contour
and crosses every line at 25° or more; only one camp is within 40 m of the water route and every other camp is at
least 250 m from it.

## Key findings
- Single reads (one elevation, one label, the scale bar) and the arithmetic are reliably right; counting or
  following along a path through many lines is reliably wrong.
- A wide tolerance or a 3 or 4 way choice hides a tracing miss, so answers are exact integers or one of 6 names.
- With 3 tasks per type the scores are noise (5 of 18 results changed between two runs of the same images at
  different max_tokens), so every decision here uses 10 seeds.
- Answer format is not stable across runs even at temperature 0; every question shows one example answer in the
  exact expected form, and each reply is stored once and never re-asked.

More notes with their sources: `NOTES.md`.

## Hand check
A person solves each reported task from the image alone and compares with the computed answer. One line per
task is added here when the reported set is frozen.

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
- OpenRouter's chat completions API for both models. No model output is used to make an image or an answer.
- The code was written during the event with AI coding agents working under each team member's direction.

## Manual interventions
- No image, question or reference answer was edited by hand. Every task is rebuilt from its seed by the commands
  above.
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

## Team contributions
- **Alex Epstein (`Alex-Epstein`)**, team lead: plan and decisions, the core command line (`factory/`), the
  checks (`validate/`), the real-terrain spike, the demo.
- **Shivam Raj (`tech-cosmos`)**: the evaluation client and scoring (`eval/`), the topographic family
  (`gen/topo`) and its pilots, Docker and packaging.
- **`WindHurtLZ`**: the power one-line family and its pilots; subway spikes.
- **`dl3832`**: Gantt spike; human baseline and hand checks.
