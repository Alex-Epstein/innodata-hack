"""Build one task through a family's build() and normalize the record to contracts/SCHEMA.md.

Files in a task folder (tasks/<set>/):
    tasks.jsonl              one record per kept task (SCHEMA.md fields + steps + hashes + checks)
    data/<task_id>.json      the structured data, written by the family BEFORE the image
    images/<task_id>.png     rendered from the data only
    layout/<task_id>.json    {"layout": {"texts": [...], "probes": [...]}, "overlay": ...} from build(),
                             read by validate/ (legibility, render_matches_data) and the demo overlay
    generation_log.json      what generate attempted, rejected (and why) and kept
    validation_report.json   the funnel written by validate
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import ModuleType

from factory.render import sha256_file

# Field order in tasks.jsonl: the required ones first, so a line reads well.
ORDER = ["task_id", "image", "question", "answer", "answer_type", "tolerance_rel", "tolerance_abs", "options",
         "ordered", "seed", "generator_version", "question_type", "family", "template", "difficulty", "data",
         "references", "steps", "image_sha256", "data_sha256", "data_written_first", "checks"]
SIDE_KEYS = ("layout", "overlay")             # kept out of tasks.jsonl, stored in layout/<task_id>.json


def is_reject(family: ModuleType, exc: BaseException) -> bool:
    return isinstance(exc, family.RejectSeed) or type(exc).__name__ == "RejectSeed"


def _rel(path, out_dir: Path) -> str:
    p = Path(path)
    if p.is_absolute():
        try:
            p = p.resolve().relative_to(out_dir.resolve())
        except ValueError:
            pass
    return p.as_posix()


def build_task(family: ModuleType, seed: int, template: str, difficulty: int, out_dir) -> dict:
    """Call family.build() and return the normalized record. Raises the family's RejectSeed unchanged.

    Writes the layout sidecar and records the image/data SHA-256 and whether the data file was written
    before the image (mtime in nanoseconds, measured right here)."""
    out_dir = Path(out_dir)
    (out_dir / "data").mkdir(parents=True, exist_ok=True)
    (out_dir / "images").mkdir(parents=True, exist_ok=True)
    if template not in family.TEMPLATES:
        raise ValueError(f"family {family.FAMILY!r} has no template {template!r} (has {list(family.TEMPLATES)})")
    raw = family.build(int(seed), template, int(difficulty), out_dir)
    if not isinstance(raw, dict):
        raise TypeError(f"{family.FAMILY}.build() returned {type(raw).__name__}, expected a dict")
    rec = {k: v for k, v in raw.items() if k not in SIDE_KEYS}
    tid = rec.get("task_id") or f"{family.FAMILY}-{template}-{int(seed):06d}"
    rec["task_id"] = tid
    rec["image"] = _rel(rec.get("image") or f"images/{tid}.png", out_dir)
    rec["data"] = _rel(rec.get("data") if isinstance(rec.get("data"), (str, os.PathLike))
                       else f"data/{tid}.json", out_dir)
    rec["seed"] = int(seed)
    rec["generator_version"] = family.VERSION
    rec["question_type"] = f"{family.FAMILY}.{template}"
    rec["family"] = family.FAMILY
    rec["template"] = template
    rec["difficulty"] = int(difficulty)
    if not rec.get("references"):
        refs = family.REFERENCES.get(template) if isinstance(family.REFERENCES, dict) else None
        rec["references"] = list(refs or family.REFERENCES.get("*") or [])
    rec.setdefault("steps", [])

    img, data = out_dir / rec["image"], out_dir / rec["data"]
    if img.exists():
        rec["image_sha256"] = sha256_file(img)
    if data.exists():
        rec["data_sha256"] = sha256_file(data)
    if img.exists() and data.exists():
        rec["data_written_first"] = data.stat().st_mtime_ns <= img.stat().st_mtime_ns

    side = {k: raw.get(k) for k in SIDE_KEYS if raw.get(k) is not None}
    (out_dir / "layout").mkdir(parents=True, exist_ok=True)
    (out_dir / "layout" / f"{tid}.json").write_text(json.dumps(side, indent=1, ensure_ascii=False),
                                                    encoding="utf-8")
    return ordered(rec)


def ordered(rec: dict) -> dict:
    head = {k: rec[k] for k in ORDER if k in rec}
    return {**head, **{k: v for k, v in rec.items() if k not in head}}


def load_tasks(tasks_dir) -> list[dict]:
    f = Path(tasks_dir) / "tasks.jsonl"
    if not f.exists():
        raise FileNotFoundError(f"no tasks.jsonl in {tasks_dir}")
    return [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_tasks(tasks_dir, records: list[dict]) -> None:
    f = Path(tasks_dir) / "tasks.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(ordered(r), ensure_ascii=False) + "\n" for r in records)
    tmp = f.with_suffix(".jsonl.tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, f)


def load_side(tasks_dir, task_id: str) -> dict:
    f = Path(tasks_dir) / "layout" / f"{task_id}.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def load_data(tasks_dir, rec: dict) -> dict:
    return json.loads((Path(tasks_dir) / rec["data"]).read_text(encoding="utf-8"))


def parse_seeds(spec: str) -> list[int]:
    """'0-9' -> 0..9, '1,5,7' -> [1, 5, 7], '0-2,10' -> [0, 1, 2, 10]. Seeds are non-negative."""
    out: list[int] = []
    for part in str(spec).replace(" ", "").split(","):
        if not part:
            continue
        lo, _, hi = part.partition("-")
        out.extend(range(int(lo), int(hi) + 1) if hi else [int(lo)])
    return list(dict.fromkeys(out))
