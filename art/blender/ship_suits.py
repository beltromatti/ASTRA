"""ASN Aquila interior kit (ARTE-INTERNI-2): EVA suits and what goes with them. The suit lockers, the airlocks and the repair bay had white mannequins made of boxes; this is a suit — a hard
upper torso with a control panel and its lamps, bearings at the shoulders, the waist and the wrists, bellows at the elbows and knees, a backpack with its hoses, a helmet with a dark visor
and two lamps, gloves and boots — in the same frame as the furniture (origin on the floor under the suit, the front towards +x), hung from a hook at the shoulders so the boots stand just
above the floor. About 2 000 triangles a suit; the finishes are the ship's own (white ceramic, brushed steel, the palette's orange and charcoal, dark glass).
"""
from __future__ import annotations

from mathutils import Vector

import ship_mk as MK
from bridge3_lib import T
from ship_lib import BRASS, CERAMIC, COMPOSITE, DGLASS, LAMP_DIM, STEEL, STRUCT, SWATCH, TRIM, SParts


def _bellows(b: SParts, z0: float, z1: float, y: float, r: float, x: float = 0.04, n: int = 4) -> None:
    """A concertina joint (a knee): a stack of `n` ridges between z0 and z1 round the vertical axis through (x, y)."""
    prof = [(r * 0.86, z0)]
    for k in range(n):
        za = z0 + (z1 - z0) * (k + 0.5) / n
        d = (z1 - z0) / n * 0.2
        prof += [(r, za - d), (r * 1.14, za), (r, za + d)]
    prof.append((r * 0.86, z1))
    MK.lathe(b.soft, prof, (x, y, 0.0), CERAMIC, seg=14)


def _band(b: SParts, p: Vector, d: Vector, r: float, color: str, w: float = 0.04) -> None:
    """A coloured band round a limb at p (the limb runs along d)."""
    u = d.normalized() * (w / 2)
    b.soft.paint(b.soft.cyl(tuple(p - u), tuple(p + u), r, SWATCH, seg=12), color)


def eva_suit(b: SParts, seed: int = 1, stripe: str = "orange") -> None:
    """One EVA suit hanging (origin on the floor under it, facing +x; the crown of the helmet at 2.1 m, the boots 6 cm off the floor)."""
    zb = 0.06
    for sy in (-0.1, 0.1):                                                                                          # legs: a boot (rounded block, rubber sole), the shin, the knee, the thigh
        b.soft.paint(MK.rbox(b.soft, (-0.08, sy - 0.062, zb + 0.03), (0.22, sy + 0.062, zb + 0.15), 0.035, SWATCH, 2), "charcoal")
        b.soft.paint(MK.rbox(b.soft, (-0.09, sy - 0.066, zb), (0.23, sy + 0.066, zb + 0.035), 0.012, SWATCH, 1), "grey2")
        b.fine.cyl((0.04, sy, zb + 0.15 - 0.015), (0.04, sy, zb + 0.15 + 0.015), 0.085, STEEL, seg=14)                 # the ankle bearing
        MK.lathe(b.soft, [(0.074, zb + 0.165), (0.084, zb + 0.22), (0.09, zb + 0.46), (0.084, zb + 0.58)], (0.04, sy, 0.0), CERAMIC, seg=14)
        _bellows(b, zb + 0.58, zb + 0.7, sy, 0.088, 0.04, 4)
        MK.lathe(b.soft, [(0.088, zb + 0.7), (0.1, zb + 0.84), (0.108, zb + 0.96), (0.106, zb + 1.0)], (0.0, sy, 0.0), CERAMIC, seg=14)
    b.soft.paint(MK.rbox(b.soft, (-0.15, -0.2, zb + 0.96), (0.15, 0.2, zb + 1.1), 0.06, SWATCH, 2), "cream")        # the pelvis
    b.fine.cyl((0, 0, zb + 1.1), (0, 0, zb + 1.14), 0.215, STEEL, seg=18)                                           # the waist bearing
    MK.rbox(b.soft, (-0.17, -0.26, zb + 1.14), (0.16, 0.26, zb + 1.7), 0.09, CERAMIC, 2)                            # the hard upper torso
    b.soft.paint(b.soft.box((0.158, -0.262, zb + 1.18), (0.169, 0.262, zb + 1.22), SWATCH), stripe)                 # the stripe round the chest
    b.fine.box((0.157, -0.12, zb + 1.28), (0.172, 0.12, zb + 1.5), STRUCT)                                          # the chest control panel: lamps, three knobs, a nameplate
    for k, cell in enumerate(("green", "amber", "cyan", "green")):
        b.emit.lamp_box((0.172, -0.095 + k * 0.05, zb + 1.46), (0.176, -0.065 + k * 0.05, zb + 1.48), cell, LAMP_DIM)
    for k in range(3):
        b.fine.cyl((0.172, -0.07 + k * 0.07, zb + 1.35), (0.185, -0.07 + k * 0.07, zb + 1.35), 0.014, TRIM, seg=8)
    b.fine.box((0.168, -0.095, zb + 1.295), (0.176, 0.095, zb + 1.32), BRASS)
    for sy in (-1, 1):                                                                                              # arms: a bearing, the upper arm, the elbow, the forearm, the wrist, the glove
        sh = Vector((0.0, sy * 0.29, zb + 1.56))
        el = Vector((0.045, sy * 0.35, zb + 1.27))
        wr = Vector((0.09, sy * 0.38, zb + 1.0))
        MK.puff(b.soft, tuple(sh), (0.105, 0.1, 0.105), CERAMIC, e=1.0, nu=12, nv=7)
        b.soft.cyl(tuple(sh), tuple(el), 0.078, CERAMIC, seg=12, r2=0.068)
        _band(b, sh + (el - sh) * 0.45, el - sh, 0.081, stripe)
        b.soft.cyl(tuple(el + Vector((0, 0, 0.035))), tuple(el - Vector((0, 0, 0.035))), 0.08, CERAMIC, seg=12)     # the elbow joint
        b.soft.cyl(tuple(el), tuple(wr), 0.068, CERAMIC, seg=12, r2=0.056)
        b.fine.cyl(tuple(wr + Vector((0, 0, 0.014))), tuple(wr - Vector((0, 0, 0.014))), 0.066, STEEL, seg=12)      # the wrist ring
        b.soft.paint(MK.rbox(b.soft, (wr.x - 0.055, wr.y - 0.06, wr.z - 0.19), (wr.x + 0.07, wr.y + 0.06, wr.z - 0.012), 0.04, SWATCH, 2), "grey1")     # the glove and its thumb
        b.soft.paint(MK.rbox(b.soft, (wr.x + 0.02, wr.y + sy * 0.035, wr.z - 0.12), (wr.x + 0.08, wr.y + sy * 0.08, wr.z - 0.05), 0.02, SWATCH, 1), "grey1")
    b.fine.cyl((0.0, 0.0, zb + 1.7), (0.0, 0.0, zb + 1.76), 0.125, STEEL, seg=16)                                   # the neck ring and the helmet
    MK.puff(b.soft, (0.0, 0.0, zb + 1.92), (0.22, 0.215, 0.22), CERAMIC, e=1.0, nu=18, nv=10)
    MK.puff(b.soft, (0.1, 0.0, zb + 1.93), (0.15, 0.175, 0.145), DGLASS, e=0.9, nu=14, nv=8)
    for sy in (-1, 1):
        b.emit.lamp_box((0.07, sy * 0.215 - 0.02, zb + 2.0), (0.12, sy * 0.215 + 0.02, zb + 2.03), "white_cool", LAMP_DIM)
    b.fine.box((0.14, -0.03, zb + 2.1), (0.2, 0.03, zb + 2.14), STRUCT)                                              # a camera on the crown
    b.soft.paint(MK.rbox(b.soft, (-0.36, -0.21, zb + 1.18), (-0.17, 0.21, zb + 1.72), 0.07, SWATCH, 2), "grey3")    # the backpack, a stripe, a status lamp
    b.soft.paint(b.soft.box((-0.364, -0.21, zb + 1.5), (-0.17, 0.21, zb + 1.55), SWATCH), stripe)
    b.emit.lamp_box((-0.366, -0.06, zb + 1.62), (-0.36, 0.06, zb + 1.66), "red", LAMP_DIM)
    for sy in (-1, 1):                                                                                              # two hoses from the chest to the pack, over the shoulders
        b.soft.paint(b.soft.tube([(0.16, sy * 0.1, zb + 1.4), (0.14, sy * 0.22, zb + 1.34), (0.0, sy * 0.275, zb + 1.3), (-0.17, sy * 0.19, zb + 1.3)], 0.016, SWATCH, seg=6, caps=False),
                     "charcoal")


def eva_helmet(b: SParts) -> None:
    """A helmet on its own (a shelf, a bench): the dome, the dark visor, the neck ring, the two lamps (origin under it on the surface)."""
    MK.puff(b.soft, (0.0, 0.0, 0.22), (0.22, 0.215, 0.22), CERAMIC, e=1.0, nu=16, nv=9)
    MK.puff(b.soft, (0.1, 0.0, 0.23), (0.15, 0.175, 0.145), DGLASS, e=0.9, nu=12, nv=7)
    b.fine.cyl((0, 0, 0.0), (0, 0, 0.05), 0.125, STEEL, seg=14)
    for sy in (-1, 1):
        b.emit.lamp_box((0.07, sy * 0.215 - 0.02, 0.3), (0.12, sy * 0.215 + 0.02, 0.33), "white_cool", LAMP_DIM)


def eva_rack(b: SParts, n: int = 4, seed: int = 1) -> None:
    """A wall rack of EVA suits, facing +x (origin on the floor at the middle of the wall panel): a steel back panel with a hook rail high over the helmets, `n` suits hanging from
    it by their backpacks 0.9 m apart (the suit stands clear of the panel, its pack against it), a boot tray along the foot. A rack is 0.7 m deep."""
    pitch = 0.9
    w = n * pitch
    b.body.box((-0.1, -w / 2, 0.0), (-0.04, w / 2, 2.45), COMPOSITE)
    b.body.box((-0.1, -w / 2, 2.45), (0.5, w / 2, 2.5), TRIM)
    b.fine.cyl((-0.01, -w / 2 + 0.05, 2.3), (-0.01, w / 2 - 0.05, 2.3), 0.012, STEEL, seg=8)                        # the hook rail
    b.body.box((-0.05, -w / 2, 0.0), (0.7, w / 2, 0.05), STRUCT)                                                      # the boot tray
    for k in range(n):
        y = -w / 2 + pitch / 2 + k * pitch
        with b.at(T(0.39, y, 0.0)):
            eva_suit(b, seed + k, ("orange", "orange", "mustard", "orange")[k % 4])
        for sy in (-0.12, 0.12):                                                                                         # the hanger straps: from the rail down to the top of the pack
            b.fine.box((0.0, y + sy - 0.012, 1.86), (0.03, y + sy + 0.012, 2.3), STEEL)
