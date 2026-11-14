# Spike E (#16): Gantt chart, results

Generator `gen.py` (Microsoft Project look: task table + dated timescale, finish-to-start link lines, weekends and
4 company holidays shaded). Answers from a CPM forward/backward pass; every zero-slack answer is re-checked by
brute force (slip each task 1 day, see if the finish moves). Eval: `uv run python -m eval.run --tasks
results/spikes/gantt/tasks --out results/spikes/gantt/results` (temperature 0, reasoning high, max_tokens 32000).

| Level | Question | claude-haiku-5.5 | gpt-6-luna |
|---|---|---|---|
| L1: 6 tasks, durations + predecessors shown | finish date | 3/3 | 3/3 |
| L2: 10 tasks, 2 paths | finish if task K slips N days (critical / partly absorbed / fully absorbed) | 3/3 | 3/3 |
| L3: 16 tasks, bars and arrows only | zero-slack task list (x2), finish after two slips (x1) | 3/3 | 2/3 |
| **Total** | | **9/9** | **8/9** |

All 18 replies complete (`finish_reason` stop). Spend: OpenRouter usage $0.2644 → $0.3177 ($0.053, including
calls repeated after a crash; the final run reported $0.0125 new spend).

## The one failure
- `gantt-000301` (L3, zero slack), gpt-6-luna answered `1,2,3,4,5,6,7,8,11,12,13,14,16`; truth
  `1,3,4,8,12,13,14,16`. It marked 5 tasks with slack as critical (over-inclusion); its reply is 208 characters, so
  the reasoning is not visible.

## Verdict
**Too easy, like circuits.** Both models read bar lengths against the day grid, followed the link lines, skipped
weekends and holidays, and did the schedule arithmetic correctly, even at L3 with no durations or predecessors
shown. No accuracy drop across levels (Haiku 100% at every level).

## Honest notes
- Image L3: `tasks/images/gantt-000301.png`. A careful person can solve L3 but it takes longer than 2 to 3
  minutes (counting bar lengths for 16 tasks). Looks close to an MS Project Gantt view; resource names are random.
- Bug found (eval, not fixed here): on a Windows machine with a non-UTF-8 locale (cp932), `eval/client.py`
  writes and reads cache files with the default encoding and crashes on characters like "–". Workaround:
  `PYTHONUTF8=1`. Fix: `encoding="utf-8"` in `read_text`/`write_text`.
