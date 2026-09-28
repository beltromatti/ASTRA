"""New Ravenna, the coast at Port Aurelius: the ground the Captain flies over and lands on.

A procedural coastline (a wide bay opening to the south, headlands with cliffs, a beach in the bay, hills and a snowy
range inland, islands offshore), eroded, with a plateau for the spaceport (Port Aurelius Field) and the gentle slope
where the city climbs from the shore. Built as Nanite mesh tiles:

  SM_NR_Core_<i>_<j>   the 12 x 12 km around the port, 8 m spacing, 4 x 4 tiles of 3 km (skirted edges)
  SM_NR_Far            64 x 64 km at 100 m, a little lower where the core covers it
  nr_sites.json        where things stand: the field, the city blocks (x, y, ground z), sea level

Frame: metres, +X east, +Y north, +Z up, origin on the shore of the bay, sea level at z = 0. The core's outer 400 m
blends into the far terrain's surface, so the two meet without a step.

Run: blender -b --factory-startup --python-exit-code 1 -P art/blender/terrain.py -- art/export/newravenna [--preview <dir>]
"""
from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import bpy  # noqa: E402

CORE_HALF = 6000.0          # the core spans -6..6 km
CORE_STEP = 8.0
TILES = 4
FAR_HALF = 32000.0
FAR_STEP = 100.0
BLEND = 400.0               # the core's edge band that meets the far terrain
FIELD = (1800.0, 1400.0, 36.0, 700.0, 420.0)   # spaceport plateau: centre x, y, height, half length (x), half width (y)
SEED = 2491


# ------------------------------------------------------------------------------------------------ noise
class Noise:
    """Gradient-free value noise with smooth interpolation, vectorised (numpy), periodic hashing by lattice."""

    def __init__(self, seed: int):
        rng = np.random.default_rng(seed)
        self.perm = rng.permutation(4096).astype(np.int64)
        self.vals = rng.random(4096)

    def _h(self, ix, iy):
        return self.vals[(self.perm[(ix * 73856093) & 4095] ^ (iy * 19349663)) & 4095]

    def value(self, x, y):
        ix, iy = np.floor(x).astype(np.int64), np.floor(y).astype(np.int64)
        fx, fy = x - ix, y - iy
        ux, uy = fx * fx * fx * (fx * (fx * 6 - 15) + 10), fy * fy * fy * (fy * (fy * 6 - 15) + 10)
        a, b = self._h(ix, iy), self._h(ix + 1, iy)
        c, d = self._h(ix, iy + 1), self._h(ix + 1, iy + 1)
        return (a + (b - a) * ux) + ((c + (d - c) * ux) - (a + (b - a) * ux)) * uy

    def fbm(self, x, y, octaves=6, lac=2.03, gain=0.5):
        v = np.zeros_like(x)
        a, f = 0.5, 1.0
        for o in range(octaves):
            v += a * (self.value(x * f + o * 17.3, y * f - o * 9.1) * 2 - 1)
            f *= lac
            a *= gain
        return v

    def ridged(self, x, y, octaves=6):
        v = np.zeros_like(x)
        a, f, w = 0.5, 1.0, 1.0
        for o in range(octaves):
            n = 1.0 - np.abs(self.value(x * f + o * 31.7, y * f + o * 7.7) * 2 - 1)
            n = n * n * w
            w = np.clip(n * 2.0, 0, 1)
            v += a * n
            f *= 2.1
            a *= 0.5
        return v


N = Noise(SEED)


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def height(x: np.ndarray, y: np.ndarray, detail: bool = True, field: bool = True) -> np.ndarray:
    """The ground at (x, y) metres. detail=False gives the far terrain's gentler surface (no small features);
    field=False leaves the spaceport's plateau out (its level is the natural ground's at its centre)."""
    # the coastline: land to the north; the bay opens south around the origin, its arms (headlands) reach 3 km
    # further south some 6 km east and west
    wx = x + 500 * N.fbm(x / 7000, y / 7000 + 3, 4)
    wy = y + 500 * N.fbm(x / 7000 + 5, y / 7000, 4)
    coast = -3000 * (1 - np.exp(-((wx / 5000) ** 2))) + 260 * N.fbm(wx / 2500, np.full_like(wx, 1.7), 4)
    d = wy - coast                                   # metres inland (negative: at sea)
    inland = smooth(-300, 16000, d)
    base = 6 + 150 * smooth(0, 2800, d) + 420 * inland ** 1.3 + 180 * inland * N.fbm(wx / 6000, wy / 6000, 5)
    hills = 230 * smooth(150, 2600, d) * (N.fbm(wx / 2300, wy / 2300, 6 if detail else 3) + 0.35)
    mountains = 2100 * smooth(9000, 22000, d) * N.ridged(wx / 9000 + 4, wy / 9000, 7 if detail else 4)
    land = base + hills + mountains
    # headlands with cliffs: where the coast bulges, the land rises sharply from the water
    headland = smooth(0.1, 0.45, N.fbm(wx / 4200 + 9, wy / 4200, 3)) * smooth(-150, 250, d) * (1 - smooth(1500, 4500, d))
    land += headland * 70 * smooth(0, 120, d)
    # the beach in the bay: flat sand near the water
    beach = np.exp(-((wx / 2600) ** 2)) * (1 - smooth(0, 220, d))
    land = land * (1 - 0.8 * beach) + 2.5 * beach
    # the sea floor: shelving down offshore
    sea = -8 - 120 * smooth(0, 9000, -d) + 25 * N.fbm(x / 3000, y / 3000, 4)
    h = np.where(d > 0, land * smooth(0, 60, d) + (-3.0) * (1 - smooth(0, 60, d)), sea * smooth(0, 200, -d) + (-3.0) * (1 - smooth(0, 200, -d)))
    # islands offshore
    for (ix, iy, r, hi) in ((-7500, -9500, 1700, 380), (5200, -12500, 2400, 520), (13000, -6500, 1200, 240), (-15000, -4000, 2600, 610)):
        rr = np.sqrt((x - ix) ** 2 + (y - iy) ** 2) / r
        isl = np.clip(1 - rr * rr, 0, 1) ** 1.6 * (hi + 90 * N.fbm(x / 900, y / 900, 5 if detail else 2))
        h = np.maximum(h, np.where(rr < 1.2, isl - 4 * (1 - np.clip(1 - rr, 0, 1)), h))
    if detail:
        h += 3.5 * N.fbm(x / 140, y / 140, 4) * smooth(2, 30, h) + 0.8 * N.fbm(x / 35, y / 35, 3) * smooth(1, 10, h)
    # the spaceport's plateau: graded at the natural ground's level (the mean over its area), blending out gently
    if field:
        fx, fy, _, hl, hw = FIELD
        gx, gy = np.meshgrid(np.linspace(fx - hl, fx + hl, 9), np.linspace(fy - hw, fy + hw, 7))
        fz = float(np.mean(height(gx, gy, detail, field=False)))
        q = np.maximum(np.abs(x - fx) / hl, np.abs(y - fy) / hw)
        h = h * smooth(0.95, 1.9, q) + fz * (1 - smooth(0.95, 1.9, q))
    return h


def field_level() -> float:
    fx, fy, _, hl, hw = FIELD
    gx, gy = np.meshgrid(np.linspace(fx - hl, fx + hl, 9), np.linspace(fy - hw, fy + hw, 7))
    return float(np.mean(height(gx, gy, True, field=False)))


def erode(h: np.ndarray, cell: float, iterations: int = 40, talus: float = 0.9) -> np.ndarray:
    """Thermal erosion: material slides down wherever a slope is steeper than the talus angle (tan), carving scree
    and softening peaks the way wind and frost do (vectorised, 4 neighbours)."""
    h = h.copy()
    for _ in range(iterations):
        moved = np.zeros_like(h)
        for dy, dx in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            nb = np.roll(np.roll(h, dy, 0), dx, 1)
            diff = h - nb - talus * cell
            m = np.where(diff > 0, diff * 0.12, 0.0)
            moved -= m
            moved += np.roll(np.roll(m, -dy, 0), -dx, 1)
        h += moved
    return h


# ------------------------------------------------------------------------------------------------ meshes
def grid_mesh(name: str, xs: np.ndarray, ys: np.ndarray, hz: np.ndarray, skirt: float = 0.0):
    """A regular grid (rows = y, cols = x) as one mesh; optional skirts hanging from the four edges."""
    ny, nx = hz.shape
    X, Y = np.meshgrid(xs, ys)
    verts = np.stack([X.ravel(), Y.ravel(), hz.ravel()], 1)
    i = np.arange(ny * nx).reshape(ny, nx)
    a, b, c, d = i[:-1, :-1].ravel(), i[:-1, 1:].ravel(), i[1:, 1:].ravel(), i[1:, :-1].ravel()
    quads = [np.stack([a, b, c, d], 1)]
    if skirt > 0:
        edges = [i[0, :], i[:, -1], i[-1, ::-1], i[::-1, 0]]
        base = len(verts)
        extra = []
        for e in edges:
            top = verts[e].copy()
            bot = top.copy()
            bot[:, 2] -= skirt
            it = np.arange(base, base + len(e))
            ib = np.arange(base + len(e), base + 2 * len(e))
            extra += [top, bot]
            quads.append(np.stack([it[:-1], ib[:-1], ib[1:], it[1:]], 1))
            base += 2 * len(e)
        verts = np.concatenate([verts] + extra, 0)
    quads = np.concatenate(quads, 0)
    me = bpy.data.meshes.new(name)
    me.vertices.add(len(verts))
    me.vertices.foreach_set("co", verts.astype(np.float32).ravel())
    me.loops.add(len(quads) * 4)
    me.loops.foreach_set("vertex_index", quads.astype(np.int32).ravel())
    me.polygons.add(len(quads))
    me.polygons.foreach_set("loop_start", (np.arange(len(quads)) * 4).astype(np.int32))
    me.polygons.foreach_set("loop_total", np.full(len(quads), 4, np.int32))
    me.update(calc_edges=True)
    me.validate()
    # planar UVs (1 unit = 100 m): the material works in world space; the engine wants a channel anyway
    uv = me.uv_layers.new(name="UVMap")
    loop_v = np.empty(len(me.loops), np.int32)
    me.loops.foreach_get("vertex_index", loop_v)
    uv.data.foreach_set("uv", (verts[loop_v][:, :2] / 100.0).astype(np.float32).ravel())
    me.polygons.foreach_set("use_smooth", np.ones(len(quads), bool))
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    mat = A.material("MI_NR_Terrain")
    me.materials.append(mat)
    return ob


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[0] if argv else "art/export/newravenna"
    preview = argv[argv.index("--preview") + 1] if "--preview" in argv else None
    os.makedirs(out, exist_ok=True)
    A.reset_scene()
    A.clear_objects()
    # --- far terrain (the gentle surface, also what the core's edge blends into)
    fx = np.arange(-FAR_HALF, FAR_HALF + 1, FAR_STEP)
    FX, FY = np.meshgrid(fx, fx)
    far = height(FX, FY, detail=False)
    far = erode(far, FAR_STEP, 20, 1.2)

    def far_at(x, y):
        """Bilinear sample of the far grid (what its triangles show)."""
        gx = (x + FAR_HALF) / FAR_STEP
        gy = (y + FAR_HALF) / FAR_STEP
        x0 = np.clip(np.floor(gx).astype(int), 0, len(fx) - 2)
        y0 = np.clip(np.floor(gy).astype(int), 0, len(fx) - 2)
        tx, ty = gx - x0, gy - y0
        return (far[y0, x0] * (1 - tx) * (1 - ty) + far[y0, x0 + 1] * tx * (1 - ty) + far[y0 + 1, x0] * (1 - tx) * ty
                + far[y0 + 1, x0 + 1] * tx * ty)

    # under the core the far surface drops 25 m out of sight (the core's skirts close the gap)
    under = (np.abs(FX) < CORE_HALF - 50) & (np.abs(FY) < CORE_HALF - 50)
    far_mesh = np.where(under, far - 25.0, far)
    objs = [grid_mesh("SM_NR_Far", fx, fx, far_mesh)]
    # --- the core, eroded, blended into the far surface at its edge
    cx = np.arange(-CORE_HALF, CORE_HALF + 1, CORE_STEP)
    CX, CY = np.meshgrid(cx, cx)
    core = erode(height(CX, CY, True), CORE_STEP, 45, 0.85)
    edge = np.minimum(CORE_HALF - np.abs(CX), CORE_HALF - np.abs(CY))
    w = smooth(0, BLEND, edge)
    core = core * w + far_at(CX, CY) * (1 - w)
    n = (len(cx) - 1) // TILES
    for ti in range(TILES):
        for tj in range(TILES):
            sl = (slice(tj * n, tj * n + n + 1), slice(ti * n, ti * n + n + 1))
            objs.append(grid_mesh(f"SM_NR_Core_{ti}_{tj}", cx[sl[1]], cx[sl[0]], core[sl], skirt=40.0))
    for ob in objs:
        A.export_fbx(ob, os.path.join(out, ob.name + ".fbx"))
    # --- where things stand
    rng = np.random.default_rng(SEED)
    blocks = []
    for _ in range(420):
        # the city climbs from the bay's shore up the gentle slope west of the field
        x = rng.normal(-1200, 1500)
        y = rng.normal(900, 600)
        if abs(x - FIELD[0]) < FIELD[3] + 250 and abs(y - FIELD[1]) < FIELD[4] + 250:
            continue
        gi, gj = int((y + CORE_HALF) / CORE_STEP), int((x + CORE_HALF) / CORE_STEP)
        if not (0 <= gi < len(cx) and 0 <= gj < len(cx)):
            continue
        z = float(core[gi, gj])
        slope = float(np.hypot(core[gi, min(gj + 1, len(cx) - 1)] - core[gi, gj], core[min(gi + 1, len(cx) - 1), gj] - core[gi, gj])) / CORE_STEP
        if z < 3.0 or z > 220 or slope > 0.25:
            continue
        near = math.exp(-(((x + 1200) / 1300) ** 2 + ((y - 700) / 500) ** 2))       # taller towards the centre
        blocks.append({"x": round(x, 1), "y": round(y, 1), "z": round(z, 2), "w": round(float(rng.uniform(18, 46)), 1),
                       "d": round(float(rng.uniform(18, 46)), 1), "h": round(float(12 + rng.gamma(2.0, 14) + 160 * near * rng.random()), 1),
                       "yaw": round(float(rng.choice([0, 0, 15, -12, 30])), 1)})
    fz = float(core[int((FIELD[1] + CORE_HALF) / CORE_STEP), int((FIELD[0] + CORE_HALF) / CORE_STEP)])
    sites = {"sea_level": 0.0, "field": {"x": FIELD[0], "y": FIELD[1], "z": round(fz, 2), "half_x": FIELD[3], "half_y": FIELD[4]},
             "city": blocks, "core_half": CORE_HALF, "far_half": FAR_HALF}
    with open(os.path.join(out, "nr_sites.json"), "w", encoding="utf-8") as f:
        json.dump(sites, f)
    # a heightmap picture of the core for eyes (and the report)
    img = np.clip((core + 150) / 1200.0, 0, 1)
    rgb = np.dstack([img, img, img])
    rgb[core < 0] = [0.05, 0.15, 0.3]
    print("TERRAIN_OK", json.dumps({"core_min": float(core.min()), "core_max": float(core.max()), "far_max": float(far.max()),
                                    "blocks": len(blocks), "tiles": len(objs)}))
    if preview:
        os.makedirs(preview, exist_ok=True)
        small = rgb[::4, ::4]
        im = bpy.data.images.new("hm", width=small.shape[1], height=small.shape[0])
        im.pixels.foreach_set(np.dstack([small, np.ones(small.shape[:2])]).astype(np.float32).ravel())
        im.filepath_raw = os.path.join(preview, "nr_core_heightmap.png")
        im.file_format = "PNG"
        im.save()


if __name__ == "__main__":
    main()
