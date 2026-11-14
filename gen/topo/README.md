# gen/topo: missions on a topographic map

A family plug-in (`contracts/FAMILY.md`). The image is a USGS 7.5-minute quadrangle look-alike: brown contours
every 20 m, heavy index contours every 100 m, spot heights, trails, streams, a scale bar and an incident box.

```bash
uv run python -m factory generate --family topo --template flood --difficulty 3 --seeds 0-9 --out tasks/pilot_topo_flood
uv run python -m factory validate --tasks tasks/pilot_topo_flood
```

## How a task is made
1. `terrain.new_terrain(rng)`: a tilted plane plus 5 to 7 Gaussian hills. The elevation at any point is a formula
   of the data (`terrain.elev`), so nothing is ever read off the picture.
2. `missions.place_<template>`: the marks (points, trails) and the incident box text, with the fairness rules below.
3. `terrain.decorate`: spot heights, a second trail, streams and index-contour labels, kept clear of the marks, of
   the lines a solver must trace and of the incident box.
4. The data JSON is written, then `render.render` draws the PNG from that file's content only.
5. `missions.answer_<template>` computes the answer and the reasoning chain (`steps`) on the analytic field;
   `solve_independent` recomputes the answer on the 10 m grid and the contour polylines traced from it (contourpy).
   A draw where the two disagree is thrown away. So is one where two labels overlap or the answer would appear
   in the question. After 60 failed draws the seed raises `RejectSeed`.

## Templates
| Template | Mission | Chain | Answer |
|---|---|---|---|
| `crossings` | Rescue carry from S to E | trace the trail, count every contour line it crosses | integer |
| `sunset` | Lost hiker must reach the hut before dark | read trail length, now and sunset from the incident box → count the contour lines crossed going uphill → Naismith's rule (15 min per km + 4 min per uphill contour) → minutes to spare | integer, may be negative |
| `flood` | Dam fails at D | read which way is downhill at D → trace the water at right angles to the contours → which camp it reaches | camp name |
| `wildfire` | Fire at F, crew at S | read the fire's elevation → find the highest ground on each escape trail → which one stays below the fire | trail name |

## Difficulty (1 to 3) = clutter to trace through
| Template | 1 | 2 | 3 |
|---|---|---|---|
| `crossings`, `sunset` | 1 leg, 3 to 6 crossings | 2 legs, 7 to 12 | 3 legs, 14 to 24; `sunset` needs 4 or more uphill and 3 or more downhill |
| `flood` | 3 camps, others 500 m or more off the route | 4 camps, 400 m | 6 camps, 300 m, and the route bends so that a dry camp lies more directly below the dam |
| `wildfire` | 2 trails, 60 m margin | 3 trails, 40 m | 4 trails, 40 m, every trail climbs at least 40 m first |

## Fairness rules (in code)
- Trails: no contour is grazed (crossings 25 m or more apart, none shallow, none within 60 m of an end marker), and
  the trail never turns around within 5 m of a contour level.
- `sunset`: the last leg is stretched so the trail's true length is the printed length to within 1 m.
- `flood`: the flooded camp is within 45 m of the water route from the dam, from the grid route and from four
  starts 25 m off the dam; every other camp is at least the dry gap away from all of them; every camp is below the dam.
- `wildfire`: each trail's highest ground is at least the margin above or below the fire, on the field and on the grid.
- The incident box covers no mark, no asked trail and no part of the water route.

## Not included
- **Line of sight** (search and rescue). On this terrain a visible hiker almost never clears the ground by 60 m,
  the margin a person needs; the spike used 26 to 28 m and `openai/gpt-6-luna` still scored 6/6
  (`results/spikes/missions/summary.md`).
- **Base camp** (three rules per site): single reads, no tracing step; 10 of 12 right in the spike.
