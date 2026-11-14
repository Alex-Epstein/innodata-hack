"""Directive #26: rerun ONLY the three calendar L3 tasks on claude-haiku-5.5 with max_tokens 64000.

    uv run python results/spikes/calendar_64k/run.py

At 16000 and at 32000 Haiku was cut off (`finish_reason: length`) on L3_s1 and L3_s2. Same images and
questions as ../calendar/tasks.json, same answer parser, calls through eval/client.py (temperature 0,
reasoning effort high, max_tokens 64000). Replies are cached.
"""
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[2]))
from eval import client  # noqa: E402

SPIKE = HERE.parent / "calendar"
MODEL = "anthropic/claude-haiku-5.5"


def parse(text):          # copied from ../calendar/run.py
    m = re.findall(r"FINAL ANSWER:\s*\**\s*([A-Za-z]+)\.?,?\s+(\d{1,2})[:.](\d{2})", text)
    if not m:
        return None
    d, h, mi = m[-1]
    return f"{d[:3].capitalize()} {int(h):02d}:{mi}"


def one(task):
    rec = client.call(MODEL, task["question"], SPIKE / "images" / f"{task['id']}.png")
    r = client.reply(rec)
    (HERE / "raw" / f"{task['id']}__claude-haiku-5.5.json").write_text(
        json.dumps(client.for_raw_log(rec), ensure_ascii=False, indent=1))
    complete = not rec["error"] and r["finish_reason"] == "stop"
    pred = parse(r["text"]) if complete else None
    u = r["usage"]
    return {"task": task["id"], "model": MODEL, "pred": pred, "truth": task["answer"],
            "correct": (pred == task["answer"]) if complete else None, "finish_reason": r["finish_reason"],
            "error": rec["error"], "cost": r["cost"], "completion_tokens": u.get("completion_tokens"),
            "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            "seconds": sum(a["seconds"] for a in rec["attempts"]), "attempts": len(rec["attempts"]),
            "cached": rec["cached"]}


if __name__ == "__main__":
    assert client.SETTINGS["max_tokens"] == 64000, client.SETTINGS
    tasks = [t for t in json.loads((SPIKE / "tasks.json").read_text()) if t["level"] == "L3"]
    with ThreadPoolExecutor(3) as ex:
        results = list(ex.map(one, tasks))
    (HERE / "results.json").write_text(json.dumps({"settings": client.SETTINGS, "results": results}, indent=1))
    for r in results:
        print(r["task"], "pred", r["pred"], "truth", r["truth"], "correct", r["correct"], r["finish_reason"],
              "tokens", r["completion_tokens"], "reasoning", r["reasoning_tokens"], "cost", r["cost"],
              "seconds", r["seconds"], r["error"])
    print("total cost", sum(r["cost"] or 0 for r in results))
