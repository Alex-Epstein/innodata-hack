"""Independent second solver for the subway spike: Dijkstra (heapq) on an expanded graph built from the coords in
data/*.json (not from the station-name lists gen.py solved on). Must agree with every reference answer.

    uv run python results/spikes/subway/check.py
"""
import heapq
import json
import pathlib

TASKS = pathlib.Path(__file__).parent / "tasks"


def solve2(data, a, b, metric, closed):
    name_at = {}
    for ln in data["lines"]:
        for s, c in zip(ln["stations"], ln["coords"]):
            name_at[tuple(c)] = s
    adj = {}
    for li, ln in enumerate(data["lines"]):
        cs = [tuple(c) for c in ln["coords"]]
        for p, q in zip(cs, cs[1:]):
            for u, v in ((p, q), (q, p)):
                adj.setdefault((u, li), []).append(((v, li), (1, 0)))
    nodes = {n for n in adj}
    for (c, li) in nodes:
        if name_at[c] == closed:
            continue
        for (c2, lj) in nodes:
            if c2 == c and lj != li:
                adj[(c, li)].append(((c, lj), (0, 1)))
    w = (lambda t: t[0]) if metric == "stops" else (lambda t: t[1])
    start = [n for n in nodes if name_at[n[0]] == a]
    pq = [(0, n) for n in start]
    seen = {}
    while pq:
        d, n = heapq.heappop(pq)
        if n in seen:
            continue
        seen[n] = d
        if name_at[n[0]] == b:
            return d
        for m, cost in adj.get(n, []):
            if m not in seen:
                heapq.heappush(pq, (d + w(cost), m))
    return None


def main():
    ok = True
    for line in (TASKS / "tasks.jsonl").read_text(encoding="utf-8").splitlines():
        t = json.loads(line)
        rec = json.loads((TASKS / t["data"]).read_text(encoding="utf-8"))
        q = rec["question"]
        metric = "transfers" if q["type"] == "subway.fewest_transfers" else "stops"
        got = solve2(rec["data"], q["from"], q["to"], metric, rec["data"]["closed"])
        agree = got == t["answer"]
        ok &= agree
        print(t["task_id"], q["type"], "ref", t["answer"], "solver2", got, "OK" if agree else "MISMATCH")
    print("ALL AGREE" if ok else "DISAGREEMENT")


if __name__ == "__main__":
    main()
