"""ASTRA ships v3 — the preview renders of shipgen3.py: a three-quarter view, close-up patches at the '×300 zoom' framing, the pieces
pulled apart and one cut face. Eevee, the orange star with the teal fill (the light is placed against each camera, so every view
shows the plates' relief). Nothing here is exported."""
from __future__ import annotations

import math
import os

import numpy as np
from mathutils import Matrix, Vector

import ship3_build as B
import ship3_geo as G
import ship3_preview as PV


def verts_world(obj) -> np.ndarray:
    me = obj.data
    a = np.empty(len(me.vertices) * 3, np.float32)
    me.vertices.foreach_get("co", a)
    P = a.reshape(-1, 3).astype(np.float64)
    M = np.array(obj.matrix_world)
    return P @ M[:3, :3].T + M[:3, 3]


def view_dir(az_deg: float, el_deg: float) -> np.ndarray:
    """Unit vector from the subject to the camera: az 0 = from the starboard side (-Y), -90 = from the bow (+X), 90 = from the stern."""
    az, el = math.radians(az_deg), math.radians(el_deg)
    return np.array([math.cos(el) * math.cos(az + math.pi / 2), -math.cos(el) * math.sin(az + math.pi / 2), math.sin(el)])


def shot(name: str, pts: np.ndarray, d: np.ndarray, path: str, size, lens: float = 50.0, side: float = 1.0, key_az: float = 55.0,
         key_el: float = 32.0, margin: float = 0.06) -> None:
    w, h = size
    cam, tgt = PV.fit_camera(name, pts, d, lens=lens, aspect=w / h, margin=margin)
    PV.rig(cam.location, tgt, key_az=key_az, key_el=key_el, side=side)
    PV.render(cam, path)


def render_previews(name: str, short_name: str, spec: dict, res: dict, obj, args: dict, compact) -> None:
    """All the views asked for in args['views'] for one ship (`compact` is shipgen3.compact: the slots the faces use)."""
    g, info = res["g"], res["info"]
    fac = spec["fac"]
    w, h = args["size"]
    outd = args["preview"]
    os.makedirs(outd, exist_ok=True)
    PV.make_materials(fac)
    PV.configure(w, h, args["samples"], exposure=info.get("exposure", 0.0))
    sn = short_name
    side = info.get("light_side", 1.0)
    pts = verts_world(obj)
    for view in args["views"]:
        if view == "three_quarter":
            d = view_dir(info.get("cam_az", -48.0), info.get("cam_el", 18.0))
            shot("cam", pts, d, os.path.join(outd, f"{sn}_three_quarter.jpg"), (w, h), lens=info.get("lens", 60.0), side=side,
                 margin=info.get("margin", 0.05))
        elif view == "closeup":
            for i, cu in enumerate(info.get("closeups", [])):
                tgt = np.array(cu["target"], float)
                nrm = G.norm(np.array(cu["normal"], float))
                dist = cu.get("distance", 110.0)
                span = cu.get("span", 50.0)
                cam = PV.camera("cam", tuple(tgt + nrm * dist), tuple(tgt), PV.close_up_lens(dist, span, 36.0))
                PV.rig(cam.location, tgt, key_az=cu.get("key_az", 62.0), key_el=cu.get("key_el", 28.0), side=cu.get("side", side))
                PV.render(cam, os.path.join(outd, f"{sn}_closeup_{cu.get('name', i)}.jpg"))
    cuts = info.get("cuts")
    if not cuts or not ("pieces" in args["views"] or "cutface" in args["views"]):
        return
    section_of = lambda x, cu=list(cuts): np.where(x > cu[0], 0, np.where(x > cu[1], 1, 2)) if len(cu) == 2 else np.where(x > cu[0], 0, 1)  # noqa: E731
    obj.hide_render = True
    ext = float(pts[:, 0].max() - pts[:, 0].min())
    gap = info.get("pieces_gap", 0.13) * ext
    nsec = len(cuts) + 1
    yaws = (9.0, -3.0, -10.0) if nsec == 3 else (7.0, -8.0)
    pitch = (-3.0, 2.0, 5.0) if nsec == 3 else (-3.0, 4.0)
    objs, cens = [], []
    for k in range(nsec):
        pa = g.assemble(sections={k}, include_caps=True, section_of=section_of)
        if pa is None:
            continue
        pa, pm = compact(pa, g.mats)
        po = B.build_object(f"_prev_{k}", pa, pm)
        cen = Vector(pa["V"].mean(axis=0))
        off = Vector((((nsec - 1) / 2.0 - k) * gap, ((k % 2) - 0.5) * gap * 0.10, (k - 1) * gap * 0.03))
        po.matrix_world = (Matrix.Translation(cen + off) @ Matrix.Rotation(math.radians(yaws[k]), 4, "Z")
                           @ Matrix.Rotation(math.radians(pitch[k]), 4, "Y") @ Matrix.Translation(-cen))
        objs.append(po)
        cens.append(cen)
    if "pieces" in args["views"]:
        allp = np.vstack([verts_world(o) for o in objs])
        d = view_dir(info.get("pieces_az", -62.0), info.get("pieces_el", 24.0))
        shot("cam", allp, d, os.path.join(outd, f"{sn}_pieces.jpg"), (w, h), lens=info.get("lens", 60.0), side=side, margin=0.05)
    if "cutface" in args["views"] and info.get("cut_faces"):
        k = 1
        fc = [f for f in info["cut_faces"] if f["section"] == k and f["normal"][0] > 0]
        if fc and k < len(objs):
            f = fc[0]
            for o in objs:
                o.hide_render = True
            objs[k].hide_render = False
            mw = objs[k].matrix_world
            ctr = mw @ Vector(f["center"])
            size = max(f["y"][1] - f["y"][0], f["z"][1] - f["z"][0])
            cam = PV.camera("cam", tuple(ctr + Vector((size * 1.7, -size * 0.85, size * 0.55))), tuple(ctr), 50.0)
            PV.rig(cam.location, tuple(ctr), key_az=40.0, key_el=26.0, side=side)
            PV.render(cam, os.path.join(outd, f"{sn}_cutface.jpg"))
