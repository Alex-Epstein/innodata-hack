# Speaker script, per slide (same text as the deck's speaker notes)

Deck: `slides/TheMapVsTheMountain.pptx` (Presenter View shows these notes). Demo: https://alex-epstein.github.io/innodata-hack/
Q&A: `docs/QA.md`. Each speaker owns about a minute. Rehearse with a timer; cut words, not beats.

## Slide 1 · Intro (0:00-0:30)

0:00-0:30 · ALEX

[Before slide 1: the site intro is playing (alex-epstein.github.io/innodata-hack/?intro=1): flyover, THE MAP / THE MOUNTAIN, lands on the flat map.]

"Two AI models looked at this map. A person answers it in about a minute. On our final ten tasks, Claude Haiku got 2 right and GPT-6 Luna got 3."

[Slide 1] "We're Lost the Plot. We built a factory that generates map-reading tasks on real terrain, proves every answer in code, and finds exactly where vision models break."

## Slide 2 · How we generate a task (0:30-1:25)

0:30-1:25

WINDHURTLZ (0:30-0:55), the journey:

"We started where everyone starts: circuits, ECGs, Gantt charts, calendars, subway and power diagrams. We generated each in code and tested both models. They aced them: 18 of 18 on circuits, 9 of 9 on Gantt charts. We made the rules harder, time zones, closures, and they still aced them. We were stuck. Then we saw the pattern: they read labels and do math perfectly. They can't trace a path through clutter."

SHIVAM (0:55-1:25), the map lesson + how a task is made:

"Twenty-second lesson: each brown line is one height, 20 meters apart. Close lines mean steep. Every line a trail crosses is 20 meters up or down. Water runs downhill at right angles to the lines."

"Our code takes real USGS elevation data (Bear Mountain, Breakneck Ridge, Harriman, Mount Tamalpais), crops a window, places a trail or a dam and campsites from a seed, saves the data, draws the map, and computes the answer from the data. Three missions: count every line the rescue trail crosses; count only the uphill ones to see if a lost hiker beats sunset; follow a dam-break flood to the right campsite."

## Slide 3 · Live demo (1:25-2:30)

1:25-2:30 · LIVE DEMO

ALEX (1:25-2:00): open play.html on the featured flood (topo-flood-000102).

"Your turn. The dam at D just failed. Which campsite does the water reach? Ten seconds." [wait] [Reveal] "C1. Both models said C6, the camp closest to the dam. You beat both."

DL3832 (2:00-2:30): terminal. "It's a factory, not a slideshow. Pick any number." [run: uv run python -m factory fresh --seed <n> --family topo; pre-warmed seeds 7, 42, 100 are cached] "New map, seven checks passed, and here are both models' answers, in seconds."

FALLBACK if Wi-Fi dies: the report page from disk (report/index.html) and the screenshots.

## Slide 4 · What the runs showed + what a lab buys (2:30-4:00)

2:30-4:00

ALEX (2:30-3:00), why you'd train on this:

"That's the fun part. Here's why you'd pay for it. AI assistants get handed pictures of maps: a screenshot, a PDF incident map, a photo of a trailhead sign, an agent looking at a map app. In those cases they don't say 'I can't read this.' They're confidently wrong: 12 crossings became 6. The map is the test bed; the skill is tracing."

SHIVAM (3:00-3:30), what a lab buys (train.html is the backup visual):

"Two products. Eval sets, to measure and train spatial AI. And RL environments: every task ships with a verifier, a small program that reads the model's answer and returns a reward, 1 or 0. The model tries thousands of tasks, gets rewarded for right answers, and learns the skill. That's how labs teach reasoning now. Ours can't be gamed, because the reward comes from the elevation data, and our tasks sit exactly where models sometimes fail, which is where training teaches the most. We also ship worked, step-by-step solutions computed from the data."

WINDHURTLZ (3:30-3:50), why you can trust it:

"Every answer is computed from the data, never by a model. Seven automatic checks on every task: a second independent solver, a pixel check of the picture, legibility, and a byte-identical rebuild. All 10 final tasks passed, and you can rebuild them in Docker yourselves."

DL3832 (3:50-4:00), the numbers on this slide: "Haiku 2 of 10, Luna 3 of 10. And we tried the cheap fix, two worked examples in the prompt: 8 of 48 right without, 6 of 48 with. Prompting doesn't teach it."

## Slide 5 · What we learned (4:00-5:00)

4:00-5:00 · ALEX

"What we learned: these models read the map but don't trace it. Haiku undercounts crossings by about four, and both pick the decoy camp right below the dam."

"Limitation: ten reported tasks is a small sample, and our trails are drawn for the exercise. The terrain is real."

"Next: train on our RL environments and measure the gain on held-out regions, and point the same engine at any contour map: weather isobars, nautical charts. Any place with elevation data becomes a test. Thank you."

[End on the landing page with the QR code.]
