"""Run the checks on one task or a whole task folder, write the funnel report."""
from __future__ import annotations

import csv
import json
import traceback
from collections import Counter
from pathlib import Path
from typing import Iterator

from factory import registry
from factory.tasks import load_side, load_tasks, write_tasks
from validate.checks import CHECKS, NAMES, Ctx


def iter_checks(tasks_dir, rec: dict, skip: tuple[str, ...] = ()) -> Iterator[tuple[str, bool, str]]:
    """Yield (name, passed, detail) per check, in CHECKS order. A check that crashes fails with the reason."""
    tasks_dir = Path(tasks_dir)
    fams = registry.discover(quiet=True)
    ctx = Ctx(tasks_dir=tasks_dir, rec=rec, family=fams.get(rec.get("family")),
              side=load_side(tasks_dir, rec.get("task_id", "")))
    for check in CHECKS:
        if check.__name__ in skip:
            continue
        try:
            name, ok, detail = check(ctx)
        except Exception as e:
            last = traceback.format_exception_only(type(e), e)[-1].strip()
            name, ok, detail = check.__name__, False, f"check crashed: {last}"
        yield name, bool(ok), detail


def validate_task(tasks_dir, rec: dict, skip: tuple[str, ...] = ()) -> list[tuple[str, bool, str]]:
    return list(iter_checks(tasks_dir, rec, skip))


def needs_image_from_blind(blind_dir) -> dict[str, tuple[bool, str]]:
    """From a blind run (eval.run --blind): {task_id: (needs_image, detail)}. A task leaks when every model
    in the run answered it correctly without the image."""
    with open(Path(blind_dir) / "responses.csv", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    by_task: dict[str, list[dict]] = {}
    for r in rows:
        by_task.setdefault(r["task_id"], []).append(r)
    out = {}
    for tid, rs in by_task.items():
        right = [r["model"] for r in rs if r.get("correct") == "1"]
        leak = len(rs) >= 2 and len(right) == len(rs)
        out[tid] = (not leak, f"blind: {len(right)}/{len(rs)} models right without the image"
                    + (" (answerable without the image)" if leak else ""))
    return out


def validate_set(tasks_dir, drop_invalid: bool = False, blind_results=None, skip: tuple[str, ...] = (),
                 verbose: bool = True) -> dict:
    """Check every task in tasks_dir, write `checks` into tasks.jsonl and validation_report.json."""
    tasks_dir = Path(tasks_dir)
    records = load_tasks(tasks_dir)
    blind = needs_image_from_blind(blind_results) if blind_results else None
    ids = Counter(r.get("task_id") for r in records)
    names = [n for n in NAMES if n not in skip] + (["needs_image"] if blind is not None else [])
    failures: dict[str, dict[str, str]] = {}
    for rec in records:
        results = validate_task(tasks_dir, rec, skip)
        if ids[rec.get("task_id")] > 1:
            results = [(n, False, d + "; duplicate task_id") if n == "schema" else (n, ok, d)
                       for n, ok, d in results]
        if blind is not None:
            ok, detail = blind.get(rec.get("task_id"), (False, "not in the blind run"))
            results.append(("needs_image", ok, detail))
        rec["checks"] = {n: ok for n, ok, _ in results}
        bad = {n: d for n, ok, d in results if not ok}
        if bad:
            failures[rec["task_id"]] = bad
        if verbose:
            mark = "ok  " if not bad else "FAIL"
            print(f"{mark} {rec['task_id']}" + ("" if not bad else "  " + "; ".join(f"{n}: {d}" for n, d in bad.items())))

    passed = [r for r in records if all(r["checks"].values())]
    per_check = {n: {"passed": sum(r["checks"].get(n) is True for r in records),
                     "failed": sum(r["checks"].get(n) is False for r in records)} for n in names}
    cumulative, alive = {}, list(records)
    for n in names:
        alive = [r for r in alive if r["checks"].get(n)]
        cumulative[n] = len(alive)
    gen_log = tasks_dir / "generation_log.json"
    generation = None
    if gen_log.exists():
        g = json.loads(gen_log.read_text(encoding="utf-8"))
        generation = {k: g.get(k) for k in ("attempted", "rejected_count", "kept")}
    report = {"tasks_folder": str(tasks_dir), "generation": generation, "checked": len(records),
              "all_passed": len(passed), "per_check": per_check, "cumulative_funnel": cumulative,
              "failures": failures, "dropped": []}

    if drop_invalid:
        dropped = [r for r in records if not all(r["checks"].values())]
        for r in dropped:
            for rel in (r.get("image"), r.get("data"), f"layout/{r.get('task_id')}.json"):
                if rel and (tasks_dir / rel).is_file():
                    (tasks_dir / rel).unlink()
        report["dropped"] = [r["task_id"] for r in dropped]
        records = passed
    write_tasks(tasks_dir, records)
    (tasks_dir / "validation_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False),
                                                      encoding="utf-8")
    return report


def print_funnel(report: dict) -> None:
    g = report.get("generation")
    if g:
        print(f"generated: {g['attempted']} attempted, {g['rejected_count']} seeds rejected, {g['kept']} kept")
    print(f"checked {report['checked']} tasks")
    for n, c in report["per_check"].items():
        print(f"  {n:<24} {c['passed']:>4} pass  {c['failed']:>4} fail   (still alive: {report['cumulative_funnel'][n]})")
    print(f"all checks passed: {report['all_passed']}/{report['checked']}"
          + (f"; dropped {len(report['dropped'])}" if report["dropped"] else ""))


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(prog="python -m validate", description="Run every check on a task folder.")
    ap.add_argument("--tasks", required=True)
    ap.add_argument("--drop-invalid", action="store_true", help="keep only tasks that pass every check")
    ap.add_argument("--blind-results", help="a blind eval run folder (responses.csv) for the needs_image check")
    ap.add_argument("--skip", action="append", default=[], choices=NAMES, help="skip a check (repeatable)")
    a = ap.parse_args(argv)
    rep = validate_set(a.tasks, a.drop_invalid, a.blind_results, tuple(a.skip))
    print_funnel(rep)
    return 0 if rep["all_passed"] == rep["checked"] or (a.drop_invalid and rep["all_passed"] > 0) else 1
