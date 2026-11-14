"""Real terrain: maps drawn from USGS 3DEP elevation (AWS Terrain Tiles stored in gen/topo/tiles/, offline).

Ported from Alex's spike results/spikes/real_terrain/gen.py (terrain loading, the trail builder and its
fairness rules, the quadrangle drawing) and fitted to contracts/FAMILY.md: the data JSON names the tiles and
the crop window, and the elevation grid, the image and both answers are rebuilt from that alone.

Templates on this base: `crossings` (count the contour lines a trail crosses), `sunset` (Naismith's rule
with the uphill crossings, minutes to spare before dark) and `flood` (follow the water downhill from a failed
dam to the one camp in its path).
"""
from __future__ import annotations

import functools
import math
from pathlib import Path

import numpy as np
from contourpy import contour_generator
from matplotlib.collections import LineCollection
from matplotlib.lines import Line2D
from matplotlib.patches import Polygon, Rectangle
from PIL import Image

from factory.render import new_figure, save_png, text_boxes, to_pixels

TILES = Path(__file__).resolve().parent / "tiles"
ZOOM = 13
CROP_W, CROP_H = 3200.0, 2400.0            # map window, meters (4:3)
UP = 3                                      # contours are traced on a 3x bilinear upsample of the grid
SEP_M, GRAZE_DZ, GRAZE_RUN = 40.0, 2.0, 40.0
TURN_FRAC, MIN_ANGLE = 0.25, 25.0
BOX_W, BOX_H = 1330.0, 330.0                # the incident box, meters on the map
KNOB = {1: (3, 6, 300.0), 2: (7, 10, 500.0), 3: (11, 20, 600.0)}       # fewest, most crossings, least trail length m
AREAS = [  # name, state, 2x2 tile mosaic (x0, y0), a named spot (lat, lon) every crop must contain
    {"key": "bear", "name": "Bear Mountain", "state": "New York", "x0": 2411, "y0": 3061, "anchor": (41.3126, -73.9888)},
    {"key": "breakneck", "name": "Breakneck Ridge", "state": "New York", "x0": 2412, "y0": 3057, "anchor": (41.4440, -73.9700)},
    {"key": "harriman", "name": "Harriman State Park", "state": "New York", "x0": 2409, "y0": 3063, "anchor": (41.2236, -74.0671)},
    {"key": "tam", "name": "Mount Tamalpais", "state": "California", "x0": 1305, "y0": 3161, "anchor": (37.9235, -122.5965)},
]
TRAILS = ["Ridge Trail", "Miners Trail", "Lookout Trail", "Aspen Trail", "Summit Trail", "Cedar Trail",
          "Juniper Trail", "Quarry Trail", "Basin Trail", "Pack Trail"]
GREEN, WATER, BROWN, BROWN_IDX, RED, MAGENTA, PAPER = "#dcebc8", "#a9d3ee", "#b5743a", "#8f4f1c", "#d7191c", "#b0127e", "#fffbe6"
WIDTH_PX, HEIGHT_PX, S = 1600, 1200, 1.5    # the factory renders at 100 dpi; sizes are points for a 150 dpi look


# ------------------------------------------------------------------------------------------------ terrain
def global_px_to_lonlat(X, Y):
    n = 256 * 2 ** ZOOM
    return X / n * 360 - 180, math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * Y / n))))


def lonlat_to_global_px(lat, lon):
    n = 256 * 2 ** ZOOM
    return (lon + 180) / 360 * n, (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n


def blur(a, sigma=1.0):
    r = int(math.ceil(3 * sigma))
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sigma) ** 2)
    k /= k.sum()
    p = np.pad(a, r, mode="edge")
    p = np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 0, p)
    return np.apply_along_axis(lambda v: np.convolve(v, k, mode="valid"), 1, p)


def _window(a, r, fn):
    v = np.lib.stride_tricks.sliding_window_view(np.pad(a, r, mode="edge"), (2 * r + 1, 2 * r + 1))
    return fn(v, axis=(-1, -2))


@functools.lru_cache(maxsize=None)
def mosaic(key):
    """One area's 2x2 tiles -> (raw elevation clamped at 0, smoothed elevation, water mask, meters per pixel)."""
    area = next(a for a in AREAS if a["key"] == key)
    rows = []
    for dy in (0, 1):
        row = []
        for dx in (0, 1):
            a = np.asarray(Image.open(TILES / f"{key}_{ZOOM}_{area['x0'] + dx}_{area['y0'] + dy}.png").convert("RGB")).astype(np.float64)
            row.append(a[..., 0] * 256 + a[..., 1] + a[..., 2] / 256 - 32768)       # terrarium encoding
        rows.append(np.hstack(row))
    raw = np.maximum(np.vstack(rows), 0.0)                 # river and sea pixels carry bathymetry artifacts below 0
    flat = (_window(raw, 1, np.max) - _window(raw, 1, np.min)) < 0.05               # hydro-flattened lakes
    lake = _window(_window(flat.astype(np.uint8), 2, np.min), 2, np.max).astype(bool) & flat
    wet = (raw <= 1.0) | lake
    wet = _window(_window(wet.astype(np.uint8), 2, np.min), 2, np.max).astype(bool)
    lat_c = global_px_to_lonlat(area["x0"] * 256 + 256, area["y0"] * 256 + 256)[1]
    s = 40075016.686 * math.cos(math.radians(lat_c)) / (256 * 2 ** ZOOM)
    return raw, blur(raw, 1.0), wet, s


def crop(key, c0, r0, nx, ny):
    """The elevation grid G (row 0 = south, float32 values) and water mask of one window."""
    _, sm, wet, _ = mosaic(key)
    return sm[r0:r0 + ny, c0:c0 + nx][::-1].astype(np.float32).astype(np.float64), wet[r0:r0 + ny, c0:c0 + nx][::-1]


def window_of(d):
    c = d["source"]["crop_px"]
    return crop(d["source"]["area_key"], c["col0"], c["row0"], c["nx"], c["ny"])


def bilinear(G, s, x, y):
    j, i = np.asarray(x, float) / s, np.asarray(y, float) / s
    j0 = np.clip(np.floor(j).astype(int), 0, G.shape[1] - 2)
    i0 = np.clip(np.floor(i).astype(int), 0, G.shape[0] - 2)
    fj, fi = j - j0, i - i0
    return (G[i0, j0] * (1 - fi) * (1 - fj) + G[i0, j0 + 1] * (1 - fi) * fj
            + G[i0 + 1, j0] * fi * (1 - fj) + G[i0 + 1, j0 + 1] * fi * fj)


def contour_lines(G, s, levels):
    ny, nx = G.shape
    xs = np.linspace(0, (nx - 1) * s, (nx - 1) * UP + 1)
    ys = np.linspace(0, (ny - 1) * s, (ny - 1) * UP + 1)
    X, Y = np.meshgrid(xs, ys)
    cg = contour_generator(x=xs, y=ys, z=bilinear(G, s, X, Y))
    return {int(l): [np.asarray(p) for p in cg.lines(l) if len(p) > 1] for l in levels}


# ------------------------------------------------------------------------------------------------ trail
def densify(pts, ds=1.0):
    pts = np.asarray(pts, float)
    out = [pts[:1]]
    for a, b in zip(pts[:-1], pts[1:]):
        n = max(2, int(math.ceil(np.linalg.norm(b - a) / ds)) + 1)
        out.append(a + (b - a) * np.linspace(0, 1, n)[1:, None])
    return np.vstack(out)


def _arc(p):
    return np.r_[0, np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))]


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


def _grad(G, s, x, y):
    e = 2 * s
    return np.array([bilinear(G, s, x + e, y) - bilinear(G, s, x - e, y),
                     bilinear(G, s, x, y + e) - bilinear(G, s, x, y - e)]) / (2 * e)


def random_route(rng, G, s, ci, margin=280.0):
    """A smooth winding route that sidehills at a steady grade, like a built trail."""
    for _ in range(40):
        p = np.array([rng.uniform(margin, CROP_W - margin), rng.uniform(margin, CROP_H - margin)])
        sign, side, ctrl, h = rng.choice([-1.0, 1.0]), rng.choice([-1.0, 1.0]), [p], rng.uniform(0, 2 * math.pi)
        for _ in range(int(rng.integers(10, 17))):
            g = _grad(G, s, p[0], p[1])
            m = float(np.linalg.norm(g))
            if m > 0.06 * ci / 10:
                off = math.acos(min(1.0, rng.uniform(0.30, 0.42) * ci / 20 / m))
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
        arc = _arc(q)
        D = np.sqrt(((q[:, None] - q[None]) ** 2).sum(-1))
        if (D[np.abs(arc[:, None] - arc[None]) > 300] < 150).any() or arc[-1] < 900:
            continue
        return pts
    return None


def crossings_sampled(G, s, pts, levels):
    """Way 1: walk the trail in 1 m steps on the bilinear grid; a crossing is a sign change of (z - level).
    Returns ([(arc_m, level, x, y, uphill)], z along the trail, arc)."""
    p = densify(pts, 1.0)
    seg = _arc(p)
    z = bilinear(G, s, p[:, 0], p[:, 1])
    found = []
    for l in levels:
        dz = z - l
        for i in np.where(np.sign(dz[:-1]) * np.sign(dz[1:]) < 0)[0]:
            found.append((float(seg[i]), int(l), float(p[i, 0]), float(p[i, 1]), bool(dz[i + 1] > dz[i])))
    return sorted(found), z, seg


def crossings_geometry(G, s, pts, lines):
    """Way 2: intersect the trail polyline with the contour polylines that are drawn (contourpy). A crossing
    is uphill when the ground 4 m further along the trail is higher than 4 m before. Returns (all, uphill)."""
    pts = np.asarray(pts, float)
    a, r = pts[:-1], pts[1:] - pts[:-1]
    lo, hi = pts.min(0) - 5, pts.max(0) + 5
    total = up = 0
    for segs in lines.values():
        for line in segs:
            if (line.max(0) < lo).any() or (line.min(0) > hi).any():
                continue
            c, sv = line[:-1], line[1:] - line[:-1]
            den = r[:, None, 0] * sv[None, :, 1] - r[:, None, 1] * sv[None, :, 0]
            ok = np.abs(den) > 1e-12
            den = np.where(ok, den, 1)
            w = c[None] - a[:, None]
            t = (w[..., 0] * sv[None, :, 1] - w[..., 1] * sv[None, :, 0]) / den
            u = (w[..., 0] * r[:, None, 1] - w[..., 1] * r[:, None, 0]) / den
            hit = ok & (t >= 0) & (t < 1) & (u >= 0) & (u < 1)
            total += int(hit.sum())
            for k, m in np.argwhere(hit):
                at = a[k] + t[k, m] * r[k]
                step = 4.0 * r[k] / max(np.linalg.norm(r[k]), 1e-9)
                up += int(float(bilinear(G, s, *(at + step))) > float(bilinear(G, s, *(at - step))))
    return total, up


def _angle_bad(G, s, p, i, x, y):
    t = p[min(i + 4, len(p) - 1)] - p[max(i - 4, 0)]
    g = _grad(G, s, x, y)
    return abs(t @ g) / max(np.linalg.norm(t) * np.linalg.norm(g), 1e-12) < math.sin(math.radians(MIN_ANGLE))


def unfair(G, s, p, z, found, levels, ci):
    """Why a careful person could miscount: grazing a level, a near-tangent touch, or a shallow crossing angle."""
    for l in levels:
        near = np.abs(z - l) < GRAZE_DZ
        if near.any():
            e = np.diff(np.r_[0, near.astype(int), 0])
            if ((np.where(e == -1)[0] - np.where(e == 1)[0]) > GRAZE_RUN).any():
                return "graze"
    zz = np.convolve(z, np.ones(9) / 9, mode="same")[5:-5]
    dz = np.diff(zz)
    lv = np.array(levels, float)
    for i in np.where(np.sign(dz[1:]) * np.sign(dz[:-1]) < 0)[0] + 6:
        if np.abs(lv - z[i]).min() < TURN_FRAC * ci:
            return "touch"
    seg = _arc(p)
    for a, l, x, y, _ in found:
        if _angle_bad(G, s, p, int(np.searchsorted(seg, a)), x, y):
            return "angle"
    return None


def pick_piece(G, s, Wt, pts, levels, ci, rng, lo, hi, min_len):
    """Choose S and E on a long route so the piece between them passes every fairness rule (re-checked later)."""
    p = densify(pts, 1.0)
    found, z, seg = crossings_sampled(G, s, pts, levels)
    pos = np.array([f[0] for f in found])
    L = float(seg[-1])
    if len(pos) < lo:
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
    for a, l, x, y, _ in found:
        if _angle_bad(G, s, p, int(np.searchsorted(seg, a)), x, y):
            bad.append((a - 20, a + 20))
    for a, b in zip(pos[:-1], pos[1:]):
        if b - a < SEP_M:
            bad.append((a, b))
    edges = np.r_[0.0, pos, L]
    spots = []                                       # S/E candidates: one per gap between crossings
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
            if lo <= kj - ki <= hi and sE - sS >= min_len and not any(x1 >= sS and x0 <= sE for x0, x1 in bad):
                good.append((kj - ki, sS, sE))
    if not good:
        return None
    top = max(g[0] for g in good)                    # prefer long pieces: more crossings, harder to count
    good = [g for g in good if g[0] >= top - 2]
    _, sS, sE = good[int(rng.integers(len(good)))]
    i0, i1 = int(np.searchsorted(seg, sS)), int(np.searchsorted(seg, sE))
    return np.round(p[list(range(i0, i1, 5)) + [i1]], 2)


# ------------------------------------------------------------------------------------------------ sampling
def clock(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _box_corner(pts):
    for x0, y0 in ((35, CROP_H - 35 - BOX_H), (CROP_W - 35 - BOX_W, CROP_H - 35 - BOX_H), (35, 35), (CROP_W - 35 - BOX_W, 35)):
        if not ((pts[:, 0] > x0 - 150) & (pts[:, 0] < x0 + BOX_W + 150) & (pts[:, 1] > y0 - 150) & (pts[:, 1] < y0 + BOX_H + 150)).any():
            return [float(x0), float(y0)]
    return None


def sample(rng, seed, template, difficulty, tries=40):
    """The structured data for one task, or None when no fair trail turns up in `tries` crop windows."""
    lo, hi, min_len = KNOB[difficulty]
    areas = AREAS if difficulty < 3 else [a for a in AREAS if a["key"] != "harriman"]   # Harriman's gentle relief
    area = areas[seed % len(areas)]                                                    # cannot give 11 crossings
    raw, _, _, s = mosaic(area["key"])
    X0, Y0 = area["x0"] * 256, area["y0"] * 256
    nx, ny = int(CROP_W / s) + 2, int(CROP_H / s) + 2
    ax_, ay_ = lonlat_to_global_px(*area["anchor"])
    ac, ar = ax_ - X0, ay_ - Y0
    m = int(400 / s)
    for attempt in range(tries):
        c0 = int(rng.integers(max(4, int(ac) - nx + m), min(512 - nx - 4, int(ac) - m) + 1))
        r0 = int(rng.integers(max(4, int(ar) - ny + m), min(512 - ny - 4, int(ar) - m) + 1))
        if (raw[r0:r0 + ny, c0:c0 + nx] <= 1.0).mean() > 0.10:
            continue                                                   # too much river or sea in the window
        G, Wt = crop(area["key"], c0, r0, nx, ny)
        ci = 20 if float(G.max() - G.min()) > 250 else 10
        levels = [l for l in range(int(math.ceil(max(G.min(), 0.5) / ci)) * ci, int(G.max()) + 1, ci) if l > 0]
        for _ in range(15):
            route = random_route(rng, G, s, ci)
            pts = None if route is None else pick_piece(G, s, Wt, route, levels, ci, rng, lo, hi, min_len)
            if pts is None:
                continue
            q = densify(pts, 5.0)
            jj, ii = np.round(q[:, 0] / s).astype(int), np.round(q[:, 1] / s).astype(int)
            if Wt[np.clip(ii, 0, ny - 1), np.clip(jj, 0, nx - 1)].any():
                continue
            found, z, seg = crossings_sampled(G, s, pts, levels)
            pos, L = np.array([f[0] for f in found]), float(seg[-1])
            if not lo <= len(found) <= hi or pos.min() < SEP_M or pos.max() > L - SEP_M or (np.diff(pos) < SEP_M).any():
                continue
            if unfair(G, s, densify(pts, 1.0), z, found, levels, ci):
                continue
            up = sum(f[4] for f in found)
            if template == "sunset" and up < 2:
                continue                                               # the climb has to matter
            lines = contour_lines(G, s, levels)
            if crossings_geometry(G, s, pts, lines) != (len(found), up):
                continue
            corner = _box_corner(q)
            if corner is None:
                continue
            return _data(rng, area, attempt, c0, r0, nx, ny, s, G, Wt, ci, levels, pts, L, lines, corner, template, up)
    return None


def _data(rng, area, attempt, c0, r0, nx, ny, s, G, Wt, ci, levels, pts, L, lines, corner, template, up):
    X0, Y0 = area["x0"] * 256, area["y0"] * 256
    lon_w, lat_n = global_px_to_lonlat(X0 + c0, Y0 + r0)
    lon_e, lat_s = global_px_to_lonlat(X0 + c0 + (nx - 1), Y0 + r0 + (ny - 1))
    idx = ci * 5
    tq = densify(pts, 5.0)
    bx, by = corner

    def near_trail(p, r):
        return float(np.sqrt(((tq - p) ** 2).sum(1)).min()) < r

    def in_box(p, pad=110):
        return bx - pad <= p[0] <= bx + BOX_W + pad and by - pad <= p[1] <= by + BOX_H + pad

    ends = []                                           # where the S and E labels are printed
    for q, nb in ((tq[0], tq[min(8, len(tq) - 1)]), (tq[-1], tq[max(-9, -len(tq))])):
        v = q - nb
        ends.append(q + 90 * v / max(np.linalg.norm(v), 1e-9))
    labels = []
    for l in levels:                                    # index-contour labels on long index lines
        if l % idx:
            continue
        for line in lines[l]:
            if len(line) < 60:
                continue
            for k in rng.permutation(np.arange(10, len(line) - 10, 6))[:60]:
                p = line[k]
                if not (110 < p[0] < CROP_W - 110 and 80 < p[1] < CROP_H - 80) or in_box(p) or near_trail(p, 130):
                    continue
                if any(math.hypot(p[0] - e[0], p[1] - e[1]) < 200 for e in ends) or \
                        any(math.hypot(p[0] - q["x"], p[1] - q["y"]) < 300 for q in labels):
                    continue
                t = line[k + 3] - line[k - 3]
                ang = math.degrees(math.atan2(t[1], t[0]))
                ang = ang - 180 if ang > 90 else ang + 180 if ang < -90 else ang
                labels.append({"x": round(float(p[0]), 1), "y": round(float(p[1]), 1), "level": int(l), "angle": round(ang, 1)})
                break
    r = int(round(225 / s))
    spots = []                                          # spot heights at local maxima
    for i, j in sorted(np.argwhere((G == _window(G, r, np.max)) & (G - G.min() > 30)).tolist(), key=lambda ij: -G[ij[0], ij[1]]):
        p = np.array([j * s, i * s])
        if not (120 < p[0] < CROP_W - 260 and 100 < p[1] < CROP_H - 120) or near_trail(p, 150) or in_box(p, 200):
            continue
        if any(math.hypot(p[0] - e[0], p[1] - e[1]) < 260 for e in ends) or \
                any(math.hypot(p[0] - q["x"], p[1] - q["y"]) < 260 for q in labels + spots):
            continue
        spots.append({"x": round(float(p[0]), 1), "y": round(float(p[1]), 1), "elev": int(round(G[i, j]))})
        if len(spots) == 4:
            break
    name = str(rng.choice(TRAILS))
    d = {"area": area["name"], "state": area["state"], "attempt": attempt,
         "source": {"area_key": area["key"],
                    "tiles": [f"terrarium/{ZOOM}/{area['x0'] + dx}/{area['y0'] + dy}.png" for dy in (0, 1) for dx in (0, 1)],
                    "crop_px": {"col0": c0, "row0": r0, "nx": nx, "ny": ny},
                    "processing": "elevation clamped at 0 m, Gaussian blur sigma 1 px, float32, bilinear interpolation"},
         "grid": {"spacing_m": round(s, 4), "shape": [ny, nx], "extent_m": [CROP_W, CROP_H],
                  "bounds": {"west": round(lon_w, 6), "east": round(lon_e, 6), "south": round(lat_s, 6), "north": round(lat_n, 6)},
                  "elev_min_m": round(float(G.min()), 1), "elev_max_m": round(float(G.max()), 1)},
         "contour_interval_m": ci, "index_interval_m": idx, "levels": levels,
         "trail": {"name": name, "pts": pts.tolist(), "length_m": round(L, 1)},
         "index_labels": labels, "spot_heights": spots}
    if template == "sunset":
        flat = int(round(15 * L / 1000))                               # Naismith: 15 minutes per kilometer
        per_line = 4 if ci == 20 else 2                                # 300 m of climb per hour
        now = int(rng.integers(14 * 12, 17 * 12)) * 5
        spare = int(rng.integers(-45, 76))
        d["mission"] = {"template": "sunset", "from": "S", "to": "H", "flat_walk_min": flat, "now_min": now,
                        "sunset_min": now + flat + per_line * up + spare, "minutes_per_uphill_contour": per_line}
        d["box"] = {"xy": corner, "title": f"LOST HIKER  ·  NOW {clock(now)}  ·  SUNSET {clock(d['mission']['sunset_min'])}",
                    "body": f"Hiker at S must reach the hut at H before dark.\n{name}: {flat} min of walking on the flat."}
    else:
        d["mission"] = {"template": "crossings", "from": "S", "to": "E"}
        d["box"] = {"xy": corner, "title": "RESCUE CARRY  ·  STRETCHER TEAM S TO E",
                    "body": f"Team carries the casualty along the {name}.\nLog every contour line the trail crosses."}
    return d


# ------------------------------------------------------------------------------------------------ flash flood
FLOOD_KNOB = {1: (3, 60, 450.0), 2: (4, 80, 350.0), 3: (6, 100, 250.0)}   # camps, route steps to the camp (x10 m), dry gap m
HIT_M = 40.0


def descend(G, s, Wt, start, ds=10.0, e=None, steps=500):
    """The way water runs: steepest descent on the bilinear grid, until it reaches water, a hollow or the map edge."""
    e = 2 * s if e is None else e
    p, out = np.array(start, float), []
    z_prev = float("inf")
    ny, nx = G.shape
    for _ in range(steps):
        if not (0 < p[0] < CROP_W and 0 < p[1] < CROP_H):
            break
        z = float(bilinear(G, s, p[0], p[1]))
        if z > z_prev + 0.5 or Wt[min(ny - 1, int(round(p[1] / s))), min(nx - 1, int(round(p[0] / s)))]:
            break
        out.append([round(float(p[0]), 1), round(float(p[1]), 1)])
        z_prev = z
        g = np.array([bilinear(G, s, p[0] + e, p[1]) - bilinear(G, s, p[0] - e, p[1]),
                      bilinear(G, s, p[0], p[1] + e) - bilinear(G, s, p[0], p[1] - e)]) / (2 * e)
        n = float(np.linalg.norm(g))
        if n < 0.01:
            break
        p = p - ds * g / n
    return out


def _gap(q, route):
    r = np.asarray(route, float)
    return float(np.sqrt(((r - np.asarray(q, float)) ** 2).sum(1)).min())


def sample_flood(rng, seed, difficulty, tries=60):
    n, min_k, gap_m = FLOOD_KNOB[difficulty]
    area = AREAS[seed % len(AREAS)]
    raw, _, _, s = mosaic(area["key"])
    X0, Y0 = area["x0"] * 256, area["y0"] * 256
    nx, ny = int(CROP_W / s) + 2, int(CROP_H / s) + 2
    ax_, ay_ = lonlat_to_global_px(*area["anchor"])
    ac, ar = ax_ - X0, ay_ - Y0
    m = int(400 / s)
    for attempt in range(tries):
        c0 = int(rng.integers(max(4, int(ac) - nx + m), min(512 - nx - 4, int(ac) - m) + 1))
        r0 = int(rng.integers(max(4, int(ar) - ny + m), min(512 - ny - 4, int(ar) - m) + 1))
        if (raw[r0:r0 + ny, c0:c0 + nx] <= 1.0).mean() > 0.10:
            continue
        G, Wt = crop(area["key"], c0, r0, nx, ny)
        ci = 20 if float(G.max() - G.min()) > 250 else 10
        levels = [l for l in range(int(math.ceil(max(G.min(), 0.5) / ci)) * ci, int(G.max()) + 1, ci) if l > 0]
        zlo, zhi = np.quantile(G, 0.55), np.quantile(G, 0.95)

        def wet(q):
            return bool(Wt[min(ny - 1, int(round(q[1] / s))), min(nx - 1, int(round(q[0] / s)))])

        for _ in range(25):
            dam = [round(float(rng.uniform(350, CROP_W - 350)), 1), round(float(rng.uniform(300, CROP_H - 300)), 1)]
            z_dam = float(bilinear(G, s, *dam))
            if not zlo <= z_dam <= zhi or wet(dam):
                continue
            route = descend(G, s, Wt, dam)
            if len(route) < min_k + 20:
                continue
            routes = [route, descend(G, s, Wt, dam, ds=4.0, e=0.75 * s, steps=1250)] + \
                     [descend(G, s, Wt, [dam[0] + dx, dam[1] + dy]) for dx, dy in ((20, 0), (-20, 0), (0, 20), (0, -20))]
            k = int(rng.integers(min_k, len(route) - 10))
            hit = route[k]
            if not (260 < hit[0] < CROP_W - 260 and 220 < hit[1] < CROP_H - 220) or wet(hit):
                continue
            if any(_gap(hit, r) > HIT_M - 10 for r in routes):
                continue                                               # the routes disagree at the camp
            first = np.array(route[25]) - np.array(dam)                # where the water sets off (first 250 m)

            def off_line(q):
                v = np.array(q) - np.array(dam)
                return math.degrees(math.acos(max(-1.0, min(1.0, float(first @ v / (np.linalg.norm(first) * np.linalg.norm(v)))))))

            dry = []
            for _ in range(1500):
                q = [round(float(rng.uniform(260, CROP_W - 260)), 1), round(float(rng.uniform(220, CROP_H - 220)), 1)]
                if wet(q) or float(bilinear(G, s, *q)) > z_dam - 30 or not 450 <= math.dist(q, dam) <= 2600:
                    continue                                           # every camp is below the dam
                if any(math.dist(q, o) < 330 for o in dry + [hit, dam]) or min(_gap(q, r) for r in routes) < gap_m:
                    continue
                dry.append(q)
                if len(dry) == n - 1:
                    break
            if len(dry) < n - 1:
                continue
            if difficulty == 3 and not (off_line(hit) >= 15 and any(off_line(q) < off_line(hit) for q in dry)):
                continue                          # the route must bend: a dry camp lies more "straight below" the dam
            camps = [hit] + dry
            camps = [camps[i] for i in rng.permutation(n)]
            pts = np.array([dam] + camps + route)
            corner = _box_corner(pts)
            if corner is None:
                continue
            lines = contour_lines(G, s, levels)
            labels, spots = _flood_labels(rng, G, s, levels, ci * 5, lines, corner, np.array(route), np.array([dam] + camps))
            if len(labels) < 3:
                continue
            lon_w, lat_n = global_px_to_lonlat(X0 + c0, Y0 + r0)
            lon_e, lat_s = global_px_to_lonlat(X0 + c0 + (nx - 1), Y0 + r0 + (ny - 1))
            names = [f"C{i + 1}" for i in range(n)]
            return {"area": area["name"], "state": area["state"], "attempt": attempt,
                    "source": {"area_key": area["key"],
                               "tiles": [f"terrarium/{ZOOM}/{area['x0'] + dx}/{area['y0'] + dy}.png" for dy in (0, 1) for dx in (0, 1)],
                               "crop_px": {"col0": c0, "row0": r0, "nx": nx, "ny": ny},
                               "processing": "elevation clamped at 0 m, Gaussian blur sigma 1 px, float32, bilinear interpolation"},
                    "grid": {"spacing_m": round(s, 4), "shape": [ny, nx], "extent_m": [CROP_W, CROP_H],
                             "bounds": {"west": round(lon_w, 6), "east": round(lon_e, 6), "south": round(lat_s, 6), "north": round(lat_n, 6)},
                             "elev_min_m": round(float(G.min()), 1), "elev_max_m": round(float(G.max()), 1)},
                    "contour_interval_m": ci, "index_interval_m": ci * 5, "levels": levels,
                    "points": [{"name": "D", "x": dam[0], "y": dam[1], "shape": "square", "label_dx": 75.0, "label_dy": 75.0}] +
                              [{"name": nm, "x": q[0], "y": q[1], "shape": "dot", "label_dx": 80.0, "label_dy": 75.0}
                               for nm, q in zip(names, camps)],
                    "index_labels": labels, "spot_heights": spots,
                    "mission": {"template": "flood", "dam": "D", "camps": names, "hit_radius_m": HIT_M},
                    "box": {"xy": corner, "title": "FLASH FLOOD  ·  DAM FAILED AT D",
                            "body": f"Water runs straight downhill from D.\nWhich camp, C1 to C{n}, is in its path?"}}
    return None


def _flood_labels(rng, G, s, levels, idx, lines, corner, route, marks):
    bx, by = corner
    anchors = marks + np.array([80.0, 75.0])

    def in_box(p, pad=110):
        return bx - pad <= p[0] <= bx + BOX_W + pad and by - pad <= p[1] <= by + BOX_H + pad

    def near(p, pts, r):
        return float(np.sqrt(((pts - p) ** 2).sum(1)).min()) < r

    labels = []
    for l in levels:
        if l % idx:
            continue
        for line in lines[l]:
            if len(line) < 60:
                continue
            for k in rng.permutation(np.arange(10, len(line) - 10, 6))[:60]:
                p = line[k]
                if not (110 < p[0] < CROP_W - 110 and 80 < p[1] < CROP_H - 80) or in_box(p):
                    continue
                if near(p, route, 110) or near(p, marks, 170) or near(p, anchors, 190) or \
                        any(math.hypot(p[0] - q["x"], p[1] - q["y"]) < 300 for q in labels):
                    continue
                t = line[k + 3] - line[k - 3]
                ang = math.degrees(math.atan2(t[1], t[0]))
                ang = ang - 180 if ang > 90 else ang + 180 if ang < -90 else ang
                labels.append({"x": round(float(p[0]), 1), "y": round(float(p[1]), 1), "level": int(l), "angle": round(ang, 1)})
                break
    r = int(round(225 / s))
    spots = []
    for i, j in sorted(np.argwhere((G == _window(G, r, np.max)) & (G - G.min() > 30)).tolist(), key=lambda ij: -G[ij[0], ij[1]]):
        p = np.array([j * s, i * s])
        if not (120 < p[0] < CROP_W - 260 and 100 < p[1] < CROP_H - 120) or in_box(p, 200):
            continue
        if near(p, marks, 220) or near(p, anchors, 240) or any(math.hypot(p[0] - q["x"], p[1] - q["y"]) < 260 for q in labels + spots):
            continue
        spots.append({"x": round(float(p[0]), 1), "y": round(float(p[1]), 1), "elev": int(round(G[i, j]))})
        if len(spots) == 4:
            break
    return labels, spots


def _flood_pick(d, route):
    pts = {p["name"]: [p["x"], p["y"]] for p in d["points"]}
    gaps = {c: _gap(pts[c], route) for c in d["mission"]["camps"]}
    hit = [c for c, g in gaps.items() if g <= d["mission"]["hit_radius_m"]]
    return (hit[0] if len(hit) == 1 else None), gaps, pts


def answer_flood(d):
    G, Wt = window_of(d)
    s = d["grid"]["spacing_m"]
    dam = next([p["x"], p["y"]] for p in d["points"] if p["name"] == "D")
    route = descend(G, s, Wt, dam)
    ans, gaps, pts = _flood_pick(d, route)
    steps = {"dam_elev_m": round(float(bilinear(G, s, *dam)), 1), "water_route_length_m": round(10.0 * (len(route) - 1), 1),
             "camps": [{"camp": c, "elev_m": round(float(bilinear(G, s, *pts[c])), 1),
                        "distance_to_water_route_m": round(g, 1), "flooded": c == ans} for c, g in gaps.items()]}
    return ans, steps, {"water_route": route, "flooded_camp": ans}


def independent_flood(d):
    """Second way: a finer descent (4 m steps, a tighter slope stencil) on the same grid."""
    G, Wt = window_of(d)
    s = d["grid"]["spacing_m"]
    dam = next([p["x"], p["y"]] for p in d["points"] if p["name"] == "D")
    return _flood_pick(d, descend(G, s, Wt, dam, ds=4.0, e=0.75 * s, steps=1250))[0]


def ask_flood(d):
    camps = d["mission"]["camps"]
    return {"answer_type": "label", "question": (
        f"This is a topographic map of a real place ({d['area']}, {d['state']}), drawn in the style of a USGS "
        f"7.5-minute quadrangle. The contour interval is {d['contour_interval_m']} meters, index contours (heavy brown "
        f"lines, some labeled) are every {d['index_interval_m']} meters, and elevations are in meters. "
        "Flash flood: the dam at the magenta square D has failed. The water runs downhill from D, always in the "
        "direction of steepest descent, so its path crosses every contour line at a right angle. "
        f"{len(camps)} campsites are marked with magenta points, {camps[0]} to {camps[-1]}, all lower than the dam. "
        "Exactly one of them lies in the water's path. Which campsite does the water reach? Answer with the campsite "
        f"name, for example {camps[1]}.")}


# ------------------------------------------------------------------------------------------------ answers
def answer(d):
    """(answer, steps, overlay) from the data alone, by walking the trail on the bilinear grid."""
    G, _ = window_of(d)
    s, pts = d["grid"]["spacing_m"], np.array(d["trail"]["pts"])
    found, _, _ = crossings_sampled(G, s, pts, d["levels"])
    total, up = len(found), sum(f[4] for f in found)
    overlay = {"route": d["trail"]["pts"], "crossings": [{"x": round(x, 1), "y": round(y, 1), "level": l, "uphill": u}
                                                           for _, l, x, y, u in found]}
    if d["mission"]["template"] == "crossings":
        return total, {"contour_crossings": total, "uphill": up, "downhill": total - up,
                       "trail_length_m": d["trail"]["length_m"], "levels_crossed": [f[1] for f in found]}, overlay
    m = d["mission"]
    walk = m["flat_walk_min"] + m["minutes_per_uphill_contour"] * up
    daylight = m["sunset_min"] - m["now_min"]
    steps = {"flat_walk_min": m["flat_walk_min"], "uphill_contour_crossings": up, "downhill_contour_crossings": total - up,
             "minutes_for_ascent": m["minutes_per_uphill_contour"] * up, "walking_minutes": walk, "daylight_minutes": daylight,
             "arrival": clock(m["now_min"] + walk),
             "wrong_if_every_crossing_counted": daylight - m["flat_walk_min"] - m["minutes_per_uphill_contour"] * total,
             "wrong_if_climb_ignored": daylight - m["flat_walk_min"]}
    return daylight - walk, steps, overlay


def independent(d):
    """The answer again, from the contour polylines that are drawn (contourpy) intersected with the trail."""
    G, _ = window_of(d)
    s = d["grid"]["spacing_m"]
    total, up = crossings_geometry(G, s, np.array(d["trail"]["pts"]), contour_lines(G, s, d["levels"]))
    if d["mission"]["template"] == "crossings":
        return total
    m = d["mission"]
    return m["sunset_min"] - m["now_min"] - m["flat_walk_min"] - m["minutes_per_uphill_contour"] * up


def ask(d):
    ci, idx, name = d["contour_interval_m"], d["index_interval_m"], d["trail"]["name"]
    intro = (f"This is a topographic map of a real place ({d['area']}, {d['state']}), drawn in the style of a USGS "
             f"7.5-minute quadrangle. The contour interval is {ci} meters, index contours (heavy brown lines, some "
             f"labeled) are every {idx} meters, and elevations are in meters. ")
    if d["mission"]["template"] == "crossings":
        return {"answer_type": "integer", "question": intro + (
            f"Rescue carry: a stretcher team carries a casualty along the {name} (dashed red line) from the magenta "
            "square S to the magenta square E. To pace the carry, the team leader logs every contour line the trail "
            "crosses. How many contour lines (index contours included) does the trail cross between S and E? If it "
            "crosses the same contour line more than once, count every crossing. Answer with a whole number, for "
            "example 7.")}
    per = d["mission"]["minutes_per_uphill_contour"]
    return {"answer_type": "integer", "question": intro + (
        f"A lost hiker at the magenta square S must reach the hut at the magenta square H along the {name} (dashed "
        "red line) before dark. The incident box on the map gives the time now, the time of sunset and the walking "
        "time for the trail's length on flat ground. By Naismith's rule the climb adds time: add "
        f"{per} minutes for every contour line the trail crosses going uphill (each one is {ci} m of climb, at 300 m "
        "of climb per hour). Contour lines crossed going downhill add no time. How many minutes before sunset does "
        "the hiker reach the hut? Give a negative number if the hiker arrives after sunset. Answer with a whole "
        "number of minutes, for example 12 or -7.")}


# ------------------------------------------------------------------------------------------------ drawing
def _dms(v, lon):
    h = ("W" if v < 0 else "E") if lon else ("S" if v < 0 else "N")
    v = abs(v)
    sec = int(round((v - int(v)) * 3600))
    return f"{int(v)}°{sec // 60:02d}'{sec % 60:02d}\"{h}"


def render(d, path):
    """Draw the PNG from the data dict (plus the tiles it names). Returns the layout for the validator."""
    G, Wt = window_of(d)
    s, ci, idx = d["grid"]["spacing_m"], d["contour_interval_m"], d["index_interval_m"]
    fig = new_figure(WIDTH_PX, HEIGHT_PX)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0.065, 0.115, 0.78, 0.78])
    ax.set_facecolor(GREEN)
    ny, nx = G.shape
    if Wt.any():                                      # smooth shoreline: contour the blurred mask at 0.5
        ax.contourf(np.arange(nx) * s, np.arange(ny) * s, blur(Wt.astype(np.float64), 1.2), levels=[0.5, 2.0],
                    colors=[WATER], zorder=1)
    for l, segs in contour_lines(G, s, d["levels"]).items():
        major = l % idx == 0
        ax.add_collection(LineCollection(segs, colors=BROWN_IDX if major else BROWN,
                                         linewidths=(1.25 if major else 0.55) * S, zorder=2))
    for lb in d["index_labels"]:
        ax.text(lb["x"], lb["y"], str(lb["level"]), color=BROWN_IDX, fontsize=8 * S, rotation=lb["angle"],
                rotation_mode="anchor", ha="center", va="center", zorder=5, bbox=dict(fc=GREEN, ec="none", pad=0.45))
    for sp in d["spot_heights"]:
        ax.plot(sp["x"], sp["y"], marker="x", color="black", ms=4.5 * S, mew=1.0 * S, zorder=6)
        ax.text(sp["x"] + 35, sp["y"] - 10, str(sp["elev"]), fontsize=8 * S, va="top", zorder=6)
    marks, p = [], None
    if d.get("trail"):
        p = np.array(d["trail"]["pts"])
        ax.plot(p[:, 0], p[:, 1], color=RED, lw=1.5 * S, dashes=(5, 2.5), zorder=7, solid_capstyle="butt")
        for name, q, nb in ((d["mission"]["from"], p[0], p[min(8, len(p) - 1)]), (d["mission"]["to"], p[-1], p[max(-9, -len(p))])):
            ax.plot(*q, marker="s", color=MAGENTA, ms=7.5 * S, mec="white", mew=0.9 * S, zorder=8)
            v = q - nb
            v = 90 * v / max(np.linalg.norm(v), 1e-9)
            ax.text(*(q + v), name, color=MAGENTA, fontsize=12 * S, weight="bold", ha="center", va="center", zorder=8,
                    bbox=dict(fc="white", ec=MAGENTA, lw=0.7 * S, pad=1.8, alpha=0.92))
            marks.append((name, q))
    for pt in d.get("points", []):
        q = np.array([pt["x"], pt["y"]])
        ax.plot(*q, marker="s" if pt["shape"] == "square" else "o", color=MAGENTA, ms=7.5 * S, mec="white",
                mew=0.9 * S, zorder=8)
        ax.text(q[0] + pt["label_dx"], q[1] + pt["label_dy"], pt["name"], color=MAGENTA, fontsize=12 * S, weight="bold",
                ha="center", va="center", zorder=8, bbox=dict(fc="white", ec=MAGENTA, lw=0.7 * S, pad=1.8, alpha=0.92))
        marks.append((pt["name"], q))
    bx, by = d["box"]["xy"]
    ax.add_patch(Rectangle((bx, by), BOX_W, BOX_H, fc=PAPER, ec="#8a1c1c", lw=1.4 * S, zorder=9))
    ax.text(bx + 35, by + BOX_H - 40, d["box"]["title"], fontsize=8.5 * S, weight="bold", color="#8a1c1c", va="top", zorder=10)
    ax.text(bx + 35, by + BOX_H - 145, d["box"]["body"], fontsize=7.4 * S, va="top", zorder=10, linespacing=1.35)
    W, H = d["grid"]["extent_m"]
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_aspect("equal")
    b = d["grid"]["bounds"]
    xt = np.arange(math.ceil(b["west"] * 120), math.floor(b["east"] * 120) + 1) / 120       # every 30 arc-seconds
    yt = np.arange(math.ceil(b["south"] * 120), math.floor(b["north"] * 120) + 1) / 120
    fx, fy = (xt - b["west"]) / (b["east"] - b["west"]), (yt - b["south"]) / (b["north"] - b["south"])
    xt, fx, yt, fy = xt[(fx > 0.07) & (fx < 0.93)], fx[(fx > 0.07) & (fx < 0.93)], yt[(fy > 0.10) & (fy < 0.90)], fy[(fy > 0.10) & (fy < 0.90)]
    ax.set_xticks(fx * (nx - 1) * s, [_dms(v, True) for v in xt], fontsize=8 * S)
    ax.set_yticks(fy * (ny - 1) * s, [_dms(v, False) for v in yt], fontsize=8 * S, rotation=90, va="center")
    ax.tick_params(length=5 * S, width=0.8 * S, top=True, right=False, direction="in")
    for spn in ax.spines.values():
        spn.set_linewidth(1.4 * S)
    fig.text(0.065, 0.972, f"{d['area'].upper()} QUADRANGLE · {d['state'].upper()}", fontsize=14 * S, weight="bold", va="top")
    fig.text(0.065, 0.938, "7.5-MINUTE SERIES STYLE (TOPOGRAPHIC)   ·   data: USGS 3DEP via AWS Terrain Tiles",
             fontsize=8.5 * S, va="top")
    fig.text(0.845, 0.972, "ELEVATION: U.S. GEOLOGICAL SURVEY 3DEP\nWGS84 · ELEVATIONS IN METERS", fontsize=8 * S, ha="right",
             va="top", linespacing=1.4)
    frac = 1000 / W * 0.78                            # scale bar: 1 km at map scale
    sax = fig.add_axes([0.455 - frac / 2, 0.055, frac, 0.012])
    for a0, a1, c in ((0, 250, "black"), (250, 500, "white"), (500, 1000, "black")):
        sax.add_patch(Rectangle((a0, 0), a1 - a0, 1, fc=c, ec="black", lw=0.8 * S))
    sax.set_xlim(0, 1000)
    sax.set_ylim(0, 1)
    sax.set_yticks([])
    sax.set_xticks([0, 250, 500, 1000], ["0", "250", "500", "1 KILOMETER"], fontsize=8 * S)
    sax.tick_params(length=0, pad=3)
    for spn in sax.spines.values():
        spn.set_visible(False)
    ratio = W / (0.78 * WIDTH_PX / 150 * 0.0254)
    fig.text(0.455, 0.085, f"SCALE 1:{int(round(ratio, -2)):,}".replace(",", " "), fontsize=9 * S, weight="bold", ha="center")
    fig.text(0.455, 0.012, f"CONTOUR INTERVAL {ci} METERS  ·  INDEX CONTOURS EVERY {idx} METERS", fontsize=9 * S,
             weight="bold", ha="center")
    fig.add_artist(Polygon([[0.905, 0.80], [0.92, 0.88], [0.935, 0.80], [0.92, 0.815]], closed=True, fc="black",
                           transform=fig.transFigure))
    fig.text(0.92, 0.89, "N", fontsize=12 * S, weight="bold", ha="center")
    lx, ly = 0.865, 0.70
    fig.text(lx, ly + 0.035, "LEGEND", fontsize=9 * S, weight="bold")
    items = [("line", BROWN, 0.55, None, "Contour"), ("line", BROWN_IDX, 1.25, None, "Index contour"),
             ("line", RED, 1.5, (5, 2.5), "Trail"), ("patch", WATER, None, None, "Water"),
             ("patch", GREEN, None, None, "Woodland"), ("x", "black", None, None, "Spot elevation (m)"),
             ("sq", MAGENTA, None, None, "Marked point")]
    if not d.get("trail"):
        items = [it for it in items if it[4] != "Trail"]
    for k, (kind, c, lw, dash, label) in enumerate(items):
        y = ly - k * 0.04
        if kind == "line":
            ln = Line2D([lx, lx + 0.025], [y, y], color=c, lw=lw * S, transform=fig.transFigure)
            if dash:
                ln.set_dashes(dash)
            fig.add_artist(ln)
        elif kind == "patch":
            fig.add_artist(Rectangle((lx, y - 0.008), 0.025, 0.016, fc=c, ec="#777777", lw=0.5 * S, transform=fig.transFigure))
        else:
            fig.add_artist(Line2D([lx + 0.0125], [y], marker="x" if kind == "x" else "s", color=c, ms=6 * S, mew=1.0 * S,
                                  transform=fig.transFigure))
        fig.text(lx + 0.032, y, label, fontsize=8 * S, va="center")
    note = "Trail is a\ndrawn route for\nthis exercise." if d.get("trail") else "Marked points\nare placed for\nthis exercise."
    fig.text(0.865, 0.30, "Terrain: real elevation\n(USGS 3DEP, public\ndomain), lightly\nsmoothed. " + note,
             fontsize=8 * S, va="top", linespacing=1.35, color="#333333")
    texts = text_boxes(fig)
    probes = [{"xy": [round(v, 1) for v in to_pixels(ax, q[0], q[1])], "expect": MAGENTA, "tol": 40, "r": 1,
               "what": f"marker {name}"} for name, q in marks]
    probes.append({"xy": [round(v, 1) for v in to_pixels(ax, bx + BOX_W - 30, by + 30)], "expect": PAPER, "tol": 40,
                   "what": "incident box"})
    if p is not None:                                  # the trail itself, at its middle vertex
        mid = p[len(p) // 2]
        probes.append({"xy": [round(v, 1) for v in to_pixels(ax, mid[0], mid[1])], "expect": RED, "tol": 90, "r": 3,
                       "what": "trail line"})
    save_png(fig, path)
    return {"texts": texts, "probes": probes}


def label_clash(layout, markers):
    """Why this drawing is not fair to read, or None. The same rule as validate's legibility check (no two labels
    overlap by more than 2 px), plus: no label covers a marker (the first `markers` probes)."""
    t = layout["texts"]
    for i in range(len(t)):
        for j in range(i + 1, len(t)):
            ow = min(t[i][2], t[j][2]) - max(t[i][0], t[j][0])
            oh = min(t[i][3], t[j][3]) - max(t[i][1], t[j][1])
            if ow > 2 and oh > 2:
                return "two labels overlap"
    for pr in layout["probes"][:markers]:
        x, y = pr["xy"]
        if any(b[0] - 5 <= x <= b[2] + 5 and b[1] - 5 <= y <= b[3] + 5 for b in t):
            return f"a label covers {pr['what']}"
    return None
