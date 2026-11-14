"""Rerun the 9 calendar spike tasks with max_tokens 32000 (the spike used 16000 and Haiku was cut off twice).

    uv run python results/spikes/calendar_32k/run.py

Same images, same questions (sent exactly as in ../calendar/tasks.json), same answer parser as
../calendar/run.py. The only change is that calls go through eval/client.py, whose fixed settings are
temperature 0, reasoning effort high, max_tokens 32000. Replies are cached, so a rerun costs nothing.
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT))
from eval import client  # noqa: E402

SPIKE = HERE.parent / "calendar"


def parse(text):          # copied from ../calendar/run.py so the two runs are scored the same way
    m = re.findall(r"FINAL ANSWER:\s*\**\s*([A-Za-z]+)\.?,?\s+(\d{1,2})[:.](\d{2})", text)
    if not m:
        return None
    d, h, mi = m[-1]
    return f"{d[:3].capitalize()} {int(h):02d}:{mi}"


def one(job):
    task, model = job
    rec = client.call(model, task["question"], SPIKE / "images" / f"{task['id']}.png")
    r = client.reply(rec)
    name = f"{task['id']}__{model.split('/')[-1]}.json"
    (HERE / "raw" / name).write_text(json.dumps(rec, ensure_ascii=False, indent=1))
    complete = not rec["error"] and r["finish_reason"] == "stop"
    pred = parse(r["text"]) if complete else None
    u = r["usage"]
    return {"task": task["id"], "level": task["level"], "model": model, "pred": pred, "truth": task["answer"],
            "correct": (pred == task["answer"]) if complete else None, "finish_reason": r["finish_reason"],
            "error": rec["error"], "cost": r["cost"], "completion_tokens": u.get("completion_tokens"),
            "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            "cached": rec["cached"], "attempts": len(rec["attempts"])}


if __name__ == "__main__":
    tasks = json.loads((SPIKE / "tasks.json").read_text())
    jobs = [(t, m) for t in tasks for m in client.MODELS]
    (HERE / "raw").mkdir(exist_ok=True)
    print(f"{len(jobs)} calls, max_tokens {client.SETTINGS['max_tokens']}", flush=True)
    with ThreadPoolExecutor(4) as ex:
        results = list(ex.map(one, jobs))
    (HERE / "results.json").write_text(json.dumps(
        {"settings": client.SETTINGS, "models": list(client.MODELS), "results": results}, indent=1))
    for r in results:
        print(r["task"], r["model"].split("/")[-1], "pred", r["pred"], "truth", r["truth"], "correct", r["correct"],
              r["finish_reason"], "tokens", r["completion_tokens"], "cost", r["cost"], r["error"])
    print("total cost", sum(r["cost"] or 0 for r in results),
          "new", sum(r["cost"] or 0 for r in results if not r["cached"]))
