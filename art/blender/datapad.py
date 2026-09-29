"""The Captain's datapad: a rugged slate the Captain raises in the left hand anywhere aboard (the ship at a glance).

  SM_PROP_Datapad  the screen faces -X (the eye, when the pad is held up in front of the camera), Y across (Blender -Y =
                   the Captain's right), Z up; origin at the centre of the screen's face. 22 x 14.5 cm, 1.5 cm thick: a
                   graphite shell with rubber corner bumpers, a raised bezel, the 16:10 screen (MI_PAD_Screen: the game
                   paints it live), three keys under the screen, a status lamp, a grip strap across the back

Run: blender -b --factory-startup --python-exit-code 1 -P art/blender/datapad.py -- art/export/datapad [--preview <dir>]
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
from mathutils import Matrix  # noqa: E402

BODY, BUMPER, KEYS, LAMP, SCREEN = "MI_PAD_Body", "MI_ASTRA_Rubber", "MI_ASTRA_Trim", "MI_POD_Status", "MI_PAD_Screen"

W, H, T = 0.22, 0.145, 0.015          # the shell: width (Y), height (Z), thickness (X)
SW, SH = 0.184, 0.115                 # the screen, 16:10
SZ = 0.009                            # the screen sits a little above the centre (the keys below it)
FRONT = -T / 2                        # the shell's front face (towards the eye)


def datapad(name: str):
    parts = []
    # the shell: rounded all round
    parts.append(A.rounded_box(name + "_shell", (0.0, 0.0, 0.0), (T, W, H), 0.006, BODY, segments=4))
    # the bezel: a raised frame around the screen (the screen is recessed 1.5 mm behind its lip)
    b = A.Builder()
    lip = 0.0022
    x0, x1 = FRONT - lip, FRONT + 0.0005
    fw = 0.007                                               # frame width
    y0, y1 = -SW / 2 - fw, SW / 2 + fw
    z0, z1 = SZ - SH / 2 - fw, SZ + SH / 2 + fw
    b.box_minmax((x0, y0, SZ + SH / 2), (x1, y1, z1), BODY)
    b.box_minmax((x0, y0, z0), (x1, y1, SZ - SH / 2), BODY)
    b.box_minmax((x0, y0, SZ - SH / 2), (x1, -SW / 2, SZ + SH / 2), BODY)
    b.box_minmax((x0, SW / 2, SZ - SH / 2), (x1, y1, SZ + SH / 2), BODY)
    # the screen: its local +Y runs to the Captain's right (Blender -Y) so the picture is not mirrored
    b.screen(Matrix.Translation((FRONT - 0.0008, 0.0, SZ)) @ Matrix.Diagonal((0.001, -SW, SH, 1.0)), SCREEN)
    # three keys under the screen (left to right as the Captain sees them: -Y is the right), the status lamp
    for k, y in enumerate((0.03, 0.0, -0.03)):
        b.cylinder((FRONT, y, -0.057), (FRONT - 0.0025, y, -0.057), 0.0048 if k != 1 else 0.0056, KEYS, segments=20)
    b.box((FRONT - 0.0006, -0.088, -0.057), (0.0016, 0.006, 0.0022), LAMP)
    # the grip strap across the back, and its two anchors
    b.box_minmax((T / 2 - 0.0005, -0.018, -0.052), (T / 2 + 0.006, 0.018, 0.052), BUMPER)
    for z in (-0.056, 0.056):
        b.box_minmax((T / 2 - 0.0005, -0.022, z - 0.006), (T / 2 + 0.004, 0.022, z + 0.006), KEYS)
    # a stylus clip on the top edge
    b.box_minmax((-0.004, 0.07, H / 2 - 0.002), (0.004, 0.1, H / 2 + 0.003), KEYS)
    parts.append(A.finish(b.to_object(name + "_detail"), bevel=0.0007, segments=2))
    # rubber bumpers on the four corners: rounded blocks a little proud of the shell
    for sy in (-1, 1):
        for sz in (-1, 1):
            parts.append(A.rounded_box(name + f"_bump{sy}{sz}", (0.0, sy * (W / 2 - 0.013), sz * (H / 2 - 0.013)),
                                       (T + 0.004, 0.032, 0.032), 0.006, BUMPER, segments=3))
    obj = A.join(parts, name)
    A.box_uv(obj, texel_m=0.25)
    return obj


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_dir = argv[0] if argv else "art/export/datapad"
    preview = argv[argv.index("--preview") + 1] if "--preview" in argv else None
    A.reset_scene()
    A.clear_objects()
    os.makedirs(out_dir, exist_ok=True)
    o = datapad("SM_PROP_Datapad")
    A.export_fbx(o, os.path.join(out_dir, "SM_PROP_Datapad.fbx"))
    print("DATAPAD_OK", A.stats(o))
    if preview:
        os.makedirs(preview, exist_ok=True)
        A.render_preview([o], os.path.join(preview, "datapad_front.png"), view=(180.0 + 25.0, 15.0))
        A.render_preview([o], os.path.join(preview, "datapad_back.png"), view=(20.0, 20.0))


if __name__ == "__main__":
    main()
