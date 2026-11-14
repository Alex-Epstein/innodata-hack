# Contract: an image family is one Python package `gen/<family>/`

The core (`factory/`, Alex) and the validator (`validate/`, Alex) only talk to families through this interface,
so families (`gen/topo/` tech-cosmos, `gen/power/` WindHurtLZ) can be built in parallel. Change only with a line in
`docs/DECISIONS.md`.

```python
# gen/<family>/__init__.py
FAMILY = "topo"                       # short name, used in task_id: f"{FAMILY}-{template}-{seed:06d}"
VERSION = "topo-1.0.0"                # bump when output for the same seed changes
TEMPLATES = ["flood", "sight", ...]   # question templates this family supports
REFERENCES = {"flood": ["USGS 7.5-minute quadrangle (US Topo) conventions", "..."], ...}

def build(seed: int, template: str, difficulty: int, out_dir: Path) -> dict:
    """Deterministic: same (seed, template, difficulty) -> byte-identical files.
    1. sample the structured data from numpy.random.default_rng(seed) (no global randomness)
    2. write out_dir/data/<task_id>.json BEFORE rendering
    3. render out_dir/images/<task_id>.png from that data only (matplotlib Agg, fixed size and dpi,
       savefig(..., metadata={"Software": None}))
    4. compute the answer from the data
    Return the task record (contracts/SCHEMA.md fields) plus:
      "steps":   the intermediate facts of the reasoning chain (for failure analysis)
      "overlay": geometry for the demo's truth overlay (optional)
      "layout":  {"texts": [[x0,y0,x1,y1,fontsize_px], ...],          # every drawn label, in image pixels
                  "probes": [{"xy": [x, y], "expect": "#rrggbb", "tol": 40, "what": "breaker CB-07 open"}, ...]}
                 probes are pixels the validator samples to confirm the image shows the data
    Raise RejectSeed("why") if this seed can't make a fair task (ties, near-misses inside tolerance, cramped labels)."""

def solve_independent(data: dict, template: str):
    """A SECOND way to compute the answer from the data JSON alone (different algorithm or library from build()).
    The validator requires it to equal build()'s answer."""

class RejectSeed(Exception): ...
```

**Difficulty:** `difficulty` 1 to 3 (easy, medium, hard), mapped inside the family to concrete knobs (contour count, crossing
density, number of loads...). The final 10 use the hardest level that stays fair.

**Questions:** chained reasoning (AGENTS.md), all rules and constants stated in the question, the exact answer format spelled
out. The eval prompt adds the `FINAL ANSWER:` instruction itself (`eval/scoring.py`).
