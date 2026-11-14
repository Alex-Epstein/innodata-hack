# Q&A prep: know it inside out (every speaker reads all of this)

Numbers below are from the **pilots** (generator topo 2.0, 10 tasks per mission, the hardest level). Swap in the final-10
numbers from `docs/EVIDENCE.md` once the final run lands. Never round, never guess.

## The hardest question first: "Why would anyone use a picture? Don't they just use Google Maps or GIS?"
**Short answer:** when the data is there, use the tool. Our customers are the cases where the AI only gets the picture,
and the AI doesn't know it's wrong.
1. **The AI often only has pixels.** A user uploads a screenshot or a photo of a trailhead map ("will I make it before
   dark?"). An incident map arrives as a PDF. A field crew photographs a paper quad. A **computer-use agent** looking at
   a map app sees a rendered image, not the database behind it. Innodata sells computer-use and physical-AI data for
   exactly this reason.
2. **Confident and wrong is the danger.** The models didn't say "I can't read this map." They gave a precise number:
   12 crossings became 6 and 14 minutes to spare became 46. The brief itself says a confident wrong answer is worse than no answer.
   Training on our data is how a model learns either to do it right or to know when to call the tool.
3. **Maps are the testbed; tracing is the skill.** The weakness we found, following a path through clutter, also shows
   up in engineering drawings, schematics with crossing wires (our power-diagram tests got worse with crossings), floor
   plans, weather maps and robot path planning from maps. Topographic maps are the cleanest place to measure and train
   it, because the answer can be computed exactly.
4. **Tools need inputs.** Even an agent that calls a GIS tool has to read the map to know which trail, which dam,
   which campsite. That's the step that fails.

## Luna vs Haiku (they asked)
| Mission | Haiku 5.5 | Luna | How they're different |
|---|---|---|---|
| Crossings | 1/10 | 0/10 | **Haiku undercounts systematically** (average 4 lines short: said 6 for 12). **Luna scatters around the truth** (average error about 0, but off by 1 to 4 each time), like an estimate rather than a count |
| Sunset | 0/10 | 1/10 | **Both overestimate the spare time by about 12 minutes on average**: they miss uphill crossings, so they think the climb is shorter |
| Flood | 3/10 | 3/10 | Both stop tracing early and pick a decoy, most often the camp straight below the dam |
| **All pilots** | **4/30** | **4/30** | A tie. Same weakness, different style |
- **Style:** Haiku shows its work (median reply about 900 to 1,300 characters); Luna mostly answers in a sentence or two
  (about 120 to 230 characters), with its reasoning hidden. So Haiku's failures are easier to diagnose step by step.
- **Earlier spikes:** on the first real-terrain test, Haiku went 0/10 and Luna 3/10 (Luna's answers bunched around 10,
  so some hits may be luck). On simpler task families (calendars, subway), Luna was usually a bit weaker and Haiku a bit
  stronger; neither is better at tracing.
- **Settings:** both at temperature 0, reasoning effort high, 64,000 max tokens; every reply finished normally (no cut-offs).

## Questions judges will likely ask
| Question | Answer |
|---|---|
| How do you know the reference answer is right? | It's computed from the elevation data, never read off the picture. A second, independent method recomputes it and must agree. The picture is checked against the data at the pixel level. Then a reviewer agent and a person check each task. |
| Is it fair, or just hard to see? | A person solves it in about [human baseline] minutes. Every label has a minimum size. The trail is solid magenta with a white casing, so each crossing is visible. The start and end squares are kept off contour lines. The question states every rule (Naismith's 4 minutes per uphill line, steepest descent). |
| What are the 7 checks? | schema · data first · two solvers agree · picture matches data (pixel probes) · legibility · answer not in question · byte-identical rebuild. |
| Can judges reproduce it? | Yes. `docker build`, then one command rebuilds the 10 reported tasks from their seeds (identical images, questions, answers) and scores both models; a second builds a fresh task. The final set was generated inside Docker so the rebuild matches byte for byte. |
| Why only topo maps? Isn't that narrow? | We tested ten families; the models solved the others. Narrowing to what reliably breaks them is the finding. Inside topo there are three different reasoning chains (count, count-only-uphill plus time math, follow steepest descent). The engine generalizes to any contour or field map. |
| Isn't real terrain just one map reused? | Four real areas (Bear Mountain, Breakneck Ridge, Harriman NY; Mt Tamalpais CA), and every seed picks a different window, trail, dam and campsites. |
| Did you pick the tasks the models failed? | No. The final 10 follow a rule written before the final run (fixed seeds per mission, next seed only if a task fails a check). We report every result. |
| How hard is it to make harder or easier? | Difficulty is a dial: longer trails and more contour crossings, more campsites and decoys, tighter time margins. |
| Would training on this actually help? | We tested the cheap fix first: two of our worked examples in the prompt. It didn't help: 8/48 right without examples, 6/48 with them (`results/extra/fewshot/summary.md`). Luna copied the example answers (its crossings answers bunched at 10 or 11); Haiku copied the solution layout, then still "estimated" ("I estimate about 9", truth 13). So the skill isn't fixable by prompting. It needs training data at scale with a checker, which is exactly what we ship: RL environments with a verifier and step-by-step solutions (`product/`). Honest limit: 8 tasks per cell, so it rules out a big effect, not a small one. |
| What does it cost? | Generating tasks makes no API calls. Evaluating one task on both models is about half a cent. The whole day, every experiment included, cost about $2 of the $100. |
| What would a lab buy? | An eval set, RL environments (prompt + image + verifier), and step-by-step SFT data, for any region, mission, difficulty and count. See `product/DATASHEET.md`. |
| Why not use an LLM to generate the maps? | Then nobody could prove the answer. Everything is drawn from data so the answer is exact (the organizers require it too). |

## Shortcomings (say them before they're asked)
- **Small final sample:** 10 reported tasks (plus 30 pilot tasks). Enough to show the gap, not to give tight error bars.
- **Trails are drawn for the exercise,** not real trails. The terrain is real.
- **Real terrain only in the current generator.** A procedural mode existed in an early spike, not today.
- **Limited regions:** 4 areas are bundled (so Docker runs offline). More regions need more tiles downloaded.
- **Some wrong answers can't be explained:** Luna often gives only the final line, so we can't see which step broke.
- **Power diagrams and the other families were too easy,** so the final set is one image type with three reasoning chains.
- **The reviewer agent sometimes flags things our geometry checks already handle;** a person resolves those.

## How we'd improve it (next steps)
- More regions and missions: line of sight for spotters, wildfire escape routes, multi-leg routes.
- Other contour or field maps from the same engine: weather isobars (wind), nautical depth charts (safe passage), heat maps.
- A difficulty curve per model (find the exact number of crossings where each one breaks).
- Train on it: fine-tune with the step-by-step data and measure the gain on held-out regions.
- Ask the model to say "I'm not sure" (calibration), and reward it for knowing when to call a tool.

## Where we got stuck (and what got us unstuck)
1. Every family we tried first was too easy (circuits 18/18, Gantt 9/9). **Unstuck:** we stopped guessing and ran the same quick test on ten families, then looked for the pattern.
2. Calendar looked hard (1/3) until the models got more thinking tokens (16k → 64k), then Luna got 9/9. **Lesson:** test with the final settings early.
3. Power diagrams were hard only because of confusing wording; once we made the questions fair, the models solved them. **Lesson:** difficulty has to come from the reasoning, not the wording.
4. The reviewer agent caught a real readability issue (a red trail over brown contours) that we fixed in v2.1.
5. Images rendered on Windows and Mac differ in the last bytes, so we generate the final set inside Docker.

## Know your part (check yourself)
Everyone should be able to answer, without notes: what the factory does (one sentence) · how to read a contour map ·
the three missions and their answers · the 7 checks · how the Docker rebuild works · the Luna vs Haiku table · the
"why a picture" answer · one shortcoming and one next step.
