# Notes: insights, limitations, weird model behavior (slide 5 and the README come from here)


- 10:54 · eval (#2) · On the 6-load power spike image, `openai/gpt-6-luna` reasoned correctly but wrote
  `FINAL ANSWER: [3, 4]` for loads L3 and L4. Strict scoring marks that wrong. To keep failures about reasoning
  and not format, every question should show one example answer in the exact expected form (e.g. `L3, L4`).
  Source: one call per model through `eval.client`, cached under `cache/eval/`; not a reported result.
- 11:00 · eval · Same image and prompt with max_tokens 32000 instead of 16000: `openai/gpt-6-luna` wrote
  `["L3","L4"]` this time (it wrote `[3, 4]` before). Its answer format is not stable across runs even at
  temperature 0, which is why the disk cache matters: one stored reply per (model, prompt, image, settings).
