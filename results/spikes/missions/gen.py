"""Issue #29 / directive #39: the multi-step topo questions framed as missions, with a scenario box on the map.

    uv run python results/spikes/missions/gen.py

Reads the task data written by results/spikes/multistep/gen.py (same terrain, same marks, same computed
chain) and re-frames each as a mission:

  mission.sar_line_of_sight   helicopter landed at R: which of four hikers can the crew see?
  mission.lost_hiker_sunset   Naismith's rule from S to the hut H: minutes of daylight left on arrival
  mission.base_camp           ranger picks the one site that meets three rules

Nothing about the terrain or the computed answers changes, only names, the scenario box and the wording
(the sunset mission adds one subtraction). `overlay` in each data file holds what a demo needs to draw the
true answer on the map (sight lines with their tightest point, the route, the site verdicts).
"""
import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "topo"))
import gen as topo  # noqa: E402

SRC = HERE.parent / "multistep" / "tasks"
OUT = HERE / "tasks"
VERSION = "topo-missions-0.1"
W, H = topo.W, topo.H
BOX_W, BOX_H = 1560.0, 400.0


def box_corner(d):
    """A map corner for the scenario box that covers no task mark and no part of the asked trail."""
    marks = [[p["x"], p["y"]] for p in d["points"]]
    for t in d["trails"]:
        if t.get("asked"):
            marks += topo.densify(t["pts"], 40).tolist()
    for x0, y0 in ((40, H - 40 - BOX_H), (W - 40 - BOX_W, H - 40 - BOX_H), (40, 40), (W - 40 - BOX_W, 40)):
        if all(not (x0 - 130 <= m[0] <= x0 + BOX_W + 130 and y0 - 130 <= m[1] <= y0 + BOX_H + 130) for m in marks):
            return [x0, y0]
    return None


def render(d, path):
    """topo.render, plus the scenario box drawn from d["scenario"]."""
    plt = topo.plt
    keep, plt.close = plt.close, lambda fig=None: None
    try:
        topo.render(d, path)
        fig = plt.gcf()
        ax = fig.axes[0]
        x0, y0 = d["scenario"]["box_xy"]
        ax.add_patch(plt.Rectangle((x0, y0), BOX_W, BOX_H, fc="#fffbe6", ec="#8a1c1c", lw=1.4, zorder=9))
        ax.text(x0 + 45, y0 + BOX_H - 55, d["scenario"]["title"], fontsize=8, weight="bold", color="#8a1c1c",
                va="top", zorder=10)
        ax.text(x0 + 45, y0 + BOX_H - 175, d["scenario"]["body"], fontsize=6.8, va="top", zorder=10, linespacing=1.35)
        fig.savefig(path, metadata={"Software": None})
    finally:
        plt.close = keep
        plt.close("all")


def clock(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def reframe(src_task, rec):
    d, steps, qt = rec["data"], rec["steps"], src_task["question_type"]
    rng = np.random.default_rng(rec["seed"] + 5000)
    if qt == "topo.line_of_sight":
        d["points"][0]["name"] = "R"
        r = d["points"][0]
        d["scenario"] = {"title": "SAR MISSION  ·  HELICOPTER DOWN AT R",
                         "body": "Four hikers reported missing at A, B, C and D.\nWhich can the crew see from R?"}
        overlay = {"sight_lines": [{"from": [r["x"], r["y"]], "to": [p["x"], p["y"]], "hiker": p["name"],
                                    "visible": s["visible"], "tightest_point": [s["tightest_x"], s["tightest_y"]]}
                                   for p, s in zip(d["points"][1:], steps)]}
        q = topo.INTRO + ("Search and rescue: a helicopter has landed on the ridge at the magenta square R. Four missing "
                          "hikers are at the magenta points A, B, C and D. The crew can see a hiker only if the ground "
                          "nowhere between rises above the straight sight line from R to that hiker. Ignore trees, eye "
                          "height and the curvature of the Earth. Which hikers can the crew see from R? Answer with "
                          "their letters separated by commas, for example A, C.")
        return q, src_task["answer"], {"answer_type": "sequence", "ordered": False}, "mission.sar_line_of_sight", steps, overlay
    if qt == "topo.hike_time":
        d["points"][1]["name"] = "H"
        name = d["trails"][0]["name"]
        walk = 60 * steps["trail_length_m"] / 4000 + 60 * steps["total_ascent_m"] / 300
        spare = int(rng.choice([-35, -20, 20, 35, 50]))
        daylight = int(round((walk + spare) / 5) * 5)
        now = 15 * 60 + 30
        d["scenario"] = {"title": f"LOST HIKER  ·  NOW {clock(now)}  ·  SUNSET {clock(now + daylight)}",
                         "body": f"Hiker at S must reach the hut at H\nalong the {name} before dark."}
        steps = {**steps, "walking_minutes": round(walk, 1), "daylight_minutes": daylight,
                 "minutes_left_at_arrival": round(daylight - walk, 1)}
        q = topo.INTRO + (f"A lost hiker at the magenta square S must reach the hut at the magenta square H along the {name} "
                          f"(dashed black line). It is {clock(now)} and sunset is at {clock(now + daylight)}. Walking time "
                          "follows Naismith's rule: 1 hour for every 4 km of map distance, plus 1 hour for every 300 m of "
                          "ascent. Add up every uphill stretch along the way; downhill stretches add no time and do not "
                          "cancel ascent. Use the scale bar for distance. How many minutes of daylight are left when the "
                          "hiker reaches the hut? Give a negative number if the hiker arrives after sunset. An answer "
                          "within 10 minutes of the true value is accepted. Give one number, for example 25 or -15.")
        return (q, int(round(daylight - walk)), {"answer_type": "number", "tolerance_abs": 10}, "mission.lost_hiker_sunset",
                steps, {"route": d["trails"][0]["pts"]})
    rule = d["campsite_rule"]
    d["scenario"] = {"title": "RANGER MISSION  ·  SITE THE BASE CAMP",
                     "body": (f"Sites C1 to C4. Rules: below {rule['elevation_limit_m']} m, within 300 m\n"
                              "of a stream, contour lines at least 100 m apart.")}
    q = topo.INTRO + ("Ranger mission: choose the base camp from the magenta points C1, C2, C3 and C4. The site must meet "
                      f"all three rules: (1) it is below {rule['elevation_limit_m']} m; (2) it is within 300 m of a stream "
                      "(blue line), measured with the scale bar; (3) it is on gentle ground, where neighbouring contour "
                      "lines are at least 100 m apart. Exactly one site meets all three rules. Which one? Answer with the "
                      "site name, for example C2.")
    overlay = {"sites": [{"site": s["site"], "verdict": s["kind"]} for s in steps]}
    return q, src_task["answer"], {"answer_type": "label"}, "mission.base_camp", steps, overlay


def main():
    for sub in ("images", "data"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    rows = []
    for line in (SRC / "tasks.jsonl").read_text(encoding="utf-8").splitlines():
        src = json.loads(line)
        rec = json.loads((SRC / src["data"]).read_text(encoding="utf-8"))
        q, answer, kind, qtype, steps, overlay = reframe(src, rec)
        d = rec["data"]
        corner = box_corner(d)
        assert corner is not None, f"{src['task_id']}: no free corner for the scenario box"
        d["scenario"]["box_xy"] = corner
        tid = src["task_id"].replace("topo-", "mission-")
        (OUT / "data" / f"{tid}.json").write_text(json.dumps(
            {"task_id": tid, "family": "topo", "seed": rec["seed"], "generator_version": VERSION,
             "params": {"template": qtype, "source_task": src["task_id"]}, "data": d, "steps": steps,
             "overlay": overlay, "references": topo.REFERENCES}, indent=1), encoding="utf-8")
        render(d, OUT / "images" / f"{tid}.png")
        rows.append({"task_id": tid, "image": f"images/{tid}.png", "question": q, "answer": answer, **kind,
                     "question_type": qtype, "steps": steps, "seed": rec["seed"], "generator_version": VERSION,
                     "family": "topo", "difficulty": 4, "data": f"data/{tid}.json",
                     "checks": {**src["checks"], "scenario_box_clear_of_marks": True}, "references": topo.REFERENCES})
        print(tid, qtype, "answer", answer, "box", corner, flush=True)
    (OUT / "tasks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


if __name__ == "__main__":
    main()
