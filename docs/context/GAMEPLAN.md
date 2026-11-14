# Innodata game plan (from the real packet, Sat Nov 14)

Sources: `~/Downloads/Innodata Hackathon/` (kickoff PDF, both track briefs, JUDGING.md, the Track 2 format
checker, the slide template) plus the opening-talk transcript.

---

## 1. The facts that decide everything

| | |
|---|---|
| Prizes | $5,000 / $2,500 / $1,250 to the **top three teams overall**. Each track's score is **converted to a percentage**, so both tracks compete in one pool |
| What wins | **The rubric.** Judges score fixed criteria. No criterion is called "creativity" or "pitch", so creativity only pays where it raises a rubric score |
| Deadline | **Upload ZIP by 3:30 PM ET** (Box link). Presentations start 3:30, **5 min per team**, judging 4 to 5. Build window "4h30": ask whether that ends ~1:50 or at 3:30 |
| Team | 5 people (the rules say teams of 5) |
| Keys | $100 OpenRouter + $100 Anthropic **per team**. Only these. Ask Amila for usage mid-day |
| Slides | Optional but templated: **max 5 slides**, fixed order (intro 30s, how 30s, **live demo 2.5 min**, results 1 min, learned 30s) |

**Track crowding doesn't matter.** Prizes are overall and scores are percentages, so a crowded Visual track
costs us nothing. What matters is how close to 100% we get.

### Visual rubric (7 criteria, 0 to 5 each = 35 pts; weights from the kickoff slide)
| Criterion | Weight | What earns a 5 |
|---|---|---|
| Realistic, useful visuals | **20%** | Looks like real software or publication output, real names and units, cites 1 or 2 real references per image, a few distinct styles |
| Reliable generation pipeline | **20%** | Fresh valid tasks from structured data, on demand, every time |
| Fair, verifiable tasks | 15% | Needs the image, unique answer, computed from data, visible in the render, fair tolerance |
| Task difficulty | 15% | Both models actually fail, and the failures come from **reasoning**, not illegibility |
| Meaningful variation | 10% | Different reasoning across tasks, not recolors or rewording |
| Model evaluation | 10% | Real runs, consistent scoring, findings backed by results |
| Runnable submission | 10% | Judges `docker build` and rebuild the **identical** 10 tasks, then score them |

**Tie-break:** task validity and reference-answer verification, then fresh-task generation. That's the
validator lane. Over-invest there.

### Coding rubric (100 pts): Reliability 20 · Fairness 15 · Difficulty 20 · Variation 20 · Regression 10 · Reproducibility 5 · Efficiency 10
Mostly **measured by their scripts**: first-pass yield through 8 gates (structure, name integrity, novelty against
live upstream, grounding, gold = 1.0, nop fails, base healthy, mutation), resolve@3 on Haiku 5.5 via
Harbor + terminus-2, and $ per valid task. 5 tasks from click / zod / jsoncpp.

---

## 2. Track call: **Visual** (unless the team has a Harbor/Docker wizard who wants Coding)

- **Shared pool**: the "everyone picks Visual" worry doesn't apply.
- **Infra risk**: Coding needs the Harbor CLI (not installed on Alex's laptop), building click in Docker, agent
  rollouts (5 tasks x 3 multi-turn runs, slow and expensive), and a mechanical gate on novelty against live
  upstream. One broken piece and yield collapses. Visual needs Python, matplotlib, OpenRouter and one Dockerfile.
- **Where creativity pays**: Visual gives 20% to realism and 10% to variation, both judged by humans who look at
  our images. Coding's scoring is mostly mechanical, so creativity barely moves it.
- **Our edge**: Alex's CV and OpenCV background is exactly the "check the rendering against the data" requirement.

---

## 3. The concept: "The Ops Desk"

**One line:** the visuals an AI assistant at work actually has to read (a team calendar, a project schedule,
a power diagram), where a confident wrong answer costs a meeting, a deadline or an outage.

Why this beats charts and graphs (what most teams will do):
- Every image type is **real business material** with real references (Outlook Scheduling Assistant, MS Project
  Gantt, IEEE one-line diagrams). That scores realism.
- Each family needs a **different kind of reasoning**: interval intersection, dependency propagation, graph
  connectivity. That's variation of the kind the rubric asks for.
- Difficulty comes from **reasoning hops** (more people, a deeper dependency chain, more breakers), never from
  blur. That's exactly what "hard but fair" asks for.
- It lines up with what Innodata sells (their slide 3): computer-use agents, copilots, agent evaluation.

### Task families (ship 3, the 4th is a stretch)
| Family | Image (real reference to cite) | Question types (different reasoning) | Difficulty knob |
|---|---|---|---|
| **A. Scheduling** | Week view of 3 to 6 people's calendars, Outlook / Google style | earliest common free slot of length D · total hours booked by one person · which meeting conflicts if X moves to time T | people, meeting density, near-miss gaps (25 min when 30 is needed) |
| **B. Project schedule** | Gantt chart with dependency arrows, MS Project style | finish date (critical path) · new finish date if task K slips N days · which tasks have zero slack | task count, chain depth, parallel branches |
| **C. Power one-line** | Single-line electrical diagram (breakers, buses, transformers, loads) | which loads lose power if breaker X trips · count of loads with a backup path · number of breakers between source and load | buses, loops/tie breakers, line crossings |
| D. Stretch: **Floor-plan egress** | Architectural floor plan with a scale bar | shortest exit route in meters (stated tolerance) · which exit is nearest from room R | rooms, doors, corridor turns |

Answers are computed from the structured data with standard methods: interval math, CPM, graph reachability,
Dijkstra. Every one is textbook-level, as the brief requires.

**Realism checklist for every family:** real-looking names, titles and units drawn from a fixed vocabulary JSON
(no "Series 1", no "Node A"). 2 or 3 distinct styles per family (theme, density, layout). Small fonts and
clutter like the real thing, never unreadable. 1 or 2 cited real references per image in `tasks.jsonl`.

---

## 4. How we stand out (all of it maps to a rubric line)

1. **Byte-identical reproduction** (Runnable, Reliable). Pin matplotlib, use the bundled DejaVu fonts, strip PNG
   metadata (`metadata={"Software": None}`), seed everything. `validate/` stores the SHA-256 of each image and
   the Docker rebuild checks it. Most teams won't prove their rebuild is identical. We will.
2. **Validator stack** (Fair/verifiable, tie-break). Five checks, one per line of the kickoff slide:
   - structured data saved before rendering
   - **two independent answer solvers** that must agree (e.g. interval algebra vs a minute-by-minute scan;
     networkx vs our own BFS)
   - **render check from pixels**: sample known pixel positions for each block or edge, plus matplotlib text
     bounding boxes for label overlap and minimum font size (OCR is a stretch)
   - **uniqueness**: reject ties, reject near-misses inside the tolerance
   - **requires the image**: a blind run (the question with no image) on both models; above-chance accuracy
     means the task is flagged
3. **Pilot → revise loop in the README.** It's a required section, and we make it the story: a difficulty ladder
   (1 hop → 2 → 3) piloted on both models, a chart of accuracy dropping with hops, and the generator changes it
   caused.
4. **Why the models failed, not just that they failed** (Model evaluation). A cheap side run, kept out of the
   reported eval: ask the model to **first transcribe the raw data** (each person's meetings, each task's
   duration), then score the transcription separately. That splits failures into misreading vs misreasoning.
   It's a real finding, and few teams will have one.
5. **Human fairness evidence**: teammates who didn't build a family solve its tasks, timed. "A careful person
   gets it in about 90 s; both models miss" is the strongest fairness proof, and the brief asks for a hand check anyway.
6. **Confident and wrong.** The brief itself says "a confident wrong answer is worse than no answer." In a
   side run, ask for a 0 to 100 confidence, then report the confident-wrong rate. It quotes their own words
   back to them.

### Getting creative with models (yes, within the rules)
- **Reported eval is fixed**: `anthropic/claude-haiku-5.5` and `openai/gpt-6-luna` (confirm the IDs on
  OpenRouter), temperature 0, reasoning effort high, fixed max_tokens, every row `finish_reason=stop`.
- **Extras go in `results/extra/`**, clearly labeled, never mixed into the reported numbers:
  - **Reasoning effort ablation** (low vs high): does thinking harder fix it? If not, that's evidence of a
    perception failure.
  - **One open-weight vision model** via OpenRouter (a Qwen or Llama vision model, whatever's listed and cheap):
    "even open models fail in the same place" or "they fail differently."
  - **Resolution ablation**: the same task at 2 sizes. If accuracy doesn't move, the failure is reasoning, not pixels.
- Don't use a model to make images or answers. One allowed use: an LLM writes the realistic vocabulary bank
  (names, project titles, equipment tags) once, saved as JSON and disclosed in the README.

### Budget
Make one real call per model first, read `usage.cost` from the OpenRouter response, then estimate. Rough call
count: pilot ~120, final 20, extras ~150, blind checks ~40. Cache every response to disk keyed by (model,
prompt, image hash, settings). Never rerun the final eval except to fix an infra error, and then rerun every task.

---

## 5. Roles (5 people, one folder each)
| Person | Owns | First deliverable |
|---|---|---|
| **Alex** | `validate/` + the shared task schema | Schema + validator skeleton passing on 1 hand-made task by 10:15 |
| P2 | `eval/` (OpenRouter client, cache, retries, parser, scoring, responses.csv, run_config.json, raw/) | One real call per model, cost per call measured |
| P3 | `gen/calendar` (family A) | One task end to end |
| P4 | `gen/gantt` (family B) | One task end to end |
| P5 | `gen/oneline` (family C) **+ Dockerfile, README and format checker from hour 1** | Format checker passing on a dummy submission by 10:30 |

The pitch owner is whoever presents best (probably not the person rushing packaging at 3:00). Everyone writes
insights and limitations as they hit them in `NOTES.md` (the slide-5 material comes from there).

## 6. Clock (aim to upload by 3:10, not 3:29)
| Time | Gate |
|---|---|
| 9:20 to 9:50 | Team, track, roles, repo, keys in `.env`. **Talk to a mentor** (questions in section 8) |
| **10:30** | 1 task per family end to end (data → PNG → answer → validate). Checker passes on the skeleton. Both models answer one task |
| **11:30** | **Pilot 1**: ~10 tasks per family across 3 difficulty levels, both models. Read every wrong answer |
| 12:00 to 1:00 | Lunch at the desk. Generators revised for difficulty, blind check, pixel checks. Pilot 2 |
| **1:30** | **Generator frozen.** Final 10 picked by a rule written down *before* running the final eval (e.g. first valid seeds at the final settings, 3/3/4 across families) |
| 1:30 to 2:15 | Final eval, Docker clean-checkout rebuild with hashes matching, hand-check notes, extras |
| **2:45** | ZIP + `check_submission.py` with 0 FAIL, slides filled in |
| 2:45 to 3:10 | Rehearse twice with a timer. **Upload** |

## 7. The 5-minute presentation (inside their template)
1. **Slide 1 (30s):** the exemplar image full screen. "Four people, one 45-minute meeting. When's the first
   slot?" Give the judges 10 seconds to answer. Then: "Both models said Tuesday 2:00. That's booked. The answer
   is Wednesday 10:15." (Use our real result.)
2. **Slide 2 (30s):** data → render → computed answer → 5 checks. What changes between tasks: the reasoning
   ladder across the three families.
3. **Slide 3 (2.5 min), live:** **a judge picks the seed.** `docker run ... fresh --seed <their number>` →
   image, checks passing, both models answer, scored. Start the model calls when the slide opens (high reasoning
   can take 30+ s) and keep a pre-run seed ready as a fallback.
4. **Slide 4 (1 min):** "N of M generated tasks were valid; we submitted 10. Haiku a/10, Luna b/10." The pilot
   ladder chart, plus the one generator change and what it did.
5. **Slide 5 (30s):** the finding (misreading vs misreasoning), one honest limitation, the next test.

The judges-answer-first beat is the eye-exam idea, cut down to fit 5 minutes. Judges seeing that *they* can
answer it is also our fairness proof.

## 8. Ask mentors in the first 30 minutes
1. Does the 4h30 build window end around 1:50, or is 3:30 the only deadline?
2. Visual weights: the kickoff slide shows percentages, the brief says 7 x 0 to 5. Which is used?
3. Is it OK to put extra models and ablations in a separate results folder?
4. Does picking the final 10 from pilot-informed settings count as cherry-picking if we disclose the rule?
5. How do we check our key's spend mid-day?
6. (If Coding) resolve@3 or @5? The kickoff slide says 5, the talk said 3.

## 9. RL environments in 60 seconds (from the kickoff talk)
An RL environment is **a task plus an automatic checker that pays a reward**. Labs train agents by letting them
attempt thousands of tasks and reinforcing the attempts the checker accepts ("RL from verifiable rewards").
That's why the answer must come from code: a wrong reward teaches the wrong lesson. And it's why "stumped 1 of 3
times" counts as a good task: a task the model always solves, or never solves, teaches it nothing. The useful
ones sit at the edge of what it can do. Our factory makes that edge on demand. Say that sentence in the pitch.

## 10. If the team picks Coding anyway
Python + `pallets/click` at a release tag (the team knows Python, pytest is simple). Pipeline: a capability
taxonomy (option types, parameter sources and env vars, help formatting, shell completion, CliRunner testing,
command chaining) decides *what* to generate, which gives variation by construction. Claude writes the spec,
gold patch and tests. Then the gates: `check_structure`, `selfcheck.sh` (oracle 1.0, nop 0.0), our own mutation
gate, a novelty search against upstream issues and PRs, then Haiku 5.5 k=3. Log tokens and attempts into
`pipeline_run.json` from the first call. Install Harbor in the first 15 minutes or don't pick this track.
