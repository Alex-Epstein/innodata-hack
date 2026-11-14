"""Spike C (#5): power single-line diagram, breaker-trip questions.

    uv run python results/spikes/power/gen.py

Data first: a random main-tie-main (secondary-selective) distribution system is built as a tree
(sources -> main breakers -> 13.8 kV buses -> feeder breakers -> transformers -> 480 V MCCs ->
load / panel breakers -> loads), plus normally-open ties. The PNG is drawn from that data, and the
answer is computed from the same data twice: (1) breadth-first reachability from the sources over
closed switches, (2) an independent rule walk down the tree (bus live? -> feeder closed? ...).

Levels
  L1  one source, radial, one breaker trips -> which loads lose power (list)
  L2  two sources, N.O. main tie + N.O. MCC tie, feeders that cross to the far side,
      two breakers trip -> which loads lose power (list)
  L3  same system; a main breaker and one more breaker trip, the operator closes the MCC tie
      -> total kW left without power (integer). Chain: find dead bus -> trace which MCCs it fed
      (crossing feeders) -> apply the tie -> apply the second trip -> add the kW labels.
"""
from __future__ import annotations

import json
import random
import textwrap
from itertools import combinations
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Circle, Polygon, Rectangle  # noqa: E402
from collections import defaultdict, deque  # noqa: E402

HERE = Path(__file__).resolve().parent
OUT = HERE / "tasks"
VERSION = "power-spike-0.1"
SEEDS = {1: [101, 102, 103], 2: [201, 202, 203], 3: [301, 302, 303]}

LOAD_NAMES = ["Pump House 1", "Pump House 2", "Raw Water Intake", "Clarifier Drive 1", "Clarifier Drive 2",
              "Aeration Blower 3", "Aeration Blower 4", "Chlorine Feed", "UV Disinfection", "Sludge Press",
              "Lab Building", "Admin Building", "Lighting Panel LP-2", "Chiller 1", "Chiller 2", "Fire Pump",
              "Filter Gallery", "Backwash Pump", "Maintenance Shop", "Control Room", "Grit Removal",
              "Lift Station 3", "Odor Control", "Boiler Room", "Air Compressor 2", "Elevator 2",
              "Security Gate", "Fuel Oil Pump", "Heat Trace", "Sump Pump 4"]
KW = [15, 20, 25, 30, 40, 50, 60, 75, 100, 125, 150, 200]
SITES = ["Northgate Water Treatment Plant", "Cedar Falls Wastewater Facility", "Riverside Hospital Central Plant",
         "Mesa Ridge Industrial Park", "Harbor Point Pumping Station", "Lakeview Campus Utility Building"]
KVA = [500, 750, 1000, 1500]
REFERENCES = ["IEEE Std 141 (Red Book): secondary-selective (main-tie-main) distribution systems",
              "IEEE Std 315 / ANSI Y32.2 graphic symbols for single-line diagrams",
              "IEEE C37.2 device function numbers (52 = AC circuit breaker)"]

SLOT = 1.35        # horizontal space per load
GAP = 1.6          # extra space (in slots) between the two crossing MCCs, where the ties sit


# ============================================================================================ data
def build(level: int, rng: random.Random) -> dict:
    names = rng.sample(LOAD_NAMES, len(LOAD_NAMES))
    cb = iter(range(1, 200))
    mcc_no = iter(range(1, 20))
    pnl_no = iter(range(1, 20))
    t_no = iter(range(1, 20))

    def load():
        return {"type": "load", "name": names.pop(), "kw": rng.choice(KW)}

    def feeder(side, cross=False, n_children=None):
        children = []
        n = n_children or rng.choice([2, 3])
        has_panel = rng.random() < 0.6
        for i in range(n):
            if has_panel and i == n - 1:
                children.append({"type": "panel", "name": f"PNL-{next(pnl_no)}",
                                 "children": [load() for _ in range(rng.choice([2, 2, 3]))]})
            else:
                children.append(load())
        return {"side": side, "cross": cross, "mcc": f"MCC-{next(mcc_no)}",
                "xfmr": {"name": f"T-{next(t_no)}", "kva": rng.choice(KVA)}, "children": children}

    if level == 1:
        sides = [{"name": "A", "source": {"kind": "utility", "label": "UTILITY SERVICE\n13.8 kV, 3φ, 60 Hz"},
                  "feeders": [feeder("A") for _ in range(3)]}]
    else:
        src_b = rng.choice([{"kind": "utility", "label": "UTILITY FEED 2\n13.8 kV, 3φ, 60 Hz"},
                            {"kind": "generator", "label": "GEN-1\n2000 kW, 13.8 kV"}])
        n_norm = 2
        sides = [{"name": "A", "source": {"kind": "utility", "label": "UTILITY FEED 1\n13.8 kV, 3φ, 60 Hz"},
                  "feeders": [feeder("A") for _ in range(n_norm)] + [feeder("A", cross=True, n_children=2)]},
                 {"name": "B", "source": src_b,
                  "feeders": [feeder("B", cross=True, n_children=2)] + [feeder("B") for _ in range(n_norm)]}]
    # number breakers top-down, left to right (main breakers, feeders, then MCC level, then panels)
    for s in sides:
        s["main_cb"] = f"CB-{next(cb)}"
    for s in sides:
        for f in s["feeders"]:
            f["cb"] = f"CB-{next(cb)}"
    for s in sides:
        for f in s["feeders"]:
            for c in f["children"]:
                c["cb"] = f"CB-{next(cb)}"
    for s in sides:
        for f in s["feeders"]:
            for c in f["children"]:
                for ld in c.get("children", []):
                    ld["cb"] = f"CB-{next(cb)}"
    data = {"level": level, "site": rng.choice(SITES), "sides": sides, "ties": []}
    if level >= 2:
        fa = next(f for f in sides[0]["feeders"] if f["cross"])
        fb = next(f for f in sides[1]["feeders"] if f["cross"])
        data["ties"] = [{"cb": "CB-T1", "between": ["BUS A", "BUS B"], "normally": "open"},
                        {"cb": "CB-T2", "between": [fb["mcc"], fa["mcc"]], "normally": "open"}]
    return data


def all_loads(data):
    for s in data["sides"]:
        for f in s["feeders"]:
            for c in f["children"]:
                if c["type"] == "load":
                    yield c
                else:
                    yield from c["children"]


def edges(data) -> list[tuple[str, str, str | None]]:
    """(node, node, breaker or None). Nodes are sources, buses and loads; None = cable or transformer."""
    out = []
    for s in data["sides"]:
        src, bus = f"SRC {s['name']}", f"BUS {s['name']}"
        out.append((src, bus, s["main_cb"]))
        for f in s["feeders"]:
            hv = f"{f['mcc']} HV"                       # transformer primary
            out.append((bus, hv, f["cb"]))
            out.append((hv, f["mcc"], None))            # transformer: always conducts
            for c in f["children"]:
                out.append((f["mcc"], c["name"], c["cb"]))
                for ld in c.get("children", []):
                    out.append((c["name"], ld["name"], ld["cb"]))
    for t in data["ties"]:
        out.append((*t["between"], t["cb"]))
    return out


def dead_loads_graph(data, tripped: set, closed: set) -> list[str]:
    """Method 1: breadth-first reachability from the sources over conducting edges."""
    normally_open = {t["cb"] for t in data["ties"]}
    adj = defaultdict(list)
    for u, v, c in edges(data):
        if c is None or (c not in tripped and (c not in normally_open or c in closed)):
            adj[u].append(v)
            adj[v].append(u)
    energized = {f"SRC {s['name']}" for s in data["sides"]}
    queue = deque(energized)
    while queue:
        for v in adj[queue.popleft()]:
            if v not in energized:
                energized.add(v)
                queue.append(v)
    return [ld["name"] for ld in all_loads(data) if ld["name"] not in energized]


def dead_loads_rules(data, tripped: set, closed: set) -> list[str]:
    """Method 2 (independent): the operator's rule walk, bus by bus, no graph library."""
    def is_closed(c):
        if c in tripped:
            return False
        if c in ("CB-T1", "CB-T2"):
            return c in closed
        return True

    # fixed point: a bus or MCC is live if any closed path joins it to something live (back-feed included)
    feeders = [(s["name"], f) for s in data["sides"] for f in s["feeders"]]
    bus_live = {s["name"]: is_closed(s["main_cb"]) for s in data["sides"]}
    mcc_live = {f["mcc"]: False for _, f in feeders}
    changed = True
    while changed:
        changed = False
        for side, f in feeders:
            if is_closed(f["cb"]) and bus_live[side] != mcc_live[f["mcc"]]:
                bus_live[side] = mcc_live[f["mcc"]] = True
                changed = True
        if len(bus_live) == 2 and is_closed("CB-T1") and bus_live["A"] != bus_live["B"]:
            bus_live = {"A": True, "B": True}
            changed = True
        if data["ties"] and is_closed("CB-T2"):
            x, y = data["ties"][1]["between"]
            if mcc_live[x] != mcc_live[y]:
                mcc_live[x] = mcc_live[y] = True
                changed = True
    dead = set()
    for s in data["sides"]:
        for f in s["feeders"]:
            for c in f["children"]:
                up = mcc_live[f["mcc"]] and is_closed(c["cb"])
                for ld in ([c] if c["type"] == "load" else c["children"]):
                    if not (up and is_closed(ld["cb"])):
                        dead.add(ld["name"])
    return [ld["name"] for ld in all_loads(data) if ld["name"] in dead]


# ============================================================================================ scenario
def scenario(data, rng: random.Random) -> dict:
    level, sides = data["level"], data["sides"]
    feeders = [f for s in sides for f in s["feeders"]]
    feeder_cbs = [f["cb"] for f in feeders]
    panel_cbs = [c["cb"] for f in feeders for c in f["children"] if c["type"] == "panel"]
    kw = {ld["name"]: ld["kw"] for ld in all_loads(data)}
    if level == 1:
        trip = [rng.choice(feeder_cbs + panel_cbs)]
        return {"tripped": trip, "closed": []}
    if level == 2:
        for _ in range(500):
            a = rng.choice([f["cb"] for f in sides[0]["feeders"]] + panel_cbs)
            b = rng.choice([f["cb"] for f in sides[1]["feeders"]] + panel_cbs)
            if a == b:
                continue
            crossers = {f["cb"] for f in feeders if f["cross"]}
            if crossers & {a, b}:                       # the trap: one trip is a crossing feeder
                return {"tripped": [a, b], "closed": []}
        raise RuntimeError("no L2 scenario")
    # level 3: one main breaker trips, plus one more breaker; operator closes the MCC tie CB-T2
    for _ in range(2000):
        s = rng.choice(sides)
        s_cross = next(f["cb"] for f in s["feeders"] if f["cross"])
        second = rng.choice([c for c in feeder_cbs + panel_cbs if c != s_cross])
        tripped, closed = {s["main_cb"], second, s_cross}, {"CB-T2"}
        truth = dead_loads_graph(data, tripped, closed)
        no_tie = dead_loads_graph(data, tripped, set())
        # naive reading: everything drawn under the dead bus is dead (ignores where crossing feeders really go)
        x = layout(data)
        span = x["bus_span"][s["name"]]
        naive = [n for n, (lx, _) in x["load_xy"].items() if span[0] <= lx <= span[1]]
        naive = sorted(set(naive) | set(dead_loads_graph(data, {second}, set())))
        total = sum(kw[n] for n in truth)
        if (truth and set(truth) != set(no_tie) and set(naive) != set(truth)
                and total != sum(kw[n] for n in no_tie) and total != sum(kw[n] for n in naive)
                and second not in {f["cb"] for f in s["feeders"] if not f["cross"]}):
            return {"tripped": [s["main_cb"], second], "opened": [s_cross], "closed": ["CB-T2"],
                    "distractors": {"ignore_tie_kw": sum(kw[n] for n in no_tie),
                                    "by_position_kw": sum(kw[n] for n in naive)}}
    raise RuntimeError("no L3 scenario")


# ============================================================================================ layout
def layout(data) -> dict:
    """x positions of every load slot, MCC, feeder breaker, bus span and tie (pure geometry, no drawing)."""
    sides = data["sides"]
    if len(sides) == 1:
        order = sides[0]["feeders"]
    else:
        a_norm = [f for f in sides[0]["feeders"] if not f["cross"]]
        a_x = [f for f in sides[0]["feeders"] if f["cross"]]
        b_x = [f for f in sides[1]["feeders"] if f["cross"]]
        b_norm = [f for f in sides[1]["feeders"] if not f["cross"]]
        order = a_norm + b_x + ["GAP"] + a_x + b_norm   # B's crossing MCC sits under bus A, and vice versa
    x = 1.2
    load_xy, child_x, mcc_span, feeder_x, tie_x = {}, {}, {}, {}, None
    for f in order:
        if f == "GAP":
            tie_x = x - SLOT / 2 + GAP * SLOT / 2
            x += (GAP - 1) * SLOT
            continue
        xs = []
        for c in f["children"]:
            if c["type"] == "load":
                load_xy[c["name"]] = (x, 0)
                child_x[c["cb"]] = x
                xs.append(x)
                x += SLOT
            else:
                px = []
                for ld in c["children"]:
                    load_xy[ld["name"]] = (x, 1)
                    child_x[ld["cb"]] = x
                    px.append(x)
                    x += SLOT
                child_x[c["cb"]] = sum(px) / len(px)
                mcc_span[c["name"]] = (px[0] - 0.4, px[-1] + 0.4)
                xs.append(child_x[c["cb"]])
        mcc_span[f["mcc"]] = (min(xs) - 0.45, max(xs) + 0.45)
        feeder_x[f["cb"]] = (min(xs) + max(xs)) / 2
        x += 0.35 * SLOT                                      # small gap between MCCs
    width = x + 0.6
    bus_span = {}
    if len(sides) == 1:
        xs = [feeder_x[f["cb"]] for f in sides[0]["feeders"]]
        bus_span["A"] = (min(xs) - 0.6, max(xs) + 0.6)
    else:
        fa = next(f for f in sides[0]["feeders"] if f["cross"])
        fb = next(f for f in sides[1]["feeders"] if f["cross"])
        feeder_x[fa["cb"]] = tie_x - 0.85                     # breaker on bus A, MCC on the right
        feeder_x[fb["cb"]] = tie_x + 0.85                     # breaker on bus B, MCC on the left
        left = min(feeder_x[f["cb"]] for f in sides[0]["feeders"]) - 0.6
        right = max(feeder_x[f["cb"]] for f in sides[1]["feeders"]) + 0.6
        bus_span["A"] = (left, tie_x - 0.35)
        bus_span["B"] = (tie_x + 0.35, right)
    return {"load_xy": load_xy, "child_x": child_x, "mcc_span": mcc_span, "feeder_x": feeder_x,
            "bus_span": bus_span, "tie_x": tie_x, "width": width}


# ============================================================================================ drawing
Y = {"src": 12.0, "main_cb": 11.0, "bus": 10.2, "fcb": 9.4, "xf": 8.45, "chan_hi": 7.7, "chan_lo": 7.4,
     "mcc": 6.9, "ccb": 6.25, "pnl": 5.45, "pcb": 4.8, "arrow": 3.95, "label": 3.75}
LW, BUS_LW = 1.3, 4.0
INK = "#111111"


def draw(data, path: Path) -> list:
    L = layout(data)
    W = max(L["width"], 14.0)
    H = 14.2
    fig = plt.figure(figsize=(W * 0.62, H * 0.62), dpi=130)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")
    texts = []

    def line(x1, y1, x2, y2, lw=LW):
        ax.plot([x1, x2], [y1, y2], color=INK, lw=lw, solid_capstyle="butt", zorder=2)

    def text(x, y, s, **kw):
        kw.setdefault("fontsize", 7.2)
        kw.setdefault("color", INK)
        t = ax.text(x, y, s, zorder=5, **kw)
        texts.append(t)
        return t

    def breaker(x, y, name, closed=True, horizontal=False, label_side="right"):
        s = 0.24
        ax.add_patch(Rectangle((x - s / 2, y - s / 2), s, s, facecolor=INK if closed else "white",
                               edgecolor=INK, lw=1.4, zorder=4))
        lab = name + ("" if closed else "\nN.O.")
        if horizontal:
            text(x, y - 0.2, lab, ha="center", va="top", fontsize=7)
        elif label_side == "right":
            text(x + 0.2, y, lab, ha="left", va="center", fontsize=7)
        else:
            text(x - 0.2, y, lab, ha="right", va="center", fontsize=7)

    def xfmr(x, y, name, kva, hv="13.8 kV", lv="480 V"):
        for dy in (0.15, -0.15):
            ax.add_patch(Circle((x, y + dy), 0.22, facecolor="none", edgecolor=INK, lw=1.2, zorder=3))
        line(x, y + 0.37, x, y + 0.6)
        line(x, y - 0.37, x, y - 0.6)
        text(x + 0.3, y, f"{name}\n{kva} kVA\n{hv}–{lv}", ha="left", va="center", fontsize=6.4)

    def load(x, y_top, ld):
        line(x, y_top, x, Y["arrow"] + 0.2)
        ax.add_patch(Polygon([[x - 0.13, Y["arrow"] + 0.22], [x + 0.13, Y["arrow"] + 0.22], [x, Y["arrow"]]],
                             closed=True, facecolor=INK, edgecolor=INK, zorder=3))
        name = "\n".join(textwrap.wrap(ld["name"], 12, break_long_words=False))
        text(x, Y["label"], f"{name}\n{ld['kw']} kW", ha="center", va="top", fontsize=6.9, linespacing=1.15)

    sides = data["sides"]
    ties = {t["cb"]: t for t in data["ties"]}
    # sources, main breakers, buses
    for s in sides:
        b0, b1 = L["bus_span"][s["name"]]
        sx = (b0 + b1) / 2 if len(sides) == 1 else (b0 + 2.4 if s["name"] == "A" else b1 - 1.1)
        # keep the source drop away from feeder drops
        fx = [L["feeder_x"][f["cb"]] for f in s["feeders"]]
        while any(abs(sx - v) < 0.55 for v in fx):
            sx += 0.3 if s["name"] == "A" else -0.3
        if s["source"]["kind"] == "generator":
            ax.add_patch(Circle((sx, Y["src"] + 0.35), 0.34, facecolor="white", edgecolor=INK, lw=1.4, zorder=3))
            text(sx, Y["src"] + 0.35, "G", ha="center", va="center", fontsize=10, weight="bold")
            line(sx, Y["src"] + 0.01, sx, Y["main_cb"])
            text(sx + 0.45, Y["src"] + 0.35, s["source"]["label"], ha="left", va="center", fontsize=7)
        else:
            ax.add_patch(Polygon([[sx - 0.16, Y["src"] + 0.55], [sx + 0.16, Y["src"] + 0.55], [sx, Y["src"] + 0.25]],
                                 closed=True, facecolor=INK, zorder=3))
            line(sx, Y["src"] + 0.9, sx, Y["main_cb"])
            text(sx + 0.3, Y["src"] + 0.6, s["source"]["label"], ha="left", va="center", fontsize=7)
        line(sx, Y["main_cb"], sx, Y["bus"])
        breaker(sx, Y["main_cb"], s["main_cb"])
        line(b0, Y["bus"], b1, Y["bus"], lw=BUS_LW)
        text(b0, Y["bus"] + 0.22, f"BUS {s['name']}  13.8 kV", ha="left", va="bottom", fontsize=7.6, weight="bold")
        for f in s["feeders"]:
            fxx = L["feeder_x"][f["cb"]]
            m0, m1 = L["mcc_span"][f["mcc"]]
            mx = (m0 + m1) / 2
            line(fxx, Y["bus"], fxx, Y["xf"] + 0.6)
            breaker(fxx, Y["fcb"], f["cb"])
            xfmr(fxx, Y["xf"], f["xfmr"]["name"], f["xfmr"]["kva"])
            if abs(fxx - mx) < 1e-6:
                line(fxx, Y["xf"] - 0.6, fxx, Y["mcc"])
            else:                                        # crossing feeder: jog across to the far MCC
                cy = Y["chan_lo"] if s["name"] == "A" else Y["chan_hi"]
                line(fxx, Y["xf"] - 0.6, fxx, cy)
                line(fxx, cy, mx, cy)
                line(mx, cy, mx, Y["mcc"])
            line(m0, Y["mcc"], m1, Y["mcc"], lw=BUS_LW * 0.8)
            text(m0, Y["mcc"] + 0.14, f['mcc'], ha="left", va="bottom", fontsize=7, weight="bold")
            for c in f["children"]:
                cx = L["child_x"][c["cb"]]
                line(cx, Y["mcc"], cx, Y["ccb"])
                breaker(cx, Y["ccb"], c["cb"])
                if c["type"] == "load":
                    load(cx, Y["ccb"], c)
                else:
                    p0, p1 = L["mcc_span"][c["name"]]
                    line(cx, Y["ccb"], cx, Y["pnl"])
                    line(p0, Y["pnl"], p1, Y["pnl"], lw=BUS_LW * 0.6)
                    text(p0, Y["pnl"] + 0.1, f"{c['name']} 480 V", ha="left", va="bottom", fontsize=6.6)
                    for ld in c["children"]:
                        lx = L["child_x"][ld["cb"]]
                        line(lx, Y["pnl"], lx, Y["pcb"])
                        breaker(lx, Y["pcb"], ld["cb"])
                        load(lx, Y["pcb"], ld)
    # ties
    if "CB-T1" in ties:
        tx = L["tie_x"]
        line(L["bus_span"]["A"][1], Y["bus"], L["bus_span"]["B"][0], Y["bus"])
        breaker(tx, Y["bus"], "CB-T1", closed=False, horizontal=True)
    if "CB-T2" in ties:
        tx = L["tie_x"]
        left_mcc, right_mcc = ties["CB-T2"]["between"]
        line(L["mcc_span"][left_mcc][1], Y["mcc"], L["mcc_span"][right_mcc][0], Y["mcc"])
        breaker(tx, Y["mcc"], "CB-T2", closed=False, horizontal=True)
    # title block and legend
    text(0.4, H - 0.35, f"SINGLE-LINE DIAGRAM  ·  {data['site'].upper()}", ha="left", va="top",
         fontsize=10, weight="bold")
    text(0.4, H - 0.85, "13.8 kV / 480 V DISTRIBUTION  ·  DWG E-001  REV C  ·  NOT TO SCALE", ha="left",
         va="top", fontsize=7.2)
    lx, ly = W - 4.3, 2.3
    ax.add_patch(Rectangle((lx - 0.2, 0.1), 4.25, 2.65, facecolor="none", edgecolor=INK, lw=0.8))
    text(lx, ly + 0.25, "LEGEND", ha="left", va="center", fontsize=7.2, weight="bold")
    ax.add_patch(Rectangle((lx, ly - 0.42), 0.22, 0.22, facecolor=INK, edgecolor=INK))
    text(lx + 0.4, ly - 0.31, "Circuit breaker (52), closed", ha="left", va="center", fontsize=6.8)
    ax.add_patch(Rectangle((lx, ly - 0.87), 0.22, 0.22, facecolor="white", edgecolor=INK, lw=1.4))
    text(lx + 0.4, ly - 0.76, "Circuit breaker, normally open (N.O.)", ha="left", va="center", fontsize=6.8)
    for dy in (0.1, -0.1):
        ax.add_patch(Circle((lx + 0.11, ly - 1.22 + dy), 0.13, facecolor="none", edgecolor=INK, lw=1))
    text(lx + 0.4, ly - 1.22, "Transformer", ha="left", va="center", fontsize=6.8)
    ax.add_patch(Polygon([[lx, ly - 1.55], [lx + 0.22, ly - 1.55], [lx + 0.11, ly - 1.75]], closed=True,
                         facecolor=INK))
    text(lx + 0.4, ly - 1.65, "Load (demand in kW)", ha="left", va="center", fontsize=6.8)
    line(lx - 0.02, ly - 2.05, lx + 0.24, ly - 2.05, lw=1)
    line(lx + 0.11, ly - 1.92, lx + 0.11, ly - 2.18, lw=1)
    text(lx + 0.4, ly - 2.05, "Lines crossing without a dot are not connected", ha="left", va="center", fontsize=6.8)

    fig.canvas.draw()
    overlaps = _overlaps(fig, texts)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=130, facecolor="white", metadata={"Software": None})
    plt.close(fig)
    return overlaps


def _overlaps(fig, texts):
    r = fig.canvas.get_renderer()
    boxes = [(t.get_text().replace("\n", " "), t.get_window_extent(r)) for t in texts]
    return [(a, b) for (a, ba), (b, bb) in combinations(boxes, 2) if ba.overlaps(bb)]


# ============================================================================================ tasks
INTRO = ("This is a single-line diagram of an electrical distribution system. Filled breaker squares are "
         "closed; hollow squares are open (N.O. = normally open). Power flows through closed breakers, "
         "transformers and conductors in either direction, from the sources at the top. Ignore equipment ratings.")


def make_task(level: int, seed: int) -> dict:
    rng = random.Random(seed)
    data = build(level, rng)
    sc = scenario(data, rng)
    tripped, closed = set(sc["tripped"]) | set(sc.get("opened", [])), set(sc["closed"])
    d1 = dead_loads_graph(data, tripped, closed)
    d2 = dead_loads_rules(data, tripped, closed)
    kw = {ld["name"]: ld["kw"] for ld in all_loads(data)}
    tid = f"power-{seed:06d}"
    trips = " and ".join(sc["tripped"])
    if level in (1, 2):
        verb = "trips" if len(sc["tripped"]) == 1 else "trip"
        q = (f"{INTRO} Breaker{'s' if len(sc['tripped']) > 1 else ''} {trips} {verb} open; every other breaker "
             "stays as drawn. Which loads lose power? Answer with the load names exactly as written on the "
             "diagram, as a comma-separated list in any order.")
        answer, atype, qtype = d1, "sequence", f"power.loads_lost_{len(sc['tripped'])}trip"
    else:
        q = (f"{INTRO} Breakers {trips} trip open. The operator then opens breaker {sc['opened'][0]} and closes tie "
             "breaker CB-T2; every other "
             "breaker stays as drawn. What is the total load, in kW, that is left without power? Answer with "
             "a single integer number of kW.")
        answer, atype, qtype = sum(kw[n] for n in d1), "integer", "power.kw_unserved_after_tie"
    overlaps = draw(data, OUT / "images" / f"{tid}.png")
    record = {"data": data, "scenario": sc, "dead_loads": d1, "kw": kw}
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    (OUT / "data" / f"{tid}.json").write_text(json.dumps(record, indent=1, ensure_ascii=False), encoding="utf-8")
    task = {"task_id": tid, "image": f"images/{tid}.png", "question": q, "answer": answer, "answer_type": atype,
            "seed": seed, "generator_version": VERSION, "question_type": qtype, "family": "power",
            "difficulty": level, "data": f"data/{tid}.json",
            "checks": {"graph_and_rule_walk_agree": sorted(d1) == sorted(d2), "no_text_overlap": not overlaps,
                       "answer_nonempty": bool(d1)},
            "references": REFERENCES}
    if atype == "sequence":
        task["ordered"] = False
    if overlaps:
        print(f"  {tid}: text overlaps: {overlaps[:4]}")
    return task


def main():
    tasks = [make_task(lv, s) for lv in (1, 2, 3) for s in SEEDS[lv]]
    (OUT / "tasks.jsonl").write_text("".join(json.dumps(t, ensure_ascii=False) + "\n" for t in tasks),
                                     encoding="utf-8")
    for t in tasks:
        print(t["task_id"], t["question_type"], "answer:", t["answer"], "checks:", t["checks"])


if __name__ == "__main__":
    main()
