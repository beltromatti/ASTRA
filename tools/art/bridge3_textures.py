"""Textures of the bridge v3 (ARTE-PLANCIA): CC0 sets from ambientCG + procedural maps. Output in art/_cache/ (gitignored,
reproducible with this script):

  art/_cache/textures/T_Carbon_{BC,N,ORM}.png        ambientCG Fabric004 (carbon twill): the dark composite of walls and shells
  art/_cache/textures/T_LeatherBlack_{BC,N,ORM}.png  ambientCG Leather026 (black leather): the seats
  art/_cache/textures/T_BRG3_DeckGrain_{BC,N,ORM}.png  procedural: fine diamond anti-slip knurl on gunmetal (tileable, 0.4 m)
  art/_cache/bridge3/T_BRG3_Lamps.png                8x8 palette of 8x8 px cells: RGB = emissive colour, A = alert weight
  art/_cache/bridge3/T_BRG3_Labels.png + labels.json label atlas (stations, equipment tags, deck legends, pictograms)

The packing follows tools/art/pack_textures.py (BC sRGB, N DirectX, ORM = AO/roughness/metal): its pack_set() is reused.

  art/_cache/bridge3/T_BRG3_Decor.png + decor.json    ARTE-PLANCIA-2: static display pages and soft glows (tools/art/bridge3_decor.py)

Run: uv run --with pillow --with numpy python tools/art/bridge3_textures.py [--no-download | --atlas-only]
"""
from __future__ import annotations

import json
import math
import os
import sys
import urllib.request
import zipfile

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import pack_textures as PT  # noqa: E402  (SRC/OUT are relative to ROOT: this checkout)

SETS = {"Carbon": "Fabric004", "LeatherBlack": "Leather026"}
OUT_TEX = PT.OUT
OUT_B3 = os.path.join(ROOT, "art", "_cache", "bridge3")


def download(acg: str) -> None:
    folder = os.path.join(PT.SRC, acg)
    if os.path.isdir(folder) and any(f.endswith("_Color.jpg") for f in os.listdir(folder)):
        return
    os.makedirs(folder, exist_ok=True)
    zpath = os.path.join(PT.SRC, f"{acg}_2K-JPG.zip")
    req = urllib.request.Request(f"https://ambientcg.com/get?file={acg}_2K-JPG.zip", headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=300) as r, open(zpath, "wb") as fh:
        fh.write(r.read())
    with zipfile.ZipFile(zpath) as z:
        z.extractall(folder)
    os.remove(zpath)
    print(f"  downloaded {acg}")


# ---------------------------------------------------------------------------------------------------------- lamps palette
def palette() -> None:
    sys.path.insert(0, os.path.join(ROOT, "art", "blender"))
    # the palette lives in the Blender toolkit (single source of truth); parse it without importing bpy
    src = open(os.path.join(ROOT, "art", "blender", "bridge3_lib.py"), encoding="utf-8").read()
    start = src.index("PALETTE = [")
    end = src.index("PAL_INDEX")
    ns: dict = {}
    exec(src[start:end], ns)
    pal = ns["PALETTE"]
    img = np.zeros((64, 64, 4), np.uint8)
    for i, (_name, hexcol, alert) in enumerate(pal):
        col, row = i % 8, i // 8
        rgb = [int(hexcol[k:k + 2], 16) for k in (1, 3, 5)]
        img[row * 8:(row + 1) * 8, col * 8:(col + 1) * 8] = (*rgb, int(round(alert * 255)))
    # unused cells: near black, alert 0
    for i in range(len(pal), 64):
        col, row = i % 8, i // 8
        img[row * 8:(row + 1) * 8, col * 8:(col + 1) * 8] = (4, 5, 6, 0)
    os.makedirs(OUT_B3, exist_ok=True)
    Image.fromarray(img, "RGBA").save(os.path.join(OUT_B3, "T_BRG3_Lamps.png"))
    print(f"  palette: {len(pal)} cells")


# -------------------------------------------------------------------------------------------------------------- deck grain
def periodic_noise(size: int, seed: int, beta: float) -> np.ndarray:
    rng = np.random.default_rng(seed)
    fx = np.fft.fftfreq(size)[:, None]
    fy = np.fft.fftfreq(size)[None, :]
    f = np.sqrt(fx * fx + fy * fy)
    f[0, 0] = 1.0
    spec = (rng.normal(size=(size, size)) + 1j * rng.normal(size=(size, size))) / f ** (beta / 2.0)
    spec[0, 0] = 0.0
    field = np.real(np.fft.ifft2(spec))
    return (field - field.mean()) / (field.std() + 1e-8)


def deck_grain(size: int = 1024, pitch_px: float = 12.0) -> None:
    """Diamond knurl: pyramids on a 45-degree lattice (5 mm pitch at 0.4 m per tile), worn on the ridges."""
    n = int(round(size / pitch_px))
    u = np.arange(size)[None, :] / size
    v = np.arange(size)[:, None] / size
    a = np.abs(((u + v) * n) % 1.0 - 0.5) * 2.0          # 0 at the ridge line, 1 at the valley
    b = np.abs(((u - v) * n) % 1.0 - 0.5) * 2.0
    h = (1.0 - a) * (1.0 - b)                            # pyramid tips
    h = h ** 0.8
    wear = periodic_noise(size, 5, 2.6)
    wear = np.clip(0.5 + 0.25 * wear, 0, 1)
    height = 0.85 * h + 0.15 * wear
    # normal map from the height (wrapped differences), DirectX convention (green up-is-down)
    strength = 4.0
    dx = (np.roll(height, -1, 1) - np.roll(height, 1, 1)) * 0.5 * strength
    dy = (np.roll(height, -1, 0) - np.roll(height, 1, 0)) * 0.5 * strength
    nx, ny, nz = -dx, dy, np.ones_like(dx)               # DX: +Y is down in the image
    ln = np.sqrt(nx * nx + ny * ny + nz * nz)
    normal = np.dstack([nx / ln, ny / ln, nz / ln]) * 0.5 + 0.5
    # base colour: dark gunmetal, ridges catch a little more light, macro mottling
    macro = np.clip(0.5 + 0.2 * periodic_noise(size, 9, 3.0), 0, 1)
    grey = 0.05 + 0.028 * height + 0.02 * macro
    bc = np.dstack([grey * 0.96, grey * 1.0, grey * 1.1])
    bc = np.clip(bc ** (1 / 2.2), 0, 1)
    ao = np.clip(0.55 + 0.45 * height ** 0.6, 0, 1)
    rough = np.clip(0.52 - 0.16 * height + 0.08 * (wear - 0.5), 0.2, 0.85)
    metal = np.full_like(height, 0.85)
    orm = np.dstack([ao, rough, metal])
    for suffix, arr in (("BC", bc), ("N", normal), ("ORM", orm)):
        PT.save(arr, os.path.join(OUT_TEX, f"T_BRG3_DeckGrain_{suffix}.png"))
    print("  deck grain (procedural, 1024, 0.4 m tile)")


# ------------------------------------------------------------------------------------------------------------- label atlas
FONTS = [os.path.join(ROOT, "art", "_downloads", "fonts"), "/Users/beltromatti/Desktop/ASTRA/art/_downloads/fonts"]


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    for d in FONTS:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    raise FileNotFoundError(name)


TITLE, MONO = "BarlowCondensed-SemiBold.ttf", "IBMPlexMono-Medium.ttf"
ICE, DIM, PLATE = (190, 225, 255), (110, 140, 170), (11, 14, 18)
DEPT = {"command": (62, 123, 250), "engineering": (255, 159, 28), "flight": (255, 214, 10), "science": (155, 93, 229),
        "security": (230, 57, 70), "medical": (46, 196, 182)}

STATIONS = [("st_captain", "COMMANDING OFFICER", "CAPTAIN · CVC-01", "command"),
            ("st_xo", "EXECUTIVE OFFICER", "XO · CVC-01", "command"),
            ("st_helm", "HELM", "FLIGHT CONTROL · 1A-H1", "command"),
            ("st_ops", "OPERATIONS", "SHIP SYSTEMS · 1A-O1", "command"),
            ("st_tactical", "TACTICAL", "WEAPONS · SHIELDS · 1A-T1", "security"),
            ("st_comms", "COMMUNICATIONS", "FLEET NET · 1A-C1", "command"),
            ("st_sensors", "SCIENCE & SENSORS", "DETECTION · 1A-S1", "science"),
            ("st_engineering", "ENGINEERING", "POWER · THERMAL · 1A-E1", "engineering"),
            ("st_flight", "FLIGHT CONTROL", "AIR GROUP · 1A-F1", "flight")]
TAGS = ["EMERGENCY EQUIPMENT", "FIRST AID", "FIRE CONTROL", "LIFE SUPPORT", "COOLANT · LOOP 2", "DATA TRUNK 07", "POWER 480 V",
        "VENT 1A-04", "AUTHORIZED PERSONNEL ONLY", "EVA KITS · LOCKER 07", "DAMAGE CONTROL", "MAINTENANCE ACCESS 1A-12",
        "BREAKER PANEL 1A-03", "ATMOSPHERE CONTROL", "MAGNETIC BOOTS", "COMM RELAY 2"]
SMALL = ["1A-03", "1A-04", "1A-05", "1A-06", "1A-07", "1A-08", "PWR", "DATA", "COOL", "AIR", "O2", "H2O", "N2", "CAUTION", "STOP", "OPEN"]
DECK_LEGENDS = [("deck_bridge", "DECK 1 · SECTION A · BRIDGE", "ASN AQUILA · CVC-01"), ("deck_dais", "COMMAND DAIS", "AUTHORIZED PERSONNEL"),
                ("deck_step", "MIND THE STEP", "WELL DECK · -0.6 M"), ("deck_well", "TACTICAL WELL", "HOLOGRAPHIC PLOT")]

# ---- ARTE-PLANCIA-2: tiles APPENDED after the old ones (the old rects keep their pixel positions; the atlas is 2048 x 4096 now)
TAGS2 = ["OXYGEN MASKS · RACK 3", "EMERGENCY LIGHTING", "SURVIVAL KITS", "HULL BREACH KIT", "COMM RELAY 1", "SENSOR ARRAY CONTROL", "FIRE SUPPRESSION",
         "PRESSURE DOOR 1A-01", "LIFEPOD ACCESS", "SECURE STORAGE", "LOG ARCHIVE · CVC-01", "HIGH VOLTAGE 480 V", "HYDRAULICS · LOOP 1", "NAV COMPUTER",
         "SPARE PARTS · CONSOLES", "PORTABLE O2 · 8 UNITS", "EMERGENCY BEACON", "COMPARTMENT SEAL", "STATION READY", "CHECK BEFORE USE", "KEEP CLEAR",
         "STANDBY POWER", "TRANSPORT CASE", "BRIDGE ACCESS", "CAUTION · HOT SURFACE", "DO NOT OBSTRUCT", "FLIGHT SUIT LOCKER", "SIGNAL FLARES"]
SMALL2 = ["1A-09", "1A-10", "1A-11", "1A-12", "A1", "A2", "B1", "B2", "L1", "L2", "R1", "R2", "ON", "OFF", "AUTO", "MAN",
          "ARM", "SAFE", "RDY", "TEST", "RESET", "MUTE", "SYNC", "ALT"]
# corridor / door plates (1024 x 128): (cell, title, sub, accent, arrow)  arrow: -1 left, 1 right, 0 none
PLATES2 = [("sign_port_corridor", "PORT CORRIDOR · DECK 1-A", "ASN AQUILA · CVC-01", "command", 0),
           ("sign_stbd_corridor", "STARBOARD CORRIDOR · DECK 1-A", "ASN AQUILA · CVC-01", "command", 0),
           ("sign_quarters", "CAPTAIN'S QUARTERS", "AUTHORIZED PERSONNEL", "command", 0),
           ("sign_ready_room", "READY ROOM", "COMMAND STAFF", "command", 0),
           ("sign_turbolift", "TURBOLIFT", "DECKS 1-12", "science", 0),
           ("sign_lifepods", "LIFEPODS 1-A", "8 PODS · STAND CLEAR", "security", 0),
           ("sign_bridge", "BRIDGE", "AUTHORIZED PERSONNEL ONLY", "command", 0),
           ("sign_to_bridge", "BRIDGE", "DECK 1 · SECTION A", "command", 1),
           ("sign_to_lift", "TURBOLIFTS · LIFEPODS", "DECKS 2-12", "science", -1),
           ("sign_to_quarters", "CAPTAIN'S QUARTERS · READY ROOM", "STARBOARD", "command", 1),
           ("sign_emergency", "EMERGENCY EXIT · LIFEPODS", "FOLLOW THE GREEN LIGHTS", "security", 0),
           ("sign_deck1", "DECK 1 · COMMAND", "SECTION A · BRIDGE COMPLEX", "command", 0)]


def plate(w: int, h: int, title: str, sub: str, accent) -> Image.Image:
    img = Image.new("RGBA", (w, h), (*PLATE, 255))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w - 1, h - 1), outline=(46, 54, 66, 255), width=3)
    d.rectangle((0, 0, int(h * 0.09), h), fill=(*accent, 255))
    d.text((int(h * 0.3), h * 0.42), title, font=font(TITLE, int(h * 0.56)), fill=(*ICE, 255), anchor="lm")
    if sub:
        d.text((w - int(h * 0.18), h * 0.82), sub, font=font(MONO, int(h * 0.15)), fill=(*DIM, 255), anchor="rm")
    return img


def tag(w: int, h: int, text: str, warn: bool = False) -> Image.Image:
    bg = (236, 190, 20) if warn else PLATE
    fg = (16, 16, 18) if warn else ICE
    img = Image.new("RGBA", (w, h), (*bg, 255))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w - 1, h - 1), outline=(30, 34, 40, 255) if not warn else (16, 16, 18, 255), width=max(2, h // 32))
    size = int(h * 0.5)
    f = font(TITLE, size)
    while d.textlength(text, font=f) > w * 0.9 and size > 8:
        size -= 2
        f = font(TITLE, size)
    d.text((w / 2, h * 0.52), text, font=f, fill=(*fg, 255), anchor="mm")
    return img


def plate_arrow(w: int, h: int, title: str, sub: str, accent, arrow: int) -> Image.Image:
    """A plate with a drawn arrow (the font has no arrows): arrow -1 on the left, 1 on the right, 0 none."""
    if not arrow:
        return plate(w, h, title, sub, accent)
    img = Image.new("RGBA", (w, h), (*PLATE, 255))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w - 1, h - 1), outline=(46, 54, 66, 255), width=3)
    d.rectangle((0, 0, int(h * 0.09), h), fill=(*accent, 255))
    ah = h * 0.7
    tip = 14 if arrow < 0 else w - 14
    tail = tip + ah * 1.05 if arrow < 0 else tip - ah * 1.05
    sgn = -1 if arrow < 0 else 1
    cy = h * 0.5
    neck = tip - sgn * ah * 0.5
    d.polygon([(tail, cy - ah * 0.13), (neck, cy - ah * 0.13), (neck, cy - ah * 0.34), (tip, cy), (neck, cy + ah * 0.34), (neck, cy + ah * 0.13), (tail, cy + ah * 0.13)],
              fill=(*ICE, 255))
    x_text = int(h * 0.3) if arrow > 0 else int(h * 0.3) + int(ah * 1.3)
    d.text((x_text, h * 0.42), title, font=font(TITLE, int(h * 0.56)), fill=(*ICE, 255), anchor="lm")
    d.text((w - int(h * 0.18) - (int(ah * 1.4) if arrow > 0 else 0), h * 0.82), sub, font=font(MONO, int(h * 0.15)), fill=(*DIM, 255), anchor="rm")
    return img


def emblem(size: int = 384) -> Image.Image:
    """The ASTRA Navy emblem as a lit inlay: a double ring with the motto round it, an eight-pointed compass star (long points N/E/S/W)
    (the proportions of art/blender/ship3_text.astra_emblem and tools/art/signage.py)."""
    S2 = 3
    big = Image.new("RGBA", (size * S2, size * S2), (*PLATE, 255))
    d = ImageDraw.Draw(big)
    c = size * S2 / 2
    r = size * S2 / 2 * 0.96
    for ri, ro in ((0.90 * r, 0.97 * r), (0.58 * r, 0.63 * r)):
        d.ellipse((c - ro, c - ro, c + ro, c + ro), outline=(*ICE, 255), width=int(ro - ri))
    pts = []
    for k in range(16):
        rad = {0: 0.72 * r, 2: 0.40 * r}.get(k % 4, 0.11 * r)
        a = 2 * math.pi * k / 16
        pts.append((c + rad * math.sin(a), c - rad * math.cos(a)))
    d.polygon(pts, fill=(*ICE, 255))
    d.ellipse((c - 0.065 * r, c - 0.065 * r, c + 0.065 * r, c + 0.065 * r), fill=(*PLATE, 255))

    def ring_text(text: str, mid_deg: float, rad: float, fsize: int, bottom: bool) -> None:
        f = font(TITLE, fsize * S2)
        total = sum(d.textlength(ch, font=f) for ch in text) + 6 * S2 * (len(text) - 1)
        ang_total = total / rad
        a = math.radians(mid_deg) - (ang_total / 2 if not bottom else -ang_total / 2)
        for ch in text:
            wch = d.textlength(ch, font=f)
            half = (wch / 2 + 3 * S2) / rad
            a_c = a + (half if not bottom else -half)
            tile = Image.new("RGBA", (int(wch + 20 * S2), int(fsize * S2 * 1.6)), (0, 0, 0, 0))
            ImageDraw.Draw(tile).text((tile.width / 2, tile.height / 2), ch, font=f, fill=(*ICE, 255), anchor="mm")
            rot = -math.degrees(a_c) + (180 if bottom else 0)
            tile = tile.rotate(rot, resample=Image.BICUBIC, expand=True)
            x = c + rad * math.sin(a_c) - tile.width / 2
            y = c - rad * math.cos(a_c) - tile.height / 2
            big.alpha_composite(tile, (int(x), int(y)))
            a += (2 * half) if not bottom else -(2 * half)

    ring_text("ASTRA NAVY", 0, 0.765 * r, 30, False)
    ring_text("CONCORD · LAW · LIGHT", 180, 0.765 * r, 24, True)
    return big.resize((size, size), Image.LANCZOS)


def stripes(w: int, h: int, step: int = 36) -> Image.Image:
    img = Image.new("RGBA", (w, h), (236, 190, 20, 255))
    d = ImageDraw.Draw(img)
    for x in range(-h, w + h, step):
        d.polygon([(x, h), (x + step / 2, h), (x + step / 2 + h, 0), (x + h, 0)], fill=(16, 16, 18, 255))
    return img


def icon(kind: str, s: int = 128) -> Image.Image:
    img = Image.new("RGBA", (s, s), (0, 0, 0, 255))
    d = ImageDraw.Draw(img)
    m = s * 0.08
    if kind == "hv":                       # high voltage: yellow triangle, a bolt
        d.rectangle((0, 0, s, s), fill=(20, 20, 22, 255))
        d.polygon([(s / 2, m), (s - m, s - m), (m, s - m)], fill=(236, 190, 20, 255))
        d.polygon([(s * 0.55, s * 0.28), (s * 0.38, s * 0.58), (s * 0.5, s * 0.58), (s * 0.44, s * 0.8), (s * 0.64, s * 0.5),
                   (s * 0.52, s * 0.5)], fill=(16, 16, 18, 255))
    elif kind == "fire":                   # fire equipment: red square, a flame
        d.rectangle((m, m, s - m, s - m), fill=(200, 40, 34, 255))
        d.polygon([(s * 0.5, s * 0.16), (s * 0.66, s * 0.46), (s * 0.7, s * 0.7), (s * 0.5, s * 0.84), (s * 0.3, s * 0.7),
                   (s * 0.34, s * 0.5), (s * 0.45, s * 0.58)], fill=(245, 245, 240, 255))
    elif kind == "exit":                   # emergency exit: green square, an arrow
        d.rectangle((m, m, s - m, s - m), fill=(28, 150, 90, 255))
        d.polygon([(s * 0.2, s * 0.42), (s * 0.55, s * 0.42), (s * 0.55, s * 0.25), (s * 0.82, s * 0.5), (s * 0.55, s * 0.75),
                   (s * 0.55, s * 0.58), (s * 0.2, s * 0.58)], fill=(245, 245, 240, 255))
    elif kind == "aid":                    # first aid: green square, a white cross
        d.rectangle((m, m, s - m, s - m), fill=(28, 150, 90, 255))
        d.rectangle((s * 0.4, s * 0.2, s * 0.6, s * 0.8), fill=(245, 245, 240, 255))
        d.rectangle((s * 0.2, s * 0.4, s * 0.8, s * 0.6), fill=(245, 245, 240, 255))
    elif kind == "eva":                    # EVA: a blue disc, a helmet ring
        d.rectangle((m, m, s - m, s - m), fill=(40, 90, 190, 255))
        d.ellipse((s * 0.28, s * 0.22, s * 0.72, s * 0.7), outline=(245, 245, 240, 255), width=int(s * 0.06))
        d.rectangle((s * 0.34, s * 0.7, s * 0.66, s * 0.8), fill=(245, 245, 240, 255))
    elif kind == "rad":                    # radiation: yellow disc, three blades
        d.rectangle((0, 0, s, s), fill=(20, 20, 22, 255))
        d.ellipse((m, m, s - m, s - m), fill=(236, 190, 20, 255))
        c = s / 2
        for k in range(3):
            a0 = math.radians(90 + 120 * k - 30)
            a1 = math.radians(90 + 120 * k + 30)
            pts = [(c, c)] + [(c + s * 0.36 * math.cos(a0 + (a1 - a0) * t / 8), c - s * 0.36 * math.sin(a0 + (a1 - a0) * t / 8)) for t in range(9)]
            d.polygon(pts, fill=(16, 16, 18, 255))
        d.ellipse((c - s * 0.07, c - s * 0.07, c + s * 0.07, c + s * 0.07), fill=(16, 16, 18, 255))
    elif kind == "no_step":                # do not step: red ring and slash
        d.rectangle((0, 0, s, s), fill=(20, 20, 22, 255))
        d.ellipse((m, m, s - m, s - m), outline=(200, 40, 34, 255), width=int(s * 0.1))
        d.line((s * 0.24, s * 0.76, s * 0.76, s * 0.24), fill=(200, 40, 34, 255), width=int(s * 0.1))
    else:
        d.rectangle((0, 0, s, s), fill=(20, 20, 22, 255))
    return img


def atlas(W: int = 2048, H: int = 4096) -> None:
    img = Image.new("RGBA", (W, H), (*PLATE, 255))
    rects: dict[str, tuple[int, int, int, int]] = {}
    cx = cy = row_h = 0

    def put(name: str, tile: Image.Image) -> None:
        nonlocal cx, cy, row_h
        w, h = tile.size
        if cx + w > W:
            cx, cy, row_h = 0, cy + row_h, 0
        if cy + h > H:
            raise RuntimeError(f"the label atlas is full at {name}")
        img.paste(tile, (cx, cy))
        rects[name] = (cx, cy, w, h)
        cx += w
        row_h = max(row_h, h)

    for name, title, sub, dept in STATIONS:
        put(name, plate(1024, 128, title, sub, DEPT[dept]))
    for name, title, sub in DECK_LEGENDS:
        put(name, plate(1024, 128, title, sub, DEPT["command"]))
    put("hazard", stripes(1024, 64))
    put("hazard_h", stripes(512, 64, 28))
    for i, t in enumerate(TAGS):
        put(f"tag_{i:02d}", tag(512, 128, t, warn=(i in (8,))))
    for i, t in enumerate(SMALL):
        put(f"small_{i:02d}", tag(256, 64, t, warn=(t in ("CAUTION", "STOP"))))
    for k in ("hv", "fire", "exit", "aid", "eva", "rad", "no_step"):
        put(f"icon_{k}", icon(k))
    # ---- appended (ARTE-PLANCIA-2)
    for i, t in enumerate(TAGS2):
        put(f"tag_{len(TAGS) + i:02d}", tag(512, 128, t, warn=(t.startswith("CAUTION") or t in ("KEEP CLEAR", "DO NOT OBSTRUCT"))))
    for i, t in enumerate(SMALL2):
        put(f"small_{len(SMALL) + i:02d}", tag(256, 64, t, warn=(t in ("ARM", "TEST"))))
    for cell, title, sub, dept, arrow in PLATES2:
        put(cell, plate_arrow(1024, 128, title, sub, DEPT[dept], arrow))
    put("emblem", emblem(384))
    img.convert("RGB").save(os.path.join(OUT_B3, "T_BRG3_Labels.png"), optimize=True)
    uv = {k: [x / W, 1.0 - (y + h) / H, (x + w) / W, 1.0 - y / H] for k, (x, y, w, h) in rects.items()}
    tags = {f"tag_{i:02d}": t for i, t in enumerate(TAGS + TAGS2)}
    small = {f"small_{i:02d}": t for i, t in enumerate(SMALL + SMALL2)}
    for cell, title, _sub, _dept, _arrow in PLATES2:
        tags[cell] = title
    with open(os.path.join(OUT_B3, "labels.json"), "w", encoding="utf-8") as fh:
        json.dump({"size": [W, H], "rects": uv, "px": {k: list(v) for k, v in rects.items()}, "tags": tags, "small": small}, fh, indent=1)
    print(f"  label atlas: {len(rects)} tiles, {cy + row_h}/{H} px used")


def main() -> None:
    os.makedirs(OUT_TEX, exist_ok=True)
    os.makedirs(OUT_B3, exist_ok=True)
    if "--atlas-only" in sys.argv:                  # the lamp palette, the label atlas and the decor atlas (no downloads, no PBR sets)
        import bridge3_decor as DC  # noqa: E402
        palette()
        atlas()
        DC.atlas()
        print("OUT", OUT_B3)
        return
    if "--no-download" not in sys.argv:
        for acg in SETS.values():
            download(acg)
    print("Texture sets:")
    for name, acg in SETS.items():
        PT.pack_set(name, acg)
    deck_grain()
    palette()
    atlas()
    import bridge3_decor as DC  # noqa: E402
    DC.atlas()
    print("OUT", OUT_TEX, OUT_B3)


if __name__ == "__main__":
    sys.exit(main())
