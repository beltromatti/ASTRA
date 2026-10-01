"""ASN Aquila interior kit: the corridor modules (bridge v3 language).

A module is a 4 m x 4 m cell of the ship's grid: 3.1 m clear between the finished walls, 0.45 m of wall on each side, 3.4 m
clear height, 0.3 m of floor and ceiling structure (a 4 m deck pitch). Module frame: origin on the floor on the centre line at
the AFT end, x forward 0..4, y across (starboard +), z up. The walls are layered dark composite panels in brushed frames with
ribs every 2 m, light lines, a handrail, cable trays and conduits; a bay holds a piece of equipment; the ceiling has a linear
luminaire, a duct and a cable tray; the floor is gunmetal plates in a running bond with guide lights and a direction chevron.

  SM_SHIP_<tone>_Straight_A/B/C    straight cells with different equipment bays
  SM_SHIP_<tone>_Door_L_A/B, _R_A/B, _LR    a sliding door (1.6 x 2.4, AAstraDoor) in the port / starboard / both walls
  SM_SHIP_<tone>_Gate_L / _R / _LR          a wide portal (3.2 x 3.0, two leaves) into a big space
  SM_SHIP_<tone>_Bulkhead                    the section blast door frame across the corridor (2.0 x 2.5 opening) at the forward end
  SM_SHIP_<tone>_T_L / _T_R / _X             the throat of a side passage (3.1 m) on the port / starboard / both sides
  SM_SHIP_<tone>_End                         a closed end wall at the forward end (turn it with the yaw)
tone S = the spine (blue lines, cool white light), tone P = the passages (amber lines, warm white light).
"""
from __future__ import annotations

import math
import random

from mathutils import Matrix

import ship_lib as SL
import ship_walls as SW
from bridge3_lib import Rz
from ship_catalog import (BLAST_H, BLAST_W, CLEAR_H, CORRIDOR_SPECS, CRAWL_H, CRAWL_HW, DOOR_H, DOOR_W, GATE_H, GATE_W, HW, MOD, SLOT_HW, TONES, WALL_T)
from ship_lib import (COMPOSITE, CRATE_BLUE, CRATE_ORANGE, DECK, IVORY, LAMP, LAMP_DIM, LAMP_HOT, PAINT_RED, RUBBER, STEEL, STRUCT, TRIM, SParts)

H = CLEAR_H
FLOOR_T = 0.30
OV = 0.02                       # modules overlap by 2 cm at their ends (no light leaks through the seams)
PLAN = {"A": (("lockers", "plain"), ("safety", "vent")),
        "B": (("vent", "conduits"), ("hydrant", "screen")),
        "C": (("screen", "plain"), ("panelboard", "vent"))}          # bay kinds (left = port wall, right = starboard wall)
NARROW = {"A": (("plain", "vent"), ("vent", "plain")), "B": (("vent", "plain"), ("plain", "vent"))}
OPENING = {"door": (2.0 - DOOR_W / 2, 2.0 + DOOR_W / 2, DOOR_H), "gate": (2.0 - GATE_W / 2, 2.0 + GATE_W / 2, GATE_H),
           "branch": (0.45, 3.55, H)}


def wall_matrix(side: int) -> Matrix:
    """Wall-local frame (s along the wall, t outward from the finished face, z up) in module coordinates; side +1 = starboard."""
    m = Matrix.Identity(4)
    m[1][1] = float(side)
    m[1][3] = side * HW
    return m


def plate_uv(fb, faces, rng: random.Random, scale: float = 1.0) -> None:
    ou, ov = rng.random() * 8.0, rng.random() * 8.0
    for f in faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        f[fb.cu] = 1
        for loop in f.loops:
            co = loop.vert.co
            u, v = ((co.y, co.z), (co.x, co.z), (co.x, co.y))[ax]
            loop[fb.uv].uv = (u / scale + ou, v / scale + ov)


# ---------------------------------------------------------------------------------------------------------------- floor
def floor(b: SParts, tn: dict, rng: random.Random, seam: bool = True) -> None:
    fb, em = b.body, b.emit
    fb.box((-OV, -SLOT_HW, -FLOOR_T), (MOD + OV, SLOT_HW, -0.012), STRUCT)
    rows = 4
    rw = 2 * HW / rows
    for j in range(rows):
        y0, y1 = -HW + j * rw + 0.008, -HW + (j + 1) * rw - 0.008
        cuts = [0.0, 2.0, 4.0] if j % 2 == 0 else [0.0, 1.0, 3.0, 4.0]
        for a, c in zip(cuts, cuts[1:]):
            x0 = a - (OV if a == 0.0 else 0.0) + 0.008
            x1 = c + (OV if c == MOD else 0.0) - 0.008
            faces = fb.box((x0, y0, -0.012), (x1, y1, 0.0), DECK)
            plate_uv(fb, faces, rng, 1.0)
    for y in (-1.34, 1.34):                               # guide lights near the walls
        em.lamp_box((0.15, y - 0.014, 0.0), (1.9, y + 0.014, 0.004), tn["accent_dim"], LAMP_DIM)
        em.lamp_box((2.1, y - 0.014, 0.0), (3.85, y + 0.014, 0.004), tn["accent_dim"], LAMP_DIM)
    # the direction chevron on the centre line (points forward)
    SL.lamp_strip(em, (1.72, -0.30, 0.002), (2.12, 0.0, 0.002), 0.035, 0.004, tn["accent"], LAMP_DIM)
    SL.lamp_strip(em, (1.72, 0.30, 0.002), (2.12, 0.0, 0.002), 0.035, 0.004, tn["accent"], LAMP_DIM)


# -------------------------------------------------------------------------------------------------------------- ceiling
def ceiling(b: SParts, tn: dict, rng: random.Random, duct_side: int = 1) -> None:
    fb, em, fine = b.body, b.emit, b.fine
    fb.box((-OV, -SLOT_HW, H), (MOD + OV, SLOT_HW, H + FLOOR_T), STRUCT)
    # composite panels either side of the luminaire, brushed frames, cross beams every 2 m
    for (s0, s1) in ((0.14, 1.86), (2.14, 3.86)):
        for sy in (-1, 1):
            y0, y1 = (0.36, HW - 0.06) if sy > 0 else (-HW + 0.06, -0.36)
            fb.box((s0, y0, H - 0.045), (s1, y1, H), COMPOSITE)
            fb.box((s0, y0, H - 0.058), (s1, y0 + 0.028, H - 0.045), TRIM)
            fb.box((s0, y1 - 0.028, H - 0.058), (s1, y1, H - 0.045), TRIM)
            fb.box((s0, y0 + 0.028, H - 0.058), (s0 + 0.028, y1 - 0.028, H - 0.045), TRIM)
            fb.box((s1 - 0.028, y0 + 0.028, H - 0.058), (s1, y1 - 0.028, H - 0.045), TRIM)
    for s in (0.0, 2.0):
        for (y0, y1) in ((-HW, -0.36), (0.36, HW)):
            fb.box((s - 0.07, y0, H - 0.17), (s + 0.07, y1, H - 0.02), TRIM)
            fb.box((s - 0.045, y0, H - 0.185), (s + 0.045, y1, H - 0.17), STRUCT)
        em.lamp_box((s - 0.006, -HW + 0.1, H - 0.187), (s + 0.006, -0.42, H - 0.182), tn["accent_dim"], LAMP_DIM)
        em.lamp_box((s - 0.006, 0.42, H - 0.187), (s + 0.006, HW - 0.1, H - 0.182), tn["accent_dim"], LAMP_DIM)
    # the linear luminaire: a trough with a bright strip and two dim edge lines
    fb.box((0.06, -0.33, H - 0.075), (MOD - 0.06, -0.29, H - 0.02), TRIM)                # the trough: two side bars, two end bars
    fb.box((0.06, 0.29, H - 0.075), (MOD - 0.06, 0.33, H - 0.02), TRIM)
    fb.box((0.06, -0.29, H - 0.075), (0.10, 0.29, H - 0.02), TRIM)
    fb.box((MOD - 0.10, -0.29, H - 0.075), (MOD - 0.06, 0.29, H - 0.02), TRIM)
    fb.box((0.10, -0.29, H - 0.027), (MOD - 0.10, 0.29, H - 0.02), STRUCT)               # the back of the trough
    em.lamp_box((0.16, -0.22, H - 0.034), (MOD - 0.16, 0.22, H - 0.028), tn["strip"], LAMP_HOT)
    em.lamp_box((0.14, -0.285, H - 0.06), (MOD - 0.14, -0.27, H - 0.056), tn["accent_dim"], LAMP_DIM)
    em.lamp_box((0.14, 0.27, H - 0.06), (MOD - 0.14, 0.285, H - 0.056), tn["accent_dim"], LAMP_DIM)
    # a round duct on one side, a rectangular vent duct and a cable tray on the other
    yd = duct_side * 1.0
    fine.cyl((-OV, yd, H - 0.22), (MOD + OV, yd, H - 0.22), 0.14, TRIM, seg=14)
    for s in (0.55, 2.55):
        fine.box((s - 0.03, yd - 0.05, H - 0.10), (s + 0.03, yd + 0.05, H), STRUCT)
        fine.box((s - 0.075, yd - 0.145, H - 0.24), (s + 0.075, yd + 0.145, H - 0.20), TRIM)
    fine.box((0.7, yd - 0.145, H - 0.225), (0.78, yd + 0.145, H - 0.215), STRUCT)
    fine.box((3.0, yd - 0.145, H - 0.225), (3.08, yd + 0.145, H - 0.215), STRUCT)
    yv = -duct_side * 1.05
    fine.box((-OV, yv - 0.22, H - 0.26), (MOD + OV, yv + 0.22, H - 0.05), COMPOSITE)
    for k in range(3):
        fine.box((0.35 + k * 1.3, yv - 0.16, H - 0.268), (0.75 + k * 1.3, yv + 0.16, H - 0.26), RUBBER)
        for j in range(4):
            fine.box((0.38 + k * 1.3 + j * 0.1, yv - 0.15, H - 0.27), (0.42 + k * 1.3 + j * 0.1, yv + 0.15, H - 0.266), TRIM)
    fine.box((-OV, yv + 0.30, H - 0.14), (MOD + OV, yv + 0.55, H - 0.13), STRUCT)
    for k in range(4):
        fine.cyl((-OV, yv + 0.34 + 0.05 * k, H - 0.115), (MOD + OV, yv + 0.34 + 0.05 * k, H - 0.115), 0.012, RUBBER, seg=6)


# ------------------------------------------------------------------------------------------------------ doors and frames
def door_frame(b: SParts, sc: float, w: float, h: float, tn: dict, wide: bool = False) -> None:
    """Jambs and header through the wall thickness, a status lamp, a call panel, a threshold (wall-local frame)."""
    fb, fine, em = b.body, b.fine, b.emit
    jl, jr = sc - w / 2, sc + w / 2
    t0 = -0.075
    fine.box((jl - 0.09, t0, 0.0), (jl, WALL_T + 0.01, h + 0.09), TRIM)
    fine.box((jr, t0, 0.0), (jr + 0.09, WALL_T + 0.01, h + 0.09), TRIM)
    fine.box((jl - 0.09, t0, h), (jr + 0.09, WALL_T + 0.01, h + 0.09), TRIM)
    fine.box((jl - 0.02, t0 - 0.012, 0.0), (jl, t0, h), STRUCT)
    fine.box((jr, t0 - 0.012, 0.0), (jr + 0.02, t0, h), STRUCT)
    fine.box((jl - 0.02, t0 - 0.012, h), (jr + 0.02, t0, h + 0.02), STRUCT)
    fine.box((jl, -0.02, 0.0), (jr, WALL_T + 0.01, 0.012), TRIM)                                   # threshold
    em.lamp_box((sc - 0.22, t0 - 0.014, h + 0.03), (sc + 0.22, t0 - 0.008, h + 0.06), "green", LAMP)   # status lamp above
    for sgn in (-1, 1):                                                                            # call panel beside the door
        s = (jl - 0.24) if sgn < 0 else (jr + 0.24)
        fine.box((s - 0.06, -0.05, 1.02), (s + 0.06, -0.008, 1.22), TRIM)
        fine.box((s - 0.045, -0.058, 1.05), (s + 0.045, -0.05, 1.19), RUBBER)
        em.lamp_box((s - 0.012, -0.0585, 1.10), (s + 0.012, -0.0575, 1.14), tn["accent"], LAMP)
    if wide:
        em.lamp_box((jl, t0 - 0.014, h + 0.10), (jr, t0 - 0.008, h + 0.115), tn["accent"], LAMP)


def header_plate(b: SParts, sc: float, w: float, h: float) -> None:
    """The composite header over a door with a blank recessed field (the room's name plate is placed there by the layout)."""
    fb = b.body
    z0, z1 = h + 0.13, H - 0.52
    if z1 - z0 < 0.25:
        return
    s0, s1 = sc - w / 2 - 0.1, sc + w / 2 + 0.1
    SW.panel(fb, s0, s1, z0, z1, raised=False, bolts=True)
    fb.box((sc - 0.62, -0.05, z0 + 0.06), (sc + 0.62, -0.035, z1 - 0.06), SL.DGLASS)


# ----------------------------------------------------------------------------------------------------------------- walls
def wall(b: SParts, side: int, kind: str, tn: dict, rng: random.Random, plan_id: str) -> None:
    fb, fine, em = b.body, b.fine, b.emit
    with b.at(wall_matrix(side)):
        s_op = OPENING.get(kind)
        # ---- the body: full height except over openings
        if s_op is None:
            fb.box((-OV, 0.0, 0.0), (MOD + OV, WALL_T, H), STRUCT)
        else:
            a, c, oh = s_op
            fb.box((-OV, 0.0, 0.0), (a, WALL_T, H), STRUCT)
            fb.box((c, 0.0, 0.0), (MOD + OV, WALL_T, H), STRUCT)
            if oh < H:
                fb.box((a, 0.0, oh), (c, WALL_T, H), STRUCT)
        # ---- corridor-side finish
        plinth_spans = [(0.0, MOD)] if s_op is None else [(0.0, s_op[0] - 0.1), (s_op[1] + 0.1, MOD)]
        for (a, c) in plinth_spans:
            if c - a > 0.15:
                SW.plinth(fine, a + 0.02, c - 0.02, tn["accent_dim"])
        ribs = [0.0, 2.0] if kind == "wall" else [0.0]
        for s in ribs:
            SW.rib(fb, s, 0.0, H - 0.06, tn["accent_dim"], wide=False)
        # the equipment bays
        left_plan, right_plan = PLAN[plan_id] if kind == "wall" else NARROW["A" if plan_id != "B" else "B"]
        kinds = (left_plan if side < 0 else right_plan)
        if kind == "wall":
            for (s0, s1), k in zip(((0.14, 1.86), (2.14, 3.86)), kinds):
                SW.bay(fb, k, s0, s1, H, rng, tn["accent"], tn["accent_dim"])
        elif kind == "door":
            for (s0, s1), k in zip(((0.14, 1.04), (2.96, 3.86)), kinds):
                SW.bay(fb, k, s0, s1, H, rng, tn["accent"], tn["accent_dim"])
            door_frame(b, 2.0, DOOR_W, DOOR_H, tn)
            header_plate(b, 2.0, DOOR_W, DOOR_H)
        elif kind == "gate":
            SW.panel(fb, 0.06, 0.32, 0.36, H - 0.55, raised=False)
            SW.panel(fb, MOD - 0.32, MOD - 0.06, 0.36, H - 0.55, raised=False)
            door_frame(b, 2.0, GATE_W, GATE_H, tn, wide=True)
        elif kind == "branch":
            for s in (0.45, 3.55):                          # the jambs of the side passage's throat
                fine.box((s - 0.09 if s < 2 else s, -0.075, 0.0), (s if s < 2 else s + 0.09, WALL_T + 0.01, H), TRIM)
                em.lamp_box((s - 0.006, -0.082, 0.35), (s + 0.006, -0.077, H - 0.35), tn["accent_dim"], LAMP_DIM)
            fine.box((0.45, -0.02, 0.0), (3.55, WALL_T + 0.01, 0.012), TRIM)
            em.lamp_box((0.6, -0.012, 0.0), (3.4, 0.012, 0.004), tn["accent"], LAMP_DIM)
        # rails, service zone, cornice
        if kind == "wall":
            SW.utility_rail(fine, 0.15, 3.85, tn["accent_dim"])
            SW.cable_runs(fine, 0.2, 3.8, H, rng, tray=True, conduits=2)
            SW.cornice(fine, 0.0, MOD, H)
        elif kind == "door":
            SW.utility_rail(fine, 0.15, 1.1, tn["accent_dim"])
            SW.utility_rail(fine, 2.9, 3.85, tn["accent_dim"])
            SW.cable_runs(fine, 0.2, 3.8, H, rng, tray=True, conduits=1)
            SW.cornice(fine, 0.0, MOD, H)
        else:
            SW.cornice(fine, 0.0, 0.4 if kind == "gate" else 0.45, H)
            SW.cornice(fine, MOD - (0.4 if kind == "gate" else 0.45), MOD, H)


# ------------------------------------------------------------------------------------------------------------------ ends
def end_wall(b: SParts, tn: dict, rng: random.Random) -> None:
    """A closed end at the forward end: structure, composite finish, a maintenance hatch and a tag."""
    fb, fine, em = b.body, b.fine, b.emit
    fb.box((MOD - 0.42, -HW - 0.02, 0.0), (MOD + OV, HW + 0.02, H), STRUCT)
    # finish panels (built directly in module coordinates, facing -x)
    x = MOD - 0.42
    for (y0, y1) in ((-HW, -0.65), (0.65, HW)):
        SW_panel_x(fb, x, y0 + 0.04, y1 - 0.04, 0.36, H - 0.55)
    fine.box((x - 0.05, -0.62, 0.02), (x, 0.62, 0.30), TRIM)
    fine.box((x - 0.05, -0.62, 0.30), (x, 0.62, H - 0.5), COMPOSITE)
    fine.box((x - 0.07, -0.5, 0.4), (x - 0.05, 0.5, 2.2), STRUCT)
    fine.box((x - 0.11, -0.16, 1.15), (x - 0.07, 0.16, 1.27), TRIM)
    em.lamp_box((x - 0.05, 0.42, 2.02), (x - 0.045, 0.46, 2.12), "amber", LAMP)
    em.label((x - 0.06, 0.0, 2.55), 0.9, 0.225, (-1, 0, 0), "tag_08")


def SW_panel_x(fb, x: float, y0: float, y1: float, z0: float, z1: float) -> None:
    """A wall panel on a wall that faces -x (finished face at x): the same layers as ship_walls.panel."""
    proud = 0.026
    fw = 0.028
    fb.box((x - proud, y0, z0), (x, y1, z1), COMPOSITE)
    tf = x - proud - 0.012
    fb.box((tf, y0, z0), (x - proud, y1, z0 + fw), TRIM)
    fb.box((tf, y0, z1 - fw), (x - proud, y1, z1), TRIM)
    fb.box((tf, y0, z0 + fw), (x - proud, y0 + fw, z1 - fw), TRIM)
    fb.box((tf, y1 - fw, z0 + fw), (x - proud, y1, z1 - fw), TRIM)


def blast_frame(b: SParts, tn: dict) -> None:
    """The section blast door: a heavy frame across the corridor at the forward end (x 3.4 .. 4.0), opening 2.0 x 2.5."""
    fb, fine, em = b.body, b.fine, b.emit
    hx = BLAST_W / 2
    x0, x1 = 3.40, MOD + OV
    fb.box((x0, -HW - 0.02, 0.0), (x1, -hx, H), STRUCT)
    fb.box((x0, hx, 0.0), (x1, HW + 0.02, H), STRUCT)
    fb.box((x0, -hx, BLAST_H), (x1, hx, H), STRUCT)
    # brushed jambs and a heavy header, proud of the frame on the approach side (x < 3.4)
    fine.box((x0 - 0.10, -hx - 0.16, 0.0), (x1 - 0.1, -hx, BLAST_H + 0.16), TRIM)
    fine.box((x0 - 0.10, hx, 0.0), (x1 - 0.1, hx + 0.16, BLAST_H + 0.16), TRIM)
    fine.box((x0 - 0.10, -hx - 0.16, BLAST_H), (x1 - 0.1, hx + 0.16, BLAST_H + 0.16), TRIM)
    for sgn in (-1, 1):
        y = sgn * (hx + 0.08)
        for z in (0.3, 0.9, 1.5, 2.1):
            fine.box((x0 - 0.135, y - 0.075, z - 0.05), (x0 - 0.10, y + 0.075, z + 0.05), STRUCT)
            for dy in (-0.05, 0.05):
                fine.cyl((x0 - 0.135, y + dy, z), (x0 - 0.146, y + dy, z), 0.012, TRIM, seg=6)
    # hazard stripes on the jamb faces and across the floor threshold
    for sgn in (-1, 1):
        fb.label((x0 - 0.137, sgn * (hx + 0.08), BLAST_H / 2 + 0.05), BLAST_H - 0.1, 0.10, (-1, 0, 0), "hazard_h", up=(0, 1, 0))
    fb.label((x0 - 0.06, 0.0, BLAST_H + 0.08), 2 * hx + 0.3, 0.10, (-1, 0, 0), "hazard")
    fb.label((x0 + 0.20, 0.0, 0.0125), 2 * hx, 0.18, (0, 0, 1), "hazard_h", up=(1, 0, 0))
    # lamps: two red beacons, a green ready lamp, guide lines on both sides
    for sgn in (-1, 1):
        em.lamp_box((x0 - 0.14, sgn * (hx + 0.06) - 0.03, BLAST_H + 0.2), (x0 - 0.10, sgn * (hx + 0.06) + 0.03, BLAST_H + 0.26), "red", LAMP)
    em.lamp_box((x0 - 0.12, -0.10, BLAST_H + 0.20), (x0 - 0.10, 0.10, BLAST_H + 0.25), "green", LAMP)
    # finish on the approach side between the frame and the walls
    for (y0, y1) in ((-HW, -hx - 0.2), (hx + 0.2, HW)):
        if y1 - y0 > 0.2:
            SW_panel_x(fb, x0, y0 + 0.03, y1 - 0.03, 0.36, H - 0.55)
    fb.box((x0 - 0.06, -hx - 0.2, BLAST_H + 0.18), (x0, hx + 0.2, H - 0.06), COMPOSITE)
    fb.box((x0 - 0.045, -0.9, BLAST_H + 0.26), (x0 - 0.02, 0.9, H - 0.14), SL.DGLASS)         # the sign field over the opening


# -------------------------------------------------------------------------------------------------------------- the keel's crawlways
ALCOVE = (1.45, 2.55)                                       # a trunk cell's ladder niche: its extent along x (the niche is 1.1 m deep, from the walkway's side wall to the slot's edge)


def slab(fb, z0: float, z1: float, hole=None) -> None:
    """The floor or the roof structure of a 4 x 4 cell, with the ladder shaft's hole through it when `hole` = (x0, x1) (the niche: y from the walkway's wall to the slot's edge)."""
    if hole is None:
        fb.box((-OV, -SLOT_HW, z0), (MOD + OV, SLOT_HW, z1), STRUCT)
        return
    a, c = hole
    y0 = CRAWL_HW
    fb.box((-OV, -SLOT_HW, z0), (MOD + OV, y0, z1), STRUCT)
    fb.box((-OV, y0, z0), (a, SLOT_HW, z1), STRUCT)
    fb.box((c, y0, z0), (MOD + OV, SLOT_HW, z1), STRUCT)


def trunk_alcove(b: SParts, tw: float, kh: float, variant: str, tn: dict) -> None:
    """The inside of a Jefferies trunk's niche (wall-local frame of the starboard wall: s along the cell, t from the walkway's wall face (0) into the wall, to 1.1): two ladder rails on the
    back wall with rungs every 0.3 m that run up through the roof and down through the floor, a safety cage of hoops over the deck, a lamp, the labels; the top of the column has its roof
    closed with a hatch plate, the bottom its floor closed and a toe plate."""
    fb, fine, em = b.body, b.fine, b.emit
    a, c = ALCOVE
    sc = (a + c) / 2
    tb = tw - 0.06                                                   # the back wall's face
    fb.box((a - 0.02, tb, 0.0), (c + 0.02, tw, kh), STRUCT)         # the niche's back wall (the slot's edge)
    fb.box((a - 0.02, tb, kh), (c + 0.02, tw, kh + 1.2), STRUCT)    # ... and the shaft's, up through the roof's thickness
    fb.box((a - 0.02, tb, -FLOOR_T), (c + 0.02, tw, 0.0), STRUCT)   # ... and down through the floor's
    for sx in (sc - 0.22, sc + 0.22):                                # the rails
        fine.box((sx - 0.02, tb - 0.1, -0.30 if variant != "TrunkBottom" else 0.0), (sx + 0.02, tb - 0.06, kh + 1.2 if variant != "TrunkTop" else kh), TRIM)
    z_lo = 0.0 if variant == "TrunkBottom" else -0.28
    z_hi = kh if variant == "TrunkTop" else kh + 1.15
    z = z_lo + 0.15
    while z < z_hi:
        fine.cyl((sc - 0.22, tb - 0.08, z), (sc + 0.22, tb - 0.08, z), 0.014, STRUCT, seg=6)
        z += 0.30
    for zc in (2.15, 3.0, 3.85):                                     # the safety cage
        if variant == "TrunkTop" and zc > kh - 0.2:
            continue
        if zc > z_hi:
            continue
        fine.box((a + 0.06, tb - 0.55, zc - 0.015), (c - 0.06, tb - 0.52, zc + 0.015), TRIM)
        fine.box((a + 0.06, tb - 0.55, zc - 0.015), (a + 0.09, tb - 0.10, zc + 0.015), TRIM)
        fine.box((c - 0.09, tb - 0.55, zc - 0.015), (c - 0.06, tb - 0.10, zc + 0.015), TRIM)
    fb.box((a, 0.0, 0.0), (c, 0.015, 0.012), TRIM)                   # the sill between the walkway and the niche
    if variant == "TrunkBottom":                                     # the bottom of the column: a toe plate over the last rung
        fine.box((a + 0.02, 0.0, 0.012), (c - 0.02, 0.05, 0.14), TRIM)
    else:                                                            # the floor opening: a kerb and a yellow edge
        fine.box((a, 0.03, 0.0), (c, 0.06, 0.07), TRIM)
        fb.label((sc, 0.0, 0.0125), c - a, 0.10, (0, 0, 1), "hazard_h", up=(0, 1, 0))
    em.lamp_box((sc - 0.15, 0.2, kh - 0.04), (sc + 0.15, 0.5, kh - 0.03), tn["strip"], LAMP_DIM)
    fb.label((sc, 0.0, 1.9), 0.5, 0.125, (0, -1, 0), "tag_13")
    if variant == "TrunkTop":
        fb.box((a, 0.0, kh - 0.05), (c, tw, kh), COMPOSITE)
        fb.label((sc, tb - 0.02, kh - 0.3), 0.5, 0.125, (0, -1, 0), "small_06")


# --------------------------------------------------------------------------------------------------------------- the build of a crawlway cell
def _crawl_matrix(side: int) -> Matrix:
    m = Matrix.Identity(4)
    m[1][1] = float(side)
    m[1][3] = side * CRAWL_HW
    return m


def parse_trunk(suffix: str):
    """A trunk module's name: Trunk | TrunkTop | TrunkBottom, with EndFwd / EndAft when the arm ends in this cell (a one-module arm): (variant, end) or None."""
    for base in ("TrunkBottom", "TrunkTop", "Trunk"):
        if suffix.startswith(base):
            tail = suffix[len(base):]
            return base, (tail if tail in ("EndFwd", "EndAft") else None)
    return None


def build_crawl_module(name: str, suffix: str) -> "bpy.types.Object":
    """A module of the keel's crawlways (tone K, Deck 12): the same names, 4 x 4 m cell and openings as the corridor modules, but a 1.7 m wide and 2.5 m high tunnel in the middle
    of the slot: 1.15 m thick walls with pipe bundles in three rows, a cable tray and a hull frame every 2 m; a roof 1.2 m thick with a pipe run and a dim lamp strip; a grating floor
    with low amber guide lights. A room's hatch (1.6 x 2.4) or a side crawlway (1.7 wide) is a short tunnel through the wall."""
    trunk = parse_trunk(suffix)
    if trunk:                                                     # a Jefferies trunk cell: a straight cell with the ladder shaft in an alcove of its starboard wall (local +y)
        left, right, aft, fwd = "wall", "alcove", "closed" if trunk[1] == "EndAft" else "open", "closed" if trunk[1] == "EndFwd" else "open"
    else:
        left, right, aft, fwd = CORRIDOR_SPECS[suffix.split("#")[0]]
    tn = TONES["K"]
    seed = sum(ord(c) for c in name) * 7 + 13
    rng = random.Random(seed)
    b = SParts(bevel=0.006, fine_bevel=0.0)
    fb, fine, em, soft = b.body, b.fine, b.emit, b.soft
    kw, kh = CRAWL_HW, CRAWL_H
    tw = SLOT_HW - kw
    hole_floor = bool(trunk) and trunk[0] in ("Trunk", "TrunkTop")        # the shaft passes through the floor (not at the bottom of the column) and the roof (not at the top)
    hole_roof = bool(trunk) and trunk[0] in ("Trunk", "TrunkBottom")
    # floor: structure, plates over the clear width, guide lights, a chevron
    slab(fb, -FLOOR_T, -0.012, ALCOVE if hole_floor else None)
    for j in range(2):
        for (a, c) in ((0.0, 2.0), (2.0, 4.0)) if j == 0 else ((0.0, 1.0), (1.0, 3.0), (3.0, 4.0)):
            faces = fb.box((a - (OV if a == 0.0 else 0.0) + 0.008, -kw + j * kw + 0.008, -0.012), (c + (OV if c == MOD else 0.0) - 0.008, -kw + (j + 1) * kw - 0.008, 0.0), DECK)
            plate_uv(fb, faces, rng, 1.0)
    for y in (-0.62, 0.62):
        em.lamp_box((0.15, y - 0.012, 0.0), (MOD - 0.15, y + 0.012, 0.004), tn["accent_dim"], LAMP_DIM)
    SL.lamp_strip(em, (1.8, -0.2, 0.002), (2.2, 0.0, 0.002), 0.03, 0.004, tn["accent"], LAMP_DIM)
    SL.lamp_strip(em, (1.8, 0.2, 0.002), (2.2, 0.0, 0.002), 0.03, 0.004, tn["accent"], LAMP_DIM)
    # roof: a thick slab, pipe runs, a cable tray and the dim strip along the middle
    slab(fb, kh, kh + 1.2, ALCOVE if hole_roof else None)
    for k, (y, r, mat) in enumerate(((-0.52, 0.07, CRATE_BLUE), (-0.34, 0.05, TRIM), (0.5, 0.09, STEEL), (0.28, 0.045, CRATE_ORANGE))):
        soft.cyl((-OV, y, kh - r - 0.02), (MOD + OV, y, kh - r - 0.02), r, mat, seg=8)
    for s in (0.5, 2.5):
        soft.box((s - 0.03, -0.62, kh - 0.2), (s + 0.03, 0.62, kh), STRUCT)
    em.lamp_box((0.1, -0.08, kh - 0.03), (MOD - 0.1, 0.08, kh - 0.018), tn["strip"], LAMP_DIM)
    # the walls
    ribs = (0.0, 2.0)
    for side, kind in ((-1, left), (1, right)):
        with b.at(_crawl_matrix(side)):
            op = {"door": (2.0 - DOOR_W / 2, 2.0 + DOOR_W / 2, DOOR_H), "gate": (0.8, 3.2, kh), "branch": (2.0 - kw, 2.0 + kw, kh), "alcove": (ALCOVE[0], ALCOVE[1], kh)}.get(kind)
            if op is None:
                fb.box((-OV, 0.0, 0.0), (MOD + OV, tw, kh), STRUCT)
            else:
                a, c, oh = op
                fb.box((-OV, 0.0, 0.0), (a, tw, kh), STRUCT)
                fb.box((c, 0.0, 0.0), (MOD + OV, tw, kh), STRUCT)
                if oh < kh:
                    fb.box((a, 0.0, oh), (c, tw, kh), STRUCT)
            spans = [(0.0, MOD)] if op is None else [(0.0, op[0] - 0.02), (op[1] + 0.02, MOD)]
            for (s0, s1) in spans:
                if s1 - s0 < 0.2:
                    continue
                fb.box((s0 + 0.02, -0.04, 0.1), (s1 - 0.02, 0.0, 0.95), COMPOSITE)                                      # the lower panel
                for z, mats in ((0.42, (CRATE_BLUE, TRIM)), (1.0, (STEEL, CRATE_ORANGE, TRIM)), (1.55, (PAINT_RED, CRATE_BLUE))):
                    for j, mat in enumerate(mats):
                        r = 0.05 + 0.012 * ((j + int(z * 10)) % 3)
                        soft.cyl((s0 + 0.02, -r - 0.02, z + j * 0.11), (s1 - 0.02, -r - 0.02, z + j * 0.11), r, mat, seg=8)
                soft.box((s0 + 0.02, -0.1, 2.0), (s1 - 0.02, 0.0, 2.04), STRUCT)                                          # the cable tray
                for k in range(3):
                    soft.cyl((s0 + 0.02, -0.03 - 0.025 * k, 2.06), (s1 - 0.02, -0.03 - 0.025 * k, 2.06), 0.012, RUBBER, seg=5)
            for s in ribs:                                                                                                  # a hull frame every 2 m
                if op is not None and op[0] - 0.4 < s < op[1] + 0.4:
                    continue
                fb.box((s - 0.07, -0.16, 0.0), (s + 0.07, 0.0, kh), TRIM)
                fb.box((s - 0.07, -0.16, kh - 0.12), (s + 0.07, 0.0, kh), STRUCT)
                em.lamp_box((s - 0.006, -0.162, 0.3), (s + 0.006, -0.158, kh - 0.4), tn["accent_dim"], LAMP_DIM)
            if op is not None and kind in ("door", "gate"):                                                                 # the hatch tunnel: brushed lining, a threshold, a status lamp
                a, c, oh = op
                fine.box((a - 0.04, 0.0, 0.0), (a, tw, oh + 0.04), TRIM)
                fine.box((c, 0.0, 0.0), (c + 0.04, tw, oh + 0.04), TRIM)
                fine.box((a - 0.04, 0.0, oh), (c + 0.04, tw, oh + 0.04), TRIM)
                fine.box((a, 0.0, 0.0), (c, tw, 0.012), TRIM)
                em.lamp_box((c + 0.06, -0.12, 1.55), (c + 0.1, -0.08, 1.62), "green", LAMP_DIM)
                em.lamp_box((a - 0.02, 0.01, 2.3), (c + 0.02, 0.012 + 0.01, 2.34), "amber", LAMP_DIM)
            elif op is not None and kind == "alcove":                                                                       # the ladder shaft's niche
                trunk_alcove(b, tw, kh, trunk[0], tn)
            elif op is not None and kind == "branch":                                                                       # the mouth of a side crawlway
                a, c, oh = op
                fine.box((a - 0.05, 0.0, 0.0), (a, tw, kh), TRIM)
                fine.box((c, 0.0, 0.0), (c + 0.05, tw, kh), TRIM)
                em.lamp_box((a - 0.006, -0.01, 0.3), (a, 0.0, kh - 0.4), tn["accent"], LAMP_DIM)
                em.lamp_box((c, -0.01, 0.3), (c + 0.006, 0.0, kh - 0.4), tn["accent"], LAMP_DIM)
    # the ends
    if aft == "closed":                                                                                              # (a one-module arm on the port side: its far end is the aft one)
        fb.box((-OV, -kw - 0.02, 0.0), (0.42, kw + 0.02, kh), STRUCT)
        fine.box((0.42, -0.62, 0.02), (0.47, 0.62, 0.3), TRIM)
        fine.box((0.42, -0.62, 0.3), (0.47, 0.62, kh - 0.2), COMPOSITE)
        em.lamp_box((0.47, -0.44, 1.8), (0.48, -0.40, 1.9), "amber", LAMP)
        em.label((0.49, 0.0, 2.1), 0.8, 0.2, (1, 0, 0), "tag_08")
    if fwd == "closed":
        fb.box((MOD - 0.42, -kw - 0.02, 0.0), (MOD + OV, kw + 0.02, kh), STRUCT)
        fine.box((MOD - 0.47, -0.62, 0.02), (MOD - 0.42, 0.62, 0.3), TRIM)
        fine.box((MOD - 0.47, -0.62, 0.3), (MOD - 0.42, 0.62, kh - 0.2), COMPOSITE)
        em.lamp_box((MOD - 0.48, 0.4, 1.8), (MOD - 0.47, 0.44, 1.9), "amber", LAMP)
        em.label((MOD - 0.49, 0.0, 2.1), 0.8, 0.2, (-1, 0, 0), "tag_08")
    elif fwd == "blast":
        x0, x1 = 3.40, MOD + OV
        hx, oh = 0.6, 1.95
        fb.box((x0, -kw - 0.02, 0.0), (x1, -hx, kh), STRUCT)
        fb.box((x0, hx, 0.0), (x1, kw + 0.02, kh), STRUCT)
        fb.box((x0, -hx, oh), (x1, hx, kh), STRUCT)
        for sgn in (-1, 1):
            fine.box((x0 - 0.1, sgn * hx - (0.14 if sgn < 0 else 0.0), 0.0), (x1 - 0.1, sgn * hx + (0.0 if sgn < 0 else 0.14), oh + 0.12), TRIM)
            fb.label((x0 - 0.103, sgn * (hx + 0.07), oh / 2), oh - 0.1, 0.1, (-1, 0, 0), "hazard_h", up=(0, 1, 0))
            em.lamp_box((x0 - 0.12, sgn * (hx + 0.05) - 0.03, oh + 0.08), (x0 - 0.1, sgn * (hx + 0.05) + 0.03, oh + 0.14), "red", LAMP)
        fine.box((x0 - 0.1, -hx - 0.14, oh), (x1 - 0.1, hx + 0.14, oh + 0.12), TRIM)
        fb.label((x0 - 0.06, 0.0, oh + 0.2), 2 * hx + 0.3, 0.1, (-1, 0, 0), "hazard")
    return b.build(name)


# ----------------------------------------------------------------------------------------------------------------------- a stub
def build_stub(name: str, tone: str, length: float) -> "bpy.types.Object":
    """A plain stretch of corridor shorter than a module (0.3 .. 3.9 m, origin on the floor on the centre line at its aft end, running to x = length): the vestibule that fills
    the gap between the end of a passage on the 4 m grid and the wall of a room that stands off the grid (Main Engineering). Floor plates, a ceiling with its luminaire, plain wall
    panels with the rail and the cornice, open at both ends."""
    tn = TONES[tone]
    n = float(length)
    rng = random.Random(sum(ord(c) for c in name) * 7 + 13)
    b = SParts(bevel=0.006, fine_bevel=0.003)
    fb, fine, em = b.body, b.fine, b.emit
    # floor
    fb.box((-OV, -SLOT_HW, -FLOOR_T), (n + OV, SLOT_HW, -0.012), STRUCT)
    rw = 2 * HW / 4
    for j in range(4):
        faces = fb.box((0.008 - OV, -HW + j * rw + 0.008, -0.012), (n + OV - 0.008, -HW + (j + 1) * rw - 0.008, 0.0), DECK)
        plate_uv(fb, faces, rng, 1.0)
    if n > 0.5:
        for y in (-1.34, 1.34):
            em.lamp_box((0.15, y - 0.014, 0.0), (n - 0.15, y + 0.014, 0.004), tn["accent_dim"], LAMP_DIM)
    # ceiling: structure, composite panels either side of the luminaire, the trough and its strip
    fb.box((-OV, -SLOT_HW, H), (n + OV, SLOT_HW, H + FLOOR_T), STRUCT)
    for sy in (-1, 1):
        y0, y1 = (0.36, HW - 0.06) if sy > 0 else (-HW + 0.06, -0.36)
        fb.box((0.04, y0, H - 0.045), (n - 0.04, y1, H), COMPOSITE)
    if n > 0.4:
        fb.box((0.0, -0.33, H - 0.075), (n, -0.29, H - 0.02), TRIM)
        fb.box((0.0, 0.29, H - 0.075), (n, 0.33, H - 0.02), TRIM)
        fb.box((0.0, -0.29, H - 0.027), (n, 0.29, H - 0.02), STRUCT)
        em.lamp_box((min(0.1, n / 4), -0.22, H - 0.034), (n - min(0.1, n / 4), 0.22, H - 0.028), tn["strip"], LAMP_HOT)
    # walls: structure, a composite panel, the plinth, the rail and the cornice
    for side in (-1, 1):
        with b.at(wall_matrix(side)):
            fb.box((-OV, 0.0, 0.0), (n + OV, WALL_T, H), STRUCT)
            if n > 0.5:
                SW.panel(fb, 0.06, n - 0.06, 0.36, H - 0.55, raised=False)
                SW.plinth(fine, 0.02, n - 0.02, tn["accent_dim"])
            if n > 1.0:
                SW.utility_rail(fine, 0.1, n - 0.1, tn["accent_dim"])
            SW.cornice(fine, 0.0, n, H)
    return b.build(name)


# ------------------------------------------------------------------------------------------------------- the whole module
def build_module(name: str, tone: str, suffix: str) -> "bpy.types.Object":
    if tone == "K":
        return build_crawl_module(name, suffix)
    if tone in ("V", "T"):                                                       # the service corridors and the shuttle's tunnel (NAVE-3: ship_corridor2.py)
        import ship_corridor2 as SC2
        return SC2.build_service_module(name, suffix) if tone == "V" else SC2.build_tunnel_module(name, suffix)
    left, right, aft, fwd = CORRIDOR_SPECS[suffix.split("#")[0]]
    tn = TONES[tone]
    plan_id = "A"
    for ch in ("A", "B", "C"):
        if suffix.endswith("_" + ch):
            plan_id = ch
    seed = sum(ord(c) for c in name) * 7 + 13
    rng = random.Random(seed)
    b = SParts(bevel=0.006, fine_bevel=0.003)
    floor(b, tn, rng)
    ceiling(b, tn, rng, duct_side=1 if plan_id != "B" else -1)
    wall(b, -1, left, tn, rng, plan_id)
    wall(b, 1, right, tn, rng, plan_id)
    if fwd == "closed":
        end_wall(b, tn, rng)
    elif fwd == "blast":
        blast_frame(b, tn)
    return b.build(name)
