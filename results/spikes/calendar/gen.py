"""Generate 9 team-calendar tasks (3 levels x 3 seeds): data -> render -> ground truth."""
import json, random, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

OUT = os.path.dirname(os.path.abspath(__file__))
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
DAY_FULL = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
START, END = 8 * 60, 18 * 60
NAMES = ["Priya Shah", "Marcus Lee", "Elena Ruiz", "Tom Becker", "Aisha Khan", "Daniel Park",
         "Sofia Moreno", "Kenji Watanabe"]
COLORS = [("#d2e3fc", "#1a73e8"), ("#fce8b2", "#e37400"), ("#ceead6", "#188038"),
          ("#f6d6e6", "#c2185b"), ("#e4d7f5", "#7b1fa2"), ("#fad2cf", "#d93025"),
          ("#cbf0f8", "#007b83"), ("#e8eaed", "#5f6368")]
TITLES = ["Sprint planning", "Vendor call", "Standup", "Design review", "Budget sync", "Interview",
          "Customer demo", "Roadmap review", "Hiring sync", "QBR prep", "Focus time", "Team lunch",
          "Code review", "Board prep", "Ops sync", "Training", "Retro", "Offsite prep",
          "Security review", "Pipeline review", "Dentist", "Partner call", "All hands", "Data sync"]

LEVELS = {
    "L1": dict(n=3, D=30, p=0.20, ans_days=[0, 1], near=0),
    "L2": dict(n=4, D=45, p=0.35, ans_days=[1, 2, 3], near=1),
    "L3": dict(n=6, D=60, p=0.45, ans_days=[2, 3, 4], near=3),
}


def hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def overlaps(a0, a1, ivs):
    return any(a0 < b1 and b0 < a1 for b0, b1 in ivs)


def title_for(rng, people, me):
    if rng.random() < 0.25:
        other = rng.choice([p for p in people if p != me]).split()[0]
        return f"1:1 with {other}"
    return rng.choice(TITLES)


def build(level, seed):
    cfg = LEVELS[level]
    rng = random.Random(f"{level}-{seed}")
    people = rng.sample(NAMES, cfg["n"])
    D = cfg["D"]
    ans_day = rng.choice(cfg["ans_days"])
    # designed common-free windows: (day, start, end)
    windows = []
    ans_start = rng.choice(range(9 * 60, 16 * 60 + 1, 15)) if level != "L1" else rng.choice(range(9 * 60 + 30, 15 * 60 + 1, 15))
    ans_len = D + rng.choice([0, 0, 15, 30])
    windows.append((ans_day, ans_start, ans_start + ans_len))
    # near misses (length D-15) strictly before the answer
    def free_spot(day, length, lo, hi):
        for _ in range(500):
            s = rng.choice(range(lo, hi - length + 1, 15))
            if all(not (w[0] == day and s - 30 < w[2] and w[1] < s + length + 30) for w in windows):
                return s
        return None
    nm = 0
    tries = 0
    while nm < cfg["near"] and tries < 200:
        tries += 1
        day = rng.choice(range(0, ans_day + 1))
        hi = ans_start - 30 if day == ans_day else 17 * 60 + 30
        if hi - (8 * 60 + 30) < D:
            continue
        s = free_spot(day, D - 15, 8 * 60 + 30, hi)
        if s is not None:
            windows.append((day, s, s + D - 15)); nm += 1
    # small 15/30 min distractor gaps before the answer
    for _ in range(rng.randint(2, 4)):
        day = rng.choice(range(0, ans_day + 1))
        L = rng.choice([15, 30]) if D > 30 else 15
        hi = ans_start - 30 if day == ans_day else 17 * 60 + 30
        if hi - (8 * 60 + 30) < L + 30:
            continue
        s = free_spot(day, L, 8 * 60 + 30, hi)
        if s is not None:
            windows.append((day, s, s + L))

    cal = {p: {d: [] for d in DAYS} for p in people}

    def add(p, d, s, e):
        cal[p][DAYS[d]].append({"start": s, "end": e, "title": title_for(rng, people, p)})

    def busy(p, d):
        return [(m["start"], m["end"]) for m in cal[p][DAYS[d]]]

    wins = lambda d: [(w[1], w[2]) for w in windows if w[0] == d]
    for d in range(5):
        # base random meetings
        for p in people:
            target = cfg["p"] * (END - START) * rng.uniform(0.7, 1.3)
            tot, att = 0, 0
            while tot < target and att < 200:
                att += 1
                dur = rng.choice([15, 30, 30, 45, 60, 60, 90])
                s = rng.choice(range(START, END - dur + 1, 15))
                if overlaps(s, s + dur, busy(p, d)) or overlaps(s, s + dur, wins(d)):
                    continue
                add(p, d, s, s + dur); tot += dur
        if d > ans_day:
            continue
        # fill: every 15-min slot outside designed windows must be covered by someone
        for s in range(START, END, 15):
            if overlaps(s, s + 15, wins(d)):
                continue
            if any(overlaps(s, s + 15, busy(p, d)) for p in people):
                continue
            p = rng.choice(people)
            dur = rng.choice([30, 30, 45, 60])
            a, b = s, s + dur
            # trim to avoid own meetings, windows, day end
            while b > a + 15 and (b > END or overlaps(a, b, busy(p, d)) or overlaps(a, b, wins(d))):
                b -= 15
            add(p, d, a, b)
    for p in people:
        for d in DAYS:
            cal[p][d].sort(key=lambda m: m["start"])
    return dict(level=level, seed=seed, people=people, D=D, calendar=cal,
                designed_answer=(DAYS[ans_day], hhmm(ans_start)))


def solve(task):
    D, cal, people = task["D"], task["calendar"], task["people"]
    def free(d, s, e):
        return not any(m["start"] < e and s < m["end"] for p in people for m in cal[p][d])
    ans = None
    for di, d in enumerate(DAYS):
        for s in range(START, END - D + 1, 15):
            if free(d, s, s + D):
                ans = (d, hhmm(s)); break
        if ans:
            break
    # maximal common-free intervals per day
    gaps = []
    for d in DAYS:
        cur = None
        for s in range(START, END, 15):
            if free(d, s, s + 15):
                cur = [s, s + 15] if cur is None else [cur[0], s + 15]
            else:
                if cur: gaps.append((d, *cur)); cur = None
        if cur: gaps.append((d, *cur))
    a_key = (DAYS.index(ans[0]), int(ans[1][:2]) * 60 + int(ans[1][3:]))
    near = [(d, hhmm(a), hhmm(b)) for d, a, b in gaps
            if b - a == D - 15 and (DAYS.index(d), b) <= a_key]
    return ans, near, [(d, hhmm(a), hhmm(b)) for d, a, b in gaps]


def wrap(text, maxc):
    words, lines, cur = text.split(), [], ""
    for w in words:
        if not cur: cur = w
        elif len(cur) + 1 + len(w) <= maxc: cur += " " + w
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    return lines


def render(task, path):
    people, cal = task["people"], task["calendar"]
    n = len(people)
    W, H = 1600, 1000
    fig = plt.figure(figsize=(16, 10), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, W); ax.set_ylim(H, 0); ax.axis("off")
    fig.patch.set_facecolor("white")
    left, right, top, bottom = 62, 1588, 128, 984
    gut = 8
    dayw = (right - left) / 5
    ph = (bottom - top) / ((END - START) / 60)
    y = lambda m: top + (m - START) / 60 * ph
    ax.text(16, 22, "Team calendar  ·  Week of Nov 16 – 20", fontsize=15, weight="bold", va="center", color="#202124")
    # legend
    lx = 16
    for i, p in enumerate(people):
        ax.add_patch(Rectangle((lx, 46), 14, 14, facecolor=COLORS[i][0], edgecolor=COLORS[i][1], lw=1.5))
        ax.text(lx + 20, 53, p, fontsize=10, va="center", color="#202124")
        lx += 30 + 8.2 * len(p) + 20
    ax.text(W - 16, 53, "Shaded blocks = busy", fontsize=9, va="center", ha="right", color="#5f6368")
    for di in range(5):
        x0 = left + di * dayw + gut / 2
        w = dayw - gut
        ax.text(x0 + w / 2, 82, f"{DAY_FULL[di]} {16 + di}", fontsize=11, weight="bold", ha="center", va="center", color="#202124")
        sw = w / n
        for i, p in enumerate(people):
            ax.text(x0 + (i + 0.5) * sw, 110, p.split()[0], fontsize=8.5, ha="center", va="center", color=COLORS[i][1], weight="bold")
            if i:
                ax.plot([x0 + i * sw] * 2, [top, bottom], color="#eeeeee", lw=0.8, zorder=1)
        ax.add_patch(Rectangle((x0, top), w, bottom - top, fill=False, edgecolor="#c4c7c5", lw=1, zorder=3))
        # gridlines
        for m in range(START, END + 1, 30):
            hour = m % 60 == 0
            ax.plot([x0, x0 + w], [y(m)] * 2, color="#c4c7c5" if hour else "#e6e6e6",
                    lw=1.0 if hour else 0.7, ls="-" if hour else (0, (3, 3)), zorder=1)
        for i, p in enumerate(people):
            for mt in cal[p][DAYS[di]]:
                bx, by = x0 + i * sw + 2, y(mt["start"])
                bw, bh = sw - 4, y(mt["end"]) - y(mt["start"])
                ax.add_patch(Rectangle((bx, by), bw, bh, facecolor=COLORS[i][0], edgecolor="white", lw=1.2, zorder=4))
                ax.add_patch(Rectangle((bx, by + 0.6), 3, bh - 1.2, facecolor=COLORS[i][1], lw=0, zorder=5))
                maxc = max(3, int((bw - 7) / 5.9))
                maxl = max(1, int((bh - 2) / 12))
                lines = wrap(mt["title"], maxc)
                if len(lines) > maxl:  # put the remainder on the last line; clipping truncates it
                    lines = lines[:maxl - 1] + [" ".join(lines[maxl - 1:])]
                lines = [l if len(l) <= maxc else l[:maxc - 1].rstrip() + "\u2026" for l in lines]
                clip = Rectangle((bx, by), bw, bh, transform=ax.transData)
                t = ax.text(bx + 5, by + 1.5, "\n".join(lines), fontsize=8, va="top", ha="left",
                            color="#202124", linespacing=1.0, zorder=6)
                t.set_clip_on(True); t.set_clip_path(clip)
    for m in range(START, END + 1, 60):
        ax.text(left - 8, y(m), f"{m // 60}:00", fontsize=9, ha="right", va="center", color="#5f6368")
    fig.savefig(path, dpi=100, facecolor="white")
    plt.close(fig)


def question(task):
    names = task["people"]
    nm = ", ".join(names[:-1]) + " and " + names[-1]
    return (f"This image shows the calendars of {nm} for one work week (Mon to Fri, 8:00 to 18:00). "
            f"What is the earliest time when all of them are free for {task['D']} consecutive minutes? "
            "Think step by step, then end your reply with a final line exactly in the form "
            "`FINAL ANSWER: <Day> <HH:MM>` (for example `FINAL ANSWER: Tue 13:30`).")


if __name__ == "__main__":
    tasks = []
    for level in ["L1", "L2", "L3"]:
        for seed in [1, 2, 3]:
            t = build(level, seed)
            ans, near, gaps = solve(t)
            cfg = LEVELS[level]
            assert ans is not None
            assert ans == tuple(t["designed_answer"]), (level, seed, ans, t["designed_answer"])
            assert DAYS.index(ans[0]) in cfg["ans_days"]
            assert len(near) >= cfg["near"], (level, seed, near)
            tid = f"{level}_s{seed}"
            img = os.path.join(OUT, "images", f"{tid}.png")
            render(t, img)
            t.update(id=tid, image=img, answer=f"{ans[0]} {ans[1]}", near_misses=near,
                     common_gaps=gaps, question=question(t))
            tasks.append(t)
            print(tid, t["answer"], "near:", near)
    json.dump(tasks, open(os.path.join(OUT, "tasks.json"), "w"), indent=1)
