"""Spike G: topographic map tasks (USGS 7.5-minute quadrangle look).

    uv run python results/spikes/topo/gen.py

Data first: an elevation field (a tilted plane plus Gaussian hills), marked points, trails, streams and
label positions are sampled from the seed and saved to tasks/data/<task_id>.json. The PNG is drawn only
from that data. Every answer is computed from the data in code, and recomputed a second, independent
way (the `checks` field of tasks.jsonl); a sample whose two answers disagree is thrown away.

Levels: L1 which of two marked points is higher · L2 elevation of a point lying on a contour ·
L3 how many contour lines a trail crosses between its two marked ends.
"""
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from contourpy import contour_generator

HERE = Path(__file__).resolve().parent
OUT = HERE / "tasks"
VERSION = "topo-spike-0.1"
W, H, STEP = 4000.0, 3000.0, 10.0          # map size and grid spacing, meters
CI, INDEX = 20, 100                         # contour interval and index-contour interval, meters
REFERENCES = ["USGS 7.5-minute topographic quadrangle maps (1:24 000, brown contours, bold index contours)",
              "USGS Topographic Map Symbols booklet (contours, spot elevations, trails, streams)"]
QUADS = ["Harlan Ridge", "Coldwater Peak", "Juniper Flat", "Tamarack Butte", "Saddle Mountain", "Elk Hollow",
         "Granite Knob", "Marble Fork", "Antelope Spring"]
PEAKS = ["Coldwater Pk", "Granite Knob", "Bald Mtn", "Lookout Pt", "Eagle Rock", "Signal Hill", "Pine Butte"]
TRAILS = ["Ridge Trail", "Miners Trail", "Lookout Trail", "Aspen Trail", "Summit Trail", "Cedar Trail"]
STREAMS = ["Mill Creek", "Cold Brook", "Wolf Creek", "Dry Fork"]
MAGENTA, BROWN, BROWN_INDEX, BLUE, GREEN = "#c2188f", "#b9793f", "#9a5a22", "#2b7bbb", "#e9f2dc"


# ---------------------------------------------------------------------------------------------- the terrain
def elev(d, x, y):
    """Elevation in meters at (x, y): the analytic field, straight from the data."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    z = d["base"]["z0"] + d["base"]["gx"] * x + d["base"]["gy"] * y
    for h in d["hills"]:
        c, s = math.cos(h["rot"]), math.sin(h["rot"])
        dx, dy = x - h["x"], y - h["y"]
        u, v = c * dx + s * dy, -s * dx + c * dy
        z = z + h["h"] * np.exp(-(u * u / (2 * h["sx"] ** 2) + v * v / (2 * h["sy"] ** 2)))
    return z


def grid(d):
    xs, ys = np.arange(0, W + 1, STEP), np.arange(0, H + 1, STEP)
    X, Y = np.meshgrid(xs, ys)
    return X, Y, elev(d, X, Y)


def gradient(d, x, y, e=1.0):
    return np.array([(elev(d, x + e, y) - elev(d, x - e, y)) / (2 * e),
                     (elev(d, x, y + e) - elev(d, x, y - e)) / (2 * e)])


def dist_to_poly(p, pts):
    p, pts = np.asarray(p, float), np.asarray(pts, float)
    a, b = pts[:-1], pts[1:]
    ab = b - a
    t = np.clip(((p - a) * ab).sum(1) / np.maximum((ab * ab).sum(1), 1e-9), 0, 1)
    return float(np.sqrt((((a + t[:, None] * ab) - p) ** 2).sum(1)).min())


def densify(pts, ds=1.0):
    pts = np.asarray(pts, float)
    out = [pts[:1]]
    for a, b in zip(pts[:-1], pts[1:]):
        n = max(2, int(math.ceil(np.linalg.norm(b - a) / ds)) + 1)
        out.append(a + (b - a) * np.linspace(0, 1, n)[1:, None])
    return np.vstack(out)


# ---------------------------------------------------------------------------------------------- solvers
def crossings_by_sampling(d, pts):
    """Answer 1 for L3: walk the trail in 1 m steps over the analytic field, count contour-level changes."""
    p = densify(pts)
    band = np.floor(elev(d, p[:, 0], p[:, 1]) / CI)
    return int(np.abs(np.diff(band)).sum())


def crossings_by_geometry(d, pts, lines_by_level):
    """Answer 2 for L3: intersect the trail's straight legs with the contour polylines traced from the grid."""
    pts = np.asarray(pts, float)
    total = 0
    for lines in lines_by_level.values():
        for line in lines:
            a, b = line[:-1], line[1:]
            for p, q in zip(pts[:-1], pts[1:]):
                r, s = q - p, b - a
                den = r[0] * s[:, 1] - r[1] * s[:, 0]
                ok = np.abs(den) > 1e-12
                t = np.where(ok, ((a[:, 0] - p[0]) * s[:, 1] - (a[:, 1] - p[1]) * s[:, 0]) / np.where(ok, den, 1), -1)
                u = np.where(ok, ((a[:, 0] - p[0]) * r[1] - (a[:, 1] - p[1]) * r[0]) / np.where(ok, den, 1), -1)
                total += int(((t >= 0) & (t < 1) & (u >= 0) & (u < 1)).sum())
    return total


def trail_is_fair(d, pts):
    """No grazing: the trail never turns around within 5 m (vertically) of a contour, crossings are at
    least 25 m apart along the trail, and it never crosses a contour at a shallow angle."""
    p = densify(pts)
    z = elev(d, p[:, 0], p[:, 1])
    dz = np.diff(z)
    turn = np.where(np.sign(dz[1:]) != np.sign(dz[:-1]))[0] + 1
    for i in list(turn) + [0, len(z) - 1]:
        if abs(((z[i] + CI / 2) % CI) - CI / 2) < 5.0:
            return False
    cross = np.where(np.diff(np.floor(z / CI)) != 0)[0]
    if len(cross) > 1 and np.diff(cross).min() < 25:
        return False
    for i in cross:
        lo, hi = max(0, i - 5), min(len(z) - 1, i + 5)
        if abs(z[hi] - z[lo]) / (hi - lo) < 0.04:
            return False
    return True


# ---------------------------------------------------------------------------------------------- sampling
def inside(p, m):
    return m <= p[0] <= W - m and m <= p[1] <= H - m


def random_trail(rng, legs, margin=260):
    for _ in range(200):
        p = np.array([rng.uniform(margin, W - margin), rng.uniform(margin, H - margin)])
        heading, pts = rng.uniform(0, 2 * math.pi), [p]
        for _ in range(legs):
            heading += rng.uniform(-1.1, 1.1)
            p = p + rng.uniform(450, 1000) * np.array([math.cos(heading), math.sin(heading)])
            pts.append(p)
        if all(inside(q, margin) for q in pts):
            return [[round(float(q[0]), 1), round(float(q[1]), 1)] for q in pts]
    return None


def stream_from(d, start):
    p, pts = np.array(start, float), []
    for _ in range(400):
        if not inside(p, 0):
            break
        pts.append([round(float(p[0]), 1), round(float(p[1]), 1)])
        g = gradient(d, *p)
        n = np.linalg.norm(g)
        if n < 0.004:
            break
        p = p - 15 * g / n
    return pts


def contour_lines(Z):
    cg = contour_generator(x=np.arange(0, W + 1, STEP), y=np.arange(0, H + 1, STEP), z=Z)
    lo, hi = math.ceil(Z.min() / CI) * CI, math.floor(Z.max() / CI) * CI
    return {lv: [ln for ln in cg.lines(lv) if len(ln) > 1] for lv in range(int(lo), int(hi) + 1, CI)}


def sample(seed, level):
    """Structured data for one task, or None if this draw breaks a fairness rule (the caller retries)."""
    rng = np.random.default_rng(seed)
    for attempt in range(400):
        d = {"extent_m": [W, H], "contour_interval_m": CI, "index_interval_m": INDEX,
             "base": {"z0": round(float(rng.uniform(240, 420)), 1), "gx": round(float(rng.uniform(-0.02, 0.02)), 4),
                      "gy": round(float(rng.uniform(-0.02, 0.02)), 4)},
             "hills": [{"x": round(float(rng.uniform(300, W - 300)), 1), "y": round(float(rng.uniform(300, H - 300)), 1),
                        "h": round(float(rng.uniform(120, 360)), 1), "sx": round(float(rng.uniform(380, 800)), 1),
                        "sy": round(float(rng.uniform(380, 800)), 1), "rot": round(float(rng.uniform(0, math.pi)), 3)}
                       for _ in range(int(rng.integers(5, 8)))],
             "quad": str(rng.choice(QUADS)), "points": [], "trails": [], "attempt": attempt}
        X, Y, Z = grid(d)
        lines = contour_lines(Z)
        names = list(rng.permutation(TRAILS))

        if level == 3:
            pts = random_trail(rng, legs=int(rng.integers(2, 4)))
            if pts is None or not trail_is_fair(d, pts):
                continue
            n1, n2 = crossings_by_sampling(d, pts), crossings_by_geometry(d, pts, lines)
            if n1 != n2 or not 8 <= n1 <= 20:
                continue
            d["trails"].append({"name": str(names[0]), "pts": pts, "asked": True})
            def away(a, b):       # label offset: 95 m from end a, pointing away from the trail's next vertex b
                v = np.array(a) - np.array(b)
                v = 95 * v / np.linalg.norm(v)
                return {"label_dx": round(float(v[0]), 1), "label_dy": round(float(v[1]), 1)}
            d["points"] = [{"name": "S", "x": pts[0][0], "y": pts[0][1], "shape": "square", **away(pts[0], pts[1])},
                           {"name": "E", "x": pts[-1][0], "y": pts[-1][1], "shape": "square", **away(pts[-1], pts[-2])}]
            answer, checks = n1, {"sampled_field_equals_contour_geometry": n1 == n2, "trail_not_grazing_a_contour": True}
        elif level == 2:
            cands = [lv for lv in lines if lv % INDEX != 0 and any(len(ln) > 60 for ln in lines[lv])]
            if not cands:
                continue
            lv = int(rng.choice(cands))
            ln = [l for l in lines[lv] if len(l) > 60][int(rng.integers(0, sum(len(l) > 60 for l in lines[lv])))]
            p = ln[int(rng.integers(5, len(ln) - 5))].astype(float)
            for _ in range(3):                                     # slide onto the exact analytic contour
                g = gradient(d, *p)
                p = p - (float(elev(d, *p)) - lv) * g / max(float(g @ g), 1e-9)
            slope = float(np.linalg.norm(gradient(d, *p)))
            if not inside(p, 300) or not 0.08 <= slope <= 0.42:     # neighbours 48 to 250 m away: easy to tell apart
                continue
            d["points"] = [{"name": "P", "x": round(float(p[0]), 1), "y": round(float(p[1]), 1), "shape": "dot"}]
            z = float(elev(d, d["points"][0]["x"], d["points"][0]["y"]))
            nearest = int(round(z / CI) * CI)
            if nearest != lv or abs(z - lv) > 1.0:
                continue
            answer, checks = lv, {"field_at_P_within_1m_of_contour": abs(z - lv) <= 1.0, "nearest_contour_equals_answer": nearest == lv}
        else:
            a = np.array([rng.uniform(350, W - 350), rng.uniform(350, H - 350)])
            b = np.array([rng.uniform(350, W - 350), rng.uniform(350, H - 350)])
            za, zb = float(elev(d, *a)), float(elev(d, *b))
            if np.linalg.norm(a - b) < 1200 or not 40 <= abs(za - zb) <= 140:
                continue
            d["points"] = [{"name": "A", "x": round(float(a[0]), 1), "y": round(float(a[1]), 1), "shape": "dot"},
                           {"name": "B", "x": round(float(b[0]), 1), "y": round(float(b[1]), 1), "shape": "dot"}]
            answer = "A" if za > zb else "B"
            ia = Z[int(round(a[1] / STEP)), int(round(a[0] / STEP))]   # second way: nearest grid sample
            ib = Z[int(round(b[1] / STEP)), int(round(b[0] / STEP))]
            checks = {"grid_sample_agrees_with_field": ("A" if ia > ib else "B") == answer,
                      "gap_at_least_two_contour_intervals": abs(za - zb) >= 2 * CI}
        if not all(checks.values()):
            continue

        marks = [[p["x"], p["y"]] for p in d["points"]]
        asked = [t["pts"] for t in d["trails"]]

        def clear(q, r):          # is q at least r meters from every marked point and from the asked trail?
            return all(math.dist(q, m) >= r for m in marks) and all(dist_to_poly(q, t) >= r for t in asked)

        peak =(Z[1:-1, 1:-1] > Z[:-2, 1:-1]) & (Z[1:-1, 1:-1] > Z[2:, 1:-1]) & (Z[1:-1, 1:-1] > Z[1:-1, :-2]) & \
               (Z[1:-1, 1:-1] > Z[1:-1, 2:]) & (Z[1:-1, 1:-1] > Z[:-2, :-2]) & (Z[1:-1, 1:-1] > Z[2:, 2:]) & \
               (Z[1:-1, 1:-1] > Z[:-2, 2:]) & (Z[1:-1, 1:-1] > Z[2:, :-2])
        d["spot_heights"] = []
        for (j, i), name in zip(np.argwhere(peak), rng.permutation(PEAKS)):
            q = [float(X[j + 1, i + 1]), float(Y[j + 1, i + 1])]
            if inside(q, 200) and clear(q, 220):
                d["spot_heights"].append({"x": q[0], "y": q[1], "elev": int(round(float(Z[j + 1, i + 1]))), "name": str(name)})
        spots = [[sp["x"], sp["y"]] for sp in d["spot_heights"]]
        extra = random_trail(rng, legs=2)                              # a second trail, as on a real map
        if extra and all(clear(q, 250) and all(math.dist(q, o) >= 320 for o in spots) for q in densify(extra, 50)):
            d["trails"].append({"name": str(names[1]), "pts": extra, "asked": False})
        d["streams"] = []
        for h, name in zip(rng.permutation(len(d["hills"]))[:2], rng.permutation(STREAMS)):
            hill, ang = d["hills"][int(h)], rng.uniform(0, 2 * math.pi)
            s = stream_from(d, [hill["x"] + 2.2 * hill["sx"] * math.cos(ang), hill["y"] + 2.2 * hill["sy"] * math.sin(ang)])
            if len(s) > 25 and all(math.dist(q, o) >= 200 for q in s[::5] for o in spots + marks):
                d["streams"].append({"name": str(name), "pts": s})
        lines_drawn = [t["pts"] for t in d["trails"]] + [st["pts"] for st in d["streams"]]
        d["index_labels"] = []
        for lv in sorted(l for l in lines if l % INDEX == 0):
            for ln in lines[lv]:
                if len(ln) < 60:
                    continue
                for frac in (0.3, 0.72) if len(ln) > 260 else (0.5,):
                    k = int(frac * (len(ln) - 1))
                    q = [float(ln[k][0]), float(ln[k][1])]
                    tx, ty = ln[min(k + 4, len(ln) - 1)] - ln[max(k - 4, 0)]
                    ang = math.degrees(math.atan2(ty, tx))
                    ang = ang - 180 if ang > 90 else ang + 180 if ang < -90 else ang
                    others = [[s["x"], s["y"]] for s in d["spot_heights"]] + [[l["x"], l["y"]] for l in d["index_labels"]]
                    if inside(q, 160) and clear(q, 170) and all(math.dist(q, o) >= 260 for o in others) \
                            and all(dist_to_poly(q, ln2) >= 150 for ln2 in lines_drawn):
                        d["index_labels"].append({"x": round(q[0], 1), "y": round(q[1], 1), "level": int(lv), "angle": round(ang, 1)})
        if len(d["index_labels"]) < 3:
            continue
        return d, answer, checks
    return None


# ---------------------------------------------------------------------------------------------- drawing
def render(d, path):
    X, Y, Z = grid(d)
    fig = plt.figure(figsize=(10.4, 8.6), dpi=150)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0.07, 0.13, 0.86, 0.78])
    ax.set_facecolor(GREEN)
    lo, hi = math.ceil(Z.min() / CI) * CI, math.floor(Z.max() / CI) * CI
    levels = np.arange(lo, hi + 1, CI)
    ax.contour(X, Y, Z, levels=[l for l in levels if l % INDEX], colors=BROWN, linewidths=0.55)
    ax.contour(X, Y, Z, levels=[l for l in levels if l % INDEX == 0], colors=BROWN_INDEX, linewidths=1.3)
    for g in range(1000, int(W), 1000):
        ax.plot([g, g], [0, H], color="#444444", lw=0.3, alpha=0.6, zorder=1)
    for g in range(1000, int(H), 1000):
        ax.plot([0, W], [g, g], color="#444444", lw=0.3, alpha=0.6, zorder=1)
    for s in d["streams"]:
        p = np.array(s["pts"])
        ax.plot(p[:, 0], p[:, 1], color=BLUE, lw=1.1, zorder=3)
        k = len(p) // 2
        t = p[min(k + 3, len(p) - 1)] - p[max(k - 3, 0)]
        nrm = np.array([-t[1], t[0]]) / max(np.linalg.norm(t), 1e-9)
        ang = math.degrees(math.atan2(t[1], t[0]))
        ang = ang - 180 if ang > 90 else ang + 180 if ang < -90 else ang
        ax.text(*(p[k] + 65 * nrm), s["name"], color=BLUE, fontsize=6.5, style="italic", rotation=ang, ha="center",
                va="center", zorder=6)
    for t in d["trails"]:
        p = np.array(t["pts"])
        ax.plot(p[:, 0], p[:, 1], color="black", lw=1.15, dashes=(5, 2.2), zorder=4)
        mid = (p[0] + p[1]) / 2
        leg = p[1] - p[0]
        nrm = np.array([-leg[1], leg[0]]) / max(np.linalg.norm(leg), 1e-9)
        ang = math.degrees(math.atan2(leg[1], leg[0]))
        ang = ang - 180 if ang > 90 else ang + 180 if ang < -90 else ang
        ax.text(*(mid + 70 * nrm), t["name"], fontsize=6.5, rotation=ang, ha="center", va="center", zorder=6,
                bbox=dict(fc=GREEN, ec="none", pad=0.4, alpha=0.85))
    for lb in d["index_labels"]:
        ax.text(lb["x"], lb["y"], str(lb["level"]), color=BROWN_INDEX, fontsize=6.5, rotation=lb["angle"], ha="center",
                va="center", zorder=5, bbox=dict(fc=GREEN, ec="none", pad=0.5))
    for s in d["spot_heights"]:
        ax.plot(s["x"], s["y"], marker="x", color="black", ms=4, mew=0.9, zorder=6)
        ax.text(s["x"] + 45, s["y"] - 25, str(s["elev"]), fontsize=6.5, va="top", zorder=6)
        ax.text(s["x"] + 45, s["y"] + 30, s["name"], fontsize=7, style="italic", va="bottom", zorder=6)
    for p in d["points"]:
        ax.plot(p["x"], p["y"], marker="s" if p["shape"] == "square" else "o", color=MAGENTA, ms=6.5, mec="white",
                mew=0.8, zorder=8)
        ax.text(p["x"] + p.get("label_dx", 70), p["y"] + p.get("label_dy", 70), p["name"], color=MAGENTA, fontsize=12,
                weight="bold", ha="center", va="center", zorder=8,
                bbox=dict(fc="white", ec=MAGENTA, lw=0.6, pad=1.0, alpha=0.9))
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_aspect("equal")
    ax.set_xticks(range(0, int(W) + 1, 1000), [f"{571 + i}" for i in range(int(W // 1000) + 1)], fontsize=7)
    ax.set_yticks(range(0, int(H) + 1, 1000), [f"41{62 + i}" for i in range(int(H // 1000) + 1)], fontsize=7)
    ax.tick_params(length=4, width=0.8, top=True, right=True, labeltop=True, labelright=True, direction="in")
    for sp in ax.spines.values():
        sp.set_linewidth(1.3)
    fig.text(0.07, 0.965, "TOPOGRAPHIC MAP SERIES", fontsize=9, weight="bold", va="top")
    fig.text(0.07, 0.945, "1000-meter grid ticks, zone 11 · elevations in meters", fontsize=7, va="top")
    fig.text(0.93, 0.965, f"{d['quad'].upper()} QUADRANGLE", fontsize=11, weight="bold", ha="right", va="top")
    fig.text(0.93, 0.942, "7.5-MINUTE SERIES (TOPOGRAPHIC)", fontsize=7.5, ha="right", va="top")
    sax = fig.add_axes([0.285, 0.062, 0.43, 0.012])                    # 2000 m at the map's own scale
    for x0, x1, c in ((0, 500, "black"), (500, 1000, "white"), (1000, 2000, "black")):
        sax.add_patch(plt.Rectangle((x0, 0), x1 - x0, 1, fc=c, ec="black", lw=0.8))
    sax.set_xlim(0, 2000)
    sax.set_ylim(0, 1)
    sax.set_yticks([])
    sax.set_xticks([0, 500, 1000, 2000], ["0", "500", "1000", "2000 METERS"], fontsize=7)
    sax.tick_params(length=0, pad=2)
    for sp in sax.spines.values():
        sp.set_visible(False)
    fig.text(0.5, 0.093, "SCALE 1:24 000", fontsize=8.5, weight="bold", ha="center")
    fig.text(0.5, 0.022, "CONTOUR INTERVAL 20 METERS", fontsize=8.5, weight="bold", ha="center")
    fig.patches.append(plt.Polygon([[0.105, 0.035], [0.115, 0.095], [0.125, 0.035], [0.115, 0.05]], closed=True,
                                   fc="black", transform=fig.transFigure))
    fig.text(0.115, 0.1, "N", fontsize=10, weight="bold", ha="center")
    fig.text(0.93, 0.06, "Woodland tint: green\nTrail: dashed black  ·  Stream: blue\nIndex contour: heavy brown",
             fontsize=6.5, ha="right", va="center")
    fig.savefig(path, metadata={"Software": None})
    plt.close(fig)


# ---------------------------------------------------------------------------------------------- questions
INTRO = ("This is a topographic map. The contour interval is 20 meters, index contours (heavy lines) are every "
         "100 meters, and elevations are in meters. ")


def ask(d, level):
    if level == 1:
        return ("topo.higher_point", "label", INTRO + "Two points are marked in magenta, A and B. Which point is at the "
                "higher elevation? Answer with a single letter, A or B.")
    if level == 2:
        return ("topo.point_elevation", "integer", INTRO + "The magenta point P lies exactly on a contour line. What is "
                "the elevation of P in meters? Answer with a whole number, for example 1240.")
    t = d["trails"][0]["name"]
    return ("topo.trail_crossings", "integer", INTRO + f"The {t} (dashed black line) runs from the magenta square S to "
            "the magenta square E. How many contour lines does it cross between S and E? Count every crossing, index "
            "contours included; if it crosses the same contour line twice, count both. Answer with a whole number, "
            "for example 7.")


def main():
    for sub in ("images", "data"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    rows = []
    for level in (1, 2, 3):
        for k in range(3):
            seed = level * 100 + k + 1
            got = sample(seed, level)
            if got is None:
                raise SystemExit(f"seed {seed}: no fair task found")
            d, answer, checks = got
            tid = f"topo-{seed:06d}"
            (OUT / "data" / f"{tid}.json").write_text(json.dumps(
                {"task_id": tid, "family": "topo", "seed": seed, "generator_version": VERSION,
                 "params": {"level": level}, "data": d, "references": REFERENCES}, indent=1))
            render(d, OUT / "images" / f"{tid}.png")
            qtype, atype, question = ask(d, level)
            rows.append({"task_id": tid, "image": f"images/{tid}.png", "question": question, "answer": answer,
                         "answer_type": atype, "seed": seed, "generator_version": VERSION, "question_type": qtype,
                         "family": "topo", "difficulty": level, "data": f"data/{tid}.json", "checks": checks,
                         "references": REFERENCES})
            print(tid, qtype, "answer", answer, "attempt", d["attempt"], checks)
    (OUT / "tasks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


if __name__ == "__main__":
    main()
