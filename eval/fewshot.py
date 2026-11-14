"""Few-shot experiment: do two worked examples in the prompt help the models on new tasks of the same kind?

    EVAL_CACHE_DIR=cache/fewshot uv run python -m eval.fewshot --dry-run    # prompts + cost estimate, no calls
    EVAL_CACHE_DIR=cache/fewshot uv run python -m eval.fewshot              # 48 calls, writes results/extra/fewshot

For each topo pilot mission, seeds 0 and 1 are the worked examples and seeds 2 to 9 are the test tasks, so an
example is never a test task. A worked example is its image, its question and a
short solution written by a template from the task's `steps` and data JSON (code, not a person or a model). The
test task goes last, in exactly the eval prompt (scoring.build_prompt). Settings, request shape, retries and the
raw-log scrubbing are eval.client's; only the message holds 3 images instead of 1, so the call is assembled here.

The zero-shot baseline is read from results/pilot_topo_<mission>/responses.csv (same 8 test tasks, no new calls).
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import os
import re
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from eval import client, scoring
from eval.run import COLUMNS, _git_commit, load_tasks

ROOT = client.ROOT
MISSIONS = ("crossings", "sunset", "flood")
EXAMPLE_SEEDS = (0, 1)
TEST_SEEDS = tuple(range(2, 10))
OUT = ROOT / "results" / "extra" / "fewshot"

INTRO = ("Here are 2 worked examples of this kind of task, each with its map and a correct step-by-step "
         "solution. After them comes a new task with its own map. Solve the new task.")
EXAMPLE_HEADER = "Worked example {n} (map above):\n\n{question}\n\nWorked solution:\n{solution}"
TEST_HEADER = "New task (map above):\n\n{prompt}"


def tasks_dir(mission: str) -> Path:
    return ROOT / "tasks" / f"pilot_topo_{mission}"


def clock(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def compass(deg: float) -> str:
    names = ["north", "north-northeast", "northeast", "east-northeast", "east", "east-southeast", "southeast",
             "south-southeast", "south", "south-southwest", "southwest", "west-southwest", "west", "west-northwest",
             "northwest", "north-northwest"]
    return names[round(deg / 22.5) % 16]


# ---------------------------------------------------------------------------------------------- solutions
def solution(task: dict, data: dict) -> str:
    """The worked solution for an example task, from its steps and data only. Ends with the FINAL ANSWER line."""
    s, mission = task["steps"], task["template"]
    if mission == "crossings":
        levels = s["levels_crossed"]
        index = [lv for lv in levels if lv % data["index_interval_m"] == 0]
        assert len(levels) == s["contour_crossings"] == task["answer"] == s["uphill_crossings"] + s["downhill_crossings"]
        assert len(index) == s["index_contour_crossings"]
        idx = " and ".join(f"{lv} m line" + (f" crossed {index.count(lv)} times" if index.count(lv) > 1 else "")
                           for lv in dict.fromkeys(index))
        text = (f"Trace the trail from S to E with a finger and note every contour line it crosses, in order: "
                f"{', '.join(str(lv) for lv in levels)} m. "
                f"That is {s['uphill_crossings']} crossings going uphill and {s['downhill_crossings']} going downhill, "
                f"{s['contour_crossings']} crossings in total. {len(index)} of them are index contours (the heavy "
                f"{idx}), and they count too (leaving them out would give "
                f"{s['wrong_if_index_contours_left_out']}).")
        answer = s["contour_crossings"]
    elif mission == "sunset":
        m = data["mission"]
        daylight = m["sunset_min"] - m["now_min"]
        climb = s["uphill_crossings"] * m["minutes_per_uphill_contour"]
        walk = m["flat_walk_min"] + climb
        answer = daylight - walk
        assert (daylight, climb, walk, answer, m["flat_walk_min"]) == (
            s["daylight_minutes"], s["minutes_for_ascent"], s["walking_minutes"], task["answer"], s["flat_walk_min"])
        assert clock(m["now_min"] + walk) == s["arrival"]
        text = (f"Read the incident box: the time now is {clock(m['now_min'])} and sunset is {clock(m['sunset_min'])}, "
                f"so there are {daylight} minutes of daylight left. The flat walking time for the trail is "
                f"{m['flat_walk_min']} min. Trace the trail from S to H and note every contour line it crosses: "
                f"{s['uphill_crossings']} going uphill and {s['downhill_crossings']} going downhill. Only the uphill "
                f"ones add time: {s['uphill_crossings']} x {m['minutes_per_uphill_contour']} = {climb} min of climb. "
                f"Total walking time {m['flat_walk_min']} + {climb} = {walk} min, so the hiker arrives at "
                f"{s['arrival']}, which is {daylight} - {walk} = {answer} minutes before sunset.")
    elif mission == "flood":
        camps = {c["camp"]: c for c in s["camps"]}
        hit = s["flooded_camp"]
        assert hit == task["answer"] and camps[hit]["flooded"]
        bearing = s["water_sets_off_bearing_deg"]
        text = (f"The dam D stands at about {round(s['dam_elev_m'])} m. From D the steepest way down sets off "
                f"heading about {bearing} degrees ({compass(bearing)}), crossing each contour line at a right angle. "
                f"Keep following it downhill, bending wherever the contours bend so the path stays perpendicular to "
                f"them and runs down the valley floor. After about {round(s['water_route_length_m'])} m it reaches "
                f"{hit} (at {round(camps[hit]['elev_m'])} m).")
        decoys = []
        for key, why in (("dry_camp_most_directly_below_dam", "lies most directly below the dam in the first flow "
                          "direction"), ("nearest_campsite_to_dam", "is the nearest camp to the dam"),
                         ("lowest_campsite", "is the lowest camp")):
            c = s.get(key)
            if c and c != hit:
                decoys.append(f"{c} {why}, but the water's path passes "
                              f"{round(camps[c]['distance_to_water_route_m'])} m from it")
        if decoys:
            text += " Check the tempting wrong answers: " + "; ".join(decoys) + "."
        answer = hit
    else:
        raise ValueError(mission)
    return f"{text}\nFINAL ANSWER: {answer}"


# ---------------------------------------------------------------------------------------------- prompt and call
def build(mission: str):
    """-> (examples, tests): examples = [(task, solution)], tests = [task]."""
    tdir = tasks_dir(mission)
    by_seed = {t["seed"]: t for t in load_tasks(tdir)}
    examples = []
    for seed in EXAMPLE_SEEDS:
        t = by_seed[seed]
        data = json.loads((tdir / t["data"]).read_text(encoding="utf-8"))["data"]
        examples.append((t, solution(t, data)))
    return examples, [by_seed[s] for s in TEST_SEEDS]


def parts(mission: str, examples, test) -> list[tuple[str, object]]:
    """The message as an ordered list of ("text", str) and ("image", Path)."""
    tdir = tasks_dir(mission)
    out = [("text", INTRO)]
    for n, (t, sol) in enumerate(examples, 1):
        out += [("image", tdir / t["image"]),
                ("text", EXAMPLE_HEADER.format(n=n, question=t["question"], solution=sol))]
    out += [("image", tdir / test["image"]),
            ("text", TEST_HEADER.format(prompt=scoring.build_prompt(test["question"])))]
    return out


def call_multi(model: str, msg: list[tuple[str, object]]) -> dict:
    """eval.client.call with several images: same settings, retries, cache layout and record shape."""
    settings = dict(client.SETTINGS)
    texts = [v for k, v in msg if k == "text"]
    hashes = [client.image_sha256(v) for k, v in msg if k == "image"]
    prompt_key = "\n\n<image>\n\n".join(texts)
    key = client.cache_key(model, "fewshot\n" + prompt_key, "+".join(hashes), settings)
    path = client.cache_dir() / f"{key}.json"
    if path.exists():
        rec = json.loads(path.read_text(encoding="utf-8"))
        rec["cached"] = True
        return rec
    content, logged = [], []
    for k, v in msg:
        if k == "text":
            content.append({"type": "text", "text": v})
            logged.append({"type": "text", "text": v})
        else:
            p = Path(v)
            data = base64.b64encode(p.read_bytes()).decode()
            content.append({"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}})
            logged.append({"type": "image_url", "image_url": {"file": p.name, "sha256": client.image_sha256(p)}})
    body = {"model": model, "messages": [{"role": "user", "content": content}], **settings, "usage": {"include": True}}
    rec = {"key": key, "model": model, "request": {**body, "messages": [{"role": "user", "content": logged}]},
           "response": None, "attempts": [], "error": "", "cached": False, "mock": False,
           "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    rec["response"], rec["attempts"] = client._post_with_retries(body)
    if rec["response"] is None:
        rec["error"] = "api_error"
        return rec
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    return rec


def row_for(model: str, task: dict, rec: dict) -> dict:
    """Same logic and columns as eval.run.evaluate_one."""
    r = client.reply(rec)
    row = {"model": model, "task_id": task["task_id"], "status": "ok", "parsed": "",
           "question_type": task.get("question_type") or "unknown", "response": r["text"],
           "ref_answer": scoring.ref_answer_cell(task["answer"]), "correct": "",
           "finish_reason": r["finish_reason"], "error": ""}
    if rec["error"]:
        row["status"], row["error"] = "api_error", "api_error"
    elif r["finish_reason"] == "length":
        row["error"] = "length"
    elif r["finish_reason"] != "stop":
        row["status"], row["error"] = "api_error", "api_error"
    else:
        row["parsed"] = scoring.parse_final_answer(r["text"])
        row["correct"] = "1" if scoring.score(row["parsed"], task) else "0"
    return row


def baseline(mission: str) -> dict:
    path = ROOT / "results" / f"pilot_topo_{mission}" / "responses.csv"
    with open(path, encoding="utf-8") as f:
        return {(r["model"], r["task_id"]): r for r in csv.DictReader(f)}


# ---------------------------------------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="print one prompt per mission and the estimate, no calls")
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args(argv)
    if not os.environ.get("EVAL_CACHE_DIR"):
        print("set EVAL_CACHE_DIR (e.g. cache/fewshot) so this never mixes with the eval cache", file=sys.stderr)
        return 2

    plan, example_ids = [], {}
    for mission in MISSIONS:
        examples, tests = build(mission)
        example_ids[mission] = [t["task_id"] for t, _ in examples]
        assert not set(example_ids[mission]) & {t["task_id"] for t in tests}
        for t in tests:
            for model in client.MODELS:
                plan.append((mission, model, t, parts(mission, examples, t)))
    # Estimate from the zero-shot pilot: prompt tokens x3 (3 images) plus the example text; completion as before.
    est = len(plan) * 0.0028 * 1.8
    print(f"{len(plan)} calls, 3 images each, estimate ~${est:.2f} (upper ~${est * 2:.2f})", flush=True)
    if a.dry_run:
        for mission in MISSIONS:
            msg = next(p for m, _, _, p in plan if m == mission)
            print(f"\n===== {mission}")
            for k, v in msg:
                print(f"[image {Path(v).name}]" if k == "image" else v)
        return 0

    stop = threading.Event()

    def work(item):
        mission, model, task, msg = item
        if stop.is_set():
            return None
        rec = call_multi(model, msg)
        row = row_for(model, task, rec)
        if row["error"]:
            stop.set()
            print(f"STOP: {model} on {task['task_id']}: {row['error']} ({row['finish_reason']})", file=sys.stderr)
        else:
            print(f"{model:28s} {task['task_id']}  parsed={row['parsed']!r:8s} ref={row['ref_answer']:4s} "
                  f"correct={row['correct']}{'  (cached)' if rec.get('cached') else ''}", flush=True)
        return row, rec

    try:
        with ThreadPoolExecutor(max_workers=a.workers) as pool:
            results = list(pool.map(work, plan))
    except client.FatalAPIError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2
    if stop.is_set() or any(r is None for r in results):
        print("Stopped: a call errored or was cut off. Nothing written to results/.", file=sys.stderr)
        return 1

    raw = OUT / "raw"
    raw.mkdir(parents=True, exist_ok=True)
    for old in raw.glob("*.json"):
        old.unlink()
    rows, cost_all, cost_new = [], 0.0, 0.0
    for (mission, model, task, _), (row, rec) in zip(plan, results):
        rows.append(row)
        name = f"{task['task_id']}__{re.sub(r'[^A-Za-z0-9.-]+', '_', model)}.json"
        (raw / name).write_text(json.dumps(client.for_raw_log(rec), ensure_ascii=False, indent=1), encoding="utf-8")
        c = client.reply(rec)["cost"] or 0
        cost_all += c
        cost_new += 0 if rec.get("cached") else c
    with open(OUT / "responses.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)

    table = {}
    for mission in MISSIONS:
        base = baseline(mission)
        for model in client.MODELS:
            mine = [r for (m, mo, _, _), r in zip(plan, rows) if m == mission and mo == model]
            zero = [base[(model, r["task_id"])] for r in mine]
            assert all(z["error"] == "" and z["correct"] in ("0", "1") for z in zero)
            table[f"{mission} | {model}"] = {
                "zero_shot": sum(z["correct"] == "1" for z in zero), "two_shot": sum(r["correct"] == "1" for r in mine),
                "n": len(mine),
                "per_task": {r["task_id"]: {"ref": r["ref_answer"], "zero_shot": z["parsed"], "two_shot": r["parsed"]}
                             for r, z in zip(mine, zero)}}
    config = {
        "experiment": "2 worked examples in context vs zero-shot, same 8 test tasks per mission",
        "models": list(client.MODELS), "endpoint": client.URL, **client.SETTINGS,
        "prompt_structure": ["text: INTRO", "image: example 1", "text: EXAMPLE_HEADER (n=1)", "image: example 2",
                             "text: EXAMPLE_HEADER (n=2)", "image: test task", "text: TEST_HEADER"],
        "intro": INTRO, "example_header": EXAMPLE_HEADER, "test_header": TEST_HEADER,
        "prompt_template": scoring.PROMPT_TEMPLATE,
        "solution_source": "eval/fewshot.py solution(): one template per mission, filled from the task's steps "
                           "and data JSON; asserted equal to the task's answer",
        "example_task_ids": example_ids,
        "test_task_ids": {m: [f"topo-{m}-{s:06d}" for s in TEST_SEEDS] for m in MISSIONS},
        "baseline": {m: f"results/pilot_topo_{m}/responses.csv (zero-shot, not re-called)" for m in MISSIONS},
        "tasks_folders": {m: f"tasks/pilot_topo_{m}" for m in MISSIONS},
        "cache_dir": "cache/fewshot (EVAL_CACHE_DIR)",
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"), "git_commit": _git_commit(),
        "totals": {"calls": len(rows), "from_cache": sum(bool(rec.get("cached")) for _, rec in results),
                   "incomplete": sum(r["error"] != "" for r in rows),
                   "retried_calls": sum(len(rec.get("attempts") or []) > 1 for _, rec in results),
                   "cost_usd_all_calls": cost_all, "cost_usd_new_calls": cost_new},
        "results": table,
    }
    (OUT / "run_config.json").write_text(json.dumps(config, indent=1), encoding="utf-8")
    print()
    for k, v in table.items():
        print(f"{k:42s} zero-shot {v['zero_shot']}/{v['n']}   2-shot {v['two_shot']}/{v['n']}")
    print(f"cost: new ${cost_new:.4f}, all ${cost_all:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
