"""SPAZIO-VIVO — the solid parts of the places' hulls, as boxes (docs/SPAZIO.md): data/space/solids.json.

The Captain's Falcon flies into a ship's hull and is lost (the battle's PilotCollision); the places of the system (Keeper Station, the Arsenal, the refinery, the mine) are fixtures in the plot
and must be as solid as a ship, but their meshes are mostly air (a ring, bays, piers, cranes): the bounding box of the mesh is no hull. This makes each place's hull from its own mesh, the way
the game draws it: the surface is sampled finely, the cells it touches are marked (a voxel grid in the mesh's frame), what is closed inside is filled, and the cells are merged into the fewest
boxes (runs along x, joined across y, joined across z). Open bays stay open (they are reachable from outside), a ring's hole stays a hole, a closed hull is solid. The game tests a point against
the boxes (a few thousand, in a coarse grid of buckets): a Falcon that is inside one has flown into the place.

The grid's cell is a fraction of the mesh's size (3 to 12 m: the Falcon is a dozen metres long, so the hull is true to a few metres) and is made coarser until the boxes are within the budget.
The parts that turn (the Keeper's ring, the Arsenal's cranes) have their own boxes, in their own frame (the part mesh's origin is its pivot), which the game turns as it draws them.

The wrecks of the war get the same: a ship that broke apart leaves three pieces (SM_SHIP_<fac>_<Name>_Sec<Bow|Mid|Stern>, the ship's own geometry between the cut planes with the burnt cut faces
on) and a ship that was only destroyed leaves her whole hull burnt dark (SM_SHIP_<fac>_<Name>); the Captain's Falcon is lost in them as in a place (AstraWrecks, UAstraSpaceLife::PilotHit). Their
meshes come from the ship generators (shipgen3, the same builds as the game's meshes) in the same frame as the whole ship, and a piece open at its torn end has its inside open too: the exterior reaches in
through the cut, so a Falcon that flies into a torn hull is in air until it meets a deck or a bulkhead.

Usage (headless Blender; the generators need bpy, the rest is numpy):
  blender -b --factory-startup --python-exit-code 1 -P art/blender/space3_solids.py -- [--out data/space/solids.json] [--only keeper,arsenal,vigilant] [--budget 6000] [--detail 0.3]
                                                                                       [--places | --ships] [--ship-budget 3500] [--ship-detail 0.3]
  (no --places or --ships: both; --only names a place (keeper, arsenal...) or a ship's short name (vigilant, acheron...) and keeps what is already in the file)
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

import shipgen3 as SG  # noqa: E402
import spacegen3 as SP  # noqa: E402

MESHES = ["SM_PLACE_Keeper", "SM_PLACE_KeeperRing", "SM_PLACE_Arsenal", "SM_PART_ArsenalCrane", "SM_PLACE_Refinery", "SM_PLACE_Mine"]
# the ships that leave wrecks (the Aquila's loss is the end of the story: she leaves none) and the Watch station, simply destroyed
SHIPS = ["SM_SHIP_ASTRA_Praetorian", "SM_SHIP_ASTRA_Vigilant", "SM_SHIP_MANDATE_Acheron", "SM_SHIP_MANDATE_Styx", "SM_SHIP_MANDATE_Lethe", "SM_SHIP_GUILD_Freighter", "SM_STATION_ASTRA_Watch"]
SEC_NAMES = ("Bow", "Mid", "Stern")


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


def solids_from(name: str, V: np.ndarray, F: np.ndarray, budget: int) -> dict:
    """One mesh's hull as boxes: V is in the Unreal frame (x forward, y starboard, z up), metres; the cell is a fraction of the mesh's size and is made coarser until the boxes are in the budget."""
    t0 = time.time()
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
        if len(boxes) <= budget:
            break
        note = f" (coarsened to {cell * 1.25:.1f} m: {len(boxes)} boxes were over the budget)"
        cell *= 1.25
    print(f"{name}: {len(V):,} vertices, {len(F):,} triangles, {size:.0f} m; cell {cell:.1f} m, grid {shape}, {int(occ.sum()):,} surface cells, {int(solid.sum()):,} solid -> {len(boxes)} boxes{note}; "
          f"{time.time() - t0:.1f} s")
    return {"cell": round(cell, 3), "origin": [round(float(x), 3) for x in origin], "size": [round(float(x), 1) for x in (hi - lo)], "tris": int(len(F)), "boxes": boxes}


def solids_of(name: str, spec: dict, args: dict) -> dict:
    """A place's hull, from its own mesh as the game draws it."""
    res = SP.build_mesh(name, spec, {"seed": 0, "detail": args["detail"]})
    asm = res["g"].assemble()
    V = np.asarray(asm["V"], np.float64) * np.array([1.0, -1.0, 1.0])            # the Unreal frame (the FBX export mirrors y)
    return solids_from(name, V, np.asarray(asm["F"], np.int64), args["budget"])


def ship_solids(name: str, spec: dict, args: dict) -> dict[str, dict]:
    """A ship's whole hull (what a ship that was only destroyed leaves, burnt dark) and, for a capital ship, her three pieces as the breakup leaves them: the meshes shipgen3 exports, in the same frame."""
    res = SG.build_ship(name, spec, {"seed": 0, "detail": args["ship_detail"], "export": False, "pieces": False})
    g, info = res["g"], res["info"]
    flip = np.array([1.0, -1.0, 1.0])
    out: dict[str, dict] = {}
    asm = g.assemble()
    out[name] = solids_from(name, np.asarray(asm["V"], np.float64) * flip, np.asarray(asm["F"], np.int64), args["ship_budget"])
    cuts = list(info.get("cuts") or [])
    if spec.get("sections") and cuts:
        section_of = lambda x, cu=cuts: np.where(x > cu[0], 0, np.where(x > cu[1], 1, 2)) if len(cu) == 2 else np.where(x > cu[0], 0, 1)  # noqa: E731
        for k in range(len(cuts) + 1):
            pa = g.assemble(sections={k}, include_caps=True, section_of=section_of)
            if pa is None:
                continue
            pname = f"{name}_Sec{SEC_NAMES[k] if len(cuts) == 2 else ('Bow', 'Stern')[k]}"
            out[pname] = solids_from(pname, np.asarray(pa["V"], np.float64) * flip, np.asarray(pa["F"], np.int64), args["ship_budget"])
    return out


def parse_args() -> dict:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    a = {"out": os.path.join(ROOT, "data", "space", "solids.json"), "only": [], "budget": 6000, "detail": 0.3, "ship_budget": 3500, "ship_detail": 0.3, "places": True, "ships": True}
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
        elif k == "--ship-budget":
            a["ship_budget"] = int(argv[i + 1])
            i += 1
        elif k == "--ship-detail":
            a["ship_detail"] = float(argv[i + 1])
            i += 1
        elif k == "--places":
            a["ships"] = False
        elif k == "--ships":
            a["places"] = False
        i += 1
    return a


def wanted(n: str, only: list[str], short: str) -> bool:
    return not only or n in only or short in only or short.lower() in [o.lower() for o in only]


def main() -> None:
    a = parse_args()
    reg = SP.registry()
    sreg = SG.registry()
    places = [n for n in MESHES if a["places"] and n in reg and wanted(n, a["only"], SP.short(n))]
    ships = [n for n in SHIPS if a["ships"] and n in sreg and wanted(n, a["only"], SG.short(n))]
    out = {"_doc": "The solid parts of the hulls as boxes: cells of `cell` metres on a grid from `origin` (the mesh's frame, Unreal: x forward, y starboard, z up); a box is [x0, y0, z0, dx, dy, dz] in cells. "
                   "The places (Keeper Station, the Arsenal...), and the wrecks of the war: the ships' whole hulls and their three pieces (_SecBow, _SecMid, _SecStern). art/blender/space3_solids.py", "version": 2, "meshes": {}}
    if os.path.exists(a["out"]) and (a["only"] or not (a["places"] and a["ships"])):
        out["meshes"].update(json.load(open(a["out"], encoding="utf-8")).get("meshes", {}))
    for n in places:
        out["meshes"][n] = solids_of(n, reg[n], a)
    for n in ships:
        out["meshes"].update(ship_solids(n, sreg[n], a))
    os.makedirs(os.path.dirname(a["out"]), exist_ok=True)
    with open(a["out"], "w", encoding="utf-8") as fh:
        json.dump(out, fh, separators=(",", ":"))
    print("written", a["out"], f"{os.path.getsize(a['out']) / 1024:.0f} KB, {len(out['meshes'])} meshes")
    print("SOLIDS_OK")


if __name__ == "__main__":
    main()
