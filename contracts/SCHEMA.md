# Contracts: folders and file formats (everyone builds against this)

The required parts come from the organizers' brief and their `check_submission.py`. Extra fields are ours.
Change this file only with a line in `docs/DECISIONS.md`.

## Folder layout
```
gen/<family>/        generators: data → PNG + question + answer (one folder per image family)
validate/            every check on a task (required folder name)
eval/                model client, prompt, answer parsing, scoring, report (required folder name)
tasks/final/         the 10 reported tasks: tasks.jsonl, images/, data/
tasks/pilot1/ ...    pilot task sets
results/final/       responses.csv, run_config.json, raw/  (the reported evaluation)
results/pilot1/ ...  pilot results (summarized in the README "Pilot results" section)
results/extra/       ablations and extra models, never mixed into reported numbers
Dockerfile           at the root; builds the whole pipeline
README.md            required sections, see docs/BRIEF.md
```

## Per-task data: `tasks/<set>/data/<task_id>.json`
Written **before** rendering. The image is a pure function of this file.
```json
{ "task_id": "cal-000123", "family": "calendar", "seed": 123, "generator_version": "cal-0.1.0",
  "params": { "...": "difficulty knobs" },
  "data": { "...": "the structured content the image is drawn from" },
  "references": ["Real source this image imitates, e.g. Outlook Scheduling Assistant"] }
```

## `tasks/<set>/tasks.jsonl` (one JSON object per line)
| Field | Required | Notes |
|---|---|---|
| `task_id` | yes | unique; `<family>-<seed, 6 digits>` |
| `image` | yes | path relative to the task folder, e.g. `images/cal-000123.png` |
| `question` | yes | exactly as sent to the model, including the answer-format instruction and any tolerance |
| `answer` | yes | number, label, option letter, or JSON list |
| `answer_type` | yes | `number`, `integer`, `label`, `multiple_choice`, or `sequence` |
| `tolerance_rel` / `tolerance_abs` | for non-integer numbers | exactly one; the same tolerance is stated in the question |
| `options` | for multiple_choice | in letter order |
| `seed` | ours (checker looks for it) | |
| `generator_version` | ours (checker looks for it) | |
| `question_type` | ours (needed in results) | the question template, e.g. `cal.earliest_common_slot` |
| `family` | ours | |
| `difficulty` | ours | knob values or a level |
| `data` | ours | path to the data JSON |
| `checks` | ours (checker looks for it) | `{"name": true/false, ...}` from `validate/` |
| `references` | ours | 1 or 2 real sources this image is based on |

## `results/<set>/responses.csv` (one row per model per task)
Columns (all required): `model, task_id, status, parsed, question_type, response, ref_answer, correct, finish_reason, error`
- `model`: exact OpenRouter ID · `status`: `ok` · `correct`: 1 or 0 · `finish_reason`: `stop` · `error`: empty
- `ref_answer` must equal the task's `answer`. Every reported row must be complete: no API error, no truncation.

## `results/<set>/run_config.json`
Model IDs, temperature (0), reasoning effort (high), max_tokens, the prompt template, timestamp, git commit.

## `results/<set>/raw/`
One file per call: the full request (minus the image bytes and keys) and the full raw response.
