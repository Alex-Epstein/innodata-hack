"""The topographic-map family: missions on a USGS-style quadrangle (contracts/FAMILY.md).

    from gen import topo
    task = topo.build(seed=7, template="flood", difficulty=3, out_dir=Path("tasks/pilot_topo"))

Data first: the terrain (a tilted plane plus Gaussian hills), the marks and every label position are sampled
from the seed and written to data/<task_id>.json; the PNG is drawn from that file's content only; the answer
is computed from it on the analytic field, and solve_independent() recomputes it on the 10 m grid.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from . import missions as M
from . import terrain as T
from .render import label_clash, render

FAMILY = "topo"
VERSION = "topo-1.0.0"
TEMPLATES = ["crossings", "sunset", "flood", "wildfire"]
_USGS = ["USGS 7.5-minute topographic quadrangle maps (US Topo, 1:24 000): brown contours, heavy index contours",
         "USGS Topographic Map Symbols (contours, spot elevations, trails, streams)"]
REFERENCES = {
    "crossings": _USGS,
    "sunset": [_USGS[0], "Naismith's rule for walking time (W. W. Naismith, 1892): 1 hour per 4 km plus 1 hour per 300 m of climb"],
    "flood": [_USGS[0], "Surface water runs down the line of steepest descent, at right angles to the contours (USGS map-reading guidance)"],
    "wildfire": [_USGS[0], "Fire spreads faster upslope: NWCG wildland fire behavior training (S-190), slope as a topographic factor"],
}
MAX_ATTEMPTS = 60


class RejectSeed(Exception):
    """This seed cannot make a fair task for the template and difficulty asked."""


def _same(a, b):
    return sorted(a) == sorted(b) if isinstance(a, list) and isinstance(b, list) else a == b


def _given_away(answer, question):
    """A number equal to the answer, or the whole answer list in order, must not appear in the question."""
    if isinstance(answer, int):
        return abs(answer) >= 10 and answer in {int(float(x)) for x in re.findall(r"(?<![\w.])[-+]?\d+", question)}
    if isinstance(answer, list) and len(answer) > 1:
        return " ".join(a.lower() for a in answer) in " ".join(re.sub(r"[^a-z0-9]+", " ", question.lower()).split())
    return False


def build(seed: int, template: str, difficulty: int, out_dir: Path) -> dict:
    """Deterministic: the same (seed, template, difficulty) gives the same files. See contracts/FAMILY.md."""
    if template not in TEMPLATES or difficulty not in (1, 2, 3):
        raise ValueError(f"template must be one of {TEMPLATES} and difficulty 1, 2 or 3")
    out_dir = Path(out_dir)
    for sub in ("images", "data"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)
    task_id = f"{FAMILY}-{template}-{seed:06d}"
    rng = np.random.default_rng([seed, TEMPLATES.index(template), difficulty])
    why = "no fair layout found"
    for attempt in range(MAX_ATTEMPTS):
        d = T.new_terrain(rng)
        X, Y, Z = T.grid(d)
        lines = T.contour_lines(Z)
        placed = M.PLACE[template](rng, d, Z, lines, difficulty)
        if placed is None:
            continue
        corner = T.box_corner([[p["x"], p["y"]] for p in d["points"]] + placed["avoid"])
        if corner is None:
            why = "no free corner for the incident box"
            continue
        d["box"]["xy"] = corner
        T.decorate(rng, d, X, Y, Z, lines, placed["keep_lines"], placed.get("stream_gap_lines", ()),
                   placed.get("extra_trail", True))
        if len(d["index_labels"]) < 3:
            why = "too few index-contour labels to read elevations"
            continue
        answer, steps, overlay = M.ANSWER[template](d)
        if answer is None or not _same(answer, M.INDEPENDENT[template](d)):
            why = "the two solvers disagree"
            continue
        asked = M.ASK[template](d)
        if _given_away(answer, asked["question"]):
            why = "the answer would appear in the question text"
            continue
        d["attempt"] = attempt
        record = {"task_id": task_id, "family": FAMILY, "seed": seed, "generator_version": VERSION,
                  "params": {"template": template, "difficulty": difficulty}, "data": d,
                  "references": REFERENCES[template]}
        data_path = out_dir / "data" / f"{task_id}.json"
        data_path.write_text(json.dumps(record, indent=1), encoding="utf-8")       # data first
        drawn = json.loads(data_path.read_text(encoding="utf-8"))["data"]           # the image sees only the file
        layout = render(drawn, out_dir / "images" / f"{task_id}.png")
        clash = label_clash(layout)
        if clash:
            why = clash
            continue
        return {"task_id": task_id, "image": f"images/{task_id}.png", **asked, "answer": answer,
                "seed": seed, "generator_version": VERSION, "question_type": f"{FAMILY}.{template}", "family": FAMILY,
                "difficulty": difficulty, "data": f"data/{task_id}.json",
                "checks": {"two_solvers_agree": True, "labels_do_not_overlap": True, "incident_box_clear_of_marks": True},
                "references": REFERENCES[template], "steps": steps, "overlay": overlay, "layout": layout}
    for stale in (out_dir / "data" / f"{task_id}.json", out_dir / "images" / f"{task_id}.png"):
        stale.unlink(missing_ok=True)
    raise RejectSeed(f"{task_id} difficulty {difficulty}: {why}")


def solve_independent(data: dict, template: str):
    """The answer recomputed from the data JSON alone, on the 10 m grid and the contour polylines traced from it
    (contourpy), not on the analytic field that build() uses."""
    return M.INDEPENDENT[template](data.get("data", data))
