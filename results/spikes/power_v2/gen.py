"""Power one-line diagram spike v2: data -> PNG -> chained question, answers by graph reachability.

    uv run --directory /Users/alex/Desktop/innodata-hack python <work>/gen.py

Writes <work>/tasks/{tasks.jsonl, data/, images/}.
"""
from __future__ import annotations

import itertools
import json
import random
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Polygon, Rectangle

WORK = Path(__file__).resolve().parent
OUT = WORK / "tasks"
VERSION = "pwr-0.2.0"
REFERENCES = [
    "IEEE Std 141 (Red Book), secondary-selective / main-tie-main low-voltage switchgear single-line diagrams",
    "IEEE Std 315 / ANSI Y32.2 graphic symbols and ANSI/IEEE C37.2 device numbers (52 = AC circuit breaker)",
]

W, H = 1600, 1100
SLOT, GGAP, BUS_GAP, X0 = 90, 26, 74, 46
Y_BUS, Y_FBRK, Y_SUB, Y_LBRK, Y_LOAD, Y_TEE = 330, 392, 640, 702, 772, 622
CHANNELS = [452, 492, 532, 572]

# tag, name, motor?, kW choices
POOL = [
    ("CH-1", "CHILLER", True, range(300, 425, 5)), ("CH-2", "CHILLER", True, range(300, 425, 5)),
    ("CT-1", "CLG TOWER", True, range(55, 95, 5)), ("CHWP-1", "CHW PUMP", True, range(37, 60, 1)),
    ("DH-A", "DATA HALL A", False, range(380, 470, 5)), ("DH-B", "DATA HALL B", False, range(330, 420, 5)),
    ("UPS-1", "UPS MODULE", False, range(150, 260, 5)), ("AHU-3", "AIR HANDLER", True, range(45, 80, 1)),
    ("EL-1", "ELEVATOR", True, range(30, 52, 1)), ("LP-2", "LTG PANEL", False, range(25, 60, 1)),
    ("AC-1", "AIR COMPR", True, range(90, 135, 1)), ("KP-1", "KITCHEN PNL", False, range(65, 95, 1)),
    ("PP-2", "PROC PUMP", True, range(130, 165, 1)), ("EF-4", "EXHAUST FAN", True, range(15, 30, 1)),
    ("HP-2", "HEAT PUMP", True, range(60, 95, 1)), ("RP-3", "RECEPT PNL", False, range(40, 70, 1)),
    ("CRAH-4", "CRAH UNIT", True, range(22, 40, 1)), ("EV-1", "EV CHARGERS", False, range(120, 180, 1)),
    ("BP-1", "BOOST PUMP", True, range(18, 37, 1)), ("LAB-2", "LAB PANEL", False, range(70, 110, 1)),
]
LIFE = [("FP-1", "FIRE PUMP", True, range(75, 112, 1)), ("ELP-1", "EMERG LTG", False, range(20, 45, 1)),
        ("SF-2", "SMOKE FAN", True, range(30, 56, 1)), ("EL-2", "ELEVATOR", True, range(30, 52, 1))]


# ============================================================================== topology + geometry
class Diagram:
    def __init__(self, rng: random.Random, with_pv: bool):
        self.rng = rng
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.with_pv = with_pv
        self.build()

    # ---------------------------------------------------------------- build
    def node(self, nid, kind, **kw):
        self.nodes[nid] = {"id": nid, "kind": kind, **kw}

    def edge(self, eid, a, b, kind, pts, state="closed", label=None, brk=None, no=False, label_side="right", role=None):
        self.edges.append({"id": eid, "a": a, "b": b, "kind": kind, "state": state, "normally_open": no,
                           "label": label or eid, "pts": pts, "breaker_at": brk, "label_side": label_side,
                           "role": role})

    def build(self):
        rng = self.rng
        # ---- loads: per main bus, a list of groups
        pool = POOL[:]
        rng.shuffle(pool)
        life = LIFE[:]
        rng.shuffle(life)
        n1b = rng.choice([3, 4])
        n2b = 3 if self.with_pv else rng.choice([3, 4])
        neb = rng.choice([2, 3])
        groups = {
            "B1": [("sub", "B1B", n1b), ("direct", None, 1), ("pair", None, 2)],
            "B2": [("sub", "B2B", n2b), ("direct", None, 1)],
            "BE": [("sub", "BEB", neb), ("direct", None, 1)],
        }
        for b in ("B1", "B2"):
            rng.shuffle(groups[b])
        if rng.random() < 0.5:
            groups["BE"].reverse()
        total = sum(g[2] for b in groups.values() for g in b)
        while total > 14:   # keep the drawing readable
            if n1b == 4:
                n1b = 3
            elif neb == 3:
                neb = 2
            else:
                n2b = 3
            groups["B1"] = [(t, s, n1b if s == "B1B" else n) for t, s, n in groups["B1"]]
            groups["B2"] = [(t, s, n2b if s == "B2B" else n) for t, s, n in groups["B2"]]
            groups["BE"] = [(t, s, neb if s == "BEB" else n) for t, s, n in groups["BE"]]
            total = sum(g[2] for b in groups.values() for g in b)
        self.groups = groups

        used_kw = set()

        def make_load(spec, x):
            tag, name, motor, kws = spec
            kw = rng.choice([k for k in kws if k not in used_kw])
            used_kw.add(kw)
            nid = "L:" + tag
            self.node(nid, "load", tag=tag, name=name, motor=motor, kw=kw, x=x, y=Y_LOAD)
            return nid

        x = X0
        self.bus_span, self.sub_span, self.verticals = {}, {}, []   # verticals: (x, y0, y1, owner)
        feeders = []      # (bus, x, target kind, target)
        self.loads_order = []
        for bus in ("B1", "B2", "BE"):
            start = x
            for gi, (gtype, sub, n) in enumerate(groups[bus]):
                left = x
                xs = [left + SLOT / 2 + i * SLOT for i in range(n)]
                if gtype == "sub":
                    self.sub_span[sub] = (left + 8, left + n * SLOT - 8)
                    specs = [pool.pop() for _ in range(n)]
                    if sub == "B2B" and self.with_pv:
                        specs[-1] = None     # PV inverter goes in the last slot
                    ids = []
                    for xi, sp in zip(xs, specs):
                        if sp is None:
                            ids.append(("PV", xi))
                        else:
                            ids.append((make_load(sp, xi), xi))
                    feed_x = left + SLOT * rng.choice(range(1, n))      # between two loads
                    feeders.append((bus, feed_x, "sub", sub, ids))
                elif gtype == "direct":
                    sp = life.pop() if bus == "BE" else pool.pop()
                    nid = make_load(sp, xs[0])
                    feeders.append((bus, xs[0], "direct", nid, None))
                else:
                    a, b = make_load(pool.pop(), xs[0]), make_load(pool.pop(), xs[1])
                    feeders.append((bus, (xs[0] + xs[1]) / 2, "pair", None, [(a, xs[0]), (b, xs[1])]))
                x += n * SLOT + GGAP
            self.bus_span[bus] = (start + 4, x - GGAP - 4)
            x += BUS_GAP - GGAP
        self.right_edge = x - BUS_GAP + GGAP

        # ---- sources and mains
        bx = {b: (s + e) / 2 for b, (s, e) in self.bus_span.items()}
        self.node("U1", "utility", label="UTILITY SERVICE 1", kv="13.8 kV", x=bx["B1"] - 60, y=60)
        self.node("U2", "utility", label="UTILITY SERVICE 2", kv="13.8 kV", x=bx["B2"] + 40, y=60)
        gx = bx["BE"] + 40
        self.gen_kw = None   # set by the template
        self.node("G1", "generator", label="G1", x=gx, y=180)
        for b, lab in (("B1", "BUS 1  SWGR-1  480 V  3000 A"), ("B2", "BUS 2  SWGR-2  480 V  3000 A"),
                       ("BE", "BUS E  EMERG SWGR  480 V  1600 A")):
            self.node(b, "bus", label=lab, x0=self.bus_span[b][0], x1=self.bus_span[b][1], y=Y_BUS)
        for u, b, t, kva in (("U1", "B1", "T1", rng.choice([2000, 2500])), ("U2", "B2", "T2", rng.choice([1500, 2000]))):
            ux = self.nodes[u]["x"]
            self.node(t + "s", "point", x=ux, y=240)
            self.nodes[u]["xfmr"] = {"id": t, "kva": kva}
            self.edge(t, u, t + "s", "transformer", [(ux, 92), (ux, 240)], label=f"{t}")
            self.edge("52-M" + u[1], t + "s", b, "breaker", [(ux, 240), (ux, Y_BUS)], brk=(ux, 280))
        self.edge("52-G1", "G1", "BE", "breaker", [(gx, 208), (gx, Y_BUS)], brk=(gx, 275))
        # ties on the bus line
        tx = (self.bus_span["B1"][1] + self.bus_span["B2"][0]) / 2
        self.edge("52-T", "B1", "B2", "breaker", [(self.bus_span["B1"][1], Y_BUS), (self.bus_span["B2"][0], Y_BUS)],
                  brk=(tx, Y_BUS), label_side="above")
        ex = (self.bus_span["B2"][1] + self.bus_span["BE"][0]) / 2
        self.edge("52-ET", "B2", "BE", "breaker", [(self.bus_span["B2"][1], Y_BUS), (self.bus_span["BE"][0], Y_BUS)],
                  brk=(ex, Y_BUS), label_side="above")

        # ---- sub-buses
        names = {"B1B": ("BUS 1B", "MCC-1B"), "B2B": ("BUS 2B", "PNL-2B"), "BEB": ("BUS EB", "EMCC-1")}
        for s, (x0, x1) in self.sub_span.items():
            self.node(s, "bus", label=names[s][0], sub_label=names[s][1], x0=x0, x1=x1, y=Y_SUB, sub=True)

        # ---- feeders; numbering assigned later left-to-right
        self.pending = []    # (sort key, builder)
        for bus, fx, kind, target, ids in feeders:
            if kind == "sub":
                self.pending.append(((0, fx), ("feed", bus, target, fx)))
                for nid, lx in ids:
                    if nid == "PV":
                        self.pending.append(((1, lx), ("pv", target, lx)))
                    else:
                        self.pending.append(((1, lx), ("lbrk", target, nid, lx)))
                self.verticals.append((fx, Y_BUS, Y_SUB, "feed:" + target))
            elif kind == "direct":
                self.pending.append(((0, fx), ("direct", bus, target, fx)))
                self.verticals.append((fx, Y_BUS, Y_LOAD, "direct:" + target))
            else:
                jid = f"J{len([n for n in self.nodes if n.startswith('J')]) + 1}"
                self.node(jid, "junction", x=fx, y=Y_TEE)
                self.pending.append(((0, fx), ("pairfeed", bus, jid, fx)))
                for nid, lx in ids:
                    self.pending.append(((1, lx), ("pairbr", jid, nid, lx, fx)))
                self.verticals.append((fx, Y_BUS, Y_TEE, "pair:" + jid))

        # ---- alternate feeds into sub-buses (routed through the cable channel; they cross other feeders)
        alt_from = {"B1B": "B2", "B2B": rng.choice(["BE", "B1"]), "BEB": rng.choice(["B1", "B2"])}
        chans = CHANNELS[:]
        rng.shuffle(chans)
        self.alts = {}
        for sub in ("B1B", "B2B", "BEB"):
            src = alt_from[sub]
            route = self.route_alt(src, sub, chans.pop())
            if route is None:
                raise RejectSeed(f"no route for alternate feed {src}->{sub}")
            tap_x, ch, drop_x = route
            self.alts[sub] = (src, tap_x, ch, drop_x)
            self.pending.append(((0, tap_x), ("alt", src, sub, tap_x, ch, drop_x)))
            self.verticals.append((tap_x, Y_BUS, ch, "alt-tap:" + sub))
            self.verticals.append((drop_x, ch, Y_SUB, "alt-drop:" + sub))

        # ---- create breakers with left-to-right numbering
        self.pending.sort(key=lambda p: p[0])
        n = 0
        for _, item in self.pending:
            n += 1
            cid = f"CB-{n:02d}"
            kind = item[0]
            if kind == "feed":
                _, bus, sub, fx = item
                self.edge(cid, bus, sub, "breaker", [(fx, Y_BUS), (fx, Y_SUB)], brk=(fx, Y_FBRK), role="normal")
            elif kind == "direct":
                _, bus, nid, fx = item
                self.edge(cid, bus, nid, "breaker", [(fx, Y_BUS), (fx, Y_LOAD - 14)], brk=(fx, Y_FBRK))
            elif kind == "pairfeed":
                _, bus, jid, fx = item
                self.edge(cid, bus, jid, "breaker", [(fx, Y_BUS), (fx, Y_TEE)], brk=(fx, Y_FBRK))
            elif kind == "pairbr":
                _, jid, nid, lx, fx = item
                self.edge(cid, jid, nid, "breaker", [(fx, Y_TEE), (lx, Y_TEE), (lx, Y_LOAD - 14)], brk=(lx, Y_LBRK))
            elif kind == "lbrk":
                _, sub, nid, lx = item
                self.edge(cid, sub, nid, "breaker", [(lx, Y_SUB), (lx, Y_LOAD - 14)], brk=(lx, Y_LBRK))
            elif kind == "pv":
                _, sub, lx = item
                self.node("PV1", "pv", label="PV-1", kw=None, x=lx, y=Y_LOAD + 4)
                self.edge(cid, sub, "PV1", "breaker", [(lx, Y_SUB), (lx, Y_LOAD - 16)], brk=(lx, Y_LBRK))
            elif kind == "alt":
                _, src, sub, tx_, ch, dx = item
                self.edge(cid, src, sub, "breaker", [(tx_, Y_BUS), (tx_, ch), (dx, ch), (dx, Y_SUB)],
                          brk=(tx_, Y_FBRK), role="alternate")
        self.check_geometry()

    def edge_role(self, e):
        return e.get("role")

    def route_alt(self, src, sub, ch):
        s0, s1 = self.bus_span[src]
        u0, u1 = self.sub_span[sub]
        sub_feed = [v[0] for v in self.verticals if v[3] == "feed:" + sub][0]
        sub_ids = [n for n in self.nodes.values() if n["kind"] == "load"]
        load_x = [n["x"] for n in sub_ids] + [p[2] for p in []]
        # candidate drop x: inside the sub-bus, away from its feeder, loads below and other verticals
        def clear(x, xs, d):
            return all(abs(x - o) >= d for o in xs)
        allv = [v[0] for v in self.verticals]
        slot_xs = [u0 + 8 + i * 4 for i in range(int((u1 - u0 - 16) / 4) + 1)]
        drops = [x for x in slot_xs if clear(x, allv, 34) and clear(x, load_x, 22) and abs(x - sub_feed) >= 34]
        bus_level = [v[0] for v in self.verticals if v[1] == Y_BUS]
        taps = [x for x in range(int(s0) + 30, int(s1) - 60, 4) if clear(x, allv, 34) and clear(x, bus_level, 66)]
        # pass a slot-wide band for the tap so the tap is not inside the sub-bus x-span of its own drop
        if not drops or not taps:
            return None
        # prefer the drop end nearest the source and a tap near the bus end nearest the sub-bus
        src_mid = (s0 + s1) / 2
        drops.sort(key=lambda x: abs(x - src_mid))
        taps.sort(key=lambda x: abs(x - (u0 + u1) / 2))
        drop = drops[0]
        tap = self.rng.choice(taps[: max(1, len(taps) // 3)])
        # the new verticals must stay clear of the drop/tap pair itself
        if abs(tap - drop) < 34:
            return None
        return tap, ch, drop

    def check_geometry(self):
        """Reject drawings where a crossing sits on a corner, breaker or label, or verticals are too close."""
        xs = sorted(v[0] for v in self.verticals)
        for a, b in zip(xs, xs[1:]):
            if b - a < 30:
                raise RejectSeed(f"verticals too close: {a} {b}")
        horiz = []
        for e in self.edges:
            pts = e["pts"]
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                if y0 == y1 and y0 in CHANNELS:
                    horiz.append((min(x0, x1), max(x0, x1), y0, e["id"]))
        self.crossings = []
        for e in self.edges:
            pts = e["pts"]
            for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                if x0 != x1:
                    continue
                lo, hi = min(y0, y1), max(y0, y1)
                for hx0, hx1, hy, hid in horiz:
                    if hid == e["id"]:
                        continue
                    if hx0 < x0 < hx1 and lo < hy < hi:
                        if min(abs(x0 - hx0), abs(x0 - hx1)) < 20 or min(abs(hy - lo), abs(hy - hi)) < 20:
                            raise RejectSeed("crossing too close to a corner")
                        self.crossings.append((x0, hy, e["id"], hid))

    # ---------------------------------------------------------------- electrical model
    def ebyid(self, eid):
        return next(e for e in self.edges if e["id"] == eid)

    def sources(self):
        return [n for n, v in self.nodes.items() if v["kind"] in ("utility", "generator", "pv")]

    def live(self, states, sources=None):
        adj = {}
        for e in self.edges:
            if e["kind"] == "breaker" and states[e["id"]] != "closed":
                continue
            adj.setdefault(e["a"], []).append(e["b"])
            adj.setdefault(e["b"], []).append(e["a"])
        seen = set()
        stack = list(sources if sources is not None else self.sources())
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            stack.extend(adj.get(n, []))
        return seen

    def loads(self):
        return sorted((v for v in self.nodes.values() if v["kind"] == "load"), key=lambda v: v["x"])

    def load_breaker(self, nid):
        return next(e["id"] for e in self.edges if e["b"] == nid and e["kind"] == "breaker")


class RejectSeed(Exception):
    pass


# ============================================================================== rendering
def render(d: Diagram, states: dict, path: Path, gen_kw: int, notes: list[str]):
    fig = plt.figure(figsize=(16, 11), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    K = "#111111"
    LW = 1.35
    ax.add_patch(Rectangle((12, 12), W - 24, H - 24, fill=False, lw=1.6, ec=K))

    # conductors
    for e in d.edges:
        if e["kind"] == "transformer":
            continue
        xs, ys = zip(*e["pts"])
        if e["id"] in ("52-T", "52-ET"):
            ax.plot(xs, ys, color=K, lw=3.2, solid_capstyle="butt", zorder=2)
        else:
            ax.plot(xs, ys, color=K, lw=LW, zorder=2)
    # buses
    for n in d.nodes.values():
        if n["kind"] == "bus":
            sub = n.get("sub")
            ax.plot([n["x0"], n["x1"]], [n["y"], n["y"]], color=K, lw=4.5 if sub else 7, solid_capstyle="butt", zorder=3)
            if sub:
                ent = sorted(e["pts"][-1][0] for e in d.edges if e["b"] == n["id"])
                cuts = [n["x0"]] + ent + [n["x1"]]
                gap = max(zip(cuts, cuts[1:]), key=lambda g: g[1] - g[0])
                ax.text((gap[0] + gap[1]) / 2, n["y"] - 8, f'{n["label"]}\n{n["sub_label"]}', fontsize=7.8,
                        fontweight="bold", va="bottom", ha="center", zorder=6, linespacing=1.05)
            else:
                ax.text(n["x0"] + 4, n["y"] - 10, n["label"], fontsize=8.6, fontweight="bold", va="bottom", ha="left",
                        zorder=6, bbox=dict(fc="white", ec="none", pad=0.8))
    # junction dots
    for n in d.nodes.values():
        if n["kind"] == "junction":
            ax.add_patch(Circle((n["x"], n["y"]), 4.6, color=K, zorder=5))
    # sources
    for u in ("U1", "U2"):
        n = d.nodes[u]
        x = n["x"]
        ax.add_patch(Polygon([(x - 14, 72), (x + 14, 72), (x, 92)], closed=True, fc="white", ec=K, lw=1.4, zorder=4))
        ax.text(x, 66, f'{n["label"]}\n{n["kv"]}, 3φ, 60 Hz', fontsize=8.4, ha="center", va="bottom", fontweight="bold")
        t = n["xfmr"]
        ax.add_patch(Circle((x, 150), 19, fill=False, ec=K, lw=1.4, zorder=4))
        ax.add_patch(Circle((x, 176), 19, fill=False, ec=K, lw=1.4, zorder=4))
        ax.plot([x, x], [92, 131], color=K, lw=LW)
        ax.plot([x, x], [195, 240], color=K, lw=LW)
        ax.text(x + 28, 163, f'{t["id"]}\n{t["kva"]} kVA\n13.8 kV–480Y/277 V\nZ = 5.75%', fontsize=7.8, va="center")
    g = d.nodes["G1"]
    ax.add_patch(Circle((g["x"], g["y"]), 27, fc="white", ec=K, lw=1.5, zorder=4))
    ax.text(g["x"], g["y"] - 3, "G", fontsize=15, ha="center", va="center", fontweight="bold", zorder=5)
    ax.text(g["x"], g["y"] + 14, "~", fontsize=11, ha="center", va="center", zorder=5)
    ax.text(g["x"] - 36, g["y"], f"G1  STANDBY GEN\n{gen_kw} kW, 480 V\nDIESEL", fontsize=8.2, va="center", ha="right")

    # breakers
    for e in d.edges:
        if e["kind"] != "breaker":
            continue
        bx, by = e["breaker_at"]
        closed = states[e["id"]] == "closed"
        ax.add_patch(Rectangle((bx - 7.5, by - 7.5), 15, 15, fc=K if closed else "white", ec=K, lw=1.5, zorder=6))
        lab = e["label"] + ("\nN.O." if e["normally_open"] else "")
        if e["label_side"] == "above":
            ax.text(bx, by - 13, lab, fontsize=8.2, ha="center", va="bottom", fontweight="bold", zorder=7)
        else:
            ax.text(bx + 11, by, lab, fontsize=7.8, ha="left", va="center", zorder=7, linespacing=1.0,
                    bbox=dict(fc="white", ec="none", pad=0.3))
    # loads
    for n in d.nodes.values():
        if n["kind"] == "load":
            x, y = n["x"], n["y"]
            if n["motor"]:
                ax.add_patch(Circle((x, y), 12, fc="white", ec=K, lw=1.4, zorder=4))
                ax.text(x, y, "M", fontsize=8.5, ha="center", va="center", fontweight="bold", zorder=5)
            else:
                ax.add_patch(Polygon([(x - 10, y - 14), (x + 10, y - 14), (x, y + 6)], closed=True, fc=K, ec=K, zorder=4))
            ax.text(x, y + 18, f'{n["tag"]}\n{n["name"]}\n{n["kw"]} kW', fontsize=7.6, ha="center", va="top",
                    linespacing=1.15)
        if n["kind"] == "pv":
            x, y = n["x"], n["y"]
            ax.add_patch(Rectangle((x - 14, y - 16), 28, 28, fc="white", ec=K, lw=1.4, zorder=4))
            ax.plot([x - 14, x + 14], [y + 12, y - 16], color=K, lw=1)
            ax.text(x - 6, y - 7, "=", fontsize=8, ha="center", va="center")
            ax.text(x + 6, y + 4, "~", fontsize=8, ha="center", va="center")
            ax.text(x, y + 18, "PV-1\nSOLAR INV\n(SOURCE)", fontsize=7.6, ha="center", va="top", linespacing=1.15)

    # legend
    lx, ly = 30, 930
    ax.add_patch(Rectangle((lx, ly), 520, 150, fill=False, ec=K, lw=1.2))
    ax.text(lx + 8, ly + 8, "LEGEND", fontsize=9, fontweight="bold", va="top")
    items = [("closed", "CIRCUIT BREAKER, CLOSED"), ("open", "CIRCUIT BREAKER, OPEN"),
             ("no", "NORMALLY-OPEN TIE / ALT FEED (SHOWN OPEN)"), ("dot", "JUNCTION: CONDUCTORS CONNECTED"),
             ("cross", "CROSSING WITHOUT DOT: NOT CONNECTED")]
    for i, (k, t) in enumerate(items):
        yy = ly + 34 + i * 23
        if k in ("closed", "open", "no"):
            ax.add_patch(Rectangle((lx + 20, yy - 7), 14, 14, fc=K if k == "closed" else "white", ec=K, lw=1.5))
            if k == "no":
                ax.text(lx + 38, yy, "N.O.", fontsize=7.5, va="center", fontweight="bold")
        elif k == "dot":
            ax.plot([lx + 12, lx + 42], [yy, yy], color=K, lw=LW)
            ax.plot([lx + 27, lx + 27], [yy, yy + 10], color=K, lw=LW)
            ax.add_patch(Circle((lx + 27, yy), 4, color=K))
        else:
            ax.plot([lx + 12, lx + 42], [yy, yy], color=K, lw=LW)
            ax.plot([lx + 27, lx + 27], [yy - 9, yy + 9], color=K, lw=LW)
        ax.text(lx + 80, yy, t, fontsize=7.8, va="center")
    lx2 = lx + 385
    ax.add_patch(Circle((lx2 + 12, ly + 34), 10, fc="white", ec=K, lw=1.3))
    ax.text(lx2 + 12, ly + 34, "M", fontsize=7, ha="center", va="center", fontweight="bold")
    ax.text(lx2 + 28, ly + 34, "MOTOR LOAD", fontsize=7.5, va="center")
    ax.add_patch(Polygon([(lx2 + 4, ly + 51), (lx2 + 20, ly + 51), (lx2 + 12, ly + 65)], closed=True, fc=K))
    ax.text(lx2 + 28, ly + 57, "OTHER LOAD", fontsize=7.5, va="center")
    ax.add_patch(Circle((lx2 + 12, ly + 80), 7, fill=False, ec=K, lw=1.1))
    ax.add_patch(Circle((lx2 + 12, ly + 90), 7, fill=False, ec=K, lw=1.1))
    ax.text(lx2 + 28, ly + 85, "TRANSFORMER", fontsize=7.5, va="center")
    ax.add_patch(Circle((lx2 + 12, ly + 113), 9, fc="white", ec=K, lw=1.2))
    ax.text(lx2 + 12, ly + 113, "G", fontsize=7, ha="center", va="center", fontweight="bold")
    ax.text(lx2 + 28, ly + 113, "GENERATOR", fontsize=7.5, va="center")

    # notes
    nx = 575
    ax.text(nx, 935, "NOTES:", fontsize=8.6, fontweight="bold", va="top")
    base = ["1. BREAKER POSITIONS SHOWN AS FOUND (FILLED = CLOSED, HOLLOW = OPEN).",
            "2. CONDUCTORS THAT CROSS WITHOUT A JUNCTION DOT ARE NOT CONNECTED.",
            "3. ALL LOADS 480 V, 3φ. kW SHOWN = RUNNING DEMAND.",
            "4. 52 = ANSI DEVICE NO. FOR AC POWER CIRCUIT BREAKER."] + notes
    ax.text(nx, 955, "\n".join(base), fontsize=7.8, va="top", linespacing=1.5)

    # title block
    tx0, ty0, tw, th = 1150, 922, 420, 158
    ax.add_patch(Rectangle((tx0, ty0), tw, th, fill=False, ec=K, lw=1.6))
    for yy in (ty0 + 30, ty0 + 78, ty0 + 108, ty0 + 132):
        ax.plot([tx0, tx0 + tw], [yy, yy], color=K, lw=0.9)
    ax.plot([tx0 + 210, tx0 + 210], [ty0 + 108, ty0 + th], color=K, lw=0.9)
    ax.text(tx0 + 8, ty0 + 15, "NORTHGATE CAMPUS  FACILITIES ENGINEERING", fontsize=8, va="center")
    ax.text(tx0 + tw / 2, ty0 + 54, "MAIN-TIE-MAIN SWITCHGEAR, BLDG 4\nSINGLE-LINE DIAGRAM", fontsize=10.5,
            fontweight="bold", ha="center", va="center", linespacing=1.3)
    ax.text(tx0 + 8, ty0 + 93, "480 V DISTRIBUTION  •  AS-FOUND CONDITION", fontsize=8, va="center")
    ax.text(tx0 + 8, ty0 + 120, "DWG NO.  E-601", fontsize=8.5, va="center", fontweight="bold")
    ax.text(tx0 + 218, ty0 + 120, "REV  3        SCALE: NONE", fontsize=8.5, va="center")
    ax.text(tx0 + 8, ty0 + 145, "DRN: JRH    CHK: MKP", fontsize=8, va="center")
    ax.text(tx0 + 218, ty0 + 145, "DATE: 2026-10-02", fontsize=8, va="center")

    fig.savefig(path, dpi=100, facecolor="white")
    plt.close(fig)


# ============================================================================== templates
def base_states(d: Diagram, rng: random.Random, mode: str):
    """Breaker positions. Every sub-bus has exactly one of (normal, alternate) closed: no paralleled sources."""
    st = {e["id"]: "closed" for e in d.edges if e["kind"] == "breaker"}
    for e in d.edges:
        if e["id"] in ("52-T",):
            st[e["id"]] = "open"
            e["normally_open"] = True
    if mode == "t1":     # utility 2 out of service, G1 carrying bus 2 and bus E through 52-ET
        st["52-M2"] = "open"
        st["52-ET"] = "closed"
        st["52-G1"] = "closed"
    else:                # both utilities in, G1 either standby (ET closed) or running bus E alone (ET N.O.)
        if rng.random() < 0.5:
            st["52-G1"] = "open"
            st["52-ET"] = "closed"
        else:
            st["52-G1"] = "closed"
            st["52-ET"] = "open"
            d.ebyid("52-ET")["normally_open"] = True
    for sub in ("B1B", "B2B", "BEB"):
        normal = next(e for e in d.edges if e["b"] == sub and e.get("role") == "normal")
        alt = next(e for e in d.edges if e["b"] == sub and e.get("role") == "alternate")
        if rng.random() < 0.45:
            st[normal["id"]], st[alt["id"]] = "open", "closed"
        else:
            st[alt["id"]] = "open"
            alt["normally_open"] = True
    # one or two load breakers open (loads already off)
    lb = [d.load_breaker(n["id"]) for n in d.loads()]
    for cid in rng.sample(lb, rng.choice([1, 2])):
        st[cid] = "open"
    return st


def running(d, st):
    lv = d.live(st)
    return [n for n in d.loads() if n["id"] in lv]


def make_t1(seed):
    rng = random.Random(1000 + seed)
    d = Diagram(rng, with_pv=False)
    st = base_states(d, rng, "t1")
    run0 = running(d, st)
    st1 = dict(st, **{"52-M1": "open"})
    lv1 = d.live(st1)
    dead = [n for n in run0 if n["id"] not in lv1]
    if "B2" not in lv1:
        raise RejectSeed("tie far side dead")
    g_comp = d.live(st1, ["G1"])
    if "U2" in g_comp or "U1" in g_comp:
        raise RejectSeed("G1 paralleled with a utility")
    gen_now = [n for n in run0 if n["id"] in g_comp]
    gen_now_kw = sum(n["kw"] for n in gen_now)
    st2 = dict(st1, **{"52-T": "closed"})
    lv2 = d.live(st2)
    restored = [n for n in dead if n["id"] in lv2]
    not_restored = [n for n in dead if n["id"] not in lv2]
    total = gen_now_kw + sum(n["kw"] for n in restored)
    big = max(n["kw"] for n in restored)
    candidates = [r for r in range(500, 3000, 50) if gen_now_kw + 60 <= r <= total - big - 25]
    if not candidates:
        raise RejectSeed("no generator rating forces a 2+ load shed")
    rating = rng.choice(candidates)
    shed, load = [], total
    for n in sorted(restored, key=lambda n: -n["kw"]):
        if load <= rating:
            break
        shed.append(n)
        load -= n["kw"]
    if len(shed) < 2 or len(shed) == len(restored):
        raise RejectSeed("shed count")
    if abs(load - rating) < 10:
        raise RejectSeed("too close to rating")
    # trap check: something on the bus-1 side that does NOT drop (fed through a closed alternate), or an off load
    b1_side_alive = [n for n in run0 if n["id"] not in [x["id"] for x in dead] and n["id"] in d.live(st, ["U1"])]
    off = [n for n in d.loads() if n["id"] not in [x["id"] for x in run0]]
    answer = sum(n["kw"] for n in shed) + sum(n["kw"] for n in not_restored)
    q = (f"This is the as-found single-line diagram of a building's 480 V switchgear. Utility 2 is out of service, "
         f"so generator G1 is running and carrying everything it is connected to through closed breakers. "
         f"Main breaker 52-M1 trips. The operator then closes tie breaker 52-T (it was N.O.); a tie can only "
         f"restore power if the bus on its other side is energized. No other breaker changes position by itself. "
         f"G1 cannot carry more than its {rating} kW rating, so before closing 52-T the operator sheds loads that "
         f"lost power: he opens their own load breakers one at a time, largest kW first, stopping as soon as G1's "
         f"total load after the transfer would be at or below {rating} kW. Count only loads that were running "
         f"before the trip (a load behind an open breaker was not running). How many kW of load that was running "
         f"before the trip are still without power after the transfer? Answer with an integer number of kW.")
    steps = {
        "1_running_before": {n["tag"]: n["kw"] for n in run0},
        "1_off_before": [n["tag"] for n in off],
        "2_dead_after_52M1_trip": {n["tag"]: n["kw"] for n in dead},
        "2_bus1_side_still_alive_via_alternates": [n["tag"] for n in run0 if n["id"] in lv1 and n["id"] not in g_comp],
        "3_tie_far_side_energized_by": "G1 via 52-G1 and 52-ET (52-M2 open)",
        "3_G1_load_before_transfer_kw": gen_now_kw, "3_G1_loads": [n["tag"] for n in gen_now],
        "4_restorable_through_52T": {n["tag"]: n["kw"] for n in restored},
        "4_total_if_no_shedding_kw": total, "rating_kw": rating,
        "5_shed_largest_first": {n["tag"]: n["kw"] for n in shed}, "5_G1_load_after_kw": load,
        "answer_kw": answer,
    }
    return d, st, rating, q, answer, "integer", steps, {"n_loads": len(d.loads()), "n_shed": len(shed),
                                                          "traps": {"bus1_side_alive": len(b1_side_alive),
                                                                    "off_loads": len(off)}}, []


def make_t2(seed):
    rng = random.Random(2000 + seed)
    d = Diagram(rng, with_pv=False)
    st = base_states(d, rng, "t2")
    run0 = running(d, st)
    lv0 = d.live(st)
    # candidate second trip: a closed CB-xx at bus level not on bus 2
    cands = [e for e in d.edges if e["kind"] == "breaker" and e["id"].startswith("CB-") and st[e["id"]] == "closed"
             and e["a"] in ("B1", "BE")]
    rng.shuffle(cands)
    for e in cands:
        st1 = dict(st, **{"52-M2": "open", e["id"]: "open"})
        lv1 = d.live(st1)
        lost = [n for n in run0 if n["id"] not in lv1]
        lost_m2_only = [n for n in run0 if n["id"] not in d.live(dict(st, **{"52-M2": "open"}))]
        lost_cb_only = [n for n in run0 if n["id"] not in d.live(dict(st, **{e["id"]: "open"}))]
        if not (4 <= len(lost) <= 8):
            continue
        if len(lost_cb_only) < 1 or len(lost_m2_only) < 2:
            continue
        # trap: something drawn under bus 2 that survives, or an off load inside the dead area
        under_b2_alive = [n for n in run0 if n["id"] in lv1 and d.bus_span["B2"][0] <= n["x"] <= d.bus_span["B2"][1]]
        off_in_dead = [n for n in d.loads() if n["id"] not in lv0]
        if not under_b2_alive and not off_in_dead:
            continue
        cb = e["id"]
        break
    else:
        raise RejectSeed("no good double fault")
    ans = [n["tag"] for n in sorted(lost, key=lambda n: n["x"])]
    gen_state = ("Generator G1 is in standby and does not start" if st["52-G1"] == "open"
                 else "Generator G1 keeps running")
    q = (f"This is the as-found single-line diagram of a building's 480 V switchgear. Breakers 52-M2 and {cb} "
         f"both trip at the same moment. Nothing else changes: no other breaker opens or closes, N.O. ties stay "
         f"open, and {gen_state}. Which loads that were running before the event lose power? A load behind an "
         f"open breaker was not running. Answer with the load tags (for example CH-2), in the order they appear "
         f"on the drawing from left to right, separated by commas.")
    steps = {
        "1_running_before": [n["tag"] for n in run0],
        "1_off_before": [n["tag"] for n in d.loads() if n["id"] not in lv0],
        "2_lost_from_52M2_alone": [n["tag"] for n in lost_m2_only],
        "3_lost_from_" + cb + "_alone": [n["tag"] for n in lost_cb_only],
        "4_alive_though_drawn_under_bus2": [n["tag"] for n in under_b2_alive],
        "5_answer_left_to_right": ans,
    }
    return d, st, None, q, ans, "sequence", steps, {"n_loads": len(d.loads()), "n_lost": len(ans),
                                                    "second_trip": cb}, []


def make_t3(seed):
    rng = random.Random(3000 + seed)
    d = Diagram(rng, with_pv=True)
    st = base_states(d, rng, "t3")
    pv_cb = next(e["id"] for e in d.edges if e["b"] == "PV1")
    st[pv_cb] = "closed"
    # variant: Bus 2B fed from both ends (normal + alternate closed) when both ends are on the same source
    nrm = next(e for e in d.edges if e["b"] == "B2B" and e.get("role") == "normal")
    alt = next(e for e in d.edges if e["b"] == "B2B" and e.get("role") == "alternate")
    if alt["a"] == "BE" and st["52-ET"] == "closed" and st["52-G1"] == "open" and rng.random() < 0.6:
        st[nrm["id"]] = st[alt["id"]] = "closed"
        alt["normally_open"] = False
    lv0 = d.live(st)
    if "B2B" not in lv0:
        raise RejectSeed("2B dead")
    run0 = running(d, st)
    others = [n for n in run0 if not any(e["a"] == "B2B" and e["b"] == n["id"] for e in d.edges)]
    closed = [k for k, v in st.items() if v == "closed"]
    best = None
    for k in range(1, 5):
        sols = []
        for combo in itertools.combinations(closed, k):
            s = dict(st, **{c: "open" for c in combo})
            lv = d.live(s)
            if "B2B" in lv:
                continue
            if any(n["id"] not in lv for n in others):
                continue
            sols.append(sorted(combo))
        if sols:
            best = sols
            break
    if best is None or len(best) != 1:
        raise RejectSeed(f"min isolation set not unique: {best}")
    ans = best[0]
    if len(ans) < 2:
        raise RejectSeed("too small")
    # adjacent breakers for the steps
    adj = [e for e in d.edges if e["kind"] == "breaker" and "B2B" in (e["a"], e["b"])]
    q = ("This is the as-found single-line diagram of a building's 480 V switchgear. A crew must work on BUS 2B "
         "(panel PNL-2B). Bus 2B must be isolated: afterwards there may be no path through closed breakers from "
         "any source (utility services, generator G1, or the PV-1 solar inverter) to Bus 2B. Breakers that are "
         "already open need no action. Open as few breakers as possible, and do not cut power to any running load "
         "that is not fed from Bus 2B. Which breakers must be opened? Answer with the breaker IDs sorted "
         "alphabetically, separated by commas.")
    steps = {
        "1_breakers_touching_bus2B": {e["id"]: {"state": st[e["id"]], "other_side": e["a"] if e["b"] == "B2B" else e["b"],
                                                 "role": e.get("role") or ("pv" if e["b"] == "PV1" else "load")}
                                      for e in adj},
        "2_bus2B_currently_fed_by": [e["id"] for e in adj if e.get("role") and st[e["id"]] == "closed"],
        "3_backfeed_source_on_bus2B": pv_cb + " (PV-1)",
        "4_minimum_set_bruteforce": ans,
    }
    return d, st, None, q, ans, "sequence", steps, {"n_loads": len(d.loads()), "set_size": len(ans)}, []


TEMPLATES = {"trip": (make_t1, "pwr.trip_transfer_shed"), "dbl": (make_t2, "pwr.double_fault_list"),
             "iso": (make_t3, "pwr.isolation_min_set")}


def main():
    want = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    (OUT / "images").mkdir(parents=True, exist_ok=True)
    lines, log = [], []
    for name, (fn, qtype) in TEMPLATES.items():
        got, seed = 0, 0
        while got < want and seed < 400:
            try:
                d, st, rating, q, ans, atype, steps, diff, notes = fn(seed)
            except RejectSeed as ex:
                log.append(f"{name} seed {seed}: reject ({ex})")
                seed += 1
                continue
            tid = f"pwr2-{name}-{seed:06d}"
            gen_kw = rating or d.rng.choice([750, 1000, 1250])
            data = {"task_id": tid, "family": "power", "seed": seed, "generator_version": VERSION,
                    "params": {"template": name, **diff},
                    "data": {"nodes": d.nodes, "edges": d.edges, "states": st, "generator_kw": gen_kw,
                             "crossings": d.crossings},
                    "references": REFERENCES}
            (OUT / "data" / f"{tid}.json").write_text(json.dumps(data, indent=1))
            render(d, st, OUT / "images" / f"{tid}.png", gen_kw, notes)
            task = {"task_id": tid, "image": f"images/{tid}.png", "question": q, "answer": ans,
                    "answer_type": atype, "seed": seed, "generator_version": VERSION, "question_type": qtype,
                    "family": "power", "difficulty": {"level": "hard", **diff}, "data": f"data/{tid}.json",
                    "steps": steps, "references": REFERENCES}
            if name == "iso":
                task["ordered"] = True
            lines.append(json.dumps(task))
            log.append(f"{name} seed {seed}: OK answer={ans} crossings={len(d.crossings)}")
            got += 1
            seed += 1
    (OUT / "tasks.jsonl").write_text("\n".join(lines) + "\n")
    print("\n".join(log))


if __name__ == "__main__":
    main()
