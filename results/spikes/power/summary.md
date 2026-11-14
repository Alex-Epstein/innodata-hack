# Spike C: power single-line diagram (#5), Nov 14, 11:40 to 11:48

Generator: `gen.py` (data → PNG → answer, all in code). Tasks: `tasks/tasks.jsonl` (9 tasks). Evaluation:
`uv run python -m eval.run --tasks results/spikes/power/tasks --out results/spikes/power/results`
(temperature 0, reasoning effort high, max_tokens 64000). Per-call results: `results/responses.csv`; totals: `results/summary.json`.

The system is a main-tie-main (secondary-selective, IEEE 141) layout: two 13.8 kV sources and buses, a N.O. main tie,
feeder breakers → transformers → 480 V MCCs → load and panel breakers → loads (named, with kW). One feeder from
each bus crosses over to an MCC drawn under the *other* bus, and a N.O. tie joins those two MCCs. Each answer is
computed twice (breadth-first reachability from the sources; an independent fixed-point rule walk, bus → MCC →
load) and the two must agree. A text-overlap check runs on every image.

## Results (correct / tasks)
| Level | Question | claude-haiku-5.5 | gpt-6-luna |
|---|---|---|---|
| L1: one source, ~8 loads | one breaker trips: which loads lose power (list) | 3/3 | 3/3 |
| L2: two sources, 14+ loads, crossing feeders, 2 N.O. ties | two breakers trip: which loads lose power (list) | 3/3 | 3/3 |
| L3: same system | a main breaker and one more trip; operator opens the dead side's crossing feeder and closes the MCC tie: total kW without power (4 to 5 steps) | 3/3 | 3/3 |

- Cost: $0.0181 for 18 calls. `scripts/budget` before: $0.42 used; after: $0.46 used (other sessions running too).
- Every reply finished with `finish_reason: stop`. No retries.
- The models found it easy: the hardest L3 task took Haiku 3319 output tokens and Luna 1844 (reasoning included).

## What we learned
- **Power one-line diagrams as built are too easy. Ruled out**, like circuits and Gantt. Clean orthogonal lines with
  labelled breakers are traced reliably, and the crossing-feeder trap (an MCC drawn under the other bus) did not
  fool either model.
- **Same lesson as ECG, circuit, Gantt:** a clean schematic with crisp labels is read perfectly; graph logic on top
  of it is easy for both models. Difficulty has to come from perception of continuous or crowded structure
  (topo contours, subway diagonals), not from more logic steps on a clean diagram.
- **A fairness trap I hit and fixed:** with "power flows either way", closing the MCC tie back-feeds the dead 13.8 kV
  bus through the crossing feeder's transformer and restores everything. The two methods disagreed until the
  rule walk handled back-feed. The final L3 question has the operator open that feeder first (the real switching
  practice), so back-feed never decides an answer.

## Honest answers
- **Can a careful person solve L3 in 2 to 3 minutes?** Yes. I checked power-000303 by hand (675 kW) in about 2 minutes.
- **Does it look like the real thing?** Close to a plant single-line: title block, IEEE-style symbols, kVA ratings,
  MCC and panel names. No relay or metering detail.
