"""ASTRA ships v3 — parts kit, second half: engines, thrusters, radiators, antennas, hangar mouths, windows, running lights and
the small details (hatches, vents, blisters, lamps, cables, stencils) that get scattered over panels."""
from __future__ import annotations

import math

import numpy as np

import ship3_geo as G
import ship3_loft as LF
import ship3_panels as PN
import ship3_text as TX
from ship3_kit import Ctx, Xf

NAV_RED, NAV_GREEN, NAV_WHITE = 0.0, 0.5, 1.0
_Z_TO_X = np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]])      # revolve axis (local z) -> the part's local +x


def _rx(deg: float) -> np.ndarray:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[1.0, 0.0, 0.0], [0.0, c, s], [0.0, -s, c]])


# ================================================================================================================= engines
def engine_nozzle(c: Ctx, xf: Xf, R: float, style: str = "astra", detail: int = 1) -> None:
    """A drive bell (R = the throat-ring radius; the bell is ~2.1 R long along local +z, the exhaust direction): the chamber
    housing, a flared wall with cooling pipes and bands, a lip, and inside it the injector face with concentric glowing rings and
    a short cone of light."""
    g, m = c.g, c.m
    # the wall as a closed loop: outer surface out to the lip, back along the inner surface (counter-clockwise in (r, z))
    wall = [(0.78, 0.0), (0.66, 0.30), (0.72, 0.85), (0.90, 1.50), (1.00, 1.98), (1.07, 2.03), (1.07, 2.14), (0.97, 2.14),
            (0.87, 1.70), (0.62, 0.95), (0.52, 0.42), (0.50, 0.08), (0.78, 0.0)]
    xf.revolve(g, [(r * R, z * R) for r, z in wall], m("Engine"), seg=28 if detail else 14, wear=0.7, kind="engine")
    xf.cyl(g, (0, 0, -1.3 * R), (0, 0, 0.02 * R), 1.12 * R, 1.0 * R, m("Frame"), seg=24 if detail else 12, ch=0.06 * R, kind="engine")
    if detail:
        for z in (0.45, 1.0, 1.55):                                                        # bands round the bell
            r = float(np.interp(z, [0.0, 0.3, 0.85, 1.5, 1.98], [0.78, 0.66, 0.72, 0.90, 1.0]))
            xf.revolve(g, [(r * R - 0.02 * R, (z - 0.07) * R), (r * R + 0.07 * R, (z - 0.07) * R), (r * R + 0.07 * R, (z + 0.07) * R),
                           (r * R - 0.02 * R, (z + 0.07) * R), (r * R - 0.02 * R, (z - 0.07) * R)], m("Frame"), seg=24, wear=0.6, kind="engine")
        k = 10                                                                             # cooling pipes following the wall
        a = np.linspace(0, 2 * math.pi, k, endpoint=False)
        zs = np.array([0.02, 0.5, 1.0, 1.5, 1.95])
        rs = np.interp(zs, [0.0, 0.3, 0.85, 1.5, 1.98], [0.78, 0.66, 0.72, 0.90, 1.0]) + 0.04
        for i in range(len(zs) - 1):
            p0 = np.stack([rs[i] * R * np.cos(a), rs[i] * R * np.sin(a), np.full(k, zs[i] * R)], axis=1)
            p1 = np.stack([rs[i + 1] * R * np.cos(a), rs[i + 1] * R * np.sin(a), np.full(k, zs[i + 1] * R)], axis=1)
            g.cylinders(xf.pts(p0), xf.pts(p1), 0.04 * R * xf.s, m("Frame"), seg=6, kind="engine")
    # the injector face: concentric rings, glowing and dark, and a cone of light
    for r0, r1, mat in ((0.0, 0.12, "Glow"), (0.12, 0.19, "Engine"), (0.19, 0.31, "Glow"), (0.31, 0.37, "Engine"), (0.37, 0.49, "Glow")):
        xf.revolve(g, [(r1 * R, 0.14 * R), (r0 * R, 0.14 * R)], m(mat), seg=20 if detail else 12, wear=0.2, kind="engine")
    xf.revolve(g, [(0.40 * R, 0.15 * R), (0.28 * R, 0.5 * R), (0.12 * R, 0.85 * R), (0.0, 1.05 * R)], m("Glow"), seg=16 if detail else 10, wear=0.0, kind="engine")


def engine_bank(c: Ctx, stern_x: float, ys, zs, R: float, style: str = "astra") -> None:
    """A stern block of drive bells at x = stern_x facing aft: ys/zs are the bell centres, R their radius. Heat-shield plates
    round the chambers and braces between the bells."""
    g, m = c.g, c.m
    fr = G.frame_z((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    for y in ys:
        for z in zs:
            engine_nozzle(c, Xf((stern_x, y, z), fr, 1.0), R, style)
            g.box((stern_x + 0.25 * R, y, z), (0.5 * R, 2.7 * R, 2.7 * R), m("Frame"), chamfer=0.08 * R, kind="engine")
    for i in range(len(ys) - 1):
        for z in zs:
            g.box_between((stern_x - 0.2 * R, ys[i], z), (stern_x - 0.2 * R, ys[i + 1], z), 0.35 * R, 0.5 * R, m("Frame"), chamfer=0.04, kind="engine")
    for j in range(len(zs) - 1):
        for y in ys:
            g.box_between((stern_x - 0.2 * R, y, zs[j]), (stern_x - 0.2 * R, y, zs[j + 1]), 0.35 * R, 0.5 * R, m("Frame"), chamfer=0.04, kind="engine")


def thruster_cluster(c: Ctx, xf: Xf, r: float = 0.45) -> None:
    """A manoeuvring-thruster quad (r = nozzle radius): a small block with four little bells looking along local +x, +y, -y, +z."""
    g, m = c.g, c.m
    xf.box(g, (0, 0, 0), (4.8 * r, 4.8 * r, 3.2 * r), m("Frame"), ch=0.05, kind="rcs")
    for dx, dy, dz in ((1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1)):
        fr = G.frame_z((dx, dy, dz), (0.0, 0.0, 1.0) if dz == 0 else (1.0, 0.0, 0.0)) @ xf.R
        engine_nozzle(c, Xf(xf.p(dx * 2.4 * r, dy * 2.4 * r, dz * 1.6 * r), fr, xf.s), r * 0.9, "astra", detail=0)


# ============================================================================================================== radiators
def radiator_wing(c: Ctx, xf: Xf, length: float, span: float, open_deg: float, style: str = "astra", leaves: int = 3) -> None:
    """A folding radiator hinged along local x at y = 0 (the hull flank), opened by `open_deg` about the hinge (0 = flat on the
    hull, 90 = square to it): `leaves` panels folding on their own hinges, each a frame round a corrugated sheet with coolant
    tubes running along it, headers at the ends, struts from the hull."""
    g, m = c.g, c.m
    hinge = xf.sub((0, 0, 0), _rx(open_deg))
    hinge.cyl(g, (0, 0, 0), (length, 0, 0), 0.7, 0.7, m("Engine"), seg=12, ch=0.05, kind="radiator")
    ls = (span - 0.8) / leaves
    t = 0.5
    for i in range(leaves):
        y0, y1 = 0.8 + i * ls, 0.8 + (i + 1) * ls
        ym = 0.5 * (y0 + y1)
        hinge.box(g, (length / 2, ym, 0), (length - 0.6, ls - 0.5, t), m("Frame"), ch=0.06, kind="radiator")              # the sheet
        for sx in (0.3, length - 0.3):                                                                                  # end frames
            hinge.box(g, (sx, ym, 0), (0.6, ls - 0.3, t + 0.3), m("Engine"), ch=0.05, kind="radiator")
        for sy in (y0 + 0.15, y1 - 0.15):                                                                              # long frames
            hinge.box(g, (length / 2, sy, 0), (length, 0.5, t + 0.3), m("Engine"), ch=0.05, kind="radiator")
        n = max(8, int(length / 1.1))                                                                                   # corrugations across the leaf
        xs = (np.arange(n) + 0.5) * length / n
        cs = np.stack([xs, np.full(n, ym), np.full(n, t / 2 + 0.07)], axis=1)
        g.boxes(hinge.pts(cs), np.array([0.09, (ls - 1.3) / 2, 0.07]) * hinge.s, m("Radiator"), frames=hinge.R, chamfer=0.0, kind="radiator")
        for k in range(4):                                                                                              # coolant tubes along the leaf
            yy = y0 + ls * (0.2 + 0.2 * k)
            hinge.cyl(g, (0.8, yy, t / 2 + 0.2), (length - 0.8, yy, t / 2 + 0.2), 0.12, 0.12, m("Frame"), seg=6, kind="radiator")
        if i < leaves - 1:                                                                                              # the fold hinge
            hinge.cyl(g, (0.3, y1 + 0.02, 0), (length - 0.3, y1 + 0.02, 0), 0.32, 0.32, m("Engine"), seg=8, kind="radiator")
    for sx in (length * 0.2, length * 0.8):                                                                           # struts hull -> panel
        if open_deg > 12.0:
            g.box_between(xf.p(sx, 0, 0) + xf.R[2] * 0.5, hinge.p(sx, span * 0.72, -t / 2 - 0.2), 0.5 * xf.s, 0.5 * xf.s, m("Engine"), chamfer=0.05, kind="radiator")


# ================================================================================================================ antennas
def dish_antenna(c: Ctx, xf: Xf, r: float) -> None:
    """A parabolic dish looking along local +x: a double-skinned bowl, three feed struts and a horn, a yoke behind."""
    g, m = c.g, c.m
    front = [(r, 0.40 * r), (0.8 * r, 0.24 * r), (0.55 * r, 0.11 * r), (0.3 * r, 0.03 * r), (0.0, 0.0)]         # rim to centre: concave side
    back = [(0.0, -0.05 * r), (0.3 * r, -0.02 * r), (0.55 * r, 0.06 * r), (0.8 * r, 0.19 * r), (r, 0.35 * r)]
    xf.revolve(g, front + back + [front[0]], m("Plate"), axis_rot=_Z_TO_X, seg=28, wear=0.5, kind="antenna")
    xf.cyl(g, (-0.05 * r, 0, 0), (-0.35 * r, 0, 0), 0.10 * r, 0.14 * r, m("Frame"), seg=10, kind="antenna")
    for k in range(3):
        a = 2 * math.pi * k / 3 + 0.5
        xf.cyl(g, (0.38 * r, r * 0.92 * math.cos(a), r * 0.92 * math.sin(a)), (0.85 * r, 0, 0), 0.03 * r, 0.03 * r, m("Frame"), seg=5, kind="antenna")
    xf.cyl(g, (0.85 * r, 0, 0), (1.0 * r, 0, 0), 0.07 * r, 0.05 * r, m("Engine"), seg=8, kind="antenna")


def mast(c: Ctx, xf: Xf, h: float, dish: float = 0.0, arms: int = 3, beacon: bool = True) -> None:
    g, m = c.g, c.m
    xf.cyl(g, (0, 0, 0), (0, 0, h), max(0.22, h * 0.018), max(0.14, h * 0.012), m("Frame"), seg=8, kind="antenna")
    xf.cyl(g, (0, 0, 0), (0, 0, 0.6), max(0.5, h * 0.04), max(0.4, h * 0.03), m("Engine"), seg=10, ch=0.04, kind="antenna")
    for k in range(arms):
        z = h * (0.42 + 0.17 * k)
        w = h * 0.22 * (1 - 0.25 * k)
        xf.box(g, (0, 0, z), (0.22, w, 0.22), m("Frame"), ch=0.03, kind="antenna")
        if k % 2 == 0:
            xf.box(g, (0, 0, z + 0.3), (0.35, 0.35, 0.5), m("Engine"), ch=0.04, kind="antenna")
    if dish > 0:
        dish_antenna(c, xf.sub((dish * 0.3, 0, h * 0.62), xf.rot_y(-30)), dish)
    if beacon:
        xf.box(g, (0, 0, h + 0.3), (0.5, 0.5, 0.5), m("Nav"), ch=0.05, kind="nav", a1_all=(NAV_WHITE, 0.0))


def antenna_farm(c: Ctx, xf: Xf, w: float, l: float, n: int = 9) -> None:
    """A cluster of whips, small masts, dishes and array panels on a plinth of l x w metres (local x, y)."""
    g, m, rng = c.g, c.m, c.rng
    xf.box(g, (0, 0, 0.25), (l, w, 0.5), m("Frame"), ch=0.08, kind="antenna")
    for _ in range(n):
        p = xf.sub((rng.uniform(-l / 2 + 1, l / 2 - 1), rng.uniform(-w / 2 + 1, w / 2 - 1), 0.5))
        kind = rng.choice(["whip", "whip", "mast", "dish", "panel"])
        if kind == "whip":
            hh = rng.uniform(3.0, 9.0)
            p.cyl(g, (0, 0, 0), (0, 0, hh), 0.08, 0.04, m("Frame"), seg=6, kind="antenna")
            p.box(g, (0, 0, 0.3), (0.5, 0.5, 0.6), m("Engine"), ch=0.04, kind="antenna")
        elif kind == "mast":
            mast(c, p, rng.uniform(5.0, 11.0), arms=2, beacon=bool(rng.random() < 0.5))
        elif kind == "dish":
            r = rng.uniform(1.4, 3.0)
            p.cyl(g, (0, 0, 0), (0, 0, r * 0.9), 0.2, 0.2, m("Frame"), seg=8, kind="antenna")
            dish_antenna(c, p.sub((0, 0, r + 0.4), p.rot_z(rng.uniform(0, 360)) @ p.rot_y(rng.uniform(-40, 10))), r)
        else:
            hh = rng.uniform(1.6, 3.0)
            p.box(g, (0, 0, hh / 2 + 0.2), (0.4, hh * 1.4, hh), m("Engine"), ch=0.04, kind="antenna")
            p.cyl(g, (0, 0, 0), (0, 0, 0.3), 0.3, 0.3, m("Frame"), seg=8, kind="antenna")


# ==================================================================================================================== hangar
def hangar_mouth(c: Ctx, xf: Xf, width: float, height: float, depth: float = 6.0) -> None:
    """The mouth of a flight-deck tube on a hull face: local x points out of the hull, y is the width, z the height, the origin
    is the centre of the opening on the face. An armoured collar, a lit liner going in, hazard stripes on the sill. Open: the
    hangar's own geometry is seen through it."""
    g, m = c.g, c.m
    t = max(1.4, 0.09 * height)
    out = max(2.0, 0.1 * depth)
    hw, hh = width / 2, height / 2
    for dz in (-1, 1):
        xf.box(g, (out / 2, 0, dz * (hh + t / 2)), (out, width + 2 * t, t), m("Frame"), ch=0.18, kind="hangar")
    for dy in (-1, 1):
        xf.box(g, (out / 2, dy * (hw + t / 2), 0), (out, t, height), m("Frame"), ch=0.18, kind="hangar")
    for dz in (-1, 1):
        xf.box(g, (0.25, 0, dz * (hh + t + 0.6)), (0.5, width + 2 * t + 3.0, 1.2), m("Plate"), ch=0.08, kind="hangar")
    for dy in (-1, 1):
        xf.box(g, (0.25, dy * (hw + t + 0.6), 0), (0.5, 1.2, height + 2 * t), m("Plate"), ch=0.08, kind="hangar")
    for dz in (-1, 1):                                                        # the liner: four walls going in
        xf.box(g, (-depth / 2, 0, dz * (hh + 0.15)), (depth, width + 0.6, 0.3), m("Frame"), ch=0.05, kind="hangar")
    for dy in (-1, 1):
        xf.box(g, (-depth / 2, dy * (hw + 0.15), 0), (depth, 0.3, height + 0.6), m("Frame"), ch=0.05, kind="hangar")
    for dy in (-1, 1):
        for dz in (-1, 1):
            xf.box(g, (-depth / 2, dy * (hw - 0.25), dz * (hh - 0.25)), (depth - 0.6, 0.3, 0.3), m("Lights"), ch=0.0, kind="hangar", aux=0.2)
    for k in range(3):
        xf.box(g, (-1.2 - k * depth / 3.2, 0, hh - 0.2), (0.3, width - 0.8, 0.2), m("Lights"), ch=0.0, kind="hangar", aux=0.2)
    n = max(4, int(width / 1.6))                                              # hazard stripes on the outer sill
    for i in range(n):
        xf.box(g, (out + 0.01, -hw + (i + 0.5) * width / n, -hh - t * 0.5), (0.05, width / n * 0.5, t * 0.8),
               m("Trim") if i % 2 else m("Frame"), ch=0.0, kind="hangar")
    xf.box(g, (out + 0.1, 0, hh + t + 0.15), (0.2, width * 0.9, 0.3), m("Lights"), ch=0.0, kind="hangar", aux=0.15)


# ==================================================================================================================== windows
def window_band(c: Ctx, zone, w: float, a0: float, a1: float, rows: int = 2, pitch_w: float = 2.6, win=(1.4, 0.75), lift: float = 0.5,
                runs=(3, 12), gap=(3.0, 9.0), lift_fn=None) -> int:
    """Rows of windows along a zone at cross position w: panes in runs (some dark: each pane carries a random id in UVMap_D2.y that
    the light material turns into lit or dark and a flicker phase), framed. `lift_fn(a)` gives the height of the surface the panes
    stand on (a plate's thickness). Returns the number of panes."""
    g, m, rng = c.g, c.m, c.rng
    dw = pitch_w / zone.sw(0.5 * (a0 + a1))
    total = 0
    for r in range(rows):
        wr = w + r * dw
        if wr > 0.97:
            break
        cs, ids = [], []
        a = a0 + rng.uniform(0, 4)
        while a < a1 - win[0]:
            run = int(rng.integers(runs[0], runs[1] + 1))
            for k in range(run):
                x = a + k * (win[0] + 0.5)
                if x > a1 - win[0]:
                    break
                cs.append((x, wr))
                ids.append(rng.random())
            a += run * (win[0] + 0.5) + rng.uniform(*gap)
        if not cs:
            continue
        cs = np.array(cs)
        P, N, T = zone.frame(cs[:, 0], cs[:, 1])
        base = lift if lift_fn is None else np.array([lift_fn(x) for x in cs[:, 0]])[:, None] + lift
        Pp = P + N * base
        Fr = G.frames_z(N, T)
        g.boxes(Pp, (win[0] / 2 + 0.16, win[1] / 2 + 0.16, 0.10), m("Frame"), frames=Fr, chamfer=0.03, wear=0.7, kind="window")
        g.boxes(Pp + N * 0.12, (win[0] / 2, win[1] / 2, 0.05), m("Lights"), frames=Fr, chamfer=0.0, kind="window", aux=np.array(ids))
        total += len(cs)
    return total


def window_row(c: Ctx, zone, a: float, w0: float, w1: float, win=(1.3, 0.8), lift: float = 0.5, runs=(3, 9), gap=(2.0, 5.0), lift_fn=None) -> int:
    """One horizontal row of windows across a zone at coordinate a (the decks of a tower: `a` is the height, w runs round): panes in
    runs, framed, each with its own id. Returns the number of panes."""
    g, m, rng = c.g, c.m, c.rng
    swz = zone.sw(a)
    wm = (w1 - w0) * swz
    cs, ids = [], []
    x = rng.uniform(0.0, 2.0)
    while x < wm - win[0]:
        run = int(rng.integers(runs[0], runs[1] + 1))
        for k in range(run):
            xx = x + k * (win[0] + 0.45)
            if xx > wm - win[0]:
                break
            cs.append(w0 + xx / swz)
            ids.append(rng.random())
        x += run * (win[0] + 0.45) + rng.uniform(*gap)
    if not cs:
        return 0
    ws = np.array(cs)
    aa = np.full(len(ws), a)
    P, N, _ = zone.frame(aa, ws)
    T = G.norm(zone.pts(aa, ws + 1e-3) - zone.pts(aa, ws - 1e-3))
    base = lift if lift_fn is None else lift + float(lift_fn(a))
    Pp = P + N * base
    Fr = G.frames_z(N, T)
    g.boxes(Pp, (win[0] / 2 + 0.15, win[1] / 2 + 0.15, 0.10), m("Frame"), frames=Fr, chamfer=0.03, wear=0.7, kind="window")
    g.boxes(Pp + N * 0.12, (win[0] / 2, win[1] / 2, 0.05), m("Lights"), frames=Fr, chamfer=0.0, kind="window", aux=np.array(ids))
    return len(ws)


def light_strips(c: Ctx, zone, w: float, a0: float, a1: float, lit: float = 0.6, lift: float = 0.5, height: float = 0.28, seg=(4.0, 16.0),
                 gap=(3.0, 12.0)) -> None:
    """Broken rows of lit strips on a zone (deck lights that read from kilometres away)."""
    g, m, rng = c.g, c.m, c.rng
    a = a0 + rng.uniform(0, 5)
    cs, ls, ids = [], [], []
    while a < a1 - 2:
        L = min(rng.uniform(*seg), a1 - a)
        if rng.random() < lit:
            cs.append((a + L / 2, w))
            ls.append(L)
            ids.append(rng.random())
        a += L + rng.uniform(*gap)
    if not cs:
        return
    cs = np.array(cs)
    P, N, T = zone.frame(cs[:, 0], cs[:, 1])
    ls = np.array(ls)
    half = np.stack([ls / 2, np.full(len(ls), height / 2), np.full(len(ls), 0.05)], axis=1)
    g.boxes(P + N * lift, half, m("Lights"), frames=G.frames_z(N, T), chamfer=0.0, kind="window", aux=np.array(ids))


# ============================================================================================================== running lights
def nav_light(c: Ctx, p, normal, colour: float, size: float = 1.0, pulse: bool = False) -> None:
    """A running-light fixture at p, its lens looking along `normal`: colour code 0 red / 0.5 green / 1 white (UVMap_D1.x),
    pulse flag in UVMap_D2.y for the keel's pulsing red."""
    g, m = c.g, c.m
    n = G.norm(normal)
    fr = G.frame_z(n, (1.0, 0.0, 0.0) if abs(n[0]) < 0.9 else (0.0, 0.0, 1.0))
    g.box(np.asarray(p) + n * 0.15 * size, (0.7 * size, 0.7 * size, 0.3 * size), m("Frame"), frame=fr, chamfer=0.05, kind="nav")
    g.box(np.asarray(p) + n * 0.34 * size, (0.5 * size, 0.5 * size, 0.1 * size), m("Nav"), frame=fr, chamfer=0.02, kind="nav",
          a1_all=(colour, 0.0), aux=1.0 if pulse else 0.0)


# ============================================================================================================ small details
def _tone(panel: PN.Panel, rng, s: float = 0.05) -> float:
    return float(np.clip(panel.plate.tone + rng.normal(0, s), 0.05, 0.95))


def hatch(c: Ctx, panel: PN.Panel, u: float, v: float, rng, size=(1.0, 0.8)) -> None:
    """An access hatch: a thin lid on a frame, two hinges and a handle."""
    g, m = c.g, c.m
    la, lw = panel.size_m()
    sx, sy = min(size[0], la * 0.7), min(size[1], lw * 0.7)
    if sx < 0.3 or sy < 0.25:
        return
    P, fr = panel.frame_at(u, v)
    n = fr[2]
    g.box(P + n * 0.03, (sx + 0.14, sy + 0.14, 0.06), m("Frame"), frame=fr, chamfer=0.015, kind="hatch")
    g.box(P + n * 0.085, (sx, sy, 0.05), m("Plate"), frame=fr, chamfer=0.015, wear=0.9, kind="hatch", tone=_tone(panel, rng))
    g.box(P + n * 0.14 + fr[1] * (sy * 0.28), (sx * 0.35, 0.07, 0.06), m("Engine"), frame=fr, chamfer=0.01, kind="hatch")
    for sxx in (-1, 1):
        g.box(P + n * 0.08 + fr[0] * (sxx * sx * 0.4) - fr[1] * (sy * 0.5), (0.14, 0.08, 0.08), m("Frame"), frame=fr, chamfer=0.01, kind="hatch")


def vent(c: Ctx, panel: PN.Panel, u: float, v: float, rng, size=(1.6, 0.9)) -> None:
    """A vent grille: a frame with parallel slats leaning one way."""
    g, m = c.g, c.m
    la, lw = panel.size_m()
    sx, sy = min(size[0], la * 0.75), min(size[1], lw * 0.75)
    if sx < 0.4 or sy < 0.3:
        return
    P, fr = panel.frame_at(u, v)
    n = fr[2]
    g.box(P + n * 0.05, (sx + 0.16, sy + 0.16, 0.10), m("Frame"), frame=fr, chamfer=0.02, kind="vent", grime=0.6)
    k = max(3, int(sy / 0.13))
    ys = (np.arange(k) + 0.5) / k * sy - sy / 2
    Fs = np.broadcast_to(_rx(35.0) @ fr, (k, 3, 3))
    g.boxes(P[None] + n[None] * 0.09 + fr[1][None] * ys[:, None], (sx / 2, 0.035, 0.06), m("Engine"), frames=Fs, chamfer=0.0, kind="vent")


def blister(c: Ctx, panel: PN.Panel, u: float, v: float, rng, r: float = 0.6) -> None:
    """A sensor blister: a domed housing on a collar, sometimes with a lens."""
    g, m = c.g, c.m
    la, lw = panel.size_m()
    r = min(r, la * 0.4, lw * 0.4)
    if r < 0.2:
        return
    P, fr = panel.frame_at(u, v)
    g.cylinder(P, P + fr[2] * 0.12, r * 1.2, r * 1.15, m("Frame"), seg=14, chamfer=0.02, kind="blister")
    g.dome(P + fr[2] * 0.1, r, m("Engine"), frame=fr, seg=12, rings=3, squash=0.8, kind="blister")
    if rng.random() < 0.5:
        q = P + fr[2] * (0.1 + r * 0.7) + fr[0] * r * 0.4
        g.cylinder(q, q + fr[0] * 0.1, r * 0.25, r * 0.25, m("Glow"), seg=8, kind="blister")


def lamp(c: Ctx, panel: PN.Panel, u: float, v: float, rng, size: float = 0.5) -> None:
    """A docking / flood lamp: a small housing with a lit lens."""
    g, m = c.g, c.m
    P, fr = panel.frame_at(u, v)
    g.box(P + fr[2] * (0.2 * size), (size, size, 0.4 * size), m("Frame"), frame=fr, chamfer=0.03, kind="lamp")
    g.box(P + fr[2] * (0.43 * size), (0.72 * size, 0.72 * size, 0.06), m("Lights"), frame=fr, chamfer=0.0, kind="lamp", aux=float(rng.random() * 0.5))


def cable_run(c: Ctx, panel: PN.Panel, rng, count: int = 2) -> None:
    """Cables and pipes laid along a panel with clamps."""
    g, m = c.g, c.m
    la, lw = panel.size_m()
    if la < 1.5 or lw < 0.8:
        return
    v0 = rng.uniform(0.25, 0.75)
    for k in range(count):
        v = v0 + (k - (count - 1) / 2) * min(0.14, 0.4 / max(count, 1))
        P0, N0, _ = panel.pts([[0.05, v]])
        P1, N1, _ = panel.pts([[0.95, v]])
        g.cylinders(P0 + N0 * 0.09, P1 + N1 * 0.09, 0.05 + 0.02 * (k % 2), m("Frame") if k % 2 == 0 else m("Engine"), seg=6, kind="cable")
    for uu in (0.2, 0.5, 0.8):
        P, fr = panel.frame_at(uu, v0)
        g.box(P + fr[2] * 0.06, (0.12, 0.16 * count + 0.1, 0.12), m("Frame"), frame=fr, chamfer=0.01, kind="cable")


def stencil(c: Ctx, panel: PN.Panel, u: float, v: float, text: str, height: float, up=(0.0, 0.0, 1.0), mat: str | None = None) -> None:
    P, fr = panel.frame_at(u, v)
    TX.place_text(c.g, text, P, fr[2], height, mat or c.m("Marking"), up=up, depth=0.012, kind="text")
