"""The terrain and its geometry: an analytic elevation field, the 10 m grid, contours, trails, water routes.

Everything here is a pure function of the data dict `d` (or of a numpy Generator when sampling), so the
image and every answer can be rebuilt from the data JSON alone.
"""
from __future__ import annotations

import math

import numpy as np
from contourpy import contour_generator

W, H, STEP = 4000.0, 3000.0, 10.0          # map size and grid spacing, meters
CI, INDEX = 20, 100                         # contour interval and index-contour interval, meters
BOX_W, BOX_H = 1560.0, 400.0                # the incident box, meters on the map

QUADS = ["Harlan Ridge", "Coldwater Peak", "Juniper Flat", "Tamarack Butte", "Saddle Mountain", "Elk Hollow",
         "Granite Knob", "Marble Fork", "Antelope Spring", "Castle Crags", "Bear Wallow", "Indian Meadows",
         "Windy Gap", "Soda Springs", "Deadman Canyon", "Grouse Ridge"]
PEAKS = ["Coldwater Pk", "Granite Knob", "Bald Mtn", "Lookout Pt", "Eagle Rock", "Signal Hill", "Pine Butte",
         "Hogback", "Sugarloaf", "Round Top", "Black Butte", "Chimney Rock"]
TRAILS = ["Ridge Trail", "Miners Trail", "Lookout Trail", "Aspen Trail", "Summit Trail", "Cedar Trail",
          "Juniper Trail", "Quarry Trail", "Basin Trail", "Pack Trail"]
STREAMS = ["Mill Creek", "Cold Brook", "Wolf Creek", "Dry Fork", "Bear Creek", "Alder Creek"]


# ---------------------------------------------------------------------------------------------- the field
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


def z_grid(Z, x, y):
    """Elevation by bilinear interpolation of the 10 m grid: the second, independent way to read the terrain."""
    x, y = np.asarray(x, float) / STEP, np.asarray(y, float) / STEP
    i = np.clip(np.floor(x).astype(int), 0, Z.shape[1] - 2)
    j = np.clip(np.floor(y).astype(int), 0, Z.shape[0] - 2)
    fx, fy = x - i, y - j
    return (Z[j, i] * (1 - fx) * (1 - fy) + Z[j, i + 1] * fx * (1 - fy)
            + Z[j + 1, i] * (1 - fx) * fy + Z[j + 1, i + 1] * fx * fy)


def gradient(d, x, y, e=1.0):
    return np.array([(elev(d, x + e, y) - elev(d, x - e, y)) / (2 * e),
                     (elev(d, x, y + e) - elev(d, x, y - e)) / (2 * e)])


def contour_lines(Z):
    cg = contour_generator(x=np.arange(0, W + 1, STEP), y=np.arange(0, H + 1, STEP), z=Z)
    lo, hi = math.ceil(Z.min() / CI) * CI, math.floor(Z.max() / CI) * CI
    return {lv: [ln for ln in cg.lines(lv) if len(ln) > 1] for lv in range(int(lo), int(hi) + 1, CI)}


# ---------------------------------------------------------------------------------------------- geometry
def inside(p, m):
    return m <= p[0] <= W - m and m <= p[1] <= H - m


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


def length(pts):
    pts = np.asarray(pts, float)
    return float(np.sqrt((np.diff(pts, axis=0) ** 2).sum(1)).sum())


# ---------------------------------------------------------------------------------------------- trails
def crossings_sampled(d, pts):
    """Walk the trail in 1 m steps over the analytic field. Returns (all crossings, uphill ones, where)."""
    p = densify(pts)
    band = np.floor(elev(d, p[:, 0], p[:, 1]) / CI)
    step = np.diff(band)
    k = np.where(step != 0)[0]
    where = [[round(float(p[i, 0]), 1), round(float(p[i, 1]), 1), bool(step[i] > 0)] for i in k]
    return int(np.abs(step).sum()), int(step[step > 0].sum()), where


def crossings_geometry(Z, lines, pts):
    """Intersect the trail's straight legs with the contour polylines traced from the grid (contourpy).
    A crossing is uphill when the grid is higher 4 m after it than 4 m before it. Returns (all, uphill)."""
    pts = np.asarray(pts, float)
    total = up = 0
    for lns in lines.values():
        for line in lns:
            a, s = line[:-1], line[1:] - line[:-1]
            for p, q in zip(pts[:-1], pts[1:]):
                r = q - p
                den = r[0] * s[:, 1] - r[1] * s[:, 0]
                ok = np.abs(den) > 1e-12
                safe = np.where(ok, den, 1)
                t = np.where(ok, ((a[:, 0] - p[0]) * s[:, 1] - (a[:, 1] - p[1]) * s[:, 0]) / safe, -1)
                u = np.where(ok, ((a[:, 0] - p[0]) * r[1] - (a[:, 1] - p[1]) * r[0]) / safe, -1)
                hit = (t >= 0) & (t < 1) & (u >= 0) & (u < 1)
                total += int(hit.sum())
                ahead = 4.0 * r / np.linalg.norm(r)
                for tt in t[hit]:
                    c = p + tt * r
                    up += int(float(z_grid(Z, *(c + ahead))) > float(z_grid(Z, *(c - ahead))))
    return total, up


def trail_is_fair(d, pts):
    """No grazing: the trail never turns around within 5 m (vertically) of a contour, crossings are at least
    25 m apart along the trail, none is shallow, and none hides under an end marker (within 60 m of an end)."""
    p = densify(pts)
    z = elev(d, p[:, 0], p[:, 1])
    dz = np.diff(z)
    turn = np.where(np.sign(dz[1:]) != np.sign(dz[:-1]))[0] + 1
    for i in list(turn) + [0, len(z) - 1]:
        if abs(((z[i] + CI / 2) % CI) - CI / 2) < 5.0:
            return False
    cross = np.where(np.diff(np.floor(z / CI)) != 0)[0]
    if len(cross) == 0 or cross[0] < 60 or cross[-1] > len(z) - 60:
        return False
    if len(cross) > 1 and np.diff(cross).min() < 25:
        return False
    for i in cross:
        lo, hi = max(0, i - 5), min(len(z) - 1, i + 5)
        if abs(z[hi] - z[lo]) / (hi - lo) < 0.04:
            return False
    return True


def random_trail(rng, legs, margin=260, start=None, heading=None, leg_m=(450, 1000), bend=1.1):
    for _ in range(200):
        p = np.array(start, float) if start is not None else np.array(
            [rng.uniform(margin, W - margin), rng.uniform(margin, H - margin)])
        head, pts = (rng.uniform(0, 2 * math.pi) if heading is None else heading), [p]
        for _ in range(legs):
            head += rng.uniform(-bend, bend)
            p = p + rng.uniform(*leg_m) * np.array([math.cos(head), math.sin(head)])
            pts.append(p)
        if all(inside(q, margin) for q in pts):
            return [[round(float(q[0]), 1), round(float(q[1]), 1)] for q in pts]
        if start is not None:
            return None
    return None


# ---------------------------------------------------------------------------------------------- water
def descend(d, start, ds=15.0, steps=400):
    """Steepest descent on the analytic field: the way water runs."""
    p, pts = np.array(start, float), []
    for _ in range(steps):
        if not inside(p, 0):
            break
        pts.append([round(float(p[0]), 1), round(float(p[1]), 1)])
        g = gradient(d, *p)
        n = np.linalg.norm(g)
        if n < 0.004:
            break
        p = p - ds * g / n
    return pts


def descend_grid(Z, start, ds=5.0, steps=1600):
    """Second way: steepest descent on the 10 m grid (bilinear), with 5 m steps."""
    gy, gx = np.gradient(Z, STEP)
    p, pts = np.array(start, float), []
    for _ in range(steps):
        if not inside(p, 0):
            break
        pts.append([float(p[0]), float(p[1])])
        g = np.array([float(z_grid(gx, p[0], p[1])), float(z_grid(gy, p[0], p[1]))])
        n = np.linalg.norm(g)
        if n < 0.004:
            break
        p = p - ds * g / n
    return pts


# ---------------------------------------------------------------------------------------------- sampling
def new_terrain(rng):
    return {"extent_m": [W, H], "contour_interval_m": CI, "index_interval_m": INDEX,
            "base": {"z0": round(float(rng.uniform(240, 420)), 1), "gx": round(float(rng.uniform(-0.02, 0.02)), 4),
                     "gy": round(float(rng.uniform(-0.02, 0.02)), 4)},
            "hills": [{"x": round(float(rng.uniform(300, W - 300)), 1), "y": round(float(rng.uniform(300, H - 300)), 1),
                       "h": round(float(rng.uniform(120, 360)), 1), "sx": round(float(rng.uniform(380, 800)), 1),
                       "sy": round(float(rng.uniform(380, 800)), 1), "rot": round(float(rng.uniform(0, math.pi)), 3)}
                      for _ in range(int(rng.integers(5, 8)))],
            "quad": str(rng.choice(QUADS)), "points": [], "trails": [], "streams": [], "spot_heights": [],
            "index_labels": []}


def box_corner(marks):
    """A map corner where the incident box covers none of `marks` (points and densified lines), with 130 m to spare."""
    for x0, y0 in ((40, H - 40 - BOX_H), (W - 40 - BOX_W, H - 40 - BOX_H), (40, 40), (W - 40 - BOX_W, 40)):
        if all(not (x0 - 130 <= m[0] <= x0 + BOX_W + 130 and y0 - 130 <= m[1] <= y0 + BOX_H + 130) for m in marks):
            return [float(x0), float(y0)]
    return None


def decorate(rng, d, X, Y, Z, lines, keep_lines, stream_gap_lines=(), extra_trail=True):
    """Spot heights, a second trail, streams and index-contour labels, as on a real quadrangle. Labels stay clear
    of the task marks, of the lines a solver must trace (`keep_lines`) and of the incident box."""
    marks = [[p["x"], p["y"]] for p in d["points"]]
    bx, by = d["box"]["xy"]

    def clear(q, r):
        return all(math.dist(q, m) >= r for m in marks) and all(dist_to_poly(q, t) >= r for t in keep_lines)

    def in_box(q, pad=150):
        return bx - pad <= q[0] <= bx + BOX_W + pad and by - pad <= q[1] <= by + BOX_H + pad

    c = Z[1:-1, 1:-1]
    peak = (c > Z[:-2, 1:-1]) & (c > Z[2:, 1:-1]) & (c > Z[1:-1, :-2]) & (c > Z[1:-1, 2:]) & \
           (c > Z[:-2, :-2]) & (c > Z[2:, 2:]) & (c > Z[:-2, 2:]) & (c > Z[2:, :-2])
    d["spot_heights"] = []
    for (j, i), name in zip(np.argwhere(peak), rng.permutation(PEAKS)):
        q = [float(X[j + 1, i + 1]), float(Y[j + 1, i + 1])]
        if inside(q, 200) and clear(q, 220) and not in_box(q, 260):
            d["spot_heights"].append({"x": q[0], "y": q[1], "elev": int(round(float(Z[j + 1, i + 1]))), "name": str(name)})
    spots = [[sp["x"], sp["y"]] for sp in d["spot_heights"]]

    used = {t["name"] for t in d["trails"]}
    free = [n for n in rng.permutation(TRAILS) if n not in used]
    extra = random_trail(rng, legs=2)
    if extra_trail and extra and all(clear(q, 250) and not in_box(q, 60) and all(math.dist(q, o) >= 320 for o in spots)
                                     for q in densify(extra, 50)):
        d["trails"].append({"name": str(free[0]), "pts": extra, "asked": False})

    d["streams"] = []
    for h, name in zip(rng.permutation(len(d["hills"]))[:2], rng.permutation(STREAMS)):
        hill, ang = d["hills"][int(h)], rng.uniform(0, 2 * math.pi)
        s = descend(d, [hill["x"] + 2.2 * hill["sx"] * math.cos(ang), hill["y"] + 2.2 * hill["sy"] * math.sin(ang)])
        if len(s) <= 25 or in_box(s[len(s) // 2], 120):
            continue
        if all(math.dist(q, o) >= 200 for q in s[::5] for o in spots + marks) and \
                all(dist_to_poly(q, ln) >= 300 for q in s[::5] for ln in stream_gap_lines):
            d["streams"].append({"name": str(name), "pts": s})

    drawn = [t["pts"] for t in d["trails"]] + [st["pts"] for st in d["streams"]]
    names_at = [((np.array(t["pts"][0]) + np.array(t["pts"][1])) / 2).tolist() for t in d["trails"]] + \
               [st["pts"][len(st["pts"]) // 2] for st in d["streams"]]         # where line names are printed
    d["spot_heights"] = [sp for sp in d["spot_heights"] if all(math.dist([sp["x"], sp["y"]], o) >= 330 for o in names_at)]
    spots = [[sp["x"], sp["y"]] for sp in d["spot_heights"]]
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
                others = spots + names_at + [[l["x"], l["y"]] for l in d["index_labels"]]
                if inside(q, 160) and clear(q, 170) and not in_box(q) and all(math.dist(q, o) >= 260 for o in others) \
                        and all(dist_to_poly(q, ln2) >= 150 for ln2 in drawn):
                    d["index_labels"].append({"x": round(q[0], 1), "y": round(q[1], 1), "level": int(lv),
                                              "angle": round(ang, 1)})
