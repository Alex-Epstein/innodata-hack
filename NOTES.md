# Notes: insights, limitations, weird model behavior (slide 5 and the README come from here)


- 10:54 · eval (#2) · On the 6-load power spike image, `openai/gpt-6-luna` reasoned correctly but wrote
  `FINAL ANSWER: [3, 4]` for loads L3 and L4. Strict scoring marks that wrong. To keep failures about reasoning
  and not format, every question should show one example answer in the exact expected form (e.g. `L3, L4`).
  Source: one call per model through `eval.client`, cached under `cache/eval/`; not a reported result.
