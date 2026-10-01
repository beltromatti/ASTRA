"""The decor atlas of the bridge (ARTE-PLANCIA-2): static display pages for the screens nobody plays on, and the soft glows round the
ones everybody does. Output (art/_cache/bridge3/, gitignored, reproducible with this script):

  T_BRG3_Decor.png  2048 x 4096 RGB, emissive content on near-black (the instance MI_BRG3_Decor is a M_ASTRA_Screen: ScreenTexture x Intensity)
  decor.json        the rect of every tile: {"rects": {name: [u0, v0, u1, v1]}, "px": {name: [x, y, w, h]}, "aspect": {name: w / h}}

Pages (landscape 16:10 unless noted): ship, starmap, orbit, log, hex, rings, waterfall, matrix, schematic, gauges; wide: wave, bars, ticker;
portrait: decks, atmo, equalizer, checklist; squares: radar, attitude, compass; the cockpit's: caution, engine, weapons, navmfd;
glows: glow_<department> (a soft rounded rectangle, bright in the middle and nothing at the border: it is laid on a wall behind a screen).

The style is the one of the live pages (tools/art/ui_screens.py): navy glass, thin lines, light-blue text (Barlow Condensed titles, IBM Plex Mono
data), amber for engineering, violet for science, red for trouble. Everything is English. Run (also called by bridge3_textures.py):
  uv run --python /opt/homebrew/bin/python3.13 --with pillow --with numpy python tools/art/bridge3_decor.py
"""
from __future__ import annotations

import json
import math
import os
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OUT = os.path.join(ROOT, "art", "_cache", "bridge3")
FONTS = [os.path.join(ROOT, "art", "_downloads", "fonts"), "/Users/beltromatti/Desktop/ASTRA/art/_downloads/fonts"]

BG = (3, 7, 14)
PANEL = (7, 15, 28)
GRID = (14, 34, 58)
CY = (72, 172, 255)
ICE = (190, 225, 255)
DIM = (74, 106, 140)
AMB = (255, 159, 28)
RED = (236, 62, 70)
GRN = (84, 224, 150)
VIO = (160, 100, 235)
YEL = (255, 214, 10)
TEAL = (46, 196, 182)
WHT = (240, 247, 255)
DEPT = {"command": (62, 123, 250), "engineering": AMB, "flight": YEL, "science": VIO, "security": RED, "medical": TEAL}
S = 2                                   # supersampling of every page


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for d in FONTS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, int(size * S))
    raise FileNotFoundError(name)


def title_f(size: int) -> ImageFont.FreeTypeFont:
    return font("BarlowCondensed-SemiBold.ttf", size)


def mono_f(size: int) -> ImageFont.FreeTypeFont:
    return font("IBMPlexMono-Medium.ttf", size)


class Page:
    """A drawing surface w x h px (drawn at S times that size); `glow` is a second layer that is blurred and added at the end (bloom)."""

    def __init__(self, w: int, h: int, bg=BG) -> None:
        self.w, self.h = w, h
        self.img = Image.new("RGB", (w * S, h * S), bg)
        self.d = ImageDraw.Draw(self.img)
        self.gl = Image.new("RGB", (w * S, h * S), (0, 0, 0))
        self.g = ImageDraw.Draw(self.gl)

    # -- primitives (coordinates in output pixels) --------------------------------------------------------------------------
    @staticmethod
    def _s(pts):
        return [(x * S, y * S) for x, y in pts]

    def line(self, pts, col, w: float = 1.0, glow: float = 0.0) -> None:
        self.d.line(self._s(pts), fill=col, width=max(1, int(round(w * S))), joint="curve")
        if glow > 0:
            self.g.line(self._s(pts), fill=tuple(int(c * glow) for c in col), width=max(1, int(round(w * S * 2))), joint="curve")

    def rect(self, x0, y0, x1, y1, fill=None, outline=None, w: float = 1.0, glow: float = 0.0) -> None:
        box = (x0 * S, y0 * S, x1 * S, y1 * S)
        self.d.rectangle(box, fill=fill, outline=outline, width=max(1, int(round(w * S))))
        if glow > 0 and (outline or fill):
            self.g.rectangle(box, fill=None if fill is None else tuple(int(c * glow * 0.5) for c in fill),
                             outline=tuple(int(c * glow) for c in (outline or fill)), width=max(1, int(round(w * S * 2))))

    def ellipse(self, cx, cy, rx, ry, fill=None, outline=None, w: float = 1.0, glow: float = 0.0) -> None:
        box = ((cx - rx) * S, (cy - ry) * S, (cx + rx) * S, (cy + ry) * S)
        self.d.ellipse(box, fill=fill, outline=outline, width=max(1, int(round(w * S))))
        if glow > 0 and (outline or fill):
            self.g.ellipse(box, fill=None if fill is None else tuple(int(c * glow * 0.5) for c in fill),
                           outline=tuple(int(c * glow) for c in (outline or fill)), width=max(1, int(round(w * S * 2))))

    def poly(self, pts, fill=None, outline=None, w: float = 1.0, glow: float = 0.0) -> None:
        if fill is not None:
            self.d.polygon(self._s(pts), fill=fill)
        if outline is not None:
            self.d.line(self._s(list(pts) + [pts[0]]), fill=outline, width=max(1, int(round(w * S))), joint="curve")
            if glow > 0:
                self.g.line(self._s(list(pts) + [pts[0]]), fill=tuple(int(c * glow) for c in outline), width=max(1, int(round(w * S * 2))), joint="curve")

    def arc(self, cx, cy, r, a0, a1, col, w: float = 1.0, glow: float = 0.0) -> None:
        box = ((cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S)
        self.d.arc(box, a0, a1, fill=col, width=max(1, int(round(w * S))))
        if glow > 0:
            self.g.arc(box, a0, a1, fill=tuple(int(c * glow) for c in col), width=max(1, int(round(w * S * 2))))

    def text(self, x, y, s: str, f, col=ICE, anchor="la", glow: float = 0.0) -> None:
        self.d.text((x * S, y * S), s, font=f, fill=col, anchor=anchor)
        if glow > 0:
            self.g.text((x * S, y * S), s, font=f, fill=tuple(int(c * glow) for c in col), anchor=anchor)

    def dot(self, x, y, r, col, glow: float = 0.6) -> None:
        self.ellipse(x, y, r, r, fill=col, glow=glow)

    # -- the chrome of a page -------------------------------------------------------------------------------------------------
    def frame(self, title: str, sub: str = "ASN AQUILA · CVC-01", accent=CY, footer: str | None = None) -> None:
        """Header strip with the title, a hairline border, an optional footer line: the same chrome as the live pages."""
        w, h = self.w, self.h
        self.rect(0, 0, w - 1, h - 1, outline=(22, 46, 76), w=1.2)
        self.rect(0, 0, 7, 26, fill=accent)
        size = max(11, int(h * 0.072))
        sub_w = 0 if w < 300 else 150
        tf = title_f(size)
        while self.d.textlength(title, font=tf) / S > w - 28 - sub_w and size > 9:
            size -= 1
            tf = title_f(size)
        self.text(16, 13, title, tf, ICE, "lm", glow=0.35)
        if w >= 300:
            self.text(w - 10, 13, sub, mono_f(max(7, int(h * 0.026))), DIM, "rm")
        self.line([(0, 27), (w, 27)], accent, 1.0, glow=0.5)
        if footer:
            self.line([(0, h - 19), (w, h - 19)], (22, 46, 76), 1.0)
            self.text(10, h - 9, footer, mono_f(max(7, int(h * 0.026))), DIM, "lm")

    def grid(self, x0, y0, x1, y1, step: float, col=GRID, w: float = 0.6) -> None:
        x = x0
        while x <= x1 + 0.01:
            self.line([(x, y0), (x, y1)], col, w)
            x += step
        y = y0
        while y <= y1 + 0.01:
            self.line([(x0, y), (x1, y)], col, w)
            y += step

    def done(self, bloom: float = 1.0) -> Image.Image:
        base = self.img
        if bloom > 0:
            g1 = self.gl.filter(ImageFilter.GaussianBlur(2.2 * S))
            g2 = self.gl.filter(ImageFilter.GaussianBlur(0.8 * S))
            base = ImageChops.add(base, g1.point(lambda v: int(v * 1.2 * bloom)))
            base = ImageChops.add(base, g2.point(lambda v: int(v * 0.6 * bloom)))
        return base.resize((self.w, self.h), Image.LANCZOS)


# ================================================================================================== the consoles' glass tops
class Polar:
    """A tile that is wrapped onto a console's conical work surface: u = the angle (th_deg from -a to +a, to the officer's right), v = the radius
    (r from r0 at the bottom edge, next to the officer, to r1 at the top edge). Everything is drawn in metres on the surface (polar-aware): the
    result on the glass is the undistorted drawing (rings stay circular, text keeps its proportions, it runs along the arcs)."""

    def __init__(self, w: int, h: int, a: float, r0: float, r1: float) -> None:
        self.p = Page(w, h, bg=(0, 0, 0))
        self.w, self.h, self.a, self.r0, self.r1 = w, h, a, r0, r1

    def xy(self, th_deg: float, r: float):
        return ((th_deg + self.a) / (2 * self.a) * self.w, (1.0 - (r - self.r0) / (self.r1 - self.r0)) * self.h)

    def ppm_u(self, r: float) -> float:
        return self.w / (math.radians(2 * self.a) * r)

    def ppm_v(self) -> float:
        return self.h / (self.r1 - self.r0)

    def arc_line(self, r: float, th0: float, th1: float, col, w: float = 1.0, glow: float = 0.0) -> None:
        self.p.line([self.xy(th0, r), self.xy(th1, r)], col, w, glow=glow)

    def ray(self, th: float, r0: float, r1: float, col, w: float = 1.0, glow: float = 0.0) -> None:
        self.p.line([self.xy(th, r0), self.xy(th, r1)], col, w, glow=glow)

    def ring(self, r_c: float, th_c: float, rad: float, col, w: float = 1.0, glow: float = 0.0, n: int = 40) -> None:
        """A circle of radius `rad` metres round the point (r_c, th_c) on the surface."""
        cx, cy = r_c * math.cos(math.radians(th_c)), r_c * math.sin(math.radians(th_c))
        pts = []
        for k in range(n + 1):
            t = 2 * math.pi * k / n
            x, y = cx + rad * math.cos(t), cy + rad * math.sin(t)
            pts.append(self.xy(math.degrees(math.atan2(y, x)), math.hypot(x, y)))
        self.p.line(pts, col, w, glow=glow)

    def box(self, r_c: float, th_c: float, w_m: float, h_m: float, col, w: float = 1.0, glow: float = 0.0, corner: float = 0.0) -> None:
        """A rectangle w_m (along the arc) x h_m (radial) centred on (r_c, th_c), its sides aligned with the local radial frame; with `corner`
        only the corner brackets of that length (metres) are drawn."""
        t = math.radians(th_c)
        ex, ey = (-math.sin(t), math.cos(t))                    # along the arc (to the officer's right)
        rx, ry = (math.cos(t), math.sin(t))                     # radially out
        cx, cy = r_c * rx, r_c * ry

        def pt(su, sv):
            x, y = cx + ex * su * w_m / 2 + rx * sv * h_m / 2, cy + ey * su * w_m / 2 + ry * sv * h_m / 2
            return self.xy(math.degrees(math.atan2(y, x)), math.hypot(x, y))

        if corner <= 0:
            self.p.line([pt(-1, -1), pt(1, -1), pt(1, 1), pt(-1, 1), pt(-1, -1)], col, w, glow=glow)
        else:
            for sx in (-1, 1):
                for sy in (-1, 1):
                    kx, ky = corner / (w_m / 2), corner / (h_m / 2)
                    self.p.line([pt(sx, sy * (1 - ky)), pt(sx, sy), pt(sx * (1 - kx), sy)], col, w, glow=glow)

    def text(self, s: str, r_c: float, th_c: float, cap_m: float, col, mono: bool = True, glow: float = 0.0) -> None:
        f = (mono_f if mono else title_f)(24)
        tmp = Image.new("L", (int(len(s) * 30 * S) + 8, int(40 * S)), 0)
        ImageDraw.Draw(tmp).text((4, 4), s, font=f, fill=255)
        bb = tmp.getbbox()
        if not bb:
            return
        tmp = tmp.crop(bb)
        tw = max(2, int(round((tmp.width / tmp.height) * cap_m * self.ppm_u(r_c))) * S)
        th = max(2, int(round(cap_m * self.ppm_v())) * S)
        tmp = tmp.resize((tw, th), Image.LANCZOS)
        x, y = self.xy(th_c, r_c)
        layer = Image.new("RGB", tmp.size, col)
        self.p.img.paste(layer, (int(x * S - tw / 2), int(y * S - th / 2)), tmp)
        if glow > 0:
            self.p.gl.paste(tuple(int(c * glow) for c in col), (int(x * S - tw / 2), int(y * S - th / 2)), tmp)

    def done(self) -> Image.Image:
        return self.p.done(bloom=0.6)


FAN_LABELS = {"command": ["NAV", "TRIM", "SYS", "DATA", "LINK"], "engineering": ["PWR", "COOL", "BUS A", "BUS B", "RAD"], "science": ["SCAN", "SPEC", "ARRAY", "LOG", "CAL"],
              "flight": ["LAUNCH", "RECOVER", "DECK", "FUEL", "WING"], "security": ["ARM", "TRACK", "SHLD", "PD", "ORD"]}


def page_fan(dept: str, seed: int, a: float = 58.0, r0: float = 0.50, r1: float = 1.08, w: int = 1024, h: int = 352) -> Image.Image:
    """The silkscreen of a fan console's glass top in the colour of its department: a border, hairline rings and rays that split the surface into
    zones (a few of them dashed), a tick scale along the edge next to the officer, bracketed boxes where key banks sit, zone names."""
    col = DEPT[dept]
    dim = tuple(int(c * 0.30) for c in col)
    mid = tuple(int(c * 0.55) for c in col)
    rng = random.Random(seed)
    P = Polar(w, h, a, r0, r1)
    rr = lambda r: min(max(r, r0 + 0.004), r1 - 0.004)
    P.arc_line(rr(0.515), -a + 1.5, a - 1.5, mid, 1.2, glow=0.4)
    P.arc_line(rr(1.065), -a + 1.5, a - 1.5, mid, 1.2, glow=0.4)
    for k, r in enumerate((0.60, 0.68, 0.76, 0.84, 0.92, 1.0)):                  # rings, broken into dashes
        th = -a + 3.0
        while th < a - 3.0:
            seg = rng.uniform(6.0, 22.0)
            if rng.random() < 0.72:
                P.arc_line(r, th, min(th + seg, a - 3.0), dim, 0.9)
            th += seg + rng.uniform(1.5, 5.0)
    for th in (-46, -34, -22, -10, 10, 22, 34, 46):                               # rays between the zones
        if abs(th) >= a - 2:
            continue
        r_a = rng.choice([0.56, 0.60, 0.64])
        r_b = rng.choice([0.94, 1.0, 1.04])
        P.ray(th, r_a, r_b, dim, 0.9)
    for k in range(int(2 * (a - 3) / 2.0) + 1):                                     # the scale next to the officer
        th = -(a - 3.0) + 2.0 * k
        big = (round(th + a) % 10 == 0) or (round(th) % 10 == 0)
        P.ray(th, 0.525, 0.525 + (0.024 if big else 0.012), mid if big else dim, 0.9 if big else 0.7)
    for (th, r, bw, bh) in ((-40, 0.72, 0.30, 0.17), (40, 0.72, 0.30, 0.17), (-36, 0.93, 0.26, 0.10), (36, 0.93, 0.26, 0.10), (0, 0.585, 0.46, 0.06)):
        if abs(th) < a - 8:
            P.box(r, th, bw, bh, mid, 1.0, glow=0.3, corner=0.035)
    for th in (-30, -14, 14, 30):                                                   # small marks
        P.ring(0.80, th, 0.012, mid, 0.9)
    labs = FAN_LABELS[dept]
    for k, name in enumerate(labs):
        th = -a * 0.72 + k * (a * 1.44) / (len(labs) - 1)
        P.text(name, 1.035, th, 0.0095, mid, mono=True, glow=0.3)
    return P.done()


# ============================================================================================================== landscape pages
def page_ship(w=512, h=320) -> Image.Image:
    p = Page(w, h)
    p.frame("ASN AQUILA · HULL INTEGRITY", accent=DEPT["command"], footer="SECTIONS A-H  |  ALL WATERTIGHT DOORS SECURE")
    # the hull in profile (bow to the right), a spine, the bridge island, the engines at the stern
    cy = 150
    hull = [(26, cy + 6), (70, cy - 10), (150, cy - 20), (300, cy - 22), (396, cy - 18), (454, cy - 7), (488, cy + 2), (454, cy + 12), (396, cy + 22), (300, cy + 26),
            (150, cy + 24), (70, cy + 16)]
    p.poly(hull, fill=(8, 22, 40), outline=CY, w=1.3, glow=0.7)
    p.poly([(300, cy - 22), (318, cy - 40), (372, cy - 44), (392, cy - 32), (396, cy - 18)], fill=(10, 28, 50), outline=CY, w=1.1, glow=0.5)
    for k in range(12):                                                    # deck lines
        y = cy - 20 + k * 3.8
        p.line([(80, y), (452, y)], (16, 40, 68), 0.5)
    stat = [GRN, GRN, GRN, GRN, GRN, AMB, GRN, GRN]
    xs = [26 + k * (488 - 26) / 8 for k in range(9)]
    for k in range(8):                                                     # sections A..H from the stern
        p.line([(xs[k], cy - 34), (xs[k], cy + 34)], (30, 60, 96), 0.8)
        p.rect(xs[k] + 5, cy + 36, xs[k + 1] - 5, cy + 44, fill=tuple(int(c * 0.55) for c in stat[k]), outline=stat[k], w=0.8, glow=0.4)
        p.text((xs[k] + xs[k + 1]) / 2, cy + 54, "ABCDEFGH"[k], title_f(15), ICE, "mm")
    for (x, y, c) in ((338, cy - 3, AMB), (190, cy + 4, GRN), (420, cy, GRN)):    # a few markers
        p.dot(x, y, 3.2, c)
    for k in range(3):                                                     # engines
        p.rect(14, cy - 2 + k * 8 - 8, 28, cy + 2 + k * 8 - 8, fill=(255, 140, 40), glow=0.9)
    # integrity bars
    names = ["HULL", "SHIELDS", "ARMOUR", "SYSTEMS"]
    vals = [0.97, 0.88, 0.94, 0.91]
    for k, (n, v) in enumerate(zip(names, vals)):
        y = 222 + k * 20
        p.text(24, y, n, title_f(13), DIM, "lm")
        p.rect(92, y - 5, 300, y + 5, outline=(30, 60, 96), w=1)
        for j in range(int(v * 28)):
            x = 94 + j * 7.3
            p.rect(x, y - 3.2, x + 5.2, y + 3.2, fill=(CY if v > 0.9 else AMB))
        p.text(312, y, f"{int(v * 100)} %", mono_f(11), ICE, "lm")
    p.text(432, 236, "CONDITION", mono_f(9), DIM, "mm")
    p.text(432, 262, "GREEN", title_f(30), GRN, "mm", glow=0.5)
    return p.done()


def page_starmap(w=512, h=320) -> Image.Image:
    p = Page(w, h)
    p.frame("SECTOR AURELIA · NAV CHART", accent=DEPT["science"], footer="GRID 12 LY  |  PLOT: AURELIA > JANUS GATE")
    rng = random.Random(11)
    p.grid(14, 36, w - 14, h - 28, 40, GRID, 0.5)
    stars = []
    for _ in range(190):
        x, y = rng.uniform(16, w - 16), rng.uniform(38, h - 30)
        r = rng.choice([0.7, 0.7, 0.9, 1.2, 1.7])
        c = rng.choice([ICE, ICE, (255, 220, 170), CY])
        p.dot(x, y, r, tuple(int(v * rng.uniform(0.35, 0.9)) for v in c), 0.3 if r > 1 else 0)
        stars.append((x, y))
    named = [(104, 108, "AURELIA", AMB), (214, 198, "NEW RAVENNA", CY), (330, 126, "JANUS GATE", VIO), (426, 214, "KHARON", RED), (160, 262, "ORPHEUS", DIM)]
    route = [(104, 108), (150, 150), (214, 198), (270, 170), (330, 126)]
    p.line(route, CY, 1.4, glow=0.8)
    for k in range(len(route) - 1):                                         # dashes
        (x0, y0), (x1, y1) = route[k], route[k + 1]
        p.dot((x0 + x1) / 2, (y0 + y1) / 2, 1.6, WHT)
    for (x, y, n, c) in named:
        p.ellipse(x, y, 7, 7, outline=c, w=1.2, glow=0.8)
        p.dot(x, y, 2.3, c)
        p.text(x + 11, y - 1, n, title_f(13), c, "lm", glow=0.4)
    for a, b in ((0, 1), (1, 3), (3, 4), (2, 3)):                          # constellation hairlines
        p.line([named[a][:2], named[b][:2]], (36, 66, 104), 0.8)
    p.rect(w - 112, h - 54, w - 18, h - 34, outline=(30, 60, 96), w=1)
    p.line([(w - 106, h - 40), (w - 66, h - 40)], ICE, 1.2)
    p.text(w - 60, h - 44, "4 LY", mono_f(9), ICE, "lm")
    return p.done()


def page_orbit(w=512, h=320) -> Image.Image:
    p = Page(w, h)
    p.frame("NEW RAVENNA · ORBITAL PLOT", accent=DEPT["command"], footer="ALT 412 KM  |  INC 31.4  |  PERIOD 94 MIN")
    cx, cy = 152, 176
    arr = np.zeros((h * S, w * S, 3), np.float32)
    yy, xx = np.mgrid[0:h * S, 0:w * S].astype(np.float32)
    rr = np.sqrt(((xx / S - cx) ** 2 + (yy / S - cy) ** 2)) / 78.0
    inside = rr < 1.0
    nz = np.sqrt(np.clip(1 - rr * rr, 0, 1))
    light = np.clip(0.18 + 1.1 * (-(xx / S - cx) / 78.0 * 0.55 + (-(yy / S - cy) / 78.0) * 0.35 + nz * 0.6), 0, 1)
    rng = np.random.default_rng(5)
    noise = rng.random((h * S // 16 + 2, w * S // 16 + 2)).astype(np.float32)
    noise = np.asarray(Image.fromarray((noise * 255).astype(np.uint8)).resize((w * S + 32, h * S + 32), Image.BICUBIC), np.float32)[:h * S, :w * S] / 255.0
    noise2 = rng.random((h * S // 5 + 2, w * S // 5 + 2)).astype(np.float32)
    noise2 = np.asarray(Image.fromarray((noise2 * 255).astype(np.uint8)).resize((w * S + 20, h * S + 20), Image.BICUBIC), np.float32)[:h * S, :w * S] / 255.0
    land = np.clip((noise * 0.7 + noise2 * 0.3 - 0.5) * 9.0, 0, 1)
    col = np.stack([0.05 + 0.15 * land, 0.22 + 0.2 * land, 0.5 - 0.2 * land], axis=-1) * light[..., None] * 255
    arr[inside] = col[inside]
    p.img = Image.fromarray(np.clip(arr + np.array(BG, np.float32), 0, 255).astype(np.uint8), "RGB")
    p.d = ImageDraw.Draw(p.img)
    p.frame("NEW RAVENNA · ORBITAL PLOT", accent=DEPT["command"], footer="ALT 412 KM  |  INC 31.4  |  PERIOD 94 MIN")
    p.ellipse(cx, cy, 79, 79, outline=(80, 150, 230), w=1.1, glow=0.9)
    for (rx, ry, tilt) in ((104, 40, -22), (150, 66, -22), (212, 108, -22)):
        pts = []
        for k in range(90):
            a = 2 * math.pi * k / 90
            x, y = rx * math.cos(a), ry * math.sin(a)
            t = math.radians(tilt)
            pts.append((cx + x * math.cos(t) - y * math.sin(t), cy + x * math.sin(t) + y * math.cos(t)))
        p.line(pts + [pts[0]], (40, 82, 130), 0.9)
    mk = [(268, 100, "ASN AQUILA", CY), (330, 238, "7TH FLEET", GRN), (402, 148, "RELAY 3", DIM), (222, 258, "WATCH STN", GRN)]
    for (x, y, n, c) in mk:
        p.poly([(x, y - 7), (x + 6, y + 5), (x - 6, y + 5)], outline=c, w=1.3, glow=0.8)
        p.text(x + 10, y, n, title_f(12), c, "lm")
    p.line([(268, 100), (330, 238)], (50, 100, 150), 0.7)
    p.text(w - 12, 46, "AURELIA STAR", mono_f(9), AMB, "rm")
    p.dot(w - 24, 66, 5, AMB, 1.0)
    return p.done()


def page_log(w=512, h=320) -> Image.Image:
    p = Page(w, h)
    p.frame("CVC-01 · EVENT LOG", accent=DEPT["command"], footer="2491.271  |  SHIP TIME 03:38")
    lines = [("03:31:07", "HELM", "COURSE 077 MARK 3 CONFIRMED", CY), ("03:32:40", "SENS", "NEW CONTACT T-14 BEARING 112", AMB), ("03:32:44", "TACT", "T-14 CLASSIFIED: UNKNOWN", AMB),
             ("03:33:02", "COMM", "FLEET NET: ACKNOWLEDGED", CY), ("03:33:51", "OPS ", "DECK 6 SQUAD 4 REPAIRS COMPLETE", GRN), ("03:34:18", "ENG ", "REACTOR OUTPUT 78 PERCENT", CY),
             ("03:34:55", "FLT ", "ALPHA SQN READY ON CATAPULT", GRN), ("03:35:12", "TACT", "SHIELDS BALANCED 100 PERCENT", CY), ("03:36:29", "SENS", "T-14 IDENTIFIED: FRIENDLY (CONSTANCE)", GRN),
             ("03:37:03", "HELM", "HOLD STATION 2.8 KM", CY), ("03:37:40", "OPS ", "VIEWSCREEN: TARGET AUTO", CY), ("03:38:01", "XO  ", "CONDITION GREEN, ALL STATIONS", GRN),
             ("03:38:20", "ENG ", "COOLANT LOOP 2 NOMINAL", CY), ("03:38:44", "COMM", "INBOUND: PORT AURELIUS CONTROL", AMB)]
    f = mono_f(11)
    for k, (t, st, msg, c) in enumerate(lines):
        y = 44 + k * 18.2
        p.text(14, y, t, f, DIM, "lm")
        p.text(80, y, st, f, c, "lm")
        p.text(122, y, msg, f, ICE if k % 5 else WHT, "lm")
        if k % 4 == 0:
            p.rect(w - 22, y - 4, w - 14, y + 4, fill=c)
    p.rect(14, 44 + 13 * 18.2 - 8, w - 28, 44 + 13 * 18.2 + 9, outline=(40, 80, 120), w=0.8)
    return p.done()


def hexagon(cx, cy, r, rot=30):
    return [(cx + r * math.cos(math.radians(rot + 60 * k)), cy + r * math.sin(math.radians(rot + 60 * k))) for k in range(6)]


def page_hex(w=512, h=320) -> Image.Image:
    p = Page(w, h)
    p.frame("POWER GRID · BUS A / BUS B", accent=DEPT["engineering"], footer="TOTAL 480 V  |  LOAD 78 PERCENT")
    rng = random.Random(21)
    r = 15
    dx, dy = r * 1.5, r * math.sqrt(3)
    for i in range(14):
        for j in range(8):
            cx = 30 + i * dx * 1.0
            cy = 62 + j * dy + (dy / 2 if i % 2 else 0)
            if cx > w - 24 or cy > h - 34:
                continue
            v = rng.random()
            if v > 0.78:
                col, fill = AMB, (70, 42, 8)
            elif v > 0.35:
                col, fill = CY, (8, 30, 54)
            else:
                col, fill = (36, 70, 110), None
            p.poly(hexagon(cx, cy, r - 1.6), fill=fill, outline=col, w=1.0, glow=0.5 if fill else 0)
            if fill and rng.random() > 0.5:
                p.dot(cx, cy, 2, col, 0.8)
    return p.done()


def page_rings(w=512, h=320) -> Image.Image:
    p = Page(w, h)
    p.frame("TACTICAL · 360 SCOPE", accent=DEPT["security"], footer="RANGE 40 KM  |  CONTACTS 11")
    cx, cy = w / 2, 172
    for k, r in enumerate((30, 60, 90, 120)):
        p.ellipse(cx, cy, r, r, outline=(30, 64, 104) if k < 3 else (60, 120, 190), w=0.9, glow=0.3 if k == 3 else 0)
    for a in range(0, 360, 10):
        t = math.radians(a)
        l = 8 if a % 30 == 0 else 4
        p.line([(cx + 120 * math.cos(t), cy + 120 * math.sin(t)), (cx + (120 - l) * math.cos(t), cy + (120 - l) * math.sin(t))], DIM, 0.8)
        if a % 90 == 0:
            p.line([(cx, cy), (cx + 120 * math.cos(t), cy + 120 * math.sin(t))], (30, 64, 104), 0.7)
    p.arc(cx, cy, 90, -118, -58, CY, 2.0, glow=0.9)
    rng = random.Random(8)
    for k in range(11):
        a = rng.uniform(0, 2 * math.pi)
        r = rng.uniform(20, 112)
        c = RED if k % 3 == 0 else (GRN if k % 3 == 1 else AMB)
        x, y = cx + r * math.cos(a), cy + r * math.sin(a)
        p.poly([(x, y - 5), (x + 4.4, y + 3.6), (x - 4.4, y + 3.6)], outline=c, w=1.2, glow=0.8)
    p.poly([(cx, cy - 8), (cx + 6, cy + 6), (cx, cy + 3), (cx - 6, cy + 6)], fill=ICE)
    for k in range(5):
        y = 56 + k * 15
        p.text(22, y, f"T-{10 + k}", mono_f(10), (RED, GRN, AMB, GRN, AMB)[k], "lm")
        p.text(62, y, f"{12 + k * 3.7:.1f} KM", mono_f(10), ICE, "lm")
    return p.done()


def page_waterfall(w=512, h=320) -> Image.Image:
    p = Page(w, h)
    p.frame("SIGNAL INTERCEPT · WATERFALL", accent=DEPT["science"], footer="BAND 4.1-4.9 GHZ  |  AGC AUTO")
    rng = np.random.default_rng(3)
    ww, hh = (w - 28), (h - 82)
    base = rng.random((hh // 2, ww // 2)).astype(np.float32) ** 3 * 0.25
    for x0, wd, amp in ((60, 6, 0.9), (150, 3, 0.7), (211, 10, 0.5), (300, 4, 0.95), (352, 2, 0.6), (420, 7, 0.8)):
        x = np.arange(ww // 2)[None, :]
        drift = np.sin(np.arange(hh // 2)[:, None] * 0.08 + x0) * 3
        base += amp * np.exp(-((x - x0 / 2 - drift) / (wd / 2)) ** 2) * (0.6 + 0.4 * rng.random((hh // 2, 1)))
    base = np.clip(base, 0, 1)
    img = np.zeros((hh // 2, ww // 2, 3), np.float32)
    img[..., 0] = base ** 2.2 * 255
    img[..., 1] = base ** 1.1 * 190
    img[..., 2] = base ** 0.7 * 255
    tile = Image.fromarray(img.astype(np.uint8), "RGB").resize((ww * S, hh * S), Image.BICUBIC)
    p.img.paste(tile, (14 * S, 38 * S))
    p.rect(14, 38, 14 + ww, 38 + hh, outline=(30, 60, 96), w=1)
    for k in range(0, 9):
        x = 14 + k * ww / 8
        p.line([(x, 38 + hh), (x, 38 + hh + 5)], DIM, 0.8)
        p.text(x, 38 + hh + 12, f"{4.1 + 0.1 * k:.1f}", mono_f(8), DIM, "mm")
    p.d = ImageDraw.Draw(p.img)
    return p.done()


def page_matrix(w=512, h=320) -> Image.Image:
    p = Page(w, h)
    p.frame("DAMAGE CONTROL · SYSTEM MATRIX", accent=DEPT["engineering"], footer="12 DECKS  |  16 SYSTEMS  |  0 CRITICAL")
    rng = random.Random(5)
    cols, rows = 16, 9
    cw, ch = (w - 56) / cols, (h - 84) / rows
    sys_names = ["RCT", "BUS", "SHD", "WPN", "ENG", "SNS", "COM", "LSS", "CLN", "DCS", "NAV", "CPU", "RAD", "CPL", "FLT", "MED"]
    for i in range(cols):
        p.text(34 + i * cw + cw / 2, 42, sys_names[i], mono_f(7), DIM, "mm")
    for j in range(rows):
        p.text(18, 58 + j * ch + ch / 2, f"D{j + 1:02d}", mono_f(8), DIM, "mm")
        for i in range(cols):
            v = rng.random()
            c, f = (GRN, (8, 40, 28)) if v > 0.12 else ((AMB, (60, 38, 6)) if v > 0.04 else (RED, (70, 12, 16)))
            x0, y0 = 34 + i * cw + 2, 54 + j * ch + 2
            p.rect(x0, y0, x0 + cw - 4, y0 + ch - 4, fill=f, outline=c, w=0.8, glow=0.25)
    return p.done()


def page_schematic(w=512, h=320) -> Image.Image:
    p = Page(w, h)
    p.frame("POWER DISTRIBUTION", accent=DEPT["engineering"], footer="REACTOR 1 ONLINE  |  BUS A/B CROSS-TIE CLOSED")
    boxes = {"REACTOR": (36, 130, 120, 180, AMB), "BUS A": (170, 80, 250, 112, CY), "BUS B": (170, 198, 250, 230, CY), "SHIELDS": (310, 56, 410, 88, CY),
             "WEAPONS": (310, 106, 410, 138, RED), "ENGINES": (310, 168, 410, 200, AMB), "SENSORS": (310, 220, 410, 252, VIO), "LIFE SUPPORT": (430, 130, 500, 176, GRN)}
    for (a, b) in (("REACTOR", "BUS A"), ("REACTOR", "BUS B"), ("BUS A", "SHIELDS"), ("BUS A", "WEAPONS"), ("BUS B", "ENGINES"), ("BUS B", "SENSORS"), ("BUS A", "BUS B")):
        (x0, y0, x1, y1, _), (u0, v0, u1, v1, _) = boxes[a], boxes[b]
        ax, ay = (x1, (y0 + y1) / 2) if u0 > x1 else ((x0 + x1) / 2, y1 if v0 > y1 else y0)
        bx, by = (u0, (v0 + v1) / 2) if u0 > x1 else ((u0 + u1) / 2, v0 if v0 > y1 else v1)
        mx = (ax + bx) / 2
        pts = [(ax, ay), (mx, ay), (mx, by), (bx, by)] if u0 > x1 else [(ax, ay), (bx, by)]
        p.line(pts, (60, 120, 190), 1.3, glow=0.5)
        p.dot(ax, ay, 2, WHT)
    p.line([(250, (80 + 112) / 2), (275, (80 + 112) / 2), (275, 214), (250, 214)], (60, 120, 190), 1.0)
    for n, (x0, y0, x1, y1, c) in boxes.items():
        p.rect(x0, y0, x1, y1, fill=tuple(int(v * 0.16) for v in c), outline=c, w=1.4, glow=0.6)
        p.text((x0 + x1) / 2, (y0 + y1) / 2, n, title_f(15), ICE, "mm", glow=0.3)
    p.text(78, 196, "480 V", mono_f(10), AMB, "mm")
    return p.done()


def gauge(p: Page, cx, cy, r, val, label, col=CY, unit="") -> None:
    p.arc(cx, cy, r, 135, 405, (24, 50, 82), 5)
    p.arc(cx, cy, r, 135, 135 + 270 * val, col, 5, glow=0.8)
    for k in range(0, 28):
        a = math.radians(135 + 270 * k / 27)
        l = 7 if k % 3 == 0 else 3.5
        p.line([(cx + (r + 5) * math.cos(a), cy + (r + 5) * math.sin(a)), (cx + (r + 5 + l) * math.cos(a), cy + (r + 5 + l) * math.sin(a))], DIM, 0.7)
    a = math.radians(135 + 270 * val)
    p.line([(cx, cy), (cx + (r - 6) * math.cos(a), cy + (r - 6) * math.sin(a))], WHT, 1.6, glow=0.6)
    p.dot(cx, cy, 3.4, ICE)
    p.text(cx, cy + r * 0.52, f"{int(val * 100)}{unit}", mono_f(int(r * 0.3)), ICE, "mm")
    p.text(cx, cy + r + 18, label, title_f(13), DIM, "mm")


def page_gauges(w=512, h=320) -> Image.Image:
    p = Page(w, h)
    p.frame("ENGINE ROOM · INSTRUMENTS", accent=DEPT["engineering"], footer="NOMINAL  |  MAIN ENGINES 2/2  |  RADIATORS EXTENDED")
    gauge(p, 96, 142, 56, 0.78, "REACTOR", AMB, "%")
    gauge(p, 256, 142, 56, 0.46, "RADIATORS", CY, "%")
    gauge(p, 416, 142, 56, 0.62, "COOLANT", GRN, "%")
    for k, (n, v, c) in enumerate((("THRUST L", 0.4, CY), ("THRUST R", 0.42, CY), ("HEAT", 0.31, AMB))):
        y = 258 + k * 16
        p.text(30, y, n, title_f(12), DIM, "lm")
        p.rect(100, y - 4, 470, y + 4, outline=(30, 60, 96), w=0.8)
        p.rect(101, y - 3, 101 + 368 * v, y + 3, fill=c)
    return p.done()


# ================================================================================================================ wide / portrait
def page_wave(w=512, h=192) -> Image.Image:
    p = Page(w, h)
    p.frame("WAVEFORMS · CH 1-3", accent=DEPT["science"], footer="SAMPLE 48 KHZ")
    p.grid(10, 34, w - 10, h - 24, 24, GRID, 0.5)
    for ch, (col, f1, f2, a) in enumerate(((CY, 0.045, 0.13, 30), (AMB, 0.03, 0.09, 24), (GRN, 0.06, 0.21, 16))):
        y0 = 62 + ch * 36
        pts = [(x, y0 + a * 0.5 * (math.sin(x * f1 + ch) + 0.5 * math.sin(x * f2 + 2 * ch) * math.sin(x * 0.011))) for x in range(12, w - 12, 2)]
        p.line(pts, col, 1.3, glow=0.9)
    return p.done()


def page_bars(w=512, h=192) -> Image.Image:
    p = Page(w, h)
    p.frame("CREW STATUS · BY DEPARTMENT", accent=DEPT["command"], footer="CREW 560  |  ON WATCH 187")
    rows = (("COMMAND", 0.96, DEPT["command"]), ("ENGINEERING", 0.88, AMB), ("FLIGHT", 0.74, YEL), ("SCIENCE", 0.9, VIO), ("SECURITY", 0.99, RED), ("MEDICAL", 0.93, TEAL))
    for k, (n, v, c) in enumerate(rows):
        y = 44 + k * 22
        p.text(16, y, n, title_f(13), DIM, "lm")
        p.rect(112, y - 5, 440, y + 5, outline=(30, 60, 96), w=0.8)
        for j in range(int(v * 40)):
            x = 114 + j * 8.1
            p.rect(x, y - 3.4, x + 6.2, y + 3.4, fill=c)
        p.text(w - 14, y, f"{int(v * 100)}", mono_f(11), ICE, "rm")
    return p.done()


def page_ticker(w=1024, h=64) -> Image.Image:
    p = Page(w, h)
    p.rect(0, 0, w - 1, h - 1, outline=(22, 46, 76), w=1.2)
    p.rect(0, 0, 9, h, fill=DEPT["command"])
    msg = "CONDITION GREEN  ·  ALL STATIONS REPORT READY  ·  7TH FLEET HOLDING AT JANUS GATE  ·  PORT AURELIUS CONTROL: NORMAL TRAFFIC  ·  NEXT SHIFT CHANGE 0800  ·  "
    p.text(24, h / 2, msg * 2, mono_f(20), ICE, "lm", glow=0.3)
    return p.done()


DECK_ROWS = [("01", "COMMAND", DEPT["command"]), ("02", "CIC · COMMS", DEPT["command"]), ("03", "CREW COUNTRY", DEPT["medical"]), ("04", "CREW SERVICES", DEPT["medical"]),
             ("05", "SCIENCE · TRANSPORT", DEPT["science"]), ("06", "MEDICAL", DEPT["medical"]), ("07", "ENGINEERING", AMB), ("08", "MARINES · ARMORY", RED),
             ("09", "FLIGHT", YEL), ("10", "HOLDS · MUNITIONS", DIM), ("11", "WORKSHOPS · DC", AMB), ("12", "KEEL", DIM)]


def page_decks(w=256, h=512) -> Image.Image:
    p = Page(w, h)
    p.frame("DECK STATUS", accent=DEPT["engineering"], footer="12 DECKS  |  0 BREACH")
    for k, (n, name, c) in enumerate(DECK_ROWS):
        y = 38 + k * 38.4
        p.rect(12, y, w - 12, y + 31, fill=tuple(int(v * 0.12) for v in c), outline=tuple(int(v * 0.7) for v in c), w=0.9)
        p.rect(12, y, 20, y + 31, fill=c)
        p.text(30, y + 16, n, mono_f(14), ICE, "lm")
        p.text(62, y + 16, name, title_f(15), ICE, "lm")
        p.dot(w - 24, y + 16, 3.6, GRN if k not in (5,) else AMB, 0.9)
    return p.done()


def page_atmo(w=256, h=512) -> Image.Image:
    p = Page(w, h)
    p.frame("ATMOSPHERE · LIFE SUPPORT", accent=DEPT["medical"], footer="DECK 1-12  |  ALL LOOPS NOMINAL")
    for k, (n, v, c) in enumerate((("O2", 0.21, GRN), ("N2", 0.78, CY), ("CO2", 0.04, AMB), ("H2O", 0.46, CY))):
        x = 34 + k * 52
        p.rect(x, 64, x + 30, 330, outline=(30, 60, 96), w=1)
        for j in range(int(v * 26)):
            y = 326 - j * 10
            p.rect(x + 2.5, y - 7, x + 27.5, y, fill=c)
        p.text(x + 15, 350, n, title_f(15), ICE, "mm")
        p.text(x + 15, 368, f"{v * 100:.0f}", mono_f(10), DIM, "mm")
    gauge(p, 128, 424, 34, 0.82, "PRESSURE", CY, "")
    return p.done()


def page_equalizer(w=256, h=512) -> Image.Image:
    p = Page(w, h)
    p.frame("SENSOR SPECTRUM", accent=DEPT["science"], footer="PASSIVE ARRAY 2")
    rng = random.Random(4)
    for k in range(14):
        x = 20 + k * 16
        v = 0.15 + 0.8 * abs(math.sin(k * 0.7 + 1.0)) * rng.uniform(0.6, 1.0)
        for j in range(int(v * 36)):
            y = h - 40 - j * 11.2
            c = VIO if j < 22 else (AMB if j < 30 else RED)
            p.rect(x, y - 8, x + 12, y, fill=tuple(int(q * 0.9) for q in c))
    return p.done()


def page_checklist(w=256, h=512) -> Image.Image:
    p = Page(w, h)
    p.frame("PRE-WATCH CHECKLIST", accent=DEPT["command"], footer="SIGNED: XO · 0300")
    items = ["HELM CONSOLE", "NAV ALIGNMENT", "REACTOR OUTPUT", "SHIELD GRID", "WEAPONS SAFE", "FLEET NET", "LIFE SUPPORT", "DAMAGE CONTROL", "FLIGHT DECK", "HULL SEALS", "COMPUTER CORE", "BRIDGE LOG"]
    for k, n in enumerate(items):
        y = 46 + k * 37
        p.rect(14, y - 8, 26, y + 4, outline=GRN, w=1.1, glow=0.4)
        p.line([(16, y - 2), (20, y + 2), (25, y - 8)], GRN, 1.4)
        p.text(40, y - 2, n, title_f(15), ICE, "lm")
        p.text(w - 12, y - 2, f"{k + 1:02d}", mono_f(10), DIM, "rm")
    return p.done()


# ===================================================================================================================== squares
def page_radar(w=320, h=320) -> Image.Image:
    p = Page(w, h)
    p.frame("RADAR · FWD 120", accent=DEPT["security"], footer="SWEEP 4 S")
    cx, cy = w / 2, h / 2 + 8
    for r in (40, 80, 120):
        p.ellipse(cx, cy, r, r, outline=(30, 64, 104), w=0.9)
    p.line([(cx - 124, cy), (cx + 124, cy)], (30, 64, 104), 0.7)
    p.line([(cx, cy - 124), (cx, cy + 124)], (30, 64, 104), 0.7)
    for k in range(40):                                                    # sweep trail
        a = math.radians(-60 - k * 1.6)
        c = tuple(int(v * (1 - k / 40) * 0.8) for v in GRN)
        p.line([(cx, cy), (cx + 120 * math.cos(a), cy + 120 * math.sin(a))], c, 1.2)
    a = math.radians(-60)
    p.line([(cx, cy), (cx + 120 * math.cos(a), cy + 120 * math.sin(a))], GRN, 1.6, glow=0.9)
    rng = random.Random(13)
    for _ in range(6):
        ang, r = rng.uniform(0, 6.28), rng.uniform(25, 110)
        p.dot(cx + r * math.cos(ang), cy + r * math.sin(ang), 2.6, rng.choice([GRN, AMB, RED]))
    return p.done()


def page_attitude(w=320, h=320) -> Image.Image:
    """The attitude indicator ball: sky over ground, a horizon, pitch ladder, the aircraft symbol, bank ticks."""
    p = Page(w, h, bg=(2, 4, 8))
    cx, cy, r = w / 2, h / 2, 138
    yy, xx = np.mgrid[0:h * S, 0:w * S].astype(np.float32)
    dx, dy = (xx / S - cx), (yy / S - cy)
    tilt = math.radians(-8)
    ry = -dx * math.sin(tilt) + dy * math.cos(tilt) - 14
    inside = (dx * dx + dy * dy) < r * r
    shade = 1.0 - 0.45 * (dx * dx + dy * dy) / (r * r)
    sky = np.stack([40 + 30 * (1 - np.clip(-ry / r, 0, 1)), 110 + 60 * (1 - np.clip(-ry / r, 0, 1)), 230 - 40 * np.clip(-ry / r, 0, 1)], -1)
    gnd = np.stack([108 - 30 * np.clip(ry / r, 0, 1), 70 - 24 * np.clip(ry / r, 0, 1), 36 - 14 * np.clip(ry / r, 0, 1)], -1)
    arr = np.where((ry < 0)[..., None], sky, gnd) * shade[..., None] * 0.9
    base = np.array(p.img, np.float32)
    base[inside] = arr[inside]
    p.img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")
    p.d = ImageDraw.Draw(p.img)
    p.ellipse(cx, cy, r, r, outline=(120, 150, 190), w=2.4, glow=0.5)
    c, s = math.cos(tilt), math.sin(tilt)
    def R(x, y):
        return (cx + x * c - (y + 14) * s * -1 * 1.0 + 0, cy + x * s + (y + 14) * c)
    for k in range(-3, 4):                                                 # pitch ladder
        yv = k * 26
        ln = 34 if k % 2 == 0 else 18
        if k == 0:
            ln = 140
        a = (cx - ln * c - (yv) * -s * -1, cy - ln * s + yv * c)
        pa = (cx + (-ln) * c - yv * s, cy + (-ln) * s + yv * c + 14 * c * 0 - 14 * 0)
        pb = (cx + ln * c - yv * s, cy + ln * s + yv * c)
        p.line([(pa[0], pa[1] - 14 * c), (pb[0], pb[1] - 14 * c)], WHT, 1.4 if k == 0 else 1.0)
    p.line([(cx - 52, cy + 6), (cx - 22, cy + 6), (cx - 22, cy + 16)], AMB, 3.0, glow=0.9)
    p.line([(cx + 52, cy + 6), (cx + 22, cy + 6), (cx + 22, cy + 16)], AMB, 3.0, glow=0.9)
    p.dot(cx, cy + 6, 3.4, AMB, 1.0)
    for a in (-60, -45, -30, -20, -10, 0, 10, 20, 30, 45, 60):
        t = math.radians(a - 90)
        l = 12 if a % 30 == 0 else 7
        p.line([(cx + (r - 2) * math.cos(t), cy + (r - 2) * math.sin(t)), (cx + (r - 2 - l) * math.cos(t), cy + (r - 2 - l) * math.sin(t))], WHT, 1.2)
    p.poly([(cx, cy - r + 14), (cx + 6, cy - r + 26), (cx - 6, cy - r + 26)], fill=AMB)
    return p.done()


def page_compass(w=320, h=320) -> Image.Image:
    p = Page(w, h)
    cx, cy, r = w / 2, h / 2, 138
    p.ellipse(cx, cy, r, r, outline=(60, 120, 190), w=1.6, glow=0.7)
    p.ellipse(cx, cy, r - 26, r - 26, outline=(30, 64, 104), w=0.9)
    for a in range(0, 360, 5):
        t = math.radians(a - 90)
        l = 14 if a % 30 == 0 else (9 if a % 10 == 0 else 5)
        p.line([(cx + r * math.cos(t), cy + r * math.sin(t)), (cx + (r - l) * math.cos(t), cy + (r - l) * math.sin(t))], ICE if a % 30 == 0 else DIM, 1.0)
        if a % 30 == 0:
            lab = {0: "N", 90: "E", 180: "S", 270: "W"}.get(a, f"{a // 10:02d}")
            tx, ty = cx + (r - 26) * math.cos(t), cy + (r - 26) * math.sin(t)
            p.text(tx, ty, lab, title_f(17 if a % 90 == 0 else 12), AMB if a == 0 else ICE, "mm")
    p.poly([(cx, cy - 64), (cx + 12, cy + 4), (cx, cy - 8), (cx - 12, cy + 4)], fill=CY, outline=WHT, w=1.0, glow=0.8)
    p.poly([(cx, cy + 56), (cx + 9, cy + 6), (cx, cy + 12), (cx - 9, cy + 6)], fill=(30, 60, 96))
    p.text(cx, cy + 96, "HDG 077", mono_f(15), WHT, "mm", glow=0.5)
    return p.done()


# ====================================================================================================== the cockpit's own pages
CAUTION = ["REACTOR", "COOLANT", "SHIELDS", "RAIL FEED", "MISSILE", "DECOY", "FUEL", "BINGO", "LOCK", "FLIGHT CTL", "HYD", "ELEC", "DOORS", "MASTER", "O2", "HULL", "EJECT", "GEAR"]


def page_caution(w=512, h=192) -> Image.Image:
    p = Page(w, h)
    cols, rows = 6, 3
    cw, ch = (w - 16) / cols, (h - 16) / rows
    lit = {1: AMB, 7: AMB, 13: RED, 15: AMB}
    for k, n in enumerate(CAUTION):
        i, j = k % cols, k // cols
        x0, y0 = 8 + i * cw + 3, 8 + j * ch + 3
        c = lit.get(k)
        if c:
            p.rect(x0, y0, x0 + cw - 6, y0 + ch - 6, fill=tuple(int(v * 0.6) for v in c), outline=c, w=1.4, glow=0.8)
            p.text(x0 + (cw - 6) / 2, y0 + (ch - 6) / 2, n, title_f(15), (16, 16, 18) if c == AMB else WHT, "mm")
        else:
            p.rect(x0, y0, x0 + cw - 6, y0 + ch - 6, fill=(6, 12, 22), outline=(26, 50, 82), w=1.0)
            p.text(x0 + (cw - 6) / 2, y0 + (ch - 6) / 2, n, title_f(15), (42, 70, 104), "mm")
    return p.done()


def page_engine(w=256, h=512) -> Image.Image:
    p = Page(w, h)
    p.frame("PROPULSION", accent=DEPT["flight"], footer="2 ENGINES  |  AFTERBURNER ARMED")
    cols = (("THR L", 0.62, CY), ("THR R", 0.64, CY), ("TEMP", 0.41, AMB), ("FLOW", 0.7, GRN))
    for k, (n, v, c) in enumerate(cols):
        x = 24 + k * 54
        p.rect(x, 52, x + 30, 352, outline=(30, 60, 96), w=1)
        for t in range(0, 11):
            y = 352 - t * 30
            p.line([(x + 30, y), (x + 36, y)], DIM, 0.8)
        for j in range(int(v * 30)):
            y = 348 - j * 10.0
            p.rect(x + 3, y - 7, x + 27, y, fill=c)
        p.text(x + 15, 372, n, title_f(14), ICE, "mm")
    gauge(p, 128, 432, 30, 0.74, "REACTOR", AMB, "%")
    return p.done()


def page_weapons(w=512, h=320) -> Image.Image:
    p = Page(w, h)
    p.frame("ORDNANCE · ALPHA 1", accent=DEPT["security"], footer="MASTER ARM: SAFE  |  GUN CAM: ON")
    rows = (("RAIL CANNON", "240", "RDY", GRN), ("MISSILE · IR", "4", "RDY", GRN), ("MISSILE · RADAR", "0", "EMPTY", DIM), ("DECOY · CHAFF", "4", "RDY", GRN), ("DECOY · FLARE", "4", "RDY", GRN), ("SHIELD CELL", "100", "FULL", CY))
    for k, (n, c, st, col) in enumerate(rows):
        y = 52 + k * 36
        p.rect(14, y - 14, w - 14, y + 14, fill=(6, 14, 26), outline=(26, 50, 82), w=1)
        p.rect(14, y - 14, 20, y + 14, fill=col)
        p.text(34, y, n, title_f(17), ICE, "lm")
        p.text(300, y, c, mono_f(17), WHT, "rm")
        p.text(w - 28, y, st, mono_f(11), col, "rm", glow=0.4)
    p.text(30, 282, "SELECTED", mono_f(10), DIM, "lm")
    p.text(110, 282, "RAIL CANNON · SUSTAINED", title_f(16), AMB, "lm", glow=0.5)
    return p.done()


def page_navmfd(w=512, h=320) -> Image.Image:
    p = Page(w, h)
    p.frame("NAV · ASN AQUILA REL", accent=DEPT["command"], footer="RANGE 20 KM  |  FRIENDLY 15  |  HOSTILE 0")
    cx, cy = 256, 186
    p.grid(14, 36, w - 14, h - 28, 36, GRID, 0.5)
    for r in (38, 76, 114):
        p.ellipse(cx, cy, r, r, outline=(30, 64, 104), w=0.8)
    p.poly([(cx, cy - 9), (cx + 6, cy + 6), (cx, cy + 3), (cx - 6, cy + 6)], fill=ICE)
    p.line([(cx, cy - 9), (cx, cy - 110)], CY, 1.0, glow=0.6)
    p.poly([(400, 90), (394, 100), (406, 100)], outline=GRN, w=1.2, glow=0.8)
    p.text(412, 92, "AQUILA", mono_f(10), GRN, "lm")
    for (x, y) in ((140, 120), (330, 240), (200, 250)):
        p.poly([(x, y - 5), (x + 4.4, y + 3.6), (x - 4.4, y + 3.6)], outline=CY, w=1.1, glow=0.6)
    p.text(22, 44 + 8, "HDG 077", mono_f(12), WHT, "lm")
    p.text(w - 22, 52, "SPD 432", mono_f(12), WHT, "rm")
    return p.done()


# =========================================================================================================================== glows
def glow_cell(col, w=256, h=128) -> Image.Image:
    """A soft rounded rectangle: bright in the middle (col), falling to nothing at the border; it is laid on a wall behind a screen so the
    screen reads as a light source (the light it spills on the panel round it)."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u = np.abs((xx + 0.5) / w * 2 - 1)
    v = np.abs((yy + 0.5) / h * 2 - 1)
    d = np.maximum(u, v) ** 3.0 * 0.55 + np.sqrt(u * u + v * v) * 0.45
    a = np.clip(1.0 - d, 0, 1) ** 1.7
    arr = np.stack([a * col[0], a * col[1], a * col[2]], -1)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


def glow_bar(col, w=256, h=64) -> Image.Image:
    """A soft glowing bar (a fixture's wash): the profile across is a gaussian, the ends fade out."""
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    u = np.abs((xx + 0.5) / w * 2 - 1)
    v = np.abs((yy + 0.5) / h * 2 - 1)
    a = np.exp(-(v / 0.38) ** 2) * np.clip(1 - u ** 4, 0, 1)
    arr = np.stack([a * col[0], a * col[1], a * col[2]], -1)
    return Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")


# ==================================================================================================================== the atlas
PAGES = [("ship", page_ship), ("starmap", page_starmap), ("orbit", page_orbit), ("log", page_log), ("hex", page_hex), ("rings", page_rings),
         ("waterfall", page_waterfall), ("matrix", page_matrix), ("schematic", page_schematic), ("gauges", page_gauges), ("weapons", page_weapons),
         ("navmfd", page_navmfd), ("wave", page_wave), ("bars", page_bars), ("caution", page_caution), ("ticker", page_ticker),
         ("decks", page_decks), ("atmo", page_atmo), ("equalizer", page_equalizer), ("checklist", page_checklist), ("engine", page_engine),
         ("radar", page_radar), ("attitude", page_attitude), ("compass", page_compass)]


def atlas(W: int = 2048, H: int = 4096, pad: int = 0) -> None:
    img = Image.new("RGB", (W, H), (0, 0, 0))
    rects, px, aspect = {}, {}, {}
    tiles = [(n, fn()) for n, fn in PAGES]
    tiles += [(f"glow_{k}", glow_cell(c)) for k, c in (("command", (70, 130, 255)), ("engineering", (255, 150, 30)), ("flight", (255, 210, 20)),
                                                       ("science", (160, 100, 240)), ("security", (240, 60, 70)), ("medical", (46, 196, 182)),
                                                       ("white", (225, 235, 255)), ("warm", (255, 190, 120)))]
    tiles += [(f"bar_{k}", glow_bar(c)) for k, c in (("white", (225, 235, 255)), ("warm", (255, 190, 120)), ("cool", (110, 170, 255)))]
    tiles += [(f"fan_{d}", page_fan(d, 11 + i)) for i, d in enumerate(("command", "engineering", "flight", "science", "security"))]
    order = sorted(tiles, key=lambda t: (-t[1].size[1], -t[1].size[0]))        # shelf packing, tallest first
    cx = cy = row_h = 0
    for name, tile in order:
        w, h = tile.size
        if cx + w + pad > W:
            cx, cy, row_h = 0, cy + row_h + pad, 0
        if cy + h > H:
            raise RuntimeError(f"the decor atlas is full at {name} ({cy + h} > {H})")
        img.paste(tile, (cx, cy))
        rects[name] = [cx / W, 1.0 - (cy + h) / H, (cx + w) / W, 1.0 - cy / H]
        px[name] = [cx, cy, w, h]
        aspect[name] = round(w / h, 4)
        cx += w + pad
        row_h = max(row_h, h)
    os.makedirs(OUT, exist_ok=True)
    img.save(os.path.join(OUT, "T_BRG3_Decor.png"), optimize=True)
    with open(os.path.join(OUT, "decor.json"), "w", encoding="utf-8") as fh:
        json.dump({"size": [W, H], "rects": rects, "px": px, "aspect": aspect}, fh, indent=1)
    print(f"  decor atlas: {len(rects)} tiles, {cy + row_h}/{H} px used")


def main() -> None:
    atlas()


if __name__ == "__main__":
    main()
