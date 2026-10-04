"""SPAZIO-VIVO (docs/SPAZIO.md): the shared parts of the places and the civilian hulls of the Aurelia system.

The meshes of this module are built with the same numpy engine as the ships (ship3_geo.Geo: chunks of triangles, per-vertex wear/grime/tone in the
2nd and 3rd UV sets, material slots MI_HULL_<A|M|G>_<Part>) and the same kit (ship3_kit/kit2, ship3_loft plating), so a place wears the paint of the
faction that built it exactly as the ships do. What is added here is what a place or a civilian hull needs and a warship does not:

  Rec          what the game must know about a mesh without opening it: lamps (where, colour, size, how bright, how they blink), drive bells, berths
               (a pier's collar and the way a hull comes in), waiting points, moving parts (the Keeper's control ring, the Arsenal's cranes), a flare.
               Written in the manifest in the Unreal frame (Blender +Y is Unreal -Y), read by tools/space.py meshes -> data/space/meshes.json.
  beams/truss  lattice work in bulk (a truss is a few hundred beams: one call), tanks, collars, floodlights, window rows on any surface.
  stamp        a module built once and copied many times into a mesh (twelve identical piers, a row of silos), proper rotations or a mirror.

Frame: Blender's, metres, +X forward, +Z up, +Y to port. The FBX export mirrors Y (Unreal's starboard is Blender's -Y).
"""
from __future__ import annotations

import math

import numpy as np

import ship3_geo as G
import ship3_kit2 as K2
import ship3_text as TX
from ship3_kit import Ctx, Xf

I3 = np.eye(3)
UP = np.array([0.0, 0.0, 1.0])

# lamp patterns, as AstraSpace::PatternOn (Source/ASTRA/AstraSpaceLifeData.h)
STEADY, FLASH2, REDPULSE, AMBER, STROBE3, BEACON, CHASER, FLICKER = range(8)
WHITE, WARM, RED, GREEN, AMBERC, TEAL, ORANGE = ((1.0, 1.0, 1.0), (1.0, 0.86, 0.62), (1.0, 0.08, 0.05), (0.1, 1.0, 0.3), (1.0, 0.62, 0.15),
                                                  (0.35, 0.95, 1.0), (1.0, 0.45, 0.12))


# ====================================================================================================================== what the game needs
class Rec:
    """The game's table for one mesh. Everything is given in the Blender frame and converted when written (y -> -y)."""

    def __init__(self):
        self.lamps: list = []
        self.bells: list = []
        self.docks: list = []
        self.holds: list = []
        self.parts: list = []
        self.flare = None
        self.flare_len = 0.0

    def lamp(self, p, color=WHITE, size: float = 2.0, glow: float = 300.0, pat: int = STEADY, phase: float = 0.0) -> None:
        """One lamp: size = metres across up close; glow = the intensity when lit (the war's scale: 160 a window, 500-900 a strobe)."""
        self.lamps.append({"p": [float(x) for x in p], "c": [float(x) for x in color], "s": float(size), "i": float(glow), "pat": int(pat), "ph": float(phase)})

    def lamps_along(self, p0, p1, n: int, color=WARM, size: float = 2.0, glow: float = 260.0, pat: int = STEADY, chase: float = 0.0, phase0: float = 0.0) -> None:
        """n lamps evenly from p0 to p1; chase > 0 gives them a phase run down the row (a chaser, `chase` seconds from one to the next)."""
        p0, p1 = np.asarray(p0, np.float64), np.asarray(p1, np.float64)
        for i in range(n):
            t = i / max(1, n - 1)
            self.lamp(p0 + (p1 - p0) * t, color, size, glow, pat, phase0 + i * chase)

    def bell(self, p, r: float) -> None:
        self.bells.append({"p": [float(x) for x in p], "r": float(r)})

    def dock(self, tip, out, max_len: float, roles, lead: float = 700.0) -> None:
        """A berth. `tip` is where the bow of a hull in the berth meets the pier's collar, `out` the unit vector pointing away from the place along the pier (the way
        a hull comes in is -out: bow first, towards the place). The game places a hull of any length so that its bow meets the collar; `p` is the centre of a hull
        as long as max_len, `approach` the point it comes in from."""
        tip, out = np.asarray(tip, np.float64), G.norm(out)
        p = tip + out * (max_len * 0.5 + 2.0)
        self.docks.append({"p": [float(x) for x in p], "dir": [float(x) for x in -out], "approach": [float(x) for x in p + out * lead], "max_len": float(max_len),
                           "roles": list(roles)})

    def hold(self, p) -> None:
        self.holds.append([float(x) for x in p])

    def hold_ring(self, radius: float, n: int = 8, wobble: float = 0.1, center=(0.0, 0.0, 0.0), phase: float = 0.0) -> None:
        """Waiting points in a ring round the place (a hull that finds no berth free waits at one), a little up and down so that two do not lie in line."""
        for k in range(n):
            a = phase + 2.0 * math.pi * k / n
            self.hold(np.asarray(center) + np.array([radius * math.cos(a), radius * math.sin(a), radius * wobble * math.sin(a * 3.0 + 1.0)]))

    def part(self, mesh: str, pivot, axis, period_s: float, phase: float = 0.0, swing_deg: float = 0.0, lamps: list | None = None) -> None:
        """A moving part with its own mesh (origin at the pivot): turns about `axis` once per period_s (negative: the other way), or swings swing_deg either way.
        `lamps` are the part's own (in its mesh frame: they turn with it)."""
        self.parts.append({"mesh": mesh, "pivot": [float(x) for x in pivot], "axis": [float(x) for x in axis], "period_s": float(period_s), "phase": float(phase),
                           "swing_deg": float(swing_deg), "lamps": lamps or []})

    def set_flare(self, tip, length: float) -> None:
        self.flare = [float(x) for x in tip]
        self.flare_len = float(length)

    # ------------------------------------------------------------------------------------------------------------ out
    @staticmethod
    def _ue(p) -> list:
        return [round(float(p[0]), 2), round(-float(p[1]), 2), round(float(p[2]), 2)]

    def lamp_entries(self, lamps=None) -> list:
        out = []
        for lp in (self.lamps if lamps is None else lamps):
            out.append({"p": self._ue(lp["p"]), "c": [round(x, 3) for x in lp["c"]], "s": round(lp["s"], 2), "i": round(lp["i"], 1), "pat": lp["pat"], "ph": round(lp["ph"], 3)})
        return out

    def to_json(self) -> dict:
        out: dict = {"lamps": self.lamp_entries(), "bells": [{"p": self._ue(b["p"]), "r": round(b["r"], 2)} for b in self.bells]}
        if self.docks:
            out["docks"] = [{"p": self._ue(d["p"]), "dir": self._ue(d["dir"]), "approach": self._ue(d["approach"]), "max_len": d["max_len"], "roles": d["roles"]}
                            for d in self.docks]
        if self.holds:
            out["holds"] = [self._ue(h) for h in self.holds]
        if self.parts:
            out["parts"] = [{"mesh": p["mesh"], "pivot": self._ue(p["pivot"]), "axis": self._ue(p["axis"]), "period_s": p["period_s"], "phase": p["phase"],
                             "swing_deg": p["swing_deg"], "lamps": self.lamp_entries(p["lamps"])} for p in self.parts]
        if self.flare is not None:
            out["flare"] = self._ue(self.flare)
            out["flare_len"] = round(self.flare_len, 1)
        return out


# ===================================================================================================================== frames and beams
def frames_x(ex, up=UP) -> np.ndarray:
    """Row-basis frames (n,3,3) with x along `ex` (n,3), z as close to `up` as possible (a vertical beam falls back to another up)."""
    ex = G.norm(np.atleast_2d(np.asarray(ex, np.float64)))
    u = np.broadcast_to(np.asarray(up, np.float64), ex.shape).copy()
    bad = np.abs(np.sum(ex * u, axis=1)) > 0.98
    if bad.any():
        u[bad] = np.where(np.abs(ex[bad][:, 1:2]) < 0.9, np.array([[0.0, 1.0, 0.0]]), np.array([[1.0, 0.0, 0.0]]))
    ey = G.norm(np.cross(u, ex))
    ez = np.cross(ex, ey)
    return np.stack([ex, ey, ez], axis=1)


def beams(c: Ctx, P0, P1, w, h=None, mat: str = "Frame", up=UP, chamfer: float = 0.0, kind: str = "beam", tone=G.TONE0, wear: float = 0.5, aux=0.0) -> None:
    """Many square-ish beams at once: from P0 (n,3) to P1 (n,3), section w x h metres (scalars or (n,)). Plain boxes (12 triangles) unless chamfered."""
    P0 = np.atleast_2d(np.asarray(P0, np.float64))
    P1 = np.atleast_2d(np.asarray(P1, np.float64))
    d = P1 - P0
    L = np.linalg.norm(d, axis=1)
    ok = L > 1e-4
    if not ok.any():
        return
    n = len(P0)
    w = np.broadcast_to(np.asarray(w, np.float64), (n,))
    h = w if h is None else np.broadcast_to(np.asarray(h, np.float64), (n,))
    P0, P1, d, L, w, h = P0[ok], P1[ok], d[ok], L[ok], w[ok], h[ok]
    fr = frames_x(d, up)
    half = np.stack([L / 2.0, w / 2.0, h / 2.0], axis=1)
    c.g.boxes((P0 + P1) / 2.0, half, c.m(mat), frames=fr, chamfer=chamfer, wear=wear, kind=kind, tone=tone, aux=aux)


def pipes(c: Ctx, P0, P1, r, mat: str = "Frame", seg: int = 8, kind: str = "pipe", tone=G.TONE0, wear: float = 0.5) -> None:
    c.g.cylinders(np.atleast_2d(P0), np.atleast_2d(P1), r, c.m(mat), seg=seg, kind=kind, tone=tone, wear=wear)


def truss(c: Ctx, A, B, hy: float, hz: float | None = None, bay: float = 16.0, chord: float = 0.9, web: float = 0.45, mat: str = "Frame", up=UP,
          kind: str = "truss", diag: bool = True, ring: bool = True, skip_ends: bool = False, tone=G.TONE0, mat_web: str | None = None) -> np.ndarray:
    """A square truss from A to B (any direction): four chords, square rings every `bay` metres and a diagonal on every face of every bay.
    hy, hz = half widths across (y then z of the beam's own frame). The chords are `mat`, the rings and diagonals `mat_web` (default the same). Returns the frame (rows
    ex, ey, ez) so that things can be hung on it."""
    A, B = np.asarray(A, np.float64), np.asarray(B, np.float64)
    mat_web = mat_web or mat
    hz = hy if hz is None else hz
    d = B - A
    L = float(np.linalg.norm(d))
    fr = frames_x(d, up)[0]
    ex, ey, ez = fr
    cor = np.array([[1.0, 1.0], [-1.0, 1.0], [-1.0, -1.0], [1.0, -1.0]]) * np.array([hy, hz])
    off = cor[:, 0:1] * ey[None] + cor[:, 1:2] * ez[None]                                  # (4,3)
    beams(c, A + off, B + off, chord, mat=mat, up=up, kind=kind, tone=tone)
    n = max(1, int(round(L / bay)))
    ts = np.linspace(0.0, 1.0, n + 1)
    st = A[None] + d[None] * ts[:, None]                                                   # (n+1,3) ring centres
    if ring:
        idx = range(n + 1)
        if skip_ends:
            idx = range(1, n)
        p0 = np.concatenate([st[i][None] + off for i in idx]) if len(idx) else np.zeros((0, 3))
        p1 = np.concatenate([st[i][None] + np.roll(off, -1, axis=0) for i in idx]) if len(idx) else np.zeros((0, 3))
        if len(p0):
            beams(c, p0, p1, web, mat=mat_web, up=up, kind=kind, tone=tone)
    if diag:
        a, b = [], []
        for i in range(n):
            for k in range(4):
                k2 = (k + 1) % 4
                if (i + k) % 2 == 0:
                    a.append(st[i] + off[k]); b.append(st[i + 1] + off[k2])
                else:
                    a.append(st[i] + off[k2]); b.append(st[i + 1] + off[k])
        beams(c, np.array(a), np.array(b), web * 0.9, mat=mat_web, up=up, kind=kind, tone=tone)
    return fr


def girder(c: Ctx, A, B, h: float, depth: float, mat: str = "Frame", bay: float = 12.0, chord: float = 0.7, web: float = 0.4, up=UP, kind: str = "truss") -> None:
    """A flat Warren girder (two chords and a zigzag web in one plane, `h` apart; `depth` the plane's thickness): the arms of cranes and gantries."""
    A, B = np.asarray(A, np.float64), np.asarray(B, np.float64)
    d = B - A
    L = float(np.linalg.norm(d))
    ex, ey, ez = frames_x(d, up)[0]
    n = max(2, int(round(L / bay)))
    top, bot = ez * h / 2.0, -ez * h / 2.0
    beams(c, np.array([A + top, A + bot]), np.array([B + top, B + bot]), chord, depth, mat=mat, up=up, kind=kind)
    ts = np.linspace(0.0, 1.0, n + 1)
    a, b = [], []
    for i in range(n):
        p, q = A + d * ts[i], A + d * ts[i + 1]
        if i % 2 == 0:
            a.append(p + bot); b.append(q + top)
        else:
            a.append(p + top); b.append(q + bot)
    beams(c, np.array(a), np.array(b), web, depth * 0.7, mat=mat, up=up, kind=kind)
    beams(c, A[None] + d[None] * ts[:, None] + bot, A[None] + d[None] * ts[:, None] + top, web, depth * 0.7, mat=mat, up=up, kind=kind)


# ==================================================================================================================== tanks and cylinders
def sphere_tank(c: Ctx, p, R: float, mat: str = "Plate", axis=UP, seg: int = 36, rings: int = 14, bands: int = 3, band_mat: str = "Frame", skirt: bool = False,
                kind: str = "tank", wear: float = 0.45, tone=G.TONE0) -> None:
    """A spherical tank centred at p: the shell, equatorial and tropic bands, a manway on top. With `skirt` a cylindrical support ring under it."""
    g = c.g
    fr = G.frame_z(axis, (1.0, 0.0, 0.0) if abs(axis[2]) < 0.9 else (0.0, 1.0, 0.0))
    t = np.linspace(-math.pi / 2, math.pi / 2, rings + 1)
    prof = [(max(R * math.cos(x), 1e-3), R * math.sin(x)) for x in t]
    g.revolve(prof, c.m(mat), origin=p, frame=fr, seg=seg, wear=wear, kind=kind, tone=tone)
    for k in range(bands):
        a = (k - (bands - 1) / 2.0) * 0.55
        r0 = R * math.cos(a) + 0.04 * R
        z0 = R * math.sin(a)
        w = 0.035 * R
        g.revolve([(r0 - 0.02 * R, z0 - w), (r0 + 0.03 * R, z0 - w), (r0 + 0.03 * R, z0 + w), (r0 - 0.02 * R, z0 + w), (r0 - 0.02 * R, z0 - w)], c.m(band_mat),
                  origin=p, frame=fr, seg=seg, wear=0.6, kind=kind)
    top = np.asarray(p, np.float64) + fr[2] * R
    g.cylinder(top - fr[2] * 0.02 * R, top + fr[2] * 0.12 * R, 0.16 * R, 0.14 * R, c.m(band_mat), seg=14, chamfer=0.01 * R, kind=kind)
    if skirt:
        base = np.asarray(p, np.float64) - fr[2] * R * 0.93
        g.cylinder(base - fr[2] * R * 0.55, base + fr[2] * R * 0.1, R * 0.62, R * 0.55, c.m(band_mat), seg=seg // 2, chamfer=0.02 * R, kind=kind)


def tank_cyl(c: Ctx, p0, p1, r: float, mat: str = "Plate", seg: int = 28, bands: int = 5, band_mat: str = "Frame", kind: str = "tank", dome: bool = True, wear: float = 0.5,
             tone=G.TONE0) -> None:
    """A capsule tank from p0 to p1 (domed ends, so p0 and p1 are the tips), with bands along it."""
    g = c.g
    p0, p1 = np.asarray(p0, np.float64), np.asarray(p1, np.float64)
    d = p1 - p0
    L = float(np.linalg.norm(d))
    ez = d / L
    fr = G.frame_z(ez, (1.0, 0.0, 0.0) if abs(ez[0]) < 0.9 else (0.0, 1.0, 0.0))
    cap = r * 0.6 if dome else 0.0
    if dome:
        th = np.linspace(0.0, math.pi / 2, 5)
        profile = [(r * math.sin(t), cap * (1.0 - math.cos(t))) for t in th] + [(r * math.sin(t), L - cap * (1.0 - math.cos(t))) for t in th[::-1]]
    else:
        profile = [(r, 0.0), (r, L)]
    g.revolve(profile, c.m(mat), origin=p0, frame=fr, seg=seg, wear=wear, kind=kind, tone=tone)
    bodyL = L - 2.0 * cap
    for k in range(bands):
        z = cap + (k + 0.5) * bodyL / bands
        w = 0.3 + 0.015 * r
        g.revolve([(r - 0.05, z - w), (r + 0.18 + 0.01 * r, z - w), (r + 0.18 + 0.01 * r, z + w), (r - 0.05, z + w), (r - 0.05, z - w)], c.m(band_mat), origin=p0, frame=fr,
                  seg=seg, wear=0.6, kind=kind)


def collar(c: Ctx, tip, out, r: float = 10.0, depth: float = 6.0, lit: bool = True, kind: str = "dock") -> None:
    """A docking collar at the end of a pier: `tip` is where a hull's bow meets it, `out` points away from the place (the way the pier runs). A heavy ring, an inner
    lit liner (the lit seal), clamp pads and a pair of status lamps."""
    g, m = c.g, c.m
    out = G.norm(out)
    tip = np.asarray(tip, np.float64)
    fr = G.frame_z(out, (0.0, 0.0, 1.0) if abs(out[2]) < 0.9 else (1.0, 0.0, 0.0))
    o = tip - out * depth                                                                   # the collar's body, behind the mating face
    g.revolve([(r * 0.62, 0.0), (r * 1.18, 0.0), (r * 1.18, depth * 0.55), (r * 1.0, depth), (r * 0.62, depth), (r * 0.62, 0.0)], m("Frame"), origin=o, frame=fr, seg=28, wear=0.7,
              kind=kind)
    g.revolve([(r * 0.66, depth - 0.01), (r * 0.96, depth - 0.01), (r * 0.96, depth + 0.35), (r * 0.66, depth + 0.35), (r * 0.66, depth - 0.01)], m("Engine"), origin=o, frame=fr,
              seg=28, wear=0.5, kind=kind)
    if lit:
        g.revolve([(r * 0.90, depth + 0.36), (r * 0.70, depth + 0.36)], m("Lights"), origin=o, frame=fr, seg=28, wear=0.0, kind=kind, aux=0.1)
    for k in range(4):                                                                     # clamp pads round the lip
        a = math.pi / 2 * k + math.pi / 4
        q = o + fr[0] * math.cos(a) * r * 1.02 + fr[1] * math.sin(a) * r * 1.02 + fr[2] * depth * 0.7
        g.box(q, (depth * 0.5, 1.4, 1.1), m("Engine"), frame=G.frame_z(fr[0] * math.cos(a) + fr[1] * math.sin(a), tuple(out)), chamfer=0.08, kind=kind)


def floodlight(c: Ctx, rec: Rec | None, base, h: float, face, n: int = 3, color=WARM, glow: float = 700.0, size: float = 3.2, kind: str = "lamp", scale: float = 1.0) -> None:
    """A floodlight mast: a thin pole `h` metres up from `base` carrying a bank of `n` lamps looking along `face` (the lamps are lit panels, `scale` times a 1.7 m head, and,
    for the far view, one lamp of the table at the top)."""
    g, m = c.g, c.m
    base = np.asarray(base, np.float64)
    top = base + UP * h
    s = scale
    g.cylinder(base, top, 0.5 * s, 0.32 * s, m("Frame"), seg=8, kind=kind)
    fr = G.frame_z(G.norm(face), (0.0, 0.0, 1.0))
    for k in range(n):
        q = top + fr[1] * ((k - (n - 1) / 2.0) * 1.9 * s)
        g.box(q - fr[2] * 0.2 * s, (1.7 * s, 1.7 * s, 0.9 * s), m("Frame"), frame=fr, chamfer=0.06 * s, kind=kind)
        g.box(q + fr[2] * 0.3 * s, (1.45 * s, 1.45 * s, 0.12 * s), m("Lights"), frame=fr, chamfer=0.0, kind=kind, aux=0.1)
    if rec is not None:
        rec.lamp(top + fr[2] * 1.2 * s, color, size, glow, STEADY)


def nav(c: Ctx, rec: Rec | None, p, normal, colour: float, size: float = 1.4, pat: int = STEADY, glow: float = 300.0, phase: float = 0.0) -> None:
    """A running-light fixture and, if a table is given, its lamp for the far view (colour 0 red / 0.5 green / 1 white)."""
    K2.nav_light(c, p, normal, colour, size, pulse=pat == REDPULSE)
    if rec is not None:
        col = RED if colour < 0.25 else (GREEN if colour < 0.75 else WHITE)
        rec.lamp(np.asarray(p, np.float64) + G.norm(normal) * 0.9 * size, col, 2.2 * size, glow, pat, phase)


def windows_at(c: Ctx, P, N, T, win=(1.5, 0.85), ids=None, lift: float = 0.12, frame_mat: str = "Frame", cheap: bool = False) -> int:
    """Lit/dark windows at arbitrary points: P (n,3) on a surface, N its normals, T the reading direction. Each pane carries a random id (the light material turns it
    on or off and flickers it). `cheap`: plain frames, 24 triangles a window instead of 56 (the long rows of a ring or a spine). Returns the number of panes."""
    P = np.atleast_2d(P)
    n = len(P)
    if n == 0:
        return 0
    ids = c.rng.random(n) if ids is None else ids
    Fr = G.frames_z(N, T)
    c.g.boxes(P + np.asarray(N) * 0.05, (win[0] / 2 + 0.16, win[1] / 2 + 0.16, 0.10), c.m(frame_mat), frames=Fr, chamfer=0.0 if cheap else 0.03, wear=0.7, kind="window")
    c.g.boxes(P + np.asarray(N) * (0.05 + lift), (win[0] / 2, win[1] / 2, 0.05), c.m("Lights"), frames=Fr, chamfer=0.0, kind="window", aux=np.asarray(ids))
    return n


def zone_windows(c: Ctx, zone, w: float, a0: float, a1: float, pitch: float = 2.6, win=(1.4, 0.75), lift: float = 0.7, runs=(4, 14), gaps=(1.0, 3.0), rows: int = 1,
                 row_m: float = 2.6, cheap: bool = True) -> int:
    """Rows of windows along a zone at cross position w, from a0 to a1: panes every `pitch` metres in runs of `runs` panes separated by dark stretches of `gaps` panes,
    `rows` rows `row_m` apart. Like ship3_kit2.window_band with plain frames (a lit pane and its frame: 24 triangles). `lift`: the height of the surface they stand on."""
    rng = c.rng
    dw = row_m / zone.sw(0.5 * (a0 + a1))
    total = 0
    for r in range(rows):
        wr = w + r * dw
        if wr > 0.97:
            break
        xs, a = [], a0 + float(rng.uniform(0.0, 2.0 * pitch))
        while a < a1 - win[0]:
            run = int(rng.integers(runs[0], runs[1] + 1))
            for k in range(run):
                x = a + k * pitch
                if x > a1 - win[0]:
                    break
                xs.append(x)
            a += (run + float(rng.uniform(*gaps))) * pitch
        if not xs:
            continue
        xs = np.array(xs)
        P, N, T = zone.frame(xs, np.full(len(xs), wr))
        total += windows_at(c, P + N * lift, N, T, win=win, cheap=cheap)
    return total


def window_rows(c: Ctx, A, B, normal, rows: int = 1, pitch: float = 2.4, win=(1.5, 0.85), up=UP, gap_p: float = 0.12, row_pitch: float = 2.6, offset=0.0, lift: float = 0.12,
                runs=(4, 14), gaps=(2, 5)) -> int:
    """Rows of windows along the line A -> B on a flat face with the given outward normal: panes in runs separated by gaps (dark stretches), `rows` rows `row_pitch`
    apart (the first on the line, the next ones up). Returns the panes."""
    A, B = np.asarray(A, np.float64), np.asarray(B, np.float64)
    d = B - A
    L = float(np.linalg.norm(d))
    ex = d / L
    nrm = G.norm(normal)
    ey = G.norm(np.cross(nrm, ex))
    upv = np.cross(ex, ey)
    upv = upv if upv @ np.asarray(up) > 0 else -upv
    k = int(L // pitch)
    pts = []
    i = int(c.rng.integers(0, 3))
    while i < k:
        run = int(c.rng.integers(runs[0], runs[1] + 1))
        for j in range(run):
            if i + j >= k:
                break
            pts.append(A + ex * ((i + j + 0.5) * pitch))
        i += run + int(c.rng.integers(gaps[0], gaps[1] + 1))
    if not pts:
        return 0
    pts = np.array(pts)
    total = 0
    for r in range(rows):
        q = pts + upv * (r * row_pitch + offset)
        total += windows_at(c, q, np.tile(nrm, (len(q), 1)), np.tile(ex, (len(q), 1)), win=win, lift=lift)
    return total


# ====================================================================================================================== modules
def new_like(g: G.Geo) -> G.Geo:
    """An empty Geo with the same material slots in the same order: a module to build once and stamp many times."""
    return G.Geo(list(g.mats))


def stamp(dst: G.Geo, src: G.Geo, origin=(0.0, 0.0, 0.0), R=None, scale: float = 1.0, mirror_y: bool = False, tone_shift: float = 0.0) -> None:
    """Copy the chunks of a module into `dst` at `origin`, turned by the row-basis rotation R (rows = the module's axes in the destination), scaled; mirror_y
    mirrors the module across its own xz plane first (the winding is turned so that the faces still look out)."""
    Rm = np.eye(3) if R is None else np.asarray(R, np.float64)
    o = np.asarray(origin, np.float64)
    remap = np.array([dst.mi(n) for n in src.mats], np.int16)                              # the slots by name: the two may have been made with another order
    for ch in src.chunks:
        V = ch["V"].astype(np.float64) * scale
        F = ch["F"]
        if mirror_y:
            V = V * np.array([1.0, -1.0, 1.0])
            F = F[:, [0, 2, 1]]
        V = o + V @ Rm
        a2 = ch["a2"]
        if tone_shift:
            a2 = a2.copy()
            a2[:, 0] = np.clip(a2[:, 0] + tone_shift, 0.02, 0.98)
        dst.add(V, F, remap[ch["mat"]], ch["a1"], a2, uv=ch["uv"], kind=ch["kind"], split=ch["split"], cap=ch["cap"], sec=ch["sec"])


def rot_z_deg(deg: float) -> np.ndarray:
    a = math.radians(deg)
    cs, sn = math.cos(a), math.sin(a)
    return np.array([[cs, sn, 0.0], [-sn, cs, 0.0], [0.0, 0.0, 1.0]])


def rot_x_deg(deg: float) -> np.ndarray:
    a = math.radians(deg)
    cs, sn = math.cos(a), math.sin(a)
    return np.array([[1.0, 0.0, 0.0], [0.0, cs, sn], [0.0, -sn, cs]])


def rot_y_deg(deg: float) -> np.ndarray:
    a = math.radians(deg)
    cs, sn = math.cos(a), math.sin(a)
    return np.array([[cs, 0.0, sn], [0.0, 1.0, 0.0], [-sn, 0.0, cs]])


def text_on(c: Ctx, text: str, centre, normal, height: float, up=UP, mat: str = "Marking", depth: float = 0.2) -> float:
    return TX.place_text(c.g, text, centre, normal, height, c.m(mat), up=up, depth=depth)
