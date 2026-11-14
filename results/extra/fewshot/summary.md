# Few-shot experiment: do 2 worked examples help?

**Question.** If we put two of our worked, step-by-step examples in the prompt, do the models get more of the
next tasks of the same kind right? (Asked because judges may ask "why would an AI company train on this data?")

**Answer: no.** Two worked examples in context did not improve either model. Across all 48 test calls the models
got 8/48 right zero-shot and 6/48 right with two examples. Every per-mission change is 0 to 2 tasks out of 8, well
inside run-to-run noise at this size.

## Setup
- Tasks: the topo pilot sets `tasks/pilot_topo_{crossings,sunset,flood}` (10 each, difficulty 3, the files the
  baseline was run on). Per mission, seeds 0 and 1 are the worked examples and seeds 2 to 9 are the 8 test tasks,
  so no example is ever a test task.
- A worked example = its map image + its question + a short solution written by a fixed template per mission from
  the task's `steps` and data JSON (code, not a person or a model; each template asserts it reaches the task's
  answer). Templates and the exact prompt are in `eval/fewshot.py` and `run_config.json`.
- Prompt: intro line, example 1 (image, question, solution ending `FINAL ANSWER: ...`), example 2, then the test
  map and the test question in exactly the eval prompt (`eval/scoring.py`). One user message, 3 images.
- Settings as in eval: temperature 0, reasoning effort high, max_tokens 64000, both models, through OpenRouter with
  eval.client's request shape, retries and raw-log scrubbing; own cache (`cache/fewshot`).
- Baseline: the existing zero-shot replies in `results/pilot_topo_*/responses.csv` for the same 8 tasks (not re-called).
- 48 calls, all complete (finish_reason stop, no errors, no retries). Cost $0.1708 (OpenRouter $2.09 used before,
  $2.28 after).

## Results (correct out of 8 test tasks)
| Mission | Model | Zero-shot | 2-shot |
|---|---|---|---|
| Crossings | Claude Haiku 5.5 | 1/8 | 0/8 |
| Crossings | GPT-6 Luna | 0/8 | 1/8 |
| Sunset | Claude Haiku 5.5 | 0/8 | 1/8 |
| Sunset | GPT-6 Luna | 1/8 | 0/8 |
| Flood | Claude Haiku 5.5 | 3/8 | 3/8 |
| Flood | GPT-6 Luna | 3/8 | 1/8 |
| **All** | **both** | **8/48** | **6/48** |

Closeness on the numeric missions (mean absolute error, same 8 tasks) also did not move in a useful way:
crossings Haiku 4.9 to 4.5 lines, Luna 2.3 to 3.0; sunset Haiku 13.0 to 12.5 minutes, Luna 12.0 to 13.0.

## How the reasoning changed
1. **Luna anchored on the examples' answers instead of tracing.** The two crossings examples answered 12 and 11.
   With them in the prompt, 6 of Luna's 8 crossings answers were 10 or 11 (zero-shot they ranged from 7 to 21),
   and its average error went from +0.5 to -3.0 lines. On topo-crossings-000007 (truth 16) it went from
   "counting each contour crossing, including index contours, gives 21" to "I count 10 contour-line crossings in total".
2. **Haiku copied the shape of the solution, not the skill.** On topo-crossings-000008 (truth 13) the 2-shot reply
   walks the trail leg by leg like the example, then concludes "Reading the contour spacing by eye, I estimate about
   9 crossings in total" (zero-shot said 4). Closer, still wrong, and it says itself it did not trace each crossing.
3. **The one new sunset hit came from a shortcut.** On topo-sunset-000002 Haiku followed the example's arithmetic
   layout exactly and got 10 (truth 10), but it found the uphill count from the elevation difference, "the trail
   climbs roughly from the 600 m level to about 700 m", rather than by tracing. It works only when the trail never
   dips, so it does not show the tracing skill was picked up.

## What this means
The models already understand the rules (they read the incident box and do the Naismith arithmetic correctly in
both conditions). What fails is the perceptual tracing step, and two examples in the prompt do not teach that:
the models copy the format and lean on the example answers. A skill that a couple of in-context examples cannot
unlock is the case for training data at scale, where the model gets many tasks plus an automatic checker.

## Limits (say these out loud)
- 8 tasks per mission and model. A difference of 1 or 2 tasks is noise; this run can only show there is no large effect.
- One prompt design, one pair of examples per mission, no repeats. Other examples or more of them might do better.
- Both sunset examples happen to have 0 downhill crossings, so they never show the "ignore downhill lines" step.
- GPT-6 Luna's visible replies are short (its reasoning is hidden), so its reasoning change is judged from its
  final text only.
- The pilot task files are generator 2.1.0 and match their baseline results (image hashes checked against the raw
  requests). The official final set is separate and not used here.

Files: `responses.csv` (same columns as eval), `raw/` (one JSON per call), `run_config.json` (prompt parts,
example and test task ids, per-task answers in both conditions, totals). Script: `eval/fewshot.py`.
