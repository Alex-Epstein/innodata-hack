# Presentation script: 5 minutes, the story of how we found it

Shape (from the team's own discussion): **what we tried → we got stuck → the idea → teach the map → the three questions
→ live demo → how we guarantee the answers → results → what we learned.** Judges love seeing the problem we hit.
Slides use the organizers' template (max 5). [N] = fill from `docs/EVIDENCE.md` after the 2:15 final run.

| Time | Screen | Speaker | Says |
|---|---|---|---|
| 0:00 | **Site intro** (`?intro=1`): flyover, "THE MAP / THE MOUNTAIN", lands on the flat map | A | "Two AI models looked at this map. A person answers it in about a minute. Both models got it wrong, nine times out of ten. Here's how we found that." |
| 0:20 | **Slide 1** (template intro): team, Visual Task Factory, one line | A | "We're [team]. We built a factory that generates map-reading tasks with provably correct answers, and uses them to find where vision models break." |
| 0:30 | **Slide 2: "How we got here"**: a grid of 8 thumbnails (circuit, ECG, Gantt, calendar, calendar v2, subway, power, topo), each with its score in mono | B | "We started where everyone starts: circuits, ECGs, Gantt charts, calendars, subway maps, power diagrams. We generated each one in code and tested both models. They aced almost all of it: 18 out of 18 on circuits, 9 out of 9 on Gantt charts. So we made the reasoning harder, chained rules, time zones, closures. Still aced. Honestly, we were stuck." |
| 1:05 | Slide 2: the pattern line highlighted | B | "Then we noticed the pattern: they read labels perfectly and do the math perfectly. What they couldn't do was **trace a path through clutter**. And there's a kind of image that is nothing but that: the topographic map." |
| 1:20 | Map with 3 callouts (site or slide image) | C | "Thirty-second lesson. Each brown line is one height; neighbours are 20 meters apart. Lines close together means steep. Walk a trail, and every line you cross is 20 meters up or down. Water always runs downhill at right angles to the lines. That's it. It looks complicated, and it isn't, for us." |
| 1:50 | Site: one card per mission | C | "So we wrote three missions on real terrain, Bear Mountain and Breakneck Ridge, real USGS elevation data. **Rescue carry:** count every line the trail crosses. **Lost hiker:** count only the uphill crossings, add four minutes each, and say if they beat sunset. **Flash flood:** the dam fails; which of six campsites does the water reach? Each one is a chain: trace, count, apply a rule, conclude." |
| 2:20 | **Slide 3: Live demo** → site, flood task | A | "Your turn. The dam at D just failed. Which campsite does the water reach? Ten seconds." *(wait)* |
| 2:35 | Site: 3D reveal | A | "Here's the mountain. The water goes here, C6. Claude Haiku said C1, the camp straight below the dam. Luna said C3. You beat both." |
| 2:55 | Terminal: a judge picks a number → `fresh --seed <n>` | D | "And it's a factory, not a slideshow. Pick any number." *(checks tick green)* "Brand-new map, seven checks passed, and here are both models' answers." *(cached fallback if the network is slow)* |
| 3:25 | **Slide 4: How we know it's right + results** | D | "Every map is drawn from the elevation data, and every answer is computed from that data, never by a model. Seven automatic checks, including a second independent solver and a pixel check of the picture, plus a reviewer agent and a human hand check. On our final ten tasks: Haiku [a]/10, Luna [b]/10. Across the 30 pilot tasks: 4 of 30 each. We timed ourselves: [human result]." |
| 4:05 | Slide 4: failure examples | D | "Where do they break? Not reading. Counting: on the crossings they lose count and come in low, 6 when it's 12. On the flood they stop tracing and pick the decoy right below the dam." |
| 4:25 | **Slide 5: What we learned** | A | "What we learned: these models read, but they don't trace. Limitation: ten reported tasks is a small sample, and our trails are drawn for the exercise. Next: any place on Earth with elevation data becomes a test, and each task is already an RL environment with a reward a model can't fake. Thank you." |
| 5:00 | End on the site's landing page with the QR | | |

**Roles (suggested):** A = Alex (opens, demo, close) · B = the journey (someone who ran spikes: WindHurtLZ or dl3832) ·
C = map lesson + missions (tech-cosmos, who built topo) · D = factory, live seed, results (whoever knows the pipeline best).
Each speaker owns about a minute. Rehearse twice with a timer; cut words, not beats.

**Prep before 3:10:** pre-warm `fresh` for 3 likely seeds (7, 42, 100) so the live call is cached; keep a fallback seed;
the site open in a tab at the featured flood task; slides exported as PDF; laptop on power; screen mirroring tested.
