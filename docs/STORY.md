# The full story of the day: decisions, challenges, fixes, and where we ended

## 1. The decision chain
**Track.** Read the packet: prizes are top 3 *overall*, and each track's score is converted to a percentage
→ track crowding doesn't matter, only how close we get to 100%
→ Coding needs Harbor + agent rollouts (high infra risk in 4.5 h) and is mostly scored by scripts; Visual rewards realism and variation
→ **Visual track** (09:45).

**Finding the idea.** First instinct "Ops Desk" (calendar + Gantt + power)
→ Alex: don't lock the first idea → structured ideation: rubric-based criteria, 21 scored ideas (`docs/IDEATION.md`)
→ decide by evidence, not debate: **spike test** (3 levels × 3 seeds × both models, under a dollar)
→ round 1: **circuit 18/18 (out)**, calendar dropped to 1/3 on the hard level (promising)
→ round 2, everyone on the same protocol: **ECG 12/12, Gantt 9/9 and 8/9 (out)**, subway weak, **topo trail crossings 0/3 on both models**
→ Haiku hit the token limit (`length`), so 16k → 32k → **64k max_tokens**; at 32k Luna then solved the calendar 9/9 → calendar was hard only because the models ran out of room to think
→ mentor: "make small models do the most complex reasoning possible" → **chained questions** (read several facts → apply a rule → conclude)
→ chained v2 spikes: calendar v2 9/9 and 8/9, subway v2 mostly solved, power v2 6/9 and 5/9, topo missions mixed
→ **the pattern: these models read labels and do math; they can't trace a path through clutter** (same power diagram: 9/9 clean, worse with crossings)
→ **families: topo missions + power** (12:10).

**Making topo great.** "This is boring" → **missions with stakes** (flash flood, lost hiker vs sunset, rescue carry)
→ "what sets us apart?" → **real terrain**: real USGS 3DEP elevation for Bear Mountain, Breakneck Ridge, Harriman, Mt Tamalpais, stored in the repo, rendered offline byte-identical → Haiku 0/10, Luna 3/10 on real-terrain crossings
→ gen/topo moved to real terrain; wildfire and yes/no line-of-sight dropped (too guessable)
→ 10-seed pilots: **crossings 1/10 · 0/10, sunset 0/10 · 1/10, flood 3/10 · 3/10 → 4/30 each**.

**Final set.** Power after wording fixes: 60 to 100% right → fails our keep rule
→ **final 10 = all topo** (13:45), with power reported as a finding
→ the final-10 rule written down *before* the run (crossings seeds 100-102, sunset 100-102, flood 100-103)
→ PNG bytes differ between Windows and Mac (same pixels) → **generate inside Docker**, the judges' environment
→ **final: Haiku 2/10, Luna 3/10**; 10/10 pass all 7 checks, 0 seeds rejected, 20/20 replies complete, 10/10 rebuild byte-identical.

**Selling it.** Judges: "treat us as an AI company; sell it like a data vendor; why would we train on this? don't people just use Google Maps?"
→ pitch in two halves: **the fun** (3D demo) + **the sale** (who needs it, what you get, why trust it)
→ built the product: `factory export --format rl` = **RL environments with a verifier + step-by-step SFT solutions + datasheet + use cases**
→ tested the cheap fix: two worked examples in the prompt → **8/48 → 6/48**: prompting doesn't teach tracing; it needs training data at scale.

## 2. How we built it (the architecture decisions)
Repo as the team's shared brain (`AGENTS.md`, briefing, decisions, live log, directives)
→ contracts first (`contracts/SCHEMA.md` from the organizers' formats, `contracts/FAMILY.md` plug-in interface)
→ one cached eval client (temperature 0, reasoning high, 64k tokens; every raw reply logged)
→ factory core + **7-check validator** (schema, data first, two solvers, picture matches data, legibility, answer not in question, byte-identical rebuild)
→ **reviewer agent** (Sonnet, advisory) + human hand check
→ report page (failure gallery tagged with the broken step) → **"The Map vs the Mountain" 3D site** on GitHub Pages in the "Field Survey" art direction
→ Docker image whose `rebuild` reproduces the 10 tasks exactly.

## 3. Challenges and how we fixed them
| Challenge | Fix |
|---|---|
| The models aced almost everything (circuits 18/18, Gantt 9/9) | Stopped guessing: the same quick test on ten families, then looked for the pattern (they can't trace) |
| Calendar looked hard, then wasn't | Tested with final settings: at 64k tokens Luna solved it. Lesson: pilot with the real settings |
| Haiku replies cut off at 16k and 32k tokens (not allowed in the final eval) | Raised max_tokens to 64k (both models allow 128k); every final reply finished normally |
| 3 seeds per type was noise (the same map went 2/6 to 6/6 with new wording) | 10-seed pilots per question type, and a keep rule: at most 5/10 right for at least one model |
| Power looked hard only because of confusing wording; subway because of misleading labels | Made the questions fair and reran: both became easy, so they're out. Difficulty must come from reasoning |
| Yes/no and 4-option missions were guessable | Answers became counts and 6-option choices with planted decoys |
| Reviewer agent flagged the red trail over brown contours and endpoints on contour lines | v2.1: solid magenta trail with a white casing, endpoints kept off every contour, wording says so |
| Real terrain broke the original "grazing" rule (no real trail could pass it) | Replaced it with fair, checkable rules (crossing angle, distance from endpoints, flat stretches) |
| Images differ in their last bytes across Windows and Mac | The final set is generated inside Docker, the same environment the judges use |
| API keys: asked to commit them to the public repo | Kept them in a gitignored .env and shared them in Discord; GitHub would have revoked keys found in a public repo |
| Budget worry | Budget caps + `scripts/budget` + caching; whole day about $2.3 of $100 |
| Several agents switching branches in one checkout | Every agent in its own git worktree |
| Teammates felt like "subagents" | Owners of whole pieces (a family, the final set, the README/ZIP, the human baseline) instead of tickets |
| Duplicate demo builds (two Beat-the-AI pages, a Fable 3D version) | Picked one (`site/`), others contribute small PRs |
| "This is boring" | Missions with stakes, real places, and the 3D reveal |
| "Why would anyone use a picture instead of Google Maps?" | When the AI only has pixels (screenshots, PDFs, photos, computer-use agents), it's confidently wrong; the map is the testbed, tracing is the skill (`docs/QA.md`) |
| The final set wasn't started at 14:27 | Alex's agent took it over: generated, validated, evaluated and rebuilt in Docker by 14:36 |
| A claim we couldn't back ("procedural terrain mode") | Corrected everywhere: real terrain only in the current generator |
| Few-shot examples didn't help | Reported honestly, and it became a sales point: the skill needs training data at scale |

## 4. Where we ended
- **The factory:** real-terrain topo missions (crossings, sunset, flood), every task verified by 7 checks + a reviewer agent; one command for a fresh task; Docker rebuild byte-identical.
- **The results:** final 10, **Haiku 2/10, Luna 3/10**; 7 of the 10 stumped both models; pilots 4/30 each; ten families tested along the way.
- **The finding:** they read the map but don't trace it (Haiku undercounts crossings by about 4; both pick the decoy camp below the dam; both overestimate the hiker's spare time by about 12 minutes).
- **The product:** eval set, RL environments with a verifier, step-by-step SFT data, datasheet, use cases (`product/`).
- **The demo:** "The Map vs the Mountain" at https://alex-epstein.github.io/innodata-hack/ (press S); report page; 5 slides; a two-half script; Q&A prep.
- **Cost:** about $2.3 of the $100 OpenRouter budget for the whole day.
- **Open at 14:50:** human hand check of the final 10, the ZIP with 0 FAIL, two rehearsals, upload by 3:10.
