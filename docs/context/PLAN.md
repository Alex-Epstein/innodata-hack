# Innodata game plan (Sat Nov 14, freeze 4:15 PM)

## 0. The one strategic call

The organizers said two things: **"evidence your approach works beyond a single example"** and **"a focused,
reliable prototype over a polished product."** Their application form also tells us what they grade:

- Coding: "would the tests catch an incorrect solution?"
- Visual: "is the question answerable from the image?" and "verify the reference answer **independently of the
  model being tested**". Also "which visual capabilities **matter in real-world applications**".

So "push hard" here means **depth of rigor, not breadth of features**. Most teams will ship a generator, a model
call and a bar chart. We beat them with a **trust stack**: every item proves itself correct several independent
ways, and every model number has error bars. Two or three capabilities made airtight, then everything else goes
into evidence and the demo.

Innodata sells AI evaluation data to frontier labs and enterprises, and it started in **document data**. Their
judges think in terms of data quality, label validity, cost per item, and what we learned about the models.
Speak that language.

---

## 1. Recommended: Visual Task Factory, "an eye exam for AI"

**Pitch in one line:** an optometrist finds the exact line where your vision fails. We do that for frontier
models, on the documents enterprises actually feed them, and every answer key is proven correct before a
model ever sees it.

### Capabilities (picked for real enterprise work, Innodata's home turf)
| # | Capability | Real use | Difficulty knobs (each one a sweepable number) |
|---|---|---|---|
| A | **Chart value reading** (bar + line) | finance dashboards, 10-K figures | bars/points, tick spacing vs value precision, gridlines on/off, series count + legend, label rotation |
| B | **Table lookup in a scanned doc** | invoices, claims, statements | rows x cols, near-duplicate distractor values, merged headers, scan degradation (rotation, blur, JPEG, noise) |
| C | **Gauge / meter reading** (stretch) | industrial inspection, utilities | tick density, needle thickness, glare, viewing angle |

Ship A and B airtight first. Add C only after the evidence pipeline is done.
Every capability shares a **degradation knob** (the "photo of a printout" axis) so we get one curve that
cuts across all of them.

### The trust stack (this is where we win)
1. **Correct by construction**: the answer comes from the generator's params, never from a model.
2. **Pixel oracle (answerable from the image)**: a separate CV solver (OpenCV, Alex's lane) reads the answer
   back from the rendered PNG alone. Keep the item only if the oracle agrees with the params. That proves the
   answer can be recovered from the image itself, separately from how it was generated.
3. **Ambiguity guard**: no overlapping labels (bounding-box check), minimum size and contrast, near-ties
   rejected, an explicit tolerance band per item.
4. **Blind baseline**: ask each model the question with **no image**. Accuracy above chance there means the
   item leaks the answer through the text, so the item gets fixed. It also catches models guessing from priors.
5. **Counterfactual twins**: same scene with one value changed. If the answer flips and the model's doesn't,
   it wasn't looking. Measures "actually reads" vs "guesses plausibly".
6. **Human agreement**: the team labels about 30 items, and **judges add more live at the demo** (section 1d).
7. **Statistics**: bootstrap 95% CIs, a logistic psychometric fit per model per knob, and a **breaking point**
   (the knob value where accuracy crosses 50%) with its own CI.
8. **Reproducible**: seeds, a disk cache of every response, one command, a dataset hash in the report.

Report a **validity funnel**: generated → renders clean → oracle agrees → ambiguity guard → blind-safe → kept.
The rejection rate at each stage is itself evidence the factory has standards.

### Standout extras (in priority order, only after the core works)
1. **Item calibration like the SAT**: fit an IRT model (difficulty + discrimination per item, ability per
   model). We already know Glicko from Volee; same idea. Lets us say which items are actually informative
   and drop useless ones. Innodata will recognize this from their own work.
2. **Adaptive breaking-point search**: binary-search each knob per model, so we find a model's limit in about 20
   calls instead of 500. That's a cost story.
3. **Failure taxonomy, computed**: off by one tick, read the neighboring bar or cell, wrong series, unit or
   scale slip, a hallucinated value. Classified by code from (truth, answer, scene), so no model does the grading.
4. **Cost per validated item** and items per minute. A data company cares about this.

### 1d. The demo moment (judges touch it)
- **Judges take the eye exam.** On a laptop: 8 items with a 10-second timer each, then their score goes up on
  the board **next to each frontier model on the same items**. Humans usually win on chart reading, and that gets a reaction.
  Their answers also add to the human-agreement stat live.
- **Turn the knob.** A slider makes a fresh item at difficulty X, sends it to a model live, and shows truth vs
  answer. Then they watch it break.
- **Failure gallery**: 3 images where a frontier model is confidently wrong about something a person reads at
  a glance.

---

## 2. Plan B: Coding Task Factory, "tests that can't be fooled"

Use this if the team leans SWE. Same rigor philosophy.

- **Seed repos**: 2 or 3 small, realistic multi-file Python services written at the event (an inventory API,
  a ledger/CSV library, a rate limiter). Tickets read like real Jira tickets: a user story plus acceptance criteria.
- **Generator**: ticket → reference patch → hidden tests, plus difficulty tags (files touched, cross-module deps,
  edge cases, spec vagueness).
- **Validity funnel**: tests pass on the reference · fail on the base repo and on a stub · stable across 3
  shuffled runs (flake check) · **mutation score** (AST mutators: flip comparisons, off-by-one, drop a branch) ·
  **impostor solutions** (a red model writes plausible but wrong patches, and the tests must reject them; the
  Red Ledger pattern) · leakage check (the spec doesn't contain the solution) · dedupe.
- **Spec ambiguity detector**: 3 independent models solve from the spec alone, then **differential testing**
  runs their solutions on generated inputs. Where they disagree with each other, the spec is ambiguous, and we
  point to the sentence responsible.
- **Probe**: pass@1 by difficulty per model, regressions (did it break existing tests?), failure categories.
- **Demo moment: "Sneak a bug past the tests."** A judge edits the reference to plant a bug, hits run, and sees
  whether the hidden tests catch it. The kill board updates.
- Risk vs Visual: more moving parts (sandboxed execution, heavier LLM code generation, and a bigger quota bill).

**Why Visual first:** it fits Alex's CV strength, it's more deterministic, it costs fewer tokens per item,
and an image failure lands in a demo in 2 seconds. Switch if the team is stronger at SWE or the room is all Visual.

---

## 3. Team of 4: who owns what (one folder each)
| Role | Visual | Coding |
|---|---|---|
| **Alex** | `gen/` + `validate/` (generators, pixel oracle, ambiguity guard) | `validate/` (funnel, mutants, sandbox) |
| P2 | `probe/` (model client, cache, retries, blind + twin runs) | `gen/` (seed repos, ticket generator) |
| P3 | `stats/` + `report/` (CIs, psychometric fit, IRT, funnel, gallery, EVIDENCE.md) | `probe/` + `stats/` |
| P4 | `demo/` + pitch (eye exam UI, knob slider, deck, Devpost) | `demo/` + pitch ("sneak a bug" UI) |

With 5 people, split `gen/` from `validate/`.

## 4. Clock (gates in bold)
| Time | Do |
|---|---|
| 9:00 | Intros, organizer questions (CLAUDE.md section 1), pick a track, roles. Repo + AGENTS.md + `.env` |
| 9:30 | **Freeze the schemas** (item + result) plus 5 hand-written fixtures. Everyone builds against them with `MOCK=1` |
| **10:30** | **One capability end to end**: generate → oracle → one real model → scored |
| **12:00** | **First real numbers**: 2 or 3 models, about 100 items, cached. Write the first lines of EVIDENCE.md |
| 12:00 to 2:00 | Capability B, knob sweeps, blind baseline, twins, human labels. Scale to hundreds of items |
| 2:00 to 3:30 | Curves with CIs, breaking points, funnel, gallery, taxonomy; the eye-exam UI wired to real items |
| 3:30 | Stretch only if green: IRT, adaptive search, capability C |
| **4:15** | **Freeze.** `make all` reproduces every number. Submission drafted |
| 4:15 to 5:00 | Rehearse twice with a timer; one person owns the laptop and the backup screenshots |

## 5. Pitch (2 to 3 min)
1. Hook with a real number from **our own run**: "Model X misreads a bar chart N% of the time once it has
   more than K bars. A person reads it in two seconds."
2. The problem: static benchmarks leak into training data, and hand-made sets don't scale or prove their own answers.
3. The factory: generate → **prove** (oracle, guard, blind, twins) → probe → calibrate.
4. The chart: accuracy collapsing with difficulty, every model, error bars, breaking points marked.
5. Gallery: 2 striking failures.
6. Trust numbers: funnel rejection rate, oracle agreement, human agreement, blind-baseline accuracy, cost per item.
7. Monday at a lab: run `make all` with a new capability plugin and get a calibrated, contamination-proof
   suite by lunch.

Prepared answers: how do you know the answers are right (stack layers 1 to 3)? Too synthetic (degradation
knob, real document layouts, and the human baseline)? Cost (cache + adaptive search, $/item)? 10k items (it's
procedural, and the funnel throughput is measured)?

## 6. Ready-to-paste for the team (after track is picked)
See the chat; Claude fills in names, repo URL and roles once the team exists.
