"""Speaker notes as bullets (who says what), written into the deck. Run only when the deck is CLOSED in PowerPoint."""
from pathlib import Path
from pptx import Presentation

DECK = Path(__file__).resolve().parents[2] / "slides/TheMapVsTheMountain.pptx"

NOTES = [
["ALEX · 0:00-0:30",
 "• Before slide 1: site intro playing (alex-epstein.github.io/innodata-hack/?intro=1), lands on the flat map",
 "• \"Two AI models looked at this map. A person answers it in about a minute.\"",
 "• \"On our final 10 tasks: Claude Haiku got 2 right, GPT-6 Luna got 3.\"",
 "• \"We're Lost the Plot: a factory that makes map-reading tasks on real terrain, proves every answer in code, and finds where vision models break.\""],
["WINDHURTLZ · 0:30-0:55 · the journey",
 "• Tried circuits, ECGs, Gantt charts, calendars, subway and power diagrams",
 "• Both models aced them: circuits 18/18, Gantt 9/9",
 "• Made the rules harder (time zones, closures): still aced. We were stuck",
 "• The pattern: they read labels and do math perfectly; they can't TRACE a path through clutter",
 "SHIVAM · 0:55-1:25 · map lesson + how a task is made",
 "• Each brown line = one height, 20 m apart · close lines = steep · each line crossed = 20 m up or down · water runs downhill at right angles",
 "• Real USGS elevation (Bear Mountain, Breakneck Ridge, Harriman, Mt Tamalpais) → crop → place trail / dam / camps from a seed → save data → draw map → compute answer → 7 checks",
 "• 3 missions: crossings (count every line) · sunset (count only uphill, +4 min each, vs daylight) · flood (follow steepest descent to 1 of 6 camps)"],
["ALEX · 1:25-2:00 · Beat the AI",
 "• Open play.html on topo-flood-000102",
 "• \"The dam at D just failed. Which campsite does the water reach? Ten seconds.\"",
 "• Reveal: \"C1. Both models said C6, the camp closest to the dam. You beat both.\"",
 "DL3832 · 2:00-2:30 · live factory",
 "• \"It's a factory, not a slideshow. Pick any number.\"",
 "• Run: uv run python -m factory fresh --seed <n> --family topo (seeds 7, 42, 100 pre-warmed)",
 "• \"New map, 7 checks passed, both models' answers, in seconds.\"",
 "• Wi-Fi fallback: report/index.html from disk + screenshots"],
["ALEX · 2:30-3:00 · why you'd train on this",
 "• AI gets handed PICTURES of maps: screenshots, PDF incident maps, trailhead photos, agents looking at a map app",
 "• It's confidently wrong, never \"I can't read this\": 12 crossings became 6",
 "• The map is the test bed; the skill is tracing",
 "SHIVAM · 3:00-3:30 · what a lab buys (train.html = backup visual)",
 "• Eval sets: measure and train spatial AI",
 "• RL environments: each task + a verifier that returns a reward, 1 or 0; the model tries thousands, learns from the reward",
 "• Can't be gamed: the reward comes from the elevation data; tasks sit where models sometimes fail = where training teaches most",
 "• Plus step-by-step solutions computed from the data (SFT)",
 "WINDHURTLZ · 3:30-3:50 · why you can trust it",
 "• Answers computed from data, never by a model",
 "• 7 checks per task: second solver, pixel check, legibility, byte-identical rebuild; all 10 passed; rebuild it yourself in Docker",
 "DL3832 · 3:50-4:00 · the numbers",
 "• Haiku 2/10 · Luna 3/10",
 "• Cheap fix tested: 2 worked examples in the prompt → 8/48 vs 6/48. Prompting doesn't teach it"],
["ALEX · 4:00-5:00 · close",
 "• Finding: they read the map but don't trace it. Haiku undercounts crossings by about 4; both pick the decoy camp below the dam",
 "• Limitation: 10 reported tasks is a small sample; trails are drawn for the exercise (terrain is real)",
 "• Next: train on our RL environments, test on held-out regions; same engine for weather isobars, nautical charts",
 "• \"Any place with elevation data becomes a test. Thank you.\" → end on the landing page with the QR"],
]

prs = Presentation(DECK)
assert len(prs.slides) == 5, len(prs.slides)
for slide, lines in zip(prs.slides, NOTES):
    slide.notes_slide.notes_text_frame.text = "\n".join(lines)
prs.save(DECK)
print("bullet notes written:", DECK)
