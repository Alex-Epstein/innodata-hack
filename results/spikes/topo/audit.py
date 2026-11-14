"""Fairness audit of the L3 trails: how close is the first/last contour crossing to a trail end marker?

    uv run python results/spikes/topo/audit.py

An end marker is about 40 m wide on the map, so a crossing within 20 m of an end can sit under the marker.
"""
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import gen  # noqa: E402

for line in (HERE / "tasks" / "tasks.jsonl").read_text().splitlines():
    t = json.loads(line)
    if t["difficulty"] != 3:
        continue
    d = json.loads((HERE / "tasks" / t["data"]).read_text())["data"]
    p = gen.densify(d["trails"][0]["pts"])
    z = gen.elev(d, p[:, 0], p[:, 1])
    cross = np.where(np.diff(np.floor(z / gen.CI)) != 0)[0]
    print(t["task_id"], "answer", t["answer"], "crossings", len(cross), "trail length m", len(p) - 1,
          "first crossing m from S", int(cross[0]), "last crossing m from E", int(len(p) - 1 - cross[-1]),
          "closest two crossings m", int(np.diff(cross).min()),
          "elev S", round(float(z[0]), 1), "elev E", round(float(z[-1]), 1))
