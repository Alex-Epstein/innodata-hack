"""Issue #29: multi-step reasoning questions on the topo map (read several facts -> apply a rule -> conclude).

    uv run python results/spikes/multistep/gen.py

Reuses the terrain, decorations and renderer of results/spikes/topo/gen.py. Three templates, 3 seeds each:

  topo.line_of_sight   Which of four hikers can a lookout see? For each: read both elevations, find the
                       highest ground between, compare with the straight sight line. Answer: a set of letters.
  topo.hike_time       Naismith's rule on a marked trail: measure its length with the scale bar, add up every
                       uphill stretch from the contours, combine. Answer: minutes, accepted within 10.
  topo.campsite        Pick the one site of four that meets three rules (elevation limit, distance to a
                       stream, contour spacing). Each wrong site fails exactly one rule. Answer: a site name.

Every answer is computed from the analytic elevation field in the data, then recomputed a second way from the
10 m grid; a draw where the two disagree, or where a margin is thin, is thrown away. The intermediate facts
are saved in each task's `steps` field so we can see which step a model got wrong.
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "topo"))
import gen as topo  # noqa: E402  (results/spikes/topo/gen.py)

OUT = HERE / "tasks"
VERSION = "topo-multistep-0.1"
W, H, STEP, CI = topo.W, topo.H, topo.STEP, topo.CI
INTRO = topo.INTRO


# ---------------------------------------------------------------------------------------------- helpers
def z_at(d, p):
    return float(topo.elev(d, p[0], p[1]))


def z_grid(Z, x, y):
    """Second, independent elevation: bilinear interpolation of the 10 m grid (not the analytic field)."""
    x, y = np.asarray(x, float) / STEP, np.asarray(y, float) / STEP
    i, j = np.clip(np.floor(x).astype(int), 0, Z.shape[1] - 2), np.clip(np.floor(y).astype(int), 0, Z.shape[0] - 2)
    fx, fy = x - i, y - j
    return (Z[j, i] * (1 - fx) * (1 - fy) + Z[j, i + 1] * fx * (1 - fy)
            + Z[j + 1, i] * (1 - fx) * fy + Z[j + 1, i + 1] * fx * fy)


def clear_of_labels(d, q, r=210):
    """q is at least r meters from every printed label, so a marker never hides or is hidden by one."""
    labels = [[s["x"], s["y"]] for s in d["spot_heights"]] + [[l["x"], l["y"]] for l in d["index_labels"]]
    lines = [t["pts"] for t in d["trails"]] + [s["pts"] for s in d["streams"]]
    return all(math.dist(q, o) >= r for o in labels) and all(topo.dist_to_poly(q, ln) >= 130 for ln in lines)


def base_map(seed, need_stream=False):
    """A decorated map (terrain, spot heights, index labels, streams) with no task marks on it yet."""
    for k in range(40):
        got = topo.sample(seed * 1000 + k, 1)
        if got and (not need_stream or got[0]["streams"]):
            d = got[0]
            d["points"] = []
            return d
    raise SystemExit(f"seed {seed}: no base map")


def pt(name, p, shape="dot", **kw):
    return {"name": name, "x": round(float(p[0]), 1), "y": round(float(p[1]), 1), "shape": shape, **kw}


# ---------------------------------------------------------------------------------------------- 1. line of sight
def sight(zfun, a, b):
    """Clearance of the straight line a -> b over the ground: min of (sight line - terrain), middle 84%."""
    n = max(50, int(math.dist(a, b)))
    s = np.linspace(0.08, 0.92, n)
    x, y = a[0] + (b[0] - a[0]) * s, a[1] + (b[1] - a[1]) * s
    ground = zfun(x, y)
    za, zb = float(zfun(a[0], a[1])), float(zfun(b[0], b[1]))
    gap = za + (zb - za) * s - ground
    k = int(np.argmin(gap))
    return {"clearance_m": round(float(gap[k]), 1), "tightest_x": round(float(x[k]), 1), "tightest_y": round(float(y[k]), 1),
            "ground_there_m": round(float(ground[k]), 1), "sight_line_there_m": round(float(za + (zb - za) * s[k]), 1)}


def line_of_sight(seed):
    rng = np.random.default_rng(seed)
    for _ in range(60):
        d = base_map(int(rng.integers(1, 10 ** 6)))
        X, Y, Z = topo.grid(d)
        high = np.argwhere(Z >= np.quantile(Z, 0.85))
        tower = None
        for j, i in high[rng.permutation(len(high))[:300]]:
            q = [float(X[j, i]), float(Y[j, i])]
            if topo.inside(q, 350) and clear_of_labels(d, q, 240):
                tower = q
                break
        if tower is None:
            continue
        analytic = lambda x, y: topo.elev(d, x, y)
        gridded = lambda x, y: z_grid(Z, x, y)
        seen, hidden = [], []
        for _ in range(4000):
            q = [float(rng.uniform(300, W - 300)), float(rng.uniform(300, H - 300))]
            if not 900 <= math.dist(q, tower) <= 2900 or z_at(d, q) > z_at(d, tower) - 40 or not clear_of_labels(d, q):
                continue
            if any(math.dist(q, o["p"]) < 420 for o in seen + hidden):
                continue
            a, g = sight(analytic, tower, q), sight(gridded, tower, q)
            if abs(a["clearance_m"]) < 25 or (a["clearance_m"] > 0) != (g["clearance_m"] > 0):
                continue                                     # thin margin, or the two methods disagree
            (seen if a["clearance_m"] > 0 else hidden).append({"p": q, "analytic": a, "grid": g})
        n_seen = int(rng.integers(1, 4))
        if len(seen) < n_seen or len(hidden) < 4 - n_seen:
            continue
        chosen = seen[:n_seen] + hidden[:4 - n_seen]
        chosen = [chosen[k] for k in rng.permutation(4)]
        d["points"] = [pt("T", tower, "square")] + [pt(n, c["p"]) for n, c in zip("ABCD", chosen)]
        steps = [{"hiker": n, "tower_elev_m": round(z_at(d, tower), 1), "hiker_elev_m": round(z_at(d, c["p"]), 1),
                  **c["analytic"], "visible": c["analytic"]["clearance_m"] > 0} for n, c in zip("ABCD", chosen)]
        answer = [s["hiker"] for s in steps if s["visible"]]
        checks = {"analytic_field_and_grid_agree": all((c["analytic"]["clearance_m"] > 0) == (c["grid"]["clearance_m"] > 0)
                                                       for c in chosen),
                  "clearance_margin_at_least_25m": all(abs(s["clearance_m"]) >= 25 for s in steps),
                  "some_visible_some_hidden": 0 < len(answer) < 4}
        q = INTRO + ("A fire lookout stands at the magenta square T. Four hikers are at the magenta points A, B, C and D. "
                     "A hiker is hidden when the ground somewhere between rises above the straight sight line from T "
                     "to that hiker. Ignore trees, eye height and the curvature of the Earth. Which hikers can the "
                     "lookout see? Answer with their letters separated by commas, for example A, C.")
        return d, {"question": q, "answer": answer, "answer_type": "sequence", "ordered": False,
                   "question_type": "topo.line_of_sight", "steps": steps, "checks": checks}
    raise SystemExit(f"line_of_sight seed {seed}: nothing fair found")


# ---------------------------------------------------------------------------------------------- 2. hike time
def climb_and_length(zfun, pts):
    p = topo.densify(pts)
    z = zfun(p[:, 0], p[:, 1])
    dz = np.diff(z)
    length = float(np.sqrt((np.diff(p, axis=0) ** 2).sum(1)).sum())
    return length, float(dz[dz > 0].sum()), z


def hike_time(seed):
    rng = np.random.default_rng(seed)
    minutes = lambda length, climb: 60 * length / 4000 + 60 * climb / 300
    for _ in range(400):
        d = base_map(int(rng.integers(1, 10 ** 6)))
        d["trails"] = []
        X, Y, Z = topo.grid(d)
        pts = topo.random_trail(rng, legs=int(rng.integers(2, 4)))
        if pts is None or not topo.trail_is_fair(d, pts):
            continue
        if not all(clear_of_labels(d, q, 190) for q in topo.densify(pts, 40)):
            continue
        length, climb, z = climb_and_length(lambda x, y: topo.elev(d, x, y), pts)
        length_g, climb_g, _ = climb_and_length(lambda x, y: z_grid(Z, x, y), pts)
        band = np.floor(z / CI)
        cross = np.where(np.diff(band) != 0)[0]
        if len(cross) < 6 or cross[0] < 60 or cross[-1] > len(z) - 60:
            continue                                         # no contour crossing hidden under an end marker
        up_lines = int((np.diff(band) > 0).sum())            # what a careful reader counts: uphill crossings
        true = minutes(length, climb)
        reader = minutes(length, up_lines * CI)
        net_only = minutes(length, max(0.0, float(z[-1] - z[0])))
        flat = minutes(length, 0)
        checks = {"analytic_field_and_grid_agree": abs(true - minutes(length_g, climb_g)) <= 1.0,
                  "contour_counting_reader_within_6_min": abs(reader - true) <= 6,
                  "net_gain_shortcut_off_by_15_min": abs(net_only - true) >= 15,
                  "ignoring_climb_off_by_15_min": abs(flat - true) >= 15}
        if not all(checks.values()):
            continue
        name = str(rng.choice(topo.TRAILS))
        d["trails"] = [{"name": name, "pts": pts, "asked": True}]

        def away(a, b):
            v = np.array(a) - np.array(b)
            v = 95 * v / np.linalg.norm(v)
            return {"label_dx": round(float(v[0]), 1), "label_dy": round(float(v[1]), 1)}
        d["points"] = [pt("S", pts[0], "square", **away(pts[0], pts[1])), pt("E", pts[-1], "square", **away(pts[-1], pts[-2]))]
        steps = {"trail_length_m": round(length, 1), "total_ascent_m": round(climb, 1), "uphill_contour_crossings": up_lines,
                 "start_elev_m": round(float(z[0]), 1), "end_elev_m": round(float(z[-1]), 1),
                 "minutes_from_distance": round(60 * length / 4000, 1), "minutes_from_ascent": round(60 * climb / 300, 1),
                 "wrong_if_net_gain_only": round(net_only, 1), "wrong_if_climb_ignored": round(flat, 1)}
        q = INTRO + (f"A hiker walks the {name} (dashed black line) from the magenta square S to the magenta square E. "
                     "Estimate the walking time with Naismith's rule: 1 hour for every 4 km of map distance, plus "
                     "1 hour for every 300 m of ascent. Add up every uphill stretch along the way; downhill stretches "
                     "add no time and do not cancel ascent. Use the scale bar for distance. Answer in minutes; an "
                     "answer within 10 minutes of the true value is accepted. Give one number, for example 95.")
        return d, {"question": q, "answer": int(round(true)), "answer_type": "number", "tolerance_abs": 10,
                   "question_type": "topo.hike_time", "steps": steps, "checks": checks}
    raise SystemExit(f"hike_time seed {seed}: nothing fair found")


# ---------------------------------------------------------------------------------------------- 3. campsite
def campsite(seed):
    rng = np.random.default_rng(seed)
    for _ in range(80):
        d = base_map(int(rng.integers(1, 10 ** 6)), need_stream=True)
        X, Y, Z = topo.grid(d)
        gy, gx = np.gradient(Z, STEP)
        limit = int(round(float(np.median(Z)) / 100) * 100)          # the elevation rule, a round index value
        streams = [np.array(s["pts"]) for s in d["streams"]]
        found = {"ok": [], "too_high": [], "too_far": [], "too_steep": []}
        for _ in range(6000):
            q = [float(rng.uniform(300, W - 300)), float(rng.uniform(300, H - 300))]
            if not clear_of_labels(d, q):
                continue
            ring = [[q[0] + 50 * math.cos(a), q[1] + 50 * math.sin(a)] for a in np.linspace(0, 2 * math.pi, 9)[:-1]] + [q]
            slopes = [float(np.linalg.norm(topo.gradient(d, *r))) for r in ring]
            z, dist = z_at(d, q), min(topo.dist_to_poly(q, s) for s in streams)
            low, high = z <= limit - 30, z >= limit + 30
            near, far = 70 <= dist <= 220, dist >= 400
            gentle, steep = max(slopes) <= 0.14, min(slopes) >= 0.30
            kind = ("ok" if low and near and gentle else "too_high" if high and near and gentle else
                    "too_far" if low and far and gentle else "too_steep" if low and near and steep else None)
            if kind is None:
                continue
            j, i = int(round(q[1] / STEP)), int(round(q[0] / STEP))   # second way: the grid, not the field
            zg, sg = float(z_grid(Z, q[0], q[1])), float(math.hypot(gx[j, i], gy[j, i]))
            dg = min(float(np.sqrt(((topo.densify(s, 2.0) - np.array(q)) ** 2).sum(1)).min()) for s in streams)
            same = ((zg < limit) == low) and ((dg <= 300) == near) and ((sg <= 0.2) == gentle)
            if same:
                found[kind].append({"p": q, "elev_m": round(z, 1), "stream_distance_m": round(dist, 1),
                                    "contour_spacing_m": round(CI / max(slopes), 1), "kind": kind})
        picks = []
        for kind in ("ok", "too_high", "too_far", "too_steep"):
            c = next((c for c in found[kind] if all(math.dist(c["p"], o["p"]) >= 380 for o in picks)), None)
            if c is None:
                break
            picks.append(c)
        if len(picks) < 4:
            continue
        picks = [picks[k] for k in rng.permutation(4)]
        names = ["C1", "C2", "C3", "C4"]
        d["points"] = [pt(n, c["p"]) for n, c in zip(names, picks)]
        steps = [{"site": n, **{k: v for k, v in c.items() if k != "p"},
                  "below_limit": c["kind"] != "too_high", "within_300m_of_stream": c["kind"] != "too_far",
                  "gentle_ground": c["kind"] != "too_steep"} for n, c in zip(names, picks)]
        answer = next(s["site"] for s in steps if s["kind"] == "ok")
        checks = {"analytic_field_and_grid_agree": True, "exactly_one_site_passes": sum(s["kind"] == "ok" for s in steps) == 1,
                  "each_wrong_site_fails_exactly_one_rule": sorted(s["kind"] for s in steps) == ["ok", "too_far", "too_high", "too_steep"],
                  "margins": "elevation 30 m from the limit, stream <=220 m or >=400 m, spacing >=143 m or <=67 m"}
        d["campsite_rule"] = {"elevation_limit_m": limit, "max_stream_distance_m": 300, "min_contour_spacing_m": 100}
        q = INTRO + ("A ranger must choose one campsite from the magenta points C1, C2, C3 and C4. The site must meet all "
                     f"three rules: (1) it is below {limit} m; (2) it is within 300 m of a stream (blue line), measured "
                     "with the scale bar; (3) it is on gentle ground, where neighbouring contour lines are at least "
                     "100 m apart. Exactly one site meets all three rules. Which one? Answer with the site name, for "
                     "example C2.")
        return d, {"question": q, "answer": answer, "answer_type": "label", "question_type": "topo.campsite",
                   "steps": steps, "checks": checks}
    raise SystemExit(f"campsite seed {seed}: nothing fair found")


# ---------------------------------------------------------------------------------------------- main
def main():
    for sub in ("images", "data"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    rows = []
    for base, make in ((1100, line_of_sight), (1200, hike_time), (1300, campsite)):
        for k in (1, 2, 3):
            seed = base + k
            d, task = make(seed)
            tid = f"topo-{seed:06d}"
            checks = task.pop("checks")
            assert all(v for v in checks.values()), (tid, checks)
            (OUT / "data" / f"{tid}.json").write_text(json.dumps(
                {"task_id": tid, "family": "topo", "seed": seed, "generator_version": VERSION,
                 "params": {"template": task["question_type"]}, "data": d, "steps": task["steps"],
                 "references": topo.REFERENCES}, indent=1), encoding="utf-8")
            topo.render(d, OUT / "images" / f"{tid}.png")
            rows.append({"task_id": tid, "image": f"images/{tid}.png", **task, "seed": seed,
                         "generator_version": VERSION, "family": "topo", "difficulty": 4,
                         "data": f"data/{tid}.json", "checks": checks, "references": topo.REFERENCES})
            print(tid, task["question_type"], "answer", task["answer"], flush=True)
    (OUT / "tasks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


if __name__ == "__main__":
    main()
