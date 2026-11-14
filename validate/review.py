"""Advisory LLM review of a task folder: a careful reader looks for problems a human checker would raise.

    uv run python -m validate.review --tasks <dir> [--limit N] [--dry-run]

A reviewer, not a solver. The reference answer still comes only from code; this never changes an answer,
never edits tasks.jsonl and never drops a task. It writes review_report.json next to tasks.jsonl and prints a
table (task_id, verdict, issue kinds). Every flagged task goes to the human hand check (README "Hand check").

For each task the model sees the image, the question, the reference answer and the `steps` chain, and returns
    {"verdict": "ok" | "flag", "issues": [{"kind": ..., "detail": ...}], "realism_notes": "..."}
with kinds: ambiguity (a careful reader could reasonably reach another answer), legibility (something the answer
needs is too small, covered or cut off), leakage (the question gives the answer away), realism (what gives the
image away as not real material of its kind), other.

Model: Anthropic Messages API directly (Alex's call: eval/client.py is OpenRouter only and is kept for the
two evaluated models). Key from ANTHROPIC_API_KEY (.env first, then environment), never printed or stored.
Fixed settings (SETTINGS). claude-sonnet-5-5 accepts only the default temperature (and API version 2026-10-21
rejects the field), so none is sent; reruns are still identical because every reply is cached on disk under
cache/review/ keyed like eval's cache (model, prompt, image hash, settings). Retries 429 / 5xx / 529.
MOCK=1: a canned "ok" review, no network, nothing cached.
Anthropic spend can't be queried like OpenRouter's (scripts/budget), so the run prints token totals and an
estimate at list price.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from eval.client import ROOT, cache_key, image_sha256
from factory.tasks import load_tasks

URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2026-10-21"
MODEL = "claude-sonnet-5-5"
PRICE_PER_MTOK = {"input": 2.00, "output": 10.00}       # claude-sonnet-5-5 list price, USD
KINDS = ["ambiguity", "legibility", "leakage", "realism", "other"]

# Thinking off (between_tools is this model's lowest thinking setting) so the 2000-token cap is spent on the
# review itself; structured output guarantees the JSON shape.
SCHEMA = {
    "type": "object",
    "properties": {
        "issues": {"type": "array", "items": {
            "type": "object",
            "properties": {"kind": {"type": "string", "enum": KINDS}, "detail": {"type": "string"}},
            "required": ["kind", "detail"], "additionalProperties": False}},
        "realism_notes": {"type": "string"},
        "verdict": {"type": "string", "enum": ["ok", "flag"]},
    },
    "required": ["issues", "realism_notes", "verdict"],
    "additionalProperties": False,
}
SETTINGS = {"max_tokens": 2000, "thinking": {"type": "between_tools"},
            "output_config": {"effort": "high", "format": {"type": "json_schema", "schema": SCHEMA}}}

MAX_ATTEMPTS = 6
TIMEOUT_S = 300
RETRY_HTTP = {408, 409, 425, 429}          # plus every 5xx (529 = overloaded)
MAX_IMAGE_BYTES = 5 * 1024 * 1024

SYSTEM = """You review visual reasoning tasks for a benchmark before a human checks them by hand. You are a \
reviewer, not a solver: the reference answer was computed by code from the structured data the image was drawn \
from, and you cannot change it. Your job is to find problems a careful human checker would raise.

The benchmark's rules: a task must be fair, unambiguous and answerable from the image alone; its difficulty must \
come from reasoning, never from illegibility; the image should look like real material of its kind (for example \
a USGS 7.5-minute topographic quadrangle, or an IEEE-style one-line electrical diagram).

Look for:
- ambiguity: could a careful reader, using only the image and the question, reasonably reach a different answer? \
Examples: two candidates nearly tied, a crossing hidden under a label, a line that grazes a contour, a breaker \
state hard to tell, an undefined term or rule in the question. Walk through the given reasoning steps against \
the image and say which step a reader could get differently, and why.
- legibility: is any label, symbol, line or number the answer depends on too small, faint, covered or cut off?
- leakage: does the question text give away the answer or make the image unnecessary?
- realism: does it look like real material of its kind? Put what gives it away in realism_notes. Add a realism \
issue only for something that would make a judge doubt it is real material of its kind.
- other: anything else that makes the task unfair (wrong units, a reference answer the image plainly \
contradicts, an answer format the question does not state).

Be specific: name the place in the image (label, quadrant, feature) and the step it affects. Do not report \
mere difficulty: a task can be hard and still fair. If you find nothing a careful checker would worry about, \
return no issues. verdict is "flag" when issues is not empty, otherwise "ok"."""


class FatalAPIError(RuntimeError):
    """A failure retrying cannot fix (bad key, bad request, unknown model). Stops the run."""


# ---------------------------------------------------------------------------------------------- key and cache
def api_key() -> str:
    """The team key: .env first (a coding agent's shell can carry its own ANTHROPIC_API_KEY), then the
    environment (Docker passes it with -e)."""
    key = ""
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
    key = key or os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise FatalAPIError("ANTHROPIC_API_KEY is not set (environment or .env)")
    return key


def cache_dir() -> Path:
    return Path(os.environ.get("REVIEW_CACHE_DIR") or ROOT / "cache" / "review")


# ---------------------------------------------------------------------------------------------- prompt
def task_text(rec: dict) -> str:
    """Everything the reviewer reads about one task besides the image."""
    lines = [f"Task {rec.get('task_id')} ({rec.get('question_type') or rec.get('family')})", "",
             "QUESTION (exactly as the evaluated models see it):", str(rec.get("question", "")), ""]
    if rec.get("options"):
        lines += ["OPTIONS:"] + [f"{chr(65 + i)}. {o}" for i, o in enumerate(rec["options"])] + [""]
    ans = rec.get("answer")
    lines.append(f"REFERENCE ANSWER (computed by code, answer_type {rec.get('answer_type')}): "
                 + (json.dumps(ans, ensure_ascii=False) if isinstance(ans, (list, dict)) else str(ans)))
    for k in ("tolerance_rel", "tolerance_abs"):
        if rec.get(k) is not None:
            lines.append(f"{k}: {rec[k]}")
    steps = rec.get("steps") or []
    lines += ["", "REASONING STEPS (intermediate facts computed by code):"]
    lines += [f"{i}. {s if isinstance(s, str) else json.dumps(s, ensure_ascii=False)}"
              for i, s in enumerate(steps, 1)] or ["(none recorded for this task)"]
    if rec.get("references"):
        lines += ["", "THE IMAGE IMITATES:"] + [f"- {r}" for r in rec["references"]]
    lines += ["", "Review this task. Return the JSON object only."]
    return "\n".join(lines)


def estimate_input_tokens(rec: dict, tasks_dir: Path) -> int:
    """Rough, on the high side: image tokens (w*h/750 after the long edge is cut to 1568) + text at 4 chars/token,
    plus 25%. First real run: 3900 measured vs about 4200 estimated for a 1600x1200 map."""
    w, h = 1568, 1176
    try:
        from PIL import Image
        with Image.open(tasks_dir / rec["image"]) as im:
            w, h = im.size
    except Exception:
        pass
    s = min(1.0, 1568 / max(w, h))
    return int(1.25 * (w * s * h * s / 750 + (len(SYSTEM) + len(task_text(rec))) / 4 + 50))


def cost_usd(input_tokens: float, output_tokens: float) -> float:
    return (input_tokens * PRICE_PER_MTOK["input"] + output_tokens * PRICE_PER_MTOK["output"]) / 1e6


# ---------------------------------------------------------------------------------------------- one call
def _key_for(rec: dict, tasks_dir: Path) -> tuple[str, str, str]:
    text = task_text(rec)
    img_hash = image_sha256(tasks_dir / rec["image"])
    return cache_key(MODEL, SYSTEM + "\n\n" + text, img_hash, SETTINGS), text, img_hash


def review_task(rec: dict, tasks_dir, *, use_cache: bool = True) -> dict:
    """Review one task. Always returns a record:
        {key, task_id, model, request, response, attempts, error, cached, mock, created}
    `error` is "" for a usable review. Read the review with parse_review(record)."""
    tasks_dir = Path(tasks_dir)
    key, text, img_hash = _key_for(rec, tasks_dir)
    mock = os.environ.get("MOCK") == "1"
    path = cache_dir() / f"{key}.json"
    if use_cache and not mock and path.exists():
        out = json.loads(path.read_text(encoding="utf-8"))
        out["cached"] = True
        return out

    img_path = tasks_dir / rec["image"]
    body = {"model": MODEL, **SETTINGS, "system": SYSTEM, "messages": [{"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": ""}},
        {"type": "text", "text": text}]}]}
    logged = json.loads(json.dumps(body))
    logged["messages"][0]["content"][0]["source"] = {"file": img_path.name, "sha256": img_hash}
    out = {"key": key, "task_id": rec.get("task_id"), "model": MODEL, "request": logged, "response": None,
           "attempts": [], "error": "", "cached": False, "mock": mock,
           "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if mock:
        out["response"] = {"model": MODEL, "stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(
            {"issues": [], "realism_notes": "Mock review, no model was called.", "verdict": "ok"})}],
            "usage": {"input_tokens": 0, "output_tokens": 0}}
        return out

    raw = img_path.read_bytes()
    if len(raw) > MAX_IMAGE_BYTES:
        out["error"] = f"image is {len(raw)} bytes, over the API's 5 MB limit"
        return out
    body["messages"][0]["content"][0]["source"]["data"] = base64.b64encode(raw).decode()
    out["response"], out["attempts"] = _post_with_retries(body)
    if out["response"] is None:
        out["error"] = "api_error"
        return out                                   # not cached: the next run tries again
    problem = parse_review(out)["error"]
    if problem:
        out["error"] = problem
        return out                                   # a refusal or truncated reply is not cached either
    if use_cache:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.{random.randrange(1 << 30)}.tmp")
        tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)
    return out


def _post_with_retries(body: dict):
    """(raw response JSON or None, attempts). Raises FatalAPIError on a 4xx that retrying can't fix."""
    payload = json.dumps(body).encode()
    headers = {"x-api-key": api_key(), "anthropic-version": API_VERSION, "content-type": "application/json"}
    attempts = []
    for n in range(1, MAX_ATTEMPTS + 1):
        t0 = time.time()
        problem, wait_hint, raw = None, None, None
        try:
            req = urllib.request.Request(URL, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                raw = json.loads(resp.read().decode())
            if not isinstance(raw, dict) or raw.get("type") == "error":
                problem = f"error in body: {json.dumps(raw)[:300]}"
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            if e.code not in RETRY_HTTP and e.code < 500:
                raise FatalAPIError(f"HTTP {e.code} from Anthropic for {body['model']}: {detail}") from None
            problem, wait_hint = f"HTTP {e.code}: {detail}", e.headers.get("retry-after")
        except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError) as e:
            problem = f"{type(e).__name__}: {e}"
        attempts.append({"attempt": n, "seconds": round(time.time() - t0, 2), "problem": problem or ""})
        if problem is None:
            return raw, attempts
        if n < MAX_ATTEMPTS:
            try:
                wait = float(wait_hint)
            except (TypeError, ValueError):
                wait = min(60.0, 2.0 ** n)
            time.sleep(wait + random.uniform(0, 1))
    return None, attempts


# ---------------------------------------------------------------------------------------------- reading a record
def parse_review(out: dict) -> dict:
    """{verdict, issues, realism_notes, usage, error} from a record. A bad reply gives verdict "error"."""
    resp = out.get("response") or {}
    usage = resp.get("usage") or {}
    res = {"verdict": "error", "issues": [], "realism_notes": "", "usage": usage, "error": out.get("error", "")}
    if res["error"] or not resp:
        res["error"] = res["error"] or "no response"
        return res
    stop = resp.get("stop_reason")
    if stop in ("refusal", "max_tokens"):
        res["error"] = f"stop_reason {stop}"
        return res
    text = "".join(b.get("text", "") for b in resp.get("content") or [] if b.get("type") == "text")
    try:
        r = json.loads(text)
        issues = [{"kind": i["kind"] if i.get("kind") in KINDS else "other", "detail": str(i.get("detail", ""))}
                  for i in r.get("issues") or []]
    except (json.JSONDecodeError, AttributeError, KeyError, TypeError):
        res["error"] = f"reply is not the review JSON: {text[:200]!r}"
        return res
    res.update(issues=issues, realism_notes=str(r.get("realism_notes", "")),
               verdict="flag" if issues else "ok")    # the verdict follows the issues, whatever the model wrote
    return res


# ---------------------------------------------------------------------------------------------- a folder
def review_set(tasks_dir, limit: int | None = None, *, dry_run: bool = False, verbose: bool = True) -> dict:
    tasks_dir = Path(tasks_dir)
    records = load_tasks(tasks_dir)[:limit] if limit else load_tasks(tasks_dir)
    mock = os.environ.get("MOCK") == "1"
    todo = [r for r in records if mock or not (cache_dir() / f"{_key_for(r, tasks_dir)[0]}.json").exists()]
    est_in = sum(estimate_input_tokens(r, tasks_dir) for r in todo)
    est_max = cost_usd(est_in, len(todo) * SETTINGS["max_tokens"])
    if verbose:
        print(f"review: {len(records)} tasks, {len(todo)} new {MODEL} calls ({len(records) - len(todo)} cached)"
              + (" [MOCK, no network]" if mock else "")
              + f"; estimated <= ${est_max:.3f} (~{est_in} input tokens + up to {SETTINGS['max_tokens']} output each)")
    if dry_run:
        return {"planned_new_calls": len(todo), "estimated_max_usd": round(est_max, 4)}

    reviews, totals = [], {"input_tokens": 0, "output_tokens": 0}
    for rec in records:
        out = review_task(rec, tasks_dir)
        r = parse_review(out)
        if not out["cached"]:
            for k in totals:
                totals[k] += int(r["usage"].get(k) or 0)
        reviews.append({"task_id": rec.get("task_id"), "verdict": r["verdict"], "issues": r["issues"],
                        "realism_notes": r["realism_notes"], "error": r["error"], "cached": out["cached"],
                        "mock": out.get("mock", False), "usage": r["usage"], "cache_key": out["key"]})
    report = {
        "tasks_folder": str(tasks_dir), "model": MODEL, "settings": {k: v for k, v in SETTINGS.items()},
        "advisory": "LLM review for the human hand check. It never changes an answer and never drops a task.",
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "reviewed": len(reviews), "flagged": sum(r["verdict"] == "flag" for r in reviews),
        "errors": sum(r["verdict"] == "error" for r in reviews),
        "new_calls": sum(not r["cached"] for r in reviews),
        "new_usage": totals, "new_cost_usd_estimate": round(cost_usd(totals["input_tokens"], totals["output_tokens"]), 6),
        "reviews": reviews,
    }
    (tasks_dir / "review_report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    return report


def print_table(report: dict) -> None:
    rows = [(r["task_id"], r["verdict"], ", ".join(sorted({i["kind"] for i in r["issues"]})) or r["error"] or "-",
             "yes" if r["cached"] else "no") for r in report["reviews"]]
    w = max([len("task_id")] + [len(r[0]) for r in rows])
    print(f"{'task_id':<{w}}  {'verdict':<7}  {'cached':<6}  issue kinds")
    for tid, v, kinds, c in rows:
        print(f"{tid:<{w}}  {v:<7}  {c:<6}  {kinds}")
    u = report["new_usage"]
    print(f"flagged {report['flagged']}/{report['reviewed']}, errors {report['errors']}; "
          f"new calls {report['new_calls']}: {u['input_tokens']} input + {u['output_tokens']} output tokens "
          f"(~${report['new_cost_usd_estimate']:.4f} at list price)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m validate.review",
                                 description="Advisory LLM review of a task folder (writes review_report.json).")
    ap.add_argument("--tasks", required=True, help="folder with tasks.jsonl")
    ap.add_argument("--limit", type=int, help="review only the first N tasks")
    ap.add_argument("--dry-run", action="store_true", help="print the call count and cost estimate, call nothing")
    a = ap.parse_args(argv)
    try:
        rep = review_set(a.tasks, a.limit, dry_run=a.dry_run)
    except FatalAPIError as e:
        print(f"FATAL: {e}", file=sys.stderr)
        return 2
    if a.dry_run:
        return 0
    print_table(rep)
    print(f"wrote {Path(a.tasks) / 'review_report.json'}")
    return 1 if rep["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
