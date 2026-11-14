"""Subway v2 (#34): chained routing questions on the spike-F map (7 lines, ~90 stations).

T1 subway.fastest_trip   : per-line running times (table on the map) + 5 min per change + a closed station
                           -> shortest trip time in minutes. Chosen so the fewest-stops route is NOT the fastest.
T2 subway.worst_closure  : three weekend closures in a notice -> which weekend makes the fewest-stops trip longest,
                           and by how many stops. One closure is a decoy the route only rides through (adds 0).

Data first (tasks/data/<id>.json), PNG rendered from it, answers + intermediate `steps` computed from it.
    uv run python results/spikes/subway_chain/chain_gen.py
"""
import heapq
import importlib.util
import json
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("subway_base", os.path.join(HERE, "..", "subway", "gen.py"))
base = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(base)

VERSION = "subway-chain-0.1.0"
OUT = os.path.join(HERE, "tasks")
CHANGE_MIN = 5
TEMPLATES = {"subway.fastest_trip": [401, 402, 403], "subway.worst_closure": [501, 502, 503]}


def build_map(seed):
    rng = np.random.default_rng(seed)
    W, H, n = 16, 11, 7
    paths = base.make_map(rng, n, W, H)
    names = base.name_stations(rng, {c for p in paths for c in p})
    routes = [base.ROUTES[i] for i in sorted(rng.choice(len(base.ROUTES), n, replace=False))]
    data = {"city": base.CITY, "grid": [W, H], "closed": None,
            "lines": [{"name": r[0], "color": r[1], "bullet_text": r[2], "stations": [names[c] for c in p],
                       "coords": [list(c) for c in p]} for r, p in zip(routes, paths)]}
    return rng, data


def index(data):
    lines = {ln["name"]: ln["stations"] for ln in data["lines"]}
    at = {}
    for name, sts in lines.items():
        for s in sts:
            at.setdefault(s, []).append(name)
    return lines, at


def search(data, a, b, closed, ride, change):
    """Dijkstra over (station, line). ride(line) and change are cost tuples compared lexicographically.
    Returns (best cost, legs) where legs = [[line, board, alight, n_stops], ...]."""
    lines, at = index(data)
    zero = tuple(0 for _ in change)
    add = lambda x, y: tuple(p + q for p, q in zip(x, y))
    dist, parent, pq = {}, {}, []
    for ln in at[a]:
        dist[(a, ln)] = zero
        heapq.heappush(pq, (zero, a, ln))
    while pq:
        d, s, ln = heapq.heappop(pq)
        if d > dist[(s, ln)]:
            continue
        sts = lines[ln]
        i = sts.index(s)
        moves = [((sts[j], ln), ride(ln)) for j in (i - 1, i + 1) if 0 <= j < len(sts)]
        if s != closed:
            moves += [((s, o), change) for o in at[s] if o != ln]
        for st, w in moves:
            nd = add(d, w)
            if st not in dist or nd < dist[st]:
                dist[st], parent[st] = nd, (s, ln)
                heapq.heappush(pq, (nd, st[0], st[1]))
    ends = [(dist[(b, ln)], (b, ln)) for ln in at[b] if (b, ln) in dist]
    if not ends:
        return None, None
    cost, st = min(ends)
    chain = [st]
    while chain[-1] in parent:
        chain.append(parent[chain[-1]])
    chain.reverse()
    legs = []
    for s, ln in chain:
        if legs and legs[-1][0] == ln:
            legs[-1][2] = s
            legs[-1][3] += 1
        else:
            legs.append([ln, s, s, 0])
    return cost, [lg for lg in legs if lg[3] > 0]


def stations_on(data, legs):
    """Every station visited on a route (boarding, ridden through, alighting)."""
    lines, _ = index(data)
    out = []
    for ln, s0, s1, _ in legs:
        sts = lines[ln]
        i, j = sts.index(s0), sts.index(s1)
        out += sts[i:j + 1] if i <= j else sts[j:i + 1][::-1]
    return out


def fastest_trip(rng, data):
    _, at = index(data)
    mins = [2, 2, 3, 3, 4, 4, 3]
    rt = {ln["name"]: int(m) for ln, m in zip(data["lines"], rng.permutation(mins))}
    plain = sorted(s for s, ls in at.items() if len(ls) == 1)
    hubs = sorted(s for s, ls in at.items() if len(ls) > 1)
    T = lambda ln: (rt[ln],)
    cands, loose = [], []
    for i in rng.permutation(len(plain))[:40]:
        for j in rng.permutation(len(plain))[:40]:
            a, b = plain[i], plain[j]
            if a >= b or at[a] == at[b]:
                continue
            t_open, _ = search(data, a, b, None, T, (CHANGE_MIN,))
            for x in hubs:
                t, legs = search(data, a, b, x, T, (CHANGE_MIN,))
                if t is None or t[0] > 60 or t[0] - t_open[0] < 3 or len(legs) < 2:
                    continue
                # time of the fewest-stops route (ties broken by time)
                s_cost, _ = search(data, a, b, x, lambda ln: (1, rt[ln]), (0, CHANGE_MIN))
                item = (a, b, x, t[0], legs, t_open[0], s_cost)
                (cands if s_cost[1] - t[0] >= 3 else loose).append(item)
        if len(cands) >= 5:
            break
    pool = cands or loose
    a, b, x, ans, legs, t_open, s_cost = pool[int(rng.integers(len(pool)))]
    data["closed"] = x
    q = (f"This is the {base.CITY} subway map. Running times between adjacent stations differ by line (see the "
         f"table on the map), and every change of trains takes {CHANGE_MIN} minutes. Read the service notice and "
         f"take it into account. What is the shortest possible travel time, in minutes, from {a} to {b}? Count "
         f"riding time and change time only (no waiting at {a}). Answer with a single integer.")
    steps = {"closed": x, "run_times": rt, "route": [{"line": l, "from": s0, "to": s1, "stops": n,
                                                       "minutes": n * rt[l]} for l, s0, s1, n in legs],
             "changes": len(legs) - 1, "minutes": ans, "minutes_without_closure": t_open,
             "fewest_stops_route": {"stops": s_cost[0], "minutes": s_cost[1]}}
    notice = (f"SERVICE NOTICE\n{x} station is closed.\nTrains run through {x} without stopping.\n"
              f"No transfers between lines at {x}.")
    run_times = [(ln["name"], ln["color"], ln["bullet_text"], rt[ln["name"]]) for ln in data["lines"]]
    return a, b, q, ans, "integer", steps, notice, run_times


def worst_closure(rng, data):
    _, at = index(data)
    plain = sorted(s for s, ls in at.items() if len(ls) == 1)
    hubs = sorted(s for s, ls in at.items() if len(ls) > 1)
    S = lambda ln: (1,)
    found = []
    for i in rng.permutation(len(plain)):
        for j in rng.permutation(len(plain))[:30]:
            a, b = plain[i], plain[j]
            if a >= b or at[a] == at[b]:
                continue
            b0, legs0 = search(data, a, b, None, S, (0,))
            ride_through = set(stations_on(data, legs0)[1:-1]) - {lg[1] for lg in legs0[1:]}
            extra = {}
            for x in hubs:
                c, _ = search(data, a, b, x, S, (0,))
                if c is not None:
                    extra[x] = c[0] - b0[0]
            big = [x for x, e in extra.items() if e >= 3]
            decoys = [x for x in hubs if x in ride_through and extra.get(x) == 0]
            if not big or not decoys:
                continue
            x1 = big[int(rng.integers(len(big)))]
            mids = [x for x, e in extra.items() if 1 <= e <= extra[x1] - 2]
            if not mids or any(e > extra[x1] for e in extra.values() if False):
                continue
            x2 = mids[int(rng.integers(len(mids)))]
            x3 = decoys[int(rng.integers(len(decoys)))]
            found = (a, b, b0[0], legs0, [x1, x2, x3], extra)
            break
        if found:
            break
    a, b, s0, legs0, xs, extra = found
    order = [xs[k] for k in rng.permutation(3)]
    win = max(range(3), key=lambda k: extra[order[k]])
    assert sorted(extra[x] for x in order)[-1] - sorted(extra[x] for x in order)[-2] >= 2  # unique winner
    q = (f"This is the {base.CITY} subway map. The notice lists three weekends of station closures (one closure "
         f"per weekend). You always ride from {a} to {b} by the route with the fewest stops: count every station "
         f"after {a}, including {b} and any closed station the train runs through; changing trains adds no stop. "
         f"Which weekend makes your trip longest, and by how many stops compared with a weekend with no closures? "
         f"Answer as: Weekend N, K (for example: Weekend 1, 4).")
    ans = [f"Weekend {win + 1}", extra[order[win]]]
    steps = {"stops_normal": s0, "route_normal": legs0,
             "weekends": [{"weekend": k + 1, "closed": x, "stops": s0 + extra[x], "extra": extra[x]}
                          for k, x in enumerate(order)]}
    notice = ("PLANNED WEEKEND WORK\n" + "\n".join(f"Weekend {k + 1}: {x} closed" for k, x in enumerate(order))
              + "\nTrains run through a closed station without\nstopping. No transfers there.")
    return a, b, q, ans, "sequence", steps, notice, None


def main():
    os.makedirs(os.path.join(OUT, "images"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
    rows, rejected = [], []
    for qtype, seeds in TEMPLATES.items():
        for want in seeds:
          for seed in (want, want + 1000, want + 2000, want + 3000):
            rng, data = build_map(seed)
            make = fastest_trip if qtype == "subway.fastest_trip" else worst_closure
            a, b, q, ans, atype, steps, notice, run_times = make(rng, data)
            tid = f"subway-{seed:06d}"
            rec = {"task_id": tid, "family": "subway", "seed": seed, "generator_version": VERSION,
                   "params": {"template": qtype, "n_lines": 7, "grid": data["grid"], "change_min": CHANGE_MIN},
                   "data": data, "references": base.REFERENCES,
                   "question": {"type": qtype, "from": a, "to": b, "text": q, "answer": ans, "steps": steps},
                   "render": {"notice": notice, "run_times": run_times}}
            with open(os.path.join(OUT, "data", f"{tid}.json"), "w", encoding="utf-8") as f:
                json.dump(rec, f, indent=1)
            unclear = base.render(rec, os.path.join(OUT, "images", f"{tid}.png"), notice=notice,
                                  run_times=run_times)
            if unclear:  # legibility check failed: drop this seed, try the next one (counted in the funnel)
                print("  rejected", tid, "unclear labels:", unclear)
                rejected.append({"task_id": tid, "reason": "unclear labels", "labels": unclear})
                os.remove(os.path.join(OUT, "images", f"{tid}.png"))
                os.remove(os.path.join(OUT, "data", f"{tid}.json"))
                continue
            row = {"task_id": tid, "image": f"images/{tid}.png", "question": q, "answer": ans,
                   "answer_type": atype, "seed": seed, "generator_version": VERSION, "question_type": qtype,
                   "family": "subway", "difficulty": "chain", "data": f"data/{tid}.json",
                   "references": base.REFERENCES, "steps": steps}
            if atype == "sequence":
                row["ordered"] = True
            rows.append(row)
            print(tid, qtype, a, "->", b, "answer", ans)
            break
    with open(os.path.join(OUT, "tasks.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    with open(os.path.join(OUT, "funnel.json"), "w", encoding="utf-8") as f:
        json.dump({"generated": len(rows) + len(rejected), "kept": len(rows), "rejected": rejected}, f, indent=1)
    print(f"funnel: {len(rows) + len(rejected)} generated, {len(rows)} kept, {len(rejected)} rejected")


if __name__ == "__main__":
    main()
