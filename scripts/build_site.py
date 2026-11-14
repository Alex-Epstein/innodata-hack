"""Build the "Beat the AI" phone page data (#40): site/tasks.json + site/img/ from task folders and their results.

    scripts/build-site                                   # results/final if it exists, else the topo spike sets
    scripts/build-site tasks/final:results/final         # explicit task_dir:results_dir pairs

The page (site/index.html) is static and reads only site/tasks.json, so what judges play always matches the
reported results: the reference answer comes from tasks.jsonl, each model's answer and correct flag come from
responses.csv exactly as scored by eval/. Nothing is re-scored here.
"""
from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
IMG = SITE / "img"
MAX_W = 1600                       # phone-friendly size; contours stay readable when zoomed
MODEL_NAMES = {"anthropic/claude-haiku-5.5": "Haiku", "openai/gpt-6-luna": "Luna"}
DEFAULT_SOURCES = [("tasks/final", "results/final")]
SPIKE_SOURCES = [("results/spikes/missions/tasks", "results/spikes/missions/results"),
                 ("results/spikes/missions/tasks_flood", "results/spikes/missions/results_flood"),
                 ("results/spikes/topo/tasks", "results/spikes/topo/results_64k")]
TITLES = {
    "mission.sar_line_of_sight": "Search and rescue: who can the crew see?",
    "mission.lost_hiker_sunset": "Lost hiker vs sunset",
    "mission.base_camp": "Pick the base camp",
    "mission.flash_flood": "Flash flood: which camp is hit?",
    "mission.wildfire": "Wildfire escape",
    "topo.trail_crossings": "Count the contour lines",
    "topo.higher_point": "Which point is higher?",
    "topo.point_elevation": "Read the elevation",
}


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def options_for(task: dict) -> list[str]:
    """Tap targets for label / sequence answers: the task's own `options`, else the marked points named in the
    question ("the magenta points C1, C2, C3 and C4", "marked in magenta, A and B")."""
    if task.get("options"):
        return [str(o) for o in task["options"]]
    q = task["question"]
    m = re.search(r"(?:magenta points?|marked in magenta,?)\s+((?:[A-Z]\d?)(?:\s*(?:,|and|, and)\s*[A-Z]\d?)*)", q)
    if m:
        return re.findall(r"[A-Z]\d?", m.group(1))
    ans = task["answer"] if isinstance(task["answer"], list) else [task["answer"]]
    if all(str(a).lower() in ("yes", "no") for a in ans):
        return ["Yes", "No"]
    return []


def input_kind(task: dict, options: list[str]) -> str:
    t = task["answer_type"]
    if t in ("integer", "number"):
        return "number"
    if t == "sequence" and options:
        return "multi"
    if t in ("label", "multiple_choice") and options:
        return "choice"
    return "text"


def build(sources: list[tuple[str, str]]) -> dict:
    IMG.mkdir(parents=True, exist_ok=True)
    for old in IMG.glob("*"):
        old.unlink()
    out, used = [], []
    for tdir, rdir in sources:
        tdir, rdir = ROOT / tdir, ROOT / rdir
        if not (tdir / "tasks.jsonl").exists() or not (rdir / "responses.csv").exists():
            continue
        used.append({"tasks": str(tdir.relative_to(ROOT)).replace("\\", "/"),
                     "results": str(rdir.relative_to(ROOT)).replace("\\", "/")})
        rows = list(csv.DictReader((rdir / "responses.csv").open(encoding="utf-8", newline="")))
        for task in load_jsonl(tdir / "tasks.jsonl"):
            models = {}
            for r in rows:
                if r["task_id"] == task["task_id"] and r["correct"] in ("0", "1"):
                    models[MODEL_NAMES.get(r["model"], r["model"])] = {
                        "model_id": r["model"], "answer": r["parsed"], "correct": r["correct"] == "1"}
            if len(models) < 2:                      # only tasks both models answered completely
                continue
            src = tdir / task["image"]
            name = f"{task['task_id']}.jpg"
            with Image.open(src) as im:
                im = im.convert("RGB")
                if im.width > MAX_W:
                    im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.LANCZOS)
                im.save(IMG / name, "JPEG", quality=88, optimize=True)
            overlay = None
            for cand in (task.get("overlay_image"), f"images/{task['task_id']}_truth.png"):
                if cand and (tdir / cand).exists():
                    overlay = f"img/{task['task_id']}_truth.jpg"
                    with Image.open(tdir / cand) as im:
                        im = im.convert("RGB")
                        if im.width > MAX_W:
                            im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.LANCZOS)
                        im.save(SITE / overlay, "JPEG", quality=88, optimize=True)
                    break
            opts = options_for(task)
            out.append({
                "id": task["task_id"], "title": TITLES.get(task.get("question_type"), "Map challenge"),
                "question_type": task.get("question_type"), "difficulty": task.get("difficulty"),
                "image": f"img/{name}", "overlay": overlay, "question": task["question"],
                "answer": task["answer"], "answer_type": task["answer_type"],
                "ordered": task.get("ordered", True), "tolerance_abs": task.get("tolerance_abs"),
                "tolerance_rel": task.get("tolerance_rel"), "options": opts, "input": input_kind(task, opts),
                "steps": task.get("steps"), "models": models,
            })
    # the tasks both models missed first, then one miss, then the rest (stable within each group)
    out.sort(key=lambda t: sum(m["correct"] for m in t["models"].values()))
    return {"sources": used, "n_tasks": len(out), "tasks": out}


def main(argv: list[str]) -> int:
    if argv:
        sources = [tuple(a.split(":", 1)) for a in argv]
    elif (ROOT / "results/final/responses.csv").exists():
        sources = DEFAULT_SOURCES
    else:
        sources = SPIKE_SOURCES
    data = build(sources)
    if not data["tasks"]:
        print("no tasks with complete results for both models in", sources, file=sys.stderr)
        return 1
    (SITE / "tasks.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    missed = sum(not all(m["correct"] for m in t["models"].values()) for t in data["tasks"])
    print(f"site/tasks.json: {data['n_tasks']} tasks ({missed} that at least one model missed) from "
          f"{', '.join(s['tasks'] for s in data['sources'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
