"""Spike F: subway map (NYC / Vignelli-1972-style schematic of an invented city).

Data first (tasks/data/<id>.json), PNG rendered from that data only, answer computed from that data by
0-1 BFS over (station, line) states. 3 levels x 3 seeds = 9 tasks, written in contracts/SCHEMA.md format.

    uv run python results/spikes/subway/gen.py
"""
import json
import os
from collections import deque

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe

VERSION = "subway-spike-0.1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "tasks")
CITY = "Port Calder"
REFERENCES = ["Massimo Vignelli, New York City Subway Diagram (1972)",
              "MTA New York City Subway map conventions (route bullets, transfer circles, service notices)"]

# (route name, line color, bullet text color): MTA-style trunk colors
ROUTES = [("A", "#0039A6", "white"), ("1", "#EE352E", "white"), ("4", "#00933C", "white"),
          ("N", "#FCCC0A", "black"), ("7", "#B933AD", "white"), ("L", "#7C858C", "white"),
          ("J", "#996633", "white"), ("G", "#6CBE45", "white")]

PREFIXES = ["Harbor", "Calder", "Mercer", "Foundry", "Kestrel", "Linden", "Bellamy", "Tillman", "Orchard",
            "Granary", "Quarry", "Beacon", "Garnet", "Hollis", "Ironworks", "Sutter", "Clement", "Brightwater",
            "Saltmarsh", "Weirfield", "Knox", "Arden", "Copper", "Lantern", "Marlow", "Pembrook", "Ashby",
            "Thornton", "Willet", "Hadley", "Ferris", "Corbin", "Easton", "Fairmount", "Greystone", "Juniper",
            "Larkin", "Norwood", "Oakmont", "Rowan", "Stanton", "Vesey", "Whitlock", "Yardley", "Alder",
            "Birch", "Crane", "Dunmore", "Elwood", "Fenwick", "Gilman", "Halstead", "Inwood", "Jessup",
            "Kimball", "Lowell", "Maddox", "Newbury", "Osgood", "Prescott", "Quincy", "Radley", "Selden",
            "Tremont", "Upton", "Vance", "Warwick", "Ainsley", "Bramble", "Colton", "Dorset", "Emery"]
SUFFIXES = ["St", "Av", "Sq", "Blvd", "Rd", "Park", "Pl", "Hts", "Jct", "Pkwy"]
NUMBERED = ([f"{n} St" for n in (9, 14, 23, 31, 38, 47, 53, 61, 68, 74, 82, 91, 104, 117, 128, 139, 152, 163)]
            + [f"Av {c}" for c in "BCDHJMPU"] + [f"{n} Av" for n in (2, 3, 5, 7, 8, 11)])
SPECIAL = ["Ferry Terminal", "Union Station", "Civic Center", "Stadium", "Medical Center", "Courthouse",
           "Convention Ctr", "University"]

LEVELS = {
    "L1": dict(n_lines=3, W=12, H=8, seeds=[101, 102, 103], qtype="subway.fewest_stops"),
    "L2": dict(n_lines=5, W=14, H=10, seeds=[201, 202, 203], qtype="subway.fewest_transfers"),
    "L3": dict(n_lines=7, W=16, H=11, seeds=[301, 302, 303], qtype="subway.fewest_stops_closure"),
}
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]


# ---------------------------------------------------------------- data
def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def walk(rng, points, W, H, used_edges, occupied_ends):
    """Octilinear route through the given points, one station per grid step, no reused edges."""
    path = [points[0]]
    d = None
    for tgt in points[1:]:
        cur = path[-1]
        while cur != tgt:
            dist = cheb(cur, tgt)
            cands = []
            for mv in DIRS:
                nxt = (cur[0] + mv[0], cur[1] + mv[1])
                if not (0 <= nxt[0] < W and 0 <= nxt[1] < H) or cheb(nxt, tgt) >= dist:
                    continue
                if nxt in path or frozenset((cur, nxt)) in used_edges or nxt in occupied_ends:
                    continue
                if d is not None and mv[0] * d[0] + mv[1] * d[1] < 0:  # no turn sharper than 90 degrees
                    continue
                if mv[0] and mv[1]:  # a diagonal must not cross this line's own other diagonal
                    a_, b_ = (cur[0], nxt[1]), (nxt[0], cur[1])
                    own = set(zip(path, path[1:]))
                    if (a_, b_) in own or (b_, a_) in own:
                        continue
                cands.append(mv)
            if not cands:
                return None
            mv = d if (d in cands and rng.random() < 0.75) else cands[int(rng.integers(len(cands)))]
            d = mv
            cur = (cur[0] + mv[0], cur[1] + mv[1])
            path.append(cur)
    return path


def border_point(rng, side, W, H):
    if side == 0:
        return (0, int(rng.integers(1, H - 1)))
    if side == 1:
        return (W - 1, int(rng.integers(1, H - 1)))
    if side == 2:
        return (int(rng.integers(1, W - 1)), 0)
    return (int(rng.integers(1, W - 1)), H - 1)


def make_map(rng, n_lines, W, H):
    for _ in range(500):
        lines, used_edges, ends, on_map = [], set(), set(), set()
        ok = True
        for k in range(n_lines):
            for _try in range(300):
                side = int(rng.integers(4))
                a = border_point(rng, side, W, H)
                b = border_point(rng, side ^ 1, W, H)  # opposite side
                if a in on_map or b in on_map or cheb(a, b) < W // 2:
                    continue
                if any(cheb(a, e) < 2 or cheb(b, e) < 2 for e in ends):  # route bullets must not collide
                    continue
                pts = [a]
                if lines:  # pass through an existing station: the network is connected
                    pool = sorted(on_map - ends)
                    pts.append(pool[int(rng.integers(len(pool)))])
                pts.append(b)
                path = walk(rng, pts, W, H, used_edges, ends)
                if path and len(path) >= 7:
                    break
            else:
                ok = False
                break
            lines.append(path)
            used_edges |= {frozenset(e) for e in zip(path, path[1:])}
            ends |= {path[0], path[-1]}
            on_map |= set(path)
        if ok:
            return lines
    raise RuntimeError("could not build a map")


def name_stations(rng, coords):
    pool = [f"{p} {SUFFIXES[int(rng.integers(len(SUFFIXES)))]}" for p in PREFIXES] + NUMBERED + SPECIAL
    order = rng.permutation(len(pool))
    assert len(pool) >= len(coords), "station name pool too small"
    return {c: pool[i] for c, i in zip(sorted(coords), order)}


def solve(data, a, b, metric, closed=None):
    """0-1 BFS over (station, line). metric 'stops': ride=1, change=0; 'transfers': ride=0, change=1.
    A closed station can be ridden through but not changed at."""
    lines = {ln["name"]: ln["stations"] for ln in data["lines"]}
    at = {}
    for name, sts in lines.items():
        for s in sts:
            at.setdefault(s, []).append(name)
    ride, change = (1, 0) if metric == "stops" else (0, 1)
    dist = {}
    dq = deque()
    for ln in at[a]:
        dist[(a, ln)] = 0
        dq.append((a, ln))
    while dq:
        s, ln = dq.popleft()
        d0 = dist[(s, ln)]
        sts = lines[ln]
        i = sts.index(s)
        moves = [((sts[j], ln), ride) for j in (i - 1, i + 1) if 0 <= j < len(sts)]
        if s != closed:
            moves += [((s, other), change) for other in at[s] if other != ln]
        for st, w in moves:
            if st not in dist or d0 + w < dist[st]:
                dist[st] = d0 + w
                (dq.appendleft if w == 0 else dq.append)(st)
    best = [dist[(b, ln)] for ln in at[b] if (b, ln) in dist]
    return min(best) if best else None


def build(level, seed):
    cfg = LEVELS[level]
    rng = np.random.default_rng(seed)
    paths = make_map(rng, cfg["n_lines"], cfg["W"], cfg["H"])
    coords = {c for p in paths for c in p}
    names = name_stations(rng, coords)
    routes = [ROUTES[i] for i in sorted(rng.choice(len(ROUTES), cfg["n_lines"], replace=False))]
    data = {
        "city": CITY, "grid": [cfg["W"], cfg["H"]],
        "lines": [{"name": r[0], "color": r[1], "bullet_text": r[2],
                   "stations": [names[c] for c in p], "coords": [list(c) for c in p]}
                  for r, p in zip(routes, paths)],
        "closed": None,
    }
    count = {}
    for ln in data["lines"]:
        for s in ln["stations"]:
            count[s] = count.get(s, 0) + 1
    transfers = sorted(s for s, n in count.items() if n > 1)
    plain = sorted(s for s, n in count.items() if n == 1)
    line_of = {s: ln["name"] for ln in data["lines"] for s in ln["stations"] if count[s] == 1}
    pairs = [(a, b) for i, a in enumerate(plain) for b in plain[i + 1:] if line_of[a] != line_of[b]]
    pairs = [pairs[i] for i in rng.permutation(len(pairs))]

    if level == "L1":
        scored = [(solve(data, a, b, "stops"), a, b) for a, b in pairs]
        top = max(s for s, _, _ in scored)
        cand = [x for x in scored if x[0] >= top - 2]
        ans, a, b = cand[0]
        q = (f"This is the {CITY} subway map. What is the fewest number of stops needed to travel from {a} to "
             f"{b}? Count each station the train arrives at after leaving {a}, including {b}. Changing lines at a "
             f"transfer station (white circle) does not add a stop. Answer with a single integer.")
        extra = {}
    elif level == "L2":
        scored = [(solve(data, a, b, "transfers"), a, b) for a, b in pairs]
        top = max(s for s, _, _ in scored)
        ans, a, b = next(x for x in scored if x[0] == top)
        q = (f"This is the {CITY} subway map. What is the fewest number of times you must change trains to "
             f"travel from {a} to {b}? You can only change trains at transfer stations (white circles); the "
             f"number of stops does not matter. Answer with a single integer.")
        extra = {}
    else:
        # The closure must change the answer (by >= 3 stops) but keep the detour short enough that a careful
        # person can count it in 2 to 3 minutes (<= 14 stops).
        good, fallback = [], None
        for a, b in pairs:
            d0 = solve(data, a, b, "stops")
            for x in transfers:
                d1 = solve(data, a, b, "stops", closed=x)
                if d1 is None or d1 - d0 < 2:
                    continue
                if d1 - d0 >= 3 and d1 <= 14:
                    good.append((a, b, x, d0, d1))
                if fallback is None or (d1 - d0, -d1) > fallback[0]:
                    fallback = ((d1 - d0, -d1), a, b, x, d0, d1)
        if good:
            a, b, x, d0, ans = good[int(rng.integers(len(good)))]
        elif fallback:
            _, a, b, x, d0, ans = fallback
        else:
            raise RuntimeError("no closure changes any route")
        data["closed"] = x
        q = (f"This is the {CITY} subway map. Read the service notice on the map and take it into account. What "
             f"is the fewest number of stops needed to travel from {a} to {b}? Count each station the train "
             f"arrives at or runs through after leaving {a}, including {b} and any closed station it runs "
             f"through. Changing lines at an open transfer station (white circle) does not add a stop. Answer "
             f"with a single integer.")
        extra = {"answer_without_closure": d0}
    task_id = f"subway-{seed:06d}"
    params = {"level": level, "n_lines": cfg["n_lines"], "grid": [cfg["W"], cfg["H"]],
              "n_stations": len(count), "n_transfer_stations": len(transfers)}
    record = {"task_id": task_id, "family": "subway", "seed": seed, "generator_version": VERSION,
              "params": params, "data": data, "references": REFERENCES,
              "question": {"type": cfg["qtype"], "from": a, "to": b, "text": q, "answer": ans, **extra}}
    return record


# ---------------------------------------------------------------- render
def render(record, path, notice=None, run_times=None):
    """notice: custom notice text (default: the closed-station notice). run_times: [(route, color, text color,
    minutes)] drawn as a running-time table in the footer."""
    data = record["data"]
    W, H = data["grid"]
    fig = plt.figure(figsize=(W * 0.95 + 1.2, H * 0.95 + 2.6), dpi=110)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0.02, 0.13, 0.96, 0.76])
    ax.set_xlim(-1.1, W + 0.1)
    ax.set_ylim(H + 0.1, -1.1)
    ax.set_aspect("equal")
    ax.axis("off")

    # header bar, MTA style
    fig.add_artist(plt.Rectangle((0, 0.93), 1, 0.07, transform=fig.transFigure, color="black"))
    fig.text(0.02, 0.965, f"{data['city']} Transit", color="white", fontsize=17, weight="bold", va="center")
    fig.text(0.98, 0.965, "Subway Service Map", color="white", fontsize=12, va="center", ha="right")

    count = {}
    for ln in data["lines"]:
        for s in ln["stations"]:
            count[s] = count.get(s, 0) + 1
    pos = {s: c for ln in data["lines"] for s, c in zip(ln["stations"], ln["coords"])}

    seg_pts = []
    for ln in data["lines"]:
        xs, ys = zip(*ln["coords"])
        ax.plot(xs, ys, color=ln["color"], lw=6.5, solid_capstyle="round", solid_joinstyle="round", zorder=2)
    for s, (x, y) in pos.items():
        if count[s] == 1:
            ax.plot(x, y, "o", ms=4.6, color="black", zorder=4)
        else:
            ax.plot(x, y, "o", ms=12, mfc="white", mec="black", mew=2.2, zorder=5)
    # route bullets beyond each terminus
    bullets = []
    for ln in data["lines"]:
        c = ln["coords"]
        for end, prev in ((c[0], c[1]), (c[-1], c[-2])):
            dx, dy = end[0] - prev[0], end[1] - prev[1]
            n = max(abs(dx), abs(dy))
            bx, by = end[0] + 0.62 * dx / n, end[1] + 0.62 * dy / n
            ax.add_patch(plt.Circle((bx, by), 0.27, color=ln["color"], zorder=6))
            ax.text(bx, by, ln["name"], color=ln["bullet_text"], fontsize=10, weight="bold", ha="center",
                    va="center", zorder=7)
            bullets.append((bx, by))

    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    T = ax.transData
    for ln in data["lines"]:
        for p, q in zip(ln["coords"], ln["coords"][1:]):
            a, b = T.transform(p), T.transform(q)
            k = max(2, int(np.hypot(*(b - a)) / 3))
            seg_pts.append(np.linspace(a, b, k))
    seg_pts = np.vstack(seg_pts)
    blocks = []  # display-space boxes: station markers and bullets
    r = 9
    rb = (T.transform((0.32, 0)) - T.transform((0, 0)))[0]
    for x, y in pos.values():
        px, py = T.transform((x, y))
        blocks.append((px - r, py - r, px + r, py + r))
    bullet_blocks = []
    for x, y in bullets:
        px, py = T.transform((x, y))
        bullet_blocks.append((px - rb, py - rb, px + rb, py + rb))
    axbox = ax.get_window_extent(rend)

    cands = [(9, 0, "left", "center"), (-9, 0, "right", "center"), (0, 9, "center", "bottom"),
             (0, -9, "center", "top"), (7, 7, "left", "bottom"), (-7, 7, "right", "bottom"),
             (7, -7, "left", "top"), (-7, -7, "right", "top")]
    placed = []
    halo = [pe.withStroke(linewidth=3, foreground="white")]

    def inter(b1, b2):
        return b1[0] < b2[2] and b2[0] < b1[2] and b1[1] < b2[3] and b2[1] < b1[3]

    order = sorted(pos, key=lambda s: (-count[s], s))
    for s in order:
        best = None
        for i, (dx, dy, ha, va) in enumerate(cands):
            t = ax.annotate(s, pos[s], xytext=(dx, dy), textcoords="offset points", ha=ha, va=va,
                            fontsize=7.6, weight="bold" if count[s] > 1 else "normal", zorder=8)
            bb = t.get_window_extent(rend)
            t.remove()
            box = (bb.x0 - 1, bb.y0 - 1, bb.x1 + 1, bb.y1 + 1)
            sc = i * 0.5
            sc += 1000 * sum(inter(box, p) for p in placed)
            mine = T.transform(pos[s])
            sc += 300 * sum(inter(box, blk) for blk in blocks
                            if not (abs((blk[0] + r) - mine[0]) < 1 and abs((blk[1] + r) - mine[1]) < 1))
            sc += 1000 * sum(inter(box, blk) for blk in bullet_blocks)
            inside = ((seg_pts[:, 0] > box[0]) & (seg_pts[:, 0] < box[2]) &
                      (seg_pts[:, 1] > box[1]) & (seg_pts[:, 1] < box[3])).sum()
            sc += 25 * inside
            if box[0] < axbox.x0 or box[2] > axbox.x1 or box[1] < axbox.y0 or box[3] > axbox.y1:
                sc += 2000
            if best is None or sc < best[0]:
                best = (sc, i, box)
        dx, dy, ha, va = cands[best[1]]
        ax.annotate(s, pos[s], xytext=(dx, dy), textcoords="offset points", ha=ha, va=va, fontsize=7.6,
                    weight="bold" if count[s] > 1 else "normal", zorder=8, path_effects=halo)
        placed.append(best[2])

    # legend + notice
    lx = 0.03
    fig.text(lx, 0.085, "●", fontsize=9, va="center")
    fig.text(lx + 0.02, 0.085, "Station", fontsize=9, va="center")
    fig.text(lx, 0.05, "○", fontsize=14, va="center", weight="bold")
    fig.text(lx + 0.02, 0.05, "Transfer station: change between all lines that stop here",
             fontsize=9, va="center")
    fig.text(lx, 0.018, "Trains stop at every station on their line. All lines run in both directions.",
             fontsize=8, va="center", color="#333333")
    if notice is None and data["closed"]:
        x = data["closed"]
        notice = (f"SERVICE NOTICE\n{x} station is closed.\nTrains run through {x} without stopping.\n"
                  f"No transfers between lines at {x}.")
    if notice:
        fig.text(0.97, 0.06, notice, fontsize=9, ha="right", va="center",
                 bbox=dict(boxstyle="square,pad=0.6", fc="#FFF3B0", ec="black", lw=1.4), linespacing=1.4)
    if run_times:
        tx = 0.36
        fig.text(tx, 0.10, "Running time between adjacent stations", fontsize=9, weight="bold", va="center")
        for k, (name, color, tc, mins) in enumerate(run_times):
            x0 = tx + k * 0.05
            fig.text(x0 + 0.008, 0.055, name, color=tc, fontsize=9, weight="bold", ha="center", va="center",
                     bbox=dict(boxstyle="circle,pad=0.3", fc=color, ec=color))
            fig.text(x0 + 0.02, 0.055, f"{mins} min", fontsize=9, va="center")
    fig.savefig(path, dpi=110, metadata={"Software": None}, facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------- main
def main():
    os.makedirs(os.path.join(OUT, "images"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
    rows = []
    for level, cfg in LEVELS.items():
        for seed in cfg["seeds"]:
            rec = build(level, seed)
            tid = rec["task_id"]
            with open(os.path.join(OUT, "data", f"{tid}.json"), "w", encoding="utf-8") as f:
                json.dump(rec, f, indent=1)   # data saved before rendering
            render(rec, os.path.join(OUT, "images", f"{tid}.png"))
            q = rec["question"]
            rows.append({"task_id": tid, "image": f"images/{tid}.png", "question": q["text"],
                         "answer": q["answer"], "answer_type": "integer", "seed": rec["seed"],
                         "generator_version": VERSION, "question_type": q["type"], "family": "subway",
                         "difficulty": level, "data": f"data/{tid}.json", "references": REFERENCES})
            print(tid, level, q["type"], q["from"], "->", q["to"], "closed:", rec["data"]["closed"],
                  "answer:", q["answer"], q.get("answer_without_closure", ""), rec["params"])
    with open(os.path.join(OUT, "tasks.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


if __name__ == "__main__":
    main()
