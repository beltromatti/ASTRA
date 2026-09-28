"""Hard-surface kit for ASTRA's capital ships (v2): chamfered lofted blocks built as grids, plated with raised and
recessed armour panels, and the parts that make a warship read at a distance — towers, turrets with barrels, VLS
grids, lit hangar mouths, engine banks, radiator fin arrays, masts, window bands, running lights.

Everything works in metres along +X (bow), +Z up, on one bmesh (astra_bpy.Builder); material slots by name.
"""
from __future__ import annotations

import math
import random
from contextlib import contextmanager
from typing import Sequence

import bmesh
from mathutils import Matrix, Vector


@contextmanager
def part(b, matrix: Matrix):
    """Build a part in its own frame, then place it: geometry made inside the block goes to a scratch bmesh
    (same material table), is transformed by `matrix` and merged into the ship."""
    main = b.bm
    tmp = bmesh.new()
    b.bm = tmp
    try:
        yield
    finally:
        b.bm = main
        vmap = {v: main.verts.new(matrix @ v.co) for v in tmp.verts}
        for f in tmp.faces:
            nf = main.faces.new([vmap[v] for v in f.verts])
            nf.material_index = f.material_index
        tmp.free()

Section = Sequence[tuple[float, float]]


# ------------------------------------------------------------------------------------------------ sections
def chamfer_rect(w: float, h: float, c: float = 0.25, top: float = 1.0, bottom: float = 1.0) -> list[tuple[float, float]]:
    """An octagon from a w x h rectangle (half sizes), corners cut by c (fraction); top/bottom narrow the upper/lower
    halves (a keel or a deck ridge). Counter-clockwise, starting bottom-left."""
    cw, ch = c * w, c * h
    return [(-w * bottom + cw, -h), (w * bottom - cw, -h), (w, -h + ch), (w, h - ch), (w * top - cw, h), (-w * top + cw, h),
            (-w, h - ch), (-w, -h + ch)]


def blade(w: float, h: float, skew: float = 0.0) -> list[tuple[float, float]]:
    """The Mandate's faceted armour section: a low keel, a ridge pushed to one side (8 points)."""
    return [(-0.4 * w, -h), (0.45 * w, -h), (w, -0.3 * h), (w * 0.92, 0.35 * h), (0.3 * w + skew * w, h),
            (-0.35 * w + skew * w, 0.9 * h), (-w * 0.95, 0.3 * h), (-w, -0.35 * h)]


def resample(sec: Section, per_edge: Sequence[int]) -> list[tuple[float, float]]:
    """Split each edge of a closed section into per_edge[i] segments (the grid's resolution around the hull)."""
    out = []
    n = len(sec)
    for i in range(n):
        (y0, z0), (y1, z1) = sec[i], sec[(i + 1) % n]
        k = max(1, per_edge[i % len(per_edge)])
        for j in range(k):
            t = j / k
            out.append((y0 + (y1 - y0) * t, z0 + (z1 - z0) * t))
    return out


def edge_splits(sec: Section, target: float) -> list[int]:
    """How many grid cells along each section edge for cells of about `target` metres."""
    n = len(sec)
    return [max(1, round(math.dist(sec[i], sec[(i + 1) % n]) / target)) for i in range(n)]


# ---------------------------------------------------------------------------------------------------- hulls
class Hull:
    """A lofted grid hull: rings of the same vertex count at stations along X. Keeps the face grid for plating."""

    def __init__(self, b, stations: Sequence[tuple[float, Section, float]], mat: str, cell: float = 8.0, caps=(True, True)):
        """stations: (x, section, z_offset); sections are resampled with the first station's edge splits."""
        self.b = b
        bm = b.bm
        splits = edge_splits(stations[len(stations) // 2][1], cell)
        self.rings = []
        for x, sec, zo in stations:
            pts = resample(sec, splits)
            self.rings.append([bm.verts.new((x, y, z + zo)) for y, z in pts])
        idx = b.mi(mat)
        self.grid: list[list] = []          # grid[i][j]: the face between ring i and i+1, around-index j
        n = len(self.rings[0])
        for r0, r1 in zip(self.rings, self.rings[1:]):
            row = []
            for j in range(n):
                k = (j + 1) % n
                f = bm.faces.new((r0[j], r0[k], r1[k], r1[j]))
                f.material_index = idx
                row.append(f)
            self.grid.append(row)
        self.caps = []
        if caps[0]:
            self.caps.append(bm.faces.new(list(reversed(self.rings[0]))))
        if caps[1]:
            self.caps.append(bm.faces.new(self.rings[-1]))
        for f in self.caps:
            f.material_index = idx
        bmesh.ops.recalc_face_normals(bm, faces=[f for row in self.grid for f in row] + self.caps)

    def plate(self, rng: random.Random, depth=(0.25, 0.9), recess: float = 0.25, margin: float = 0.35,
              skip: float = 0.12, max_run=(3, 2), mats: dict | None = None) -> None:
        """Armour plating: the grid is cut into rectangular regions (1..max_run cells), each inset as one plate,
        raised (or, sometimes, recessed); some cells stay bare. mats: {material: probability} recolours plates."""
        bm = self.b.bm
        rows, cols = len(self.grid), len(self.grid[0])
        used = [[False] * cols for _ in range(rows)]
        for i in range(rows):
            for j in range(cols):
                if used[i][j]:
                    continue
                if rng.random() < skip:
                    used[i][j] = True
                    continue
                ri = rng.randint(1, max_run[0])
                rj = rng.randint(1, max_run[1])
                region = []
                for a in range(i, min(rows, i + ri)):
                    for c in range(j, min(cols, j + rj)):
                        if not used[a][c]:
                            region.append(self.grid[a][c])
                            used[a][c] = True
                if not region:
                    continue
                d = -rng.uniform(0.2, recess) if rng.random() < 0.2 else rng.uniform(*depth)
                res = bmesh.ops.inset_region(bm, faces=region, thickness=margin, depth=d, use_even_offset=True)
                if mats:
                    r = rng.random()
                    acc = 0.0
                    for m, p in mats.items():
                        acc += p
                        if r < acc:
                            mi = self.b.mi(m)
                            for f in region:
                                f.material_index = mi
                            break

    def cells(self, i0: int, i1: int, j0: int, j1: int) -> list:
        return [self.grid[i][j % len(self.grid[0])] for i in range(max(0, i0), min(len(self.grid), i1)) for j in range(j0, j1)]


def slab(b, x0: float, x1: float, sec0: Section, sec1: Section, mat: str, z0: float = 0.0, z1: float = 0.0,
         y0: float = 0.0, y1: float = 0.0) -> None:
    """A single chamfered block lofted between two sections (no grid): armour slabs, towers, housings."""
    bm = b.bm
    r0 = [bm.verts.new((x0, y + y0, z + z0)) for y, z in sec0]
    r1 = [bm.verts.new((x1, y + y1, z + z1)) for y, z in sec1]
    idx = b.mi(mat)
    n = len(r0)
    faces = [bm.faces.new((r0[i], r0[(i + 1) % n], r1[(i + 1) % n], r1[i])) for i in range(n)]
    faces += [bm.faces.new(list(reversed(r0))), bm.faces.new(r1)]
    for f in faces:
        f.material_index = idx
    bmesh.ops.recalc_face_normals(bm, faces=faces)


def frustum(b, bottom, top, zb: float, zt: float, mat: str, chamfer: float = 0.0) -> None:
    """A tapered tower: a (x0, x1, half_y) rectangle at zb up to another at zt (optionally chamfered corners)."""
    bm = b.bm

    def ring(r, z):
        x0, x1, hy = r
        c = chamfer * min(x1 - x0, 2 * hy)
        if c <= 0:
            pts = [(x0, -hy), (x1, -hy), (x1, hy), (x0, hy)]
        else:
            pts = [(x0 + c, -hy), (x1 - c, -hy), (x1, -hy + c), (x1, hy - c), (x1 - c, hy), (x0 + c, hy), (x0, hy - c), (x0, -hy + c)]
        return [bm.verts.new((x, y, z)) for x, y in pts]
    r0, r1 = ring(bottom, zb), ring(top, zt)
    n = len(r0)
    idx = b.mi(mat)
    faces = [bm.faces.new((r0[i], r0[(i + 1) % n], r1[(i + 1) % n], r1[i])) for i in range(n)]
    faces += [bm.faces.new(list(reversed(r0))), bm.faces.new(r1)]
    for f in faces:
        f.material_index = idx
    bmesh.ops.recalc_face_normals(bm, faces=faces)


def block(b, center, size, mat: str, c: float = 0.2, taper: float = 1.0, rot_z: float = 0.0) -> None:
    """A chamfered box (optionally tapering towards +X, rotated about Z)."""
    x, y, z = center
    sx, sy, sz = size
    s0 = chamfer_rect(sy / 2, sz / 2, c)
    s1 = chamfer_rect(sy / 2 * taper, sz / 2 * taper, c)
    if rot_z == 0.0:
        slab(b, x - sx / 2, x + sx / 2, s0, s1, mat, z, z, y, y)
        return
    with part(b, Matrix.Translation((x, y, z)) @ Matrix.Rotation(rot_z, 4, "Z")):
        slab(b, -sx / 2, sx / 2, s0, s1, mat)


# ---------------------------------------------------------------------------------------------------- parts
def turret(b, pos, scale: float, barrels: int, plate: str, frame: str, up: int = 1, yaw: float = 0.0) -> None:
    """Barbette, an angular gun house, barrels with muzzle collars (scale 1 = a 16 m gun house)."""
    x, y, z = pos
    s = scale
    b.cylinder((x, y, z), (x, y, z + up * 1.6 * s), 6.2 * s, frame, segments=20)
    b.cylinder((x, y, z + up * 1.6 * s), (x, y, z + up * 2.0 * s), 6.8 * s, plate, segments=20)
    m = Matrix.Translation((x, y, z + up * 3.4 * s)) @ Matrix.Rotation(math.radians(yaw), 4, "Z")
    if up < 0:
        m = m @ Matrix.Rotation(math.pi, 4, "X")
    with part(b, m):
        house = chamfer_rect(4.6 * s, 2.0 * s, 0.35, top=0.8)
        slab(b, -6.0 * s, 7.5 * s, house, chamfer_rect(3.6 * s, 1.5 * s, 0.35, top=0.7), plate, 0.0, -0.3 * s)
        gap = 2.4 * s if barrels > 1 else 0.0
        for k in range(barrels):
            yy = (k - (barrels - 1) / 2) * gap
            b.cylinder((6.5 * s, yy, 0.2 * s), (22.0 * s, yy, 0.2 * s), 0.55 * s, frame, segments=10)
            b.cylinder((20.5 * s, yy, 0.2 * s), (22.5 * s, yy, 0.2 * s), 0.8 * s, frame, segments=10)


def vls_grid(b, center, cols: int, rows: int, cell: float, plate: str, frame: str) -> None:
    """A raised launcher block with a grid of hatches."""
    x, y, z = center
    w, d = cols * cell, rows * cell
    block(b, (x, y, z + 0.6), (w + 1.6, d + 1.6, 1.2), frame, c=0.15)
    for i in range(cols):
        for j in range(rows):
            b.box((x - w / 2 + (i + 0.5) * cell, y - d / 2 + (j + 0.5) * cell, z + 1.3), (cell * 0.78, cell * 0.78, 0.25), plate)


def hangar(b, x: float, y: float, z: float, w: float, h: float, depth: float, frame: str, lights: str, side: int = 0) -> None:
    """A hangar mouth on a hull face: a protruding collar around a dark opening, the lit deck inside seen through it,
    light strips on the sill. side 0: the face looks +X at x; side +-1: a flank at y looking +-Y."""
    t = max(1.5, 0.08 * h)
    c = max(2.0, 0.12 * depth)     # how far the collar stands out
    if side == 0:
        for dz in (1, -1):
            b.box((x + c / 2, y, z + dz * (h / 2 + t / 2)), (c, w + 2 * t, t), frame)
        for dy in (1, -1):
            b.box((x + c / 2, y + dy * (w / 2 + t / 2), z), (c, t, h), frame)
        b.box((x + 0.25, y, z), (0.5, w, h), frame)
        b.box((x + 0.55, y, z - h * 0.22), (0.3, w * 0.86, h * 0.4), lights)
        b.box((x + c + 0.2, y, z - h / 2 - t * 0.5), (0.4, w * 0.9, 0.5), lights)
    else:
        for dz in (1, -1):
            b.box((x, y + side * c / 2, z + dz * (h / 2 + t / 2)), (w + 2 * t, c, t), frame)
        for dx in (1, -1):
            b.box((x + dx * (w / 2 + t / 2), y + side * c / 2, z), (t, c, h), frame)
        b.box((x, y + side * 0.25, z), (w, 0.5, h), frame)
        b.box((x, y + side * 0.55, z - h * 0.22), (w * 0.86, 0.3, h * 0.4), lights)
        b.box((x, y + side * (c + 0.2), z - h / 2 - t * 0.5), (w * 0.9, 0.4, 0.5), lights)


def engine_bank(b, x: float, y: float, z: float, r: float, n: int, rows: int, spacing: float, frame: str, engine: str,
                glow: str) -> None:
    """A block of nozzles at the stern (bells, inner glow, collars)."""
    for i in range(n):
        for j in range(rows):
            yy = y + (i - (n - 1) / 2) * spacing
            zz = z + (j - (rows - 1) / 2) * spacing
            b.cylinder((x, yy, zz), (x - 1.3 * r, yy, zz), r * 1.12, frame, segments=24)
            b.cylinder((x - 1.3 * r, yy, zz), (x - 2.6 * r, yy, zz), r * 0.78, engine, segments=24, radius2=r * 1.05)
            b.cylinder((x - 1.1 * r, yy, zz), (x - 1.3 * r, yy, zz), r * 1.2, frame, segments=24)
            b.cylinder((x - 2.1 * r, yy, zz), (x - 2.35 * r, yy, zz), r * 0.86, glow, segments=24)


def fins(b, x0: float, x1: float, y: float, z: float, height: float, count: int, mat: str, thick: float = 0.35,
         rake: float = 0.0) -> None:
    """A row of thin radiator fins along X."""
    step = (x1 - x0) / max(1, count - 1)
    for k in range(count):
        x = x0 + k * step
        b.box((x + rake * height / 2, y, z + height / 2), (thick, max(1.0, height * 0.6), height), mat)


def mast(b, x: float, y: float, z: float, h: float, frame: str, lights: str, dish: float = 0.0) -> None:
    b.cylinder((x, y, z), (x, y, z + h), max(0.25, h * 0.02), frame, segments=8)
    for k in range(3):
        zz = z + h * (0.4 + 0.2 * k)
        b.box((x, y, zz), (0.3, h * 0.25 * (1 - 0.25 * k), 0.3), frame)
    b.box((x, y, z + h + 0.4), (0.8, 0.8, 0.8), lights)
    if dish > 0:
        b.cylinder((x + dish * 0.2, y, z + h * 0.55), (x + dish * 0.6, y, z + h * 0.55), dish * 0.1, frame, segments=16, radius2=dish)


def window_band(b, x0: float, x1: float, y: float, z: float, rows: int, rng: random.Random, lights: str,
                pitch: float = 2.4, lit: float = 0.65, win=(1.2, 0.7)) -> None:
    """Rows of small lit windows (individual panes in runs, some dark)."""
    for r in range(rows):
        zz = z + r * pitch
        x = x0
        while x < x1:
            run = rng.randint(3, 14)
            on = rng.random() < lit
            for k in range(run):
                if on and x + k * 1.8 < x1 and rng.random() < 0.9:
                    b.box((x + k * 1.8, y, zz), (win[0], 0.2, win[1]), lights)
            x += run * 1.8 + rng.uniform(4, 12)


def running_lights(b, points: Sequence[tuple[float, float, float]], size: float, lights: str) -> None:
    for p in points:
        b.box(p, (size, size, size), lights)
