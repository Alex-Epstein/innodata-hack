"""Spike D (#15): ECG rhythm strips. Data first, image rendered from it, answers computed from it.

    uv run python results/spikes/ecg/gen.py      # writes tasks/data, tasks/images, tasks/tasks.jsonl

Look copied from: a lead II rhythm strip on standard ECG paper (1 mm small boxes = 0.04 s and 0.1 mV,
5 mm large boxes = 0.20 s and 0.5 mV, 25 mm/s, 10 mm/mV, 1 mV calibration pulse at the left).

Levels (one question type each, 3 seeds each):
  L1 ecg.rate_regular   regular rhythm            -> heart rate in bpm (1500 / small boxes), accepted within +/-3 bpm
  L2 ecg.rr_marked_ms   sinus rhythm + one early  -> R-R interval between the two marked beats, in ms (exact)
                        beat, two beats marked
  L3 ecg.longest_pause  irregular rhythm, 10 s    -> number of the beat that starts the longest R-R interval (exact)
  L4 ecg.rr_range_ms    irregular rhythm, 10 s    -> longest minus shortest R-R interval, in ms (exact). Added after
                        L1 to L3 came back 18/18: it needs two exact measurements among near-equal candidates.

Every R peak sits a whole number of small boxes from the next, so a careful reader can count exactly.
Checks per task: the answer is recomputed from R peaks detected in the PNG pixels (not from the data).
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
OUT = HERE / "tasks"
VERSION = "ecg-spike-0.1"
REFERENCES = ["Lead II rhythm strip from a standard 12-lead ECG printout (25 mm/s, 10 mm/mV)",
              "Dubin, Rapid Interpretation of EKG's: rate by small/large boxes"]

BOX = 0.04                      # seconds per small box
PX_MM = 8                       # pixels per millimetre
DPI = PX_MM * 25.4
T_END, V_LO, V_HI = 10.0, -1.0, 2.0          # strip: 250 mm wide, 30 mm tall
M_LEFT, M_RIGHT, M_TOP, M_BOTTOM = 5, 5, 12, 6   # margins in mm
W_MM, H_MM = 250 + M_LEFT + M_RIGHT, 30 + M_TOP + M_BOTTOM
SIGNAL_START = 0.40             # the trace starts after the calibration pulse
FS = 1000

PATIENTS = ["OKAFOR, MARIA", "LINDQVIST, ERIK", "NAKAMURA, HANA", "DELGADO, RAUL", "WHITFIELD, JOAN",
            "PETROV, ANTON", "MBEKI, THANDI", "ROSSI, CARLA", "HOLLOWAY, DEAN"]
INTRO = ("This is a lead II rhythm strip on standard ECG paper recorded at 25 mm/s: one small box is 0.04 s "
         "and one large box (5 small boxes) is 0.20 s. The square pulse at the far left is the 1 mV "
         "calibration mark, not a heartbeat. ")


# ------------------------------------------------------------------------------------------------ data
def sample(level: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    if level == 1:                                   # regular; off-by-one box must fall outside +/-3 bpm
        n = int(rng.integers(12, 22))
        rr = [n] * 40
    elif level == 2:                                 # sinus arrhythmia with one early beat and a pause
        n = int(rng.integers(16, 24))
        rr = [n + int(rng.integers(-2, 3)) for _ in range(40)]
        k = int(rng.integers(2, 5))
        rr[k] = n - int(rng.integers(5, 8))
        rr[k + 1] = n + int(rng.integers(3, 6))
    else:                                            # irregularly irregular, no P waves
        rr = [int(rng.integers(10, 27)) for _ in range(40)]
    first = round(0.80 + int(rng.integers(0, 8)) * BOX + int(rng.integers(0, 4)) * 0.01, 2)
    beats, t, used = [], first, []
    for step in rr:
        if t > T_END - 0.35:
            break
        beats.append(round(t, 2))
        used.append(step)
        t += step * BOX
    rr_boxes = used[:len(beats) - 1]
    data = {"level": level, "beats_s": beats, "rr_small_boxes": rr_boxes,
            "has_p_wave": level < 3,
            "r_mv": round(float(rng.uniform(1.0, 1.3)), 2), "t_mv": round(float(rng.uniform(0.22, 0.32)), 2),
            "patient": PATIENTS[seed % len(PATIENTS)], "patient_id": f"{4000 + seed * 37 % 5000}-{seed % 900 + 100}",
            "time": f"{8 + seed % 9:02d}:{seed * 7 % 60:02d}:{seed * 13 % 60:02d}", "noise_seed": seed + 10_000}
    if level == 3:                                   # make the longest interval unique by a clear margin
        j = int(rng.integers(1, len(rr_boxes) - 1))
        others = max(b for i, b in enumerate(rr_boxes) if i != j)
        grow = others + 3 - rr_boxes[j]
        rr_boxes[j] += grow
        data["beats_s"] = [b if i <= j else round(b + grow * BOX, 2) for i, b in enumerate(beats)]
        while data["beats_s"][-1] > T_END - 0.35:    # drop beats pushed off the paper
            data["beats_s"].pop()
            rr_boxes.pop()
        data["rr_small_boxes"] = rr_boxes
    if level == 2:
        m = int(rng.integers(1, len(rr_boxes) - 1))
        data["marked"] = [m, m + 1]                  # 0-based indices of beats A and B
    return data


def waveform(data: dict):
    """The plotted signal, a pure function of the data: sum of Gaussians per beat + small wander and noise."""
    t = np.arange(SIGNAL_START, T_END, 1 / FS)
    v = np.zeros_like(t)
    beats = data["beats_s"]
    for i, b in enumerate(beats):
        nxt = (beats[i + 1] - b) if i + 1 < len(beats) else 0.8
        t_center = min(0.26, 0.45 * nxt)             # the T wave moves in when the next beat is early
        parts = [(-0.08, -0.025, 0.008), (data["r_mv"], 0.0, 0.009), (-0.20, 0.028, 0.010),
                 (data["t_mv"], t_center, 0.045)]
        if data["has_p_wave"]:
            parts.append((0.14, -0.16, 0.022))
        for amp, center, sigma in parts:
            v += amp * np.exp(-0.5 * ((t - b - center) / sigma) ** 2)
    rng = np.random.default_rng(data["noise_seed"])
    v += 0.025 * np.sin(2 * np.pi * 0.27 * t + rng.uniform(0, 6.28))          # baseline wander
    if not data["has_p_wave"]:                                                # fibrillatory baseline
        v += 0.03 * np.sin(2 * np.pi * 6.1 * t + rng.uniform(0, 6.28)) + 0.02 * np.sin(2 * np.pi * 8.3 * t)
    v += rng.normal(0, 0.006, len(t))
    return t, v


# ------------------------------------------------------------------------------------------------ question + answer
def ask_and_solve(data: dict):
    rr = data["rr_small_boxes"]
    if data["level"] == 1:
        bpm = round(1500 / rr[0], 1)
        q = INTRO + ("The rhythm is regular. What is the heart rate in beats per minute? An answer within 3 bpm "
                     "of the true value is accepted. Give one number, for example 64.")
        return q, "ecg.rate_regular", bpm, "number", {"tolerance_abs": 3}
    if data["level"] == 2:
        a, _ = data["marked"]
        q = INTRO + ("Two consecutive beats are marked A and B above their R waves. What is the R-R interval "
                     "from A to B in milliseconds? R peaks are a whole number of small boxes apart, so give a "
                     "multiple of 40, for example 760.")
        return q, "ecg.rr_marked_ms", rr[a] * 40, "integer", {}
    if data["level"] == 4:
        q = INTRO + ("The rhythm is irregular. What is the difference between the longest and the shortest R-R "
                     "interval on this strip, in milliseconds? R peaks are a whole number of small boxes apart, "
                     "so give a multiple of 40, for example 360.")
        return q, "ecg.rr_range_ms", (max(rr) - min(rr)) * 40, "integer", {}
    longest = max(range(len(rr)), key=lambda i: rr[i])
    q = INTRO + ("The rhythm is irregular. Number the heartbeats (QRS complexes) from left to right, starting "
                 "at 1. The longest R-R interval lies between which two consecutive beats? Answer with the "
                 "number of the earlier of the two beats, for example 4.")
    return q, "ecg.longest_pause", longest + 1, "integer", {}


# ------------------------------------------------------------------------------------------------ render
def render(data: dict, path: Path) -> None:
    fig = plt.figure(figsize=(W_MM / 25.4, H_MM / 25.4), dpi=DPI, facecolor="white")
    ax = fig.add_axes([M_LEFT / W_MM, M_BOTTOM / H_MM, 250 / W_MM, 30 / H_MM])
    ax.set_xlim(0, T_END)
    ax.set_ylim(V_LO, V_HI)
    ax.set_facecolor("#fff6f4")
    for k in range(251):                                                      # vertical grid lines, every 1 mm
        big = k % 5 == 0
        ax.axvline(k * BOX, color="#e2726e" if big else "#f3b9b4", lw=0.75 if big else 0.35, zorder=1)
    for k in range(31):                                                       # horizontal grid lines
        big = k % 5 == 0
        ax.axhline(V_LO + k * 0.1, color="#e2726e" if big else "#f3b9b4", lw=0.75 if big else 0.35, zorder=1)
    ax.plot([0.04, 0.08, 0.08, 0.28, 0.28, 0.32], [0, 0, 1, 1, 0, 0], color="black", lw=1.0, zorder=3)  # 1 mV cal
    t, v = waveform(data)
    ax.plot(t, v, color="black", lw=1.0, zorder=3, solid_joinstyle="round")
    if "marked" in data:
        for idx, name in zip(data["marked"], "AB"):
            x = data["beats_s"][idx]
            ax.plot([x], [1.66], marker="v", color="#1a3f8f", ms=4.5, zorder=4)
            ax.text(x, 1.74, name, ha="center", va="bottom", fontsize=7.5, color="#1a3f8f", weight="bold", zorder=4)
    for s in (3, 6, 9):                                                       # 3-second marks on the bottom edge
        ax.plot([s, s], [V_LO, V_LO + 0.12], color="black", lw=1.0, zorder=3)
    ax.set_xticks([])
    ax.set_yticks([])
    for sp in ax.spines.values():
        sp.set_color("#e2726e")
        sp.set_linewidth(0.75)
    top = 1 - 3.2 / H_MM
    fig.text(M_LEFT / W_MM, top, f"{data['patient']}    ID {data['patient_id']}    14-NOV-2026  {data['time']}",
             fontsize=7.5, family="DejaVu Sans Mono", va="center")
    fig.text(1 - M_RIGHT / W_MM, top, "RHYTHM STRIP    II    25 mm/s    10 mm/mV    0.5-40 Hz    60 Hz filter ON",
             fontsize=7.5, family="DejaVu Sans Mono", va="center", ha="right")
    fig.text(M_LEFT / W_MM, 1 - 8.6 / H_MM, "II", fontsize=8, weight="bold", va="center")
    fig.text(M_LEFT / W_MM, 2.6 / H_MM, "Unconfirmed tracing. Not for diagnostic use.", fontsize=6,
             family="DejaVu Sans Mono", va="center", color="#444444")
    fig.savefig(path, dpi=DPI, metadata={"Software": None})
    plt.close(fig)


# ------------------------------------------------------------------------------------------------ pixel check
def r_peaks_from_pixels(path: Path) -> list[float]:
    """R-peak times read from the PNG alone: columns where the dark trace rises above 0.6 mV."""
    px = np.asarray(Image.open(path).convert("RGB")).astype(int)
    top = M_TOP * PX_MM                                         # pixel row of V_HI
    y_of = lambda mv: int(round(top + (V_HI - mv) * 10 * PX_MM))
    rows = px[y_of(1.55):y_of(0.6), :, :]                       # below the A/B markers, above 0.6 mV
    dark = (rows.max(axis=2) < 90)
    cols = np.where(dark.any(axis=0))[0]
    x0 = M_LEFT * PX_MM
    cols = cols[cols > x0 + SIGNAL_START * 25 * PX_MM]          # skip the calibration pulse
    peaks, group = [], []
    for c in cols:
        if group and c - group[-1] > 3:
            peaks.append(group)
            group = []
        group.append(c)
    if group:
        peaks.append(group)
    out = []
    for g in peaks:
        heights = [dark[:, c].argmax() for c in g]             # topmost dark pixel in each column
        best = [c for c, h in zip(g, heights) if h == min(heights)]
        out.append((np.mean(best) - x0) / (25 * PX_MM))
    return out


def answer_from_pixels(data: dict, path: Path):
    times = r_peaks_from_pixels(path)
    boxes = [int(round((b - a) / BOX)) for a, b in zip(times, times[1:])]
    if data["level"] == 1:
        return round(1500 / boxes[0], 1), boxes
    if data["level"] == 2:
        return boxes[data["marked"][0]] * 40, boxes
    if data["level"] == 4:
        return (max(boxes) - min(boxes)) * 40, boxes
    return max(range(len(boxes)), key=lambda i: boxes[i]) + 1, boxes


# ------------------------------------------------------------------------------------------------ main
def main():
    (OUT / "data").mkdir(parents=True, exist_ok=True)
    (OUT / "images").mkdir(exist_ok=True)
    lines = []
    for level in (1, 2, 3, 4):
        for s in (1, 2, 3):
            seed = level * 100 + s
            tid = f"ecg-{seed:06d}"
            data = sample(level, seed)
            question, qtype, answer, atype, extra = ask_and_solve(data)
            record = {"task_id": tid, "family": "ecg", "seed": seed, "generator_version": VERSION,
                      "params": {"level": level}, "data": data, "references": REFERENCES}
            (OUT / "data" / f"{tid}.json").write_text(json.dumps(record, indent=1))
            img = OUT / "images" / f"{tid}.png"
            render(data, img)
            pix_answer, pix_boxes = answer_from_pixels(data, img)
            rr = data["rr_small_boxes"]
            checks = {
                "pixel_rr_matches_data": pix_boxes == rr,
                "pixel_answer_matches": pix_answer == answer,
                "unique_answer": True if level != 3 else sorted(rr)[-1] - sorted(rr)[-2] >= 3,
                "no_beat_at_paper_edge": data["beats_s"][0] >= 0.8 and data["beats_s"][-1] <= T_END - 0.35,
                "off_by_one_box_is_wrong": True if level != 1 else
                    min(abs(1500 / (rr[0] + d) - answer) for d in (-1, 1)) > 3,
            }
            lines.append({"task_id": tid, "image": f"images/{tid}.png", "question": question, "answer": answer,
                          "answer_type": atype, **extra, "seed": seed, "generator_version": VERSION,
                          "question_type": qtype, "family": "ecg", "difficulty": level,
                          "data": f"data/{tid}.json", "checks": checks, "references": REFERENCES})
            print(tid, qtype, "answer", answer, "beats", len(data["beats_s"]), "rr", rr,
                  "OK" if all(checks.values()) else f"CHECK FAILED {checks}")
    (OUT / "tasks.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    assert all(all(x["checks"].values()) for x in lines), "a task failed its checks"


if __name__ == "__main__":
    main()
