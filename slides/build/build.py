"""Fill the organizers' template: uv run --with python-pptx --with segno --with pillow python slides/build/build.py"""
import copy
from pathlib import Path
from PIL import Image
import segno
from pptx import Presentation
from pptx.util import Emu, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "slides" / "TheMapVsTheMountain.pptx"
ASSETS = ROOT / "slides" / "build" / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)
M = 1_000_000  # EMU helper: positions below are in millions of EMU

TRUTH, AI, HUMAN = "2F7FC1", "D2412C", "D9A441"
INK, PAPER, LABEL, GREY, BODY = "1E1B16", "F3EEDF", "0070C0", "898989", "474747"
LEAGUE, COND, MONO, SERIF = "League Spartan", "IBM Plex Sans Condensed", "IBM Plex Mono", "Source Serif 4"


def E(x):
    return Emu(int(x * M))


def style_run(r, text, font=LEAGUE, size=15, bold=False, italic=False, color=BODY, spc=None):
    r.text = text
    f = r.font
    f.name, f.size, f.bold, f.italic = font, Pt(size), bold, italic
    f.color.rgb = RGBColor.from_string(color)
    if spc is not None:
        r._r.get_or_add_rPr().set("spc", str(spc))


def fill(tf, paras, anchor=MSO_ANCHOR.TOP, margins=(0.09, 0.07)):
    """paras: list of (runs, opts); runs: list of (text, style-dict)."""
    tf.clear()
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    tf.margin_left = tf.margin_right = E(margins[0])
    tf.margin_top = tf.margin_bottom = E(margins[1])
    for i, (runs, opts) in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        if "before" in opts:
            p.space_before = Pt(opts["before"])
        if "align" in opts:
            p.alignment = opts["align"]
        p.line_spacing = opts.get("spacing", 1.05)
        for text, st in runs:
            style_run(p.add_run(), text, **st)


def label(text, color=LABEL, size=11):
    return (text.upper(), dict(font=COND, size=size, bold=True, color=color, spc=150))


def body(text, size=15, color=BODY, **kw):
    return (text, dict(font=LEAGUE, size=size, color=color, **kw))


def mono(text, size=15, color=INK, bold=False):
    return (text, dict(font=MONO, size=size, color=color, bold=bold))


def serif(text, size=18, color=INK):
    return (text, dict(font=SERIF, size=size, italic=True, color=color))


def shape(slide, name):
    return next(s for s in slide.shapes if s.name == name)


def place(sh, x=None, y=None, w=None, h=None):
    if x is not None: sh.left = E(x)
    if y is not None: sh.top = E(y)
    if w is not None: sh.width = E(w)
    if h is not None: sh.height = E(h)


def textbox(slide, x, y, w, h, paras, **kw):
    tb = slide.shapes.add_textbox(E(x), E(y), E(w), E(h))
    fill(tb.text_frame, paras, **kw)
    return tb


def rect(slide, x, y, w, h, color, line=None):
    r = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, E(x), E(y), E(w), E(h))
    r.fill.solid(); r.fill.fore_color.rgb = RGBColor.from_string(color)
    if line:
        r.line.color.rgb = RGBColor.from_string(line); r.line.width = Pt(0.75)
    else:
        r.line.fill.background()
    r.shadow.inherit = False
    return r


# ---------- assets ----------
MAP_BOX = (104, 126, 1353, 1063)  # the map frame inside the 1600x1200 task image (4:3)


def crop(src, box, dst, size=None):
    im = Image.open(src).convert("RGB").crop(box)
    if size:
        im.thumbnail(size, Image.LANCZOS)
    im.save(dst)
    return dst


hero = crop(ROOT / "tasks/final/images/topo-flood-000102.png", MAP_BOX, ASSETS / "hero_flood_000102.png")
truth = crop(ROOT / "tasks/final/overlays/topo-flood-000102_truth.png", MAP_BOX, ASSETS / "truth_flood_000102.png")
qr_path = ASSETS / "qr_site.png"
segno.make("https://alex-epstein.github.io/innodata-hack/", error="m").save(
    qr_path, scale=20, border=2, dark="#" + INK, light="#FFFFFF")

SP = ROOT / "results/spikes"
FAMILIES = [  # (name, thumbnail, score, colour of score); scores from docs/EVIDENCE.md + results/spikes/README.md
    ("Circuit", SP / "circuit/img/L3_s0.png", "18/18", INK),
    ("ECG", SP / "ecg/tasks/images/ecg-000302.png", "12/12", INK),
    ("Gantt", SP / "gantt/tasks/images/gantt-000201.png", "9/9 · 8/9", INK),
    ("Calendar", SP / "calendar_v2/tasks/images/cal2-tz-000001.png", "9/9 · 8/9", INK),
    ("Power (clean)", SP / "power/tasks/images/power-000302.png", "9/9 · 9/9", INK),
    ("Subway", SP / "subway_v2/tasks/images/sub2-worst-000032.png", "mostly solved", INK),
    ("Topo", SP / "topo/tasks/images/topo-000303.png", "0/3 · 0/3", AI),
]


def thumb(src, dst, aspect=5 / 3):
    im = Image.open(src).convert("RGB")
    w, h = im.size
    cw, ch = (w, int(w / aspect)) if w / h < aspect else (int(h * aspect), h)
    cw, ch = int(cw * 0.7), int(ch * 0.7)  # zoom in a little so the content reads
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    im = im.crop((x0, y0, x0 + cw, y0 + ch))
    im.thumbnail((500, 300), Image.LANCZOS)
    im.save(dst)
    return dst


prs = Presentation(ROOT / "docs/organizer/presentation-template.pptx")
s1, s2, s3, s4, s5 = prs.slides

# ---------- slide 1: intro ----------
TW = 6.40  # left text column width on slide 1
place(shape(s1, "title"), y=1.90, w=TW, h=1.20)
fill(shape(s1, "title").text_frame, [
    ([("The Map vs the Mountain", dict(font=LEAGUE, size=36, bold=True, color="FFFFFF"))], {}),
    ([("a terrain-reasoning task factory", dict(font=LEAGUE, size=24, color="FFFFFF"))], {"before": 4}),
], margins=(0, 0.03))
place(shape(s1, "team"), y=3.20, w=TW, h=0.36)
fill(shape(s1, "team").text_frame, [([
    ("Lost the Plot", dict(font=LEAGUE, size=16, color="FFFFFF")),
    ("  ·  Visual Task Factory", dict(font=LEAGUE, size=16, color="FFFFFF"))], {})], margins=(0, 0.02))
place(shape(s1, "members"), y=3.58, w=TW, h=0.40)
fill(shape(s1, "members").text_frame, [([
    ("Alex Epstein · Shivam Raj (tech-cosmos) · dl3832 · WindHurtLZ", dict(font=LEAGUE, size=13, color="B5B5B5"))], {})],
    margins=(0, 0.02))
place(shape(s1, "divider"), y=4.12, w=TW)
place(shape(s1, "pitch"), y=4.28, w=TW, h=1.00)
fill(shape(s1, "pitch").text_frame, [([
    ("Our pipeline generates topographic-map missions on real USGS terrain to test whether a model can ",
     dict(font=LEAGUE, size=17, color="FFFFFF")),
    ("trace a path through clutter.", dict(font=LEAGUE, size=17, bold=True, color="FFFFFF"))], {})], margins=(0, 0.02))
place(shape(s1, "example"), y=5.40, w=TW, h=0.70)
fill(shape(s1, "example").text_frame, [([
    ("Where it matters: a hiker's AI assistant asked “will I make it before dark?”",
     dict(font=SERIF, size=17, italic=True, color="D8D2C2"))], {})], margins=(0, 0.02))
pic = s1.shapes.add_picture(str(hero), E(7.38), E(1.70), width=E(4.10))
pic.name = "hero-map"
textbox(s1, 7.38, 1.70 + pic.height / M + 0.06, 4.10, 0.30, [([
    ("HARRIMAN STATE PARK, NY · USGS 3DEP", dict(font=COND, size=10, bold=True, color=GREY, spc=100))],
    {})], margins=(0, 0))

# ---------- slide 2: how we generate a task ----------
CW = 6.75  # card width (left column)
cards = [("card1", "card1-text", 1.72, 1.00), ("card2", "card2-text", 2.86, 1.00), ("card3", "card3-text", 4.00, 2.20)]
for card, txt, y, h in cards:
    place(shape(s2, card), y=y, w=CW, h=h)
    place(shape(s2, txt), x=0.86, y=y, w=CW - 0.30, h=h)
fill(shape(s2, "card1-text").text_frame, [
    ([label("Starting input")], {}),
    ([body("Real USGS 3DEP elevation (Bear Mountain, Breakneck Ridge, Harriman, Mt Tamalpais) + a seed", 14)], {"before": 3}),
], anchor=MSO_ANCHOR.MIDDLE)
fill(shape(s2, "card2-text").text_frame, [
    ([label("What our code does")], {}),
    ([body("Crop the terrain → place trail / dam / campsites → save the data → draw the USGS-style map → "
           "compute the answer from the data → ", 14), mono("7 checks", 14, INK, bold=True)], {"before": 3}),
], anchor=MSO_ANCHOR.MIDDLE)
missions = [("Crossings", "count every contour line the trail crosses"),
            ("Sunset", "count only uphill crossings, add 4 min each, compare to daylight"),
            ("Flood", "follow steepest descent from the dam to one of 6 camps")]
fill(shape(s2, "card3-text").text_frame, [([label("What changes between tasks: three missions")], {})] + [
    ([label(name, color=INK, size=14), body("   " + what, 14)], {"before": 9}) for name, what in missions
], anchor=MSO_ANCHOR.MIDDLE)

RX, RW = 7.74, 11.48 - 7.74
textbox(s2, RX, 1.70, RW, 0.30, [([label("How we got here")], {})], margins=(0, 0))
row_y, row_h = 2.02, 0.50
for i, (name, src, score, col) in enumerate(FAMILIES):
    y = row_y + i * (row_h + 0.03)
    t = thumb(src, ASSETS / f"thumb_{name.split()[0].lower()}.png")
    p = s2.shapes.add_picture(str(t), E(RX), E(y), width=E(0.80), height=E(row_h - 0.02))
    p.line.color.rgb = RGBColor.from_string("C8C8C8"); p.line.width = Pt(0.5)
    hi = name == "Topo"
    textbox(s2, RX + 0.90, y, 1.30, row_h, [([body(name, 14, INK, bold=hi)], {})], anchor=MSO_ANCHOR.MIDDLE, margins=(0, 0))
    textbox(s2, RX + 2.10, y, RW - 2.10, row_h, [([mono(score, 13, col, bold=hi)], {"align": PP_ALIGN.RIGHT})],
            anchor=MSO_ANCHOR.MIDDLE, margins=(0, 0))
textbox(s2, RX, 5.75, RW, 0.50, [([serif("They read labels and do math. They can't trace.", 15)], {})],
        margins=(0, 0))

# ---------- slide 3: live demo ----------
place(shape(s3, "demo-card"), y=1.80, w=7.10, h=3.05)
place(shape(s3, "demo-bar"), y=1.80, h=3.05)
place(shape(s3, "demo-text"), x=1.05, y=1.80, w=6.60, h=3.05)
fill(shape(s3, "demo-text").text_frame, [
    ([label("1 · The site", color="B5B5B5")], {}),
    ([mono("alex-epstein.github.io/innodata-hack", 17, "FFFFFF", bold=True)], {"before": 3}),
    ([body("press ", 14, "D8D2C2"), mono("S", 14, HUMAN, bold=True), body(" for the tour", 14, "D8D2C2")], {"before": 2}),
    ([label("2 · The factory", color="B5B5B5")], {"before": 16}),
    ([mono("docker run … visual-task-factory", 15, "FFFFFF")], {"before": 3}),
    ([mono("  fresh --seed ", 15, "FFFFFF"), mono("<your number>", 15, HUMAN, bold=True)], {}),
], anchor=MSO_ANCHOR.MIDDLE)
qs = 3.35
s3.shapes.add_picture(str(qr_path), E(11.48 - qs), E(1.70), width=E(qs), height=E(qs)).name = "qr-site"
textbox(s3, 11.48 - qs, 1.70 + qs + 0.04, qs, 0.30, [([
    ("SCAN FOR THE SITE", dict(font=COND, size=11, bold=True, color=GREY, spc=150))], {"align": PP_ALIGN.CENTER})],
    margins=(0, 0))
textbox(s3, 0.71, 5.10, 7.10, 0.55, [([serif("Pick any number. New task, verified, scored, in seconds.", 20)], {})],
        margins=(0, 0))

# ---------- slide 4: what the runs showed ----------
# Visual track: the template's CODING card does not apply, so its slot holds the VISUAL result and the
# template's VISUAL card holds the "why you'd buy it" box.
vc, vt = shape(s4, "card-coding"), shape(s4, "card-coding-text")
place(vc, y=1.70, h=2.95); place(vt, x=0.90, y=1.70, w=6.55, h=2.95)
fill(vt.text_frame, [
    ([label("Visual")], {}),
    ([mono("10 of 10", 15, INK, bold=True), body(" generated tasks were valid (all ", 15), mono("7", 15),
      body(" checks; none rejected). We submitted ", 15), mono("10", 15), body(" hand-checked tasks.", 15)], {"before": 4}),
    ([body("On those tasks, Claude Haiku 5.5 answered ", 15), mono("2/10", 15, AI, bold=True),
      body(" correctly and GPT-6 Luna answered ", 15), mono("3/10", 15, AI, bold=True), body(".", 15)], {"before": 6}),
    ([label("One change after the pilot", color=INK, size=10),
      body("  The trail was red over brown contours and the endpoints could sit on a line (our reviewer agent "
           "flagged it) → v2.1 drew the trail solid magenta with a white casing and kept endpoints off contours; "
           "difficulty held (pilot ", 12.5), mono("4/30", 12.5), body(" each → final ", 12.5), mono("2/10", 12.5),
      body(" and ", 12.5), mono("3/10", 12.5), body(").", 12.5)], {"before": 8}),
], anchor=MSO_ANCHOR.MIDDLE)
# score panel on the right of the VISUAL card
SX = 7.75
rect(s4, SX, 1.85, 11.30 - SX, 2.65, "FFFFFF")
for j, (who, sc) in enumerate([("Haiku 5.5", "2/10"), ("Luna", "3/10")]):
    x = SX + 0.15 + j * 1.75
    textbox(s4, x, 1.92, 1.60, 0.28, [([label(who, color=INK, size=11)], {})], margins=(0, 0))
    textbox(s4, x, 2.16, 1.60, 0.70, [([mono(sc, 40, AI, bold=True)], {})], margins=(0, 0))
rows = [("Crossings", "0/3", "1/3"), ("Sunset", "0/3", "0/3"), ("Flood", "2/4", "2/4")]
for k, (m, a, b) in enumerate(rows):
    y = 3.02 + k * 0.45
    textbox(s4, SX + 0.15, y, 1.4, 0.40, [([label(m, color=INK, size=11)], {})], anchor=MSO_ANCHOR.MIDDLE, margins=(0, 0))
    textbox(s4, SX + 1.45, y, 2.0, 0.40, [([mono(a, 15, AI), mono("  ·  ", 15, GREY), mono(b, 15, AI)], {})],
            anchor=MSO_ANCHOR.MIDDLE, margins=(0, 0))

bc, bt = shape(s4, "card-visual"), shape(s4, "card-visual-text")
place(bc, y=4.80, h=1.45); place(bt, x=0.90, y=4.80, w=3.0, h=0.40)
fill(bt.text_frame, [([label("Why you'd buy it")], {})], margins=(0, 0.12))
offers = [("Eval set", "measures the gap"), ("RL environments", "with a verifier"),
          ("SFT solutions", "step by step")]
for k, (t1, t2) in enumerate(offers):
    x = 0.90 + k * 2.13
    rect(s4, x, 5.25, 2.03, 0.85, "FFFFFF")
    textbox(s4, x, 5.25, 2.03, 0.85, [([label(t1, color=INK, size=11)], {}), ([body(t2, 14)], {"before": 2})],
            anchor=MSO_ANCHOR.MIDDLE, margins=(0.12, 0.05))
textbox(s4, 7.50, 4.95, 3.85, 1.20, [
    ([label("2 worked examples in the prompt", color=INK, size=11)], {}),
    ([mono("8/48", 22, AI, bold=True), mono(" → ", 22, GREY), mono("6/48", 22, AI, bold=True)], {"before": 2}),
    ([serif("Prompting doesn't fix it.", 16)], {"before": 2}),
], anchor=MSO_ANCHOR.MIDDLE, margins=(0, 0))

# ---------- slide 5: what we learned ----------
CW5 = 6.65
for card, txt in [("card1", "card1-text"), ("card2", "card2-text"), ("card3", "card3-text")]:
    place(shape(s5, card), w=CW5)
    place(shape(s5, txt), x=0.90, w=CW5 - 0.30)
fill(shape(s5, "card1-text").text_frame, [
    ([label("Finding")], {}),
    ([body("These models read the map but don't trace it: they lose count along the trail (Haiku undercounts by "
           "about ", 14), mono("4", 14, AI, bold=True), body(") and pick the decoy camp below the dam.", 14)], {"before": 3}),
], anchor=MSO_ANCHOR.MIDDLE)
fill(shape(s5, "card2-text").text_frame, [
    ([label("Limitation")], {}),
    ([mono("10", 14), body(" reported tasks; trails are drawn for the exercise; ", 14), mono("4", 14),
      body(" bundled regions.", 14)], {"before": 3}),
], anchor=MSO_ANCHOR.MIDDLE)
fill(shape(s5, "card3-text").text_frame, [
    ([label("Next test")], {}),
    ([body("Train on our RL environments and measure the gain on held-out regions; extend the engine to weather "
           "isobars and nautical charts.", 14)], {"before": 3}),
], anchor=MSO_ANCHOR.MIDDLE)
IX, IW = 7.66, 11.48 - 7.66
p5 = s5.shapes.add_picture(str(truth), E(IX), E(1.88), width=E(IW))
p5.name = "truth-map"
cy = 1.88 + p5.height / M + 0.08
textbox(s5, IX, cy, IW, 0.62, [
    ([mono("TRUTH (computed): water reaches C1", 12, TRUTH, bold=True)], {}),
    ([mono("Haiku: C6 · Luna: C6", 12, AI, bold=True)], {"before": 2}),
], margins=(0, 0))

prs.save(OUT)
print("wrote", OUT, "slides:", len(prs.slides))
