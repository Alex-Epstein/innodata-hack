"""Subway map v2 spike: chained multi-step questions on an NYC/Vignelli-style diagram of an invented city.

Data first (tasks/data/<task_id>.json), PNG rendered only from that file, answer computed from that file with
Dijkstra over an expanded (station, line, direction) graph. Three templates x three seeds:

  svc   service change + clock time      (directional skips, no-transfer station, HH:MM arithmetic)
  acc   accessible route                  (wheelchair transfers only, a closure, an elevator outage)
  worst worst of three closures           (no-transfer station in force, 4 shortest-path searches)

    cd /Users/alex/Desktop/innodata-hack && uv run python <this file>
"""
import json
import heapq
import os
import textwrap
from collections import defaultdict

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe

VERSION = "sub2-0.1.0"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "tasks")
CITY = "Port Calder"
REFERENCES = ["Massimo Vignelli, New York City Subway Diagram (1972)",
              "MTA New York City Subway map and weekend service-change notices (route bullets, transfer "
              "connectors, accessibility symbol)"]
W, H = 14, 8

# MTA trunk colors; (route, line color, bullet text color)
ROUTES = [("A", "#0039A6", "white"), ("D", "#FF6319", "white"), ("G", "#6CBE45", "white"),
          ("J", "#996633", "white"), ("N", "#FCCC0A", "black"), ("2", "#EE352E", "white"),
          ("6", "#00933C", "white"), ("7", "#B933AD", "white"), ("L", "#7C858C", "white")]

PREFIXES = ["Linden", "Harbor", "Elm", "Bay", "Mercer", "Foundry", "Kestrel", "Bellamy", "Orchard", "Granary",
            "Quarry", "Beacon", "Garnet", "Hollis", "Sutter", "Clement", "Brightwater", "Saltmarsh", "Knox",
            "Arden", "Copper", "Lantern", "Marlow", "Pembrook", "Ashby", "Thornton", "Willet", "Hadley",
            "Ferris", "Corbin", "Easton", "Fairmount", "Greystone", "Juniper", "Larkin", "Norwood", "Oakmont",
            "Rowan", "Stanton", "Whitlock", "Alder", "Birch", "Crane", "Dunmore", "Elwood", "Fenwick", "Gilman",
            "Halstead", "Inwood", "Jessup", "Kimball", "Maddox", "Newbury", "Osgood", "Prescott", "Tremont",
            "Upton", "Warwick", "Bramble", "Colton", "Dorset", "Emery", "Wyckoff", "Cortland", "Ridgewood"]
SUFFIXES = ["St", "Av", "Sq", "Blvd", "Rd", "Park", "Pl", "Hts", "Pkwy"]
NUMBERED = ([f"{n} St" for n in (9, 14, 23, 31, 38, 47, 53, 61, 68, 74, 86, 95, 104, 125, 145, 168)]
            + [f"Av {c}" for c in "HJMPU"] + [f"{n} Av" for n in (2, 5, 7, 8, 11)])
SPECIAL = ["Civic Ctr", "Ferry Terminal", "Medical Ctr", "Courthouse", "Union Tpke", "College", "Stadium",
           "Botanic Garden", "Navy Yard", "City Hall"]
DIRS = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
RIDE_MIN, XFER_MIN = 2, 4


# ============================================================================== map data
def cheb(a, b):
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]))


def walk(rng, points, used_edges, ends):
    """Octilinear route through `points`, one grid step at a time, never reusing another line's edge."""
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
                if nxt in path or frozenset((cur, nxt)) in used_edges or nxt in ends:
                    continue
                if d is not None and mv[0] * d[0] + mv[1] * d[1] < 0:
                    continue
                if mv[0] and mv[1]:
                    a_, b_ = (cur[0], nxt[1]), (nxt[0], cur[1])
                    own = set(zip(path, path[1:]))
                    if (a_, b_) in own or (b_, a_) in own:
                        continue
                cands.append(mv)
            if not cands:
                return None
            mv = d if (d in cands and rng.random() < 0.7) else cands[int(rng.integers(len(cands)))]
            d = mv
            cur = (cur[0] + mv[0], cur[1] + mv[1])
            path.append(cur)
    return path


def border_point(rng, side):
    if side == 0:
        return (0, int(rng.integers(1, H - 1)))
    if side == 1:
        return (W - 1, int(rng.integers(1, H - 1)))
    if side == 2:
        return (int(rng.integers(1, W - 1)), 0)
    return (int(rng.integers(1, W - 1)), H - 1)


def make_paths(rng, n_lines=7):
    for _ in range(400):
        paths, used, ends, on_map = [], set(), set(), set()
        ok = True
        for k in range(n_lines):
            for _t in range(300):
                side = int(rng.integers(4))
                a, b = border_point(rng, side), border_point(rng, side ^ 1)
                if a in on_map or b in on_map or cheb(a, b) < 6:
                    continue
                if any(cheb(a, e) < 2 or cheb(b, e) < 2 for e in ends):
                    continue
                pts = [a]
                if paths:
                    pool = sorted(on_map - ends)
                    pts.append(pool[int(rng.integers(len(pool)))])
                pts.append(b)
                p = walk(rng, pts, used, ends)
                if p and 8 <= len(p) <= 14:
                    break
            else:
                ok = False
                break
            paths.append(p)
            used |= {frozenset(e) for e in zip(p, p[1:])}
            ends |= {p[0], p[-1]}
            on_map |= set(p)
        if ok:
            return paths
    raise RuntimeError("no map")


def build_map(rng):
    """Lines, stations, transfer stations, a transfer complex, accessibility flags. Retries until ~50 stations
    and the station graph is connected."""
    for _ in range(200):
        paths = make_paths(rng)
        through = defaultdict(list)                    # grid point -> [(line index, position in path)]
        for li, p in enumerate(paths):
            for i, c in enumerate(p):
                through[c].append((li, i))
        stop = {}
        ok = True
        for c, occ in through.items():
            if len(occ) == 1:
                li, i = occ[0]
                end = i in (0, len(paths[li]) - 1)
                stop[c] = end or rng.random() < 0.8
            else:
                straight = all(0 < i < len(paths[li]) - 1 and
                               (paths[li][i][0] - paths[li][i - 1][0], paths[li][i][1] - paths[li][i - 1][1]) ==
                               (paths[li][i + 1][0] - paths[li][i][0], paths[li][i + 1][1] - paths[li][i][1])
                               for li, i in occ)
                # a crossing with no station only where every line runs straight through (no visual merge)
                stop[c] = not (straight and len(occ) == 2 and rng.random() < 0.35)
        # no more than 2 grid steps between consecutive stations on a line
        for li, p in enumerate(paths):
            gap = 0
            for c in p:
                gap = 0 if stop[c] else gap + 1
                if gap >= 2:
                    stop[c] = True
                    gap = 0
        stations = [c for c in through if stop[c]]
        if not 44 <= len(stations) <= 56:
            continue
        crossings = [c for c, occ in through.items() if len(occ) > 1 and not stop[c]]
        # transfer complex: two stations of different lines on orthogonal neighbor points, not joined by a line
        edges = {frozenset(e) for p in paths for e in zip(p, p[1:])}
        lines_at = {c: {li for li, _ in through[c]} for c in stations}
        cand = []
        for u in stations:
            for dx, dy in ((1, 0), (0, 1)):
                v = (u[0] + dx, u[1] + dy)
                if v in lines_at and not (lines_at[u] & lines_at[v]) and frozenset((u, v)) not in edges:
                    cand.append((u, v))
        if not cand:
            continue
        complexes = [cand[int(rng.integers(len(cand)))]]
        rest = [c for c in cand if not (set(c) & set(complexes[0]))]
        if rest and rng.random() < 0.6:
            complexes.append(rest[int(rng.integers(len(rest)))])
        # connected?
        adj = defaultdict(set)
        for p in paths:
            sp = [c for c in p if stop[c]]
            for a, b in zip(sp, sp[1:]):
                adj[a].add(b)
                adj[b].add(a)
        for u, v in complexes:
            adj[u].add(v)
            adj[v].add(u)
        seen, todo = {stations[0]}, [stations[0]]
        while todo:
            x = todo.pop()
            for y in adj[x] - seen:
                seen.add(y)
                todo.append(y)
        if len(seen) != len(stations):
            ok = False
        if ok:
            return paths, stop, stations, lines_at, complexes, crossings
    raise RuntimeError("no map with ~50 stations")


def name_stations(rng, stations, lines_at, complexes):
    pool = [f"{p} {SUFFIXES[int(rng.integers(len(SUFFIXES)))]}" for p in PREFIXES] + NUMBERED + SPECIAL
    pool = [pool[i] for i in rng.permutation(len(pool))]
    names, k = {}, 0
    in_complex = {c for cx in complexes for c in cx}
    for c in sorted(stations):
        if len(lines_at[c]) > 1 and c not in in_complex and rng.random() < 0.2:
            names[c] = f"{pool[k]}–{pool[k + 1]}"     # dual name with an en dash, like "Harbor St–Civic Ctr"
            k += 2
        else:
            names[c] = pool[k]
            k += 1
    return names


def make_data(rng):
    paths, stop, stations, lines_at, complexes, crossings = build_map(rng)
    names = name_stations(rng, stations, lines_at, complexes)
    routes = [ROUTES[i] for i in sorted(rng.choice(len(ROUTES), len(paths), replace=False))]
    in_complex = {c for cx in complexes for c in cx}
    acc = {}
    for c in stations:
        is_x = len(lines_at[c]) > 1 or c in in_complex
        acc[names[c]] = bool(rng.random() < (0.5 if is_x else 0.3))
    lines = []
    for (r, col, tc), p in zip(routes, paths):
        lines.append({"route": r, "color": col, "bullet_text": tc, "path": [list(c) for c in p],
                      "stations": [names[c] for c in p if stop[c]]})
    st = {}
    for c in stations:
        st[names[c]] = {"xy": list(c), "routes": sorted(lines[li]["route"] for li in lines_at[c]),
                        "accessible": acc[names[c]], "transfer_station": False}
    for cx in complexes:
        for c in cx:
            st[names[c]]["transfer_station"] = True
    for n, s in st.items():
        if len(s["routes"]) > 1:
            s["transfer_station"] = True
    return {"city": CITY, "grid": [W, H], "lines": lines, "stations": st,
            "complexes": [[names[u], names[v]] for u, v in complexes],
            "crossings_without_station": [list(c) for c in crossings],
            "rules": {"ride_minutes_per_segment": RIDE_MIN, "transfer_minutes": XFER_MIN}}


# ============================================================================== solver
def build_graph(data, ride_w, xfer_w, skip=None, closed=(), no_xfer=(), xfer_ok=None, endpoints_ok=None):
    """Expanded graph. Nodes: ('T', station, route, dir) on a train, ('ARR', s) just got off, ('DEP', s) on the
    platform ready to board. dir +1 = toward the last station in the line's list.
    skip: {(route, dir): set(stations)} trains pass without stopping. closed: no train stops (both directions).
    no_xfer: no changes there. xfer_ok: if given, changes only at these stations (accessibility)."""
    skip = skip or {}
    adj = defaultdict(list)
    partner = defaultdict(set)
    for u, v in data["complexes"]:
        partner[u].add(v)
        partner[v].add(u)

    def stops(route, d, s):
        return s not in closed and s not in skip.get((route, d), ())

    for ln in data["lines"]:
        r, sts = ln["route"], ln["stations"]
        for d in (1, -1):
            idx = range(len(sts)) if d == 1 else range(len(sts) - 1, -1, -1)
            idx = list(idx)
            for a, b in zip(idx, idx[1:]):
                adj[("T", sts[a], r, d)].append((("T", sts[b], r, d), ride_w))
            for i in idx:
                s = sts[i]
                if stops(r, d, s):
                    adj[("T", s, r, d)].append((("ARR", s), 0))
                    adj[("DEP", s)].append((("T", s, r, d), 0))

    def can_x(s):
        st = data["stations"][s]
        return (st["transfer_station"] and s not in no_xfer and s not in closed
                and (xfer_ok is None or s in xfer_ok))
    for s in data["stations"]:
        if not can_x(s):
            continue
        adj[("ARR", s)].append((("DEP", s), xfer_w))     # same station: other line or reverse direction
        for t in partner[s]:
            if can_x(t):
                adj[("ARR", s)].append((("DEP", t), xfer_w))
    return adj


def dijkstra(adj, src, dst, count=False):
    """Plain Dijkstra; optimal-path count by DP over tight edges in (distance, node-kind) order, which is a
    topological order because every zero-weight edge goes DEP -> T -> ARR -> DST."""
    dist, par = {src: 0}, {}
    pq, k, done = [(0, 0, src)], 1, set()
    while pq:
        d, _, u = heapq.heappop(pq)
        if u in done:
            continue
        done.add(u)
        for v, w in adj.get(u, ()):
            if v not in dist or d + w < dist[v]:
                dist[v], par[v] = d + w, u
                heapq.heappush(pq, (d + w, k, v))
                k += 1
    if dst not in dist:
        return None, 0, None
    n_opt = None
    if count:
        rank = {"SRC": 0, "DEP": 1, "T": 2, "ARR": 3, "DST": 4}
        cnt = defaultdict(int)
        cnt[src] = 1
        for u in sorted(dist, key=lambda n: (dist[n], rank[n[0]])):
            if cnt[u]:
                for v, w in adj.get(u, ()):
                    if v in dist and dist[u] + w == dist[v]:
                        cnt[v] += cnt[u]
        n_opt = cnt[dst]
    path = [dst]
    while path[-1] != src:
        path.append(par[path[-1]])
    return dist[dst], n_opt, path[::-1]


def solve(data, a, b, **kw):
    count = kw.pop("count", False)
    adj = build_graph(data, **kw)
    adj[("SRC",)].append((("DEP", a), 0))
    adj[("ARR", b)].append((("DST",), 0))
    return dijkstra(adj, ("SRC",), ("DST",), count)


def legs(data, path):
    """Readable legs from an expanded-graph path."""
    out, cur = [], None
    for n in path:
        if n[0] == "T":
            _, s, r, d = n
            if cur is None or cur["route"] != r or cur["dir"] != d:
                ln = next(l for l in data["lines"] if l["route"] == r)
                cur = {"route": r, "dir": d, "toward": ln["stations"][-1] if d == 1 else ln["stations"][0],
                       "board": s, "segments": 0}
                out.append(cur)
            else:
                cur["segments"] += 1
                cur["alight"] = s
        elif n[0] == "ARR":
            if cur is not None:
                cur["alight"] = n[1]
            cur = None
    return [l for l in out if l.get("alight")]


def leg_text(lg):
    return f"({lg['route']}) toward {lg['toward']}: {lg['board']} -> {lg['alight']}, {lg['segments']} segments"


def compass(data, route, d):
    ln = next(l for l in data["lines"] if l["route"] == route)
    p0, p1 = ln["path"][0], ln["path"][-1]
    if d == -1:
        p0, p1 = p1, p0
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    if abs(dy) >= abs(dx) and abs(dy) >= 3:
        return "northbound" if dy < 0 else "southbound"
    if abs(dx) > abs(dy) and abs(dx) >= 3:
        return "eastbound" if dx > 0 else "westbound"
    return None


# ============================================================================== templates
def transfer_names(data, plain=True):
    return [n for n, s in data["stations"].items() if s["transfer_station"] and (not plain or "–" not in n)]


def t_service(rng, data):
    """Directional skips on one line + one station with no transfers; earliest arrival time."""
    lines = [l for l in data["lines"] if len(l["stations"]) >= 8]
    xfers = transfer_names(data, plain=False)
    best = None
    for _ in range(60):
        ln = lines[int(rng.integers(len(lines)))]
        d = int(rng.choice([1, -1]))
        inner = ln["stations"][1:-1]
        tx = [s for s in inner if data["stations"][s]["transfer_station"]]
        if not tx:
            continue
        k = int(rng.integers(2, 4))
        sk = {tx[int(rng.integers(len(tx)))]}
        while len(sk) < k:
            sk.add(inner[int(rng.integers(len(inner)))])
        hubs = [x for x in xfers if x not in sk and len(data["stations"][x]["routes"]) > 1]
        hub = hubs[int(rng.integers(len(hubs)))]
        skip = {(ln["route"], d): sk}
        skip_both = {(ln["route"], 1): sk, (ln["route"], -1): sk}
        names = [n for n in data["stations"] if n not in sk and n != hub]
        for _p in range(150):
            a, b = rng.choice(names, 2, replace=False)
            a, b = str(a), str(b)
            full, n_opt, path = solve(data, a, b, ride_w=RIDE_MIN, xfer_w=XFER_MIN, skip=skip, no_xfer={hub},
                                      count=True)
            if full is None or n_opt != 1:
                continue
            lg = legs(data, path)
            if not 2 <= len(lg) <= 4 or sum(l["segments"] for l in lg) > 16:
                continue
            none = solve(data, a, b, ride_w=RIDE_MIN, xfer_w=XFER_MIN)[0]
            noskip = solve(data, a, b, ride_w=RIDE_MIN, xfer_w=XFER_MIN, no_xfer={hub})[0]
            nohub = solve(data, a, b, ride_w=RIDE_MIN, xfer_w=XFER_MIN, skip=skip)[0]
            both = solve(data, a, b, ride_w=RIDE_MIN, xfer_w=XFER_MIN, skip=skip_both, no_xfer={hub})[0]
            if not (none < full and noskip < full and nohub < full):
                continue
            sc = (both != full) * 2 + (len(lg) >= 3) + (full >= 30)
            if best is None or sc > best[0]:
                best = (sc, ln["route"], d, sorted(sk, key=ln["stations"].index), hub, a, b, full, lg,
                        dict(ignore_notice=none, ignore_skips=noskip, ignore_no_transfer=nohub,
                             skips_both_directions=both))
        if best and best[0] >= 4:
            break
    if best is None:
        return None
    sc, route, d, sk, hub, a, b, full, lg, traps = best
    ln = next(l for l in data["lines"] if l["route"] == route)
    toward = ln["stations"][-1] if d == 1 else ln["stations"][0]
    cp = compass(data, route, d)
    dep_h = int(rng.integers(10, 21))
    m = full % 60
    dep_m = int(rng.integers(60 - m, 60)) if m > 0 else int(rng.integers(0, 60))   # arrival crosses the hour
    t_arr = dep_h * 60 + dep_m + full
    ans = f"{t_arr // 60:02d}:{t_arr % 60:02d}"
    dep = f"{dep_h:02d}:{dep_m:02d}"
    sk_txt = ", ".join(sk[:-1]) + f" and {sk[-1]}" if len(sk) > 1 else sk[0]
    notice = [{"route": route, "kind": "skip", "direction": d, "toward": toward, "stations": sk,
               "text": f"{(cp.capitalize() + ' trains') if cp else 'Trains'} toward {toward} skip {sk_txt}. "
                       f"Trains toward the other terminal stop as usual."},
              {"route": None, "kind": "no_transfer", "station": hub,
               "text": f"No transfers at {hub}. The station is open for entry and exit only."}]
    n_seg = sum(l["segments"] for l in lg)
    steps = [f"Notice: ({route}) {cp or ''} trains toward {toward} do not stop at {sk_txt}; no changes at {hub}.",
             *[f"Leg {i + 1}: {leg_text(l)}" for i, l in enumerate(lg)],
             f"{n_seg} segments x {RIDE_MIN} min + {len(lg) - 1} changes x {XFER_MIN} min = {full} min",
             f"{dep} + {full} min = {ans}",
             f"Trap answers (minutes): {traps}; route is the unique optimum"]
    q = (f"This is the {CITY} weekend subway map. Read the yellow SERVICE CHANGE notice and follow it. "
         f"Rules: a train takes {RIDE_MIN} minutes for each segment between two neighboring stations on its line "
         f"(passing a station without stopping still takes {RIDE_MIN} minutes per segment). Each change of trains "
         f"takes {XFER_MIN} minutes. You can change trains, including switching to the opposite direction of the "
         f"same line, only at a transfer station (white circle) or between two stations joined by a white "
         f"connector, and only where your trains stop. Ignore waiting time. You leave {a} at {dep}. What is the "
         f"earliest time you can arrive at {b}? Answer in 24-hour HH:MM format, for example 14:05.")
    return dict(question=q, answer=ans, answer_type="label", qtype="subway2.service_change_time",
                notice=notice, frm=a, to=b, steps=steps,
                extra={"total_minutes": full, "departure": dep, "trap_minutes": traps})


def t_access(rng, data):
    xfers = transfer_names(data, plain=False)
    acc = {n for n, s in data["stations"].items() if s["accessible"]}
    best = None
    for _ in range(80):
        x = xfers[int(rng.integers(len(xfers)))]
        accx = [s for s in xfers if s in acc and s != x]
        if not accx:
            continue
        y = accx[int(rng.integers(len(accx)))]
        ok_acc = acc - {y}
        ends = [n for n in ok_acc if n != x]
        for _p in range(120):
            a, b = (str(v) for v in rng.choice(ends, 2, replace=False))
            kw = dict(ride_w=0, xfer_w=1)
            full, _, path = solve(data, a, b, closed={x}, xfer_ok=ok_acc, **kw)
            if full is None or not 2 <= full <= 3:
                continue
            any_x = solve(data, a, b, closed={x}, **kw)[0]
            no_close = solve(data, a, b, xfer_ok=ok_acc, **kw)[0]
            no_outage = solve(data, a, b, closed={x}, xfer_ok=acc, **kw)[0]
            if not (any_x < full and no_close is not None and no_close < full
                    and no_outage is not None and no_outage < full):
                continue
            sc = (full - any_x) + (full >= 3)
            if best is None or sc > best[0]:
                best = (sc, x, y, a, b, full, legs(data, path),
                        dict(ignore_accessibility=any_x, ignore_closure=no_close, ignore_elevator_outage=no_outage))
        if best and best[0] >= 3:
            break
    if best is None:
        return None
    sc, x, y, a, b, full, lg, traps = best
    notice = [{"route": None, "kind": "closed", "station": x,
               "text": f"{x} is closed. Trains run through without stopping. No entry, exit or transfers."},
              {"route": None, "kind": "elevator_outage", "station": y,
               "text": f"Elevator out of service at {y}. The station is not accessible this weekend."}]
    steps = [f"Notice: {x} closed; {y} not accessible (elevator outage).",
             f"Accessible transfer stations usable: "
             f"{sorted(s for s in transfer_names(data, plain=False) if data['stations'][s]['accessible'] and s not in (x, y))}",
             *[f"Leg {i + 1}: {leg_text(l)}" for i, l in enumerate(lg)],
             f"Minimum changes = {full}", f"Trap answers: {traps}"]
    q = (f"This is the {CITY} weekend subway map. Read the yellow SERVICE CHANGE notice and follow it. A wheelchair "
         f"user travels from {a} to {b}. They can get on, get off and change trains only at accessible stations "
         f"(stations with the wheelchair symbol). Trains may pass through any station. Changes are possible only "
         f"at a transfer station (white circle) or between two stations joined by a white connector; a connector "
         f"change needs both stations to be accessible. What is the minimum number of changes of train for this "
         f"trip? Answer with a single integer.")
    return dict(question=q, answer=full, answer_type="integer", qtype="subway2.accessible_transfers",
                notice=notice, frm=a, to=b, steps=steps, extra={"trap_answers": traps})


def t_worst(rng, data):
    plain_x = [n for n in transfer_names(data, plain=True)]
    xfers_multi = [n for n in transfer_names(data, plain=False) if len(data["stations"][n]["routes"]) > 1]
    best = None
    names = list(data["stations"])
    for _ in range(60):
        hub = xfers_multi[int(rng.integers(len(xfers_multi)))]
        for _p in range(60):
            a, b = (str(v) for v in rng.choice([n for n in names if n != hub], 2, replace=False))
            kw = dict(ride_w=1, xfer_w=0, no_xfer={hub})
            base, _, path = solve(data, a, b, **kw)
            if base is None or not 5 <= base <= 11:
                continue
            base_nohub = solve(data, a, b, ride_w=1, xfer_w=0)[0]
            pool = [c for c in plain_x if c not in (a, b, hub)]
            inc = {}
            for c in pool:
                d1 = solve(data, a, b, closed={c}, **kw)[0]
                if d1 is not None:
                    inc[c] = d1 - base
            on_route = [c for c in inc if c in {n[1] for n in path if n[0] == "T"}]
            if len(on_route) < 2:
                continue
            for _t in range(30):
                trio = [str(c) for c in rng.choice(list(inc), 3, replace=False)]
                if sum(c in on_route for c in trio) < 2:
                    continue
                vals = sorted((inc[c] for c in trio), reverse=True)
                if vals[0] < 2 or vals[0] == vals[1] or base + vals[0] > 17:
                    continue
                worst = max(trio, key=lambda c: inc[c])
                inc_nohub = {c: solve(data, a, b, ride_w=1, xfer_w=0, closed={c})[0] - base_nohub for c in trio}
                vals_nh = sorted(inc_nohub.values(), reverse=True)
                trap = max(trio, key=lambda c: inc_nohub[c]) if vals_nh[0] != vals_nh[1] else "tie"
                sc = (trap != worst) * 3 + (vals[1] >= 1) + (len(set(vals)) == 3) + (base_nohub != base)
                if best is None or sc > best[0]:
                    best = (sc, hub, a, b, base, trio, {c: inc[c] for c in trio}, worst, trap, inc_nohub,
                            base_nohub, legs(data, path))
            if best and best[0] >= 6:
                break
        if best and best[0] >= 6:
            break
    if best is None:
        return None
    sc, hub, a, b, base, trio, inc, worst, trap, inc_nohub, base_nohub, lg = best
    trio = [trio[i] for i in rng.permutation(3)]
    notice = [{"route": None, "kind": "no_transfer", "station": hub,
               "text": f"No transfers at {hub}. The station is open for entry and exit only."}]
    steps = [f"Notice: no changes at {hub}.",
             f"Base fewest stops {a} -> {b} = {base}: " + "; ".join(leg_text(l) for l in lg),
             *[f"Close {c}: {base + inc[c]} stops (+{inc[c]})" for c in trio],
             f"Worst closure = {worst} (+{inc[worst]})",
             f"Ignoring the notice: base {base_nohub}, increments {inc_nohub}, worst = {trap}"]
    q = (f"This is the {CITY} weekend subway map. Read the yellow SERVICE CHANGE notice and follow it. Count a "
         f"trip's stops as the number of segments between neighboring stations that you ride (stations a train "
         f"passes without stopping also count). Changing trains adds no stops and is possible only at a transfer "
         f"station (white circle) or between two stations joined by a white connector. Consider the trip from "
         f"{a} to {b} with the fewest stops. Planners must close exactly one more station this weekend: "
         f"{trio[0]}, {trio[1]} or {trio[2]}. A closed station has no entry, exit or transfers, and trains run "
         f"through it without stopping. Which one of these three closures increases the fewest-stops trip from "
         f"{a} to {b} by the most stops? Answer with the station name exactly as written on the map.")
    return dict(question=q, answer=worst, answer_type="label", qtype="subway2.worst_closure", notice=notice,
                frm=a, to=b, steps=steps, extra={"candidates": trio, "increments": inc, "base_stops": base,
                                                   "trap_answer_ignoring_notice": trap})


TEMPLATES = {"svc": t_service, "acc": t_access, "worst": t_worst}
SEEDS = {"svc": [11, 12, 13], "acc": [21, 22, 23], "worst": [31, 32, 33]}


# ============================================================================== render
def render(rec, out_path):
    data = rec["data"]
    fig = plt.figure(figsize=(16, 12), dpi=100)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0.02, 0.2, 0.96, 0.725])
    ax.set_xlim(-0.9, W - 0.1)
    ax.set_ylim(H - 0.2, -0.8)
    ax.set_aspect("equal")
    ax.axis("off")

    fig.add_artist(plt.Rectangle((0, 0.935), 1, 0.065, transform=fig.transFigure, color="black"))
    fig.text(0.025, 0.967, f"{data['city']} Subway", color="white", fontsize=24, weight="bold", va="center")
    fig.text(0.975, 0.967, "Weekend Service Map", color="white", fontsize=15, va="center", ha="right")

    st = data["stations"]
    pos = {n: tuple(s["xy"]) for n, s in st.items()}
    for ln in data["lines"]:
        xs, ys = zip(*ln["path"])
        ax.plot(xs, ys, color=ln["color"], lw=7.5, solid_capstyle="butt", solid_joinstyle="round", zorder=2)
    # transfer complexes: white connector with a black outline
    for u, v in data["complexes"]:
        (x0, y0), (x1, y1) = pos[u], pos[v]
        ax.plot([x0, x1], [y0, y1], color="black", lw=17, solid_capstyle="round", zorder=4)
        ax.plot([x0, x1], [y0, y1], color="white", lw=12, solid_capstyle="round", zorder=4.5)
    for n, (x, y) in pos.items():
        if st[n]["transfer_station"]:
            ax.plot(x, y, "o", ms=15, mfc="white", mec="black", mew=2.6, zorder=5)
        else:
            ax.plot(x, y, "o", ms=6.5, color="black", zorder=5)
    bullets = []
    for ln in data["lines"]:
        c = ln["path"]
        for end, prev in ((c[0], c[1]), (c[-1], c[-2])):
            dx, dy = end[0] - prev[0], end[1] - prev[1]
            nrm = max(abs(dx), abs(dy))
            bx, by = end[0] + 0.5 * dx / nrm, end[1] + 0.5 * dy / nrm
            ax.add_patch(plt.Circle((bx, by), 0.24, color=ln["color"], zorder=6))
            ax.text(bx, by, ln["route"], color=ln["bullet_text"], fontsize=15, weight="bold", ha="center",
                    va="center", zorder=7)
            bullets.append((bx, by))

    # ---- labels (collision search in display space)
    fig.canvas.draw()
    rend = fig.canvas.get_renderer()
    T = ax.transData
    seg_pts = []
    for ln in data["lines"]:
        for p, q in zip(ln["path"], ln["path"][1:]):
            a, b = T.transform(p), T.transform(q)
            seg_pts.append(np.linspace(a, b, max(2, int(np.hypot(*(b - a)) / 3))))
    seg_pts = np.vstack(seg_pts)
    r = 10
    blocks = [(n, *T.transform(p)) for n, p in pos.items()]
    rb = (T.transform((0.28, 0)) - T.transform((0, 0)))[0]
    bblocks = [(px - rb, py - rb, px + rb, py + rb) for px, py in (T.transform(b) for b in bullets)]
    axbox = ax.get_window_extent(rend)
    O = 11
    cands = [(O, 0, "left", "center"), (-O, 0, "right", "center"), (0, O, "center", "bottom"),
             (0, -O, "center", "top"), (8, 8, "left", "bottom"), (-8, 8, "right", "bottom"),
             (8, -8, "left", "top"), (-8, -8, "right", "top")]
    halo = [pe.withStroke(linewidth=3.2, foreground="white")]
    placed = []
    quality = {"label_overlaps": 0, "ambiguous_labels": 0, "labels_off_map": 0}
    ICON = 17           # wheelchair icon, display px

    def inter(b1, b2):
        return b1[0] < b2[2] and b2[0] < b1[2] and b1[1] < b2[3] and b2[1] < b1[3]

    def shift(n, dx, ha):
        """Offset in points; an accessible station's name moves out to leave room for the icon by the dot."""
        if st[n]["accessible"] and ha in ("left", "right"):
            return dx + (1 if ha == "left" else -1) * (ICON + 4) * 72 / 100
        return dx

    def label_kw(n):
        return dict(fontsize=9.8, weight="bold" if st[n]["transfer_station"] else "normal", zorder=8)

    order = sorted(pos, key=lambda n: (-len(st[n]["routes"]), n))
    for n in order:
        best = None
        for i, (dx, dy, ha, va) in enumerate(cands):
            t = ax.annotate(n, pos[n], xytext=(shift(n, dx, ha), dy), textcoords="offset points", ha=ha, va=va,
                            **label_kw(n))
            bb = t.get_window_extent(rend)
            t.remove()
            box = [bb.x0 - 3, bb.y0 - 3, bb.x1 + 3, bb.y1 + 3]
            if st[n]["accessible"]:                 # icon sits between the dot and the name (or right of it)
                if ha == "left":
                    box[0] -= ICON + 4
                else:
                    box[2] += ICON + 4
                box[1] = min(box[1], (bb.y0 + bb.y1) / 2 - ICON / 2)
                box[3] = max(box[3], (bb.y0 + bb.y1) / 2 + ICON / 2)
            sc = i * 0.5 + 1000 * sum(inter(box, p) for p in placed)
            mine = T.transform(pos[n])
            sc += 400 * sum(inter(box, (px - r, py - r, px + r, py + r)) for m, px, py in blocks if m != n)
            sc += 1000 * sum(inter(box, bk) for bk in bblocks)
            inside = ((seg_pts[:, 0] > box[0]) & (seg_pts[:, 0] < box[2]) &
                      (seg_pts[:, 1] > box[1]) & (seg_pts[:, 1] < box[3])).sum()
            sc += 25 * inside
            # ambiguity: another station must not be as close to this label as its own station
            def bdist(px, py):
                return np.hypot(max(box[0] - px, 0, px - box[2]), max(box[1] - py, 0, py - box[3]))
            own = bdist(*mine)
            amb = sum(bdist(px, py) < own + 9 for m, px, py in blocks if m != n)
            hits = (sum(inter(box, p) for p in placed) + sum(inter(box, bk) for bk in bblocks)
                    + sum(inter(box, (px - r, py - r, px + r, py + r)) for m, px, py in blocks if m != n))
            sc += 600 * amb
            if box[0] < axbox.x0 or box[2] > axbox.x1 or box[1] < axbox.y0 or box[3] > axbox.y1:
                sc += 3000
            off = box[0] < axbox.x0 or box[2] > axbox.x1 or box[1] < axbox.y0 or box[3] > axbox.y1
            if best is None or sc < best[0]:
                best = (sc, i, box, bb, amb, hits, off)
        sc, i, box, bb, amb, hits, off = best
        quality["ambiguous_labels"] += int(amb > 0)
        quality["label_overlaps"] += int(hits > 0)
        quality["labels_off_map"] += int(off)
        dx, dy, ha, va = cands[i]
        ax.annotate(n, pos[n], xytext=(shift(n, dx, ha), dy), textcoords="offset points", ha=ha, va=va,
                    path_effects=halo, **label_kw(n))
        if st[n]["accessible"]:
            cx = (bb.x0 - 4 - ICON / 2) if ha == "left" else (bb.x1 + 4 + ICON / 2)
            cy = (bb.y0 + bb.y1) / 2
            ix, iy = ax.transData.inverted().transform((cx, cy))
            ax.text(ix, iy, "♿", fontsize=10.5, color="white", ha="center", va="center", zorder=9,
                    bbox=dict(boxstyle="square,pad=0.12", fc="#1A5DAD", ec="none"))
        placed.append(box)

    # ---- legend: routes in two columns, symbol key in a third
    fig.add_artist(plt.Rectangle((0.02, 0.012), 0.585, 0.18, transform=fig.transFigure, fc="#F4F4F4",
                                 ec="#999999", lw=1))
    fig.text(0.03, 0.176, "LEGEND", fontsize=12, weight="bold", va="center")
    for i, ln in enumerate(data["lines"]):
        col, row = divmod(i, 4)
        x, y = 0.04 + col * 0.18, 0.148 - row * 0.03
        fig.text(x, y, ln["route"], fontsize=11, weight="bold", color=ln["bullet_text"], ha="center",
                 va="center", bbox=dict(boxstyle="circle,pad=0.25", fc=ln["color"], ec="none"))
        fig.text(x + 0.014, y, f"{ln['stations'][0]} \u2013 {ln['stations'][-1]}", fontsize=9.3, va="center")
    key_x = 0.41
    syms = [("dot", "Station"), ("circle", "Transfer station"), ("link", "Linked stations: free transfer"),
            ("wc", "Accessible station")]
    for j, (kind, label) in enumerate(syms):
        y = 0.148 - j * 0.03
        if kind == "dot":
            fig.text(key_x, y, "\u25CF", fontsize=9, ha="center", va="center")
        elif kind == "circle":
            fig.text(key_x, y, " ", fontsize=6, ha="center", va="center",
                     bbox=dict(boxstyle="circle,pad=0.45", fc="white", ec="black", lw=2.2))
        elif kind == "link":
            fig.text(key_x, y, "      ", fontsize=6, ha="center", va="center",
                     bbox=dict(boxstyle="round,pad=0.3,rounding_size=0.6", fc="white", ec="black", lw=2.2))
        else:
            fig.text(key_x, y, "\u267F", fontsize=10.5, color="white", ha="center", va="center",
                     bbox=dict(boxstyle="square,pad=0.12", fc="#1A5DAD", ec="none"))
        fig.text(key_x + 0.02, y, label, fontsize=9.5, va="center")
    fig.text(0.03, 0.024, "Lines that cross with no dot or circle have no station there. All lines run in both "
             "directions; trains stop at every station unless a notice says otherwise.", fontsize=8.6,
             color="#333333", va="center")

    # ---- SERVICE CHANGE notice
    nx0, nx1, ny0, ny1 = 0.62, 0.98, 0.012, 0.192
    fig.add_artist(plt.Rectangle((nx0, ny0), nx1 - nx0, ny1 - ny0, transform=fig.transFigure, fc="#FFE14D",
                                 ec="black", lw=2))
    fig.add_artist(plt.Rectangle((nx0, ny1 - 0.04), nx1 - nx0, 0.04, transform=fig.transFigure, fc="black"))
    fig.text(nx0 + 0.012, ny1 - 0.02, "SERVICE CHANGE", color="#FFE14D", fontsize=15, weight="bold", va="center")
    fig.text(nx1 - 0.012, ny1 - 0.02, "This weekend, all day", color="white", fontsize=11, va="center",
             ha="right")
    y = ny1 - 0.062
    routes = {l["route"]: l for l in data["lines"]}
    for item in rec["notice"]:
        tx = nx0 + 0.048
        if item["route"]:
            ln = routes[item["route"]]
            fig.text(nx0 + 0.024, y, ln["route"], fontsize=12, weight="bold", color=ln["bullet_text"],
                     ha="center", va="center", bbox=dict(boxstyle="circle,pad=0.25", fc=ln["color"], ec="none"))
        else:
            fig.text(nx0 + 0.024, y, "!", fontsize=13, weight="bold", color="white", ha="center", va="center",
                     bbox=dict(boxstyle="square,pad=0.35", fc="black", ec="none"))
        wrapped = textwrap.fill(item["text"], 46)
        fig.text(tx, y + 0.012, wrapped, fontsize=11.5, va="top", linespacing=1.35)
        y -= 0.021 * (wrapped.count("\n") + 1) + 0.012
    fig.savefig(out_path, dpi=100, facecolor="white", metadata={"Software": None})
    plt.close(fig)
    return quality


# ============================================================================== main
def main():
    rows = []
    for tname, seeds in SEEDS.items():
        for seed in seeds:
            rng = np.random.default_rng(seed)
            tid = f"sub2-{tname}-{seed:06d}"
            for attempt in range(120):
                data = make_data(rng)
                q = TEMPLATES[tname](rng, data)
                if not q:
                    continue
                n_tx = sum(s["transfer_station"] for s in data["stations"].values())
                rec = {"task_id": tid, "family": "subway2", "seed": seed, "generator_version": VERSION,
                       "params": {"template": tname, "n_lines": len(data["lines"]),
                                  "n_stations": len(data["stations"]), "n_transfer_stations": n_tx,
                                  "map_attempts": attempt + 1},
                       "data": data, "notice": q["notice"], "references": REFERENCES,
                       "question": {"type": q["qtype"], "from": q["frm"], "to": q["to"], "text": q["question"],
                                    "answer": q["answer"], **q["extra"]},
                       "steps": q["steps"]}
                tmp = os.path.join(OUT, "images", f"{tid}.png")
                quality = render(rec, tmp)          # gate: every label unambiguous and collision-free
                if not any(quality.values()):
                    break
                print("   reject render", tid, quality)
            else:
                raise RuntimeError(f"{tname} {seed}: no clean map")
            rec["params"]["render_quality"] = quality
            with open(os.path.join(OUT, "data", f"{tid}.json"), "w", encoding="utf-8") as f:
                json.dump(rec, f, indent=1, ensure_ascii=False)
            render(rec, os.path.join(OUT, "images", f"{tid}.png"))     # re-render from the saved data file
            rows.append({"task_id": tid, "image": f"images/{tid}.png", "question": q["question"],
                         "answer": q["answer"], "answer_type": q["answer_type"], "seed": seed,
                         "generator_version": VERSION, "question_type": q["qtype"], "family": "subway2",
                         "difficulty": "hardest", "data": f"data/{tid}.json", "steps": q["steps"],
                         "references": REFERENCES})
            print(tid, rec["params"], "->", q["answer"])
            for s in q["steps"]:
                print("    ", s)
    with open(os.path.join(OUT, "tasks.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
