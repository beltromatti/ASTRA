"""ASTRA ships v3 — the parts kit: turrets, launchers, engines, radiators, antennas, hangar mouths, windows, running lights.

Every part is built in its own frame (x forward, y left, z out of the hull, units of `s` metres unless a value is said to be in
metres) and placed with an `Xf`; sub-parts nest (a barrel group elevates about its trunnion) and flat faces can be plated like
hull (ship3_loft.PlanarZone). Material names are `<prefix><Part>` (`MI_HULL_A_Plate`, ...).
"""
from __future__ import annotations

import math

import numpy as np

import ship3_geo as G
import ship3_loft as LF
import ship3_panels as PN


class Xf:
    """A placement: origin, rotation (rows = the local axes in world space) and a uniform scale."""

    def __init__(self, origin=(0.0, 0.0, 0.0), R=None, s: float = 1.0):
        self.o = np.asarray(origin, np.float64)
        self.R = np.eye(3) if R is None else np.asarray(R, np.float64)
        self.s = float(s)

    def p(self, x=0.0, y=0.0, z=0.0):
        return self.o + (np.array([x, y, z], np.float64) * self.s) @ self.R

    def pts(self, a):
        return self.o + (np.asarray(a, np.float64) * self.s) @ self.R

    def sub(self, off=(0.0, 0.0, 0.0), rot=None, s: float = 1.0) -> "Xf":
        """A child placement at local `off`, turned by the row-basis `rot` (in this frame's local axes), scaled by s."""
        R2 = np.eye(3) if rot is None else np.asarray(rot, np.float64)
        return Xf(self.p(*off), R2 @ self.R, self.s * s)

    def rot_y(self, deg: float) -> np.ndarray:
        """Row basis of a turn about local y (positive raises +x towards +z)."""
        a = math.radians(deg)
        c, s = math.cos(a), math.sin(a)
        return np.array([[c, 0.0, s], [0.0, 1.0, 0.0], [-s, 0.0, c]])

    def rot_z(self, deg: float) -> np.ndarray:
        a = math.radians(deg)
        c, s = math.cos(a), math.sin(a)
        return np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])

    def rot_x(self, deg: float) -> np.ndarray:
        a = math.radians(deg)
        c, s = math.cos(a), math.sin(a)
        return np.array([[1.0, 0.0, 0.0], [0.0, c, s], [0.0, -s, c]])

    # ---------------------------------------------------------------- builders (sizes in local units, chamfers in metres)
    def box(self, g, c, size, mat, ch=0.05, **kw):
        g.box(self.p(*c), np.asarray(size, np.float64) * self.s, mat, frame=self.R, chamfer=ch, **kw)

    def cyl(self, g, a, b, r0, r1, mat, seg=16, ch=0.0, **kw):
        g.cylinder(self.p(*a), self.p(*b), r0 * self.s, r1 * self.s, mat, seg=seg, chamfer=ch, **kw)

    def prism(self, g, poly, h, mat, z0=0.0, ch=0.0, taper=1.0, **kw):
        poly = np.asarray(poly, np.float64) * self.s
        g.prism(poly, h * self.s, mat, origin=self.p(0, 0, z0), frame=self.R, chamfer=ch, taper=taper, **kw)

    def revolve(self, g, prof, mat, at=(0.0, 0.0, 0.0), axis_rot=None, seg=24, **kw):
        """Surface of revolution about the local z (or the axis given by the rotation `axis_rot`, rows in local axes)."""
        pr = np.asarray(prof, np.float64) * self.s
        fr = self.R if axis_rot is None else np.asarray(axis_rot, np.float64) @ self.R
        g.revolve(pr, mat, origin=self.p(*at), frame=fr, seg=seg, **kw)

    def dome(self, g, at, r, mat, squash=1.0, seg=16, rings=4, **kw):
        g.dome(self.p(*at), r * self.s, mat, frame=self.R, seg=seg, rings=rings, squash=squash, **kw)

    def zone(self, o, ea, ew, La, Lw) -> LF.PlanarZone:
        """A plate-able rectangle on a face: origin `o`, axes ea (length La) and ew (width Lw), local units."""
        return LF.PlanarZone(self.p(*o), np.asarray(ea, np.float64) @ self.R, np.asarray(ew, np.float64) @ self.R, La * self.s, Lw * self.s)


class Ctx:
    """What a ship build carries around: the geometry, the random stream, the faction's material prefix."""

    def __init__(self, g: G.Geo, rng: np.random.Generator, pre: str, detail: float = 1.0):
        self.g, self.rng, self.pre, self.detail = g, rng, pre, detail

    def m(self, part: str) -> str:
        return self.pre + part


def _rot_about(axis, deg):
    return G.rot_axis(axis, math.radians(deg))


# ================================================================================================================ turrets
def railgun_turret(c: Ctx, xf: Xf, barrels: int = 2, elev: float = 10.0, style: str = "astra", plate: bool = True) -> None:
    """A heavy turret (scale 1 = a 13 m gun house): barbette and roller ring, an angular armoured house with plated cheeks, a
    mantlet, rail barrels with insulator rings, recoil cylinders and muzzle brakes. x is the direction of fire."""
    g, m = c.g, c.m
    mandate = style == "mandate"
    # barbette: the ring the house turns on
    xf.cyl(g, (0, 0, 0), (0, 0, 1.5), 6.2, 6.2, m("Frame"), seg=28, ch=0.12, kind="turret")
    xf.cyl(g, (0, 0, 1.2), (0, 0, 1.6), 6.7, 6.7, m("Engine"), seg=28, ch=0.1, kind="turret")             # the roller ring
    for k in range(12):                                                                                        # bolt heads on the ring
        a = 2 * math.pi * k / 12
        xf.cyl(g, (6.45 * math.cos(a), 6.45 * math.sin(a), 1.4), (6.45 * math.cos(a), 6.45 * math.sin(a), 1.75), 0.16, 0.14, m("Frame"),
               seg=6, kind="turret")
    # the house: an elongated octagon narrowing to the front, sloped glacis
    if mandate:
        poly = [(-6.4, -3.4), (-3.0, -5.0), (2.8, -4.2), (5.4, -2.0), (5.4, 2.0), (2.8, 4.2), (-3.0, 5.0), (-6.4, 3.4)]
    else:
        poly = [(-6.6, -3.2), (-4.4, -4.9), (2.6, -4.9), (5.6, -2.6), (5.6, 2.6), (2.6, 4.9), (-4.4, 4.9), (-6.6, 3.2)]
    xf.prism(g, poly, 3.6, m("Plate"), z0=1.6, ch=0.35, taper=0.86, wear=0.9, kind="turret")
    xf.prism(g, [(-4.6, -3.0), (0.8, -3.6), (3.6, -1.7), (3.6, 1.7), (0.8, 3.6), (-4.6, 3.0)], 0.7, m("Plate"), z0=5.2, ch=0.16, taper=0.9, kind="turret")
    # plated cheeks, roof panels and small hatches
    if plate:
        for side in (-1, 1):
            z = xf.zone((-5.0, side * 4.55 if not mandate else side * 4.9, 1.9), (1, 0, 0), (0, 0, 1), 9.0, 3.0)
            _plate_flat(c, z, side, (1.4, 3.2), (0.8, 1.6), 0.08)
        z = xf.zone((-4.4, -2.9, 5.9), (1, 0, 0), (0, 1, 0), 8.0, 5.8)
        _plate_flat(c, z, 1, (1.5, 3.5), (1.2, 2.4), 0.08)
    # the mantlet and the trunnion block
    xf.box(g, (5.4, 0, 3.4), (1.6, 5.4, 2.6), m("Frame"), ch=0.12, kind="turret")
    xf.box(g, (5.9, 0, 3.4), (0.5, 4.2, 1.9), m("Engine"), ch=0.08, kind="turret")
    # the barrels: elevated together about the trunnion
    gap = 2.3 if barrels > 1 else 0.0
    bx = xf.sub((5.6, 0, 3.4), xf.rot_y(elev))
    for k in range(barrels):
        y = (k - (barrels - 1) / 2) * gap
        bx.box(g, (7.6, y, 0), (15.2, 0.75, 0.95), m("Engine"), ch=0.06, kind="barrel")                 # the rail, 15 m
        bx.box(g, (4.0, y, 0), (7.4, 1.5, 1.7), m("Frame"), ch=0.1, kind="barrel")                     # the shroud round the breech end
        for j in range(5):                                                                              # insulator rings
            bx.box(g, (6.8 + j * 1.9, y, 0), (0.28, 1.15, 1.35), m("Frame"), ch=0.04, kind="barrel")
        bx.box(g, (15.6, y, 0), (1.5, 1.35, 1.35), m("Frame"), ch=0.08, kind="barrel")                  # muzzle brake
        bx.box(g, (16.4, y, 0), (0.3, 0.7, 0.7), m("Glow") if not mandate else m("Radiator"), ch=0.03, kind="barrel")
        for sy in (-1, 1):                                                                              # recoil cylinders
            bx.cyl(g, (0.8, y + sy * 0.95, 0.15), (7.0, y + sy * 0.95, 0.15), 0.26, 0.26, m("Engine"), seg=10, kind="barrel")
    # a sensor blister and the hatch on the roof
    xf.dome(g, (-1.5, 1.2, 5.9), 0.7, m("Frame"), squash=0.7, seg=12, rings=3, kind="turret")
    xf.box(g, (-3.2, -1.4, 5.92), (1.2, 1.0, 0.1), m("Frame"), ch=0.03, kind="turret")


def _plate_flat(c: Ctx, zone: LF.PlanarZone, side: int, plate_len: tuple, row_w: tuple, thick: float) -> None:
    """Small plating on a flat face: plates and a light panelling (used on turret cheeks, tower sides, ...)."""
    sch = LF.Scheme(row_w=row_w, plate_len=plate_len, gap_a=(0.06, 0.12), gap_w=(0.06, 0.12), levels=(thick, thick * 1.4), level_weights=(0.6, 0.4),
                    chamfer=0.03, rim=0.06, embed=0.08, tone_sigma=0.1, mats=(("Plate", 1.0),), min_len=1.0)
    plates = LF.plate_zone(c.g, zone, c.rng, sch, c.pre)
    sty = PN.PanelStyle(min_size=(1.0, 0.7), max_size=(3.0, 2.0), seam=(0.03, 0.06), margin=0.08, lifts=(0.02, 0.04), lift_w=(0.6, 0.4), chamfer=0.015, rim=0.03, p_stop=0.5)
    for p in plates:
        if c.rng.random() < 0.5:
            PN.panelize(c.g, p, c.rng, sty, c.pre)


def laser_battery(c: Ctx, xf: Xf, style: str = "astra") -> None:
    """A laser battery (scale 1 = a 4 m dome): pedestal, a domed housing with cooling fins and a lensed emitter."""
    g, m = c.g, c.m
    xf.cyl(g, (0, 0, 0), (0, 0, 0.8), 1.6, 1.5, m("Frame"), seg=16, ch=0.06, kind="laser")
    xf.dome(g, (0, 0, 0.7), 1.7, m("Plate"), squash=0.75, seg=18, rings=4, wear=0.8, kind="laser")
    for k in range(6):                                                    # fins
        a = math.radians(-80 + 32 * k)
        xf.box(g, (-0.9 * math.cos(a), 1.5 * math.sin(a), 1.5), (0.16, 0.16, 0.7), m("Engine"), ch=0.03, kind="laser")
    em = xf.sub((1.3, 0, 1.3), xf.rot_y(-8))
    em.cyl(g, (0, 0, 0), (2.4, 0, 0), 0.42, 0.34, m("Engine"), seg=12, ch=0.05, kind="laser")
    em.cyl(g, (2.3, 0, 0), (2.42, 0, 0), 0.28, 0.28, m("Glow"), seg=12, kind="laser")


def pd_mount(c: Ctx, xf: Xf, style: str = "astra") -> None:
    """A point-defence mount (scale 1 = a 3 m turntable): pedestal, cradle, a cluster of rotary barrels, ammunition drum, eye."""
    g, m = c.g, c.m
    xf.cyl(g, (0, 0, 0), (0, 0, 0.5), 1.3, 1.2, m("Frame"), seg=14, ch=0.05, kind="pd")
    xf.box(g, (0, 0, 1.1), (1.7, 1.9, 1.2), m("Plate"), ch=0.08, kind="pd")
    xf.box(g, (-0.5, 0, 1.9), (0.9, 1.1, 0.6), m("Frame"), ch=0.05, kind="pd")
    b = xf.sub((0.6, 0, 1.25), xf.rot_y(-12))
    for k in range(6):
        a = 2 * math.pi * k / 6
        b.cyl(g, (0, 0.28 * math.cos(a), 0.28 * math.sin(a)), (2.3, 0.28 * math.cos(a), 0.28 * math.sin(a)), 0.09, 0.09, m("Engine"), seg=6, kind="pd")
    b.cyl(g, (0.4, 0, 0), (2.5, 0, 0), 0.42, 0.4, m("Frame"), seg=10, kind="pd")
    xf.cyl(g, (-0.4, 0.95, 1.0), (0.2, 0.95, 1.0), 0.45, 0.45, m("Frame"), seg=10, kind="pd")
    xf.dome(g, (-0.3, -0.8, 1.7), 0.3, m("Glow"), squash=0.8, seg=8, rings=2, kind="pd")


def vls_bank(c: Ctx, xf: Xf, cols: int, rows: int, cell: float = 3.2, open_frac: float = 0.06) -> None:
    """A vertical launch bank: a raised block with a grid of hatches (a few open, the dark cells showing). Unit: metres."""
    g, m, rng = c.g, c.m, c.rng
    w, d = cols * cell, rows * cell
    xf.box(g, (0, 0, 0.55), (w + 1.4, d + 1.4, 1.1), m("Frame"), ch=0.12, kind="vls")
    xf.box(g, (0, 0, 1.08), (w + 0.7, d + 0.7, 0.16), m("Plate"), ch=0.06, kind="vls")
    cx = (np.arange(cols) - (cols - 1) / 2) * cell
    cy = (np.arange(rows) - (rows - 1) / 2) * cell
    for i in range(cols):
        for j in range(rows):
            p = (cx[i], cy[j], 1.24)
            if rng.random() < open_frac:
                xf.box(g, (p[0], p[1], 1.18), (cell * 0.78, cell * 0.78, 0.06), m("Frame"), ch=0.0, kind="vls")
                hinge = xf.sub((p[0] - cell * 0.39, p[1], 1.3), xf.rot_y(-72))
                hinge.box(g, (cell * 0.39, 0, 0), (cell * 0.78, cell * 0.78, 0.16), m("Plate"), ch=0.05, kind="vls")
            else:
                xf.box(g, p, (cell * 0.8, cell * 0.8, 0.2), m("Plate"), ch=0.05, kind="vls")
                xf.box(g, (p[0], p[1], 1.36), (cell * 0.5, cell * 0.5, 0.05), m("Frame"), ch=0.02, kind="vls")
                for sx in (-1, 1):
                    for sy in (-1, 1):
                        xf.cyl(g, (p[0] + sx * cell * 0.36, p[1] + sy * cell * 0.36, 1.32), (p[0] + sx * cell * 0.36, p[1] + sy * cell * 0.36, 1.4),
                               0.06, 0.05, m("Frame"), seg=5, kind="vls")
