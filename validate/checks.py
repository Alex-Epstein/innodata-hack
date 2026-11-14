"""Every automatic check on one task. Each check is a function (ctx) -> (name, passed, detail).

The checks are family-agnostic: a family supplies what they need through contracts/FAMILY.md
(build, solve_independent, and build()'s layout.texts / layout.probes, stored in layout/<task_id>.json).
"""
from __future__ import annotations

import json
import math
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from types import ModuleType

from eval import scoring

ANSWER_TYPES = ("number", "integer", "label", "multiple_choice", "sequence")
MIN_TEXT_PX = 8.0          # smallest legible text height at the saved resolution
MAX_OVERLAP_PX = 2.0       # two text boxes may touch by at most this much
EDGE_SLACK_PX = 2.0        # a text box may poke this far past the image edge
DEFAULT_PROBE_TOL = 40     # max per-channel difference (0-255) between a probe pixel and its expected color


@dataclass
class Ctx:
    tasks_dir: Path
    rec: dict
    family: ModuleType | None = None
    side: dict = field(default_factory=dict)          # {"layout": {...}, "overlay": ...}
    _image = None

    @property
    def image_path(self) -> Path:
        return self.tasks_dir / str(self.rec.get("image", ""))

    @property
    def data_path(self) -> Path:
        return self.tasks_dir / str(self.rec.get("data", ""))

    def image(self):
        if self._image is None:
            from PIL import Image
            with Image.open(self.image_path) as im:
                self._image = im.convert("RGB")
        return self._image

    def template(self) -> str:
        if self.rec.get("template"):
            return self.rec["template"]
        qt = str(self.rec.get("question_type", ""))
        return qt.split(".", 1)[1] if "." in qt else qt


def _is_num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def tolerance_strings(v: float, kind: str) -> set[str]:
    """How a tolerance may be written in the question (same rule as the organizers' format checker)."""
    out = set()
    if kind == "rel":
        p = v * 100
        for s in (f"{p:g}", f"{p:.1f}", f"{p:.2f}"):
            out |= {s + "%", s + " %", s + " percent", s + " per cent"}
    out |= {f"{v:g}", repr(v), str(v)}
    return out


# ---------------------------------------------------------------------------------------------- schema
def schema(ctx: Ctx):
    r, bad = ctx.rec, []
    for k in ("task_id", "image", "question", "answer_type", "generator_version", "question_type", "family",
              "data"):
        if not isinstance(r.get(k), str) or not r.get(k).strip():
            bad.append(f"{k} missing or not a non-empty string")
    if r.get("answer") in (None, "", []):
        bad.append("answer missing or empty")
    if not isinstance(r.get("seed"), int) or isinstance(r.get("seed"), bool):
        bad.append("seed missing or not an integer")
    if r.get("difficulty") in (None, ""):
        bad.append("difficulty missing")
    refs = r.get("references")
    if not (isinstance(refs, list) and 1 <= len(refs) <= 2 and all(isinstance(x, str) and x.strip() for x in refs)):
        bad.append("references must be a list of 1 or 2 real sources")
    tid, seed, fam = r.get("task_id"), r.get("seed"), r.get("family")
    if isinstance(tid, str) and isinstance(seed, int) and isinstance(fam, str):
        if not (tid.startswith(fam + "-") and tid.endswith(f"{seed:06d}")):
            bad.append(f"task_id {tid!r} is not <family>-...-<seed, 6 digits>")
    img = r.get("image")
    if isinstance(img, str) and img:
        if Path(img).is_absolute():
            bad.append("image path is absolute (must be relative to the task folder)")
        elif not ctx.image_path.is_file() or ctx.image_path.stat().st_size == 0:
            bad.append(f"image file {img} not found or empty")
        elif ctx.image_path.suffix.lower() != ".png":
            bad.append("image is not a .png")
    if isinstance(r.get("data"), str) and r["data"] and not ctx.data_path.is_file():
        bad.append(f"data file {r['data']} not found")

    at, ans, q = r.get("answer_type"), r.get("answer"), r.get("question") or ""
    has_rel, has_abs = r.get("tolerance_rel") is not None, r.get("tolerance_abs") is not None
    if at not in ANSWER_TYPES:
        bad.append(f"answer_type {at!r} is not one of {', '.join(ANSWER_TYPES)}")
    elif at == "number":
        if not _is_num(ans):
            bad.append("answer_type number but answer is not a number")
        elif has_rel and has_abs:
            bad.append("both tolerance_rel and tolerance_abs set (use exactly one)")
        elif not (has_rel or has_abs):
            if not float(ans).is_integer():
                bad.append("non-integer number answer without a tolerance")
        else:
            kind = "rel" if has_rel else "abs"
            tv = r.get(f"tolerance_{kind}")
            if not _is_num(tv) or tv <= 0:
                bad.append(f"tolerance_{kind} must be a positive number")
            elif kind == "rel" and tv >= 1:
                bad.append("tolerance_rel >= 1 (it is a fraction: 0.05 means 5%)")
            elif not any(s in q for s in tolerance_strings(float(tv), kind)):
                bad.append(f"tolerance_{kind}={tv} is not stated in the question")
    elif at == "integer":
        if not (_is_num(ans) and float(ans).is_integer()):
            bad.append("answer_type integer but answer is not a whole number")
    elif at == "label":
        if not isinstance(ans, str):
            bad.append("answer_type label but answer is not a string")
    elif at == "multiple_choice":
        opts = r.get("options")
        if not isinstance(opts, list) or len(opts) < 2:
            bad.append("multiple_choice without an options list")
        elif not (isinstance(ans, str) and re.fullmatch(r"[A-Z]", ans) and ord(ans) - 65 < len(opts)):
            bad.append("multiple_choice answer is not an option letter within the options")
    elif at == "sequence":
        if not isinstance(ans, list) or not ans:
            bad.append("answer_type sequence but answer is not a non-empty list")
    if at in ("label", "multiple_choice", "sequence") and (has_rel or has_abs):
        bad.append(f"tolerance set on a {at} answer")
    return "schema", not bad, "; ".join(bad) or "all fields present and well-formed"


# ---------------------------------------------------------------------------------------------- data first
def data_first(ctx: Ctx):
    if not ctx.data_path.is_file():
        return "data_first", False, "data JSON missing"
    if not ctx.image_path.is_file():
        return "data_first", False, "image missing"
    from factory.render import sha256_file
    try:
        data = json.loads(ctx.data_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return "data_first", False, f"data JSON does not parse: {e}"
    for k in ("task_id", "seed"):
        if isinstance(data, dict) and k in data and data[k] != ctx.rec.get(k):
            return "data_first", False, f"data JSON {k}={data[k]!r} but the task says {ctx.rec.get(k)!r}"
    recorded = ctx.rec.get("data_sha256")
    if recorded and sha256_file(ctx.data_path) != recorded:
        return "data_first", False, "data JSON changed since generation (SHA-256 differs from the task record)"
    if ctx.data_path.stat().st_mtime_ns <= ctx.image_path.stat().st_mtime_ns:
        return "data_first", True, "data JSON written before the PNG (mtime)"
    if recorded and ctx.rec.get("data_written_first") is True:
        return "data_first", True, "order recorded at generation; data SHA-256 unchanged since"
    return "data_first", False, "data JSON is newer than the PNG and no generation record proves the order"


# ---------------------------------------------------------------------------------------------- two solvers
def _as_reply(x) -> str:
    return json.dumps(x, ensure_ascii=False) if isinstance(x, (list, dict)) else str(x)


def two_solvers(ctx: Ctx):
    if ctx.family is None:
        return "two_solvers", False, f"family {ctx.rec.get('family')!r} not available"
    data = json.loads(ctx.data_path.read_text(encoding="utf-8"))
    note = ""
    try:
        got = ctx.family.solve_independent(data, ctx.template())
    except Exception as e:
        if isinstance(data, dict) and isinstance(data.get("data"), dict):
            got = ctx.family.solve_independent(data["data"], ctx.template())   # family reads the inner dict
            note = " (solver took the inner 'data' dict)"
        else:
            raise e
    ok = scoring.score(_as_reply(got), ctx.rec)
    return "two_solvers", ok, f"independent {_as_reply(got)} vs build {_as_reply(ctx.rec.get('answer'))}{note}"


# ---------------------------------------------------------------------------------------------- legibility
def legibility(ctx: Ctx):
    texts = ((ctx.side.get("layout") or {}).get("texts")) or []
    if not texts:
        return "legibility", False, "build() returned no layout.texts"
    import numpy as np
    W, H = ctx.image().size
    a = np.array([[float(v) for v in t[:4]] for t in texts])
    x0, x1 = np.minimum(a[:, 0], a[:, 2]), np.maximum(a[:, 0], a[:, 2])
    y0, y1 = np.minimum(a[:, 1], a[:, 3]), np.maximum(a[:, 1], a[:, 3])
    size = np.array([float(t[4]) if len(t) > 4 else 0.0 for t in texts])
    size = np.where(size > 0, size, y1 - y0)
    problems = []
    small = np.flatnonzero(size < MIN_TEXT_PX)
    if small.size:
        problems.append(f"{small.size} text(s) under {MIN_TEXT_PX:g} px (smallest {size.min():.1f} px)")
    out = np.flatnonzero((x0 < -EDGE_SLACK_PX) | (y0 < -EDGE_SLACK_PX) | (x1 > W + EDGE_SLACK_PX)
                         | (y1 > H + EDGE_SLACK_PX))
    if out.size:
        problems.append(f"{out.size} text box(es) cut off at the image edge")
    pairs, worst = 0, 0.0
    for i in range(len(a) - 1):
        ow = np.minimum(x1[i], x1[i + 1:]) - np.maximum(x0[i], x0[i + 1:])
        oh = np.minimum(y1[i], y1[i + 1:]) - np.maximum(y0[i], y0[i + 1:])
        hit = (ow > MAX_OVERLAP_PX) & (oh > MAX_OVERLAP_PX)
        if hit.any():
            pairs += int(hit.sum())
            worst = max(worst, float(np.minimum(ow, oh)[hit].max()))
    if pairs:
        problems.append(f"{pairs} overlapping text pair(s) (worst {worst:.1f} px)")
    return ("legibility", not problems,
            "; ".join(problems) or f"{len(texts)} texts, all >= {MIN_TEXT_PX:g} px, none overlapping")


# ---------------------------------------------------------------------------------------------- render check
def _hex(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def render_matches_data(ctx: Ctx):
    probes = ((ctx.side.get("layout") or {}).get("probes")) or []
    if not probes:
        return "render_matches_data", False, "build() returned no layout.probes"
    im = ctx.image()
    W, H = im.size
    px = im.load()
    failed = []
    for p in probes:
        x, y = int(round(p["xy"][0])), int(round(p["xy"][1]))
        want, tol, r = _hex(p["expect"]), p.get("tol", DEFAULT_PROBE_TOL), int(p.get("r", 0))
        best, best_px = None, None
        for yy in range(max(0, y - r), min(H, y + r + 1)):
            for xx in range(max(0, x - r), min(W, x + r + 1)):
                got = px[xx, yy]
                d = max(abs(got[i] - want[i]) for i in range(3))
                if best is None or d < best:
                    best, best_px = d, got
        if best is None or best > tol:
            seen = "outside the image" if best is None else "#%02x%02x%02x" % best_px
            failed.append(f"{p.get('what', p['xy'])}: want {p['expect']}, got {seen}")
    n = len(probes)
    detail = f"{n - len(failed)}/{n} probes match"
    if failed:
        detail += ": " + "; ".join(failed[:3]) + (f"; +{len(failed) - 3} more" if len(failed) > 3 else "")
    return "render_matches_data", not failed, detail


# ---------------------------------------------------------------------------------------------- answer leak
def _shape(s: str) -> str:
    """'B' -> '[A-Z]', 'CB-07' -> '[A-Z][A-Z]-\\d\\d': the pattern of a label, to find its siblings."""
    out = []
    for ch in s:
        out.append(r"[A-Z]" if ch.isupper() else r"[a-z]" if ch.islower() else r"\d" if ch.isdigit()
                   else re.escape(ch))
    return "".join(out)


def _leaks(answer: str, question: str) -> tuple[bool, str]:
    answer = answer.strip()
    if not answer:
        return False, ""
    short = len(answer) <= 3
    flags = 0 if short else re.IGNORECASE               # "A" must not match the article "a"
    pat = rf"(?<![\w]){re.escape(answer)}(?![\w])"
    if not re.search(pat, question, flags):
        return False, "not in the question"
    # The answer is in the question. Fine if it is one of several candidates of the same shape
    # ("which bar, A, B or C?"); a leak if it is the only one.
    siblings = {m.group(0) for m in re.finditer(rf"(?<![\w]){_shape(answer)}(?![\w])", question)}
    siblings = {s for s in siblings if s.lower() != answer.lower()}
    if siblings:
        return False, f"appears only as one of {len(siblings) + 1} listed candidates"
    return True, f"the answer {answer!r} appears in the question with no other candidate like it"


def answer_not_in_question(ctx: Ctx):
    r = ctx.rec
    q, ans, at = str(r.get("question", "")), r.get("answer"), r.get("answer_type")
    if at == "multiple_choice":
        opts = r.get("options") or []
        idx = ord(str(ans)) - 65 if isinstance(ans, str) and len(ans) == 1 else -1
        if 0 <= idx < len(opts):
            if re.search(rf"(?i)\b(answer|correct)\b[^.?\n]{{0,20}}\b{re.escape(ans)}\b", q):
                return "answer_not_in_question", False, f"the question points at option {ans}"
            return "answer_not_in_question", True, "multiple choice: options are listed by design"
        return "answer_not_in_question", True, "no option to look for"
    if at in ("integer", "number") and isinstance(ans, (int, float)):
        if float(ans).is_integer() and abs(ans) < 10:
            return "answer_not_in_question", True, "single-digit number: too common to judge"
        txt = f"{int(ans)}" if float(ans).is_integer() else f"{ans:g}"
        nums = {scoring.to_number(m.group(0)) for m in re.finditer(r"(?<![\w.])[-+]?\d[\d,]*\.?\d*", q)}
        if float(ans) in nums:
            return "answer_not_in_question", False, f"the number {txt} appears in the question"
        return "answer_not_in_question", True, f"{txt} not in the question"
    if at == "sequence" and isinstance(ans, list):
        joined = re.sub(r"\s+", " ", ", ".join(map(str, ans)))
        if len(ans) > 1 and scoring.norm_label(joined) in scoring.norm_label(q):
            return "answer_not_in_question", False, "the whole sequence appears in order in the question"
        return "answer_not_in_question", True, "the sequence is not spelled out in the question"
    leak, why = _leaks(str(ans), q)
    return "answer_not_in_question", not leak, why


# ---------------------------------------------------------------------------------------------- reproducible
def reproducible(ctx: Ctx):
    if ctx.family is None:
        return "reproducible", False, f"family {ctx.rec.get('family')!r} not available"
    from factory.render import sha256_file
    from factory.tasks import build_task
    r = ctx.rec
    if r.get("generator_version") != ctx.family.VERSION:
        return ("reproducible", False,
                f"task made by {r.get('generator_version')}, family is now {ctx.family.VERSION}: regenerate")
    with tempfile.TemporaryDirectory(prefix="rebuild-") as tmp:
        new = build_task(ctx.family, r["seed"], ctx.template(), r["difficulty"], Path(tmp))
        new_png = sha256_file(Path(tmp) / new["image"])
        new_data = sha256_file(Path(tmp) / new["data"])
    diffs = []
    if new_png != sha256_file(ctx.image_path):
        diffs.append("PNG")
    if ctx.data_path.is_file() and new_data != sha256_file(ctx.data_path):
        diffs.append("data JSON")
    if new.get("question") != r.get("question"):
        diffs.append("question")
    if new.get("answer") != r.get("answer"):
        diffs.append("answer")
    if diffs:
        return "reproducible", False, "rebuild differs in " + ", ".join(diffs)
    return "reproducible", True, f"rebuilt byte-identical (PNG sha256 {new_png[:12]}...)"


CHECKS = [schema, data_first, two_solvers, render_matches_data, legibility, answer_not_in_question, reproducible]
NAMES = [f.__name__ for f in CHECKS]
