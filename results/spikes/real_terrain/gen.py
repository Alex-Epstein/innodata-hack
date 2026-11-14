"""Real-terrain topo spike: USGS-quad-style maps drawn from real US elevation (USGS 3DEP via AWS Terrain Tiles).

    cd /Users/alex/Desktop/innodata-hack && uv run python -I <work>/gen.py [--out <work>/tasks] [--seeds 1-10]

Reads ONLY the local terrarium tiles in tiles/ (no network), so a seed gives the same PNG byte for byte.
Data first: for each seed we pick an area and a crop window, smooth the elevation lightly, sample a winding
trail, compute the answer two ways, and write data/<task_id>.json plus the grid (.npy). The PNG is drawn only
from those files.

Question template (one): how many contour lines does the dashed red trail cross between S and E?
  answer 1: walk the trail in 1 m steps on the bilinearly interpolated grid, count sign changes of (z - level)
            for every contour level
  answer 2: intersect the trail polyline with the contour polylines that are actually drawn (contourpy)
Seeds are rejected when the two disagree, when crossings are < 40 m apart or < 40 m from an end, or when the
trail grazes a level (|z - level| < 2 m for more than 15 m of trail).
"""
import argparse
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from contourpy import contour_generator
from matplotlib.collections import LineCollection
from PIL import Image

HERE = Path(__file__).resolve().parent
TILES = HERE / "tiles"
VERSION = "realtopo-spike-0.1"
Z = 13
CROP_W, CROP_H = 3200.0, 2400.0            # map window, meters (4:3)
UP = 3                                      # contour on a 3x bilinear upsample of the grid (same field, smoother lines)
MIN_CROSS, MAX_CROSS = 8, 20
MAX_ATTEMPTS = 400
SEP_M, GRAZE_DZ, GRAZE_RUN = 40.0, 2.0, 40.0          # spec said 15 m; infeasible on real terrain (notes.md)
TURN_FRAC, MIN_ANGLE = 0.25, 25.0                  # extra fairness rules (see notes.md)
REFERENCES = ["USGS 7.5-minute topographic quadrangle maps (1:24 000 style: brown contours, bold labeled index "
              "contours, woodland green tint)",
              "Elevation: USGS 3DEP / NED (public domain) via AWS Open Data Terrain Tiles (Mapzen terrarium, z13)"]
AREAS = [  # name, state, mosaic tiles (x0, y0, 2x2), anchor (lat, lon) that every crop must contain
    {"key": "bear", "name": "Bear Mountain", "state": "New York", "x0": 2411, "y0": 3061, "anchor": (41.3126, -73.9888)},
    {"key": "breakneck", "name": "Breakneck Ridge", "state": "New York", "x0": 2412, "y0": 3057, "anchor": (41.4440, -73.9700)},
    {"key": "harriman", "name": "Harriman State Park", "state": "New York", "x0": 2409, "y0": 3063, "anchor": (41.2236, -74.0671)},
    {"key": "tam", "name": "Mount Tamalpais", "state": "California", "x0": 1305, "y0": 3161, "anchor": (37.9235, -122.5965)},
]
GREEN, WATER, BROWN, BROWN_IDX, RED, MAGENTA = "#dcebc8", "#a9d3ee", "#b5743a", "#8f4f1c", "#d7191c", "#b0127e"


# ------------------------------------------------------------------------------------------------ terrain
def global_px_to_lonlat(X, Y):
    n = 256 * 2 ** Z
    return X / n * 360 - 180, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * Y / n))))


def lonlat_to_global_px(lat, lon):
    n = 256 * 2 ** Z
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def load_mosaic(area):
    """2x2 tiles -> 512x512 elevation (m), north at row 0. Bathymetry/nodata spikes below 0 are clamped to 0."""
    rows = []
    for dy in (0, 1):
        row = []
        for dx in (0, 1):
            f = TILES / f"{area['key']}_{Z}_{area['x0'] + dx}_{area['y0'] + dy}.png"
            a = np.asarray(Image.open(f).convert("RGB")).astype(np.float64)
            row.append(a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768)
        rows.append(np.hstack(row))
    return np.vstack(rows)


def blur(a, sigma=1.0):
    r = int(math.ceil(3 * sigma))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    p = np.pad(a, r, mode="edge")
    p = np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 0, p)
    return np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 1, p)


def window(a, r, fn):
    v = np.lib.stride_tricks.sliding_window_view(np.pad(a, r, mode="edge"), (2 * r + 1, 2 * r + 1))
    return fn(v, axis=(-1, -2))


def water_mask(raw):
    """Sea level / river (<= 1 m) plus hydro-flattened lakes (flat to 5 cm over a 5x5 window)."""
    flat = (window(raw, 1, np.max) - window(raw, 1, np.min)) < 0.05
    lake = window(window(flat.astype(np.uint8), 2, np.min), 2, np.max).astype(bool) & flat
    w = (raw <= 1.0) | lake
    w = window(window(w.astype(np.uint8), 2, np.min), 2, np.max).astype(bool)   # drop specks under ~5 px
    return w


def bilinear(G, s, x, y):
    """Elevation at (x, y) meters; grid G has row 0 = south edge, spacing s meters."""
    j, i = np.asarray(x, float) / s, np.asarray(y, float) / s
    j0 = np.clip(np.floor(j).astype(int), 0, G.shape[1] - 2)
    i0 = np.clip(np.floor(i).astype(int), 0, G.shape[0] - 2)
    fj, fi = j - j0, i - i0
    return (G[i0, j0] * (1 - fi) * (1 - fj) + G[i0, j0 + 1] * (1 - fi) * fj
            + G[i0 + 1, j0] * fi * (1 - fj) + G[i0 + 1, j0 + 1] * fi * fj)


def fine_grid(G, s):
    ny, nx = G.shape
    xs = np.linspace(0, (nx - 1) * s, (nx - 1) * UP + 1)
    ys = np.linspace(0, (ny - 1) * s, (ny - 1) * UP + 1)
    X, Y = np.meshgrid(xs, ys)
    return xs, ys, bilinear(G, s, X, Y)


def contour_lines(G, s, levels):
    xs, ys, F = fine_grid(G, s)
    cg = contour_generator(x=xs, y=ys, z=F)
    return {int(l): [np.asarray(p) for p in cg.lines(l) if len(p) > 1] for l in levels}


# ------------------------------------------------------------------------------------------------ trail + answers
def densify(pts, ds=1.0):
    out = [pts[:1]]
    for a, b in zip(pts[:-1], pts[1:]):
        n = max(2, int(math.ceil(np.linalg.norm(b - a) / ds)) + 1)
        out.append(a + (b - a) * np.linspace(0, 1, n)[1:, None])
    return np.vstack(out)


def catmull_rom(ctrl, step=5.0):
    P = np.vstack([2 * ctrl[0] - ctrl[1], ctrl, 2 * ctrl[-1] - ctrl[-2]])
    out = []
    for k in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[k - 1], P[k], P[k + 1], P[k + 2]
        n = max(4, int(np.linalg.norm(p2 - p1) / step))
        t = np.linspace(0, 1, n, endpoint=False)[:, None]
        out.append(0.5 * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2
                          + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    out.append(ctrl[-1:])
    return np.vstack(out)


def random_trail(rng, G, s, ci, margin=280.0):
    """A smooth winding route that mostly climbs or descends along the fall line (steep, clean crossings)."""
    def grad(p):
        e = 2 * s
        return np.array([bilinear(G, s, p[0] + e, p[1]) - bilinear(G, s, p[0] - e, p[1]),
                         bilinear(G, s, p[0], p[1] + e) - bilinear(G, s, p[0], p[1] - e)]) / (2 * e)
    for _ in range(40):
        p = np.array([rng.uniform(margin, CROP_W - margin), rng.uniform(margin, CROP_H - margin)])
        sign, side, ctrl, h = rng.choice([-1.0, 1.0]), rng.choice([-1.0, 1.0]), [p], rng.uniform(0, 2 * math.pi)
        for _ in range(int(rng.integers(10, 17))):
            g = grad(p)
            m = float(np.linalg.norm(g))
            if m > 0.06 * ci / 10:                              # sidehill at a steady grade, like a built trail
                target = rng.uniform(0.30, 0.42) * ci / 20
                off = math.acos(min(1.0, target / m))
                h = math.atan2(sign * g[1], sign * g[0]) + side * off + rng.uniform(-0.2, 0.2)
            else:
                h += rng.uniform(-0.8, 0.8)
            if rng.uniform() < 0.12:
                sign = -sign
            if rng.uniform() < 0.25:
                side = -side
            p = p + rng.uniform(120, 240) * np.array([math.cos(h), math.sin(h)])
            ctrl.append(p)
        pts = np.round(catmull_rom(np.array(ctrl)), 2)
        if (pts[:, 0].min() < margin or pts[:, 0].max() > CROP_W - margin or pts[:, 1].min() < margin
                or pts[:, 1].max() > CROP_H - margin):
            continue
        q = pts[::4]                                 # no near self-approach: keeps the trail easy to follow
        arc = np.r_[0, np.cumsum(np.linalg.norm(np.diff(q, axis=0), axis=1))]
        D = np.sqrt(((q[:, None] - q[None]) ** 2).sum(-1))
        far = np.abs(arc[:, None] - arc[None]) > 300
        if (D[far] < 150).any() or arc[-1] < 900:
            continue
        return pts
    return None


def crossings_by_sampling(G, s, pts, levels):
    p = densify(pts, 1.0)
    seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    z = bilinear(G, s, p[:, 0], p[:, 1])
    found = []
    for l in levels:
        d = z - l
        idx = np.where(np.sign(d[:-1]) * np.sign(d[1:]) < 0)[0]
        found += [(float(seg[i]), int(l), float(p[i, 0]), float(p[i, 1])) for i in idx]
    return sorted(found), z, seg


def crossings_by_geometry(pts, lines):
    total = 0
    a, b = pts[:-1], pts[1:]
    r = b - a
    lo, hi = pts.min(0) - 5, pts.max(0) + 5
    for segs in lines.values():
        for line in segs:
            if (line.max(0) < lo).any() or (line.min(0) > hi).any():
                continue
            c, d = line[:-1], line[1:]
            sv = d - c
            den = r[:, None, 0] * sv[None, :, 1] - r[:, None, 1] * sv[None, :, 0]
            ok = np.abs(den) > 1e-12
            den = np.where(ok, den, 1)
            w = c[None] - a[:, None]
            t = (w[..., 0] * sv[None, :, 1] - w[..., 1] * sv[None, :, 0]) / den
            u = (w[..., 0] * r[:, None, 1] - w[..., 1] * r[:, None, 0]) / den
            total += int((ok & (t >= 0) & (t < 1) & (u >= 0) & (u < 1)).sum())
    return total


def grazes(z, levels, run=GRAZE_RUN):
    """True if the trail stays within GRAZE_DZ meters (vertically) of one level for more than `run` meters."""
    for l in levels:
        near = np.abs(z - l) < GRAZE_DZ
        if not near.any():
            continue
        e = np.diff(np.r_[0, near.astype(int), 0])
        if ((np.where(e == -1)[0] - np.where(e == 1)[0]) > run).any():
            return True
    return False


def unfair(G, s, p, z, found, levels, ci):
    """Reasons a careful human could miscount: a near-tangent touch, a shallow crossing angle, or grazing."""
    if grazes(z, levels):
        return "graze"
    zz = np.convolve(z, np.ones(9) / 9, mode="same")[5:-5]
    dz = np.diff(zz)
    turn = np.where(np.sign(dz[1:]) * np.sign(dz[:-1]) < 0)[0] + 6
    lv = np.array(levels, float)
    for i in turn:                                   # turnaround (local high/low along the trail) near a level
        if np.abs(lv - z[i]).min() < TURN_FRAC * ci:
            return "touch"
    for a, l, x, y in found:                         # crossing angle between trail and contour
        i = int(np.searchsorted(np.r_[0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))], a))
        t = p[min(i + 4, len(p) - 1)] - p[max(i - 4, 0)]
        e = 2 * s
        g = np.array([bilinear(G, s, x + e, y) - bilinear(G, s, x - e, y), bilinear(G, s, x, y + e) - bilinear(G, s, x, y - e)])
        if abs(t @ g) / max(np.linalg.norm(t) * np.linalg.norm(g), 1e-12) < math.sin(math.radians(MIN_ANGLE)):
            return "angle"
    return None


def pick_window(G, s, Wt, pts, levels, ci, rng):
    """Choose S and E on a long route so that the piece between them passes every fairness rule.
    Returns the trimmed polyline (5 m vertices) or None. The trimmed piece is re-checked from scratch later."""
    p = densify(pts, 1.0)
    seg = np.r_[0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]
    z = bilinear(G, s, p[:, 0], p[:, 1])
    found = crossings_by_sampling(G, s, pts, levels)[0]
    pos = np.array([f[0] for f in found])
    L = float(seg[-1])
    if len(pos) < MIN_CROSS:
        return None
    bad = []
    ny, nx = Wt.shape
    jj, ii = np.round(p[:, 0] / s).astype(int), np.round(p[:, 1] / s).astype(int)
    for a in seg[Wt[np.clip(ii, 0, ny - 1), np.clip(jj, 0, nx - 1)]]:
        bad.append((a - 20, a + 20))
    for l in levels:
        near = np.abs(z - l) < GRAZE_DZ
        e = np.diff(np.r_[0, near.astype(int), 0])
        for a0, a1 in zip(np.where(e == 1)[0], np.where(e == -1)[0]):
            if a1 - a0 > GRAZE_RUN:
                bad.append((seg[a0], seg[a1 - 1]))
    zz = np.convolve(z, np.ones(9) / 9, mode="same")
    dz = np.diff(zz[5:-5])
    lv = np.array(levels, float)
    for i in np.where(np.sign(dz[1:]) * np.sign(dz[:-1]) < 0)[0] + 6:
        if np.abs(lv - z[i]).min() < TURN_FRAC * ci:
            bad.append((seg[i] - 20, seg[i] + 20))
    for a, l, x, y in found:
        i = int(np.searchsorted(seg, a))
        t = p[min(i + 4, len(p) - 1)] - p[max(i - 4, 0)]
        e = 2 * s
        g = np.array([bilinear(G, s, x + e, y) - bilinear(G, s, x - e, y), bilinear(G, s, x, y + e) - bilinear(G, s, x, y - e)])
        if abs(t @ g) / max(np.linalg.norm(t) * np.linalg.norm(g), 1e-12) < math.sin(math.radians(MIN_ANGLE)):
            bad.append((a - 20, a + 20))
    for a, b in zip(pos[:-1], pos[1:]):
        if b - a < SEP_M:
            bad.append((a, b))
    # S/E candidates: one per gap between crossings (gap k lies before crossing k)
    edges = np.r_[0.0, pos, L]
    spots = []
    for k in range(len(pos) + 1):
        a, b = edges[k], edges[k + 1]
        if k == 0 and b >= SEP_M:
            spots.append((k, max(0.0, b - 2 * SEP_M)))
        elif k == len(pos) and L - a >= SEP_M:
            spots.append((k, min(L, a + 2 * SEP_M)))
        elif b - a >= 2 * SEP_M:
            spots.append((k, (a + b) / 2))
    good = []
    for i, (ki, sS) in enumerate(spots):
        for kj, sE in spots[i + 1:]:
            if MIN_CROSS <= kj - ki <= MAX_CROSS and sE - sS >= 600 and not any(x1 >= sS and x0 <= sE for x0, x1 in bad):
                good.append((kj - ki, sS, sE))
    if not good:
        return None
    top = max(g[0] for g in good)                    # prefer long pieces: more crossings, harder to count
    good = [g for g in good if g[0] >= top - 2]
    _, sS, sE = good[int(rng.integers(len(good)))]
    i0, i1 = int(np.searchsorted(seg, sS)), int(np.searchsorted(seg, sE))
    keep = list(range(i0, i1, 5)) + [i1]
    return np.round(p[keep], 2)


# ------------------------------------------------------------------------------------------------ sampling a task
def sample(seed, stats=None):
    stats = {} if stats is None else stats
    rng = np.random.default_rng(seed)
    area = AREAS[(seed - 1) % len(AREAS)]
    raw = load_mosaic(area)
    raw = np.maximum(raw, 0.0)
    wet = water_mask(raw)
    sm = blur(raw, 1.0)
    X0, Y0 = area["x0"] * 256, area["y0"] * 256
    lat_c = global_px_to_lonlat(X0 + 256, Y0 + 256)[1]
    s = 40075016.686 * math.cos(math.radians(lat_c)) / (256 * 2 ** Z)        # meters per pixel (square)
    nx, ny = int(CROP_W / s) + 2, int(CROP_H / s) + 2
    ax_, ay_ = lonlat_to_global_px(*area["anchor"])
    ac, ar = ax_ - X0, ay_ - Y0
    m = int(400 / s)
    for attempt in range(MAX_ATTEMPTS):
        c0 = int(rng.integers(max(4, int(ac) - nx + m), min(512 - nx - 4, int(ac) - m) + 1))
        r0 = int(rng.integers(max(4, int(ar) - ny + m), min(512 - ny - 4, int(ar) - m) + 1))
        G = sm[r0:r0 + ny, c0:c0 + nx][::-1].astype(np.float32).astype(np.float64)    # row 0 = south
        Wt = wet[r0:r0 + ny, c0:c0 + nx][::-1]
        if (raw[r0:r0 + ny, c0:c0 + nx] <= 1.0).mean() > 0.10:   # rivers/sea carry blended bathymetry artifacts
            stats["crop_too_wet"] = stats.get("crop_too_wet", 0) + 1
            continue
        ci = 20 if float(G.max() - G.min()) > 250 else 10
        idx = ci * 5
        levels = list(range(int(math.ceil(max(G.min(), 0.5) / ci)) * ci, int(G.max()) + 1, ci))
        levels = [l for l in levels if l > 0]
        for _ in range(15):
            pts = random_trail(rng, G, s, ci)
            if pts is None:
                stats["no_trail"] = stats.get("no_trail", 0) + 1
                continue
            pts = pick_window(G, s, Wt, pts, levels, ci, rng)
            if pts is None:
                stats["no_fair_window"] = stats.get("no_fair_window", 0) + 1
                continue
            q = densify(pts, 5.0)
            jj, ii = np.round(q[:, 0] / s).astype(int), np.round(q[:, 1] / s).astype(int)
            if Wt[np.clip(ii, 0, ny - 1), np.clip(jj, 0, nx - 1)].any():
                stats["water"] = stats.get("water", 0) + 1
                continue
            found, z, seg = crossings_by_sampling(G, s, pts, levels)
            n1 = len(found)
            if not MIN_CROSS <= n1 <= MAX_CROSS:
                stats["count_out_of_range"] = stats.get("count_out_of_range", 0) + 1
                continue
            pos = np.array([f[0] for f in found])
            L = float(seg[-1])
            if pos.min() < SEP_M or pos.max() > L - SEP_M or (np.diff(pos) < SEP_M).any():
                stats["spacing_40m"] = stats.get("spacing_40m", 0) + 1
                continue
            why = unfair(G, s, densify(pts, 1.0), z, found, levels, ci)
            if why:
                stats[why] = stats.get(why, 0) + 1
                continue
            lines = contour_lines(G, s, levels)
            n2 = crossings_by_geometry(pts, lines)
            if n2 != n1:
                stats["methods_disagree"] = stats.get("methods_disagree", 0) + 1
                continue
            d = build_data(seed, area, attempt, c0, r0, nx, ny, s, G, Wt, ci, idx, levels, pts, found, n1, n2,
                           L, lines, rng)
            return d, G, Wt
    return None


def build_data(seed, area, attempt, c0, r0, nx, ny, s, G, Wt, ci, idx, levels, pts, found, n1, n2, L, lines, rng):
    X0, Y0 = area["x0"] * 256, area["y0"] * 256
    lon_w, lat_n = global_px_to_lonlat(X0 + c0, Y0 + r0)
    lon_e, lat_s = global_px_to_lonlat(X0 + c0 + (nx - 1), Y0 + r0 + (ny - 1))
    tq = densify(pts, 5.0)

    def dist_trail(p):
        return float(np.sqrt(((tq - p) ** 2).sum(1)).min())

    # index-contour labels: on long index lines, >= 130 m from the trail, >= 300 m from each other
    labels = []
    for l in levels:
        if l % idx:
            continue
        for line in lines[l]:
            if len(line) < 60:
                continue
            for k in rng.permutation(np.arange(10, len(line) - 10, 6))[:60]:
                p = line[k]
                if not (90 < p[0] < CROP_W - 90 and 60 < p[1] < CROP_H - 60):
                    continue
                if dist_trail(p) < 130 or any(math.hypot(p[0] - q["x"], p[1] - q["y"]) < 300 for q in labels):
                    continue
                t = line[k + 3] - line[k - 3]
                ang = math.degrees(math.atan2(t[1], t[0]))
                ang = ang - 180 if ang > 90 else ang + 180 if ang < -90 else ang
                labels.append({"x": round(float(p[0]), 1), "y": round(float(p[1]), 1), "level": int(l),
                               "angle": round(ang, 1)})
                break
    # spot heights: local maxima over ~450 m windows, not on the trail or a label
    r = int(round(225 / s))
    peaks = np.argwhere((G == window(G, r, np.max)) & (G - G.min() > 30))
    spots = []
    for i, j in sorted(peaks.tolist(), key=lambda ij: -G[ij[0], ij[1]]):
        p = np.array([j * s, i * s])
        if not (120 < p[0] < CROP_W - 200 and 80 < p[1] < CROP_H - 120) or dist_trail(p) < 120:
            continue
        if any(math.hypot(p[0] - q["x"], p[1] - q["y"]) < 200 for q in labels + spots):
            continue
        spots.append({"x": round(float(p[0]), 1), "y": round(float(p[1]), 1), "elev": int(round(G[i, j]))})
        if len(spots) == 4:
            break
    return {
        "area": area["name"], "state": area["state"], "attempt": attempt,
        "source": {"tiles": [f"terrarium/{Z}/{area['x0'] + dx}/{area['y0'] + dy}.png" for dy in (0, 1) for dx in (0, 1)],
                   "crop_px": {"col0": c0, "row0": r0, "nx": nx, "ny": ny},
                   "processing": "elevation clamped at 0 m, Gaussian blur sigma 1 px, float32, bilinear interpolation"},
        "grid": {"spacing_m": round(s, 4), "shape": [ny, nx], "extent_m": [CROP_W, CROP_H],
                 "bounds": {"west": round(lon_w, 6), "east": round(lon_e, 6), "south": round(lat_s, 6),
                            "north": round(lat_n, 6)},
                 "elev_min_m": round(float(G.min()), 1), "elev_max_m": round(float(G.max()), 1),
                 "elev_mean_m": round(float(G.mean()), 1), "water_fraction": round(float(Wt.mean()), 4)},
        "contour_interval_m": ci, "index_interval_m": idx, "levels": levels,
        "trail": {"pts": pts.tolist(), "length_m": round(L, 1)},
        "crossings": [{"arc_m": round(a, 1), "level": l, "x": round(x, 1), "y": round(y, 1)} for a, l, x, y in found],
        "answer_sampling": n1, "answer_geometry": n2,
        "index_labels": labels, "spot_heights": spots,
    }


# ------------------------------------------------------------------------------------------------ drawing
def dms(v, lon):
    h = ("W" if v < 0 else "E") if lon else ("S" if v < 0 else "N")
    v = abs(v)
    d, mnt = int(v), int(round((v - int(v)) * 3600)) // 60
    sec = int(round((v - int(v)) * 3600)) % 60
    return f"{d}°{mnt:02d}'{sec:02d}\"{h}"


def render(d, G, Wt, path):
    s, ci, idx = d["grid"]["spacing_m"], d["contour_interval_m"], d["index_interval_m"]
    fig = plt.figure(figsize=(1600 / 150, 1200 / 150), dpi=150)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0.065, 0.115, 0.78, 0.78])
    ax.set_facecolor(GREEN)
    ny, nx = G.shape
    if Wt.any():                                      # smooth shoreline: contour the blurred mask at 0.5
        xs, ys = np.arange(nx) * s, np.arange(ny) * s
        ax.contourf(xs, ys, blur(Wt.astype(np.float64), 1.2), levels=[0.5, 2.0], colors=[WATER], zorder=1)
    lines = contour_lines(G, s, d["levels"])
    for l, segs in lines.items():
        major = l % idx == 0
        ax.add_collection(LineCollection(segs, colors=BROWN_IDX if major else BROWN,
                                         linewidths=1.25 if major else 0.55, zorder=2))
    for lb in d["index_labels"]:
        ax.text(lb["x"], lb["y"], str(lb["level"]), color=BROWN_IDX, fontsize=8, rotation=lb["angle"],
                rotation_mode="anchor", ha="center", va="center", zorder=5,
                bbox=dict(fc=GREEN, ec="none", pad=0.3))
    for sp in d["spot_heights"]:
        ax.plot(sp["x"], sp["y"], marker="x", color="black", ms=4.5, mew=1.0, zorder=6)
        ax.text(sp["x"] + 35, sp["y"] - 10, str(sp["elev"]), fontsize=8, va="top", zorder=6)
    p = np.array(d["trail"]["pts"])
    ax.plot(p[:, 0], p[:, 1], color=RED, lw=1.5, dashes=(5, 2.5), zorder=7, solid_capstyle="butt")
    for name, q, nb in (("S", p[0], p[min(8, len(p) - 1)]), ("E", p[-1], p[max(-9, -len(p))])):
        ax.plot(*q, marker="s", color=MAGENTA, ms=7.5, mec="white", mew=0.9, zorder=8)
        v = q - nb
        v = 90 * v / max(np.linalg.norm(v), 1e-9)
        ax.text(*(q + v), name, color=MAGENTA, fontsize=12, weight="bold", ha="center", va="center", zorder=8,
                bbox=dict(fc="white", ec=MAGENTA, lw=0.7, pad=1.2, alpha=0.92))
    W, H = d["grid"]["extent_m"]
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_aspect("equal")
    b = d["grid"]["bounds"]
    xt = np.arange(math.ceil(b["west"] * 120), math.floor(b["east"] * 120) + 1) / 120       # every 30"
    yt = np.arange(math.ceil(b["south"] * 120), math.floor(b["north"] * 120) + 1) / 120
    xt = xt[((xt - b["west"]) / (b["east"] - b["west"]) > 0.04) & ((xt - b["west"]) / (b["east"] - b["west"]) < 0.96)]
    yt = yt[((yt - b["south"]) / (b["north"] - b["south"]) > 0.05) & ((yt - b["south"]) / (b["north"] - b["south"]) < 0.95)]
    ax.set_xticks((xt - b["west"]) / (b["east"] - b["west"]) * (nx - 1) * s, [dms(v, True) for v in xt], fontsize=8)
    ax.set_yticks((yt - b["south"]) / (b["north"] - b["south"]) * (ny - 1) * s, [dms(v, False) for v in yt],
                  fontsize=8, rotation=90, va="center")
    ax.tick_params(length=5, width=0.8, top=True, right=False, direction="in")
    for spn in ax.spines.values():
        spn.set_linewidth(1.4)
    fig.text(0.065, 0.972, f"{d['area'].upper()} QUADRANGLE · {d['state'].upper()}", fontsize=14, weight="bold",
             va="top")
    fig.text(0.065, 0.938, "7.5-MINUTE SERIES STYLE (TOPOGRAPHIC)   ·   data: USGS 3DEP via AWS Terrain Tiles",
             fontsize=8.5, va="top")
    fig.text(0.845, 0.972, "ELEVATION: U.S. GEOLOGICAL SURVEY 3DEP\nWGS84 · ELEVATIONS IN METERS", fontsize=8, ha="right",
             va="top", linespacing=1.4)
    # scale bar: 1 km at map scale
    axw_in = 0.78 * fig.get_figwidth()
    frac = 1000 / W * 0.78
    x0 = 0.455 - frac / 2
    sax = fig.add_axes([x0, 0.055, frac, 0.012])
    for a0, a1, c in ((0, 250, "black"), (250, 500, "white"), (500, 1000, "black")):
        sax.add_patch(plt.Rectangle((a0, 0), a1 - a0, 1, fc=c, ec="black", lw=0.8))
    sax.set_xlim(0, 1000)
    sax.set_ylim(0, 1)
    sax.set_yticks([])
    sax.set_xticks([0, 250, 500, 1000], ["0", "250", "500", "1 KILOMETER"], fontsize=8)
    sax.tick_params(length=0, pad=2)
    for spn in sax.spines.values():
        spn.set_visible(False)
    ratio = W / (axw_in * 0.0254)
    fig.text(0.455, 0.083, f"SCALE 1:{int(round(ratio, -2)):,}".replace(",", " "), fontsize=9, weight="bold",
             ha="center")
    fig.text(0.455, 0.02, f"CONTOUR INTERVAL {ci} METERS  ·  INDEX CONTOURS EVERY {idx} METERS", fontsize=9,
             weight="bold", ha="center")
    # right column: north arrow and legend
    fig.patches.append(plt.Polygon([[0.905, 0.80], [0.92, 0.88], [0.935, 0.80], [0.92, 0.815]], closed=True,
                                   fc="black", transform=fig.transFigure))
    fig.text(0.92, 0.89, "N", fontsize=12, weight="bold", ha="center")
    lx, ly = 0.865, 0.70
    fig.text(lx, ly + 0.035, "LEGEND", fontsize=9, weight="bold")
    items = [("line", BROWN, 0.55, None, "Contour"), ("line", BROWN_IDX, 1.25, None, "Index contour"),
             ("line", RED, 1.5, (5, 2.5), "Trail"), ("patch", WATER, None, None, "Water"),
             ("patch", GREEN, None, None, "Woodland"), ("x", "black", None, None, "Spot elevation (m)"),
             ("sq", MAGENTA, None, None, "Trail start S / end E")]
    for k, (kind, c, lw, dash, label) in enumerate(items):
        y = ly - k * 0.04
        if kind == "line":
            ln = matplotlib.lines.Line2D([lx, lx + 0.025], [y, y], color=c, lw=lw, transform=fig.transFigure)
            if dash:
                ln.set_dashes(dash)
            fig.lines.append(ln)
        elif kind == "patch":
            fig.patches.append(plt.Rectangle((lx, y - 0.008), 0.025, 0.016, fc=c, ec="#777777", lw=0.5,
                                             transform=fig.transFigure))
        else:
            fig.lines.append(matplotlib.lines.Line2D([lx + 0.0125], [y], marker="x" if kind == "x" else "s",
                                                     color=c, ms=6, mew=1.0, transform=fig.transFigure))
        fig.text(lx + 0.032, y, label, fontsize=8, va="center")
    fig.text(0.865, 0.30, "Terrain: real elevation\n(USGS 3DEP, public\ndomain), lightly\nsmoothed. Trail is a\n"
             "drawn route for\nthis exercise.", fontsize=8, va="top", linespacing=1.35, color="#333333")
    fig.savefig(path, metadata={"Software": None})
    plt.close(fig)


# ------------------------------------------------------------------------------------------------ questions
def question(d):
    return (f"This is a topographic map of a real place, drawn in the style of a USGS 7.5-minute quadrangle. The "
            f"contour interval is {d['contour_interval_m']} meters, index contours (heavy brown lines, some labeled) "
            f"are every {d['index_interval_m']} meters, and elevations are in meters. A hiking trail is drawn as a "
            "dashed red line from the magenta square S to the magenta square E. How many contour lines (including "
            "index contours) does the trail cross between S and E? If it crosses the same contour line more than "
            "once, count every crossing. Answer with a whole number, for example 7.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(HERE / "tasks"))
    ap.add_argument("--seeds", default="1-10")
    a = ap.parse_args()
    lo, hi = (int(v) for v in a.seeds.split("-"))
    out = Path(a.out)
    for sub in ("images", "data"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    rows = []
    for seed in range(lo, hi + 1):
        got = sample(seed)
        if got is None:
            raise SystemExit(f"seed {seed}: no fair task found")
        d, G, Wt = got
        tid = f"realtopo-cross-{seed:06d}"
        np.save(out / "data" / f"{tid}.npy", G.astype(np.float32))
        np.save(out / "data" / f"{tid}_water.npy", Wt)
        rec = {"task_id": tid, "family": "realtopo", "seed": seed, "generator_version": VERSION,
               "params": {"contour_interval_m": d["contour_interval_m"], "crossings": d["answer_sampling"],
                          "trail_length_m": d["trail"]["length_m"]},
               "data": d, "grid_file": f"data/{tid}.npy", "water_file": f"data/{tid}_water.npy",
               "references": REFERENCES}
        (out / "data" / f"{tid}.json").write_text(json.dumps(rec, indent=1))
        # the image is drawn only from the saved files
        d2 = json.loads((out / "data" / f"{tid}.json").read_text())["data"]
        G2 = np.load(out / "data" / f"{tid}.npy").astype(np.float64)
        W2 = np.load(out / "data" / f"{tid}_water.npy")
        render(d2, G2, W2, out / "images" / f"{tid}.png")
        rows.append({"task_id": tid, "image": f"images/{tid}.png", "question": question(d),
                     "answer": d["answer_sampling"], "answer_type": "integer", "seed": seed,
                     "generator_version": VERSION, "question_type": "topo.crossings_real", "family": "realtopo",
                     "difficulty": {"contour_interval_m": d["contour_interval_m"], "crossings": d["answer_sampling"],
                                    "area": d["area"]},
                     "data": f"data/{tid}.json",
                     "checks": {"sampling_equals_drawn_contour_geometry": d["answer_sampling"] == d["answer_geometry"],
                                "crossings_40m_apart_and_from_ends": True, "no_grazing_2m_over_40m": True,
                                "no_touch_within_quarter_ci_at_turnarounds": True, "crossing_angle_ge_25deg": True,
                                "trail_avoids_water": True},
                     "references": REFERENCES})
        print(tid, d["area"], "CI", d["contour_interval_m"], "answer", d["answer_sampling"], "geom",
              d["answer_geometry"], "len", d["trail"]["length_m"], "attempt", d["attempt"], flush=True)
    (out / "tasks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))


if __name__ == "__main__":
    main()
