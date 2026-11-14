# Demo and pitch: 5 minutes, 5 slides (written before building, so we build exactly this)

**Format (organizers):** 5 minutes total, live demo required, at most 5 slides in their template
(`docs/organizer/presentation-template.pptx`): 1 intro 30 s · 2 how 30 s · **3 live demo 2.5 min** · 4 results 1 min ·
5 learned 30 s. Required: show one exemplar task that stumped the models (image, question, reference, each model's answer)
and the pipeline building, checking and scoring a fresh task.

**The feeling we want:** the judges beat the AI in the first 30 seconds, then watch us prove it wasn't luck.
**Every number on screen comes from `docs/EVIDENCE.md`.** Placeholders below are `[N]`.

## Run of show
| Time | Slide | On screen | Said (short, plain) |
|---|---|---|---|
| 0:00 | 1 | Full-screen flood map: dam at D, campsites C1 to C4, incident box | "Flash flood warning. The dam at D just failed. Which campsite floods first? You have ten seconds. Point at it." |
| 0:12 | 1 | Same map + the true water path in blue, each model's answer in red | "C3. Most of you got it. Claude Haiku said [C1]. GPT-6 Luna said [C4]. Both sure of themselves." |
| 0:22 | 1 | Title, team, one line | "We built a factory that makes unlimited maps like this, and proves every answer before a model sees it." |
| 0:30 | 2 | Pipeline: data → map → answer → 7 checks → both models → score | "Every map is drawn from an elevation model in code, so the answer is computed, not guessed. Seven automatic checks reject anything unfair. What changes between tasks is the reasoning: where water goes, what a spotter can see, which trail stays below a fire, whether a hiker beats sunset." |
| 1:00 | 3 | Terminal: a judge picks any number | "Pick a number." → `fresh --seed <their number>` |
| 1:10 | 3 | The new map appears, the checks tick green one by one | Narrate the checks in one breath: answer computed two ways, the picture matches the data, the answer is unique, the question needs the image, the image rebuilds identically |
| 1:40 | 3 | Both models answer live (started in the background at 1:10), scored | "Here's what they said." (If live calls are slow, show the cached run of the same seed.) |
| 2:10 | 3 | Report page: failure gallery, each failure tagged with the step that broke | "This is the interesting part: *where* they break. Haiku subtracts the two end heights and assumes the trail climbs steadily. It never traces the ridge." |
| 3:00 | 3 | QR code: "Beat the AI" on your phone | "You can play every task on your phone right now." |
| 3:30 | 4 | Accuracy ladder (L1 → L3, both models) + the validity funnel | "[N] of [M] generated tasks passed every check; we hand-checked the 10 we report. Haiku [a]/10, Luna [b]/10. Our first calendar tasks fell once the models got more thinking tokens, so we switched to chained missions, and accuracy dropped from [x] to [y]." |
| 4:30 | 5 | Finding · limitation · next | "Finding: they read the map fine, but don't *trace* it. Limitation: our terrain is synthetic and 10 tasks is a small sample. Next: real USGS elevation data, so every real place becomes a test. Each task is already an RL environment: verified reward, a difficulty dial, unlimited fresh seeds." |
| 5:00 | | End | |

## What we need to build for this (owners in issues)
1. **Mission maps + truth overlays** (topo generator): the water path, sight line or trail drawn in blue, and each model's answer marked in red.
2. **`fresh --seed N`** with readable, step-by-step terminal output (checks ticking), which starts the model calls in the background (core, #6).
3. **Report page** (static HTML): the exemplar, the failure gallery with the broken step, the ladder chart, the funnel. It doubles as the README's findings.
4. **"Beat the AI" phone page** on GitHub Pages: map, question, tap an answer, 60-second timer, then the reveal (truth overlay plus both models' answers). It shows "You vs Haiku vs Luna", with a QR code on slides 1 and 3. Static, no server.
5. **Slides**: the 5-slide template filled from EVIDENCE.md at ~2:30, plus a backup video or screenshots of the live part.

## Rehearsal rules
- One speaker, one driver at the laptop. Run it **twice with a timer** before 3:10.
- Pre-warm the cache for the 3 seeds most likely to be picked, and keep a fallback seed.
- Wi-Fi dies → the cached run plus screenshots. Nothing on stage depends on a live call succeeding.

## Q&A answers (have them ready)
- **How do you know the answers are right?** Computed from the elevation data two independent ways, the image checked against the data, ambiguous cases rejected (near-ties, grazing sight lines), and every final task hand-checked.
- **Isn't it synthetic?** The terrain is, but the map conventions are USGS's, and the generator takes any elevation grid. Real terrain is the next step.
- **Is it fair, or just hard to read?** A person solves each one in about [t] minutes (we timed ourselves), and you just did one in ten seconds.
- **Cost?** About [c] cents per task across both models; the whole day cost $[spent] of $100.
- **Scale?** It's procedural: a new seed is a new task, and the checks run automatically, so 10,000 tasks is just a longer run.
