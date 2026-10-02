"""ASN Aquila bridge v3: the small things of the people who work here (ARTE-PLANCIA-2).

Mugs, a datapad with a page on it, a pot plant, a desk model of a Falcon on a brass stand, a headset on its hook, a framed picture, a
flight helmet, a planter, a coil of cable. Each builder adds its geometry to the FB groups it is given, in the frame the caller stands in
(local x forward, y to the right, z up, metres), and uses the shared materials only (plus MI_SHIP_Leaf / MI_SHIP_Soil of the ship kit). Round
things go to the `soft` group (smooth shading, no bevel: at this size the project's 3 mm bevel would eat them), flat things to `emit`.
"""
from __future__ import annotations

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge3_lib as L  # noqa: E402
from bridge3_lib import FB, Ry, Rz, T, lerp  # noqa: E402

LEAF = "MI_SHIP_Leaf"
SOIL = "MI_SHIP_Soil"


def mug(soft: FB, x: float, y: float, z: float, mat: str = L.IVORY, band: bool = True, em: FB | None = None, yaw: float = 0.0) -> None:
    """A mug standing on z: r 4 cm, 9.5 cm tall, a handle on the +y side (turned by `yaw`), a dark coffee surface; `band`: a brass line near the rim."""
    with soft.at(T(x, y, z) @ Rz(yaw)):
        soft.cyl((0, 0, 0), (0, 0, 0.095), 0.040, mat, seg=18, r2=0.043)
        soft.cyl((0, 0, 0.0935), (0, 0, 0.0955), 0.0375, L.RUBBER, seg=18)                      # the coffee
        for (a0, a1) in ((0.0, 0.5), (0.5, 1.0)):                                               # the handle: two bars and a bend
            soft.cyl((0.0, 0.040, 0.020 + 0.055 * a0), (0.0, 0.058, 0.026 + 0.050 * a0 + 0.012), 0.0065, mat, seg=6)
        soft.cyl((0.0, 0.058, 0.043), (0.0, 0.058, 0.068), 0.0065, mat, seg=6)
        soft.cyl((0.0, 0.058, 0.068), (0.0, 0.042, 0.084), 0.0065, mat, seg=6)
    if band and em is not None:
        with em.at(T(x, y, z) @ Rz(yaw)):
            em.cyl((0, 0, 0.078), (0, 0, 0.083), 0.0435, L.BRASS, seg=18, r2=0.0437)


def datapad(fb: FB, em: FB, x: float, y: float, z: float, yaw: float = 0.0, page: str = "checklist", w: float = 0.16) -> None:
    """A datapad lying on a surface at z: a dark slab with a rounded-looking edge, its screen showing a page of the decor atlas."""
    h = w * 1.4
    with fb.at(T(x, y, z) @ Rz(yaw)), em.at(T(x, y, z) @ Rz(yaw)):
        fb.box((-h / 2, -w / 2, 0.0), (h / 2, w / 2, 0.011), L.STRUCT)
        fb.box((-h / 2 + 0.004, -w / 2 + 0.004, 0.011), (h / 2 - 0.004, w / 2 - 0.004, 0.0125), L.RUBBER)
        pw = w - 0.026
        ph = pw / L.DECOR_ASPECT[page]
        em.decor((0.0, 0.0, 0.0128), pw, ph, (0, 0, 1), page, up=(1, 0, 0))


def plant(soft: FB, x: float, y: float, z: float, size: float = 1.0, seed: int = 1, pot: str = L.IVORY) -> None:
    """A pot plant: a tapered pot with a brass rim, soil, and a crown of broad curved leaves (each a strip of triangles). `size` scales it (1 = 30 cm)."""
    rng = random.Random(seed)
    s = size
    with soft.at(T(x, y, z)):
        soft.cyl((0, 0, 0), (0, 0, 0.10 * s), 0.055 * s, pot, seg=14, r2=0.068 * s)
        soft.cyl((0, 0, 0.098 * s), (0, 0, 0.106 * s), 0.071 * s, L.BRASS, seg=14)
        soft.cyl((0, 0, 0.100 * s), (0, 0, 0.1035 * s), 0.060 * s, SOIL, seg=14)
        for k in range(9):
            a = 2 * math.pi * k / 9 + rng.uniform(-0.2, 0.2)
            ln = rng.uniform(0.15, 0.24) * s
            tilt = rng.uniform(0.45, 1.0)
            wd = rng.uniform(0.028, 0.040) * s
            pts = []
            for j in range(5):
                t = j / 4
                rr = 0.012 * s + ln * 0.7 * math.sin(t * 1.4 * tilt)
                zz = 0.103 * s + ln * 0.9 * (1 - math.cos(t * 1.1)) * 0.0 + ln * 0.85 * math.sin(t * 1.25) * (1.0 - 0.45 * tilt) + ln * 0.18 * t
                wj = wd * math.sin(math.pi * min(0.999, 0.1 + 0.9 * t))
                pts.append((rr * math.cos(a), rr * math.sin(a), zz, wj))
            rings = []
            for (px, py, pz, wj) in pts:
                nx, ny = -math.sin(a), math.cos(a)
                rings.append([(px - nx * wj, py - ny * wj, pz), (px + nx * wj, py + ny * wj, pz)])
            soft.loft(rings, LEAF, caps=False, closed=False)


def falcon_model(fb: FB, em: FB, x: float, y: float, z: float, yaw: float = 0.0, scale: float = 1.0) -> None:
    """A desk model of the Falcon fighter on a brass stand: an ivory fuselage and swept wings, two fins, a navy stripe, standing on a rod."""
    s = scale
    with fb.at(T(x, y, z) @ Rz(yaw)), em.at(T(x, y, z) @ Rz(yaw)):
        em.cyl((0, 0, 0), (0, 0, 0.006), 0.034 * s, L.BRASS, seg=16)                       # the base
        em.cyl((0, 0, 0.006), (0, 0, 0.060 * s), 0.0035, L.BRASS, seg=8)                  # the rod
        zb = 0.066 * s
        rings = []
        for (xx, hw, hh) in ((-0.075, 0.016, 0.010), (-0.04, 0.020, 0.013), (0.02, 0.020, 0.013), (0.06, 0.012, 0.008), (0.088, 0.004, 0.004)):
            rings.append([(xx * s, -hw * s, zb - hh * s), (xx * s, hw * s, zb - hh * s), (xx * s, hw * s * 0.7, zb + hh * s), (xx * s, -hw * s * 0.7, zb + hh * s)])
        fb.loft(rings, L.IVORY, caps=True)
        for sd in (-1, 1):                                                                  # the wings
            fb.loft([[(-0.060 * s, sd * 0.014 * s, zb - 0.001 * s), (0.010 * s, sd * 0.014 * s, zb - 0.001 * s), (0.010 * s, sd * 0.014 * s, zb + 0.003 * s), (-0.060 * s, sd * 0.014 * s, zb + 0.003 * s)],
                     [(-0.085 * s, sd * 0.078 * s, zb), (-0.050 * s, sd * 0.078 * s, zb), (-0.050 * s, sd * 0.078 * s, zb + 0.0025 * s), (-0.085 * s, sd * 0.078 * s, zb + 0.0025 * s)]],
                    L.IVORY, caps=True)
            fb.loft([[(-0.080 * s, sd * 0.016 * s, zb), (-0.050 * s, sd * 0.016 * s, zb), (-0.050 * s, sd * 0.016 * s, zb + 0.002 * s), (-0.080 * s, sd * 0.016 * s, zb + 0.002 * s)],
                     [(-0.092 * s, sd * 0.018 * s, zb + 0.030 * s), (-0.074 * s, sd * 0.018 * s, zb + 0.030 * s), (-0.074 * s, sd * 0.018 * s, zb + 0.032 * s), (-0.092 * s, sd * 0.018 * s, zb + 0.032 * s)]],
                    L.IVORY, caps=True)                                                       # the fins
        em.lamp_cbox((0.0, 0.0, zb + 0.0125 * s), (0.10 * s, 0.006 * s, 0.002 * s), "command", L.LAMP_DIM)    # the stripe


def photo(fb: FB, em: FB, x: float, y: float, z: float, yaw: float = 0.0, w: float = 0.085, page: str = "orbit") -> None:
    """A framed picture standing on a surface (leaning back 12 degrees on a strut): a brass frame round a page of the decor atlas."""
    h = w / L.DECOR_ASPECT[page]
    with fb.at(T(x, y, z) @ Rz(yaw) @ Ry(-12)), em.at(T(x, y, z) @ Rz(yaw) @ Ry(-12)):
        fb.box((-0.006, -w / 2 - 0.007, 0.0), (0.006, w / 2 + 0.007, h + 0.014), L.STRUCT)
        em.box((0.006, -w / 2 - 0.007, 0.0), (0.0075, w / 2 + 0.007, 0.004), L.BRASS)
        em.box((0.006, -w / 2 - 0.007, h + 0.010), (0.0075, w / 2 + 0.007, h + 0.014), L.BRASS)
        em.box((0.006, -w / 2 - 0.007, 0.0), (0.0075, -w / 2, h + 0.014), L.BRASS)
        em.box((0.006, w / 2, 0.0), (0.0075, w / 2 + 0.007, h + 0.014), L.BRASS)
        em.decor((0.0078, 0.0, 0.007 + h / 2), w, h, (1, 0, 0), page, up=(0, 0, 1))
    with fb.at(T(x, y, z) @ Rz(yaw)):
        fb.cyl((-0.004, 0, 0.012), (-0.040, 0, 0.0), 0.003, L.STRUCT, seg=6)


def headset(soft: FB, em: FB, x: float, y: float, z: float, yaw: float = 0.0) -> None:
    """A communications headset hanging on a brass hook: a headband arc, two ear cups, a mic boom. (x, y, z) = the hook's tip."""
    with soft.at(T(x, y, z) @ Rz(yaw)), em.at(T(x, y, z) @ Rz(yaw)):
        em.cyl((0.0, 0.0, 0.0), (0.020, 0.0, 0.0), 0.004, L.BRASS, seg=6)
        em.cyl((0.020, 0.0, 0.0), (0.020, 0.0, 0.010), 0.004, L.BRASS, seg=6)
        pts = [(0.034, math.cos(a) * 0.075, -0.012 - 0.07 * (1 - math.sin(a))) for a in [lerp(-math.pi * 0.5, math.pi * 0.5, k / 12) for k in range(13)]]
        for (p0, p1) in zip(pts[:-1], pts[1:]):
            soft.cyl(p0, p1, 0.0045, L.RUBBER, seg=6)
        for sd in (-1, 1):
            soft.cyl((0.034, sd * 0.075, -0.082), (0.034, sd * 0.075, -0.104), 0.028, L.STRUCT, seg=14, r2=0.030)
            soft.cyl((0.034, sd * 0.075, -0.104), (0.034, sd * 0.075, -0.108), 0.024, L.RUBBER, seg=14)
        soft.cyl((0.034, 0.075, -0.098), (0.074, 0.040, -0.116), 0.0028, L.RUBBER, seg=6)
        em.lamp_cyl((0.074, 0.040, -0.116), (0.077, 0.038, -0.1175), 0.0075, "red", L.LAMP_DIM, seg=8)


def globe(soft: FB, em: FB, x: float, y: float, z: float, yaw: float = 0.0, r: float = 0.05) -> None:
    """A desk globe of a planet (blue, with a lit terminator band) tilted in a brass ring on a stand: 14 cm tall."""
    with soft.at(T(x, y, z) @ Rz(yaw)), em.at(T(x, y, z) @ Rz(yaw)):
        em.cyl((0, 0, 0.0), (0, 0, 0.008), 0.040, L.BRASS, seg=18)
        soft.cyl((0, 0, 0.008), (0, 0, 0.040), 0.007, L.TRIM, seg=8)
        soft.sphere((0.0, 0.0, 0.040 + r), r, "MI_SHIP_CrateBlue", seg=20, rings=12)
        for k in range(24):                                                                    # the meridian ring (brass), tilted
            a0, a1 = 2 * math.pi * k / 24, 2 * math.pi * (k + 1) / 24
            p0 = (0.0, (r + 0.008) * math.cos(a0), 0.040 + r + (r + 0.008) * math.sin(a0))
            p1 = (0.0, (r + 0.008) * math.cos(a1), 0.040 + r + (r + 0.008) * math.sin(a1))
            em.cyl(p0, p1, 0.0028, L.BRASS, seg=5)
        em.lamp_cyl((0.0, 0.0, 0.040 + r + r + 0.010), (0.0, 0.0, 0.040 + r + r + 0.0125), 0.006, "cyan", L.LAMP_DIM, seg=8)


def cable_coil(soft: FB, x: float, y: float, z: float, r: float = 0.07, turns: int = 5, yaw: float = 0.0, mat: str = L.RUBBER) -> None:
    """A coil of cable lying on a surface (or hanging from a hook): a flat helix of tube."""
    pts = []
    for k in range(turns * 14 + 1):
        a = 2 * math.pi * k / 14
        rr = r * (1.0 - 0.06 * (k / 14.0) / max(1, turns) * 4)
        pts.append((x + rr * math.cos(a), y + rr * math.sin(a), z + 0.009 + 0.0095 * (k / 14.0)))
    soft.tube(pts, 0.0045, mat, seg=6)


def planter(soft: FB, fb: FB, em: FB, x: float, y: float, z: float, yaw: float = 0.0, length: float = 0.9, seed: int = 3) -> None:
    """A hydroponic planter trough (dark composite, a brass rim, a lit nutrient strip) with a hedge of broad-leaved plants growing in it."""
    rng = random.Random(seed)
    with fb.at(T(x, y, z) @ Rz(yaw)), em.at(T(x, y, z) @ Rz(yaw)):
        fb.box((-length / 2, -0.22, 0.0), (length / 2, 0.22, 0.36), L.COMPOSITE)
        fb.box((-length / 2 - 0.02, -0.24, 0.34), (length / 2 + 0.02, 0.24, 0.38), L.STRUCT)
        em.box((-length / 2 - 0.02, -0.24, 0.378), (length / 2 + 0.02, 0.24, 0.382), L.BRASS)
        em.lamp_box((-length / 2 + 0.05, -0.2205, 0.12), (length / 2 - 0.05, -0.2195, 0.135), "green", L.LAMP_DIM)
        fb.box((-length / 2 + 0.02, -0.19, 0.372), (length / 2 - 0.02, 0.19, 0.384), SOIL)
    n = max(3, int(length / 0.20))
    for k in range(n):
        px = -length / 2 + 0.12 + k * (length - 0.24) / max(1, n - 1)
        c, s_ = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        plant(soft, x + px * c - rng.uniform(-0.06, 0.06) * s_, y + px * s_ + rng.uniform(-0.06, 0.06) * c, z + 0.36 - 0.1 * 1.0, size=rng.uniform(1.6, 2.4), seed=seed * 10 + k, pot=SOIL)


def side_table(fb: FB, soft: FB, em: FB, x: float, y: float, z: float, yaw: float = 0.0) -> None:
    """A round pedestal table by the Captain's chair: a dark glass top in a brass ring on a gunmetal column and a lit foot, with a mug, a datapad, a stylus."""
    with fb.at(T(x, y, z) @ Rz(yaw)), em.at(T(x, y, z) @ Rz(yaw)):
        fb.cyl((0, 0, 0.0), (0, 0, 0.03), 0.19, L.STRUCT, seg=28, r2=0.15)
        fb.cyl((0, 0, 0.03), (0, 0, 0.50), 0.045, L.TRIM, seg=20)
        fb.cyl((0, 0, 0.50), (0, 0, 0.55), 0.24, L.STRUCT, seg=32, r2=0.255)
        fb.cyl((0, 0, 0.55), (0, 0, 0.562), 0.225, L.DGLASS, seg=32)
        em.cyl((0, 0, 0.5495), (0, 0, 0.5535), 0.2565, L.BRASS, seg=32)
        em.lamp_arc([(0.150, 0.0), (0.158, 0.0), (0.158, 0.003), (0.150, 0.003)], 0, 0, 0, 0, 360, "command_dim", L.LAMP_DIM, seg=32, z0=0.031, loop=True)
    mug(soft, x + 0.07 * math.cos(math.radians(yaw)) - 0.06 * math.sin(math.radians(yaw)), y + 0.07 * math.sin(math.radians(yaw)) + 0.06 * math.cos(math.radians(yaw)), z + 0.562,
        L.IVORY, True, em, yaw + 40.0)
    datapad(fb, em, x - 0.04 * math.cos(math.radians(yaw)), y - 0.04 * math.sin(math.radians(yaw)), z + 0.562, yaw - 18.0, "log", 0.13)
    with em.at(T(x, y, z + 0.562) @ Rz(yaw)):
        em.cyl((0.05, -0.12, 0.003), (0.15, -0.09, 0.003), 0.0035, L.BRASS, seg=6)


# ------------------------------------------------------------------------------------------------------------ whole props (meshes)
def build_side_table(name: str = "SM_BRG3_SideTable"):
    """The Captain's side table (origin on the floor under its axis): see side_table()."""
    b = L.Parts(bevel=0.004, fine_bevel=0.002)
    side_table(b.body, b.soft, b.emit, 0.0, 0.0, 0.0, 0.0)
    return b.build(name, uv_meter=0.5)


def build_planter(name: str = "SM_BRG3_Planter"):
    """A planter trough with a hedge (origin on the floor at the middle of the trough, its length along y)."""
    b = L.Parts(bevel=0.004, fine_bevel=0.002)
    planter(b.soft, b.body, b.emit, 0.0, 0.0, 0.0, 90.0, length=1.3, seed=5)
    return b.build(name, uv_meter=0.5)


def personal_shelf(b: L.Parts, kind: str, dept: str) -> None:
    """The shelf on the right cheek of a console (the frame of the cheek: x radial, y to the officer's right; its outer face is at y = +0.031):
    a brushed tray with a brass lip on two gussets, and the things of whoever sits here."""
    fb, soft, em = b.body, b.soft, b.emit
    y0, y1, z = 0.034, 0.234, 0.74
    fb.box((0.80, y0, z), (1.08, y1, z + 0.012), L.TRIM)
    em.box((0.80, y1 - 0.005, z + 0.012), (1.08, y1, z + 0.020), L.BRASS)
    em.box((1.075, y0, z + 0.012), (1.08, y1, z + 0.020), L.BRASS)
    for xx in (0.84, 1.04):
        fb.extrude_y([(xx - 0.008, z), (xx + 0.008, z), (xx + 0.008, z - 0.08), (xx - 0.008, z - 0.002)], y0 + 0.004, y0 + 0.010, L.TRIM)
        fb.extrude_y([(xx - 0.008, z), (xx + 0.008, z), (xx + 0.008, z - 0.08), (xx - 0.008, z - 0.002)], y1 - 0.012, y1 - 0.006, L.TRIM)
    zt = z + 0.012
    ym = (y0 + y1) / 2
    if kind == "helm":
        globe(soft, em, 0.90, ym - 0.03, zt, yaw=0.0, r=0.045)
        mug(soft, 1.01, ym + 0.05, zt, L.IVORY, True, em, 150.0)
    elif kind == "ops":
        datapad(fb, em, 0.92, ym, zt, yaw=90.0, page="checklist", w=0.13)
        mug(soft, 1.02, ym + 0.04, zt, L.IVORY, True, em, 20.0)
    elif kind == "comms":
        headset(soft, em, 0.90, ym, zt + 0.21, yaw=0.0)
        mug(soft, 1.01, ym + 0.04, zt, L.IVORY, True, em, 100.0)
    elif kind == "sensors":
        plant(soft, 0.92, ym - 0.02, zt, size=0.9, seed=2)
        datapad(fb, em, 1.02, ym + 0.02, zt, yaw=70.0, page="starmap", w=0.11)
    elif kind == "engineering":
        mug(soft, 0.90, ym + 0.05, zt, L.IVORY, True, em, 210.0)
        photo(fb, em, 1.03, ym, zt, yaw=-90.0, w=0.08, page="orbit")
        cable_coil(soft, 0.93, ym - 0.05, zt, 0.034, 3)
    elif kind == "flight":
        falcon_model(fb, em, 0.93, ym, zt, yaw=-90.0, scale=1.25)
        photo(fb, em, 1.04, ym + 0.06, zt, yaw=-90.0, w=0.07, page="starmap")
