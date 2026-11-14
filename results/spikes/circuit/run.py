import base64, json, re, sys, threading, time
from concurrent.futures import ThreadPoolExecutor
import httpx

QUESTION = ("The schematic shows a resistor network between terminals A and B. What is the equivalent "
            "resistance between A and B, in ohms? Think step by step, then end your reply with a final line "
            "exactly in the form `FINAL ANSWER: <number>` (ohms, rounded to 1 decimal place). Answers within "
            "±1% are accepted.")
MODELS = ["anthropic/claude-haiku-5.5", "openai/gpt-6-luna"]
URL = "https://openrouter.ai/api/v1/chat/completions"
MAX_CALLS = 24

KEY = None
for line in open("/Users/alex/Desktop/innodata-hack/.env"):
    if line.strip().startswith("OPENROUTER_API_KEY="):
        KEY = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
assert KEY

lock = threading.Lock()
calls = 0
dropped = {m: set() for m in MODELS}   # params dropped per model after rejection
log = []


def body(model, img_b64):
    b = {"model": model,
         "messages": [{"role": "user", "content": [
             {"type": "text", "text": QUESTION},
             {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}]}],
         "temperature": 0, "max_tokens": 16000,
         "reasoning": {"effort": "high"}, "usage": {"include": True}}
    for p in dropped[model]:
        b.pop(p, None)
    return b


def call(model, task):
    global calls
    img = base64.b64encode(open(task["image"], "rb").read()).decode()
    tag = f"{task['id']}__{model.replace('/', '_')}"
    for attempt in range(4):
        with lock:
            if calls >= MAX_CALLS:
                return dict(id=task["id"], model=model, error="call budget exhausted")
            calls += 1
        try:
            r = httpx.post(URL, headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
                           json=body(model, img), timeout=600)
        except Exception as e:
            log.append(f"{tag}: transport error {type(e).__name__}")
            time.sleep(5 * (attempt + 1)); continue
        try:
            js = r.json()
        except Exception:
            js = {"non_json": r.text[:2000]}
        json.dump({"status": r.status_code, "attempt": attempt, "response": js},
                  open(f"raw/{tag}__a{attempt}.json", "w"), indent=1)
        if r.status_code == 429 or r.status_code >= 500:
            log.append(f"{tag}: HTTP {r.status_code} attempt {attempt}")
            time.sleep(5 * 2 ** attempt); continue
        if r.status_code == 400:
            msg = json.dumps(js)[:800]
            log.append(f"{tag}: HTTP 400: {msg}")
            hit = [p for p in ("temperature", "reasoning", "usage", "max_tokens") if p in msg.lower()
                   and p not in dropped[model]]
            if hit:
                dropped[model].add(hit[0]); log.append(f"{tag}: retrying without '{hit[0]}'"); continue
            return dict(id=task["id"], model=model, error=msg)
        if r.status_code != 200 or "choices" not in js:
            return dict(id=task["id"], model=model, error=f"HTTP {r.status_code}: {json.dumps(js)[:500]}")
        ch = js["choices"][0]
        text = ch["message"].get("content") or ""
        nums = re.findall(r"FINAL ANSWER:\s*\**\s*([-+]?\d[\d,]*\.?\d*)", text)
        pred = float(nums[-1].replace(",", "")) if nums else None
        truth = task["answer_exact"]
        ok = pred is not None and abs(pred - truth) <= 0.01 * truth
        u = js.get("usage", {})
        return dict(id=task["id"], level=task["level"], model=model, pred=pred, truth=round(truth, 1),
                    correct=ok, finish_reason=ch.get("finish_reason"),
                    native_finish=ch.get("native_finish_reason"), cost=u.get("cost"),
                    prompt_tokens=u.get("prompt_tokens"), completion_tokens=u.get("completion_tokens"),
                    reasoning_tokens=(u.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                    provider=js.get("provider"), tail=text[-1500:], dropped=sorted(dropped[model]))
    return dict(id=task["id"], model=model, error="retries exhausted")


tasks = json.load(open("tasks.json"))
results = []
# probe one call per model first to detect parameter rejections
first = tasks[0]
with ThreadPoolExecutor(2) as ex:
    results += list(ex.map(lambda m: call(m, first), MODELS))
for r in results: print("probe", r.get("id"), r.get("model"), r.get("pred"), r.get("correct"), r.get("error", ""))
jobs = [(m, t) for t in tasks[1:] for m in MODELS]
with ThreadPoolExecutor(8) as ex:
    results += list(ex.map(lambda mt: call(*mt), jobs))
json.dump(dict(results=results, log=log, calls=calls, dropped={k: sorted(v) for k, v in dropped.items()}),
          open("results.json", "w"), indent=1)
print("calls", calls)
print("\n".join(log))
for r in results:
    print(r.get("id"), r.get("model"), r.get("pred"), r.get("truth"), r.get("correct"), r.get("finish_reason"),
          r.get("cost"), r.get("error", ""))
