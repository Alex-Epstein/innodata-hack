"""Call two vision models on the 9 calendar tasks via OpenRouter; save raw JSON; score."""
import base64, json, os, re, time, threading
from concurrent.futures import ThreadPoolExecutor
import httpx

OUT = os.path.dirname(os.path.abspath(__file__))
MODELS = {"haiku": "anthropic/claude-haiku-5.5", "luna": "openai/gpt-6-luna"}
URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_CALLS = 24


def load_key():
    for line in open("/Users/alex/Desktop/innodata-hack/.env"):
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("key not found")


KEY = load_key()
lock = threading.Lock()
state = {"calls": 0}
notes = []
# params dropped per model after a provider rejection (learned once, applied to later calls)
dropped = {m: set() for m in MODELS}


def body_for(task, model_key, drop):
    b64 = base64.b64encode(open(task["image"], "rb").read()).decode()
    body = {
        "model": MODELS[model_key],
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": task["question"]},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]}],
        "temperature": 0, "max_tokens": 16000,
        "reasoning": {"effort": "high"}, "usage": {"include": True},
    }
    for k in drop:
        body.pop(k, None)
    return body


def post(body):
    with lock:
        if state["calls"] >= MAX_CALLS:
            raise RuntimeError("call budget exhausted")
        state["calls"] += 1
    r = httpx.post(URL, json=body, timeout=900,
                   headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    try:
        return r.status_code, r.json()
    except Exception:
        return r.status_code, {"non_json": r.text[:2000]}


def call(task, mk):
    tid = f"{task['id']}__{mk}"
    attempt = 0
    while True:
        drop = set(dropped[mk])
        status, js = post(body_for(task, mk, drop))
        err = js.get("error") if isinstance(js, dict) else None
        if status == 200 and not err:
            break
        msg = json.dumps(err or js)[:600]
        code = (err or {}).get("code", status) if isinstance(err, dict) else status
        json.dump({"status": status, "resp": js, "dropped": sorted(drop)},
                  open(os.path.join(OUT, "raw", f"{tid}__err{attempt}.json"), "w"), indent=1)
        if status == 400 or code == 400:
            low = msg.lower()
            cand = [k for k in ["temperature", "reasoning", "max_tokens", "usage"] if k in low and k not in drop]
            if cand:
                with lock:
                    dropped[mk].add(cand[0])
                notes.append(f"{MODELS[mk]} rejected `{cand[0]}`: {msg}")
                attempt += 1
                continue
            notes.append(f"{tid}: unrecoverable 400: {msg}")
            return {"id": tid, "error": msg}
        if (status == 429 or status >= 500 or (isinstance(code, int) and (code == 429 or code >= 500))) and attempt < 3:
            attempt += 1
            time.sleep(5 * 2 ** attempt)
            continue
        notes.append(f"{tid}: error status {status}: {msg}")
        return {"id": tid, "error": msg}
    json.dump(js, open(os.path.join(OUT, "raw", f"{tid}.json"), "w"), indent=1)
    ch = js["choices"][0]
    text = ch["message"].get("content") or ""
    m = re.findall(r"FINAL ANSWER:\s*\**\s*([A-Za-z]+)\.?,?\s+(\d{1,2})[:.](\d{2})", text)
    pred = None
    if m:
        d, h, mi = m[-1]
        pred = f"{d[:3].capitalize()} {int(h):02d}:{mi}"
    u = js.get("usage", {})
    return {"id": tid, "task": task["id"], "model": mk, "pred": pred, "truth": task["answer"],
            "correct": pred == task["answer"], "finish_reason": ch.get("finish_reason"),
            "native_finish_reason": ch.get("native_finish_reason"),
            "cost": u.get("cost"), "completion_tokens": u.get("completion_tokens"),
            "reasoning_tokens": (u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
            "tail": text[-1500:], "dropped": sorted(drop)}


if __name__ == "__main__":
    tasks = json.load(open(os.path.join(OUT, "tasks.json")))
    # one probe call per model first so param rejections are learned before fanning out
    jobs = [(t, mk) for t in tasks for mk in MODELS]
    probes = [j for j in jobs if j[0]["id"] == "L1_s1"]
    rest = [j for j in jobs if j not in probes]
    with ThreadPoolExecutor(2) as ex:
        results = list(ex.map(lambda j: call(*j), probes))
    print("probes:", [(r["id"], r.get("pred"), r.get("error")) for r in results], flush=True)
    with ThreadPoolExecutor(8) as ex:
        results += list(ex.map(lambda j: call(*j), rest))
    json.dump({"results": results, "notes": notes, "calls": state["calls"],
               "dropped": {k: sorted(v) for k, v in dropped.items()}},
              open(os.path.join(OUT, "results.json"), "w"), indent=1)
    for r in results:
        print(r["id"], r.get("pred"), "truth", r.get("truth"), r.get("correct"), r.get("finish_reason"), r.get("cost"), r.get("error", ""))
    print("calls", state["calls"], "notes", notes)
