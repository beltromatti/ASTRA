"""ASN Aquila interior kit: the engineering rooms of the lower decks (NAVE-2) — the radiator manifold and the pump rooms, the machinery spaces (air and water
handling, compressors), the damage control locker, power control and the capacitor hall. Frames and sizes: ship_rooms.py / ship_spec.py."""
from __future__ import annotations

import math
import random

from mathutils import Vector

import ship_furniture as F
import ship_furniture2 as G
import ship_furniture3 as H
import ship_spec as SPEC
import ship_walls as W
from bridge3_lib import Rx, Ry, Rz, T, frame
from ship_lib import (BEDDING, COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DECK, DGLASS, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST,
                      FABRIC_SAND, GLASS, IVORY, LAMINATE, LAMP, LAMP_DIM, LAMP_HOT, LEAF, PAINT_RED, RUBBER, SOIL, STEEL, STRUCT, TILE, TRIM, WOOD,
                      SParts, lamp_strip)
from ship_rooms import (Style, WF, WS, build_shell, ceiling_panels, ceiling_services, dress_wall, luminaire_strips, place, wall_finish, wall_label,
                        wall_matrix)
from ship_rooms_hub import on_wall

ENG = Style  # (alias kept short in the builders below)


def _dims(key: str):
    s = SPEC.PREFABS[key]
    return s, s["L"], s["D"], s["h"]


def _style(accent: str = "engineering_dim", cove: str = "engineering_dim", floor: str = DECK) -> Style:
    return Style(floor=floor, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent=accent, cove=cove, rib_mat=TRIM,
                 skirt=STRUCT)


# ----------------------------------------------------------------------------------------------------------------------------- pieces
def valve_wheel(b: SParts, r: float = 0.22, mat: str = PAINT_RED) -> None:
    """A hand wheel on a stem, standing on +x (axis along x): a rim, four spokes, a hub."""
    b.fine.cyl((0, 0, 0), (0.12, 0, 0), 0.025, TRIM, seg=8)
    for k in range(24):
        a0, a1 = 2 * math.pi * k / 24, 2 * math.pi * (k + 1) / 24
        b.soft.box((0.1, r * math.cos(a0) - 0.02, r * math.sin(a0) - 0.02), (0.14, r * math.cos(a0) + 0.02, r * math.sin(a0) + 0.02), mat)
    for k in range(4):
        a = math.pi / 2 * k
        b.soft.box((0.115, min(0, r * math.cos(a)) - 0.012, min(0, r * math.sin(a)) - 0.012), (0.135, max(0, r * math.cos(a)) + 0.012, max(0, r * math.sin(a)) + 0.012), mat)


def flange(b: SParts, p, r: float, axis: str = "x") -> None:
    """A pipe flange: a thick disc ring with bolt heads round the rim."""
    p = Vector(p)
    d = {"x": Vector((0.06, 0, 0)), "y": Vector((0, 0.06, 0)), "z": Vector((0, 0, 0.06))}[axis]
    b.fine.cyl(p - d / 2, p + d / 2, r * 1.35, STEEL, seg=14)


def heat_exchanger(b: SParts, l: float = 3.6, r: float = 0.58, accent: str = "engineering") -> None:
    """A shell-and-tube heat exchanger, axis along y: a long cylinder on two saddles, domed end bonnets with flanges, nozzles up and down, a nameplate and a gauge."""
    z0 = 0.95
    b.body.cyl((0, -l / 2, z0), (0, l / 2, z0), r, STEEL, seg=20)
    for sy in (-l / 2 - 0.22, l / 2):
        b.body.cyl((0, sy + 0.0, z0), (0, sy + 0.22, z0), r * 1.1, COMPOSITE, seg=20, r2=r * 0.9)
    for sy in (-l * 0.3, l * 0.3):                                                                                # the saddles
        b.body.box((-r * 0.9, sy - 0.12, 0.0), (r * 0.9, sy + 0.12, z0 - r * 0.55), STRUCT)
        b.body.box((-r * 1.1, sy - 0.14, 0.0), (r * 1.1, sy + 0.14, 0.06), TRIM)
    for sy in (-l / 2 + 0.25, l / 2 - 0.25):                                                                      # nozzles, one up and one down, flanged
        b.body.cyl((0, sy, z0 + r), (0, sy, z0 + r + 0.45), 0.13, TRIM, seg=12)
        flange(b, (0, sy, z0 + r + 0.42), 0.13, "z")
    b.body.cyl((0, -l / 2 + 0.7, z0 - r), (0, -l / 2 + 0.7, 0.18), 0.09, TRIM, seg=10)
    for k in range(5):
        y = -l / 2 + 0.55 + k * (l - 1.1) / 4
        b.fine.cyl((0, y - 0.015, z0), (0, y + 0.015, z0), r * 1.02, STRUCT, seg=20)
    b.fine.box((r - 0.01, -0.3, z0 + 0.05), (r + 0.01, 0.3, z0 + 0.3), TRIM)
    b.emit.label((r + 0.012, 0.0, z0 + 0.17), 0.5, 0.125, (1, 0, 0), "tag_08")
    b.emit.lamp_box((r - 0.005, 0.32, z0 + 0.1), (r + 0.012, 0.4, z0 + 0.15), "green", LAMP)


def air_handler(b: SParts, w: float = 2.4, d: float = 1.2, h: float = 1.9) -> None:
    """An air-handling unit facing +x: a panelled steel box with a hinged service door, a round blower fan behind a grille, ducts to the ceiling."""
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, h), CRATE_GREY)
    b.body.box((-d / 2 - 0.02, -w / 2 - 0.02, 0.0), (d / 2 + 0.02, w / 2 + 0.02, 0.1), STRUCT)
    for k in range(3):
        y0 = -w / 2 + 0.06 + k * (w - 0.12) / 3
        b.fine.box((d / 2, y0 + 0.02, 0.2), (d / 2 + 0.03, y0 + (w - 0.12) / 3 - 0.02, h - 0.3), STEEL)
        b.fine.box((d / 2 + 0.03, y0 + (w - 0.12) / 3 - 0.14, h * 0.5 - 0.12), (d / 2 + 0.06, y0 + (w - 0.12) / 3 - 0.1, h * 0.5 + 0.12), TRIM)
    b.fine.cyl((d / 2, -w / 2 + 0.4, h - 0.2), (d / 2 + 0.04, -w / 2 + 0.4, h - 0.2), 0.12, STRUCT, seg=12)
    b.body.box((-0.3, -0.3, h), (0.3, 0.3, 3.3), STEEL)
    b.emit.label((d / 2 + 0.004, 0.0, h - 0.12), 0.8, 0.2, (1, 0, 0), "eq_air")
    b.emit.lamp_box((d / 2 + 0.03, w / 2 - 0.2, 0.3), (d / 2 + 0.036, w / 2 - 0.12, 0.34), "green", LAMP_DIM)


def horizontal_tank(b: SParts, l: float = 3.6, r: float = 0.7, mat: str = STEEL) -> None:
    """A horizontal pressure vessel (an air receiver) on two saddles, axis along y, domed ends, a gauge and a safety valve on top."""
    z0 = r + 0.3
    b.body.cyl((0, -l / 2, z0), (0, l / 2, z0), r, mat, seg=20)
    for sy, sg in ((-l / 2, -1), (l / 2, 1)):
        b.body.sphere((0, sy, z0), r, mat, seg=20, rings=8, squash=(1.0, 0.3, 1.0))
    for sy in (-l * 0.3, l * 0.3):
        b.body.box((-r * 0.8, sy - 0.1, 0.0), (r * 0.8, sy + 0.1, z0 - r * 0.6), STRUCT)
    b.body.cyl((0, -l * 0.15, z0 + r), (0, -l * 0.15, z0 + r + 0.3), 0.07, TRIM, seg=10)
    b.fine.cyl((0, l * 0.15, z0 + r), (0, l * 0.15, z0 + r + 0.2), 0.03, TRIM, seg=8)
    b.fine.cyl((0, l * 0.15, z0 + r + 0.2), (0, l * 0.15, z0 + r + 0.23), 0.07, DGLASS, seg=12)
    b.emit.label((r * 0.7, 0.0, z0 + 0.2), 0.6, 0.15, (1, 0, 0), "eq_gas")


def compressor(b: SParts, l: float = 2.2, accent: str = "engineering") -> None:
    """A two-stage air compressor on a skid, axis along y: a motor, a coupling, two cylinders in a V on a crankcase, an intercooler with fins and a gauge panel."""
    b.body.box((-0.55, -l / 2, 0.0), (0.55, l / 2, 0.12), STRUCT)
    b.body.cyl((0, -l / 2 + 0.3, 0.55), (0, -0.15, 0.55), 0.34, CRATE_BLUE, seg=18)
    for k in range(6):
        b.fine.cyl((0, -l / 2 + 0.35 + k * 0.1, 0.55), (0, -l / 2 + 0.37 + k * 0.1, 0.55), 0.36, TRIM, seg=18)
    b.body.cyl((0, -0.15, 0.55), (0, 0.05, 0.55), 0.07, STEEL, seg=10)
    b.body.box((-0.3, 0.05, 0.12), (0.3, 0.7, 0.8), CRATE_GREY)
    for sx in (-0.2, 0.2):
        b.body.cyl((sx, 0.38, 0.8), (sx * 1.5, 0.38, 1.3), 0.11, STEEL, seg=12)
        for k in range(4):
            b.fine.cyl((sx + (sx * 0.5) * (k / 3.0) * 0.8, 0.38, 0.9 + k * 0.1), (sx + (sx * 0.5) * (k / 3.0) * 0.8, 0.38, 0.92 + k * 0.1), 0.14, TRIM, seg=10)
    b.body.box((-0.35, 0.78, 0.2), (0.35, l / 2 - 0.1, 1.1), COMPOSITE)
    for k in range(9):
        b.fine.box((-0.33, 0.8 + k * 0.1, 0.22), (0.33, 0.83 + k * 0.1, 1.08), TRIM)
    b.fine.box((0.36, 0.0, 0.95), (0.4, 0.4, 1.25), TRIM)
    b.emit.lamp_box((0.4, 0.05, 1.1), (0.405, 0.35, 1.13), "amber", LAMP_DIM)
    b.emit.lamp_box((-0.55, -l / 2, 0.02), (0.55, -l / 2 + 0.01, 0.1), H.dim(accent), LAMP_DIM)


def hose_reel(b: SParts, r: float = 0.4, mat: str = PAINT_RED) -> None:
    """A fire hose reel on a wall (facing +x): a drum with coiled hose, a frame, a nozzle and a red bracket."""
    b.body.box((-0.04, -r - 0.08, 0.0), (0.0, r + 0.08, 2 * r + 0.16), TRIM)
    b.body.cyl((0.0, 0.0, r + 0.08), (0.2, 0.0, r + 0.08), r, mat, seg=20)
    b.fine.cyl((0.2, 0.0, r + 0.08), (0.22, 0.0, r + 0.08), r * 1.05, STEEL, seg=20)
    b.fine.cyl((0.0, 0.0, r + 0.08), (0.2, 0.0, r + 0.08), r * 0.78, RUBBER, seg=20)
    b.fine.cyl((0.22, 0.0, r + 0.08), (0.34, 0.0, r + 0.08), 0.06, STEEL, seg=10)
    b.emit.label((0.002, 0.0, 2 * r + 0.3), 0.5, 0.125, (1, 0, 0), "eq_hydrant")


def scba_rack(b: SParts, n: int = 6, w: float = 0.32) -> None:
    """A wall rack of breathing apparatus (facing +x): n harnesses with a cylinder, a mask on a hook and a pressure indicator each."""
    L = n * w
    b.body.box((-0.05, -L / 2 - 0.03, 0.5), (0.0, L / 2 + 0.03, 2.05), COMPOSITE)
    b.body.box((-0.03, -L / 2 - 0.03, 2.05), (0.2, L / 2 + 0.03, 2.1), TRIM)
    b.body.box((-0.03, -L / 2 - 0.03, 0.46), (0.2, L / 2 + 0.03, 0.5), TRIM)
    for k in range(n):
        y = -L / 2 + w / 2 + k * w
        b.body.cyl((0.1, y, 0.62), (0.1, y, 1.65), 0.095, CRATE_ORANGE if k % 3 == 0 else CRATE_GREY, seg=10)
        b.fine.cyl((0.1, y, 1.65), (0.1, y, 1.72), 0.03, TRIM, seg=6)
        b.soft.box((0.0, y - 0.1, 1.2), (0.05, y + 0.1, 1.5), FABRIC_GREY)
        b.soft.sphere((0.05, y, 1.82), 0.09, RUBBER, seg=8, rings=6, squash=(0.6, 1.0, 1.0))
        b.emit.lamp_box((0.0, y - 0.015, 1.98), (0.006, y + 0.015, 2.02), "green", LAMP_DIM)


def pipe_rack(b: SParts, x: float, y0: float, y1: float, z: float = 2.35, n: int = 4, seed: int = 1, handrail: bool = False) -> None:
    """A pipe rack across the room along y at x: posts every 4 m, a cross beam, n pipes of different bore in a bundle with clamps, hand wheels hanging off two of them."""
    rng = random.Random(seed)
    ys = [y0 + k * (y1 - y0) / max(1, int((y1 - y0) / 4.0)) for k in range(max(1, int((y1 - y0) / 4.0)) + 1)]
    for yy in ys:
        for dx in (-0.45, 0.45):
            b.body.box((x + dx - 0.05, yy - 0.05, 0.0), (x + dx + 0.05, yy + 0.05, z - 0.1), STRUCT)
        b.body.box((x - 0.55, yy - 0.06, z - 0.1), (x + 0.55, yy + 0.06, z - 0.02), TRIM)
    mats = [STEEL, CRATE_BLUE, TRIM, CRATE_ORANGE, STEEL]
    for k in range(n):
        xx = x - 0.4 + k * 0.8 / max(1, n - 1)
        r = rng.choice((0.05, 0.07, 0.09, 0.11))
        b.fine.cyl((xx, y0 - 0.2, z + r - 0.02), (xx, y1 + 0.2, z + r - 0.02), r, mats[k % len(mats)], seg=10)
    for yy in ys[1:-1] if len(ys) > 2 else ys:
        b.fine.box((x - 0.5, yy - 0.02, z - 0.02), (x + 0.5, yy + 0.02, z + 0.2), TRIM)
    for k, yy in enumerate((ys[0] + 1.2, ys[-1] - 1.2)):
        b.fine.cyl((x + 0.0, yy, z + 0.12), (x + 0.0, yy, z + 0.6), 0.02, TRIM, seg=6)
        place(b, x, yy, 0, valve_wheel_flat, 0.18)


def valve_wheel_flat(b: SParts, r: float = 0.18) -> None:
    """A hand wheel lying flat (axis up) on a stem, on top of a pipe rack."""
    z = 0.62
    for k in range(20):
        a0 = 2 * math.pi * k / 20
        b.soft.box((r * math.cos(a0) - 0.018, r * math.sin(a0) - 0.018, z), (r * math.cos(a0) + 0.018, r * math.sin(a0) + 0.018, z + 0.03), PAINT_RED)
    b.soft.box((-r, -0.012, z), (r, 0.012, z + 0.025), PAINT_RED)
    b.soft.box((-0.012, -r, z), (0.012, r, z + 0.025), PAINT_RED)


def skid(b: SParts, w: float = 1.6, d: float = 1.0, h: float = 1.0, kind: int = 0, seed: int = 1) -> None:
    """A small process skid on a steel base: a filter column, a drum or a manifold box with gauges and a lit status."""
    rng = random.Random(seed)
    b.body.box((-d / 2, -w / 2, 0.0), (d / 2, w / 2, 0.14), STRUCT)
    for sx in (-d / 2 + 0.05, d / 2 - 0.05):
        for sy in (-w / 2 + 0.05, w / 2 - 0.05):
            b.body.box((sx - 0.03, sy - 0.03, 0.14), (sx + 0.03, sy + 0.03, h), TRIM)
    if kind == 0:                                                                                              # a pair of filter columns
        for sy in (-w / 4, w / 4):
            b.body.cyl((0, sy, 0.14), (0, sy, h - 0.1), 0.2, CRATE_GREY, seg=14)
            b.body.sphere((0, sy, h - 0.1), 0.2, CRATE_GREY, seg=14, rings=6, squash=(1, 1, 0.5))
            b.fine.cyl((0.0, sy, 0.5), (0.0, sy, 0.54), 0.215, TRIM, seg=14)
    elif kind == 1:                                                                                            # a drum and a motor
        b.body.cyl((0, -w / 4, 0.14 + 0.3), (0, w / 4 + 0.2, 0.14 + 0.3), 0.3, CRATE_BLUE, seg=16)
        b.body.box((-0.2, w / 4 + 0.2, 0.14), (0.2, w / 2 - 0.05, 0.55), CRATE_GREY)
    else:                                                                                                      # a manifold box with valves
        b.body.box((-d / 2 + 0.1, -w / 2 + 0.1, 0.14), (d / 2 - 0.1, w / 2 - 0.1, 0.8), COMPOSITE)
        for k in range(4):
            y = -w / 2 + 0.3 + k * (w - 0.6) / 3
            b.fine.cyl((d / 2 - 0.1, y, 0.5), (d / 2 + 0.06, y, 0.5), 0.03, TRIM, seg=8)
            b.fine.cyl((d / 2 + 0.06, y, 0.5), (d / 2 + 0.08, y, 0.5), 0.06, DGLASS, seg=10)
    b.emit.lamp_box((d / 2 - 0.02, -w / 2 + 0.1, 0.18), (d / 2 + 0.005, -w / 2 + 0.2, 0.22), "green", LAMP_DIM)
    b.emit.label((d / 2 + 0.002, w / 2 - 0.3, h * 0.45), 0.4, 0.1, (1, 0, 0), "tag_%02d" % rng.randint(0, 12))


# ---------------------------------------------------------------------------------------------------------------------- radiator manifold
def radiator_pumps(name: str = "SM_SHIP_RadiatorPumps"):
    """24 x 16 x 3.7: two header pipes along the far wall at 2.6 m with four branches down to four pump sets in a row, two heat exchangers at the right end, a pump
    control cabinet and a valve stand by the door, coolant lines lit in the floor."""
    spec, L, D, H_ = _dims("radiator_pumps")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _style())
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    ypump = 11.4
    # the headers: a big supply and a smaller return pipe, flanged joints every 4 m, drops to every pump
    b.body.cyl((1.0, yf - 0.5, 2.65), (L - 1.0, yf - 0.5, 2.65), 0.24, STEEL, seg=18)
    b.body.cyl((1.0, yf - 1.05, 2.45), (L - 1.0, yf - 1.05, 2.45), 0.16, CRATE_BLUE, seg=16)
    for x in range(2, 24, 4):
        b.fine.cyl((x - 0.04, yf - 0.5, 2.65), (x + 0.04, yf - 0.5, 2.65), 0.32, STEEL, seg=16)
        b.fine.cyl((x - 0.04, yf - 1.05, 2.45), (x + 0.04, yf - 1.05, 2.45), 0.22, STEEL, seg=14)
        b.body.box((x - 0.05, yf - 1.3, 2.9), (x + 0.05, yf, 3.7), STRUCT)
    for k, x in enumerate((3.4, 7.8, 12.2, 16.6)):
        place(b, x, ypump, 0, H.pump_set, 1.6, "engineering")
        b.body.cyl((x + 0.18, ypump + 0.4, 1.12), (x + 0.18, yf - 1.05, 1.12), 0.075, TRIM, seg=10)
        b.body.cyl((x + 0.18, yf - 1.05, 1.12), (x + 0.18, yf - 1.05, 2.45), 0.075, TRIM, seg=10)
        b.body.cyl((x - 0.18, ypump + 0.4, 1.12), (x - 0.18, yf - 0.5, 1.12), 0.075, TRIM, seg=10)
        b.body.cyl((x - 0.18, yf - 0.5, 1.12), (x - 0.18, yf - 0.5, 2.65), 0.075, TRIM, seg=10)
        place(b, x - 0.05, ypump + 0.9, 0, valve_wheel, 0.2)
        lamp_strip(b.emit, (x, ypump - 1.0, 0.006), (x, 2.4, 0.006), 0.05, 0.004, "engineering", LAMP_DIM)
    for k, y in enumerate((5.0, 9.4)):
        place(b, 21.0, y, 90, heat_exchanger, 3.6, 0.58, "engineering")
        H.pipe_bundle(b, (21.0 - 0.0, y + 1.8, 2.0), (21.0, yf - 1.0, 2.0), 2, 0.07, 0.03, (1, 0, 0), None, 2.0)
    # a second row: skids and expansion tanks along the left, two pipe racks across the room
    for k, y in enumerate((4.0, 6.6, 9.2)):
        place(b, 2.6, y, 0, H.tank_v, 0.8, 3.0, STEEL, "engineering") if k == 0 else place(b, 2.6, y, 0, skid, 1.6, 1.0, 1.1, k % 3, k)
    for k, x in enumerate((6.2, 10.6, 15.0)):
        place(b, x, 5.6, 0, skid, 1.8, 1.1, 1.1, k % 3, 10 + k)
    pipe_rack(b, 13.0, 1.6, 8.8, 2.3, 4, 1)
    pipe_rack(b, 18.6, 1.6, 7.6, 2.3, 4, 2)
    # the control cabinet and the valve stand by the door
    place(b, 14.6, 1.4, 90, H.hv_cabinet, 0.9, 0.7, 2.2, 3)
    place(b, 6.4, 1.1, 90, F.desk, 1.4, 0.6, 0.85, STEEL, False)
    place(b, 6.4, 1.1, 90, F.monitor, 0.5, 0.3, "scr_wave", False, z=0.85)
    place(b, xl + 0.35, 6.0, 0, F.locker_row, 4, 0.45, 1.95, 0.5, COMPOSITE)
    on_wall(b, "left", L, D, W.extinguisher, b.body, 8.2, 0.0)
    dress_wall(b, "near", L, D, H_, 8.0, 12.0, 2, accent="engineering", accent_dim="engineering_dim", kinds=("plain", "vent", "panelboard"))
    dress_wall(b, "near", L, D, H_, 16.0, 23.5, 3, accent="engineering", accent_dim="engineering_dim", kinds=("conduits", "plain", "safety", "vent"))
    ceiling_services(b, L, D, H_, [(4.6, "pipes"), (8.4, "tray")], 1.0, 23.0, 5)
    ceiling_panels(b, L, D, H_, 4, 3, "white_warm", 1.6, 1.2, 0.6, LAMP_HOT)
    return b.build(name)


# -------------------------------------------------------------------------------------------------------------------------- machinery
def machinery(name: str = "SM_SHIP_Machinery"):
    """24 x 16 x 3.7: air handling and water recycling: three air handling units in a row along the far wall with their ducts to the ceiling, two vertical water tanks
    with a pump set between them, a control desk and a maintenance bench."""
    spec, L, D, H_ = _dims("machinery")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _style("engineering_dim", "white_warm"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for k, x in enumerate((3.4, 7.4, 11.4)):
        place(b, x, yf - 0.7, -90, air_handler, 2.6, 1.2, 1.9)
        b.body.box((x - 0.35, yf - 1.5, 3.0), (x + 0.35, yf - 0.5, 3.6), STEEL)
    b.body.box((2.8, yf - 1.6, 3.35), (12.0, yf - 0.9, 3.7), STEEL)
    for k, x in enumerate((17.0, 20.2)):
        place(b, x, 11.5, 0, H.tank_v, 0.95, 2.9, STEEL, "engineering")
    place(b, 18.6, 13.4, 0, H.pump_set, 1.6, "engineering")
    H.pipe_bundle(b, (17.0, 11.5, 0.5), (20.2, 11.5, 0.5), 2, 0.06, 0.03, (0, 1, 0), None, 2.0)
    place(b, 7.0, 7.0, 90, G.workbench, 3.0, 0.8, 0.95, True)
    for k, y in enumerate((6.0, 8.4, 10.8)):
        place(b, 20.4, y, 90 if k else 0, skid, 1.8, 1.1, 1.1, k, 20 + k) if k < 1 else place(b, 22.6, y - 2.0, 180, skid, 1.8, 1.1, 1.1, k, 20 + k)
    pipe_rack(b, 15.0, 1.6, 8.8, 2.3, 5, 3)
    pipe_rack(b, 10.0, 4.4, 8.8, 2.3, 3, 4)
    place(b, xl + 0.35, 10.0, 0, F.locker_row, 4, 0.45, 1.95, 0.5, COMPOSITE)
    place(b, 14.0, 2.0, 90, F.desk, 1.6, 0.7, 0.8, STEEL, False)
    place(b, 14.0, 2.0, 90, F.monitor, 0.5, 0.3, "scr_ship", False, z=0.8)
    place(b, 14.0, 1.0, -90, H.chair_op, FABRIC_RUST)
    dress_wall(b, "near", L, D, H_, 12.0, 23.5, 7, accent="engineering", accent_dim="engineering_dim", kinds=("plain", "vent", "panelboard", "safety"))
    ceiling_services(b, L, D, H_, [(4.0, "duct"), (8.6, "pipes")], 1.0, 23.0, 9)
    ceiling_panels(b, L, D, H_, 4, 3, "white_warm", 1.6, 1.2, 0.6, LAMP_HOT)
    return b.build(name)


def machinery_b(name: str = "SM_SHIP_MachineryB"):
    """24 x 16 x 3.7: compressed air: two compressors, a long air receiver on saddles, a dryer, a manifold of hand valves and a tool store."""
    spec, L, D, H_ = _dims("machinery_b")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _style("amber_dim", "white_warm"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for k, x in enumerate((4.0, 8.4)):
        place(b, x, 9.0, 0, compressor, 2.4, "engineering")
    for k, x in enumerate((14.0, 17.6)):
        place(b, x, 11.0, 0, horizontal_tank, 4.4, 0.72)
    b.body.cyl((3.6, yf - 0.6, 2.4), (L - 2.0, yf - 0.6, 2.4), 0.14, STEEL, seg=14)
    for k, x in enumerate((6.0, 10.0, 14.0, 17.6, 21.0)):
        b.body.cyl((x, yf - 0.6, 2.4), (x, yf - 0.6, 1.4), 0.06, TRIM, seg=8)
        place(b, x + 0.0, yf - 0.64, -90, valve_wheel, 0.18, PAINT_RED)
    b.body.box((20.4, 9.0, 0.0), (21.6, 12.0, 1.9), CRATE_GREY)
    b.fine.box((21.6, 9.2, 0.4), (21.65, 11.8, 1.6), STEEL)
    b.emit.label((21.66, 10.5, 1.75), 1.0, 0.25, (1, 0, 0), "eq_air")
    for k, x in enumerate((5.0, 9.4)):
        place(b, x, 4.2, 0, skid, 1.8, 1.1, 1.1, 1 + (k % 2), 30 + k)
    pipe_rack(b, 12.0, 1.6, 8.0, 2.3, 4, 5)
    pipe_rack(b, 22.2, 1.6, 9.0, 2.3, 3, 6)
    place(b, 12.0, 2.0, 90, F.desk, 1.6, 0.7, 0.8, STEEL, False)
    place(b, 12.0, 2.0, 90, F.monitor, 0.5, 0.3, "scr_data", False, z=0.8)
    place(b, xl + 0.3, 6.0, 0, F.locker_row, 3, 0.45, 1.95, 0.5, COMPOSITE)
    place(b, 6.0, 4.0, 90, G.tool_wall, 3.0, 1.4, 4)
    dress_wall(b, "near", L, D, H_, 14.0, 23.5, 8, accent="amber", accent_dim="amber_dim", kinds=("plain", "conduits", "vent", "safety"))
    ceiling_services(b, L, D, H_, [(3.2, "tray"), (6.4, "duct")], 1.0, 23.0, 11)
    ceiling_panels(b, L, D, H_, 4, 3, "white_warm", 1.6, 1.2, 0.6, LAMP_HOT)
    return b.build(name)


# ------------------------------------------------------------------------------------------------------------------ damage control locker
def dc_locker(name: str = "SM_SHIP_DcLocker"):
    """12 x 16 x 3.4: a wall of red-doored lockers with hose reels, a rack of breathing apparatus, a workbench with hull-patch plates and shoring props, a status board."""
    spec, L, D, H_ = _dims("dc_locker")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _style("red_dim", "white_warm"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for k in range(4):                                                                                              # lockers along the far wall, red doors
        place(b, 1.4 + k * 2.4, yf - 0.3, -90, F.locker_row, 4, 0.5, 2.1, 0.55, PAINT_RED)
    place(b, xl + 0.02, 7.0, 0, hose_reel, 0.4, PAINT_RED)
    place(b, xl + 0.02, 9.2, 0, hose_reel, 0.4, PAINT_RED)
    place(b, xr - 0.02, 8.0, 180, scba_rack, 6, 0.32)
    place(b, xr - 0.02, 12.0, 180, H.wall_rack_panel, 3.0, 2.0, "scr_ship", "red")
    place(b, 6.0, 7.5, 90, G.workbench, 3.0, 0.8, 0.95, True)
    # shoring props against the wall and hull patch plates leaning on it
    for k, x in enumerate((9.0, 9.5, 10.0, 10.5)):
        b.body.cyl((x, 3.0, 0.0), (x, 3.0, 2.3), 0.05, CRATE_ORANGE, seg=8)
        b.fine.cyl((x, 3.0, 2.3), (x, 3.0, 2.38), 0.08, STEEL, seg=8)
    for k in range(3):
        b.body.box((2.0 + k * 0.5, 3.0, 0.0), (2.08 + k * 0.5, 3.8, 1.2 + k * 0.1), STEEL)
        b.fine.box((2.0 + k * 0.5, 3.0, 0.5), (2.09 + k * 0.5, 3.8, 0.56), PAINT_RED)
    place(b, 9.6, 5.4, 90, F.crate, 0.9, 0.6, 0.5, CRATE_ORANGE, "eq_dc", False)
    place(b, 9.6, 5.4, 90, F.crate, 0.8, 0.55, 0.4, CRATE_GREY, None, False, z=0.5)
    on_wall(b, "left", L, D, W.extinguisher, b.body, 3.0, 0.0)
    on_wall(b, "left", L, D, W.first_aid, b.body, 4.0, 1.4)
    b.emit.label((6.0, WF + 0.02, 2.7), 1.6, 0.4, (0, 1, 0), "eq_dc")
    b.emit.label((3.0, 6.0, 0.006), 4.0, 0.2, (0, 0, 1), "hazard_h", up=(0, 1, 0))
    ceiling_services(b, L, D, H_, [(5.0, "pipes")], 1.0, 11.0, 2)
    ceiling_panels(b, L, D, H_, 2, 3, "white_warm", 1.4, 1.0, 0.5, LAMP_HOT)
    return b.build(name)


# ------------------------------------------------------------------------------------------------------------------------ power control
def power_control(name: str = "SM_SHIP_PowerControl"):
    """24 x 16 x 3.6: a wall-length mimic of the ship's power distribution with two rows of operator consoles facing it, rows of switchgear and battery racks
    behind, the main bus riser (a thick column with lit rings) standing in the middle."""
    spec, L, D, H_ = _dims("power_control")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _style("engineering_dim", "engineering_dim"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for x, tile in ((4.4, "scr_ship"), (10.8, "scr_data"), (17.2, "scr_wave"), (22.2, "scr_map")):
        place(b, x, yf - 0.02, -90, H.wall_rack_panel, 5.8 if x < 20 else 3.0, 2.8, tile, "amber")
    b.emit.lamp_box((1.0, yf - 0.1, 3.2), (L - 1.0, yf - 0.06, 3.25), "engineering_dim", LAMP_DIM)
    for row, y in enumerate((8.6, 5.6)):
        for k, x in enumerate((3.6, 8.0, 12.4)):
            place(b, x, y, -90, H.work_console, 3.2, "engineering", 2 if row == 0 else 1, ["scr_data", "scr_wave", "scr_ship"][k:] + ["scr_map"], True, row == 0)
            place(b, x, y - 1.25, 90, H.chair_op, FABRIC_RUST)
    with b.at(T(18.5, 8.4, 0.0)):                                                                                      # the bus riser
        b.body.cyl((0, 0, 0.0), (0, 0, H_), 0.62, STRUCT, seg=20)
        for z in (0.5, 1.2, 1.9, 2.6, 3.2):
            H.ring(b.body, 0.0, 0.0, z, 0.60, 0.07, 0.10, TRIM, 20)
            H.lamp_ring(b.emit, 0.0, 0.0, z + 0.035, 0.67, 0.03, 0.03, "amber", LAMP_DIM, 20)
        for k in range(6):
            a = math.radians(60 * k)
            b.emit.lamp_box((0.6 * math.cos(a) - 0.015, 0.6 * math.sin(a) - 0.015, 0.4), (0.6 * math.cos(a) + 0.015, 0.6 * math.sin(a) + 0.015, H_ - 0.4), "engineering", LAMP_DIM)
    place(b, xr - 0.4, 3.0, 180, H.hv_cabinet, 0.9, 0.7, 2.2, 3)
    place(b, xr - 0.4, 6.5, 180, H.battery_rack, 1.4, 0.8, 2.0)
    place(b, xr - 0.4, 8.2, 180, H.battery_rack, 1.4, 0.8, 2.0)
    place(b, xl + 0.4, 3.0, 0, H.hv_cabinet, 0.9, 0.7, 2.2, 3)
    place(b, xl + 0.45, 7.0, 0, H.rack_row, 5, 0.62, 0.95, 2.2, "amber", 5)
    dress_wall(b, "near", L, D, H_, 12.0, 23.5, 9, accent="engineering", accent_dim="engineering_dim", kinds=("panelboard", "conduits", "plain", "safety"))
    ceiling_services(b, L, D, H_, [(3.2, "tray"), (12.5, "tray"), (14.4, "pipes")], 1.0, 23.0, 3)
    ceiling_panels(b, L, D, H_, 4, 3, "white_warm", 1.6, 1.0, 0.5, LAMP_HOT)
    return b.build(name)
