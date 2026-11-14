# factory/ and validate/: the core

One command line for the whole pipeline. Families plug in through `contracts/FAMILY.md`; models are only called
through `eval/`.

## Commands
```bash
uv run python -m factory list                     # working families, versions, templates
uv run python -m factory generate --family topo --template flood --difficulty 3 --seeds 0-9 --out tasks/pilot1
uv run python -m factory validate --tasks tasks/pilot1                 # add --drop-invalid to keep only passing tasks
uv run python -m factory validate --tasks tasks/pilot1 --blind-results results/extra/blind   # + needs_image
uv run python -m factory eval     --tasks tasks/pilot1 --out results/pilot1                   # = eval.run
uv run python -m factory rebuild  --tasks tasks/final [--out /out/rebuilt]  # judges: same bytes from the seeds
uv run python -m factory fresh    --seed 7 [--family F --template T --difficulty D] [--out /tmp/fresh] [--show]
MOCK=1 uv run python -m factory fresh --seed 3 --family example        # offline, canned model replies
```
- `generate` writes `tasks.jsonl`, `data/`, `images/`, `layout/` and `generation_log.json` (attempted, rejected
  seeds with the reason, kept). `--family`/`--template` take a name, a comma list or `all`; `--append` adds to a set.
- `validate` writes `checks` into every `tasks.jsonl` line and `validation_report.json` (pass/fail per check, the
  cumulative funnel, every failure's reason). Exit 0 only if every task passes.
- `rebuild` regenerates each task from (family, template, difficulty, seed) and compares the SHA-256 of the PNG and
  the data JSON, plus the question and answer. Exit 1 on any mismatch.
- `fresh` is the live demo: build one task, print the question and image path, run every check (✓/✗), and ask both
  models in a background thread while the checks run. Without `--family`, the seed picks the family and template
  (test-only families are skipped). A rejected seed moves to the next one and says why. `--show` adds short pauses.
  Writes a one-task folder with `results/` (`$OUT_DIR/fresh` in Docker, else `/tmp/fresh`).

## The checks (`validate/checks.py`, each returns `(name, passed, detail)`)
| Check | Passes when |
|---|---|
| `schema` | SCHEMA.md fields and types; `task_id` is `<family>-...-<seed:06d>`; image is a relative PNG that exists; a non-integer `number` answer has exactly one tolerance and the question states it |
| `data_first` | the data JSON exists, matches the task's `seed`/`task_id`, is unchanged since generation (SHA-256), and was written before the PNG (mtime now, or as recorded at generation) |
| `two_solvers` | `solve_independent(data_json, template)` equals the answer, compared with `eval/scoring.score` |
| `render_matches_data` | every `layout.probes` pixel is within `tol` (max per-channel difference, default 40) of `expect` |
| `legibility` | every `layout.texts` box is at least 8 px tall, no two overlap by more than 2 px, none cut off at the edge |
| `answer_not_in_question` | the answer is not in the question, unless it is one of several same-shaped candidates ("A, B or C"); short labels match case-sensitively; multiple choice and single digits are exempt |
| `reproducible` | a rebuild in a temp folder gives the same PNG and data bytes, question and answer |
| `needs_image` | only with `--blind-results`: not every model got it right without the image |

**Advisory LLM review** (`validate/review.py`, not a check: it never changes an answer, never edits `tasks.jsonl`
and never drops a task). `claude-sonnet-5-5` reads each task (image, question, reference answer, `steps`) and flags
what a careful human would raise: `ambiguity` (another answer is reasonable), `legibility` (something the answer
needs is too small, covered or cut off), `leakage` (the question gives it away), `realism` (what gives the image
away), `other`. It writes `review_report.json` next to `tasks.jsonl` and prints a table; every task it reviews goes
into the README's "Hand check" notes, flagged ones with what was found and what was done.
```bash
uv run python -m validate.review --tasks tasks/final --dry-run   # call count and estimated cost, no calls
uv run python -m validate.review --tasks tasks/final [--limit N]  # then log the actual token totals it prints
```
Calls the Anthropic API directly with `ANTHROPIC_API_KEY` from `.env` (fixed settings, max_tokens 2000, JSON
output; the model only takes the default temperature, so none is sent). Replies are cached under `cache/review/`
like eval's cache, so a rerun costs nothing and gives the same review. `MOCK=1` runs offline. Anthropic spend
is not shown by `scripts/budget`, so use the token totals the run prints.

## How a family plugs in (`contracts/FAMILY.md`)
A package `gen/<family>/` with `FAMILY, VERSION, TEMPLATES, REFERENCES, build, solve_independent, RejectSeed`. The
registry imports every such package and skips a broken one with a warning. To pass every check, `build()` must:
1. write `data/<task_id>.json` **before** the PNG, with the same `task_id` and `seed` as the record;
2. render with `factory.render`: `new_figure(w_px, h_px)`, then `save_png(fig, path)` (Agg, dpi 100, no
   metadata or timestamps, returns the SHA-256). Fixed size, no `bbox_inches="tight"`, bundled DejaVu fonts;
3. return `layout.texts` (use `text_boxes(fig)`: every drawn label as `[x0, y0, x1, y1, fontsize_px]`, image pixels,
   origin top-left) and **at least one** `layout.probes` entry (`to_pixels(ax, x, y)` gives the pixel of a data
   point). Probe things that carry the answer: a bar's fill, a breaker's open/closed symbol, a contour colour.
   Optional `"r": 1` accepts the best pixel in a 3x3 neighbourhood (antialiased lines);
4. state any tolerance in the question; return `steps`.

`solve_independent(data, template)` receives the **whole data JSON file** (`{"task_id", "seed", "params", "data",
...}`). If it raises and the file has a `data` dict, the validator retries with that inner dict and says so.
The factory sets `seed`, `generator_version`, `question_type` (`family.template`), `family`, `template`,
`difficulty`, `references` (from `REFERENCES[template]` if the record has none), and the image and data hashes.

`gen/example/` is the smallest family that passes everything (`TEST_ONLY = True`, so `fresh` only uses it when
named). Tests: `uv run python -m unittest discover -s tests -t .` (part of `scripts/check`).
