"""Diegetic UI screens of the ASN Aquila (static textures for M1; live widgets later use the same visual language).
Style: docs/STILE.md §7 — dark translucent panels, white-blue data, amber warnings, red criticals, thin line work,
English text, Barlow Condensed for titles, IBM Plex Mono for data. Rendered at 2x and downsampled (anti-aliasing).

Run: uv run --with pillow --with numpy python tools/art/ui_screens.py   ->   art/_cache/ui/T_UI_*.png
"""
from __future__ import annotations

import math
import os
import random

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONTS = os.path.join(ROOT, "art", "_downloads", "fonts")
OUT = os.path.join(ROOT, "art", "_cache", "ui")
S = 2  # supersampling

BG = (4, 9, 18)
PANEL = (10, 22, 40)
LINE = (70, 140, 210)
DIM = (40, 80, 125)
TEXT = (205, 228, 255)
CYAN = (111, 195, 255)
AMBER = (255, 179, 71)
RED = (255, 74, 46)
GREEN = (80, 220, 150)
DEPT = {"command": (62, 123, 250), "engineering": (255, 159, 28), "medical": (46, 196, 182),
        "security": (230, 57, 70), "flight": (255, 214, 10), "science": (155, 93, 229)}


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(os.path.join(FONTS, name), size * S)


F_TITLE = lambda s: font("BarlowCondensed-SemiBold.ttf", s)
F_LABEL = lambda s: font("BarlowCondensed-Medium.ttf", s)
F_MONO = lambda s: font("IBMPlexMono-Regular.ttf", s)
F_MONO_B = lambda s: font("IBMPlexMono-Medium.ttf", s)


class Screen:
    def __init__(self, w: int = 1024, h: int = 640, dept: str = "command", title: str = "", sub: str = "", seed: int = 1):
        self.w, self.h = w, h
        self.img = Image.new("RGB", (w * S, h * S), BG)
        self.d = ImageDraw.Draw(self.img)
        self.acc = DEPT[dept]
        self.rng = random.Random(seed)
        # faint background grid
        for x in range(0, w, 32):
            self.d.line([(x * S, 0), (x * S, h * S)], fill=(8, 16, 30), width=1)
        for y in range(0, h, 32):
            self.d.line([(0, y * S), (w * S, y * S)], fill=(8, 16, 30), width=1)
        if title:
            self.header(title, sub)

    # --- primitives (coordinates in output pixels)
    def P(self, *xy):
        return [v * S for v in xy]

    def text(self, x, y, s, f, fill=TEXT, anchor="la"):
        self.d.text((x * S, y * S), s, font=f, fill=fill, anchor=anchor)

    def rect(self, x0, y0, x1, y1, outline=LINE, fill=None, width=1):
        self.d.rectangle(self.P(x0, y0, x1, y1), outline=outline, fill=fill, width=width * S)

    def line(self, pts, fill=LINE, width=1):
        self.d.line([(x * S, y * S) for x, y in pts], fill=fill, width=width * S)

    def brackets(self, x0, y0, x1, y1, c=None, L=14):
        c = c or LINE
        for (x, y, dx, dy) in ((x0, y0, 1, 1), (x1, y0, -1, 1), (x0, y1, 1, -1), (x1, y1, -1, -1)):
            self.line([(x, y + dy * L), (x, y), (x + dx * L, y)], fill=c, width=2)

    def panel(self, x0, y0, x1, y1, label=None):
        self.rect(x0, y0, x1, y1, outline=DIM, fill=PANEL)
        self.brackets(x0, y0, x1, y1, c=LINE)
        if label:
            self.text(x0 + 10, y0 + 6, label.upper(), F_LABEL(17), fill=CYAN)
            self.line([(x0 + 10, y0 + 28), (x1 - 10, y0 + 28)], fill=DIM)

    def header(self, title, sub):
        self.d.rectangle(self.P(0, 0, self.w, 44), fill=(6, 14, 28))
        self.d.rectangle(self.P(0, 0, 8, 44), fill=self.acc)
        self.text(20, 7, title.upper(), F_TITLE(28), fill=TEXT)
        self.text(self.w - 16, 12, sub or "ASN AQUILA · CVC-01", F_MONO(15), fill=CYAN, anchor="ra")
        self.line([(0, 44), (self.w, 44)], fill=self.acc, width=2)

    def footer(self, s, color=GREEN):
        self.d.rectangle(self.P(0, self.h - 28, self.w, self.h), fill=(6, 14, 28))
        self.text(16, self.h - 23, s, F_MONO(14), fill=color)
        self.text(self.w - 16, self.h - 23, "2491.271  03:38 SHIP", F_MONO(14), fill=DIM, anchor="ra")

    def bar(self, x, y, w, h, frac, label, value, color=CYAN, warn=0.85, crit=0.95):
        c = color if frac < warn else (AMBER if frac < crit else RED)
        self.text(x, y - 2, label.upper(), F_LABEL(16), fill=TEXT)
        self.text(x + w, y - 2, value, F_MONO(15), fill=c, anchor="ra")
        yb = y + 20
        self.rect(x, yb, x + w, yb + h, outline=DIM, fill=(6, 12, 24))
        segs = 40
        sw = w / segs
        for i in range(int(frac * segs)):
            self.d.rectangle(self.P(x + i * sw + 1, yb + 2, x + (i + 1) * sw - 1, yb + h - 2), fill=c)

    def gauge(self, cx, cy, r, frac, label, value, color=CYAN):
        a0, a1 = 135, 405
        self.d.arc(self.P(cx - r, cy - r, cx + r, cy + r), a0, a1, fill=DIM, width=6 * S)
        self.d.arc(self.P(cx - r, cy - r, cx + r, cy + r), a0, a0 + (a1 - a0) * frac, fill=color, width=6 * S)
        self.text(cx, cy - 12, value, F_MONO_B(26), fill=TEXT, anchor="mm")
        self.text(cx, cy + 22, label.upper(), F_LABEL(16), fill=CYAN, anchor="mm")

    def glow(self, amount=1.2):
        """Soft bloom-like halo around bright elements (screens look lit, not printed)."""
        blur = self.img.filter(ImageFilter.GaussianBlur(6 * S))
        self.img = Image.blend(self.img, Image.eval(blur, lambda v: min(255, int(v * amount))), 0.25)
        self.d = ImageDraw.Draw(self.img)

    def save(self, name):
        self.glow()
        out = self.img.resize((self.w, self.h), Image.LANCZOS)
        os.makedirs(OUT, exist_ok=True)
        out.save(os.path.join(OUT, f"T_UI_{name}.png"), optimize=True)
        return name


# ---------------------------------------------------------------- reusable widgets
def heading_tape(s: Screen, x0, y0, x1, heading):
    s.rect(x0, y0, x1, y0 + 60, outline=DIM, fill=(6, 12, 24))
    cx = (x0 + x1) / 2
    for d in range(-60, 61):
        hdg = (heading + d) % 360
        x = cx + d * (x1 - x0) / 120
        if hdg % 10 == 0:
            s.line([(x, y0 + 36), (x, y0 + 58)], fill=LINE, width=2)
            s.text(x, y0 + 6, f"{int(hdg):03d}", F_MONO(15), fill=TEXT, anchor="ma")
        elif hdg % 5 == 0:
            s.line([(x, y0 + 46), (x, y0 + 58)], fill=DIM)
    s.d.polygon([(cx * S, (y0 + 34) * S), ((cx - 9) * S, (y0 + 20) * S), ((cx + 9) * S, (y0 + 20) * S)], fill=AMBER)


def radar(s: Screen, cx, cy, r, contacts, sweep_deg=40):
    for k in (1, 2, 3, 4):
        rr = r * k / 4
        s.d.ellipse(s.P(cx - rr, cy - rr, cx + rr, cy + rr), outline=DIM if k < 4 else LINE, width=S * (1 if k < 4 else 2))
    for a in range(0, 360, 30):
        s.line([(cx, cy), (cx + r * math.sin(math.radians(a)), cy - r * math.cos(math.radians(a)))], fill=(20, 45, 75))
    # sweep wedge
    for i in range(40):
        a = math.radians(sweep_deg - i * 1.2)
        col = tuple(int(c * (1 - i / 40) * 0.6) for c in CYAN)
        s.line([(cx, cy), (cx + r * math.sin(a), cy - r * math.cos(a))], fill=col, width=2)
    for (bearing, rng, label, col) in contacts:
        x = cx + r * rng * math.sin(math.radians(bearing))
        y = cy - r * rng * math.cos(math.radians(bearing))
        s.d.rectangle(s.P(x - 5, y - 5, x + 5, y + 5), outline=col, width=2 * S)
        s.text(x + 9, y - 8, label, F_MONO(13), fill=col)
    s.d.polygon([(cx * S, (cy - 9) * S), ((cx - 7) * S, (cy + 7) * S), ((cx + 7) * S, (cy + 7) * S)], outline=TEXT)


def ship_silhouette(s: Screen, x0, y0, w, h, color=LINE, fill=(8, 20, 38), compartments=True, damaged=()):
    """Side view of the Aquila-class carrier cruiser (stylised), 780 m."""
    pts = [(0.00, 0.55), (0.06, 0.40), (0.22, 0.34), (0.30, 0.22), (0.46, 0.20), (0.50, 0.10), (0.60, 0.10),
           (0.64, 0.20), (0.86, 0.24), (0.97, 0.34), (1.00, 0.48), (0.97, 0.66), (0.86, 0.74), (0.60, 0.78),
           (0.40, 0.76), (0.20, 0.70), (0.06, 0.64)]
    poly = [((x0 + px * w) * S, (y0 + py * h) * S) for px, py in pts]
    s.d.polygon(poly, fill=fill, outline=color)
    if compartments:
        for i in range(1, 12):
            x = x0 + w * (0.04 + 0.08 * i)
            s.line([(x, y0 + h * 0.3), (x, y0 + h * 0.72)], fill=DIM)
        for j in range(1, 4):
            y = y0 + h * (0.3 + 0.105 * j)
            s.line([(x0 + w * 0.08, y), (x0 + w * 0.94, y)], fill=DIM)
        for (ci, cj, col) in damaged:
            x = x0 + w * (0.04 + 0.08 * ci)
            y = y0 + h * (0.3 + 0.105 * cj)
            s.d.rectangle(s.P(x + 2, y + 2, x + w * 0.08 - 2, y + h * 0.105 - 2), fill=col)


# ---------------------------------------------------------------- station screens
def helm():
    out = []
    s = Screen(dept="command", title="Helm · Flight Control", seed=11)
    heading_tape(s, 40, 70, 984, 45)
    s.panel(40, 150, 500, 590, "Attitude")
    cx, cy = 270, 380
    for k in range(-3, 4):
        y = cy + k * 50
        s.line([(cx - 120 + abs(k) * 12, y), (cx + 120 - abs(k) * 12, y)], fill=LINE if k else AMBER, width=2 if k == 0 else 1)
        if k:
            s.text(cx + 130, y - 9, f"{-k * 10:+d}", F_MONO(14), fill=DIM)
    s.line([(cx - 40, cy), (cx - 12, cy), (cx, cy + 12), (cx + 12, cy), (cx + 40, cy)], fill=AMBER, width=3)
    s.text(60, 550, "PITCH +10.0   ROLL 0.0   YAW RATE 0.2°/s", F_MONO(15), fill=TEXT)
    s.panel(524, 150, 984, 590, "Course")
    rows = [("ORDERED", "045 MARK 10"), ("CURRENT", "044.8 MARK 9.9"), ("VELOCITY", "412 m/s"), ("ACCEL", "0.35 g"),
            ("DESTINATION", "NEW RAVENNA HIGH ORBIT"), ("RANGE", "182,400 km"), ("ETA", "00:07:24"), ("MODE", "FLIGHT COMPUTER · FINE")]
    for i, (k, v) in enumerate(rows):
        s.text(544, 196 + i * 46, k, F_LABEL(18), fill=CYAN)
        s.text(964, 196 + i * 46, v, F_MONO(18), fill=TEXT, anchor="ra")
    s.footer("HELM READY · DAMPERS 100% · NO COLLISION RISK")
    out.append(s.save("Helm_A"))

    s = Screen(dept="command", title="Navigation · Aurelia System", seed=12)
    cx, cy = 512, 340
    for r, name in ((70, "VULCAN"), (150, "NEW RAVENNA"), (225, "CERES BELT"), (290, "TIBERIUS")):
        s.d.ellipse(s.P(cx - r * 1.5, cy - r, cx + r * 1.5, cy + r), outline=DIM, width=S)
    s.d.ellipse(s.P(cx - 12, cy - 12, cx + 12, cy + 12), fill=AMBER)
    s.text(cx + 18, cy - 10, "AURELIA", F_LABEL(17), fill=AMBER)
    bodies = [(70, 200, "VULCAN"), (150, 30, "NEW RAVENNA"), (290, 300, "TIBERIUS")]
    for r, a, n in bodies:
        x = cx + r * 1.5 * math.cos(math.radians(a))
        y = cy + r * math.sin(math.radians(a))
        s.d.ellipse(s.P(x - 6, y - 6, x + 6, y + 6), fill=CYAN)
        s.text(x + 10, y - 8, n, F_LABEL(16), fill=TEXT)
    sx, sy = cx - 330, cy + 120
    ex = cx + 150 * 1.5 * math.cos(math.radians(30))
    ey = cy + 150 * math.sin(math.radians(30))
    pts = [(sx + (ex - sx) * t + 60 * math.sin(t * math.pi), sy + (ey - sy) * t - 50 * math.sin(t * math.pi)) for t in [i / 30 for i in range(31)]]
    for i in range(0, 30, 2):
        s.line([pts[i], pts[i + 1]], fill=GREEN, width=2)
    s.d.polygon([(sx * S, (sy - 9) * S), ((sx - 7) * S, (sy + 7) * S), ((sx + 7) * S, (sy + 7) * S)], fill=GREEN)
    s.text(sx - 20, sy + 14, "ASN AQUILA", F_MONO(14), fill=GREEN)
    gx, gy = cx - 420, cy - 230
    s.d.ellipse(s.P(gx - 18, gy - 18, gx + 18, gy + 18), outline=TEXT, width=3 * S)
    s.text(gx + 26, gy - 10, "JANUS GATE AURELIA", F_LABEL(17), fill=TEXT)
    s.footer("PLOT LOCKED · 7TH FLEET DISPOSITION SHARED")
    out.append(s.save("Helm_B"))

    s = Screen(dept="command", title="Propulsion", seed=13)
    for i, (lab, fr, val) in enumerate((("MAIN DRIVE 1", 0.62, "62 %"), ("MAIN DRIVE 2", 0.61, "61 %"),
                                        ("MANEUVER PORT", 0.12, "12 %"), ("MANEUVER STBD", 0.14, "14 %"),
                                        ("DEUTERIUM", 0.78, "78 %"), ("DRIVE TEMP", 0.55, "1,840 K"))):
        s.bar(40, 70 + i * 82, 560, 22, fr, lab, val)
    s.gauge(800, 250, 130, 0.62, "Thrust", "62%")
    s.gauge(800, 500, 90, 0.35, "g-load", "0.35")
    s.footer("TORCH DRIVES NOMINAL")
    out.append(s.save("Helm_C"))
    return out


def ops():
    out = []
    s = Screen(dept="command", title="Operations · Power Grid", seed=21)
    s.gauge(170, 220, 120, 0.78, "Reactor", "78%")
    sys_ = (("SHIELDS", 0.55, "38 MW"), ("WEAPONS", 0.30, "21 MW"), ("ENGINES", 0.62, "44 MW"), ("SENSORS", 0.40, "9 MW"),
            ("LIFE SUPPORT", 0.25, "6 MW"), ("FLIGHT DECK", 0.18, "4 MW"))
    for i, (lab, fr, val) in enumerate(sys_):
        s.bar(360, 70 + i * 82, 624, 22, fr, lab, val)
    s.panel(40, 380, 320, 590, "Capacitors")
    for i in range(6):
        fr = [0.9, 0.85, 1.0, 0.7, 0.95, 0.88][i]
        x = 70 + i * 40
        s.rect(x, 420, x + 24, 570, outline=DIM)
        s.d.rectangle(s.P(x + 3, 570 - 147 * fr, x + 21, 567), fill=CYAN)
    s.footer("GRID BALANCED · HEAT 41% · BATTLE SHORT OFF")
    out.append(s.save("Ops_A"))

    s = Screen(dept="command", title="Ship Status", seed=22)
    ship_silhouette(s, 60, 80, 900, 330)
    s.panel(40, 430, 984, 590, "Departments")
    deps = [("COMMAND", GREEN), ("ENGINEERING", GREEN), ("MEDICAL", GREEN), ("SECURITY", GREEN), ("FLIGHT", GREEN), ("SCIENCE", GREEN)]
    for i, (n, c) in enumerate(deps):
        x = 60 + i * 155
        s.d.ellipse(s.P(x, 485, x + 14, 499), fill=c)
        s.text(x + 22, 480, n, F_LABEL(18), fill=TEXT)
        s.text(x + 22, 510, "NOMINAL", F_MONO(13), fill=DIM)
    s.footer("CONDITION GREEN · ALL DECKS PRESSURIZED")
    out.append(s.save("Ops_B"))

    s = Screen(dept="command", title="Logistics", seed=23)
    rows = [("RAILGUN SLUGS", "2,412", 0.8), ("MISSILES (VLS)", "96", 1.0), ("TORPEDOES", "12", 1.0), ("PD ROUNDS", "88,000", 0.9),
            ("SPARE PARTS", "71 %", 0.71), ("MEDICAL STORES", "94 %", 0.94), ("WATER", "97 %", 0.97), ("RATIONS", "83 d", 0.8)]
    for i, (k, v, fr) in enumerate(rows):
        s.bar(40 + (i % 2) * 492, 70 + (i // 2) * 130, 452, 22, fr, k, v)
    s.footer("RESUPPLY: AURELIA ARSENAL · SLOT 4")
    out.append(s.save("Ops_C"))
    return out


def comms():
    out = []
    s = Screen(dept="command", title="Communications", seed=31)
    s.panel(40, 70, 600, 590, "Channels")
    ch = [("FLEET NET · 7TH FLEET", "SECURE", GREEN), ("AURELIA TRAFFIC CONTROL", "OPEN", CYAN), ("KEEPER STATION", "SECURE", GREEN),
          ("ALPHA SQUADRON", "SECURE", GREEN), ("BRAVO SQUADRON", "SECURE", GREEN), ("DISTRESS 121.5", "MONITOR", AMBER),
          ("CIVILIAN BAND 3", "MONITOR", DIM)]
    for i, (n, st, c) in enumerate(ch):
        y = 116 + i * 64
        s.text(60, y, n, F_LABEL(20), fill=TEXT)
        s.text(580, y + 2, st, F_MONO(15), fill=c, anchor="ra")
        for k in range(24):
            h = 4 + 14 * abs(math.sin(k * 0.7 + i))
            s.d.rectangle(s.P(60 + k * 8, y + 44 - h, 64 + k * 8, y + 44), fill=DIM if c == DIM else c)
    s.panel(624, 70, 984, 590, "Queue")
    msgs = [("0336", "7TH FLT", "FORM ON FLAGSHIP"), ("0331", "KEEPER", "GATE TRAFFIC HOLD"), ("0325", "ATC", "LANE 3 CLEARED"),
            ("0319", "ALPHA", "CAP ESTABLISHED")]
    for i, (t, frm, m) in enumerate(msgs):
        y = 116 + i * 110
        s.text(644, y, f"{t}  {frm}", F_MONO(16), fill=CYAN)
        s.text(644, y + 30, m, F_LABEL(20), fill=TEXT)
    s.footer("TRANSLATOR ONLINE · QUANTUM RELAY LOCKED")
    out.append(s.save("Comms_A"))
    s = Screen(dept="command", title="Signal Analysis", seed=32)
    pts = []
    for i in range(0, 945):
        v = 0.15 + 0.08 * math.sin(i * 0.05) + 0.04 * s.rng.random()
        for c, w_ in ((300, 20), (520, 8), (700, 30)):
            v += 0.6 * math.exp(-((i - c) / w_) ** 2)
        pts.append((40 + i, 560 - 420 * v))
    s.line(pts, fill=CYAN, width=2)
    for c in (300, 520, 700):
        s.line([(40 + c, 90), (40 + c, 560)], fill=AMBER)
    s.text(40 + 520, 96, "UNKNOWN CARRIER", F_LABEL(17), fill=AMBER)
    s.footer("3 CARRIERS · 1 UNIDENTIFIED")
    out.append(s.save("Comms_B"))
    s = Screen(dept="command", title="Fleet Roster", seed=33)
    rows = [("ASN PRAETORIAN", "FLAGSHIP", "12 km"), ("ASN VIGILANT", "DESTROYER", "18 km"), ("ASN CONCORD", "CRUISER", "22 km"),
            ("ASN MERIDIAN", "FRIGATE", "31 km"), ("ASN LANTERN", "TENDER", "40 km"), ("KEEPER STATION", "STATION", "96,000 km")]
    for i, (n, c_, r) in enumerate(rows):
        y = 80 + i * 78
        s.rect(40, y, 984, y + 64, outline=DIM, fill=PANEL)
        s.text(60, y + 16, n, F_LABEL(24), fill=TEXT)
        s.text(560, y + 20, c_, F_MONO(16), fill=CYAN)
        s.text(964, y + 20, r, F_MONO(16), fill=TEXT, anchor="ra")
    s.footer("DATALINK 6/6")
    out.append(s.save("Comms_C"))
    return out


def sensors():
    out = []
    s = Screen(dept="science", title="Science & Sensors · Plot", seed=41)
    radar(s, 360, 350, 270, [(20, 0.3, "ASN PRAETORIAN", GREEN), (80, 0.55, "ASN VIGILANT", GREEN), (310, 0.7, "FREIGHTER", TEXT),
                              (200, 0.85, "UNKNOWN", AMBER)])
    s.panel(680, 70, 984, 590, "Tracks")
    tr = [("T-01", "FRIENDLY", GREEN), ("T-02", "FRIENDLY", GREEN), ("T-07", "NEUTRAL", TEXT), ("T-11", "UNKNOWN", AMBER)]
    for i, (t, c_, col) in enumerate(tr):
        y = 116 + i * 110
        s.text(700, y, t, F_MONO_B(20), fill=col)
        s.text(700, y + 30, c_, F_LABEL(18), fill=TEXT)
        s.text(964, y + 4, f"{s.rng.randint(8, 190)} km", F_MONO(15), fill=CYAN, anchor="ra")
    s.footer("PASSIVE ARRAY · ACTIVE RADAR STANDBY · EMCON 2")
    out.append(s.save("Sensors_A"))
    s = Screen(dept="science", title="Spectrum", seed=42)
    for b in range(0, 944, 6):
        h = 30 + 260 * abs(math.sin(b * 0.013)) * (0.5 + 0.5 * s.rng.random())
        s.d.rectangle(s.P(40 + b, 560 - h, 44 + b, 560), fill=(155, 93, 229) if b % 60 else CYAN)
    s.footer("THERMAL · EM · GRAVIMETRIC")
    out.append(s.save("Sensors_B"))
    s = Screen(dept="science", title="Contact T-11 · Analysis", seed=43)
    s.panel(40, 70, 984, 590, "Classification")
    for i, (k, v) in enumerate((("SIGNATURE", "HEAT 3.1 MW · LOW EM"), ("SIZE", "~310 m"), ("DRIVE", "COLD / DRIFTING"),
                                ("TRANSPONDER", "NONE"), ("ASSESSMENT", "UNKNOWN · POSSIBLE DECOY"), ("CONFIDENCE", "32 %"))):
        s.text(70, 120 + i * 70, k, F_LABEL(22), fill=CYAN)
        s.text(954, 120 + i * 70, v, F_MONO(20), fill=AMBER if "UNKNOWN" in v else TEXT, anchor="ra")
    s.footer("RECOMMEND ACTIVE PING", color=AMBER)
    out.append(s.save("Sensors_C"))
    return out


def engineering():
    out = []
    s = Screen(dept="engineering", title="Engineering · Reactor", seed=51)
    cx, cy = 300, 330
    for r in (200, 150, 100):
        s.d.ellipse(s.P(cx - r, cy - r, cx + r, cy + r), outline=(255, 159, 28) if r == 100 else DIM, width=3 * S)
    s.d.ellipse(s.P(cx - 60, cy - 60, cx + 60, cy + 60), fill=(60, 36, 10), outline=AMBER, width=2 * S)
    s.text(cx, cy, "78%", F_MONO_B(34), fill=TEXT, anchor="mm")
    for i, (lab, fr, val) in enumerate((("CORE TEMP", 0.58, "142 MK"), ("CONTAINMENT", 0.99, "99.7 %"), ("COOLANT FLOW", 0.72, "72 %"),
                                        ("RADIATORS", 0.46, "46 %"), ("HEAT SINKS", 0.31, "31 %"))):
        s.bar(560, 70 + i * 100, 424, 22, fr, lab, val, color=(255, 159, 28), warn=1.01)
    s.footer("FUSION REACTOR STABLE · OKONKWO ON WATCH", color=(255, 179, 71))
    out.append(s.save("Eng_A"))
    s = Screen(dept="engineering", title="Damage Control", seed=52)
    ship_silhouette(s, 60, 70, 900, 360, damaged=())
    s.panel(40, 440, 984, 590, "Teams")
    for i, t in enumerate(("DC-1 DECK 3", "DC-2 DECK 6", "DC-3 DECK 9", "FIRE TEAM A", "MEDICAL TEAM")):
        s.text(60 + i * 186, 490, t, F_LABEL(19), fill=TEXT)
        s.text(60 + i * 186, 520, "STANDBY", F_MONO(14), fill=GREEN)
    s.footer("ALL COMPARTMENTS SEALED · NO DAMAGE", color=(255, 179, 71))
    out.append(s.save("Eng_B"))
    s = Screen(dept="engineering", title="Thermal", seed=53)
    for i in range(12):
        for j in range(6):
            t = 0.3 + 0.4 * math.sin(i * 0.5 + j) ** 2
            col = (int(255 * t), int(159 * t), int(28 * t))
            s.d.rectangle(s.P(40 + i * 78, 70 + j * 84, 112 + i * 78, 148 + j * 84), fill=col)
    s.footer("PEAK 612 K · SECTION 7-C", color=(255, 179, 71))
    out.append(s.save("Eng_C"))
    return out


def flight():
    out = []
    y_ = DEPT["flight"]
    s = Screen(dept="flight", title="Flight Control · Hangar", seed=61)
    groups = [("ALPHA SQUADRON", "FALCON", 8, 8), ("BRAVO SQUADRON", "HAMMER", 8, 7), ("WASP DRONES", "EW / RECON", 12, 12)]
    for i, (n, t, tot, rdy) in enumerate(groups):
        y = 70 + i * 170
        s.panel(40, y, 984, y + 150, n)
        for k in range(tot):
            x = 60 + k * 76
            col = GREEN if k < rdy else AMBER
            s.d.polygon([((x + 30) * S, (y + 50) * S), ((x + 10) * S, (y + 110) * S), ((x + 50) * S, (y + 110) * S)], outline=col, width=2 * S)
            s.text(x + 30, y + 118, f"{k + 1:02d}", F_MONO(13), fill=col, anchor="ma")
        s.text(964, y + 6, f"{t} · {rdy}/{tot} READY", F_MONO(15), fill=y_, anchor="ra")
    s.footer("CAG: LT CMDR KOVAC \"HEX\" · DECK CLEAR", color=y_)
    out.append(s.save("Flight_A"))
    s = Screen(dept="flight", title="Launch Sequence", seed=62)
    for i, (k, st) in enumerate((("TUBE 1", "ARMED"), ("TUBE 2", "ARMED"), ("TUBE 3", "SAFE"), ("TUBE 4", "SAFE"),
                                 ("RECOVERY DECK", "OPEN"), ("CAP", "2 × FALCON"))):
        s.text(60, 90 + i * 80, k, F_LABEL(26), fill=TEXT)
        s.text(964, 94 + i * 80, st, F_MONO(20), fill=AMBER if st == "ARMED" else CYAN, anchor="ra")
        s.line([(60, 136 + i * 80), (964, 136 + i * 80)], fill=DIM)
    s.footer("LAUNCH WINDOW OPEN", color=y_)
    out.append(s.save("Flight_B"))
    s = Screen(dept="flight", title="Patrol", seed=63)
    radar(s, 512, 340, 250, [(40, 0.5, "FALCON 1", GREEN), (60, 0.55, "FALCON 2", GREEN), (170, 0.2, "AQUILA", CYAN)], sweep_deg=120)
    s.footer("COMBAT AIR PATROL · 2 ON STATION", color=y_)
    out.append(s.save("Flight_C"))
    return out


def touch_pad(name, dept):
    s = Screen(w=1024, h=640, dept=dept, title="", seed=hash(name) % 1000)
    for i in range(4):
        for j in range(3):
            x0, y0 = 30 + i * 246, 30 + j * 200
            s.rect(x0, y0, x0 + 226, y0 + 180, outline=DIM, fill=PANEL)
            s.brackets(x0, y0, x0 + 226, y0 + 180, c=s.acc)
            s.text(x0 + 113, y0 + 90, ["ALL STOP", "FULL", "HALF", "1/3", "PORT", "STBD", "UP", "DOWN", "HOLD", "EXEC", "CANCEL", "ACK"][i + j * 4],
                   F_LABEL(30), fill=TEXT, anchor="mm")
    return s.save(name)


def master_display():
    s = Screen(w=2048, h=864, dept="command", title="ASN Aquila · Master Systems Display", sub="CVC-01 · AQUILA CLASS · 780 M", seed=71)
    ship_silhouette(s, 120, 90, 1800, 560)
    for i, (k, v, c) in enumerate((("CONDITION", "GREEN", GREEN), ("CREW", "420 + 60 + 80", TEXT), ("REACTOR", "78 %", TEXT),
                                   ("SHIELDS", "100 %", CYAN), ("HULL", "100 %", TEXT), ("MISSION", "AURELIA DEFENSE PATROL", TEXT))):
        x = 120 + (i % 3) * 620
        y = 680 + (i // 3) * 70
        s.text(x, y, k, F_LABEL(26), fill=CYAN)
        s.text(x + 590, y + 2, v, F_MONO(24), fill=c, anchor="ra")
    return s.save("Master")


def holo_plot():
    """Top-down tactical plot for the holo table (square, transparent-looking: black = no emission)."""
    s = Screen(w=1024, h=1024, dept="command", title="", seed=81)
    s.img = Image.new("RGB", (1024 * S, 1024 * S), (0, 0, 0))
    s.d = ImageDraw.Draw(s.img)
    cx = cy = 512
    for k in range(1, 7):
        r = 470 * k / 6
        s.d.ellipse(s.P(cx - r, cy - r, cx + r, cy + r), outline=(30, 90, 150) if k < 6 else (80, 170, 255), width=S * (1 if k < 6 else 3))
    for a in range(0, 360, 15):
        r0 = 460 if a % 45 else 440
        s.line([(cx + r0 * math.cos(math.radians(a)), cy + r0 * math.sin(math.radians(a))),
                (cx + 470 * math.cos(math.radians(a)), cy + 470 * math.sin(math.radians(a)))], fill=(80, 170, 255), width=2)
    for x in range(cx - 460, cx + 461, 60):
        s.line([(x, cy - 5), (x, cy + 5)], fill=(40, 110, 180))
    icons = [(0, 0, "AQUILA", (120, 200, 255)), (-120, -60, "PRAETORIAN", (120, 200, 255)), (-180, 80, "VIGILANT", (120, 200, 255)),
             (260, -210, "T-11 UNKNOWN", (255, 179, 71)), (330, 150, "FREIGHTER", (220, 220, 220))]
    for (dx, dy, lab, col) in icons:
        x, y = cx + dx, cy + dy
        s.d.polygon([(x * S, (y - 12) * S), ((x - 9) * S, (y + 9) * S), ((x + 9) * S, (y + 9) * S)], outline=col, width=2 * S)
        s.text(x + 14, y - 10, lab, F_MONO(15), fill=col)
    s.d.ellipse(s.P(cx + 200, cy - 270, cx + 320, cy - 150), outline=(255, 179, 71), width=S)   # uncertainty ellipse
    return s.save("Holo")


def tactical_strip():
    s = Screen(w=2048, h=256, dept="security", title="", seed=91)
    s.d.rectangle(s.P(0, 0, 2048, 256), fill=BG)
    items = [("RAILGUN T1", "READY", GREEN), ("RAILGUN T2", "READY", GREEN), ("RAILGUN T3", "READY", GREEN), ("RAILGUN T4", "READY", GREEN),
             ("LASERS 12/12", "ONLINE", GREEN), ("VLS A", "48", CYAN), ("VLS B", "48", CYAN), ("TORPEDO", "2 LOADED", CYAN),
             ("PD 24/24", "AUTO", GREEN), ("SHIELDS", "FORE 100 · AFT 100", CYAN)]
    for i, (k, v, c) in enumerate(items):
        x = 20 + i * 202
        s.rect(x, 20, x + 190, 236, outline=DIM, fill=PANEL)
        s.text(x + 12, 40, k, F_LABEL(24), fill=TEXT)
        s.text(x + 12, 110, v, F_MONO(20), fill=c)
        s.d.rectangle(s.P(x + 12, 180, x + 178, 200), fill=c)
    return s.save("Tactical")


# ---------------------------------------------------------------- the Medbay (Deck 6)
TEAL = DEPT["medical"]
YELLOW = (240, 214, 90)


def _trace(s: Screen, x0, y0, w, h, kind, rate, color, rng, gap=0.62, width=2, irregular=0.0):
    """A monitor waveform sweeping left to right, the fresh part bright and a short blank gap where the sweep is."""
    pts = []
    beat = 1.0 / rate
    t = 0.0
    phase = rng.random()
    for i in range(int(w)):
        u = i / w
        t = u * 4.0 + phase                       # four seconds across the screen
        b = (t % beat) / beat
        if kind == "ecg":
            jit = 1.0 + irregular * math.sin(7.3 * math.floor(t / beat))
            b = min(1.0, b * jit)
            v = (0.12 * math.exp(-((b - 0.16) / 0.035) ** 2) - 0.14 * math.exp(-((b - 0.285) / 0.012) ** 2)
                 + 1.0 * math.exp(-((b - 0.305) / 0.012) ** 2) - 0.25 * math.exp(-((b - 0.33) / 0.013) ** 2)
                 + 0.28 * math.exp(-((b - 0.56) / 0.06) ** 2))
        elif kind == "pleth":
            v = 0.9 * math.exp(-((b - 0.25) / 0.09) ** 2) + 0.35 * math.exp(-((b - 0.5) / 0.08) ** 2) + 0.1
        else:   # respiration: slow, a sine that breathes
            v = 0.5 + 0.45 * math.sin(2 * math.pi * t / (beat * 1.0))
        pts.append((x0 + i, y0 + h * (0.78 - 0.62 * v)))
    cut = int(gap * len(pts))
    s.line(pts[:cut], fill=color, width=width)
    dim = tuple(int(c * 0.55) for c in color)
    if cut + 18 < len(pts):
        s.line(pts[cut + 18:], fill=dim, width=width)


def med_vitals(critical=False):
    """The bedside monitor of a patient: ECG, pleth, respiration; the numbers on the right (a critical patient: alarms)."""
    s = Screen(w=1024, h=640, dept="medical", seed=301 if not critical else 302)
    s.d.rectangle(s.P(0, 0, 1024, 640), fill=(2, 5, 8))
    s.d.rectangle(s.P(0, 0, 1024, 40), fill=(40, 6, 6) if critical else (5, 16, 18))
    s.text(18, 8, "PATIENT MONITOR", F_TITLE(24), fill=TEXT)
    s.text(1006, 12, "MEDBAY · DECK 6 · ASN AQUILA", F_MONO(14), fill=TEAL, anchor="ra")
    if critical:
        s.d.rectangle(s.P(360, 6, 700, 34), fill=(200, 30, 20))
        s.text(530, 8, "!! ALARM · HR HIGH · SPO2 LOW", F_MONO_B(17), fill=(255, 235, 225), anchor="ma")
    hr, spo2, rr = (131, 88, 26) if critical else (78, 97, 15)
    rows = [("II", "ecg", hr / 60.0, GREEN), ("PLETH", "pleth", hr / 60.0, CYAN), ("RESP", "resp", rr / 60.0, YELLOW)]
    for k, (lab, kind, rate, col) in enumerate(rows):
        y = 58 + k * 188
        s.text(16, y, lab, F_MONO(15), fill=col)
        s.line([(16, y + 176), (690, y + 176)], fill=(14, 30, 34))
        _trace(s, 16, y + 18, 674, 150, kind, rate, col, s.rng, gap=0.58 + 0.08 * k, width=3 if kind == "ecg" else 2,
               irregular=0.35 if (critical and kind == "ecg") else 0.0)
    s.line([(706, 50), (706, 620)], fill=(14, 30, 34), width=2)
    red = (255, 70, 50)
    nums = [("HR", "bpm", str(hr), red if critical else GREEN, 96), ("SpO2", "%", str(spo2), red if critical else CYAN, 84),
            ("NIBP", "mmHg", "86/50" if critical else "118/76", TEXT, 52), ("RR", "rpm", str(rr), AMBER if critical else YELLOW, 52),
            ("TEMP", "°C", "38.9" if critical else "37.2", AMBER if critical else TEXT, 44)]
    y = 54
    for lab, unit, val, col, size in nums:
        s.text(724, y, lab, F_LABEL(20), fill=col)
        s.text(1006, y + 4, unit, F_MONO(13), fill=DIM, anchor="ra")
        s.text(1006, y + 22, val, F_MONO_B(size), fill=col, anchor="ra")
        y += 30 + int(size * 1.15)
    s.footer("VENTILATED · SEDATED · ESCALATE TO SURGEON" if critical else "MONITORING · ALARMS ARMED", color=red if critical else GREEN)
    return s.save("Med_VitalsCritical" if critical else "Med_Vitals")


def med_standby():
    s = Screen(w=1024, h=640, dept="medical", seed=303)
    s.d.rectangle(s.P(0, 0, 1024, 640), fill=(2, 5, 8))
    cx, cy = 512, 260
    s.d.rectangle(s.P(cx - 22, cy - 70, cx + 22, cy + 70), fill=(14, 60, 58))     # the medical cross, dim
    s.d.rectangle(s.P(cx - 70, cy - 22, cx + 70, cy + 22), fill=(14, 60, 58))
    s.text(cx, 380, "BED READY", F_TITLE(46), fill=(60, 130, 125), anchor="ma")
    s.text(cx, 446, "MEDBAY · DECK 6 · SECTION C", F_MONO(18), fill=(30, 70, 70), anchor="ma")
    return s.save("Med_Standby")


def med_ward():
    """The ward's board on the central console: casualties by deck, triage, blood and supplies, the watch."""
    s = Screen(w=2048, h=640, dept="medical", title="Medbay · Ward Board", sub="DECK 6 · SECTION C · 12 BEDS · 1 THEATRE", seed=304)
    s.panel(24, 64, 700, 600, "Casualties by deck")
    for d in range(1, 13):
        y = 104 + (d - 1) * 40
        s.text(44, y, f"DECK {d:02d}", F_MONO(16), fill=TEXT)
        n = [0, 0, 1, 0, 2, 0, 1, 3, 1, 0, 2, 0][d - 1]
        for k in range(n):
            s.d.rectangle(s.P(160 + k * 34, y + 2, 188 + k * 34, y + 24), fill=[RED, AMBER, GREEN][(d + k) % 3])
        s.line([(160, y + 30), (680, y + 30)], fill=(16, 34, 44))
    s.panel(724, 64, 1324, 600, "Triage")
    for k, (lab, col, note) in enumerate((("CRITICAL", RED, "THEATRE / VENTILATOR"), ("SERIOUS", AMBER, "BEDSIDE CARE"),
                                          ("STABLE", GREEN, "OBSERVATION"), ("RETURNED TO DUTY", CYAN, "CLEARED BY CMO"))):
        y = 110 + k * 116
        s.d.rectangle(s.P(748, y, 764, y + 76), fill=col)
        s.text(784, y + 2, lab, F_TITLE(34), fill=TEXT)
        s.text(784, y + 48, note, F_MONO(15), fill=DIM)
    s.panel(1348, 64, 2024, 600, "Blood · supplies · watch")
    items = [("WHOLE BLOOD O-", 0.62), ("PLASMA", 0.8), ("SYNTH-SKIN (BURNS)", 0.41), ("NANO-SUTURE", 0.73), ("ANALGESIA", 0.55),
             ("OXYGEN", 0.9)]
    for k, (lab, f) in enumerate(items):
        s.bar(1372, 108 + k * 70, 628, 16, f, lab, f"{int(f * 100)} %", color=TEAL, warn=2, crit=2)
    s.text(1372, 540, "ON WATCH  CMO LINDQVIST · 3 NURSES · 2 MEDICS", F_MONO(16), fill=TEAL)
    s.footer("THEATRE READY · STERILE FIELD OK", color=GREEN)
    return s.save("Med_Ward")


def med_scan():
    """The diagnostic scanner's display: a body in outline, the scan band, findings."""
    s = Screen(w=1024, h=640, dept="medical", title="Diagnostic Scanner", sub="FULL BODY · TOMOGRAPHIC", seed=305)
    cx = 300
    # a body in outline (front view): the right half from the neck down to the crotch, mirrored
    half = [(16, 150), (18, 168), (60, 180), (84, 196), (96, 230), (104, 300), (110, 360), (118, 420), (122, 446),
            (116, 470), (102, 452), (96, 420), (88, 360), (80, 300), (72, 250), (66, 238), (64, 280), (58, 330), (64, 380),
            (68, 410), (62, 470), (54, 530), (48, 580), (52, 600), (22, 600), (24, 580), (22, 520), (14, 450), (0, 424)]
    outline = [(cx + x, y) for x, y in half] + [(cx - x, y) for x, y in reversed(half[:-1])]
    s.d.polygon([(x * S, y * S) for x, y in outline], fill=(6, 34, 36), outline=TEAL)
    s.line(outline + [outline[0]], fill=TEAL, width=2)
    s.d.ellipse(s.P(cx - 34, 74, cx + 34, 150), fill=(6, 34, 36), outline=TEAL, width=2 * S)             # the head
    s.line([(cx, 170), (cx, 410)], fill=(20, 110, 105), width=2)                                          # the spine
    for k in range(6):                                                                                    # the ribs
        y = 206 + k * 18
        s.d.arc(s.P(cx - 52 + k * 2, y - 12, cx + 52 - k * 2, y + 26), 200, 340, fill=(20, 110, 105), width=S)
    s.d.rectangle(s.P(cx - 150, 262, cx + 150, 268), fill=(40, 180, 170))                             # the scan band
    s.d.ellipse(s.P(cx + 18, 214, cx + 50, 246), outline=AMBER, width=3 * S)                          # a finding
    s.d.ellipse(s.P(cx - 116, 356, cx - 88, 384), outline=AMBER, width=3 * S)
    s.panel(560, 64, 1004, 600, "Findings")
    for k, (lab, val, col) in enumerate((("SKELETAL", "2 FRACTURES", AMBER), ("THORAX", "CONTUSION · NO PNEUMO", AMBER),
                                          ("CRANIAL", "NO BLEED", GREEN), ("BURNS", "12 % TBSA", AMBER), ("TOXICOLOGY", "CO 9 %", AMBER),
                                          ("IMPLANT", "INTERPRETER OK", GREEN))):
        y = 108 + k * 78
        s.text(584, y, lab, F_LABEL(20), fill=TEXT)
        s.text(984, y + 28, val, F_MONO(17), fill=col, anchor="ra")
        s.line([(584, y + 62), (984, y + 62)], fill=(16, 34, 44))
    s.footer("SCAN 3 OF 3 · REVIEW BY SURGEON", color=TEAL)
    return s.save("Med_Scan")


# ---------------------------------------------------------------- the Captain's quarters (Deck 1)
def _war_data():
    """The Aurelia March from the mind's war map (mind/astra_mind/war.py: stdlib only)."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("astra_war", os.path.join(ROOT, "mind", "astra_mind", "war.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.SECTOR, mod.LINKS


def quarters_map():
    """A chart of the Aurelia March on the cabin wall: the systems, their gates, who holds them (as the war began)."""
    systems, links = _war_data()
    s = Screen(w=2048, h=1024, dept="command", title="The Aurelia March", sub="7TH FLEET · STRATEGIC CHART · ASN AQUILA", seed=401)
    xs = [d["x"] for d in systems]
    ys = [d["y"] for d in systems]
    x0, x1, y0, y1 = min(xs) - 6, max(xs) + 6, min(ys) - 6, max(ys) + 6
    P = lambda d: (80 + (d["x"] - x0) / (x1 - x0) * 1888, 1000 - (d["y"] - y0) / (y1 - y0) * 900)   # noqa: E731
    pos = {d["name"]: P(d) for d in systems}
    colour = {"astra": (80, 160, 255), "mandate": (230, 70, 55), "guilds": (240, 180, 70), "silent": (130, 140, 150)}
    for a, b in links:
        s.line([pos[a], pos[b]], fill=(40, 75, 110), width=3)
    for d in systems:
        x, y = pos[d["name"]]
        c = colour.get(d["owner"], TEXT)
        r = 16 if d["name"] in ("Aurelia", "Concordia", "Kharon") else 11
        s.d.ellipse(s.P(x - r - 8, y - r - 8, x + r + 8, y + r + 8), outline=tuple(v // 3 for v in c), width=2 * S)
        s.d.ellipse(s.P(x - r, y - r, x + r, y + r), fill=c)
        s.text(x, y + r + 12, d["name"].upper(), F_TITLE(30), fill=TEXT, anchor="ma")
        s.text(x, y + r + 48, d["world"], F_MONO(16), fill=DIM, anchor="ma")
    ax, ay = pos["Aurelia"]
    s.d.ellipse(s.P(ax - 44, ay - 44, ax + 44, ay + 44), outline=CYAN, width=2 * S)
    s.text(ax + 50, ay - 60, "ASN AQUILA", F_MONO_B(18), fill=CYAN)
    for i, (lab, own) in enumerate((("ASTRA", "astra"), ("KHARON MANDATE", "mandate"), ("FREE GUILDS", "guilds"), ("SILENT", "silent"))):
        x = 90 + i * 260
        s.d.ellipse(s.P(x, 70, x + 18, 88), fill=colour[own])
        s.text(x + 30, 66, lab, F_LABEL(20), fill=TEXT)
    s.footer("JANUS GATE LINKS · POSITIONS NOT TO SCALE", color=DIM)
    return s.save("Quarters_Map")


def quarters_log():
    """The desk terminal: the Captain's log, ready to take a voice entry."""
    s = Screen(w=1024, h=640, dept="command", title="Captain's Log", sub="ASN AQUILA · CVC-01 · PRIVATE", seed=402)
    s.panel(24, 64, 1000, 170, "Voice entry")
    s.text(44, 108, "SAY  \"CAPTAIN'S LOG\"  TO BEGIN", F_MONO_B(26), fill=TEXT)
    for i in range(46):   # a quiet waveform, waiting
        h = 4 + 10 * abs(math.sin(i * 0.7)) * (0.3 + 0.7 * s.rng.random())
        s.d.rectangle(s.P(560 + i * 9, 132 - h, 565 + i * 9, 132 + h), fill=(40, 110, 160))
    s.panel(24, 190, 1000, 600, "Entries")
    for k in range(6):
        y = 236 + k * 60
        s.text(44, y, f"2491.{265 + k:03d}", F_MONO(16), fill=CYAN)
        for j, w in enumerate((0.9, 0.62)):
            s.d.rectangle(s.P(180, y + 4 + j * 22, 180 + int(780 * w * (0.7 + 0.3 * s.rng.random())), y + 12 + j * 22), fill=(28, 52, 80))
    s.footer("ENCRYPTED · CAPTAIN'S EYES ONLY", color=DIM)
    return s.save("Quarters_Log")


def mess_menu():
    """The galley's board over the pass: what is served today (the war has not reached the coffee yet)."""
    s = Screen(w=2048, h=264, dept="command", title="Galley · Deck 4", sub="TODAY · WATCH ROTATION 2", seed=501)
    items = (("BRAISED LAMB WITH BARLEY", "from New Ravenna's hills"), ("AURELIAN RICE", "saffron, peppers"),
             ("GREENS", "hydroponics bay B"), ("COFFEE", "real beans, from Meridian"))
    for i, (dish, note) in enumerate(items):
        x = 40 + i * 500
        s.text(x, 118, dish, F_TITLE(40), fill=TEXT)
        s.text(x, 172, note, F_MONO(20), fill=DIM)
        if i:
            s.d.rectangle(s.P(x - 22, 112, x - 19, 216), fill=(28, 52, 80))
    return s.save("Mess_Menu")


def mess_placeholder(name: str, title: str, sub: str):
    """What the mess's big screens show before the ship draws them live (AstraScreensSubsystem)."""
    s = Screen(w=1024, h=320, dept="command", title=title, sub=sub, seed=502)
    s.footer("STANDBY", color=DIM)
    return s.save(name)


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["mess"]:
        print("UI_OK", [mess_menu(), mess_placeholder("Mess_News", "Fleet News", "7TH FLEET NET · AURELIA MARCH"),
                        mess_placeholder("Mess_Memorial", "In Memoriam", "ASN AQUILA · CVC-01")])
        raise SystemExit
    if sys.argv[1:] == ["med"]:   # only the Medbay's screens
        print("UI_OK", [med_vitals(), med_vitals(critical=True), med_standby(), med_ward(), med_scan()])
        raise SystemExit
    if sys.argv[1:] == ["quarters"]:
        print("UI_OK", [quarters_map(), quarters_log()])
        raise SystemExit
    made = []
    made += helm() + ops() + comms() + sensors() + engineering() + flight()
    for st, dept in (("Helm", "command"), ("Ops", "command"), ("Comms", "command"), ("Sensors", "science"), ("Eng", "engineering"),
                     ("Flight", "flight")):
        made.append(touch_pad(f"{st}_Touch", dept))
    made += [master_display(), holo_plot(), tactical_strip()]
    made += [med_vitals(), med_vitals(critical=True), med_standby(), med_ward(), med_scan()]
    made += [quarters_map(), quarters_log()]
    made += [mess_menu(), mess_placeholder("Mess_News", "Fleet News", "7TH FLEET NET · AURELIA MARCH"),
             mess_placeholder("Mess_Memorial", "In Memoriam", "ASN AQUILA · CVC-01")]
    print("UI_OK", len(made), made)
