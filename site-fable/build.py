"""Build the data for the 3D demo "The Map vs the Mountain" (issue #60) from task and result folders.

    uv run python site-fable/build.py                       # tasks/final + results/final if they exist, else the topo pilots
    uv run python site-fable/build.py --set tasks/pilot_topo_flood:results/pilot_topo_flood --per-template 4
    uv run python site-fable/build.py --add /tmp/fresh/tasks:/tmp/fresh/results      # add a fresh task to the page

Nothing here is typed by hand and no model is called. For every topo task it writes site-fable/data/<task>.js with:
  the exact PNG the models were sent, the real elevation of the map window (rebuilt from gen/topo/tiles), where the map
  frame sits in that PNG (fitted from the validator's marker probes), the truth geometry recomputed by gen.topo.real
  (and required to equal the stored answer), and both models' replies from responses.csv.
site-fable/data/index.js lists the tasks and carries the score and check counts read from summary.json and
validation_report.json. Plain <script> files (no fetch), so the page also opens from disk.
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from gen.topo import real  # noqa: E402  (the family's own code: grid, answers, truth geometry)

OUT = Path(__file__).resolve().parent / "data"
MESH_NX, MESH_NY = 241, 181            # terrain mesh samples across the 3200 m x 2400 m map frame (13.3 m cells)
MODEL_NAMES = {"anthropic/claude-haiku-5.5": ("haiku", "HAIKU"), "openai/gpt-6-luna": ("luna", "LUNA")}
ORDER = ["flood", "crossings", "sunset"]


def frame_px(d, layout, img_w, img_h):
    """Where the map frame (x 0..W m, y 0..H m) sits in the PNG, as [left, top, right, bottom] in pixels.
    Fitted from the marker probes the validator already checks (pixel position of every marked point)."""
    W, H = d["grid"]["extent_m"]
    known = {p["name"]: (p["x"], p["y"]) for p in d.get("points", [])}
    if d.get("trail"):
        known[d["mission"]["from"]] = tuple(d["trail"]["pts"][0])
        known[d["mission"]["to"]] = tuple(d["trail"]["pts"][-1])
    xs, ys, px, py = [], [], [], []
    for pr in layout["probes"]:
        name = pr["what"].replace("marker ", "")
        if pr["what"].startswith("marker ") and name in known:
            xs.append(known[name][0]); ys.append(known[name][1]); px.append(pr["xy"][0]); py.append(pr["xy"][1])
    if len(xs) < 2:
        raise SystemExit("not enough marker probes to place the map frame")
    # one scale for both axes (the map is drawn with equal aspect): px = k x + bx, py = -k y + by
    xs, ys, px, py = (np.asarray(v, float) for v in (xs, ys, px, py))
    n = len(xs)
    A = np.zeros((2 * n, 3))
    A[:n, 0], A[:n, 1] = xs, 1
    A[n:, 0], A[n:, 2] = -ys, 1
    (k, bx, by), *_ = np.linalg.lstsq(A, np.r_[px, py], rcond=None)
    res = np.abs(A @ np.array([k, bx, by]) - np.r_[px, py]).max()
    if res > 1.5 or k <= 0:
        raise SystemExit(f"map frame fit is off by {res:.1f} px")
    ax, ay = k, -k
    left, right = bx, ax * W + bx
    bottom, top = by, ay * H + by                     # image y grows downward, so ay is negative
    if not (0 <= left < right <= img_w and 0 <= top < bottom <= img_h):
        raise SystemExit("map frame falls outside the image")
    return [round(float(v), 2) for v in (left, top, right, bottom)]


def png_size(b):
    return int.from_bytes(b[16:20], "big"), int.from_bytes(b[20:24], "big")


def build_task(task, tdir, rows):
    data_file = json.loads((tdir / task["data"]).read_text())
    d = data_file["data"]
    tpl = d["mission"]["template"]
    G, _ = real.window_of(d)
    s = d["grid"]["spacing_m"]
    W, H = d["grid"]["extent_m"]

    # the truth, recomputed here by the family's code; it must equal the stored answer
    if tpl == "flood":
        ans, steps, overlay = real.answer_flood(d)
    else:
        ans, steps, overlay = real.answer(d)
    if str(ans) != str(task["answer"]):
        raise SystemExit(f"{task['task_id']}: recomputed answer {ans} != stored answer {task['answer']}")

    xs = np.linspace(0, W, MESH_NX)
    ys = np.linspace(0, H, MESH_NY)
    X, Y = np.meshgrid(xs, ys)
    Z = real.bilinear(G, s, X, Y)                      # row 0 = south
    z16 = np.clip(np.round(Z * 10), 0, 65535).astype("<u2")

    png = (tdir / task["image"]).read_bytes()
    iw, ih = png_size(png)
    layout = json.loads((tdir / "layout" / f"{task['task_id']}.json").read_text())["layout"]

    def z_at(x, y):
        return round(float(real.bilinear(G, s, x, y)), 1)

    points = [{"name": p["name"], "x": p["x"], "y": p["y"], "z": z_at(p["x"], p["y"]), "shape": p["shape"]}
              for p in d.get("points", [])]
    if d.get("trail"):
        a, b = d["trail"]["pts"][0], d["trail"]["pts"][-1]
        points += [{"name": d["mission"]["from"], "x": a[0], "y": a[1], "z": z_at(*a), "shape": "square"},
                   {"name": d["mission"]["to"], "x": b[0], "y": b[1], "z": z_at(*b), "shape": "square"}]

    truth = {}
    if tpl == "flood":
        truth = {"water_route": overlay["water_route"], "flooded_camp": overlay["flooded_camp"]}
    else:
        pts = np.array(d["trail"]["pts"])
        keep = np.unique(np.r_[np.arange(0, len(pts), 2), len(pts) - 1])       # every 2nd vertex is plenty for drawing
        found, zt, arc = real.crossings_sampled(G, s, pts, d["levels"])
        k = np.unique(np.r_[np.arange(0, len(arc), 8), len(arc) - 1])          # the profile, one sample per 8 m
        truth = {"route": [[round(float(x), 1), round(float(y), 1)] for x, y in pts[keep]],
                 "crossings": [{"arc": round(a, 1), "level": l, "x": round(x, 1), "y": round(y, 1), "uphill": u}
                               for a, l, x, y, u in found],
                 "profile": [[round(float(arc[i]), 1), round(float(zt[i]), 1)] for i in k],
                 "length_m": round(float(arc[-1]), 1)}

    models = []
    for r in rows:
        key, name = MODEL_NAMES.get(r["model"], (r["model"].split("/")[-1], r["model"].split("/")[-1].upper()))
        models.append({"key": key, "name": name, "id": r["model"], "status": r["status"], "parsed": r["parsed"],
                       "correct": r["correct"] == "1", "finish_reason": r["finish_reason"], "reply": r["response"][:6000]})

    payload = {
        "id": task["task_id"], "template": tpl, "seed": task["seed"], "difficulty": task["difficulty"],
        "generator_version": task["generator_version"], "area": d["area"], "state": d["state"],
        "question": task["question"], "answer": task["answer"], "answer_type": task["answer_type"], "steps": steps,
        "references": task["references"], "bounds": d["grid"]["bounds"], "extent_m": [W, H],
        "elev_min_m": round(float(Z.min()), 1), "elev_max_m": round(float(Z.max()), 1),
        "contour_interval_m": d["contour_interval_m"], "index_interval_m": d["index_interval_m"],
        "mission": d["mission"], "box": d["box"], "trail_name": (d.get("trail") or {}).get("name"),
        "draws_discarded": d.get("attempt", 0), "points": points, "truth": truth, "models": models,
        "mesh": {"nx": MESH_NX, "ny": MESH_NY, "unit": "0.1 m, uint16 little-endian, row 0 = south",
                 "z": base64.b64encode(z16.tobytes()).decode()},
        "image": {"w": iw, "h": ih, "frame": frame_px(d, layout, iw, ih),
                  "src": "data:image/png;base64," + base64.b64encode(png).decode()},
    }
    (OUT / f"{task['task_id']}.js").write_text("MVM_TASK(" + json.dumps(payload, separators=(",", ":")) + ");\n")
    both_wrong = len(models) >= 2 and not any(m["correct"] for m in models)
    same_miss = both_wrong and len({m["parsed"] for m in models}) == 1
    return {"id": payload["id"], "template": tpl, "seed": payload["seed"], "difficulty": payload["difficulty"],
            "area": payload["area"], "state": payload["state"], "answer": payload["answer"],
            "elev_max_m": payload["elev_max_m"], "draws_discarded": payload["draws_discarded"],
            "models": [{k: m[k] for k in ("key", "name", "parsed", "correct", "status")} for m in models],
            "rank": 0 if same_miss else 1 if both_wrong else 2 if models else 3}


def read_set(tdir, rdir):
    tasks = [json.loads(l) for l in (tdir / "tasks.jsonl").read_text().splitlines() if l.strip()]
    rows = {}
    if rdir and (rdir / "responses.csv").exists():
        with open(rdir / "responses.csv", newline="") as f:
            for r in csv.DictReader(f):
                rows.setdefault(r["task_id"], []).append(r)
    for v in rows.values():
        v.sort(key=lambda r: list(MODEL_NAMES).index(r["model"]) if r["model"] in MODEL_NAMES else 99)
    return tasks, rows


def set_stats(tdir, rdir, tasks, rows):
    """Score and check counts for one folder pair, straight from the report files (and responses.csv per template)."""
    out = {"tasks": str(tdir.relative_to(ROOT)) if tdir.is_relative_to(ROOT) else str(tdir),
           "results": (str(rdir.relative_to(ROOT)) if rdir.is_relative_to(ROOT) else str(rdir)) if rdir else None}
    vr = tdir / "validation_report.json"
    if vr.exists():
        v = json.loads(vr.read_text())
        out["validation"] = {"attempted": v["generation"]["attempted"], "kept": v["generation"]["kept"],
                             "checked": v["checked"], "all_passed": v["all_passed"],
                             "checks": [{"name": k, **c} for k, c in v["per_check"].items()]}
    score = {}
    for t in tasks:
        if t.get("family") != "topo":
            continue
        for r in rows.get(t["task_id"], []):
            if r["status"] != "ok":
                continue
            key, name = MODEL_NAMES.get(r["model"], (r["model"], r["model"]))
            c = score.setdefault(t["template"], {}).setdefault(key, {"name": name, "correct": 0, "scored": 0})
            c["scored"] += 1
            c["correct"] += r["correct"] == "1"
    out["score"] = score
    if rdir and (rdir / "run_config.json").exists():
        rc = json.loads((rdir / "run_config.json").read_text())
        out["run"] = {k: rc.get(k) for k in ("models", "temperature", "reasoning", "max_tokens")}
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", action="append", default=[], help="TASKS_DIR:RESULTS_DIR (repeatable)")
    ap.add_argument("--add", action="append", default=[], help="like --set, but keeps what is already in data/")
    ap.add_argument("--per-template", type=int, default=4, help="tasks kept per template (0 = all)")
    a = ap.parse_args()

    sets = a.set + a.add
    if not sets:
        if (ROOT / "tasks/final/tasks.jsonl").exists():
            sets = ["tasks/final:results/final"]
        else:
            sets = [f"tasks/pilot_topo_{t}:results/pilot_topo_{t}" for t in ORDER]
    OUT.mkdir(exist_ok=True)
    index = {"tasks": [], "sets": []}
    if a.add and not a.set and (OUT / "index.js").exists():
        index = json.loads((OUT / "index.js").read_text().split("=", 1)[1].rstrip().rstrip(";"))
    else:
        for f in OUT.glob("*.js"):
            f.unlink()

    for spec in sets:
        t, _, r = spec.partition(":")
        tdir = (ROOT / t) if not Path(t).is_absolute() else Path(t)
        rdir = ((ROOT / r) if not Path(r).is_absolute() else Path(r)) if r else None
        tasks, rows = read_set(tdir, rdir)
        index["sets"] = [s for s in index["sets"] if s["tasks"] != str(t)] + [set_stats(tdir, rdir, tasks, rows)]
        entries = []
        for task in tasks:
            if task.get("family") != "topo":
                continue                                # the 3D stage is for terrain; other families stay on the report page
            entries.append((task, rows.get(task["task_id"], [])))
        # which tasks go on stage is a rule, not a choice: per template, both models wrong on the same answer first,
        # then both wrong, then the rest, by seed
        picked = {}
        for task, rws in entries:
            parsed = [x["parsed"] for x in rws]
            wrong = len(rws) >= 2 and all(x["correct"] != "1" for x in rws)
            rank = 0 if wrong and len(set(parsed)) == 1 else 1 if wrong else 2
            picked.setdefault(task["template"], []).append((rank, task["seed"], task, rws))
        for tpl, lst in picked.items():
            lst.sort(key=lambda e: e[:2])
            for _, _, task, rws in (lst[:a.per_template] if a.per_template else lst):
                e = build_task(task, tdir, rws)
                e["set"] = str(t)
                index["tasks"] = [x for x in index["tasks"] if x["id"] != e["id"]] + [e]
                print(f"  {e['id']}  answer {e['answer']}  " + "  ".join(f"{m['name']} {m['parsed']}" for m in e["models"]))

    index["tasks"].sort(key=lambda e: (ORDER.index(e["template"]) if e["template"] in ORDER else 9, e["rank"], e["seed"]))
    (OUT / "index.js").write_text("window.MVM_INDEX=" + json.dumps(index, separators=(",", ":")) + ";\n")
    size = sum(f.stat().st_size for f in OUT.glob("*.js")) / 1e6
    print(f"{len(index['tasks'])} tasks -> {OUT.relative_to(ROOT)} ({size:.1f} MB)")


if __name__ == "__main__":
    main()
