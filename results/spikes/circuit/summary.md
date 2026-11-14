# Spike: resistor-schematic "equivalent resistance" task family

## Result: both models got all 18 answers right

| Level | claude-haiku-5.5 | gpt-6-luna |
|---|---|---|
| L1 (4 R, one parallel pair) | 3/3 | 3/3 |
| L2 (6-7 R, ladder / hidden parallel) | 3/3 | 3/3 |
| L3 (10 R, 3-deep nesting + short or dead end) | 3/3 | 3/3 |

- 18 calls total (budget 24). No parameter was rejected: temperature 0, max_tokens 16000, reasoning effort high and usage include all went through for both models. No 429/5xx retries.
- Total cost: **$0.0164** (Haiku $0.0109, GPT $0.0055). Every finish_reason was `stop`.
- Reasoning tokens: L1 about 70-250, L3 about 900-1600. The outlier was Haiku on L3_s2 (11.3k reasoning tokens, $0.006). It noticed the shorting wire, then gave up on series/parallel reduction and ran a full nodal analysis, which still came out right (658.5).

## Wrong answers
None outside ±1%. One near miss:
- gpt-6-luna on L1_s1 answered 8257.3 against a true 8242.3 (0.18% off, so it counts as correct). It read every value right (18‖100 = 15.254) and then made an addition slip: 15.254 + 27 + 8200 written as 8257.3. That was arithmetic, not perception. The ±1% tolerance hides small slips like this when one resistor dominates.

Neither model misread a value, missed a short, ignored the dead end incorrectly, or got the topology wrong on any task.

## Images
- L2 example: /private/tmp/claude-501/-Users-alex--claude-spares-spare-I10rOj/c178a8bb-854d-40a6-b78d-29c596d4221d/scratchpad/spike-circuit/img/L2_s2.png (looks like a bridge but has a missing arm, so it reduces as (R2 + R3‖R4) ‖ R5)
- L3 example: /private/tmp/claude-501/-Users-alex--claude-spares-spare-I10rOj/c178a8bb-854d-40a6-b78d-29c596d4221d/scratchpad/spike-circuit/img/L3_s0.png (R9 is shorted by a bypass wire drawn under it)
- Also see L3_s1.png (dead-end R8 runs to an open terminal C) and L3_s2.png (R7 is shorted by a plain wire rung).

## How it was built
- `gen.py`: each circuit is a geometric netlist of resistor and wire segments on a grid. Wires are merged into electrical nodes with union-find. Ground truth comes from two independent methods that agreed to 1e-6 on all 9 tasks: a graph reduction (drop self-loops and dead ends, merge parallel edges, merge series edges) using exact Fractions, and a numpy nodal solve. Values are random E12 × {1, 10, 100}. Images are rendered with schemdraw and padded to 1400x1000.
- Caveat: topology comes from 3 hand-made templates per level, and only the values change with the seed. L3 uses one ladder skeleton with 3 different traps.
- `run.py` does the OpenRouter calls. Raw JSON for every response is in `raw/`. Parsed results are in `results.json` and the ground truth is in `tasks.json`.

## Judgment
- **Fair to a student?** Yes. L3 is a standard ladder: shorted or dead-end part, then (R5‖R6) + R7 + R8, ‖ R4, + R3, ‖ R2, + R1 + R_last. A careful student with a calculator could do it in about 3 to 4 minutes, so "under 3 minutes" is borderline. It's four or five reductions with awkward numbers. Spotting the trap takes seconds once you know to look for it.
- **Textbook look?** Mostly. It reads like a clean intro circuits figure (Hambley or Irwin style ladder, filled junction dots, open-circle terminals). Two things give it away: values are written as "4700 Ω" where a textbook would write "4.7 kΩ", and the grid is very regular.
- **Verdict for the team:** as built, this family does not stump either model, even at L3, and it costs almost nothing to run. Both models read clean schemdraw labels perfectly and do the algebra fine. Haiku will even fall back to nodal analysis when reduction gets confusing. To get failures, the difficulty probably has to come from perception rather than circuit theory: wires that cross with and without junction dots, diagonal or bridge layouts that need Y-Δ, kΩ/MΩ prefixes mixed with Ω, much denser networks (15+ resistors), or hand-drawn style rendering. Each of those makes it harder to keep the task fair to a student. Based on this spike I would not pick this family unless one of those harder variants is tested first.
