"""Topographic map MISSIONS: chained multi-step questions on a USGS-style quadrangle with an incident briefing.

    cd /Users/alex/Desktop/innodata-hack && uv run python <work>/gen.py

Adapted from the teammate's topo spike (base_gen_copy.py: the elevation field, contour drawing, spot heights,
streams, scale bar). Data first: everything is sampled from the seed, saved to tasks/data/<task_id>.json, and
the PNG is drawn only from that file. Answers are computed from the analytic elevation field; the intermediate
facts go in `steps`, the true route / sight line / trail in `overlay`, and a second independent computation
(on the 10 m grid) goes in `checks`. A draw whose answer is fragile is thrown away and the next attempt is used.

Templates
  flood  The dam at D fails; water follows the steepest descent. Which campsite (C1..C4) does it reach first?
  los    Can the spotter at R (eyes 2 m up) see the hiker at H? yes / no, min clearance >= 10 m either way.
  fire   Which trail from S to Z stays at least 40 m below the fire's elevation? A / B / both / neither.
"""
import json
import math
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from contourpy import contour_generator
from collections import Counter
REJ = Counter()

HERE = Path(__file__).resolve().parent
OUT = HERE / "tasks"
DEMO = HERE / "demo"
VERSION = "topoM-0.1"
W, H, STEP = 4000.0, 3000.0, 10.0
CI, INDEX = 20, 100
BOX_W, BOX_H = 1560.0, 640.0                  # incident briefing box, map meters
REFERENCES = ["USGS 7.5-minute topographic quadrangle maps (1:24 000, brown 20 m contours, bold index contours, "
              "spot elevations, blue streams, dashed trails)",
              "NWCG Standards for Geospatial Operations (PMS 936) incident maps: title/briefing block with incident "
              "number, point symbols for fire origin, helispot, safety zone, drop points"]
QUADS = ["Hollister Ridge", "Coldwater Peak", "Juniper Flat", "Tamarack Butte", "Saddle Mountain", "Elk Hollow",
         "Granite Knob", "Marble Fork", "Antelope Spring"]
PEAKS = ["Hollister Ridge", "Coldwater Pk", "Bald Mtn", "Lookout Pt", "Eagle Rock", "Signal Hill", "Pine Butte",
         "Granite Knob", "Raven Crag"]
TRAILS = ["Ridge Trail", "Miners Trail", "Lookout Trail", "Aspen Trail", "Cedar Trail", "Hollister Cutoff"]
STREAMS = ["Mill Creek", "Cold Brook", "Wolf Creek", "Dry Fork", "Sawmill Creek", "Little Bear Creek"]
HUTS = ["Hollister Hut", "Miners Cabin", "Ranger Hut", "Aspen Hut"]
MAGENTA, BROWN, BROWN_INDEX, BLUE, GREEN = "#c2188f", "#b9793f", "#9a5a22", "#2b7bbb", "#e9f2dc"
RED, TRUTH = "#d7261e", "#0050ff"


# ---------------------------------------------------------------------------------------------- terrain (base)
def elev(d, x, y):
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


def grad(d, P, e=1.0):
    """Gradient at points P (n,2) -> (n,2)."""
    x, y = P[:, 0], P[:, 1]
    return np.stack([(elev(d, x + e, y) - elev(d, x - e, y)) / (2 * e),
                     (elev(d, x, y + e) - elev(d, x, y - e)) / (2 * e)], 1)


def dist_to_poly(p, pts):
    p, pts = np.asarray(p, float), np.asarray(pts, float)
    if len(pts) == 1:
        return float(np.linalg.norm(pts[0] - p))
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


def inside(p, m):
    return m <= p[0] <= W - m and m <= p[1] <= H - m


def contour_lines(Z):
    cg = contour_generator(x=np.arange(0, W + 1, STEP), y=np.arange(0, H + 1, STEP), z=Z)
    lo, hi = math.ceil(Z.min() / CI) * CI, math.floor(Z.max() / CI) * CI
    return {lv: [ln for ln in cg.lines(lv) if len(ln) > 1] for lv in range(int(lo), int(hi) + 1, CI)}


def rnd(p):
    return [round(float(p[0]), 1), round(float(p[1]), 1)]


def thin(pts, every=10.0):
    """Polyline thinned to about one vertex per `every` meters (for the overlay field)."""
    pts = np.asarray(pts, float)
    keep, acc = [pts[0]], 0.0
    for a, b in zip(pts[:-1], pts[1:]):
        acc += float(np.linalg.norm(b - a))
        if acc >= every:
            keep.append(b)
            acc = 0.0
    if not np.allclose(keep[-1], pts[-1]):
        keep.append(pts[-1])
    return [rnd(q) for q in keep]


def terrain(rng, nh=(5, 8), tilt=0.02, drain=False):
    """Base field: tilted plane + Gaussian hills. drain=True (flood maps): a steady regional slope along x so the
    fall lines run across the sheet through the valleys between hills instead of ending in pits."""
    d = {"extent_m": [W, H], "contour_interval_m": CI, "index_interval_m": INDEX,
         "base": {"z0": round(float(rng.uniform(240, 420)), 1), "gx": round(float(rng.uniform(-tilt, tilt)), 4),
                  "gy": round(float(rng.uniform(-tilt, tilt)), 4)},
         "hills": [{"x": round(float(rng.uniform(300, W - 300)), 1), "y": round(float(rng.uniform(300, H - 300)), 1),
                    "h": round(float(rng.uniform(120, 360)), 1), "sx": round(float(rng.uniform(380, 800)), 1),
                    "sy": round(float(rng.uniform(380, 800)), 1), "rot": round(float(rng.uniform(0, math.pi)), 3)}
                   for _ in range(int(rng.integers(*nh)))],
         "quad": str(rng.choice(QUADS))}
    if drain:
        sgn = 1 if rng.random() < 0.5 else -1
        d["base"]["gx"] = round(float(sgn * rng.uniform(0.035, 0.055)), 4)
        d["base"]["gy"] = round(float(rng.uniform(-0.012, 0.012)), 4)
        d["base"]["z0"] = round(float(d["base"]["z0"] + (200 if sgn < 0 else 0)), 1)
        d["base"]["gy"] = round(float(rng.uniform(-0.008, 0.008)), 4)
        troughs = [{"x": round(float(rng.uniform(0, W)), 1), "y": round(float(rng.uniform(300, H - 300)), 1),
                    "h": round(float(-rng.uniform(35, 80)), 1), "sx": round(float(rng.uniform(2800, 5000)), 1),
                    "sy": round(float(rng.uniform(140, 280)), 1), "rot": round(float(rng.uniform(-0.55, 0.55)), 3)}
                   for _ in range(int(rng.integers(3, 6)))]
        ridges = [{"x": round(float(rng.uniform(0, W)), 1), "y": round(float(rng.uniform(200, H - 200)), 1),
                   "h": round(float(rng.uniform(80, 220)), 1), "sx": round(float(rng.uniform(700, 1500)), 1),
                   "sy": round(float(rng.uniform(220, 420)), 1), "rot": round(float(rng.uniform(-0.45, 0.45)), 3)}
                  for _ in range(int(rng.integers(6, 11)))]
        d["hills"] = ridges              # troughs crossing each other made pits; ridges alone drain cleanly
    return d


# ---------------------------------------------------------------------------------------------- steepest descent
def descend(d, starts, step=2.0, max_len=7000.0, gmin=0.004):
    """Integrate the fall line (midpoint rule, `step` m) from each start. Returns (paths, why_stopped)."""
    P = np.array(starts, float).reshape(-1, 2)
    paths = [[p.copy()] for p in P]
    why = ["max_len"] * len(P)
    alive = np.ones(len(P), bool)
    for _ in range(int(max_len / step)):
        g = grad(d, P)
        n = np.linalg.norm(g, axis=1)
        for i in np.where(alive)[0]:
            if n[i] < gmin:
                alive[i], why[i] = False, "flat"
            elif not inside(P[i], 0):
                alive[i], why[i] = False, "edge"
        if not alive.any():
            break
        mid = P - 0.5 * step * g / np.maximum(n, 1e-12)[:, None]
        gm = grad(d, mid)
        nm = np.linalg.norm(gm, axis=1)
        newP = P - step * gm / np.maximum(nm, 1e-12)[:, None]
        P = np.where(alive[:, None], newP, P)
        for i in np.where(alive)[0]:
            paths[i].append(P[i].copy())
    return [np.array(p) for p in paths], why


def arclen(p):
    return np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(p, axis=0), axis=1))])


def first_hit(path, camps, r=50.0):
    """Index of the first path vertex inside any campsite circle, and which campsite; (None, None) if none."""
    C = np.array([[c["x"], c["y"]] for c in camps])
    dd = np.linalg.norm(path[:, None, :] - C[None, :, :], axis=2)
    inside_any = (dd <= r).any(1)
    if not inside_any.any():
        return None, None
    k = int(np.argmax(inside_any))
    return k, camps[int(np.argmin(dd[k]))]["name"]


def d8_hit(d, start, camps, Z, r=50.0):
    """Second, independent route: D8 steepest descent on the 10 m grid."""
    j, i = int(round(start[1] / STEP)), int(round(start[0] / STEP))
    C = np.array([[c["x"], c["y"]] for c in camps])
    for _ in range(4000):
        p = np.array([i * STEP, j * STEP])
        dd = np.linalg.norm(C - p, axis=1)
        if dd.min() <= r:
            return camps[int(np.argmin(dd))]["name"]
        best, bj, bi = 0.0, None, None
        for dj in (-1, 0, 1):
            for di in (-1, 0, 1):
                if dj == di == 0:
                    continue
                jj, ii = j + dj, i + di
                if not (0 <= jj < Z.shape[0] and 0 <= ii < Z.shape[1]):
                    return "edge"
                s = (Z[j, i] - Z[jj, ii]) / math.hypot(dj, di)
                if s > best:
                    best, bj, bi = s, jj, ii
        if bj is None:
            return "pit"
        j, i = bj, bi
    return "max_len"


# ---------------------------------------------------------------------------------------------- template: flood
def gen_flood(seed):
    rng = np.random.default_rng(seed)
    for attempt in range(int(__import__("os").environ.get("NATT", 600))):
        d = terrain(rng, drain=True)
        X, Y, Z = grid(d)
        # creeks: fall lines from the high side of the sheet; a dam sits on one once it has settled into a valley
        n0 = 48
        sx_ = rng.uniform(W - 900, W - 150, n0) if d["base"]["gx"] > 0 else rng.uniform(150, 900, n0)
        Us, whys = descend(d, np.stack([sx_, rng.uniform(300, H - 300, n0)], 1), step=3.0)
        good = [U for U, w in zip(Us, whys) if w == "edge" and arclen(U)[-1] >= 1800]
        if not good:
            REJ['flood_no_long_creek'] += 1
            continue
        for U in good[:8]:
            sU = arclen(U)
            okD = np.where((sU >= 450) & (sU <= 1300) & np.array([inside(q, 450) for q in U]))[0]
            if not len(okD):
                REJ['flood_L16'] += 1
                continue
            kD = int(rng.choice(okD))
            Dp = U[kD]
            if not inside(Dp, 450):
                REJ['flood_L16'] += 1
                continue
            flow = U[min(kD + 10, len(U) - 1)] - U[max(kD - 10, 0)]
            flow /= np.linalg.norm(flow)
            perp = np.array([-flow[1], flow[0]])
            zD = float(elev(d, *Dp))
            walls = [float(elev(d, *(Dp + s * 200 * perp))) for s in (-1, 1)]
            if min(walls) < zD + 8:                         # not a valley: no place for a dam
                REJ['flood_L23'] += 1
                continue
            start = Dp + 30 * flow
            (P,), (whyP,) = descend(d, [start])
            sP = arclen(P)
            if sP[-1] < 1500:
                REJ['flood_L28'] += 1
                continue
            vP = P - Dp
            angP = np.degrees(np.arccos(np.clip((vP @ flow) / np.maximum(np.linalg.norm(vP, axis=1), 1e-9), -1, 1)))
            okA = np.where((sP >= 1100) & (sP <= min(2600, sP[-1] - 200)) & (angP >= 32)
                           & np.array([inside(q, 150) for q in P]))[0]
            if not len(okA):
                REJ['flood_route_never_turns'] += 1
                continue
            kA = int(rng.choice(okA))
            L_ans = float(sP[kA])
            ans_c = P[kA] + rng.uniform(-12, 12, 2)
            if not inside(ans_c, 150):
                REJ['flood_L33'] += 1
                continue
            # candidate decoy spots: points on fall lines started on a ring around D that never come near P
            angs = np.linspace(0, 2 * math.pi, 36, endpoint=False)
            ring = np.array([Dp + r * np.array([math.cos(a), math.sin(a)]) for r in (250, 450, 650, 850) for a in angs])
            ring = np.array([q for q in ring if inside(q, 50) and elev(d, *q) < zD - 4])
            if len(ring) < 6:
                REJ['flood_ring'] += 1
                continue
            Qs, _ = descend(d, ring, step=4.0, max_len=4000)
            cand = np.vstack([Q[np.where(arclen(Q) >= 250)[0][::12]] for Q in Qs if arclen(Q)[-1] >= 250] or [np.zeros((0, 2))])
            cand = cand[[inside(c, 150) for c in cand]] if len(cand) else cand
            if len(cand) < 3:
                REJ['flood_few_cand'] += 1
                continue
            Pt = P[::4]
            dP = np.sqrt(((cand[:, None, :] - Pt[None]) ** 2).sum(2)).min(1)
            cand = cand[(dP >= 260) & (np.linalg.norm(cand - ans_c, axis=1) >= 450)]
            vA = ans_c - Dp
            angA = math.degrees(math.acos(np.clip(vA @ flow / np.linalg.norm(vA), -1, 1)))
            vC = cand - Dp
            distC = np.linalg.norm(vC, axis=1)
            angC = np.degrees(np.arccos(np.clip((vC @ flow) / np.maximum(distC, 1e-9), -1, 1)))
            ahead = np.where((angC <= 20) & (distC >= 0.5 * np.linalg.norm(vA)) & (distC <= 1.6 * np.linalg.norm(vA)))[0]
            if angA < 30 or len(ahead) == 0:
                REJ['flood_no_turn_trap'] += 1
                continue
            decoys = [cand[int(rng.choice(ahead))]]
            zA = float(elev(d, *ans_c))
            zC = elev(d, cand[:, 0], cand[:, 1])
            order = list(rng.permutation(len(cand)))
            order.sort(key=lambda i: zC[i] >= zA - 20)            # try lower-than-answer spots first
            for i in order:
                c = cand[i]
                if all(np.linalg.norm(c - o) >= 450 for o in decoys):
                    decoys.append(c)
                if len(decoys) == 3:
                    break
            # sometimes the third campsite sits further down the same valley (reached second)
            if rng.random() < 0.5 and sP[-1] > L_ans + 700:
                kB = int(np.searchsorted(sP, L_ans + rng.uniform(550, min(1300, sP[-1] - L_ans - 100))))
                dn = P[kB] + rng.uniform(-12, 12, 2)
                if inside(dn, 150) and all(np.linalg.norm(dn - o) >= 450 for o in decoys[:2]):
                    decoys = decoys[:2] + [dn]
            if len(decoys) < 3:
                REJ['flood_decoys'] += 1
                continue
            decoys = [c + rng.uniform(-10, 10, 2) for c in decoys]
            names = [f"C{k}" for k in rng.permutation(4) + 1]
            camps = [{"name": names[0], "x": round(float(ans_c[0]), 1), "y": round(float(ans_c[1]), 1)}] + \
                    [{"name": n, "x": round(float(c[0]), 1), "y": round(float(c[1]), 1)} for n, c in zip(names[1:], decoys)]
            answer = names[0]
            k_hit, hit = first_hit(P, camps)
            if hit != answer:
                REJ['flood_L76'] += 1
                continue
            Ph = P[:k_hit + 1]
            g_on_path = np.linalg.norm(grad(d, Ph), axis=1)
            others = {c["name"]: dist_to_poly([c["x"], c["y"]], Ph) for c in camps if c["name"] != answer}
            ans_miss = dist_to_poly([camps[0]["x"], camps[0]["y"]], P)
            # robustness: nudged starts and step sizes must reach the same campsite; the grid D8 route too
            nudges = [start + a * perp + b * flow for a in (-25, 0, 25) for b in (-10, 15)]
            NP, _ = descend(d, nudges, step=3.0)
            nudged = [first_hit(p, camps)[1] for p in NP]
            d8 = d8_hit(d, start, camps, Z)
            zc = {c["name"]: round(float(elev(d, c["x"], c["y"])), 1) for c in camps}
            straight = {c["name"]: round(float(np.linalg.norm(np.array([c["x"], c["y"]]) - Dp)), 1) for c in camps}
            nearest = min(straight, key=straight.get)
            other_drain_lower = [c["name"] for c in camps[1:] if zc[c["name"]] < zc[answer] - 20
                                 and dist_to_poly([c["x"], c["y"]], P) >= 250]
            ahead_name = camps[1]["name"]
            checks = {"min_slope_on_route_ge_0.02": bool(g_on_path.min() >= 0.02),
                      "route_misses_other_circles_by_120m": all(v >= 170 for v in others.values()),
                      "route_passes_within_20m_of_answer_center": ans_miss <= 20,
                      "nudged_starts_agree": all(n == answer for n in nudged),
                      "grid_d8_route_agrees": d8 == answer,
                      "trap_answer_not_nearest_to_dam": nearest != answer,
                      "trap_route_turns_30deg_from_dam_outflow": angA >= 30,
                      "trap_decoy_straight_down_the_outflow": True}
            if not all(checks.values()):
                REJ.update('flood_'+k for k,v in checks.items() if not v)
                REJ['flood_L98'] += 1
                continue
            reservoir_src = U[max(0, kD - 400):kD + 1]       # Bear Creek above the dam
            d.update({"template": "flood", "attempt": attempt,
                      "dam": {"name": "D", "x": round(float(Dp[0]), 1), "y": round(float(Dp[1]), 1),
                              "flow": [round(float(flow[0]), 4), round(float(flow[1]), 4)], "crest_elev": round(zD, 1)},
                      "campsites": camps, "creek_above_dam": {"name": "Bear Creek", "pts": thin(reservoir_src, 15)}})
            steps = {"dam_elev_m": round(zD, 1), "water_start": rnd(start), "rule": "fall line (steepest descent)",
                     "route_length_to_hit_m": round(float(sP[k_hit]), 1), "hit_campsite": answer,
                     "hit_point": rnd(P[k_hit]), "campsite_elev_m": zc, "straight_line_from_dam_m": straight,
                     "nearest_campsite_to_dam": nearest, "lowest_campsite": min(zc, key=zc.get),
                     "other_drainage_campsites_lower_than_answer": other_drain_lower,
                     "dam_outflow_bearing_deg": round((90 - math.degrees(math.atan2(flow[1], flow[0]))) % 360, 1),
                     "campsite_straight_down_the_outflow": ahead_name, "angle_outflow_to_answer_deg": round(angA, 1),
                     "route_min_dist_to_other_campsites_m": {k: round(v, 1) for k, v in others.items()},
                     "route_min_slope": round(float(g_on_path.min()), 4), "nudged_start_results": nudged, "grid_d8_result": d8,
                     "route_elev_profile_every_200m": [round(float(elev(d, *Ph[k]))) for k in
                                                        np.searchsorted(arclen(Ph), np.arange(0, sP[k_hit], 200))]}
            overlay = {"polylines": [{"role": "water_route", "pts": thin(Ph, 10)}],
                       "points": [{"role": "first_campsite_hit", "xy": rnd(P[k_hit])}]}
            keep = [Ph, *[np.array([[c["x"], c["y"]]]) for c in camps], np.array([Dp]), reservoir_src]
            if place_box(keep + [np.array(pl['pts']) for pl in overlay['polylines']]) is None:
                continue                                # no corner free for the briefing box
            return d, answer, steps, overlay, checks, keep
    print(REJ)
    raise SystemExit(f"flood seed {seed}: no fair task")


# ---------------------------------------------------------------------------------------------- template: line of sight
def profile(d, a, b, za_eye, zb_tgt, ds=2.0):
    n = max(2, int(np.linalg.norm(b - a) / ds) + 1)
    t = np.linspace(0, 1, n)
    pts = a + t[:, None] * (b - a)
    zt = elev(d, pts[:, 0], pts[:, 1])
    line = za_eye + t * (zb_tgt - za_eye)
    return t, pts, zt, line


def gen_los(seed, want):
    """R on a ridge, H lower down across a valley, clear line between them; then one cross-ridge is added on the
    line (a Gaussian hill, long axis across the line) whose crest is set 15-35 m below the sight line (yes) or
    15-35 m above it (no). Both answers therefore show the same picture: an intermediate ridge between a high
    spotter and a lower hiker, and only the arithmetic decides."""
    rng = np.random.default_rng(seed)
    for attempt in range(400000):
        if attempt % 1000 == 0:
            d0 = terrain(rng)
            X, Y, Z = grid(d0)
            hi = np.argwhere((Z > np.quantile(Z, 0.72)) & (X >= 300) & (X <= W - 300) & (Y >= 300) & (Y <= H - 300))
            hp = np.stack([X[hi[:, 0], hi[:, 1]], Y[hi[:, 0], hi[:, 1]]], 1)
            hp = hp[rng.permutation(len(hp))[:3000]]
            ring_max = np.max([elev(d0, hp[:, 0] + 220 * math.cos(a), hp[:, 1] + 220 * math.sin(a))
                               for a in np.linspace(0, 2 * math.pi, 24)], axis=0)
            ridge_pts = hp[ring_max <= elev(d0, hp[:, 0], hp[:, 1]) + 20]   # on a ridge or summit
        if len(ridge_pts) == 0:
            REJ['los_L17'] += 1
            continue
        R = ridge_pts[int(rng.integers(len(ridge_pts)))] + rng.uniform(-5, 5, 2)
        Hc = np.stack([rng.uniform(300, W - 300, 32), rng.uniform(300, H - 300, 32)], 1)
        Hc = Hc[(np.linalg.norm(Hc - R, axis=1) >= 1600) & (np.linalg.norm(Hc - R, axis=1) <= 2900)]
        if not len(Hc):
            continue
        Hk = Hc[0]
        L = float(np.linalg.norm(Hk - R))
        if not inside(Hk, 300):
            REJ['los_L22'] += 1
            continue
        zR, zH = float(elev(d0, *R)), float(elev(d0, *Hk))
        if zR - zH < 70 or np.linalg.norm(grad(d0, Hk[None])[0]) > 0.3:
            REJ['los_L25'] += 1
            continue
        t, pts, zt, line = profile(d0, R, Hk, zR + 2, zH + 2)
        sd = t * L
        mid = (sd >= 120) & (sd <= L - 120)
        if (line - zt)[mid].min() < 12:                     # the bare terrain must leave room for the cross-ridge
            REJ['los_L30'] += 1
            continue
        # the cross-ridge
        cb = np.where((t >= 0.33) & (t <= 0.67), line - zt, -np.inf)
        f = float(np.clip(t[int(np.argmax(cb))] + rng.uniform(-0.04, 0.04), 0.3, 0.7))   # over the deepest gap
        u = (Hk - R) / L
        rot = math.atan2(u[1], u[0])                        # hill's x axis along the line: sx = half-width along it
        c_target = rng.uniform(15, 35) * (1 if want == "yes" else -1)
        hill = {"x": round(float(R[0] + f * L * u[0]), 1), "y": round(float(R[1] + f * L * u[1]), 1), "h": 0.0,
                "sx": round(float(rng.uniform(200, 300)), 1), "sy": round(float(rng.uniform(450, 750)), 1),
                "rot": round(rot, 3)}
        d = {**d0, "hills": d0["hills"] + [hill]}
        for _ in range(6):                                  # set the crest height to hit the target clearance
            t, pts, zt, line = profile(d, R, Hk, zR + 2, float(elev(d, *Hk)) + 2)
            c = line - zt
            k = int(np.argmin(np.where(mid, c, np.inf)))
            hill["h"] = round(float(hill["h"] + (c[k] - c_target)), 1)
        if not 40 <= hill["h"] <= 260:
            REJ['los_L46'] += 1
            continue
        zR, zH = float(elev(d, *R)), float(elev(d, *Hk))
        t, pts, zt, line = profile(d, R, Hk, zR + 2, zH + 2)
        c = line - zt
        kmin = int(np.argmin(np.where(mid, c, np.inf)))
        cmin, frac = float(c[kmin]), float(t[kmin])
        ok_ends = bool((c[~mid] >= np.minimum(10, 2 + 0.06 * np.minimum(sd, L - sd))[~mid] - 1e-9).all())
        # any other place on the line within 10 m of grazing? (only the cross-ridge may come close)
        others = np.where(mid & (np.abs(sd - frac * L) > 400))[0]
        other_min = float(c[others].min()) if len(others) else 99.0
        if want == "yes":
            ok = cmin >= 10 and ok_ends and other_min >= 10
        else:
            ok = cmin <= -10 and other_min >= 10 and ok_ends
        if not ok or not 0.25 <= frac <= 0.75:
            REJ['los_L61'] += 1
            continue
        crest_elev = float(zt[kmin])
        # the cross-ridge must not be a summit with a printed spot height right on the line (that gives it away)
        fx, fy = pts[:, 0] / STEP, pts[:, 1] / STEP
        Z = elev(d, *np.meshgrid(np.arange(0, W + 1, STEP), np.arange(0, H + 1, STEP)))
        i0, j0 = np.clip(fx.astype(int), 0, Z.shape[1] - 2), np.clip(fy.astype(int), 0, Z.shape[0] - 2)
        ax_, ay_ = fx - i0, fy - j0
        zg = (Z[j0, i0] * (1 - ax_) * (1 - ay_) + Z[j0, i0 + 1] * ax_ * (1 - ay_) + Z[j0 + 1, i0] * (1 - ax_) * ay_
              + Z[j0 + 1, i0 + 1] * ax_ * ay_)
        grid_visible = bool((line - zg)[1:-1].min() > 0)
        checks = {"min_clearance_at_least_10m": abs(cmin) >= 10,
                  "no_other_point_within_10m_of_the_line": other_min >= 10,
                  "grid_profile_agrees": grid_visible == (want == "yes"),
                  "trap_spotter_at_least_70m_above_hiker": zR - zH >= 70,
                  "trap_cross_ridge_higher_than_hiker": crest_elev > zH + 20}
        if not all(checks.values()):
            REJ['los_L77'] += 1
            continue
        d.update({"template": "los", "attempt": attempt,
                  "spotter": {"name": "R", "x": round(float(R[0]), 1), "y": round(float(R[1]), 1), "eye_m": 2},
                  "hiker": {"name": "H", "x": round(float(Hk[0]), 1), "y": round(float(Hk[1]), 1), "target_m": 2}})
        steps = {"elev_R_m": round(zR, 1), "eye_R_m": round(zR + 2, 1), "elev_H_m": round(zH, 1),
                 "target_H_m": round(zH + 2, 1), "distance_m": round(L, 1),
                 "critical_point": rnd(pts[kmin]), "critical_fraction_from_R": round(frac, 3),
                 "critical_dist_from_R_m": round(frac * L, 1),
                 "terrain_at_critical_m": round(crest_elev, 1), "sightline_at_critical_m": round(float(line[kmin]), 1),
                 "min_clearance_m": round(cmin, 1), "min_clearance_elsewhere_m": round(other_min, 1),
                 "visible": want == "yes",
                 "profile_every_100m": [[round(float(s)), round(float(z)), round(float(l), 1)] for s, z, l in
                                        zip(sd[::50], zt[::50], line[::50])]}
        overlay = {"polylines": [{"role": "sight_line", "pts": [rnd(R), rnd(Hk)]}],
                   "points": [{"role": "blocking_point" if want == "no" else "closest_approach", "xy": rnd(pts[kmin])}]}
        keep = [np.array([R, Hk]), densify([R, Hk], 20)]
        if place_box(keep + [np.array(pl['pts']) for pl in overlay['polylines']]) is None:
            continue
        return d, want, steps, overlay, checks, keep
    print(REJ)
    raise SystemExit(f"los seed {seed}: no fair task")


# ---------------------------------------------------------------------------------------------- template: fire
def trail_between(rng, S, Zz, side):
    v = Zz - S
    L = np.linalg.norm(v)
    u, n = v / L, np.array([-v[1], v[0]]) / L
    pts = [S]
    for f in sorted(rng.uniform(0.15, 0.85, int(rng.integers(2, 4)))):
        pts.append(S + f * L * u + side * rng.uniform(150, 0.45 * L) * n)
    pts.append(Zz)
    return np.array(pts)


def gen_fire(seed, want):
    rng = np.random.default_rng(seed)
    for attempt in range(300000):
        if attempt % 400 == 0:
            d = terrain(rng)
            X, Y, Z = grid(d)
            lines = contour_lines(Z)
            zq = np.quantile(Z, [0.55, 0.92])
            cands = [lv for lv in lines if zq[0] <= lv <= zq[1] and lv % INDEX and any(len(l) > 60 for l in lines[lv])]
        if not cands:
            REJ['fire_L10'] += 1
            continue
        lv = int(rng.choice(cands))
        long_lines = [l for l in lines[lv] if len(l) > 60]
        ln = long_lines[int(rng.integers(len(long_lines)))]
        F = ln[int(rng.integers(5, len(ln) - 5))].astype(float)
        for _ in range(3):
            g = grad(d, F[None])[0]
            F = F - (float(elev(d, *F)) - lv) * g / max(float(g @ g), 1e-9)
        if not inside(F, 350) or abs(float(elev(d, *F)) - lv) > 0.5:
            REJ['fire_L19'] += 1
            continue
        if not 0.08 <= np.linalg.norm(grad(d, F[None])[0]) <= 0.4:
            REJ['fire_L21'] += 1
            continue
        T = lv - 40
        low = np.argwhere(Z < T - 30)
        if len(low) < 50:
            REJ['fire_L25'] += 1
            continue
        S = np.array([X[tuple(low[int(rng.integers(len(low)))])], Y[tuple(low[int(rng.integers(len(low)))])]])
        a, b = low[int(rng.integers(len(low)))], low[int(rng.integers(len(low)))]
        S, Zz = np.array([X[tuple(a)], Y[tuple(a)]]), np.array([X[tuple(b)], Y[tuple(b)]])
        if not (inside(S, 250) and inside(Zz, 250)) or not 1800 <= np.linalg.norm(Zz - S) <= 3400:
            REJ['fire_L30'] += 1
            continue
        if min(np.linalg.norm(S - F), np.linalg.norm(Zz - F)) < 500:
            REJ['fire_L32'] += 1
            continue
        tr = {"A": trail_between(rng, S, Zz, 1), "B": trail_between(rng, S, Zz, -1)}
        if rng.random() < 0.5:
            tr = {"A": tr["B"], "B": tr["A"]}
        if not all(inside(q, 120) for p in tr.values() for q in p):
            REJ['fire_L37'] += 1
            continue
        info, bad = {}, False
        for k, p in tr.items():
            q = densify(p, 2.0)
            z = elev(d, q[:, 0], q[:, 1])
            s = arclen(q)
            band = np.floor(z / CI)
            cross = np.where(np.diff(band) != 0)[0]
            if len(cross) and (s[cross[0]] < 60 or s[-1] - s[cross[-1]] < 60):
                bad = True                                  # a contour crossing hides under an end marker
            if min(dist_to_poly(F, p), 1e9) < 150:
                bad = True
            above = z > T
            info[k] = {"q": q, "z": z, "s": s, "max": float(z.max()), "kmax": int(np.argmax(z)),
                       "above_len": float((np.diff(s) * above[1:]).sum()), "mean": float(z.mean()), "len": float(s[-1])}
        if bad:
            REJ['fire_L53'] += 1
            continue
        status = {}
        for k, v in info.items():
            if v["max"] <= T - 10:
                status[k] = "safe"
            elif v["max"] >= T + 10 and v["above_len"] >= 100:
                status[k] = "unsafe"
            else:
                status[k] = "fragile"
        if "fragile" in status.values():
            REJ['fire_L63'] += 1
            continue
        safe = [k for k in "AB" if status[k] == "safe"]
        answer = safe[0] if len(safe) == 1 else ("neither" if not safe else "both")
        if want in ("A", "B") and answer in ("A", "B") and answer != want:     # which name the safe one gets is free
            tr, info, status = {"A": tr["B"], "B": tr["A"]}, {"A": info["B"], "B": info["A"]}, {"A": status["B"], "B": status["A"]}
            answer = want
        if answer != want:
            REJ['fire_L67'] += 1
            continue
        # traps: the unsafe trail looks lower (lower average) than the safe one; for neither, one barely exceeds
        if want in ("A", "B"):
            other = "B" if want == "A" else "A"
            trap = info[other]["mean"] < info[want]["mean"] - 5
        else:
            lo_k = min("AB", key=lambda k: info[k]["max"])
            trap = info[lo_k]["max"] <= T + 25 and info[lo_k]["mean"] < info["AB".replace(lo_k, "")]["mean"]
        if not trap:
            REJ['fire_L76'] += 1
            continue
        # second way: max of the 10 m grid sampled along each trail (nearest node)
        g_status = {}
        for k, v in info.items():
            q = v["q"]
            zg = Z[np.clip(np.round(q[:, 1] / STEP).astype(int), 0, Z.shape[0] - 1),
                   np.clip(np.round(q[:, 0] / STEP).astype(int), 0, Z.shape[1] - 1)]
            g_status[k] = "safe" if zg.max() <= T else "unsafe"
        checks = {"fire_on_contour_within_0.5m": True, "max_elev_at_least_10m_from_threshold_and_100m_above_it_if_unsafe": True,
                  "no_crossing_within_60m_of_trail_ends": True, "grid_profile_agrees": g_status == status,
                  "trap_unsafe_trail_looks_lower": bool(trap)}
        if not all(checks.values()):
            REJ['fire_L88'] += 1
            continue
        d.update({"template": "fire", "attempt": attempt,
                  "fire": {"name": "F", "x": round(float(F[0]), 1), "y": round(float(F[1]), 1)},
                  "crew": {"name": "S", "x": round(float(S[0]), 1), "y": round(float(S[1]), 1)},
                  "safety_zone": {"name": "Z", "x": round(float(Zz[0]), 1), "y": round(float(Zz[1]), 1)},
                  "mission_trails": [{"name": k, "pts": [rnd(q) for q in tr[k]]} for k in "AB"]})
        steps = {"fire_contour_m": lv, "threshold_m": T, "status": status,
                 **{f"trail_{k}": {"max_elev_m": round(v["max"], 1), "max_at": rnd(v["q"][v["kmax"]]),
                                   "max_at_dist_from_S_m": round(float(v["s"][v["kmax"]]), 1),
                                   "length_above_threshold_m": round(v["above_len"], 1),
                                   "mean_elev_m": round(v["mean"], 1), "length_m": round(v["len"], 1),
                                   "elev_S_m": round(float(v["z"][0]), 1), "elev_Z_m": round(float(v["z"][-1]), 1)}
                    for k, v in info.items()}}
        polys = []
        for k, v in info.items():
            if status[k] == "safe":
                polys.append({"role": f"safe_trail_{k}", "pts": thin(v["q"], 10)})
            else:
                above = v["z"] > T
                idx = np.where(above)[0]
                runs = np.split(idx, np.where(np.diff(idx) > 1)[0] + 1)
                for r_ in runs:
                    polys.append({"role": f"trail_{k}_above_threshold", "pts": thin(v["q"][r_[0]:r_[-1] + 1], 10)})
        overlay = {"polylines": polys, "threshold_contour_m": T,
                   "points": [{"role": f"trail_{k}_highest_point", "xy": rnd(v["q"][v["kmax"]])} for k, v in info.items()]}
        keep = [densify(tr["A"], 20), densify(tr["B"], 20), np.array([F, S, Zz])]
        if place_box(keep + [np.array(pl['pts']) for pl in overlay['polylines']]) is None:
            continue                                    # no corner free for the briefing box
        return d, answer, steps, overlay, checks, keep
    print(REJ)
    raise SystemExit(f"fire seed {seed}: no fair task")


# ---------------------------------------------------------------------------------------------- scenery
def place_box(keep):
    """Corner for the incident box whose rectangle (+120 m) is clear of every mission feature."""
    allp = np.vstack([np.asarray(k, float).reshape(-1, 2) for k in keep])
    for corner in ("tl", "tr", "bl", "br"):
        x0 = 0 if corner[1] == "l" else W - BOX_W
        y0 = H - BOX_H if corner[0] == "t" else 0
        m = 160
        hit = ((allp[:, 0] > x0 - m) & (allp[:, 0] < x0 + BOX_W + m) & (allp[:, 1] > y0 - m) & (allp[:, 1] < y0 + BOX_H + m))
        if not hit.any():
            return [x0, y0, BOX_W, BOX_H]
    return None


def in_box(q, box, m=60):
    return box is not None and box[0] - m <= q[0] <= box[0] + box[2] + m and box[1] - m <= q[1] <= box[1] + box[3] + m


def scenery(d, rng, keep, box, labels_marks):
    """Spot heights, a decor trail, streams, a hut, a helispot, index labels: as on a real map, kept clear of the
    mission features and the briefing box."""
    X, Y, Z = grid(d)
    lines = contour_lines(Z)
    K = np.vstack([np.asarray(k, float).reshape(-1, 2) for k in keep])

    def clear(q, r):
        return float(np.linalg.norm(K - np.asarray(q), axis=1).min()) >= r and not in_box(q, box)

    pk = (Z[1:-1, 1:-1] > Z[:-2, 1:-1]) & (Z[1:-1, 1:-1] > Z[2:, 1:-1]) & (Z[1:-1, 1:-1] > Z[1:-1, :-2]) & \
         (Z[1:-1, 1:-1] > Z[1:-1, 2:]) & (Z[1:-1, 1:-1] > Z[:-2, :-2]) & (Z[1:-1, 1:-1] > Z[2:, 2:]) & \
         (Z[1:-1, 1:-1] > Z[:-2, 2:]) & (Z[1:-1, 1:-1] > Z[2:, :-2])
    d["spot_heights"] = []
    for (j, i), name in zip(np.argwhere(pk), rng.permutation(PEAKS)):
        q = [float(X[j + 1, i + 1]), float(Y[j + 1, i + 1])]
        if inside(q, 200) and clear(q, 200):
            d["spot_heights"].append({"x": q[0], "y": q[1], "elev": int(round(float(Z[j + 1, i + 1]))), "name": str(name)})
    spots = [[s["x"], s["y"]] for s in d["spot_heights"]]
    # helispot on a high point that is not a named summit; hut somewhere on gentle ground
    d["helispot"], d["hut"] = None, None
    hi = np.argwhere(Z > np.quantile(Z, 0.8))
    for k in rng.permutation(len(hi))[:400] if d["template"] != "los" else []:   # LOS maps: no second "H"
        q = [float(X[tuple(hi[k])]), float(Y[tuple(hi[k])])]
        if inside(q, 250) and clear(q, 350) and all(math.dist(q, s) >= 300 for s in spots):
            d["helispot"] = {"x": q[0], "y": q[1], "name": "Helispot 2"}
            break
    for _ in range(400):
        q = [float(rng.uniform(300, W - 300)), float(rng.uniform(300, H - 300))]
        others = spots + ([[d["helispot"]["x"], d["helispot"]["y"]]] if d["helispot"] else [])
        if clear(q, 350) and all(math.dist(q, s) >= 350 for s in others) and np.linalg.norm(grad(d, np.array([q]))[0]) < 0.12:
            d["hut"] = {"x": q[0], "y": q[1], "name": str(rng.choice(HUTS))}
            break
    pois = spots + [[p["x"], p["y"]] for p in (d["helispot"], d["hut"]) if p]
    # one decor trail (no mission meaning), as on a real map
    d["trails"] = []
    for _ in range(60):
        p = np.array([rng.uniform(300, W - 300), rng.uniform(300, H - 300)])
        hd, pts = rng.uniform(0, 2 * math.pi), [p]
        for _ in range(2):
            hd += rng.uniform(-1.0, 1.0)
            p = p + rng.uniform(500, 1000) * np.array([math.cos(hd), math.sin(hd)])
            pts.append(p)
        if all(inside(q, 200) for q in pts) and all(clear(q, 280) and all(math.dist(q, o) >= 250 for o in pois)
                                                   for q in densify(pts, 40)):
            d["trails"].append({"name": str(rng.choice(TRAILS)), "pts": [rnd(q) for q in pts]})
            break
    # streams: fall lines started on hill flanks, drawn only away from the mission features
    d["streams"] = []
    names = list(rng.permutation(STREAMS))
    for h in rng.permutation(len(d["hills"])):
        hill, ang = d["hills"][int(h)], rng.uniform(0, 2 * math.pi)
        st = [hill["x"] + 2.0 * hill["sx"] * math.cos(ang), hill["y"] + 2.0 * hill["sy"] * math.sin(ang)]
        if not inside(st, 100):
            continue
        (s,), _ = descend(d, [st], step=15.0, max_len=4000)
        s = s[[clear(q, 300) and all(math.dist(q, o) >= 200 for o in pois) for q in s]]
        if len(s) > 1:
            gaps = np.where(np.linalg.norm(np.diff(s, axis=0), axis=1) > 20)[0]
            s = np.split(s, gaps + 1)
            s = max(s, key=len)
        if len(s) > 25 and any(np.mean([dist_to_poly(q, o["pts"]) < 120 for q in s]) > 0.15 for o in d["streams"]):
            continue                                        # merges into a stream already drawn
        if len(s) > 25:
            d["streams"].append({"name": str(names.pop()), "pts": [rnd(q) for q in s]})
        if len(d["streams"]) == 2:
            break
    drawn = [t["pts"] for t in d["trails"]] + [s["pts"] for s in d["streams"]]
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
                others = spots + [[l["x"], l["y"]] for l in d["index_labels"]] + labels_marks
                if inside(q, 160) and clear(q, 170) and all(math.dist(q, o) >= 240 for o in others) \
                        and all(dist_to_poly(q, l2) >= 140 for l2 in drawn):
                    d["index_labels"].append({"x": round(q[0], 1), "y": round(q[1], 1), "level": int(lv), "angle": round(ang, 1)})


def label_spot(p, avoid, r=95):
    """Offset for a point label: of 8 directions, the one farthest from the avoid points."""
    best, bd = None, -1
    A = np.asarray(avoid, float).reshape(-1, 2) if len(avoid) else np.zeros((0, 2))
    for a in np.linspace(0, 2 * math.pi, 8, endpoint=False):
        o = np.array([math.cos(a), math.sin(a)]) * r
        q = np.asarray(p) + o
        if not inside(q, 40):
            continue
        dd = float(np.linalg.norm(A - q, axis=1).min()) if len(A) else 1e9
        if dd > bd:
            best, bd = o, dd
    return [round(float(best[0]), 1), round(float(best[1]), 1)]


# ---------------------------------------------------------------------------------------------- briefing text
BRIEF = {
    "flood": ("INCIDENT 26-0412 · FLASH FLOOD WARNING",
              ["14:20  Bear Creek Dam (D) reported failing.",
               "Creek channel below the dam is dry and unmapped.",
               "Campsites C1-C4 occupied; circle = 50 m camp radius.",
               "Water flows the steepest way downhill (perpendicular",
               "to the contours) from just below the dam.",
               "TASK: which campsite does the water reach first?"]),
    "los": ("INCIDENT 26-0519 · SEARCH AND RESCUE",
            ["11:05  Overdue hiker located by phone ping at H.",
             "Spotter dropped on the ridge at R (eyes 2 m up).",
             "Hiker's head 2 m above the ground at H.",
             "Ignore trees and Earth curvature; terrain only.",
             "TASK: confirm direct line of sight R to H,",
             "yes or no, before the helicopter is sent."]),
    "fire": ("INCIDENT 26-0733 · WILDFIRE · CREW EGRESS",
             ["16:40  Fire front at F, spreading fastest uphill.",
              "Crew at S must walk to safety zone Z.",
              "Trail A and Trail B both run from S to Z.",
              "Rule: every point of the route must be at least",
              "40 m below F's elevation.",
              "TASK: which trail is safe: A, B, both or neither?"]),
}


# ---------------------------------------------------------------------------------------------- drawing
def mlabel(ax, x, y, off, text, color=MAGENTA, fs=11):
    ax.text(x + off[0], y + off[1], text, color=color, fontsize=fs, weight="bold", ha="center", va="center", zorder=9,
            bbox=dict(fc="white", ec=color, lw=0.6, pad=1.0, alpha=0.92))


def render(d, path, overlay=None):
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

    def along_text(p, name, color, off=65, style="italic", bbox=False):
        p = np.asarray(p, float)
        k = len(p) // 2
        t = p[min(k + 3, len(p) - 1)] - p[max(k - 3, 0)]
        nrm = np.array([-t[1], t[0]]) / max(np.linalg.norm(t), 1e-9)
        ang = math.degrees(math.atan2(t[1], t[0]))
        ang = ang - 180 if ang > 90 else ang + 180 if ang < -90 else ang
        kw = dict(bbox=dict(fc=GREEN, ec="none", pad=0.4, alpha=0.85)) if bbox else {}
        ax.text(*(p[k] + off * nrm), name, color=color, fontsize=6.5, style=style, rotation=ang, ha="center",
                va="center", zorder=6, **kw)

    for s in d["streams"]:
        p = np.array(s["pts"])
        ax.plot(p[:, 0], p[:, 1], color=BLUE, lw=1.1, zorder=3)
        along_text(p, s["name"], BLUE)
    for t in d["trails"]:
        p = np.array(t["pts"])
        ax.plot(p[:, 0], p[:, 1], color="black", lw=1.0, dashes=(5, 2.2), zorder=4)
        along_text(p[:2], t["name"], "black", off=70, style="normal", bbox=True)
    for lb in d["index_labels"]:
        ax.text(lb["x"], lb["y"], str(lb["level"]), color=BROWN_INDEX, fontsize=6.5, rotation=lb["angle"], ha="center",
                va="center", zorder=5, bbox=dict(fc=GREEN, ec="none", pad=0.5))
    for s in d["spot_heights"]:
        ax.plot(s["x"], s["y"], marker="x", color="black", ms=4, mew=0.9, zorder=6)
        ax.text(s["x"] + 45, s["y"] - 25, str(s["elev"]), fontsize=6.5, va="top", zorder=6)
        ax.text(s["x"] + 45, s["y"] + 30, s["name"], fontsize=7, style="italic", va="bottom", zorder=6)
    if d.get("helispot"):
        h = d["helispot"]
        ax.plot(h["x"], h["y"], marker="o", ms=11, mfc="white", mec="black", mew=1.1, zorder=7)
        ax.text(h["x"], h["y"], "H", fontsize=7, weight="bold", ha="center", va="center", zorder=8)
        ax.text(h["x"] + 55, h["y"] - 55, h["name"], fontsize=6.5, va="top", zorder=7)
    if d.get("hut"):
        h = d["hut"]
        ax.plot(h["x"], h["y"], marker="s", ms=5, color="black", zorder=7)
        ax.plot([h["x"] - 22, h["x"], h["x"] + 22], [h["y"] + 16, h["y"] + 40, h["y"] + 16], color="black", lw=1, zorder=7)
        ax.text(h["x"] + 50, h["y"], h["name"], fontsize=6.5, style="italic", va="center", zorder=7)

    tpl = d["template"]
    if tpl == "flood":
        D = d["dam"]
        c = np.array(d["creek_above_dam"]["pts"])
        ax.plot(c[:, 0], c[:, 1], color=BLUE, lw=1.1, zorder=3)
        along_text(c, d["creek_above_dam"]["name"], BLUE, off=70)
        fl = np.array(D["flow"])
        pp = np.array([-fl[1], fl[0]])
        # reservoir: upstream ground below crest + 8 m, closed off smoothly with distance from the dam
        dx, dy = X - D["x"], Y - D["y"]
        along = dx * fl[0] + dy * fl[1]
        lake = Z + 0.12 * np.maximum(0, np.hypot(dx, dy) - 120) + np.where(along > -6, 1e4, 0)
        lake = np.where(np.hypot(dx, dy) < 700, lake, np.nan)
        wet = np.nan_to_num(lake, nan=1e9) < D["crest_elev"] + 8      # keep only the water body touching the dam
        seed_ij = (int(round((D["y"] - 25 * fl[1]) / STEP)), int(round((D["x"] - 25 * fl[0]) / STEP)))
        keep_m = np.zeros_like(wet)
        stack = [seed_ij] if wet[seed_ij] else []
        while stack:
            j, i = stack.pop()
            if 0 <= j < wet.shape[0] and 0 <= i < wet.shape[1] and wet[j, i] and not keep_m[j, i]:
                keep_m[j, i] = True
                stack += [(j + 1, i), (j - 1, i), (j, i + 1), (j, i - 1)]
        lake = np.where(keep_m | ~wet, lake, 1e4)
        ax.contourf(X, Y, lake, levels=[-1e9, D["crest_elev"] + 8], colors=["#a9d3f0"], zorder=2.5)
        ax.contour(X, Y, lake, levels=[D["crest_elev"] + 8], colors=[BLUE], linewidths=0.8, zorder=2.6)
        half = []                                    # the dam spans the valley up to the reservoir level
        for sg in (-1, 1):
            r_ = np.arange(10, 300, 5)
            zz = elev(d, D["x"] + sg * r_ * pp[0], D["y"] + sg * r_ * pp[1])
            half.append(float(r_[np.argmax(zz >= D["crest_elev"] + 8)]) + 25 if (zz >= D["crest_elev"] + 8).any() else 200)
        a, b = np.array([D["x"], D["y"]]) - half[0] * pp, np.array([D["x"], D["y"]]) + half[1] * pp
        ax.plot([a[0], b[0]], [a[1], b[1]], color="black", lw=4.2, solid_capstyle="butt", zorder=8)
        mlabel(ax, D["x"], D["y"], D["label_off"], "D")
        for cs in d["campsites"]:
            ax.add_patch(plt.Circle((cs["x"], cs["y"]), 50, fc="none", ec=MAGENTA, lw=1.0, ls=(0, (2, 1.5)), zorder=7))
            ax.plot(cs["x"], cs["y"], marker="^", ms=6.5, color="#1d5c1d", mec="white", mew=0.6, zorder=8)
            mlabel(ax, cs["x"], cs["y"], cs["label_off"], cs["name"], fs=9.5)
    elif tpl == "los":
        R, Hk = d["spotter"], d["hiker"]
        ax.plot(R["x"], R["y"], marker="D", ms=6.5, color=MAGENTA, mec="white", mew=0.8, zorder=8)
        mlabel(ax, R["x"], R["y"], R["label_off"], "R")
        # hiker: small person glyph (head + body)
        ax.plot(Hk["x"], Hk["y"], marker="o", ms=6.5, color=MAGENTA, mec="white", mew=0.8, zorder=8)
        ax.plot(Hk["x"], Hk["y"] + 28, marker="o", ms=3.2, color=MAGENTA, zorder=8)
        mlabel(ax, Hk["x"], Hk["y"], Hk["label_off"], "H")
    elif tpl == "fire":
        for t in d["mission_trails"]:
            p = np.array(t["pts"])
            ax.plot(p[:, 0], p[:, 1], color="black", lw=1.35, dashes=(5, 2.2), zorder=4)
            k = len(p) // 2
            m = (p[k - 1] + p[k]) / 2 if len(p) % 2 == 0 else p[k]
            ax.text(*(m + np.array(t["label_off"])), f"Trail {t['name']}", fontsize=8.5, weight="bold", ha="center",
                    va="center", zorder=9, bbox=dict(fc="white", ec="black", lw=0.6, pad=1.0, alpha=0.92))
        F, S, Zz = d["fire"], d["crew"], d["safety_zone"]
        fx, fy = F["x"], F["y"]
        flame = np.array([[-4, 0], [-30, 22], [-24, 70], [-8, 52], [0, 110], [14, 58], [30, 34], [22, 0]]) * 1.25 + [fx, fy]
        ax.add_patch(plt.Polygon(flame, closed=True, fc=RED, ec="#7a0000", lw=0.8, zorder=8))
        inner = np.array([[-2, 2], [-12, 18], [-4, 40], [4, 26], [12, 14], [8, 2]]) * 1.25 + [fx, fy]
        ax.add_patch(plt.Polygon(inner, closed=True, fc="#ffb000", ec="none", zorder=8.5))
        ax.plot(fx, fy, marker="o", ms=3, color="black", zorder=9)
        mlabel(ax, fx, fy, F["label_off"], "F", color=RED)
        ax.plot(S["x"], S["y"], marker="s", ms=6.5, color=MAGENTA, mec="white", mew=0.8, zorder=8)
        mlabel(ax, S["x"], S["y"], S["label_off"], "S")
        ax.plot(Zz["x"], Zz["y"], marker="o", ms=12, mfc="#2e9e3e", mec="white", mew=0.8, zorder=8)
        ax.plot(Zz["x"], Zz["y"], marker="+", ms=8, color="white", mew=1.8, zorder=9)
        mlabel(ax, Zz["x"], Zz["y"], Zz["label_off"], "Z", color="#1d7a2c")

    if overlay is not None:                         # truth, in blue, drawn over everything else
        for pl in overlay["polylines"]:
            p = np.array(pl["pts"])
            ax.plot(p[:, 0], p[:, 1], color=TRUTH, lw=3.0, alpha=0.85, zorder=10, solid_capstyle="round")
        if tpl == "fire":
            ax.contour(X, Y, Z, levels=[overlay["threshold_contour_m"]], colors=[TRUTH], linewidths=1.2,
                       linestyles="dotted", zorder=10)
        for pt in overlay["points"]:
            ax.plot(*pt["xy"], marker="X" if "block" in pt["role"] or "highest" in pt["role"] else "o", ms=10,
                    mfc="none" if "closest" in pt["role"] else TRUTH, mec=TRUTH, mew=2, zorder=11)

    bx = d["brief_box"]
    head, body = BRIEF[tpl]
    ax.add_patch(plt.Rectangle((bx[0], bx[1]), bx[2], bx[3], fc="white", ec="black", lw=1.1, zorder=12))
    ax.add_patch(plt.Rectangle((bx[0], bx[1] + bx[3] - 115), bx[2], 115, fc=RED, ec="black", lw=1.1, zorder=12))
    ax.text(bx[0] + 45, bx[1] + bx[3] - 58, head, color="white", fontsize=7.6, weight="bold", va="center", zorder=13)
    for k, line in enumerate(body):
        ax.text(bx[0] + 45, bx[1] + bx[3] - 165 - k * 78, line, fontsize=6.9, va="center", zorder=13,
                weight="bold" if line.startswith("TASK") else "normal")

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
    sax = fig.add_axes([0.285, 0.062, 0.43, 0.012])
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
    legend = {"flood": "Dam: heavy black bar · Reservoir: light blue\nCampsite: green tent, dashed 50 m circle",
              "los": "Spotter: magenta diamond R\nHiker: magenta figure H",
              "fire": "Fire: red flame F · Crew: magenta square S\nSafety zone: green circle Z · Trail: dashed black"}[tpl]
    fig.text(0.93, 0.06, legend + ("\nHut: black square" if tpl == "los" else "\nHelispot: circled H · Hut: black square")
             + "\nStream: blue · Index contour: heavy brown",
             fontsize=6.3, ha="right", va="center")
    fig.savefig(path, metadata={"Software": None})
    plt.close(fig)


# ---------------------------------------------------------------------------------------------- questions
INTRO = ("This is a topographic map with an incident briefing box. North is up, the contour interval is 20 meters, "
         "index contours (heavy brown lines) are every 100 meters, and elevations are in meters. ")


def question(tpl):
    if tpl == "flood":
        return ("topoM.flood_first_campsite", INTRO +
                "INCIDENT 26-0412, flash flood warning: the dam at D (the heavy black bar across the valley, next to "
                "the magenta label D) fails. The released water starts just below the dam, on its downhill side, and "
                "always flows the steepest way downhill, that is, perpendicular to the contour lines; it does not "
                "spread sideways, pool, or climb. It reaches a campsite when it enters that campsite's 50 m circle "
                "(the dashed magenta circle around each green tent). The creek channel below the dam is not drawn. "
                "Which campsite does the water reach first? Answer with exactly one label: C1, C2, C3 or C4.")
    if tpl == "los":
        return ("topoM.los_spotter_hiker", INTRO +
                "INCIDENT 26-0519, search and rescue: a spotter stands at the magenta diamond R on the ridge, with eyes "
                "2 m above the ground. The hiker is at the magenta figure H; aim at the hiker's head, 2 m above the "
                "ground at H. The spotter can see the hiker only if the straight line from the spotter's eyes to the "
                "hiker's head passes above the ground at every point between them. Ignore trees, buildings and the "
                "curvature of the Earth. Can the spotter at R see the hiker at H? Answer yes or no.")
    return ("topoM.fire_safe_trail", INTRO +
            "INCIDENT 26-0733, wildfire: the fire is at the red flame F, and the point F lies exactly on a contour line. "
            "Fire spreads fastest uphill, so the crew must stay low. The crew at the magenta square S must walk to the "
            "safety zone Z (green circle). Two trails run from S to Z, labeled Trail A and Trail B (dashed black "
            "lines). Rule: a trail is safe only if every point on it, from S to Z, is at least 40 m below the elevation "
            "of F. Which trail is safe? Answer with exactly one of: A, B, both, neither.")


# ---------------------------------------------------------------------------------------------- main
PLAN = [("flood", 101, None), ("flood", 102, None), ("flood", 104, None),
        ("los", 201, "no"), ("los", 202, "yes"), ("los", 203, "no"),
        ("fire", 301, "B"), ("fire", 302, "A"), ("fire", 303, "neither")]


def build(tpl, seed, want):
    if tpl == "flood":
        d, answer, steps, overlay, checks, keep = gen_flood(seed)
    elif tpl == "los":
        d, answer, steps, overlay, checks, keep = gen_los(seed, want)
    else:
        d, answer, steps, overlay, checks, keep = gen_fire(seed, want)
    box = place_box(keep + [np.array(pl["pts"]) for pl in overlay["polylines"]])
    if box is None:
        return None
    d["brief_box"] = box
    rng = np.random.default_rng(seed + 7_000_000)
    # label offsets for the mission marks (away from the truth geometry and the other marks)
    avoid = np.vstack([np.asarray(k, float).reshape(-1, 2) for k in keep] +
                      [densify(pl["pts"], 15) for pl in overlay["polylines"]])
    marks = []
    if tpl == "flood":
        d["dam"]["label_off"] = label_spot([d["dam"]["x"], d["dam"]["y"]], avoid, 130)
        for c in d["campsites"]:
            c["label_off"] = label_spot([c["x"], c["y"]], avoid, 105)
            marks.append([c["x"] + c["label_off"][0], c["y"] + c["label_off"][1]])
    elif tpl == "los":
        for k in ("spotter", "hiker"):
            p = d[k]
            p["label_off"] = label_spot([p["x"], p["y"]], avoid, 95)
    else:
        for k in ("fire", "crew", "safety_zone"):
            p = d[k]
            p["label_off"] = label_spot([p["x"], p["y"]], avoid, 100)
        for t in d["mission_trails"]:
            p = np.array(t["pts"])
            k = len(p) // 2
            m = (p[k - 1] + p[k]) / 2 if len(p) % 2 == 0 else p[k]
            t["label_off"] = label_spot(m, densify(p, 15), 120)
    for k in ("dam", "spotter", "hiker", "fire", "crew", "safety_zone"):
        if k in d:
            marks.append([d[k]["x"] + d[k]["label_off"][0], d[k]["y"] + d[k]["label_off"][1]])
    scenery(d, rng, keep + [avoid], box, marks)
    return d, answer, steps, overlay, checks


def task_row(rec):
    tpl, tid = rec["params"]["template"], rec["task_id"]
    qtype, q = question(tpl)
    return {"task_id": tid, "image": f"images/{tid}.png", "question": q, "answer": rec["answer"],
            "answer_type": "label", "seed": rec["seed"], "generator_version": VERSION, "question_type": qtype,
            "family": "topoM", "difficulty": {"level": "hard", "template": tpl,
                                              "chain_steps": {"flood": 4, "los": 5, "fire": 5}[tpl]},
            "data": f"data/{tid}.json", "checks": rec["checks"], "steps": rec["steps"], "overlay": rec["overlay"],
            "references": REFERENCES}


def main():
    """gen.py gen [flood|los|fire|flood:103 ...]   sample tasks -> data/*.json (slow; seeds are deterministic)
       gen.py render                              draw images/ and demo/ from data/, write tasks.jsonl"""
    args = sys.argv[1:] or ["gen"]
    for sub in ("images", "data"):
        (OUT / sub).mkdir(parents=True, exist_ok=True)
    DEMO.mkdir(exist_ok=True)
    if args[0] == "gen":
        only = args[1:]
        for tpl, seed, want in PLAN:
            if only and tpl not in only and f"{tpl}:{seed}" not in only:
                continue
            got = build(tpl, seed, want)
            if got is None:
                raise SystemExit(f"{tpl} {seed}: no clear corner for the briefing box")
            d, answer, steps, overlay, checks = got
            tid = f"topoM-{tpl}-{seed:06d}"
            (OUT / "data" / f"{tid}.json").write_text(json.dumps(
                {"task_id": tid, "family": "topoM", "seed": seed, "generator_version": VERSION,
                 "params": {"template": tpl, "target_answer": want}, "data": d, "answer": answer, "steps": steps,
                 "overlay": overlay, "checks": checks, "references": REFERENCES}, indent=1))
            print(tid, "answer", answer, "attempt", d["attempt"], json.dumps(checks), flush=True)
    if args[0] in ("gen", "render"):
        rows = []
        for tpl, seed, want in PLAN:
            f = OUT / "data" / f"topoM-{tpl}-{seed:06d}.json"
            if not f.exists():
                continue
            rec = json.loads(f.read_text())
            if "checks" not in rec:
                print("skip (stale, no checks):", f.name)
                continue
            render(rec["data"], OUT / "images" / f"{rec['task_id']}.png")
            render(rec["data"], DEMO / f"{rec['task_id']}_truth.png", rec["overlay"])
            rows.append(task_row(rec))
        (OUT / "tasks.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
        print(len(rows), "tasks written")


if __name__ == "__main__":
    main()
