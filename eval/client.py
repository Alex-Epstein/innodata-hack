"""The one place that talks to the models (AGENTS.md rule 2: nobody else calls the API).

    uv run python -m eval.client --image X.png --question "..."

What it guarantees:
  * fixed settings for every call: temperature 0, reasoning effort high, max_tokens 64000 (SETTINGS)
  * disk cache keyed by hash(model, prompt, image hash, settings): a rerun costs nothing and returns the
    same reply, so we can never pick the best of several attempts
  * retries 429 / 5xx / timeouts with backoff; a failed call is returned as an error and never cached
  * the key is read from OPENROUTER_API_KEY (environment first, then .env) and never printed or stored

Standard library only, so it runs before the project has a dependency file.
Set MOCK=1 to get a canned reply with no network call (used by scripts/check).
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
URL = "https://openrouter.ai/api/v1/chat/completions"
MODELS = ("anthropic/claude-haiku-5.5", "openai/gpt-6-luna")
SETTINGS = {"temperature": 0, "reasoning": {"effort": "high"}, "max_tokens": 64000}

MAX_ATTEMPTS = 6            # 1 try + 5 retries
TIMEOUT_S = 1800            # one call with 64000 tokens of reasoning can take many minutes
RETRY_HTTP = {408, 409, 425, 429}   # plus every 5xx
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


class FatalAPIError(RuntimeError):
    """A failure that retrying cannot fix (bad key, bad request, unknown model). Stops the run."""


# ---------------------------------------------------------------------------------------------- key and cache
def api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    env_file = ROOT / ".env"
    if not key and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("OPENROUTER_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
    if not key:
        raise FatalAPIError("OPENROUTER_API_KEY is not set (environment or .env)")
    return key


def cache_dir() -> Path:
    return Path(os.environ.get("EVAL_CACHE_DIR") or ROOT / "cache" / "eval")


def image_sha256(image_path) -> str | None:
    return hashlib.sha256(Path(image_path).read_bytes()).hexdigest() if image_path else None


def cache_key(model: str, prompt: str, image_hash: str | None, settings: dict) -> str:
    blob = json.dumps({"model": model, "prompt": prompt, "image_sha256": image_hash, "settings": settings},
                      sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode()).hexdigest()


# ---------------------------------------------------------------------------------------------- one call
def call(model: str, prompt: str, image_path=None, *, settings: dict | None = None, use_cache: bool = True) -> dict:
    """Send `prompt` (+ the image, if given) to `model`. Always returns a record:

        {key, model, request, response, attempts, error, cached, created}

    `request` is what we sent, with the image bytes replaced by their hash. `response` is the raw JSON
    from OpenRouter. `error` is "" for a usable reply, else "api_error". Read it with reply(record).
    """
    settings = dict(SETTINGS if settings is None else settings)
    img_hash = image_sha256(image_path)
    key = cache_key(model, prompt, img_hash, settings)
    mock = os.environ.get("MOCK") == "1"
    path = cache_dir() / f"{key}.json"
    if use_cache and not mock and path.exists():
        rec = json.loads(path.read_text(encoding="utf-8"))
        rec["cached"] = True
        return rec

    content = [{"type": "text", "text": prompt}]
    logged_content = list(content)
    if image_path:
        p = Path(image_path)
        data = base64.b64encode(p.read_bytes()).decode()
        mime = MIME.get(p.suffix.lower(), "image/png")
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{data}"}})
        logged_content.append({"type": "image_url", "image_url": {"file": p.name, "sha256": img_hash}})
    body = {"model": model, "messages": [{"role": "user", "content": content}], **settings,
            "usage": {"include": True}}
    logged = {**body, "messages": [{"role": "user", "content": logged_content}]}

    rec = {"key": key, "model": model, "request": logged, "response": None, "attempts": [], "error": "",
           "cached": False, "mock": mock, "created": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if mock:
        rec["response"] = {"model": model, "choices": [{"finish_reason": "stop", "message": {
            "role": "assistant", "content": "Mock reply, no model was called.\nFINAL ANSWER: mock"}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "cost": 0}}
        return rec

    rec["response"], rec["attempts"] = _post_with_retries(body)
    if rec["response"] is None:
        rec["error"] = "api_error"
        return rec                                   # not cached: the next run tries again
    if use_cache:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(f".{os.getpid()}.{random.randrange(1 << 30)}.tmp")
        tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, path)                        # atomic, safe with several threads
    return rec


def _post_with_retries(body: dict):
    """Returns (raw response JSON or None, list of attempts). Raises FatalAPIError on 4xx we can't fix."""
    payload = json.dumps(body).encode()
    headers = {"Authorization": f"Bearer {api_key()}", "Content-Type": "application/json"}
    attempts = []
    for n in range(1, MAX_ATTEMPTS + 1):
        t0 = time.time()
        problem, wait_hint, raw = None, None, None
        try:
            req = urllib.request.Request(URL, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
                raw = json.loads(resp.read().decode())
            problem = _reply_problem(raw)
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            if e.code not in RETRY_HTTP and e.code < 500:
                raise FatalAPIError(f"HTTP {e.code} from OpenRouter for {body['model']}: {detail}") from None
            problem, wait_hint = f"HTTP {e.code}: {detail}", e.headers.get("Retry-After")
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


def _reply_problem(raw) -> str | None:
    """None if `raw` is a usable completion; otherwise why it should be retried.

    OpenRouter can answer HTTP 200 with an error object (a provider failed upstream) or with an
    empty message. Neither is a model answer, so we retry instead of scoring it."""
    if not isinstance(raw, dict):
        return "reply is not a JSON object"
    if raw.get("error"):
        return f"error in body: {json.dumps(raw['error'])[:300]}"
    choices = raw.get("choices") or []
    if not choices:
        return "no choices in reply"
    c = choices[0]
    if c.get("error"):
        return f"error in choice: {json.dumps(c['error'])[:300]}"
    if c.get("finish_reason") in (None, "error"):
        return f"finish_reason {c.get('finish_reason')}"
    text = (c.get("message") or {}).get("content")
    if c.get("finish_reason") == "stop" and not (isinstance(text, str) and text.strip()):
        return "empty reply with finish_reason stop"
    return None


# ---------------------------------------------------------------------------------------------- reading a record
def reply(rec: dict) -> dict:
    """The parts of a record everyone needs: text, finish_reason, usage, cost (USD)."""
    resp = rec.get("response") or {}
    c = (resp.get("choices") or [{}])[0]
    text = (c.get("message") or {}).get("content")
    if isinstance(text, list):                       # some providers return content as parts
        text = "".join(p.get("text", "") for p in text if isinstance(p, dict))
    usage = resp.get("usage") or {}
    return {"text": text or "", "finish_reason": c.get("finish_reason") or "", "usage": usage,
            "cost": usage.get("cost"), "served_model": resp.get("model", "")}


def for_raw_log(rec: dict) -> dict:
    """A copy of a record that is safe to commit under results/<set>/raw/.

    Providers attach opaque blobs to a reply (OpenAI: encrypted reasoning `data`; Anthropic: a reasoning
    `signature`). They are random-looking base64, not model output, and a secret scanner can mistake a
    substring for an API key: GitHub push protection rejected one. Each blob is replaced by its length and
    SHA-256. The reply text, readable reasoning, finish_reason and usage are left exactly as returned.
    The untouched record stays in the local cache."""
    rec = json.loads(json.dumps(rec))
    for choice in (rec.get("response") or {}).get("choices") or []:
        for detail in (choice.get("message") or {}).get("reasoning_details") or []:
            for field in ("data", "signature"):
                blob = detail.get(field)
                if isinstance(blob, str) and len(blob) > 64:
                    detail[field] = {"removed": "opaque provider blob", "chars": len(blob),
                                     "sha256": hashlib.sha256(blob.encode()).hexdigest()}
    return rec


# ---------------------------------------------------------------------------------------------- command line
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Ask both evaluation models one question about one image.")
    ap.add_argument("--question", required=True, help="sent exactly as given")
    ap.add_argument("--image", help="PNG/JPG path; leave out for a text-only (blind) call")
    ap.add_argument("--model", action="append", help=f"repeatable; default: {', '.join(MODELS)}")
    ap.add_argument("--no-cache", action="store_true", help="call again even if this exact call is cached")
    a = ap.parse_args(argv)

    total, failed = 0.0, False
    for model in a.model or MODELS:
        try:
            rec = call(model, a.question, a.image, use_cache=not a.no_cache)
        except FatalAPIError as e:
            print(f"== {model}\nFATAL: {e}", file=sys.stderr)
            return 2
        r = reply(rec)
        u = r["usage"]
        print(f"== {model}" + ("  (cached)" if rec["cached"] else "") + ("  (MOCK)" if rec.get("mock") else ""))
        if rec["error"]:
            failed = True
            print(f"error: {rec['error']} after {len(rec['attempts'])} attempts: {rec['attempts'][-1]['problem']}")
            continue
        print(f"finish_reason: {r['finish_reason']}")
        print(f"usage: prompt {u.get('prompt_tokens')}, completion {u.get('completion_tokens')}, "
              f"cost ${r['cost']}")
        print(f"reply:\n{r['text']}\n")
        if not rec["cached"]:
            total += r["cost"] or 0
    print(f"new spend this run: ${total:.6f}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
