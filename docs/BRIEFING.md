# Briefing (the latest shared context; Alex's session keeps "Now" current)

## Now
**13:45 · FINAL STRETCH. Everyone: read `docs/OVERVIEW.md` and `docs/SCRIPT.md` until you can explain any part.**
Final 10 = all topo (crossings 3, sunset 3, flood 4), generated in Docker by the rule in DECISIONS. Demo = `site/` (live:
https://alex-epstein.github.io/innodata-hack/).
| Who | Job | Done by |
|---|---|---|
| WindHurtLZ | **Final set in Docker**: build image, generate per the rule, validate --drop-invalid, eval both models → `tasks/final`, `results/final`; then test the README's Docker commands on a clean clone | 2:20 |
| tech-cosmos | **README content** (all organizer headings: problem, pipeline, pilot results + generator changes, findings incl. power, hand check, reused components, manual steps, limitations, contributions) + `scripts/package` ZIP, checker 0 FAIL. Stop site-fable | 2:50 |
| dl3832 | **Human baseline** #55 on the final 10 (timed, image only) → hand-check notes for the README | 2:35 |
| Alex + agents | slides from the template, rebuild report + site on the final set, EVIDENCE.md, rehearsal | 3:00 |
| **Everyone** | learn your SCRIPT.md part; **two timed rehearsals at 2:50 and 3:00** | 3:10 |
**Upload by 3:10** (hard 3:30). Presentations at 3:30.

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
