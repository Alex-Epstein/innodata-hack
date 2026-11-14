"""Evaluate both models on a task folder and write the results folder (contracts/SCHEMA.md).

    uv run python -m eval.run --tasks tasks/final --out results/final

Writes  <out>/responses.csv   one row per model per task
        <out>/run_config.json models, settings, prompt template, commit, totals
        <out>/raw/            one JSON per call: the request (no image bytes, no key) and the raw reply
        <out>/summary.json    accuracy per model and per question_type (computed from responses.csv rows)

Exit code 0 only if every row is complete (finish_reason stop, no error). Anything else must be
fixed and the whole evaluation run again; cached calls make the rerun free.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from eval import client, scoring

COLUMNS = ["model", "task_id", "status", "parsed", "question_type", "response", "ref_answer", "correct",
           "finish_reason", "error"]
EST_USD_PER_CALL = 0.005        # planning figure from docs/BRIEFING.md; real cost is read from each reply
CSV_CELL_LIMIT = 131072         # the judges' CSV reader stops at this many characters per cell


def load_tasks(tasks_dir: Path) -> list[dict]:
    lines = (tasks_dir / "tasks.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def evaluate_one(model: str, task: dict, tasks_dir: Path, blind: bool = False):
    """One model on one task -> (responses.csv row, raw record)."""
    image = None if blind else tasks_dir / task["image"]
    rec = client.call(model, scoring.build_prompt(task["question"]), image)
    r = client.reply(rec)
    row = {"model": model, "task_id": task["task_id"], "status": "ok", "parsed": "",
           "question_type": task.get("question_type") or task.get("family") or "unknown",
           "response": r["text"], "ref_answer": scoring.ref_answer_cell(task["answer"]), "correct": "",
           "finish_reason": r["finish_reason"], "error": ""}
    if rec["error"]:                                  # every retry failed
        row["status"], row["error"] = "api_error", "api_error"
    elif r["finish_reason"] == "length":              # cut off by max_tokens: not a model failure
        row["error"] = "length"
    elif r["finish_reason"] != "stop":                # content filter etc.: not a complete reply
        row["status"], row["error"] = "api_error", "api_error"
    else:
        row["parsed"] = scoring.parse_final_answer(r["text"])
        row["correct"] = "1" if scoring.score(row["parsed"], task) else "0"
    return row, rec


def evaluate(tasks_dir, out_dir, models=client.MODELS, workers: int = 4, blind: bool = False) -> dict:
    """Run every (model, task) pair, write the results folder, return the summary dict."""
    tasks_dir, out_dir = Path(tasks_dir), Path(out_dir)
    tasks = load_tasks(tasks_dir)
    pairs = [(m, t) for t in tasks for m in models]
    print(f"{len(tasks)} tasks x {len(models)} models = {len(pairs)} calls, at most "
          f"~${len(pairs) * EST_USD_PER_CALL:.2f} (estimate; cached calls cost nothing)", flush=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda p: evaluate_one(p[0], p[1], tasks_dir, blind), pairs))

    (out_dir / "raw").mkdir(parents=True, exist_ok=True)
    for old in (out_dir / "raw").glob("*.json"):      # the folder always reflects exactly this run
        old.unlink()
    rows = []
    for (model, task), (row, rec) in zip(pairs, results):
        rows.append(row)
        name = f"{task['task_id']}__{re.sub(r'[^A-Za-z0-9.-]+', '_', model)}.json"
        (out_dir / "raw" / name).write_text(json.dumps(client.for_raw_log(rec), ensure_ascii=False, indent=1), encoding="utf-8")
        if len(row["response"]) > CSV_CELL_LIMIT:
            print(f"WARNING: reply of {model} on {task['task_id']} is {len(row['response'])} characters; the "
                  f"judges' CSV reader stops at {CSV_CELL_LIMIT}", file=sys.stderr)

    with open(out_dir / "responses.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")   # same bytes on every OS
        w.writeheader()
        w.writerows(rows)

    summary = summarize(rows, [rec for _, rec in results])
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    config = {
        "models": list(models), "endpoint": client.URL, **client.SETTINGS,
        "prompt_template": scoring.PROMPT_TEMPLATE, "image_sent": not blind,
        "retries": {"max_attempts": client.MAX_ATTEMPTS, "retried": "HTTP 408/409/425/429, 5xx, timeouts, "
                    "error bodies, empty replies", "backoff": "Retry-After if given, else 2^n s up to 60 s"},
        "raw_log_note": "raw/ holds each request (no image bytes, no key) and the full reply; opaque provider "
                        "blobs (encrypted reasoning data, reasoning signatures) are replaced by their SHA-256",
        "tasks_folder": str(tasks_dir), "n_tasks": len(tasks), "mock": os.environ.get("MOCK") == "1",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "git_commit": _git_commit(),
        "totals": summary["totals"],
    }
    (out_dir / "run_config.json").write_text(json.dumps(config, indent=1), encoding="utf-8")
    return summary


def summarize(rows: list[dict], records: list[dict]) -> dict:
    def acc(sel):
        done = [r for r in sel if r["correct"] in ("0", "1")]
        return {"correct": sum(r["correct"] == "1" for r in done), "scored": len(done), "rows": len(sel)}

    by_model = {}
    for m in dict.fromkeys(r["model"] for r in rows):
        mine = [r for r in rows if r["model"] == m]
        by_model[m] = {**acc(mine), "by_question_type": {
            q: acc([r for r in mine if r["question_type"] == q])
            for q in dict.fromkeys(r["question_type"] for r in mine)}}
    replies = [client.reply(rec) for rec in records]
    return {"by_model": by_model, "totals": {
        "calls": len(rows),
        "from_cache": sum(bool(rec.get("cached")) for rec in records),
        "incomplete": sum(r["error"] != "" for r in rows),
        "retried_calls": sum(len(rec.get("attempts") or []) > 1 for rec in records),
        "cost_usd_all_calls": sum(r["cost"] or 0 for r in replies),
        "cost_usd_new_calls": sum(r["cost"] or 0 for r, rec in zip(replies, records) if not rec.get("cached")),
    }}


def _git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], cwd=client.ROOT, capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate the models on a task folder and write the results folder.")
    ap.add_argument("--tasks", required=True, help="task folder holding tasks.jsonl, e.g. tasks/final")
    ap.add_argument("--out", required=True, help="results folder to write, e.g. results/final")
    ap.add_argument("--model", action="append", help=f"repeatable; default: {', '.join(client.MODELS)}")
    ap.add_argument("--workers", type=int, default=4, help="concurrent calls (default 4)")
    ap.add_argument("--blind", action="store_true",
                    help="send no image (the 'needs the image' check); write to results/extra/, never final")
    a = ap.parse_args(argv)
    try:
        s = evaluate(a.tasks, a.out, tuple(a.model) if a.model else client.MODELS, a.workers, a.blind)
    except client.FatalAPIError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2
    for m, v in s["by_model"].items():
        print(f"{m}: {v['correct']}/{v['scored']} correct ({v['rows']} rows)")
        for q, qv in v["by_question_type"].items():
            print(f"    {q}: {qv['correct']}/{qv['scored']}")
    t = s["totals"]
    print(f"calls {t['calls']} (cached {t['from_cache']}, retried {t['retried_calls']}), "
          f"new spend ${t['cost_usd_new_calls']:.4f}, incomplete rows {t['incomplete']}")
    if t["incomplete"]:
        print("INCOMPLETE: some rows have an API error or were cut off. Fix the cause and rerun everything.",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
