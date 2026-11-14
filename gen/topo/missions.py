"""The four mission templates. For each: place(...) samples the marks on a terrain and applies the fairness
rules, answer(...) computes the answer and the reasoning chain from the data on the analytic field, and
independent(...) recomputes the answer a second way on the 10 m grid.

Difficulty 1 to 3 is the amount of clutter a solver must trace through: more contour lines along the path,
more legs, more candidates that look right at a glance.
"""
from __future__ import annotations

import math

import numpy as np

from . import terrain as T

INTRO = ("This is a topographic map. The contour interval is 20 meters, index contours (heavy lines) are every "
         "100 meters, and elevations are in meters. ")


def pt(name, p, shape="dot", **kw):
    return {"name": name, "x": round(float(p[0]), 1), "y": round(float(p[1]), 1), "shape": shape, **kw}


def away(a, b, r=95):
    """Label offset: r meters from point a, pointing away from b."""
    v = np.array(a, float) - np.array(b, float)
    v = r * v / np.linalg.norm(v)
    return {"label_dx": round(float(v[0]), 1), "label_dy": round(float(v[1]), 1)}


def point(d, name):
    p = next(p for p in d["points"] if p["name"] == name)
    return [p["x"], p["y"]]


def clock(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


# ============================================================================================ 1. crossings
CROSS_KNOB = {1: (1, 3, 6), 2: (2, 7, 12), 3: (3, 14, 24)}          # legs, fewest and most contour crossings


def _fair_trail(rng, d, Z, lines, legs, lo, hi, tries=150, want=None):
    for _ in range(tries):
        pts = T.random_trail(rng, legs)
        if pts is None or not T.trail_is_fair(d, pts):
            continue
        total, up, _ = T.crossings_sampled(d, pts)
        if not lo <= total <= hi or (total, up) != T.crossings_geometry(Z, lines, pts):
            continue
        if want is None or want(total, up):
            return pts
    return None


def place_crossings(rng, d, Z, lines, difficulty):
    legs, lo, hi = CROSS_KNOB[difficulty]
    pts = _fair_trail(rng, d, Z, lines, legs, lo, hi)
    if pts is None:
        return None
    name = str(rng.choice(T.TRAILS))
    d["trails"] = [{"name": name, "pts": pts, "asked": True}]
    d["points"] = [pt("S", pts[0], "square", **away(pts[0], pts[1])), pt("E", pts[-1], "square", **away(pts[-1], pts[-2]))]
    d["mission"] = {"template": "crossings", "trail": name, "from": "S", "to": "E"}
    d["box"] = {"title": "RESCUE CARRY  ·  STRETCHER TEAM S TO E",
                "body": f"Team carries the casualty along the {name}.\nLog every contour line the trail crosses."}
    return {"keep_lines": [pts], "avoid": T.densify(pts, 40).tolist()}


def answer_crossings(d):
    pts = d["trails"][0]["pts"]
    total, up, where = T.crossings_sampled(d, pts)
    steps = {"contour_crossings": total, "uphill": up, "downhill": total - up, "legs": len(pts) - 1,
             "trail_length_m": round(T.length(pts), 1)}
    return total, steps, {"route": pts, "crossings": where}


def independent_crossings(d):
    _, _, Z = T.grid(d)
    return T.crossings_geometry(Z, T.contour_lines(Z), d["trails"][0]["pts"])[0]


def ask_crossings(d):
    name = d["mission"]["trail"]
    return {"answer_type": "integer", "question": INTRO + (
        f"Rescue carry: a stretcher team carries a casualty along the {name} (dashed black line) from the magenta "
        "square S to the magenta square E. To pace the carry, the team leader logs every contour line the trail "
        "crosses. How many contour lines does the trail cross between S and E? Count every crossing, index contours "
        "included; if the trail crosses the same contour line twice, count both. Answer with a whole number, for "
        "example 7.")}


# ============================================================================================ 2. sunset
def place_sunset(rng, d, Z, lines, difficulty):
    legs, lo, hi = CROSS_KNOB[difficulty]
    for _ in range(150):
        pts = T.random_trail(rng, legs)
        if pts is None:
            continue
        a, b = np.array(pts[-2]), np.array(pts[-1])                  # stretch the last leg: length = a multiple of 200 m
        total_len = T.length(pts)
        target = round(total_len / 200) * 200
        last = float(np.linalg.norm(b - a)) + target - total_len
        if last < 300:
            continue
        b = a + (b - a) / np.linalg.norm(b - a) * last
        pts = pts[:-1] + [[round(float(b[0]), 1), round(float(b[1]), 1)]]
        if not T.inside(pts[-1], 260) or abs(T.length(pts) - target) > 1.0 or not T.trail_is_fair(d, pts):
            continue
        total, up, _ = T.crossings_sampled(d, pts)
        if not lo <= total <= hi or (total, up) != T.crossings_geometry(Z, lines, pts):
            continue
        if up < 1 or (difficulty == 3 and (up < 4 or total - up < 3)):   # at the top level both directions matter
            continue
        km = target / 1000
        walk = int(round(15 * km)) + 4 * up
        now = int(rng.integers(14 * 12, 17 * 12)) * 5                    # 14:00 to 16:55 in 5-minute steps
        spare = int(rng.integers(-45, 76))
        name = str(rng.choice(T.TRAILS))
        d["trails"] = [{"name": name, "pts": pts, "asked": True}]
        d["points"] = [pt("S", pts[0], "square", **away(pts[0], pts[1])), pt("H", pts[-1], "square", **away(pts[-1], pts[-2]))]
        d["mission"] = {"template": "sunset", "trail": name, "from": "S", "to": "H", "trail_km": km, "now_min": now,
                        "sunset_min": now + walk + spare, "minutes_per_km": 15, "minutes_per_uphill_contour": 4}
        d["box"] = {"title": f"LOST HIKER  ·  NOW {clock(now)}  ·  SUNSET {clock(now + walk + spare)}",
                    "body": f"Hiker at S must reach the hut at H before dark.\n{name}, S to H: {km:.1f} km."}
        return {"keep_lines": [pts], "avoid": T.densify(pts, 40).tolist()}
    return None


def _sunset_answer(m, up):
    walk = int(round(m["minutes_per_km"] * m["trail_km"])) + m["minutes_per_uphill_contour"] * up
    return m["sunset_min"] - m["now_min"] - walk, walk


def answer_sunset(d):
    m, pts = d["mission"], d["trails"][0]["pts"]
    total, up, where = T.crossings_sampled(d, pts)
    spare, walk = _sunset_answer(m, up)
    steps = {"trail_km": m["trail_km"], "minutes_for_distance": int(round(15 * m["trail_km"])),
             "uphill_contour_crossings": up, "downhill_contour_crossings": total - up, "minutes_for_ascent": 4 * up,
             "walking_minutes": walk, "daylight_minutes": m["sunset_min"] - m["now_min"], "arrival": clock(m["now_min"] + walk),
             "wrong_if_every_crossing_counted": _sunset_answer(m, total)[0], "wrong_if_climb_ignored": _sunset_answer(m, 0)[0]}
    return spare, steps, {"route": pts, "crossings": where}


def independent_sunset(d):
    _, _, Z = T.grid(d)
    up = T.crossings_geometry(Z, T.contour_lines(Z), d["trails"][0]["pts"])[1]
    return _sunset_answer(d["mission"], up)[0]


def ask_sunset(d):
    m = d["mission"]
    return {"answer_type": "integer", "question": INTRO + (
        f"A lost hiker at the magenta square S must reach the hut at the magenta square H along the {m['trail']} "
        "(dashed black line) before dark. The incident box on the map gives the time now, the time of sunset and the "
        "length of the trail from S to H. Walking time follows Naismith's rule: 15 minutes for every kilometer of "
        "trail, plus 4 minutes for every contour line the trail crosses going uphill (each one is 20 m of climb, at "
        "300 m of climb per hour). Contour lines crossed going downhill add no time. How many minutes before sunset "
        "does the hiker reach the hut? Give a negative number if the hiker arrives after sunset. Answer with a whole "
        "number of minutes, for example 12 or -7.")}


# ============================================================================================ 3. flood
FLOOD_KNOB = {1: (3, 55, 500), 2: (4, 75, 400), 3: (6, 95, 300)}    # camps, route steps to the camp (x15 m), dry gap m
HIT_M = 45


def _routes(d, Z, dam):
    return [T.descend(d, dam), T.descend_grid(Z, dam)] + [T.descend(d, [dam[0] + dx, dam[1] + dy])
                                                           for dx, dy in ((25, 0), (-25, 0), (0, 25), (0, -25))]


def place_flood(rng, d, Z, lines, difficulty):
    n, min_k, gap_m = FLOOD_KNOB[difficulty]
    lo, hi = np.quantile(Z, 0.60), np.quantile(Z, 0.92)
    for _ in range(40):
        dam = [round(float(rng.uniform(450, T.W - 450)), 1), round(float(rng.uniform(450, T.H - 450)), 1)]
        z_dam = float(T.elev(d, *dam))
        if not lo <= z_dam <= hi:
            continue
        routes = _routes(d, Z, dam)
        route = routes[0]
        if len(route) < min_k + 25:
            continue
        k = int(rng.integers(min_k, len(route) - 12))
        a, b = np.array(route[k]), np.array(route[k + 1])
        side = np.array([-(b - a)[1], (b - a)[0]]) / max(np.linalg.norm(b - a), 1e-9)
        hit = [round(float(v), 1) for v in a + side * float(rng.uniform(-25, 25))]
        if not T.inside(hit, 300) or any(T.dist_to_poly(hit, r) > HIT_M for r in routes):
            continue
        first = np.array(route[20]) - np.array(dam)                    # where the water sets off (first 300 m)

        def off_line(q):                                               # angle between the first run and dam -> q
            v = np.array(q) - np.array(dam)
            c = float(first @ v / (np.linalg.norm(first) * np.linalg.norm(v)))
            return math.degrees(math.acos(max(-1.0, min(1.0, c))))

        cloud = np.vstack([np.asarray(r, float) for r in routes])      # every route, as points 5 to 15 m apart
        cand = np.column_stack([rng.uniform(300, T.W - 300, 1500), rng.uniform(300, T.H - 300, 1500)]).round(1)
        gap = np.sqrt(((cand[:, None, :] - cloud[None, ::2, :]) ** 2).sum(2)).min(1)
        from_dam = np.sqrt(((cand - np.array(dam)) ** 2).sum(1))
        ok = (T.elev(d, cand[:, 0], cand[:, 1]) <= z_dam - 40) & (from_dam >= 600) & (from_dam <= 3000) \
            & (gap >= gap_m + 10) & (gap <= 1000)                      # every camp is below the dam
        dry = []
        for q in cand[ok].tolist():
            if all(math.dist(q, o) >= 400 for o in dry + [hit, dam]) and \
                    min(T.dist_to_poly(q, r) for r in routes) >= gap_m:
                dry.append(q)
            if len(dry) == n - 1:
                break
        if len(dry) < n - 1:
            continue
        if difficulty == 3 and not (off_line(hit) >= 15 and any(off_line(q) < off_line(hit) for q in dry)):
            continue                              # the route must bend: a dry camp lies more "straight below" the dam
        camps = [hit] + dry
        camps = [camps[i] for i in rng.permutation(n)]
        d["points"] = [pt("D", dam, "square")] + [pt(f"C{i + 1}", q) for i, q in enumerate(camps)]
        d["mission"] = {"template": "flood", "dam": "D", "camps": [f"C{i + 1}" for i in range(n)], "hit_radius_m": HIT_M}
        d["box"] = {"title": "FLASH FLOOD  ·  DAM FAILED AT D",
                    "body": f"Water runs straight downhill from D.\nWhich camp, C1 to C{n}, is in its path?"}
        return {"keep_lines": [route], "avoid": route, "stream_gap_lines": [route]}
    return None


def _flood_pick(d, route):
    gaps = {c: T.dist_to_poly(point(d, c), route) for c in d["mission"]["camps"]}
    hit = [c for c, g in gaps.items() if g <= d["mission"]["hit_radius_m"]]
    return (hit[0] if len(hit) == 1 else None), gaps


def answer_flood(d):
    dam = point(d, "D")
    route = T.descend(d, dam)
    answer, gaps = _flood_pick(d, route)
    z_dam = float(T.elev(d, *dam))
    steps = {"dam_elev_m": round(z_dam, 1), "camps": [
        {"camp": c, "elev_m": round(float(T.elev(d, *point(d, c))), 1), "distance_to_water_route_m": round(g, 1),
         "flooded": c == answer} for c, g in gaps.items()]}
    return answer, steps, {"water_route": route, "flooded_camp": answer}


def independent_flood(d):
    _, _, Z = T.grid(d)
    return _flood_pick(d, T.descend_grid(Z, point(d, "D")))[0]


def ask_flood(d):
    camps = d["mission"]["camps"]
    return {"answer_type": "label", "question": INTRO + (
        "Flash flood: the dam at the magenta square D has failed. The water runs downhill from D, always in the "
        "direction of steepest descent, so its path crosses every contour line at a right angle. "
        f"{len(camps)} campsites are marked with magenta points, {camps[0]} to {camps[-1]}, all lower than the dam. "
        "Exactly one of them lies in the water's path. Which campsite does the water reach? Answer with the campsite "
        f"name, for example {camps[1]}.")}


# ============================================================================================ 4. wildfire
FIRE_TRAILS = ["Ridge Trail", "Aspen Trail", "Cedar Trail", "Basin Trail", "Birch Trail", "Maple Trail", "Alder Trail",
               "Eagle Trail", "Raven Trail", "Bluff Trail", "Flume Trail"]
FIRE_KNOB = {1: (2, 60, 0), 2: (3, 40, 0), 3: (4, 40, 40)}         # trails, margin m, least climb above the crew m


def _top(zfun, pts):
    p = T.densify(pts, 2.0)
    z = zfun(p[:, 0], p[:, 1])
    k = int(np.argmax(z))
    return float(z[k]), [round(float(p[k, 0]), 1), round(float(p[k, 1]), 1)], float(z[-1])


def place_wildfire(rng, d, Z, lines, difficulty):
    n, margin, climb = FIRE_KNOB[difficulty]
    field = lambda x, y: T.elev(d, x, y)
    gridded = lambda x, y: T.z_grid(Z, x, y)
    for _ in range(25):
        crew = [round(float(rng.uniform(900, T.W - 900)), 1), round(float(rng.uniform(800, T.H - 800)), 1)]
        ang = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(450, 800)
        fire = [round(crew[0] + r * math.cos(ang), 1), round(crew[1] + r * math.sin(ang), 1)]
        if not T.inside(fire, 300):
            continue
        z_fire, z_crew = float(T.elev(d, *fire)), float(T.elev(d, *crew))
        if not max(50, climb + margin + 20) <= z_fire - z_crew <= 220:
            continue
        safe, unsafe = [], []
        for _ in range(200):
            pts = T.random_trail(rng, int(rng.integers(2, 4)), start=crew, heading=rng.uniform(0, 2 * math.pi),
                                 leg_m=(450, 850), bend=0.7)
            if pts is None or T.dist_to_poly(fire, pts) < 260:
                continue
            first = math.atan2(pts[1][1] - crew[1], pts[1][0] - crew[0])
            if any(abs((first - o["first"] + math.pi) % (2 * math.pi) - math.pi) < 0.6 for o in safe + unsafe):
                continue                                               # trails leave S in clearly different directions
            if any(math.dist(pts[-1], o["pts"][-1]) < 500 or min(T.dist_to_poly(q, o["pts"]) for q in pts[1:]) < 280
                   or min(T.dist_to_poly(q, pts) for q in o["pts"][1:]) < 280 for o in safe + unsafe):
                continue
            top, _, end = _top(field, pts)
            top_g = _top(gridded, pts)[0]
            if top < z_crew + climb:
                continue                                               # at the top level every trail climbs first
            rec = {"pts": pts, "first": first}
            if top <= z_fire - margin and top_g <= z_fire - margin and not safe:
                safe.append(rec)
            elif top >= z_fire + margin and top_g >= z_fire + margin and len(unsafe) < n - 1:
                unsafe.append(rec)
            if safe and len(unsafe) == n - 1:
                break
        if not safe or len(unsafe) < n - 1:
            continue
        trails = safe + unsafe
        trails = [trails[i] for i in rng.permutation(n)]
        names = [str(x) for x in rng.choice(FIRE_TRAILS, n, replace=False)]
        # a trail's name is printed beside its first leg, so each trail is stored from its far end back to S
        d["trails"] = [{"name": nm, "pts": t["pts"][::-1], "asked": True} for nm, t in zip(names, trails)]
        d["points"] = [pt("S", crew, "square"), pt("F", fire, "square")]
        d["mission"] = {"template": "wildfire", "fire": "F", "crew": "S", "trails": names}
        d["box"] = {"title": "WILDFIRE  ·  FIRE AT F, CREW AT S",
                    "body": "Fire runs uphill. Which escape trail from S\nstays below the fire at F the whole way?"}
        return {"keep_lines": [t["pts"] for t in trails],
                "avoid": [m for t in trails for m in T.densify(t["pts"], 40).tolist()], "extra_trail": False}
    return None


def _fire_answer(d, zfun):
    z_fire = float(zfun(*point(d, "F")))
    rows = []
    for t in d["trails"]:
        if t.get("asked"):
            top, where, _ = _top(zfun, t["pts"])
            rows.append({"trail": t["name"], "highest_ground_m": round(top, 1), "highest_point": where,
                         "fire_elev_m": round(z_fire, 1), "stays_below_fire": top < z_fire})
    safe = [r["trail"] for r in rows if r["stays_below_fire"]]
    return (safe[0] if len(safe) == 1 else None), rows


def answer_wildfire(d):
    answer, rows = _fire_answer(d, lambda x, y: T.elev(d, x, y))
    overlay = {"fire_elev_m": rows[0]["fire_elev_m"], "trails": [
        {"trail": r["trail"], "highest_point": r["highest_point"], "safe": r["stays_below_fire"]} for r in rows]}
    return answer, rows, overlay


def independent_wildfire(d):
    _, _, Z = T.grid(d)
    return _fire_answer(d, lambda x, y: T.z_grid(Z, x, y))[0]


def ask_wildfire(d):
    names = d["mission"]["trails"]
    listed = ", ".join(names[:-1]) + " and " + names[-1]
    return {"answer_type": "label", "question": INTRO + (
        "Wildfire: a fire is burning at the magenta square F and a crew is at the magenta square S. Fire spreads "
        "fastest uphill, so the crew is safe only on a route that stays below the elevation of F the whole way. "
        f"{len(names)} escape trails (dashed black lines) leave S: {listed}. Exactly one of them never climbs to the "
        f"elevation of F. Which trail should the crew take? Answer with the trail name, for example {names[0]}.")}


# ============================================================================================ registry
PLACE = {"crossings": place_crossings, "sunset": place_sunset, "flood": place_flood, "wildfire": place_wildfire}
ANSWER = {"crossings": answer_crossings, "sunset": answer_sunset, "flood": answer_flood, "wildfire": answer_wildfire}
INDEPENDENT = {"crossings": independent_crossings, "sunset": independent_sunset, "flood": independent_flood,
               "wildfire": independent_wildfire}
ASK = {"crossings": ask_crossings, "sunset": ask_sunset, "flood": ask_flood, "wildfire": ask_wildfire}
