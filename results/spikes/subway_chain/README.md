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
**Run 2 (reported, after the label fix):** every kept map passes a legibility check (each label is nearer its own
dot than any other dot, and overlaps no other label or bullet). Funnel: 11 maps generated, 6 kept, 5 rejected for
unclear labels (`tasks/funnel.json`). Second solver agrees 6/6.

| Template | Haiku 5.5 | GPT-6 Luna |
|---|---|---|
| T1 fastest trip | 3/3 | 2/3 |
| T2 worst closure | 3/3 | 1/3 |
| **Total** | **6/6** | **3/6** |

Cost run 2: $0.05 (budget $0.75 before, $0.85 after; other teammates were also spending).

**Run 1 (superseded):** Haiku 3/5, Luna 0/5 on the valid tasks, with 502 excluded. Its label placer let a J-line
label ("Medical Center") sit under an L-line dot; both models read it wrong. After fixing the placer, Haiku went
6/6. **Lesson: part of run 1's difficulty came from label ambiguity, not reasoning.** On clean maps, subway v2 is
hard for Luna and easy for Haiku.

## Where Luna broke (run 2)
- 401 (T1): 40 vs 42. It counted one segment too few on the route (same miss as both models in run 1).
- 501 (T2): right weekend, detour +3 vs +4 (a recount off by one).
- 1503 (T2): "Weekend 1 and Weekend 2, 4". It thought Weekend 2 also forces a +4 detour; the truth is +2 (it missed
  the shorter detour).

## Fairness and honesty notes
- A careful person: about 3 minutes per task. Not yet timed by a teammate.
- 45% of maps fail the legibility check: the label placer needs work (smaller font in dense areas, more candidate
  positions) before this family can feed a reliable pipeline.
- Haiku 6/6 means subway v2 is not a strong difficulty story for both models; Luna's 3/6 failures are all counting
  slips along routes.

Reproduce: `uv run python results/spikes/subway_chain/chain_gen.py && uv run python results/spikes/subway_chain/check.py`,
then `uv run python -m eval.run --tasks results/spikes/subway_chain/tasks --out results/spikes/subway_chain/results`.
