"""Generate OceanVerse AI SIH pitch deck (4 slides, light theme)."""

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.util import Inches, Pt

# ---- palette ----
NAVY = RGBColor(0x1E, 0x3A, 0x5F)
BLUE = RGBColor(0x0E, 0xA5, 0xE9)
DEEP = RGBColor(0xB4, 0x5F, 0x06)
TEAL = RGBColor(0x0F, 0x76, 0x6E)
RED = RGBColor(0xE1, 0x1D, 0x48)
GREEN = RGBColor(0x05, 0x96, 0x69)
INK = RGBColor(0x1F, 0x29, 0x37)
MUT = RGBColor(0x55, 0x66, 0x78)
PANEL = RGBColor(0xEE, 0xF2, 0xF7)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
LINE = RGBColor(0xC8, 0xD3, 0xE0)

SW, SH = Inches(13.333), Inches(7.5)
FONT = "Segoe UI"


def _bg(slide, color=WHITE):
    slide.background.fill.solid()
    slide.background.fill.fore_color.rgb = color


def _box(slide, x, y, w, h, fill=PANEL, line=LINE, rounded=True, line_w=1.0, radius=0.12):
    shp = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if rounded else MSO_SHAPE.RECTANGLE,
        x, y, w, h,
    )
    if rounded:
        shp.adjustments[0] = radius
    shp.fill.solid()
    shp.fill.fore_color.rgb = fill
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line
        shp.line.width = Pt(line_w)
    return shp


def _txt(slide, x, y, w, h, text, size=18, color=INK, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, wrap=True, font=FONT, line_spacing=1.0):
    tb = slide.shapes.add_textbox(x, y, w, h)
    tf = tb.text_frame
    tf.word_wrap = wrap
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    lines = text.split("\n") if isinstance(text, str) else text
    for i, ln in enumerate(lines):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = line_spacing
        r = p.add_run()
        r.text = ln
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = color
        r.font.name = font
    return tb


def _chip(slide, x, y, w, h, text, fill, color=WHITE, size=12, bold=True):
    shp = _box(slide, x, y, w, h, fill=fill, line=None, radius=0.5)
    tf = shp.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.08)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    p = tf.paragraphs[0]
    p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = text
    r.font.size = Pt(size); r.font.bold = bold
    r.font.color.rgb = color; r.font.name = FONT
    return shp


def _pipeline(slide, x, y, w, step_w, h=Inches(0.62), gap=Inches(0.07)):
    steps = [("DATA", MUT), ("QC", MUT), ("MATCHING", BLUE), ("DEVIATION", RED),
             ("UNCERTAINTY", RED), ("EVENT", RED), ("IMPACT", RED), ("DECISION", GREEN)]
    cx = x
    for label, color in steps:
        box = _box(slide, cx, y, step_w, h, fill=color, line=None, radius=0.28)
        tf = box.text_frame
        tf.word_wrap = False
        tf.margin_left = tf.margin_right = Inches(0.03)
        p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = label
        r.font.size = Pt(10); r.font.bold = True
        r.font.color.rgb = WHITE; r.font.name = FONT
        if color == MUT:
            r.font.color.rgb = WHITE
        if label != "DECISION":
            ar = slide.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW, cx + step_w + Inches(0.008), y + h / 2 - Inches(0.09), gap - Inches(0.016), Inches(0.18))
            ar.fill.solid(); ar.fill.fore_color.rgb = DEEP
            ar.line.fill.background()
        cx += step_w + gap


prs = Presentation()
prs.slide_width, prs.slide_height = SW, SH
BLANK = prs.slide_layouts[6]

HEAD = Inches(0.55)
TITLE_BAR = Inches(0.85)

# ============================================================ SLIDE 1
s = prs.slides.add_slide(BLANK); _bg(s)
_box(s, 0, 0, SW, Inches(0.28), fill=BLUE, line=None, rounded=False)
_txt(s, Inches(0.9), Inches(2.0), Inches(11.5), Inches(1.2), "OceanVerse AI", size=56, color=NAVY, bold=True)
_txt(s, Inches(0.95), Inches(3.05), Inches(11.4), Inches(0.6),
     "Interactive 4D Ocean Model Validation & Decision Intelligence Platform", size=24, color=BLUE, bold=True)
_box(s, Inches(0.95), Inches(3.95), Inches(11.4), Inches(0.04), fill=DEEP, line=None, rounded=False)

q = _box(s, Inches(0.95), Inches(4.25), Inches(11.4), Inches(1.5), fill=PANEL, line=LINE, radius=0.15)
_txt(s, Inches(1.35), Inches(4.62), Inches(10.6), Inches(1.0),
     "“Not another ocean viewer — we tell you where the model disagrees with reality,\n"
     "why it matters, and what to do about it. The 3D globe is just the interface.”",
     size=19, color=INK, bold=False)

_txt(s, Inches(0.95), Inches(6.35), Inches(11.4), Inches(0.5),
     "Smart India Hackathon 2026  ·  Problem Statement SIH-26067  ·  Ocean Data Utilization for Coastal Community Services",
     size=14, color=MUT, bold=False)
_txt(s, Inches(0.95), Inches(6.9), Inches(11.4), Inches(0.4), "Team OceanVerse AI  ·  Mumbai",
     size=14, color=MUT, bold=True)

# ============================================================ SLIDE 2
s = prs.slides.add_slide(BLANK); _bg(s)
_box(s, 0, 0, SW, Inches(0.28), fill=BLUE, line=None, rounded=False)
_txt(s, Inches(0.9), HEAD, Inches(11.5), Inches(0.55),
     "From “what the ocean looks like” to “is the model right?”", size=30, color=NAVY, bold=True)
_line = _box(s, Inches(0.95), TITLE_BAR, Inches(11.4), Pt(3.5), fill=BLUE, line=None, rounded=False)
_txt(s, Inches(0.95), Inches(1.0), Inches(11.4), Inches(0.5),
     "The gap: coastal India makes life-and-safety decisions on instinct and scattered data.", size=15, color=MUT)

# left problem panel
_box(s, Inches(0.9), Inches(1.65), Inches(5.0), Inches(4.3), fill=PANEL, line=LINE)
_txt(s, Inches(1.25), Inches(1.95), Inches(4.3), Inches(0.5), "THE PROBLEM", size=17, color=RED, bold=True)
prob = [
    "7,500 km of coastline — data-poor, decisions made on instinct",
    "Ocean tools show WHAT the sea looks like, never IF the model is right",
    "Models drift from reality quietly — heatwaves, rough seas, flood risk",
    "Warnings reach the coast late, in no language the community speaks",
    "Platforms are archival: they show yesterday, they don’t validate today",
]
_y = Inches(2.5)
for ln in prob:
    _box(s, Inches(1.3), _y, Inches(0.13), Inches(0.13), fill=RED, line=None, radius=0.5)
    _txt(s, Inches(1.55), _y, Inches(4.1), Inches(0.9), ln, size=12.5, color=INK, line_spacing=1.05)
    _y += Inches(0.68)

# right pipeline panel
_box(s, Inches(6.2), Inches(1.65), Inches(6.2), Inches(4.3), fill=WHITE, line=LINE)
_txt(s, Inches(6.6), Inches(1.95), Inches(5.4), Inches(0.5), "OUR ANSWER — THE SCIENTIFIC INTELLIGENCE PIPELINE",
     size=15, color=NAVY, bold=True)
_pipeline(s, Inches(6.7), Inches(2.6), Inches(5.3), Inches(0.62))
_txt(s, Inches(6.6), Inches(3.5), Inches(5.5), Inches(2.3),
     "Live data → quality check → model-observation matching → field-by-field deviation\n"
     "→ explained uncertainty → classified ocean events → impact on coastal people\n"
     "→ a concrete operational decision.",
     size=13.5, color=INK, line_spacing=1.15)
_txt(s, Inches(6.6), Inches(5.35), Inches(5.5), Inches(0.6),
     "The 3D globe is only the interface — the intelligence is the pipeline.",
     size=12.5, color=BLUE, bold=True)

# bottom differentiator strip
strip = _box(s, Inches(0.9), Inches(6.2), Inches(11.5), Inches(0.9), fill=NAVY, line=None)
_txt(s, Inches(1.3), Inches(6.5), Inches(10.8), Inches(0.5),
     "We validate · we measure · we explain · we name the event · we end in a decision",
     size=17, color=WHITE, bold=True, align=PP_ALIGN.CENTER)

# ============================================================ SLIDE 3
s = prs.slides.add_slide(BLANK); _bg(s)
_box(s, 0, 0, SW, Inches(0.28), fill=BLUE, line=None, rounded=False)
_txt(s, Inches(0.9), HEAD, Inches(11.5), Inches(0.55), "Live today — data in, decisions out", size=30, color=NAVY, bold=True)
_line = _box(s, Inches(0.95), TITLE_BAR, Inches(11.4), Pt(3.5), fill=BLUE, line=None, rounded=False)

# 3-band architecture
def _band(y, label, color, height=Inches(1.0)):
    box = _box(s, Inches(0.9), y, Inches(11.5), height, fill=PANEL, line=LINE)
    tag = _box(s, Inches(0.9), y - Inches(0.24), Inches(2.5), Inches(0.34), fill=color, line=None, radius=0.5)
    tf = tag.text_frame; p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = label; r.font.size = Pt(12); r.font.bold = True
    r.font.color.rgb = WHITE; r.font.name = FONT
    return box

_band(Inches(1.55), "DATA LAYER", MUT)
_txt(s, Inches(1.3), Inches(1.85), Inches(10.8), Inches(0.5),
     "Open-Meteo Marine (ERA5-driven)  ·  PostgreSQL 16 + PostGIS  ·  8 Indian coastal regions  ·  384+ live observations  ·  injected heatwave scenarios",
     size=13, color=INK, bold=True)

_band(Inches(2.75), "BACKEND — FASTAPI AI ENGINES", BLUE)
_txt(s, Inches(1.3), Inches(3.05), Inches(10.8), Inches(0.5),
     "Difference Engine  ·  Explainable Confidence  ·  Model Skill Score  ·  Event Classification  ·  Anomaly Detection (Isolation Forest + z-score)  ·  Forecasting  ·  Safety Advisory  ·  Risk Index  ·  What-If Simulator  ·  NLP Assistant  ·  Live WebSocket push",
     size=13, color=INK, bold=True)

_band(Inches(3.95), "FRONTEND — REACT 19 · TYPESCRIPT · CESIUM 3D · PWA", DEEP)
_txt(s, Inches(1.3), Inches(4.25), Inches(10.8), Inches(0.5),
     "Dashboard  ·  4D Digital Twin Globe & Event Replay  ·  Model Validation Workspace  ·  Monitoring  ·  Safety Center  ·  National Risk Map  ·  Ocean AI  ·  Story Mode  ·  Reports",
     size=13, color=INK, bold=True)

_band(Inches(5.15), "DECISION OUTPUTS", GREEN)
_txt(s, Inches(1.3), Inches(5.45), Inches(10.8), Inches(0.5),
     "SAFE / CAUTION / DANGER advisory  ·  safe sailing window (IST)  ·  SMS / WhatsApp + 6-language voice  ·  national risk map  ·  executive report + CSV",
     size=13, color=INK, bold=True)

# proof chips
_txt(s, Inches(0.95), Inches(6.05), Inches(11.4), Inches(0.4), "LIVE PROOF (from the running system)", size=14, color=NAVY, bold=True)
chips = [
    ("Marine heatwave at Goa CAUGHT", RED, RED),
    ("+1.8°C vs model baseline — explained", RED, RED),
    ("91% event confidence", RED, RED),
    ("DANGER advisory + 6-language voice", GREEN, GREEN),
    ("Confidence 92–100% component-by-component", BLUE, BLUE),
    ("Observations streamed live every 12s", DEEP, DEEP),
]
cw = Inches(1.62); ch = Inches(0.55); gx = Inches(0.16); gy = Inches(0.14)
_x, _y = Inches(1.6), Inches(6.5)
for t, fill, _c in chips:
    _chip(s, _x, _y, cw, ch, t, fill, color=WHITE, size=9.5)
    _x += cw + gx
    if _x + cw > Inches(12.6):
        _x = Inches(1.6); _y += ch + gy

# ============================================================ SLIDE 4
s = prs.slides.add_slide(BLANK); _bg(s)
_box(s, 0, 0, SW, Inches(0.28), fill=BLUE, line=None, rounded=False)
_txt(s, Inches(0.9), HEAD, Inches(11.5), Inches(0.55),
     "From validation to action at the coast", size=30, color=NAVY, bold=True)
_line = _box(s, Inches(0.95), TITLE_BAR, Inches(11.4), Pt(3.5), fill=BLUE, line=None, rounded=False)

columns = [
    ("🐟  LIVELIHOODS", "Tells fisherfolk which grounds are safe today — and when the next safe sailing window opens."),
    ("🏥  SAFETY", "Anomaly → event → advisory in seconds: detection, confidence, interpretation, alert on one screen."),
    ("🏛️  GOVERNANCE", "Authorities get a validated, auditable ocean brief — risk ranking, executive summary, CSV."),
    ("🌍  SCALE", "The pipeline is coastline-agnostic — point it at any coast and the same engines run."),
]
cw2 = Inches(2.68); gapx = Inches(0.25); x0 = Inches(1.2); y_top = Inches(1.7)
for i, (title, body) in enumerate(columns):
    x = x0 + i * (cw2 + gapx)
    _box(s, x, y_top, cw2, Inches(3.9), fill=PANEL, line=LINE)
    _txt(s, x + Inches(0.25), y_top + Inches(0.4), cw2 - Inches(0.5), Inches(0.5),
         title, size=17, color=NAVY, bold=True)
    _txt(s, x + Inches(0.25), y_top + Inches(1.05), cw2 - Inches(0.5), Inches(2.6),
         body, size=13, color=INK, line_spacing=1.2)

ask = _box(s, Inches(1.2), Inches(5.9), Inches(10.9), Inches(1.2), fill=NAVY, line=None)
_txt(s, Inches(1.6), Inches(6.18), Inches(10.1), Inches(0.75),
     "With SIH support: scale to 100+ Indian coastal regions and connect official marine advisories —\n"
     "a decision-intelligence dashboard in the hands of every coast.",
     size=17, color=WHITE, bold=True, align=PP_ALIGN.CENTER, line_spacing=1.15)

prs.save(r"C:\Project 2.0\presentation\OceanVerse_SIH_Pitch.pptx")
print("saved: presentation/OceanVerse_SIH_Pitch.pptx")