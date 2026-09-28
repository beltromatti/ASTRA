"""The Aquila's lifepods: the corridor hatch, the pod's cramped inside (first person, from the Captain's seat) and the
pod seen from outside (the others drifting away when the ship is abandoned).

  SM_POD_Hatch     on a corridor wall: frame +X = out of the wall, Y along it, Z up; origin on the wall's face at the
                   floor, centred. It fills one wall bay (1.72 x 2.42 m, the corridor kit's panel slot): a yellow collar
                   with black chevrons, the heavy door with a porthole glowing red (the pod's light), a lever, the
                   LIFEPOD plate and a status lamp above (green: ready; the game turns it amber, then red)
  SM_POD_Interior  +X forward (the porthole), Z up, the Captain's eye at the origin, seated on the front seat facing the
                   porthole; a tube 2.7 m across with ribs, a flat deck, five seats along the walls with harnesses,
                   the console, lockers, oxygen, the red emergency strip; the rear hatch with its wheel
  SM_POD_Exterior  the same capsule from outside (+X = the porthole's end): hull plating, the livery band, the rear
                   collar with four thrusters, the beacon on top

Run: blender -b --factory-startup --python-exit-code 1 -P art/blender/lifepod.py -- art/export/lifepod [--preview <dir>]
"""
from __future__ import annotations

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402

# slot names = the Unreal instances they get (astra_editor.assign_materials_by_slot)
WALL, STRUCT, TRIM, SEAT, RUBBER = "MI_ASTRA_Panel", "MI_ASTRA_Structure", "MI_ASTRA_Trim", "MI_ASTRA_Leather", "MI_ASTRA_Rubber"
GLASS, LIGHT, FLOOR = "MI_ASTRA_Glass", "MI_ASTRA_Light", "MI_ASTRA_FloorBridge"
YELLOW, BLACK, RED, STATUS, SCREEN = "MI_POD_Yellow", "MI_POD_Black", "MI_POD_RedLight", "MI_POD_Status", "MI_POD_Screen"
SIGN = "MI_SIGN_Lifepod_1A"
PLATE, FRAME, LIVERY, LIGHTS, ENGINE = "MI_HULL_A_Plate", "MI_HULL_A_Frame", "MI_HULL_A_Livery", "MI_HULL_A_Lights", "MI_HULL_A_Engine"

R, ZC = 1.35, -0.15            # the tube: radius, axis height (the eye is 0.15 m above the axis)
X_AFT, X_RING, X_NOSE = -2.25, 0.85, 1.3
R_NOSE, R_PORT = 0.74, 0.54
DECK = -1.2                    # the deck under the seats (1.7 m wide)


def ring(x: float, r: float, zc: float, n: int, y0: float = 0.0):
    return [(x, y0 + r * math.cos(2 * math.pi * k / n), zc + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def loft(b, rings, mat: str, inward: bool, closed: bool = True, skip=None) -> None:
    """Quads between consecutive rings of points (same count). inward: normals towards the axis."""
    bm = b.bm
    idx = b.mi(mat)
    vs = [[bm.verts.new(p) for p in rg] for rg in rings]
    n = len(rings[0])
    for a, c in zip(vs, vs[1:]):
        for k in range(n if closed else n - 1):
            j = (k + 1) % n
            quad = (a[k], c[k], c[j], a[j]) if inward else (a[k], a[j], c[j], c[k])
            if skip and skip(quad):
                continue
            f = bm.faces.new(quad)
            f.material_index = idx


def fan(b, center, rim, mat: str, flip: bool) -> None:
    bm = b.bm
    c = bm.verts.new(center)
    vs = [bm.verts.new(p) for p in rim]
    idx = b.mi(mat)
    for k in range(len(vs)):
        j = (k + 1) % len(vs)
        f = bm.faces.new((c, vs[j], vs[k]) if flip else (c, vs[k], vs[j]))
        f.material_index = idx


def quad_prism(b, pts, depth_axis, depth: float, mat: str) -> None:
    """A flat quad (4 points, counter-clockwise seen from +depth_axis) extruded by `depth` along the axis."""
    bm = b.bm
    off = [0.0, 0.0, 0.0]
    off[depth_axis] = depth
    front = [bm.verts.new(p) for p in pts]
    back = [bm.verts.new((p[0] - off[0], p[1] - off[1], p[2] - off[2])) for p in pts]
    faces = [bm.faces.new(front), bm.faces.new(list(reversed(back)))]
    for k in range(4):
        j = (k + 1) % 4
        faces.append(bm.faces.new((front[k], back[k], back[j], front[j])))
    idx = b.mi(mat)
    for f in faces:
        f.material_index = idx
    import bmesh
    bmesh.ops.recalc_face_normals(bm, faces=faces)


def rib(b, x: float, r: float, zc: float, mat: str, t: float = 0.06, n: int = 28, zmin: float = -9.0) -> None:
    pts = ring(x, r, zc, n)
    for k in range(n):
        p, q = pts[k], pts[(k + 1) % n]
        if p[2] < zmin and q[2] < zmin:
            continue
        b.cylinder(p, q, t / 2, mat, segments=6)


def seat(b, x: float, y: float, facing: float, rng: random.Random, captain: bool = False) -> None:
    """A crash seat: pan, tilted back against the hull, headrest, side wings, a four-point harness. facing: yaw (deg)."""
    import bmesh
    from mathutils import Matrix
    start = len(b.bm.verts)
    pan_z = -0.72 if captain else -0.78
    b.box((0.0, 0.0, pan_z), (0.5, 0.5, 0.09), SEAT)                                 # pan
    b.box((0.0, 0.0, pan_z - 0.2), (0.4, 0.36, 0.3), STRUCT)                          # base
    b.box((-0.27, 0.0, pan_z + 0.42), (0.09, 0.5, 0.78), SEAT)                        # back
    b.box((-0.29, 0.0, pan_z + 0.93), (0.1, 0.32, 0.22), SEAT)                        # headrest
    for s in (-1, 1):
        b.box((-0.18, s * 0.27, pan_z + 0.25), (0.28, 0.05, 0.45), STRUCT)            # side wings
        b.cylinder((-0.2, s * 0.14, pan_z + 0.82), (0.06, s * 0.12, pan_z + 0.3), 0.022, RUBBER, segments=6)   # shoulder straps
        b.cylinder((0.06, s * 0.2, pan_z + 0.08), (0.08, s * 0.05, pan_z + 0.25), 0.02, RUBBER, segments=6)   # lap belts
    b.box((0.09, 0.0, pan_z + 0.27), (0.06, 0.1, 0.08), TRIM)                         # the buckle
    if captain:
        for s in (-1, 1):
            b.box((0.02, s * 0.3, pan_z + 0.2), (0.4, 0.07, 0.05), SEAT)              # armrests
    b.bm.verts.ensure_lookup_table()
    verts = [b.bm.verts[i] for i in range(start, len(b.bm.verts))]
    m = Matrix.Translation((x, y, 0.0)) @ Matrix.Rotation(math.radians(facing), 4, "Z")
    bmesh.ops.transform(b.bm, matrix=m, verts=verts)


def interior(name: str):
    rng = random.Random(21)
    b = A.Builder()
    n = 36
    below = lambda q: all(v.co.z < DECK - 0.02 for v in q)                             # noqa: E731  hidden under the deck
    # ---------------------------------------------------------------- the shell: tube, nose cone, the porthole's plate
    loft(b, [ring(X_AFT, R, ZC, n), ring(-0.6, R, ZC, n), ring(X_RING, R, ZC, n)], WALL, inward=True, skip=below)
    loft(b, [ring(X_RING, R, ZC, n), ring(X_NOSE - 0.12, R_NOSE + 0.1, ZC, n), ring(X_NOSE, R_NOSE, ZC, n)], STRUCT, inward=True, skip=below)
    loft(b, [ring(X_NOSE, R_NOSE, ZC, n), ring(X_NOSE, R_PORT + 0.06, ZC, n)], STRUCT, inward=True)          # the plate around the porthole
    loft(b, [ring(X_NOSE, R_PORT + 0.06, ZC, n), ring(X_NOSE + 0.08, R_PORT, ZC, n)], TRIM, inward=True)   # its bevelled rim
    fan(b, (X_NOSE + 0.1, 0.0, ZC), ring(X_NOSE + 0.1, R_PORT, ZC, n), GLASS, flip=True)                  # the glass
    for k in range(4):                                                                                   # rim bolts
        a = 2 * math.pi * (k + 0.5) / 4
        b.cylinder((X_NOSE - 0.02, (R_PORT + 0.12) * math.cos(a), ZC + (R_PORT + 0.12) * math.sin(a)),
                   (X_NOSE - 0.05, (R_PORT + 0.12) * math.cos(a), ZC + (R_PORT + 0.12) * math.sin(a)), 0.025, TRIM, segments=6)
    fan(b, (X_AFT, 0.0, ZC), ring(X_AFT, R, ZC, n), STRUCT, flip=False)                                  # the aft bulkhead
    # ---------------------------------------------------------------- deck, ribs, stringers
    half = math.sqrt(R * R - (DECK - ZC) ** 2)
    b.box_minmax((X_AFT, -half, DECK - 0.06), (X_RING + 0.2, half, DECK), FLOOR)
    for x in (-1.95, -1.4, -0.85, -0.3, 0.25, 0.8):
        rib(b, x, R - 0.04, ZC, STRUCT, t=0.07, zmin=DECK)
    for a in (58, 90, 122):                                                                              # stringers over the head
        yy, zz = (R - 0.07) * math.cos(math.radians(a)), ZC + (R - 0.07) * math.sin(math.radians(a))
        b.box_minmax((X_AFT + 0.05, yy - 0.03, zz - 0.03), (X_RING, yy + 0.03, zz + 0.03), STRUCT)
    # the red emergency strip along the crown, and handholds either side of it
    b.box_minmax((X_AFT + 0.2, -0.05, ZC + R - 0.1), (X_RING - 0.1, 0.05, ZC + R - 0.075), RED)
    for x in (-1.7, -1.1, -0.5, 0.1):
        for s in (-1, 1):
            a = math.radians(90 - s * 28)
            p = ((R - 0.12) * math.cos(a), ZC + (R - 0.12) * math.sin(a))
            b.cylinder((x - 0.18, p[0], p[1]), (x + 0.18, p[0], p[1]), 0.018, TRIM, segments=8)
            b.cylinder((x - 0.18, p[0], p[1]), (x - 0.18, p[0] * 1.06, p[1] + 0.05), 0.016, TRIM, segments=6)
            b.cylinder((x + 0.18, p[0], p[1]), (x + 0.18, p[0] * 1.06, p[1] + 0.05), 0.016, TRIM, segments=6)
    # ---------------------------------------------------------------- the seats: the Captain's, facing the porthole;
    # four along the walls facing in (the others who got in with the Captain)
    seat(b, 0.0, 0.0, 0.0, rng, captain=True)
    for x in (-0.95, -1.7):
        for s in (-1, 1):
            seat(b, x, s * 0.85, -90.0 * s, rng)
    # ---------------------------------------------------------------- the console before the Captain
    b.box_minmax((0.42, -0.42, DECK), (0.62, 0.42, -0.62), STRUCT)
    quad_prism(b, [(0.42, -0.42, -0.62), (0.42, 0.42, -0.62), (0.7, 0.42, -0.36), (0.7, -0.42, -0.36)], 2, 0.03, STRUCT)
    from mathutils import Matrix
    # two displays on the slope (43 degrees): local Z up the slope, local X into the console, local Y negative so the
    # image runs to the Captain's right (Blender -Y); the left one shows the texture's left half
    rot = Matrix.Rotation(math.radians(47), 4, "Y")
    for y in (-0.19, 0.19):
        c = (0.555 - 0.68 * 0.006, y, -0.495 + 0.73 * 0.006)
        b.screen(Matrix.Translation(c) @ rot @ Matrix.Diagonal((0.004, -0.3, 0.19, 1.0)), SCREEN,
                 u_range=(0.5, 1.0) if y < 0 else (0.0, 0.5))
        b.screen(Matrix.Translation((0.555 + 0.68 * 0.004, y, -0.495 - 0.73 * 0.004)) @ rot @ Matrix.Diagonal((0.012, 0.33, 0.22, 1.0)), TRIM)
    for k in range(7):
        b.box((0.47, -0.3 + k * 0.1, -0.64), (0.02, 0.05, 0.025), LIGHT if k % 3 else RED)
    b.cylinder((0.62, 0.33, -0.42), (0.625, 0.33, -0.395), 0.022, RED, segments=12)                         # the beacon switch
    # ---------------------------------------------------------------- aft: the hatch and its wheel, lockers, oxygen
    b.cylinder((X_AFT, 0.0, ZC - 0.05), (X_AFT + 0.08, 0.0, ZC - 0.05), 0.62, STRUCT, segments=32)         # door
    b.cylinder((X_AFT + 0.08, 0.0, ZC - 0.05), (X_AFT + 0.1, 0.0, ZC - 0.05), 0.5, YELLOW, segments=32)    # its painted face
    rib(b, X_AFT + 0.1, 0.62, ZC - 0.05, TRIM, t=0.05, n=32)                                               # rim
    rib(b, X_AFT + 0.24, 0.2, ZC - 0.05, TRIM, t=0.03, n=16)                                               # the wheel
    for k in range(3):
        a = math.radians(90 + k * 120)
        b.cylinder((X_AFT + 0.12, 0.0, ZC - 0.05), (X_AFT + 0.24, 0.2 * math.cos(a), ZC - 0.05 + 0.2 * math.sin(a)), 0.014, TRIM, segments=6)
    for s in (-1, 1):
        b.box_minmax((X_AFT + 0.02, s * 0.72 - 0.2, -0.95), (X_AFT + 0.34, s * 0.72 + 0.2, -0.3), STRUCT)   # lockers
        b.box_minmax((X_AFT + 0.34, s * 0.72 - 0.17, -0.9), (X_AFT + 0.345, s * 0.72 + 0.17, -0.35), TRIM)
        for k in range(2):                                                                                  # oxygen bottles
            yy = s * (0.62 + k * 0.16)
            b.cylinder((X_AFT + 0.5, yy, -1.15), (X_AFT + 0.5, yy, -0.45), 0.07, YELLOW, segments=12)
            b.cylinder((X_AFT + 0.5, yy, -0.45), (X_AFT + 0.5, yy, -0.37), 0.03, TRIM, segments=8)
    b.box_minmax((X_AFT + 0.02, -0.18, 0.55), (X_AFT + 0.2, 0.18, 0.85), WALL)                              # first-aid box
    b.box_minmax((X_AFT + 0.2, -0.05, 0.64), (X_AFT + 0.205, 0.05, 0.76), RED)
    obj = b.to_object(name)
    A.finish(obj, bevel=0.004, segments=1)
    A.box_uv(obj, texel_m=1.0)
    return obj


def exterior(name: str):
    b = A.Builder()
    n = 32
    rx = R + 0.1
    loft(b, [ring(X_AFT - 0.2, rx - 0.12, 0.0, n), ring(X_AFT, rx, 0.0, n), ring(-0.7, rx, 0.0, n)], PLATE, inward=False)
    loft(b, [ring(-0.7, rx, 0.0, n), ring(-0.3, rx, 0.0, n)], LIVERY, inward=False)                       # the livery band
    loft(b, [ring(-0.3, rx, 0.0, n), ring(X_RING, rx, 0.0, n), ring(X_NOSE - 0.1, R_NOSE + 0.22, 0.0, n),
             ring(X_NOSE + 0.1, R_NOSE + 0.08, 0.0, n)], PLATE, inward=False)
    fan(b, (X_NOSE + 0.12, 0.0, 0.0), ring(X_NOSE + 0.1, R_NOSE + 0.08, 0.0, n), FRAME, flip=False)
    fan(b, (X_NOSE + 0.14, 0.0, 0.0), ring(X_NOSE + 0.14, R_PORT, 0.0, n), GLASS, flip=False)
    fan(b, (X_AFT - 0.2, 0.0, 0.0), ring(X_AFT - 0.2, rx - 0.12, 0.0, n), FRAME, flip=True)
    for x in (-1.6, -0.9, 0.2):                                                                           # seams
        rib(b, x, rx + 0.01, 0.0, FRAME, t=0.05, n=n)
    b.cylinder((X_AFT - 0.2, 0.0, 0.0), (X_AFT - 0.45, 0.0, 0.0), 0.75, FRAME, segments=24)               # docking collar
    for k in range(4):                                                                                    # thrusters
        a = math.radians(45 + 90 * k)
        p = (X_AFT - 0.3, 1.05 * math.cos(a), 1.05 * math.sin(a))
        b.cylinder(p, (X_AFT - 0.55, p[1] * 1.08, p[2] * 1.08), 0.12, ENGINE, segments=10, radius2=0.18)
    b.cylinder((-0.9, 0.0, rx - 0.02), (-0.9, 0.0, rx + 0.18), 0.16, FRAME, segments=12)                   # the beacon
    b.cylinder((-0.9, 0.0, rx + 0.18), (-0.9, 0.0, rx + 0.34), 0.11, LIGHTS, segments=12, radius2=0.05)
    obj = b.to_object(name)
    A.finish(obj, bevel=0.01, segments=1)
    A.box_uv(obj, texel_m=1.0)
    return obj


def hatch(name: str):
    b = A.Builder()
    W, H = 1.72, 2.42
    b.box_minmax((-0.01, -W / 2, 0.0), (0.02, W / 2, H), STRUCT)                                          # backplate
    # the collar: yellow, standing 0.16 m out of the wall (it swallows the handrail)
    oy, iy, ob, ib, it, ot = 0.74, 0.5, 0.02, 0.1, 1.98, 2.1
    for s in (-1, 1):
        b.box_minmax((0.0, s * iy if s > 0 else -oy, ob), (0.16, oy if s > 0 else -iy, ot), YELLOW)
    b.box_minmax((0.0, -iy, ob), (0.16, iy, ib), YELLOW)
    b.box_minmax((0.0, -iy, it), (0.16, iy, ot), YELLOW)
    # black chevrons on its face (diagonal bands)
    step, band = 0.2, 0.085
    for s in (-1, 1):
        y0, y1 = (iy, oy) if s > 0 else (-oy, -iy)
        z = ob - 0.1
        while z < ot:
            za, zb = max(ob, z), min(ot, z + band)
            if zb - za > 0.02:
                sk = (y1 - y0) * 0.9
                quad_prism(b, [(0.162, y0, za), (0.162, y1, min(ot, za + sk)), (0.162, y1, min(ot, zb + sk)), (0.162, y0, zb)], 0, 0.004, BLACK)
            z += step
    for (za, zb) in ((ob, ib), (it, ot)):
        yy = -iy
        while yy < iy:
            ya, yb = yy, min(iy, yy + band)
            quad_prism(b, [(0.162, ya, za), (0.162, yb, za), (0.162, min(iy, yb + 0.08), zb), (0.162, min(iy, ya + 0.08), zb)], 0, 0.004, BLACK)
            yy += step
    # the door: heavy, recessed a hand's width, a porthole glowing red (the pod's light behind it), the lever
    b.box_minmax((0.02, -iy + 0.01, ib), (0.11, iy - 0.01, it), STRUCT)
    for z in (0.5, 1.2):
        b.box_minmax((0.11, -iy + 0.06, z - 0.015), (0.115, iy - 0.06, z + 0.015), TRIM)
    b.cylinder((0.11, 0.0, 1.55), (0.14, 0.0, 1.55), 0.19, TRIM, segments=24)
    b.cylinder((0.105, 0.0, 1.55), (0.145, 0.0, 1.55), 0.15, RED, segments=24)
    b.cylinder((0.145, 0.0, 1.55), (0.15, 0.0, 1.55), 0.15, GLASS, segments=24)
    b.box_minmax((0.11, 0.3, 0.96), (0.15, 0.36, 1.2), TRIM)                                               # lever pivot
    b.cylinder((0.15, 0.33, 1.14), (0.21, 0.33, 0.9), 0.022, RED, segments=8)                              # the lever
    # above: the LIFEPOD plate and the status lamp
    b.box_minmax((0.0, -0.6, 2.14), (0.05, 0.5, 2.4), STRUCT)
    b.screen(Matrix_T((0.055, -0.05, 2.27)) @ Matrix_D((0.006, 1.04, 0.24)), SIGN)
    b.box_minmax((0.0, 0.58, 2.16), (0.08, 0.74, 2.36), STRUCT)
    b.box_minmax((0.08, 0.6, 2.18), (0.1, 0.72, 2.34), STATUS)
    obj = b.to_object(name)
    A.finish(obj, bevel=0.004, segments=1)
    A.box_uv(obj, texel_m=1.0)
    return obj


def Matrix_T(p):
    from mathutils import Matrix
    return Matrix.Translation(p)


def Matrix_D(s):
    from mathutils import Matrix
    return Matrix.Diagonal((s[0], s[1], s[2], 1.0))


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_dir = argv[0] if argv else "art/export/lifepod"
    preview = argv[argv.index("--preview") + 1] if "--preview" in argv else None
    A.reset_scene()
    A.clear_objects()
    os.makedirs(out_dir, exist_ok=True)
    objs = {}
    for nm, fn in (("SM_POD_Interior", interior), ("SM_POD_Exterior", exterior), ("SM_POD_Hatch", hatch)):
        o = fn(nm)
        A.export_fbx(o, os.path.join(out_dir, nm + ".fbx"))
        objs[nm] = o
        print("LIFEPOD_OK", nm, A.stats(o))
    if preview:
        import bpy
        from mathutils import Vector
        os.makedirs(preview, exist_ok=True)
        for nm, o in objs.items():
            for other in objs.values():
                other.hide_render = other is not o
            if nm == "SM_POD_Interior":
                scene = bpy.context.scene
                for tag, loc, look in (("seat", (0.0, 0.0, 0.0), (2.0, 0.0, -0.3)), ("back", (0.2, 0.0, 0.1), (-2.5, 0.0, -0.4)),
                                       ("side", (0.1, 0.3, 0.1), (-1.2, -1.5, -0.6))):
                    cam_data = bpy.data.cameras.new("C")
                    cam_data.lens = 14
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
                    scene.render.resolution_x, scene.render.resolution_y = 960, 540
                    scene.render.filepath = os.path.join(preview, f"pod_{tag}.png")
                    bpy.ops.render.render(write_still=True)
                    bpy.data.objects.remove(cam, do_unlink=True)
            else:
                A.render_preview([o], os.path.join(preview, f"{nm}.png"), view=(30.0, 15.0) if nm == "SM_POD_Hatch" else (40.0, 25.0))


main()
