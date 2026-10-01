"""ASN Aquila interior kit (NAVE-3): the service corridors and the shuttle's tunnel — the two narrow corridor families that are not the Spine's or the passages'.

  tone V, the service corridors and hull galleries: 2.1 m wide, 2.7 m high, in the same 4 x 4 m slot (walls 0.95 m thick: pipe runs, valves, junction boxes), a low warm light, a handrail,
         a deck of grated plates; the names are the corridors' (Straight_A/B/C, Door_L/R, Door_LR, Gate_L/R/LR, T_L/T_R/X, Bulkhead, End);
  tone T, the Spine Shuttle's tunnel: 3.5 m wide, 3.25 m high, 0.25 m walls, a track bed (two rails, sleepers, a guide line) and a service ledge on the starboard side, cold light, cable
         trays and hazard marks; Straight_A/B, the section's blast gate (Bulkhead: the car's 2.9 m opening) and the closed end of the line with its buffers.

Same module frame as ship_corridor.py: origin on the floor on the centre line at the AFT end, x forward 0..4, y across (starboard +), z up.
"""
from __future__ import annotations

import random

from mathutils import Matrix

import ship_lib as SL
import ship_walls as SW
from ship_catalog import CORRIDOR_SPECS, DOOR_H, DOOR_W, MOD, SERV_H, SERV_HW, SLOT_HW, TONES, TUNNEL_H, TUNNEL_HW
from ship_corridor import FLOOR_T, OV, plate_uv
from ship_lib import (COMPOSITE, CRATE_BLUE, CRATE_ORANGE, CRATE_GREY, DECK, DGLASS, LAMP, LAMP_DIM, LAMP_HOT, PAINT_RED, RUBBER, STEEL, STRUCT, TRIM, SParts)


def _wall_matrix(side: int, hw: float) -> Matrix:
    """The wall-local frame of a narrow corridor (s along the wall, t from the finished face INTO the wall, z up): the face is at y = side * hw."""
    m = Matrix.Identity(4)
    m[1][1] = float(side)
    m[1][3] = side * hw
    return m


def _wall_opening(kind: str, hw: float, h: float):
    return {"door": (2.0 - DOOR_W / 2, 2.0 + DOOR_W / 2, DOOR_H), "gate": (0.8, 3.2, h), "branch": (2.0 - hw, 2.0 + hw, h)}.get(kind)


# ======================================================================================================================================================= V: the service corridor
PIPE_MATS = (CRATE_BLUE, STEEL, CRATE_ORANGE, PAINT_RED, CRATE_GREY)
TAGS_V = ("eq_pipe", "eq_water", "eq_air", "eq_cable", "eq_dc", "eq_maint", "eq_breaker", "eq_vent")


def _service_wall(b: SParts, side: int, kind: str, tn: dict, rng: random.Random, plan_id: str) -> None:
    fb, fine, em, soft = b.body, b.fine, b.emit, b.soft
    hw, kh = SERV_HW, SERV_H
    tw = SLOT_HW - hw
    op = _wall_opening(kind, hw, kh)
    with b.at(_wall_matrix(side, hw)):
        # the structure, with the opening cut through
        if op is None:
            fb.box((-OV, 0.0, 0.0), (MOD + OV, tw, kh), STRUCT)
        else:
            a, c, oh = op
            fb.box((-OV, 0.0, 0.0), (a, tw, kh), STRUCT)
            fb.box((c, 0.0, 0.0), (MOD + OV, tw, kh), STRUCT)
            if oh < kh:
                fb.box((a, 0.0, oh), (c, tw, kh), STRUCT)
        spans = [(0.0, MOD)] if op is None else [(0.0, op[0] - 0.08), (op[1] + 0.08, MOD)]
        for (s0, s1) in spans:
            if s1 - s0 < 0.3:
                continue
            fb.box((s0 + 0.02, -0.04, 0.08), (s1 - 0.02, 0.0, 0.92), COMPOSITE)                       # the lower panel, bolted, with a plinth lamp
            SW.bolts_rect(fb, s0 + 0.02, s1 - 0.02, 0.08, 0.92, -0.04, 0.05)
            em.lamp_box((s0 + 0.1, -0.044, 0.12), (s1 - 0.1, -0.04, 0.135), tn["accent_dim"], LAMP_DIM)
            # pipe runs above it: three rows, each a different service, on brackets
            for row, z in enumerate((1.28, 1.74, 2.2)):
                k = (row + (1 if side > 0 else 0) + (plan_id == "B")) % len(PIPE_MATS)
                r = 0.05 + 0.012 * ((row + int(side)) % 3)
                soft.cyl((s0 + 0.02, -r - 0.03, z), (s1 - 0.02, -r - 0.03, z), r, PIPE_MATS[k], seg=10)
                if row == 1:
                    soft.cyl((s0 + 0.02, -0.09, z + 0.13), (s1 - 0.02, -0.09, z + 0.13), 0.028, TRIM, seg=8)
                s = s0 + 0.35
                while s < s1 - 0.1:                                                                       # brackets and, here and there, a flange
                    fine.box((s - 0.02, -r - 0.07, z - r - 0.02), (s + 0.02, 0.0, z + r + 0.02), TRIM)
                    if (int(s * 10) + row) % 7 == 0:
                        fine.cyl((s + 0.25, -r - 0.03, z), (s + 0.31, -r - 0.03, z), r + 0.025, TRIM, seg=10)
                    s += 0.9
            # a valve with a hand-wheel and a stencilled tag
            sv = (s0 + s1) / 2 + rng.uniform(-0.2, 0.2)
            if s1 - s0 > 1.2:
                zv = 1.28 if rng.random() < 0.5 else 1.74
                fine.cyl((sv, -0.14, zv - 0.0), (sv, -0.2, zv), 0.11, TRIM, seg=14, r2=0.11)
                fine.cyl((sv, -0.2, zv), (sv, -0.21, zv), 0.15, PAINT_RED, seg=14)
                fb.label((sv, -0.012, 0.62), 0.5, 0.125, (0, -1, 0), TAGS_V[(int(s0 * 10) + side + plan_id.count("B")) % len(TAGS_V)])
        # frame ribs every 2 m (not through an opening)
        for s in (0.0, 2.0):
            if op is not None and op[0] - 0.4 < s < op[1] + 0.4:
                continue
            fb.box((s - 0.07, -0.14, 0.0), (s + 0.07, 0.0, kh), TRIM)
            fb.box((s - 0.07, -0.14, kh - 0.12), (s + 0.07, 0.0, kh), STRUCT)
            em.lamp_box((s - 0.006, -0.142, 0.4), (s + 0.006, -0.138, kh - 0.5), tn["accent_dim"], LAMP_DIM)
        # the handrail along the starboard wall; a hose reel in a bay of the port one
        if kind == "wall" and side > 0:
            SW.utility_rail(fine, 0.15, 3.85, tn["accent_dim"], z=1.0)
        if kind == "wall" and side < 0 and plan_id == "A":
            fb.box((1.25, -0.2, 0.9), (2.75, -0.02, 1.9), TRIM)
            fb.cyl((2.0, -0.22, 1.4), (2.0, -0.3, 1.4), 0.3, PAINT_RED, seg=18)
            fb.cyl((2.0, -0.3, 1.4), (2.0, -0.32, 1.4), 0.22, RUBBER, seg=18)
            fb.label((2.0, -0.215, 1.97), 0.5, 0.125, (0, -1, 0), "eq_hydrant")
        if op is not None and kind in ("door", "gate"):                                                  # the hatch: a brushed lining through the wall, a sill, a lamp, a tag beside it
            a, c, oh = op
            fine.box((a - 0.05, 0.0, 0.0), (a, tw, oh + 0.05), TRIM)
            fine.box((c, 0.0, 0.0), (c + 0.05, tw, oh + 0.05), TRIM)
            fine.box((a - 0.05, 0.0, oh), (c + 0.05, tw, oh + 0.05), TRIM)
            fine.box((a, 0.0, 0.0), (c, tw, 0.014), TRIM)
            fine.box((a - 0.07, -0.07, 0.0), (a - 0.05, 0.0, oh + 0.07), STRUCT)
            fine.box((c + 0.05, -0.07, 0.0), (c + 0.07, 0.0, oh + 0.07), STRUCT)
            fine.box((a - 0.07, -0.07, oh + 0.05), (c + 0.07, 0.0, oh + 0.07), STRUCT)
            em.lamp_box((c + 0.1, -0.1, 1.6), (c + 0.14, -0.06, 1.68), "green", LAMP_DIM)
            em.lamp_box((a + 0.3, -0.075, oh + 0.09), (c - 0.3, -0.07, oh + 0.12), "amber", LAMP)
        elif op is not None and kind == "branch":                                                        # the mouth of a side corridor: jambs with lamp lines
            a, c, oh = op
            for s in (a, c):
                fine.box((s - 0.05 if s < 2.0 else s, -0.07, 0.0), (s if s < 2.0 else s + 0.05, tw, kh), TRIM)
                em.lamp_box((s - 0.006, -0.075, 0.3), (s + 0.006, -0.07, kh - 0.4), tn["accent"], LAMP_DIM)


def build_service_module(name: str, suffix: str) -> "bpy.types.Object":
    left, right, aft, fwd = CORRIDOR_SPECS[suffix.split("#")[0]]
    tn = TONES["V"]
    plan_id = "B" if suffix.endswith("_B") else "A"
    rng = random.Random(sum(ord(c) for c in name) * 7 + 13)
    b = SParts(bevel=0.006, fine_bevel=0.0)
    fb, fine, em, soft = b.body, b.fine, b.emit, b.soft
    hw, kh = SERV_HW, SERV_H
    # the floor: structure and grated plates over the clear width, low amber guide lights, a chevron
    fb.box((-OV, -SLOT_HW, -FLOOR_T), (MOD + OV, SLOT_HW, -0.012), STRUCT)
    for j in range(2):
        for (a, c) in ((0.0, 2.0), (2.0, 4.0)) if j == 0 else ((0.0, 1.0), (1.0, 3.0), (3.0, 4.0)):
            faces = fb.box((a - (OV if a == 0.0 else 0.0) + 0.008, -hw + j * hw + 0.008, -0.012), (c + (OV if c == MOD else 0.0) - 0.008, -hw + (j + 1) * hw - 0.008, 0.0), DECK)
            plate_uv(fb, faces, rng, 1.0)
    for y in (-0.93, 0.93):
        em.lamp_box((0.15, y - 0.012, 0.0), (MOD - 0.15, y + 0.012, 0.004), tn["accent_dim"], LAMP_DIM)
    SL.lamp_strip(em, (1.76, -0.26, 0.002), (2.16, 0.0, 0.002), 0.03, 0.004, tn["accent"], LAMP_DIM)
    SL.lamp_strip(em, (1.76, 0.26, 0.002), (2.16, 0.0, 0.002), 0.03, 0.004, tn["accent"], LAMP_DIM)
    # the roof: a slab, a pipe run on one side, a cable tray on the other, a warm lamp strip in a trough along the middle
    fb.box((-OV, -SLOT_HW, kh), (MOD + OV, SLOT_HW, kh + 1.0), STRUCT)
    duct = -1 if plan_id == "A" else 1
    for k, (y, r, mat) in enumerate(((0.62, 0.075, CRATE_BLUE), (0.44, 0.05, STEEL), (0.82, 0.05, PAINT_RED))):
        soft.cyl((-OV, duct * y, kh - r - 0.03), (MOD + OV, duct * y, kh - r - 0.03), r, mat, seg=10)
    for s in (0.5, 1.5, 2.5, 3.5):
        fine.box((s - 0.02, duct * 0.95, kh - 0.27), (s + 0.02, duct * 0.3, kh), TRIM)
    yt = -duct * 0.62
    soft.box((-OV, yt - 0.25, kh - 0.14), (MOD + OV, yt + 0.25, kh - 0.1), STRUCT)
    for k in range(4):
        soft.cyl((-OV, yt - 0.18 + 0.12 * k, kh - 0.07), (MOD + OV, yt - 0.18 + 0.12 * k, kh - 0.07), 0.016, RUBBER, seg=6)
    fb.box((0.1, -0.16, kh - 0.07), (MOD - 0.1, -0.12, kh - 0.01), TRIM)
    fb.box((0.1, 0.12, kh - 0.07), (MOD - 0.1, 0.16, kh - 0.01), TRIM)
    em.lamp_box((0.18, -0.12, kh - 0.04), (MOD - 0.18, 0.12, kh - 0.032), tn["strip"], LAMP_DIM)
    # the walls
    _service_wall(b, -1, left, tn, rng, plan_id)
    _service_wall(b, 1, right, tn, rng, plan_id)
    # the ends
    if fwd == "closed":
        fb.box((MOD - 0.42, -hw - 0.02, 0.0), (MOD + OV, hw + 0.02, kh), STRUCT)
        fine.box((MOD - 0.47, -0.7, 0.02), (MOD - 0.42, 0.7, 0.3), TRIM)
        fine.box((MOD - 0.47, -0.7, 0.3), (MOD - 0.42, 0.7, kh - 0.2), COMPOSITE)
        fine.box((MOD - 0.49, -0.32, 0.55), (MOD - 0.47, 0.32, 1.65), TRIM)                      # a service hatch
        fine.box((MOD - 0.5, -0.27, 0.6), (MOD - 0.49, 0.27, 1.6), STRUCT)
        em.lamp_box((MOD - 0.51, 0.46, 1.8), (MOD - 0.5, 0.5, 1.9), "amber", LAMP)
        em.label((MOD - 0.52, 0.0, 2.1), 0.8, 0.2, (-1, 0, 0), "tag_08")
    elif fwd == "blast":
        x0, x1 = 3.40, MOD + OV
        hx, oh = 0.6, 1.95
        fb.box((x0, -hw - 0.02, 0.0), (x1, -hx, kh), STRUCT)
        fb.box((x0, hx, 0.0), (x1, hw + 0.02, kh), STRUCT)
        fb.box((x0, -hx, oh), (x1, hx, kh), STRUCT)
        for sgn in (-1, 1):
            fine.box((x0 - 0.1, sgn * hx - (0.14 if sgn < 0 else 0.0), 0.0), (x1 - 0.1, sgn * hx + (0.0 if sgn < 0 else 0.14), oh + 0.12), TRIM)
            fb.label((x0 - 0.103, sgn * (hx + 0.07), oh / 2), oh - 0.1, 0.1, (-1, 0, 0), "hazard_h", up=(0, 1, 0))
            em.lamp_box((x0 - 0.12, sgn * (hx + 0.05) - 0.03, oh + 0.08), (x0 - 0.1, sgn * (hx + 0.05) + 0.03, oh + 0.14), "red", LAMP)
        fine.box((x0 - 0.1, -hx - 0.14, oh), (x1 - 0.1, hx + 0.14, oh + 0.12), TRIM)
        fb.label((x0 - 0.06, 0.0, oh + 0.2), 2 * hx + 0.3, 0.1, (-1, 0, 0), "hazard")
    return b.build(name)


# ======================================================================================================================================================= T: the shuttle's tunnel
RAIL_Y = 0.65                       # the rails' gauge: 1.3 m
LEDGE_Y = 1.10                      # the service ledge on the starboard side: y 1.10 .. 1.75, 0.22 m above the track bed


def _tunnel_floor(b: SParts, tn: dict, rng: random.Random) -> None:
    fb, fine, em = b.body, b.fine, b.emit
    hw = TUNNEL_HW
    fb.box((-OV, -SLOT_HW, -FLOOR_T), (MOD + OV, SLOT_HW, -0.012), STRUCT)
    faces = fb.box((-OV, -hw, -0.012), (MOD + OV, hw, 0.0), DECK)                               # the bed
    plate_uv(fb, faces, rng, 1.0)
    for s in (0.2, 1.0, 1.8, 2.6, 3.4):                                                         # sleepers
        fine.box((s - 0.11, -1.0, 0.0), (s + 0.11, 1.0, 0.035), TRIM)
    for y in (-RAIL_Y, RAIL_Y):                                                                 # the rails: a foot, a web and a head
        fine.box((-OV, y - 0.05, 0.035), (MOD + OV, y + 0.05, 0.05), STEEL)
        fine.box((-OV, y - 0.018, 0.05), (MOD + OV, y + 0.018, 0.13), STEEL)
        fine.box((-OV, y - 0.045, 0.13), (MOD + OV, y + 0.045, 0.16), STEEL)
    em.lamp_box((-OV, -0.014, 0.036), (MOD + OV, 0.014, 0.046), tn["accent_dim"], LAMP_DIM)         # the guide line in the middle of the track
    fine.box((-OV, -0.18, 0.036), (MOD + OV, -0.1, 0.07), TRIM)                                  # the power rail's cover
    fb.box((-OV, LEDGE_Y, 0.0), (MOD + OV, hw, 0.22), STRUCT)                                    # the service ledge, a tread on top, a yellow edge and a low lamp line
    fine.box((-OV, LEDGE_Y + 0.02, 0.22), (MOD + OV, hw - 0.02, 0.232), TRIM)
    fb.label((2.0, LEDGE_Y - 0.001, 0.12), MOD, 0.14, (0, -1, 0), "hazard_h")
    em.lamp_box((0.15, LEDGE_Y + 0.05, 0.234), (MOD - 0.15, LEDGE_Y + 0.07, 0.24), tn["accent"], LAMP_DIM)
    for y0, y1 in ((-hw, -1.2),):                                                                # a cable trench cover on the other side
        fine.box((-OV, y0, 0.0), (MOD + OV, y1, 0.018), TRIM)


def _tunnel_walls(b: SParts, tn: dict, rng: random.Random) -> None:
    fb, fine, em, soft = b.body, b.fine, b.emit, b.soft
    hw, kh = TUNNEL_HW, TUNNEL_H
    tw = SLOT_HW - hw
    for side in (-1, 1):
        with b.at(_wall_matrix(side, hw)):
            fb.box((-OV, 0.0, 0.0), (MOD + OV, tw, kh), STRUCT)
            fb.box((0.02, -0.035, 0.1), (MOD - 0.02, 0.0, 1.45), COMPOSITE)                      # the lower panel and the hazard base line
            SW.bolts_rect(fb, 0.02, MOD - 0.02, 0.1, 1.45, -0.035, 0.06)
            fb.label((2.0, -0.036, 0.1), MOD - 0.2, 0.08, (0, -1, 0), "hazard")
            for z, mat in ((1.75, CRATE_BLUE), (2.05, STEEL)):                                    # the cable trays and a pipe, on brackets
                soft.box((0.02, -0.22, z), (MOD - 0.02, 0.0, z + 0.04), STRUCT)
                soft.box((0.02, -0.22, z), (MOD - 0.02, -0.215, z + 0.13), STRUCT)
                for k in range(4):
                    soft.cyl((0.02, -0.05 - 0.04 * k, z + 0.08), (MOD - 0.02, -0.05 - 0.04 * k, z + 0.08), 0.014, RUBBER if k % 2 == 0 else mat, seg=6)
            soft.cyl((0.02, -0.09, 2.62), (MOD - 0.02, -0.09, 2.62), 0.06, CRATE_ORANGE if side > 0 else CRATE_GREY, seg=10)
            for s in (0.0, 2.0):                                                                  # frame ribs with a cold lamp line, and a stencil tile on the one at 2.0
                fb.box((s - 0.09, -0.2, 0.0), (s + 0.09, 0.0, kh), TRIM)
                fb.box((s - 0.09, -0.2, kh - 0.18), (s + 0.09, 0.0, kh), STRUCT)
                em.lamp_box((s - 0.007, -0.205, 0.5), (s + 0.007, -0.2, kh - 0.5), tn["accent_dim"], LAMP_DIM)
            fb.label((1.0, -0.037, 2.78), 0.5, 0.125, (0, -1, 0), "tag_08" if side > 0 else "eq_cable")
            fb.label((3.0, -0.037, 0.9), 0.18, 0.18, (0, -1, 0), "icon_exit")
            em.lamp_box((1.5, -0.04, 0.42), (2.5, -0.036, 0.45), tn["accent_dim"], LAMP_DIM)
    # the ceiling: a slab, two luminaire strips, a rectangular duct along the middle, hangers
    fb.box((-OV, -SLOT_HW, kh), (MOD + OV, SLOT_HW, kh + 0.45), STRUCT)
    for y in (-1.0, 1.0):
        fb.box((0.12, y - 0.17, kh - 0.07), (MOD - 0.12, y - 0.13, kh - 0.01), TRIM)
        fb.box((0.12, y + 0.13, kh - 0.07), (MOD - 0.12, y + 0.17, kh - 0.01), TRIM)
        em.lamp_box((0.2, y - 0.13, kh - 0.04), (MOD - 0.2, y + 0.13, kh - 0.032), tn["strip"], LAMP)
    soft.box((-OV, -0.3, kh - 0.34), (MOD + OV, 0.3, kh - 0.04), COMPOSITE)
    for k in range(3):
        soft.box((0.4 + k * 1.3, -0.25, kh - 0.345), (0.8 + k * 1.3, 0.25, kh - 0.34), RUBBER)
    for s in (0.6, 2.6):
        fine.box((s - 0.03, -0.34, kh - 0.4), (s + 0.03, 0.34, kh), TRIM)


def build_tunnel_module(name: str, suffix: str) -> "bpy.types.Object":
    tn = TONES["T"]
    rng = random.Random(sum(ord(c) for c in name) * 7 + 13)
    b = SParts(bevel=0.006, fine_bevel=0.0)
    fb, fine, em, soft = b.body, b.fine, b.emit, b.soft
    hw, kh = TUNNEL_HW, TUNNEL_H
    _tunnel_floor(b, tn, rng)
    _tunnel_walls(b, tn, rng)
    if suffix == "Bulkhead":                                                                    # the section's blast gate: the car's opening 2.9 x 3.0, two leaves parked in the pillars
        x0, x1 = 3.30, MOD + OV
        ho, oh = 1.45, 3.0
        fb.box((x0, -hw - 0.02, 0.0), (x1, -ho, kh + 0.45), STRUCT)
        fb.box((x0, ho, 0.0), (x1, hw + 0.02, kh + 0.45), STRUCT)
        fb.box((x0, -ho, oh), (x1, ho, kh + 0.45), STRUCT)
        for sgn in (-1, 1):
            fine.box((x0 - 0.12, sgn * ho - (0.2 if sgn < 0 else 0.0), 0.0), (x1 - 0.1, sgn * ho + (0.0 if sgn < 0 else 0.2), oh + 0.14), TRIM)
            fb.label((x0 - 0.123, sgn * (ho + 0.1), oh / 2), oh - 0.1, 0.12, (-1, 0, 0), "hazard_h", up=(0, 1, 0))
            for z in (0.5, 1.4, 2.3):
                fine.box((x0 - 0.16, sgn * (ho + 0.1) - 0.09, z - 0.06), (x0 - 0.12, sgn * (ho + 0.1) + 0.09, z + 0.06), STRUCT)
            em.lamp_box((x0 - 0.15, sgn * (ho + 0.1) - 0.04, oh + 0.04), (x0 - 0.12, sgn * (ho + 0.1) + 0.04, oh + 0.12), "red", LAMP)
        fine.box((x0 - 0.12, -ho - 0.2, oh), (x1 - 0.1, ho + 0.2, oh + 0.14), TRIM)
        fb.label((x0 - 0.1, 0.0, oh + 0.24), 2 * ho + 0.3, 0.12, (-1, 0, 0), "hazard")
        em.lamp_box((x0 - 0.14, -0.14, oh + 0.04), (x0 - 0.12, 0.14, oh + 0.1), "green", LAMP)
        fb.box((x0 - 0.06, -ho - 0.15, oh + 0.18), (x0, ho + 0.15, kh + 0.3), COMPOSITE)
        fb.box((x0 - 0.04, -1.0, oh + 0.3), (x0 - 0.02, 1.0, kh + 0.2), DGLASS)                  # the sign field over the opening
    elif suffix == "End":                                                                       # the end of the line: a wall and two buffers
        fb.box((MOD - 0.5, -hw - 0.02, 0.0), (MOD + OV, hw + 0.02, kh + 0.45), STRUCT)
        fb.box((MOD - 0.55, -hw, 0.0), (MOD - 0.5, hw, kh), COMPOSITE)
        for y in (-RAIL_Y, RAIL_Y):
            fine.cyl((MOD - 0.55, y, 0.45), (MOD - 1.15, y, 0.45), 0.09, TRIM, seg=12)
            fine.cyl((MOD - 1.15, y, 0.45), (MOD - 1.3, y, 0.45), 0.13, PAINT_RED, seg=12)
            fine.box((MOD - 0.58, y - 0.2, 0.2), (MOD - 0.55, y + 0.2, 0.7), STRUCT)
        fb.label((MOD - 0.56, 0.0, 2.2), 1.2, 0.3, (-1, 0, 0), "hazard")
        em.lamp_box((MOD - 0.58, -0.1, 2.7), (MOD - 0.56, 0.1, 2.9), "red", LAMP)
    return b.build(name)
