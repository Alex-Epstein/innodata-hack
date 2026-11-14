"""Directive #39: the flash flood mission. A dam fails at D; water runs down the steepest way; which camp is hit?

    uv run python results/spikes/missions/flood.py

The chain a solver follows: read which way is downhill at D from the contour values -> trace a line that
crosses every contour at a right angle, bend by bend -> see which of four campsites it runs through.

Ground truth: the water route is the steepest-descent path of the analytic elevation field in the data.
It is recomputed a second way (finer steps on the 10 m grid) and from four starts moved 25 m off the dam;
a draw is kept only if every one of those routes hits the same campsite and stays far from the other three.
`overlay.water_route` holds the route so a demo can draw the true answer on the map.
"""
import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "topo"))
import gen as topo  # noqa: E402  (results/spikes/topo/gen.py)


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ms = _load("multistep_gen", HERE.parent / "multistep" / "gen.py")      # base_map, z_grid, clear_of_labels, pt
mg = _load("missions_gen", HERE / "gen.py")                            # render with the scenario box

OUT = HERE / "tasks_flood"
VERSION = "topo-missions-0.1"
W, H, STEP = topo.W, topo.H, topo.STEP
HIT_M, MISS_M = 45, 300             # the flooded camp is within 45 m of the water; the others at least 300 m away


def descend_grid(Z, start, ds=5.0):
    """Second way: steepest descent on the 10 m grid (bilinear), 5 m steps instead of 15 m on the field."""
    gy, gx = np.gradient(Z, STEP)
    p, pts = np.array(start, float), []
    for _ in range(1600):
        if not topo.inside(p, 0):
            break
        pts.append([float(p[0]), float(p[1])])
        g = np.array([float(ms.z_grid(gx, p[0], p[1])), float(ms.z_grid(gy, p[0], p[1]))])
        n = np.linalg.norm(g)
        if n < 0.004:
            break
        p = p - ds * g / n
    return pts


def box_corner(d, route):
    marks = [[p["x"], p["y"]] for p in d["points"]] + route
    for x0, y0 in ((40, H - 40 - mg.BOX_H), (W - 40 - mg.BOX_W, H - 40 - mg.BOX_H), (40, 40), (W - 40 - mg.BOX_W, 40)):
        if all(not (x0 - 130 <= m[0] <= x0 + mg.BOX_W + 130 and y0 - 130 <= m[1] <= y0 + mg.BOX_H + 130) for m in marks):
            return [x0, y0]
    return None


def flash_flood(seed):
    rng = np.random.default_rng(seed)
    for _ in range(60):
        d = ms.base_map(int(rng.integers(1, 10 ** 6)))
        X, Y, Z = topo.grid(d)
        lo, hi = np.quantile(Z, 0.60), np.quantile(Z, 0.92)
        for _ in range(40):
            dam = [float(rng.uniform(450, W - 450)), float(rng.uniform(450, H - 450))]
            if not lo <= ms.z_at(d, dam) <= hi or not ms.clear_of_labels(d, dam, 240):
                continue
            route = topo.stream_from(d, dam)                                 # 15 m steps on the analytic field
            if len(route) < 110:                                             # under about 1.6 km of flow
                continue
            others = [descend_grid(Z, dam)] + [topo.stream_from(d, [dam[0] + dx, dam[1] + dy])
                                               for dx, dy in ((25, 0), (-25, 0), (0, 25), (0, -25))]
            k = int(rng.integers(60, len(route) - 12))                       # the camp sits 0.9 km or more downstream
            a, b = np.array(route[k]), np.array(route[k + 1])
            side = np.array([-(b - a)[1], (b - a)[0]]) / np.linalg.norm(b - a)
            hit = (a + side * float(rng.uniform(-25, 25))).tolist()
            if not topo.inside(hit, 300) or not ms.clear_of_labels(d, hit):
                continue
            if any(topo.dist_to_poly(hit, r) > HIT_M for r in [route] + others):
                continue                                                     # the routes disagree at the camp
            box = None
            dry = []
            for _ in range(5000):
                q = [float(rng.uniform(300, W - 300)), float(rng.uniform(300, H - 300))]
                if ms.z_at(d, q) > ms.z_at(d, dam) - 40 or not 700 <= math.dist(q, dam) <= 2800:
                    continue                                                 # every camp is below the dam
                if not ms.clear_of_labels(d, q) or any(math.dist(q, o) < 420 for o in dry + [hit, dam]):
                    continue
                gap = min(topo.dist_to_poly(q, r) for r in [route] + others)
                if MISS_M <= gap <= 900:
                    dry.append(q)
                if len(dry) == 3:
                    break
            if len(dry) < 3:
                continue
            sites = [(hit, True)] + [(q, False) for q in dry]
            sites = [sites[i] for i in rng.permutation(4)]
            names = ["C1", "C2", "C3", "C4"]
            d["points"] = [ms.pt("D", dam, "square")] + [ms.pt(n, s[0]) for n, s in zip(names, sites)]
            box = box_corner(d, route)
            if box is None:
                continue
            flow_m = 15.0 * k
            steps = [{"site": n, "elev_m": round(ms.z_at(d, s[0]), 1),
                      "distance_to_water_route_m": round(float(topo.dist_to_poly(s[0], route)), 1), "flooded": s[1]}
                     for n, s in zip(names, sites)]
            answer = next(s["site"] for s in steps if s["flooded"])
            checks = {"field_route_and_grid_route_agree": True,
                      "same_camp_from_starts_25m_off_the_dam": True,
                      "flooded_camp_within_45m_of_every_route": True,
                      "dry_camps_at_least_300m_from_every_route": all(
                          min(topo.dist_to_poly(q, r) for r in [route] + others) >= MISS_M for q in dry),
                      "every_camp_below_the_dam": all(s["elev_m"] <= ms.z_at(d, dam) - 40 for s in steps),
                      "exactly_one_camp_flooded": sum(s["flooded"] for s in steps) == 1,
                      "scenario_box_clear_of_marks_and_route": True}
            d["scenario"] = {"title": "FLASH FLOOD  ·  DAM FAILED AT D", "box_xy": box,
                             "body": "Water runs straight downhill from D.\nWhich camp, C1 to C4, is in its path?"}
            q = topo.INTRO + ("Flash flood: the dam at the magenta square D has failed. The water runs downhill from D, always "
                              "in the direction of steepest descent, so its path crosses every contour line at a right "
                              "angle. Four campsites are at the magenta points C1, C2, C3 and C4, all lower than the dam. "
                              "Exactly one of them lies in the water's path. Which campsite does the water reach? Answer "
                              "with the site name, for example C2.")
            extra = {"dam_elev_m": round(ms.z_at(d, dam), 1), "flow_distance_to_camp_m": flow_m, "sites": steps}
            return d, {"question": q, "answer": answer, "answer_type": "label", "question_type": "mission.flash_flood",
                       "steps": extra, "checks": checks}, {"water_route": route, "flooded_site": answer}
    raise SystemExit(f"flash_flood seed {seed}: nothing fair found")


def main():
    for sub in ("images", "data"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    rows = []
    for seed in (1401, 1402, 1403):
        d, task, overlay = flash_flood(seed)
        tid = f"mission-{seed:06d}"
        checks = task.pop("checks")
        assert all(checks.values()), (tid, checks)
        (OUT / "data" / f"{tid}.json").write_text(json.dumps(
            {"task_id": tid, "family": "topo", "seed": seed, "generator_version": VERSION,
             "params": {"template": task["question_type"]}, "data": d, "steps": task["steps"], "overlay": overlay,
             "references": topo.REFERENCES}, indent=1), encoding="utf-8")
        mg.render(d, OUT / "images" / f"{tid}.png")
        rows.append({"task_id": tid, "image": f"images/{tid}.png", **task, "seed": seed, "generator_version": VERSION,
                     "family": "topo", "difficulty": 4, "data": f"data/{tid}.json", "checks": checks,
                     "references": topo.REFERENCES})
        print(tid, task["question_type"], "answer", task["answer"], "flow m", task["steps"]["flow_distance_to_camp_m"],
              [(s["site"], s["distance_to_water_route_m"]) for s in task["steps"]["sites"]], flush=True)
    (OUT / "tasks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


if __name__ == "__main__":
    main()
