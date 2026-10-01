"""ASN Aquila interior kit: the signs — the door plates (SM_SHIP_Plate_<plate>: the room's name over its door on the corridor face) and the
section signs of the blast door frames (SM_SHIP_Sign_<deck><section>: "DECK 4 · SECTION B", both faces).

Plate frame: origin at the plate's centre, its back on x = 0 against the wall, the face towards +x (the layout turns it to face the corridor).
Sign frame: origin at the sign's centre, readable from both sides (x = +-0.0265)."""
from __future__ import annotations

import ship_catalog as CAT
from ship_lib import DGLASS, LAMP, LAMP_DIM, STRUCT, TRIM, SParts

PLATE_W = 1.36                 # the plate's label width (the 8:1 tile of the atlas: 0.17 m tall)
SIGN_W = 1.70                  # the section sign's label width


def plate(name: str, key: str):
    """The name plate over a room's door: a brushed frame, a dark glass backing, the lit label, a warm lamp line along the top."""
    tile = f"room_{key}"
    b = SParts(bevel=0.004, fine_bevel=0.002)
    w = PLATE_W
    h = w / 8.0
    b.body.box((0.0, -w / 2 - 0.035, -h / 2 - 0.035), (0.036, w / 2 + 0.035, h / 2 + 0.035), TRIM)
    b.body.box((0.030, -w / 2, -h / 2), (0.040, w / 2, h / 2), DGLASS)
    b.emit.label((0.0405, 0.0, 0.0), w, h, (1, 0, 0), tile)
    b.emit.lamp_box((0.030, -w / 2, h / 2 + 0.036), (0.038, w / 2, h / 2 + 0.043), "white_warm", LAMP_DIM)
    return b.build(name)


def sign(name: str, deck: int, section: str):
    """A section sign for the frame of a blast door: readable from both sides."""
    tile = f"sec_{deck}{section}"
    b = SParts(bevel=0.004, fine_bevel=0.002)
    w = SIGN_W
    h = w / 8.0
    b.body.box((-0.025, -w / 2 - 0.03, -h / 2 - 0.03), (0.025, w / 2 + 0.03, h / 2 + 0.03), TRIM)
    b.body.box((-0.0262, -w / 2, -h / 2), (0.0262, w / 2, h / 2), DGLASS)
    b.emit.label((0.0265, 0.0, 0.0), w, h, (1, 0, 0), tile)
    b.emit.label((-0.0265, 0.0, 0.0), w, h, (-1, 0, 0), tile)
    b.emit.lamp_box((-0.02, -w / 2 - 0.028, -h / 2 - 0.036), (0.02, w / 2 + 0.028, -h / 2 - 0.031), "white_cool", LAMP_DIM)
    return b.build(name)


# ------------------------------------------------------------------------------------------------------------------------------------------------ wayfinding (docs/NAVE.md, Wayfinding)
WAY_W = 2.0
WAY_ICON = 0.26
WAY_DEST_W, WAY_DEST_H = 1.20, 0.20  # the 6:1 destination tile of the atlas
WAY_ARROW = {"A": "arrow_ahead", "L": "arrow_left", "R": "arrow_right"}
WAY_ICONS = {"lift": "pict_lift", "stairs": "pict_stairs", "med": "pict_med", "pods": "pict_pods", "bridge": "pict_bridge", "mess": "pict_galley", "engineering": "pict_engine",
             "flight": "pict_flight", "shuttle": "pict_shuttle", "brig": "pict_brig"}


def way_row(code: str) -> tuple[str, str]:
    """'liftA' -> ('lift', 'A'): a destination and where it lies for the one who reads the sign (A ahead, L left, R right)."""
    dest, arrow = code[:-1], code[-1]
    if dest not in WAY_ICONS or arrow not in WAY_ARROW:
        raise ValueError(f"blade sign row {code!r}")
    return dest, arrow


def way_blade(name: str, rows: int):
    """The frame of a blade sign hung from the ceiling across a corridor (SM_SHIP_WayBlade_<rows>): origin at the ceiling on the corridor's axis, the face towards +x (the layout turns it
    to the one who walks towards it), the back plain; two rods, a brushed frame, a dark glass, a white lamp line over it and a cyan one under it. The rows (SM_SHIP_WayRow_*) are placed on
    it by the plan: a pair of blades back to back says one thing to each direction of walking."""
    w, h = WAY_W, rows * CAT.WAY_ROW_H + 2 * CAT.WAY_FRAME_PAD
    top = -CAT.WAY_HANGER
    bot = top - h
    b = SParts(bevel=0.004, fine_bevel=0.002)
    b.body.box((0.0, -w / 2 - 0.035, bot - 0.035), (0.036, w / 2 + 0.035, top + 0.035), TRIM)
    b.body.box((0.030, -w / 2, bot), (0.040, w / 2, top), DGLASS)
    b.emit.lamp_box((0.028, -w / 2, top + 0.036), (0.038, w / 2, top + 0.043), "white_cool", LAMP_DIM)
    b.emit.lamp_box((0.028, -w / 2, bot - 0.043), (0.038, w / 2, bot - 0.036), "cyan_dim", LAMP_DIM)
    for y in (-0.7, 0.7):
        b.fine.cyl((0.018, y, top + 0.035), (0.018, y, 0.0), 0.012, TRIM, seg=8)
    return b.build(name)


def way_row_mesh(name: str, code: str):
    """One row of a blade sign (SM_SHIP_WayRow_<dest><arrow>): origin on the face's plane in the middle of the row, the face towards +x: the destination's pictogram, its name, an arrow."""
    dest, arrow = way_row(code)
    b = SParts(bevel=0.004, fine_bevel=0.002)
    xi = WAY_W / 2 - 0.10 - WAY_ICON / 2                  # (the layout is left-handed: for the one who reads a face turned to +x the left is +y)
    xa = -WAY_W / 2 + 0.10 + WAY_ICON / 2
    b.emit.label((0.0405, xi, 0.0), WAY_ICON, WAY_ICON, (1, 0, 0), WAY_ICONS[dest])
    b.emit.label((0.0405, 0.0, 0.0), WAY_DEST_W, WAY_DEST_H, (1, 0, 0), f"dest_{dest}")
    b.emit.label((0.0405, xa, 0.0), WAY_ICON, WAY_ICON, (1, 0, 0), WAY_ARROW[arrow])
    return b.build(name)


FRAME_DIGIT_H = 0.17


def frame_plate(name: str, n: int):
    """The frame number on a wall or a bulkhead ("FR 134": the ship's ordinates, one per 4 m from the bow, frame 0 at x = +216): back on x = 0, the face towards +x."""
    s = str(n)
    wd, wf = FRAME_DIGIT_H * 64 / 96, FRAME_DIGIT_H
    w = 0.06 + wf + 0.03 + wd * len(s)
    h = FRAME_DIGIT_H + 0.06
    b = SParts(bevel=0.004, fine_bevel=0.002)
    b.body.box((0.0, -w / 2 - 0.02, -h / 2 - 0.02), (0.030, w / 2 + 0.02, h / 2 + 0.02), TRIM)
    b.body.box((0.024, -w / 2, -h / 2), (0.034, w / 2, h / 2), DGLASS)
    y = w / 2 - 0.03 - wf / 2                          # (reading from the left, which is +y on a face turned to +x)
    b.emit.label((0.0345, y, 0.0), wf, FRAME_DIGIT_H, (1, 0, 0), "dg_fr")
    y -= wf / 2 + 0.03 + wd / 2
    for ch in s:
        b.emit.label((0.0345, y, 0.0), wd, FRAME_DIGIT_H, (1, 0, 0), f"dg_{ch}")
        y -= wd
    return b.build(name)


def directory(name: str, deck: int):
    """The deck's directory on a lobby's wall: origin on the floor, the back on x = 0, the face towards +x; a 1.5 x 0.84 m screen in a brushed frame at 1.25 m, a lamp line under it."""
    w, h = 1.5, 1.5 * 288 / 512
    z0 = 1.25
    b = SParts(bevel=0.004, fine_bevel=0.002)
    b.body.box((0.0, -w / 2 - 0.05, z0 - 0.05), (0.05, w / 2 + 0.05, z0 + h + 0.05), TRIM)
    b.body.box((0.044, -w / 2, z0), (0.054, w / 2, z0 + h), DGLASS)
    b.emit.label((0.0545, 0.0, z0 + h / 2), w, h, (1, 0, 0), f"scr_dir_{deck}")
    b.emit.lamp_box((0.04, -w / 2, z0 - 0.058), (0.05, w / 2, z0 - 0.052), "cyan_dim", LAMP_DIM)
    return b.build(name)
