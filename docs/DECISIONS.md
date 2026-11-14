# Decisions

One line per decision: `- <time> · <who> · <decision> (why)`. Never re-argued; agents read this and stop
proposing alternatives.

- 09:45 · Team · **Track: Visual Task Factory** (prizes are overall and scored as %, so crowding doesn't matter; less infra risk than Harbor; realism and variation reward design).
- 09:45 · Alex · Repo created; formats frozen in `contracts/SCHEMA.md` (they follow the organizers' required formats).
- 11:45 · Alex · **Family 1 = topographic map** (L3 0/3 on both models, clean accuracy drop, answers double-computed). Family 2 by a 12:20 bake-off of chained calendar / subway / power. Gantt, ECG and circuit ruled out (too easy).
- 11:45 · Alex · Questions must chain 3 to 5 reads + rules into one exact answer (mentor advice, #29). max_tokens 64000.
- 11:55 · Alex · **Topo theme = missions with stakes:** wildfire escape, flash flood, search-and-rescue line of sight, hiker vs sunset. Each question is a scenario box on the map + a chained question. Demo draws the model's wrong path vs the true one.
- 12:10 · Alex · **Families: topo missions (main, ~6 of 10) + power one-line (~4 of 10).** Difficulty knob = clutter you must trace through (contours along a path, feeder crossings). Plug-in contract: `contracts/FAMILY.md`. Pilot 10 seeds per question type; keep only types that stay hard.
- 13:35 · Alex · The advisory reviewer (validate/review.py, PR #58) calls claude-sonnet-5-5 on the team Anthropic key directly, the one exception to 'all model calls through eval/'. It never decides answers; its flags feed the human hand check.
- 13:45 · Alex · **Final 10 = all topo** (power stayed 60 to 100% right after the wording fixes; reported in the README as a finding). The demo uses **site/** (Alex's 3D build); site-fable stops, and good ideas go to site/ as small PRs.
- 13:45 · Alex · **Final-10 rule (fixed before the final run):** topo 2.1.x, difficulty 3, generated **inside Docker**: crossings seeds 100-102, sunset 100-102, flood 100-103. Validate with --drop-invalid; if a seed is rejected, take the next seed of that mission in order. Then one eval run on both models. No reselection after seeing results.
