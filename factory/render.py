"""Determinism helpers every family can import (contracts/FAMILY.md, docs/ARCHITECTURE.md E4).

    from factory.render import new_figure, save_png, text_boxes, to_pixels

Same (seed, template, difficulty) must give byte-identical PNGs on a laptop and in Docker. That holds when:
  * the backend is Agg (set here, on import),
  * the figure size and dpi are fixed and savefig uses the same dpi (no bbox_inches="tight", which can
    shift by a pixel between machines and breaks the layout coordinates),
  * no metadata that changes per run: matplotlib's "Software" tag is removed and PIL writes no tIME chunk,
  * fonts come from matplotlib's bundled DejaVu family (the default), not system fonts.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

os.environ.setdefault("MPLBACKEND", "Agg")
import matplotlib  # noqa: E402

matplotlib.use("Agg", force=True)
from matplotlib.figure import Figure  # noqa: E402

DPI = 100                                     # fixed; 1 inch = 100 image pixels
PNG_METADATA = {"Software": None}             # matplotlib otherwise writes its version string
PNG_PIL_KWARGS = {"compress_level": 6}        # explicit, and no pnginfo / tIME chunk: no timestamps


def new_figure(width_px: int, height_px: int, dpi: int = DPI) -> Figure:
    """A Figure of exactly width_px x height_px pixels on the Agg canvas (no pyplot, no global state)."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    fig = Figure(figsize=(width_px / dpi, height_px / dpi), dpi=dpi)
    FigureCanvasAgg(fig)
    return fig


def save_png(fig, path, dpi: int = DPI) -> str:
    """Write `fig` as a deterministic PNG and return its SHA-256 (hex).

    The figure's own dpi is set to `dpi` first, so pixel coordinates measured before saving (text_boxes,
    to_pixels) match the saved image."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if fig.canvas is None or type(fig.canvas).__name__ != "FigureCanvasAgg":
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        FigureCanvasAgg(fig)
    fig.set_dpi(dpi)
    fig.savefig(path, format="png", dpi=dpi, metadata=dict(PNG_METADATA), pil_kwargs=dict(PNG_PIL_KWARGS))
    return sha256_file(path)


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def image_height(fig) -> int:
    return int(round(fig.get_figheight() * fig.dpi))


def to_pixels(ax, x: float, y: float) -> list[float]:
    """Data coordinates on `ax` -> image pixels [col, row], origin top-left (what layout.probes expects)."""
    fig = ax.figure
    dx, dy = ax.transData.transform((x, y))
    return [float(dx), float(image_height(fig) - dy)]


def text_boxes(fig, min_chars: int = 1) -> list[list[float]]:
    """Every visible, non-empty Text artist in `fig` as [x0, y0, x1, y1, fontsize_px] in image pixels,
    origin top-left. Draws the figure once (on the Agg canvas) so extents are final. Use it for
    layout["texts"]; call it after all drawing and before or after save_png (same dpi)."""
    from matplotlib.text import Text
    drawn = []                                # only texts that are really drawn (not hidden or off-view ticks)
    original = Text.draw

    def recording_draw(self, renderer):
        drawn.append(self)
        return original(self, renderer)

    Text.draw = recording_draw
    try:
        fig.canvas.draw()
    finally:
        Text.draw = original
    renderer = fig.canvas.get_renderer()
    h = image_height(fig)
    out = []
    for t in dict.fromkeys(drawn):
        if not t.get_visible() or len(t.get_text().strip()) < min_chars:
            continue
        bb = t.get_window_extent(renderer)
        if bb.width <= 0 or bb.height <= 0:
            continue
        size_px = t.get_fontsize() * fig.dpi / 72.0
        out.append([round(bb.x0, 1), round(h - bb.y1, 1), round(bb.x1, 1), round(h - bb.y0, 1), round(size_px, 2)])
    return out
