# Presentation script v2: 5 minutes = the fun half + the sale half

Judges' feedback (13:50): *"Treat us as an AI company and you as a data vendor. Sell it. Make us believe we need to train
our AI on this, because people will use it for exactly that purpose."* They loved the demo. So: keep the demo as the
hook, then sell. Every line maps to a rubric criterion (in brackets). [N] = fill from `docs/EVIDENCE.md` after the final run.

## Half 1: the fun (0:00 to 2:30), what makes them lean in
| Time | Screen | Who | Says |
|---|---|---|---|
| 0:00 | Site `?intro=1`: flyover → "THE MAP / THE MOUNTAIN" → lands on the flat map | A | "Two AI models looked at this map. A person answers it in about a minute. Both models got it wrong almost every time." |
| 0:15 | **Slide 2 "How we got here"**: 8 thumbnails with scores | B | "We built generators for the visuals AI gets asked about at work: circuits, ECGs, Gantt charts, calendars, subway and power diagrams. Both models aced them, even with harder rules. We were stuck, until we saw the pattern: **they read labels and do math perfectly; they can't trace a path through clutter.**" [variation, difficulty] |
| 0:45 | Map with 3 callouts | C | "Twenty-second lesson: each brown line is one height, 20 meters apart; close lines are steep; every line a trail crosses is 20 meters up or down; water runs downhill at right angles to the lines." |
| 1:05 | Site: the three mission cards | C | "So we made three missions on real terrain, from USGS elevation data: count the lines a rescue trail crosses; work out whether a lost hiker beats sunset; find which campsite a dam break floods. Each one is a chain: trace, count, apply a rule, conclude." [realistic visuals, variation] |
| 1:25 | **Slide 3 Live demo** → site, flood task | A | "Your turn. The dam at D failed. Which campsite does the water reach? Ten seconds." → 3D reveal: "C6. Haiku said C1, the camp straight below the dam. Luna said C3. You beat both." |
| 2:00 | Terminal: judge picks a number → `fresh --seed <n>` | D | "It's a factory. Pick any number." *(map renders, 7 checks tick green, both answers)* "New task, verified, scored, in seconds." [reliable pipeline] |

## Half 2: the sale (2:30 to 5:00), why an AI lab buys this
| Time | Screen | Who | Says |
|---|---|---|---|
| 2:30 | **Slide 4 "Why you'd train on this"**: the use-case strip (from `product/USE_CASES.md`) | A | "That's the fun part. Here's why you'd pay for it. AI assistants are being asked to reason over maps: a hiking assistant asked 'will I make it before dark', a flood or wildfire planning copilot, a drone planning a route over a ridge, an earth-science tutor. Every one needs the skill these models don't have: tracing across contours. Our sunset mission *is* the hiking question; our flood mission *is* the flood-path question." [realistic, useful] |
| 3:05 | Slide 4: "What you get" (3 boxes) | D | "We deliver it three ways: **an eval set** that measures the gap; **RL environments**, each with a verifier that returns the reward; and **worked, step-by-step solutions** for fine-tuning, with every step computed from the data. Any region with US elevation data, any difficulty, any count, on demand." [reliable pipeline, model evaluation] |
| 3:35 | Slide 4: "Why you can trust it" | B | "Every answer is computed from the elevation data, never by a model. Seven automatic checks on every task: a second independent solver, a pixel check of the picture, a reproducible rebuild, plus a reviewer agent and a human hand check. Judges can rebuild our ten tasks in Docker byte for byte." [fair and verifiable, runnable] |
| 4:00 | **Slide 5 "Results"**: final scores, human baseline, few-shot result | D | "On our final ten: Haiku [a]/10, Luna [b]/10. A person: [h]. Where they break: they lose count along the trail and pick the decoy below the dam. [Few-shot line from `results/extra/fewshot/summary.md`, e.g. 'Two of our worked examples took Haiku from x to y', or 'Examples in the prompt don't fix it; this needs training data at scale']." [difficulty, model evaluation] |
| 4:30 | Slide 5: "What's next" | A | "The engine isn't about hiking. Any contour or field map works the same way: weather isobars, nautical depth charts, heat maps. It's one factory for the skill models lack, tracing, and it costs about half a cent a task to evaluate. We'd love to build it with you." |
| 5:00 | End on the landing page with the QR | | |

## Rubric checklist (say each out loud at least once)
| Criterion | Weight | Where we hit it |
|---|---|---|
| Realistic, useful visuals | 20% | Real USGS terrain + USGS map style (1:05), real use cases (2:30) |
| Reliable generation pipeline | 20% | Live fresh seed (2:00), any region on demand (3:05) |
| Fair, verifiable tasks | 15% | 7 checks + reviewer + human (3:35), humans solve it (4:00) |
| Task difficulty | 15% | Final scores (4:00), "aced everything else" (0:15) |
| Meaningful variation | 10% | 3 missions with different reasoning chains (1:05) |
| Model evaluation | 10% | Both models, where they break (4:00) |
| Runnable submission | 10% | Docker rebuild byte for byte (3:35) |

**Roles:** A = Alex · B = WindHurtLZ or dl3832 · C = tech-cosmos (built topo) · D = whoever knows the pipeline best.
Rehearse twice with a timer (2:50 and 3:00). Pre-warm `fresh` for seeds 7, 42, 100; keep a fallback tab with a cached run.
