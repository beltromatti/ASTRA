"""ASN Aquila interior kit (ARTE-INTERNI): furniture, second generation. The same pieces as ship_furniture.py (seats, tables, shelves, lamps), with the same frames and footprints
(origin on the floor, x = the piece's front, y = its left, z up) so that the crew's places and the rooms' layouts stay where they are — but built the way furniture is built:
rounded cushions (ship_mk.rbox / puff), padded seats on tapered steel legs, tables with a rolled edge, lamps with a glowing shade, shelves with books of every height and the
small things people keep. ship_furniture.py delegates its older functions here.
"""
from __future__ import annotations

import math
import random

import ship_mk as MK
from bridge3_lib import Rx, Ry, Rz, T
from ship_lib import (DGLASS as SL_DGLASS, TUFT_SAND, CERAMIC, WHITE_GLOSS, BOOK_COLORS, SWATCH, BEDDING, BRASS, COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST, FABRIC_SAND, IVORY, LAMINATE, LAMP, LAMP_DIM, LEATHER_CREAM,
                      LEATHER_NAVY, LEATHER_OX, LEATHER_TAN, OAK, PAPER, RUBBER, STEEL, STRUCT, TRIM, WALNUT, WOOD, SParts)


# --------------------------------------------------------------------------------------------------------------------------------- seats
def chair(b: SParts, seat: str, frame_mat: str = TRIM, h: float = 0.46, w: float = 0.46) -> None:
    """A ship's chair facing +x: a padded seat and back on four tapered steel legs, the back on two posts, a slight lean."""
    hw = w / 2
    for sx, ox in ((-0.18, -0.02), (0.18, 0.02)):
        for sy, oy in ((-hw + 0.045, -0.015), (hw - 0.045, 0.015)):
            MK.rod(b.fine, (sx + ox, sy + oy, 0.0), (sx, sy, h - 0.06), 0.011, 0.016, frame_mat, 8)
    b.body.box((-0.19, -hw + 0.02, h - 0.075), (0.19, hw - 0.02, h - 0.05), frame_mat)
    MK.rbox(b.soft, (-0.215, -hw, h - 0.05), (0.215, hw, h + 0.035), 0.022, seat, 3)
    for sy in (-hw + 0.06, hw - 0.06):
        MK.rod(b.fine, (-0.20, sy, h - 0.04), (-0.235, sy, h + 0.40), 0.011, 0.009, frame_mat, 8)
    MK.rbox(b.soft, (-0.265, -hw + 0.02, h + 0.14), (-0.215, hw - 0.02, h + 0.42), 0.022, seat, 3, rot=Ry(-7.0))


def stool(b: SParts, r: float, h: float, mat: str) -> None:
    """A round padded stool: a rounded seat, a steel column, a foot ring and a heavy foot."""
    b.body.cyl((0, 0, 0.0), (0, 0, 0.02), r * 0.78, STRUCT, seg=20, r2=r * 0.7)
    b.body.cyl((0, 0, 0.02), (0, 0, h - 0.07), 0.026, TRIM, seg=10)
    b.fine.cyl((0, 0, h * 0.34 - 0.01), (0, 0, h * 0.34 + 0.01), r * 0.82, TRIM, seg=24, r2=r * 0.82)
    MK.rbox(b.soft, (-r, -r, h - 0.075), (r, r, h), min(0.045, r * 0.4), mat, 3)


def armchair(b: SParts, mat: str) -> None:
    """A lounge armchair, 0.84 x 0.84 m: a rounded seat cushion, a back pad leaning 12 degrees, two rolled arms, on four short steel legs under a dark plinth."""
    for sx in (-0.34, 0.34):
        for sy in (-0.34, 0.34):
            MK.rod(b.fine, (sx, sy, 0.0), (sx * 0.95, sy * 0.95, 0.09), 0.018, 0.026, TRIM, 8)
    b.body.box((-0.40, -0.39, 0.09), (0.40, 0.39, 0.17), STRUCT)
    MK.rbox(b.soft, (-0.28, -0.30, 0.17), (0.40, 0.30, 0.44), 0.07, mat, 3)                          # seat
    MK.rbox(b.soft, (-0.42, -0.40, 0.17), (-0.20, 0.40, 0.88), 0.08, mat, 3, rot=Ry(-12.0))          # back
    for sy in (-0.395, 0.395):
        MK.rbox(b.soft, (-0.40, sy - 0.07, 0.17), (0.40, sy + 0.07, 0.60), 0.065, mat, 3)            # arms


def sofa(b: SParts, w: float, mat: str, arms: bool = True) -> None:
    """A sofa facing +x, w long along y, 0.9 deep: a plinth on steel legs, a seat cushion and a back cushion for every 0.7 m, rolled arms, and two throw pillows."""
    hw = w / 2
    for sx in (-0.36, 0.36):
        for sy in (-hw + 0.1, hw - 0.1):
            MK.rod(b.fine, (sx, sy, 0.0), (sx * 0.96, sy, 0.1), 0.017, 0.025, TRIM, 8)
    b.body.box((-0.42, -hw + 0.02, 0.10), (0.42, hw - 0.02, 0.19), STRUCT)
    arm_w = 0.17 if arms else 0.03
    inner = w - 2 * arm_w
    n = max(2, int(round(inner / 0.72)))
    cw = inner / n
    for k in range(n):
        y0 = -hw + arm_w + k * cw
        MK.rbox(b.soft, (-0.28, y0 + 0.006, 0.19), (0.43, y0 + cw - 0.006, 0.45), 0.055, mat, 3)
        MK.rbox(b.soft, (-0.44, y0 + 0.006, 0.19), (-0.17, y0 + cw - 0.006, 0.86), 0.07, mat, 3, rot=Ry(-10.0))
    if arms:
        for sy in (-hw, hw - arm_w):
            MK.rbox(b.soft, (-0.43, sy, 0.19), (0.43, sy + arm_w, 0.62), 0.075, mat, 3)
    for k, ypp in enumerate((-hw + arm_w + 0.28, hw - arm_w - 0.28)):                                    # two throw pillows
        pm = (FABRIC_SAND, FABRIC_RUST, FABRIC_NAVY, FABRIC_GREY)[(int(w * 7) + k) % 4]
        MK.puff(b.soft, (-0.12, ypp, 0.58), (0.045, 0.2, 0.2), pm, e=0.55, rot=Ry(-22.0) @ Rx(8.0 if k else -8.0))


def bench(b: SParts, w: float, d: float, h: float, mat: str) -> None:
    """A padded bench: a thick rounded pad on a steel frame with two panel feet."""
    MK.rbox(b.soft, (-d / 2, -w / 2, h - 0.075), (d / 2, w / 2, h), 0.03, mat, 3)
    b.body.box((-d / 2 + 0.025, -w / 2 + 0.03, h - 0.105), (d / 2 - 0.025, w / 2 - 0.03, h - 0.075), TRIM)
    for sy in (-w / 2 + 0.12, w / 2 - 0.12):
        b.body.box((-d / 2 + 0.05, sy - 0.02, 0.0), (d / 2 - 0.05, sy + 0.02, h - 0.105), TRIM)
        b.fine.box((-d / 2 + 0.03, sy - 0.05, 0.0), (d / 2 - 0.03, sy + 0.05, 0.012), STRUCT)


# -------------------------------------------------------------------------------------------------------------------------------- tables
def table(b: SParts, w: float, d: float, h: float, top: str, base: str, pedestal: bool) -> None:
    """A table centred on the origin, w along x, d along y: a top 3.4 cm thick with a rounded edge and a steel edge band, on tapered legs or a pedestal."""
    MK.rbox(b.soft, (-w / 2, -d / 2, h - 0.034), (w / 2, d / 2, h), 0.012, top, 2)
    b.fine.box((-w / 2 + 0.025, -d / 2 + 0.025, h - 0.058), (w / 2 - 0.025, d / 2 - 0.025, h - 0.034), base)
    if pedestal:
        b.body.cyl((0, 0, 0.02), (0, 0, h - 0.058), 0.045, base, seg=14, r2=0.055)
        b.body.cyl((0, 0, 0.0), (0, 0, 0.025), min(0.3, d * 0.34), STRUCT, seg=24, r2=min(0.27, d * 0.31))
        b.fine.cyl((0, 0, h - 0.07), (0, 0, h - 0.058), 0.15, base, seg=16)
    else:
        for sx in (-w / 2 + 0.07, w / 2 - 0.07):
            for sy in (-d / 2 + 0.07, d / 2 - 0.07):
                MK.rod(b.body, (sx, sy, 0.0), (sx * 0.99, sy * 0.99, h - 0.058), 0.014, 0.022, base, 8)


def low_table(b: SParts, w: float, d: float, h: float, mat: str) -> None:
    """A low table: a thick top with a rounded edge, a lower shelf, four slim legs."""
    MK.rbox(b.soft, (-w / 2, -d / 2, h - 0.04), (w / 2, d / 2, h), 0.014, mat, 2)
    b.fine.box((-w / 2 + 0.04, -d / 2 + 0.04, h - 0.075), (w / 2 - 0.04, d / 2 - 0.04, h - 0.04), TRIM)
    if h > 0.3:
        b.body.box((-w / 2 + 0.07, -d / 2 + 0.07, 0.10), (w / 2 - 0.07, d / 2 - 0.07, 0.115), mat)
    for sx in (-w / 2 + 0.05, w / 2 - 0.05):
        for sy in (-d / 2 + 0.05, d / 2 - 0.05):
            MK.rod(b.body, (sx, sy, 0.0), (sx, sy, h - 0.075), 0.013, 0.02, TRIM, 8)


def desk(b: SParts, w: float, d: float, h: float, top: str, drawers: bool) -> None:
    """A desk, its kneehole towards -x: a top with a rounded edge, a steel side frame and a drawer unit with recessed pulls."""
    MK.rbox(b.soft, (-d / 2, -w / 2, h - 0.04), (d / 2, w / 2, h), 0.012, top, 2)
    b.body.box((-d / 2 + 0.03, -w / 2 + 0.02, 0.0), (d / 2 - 0.03, -w / 2 + 0.05, h - 0.04), STRUCT)
    if drawers:
        b.body.box((-d / 2 + 0.03, w / 2 - 0.44, 0.04), (d / 2 - 0.03, w / 2 - 0.02, h - 0.04), COMPOSITE)
        for k in range(3):
            z = 0.1 + k * 0.2
            b.fine.box((-d / 2 + 0.025, w / 2 - 0.40, z), (-d / 2 + 0.03, w / 2 - 0.06, z + 0.17), STRUCT)
            b.fine.box((-d / 2 + 0.005, w / 2 - 0.30, z + 0.12), (-d / 2 + 0.025, w / 2 - 0.16, z + 0.135), TRIM)
    else:
        b.body.box((-d / 2 + 0.03, w / 2 - 0.05, 0.0), (d / 2 - 0.03, w / 2 - 0.02, h - 0.04), STRUCT)
    b.fine.box((d / 2 - 0.06, -w / 2 + 0.05, h - 0.1), (d / 2 - 0.02, w / 2 - 0.05, h - 0.04), STRUCT)         # the modesty panel's lip


# ------------------------------------------------------------------------------------------------------------------------------- lamps
def lamp_standard(b: SParts, h: float, cell: str) -> None:
    """A floor lamp: a heavy round foot, a slim pole, an open conical shade that glows (the shade's inside is the light)."""
    b.fine.cyl((0, 0, 0.0), (0, 0, 0.025), 0.15, STRUCT, seg=24, r2=0.13)
    b.fine.cyl((0, 0, 0.025), (0, 0, h), 0.012, TRIM, seg=8)
    b.fine.cyl((0, 0, h - 0.015), (0, 0, h + 0.005), 0.022, TRIM, seg=10)
    sh = 0.24
    b.emit.lamp_cyl((0, 0, h + 0.005), (0, 0, h + sh), 0.075, cell, LAMP, seg=16, r2=0.12)
    b.fine.cyl((0, 0, h + 0.003), (0, 0, h + sh + 0.003), 0.0765, FABRIC_SAND, seg=16, r2=0.1215, caps=False)


# ---------------------------------------------------------------------------------------------------------------------------- shelves
def shelf(b: SParts, w: float, d: float, h: float, shelves: int, mat: str, books: bool, seed: int, back: bool) -> None:
    """A shelving unit facing +x (back at -d/2), w along y. With `books`: runs of books of every height and colour (some leaning, a pile lying flat) and, here and there, a small
    object — a framed picture, a box, a mug, a pot — so that no shelf is a barcode. The books are plain boxes of the colour swatch (one material, 12 triangles each)."""
    rng = random.Random(seed)
    if back:
        b.body.box((-d / 2, -w / 2, 0.0), (-d / 2 + 0.02, w / 2, h), STRUCT)
    for sy in (-w / 2, w / 2 - 0.03):
        b.body.box((-d / 2, sy, 0.0), (d / 2, sy + 0.03, h), mat)
    zs = [0.05 + k * (h - 0.1) / (shelves - 1) for k in range(shelves)]
    for z in zs:
        b.body.box((-d / 2, -w / 2, z), (d / 2, w / 2, z + 0.025), mat)
    if not books:
        return
    colors = BOOK_COLORS
    for i, z in enumerate(zs[:-1]):
        gap = zs[i + 1] - z - 0.025
        y = -w / 2 + 0.05
        while y < w / 2 - 0.09:
            r = rng.random()
            if r < 0.09:                                                       # an empty stretch
                y += rng.uniform(0.06, 0.16)
            elif r < 0.17 and gap > 0.22:                                      # a small object
                kind = rng.choice(("frame", "box", "mug", "pot"))
                x = -d / 2 + 0.03 + d * 0.18
                if kind == "frame":
                    fw, fh = rng.uniform(0.1, 0.16), rng.uniform(0.12, 0.2)
                    b.fine.swatch_box((x - 0.012, y, z + 0.025), (x + 0.012, y + fw, z + 0.025 + fh), "w_walnut")
                    b.fine.swatch_box((x + 0.012, y + 0.01, z + 0.025 + 0.01), (x + 0.014, y + fw - 0.01, z + 0.025 + fh - 0.01), rng.choice(colors))
                    y += fw + 0.03
                elif kind == "box":
                    bw, bh = rng.uniform(0.1, 0.18), rng.uniform(0.06, 0.12)
                    b.soft.swatch_box((x - 0.07, y, z + 0.025), (x + 0.07, y + bw, z + 0.025 + bh), rng.choice(colors))
                    y += bw + 0.03
                elif kind == "mug":
                    b.fine.cyl((x, y + 0.04, z + 0.025), (x, y + 0.04, z + 0.105), 0.04, rng.choice((LAMINATE, IVORY, LEATHER_NAVY)), seg=10)
                    y += 0.1
                else:
                    b.fine.cyl((x, y + 0.055, z + 0.025), (x, y + 0.055, z + 0.125), 0.055, LEATHER_TAN, seg=10, r2=0.045)
                    y += 0.13
            else:                                                              # a run of books
                run = rng.randint(3, 9)
                lean = rng.random() < 0.18
                for j in range(run):
                    bw = rng.uniform(0.022, 0.055)
                    bh = rng.uniform(0.17, min(0.31, gap - 0.025))
                    bd = rng.uniform(0.17, 0.23)
                    if y + bw > w / 2 - 0.07:
                        break
                    tint = rng.choice(colors)
                    if lean and j == run - 1:
                        faces = b.soft.box((-d / 2 + 0.03, y, z + 0.025), (-d / 2 + 0.03 + bd, y + bw, z + 0.025 + bh), SWATCH, Rx(rng.uniform(8, 14)))
                        b.soft.paint(faces, tint)
                    else:
                        b.soft.swatch_slab((-d / 2 + 0.03, y, z + 0.025), (-d / 2 + 0.03 + bd, y + bw, z + 0.025 + bh), tint, sides=(j == 0 or j == run - 1))     # (ARTE-INTERNI-2: only the faces that are seen)
                        if rng.random() < 0.5:                                  # a gilt line on the spine: one flat quad of the palette's brass, not a lamp box
                            gz = z + 0.025 + bh * 0.62
                            gf = b.soft.face([(-d / 2 + 0.03 + bd + 0.0006, y + 0.004, gz), (-d / 2 + 0.03 + bd + 0.0006, y + bw - 0.004, gz), (-d / 2 + 0.03 + bd + 0.0006, y + bw - 0.004, gz + 0.006),
                                              (-d / 2 + 0.03 + bd + 0.0006, y + 0.004, gz + 0.006)], SWATCH, (1, 0, 0))
                            b.soft.paint([gf], "brass")
                    y += bw + 0.003
                if rng.random() < 0.3 and gap > 0.2:                            # a pile lying flat at the end of the run
                    for t in range(rng.randint(2, 4)):
                        bw2 = rng.uniform(0.14, 0.2)
                        if y + bw2 > w / 2 - 0.07:
                            break
                        b.soft.swatch_box((-d / 2 + 0.035, y, z + 0.025 + t * 0.03), (-d / 2 + 0.035 + 0.2, y + bw2, z + 0.025 + (t + 1) * 0.03), rng.choice(colors))
                    y += 0.2


# ---------------------------------------------------------------------------------------------------------------------------- beds
def bunk_bed(b: SParts, l: float, w: float, levels: int, blanket: str, seed: int) -> None:
    """A crew bunk, head at -x, open side +y (the ladder). Steel tube posts and rails, a slatted base, a 12 cm mattress with a sheet, a rounded pillow and a blanket folded back at the
    head; a privacy curtain hanging from the rail of the open side, drawn back at one end; a reading lamp with its switch, a net pocket with a book and a photograph, a number plate.
    The mattress tops are at 0.50 m and 1.46 m: the height the sleepers lie at (AstraLifeData: 60 cm above the station for the lower bunk, +0.96 for the upper)."""
    rng = random.Random(seed)
    hl, hw = l / 2, w / 2
    zs = [0.36, 1.32][:levels] if levels == 2 else [0.40]
    top = 1.90 if levels == 2 else 1.0
    for sx in (-hl, hl - 0.05):
        for sy in (-hw, hw - 0.05):
            MK.rbox(b.soft, (sx, sy, 0.0), (sx + 0.05, sy + 0.05, top), 0.012, TRIM, 1)
    for k, z in enumerate(zs):
        b.body.box((-hl, -hw, z - 0.07), (hl, hw, z - 0.03), STRUCT)
        for sx in (-hl + 0.05, hl - 0.07):
            b.body.box((sx, -hw + 0.04, z - 0.09), (sx + 0.02, hw - 0.04, z - 0.03), TRIM)
        for j in range(6):                                                                    # the slats
            b.fine.box((-hl + 0.12 + j * (l - 0.24) / 5 - 0.03, -hw + 0.03, z - 0.03), (-hl + 0.12 + j * (l - 0.24) / 5 + 0.03, hw - 0.03, z - 0.012), COMPOSITE)
        MK.rbox(b.soft, (-hl + 0.035, -hw + 0.035, z - 0.012), (hl - 0.035, hw - 0.035, z + 0.12), 0.04, BEDDING, 2)                                         # mattress and sheet
        MK.rbox(b.soft, (-hl + 0.60, -hw + 0.03, z + 0.09), (hl - 0.03, hw - 0.03, z + 0.165), 0.03, blanket, 2)                                       # blanket
        MK.rbox(b.soft, (-hl + 0.545, -hw + 0.03, z + 0.10), (-hl + 0.62, hw - 0.03, z + 0.17), 0.025, BEDDING, 2)                                       # the fold
        MK.puff(b.soft, (-hl + 0.27, 0.0, z + 0.19), (0.2, w * 0.3, 0.07), BEDDING, e=0.6)                                                               # the pillow
        # the reading lamp on the wall end, with its switch
        b.fine.box((-hl + 0.055, hw - 0.30, z + 0.58), (-hl + 0.085, hw - 0.18, z + 0.64), TRIM)
        b.emit.lamp_box((-hl + 0.085, hw - 0.285, z + 0.595), (-hl + 0.095, hw - 0.195, z + 0.625), "white_warm" if rng.random() > 0.3 else "warm_dim", LAMP_DIM)
        # the net pocket: a book and a photograph
        b.soft.box((-hl + 0.06, -hw + 0.12, z + 0.30), (-hl + 0.09, -hw + 0.46, z + 0.44), FABRIC_GREY)
        b.soft.swatch_box((-hl + 0.09, -hw + 0.16, z + 0.32), (-hl + 0.105, -hw + 0.28, z + 0.40), BOOK_COLORS[(seed * 3 + k) % len(BOOK_COLORS)])
        b.fine.swatch_box((-hl + 0.09, -hw + 0.32, z + 0.38), (-hl + 0.095, -hw + 0.40, z + 0.46), "paper")
    if levels == 2:
        b.body.box((-hl + 0.1, -hw, zs[1] + 0.12), (hl - 0.1, -hw + 0.025, zs[1] + 0.40), TRIM)               # the guard on the wall side
        b.body.box((-hl + 0.1, hw - 0.025, zs[1] + 0.12), (-hl + 0.9, hw, zs[1] + 0.34), TRIM)                # a short guard on the open side
        for k in range(5):                                                                                       # the ladder
            z = 0.30 + k * 0.28
            b.fine.cyl((hl - 0.42, hw + 0.02, z), (hl - 0.22, hw + 0.02, z), 0.013, TRIM, seg=6)
        b.fine.cyl((hl - 0.42, hw + 0.02, 0.2), (hl - 0.42, hw + 0.02, 1.55), 0.012, TRIM, seg=6)
        b.fine.cyl((hl - 0.22, hw + 0.02, 0.2), (hl - 0.22, hw + 0.02, 1.55), 0.012, TRIM, seg=6)
    # the privacy curtains along the open side: pleated panels hanging from the frame, drawn over the foot half of each bunk
    pleats = 8
    cw = 0.95 / pleats
    for k, z in enumerate(zs):
        z_top = (zs[1] - 0.04) if (levels == 2 and k == 0) else (top - 0.08)
        z_bot = z + 0.02
        for j in range(pleats):
            x0 = hl - 1.1 + j * cw
            off = 0.012 * (1 if j % 2 else -1)
            b.soft.box((x0, hw + 0.012 + off, z_bot), (x0 + cw * 0.96, hw + 0.03 + off, z_top), (FABRIC_GREY, FABRIC_NAVY, FABRIC_SAND)[(seed + k) % 3])
        b.fine.cyl((hl - 1.12, hw + 0.01, z_top), (hl - 0.12, hw + 0.01, z_top), 0.007, TRIM, seg=6)
    # a number plate on the post
    b.emit.lamp_box((hl - 0.056, -hw + 0.012, 1.55), (hl - 0.05, -hw + 0.036, 1.62), "cool_dim", LAMP_DIM)


def officer_bed(b: SParts, w: float, l: float, blanket: str) -> None:
    """An officer's bed, head at -x, foot at +x: a walnut platform on a recessed plinth, a mattress with a turned-down duvet draped over the sides, a throw across the foot, two pillows and a
    bolster, an upholstered headboard in a walnut frame with two reading lights, a drawer front under the foot. The mattress top is at 0.52 m (the sleeper lies 0.60 m above the floor)."""
    b.body.box((-l / 2 + 0.06, -w / 2 + 0.05, 0.0), (l / 2 - 0.06, w / 2 - 0.05, 0.10), STRUCT)
    MK.rbox(b.soft, (-l / 2, -w / 2, 0.10), (l / 2, w / 2, 0.36), 0.02, WALNUT, 2)
    MK.rbox(b.soft, (-l / 2 + 0.03, -w / 2 + 0.03, 0.36), (l / 2 - 0.03, w / 2 - 0.03, 0.53), 0.05, BEDDING, 2)                                  # the mattress
    MK.rbox(b.soft, (-l / 2 + 0.72, -w / 2 - 0.015, 0.40), (l / 2 + 0.01, w / 2 + 0.015, 0.575), 0.04, blanket, 2)                                # the duvet, hanging over the sides
    MK.rbox(b.soft, (-l / 2 + 0.66, -w / 2 - 0.01, 0.50), (-l / 2 + 0.78, w / 2 + 0.01, 0.585), 0.03, BEDDING, 2)                                  # the turn-down
    b.soft.swatch_box((l / 2 - 0.62, -w / 2 - 0.016, 0.572), (l / 2 - 0.40, w / 2 + 0.016, 0.585), ("mustard", "rust", "teal", "cream")[int(w * 7) % 4])   # a throw across the foot
    for k, yc in enumerate((-w * 0.22, w * 0.22)):
        MK.puff(b.soft, (-l / 2 + 0.3, yc, 0.60), (0.22, 0.28, 0.075), BEDDING, e=0.6, rot=Ry(-6.0))
    MK.puff(b.soft, (-l / 2 + 0.17, 0.0, 0.67), (0.09, w * 0.4, 0.075), FABRIC_SAND, e=0.8, rot=Ry(-6.0))
    MK.rbox(b.soft, (-l / 2 - 0.09, -w / 2 - 0.03, 0.0), (-l / 2 - 0.02, w / 2 + 0.03, 1.05), 0.02, WALNUT, 2)                                       # the headboard frame
    MK.rbox(b.soft, (-l / 2 - 0.02, -w / 2 + 0.04, 0.46), (-l / 2 + 0.035, w / 2 - 0.04, 0.98), 0.02, TUFT_SAND, 2)
    for sy in (-w * 0.3, w * 0.3):
        b.fine.box((-l / 2 - 0.0, sy - 0.07, 0.86), (-l / 2 + 0.07, sy + 0.07, 0.9), BRASS)
        b.emit.lamp_box((-l / 2 + 0.07, sy - 0.05, 0.862), (-l / 2 + 0.072, sy + 0.05, 0.897), "white_warm", LAMP_DIM)
    b.fine.box((l / 2 - 0.02, -w / 2 + 0.1, 0.16), (l / 2 + 0.01, w / 2 - 0.1, 0.32), STRUCT)                                                      # a drawer under the foot
    b.fine.box((l / 2 + 0.01, -0.1, 0.25), (l / 2 + 0.03, 0.1, 0.265), BRASS)


def wardrobe(b: SParts, w: float, d: float, h: float, mat: str) -> None:
    """A tall wardrobe facing +x: walnut carcass on a recessed plinth, two flush doors with a recessed panel and a slim brass pull, a lit slot above, a crown."""
    b.body.box((-d / 2 + 0.03, -w / 2 + 0.03, 0.0), (d / 2 - 0.03, w / 2 - 0.03, 0.08), STRUCT)
    MK.rbox(b.soft, (-d / 2, -w / 2, 0.08), (d / 2, w / 2, h), 0.012, mat if mat != COMPOSITE else WALNUT, 2)
    for k, y0 in enumerate((-w / 2, 0.0)):
        b.fine.box((d / 2, y0 + 0.012, 0.14), (d / 2 + 0.012, y0 + w / 2 - 0.012, h - 0.18), IVORY if mat == COMPOSITE else OAK)
        b.fine.box((d / 2 + 0.012, y0 + 0.05, 0.2), (d / 2 + 0.018, y0 + w / 2 - 0.05, h - 0.24), WALNUT)
        yp = y0 + (w / 2 - 0.07 if k == 0 else 0.07)
        b.fine.box((d / 2 + 0.012, yp - 0.008, h * 0.45), (d / 2 + 0.035, yp + 0.008, h * 0.45 + 0.28), BRASS)
    b.emit.lamp_box((d / 2 + 0.012, -w / 2 + 0.06, h - 0.14), (d / 2 + 0.016, w / 2 - 0.06, h - 0.12), "warm_dim", LAMP_DIM)


def vanity(b: SParts, w: float, d: float) -> None:
    """A washbasin unit facing +x: a walnut cabinet with two drawers, a white top with a ceramic basin sunk in it, a brass tap, a framed mirror with a lit edge, a cup with a toothbrush, a rail
    with a towel."""
    MK.rbox(b.soft, (-d / 2, -w / 2, 0.06), (d / 2, w / 2, 0.82), 0.01, WALNUT, 2)
    b.body.box((-d / 2 + 0.03, -w / 2 + 0.03, 0.0), (d / 2 - 0.03, w / 2 - 0.03, 0.06), STRUCT)
    MK.rbox(b.soft, (-d / 2 - 0.015, -w / 2 - 0.015, 0.82), (d / 2 + 0.015, w / 2 + 0.015, 0.855), 0.008, WHITE_GLOSS, 2)
    MK.lathe(b.fine, [(0.12, 0.84), (0.19, 0.855), (0.2, 0.86), (0.17, 0.86), (0.1, 0.80), (0.09, 0.80)], (0.0, 0.0, 0.0), CERAMIC, seg=20)
    b.fine.cyl((-0.2, 0.0, 0.855), (-0.2, 0.0, 1.0), 0.012, BRASS, seg=8)
    b.fine.cyl((-0.2, 0.0, 1.0), (-0.1, 0.0, 1.0), 0.012, BRASS, seg=8)
    for z in (0.18, 0.5):
        b.fine.box((d / 2, -w / 2 + 0.03, z), (d / 2 + 0.012, w / 2 - 0.03, z + 0.28), OAK)
        b.fine.box((d / 2 + 0.012, -0.1, z + 0.22), (d / 2 + 0.03, 0.1, z + 0.235), BRASS)
    b.fine.box((-d / 2 - 0.0, -w / 2 + 0.06, 1.28), (-d / 2 + 0.03, w / 2 - 0.06, 1.98), TRIM)
    b.fine.box((-d / 2 + 0.03, -w / 2 + 0.08, 1.30), (-d / 2 + 0.035, w / 2 - 0.08, 1.96), STEEL)                                  # the mirror
    b.emit.lamp_box((-d / 2 + 0.03, -w / 2 + 0.06, 1.97), (-d / 2 + 0.05, w / 2 - 0.06, 2.0), "white_warm", LAMP)
    b.fine.cyl((-d / 2 + 0.1, w / 2 - 0.1, 0.855), (-d / 2 + 0.1, w / 2 - 0.1, 0.93), 0.03, CERAMIC, seg=10)
    b.fine.cyl((-d / 2 + 0.1, w / 2 - 0.1, 0.9), (-d / 2 + 0.11, w / 2 - 0.09, 1.0), 0.004, STEEL, seg=5)
    b.fine.cyl((-d / 2 + 0.02, -w / 2 + 0.05, 1.05), (-d / 2 + 0.02, -w / 2 + 0.4, 1.05), 0.008, BRASS, seg=6)
    b.soft.box((-d / 2 + 0.005, -w / 2 + 0.06, 0.78 + 0.28), (-d / 2 + 0.03, -w / 2 + 0.38, 1.06), BEDDING)
