# Briefing (the latest shared context; Alex's session keeps "Now" current)

## Now
**~11:05 · Spike round 2: every family gets the same test, then we pick the 2 with the best accuracy drop.**
Scoreboard so far (L1 / L2 / L3, Haiku · Luna):
| Family | L1 | L2 | L3 | Verdict |
|---|---|---|---|---|
| **Topo map** (#18) | 3/3 · 3/3 | 1/3 · 1/3 | **0/3 · 0/3** | **Leading.** Clean drop, failures are tracing and counting, answers double-computed, byte-identical rebuild |
| Calendar (32k rerun) | 2/3 · 3/3 | 3/3 · 3/3 | 0/3 (2 cut off) · **3/3** | Luna solves it with enough tokens; needs to be harder |
| ECG (#15) | 12/12 both | | | Ruled out: sharp marks on a grid are read to the pixel |
| Circuit | 9/9 both | | | Ruled out |
| Subway (#17) | running | | | WindHurtLZ |
| Gantt (#16) | ? | | | dl3832 |
| Power (#5) | ? | | | tech-cosmos Codex |
**Decision at 11:50:** topo + the best of subway / Gantt / power / a harder calendar.
**Eval issue:** Haiku still hits the token limit on hard tasks (all 32k spent reasoning). Both models allow up to 128k output, so go to 64000 (about $0.03 per call worst case).
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
