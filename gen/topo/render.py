"""Draw the map from the data dict only (USGS 7.5-minute quadrangle look) and report where every label landed."""
from __future__ import annotations

import math

import numpy as np

from factory.render import new_figure, save_png, text_boxes, to_pixels
from matplotlib.patches import Polygon, Rectangle

from .terrain import BOX_H, BOX_W, CI, H, INDEX, W, grid

MAGENTA, BROWN, BROWN_INDEX, BLUE, GREEN, PAPER = "#c2188f", "#b9793f", "#9a5a22", "#2b7bbb", "#e9f2dc", "#fffbe6"
WIDTH_PX, HEIGHT_PX = 1560, 1290
S = 1.5                     # the factory renders at 100 dpi; sizes below are in points for a 150 dpi look


def _flip(a):
    return a - 180 if a > 90 else a + 180 if a < -90 else a


def render(d, path):
    """Write the PNG from the data dict only. Returns the layout (contracts/FAMILY.md): every label's box in
    image pixels and the pixels the validator samples (each marker, the incident box)."""
    X, Y, Z = grid(d)
    fig = new_figure(WIDTH_PX, HEIGHT_PX)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0.07, 0.13, 0.86, 0.78])
    ax.set_facecolor(GREEN)

    def put(kind, artist):
        return artist

    lo, hi = math.ceil(Z.min() / CI) * CI, math.floor(Z.max() / CI) * CI
    levels = np.arange(lo, hi + 1, CI)
    ax.contour(X, Y, Z, levels=[l for l in levels if l % INDEX], colors=BROWN, linewidths=0.825)
    ax.contour(X, Y, Z, levels=[l for l in levels if l % INDEX == 0], colors=BROWN_INDEX, linewidths=1.95)
    for g in range(1000, int(W), 1000):
        ax.plot([g, g], [0, H], color="#444444", lw=0.45, alpha=0.6, zorder=1)
    for g in range(1000, int(H), 1000):
        ax.plot([0, W], [g, g], color="#444444", lw=0.45, alpha=0.6, zorder=1)
    for s in d["streams"]:
        p = np.array(s["pts"])
        ax.plot(p[:, 0], p[:, 1], color=BLUE, lw=1.65, zorder=3)
        k = len(p) // 2
        t = p[min(k + 3, len(p) - 1)] - p[max(k - 3, 0)]
        nrm = np.array([-t[1], t[0]]) / max(np.linalg.norm(t), 1e-9)
        put("stream", ax.text(*(p[k] + 65 * nrm), s["name"], color=BLUE, fontsize=9.75, style="italic",
                              rotation=_flip(math.degrees(math.atan2(t[1], t[0]))), ha="center", va="center", zorder=6))
    for t in d["trails"]:
        p = np.array(t["pts"])
        ax.plot(p[:, 0], p[:, 1], color="black", lw=1.725, dashes=(5, 2.2), zorder=4)
        mid, leg = (p[0] + p[1]) / 2, p[1] - p[0]
        nrm = np.array([-leg[1], leg[0]]) / max(np.linalg.norm(leg), 1e-9)
        put("trail", ax.text(*(mid + 70 * nrm), t["name"], fontsize=9.75, rotation=_flip(math.degrees(math.atan2(leg[1], leg[0]))),
                             ha="center", va="center", zorder=6, bbox=dict(fc=GREEN, ec="none", pad=0.6, alpha=0.85)))
    for lb in d["index_labels"]:
        put("index", ax.text(lb["x"], lb["y"], str(lb["level"]), color=BROWN_INDEX, fontsize=9.75, rotation=lb["angle"],
                             ha="center", va="center", zorder=5, bbox=dict(fc=GREEN, ec="none", pad=0.75)))
    for s in d["spot_heights"]:
        ax.plot(s["x"], s["y"], marker="x", color="black", ms=6, mew=1.35, zorder=6)
        put("spot", ax.text(s["x"] + 45, s["y"] - 25, str(s["elev"]), fontsize=9.75, va="top", zorder=6))
        put("spot", ax.text(s["x"] + 45, s["y"] + 30, s["name"], fontsize=10.5, style="italic", va="bottom", zorder=6))
    for p in d["points"]:
        ax.plot(p["x"], p["y"], marker="s" if p["shape"] == "square" else "o", color=MAGENTA, ms=9.75, mec="white",
                mew=1.2, zorder=8)
        put("point", ax.text(p["x"] + p.get("label_dx", 70), p["y"] + p.get("label_dy", 70), p["name"], color=MAGENTA,
                             fontsize=18, weight="bold", ha="center", va="center", zorder=8,
                             bbox=dict(fc="white", ec=MAGENTA, lw=0.9, pad=1.5, alpha=0.9)))
    x0, y0 = d["box"]["xy"]
    ax.add_patch(Rectangle((x0, y0), BOX_W, BOX_H, fc=PAPER, ec="#8a1c1c", lw=2.1, zorder=9))
    put("box", ax.text(x0 + 45, y0 + BOX_H - 55, d["box"]["title"], fontsize=12, weight="bold", color="#8a1c1c",
                       va="top", zorder=10))
    put("box", ax.text(x0 + 45, y0 + BOX_H - 175, d["box"]["body"], fontsize=10.2, va="top", zorder=10, linespacing=1.35))

    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.set_aspect("equal")
    ax.set_xticks(range(0, int(W) + 1, 1000), [f"{571 + i}" for i in range(int(W // 1000) + 1)], fontsize=10.5)
    ax.set_yticks(range(0, int(H) + 1, 1000), [f"41{62 + i}" for i in range(int(H // 1000) + 1)], fontsize=10.5)
    ax.tick_params(length=6, width=1.2, top=True, right=True, labeltop=True, labelright=True, direction="in")
    ax.tick_params(axis="x", pad=9)                 # keeps the corner grid numbers from touching each other
    for sp in ax.spines.values():
        sp.set_linewidth(1.95)
    put("frame", fig.text(0.07, 0.965, "TOPOGRAPHIC MAP SERIES", fontsize=13.5, weight="bold", va="top"))
    put("frame", fig.text(0.07, 0.945, "1000-meter grid ticks, zone 11 · elevations in meters", fontsize=10.5, va="top"))
    put("frame", fig.text(0.93, 0.965, f"{d['quad'].upper()} QUADRANGLE", fontsize=16.5, weight="bold", ha="right", va="top"))
    put("frame", fig.text(0.93, 0.942, "7.5-MINUTE SERIES (TOPOGRAPHIC)", fontsize=11.25, ha="right", va="top"))
    sax = fig.add_axes([0.285, 0.062, 0.43, 0.012])                    # 2000 m at the map's own scale
    for a, b, c in ((0, 500, "black"), (500, 1000, "white"), (1000, 2000, "black")):
        sax.add_patch(Rectangle((a, 0), b - a, 1, fc=c, ec="black", lw=1.2))
    sax.set_xlim(0, 2000)
    sax.set_ylim(0, 1)
    sax.set_yticks([])
    sax.set_xticks([0, 500, 1000, 2000], ["0", "500", "1000", "2000 METERS"], fontsize=10.5)
    sax.tick_params(length=0, pad=3)
    for sp in sax.spines.values():
        sp.set_visible(False)
    put("frame", fig.text(0.5, 0.093, "SCALE 1:24 000", fontsize=12.75, weight="bold", ha="center"))
    put("frame", fig.text(0.5, 0.022, "CONTOUR INTERVAL 20 METERS", fontsize=12.75, weight="bold", ha="center"))
    fig.add_artist(Polygon([[0.105, 0.035], [0.115, 0.095], [0.125, 0.035], [0.115, 0.05]], closed=True,
                                   fc="black", transform=fig.transFigure))
    put("frame", fig.text(0.115, 0.1, "N", fontsize=15, weight="bold", ha="center"))
    put("frame", fig.text(0.93, 0.06, "Woodland tint: green\nTrail: dashed black  ·  Stream: blue\nIndex contour: heavy brown",
                          fontsize=9.75, ha="right", va="center"))

    texts = text_boxes(fig)
    probes = [{"xy": [round(v, 1) for v in to_pixels(ax, p["x"], p["y"])], "expect": MAGENTA, "tol": 40, "r": 1,
               "what": f"marker {p['name']}"} for p in d["points"]]
    probes.append({"xy": [round(v, 1) for v in to_pixels(ax, x0 + BOX_W - 40, y0 + 40)], "expect": PAPER, "tol": 40,
                   "what": "incident box"})
    save_png(fig, path)
    return {"texts": texts, "probes": probes}


def label_clash(layout):
    """Why this drawing is not fair to read, or None. The same rule as validate's legibility check (no two labels
    overlap by more than 2 px), plus: no label covers a marker."""
    t = layout["texts"]
    for i in range(len(t)):
        for j in range(i + 1, len(t)):
            ow = min(t[i][2], t[j][2]) - max(t[i][0], t[j][0])
            oh = min(t[i][3], t[j][3]) - max(t[i][1], t[j][1])
            if ow > 2 and oh > 2:
                return "two labels overlap"
    for pr in layout["probes"][:-1]:
        x, y = pr["xy"]
        if any(b[0] - 5 <= x <= b[2] + 5 and b[1] - 5 <= y <= b[3] + 5 for b in t):
            return f"a label covers {pr['what']}"
    return None
