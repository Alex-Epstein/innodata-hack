# Spike D: ECG rhythm strip (#15), Nov 14, 11:17 to 11:21

Generator: `gen.py` (data → PNG → answer, all in code). Tasks: `tasks/tasks.jsonl` (12 tasks). Evaluation:
`uv run python -m eval.run --tasks results/spikes/ecg/tasks --out results/spikes/ecg/results`
(temperature 0, reasoning effort high, max_tokens 32000). Per-call results: `results/responses.csv`; totals: `results/summary.json`.

## Results (correct / tasks)
| Level | Question | claude-haiku-5.5 | gpt-6-luna |
|---|---|---|---|
| L1: regular rhythm | heart rate in bpm, accepted within 3 bpm | 3/3 | 3/3 |
| L2: sinus rhythm + one early beat | R-R interval between two marked beats, in ms (exact) | 3/3 | 3/3 |
| L3: irregular rhythm, 10 s | which beat starts the longest R-R interval (exact) | 3/3 | 3/3 |
| L4 (added after L1 to L3 came back 18/18) | longest minus shortest R-R interval, in ms (exact) | 3/3 | 3/3 |

- Cost: $0.011069575 for 24 calls. `scripts/budget` before: $0.20 used; after: $0.21 used.
- Every reply finished with `finish_reason: stop`. No retries.
- Failures to show: none. Both models answered all 12 tasks correctly.

## What we learned
- **ECG strips as built are too easy. Ruled out.** The models locate each R peak to within a pixel or two and convert
  to boxes. On `ecg-000402`, claude-haiku-5.5 listed all 12 R-R intervals in small boxes
  (22, 14, 12, 24, 25, 14, 22, 15, 23, 24, 11, 10), which is exactly the data.
- **Why it matters for the idea choice:** sharp, isolated marks on a regular grid are read precisely, even at
  1 mm (8 px) resolution. Questions built on measuring such marks will not stump these models, however many
  steps follow. Difficulty has to come from something else (crowded two-dimensional layouts, connectivity).

## Honest answers
- **Can a careful person solve L3 in 2 to 3 minutes?** Yes. The longest gap stands out by eye; counting the boxes
  of the two nearest candidates confirms it (the margin is 3 small boxes). L4 takes longer, about 3 minutes.
- **Does it look like the real thing?** Close to a monitor rhythm strip: pink 1 mm / 5 mm grid, calibration pulse,
  lead label, speed and gain in the header. A clinician would notice every beat has the same shape and there is no
  artifact. L3 image: `tasks/images/ecg-000301.png`.
- **Checks:** all 12 tasks pass; each answer is recomputed from R peaks detected in the PNG pixels alone.
