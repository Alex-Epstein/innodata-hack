> Written by Alex's other session the morning of the event, before the packet arrived. Where it differs from docs/BRIEF.md, BRIEF.md wins.

# Innodata hackathon: everything you need (read all of this first)

Team handoff brief for the **Innodata hackathon, Sat Nov 14 2026, 9 AM to 5 PM, NYC**.
This file is the whole brief. It was written by Alex's HackPrinceton session the morning of the event, from
everything he had gathered. Treat it as the source of truth until the organizers say otherwise, and update
`## Live notes` at the bottom as things change.


---

## 1. The event

| | |
|---|---|
| Where | St. John's University Manhattan campus, **101 Astor Place**, NYC |
| When | Registration 8:30 AM · hacking 9:00 AM to 5:00 PM · **freeze code at 4:15 PM** |
| Teams | **Assigned by Innodata**, 4 to 5 people. Alex probably won't be on a team with his Princeton teammates. Julian Sanchez (`jul-san`) is also attending |
| Prizes | $5,000 / $2,500 / $1,250 (ask whether that's per track or overall) |
| Models | **Organizer-provided model APIs and coding assistants.** Use those for every model call |
| Judges want | "**evidence your approach works beyond a single example**" and "**a focused, reliable prototype over a polished product**" |

### The two tracks (the assigned team picks one)
- **Coding Task Factory:** auto-generate realistic feature-development tasks (requirements, a reference
  implementation, tests) for evaluating AI coding systems.
- **Visual Task Factory:** generate synthetic images with questions and verifiable answers, then probe frontier
  multimodal models.

Both tracks have the same shape, and it's the shape that won Alex 2nd place at Cal Hacks (section 4):
**a generator that makes cases with a known answer → the model under test → an independent verifier →
a scoreboard plus a failure gallery**, with difficulty knobs and accuracy-vs-difficulty curves.

### Ask the organizers in the first 30 minutes
1. Which models can we call, with what rate limits, and is there a key per team? Can we see the cost or quota?
2. Prizes: per track or overall? How many finalists? How long is the demo, and live or slides?
3. What do the judges score (rubric)? Do they want the dataset itself, the generator, or the evaluation results?
4. Submission: repo link, Devpost, a form? Public repo allowed? What license or IP terms apply (see section 2)?
5. Are there reference formats (task schema, an existing benchmark they want us to match, like SWE-bench style)?

---

## 2. Hard rules

- **Money: never charge Alex.** Only organizer-provided APIs or free tiers with no card attached. Even if
  Before any batch run, estimate the call count and check the quota. Cache every model response to disk so
  reruns cost nothing.
- **Keys** go only in a gitignored `.env`. Never paste a key into chat, logs, commits, issues or the README.
- **Write the code at the event, in a new repo.** Don't copy code from `hackprinceton-f26` or Red Ledger.
  Reuse patterns and ideas only (pointers in section 8 are for reading).
  (Summer 2027), so flag anything that assigns IP broadly. Ask Alex before signing anything for him.
- **Team messages:** when something needs to reach teammates, give Alex **only the exact text to paste**,
  in one fenced block. Keep everything else short.
- **Autopilot:** do in-bounds work without asking. Stop only for things that are Alex's call (money, signing
  agreements, other people's code, picking the track with the team).

---

## 3. Who Alex is (for picking his role on the team)
- Georgia Tech, B.S. Math + CS. Strengths: **ML and computer vision**, Python, evaluation harnesses, fast
  full-stack prototypes, directing many Claude sessions in parallel.
- ML research (Polo Club), embedded CV work (EPIC Lab), and **Red Ledger** (Cal Hacks 13.0, 2nd place, CRS
  track): an adversarial sandbox where a red agent attacks, a blue controller gates payments, and a harness
  scores every run.
- Good roles for him on an assigned team: **generator + validator** (the core that makes the dataset
  trustworthy), or **harness + scoreboard** (model calls, caching, metrics, charts). Let a teammate who wants
  it own the pitch.

---

## 4. Why this shape wins: lessons from Red Ledger and other winning projects

**Red Ledger (Cal Hacks, Oct 2026)**, repo at (Alex's local files) (read-only reference):
- A catalog of cases with known ground truth, an agent under test, an **independent** judge, and a
  scoreboard that turns runs into one headline number plus a gallery of failures.
- The pitch landed because of **before/after numbers from real runs**: the controller's share of fraud dollars
  stopped went from 14% to 85%. Judges trust a measured curve over a claim.
- `battlefield/app/evolution/report.py` and `docs/EVIDENCE.md` show the pattern: every number in the pitch
  traces to one file, rerunnable with one command.
- What bit us: numbers drifted between the pitch and the code (fix: one EVIDENCE file, never round), and
  infrastructure on a personal account cost real money (fix: section 2).

**What winners had in common** (from (Alex's local files)):
1. A real person and a real number in the first 15 seconds.
2. Honest evals, **including where it fails**, said out loud.
3. Deterministic core, AI for judgment. Ground truth is computed, never generated by a model.
4. Judges touch it: they turn a knob and watch the numbers change.
5. Safety and validity rules enforced in code, and the pitch says so.

For Innodata specifically, "evidence beyond a single example" means **scale + statistics**: hundreds of
generated items, a validity rate for the generator itself, accuracy curves with error bars across several
models, and a failure gallery. "Focused and reliable" means **pick 2 or 3 capabilities and make them airtight**
rather than 10 shaky ones.

---

## 5. Track playbooks

### 5a. Visual Task Factory
**Pipeline**
1. **Generator**: parametric scenes drawn in code (matplotlib, PIL, maybe SVG). Each item is
   `{id, capability, params, seed, image_path, question, answer, answer_type, difficulty}`. The answer comes
   from the params, **never from a model**.
2. **Capabilities** (pick 2 to 4 that matter in real work):
   - read a value off a bar or line chart (finance dashboards)
   - read an analog gauge or clock (industrial)
   - look up a cell in a rendered table (documents)
   - count objects with occlusion (inventory)
   - spatial relations: left/right/above/inside (robotics)
   - trace a path in a diagram or maze (maps, flowcharts)
3. **Difficulty knobs**, each a number you can sweep: object count, occlusion %, label density, tick spacing,
   rotation, noise/blur, distractors, resolution.
4. **Validator**, so every item is answerable and unambiguous:
   - minimum object size and contrast
   - labels don't overlap (check bounding boxes)
   - one correct answer (reject ties and near-ties beyond the tolerance)
   - re-check the render in code (sample pixels at known positions, re-detect counts with simple CV)
   - a human spot-check of about 20 items; report the agreement rate
   - report the **validator rejection rate** as a quality stat
5. **Probe** 2 or 3 models through the organizer API: fixed seeds, logged prompts, a strict answer format,
   and a tolerant parser (numbers within tolerance, normalized strings).
6. **Report**:
   - accuracy vs difficulty per model per capability, with bootstrap 95% error bars
   - each model's "breaking point" (the difficulty where accuracy drops below 50%)
   - a failure gallery: the image, the question, the model's answer and the truth
   - one command reruns everything

**Ways to stand out**
- **Adaptive difficulty**: binary-search each knob to find each model's breaking point with few calls.
- **Contamination-proof by construction**: fresh procedural items, so models can't have trained on them.
- **Failure taxonomy**: group errors into off-by-one counting, reading the wrong axis, distractor confusion,
  and so on.
- **Minimal pairs**: the same scene with one knob changed, which isolates what breaks the model.

### 5b. Coding Task Factory
**Pipeline**
1. **Task generator**: start from a small seed codebase (a tiny inventory API, a todo app, a parser library).
   A model proposes a feature request, then writes the **reference implementation** and **hidden tests**.
   Schema: `{id, repo_snapshot, spec, reference_patch, tests, difficulty, tags}`.
2. **Validity checks** (the core of the project):
   1. tests **pass** on the reference
   2. tests **fail** on the untouched repo and on an empty or stub solution
   3. **mutation testing**: small edits to the reference (flip a comparison, drop a branch, off-by-one) must
      be caught by the tests; report the mutation score
   4. **spec sufficiency**: a second model solves from the spec alone. If it fails while the reference
      passes, check the spec for ambiguity
   5. **leakage and dedupe**: the spec must not contain the solution; drop near-duplicate tasks (AST or
      text similarity)
   6. every check runs in a sandbox (subprocess with a timeout, no network)
3. **Difficulty knobs**: number of files touched, cross-module dependencies, edge cases, spec vagueness,
   size of the existing code.
4. **Probe** 2 or 3 coding models: pass@1 by difficulty, how often they break existing tests (regressions),
   and failure categories.
5. **Report**: the validity funnel (generated → passes reference → kills mutants → spec-sufficient → kept),
   pass rate vs difficulty per model, and example failures.

**Ways to stand out**
- The **validity funnel** chart is the money shot: it proves the generator's tasks are trustworthy at scale.
- **Mutation score** as the quality metric for the tests, a number most teams won't have.
- Tasks that look like real tickets (a user story plus acceptance criteria), not LeetCode.

### Default stack (fast, cheap, reliable)
- Python 3.12 + `uv`, `numpy`, `pandas`, `matplotlib`, `pillow`, `scipy` (bootstrap), `pytest`,
  `mutmut` or a home-made mutator (coding track).
- **One** model-client module: async with a concurrency limit, retries with backoff on 429, and a **disk
  cache** keyed by a hash of (model, prompt, image hash, params). A rerun costs zero calls.
- Data as JSONL plus a folder of PNGs. `make all` (or one script) runs generate → validate → probe → report.
- Demo UI: a static HTML report, or Streamlit if someone wants knobs live. Charts beat UI polish.
- `MOCK=1` mode with a fake model, so the pipeline and demo run without the API.

---

## 6. Working as a team (the Princeton setup, trimmed for 8 hours)
- **Repo is the shared brain**: a short `AGENTS.md` (what it is, golden path, who owns which folder, rules)
  plus `CLAUDE.md` containing `@AGENTS.md`, so every AI tool reads the same thing.
- **Contracts first (first 45 min)**: freeze the item schema and the results schema, plus 5 hand-written
  fixture items. Then everyone builds against fixtures in parallel.
- **Own a folder each**: `gen/`, `validate/`, `probe/`, `report/`. Two agents never edit the same files.
- **Small PRs, merge your own when tests pass.** `main` always runs end to end.
- **One live log**: a pinned GitHub issue that everyone's agent comments on after each step, so all agents
  share context. For reference, Princeton used (Alex's local files) and `catchup`.
  Recreate them at the event; don't copy them.
- **One EVIDENCE file**: every number in the pitch comes from `results/` generated by the one-command run.

### 8-hour plan
| Time | Do |
|---|---|
| 9:00 to 9:30 | Intros, pick the track, split roles: generator / validator / harness / report + pitch |
| 9:30 to 10:30 | Schemas + fixtures; **one capability end to end** (generate → validate → one model answers → scored) |
| 10:30 to 12:00 | Harness on 2 or 3 models with caching; **first real accuracy numbers** |
| 12:00 to 2:00 | More capabilities + difficulty knobs; run at scale (hundreds of items) |
| 2:00 to 3:30 | Charts with error bars, failure gallery, validity stats, one-command rerun |
| 3:30 to 4:15 | Demo + pitch prep, submission draft. **Freeze 4:15** |
| 4:15 to 5:00 | Submit, rehearse twice with a timer |

### Pitch shape (about 2 to 3 min)
1. One line: what breaks in today's evals (static benchmarks leak into training data; hand-made tasks
   don't scale).
2. The factory: generator → validator → probe, with one sentence on why the answers are guaranteed correct.
3. **The chart**: accuracy collapsing as difficulty rises, for each model, with error bars.
4. The failure gallery: 2 or 3 striking examples.
5. Proof of reliability: validator rejection rate, human agreement, mutation score.
6. What's next, and how a lab would use it Monday.

Have answers ready for: how do you know the answers are right? Isn't this too easy or too synthetic? How much
did it cost to run? Can it scale to 10k items?

---

## 7. First 15 minutes in this session
1. Ask Alex which track the team picked and who is on it (names, GitHub usernames, what each person wants to own).
2. Create the repo (Alex's GitHub `Alex-Epstein`, public unless the organizers say otherwise), add teammates,
   write `AGENTS.md` and the schemas, and put the organizer API key in a gitignored `.env`.
3. Give Alex a paste-ready team message: repo link, roles, rules, the plan above.
4. Build the one-capability end-to-end slice right away.

---


## Live notes
(Update as the day goes: track picked, team, repo URL, API details, rubric, decisions.)
- Packet: `~/Downloads/Innodata Hackathon/`. Game plan from it: `GAMEPLAN.md` (supersedes PLAN.md and IDEAS.md where they differ).
- **Upload ZIP by 3:30 PM ET**; 5-min presentations at 3:30; judging 4 to 5. Teams of 5. Prizes are top 3 overall; track scores converted to %.
- Keys: $100 OpenRouter + $100 Anthropic per team (organizer keys only). Visual must eval `anthropic/claude-haiku-5.5` + `openai/gpt-6-luna`, temp 0, reasoning high, finish_reason=stop on every row.
- Visual format checker: `track2-format-check.zip` → `check_submission.py` (stdlib only). Must reach 0 FAIL.
- Track: **Visual** (picked). Concept: "The Ops Desk" (calendars, Gantt, power one-line). Team message sent via Discord.
- Repo: https://github.com/Alex-Epstein/innodata-hack (public, empty at 9:4x). Write invites sent to tech-cosmos, dl3832, WindHurtLZ (team may still change).
