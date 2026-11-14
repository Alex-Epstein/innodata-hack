# Notes: insights, limitations, weird model behavior (slide 5 and the README come from here)


- 10:54 · eval (#2) · On the 6-load power spike image, `openai/gpt-6-luna` reasoned correctly but wrote
  `FINAL ANSWER: [3, 4]` for loads L3 and L4. Strict scoring marks that wrong. To keep failures about reasoning
  and not format, every question should show one example answer in the exact expected form (e.g. `L3, L4`).
  Source: one call per model through `eval.client`, cached under `cache/eval/`; not a reported result.
- 11:00 · eval · Same image and prompt with max_tokens 32000 instead of 16000: `openai/gpt-6-luna` wrote
  `["L3","L4"]` this time (it wrote `[3, 4]` before). Its answer format is not stable across runs even at
  temperature 0, which is why the disk cache matters: one stored reply per (model, prompt, image, settings).
- 11:08 · calendar rerun · At max_tokens 32000, `anthropic/claude-haiku-5.5` still returned no text on 2 of the 3
  hardest calendar images (all 32000 tokens went to reasoning). `openai/gpt-6-luna` got all 9 right. 5 of 18
  results differ from the 16000 run on identical images and questions, so single runs with 3 tasks per level are
  noise-prone. Source: `results/spikes/calendar_32k/summary.md`.
- 12:03 · topo missions (#29) · The same 9 maps asked in plain wording and then as missions gave different scores:
  Naismith hike time 2/6 plain, 6/6 as "hiker vs sunset"; campsite rules 6/6 plain, 4/6 as "base camp". Same
  terrain, same marks, same chain. With 3 tasks per type these numbers are noise and must not be quoted as
  difficulty. Source: `results/spikes/missions/summary.md`.
- 12:03 · topo missions (#29) · The step that breaks is tracing a line across many contours (adding up ascent,
  following water downhill, counting crossings). Reading one elevation, using the scale bar and the arithmetic
  are fine: trail length was read as 2.44 km against 2.439 km true. A wide tolerance (±10 min is ±50 m of
  ascent) or a 3 or 4 way choice hides the miss. Wildfire "which trail stays below the fire" was 6/6 (too easy);
  `openai/gpt-6-luna` got line of sight 6/6. Source: same file.
- 12:03 · topo missions (#29) · Limitation: line-of-sight tasks in the spike have visible hikers clearing the
  ground by only 25.9 to 28.4 m, about one contour line, which is too thin for a person. A real generator should
  require 60 m or more. The hike-time search also took minutes for 3 tasks, too slow for a live seed as written.
