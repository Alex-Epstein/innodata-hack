"""Print the pilot table for the topo family from results/pilot_topo_<template>/responses.csv (nothing typed by hand).

    uv run python -m gen.topo.pilot_report            # markdown table + per-task lines
"""
import csv
import json
from pathlib import Path

from gen import topo

ROOT = Path(__file__).resolve().parents[2]
csv.field_size_limit(10 ** 9)


def main():
    head, detail = [], []
    for template in topo.TEMPLATES:
        res, tasks = ROOT / "results" / f"pilot_topo_{template}", ROOT / "tasks" / f"pilot_topo_{template}"
        if not (res / "responses.csv").exists():
            continue
        rows = list(csv.DictReader(open(res / "responses.csv", encoding="utf-8")))
        total = json.loads((res / "summary.json").read_text(encoding="utf-8"))["totals"]
        score = {}
        for short in ("haiku", "luna"):
            mine = [r for r in rows if short in r["model"]]
            score[short] = (sum(r["correct"] == "1" for r in mine), len(mine))
        finish = ", ".join(sorted({r["finish_reason"] for r in rows}))
        keep = min(score["haiku"][0], score["luna"][0]) <= 5
        head.append(f"| `{template}` | {score['haiku'][0]}/{score['haiku'][1]} | {score['luna'][0]}/{score['luna'][1]} | "
                    f"{finish} | ${total['cost_usd_all_calls']:.4f} | {'KEEP' if keep else 'DROP'} (rule: at most 5 of 10 "
                    f"for at least one model) |")
        for t in [json.loads(l) for l in (tasks / "tasks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]:
            got = {("haiku" if "haiku" in r["model"] else "luna"): r for r in rows if r["task_id"] == t["task_id"]}
            mark = lambda r: f"{r['parsed']} {'✓' if r['correct'] == '1' else '✗'}"
            detail.append(f"- `{t['task_id']}` truth {t['answer']} · Haiku {mark(got['haiku'])} · Luna {mark(got['luna'])}")
    print("| Template (difficulty 3, seeds 0-9) | Haiku | Luna | finish | cost | Verdict |\n|---|---|---|---|---|---|")
    print("\n".join(head))
    print()
    print("\n".join(detail))


if __name__ == "__main__":
    main()
