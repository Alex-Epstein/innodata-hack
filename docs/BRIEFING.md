# Briefing (the latest shared context; Alex's session keeps "Now" current)

## Now
**~11:05 · Spike round 2: every family gets the same test, then we pick the 2 with the best accuracy drop.**
**11:45 · Family 1 = TOPO MAP (locked), themed as MISSIONS** (wildfire escape, flash flood, SAR line of sight, hiker vs sunset; see DECISIONS). Family 2 = a 12:20 bake-off of chained versions (mentor's advice, #29).
| Family | Result so far (L3, Haiku · Luna) | Next | Owner |
|---|---|---|---|
| **Topo** | 0/3 · 0/3 at 32k | rerun at 64k to confirm; chained templates (#29) | tech-cosmos |
| Calendar | 2/3 · 3/3 at 64k (too easy) | v2 chained (#33) | **dl3832 owns** |
| Subway | 3/3 · 1/3 at 64k (weak) | v2 chained (#34) | **WindHurtLZ owns** |
| Power | running (#5) | L3 already chained (trip + tie close + kW unserved) | tech-cosmos |
| Gantt, ECG, circuit | ruled out (too easy) | | |
max_tokens is 64000 (both models allow 128k). Every run from now on uses it.
Meanwhile: #8 packaging (tech-cosmos), #6 core + #7 validator (Alex).

**Demo plan: "Beat the AI."** Judges solve our exemplar task on screen (60 s), then we reveal both models' wrong
answers. Then a judge picks a seed: we generate, check and score a fresh task live, and the judges race the models.
A static "Beat the AI" page (image, timer, reveal) can be served from GitHub Pages so judges play on their phones via a QR code.

**Budget (Alex's session tracks it; check with `scripts/budget`)**
| Pot | Cap | Spent | Notes |
|---|---|---|---|
| OpenRouter: spikes + pilots | $15 | $0.08 | about half a cent per call at high reasoning |
| OpenRouter: final eval (10 tasks x 2 models + reruns) | $5 | $0 | |
| OpenRouter: extras (blind runs, ablations) | $10 | $0 | |
| OpenRouter: **reserve, don't touch** | $70 | | for reruns before the deadline |
| Anthropic key | $100 | unknown | no usage API for this key; ask Amila. Coding agents on it: use Sonnet or Haiku, not Opus; no long unattended loops |

**Claim order** (take the first with no assignee; docs/SETUP.md step 6): #2 eval client → #8 packaging. (#5 tech-cosmos; #3, #4, #6, #7 Alex.)

**Deadline:** ZIP uploaded by 3:10 (hard 3:30). Next gate: **one calendar task end to end on main by 12:15.**

## Where things are
The file table in `AGENTS.md`.
