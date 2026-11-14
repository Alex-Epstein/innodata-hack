"""Print the spike report tables from results/responses.csv and results/summary.json (nothing typed by hand).

    uv run python results/spikes/topo/summarize.py
"""
import csv
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
tasks = {t["task_id"]: t for t in map(json.loads, (HERE / "tasks" / "tasks.jsonl").read_text().splitlines())}
with open(HERE / "results" / "responses.csv", newline="", encoding="utf-8") as f:
    rows = list(csv.DictReader(f))
models = list(dict.fromkeys(r["model"] for r in rows))
names = {1: "L1: which of two points is higher", 2: "L2: elevation of point P on a contour",
         3: "L3: contour lines crossed by a trail"}

print("| Level | " + " | ".join(models) + " |")
print("|---|" + "---|" * len(models))
for lv in (1, 2, 3):
    cells = []
    for m in models:
        mine = [r for r in rows if r["model"] == m and tasks[r["task_id"]]["difficulty"] == lv]
        cells.append(f"{sum(r['correct'] == '1' for r in mine)} right, {sum(r['correct'] == '0' for r in mine)} wrong, "
                     f"{sum(r['error'] != '' for r in mine)} cut off or failed")
    print(f"| {names[lv]} | " + " | ".join(cells) + " |")

totals = json.loads((HERE / "results" / "summary.json").read_text())["totals"]
print("\ntotals:", json.dumps(totals))
print("finish_reason other than stop:", [(r["model"], r["task_id"], r["finish_reason"], r["error"]) for r in rows
                                         if r["finish_reason"] != "stop" or r["error"]] or "none")
print("\nper task (model answer vs truth):")
for r in rows:
    print(f"  {r['task_id']} {r['model'].split('/')[-1]}: parsed {r['parsed']!r} truth {r['ref_answer']!r} "
          f"correct {r['correct'] or '-'} {r['finish_reason']}")
