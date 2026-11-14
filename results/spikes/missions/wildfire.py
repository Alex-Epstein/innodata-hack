"""Directive #39: the wildfire mission. Fire at F; which escape trail stays below the fire the whole way?

    uv run python results/spikes/missions/wildfire.py

The chain a solver follows: read the fire's elevation at F from the contours -> for each of three trails
leaving the crew at S, find the highest ground it crosses -> compare with the fire -> one trail stays below.

Every trail starts and ends below the fire, so looking at the end points alone decides nothing: the two
unsafe trails climb above the fire in the middle. Ground truth is the highest point of each trail on the
analytic elevation field, recomputed on the 10 m grid. Margins: the safe trail tops out at least 40 m (two
contour lines) below the fire, each unsafe trail at least 40 m above it.
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


ms = _load("multistep_gen", HERE.parent / "multistep" / "gen.py")
mg = _load("missions_gen", HERE / "gen.py")

OUT = HERE / "tasks_wildfire"
VERSION = "topo-missions-0.1"
W, H = topo.W, topo.H
MARGIN_M = 40


def top_of(zfun, pts):
    p = topo.densify(pts)
    z = zfun(p[:, 0], p[:, 1])
    k = int(np.argmax(z))
    return float(z[k]), [round(float(p[k, 0]), 1), round(float(p[k, 1]), 1)], float(z[-1])


def one_trail(rng, start, heading):
    p, pts = np.array(start, float), [list(start)]
    for _ in range(2):
        heading += rng.uniform(-0.7, 0.7)
        p = p + rng.uniform(550, 950) * np.array([math.cos(heading), math.sin(heading)])
        pts.append([round(float(p[0]), 1), round(float(p[1]), 1)])
    return pts if all(topo.inside(q, 260) for q in pts) else None


def wildfire(seed):
    rng = np.random.default_rng(seed)
    for _ in range(3000):
        d = ms.base_map(int(rng.integers(1, 10 ** 6)))
        d["trails"] = []
        X, Y, Z = topo.grid(d)
        analytic = lambda x, y: topo.elev(d, x, y)
        gridded = lambda x, y: ms.z_grid(Z, x, y)
        crew = [float(rng.uniform(900, W - 900)), float(rng.uniform(800, H - 800))]
        if not ms.clear_of_labels(d, crew, 240):
            continue
        ang = rng.uniform(0, 2 * math.pi)
        fire = [crew[0] + rng.uniform(450, 800) * math.cos(ang), crew[1] + rng.uniform(450, 800) * math.sin(ang)]
        if not topo.inside(fire, 300) or not ms.clear_of_labels(d, fire, 240):
            continue
        z_fire, z_crew = ms.z_at(d, fire), ms.z_at(d, crew)
        if not 50 <= z_fire - z_crew <= 160:                      # the fire is above the crew, not by much
            continue
        safe, unsafe = [], []
        for _ in range(400):
            head = rng.uniform(0, 2 * math.pi)
            pts = one_trail(rng, crew, head)
            if pts is None or not all(ms.clear_of_labels(d, q, 190) for q in topo.densify(pts, 40)[3:]):
                continue
            if topo.dist_to_poly(fire, pts) < 260:
                continue
            first = math.atan2(pts[1][1] - crew[1], pts[1][0] - crew[0])
            if any(abs((first - o["first"] + math.pi) % (2 * math.pi) - math.pi) < 0.75 for o in safe + unsafe):
                continue                                           # trails leave S in clearly different directions
            if any(math.dist(pts[-1], o["pts"][-1]) < 500 or topo.dist_to_poly(pts[-1], o["pts"]) < 300
                   or topo.dist_to_poly(o["pts"][-1], pts) < 300 for o in safe + unsafe):
                continue
            top, where, end = top_of(analytic, pts)
            top_g, _, _ = top_of(gridded, pts)
            rec = {"pts": pts, "first": first, "top": top, "where": where, "end": end}
            if top <= z_fire - MARGIN_M and top_g <= z_fire - MARGIN_M and len(safe) < 1:
                safe.append(rec)
            elif (top >= z_fire + MARGIN_M and top_g >= z_fire + MARGIN_M and end <= z_fire - MARGIN_M
                  and len(unsafe) < 2):
                unsafe.append(rec)
            if len(safe) == 1 and len(unsafe) == 2:
                break
        if len(safe) < 1 or len(unsafe) < 2:
            continue
        trails = [(safe[0], True)] + [(u, False) for u in unsafe]
        trails = [trails[i] for i in rng.permutation(3)]
        names = [str(n) for n in rng.choice(topo.TRAILS, 3, replace=False)]
        # the name is printed beside a trail's first leg, so store each trail from its far end back to S
        d["trails"] = [{"name": n, "pts": t[0]["pts"][::-1], "asked": True} for n, t in zip(names, trails)]
        d["points"] = [ms.pt("S", crew, "square"), ms.pt("F", fire, "square")]
        box = mg.box_corner(d)
        if box is None:
            continue
        steps = [{"trail": n, "highest_ground_m": round(t[0]["top"], 1), "highest_point": t[0]["where"],
                  "end_elev_m": round(t[0]["end"], 1), "fire_elev_m": round(z_fire, 1),
                  "stays_below_fire": t[1]} for n, t in zip(names, trails)]
        answer = next(s["trail"] for s in steps if s["stays_below_fire"])
        checks = {"analytic_field_and_grid_agree": True,
                  "margin_at_least_40m": all(abs(s["highest_ground_m"] - z_fire) >= MARGIN_M for s in steps),
                  "every_trail_ends_below_the_fire": all(s["end_elev_m"] <= z_fire - MARGIN_M for s in steps),
                  "exactly_one_safe_trail": sum(s["stays_below_fire"] for s in steps) == 1,
                  "scenario_box_clear_of_marks": True}
        d["scenario"] = {"title": "WILDFIRE  ·  FIRE AT F, CREW AT S", "box_xy": box,
                         "body": "Fire runs uphill. Which escape trail from S\nstays below the fire at F the whole way?"}
        listed = ", ".join(names[:2]) + " and " + names[2]
        q = topo.INTRO + ("Wildfire: a fire is burning at the magenta square F and a crew is at the magenta square S. Fire "
                          "spreads fastest uphill, so the crew is safe only on a route that stays below the elevation of F "
                          f"the whole way. Three escape trails (dashed black lines) leave S: {listed}. Exactly one of them "
                          "never climbs to the elevation of F. Which trail should the crew take? Answer with the trail "
                          f"name, for example {names[0]}.")
        overlay = {"fire_elev_m": round(z_fire, 1), "trails": [{"trail": s["trail"], "highest_point": s["highest_point"],
                                                                "safe": s["stays_below_fire"]} for s in steps]}
        return d, {"question": q, "answer": answer, "answer_type": "label", "question_type": "mission.wildfire",
                   "steps": steps, "checks": checks}, overlay
    raise SystemExit(f"wildfire seed {seed}: nothing fair found")


def main():
    for sub in ("images", "data"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    rows = []
    for seed in (1501, 1502, 1503):
        d, task, overlay = wildfire(seed)
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
        print(tid, "answer", task["answer"], [(s["trail"], s["highest_ground_m"], s["fire_elev_m"]) for s in task["steps"]],
              flush=True)
    (OUT / "tasks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


if __name__ == "__main__":
    main()
