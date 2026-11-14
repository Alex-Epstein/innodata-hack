# gen/power: main-tie-main switchgear single-line diagram (owner: WindHurtLZ, issue #47)

A plug-in per `contracts/FAMILY.md`, ported from `results/spikes/power_v2/gen.py`. A 480 V main-tie-main
switchgear drawn as found: two utility services through T1/T2 (kVA, %Z), a standby generator G1 (rating on the
drawing), buses 1, 2 and E, sub-buses 1B/2B/EB, ANSI 52 breakers (filled = closed, hollow = open), alternate feeds
routed through a cable channel that cross other feeders without junction dots, a legend, notes and a title block.
References: IEEE Std 141 (Red Book), IEEE Std 315 / ANSI C37.2.

## Templates (all state their procedure step by step; answers exact)
| Template | Question | Answer |
|---|---|---|
| `trip` | Utility 2 out, G1 running. 52-M1 trips; the operator sheds largest-first to G1's drawn rating, then closes tie 52-T. Total kW of loads running before and not running at the end | integer kW |
| `dbl` | 52-M2 and a feeder breaker trip together. Which running loads lose power | load tags, left to right |
| `iso` | Isolate a sub-bus (fed through its crossing alternate feed, PV-1 back-feeds it) with the fewest breakers without dropping other running loads | breaker IDs, sorted |

Difficulty 1 to 3 = number of alternate feeds crossing the sheet (1, 2 or 3). Every task carries the cross-feed trap:
loads whose fate contradicts where they are drawn (trip, dbl), or a work bus fed from across the sheet (iso).
Two solvers: DFS reachability in `build`, union-find in `solve_independent`. Probes check every breaker's fill.

## Pilots (difficulty 3, 10 seeds each, max_tokens 64000, all finish_reason stop)
| Version | Change | trip H / L | dbl H / L | iso H / L | Spend |
|---|---|---|---|---|---|
| 1.0.0 | port + clearer wording + random skeleton + tight G1 rating | 10/10 · 9/10 | 6/10 · 8/10 | 7/10 · 9/10 | $0.11 |
| **1.1.0 (current)** | require the cross-feed trap in every task | 9/10 · 9/10 | 6/10 · 7/10 | 7/10 · 7/10 | $0.08 |
| 1.2.0 (reverted) | 3+ traps, bigger answer sets | 8/10 · 9/10 | 9/10 · 10/10 | 9/9 · 7/9 | $0.07 |

**No template meets the keep rule (a model at 5/10 or lower).** The spike's lower scores came partly from ambiguous
wording; with the wording fixed, both models trace these diagrams well. Where they break (v1.1.0):
- `dbl`: they miss loads that are lost through a closed alternate feed crossing the sheet (5 of 7 misses), plus one
  transcription error (Luna wrote PR-3 for RP-3).
- `iso`: over-isolation, adding the work bus's own (already irrelevant) normal feeder (5 of 6); one miss of the PV
  back-feed breaker.
- `trip`: one sum off by 13 kW (Luna), one answer of 0 (Haiku).

Only the v1.1.0 task sets are in `tasks/pilot_power_*`; v1.0.0 and v1.2.0 results (with reference answers and raw
replies) are in `results/pilot1_power_*` and `results/pilot3_power_*`.

```bash
uv run python -m factory generate --family power --template dbl --difficulty 3 --seeds 0-9 --out tasks/pilot_power_dbl
uv run python -m factory validate --tasks tasks/pilot_power_dbl
uv run python -m factory eval --tasks tasks/pilot_power_dbl --out results/pilot2_power_dbl
```
