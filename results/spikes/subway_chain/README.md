# Subway v2: chained routing questions (issue #34)

Same map generator as spike F (`../subway/gen.py`: 7 lines, ~90 stations, Vignelli/MTA style). Each question chains
3 to 5 reads and stated rules into one exact answer; the intermediate facts are in each task's `steps` field.

- `chain_gen.py`: data, then PNG, then answers and steps (Dijkstra over (station, line) with lexicographic costs).
- `check.py`: independent second solver (Bellman-Ford on a graph rebuilt from coordinates). **6/6 agree.**
- `tasks/`: 6 tasks (SCHEMA format) · `results/`: `eval.run` output at max_tokens 64000.

## Templates
**T1 `subway.fastest_trip`**: per-line running times in a table on the map, plus 5 min per change of trains (stated in
the question), plus one closed station (notice). What is the shortest travel time from A to B, in minutes?
Chain: read the notice → read the running times → find candidate routes and count stops per leg → minutes = stops x
line time + 5 x changes → take the minimum. Chosen so the fewest-stops route is at least 3 min slower than the fastest
one, and the closure adds at least 3 min.

**T2 `subway.worst_closure`**: a notice lists 3 weekend closures. Which weekend makes the fewest-stops trip A to B
longest, and by how many stops? Chain: count the normal trip → recount under each closure (3x) → compare → subtract.
One closure is a decoy: a transfer station the normal route only rides through, so closing it adds 0.

## Results (both models, max_tokens 64000, all finish_reason stop)
| Template | Haiku 5.5 | GPT-6 Luna |
|---|---|---|
| T1 fastest trip | 2/3 | 0/3 |
| T2 worst closure (valid tasks only) | 1/2 | 0/2 |
| **Total valid** | **3/5** | **0/5** |

**subway-000502 is INVALID and excluded:** the "Medical Center" label (a J-line station) sits directly under the
L-line dot Harbor Blvd. Both models read it as an L station and answered "Weekend 1, 0". That is a label-placement
defect, not a reasoning failure. Fix: the label placer must reject a position that is closer to another station's dot
than to its own (next commit), then regenerate and rerun.

Cost: $0.06 for 12 calls (budget $0.56 before, $0.63 after).

## Where the models broke
- **T1:** route tracing. On 401 both answered 40 vs 42: Haiku's own route lists Courthouse → Newbury Av → 74 St and
  skips 82 St, a station clearly drawn on the blue line between them (one segment, 2 min). Luna 403: 33 vs 43, close to
  the no-closure time (31), so it likely ignored the closed transfer.
- **T2:** the per-closure recount. 501: both picked the right weekend but miscounted the detour (Haiku +5, Luna +3,
  truth +4). Luna 503: picked the +2 weekend over the +4 one.

## Fairness
A careful person: T1 takes about 3 minutes (find 2 or 3 candidate routes, count dots per leg, multiply, add 5s);
T2 about 3 minutes (one normal count plus three recounts, the decoy recount is instant). Not yet timed by a person on
the team. Known label risk (see 502, and 401's "Juniper St"/"Jessup Jct" pair): fixed next.

Reproduce: `uv run python results/spikes/subway_chain/chain_gen.py && uv run python results/spikes/subway_chain/check.py`,
then `uv run python -m eval.run --tasks results/spikes/subway_chain/tasks --out results/spikes/subway_chain/results`.
