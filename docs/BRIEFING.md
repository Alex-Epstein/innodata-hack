# Briefing (the latest shared context; Alex's session keeps "Now" current)

## Now
**~11:05 · Spike round 2: every family gets the same test, then we pick the 2 with the best accuracy drop.**
Done: calendar (L3 Haiku 1/3, Luna 1/3) · circuit ruled out (18/18). Running now, results on each issue by **11:45**:
| Family | Issue | Owner |
|---|---|---|
| Power one-line (harder) | #5 | tech-cosmos (Codex) |
| ECG rhythm strip | #15 | tech-cosmos |
| Gantt chart | #16 | dl3832 |
| Subway map | #17 | WindHurtLZ |
| Topographic map | #18 | tech-cosmos |
Same protocol everywhere (in each issue): 3 levels x 3 seeds, `eval.run`, a results table, honest fairness and realism notes.
**Decision at 11:50:** the family pair with the clearest accuracy drop that stays fair and looks real. Calendar is the one to beat.
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
