# Briefing (the latest shared context; Alex's session keeps "Now" current)

## Now
**12:15 · BUILD PHASE. Families decided: topo missions + power one-line** (`results/spikes/README.md` has the evidence).
The difficulty is tracing a path through clutter: these models read labels and do math fine, but miscount contours along a
trail and mis-trace feeders across crossings.
| Owner | Issue | Done by |
|---|---|---|
| tech-cosmos | #46 topo family → `gen/topo`, 10-seed pilot per mission | 1:30 |
| WindHurtLZ | #47 power family → `gen/power`, wording + variety fixes, 10-seed pilot | 1:30 |
| dl3832 | #40 Beat the AI phone page (GitHub Pages + QR) | 2:30 |
| Alex | #6 core CLI + #7 validator (plug-in contract: `contracts/FAMILY.md`), #41 report page | core 1:00 |
| tech-cosmos | #8 packaging, then the final eval (you own eval runs) | 2:45 |
**Next gates:** 1:00 core + validator on main · 1:30 both families pass `validate`, pilots posted · **1:45 generator frozen, final-10 rule written** · 2:15 final eval + Docker rebuild · 2:45 ZIP passes checker · 3:10 uploaded.

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
