"""ASTRA ships v3 — the preview renders of shipgen3.py: a three-quarter view, close-up patches at the '×300 zoom' framing, the pieces
pulled apart and one cut face. Eevee, the orange star with the teal fill (the light is placed against each camera, so every view
shows the plates' relief). Nothing here is exported."""
from __future__ import annotations

import math
import os

import bpy
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


def shot(name: str, pts: np.ndarray, d: np.ndarray, path: str, size, lens: float = 50.0, side: float = 1.0, key_az: float = 72.0,
         key_el: float = 28.0, margin: float = 0.06) -> None:
    w, h = size
    cam, tgt = PV.fit_camera(name, pts, d, lens=lens, aspect=w / h, margin=margin)
    PV.rig(cam.location, tgt, key_az=key_az, key_el=key_el, side=side)
    PV.render(cam, path)


def crop_to(cx: float, cy: float, cw: int, ch: int, w: int, h: int) -> None:
    """Render only a window of cw x ch pixels centred on (cx, cy) in unit frame coordinates (0..1, y up) of a w x h frame."""
    r = bpy.context.scene.render
    r.use_border = True
    r.use_crop_to_border = True
    r.border_min_x, r.border_max_x = cx - 0.5 * cw / w, cx + 0.5 * cw / w
    r.border_min_y, r.border_max_y = cy - 0.5 * ch / h, cy + 0.5 * ch / h


def uncrop() -> None:
    r = bpy.context.scene.render
    r.use_border = False
    r.use_crop_to_border = False


def range_shots(sn: str, pts: np.ndarray, d: np.ndarray, outd: str, side: float, info: dict, args: dict) -> None:
    """The ship as the game shows it at a distance (docs/progressi/scafi): at 2 km and at 20 km, twice each.
      _screen  the main viewscreen (feed 1280 x 534, the ship fills about 60% of the width: AstraViewscreen's auto-zoom), the telephoto look;
      _eye     the bridge window with the naked eye (90 degrees across a 1600 x 900 frame, the player's field of view), a crop round the ship at
               its true size in pixels: this is what a silhouette, a hull colour and a few lights must carry on their own.
    d: unit vector from the ship to the camera."""
    ctr = 0.5 * (pts.min(axis=0) + pts.max(axis=0))
    reach = 0.5 * float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0)))
    tag = args.get("tag", "")
    for km in (2.0, 20.0):
        dist = km * 1000.0
        loc = ctr + d * dist
        # the screen: the bounding sphere's apparent half-size over 0.6 of the half-frame
        tan_half = (0.80 * reach / dist) / 0.62
        lens = 18.0 / max(tan_half, 1e-4)
        PV.configure(1280, 534, args["samples"], exposure=info.get("exposure", 0.0))
        uncrop()
        cam = PV.camera("cam", tuple(loc), tuple(ctr), lens, clip_end=dist * 4.0)
        PV.rig(cam.location, tuple(ctr), key_az=info.get("range_key_az", 72.0), key_el=28.0, side=side)
        PV.render(cam, os.path.join(outd, f"{sn}_range_{int(km)}km_screen{tag}.jpg"))
        # the naked eye: 90 degrees across 1600 x 900, the render window only a few hundred pixels round the ship
        PV.configure(1600, 900, args["samples"], exposure=info.get("exposure", 0.0))
        span_px = 800.0 * 2.0 * reach / dist
        cw = int(min(1600, max(160, span_px * 1.25)))
        ch = int(cw * 9 / 16)
        crop_to(0.5, 0.5, cw, ch, 1600, 900)
        cam = PV.camera("cam", tuple(loc), tuple(ctr), 18.0, clip_end=dist * 4.0)
        PV.rig(cam.location, tuple(ctr), key_az=info.get("range_key_az", 72.0), key_el=28.0, side=side)
        PV.render(cam, os.path.join(outd, f"{sn}_range_{int(km)}km_eye{tag}.jpg"))
        uncrop()


def blueprint_shots(sn: str, pts: np.ndarray, outd: str, side: float, info: dict, args: dict) -> None:
    """Side, top and front elevations, orthographic, lit from the camera's upper left: the silhouette and its proportions."""
    ctr = 0.5 * (pts.min(axis=0) + pts.max(axis=0))
    ext = pts.max(axis=0) - pts.min(axis=0)
    tag = args.get("tag", "")
    w, h = 1600, 600
    PV.configure(w, h, args["samples"], exposure=info.get("exposure", 0.0))
    # (name, direction from the ship to the camera, the frame's horizontal extent in metres, the up vector)
    views = (("side", (0.0, -1.0, 0.0), max(ext[0] * 1.04, ext[2] * 1.04 * w / h), (0.0, 0.0, 1.0)),
             ("top", (0.0, 0.0, 1.0), max(ext[0] * 1.04, ext[1] * 1.04 * w / h), (0.0, 1.0, 0.0)),
             ("front", (1.0, 0.0, 0.0), max(ext[1] * 1.04, ext[2] * 1.04 * w / h), (0.0, 0.0, 1.0)))
    for nm, dv, scale, up in views:
        dv = np.asarray(dv, float)
        loc = ctr + dv * (0.5 * float(np.linalg.norm(ext)) + 400.0)
        cd = bpy.data.cameras.new("cam")
        cd.type = "ORTHO"
        cd.ortho_scale = scale
        cd.clip_start, cd.clip_end = 1.0, 60000.0
        o = bpy.data.objects.new("cam", cd)
        bpy.context.scene.collection.objects.link(o)
        o.location = tuple(loc)
        f = Vector(tuple(ctr - loc))
        quat = f.to_track_quat("-Z", "Y") if abs(f.normalized().z) < 0.99 else f.to_track_quat("-Z", "X")
        o.rotation_euler = quat.to_euler()
        if nm == "top":
            o.rotation_euler = (0.0, 0.0, 0.0)               # looking straight down: +x to the right, +y (port) up the frame
        PV.rig(o.location, tuple(ctr), key_az=info.get("blueprint_key_az", 60.0), key_el=info.get("blueprint_key_el", 40.0), side=side)
        PV.render(o, os.path.join(outd, f"{sn}_blueprint_{nm}{tag}.jpg"))


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
        if view == "range":
            cam = args.get("cam") or [info.get("cam_az", -48.0), info.get("cam_el", 18.0)]
            range_shots(sn, pts, view_dir(cam[0], cam[1]), outd, side, info, args)
            PV.configure(w, h, args["samples"], exposure=info.get("exposure", 0.0))
            continue
        if view == "blueprint":
            blueprint_shots(sn, pts, outd, side, info, args)
            PV.configure(w, h, args["samples"], exposure=info.get("exposure", 0.0))
            continue
        if view == "three_quarter":
            cam = args.get("cam") or [info.get("cam_az", -48.0), info.get("cam_el", 18.0), info.get("lens", 60.0)]
            d = view_dir(cam[0], cam[1])
            shot("cam", pts, d, os.path.join(outd, f"{sn}_three_quarter{args.get('tag', '')}.jpg"), (w, h), lens=cam[2] if len(cam) > 2 else info.get("lens", 60.0),
                 side=side, key_el=cam[3] if len(cam) > 3 else 28.0, margin=info.get("margin", 0.05))
        elif view == "closeup":
            for i, cu in enumerate(info.get("closeups", [])):
                tgt = np.array(cu["target"], float)
                nrm = G.norm(np.array(cu["normal"], float))
                dist = cu.get("distance", 110.0)
                span = cu.get("span", 50.0)
                cam = PV.camera("cam", tuple(tgt + nrm * dist), tuple(tgt), PV.close_up_lens(dist, span, 36.0))
                PV.rig(cam.location, tgt, key_az=cu.get("key_az", 70.0), key_el=cu.get("key_el", 36.0), side=cu.get("side", side))
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
        shot("cam", allp, d, os.path.join(outd, f"{sn}_pieces.jpg"), (w, h), lens=info.get("lens", 60.0), side=side, margin=0.05, key_az=48.0, key_el=30.0)
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
            PV.rig(cam.location, tuple(ctr), key_az=68.0, key_el=24.0, side=side)
            PV.render(cam, os.path.join(outd, f"{sn}_cutface.jpg"))
