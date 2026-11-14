"""Spike E (#16): Gantt-chart tasks, 3 levels x 3 seeds. Data first -> render PNG -> answer from data by code.

    uv run python results/spikes/gantt/gen.py

Writes results/spikes/gantt/tasks/{tasks.jsonl, data/, images/} in the contracts/SCHEMA.md format.

Scheduling rule (stated in every question): durations are in working days (Mon-Fri, minus the shaded
company holiday), every link is finish-to-start, and a task starts on the first working day after all of
its predecessors finish. Answers come from a CPM forward/backward pass; a brute-force check (re-run the
schedule with one task 1 day longer) independently confirms every zero-slack answer.
"""
from __future__ import annotations

import datetime as dt
import json
import random
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

VERSION = "gantt-spike-0.1.0"
OUT = Path(__file__).resolve().parent / "tasks"
REFERENCES = ["Microsoft Project Gantt Chart view (task table + timescale, finish-to-start link lines)",
              "Smartsheet Gantt view with dependencies and non-working days shaded"]

PROJECT_START = dt.date(2026, 11, 16)                      # Monday
HOLIDAYS = {dt.date(2026, 11, 26), dt.date(2026, 11, 27),   # Thanksgiving + day after
            dt.date(2026, 12, 25), dt.date(2027, 1, 1)}
TIMELINE_START = dt.date(2026, 11, 15)                     # Sunday, like MS Project's default week

DOMAINS = [
    ("Office fit-out, 5th floor", "Fit-out schedule v3", [
        "Site survey", "Permit application", "Demolition", "Electrical rough-in", "Plumbing rough-in",
        "HVAC ductwork", "Framing", "Drywall", "Fire alarm install", "Ceiling grid", "Painting",
        "Flooring", "Lighting fixtures", "IT cabling", "Kitchenette install", "Furniture delivery",
        "Signage", "Fire inspection", "Deep clean", "Punch list"],
     ["Kickoff meeting", "Handover to tenant"], ["GC crew", "Electrician", "Plumber", "IT vendor", "Facilities"]),
    ("Customer portal relaunch", "Portal relaunch plan", [
        "Requirements sign-off", "UX wireframes", "Visual design", "API contract", "Auth service",
        "Billing integration", "Search index", "Front-end build", "Content migration", "Accessibility audit",
        "Load testing", "Security review", "Analytics tagging", "Help-center articles", "UAT round 1",
        "Bug-fix sprint", "UAT round 2", "Support training", "Marketing assets", "Data backfill"],
     ["Project kickoff", "Go-live"], ["Web team", "Platform", "QA", "Design", "Content"]),
    ("Warehouse WMS rollout", "WMS rollout baseline", [
        "Process mapping", "Vendor contract", "Server provisioning", "Barcode label design", "Scanner purchase",
        "Rack relabeling", "Data cleanup", "Item master import", "Interface to ERP", "Pick-path setup",
        "Printer setup", "Wi-Fi survey", "Access points install", "Super-user training", "Floor-staff training",
        "Mock go-live", "Cycle count", "Cutover plan", "Inventory freeze", "Parallel run"],
     ["Kickoff", "Go-live"], ["Ops", "IT", "Vendor", "Finance", "Training"]),
]

LEVELS = {
    "L1": dict(n=6, chains=2, cross=0.0, dur=(2, 6), table=("dur", "pred"), grouped=True, resources=False),
    "L2": dict(n=10, chains=2, cross=0.15, dur=(2, 7), table=("dur", "pred"), grouped=True, resources=True),
    "L3": dict(n=16, chains=3, cross=0.35, dur=(1, 8), table=(), grouped=False, resources=True),
}
RULE = ("Durations are in working days: Monday to Friday, except the shaded company holidays. Every link is "
        "finish-to-start, and a task starts on the first working day after all of its predecessors finish.")
DATE_FMT = "Answer with the date in the form Fri Mar 5."


# ------------------------------------------------------------------------------------------- calendar
def is_work(d: dt.date) -> bool:
    return d.weekday() < 5 and d not in HOLIDAYS


def workday(i: int) -> dt.date:
    """The i-th working day of the project (0 = PROJECT_START)."""
    d, k = PROJECT_START, 0
    while True:
        if is_work(d):
            if k == i:
                return d
            k += 1
        d += dt.timedelta(days=1)


def fmt(d: dt.date) -> str:
    return f"{d:%a} {d:%b} {d.day}"


# ------------------------------------------------------------------------------------------- scheduling
def schedule(tasks: list[dict], extra: dict[int, int] | None = None):
    """CPM forward pass in working-day indices. extra = {task id: added days}. Returns (ES, EF, finish)."""
    extra = extra or {}
    es, ef = {}, {}
    for t in topo(tasks):
        es[t["id"]] = max((ef[p] + 1 for p in t["pred"]), default=0)
        ef[t["id"]] = es[t["id"]] + t["dur"] + extra.get(t["id"], 0) - 1
    return es, ef, max(ef.values())


def slack(tasks: list[dict]) -> dict[int, int]:
    es, ef, fin = schedule(tasks)
    succ = {t["id"]: [u["id"] for u in tasks if t["id"] in u["pred"]] for t in tasks}
    ls = {}
    for t in reversed(topo(tasks)):
        lf = min((ls[s] - 1 for s in succ[t["id"]]), default=fin)
        ls[t["id"]] = lf - t["dur"] + 1
    return {i: ls[i] - es[i] for i in es}


def topo(tasks: list[dict]) -> list[dict]:
    done, order, by_id = set(), [], {t["id"]: t for t in tasks}
    while len(order) < len(tasks):
        for t in tasks:
            if t["id"] not in done and all(p in done for p in t["pred"]):
                done.add(t["id"])
                order.append(t)
    return order


# ------------------------------------------------------------------------------------------- generation
def build_plan(level: str, rng: random.Random) -> dict:
    cfg = LEVELS[level]
    project, file_title, pool, ends, resources = rng.choice(DOMAINS)
    n_mid = cfg["n"] - 2
    names = rng.sample(pool, n_mid)
    # generation order: 0 = start, 1..n_mid = middle tasks, n_mid+1 = finish task
    chain_of, chain_last, preds = {}, {}, {0: []}
    for g in range(1, n_mid + 1):
        c = rng.randrange(cfg["chains"]) if g > cfg["chains"] else g - 1
        chain_of[g] = c
        p = {chain_last.get(c, 0)}
        others = [h for h in range(1, g) if chain_of[h] != c]
        if others and rng.random() < cfg["cross"]:
            p.add(rng.choice(others))
        preds[g] = sorted(p)
        chain_last[c] = g
    fin_g = n_mid + 1
    preds[fin_g] = sorted(set(chain_last.values()))
    # display order (IDs): grouped by chain for L1/L2 like a WBS, interleaved for L3
    mids = list(range(1, n_mid + 1))
    if cfg["grouped"]:
        mids.sort(key=lambda g: (chain_of[g], g))
    order = [0] + mids + [fin_g]
    gid = {g: i + 1 for i, g in enumerate(order)}
    tasks = []
    for g in order:
        name = ends[0] if g == 0 else ends[1] if g == fin_g else ""
        dur = 1 if g in (0, fin_g) else rng.randint(*cfg["dur"])
        tasks.append({"id": gid[g], "name": name, "dur": dur, "pred": sorted(gid[p] for p in preds[g]),
                      "resource": "" if g in (0, fin_g) else rng.choice(resources)})
    # realism: the pool lists work in a plausible real-world order, so name tasks in order of their start
    es, _, _ = schedule(tasks)
    unnamed = sorted((t for t in tasks if not t["name"]), key=lambda t: (es[t["id"]], t["id"]))
    for t, name in zip(unnamed, sorted(names, key=pool.index)):
        t["name"] = name
    return {"project": project, "file_title": file_title, "tasks": tasks}


def make_question(level: str, idx: int, plan: dict, rng: random.Random):
    """Pick a question for this level/seed slot. Returns None if this plan has no suitable trap (resample)."""
    tasks = plan["tasks"]
    _, _, fin = schedule(tasks)
    sl = slack(tasks)
    mids = [t for t in tasks if t["id"] not in (1, len(tasks))]
    if level == "L1":
        return dict(qtype="gantt.finish_date", answer=fmt(workday(fin)), answer_type="label",
                    question=f"{RULE} On what date does the last task of this project finish? {DATE_FMT}")
    if level == "L2":
        n = rng.randint(2, 4)
        want = [lambda s: s == 0, lambda s: 0 < s < n, lambda s: s >= n][idx]
        cands = [t for t in mids if want(sl[t["id"]])]
        if not cands:
            return None
        k = rng.choice(cands)
        _, _, fin2 = schedule(tasks, {k["id"]: n})
        return dict(qtype="gantt.slip_finish", answer=fmt(workday(fin2)), answer_type="label",
                    meta={"slipped": {k["id"]: n}, "slack_of_slipped": sl[k["id"]]},
                    question=(f"{RULE} Suppose task {k['id']} ({k['name']}) takes {n} more working days than "
                              f"planned and nothing else changes. On what date does the project now finish? "
                              f"{DATE_FMT}"))
    if idx == 1:                                       # L3, two slips
        a, b = rng.sample(mids, 2)
        na, nb = rng.randint(2, 4), rng.randint(2, 4)
        _, _, fin2 = schedule(tasks, {a["id"]: na, b["id"]: nb})
        if fin2 in (fin, fin + na + nb):               # want something smarter than "no change" or "add both"
            return None
        return dict(qtype="gantt.two_slip_finish", answer=fmt(workday(fin2)), answer_type="label",
                    meta={"slipped": {a["id"]: na, b["id"]: nb}},
                    question=(f"{RULE} Suppose task {a['id']} ({a['name']}) takes {na} more working days and "
                              f"task {b['id']} ({b['name']}) takes {nb} more working days than shown, and nothing "
                              f"else changes. On what date does the project now finish? {DATE_FMT}"))
    zero = sorted(i for i, s in sl.items() if s == 0)
    if not any(sl[t["id"]] == 1 for t in mids):        # need a near-critical trap
        return None
    brute = sorted(t["id"] for t in tasks if schedule(tasks, {t["id"]: 1})[2] > fin)
    assert brute == zero, (brute, zero)               # independent check of the zero-slack answer
    return dict(qtype="gantt.zero_slack", answer=[str(i) for i in zero], answer_type="sequence", ordered=False,
                question=(f"{RULE} Which tasks have zero total slack, meaning any delay to them delays the "
                          f"project finish? List their IDs in increasing order, separated by commas."))


# ------------------------------------------------------------------------------------------- rendering
def render(plan: dict, level: str, path: Path) -> None:
    cfg = LEVELS[level]
    tasks = plan["tasks"]
    es, ef, fin = schedule(tasks)
    last = workday(fin) + dt.timedelta(days=4)
    n_days = (last - TIMELINE_START).days + 1
    n_days += (7 - n_days % 7) % 7                     # end on a Saturday
    cols = [("ID", 34), ("Task Name", 190)]
    if "dur" in cfg["table"]:
        cols.append(("Duration", 70))
    if "pred" in cfg["table"]:
        cols.append(("Predecessors", 92))
    table_w = sum(w for _, w in cols)
    dw, rh, top, head = 22, 26, 58, 44
    gx = table_w + 14
    W = gx + n_days * dw + 110
    H = top + head + rh * len(tasks) + 30
    fig = plt.figure(figsize=(W / 100, H / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    ink, grid = "#262626", "#C8C8C8"
    ax.text(10, 20, f"{plan['file_title']}.mpp  ·  {plan['project']}", fontsize=12, weight="bold", color=ink,
            va="center")
    ax.text(10, 42, f"Project start: Mon 11/16/26   ·   Shaded columns = non-working time (weekends; "
                    f"company holidays Thu 11/26, Fri 11/27, Fri 12/25, Fri 1/1)", fontsize=9, color="#555555", va="center")
    y0 = top + head
    # table
    ax.add_patch(Rectangle((0, top), table_w, head, facecolor="#E9EEF5", edgecolor=grid, lw=0.8))
    x = 0
    for name, w in cols:
        ax.text(x + 6, top + head / 2, name, fontsize=9, weight="bold", color=ink, va="center")
        ax.plot([x, x], [top, y0 + rh * len(tasks)], color=grid, lw=0.8)
        x += w
    ax.plot([table_w, table_w], [top, y0 + rh * len(tasks)], color=grid, lw=0.8)
    for r, t in enumerate(tasks):
        yc = y0 + r * rh + rh / 2
        ax.plot([0, table_w], [y0 + (r + 1) * rh] * 2, color="#E3E3E3", lw=0.6)
        vals = [str(t["id"]), t["name"]]
        if "dur" in cfg["table"]:
            vals.append(f"{t['dur']} day{'s' if t['dur'] > 1 else ''}")
        if "pred" in cfg["table"]:
            vals.append(",".join(map(str, t["pred"])))
        x = 0
        for (cname, w), v in zip(cols, vals):
            ax.text(x + (w - 6 if cname == "ID" else 6), yc, v, fontsize=9, color=ink, va="center",
                    ha="right" if cname == "ID" else "left")
            x += w
    # timescale header: weeks (Sunday dates) and day letters
    for i in range(n_days):
        d = TIMELINE_START + dt.timedelta(days=i)
        cx = gx + i * dw
        if not is_work(d):
            ax.add_patch(Rectangle((cx, y0), dw, rh * len(tasks), facecolor="#E6E6E6", edgecolor="none"))
        ax.plot([cx, cx], [y0, y0 + rh * len(tasks)], color="#EDEDED", lw=0.5)
        ax.text(cx + dw / 2, top + 33, "SMTWTFS"[(d.weekday() + 1) % 7], fontsize=8, color=ink, ha="center",
                va="center")
        if d.weekday() == 6:
            ax.add_patch(Rectangle((cx, top), 7 * dw, 22, facecolor="#E9EEF5", edgecolor=grid, lw=0.8))
            ax.text(cx + 5, top + 11, f"{d:%b} {d.day}, '{d:%y}", fontsize=8.5, color=ink, va="center")
    ax.add_patch(Rectangle((gx, top + 22), n_days * dw, head - 22, facecolor="none", edgecolor=grid, lw=0.8))
    ax.plot([gx, gx + n_days * dw], [y0 + rh * len(tasks)] * 2, color=grid, lw=0.8)

    def xs(d):
        return gx + (d - TIMELINE_START).days * dw

    bar = {}
    for r, t in enumerate(tasks):
        x0, x1 = xs(workday(es[t["id"]])), xs(workday(ef[t["id"]])) + dw
        yc = y0 + r * rh + rh / 2
        bar[t["id"]] = (x0, x1, yc)
        ax.add_patch(Rectangle((x0, yc - 6), x1 - x0, 12, facecolor="#8DB4E2", edgecolor="#3D6AA2", lw=0.9,
                               zorder=3))
        if cfg["resources"] and t["resource"]:
            ax.text(x1 + 0.4 * dw + 16, yc, t["resource"], fontsize=7.5, color="#555555", va="center", zorder=4)
    # finish-to-start link lines
    link = "#1F3A64"
    for t in tasks:
        sx0, _, sy = bar[t["id"]]
        for p in t["pred"]:
            _, px1, py = bar[p]
            cx = px1 + 4 + 5 * (p % 3)          # stagger so links from tasks ending the same day don't overlap
            down = 1 if sy > py else -1
            if sx0 > cx + 2:
                ax.plot([px1, cx, cx, sx0 - 1], [py, py, sy, sy], color=link, lw=0.8, zorder=2)
                ax.annotate("", xy=(sx0, sy), xytext=(sx0 - 6, sy), zorder=5,
                            arrowprops=dict(arrowstyle="-|>", color=link, lw=0.8, mutation_scale=7,
                                            shrinkA=0, shrinkB=0))
            else:
                end_y = sy - 6 * down
                ax.plot([px1, cx, cx], [py, py, end_y - 5 * down], color=link, lw=0.8, zorder=2)
                ax.annotate("", xy=(cx, end_y), xytext=(cx, end_y - 6 * down), zorder=5,
                            arrowprops=dict(arrowstyle="-|>", color=link, lw=0.8, mutation_scale=7,
                                            shrinkA=0, shrinkB=0))
    fig.savefig(path, dpi=100, facecolor="white", metadata={"Software": None})
    plt.close(fig)


# ------------------------------------------------------------------------------------------- main
def main() -> None:
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    (OUT / "images").mkdir(parents=True, exist_ok=True)
    lines = []
    for li, level in enumerate(LEVELS):
        for idx in range(3):
            seed = (li + 1) * 100 + idx + 1
            rng = random.Random(seed)
            while True:
                plan = build_plan(level, rng)
                q = make_question(level, idx, plan, rng)
                if q:
                    break
            tid = f"gantt-{seed:06d}"
            data = {"task_id": tid, "family": "gantt", "seed": seed, "generator_version": VERSION,
                    "params": {"level": level, **{k: v for k, v in LEVELS[level].items() if k != "table"},
                               "table_columns": list(LEVELS[level]["table"])},
                    "data": {**plan, "project_start": str(PROJECT_START),
                             "holidays": sorted(map(str, HOLIDAYS)), "question_meta": q.get("meta", {})},
                    "references": REFERENCES}
            (OUT / "data" / f"{tid}.json").write_text(json.dumps(data, indent=1))
            render(plan, level, OUT / "images" / f"{tid}.png")
            task = {"task_id": tid, "image": f"images/{tid}.png", "question": q["question"],
                    "answer": q["answer"], "answer_type": q["answer_type"], "seed": seed,
                    "generator_version": VERSION, "question_type": q["qtype"], "family": "gantt",
                    "difficulty": level, "data": f"data/{tid}.json", "references": REFERENCES}
            if "ordered" in q:
                task["ordered"] = q["ordered"]
            lines.append(json.dumps(task))
            print(tid, level, q["qtype"], q["answer"], q.get("meta", ""))
    (OUT / "tasks.jsonl").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
