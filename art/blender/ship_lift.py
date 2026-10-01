"""ASCENSORI: the lift kit (docs/ASCENSORI.md): turbolift, service and cargo cars, the shuttle car, their doors, the landings' frames and leaves, the shaft's lining, the call
lamp and post, and the quad of the car's screen. Procedural, headless, in the language of the bridge v3 (docs/STILE.md §11): dark composite panels, brushed frames, light
in the architecture, nothing flat and empty.

Usage:  blender -b --factory-startup --python-exit-code 1 -P art/blender/ship_lift.py -- <output_dir> [--preview <dir>] [--only SM_LIFT_Car_tl,...]
        (default output art/export/ship_lift; the previews are Eevee renders of the car's inside, a landing, a shaft and the shuttle, for looking at the result)

Every mesh is built to the numbers the C++ uses (Source/ASTRA/AstraLiftCar.cpp, FAstraLiftSpec): the car's frame has its origin on the floor under its middle, +X the side of
its doors, +Z up; a landing's frame has its origin in the middle of the opening at floor level, +X into the lobby; a shaft segment's origin is the shaft's middle at the bottom
of the segment, +X the side of the doors. The FBX export flips Y (Blender +Y is Unreal -Y): the car's screen and a landing's call panel are on Blender +Y, which is where the
C++ puts them (Unreal -Y), and a door leaf has its meeting edge on Blender +Y (the Unreal leaf at +Y is the mesh as it is, the one at -Y is its mirror). Meshes are modelled to
the NOMINAL size of their kind (KIT below, the same table as FAstraLiftSpec::Nominal): a plan with other measures gets the mesh scaled.

  SM_LIFT_Car_<k>          the cabin: floor, walls, ceiling, the door's piers and header, the window frame, handrails, light strips, the screen's bezel and the door buttons
  SM_LIFT_CarGlass_<k>     the pane of the window onto the shaft (the shuttle: the long windows)
  SM_LIFT_CarLeaf_<k>      half a door of the car (the other half is the same mirrored)
  SM_LIFT_Landing_<k>      the fascia round a landing's opening, its reveal, the call panel with its lamp socket, the deck sign's plate, the chevrons
  SM_LIFT_LandingLeaf_<k>  half a landing door
  SM_LIFT_Shaft_<k>        a plain 4 m segment of the shaft's lining: guide rails, brackets, cables, light strips
  SM_LIFT_ShaftDoor_<k>    the 3.2 m segment with a landing's opening, a ring of light at the landing
  SM_LIFT_CallLamp         the lamp of the call panel (lit while a car is on its way)      SM_LIFT_CallPost   the shuttle platform's call post      SM_LIFT_Screen   the 1 m quad of the car's screen
  <k> is tl (turbolift), sv (service), cg (cargo); the shuttle is sh (car, glass and leaf only: its platforms and its tunnel are the ship's)
"""
from __future__ import annotations

import json
import os
import sys

import bmesh
import bpy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402

# the lift kit's own slots (tools/ue_scripts/build_lifts.py makes the instances); the others are the standard MI_ASTRA_* of astra_bpy
MAT_LIFT_SCREEN = "MI_LIFT_Screen"      # the car's screen (an instance of the project's screen master; the game paints it)
MAT_LIFT_LAMP = "MI_LIFT_Lamp"          # the call lamp (emissive amber)
MAT_LIFT_RING = "MI_LIFT_Ring"          # the shaft's rings of light (emissive cold blue)

# the nominal measures of each kind (metres), the table of FAstraLiftSpec::Nominal: the car's outer width (across the door) and depth, the inside height, the opening, the shaft inside
KIT = {
    "tl": dict(w=2.4, d=2.4, h=2.6, opw=1.18, oph=2.2, sw=2.8, sd=2.8, name="turbolift"),
    "sv": dict(w=2.8, d=2.4, h=2.8, opw=1.38, oph=2.3, sw=3.2, sd=2.8, name="service"),
    "cg": dict(w=3.4, d=3.0, h=3.2, opw=1.68, oph=2.6, sw=3.8, sd=3.4, name="cargo"),
}
SHUTTLE = dict(length=14.0, d=2.8, h=2.9, floor=0.16, opw=1.30, oph=2.10, doors=(-3.5, 0.0, 3.5))
WALL, FLOOR_T, CEIL_T, LEAF_T = 0.14, 0.30, 0.14, 0.06
SEG_H, DOORSEG_H, DOORSEG_DOWN = 4.0, 3.2, 0.4
SILL_GAP = 0.03


# ---------------------------------------------------------------------------------------------------------------------------------- helpers
def bars(b: A.Builder, x0: float, x1: float, y0: float, y1: float, z0: float, z1: float, t: float, mat: str) -> None:
    """A rectangular frame of bars in the YZ plane (t thick), between x0 and x1."""
    b.box_minmax((x0, y0, z0), (x1, y1, z0 + t), mat)
    b.box_minmax((x0, y0, z1 - t), (x1, y1, z1), mat)
    b.box_minmax((x0, y0, z0 + t), (x1, y0 + t, z1 - t), mat)
    b.box_minmax((x0, y1 - t, z0 + t), (x1, y1, z1 - t), mat)


def finish(b: A.Builder, name: str, bevel: float = 0.004) -> bpy.types.Object:
    obj = b.to_object(name)
    A.finish(obj, bevel=bevel)
    return obj


def part(builders: list, name: str) -> bpy.types.Object:
    """Several builders (each with its own bevel) joined into one mesh."""
    return A.join([finish(b, f"{name}_{i}", bevel) for i, (b, bevel) in enumerate(builders)], name)


def triangle(b: A.Builder, y: float, z: float, up: bool, x0: float, x1: float, mat: str, w: float = 0.045, h: float = 0.04) -> None:
    pts = [(y - w, z - h), (y + w, z - h), (y, z + h)] if up else [(y - w, z + h), (y, z - h), (y + w, z + h)]
    b.prism(pts, x0, x1, mat)


# ---------------------------------------------------------------------------------------------------------------------------------- the car
def car_dims(k: str):
    c = KIT[k]
    return c, (c["w"] - 2 * WALL) / 2, (c["d"] - 2 * WALL) / 2          # the kind, the inside half-width (across the door), the inside half-depth


def window_of(k: str) -> tuple[float, float, float]:
    """The back wall's window: half its width, its sill and its head (inside the car, from the floor)."""
    c = KIT[k]
    return (0.80 if k in ("sv", "cg") else 0.66), 0.45, c["h"] - 0.34


def screen_of(k: str) -> tuple[float, float]:
    return (1.00, 0.625) if k in ("sv", "cg") else (0.80, 0.50)         # the quad's size (m), as FAstraLiftSpec::Make


def corner_posts(trim: A.Builder, xi: float, iw: float, H: float) -> None:
    for sx in (-1, 1):
        for sy in (-1, 1):
            x0, x1 = (xi - 0.035, xi) if sx > 0 else (-xi, -xi + 0.035)
            y0, y1 = (iw - 0.035, iw) if sy > 0 else (-iw, -iw + 0.035)
            trim.box_minmax((x0, y0, 0.0), (x1, y1, H), A.MAT_TRIM)


def handrails(trim: A.Builder, xi: float, iw: float, z: float, side_to: float) -> None:
    """A rail along the back wall and one along each side, 95 cm up and 6 cm off the wall, on brackets; the sides stop at `side_to` (the door's lane is clear)."""
    r = 0.018
    trim.cylinder((-xi + 0.06, -iw + 0.15, z), (-xi + 0.06, iw - 0.15, z), r, A.MAT_TRIM, segments=10)
    for yb in (-0.5, 0.5):
        trim.cylinder((-xi + 0.005, yb, z), (-xi + 0.06, yb, z), 0.01, A.MAT_TRIM, segments=8)
    for sy in (-1, 1):
        trim.cylinder((-xi + 0.15, sy * (iw - 0.06), z), (side_to, sy * (iw - 0.06), z), r, A.MAT_TRIM, segments=10)
        for xb in (-xi + 0.30, side_to - 0.15):
            trim.cylinder((xb, sy * (iw - 0.005), z), (xb, sy * (iw - 0.06), z), 0.01, A.MAT_TRIM, segments=8)


def car_turbolift(k: str, name: str) -> bpy.types.Object:
    c, iw, xi = car_dims(k)
    H, opw, oph = c["h"], c["opw"], c["oph"]
    shell, trim, light, fit = A.Builder(), A.Builder(), A.Builder(), A.Builder()
    xo, yo = xi + WALL, iw + WALL                                          # outer faces (the front wall is +X, the back -X)
    # ---- the floor: a structural slab, the non-skid plate on top, a guide light along the walls, the plates' joints
    shell.box_minmax((-xo, -yo, -FLOOR_T), (xo, yo, -0.04), A.MAT_STRUCTURE)
    shell.box_minmax((-xi, -iw, -0.04), (xi, iw, 0.0), A.MAT_FLOOR)
    for s in (-1, 1):
        light.box_minmax((-xi + 0.02, s * (iw - 0.06), 0.0), (xi - 0.02, s * (iw - 0.045), 0.006), A.MAT_GUIDE)
        light.box_minmax((s * (xi - 0.06), -iw + 0.02, 0.0), (s * (xi - 0.045), iw - 0.02, 0.006), A.MAT_GUIDE)
    for i in range(1, 4):
        y = -iw + i * 2 * iw / 4
        trim.box_minmax((-xi, y - 0.004, 0.0), (xi, y + 0.004, 0.004), A.MAT_STRUCTURE)
    # ---- the ceiling: the slab, the inner panel, two ribs, the light panel, a vent
    shell.box_minmax((-xo, -yo, H), (xo, yo, H + CEIL_T), A.MAT_STRUCTURE)
    shell.box_minmax((-xi, -iw, H - 0.05), (xi, iw, H), A.MAT_PANEL)
    for x in (-0.5 * xi, 0.5 * xi):
        trim.box_minmax((x - 0.025, -iw, H - 0.075), (x + 0.025, iw, H - 0.05), A.MAT_TRIM)
    light.box_minmax((-0.28 * xi, -0.55 * iw, H - 0.062), (0.28 * xi, 0.55 * iw, H - 0.05), A.MAT_LIGHT)
    for i in range(5):
        y = -iw + 0.22 + i * 0.05
        fit.box_minmax((-xi + 0.18, y, H - 0.058), (-xi + 0.46, y + 0.022, H - 0.05), A.MAT_STRUCTURE)
    # ---- the back wall (-X): panels round a window onto the shaft, its frame
    wy, wz0, wz1 = window_of(k)
    for (y0, y1, z0, z1) in ((-yo, -wy, 0.0, H), (wy, yo, 0.0, H), (-wy, wy, 0.0, wz0), (-wy, wy, wz1, H)):
        shell.box_minmax((-xo, y0, z0), (-xi, y1, z1), A.MAT_PANEL)
    bars(trim, -xi - 0.012, -xi + 0.035, -wy - 0.05, wy + 0.05, wz0 - 0.05, wz1 + 0.05, 0.05, A.MAT_TRIM)
    # ---- the side walls: panels, a skirting, a band of colour, a rib at two places, the corner posts
    for s in (-1, 1):
        shell.box_minmax((-xi, s * iw, 0.0), (xi, s * yo, H), A.MAT_PANEL)
        fit.box_minmax((-xi, s * (iw - 0.03) if s > 0 else -iw, 0.0), (xi, iw if s > 0 else -(iw - 0.03), 0.11), A.MAT_STRUCTURE)
        light.box_minmax((-xi, s * (iw - 0.012) if s > 0 else -iw, 1.30), (xi, iw if s > 0 else -(iw - 0.012), 1.34), A.MAT_ACCENT)
        for x in (0.0, 0.5 * xi):
            fit.box_minmax((x - 0.02, s * (iw - 0.012) if s > 0 else -iw, 0.11), (x + 0.02, iw if s > 0 else -(iw - 0.012), H), A.MAT_STRUCTURE)
        light.box_minmax((-xi, s * (iw - 0.07) - 0.008, 0.18), (-xi + 0.012, s * (iw - 0.07) + 0.008, H - 0.2), A.MAT_LIGHT)    # the strips in the back corners
    corner_posts(trim, xi, iw, H)
    # ---- the front wall (+X): the piers and the header round the opening, the reveal, a light over the door
    for (y0, y1, z0, z1) in ((-yo, -opw / 2, 0.0, H + CEIL_T), (opw / 2, yo, 0.0, H + CEIL_T), (-opw / 2, opw / 2, oph, H + CEIL_T)):
        shell.box_minmax((xi, y0, z0), (xo, y1, z1), A.MAT_PANEL)
    bars(trim, xi - 0.01, xo, -opw / 2, opw / 2, 0.0, oph, 0.04, A.MAT_TRIM)
    light.box_minmax((xi - 0.006, -opw / 2 + 0.06, oph + 0.05), (xi + 0.002, opw / 2 - 0.06, oph + 0.075), A.MAT_LIGHT)
    handrails(trim, xi, iw, 0.95, xi - 0.95)
    # ---- the screen's bezel and the door buttons, on the wall at Blender +Y (Unreal -Y), at the right of whoever comes in; the quad stands 3 cm off the wall
    sx_c, sz_c = xi - 0.70, 1.50
    sw_, sh_ = screen_of(k)
    for (x0, x1, z0, z1) in ((sx_c - sw_ / 2 - 0.04, sx_c + sw_ / 2 + 0.04, sz_c + sh_ / 2, sz_c + sh_ / 2 + 0.04),
                             (sx_c - sw_ / 2 - 0.04, sx_c + sw_ / 2 + 0.04, sz_c - sh_ / 2 - 0.04, sz_c - sh_ / 2),
                             (sx_c - sw_ / 2 - 0.04, sx_c - sw_ / 2, sz_c - sh_ / 2, sz_c + sh_ / 2),
                             (sx_c + sw_ / 2, sx_c + sw_ / 2 + 0.04, sz_c - sh_ / 2, sz_c + sh_ / 2)):
        fit.box_minmax((x0, iw - 0.05, z0), (x1, iw, z1), A.MAT_TRIM)
    fit.box_minmax((sx_c - sw_ / 2, iw - 0.027, sz_c - sh_ / 2), (sx_c + sw_ / 2, iw, sz_c + sh_ / 2), A.MAT_STRUCTURE)       # the screen's back, behind the quad (3 cm off the wall)
    fit.box_minmax((sx_c + sw_ / 2 - 0.10, iw - 0.056, sz_c - sh_ / 2 - 0.035), (sx_c + sw_ / 2 - 0.04, iw - 0.05, sz_c - sh_ / 2 - 0.025), A.MAT_GUIDE)   # a status light on the bezel
    zb = sz_c - sh_ / 2 - 0.20
    fit.box_minmax((sx_c - 0.20, iw - 0.045, zb - 0.10), (sx_c + 0.20, iw, zb + 0.10), A.MAT_STRUCTURE)                       # the door buttons and the emergency call
    for i, xb in enumerate((-0.12, 0.0, 0.12)):
        fit.cylinder((sx_c + xb, iw - 0.045, zb), (sx_c + xb, iw - 0.056, zb), 0.022 if i < 2 else 0.018, A.MAT_TRIM if i < 2 else A.MAT_ACCENT, segments=14)
    return part([(shell, 0.006), (trim, 0.003), (light, 0.002), (fit, 0.002)], name)


def car_glass(k: str, name: str) -> bpy.types.Object:
    c, iw, xi = car_dims(k)
    wy, wz0, wz1 = window_of(k)
    b = A.Builder()
    b.box_minmax((-xi - 0.09, -wy, wz0), (-xi - 0.07, wy, wz1), A.MAT_GLASS)
    return finish(b, name, 0.0)


def car_leaf(k: str, name: str) -> bpy.types.Object:
    """Half a door (the car's and the landing's are the same): a brushed panel in a frame, a light slit and a rubber seal on the edge where the halves meet (Blender +Y), origin
    in its middle."""
    opw, oph = (SHUTTLE["opw"], SHUTTLE["oph"]) if k == "sh" else (KIT[k]["opw"], KIT[k]["oph"])
    hw, hh, t = opw / 4 + 0.01, oph / 2, LEAF_T / 2
    body, trim, light = A.Builder(), A.Builder(), A.Builder()
    body.box_minmax((-t, -hw, -hh), (t, hw, hh), A.MAT_PANEL)
    bars(trim, -t - 0.004, t + 0.004, -hw, hw, -hh, hh, 0.045, A.MAT_TRIM)
    trim.box_minmax((-t - 0.003, -hw + 0.045, -hh + 0.30), (t + 0.003, hw - 0.045, -hh + 0.325), A.MAT_TRIM)               # a kick panel's edge and a belt rail
    trim.box_minmax((-t - 0.003, -hw + 0.045, 0.08), (t + 0.003, hw - 0.045, 0.105), A.MAT_TRIM)
    trim.box_minmax((-t, hw - 0.012, -hh), (t, hw, hh), A.MAT_RUBBER)                                                        # the seal on the meeting edge
    for x0, x1 in ((-t - 0.006, -t), (t, t + 0.006)):
        light.box_minmax((x0, hw - 0.075, -hh + 0.2), (x1, hw - 0.062, hh - 0.2), A.MAT_LIGHT)                                # and the light slit beside it
    return part([(body, 0.004), (trim, 0.002), (light, 0.0)], name)


def shuttle_layout():
    """The shuttle's walls along Y: the back wall's windows and the screen's panel, the front wall's pillars between the doors (all (y0, y1))."""
    S = SHUTTLE
    yi = S["length"] / 2 - WALL
    posts = [-6.2, -4.9, -3.6, -1.2, 1.2, 3.6, 4.9, 6.2]
    back = list(zip([-yi] + posts, posts + [yi]))
    windows = [s for s in back if s[1] - s[0] >= 0.3 and abs((s[0] + s[1]) / 2) >= 1.3]
    panel = [s for s in back if s not in windows]
    ops, opw = S["doors"], S["opw"]
    piers = [(-yi, ops[0] - opw / 2)] + [(ops[i] + opw / 2, ops[i + 1] - opw / 2) for i in range(len(ops) - 1)] + [(ops[-1] + opw / 2, yi)]
    return yi, windows, panel, piers


def car_shuttle(name: str) -> bpy.types.Object:
    """The Spine shuttle's car: 14 m along Y, 2.8 m deep, doors on the +X side, panoramic windows on the other, a screen at the middle of the back wall, poles."""
    S = SHUTTLE
    L2, H = S["length"] / 2, S["h"]
    xi = (S["d"] - 2 * WALL) / 2
    xo = xi + WALL
    yi, windows, panel, piers = shuttle_layout()
    ops, opw, oph = S["doors"], S["opw"], S["oph"]
    shell, trim, light, fit = A.Builder(), A.Builder(), A.Builder(), A.Builder()
    # floor, ceiling and the light channel along it
    shell.box_minmax((-xo, -L2, -FLOOR_T), (xo, L2, -0.04), A.MAT_STRUCTURE)
    shell.box_minmax((-xi, -yi, -0.04), (xi, yi, 0.0), A.MAT_FLOOR)
    for s in (-1, 1):
        light.box_minmax((s * (xi - 0.06) - 0.0075, -yi + 0.05, 0.0), (s * (xi - 0.06) + 0.0075, yi - 0.05, 0.006), A.MAT_GUIDE)
    shell.box_minmax((-xo, -L2, H), (xo, L2, H + CEIL_T), A.MAT_STRUCTURE)
    shell.box_minmax((-xi, -yi, H - 0.05), (xi, yi, H), A.MAT_PANEL)
    light.box_minmax((-0.5, -yi + 0.4, H - 0.062), (0.5, yi - 0.4, H - 0.05), A.MAT_LIGHT)
    for i in range(7):
        y = -yi + 0.05 + i * (2 * yi - 0.1) / 6
        trim.box_minmax((-xi, y - 0.03, H - 0.075), (xi, y + 0.03, H - 0.05), A.MAT_TRIM)
    # the end walls
    for s in (-1, 1):
        shell.box_minmax((-xo, s * yi if s > 0 else -L2, 0.0), (xo, L2 if s > 0 else -yi, H + CEIL_T), A.MAT_PANEL)
    # the back wall (-X): windows between posts, the middle panel carries the screen
    wz0, wz1 = 0.75, H - 0.45
    for (y0, y1) in windows:
        shell.box_minmax((-xo, y0, 0.0), (-xi, y1, wz0), A.MAT_PANEL)
        shell.box_minmax((-xo, y0, wz1), (-xi, y1, H), A.MAT_PANEL)
        bars(trim, -xi - 0.01, -xi + 0.03, y0 + 0.02, y1 - 0.02, wz0 - 0.03, wz1 + 0.03, 0.04, A.MAT_TRIM)
    for (y0, y1) in panel:
        shell.box_minmax((-xo, y0, 0.0), (-xi, y1, H), A.MAT_PANEL)
    # the front wall (+X): the piers between the three doors with a window each, the headers, the frames, the light over each door
    for (y0, y1) in piers:
        shell.box_minmax((xi, y0, 0.0), (xo, y1, 0.78), A.MAT_PANEL)
        shell.box_minmax((xi, y0, 0.78 + 0.9), (xo, y1, H + CEIL_T), A.MAT_PANEL)
        bars(trim, xi - 0.01, xi + 0.03, y0 + 0.08, y1 - 0.08, 0.78 - 0.03, 0.78 + 0.9 + 0.03, 0.04, A.MAT_TRIM)
    for y in ops:
        shell.box_minmax((xi, y - opw / 2, oph), (xo, y + opw / 2, H + CEIL_T), A.MAT_PANEL)
        bars(trim, xi - 0.01, xo, y - opw / 2, y + opw / 2, 0.0, oph, 0.04, A.MAT_TRIM)
        light.box_minmax((xi - 0.006, y - opw / 2 + 0.06, oph + 0.04), (xi + 0.002, y + opw / 2 - 0.06, oph + 0.065), A.MAT_LIGHT)
    # skirting and an accent band on both long walls, a rail and poles
    for x0, x1 in ((-xi, -xi + 0.03), (xi - 0.03, xi)):
        fit.box_minmax((x0, -yi, 0.0), (x1, yi, 0.11), A.MAT_STRUCTURE)
    for x0, x1 in ((-xi, -xi + 0.012), (xi - 0.012, xi)):
        light.box_minmax((x0, -yi, 0.68), (x1, yi, 0.72), A.MAT_ACCENT)
    trim.cylinder((-xi + 0.08, -yi + 0.2, 0.95), (-xi + 0.08, yi - 0.2, 0.95), 0.02, A.MAT_TRIM, segments=10)
    for (y0, y1) in windows:
        trim.cylinder((-xi + 0.005, (y0 + y1) / 2, 0.95), (-xi + 0.08, (y0 + y1) / 2, 0.95), 0.012, A.MAT_TRIM, segments=8)
    for y in (-5.5, -2.0, 2.0, 5.5):
        trim.cylinder((0.0, y, 0.0), (0.0, y, H - 0.05), 0.025, A.MAT_TRIM, segments=12)
    # the screen's bezel at the middle of the back wall (the quad is 1.4 x 0.88 m, 4 cm off the wall at 1.65 m)
    sz, sw_, sh_ = 1.65, 1.40, 0.88
    for (y0, y1, z0, z1) in ((-sw_ / 2 - 0.05, sw_ / 2 + 0.05, sz + sh_ / 2, sz + sh_ / 2 + 0.05), (-sw_ / 2 - 0.05, sw_ / 2 + 0.05, sz - sh_ / 2 - 0.05, sz - sh_ / 2),
                             (-sw_ / 2 - 0.05, -sw_ / 2, sz - sh_ / 2, sz + sh_ / 2), (sw_ / 2, sw_ / 2 + 0.05, sz - sh_ / 2, sz + sh_ / 2)):
        fit.box_minmax((-xi, y0, z0), (-xi + 0.06, y1, z1), A.MAT_TRIM)
    fit.box_minmax((-xi, -sw_ / 2, sz - sh_ / 2), (-xi + 0.037, sw_ / 2, sz + sh_ / 2), A.MAT_STRUCTURE)
    return part([(shell, 0.006), (trim, 0.003), (light, 0.002), (fit, 0.002)], name)


def shuttle_glass(name: str) -> bpy.types.Object:
    S = SHUTTLE
    xi = (S["d"] - 2 * WALL) / 2
    yi, windows, _, piers = shuttle_layout()
    b = A.Builder()
    for (y0, y1) in windows:
        b.box_minmax((-xi - 0.07, y0 + 0.03, 0.75), (-xi - 0.05, y1 - 0.03, S["h"] - 0.45), A.MAT_GLASS)
    for (y0, y1) in piers:
        b.box_minmax((xi + 0.06, y0 + 0.09, 0.78), (xi + 0.08, y1 - 0.09, 0.78 + 0.9), A.MAT_GLASS)
    return finish(b, name, 0.0)


# ---------------------------------------------------------------------------------------------------------------------------------- the landing
def landing(k: str, name: str) -> bpy.types.Object:
    """A landing's frame: origin in the middle of the opening at floor level, +X into the lobby. The leaves run at X 0.5..6.5 cm behind a fascia at 6.6..7.4 cm."""
    c = KIT[k]
    opw, oph = c["opw"], c["oph"]
    pier, head = 0.58, 0.34                      # the fascia beside the opening (the leaves slide behind it) and over it
    fa, tr, li = A.Builder(), A.Builder(), A.Builder()
    xf0, xf1 = 0.066, 0.074
    # the fascia: two piers and the head
    fa.box_minmax((xf0, opw / 2, 0.0), (xf1, opw / 2 + pier, oph + head), A.MAT_PANEL)
    fa.box_minmax((xf0, -opw / 2 - pier, 0.0), (xf1, -opw / 2, oph + head), A.MAT_PANEL)
    fa.box_minmax((xf0, -opw / 2, oph), (xf1, opw / 2, oph + head), A.MAT_PANEL)
    # the reveal: the opening's jambs and head, from the shaft's plane to the fascia; the raised bezel round the opening
    for (y0, y1) in ((opw / 2, opw / 2 + 0.05), (-opw / 2 - 0.05, -opw / 2)):
        tr.box_minmax((0.0, y0, 0.0), (xf0, y1, oph + 0.05), A.MAT_TRIM)
    tr.box_minmax((0.0, -opw / 2, oph), (xf0, opw / 2, oph + 0.05), A.MAT_TRIM)
    for (y0, y1) in ((opw / 2, opw / 2 + 0.07), (-opw / 2 - 0.07, -opw / 2)):
        tr.box_minmax((xf1, y0, 0.0), (xf1 + 0.014, y1, oph + 0.07), A.MAT_TRIM)
    tr.box_minmax((xf1, -opw / 2, oph), (xf1 + 0.014, opw / 2, oph + 0.07), A.MAT_TRIM)
    for (y0, y1) in ((opw / 2 + 0.07, opw / 2 + pier), (-opw / 2 - pier, -opw / 2 - 0.07)):
        tr.box_minmax((xf1, y0, 0.0), (xf1 + 0.012, y1, 0.10), A.MAT_STRUCTURE)               # the skirting
    # light on the jambs and over the door
    for s in (-1, 1):
        li.box_minmax((xf1 - 0.002, s * (opw / 2 + 0.085) - 0.007, 0.15), (xf1 + 0.008, s * (opw / 2 + 0.085) + 0.007, oph - 0.1), A.MAT_LIGHT)
    li.box_minmax((xf1 - 0.002, -opw / 2 + 0.1, oph + 0.085), (xf1 + 0.008, opw / 2 - 0.1, oph + 0.099), A.MAT_LIGHT)
    # the deck sign's plate over the door (the game puts the text on it), its frame, and the arrows at its ends
    sw_, sh_ = 0.62, 0.15
    zc = oph + head - 0.13
    fa.box_minmax((xf1, -sw_ / 2 - 0.02, zc - sh_ / 2 - 0.02), (xf1 + 0.006, sw_ / 2 + 0.02, zc + sh_ / 2 + 0.02), A.MAT_STRUCTURE)
    tr.box_minmax((xf1 + 0.006, -sw_ / 2 - 0.02, zc + sh_ / 2), (xf1 + 0.012, sw_ / 2 + 0.02, zc + sh_ / 2 + 0.02), A.MAT_TRIM)
    tr.box_minmax((xf1 + 0.006, -sw_ / 2 - 0.02, zc - sh_ / 2 - 0.02), (xf1 + 0.012, sw_ / 2 + 0.02, zc - sh_ / 2), A.MAT_TRIM)
    triangle(li, -(sw_ / 2 + 0.17), zc, True, xf1, xf1 + 0.006, A.MAT_LIGHT)
    triangle(li, sw_ / 2 + 0.17, zc, False, xf1, xf1 + 0.006, A.MAT_LIGHT)
    # the call panel on the left pier (Blender +Y): a plate in a frame, the lamp's socket, two buttons, the arrows' strip
    py, pz = opw / 2 + 0.45, 1.10
    fa.box_minmax((xf1, py - 0.09, pz - 0.19), (xf1 + 0.004, py + 0.09, pz + 0.19), A.MAT_STRUCTURE)
    bars(tr, xf1 + 0.004, xf1 + 0.011, py - 0.095, py + 0.095, pz - 0.205, pz + 0.205, 0.015, A.MAT_TRIM)
    tr.cylinder((xf1 + 0.004, py, pz + 0.06), (xf1 + 0.009, py, pz + 0.06), 0.034, A.MAT_RUBBER, segments=16)        # the lamp's socket (the lamp sits in it)
    for dz in (-0.06, -0.13):
        tr.cylinder((xf1 + 0.004, py, pz + dz), (xf1 + 0.016, py, pz + dz), 0.02, A.MAT_TRIM, segments=14)
    li.box_minmax((xf1 + 0.004, py - 0.06, pz + 0.135), (xf1 + 0.008, py + 0.06, pz + 0.145), A.MAT_ACCENT)
    # the sill: a threshold of brushed metal across the opening, flush with the floor
    tr.box_minmax((-0.045, -opw / 2 - 0.05, -0.012), (0.10, opw / 2 + 0.05, 0.0), A.MAT_TRIM)
    return part([(fa, 0.002), (tr, 0.002), (li, 0.0)], name)


# ---------------------------------------------------------------------------------------------------------------------------------- the shaft
def shaft_segment(k: str, name: str, door: bool) -> bpy.types.Object:
    """A shaft's lining. Origin: the shaft's middle at the bottom of the segment; +X the side of the doors. A door segment is 3.2 m: its floor level is 0.4 m up."""
    c = KIT[k]
    hw, hd, cd = c["sw"] / 2, c["sd"] / 2, c["d"]
    xc = hd - SILL_GAP - cd / 2                  # the car's middle
    H = DOORSEG_H if door else SEG_H
    zf = DOORSEG_DOWN
    t = 0.04
    wall, trim, ring = A.Builder(), A.Builder(), A.Builder()
    # the walls of the lining (the inside faces of the shaft): the back, the two sides, the front (with the landing's opening in a door segment)
    wall.box_minmax((-hd, -hw, 0.0), (-hd + t, hw, H), A.MAT_STRUCTURE)
    wall.box_minmax((-hd, hw - t, 0.0), (hd, hw, H), A.MAT_STRUCTURE)
    wall.box_minmax((-hd, -hw, 0.0), (hd, -hw + t, H), A.MAT_STRUCTURE)
    if not door:
        wall.box_minmax((hd - t, -hw, 0.0), (hd, hw, H), A.MAT_STRUCTURE)
    else:
        opw, oph = c["opw"] + 0.06, c["oph"] + 0.05
        for (y0, y1, z0, z1) in ((-hw, -opw / 2, 0.0, H), (opw / 2, hw, 0.0, H), (-opw / 2, opw / 2, 0.0, zf), (-opw / 2, opw / 2, zf + oph, H)):
            wall.box_minmax((hd - t, y0, z0), (hd, y1, z1), A.MAT_STRUCTURE)
    # the beams: a horizontal frame standing off the back and the side walls
    for z in ([0.0, 2.0] if not door else [0.0, 1.6]):
        trim.box_minmax((-hd + t, -hw + t, z + 0.02), (-hd + t + 0.04, hw - t, z + 0.09), A.MAT_TRIM)
        trim.box_minmax((-hd + t, hw - t - 0.04, z + 0.02), (hd - t, hw - t, z + 0.09), A.MAT_TRIM)
        trim.box_minmax((-hd + t, -hw + t, z + 0.02), (hd - t, -hw + t + 0.04, z + 0.09), A.MAT_TRIM)
    # the guide rails: a T section the whole height either side of the car, on brackets from the side walls
    for s in (-1, 1):
        y = s * (c["w"] / 2 + 0.06)
        trim.box_minmax((xc - 0.05, y - 0.012, 0.0), (xc + 0.05, y + 0.012, H), A.MAT_TRIM)
        trim.box_minmax((xc - 0.012, min(y, y - s * 0.05), 0.0), (xc + 0.012, max(y, y - s * 0.05), H), A.MAT_TRIM)
        for z in ([0.5, 1.5, 2.5, 3.5] if not door else [0.4, 1.4, 2.4]):
            trim.box_minmax((xc - 0.06, min(y, s * (hw - t)), z), (xc + 0.06, max(y, s * (hw - t)), z + 0.04), A.MAT_STRUCTURE)
    # the counterweight's cables and rails behind the car (what the car's window shows)
    for y in (-0.30, 0.30):
        trim.cylinder((-hd + 0.16, y, 0.0), (-hd + 0.16, y, H), 0.012, A.MAT_RUBBER, segments=8)
    for y in (-0.62, 0.62):
        trim.box_minmax((-hd + t, y - 0.03, 0.0), (-hd + t + 0.07, y + 0.03, H), A.MAT_TRIM)
    # the light: strips across the back wall every metre (the eye reads the speed from them) and, at a landing, a ring round the walls and a frame of light round the opening
    for z in ([0.5, 1.5, 2.5, 3.5] if not door else [1.2, 2.2, 3.0]):
        ring.box_minmax((-hd + t, -0.95, z), (-hd + t + 0.008, 0.95, z + 0.018), MAT_LIFT_RING)
    if door:
        zr = zf + 0.03
        ring.box_minmax((-hd + t, -hw + t, zr), (-hd + t + 0.012, hw - t, zr + 0.05), MAT_LIFT_RING)
        for s in (-1, 1):
            y0, y1 = (hw - t - 0.012, hw - t) if s > 0 else (-hw + t, -hw + t + 0.012)
            ring.box_minmax((-hd + t, y0, zr), (hd - 0.5, y1, zr + 0.05), MAT_LIFT_RING)
        bars(trim, hd - t - 0.03, hd, -opw / 2, opw / 2, zf, zf + oph, 0.03, A.MAT_TRIM)
        ring.box_minmax((hd - t - 0.005, -opw / 2 + 0.03, zf + oph + 0.01), (hd - t, opw / 2 - 0.03, zf + oph + 0.024), MAT_LIFT_RING)
    return part([(wall, 0.0), (trim, 0.0), (ring, 0.0)], name)


# ---------------------------------------------------------------------------------------------------------------------------------- the small ones
def call_lamp(name: str) -> bpy.types.Object:
    """The lens of the call lamp: a disc 5.2 cm across and 1.8 cm deep (its origin 0.6 cm in from its back), +X out."""
    b = A.Builder()
    b.cylinder((-0.006, 0.0, 0.0), (0.012, 0.0, 0.0), 0.026, MAT_LIFT_LAMP, segments=20)
    return finish(b, name, 0.002)


def call_post(name: str) -> bpy.types.Object:
    """The shuttle platform's call post: a slim blade 16 cm wide and 7 cm deep, 1.3 m tall, with a panel and a socket for the lamp at 1.16 m. Origin: its base, 5 cm behind the front."""
    b, tr, li = A.Builder(), A.Builder(), A.Builder()
    b.box_minmax((-0.05, -0.07, 0.0), (0.02, 0.07, 1.30), A.MAT_STRUCTURE)
    tr.box_minmax((-0.06, -0.08, 0.0), (0.03, 0.08, 0.06), A.MAT_TRIM)
    tr.box_minmax((-0.055, -0.075, 1.30), (0.025, 0.075, 1.34), A.MAT_TRIM)
    tr.cylinder((0.02, 0.0, 1.16), (0.026, 0.0, 1.16), 0.034, A.MAT_RUBBER, segments=16)
    for dz in (-0.06, -0.13):
        tr.cylinder((0.02, 0.0, 1.16 + dz), (0.03, 0.0, 1.16 + dz), 0.02, A.MAT_TRIM, segments=14)
    li.box_minmax((0.02, -0.05, 1.31), (0.024, 0.05, 1.318), A.MAT_ACCENT)
    li.box_minmax((0.02, -0.012, 0.15), (0.023, 0.012, 1.0), A.MAT_LIGHT)
    return part([(b, 0.003), (tr, 0.002), (li, 0.0)], name)


def screen_quad(name: str) -> bpy.types.Object:
    """The quad of the car's screen: 1 m square, in the YZ plane facing +X, u to the viewer's right (Blender +Y, looking at it from +X), v up, the slot MI_LIFT_SCREEN."""
    b = A.Builder()
    b.mi(MAT_LIFT_SCREEN)
    uv = b.bm.loops.layers.uv.verify()
    corners = [((0.0, -0.5, -0.5), (0.0, 0.0)), ((0.0, -0.5, 0.5), (0.0, 1.0)), ((0.0, 0.5, 0.5), (1.0, 1.0)), ((0.0, 0.5, -0.5), (1.0, 0.0))]
    f = b.bm.faces.new([b.bm.verts.new(p) for p, _ in corners])         # (the winding is checked below: the normal must be +X)
    f.material_index = 0
    for loop, (_, tc) in zip(f.loops, corners):
        loop[uv].uv = tc
    bmesh.ops.recalc_face_normals(b.bm, faces=[f])
    if f.normal.x < 0:
        f.normal_flip()
    return b.to_object(name)


# ---------------------------------------------------------------------------------------------------------------------------------- the build
def builders():
    out = []
    for k in KIT:
        out += [(f"SM_LIFT_Car_{k}", lambda n, k=k: car_turbolift(k, n)),
                (f"SM_LIFT_CarGlass_{k}", lambda n, k=k: car_glass(k, n)),
                (f"SM_LIFT_CarLeaf_{k}", lambda n, k=k: car_leaf(k, n)),
                (f"SM_LIFT_Landing_{k}", lambda n, k=k: landing(k, n)),
                (f"SM_LIFT_LandingLeaf_{k}", lambda n, k=k: car_leaf(k, n)),
                (f"SM_LIFT_Shaft_{k}", lambda n, k=k: shaft_segment(k, n, False)),
                (f"SM_LIFT_ShaftDoor_{k}", lambda n, k=k: shaft_segment(k, n, True))]
    out += [("SM_LIFT_Car_sh", car_shuttle), ("SM_LIFT_CarGlass_sh", shuttle_glass), ("SM_LIFT_CarLeaf_sh", lambda n: car_leaf("sh", n)),
            ("SM_LIFT_CallLamp", call_lamp), ("SM_LIFT_CallPost", call_post), ("SM_LIFT_Screen", screen_quad)]
    return out


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_dir = argv[0] if argv and not argv[0].startswith("--") else "art/export/ship_lift"
    only = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else set()
    preview = argv[argv.index("--preview") + 1] if "--preview" in argv else ""
    A.reset_scene()
    report = []
    for name, build in builders():
        if only and name not in only:
            continue
        A.clear_objects()
        obj = build(name)
        A.export_fbx(obj, os.path.join(out_dir, name + ".fbx"))
        report.append(A.stats(obj))
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump({"kit": KIT, "shuttle": SHUTTLE, "meshes": report}, fh, indent=1)
    print("LIFT_KIT_OK", json.dumps(report))
    if preview:
        import ship_lift_preview as P
        A.clear_objects()
        P.render_all(preview, builders())


if __name__ == "__main__":
    main()
