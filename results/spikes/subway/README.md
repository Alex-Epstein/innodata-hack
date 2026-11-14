# Spike F: subway map (issue #17)

NYC / Vignelli-1972-style schematic of an invented city ("Port Calder"): MTA trunk colors, route bullets at each
terminus, black dots for stations, white circles for transfer stations, octilinear routing with diagonal crossings
that have **no** station (a tracing trap), and a yellow service notice at L3.

- `gen.py`: data first (`tasks/data/<id>.json`), PNG rendered from that data, answer by 0-1 BFS over (station, line).
- `check.py`: independent second solver (heapq Dijkstra on a graph rebuilt from coordinates). **Agrees on 9/9.**
- `tasks/`: 9 tasks in `contracts/SCHEMA.md` format · `results/`: `eval.run` output (responses.csv, raw/, run_config.json).

| Level | Map | Question | Haiku 5.5 | GPT-6 Luna |
|---|---|---|---|---|
| L1 | 3 lines, ~30 stations | fewest stops A to B | 3/3 | 3/3 |
| L2 | 5 lines, ~58 stations | fewest train changes A to B | 2/3 | 3/3 |
| L3 | 7 lines, ~90 stations, 1 station closed | fewest stops A to B, honoring the notice | **2/3** | **0/3** |

Cost: $0.04 for the 18 calls (budget $0.25 before, $0.29 after). Every row has finish_reason `stop`; no errors.

## Failures (model vs truth)
- **Luna, subway-000302 (L3): 9 vs 11.** Luna found exactly the reference route (red to Clement Hts, green to Ferris
  Av, yellow to Elwood St, purple to Greystone Hts) and avoided the closed station, but counted 2 stops instead of 3 on
  two diagonal legs. A counting/tracing failure on the right plan.
- **Haiku, subway-000201 (L2): 3 vs 2.** It claimed the only transfer on the 4 line leads nowhere useful, then listed a
  route whose own steps contradict its count ("change 2" is its third change). It misread which lines meet where.
- Haiku 000301 (L3): 12 vs 13 (one station dropped on the detour). Luna 000301: 9 vs 13; Luna 000303: 5 vs 6.

## Honest assessment
- **Can a careful person solve L3 in 2 to 3 minutes?** Yes: the detour is capped at 14 stops by design, and the notice
  names the closed station. Tracing a finger along the colored line and counting dots is all it takes.
- **Does it look like the real thing?** Close to the MTA/Vignelli diagram (trunk colors, bullets, transfer circles,
  notice box). Not yet: station-name pills, line thickness for express, borough/water background.
- **Hard because of reasoning, not legibility:** text is 7.6 pt with a white halo; labels are placed by a collision
  search. The L3 failures are miscounts and wrong transfers on correct-looking plans.
- **Caveats:** 9 tasks is a spike, not evidence. L2 answers are all 2 (the generator picks the max-transfer pair);
  it needs answers spread 1 to 4. L1 is solved by both models.

Example L3 image: `results/spikes/subway/tasks/images/subway-000302.png`

Reproduce: `uv run python results/spikes/subway/gen.py && uv run python results/spikes/subway/check.py`, then
`PYTHONUTF8=1 uv run python -m eval.run --tasks results/spikes/subway/tasks --out results/spikes/subway/results`
(`PYTHONUTF8=1` is needed on Windows until `eval/client.py` reads and writes its cache as UTF-8).
