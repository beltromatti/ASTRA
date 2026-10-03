"""ASN Aquila — the Medbay (Deck 6 · Section C), rebuilt in the kit's language (ARTE-INTERNI). SM_MED_Ward of art/blender/medbay.py, same frame and same places (data/ship/aquila_medbay.json:
the ward runs aft of the lift on x 0 .. -30, y +-9, the twelve beds six a side with their heads on the side walls, the duty desk and the records by the entrance on the starboard side, the
supply wall by it on the port side, the central console, the glass partition of the operating theatre at x -23.8 and the theatre behind it), but with the shell, the light and the dressing
of the rooms of the plan: white tile to the rail and teal cloth between the pilasters that stand where the beds' bays divide, flush light panels over the beds and the aisle (the actor lights
of build_medbay.py are the same ones), a ceiling with its beams, ducts, grilles and sprinklers, pleated curtains on their tracks, a bedside cabinet and a visitor's chair at every bed, a
proper nurses' station, a supply wall of cabinets full of stores, a central console with its boards, the theatre with its table, twin lamps, anaesthesia machine, instrument trolleys, a
scanner, a crash cart, sterile cabinets and a big display. The room is built in its own frame (x aft from the forward wall, y from the starboard wall) and turned into the ward's frame by
one transform. The glass of the cabinets and the mirrors goes to SM_MED_Glass (translucent: not Nanite) through the list the caller passes.

  blender -b --factory-startup --python-exit-code 1 -P art/blender/ship_medbay.py -- [--preview <dir>] [--samples N]
(the FBX export stays with medbay.py, which calls ward() here).
"""
from __future__ import annotations

import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import ship_decor as DC  # noqa: E402
import ship_furn4 as MD  # noqa: E402
import ship_furniture as F  # noqa: E402
import ship_lib as SL  # noqa: E402
import ship_mk as MK  # noqa: E402
import ship_shell as SH  # noqa: E402
import ship_themes as TH  # noqa: E402
from bridge3_lib import Ry, Rz, T, frame  # noqa: E402
from ship_lib import (BEDDING, BRASS, COMPOSITE, FABRIC_GREY, FABRIC_NAVY, LAMINATE, LAMP, LAMP_DIM, LAMP_HOT, PERF, PLASTER_IVORY, PLASTER_TEAL, RUBBER, STEEL, STRUCT, SWATCH,  # noqa: E402
                      TILE_FLOOR, TILE_HEX, TILE_WALL, TRIM, WEAVE_TEAL, WHITE_GLOSS, SParts)
from ship_rooms import WF, WS, build_shell, place  # noqa: E402

ROOT = SL.ROOT
D = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_medbay.json"), encoding="utf-8"))
LEN, HW, H = D["length"], D["half_width"], D["height"]
OFF = WS + WF                                                  # the finished faces stand this far inside the shell's frame
BEDS = D["beds"]
U_BEDS = [-x for x in BEDS["x"]]                               # the beds' places along the ward (u: aft from the forward wall)
V_STBD, V_PORT = HW - BEDS["hinge_y"], HW + BEDS["hinge_y"]    # the backrests' hinges across the ward (v: from the starboard wall)
PIL = [2.8, 5.3, 8.3, 11.3, 14.3, 17.3, 20.3, 23.3, 26.5]      # where the pilasters of the side walls stand: the bays divide the beds
WARD, VITALS, SCAN, CROSS = "MI_MED_Ward", "MI_MED_Vitals", "MI_MED_Scan", "MI_MED_Cross"
PART_U = -D["partition"]["x"]                                  # the theatre's partition (u 23.8)
CURTAIN = WEAVE_TEAL


def style():
    edges_far = [u + OFF for u in PIL]
    edges_near = [LEN + 2 * OFF - OFF - u for u in PIL]
    return TH.medical(floor=TILE_FLOOR, floor2=TILE_HEX, border=0.0, wain_h=1.25, wall_pattern=("panel", "cloth"), ceiling="flat", downlights=False, baseboard_light=True,
                      bay_edges={"far": edges_far, "near": edges_near})


def to_hall(u0: float, u1: float, v0: float, v1: float, z0: float, z1: float) -> tuple:
    """A box in the room's interior frame -> the ward's frame (x, y, z min / max) for SM_MED_Glass."""
    return (min(-u0, -u1), max(-u0, -u1), min(HW - v0, HW - v1), max(HW - v0, HW - v1), z0, z1)


def glass_of(piece_boxes: list, cu: float, cv: float, yaw: int, out: list) -> None:
    """Turn the boxes a piece reports in its own frame (x0, x1, y0, y1, z0, z1) into hall-frame glass boxes, for a piece placed at (cu, cv) turned by yaw (a multiple of 90)."""
    c, s = round(math.cos(math.radians(yaw))), round(math.sin(math.radians(yaw)))
    for (x0, x1, y0, y1, z0, z1) in piece_boxes:
        pts = [(cu + c * x - s * y, cv + s * x + c * y) for x in (x0, x1) for y in (y0, y1)]
        us, vs = [p[0] for p in pts], [p[1] for p in pts]
        out.append(to_hall(min(us), max(us), min(vs), max(vs), z0, z1))


# ------------------------------------------------------------------------------------------------------------------------------------------------------ curtains
def curtain(b: SParts, p0, p1, z0: float, z1: float, amp: float = 0.045, wave: float = 0.26, thick: float = 0.012, flare: float = 1.25) -> None:
    """A pleated curtain hanging from a track between two points (plan), from z1 down to z0: a thin shell lofted through four rings, the pleats opening a little towards the hem."""
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    ln = math.hypot(dx, dy)
    tx, ty = dx / ln, dy / ln
    nx, ny = -ty, tx
    n = max(8, int(ln / wave * 6))
    rings = []
    for r in range(4):
        z = z0 + (z1 - z0) * r / 3
        a = amp * (flare - (flare - 1.0) * r / 3)
        fwd, back = [], []
        for k in range(n + 1):
            s = ln * k / n
            off = a * math.sin(2 * math.pi * s / wave)
            x, y = p0[0] + tx * s + nx * off, p0[1] + ty * s + ny * off
            fwd.append((x - nx * thick / 2, y - ny * thick / 2, z))
            back.append((x + nx * thick / 2, y + ny * thick / 2, z))
        rings.append(fwd + list(reversed(back)))
    MK.stack(b.soft, rings, CURTAIN)


def track(b: SParts, p0, p1, z: float, drops: bool = True) -> None:
    """A ceiling curtain track with its drop rods."""
    b.fine.cyl((p0[0], p0[1], z), (p1[0], p1[1], z), 0.018, STEEL, seg=8)
    if drops:
        ln = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        for k in range(int(ln / 1.4) + 1):
            f = min(1.0, k * 1.4 / ln) if ln > 0 else 0.0
            x, y = p0[0] + (p1[0] - p0[0]) * f, p0[1] + (p1[1] - p0[1]) * f
            b.fine.cyl((x, y, z), (x, y, H - 0.05), 0.008, STEEL, seg=6)


# ------------------------------------------------------------------------------------------------------------------------------------------------------ the ward
def build_room(b: SParts, glass: list) -> None:
    """Everything in the shell's frame, the interior drawn at (OFF, OFF): the caller wraps the call in the transform into the ward's frame."""
    rng = random.Random(6)
    lift = D["lift"]
    spec = {"key": "medbay_ward", "L": LEN + 2 * OFF, "D": 2 * HW + 2 * OFF, "h": H, "doors": [{"wall": "left", "x": HW + OFF, "w": lift["width"], "h": lift["height"]}]}
    build_shell(b, spec, style(), doors=spec["doors"], bare=(), ceil_t=0.3, floor_t=0.3)
    with b.at(T(OFF, OFF, 0.0)):                                   # from here: u aft from the forward wall's face, v from the starboard wall's face
        entrance(b, glass)
        bays(b)
        console(b)
        theatre(b, glass)
        ceiling(b)


def entrance(b: SParts, glass: list) -> None:
    """The forward wall (the lift, the ward board, the cross), the hand-wash station, the nurses' station with its records, the supply wall and what is parked by the door."""
    lift = D["lift"]
    v0, v1 = HW - lift["width"] / 2, HW + lift["width"] / 2
    # the lift's shaft behind its doors: a floor, three walls and a roof (the cabin itself belongs to the lift system)
    b.body.box((-3.55, v0 - 0.4, -0.1), (-0.25, v1 + 0.4, 0.0), STEEL)
    b.body.box((-3.55, v0 - 0.4, 0.0), (-3.15, v1 + 0.4, 3.6), STRUCT)
    b.body.box((-3.55, v0 - 0.4, 0.0), (-0.25, v0, 3.6), STRUCT)
    b.body.box((-3.55, v1, 0.0), (-0.25, v1 + 0.4, 3.6), STRUCT)
    b.body.box((-3.55, v0 - 0.4, 3.6), (-0.25, v1 + 0.4, 3.9), STRUCT)
    b.emit.lamp_box((-3.1, v0 + 0.3, 3.55), (-0.5, v1 - 0.3, 3.6), "white_cool", LAMP_DIM)
    # the lift's frame: a brushed surround and a lit header (the leaves are actors)
    b.body.box((0.0, v0 - 0.2, 0.0), (0.12, v0, lift["height"] + 0.2), STEEL)
    b.body.box((0.0, v1, 0.0), (0.12, v1 + 0.2, lift["height"] + 0.2), STEEL)
    b.body.box((0.0, v0 - 0.2, lift["height"]), (0.12, v1 + 0.2, lift["height"] + 0.2), STEEL)
    b.emit.lamp_box((0.121, v0 - 0.1, lift["height"] + 0.08), (0.126, v1 + 0.1, lift["height"] + 0.12), "medical", LAMP_DIM)
    # the ward board (starboard of the lift): a framed board of the twelve beds, and the cross over the nurses' station
    vb = 4.0
    b.body.box((0.0, vb - 2.4, 1.35), (0.07, vb + 2.4, 2.95), STRUCT)
    b.fine.box((0.07, vb - 2.34, 1.39), (0.075, vb + 2.34, 2.91), STEEL)
    b.emit.screen((0.08, vb, 2.15), 4.6, 1.44, WARD, (1, 0, 0))
    for (a0, a1, c0, c1) in ((-0.45, 0.45, -0.14, 0.14), (-0.14, 0.14, -0.45, 0.45)):
        b.emit.box((0.0, vb + a0, 3.55 + c0), (0.05, vb + a1, 3.55 + c1), CROSS)
    # the hand-wash station by the lift (port), a sharps bin and a gel dispenser beside it
    place(b, 0.35, 12.6, 0, MD.medical_sink, 2.2, 0.7)
    place(b, 0.02, 14.0, 0, MD.sanitiser, z=1.35)
    place(b, 0.02, 14.4, 0, MD.sharps_bin, z=1.2)
    # what is parked by the door: a patient trolley along the wall, two wheelchairs, a drip stand
    place(b, 0.6, 15.0, 90, MD.patient_trolley, 1)
    place(b, 0.5, 16.9, 20, MD.wheelchair, 1)
    place(b, 1.5, 16.9, -10, MD.wheelchair, 2)
    place(b, 1.4, 13.0, 0, MD.iv_stand, 1)
    # the nurses' station (starboard): a high counter of teal laminate towards the aisle with a lit kick, a desk behind it with two screens, a printer, a phone, a lamp, the charts
    du0, du1, vf = 1.5, 5.7, 4.35
    b.body.box((du0, vf - 0.16, 0.0), (du1, vf, 0.1), STRUCT)
    MK.rbox(b.soft, (du0, vf - 0.16, 0.1), (du1, vf, 1.1), 0.012, PLASTER_TEAL, 1)
    for k in range(int((du1 - du0) / 0.6)):
        b.fine.box((du0 + 0.3 + k * 0.6, vf, 0.2), (du0 + 0.305 + k * 0.6, vf + 0.006, 1.0), STEEL)
    b.body.box((du0 - 0.05, vf - 0.3, 1.1), (du1 + 0.05, vf + 0.04, 1.14), STEEL)
    b.emit.lamp_box((du0 + 0.1, vf + 0.001, 0.12), (du1 - 0.1, vf + 0.004, 0.15), "medical", LAMP_DIM)
    b.body.box((du0, 3.25, 0.0), (du1, vf - 0.16, 0.74), WHITE_GLOSS)
    b.body.box((du0, 3.2, 0.74), (du1 + 0.05, vf - 0.16, 0.775), LAMINATE)
    for k in range(3):
        b.fine.box((du0 + 0.15 + k * 1.3, vf - 0.16, 0.1), (du0 + 1.25 + k * 1.3, vf - 0.155, 0.7), PLASTER_TEAL)
    for k, us in enumerate((3.0, 4.3)):                                                               # two screens facing the nurse behind the desk (towards -v)
        b.fine.cyl((us, 3.62, 0.775), (us, 3.62, 0.95), 0.025, STEEL, seg=8)
        b.body.box((us - 0.3, 3.6, 0.95), (us + 0.3, 3.65, 1.3), STRUCT)
        b.emit.screen((us, 3.595, 1.125), 0.56, 0.35, WARD if k else VITALS, (0, -1, 0))
    b.fine.box((5.0, 3.35, 0.775), (5.5, 3.75, 0.9), WHITE_GLOSS)                                  # a printer
    b.fine.box((1.7, 3.5, 0.775), (1.9, 3.7, 0.79), STRUCT)                                         # a phone
    for k in range(4):                                                                              # charts on a rack
        b.soft.swatch_box((2.1 + k * 0.07, 3.4, 0.775), (2.14 + k * 0.07, 3.8, 0.775 + 0.16), ("teal", "white", "cream", "mustard")[k])
    place(b, 2.3, 3.7, 0, DC.mug, z=0.775)
    place(b, 4.9, 2.7, rng_yaw(1), F.chair, FABRIC_GREY)
    # the records and the linen cupboards along the starboard wall behind the station
    for k in range(3):
        place(b, 1.9 + k * 1.2, 0.3, 90, MD.supply_cabinet, 1.1, 0.5, 2.1, 20 + k, None)
    # the supply wall (port): four tall cabinets with their glass fronts; the sink and the bins are further in
    for k in range(4):
        gl: list = []
        place(b, 1.7 + k * 1.0, 17.69, -90, MD.supply_cabinet, 1.0, 0.62, 2.3, 30 + k, gl)
        glass_of(gl, 1.7 + k * 1.0, 17.69, -90, glass)


def rng_yaw(k: int) -> float:
    return random.Random(k * 17).uniform(-25.0, 25.0)


def bays(b: SParts) -> None:
    """The twelve bays: a bedside cabinet and a visitor's chair at every bed, sanitisers on the pilasters, the hand rails of the entrance and the theatre's wall, the tracks and the
    pleated curtains between the beds (gathered at the aisle's edge at both corners of a bay)."""
    rng = random.Random(8)
    for row, (v_hinge, wall, yaw_f, sgn) in enumerate(((V_STBD, 0.0, 90, 1), (V_PORT, 2 * HW, -90, -1))):
        for k, u in enumerate(U_BEDS):
            place(b, u + 0.85, wall + sgn * 0.3, yaw_f, MD.bedside_cabinet, row * 6 + k)
            place(b, u - 0.92, v_hinge + sgn * 0.55, rng.uniform(-12, 12), MD.visitor_chair, row * 6 + k)
        for u in PIL[1:-1]:
            place(b, u, wall + sgn * 0.075, yaw_f, MD.sanitiser, z=1.25)
        for (u0, u1) in ((0.5, 5.2), (24.0, 29.6)):                                                  # the bumper rails on brackets
            b.body.cyl((u0, wall + sgn * 0.07, 0.9), (u1, wall + sgn * 0.07, 0.9), 0.025, STEEL, seg=10)
            va, vb = sorted((wall, wall + sgn * 0.07))
            for u in [u0 + k * 1.5 for k in range(int((u1 - u0) / 1.5) + 1)]:
                b.fine.box((u - 0.02, va, 0.85), (u + 0.02, vb, 0.95), STEEL)
        # the tracks and the curtains
        va = 2.95 if sgn > 0 else 2 * HW - 2.95                                                      # the aisle line of the curtains (the hall's y +-6.05)
        vw = 0.3 if sgn > 0 else 2 * HW - 0.3
        for k, u in enumerate(PIL[1:-1]):
            track(b, (u, vw), (u, va), 2.45)
            if 0 < k < 6:
                curtain(b, (u, vw + sgn * 0.02), (u, va), 0.32, 2.42)
            else:
                curtain(b, (u, vw + sgn * 0.02), (u, vw + sgn * 0.36), 0.32, 2.42, amp=0.07, wave=0.07, flare=1.1)
            if k < 6:                                                                                # the aisle side: gathered at the corners of the bay
                curtain(b, (u + 0.08, va), (u + 0.4, va), 0.32, 2.42, amp=0.07, wave=0.07, flare=1.1)
                curtain(b, (u + 2.6, va), (u + 2.92, va), 0.32, 2.42, amp=0.07, wave=0.07, flare=1.1)
        track(b, (PIL[1], va), (PIL[-2], va), 2.45)


def console(b: SParts) -> None:
    """The central console (u 10.2 .. 18.4, v 8.25 .. 9.75): a teal laminate base with a lit kick on both sides, a steel-edged top, a double-sided board leaning back with three screens a side,
    and the doctor's terminal on its pedestal facing her."""
    cc = D["central_console"]
    u0, u1, hw = -cc["x0"], -cc["x1"], cc["half_width"]
    u0, u1 = min(u0, u1), max(u0, u1)
    v0, v1 = HW - hw, HW + hw
    b.body.box((u0 + 0.1, v0 + 0.1, 0.0), (u1 - 0.1, v1 - 0.1, 0.1), STRUCT)
    MK.rbox(b.soft, (u0, v0, 0.1), (u1, v1, 0.92), 0.015, PLASTER_TEAL, 1)
    b.body.box((u0 - 0.05, v0 - 0.05, 0.92), (u1 + 0.05, v1 + 0.05, 0.96), STEEL)
    for v, sgn in ((v0, -1), (v1, 1)):
        b.emit.lamp_box((u0 + 0.1, v + (0.0 if sgn > 0 else -0.004), 0.12), (u1 - 0.1, v + (0.004 if sgn > 0 else 0.0), 0.15), "medical", LAMP_DIM)
        for k in range(8):                                                                           # panel lines in the base
            b.fine.box((u0 + 0.3 + k * (u1 - u0 - 0.6) / 7, v - (0.004 if sgn < 0 else -0.0), 0.2), (u0 + 0.305 + k * (u1 - u0 - 0.6) / 7, v + (0.0 if sgn < 0 else 0.004), 0.85), STEEL)
    for k in range(3):                                                                               # the board: three screens on each side of a slab on a post
        um = u0 + 1.4 + k * 2.7
        b.fine.cyl((um, HW, 0.96), (um, HW, 1.28), 0.05, STEEL, seg=10)
        b.soft.box((um - 1.25, HW - 0.06, 1.28), (um + 1.25, HW + 0.06, 1.9), STRUCT)
        for sgn in (-1, 1):
            b.emit.screen((um, HW + sgn * 0.061, 1.59), 2.42, 0.56, WARD, (0.0, sgn, 0.0))
    doc = next(c for c in D["crew"] if c["station"] == "doctor")
    ut, vt = -(doc["x"] + 0.5), HW - doc["y"]
    b.body.cyl((ut, vt, 0.0), (ut, vt, 0.05), 0.2, STRUCT, seg=16)                                  # a slim pedestal: a round foot, a steel column, a tilted screen in a dark frame
    b.body.cyl((ut, vt, 0.05), (ut, vt, 1.0), 0.035, STEEL, seg=10)
    with b.at(T(ut, vt, 1.1) @ Ry(-20.0)):
        MK.rbox(b.soft, (-0.03, -0.25, -0.17), (0.02, 0.25, 0.17), 0.012, STRUCT, 1)
    b.emit.screen((ut + 0.027, vt, 1.1), 0.42, 0.27, VITALS, (0.94, 0.0, 0.34), up=(-0.34, 0.0, 0.94))


def theatre(b: SParts, glass: list) -> None:
    """The partition and the theatre behind it."""
    P = D["partition"]
    dhw = P["door_half_width"]
    pu = PART_U
    posts = [HW - y for y in (-HW, -6.3, -3.6, -dhw, dhw, 3.6, 6.3, HW)]
    posts = sorted(posts)
    for v in posts:
        MK.rbox(b.soft, (pu - 0.08, v - 0.06, 0.0), (pu + 0.08, v + 0.06, 2.7), 0.01, STEEL, 1)
        b.emit.lamp_box((pu - 0.082, v - 0.01, 0.4), (pu - 0.08, v + 0.01, 2.4), "medical", LAMP_DIM)
    b.body.box((pu - 0.12, 0.0, 2.7), (pu + 0.12, 2 * HW, H), PLASTER_IVORY)
    b.body.box((pu - 0.13, 0.0, 2.66), (pu + 0.13, 2 * HW, 2.72), STEEL)
    for (a, c) in ((0.0, HW - dhw), (HW + dhw, 2 * HW)):
        b.body.box((pu - 0.08, a, 0.0), (pu + 0.08, c, 0.12), STEEL)
    for (a0, a1, c0, c1) in ((-0.3, 0.3, -0.1, 0.1), (-0.1, 0.1, -0.3, 0.3)):
        b.emit.box((pu + 0.12, HW + a0, 3.3 + c0), (pu + 0.14, HW + a1, 3.3 + c1), CROSS)
    b.body.box((pu - 0.05, HW + dhw + 0.05, 2.6), (pu + 0.05, HW + dhw + 1.25, 2.7), STEEL)         # the sliding door's track
    if "room_surgery" in SL.LABELS:
        b.emit.label_fit((pu - 0.135, HW, 3.5), 2.2, "room_surgery", (-1, 0, 0))
    # the theatre
    sg = D["surgery"]
    tu, tv = -sg["table"][0], HW - sg["table"][1]
    place(b, tu, tv, 0, MD.op_table)
    place(b, tu, tv, 0, MD.surgical_lamp, H - 0.05, 0.6, 2.25)
    place(b, tu - 1.65, tv + 0.55, 0, MD.anesthesia_machine)
    place(b, tu + 0.1, tv - 1.15, 90, MD.instrument_trolley, 1)
    place(b, tu + 0.8, tv + 1.05, -90, MD.instrument_trolley, 2)
    place(b, tu - 0.3, tv + 1.2, 0, MD.iv_stand, 3)
    su, sv = -sg["scanner"][0], HW - sg["scanner"][1]
    place(b, su, sv, 0, MD.scanner_ring)
    stand = (su - 1.6, sv + 2.3)                                                                      # the scanner's display on its stand
    b.body.cyl((stand[0], stand[1], 0.0), (stand[0], stand[1], 1.2), 0.04, TRIM, seg=10)
    b.body.cyl((stand[0], stand[1], 0.0), (stand[0], stand[1], 0.03), 0.3, STRUCT, seg=20)
    with b.at(T(stand[0], stand[1], 1.5) @ Rz(-40.0)):
        MK.rbox(b.soft, (-0.04, -0.43, -0.28), (0.04, 0.43, 0.28), 0.015, STRUCT, 1)
    b.emit.screen((stand[0] + 0.03 * 0.77, stand[1] - 0.03 * 0.64, 1.5), 0.8, 0.5, SCAN, (0.77, -0.64, 0.0))
    # the sterile cabinets along the aft wall and the big display between them
    wall = LEN
    for k in range(10):
        v = 0.4 + k * 1.72 + 0.83
        if abs(v - HW) < 1.75:
            continue
        gl: list = []
        place(b, wall - 0.21, v, 180, MD.supply_cabinet, 1.66, 0.42, 2.2, 40 + k, gl)
        glass_of(gl, wall - 0.21, v, 180, glass)
    b.body.box((wall - 0.06, HW - 1.3, 1.25), (wall, HW + 1.3, 2.85), STRUCT)
    b.emit.screen((wall - 0.065, HW, 2.05), 2.3, 1.44, SCAN, (-1.0, 0.0, 0.0))
    place(b, PART_U + 0.55, HW + 2.3, 90, MD.crash_cart)


def ceiling(b: SParts) -> None:
    """The ceiling: beams over the pilasters, flush light panels over each bed (three bays to a light) and down the aisle, the theatre's bright field, a main duct with grilles and
    sprinkler heads."""
    beam_xs = [u + OFF for u in PIL[1:-1]]
    SH.beams(b, {"L": LEN + 2 * OFF, "D": 2 * HW + 2 * OFF, "h": H}, style(), beam_xs, 0.2)
    zc = H - 0.05
    for v in (1.7, 2 * HW - 1.7):                                                                    # over the beds
        for g in range(2):
            for j in range(3):
                u = U_BEDS[g * 3 + j]
                SH.band(b, u - 1.2, u + 1.2, v, 0.8, zc, "white_cool", LAMP_HOT)
    for v in (5.8, 12.2):                                                                            # down the aisle
        for (a, c) in ((0.9, 5.1), (5.5, 9.7), (10.1, 14.3), (14.7, 18.9), (19.3, 23.1)):
            SH.band(b, a, c, v, 0.6, zc, "white_cool", LAMP_HOT)
    tu, tv = -D["surgery"]["table"][0], HW - D["surgery"]["table"][1]
    SH.band(b, tu - 1.4, tu + 1.4, tv, 3.2, zc, "white_cool", LAMP_HOT)
    b.soft.box((1.0, HW - 0.28, H - 0.36), (22.8, HW + 0.28, H - 0.05), WHITE_GLOSS)                  # the main duct, its flanges and its grilles
    for k in range(8):
        b.fine.box((1.0 + k * 3.0 - 0.03, HW - 0.32, H - 0.4), (1.0 + k * 3.0 + 0.03, HW + 0.32, H - 0.04), STEEL)
    for u in (4.0, 12.0, 20.0):
        b.fine.box((u - 0.3, HW - 0.24, H - 0.365), (u + 0.3, HW + 0.24, H - 0.36), PERF)
    for (u, v) in ((27.0, 5.5), (27.0, 12.5)):
        b.fine.box((u - 0.35, v - 0.35, H - 0.055), (u + 0.35, v + 0.35, H - 0.05), PERF)
    for u in [1.5 + 3.0 * k for k in range(8)]:                                                      # sprinkler heads on the aisle line
        for v in (HW - 1.0, HW + 1.0):
            b.fine.cyl((u, v, H - 0.05), (u, v, H - 0.12), 0.012, BRASS, seg=6)
            b.fine.cyl((u, v, H - 0.12), (u, v, H - 0.15), 0.03, STEEL, seg=8, r2=0.01)
    b.emit.lamp_box((0.6, HW - 0.04, 0.0), (23.6, HW + 0.04, 0.004), "medical", LAMP_DIM)             # the guide line in the floor, lift to theatre


# ------------------------------------------------------------------------------------------------------------------------------------------------------ the mesh
def ward(name: str = "SM_MED_Ward", glass: list | None = None):
    """The ward's mesh in the ward's frame (the forward wall at x 0, the ward running aft to x -30, y +-9; the lift's gate at y 0). `glass` receives the boxes of the cabinets' glass
    (x0, x1, y0, y1, z0, z1) for SM_MED_Glass."""
    SL.load_labels()
    b = SParts(bevel=0.005, fine_bevel=0.0)
    with b.at(frame(OFF, HW + OFF, 0.0, 180.0)):
        build_room(b, glass if glass is not None else [])
    return b.build(name, uv_meter=1.0)


# ------------------------------------------------------------------------------------------------------------------------------------- preview
def preview(out: str, samples: int = 24) -> None:
    import bpy
    import bridge3_preview as PV
    import ship_preview as SP
    glass: list = []
    obj = ward("SM_MED_Ward", glass)
    SP.setup(1600, 900, samples, exposure=0.0, world=(0.05, 0.052, 0.058))
    for slot, page in ((WARD, "Med_Ward"), (VITALS, "Med_Vitals"), (SCAN, "Med_Scan")):
        try:
            PV.screen_mat(slot, page, 2.4)
        except Exception:
            pass
    SP.instance(obj, (0, 0, 0), 0)
    obj.hide_render = True
    import medbay as MB
    import math as _m
    bed = MB.bed()
    bed.hide_render = True
    for side in (-1, 1):                                                                              # the twelve beds, as build_medbay.py places them (the kit's Y is mirrored)
        for x in BEDS["x"]:
            inst = bpy.data.objects.new("bed", bed.data)
            bpy.context.scene.collection.objects.link(inst)
            inst.location = (x, -side * BEDS["hinge_y"], 0.0)
            inst.rotation_euler = (0.0, 0.0, _m.radians(-90.0 * side))
    gain = 1.5
    bx = BEDS["x"]
    for side in (-1, 1):
        for i, grp in enumerate((bx[:3], bx[3:])):
            SP.rect_light(f"bed{side}{i}", (sum(grp) / 3.0, side * 7.3, H - 0.1), (7.2, 0.9), 7800 * 0.03 * gain, (0.95, 0.97, 1.0))
    for i, (x0, x1) in enumerate(((-0.8, -11.2), (-11.2, -23.3))):
        for yy in (-3.2, 3.2):
            SP.rect_light(f"aisle{i}{yy}", ((x0 + x1) / 2, yy, H - 0.1), (abs(x1 - x0) - 1.0, 0.6), 8800 * 0.03 * gain, (0.95, 0.97, 1.0))
    tx, ty = D["surgery"]["table"]
    SP.rect_light("theatre", (tx, ty, H - 0.1), (2.8, 3.2), 9000 * 0.03 * gain, (0.97, 0.98, 1.0))
    views = {"lift": ((-1.0, 0.0, 1.65), (-24.0, 0.0, 1.5), 82), "beds_p": ((-3.0, 4.0, 1.65), (-14.0, -8.0, 1.2), 84), "beds_s": ((-3.0, -4.0, 1.65), (-14.0, 8.0, 1.2), 84),
             "aisle": ((-2.0, 0.0, 1.7), (-22.0, 0.0, 1.5), 74), "desk": ((-9.0, -2.0, 1.7), (-3.5, 5.0, 1.1), 80), "supply": ((-8.0, 2.0, 1.7), (-3.0, -8.0, 1.3), 80),
             "theatre": ((-19.0, 0.0, 1.7), (-27.0, 0.0, 1.2), 80), "theatre2": ((-24.6, -6.0, 1.7), (-28.0, 4.0, 1.0), 86), "console": ((-7.0, 3.0, 1.7), (-15.0, -1.0, 1.0), 78),
             "bay": ((-9.0, 3.0, 1.65), (-9.8, 8.0, 1.1), 80)}
    for n, (eye, tgt, fov) in views.items():
        cam = SP.look_camera(n, eye, tgt, fov)
        SP.render(cam, os.path.join(out, f"med_{n}.jpg"))


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    A.reset_scene()
    if "--preview" in argv:
        out = argv[argv.index("--preview") + 1]
        os.makedirs(out, exist_ok=True)
        preview(out, int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 24)
    else:
        g: list = []
        o = ward("SM_MED_Ward", g)
        print("MED_WARD tris", sum(len(p.vertices) - 2 for p in o.data.polygons), "slots", len(o.data.materials), "glass", len(g))
