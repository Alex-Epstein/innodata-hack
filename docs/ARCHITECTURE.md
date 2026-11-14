# Architecture (proposed; the team confirms each line, then it moves to DECISIONS.md)

Most of this doesn't depend on which image family we pick, so it can be locked now and everyone starts in parallel.
Each decision lists the options, a recommendation and why. **Bold = recommended.**

## The pipeline

```
 seed + difficulty
        │
        ▼
 gen/<family>.sample(seed, difficulty) ──► data JSON (saved first)
        │
        ├─► gen/<family>.render(data) ──► PNG  +  layout.json (pixel boxes of every drawn element)
        ├─► gen/<family>.ask(data, rng) ──► question + question_type
        └─► gen/<family>.solve(data, question_type) ──► reference answer
        │
        ▼
 validate/  ── every check returns (name, pass, detail); a task is kept only if all pass
   1 schema          fields, types, tolerance stated in the question
   2 two solvers     validate/solvers/<family>.py recomputes the answer a different way; must match
   3 unique answer   no ties; nearest wrong answer is outside the tolerance
   4 render check    sample pixels at layout boxes (right color/shape where data says) + OCR stretch
   5 legibility      min text height in px, no overlapping text boxes, contrast
   6 needs the image blind run (question, no image) on both models; flag if it's answered right
   7 reproducible    re-render from the seed → same SHA-256
        │
        ▼
 eval/  ── one client for every model call
   OpenRouter chat completions · image as base64 · temperature 0 · reasoning effort high · fixed max_tokens
   disk cache keyed by hash(model, prompt, image hash, settings) · retry 429/5xx/timeouts with backoff
   parse "FINAL ANSWER: ..." · score per answer_type · write responses.csv, run_config.json, raw/
        │
        ▼
 report  ── README tables, pilot ladder chart, failure gallery (static HTML), funnel counts
```

## Decisions to confirm

| # | Decision | Options | Recommendation | Why |
|---|---|---|---|---|
| A1 | Language / env | Python, JS, R | **Python 3.12 + `uv` (pinned `uv.lock`)** | Everyone knows it; matplotlib/numpy/networkx; uv makes Docker installs reproducible |
| A2 | Rendering | matplotlib Agg · SVG templates → PNG (cairosvg) · HTML + headless browser | **matplotlib Agg** (plus a domain library if the idea needs one, e.g. `schemdraw` for circuits) | Deterministic byte-for-byte with pinned versions and bundled fonts. A browser in Docker is heavy and less deterministic |
| A3 | Family plugin interface | free-form scripts · one interface | **One interface:** `sample(seed, difficulty) → data`, `render(data, out) → layout`, `ask(data, rng) → (question, qtype, answer_type, tolerance)`, `solve(data, qtype) → answer`, plus `REFERENCES` and `VERSION`. Registered in `gen/__init__.py` | 5 people build in parallel; validate/eval never care which family it is; adding a family is one file |
| A4 | Randomness | `random` · `numpy` global · per-task generator | **`numpy.random.default_rng(seed)` passed down, nothing global** | Same seed, same task, on any machine |
| A5 | Determinism of PNGs | trust it · prove it | **Prove it:** pin matplotlib, use its bundled DejaVu fonts, `savefig(..., metadata={"Software": None})`, fixed DPI and size; store SHA-256 per image; `rebuild` command checks hashes | "Rebuild the identical 10 tasks" is a judged requirement; most teams won't prove it |
| A6 | Answer types | numbers with tolerance · exact (integer, label, sequence) · multiple choice | **Prefer exact** (integer, label like `Wed 10:15`, sequence). Tolerance only where reading a continuous scale is the point. **Avoid multiple choice** | Exact answers are unambiguous to score; multiple choice gives 25% free from guessing |
| A7 | Answer format in the prompt | free text · JSON · a fixed last line | **Last line `FINAL ANSWER: <answer>`**, with the exact format spelled out (e.g. "a time like Wed 10:15") | Easy to parse, reasoning stays free above it. The parser normalizes case, spaces and units |
| A8 | Render check depth | none · layout-box pixel sampling · OCR | **Pixel sampling at layout boxes (must have) + text bounding boxes from matplotlib for overlap and min size; OCR (`tesseract`) as stretch** | The brief asks to check the image against the data; pixel sampling is fast and Alex's lane |
| A9 | "Needs the image" check | heuristic only · blind model run | **Blind run on both models** (cheap: no image tokens), plus a check that the answer string isn't in the question | It's on the kickoff slide's 5-step list |
| A10 | Model calls | sequential · async with a cap | **Async (`httpx`), max 4 concurrent, disk cache** | Pilots finish in minutes, reruns cost $0 |
| A11 | Eval settings | | **temperature 0, `reasoning: {effort: "high"}`, max_tokens 16000** (raise if any `length`), request `usage` so cost is logged per call | Required settings; cost per call lets us budget |
| A12 | Difficulty | per-family ad hoc · shared levels | **`difficulty` 1 to 5 per family, mapped to knob values** (people, tasks, nodes, hops) | Gives the pilot ladder chart and the required "how difficulty changed" story |
| A13 | Single entry point | scripts per step · one CLI | **`python -m factory <cmd>`:** `generate`, `validate`, `eval`, `report`, `rebuild` (from seeds, hash check), `fresh --seed N` (generate + validate + eval one task, for the demo) | The README's Docker commands and the live demo use the same commands |
| A14 | Docker | python slim · full | **`python:3.12-slim` + uv sync; ENTRYPOINT `python -m factory`; outputs to a mounted `/out`**; key only via `-e OPENROUTER_API_KEY` | Matches the README requirements the checker looks for |
| A15 | Final 10 selection | best stumps · fixed rule | **A rule written in DECISIONS.md before the final run** (e.g. first valid seeds at the final difficulty, a fixed split per family) | No cherry-picking accusations; the brief forbids best-of-N on responses |
| A16 | Demo UI | CLI only · static HTML report · Streamlit | **CLI for `fresh` + one static HTML report** (gallery: image, question, truth, both answers, checks) | No server to break on stage; the HTML is also the failure gallery |
| A17 | Extras | none · separate | **`results/extra/`** for blind runs, low-vs-high reasoning, one open-weight model, transcription probe | Interesting findings without touching the reported numbers |

## Folder ownership (proposal)
| Path | Owner | First milestone |
|---|---|---|
| `factory/` (CLI, registry, task schema dataclasses) | Alex | Interface + CLI stubs on main by 10:30 so everyone imports the same thing |
| `validate/` | Alex | Checks 1, 2, 3, 5, 7 on a hand-made task |
| `eval/` | teammate | One real call per model with cost logged; cache and parser |
| `gen/<family_a>/` | teammate | `sample/render/ask/solve` for one task end to end |
| `gen/<family_b>/` | teammate | same |
| `Dockerfile`, `README.md`, `report/`, slides | teammate | Docker build + checker passing on a dummy task by 11:00 |

## Open questions (decide with the idea)
- How many families: 2 deep or 3 shallower? (IDEATION.md section 3)
- Any domain library needed (schemdraw, networkx)? Pin it.
- Final split of the 10 tasks across families and question types.
