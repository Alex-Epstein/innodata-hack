# How we got here (Alex's planning session, 7:30 to 10:30 AM)

So everyone (and every agent) knows what was already considered and why.

1. **Before the packet (7:30):** a handoff brief (`HANDOFF.md`) from Alex's other hackathon session. Core
   pattern from Cal Hacks (Red Ledger, 2nd place): generator with known answers → model under test →
   independent verifier → scoreboard + failure gallery. Judges trust measured curves over claims.
2. **First plan and idea bank (`PLAN.md`, `IDEAS.md`):** 40 visual capabilities, 17 coding task types, rigor
   checks, demo ideas (judges take an "eye exam" next to the models), pitch hooks.
3. **The packet arrived (~9:30).** Key facts (`../BRIEF.md`): ZIP due 3:30 PM; prizes are top 3 overall with each
   track's score converted to %; Visual rubric weights Realism 20 / Reliable pipeline 20 / Fair 15 / Difficulty 15 /
   Variation 10 / Eval 10 / Runnable 10; tie-break is validity; models fixed (Haiku 5.5, GPT-6 Luna);
   temperature 0, reasoning high, no truncation.
4. **Track decision: Visual.** Because prizes are overall, track crowding doesn't matter. Coding needs Harbor +
   agent rollouts (high infra risk in 4.5 h) and is mostly scored by scripts. Visual rewards realism and
   variation, which design and CV skills move. (`GAMEPLAN.md`)
5. **First concept: "Ops Desk"** (calendar + Gantt + power one-line). Alex asked not to lock the first idea, so we
   did structured ideation: rubric-based criteria, 21 scored ideas, 5 ways to package them, and a 15-minute spike
   test to pick by evidence. (`../IDEATION.md`)
6. **Repo + process** set up the HackPrinceton way (`OPERATIONS.md`): AGENTS.md as the shared brain, contracts
   frozen from the required formats, live log issue #1, status files, decisions file, director loop.
7. **Architecture proposed** (`../ARCHITECTURE.md`): Python + uv + matplotlib, one plugin interface per image
   family, proven byte-identical rebuilds, a 7-check validator, one cached OpenRouter client, one CLI used by both
   Docker and the live demo.

## Ideas we're carrying forward into the spike test
See `../IDEATION.md` section 2 and `../BRIEFING.md` ("Now").

## Demo ideas already agreed in spirit
- Judges answer the exemplar task first, then we reveal both models' answers (the eye exam, cut to fit 5 min).
- A judge picks the seed; we generate, check and score a fresh task live.
- RL-environment framing: tasks the model sometimes fails are the ones that teach it; our factory makes them on demand.
