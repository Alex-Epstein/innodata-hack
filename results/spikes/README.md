# Idea spikes (pilot 0), Nov 14 ~10:55 to 11:05

Rough throwaway generators (`gen.py`, `run.py` in each folder) used to choose the image family. Both models are
called through OpenRouter: temperature 0, reasoning effort high, max_tokens 16000. Raw responses are in `raw/`.
**This counts as our first pilot** for the README's "Pilot results" section.

## Results
| Family | Level | claude-haiku-5.5 | gpt-6-luna |
|---|---|---|---|
| Calendar: earliest common free slot | L1: 3 people, 30 min | 3/3 | 3/3 |
| | L2: 4 people, 45 min, near misses | 2/3 | 3/3 |
| | L3: 6 people, 60 min, dense, near misses | 1/3 (2 cut off by `length`) | 1/3 |
| Circuit: equivalent resistance | L1: 4 R | 3/3 | 3/3 |
| | L2: 6 or 7 R, hidden parallel | 3/3 | 3/3 |
| | L3: 10 R, 3 levels deep, short or dead end | 3/3 | 3/3 |

Cost: calendar $0.0656 for 18 calls, circuit $0.0164 for 18 calls.

## What we learned
- **Circuits are too easy.** Both models read every label and did the algebra. Ruled out.
- **The calendar difficulty climbs with the level, and the failures are reasoning failures.** Models read a block edge
  15 minutes off, which turns a planted 45-minute near miss into a fake 60-minute slot (`calendar/results.json`,
  L3_s1 and L3_s2). Haiku also missed a whole block on L2_s1.
- **max_tokens 16000 is too low for Haiku on hard tasks.** Two L3 replies used all 16k on reasoning and stopped with
  `length`. The reported eval forbids that, so raise it (32000+) and rerun every task.
- **Fairness and realism fixes for the calendar:**
  - add quarter-hour ticks, or start and end times inside tall blocks, so a careful human can read 15-minute edges
  - avoid titles cut off in narrow columns
  - consider Outlook's Scheduling Assistant layout (rows = people, columns = time), which is the real tool for this question

## Round 2 (11:15 to 12:10, max_tokens 32000 then 64000) · hardest level, Haiku · Luna
| Family | Result | Verdict | Folder |
|---|---|---|---|
| Topo: contour lines a trail crosses (L3) | 0/3 · 0/3 at 32k and 64k | **Reliably hard** | `topo/` (`results_64k/`) |
| Topo: elevation of one point (L2) | 3/3 · 2/3 at 64k | Single reads not reliably hard | `topo/` |
| Topo missions (SAR sight, flood, base camp, hiker, wildfire) | see `missions/summary.md` | Mixed; 3 seeds per type is noise | `missions/` |
| **Power v2: dense crossings, long cross-sheet feeds** | 6/9 · 5/9 | **Hard**; Luna mis-traces crossings, invents backfeeds | `power_v2/` |
| Power (clean layout) | 9/9 · 9/9 | Too easy: clutter is the knob | `power/` |
| Calendar v2 (Outlook Scheduling Assistant, chained rules) | 9/9 · 8/9 | Out | `calendar_v2/` |
| Subway v2 (service change + times, accessible routes, worst closure) | svc 0/3 · 2/3, others 12/12 | Weak; the svc gap is a 2-minute trick | `subway_v2/`, WindHurtLZ's in `subway*/` |
| Gantt, ECG | 9/9 · 8/9, 12/12 · 12/12 | Out | `gantt/`, `ecg/` |

**Finding:** these models read labels, do arithmetic and follow rule chains on clean layouts. They break when they
must **trace a path through clutter**: counting contours along a winding trail, following a feeder across crossings,
telling a crossing from a junction. The same power family went from 9/9 (clean) to 5/9 (dense crossings).
**Decision (12:10): topo missions + power one-line, with crossing and contour density as the difficulty knob.**
