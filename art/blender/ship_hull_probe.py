"""ASTRA ships: what the hull really is, measured on the exported meshes (FLOTTA-VIVA, docs/FLOTTA-VIVA.md §2).

The class plans (data/ship/plans/<class>.json) must lie inside the hulls the game draws, and their boarding hatches on the skin: the
lofts of art/blender/ship3_*.py are the truth, but they are a tangle of plates and details. This reads the exported FBX of each
class (art/export/ships_v3/, made by shipgen3.py), keeps the vertices of the main shell and writes a small profile per class
that the plan generator (ship_class_plans.py, pure Python) reads: for every station along the ship and every band of height, how far
the skin stands to port and to starboard, and where the keel and the top of the body are. A turret or a mast stands out of the
skin and has few vertices at that distance: the statistic is a low percentile of how far out the vertices of the band stand, so
the profile follows the plating, not the details on it.

  Blender -b --factory-startup --python art/blender/ship_hull_probe.py -- [--only lethe,styx] [--src art/export/ships_v3] [--out data/ship/plans/hulls]

Frame of the output: the mesh's own, as the game sees it (Unreal: X to the bow, Y to starboard, Z up, metres, origin at the mesh's origin;
the FBX holds Y mirrored: Unreal y = -Blender y). Pure data, small (tens of KB per class): it is committed, the FBX are not.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

# class key -> exported mesh, the step of the stations (m) and of the bands of height (m)
SHIPS = {
    "lethe":      ("SM_SHIP_MANDATE_Lethe", 2.0, 1.5),
    "styx":       ("SM_SHIP_MANDATE_Styx", 3.0, 2.0),
    "acheron":    ("SM_SHIP_MANDATE_Acheron", 4.0, 3.0),
    "vigilant":   ("SM_SHIP_ASTRA_Vigilant", 3.0, 2.0),
    "praetorian": ("SM_SHIP_ASTRA_Praetorian", 6.0, 4.0),
    "freighter":  ("SM_SHIP_GUILD_Freighter", 4.0, 2.5),
    "station":    ("SM_STATION_ASTRA_Watch", 4.0, 2.5),
}


def arg(name: str, default: str) -> str:
    if "--" in sys.argv:
        a = sys.argv[sys.argv.index("--") + 1:]
        if name in a and a.index(name) + 1 < len(a):
            return a[a.index(name) + 1]
    return default


def load_vertices(path: str) -> np.ndarray:
    """All the vertices of the mesh, in the Unreal frame (metres)."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=path)
    parts = []
    for o in bpy.context.scene.objects:
        if o.type != "MESH":
            continue
        me = o.data
        n = len(me.vertices)
        co = np.empty(n * 3, dtype=np.float32)
        me.vertices.foreach_get("co", co)
        co = co.reshape(-1, 3).astype(np.float64)
        m = np.array(o.matrix_world)
        parts.append(co @ m[:3, :3].T + m[:3, 3])
    v = np.concatenate(parts)
    v[:, 1] *= -1.0                                           # Blender y -> Unreal y
    return v


def probe(v: np.ndarray, dx: float, dz: float) -> dict:
    x0, x1 = float(v[:, 0].min()), float(v[:, 0].max())
    z0, z1 = float(v[:, 2].min()), float(v[:, 2].max())
    nx = int(math.ceil((x1 - x0) / dx))
    nz = int(math.ceil((z1 - z0) / dz))
    ix = np.clip(((v[:, 0] - x0) / dx).astype(np.int64), 0, nx - 1)
    iz = np.clip(((v[:, 2] - z0) / dz).astype(np.int64), 0, nz - 1)
    cell = ix * nz + iz
    order = np.argsort(cell, kind="stable")
    cs = cell[order]
    ys = v[order, 1]
    bounds = np.searchsorted(cs, np.arange(nx * nz + 1))
    # per cell: how far out the skin stands on each side. The statistic is a low-middle percentile of |y| among the vertices
    # on that side that stand beyond a third of the cell's furthest one (a flat flank has them all at one distance: any
    # percentile is that; a turret or a plate edge has few). The cells with too few vertices are empty (null).
    right = [[None] * nz for _ in range(nx)]
    left = [[None] * nz for _ in range(nx)]
    for i in range(nx):
        for k in range(nz):
            a, b = bounds[i * nz + k], bounds[i * nz + k + 1]
            if b - a < 6:
                continue
            y = ys[a:b]
            for side, arr in ((1.0, right), (-1.0, left)):
                s = y[y * side > 0.0] * side
                if len(s) < 4:
                    continue
                far = s.max()
                t = s[s >= 0.33 * far]
                arr[i][k] = round(float(np.percentile(t, 35.0)), 2)
    # the keel and the top of the body at each station: the vertices' heights, with the details (masts, turrets) trimmed (a percentile)
    # the body's upper surface is taken per lane across the ship (|y| bands): a tower is a lane that rises
    lanes = [0.0, 0.1, 0.2, 0.3, 0.4, 0.55, 0.7, 0.85, 1.01]
    wmax = float(np.abs(v[:, 1]).max())
    lane_top = []
    lane_bot = []
    xs_all = v[:, 0]
    xi = np.clip(((xs_all - x0) / dx).astype(np.int64), 0, nx - 1)
    order2 = np.argsort(xi, kind="stable")
    xi_s = xi[order2]
    b2 = np.searchsorted(xi_s, np.arange(nx + 1))
    for i in range(nx):
        a, b = b2[i], b2[i + 1]
        tops, bots = [], []
        if b - a >= 6:
            seg = v[order2[a:b]]
            aw = np.abs(seg[:, 1]) / max(wmax, 1e-6)
            for l0, l1 in zip(lanes, lanes[1:]):
                m = (aw >= l0) & (aw < l1)
                if m.sum() < 5:
                    tops.append(None)
                    bots.append(None)
                    continue
                z = seg[m, 2]
                tops.append(round(float(np.percentile(z, 96.0)), 2))
                bots.append(round(float(np.percentile(z, 4.0)), 2))
        else:
            tops = [None] * (len(lanes) - 1)
            bots = [None] * (len(lanes) - 1)
        lane_top.append(tops)
        lane_bot.append(bots)
    return {
        "x0": round(x0, 3), "dx": dx, "nx": nx,
        "z0": round(z0, 3), "dz": dz, "nz": nz,
        "wmax": round(wmax, 3),
        "right": right, "left": left,
        "lane_edges": lanes, "lane_top": lane_top, "lane_bot": lane_bot,
        "bounds": {"min": [round(float(c), 3) for c in v.min(axis=0)], "max": [round(float(c), 3) for c in v.max(axis=0)]},
        "vertices": int(len(v)),
    }


def main() -> None:
    src = arg("--src", os.path.join(ROOT, "art", "export", "ships_v3"))
    if not os.path.isdir(src):
        # a helper's worktree has no exports (they are not in git): the main checkout's are the same files
        alt = "/Users/beltromatti/Desktop/ASTRA/art/export/ships_v3"
        src = alt if os.path.isdir(alt) else src
    out = arg("--out", os.path.join(ROOT, "data", "ship", "plans", "hulls"))
    only = [s for s in arg("--only", "").split(",") if s]
    os.makedirs(out, exist_ok=True)
    for key, (mesh, dx, dz) in SHIPS.items():
        if only and key not in only:
            continue
        t0 = time.time()
        path = os.path.join(src, mesh + ".fbx")
        if not os.path.isfile(path):
            print(f"[probe] {key}: {path} is missing")
            continue
        v = load_vertices(path)
        hist_dir = arg("--hist", "")
        if hist_dir:
            # (a look at the shape: vertex counts over the side view (x, z) and the top view (x, y), for a picture; not part of the profile)
            os.makedirs(hist_dir, exist_ok=True)
            hx = np.arange(v[:, 0].min(), v[:, 0].max() + 2.0, 2.0)
            hz = np.arange(v[:, 2].min(), v[:, 2].max() + 2.0, 2.0)
            hy = np.arange(v[:, 1].min(), v[:, 1].max() + 2.0, 2.0)
            side, _, _ = np.histogram2d(v[:, 0], v[:, 2], bins=[hx, hz])
            top, _, _ = np.histogram2d(v[:, 0], v[:, 1], bins=[hx, hy])
            np.savez_compressed(os.path.join(hist_dir, key + "_hist.npz"), side=side, top=top, hx=hx, hz=hz, hy=hy)
        prof = probe(v, dx, dz)
        prof["class"] = key
        prof["mesh"] = mesh
        prof["frame"] = "the mesh's own (Unreal: X to the bow, Y to starboard, Z up, metres): right[i][k] = how far the skin stands to starboard at station x0 + i*dx, band z0 + k*dz; left[i][k] to port"
        p = os.path.join(out, key + ".json")
        with open(p, "w") as f:
            json.dump(prof, f, separators=(",", ":"))
        print(f"[probe] {key}: {len(v)} vertices, {prof['nx']} stations x {prof['nz']} bands -> {p} ({os.path.getsize(p) // 1024} KB, {time.time() - t0:.1f} s)")


main()
