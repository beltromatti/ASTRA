"""SPAZIO-VIVO — the small things of the Aurelia system: the rocks of the Ceres Belt, what a wreck leaves (hull plates, girders, chunks of broken ship, a burnt cut face),
escape pods with their beacons, and the buoys that mark the lanes.

The rocks are displaced icospheres (fractal value noise, flattened and fractured), with the ore showing in veins; the debris is made of the same plates and frames as the
ships it came from (a faction's slots), so a field of it matches the wreck it spreads from.
"""
from __future__ import annotations

import math

import numpy as np

import ship3_geo as G
import ship3_kit2 as K2
from ship3_kit import Ctx, Xf
from space3_common import AMBER, AMBERC, BEACON, CHASER, FLASH2, RED, STEADY, STROBE3, TEAL, UP, WARM, WHITE, Rec, beams, collar, frames_x, tank_cyl

I3 = np.eye(3)


# ====================================================================================================================== noise and rock geometry
def icosphere(level: int) -> tuple:
    """Unit icosphere: (V (n,3), F (m,3) outward)."""
    t = (1.0 + math.sqrt(5.0)) / 2.0
    V = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t), (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    F = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9),
         (4, 9, 5), (2, 4, 11), (6, 2, 10), (8, 6, 7), (9, 8, 1)]
    V = [np.array(v, np.float64) / np.linalg.norm(v) for v in V]
    for _ in range(level):
        cache: dict = {}
        out = []

        def mid(a, b):
            key = (min(a, b), max(a, b))
            if key not in cache:
                p = V[a] + V[b]
                V.append(p / np.linalg.norm(p))
                cache[key] = len(V) - 1
            return cache[key]
        for a, b, c in F:
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            out += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        F = out
    return np.array(V), np.array(F, np.int32)


class Noise3:
    """Value noise on a wrapped random lattice (trilinear, smoothstepped), seeded: enough for rock."""

    def __init__(self, rng: np.random.Generator, n: int = 24):
        self.n = n
        self.g = rng.random((n, n, n))

    def __call__(self, P: np.ndarray, freq: float) -> np.ndarray:
        q = np.asarray(P, np.float64) * freq
        i = np.floor(q).astype(np.int64)
        f = q - i
        f = f * f * (3.0 - 2.0 * f)
        n = self.n
        out = 0.0
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    w = (f[:, 0] if dx else 1 - f[:, 0]) * (f[:, 1] if dy else 1 - f[:, 1]) * (f[:, 2] if dz else 1 - f[:, 2])
                    out = out + w * self.g[(i[:, 0] + dx) % n, (i[:, 1] + dy) % n, (i[:, 2] + dz) % n]
        return out


def fbm(noise: Noise3, P: np.ndarray, freq: float, octaves: int = 5, gain: float = 0.5, lac: float = 2.03) -> np.ndarray:
    tot, amp, norm_ = 0.0, 1.0, 0.0
    for o in range(octaves):
        tot = tot + amp * noise(P + o * 17.31, freq * lac ** o)
        norm_ += amp
        amp *= gain
    return tot / norm_


def rock_geometry(rng: np.random.Generator, radius: float, level: int = 3, kind: str = "rough", ore: float = 0.0, ice: bool = False) -> dict:
    """A rock about `radius` metres: {"V","F","a1","a2","mat" (per face: 0 rock, 1 ore, 2 ice)}. kind: rough (a lumpy boulder), long (a tumbling spindle), shard (fractured,
    flat-faced), pitted (craters), round (smoothed, a small moon)."""
    V0, F = icosphere(level)
    nz = Noise3(rng)
    P = V0.copy()
    sc = {"rough": (1.0, 0.86, 0.78), "long": (1.0, 0.42, 0.38), "shard": (1.0, 0.7, 0.55), "pitted": (1.0, 0.92, 0.82), "round": (1.0, 0.97, 0.94)}[kind]
    rough = {"rough": 0.34, "long": 0.30, "shard": 0.16, "pitted": 0.22, "round": 0.10}[kind]
    d = fbm(nz, V0 * 1.3, 1.0, 5, 0.55) - 0.5
    fine = fbm(nz, V0 + 3.7, 7.0, 4, 0.55) - 0.5                         # the small relief: ledges, pits and ridges a few metres across
    r = 1.0 + rough * 2.0 * d + (0.035 if kind != "round" else 0.02) * 2.0 * fine
    P = V0 * r[:, None]
    if kind == "shard":                                                  # cut by a few planes: flat faces and sharp ridges
        for _ in range(7):
            n = G.norm(rng.normal(size=3))
            off = rng.uniform(0.45, 0.8)
            s = P @ n - off
            P = np.where((s > 0)[:, None], P - s[:, None] * n[None], P)
    if kind == "pitted":                                                 # craters: spherical dents
        for _ in range(9):
            n = G.norm(rng.normal(size=3))
            rad = rng.uniform(0.18, 0.34)
            dd = np.linalg.norm(P / np.linalg.norm(P, axis=1, keepdims=True) - n, axis=1)
            dent = np.clip(1.0 - dd / rad, 0.0, 1.0)
            P = P * (1.0 - 0.5 * rad * np.sin(dent * math.pi / 2)[:, None] ** 2 * 1.2)[:, :]
    P = P * np.array(sc)[None] * radius
    # per-vertex data: wear on the high ridges, grime in the hollows, tone by a broad noise
    rr = np.linalg.norm(P, axis=1) / radius
    hi = np.clip((rr - np.percentile(rr, 55)) / max(1e-6, np.percentile(rr, 97) - np.percentile(rr, 55)), 0.0, 1.0)
    wear = hi * 0.42
    if ore > 0.0:                                                        # veins of ore: a noise thresholded, soft: the wear channel (chipped down to the bare ore, which shines)
        vein = fbm(nz, V0 * 1.0 + 9.0, 2.6, 4)
        thr = np.quantile(vein, 1.0 - ore)
        wear = np.maximum(wear, np.clip((vein - thr) * 14.0, 0.0, 1.0) * 0.95)
    a1 = np.stack([wear, np.clip(1.0 - hi * 1.6, 0.0, 1.0) * 0.8], axis=1)
    tone = np.clip(0.5 + (fbm(nz, V0, 2.3, 4) - 0.5) * 1.4, 0.05, 0.95)
    a2 = np.stack([tone, np.zeros_like(tone)], axis=1)
    mat = np.full(len(F), 2 if ice else 0, np.int16)
    return {"V": P, "F": F, "a1": a1, "a2": a2, "mat": mat}


def add_rock(c: Ctx, rock: dict, origin=(0.0, 0.0, 0.0), R=None, scale=1.0, mats=("Rock", "Ore", "Ice"), kind: str = "rock") -> None:
    V = np.asarray(origin) + (rock["V"] * scale) @ (np.eye(3) if R is None else R)
    names = [n if n.startswith("MI_") else c.m(n) for n in mats]                  # absolute slot names (MI_SPACE_Rock in a Guild mesh) or the mesh's own prefix
    mi = np.array([c.g.mi(n) for n in names], np.int16)
    c.g.add(V, rock["F"], mi[rock["mat"]], rock["a1"], rock["a2"], kind=kind)


def rock_spec(name: str):
    return {"A": dict(kind="rough", ore=0.12), "B": dict(kind="long", ore=0.08), "C": dict(kind="shard", ore=0.2), "D": dict(kind="pitted", ore=0.05),
            "E": dict(kind="round", ore=0.0, ice=True)}[name]


def make_rock(name: str):
    def build(c: Ctx) -> dict:
        s = rock_spec(name)
        rock = rock_geometry(c.rng, 50.0, level=4, kind=s["kind"], ore=s.get("ore", 0.0), ice=s.get("ice", False))
        add_rock(c, rock)
        return {"rec": Rec(), "length_m": 100.0, "cam": [-30.0, 20.0, 60.0], "margin": 0.12, "exposure": 0.2}
    return build


# ======================================================================================================================== debris
def _bent_plate(c: Ctx, size, bend: float, torn: float, mat_top: str, mat_under: str = "Frame") -> None:
    """A hull plate gone bent and torn: a slab of `size` (x, y) metres curved by `bend` (radians over its width), a ragged edge on one side, the frame ribs under it."""
    g, m, rng = c.g, c.m, c.rng
    sx, sy = size
    nx, ny = 10, 6
    xs = np.linspace(-sx / 2, sx / 2, nx + 1)
    ys = np.linspace(-sy / 2, sy / 2, ny + 1)
    X, Y = np.meshgrid(xs, ys, indexing="ij")
    ang = Y / sy * bend
    rad = sy / max(bend, 1e-3)
    Z = rad * (1.0 - np.cos(ang)) if bend > 1e-3 else np.zeros_like(Y)
    Yb = rad * np.sin(ang) if bend > 1e-3 else Y
    rag = (rng.random((nx + 1, 1)) - 0.5) * torn * sy
    Yb = np.where(Y > sy * 0.3, Yb + rag * (Y - sy * 0.3) / (sy * 0.2), Yb)
    th = 0.35
    top = np.stack([X, Yb, Z + th / 2], axis=-1).reshape(-1, 3)
    bot = np.stack([X, Yb, Z - th / 2], axis=-1).reshape(-1, 3)
    idx = np.arange((nx + 1) * (ny + 1)).reshape(nx + 1, ny + 1)
    quads = np.stack([idx[:-1, :-1], idx[1:, :-1], idx[1:, 1:], idx[:-1, 1:]], axis=-1).reshape(-1, 4)
    Ft = G.quads_to_tris(quads)
    nv = len(top)
    V = np.concatenate([top, bot])
    F = np.concatenate([Ft, Ft[:, [0, 2, 1]] + nv])
    # the edges: strips between top and bottom round the rim
    rim = []
    for i in range(nx):
        rim += [(idx[i, 0], idx[i + 1, 0]), (idx[i + 1, ny], idx[i, ny])]
    for j in range(ny):
        rim += [(idx[nx, j], idx[nx, j + 1]), (idx[0, j + 1], idx[0, j])]
    for a, b in rim:
        F = np.concatenate([F, np.array([[a, b, b + nv], [a, b + nv, a + nv]], np.int32)])
    a1 = np.zeros((len(V), 2), np.float32)
    a1[:nv, 0] = 0.15
    a1[nv:, 1] = 0.7
    g.add(V, F, c.m(mat_top), a1, (0.5, 0.0), kind="debris")
    for k in range(3):                                                    # ribs under the plate, one broken off
        yy = (k - 1) * sy * 0.3
        zz = (rad * (1.0 - np.cos(yy / sy * bend)) if bend > 1e-3 else 0.0) - 0.35
        g.box((0.0, yy, zz - 0.3), (sx * (0.9 if k != 2 else 0.5), 0.3, 0.6), m(mat_under), chamfer=0.04, kind="debris")


def build_debris_plate(c: Ctx) -> dict:
    _bent_plate(c, (13.0, 8.0), 0.5, 0.5, "Plate")
    return {"rec": Rec(), "length_m": 13.0, "cam": [-40.0, 30.0, 60.0], "margin": 0.1}


def build_debris_girder(c: Ctx) -> dict:
    """A length of lattice girder, twisted and snapped, a few loose plates still on it."""
    g, m, rng = c.g, c.m, c.rng
    L, h = 24.0, 1.4
    n = 10
    twist = np.linspace(0.0, 0.7, n + 1)
    cor = np.array([[1, 1], [-1, 1], [-1, -1], [1, -1]], np.float64) * h
    P = []
    for i in range(n + 1):
        a = twist[i]
        R2 = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
        pts = cor @ R2.T
        bend = 0.9 * math.sin(i / n * math.pi * 0.8)
        P.append(np.array([[-L / 2 + L * i / n, p[0] + bend, p[1] + 0.4 * bend] for p in pts]))
    P = np.array(P)
    for k in range(4):
        beams(c, P[:-1, k], P[1:, k], 0.32, mat="Frame", kind="debris")
    for i in range(n + 1):
        if i == 7 and rng.random() < 2.0:
            continue
        for k in range(4):
            beams(c, P[i, k][None], P[i, (k + 1) % 4][None], 0.2, mat="Frame", kind="debris")
    for i in range(n):
        for k in range(4):
            a, b = (P[i, k], P[i + 1, (k + 1) % 4]) if (i + k) % 2 == 0 else (P[i, (k + 1) % 4], P[i + 1, k])
            if i in (6, 7) and k > 1:
                continue
            beams(c, a[None], b[None], 0.16, mat="Frame", kind="debris")
    for xx, yy, zz, sz in ((-6.0, 0.4, 1.7, 3.2), (2.0, -0.2, 1.6, 2.4)):
        c.g.box((xx, yy, zz), (sz, sz * 0.7, 0.3), m("Plate"), frame=frames_x(G.norm(np.array([1.0, 0.25, 0.1])))[0], chamfer=0.03, kind="debris")
    return {"rec": Rec(), "length_m": L, "cam": [-40.0, 30.0, 60.0], "margin": 0.1}


def build_debris_chunk(c: Ctx) -> dict:
    """A chunk of broken hull: a few plates on a frame, a burnt cut face on one side, a pipe end."""
    g, m, rng = c.g, c.m, c.rng
    s = 9.0
    g.box((0, 0, 0), (s, s * 0.8, s * 0.55), m("Frame"), chamfer=0.2, kind="debris")
    for k, (cx, cy, cz, sx_, sy2) in enumerate(((0.0, 0.0, s * 0.31, 7.5, 6.0), (0.4, -s * 0.42, 0.2, 6.5, 3.2), (-1.0, s * 0.43, -0.4, 5.0, 3.6))):
        if k == 0:
            g.box((cx, cy, cz), (sx_, sy2, 0.5), m("Plate"), chamfer=0.06, kind="debris")
        else:
            g.box((cx, cy, cz), (sx_, 0.5, sy2), m("Plate"), chamfer=0.06, kind="debris")
    g.box((s * 0.52, 0.0, 0.0), (0.4, s * 0.74, s * 0.5), m("Cut"), chamfer=0.0, kind="debris")
    for k in range(5):                                                      # ribs sticking out of the torn end
        g.box((s * 0.52 + 1.2, (k - 2) * 1.6, rng.uniform(-1.0, 1.0)), (rng.uniform(1.8, 3.5), 0.3, 0.7), m("Frame"), chamfer=0.03, kind="debris")
    c.g.cylinders(np.array([[-s * 0.2, -s * 0.2, -s * 0.28]]), np.array([[-s * 0.2, -s * 0.2, -s * 0.28 - 3.5]]), 0.35, m("Engine"), seg=8, kind="debris")
    return {"rec": Rec(), "length_m": s, "cam": [-40.0, 30.0, 60.0], "margin": 0.12}


# ========================================================================================================================== pods and buoys
def build_pod(c: Ctx) -> dict:
    """An escape pod (about 6 m): an egg-shaped shell with a ring of thrusters, a hatch, a viewport, handholds, and a beacon on a short stalk (its lamp is in the table: a
    slow white blink; the wrecks module drives it)."""
    g, m, rng = c.g, c.m, c.rng
    rec = Rec()
    prof = [(0.05, -3.0), (0.9, -2.8), (1.65, -2.0), (2.0, -0.8), (2.05, 0.4), (1.8, 1.5), (1.2, 2.4), (0.55, 2.95), (0.05, 3.1)]
    fr = G.frame_z((1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    g.revolve(prof, m("Plate"), origin=(0, 0, 0), frame=fr, seg=28, wear=0.45, kind="pod")
    g.revolve([(2.06, -0.2), (2.14, -0.2), (2.14, 0.15), (2.06, 0.15), (2.06, -0.2)], m("Livery"), origin=(0, 0, 0), frame=fr, seg=28, kind="pod")
    for k in range(4):                                                      # thrusters
        a = math.pi / 2 * k + math.pi / 4
        p = np.array([-2.35, 1.55 * math.cos(a), 1.55 * math.sin(a)])
        g.cylinder(p, p + np.array([-0.6, 0.0, 0.0]), 0.28, 0.2, m("Engine"), seg=8, kind="pod")
    g.box((0.9, 0.0, 1.95), (1.0, 0.8, 0.12), m("Frame"), frame=G.frame_z((0.2, 0.0, 1.0), (1.0, 0.0, 0.0)), chamfer=0.03, kind="pod")        # hatch
    g.dome((1.3, 0.0, 1.42), 0.42, m("Glass"), frame=G.frame_z((0.4, 0.0, 1.0), (1.0, 0.0, 0.0)), seg=14, rings=3, squash=0.5, kind="pod")
    for sy in (-1, 1):                                                      # handholds and a stripe
        g.box((0.0, sy * 2.0, 0.0), (1.6, 0.12, 0.16), m("Trim"), chamfer=0.02, kind="pod")
    stalk_top = np.array([0.2, 0.0, 2.7])
    g.cylinder(np.array([0.2, 0.0, 1.95]), stalk_top, 0.07, 0.05, m("Frame"), seg=6, kind="pod")
    g.box(stalk_top + UP * 0.12, (0.28, 0.28, 0.28), m("Nav"), chamfer=0.02, kind="pod", a1_all=(1.0, 0.0))
    rec.lamp(stalk_top + UP * 0.3, WHITE, 1.4, 120.0, BEACON)
    rec.lamp((0.5, 0.0, 0.0), AMBERC, 0.5, 0.0, STEADY)
    return {"rec": rec, "length_m": 6.1, "cam": [-40.0, 25.0, 60.0], "margin": 0.12}


def build_buoy(c: Ctx) -> dict:
    """A lane buoy: a 30 m mast with a spindle body, a ring of lit panels and a strobe on top; the lane's colour is the lamp's (in the table, per lane)."""
    g, m, rng = c.g, c.m, c.rng
    rec = Rec()
    fr = G.frame_z((0.0, 0.0, 1.0), (1.0, 0.0, 0.0))
    g.revolve([(0.05, -6.0), (1.6, -5.2), (3.0, -2.5), (3.4, 0.0), (3.0, 2.5), (1.6, 5.2), (0.05, 6.0)], m("Plate"), origin=(0, 0, 0), frame=fr, seg=20, wear=0.5, kind="buoy")
    g.revolve([(3.45, -0.5), (3.7, -0.5), (3.7, 0.5), (3.45, 0.5), (3.45, -0.5)], m("Livery"), origin=(0, 0, 0), frame=fr, seg=20, kind="buoy")
    g.revolve([(3.46, 0.7), (3.46, 1.3)], m("Lights"), origin=(0, 0, 0), frame=fr, seg=20, kind="buoy", aux=0.1, wear=0.0)
    g.revolve([(3.46, -1.3), (3.46, -0.7)], m("Lights"), origin=(0, 0, 0), frame=fr, seg=20, kind="buoy", aux=0.1, wear=0.0)
    g.cylinder((0, 0, 5.5), (0, 0, 30.0), 0.34, 0.2, m("Frame"), seg=8, kind="buoy")
    for z, w in ((14.0, 4.0), (22.0, 3.0)):
        g.box((0, 0, z), (0.2, w, 0.2), m("Frame"), chamfer=0.0, kind="buoy")
        g.box((0, 0, z), (w, 0.2, 0.2), m("Frame"), chamfer=0.0, kind="buoy")
    g.box((0, 0, 30.4), (0.9, 0.9, 0.9), m("Nav"), chamfer=0.05, kind="buoy", a1_all=(1.0, 0.0))
    rec.lamp((0, 0, 31.4), WHITE, 3.0, 300.0, CHASER)
    return {"rec": rec, "length_m": 36.0, "cam": [-40.0, 20.0, 60.0], "margin": 0.12}


REGISTRY = {
    "SM_ROCK_A": dict(fac="R", seed=71, cls="rock", build=make_rock("A")),
    "SM_ROCK_B": dict(fac="R", seed=72, cls="rock", build=make_rock("B")),
    "SM_ROCK_C": dict(fac="R", seed=73, cls="rock", build=make_rock("C")),
    "SM_ROCK_D": dict(fac="R", seed=74, cls="rock", build=make_rock("D")),
    "SM_ROCK_E": dict(fac="R", seed=75, cls="rock", build=make_rock("E")),
    "SM_DEBRIS_A_Plate": dict(fac="A", seed=81, cls="prop", build=build_debris_plate),
    "SM_DEBRIS_A_Girder": dict(fac="A", seed=82, cls="prop", build=build_debris_girder),
    "SM_DEBRIS_A_Chunk": dict(fac="A", seed=83, cls="prop", build=build_debris_chunk),
    "SM_DEBRIS_M_Plate": dict(fac="M", seed=84, cls="prop", build=build_debris_plate),
    "SM_DEBRIS_M_Girder": dict(fac="M", seed=85, cls="prop", build=build_debris_girder),
    "SM_DEBRIS_M_Chunk": dict(fac="M", seed=86, cls="prop", build=build_debris_chunk),
    "SM_DEBRIS_G_Plate": dict(fac="G", seed=87, cls="prop", build=build_debris_plate),
    "SM_DEBRIS_G_Girder": dict(fac="G", seed=88, cls="prop", build=build_debris_girder),
    "SM_DEBRIS_G_Chunk": dict(fac="G", seed=89, cls="prop", build=build_debris_chunk),
    "SM_POD_A": dict(fac="A", seed=91, cls="prop", build=build_pod),
    "SM_POD_M": dict(fac="M", seed=92, cls="prop", build=build_pod),
    "SM_POD_G": dict(fac="G", seed=93, cls="prop", build=build_pod),
    "SM_BUOY_Lane": dict(fac="G", seed=95, cls="prop", build=build_buoy),
}
