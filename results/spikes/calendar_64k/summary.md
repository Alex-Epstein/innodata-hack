# Calendar L3 on claude-haiku-5.5 at max_tokens 64000 (directive #26, Nov 14, 11:32 to 11:36)

Only the three L3 calendar tasks, only Haiku, through `eval/client.py` (temperature 0, reasoning effort high,
max_tokens 64000). Command: `uv run python results/spikes/calendar_64k/run.py`. Per-call results: `results.json`.

| Task | Truth | 16000 | 32000 | 64000 | Tokens used at 64000 | Seconds |
|---|---|---|---|---|---|---|
| L3_s1 | Fri 12:15 | cut off | cut off | Fri 12:15 (right) | 29603 | 114.98 |
| L3_s2 | Thu 13:30 | cut off | cut off | Wed 13:15 (wrong) | 58861 | 229.41 |
| L3_s3 | Thu 12:15 | Thu 12:15 (right) | Wed 12:00 (wrong) | Thu 12:15 (right) | 15285 | 58.74 |

- **Haiku finishes at 64000:** all three replies ended with `finish_reason: stop`. Score 2 of 3.
- **Little headroom:** L3_s2 used 58861 of 64000 tokens. A denser task could still be cut off.
- **Odd:** L3_s1 was cut off at 32000 but finished here with 29603 tokens, so Haiku's reasoning length varies from
  run to run on the same input.
- Cost: $0.0525563 for 3 calls. `scripts/budget` before: $0.31 used; after: $0.34 used (other sessions were running).
- With gpt-6-luna at 3 of 3 on L3 (`../calendar_32k/`), the calendar's hardest level is not hard for either model.
