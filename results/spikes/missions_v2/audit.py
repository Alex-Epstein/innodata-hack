"""Re-derive every answer from tasks/data/*.json alone, with different numerics than gen.py.

    cd /Users/alex/Desktop/innodata-hack && uv run python <work>/audit.py

flood: RK4 fall line, 1 m steps, analytic-free finite differences (e = 0.25 m); first 50 m circle entered.
los:   terrain profile every 0.5 m; min clearance away from the ends.
fire:  each trail sampled every 0.5 m; max elevation vs F's elevation minus 40 m.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from gen import elev, W, H  # noqa: E402  (the field itself is the data; everything else is recomputed here)


def fall_line(d, p, step=1.0, n=8000):
    def dirn(q):
        e = 0.25
        g = np.array([(elev(d, q[0] + e, q[1]) - elev(d, q[0] - e, q[1])) / (2 * e),
                      (elev(d, q[0], q[1] + e) - elev(d, q[0], q[1] - e)) / (2 * e)])
        return -g / max(np.linalg.norm(g), 1e-12)
    pts = [np.array(p, float)]
    for _ in range(n):
        q = pts[-1]
        if not (0 <= q[0] <= W and 0 <= q[1] <= H):
            break
        k1 = dirn(q); k2 = dirn(q + step / 2 * k1); k3 = dirn(q + step / 2 * k2); k4 = dirn(q + step * k3)
        pts.append(q + step / 6 * (k1 + 2 * k2 + 2 * k3 + k4))
    return np.array(pts)


def audit(rec):
    d, tpl = rec["data"], rec["params"]["template"]
    if tpl == "flood":
        D = d["dam"]
        start = np.array([D["x"], D["y"]]) + 30 * np.array(D["flow"])
        P = fall_line(d, start)
        C = np.array([[c["x"], c["y"]] for c in d["campsites"]])
        dd = np.linalg.norm(P[:, None] - C[None], axis=2)
        k = int(np.argmax((dd <= 50).any(1))) if (dd <= 50).any() else None
        got = d["campsites"][int(np.argmin(dd[k]))]["name"] if k is not None else "none"
        return got, f"route {k} m"
    if tpl == "los":
        R, Hk = d["spotter"], d["hiker"]
        a, b = np.array([R["x"], R["y"]]), np.array([Hk["x"], Hk["y"]])
        L = float(np.linalg.norm(b - a))
        t = np.linspace(0, 1, int(L / 0.5) + 1)
        p = a + t[:, None] * (b - a)
        z = elev(d, p[:, 0], p[:, 1])
        line = (elev(d, *a) + 2) + t * ((elev(d, *b) + 2) - (elev(d, *a) + 2))
        c = (line - z)[1:-1]
        return ("yes" if c.min() > 0 else "no"), f"min clearance (whole line) {c.min():.1f} m"
    F = d["fire"]
    T = float(elev(d, F["x"], F["y"])) - 40
    safe = []
    notes = []
    for tr in d["mission_trails"]:
        pts = np.array(tr["pts"])
        seg = [a + np.linspace(0, 1, int(np.linalg.norm(b - a) / 0.5) + 2)[:, None] * (b - a) for a, b in zip(pts[:-1], pts[1:])]
        q = np.vstack(seg)
        zmax = float(elev(d, q[:, 0], q[:, 1]).max())
        notes.append(f"{tr['name']} max {zmax:.1f} vs {T:.1f}")
        if zmax <= T:
            safe.append(tr["name"])
    got = safe[0] if len(safe) == 1 else ("neither" if not safe else "both")
    return got, "; ".join(notes)


ok = True
for f in sorted((HERE / "tasks" / "data").glob("*.json")):
    rec = json.loads(f.read_text())
    got, note = audit(rec)
    flag = "OK " if got == rec["answer"] else "BAD"
    ok &= got == rec["answer"]
    print(flag, rec["task_id"], "answer", rec["answer"], "audit", got, "|", note)
print("all agree" if ok else "MISMATCH")
