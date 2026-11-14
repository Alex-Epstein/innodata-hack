"""Independent second solver for the v2 subway tasks. Rebuilds the network from each line's grid path and the
station coordinates (not the station lists the generator solved on), reads the notice records, and solves with
Bellman-Ford style relaxation. Must agree with every reference answer.

    uv run python check.py
"""
import json
import pathlib

TASKS = pathlib.Path(__file__).parent / "tasks"
INF = float("inf")


def network(data):
    at = {tuple(s["xy"]): n for n, s in data["stations"].items()}
    lines = {}
    for ln in data["lines"]:
        lines[ln["route"]] = [at[tuple(c)] for c in ln["path"] if tuple(c) in at]
    links = {}
    for u, v in data["complexes"]:
        links.setdefault(u, set()).add(v)
        links.setdefault(v, set()).add(u)
    return lines, links


def best(data, a, b, ride, change, skip=None, closed=(), no_x=(), x_ok=None):
    """State (station, route, dir) = on board. Relax until stable."""
    lines, links = network(data)
    skip = skip or {}
    st = data["stations"]

    def stops(r, d, s):
        return s not in closed and s not in skip.get((r, d), set())

    def can_change(s):
        return st[s]["transfer_station"] and s not in closed and s not in no_x and (x_ok is None or s in x_ok)

    states = [(s, r, d) for r, sts in lines.items() for s in sts for d in (1, -1)]
    cost = {k: INF for k in states}
    for r, sts in lines.items():
        for d in (1, -1):
            if a in sts and stops(r, d, a):
                cost[(a, r, d)] = 0
    changed = True
    while changed:
        changed = False
        for (s, r, d), c in list(cost.items()):
            if c == INF:
                continue
            sts = lines[r]
            i = sts.index(s) + d
            nxt = []
            if 0 <= i < len(sts):
                nxt.append(((sts[i], r, d), c + ride))
            if stops(r, d, s) and can_change(s):
                for t in {s} | {t for t in links.get(s, ()) if can_change(t)}:
                    for r2, sts2 in lines.items():
                        for d2 in (1, -1):
                            if t in sts2 and stops(r2, d2, t) and (t, r2, d2) != (s, r, d):
                                nxt.append(((t, r2, d2), c + change))
            for k, v in nxt:
                if v < cost[k]:
                    cost[k] = v
                    changed = True
    ends = [c for (s, r, d), c in cost.items() if s == b and stops(r, d, s)]
    return min(ends) if ends else None


def answer(rec):
    data, q, notice = rec["data"], rec["question"], rec["notice"]
    a, b = q["from"], q["to"]
    qt = q["type"]
    skip, closed, no_x, outage = {}, set(), set(), set()
    for it in notice:
        if it["kind"] == "skip":
            skip[(it["route"], it["direction"])] = set(it["stations"])
        elif it["kind"] == "closed":
            closed.add(it["station"])
        elif it["kind"] == "no_transfer":
            no_x.add(it["station"])
        elif it["kind"] == "elevator_outage":
            outage.add(it["station"])
    if qt.endswith("service_change_time"):
        m = best(data, a, b, 2, 4, skip=skip, closed=closed, no_x=no_x)
        h, mi = map(int, q["departure"].split(":"))
        t = h * 60 + mi + m
        return f"{t // 60:02d}:{t % 60:02d}"
    if qt.endswith("accessible_transfers"):
        ok = {n for n, s in data["stations"].items() if s["accessible"]} - outage
        assert a in ok and b in ok
        return best(data, a, b, 0, 1, skip=skip, closed=closed, no_x=no_x, x_ok=ok)
    if qt.endswith("worst_closure"):
        base = best(data, a, b, 1, 0, skip=skip, closed=closed, no_x=no_x)
        inc = {c: best(data, a, b, 1, 0, skip=skip, closed=closed | {c}, no_x=no_x) - base
               for c in q["candidates"]}
        top = sorted(inc.values(), reverse=True)
        assert top[0] > top[1], f"tie {inc}"
        return max(inc, key=inc.get)
    raise ValueError(qt)


def main():
    ok = 0
    rows = [json.loads(l) for l in (TASKS / "tasks.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    for row in rows:
        rec = json.loads((TASKS / row["data"]).read_text(encoding="utf-8"))
        got = answer(rec)
        same = str(got) == str(row["answer"])
        ok += same
        print(f"{row['task_id']}: reference {row['answer']!r}, checker {got!r} {'OK' if same else 'MISMATCH'}")
    print(f"agree {ok}/{len(rows)}")


if __name__ == "__main__":
    main()
