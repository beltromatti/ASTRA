"""The Falcon's cockpit, seen from the pilot's seat (first person): the tub with its side consoles, the ejection seat,
the instrument panel with three displays under a glare shield, the stick and the throttle, the canopy frame, and
outside it the Falcon itself — the nose ahead, the wings and the twin fins when the pilot looks around.

Frame: metres, +X forward, +Z up, the pilot's eye at the origin (the fighter pawn's camera). The outside of the ship
matches craft2("fighter") in shipgen2.py (the eye sits 3.2 m ahead of the Falcon's centre, 1.0 m above its axis).

Run: blender -b --factory-startup --python-exit-code 1 -P art/blender/cockpit.py -- art/export/cockpit [--preview <dir>]
"""
from __future__ import annotations

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import hullkit as K  # noqa: E402

# slot names = the Unreal instances they get (astra_editor.assign_materials_by_slot)
PLATE, FRAME, LIVERY, LIGHTS = "MI_HULL_A_Plate", "MI_HULL_A_Frame", "MI_HULL_A_Livery", "MI_HULL_A_Lights"
TUB, SEAT, SCREEN, ACCENT, TRIM = "MI_ASTRA_Structure", "MI_ASTRA_Leather", "MI_ASTRA_ScreenTactical", "MI_ASTRA_Accent", "MI_ASTRA_Trim"
ENGINE, GLOW = "MI_HULL_A_Engine", "MI_HULL_A_Glow"

EYE_AHEAD, EYE_UP = 3.2, 1.0          # where the eye is in the Falcon's own frame (for the outside parts)


def arch(b, x: float, pts, r: float, mat: str) -> None:
    """A canopy bow: a chain of struts through (y, z) points at station x."""
    for (y0, z0), (y1, z1) in zip(pts, pts[1:]):
        b.cylinder((x, y0, z0), (x, y1, z1), r, mat, segments=8)


def canopy_profile(x: float) -> list[tuple[float, float]]:
    """The canopy's cross-section at station x: from the port sill over the top to the starboard sill."""
    top = 0.42 - 0.18 * max(0.0, (x - 0.2) / 0.9) ** 2 - 0.05 * max(0.0, (-0.3 - x) / 0.6)
    half = 0.62 - 0.22 * max(0.0, (x - 0.4) / 0.7)
    out = []
    for k in range(9):
        a = math.pi * k / 8
        out.append((half * math.cos(a), -0.36 + (top + 0.36) * math.sin(a)))
    return out


def build(name: str):
    rng = random.Random(9)
    b = A.Builder()
    # ---------------------------------------------------------------- the tub and the consoles
    b.box((0.3, 0, -1.08), (2.3, 1.3, 0.06), TUB)                                      # floor
    for side in (-1, 1):
        K.slab(b, -0.85, 1.05, K.chamfer_rect(0.1, 0.36, 0.3), K.chamfer_rect(0.1, 0.3, 0.3), TUB, -0.72, -0.72, side * 0.56, side * 0.56)
        b.box((0.1, side * 0.5, -0.37), (1.7, 0.2, 0.03), TRIM)                          # console tops
        for k in range(6):                                                               # switch rows and lamps
            b.box((-0.45 + k * 0.22, side * 0.5, -0.35), (0.12, 0.08, 0.02), TUB)
            if rng.random() < 0.6:
                b.box((-0.45 + k * 0.22 + 0.04, side * 0.47, -0.338), (0.02, 0.02, 0.01), ACCENT if rng.random() < 0.5 else LIGHTS)
    # ---------------------------------------------------------------- the seat (ejection seat, headrest behind the eye)
    K.block(b, (-0.22, 0, -0.8), (0.5, 0.5, 0.12), SEAT, c=0.2)                        # pan
    K.slab(b, -0.55, -0.42, K.chamfer_rect(0.25, 0.5, 0.25), K.chamfer_rect(0.23, 0.46, 0.25), SEAT, -0.35, -0.3)   # back
    K.block(b, (-0.5, 0, 0.05), (0.14, 0.3, 0.26), SEAT, c=0.3)                        # headrest
    for side in (-1, 1):
        b.box((-0.5, side * 0.28, -0.4), (0.12, 0.05, 0.9), TUB)                        # seat rails
        b.box((-0.5, side * 0.2, 0.2), (0.06, 0.04, 0.12), (LIVERY if side > 0 else FRAME))   # ejection handles
    # ---------------------------------------------------------------- the stick and the throttle
    b.cylinder((0.32, 0, -1.05), (0.4, 0, -0.62), 0.025, TUB, segments=10)
    K.block(b, (0.41, 0, -0.56), (0.07, 0.06, 0.14), SEAT, c=0.35)
    b.box((0.44, 0, -0.5), (0.02, 0.02, 0.02), LIGHTS)
    b.box((0.05, 0.48, -0.36), (0.3, 0.05, 0.03), TUB)                                  # throttle quadrant (port)
    b.cylinder((0.1, 0.46, -0.35), (0.16, 0.44, -0.18), 0.02, TUB, segments=8)
    K.block(b, (0.17, 0.44, -0.15), (0.08, 0.07, 0.07), SEAT, c=0.3)
    # ---------------------------------------------------------------- the instrument panel and the glare shield
    K.slab(b, 0.72, 0.98, K.chamfer_rect(0.58, 0.26, 0.15), K.chamfer_rect(0.58, 0.3, 0.15), TUB, -0.66, -0.72)
    K.block(b, (0.72, 0, -0.34), (0.14, 1.1, 0.04), TUB, c=0.2)                        # glare shield
    b.box((0.645, 0, -0.355), (0.02, 1.0, 0.01), ACCENT)                                 # its lit edge
    for (y, w, h) in ((0.0, 0.24, 0.19), (0.36, 0.19, 0.16), (-0.36, 0.19, 0.16)):     # three displays
        b.box((0.705, y, -0.52), (0.02, w + 0.03, h + 0.03), FRAME)
        b.box((0.694, y, -0.52), (0.006, w, h), SCREEN)
    for k in range(8):                                                                   # warning lamps under them
        b.box((0.7, -0.35 + k * 0.1, -0.7), (0.01, 0.05, 0.02), LIGHTS if k % 3 else ACCENT)
    # ---------------------------------------------------------------- the canopy frame
    for x in (0.62, -0.34):
        arch(b, x, canopy_profile(x), 0.022 if x != 0.62 else 0.03, FRAME)
    prof = [canopy_profile(0.62 - k * 0.12) for k in range(9)]
    for i in (0, 8):                                                                     # sill rails
        for k in range(8):
            y0, z0 = prof[k][i]
            y1, z1 = prof[k + 1][i]
            b.cylinder((0.62 - k * 0.12, y0, z0), (0.62 - (k + 1) * 0.12, y1, z1), 0.03, FRAME, segments=8)
    for k in range(8):                                                                   # the spine over the head
        y0, z0 = prof[k][4]
        y1, z1 = prof[k + 1][4]
        b.cylinder((0.62 - k * 0.12, y0, z0), (0.62 - (k + 1) * 0.12, y1, z1), 0.016, FRAME, segments=6)
    # ---------------------------------------------------------------- outside: the Falcon around the pilot
    # the fuselage is built in three pieces so the cockpit is a real opening: the nose ahead of the panel, the
    # shoulders and belly around the tub, the turtle deck and the tail behind the seat. Axis 1.2 m under the eye.
    AX = -1.2
    L = 18.0

    def sec(half_w: float, top: float, bottom: float):
        return (K.chamfer_rect(half_w, (top - bottom) / 2, 0.38, top=0.82, bottom=0.7), (top + bottom) / 2)

    nose = []
    for x, hw, top, bot in ((0.95, 1.3, -0.40, -2.15), (2.2, 1.2, -0.5, -2.05), (3.6, 0.95, -0.72, -1.9), (4.8, 0.62, -0.95, -1.7),
                            (5.8, 0.2, -1.15, -1.45)):
        sc, zc = sec(hw, top, bot)
        nose.append((x, sc, zc))
    hull = K.Hull(b, nose, PLATE, cell=0.45)
    hull.plate(rng, depth=(0.01, 0.03), recess=0.02, margin=0.03, skip=0.35, max_run=(2, 2), mats={FRAME: 0.15})
    b.cylinder((5.8, 0, -1.3), (6.15, 0, -1.3), 0.07, LIGHTS, segments=10)              # the sensor tip
    b.box((2.4, 0, -0.505), (2.2, 0.16, 0.012), LIVERY)                                 # a stripe down the nose
    for side in (-1, 1):                                                                # shoulders beside the tub
        K.slab(b, -0.9, 0.95, K.chamfer_rect(0.39, 0.88, 0.3, top=0.9), K.chamfer_rect(0.39, 0.88, 0.3, top=0.9), PLATE,
               -1.28, -1.28, side * 0.95, side * 0.95)
        b.box((0.0, side * 0.95, -0.395), (1.8, 0.7, 0.012), FRAME)                      # the sill plate
    K.slab(b, -0.9, 0.95, K.chamfer_rect(0.58, 0.5, 0.2), K.chamfer_rect(0.58, 0.5, 0.2), PLATE, -1.62, -1.62)   # belly
    b.box((-0.86, 0, -0.73), (0.06, 1.12, 0.7), TUB)                                     # bulkhead behind the seat
    aft = []
    for x, hw, top, bot in ((-0.9, 1.35, -0.40, -2.15), (-1.7, 1.35, 0.02, -2.2), (-4.0, 1.35, -0.12, -2.2), (-8.0, 1.15, -0.35, -2.1),
                            (-10.9, 0.85, -0.6, -1.85)):
        sc, zc = sec(hw, top, bot)
        aft.append((x, sc, zc))
    aft.reverse()
    tail = K.Hull(b, aft, PLATE, cell=0.6)
    tail.plate(rng, depth=(0.01, 0.03), recess=0.02, margin=0.03, skip=0.35, max_run=(2, 2), mats={FRAME: 0.12})
    for side in (-1, 1):                                                                 # the wings
        y0, y1 = side * 1.2, side * L * 0.36
        z = AX - 0.27
        x_root = -8.24
        root_c, tip_c, sweep = L * 0.42, L * 0.14, L * 0.18
        bm = b.bm
        verts = [bm.verts.new(v) for v in (
            (x_root, y0, z - 0.1), (x_root + root_c, y0, z - 0.1), (x_root + sweep + root_c * 0.5 + tip_c * 0.5, y1, z + 0.2),
            (x_root + sweep + root_c * 0.5 - tip_c * 0.5, y1, z + 0.2),
            (x_root, y0, z + 0.1), (x_root + root_c, y0, z + 0.1), (x_root + sweep + root_c * 0.5 + tip_c * 0.5, y1, z + 0.26),
            (x_root + sweep + root_c * 0.5 - tip_c * 0.5, y1, z + 0.26))]
        import bmesh
        idx = b.mi(PLATE)
        faces = [bm.faces.new((verts[a], verts[bb], verts[c], verts[d])) for a, bb, c, d in
                 ((0, 1, 2, 3), (7, 6, 5, 4), (0, 4, 5, 1), (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0))]
        for f in faces:
            f.material_index = idx
        bmesh.ops.recalc_face_normals(bm, faces=faces)
        tipx = x_root + sweep + root_c * 0.5
        K.running_lights(b, [(tipx, y1, z + 0.28)], 0.22, LIGHTS)
        b.box((tipx - tip_c * 0.1, y1 - side * 0.6, z + 0.25), (tip_c * 0.8, 0.6, 0.1), LIVERY)
        for k in range(2):                                                               # missiles on the hardpoints
            yy = side * (2.2 + (L * 0.36 - 1.35) * (0.35 + 0.3 * k))
            b.cylinder((-6.4, yy, z - 0.42), (-2.3, yy, z - 0.42), 0.2, FRAME, segments=10)
            b.cylinder((-2.3, yy, z - 0.42), (-1.9, yy, z - 0.42), 0.2, LIVERY, segments=10, radius2=0.02)
        yb = side * 0.75                                                                 # twin fins
        K.slab(b, -11.84, -8.6, K.chamfer_rect(0.1, 0.97, 0.2), K.chamfer_rect(0.08, 0.38, 0.2), PLATE, AX + 1.4, AX + 1.68,
               yb + side * 0.2, yb + side * 0.5)
    for i in range(2):                                                                   # engines
        yy = (i - 0.5) * 1.55
        r = L * 0.04
        b.cylinder((-10.9, yy, AX), (-12.3, yy, AX), r * 1.15, FRAME, segments=16)
        b.cylinder((-12.3, yy, AX), (-12.8, yy, AX), r * 0.85, ENGINE, segments=16, radius2=r * 1.05)
        b.cylinder((-12.4, yy, AX), (-12.55, yy, AX), r * 0.9, GLOW, segments=16)
    obj = b.to_object(name)
    A.finish(obj, bevel=0.006, segments=1)
    A.box_uv(obj, texel_m=1.0)
    return obj


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_dir = argv[0] if argv else "art/export/cockpit"
    preview = argv[argv.index("--preview") + 1] if "--preview" in argv else None
    A.reset_scene()
    A.clear_objects()
    obj = build("SM_CRAFT_ASTRA_Falcon_Cockpit")
    os.makedirs(out_dir, exist_ok=True)
    A.export_fbx(obj, os.path.join(out_dir, "SM_CRAFT_ASTRA_Falcon_Cockpit.fbx"))
    print("COCKPIT_OK", A.stats(obj))
    if preview:
        import bpy
        from mathutils import Vector
        os.makedirs(preview, exist_ok=True)
        scene = bpy.context.scene
        for tag, loc, look in (("pilot", (0.0, 0.0, 0.0), (3.0, 0.0, -0.45)), ("side", (0.2, -0.1, 0.05), (-1.0, -4.0, -0.8)),
                               ("out", (6.0, -7.0, 2.5), (-1.0, 0.0, -0.8))):
            cam_data = bpy.data.cameras.new("C")
            cam_data.lens = 18 if tag != "out" else 30
            cam_data.clip_start = 0.02
            cam = bpy.data.objects.new("C", cam_data)
            scene.collection.objects.link(cam)
            cam.location = loc
            d = (Vector(look) - Vector(loc)).normalized()
            cam.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
            scene.camera = cam
            scene.render.engine = "BLENDER_WORKBENCH"
            scene.display.shading.light = "STUDIO"
            scene.display.shading.color_type = "RANDOM"
            scene.display.shading.show_cavity = True
            scene.render.resolution_x, scene.render.resolution_y = 1400, 800
            scene.render.filepath = os.path.join(preview, f"cockpit_{tag}.png")
            bpy.ops.render.render(write_still=True)
            bpy.data.objects.remove(cam, do_unlink=True)


if __name__ == "__main__":
    main()
