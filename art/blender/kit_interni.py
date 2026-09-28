"""Kit modulare degli interni della ASN Aquila (corridoi) — generatore procedurale.

Uso:  blender -b --factory-startup --python-exit-code 1 -P art/blender/kit_interni.py -- <cartella_output>

Moduli (asse X = direzione del corridoio, origine al centro del pavimento all'inizio del modulo):
  SM_COR_Straight_4m    corridoio dritto 4 m
  SM_COR_Window_4m  corridoio con finestrone sul lato destro (+Y) e vetro separato
  SM_COR_Bulkhead      paratia stagna con telaio della porta (spessore 0,5 m)
  SM_COR_DoorLeaf    anta scorrevole della porta (una; si usa specchiata)
  SM_COR_EndCap        parete di chiusura a fine corridoio
Sezione interna: larghezza 3,2 m, altezza 3,0 m, smussi superiori 0,5 m; pareti spesse 0,2 m.
"""
from __future__ import annotations

import json
import math
import os
import sys

import bmesh
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402

W, H, C, T = 3.2, 3.0, 0.5, 0.2   # larghezza, altezza, smusso, spessore
L = 4.0                            # lunghezza modulo


def inner_profile(inset: float = 0.0) -> list[tuple[float, float]]:
    """Profilo interno (y, z) del corridoio, in senso antiorario; `inset` lo restringe verso l'interno."""
    w2, h, c = W / 2 - inset, H - inset, C
    z0 = 0.0 + (inset if inset > 0 else 0.0)
    return [(-w2, z0), (w2, z0), (w2, h - c), (w2 - c, h), (-w2 + c, h), (-w2, h - c)]


def offset_convex(poly: list[tuple[float, float]], d: float) -> list[tuple[float, float]]:
    """Offset (verso l'esterno se d > 0) di un poligono convesso antiorario."""
    n = len(poly)
    lines = []
    for i in range(n):
        p0, p1 = Vector(poly[i]), Vector(poly[(i + 1) % n])
        e = (p1 - p0).normalized()
        normal = Vector((e.y, -e.x))  # normale esterna per poligono antiorario
        lines.append((p0 + normal * d, e))
    out = []
    for i in range(n):
        (a, da), (b, db) = lines[i - 1], lines[i]
        # intersezione a + t*da = b + s*db
        det = da.x * (-db.y) - da.y * (-db.x)
        t = ((b.x - a.x) * (-db.y) - (b.y - a.y) * (-db.x)) / det
        p = a + da * t
        out.append((p.x, p.y))
    return out


def ring_solid(bm, inner, outer, x0: float, x1: float, mat_inner_by_edge, mat_other: int) -> None:
    """Solido ad anello: profilo interno/esterno estruso lungo X da x0 a x1.
    mat_inner_by_edge[i] = materiale della faccia interna generata dal lato i del profilo interno."""
    n = len(inner)
    vi0 = [bm.verts.new((x0, y, z)) for y, z in inner]
    vo0 = [bm.verts.new((x0, y, z)) for y, z in outer]
    vi1 = [bm.verts.new((x1, y, z)) for y, z in inner]
    vo1 = [bm.verts.new((x1, y, z)) for y, z in outer]
    for i in range(n):
        j = (i + 1) % n
        # tappi alle estremità
        f = bm.faces.new((vi0[i], vo0[i], vo0[j], vi0[j])); f.material_index = mat_other
        f = bm.faces.new((vi1[j], vo1[j], vo1[i], vi1[i])); f.material_index = mat_other
        # superficie interna (visibile dal corridoio) e superficie esterna
        f = bm.faces.new((vi0[i], vi0[j], vi1[j], vi1[i])); f.material_index = mat_inner_by_edge[i]
        f = bm.faces.new((vo0[j], vo0[i], vo1[i], vo1[j])); f.material_index = mat_other
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)


def panel_quad_on_wall(bm, side: int, x0: float, x1: float, z0: float, z1: float, depth: float, mat: int) -> None:
    """Pannello (scatola sottile) sulla parete laterale: side = +1 destra (+Y), -1 sinistra."""
    y_wall = side * W / 2
    y_in = y_wall - side * depth
    A.add_box(bm, ((x0 + x1) / 2, (y_wall + y_in) / 2, (z0 + z1) / 2), (x1 - x0, abs(y_wall - y_in), z1 - z0), mat)


def corridor(name: str, window: bool = False):
    import bpy  # noqa: F401
    mats = [A.MAT_STRUTTURA, A.MAT_PANNELLO, A.MAT_PAVIMENTO, A.MAT_GRIGLIA, A.MAT_FINITURA, A.MAT_LUCE]
    MS, MP, MF, MG, MT, ML = range(6)
    inner = inner_profile()
    outer = offset_convex(inner, T)

    # 1) guscio strutturale (materiale scuro): pavimento, pareti, smussi, soffitto
    bm = bmesh.new()
    #   lati del profilo: 0 pavimento, 1 parete dx, 2 smusso dx, 3 soffitto, 4 smusso sx, 5 parete sx
    if window:
        # guscio senza la parete destra tra x=0.5 e x=3.5, z=0.9..2.4 (apertura del finestrone)
        ring_solid(bm, inner, outer, 0.0, L, [MF, MS, MS, MP, MS, MS], MS)
        geom_del = [f for f in bm.faces if all(v.co.y > W / 2 - 0.01 for v in f.verts)
                    and all(0.49 < v.co.x < 3.51 or True for v in f.verts)]
        bm.free()
        bm = bmesh.new()
        # ricostruisco il lato destro in tre pezzi attorno all'apertura
        left_ring = [0, 2, 3, 4, 5]
        ring_solid(bm, inner, outer, 0.0, L, [MF, MS, MS, MP, MS, MS], MS)
        # taglio con una scatola: rimuovo le facce del lato destro nella zona finestra e chiudo con un telaio
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-5,
                               plane_co=(0.5, 0, 0), plane_no=(1, 0, 0))
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-5,
                               plane_co=(3.5, 0, 0), plane_no=(1, 0, 0))
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-5,
                               plane_co=(0, 0, 0.9), plane_no=(0, 0, 1))
        bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], dist=1e-5,
                               plane_co=(0, 0, 2.4), plane_no=(0, 0, 1))
        hole = [f for f in bm.faces
                if f.calc_center_median().y > W / 2 - 0.02
                and 0.5 < f.calc_center_median().x < 3.5 and 0.9 < f.calc_center_median().z < 2.4]
        bmesh.ops.delete(bm, geom=hole, context="FACES")
        # telaio del finestrone (4 listelli) in materiale struttura
        for (cx, cz, sx, sz) in ((2.0, 0.9, 3.1, 0.08), (2.0, 2.4, 3.1, 0.08), (0.5, 1.65, 0.08, 1.58), (3.5, 1.65, 0.08, 1.58)):
            A.add_box(bm, (cx, W / 2 + T / 2, cz), (sx, T + 0.04, sz), MS)
    else:
        ring_solid(bm, inner, outer, 0.0, L, [MF, MS, MS, MP, MS, MS], MS)

    # 2) costole strutturali: mezza costola alle estremità (così due moduli ne formano una intera), una piena a metà
    rib_in = inner_profile(inset=0.08)
    for (x0, x1) in ((0.0, 0.1), (L / 2 - 0.1, L / 2 + 0.1), (L - 0.1, L)):
        ring_solid(bm, rib_in, inner, x0, x1, [MS] * 6, MS)

    # 3) pannelli chiari staccati di 1,5 cm (le fessure scure fanno da "linee di pannello")
    for side in (+1, -1):
        for (x0, x1) in ((0.14, 1.86), (2.14, 3.86)):
            if window and side == +1:
                continue
            panel_quad_on_wall(bm, side, x0, x1, 0.22, 1.28, 0.015, MP)   # pannello basso
            panel_quad_on_wall(bm, side, x0, x1, 1.32, 2.42, 0.015, MP)   # pannello alto
    # soffitto: due pannelli per campata ai lati della canalina luminosa
    for (x0, x1) in ((0.14, 1.86), (2.14, 3.86)):
        for yc in (-0.62, 0.62):
            A.add_box(bm, ((x0 + x1) / 2, yc, H - 0.0075), (x1 - x0, 0.95, 0.015), MP)
        # canalina luminosa con cornice
        A.add_box(bm, ((x0 + x1) / 2, 0.0, H - 0.03), (x1 - x0, 0.22, 0.06), MT)
        A.add_box(bm, ((x0 + x1) / 2, 0.0, H - 0.065), (x1 - x0 - 0.04, 0.14, 0.012), ML)

    # 4) pavimento: piastre laterali e grigliato centrale leggermente incassato
    for (x0, x1) in ((0.1, 1.9), (2.1, 3.9)):
        for yc in (-1.06, 1.06):
            A.add_box(bm, ((x0 + x1) / 2, yc, 0.006), (x1 - x0, 0.98, 0.012), MF)
        A.add_box(bm, ((x0 + x1) / 2, 0.0, -0.002), (x1 - x0, 1.1, 0.012), MG)
        # listelli di bordo del grigliato
        for yc in (-0.57, 0.57):
            A.add_box(bm, ((x0 + x1) / 2, yc, 0.004), (x1 - x0, 0.04, 0.02), MT)

    # 5) battiscopa, tubi, corrimano con staffe
    for side in (+1, -1):
        y = side * (W / 2 - 0.02)
        A.add_box(bm, (L / 2, y, 0.09), (L, 0.04, 0.18), MT)                   # battiscopa
        A.add_cylinder_x(bm, side * (W / 2 - 0.09), 0.30, 0.0, L, 0.045, 14, MT)  # tubo grande
        A.add_cylinder_x(bm, side * (W / 2 - 0.08), 0.44, 0.0, L, 0.028, 12, MT)  # tubo piccolo
        if not (window and side == +1):
            A.add_cylinder_x(bm, side * (W / 2 - 0.075), 1.02, 0.0, L, 0.021, 12, MT)  # corrimano
            for xb in (0.5, 1.5, 2.5, 3.5):
                A.add_box(bm, (xb, side * (W / 2 - 0.04), 1.02), (0.04, 0.07, 0.04), MT)
        # passacavi sotto lo smusso
        A.add_box(bm, (L / 2, side * (W / 2 - 0.35), H - C - 0.12), (L, 0.28, 0.06), MS)

    obj = A.new_object(name, bm, mats)
    A.bevel_and_normals(obj, width=0.008, segments=2)
    A.box_uv(obj, texel_m=1.0)
    return obj


def glass_panel(name: str):
    bm = bmesh.new()
    A.add_box(bm, (2.0, W / 2 + T / 2, 1.65), (3.0, 0.03, 1.5), 0)
    obj = A.new_object(name, bm, [A.MAT_VETRO])
    A.box_uv(obj)
    return obj


def bulkhead(name: str):
    """Paratia stagna: anello pieno profondo 0,5 m con apertura porta 1,4 x 2,3 m."""
    mats = [A.MAT_STRUTTURA, A.MAT_PANNELLO, A.MAT_FINITURA, A.MAT_LUCE]
    MS, MP, MT, ML = range(4)
    bm = bmesh.new()
    inner = inner_profile(inset=0.0)
    outer = offset_convex(inner, T)
    depth = 0.5
    # piastra piena della paratia (la sezione intera), poi foro della porta
    verts_front = [bm.verts.new((0.0, y, z)) for y, z in outer]
    verts_back = [bm.verts.new((depth, y, z)) for y, z in outer]
    ff = bm.faces.new(verts_front); ff.material_index = MS
    fb = bm.faces.new(list(reversed(verts_back))); fb.material_index = MS
    n = len(outer)
    for i in range(n):
        j = (i + 1) % n
        f = bm.faces.new((verts_front[i], verts_back[i], verts_back[j], verts_front[j])); f.material_index = MS
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    obj_plate = A.new_object(name + "_tmp_plate", bm, mats)
    # foro porta con booleana Manifold
    import bpy
    bm2 = bmesh.new()
    A.add_box(bm2, (depth / 2, 0.0, 1.15), (depth + 0.4, 1.4, 2.3), 0)
    cutter = A.new_object("cutter", bm2, [A.MAT_STRUTTURA])
    mod = obj_plate.modifiers.new("Porta", "BOOLEAN")
    mod.operation = "DIFFERENCE"
    mod.solver = "MANIFOLD"
    mod.object = cutter
    bpy.context.view_layer.objects.active = obj_plate
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)
    # telaio porta, pannelli decorativi e luce di stato sopra la porta
    bm3 = bmesh.new()
    for (cy, cz, sy, sz) in ((0.0, 2.36, 1.64, 0.12), (-0.76, 1.15, 0.12, 2.42), (0.76, 1.15, 0.12, 2.42)):
        A.add_box(bm3, (depth / 2, cy, cz), (depth + 0.06, sy, sz), MT)
    for x in (-0.03, depth + 0.03):
        for (cy, cz, sy, sz) in ((-1.22, 1.3, 0.62, 2.1), (1.22, 1.3, 0.62, 2.1), (0.0, 2.72, 1.9, 0.36)):
            A.add_box(bm3, (x, cy, cz), (0.02, sy, sz), MP)
        A.add_box(bm3, (x + (0.012 if x > 0 else -0.012), 0.0, 2.52), (0.012, 0.5, 0.05), ML)
    extra = A.new_object(name + "_tmp_extra", bm3, mats)
    obj = A.join([obj_plate, extra], name)
    A.bevel_and_normals(obj, width=0.01, segments=2)
    A.box_uv(obj)
    return obj


def door_leaf(name: str):
    """Anta scorrevole (metà porta): 0,7 x 2,3 m, spessa 0,08 m, con oblò e maniglia."""
    mats = [A.MAT_PANNELLO, A.MAT_FINITURA, A.MAT_LUCE]
    MP, MT, ML = range(3)
    bm = bmesh.new()
    A.add_box(bm, (0.0, 0.35, 1.15), (0.08, 0.7, 2.3), MP)
    A.add_box(bm, (0.0, 0.35, 0.12), (0.1, 0.72, 0.2), MT)      # fascia bassa
    A.add_box(bm, (0.0, 0.02, 1.15), (0.1, 0.04, 2.3), MT)      # bordo di battuta centrale
    A.add_box(bm, (0.0, 0.5, 1.05), (0.1, 0.05, 0.3), MT)       # maniglia incassata
    A.add_box(bm, (0.0, 0.35, 2.05), (0.1, 0.5, 0.03), ML)      # striscia luminosa di stato
    obj = A.new_object(name, bm, mats)
    A.bevel_and_normals(obj, width=0.006, segments=2)
    A.box_uv(obj)
    return obj


def end_cap(name: str):
    mats = [A.MAT_STRUTTURA, A.MAT_PANNELLO]
    bm = bmesh.new()
    outer = offset_convex(inner_profile(), T)
    vf = [bm.verts.new((0.0, y, z)) for y, z in outer]
    vb = [bm.verts.new((0.2, y, z)) for y, z in outer]
    bm.faces.new(vf); bm.faces.new(list(reversed(vb)))
    for i in range(len(outer)):
        j = (i + 1) % len(outer)
        bm.faces.new((vf[i], vb[i], vb[j], vf[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for (cy, cz, sy, sz) in ((-0.8, 1.2, 1.4, 2.0), (0.8, 1.2, 1.4, 2.0)):
        A.add_box(bm, (-0.01, cy, cz), (0.02, sy, sz), 1)
    obj = A.new_object(name, bm, mats)
    A.bevel_and_normals(obj, width=0.01)
    A.box_uv(obj)
    return obj


def main() -> None:
    out_dir = sys.argv[sys.argv.index("--") + 1] if "--" in sys.argv else "art/export/kit_interni"
    A.reset_scene()
    import bpy
    report = []
    builders = [("SM_COR_Straight_4m", lambda n: corridor(n)),
                ("SM_COR_Window_4m", lambda n: corridor(n, window=True)),
                ("SM_COR_WindowGlass", glass_panel),
                ("SM_COR_Bulkhead", bulkhead),
                ("SM_COR_DoorLeaf", door_leaf),
                ("SM_COR_EndCap", end_cap)]
    for name, build in builders:
        for o in list(bpy.context.scene.objects):
            bpy.data.objects.remove(o, do_unlink=True)
        obj = build(name)
        A.export_fbx(obj, os.path.join(out_dir, name + ".fbx"))
        report.append(A.stats(obj))
    with open(os.path.join(out_dir, "report.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, ensure_ascii=False)
    print("KIT_OK", json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
