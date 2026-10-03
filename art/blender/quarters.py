"""ASN Aquila — the Captain's quarters (Deck 1 · Section A), from data/ship/aquila_quarters.json.

  SM_QTR_Room                       the cabin (quarters_room.py, on the bridge v3 toolkit): dark walnut wainscot in raised panels, panelled cream walls, a navy carpet in a wood border with
                                    a brass compass rose, a coffered ceiling with a lit cove, the stern gallery (the great aft window with drapes and a window seat), the desk with its terminal (the
                                    Captain's log) and the Captain's chair, two visitors' chairs, the sofa, a low table and an armchair, the bunk in its alcove, the bookcase, the galley corner, the sideboard
                                    under the starboard window with the cradle of the Aquila's model (placed in Unreal), the sector chart on the forward wall, the clock, the Captain's cap, the pennant
  SM_QTR_Glass                      the windows (translucent: not Nanite)
  SM_SHIP_ASTRA_AquilaBridgeBlock   outside: the cabin's hull-plated block on its pedestal, overhanging the island's aft slope; the housing of the bridge lift beside it (its fore face open on the
                                    corridor's mouth, its pedestal without a top face under it); the fairings under the two corridors behind the bridge (they floated over the island)

Everything is in the cabin's frame (world_origin in the data); coordinates are Unreal's, U() flips Y for Blender.
blender -b --factory-startup --python-exit-code 1 -P art/blender/quarters.py -- art/export/quarters [--preview <dir> [--views entry,desk,...] [--samples N]] [--no-export]
"""
from __future__ import annotations

import json
import os
import sys

import bmesh

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import bridge3_lib as B3  # noqa: E402
import hullkit as K  # noqa: E402
import quarters_room as QR  # noqa: E402
from medbay import box  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_quarters.json"), encoding="utf-8"))
LEN, HW, H = D["length"], D["half_width"], D["height"]
OX, OY, OZ = D["world_origin"]
EXT = 0.35            # the outer skin
PLATE, FRAME, LIGHTS = "MI_HULL_A_Plate", "MI_HULL_A_Frame", "MI_HULL_A_Lights"


def L(x, y, z):
    """World (bridge frame) to the cabin's frame."""
    return x - OX, y - OY, z - OZ


def wall_with_holes(b, axis, pos0, pos1, u0, u1, z0, z1, holes, mat):
    """A wall slab: axis 'x' = the slab spans y (u) at x in [pos0, pos1]; 'y' = it spans x (u) at y in [pos0, pos1].
    holes: (u0, u1, z0, z1) rectangles left open (doors, windows)."""
    cuts_u = sorted({u0, u1, *[h[0] for h in holes], *[h[1] for h in holes]})
    for ua, ub in zip(cuts_u, cuts_u[1:]):
        zs = [(z0, z1)]
        for hu0, hu1, hz0, hz1 in holes:
            if hu0 <= ua and ub <= hu1:
                zs = [(z0, hz0), (hz1, z1)]
        for za, zb in zs:
            if zb - za < 1e-3:
                continue
            if axis == "x":
                box(b, pos0, pos1, ua, ub, za, zb, mat)
            else:
                box(b, ua, ub, pos0, pos1, za, zb, mat)


# ------------------------------------------------------------------------------------------------ the cabin
def room():
    return QR.build_room("SM_QTR_Room")


def glass():
    return QR.build_glass("SM_QTR_Glass")


# ------------------------------------------------------------------------------------------------ outside
def housing_block(b, xa: float, xf: float, yc: float, zc: float, sy: float, sz: float, c: float, mat: str, mouth) -> None:
    """hullkit.block's chamfered box (an octagonal section along x, in Blender's frame: yc is the centre's y as Blender has it) with the fore
    face (x = xf, the one that looks at the corridor) cut open on `mouth` = (y0, y1, z0, z1), also Blender's y: the corridor's clear opening,
    so that the corridor runs into the housing of the lift instead of ending on a patterned wall. The section is a tube from xa to xf, closed
    at the aft end, and the fore face is four convex plates round the opening (the opening lies inside the section's flat parts)."""
    bm = b.bm
    sec = K.chamfer_rect(sy / 2, sz / 2, c)
    ra = [bm.verts.new((xa, yc + y, zc + z)) for y, z in sec]
    rf = [bm.verts.new((xf, yc + y, zc + z)) for y, z in sec]
    my0, my1, mz0, mz1 = mouth
    hy0, hy1, hz0, hz1 = my0 - yc, my1 - yc, mz0 - zc, mz1 - zc
    assert sec[0][0] < hy0 < hy1 < sec[1][0] and sec[0][1] < hz0 < hz1 < sec[4][1], "the mouth must lie inside the flat parts of the section"
    va, vb = bm.verts.new((xf, yc + hy0, zc + hz0)), bm.verts.new((xf, yc + hy1, zc + hz0))
    vc, vd = bm.verts.new((xf, yc + hy1, zc + hz1)), bm.verts.new((xf, yc + hy0, zc + hz1))
    n = len(sec)
    polys = [[ra[i], ra[(i + 1) % n], rf[(i + 1) % n], rf[i]] for i in range(n)]
    polys.append(list(reversed(ra)))
    polys += [[rf[0], rf[1], vb, va], [rf[1], rf[2], rf[3], rf[4], vc, vb], [rf[4], rf[5], vd, vc], [rf[5], rf[6], rf[7], rf[0], va, vd]]
    centre = ((xa + xf) / 2, yc, zc)
    idx = b.mi(mat)
    for vs in polys:
        f = bm.faces.new(vs)
        f.material_index = idx
        mid = [sum(v.co[k] for v in vs) / len(vs) for k in range(3)]
        if f.normal.dot((mid[0] - centre[0], mid[1] - centre[1], mid[2] - centre[2])) < 0:        # every plate looks outwards
            f.normal_flip()


def drop_up_faces(b, first: int, z: float) -> int:
    """Delete, among the faces made since index `first`, the ones that look up and lie on the plane z (the top of a slab: under the lift's housing
    it would be a floor in the middle of the shaft). Returns how many went."""
    bm = b.bm
    bm.faces.ensure_lookup_table()
    gone = [f for f in list(bm.faces)[first:] if f.normal.z > 0.9 and all(abs(v.co.z - z) < 1e-4 for v in f.verts)]
    bmesh.ops.delete(bm, geom=gone, context="FACES_ONLY")
    return len(gone)


def exterior():
    b = A.Builder()
    wa, ws = D["window_aft"], D["window_side"]
    fx = D["corridor_end_x"] - OX            # the corridor's end, in the cabin's frame (+0.8)
    xa, xf = -LEN - EXT, fx
    yp, ys_ = -HW - EXT, HW + EXT
    zt = H + 0.4
    # the forward face around the corridor's end (the tube meets the block there), the sides, the aft face, the roof
    tube = (-1.85, 1.85, -0.3, 3.25)
    wall_with_holes(b, "x", 0.3, xf, yp, ys_, -0.3, zt, [tube], PLATE)
    wall_with_holes(b, "y", yp, -HW, xa, xf, -0.3, zt, [], PLATE)
    wall_with_holes(b, "y", HW, ys_, xa, xf, -0.3, zt, [(ws["x0"], ws["x1"], ws["z0"], ws["z1"])], PLATE)
    wall_with_holes(b, "x", xa, -LEN, yp, ys_, -0.3, zt, [(wa["y0"], wa["y1"], wa["z0"], wa["z1"])], PLATE)
    box(b, xa, xf, yp, ys_, H + 0.05, zt, PLATE)
    # a raised fairing on the roof, frames round the windows, a sill that sheds nothing (space has no rain: it is a
    # hood for the window's edge), running lights at the aft corners
    K.block(b, ((xa + xf) / 2 - 0.6, 0.0, zt + 0.25), (xf - xa - 2.2, 2 * ys_ - 1.6, 0.5), FRAME, c=0.35)
    for (y0, y1, z0, z1) in ((wa["y0"] - 0.25, wa["y0"], wa["z0"] - 0.25, wa["z1"] + 0.25), (wa["y1"], wa["y1"] + 0.25, wa["z0"] - 0.25, wa["z1"] + 0.25),
                             (wa["y0"], wa["y1"], wa["z1"], wa["z1"] + 0.25), (wa["y0"], wa["y1"], wa["z0"] - 0.25, wa["z0"])):
        box(b, xa - 0.22, xa, y0, y1, z0, z1, FRAME)
    box(b, xa - 0.6, xa, wa["y0"] - 0.4, wa["y1"] + 0.4, wa["z1"] + 0.25, wa["z1"] + 0.4, FRAME)
    for (x0, x1, z0, z1) in ((ws["x0"] - 0.2, ws["x0"], ws["z0"] - 0.2, ws["z1"] + 0.2), (ws["x1"], ws["x1"] + 0.2, ws["z0"] - 0.2, ws["z1"] + 0.2),
                             (ws["x0"], ws["x1"], ws["z1"], ws["z1"] + 0.2), (ws["x0"], ws["x1"], ws["z0"] - 0.2, ws["z0"])):
        box(b, x0, x1, ys_, ys_ + 0.2, z0, z1, FRAME)
    for (yy, m) in ((yp - 0.05, LIGHTS), (ys_ + 0.05, LIGHTS)):
        box(b, xa - 0.1, xa + 0.3, yy - 0.08, yy + 0.08, zt - 0.3, zt - 0.1, m)
    # the pedestal: down into the island's aft slope (it swallows the lower part), panelled bands
    K.slab(b, xa, xf, K.chamfer_rect(ys_, 7.0, 0.08, top=1.0, bottom=0.8), K.chamfer_rect(ys_, 7.0, 0.08, top=1.0, bottom=0.8),
           PLATE, -7.3, -7.3)
    for z in (-1.2, -3.4, -5.6):
        box(b, xa - 0.08, xa, yp + 0.4, ys_ - 0.4, z - 0.12, z, FRAME)
    # the housing of the bridge lift (behind the port corridor's end), on its own pedestal
    pb = D["port_block"]
    px0, _, _ = L(pb["x0"], 0, 0)
    px1, _, _ = L(pb["x1"], 0, 0)
    _, py0, _ = L(0, pb["y0"], 0)
    _, py1, _ = L(0, pb["y1"], 0)
    pc = ((px0 + px1) / 2, (py0 + py1) / 2)
    # (hullkit builds in Blender's frame: its y is flipped by hand). The fore face of the block has the corridor's mouth cut out (pb["mouth"], world
    # coordinates: the corridor's clear opening, 3.2 x 2.5 like the mouth of the housing mesh SM_SHIP_LiftHousingBridge), and the pedestal has no top
    # face under the block (the shafts of the lifts run down through it).
    _, mouth_y0, mouth_z0 = L(0, pb["mouth"]["y0"], pb["mouth"]["z0"])
    _, mouth_y1, mouth_z1 = L(0, pb["mouth"]["y1"], pb["mouth"]["z1"])
    housing_block(b, px1, px0, -pc[1], zt - 1.95, py1 - py0, 3.9, 0.18, PLATE, (-mouth_y1, -mouth_y0, mouth_z0, mouth_z1))
    n_before = len(b.bm.faces)
    K.slab(b, px1, px0, K.chamfer_rect((py1 - py0) / 2, 7.0, 0.06, top=1.0, bottom=0.8),
           K.chamfer_rect((py1 - py0) / 2, 7.0, 0.06, top=1.0, bottom=0.8), PLATE, -7.3, -7.3, -pc[1], -pc[1])
    assert drop_up_faces(b, n_before, -0.3) == 1, "the pedestal's top face was not found"
    box(b, px1 - 0.1, px1, pc[1] - 1.2, pc[1] + 1.2, 0.6, 2.4, FRAME)
    box(b, px1 - 0.12, px1 - 0.1, pc[1] - 1.0, pc[1] + 1.0, 2.1, 2.2, LIGHTS)
    # the fairings under the two corridors behind the bridge (from their floor down into the island's top)
    for yc in (-3.9, 3.9):
        _, ly, _ = L(0, yc, 0)
        box(b, fx, fx + 12.0, ly - 1.9, ly + 1.9, -1.8, -0.25, PLATE)
    obj = b.to_object("SM_SHIP_ASTRA_AquilaBridgeBlock")
    A.finish(obj, bevel=0.03, segments=1)
    A.box_uv(obj, texel_m=8.0)
    return obj


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[0] if argv and not argv[0].startswith("--") else "art/export/quarters"
    export = "--no-export" not in argv
    A.reset_scene()
    B3.load_label_atlas()
    B3.load_decor_atlas()
    report = []
    for fn in (room, glass, exterior):
        A.clear_objects()
        obj = fn()
        if export:
            os.makedirs(out, exist_ok=True)
            A.export_fbx(obj, os.path.join(out, obj.name + ".fbx"))
        report.append(A.stats(obj))
    print("QUARTERS_OK" if export else "QUARTERS_STATS", json.dumps(report))
    if "--preview" in argv:
        views = argv[argv.index("--views") + 1].split(",") if "--views" in argv else ["entry", "desk", "sofa", "bunk", "galley", "bookcase", "door"]
        samples = int(argv[argv.index("--samples") + 1]) if "--samples" in argv else 32
        QR.preview(argv[argv.index("--preview") + 1], views, samples)


if __name__ == "__main__":
    main()
