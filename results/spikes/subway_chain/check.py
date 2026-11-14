"""Independent second solver for subway v2: Bellman-Ford relaxation on a graph rebuilt from coordinates (no code
shared with chain_gen.py). Recomputes every answer and the per-weekend extras.

    uv run python results/spikes/subway_chain/check.py
"""
import json
import pathlib

TASKS = pathlib.Path(__file__).parent / "tasks"
INF = float("inf")


def shortest(data, a, b, closed, ride_minutes, change_minutes):
    name = {}
    edges = []
    for li, ln in enumerate(data["lines"]):
        cs = [tuple(c) for c in ln["coords"]]
        for c, s in zip(cs, ln["stations"]):
            name[c] = s
        for p, q in zip(cs, cs[1:]):
            w = ride_minutes(ln["name"])
            edges += [((p, li), (q, li), w), ((q, li), (p, li), w)]
    nodes = {e[0] for e in edges}
    for (c, li) in nodes:
        for (c2, lj) in nodes:
            if c == c2 and li != lj and name[c] != closed:
                edges.append(((c, li), (c2, lj), change_minutes))
    d = {n: (0 if name[n[0]] == a else INF) for n in nodes}
    for _ in range(len(nodes)):
        changed = False
        for u, v, w in edges:
            if d[u] + w < d[v]:
                d[v] = d[u] + w
                changed = True
        if not changed:
            break
    return min(d[n] for n in nodes if name[n[0]] == b)


def main():
    ok = True
    for line in (TASKS / "tasks.jsonl").read_text(encoding="utf-8").splitlines():
        t = json.loads(line)
        rec = json.loads((TASKS / t["data"]).read_text(encoding="utf-8"))
        data, q = rec["data"], rec["question"]
        if q["type"] == "subway.fastest_trip":
            rt = q["steps"]["run_times"]
            got = shortest(data, q["from"], q["to"], data["closed"], lambda ln: rt[ln], 5)
        else:
            base = shortest(data, q["from"], q["to"], None, lambda ln: 1, 0)
            extras = []
            for wk in q["steps"]["weekends"]:
                extras.append(shortest(data, q["from"], q["to"], wk["closed"], lambda ln: 1, 0) - base)
            k = max(range(3), key=lambda i: extras[i])
            top2 = sorted(extras)[-2:]
            ok &= top2[1] - top2[0] >= 1  # unique worst weekend
            got = [f"Weekend {k + 1}", int(extras[k])]
        agree = got == t["answer"]
        ok &= agree
        print(t["task_id"], q["type"], "ref", t["answer"], "solver2", got, "OK" if agree else "MISMATCH")
    print("ALL AGREE" if ok else "DISAGREEMENT")


if __name__ == "__main__":
    main()
