# eval/: the only code that calls the models

| File | What it does |
|---|---|
| `client.py` | One OpenRouter call: fixed settings (temperature 0, reasoning effort high, max_tokens 32000), disk cache in `cache/eval/` keyed by hash(model, prompt, image hash, settings), retries on 429/5xx/timeouts, key from `OPENROUTER_API_KEY`. `MOCK=1` returns a canned reply with no network call. |
| `scoring.py` | `PROMPT_TEMPLATE` (question + "end with `FINAL ANSWER:`"), `parse_final_answer`, `score` per `answer_type`. |
| `run.py` | Task folder → `responses.csv`, `run_config.json`, `raw/`, `summary.json`. |
| `test_eval.py` | `uv run python -m unittest eval.test_eval` (no network). |

```bash
# one question, both models
uv run python -m eval.client --image X.png --question "..."
# a whole task folder
uv run python -m eval.run --tasks tasks/final --out results/final
# no image sent (the "needs the image" check); keep it out of the reported folder
uv run python -m eval.run --tasks tasks/final --out results/extra/blind --blind
```

From other code: `from eval import client, scoring, run`, then `client.call(model, prompt, image_path)`,
`client.reply(record)`, `run.evaluate(tasks_dir, out_dir)`.

Raw logs: `run.py` writes `client.for_raw_log(record)` to `raw/`. It replaces opaque provider blobs (encrypted
reasoning data, reasoning signatures) with their length and SHA-256, because GitHub push protection mistook one
for an API key. Reply text, readable reasoning, `finish_reason` and usage are untouched. Use the same function
in any script that commits raw replies.

Scoring rules generators should know:
- `sequence` answers are compared in order. Add `"ordered": false` to the task if the answer is a set.
- A reply with no `FINAL ANSWER:` line, or one cut off or failed, is never scored as correct; cut-off and failed
  rows get `error` set and an empty `correct`, and `run` exits non-zero so the evaluation is rerun.
- Labels and list items ignore case, punctuation and spacing, nothing else: `3` does not match `L3`.
