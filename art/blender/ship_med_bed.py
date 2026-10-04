"""ASN Aquila — a bed of the Medbay's ward and its headwall, rebuilt in the kit's language (ARTE-INTERNI-2). SM_MED_Bed of art/blender/medbay.py: the same frame (the origin on the floor under the backrest's
hinge, +X towards the head of the bed, the wall at +1.4 m, placed twelve times by tools/ue_scripts/build_medbay.py), the same mattress (the leg section flat at 0.64 m, the back section raised 20 degrees along
its hinge: AstraPatient lies a patient on it, SM_MED_Blanket is shaped over the body that lies there) and the same monitor (the standby face at the rectangle that SM_MED_Vitals covers with the live traces:
AstraPatient swaps the material of the vitals face, never of this one).

  bed        chassis on four braked castors with two lifting columns, a steel platform in two sections, a mattress and a pillow, white head and foot boards with a teal inlay and a chart holder, side rails on the
             leg section, a drip stand with its bag at the head; on the wall behind: the bed-head unit (a services rail with its outlets in their gas colours, a nurse-call button, a reading lamp, a bed plate) and
             the patient monitor on its arm

Built in layout coordinates (X forward, Y starboard, Z up; the builder mirrors Y on the way out, as the first generation's U() did).
  blender -b --factory-startup --python-exit-code 1 -P art/blender/ship_med_bed.py
"""
from __future__ import annotations

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import ship_lib as SL  # noqa: E402
import ship_mk as MK  # noqa: E402
from bridge3_lib import Rz, Ry, T  # noqa: E402
from ship_lib import (BEDDING, LAMP_DIM, PAPER, PLASTER_TEAL, RUBBER, STEEL, STRUCT, SWATCH, TRIM, WHITE_GLOSS, SParts)  # noqa: E402

D = json.load(open(os.path.join(SL.ROOT, "data", "ship", "aquila_medbay.json"), encoding="utf-8"))
BEDS = D["beds"]
MAT_TOP = BEDS["mattress_top"]                      # 0.64: the leg section's top and the backrest's hinge
RECLINE = BEDS["recline_deg"]                       # the back section, degrees
HEAD, FOOT, HW = 0.95, -1.25, 0.5
BACK = 0.92                                         # the back section's length along its slope
WALL = 1.4                                          # the ward's wall, from the hinge
# the monitor over each bed: the standby face at the rectangle SM_MED_Vitals covers (medbay.py: MON_C is its lower corner, MON_YAW the way it faces, its width runs to the bed's left)
MON_C = (1.08, 0.6, 1.74)
MON_YAW = -168.0
MON_W, MON_H = 0.52, 0.325
STANDBY = "MI_MED_ScreenStandby"


def bed(name: str = "SM_MED_Bed"):
    SL.load_labels()
    b = SParts(bevel=0.005, fine_bevel=0.0)
    chassis(b)
    sleeping_surface(b)
    boards_and_rails(b)
    drip_stand(b, 0.78, -0.66)
    headwall(b)
    return b.build(name, uv_meter=0.7)


def chassis(b: SParts) -> None:
    """Four braked castors, a base under a white shroud, two lifting columns, the platform (the leg section flat, the back section raised along the backrest's hinge)."""
    for (cx, cy) in ((-0.95, -0.3), (-0.95, 0.3), (0.68, -0.3), (0.68, 0.3)):
        b.soft.cyl((cx, cy, 0.0), (cx, cy, 0.1), 0.05, RUBBER, seg=10)
        b.soft.cyl((cx, cy, 0.1), (cx, cy, 0.14), 0.022, STEEL, seg=8)
    b.body.box((-1.05, -0.36, 0.12), (0.78, 0.36, 0.2), STRUCT)
    MK.rbox(b.soft, (-1.0, -0.33, 0.2), (0.74, 0.33, 0.3), 0.025, WHITE_GLOSS, 1)
    for x in (-0.55, 0.38):
        b.body.box((x - 0.11, -0.16, 0.3), (x + 0.11, 0.16, 0.38), WHITE_GLOSS)
        b.body.box((x - 0.08, -0.12, 0.38), (x + 0.08, 0.12, 0.46), STEEL)
    b.body.box((FOOT + 0.03, -HW, 0.44), (0.0, HW, 0.48), STEEL)
    b.body.box((FOOT + 0.03, -HW + 0.04, 0.41), (0.0, -HW + 0.06, 0.44), TRIM)
    b.body.box((FOOT + 0.03, HW - 0.06, 0.41), (0.0, HW - 0.04, 0.44), TRIM)
    with b.at(T(0.0, 0.0, 0.48) @ Ry(-RECLINE)):
        b.body.box((0.0, -HW, -0.04), (BACK, HW, 0.0), STEEL)


def sleeping_surface(b: SParts) -> None:
    """The mattress in two sections (the back one along the backrest) and the pillow on it."""
    th = MAT_TOP - 0.48
    MK.rbox(b.soft, (FOOT + 0.04, -0.47, 0.48), (0.0, 0.47, MAT_TOP), 0.04, BEDDING, 2)
    with b.at(T(0.0, 0.0, MAT_TOP) @ Ry(-RECLINE)):
        MK.rbox(b.soft, (0.0, -0.47, -th), (BACK - 0.02, 0.47, 0.0), 0.035, BEDDING, 2)
        MK.puff(b.soft, (0.7, 0.0, 0.066), (0.17, 0.3, 0.066), BEDDING, e=0.6, nu=14, nv=7)


def boards_and_rails(b: SParts) -> None:
    """White head and foot boards with a teal inlay, a chart holder on the foot board, raised rails on the leg section, a push bar."""
    b.body.box((HEAD - 0.04, -HW, 0.44), (HEAD, HW, 1.12), WHITE_GLOSS)
    b.soft.box((HEAD - 0.045, -HW + 0.06, 0.95), (HEAD - 0.04, HW - 0.06, 1.05), PLASTER_TEAL)
    b.body.box((FOOT, -HW, 0.44), (FOOT + 0.04, HW, 0.98), WHITE_GLOSS)
    b.soft.box((FOOT - 0.006, -HW + 0.06, 0.8), (FOOT, HW - 0.06, 0.92), PLASTER_TEAL)
    b.soft.box((FOOT - 0.02, -0.18, 0.52), (FOOT, 0.18, 0.74), STRUCT)                                  # the chart holder
    b.soft.box((FOOT - 0.0215, -0.15, 0.55), (FOOT - 0.02, 0.15, 0.71), PAPER)
    b.soft.cyl((FOOT - 0.03, -HW + 0.08, 1.0), (FOOT - 0.03, HW - 0.08, 1.0), 0.016, STEEL, seg=8, caps=False)   # the push bar
    for sy in (-HW + 0.08, HW - 0.08):
        b.soft.cyl((FOOT - 0.03, sy, 0.98), (FOOT - 0.03, sy, 1.0), 0.016, STEEL, seg=8, caps=False)
    for side in (-1, 1):
        y = side * (HW + 0.02)
        for z in (0.9, 0.72):
            b.soft.cyl((-0.95, y, z), (-0.2, y, z), 0.014, STEEL, seg=8, caps=False)
        for x in (-0.95, -0.575, -0.2):
            b.soft.cyl((x, y, 0.5), (x, y, 0.9), 0.013, STEEL, seg=6, caps=False)


def drip_stand(b: SParts, px: float, py: float) -> None:
    """A drip stand (a five-star base on castors, a pole, a hook rail, a bag of fluid): the bed's own, at its head."""
    for q in range(5):
        a = 2 * math.pi * q / 5
        ex, ey = px + math.cos(a) * 0.26, py + math.sin(a) * 0.26
        b.soft.cyl((px, py, 0.05), (ex, ey, 0.05), 0.012, STEEL, seg=5, caps=False)
        b.soft.cyl((ex, ey, 0.0), (ex, ey, 0.05), 0.02, RUBBER, seg=6)
    b.soft.cyl((px, py, 0.05), (px, py, 2.05), 0.012, STEEL, seg=6, caps=False)
    b.soft.cyl((px - 0.14, py, 2.0), (px + 0.14, py, 2.0), 0.008, STEEL, seg=5, caps=False)
    b.soft.paint(MK.puff(b.soft, (px + 0.1, py, 1.84), (0.04, 0.06, 0.1), SWATCH, e=0.6, nu=8, nv=6), "m_saline")
    b.soft.paint(MK.puff(b.soft, (px - 0.1, py, 1.88), (0.035, 0.05, 0.08), SWATCH, e=0.6, nu=8, nv=6), "m_white")
    b.soft.box((px - 0.045, py - 0.06, 1.2), (px + 0.045, py + 0.06, 1.38), STRUCT)                      # the pump
    b.emit.lamp_box((px - 0.046, py - 0.045, 1.28), (px - 0.0455, py + 0.045, 1.35), "green", LAMP_DIM)


def headwall(b: SParts) -> None:
    """The bed-head unit on the wall at +1.4 (a services rail, a reading lamp, a bed plate) and the monitor on its arm."""
    xr = WALL - 0.1
    b.body.box((xr, -0.8, 1.3), (WALL - 0.005, 0.8, 1.47), WHITE_GLOSS)
    b.body.box((xr - 0.012, -0.8, 1.45), (xr, 0.8, 1.47), STEEL)
    for k, color in enumerate(("white", "green", "yellow", "blue", "grey5")):                            # the outlets in their gas colours
        y = -0.62 + k * 0.12
        b.soft.paint(b.soft.cyl((xr - 0.014, y, 1.37), (xr, y, 1.37), 0.03, SWATCH, seg=10), color)
    b.soft.paint(b.soft.cyl((xr - 0.02, 0.5, 1.37), (xr, 0.5, 1.37), 0.025, SWATCH, seg=10), "red")                    # the nurse-call button
    b.soft.box((xr - 0.012, 0.08, 1.33), (xr, 0.17, 1.4), STRUCT)                                         # two sockets
    b.soft.box((xr - 0.012, 0.2, 1.33), (xr, 0.29, 1.4), STRUCT)
    b.body.box((xr - 0.03, 0.62, 1.325), (xr - 0.012, 0.76, 1.445), STEEL)
    b.emit.label((xr - 0.0305, 0.69, 1.385), 0.11, 0.0275, (-1, 0, 0), "small_00")                         # the bed plate
    # the reading lamp over the bed, on a short arm, and its light
    b.body.box((xr, -0.5, 2.0), (WALL - 0.005, 0.5, 2.09), WHITE_GLOSS)
    b.emit.lamp_box((xr - 0.012, -0.46, 2.02), (xr, 0.46, 2.07), "medical", LAMP_DIM)
    # the monitor: a dark bezel behind the standby face, on an arm from the unit (the face is 4.5 mm in front of the origin plane: the live traces of SM_MED_Vitals sit 8 mm in front)
    mx, my, mz = MON_C
    fx, fy = math.cos(math.radians(MON_YAW)), math.sin(math.radians(MON_YAW))
    lx, ly = -fy, fx                                                                                     # the face's width direction (its local +y)
    cx, cy, cz = mx + lx * MON_W / 2, my + ly * MON_W / 2, mz + MON_H / 2
    b.body.cbox((cx - fx * 0.02, cy - fy * 0.02, cz), (0.05, MON_W + 0.05, MON_H + 0.05), STRUCT, rot=Rz(MON_YAW))
    b.emit.screen((cx + fx * 0.0045, cy + fy * 0.0045, cz), MON_W, MON_H, STANDBY, (fx, fy, 0.0))
    ax, ay = cx - fx * 0.045, cy - fy * 0.045
    b.soft.cyl((WALL - 0.03, ay, cz), (ax, ay, cz), 0.02, STEEL, seg=8)
    b.body.box((WALL - 0.045, ay - 0.045, cz - 0.3), (WALL - 0.005, ay + 0.045, cz + 0.3), TRIM)


if __name__ == "__main__":
    A.reset_scene()
    o = bed()
    print("MED_BED", A.stats(o)["tris"], "slots", len(o.data.materials), [m.name for m in o.data.materials])
