# gen/topo: missions on a topographic map of a real place

A family plug-in (`contracts/FAMILY.md`). The image is a topographic map in the style of a USGS 7.5-minute
quadrangle, drawn from **real elevation**: brown contours every 20 m (10 m on gentle ground), heavy index contours,
spot elevations, water, latitude and longitude ticks, a scale bar, a legend and an incident box. The trail is a
solid magenta line with a thin white casing, so no dash gap can hide a crossing.

```bash
uv run python -m factory generate --family topo --template crossings --difficulty 3 --seeds 0-9 --out tasks/pilot_topo_crossings
uv run python -m factory validate --tasks tasks/pilot_topo_crossings
uv run python -m factory eval --tasks tasks/pilot_topo_crossings --out results/pilot_topo_crossings
uv run python -m unittest gen.topo.test_topo          # 7 checks, about 20 s
PYTHONPATH=. uv run python -m gen.topo.pilot_report   # the pilot table, from results/ (nothing typed by hand)
```

## Where the terrain comes from
`tiles/` holds 16 elevation tiles (1.9 MB) from the USGS 3D Elevation Program (public domain), served as AWS Open
Data Terrain Tiles: Bear Mountain, Breakneck Ridge and Harriman State Park (New York) and Mount Tamalpais
(California). `tiles/SOURCES.md` lists every URL and `tiles/SHA256SUMS` their checksums (a unit test checks them).
Nothing is downloaded at run time. The terrain loader, the trail builder and the map drawing are ported from the
lead's spike `results/spikes/real_terrain/gen.py`.

## How a task is made (`real.py`)
1. The seed picks the place (`seed % number of places`) and a 3200 m by 2400 m window on it. Elevation is decoded
   from the tiles, clamped at 0 m, blurred by 1 pixel and read by bilinear interpolation.
2. The marks are placed with the fairness rules below: a trail between two squares (`crossings`, `sunset`) or a
   dam and campsites (`flood`). Index-contour labels and spot elevations are placed clear of the marks, of the
   line a solver must trace and of the incident box.
3. The data JSON is written: tile names, crop window, contour levels, every mark and label. The elevation grid
   itself is not stored; it is rebuilt from `tiles/` and the window. Then the PNG is drawn from that file only.
4. The answer and its reasoning chain (`steps`, with the named decoys and planted wrong methods) are computed
   from the data; `solve_independent` computes the
   answer a second way. A draw where the two disagree, where two labels overlap, or where the answer would appear
   in the question is thrown away. A seed with no fair draw raises `RejectSeed`.
5. A second picture, `overlays/<task_id>_truth.png`, shows the same map with the computed truth in blue (a ring on
   every crossing, or the water's route). It is for people and the demo; no model ever sees it.

## Templates
| Template | Mission | Chain | Answer | Second solver |
|---|---|---|---|---|
| `crossings` | Rescue carry along a trail from S to E | follow the dashed trail through the contours → count every line it crosses, index lines included | integer | the drawn contour polylines (contourpy) intersected with the trail |
| `sunset` | Lost hiker must reach the hut before dark | read now, sunset and the flat walking time from the incident box → count the contour lines crossed going uphill (needs the labeled elevations to tell up from down) → Naismith's rule: 4 minutes per uphill line (2 on a 10 m map) → minutes to spare | integer, may be negative | same as `crossings`, uphill only |
| `flood` | The dam at D has failed | find downhill at D → follow the water at right angles to every contour as the slope turns → name the one camp in its path | camp name, C1 to C6 | a finer descent (4 m steps, a tighter slope stencil) |

## Difficulty (1 to 3)
| Template | 1 | 2 | 3 |
|---|---|---|---|
| `crossings`, `sunset` | 3 to 6 crossings, trail 300 m or longer | 7 to 10, 500 m | 11 to 20, 600 m (Harriman's gentle ground is left out) |
| `flood` | 3 camps, the water runs 600 m or more to the camp, dry camps 450 m or more off the route | 4 camps, 800 m, 350 m | 6 camps, 1000 m, 250 m, and the route bends at least 15° so that a dry camp lies more directly below the dam |

## Fairness rules (in code, so a careful person can get every task right)
- Trails: crossings are 40 m or more apart and from both ends; the trail never runs along a contour (within 2 m of
  its level for more than 40 m), never turns around within a quarter interval of a level, crosses every line at
  25° or more, and stays out of water. Both end markers stand at least 20 m (on the map) from every contour line,
  and the question says to count only the crossings between them.
- `sunset`: at least 2 uphill crossings; the flat walking time is printed, so no distance has to be measured.
- `flood`: the flooded camp is within 40 m of the water route, of the finer route and of four routes started 20 m
  off the dam; every other camp is at least the dry gap away from all six and 30 m or more below the dam (the flooded camp
  is downhill of the dam by construction), so elevation alone never gives the answer away.
- The incident box covers no mark, no part of the trail and no part of the water route.

## Pilot (10 seeds, difficulty 3, both models, `topo-2.1.0`)
| Template (difficulty 3, seeds 0-9) | Haiku | Luna | finish | cost | Verdict |
|---|---|---|---|---|---|
| `crossings` | 1/10 | 0/10 | stop | $0.0574 | KEEP (rule: at most 5 of 10 for at least one model) |
| `sunset` | 0/10 | 1/10 | stop | $0.0691 | KEEP (rule: at most 5 of 10 for at least one model) |
| `flood` | 3/10 | 3/10 | stop | $0.0426 | KEEP (rule: at most 5 of 10 for at least one model) |

From `results/pilot_topo_<template>/` (60 calls). What broke, checked against each task's `steps`:
- `crossings`: every miss is a miscount of the trail's contour crossings. Haiku counted too few in 8 of 9 misses
  (by up to 9); Luna was within two lines in 8 of 10 but never exact, too few in 5 and too many in 5.
- `sunset`: all 20 replies apply the stated rule correctly to their own count (daylight − flat time − 4 × count
  gives exactly their answer). The count of uphill crossings is wrong in 19 of 20, too low in 17.
- `flood`: with 6 camps a guess is right 1 time in 6. Of 14 misses, 10 name the dry camp that lies most directly
  below the dam (the designed decoy, 6 times) or the camp nearest the dam (8 times; 4 are both). The water route
  was not followed around its bends.

The first real-terrain pilot (`topo-2.0.0`: dashed red trail) scored crossings 1/10 · 0/10, sunset 0/10 · 0/10,
flood 2/10 · 3/10. A reviewer pass then asked for a trail no dash gap could hide a crossing in and for end markers
clear of every contour; 2.1.0 has both, and the scores did not move, so the misses are not a legibility effect.

Rule: keep a template only if at most 5 of 10 are right for at least one model, with failures from reasoning.

## Known limits
- On real slopes most fair trails climb one way, so in `sunset` the uphill count often equals the total count
  (8 of the 10 pilot trails have no downhill crossing).
- `crossings` answers at difficulty 3 fall between 11 and 20 (11 to 19 in the pilot, and 4 of the 10 are 11).
- Four places only. Windows differ per seed, but the same hills return.
- PNG bytes are identical run to run on one machine; the factory's `reproducible` check covers that. Across
  machines the font rasterizer may differ.

## Not included
- **Wildfire** (which escape trail stays below the fire): 8/10 and 7/10 in the pilot, dropped by the rule.
- **Line of sight** and **base camp**: no tracing step; models got them right in the spikes
  (`results/spikes/missions/summary.md`, `results/spikes/missions_v2/`).
- The earlier synthetic-field generator and its pilot results: `results/spikes/topo_synthetic/README.md`.
