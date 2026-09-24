"""Render TidalTwin whole-project workflow diagram -> project_workflow.png"""
import os, math
from PIL import Image, ImageDraw, ImageFont

S = 2
W, H = 2600, 2680
img = Image.new("RGB", (W * S, H * S), (255, 255, 255))
d = ImageDraw.Draw(img)

NAVY = (0x1E, 0x3A, 0x5F); BLUE = (0x0E, 0xA5, 0xE9)
DEEP = (0xB4, 0x5F, 0x06); TEAL = (0x0F, 0x76, 0x6E)
RED = (0xE1, 0x1D, 0x48); GREEN = (0x05, 0x96, 0x69)
GOLD = (0x9A, 0x70, 0x1F); INK = (0x1F, 0x29, 0x37)
MUT = (0x55, 0x66, 0x78); PANEL = (0xEE, 0xF2, 0xF7)
WHITE = (255, 255, 255); LINE = (0xC8, 0xD3, 0xE0)
BLUEL = (0xE3, 0xF3, 0xFC); ORANGEL = (0xFE, 0xEF, 0xDF)
TEALL = (0xE4, 0xF4, 0xF1); REDL = (0xFB, 0xE9, 0xEE)

_fonts = {}
def _font(size, bold=False):
    key = (size, bold)
    if key not in _fonts:
        name = "seguisb.ttf" if bold else "segoeui.ttf"
        path = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name)
        _fonts[key] = ImageFont.truetype(path, size * S)
    return _fonts[key]

def R(x0, y0, x1, y1): return (x0 * S, y0 * S, x1 * S, y1 * S)

def box(x0, y0, x1, y1, fill=PANEL, outline=LINE, radius=14, width=2):
    d.rounded_rectangle(R(x0, y0, x1, y1), radius=radius * S, fill=fill,
                        outline=outline, width=width * S)

def line(x0, y0, x1, y1, color=MUT, width=2, dash=None):
    if dash is None:
        d.line(R(x0, y0, x1, y1), fill=color, width=width * S)
    else:
        _dash(x0, y0, x1, y1, color, width, dash)

def _dash(x0, y0, x1, y1, color, width, dash):
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy); ux, uy = dx / dist, dy / dist
    t, on = 0.0, True
    while t < dist:
        seg = dash if on else dash * 0.6
        if t + seg > dist: seg = dist - t
        if on:
            d.line((x0 + ux * t, y0 + uy * t, x0 + ux * (t + seg), y0 + uy * (t + seg)),
                   fill=color, width=width * S)
        t += seg; on = not on

def arrow(x0, y0, x1, y1, color=MUT, width=3, head=16, dash=None):
    if dash == "dashed": _dash(x0, y0, x1, y1, color, width, 18)
    else: d.line(R(x0, y0, x1, y1), fill=color, width=width * S)
    ang = math.atan2(y1 - y0, x1 - x0)
    hx, hy = head * math.cos(ang), head * math.sin(ang)
    bx = math.cos(ang + 2.4) * head; by = math.sin(ang + 2.4) * head
    cx = math.cos(ang - 2.4) * head; cy = math.sin(ang - 2.4) * head
    d.polygon([(x1 * S, y1 * S), ((x1 - hx + bx) * S, (y1 - hy + by) * S),
               ((x1 - hx + cx) * S, (y1 - hy + cy) * S)], fill=color)

def txt(x, y, s, size=18, fill=INK, bold=False, center=False):
    f = _font(size, bold)
    if center:
        x -= (f.getbbox(s)[2] - f.getbbox(s)[0]) / 2 / S
    d.text((x * S, y * S), s, font=f, fill=fill)

def chip(x0, y0, x1, y1, s, fill=NAVY, size=19, tcol=WHITE):
    box(x0, y0, x1, y1, fill=fill, outline=None, radius=(y1 - y0) / 2)
    f = _font(size, True)
    w = (f.getbbox(s)[2] - f.getbbox(s)[0]) / S
    txt((x0 + x1) / 2 - w / 2, y0 + (y1 - y0) / 2 - size * 0.72, s, size, tcol, bold=True)

def cards(name, lines, x0, y0, w, h, bcol, bfill, tcol=NAVY, name_size=18, line_size=13.5, start=12, step=24):
    box(x0, y0, x0 + w, y0 + h, fill=bfill, outline=bcol, radius=12)
    txt(x0 + 16, y0 + start - 2, name, name_size, tcol, bold=True)
    idx = 0
    for ln in lines:
        txt(x0 + 16, y0 + start + 34 + idx * step, ln, line_size, INK)
        idx += 1

# ============================================================ HEADER
txt(70, 34, "TidalTwin — Whole-Project Workflow", 44, NAVY, bold=True)
txt(70, 92, "Sources → Ingestion → Store → FastAPI engines (27 REST routers + WebSocket) → React/Cesium frontend → decisions  ·  TIDE closes the adaptive loop",
    21, MUT)

# ============================================================ 1. SOURCES
chip(70, 148, 400, 200, "DATA SOURCES", NAVY, 19)
srcs = [
    ("Open-Meteo Marine", ["ERA5-driven live surface", "T/S · waves · currents"], "OBSERVED", BLUE, BLUEL),
    ("NOAA CoastWatch", ["ERDDAP griddap: HYCOM", "3D model fields + chlorophyll"], "MODEL", DEEP, ORANGEL),
    ("Argo GDAC", ["real float T/S profiles", "(WMO float ids)"], "OBSERVED", BLUE, BLUEL),
    ("IOOS Glider DAC", ["glider trajectories + BGC", "(O2 · Chl · NO3)"], "OBSERVED", BLUE, BLUEL),
    ("Ship / moored CTD", ["vertical cast profiles", "T · S · P · BGC-capable"], "OBSERVED", BLUE, BLUEL),
    ("GFW AIS", ["ships-as-sensors →", "derived surface currents"], "OBSERVED", BLUE, BLUEL),
    ("Scenario Lab", ["injected marine-heatwave", "& severe-weather runs"], "SIMULATED", TEAL, TEALL),
]
sw, sg = 335, 26
bx0 = 70
for name, sub, tag, tcol, tfill in srcs:
    box(bx0, 226, bx0 + sw, 432, fill=tfill, outline=BLUE, radius=16)
    txt(bx0 + 18, 248, name, 19, NAVY, bold=True)
    y = bt = 296
    for ln in sub:
        txt(bx0 + 18, y, ln, 14.5, MUT); y += 27
    tw = _font(13, True).getbbox(tag)[2] - _font(13, True).getbbox(tag)[0]
    chip(bx0 + sw - tw - 52, 398, bx0 + sw - 18, 424, tag, tcol, 12)
    arrow(bx0 + sw / 2, 432, bx0 + sw / 2, 486, BLUE, 3, 14)
    bx0 += sw + sg

# ============================================================ 2. INGESTION
box(70, 486, 2530, 596, fill=PANEL, outline=GREEN, radius=16)
chip(95, 522, 275, 582, "INGESTION", GREEN, 18)
txt(310, 520, "fetch_* → ingest_* scripts  ·  NetCDF 4-D box unpacked into SQL rows  ·  QC  ·  missing fields stay NULL (never invented)", 19, INK, bold=True)
txt(310, 556, "every batch registered in provenance_register → each value traceable to source + method tag  (OBSERVED | DERIVED | MODEL | SIMULATED)", 18, MUT)
for x in (400, 800, 1200, 1600, 2000):
    arrow(x, 596, x, 636, GREEN, 3, 14)

# ============================================================ 3. DATABASE
box(70, 636, 2530, 884, fill=WHITE, outline=NAVY, radius=18, width=3)
txt(1300, 656, "PostgreSQL 16 + PostGIS 3.4 — single relational store (geometry SRID 4326)", 26, NAVY, bold=True, center=True)
tabs = [
    ("ocean_locations", REDL, RED), ("ocean_observations ★ heart", TEALL, TEAL),
    ("netcdf_readings", ORANGEL, DEEP), ("derived_currents", TEALL, TEAL),
    ("argo_profiles", BLUEL, BLUE), ("glider_profiles", BLUEL, BLUE),
    ("ctd_profiles", BLUEL, BLUE), ("ais_tracks", BLUEL, BLUE),
    ("provenance_register", TEALL, TEAL), ("ocean_alerts ★ outputs", REDL, RED),
]
cw0, chh = 460, 62
for i, (t, tf, tc) in enumerate(tabs):
    col, row = i % 5, i // 5
    x = 120 + col * (cw0 + 35)
    y = 712 + row * (chh + 26)
    box(x, y, x + cw0, y + chh, fill=tf, outline=tc, radius=12)
    txt(x + 16, y + 18, t, 16, NAVY, bold=True)
for x in (500, 1100, 1700, 2300):
    arrow(x, 884, x, 924, NAVY, 3, 14)

# ============================================================ 4. ENGINES
box(70, 924, 2530, 1820, fill=WHITE, outline=BLUE, radius=18, width=3)
txt(1300, 948, "AI ENGINE LAYER — FastAPI modules (read the store, write verdicts & alerts)", 26, NAVY, bold=True, center=True)

def ecc(name, lines, x, y, w, h, bcol, bfill, tcol=NAVY):
    cards(name, lines, x, y, w, h, bcol, bfill, tcol=tcol)

xs4 = [110, 705, 1300, 1895]; cw4 = 565; rch = 200
r1y, r2y = 1000, 1246

ecc("Twin & Difference Engine", ["model vs observed, field-by-field", "deviation + explained uncertainty", "skill score · confidence"], xs4[0], r1y, cw4, rch, BLUE, BLUEL)
ecc("Anomaly Radar", ["Isolation Forest + z-score", "event candidates: marine heatwave,", "cold water, rapid change, currents"], xs4[1], r1y, cw4, rch, BLUE, BLUEL)
ecc("Forensics + Event DNA", ["what · when · at what depth", "contributing factors · evidence", "timeline → structured fingerprint"], xs4[2], r1y, cw4, rch, BLUE, BLUEL)
ecc("Forecasting", ["short-term trends", "+ Argo float trajectories", "(input to APEX planning)"], xs4[3], r1y, cw4, rch, BLUE, BLUEL)

ecc("Ocean Copilot (NLP)", ["natural-language access to the", "same grounded data & engines", "(assistant · multimodal)"], xs4[0], r2y, cw4, rch, BLUE, BLUEL)
ecc("APEX Adaptive Sensing", ["autonomous sensing planning", "sensing · adaptive · recommend", "(observation strategy)"], xs4[1], r2y, cw4, rch, BLUE, BLUEL)
ecc("Coastal Impact", ["sea-level rise · coral · beach", "fisheries · oil-spill exposure", "coastal community services"], xs4[2], r2y, cw4, rch, BLUE, BLUEL)
ecc("Safety Advisory & Risk", ["SAFE / CAUTION / DANGER", "risk index · safe sailing window", "(IST) · advisory reasoning"], xs4[3], r2y, cw4, rch, BLUE, BLUEL)

# TIDE wide card
r3y = 1492; tide_h = 292
box(xs4[0], r3y, xs4[1] + cw4, r3y + tide_h, fill=ORANGEL, outline=GOLD, radius=12)
txt(xs4[0] + 18, r3y + 14, "TIDE-Loop ★ — Trust-aware Information for Decision and Exploration", 21, GOLD, bold=True)
tide_lines = [
    "MODEL → OBSERVATION → DISAGREEMENT → NEXT OBSERVATION → DECISION → VALIDATION ↺",
    "observation value = decision impact × uncertainty × data gap × anomaly persistence ÷ cost",
    "evidence-backed observation ranking · cautious verdicts (LIKELY_*) · confidence ≠ proof",
    "what-if virtual observation (SIMULATED — never persisted) · decision replay (2 modes)",
    "benchmark vs RANDOM · UNIFORM · UNCERTAINTY_ONLY · ANOMALY_ONLY · DATA_GAP_ONLY",
]
y = r3y + 66
for ln in tide_lines:
    txt(xs4[0] + 18, y, ln, 16.5, INK); y += 30
txt(xs4[0] + 18, r3y + tide_h - 60, "honest boundary: heuristic, NOT validated science · “TIDE ties ANOMALY_ONLY” in the reference run",
    14.5, MUT)

ecc("Scenario Lab", ["deterministic scenario", "simulation for experiments", "and demonstration"], xs4[2], r3y, cw4, 136, TEAL, TEALL)
ecc("Reports & Risk", ["executive brief", "national risk ranking", "CSV export · story mode"], xs4[3], r3y, cw4, 136, TEAL, TEALL)
# 2 short cards fill below Scenario/Reports
box(xs4[2], r3y + 148, xs4[2] + cw4, r3y + tide_h, fill=PANEL, outline=LINE, radius=12)
txt(xs4[2] + 16, r3y + 164, "WebSocket live loop", 16, NAVY, bold=True)
txt(xs4[2] + 16, r3y + 200, "observations broadcast to the", 13.5, INK); txt(xs4[2] + 16, r3y + 224, "frontend (SST, wave, alerts)", 13.5, INK)
box(xs4[3], r3y + 148, xs4[3] + cw4, r3y + tide_h, fill=PANEL, outline=LINE, radius=12)
txt(xs4[3] + 16, r3y + 164, "OGC / EDR / CF / Interop", 16, NAVY, bold=True)
txt(xs4[3] + 16, r3y + 200, "standards-based data access", 13.5, INK); txt(xs4[3] + 16, r3y + 224, "(ogc · edr · cf · modelgrid)", 13.5, INK)

for x in (500, 1100, 1700, 2300):
    arrow(x, 1820, x, 1860, BLUE, 3, 14)

# ============================================================ 5. API + WEBSOCKET
box(70, 1860, 2530, 1972, fill=PANEL, outline=DEEP, radius=16)
chip(95, 1896, 270, 1956, "API", DEEP, 18)
txt(305, 1894, "FastAPI REST + WebSocket — 27 routers under /api/v1/*  ·  twin · tide · forensics · safety · coastal · intelligence · anomaly · forecast", 19, INK, bold=True)
txt(305, 1930, "argo · glider · ctd · ersst · chlor · modelgrid · currents · edr · lens · ogc · cf · reports · stories · demo · health/status   ⊕  live broadcast loop (WebSocket)", 18, MUT)
for x in (500, 1100, 1700, 2300):
    arrow(x, 1972, x, 2012, DEEP, 3, 14)

# ============================================================ 6. FRONTEND
box(70, 2012, 2530, 2462, fill=WHITE, outline=BLUE, radius=18, width=3)
txt(1300, 2036, "FRONTEND — React 19 · TypeScript · Vite · CesiumJS 3D globe · PWA", 26, NAVY, bold=True, center=True)
pages = [
    ("Mission Control", "dashboard"),
    ("4D Twin Globe", "CesiumJS"),
    ("Monitoring & Alerts", "live"),
    ("Model Validation", "workspace"),
    ("Anomaly Intel", "radar"),
    ("Ocean Forensics", "event DNA"),
    ("Decision Intelligence", "evidence"),
    ("TIDE Command Center", "+ replay · validation"),
    ("Ocean Vision", "depth views"),
    ("Coastal Intel", "impact"),
    ("Scenario Lab", "what-if"),
    ("Safety Center", "advisories"),
    ("Risk Map", "national"),
    ("Story Mode", "narrative"),
    ("Ocean AI Copilot", "chat"),
    ("Risk Reports", "CSV"),
]
for i, (p, sub) in enumerate(pages):
    col, row = i % 4, i // 4
    x = 110 + col * (cw4 + 30); y = 2090 + row * 84
    box(x, y, x + cw4, y + 66, fill=PANEL, outline=BLUE if "TIDE" in p else LINE, radius=12)
    txt(x + 14, y + 11, p, 16, NAVY if "TIDE" not in p else GOLD, bold=True)
    txt(x + 14, y + 39, sub, 12.5, MUT)
for x in (500, 1100, 1700, 2300):
    arrow(x, 2462, x, 2502, BLUE, 3, 14)

# ============================================================ 7. OUTPUTS / USERS
box(70, 2502, 2530, 2636, fill=PANEL, outline=GREEN, radius=16)
chip(95, 2538, 285, 2598, "USERS", GREEN, 18)
txt(320, 2518, "Safe sailing window (IST) · SMS / WhatsApp alerts · 6-language voice", 18, INK, bold=True)
txt(320, 2550, "SAFE · CAUTION · DANGER advisories  ·  national risk map  ·  auditable executive brief + CSV", 18, INK)
txt(320, 2586, "fisherfolk & coastal communities  ·  safety & coastal agencies  ·  governance", 17, MUT)

# ============================================================ FEEDBACK LOOP
fbx = 2576
arrow(fbx, 2580, fbx, 1450, MUT, 3, 14, dash="dashed")
arrow(fbx, 1450, fbx, 520, MUT, 3, 14, dash="dashed")
arrow(fbx - 6, 520, fbx - 6, 462, MUT, 3, 12, dash="dashed")
lab = "ADAPTIVE FEEDBACK  —  TIDE recommends the next observation → re-observe → re-ingest (loop closes)"
f = _font(20, True)
tw = f.getbbox(lab)[2] - f.getbbox(lab)[0]
tmp = Image.new("RGBA", (int(tw) + 20 * S, 46 * S), (255, 255, 255, 0))
td = ImageDraw.Draw(tmp)
td.text((10 * S, 8 * S), lab, font=f, fill=MUT)
tmp = tmp.rotate(90, expand=True)
cy = (2580 + 520) // 2
img = img.convert("RGBA")
d = ImageDraw.Draw(img)
img.alpha_composite(tmp, (int(fbx * S - tmp.width / 2), int(cy * S - tmp.height / 2)))

img = img.resize((W, H), Image.LANCZOS)
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "project_workflow.png")
img.save(out)
print("saved:", out, img.size)