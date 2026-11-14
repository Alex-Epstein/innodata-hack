"""Independent minute-level brute force over tasks/data/*.json (does not import gen.py)."""
import json, glob, os, sys
T = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks")
tasks = {json.loads(l)["task_id"]: json.loads(l) for l in open(os.path.join(T, "tasks.jsonl"))}
def busy(evs, a, b, tent_busy):
    return any(e["start"] < b and a < e["end"] and (tent_busy or e["status"] != "tentative") for e in evs)
fmt = lambda day, m: f"{day} {m // 60:02d}:{m % 60:02d}"
ok = True
for tid, t in tasks.items():
    d = json.load(open(os.path.join(T, t["data"])))["data"]
    rows = d["rows"]
    if d["template"] == "req_opt":
        sols = [fmt(day, s) for day in d["days"] for s in range(540, 1020 - 60 + 1)
                if s % 15 == 0 and not (s < 780 and s + 60 > 720)
                and not any(busy(r["events"][day], s, s + 60, False) for r in rows if r["kind"] == "required")
                and not busy(next(r for r in rows if r["kind"] == "room")["events"][day], s, s + 60, True)
                and sum(not busy(r["events"][day], s, s + 60, False) for r in rows if r["kind"] == "optional") >= 2]
        got = sols[0]
    elif d["template"] == "tz":
        def okslot(day, s):
            for r in rows:
                sh = 300 if r["tz"] == "GMT" else 0
                a, b = s + sh, s + 45 + sh
                if a < 540 or b > 1020 or busy(r["events"][day], a, b, True):
                    return False
            return True
        got = [fmt(day, s) for day in d["days"] for s in range(540, 1020 - 45 + 1, 15) if okslot(day, s)][0]
    else:
        day = d["days"][0]
        res = {}
        for m in d["movable"]:
            for s in range(540, 1020 - 60 + 1, 15):
                if all(not busy([e for e in r["events"][day] if not (e["title"] == m["title"] and r["name"] in m["attendees"])], s, s + 60, True) for r in rows):
                    res[m["title"]] = s; break
        assert len(set(res.values())) == 3, res
        got = min(res, key=res.get)
    print(tid, got, "OK" if got == t["answer"] else f"MISMATCH (task says {t['answer']})")
    ok &= got == t["answer"]
sys.exit(0 if ok else 1)
