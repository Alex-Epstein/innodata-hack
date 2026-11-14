"""Generate resistor-network schematics + ground truth.

Each circuit is a geometric netlist: resistors and wires between grid points.
Electrical nodes = points merged by wires (union-find). Ground truth computed two
independent ways: (1) graph series/parallel reduction, (2) numpy nodal analysis.
"""
import json, random, sys
from fractions import Fraction
import numpy as np
import schemdraw
import schemdraw.elements as elm
import matplotlib
matplotlib.use("Agg")
from PIL import Image

E12 = [10, 12, 15, 18, 22, 27, 33, 39, 47, 56, 68, 82]
VALUES = [b * m for m in (1, 10, 100) for b in E12]


class Ckt:
    def __init__(self):
        self.res = []      # dict(p, q, side, kind)
        self.wires = []    # (a, b)
        self.terms = {}    # name -> point (A, B)
        self.open_terms = {}  # extra unconnected terminals, e.g. C
        self.notes = []

    def R(self, p, q, side, kind="normal"):
        self.res.append(dict(p=p, q=q, side=side, kind=kind))

    def W(self, *pts):
        for a, b in zip(pts, pts[1:]):
            self.wires.append((a, b))


# ---------------- templates ----------------
def L1(v):
    c = Ckt()
    if v == 0:  # R1 + (R2||R3) + R4, horizontal
        c.terms = {"A": (0, 0), "B": (15, 0)}
        c.R((0, 0), (5, 0), "top")
        c.W((5, 0), (5, 2)); c.R((5, 2), (10, 2), "top"); c.W((10, 2), (10, 0))
        c.W((5, 0), (5, -2)); c.R((5, -2), (10, -2), "bottom"); c.W((10, -2), (10, 0))
        c.R((10, 0), (15, 0), "top")
    elif v == 1:  # (R1||R2) + R3 + R4
        c.terms = {"A": (0, 0), "B": (17, 0)}
        c.W((0, 0), (2, 0))
        c.W((2, 0), (2, 2)); c.R((2, 2), (7, 2), "top"); c.W((7, 2), (7, 0))
        c.W((2, 0), (2, -2)); c.R((2, -2), (7, -2), "bottom"); c.W((7, -2), (7, 0))
        c.R((7, 0), (12, 0), "top")
        c.R((12, 0), (17, 0), "top")
    else:  # U shape: R1 top, R2||R3 vertical side by side, R4 bottom
        c.terms = {"A": (0, 5), "B": (0, 0)}
        c.R((0, 5), (5, 5), "top")
        c.W((5, 5), (9, 5))
        c.R((5, 5), (5, 0), "left")
        c.R((9, 5), (9, 0), "right")
        c.W((9, 0), (5, 0))
        c.R((5, 0), (0, 0), "bottom")
    return c


def L2(v):
    c = Ckt()
    if v == 0:  # R1 + R6 + R2 || (R3 + R4 + R5), ladder
        c.terms = {"A": (0, 6), "B": (0, 0)}
        c.R((0, 6), (5, 6), "top")
        c.R((5, 6), (5, 0), "right")
        c.R((5, 6), (10, 6), "top")
        c.R((10, 6), (10, 0), "right")
        c.R((10, 0), (5, 0), "bottom")
        c.R((5, 0), (0, 0), "bottom")
    elif v == 1:  # R1 + R6 + R2 || (R3 + R4 + R5 + R7) with stacked vertical pair
        c.terms = {"A": (0, 7), "B": (0, 0)}
        c.R((0, 7), (5, 7), "top")
        c.R((5, 7), (5, 0), "right")
        c.R((5, 7), (11, 7), "top")
        c.R((11, 7), (11, 3.5), "right")
        c.R((11, 3.5), (11, 0), "right")
        c.R((11, 0), (5, 0), "bottom")
        c.R((5, 0), (0, 0), "bottom")
    else:  # R1 + [(R2 + R3||R5) || R4] + R6 ; R5 vertical between rails, looks like a bridge
        c.terms = {"A": (0, 0), "B": (22, 0)}
        c.R((0, 0), (5, 0), "top")
        c.W((5, 0), (5, 3)); c.W((5, 0), (5, -3))
        c.R((5, 3), (11, 3), "top")
        c.R((11, 3), (17, 3), "top")
        c.R((11, 3), (11, -3), "right")
        c.R((5, -3), (11, -3), "bottom")
        c.W((11, -3), (17, -3))
        c.W((17, 3), (17, 0)); c.W((17, -3), (17, 0))
        c.R((17, 0), (22, 0), "top")
    return c


def L3(v):
    """Ladder: R1 + Rb + R2 || (R3 + R4 || ((R5||R6) + R7 + R8)), plus one trap."""
    c = Ckt()
    c.terms = {"A": (0, 6), "B": (0, 0)}
    c.R((0, 6), (5, 6), "top")                       # R1
    c.R((5, 6), (5, 0), "right")                     # R2 rung
    c.R((5, 6), (10, 6), "top")                      # R3
    c.R((10, 6), (10, 0), "right")                   # R4 rung
    c.R((10, 6), (15, 6), "bottom")                  # R5 (lower of pair)
    c.W((10, 6), (10, 8.5)); c.R((10, 8.5), (15, 8.5), "top"); c.W((15, 8.5), (15, 6))  # R6
    if v == 0:
        c.R((15, 6), (15, 0), "right")               # R7 rung
        c.R((15, 0), (10, 0), "bottom")              # R8
        # shorted resistor on bottom rail between rungs, bypass wire below it
        c.R((10, 0), (5, 0), "top", kind="shorted")
        c.W((10, 0), (10, -2.2), (5, -2.2), (5, 0))
        c.R((5, 0), (0, 0), "bottom")
        c.notes.append("shorted resistor on bottom rail (bypass wire)")
    elif v == 1:
        c.R((15, 6), (15, 0), "right")               # R7 rung
        # dead-end resistor off the R5/R6 node to open terminal C
        c.W((15, 6), (19, 6))
        c.R((19, 6), (24, 6), "top", kind="deadend")
        c.open_terms["C"] = (24, 6)
        c.R((15, 0), (10, 0), "bottom")              # R8
        c.W((10, 0), (5, 0))
        c.R((5, 0), (0, 0), "bottom")
        c.notes.append("dead-end resistor to unconnected terminal C")
    else:
        c.R((15, 6), (15, 0), "right")               # R7 rung, shorted by wire rung at x=21
        c.W((15, 6), (21, 6), (21, 0), (15, 0))
        c.R((15, 0), (10, 0), "bottom")              # R8
        c.R((10, 0), (5, 0), "bottom")               # extra bottom resistor
        c.R((5, 0), (0, 0), "bottom")
        for r in c.res:
            if r["p"] == (15, 6) and r["q"] == (15, 0):
                r["kind"] = "shorted"
        c.notes.append("far rung R shorted by a plain wire rung drawn beside it")
    return c


# ---------------- electrical analysis ----------------
def electrical(c):
    pts = set()
    for r in c.res: pts |= {r["p"], r["q"]}
    for a, b in c.wires: pts |= {a, b}
    pts |= set(c.terms.values()) | set(c.open_terms.values())
    parent = {p: p for p in pts}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for a, b in c.wires:
        parent[find(a)] = find(b)
    roots = sorted({find(p) for p in pts})
    idx = {r: i for i, r in enumerate(roots)}
    node = lambda p: idx[find(p)]
    edges = [(node(r["p"]), node(r["q"]), r["val"]) for r in c.res]
    return len(roots), edges, node(c.terms["A"]), node(c.terms["B"])


def sp_reduce(n, edges, a, b):
    E = [(u, v, Fraction(r)) for u, v, r in edges]
    changed = True
    while changed:
        changed = False
        E = [e for e in E if e[0] != e[1]]  # self loops = shorted, drop
        # dead ends
        deg = {}
        for u, v, _ in E:
            deg[u] = deg.get(u, 0) + 1; deg[v] = deg.get(v, 0) + 1
        dead = [x for x, d in deg.items() if d == 1 and x not in (a, b)]
        if dead:
            E = [e for e in E if e[0] not in dead and e[1] not in dead]; changed = True; continue
        # parallel
        groups = {}
        for u, v, r in E:
            groups.setdefault(tuple(sorted((u, v))), []).append(r)
        if any(len(g) > 1 for g in groups.values()):
            E = [(k[0], k[1], 1 / sum(1 / r for r in g)) for k, g in groups.items()]
            changed = True; continue
        # series
        for x, d in deg.items():
            if d == 2 and x not in (a, b):
                inc = [e for e in E if x in e[:2]]
                o = [e[1] if e[0] == x else e[0] for e in inc]
                E = [e for e in E if e not in inc] + [(o[0], o[1], inc[0][2] + inc[1][2])]
                changed = True; break
    assert len(E) == 1 and set(E[0][:2]) == {a, b}, E
    return float(E[0][2])


def nodal(n, edges, a, b):
    G = np.zeros((n, n))
    for u, v, r in edges:
        if u == v: continue
        g = 1.0 / r
        G[u, u] += g; G[v, v] += g; G[u, v] -= g; G[v, u] -= g
    I = np.zeros(n); I[a] = 1.0
    keep = [i for i in range(n) if i != b]
    Gr = G[np.ix_(keep, keep)]
    # floating subnetworks (none expected beyond dead ends connected by one R)
    V = np.linalg.lstsq(Gr, I[keep], rcond=None)[0]
    return float(V[keep.index(a)])


# ---------------- rendering ----------------
def render(c, path):
    d = schemdraw.Drawing(show=False)
    d.config(fontsize=15, lw=1.8, unit=3)
    for r in c.res:
        d.add(elm.Resistor().endpoints(r["p"], r["q"]))
    for a, b in c.wires:
        d.add(elm.Line().endpoints(a, b))
    # junction dots where >=3 segment ends meet
    cnt = {}
    for r in c.res:
        for p in (r["p"], r["q"]): cnt[p] = cnt.get(p, 0) + 1
    for a, b in c.wires:
        for p in (a, b): cnt[p] = cnt.get(p, 0) + 1
    for p, k in cnt.items():
        if k >= 3 and p not in c.terms.values():
            d.add(elm.Dot(radius=0.12).at(p))
    for name, p in list(c.terms.items()) + list(c.open_terms.items()):
        loc = "left"
        if p[0] > 0: loc = "right"
        d.add(elm.Dot(open=True, radius=0.18).at(p).label(name, loc=loc, fontsize=20, ofst=0.25))
    for r in c.res:
        (x1, y1), (x2, y2) = r["p"], r["q"]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        side = r["side"]
        if side == "top": pos, ha, va = (mx, my + 0.55), "center", "bottom"
        elif side == "bottom": pos, ha, va = (mx, my - 0.55), "center", "top"
        elif side == "right": pos, ha, va = (mx + 0.6, my), "left", "center"
        else: pos, ha, va = (mx - 0.6, my), "right", "center"
        d.add(elm.Label().at(pos).label(r["text"], halign=ha, valign=va, fontsize=15))
    tmp = path + ".raw.png"
    d.save(tmp, dpi=170)
    im = Image.open(tmp).convert("RGB")
    W, H = 1400, 1000
    s = min((W - 80) / im.width, (H - 80) / im.height)
    im2 = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    canvas = Image.new("RGB", (W, H), "white")
    canvas.paste(im2, ((W - im2.width) // 2, (H - im2.height) // 2))
    canvas.save(path)
    import os; os.remove(tmp)
    return s


def build(level, seed):
    rng = random.Random(1000 * level + seed)
    c = {1: L1, 2: L2, 3: L3}[level](seed)
    for i, r in enumerate(c.res, 1):
        r["val"] = rng.choice(VALUES)
        r["name"] = f"R{i}"
        r["text"] = f"R{i} = {r['val']} Ω"
    n, edges, a, b = electrical(c)
    sp = sp_reduce(n, edges, a, b)
    na = nodal(n, edges, a, b)
    assert abs(sp - na) < 1e-6 * max(1, sp), (sp, na)
    tid = f"L{level}_s{seed}"
    path = f"img/{tid}.png"
    scale = render(c, path)
    return dict(id=tid, level=level, seed=seed, image=path, answer=round(sp, 1),
                answer_exact=sp, nodal=na, n_resistors=len(c.res),
                resistors=[dict(name=r["name"], val=r["val"], kind=r["kind"],
                                p=r["p"], q=r["q"]) for r in c.res],
                notes=c.notes, downscale=scale)


if __name__ == "__main__":
    tasks = [build(L, s) for L in (1, 2, 3) for s in range(3)]
    json.dump(tasks, open("tasks.json", "w"), indent=1)
    for t in tasks:
        print(t["id"], t["n_resistors"], t["answer"], f"nodal={t['nodal']:.4f}", t["notes"], f"scale={t['downscale']:.2f}")
