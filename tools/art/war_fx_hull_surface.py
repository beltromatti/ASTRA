"""Where the skin of every hull is, seen from each face of its box, for the war's visual effects (AstraWarFX).

The simulation knows a ship as a box (docs/GUERRA.md): a blow lands on one of its faces, a fire is set on its surface. The mesh is not the box: a cruiser with a tower is 149 m tall and
its deck is forty metres under the top of the box, so a flash, a fire, a glow or a scar put on the face of the box hung in the air above the ship (5 Oct, in the main viewscreen). This
tool builds every ship with the generators (art/blender/shipgen3.py, almost no scattered detail: nothing is exported, about a minute for all) and, from the vertices of the hull as
the game sees it, records for each of the six faces of the box a coarse grid of how far the skin is from it:

  top / bottom      over (x, y): the z of the outermost skin seen from above / below
  starboard / port  over (x, z): the y of the outermost skin seen from the right / left
  bow / stern       over (y, z): the x of the outermost skin seen from ahead / astern

in the ship's own frame as the game sees it (x forward, y starboard, z up: the FBX export mirrors Blender's y, so y is negated here), metres, the mesh's origin at the origin. Each
cell keeps a robust extreme (a high percentile of its vertices, so that a mast does not make a cell as tall as the mast) and a cell with nothing in it takes its nearest neighbour's.
It writes data/war/fx_hull_surface.json; tools/art/war_fx_data.py turns it into Source/ASTRA/AstraWarFXSurface.inl, which the game compiles in (AstraWarFXHull.cpp: SnapToHull).

  /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python-exit-code 1 -P tools/art/war_fx_hull_surface.py [-- --only SM_SHIP_MANDATE_Acheron ...]
  (or blender -b ... with the Homebrew Blender)

The ships' own tables (the sizes of the grid, the percentile) are the constants below.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "art", "blender"))

import bpy  # noqa: E402,F401  (the generators import it)
import numpy as np  # noqa: E402

import shipgen3 as SG  # noqa: E402

OUT = os.path.join(ROOT, "data", "war", "fx_hull_surface.json")
NX, NY, NZ = 48, 16, 16        # cells along the ship, across it, up it
PCT = 97.0                     # the percentile of a cell's vertices that stands for its skin
MIN_VERTS = 3                  # fewer than this in a cell: it is empty (it takes its neighbour's)


def fill_empty(g: np.ndarray) -> np.ndarray:
    """Cells that are NaN take the value of the nearest cell that has one (a few passes of the four neighbours, then the mean)."""
    g = g.copy()
    for _ in range(max(g.shape)):
        nan = np.isnan(g)
        if not nan.any():
            return g
        pad = np.pad(g, 1, constant_values=np.nan)
        stack = np.stack([pad[:-2, 1:-1], pad[2:, 1:-1], pad[1:-1, :-2], pad[1:-1, 2:]])
        with np.errstate(all="ignore"):
            nb = np.nanmean(stack, axis=0)
        g[nan] = nb[nan]
    g[np.isnan(g)] = np.nanmean(g) if not np.isnan(g).all() else 0.0
    return g


def face_grid(a: np.ndarray, b: np.ndarray, c: np.ndarray, na: int, nb: int, lo: tuple[float, float], hi: tuple[float, float], want_max: bool) -> np.ndarray:
    """The skin seen from one face: points (a, b, c); the grid is over (a, b), the value is the robust extreme of c in each cell (the high percentile for the +c face, the low one for -c)."""
    ia = np.clip(((a - lo[0]) / (hi[0] - lo[0]) * na).astype(np.int64), 0, na - 1)
    ib = np.clip(((b - lo[1]) / (hi[1] - lo[1]) * nb).astype(np.int64), 0, nb - 1)
    cell = ia * nb + ib
    order = np.argsort(cell, kind="stable")
    cs, cc = cell[order], c[order]
    bounds = np.searchsorted(cs, np.arange(na * nb + 1))
    g = np.full(na * nb, np.nan)
    for k in range(na * nb):
        s, e = bounds[k], bounds[k + 1]
        if e - s >= MIN_VERTS:
            g[k] = np.percentile(cc[s:e], PCT if want_max else 100.0 - PCT)
    return fill_empty(g.reshape(na, nb))


def surface_of(V: np.ndarray) -> dict:
    """V: the hull's vertices (Blender frame, metres). The six grids, in the game's frame."""
    P = np.stack([V[:, 0], -V[:, 1], V[:, 2]], axis=1).astype(np.float64)       # x forward, y starboard, z up
    lo, hi = P.min(axis=0), P.max(axis=0)
    pad = 0.002 * (hi - lo)
    lo, hi = lo - pad, hi + pad
    x, y, z = P[:, 0], P[:, 1], P[:, 2]
    top = face_grid(x, y, z, NX, NY, (lo[0], lo[1]), (hi[0], hi[1]), True)
    bottom = face_grid(x, y, z, NX, NY, (lo[0], lo[1]), (hi[0], hi[1]), False)
    starboard = face_grid(x, z, y, NX, NZ, (lo[0], lo[2]), (hi[0], hi[2]), True)
    port = face_grid(x, z, y, NX, NZ, (lo[0], lo[2]), (hi[0], hi[2]), False)
    bow = face_grid(y, z, x, NY, NZ, (lo[1], lo[2]), (hi[1], hi[2]), True)
    stern = face_grid(y, z, x, NY, NZ, (lo[1], lo[2]), (hi[1], hi[2]), False)

    def cm(g: np.ndarray) -> list[int]:
        return [int(round(v * 100.0)) for v in g.reshape(-1)]

    return {"bounds_m": [round(float(v), 3) for v in (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2])], "nx": NX, "ny": NY, "nz": NZ,
            "top": cm(top), "bottom": cm(bottom), "starboard": cm(starboard), "port": cm(port), "bow": cm(bow), "stern": cm(stern), "verts": int(len(V))}


def main() -> None:
    only = []
    if "--" in sys.argv:
        rest = sys.argv[sys.argv.index("--") + 1:]
        if rest and rest[0] == "--only":
            only = rest[1:]
    reg = SG.registry()
    args = {"seed": 0, "detail": 0.02, "export": False, "pieces": False}
    result: dict = {}
    if only and os.path.exists(OUT):
        with open(OUT, encoding="utf-8") as fh:
            result = json.load(fh).get("ships", {})             # (the others stay as they were)
    for name, spec in reg.items():
        if only and name not in only and SG.short(name) not in only:
            continue
        if spec.get("cls") == "craft":
            continue                                             # (a craft has no box to snap to)
        try:
            res = SG.build_ship(name, spec, args)
            asm = res["g"].assemble()
            result[name] = surface_of(np.asarray(asm["V"], np.float64))
        except Exception as ex:                                  # one ship failing must not lose the others
            print(f"{name}: FAILED {ex!r}")
            continue
        s = result[name]
        b = s["bounds_m"]
        print(f"{name}: {s['verts']} vertices, bounds x [{b[0]:.1f}, {b[1]:.1f}] y [{b[2]:.1f}, {b[3]:.1f}] z [{b[4]:.1f}, {b[5]:.1f}] m; top {min(s['top']) / 100:.1f}..{max(s['top']) / 100:.1f}")
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"_doc": "How far the skin of each hull is from each face of its box: grids of the outermost skin seen from the six faces (cm, ship frame: x forward, y starboard, z up); "
                           "tools/art/war_fx_hull_surface.py", "ships": result}, fh, indent=None, separators=(",", ":"))
    print("written", OUT)
    print("WAR_FX_HULL_SURFACE_OK")


if __name__ == "__main__":
    main()
