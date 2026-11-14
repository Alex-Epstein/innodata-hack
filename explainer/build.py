"""Build explainer/index.html: how the Visual Task Factory works, with the pilot results.

    python3 explainer/build.py        # then open explainer/index.html

Every number on the page is read from results/ and tasks/ in this checkout (nothing typed by hand), and the
example images are linked from tasks/, so rebuild after any new run.
"""
from __future__ import annotations

import csv
import html
import io
import json
import re
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
REF = "HEAD"


def show(path: str) -> str:
    return (REPO / path).read_text(encoding="utf-8")


def jl(path):
    return [json.loads(x) for x in show(path).splitlines() if x.strip()]


def rows(path):
    return list(csv.DictReader(io.StringIO(show(path))))


commit = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", REF], capture_output=True,
                        text=True).stdout.strip()
commit_time = subprocess.run(["git", "-C", str(REPO), "log", "-1", "--format=%cd", "--date=format:%H:%M", REF],
                             capture_output=True, text=True).stdout.strip()
esc = html.escape
HAIKU, LUNA = "anthropic/claude-haiku-5.5", "openai/gpt-6-luna"

# ------------------------------------------------------------------------------------------ the pilot sets
SETS = [
    {"family": "topo", "template": "crossings", "tasks": "tasks/pilot_topo_crossings",
     "results": "results/pilot_topo_crossings", "title": "Rescue carry",
     "what": "Count every contour line the trail crosses between S and E"},
    {"family": "topo", "template": "sunset", "tasks": "tasks/pilot_topo_sunset",
     "results": "results/pilot_topo_sunset", "title": "Hiker vs sunset",
     "what": "Count the uphill crossings, apply Naismith's rule, minutes of daylight left"},
    {"family": "topo", "template": "flood", "tasks": "tasks/pilot_topo_flood",
     "results": "results/pilot_topo_flood", "title": "Dam failure",
     "what": "Follow the water at right angles to the contours: which of 6 camps floods"},
    {"family": "power", "template": "trip", "tasks": "tasks/pilot_power_trip",
     "results": "results/pilot2_power_trip", "title": "Breaker trip",
     "what": "Breakers trip on a 480 V single-line diagram: which loads lose power"},
    {"family": "power", "template": "dbl", "tasks": "tasks/pilot_power_dbl",
     "results": "results/pilot2_power_dbl", "title": "Double trip",
     "what": "Two breakers trip at once; trace alternate feeds across the sheet"},
    {"family": "power", "template": "iso", "tasks": "tasks/pilot_power_iso",
     "results": "results/pilot2_power_iso", "title": "Isolate for work",
     "what": "Which breakers must open to make a bus safe to work on"},
]
for s in SETS:
    s["task_list"] = jl(f"{s['tasks']}/tasks.jsonl")
    s["gen"] = json.loads(show(f"{s['tasks']}/generation_log.json"))
    s["val"] = json.loads(show(f"{s['tasks']}/validation_report.json"))
    s["rows"] = rows(f"{s['results']}/responses.csv")
    s["cfg"] = json.loads(show(f"{s['results']}/run_config.json"))
    s["score"] = {m: sum(r["correct"] == "1" for r in s["rows"] if r["model"] == m) for m in (HAIKU, LUNA)}
    s["n"] = {m: sum(1 for r in s["rows"] if r["model"] == m) for m in (HAIKU, LUNA)}
    s["complete"] = all(r["finish_reason"] == "stop" and not r["error"] for r in s["rows"])
    s["keep"] = min(s["score"].values()) <= 5          # keep rule: a model at 5 of 10 or lower
    s["version"] = sorted({t["generator_version"] for t in s["task_list"]})[0]

topo = [s for s in SETS if s["family"] == "topo"]
power = [s for s in SETS if s["family"] == "power"]


def tot(sets, m):
    return sum(s["score"][m] for s in sets), sum(s["n"][m] for s in sets)


# ------------------------------------------------------------------------------------------ the final 10
FINAL = {"family": "topo", "template": "final", "tasks": "tasks/final", "results": "results/final"}
FINAL["task_list"] = jl("tasks/final/tasks.jsonl")
FINAL["val"] = json.loads(show("tasks/final/validation_report.json"))
FINAL["gen"] = FINAL["val"]["generation"]
FINAL["rows"] = rows("results/final/responses.csv")
FINAL["cfg"] = json.loads(show("results/final/run_config.json"))
FINAL["score"] = {m: sum(r["correct"] == "1" for r in FINAL["rows"] if r["model"] == m) for m in (HAIKU, LUNA)}
FINAL["n"] = {m: sum(1 for r in FINAL["rows"] if r["model"] == m) for m in (HAIKU, LUNA)}
FINAL["complete"] = all(r["finish_reason"] == "stop" and not r["error"] for r in FINAL["rows"])
FINAL["version"] = sorted({t["generator_version"] for t in FINAL["task_list"]})[0]
final_by_t = {}
for t in FINAL["task_list"]:
    final_by_t.setdefault(t["template"], []).append(t)
TITLES = {s["template"]: s["title"] for s in SETS}
final_sets = []
for tpl, ts in final_by_t.items():
    ids = {t["task_id"] for t in ts}
    rr = [r for r in FINAL["rows"] if r["task_id"] in ids]
    final_sets.append({"title": TITLES.get(tpl, tpl), "template": tpl, "version": FINAL["version"], "keep": None,
                       "score": {m: sum(r["correct"] == "1" for r in rr if r["model"] == m) for m in (HAIKU, LUNA)},
                       "n": {m: sum(1 for r in rr if r["model"] == m) for m in (HAIKU, LUNA)}})
fh, fn = FINAL["score"][HAIKU], FINAL["n"][HAIKU]
_by = {}
for r in FINAL["rows"]:
    _by.setdefault(r["task_id"], {})[r["model"]] = r["parsed"]
cross_facts = "; ".join(f"{t['answer']} became {_by[t['task_id']][HAIKU]} and {_by[t['task_id']][LUNA]}"
                        for t in final_by_t.get("crossings", [])
                        if all(_by[t["task_id"]][m] != str(t["answer"]) for m in (HAIKU, LUNA)))
flood_miss = flood_decoy = 0
for t in final_by_t.get("flood", []):
    decoys = {t["steps"].get("dry_camp_most_directly_below_dam"), t["steps"].get("nearest_campsite_to_dam")}
    for m in (HAIKU, LUNA):
        if _by[t["task_id"]][m] != t["answer"]:
            flood_miss += 1
            flood_decoy += _by[t["task_id"]][m] in decoys
fl = FINAL["score"][LUNA]

# few-shot experiment (results/extra/fewshot): the results table, read from its summary
fs_cfg = json.loads(show("results/extra/fewshot/run_config.json"))
fs_rows, in_fs = [], False
for line in show("results/extra/fewshot/summary.md").splitlines():
    if line.startswith("| Mission | Model | Zero-shot"):
        in_fs = True
        continue
    if in_fs:
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip("|").split("|")]
        if not set(cells[0]) <= set("-"):
            fs_rows.append(cells)

# hand check of the final 10 (results/human/hand_check.md): rows and how many are confirmed by eye
hc_rows = [l for l in show("results/human/hand_check.md").splitlines() if l.startswith("| topo-")]
hc_total = len(hc_rows)
hc_fair = sum(1 for l in hc_rows if l.split("|")[5].strip().lower().startswith("yes"))
hc_confirmed = sum(1 for l in hc_rows if l.rstrip().rstrip("|").split("|")[-1].strip() not in ("☐", ""))
has_baseline = (REPO / "results/human/baseline.csv").exists()

th, tn = tot(topo, HAIKU)
tl, _ = tot(topo, LUNA)
ph, pn = tot(power, HAIKU)
pl, _ = tot(power, LUNA)
cost = sum(s["cfg"]["totals"]["cost_usd_all_calls"] for s in SETS + [FINAL]) + fs_cfg["totals"]["cost_usd_all_calls"]
calls = sum(s["cfg"]["totals"]["calls"] for s in SETS + [FINAL]) + fs_cfg["totals"]["calls"]
all_complete = all(s["complete"] for s in SETS + [FINAL])

# ------------------------------------------------------------------------------------------ the funnel
CHECKS = ["schema", "data_first", "two_solvers", "render_matches_data", "legibility", "answer_not_in_question",
          "reproducible"]
CHECK_TEXT = {
    "schema": "Every field the organizers require, with the right types; the image exists",
    "data_first": "The data JSON was written before the picture and is unchanged since",
    "two_solvers": "A second, independent solver computes the same answer",
    "render_matches_data": "Pixels at known points match the data (contour colour, breaker symbol)",
    "legibility": "Every label is at least 8 px tall, none overlap, none cut off",
    "answer_not_in_question": "The question does not give the answer away",
    "reproducible": "Rebuilding from the seed gives byte-identical PNG and data",
}
GATED = SETS + [FINAL]
attempted = sum(s["val"]["generation"]["attempted"] for s in GATED)
generated = sum(s["val"]["generation"]["kept"] for s in GATED)
funnel = [(c, sum(s["val"]["cumulative_funnel"][c] for s in GATED)) for c in CHECKS]
all_passed = sum(s["val"]["all_passed"] for s in GATED)
evaluated = sum(s["n"][HAIKU] for s in GATED)
kept_templates = sum(s["keep"] for s in SETS)

# ------------------------------------------------------------------------------------------ examples


def link_png(path):
    """Relative link from explainer/ to a PNG in tasks/ (None if the file is missing)."""
    return f"../{path}" if (REPO / path).exists() else None


def example(s, prefer_both_wrong=True):
    by_task = {}
    for r in s["rows"]:
        by_task.setdefault(r["task_id"], {})[r["model"]] = r
    pick = None
    for t in s["task_list"]:
        rr = by_task.get(t["task_id"], {})
        if all(rr.get(m, {}).get("correct") == "0" for m in (HAIKU, LUNA)):
            pick = t
            break
    pick = pick or s["task_list"][0]
    rr = by_task[pick["task_id"]]
    img = link_png(f"{s['tasks']}/{pick['image']}")
    overlay = link_png(f"{s['tasks']}/overlays/{pick['task_id']}_truth.png")
    return {"task": pick, "img": img, "overlay": overlay,
            "haiku": rr[HAIKU], "luna": rr[LUNA], "set": s}


FINAL_EX = []
for tpl, ts in final_by_t.items():
    FINAL_EX.append(dict(FINAL, title=TITLES.get(tpl, tpl), template=tpl, task_list=ts))
examples = [example(s) for s in FINAL_EX]

# ------------------------------------------------------------------------------------------ spike history
spike_md = show("results/spikes/README.md")
spike_rows = []
in_tbl = False
for line in spike_md.splitlines():
    if line.startswith("| Family | Result | Verdict"):
        in_tbl = True
        continue
    if in_tbl:
        if not line.startswith("|"):
            break
        cells = [c.strip() for c in line.strip("|").split("|")]
        if set(cells[0]) <= set("-"):
            continue
        spike_rows.append(cells)


def md_inline(s):
    s = esc(s)
    s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
    return re.sub(r"`(.+?)`", r"<code>\1</code>", s)


# ------------------------------------------------------------------------------------------ html pieces
def bar_chart(sets, label, rule=True):
    out = [f'<div class="chart{"" if rule else " norule"}" role="img" aria-label="{esc(label)}">']
    mid = "5" if rule else "half"
    top = "10 right" if rule else "all right"
    out.append(f'<div class="axis-top"><span></span><span class="ax"><b style="left:0">0</b><b style="left:50%">{mid}</b>'
               f'<b style="right:0">{top}</b></span><span></span></div>')
    for s in sets:
        out.append(f'<div class="grp"><div class="grp-label"><span class="cap">{esc(s["title"])}</span>'
                   f'<span class="muted">{esc(s["template"])} · {s["version"]}</span></div><div class="bars">')
        for m, cls, nm in ((HAIKU, "haiku", "Haiku"), (LUNA, "luna", "Luna")):
            k, n = s["score"][m], s["n"][m]
            out.append(f'<div class="bar-row" data-tip="{nm} · {esc(s["title"])}: {k} of {n} right">'
                       f'<span class="who">{nm}</span><span class="track"><span class="rule5"></span>'
                       f'<span class="bar {cls}" style="width:{100 * k / n:.1f}%"></span></span>'
                       f'<span class="val mono">{k}/{n}</span></div>')
        if s["keep"] is None:
            out.append(f'</div><div class="verdict final">{s["n"][HAIKU]} TASKS</div></div>')
        else:
            verdict = "KEEP" if s["keep"] else "TOO EASY"
            out.append(f'</div><div class="verdict {"keep" if s["keep"] else "drop"}">{verdict}</div></div>')
    rule_key = '<span class="key"><i class="rule-key"></i>keep rule: a model at 5/10 or lower</span>' if rule else ""
    out.append('<div class="chart-foot"><span class="key"><i class="sw haiku"></i>Haiku 5.5</span>'
               f'<span class="key"><i class="sw luna"></i>GPT-6 Luna</span>{rule_key}</div></div>')
    return "\n".join(out)


def table(sets):
    head = ("<tr><th>Family</th><th>Template</th><th>Version</th><th>Haiku</th><th>Luna</th><th>All replies "
            "complete</th><th>Cost</th><th>Verdict</th></tr>")
    body = "".join(
        f"<tr><td>{s['family']}</td><td>{s['template']}</td><td class='mono'>{s['version']}</td>"
        f"<td class='mono'>{s['score'][HAIKU]}/{s['n'][HAIKU]}</td><td class='mono'>{s['score'][LUNA]}/{s['n'][LUNA]}</td>"
        f"<td>{'yes' if s['complete'] else 'NO'}</td><td class='mono'>${s['cfg']['totals']['cost_usd_all_calls']:.4f}</td>"
        f"<td>{'keep' if s['keep'] else 'too easy'}</td></tr>" for s in sets)
    return f"<table class='data'>{head}{body}</table>"


def final_table():
    by = {}
    for r in FINAL["rows"]:
        by.setdefault(r["task_id"], {})[r["model"]] = r
    out = ["<table class='data'><tr><th>Task</th><th>Place</th><th>Computed answer</th><th>Haiku 5.5</th>"
           "<th>GPT-6 Luna</th></tr>"]
    for t in FINAL["task_list"]:
        m = re.search(r"real place \(([^)]+)\)", t["question"])
        cells = []
        for mod in (HAIKU, LUNA):
            r = by[t["task_id"]][mod]
            ok = r["correct"] == "1"
            cells.append(f"<td class='mono {'ok' if ok else 'bad'}'>{esc(r['parsed'] or '-')} {'✓' if ok else '✗'}</td>")
        out.append(f"<tr><td class='mono'>{esc(t['task_id'])}</td><td>{esc(m.group(1) if m else '')}</td>"
                   f"<td class='mono truthc'>{esc(str(t['answer']))}</td>{''.join(cells)}</tr>")
    return "".join(out) + "</table>"


def fewshot_table():
    head = "<tr><th>Mission</th><th>Model</th><th>No examples</th><th>2 worked examples</th></tr>"
    body = "".join("<tr>" + "".join(f"<td>{md_inline(c)}</td>" for c in r[:4]) + "</tr>" for r in fs_rows)
    return f"<table class='data'>{head}{body}</table>"


def steps_html(steps):
    if not steps:
        return ""
    items = []
    for k, v in steps.items():
        if isinstance(v, list) and v and isinstance(v[0], dict):
            v = f"{len(v)} entries (see data JSON)"
        elif isinstance(v, (list, dict)):
            v = json.dumps(v, ensure_ascii=False)
        items.append(f"<tr><td class='k'>{esc(k.replace('_', ' '))}</td><td class='mono'>{esc(str(v))}</td></tr>")
    return f"<table class='steps'>{''.join(items)}</table>"


def example_html(e, i):
    t, s = e["task"], e["set"]
    ans = t["answer"] if isinstance(t["answer"], str) else ", ".join(map(str, t["answer"])) if isinstance(
        t["answer"], list) else str(t["answer"])

    def model(r, nm):
        ok = r["correct"] == "1"
        return (f"<div class='reply {'ok' if ok else 'bad'}'><span class='cap'>{nm}</span>"
                f"<span class='mono big'>{esc(r['parsed'] or '(no answer)')}</span>"
                f"<span class='mark'>{'✓ right' if ok else '✗ wrong'}</span></div>")

    toggle = (f"<button class='toggle' data-target='ex{i}' data-a='{e['img']}' data-b='{e['overlay']}'>"
              "Show the truth overlay</button>") if e["overlay"] else ""
    return f"""
<article class="example">
  <header><span class="cap">{esc(s['family'])} · {esc(s['title'])}</span>
  <span class="mono muted">{esc(t['task_id'])} · seed {t['seed']} · difficulty {t['difficulty']}</span></header>
  <div class="ex-grid">
    <figure><a href="{e['img']}" target="_blank"><img id="ex{i}" src="{e['img']}" alt="task image {esc(t['task_id'])}"></a>
      <figcaption>{toggle}<span class="muted">click the image to open it full size</span></figcaption></figure>
    <div class="ex-side">
      <p class="q">{esc(t['question'])}</p>
      <div class="replies">
        <div class="reply truth"><span class="cap">Computed answer</span><span class="mono big">{esc(ans)}</span>
        <span class="mark">from the data, twice</span></div>
        {model(e['haiku'], 'Haiku 5.5')}{model(e['luna'], 'GPT-6 Luna')}
      </div>
      <details><summary>The reasoning chain the code recorded (<code>steps</code>)</summary>{steps_html(t.get('steps'))}</details>
    </div>
  </div>
</article>"""


stages = [
    ("01", "Real data in", "Elevation from USGS 3D Elevation Program tiles (4 real places) for topo; a randomly "
     "built switchgear system for power. Stored in the repo with checksums, nothing downloaded at run time.",
     "gen/topo/tiles/"),
    ("02", "Generate from a seed", "The seed picks the place, the window and the marks under fairness rules. The "
     "data JSON is written first, then the picture is drawn from it by code.",
     "factory generate --family topo --template crossings --seeds 0-9"),
    ("03", "Compute the answer twice", "The answer and its reasoning chain come from the data. A second solver, "
     "written a different way, must agree or the draw is thrown away.", "solve_independent()"),
    ("04", "Seven automatic checks", "Format, data first, two solvers, pixels match data, legibility, no answer "
     "leak, byte-identical rebuild. A task that fails one is out.", "factory validate --tasks …"),
    ("05", "Advisory review", "Claude Sonnet reads each task like a careful human and flags ambiguity or "
     "legibility. It never changes an answer; its flags go to the human hand check.", "validate.review"),
    ("06", "Evaluate Haiku and Luna", "The two models the organizers set. Same prompt, temperature 0, reasoning high, 64k tokens, cached replies, "
     "scored by the same code. Every reply and its cost is logged.", "factory eval --tasks … --out results/…"),
    ("07", "Keep only what stays hard", "A question template survives only if at least one model gets 5 of 10 or "
     "fewer right, with failures that come from reasoning, not from a bad picture.", "pilot rule"),
    ("08", "Anyone can rebuild it", "Judges regenerate every task from its seed and get the same bytes. A live "
     "demo builds, checks and scores a fresh task from a seed the judges pick.", "factory rebuild · factory fresh"),
]

stage_html = "".join(
    f"<li class='stage'><span class='num mono'>{n}</span><div><h4>{esc(h)}</h4><p>{esc(p)}</p>"
    f"<code>{esc(c)}</code></div></li>" for n, h, p, c in stages)

fmax = attempted or 1
funnel_rows = [("Seeds attempted", attempted, "generation_log.json"), ("Tasks generated", generated,
                                                                         "generation_log.json")]
funnel_rows += [(f"passed {c.replace('_', ' ')}", v, CHECK_TEXT[c]) for c, v in funnel]
funnel_rows += [("Evaluated on both models", evaluated, "responses.csv"),
                ("Templates kept by the rule", kept_templates, f"of {len(SETS)} templates")]
funnel_html = "".join(
    f"<div class='f-row' data-tip='{esc(n)}: {v}'><span class='f-name'>{esc(n)}</span>"
    f"<span class='f-track'><span class='f-bar' style='width:{100 * v / fmax:.1f}%'></span></span>"
    f"<span class='mono f-val'>{v}</span><span class='f-note muted'>{esc(note)}</span></div>"
    for n, v, note in funnel_rows[:-1])
funnel_html += (f"<div class='f-row last'><span class='f-name'>{esc(funnel_rows[-1][0])}</span><span class='f-track'>"
                f"</span><span class='mono f-val'>{kept_templates} / {len(SETS)}</span>"
                f"<span class='f-note muted'>kept: {', '.join(s['family'] + '.' + s['template'] for s in SETS if s['keep']) or 'none'}</span></div>")

spike_html = "".join(
    "<tr>" + "".join(f"<td>{md_inline(c)}</td>" for c in r[:3]) + "</tr>" for r in spike_rows)

page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Visual Task Factory · how it works</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans+Condensed:wght@500;600&family=Source+Serif+4:ital,wght@0,400;0,600;1,400&display=swap" rel="stylesheet">
<style>
:root {{
  --paper:#F3EEDF; --paper-2:#EAE3CF; --ink:#1E1B16; --ink-2:#5a5348; --rule:rgba(30,27,22,.25);
  --contour:#9A5B2E; --truth:#2F7FC1; --model:#D2412C; --you:#D9A441; --wood:#DCE8C8; --night:#0E1116;
}}
* {{ box-sizing:border-box; }}
body {{ margin:0; background:var(--paper); color:var(--ink); font:17px/1.55 "Source Serif 4", Georgia, serif; }}
.wrap {{ max-width:1180px; margin:0 auto; padding:0 32px; }}
.cap, h2, h3, h4, th, .verdict {{ font-family:"IBM Plex Sans Condensed", "Arial Narrow", sans-serif; text-transform:uppercase;
  letter-spacing:.14em; font-weight:600; }}
.mono, code {{ font-family:"IBM Plex Mono", Menlo, monospace; font-variant-numeric:tabular-nums; }}
code {{ font-size:.82em; background:rgba(30,27,22,.06); padding:1px 5px; }}
.muted {{ color:var(--ink-2); font-size:.85em; }}
.collar {{ border-bottom:3px double var(--ink); padding:22px 0 14px; display:flex; justify-content:space-between;
  align-items:baseline; gap:20px; flex-wrap:wrap; }}
.collar .cap {{ font-size:13px; }}
header.hero {{ padding:56px 0 40px; border-bottom:1px solid var(--rule); }}
header.hero h1 {{ font-family:"IBM Plex Sans Condensed", sans-serif; text-transform:uppercase; letter-spacing:.1em;
  font-size:52px; line-height:1.02; margin:0 0 18px; font-weight:600; }}
header.hero .lede {{ font-style:italic; font-size:24px; max-width:820px; margin:0 0 34px; }}
.stats {{ display:grid; grid-template-columns:repeat(4, 1fr); gap:0; border-top:1px solid var(--rule); }}
.stat {{ padding:18px 18px 6px 0; border-right:1px solid var(--rule); margin-right:18px; }}
.stat:last-child {{ border-right:0; }}
.stat .n {{ font-family:"IBM Plex Mono", monospace; font-size:40px; font-weight:600; line-height:1.1; }}
.stat .n.red {{ color:var(--model); }} .stat .n.blue {{ color:var(--truth); }}
.stat .l {{ font-size:14px; color:var(--ink-2); }}
section {{ padding:52px 0 18px; border-bottom:1px solid var(--rule); }}
h2 {{ font-size:15px; margin:0 0 6px; color:var(--contour); }}
h3 {{ font-size:28px; letter-spacing:.06em; margin:0 0 14px; }}
.beat {{ font-style:italic; font-size:21px; max-width:860px; margin:0 0 26px; }}
p {{ max-width:860px; }}
ol.stages {{ list-style:none; padding:0; margin:0; display:grid; grid-template-columns:repeat(2, 1fr); gap:0 36px; }}
.stage {{ display:flex; gap:16px; padding:16px 0; border-top:1px solid var(--rule); }}
.stage .num {{ font-size:22px; color:var(--contour); min-width:34px; }}
.stage h4 {{ margin:0 0 4px; font-size:15px; }}
.stage p {{ margin:0 0 6px; font-size:15.5px; }}
.flowline {{ display:flex; flex-wrap:wrap; gap:6px; align-items:center; margin:8px 0 28px; font-family:"IBM Plex Mono", monospace; font-size:13px; }}
.flowline span.n {{ border:1px solid var(--ink); padding:4px 9px; background:#fffdf5; }}
.flowline span.a {{ color:var(--contour); }}
/* charts */
.chart {{ margin:10px 0 8px; }}
.axis-top {{ display:grid; grid-template-columns:calc(220px + 52px) 1fr calc(60px + 90px); font:12px "IBM Plex Mono", monospace; color:var(--ink-2); height:18px; }}
.axis-top .ax {{ position:relative; }}
.axis-top .ax b {{ position:absolute; font-weight:400; transform:translateX(-50%); }}
.axis-top .ax b[style*="right"] {{ transform:none; }}
.grp {{ display:grid; grid-template-columns:220px 1fr 90px; align-items:center; border-top:1px solid var(--rule); padding:10px 0; }}
.grp-label {{ display:flex; flex-direction:column; }}
.grp-label .cap {{ font-size:14px; }}
.bars {{ display:flex; flex-direction:column; gap:6px; }}
.bar-row {{ display:grid; grid-template-columns:52px 1fr 60px; align-items:center; gap:0; cursor:default; }}
.bar-row:hover .track {{ background:rgba(30,27,22,.08); }}
.who {{ font:12px "IBM Plex Mono", monospace; color:var(--ink-2); }}
.track {{ position:relative; height:16px; background:rgba(30,27,22,.04); }}
.rule5 {{ position:absolute; left:50%; top:-4px; bottom:-4px; border-left:1.5px dashed var(--ink); opacity:.55; }}
.bar {{ position:absolute; left:0; top:2px; bottom:2px; border-radius:0 4px 4px 0; }}
.bar.haiku {{ background:var(--model); }}
.bar.luna {{ background:repeating-linear-gradient(135deg, var(--model) 0 3px, #f6d3cc 3px 6px); outline:1.5px solid var(--model); outline-offset:-1.5px; }}
.val {{ text-align:right; font-size:14px; }}
.verdict {{ font-size:12px; text-align:center; padding:4px 0; border:1px solid currentColor; margin-left:14px; }}
.verdict.keep {{ color:var(--truth); }} .verdict.drop {{ color:var(--ink-2); }} .verdict.final {{ color:var(--ink-2); border-style:dotted; }}
.chart.norule .rule5 {{ display:none; }}
td.ok {{ color:var(--ink-2); }} td.bad {{ color:var(--model); font-weight:600; }} td.truthc {{ color:var(--truth); font-weight:600; }}
.chart-foot {{ display:flex; gap:22px; flex-wrap:wrap; font:13px "IBM Plex Mono", monospace; color:var(--ink-2); padding-top:10px; border-top:1px solid var(--rule); }}
.sw {{ display:inline-block; width:14px; height:10px; margin-right:6px; vertical-align:middle; }}
.sw.haiku {{ background:var(--model); }}
.sw.luna {{ background:repeating-linear-gradient(135deg, var(--model) 0 3px, #f6d3cc 3px 6px); outline:1.5px solid var(--model); outline-offset:-1.5px; }}
.rule-key {{ display:inline-block; width:0; height:12px; border-left:1.5px dashed var(--ink); margin-right:6px; vertical-align:middle; }}
.two {{ display:grid; grid-template-columns:1fr 1fr; gap:40px; }}
table.data, table.spikes, table.steps {{ border-collapse:collapse; width:100%; font-size:14.5px; margin:8px 0 18px; }}
table th {{ font-size:12px; text-align:left; border-bottom:1px solid var(--ink); padding:6px 8px 6px 0; }}
table td {{ border-bottom:1px solid var(--rule); padding:6px 10px 6px 0; vertical-align:top; }}
table.steps td.k {{ font-family:"IBM Plex Sans Condensed", sans-serif; text-transform:uppercase; letter-spacing:.08em; font-size:12px; width:42%; }}
table.steps td {{ font-size:13px; word-break:break-word; }}
.toggle-table {{ font:13px "IBM Plex Mono", monospace; background:none; border:1px solid var(--ink); padding:4px 10px; cursor:pointer; }}
/* funnel */
.f-row {{ display:grid; grid-template-columns:250px 1fr 60px 330px; gap:14px; align-items:center; padding:5px 0; border-top:1px solid var(--rule); }}
.f-name {{ font-family:"IBM Plex Sans Condensed", sans-serif; text-transform:uppercase; letter-spacing:.08em; font-size:13px; }}
.f-track {{ height:14px; background:rgba(30,27,22,.04); position:relative; }}
.f-bar {{ position:absolute; left:0; top:2px; bottom:2px; background:var(--contour); border-radius:0 4px 4px 0; }}
.f-val {{ text-align:right; }}
.f-note {{ font-size:13px; }}
.f-row.last .f-val {{ color:var(--truth); font-weight:600; }}
/* examples */
.example {{ border:1px solid var(--ink); outline:1px solid var(--ink); outline-offset:3px; background:#fffdf5; margin:26px 0 34px; }}
.example header {{ display:flex; justify-content:space-between; gap:12px; padding:10px 16px; border-bottom:1px solid var(--rule); flex-wrap:wrap; }}
.ex-grid {{ display:grid; grid-template-columns:1.45fr 1fr; gap:0; }}
.ex-grid figure {{ margin:0; padding:14px; border-right:1px solid var(--rule); }}
.ex-grid img {{ width:100%; display:block; border:1px solid var(--rule); }}
figcaption {{ display:flex; gap:14px; align-items:center; margin-top:8px; flex-wrap:wrap; }}
.toggle {{ font:600 12px "IBM Plex Sans Condensed", sans-serif; text-transform:uppercase; letter-spacing:.12em; background:var(--truth);
  color:white; border:0; padding:7px 12px; cursor:pointer; }}
.toggle.on {{ background:var(--ink); }}
.ex-side {{ padding:16px 18px; }}
.q {{ font-size:15.5px; margin-top:0; }}
.replies {{ display:grid; gap:8px; margin:14px 0; }}
.reply {{ display:grid; grid-template-columns:150px 1fr auto; align-items:center; gap:10px; padding:8px 10px; border-left:5px solid; background:var(--paper); }}
.reply .cap {{ font-size:12px; }}
.reply .big {{ font-size:18px; font-weight:600; }}
.reply .mark {{ font:12px "IBM Plex Mono", monospace; }}
.reply.truth {{ border-color:var(--truth); }} .reply.truth .big {{ color:var(--truth); }}
.reply.bad {{ border-color:var(--model); }} .reply.bad .big, .reply.bad .mark {{ color:var(--model); }}
.reply.ok {{ border-color:var(--ink-2); }}
details summary {{ cursor:pointer; font-size:14px; }}
ul.honest li {{ margin:6px 0; max-width:900px; }}
pre.cmd {{ background:var(--night); color:#e9e3d0; padding:16px 18px; overflow:auto; font:13.5px/1.6 "IBM Plex Mono", monospace; }}
pre.cmd .c {{ color:#9aa39a; }}
footer {{ padding:28px 0 60px; font-size:13px; color:var(--ink-2); }}
#tip {{ position:fixed; pointer-events:none; background:var(--ink); color:var(--paper); font:13px "IBM Plex Mono", monospace;
  padding:5px 9px; opacity:0; transition:opacity .12s; z-index:10; }}
@media (max-width:900px) {{ .two, .ex-grid, ol.stages {{ grid-template-columns:1fr; }} .stats {{ grid-template-columns:1fr 1fr; }}
  .f-row {{ grid-template-columns:150px 1fr 50px; }} .f-note {{ display:none; }} header.hero h1 {{ font-size:36px; }} }}
</style></head>
<body>
<div id="tip"></div>
<div class="wrap">
<div class="collar"><span class="cap">Innodata hackathon · Track 2 · Visual Task Factory</span>
<span class="mono muted">built from commit {commit} ({commit_time}) · every number read from results/ and tasks/</span></div>

<header class="hero">
  <h1>A factory for questions<br>AI can't see through</h1>
  <p class="lede">We turn real data into realistic images, ask a question that takes several steps of reasoning,
  compute the answer from the data in code, check every task automatically, and evaluate Claude Haiku 5.5 and GPT-6 Luna, the two models the organizers set, on it.</p>
  <div class="stats">
    <div class="stat"><div class="n red">{fh}/{fn}</div><div class="l">Claude Haiku 5.5 right on our final {fn} tasks</div></div>
    <div class="stat"><div class="n red">{fl}/{fn}</div><div class="l">GPT-6 Luna right on the same final tasks</div></div>
    <div class="stat"><div class="n blue">{FINAL['val']['all_passed']}/{FINAL['val']['checked']}</div><div class="l">final tasks that passed all 7 automatic checks</div></div>
    <div class="stat"><div class="n">${cost:.2f}</div><div class="l">model cost for all {calls} calls on this page (final, pilots, few-shot test)</div></div>
  </div>
</header>

<section id="idea">
  <h2>The idea</h2><h3>Data first, picture second, answer from code</h3>
  <p class="beat">The model only sees the picture. We hold the data it was drawn from.</p>
  <div class="flowline"><span class="n">structured data</span><span class="a">→</span><span class="n">PNG drawn by code</span>
  <span class="a">→</span><span class="n">chained question</span><span class="a">→</span><span class="n">answer computed twice</span>
  <span class="a">→</span><span class="n">7 checks</span><span class="a">→</span><span class="n">Haiku + Luna</span>
  <span class="a">→</span><span class="n">results row</span></div>
  <p>No image is AI-generated and no answer comes from a person or a model reading the picture. Because the picture
  is rendered from the data, we know the right answer exactly, can prove the picture shows it (pixel probes), and can
  rebuild the same task byte for byte from its seed. The question is built to chain reasoning: read several things
  off the image, apply a textbook rule (Naismith's rule, water flows perpendicular to contours, a load needs a path of
  closed breakers), and combine them into one exact answer.</p>
</section>

<section id="pipeline">
  <h2>The factory</h2><h3>Eight stations, one command line</h3>
  <p class="beat">Each station either adds something or throws a task out, and says why.</p>
  <ol class="stages">{stage_html}</ol>
</section>

<section id="funnel">
  <h2>Quality gates</h2><h3>What survived each check</h3>
  <p class="beat">The final set plus all {len(SETS)} pilot sets ({len(topo)} topo, {len(power)} power), counted from the validator's own reports.</p>
  {funnel_html}
  <p class="muted" style="margin-top:14px">Draws that break a fairness rule (labels overlapping, solvers disagreeing,
  a trail running along a contour) are thrown away inside the generator before a task is written, so they don't show
  up as rejected seeds here.</p>
</section>

<section id="final">
  <h2>Final results</h2><h3>The final {fn}: Haiku {fh}/{fn}, Luna {fl}/{fn}</h3>
  <p class="beat">Fresh seeds ({min(t['seed'] for t in FINAL['task_list'])} and up, never used in a pilot), every one through all 7 checks, then both models once.</p>
  {bar_chart(final_sets, "Final set: correct answers per mission for Haiku and Luna", rule=False)}
  {final_table()}
  <p>On the trail missions both models <strong>undercount crossings</strong> (where both missed: {cross_facts}). On the
  floods, {flood_decoy} of {flood_miss} wrong answers name a <strong>planted decoy</strong> (the camp nearest the dam or
  the dry camp most directly below it). Every reply finished normally
  ({'none cut off' if FINAL['complete'] else 'SOME INCOMPLETE'}); the run cost ${FINAL['cfg']['totals']['cost_usd_all_calls']:.4f}
  for {FINAL['cfg']['totals']['calls']} calls.
  <strong>Hand check:</strong> {hc_fair} of {hc_total} final tasks judged visible, unique and fair in
  <code>results/human/hand_check.md</code> (pre-checked by an agent against the overlays; confirmed by eye: {hc_confirmed} of {hc_total} so far).</p>
</section>

<section id="fewshot">
  <h2>Can prompting fix it?</h2><h3>Two worked examples didn't help</h3>
  <p class="beat">If showing the model our step-by-step solutions fixed it, nobody would need the data.</p>
  {fewshot_table()}
  <p>Per mission, seeds 0 and 1 of the pilot were the worked examples and seeds 2 to 9 the test tasks, with the same
  eval settings ({fs_cfg['totals']['calls']} calls, ${fs_cfg['totals']['cost_usd_all_calls']:.4f}). Luna copied the
  examples' answers; Haiku copied the solution layout and still estimated. With 8 tasks per cell this rules out a big
  effect, not a small one (<code>results/extra/fewshot/summary.md</code>).</p>
</section>

<section id="results">
  <h2>Pilots</h2><h3>How we chose which missions to keep</h3>
  <p class="beat">10 seeds per mission on both models. A mission stays only if it stays hard.</p>
  {bar_chart(topo, "Topo pilot: correct answers out of 10 per template for Haiku and Luna")}
  <h3 style="margin-top:40px">Power diagrams: hard in the spike, too easy once the wording was fair</h3>
  <p>The single-line diagram family scored {ph}/{pn} (Haiku) and {pl}/{pn} (Luna) on its current pilot. With
  ambiguous wording removed, both models trace these diagrams well, so no power template meets the keep rule yet.
  We report it anyway: it shows the rule working.</p>
  {bar_chart(power, "Power pilot: correct answers out of 10 per template for Haiku and Luna")}
  <p><button class="toggle-table" onclick="document.getElementById('tbl').hidden=!document.getElementById('tbl').hidden">Show / hide the table</button></p>
  <div id="tbl" hidden>{table(SETS)}</div>
</section>

<section id="examples">
  <h2>Look inside</h2><h3>Final tasks, real misses</h3>
  <p class="beat">This is what the AI sees. Press "Show the truth overlay" to see what the code knows.</p>
  {''.join(example_html(e, i) for i, e in enumerate(examples))}
</section>

<section id="why">
  <h2>How we got here</h2><h3>Seven families tried, two picked</h3>
  <p class="beat">We tested families cheaply first and kept the ones where accuracy actually drops.</p>
  <table class="spikes"><tr><th>Family / question</th><th>Haiku · Luna</th><th>Verdict</th></tr>{spike_html}</table>
  <p><strong>The finding:</strong> these models read labels, do arithmetic and follow rule chains on clean layouts. They break
  when they have to <em>trace a path through clutter</em>: counting contours along a winding trail, following water
  around a bend, telling a crossing from a junction. That became our difficulty knob.</p>
</section>

<section id="trust">
  <h2>Why you can trust the numbers</h2><h3>Proof over claims</h3>
  <div class="two">
  <ul class="honest">
    <li><strong>Two solvers.</strong> Every answer is computed twice, by different code; a disagreement discards the task.</li>
    <li><strong>Pixels match data.</strong> Probes check that the picture shows what the data says (a contour's colour, a breaker's symbol).</li>
    <li><strong>Byte-identical rebuilds.</strong> Same seed, same PNG and data, checked by SHA-256.</li>
    <li><strong>One fixed eval.</strong> Temperature 0, reasoning effort high, max 64,000 tokens, identical prompt for both models,
      replies cached and logged raw. {'Every reply in the final run and the pilots finished normally (none cut off).' if all_complete else 'Some replies did not finish normally; see responses.csv.'}</li>
  </ul>
  <ul class="honest">
    <li><strong>Where it's weak (said out loud).</strong> The final set is {fn} tasks and pilots are 10 seeds per template: enough to show the gap, not for tight error bars. Topo uses four real places, so hills repeat.
      Flood has 6 camps, so guessing gets about 1 in 6.</li>
    <li><strong>Sunset.</strong> On real slopes most trails climb one way, so the uphill count often equals the total count.</li>
    <li><strong>Fairness.</strong> Hand check: {hc_fair} of {hc_total} final tasks judged fair, {hc_confirmed} confirmed by eye so far. {'A timed human baseline is in <code>results/human/baseline.csv</code>.' if has_baseline else 'The timed human baseline is not in the repo yet.'}</li>
    <li><strong>Power.</strong> Not yet hard enough to keep; we show it as a negative result.</li>
  </ul></div>
</section>

<section id="run">
  <h2>Run it yourself</h2><h3>One command per station</h3>
<pre class="cmd"><span class="c"># build 10 tasks from seeds 0-9, check them, score both models</span>
uv run python -m factory generate --family topo --template crossings --difficulty 3 --seeds 0-9 --out tasks/pilot_topo_crossings
uv run python -m factory validate --tasks tasks/pilot_topo_crossings
uv run python -m factory eval     --tasks tasks/pilot_topo_crossings --out results/pilot_topo_crossings
<span class="c"># judges: regenerate every task from its seed and compare bytes</span>
uv run python -m factory rebuild  --tasks tasks/pilot_topo_crossings
<span class="c"># live demo: a judge picks a seed; build, check and score one fresh task</span>
uv run python -m factory fresh    --seed 7 --show</pre>
</section>

<footer>Generated by <code>explainer/build.py</code> from commit {commit}. Sources:
{', '.join(f'<code>{s["results"]}/</code>' for s in SETS)}, <code>results/spikes/README.md</code>. results/final/, results/extra/fewshot/, results/human/hand_check.md.</footer>
</div>
<script>
const tip = document.getElementById('tip');
document.querySelectorAll('[data-tip]').forEach(el => {{
  el.addEventListener('mousemove', e => {{ tip.textContent = el.dataset.tip; tip.style.opacity = 1;
    tip.style.left = (e.clientX + 14) + 'px'; tip.style.top = (e.clientY + 14) + 'px'; }});
  el.addEventListener('mouseleave', () => tip.style.opacity = 0);
}});
document.querySelectorAll('.toggle').forEach(b => b.addEventListener('click', () => {{
  const img = document.getElementById(b.dataset.target); const on = b.classList.toggle('on');
  img.src = on ? b.dataset.b : b.dataset.a; b.textContent = on ? 'Show what the AI sees' : 'Show the truth overlay';
}}));
</script>
</body></html>"""

(HERE / "index.html").write_text(page, encoding="utf-8")
print("wrote", HERE / "index.html")
for s in SETS:
    print(f"  {s['family']}.{s['template']} {s['version']}: Haiku {s['score'][HAIKU]}/{s['n'][HAIKU]} "
          f"Luna {s['score'][LUNA]}/{s['n'][LUNA]} complete={s['complete']} keep={s['keep']}")
print("  funnel:", attempted, generated, funnel, all_passed, evaluated, kept_templates, f"cost ${cost:.4f}")
