"""A tiny family for tests only (TEST_ONLY): three bars, "which bar is tallest?".

It shows the whole contracts/FAMILY.md interface in about 100 lines and passes every check in validate/:
data JSON first, deterministic PNG via factory.render.save_png, layout.texts and layout.probes, and a
second solver that uses a different method from build().
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from factory.render import new_figure, save_png, text_boxes, to_pixels

FAMILY = "example"
VERSION = "example-1.0.0"
TEMPLATES = ["tallest"]
REFERENCES = {"tallest": ["Matplotlib bar chart gallery example (matplotlib.org)"]}
TEST_ONLY = True                      # never picked by `fresh` unless asked for by name

LABELS = ["A", "B", "C"]
COLORS = ["#1f77b4", "#ff7f0e", "#2ca02c"]
BACKGROUND = "#ffffff"
MIN_GAP = {1: 20, 2: 10, 3: 5}        # difficulty: how close the top two bars may be


class RejectSeed(Exception):
    """This seed can't make a fair task."""


def sample(seed: int, difficulty: int) -> dict:
    rng = np.random.default_rng(seed)
    heights = [int(h) for h in rng.integers(10, 100, size=3)]
    top2 = sorted(heights)[-2:]
    if top2[1] - top2[0] < MIN_GAP.get(difficulty, 5):
        raise RejectSeed(f"top two bars {top2[0]} and {top2[1]} are closer than {MIN_GAP.get(difficulty, 5)}")
    return {"labels": LABELS, "heights": heights, "unit": "units"}


def render(data: dict, png: Path) -> dict:
    fig = new_figure(480, 360)
    ax = fig.add_axes([0.14, 0.14, 0.80, 0.76])
    xs = np.arange(len(data["labels"]))
    ax.bar(xs, data["heights"], color=COLORS, width=0.6)
    ax.set_xticks(xs, data["labels"])
    ax.set_ylim(0, 110)
    ax.set_ylabel(f"Value ({data['unit']})")
    ax.set_title("Example bars")
    ax.set_facecolor(BACKGROUND)
    texts = text_boxes(fig)
    probes = [{"xy": to_pixels(ax, x, h / 2), "expect": c, "tol": 10, "what": f"bar {lab} body"}
              for x, h, c, lab in zip(xs, data["heights"], COLORS, data["labels"])]
    lo = int(np.argmin(data["heights"]))
    probes.append({"xy": to_pixels(ax, xs[lo], (data["heights"][lo] + 110) / 2), "expect": BACKGROUND, "tol": 10,
                   "what": f"empty space above bar {data['labels'][lo]}"})
    save_png(fig, png)
    return {"texts": texts, "probes": probes}


def build(seed: int, template: str, difficulty: int, out_dir: Path) -> dict:
    if template not in TEMPLATES:
        raise ValueError(f"unknown template {template!r}")
    out_dir = Path(out_dir)
    tid = f"{FAMILY}-{template}-{seed:06d}"
    data = sample(seed, difficulty)
    doc = {"task_id": tid, "family": FAMILY, "seed": seed, "generator_version": VERSION,
           "params": {"difficulty": difficulty, "min_gap": MIN_GAP.get(difficulty, 5)}, "data": data,
           "references": REFERENCES[template]}
    data_path = out_dir / "data" / f"{tid}.json"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(doc, indent=1), encoding="utf-8")          # 1. data first
    layout = render(data, out_dir / "images" / f"{tid}.png")                   # 2. image from the data
    i = max(range(3), key=lambda k: data["heights"][k])                         # 3. answer from the data
    return {
        "task_id": tid, "image": f"images/{tid}.png", "data": f"data/{tid}.json",
        "question": "Which bar in the chart is the tallest? Answer with its label (A, B or C).",
        "answer": data["labels"][i], "answer_type": "label",
        "steps": [f"{lab} = {h}" for lab, h in zip(data["labels"], data["heights"])] + [f"max is {data['labels'][i]}"],
        "layout": layout,
    }


def solve_independent(data: dict, template: str):
    """Sort instead of argmax, from the data JSON file alone."""
    d = data["data"]
    return sorted(zip(d["heights"], d["labels"]))[-1][1]
