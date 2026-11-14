# Speaker notes, per slide (same text as the deck notes)

## Slide 1

🎤 ALEX  ·  0:00 – 0:30  ·  The hook  
  
SHOW: the site intro playing first (alex-epstein.github.io/innodata-hack/?intro=1). It flies over Bear Mountain and lands on the flat map: "This is what the AI sees." Then this slide.  
  
SAY:  
• "Two AI models looked at this map. A person answers it in about a minute."  
• "On our final 10 tasks, Claude Haiku got 2 right and GPT-6 Luna got 3."  
• "We're Lost the Plot. We built a factory that makes map-reading tasks on real terrain, proves every answer in code, and finds exactly where vision models break."  
  
KEY NUMBERS: Haiku 2/10 · Luna 3/10 · 7 of 10 tasks stumped both models

## Slide 2

🎤 WINDHURTLZ  ·  0:30 – 0:55  ·  How we got here (right side of the slide)  
  
SAY:  
• "We started where everyone starts: circuits, ECGs, Gantt charts, calendars, subway and power diagrams."  
• "We generated each one in code and tested both models. They aced them: 18 of 18 on circuits, 9 of 9 on Gantt charts."  
• "We made the rules harder, time zones, closures, and they still aced them. Honestly, we were stuck."  
• "Then we saw the pattern: they read labels and do math perfectly. What they can't do is TRACE a path through clutter."  
  
🎤 SHIVAM  ·  0:55 – 1:25  ·  The map lesson + how a task is made (left side)  
  
SAY (map lesson, 20 seconds):  
• "Each brown line joins points of the same height; neighbours are 20 meters apart."  
• "Lines close together mean steep. Every line a trail crosses is 20 meters up or down."  
• "Water runs downhill at right angles to the lines."  
  
SAY (the factory):  
• "We take real USGS elevation data (Bear Mountain, Breakneck Ridge, Harriman, Mount Tamalpais), crop a window, and place a trail, a dam and campsites from a seed."  
• "We save that data first, draw the map from it, and compute the answer from the data, never from the picture. Then 7 automatic checks."  
• Three missions: CROSSINGS: count every line the rescue trail crosses · SUNSET: count only uphill crossings, add 4 minutes each, does the hiker beat sunset? · FLOOD: the dam fails; which of 6 campsites does the water reach?

## Slide 3

🎤 ALEX  ·  1:25 – 2:00  ·  Beat the AI  
  
DO: open play.html → the featured flood map (topo-flood-000102, Harriman).  
SAY:  
• "Your turn. The dam at D just failed. Which campsite does the water reach? Ten seconds."  
• [wait, then reveal: the map lifts into 3D, the blue water runs to C1]  
• "C1. Both models said C6, the camp closest to the dam. You beat both."  
  
🎤 DL3832  ·  2:00 – 2:30  ·  The live factory  
  
DO: terminal on the set-up laptop → uv run python -m factory fresh --seed <their number> --family topo  
SAY:  
• "It's a factory, not a slideshow. Pick any number."  
• [map renders, 7 checks tick green, both answers appear] "A brand-new map, verified and scored in seconds."  
  
TIPS: seeds 7, 42 and 100 are pre-warmed (instant). If Wi-Fi dies: open report/index.html from disk and use screenshots.

## Slide 4

🎤 ALEX  ·  2:30 – 3:00  ·  Why an AI lab would pay for this  
  
SAY:  
• "That's the fun part. Here's why you'd buy it."  
• "AI is constantly handed PICTURES of maps: a screenshot, a PDF incident map, a photo of a trailhead sign, an agent looking at a map app."  
• "It never says 'I can't read this.' It's confidently wrong: 12 crossings became 6."  
• "The map is our test bed. The skill is tracing, and it matters for drawings, schematics and robot path planning too."  
  
🎤 SHIVAM  ·  3:00 – 3:30  ·  What a lab buys (backup visual: train.html)  
  
SAY:  
• "Two products. EVAL SETS, to measure and train spatial AI."  
• "And RL ENVIRONMENTS: every task ships with a verifier, a small program that reads the model's answer and returns a reward, 1 if right, 0 if wrong."  
• "The model tries thousands of tasks, gets rewarded for right answers, and learns the skill. That's how labs teach reasoning now."  
• "Ours can't be gamed: the reward comes from the elevation data. And our tasks sit where models sometimes fail, which is where training teaches the most."  
• "We also ship step-by-step solutions computed from the data, for fine-tuning."  
  
🎤 WINDHURTLZ  ·  3:30 – 3:50  ·  Why you can trust it  
  
SAY:  
• "Every answer is computed from the data, never by a model."  
• "Seven checks on every task: a second independent solver, a pixel check that the picture matches the data, legibility, and a byte-identical rebuild."  
• "All 10 final tasks passed, and you can rebuild them yourselves in Docker."  
  
🎤 DL3832  ·  3:50 – 4:00  ·  The numbers on this slide  
  
SAY:  
• "Haiku 2 of 10, Luna 3 of 10."  
• "And we tried the cheap fix, two worked examples in the prompt: 8 of 48 right without them, 6 of 48 with them. Prompting doesn't teach it. It needs training data."

## Slide 5

🎤 ALEX  ·  4:00 – 5:00  ·  What we learned + close  
  
SAY:  
• FINDING: "These models read the map but don't trace it. Haiku undercounts crossings by about four, and both pick the decoy camp right below the dam."  
• LIMITATION: "Ten reported tasks is a small sample, and our trails are drawn for the exercise. The terrain is real."  
• NEXT: "Train on our RL environments and measure the gain on held-out regions. Point the same engine at any contour map: weather isobars, nautical charts."  
• "Any place with elevation data becomes a test. Thank you."  
  
DO: end on the landing page with the QR code so judges can play.  
  
IF ASKED "why not just use Google Maps?": "When the data exists, use the tool. Our customers are the cases where the AI only gets a picture, and it doesn't know it's wrong." (More answers in docs/QA.md.)
