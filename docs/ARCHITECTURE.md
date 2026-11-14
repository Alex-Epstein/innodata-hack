# Architecture: team discussion (decide by ~11:20)

Same approach as the idea doc: options and trade-offs are on the page, everyone weighs in, then Alex decides and
each decision becomes one line in `docs/DECISIONS.md` (after that, nobody re-argues it).

**How to weigh in (5 min):** read Part 1, then comment on the **Architecture discussion issue** (https://github.com/Alex-Epstein/innodata-hack/issues/9) with the decision
numbers, e.g. `D2: B, because ...` or `D5: worried about X`. Silence = OK with the recommendation.
Part 2 is defaults that stand unless someone objects.

## The pipeline (whatever idea wins)

```
 seed + difficulty
        │
        ▼
 gen/<family>.sample(seed, difficulty) ──► data JSON (saved first)
        ├─► render(data) ──► PNG  + layout.json (pixel boxes of every drawn element)
        ├─► ask(data, rng) ──► question + question_type
        └─► solve(data, question_type) ──► reference answer
        ▼
 validate/  every check → (name, pass, detail); keep a task only if all pass; count the funnel
        ▼
 eval/      one cached OpenRouter client → parse "FINAL ANSWER:" → score → responses.csv, run_config.json, raw/
        ▼
 report     README tables, pilot ladder chart, failure gallery (static HTML), funnel counts
```

---

## Part 1: decisions to discuss

### D1. How many image families?
| Option | For | Against |
|---|---|---|
| A. One family, 4 or 5 question types | Most reliable; everyone polishes one generator; realism can be excellent | Variation (10%) capped; "one trick" risk if models ace it |
| **B. Two families** | Variation across genuinely different reasoning; still deep; one generator owner each | Two realism bars to clear |
| C. Three families | Most variation, best story | Three generators in ~3 hours with strangers; likely shallow |

**Recommendation: B.** Reliability and realism are 40% together; variation is 10%. Two done well beats three done thin.
**Question for the team:** does the spike data change this (e.g. one family is so hard it carries everything)?

### D2. How do we render?
| Option | For | Against |
|---|---|---|
| **A. matplotlib (Agg)** + a domain library if needed (schemdraw, networkx layouts) | Byte-identical rebuilds are easy; everyone knows it; text boxes available for checks | Takes effort to look like real software |
| B. SVG templates → PNG (cairosvg) | Pixel-perfect "real software" look; layout control | Font rendering differences across machines; more code |
| C. HTML/CSS + headless browser | Most realistic UI look (calendars, dashboards) | Heavy Docker image; harder to make deterministic; slow |

**Recommendation: A**, but realism is 20%, so if a spike shows matplotlib can't look real for our family, B is the fallback.

### D3. What kind of answers?
| Option | For | Against |
|---|---|---|
| **A. Exact answers** (integer, a label like `Wed 10:15`, a list) | Unambiguous scoring; no tolerance arguments; a clear fairness story | Questions must be designed so the exact answer is reachable |
| B. Numbers with a stated tolerance | Natural for reading scales and measurements | Tolerance has to be justified ("a careful human could meet it"); more ways to be called unfair |
| C. Multiple choice | Easy to parse | 25% free from guessing; weaker difficulty evidence |

**Recommendation: A, with B only where reading a continuous value is the point.**

### D4. How do we prove the image matches the data? (render check, judged under "fair, verifiable")
| Option | For | Against |
|---|---|---|
| A. Layout sidecar: the renderer records where it drew everything; validate samples those pixels | Fast, exact, easy | Not fully independent: the same code drew it and described it |
| **B. A + independent CV re-detection**: OpenCV finds the elements from the PNG alone (colored blocks, line endpoints, filled vs hollow symbols) and recomputes key facts | Truly independent of the generator; a strong tie-break argument; Alex's CV lane | 30 to 60 min more work per family |
| C. A + OCR of labels (tesseract) | Proves text is readable as rendered | Adds tesseract to Docker; OCR noise on small fonts gives false fails |

**Recommendation: B** (validity is the tie-break). OCR only if time is left.

### D5. How do we make tasks hard, honestly?
| Option | For | Against |
|---|---|---|
| **A. Difficulty ladder by design**: knobs that add reasoning steps (more people, more breakers, deeper chains); pilot each level; final set uses the hardest level that stays fair | Clean story ("accuracy fell from X to Y as steps went from 2 to 5"); no selection bias | Models might still pass at the top level |
| B. Adversarial filtering: generate many, keep the ones the models fail | Guarantees "hard" tasks | Selection bias: judges may see it as cherry-picking; can keep tasks that are hard by accident (ambiguous) |
| C. Failure-driven redesign: read pilot failures, add more of what broke the models (a new question type, a distractor), re-pilot | The "pilot results → generator changes" section writes itself | Needs 2 pilot rounds on the clock |

**Recommendation: A + C.** No filtering on model outcomes for the final 10; the selection rule is fixed before the final run (D7).

### D6. The prompt
| Option | For | Against |
|---|---|---|
| **A. Image + question + "Think step by step, then end with `FINAL ANSWER: <format>`"**, the same for both models | Reasoning stays visible (great for the "why it failed" analysis); trivial to parse | Longer replies, more tokens |
| B. Answer only, no reasoning | Cheap | We lose the failure analysis; reasoning effort "high" happens anyway |

**Recommendation: A.** Reasoning tokens are where our findings come from.

### D7. Picking the final 10
| Option | For | Against |
|---|---|---|
| **A. A fixed rule, written in DECISIONS.md before the final run** (e.g. seeds 1000 to 1009 at the final settings, alternating families, skipping any that fail validation) | Honest, reproducible, defensible in Q&A | Might include a task both models get right |
| B. Hand-pick the most interesting ones | Best showcase | Looks like cherry-picking; the brief warns about selective reporting |

**Recommendation: A.** A task the models get right is fine to report; we say so honestly.

### D8. What do we show in the live demo?
| Option | For | Against |
|---|---|---|
| A. CLI only | Nothing to break | Hard for judges to see |
| **B. CLI `fresh --seed N` + one static HTML report** (image, question, truth, both answers, all checks) | Judges see everything; doubles as the failure gallery; no server | A bit of HTML work |
| C. Streamlit app with knobs | Most interactive | A server on stage; time sink |

**Recommendation: B.**

### D9. Who owns what? (set after the idea is picked)
| Path | Owner |
|---|---|
| `factory/` (CLI, registry, schemas), `validate/` | Alex |
| `eval/` | ? |
| `gen/<family 1>/` | ? |
| `gen/<family 2>/` | ? |
| Dockerfile, README, `report/`, slides | ? |

---

## Part 2: defaults (stand unless someone objects)
| # | Default | Why |
|---|---|---|
| E1 | Python 3.12 + `uv`, pinned `uv.lock` | Reproducible installs in Docker |
| E2 | One plugin interface per family: `sample(seed, difficulty)`, `render(data, out) → layout`, `ask(data, rng)`, `solve(data, qtype)`, plus `REFERENCES`, `VERSION` | Parallel work; validate and eval never care which family it is |
| E3 | `numpy.random.default_rng(seed)` passed down, nothing global | Same seed, same task everywhere |
| E4 | Byte-identical PNGs: pinned matplotlib, bundled DejaVu fonts, `metadata={"Software": None}`, fixed size and DPI, SHA-256 stored and checked by `rebuild` | Judges rebuild the 10 tasks |
| E5 | Validator checks: schema · two independent solvers agree · unique answer (no ties, nearest wrong answer outside tolerance) · render check (D4) · legibility (min text px, no overlaps) · needs the image (blind run on both models) · reproducible hash | One check per line of the organizers' "make it verifiable" slide, plus ours |
| E6 | Eval: OpenRouter via `httpx`, async, max 4 concurrent, disk cache keyed by hash(model, prompt, image hash, settings), retry 429/5xx/timeouts, temperature 0, `reasoning: {effort: "high"}`, max_tokens 16000 (raise if any `length`), `usage` logged per call | Required settings; cost is tracked |
| E7 | One CLI: `python -m factory generate | validate | eval | report | rebuild | fresh --seed N` | The README's Docker commands and the demo use the same thing |
| E8 | Docker: `python:3.12-slim` + uv; ENTRYPOINT `python -m factory`; outputs to a mounted `/out`; key only via `-e OPENROUTER_API_KEY` | What the format checker looks for |
| E9 | Extras (blind runs, low vs high reasoning, an open-weight model, transcription probe) go in `results/extra/`, never mixed into reported numbers | Interesting findings without touching the required evaluation |
| E10 | `difficulty` 1 to 5 per family, mapped to knob values | Gives the pilot ladder chart |
