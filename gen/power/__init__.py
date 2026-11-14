"""Power family (#47): a main-tie-main 480 V switchgear single-line diagram, as found, with chained questions.

Ported from results/spikes/power_v2/gen.py (Alex's spike), made a contracts/FAMILY.md plug-in, then fixed what the
spike found:
  * wording: every question states its procedure step by step; the trip question asks for kW "not running at the end"
  * variety: which sub-bus has the solar inverter / is the work bus, which sub-buses get alternate feeds and from
    where, group order and load mix are all drawn from the seed
  * trip: G1's rating is read from the drawing and chosen so the last shed is needed by a small margin
  * difficulty = crossing density: 1, 2 or 3 alternate feeds routed through the cable channel across other feeders

Templates: trip (integer kW), dbl (load tags left to right), iso (breaker IDs sorted).
"""
from __future__ import annotations

import itertools
import json
import random
from pathlib import Path

from matplotlib.patches import Circle, Polygon, Rectangle

from factory.render import new_figure, save_png, text_boxes, to_pixels

FAMILY = "power"
VERSION = "power-1.1.0"
TEMPLATES = ["trip", "dbl", "iso"]
_REFS = ["IEEE Std 141 (Red Book), secondary-selective / main-tie-main low-voltage switchgear single-line diagrams",
         "IEEE Std 315 / ANSI Y32.2 graphic symbols and ANSI/IEEE C37.2 device numbers (52 = AC circuit breaker)"]
REFERENCES = {t: _REFS for t in TEMPLATES}

W, H = 1600, 1100
SLOT, GGAP, BUS_GAP, X0 = 90, 26, 74, 46
Y_BUS, Y_FBRK, Y_SUB, Y_LBRK, Y_LOAD, Y_TEE = 330, 392, 640, 702, 772, 622
CHANNELS = [452, 492, 532, 572]
K = "#111111"
SUBS = ("B1B", "B2B", "BEB")

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
SUB_NAMES = {"B1B": ("BUS 1B", "MCC-1B"), "B2B": ("BUS 2B", "PNL-2B"), "BEB": ("BUS EB", "EMCC-1")}


class RejectSeed(Exception):
    """This seed can't make a fair task."""


# ============================================================================== topology + geometry
class Diagram:
    def __init__(self, rng: random.Random, pv_sub: str | None, n_alt: int):
        self.rng = rng
        self.nodes: dict[str, dict] = {}
        self.edges: list[dict] = []
        self.pv_sub = pv_sub
        self.n_alt = n_alt
        self.build()

    def node(self, nid, kind, **kw):
        self.nodes[nid] = {"id": nid, "kind": kind, **kw}

    def edge(self, eid, a, b, kind, pts, label=None, brk=None, label_side="right", role=None):
        self.edges.append({"id": eid, "a": a, "b": b, "kind": kind, "normally_open": False, "label": label or eid,
                           "pts": [list(p) for p in pts], "breaker_at": list(brk) if brk else None,
                           "label_side": label_side, "role": role})

    def build(self):
        rng = self.rng
        pool, life = POOL[:], LIFE[:]
        rng.shuffle(pool)
        rng.shuffle(life)
        n = {"B1B": rng.choice([3, 4]), "B2B": rng.choice([3, 4]), "BEB": rng.choice([2, 3])}
        if self.pv_sub:
            n[self.pv_sub] = max(n[self.pv_sub], 3)          # PV plus at least two loads
        groups = {"B1": [("sub", "B1B"), ("direct", None), ("pair", None)],
                  "B2": [("sub", "B2B"), ("direct", None)],
                  "BE": [("sub", "BEB"), ("direct", None)]}
        if rng.random() < 0.5:                                # the second direct/pair group moves between buses
            groups["B2"].append(groups["B1"].pop())
        for b in groups:
            rng.shuffle(groups[b])

        def total():
            return sum(n[s] if t == "sub" else (2 if t == "pair" else 1) for g in groups.values() for t, s in g)
        while total() > 14:                                   # keep the drawing readable
            big = max((s for s in SUBS if n[s] > (3 if s == self.pv_sub else 2)), key=lambda s: n[s])
            n[big] -= 1
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
        self.bus_span, self.sub_span, self.verticals = {}, {}, []
        feeders = []
        for bus in ("B1", "B2", "BE"):
            start = x
            for gtype, sub in groups[bus]:
                cnt = n[sub] if gtype == "sub" else (2 if gtype == "pair" else 1)
                left = x
                xs = [left + SLOT / 2 + i * SLOT for i in range(cnt)]
                if gtype == "sub":
                    self.sub_span[sub] = (left + 8, left + cnt * SLOT - 8)
                    specs = [pool.pop() for _ in range(cnt)]
                    if sub == self.pv_sub:
                        specs[rng.choice([0, cnt - 1])] = None        # PV inverter at one end of the sub-bus
                    ids = [("PV", xi) if sp is None else (make_load(sp, xi), xi) for xi, sp in zip(xs, specs)]
                    feed_x = left + SLOT * rng.choice(range(1, cnt))
                    feeders.append((bus, feed_x, "sub", sub, ids))
                elif gtype == "direct":
                    sp = life.pop() if bus == "BE" else pool.pop()
                    feeders.append((bus, xs[0], "direct", make_load(sp, xs[0]), None))
                else:
                    a, b = make_load(pool.pop(), xs[0]), make_load(pool.pop(), xs[1])
                    feeders.append((bus, (xs[0] + xs[1]) / 2, "pair", None, [(a, xs[0]), (b, xs[1])]))
                x += cnt * SLOT + GGAP
            self.bus_span[bus] = (start + 4, x - GGAP - 4)
            x += BUS_GAP - GGAP
        if x - BUS_GAP + GGAP > W - 40:
            raise RejectSeed("too wide")

        bx = {b: (s + e) / 2 for b, (s, e) in self.bus_span.items()}
        self.node("U1", "utility", label="UTILITY SERVICE 1", kv="13.8 kV", x=bx["B1"] - 60, y=60)
        self.node("U2", "utility", label="UTILITY SERVICE 2", kv="13.8 kV", x=bx["B2"] + 40, y=60)
        gx = bx["BE"] + 40
        self.node("G1", "generator", label="G1", x=gx, y=180)
        for b, lab in (("B1", "BUS 1  SWGR-1  480 V  3000 A"), ("B2", "BUS 2  SWGR-2  480 V  3000 A"),
                       ("BE", "BUS E  EMERG SWGR  480 V  1600 A")):
            self.node(b, "bus", label=lab, x0=self.bus_span[b][0], x1=self.bus_span[b][1], y=Y_BUS)
        for u, b, t, kva, z in (("U1", "B1", "T1", rng.choice([2000, 2500]), rng.choice([5.75, 6.0])),
                                ("U2", "B2", "T2", rng.choice([1500, 2000]), rng.choice([5.5, 5.75]))):
            ux = self.nodes[u]["x"]
            self.node(t + "s", "point", x=ux, y=240)
            self.nodes[u]["xfmr"] = {"id": t, "kva": kva, "z": z}
            self.edge(t, u, t + "s", "transformer", [(ux, 92), (ux, 240)], label=t)
            self.edge("52-M" + u[1], t + "s", b, "breaker", [(ux, 240), (ux, Y_BUS)], brk=(ux, 280))
        self.edge("52-G1", "G1", "BE", "breaker", [(gx, 208), (gx, Y_BUS)], brk=(gx, 275))
        tx = (self.bus_span["B1"][1] + self.bus_span["B2"][0]) / 2
        self.edge("52-T", "B1", "B2", "breaker", [(self.bus_span["B1"][1], Y_BUS), (self.bus_span["B2"][0], Y_BUS)],
                  brk=(tx, Y_BUS), label_side="above")
        ex = (self.bus_span["B2"][1] + self.bus_span["BE"][0]) / 2
        self.edge("52-ET", "B2", "BE", "breaker", [(self.bus_span["B2"][1], Y_BUS), (self.bus_span["BE"][0], Y_BUS)],
                  brk=(ex, Y_BUS), label_side="above")
        for s, (x0, x1) in self.sub_span.items():
            self.node(s, "bus", label=SUB_NAMES[s][0], sub_label=SUB_NAMES[s][1], x0=x0, x1=x1, y=Y_SUB, sub=True)

        self.pending = []
        for bus, fx, kind, target, ids in feeders:
            if kind == "sub":
                self.pending.append(((0, fx), ("feed", bus, target, fx)))
                for nid, lx in ids:
                    self.pending.append(((1, lx), ("pv", target, lx) if nid == "PV" else ("lbrk", target, nid, lx)))
                self.verticals.append((fx, Y_BUS, Y_SUB, "feed:" + target))
            elif kind == "direct":
                self.pending.append(((0, fx), ("direct", bus, target, fx)))
                self.verticals.append((fx, Y_BUS, Y_LOAD, "direct:" + target))
            else:
                jid = f"J{len([k for k in self.nodes if k.startswith('J')]) + 1}"
                self.node(jid, "junction", x=fx, y=Y_TEE)
                self.pending.append(((0, fx), ("pairfeed", bus, jid, fx)))
                for nid, lx in ids:
                    self.pending.append(((1, lx), ("pairbr", jid, nid, lx, fx)))
                self.verticals.append((fx, Y_BUS, Y_TEE, "pair:" + jid))

        # alternate feeds (difficulty = how many): routed through the cable channel, crossing other feeders
        home = {"B1B": "B1", "B2B": "B2", "BEB": "BE"}
        alt_subs = rng.sample(list(SUBS), self.n_alt)
        chans = CHANNELS[:]
        rng.shuffle(chans)
        self.alts = {}
        for sub in sorted(alt_subs):
            src = rng.choice([b for b in ("B1", "B2", "BE") if b != home[sub]])
            route = self.route_alt(src, sub, chans.pop())
            if route is None:
                raise RejectSeed(f"no route for alternate feed {src}->{sub}")
            tap_x, ch, drop_x = route
            self.alts[sub] = src
            self.pending.append(((0, tap_x), ("alt", src, sub, tap_x, ch, drop_x)))
            self.verticals.append((tap_x, Y_BUS, ch, "alt-tap:" + sub))
            self.verticals.append((drop_x, ch, Y_SUB, "alt-drop:" + sub))

        self.pending.sort(key=lambda p: p[0])
        for i, (_, item) in enumerate(self.pending, start=1):
            cid = f"CB-{i:02d}"
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
                self.node("PV1", "pv", label="PV-1", x=lx, y=Y_LOAD + 4)
                self.edge(cid, sub, "PV1", "breaker", [(lx, Y_SUB), (lx, Y_LOAD - 16)], brk=(lx, Y_LBRK))
            else:
                _, src, sub, tx_, ch, dx = item
                self.edge(cid, src, sub, "breaker", [(tx_, Y_BUS), (tx_, ch), (dx, ch), (dx, Y_SUB)],
                          brk=(tx_, Y_FBRK), role="alternate")
        self.check_geometry()

    def route_alt(self, src, sub, ch):
        s0, s1 = self.bus_span[src]
        u0, u1 = self.sub_span[sub]
        sub_feed = [v[0] for v in self.verticals if v[3] == "feed:" + sub][0]
        load_x = [nd["x"] for nd in self.nodes.values() if nd["kind"] == "load"]

        def clear(x, xs, d):
            return all(abs(x - o) >= d for o in xs)
        allv = [v[0] for v in self.verticals]
        slot_xs = [u0 + 8 + i * 4 for i in range(int((u1 - u0 - 16) / 4) + 1)]
        drops = [x for x in slot_xs if clear(x, allv, 34) and clear(x, load_x, 22) and abs(x - sub_feed) >= 34]
        bus_level = [v[0] for v in self.verticals if v[1] == Y_BUS]
        taps = [x for x in range(int(s0) + 30, int(s1) - 60, 4) if clear(x, allv, 34) and clear(x, bus_level, 66)]
        if not drops or not taps:
            return None
        src_mid = (s0 + s1) / 2
        drops.sort(key=lambda x: abs(x - src_mid))
        taps.sort(key=lambda x: abs(x - (u0 + u1) / 2))
        drop = drops[0]
        tap = self.rng.choice(taps[: max(1, len(taps) // 3)])
        if abs(tap - drop) < 34:
            return None
        return tap, ch, drop

    def check_geometry(self):
        """Fairness: no line closer than 30 px to another, no crossing near a corner."""
        xs = sorted(v[0] for v in self.verticals)
        for a, b in zip(xs, xs[1:]):
            if b - a < 30:
                raise RejectSeed(f"verticals too close: {a} {b}")
        horiz = []
        for e in self.edges:
            for (x0, y0), (x1, y1) in zip(e["pts"], e["pts"][1:]):
                if y0 == y1 and y0 in CHANNELS:
                    horiz.append((min(x0, x1), max(x0, x1), y0, e["id"]))
        self.crossings = []
        for e in self.edges:
            for (x0, y0), (x1, y1) in zip(e["pts"], e["pts"][1:]):
                if x0 != x1:
                    continue
                lo, hi = min(y0, y1), max(y0, y1)
                for hx0, hx1, hy, hid in horiz:
                    if hid != e["id"] and hx0 < x0 < hx1 and lo < hy < hi:
                        if min(abs(x0 - hx0), abs(x0 - hx1)) < 20 or min(abs(hy - lo), abs(hy - hi)) < 20:
                            raise RejectSeed("crossing too close to a corner")
                        self.crossings.append([x0, hy, e["id"], hid])

    # ---------------------------------------------------------------- electrical model (first solver: DFS)
    def ebyid(self, eid):
        return next(e for e in self.edges if e["id"] == eid)

    def sources(self):
        return [k for k, v in self.nodes.items() if v["kind"] in ("utility", "generator", "pv")]

    def live(self, states, sources=None):
        adj = {}
        for e in self.edges:
            if e["kind"] == "breaker" and states[e["id"]] != "closed":
                continue
            adj.setdefault(e["a"], []).append(e["b"])
            adj.setdefault(e["b"], []).append(e["a"])
        seen, stack = set(), list(sources if sources is not None else self.sources())
        while stack:
            k = stack.pop()
            if k not in seen:
                seen.add(k)
                stack.extend(adj.get(k, []))
        return seen

    def loads(self):
        return sorted((v for v in self.nodes.values() if v["kind"] == "load"), key=lambda v: v["x"])

    def load_breaker(self, nid):
        return next(e["id"] for e in self.edges if e["b"] == nid and e["kind"] == "breaker")


# ============================================================================== rendering
def render(nodes, edges, states, gen_kw, notes, png: Path) -> dict:
    fig = new_figure(W, H)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(H, 0)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    LW = 1.35
    ax.add_patch(Rectangle((12, 12), W - 24, H - 24, fill=False, lw=1.6, ec=K))
    for e in edges:
        if e["kind"] == "transformer":
            continue
        xs, ys = zip(*e["pts"])
        ax.plot(xs, ys, color=K, lw=3.2 if e["id"] in ("52-T", "52-ET") else LW, solid_capstyle="butt", zorder=2)
    for nd in nodes.values():
        if nd["kind"] == "bus":
            sub = nd.get("sub")
            ax.plot([nd["x0"], nd["x1"]], [nd["y"], nd["y"]], color=K, lw=4.5 if sub else 7, solid_capstyle="butt",
                    zorder=3)
            if sub:
                ent = sorted(e["pts"][-1][0] for e in edges if e["b"] == nd["id"])
                cuts = [nd["x0"]] + ent + [nd["x1"]]
                gap = max(zip(cuts, cuts[1:]), key=lambda g: g[1] - g[0])
                ax.text((gap[0] + gap[1]) / 2, nd["y"] - 8, f'{nd["label"]}\n{nd["sub_label"]}', fontsize=7.8,
                        fontweight="bold", va="bottom", ha="center", zorder=6, linespacing=1.05)
            else:
                ax.text(nd["x0"] + 4, nd["y"] - 10, nd["label"], fontsize=8.6, fontweight="bold", va="bottom",
                        ha="left", zorder=6, bbox=dict(fc="white", ec="none", pad=0.8))
        elif nd["kind"] == "junction":
            ax.add_patch(Circle((nd["x"], nd["y"]), 4.6, color=K, zorder=5))
    for u in ("U1", "U2"):
        nd = nodes[u]
        x = nd["x"]
        ax.add_patch(Polygon([(x - 14, 72), (x + 14, 72), (x, 92)], closed=True, fc="white", ec=K, lw=1.4, zorder=4))
        ax.text(x, 66, f'{nd["label"]}\n{nd["kv"]}, 3φ, 60 Hz', fontsize=8.4, ha="center", va="bottom",
                fontweight="bold")
        t = nd["xfmr"]
        ax.add_patch(Circle((x, 150), 19, fill=False, ec=K, lw=1.4, zorder=4))
        ax.add_patch(Circle((x, 176), 19, fill=False, ec=K, lw=1.4, zorder=4))
        ax.plot([x, x], [92, 131], color=K, lw=LW)
        ax.plot([x, x], [195, 240], color=K, lw=LW)
        ax.text(x + 28, 163, f'{t["id"]}\n{t["kva"]} kVA\n13.8 kV–480Y/277 V\nZ = {t["z"]}%', fontsize=7.8,
                va="center")
    g = nodes["G1"]
    ax.add_patch(Circle((g["x"], g["y"]), 27, fc="white", ec=K, lw=1.5, zorder=4))
    ax.text(g["x"], g["y"] - 3, "G", fontsize=15, ha="center", va="center", fontweight="bold", zorder=5)
    ax.text(g["x"], g["y"] + 14, "~", fontsize=11, ha="center", va="center", zorder=5)
    ax.text(g["x"] - 36, g["y"], f"G1  STANDBY GEN\n{gen_kw} kW, 480 V\nDIESEL", fontsize=8.2, va="center", ha="right")
    probes = []
    for e in edges:
        if e["kind"] != "breaker":
            continue
        bx, by = e["breaker_at"]
        closed = states[e["id"]] == "closed"
        ax.add_patch(Rectangle((bx - 8, by - 8), 16, 16, fc=K if closed else "white", ec=K, lw=1.5, zorder=6))
        lab = e["label"] + ("\nN.O." if e["normally_open"] else "")
        if e["label_side"] == "above":
            ax.text(bx, by - 14, lab, fontsize=8.2, ha="center", va="bottom", fontweight="bold", zorder=7)
        else:
            ax.text(bx + 12, by, lab, fontsize=7.8, ha="left", va="center", zorder=7, linespacing=1.0,
                    bbox=dict(fc="white", ec="none", pad=0.3))
        probes.append({"xy": to_pixels(ax, bx, by), "expect": K if closed else "#ffffff", "tol": 40,
                       "what": f"breaker {e['id']} {'closed (filled)' if closed else 'open (hollow)'}"})
    for nd in nodes.values():
        if nd["kind"] == "load":
            x, y = nd["x"], nd["y"]
            if nd["motor"]:
                ax.add_patch(Circle((x, y), 12, fc="white", ec=K, lw=1.4, zorder=4))
                ax.text(x, y, "M", fontsize=8.5, ha="center", va="center", fontweight="bold", zorder=5)
            else:
                ax.add_patch(Polygon([(x - 10, y - 14), (x + 10, y - 14), (x, y + 6)], closed=True, fc=K, ec=K,
                                     zorder=4))
            ax.text(x, y + 18, f'{nd["tag"]}\n{nd["name"]}\n{nd["kw"]} kW', fontsize=7.6, ha="center", va="top",
                    linespacing=1.15)
        elif nd["kind"] == "pv":
            x, y = nd["x"], nd["y"]
            ax.add_patch(Rectangle((x - 14, y - 16), 28, 28, fc="white", ec=K, lw=1.4, zorder=4))
            ax.plot([x - 14, x + 14], [y + 12, y - 16], color=K, lw=1)
            ax.text(x - 6, y - 7, "=", fontsize=8, ha="center", va="center")
            ax.text(x + 6, y + 4, "~", fontsize=8, ha="center", va="center")
            ax.text(x, y + 18, "PV-1\nSOLAR INV\n(SOURCE)", fontsize=7.6, ha="center", va="top", linespacing=1.15)

    lx, ly = 30, 930
    ax.add_patch(Rectangle((lx, ly), 520, 150, fill=False, ec=K, lw=1.2))
    ax.text(lx + 8, ly + 8, "LEGEND", fontsize=9, fontweight="bold", va="top")
    items = [("closed", "CIRCUIT BREAKER, CLOSED"), ("open", "CIRCUIT BREAKER, OPEN"),
             ("no", "NORMALLY-OPEN TIE / ALT FEED (SHOWN OPEN)"), ("dot", "JUNCTION: CONDUCTORS CONNECTED"),
             ("cross", "CROSSING WITHOUT DOT: NOT CONNECTED")]
    for i, (k, t) in enumerate(items):
        yy = ly + 34 + i * 23
        if k in ("closed", "open", "no"):
            ax.add_patch(Rectangle((lx + 20, yy - 8), 16, 16, fc=K if k == "closed" else "white", ec=K, lw=1.5))
            if k == "no":
                ax.text(lx + 40, yy, "N.O.", fontsize=7.5, va="center", fontweight="bold")
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
    nx = 575
    ax.text(nx, 935, "NOTES:", fontsize=8.6, fontweight="bold", va="top")
    base = ["1. BREAKER POSITIONS SHOWN AS FOUND (FILLED = CLOSED, HOLLOW = OPEN).",
            "2. CONDUCTORS THAT CROSS WITHOUT A JUNCTION DOT ARE NOT CONNECTED.",
            "3. ALL LOADS 480 V, 3φ. kW SHOWN = RUNNING DEMAND.",
            "4. 52 = ANSI DEVICE NO. FOR AC POWER CIRCUIT BREAKER."] + notes
    ax.text(nx, 955, "\n".join(base), fontsize=7.8, va="top", linespacing=1.5)
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
    texts = text_boxes(fig)
    save_png(fig, png)
    return {"texts": texts, "probes": probes}


# ============================================================================== states + templates
def base_states(d: Diagram, rng: random.Random, mode: str):
    """Breaker positions. Every sub-bus has exactly one of (normal, alternate) closed: no paralleled sources."""
    st = {e["id"]: "closed" for e in d.edges if e["kind"] == "breaker"}
    st["52-T"] = "open"
    d.ebyid("52-T")["normally_open"] = True
    if mode == "trip":       # utility 2 out of service, G1 carrying bus 2 and bus E through 52-ET
        st["52-M2"] = "open"
    elif rng.random() < 0.5:
        st["52-G1"] = "open"
    else:
        st["52-ET"] = "open"
        d.ebyid("52-ET")["normally_open"] = True
    for sub in SUBS:
        normal = next(e for e in d.edges if e["b"] == sub and e["role"] == "normal")
        alt = next((e for e in d.edges if e["b"] == sub and e["role"] == "alternate"), None)
        if alt is None:
            continue
        if rng.random() < 0.45:
            st[normal["id"]], st[alt["id"]] = "open", "closed"
        else:
            st[alt["id"]] = "open"
            alt["normally_open"] = True
    lb = [d.load_breaker(nd["id"]) for nd in d.loads()]
    for cid in rng.sample(lb, rng.choice([1, 2])):
        st[cid] = "open"
    return st


def running(d, st):
    lv = d.live(st)
    return [nd for nd in d.loads() if nd["id"] in lv]


def make_trip(rng, difficulty):
    d = Diagram(rng, None, difficulty)
    st = base_states(d, rng, "trip")
    run0 = running(d, st)
    st1 = dict(st, **{"52-M1": "open"})
    lv1 = d.live(st1)
    dead = [nd for nd in run0 if nd["id"] not in lv1]
    if "B2" not in lv1 or len(dead) < 3:
        raise RejectSeed("tie far side dead or too few dead loads")
    g_comp = d.live(st1, ["G1"])
    if "U2" in g_comp or "U1" in g_comp:
        raise RejectSeed("G1 paralleled with a utility")
    gen_now_kw = sum(nd["kw"] for nd in run0 if nd["id"] in g_comp)
    lv2 = d.live(dict(st1, **{"52-T": "closed"}))
    restored = [nd for nd in dead if nd["id"] in lv2]
    not_restored = [nd for nd in dead if nd["id"] not in lv2]
    if len(restored) < 3:
        raise RejectSeed("too few restorable loads")
    # cross-feed trap (pilot 1: misses came from closed alternate feeds): loads whose fate contradicts where they are
    # drawn, i.e. drawn under bus 1 but still alive, or drawn under bus 2 / bus E but dead after the trip
    under_b1 = lambda nd: d.bus_span["B1"][0] - SLOT <= nd["x"] <= d.bus_span["B1"][1] + SLOT / 2
    traps = [nd for nd in run0 if (under_b1(nd) and nd["id"] in lv1) or (not under_b1(nd) and nd["id"] not in lv1)]
    if len(traps) < 2:
        raise RejectSeed("fewer than 2 cross-feed traps")
    total = gen_now_kw + sum(nd["kw"] for nd in restored)
    options = []
    for rating in range(500, 3000, 25):
        if rating < gen_now_kw + 60:
            continue
        shed, load = [], total
        for nd in sorted(restored, key=lambda v: -v["kw"]):
            if load <= rating:
                break
            shed.append(nd)
            load -= nd["kw"]
        if len(shed) < 2 or len(shed) == len(restored) or load > rating:
            continue
        before_last = load + shed[-1]["kw"]
        # exact sums matter: the last shed is needed by at most 40 kW, and G1 ends 10 to 60 kW under its rating
        if before_last - rating <= 40 and 10 <= rating - load <= 60:
            options.append((rating, shed, load))
    if not options:
        raise RejectSeed("no generator rating makes a tight 2+ load shed")
    rating, shed, load = options[rng.randrange(len(options))]
    off = [nd for nd in d.loads() if nd["id"] not in {x["id"] for x in run0}]
    answer = sum(nd["kw"] for nd in shed) + sum(nd["kw"] for nd in not_restored)
    q = ("This is the as-found single-line diagram of a building's 480 V switchgear. Utility 2 is out of service, "
         "so standby generator G1 is running and carries every load it is connected to through closed breakers. "
         "Then main breaker 52-M1 trips. The operator restores power with this procedure: "
         "(1) find the loads that were running before the trip and lost power; "
         "(2) tie breaker 52-T (now open) will be closed, which re-energizes only what can then be reached from G1 "
         "through closed breakers; "
         "(3) G1's rating is printed next to it on the drawing; if G1's total load after closing 52-T would exceed "
         "that rating, the operator first opens the load breakers of loads that 52-T would restore, one at a time, "
         "largest kW first, until the total is at or below the rating; "
         "(4) the operator closes 52-T. No other breaker changes position. A load behind an open breaker was not "
         "running before the trip. What is the total kW of the loads that were running before the trip and are not "
         "running at the end (loads shed in step 3 plus loads 52-T cannot reach)? Answer with an integer number of kW.")
    steps = {"1_running_before": {nd["tag"]: nd["kw"] for nd in run0}, "1_off_before": [nd["tag"] for nd in off],
             "2_dead_after_52M1": {nd["tag"]: nd["kw"] for nd in dead},
             "3_G1_load_before_kw": gen_now_kw, "4_restorable_via_52T": {nd["tag"]: nd["kw"] for nd in restored},
             "4_not_reachable": {nd["tag"]: nd["kw"] for nd in not_restored}, "5_G1_rating_kw": rating,
             "5_total_without_shedding_kw": total, "6_shed_largest_first": {nd["tag"]: nd["kw"] for nd in shed},
             "6_G1_load_after_kw": load, "answer_kw": answer}
    return d, st, rating, {"template": "trip"}, q, answer, "integer", steps


def make_dbl(rng, difficulty):
    d = Diagram(rng, None, difficulty)
    st = base_states(d, rng, "dbl")
    run0 = running(d, st)
    lv0 = d.live(st)
    cands = [e for e in d.edges if e["kind"] == "breaker" and e["id"].startswith("CB-") and st[e["id"]] == "closed"
             and e["a"] in ("B1", "BE")]
    rng.shuffle(cands)
    for e in cands:
        st1 = dict(st, **{"52-M2": "open", e["id"]: "open"})
        lv1 = d.live(st1)
        lost = [nd for nd in run0 if nd["id"] not in lv1]
        lost_m2 = [nd for nd in run0 if nd["id"] not in d.live(dict(st, **{"52-M2": "open"}))]
        lost_cb = [nd for nd in run0 if nd["id"] not in d.live(dict(st, **{e["id"]: "open"}))]
        if not (3 <= len(lost) <= 7) or len(lost_cb) < 1 or len(lost_m2) < 1:
            continue
        under_b2_alive = [nd for nd in run0 if nd["id"] in lv1 and d.bus_span["B2"][0] <= nd["x"] <= d.bus_span["B2"][1]]
        off_in_dead = [nd for nd in d.loads() if nd["id"] not in lv0]
        if not under_b2_alive and not off_in_dead:
            continue
        # cross-feed trap: at least 2 lost loads drawn away from bus 2 and not behind the second trip itself
        cross_lost = [nd for nd in lost if not (d.bus_span["B2"][0] <= nd["x"] <= d.bus_span["B2"][1])
                      and nd["id"] not in {x["id"] for x in lost_cb}]
        if len(cross_lost) < 2:
            continue
        cb = e["id"]
        break
    else:
        raise RejectSeed("no good double fault")
    ans = [nd["tag"] for nd in sorted(lost, key=lambda v: v["x"])]
    gen_state = ("Standby generator G1 is not running and does not start" if st["52-G1"] == "open"
                 else "Generator G1 keeps running")
    q = (f"This is the as-found single-line diagram of a building's 480 V switchgear. Breakers 52-M2 and {cb} both "
         f"trip at the same moment. Nothing else changes: no other breaker opens or closes, normally-open (N.O.) "
         f"breakers stay open, and {gen_state}. A load has power only if a path of closed breakers connects it to a "
         f"running source. Which loads that were running before the event have no power afterwards? A load behind "
         f"an open breaker was not running. Answer with the load tags (for example CH-2), in the order they appear "
         f"on the drawing from left to right, separated by commas.")
    steps = {"1_running_before": [nd["tag"] for nd in run0],
             "1_off_before": [nd["tag"] for nd in d.loads() if nd["id"] not in lv0],
             "2_lost_from_52M2_alone": [nd["tag"] for nd in lost_m2],
             f"3_lost_from_{cb}_alone": [nd["tag"] for nd in lost_cb],
             "4_alive_though_drawn_under_bus2": [nd["tag"] for nd in under_b2_alive], "5_answer_left_to_right": ans}
    return d, st, None, {"template": "dbl", "second_trip": cb}, q, ans, "sequence", steps


def make_iso(rng, difficulty):
    target = rng.choice(list(SUBS))
    d = Diagram(rng, target, difficulty)
    st = base_states(d, rng, "iso")
    pv_cb = next(e["id"] for e in d.edges if e["b"] == "PV1")
    st[pv_cb] = "closed"
    nrm = next(e for e in d.edges if e["b"] == target and e["role"] == "normal")
    alt = next((e for e in d.edges if e["b"] == target and e["role"] == "alternate"), None)
    if alt is not None and rng.random() < 0.6:
        # fed from both ends, allowed only when both ends already sit on the same source group
        s = dict(st, **{nrm["id"]: "open", alt["id"]: "open"})
        if alt["a"] in d.live(s, [nrm["a"]]):
            st[nrm["id"]] = st[alt["id"]] = "closed"
            alt["normally_open"] = False
    lv0 = d.live(st)
    if target not in lv0:
        raise RejectSeed("work bus dead")
    # cross-feed trap: the work bus must be fed through its alternate feed, which is tapped from another bus and
    # crosses the sheet (pilot 1: the misses were all on alternate-fed buses)
    if alt is None or st[alt["id"]] != "closed":
        raise RejectSeed("work bus not fed through its crossing alternate feed")
    run0 = running(d, st)
    fed_from_target = {e["b"] for e in d.edges if e["a"] == target}
    others = [nd for nd in run0 if nd["id"] not in fed_from_target]
    closed = sorted(k for k, v in st.items() if v == "closed")
    best = None
    for k in range(1, 5):
        sols = []
        for combo in itertools.combinations(closed, k):
            lv = d.live(dict(st, **{c: "open" for c in combo}))
            if target in lv or any(nd["id"] not in lv for nd in others):
                continue
            sols.append(sorted(combo))
        if sols:
            best = sols
            break
    if best is None or len(best) != 1:
        raise RejectSeed(f"minimum isolation set not unique: {best}")
    ans = best[0]
    if len(ans) < 2:
        raise RejectSeed("isolation set too small")
    label, panel = SUB_NAMES[target]
    q = (f"This is the as-found single-line diagram of a building's 480 V switchgear. A crew must work on {label} "
         f"(panel {panel}). It must be isolated: afterwards there may be no path through closed breakers from any "
         f"source (utility services, generator G1, or the PV-1 solar inverter, which can feed power back) to {label}. "
         f"Breakers that are already open need no action. Open as few breakers as possible, and do not cut power to "
         f"any running load that is not fed from {label}. Which breakers must be opened? Answer with the breaker IDs "
         f"sorted alphabetically, separated by commas.")
    adj = [e for e in d.edges if e["kind"] == "breaker" and target in (e["a"], e["b"])]
    steps = {"1_breakers_touching_work_bus": {e["id"]: {"state": st[e["id"]],
                                                         "other_side": e["a"] if e["b"] == target else e["b"]}
                                               for e in adj},
             "2_work_bus_fed_by": [e["id"] for e in adj if e["role"] and st[e["id"]] == "closed"],
             "3_backfeed": pv_cb + " (PV-1)", "4_minimum_set_bruteforce": ans}
    return d, st, None, {"template": "iso", "work_bus": target}, q, ans, "sequence", steps


MAKERS = {"trip": make_trip, "dbl": make_dbl, "iso": make_iso}


def build(seed: int, template: str, difficulty: int, out_dir: Path) -> dict:
    if template not in TEMPLATES:
        raise ValueError(f"unknown template {template!r}")
    difficulty = max(1, min(3, int(difficulty)))
    out_dir = Path(out_dir)
    last = None
    for attempt in range(400):           # deterministic retries inside one seed
        rng = random.Random(seed * 1000 + attempt * 7 + difficulty * 100003 + TEMPLATES.index(template) * 31)
        try:
            d, st, rating, tparams, q, ans, atype, steps = MAKERS[template](rng, difficulty)
            break
        except RejectSeed as ex:
            last = ex
    else:
        raise RejectSeed(f"400 attempts rejected, last: {last}")
    gen_kw = rating or rng.choice([750, 1000, 1250])
    tid = f"{FAMILY}-{template}-{seed:06d}"
    doc = {"task_id": tid, "family": FAMILY, "seed": seed, "generator_version": VERSION,
           "params": {"difficulty": difficulty, "alternate_feeds": difficulty, "attempt": attempt,
                      "n_loads": len(d.loads()), "crossings": len(d.crossings), **tparams},
           "data": {"nodes": d.nodes, "edges": d.edges, "states": st, "generator_kw": gen_kw,
                    "crossings": d.crossings, **tparams},
           "references": REFERENCES[template]}
    data_path = out_dir / "data" / f"{tid}.json"
    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(doc, indent=1), encoding="utf-8")                      # 1. data first
    layout = render(d.nodes, d.edges, st, gen_kw, [], out_dir / "images" / f"{tid}.png")    # 2. image from data
    rec = {"task_id": tid, "image": f"images/{tid}.png", "data": f"data/{tid}.json", "question": q,
           "answer": ans, "answer_type": atype, "steps": steps, "layout": layout}
    if template == "dbl":
        rec["ordered"] = True
    if template == "iso":
        rec["ordered"] = True
    return rec


# ============================================================================== second solver: union-find
def _components(edges, states):
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for e in edges:
        find(e["a"]), find(e["b"])
        if e["kind"] != "breaker" or states[e["id"]] == "closed":
            parent[find(e["a"])] = find(e["b"])
    return find


def _powered(nodes, edges, states, sources=None):
    find = _components(edges, states)
    srcs = sources if sources is not None else [k for k, v in nodes.items() if v["kind"] in ("utility", "generator",
                                                                                         "pv")]
    roots = {find(s) for s in srcs}
    return {k for k in nodes if find(k) in roots}


def solve_independent(data: dict, template: str):
    dd = data["data"] if "data" in data and isinstance(data["data"], dict) and "nodes" in data["data"] else data
    nodes, edges, st = dd["nodes"], dd["edges"], dd["states"]
    loads = sorted((v for v in nodes.values() if v["kind"] == "load"), key=lambda v: v["x"])
    on0 = _powered(nodes, edges, st)
    run0 = [v for v in loads if v["id"] in on0]
    if template == "trip":
        rating = dd["generator_kw"]
        st1 = dict(st, **{"52-M1": "open"})
        on1 = _powered(nodes, edges, st1)
        dead = [v for v in run0 if v["id"] not in on1]
        g = _powered(nodes, edges, st1, ["G1"])
        g_kw = sum(v["kw"] for v in run0 if v["id"] in g)
        on2 = _powered(nodes, edges, dict(st1, **{"52-T": "closed"}))
        restored = sorted((v for v in dead if v["id"] in on2), key=lambda v: v["kw"], reverse=True)
        lost = sum(v["kw"] for v in dead if v["id"] not in on2)
        load = g_kw + sum(v["kw"] for v in restored)
        i = 0
        while load > rating and i < len(restored):
            load -= restored[i]["kw"]
            lost += restored[i]["kw"]
            i += 1
        return lost
    if template == "dbl":
        on1 = _powered(nodes, edges, dict(st, **{"52-M2": "open", dd["second_trip"]: "open"}))
        return [v["tag"] for v in run0 if v["id"] not in on1]
    if template == "iso":
        target = dd["work_bus"]
        fed = {e["b"] for e in edges if e["a"] == target}
        keep = [v["id"] for v in run0 if v["id"] not in fed]
        closed = sorted(k for k, v in st.items() if v == "closed")
        for k in range(1, 6):
            sols = [list(c) for c in itertools.combinations(closed, k)
                    if (lambda on: target not in on and all(x in on for x in keep))(
                        _powered(nodes, edges, dict(st, **{b: "open" for b in c})))]
            if sols:
                return sols[0] if len(sols) == 1 else None
        return None
    raise ValueError(template)
