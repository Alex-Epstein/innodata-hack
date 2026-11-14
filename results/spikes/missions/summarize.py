"""Print the #29 / #39 results table from the responses.csv files (no number is typed by hand).

    uv run python results/spikes/missions/summarize.py
"""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUNS = [("plain wording", HERE.parent / "multistep" / "results"), ("mission", HERE / "results"),
        ("mission", HERE / "results_flood"), ("mission", HERE / "results_wildfire")]
csv.field_size_limit(10 ** 9)

print("| Run | Question type | Haiku | Luna | Truth -> H: Haiku; L: Luna | finish | cost |")
print("|---|---|---|---|---|---|---|")
for label, folder in RUNS:
    if not (folder / "responses.csv").exists():
        continue
    rows = list(csv.DictReader(open(folder / "responses.csv", encoding="utf-8")))
    cost = json.loads((folder / "summary.json").read_text(encoding="utf-8"))["totals"]["cost_usd_all_calls"]
    types = list(dict.fromkeys(r["question_type"] for r in rows))
    for qt in types:
        mine = [r for r in rows if r["question_type"] == qt]
        cell = {}
        for short in ("haiku", "luna"):
            sel = [r for r in mine if short in r["model"]]
            cell[short] = f"{sum(r['correct'] == '1' for r in sel)}/{len(sel)}"
        detail = []
        for tid in dict.fromkeys(r["task_id"] for r in mine):
            pair = {("haiku" if "haiku" in r["model"] else "luna"): r for r in mine if r["task_id"] == tid}
            detail.append(f"{pair['haiku']['ref_answer']} -> H: {pair['haiku']['parsed']}; L: {pair['luna']['parsed']}")
        finish = ", ".join(sorted({r["finish_reason"] for r in mine}))
        print(f"| {label} | `{qt}` | {cell['haiku']} | {cell['luna']} | {' · '.join(detail)} | {finish} | "
              f"${cost:.4f} for the run |")
