"""ASTRA boarding craft v3 (ABBORDAGGI-2): the Kharon Mandate's boarding skiff and the Aquila's Kestrel assault shuttle.

Both are boats that go to a hull and latch to a hatch on her skin: they fly nose first, and the nose is the business end: a docking collar (the skiff's a cutting ring with clamps,
ASTRA's a mating collar with a seal) whose tip is exactly the craft's half length (7.5 m and 9.0 m: the battle docks it with the collar's lip on the skin, Source/ASTRA/AstraBoardCraft.cpp).
x is forward, the origin the middle of the hull, vertical extents symmetric about it. Budget: <= 150 k triangles each, like the other craft (ship3_craft.py is the style they follow).
"""
from __future__ import annotations

import math

import numpy as np

import ship3_geo as G
import ship3_hull as H
import ship3_kit2 as K2
import ship3_loft as LF
import ship3_mandate as MD
import ship3_text as TX
import ship3_craft as CR
from ship3_kit import Ctx, Xf

I3 = np.eye(3)
_AX_X = np.array([[0.0, 1.0, 0.0], [0.0, 0.0, 1.0], [1.0, 0.0, 0.0]])      # revolve axis (local z) -> world +x


def _collar(c: Ctx, x0: float, r_out: float, r_in: float, length: float, lugs: int, lug_r: float, phase: float = 0.0) -> None:
    """A docking collar on the nose: a thick ring from x0 to x0 + length, clamp lugs round it, and a plug in the middle."""
    g, m = c.g, c.m
    g.revolve([(r_in, 0.0), (r_out, 0.0), (r_out, length), (r_in, length), (r_in, 0.0)], m("Frame"), origin=(x0, 0.0, 0.0), frame=_AX_X, seg=32, wear=0.8, kind="collar")
    for k in range(lugs):
        a = phase + 2 * math.pi * k / lugs
        y, z = math.cos(a), math.sin(a)
        p0 = np.array([x0 - 0.9, y * (r_out + 0.12), z * (r_out + 0.12)])
        p1 = np.array([x0 + length - 0.05, y * (r_out + 0.02 + lug_r), z * (r_out + 0.02 + lug_r)])
        g.box_between(p0, p1, lug_r * 1.6, lug_r * 1.6, m("Frame"), up=(0.0, y, z), chamfer=0.04, kind="clamp")


def _fin(c: Ctx, base, height: float, chord: float, sweep: float, thick: float, tip_chord: float) -> None:
    """A fin standing up from `base` (x, y, z), swept back by `sweep` at the tip: a thin blade of four sections."""
    g, m = c.g, c.m
    bx, by, bz = base
    lo = np.array([(bx, by - thick, bz), (bx - chord, by - thick, bz), (bx - chord, by + thick, bz), (bx, by + thick, bz)])
    hi = np.array([(bx - sweep, by - thick * 0.6, bz + height), (bx - sweep - tip_chord, by - thick * 0.6, bz + height),
                   (bx - sweep - tip_chord, by + thick * 0.6, bz + height), (bx - sweep, by + thick * 0.6, bz + height)])
    fl = LF.Loft([0.0, height], [lo[::-1], hi[::-1]])
    for k in range(4):
        fl.zone(k).skin(g, m("Frame"))


# ====================================================================================================================== the skiff
def build_skiff(c: Ctx) -> dict:
    """Skiff: the Mandate's boarding craft, 15 m: an armoured wedge of heavy plates with a cutting ring on its nose (a ring of cutters and a hot throat inside it, clamp arms round it),
    grapple arms folded on the flanks, two big bells and a row of patches: ten men and the means to open a hull."""
    g, m = c.g, c.m
    L = 14.2                                    # the hull: x from -7.1 to 7.1; the collar takes the nose to 7.5
    w, h = 2.7, 1.75                            # half width and half height amidships
    wp = [(0.0, 0.64), (0.10, 0.92), (0.45, 1.0), (0.80, 0.86), (1.0, 0.46)]
    hp = [(0.0, 0.80), (0.12, 0.96), (0.50, 1.0), (0.85, 0.82), (1.0, 0.50)]
    st = CR.craft_style(True)
    loft, plates = CR.fuselage(c, L, w, h, wp, hp, False, st=st, n=10)
    # the nose: the cutting ring (cutters round a hot throat, the plug of the boarding tube) and the four clamp arms that hold it to the hull
    _collar(c, 7.1, 1.22, 0.88, 0.40, 0, 0.0)
    g.revolve([(0.52, 0.0), (0.88, 0.0), (0.88, 0.30), (0.52, 0.30), (0.52, 0.0)], m("Glow"), origin=(7.12, 0.0, 0.0), frame=_AX_X, seg=32, wear=0.0, kind="cutter")
    g.cylinder((7.05, 0, 0), (7.36, 0, 0), 0.53, 0.50, m("Engine"), seg=24, kind="hatch")
    for k in range(10):                         # the cutters: teeth on the ring's lip
        a = 2 * math.pi * k / 10
        g.box((7.46, math.cos(a) * 1.05, math.sin(a) * 1.05), (0.12, 0.22, 0.12), m("Engine"), frame=G.frame_z((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)), chamfer=0.01, kind="cutter")
    for sy in (-1, 1):
        for sz in (-1, 1):
            g.box_between((6.0, sy * 1.55, sz * 0.95), (7.38, sy * 1.30, sz * 0.78), 0.34, 0.34, m("Frame"), up=(0.0, sy, sz), chamfer=0.04, kind="clamp")
            g.box((6.05, sy * 1.62, sz * 1.0), (0.7, 0.5, 0.5), m("Plate"), chamfer=0.05, kind="clamp")
    # the armour skirts and the grapple arms folded on the flanks
    for sy in (-1, 1):
        g.box((-0.9, sy * (w + 0.08), -0.62), (5.6, 0.20, 1.35), m("Plate"), chamfer=0.07, wear=0.9, kind="skirt")
        for xb in (-3.3, -0.9, 1.5):
            g.box((xb, sy * (w + 0.10), -0.62), (0.45, 0.30, 1.55), m("Frame"), chamfer=0.05, kind="skirt")
        for dz in (-0.9, 0.5):
            g.box_between((4.6, sy * (w * 0.90), dz), (2.2, sy * (w * 0.92), dz), 0.30, 0.30, m("Frame"), chamfer=0.03, kind="grapple")
            g.box_between((4.6, sy * (w * 0.90), dz), (5.5, sy * (w * 0.72), dz + 0.1), 0.22, 0.22, m("Engine"), chamfer=0.02, kind="grapple")
    # the top: a ridge of armour, the hatch the men go out by, a sensor blister, whips
    g.box((-0.5, 0.0, h * 0.98 + 0.2), (8.0, 1.1, 0.5), m("Frame"), chamfer=0.10, kind="ridge")
    g.box((-3.4, 0.0, h * 0.98 + 0.45), (1.6, 1.5, 0.35), m("Plate"), chamfer=0.07, kind="hatch")
    g.dome((2.2, 0.0, h * 0.98 + 0.4), 0.42, m("Engine"), frame=I3, seg=12, rings=3, squash=0.6, kind="blister")
    for yy, xx in ((0.55, -5.2), (-0.55, -5.9)):
        g.cylinder((xx, yy, h * 0.95), (xx, yy, h * 0.95 + 1.5), 0.03, 0.012, m("Frame"), seg=6, kind="antenna")
    # the drive: two big bells at the stern, in a heat shield
    for sy in (-1, 1):
        g.box((-6.95, sy * 1.18, 0.15), (0.6, 2.0, 2.0), m("Frame"), chamfer=0.08, kind="engine")
        CR.engine(c, np.array([-7.2, sy * 1.18, 0.15]), 0.66, "mandate")
    # the ramp the men come back by (a framed door between the bells) and the tow lug under it
    g.box((-7.16, 0.0, 0.1), (0.14, 1.5, 1.9), m("Frame"), chamfer=0.04, kind="ramp")
    g.box((-7.22, 0.0, 0.1), (0.08, 1.2, 1.6), m("Engine"), chamfer=0.02, kind="ramp")
    # thrusters on the shoulders
    for sy in (-1, 1):
        K2.thruster_cluster(c, Xf((5.2, sy * (w * 0.62), h * 0.62), G.frame_z((0.0, sy, 0.0), (1.0, 0.0, 0.0)), 1.0), 0.06)
        K2.thruster_cluster(c, Xf((-5.6, sy * (w * 0.9), -h * 0.6), G.frame_z((0.0, sy, 0.0), (1.0, 0.0, 0.0)), 1.0), 0.06)
    # the Mandate's marks and a few tallies, patches over the plates
    for sy in (-1, 1):
        TX.mandate_mark(g, np.array([-0.9, sy * (w + 0.30), 0.45]), np.array([0.0, sy, 0.0]), 1.3, m("Marking"))
        TX.place_text(g, "SKIFF", np.array([-1.2, sy * (w + 0.30), -0.62]), np.array([0.0, sy, 0.0]), 0.28, m("Marking"), depth=0.012)
    K2.nav_light(c, np.array([-5.2, 0.0, h * 0.98 + 0.12]), np.array([0.0, 0.0, 1.0]), K2.NAV_RED, 0.3, pulse=True)
    H.scatter_details(c, plates, st)
    MD.patches(c, plates, st, p=0.3)
    return {"length_m": 15.0, "cam_az": -35.0, "cam_el": 18.0, "cam_dist": 2.3, "sun_az": -50.0, "sun_el": 32.0, "exposure": 0.7, "closeups": [], "cuts": None,
            "notes": "the nose tip is at x = +7.5 (AstraBoardCraft.cpp: the Skiff's half length)"}


# ==================================================================================================================== the Kestrel
def build_kestrel(c: Ctx) -> dict:
    """Kestrel: ASTRA's assault shuttle, 19 m: a broad troop-carrier hull with a mating collar on its nose (a seal ring, six clamps), a raised cockpit, troop doors on the flanks, stub
    wings with a nacelle on each tip, a dorsal fin, the Fleet's marks and the callsign: twelve marines and a pilot's crew."""
    g, m = c.g, c.m
    L = 16.8                                    # the hull: x from -8.4 to 8.4; the collar takes the nose to 9.0
    w, h = 2.4, 1.9
    wp = [(0.0, 0.90), (0.10, 1.0), (0.70, 1.0), (0.90, 0.76), (1.0, 0.52)]
    hp = [(0.0, 0.92), (0.12, 1.0), (0.65, 1.0), (0.90, 0.80), (1.0, 0.56)]
    st = CR.craft_style(False)
    loft, plates = CR.fuselage(c, L, w, h, wp, hp, False, st=st, n=12)
    # the nose: the mating collar, with its seal and the hatch it opens
    _collar(c, 8.4, 1.32, 0.98, 0.60, 6, 0.17, phase=math.pi / 6)
    g.revolve([(0.80, 0.0), (0.98, 0.0), (0.98, 0.10), (0.80, 0.10), (0.80, 0.0)], m("Lights"), origin=(8.96, 0.0, 0.0), frame=_AX_X, seg=32, wear=0.0, kind="seal")
    g.cylinder((8.35, 0, 0), (8.86, 0, 0), 0.82, 0.80, m("Engine"), seg=24, kind="hatch")
    # the cockpit: a glazed hump on the nose's shoulder, framed
    cx, cz = 5.0, h * 0.84 + 0.30
    g.box((cx, 0.0, cz), (4.0, w * 1.30, 0.95), m("Glass"), chamfer=0.14, kind="canopy")
    for sy in (-1, 1):
        g.box_between((cx - 2.0, sy * w * 0.70, cz - 0.05), (cx + 1.9, sy * w * 0.46, cz + 0.52), 0.12, 0.12, m("Frame"), chamfer=0.01, kind="canopy")
    g.box((cx - 2.05, 0.0, cz), (0.16, w * 1.5, 1.05), m("Frame"), chamfer=0.03, kind="canopy")
    g.box((cx + 2.0, 0.0, cz - 0.05), (0.16, w * 1.0, 0.8), m("Frame"), chamfer=0.03, kind="canopy")
    # the troop doors on the flanks (a frame and a dark leaf), and a livery band over them
    for sy in (-1, 1):
        g.box((0.6, sy * (w + 0.03), -0.05), (3.4, 0.10, 2.0), m("Frame"), chamfer=0.04, kind="door")
        g.box((0.6, sy * (w + 0.10), -0.05), (3.0, 0.06, 1.7), m("Engine"), chamfer=0.03, kind="door")
        g.box((-3.8, sy * (w + 0.02), 0.95), (3.2, 0.06, 0.55), m("Livery"), chamfer=0.0, kind="band")
    # wings: short, a little drooped, with a nacelle on each tip
    for side in (-1, 1):
        wl = CR.wing_loft(w * 0.9, w * 0.9 + 3.7, 5.2, 2.6, -4.6, 1.8, 0.50, 0.26, -0.35, -0.25, side)
        plates += CR.plate_small(c, wl, st)
        tip = wl.R[-1].mean(axis=0)
        ny, nz = float(tip[1] + side * 0.1), float(tip[2])
        g.cylinder((-6.6, ny, nz), (0.6, ny, nz), 0.80, 0.72, m("Plate"), seg=14, chamfer=0.05, wear=0.8, kind="nacelle")
        g.cylinder((0.6, ny, nz), (1.9, ny, nz), 0.72, 0.12, m("Frame"), seg=14, kind="nacelle")
        for xb in (-5.2, -3.2, -1.2):                                                   # bands round the nacelle
            g.revolve([(0.76, -0.12), (0.88, -0.12), (0.88, 0.12), (0.76, 0.12), (0.76, -0.12)], m("Frame"), origin=(xb, ny, nz), frame=_AX_X, seg=20, wear=0.7, kind="nacelle")
        g.cylinder((-0.35, ny, nz), (0.62, ny, nz), 0.50, 0.60, m("Engine"), seg=14, kind="intake")
        g.box((-2.4, ny, nz + 0.8), (1.6, 0.3, 0.3), m("Frame"), chamfer=0.03, kind="pylon")
        CR.engine(c, np.array([-6.8, ny, nz]), 0.62, "astra")
        K2.nav_light(c, np.array([-1.2, ny + side * 0.78, nz]), np.array([0.0, side, 0.0]), K2.NAV_RED if side > 0 else K2.NAV_GREEN, 0.28)
        CR.roundel(c, np.array([-2.6, side * (w * 0.9 + 2.3), -0.35 + 0.30]), np.array([0.0, 0.0, 1.0]), 1.2)
    # the dorsal fin and the ventral keel
    _fin(c, (-6.2, 0.0, h * 0.96), 2.6, 3.4, 1.6, 0.16, 1.3)
    g.box((-0.5, 0.0, -h * 1.0 - 0.1), (9.0, 0.5, 0.35), m("Frame"), chamfer=0.07, kind="keel")
    # the ramp at the stern (a framed door with a light over it), thrusters, the antenna, the strobe
    g.box((-8.45, 0.0, -0.1), (0.12, 3.0, 2.6), m("Frame"), chamfer=0.05, kind="ramp")
    g.box((-8.52, 0.0, -0.1), (0.08, 2.5, 2.2), m("Engine"), chamfer=0.03, kind="ramp")
    g.box((-8.5, 0.0, 1.55), (0.12, 1.4, 0.16), m("Lights"), chamfer=0.0, kind="ramp")
    for sy in (-1, 1):
        K2.thruster_cluster(c, Xf((6.4, sy * w * 0.55, -h * 0.74), G.frame_z((0.0, sy, 0.0), (1.0, 0.0, 0.0)), 1.0), 0.07)
        K2.thruster_cluster(c, Xf((-6.6, sy * (w + 0.1), -h * 0.55), G.frame_z((0.0, sy, 0.0), (1.0, 0.0, 0.0)), 1.0), 0.07)
    g.cylinder((-2.5, 0.0, h * 0.97), (-2.5, 0.0, h * 0.97 + 1.2), 0.03, 0.012, m("Frame"), seg=6, kind="antenna")
    K2.nav_light(c, np.array([-8.3, 0.0, h * 0.5]), np.array([-1.0, 0.0, 0.2]), K2.NAV_WHITE, 0.3)
    K2.nav_light(c, np.array([-6.2, 0.0, h * 0.96 + 2.7]), np.array([0.0, 0.0, 1.0]), K2.NAV_WHITE, 0.3)
    # the Fleet's marks: the callsign, the roundel on the fin, the stencils
    for sy in (-1, 1):
        TX.place_text(g, "ASN", np.array([-3.8, sy * (w + 0.04), 0.25]), np.array([0.0, sy, 0.0]), 0.50, m("Marking"), depth=0.012)
        TX.place_text(g, "KESTREL", np.array([-3.8, sy * (w + 0.04), -0.55]), np.array([0.0, sy, 0.0]), 0.30, m("Marking"), depth=0.012)
        TX.place_text(g, "MARINES", np.array([0.6, sy * (w + 0.16), 1.28]), np.array([0.0, sy, 0.0]), 0.20, m("Marking"), depth=0.012)
        CR.roundel(c, np.array([-6.0, sy * 0.22, h * 0.96 + 1.0]), np.array([0.0, sy, 0.0]), 1.0, up=(0.0, 0.0, 1.0))
    H.scatter_details(c, plates, st)
    return {"length_m": 19.4, "cam_az": -35.0, "cam_el": 18.0, "cam_dist": 2.3, "sun_az": -50.0, "sun_el": 32.0, "closeups": [], "cuts": None,
            "notes": "the nose tip is at x = +9.0 (AstraBoardCraft.cpp: the Kestrel's half length)"}
