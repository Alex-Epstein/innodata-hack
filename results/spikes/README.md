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
