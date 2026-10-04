"""SPAZIO-VIVO — the solid parts of the places' hulls, as boxes (docs/SPAZIO.md): data/space/solids.json.

The Captain's Falcon flies into a ship's hull and is lost (the battle's PilotCollision); the places of the system (Keeper Station, the Arsenal, the refinery, the mine) are fixtures in the plot
and must be as solid as a ship, but their meshes are mostly air (a ring, bays, piers, cranes): the bounding box of the mesh is no hull. This makes each place's hull from its own mesh, the way
the game draws it: the surface is sampled finely, the cells it touches are marked (a voxel grid in the mesh's frame), what is closed inside is filled, and the cells are merged into the fewest
boxes (runs along x, joined across y, joined across z). Open bays stay open (they are reachable from outside), a ring's hole stays a hole, a closed hull is solid. The game tests a point against
the boxes (a few thousand, in a coarse grid of buckets): a Falcon that is inside one has flown into the place.

The grid's cell is a fraction of the mesh's size (3 to 12 m: the Falcon is a dozen metres long, so the hull is true to a few metres) and is made coarser until the boxes are within the budget.
The parts that turn (the Keeper's ring, the Arsenal's cranes) have their own boxes, in their own frame (the part mesh's origin is its pivot), which the game turns as it draws them.

Usage (headless Blender; the generators need bpy, the rest is numpy):
  blender -b --factory-startup --python-exit-code 1 -P art/blender/space3_solids.py -- [--out data/space/solids.json] [--only keeper,arsenal] [--budget 6000] [--detail 0.3]
Then  tools/space.py sync  stages the file for the game, and tools/art/solids_plot.py draws it.
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)

import bpy  # noqa: E402,F401  (the generators import it)

import spacegen3 as SP  # noqa: E402

MESHES = ["SM_PLACE_Keeper", "SM_PLACE_KeeperRing", "SM_PLACE_Arsenal", "SM_PART_ArsenalCrane", "SM_PLACE_Refinery", "SM_PLACE_Mine"]


def rasterise(V: np.ndarray, F: np.ndarray, origin: np.ndarray, cell: float, shape: tuple[int, int, int]) -> np.ndarray:
    """The cells a mesh's surface touches: every triangle sampled on a barycentric grid finer than the cell (so that no cell it crosses is missed)."""
    occ = np.zeros(shape, bool)
    T = V[F]
    edge = np.maximum.reduce([np.linalg.norm(T[:, 1] - T[:, 0], axis=1), np.linalg.norm(T[:, 2] - T[:, 1], axis=1), np.linalg.norm(T[:, 0] - T[:, 2], axis=1)])
    nsub = np.clip(np.ceil(edge / (0.45 * cell)).astype(np.int64), 1, 400)
    hi = np.array(shape) - 1
    for n in np.unique(nsub):
        idx = np.nonzero(nsub == n)[0]
        bary = np.array([(i / n, j / n, 1.0 - (i + j) / n) for i in range(n + 1) for j in range(n + 1 - i)])
        per = max(1, int(1_500_000 // len(bary)))
        for s in range(0, len(idx), per):
            t = T[idx[s:s + per]]
            P = np.einsum("kb,tbc->tkc", bary, t).reshape(-1, 3)
            c = np.floor((P - origin) / cell).astype(np.int64)
            c = np.clip(c, 0, hi)
            occ[c[:, 0], c[:, 1], c[:, 2]] = True
    return occ


def fill(occ: np.ndarray) -> np.ndarray:
    """Solid = everything the outside cannot reach: the exterior is grown from a corner through the empty cells (6-connected) until it stops."""
    pad = np.zeros(tuple(s + 2 for s in occ.shape), bool)
    pad[1:-1, 1:-1, 1:-1] = occ
    out = np.zeros_like(pad)
    out[0, 0, 0] = True
    count = 1
    while True:
        g = out.copy()
        g[1:] |= out[:-1]
        g[:-1] |= out[1:]
        g[:, 1:] |= out[:, :-1]
        g[:, :-1] |= out[:, 1:]
        g[:, :, 1:] |= out[:, :, :-1]
        g[:, :, :-1] |= out[:, :, 1:]
        g &= ~pad
        n = int(g.sum())
        if n == count:
            break
        count = n
        out = g
    return ~out[1:-1, 1:-1, 1:-1]


def merge(solid: np.ndarray) -> list[list[int]]:
    """Cells to boxes: runs along x, equal runs on neighbouring y joined, equal rectangles on neighbouring z joined. [x0, y0, z0, dx, dy, dz] in cells."""
    nx, ny, nz = solid.shape
    pad = np.zeros((nx + 2, ny, nz), np.int8)
    pad[1:-1] = solid
    d = np.diff(pad, axis=0)
    st = np.argwhere(d == 1)                      # (x of the first solid cell, y, z)
    en = np.argwhere(d == -1)                     # (x one past the last, y, z)
    key = lambda a: np.lexsort((a[:, 0], a[:, 1], a[:, 2]))  # noqa: E731
    st, en = st[key(st)], en[key(en)]
    by_z: dict[int, list[tuple[int, int, int]]] = {}
    for (x0, y, z), (x1, _, _) in zip(st.tolist(), en.tolist()):
        by_z.setdefault(z, []).append((y, x0, x1))
    plates: list[tuple[int, int, int, int, int, int]] = []                                  # (x0, x1, y0, y1, z, 1): rectangles in one z layer
    for z, runs in by_z.items():
        runs.sort(key=lambda r: (r[1], r[2], r[0]))
        cur = None
        for y, x0, x1 in runs:
            if cur and cur[0] == x0 and cur[1] == x1 and cur[3] == y:
                cur[3] = y + 1
            else:
                if cur:
                    plates.append((cur[0], cur[1], cur[2], cur[3], z, 1))
                cur = [x0, x1, y, y + 1]
        if cur:
            plates.append((cur[0], cur[1], cur[2], cur[3], z, 1))
    plates.sort(key=lambda p: (p[0], p[1], p[2], p[3], p[4]))
    boxes: list[list[int]] = []
    cur = None
    for x0, x1, y0, y1, z, _ in plates:
        if cur and cur[0] == x0 and cur[1] == x1 and cur[2] == y0 and cur[3] == y1 and cur[5] == z:
            cur[5] = z + 1
        else:
            if cur:
                boxes.append([cur[0], cur[2], cur[4], cur[1] - cur[0], cur[3] - cur[2], cur[5] - cur[4]])
            cur = [x0, x1, y0, y1, z, z + 1]
    if cur:
        boxes.append([cur[0], cur[2], cur[4], cur[1] - cur[0], cur[3] - cur[2], cur[5] - cur[4]])
    return boxes


def solids_of(name: str, spec: dict, args: dict) -> dict:
    t0 = time.time()
    res = SP.build_mesh(name, spec, {"seed": 0, "detail": args["detail"]})
    asm = res["g"].assemble()
    V = np.asarray(asm["V"], np.float64) * np.array([1.0, -1.0, 1.0])            # the Unreal frame (the FBX export mirrors y)
    F = np.asarray(asm["F"], np.int64)
    lo, hi = V.min(axis=0), V.max(axis=0)
    size = float((hi - lo).max())
    cell = float(np.clip(size / 260.0, 3.0, 12.0))
    note = ""
    for attempt in range(8):
        origin = lo - cell
        shape = tuple(int(math.ceil(s)) + 2 for s in ((hi - origin) / cell + 1))
        occ = rasterise(V, F, origin, cell, shape)
        solid = fill(occ)
        boxes = merge(solid)
        if len(boxes) <= args["budget"]:
            break
        note = f" (coarsened to {cell * 1.25:.1f} m: {len(boxes)} boxes were over the budget)"
        cell *= 1.25
    vol = float(solid.sum()) * cell ** 3
    print(f"{name}: {len(V):,} vertices, {len(F):,} triangles, {size:.0f} m; cell {cell:.1f} m, grid {shape}, {int(occ.sum()):,} surface cells, {int(solid.sum()):,} solid -> {len(boxes)} boxes{note}; "
          f"{time.time() - t0:.1f} s")
    return {"cell": round(cell, 3), "origin": [round(float(x), 3) for x in origin], "size": [round(float(x), 1) for x in (hi - lo)], "tris": int(len(F)), "boxes": boxes}


def parse_args() -> dict:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    a = {"out": os.path.join(ROOT, "data", "space", "solids.json"), "only": [], "budget": 6000, "detail": 0.3}
    i = 0
    while i < len(argv):
        k = argv[i]
        if k == "--out":
            a["out"] = argv[i + 1]
            i += 1
        elif k == "--only":
            a["only"] = argv[i + 1].split(",")
            i += 1
        elif k == "--budget":
            a["budget"] = int(argv[i + 1])
            i += 1
        elif k == "--detail":
            a["detail"] = float(argv[i + 1])
            i += 1
        i += 1
    return a


def main() -> None:
    a = parse_args()
    reg = SP.registry()
    names = [n for n in MESHES if n in reg and (not a["only"] or n in a["only"] or SP.short(n) in a["only"] or n.split("_", 2)[-1].lower() in a["only"])]
    out = {"_doc": "The solid parts of the places' hulls as boxes: cells of `cell` metres on a grid from `origin` (the mesh's frame, Unreal: x forward, y starboard, z up); a box is [x0, y0, z0, dx, dy, dz] in cells. "
                   "art/blender/space3_solids.py", "version": 1, "meshes": {}}
    if os.path.exists(a["out"]) and a["only"]:
        out["meshes"].update(json.load(open(a["out"], encoding="utf-8")).get("meshes", {}))
    for n in names:
        out["meshes"][n] = solids_of(n, reg[n], a)
    os.makedirs(os.path.dirname(a["out"]), exist_ok=True)
    with open(a["out"], "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print("written", a["out"], f"{os.path.getsize(a['out']) / 1024:.0f} KB")
    print("SOLIDS_OK")


if __name__ == "__main__":
    main()
