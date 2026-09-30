"""ASTRA craft v3: the Falcon fighter, the Hammer bomber, the Wasp drone (ASTRA) and the Harpy attack fighter (Kharon Mandate).

Built to be seen from a metre away on the flight deck and from a few hundred metres in flight: a plated, panelled fuselage loft, lofted
wings with hardpoints and lights, tail surfaces, drive bells with a glowing throat, landing gear, canopy, antennas, roundels and
stencils. The vertical extents match v2 (the hangar parks them by their origin): the Falcon's skids reach z = -1.46, the Hammer's
-2.16, the Wasp hangs 0.9 below its origin. x is forward. Budget: <= 150 k triangles each.
"""
from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

import ship3_geo as G
import ship3_hull as H
import ship3_kit as K
import ship3_kit2 as K2
import ship3_loft as LF
import ship3_mandate as MD
import ship3_panels as PN
import ship3_text as TX
from ship3_kit import Ctx, Xf

I3 = np.eye(3)


def craft_style(mandate: bool) -> H.HullStyle:
    """Small plates and panels for a small machine."""
    if mandate:
        st = MD.mandate_style(0.08)
        sch = replace(st.scheme, row_w=(0.5, 1.0), plate_len=(1.0, 3.0), gap_a=(0.03, 0.06), gap_w=(0.03, 0.06), levels=(0.05, 0.08, 0.12), wedge=0.02, shear=(0.3, 0.2),
                      chamfer=0.02, rim=0.05, embed=0.06, min_len=0.6, min_w=0.25, mats=(("Plate", 0.92), ("Frame", 0.05), ("Livery", 0.03)))
        pn = replace(st.panels, min_size=(0.4, 0.3), max_size=(1.6, 1.0), seam=(0.012, 0.025), margin=0.04, lifts=(0.01, 0.02), lift_w=(0.6, 0.4), chamfer=0.006, rim=0.012)
        return replace(st, scheme=sch, panels=pn, p_panels=0.6, detail_density=0.35, stencil_height=0.10)
    from ship3_astra import astra_style
    st = astra_style(0.1)
    sch = replace(st.scheme, row_w=(0.5, 1.0), plate_len=(1.2, 3.5), gap_a=(0.03, 0.05), gap_w=(0.03, 0.05), levels=(0.03, 0.05, 0.07), wedge=0.01, chamfer=0.012,
                  rim=0.035, embed=0.05, min_len=0.6, min_w=0.25, mats=(("Plate", 0.94), ("Frame", 0.06)), tone_sigma=0.1)
    pn = replace(st.panels, min_size=(0.4, 0.3), max_size=(1.5, 1.0), seam=(0.01, 0.02), margin=0.03, lifts=(0.008, 0.016), lift_w=(0.6, 0.4), chamfer=0.005, rim=0.01)
    return replace(st, scheme=sch, panels=pn, p_panels=0.6, detail_density=0.4, stencil_height=0.09)


def airfoil(chord: float, t: float, xle: float, y: float, z0: float = 0.0, droop: float = 0.0) -> np.ndarray:
    """A six-point wing section at span position y: leading edge at xle, thickness t, as 3D points (x, y, z)."""
    pts = [(xle, 0.0), (xle + 0.22 * chord, 0.5 * t), (xle + 0.70 * chord, 0.36 * t), (xle + chord, 0.0), (xle + 0.70 * chord, -0.30 * t), (xle + 0.22 * chord, -0.5 * t)]
    return np.array([(x, y, z0 + z + droop) for x, z in pts])


def wing_loft(root_y: float, tip_y: float, root_chord: float, tip_chord: float, xle_root: float, sweep: float, t_root: float, t_tip: float, z0: float, dihedral: float,
              side: int, n: int = 5) -> LF.Loft:
    """A wing on one side: sections from the root to the tip, swept back by `sweep` (x shift of the leading edge, negative = forward),
    thickness tapering, rising by `dihedral` (z) at the tip."""
    rings, a = [], []
    for i in range(n):
        t = i / (n - 1)
        y = side * (root_y + t * (tip_y - root_y))
        chord = root_chord + (tip_chord - root_chord) * t
        rings.append(airfoil(chord, t_root + (t_tip - t_root) * t, xle_root + sweep * t, y, z0, dihedral * t))
        a.append(t * abs(tip_y - root_y))
    return LF.Loft(a, rings)


def plate_small(c: Ctx, loft: LF.Loft, st: H.HullStyle, zones=None, panel_p: float = 0.6) -> list:
    """Skin, plate and panel a small loft."""
    g = c.g
    out = []
    for k in (range(loft.n) if zones is None else zones):
        z = loft.zone(k)
        z.skin(g, c.m("Frame"))
        out += LF.plate_zone(g, z, c.rng, st.scheme, c.pre)
    for p in out:
        if c.rng.random() < panel_p:
            PN.panelize(g, p, c.rng, st.panels, c.pre, alt_mats=("Frame",))
    return out


def fuselage(c: Ctx, L: float, w: float, h: float, wp, hp, mandate: bool, zo=lambda t: 0.0, n: int = 12, st: H.HullStyle | None = None) -> tuple:
    stations = []
    for i in range(n + 1):
        t = i / n
        sec = LF.blade(w * LF.profile(t, wp), h * LF.profile(t, hp), 0.1) if mandate else LF.chamfer_rect(w * LF.profile(t, wp), h * LF.profile(t, hp), 0.38, top=0.8, bottom=0.7)
        stations.append((-L / 2 + t * L, sec, zo(t)))
    loft = LF.Loft.along_x(stations)
    plates = plate_small(c, loft, st or craft_style(mandate))
    bow = np.array(stations[-1][1])
    st_ = st or craft_style(mandate)
    H.end_face(c, np.array(stations[0][1]), -L / 2, -1.0, st_, zo=stations[0][2], plate=False)
    H.end_face(c, bow, L / 2, 1.0, st_, zo=stations[-1][2], plate=False)
    return loft, plates


def engine(c: Ctx, pos, R: float, style: str) -> None:
    fr = G.frame_z((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    K2.engine_nozzle(c, Xf(pos, fr, 1.0), R, style, detail=0)


def landing_gear(c: Ctx, pts, bottom: float) -> None:
    """Struts down to pads whose underside is at z = bottom: pts = [(x, y, z_top)]."""
    g, m = c.g, c.m
    for (x, y, zt) in pts:
        g.cylinder((x, y, zt), (x, y, bottom + 0.14), 0.05, 0.04, m("Frame"), seg=8, kind="gear")
        g.cylinder((x, y, zt - 0.3), (x + 0.10 * np.sign(x if x != 0 else 1), y, bottom + 0.25), 0.03, 0.03, m("Engine"), seg=6, kind="gear")
        g.box((x, y, bottom + 0.07), (0.5, 0.14, 0.14), m("Frame"), chamfer=0.02, kind="gear")


def roundel(c: Ctx, origin, normal, d: float, up=(1.0, 0.0, 0.0)) -> None:
    TX.astra_emblem(c.g, origin, normal, d, c.m("Marking"), up=up, depth=0.012)


def missile(c: Ctx, p0, length: float, r: float, mandate: bool) -> None:
    g, m = c.g, c.m
    p0 = np.asarray(p0, np.float64)
    g.cylinder(p0, p0 + np.array([length, 0.0, 0.0]), r, r, m("Plate"), seg=8, kind="missile")
    g.cylinder(p0 + np.array([length, 0.0, 0.0]), p0 + np.array([length + r * 3.0, 0.0, 0.0]), r, 0.0001, m("Frame"), seg=8, kind="missile")
    for k in range(4):
        a = math.pi / 2 * k
        g.box(p0 + np.array([r * 2.0, math.cos(a) * r * 1.5, math.sin(a) * r * 1.5]), (r * 2.5, r * 0.15 if k % 2 == 0 else r * 2.4, r * 2.4 if k % 2 == 0 else r * 0.15),
              m("Frame"), chamfer=0.0, kind="missile")


# ============================================================================================================ the craft
def build_falcon(c: Ctx) -> dict:
    """Falcon: Alpha Squadron's fighter, 18 m."""
    g, rng, m = c.g, c.rng, c.m
    L = 18.0
    w, h = L * 0.075, L * 0.06
    wp = [(0.0, 0.62), (0.12, 0.95), (0.5, 1.0), (0.78, 0.7), (1.0, 0.1)]
    hp = [(0.0, 0.7), (0.15, 0.95), (0.5, 1.0), (0.8, 0.75), (1.0, 0.15)]
    st = craft_style(False)
    loft, plates = fuselage(c, L, w, h, wp, hp, False, zo=lambda t: h * 0.12 * max(0.0, t - 0.6), st=st)
    # canopy: a glazed block framed by the fuselage, raked back
    cx = L * 0.2
    g.box((cx, 0, h * 1.02), (L * 0.22, w * 1.1, h * 0.5), m("Glass"), chamfer=0.08, kind="canopy")
    for dy in (-1, 1):
        g.box_between((cx - L * 0.11, dy * w * 0.55, h * 0.95), (cx + L * 0.10, dy * w * 0.28, h * 1.28), 0.07, 0.08, m("Frame"), chamfer=0.01, kind="canopy")
    g.box((cx - L * 0.12, 0, h * 1.02), (0.12, w * 1.3, h * 0.6), m("Frame"), chamfer=0.02, kind="canopy")
    g.box((cx + L * 0.11, 0, h * 1.0), (0.14, w * 1.0, h * 0.45), m("Frame"), chamfer=0.02, kind="canopy")
    # wings
    span, root_c, tip_c = L * 0.72 / 2, L * 0.42, L * 0.14
    for side in (-1, 1):
        wl = wing_loft(w * 0.9, span, root_c, tip_c, -L * 0.28, L * 0.18, 0.30, 0.10, -h * 0.25, 0.25, side)
        plates += plate_small(c, wl, st)
        tip = wl.R[-1].mean(axis=0)
        K2.nav_light(c, tip + np.array([0.0, side * 0.1, 0.1]), np.array([0.0, side, 0.3]), K2.NAV_RED if side > 0 else K2.NAV_GREEN, 0.28)
        for k in range(2):                                                         # missiles on the hardpoints
            yy = side * (w * 1.6 + (span - w) * (0.35 + 0.3 * k))
            missile(c, (-L * 0.16, yy, -h * 0.25 - 0.55), 2.2, 0.11, False)
            g.box((-L * 0.06, yy, -h * 0.25 - 0.22), (0.9, 0.10, 0.34), m("Frame"), chamfer=0.01, kind="missile")
        roundel(c, np.array([-L * 0.14, side * span * 0.55, -h * 0.25 + 0.30 + 0.02]), np.array([0.0, 0.0, 1.0]), 1.5)
    # twin tail fins, canted outwards
    for side in (-1, 1):
        base = np.array([-L * 0.42, side * w * 0.6, h * 0.95])
        tl = LF.Loft([0.0, h * 1.6], [np.array([(base[0] + dx, base[1], base[2]) for dx in (-0.1, 0.9 + 0.05, 1.5, 0.9)])[::-1],
                                       np.array([(base[0] + dx + 1.4, base[1] + side * 0.7, base[2] + h * 1.6) for dx in (-0.1, 0.3, 0.8, 0.2)])[::-1]])
        for kk in range(4):
            z = tl.zone(kk)
            z.skin(g, m("Frame"))
        roundel(c, base + np.array([0.9, side * 0.30, h * 0.65]), np.array([0.0, side, 0.0]), 0.9, up=(0.0, 0.0, 1.0))
    # drive: two bells with glowing throats
    for dy in (-1, 1):
        engine(c, np.array([-L * 0.44, dy * w * 0.6, 0.0]), 0.62, "astra")
    g.box((-L * 0.45, 0, h * 0.7), (0.5, 0.5, 0.2), m("Frame"), chamfer=0.02, kind="engine")
    # intakes, blister, antenna, formation lights
    for dy in (-1, 1):
        g.box((L * 0.02, dy * (w * 1.02), -h * 0.15), (2.2, 0.10, 0.5), m("Frame"), chamfer=0.02, kind="intake")
        g.box((L * 0.02, dy * (w * 1.06), -h * 0.15), (2.0, 0.05, 0.32), m("Engine"), chamfer=0.0, kind="intake")
    g.dome((L * 0.34, 0, h * 0.62), 0.32, m("Engine"), frame=I3, seg=12, rings=3, squash=0.6, kind="blister")
    g.cylinder((-L * 0.36, 0, h * 1.0), (-L * 0.36, 0, h * 1.0 + 0.9), 0.03, 0.015, m("Frame"), seg=6, kind="antenna")
    K2.nav_light(c, np.array([-L * 0.5 + 0.1, 0.0, h * 0.4]), np.array([-1.0, 0.0, 0.2]), K2.NAV_WHITE, 0.3)
    # landing gear: skids reaching z = -1.46
    landing_gear(c, [(L * 0.28, 0.0, -h * 0.7), (-L * 0.15, w * 1.1, -h * 0.7), (-L * 0.15, -w * 1.1, -h * 0.7)], -1.46)
    # stencils and the callsign
    _craft_marks(c, "A", L, h, w)
    H.scatter_details(c, plates, st)
    return {"length_m": 19.1, "cam_az": -35.0, "cam_el": 18.0, "cam_dist": 2.3, "sun_az": -50.0, "sun_el": 32.0, "closeups": [],
            "cuts": None, "notes": "vertical extents kept: skids at z=-1.46"}


def _craft_marks(c: Ctx, fac: str, L: float, h: float, w: float) -> None:
    """Fuselage stencils (a callsign and warning stripes) placed straight on the fuselage sides."""
    g, m = c.g, c.m
    if fac == "A":
        for sy in (-1, 1):
            TX.place_text(g, "ASN", np.array([L * 0.05, sy * (w * 1.0 + 0.02), h * 0.35]), np.array([0.0, sy, 0.0]), 0.42, m("Marking"), depth=0.012)
            TX.place_text(g, "ALPHA", np.array([-L * 0.20, sy * (w * 1.0 + 0.02), h * 0.35]), np.array([0.0, sy, 0.0]), 0.30, m("Marking"), depth=0.012)


def build_hammer(c: Ctx) -> dict:
    """Hammer: Bravo Squadron's bomber, 26 m: a broad fuselage, torpedo on the keel, big wings, twin engines."""
    g, rng, m = c.g, c.rng, c.m
    L = 26.0
    w, h = L * 0.1, L * 0.06
    wp = [(0.0, 0.62), (0.12, 0.95), (0.5, 1.0), (0.78, 0.7), (1.0, 0.1)]
    hp = [(0.0, 0.7), (0.15, 0.95), (0.5, 1.0), (0.8, 0.75), (1.0, 0.15)]
    st = craft_style(False)
    loft, plates = fuselage(c, L, w, h, wp, hp, False, zo=lambda t: h * 0.12 * max(0.0, t - 0.6), st=st)
    cx = L * 0.25
    g.box((cx, 0, h * 1.02), (L * 0.22, w * 1.0, h * 0.5), m("Glass"), chamfer=0.1, kind="canopy")
    for dy in (-1, 1):
        g.box_between((cx - L * 0.11, dy * w * 0.55, h * 0.95), (cx + L * 0.10, dy * w * 0.28, h * 1.28), 0.08, 0.09, m("Frame"), chamfer=0.01, kind="canopy")
    span, root_c, tip_c = L * 0.88 / 2, L * 0.36, L * 0.2
    for side in (-1, 1):
        wl = wing_loft(w * 0.9, span, root_c, tip_c, -L * 0.28, L * 0.06, 0.4, 0.14, -h * 0.25, 0.1, side)
        plates += plate_small(c, wl, st)
        tip = wl.R[-1].mean(axis=0)
        K2.nav_light(c, tip + np.array([0.0, side * 0.1, 0.1]), np.array([0.0, side, 0.3]), K2.NAV_RED if side > 0 else K2.NAV_GREEN, 0.34)
        yy = side * (w * 1.6 + (span - w) * 0.5)
        g.cylinder((-L * 0.18, yy, -h * 0.25 - 0.9), (L * 0.17, yy, -h * 0.25 - 0.9), 0.32, 0.30, m("Plate"), seg=12, chamfer=0.05, kind="torpedo")
        g.cylinder((L * 0.17, yy, -h * 0.25 - 0.9), (L * 0.24, yy, -h * 0.25 - 0.9), 0.30, 0.02, m("Frame"), seg=12, kind="torpedo")
        for xx in (-L * 0.08, L * 0.06):
            g.box((xx, yy, -h * 0.25 - 0.45), (0.30, 0.12, 0.55), m("Frame"), chamfer=0.02, kind="torpedo")
        roundel(c, np.array([-L * 0.14, side * span * 0.55, -h * 0.25 + 0.4 + 0.02]), np.array([0.0, 0.0, 1.0]), 2.0)
    # the keel torpedo
    g.cylinder((-L * 0.2, 0, -h * 1.05), (L * 0.14, 0, -h * 1.05), 0.34, 0.32, m("Plate"), seg=12, chamfer=0.05, kind="torpedo")
    g.cylinder((L * 0.14, 0, -h * 1.05), (L * 0.22, 0, -h * 1.05), 0.32, 0.02, m("Frame"), seg=12, kind="torpedo")
    for side in (-1, 1):
        base = np.array([-L * 0.42, side * w * 0.6, h * 0.95])
        tl = LF.Loft([0.0, h * 1.8], [np.array([(base[0] + dx, base[1], base[2]) for dx in (-0.1, 0.9 + 0.05, 1.8, 0.9)])[::-1],
                                      np.array([(base[0] + dx + 1.8, base[1] + side * 0.8, base[2] + h * 1.8) for dx in (-0.1, 0.3, 0.9, 0.2)])[::-1]])
        for kk in range(4):
            tl.zone(kk).skin(g, m("Frame"))
    for dy in (-1, 1):
        engine(c, np.array([-L * 0.44, dy * w * 0.62, 0.0]), 0.95, "astra")
    for dy in (-1, 1):
        g.box((L * 0.02, dy * (w * 1.02), -h * 0.15), (3.0, 0.12, 0.7), m("Frame"), chamfer=0.02, kind="intake")
    K2.nav_light(c, np.array([-L * 0.5 + 0.1, 0.0, h * 0.4]), np.array([-1.0, 0.0, 0.2]), K2.NAV_WHITE, 0.36)
    landing_gear(c, [(L * 0.28, 0.0, -h * 0.7), (-L * 0.15, w * 1.15, -h * 0.7), (-L * 0.15, -w * 1.15, -h * 0.7)], -2.16)
    for sy in (-1, 1):
        TX.place_text(g, "ASN", np.array([L * 0.07, sy * (w * 1.0 + 0.02), h * 0.35]), np.array([0.0, sy, 0.0]), 0.55, m("Marking"), depth=0.012)
        TX.place_text(g, "BRAVO", np.array([-L * 0.20, sy * (w * 1.0 + 0.02), h * 0.35]), np.array([0.0, sy, 0.0]), 0.36, m("Marking"), depth=0.012)
    H.scatter_details(c, plates, st)
    return {"length_m": 27.6, "cam_az": -35.0, "cam_el": 18.0, "cam_dist": 2.3, "sun_az": -50.0, "sun_el": 32.0, "closeups": [], "cuts": None,
            "notes": "vertical extents kept: skids at z=-2.16"}


def drone_style() -> H.HullStyle:
    """Plates and panels for a 1 m wide drone: fingers of ceramic 15-30 cm wide, panel seams of 5-10 mm."""
    st = craft_style(False)
    sch = replace(st.scheme, row_w=(0.13, 0.28), plate_len=(0.38, 1.1), gap_a=(0.010, 0.020), gap_w=(0.010, 0.020), levels=(0.010, 0.018, 0.028),
                  wedge=0.006, chamfer=0.005, rim=0.014, embed=0.02, min_len=0.22, min_w=0.07, mats=(("Plate", 0.90), ("Frame", 0.10)), tone_sigma=0.12)
    pn = replace(st.panels, min_size=(0.16, 0.11), max_size=(0.7, 0.4), seam=(0.004, 0.009), margin=0.018, lifts=(0.004, 0.008), lift_w=(0.6, 0.4),
                 chamfer=0.003, rim=0.005)
    return replace(st, scheme=sch, panels=pn, p_panels=0.75, detail_density=0.6, stencil_height=0.06, detail_scale=0.28)


def polygon_ring(n: int, ry: float, rz: float, phase: float = 0.0) -> list:
    a = np.linspace(0.0, 2.0 * math.pi, n, endpoint=False) + phase
    return [(ry * math.cos(t), rz * math.sin(t)) for t in a]


def fin_loft(ang_deg: float, r0: float, r1: float, x_front: float, chord0: float, chord1: float, sweep: float, t0: float, t1: float, n: int = 4) -> LF.Loft:
    """A fin standing out of a round body at `ang_deg` (0 = +y, 90 = up) from radius r0 to r1: the front edge at x_front sweeps back by
    `sweep`, the chord tapers, the section is a thick-nosed lens."""
    a = math.radians(ang_deg)
    e_rad = np.array([0.0, math.cos(a), math.sin(a)])
    e_tan = np.array([0.0, -math.sin(a), math.cos(a)])
    rings, av = [], []
    for i in range(n):
        t = i / (n - 1)
        r = r0 + (r1 - r0) * t
        ch = chord0 + (chord1 - chord0) * t
        th = t0 + (t1 - t0) * t
        xf_ = x_front - sweep * t
        sec = [(xf_, 0.0), (xf_ - 0.22 * ch, 0.5 * th), (xf_ - 0.70 * ch, 0.36 * th), (xf_ - ch, 0.0), (xf_ - 0.70 * ch, -0.30 * th), (xf_ - 0.22 * ch, -0.5 * th)]
        rings.append(np.array([np.array([x, 0.0, 0.0]) + r * e_rad + z * e_tan for x, z in sec]))
        av.append(r - r0)
    return LF.Loft(av, rings)


_AX_X = np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]])        # revolve axis (local z) -> world +x


def build_wasp(c: Ctx) -> dict:
    """Wasp: an electronic-warfare and recon drone, ~9 m: a twelve-sided spindle of ceramic plates with frame rings, a gimballed sensor
    head with a glowing lens and whisker probes, two ear dishes, three swept fins (the down-going two carry the running lights) with
    jammer pods, thruster clusters, instrument blisters, a dorsal whip, a belly phased array, one drive bell. Vertical extent kept: the
    fins stop at about z = -0.9."""
    g, rng, m = c.g, c.rng, c.m
    st = drone_style()
    xs = np.linspace(-3.7, 3.9, 19)
    rp = [(-3.7, 0.30), (-3.45, 0.40), (-3.1, 0.49), (-2.4, 0.53), (-1.2, 0.55), (0.0, 0.56), (1.2, 0.55), (2.3, 0.49), (3.2, 0.40), (3.9, 0.29)]

    def radius(x: float) -> float:
        return float(np.interp(x, [p[0] for p in rp], [p[1] for p in rp]))

    stations = [(float(x), polygon_ring(12, radius(x), radius(x) * 0.94, math.pi / 12), 0.0) for x in xs]
    body = LF.Loft.along_x(stations)
    plates = plate_small(c, body, st, panel_p=0.75)
    H.end_face(c, np.array(stations[0][1]), float(xs[0]), -1.0, st, plate=False)
    H.end_face(c, np.array(stations[-1][1]), float(xs[-1]), 1.0, st, plate=False)
    # frame rings at the section joints, with bolt heads
    for x in (-2.75, -1.55, -0.3, 0.95, 2.2, 3.05):
        r = radius(x) * 0.97
        g.revolve([(r, -0.055), (r + 0.075, -0.055), (r + 0.075, 0.055), (r, 0.055), (r, -0.055)], m("Frame"), origin=(x, 0.0, 0.0), frame=_AX_X, seg=24, wear=0.7, kind="ring")
        for k in range(8):
            aa = 2 * math.pi * k / 8 + 0.2
            g.cylinder((x, (r + 0.075) * math.cos(aa), (r + 0.075) * math.sin(aa)), (x, (r + 0.10) * math.cos(aa), (r + 0.10) * math.sin(aa)), 0.018, 0.016,
                       m("Engine"), seg=6, kind="ring")
    # the sensor head: collar, gimbal ring, lens barrel, glowing lens, whisker probes
    g.cylinder((3.9, 0, 0), (4.12, 0, 0), 0.30, 0.29, m("Frame"), seg=16, chamfer=0.02, kind="head")
    g.revolve([(0.30, -0.07), (0.38, -0.07), (0.38, 0.07), (0.30, 0.07), (0.30, -0.07)], m("Engine"), origin=(4.2, 0.0, 0.0), frame=_AX_X, seg=20, wear=0.5, kind="head")
    g.cylinder((4.12, 0, 0), (4.42, 0, 0), 0.25, 0.23, m("Engine"), seg=16, chamfer=0.015, kind="head")
    g.revolve([(0.17, 0.0), (0.22, 0.0), (0.22, 0.03), (0.17, 0.03), (0.17, 0.0)], m("Frame"), origin=(4.42, 0.0, 0.0), frame=_AX_X, seg=20, kind="head")
    g.dome((4.43, 0, 0), 0.17, m("Glow"), frame=_AX_X, seg=16, rings=4, squash=0.55, kind="lens")
    for sy in (-1, 1):
        for sz in (-1, 1):
            g.cylinder((3.98, sy * 0.30, sz * 0.26), (4.62, sy * 0.47, sz * 0.40), 0.014, 0.008, m("Frame"), seg=5, kind="probe")
            g.dome((4.62, sy * 0.47, sz * 0.40), 0.022, m("Lights"), frame=_AX_X, seg=6, rings=2, kind="probe", aux=0.1)
    # ear dishes on short booms
    for sy in (-1, 1):
        d = np.array([0.80, sy * 0.52, 0.30])
        d /= np.linalg.norm(d)
        K2.dish_antenna(c, Xf((2.75, sy * 0.66, 0.32), G.frame_x(d), 1.0), 0.30)
        g.cylinder((2.78, sy * 0.50, 0.14), (2.75, sy * 0.66, 0.32), 0.035, 0.03, m("Frame"), seg=8, kind="boom")
    # three swept fins: dorsal, and the two going down and out (green to starboard, red to port)
    for ang, col in ((90.0, K2.NAV_WHITE), (210.0, K2.NAV_GREEN), (330.0, K2.NAV_RED)):
        fl = fin_loft(ang, 0.42, 1.66, 0.95, 2.35, 1.0, 1.45, 0.16, 0.07, n=5)
        plates += plate_small(c, fl, st, panel_p=0.75)
        a = math.radians(ang)
        er = np.array([0.0, math.cos(a), math.sin(a)])
        tip = fl.R[-1].mean(axis=0)
        g.box_between(tip + np.array([0.15, 0, 0]), tip + np.array([-0.55, 0, 0]), 0.11, 0.11, m("Engine"), up=tuple(er), chamfer=0.01, kind="pod")          # jammer pod
        K2.nav_light(c, tip + np.array([-0.60, 0, 0]), np.array([-1.0, 0.0, 0.0]), col, 0.10)
        for kk in range(3):                                                    # sensor teeth along the leading edge
            rr = 0.62 + 0.34 * kk
            p0 = np.array([0.95 - 1.45 * (rr - 0.42) / 1.24 + 0.03, 0, 0]) + er * rr
            g.box(p0, (0.03, 0.05, 0.20), m("Lights"), frame=G.frame_z(er), chamfer=0.0, kind="sensor", aux=0.15 + 0.2 * kk)
    # the dorsal whip on its plinth
    g.cylinder((0.80, 0, 0.58), (0.80, 0, 0.66), 0.05, 0.05, m("Engine"), seg=8, kind="antenna")
    g.cylinder((0.80, 0, 0.66), (0.80, 0, 1.60), 0.022, 0.008, m("Frame"), seg=6, kind="antenna")
    # drive and thrusters
    engine(c, np.array([-3.84, 0.0, 0.0]), 0.27, "astra")
    for pos, nrm in (((-2.6, 0.0, 0.56), (0.0, 0.0, 1.0)), ((-2.6, 0.0, -0.56), (0.0, 0.0, -1.0)), ((2.6, 0.50, 0.12), (0.0, 1.0, 0.0)), ((2.6, -0.50, 0.12), (0.0, -1.0, 0.0))):
        K2.thruster_cluster(c, Xf(pos, G.frame_z(nrm), 1.0), 0.06)
    # belly phased array: a grid of dark cells in a frame
    g.box((0.6, 0.0, -0.56), (1.9, 0.62, 0.05), m("Frame"), chamfer=0.01, kind="array")
    for i in range(9):
        for j in range(3):
            g.box((-0.15 + i * 0.2, -0.2 + j * 0.2, -0.595), (0.15, 0.15, 0.03), m("Glass"), chamfer=0.0, kind="array")
    # instrument blisters along the flanks and back
    for k in range(7):
        x = -1.9 + 0.8 * k + float(rng.uniform(-0.15, 0.15))
        a = math.radians(float(rng.choice([35.0, 145.0, 215.0, 325.0])))
        nrm = np.array([0.0, math.cos(a), math.sin(a)])
        g.dome(np.array([x, 0.0, 0.0]) + nrm * radius(x) * 0.96, 0.06 + 0.03 * float(rng.random()), m("Engine"), frame=G.frame_z(nrm), seg=10, rings=3, kind="blister")
    # markings on flat marking panels, proud of the plates: the callsign, a roundel, the unit
    for sy in (-1, 1):
        g.box((-1.25, sy * 0.556, 0.0), (0.9, 0.04, 0.22), m("Plate"), chamfer=0.006, wear=0.6, kind="mark")
        TX.place_text(g, "AD-09", np.array([-1.25, sy * 0.578, 0.0]), np.array([0.0, sy, 0.0]), 0.12, m("Marking"), up=(0.0, 0.0, 1.0), depth=0.01)
        g.cylinder((0.25, sy * 0.54, 0.0), (0.25, sy * 0.585, 0.0), 0.15, 0.145, m("Plate"), seg=20, chamfer=0.004, kind="mark")
        TX.astra_emblem(g, np.array([0.25, sy * 0.587, 0.0]), np.array([0.0, sy, 0.0]), 0.26, m("Marking"), up=(0.0, 0.0, 1.0), depth=0.008)
        g.box((-2.3, sy * 0.535, 0.0), (0.5, 0.04, 0.2), m("Plate"), chamfer=0.006, wear=0.6, kind="mark")
        TX.place_text(g, "ASN", np.array([-2.3, sy * 0.557, 0.0]), np.array([0.0, sy, 0.0]), 0.11, m("Marking"), up=(0.0, 0.0, 1.0), depth=0.01)
    H.scatter_details(c, plates, st)
    return {"length_m": 9.0, "cam_az": -40.0, "cam_el": 20.0, "lens": 70.0, "sun_az": -50.0, "sun_el": 32.0, "closeups": [], "cuts": None,
            "notes": "vertical extent kept: fins reach about z=-0.9"}



def build_harpy(c: Ctx) -> dict:
    """Harpy: the Mandate's attack fighter, 16 m: forward-swept wings, a single tail blade, cannons in the wing roots, patched."""
    g, rng, m = c.g, c.rng, c.m
    L = 16.0
    w, h = L * 0.075, L * 0.06
    wp = [(0.0, 0.62), (0.12, 0.95), (0.5, 1.0), (0.78, 0.7), (1.0, 0.1)]
    hp = [(0.0, 0.7), (0.15, 0.95), (0.5, 1.0), (0.8, 0.75), (1.0, 0.15)]
    st = craft_style(True)
    loft, plates = fuselage(c, L, w, h, wp, hp, True, zo=lambda t: h * 0.12 * max(0.0, t - 0.6), st=st)
    cx = L * 0.22
    g.box((cx, 0, h * 1.0), (L * 0.18, w * 0.9, h * 0.4), m("Glass"), chamfer=0.07, kind="canopy")
    g.box((cx - L * 0.1, 0, h * 1.0), (0.12, w * 1.1, h * 0.5), m("Frame"), chamfer=0.02, kind="canopy")
    span, root_c, tip_c = L * 0.72 * 1.1 / 2, L * 0.42, L * 0.14
    for side in (-1, 1):
        wl = wing_loft(w * 0.9, span, root_c, tip_c, -L * 0.28, -L * 0.18, 0.28, 0.10, -h * 0.25, -0.2, side)
        plates += plate_small(c, wl, st)
        tip = wl.R[-1].mean(axis=0)
        if side > 0:
            K2.nav_light(c, tip + np.array([0.0, side * 0.1, 0.1]), np.array([0.0, side, 0.3]), K2.NAV_RED, 0.28, pulse=True)
        yy = side * (w * 1.1)
        g.cylinder((L * 0.05, yy, -h * 0.25), (L * 0.26, yy, -h * 0.25), 0.07, 0.06, m("Engine"), seg=8, kind="cannon")           # cannons in the wing roots
        g.cylinder((L * 0.25, yy, -h * 0.25), (L * 0.28, yy, -h * 0.25), 0.10, 0.10, m("Frame"), seg=8, kind="cannon")
        ym = side * (w * 1.6 + (span - w) * 0.55)
        missile(c, (-L * 0.14, ym, -h * 0.25 - 0.4), 1.8, 0.09, True)
        for xx in (-L * 0.14 + 0.35, -L * 0.14 + 1.25):                                  # the pylons that hold it to the wing
            g.box((xx, ym, -h * 0.25 - 0.26), (0.5, 0.07, 0.34), m("Frame"), chamfer=0.01, kind="missile")
        if side > 0:
            MD.tally_marks(c, wl.zone(0), 1.0, 0.5, 7, 0.12)
    base = np.array([-L * 0.44, 0.0, h * 0.95])                  # the single tail blade
    tl = LF.Loft([0.0, h * 2.6], [np.array([(base[0] + dx, base[1] + dy, base[2]) for dx, dy in ((-0.3, -0.06), (1.6, -0.08), (1.6, 0.08), (-0.3, 0.06))]),
                                    np.array([(base[0] + dx + 1.9, base[1] + dy * 0.4, base[2] + h * 2.6) for dx, dy in ((-0.3, -0.06), (0.4, -0.08), (0.4, 0.08), (-0.3, 0.06))])])
    for kk in range(4):
        tl.zone(kk).skin(g, m("Frame"))
    for dy in (-1, 1):
        engine(c, np.array([-L * 0.44, dy * w * 0.6, 0.0]), 0.6, "mandate")
    MD.tally_marks(c, loft.zone(6), L * 0.05, 0.5, 8, 0.16)
    TX.mandate_mark(g, np.array([-L * 0.30, w * 1.02, h * 0.3]), np.array([0.0, 1.0, 0.0]), 0.7, m("Marking"))
    K2.nav_light(c, np.array([-L * 0.5 + 0.1, 0.0, h * 0.2]), np.array([-1.0, 0.0, 0.2]), K2.NAV_RED, 0.3, pulse=True)
    landing_gear(c, [(L * 0.28, 0.0, -h * 0.7), (-L * 0.15, w * 1.1, -h * 0.7), (-L * 0.15, -w * 1.1, -h * 0.7)], -1.4)
    H.scatter_details(c, plates, st)
    MD.patches(c, plates, st, p=0.25)
    return {"length_m": 17.0, "cam_az": -35.0, "cam_el": 18.0, "cam_dist": 2.3, "sun_az": -50.0, "sun_el": 32.0, "closeups": [], "cuts": None}
