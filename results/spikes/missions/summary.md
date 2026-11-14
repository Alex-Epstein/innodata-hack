# Chained questions on the topo map, plain and as missions (issue #29, directives #31 and #39)

Same 9 maps asked two ways (plain wording, then as missions with a scenario box drawn on the map), plus 3 flash
flood and 3 wildfire maps. 3 tasks per question type, both models, max_tokens 64000, every reply `stop`.
Table printed by `summarize.py` from the `responses.csv` files:

| Run | Question type | Haiku | Luna | Truth -> H: Haiku; L: Luna | finish | cost |
|---|---|---|---|---|---|---|
| plain wording | `topo.line_of_sight` | 1/3 | 3/3 | ["B", "D"] -> H: D; L: B, D · ["A"] -> H: A; L: A · ["C"] -> H: A; L: C | stop | $0.0918 for the run |
| plain wording | `topo.hike_time` | 1/3 | 1/3 | 42 -> H: 48; L: 45 · 103 -> H: 88; L: 90 · 154 -> H: 140; L: 125 | stop | $0.0918 for the run |
| plain wording | `topo.campsite` | 3/3 | 3/3 | C1 -> H: C1; L: C1 · C1 -> H: C1; L: C1 · C3 -> H: C3; L: C3 | stop | $0.0918 for the run |
| mission | `mission.sar_line_of_sight` | 1/3 | 3/3 | ["B", "D"] -> H: A, B, D; L: B, D · ["A"] -> H: A, D; L: A · ["C"] -> H: C; L: C | stop | $0.0693 for the run |
| mission | `mission.lost_hiker_sunset` | 3/3 | 3/3 | 33 -> H: 32; L: 28 · 52 -> H: 52; L: 58 · 36 -> H: 44; L: 42 | stop | $0.0693 for the run |
| mission | `mission.base_camp` | 2/3 | 2/3 | C1 -> H: C1; L: C1 · C1 -> H: C3; L: C1 · C3 -> H: C3; L: C1 | stop | $0.0693 for the run |
| mission | `mission.flash_flood` | 2/3 | 2/3 | C4 -> H: C4; L: C2 · C3 -> H: C3; L: C3 · C4 -> H: C2; L: C4 | stop | $0.0189 for the run |
| mission | `mission.wildfire` | 3/3 | 3/3 | Cedar Trail -> H: Cedar Trail; L: Cedar Trail · Summit Trail -> H: Summit Trail; L: Summit Trail · Ridge Trail -> H: Ridge Trail; L: Ridge Trail | stop | $0.0078 for the run |

Total for these runs: 48 calls, $0.1878 (0.0918 + 0.0693 + 0.0189 + 0.0078).

## Which step broke (saved `steps` compared with each model's reasoning)
- **Line of sight / SAR (Haiku 2/6, Luna 6/6).** Haiku reads the point elevations about right, then guesses at
  "is the ground between above the line": it names a different wrong set each time on the same map (D, then
  A, B, D). Luna answers in three lines and is right every time, so this is not hard for Luna.
- **Hike time / hiker vs sunset (2/6 plain, 6/6 as a mission, same maps).** Trail length is read right every time
  (2.44 km read, 2.439 km true). The step that moves is the total ascent, which is the contour-crossing count
  again: 255 and 270 m read against 334 true in the plain run, then 335 m in the mission run. With ±10 minutes
  accepted (that is ±50 m of ascent) the miss sometimes fits inside the tolerance.
- **Campsite / base camp (6/6 plain, 4/6 as a mission, same maps).** The misses are single wrong reads (an
  elevation of 249 m read as 440 to 480 m; a stream 217 m away judged too far), not a broken chain.
- **Flash flood (4/6).** Both misses are the tracing step: the model picks the camp "most directly below" the
  dam instead of following the contours round the spur (chosen camps were 340 m and 586 m off the water route).
- **Wildfire (6/6).** Too easy as built: one glance at where each trail goes relative to the summit settles it.

## What this says
1. **3 tasks per type is noise.** The same maps went 2/6 to 6/6 (hike time) and 6/6 to 4/6 (campsite) between two
   wordings. Nothing here is as solid as the plain crossing count (0/12 over two runs, #18). Do not quote these as
   difficulty numbers; a pilot needs 10 or more tasks per type.
2. **The step that breaks is tracing a line across many contours** (adding up ascent, following water downhill).
   Single reads, the scale bar and the arithmetic are fine. A chain is only as hard as its tracing step, and a
   wide tolerance or a 3 or 4 way choice hides the miss.
3. **Suggestion for the real generator:** keep the mission framing, and make the answer hinge on the trace with an
   exact answer: hiker vs sunset with ascent defined as 20 m per uphill contour crossed and ±5 minutes (about one
   contour); flash flood with 6 camps or "which stream does the water join"; SAR only with Haiku-hard margins is
   not enough since Luna gets 6/6.

## Fairness (could a careful person do it in about 3 minutes?)
- Hike time: yes. A reader who counts uphill contour crossings lands within 6 minutes on every task (checked in code).
- Campsite, flash flood, wildfire: yes, about 2 minutes. Margins are wide (flooded camp within 45 m of the water
  route, the others 340 m or more away; trails top out 40 m or more above or below the fire).
- **Line of sight: not yet.** The visible hikers clear the ground by only 25.9 to 28.4 m, barely more than one
  contour line. A real generator should require 60 m or more.
- Scenario box: checked in code that it covers no mark, no asked trail, no sight line and no part of the water route.

## For the demo
Each mission data file has `overlay` (sight lines with their tightest point, the hiker's route, site verdicts, the
water route, each trail's highest point) so the true answer can be drawn on the map, and `steps` with the chain.

## Limits
- Generation time: flash flood 1.5 s for 3 tasks, wildfire about 20 s per task, but the hike-time search took
  minutes for 3 tasks. Too slow for a live "pick a seed" unless the search is tightened.
- Wildfire seed 1503 found nothing in 300 tries and needed the limit raised to 3000.
- The mission maps reuse the plain maps (same terrain and marks, renamed T to R and E to H), so the two wordings are
  a paired comparison, not 18 independent tasks.
