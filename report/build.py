"""Build the static report page (one self-contained HTML file) and report/evidence.md from task and result files.

    uv run python -m report --tasks tasks/final --results results/final \
        [--pilot tasks/pilot_topo_flood:results/pilot_topo_flood ...] --out report/index.html

Every number on the page is computed from the files passed in; nothing is typed by hand.
Inputs (missing optional files are skipped and the page says so):
    <tasks>/tasks.jsonl                  required: the tasks (question, answer, steps, difficulty, image)
    <tasks>/layout/<task_id>.json        optional: "overlay" geometry (marks a task as having a truth overlay)
    <tasks>/validation_report.json       optional: the validity funnel (factory validate)
    <tasks>/generation_log.json          optional: attempted / rejected / kept (factory generate)
    <results>/responses.csv              required: one row per model per task (eval.run)
    <results>/run_config.json            optional: models and settings
    <results>/summary.json, raw/*.json   optional: cost; raw/ also gives each model's reasoning text
Truth-overlay images are found as <task_id>*truth*.png in --truth-dir, <tasks>/overlays, <tasks>/truth,
<tasks>/images or <tasks>/../demo.
"""
from __future__ import annotations

import argparse
import base64
import csv
import html
import io
import json
import os
import re
import shlex
import subprocess
import sys
from collections import Counter, OrderedDict
from dataclasses import dataclass
from pathlib import Path

csv.field_size_limit(2**31 - 1)

# docs/DESIGN.md "Field Survey": colour is information. Truth is blue, every model is red (told apart by fill
# pattern and label), terrain is contour brown, everything else is ink on paper.
PAPER, INK, TRUTH, MODEL, CONTOUR, CONTOUR_DARK = "#F3EEDF", "#1E1B16", "#2F7FC1", "#D2412C", "#9A5B2E", "#6E3F1E"
INK2, MUTED, GRID = "#4A443A", "#7A7264", "#D8D0BC"
HATCHES = ["", "////", "xxxx", "...."]             # model i: solid red, then hatched red
MAX_EMBED = 300_000          # bytes per embedded image


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def warn(msg: str) -> None:
    print(f"report: {msg}", file=sys.stderr)


def rel(p) -> str:
    """A path as typed from the repository root when possible (for commands and source columns)."""
    p = Path(p)
    try:
        r = os.path.relpath(p.resolve(), Path.cwd())
        return r if not r.startswith("..") else str(p)
    except ValueError:
        return str(p)


def read_json(p):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ------------------------------------------------------------------------------------------------ loading
def load_tasks(d: Path) -> list[dict]:
    f = d / "tasks.jsonl"
    if not f.exists():
        warn(f"no tasks.jsonl in {d}")
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        t = json.loads(line)
        t["_dir"] = d
        if not t.get("overlay"):
            lay = read_json(d / "layout" / f"{t['task_id']}.json")
            if isinstance(lay, dict) and lay.get("overlay"):
                t["overlay"] = lay["overlay"]
        out.append(t)
    return out


@dataclass
class ResultSet:
    dir: Path
    rows: list
    run_config: dict | None
    summary: dict | None


def load_results(d: Path) -> ResultSet:
    rows = []
    f = d / "responses.csv"
    if f.exists():
        with open(f, newline="", encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                r["_dir"] = d
                rows.append(r)
    else:
        warn(f"no responses.csv in {d}")
    return ResultSet(d, rows, read_json(d / "run_config.json"), read_json(d / "summary.json"))


def raw_record(row: dict):
    name = f"{row['task_id']}__{re.sub(r'[^A-Za-z0-9.-]+', '_', row['model'])}.json"
    return read_json(Path(row["_dir"]) / "raw" / name)


def reply_texts(row: dict) -> tuple[str, str]:
    """(visible reply, readable reasoning) for one row; reasoning comes from raw/ when it is there."""
    content, reasoning = row.get("response") or "", ""
    rec = raw_record(row)
    if isinstance(rec, dict):
        msg = (((rec.get("response") or {}).get("choices") or [{}])[0] or {}).get("message") or {}
        reasoning = msg.get("reasoning") or ""
        if not reasoning:
            parts = [p.get("text") or p.get("summary") or "" for p in msg.get("reasoning_details") or []
                     if isinstance(p, dict)]
            reasoning = "\n\n".join(p for p in parts if isinstance(p, str) and p)
    return content, reasoning if isinstance(reasoning, str) else ""


def cost_of(rs: ResultSet):
    """(USD for every call in the run, source path) or (None, None)."""
    tot = (rs.summary or {}).get("totals") or (rs.run_config or {}).get("totals") or {}
    if isinstance(tot.get("cost_usd_all_calls"), (int, float)):
        src = rs.dir / ("summary.json" if (rs.summary or {}).get("totals") else "run_config.json")
        return float(tot["cost_usd_all_calls"]), src
    costs = []
    for p in sorted((rs.dir / "raw").glob("*.json")):
        c = (((read_json(p) or {}).get("response") or {}).get("usage") or {}).get("cost")
        if isinstance(c, (int, float)):
            costs.append(c)
    return (float(sum(costs)), rs.dir / "raw") if costs else (None, None)


# ------------------------------------------------------------------------------------------------ helpers
def model_name(m: str) -> str:
    base = m.split("/", 1)[-1]
    words = [w.upper() if w.lower() in ("gpt", "llm") else w.capitalize() for w in base.split("-")]
    out = " ".join(words)
    return re.sub(r"(GPT) (\d)", r"\1-\2", out)


def diff_label(t: dict) -> str:
    d = t.get("difficulty")
    if d is None or isinstance(d, bool):
        return "–"
    if isinstance(d, (int, float)):
        return f"L{d:g}"
    if isinstance(d, dict):
        lvl = d.get("level")
        return str(lvl) if lvl is not None else "–"
    return str(d)


def to_num(x):
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return x
    try:
        return float(str(x).strip().replace("−", "-").replace(",", ""))
    except ValueError:
        return None


def norm_label(x) -> str:
    return re.sub(r"[^a-z0-9]", "", str(x).lower())


def fmt_num(v) -> str:
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return f"{v:.1f}".rstrip("0").rstrip(".") if abs(v) >= 1 else f"{v:.4g}"
    return str(v)


def fmt_usd(v: float) -> str:
    return f"${v:.6f}".rstrip("0").rstrip(".")


def ref_cell(answer) -> str:
    """How eval.run writes a task's answer into responses.csv (eval/scoring.ref_answer_cell)."""
    return answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)


def matches(task: dict | None, row: dict) -> bool:
    """False when the task file changed after this row was scored (its answer is no longer the row's ref_answer)."""
    return task is not None and ref_cell(task.get("answer")).strip() == (row.get("ref_answer") or "").strip()


def acc(rows: list[dict]) -> tuple[int, int]:
    done = [r for r in rows if r.get("correct") in ("0", "1")]
    return sum(r["correct"] == "1" for r in done), len(done)


# ------------------------------------------------------------------------------------------------ broken step
UNITS = (("_minutes", "min"), ("_min", "min"), ("_km", "km"), ("_kw", "kW"), ("_deg", "°"), ("_m", "m"))
STOP = {"the", "and", "for", "to", "of", "if", "by", "with", "from", "min", "minutes", "number", "count", "total",
        "time", "before", "after", "that", "this", "are", "was", "its"}
TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")
NUM_RE = re.compile(r"(?<![\w.\-])-?\d+(?:\.\d+)?(?![\w])")


def humanize(key) -> tuple[str, str]:
    k, unit = re.sub(r"^\d+_", "", str(key)), ""
    for suf, u in UNITS:
        if k.lower().endswith(suf):
            k, unit = k[: -len(suf)], u
            break
    return k.replace("_", " ").strip(), unit


def _idlike(s: str) -> bool:
    return bool(re.search(r"\d", s) and re.search(r"[A-Za-z]", s)) or (s.isupper() and len(s) <= 6)


@dataclass
class Fact:
    name: str
    ident: str | None
    key: str
    value: object
    unit: str


def flatten(steps: dict) -> list[Fact]:
    """The chain of intermediate facts in `steps`, in order. Coordinate lists and booleans are skipped."""
    out: list[Fact] = []

    def scalar(v):
        return isinstance(v, (int, float, str)) and not isinstance(v, bool)

    def rec(obj: dict):
        for k, v in obj.items():
            if v is None or isinstance(v, bool):
                continue
            if isinstance(v, dict):
                if v and all(scalar(x) for x in v.values()) and all(_idlike(str(kk)) for kk in v):
                    name, unit = humanize(k)
                    out.extend(Fact(f"{name} › {kk}", str(kk), k, vv, unit) for kk, vv in v.items())
                else:
                    rec(v)
            elif isinstance(v, list):
                if v and all(isinstance(x, dict) for x in v):
                    for item in v:
                        idk = next((kk for kk, vv in item.items() if isinstance(vv, str)), None)
                        ident = item.get(idk) if idk else None
                        for kk, vv in item.items():
                            if kk != idk and scalar(vv):
                                name, unit = humanize(kk)
                                out.append(Fact(f"{ident} {name}" if ident else name, ident, kk, vv, unit))
            elif scalar(v):
                name, unit = humanize(k)
                out.append(Fact(name, None, str(k), v, unit))

    if isinstance(steps, dict):
        rec(steps)
    return out


def _segments(text: str):
    """(offset, sentence) pairs; decimals like 326.2 never split a sentence."""
    cuts = [0] + [m.end() for m in re.finditer(r"\n+|(?<=[.!?])\s+(?=[A-Z0-9*(\[#-])", text)] + [len(text)]
    for a, b in zip(cuts, cuts[1:]):
        if text[a:b].strip():
            yield a, text[a:b]


UNIT_WORDS = {"": {"m", "km", "min", "mins", "minutes", "meters", "metres", "kw", "h", "hours", "%", "°"},
              "m": {"min", "mins", "minutes", "kw", "%", "h", "hours"},
              "min": {"m", "km", "meters", "metres", "kw", "%"}}


def _blank(s: str, pattern: str, flags=0) -> str:
    """Replace each match with spaces of the same length, so offsets stay valid."""
    return re.sub(pattern, lambda m: " " * len(m.group()), s, flags=flags)


def _numbers(s: str, unit: str | None = None) -> list[tuple[float, int]]:
    """(value, position) of the numbers in a sentence; times, (x, y) pixel pairs, step labels, list markers and
    numbers carrying a unit that does not fit the fact are left out."""
    s = s.replace("−", "-")
    s = _blank(s, TIME_RE.pattern)
    s = _blank(s, r"\([^()\d]*-?\d+(?:\.\d+)?\s*,\s*-?\d+(?:\.\d+)?\s*\)")
    s = _blank(s, r"\b(step|stage|part|point)\s+\d+", re.I)
    s = _blank(s, r"^[\s>*#-]*\d+[.)]\s", re.M)
    out = []
    for m in NUM_RE.finditer(s):
        nxt = re.match(r"\s*([a-z%°]+)", s[m.end():m.end() + 10].lower())
        if unit is not None and nxt and nxt.group(1) in UNIT_WORDS.get(unit, set()):
            continue
        out.append((float(m.group()), m.start()))
    return out


def _near(s: str, f: "Fact", stems: list[str]) -> list[float]:
    """Numbers within 40 characters of a word naming the fact, nearest first."""
    low = s.lower()
    anchors = [m.start() for m in re.finditer(r"[a-z]+", low) if m.group()[:5] in stems]
    if f.ident:
        anchors += [m.end() for m in re.finditer(r"(?<![a-z0-9])" + re.escape(f.ident.lower()) + r"(?![a-z0-9])", low)]
    best = []
    for x, pos in _numbers(s, f.unit):
        d = min((abs(pos - a) for a in anchors), default=10**9)
        if d <= 40:
            best.append((d, x))
    return [x for _, x in sorted(best)]


def _within(truth, x) -> bool:
    if isinstance(truth, int):
        return abs(x - truth) < 0.5
    return abs(x - truth) <= 0.1 * abs(truth) + 0.5


def _plausible(truth, x) -> bool:
    return truth != 0 and x != 0 and (x > 0) == (truth > 0) and 1 / 3 <= x / truth <= 3


def check_both(f: Fact, content: str, reasoning: str):
    """check_fact on the visible reply first; the reasoning only if the reply does not settle it."""
    a = check_fact(f, content)
    if a[0] in ("ok", "wrong") or not reasoning:
        return a
    b = check_fact(f, reasoning)
    if b[0] in ("ok", "wrong"):
        return b[0], b[1], b[2] + len(content) + 1, b[3]
    return a if a[0] == "unsure" else b


def check_fact(f: Fact, text: str):
    """('ok' | 'wrong' | 'missing' | 'unsure', what it said, offset, length) for one fact against the text."""
    words = re.findall(r"[A-Za-z0-9]+", re.sub(r"^\d+_", "", f.key))
    ids = [w.lower() for w in words if _idlike(w) and re.search(r"\d", w)]
    stems = [w.lower()[:5] for w in words if w.lower() not in STOP and not re.search(r"\d", w) and len(w) >= 3]
    req = [f.ident.lower()] if f.ident else ids
    if not req and not stems:
        return "unsure", None, None, 0
    is_time = isinstance(f.value, str) and TIME_RE.fullmatch(f.value.strip())
    matched = []
    for off, s in _segments(text):
        low = s.lower()
        if req and not all(re.search(r"(?<![a-z0-9])" + re.escape(i) + r"(?![a-z0-9])", low) for i in req):
            continue
        if stems:                                      # an ident (C1, EF-4) also needs its field named
            hit = {w[:5] for w in re.findall(r"[a-z]+", low)} & set(stems)
            if len(hit) < min(1 if f.ident else 2, len(set(stems))):
                continue
        matched.append((off, s))
    if is_time:
        for off, s in matched:
            times = [m.group() for m in TIME_RE.finditer(s)]
            if f.value.strip() in times:
                return "ok", None, off, len(s)
        for off, s in matched:
            times = [m.group() for m in TIME_RE.finditer(s)]
            if times:                                  # the last time in the sentence is the one it worked out
                return "wrong", times[-1], off, len(s)
        return "missing", None, None, 0
    truth = f.value
    any_nums = False
    near = [(off, s, _near(s, f, stems)) for off, s in matched]
    for off, s, nums in near:
        any_nums |= bool(nums)
        if any(_within(truth, x) for x in nums):
            return "ok", None, off, len(s)
    for off, s, nums in near:
        for x in nums:
            if _plausible(truth, x):
                return "wrong", fmt_num(int(x) if x == int(x) else x), off, len(s)
    return ("unsure" if any_nums else "missing"), None, None, 0


@dataclass
class Tag:
    kind: str           # method | trap | wrong | skipped | final | list | picked | unclassified
    text: str
    offset: int | None = None
    length: int = 0


def classify(task: dict, row: dict, content: str, reasoning: str) -> Tag:
    """The step that broke, from the model's text vs the task's `steps` (heuristic; 'unclassified' when unsure)."""
    steps = task.get("steps")
    if not isinstance(steps, dict) or not steps:
        return Tag("unclassified", "unclassified (no steps recorded)")
    parsed, answer = row.get("parsed", ""), task.get("answer")
    pnum, anum = to_num(parsed), to_num(answer)
    text = content + "\n" + reasoning
    flat = flatten(steps)
    for f in flat:                                     # a planted wrong method the answer matches exactly
        v = to_num(f.value)
        if f.key.startswith("wrong_if") and v is not None and pnum is not None and _within(v, pnum) \
                and not (anum is not None and _within(v, anum)):
            return Tag("method", "wrong method: " + humanize(f.key[len("wrong_if_"):])[0])
    for f in flat:                                     # a named decoy the answer matches
        if f.ident is None and isinstance(f.value, str) and not TIME_RE.fullmatch(f.value.strip()) \
                and parsed and norm_label(f.value) == norm_label(parsed) and norm_label(parsed) != norm_label(answer):
            return Tag("trap", f"picked the {f.name}")
    qwords = {w[:5] for w in re.findall(r"[a-z]+", str(task.get("question", "")).lower())}

    def asked(f: Fact) -> bool:                        # the question itself talks about this quantity
        words = [w.lower() for w in re.findall(r"[A-Za-z]+", re.sub(r"^\d+_", "", f.key))
                 if w.lower() not in STOP and len(w) >= 3]
        hits = sum(any(q.startswith(w[:5]) or w[:5].startswith(q) and len(q) >= 4 for q in qwords) for w in words)
        return bool(words) and hits >= min(2, len(words))

    wrong = missing = None
    ok = 0
    for f in flat:
        if f.key.startswith("wrong_if") or not asked(f):
            continue
        is_time = isinstance(f.value, str) and TIME_RE.fullmatch(f.value.strip())
        v = to_num(f.value) if not isinstance(f.value, str) else None
        if not is_time and (v is None or v == 0):
            continue
        if not is_time and f.ident is None and anum is not None and _within(v, anum):
            continue                                   # that is the final answer, not an intermediate step
        st, said, off, ln = check_both(f, content, reasoning)
        if st == "ok":
            ok += 1
        elif st == "wrong" and wrong is None:
            wrong = (f, said, off, ln)
        elif st == "missing" and missing is None and f.ident is None and (is_time or isinstance(f.value, int)):
            missing = f
    if wrong:
        f, said, off, ln = wrong
        u = f" {f.unit}" if f.unit else ""
        return Tag("wrong", f"{f.name}: said {said}{u}, truth {fmt_num(f.value)}{u}", off, ln)
    if missing and len(text.strip()) >= 300:
        u = f" {missing.unit}" if missing.unit else ""
        return Tag("skipped", f"never states {missing.name} (truth {fmt_num(missing.value)}{u})")
    if ok:
        return Tag("final", "facts right, final step wrong")
    if isinstance(answer, list):                       # a list answer: which items it missed or added
        got = [x.strip(" '\"[]") for x in re.split(r"[,;\n]", str(parsed)) if x.strip(" '\"[]")]
        want = {norm_label(x): str(x) for x in answer}
        have = {norm_label(x): x for x in got}
        miss = [want[k] for k in want if k not in have]
        extra = [have[k] for k in have if k not in want]
        bits = ([f"missed {', '.join(miss[:4])}{' …' if len(miss) > 4 else ''}"] if miss else []) + \
               ([f"added {', '.join(extra[:4])}{' …' if len(extra) > 4 else ''}"] if extra else [])
        if bits:
            return Tag("list", "; ".join(bits))
    detail = picked_detail(task, parsed)
    if detail and norm_label(parsed) != norm_label(answer):
        return Tag("picked", detail)
    if pnum is not None and anum is not None and task.get("answer_type") in ("integer", "number"):
        return Tag("final", f"final count off by {fmt_num(pnum - anum) if pnum - anum < 0 else '+' + fmt_num(pnum - anum)}")
    return Tag("unclassified", "unclassified")


def picked_detail(task: dict, parsed: str) -> str:
    """For a label answer: what the data says about the option the model picked (e.g. its distance off the route)."""
    steps = task.get("steps")
    if not isinstance(steps, dict) or not parsed:
        return ""
    for v in steps.values():
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            for item in v:
                idk = next((k for k, x in item.items() if isinstance(x, str)), None)
                if idk and norm_label(item[idk]) == norm_label(parsed):
                    bits = []
                    for k, x in item.items():
                        if k != idk and isinstance(x, (int, float)) and not isinstance(x, bool):
                            name, unit = humanize(k)
                            bits.append(f"{name} {fmt_num(x)}{(' ' + unit) if unit else ''}")
                    return f"{item[idk]}: " + ", ".join(bits) if bits else ""
    return ""


def excerpt(content: str, reasoning: str, tag: Tag, n: int = 400) -> tuple[str, str]:
    """(label, HTML) for ~n characters of the model's text, centred on where it goes wrong when we found that."""
    if tag.offset is not None:
        src, label = (content, "reply") if tag.offset < len(content) else (reasoning, "reasoning")
        off = tag.offset if src is content else tag.offset - len(content) - 1
        start = max(0, off - 120)
        start = src.rfind(" ", 0, start) + 1 if start else 0
        end = min(len(src), start + n)
        a, b = off, min(off + tag.length, end)
        body = esc(src[start:a]) + "<mark>" + esc(src[a:b]) + "</mark>" + esc(src[b:end])
        return label, ("…" if start else "") + body + ("…" if end < len(src) else "")
    src, label = (content, "reply") if len(content.strip()) >= 150 or not reasoning else (reasoning, "reasoning")
    return label, esc(src[:n]) + ("…" if len(src) > n else "")


# ------------------------------------------------------------------------------------------------ images
_URI: dict = {}


def image_uri(path: Path, max_w: int) -> str:
    """The image downscaled to max_w and embedded as JPEG under MAX_EMBED bytes ('' if it cannot be read)."""
    key = (str(path), max_w)
    if key in _URI:
        return _URI[key]
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
    except Exception as e:                                  # noqa: BLE001 - a missing image is not fatal
        warn(f"cannot read image {path}: {e}")
        _URI[key] = ""
        return ""
    if im.width > max_w:
        im = im.resize((max_w, round(im.height * max_w / im.width)), Image.LANCZOS)
    data = b""
    for q in (90, 84, 76, 68, 60):
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=q, optimize=True)
        data = buf.getvalue()
        if len(data) <= MAX_EMBED:
            break
    _URI[key] = "data:image/jpeg;base64," + base64.b64encode(data).decode()
    return _URI[key]


def truth_image(t: dict, extra: list[Path]) -> Path | None:
    d, tid = Path(t["_dir"]), t["task_id"]
    for dd in [*extra, d / "overlays", d / "truth", d / "images", d.parent / "demo", d / "demo"]:
        if dd.is_dir():
            hits = sorted(dd.glob(f"{tid}*truth*.png")) + sorted(dd.glob(f"{tid}*overlay*.png"))
            if hits:
                return hits[0]
    return None


# ------------------------------------------------------------------------------------------------ charts
_FONTS: dict = {}


def _plt():
    """pyplot with the Field Survey look; IBM Plex if installed, else DejaVu (no warnings either way)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager
    if not _FONTS:
        have = {f.name for f in font_manager.fontManager.ttflist}
        _FONTS["label"] = next((f for f in ("IBM Plex Sans Condensed", "IBM Plex Sans") if f in have), "DejaVu Sans")
        _FONTS["mono"] = "IBM Plex Mono" if "IBM Plex Mono" in have else "DejaVu Sans Mono"
    plt.rcParams.update({"font.family": _FONTS["label"], "font.size": 11, "axes.edgecolor": INK,
                         "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK, "text.color": INK,
                         "figure.facecolor": PAPER, "axes.facecolor": PAPER, "hatch.linewidth": 1.4,
                         "hatch.color": MODEL})
    return plt


def fig_uri(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=200, facecolor=PAPER, metadata={"Software": None})
    _plt().close(fig)
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _bar_style(i: int) -> dict:
    """Model i's bar: all models are red; the first solid, the rest hatched on paper."""
    if i == 0:
        return {"facecolor": MODEL, "edgecolor": MODEL, "linewidth": 1}
    return {"facecolor": PAPER, "edgecolor": MODEL, "hatch": HATCHES[i % len(HATCHES)] or "////", "linewidth": 1.2}


def accuracy_chart(groups: list, models: list[str], styles: dict) -> str:
    """Horizontal grouped bars: one group per (question type, difficulty, generator), one bar per model."""
    plt = _plt()
    mono = _FONTS["mono"]
    n, k = len(groups), len(models)
    bh = 0.8 / max(k, 1)
    fig, ax = plt.subplots(figsize=(10, 0.36 * n * max(k, 2) + 1.3))
    for gi, g in enumerate(groups):
        for mi, m in enumerate(models):
            c, tot = g["acc"].get(m, (0, 0))
            y = gi + (mi - (k - 1) / 2) * bh
            if not tot:
                ax.text(1, y, "not run", va="center", fontsize=9.5, color=MUTED, family=mono)
                continue
            pct = 100 * c / tot
            ax.barh(y, max(pct, 0.5), height=bh * 0.8, **_bar_style(styles[m]))
            ax.text(pct + 1.2, y, f"{c}/{tot}", va="center", fontsize=10.5, color=INK, family=mono,
                    fontweight="bold")
    ax.set_yticks(range(n))
    ax.set_yticklabels([g["label"] for g in groups], fontsize=10.5, family=mono)
    ax.invert_yaxis()
    ax.set_xlim(0, 119)
    ax.set_xticks([0, 25, 50, 75, 100])
    ax.set_xticklabels(["0%", "25%", "50%", "75%", "100%"], family=mono, fontsize=10)
    ax.grid(axis="x", color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)
    for s in ("top", "right", "bottom"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_linewidth(0.8)
    ax.tick_params(axis="both", length=0)
    handles = [plt.Rectangle((0, 0), 1, 1, **_bar_style(styles[m])) for m in models]
    ax.legend(handles, [model_name(m).upper() for m in models], loc="lower left", bbox_to_anchor=(0, 1.0),
              ncol=len(models), frameon=False, fontsize=10.5, handlelength=2.2)
    fig.tight_layout()
    return fig_uri(fig)


def funnel_chart(stages: list[tuple[str, int]]) -> str:
    plt = _plt()
    mono = _FONTS["mono"]
    fig, ax = plt.subplots(figsize=(10, 0.42 * len(stages) + 0.7))
    top = max(v for _, v in stages) or 1
    for i, (name, v) in enumerate(stages):
        last = i == len(stages) - 1
        ax.barh(i, max(v, top * 0.004), height=0.62, color=CONTOUR_DARK if last else CONTOUR,
                alpha=1 if last else 0.55, linewidth=0)
        ax.text(v + top * 0.012, i, f"{v}", va="center", fontsize=11, color=INK, family=mono, fontweight="bold")
    ax.set_yticks(range(len(stages)))
    ax.set_yticklabels([s.upper() for s, _ in stages], fontsize=10)
    ax.invert_yaxis()
    ax.set_xlim(0, top * 1.1)
    ax.set_xticks([])
    for s in ("top", "right", "bottom"):
        ax.spines[s].set_visible(False)
    ax.spines["left"].set_linewidth(0.8)
    ax.tick_params(axis="y", length=0)
    fig.tight_layout()
    return fig_uri(fig)


# ------------------------------------------------------------------------------------------------ funnel data
def funnel_data(task_dirs: list[Path], tasks_by_dir: dict) -> dict:
    """Generated -> each check (cumulative) -> kept, summed over the folders; source files listed."""
    attempted = kept = checked = passed = 0
    have_gen = have_val = False
    cum: OrderedDict = OrderedDict()
    reasons: Counter = Counter()
    sources, missing = [], []
    for d in task_dirs:
        gl, vr = read_json(d / "generation_log.json"), read_json(d / "validation_report.json")
        if isinstance(gl, dict) and "attempted" in gl:
            have_gen = True
            attempted += gl.get("attempted", 0)
            kept += gl.get("kept", 0)
            for r in (gl.get("rejected") or []) + (gl.get("errors") or []):
                reasons[(r.get("reason") or r.get("error") or "?") if isinstance(r, dict) else str(r)] += 1
            sources.append(d / "generation_log.json")
        elif isinstance(vr, dict) and isinstance(vr.get("generation"), dict):
            have_gen = True
            attempted += vr["generation"].get("attempted", 0)
            kept += vr["generation"].get("kept", 0)
        if isinstance(vr, dict) and isinstance(vr.get("cumulative_funnel"), dict):
            have_val = True
            checked += vr.get("checked", 0)
            passed += vr.get("all_passed", 0)
            for k, v in vr["cumulative_funnel"].items():
                cum[k] = cum.get(k, 0) + v
            for k, fails in (vr.get("failures") or {}).items():
                reasons[f"failed {k}"] += len(fails) if isinstance(fails, list) else int(bool(fails))
            sources.append(d / "validation_report.json")
        else:
            ts = [t for t in tasks_by_dir.get(d, []) if isinstance(t.get("checks"), dict)]
            if ts:                                     # no report: recompute from the checks field
                have_val = True
                names = list(dict.fromkeys(k for t in ts for k in t["checks"]))
                alive = ts
                checked += len(ts)
                for k in names:
                    alive = [t for t in alive if t["checks"].get(k) is True]
                    cum[k] = cum.get(k, 0) + len(alive)
                passed += len(alive)
                sources.append(d / "tasks.jsonl")
                missing.append(f"{rel(d)} has no validation_report.json (funnel from the checks in tasks.jsonl)")
            else:
                missing.append(f"{rel(d)} has no validation_report.json or checks")
    stages = []
    if have_gen:
        stages += [("generated (seeds attempted)", attempted), ("kept by the generator", kept)]
    if have_val:
        if not have_gen:
            stages.append(("tasks checked", checked))
        stages += [(f"passes {k}", v) for k, v in cum.items()]
        stages.append(("passed every check", passed))
    return {"stages": stages, "reasons": reasons, "sources": sources, "missing": missing,
            "attempted": attempted if have_gen else None, "passed": passed if have_val else None,
            "checked": checked}


# ------------------------------------------------------------------------------------------------ steps rendering
def render_steps(steps) -> str:
    if not isinstance(steps, dict) or not steps:
        return "<p class='muted'>This task records no <code>steps</code>.</p>"
    items = []
    for k, v in steps.items():
        name, unit = humanize(k)
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            cols = list(dict.fromkeys(c for x in v for c in x))
            head = "".join(f"<th>{esc(humanize(c)[0])}{(' (' + esc(humanize(c)[1]) + ')') if humanize(c)[1] else ''}</th>"
                           for c in cols)
            body = "".join("<tr>" + "".join(f"<td>{esc(fmt_num(x.get(c, '')))}</td>" for c in cols) + "</tr>" for x in v)
            items.append(f"<li><span class='k'>{esc(name)}</span><table class='mini'><tr>{head}</tr>{body}</table></li>")
            continue
        if isinstance(v, list):
            if v and all(isinstance(x, (list, tuple)) for x in v):
                val = f"[{len(v)} points]"
            else:
                val = ", ".join(fmt_num(x) for x in v[:16]) + (" …" if len(v) > 16 else "") if v else "none"
        elif isinstance(v, dict):
            val = "; ".join(f"{kk} {fmt_num(vv) if not isinstance(vv, (list, dict)) else '…'}" for kk, vv in v.items()) or "none"
        else:
            val = fmt_num(v) + (f" {unit}" if unit else "")
        cls = " class='trap'" if str(k).startswith("wrong_if") else ""
        items.append(f"<li{cls}><span class='k'>{esc(name)}</span> <span class='v'>{esc(val)}</span></li>")
    return "<ol class='chain'>" + "".join(items) + "</ol>"


# ------------------------------------------------------------------------------------------------ main build
@dataclass
class Pilot:
    label: str
    tasks: Path
    results: Path


def parse_pilot(s: str) -> Pilot:
    label = None
    if "=" in s.split(":", 1)[0]:
        label, s = s.split("=", 1)
    if ":" not in s:
        raise argparse.ArgumentTypeError(f"--pilot wants tasks_dir:results_dir, got {s!r}")
    t, r = s.split(":", 1)
    return Pilot(label or Path(r).name, Path(t), Path(r))


def git_commit() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def group_accuracy(tasks: dict, rows: list[dict], models: list[str], label_prefix: str = "") -> list[dict]:
    groups: OrderedDict = OrderedDict()
    changed = {r["_dir"] for r in rows if not matches(tasks.get(r["task_id"]), r)}   # any mismatch: whole run is old
    for r in rows:
        t = tasks.get(r["task_id"])
        if r["_dir"] not in changed:
            key = (r.get("question_type") or t.get("question_type") or "unknown", diff_label(t),
                   t.get("generator_version") or "")
        else:                                          # the task file was regenerated since: version unknown
            key = (r.get("question_type") or "unknown", "", "task file regenerated since")
        g = groups.setdefault(key, {"rows": []})
        g["rows"].append(r)
    out = []
    for (qt, dl, gv), g in groups.items():
        label = "  ·  ".join(x for x in (qt, dl, gv) if x)
        if label_prefix:
            label = f"{label_prefix}: {label}"
        out.append({"qtype": qt, "diff": dl, "gen": gv, "label": label,
                    "acc": {m: acc([r for r in g["rows"] if r["model"] == m]) for m in models}})
    return out


def build(args) -> dict:
    task_dirs, result_dirs = [Path(p) for p in args.tasks], [Path(p) for p in args.results]
    out = Path(args.out)
    tasks_by_dir = {d: load_tasks(d) for d in task_dirs}
    tasks: OrderedDict = OrderedDict()
    for d in task_dirs:
        for t in tasks_by_dir[d]:
            tasks.setdefault(t["task_id"], t)
    rsets = [load_results(d) for d in result_dirs]
    rows = [r for rs in rsets for r in rs.rows]
    unknown = sorted({r["task_id"] for r in rows} - set(tasks))
    if unknown:
        warn(f"{len(unknown)} result rows have no task in the --tasks folders: {', '.join(unknown[:5])}")
    changed = {r["_dir"] for r in rows if r["task_id"] in tasks and not matches(tasks[r["task_id"]], r)}
    stale = sorted({r["task_id"] for r in rows if r["_dir"] in changed and r["task_id"] in tasks})
    if stale:
        warn(f"{len(stale)} tasks changed after they were scored (ref_answer differs from tasks.jsonl): "
             f"{', '.join(stale[:5])}; their images and steps are left out of the exemplar and gallery")
    models = list(dict.fromkeys(r["model"] for r in rows))
    pilots = [parse_pilot(p) for p in args.pilot or []]
    for p in pilots:
        for r in load_results(p.results).rows:
            models.extend([r["model"]] if r["model"] not in models else [])
    colors = {m: i for i, m in enumerate(models)}   # model -> pattern index (all red)
    reported_ids = [tid for tid in tasks if any(r["task_id"] == tid for r in rows)]
    cmd = "uv run python -m report " + " ".join(shlex.quote(a) for a in args.argv)
    pairs = list(zip(task_dirs, result_dirs)) if len(task_dirs) == len(result_dirs) else []
    eval_cmds = [f"uv run python -m eval.run --tasks {rel(t)} --out {rel(r)}" for t, r in pairs] or \
        [f"uv run python -m eval.run --tasks <tasks> --out {rel(r)}" for r in result_dirs]
    evidence: list[str] = []

    def ev(value, what, source, command):
        evidence.append(f"{value} · {what} · {source} · {command}")

    csvs = ", ".join(rel(rs.dir / "responses.csv") for rs in rsets)

    # ---- headline
    per_model = {m: acc([r for r in rows if r["model"] == m]) for m in models if any(r["model"] == m for r in rows)}
    stop_rows = [r for r in rows if r.get("finish_reason") == "stop" and not r.get("error")]
    all_stop = bool(rows) and len(stop_rows) == len(rows)
    costs = [cost_of(rs) for rs in rsets]
    total_cost = sum(c for c, _ in costs if c is not None) if any(c is not None for c, _ in costs) else None
    mock = any((rs.run_config or {}).get("mock") for rs in rsets)
    by_task: dict = {}
    for r in rows:
        by_task.setdefault(r["task_id"], []).append(r)
    all_wrong = [tid for tid in reported_ids
                 if by_task[tid] and all(r.get("correct") == "0" for r in by_task[tid])
                 and len({r["model"] for r in by_task[tid]}) == len(per_model)]
    funnel = funnel_data(task_dirs, tasks_by_dir)

    ev(len(reported_ids), "tasks reported (tasks with model rows)",
       ", ".join(rel(d / "tasks.jsonl") for d in task_dirs), cmd)
    for m, (c, n) in per_model.items():
        ev(f"{c}/{n}", f"{m} accuracy on the reported tasks", csvs, " ; ".join(eval_cmds))
    ev(f"{len(all_wrong)}/{len(reported_ids)}", "reported tasks every model got wrong", csvs, " ; ".join(eval_cmds))
    if total_cost is not None:
        ev(fmt_usd(total_cost), "model cost of the reported run(s), all calls, USD",
           ", ".join(rel(s) for c, s in costs if s is not None), " ; ".join(eval_cmds))
    ev(f"{'yes' if all_stop else 'no'} ({len(stop_rows)}/{len(rows)})",
       "reported rows with finish_reason=stop and no error", csvs, " ; ".join(eval_cmds))
    if funnel["passed"] is not None:
        base = funnel["attempted"] if funnel["attempted"] is not None else funnel["checked"]
        ev(f"{funnel['passed']}/{base}", "tasks that passed every check, of those "
           + ("generated" if funnel["attempted"] is not None else "checked"),
           ", ".join(rel(s) for s in funnel["sources"]),
           " ; ".join(f"uv run python -m factory validate --tasks {rel(d)}" for d in task_dirs))

    # ---- failures
    failures = []
    for tid in reported_ids:
        t = tasks[tid]
        if tid in stale:
            continue
        for r in by_task[tid]:
            if r.get("correct") != "0":
                continue
            content, reasoning = reply_texts(r)
            tag = classify(t, r, content, reasoning)
            failures.append({"task": t, "row": r, "tag": tag, "content": content, "reasoning": reasoning,
                             "detail": picked_detail(t, r.get("parsed", ""))})

    # ---- exemplar: every model wrong; prefer a truth image, then an overlay, then steps, then distinct answers
    truth_dirs = [Path(p) for p in args.truth_dir or []]

    def ex_score(tid):
        t = tasks[tid]
        return (truth_image(t, truth_dirs) is not None, bool(t.get("overlay")), bool(t.get("steps")),
                len({norm_label(r.get("parsed")) for r in by_task[tid]}),
                sum(f["tag"].kind in ("wrong", "method", "trap") for f in failures if f["task"]["task_id"] == tid))
    fresh = [x for x in reported_ids if x not in stale]
    cands = [x for x in all_wrong if x not in stale] or \
        sorted([x for x in fresh if any(r.get("correct") == "0" for r in by_task[x])],
               key=lambda tid: -sum(r.get("correct") == "0" for r in by_task[tid]))[:1]
    ex_id = max(cands, key=ex_score) if cands else None

    # ---- pilots
    pilot_groups, pilot_sources = [], []
    for p in pilots:
        ptasks = OrderedDict((t["task_id"], t) for t in load_tasks(p.tasks))
        prs = load_results(p.results)
        pilot_sources.append(prs)
        gs = group_accuracy(ptasks, prs.rows, models)
        for g in gs:
            g["pilot"] = p
            if len(pilots) > 1:
                g["label"] = f"{p.label}: {g['label']}"
            for m, (c, n) in g["acc"].items():
                if n:
                    ev(f"{c}/{n}", f"{m} on pilot {p.label} ("
                       + ", ".join(x for x in (g["qtype"], g["diff"], g["gen"]) if x) + ")",
                       rel(p.results / "responses.csv"), f"uv run python -m eval.run --tasks {rel(p.tasks)} --out {rel(p.results)}")
        pilot_groups += gs
    pilot_costs = [cost_of(rs) for rs in pilot_sources]
    if any(c is not None for c, _ in pilot_costs):
        ev(fmt_usd(sum(c for c, _ in pilot_costs if c is not None)), "model cost of the pilot runs, all calls, USD",
           ", ".join(rel(s) for c, s in pilot_costs if s is not None), "see the pilot eval commands above")
    chart_groups = pilot_groups or group_accuracy(tasks, rows, models)

    args.stale, args.unknown = stale, unknown
    page = render_page(args, out, tasks, rows, rsets, models, colors, per_model, reported_ids, all_wrong, all_stop,
                       stop_rows, total_cost, mock, funnel, failures, ex_id, truth_dirs, by_task, chart_groups,
                       bool(pilot_groups), pilots, cmd, pairs, eval_cmds, task_dirs, result_dirs)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    ev_path = Path(args.evidence) if args.evidence else out.parent / "evidence.md"
    ev_path.write_text("# Report evidence (generated by `report/build.py`; paste lines into docs/EVIDENCE.md)\n\n"
                       "Format: value · what it measures · source file · command\n"
                       f"Page rebuilt with: `{cmd}`\n\n" + "\n".join(f"- {e}" for e in evidence) + "\n",
                       encoding="utf-8")
    return {"out": out, "evidence": ev_path, "tasks": len(reported_ids), "failures": len(failures),
            "exemplar": ex_id, "per_model": per_model, "lines": evidence}


# ------------------------------------------------------------------------------------------------ HTML
FONTS_URL = ("https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans+Condensed:"
             "wght@500;600&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&display=swap")

CSS = """
:root{--paper:#F3EEDF;--sheet:#F8F4E9;--ink:#1E1B16;--ink2:#4A443A;--muted:#7A7264;--hair:rgba(30,27,22,.25);
--truth:#2F7FC1;--model:#D2412C;--contour:#9A5B2E;--contour2:#6E3F1E;
--label:"IBM Plex Sans Condensed","Arial Narrow","Helvetica Neue",Arial,sans-serif;
--mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
--serif:"Source Serif 4",Georgia,"Times New Roman",serif}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:18px/1.55 var(--serif)}
.wrap{max-width:1200px;margin:0 auto;padding:32px 24px 72px}
.cap{font-family:var(--label);font-weight:600;text-transform:uppercase;letter-spacing:.14em}
.mono,code{font-family:var(--mono);font-variant-numeric:tabular-nums}
code{font-size:.86em}
h1,h2,h3{font-family:var(--label);font-weight:600;text-transform:uppercase;letter-spacing:.14em;margin:0}
h1{font-size:40px;line-height:1.1;letter-spacing:.12em}
h2{font-size:22px;margin-bottom:6px}
h3{font-size:14px;margin-bottom:8px;color:var(--ink2)}
.collar{border:4px double var(--ink);padding:14px 22px 12px;margin-bottom:30px}
.collar .row{display:flex;justify-content:space-between;gap:16px;flex-wrap:wrap;font-size:12px;color:var(--ink2)}
.collar .row .mono{font-size:12px}
.collar .mid{border-top:1px solid var(--hair);border-bottom:1px solid var(--hair);margin:10px 0;padding:22px 0 20px}
.collar .sub{font-style:italic;color:var(--ink2);font-size:20px;max-width:860px;margin:10px 0 0}
.key{display:inline-flex;align-items:center;gap:6px;margin-left:14px}
.sw{display:inline-block;width:12px;height:12px;vertical-align:-1px}
.sw.truth{background:var(--truth)}.sw.contour{background:var(--contour)}
.dot{display:inline-block;width:12px;height:12px;margin-right:7px;vertical-align:-1px;border:1.5px solid var(--model)}
.dot.m0{background:var(--model)}
.dot.m1,.dot.m3{background:repeating-linear-gradient(45deg,var(--model) 0 1.5px,var(--paper) 1.5px 4px)}
.dot.m2{background:repeating-linear-gradient(45deg,var(--model) 0 1.5px,transparent 1.5px 4px),
repeating-linear-gradient(-45deg,var(--model) 0 1.5px,var(--paper) 1.5px 4px)}
section{border-top:4px double var(--ink);padding:22px 0 30px;margin:0}
.lede{color:var(--ink2);margin:0 0 18px;max-width:900px;font-style:italic}
.muted{color:var(--muted)}
.banner{border:2px solid var(--ink);padding:10px 14px;margin:0 0 18px;font-family:var(--label);font-weight:600;
text-transform:uppercase;letter-spacing:.1em}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));border-left:1px solid var(--hair);
border-top:1px solid var(--hair)}
.tile{border-right:1px solid var(--hair);border-bottom:1px solid var(--hair);padding:14px 16px 16px;background:var(--sheet)}
.tile .big{font-family:var(--mono);font-size:38px;font-weight:600;line-height:1.15;font-variant-numeric:tabular-nums}
.tile .lbl{font-family:var(--label);font-weight:600;text-transform:uppercase;letter-spacing:.12em;font-size:13px;margin-top:6px}
.tile .note{font-family:var(--mono);color:var(--muted);font-size:12px;margin-top:2px;word-break:break-word}
.tile.truth .big{color:var(--truth)}
.tile .big.long{font-size:28px;padding-top:7px}
.tile.model .big{color:var(--model)}
.ex-imgs{display:grid;grid-template-columns:1fr;gap:14px;margin-bottom:20px}
.ex-imgs.two{grid-template-columns:1fr 1fr}
figure{margin:0}
figure img{width:100%;height:auto;border:1px solid var(--ink);display:block;background:#fff}
figcaption{font-family:var(--label);text-transform:uppercase;letter-spacing:.1em;font-size:12px;color:var(--ink2);margin-top:6px}
.ex-grid{display:grid;grid-template-columns:1.1fr .9fr;gap:28px}
.ex-side{display:grid;grid-template-columns:1.3fr 1fr;gap:28px;align-items:start}
.ex-side .q{font-size:15.5px}
.q{border-left:2px solid var(--ink);padding:4px 0 4px 16px;color:var(--ink);font-size:17px}
.ref{margin:16px 0 0}
.ans{font-family:var(--mono);font-weight:600;padding:1px 7px;border:1.5px solid;white-space:nowrap}
.ans.ok{color:var(--truth);border-color:var(--truth);background:rgba(47,127,193,.08)}
.ans.bad{color:var(--model);border-color:var(--model);background:rgba(210,65,44,.07)}
.models{display:grid;grid-template-columns:repeat(auto-fit,minmax(330px,1fr));gap:0;margin-top:22px;
border-left:1px solid var(--hair);border-top:1px solid var(--hair)}
.mcard{border-right:1px solid var(--hair);border-bottom:1px solid var(--hair);padding:16px 18px;background:var(--sheet)}
.who{font-family:var(--label);font-weight:600;text-transform:uppercase;letter-spacing:.12em;font-size:15px}
blockquote{margin:12px 0 0;padding:10px 14px;font-size:15px;color:var(--ink2);white-space:pre-wrap;word-break:break-word;
border-left:1px solid var(--hair)}
blockquote .src{display:block;font-family:var(--label);font-size:11.5px;text-transform:uppercase;letter-spacing:.12em;
color:var(--muted);margin-bottom:4px;font-style:normal}
mark{background:rgba(210,65,44,.12);border-bottom:2px solid var(--model);color:inherit;padding:0 1px}
.chain{margin:0;padding-left:22px;font-size:16px}
.chain li{margin:3px 0}
.chain li::marker{font-family:var(--mono);color:var(--muted)}
.chain .k{color:var(--ink2)}
.chain .v{font-family:var(--mono);font-weight:600;color:var(--truth)}
.chain li.trap .k,.chain li.trap .v{color:var(--muted);font-weight:400}
table{border-collapse:collapse}
table.mini{margin:6px 0 4px;font-size:13px}
table.mini th,table.mini td{border-bottom:1px solid var(--hair);padding:3px 12px 3px 0;text-align:left;font-family:var(--mono)}
table.mini th{font-family:var(--label);text-transform:uppercase;letter-spacing:.08em;color:var(--muted);font-weight:600;font-size:11.5px}
.pill{display:inline-block;font-family:var(--label);font-weight:600;font-size:12.5px;letter-spacing:.06em;padding:2px 8px;
border:1px solid var(--model);color:var(--model);line-height:1.4}
.pill b{font-weight:600;text-transform:uppercase;letter-spacing:.12em;margin-right:6px;opacity:.75}
.pill.k-unclassified{border-color:var(--hair);color:var(--muted)}
.gallery{display:grid;grid-template-columns:repeat(auto-fill,minmax(270px,1fr));gap:18px}
.card{border:1px solid var(--hair);background:var(--sheet);display:flex;flex-direction:column}
.thumb{display:block;aspect-ratio:4/3;background-size:cover;background-position:center;border-bottom:1px solid var(--hair)}
.card .body{padding:11px 13px 13px;display:flex;flex-direction:column;gap:7px;font-size:15px}
.chip{font-family:var(--mono);font-size:12px;color:var(--ink2);border:1px solid var(--hair);padding:0 6px}
.detail{font-family:var(--mono);font-size:12px;color:var(--muted)}
.tagsum{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 18px}
.chart{width:100%;height:auto;display:block;border:1px solid var(--hair)}
details{margin-top:12px}
summary{cursor:pointer;font-family:var(--label);text-transform:uppercase;letter-spacing:.12em;font-size:13px;color:var(--ink2)}
table.data{font-size:15px;margin-top:8px;width:100%}
table.data th,table.data td{border-bottom:1px solid var(--hair);padding:6px 10px 6px 0;text-align:left;vertical-align:top}
table.data th{font-family:var(--label);text-transform:uppercase;letter-spacing:.1em;color:var(--ink2);font-weight:600;font-size:13px;
white-space:nowrap}
table.data td.num,table.data td.mono{font-family:var(--mono);font-size:13.5px;word-break:break-word}
pre{border:1px solid var(--hair);background:var(--sheet);padding:12px 14px;overflow-x:auto;font-family:var(--mono);
font-size:13px;white-space:pre-wrap;word-break:break-word;margin:6px 0 0}
.src-note{font-family:var(--mono);font-size:12px;color:var(--muted);word-break:break-word}
footer{border-top:4px double var(--ink);padding-top:12px;color:var(--muted);font-size:14px;font-style:italic}
@media (max-width:860px){.ex-grid,.ex-side,.ex-imgs.two{grid-template-columns:1fr}h1{font-size:28px}.wrap{padding:16px 16px 56px}
.collar{padding:12px 14px}.tile .big{font-size:30px}table.data{display:block;overflow-x:auto}}
@media print{section{break-inside:avoid}}
"""

TAG_HELP = {
    "method": "the answer equals a wrong method the generator planted (steps key wrong_if_…)",
    "trap": "the answer equals a named decoy in steps (e.g. the nearest or lowest option)",
    "wrong": "first intermediate fact from steps that the model's text states with a different value",
    "skipped": "first whole-number fact from steps the model's text never states",
    "final": "every fact the text states matches steps, or (for a count) no intermediate fact to compare; the "
             "final number is off",
    "list": "a list answer: the items it missed or added compared with the reference",
    "picked": "what the data says about the option it picked (no step in its text could be checked)",
    "unclassified": "no steps, or the text does not show which step went wrong",
}


def render_page(args, out, tasks, rows, rsets, models, colors, per_model, reported_ids, all_wrong, all_stop,
                stop_rows, total_cost, mock, funnel, failures, ex_id, truth_dirs, by_task, chart_groups,
                from_pilots, pilots, cmd, pairs, eval_cmds, task_dirs, result_dirs) -> str:
    def dot(m):
        return f"<span class='dot m{colors.get(m, 0) % 4}'></span>"

    def pill(tag):
        inner = esc(tag.text) if tag.kind == "unclassified" else f"<b>{esc(tag.kind)}</b>{esc(tag.text)}"
        return f"<span class='pill k-{tag.kind}' title='{esc(TAG_HELP[tag.kind])}'>{inner}</span>"

    def link(p):
        return esc(os.path.relpath(Path(p).resolve(), out.parent.resolve()).replace(os.sep, "/"))

    P = []
    title = args.title or "Where the models break"
    sets = ", ".join(rel(d) for d in task_dirs)
    stamps = [c for c in ((rs.run_config or {}).get("timestamp") for rs in rsets) if c]
    commits = [c[:7] for c in ((rs.run_config or {}).get("git_commit") for rs in rsets) if c]
    run_id = " · ".join(x for x in [stamps[0].replace("+00:00", "Z") if stamps else "", commits[0] if commits else ""] if x)
    P.append(
        "<header class='collar'><div class='row'><span class='cap'>Visual Task Factory · evaluation report</span>"
        f"<span class='mono'>RUN {esc(run_id or 'not recorded')}</span></div>"
        f"<div class='mid'><h1>{esc(title)}</h1><p class='sub'>{len(reported_ids)} tasks, each answered by "
        f"{len(per_model)} models. Every number on this sheet is computed from the task and result files; the "
        "method box at the end rebuilds it.</p></div>"
        f"<div class='row'><span class='mono'>{esc(sets)} → {esc(', '.join(rel(d) for d in result_dirs))}</span>"
        "<span class='cap'><span class='key'><span class='sw truth'></span>truth</span>"
        + "".join(f"<span class='key'>{dot(m)}{esc(model_name(m))}</span>" for m in per_model)
        + "</span></div></header>")

    # 1. headline
    H = ["<section id='headline'><h2>Headline numbers</h2><p class='lede'>The reported run, straight from "
         "<code>responses.csv</code>.</p>"]
    if mock:
        H.append("<div class='banner'>MOCK run: run_config.json says mock=true. These are canned replies, "
                 "not model answers.</div>")
    if args.stale:
        H.append(f"<div class='banner'>{len(args.stale)} tasks were regenerated after they were scored (their answer "
                 "no longer equals ref_answer in responses.csv). Scores are as recorded; their images are left out.</div>")
    if args.unknown:
        H.append(f"<div class='banner'>{len(args.unknown)} result rows have no matching task in the task folders.</div>")
    H.append("<div class='tiles'>")
    H.append(f"<div class='tile'><div class='big'>{len(reported_ids)}</div><div class='lbl'>tasks reported</div>"
             f"<div class='note'>{len(rows)} model answers</div></div>")
    for m, (c, n) in per_model.items():
        pct = f"{100 * c / n:.0f}%" if n else "–"
        H.append(f"<div class='tile model'><div class='big'>{c}/{n}</div><div class='lbl'>{dot(m)}{esc(model_name(m))}"
                 f"</div><div class='note'>{pct} correct · {esc(m)}</div></div>")
    H.append(f"<div class='tile'><div class='big'>{len(all_wrong)}/{len(reported_ids)}</div>"
             f"<div class='lbl'>tasks every model missed</div></div>")
    if total_cost is not None:
        H.append(f"<div class='tile'><div class='big long'>{esc(fmt_usd(total_cost))}</div><div class='lbl'>model cost, "
                 f"this run</div><div class='note'>all {len(rows)} calls, from summary.json / raw usage</div></div>")
    H.append(f"<div class='tile'><div class='big'>{'Yes' if all_stop else 'No'}</div>"
             f"<div class='lbl'>every reply complete</div><div class='note'>{len(stop_rows)}/{len(rows)} rows "
             f"finish_reason=stop, no error</div></div>")
    if funnel["passed"] is not None:
        base = funnel["attempted"] if funnel["attempted"] is not None else funnel["checked"]
        H.append(f"<div class='tile'><div class='big'>{funnel['passed']}/{base}</div><div class='lbl'>passed every "
                 f"check</div><div class='note'>of the tasks "
                 f"{'generated' if funnel['attempted'] is not None else 'checked'}</div></div>")
    H.append("</div></section>")
    P.append("".join(H))

    # 2. exemplar
    E = ["<section id='exemplar'><h2>The hardest task</h2>"]
    if ex_id is None:
        E.append("<p class='muted'>No task was answered wrongly, so there is no exemplar.</p>")
    else:
        t = tasks[ex_id]
        every = ex_id in all_wrong
        E.append(f"<p class='lede'><code>{esc(ex_id)}</code> · <span class='chip'>{esc(t.get('question_type', ''))}"
                 f"</span> <span class='chip'>{esc(diff_label(t))}</span> · "
                 f"{'every model got it wrong' if every else 'the task most models got wrong'}.</p>")
        img = Path(t["_dir"]) / t.get("image", "")
        tru = truth_image(t, truth_dirs)
        figs = []
        uri = image_uri(img, 1500) if img.is_file() else ""
        if uri:
            figs.append(f"<figure><a href='{link(img)}'><img src='{uri}' alt='Task image for {esc(ex_id)}'></a>"
                        f"<figcaption>The image the models saw</figcaption></figure>")
        else:
            figs.append(f"<p class='muted'>Image not found: {esc(rel(img))}</p>")
        if tru:
            figs.append(f"<figure><a href='{link(tru)}'><img src='{image_uri(tru, 1500)}' alt='Truth overlay for "
                        f"{esc(ex_id)}'></a><figcaption>Truth overlay, drawn from the data · "
                        f"<span class='mono'>{esc(rel(tru))}</span></figcaption></figure>")
        question = (f"<h3>Question</h3><div class='q'>{esc(t.get('question', ''))}</div>"
                    f"<p class='ref'><span class='cap' style='font-size:13px'>Reference answer</span> "
                    f"<span class='ans ok'>{esc(scoring_cell(t.get('answer')))}</span> "
                    f"<span class='muted' style='font-style:italic'>computed from the data</span></p>")
        chain = f"<h3>The correct chain · steps</h3>{render_steps(t.get('steps'))}"
        if tru:                                        # map | truth, then question | chain
            E.append(f"<div class='ex-imgs two'>{''.join(figs)}</div>"
                     f"<div class='ex-grid'><div>{question}</div><div>{chain}</div></div>")
        else:                                          # map | question + chain
            E.append(f"<div class='ex-side'>{figs[0]}<div>{question}<div style='margin-top:22px'>{chain}</div></div></div>")
        E.append("<div class='models'>")
        for r in by_task[ex_id]:
            f = next((x for x in failures if x["row"] is r), None)
            ok = r.get("correct") == "1"
            E.append(f"<div class='mcard'><div class='who'>{dot(r['model'])}{esc(model_name(r['model']))}</div>"
                     f"<p style='margin:8px 0'>Answered <span class='ans {'ok' if ok else 'bad'}'>"
                     f"{esc(r.get('parsed') or '(none)')}</span>")
            if f:
                E.append(f" &nbsp;{pill(f['tag'])}</p>")
                if f["detail"] and f["tag"].kind != "picked":
                    E.append(f"<div class='detail'>{esc(f['detail'])}</div>")
                lab, body = excerpt(f["content"], f["reasoning"], f["tag"])
            else:
                E.append("</p>")
                c, rs = reply_texts(r)
                lab, body = excerpt(c, rs, Tag("unclassified", ""))
            E.append(f"<blockquote><span class='src'>{esc(lab)} excerpt</span>{body}</blockquote></div>")
        E.append("</div>")
    E.append("</section>")
    P.append("".join(E))

    # 3. failure gallery
    G = [f"<section id='failures'><h2>Failure gallery</h2><p class='lede'>Every wrong answer ({len(failures)}), "
         "tagged with the step that broke. The tag compares the model's text with the task's <code>steps</code>: "
         "a planted wrong method or decoy the answer matches, else the first intermediate fact it states wrong, "
         "else the first count it never states; <em>unclassified</em> when the text does not tell.</p>"]
    if failures:
        kinds = Counter(f["tag"].kind for f in failures)
        G.append("<div class='tagsum'>" + "".join(
            f"<span class='pill k-{k}' title='{esc(TAG_HELP[k])}'><b>{esc(k)}</b><span class='mono'>× {n}</span></span>"
            for k, n in sorted(kinds.items(), key=lambda kv: -kv[1])) + "</div>")
        css_imgs, ids = [], {}
        for f in failures:
            p = Path(f["task"]["_dir"]) / f["task"].get("image", "")
            if str(p) not in ids and p.is_file():
                uri = image_uri(p, 560)
                if uri:
                    ids[str(p)] = f"i{len(ids)}"
                    css_imgs.append(f".{ids[str(p)]}{{background-image:url({uri})}}")
        if css_imgs:
            G.append("<style>" + "".join(css_imgs) + "</style>")
        G.append("<div class='gallery'>")
        for f in failures:
            t, r, tag = f["task"], f["row"], f["tag"]
            p = Path(t["_dir"]) / t.get("image", "")
            thumb = (f"<a class='thumb {ids[str(p)]}' href='{link(p)}' role='img' aria-label='{esc(t['task_id'])}'></a>"
                     if str(p) in ids else "")
            G.append(f"<div class='card'>{thumb}<div class='body'><div><span class='chip'>"
                     f"{esc(r.get('question_type') or t.get('question_type', ''))}</span> <span class='chip'>"
                     f"{esc(diff_label(t))}</span> <span class='muted mono' style='font-size:12px'>{esc(t['task_id'])}</span></div>"
                     f"<div class='who'>{dot(r['model'])}{esc(model_name(r['model']))}</div>"
                     f"<div class='ta'>truth <span class='ans ok'>{esc(scoring_cell(t.get('answer')))}</span> · "
                     f"answer <span class='ans bad'>{esc(r.get('parsed') or '(none)')}</span></div>"
                     f"<div>{pill(tag)}</div>"
                     + (f"<div class='detail'>{esc(f['detail'])}</div>" if f["detail"] and tag.kind != "picked" else "") + "</div></div>")
        G.append("</div>")
        G.append("<details><summary>How each tag is derived</summary><table class='data'>" + "".join(
            f"<tr><td><span class='pill k-{k}'>{k}</span></td><td>{esc(v)}</td></tr>" for k, v in TAG_HELP.items())
            + "</table></details>")
    else:
        G.append("<p class='muted'>No wrong answers in the reported run.</p>")
    G.append("</section>")
    P.append("".join(G))

    # 4. accuracy by question type and difficulty
    A = ["<section id='accuracy'><h2>Accuracy by question type and difficulty</h2>"]
    if from_pilots:
        A.append("<p class='lede'>The pilot runs, in the order given: how accuracy moved as the questions and "
                 "difficulty changed. Bars show correct answers out of scored replies.</p>")
    else:
        A.append("<p class='lede'>The reported run by question type (no <code>--pilot</code> runs were given).</p>")
    if chart_groups:
        A.append(f"<img class='chart' src='{accuracy_chart(chart_groups, models, colors)}' alt='Grouped bar chart "
                 "of accuracy per question type and difficulty for each model'>")
        A.append("<details><summary>Table view</summary><table class='data'><tr><th>Group</th>"
                 + "".join(f"<th>{esc(model_name(m))}</th>" for m in models) + "<th>Source</th></tr>")
        for g in chart_groups:
            src = rel(g["pilot"].results) if g.get("pilot") else ", ".join(rel(d) for d in result_dirs)
            A.append(f"<tr><td>{esc(g['label'])}</td>" + "".join(
                f"<td class='num'>{g['acc'][m][0]}/{g['acc'][m][1]}</td>" for m in models)
                + f"<td class='mono'>{esc(src)}</td></tr>")
        A.append("</table></details>")
    else:
        A.append("<p class='muted'>No rows to chart.</p>")
    A.append("</section>")
    P.append("".join(A))

    # 5. funnel
    F = ["<section id='funnel'><h2>Validity funnel</h2>"]
    if funnel["stages"]:
        F.append("<p class='lede'>Generated tasks, then how many are still alive after each automatic check "
                 "(cumulative). Rejected tasks are never counted as model failures.</p>")
        F.append(f"<img class='chart' src='{funnel_chart(funnel['stages'])}' alt='Validity funnel bar chart'>")
        F.append("<details><summary>Table view</summary><table class='data'>" + "".join(
            f"<tr><td>{esc(k)}</td><td class='num'>{v}</td></tr>" for k, v in funnel["stages"]) + "</table></details>")
        if funnel["reasons"]:
            F.append("<details open><summary>Why tasks were rejected</summary><table class='data'>" + "".join(
                f"<tr><td class='num'>{n}</td><td>{esc(k)}</td></tr>" for k, n in funnel["reasons"].most_common())
                + "</table></details>")
        F.append(f"<p class='src-note'>SOURCE {esc(', '.join(rel(s) for s in funnel['sources']))}</p>")
    else:
        F.append("<p class='muted'>No <code>generation_log.json</code>, <code>validation_report.json</code> or "
                 "per-task checks in the reported task folders. Run <code>factory validate</code> on them.</p>")
    for m in funnel["missing"]:
        F.append(f"<p class='muted' style='font-size:14px'>{esc(m)}</p>")
    F.append("</section>")
    P.append("".join(F))

    # 6. method
    M = ["<section id='method'><h2>Method and reproducibility</h2><table class='data'>"]
    cfgs = [(rs.dir, rs.run_config) for rs in rsets if rs.run_config]

    def vals(get):
        return list(dict.fromkeys(str(v) for v in (get(c) for _, c in cfgs) if v not in (None, "")))
    rowsM = [("Models", ", ".join(dict.fromkeys(m for _, c in cfgs for m in c.get("models") or [])) or ", ".join(models)),
             ("Temperature", " / ".join(vals(lambda c: c.get("temperature")))),
             ("Reasoning effort", " / ".join(vals(lambda c: (c.get("reasoning") or {}).get("effort")))),
             ("max_tokens", " / ".join(vals(lambda c: c.get("max_tokens")))),
             ("Image sent", " / ".join(vals(lambda c: c.get("image_sent")))),
             ("Endpoint", " / ".join(vals(lambda c: c.get("endpoint")))),
             ("Eval commit", " / ".join(vals(lambda c: (c.get("git_commit") or "")[:10]))),
             ("Run timestamp", " / ".join(vals(lambda c: c.get("timestamp")))),
             ("Mock", " / ".join(vals(lambda c: c.get("mock"))))]
    for k, v in rowsM:
        M.append(f"<tr><th>{esc(k)}</th><td class='mono'>{esc(v or 'not recorded')}</td></tr>")
    M.append("</table>")
    if not cfgs:
        M.append("<p class='muted'>No run_config.json in the results folders.</p>")
    tmpl = vals(lambda c: c.get("prompt_template"))
    if tmpl:
        M.append("<h3 style='margin-top:20px'>Prompt template</h3>" + "".join(f"<pre>{esc(x)}</pre>" for x in tmpl))
    M.append("<h3 style='margin-top:20px'>Rebuild</h3><pre>")
    lines = [f"uv run python -m factory rebuild --tasks {rel(t)}   # same images, questions, answers from the seeds"
             for t in task_dirs]
    lines += [c + "   # both models, cached calls are free" for c in eval_cmds]
    lines.append(cmd + "   # this page and report/evidence.md")
    M.append(esc("\n".join(lines)) + "</pre>")
    M.append("<p class='muted' style='font-size:14px'>Results: " + esc(", ".join(rel(d) for d in result_dirs))
             + (". Pilots: " + esc(", ".join(f"{p.label} = {rel(p.tasks)}:{rel(p.results)}" for p in pilots))
                if pilots else "") + "</p></section>")
    P.append("".join(M))

    commit = git_commit()
    P.append(f"<footer>Built by <code>report/build.py</code>{(' at commit ' + esc(commit)) if commit else ''} from "
             "the files listed above. Numbers for slides and the README go through docs/EVIDENCE.md "
             "(see report/evidence.md).</footer>")
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            f"<title>{esc(title)}</title>"
            "<link rel='preconnect' href='https://fonts.googleapis.com'>"
            "<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>"
            f"<link rel='stylesheet' href='{FONTS_URL}'><style>{CSS}</style></head><body><main class='wrap'>"
            + "\n".join(P) + "</main></body></html>\n")


def scoring_cell(answer) -> str:
    if isinstance(answer, (list, dict)):
        return json.dumps(answer, ensure_ascii=False)
    return str(answer)


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = argparse.ArgumentParser(prog="python -m report", description="Build the static report page.")
    ap.add_argument("--tasks", action="append", required=True, help="task folder (repeatable)")
    ap.add_argument("--results", action="append", required=True, help="results folder (repeatable)")
    ap.add_argument("--pilot", action="append", help="[label=]tasks_dir:results_dir for the accuracy chart (repeatable)")
    ap.add_argument("--truth-dir", action="append", help="folder with <task_id>*truth*.png overlays (repeatable)")
    ap.add_argument("--title", help="page title (default: 'Where the models break')")
    ap.add_argument("--evidence", help="evidence file (default: evidence.md next to --out)")
    ap.add_argument("--out", default="report/index.html")
    a = ap.parse_args(argv)
    a.argv = argv
    s = build(a)
    print(f"wrote {s['out']} ({s['out'].stat().st_size // 1024} KB) and {s['evidence']}")
    print(f"{s['tasks']} tasks, {s['failures']} wrong answers, exemplar {s['exemplar']}")
    for m, (c, n) in s["per_model"].items():
        print(f"  {m}: {c}/{n}")
    return 0
