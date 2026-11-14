"""Reward function for this RL environment pack. Self-contained: standard library only.

    from verifier import reward, load_envs
    envs = load_envs("envs.jsonl")
    r = reward(envs[0], model_output)              # 1.0 or 0.0, the official exact score
    r = reward(envs[0], model_output, shaped=True)  # optional partial credit, see below

    python verifier.py            # self-test: every env's reference answer scores 1.0

OFFICIAL SCORING IS EXACT. `reward(env, out)` is 1.0 when the text after the last "FINAL ANSWER:" in `out`
matches the reference under the same rules the factory's evaluation uses (eval/scoring.py, vendored verbatim
below), and 0.0 otherwise. Every number we report uses this exact reward.

OPTIONAL SHAPING (`shaped=True`), for RL training only. It looks only at the final answer, never at the
reasoning, and gives 0.5 when the answer equals one of `reward_spec.shaping.near_values`:
  - crossings: the count is off by exactly one contour line (reference +/- 1).
  - sunset: off by exactly one uphill contour line (reference +/- minutes_per_uphill_contour), or the right
    magnitude with the sign flipped (the climb count was right, the subtraction was turned around).
    "Uphill count right, arithmetic wrong" in general cannot be read from the answer alone, so it is not shaped.
  - flood (a campsite name) and every other task: no shaping, exact only.
Known wrong methods (`reward_spec.shaping.trap_values`, e.g. leaving out index contours, ignoring the climb)
always score 0.0, even if they happen to fall next to the reference.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------------------------------------
# Vendored verbatim from eval/scoring.py (the factory's evaluation scorer)
# ---------------------------------------------------------------------------------------------------------
"""Prompt wrapper, answer extraction and scoring. The same code scores every model and every task.

A task's `question` already holds the answer format and any tolerance (contracts/SCHEMA.md).
PROMPT_TEMPLATE only adds the response instruction, identical for both models, and is recorded
in run_config.json.
"""

import json
import re

PROMPT_TEMPLATE = (
    "{question}\n\n"
    "Think step by step. Then end your reply with one final line in exactly this form:\n"
    "FINAL ANSWER: <your answer>"
)

_FINAL = re.compile(r"FINAL\s+ANSWER\s*[:：]\s*(.*)", re.IGNORECASE)
_NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_SEQ_SPLIT = re.compile(r"\s*(?:,|;|\n|->|→|\|)\s*")


def build_prompt(question: str) -> str:
    return PROMPT_TEMPLATE.format(question=question)


def parse_final_answer(text: str) -> str:
    """The text after the LAST 'FINAL ANSWER:' in the reply; "" if there is none.

    Markdown decoration (**, `, quotes) and a trailing full stop are removed. If the model put the
    answer on the line after the marker, that line is used."""
    if not text:
        return ""
    matches = list(_FINAL.finditer(text))
    if not matches:
        return ""
    m = matches[-1]
    ans = _clean(m.group(1))
    if not ans:
        for line in text[m.end():].splitlines():
            if _clean(line):
                ans = _clean(line)
                break
    return ans


def _clean(s: str) -> str:
    s = s.strip().strip("*`_ \t")
    boxed = re.search(r"\\boxed\{(.*)\}", s)             # LaTeX habit: $\boxed{12}$
    if boxed:
        s = boxed.group(1)
    s = re.sub(r"\\text\{([^}]*)\}", r"\1", s).strip("$ ")
    return s.strip("\"'“”‘’ ").rstrip(". ").strip("*` ")


# ---------------------------------------------------------------------------------------------- normalizers
def to_number(s) -> float | None:
    """'1,250 kW' -> 1250.0, 'R = 12.5 Ω' -> 12.5, '3/4' -> 0.75. None if no number is found."""
    if s is None:
        return None
    s = str(s).replace("−", "-").replace("–", "-").replace(",", "").strip()
    s = re.split(r"[=≈~]", s)[-1]
    frac = re.fullmatch(r"\s*([-+]?\d+)\s*/\s*(\d+)\s*\D*", s)
    if frac and int(frac.group(2)) != 0:
        return int(frac.group(1)) / int(frac.group(2))
    m = _NUMBER.search(s.replace(" ", ""))
    return float(m.group(0)) if m else None


def norm_label(s) -> str:
    """Case, punctuation and spacing don't count: 'Pump House 2.' == 'pump house 2'."""
    s = str(s).lower().replace("&", " and ")
    s = re.sub(r"[^a-z0-9$.\-: ]+", " ", s)
    s = re.sub(r"^\s*the\s+", "", s)
    return re.sub(r"\s+", " ", s).strip(" .")


def to_sequence(s) -> list[str]:
    """'L3, L4 and L7' or '["L3","L4","L7"]' -> ['l3', 'l4', 'l7'] (normalized items)."""
    if isinstance(s, list):
        items = s
    else:
        s = str(s).strip()
        items = None
        if s.startswith("["):
            try:
                items = json.loads(s)
            except json.JSONDecodeError:
                s = s.strip("[]")
        if not isinstance(items, list):
            items = [re.sub(r"^and\s+", "", x.strip(), flags=re.IGNORECASE) for x in _SEQ_SPLIT.split(s)]
    return [n for n in (norm_label(x) for x in items) if n]


def to_choice(s, options=None) -> str:
    """'(B)', 'B) 12 Ω', '**b**' -> 'B'. Falls back to matching the option text. '' if neither works."""
    s = str(s).strip()
    m = re.match(r"^\W*([A-Za-z])(?![A-Za-z])", s)
    if m:
        return m.group(1).upper()
    for i, opt in enumerate(options or []):
        if norm_label(opt) == norm_label(s):
            return chr(65 + i)
    return ""


# ---------------------------------------------------------------------------------------------- scoring
def score(parsed: str, task: dict) -> bool:
    """Is `parsed` (from parse_final_answer) correct for this task? An empty answer is always wrong."""
    if parsed is None or str(parsed).strip() == "":
        return False
    kind, ref = task["answer_type"], task["answer"]
    if kind == "integer":
        x = to_number(parsed)
        return x is not None and x == float(ref)
    if kind == "number":
        x = to_number(parsed)
        if x is None:
            return False
        ref = float(ref)
        if task.get("tolerance_abs") is not None:
            limit = float(task["tolerance_abs"])
        elif task.get("tolerance_rel") is not None:
            limit = float(task["tolerance_rel"]) * abs(ref)
        else:
            limit = 0.0
        return abs(x - ref) <= limit + 1e-9 * max(1.0, abs(ref))
    if kind == "label":
        return norm_label(parsed) == norm_label(ref)
    if kind == "multiple_choice":
        return to_choice(parsed, task.get("options")) == str(ref).strip().upper()
    if kind == "sequence":
        got, want = to_sequence(parsed), to_sequence(ref)
        if task.get("ordered") is False:             # optional task field: order doesn't matter (a set)
            return sorted(got) == sorted(want)
        return got == want
    raise ValueError(f"unknown answer_type {kind!r} in task {task.get('task_id')}")


def ref_answer_cell(answer) -> str:
    """How a task's answer is written in responses.csv (lists as JSON, so the checker can compare)."""
    return answer if isinstance(answer, str) else json.dumps(answer, ensure_ascii=False)


# ---------------------------------------------------------------------------------------------------------
# Pack API
# ---------------------------------------------------------------------------------------------------------
def _as_task(env: dict) -> dict:
    spec = env["reward_spec"]
    task = {"task_id": env.get("env_id"), "answer_type": spec["answer_type"], "answer": spec["reference"]}
    for k in ("tolerance_abs", "tolerance_rel", "options", "ordered"):
        if spec.get(k) is not None:
            task[k] = spec[k]
    return task


def reward(env: dict, model_output: str, shaped: bool = False) -> float:
    """1.0 if the model's FINAL ANSWER is correct (exact, as in the official evaluation), else 0.0.
    With shaped=True, 0.5 for a near miss listed in reward_spec.shaping (see the module docstring)."""
    parsed = parse_final_answer(model_output or "")
    if score(parsed, _as_task(env)):
        return 1.0
    shaping = env["reward_spec"].get("shaping") or {}
    if not shaped or not shaping.get("near_values") or parsed == "":
        return 0.0
    x = to_number(parsed)
    if x is None or x in [float(v) for v in shaping.get("trap_values", [])]:
        return 0.0
    return float(shaping.get("partial_credit", 0.5)) if x in [float(v) for v in shaping["near_values"]] else 0.0


def load_envs(path) -> list:
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


if __name__ == "__main__":
    import os
    import sys
    here = os.path.dirname(os.path.abspath(__file__))
    envs = load_envs(sys.argv[1] if len(sys.argv) > 1 else os.path.join(here, "envs.jsonl"))
    bad = [e["env_id"] for e in envs
           if reward(e, "FINAL ANSWER: " + ref_answer_cell(e["reward_spec"]["reference"])) != 1.0
           or reward(e, "no answer here") != 0.0]
    print(f"{len(envs) - len(bad)}/{len(envs)} environments: reference scores 1.0, empty reply 0.0")
    sys.exit(1 if bad else 0)
