"""ASN Aquila interior kit: the signs — the door plates (SM_SHIP_Plate_<plate>: the room's name over its door on the corridor face) and the
section signs of the blast door frames (SM_SHIP_Sign_<deck><section>: "DECK 4 · SECTION B", both faces).

Plate frame: origin at the plate's centre, its back on x = 0 against the wall, the face towards +x (the layout turns it to face the corridor).
Sign frame: origin at the sign's centre, readable from both sides (x = +-0.0265)."""
from __future__ import annotations

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
