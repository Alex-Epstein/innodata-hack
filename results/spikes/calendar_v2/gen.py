"""Calendar v2 spike: Outlook Scheduling Assistant images with chained multi-step questions.

Three templates, 3 accepted seeds each:
  req_opt   required + optional attendees, tentative = free, lunch hour, room must be free
  tz        one attendee shown in London time (GMT), everyone in their own 9:00-17:00
  move      which single movable meeting gives the earliest common 60-minute slot

data dict -> tasks/data/<id>.json -> PNG (pure function of the dict) -> answer computed from the dict.
Seeds are rejected unless every "skipped step" shortcut gives a different answer than the true one
and (for `move`) the three options give three different earliest slots.

    python gen.py            # writes tasks/tasks.jsonl, tasks/images/, tasks/data/
"""
from __future__ import annotations

import json
import os
import random

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Circle, Wedge, FancyBboxPatch

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "tasks")
GEN_VERSION = "cal2-0.1.0"
DAY0, DAY1 = 8 * 60, 18 * 60          # grid columns per day (local time of the row)
WORK0, WORK1 = 9 * 60, 17 * 60        # working hours (shaded outside)
DAYNAMES = ["Mon", "Tue", "Wed", "Thu", "Fri"]
DAYLONG = ["Monday, November 16, 2026", "Tuesday, November 17, 2026", "Wednesday, November 18, 2026"]
REFERENCES = [
    "Microsoft Outlook Scheduling Assistant (classic Outlook for Windows, Meeting > Scheduling Assistant): "
    "attendee rows, room row, free/busy legend Busy / Tentative / Out of Office / Working Elsewhere / No Information",
    "Microsoft Support: 'Use the Scheduling Assistant and Room Finder for meetings in Outlook' "
    "(support.microsoft.com)",
]

NAMES = ["Priya Shah", "Marcus Lee", "Elena Ruiz", "Tom Becker", "Aisha Khan", "Daniel Park",
         "Sofia Moreno", "Kenji Watanabe", "Rachel Cohen", "Jamal Wright", "Grace Liu", "Nate Russo"]
ROOMS = ["NYC-12 Hudson (8)", "NYC-14 Liberty (10)", "NYC-09 Battery (6)"]
TITLES = ["Sprint planning", "Standup", "Budget sync", "Interview", "Customer demo", "Roadmap review",
          "Hiring sync", "QBR prep", "Focus time", "Code review", "Board prep", "Ops sync", "Training",
          "Retro", "Security review", "Pipeline review", "Partner call", "All hands", "Data sync",
          "Design sync", "Staff meeting", "Release check", "Offsite prep"]
OOF_TITLES = ["Out of office", "Doctor appt", "PTO", "Travel"]
ROOM_TITLES = ["Exec staff", "Interview loop", "Board prep", "Client visit", "Training", "Workshop",
               "Town hall prep", "Recruiting"]

# Outlook classic free/busy colors
C_BUSY = "#3b6fc0"
C_TENT_EDGE = "#3b6fc0"
C_OOF = "#7a3e9d"
C_OUTSIDE = "#e8e8e8"
C_GRID = "#d9d9d9"
C_GRID_HOUR = "#a6a6a6"


def hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def ov(a0, a1, b0, b1):
    return a0 < b1 and b0 < a1


# ---------------------------------------------------------------------------------------------- data
def random_day(rng, density, allow_oof=True, lo=DAY0, hi=DAY1, titles=TITLES, tent_p=0.22):
    """Non-overlapping events for one person-day, start/end on the 15-minute grid."""
    evs = []
    if allow_oof and rng.random() < 0.10:
        dur = rng.choice([90, 120, 180])
        s = rng.choice(range(lo, hi - dur + 1, 15))
        evs.append({"start": s, "end": s + dur, "status": "oof", "title": rng.choice(OOF_TITLES)})
    target = density * (hi - lo) * rng.uniform(0.75, 1.25)
    tot, att = sum(e["end"] - e["start"] for e in evs), 0
    while tot < target and att < 300:
        att += 1
        dur = rng.choice([30, 30, 45, 60, 60, 90])
        s = rng.choice(range(lo, hi - dur + 1, 15))
        if any(ov(s, s + dur, e["start"], e["end"]) for e in evs):
            continue
        st = "tentative" if rng.random() < tent_p else "busy"
        evs.append({"start": s, "end": s + dur, "status": st, "title": rng.choice(titles)})
        tot += dur
    return sorted(evs, key=lambda e: e["start"])


def free(evs, s, e, tentative_free):
    for ev in evs:
        if ev["status"] == "tentative" and tentative_free:
            continue
        if ov(s, e, ev["start"], ev["end"]):
            return False
    return True


# ---------------------------------------------------------------------------------------------- planting helpers
def clear(evs, a, b, keep_tentative=False):
    """Drop a row's events that overlap [a, b) (optionally keep tentative ones). In place."""
    evs[:] = [e for e in evs if not ov(a, b, e["start"], e["end"]) or (keep_tentative and e["status"] == "tentative")]


def put(evs, a, b, status, title):
    clear(evs, a, b)
    evs.append({"start": a, "end": b, "status": status, "title": title})
    evs.sort(key=lambda e: e["start"])


def block_piece(rng, evs, s, e, protected, titles=TITLES, status="busy"):
    """Add one busy block to `evs` that overlaps [s, e), avoids `protected` and the row's own events."""
    opts = []
    for L in (30, 45, 60, 15):
        for a in range(s - L + 15, e, 15):
            b = a + L
            if a < DAY0 or b > DAY1 or not ov(a, b, s, e):
                continue
            if any(ov(a, b, p0, p1) for p0, p1 in protected):
                continue
            if any(ov(a, b, x["start"], x["end"]) for x in evs):
                continue
            opts.append((a, b))
    if not opts:
        return False
    a, b = rng.choice(opts)
    evs.append({"start": a, "end": b, "status": status, "title": rng.choice(titles)})
    evs.sort(key=lambda x: x["start"])
    return True


def add_filler(rng, ev, prot, density=0.5, room_names=()):
    """Extra realistic blocks anywhere except the protected windows. Only ever adds busy time, so no
    earlier slot can open up; the answer is re-solved and re-checked afterwards anyway."""
    for r, days in ev.items():
        for dd, evs in days.items():
            target = (density * 0.7 if r in room_names else density) * (DAY1 - DAY0)
            tot = sum(e["end"] - e["start"] for e in evs)
            for _ in range(200):
                if tot >= target:
                    break
                L = rng.choice([30, 30, 45, 60, 60, 90])
                a = rng.choice(range(DAY0, DAY1 - L + 1, 15))
                if any(ov(a, a + L, p0, p1) for p0, p1 in prot.get(r, {}).get(dd, [])):
                    continue
                if any(ov(a, a + L, x["start"], x["end"]) for x in evs):
                    continue
                room = r in room_names
                st = "tentative" if (not room and rng.random() < 0.2) else "busy"
                evs.append({"start": a, "end": a + L, "status": st,
                            "title": rng.choice(ROOM_TITLES if room else TITLES)})
                tot += L
            evs.sort(key=lambda x: x["start"])


def pick_slots(rng, specs, tries=400):
    """specs: list of (name, [(day, start) candidates], dur). Non-overlapping with >=30 min gaps."""
    for _ in range(tries):
        got = {}
        for name, cands, dur in specs:
            c = rng.choice(cands)
            if any(c[0] == g[0] and ov(c[1] - 30, c[1] + dur + 30, g[1], g[1] + g[2]) for g in got.values()):
                break
            got[name] = (c[0], c[1], dur)
        else:
            return got
    return None


# ---------------------------------------------------------------------------------------------- template 1
def build_req_opt(seed):
    rng = random.Random(f"req_opt-{seed}")
    others = rng.sample([n for n in NAMES if n not in ("Priya Shah", "Marcus Lee")], 4)
    people = ["Priya Shah", "Marcus Lee"] + others
    room = rng.choice(ROOMS)
    days = ["Mon", "Tue"]
    ev = {p: {dd: random_day(rng, 0.40 if i < 2 else 0.45) for dd in days} for i, p in enumerate(people)}
    ev[room] = {dd: random_day(rng, 0.30, allow_oof=False, titles=ROOM_TITLES, tent_p=0) for dd in days}
    D = 60
    a_start = rng.choice(list(range(13 * 60, 16 * 60 + 1, 15)) + list(range(10 * 60, 11 * 60 + 1, 15)))
    ok_nolunch = lambda s: s + D <= 720 or s >= 780
    before = lambda dd, s: (days.index(dd), s + D + 30) <= (1, a_start)
    grid = [(dd, s) for dd in days for s in range(WORK0, WORK1 - D + 1, 15)]
    slots = pick_slots(rng, [
        ("A", [("Tue", a_start)], D),
        ("L", [(dd, s) for dd, s in grid if not ok_nolunch(s) and before(dd, s) and s % 60 != 0], D),
        ("R", [(dd, s) for dd, s in grid if ok_nolunch(s) and before(dd, s)], D),
        ("O", [(dd, s) for dd, s in grid if ok_nolunch(s) and before(dd, s)], D),
    ])
    if slots is None:
        return None
    req, opt = people[:2], others
    for name, (dd, s, _) in slots.items():
        e = s + D
        for p in req:
            clear(ev[p][dd], s, e, keep_tentative=True)
        nfree = {"A": 2, "L": rng.choice([2, 3]), "R": rng.choice([2, 3]), "O": 1}[name]
        fr = rng.sample(opt, nfree)
        for p in opt:
            if p in fr:
                clear(ev[p][dd], s, e, keep_tentative=True)
            elif not any(ov(s, e, x["start"], x["end"]) and x["status"] != "tentative" for x in ev[p][dd]):
                a = rng.choice(range(s - 15, e - 15 + 1, 15))
                put(ev[p][dd], max(a, DAY0), min(a + rng.choice([30, 45, 60]), DAY1), "busy", rng.choice(TITLES))
        if name == "A":   # tentative on a required attendee and on one free optional: counts as free
            p = rng.choice(req)
            a = rng.choice([s, s + 15, s + 30])
            put(ev[p][dd], a, a + 30, "tentative", rng.choice(TITLES))
            q = rng.choice(fr)
            a = rng.choice([s - 15, s, s + 30])
            put(ev[q][dd], a, a + 45, "tentative", rng.choice(TITLES))
        if name == "R":
            clear(ev[room][dd], s, e)
            a = rng.choice([s - 30, s - 15, s, s + 15, s + 30])
            put(ev[room][dd], a, a + 60, "busy", rng.choice(ROOM_TITLES))
        else:
            clear(ev[room][dd], s, e)
    d = {"template": "req_opt", "days": days, "duration": D, "required": req, "optional": opt,
         "min_optional": 2, "lunch": [720, 780], "room": room, "window": [WORK0, WORK1],
         "meeting_title": "Q4 Planning Sync", "planted": {k: [v[0], hhmm(v[1])] for k, v in slots.items()}}

    def mk():
        d["rows"] = [{"name": p, "kind": "required" if p in req else "optional", "tz": "ET", "events": ev[p]}
                     for p in people] + [{"name": room, "kind": "room", "tz": "ET", "events": ev[room]}]
    mk()
    # block every other slot that would pass before the planted answer
    for _ in range(200):
        t = solve_req_opt(d, step=15)
        if t == f"Tue {hhmm(a_start)}":
            pw = {dd: [(v[1], v[1] + D) for v in slots.values() if v[0] == dd] for dd in days}
            add_filler(rng, ev, {r: pw for r in ev}, 0.5, room_names=(room,))
            mk()
            return d
        if t is None:
            return None
        dd, hm = t.split()
        s = int(hm[:2]) * 60 + int(hm[3:])
        prot_all = [(v[1], v[1] + D) for v in slots.values() if v[0] == dd]
        prot_room = [(v[1], v[1] + D) for k, v in slots.items() if v[0] == dd and k != "R"]
        tgt = rng.choice(req + [room])
        if not block_piece(rng, ev[tgt][dd], s, s + D, prot_room if tgt == room else prot_all,
                           ROOM_TITLES if tgt == room else TITLES):
            other = [x for x in req + [room] if x != tgt]
            if not any(block_piece(rng, ev[x][dd], s, s + D, prot_room if x == room else prot_all,
                                   ROOM_TITLES if x == room else TITLES) for x in other):
                return None
        mk()
    return None




def solve_req_opt(d, tentative_free=True, use_lunch=True, use_room=True, min_opt=None, use_window=True,
                  step=1, explain=False):
    D = d["duration"]
    min_opt = d["min_optional"] if min_opt is None else min_opt
    rows = {r["name"]: r for r in d["rows"]}
    w0, w1 = d["window"] if use_window else (DAY0, DAY1)
    log = []
    for day in d["days"]:
        for s in range(w0, w1 - D + 1, step):
            e = s + D
            why = []
            req_busy = [p for p in d["required"] if not free(rows[p]["events"][day], s, e, tentative_free)]
            if req_busy:
                why.append("required busy: " + ", ".join(req_busy))
            if use_lunch and ov(s, e, *d["lunch"]):
                why.append("overlaps lunch 12:00-13:00")
            if use_room and not free(rows[d["room"]]["events"][day], s, e, False):
                why.append("room booked")
            opt_free = [p for p in d["optional"] if free(rows[p]["events"][day], s, e, tentative_free)]
            if len(opt_free) < min_opt:
                why.append(f"only {len(opt_free)} optional free ({', '.join(opt_free) or 'none'})")
            if explain and s % 15 == 0:
                log.append({"slot": f"{day} {hhmm(s)}-{hhmm(e)}", "ok": not why, "why": why,
                            "optional_free": opt_free})
            if not why:
                return (f"{day} {hhmm(s)}", log) if explain else f"{day} {hhmm(s)}"
    return (None, log) if explain else None


def accept_req_opt(d):
    if d is None:
        return None
    true = solve_req_opt(d)
    if true is None or solve_req_opt(d, step=15) != true:
        return None
    traps = {
        "tentative_counted_busy": solve_req_opt(d, tentative_free=False),
        "ignored_lunch": solve_req_opt(d, use_lunch=False),
        "ignored_room": solve_req_opt(d, use_room=False),
        "only_1_optional": solve_req_opt(d, min_opt=1),
        "all_4_optional": solve_req_opt(d, min_opt=4),
    }
    if any(v == true for v in traps.values()):
        return None
    if not true.startswith("Tue"):          # make the solver scan the whole first day
        return None
    if len(set(v for v in traps.values() if v)) < 3:   # the shortcuts should give varied wrong answers
        return None
    return true, traps


def question_req_opt(d):
    o = d["optional"]
    return (f"This Outlook Scheduling Assistant screenshot shows the free/busy times of six attendees and the "
            f"room {d['room']} on Monday and Tuesday (all times New York time). I need to book a "
            f"{d['duration']}-minute meeting. Rules: Priya Shah and Marcus Lee are required; at least "
            f"{d['min_optional']} of the other four ({', '.join(o[:-1])} and {o[-1]}) must also be able to attend; "
            f"tentative (hatched) blocks count as free, while busy and out-of-office blocks count as busy; the "
            f"meeting must not overlap the 12:00-13:00 lunch hour; the room row must be free for the whole meeting; "
            f"the meeting must lie within 9:00-17:00 and start on a quarter hour. What is the earliest start time "
            f"that satisfies every rule? Answer as the day and the 24-hour start time, in the form `Tue 09:45` (three-letter day, HH:MM with a leading zero).")


# ---------------------------------------------------------------------------------------------- template 2
LONDON = "Oliver Grant"


def build_tz(seed):
    rng = random.Random(f"tz-{seed}")
    ny = rng.sample([n for n in NAMES], 5)
    days = ["Mon", "Tue"]
    D, off = 45, 300
    ev = {p: {dd: random_day(rng, 0.40) for dd in days} for p in ny}
    lon = {dd: random_day(rng, 0.42, allow_oof=False) for dd in days}
    morning = list(range(WORK0, 12 * 60 - D + 1, 15))
    slots = pick_slots(rng, [
        ("A", [("Tue", s) for s in morning if s >= 9 * 60 + 30], D),
        ("M", [("Mon", s) for s in morning], D),
        ("T", [("Mon", s) for s in morning], D),
        ("H", [("Mon", s) for s in range(12 * 60, 16 * 60 + 1, 15)], D),
    ])
    if slots is None:
        return None
    for name, (dd, s, _) in slots.items():
        e = s + D
        for p in ny:
            clear(ev[p][dd], s, e)
        if name == "A":
            clear(lon[dd], s + off, e + off)
            a = rng.choice([s - 15, s])                      # face-value decoy: busy at the ET-looking spot
            put(lon[dd], a, a + 60, "busy", rng.choice(TITLES))
        elif name == "M":
            clear(lon[dd], s, e)                             # free at face value
            a = rng.choice([s + off - 15, s + off, s + off + 15])
            put(lon[dd], a, a + 30, "busy", rng.choice(TITLES))   # busy once converted
        elif name == "T":
            clear(lon[dd], s + off, e + off)
            p = rng.choice(ny)
            a = rng.choice([s - 15, s, s + 15])
            put(ev[p][dd], a, a + 45, "tentative", rng.choice(TITLES))
        elif name == "H":
            clear(lon[dd], min(s + off, DAY1), min(e + off, DAY1))
    pos = rng.choice([1, 2, 3, 4])
    d = {"template": "tz", "days": days, "duration": D, "offset_min": off, "window_local": [WORK0, WORK1],
         "london": LONDON, "meeting_title": "Vendor Onboarding Review",
         "planted": {k: [v[0], hhmm(v[1])] for k, v in slots.items()}}

    def mk():
        rows = [{"name": p, "kind": "required", "tz": "ET", "events": ev[p]} for p in ny]
        rows.insert(pos, {"name": LONDON, "kind": "required", "tz": "GMT", "label": f"{LONDON} (London, GMT)",
                          "events": lon})
        d["rows"] = rows
    mk()
    want = f"Tue {hhmm(slots['A'][1])}"
    for _ in range(200):
        t = solve_tz(d, step=15)
        if t == want:
            pw = {dd: [(v[1], v[1] + D) for v in slots.values() if v[0] == dd] for dd in days}
            lw = {dd: [(v[1] + off, v[1] + off + D) for k, v in slots.items() if v[0] == dd and k != "M"] +
                  [(v[1], v[1] + D) for k, v in slots.items() if v[0] == dd and k == "M"] for dd in days}
            evall = dict(ev)
            evall[LONDON] = lon
            add_filler(rng, evall, {**{p: pw for p in ny}, LONDON: lw}, 0.5)
            mk()
            return d
        if t is None:
            return None
        dd, hm = t.split()
        s = int(hm[:2]) * 60 + int(hm[3:])
        prot = [(v[1], v[1] + D) for v in slots.values() if v[0] == dd]
        cand = rng.sample(ny, len(ny))
        if not any(block_piece(rng, ev[p][dd], s, s + D, prot) for p in cand):
            return None
        mk()
    return None




def solve_tz(d, convert=1, london_hours=True, tentative_free=False, step=1, explain=False):
    """convert=1: ET = GMT - 5 h (correct); 0: read London row as ET; -1: wrong direction."""
    D, off = d["duration"], d["offset_min"]
    w0, w1 = d["window_local"]
    log = []
    for day in d["days"]:
        for s in range(w0, w1 - D + 1, step):
            e = s + D
            why = []
            for r in d["rows"]:
                if r["tz"] == "GMT":
                    shift = off * convert            # local = ET + shift
                    ls, le = s + shift, e + shift
                    if london_hours and not (ls >= w0 and le <= w1):
                        why.append(f"{r['name']} outside 9-17 London ({hhmm(ls)}-{hhmm(le)} GMT)")
                        continue
                    if not free(r["events"][day], ls, le, tentative_free):
                        why.append(f"{r['name']} busy ({hhmm(ls)}-{hhmm(le)} GMT)")
                else:
                    if not free(r["events"][day], s, e, tentative_free):
                        why.append(f"{r['name']} busy")
            if explain and s % 15 == 0:
                log.append({"slot_et": f"{day} {hhmm(s)}-{hhmm(e)}", "ok": not why, "why": why})
            if not why:
                return (f"{day} {hhmm(s)}", log) if explain else f"{day} {hhmm(s)}"
    return (None, log) if explain else None


def accept_tz(d):
    if d is None:
        return None
    true = solve_tz(d)
    if true is None or solve_tz(d, step=15) != true:
        return None
    traps = {
        "no_conversion": solve_tz(d, convert=0),
        "wrong_direction": solve_tz(d, convert=-1),
        "ignored_london_hours": solve_tz(d, london_hours=False),
        "tentative_counted_free": solve_tz(d, tentative_free=True),
    }
    if any(v == true for v in traps.values()):
        return None
    if not true.startswith("Tue"):
        return None
    if traps["no_conversion"] is None or traps["ignored_london_hours"] is None:
        return None
    return true, traps


def question_tz(d):
    names = [r["name"] for r in d["rows"]]
    return (f"This Outlook Scheduling Assistant screenshot shows six attendees ({', '.join(names)}) on Monday "
            f"and Tuesday. Every row is drawn in that attendee's own local time against the time scale at the top: "
            f"{d['london']}'s row (labeled London, GMT) is in London time, and every other row is in New York time "
            f"(ET). ET = GMT - 5 hours on these dates. Each attendee can only meet between 9:00 and 17:00 in their "
            f"own local time. Treat busy, tentative (hatched) and out-of-office blocks all as busy. What is the "
            f"earliest {d['duration']}-minute slot, starting on a quarter hour, when all six can attend? Give the "
            f"start in New York time (ET) as the day and 24-hour time, in the form `Tue 09:45` (three-letter day, HH:MM with a leading zero).")


# ---------------------------------------------------------------------------------------------- template 3
MOVABLE = ["Design review", "Vendor call", "1:1 Priya / Tom"]


def build_move(seed):
    rng = random.Random(f"move-{seed}")
    others = rng.sample([n for n in NAMES if n not in ("Priya Shah", "Tom Becker")], 4)
    people = ["Priya Shah", "Tom Becker"] + others
    rng.shuffle(people)
    room = rng.choice(ROOMS)
    day = "Wed"
    D = 60
    ev = {p: random_day(rng, 0.38) for p in people}
    ev[room] = random_day(rng, 0.28, allow_oof=False, titles=ROOM_TITLES, tent_p=0)
    att = {"Design review": rng.sample(people, 3), "Vendor call": rng.sample(people, 2),
           "1:1 Priya / Tom": ["Priya Shah", "Tom Becker"]}
    dur = {"Design review": 60, "Vendor call": rng.choice([45, 60]), "1:1 Priya / Tom": 45}
    X, Z = rng.sample(MOVABLE, 2)                      # X = answer, Z = earliest meeting but no help
    Y = next(m for m in MOVABLE if m not in (X, Z))
    z0 = rng.choice([9 * 60, 9 * 60 + 15, 9 * 60 + 30])
    wx = rng.choice(range(z0 + dur[Z] + 15, 12 * 60 + 1, 15))
    wy = rng.choice(range(wx + 90, 14 * 60 + 31, 15)) if wx + 90 <= 14 * 60 + 30 else None
    if wy is None:
        return None
    B = rng.choice(range(wy + 75, 16 * 60 + 1, 15)) if wy + 75 <= 16 * 60 else None
    if B is None:
        return None
    windows = {X: wx, Y: wy}
    for w in (wx, wy, B):
        for r in ev:
            clear(ev[r], w, w + D)
    placed = []
    for m in (X, Y):
        offs = sorted({0, D - dur[m]})
        a = windows[m] + rng.choice(offs)
        for p in att[m]:
            put(ev[p], a, a + dur[m], "busy", m)
        placed.append({"title": m, "start": a, "end": a + dur[m], "attendees": att[m]})
    for p in att[Z]:
        put(ev[p], z0, z0 + dur[Z], "busy", Z)
    placed.append({"title": Z, "start": z0, "end": z0 + dur[Z], "attendees": att[Z]})
    placed.sort(key=lambda m: m["start"])
    d = {"template": "move", "days": [day], "duration": D, "room": room, "window": [WORK0, WORK1],
         "movable": placed, "meeting_title": "Launch Go/No-Go",
         "planted": {"answer": X, "second": Y, "no_help": Z, "wx": hhmm(wx), "wy": hhmm(wy), "baseline": hhmm(B)}}

    def mk():
        d["rows"] = [{"name": p, "kind": "required", "tz": "ET", "events": {day: ev[p]}} for p in people] + \
                    [{"name": room, "kind": "room", "tz": "ET", "events": {day: ev[room]}}]
    mk()
    target = {None: B, X: wx, Y: wy, Z: B}
    prot = [(wx, wx + D), (wy, wy + D), (B, B + D)]
    mov_times = [(m["start"], m["end"]) for m in placed]
    for _ in range(300):
        bad = None
        for opt, want in target.items():
            got = earliest_move(d, opt, step=15)
            if got is None:
                return None
            if got < want:
                bad = got
                break
            if got != want:
                return None
        if bad is None:
            wrapped = {r: {day: ev[r]} for r in ev}
            add_filler(rng, wrapped, {r: {day: prot} for r in ev}, 0.45, room_names=(room,))
            mk()
            return d
        rows = list(ev)
        rng.shuffle(rows)
        if not any(block_piece(rng, ev[r], bad, bad + D, prot + mov_times,
                               ROOM_TITLES if r == room else TITLES) for r in rows):
            return None
        mk()
    return None


def earliest_move(d, removed=None, partial=False, tentative_free=False, use_room=True, step=1):
    day = d["days"][0]
    D = d["duration"]
    w0, w1 = d["window"]
    rem = next((m for m in d["movable"] if m["title"] == removed), None)
    for s in range(w0, w1 - D + 1, step):
        ok = True
        for r in d["rows"]:
            if r["kind"] == "room" and not use_room:
                continue
            evs = r["events"][day]
            if rem is not None and r["name"] in (rem["attendees"][:1] if partial else rem["attendees"]):
                evs = [e for e in evs if e["title"] != rem["title"]]
            if not free(evs, s, s + D, tentative_free):
                ok = False
                break
        if ok:
            return s
    return None


def accept_move(d):
    if d is None:
        return None
    base = earliest_move(d)
    res = {m: earliest_move(d, m) for m in MOVABLE}
    if any(res[m] != earliest_move(d, m, step=15) for m in MOVABLE):
        return None
    vals = [v for v in res.values() if v is not None]
    if len(vals) < 3 or len(set(vals)) != 3:          # no ties, every move gives some slot
        return None
    best = min(MOVABLE, key=lambda m: res[m])
    if base is not None and base <= res[best]:
        return None
    improving = [m for m in MOVABLE if base is None or res[m] < base]
    if len(improving) < 2:
        return None
    # the earliest-in-the-day movable meeting must not be the answer (no "move the first one" shortcut)
    first = min(d["movable"], key=lambda m: m["start"])["title"]
    if first == best:
        return None
    traps = {
        "only_first_attendee_freed": min(MOVABLE, key=lambda m: (earliest_move(d, m, partial=True) or 9999)),
        "ignored_room": min(MOVABLE, key=lambda m: (earliest_move(d, m, use_room=False) or 9999)),
        "move_earliest_meeting": first,
    }
    return best, {"baseline": base, "per_move": res, "traps": traps}


def question_move(d):
    names = [r["name"] for r in d["rows"] if r["kind"] != "room"]
    return (f"This Outlook Scheduling Assistant screenshot shows six attendees ({', '.join(names)}) and the room "
            f"{d['room']} on Wednesday. I need a 60-minute meeting with all six attendees in that room, within "
            f"9:00-17:00, starting on a quarter hour. Treat busy, tentative (hatched) and out-of-office blocks all as "
            f"busy. Exactly one of these existing meetings may be moved to another day: Design review, Vendor call, "
            f"or 1:1 Priya / Tom (moving a meeting frees that time for everyone who attends it; nothing else "
            f"changes). Which single move creates the earliest possible start for the new meeting? Answer with the "
            f"meeting name exactly as written above.")


# ---------------------------------------------------------------------------------------------- render
def person_icon(ax, x, y, kind):
    col = "#5b5b5b"
    if kind == "room":
        ax.add_patch(Rectangle((x - 6, y - 7), 12, 14, facecolor="white", edgecolor=col, lw=1.2, zorder=5))
        for dx in (-3, 1):
            for dy in (-4, 0):
                ax.add_patch(Rectangle((x + dx, y + dy), 2, 2, facecolor=col, lw=0, zorder=6))
        return
    ax.add_patch(Circle((x, y - 3), 3.6, facecolor=col, lw=0, zorder=5))
    ax.add_patch(Wedge((x, y + 8), 7, 180, 360, facecolor=col, lw=0, zorder=5))
    if kind == "optional":
        ax.add_patch(Circle((x + 7, y + 4), 4.2, facecolor="white", edgecolor="#3b6fc0", lw=1, zorder=6))
        ax.text(x + 7, y + 4.3, "i", fontsize=8, ha="center", va="center", color="#3b6fc0", zorder=7,
                weight="bold")
    else:
        ax.add_patch(Circle((x + 7, y + 4), 4.2, facecolor="white", edgecolor="#2e7d32", lw=1, zorder=6))
        ax.text(x + 7, y + 4.3, "↑", fontsize=8, ha="center", va="center", color="#2e7d32", zorder=7)


def render(d, path):
    W, H = 1600, 1000
    fig = plt.figure(figsize=(16, 10), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.axis("off")
    fig.patch.set_facecolor("white")
    plt.rcParams["hatch.linewidth"] = 1.4
    rend = fig.canvas.get_renderer()
    dropped = []

    # title bar + ribbon tabs
    ax.add_patch(Rectangle((0, 0), W, 34, facecolor="#2b579a", lw=0))
    ax.text(16, 17, f"{d['meeting_title']}  -  Meeting", fontsize=11, color="white", va="center")
    for i, sym in enumerate(["—", "□", "✕"]):
        ax.text(W - 100 + i * 36, 17, sym, fontsize=11, color="white", va="center", ha="center")
    ax.add_patch(Rectangle((0, 34), W, 34, facecolor="#f3f3f3", lw=0))
    tx = 16
    for t in ["File", "Meeting", "Scheduling Assistant", "Insert", "Format Text", "Review", "Help"]:
        ax.text(tx, 51, t, fontsize=10, va="center", color="#2b579a" if t == "Scheduling Assistant" else "#333333",
                weight="bold" if t == "Scheduling Assistant" else "normal")
        tw = ax.texts[-1].get_window_extent(rend).width
        if t == "Scheduling Assistant":
            ax.plot([tx, tx + tw], [64, 64], color="#2b579a", lw=2.5)
        tx += tw + 26
    # toolbar
    ax.add_patch(Rectangle((0, 68), W, 44, facecolor="#fafafa", edgecolor="#e1e1e1", lw=0.8))
    ax.add_patch(FancyBboxPatch((16, 77), 64, 26, boxstyle="round,pad=0,rounding_size=3", facecolor="#2b579a", lw=0))
    ax.text(48, 90, "Send", fontsize=10, color="white", ha="center", va="center")
    for i, t in enumerate(["Add Attendees", "Options", "Room Finder", "Time zones: (UTC-05:00) Eastern Time"]):
        ax.text(110 + i * 150 if i < 3 else 560, 90, t, fontsize=9.5, va="center", color="#333333")

    days = d["days"]
    nd = len(days)
    left, right = 280, W - 16
    top = 128
    dayw = (right - left) / nd
    span = DAY1 - DAY0
    X = lambda di, m: left + di * dayw + (m - DAY0) / span * dayw
    rowh = 54
    hdr_h = 60
    nrows = len(d["rows"])
    gy0 = top + hdr_h
    gy1 = gy0 + (nrows + 3) * rowh

    # header: "All Attendees" cell + day bars + time labels
    ax.add_patch(Rectangle((16, top), left - 16, hdr_h, facecolor="#f3f3f3", edgecolor="#c8c8c8", lw=0.8))
    ax.add_patch(Rectangle((26, top + 18), 12, 12, facecolor="white", edgecolor="#555555", lw=1))
    ax.plot([28, 31, 36], [top + 24, top + 28, top + 20], color="#2b579a", lw=1.5)
    ax.text(46, top + 24, "All Attendees", fontsize=10, va="center", color="#222222")
    for di, day in enumerate(days):
        x0 = left + di * dayw
        ax.add_patch(Rectangle((x0, top), dayw, 24, facecolor="#e9eef6", edgecolor="#c8c8c8", lw=0.8))
        idx = DAYNAMES.index(day)
        ax.text(x0 + 8, top + 12, DAYLONG[idx], fontsize=10, va="center", color="#222222", weight="bold")
        ax.add_patch(Rectangle((x0, top + 24), dayw, hdr_h - 24, facecolor="white", edgecolor="#c8c8c8", lw=0.8))
        for m in range(DAY0, DAY1, 30):
            xm = X(di, m)
            if m % 60 == 0:
                ax.text(xm + 2, top + 33, f"{m // 60}:00", fontsize=8.5, va="center", ha="left", color="#222222")
            else:
                ax.text(xm + 2, top + 45, ":30", fontsize=8, va="center", ha="left", color="#555555")

    # rows
    for ri, r in enumerate(d["rows"]):
        y0 = gy0 + ri * rowh
        ax.add_patch(Rectangle((16, y0), left - 16, rowh, facecolor="white", edgecolor="#d0d0d0", lw=0.8))
        ax.add_patch(Rectangle((26, y0 + rowh / 2 - 6), 12, 12, facecolor="white", edgecolor="#555555", lw=1))
        ax.plot([28, 31, 36], [y0 + rowh / 2, y0 + rowh / 2 + 4, y0 + rowh / 2 - 4], color="#2b579a", lw=1.5)
        person_icon(ax, 56, y0 + rowh / 2, r["kind"])
        lab = r.get("label", r["name"])
        t = ax.text(74, y0 + rowh / 2, lab, fontsize=10, va="center", color="#222222")
        assert t.get_window_extent(rend).x1 < left - 4, lab
        for di, day in enumerate(days):
            # outside working hours shading (in the row's own local time)
            for a, b in [(DAY0, WORK0), (WORK1, DAY1)]:
                ax.add_patch(Rectangle((X(di, a), y0), X(di, b) - X(di, a), rowh, facecolor=C_OUTSIDE, lw=0, zorder=1))
            for ev in r["events"][day]:
                x0, x1 = X(di, ev["start"]), X(di, ev["end"])
                by0, bh = y0 + 7, rowh - 14
                if ev["status"] == "busy":
                    ax.add_patch(Rectangle((x0, by0), x1 - x0, bh, facecolor=C_BUSY, edgecolor="white", lw=1, zorder=4))
                    tc = "white"
                elif ev["status"] == "oof":
                    ax.add_patch(Rectangle((x0, by0), x1 - x0, bh, facecolor=C_OOF, edgecolor="white", lw=1, zorder=4))
                    tc = "white"
                else:
                    ax.add_patch(Rectangle((x0, by0), x1 - x0, bh, facecolor="white", edgecolor=C_TENT_EDGE,
                                           hatch="///", lw=1.2, zorder=4))
                    tc = "#1d3f73"
                tt = ax.text(x0 + 4, y0 + rowh / 2, ev["title"], fontsize=8, va="center", ha="left", color=tc,
                             zorder=6, bbox=None if ev["status"] != "tentative" else
                             dict(facecolor="white", edgecolor="none", pad=0.6))
                bb = tt.get_window_extent(rend)
                if bb.x1 > x1 - 3:
                    tt.remove()
                    dropped.append(ev["title"])
    # empty rows like Outlook
    for k in range(3):
        y0 = gy0 + (nrows + k) * rowh
        ax.add_patch(Rectangle((16, y0), left - 16, rowh, facecolor="white", edgecolor="#d0d0d0", lw=0.8))
        if k == 0:
            ax.text(46, y0 + rowh / 2, "Click here to add a name", fontsize=9.5, va="center", color="#8a8a8a",
                    style="italic")
    # grid lines (quarter hours)
    for di in range(nd):
        for m in range(DAY0, DAY1 + 1, 15):
            xm = X(di, m)
            if m % 60 == 0:
                ax.plot([xm, xm], [top + 24, gy1], color=C_GRID_HOUR, lw=0.9, zorder=2)
            elif m % 30 == 0:
                ax.plot([xm, xm], [top + 24, gy1], color="#c4c4c4", lw=0.7, zorder=2)
            else:
                ax.plot([xm, xm], [top + 52, gy1], color="#e2e2e2", lw=0.6, zorder=2)
        ax.plot([left + di * dayw] * 2, [top, gy1], color="#555555", lw=1.6, zorder=7)
    for k in range(nrows + 4):
        yy = gy0 + k * rowh
        ax.plot([left, right], [yy, yy], color="#d0d0d0", lw=0.8, zorder=3)
    ax.plot([right, right], [top, gy1], color="#555555", lw=1.2, zorder=7)

    # bottom: AutoPick + start/end + legend
    by = gy1 + 26
    ax.add_patch(Rectangle((16, by - 13), 120, 26, facecolor="#f3f3f3", edgecolor="#bdbdbd", lw=0.8))
    ax.text(76, by, "AutoPick Next  »", fontsize=9.5, ha="center", va="center", color="#333333")
    lx, ly = 300, by
    legend = [("Busy", "busy"), ("Tentative", "tent"), ("Out of Office", "oof"), ("Working Elsewhere", "we"),
              ("No Information", "ni"), ("Outside of working hours", "out")]
    for lab, k in legend:
        if k == "busy":
            p = Rectangle((lx, ly - 8), 28, 16, facecolor=C_BUSY, lw=0)
        elif k == "tent":
            p = Rectangle((lx, ly - 8), 28, 16, facecolor="white", edgecolor=C_TENT_EDGE, hatch="///", lw=1.2)
        elif k == "oof":
            p = Rectangle((lx, ly - 8), 28, 16, facecolor=C_OOF, lw=0)
        elif k == "we":
            p = Rectangle((lx, ly - 8), 28, 16, facecolor="white", edgecolor=C_BUSY, hatch="..", lw=1)
        elif k == "ni":
            p = Rectangle((lx, ly - 8), 28, 16, facecolor="white", edgecolor="#9e9e9e", hatch="xx", lw=1)
        else:
            p = Rectangle((lx, ly - 8), 28, 16, facecolor=C_OUTSIDE, edgecolor="#bdbdbd", lw=0.8)
        ax.add_patch(p)
        t = ax.text(lx + 36, ly, lab, fontsize=9.5, va="center", color="#333333")
        lx = t.get_window_extent(rend).x1 + 28
    sy = by + 44
    for i, (lab, val) in enumerate([("Start time", f"{DAYNAMES[DAYNAMES.index(days[0])]} 11/{16 + DAYNAMES.index(days[0])}/2026"),
                                    ("End time", f"{DAYNAMES[DAYNAMES.index(days[0])]} 11/{16 + DAYNAMES.index(days[0])}/2026")]):
        yy = sy + i * 36
        ax.text(16, yy, lab, fontsize=9.5, va="center", color="#333333")
        ax.add_patch(Rectangle((96, yy - 12), 150, 24, facecolor="white", edgecolor="#bdbdbd", lw=0.8))
        ax.text(104, yy, val, fontsize=9.5, va="center", color="#333333")
        ax.add_patch(Rectangle((254, yy - 12), 70, 24, facecolor="white", edgecolor="#bdbdbd", lw=0.8))
        ax.text(262, yy, "--:--", fontsize=9.5, va="center", color="#9e9e9e")
    fig.savefig(path, dpi=100, facecolor="white")
    plt.close(fig)
    return dropped


# ---------------------------------------------------------------------------------------------- steps
def steps_req_opt(d, true, traps):
    ans, log = solve_req_opt(d, explain=True)
    rows = {r["name"]: r for r in d["rows"]}
    st = [
        "1. Treat tentative as free: Priya/Marcus busy (busy+OOF only) intervals: " + "; ".join(
            f"{p} {day}: " + ", ".join(f"{hhmm(e['start'])}-{hhmm(e['end'])}" for e in rows[p]["events"][day]
                                       if e["status"] != "tentative")
            for p in d["required"] for day in d["days"]),
        "2. Room bookings: " + "; ".join(
            f"{day}: " + ", ".join(f"{hhmm(e['start'])}-{hhmm(e['end'])}" for e in rows[d['room']]["events"][day])
            for day in d["days"]),
        "3. Remove 12:00-13:00 and keep 9:00-17:00.",
        "4. For each remaining 60-minute candidate, count optional attendees free (need >= 2).",
        f"5. Earliest passing start: {true}.",
    ]
    rejected = [x for x in log if not x["ok"]]
    return {"chain": st, "candidate_log_quarter_hours": log, "answer": true, "shortcut_answers": traps,
            "n_rejected_candidates": len(rejected)}


def steps_tz(d, true, traps):
    ans, log = solve_tz(d, explain=True)
    lon = next(r for r in d["rows"] if r["tz"] == "GMT")
    conv = {day: [f"{hhmm(e['start'])}-{hhmm(e['end'])} GMT = {hhmm(e['start'] - 300)}-{hhmm(e['end'] - 300)} ET"
                  + (" (tentative)" if e["status"] == "tentative" else "")
                  for e in lon["events"][day]] for day in d["days"]}
    st = [
        f"1. Convert {lon['name']}'s blocks to ET (subtract 5 h): {json.dumps(conv)}",
        "2. London 9:00-17:00 GMT = 4:00-12:00 ET; New York 9:00-17:00 ET; common window 9:00-12:00 ET each day.",
        "3. Within 9:00-12:00 ET, intersect free time of all six (tentative = busy).",
        f"4. Earliest 45-minute start: {true} ET.",
    ]
    return {"chain": st, "candidate_log_quarter_hours": [x for x in log], "answer": true, "shortcut_answers": traps}


def steps_move(d, best, info):
    day = d["days"][0]
    st = ["1. Locate each movable meeting and all its attendees: " + "; ".join(
        f"{m['title']} {hhmm(m['start'])}-{hhmm(m['end'])} ({', '.join(m['attendees'])})" for m in d["movable"]),
          f"2. Baseline earliest common 60-min start (room included, 9-17): "
          f"{hhmm(info['baseline']) if info['baseline'] is not None else 'none'}"]
    for i, m in enumerate(MOVABLE):
        st.append(f"{3 + i}. Remove {m}: earliest start {hhmm(info['per_move'][m])}")
    st.append(f"6. Earliest is {best}.")
    return {"chain": st, "answer": best,
            "per_move_earliest": {k: hhmm(v) for k, v in info["per_move"].items()},
            "baseline": hhmm(info["baseline"]) if info["baseline"] is not None else None,
            "shortcut_answers": info["traps"]}


# ---------------------------------------------------------------------------------------------- main
TEMPLATES = {
    "reqopt": (build_req_opt, accept_req_opt, question_req_opt, steps_req_opt, "cal2.required_optional_room",
               {"days": 2, "people": 6, "room": True, "duration": 60, "constraints": 5}),
    "tz": (build_tz, accept_tz, question_tz, steps_tz, "cal2.timezone_earliest_slot",
           {"days": 2, "people": 6, "tz_rows": 1, "duration": 45, "constraints": 4}),
    "move": (build_move, accept_move, question_move, steps_move, "cal2.move_one_meeting",
             {"days": 1, "people": 6, "room": True, "duration": 60, "options": 3}),
}


def main():
    os.makedirs(os.path.join(OUT, "images"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "data"), exist_ok=True)
    lines = []
    for key, (build, accept, qfn, sfn, qtype, diff) in TEMPLATES.items():
        got, seed, tried = 0, 0, 0
        while got < 3:
            seed += 1
            tried += 1
            d = build(seed)
            acc = accept(d) if d is not None else None
            if acc is None:
                continue
            ans, extra = acc
            tid = f"cal2-{key}-{seed:06d}"
            img_rel = f"images/{tid}.png"
            steps = sfn(d, ans, extra)
            data = {"task_id": tid, "family": "calendar", "seed": seed, "generator_version": GEN_VERSION,
                    "params": diff, "data": d, "references": REFERENCES}
            with open(os.path.join(OUT, "data", f"{tid}.json"), "w") as f:
                json.dump(data, f, indent=1)
            dropped = render(d, os.path.join(OUT, img_rel))
            if key == "move":       # the movable meetings' names must be readable in the picture
                assert not set(MOVABLE) & set(dropped), (tid, dropped)
            lines.append({"task_id": tid, "image": img_rel, "question": qfn(d), "answer": ans,
                          "answer_type": "label", "seed": seed, "generator_version": GEN_VERSION,
                          "question_type": qtype, "family": "calendar", "difficulty": diff,
                          "data": f"data/{tid}.json", "steps": steps, "references": REFERENCES})
            got += 1
            print(tid, "->", ans, "| shortcuts:", extra if key != "move" else
                  {k: v for k, v in extra.items() if k != "traps"} | extra["traps"])
        print(f"  {key}: accepted 3 of {tried} seeds")
    with open(os.path.join(OUT, "tasks.jsonl"), "w") as f:
        for l in lines:
            f.write(json.dumps(l) + "\n")


if __name__ == "__main__":
    main()
