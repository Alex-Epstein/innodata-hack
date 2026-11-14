"""The topographic-map family: missions on a map of a real place (contracts/FAMILY.md).

    from gen import topo
    task = topo.build(seed=7, template="flood", difficulty=3, out_dir=Path("tasks/pilot_topo"))

Data first: the terrain is real elevation (USGS 3DEP tiles stored in gen/topo/tiles/); the crop window, the
marks and every label position are sampled from the seed and written to data/<task_id>.json; the PNG is drawn
from that file's content only; the answer is computed from it, and solve_independent() computes it a second way.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import numpy as np

from . import real

FAMILY = "topo"
VERSION = "topo-2.0.0"
TEMPLATES = ["crossings", "sunset", "flood"]
_USGS = "USGS 7.5-minute topographic quadrangle maps (US Topo, 1:24 000): brown contours, heavy index contours"
_3DEP = "Elevation: USGS 3D Elevation Program (3DEP, public domain) via AWS Open Data Terrain Tiles (terrarium, zoom 13)"
REFERENCES = {
    "crossings": [_USGS, _3DEP],
    "sunset": [_USGS, _3DEP + "; Naismith's rule for walking time (1892): 1 hour per 4 km plus 1 hour per 300 m of climb"],
    "flood": [_USGS, _3DEP + "; surface water runs down the line of steepest descent, at right angles to the contours"],
}
_CHECKS = {"two_solvers_agree": True, "labels_do_not_overlap": True}
_TRAIL_CHECKS = {**_CHECKS, "incident_box_clear_of_trail": True, "crossings_40m_apart_and_from_ends": True,
                 "no_grazing_or_shallow_crossings": True, "trail_avoids_water": True}
_FLOOD_CHECKS = {**_CHECKS, "incident_box_clear_of_water_route": True, "one_camp_within_40m_of_every_route": True,
                 "other_camps_beyond_the_dry_gap": True, "every_camp_below_the_dam": True}
DRAWS = 6                                # layouts tried per seed (each one already searches many crop windows)


class RejectSeed(Exception):
    """This seed cannot make a fair task for the template and difficulty asked."""


def _given_away(answer, question):
    """A number equal to the answer must not appear in the question (validate's answer_not_in_question)."""
    return isinstance(answer, int) and abs(answer) >= 10 and \
        answer in {int(float(x)) for x in re.findall(r"(?<![\w.])[-+]?\d+", question)}


def build(seed: int, template: str, difficulty: int, out_dir: Path) -> dict:
    """Deterministic: the same (seed, template, difficulty) gives the same files. See contracts/FAMILY.md."""
    if template not in TEMPLATES or difficulty not in (1, 2, 3):
        raise ValueError(f"template must be one of {TEMPLATES} and difficulty 1, 2 or 3")
    out_dir = Path(out_dir)
    for sub in ("images", "data"):
        (out_dir / sub).mkdir(parents=True, exist_ok=True)
    task_id = f"{FAMILY}-{template}-{seed:06d}"
    rng = np.random.default_rng([seed, TEMPLATES.index(template), difficulty])
    flood = template == "flood"
    why = "no fair layout found on this terrain"
    for _ in range(DRAWS):
        d = real.sample_flood(rng, seed, difficulty) if flood else real.sample(rng, seed, template, difficulty)
        if d is None:
            break
        answer, steps, overlay = real.answer_flood(d) if flood else real.answer(d)
        asked = real.ask_flood(d) if flood else real.ask(d)
        if answer is None or answer != (real.independent_flood(d) if flood else real.independent(d)):
            why = "the two solvers disagree"
            continue
        if _given_away(answer, asked["question"]):
            why = "the answer would appear in the question text"
            continue
        record = {"task_id": task_id, "family": FAMILY, "seed": seed, "generator_version": VERSION,
                  "params": {"template": template, "difficulty": difficulty}, "data": d,
                  "references": REFERENCES[template]}
        data_path = out_dir / "data" / f"{task_id}.json"
        data_path.write_text(json.dumps(record, indent=1), encoding="utf-8")       # data first
        drawn = json.loads(data_path.read_text(encoding="utf-8"))["data"]           # the image sees only the file
        layout = real.render(drawn, out_dir / "images" / f"{task_id}.png")
        clash = real.label_clash(layout, markers=len(d["points"]) if flood else 2)
        if clash:
            why = clash
            continue
        return {"task_id": task_id, "image": f"images/{task_id}.png", **asked, "answer": answer,
                "seed": seed, "generator_version": VERSION, "question_type": f"{FAMILY}.{template}", "family": FAMILY,
                "difficulty": difficulty, "data": f"data/{task_id}.json",
                "checks": _FLOOD_CHECKS if flood else _TRAIL_CHECKS,
                "references": REFERENCES[template], "steps": steps, "overlay": overlay, "layout": layout}
    for stale in (out_dir / "data" / f"{task_id}.json", out_dir / "images" / f"{task_id}.png"):
        stale.unlink(missing_ok=True)
    raise RejectSeed(f"{task_id} difficulty {difficulty}: {why}")


def solve_independent(data: dict, template: str):
    """The answer recomputed from the data JSON alone, a second way. Trails: the drawn contour polylines
    (contourpy) intersected with the trail. Flood: a finer descent (4 m steps, a tighter slope stencil)."""
    d = data.get("data", data)
    return real.independent_flood(d) if template == "flood" else real.independent(d)
