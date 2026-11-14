# Calendar spike rerun at max_tokens 32000 (Nov 14, 11:05)

Same 9 images and questions as `../calendar/` (which ran at max_tokens 16000). Calls go through `eval/client.py`:
temperature 0, reasoning effort high, max_tokens 32000. Command: `uv run python results/spikes/calendar_32k/run.py`.
Per-call results: `results.json`. Raw requests and replies: `raw/`. Cost: $0.07273692 for 18 calls.

## Results (correct / wrong / cut off by `length`)
| Level | claude-haiku-5.5 at 16000 | claude-haiku-5.5 at 32000 | gpt-6-luna at 16000 | gpt-6-luna at 32000 |
|---|---|---|---|---|
| L1: 3 people, 30 min | 3 / 0 / 0 | 2 / 1 / 0 | 3 / 0 / 0 | 3 / 0 / 0 |
| L2: 4 people, 45 min, near misses | 2 / 1 / 0 | 3 / 0 / 0 | 3 / 0 / 0 | 3 / 0 / 0 |
| L3: 6 people, 60 min, dense, near misses | 1 / 0 / 2 | 0 / 1 / 2 | 1 / 2 / 0 | 3 / 0 / 0 |

## What this shows
- **gpt-6-luna got all 9 right.** Its two L3 misses in the first run (L3_s1, L3_s2) are both correct here.
- **claude-haiku-5.5 is still cut off on L3_s1 and L3_s2.** It spent all 32000 tokens on reasoning and returned no
  text (`finish_reason: length`). These are incomplete replies, not wrong answers, so they cannot be reported.
- **5 of 18 results changed between the two runs** with the same image and question: L1_s2 haiku (right → wrong),
  L2_s1 haiku (wrong → right), L3_s3 haiku (right → wrong), L3_s1 luna (wrong → right), L3_s2 luna (wrong → right).
  The only setting that differs is max_tokens. Either the models are not repeatable at temperature 0, or the
  token limit changes how much they reason. Three tasks per level is too few to tell a difficulty trend from this noise.
- **Not shown by this run:** that the calendar gets harder with level for either model. Counting complete replies
  only, haiku is 5 of 7 and luna is 9 of 9.
