"""Render TidalTwin database & data workflow diagram -> db_workflow.png"""
import os
from PIL import Image, ImageDraw, ImageFont

S = 2  # supersample factor
W, H = 2400, 1900
WW, HH = W * S, H * S
img = Image.new("RGB", (WW, HH), (255, 255, 255))
d = ImageDraw.Draw(img)

NAVY = (0x1E, 0x3A, 0x5F)
BLUE = (0x0E, 0xA5, 0xE9)
DEEP = (0xB4, 0x5F, 0x06)
TEAL = (0x0F, 0x76, 0x6E)
RED = (0xE1, 0x1D, 0x48)
GREEN = (0x05, 0x96, 0x69)
GOLD = (0x9A, 0x70, 0x1F)
INK = (0x1F, 0x29, 0x37)
MUT = (0x55, 0x66, 0x78)
PANEL = (0xEE, 0xF2, 0xF7)
WHITE = (255, 255, 255)
LINE = (0xC8, 0xD3, 0xE0)
BLUEL = (0xE3, 0xF3, 0xFC)
ORANGEL = (0xFE, 0xEF, 0xDF)
TEALL = (0xE4, 0xF4, 0xF1)
GREYL = (0xF0, 0xF3, 0xF6)

_fonts = {}
def _font(size, bold=False):
    key = (size, bold)
    if key not in _fonts:
        name = "seguisb.ttf" if bold else "segoeui.ttf"
        path = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", name)
        _fonts[key] = ImageFont.truetype(path, size * S)
    return _fonts[key]

def R(x0, y0, x1, y1):
    return (x0 * S, y0 * S, x1 * S, y1 * S)

def box(x0, y0, x1, y1, fill=PANEL, outline=LINE, radius=14, width=2):
    d.rounded_rectangle(R(x0, y0, x1, y1), radius=radius * S, fill=fill,
                        outline=outline, width=width * S)

def line(x0, y0, x1, y1, color=MUT, width=2, dash=None):
    if dash is None:
        d.line(R(x0, y0, x1, y1), fill=color, width=width * S)
    else:
        _dash(x0, y0, x1, y1, color, width, dash)

def _dash(x0, y0, x1, y1, color, width, dash):
    import math
    dx, dy = x1 - x0, y1 - y0
    dist = math.hypot(dx, dy)
    ux, uy = dx / dist, dy / dist
    t, on = 0.0, True
    while t < dist:
        seg = dash if on else dash * 0.6
        if t + seg > dist:
            seg = dist - t
        if on:
            d.line((x0 + ux * t, y0 + uy * t, x0 + ux * (t + seg), y0 + uy * (t + seg)),
                   fill=color, width=width * S)
        t += seg
        on = not on

def arrow(x0, y0, x1, y1, color=MUT, width=3, head=16, dash=None):
    import math
    if dash == "dashed":
        _dash(x0, y0, x1, y1, color, width, 18)
    else:
        d.line(R(x0, y0, x1, y1), fill=color, width=width * S)
    ang = math.atan2(y1 - y0, x1 - x0)
    hx, hy = head * math.cos(ang), head * math.sin(ang)
    bx, by = math.cos(ang + 2.4) * head, math.sin(ang + 2.4) * head
    cx, cy = math.cos(ang - 2.4) * head, math.sin(ang - 2.4) * head
    d.polygon([(x1 * S, y1 * S), ((x1 - hx + bx) * S, (y1 - hy + by) * S),
               ((x1 - hx + cx) * S, (y1 - hy + cy) * S)], fill=color)

def txt(x, y, s, size=18, fill=INK, bold=False, center=False):
    f = _font(size, bold)
    if center:
        w = f.getbbox(s)[2] - f.getbbox(s)[0]
        x -= w / 2 / S
    d.text((x * S, y * S), s, font=f, fill=fill)

def heading(title, sub):
    txt(70, 40, title, 42, NAVY, bold=True)
    txt(70, 98, sub, 21, MUT)

def chip(x0, y0, x1, y1, s, fill=NAVY, size=19):
    box(x0, y0, x1, y1, fill=fill, outline=None, radius=(y1 - y0) / 2)
    w = _font(size, True).getbbox(s)[2] - _font(size, True).getbbox(s)[0]
    txt((x0 + x1) / 2 - w / 2 / S, y0 + (y1 - y0) / 2 - size * 0.72, s, size, WHITE, bold=True)

# ============================================================ HEADER
heading("TidalTwin — Database & Data Workflow",
        "Sources → Ingestion → Single relational store → AI engines → Decisions  ·  every value traceable via provenance_register")

# ============================================================ SOURCES
chip(70, 150, 360, 200, "DATA SOURCES", NAVY, 19)
srcs = [
    ("Open-Meteo Marine", "ERA5-driven live weather-\nmarine API (surface T/S,\nwaves, currents)", "OBSERVED", BLUE, BLUEL),
    ("NOAA CoastWatch ERDDAP", "HYCOM 3D model fields\n+ daily chlorophyll\n(nesdisVHNchlaDaily)", "MODEL", DEEP, ORANGEL),
    ("Argo GDAC", "real float budgets —\nT / S vertical profiles\n(WMO float ids)", "OBSERVED", BLUE, BLUEL),
    ("IOOS Glider DAC", "glider trajectories +\nBGC sensors\n(O2 · Chl · NO3)", "OBSERVED", BLUE, BLUEL),
    ("Ship / moored CTD", "vertical cast profiles\n(T · S · P, BGC-capable,\nstation ids)", "OBSERVED", BLUE, BLUEL),
    ("Global Fishing Watch AIS", "vessels as sensors —\nposition reports used to\nderive surface currents", "OBSERVED", BLUE, BLUEL),
]
bx, bw = 70, 350
for name, sub, tag, tcol, tfill in srcs:
    box(bx, 220, bx + bw, 400, fill=tfill, outline=BLUE, radius=16)
    txt(bx + 20, 240, name, 21, NAVY, bold=True)
    idx = 0
    for ln in sub.split("\n"):
        txt(bx + 20, 282 + idx * 27, ln, 15, MUT)
        idx += 1
    tw = _font(13, True).getbbox(tag)[2] - _font(13, True).getbbox(tag)[0]
    chip(bx + bw - tw - 46, 362, bx + bw - 16, 388, tag, tcol, 13)
    cx = bx + bw / 2
    arrow(cx, 400, cx, 470, BLUE, 3, 14)
    bx += bw + 25

# ============================================================ INGESTION
box(70, 470, 2330, 590, fill=PANEL, outline=GREEN, radius=16)
chip(95, 505, 255, 565, "INGESTION", GREEN, 18)
txt(290, 502, "fetch_* → ingest_* scripts  ·  NetCDF 4-D box unpacked into SQL rows  ·  QC applied  ·  missing fields stay NULL (never invented)", 19, INK, bold=True)
txt(290, 538, "each batch registered in provenance_register → every value traceable to its source + method tag  (OBSERVED | DERIVED | MODEL | SIMULATED)", 18, MUT)
for x in (400, 800, 1200, 1600, 2000):
    arrow(x, 590, x, 640, GREEN, 3, 14)

# ============================================================ DATABASE
box(70, 640, 2330, 1200, fill=WHITE, outline=NAVY, radius=18, width=3)
txt(1200, 662, "PostgreSQL 16 + PostGIS 3.4  ·  geometry SRID 4326  ·  one relational store", 27, NAVY, bold=True, center=True)
txt(1200, 704, "ocean_observations = the heart · real in-situ profiles and model outputs kept separate · nothing interpolated", 19, MUT, center=True)

def card(x0, y0, w, h, title, lines, tag=None, tcol=BLUE, tfill=BLUEL,
         title_fill=NAVY, border=BLUE, sep_line=False):
    box(x0, y0, x0 + w, y0 + h, fill=WHITE if False else PANEL, outline=border, radius=12)
    if sep_line:
        line(x0 + 14, y0 + 32, x0 + w - 14, y0 + 32, LINE, 1)
    txt(x0 + 16, y0 + 9, title, 18, title_fill, bold=True)
    idx = 0
    for ln in lines:
        txt(x0 + 16, y0 + 47 + idx * 23, ln, 13.5, INK)
        idx += 1
    if tag:
        tw = _font(13, True).getbbox(tag)[2] - _font(13, True).getbbox(tag)[0]
        chip(x0 + w - tw - 44, y0 + 8, x0 + w - 12, y0 + 32, tag, tcol, 12)

cw, cgap = 512, 25
xs = [130, 130 + (cw + cgap), 130 + 2 * (cw + cgap), 130 + 3 * (cw + cgap)]
r1y, r2y = 742, 940

card(xs[0], r1y, cw, 172,
     "ocean_locations",
     ["id · name · region_type", "country", "geom — POLYGON (SRID 4326)", "parent of observations", "and alerts (FK targets)"],
     tag="PARENT", tcol=RED, tfill=(0xFB, 0xE9, 0xEE))
card(xs[1], r1y, cw, 172,
     "ocean_observations",
     ["id · location_id ↗ · timestamp", "SST · wave height/dir · salinity", "current speed/dir · depth_m", "O2 · Chl-a · pH · NO3 · pressure · density", "data_type · source · extra"],
     tag="HEART", tcol=TEAL, tfill=TEALL, title_fill=(0x9A, 0x70, 0x1F), border=GOLD)
arrow(xs[0] + cw - 30, r1y + 10, xs[1] + 10, r1y + 32, RED, 2, 10)
card(xs[2], r1y, cw, 172,
     "netcdf_readings",
     ["lat · lon · depth_m · time", "variable_name · value", "CF standard_name · units", "per grid point, unpacked", "from HYCOM .nc files (MODEL)"],
     tag="MODEL", tcol=DEEP, tfill=ORANGEL)
card(xs[3], r1y, cw, 172,
     "derived_currents",
     ["cell centre point · lat · lon", "cell_deg · time_bucket", "u · v · speed · direction", "n_vessels · n_obs · uncertainty", "method_tag = DERIVED"],
     tag="DERIVED", tcol=TEAL, tfill=TEALL)

card(xs[0], r2y, cw, 172,
     "argo_profiles",
     ["float_id (WMO) · time", "lat · lon · depth_m", "T · S · P — real values", "NULL where not in file", "source_file"],
     tag="IN-SITU", tcol=BLUE, tfill=BLUEL)
card(xs[1], r2y, cw, 172,
     "glider_profiles",
     ["deployment_id · instrument", "lat · lon · depth_m · time", "T · S · P · O2 · Chl · NO3", "qc_flags · source_file"],
     tag="IN-SITU", tcol=BLUE, tfill=BLUEL)
card(xs[2], r2y, cw, 172,
     "ctd_profiles",
     ["station_id · instrument", "lat · lon · depth_m · time", "T · S · P · O2 · Chl · NO3", "qc_flags · source_file"],
     tag="IN-SITU", tcol=BLUE, tfill=BLUEL)
card(xs[3], r2y, cw, 172,
     "ais_tracks",
     ["vessel_hash (SHA-256 — no MMSI)", "time · geom — POINT (SRID 4326)", "SOG · COG", "source · method_tag", "provenance_id"],
     tag="OBSERVED", tcol=BLUE, tfill=BLUEL)

# provenance strip
pbox = (130, 1128, xs[3] + cw, 1184)
box(*pbox, fill=TEALL, outline=TEAL, radius=10)
txt(150, 1139, "provenance_register — source_name · source_url · batch_key · method_tag · notes      ←  every table above traces to its batch here", 17, INK, bold=True)
for x in xs:
    arrow(x + cw / 2, r2y + 172, x + cw / 2, 1128, TEAL, 2, 10)

# ============================================================ ENGINES
for x in (300, 800, 1300, 1800):
    arrow(x, 1200, x, 1248, NAVY, 3, 14)

chip(70, 1230, 320, 1280, "AI ENGINES", NAVY, 19)
ex = [xs[0], xs[1], xs[2], xs[3]]
eng = [
    ("Difference Engine", ["model vs observed, field-by-", "field deviation — magnitude +", "explained uncertainty"], BLUE, BLUEL),
    ("Anomaly Radar", ["Isolation Forest + z-score", "event candidates with confidence", "and severity (event types)"], BLUE, BLUEL),
    ("Forensics · Event DNA", ["what · when · at what depth", "contributing factors · evidence", "structured event fingerprint"], BLUE, BLUEL),
    ("TIDE-Loop", ["observation value =", "impact × uncertainty × gap ×", "persistence ÷ cost  ·  evidence-", "backed ranking · SIMULATED", "what-if · decision replay"], DEEP, ORANGEL),
]
ey = 1290
alert_top = ey + 214 + 46 + 6
for (tx, (name, lines, bcol, bfill)) in zip(ex, eng):
    h = 214
    box(tx, ey, tx + cw, ey + h, fill=bfill, outline=bcol, radius=12)
    txt(tx + 16, ey + 10, name, 18, NAVY if name != "TIDE-Loop" else (0x9A, 0x70, 0x1F), bold=True)
    idx = 0
    for ln in lines:
        txt(tx + 16, ey + 52 + idx * 24, ln, 13.5, INK)
        idx += 1
    arrow(tx + cw / 2, ey + h, tx + cw / 2, alert_top - 2, bcol, 3, 12)
alerts_y = alert_top + 4

# ============================================================ ocean_alerts (DB table written by engines, read by UI)
abox = (130, alerts_y, xs[3] + cw, alerts_y + 76)
box(*abox, fill=(0xFB, 0xE9, 0xEE), outline=RED, radius=12)
txt(150, alerts_y + 10, "ocean_alerts  (FK → ocean_locations)", 18, RED, bold=True)
txt(150, alerts_y + 43, "alert_type · severity · confidence · status · lat/lon · I've read: engines write here → UI reads", 14.5, MUT)

for x in xs:
    arrow(x + cw / 2, alerts_y + 76, x + cw / 2, alerts_y + 118, RED, 3, 12)

# ============================================================ OUTPUTS
oy = alerts_y + 118
box(70, oy, 2330, oy + 150, fill=PANEL, outline=GREEN, radius=16)
chip(95, oy + 40, 250, oy + 100, "OUTPUTS", GREEN, 18)
txt(290, oy + 28, "CesiumJS 4D globe · event replay · what-if preview", 19, INK, bold=True)
txt(290, oy + 62, "advisories SAFE · CAUTION · DANGER  ·  national risk map  ·  executive reports + CSV  ·  SMS / WhatsApp + 6-language voice", 18, INK)
txt(290, oy + 99, "ocean_alerts and observations read by the frontend via FastAPI REST + WebSocket", 17, MUT)

# feedback loop on right margin
fbx = 2362
arrow(fbx, oy + 60, fbx, 470, MUT, 3, 14, dash="dashed")
# rotated label
lab = "ADAPTIVE FEEDBACK — recommended next observation → re-observe → re-ingest (loop closes)"
f = _font(20, True)
tw = f.getbbox(lab)[2] - f.getbbox(lab)[0]
tmp = Image.new("RGBA", (int(tw) + 20 * S, 46 * S), (255, 255, 255, 0))
td = ImageDraw.Draw(tmp)
td.text((10 * S, 8 * S), lab, font=f, fill=MUT)
tmp = tmp.rotate(90, expand=True)
cy = (oy + 60 + 470) // 2
img = img.convert("RGBA")
d = ImageDraw.Draw(img)
img.alpha_composite(tmp, (int(fbx * S - tmp.width / 2), int(cy * S - tmp.height / 2)))
# small arrowhead into sources band for feedback
arrow(fbx - 6, 470, fbx - 6, 420, MUT, 3, 12, dash="dashed")

img = img.resize((W, H), Image.LANCZOS)
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db_workflow.png")
img.save(out)
print("saved:", out, img.size)