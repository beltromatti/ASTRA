"""SPAZIO-VIVO — the civilian hulls of the Aurelia system's traffic (docs/SPAZIO.md): what runs between New Ravenna, the Keeper, the Arsenal, Tiberius and the Gate.

  Tanker   (540 m) Tiberius D2 deuterium tanker: a string of cryogenic spheres (A) or three long capsule tanks (B) on a truss, a hab module and a docking probe at the bow, a
                   drive block and radiators aft. Amber plume.
  Liner    (260 m) Concord Line passenger shuttle: a long hull with three decks of lit windows, an observation dome, twin nacelles (A), or a wide flat delta with a forward bulb (B).
  Tug      (78 m)  Arsenal yard tug: a stout body with a pusher plate and fenders at the bow, a cab all windows, big stern bells, hazard stripes. A with a gantry winch, B with a crane arm.
  Ore      (320 m) Ceres ore barge: a keel with hoppers heaped with ore (A), or a train of skips pushed by a drive unit (B). Amber plume.
  Freighter(352 m) Free Guilds bulk haulers: A is the Guild freighter as the war knows it (with another cargo), B a container hauler with the bridge aft, C a mixed hauler with tanks.

Every hull is built with x forward and its origin at the middle of its length (the berths put the bow where a pier's collar is: a probe at every bow), with the lamps (running lights,
strobes, floods) and the drive bells in the table (space3_common.Rec) for the game's far view and plumes. Paint: the Free Guilds' (MI_HULL_G_*): worn, mismatched, practical.
"""
from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

import ship3_geo as G
import ship3_hull as H
import ship3_kit2 as K2
import ship3_loft as LF
import ship3_misc as MS
import ship3_text as TX
from ship3_kit import Ctx, Xf
from space3_common import (AMBER, AMBERC, BEACON, FLASH2, GREEN, RED, REDPULSE, STEADY, STROBE3, TEAL, UP, WARM, WHITE, Rec, beams, floodlight, frames_x, girder, nav, pipes,
                           rot_x_deg, rot_y_deg, rot_z_deg, sphere_tank, tank_cyl, text_on, truss, windows_at)
from space3_props import add_rock, rock_geometry

I3 = np.eye(3)
GPRE = "MI_HULL_G_"


def vessel_style(scale: float) -> H.HullStyle:
    """The Guilds' plating at a given size: scale 1 for a 350 m hauler, 0.3 for a 78 m tug."""
    st = MS.guild_style()
    s = scale
    sch = replace(st.scheme, row_w=(2.2 * s, 4.0 * s), plate_len=(5.0 * s, 16.0 * s), levels=tuple(x * min(1.0, s * 1.4) for x in (0.25, 0.4, 0.55)), chamfer=0.07 * s, rim=0.16 * s,
                  embed=0.25 * s, min_len=max(1.0, 2.5 * s), min_w=max(0.3, 0.6 * s), gap_a=(0.25 * s, 0.5 * s), gap_w=(0.3 * s, 0.6 * s))
    pn = replace(st.panels, min_size=(1.6 * s, 1.0 * s), max_size=(6.0 * s, 3.5 * s), seam=(0.05 * s, 0.12 * s), margin=0.18 * s, lifts=tuple(x * min(1.0, s * 1.5) for x in (0.035, 0.07, 0.11)),
                 chamfer=0.03 * s, rim=0.07 * s)
    return replace(st, scheme=sch, panels=pn, detail_scale=min(1.0, max(0.3, s)), stencil_height=0.3 * max(0.4, s))


def probe(c: Ctx, x_tip: float, r: float = 4.0, L: float = 6.0, y: float = 0.0, z: float = 0.0) -> None:
    """A docking probe at the bow: a sleeve with a lit seal ring on its end face. The face is at x_tip, where a pier's collar meets it."""
    g, m = c.g, c.m
    fr = G.frame_z((1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    o = (x_tip - L, y, z)
    g.revolve([(r * 0.5, 0.0), (r * 1.3, 0.0), (r * 1.3, L * 0.3), (r, L * 0.5), (r, L - 0.4), (r * 0.82, L), (r * 0.5, L), (r * 0.5, 0.0)], m("Frame"), origin=o, frame=fr, seg=24, wear=0.7, kind="dock")
    g.revolve([(r * 0.7, L + 0.02), (r * 0.56, L + 0.02)], m("Lights"), origin=o, frame=fr, seg=24, wear=0.0, kind="dock", aux=0.1)
    for k in range(3):                                                          # capture latches
        a = 2.0 * math.pi * k / 3.0 + 0.4
        g.box((x_tip - L * 0.55, y + math.cos(a) * r * 1.02, z + math.sin(a) * r * 1.02), (L * 0.5, 0.6, 0.6), m("Engine"), chamfer=0.05, kind="dock")


def running_lights(c: Ctx, rec: Rec, x_bow: float, x_stern: float, hw: float, top: float, bottom: float = 0.0, size: float = 1.6, glow: float = 360.0) -> None:
    """The hull's running lights, fixture and lamp: red to port (+Y), green to starboard (-Y) on the shoulders, white aft, a white double flash on top and a slow red pulse under
    the keel (the ASTRA ships' own, so that a vessel is read the same in the dark)."""
    xs = x_bow - (x_bow - x_stern) * 0.12
    nav(c, rec, np.array([xs, hw, top * 0.4]), np.array([0.3, 1.0, 0.1]), 0.0, size, glow=glow)
    nav(c, rec, np.array([xs, -hw, top * 0.4]), np.array([0.3, -1.0, 0.1]), 0.5, size, glow=glow)
    nav(c, rec, np.array([x_stern + 0.5, 0.0, top * 0.5]), np.array([-1.0, 0.0, 0.1]), 1.0, size, glow=glow * 0.9)
    rec.lamp((x_bow - (x_bow - x_stern) * 0.45, 0.0, top + 1.5 * size), WHITE, 2.4 * size, glow * 2.4, FLASH2, 0.0)
    rec.lamp((x_bow - (x_bow - x_stern) * 0.5, 0.0, bottom - 1.5 * size), RED, 2.0 * size, glow * 1.6, REDPULSE, 0.0)


def hull_loft(c: Ctx, stations, st: H.HullStyle, plates: list, panel_p: float = 0.35, ends: bool = True, skip=None, zone_fn=None) -> LF.Loft:
    """Skin and plate a loft of (x, section, zo) stations, close the ends; the plates are added to `plates`. zone_fn(k, zone) -> a list of plates plates a zone its own way
    (a liner's flanks with their windows), or None for the standard plating."""
    g, rng = c.g, c.rng
    loft = LF.Loft.along_x(stations)
    for k, z in enumerate(loft.zones()):
        z.skin(g, c.m("Frame"))
        own = zone_fn(k, z) if zone_fn else None
        if own is not None:
            plates += own
            continue
        plates += LF.plate_zone(g, z, rng, st.scheme, GPRE, skip=(lambda a0, a1, w0, w1, z=z: skip(z, a0, a1, w0, w1)) if skip else None)
    if ends:
        H.end_face(c, np.array(stations[0][1]), stations[0][0], -1.0, st, zo=stations[0][2], plate=False)
        H.end_face(c, np.array(stations[-1][1]), stations[-1][0], 1.0, st, zo=stations[-1][2], plate=False)
    return loft


def finish(c: Ctx, plates: list, st: H.HullStyle, p_panels: float = 0.35, density: float = 0.25) -> None:
    H.panelize_plates(c, plates, st, p=p_panels)
    H.scatter_details(c, plates, st, density=density)
    H.rivet_plates(c, plates, p=0.2)


def engines(c: Ctx, rec: Rec, x_base: float, ys, zs, R: float) -> None:
    """A bank of drive bells at x_base (their lips are 2.1 R further aft) and their table entries."""
    K2.engine_bank(c, x_base, list(ys), list(zs), R)
    for y in ys:
        for z in zs:
            rec.bell((x_base - 2.1 * R, y, z), R)


def company_marks(c: Ctx, text: str, centre, normal, h: float, serial: bool = True, up=UP) -> None:
    """A company name in white letters of height h on a surface at `centre` (outward normal `normal`) and, if asked, a Guild serial under it."""
    text_on(c, text, centre, normal, h, up=up, depth=0.06 * max(1.0, h / 2.0))
    if serial:
        text_on(c, f"GLD-{int(c.rng.integers(1000, 9999))}", np.asarray(centre, np.float64) + np.asarray(up, np.float64) * (-h * 1.15), normal, h * 0.45, up=up, depth=0.04)


# ======================================================================================================================== the tug
def build_tug(c: Ctx, variant: str = "A") -> dict:
    g, m, rng = c.g, c.m, c.rng
    rec = Rec()
    st = vessel_style(0.85)
    st = replace(st, scheme=replace(st.scheme, mats=(("Trim", 0.5), ("Plate", 0.32), ("Frame", 0.18))))               # the yard's hazard yellow over a worn grey
    plates: list = []
    L = 78.0
    xb, xs = L / 2.0, -L / 2.0
    stations = [(xs + 0.5, LF.chamfer_rect(9.0, 8.5, 0.3, top=0.85), 0.0), (xs + 8.0, LF.chamfer_rect(12.5, 10.0, 0.3, top=0.9), 0.0), (-6.0, LF.chamfer_rect(14.5, 10.5, 0.3, top=0.9), 0.0),
                (16.0, LF.chamfer_rect(14.5, 10.0, 0.3, top=0.9), 0.0), (28.0, LF.chamfer_rect(13.0, 8.5, 0.3, top=0.9), 0.0), (xb - 6.0, LF.chamfer_rect(11.5, 7.0, 0.3, top=0.9), 0.0)]
    hull = hull_loft(c, stations, st, plates)
    # the pusher plate: a heavy face on the bow with rubber fenders, hazard stripes round its rim
    px = xb - 5.0
    g.box((px + 2.0, 0.0, 0.0), (4.0, 36.0, 17.0), m("Frame"), chamfer=0.35, kind="pusher")
    g.box((px + 4.05, 0.0, 0.0), (0.4, 33.0, 14.0), m("Plate"), chamfer=0.12, kind="pusher")
    for sy in (-1, 1):
        for sz in (-1, 1):
            g.cylinder((px + 4.3, sy * 12.0, sz * 4.8), (px + 6.2, sy * 12.0, sz * 4.8), 2.4, 2.1, m("Engine"), seg=14, chamfer=0.2, kind="pusher")       # fenders
    for k in range(9):                                                                                   # hazard stripes on the rim
        g.box((px + 4.3, -16.5 + k * 4.125, 8.0), (0.3, 2.0, 0.9), m("Trim") if k % 2 else m("Frame"), chamfer=0.0, kind="pusher")
        g.box((px + 4.3, -16.5 + k * 4.125, -8.0), (0.3, 2.0, 0.9), m("Trim") if k % 2 else m("Frame"), chamfer=0.0, kind="pusher")
    probe(c, xb, r=2.7, L=4.2, z=0.0)
    # the cab: a raised block, windows all round
    cab = LF.Loft.along_x([(-14.0, LF.chamfer_rect(8.5, 3.2, 0.3, top=0.8), 11.2), (-6.0, LF.chamfer_rect(10.5, 4.5, 0.3, top=0.85), 11.8), (8.0, LF.chamfer_rect(10.0, 4.5, 0.3, top=0.85), 11.8),
                           (13.0, LF.chamfer_rect(7.0, 3.2, 0.3, top=0.8), 11.2)])
    for k in range(8):
        cab.zone(k).skin(g, m("Frame"))
        plates += LF.plate_zone(g, cab.zone(k), rng, replace(st.scheme, row_w=(1.0, 1.8), plate_len=(2.0, 5.0), levels=(0.15, 0.22), min_len=1.2), GPRE)
    for k in (2, 6):
        K2.window_band(c, cab.zone(k), 0.55, -11.0, 10.0, rows=1, lift=0.35, pitch_w=1.4, win=(1.3, 1.2), runs=(6, 10), gap=(0.4, 0.8))
    g.box((14.15, 0.0, 12.7), (0.3, 15.0, 3.0), m("Glass"), chamfer=0.0, kind="window")                    # the great forward window: dark glass, a lit console strip under it
    g.box((14.25, 0.0, 11.3), (0.15, 13.0, 0.5), m("Lights"), chamfer=0.0, kind="window", aux=0.1)
    # thrusters: two main bells and clusters on the flanks
    engines(c, rec, xs + 0.5, (-5.0, 5.0), (0.0,), 2.6)
    for sy in (-1, 1):
        K2.thruster_cluster(c, Xf((-4.0, sy * 14.8, 0.0), I3, 1.0), 0.7)
        K2.thruster_cluster(c, Xf((22.0, sy * 13.6, 0.0), I3, 1.0), 0.7)
    for sz in (-1, 1):
        K2.thruster_cluster(c, Xf((6.0, 0.0, sz * 11.0), I3, 1.0), 0.7)
    # tow hardpoints, the winch and roof gear
    for sx in (-20.0, 20.0):
        K2.tow_lug(c, Xf((sx, 0.0, 10.5), I3, 1.0), 1.0, 0.9)
    K2.tow_lug(c, Xf((-24.0, 0.0, -10.5), Xf().rot_x(180.0), 1.0), 1.0, 0.9)
    g.cylinder((xs + 11.0, -6.0, 10.4), (xs + 11.0, 6.0, 10.4), 2.4, 2.4, m("Engine"), seg=16, kind="winch")                                        # the winch drum
    for sy in (-1, 1):
        g.box((xs + 11.0, sy * 6.8, 10.0), (3.0, 1.0, 2.6), m("Frame"), chamfer=0.08, kind="winch")
    K2.mast(c, Xf((-1.0, 6.0, 16.4), I3, 1.0), 10.0, dish=0.0, arms=2, beacon=False)
    K2.dish_antenna(c, Xf((3.0, -6.0, 18.0), Xf().rot_y(-35.0), 1.0), 2.6)
    if variant == "B":                                                                                  # a crane arm folded along the deck, a grapple at its end
        base = np.array([-27.0, 7.0, 10.6])
        g.cylinder(base, base + np.array([0, 0, 3.0]), 2.2, 2.0, m("Engine"), seg=14, kind="crane")
        girder(c, base + np.array([0.0, 0.0, 3.0]), base + np.array([34.0, 0.0, 6.0]), 2.4, 1.6, mat="Trim", bay=3.2, chord=0.3, web=0.18, kind="crane")
        g.box(base + np.array([36.0, 0.0, 5.6]), (2.6, 3.0, 2.6), m("Engine"), chamfer=0.1, kind="crane")
        for sy in (-1, 1):
            g.box_between(base + np.array([36.0, sy * 1.0, 4.4]), base + np.array([38.5, sy * 1.6, 1.8]), 0.5, 0.5, m("Frame"), kind="crane")
    # hazard livery: yellow bands on the flanks and the pusher's top; names
    for sy in (-1, 1):
        for k in range(7):
            g.box((-24.0 + k * 3.3, sy * 14.62, -4.0), (1.7, 0.1, 5.5), m("Trim") if k % 2 else m("Frame"), frame=G.frame_z((0.0, sy, 0.0), (1.0, 0.0, 0.0)), chamfer=0.0, kind="hazard")
        text_on(c, "ARSENAL YARDS", (-2.0, sy * 14.7, 3.2), (0.0, sy, 0.0), 2.2, depth=0.08)
    running_lights(c, rec, xb, xs, 14.0, 12.0, -10.0, size=1.0, glow=300.0)
    for sx in (-8.0, 8.0):                                                                              # floods on the cab roof
        floodlight(c, rec, np.array([sx, 0.0, 16.0]), 2.4, (1.0 if sx > 0 else -1.0, 0.0, 0.0), n=2, glow=520.0, size=1.6, scale=0.4)
    finish(c, plates, st, 0.4, 0.4)
    return {"rec": rec, "length_m": L, "cam": [-40.0, 22.0, 55.0], "margin": 0.08, "lens_flat": 70.0,
            "closeups": [{"name": "bow", "target": [30.0, 0.0, 4.0], "normal": [0.9, -0.5, 0.35], "distance": 70.0, "span": 40.0}]}


# ====================================================================================================================== the tanker
def build_tanker(c: Ctx, variant: str = "A") -> dict:
    g, m, rng = c.g, c.m, c.rng
    rec = Rec()
    st = vessel_style(1.0)
    plates: list = []
    L = 540.0
    xb, xs = L / 2.0, -L / 2.0
    # ---------------------------------------------------------------------------------------------------------- the drive block
    dx0, dx1 = xs + 20.0, xs + 78.0
    rows = ((0.0, 15, 15), (0.12, 19, 19), (0.75, 19, 19), (1.0, 12, 12))
    stations = [(dx0 + t * (dx1 - dx0), LF.chamfer_rect(w_, h_, 0.3), 0.0) for t, w_, h_ in rows]
    drive = hull_loft(c, stations, st, plates, ends=False)
    H.end_face(c, np.array(stations[-1][1]), dx1, 1.0, st, plate=False)
    g.box((xs + 12.0, 0.0, 0.0), (22.0, 36.0, 36.0), m("Frame"), chamfer=0.3, kind="engine")
    engines(c, rec, xs + 22.0, (-8.0, 8.0), (-8.0, 8.0), 6.4)
    for sy in (-1, 1):
        K2.radiator_wing(c, Xf((xs + (36.0 if sy > 0 else 92.0), sy * 19.0, 0.0), Xf().rot_z(0.0 if sy > 0 else 180.0), 1.0), 56.0, 30.0, 14.0, leaves=2)
    for sz in (-1, 1):
        g.box((xs + 55.0, 0.0, sz * 26.0), (40.0, 1.0, 14.0), m("Radiator"), chamfer=0.04, kind="radiator")
    # ----------------------------------------------------------------------------------------------------------------- the spine
    sx0, sx1 = dx1 - 2.0, xb - 92.0
    truss(c, (sx0, 0.0, 0.0), (sx1, 0.0, 0.0), 8.5, bay=18.0, chord=1.2, web=0.6, kind="truss")
    for sy in (-1, 1):
        g.box(((sx0 + sx1) / 2, sy * 10.5, -4.0), (sx1 - sx0, 0.7, 2.0), m("Engine"), chamfer=0.05, kind="truss")                                       # service trays
    # ---------------------------------------------------------------------------------------------------------------- the cargo
    if variant == "A":
        R = 38.0
        xc = [sx0 + 56.0 + k * 90.0 for k in range(4)]
        for k, x in enumerate(xc):
            sphere_tank(c, (x, 0.0, 0.0), R, "Trim", seg=40, rings=16, bands=3, band_mat="Frame", kind="tank", wear=0.08)
            tone_pad = rng.normal(0.0, 0.05)
            for sx_ in (-1, 1):                                                                              # the cradle rings either side of the sphere
                xr = x + sx_ * (R * 0.52)
                rr = R * 0.86
                for j in range(12):
                    a0, a1 = 2 * math.pi * j / 12, 2 * math.pi * (j + 1) / 12
                    p0 = np.array([xr, rr * math.cos(a0), rr * math.sin(a0)])
                    p1 = np.array([xr, rr * math.cos(a1), rr * math.sin(a1)])
                    beams(c, p0[None], p1[None], 1.4, 2.2, mat="Frame", kind="cradle")
            company_marks(c, "D2", (x, R * 1.0, R * 0.12), (0.0, 1.0, 0.0), 12.0, serial=False)
            company_marks(c, "D2", (x, -R * 1.0, R * 0.12), (0.0, -1.0, 0.0), 12.0, serial=False)
            rec.lamp((x, 0.0, R + 4.0), WARM, 2.4, 260.0, STEADY)
        for k in range(len(xc) - 1):                                                                         # the pipework between the spheres
            xm = 0.5 * (xc[k] + xc[k + 1])
            for sy in (-1, 1):
                pipes(c, np.array([[xc[k] + R * 0.8, sy * 13.0, -9.0]]), np.array([[xc[k + 1] - R * 0.8, sy * 13.0, -9.0]]), 1.5, mat="Engine", seg=10, kind="pipe")
                g.box((xm, sy * 13.0, -9.0), (4.0, 4.0, 4.0), m("Frame"), chamfer=0.2, kind="pipe")
    else:
        Rt = 27.0
        for (ty, tz) in ((-26.0, -15.0), (26.0, -15.0), (0.0, 30.0)):
            tank_cyl(c, np.array([sx0 + 30.0, ty, tz]), np.array([xb - 112.0, ty, tz]), Rt, "Plate", seg=36, bands=8, band_mat="Livery", kind="tank", wear=0.1)
        for x in np.linspace(sx0 + 55.0, xb - 135.0, 6):
            for j in range(18):
                a0, a1 = 2 * math.pi * j / 18, 2 * math.pi * (j + 1) / 18
                for (ty, tz) in ((-26.0, -15.0), (26.0, -15.0), (0.0, 30.0)):
                    p0 = np.array([x, ty + (Rt + 1.0) * math.cos(a0), tz + (Rt + 1.0) * math.sin(a0)])
                    p1 = np.array([x, ty + (Rt + 1.0) * math.cos(a1), tz + (Rt + 1.0) * math.sin(a1)])
                    beams(c, p0[None], p1[None], 0.9, 1.4, mat="Frame", kind="cradle")
        company_marks(c, "TIBERIUS D2", (30.0, 26.0 + Rt, -15.0), (0.0, 1.0, 0.0), 6.0, serial=False)
        company_marks(c, "TIBERIUS D2", (30.0, -26.0 - Rt, -15.0), (0.0, -1.0, 0.0), 6.0, serial=False)
        company_marks(c, "TIBERIUS D2", (30.0, 0.0, 30.0 + Rt), (0.0, 0.0, 1.0), 6.0, serial=False, up=(1.0, 0.0, 0.0))
        for x in (xb - 128.0,):
            sphere_tank(c, (x, 0.0, 0.0), 22.0, "Plate", seg=28, rings=12, bands=3, kind="tank")
    # ---------------------------------------------------------------------------------------------------------------- the bow module
    bx0, bx1 = xb - 96.0, xb - 12.0
    rows = ((0.0, 15, 15), (0.1, 22, 22), (0.5, 22, 21), (0.85, 17, 15), (1.0, 11, 10))
    stations = [(bx0 + t * (bx1 - bx0), LF.chamfer_rect(w_, h_, 0.32), 0.0) for t, w_, h_ in rows]
    bow = hull_loft(c, stations, st, plates, ends=False)
    H.end_face(c, np.array(stations[0][1]), bx0, -1.0, st, plate=False)
    H.end_face(c, np.array(stations[-1][1]), bx1, 1.0, st, plate=False)
    for k in (2, 6):
        for w in (0.30, 0.52, 0.72):
            K2.window_band(c, bow.zone(k), w, bx0 + 14.0, bx1 - 16.0, rows=1, lift=0.4, runs=(3, 9))
    g.box((bx1 + 0.4, 0.0, 3.0), (0.5, 14.0, 3.0), m("Lights"), chamfer=0.0, kind="window", aux=0.05)                                                       # the visor
    g.cylinder((bx1, 0.0, 0.0), (xb - 6.0, 0.0, 0.0), 9.0, 7.0, m("Frame"), seg=20, chamfer=0.3, kind="neck")
    probe(c, xb, r=5.2, L=7.0)
    K2.mast(c, Xf((xb - 70.0, 0.0, 21.5), I3, 1.0), 20.0, dish=7.0, arms=3, beacon=True)
    K2.antenna_farm(c, Xf((xb - 40.0, 0.0, 21.0), I3, 1.0), 10.0, 14.0, n=6)
    for sy in (-1, 1):
        text_on(c, "TIBERIUS D2", (bx0 + 36.0, sy * 21.6, 5.0), (0.0, sy, 0.0), 3.4, depth=0.1)
    running_lights(c, rec, xb, xs, 22.0, 24.0, -20.0, size=2.2, glow=420.0)
    rec.lamps_along((bx0 + 14.0, 22.5, 0.0), (bx1 - 16.0, 22.5, 0.0), 5, WARM, 2.2, 240.0, STEADY)
    rec.lamps_along((bx0 + 14.0, -22.5, 0.0), (bx1 - 16.0, -22.5, 0.0), 5, WARM, 2.2, 240.0, STEADY)
    finish(c, plates, st, 0.35, 0.2)
    return {"rec": rec, "length_m": L, "cam": [-35.0, 18.0, 55.0], "margin": 0.07, "lens_flat": 70.0, "cams": [[-100.0, 20.0, 55.0], [60.0, 30.0, 55.0]]}


# ======================================================================================================================== the liners
def shifted(sec, dy: float = 0.0, dz: float = 0.0) -> list:
    return [(y + dy, z + dz) for y, z in sec]


def liner_flank(c: Ctx, st: H.HullStyle, z, a0: float, a1: float, stripe: str, decks=(0.50, 0.63, 0.76), lit: bool = True) -> list:
    """A liner's flank: plates, a broad stripe in the line's colour, three decks of long runs of lit windows, plates above."""
    g, rng, s = c.g, c.rng, st.scheme
    base = replace(s, mats=(("Marking", 0.92), ("Plate", 0.05), ("Frame", 0.03)), row_w=(2.4, 4.4), plate_len=(8.0, 28.0))
    band = replace(s, mats=((stripe, 1.0),), row_w=(3.0, 3.6), plate_len=(24.0, 70.0), levels=(0.4,), level_weights=(1.0,), wedge=0.0, tone_sigma=0.05)
    gold = replace(s, mats=(("Trim", 1.0),), row_w=(0.35, 0.45), plate_len=(30.0, 90.0), levels=(0.45,), level_weights=(1.0,), wedge=0.0, gap_w=(0.02, 0.03), tone_sigma=0.03)
    out: list = []
    out += LF.plate_zone(g, z, rng, base, GPRE, w_lo=0.0, w_hi=0.12)
    out += LF.plate_zone(g, z, rng, band, GPRE, w_lo=0.12, w_hi=0.29)
    out += LF.plate_zone(g, z, rng, gold, GPRE, w_lo=0.295, w_hi=0.325)
    out += LF.plate_zone(g, z, rng, base, GPRE, w_lo=0.33, w_hi=0.86)
    out += LF.plate_zone(g, z, rng, base, GPRE, w_lo=0.88, w_hi=1.0)
    if lit:
        for w in decks:
            K2.window_band(c, z, w, a0 + 6.0, a1 - 6.0, rows=1, lift=0.7, pitch_w=2.5, win=(1.5, 0.95), runs=(10, 36), gap=(0.8, 2.6))
    return out


def build_liner(c: Ctx, variant: str = "A") -> dict:
    g, m, rng = c.g, c.m, c.rng
    rec = Rec()
    st = vessel_style(0.9)
    st = replace(st, scheme=replace(st.scheme, mats=(("Marking", 0.9), ("Plate", 0.06), ("Frame", 0.04))))                    # a liner is white
    plates: list = []
    L = 260.0
    xb, xs = L / 2.0, -L / 2.0
    stripe = "Blue" if variant == "A" else "Livery"
    if variant == "A":
        rows = ((xs + 8.0, 7.0, 7.0), (xs + 20.0, 15.0, 13.0), (xs + 46.0, 20.0, 15.5), (xs + 100.0, 22.0, 17.0), (xs + 170.0, 22.0, 17.0), (xs + 215.0, 19.0, 15.0), (xs + 238.0, 13.0, 10.0),
                (xb - 8.0, 6.5, 6.0))
    else:
        rows = ((xs + 8.0, 28.0, 5.5), (xs + 26.0, 36.0, 8.0), (xs + 70.0, 33.0, 10.0), (xs + 130.0, 22.0, 11.0), (xs + 188.0, 13.0, 9.0), (xs + 232.0, 8.0, 7.0), (xb - 8.0, 5.5, 5.0))
    stations = [(x, LF.chamfer_rect(w_, h_, 0.4 if variant == "A" else 0.45, top=0.82, bottom=0.7), 0.0) for x, w_, h_ in rows]
    a0, a1 = stations[0][0], stations[-1][0]
    decks = (0.50, 0.63, 0.76) if variant == "A" else (0.46, 0.66)
    hull = hull_loft(c, stations, st, plates, zone_fn=lambda k, z: liner_flank(c, st, z, a0 + 14.0, a1 - 10.0, stripe, decks) if k in (2, 6) else None)
    hh = rows[3][2]
    hw = rows[3][1]
    probe(c, xb, r=4.2, L=8.0)
    xp = xb - 5.0
    # the lounge: a glass dome on a lit ring, forward of amidships (A), a raised blister with its own windows (B)
    if variant == "A":
        g.cylinder((xs + 190.0, 0, hh * 0.9), (xs + 190.0, 0, hh * 0.9 + 1.4), 15.0, 14.6, m("Frame"), seg=28, chamfer=0.1, kind="lounge")
        g.dome((xs + 190.0, 0, hh * 0.9 + 1.2), 13.5, m("Glass"), seg=28, rings=6, squash=0.62, kind="lounge")
        g.revolve([(14.7, 0.4), (14.7, 1.1)], m("Lights"), origin=(xs + 190.0, 0, hh * 0.9), frame=G.frame_z((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)), seg=28, kind="lounge", aux=0.1, wear=0.0)
        # twin nacelles on pylons, each with its bell
        for sy in (-1, 1):
            ns = [(xs + 2.0 + t * 76.0, LF.chamfer_rect(w_, h_, 0.3), 0.0) for t, w_, h_ in ((0.0, 4.0, 4.0), (0.1, 5.6, 5.6), (0.7, 5.6, 5.6), (1.0, 3.6, 3.6))]
            ns = [(x, shifted(sec, sy * 33.0, -5.0), 0.0) for x, sec, _ in ns]
            nac = hull_loft(c, ns, st, plates, ends=False)
            H.end_face(c, np.array(ns[-1][1]), ns[-1][0], 1.0, st, plate=False)
            g.box_between((xs + 40.0, sy * 12.0, -4.0), (xs + 40.0, sy * 33.0, -5.0), 3.0, 1.6, m("Frame"), chamfer=0.1, kind="pylon")
            g.box_between((xs + 62.0, sy * 14.0, -4.0), (xs + 62.0, sy * 33.0, -5.0), 2.4, 1.4, m("Frame"), chamfer=0.1, kind="pylon")
            K2.engine_nozzle(c, Xf((xs + 5.0, sy * 33.0, -5.0), G.frame_z((-1.0, 0.0, 0.0), (0.0, 0.0, 1.0)), 1.0), 3.0, "astra")
            rec.bell((xs + 5.0 - 2.1 * 3.0, sy * 33.0, -5.0), 3.0)
            g.box((xs + 38.0, sy * 33.0, -5.0 + 5.7), (30.0, 0.5, 0.5), m(stripe), chamfer=0.0, kind="nacelle")
        engines(c, rec, xs + 8.0, (0.0,), (0.0,), 3.8)
    else:
        g.box((xs + 150.0, 0, hh + 3.0), (2.0, 20.0, 5.0), m("Frame"), chamfer=0.2, kind="lounge")
        lounge = [(xs + 128.0, LF.chamfer_rect(8.0, 3.0, 0.4, top=0.7), hh + 3.5), (xs + 150.0, LF.chamfer_rect(13.0, 4.5, 0.4, top=0.7), hh + 4.5), (xs + 190.0, LF.chamfer_rect(11.0, 4.0, 0.4, top=0.7), hh + 4.0),
                  (xs + 206.0, LF.chamfer_rect(5.0, 2.5, 0.4, top=0.7), hh + 3.0)]
        lg = hull_loft(c, lounge, st, plates, zone_fn=lambda k, z: LF.plate_zone(g, z, rng, replace(st.scheme, row_w=(1.2, 2.4), plate_len=(3, 9), levels=(0.2, 0.3), min_len=1.4), GPRE)
                       if k not in (2, 6) else [])
        for k in (2, 6):
            K2.window_band(c, LF.Loft.along_x(lounge).zone(k), 0.4, xs + 132.0, xs + 204.0, rows=2, lift=0.2, pitch_w=1.6, win=(1.5, 1.1), runs=(8, 24), gap=(0.6, 1.6))
        g.dome((xs + 238.0, 0, 7.0), 5.0, m("Glass"), seg=18, rings=4, squash=0.7, kind="lounge")
        engines(c, rec, xs + 8.0, (-8.0, 8.0, -24.0, 24.0), (0.0,), 3.4)
        for sy in (-1, 1):
            g.box((xs + 36.0, sy * 20.0, hh * 0.92 + 0.5), (44.0, 20.0, 0.6), m("Radiator"), chamfer=0.04, kind="radiator")
            g.box((xs + 36.0, sy * 20.0, hh * 0.92 + 0.15), (44.6, 20.6, 0.4), m("Engine"), chamfer=0.05, kind="radiator")
    # the line's name along the flanks, the hull number
    for sy in (-1, 1):
        text_on(c, "CONCORD LINE", (xs + 128.0, sy * (hw * 0.93), hh * 0.04), (0.0, sy, 0.0), 3.4 if variant == "A" else 2.4, depth=0.1)
        text_on(c, f"CL-{int(rng.integers(100, 999))}", (xs + 74.0, sy * (hw * 0.95), -hh * 0.46), (0.0, sy, 0.0), 1.3, depth=0.06)
    K2.mast(c, Xf((xs + 90.0, 0.0, hh * 0.95), I3, 1.0), 12.0, dish=4.0, arms=2, beacon=True)
    running_lights(c, rec, xb, xs, hw, hh, -hh, size=1.5, glow=380.0)
    rec.lamps_along((xs + 40.0, hw + 0.3, hh * 0.1), (xb - 40.0, hw + 0.3, hh * 0.1), 10, WARM, 2.0, 220.0, STEADY)
    rec.lamps_along((xs + 40.0, -hw - 0.3, hh * 0.1), (xb - 40.0, -hw - 0.3, hh * 0.1), 10, WARM, 2.0, 220.0, STEADY)
    finish(c, plates, st, 0.3, 0.15)
    return {"rec": rec, "length_m": L, "cam": [-35.0, 20.0, 55.0], "margin": 0.07, "lens_flat": 70.0, "cams": [[-110.0, 18.0, 55.0], [60.0, 35.0, 55.0]]}


# ======================================================================================================================== haulers
def crew_block(c: Ctx, rec: Rec, x0: float, x1: float, hw: float, hh: float, st: H.HullStyle, plates: list, name: str, zo: float = 0.0, windows: bool = True) -> LF.Loft:
    """A hauler's crew section: a blunt, windowed block with a lit visor on its forward face (the Guild freighter's, in any size)."""
    g, m, rng = c.g, c.m, c.rng
    rows = ((0.0, 0.7, 0.66), (0.12, 1.0, 0.95), (0.55, 1.0, 1.0), (0.84, 0.86, 0.86), (1.0, 0.5, 0.48))
    stations = [(x0 + t * (x1 - x0), LF.chamfer_rect(hw * wf, hh * hf, 0.3, top=0.85, bottom=0.8), zo + (0.8 * t if t > 0.5 else 0.0)) for t, wf, hf in rows]
    loft = hull_loft(c, stations, st, plates, ends=False)
    H.end_face(c, np.array(stations[0][1]), x0, -1.0, st, zo=stations[0][2], plate=False)
    H.end_face(c, np.array(stations[-1][1]), x1, 1.0, st, zo=stations[-1][2], plate=False)
    if windows:
        for k in (2, 6):
            for w in (0.32, 0.56):
                K2.window_band(c, loft.zone(k), w, x0 + 8.0, x1 - 10.0, rows=1, lift=0.4, pitch_w=2.6, runs=(3, 9))
    g.box((x1 + 0.3, 0.0, zo + hh * 0.26), (0.5, hw * 1.15, hh * 0.22), m("Lights"), chamfer=0.0, kind="window", aux=0.12)
    for sy in (-1, 1):
        text_on(c, name, (x0 + (x1 - x0) * 0.42, sy * (hw * 1.0 + 0.5), zo + hh * 0.05), (0.0, sy, 0.0), min(2.2, hh * 0.2), depth=0.06)
    return loft


def drive_block(c: Ctx, rec: Rec, x_st: float, x_end: float, hw: float, hh: float, R: float, ys, zs, st: H.HullStyle, plates: list, wings: bool = True) -> None:
    """A hauler's drive section: a tapering block, fuel tanks on its flanks, radiator wings, a stern plate with its bells."""
    g, m = c.g, c.m
    rows = ((0.0, 1.0, 0.92), (0.15, 1.06, 0.98), (0.7, 1.0, 0.92), (1.0, 0.62, 0.58))
    d0 = x_st + 8.0
    stations = [(d0 + t * (x_end - d0), LF.chamfer_rect(hw * wf, hh * hf, 0.3), 0.0) for t, wf, hf in rows]
    hull_loft(c, stations, st, plates, ends=False)
    H.end_face(c, np.array(stations[-1][1]), x_end, 1.0, st, plate=False)
    for sy in (-1, 1):
        for sz in (-1, 1):
            g.cylinder((d0 + 12.0, sy * hw * 0.5, sz * hh * 1.1), (x_end - 12.0, sy * hw * 0.5, sz * hh * 1.1), 3.2 * hw / 16.0, 3.2 * hw / 16.0, m("Engine"), seg=16, chamfer=0.1, kind="tank")
    if wings:
        K2.radiator_wing(c, Xf((d0 + 10.0, hw * 1.06, 0.0), I3, 1.0), 42.0, 20.0, 12.0, leaves=2)
        K2.radiator_wing(c, Xf((x_end - 8.0, -hw * 1.06, 0.0), Xf().rot_z(180.0), 1.0), 42.0, 20.0, 12.0, leaves=2)
    g.box(((x_st + 2.0 + d0 + 1.0) / 2, 0, 0), (d0 + 1.0 - x_st - 2.0, hw * 1.9, hh * 2.0), m("Frame"), chamfer=0.2, kind="engine")
    engines(c, rec, x_st + 2.0, ys, zs, R)


def traffic_pod(c: Ctx, x: float, y: float, z: float, mat: str, rng, outer: bool) -> None:
    """A cargo pod (20 x 9 x 9) as ship3_misc builds it, for the traffic: a corrugated shell, castings and a door end, and a company name on a third of the outer ones
    (the lettering is the costly part of a pod: a hauler carries dozens, nobody reads them from afar)."""
    g, m = c.g, c.m
    g.box((x, y, z), (20.0, 9.0, 9.0), m(mat), chamfer=0.10, kind="pod", tone=float(np.clip(0.5 + rng.normal(0, 0.13), 0.1, 0.9)))
    n = 22
    xs = x - 9.4 + (np.arange(n) + 0.5) * 18.8 / n
    for sy in (-1, 1):
        g.boxes(np.stack([xs, np.full(n, y + sy * 4.55), np.full(n, z)], axis=1), (0.12, 0.10, 4.0), m(mat), chamfer=0.0, kind="pod", tone=0.5)
    for sz in (-1, 1):
        g.boxes(np.stack([xs, np.full(n, y), np.full(n, z + sz * 4.55)], axis=1), (0.12, 4.0, 0.10), m(mat), chamfer=0.0, kind="pod", tone=0.5)
    for sx in (-1, 1):
        g.box((x + sx * 9.85, y, z), (0.32, 9.2, 9.2), m("Frame"), chamfer=0.05, kind="pod")
        for sy in (-1, 1):
            for sz in (-1, 1):
                g.box((x + sx * 9.9, y + sy * 4.4, z + sz * 4.4), (0.5, 0.6, 0.6), m("Engine"), chamfer=0.04, kind="pod")
    for k in range(4):
        g.cylinder((x + 9.99, y - 3.0 + k * 2.0, z - 3.6), (x + 10.12, y - 3.0 + k * 2.0, z + 3.6), 0.07, 0.07, m("Engine"), seg=6, kind="pod")
    if outer and rng.random() < 0.34:
        sy = 1 if y > 0 else -1
        TX.place_text(g, str(rng.choice(MS.COMPANIES)), np.array([x - 2.0, y + sy * 4.7, z + 1.4]), np.array([0.0, sy, 0.0]), 0.95, m("Marking"), depth=0.02, res=0, flat=True)


def cargo_bay(c: Ctx, x: float, kind: str, t: float, rng, outer: bool = True) -> None:
    """One bay of cargo on a square truss of half width t, centred at x: pods (2 x 2 inside, 2 x 2 out), tanks, an empty cradle, or ore skips."""
    g, m = c.g, c.m
    off = t + 4.5 + 0.5
    cargo_mats = [n for n, _ in MS.POD_COLOURS]
    cw = np.array([w for _, w in MS.POD_COLOURS])
    cw = cw / cw.sum()
    if kind == "tanks":
        for (ty, tz) in ((11.6, 0.0), (-11.6, 0.0), (0.0, 11.6), (0.0, -11.6)):
            MS._tank(c, x, ty, tz, "Plate" if rng.random() < 0.6 else "Engine", rng)
        return
    slots = [(sy * off, sz * off, 0.85, False) for sy in (-1, 1) for sz in (-1, 1)]
    if outer:
        slots += [(sy * (off + 9.4), sz * off, 0.55, True) for sy in (-1, 1) for sz in (-1, 1)]
    for (y, z, p, out) in slots:
        if kind == "cradle" and rng.random() < 0.75:
            g.box((x, y, z - math.copysign(4.6, z)), (20.0, 0.5, 0.5), m("Frame"), chamfer=0.03, kind="truss")
            continue
        if rng.random() > p:
            continue
        traffic_pod(c, x, y, z, str(rng.choice(cargo_mats, p=cw)), rng, out)
        if not out:
            for sx in (-1, 1):
                g.box((x + sx * 6.5, math.copysign(t + 0.25, y), math.copysign(t + 0.25, z)), (2.4, 1.4, 1.4), m("Frame"), chamfer=0.04, kind="truss")


def build_freighter_a(c: Ctx) -> dict:
    """The Free Guilds' bulk hauler as the war knows it (ship3_misc.build_freighter), with another cargo: the same design a traffic player sees flying about."""
    rec = Rec()
    MS.build_freighter(c)
    c.g.cuts = None                                                           # not a ship to be broken into sections here
    engines_at = [(-168.0, y, z) for y in (-6.5, 6.5) for z in (-6.5, 6.5)]
    for (x, y, z) in engines_at:
        rec.bell((x - 2.1 * 5.4, y, z), 5.4)
    running_lights(c, rec, 172.8, -178.0, 14.0, 22.0, -22.0, size=1.8, glow=380.0)
    rec.lamps_along((60.0, 14.2, 0.0), (160.0, 14.2, 0.0), 6, WARM, 2.2, 240.0, STEADY)
    rec.lamps_along((60.0, -14.2, 0.0), (160.0, -14.2, 0.0), 6, WARM, 2.2, 240.0, STEADY)
    return {"rec": rec, "length_m": 352.0, "cam": [-30.0, 22.0, 55.0], "margin": 0.07, "lens_flat": 70.0, "cams": [[-110.0, 20.0, 55.0], [60.0, 35.0, 55.0]]}


def build_freighter_b(c: Ctx) -> dict:
    """A container hauler: the bridge aft on a tower above the drive, a long truss of pods, the bow left open with a probe on a boom."""
    g, m, rng = c.g, c.m, c.rng
    rec = Rec()
    st = vessel_style(1.0)
    plates: list = []
    xb, xs = 176.0, -176.0
    t = 3.6
    drive_block(c, rec, xs, -112.0, 17.0, 15.0, 5.2, (-6.5, 6.5), (-6.5, 6.5), st, plates)
    # the bridge tower aft
    tw = [(x, LF.chamfer_rect(w_, h_, 0.3, top=0.8), 15.0 + h_) for x, w_, h_ in ((-166.0, 10.0, 6.0), (-158.0, 12.5, 12.0), (-134.0, 12.5, 14.0), (-124.0, 9.0, 8.0))]
    tower = hull_loft(c, tw, st, plates, ends=False)
    H.end_face(c, np.array(tw[0][1]), -166.0, -1.0, st, zo=tw[0][2], plate=False)
    H.end_face(c, np.array(tw[-1][1]), -124.0, 1.0, st, zo=tw[-1][2], plate=False)
    for k in (2, 6):
        for w in (0.30, 0.52, 0.72):
            K2.window_band(c, tower.zone(k), w, -154.0, -130.0, rows=1, lift=0.4, pitch_w=2.4, runs=(3, 8))
    g.box((-123.7, 0.0, 15.0 + 9.0), (0.5, 17.0, 3.4), m("Lights"), chamfer=0.0, kind="window", aux=0.1)
    K2.mast(c, Xf((-146.0, 0.0, 15.0 + 28.0), I3, 1.0), 16.0, dish=6.0, arms=3, beacon=True)
    K2.mast(c, Xf((-134.0, 7.0, 15.0 + 28.0), I3, 1.0), 8.0, arms=2, beacon=False)
    text_on(c, "NEMET DEEP", (-146.0, 12.7, 15.0 + 14.0), (0.0, 1.0, 0.0), 2.6, depth=0.08)
    text_on(c, "NEMET DEEP", (-146.0, -12.7, 15.0 + 14.0), (0.0, -1.0, 0.0), 2.6, depth=0.08)
    # truss and containers
    sx0, sx1 = -112.0, 166.0
    truss(c, (sx0, 0.0, 0.0), (sx1, 0.0, 0.0), t, bay=9.0, chord=1.2, web=0.65, kind="truss")
    for sy in (-1, 1):
        g.box(((sx0 + sx1) / 2, sy * (t + 1.3), 0.0), (sx1 - sx0, 0.6, 1.8), m("Engine"), chamfer=0.05, kind="truss")
    pitch = 23.0
    bays = int((150.0 - sx0 - 6.0) / pitch)
    x_first = sx0 + 8.0 + pitch / 2
    kinds = ["pods"] * bays
    for k in rng.choice(bays, 2, replace=False):
        kinds[int(k)] = "cradle"
    for k in range(bays):
        cargo_bay(c, x_first + k * pitch, kinds[k], t, rng, outer=True)
    # the open bow: a cradle ring on the truss and the probe on a boom
    for k, xr in enumerate((148.0, 160.0)):
        ring = [(xr, y, z) for y, z in ((4.8, 4.8), (-4.8, 4.8), (-4.8, -4.8), (4.8, -4.8))]
        beams(c, np.array(ring), np.array(ring[1:] + ring[:1]), 0.8, mat="Frame", kind="truss")
    probe(c, xb, r=4.0, L=7.0)
    running_lights(c, rec, xb, xs, 17.0, 30.0, -17.0, size=1.8, glow=380.0)
    rec.lamps_along((sx0 + 20.0, 0.0, 16.0), (sx1 - 30.0, 0.0, 16.0), 8, WARM, 2.0, 200.0, STEADY)
    finish(c, plates, st, 0.4, 0.25)
    return {"rec": rec, "length_m": 352.0, "cam": [-30.0, 22.0, 55.0], "margin": 0.07, "lens_flat": 70.0, "cams": [[-110.0, 20.0, 55.0], [60.0, 35.0, 55.0]]}


def build_freighter_c(c: Ctx) -> dict:
    """A mixed hauler: the crew block forward, tank and pod bays on a truss, a twin-boom drive aft (a pair of outrigger drive pods on lattice booms)."""
    g, m, rng = c.g, c.m, c.rng
    rec = Rec()
    st = vessel_style(1.0)
    plates: list = []
    xb, xs = 176.0, -176.0
    t = 3.6
    crew_block(c, rec, 98.0, 168.0, 14.0, 12.0, st, plates, "HALCYON")
    probe(c, xb, r=3.8, L=7.0)
    K2.mast(c, Xf((120.0, 0.0, 12.5), I3, 1.0), 14.0, dish=5.0, arms=3, beacon=True)
    # the central block and the drive pods on booms
    dx0, dx1 = xs + 10.0, xs + 62.0
    stations = [(dx0 + tt * (dx1 - dx0), LF.chamfer_rect(w_, h_, 0.3), 0.0) for tt, w_, h_ in ((0.0, 12, 11), (0.2, 15, 14), (0.8, 15, 14), (1.0, 9, 8))]
    hull_loft(c, stations, st, plates, ends=False)
    H.end_face(c, np.array(stations[0][1]), dx0, -1.0, st, plate=False)
    H.end_face(c, np.array(stations[-1][1]), dx1, 1.0, st, plate=False)
    for sy in (-1, 1):
        truss(c, (xs + 30.0, sy * 12.0, 0.0), (xs + 30.0, sy * 40.0, 0.0), 3.0, bay=7.0, chord=0.8, web=0.4, kind="truss")
        truss(c, (xs + 54.0, sy * 12.0, 0.0), (xs + 54.0, sy * 40.0, 0.0), 3.0, bay=7.0, chord=0.8, web=0.4, kind="truss")
        pod = [(xs + 14.0 + tt * 56.0, shifted(LF.chamfer_rect(w_, h_, 0.3), sy * 42.0, 0.0), 0.0) for tt, w_, h_ in ((0.0, 7.0, 7.0), (0.15, 9.0, 9.0), (0.75, 9.0, 9.0), (1.0, 6.0, 6.0))]
        hull_loft(c, [(x, s, z) for x, s, z in pod], st, plates, ends=False)
        H.end_face(c, np.array(pod[-1][1]), pod[-1][0], 1.0, st, plate=False)
        H.end_face(c, np.array(pod[0][1]), pod[0][0], -1.0, st, plate=False)
        engines(c, rec, xs + 12.0, (sy * 42.0,), (-3.5, 3.5), 3.2)
    engines(c, rec, xs + 12.0, (0.0,), (0.0,), 4.6)
    for sz in (-1, 1):
        g.box((xs + 36.0, 0.0, sz * 22.0), (36.0, 20.0, 0.6), m("Radiator"), chamfer=0.04, kind="radiator")
    # cargo
    sx0, sx1 = dx1 - 2.0, 98.0
    truss(c, (sx0, 0.0, 0.0), (sx1, 0.0, 0.0), t, bay=9.0, chord=1.2, web=0.65, kind="truss")
    for sy in (-1, 1):
        g.box(((sx0 + sx1) / 2, sy * (t + 1.3), 0.0), (sx1 - sx0, 0.6, 1.8), m("Engine"), chamfer=0.05, kind="truss")
    pitch = 23.0
    bays = int((sx1 - sx0 - 4.0) / pitch)
    x_first = sx0 + (sx1 - sx0 - bays * pitch) / 2 + pitch / 2
    pattern = ["tanks", "pods", "tanks", "pods", "tanks", "cradle", "pods", "tanks"]
    kinds = [pattern[k % len(pattern)] for k in range(bays)]
    for k in range(bays):
        cargo_bay(c, x_first + k * pitch, kinds[k], t, rng, outer=kinds[k] != "tanks")
    running_lights(c, rec, xb, xs, 14.0, 24.0, -24.0, size=1.8, glow=380.0)
    rec.lamps_along((100.0, 14.2, 0.0), (160.0, 14.2, 0.0), 4, WARM, 2.2, 240.0, STEADY)
    rec.lamps_along((100.0, -14.2, 0.0), (160.0, -14.2, 0.0), 4, WARM, 2.2, 240.0, STEADY)
    finish(c, plates, st, 0.4, 0.25)
    return {"rec": rec, "length_m": 352.0, "cam": [-30.0, 22.0, 55.0], "margin": 0.07, "lens_flat": 70.0, "cams": [[-110.0, 20.0, 55.0], [60.0, 35.0, 55.0]]}


# ====================================================================================================================== the ore barges
def ore_heap(c: Ctx, centre, size, mound: float, n: int, rng) -> None:
    """Ore heaped in a hopper: n rocks in a mound `size` (x, y) wide and `mound` high above `centre` (the hopper's rim level)."""
    protos = [rock_geometry(rng, 1.0, level=2, kind=k, ore=0.18) for k in ("rough", "shard", "rough", "pitted")]
    names = ("MI_SPACE_Rock", "MI_SPACE_Ore", "MI_SPACE_Ice")
    for i in range(n):
        u, v = rng.uniform(-1, 1, 2)
        if u * u + v * v > 1.0:
            continue
        h = mound * (1.0 - 0.78 * (u * u + v * v))
        p = np.asarray(centre) + np.array([u * size[0] / 2, v * size[1] / 2, h * rng.uniform(0.55, 1.0)])
        r = rng.uniform(2.6, 6.2)
        pr = protos[int(rng.integers(len(protos)))]
        Rm = (rot_z_deg(rng.uniform(0, 360)) @ rot_y_deg(rng.uniform(0, 360)) @ rot_x_deg(rng.uniform(0, 360)))
        V = p + (pr["V"] * np.array([1.0, rng.uniform(0.75, 1.0), rng.uniform(0.6, 0.95)]) * r) @ Rm
        mi = np.array([c.g.mi(n_) for n_ in names], np.int16)
        c.g.add(V, pr["F"], mi[pr["mat"]], pr["a1"], pr["a2"], kind="ore")


def hopper(c: Ctx, x: float, y: float, z: float, L: float, W: float, Hh: float, rng, loaded: bool = True) -> None:
    """An ore hopper: a tub of heavy plate on corner posts, a hazard-striped rim, ore heaped above it."""
    g, m = c.g, c.m
    t = 1.4
    g.box((x, y, z - Hh / 2 + 0.9), (L, W, 1.8), m("Frame"), chamfer=0.15, kind="hopper")
    for sx in (-1, 1):
        g.box((x + sx * (L / 2 - t / 2), y, z), (t, W, Hh), m("Frame"), chamfer=0.1, kind="hopper", wear=0.8)
        g.box((x + sx * (L / 2 + 0.05), y, z - Hh * 0.12), (0.3, W * 0.9, Hh * 0.55), m("Engine"), chamfer=0.05, kind="hopper")
    for sy in (-1, 1):
        g.box((x, y + sy * (W / 2 - t / 2), z), (L, t, Hh), m("Frame"), chamfer=0.1, kind="hopper", wear=0.8)
        g.box((x, y + sy * (W / 2 + 0.05), z - Hh * 0.12), (L * 0.9, 0.3, Hh * 0.55), m("Engine"), chamfer=0.05, kind="hopper")
    for sx in (-1, 1):
        for sy in (-1, 1):
            g.box((x + sx * (L / 2), y + sy * (W / 2), z), (3.0, 3.0, Hh + 1.0), m("Frame"), chamfer=0.2, kind="hopper")
    n = 7
    for k in range(n):                                                          # hazard stripes along the rim
        for sx in (-1, 1):
            g.box((x + sx * (L / 2 - 0.4), y - W / 2 + (k + 0.5) * W / n, z + Hh / 2 + 0.3), (0.9, W / n * 0.55, 0.6), m("Trim") if k % 2 else m("Frame"), chamfer=0.0, kind="hopper")
    for sy in (-1, 1):
        for k in range(n):
            g.box((x - L / 2 + (k + 0.5) * L / n, y + sy * (W / 2 - 0.4), z + Hh / 2 + 0.3), (L / n * 0.55, 0.9, 0.6), m("Trim") if k % 2 else m("Frame"), chamfer=0.0, kind="hopper")
    for k in range(5):                                                          # ribs across the walls
        for sy in (-1, 1):
            g.box((x - L / 2 + (k + 0.5) * L / 5, y + sy * (W / 2 + 0.3), z), (0.8, 0.5, Hh * 0.92), m("Frame"), chamfer=0.05, kind="hopper")
    if loaded:
        ore_heap(c, (x, y, z + Hh / 2 - 1.5), (L - 4.0, W - 4.0), 8.0, int(min(70, 0.026 * L * W)), rng)


def build_ore(c: Ctx, variant: str = "A") -> dict:
    g, m, rng = c.g, c.m, c.rng
    rec = Rec()
    st = vessel_style(1.0)
    st = replace(st, scheme=replace(st.scheme, mats=(("Plate", 0.55), ("Frame", 0.25), ("Livery", 0.2))))
    plates: list = []
    xb, xs = 160.0, -160.0
    if variant == "A":
        drive_block(c, rec, xs, -108.0, 16.0, 14.0, 5.0, (-6.0, 6.0), (-6.0, 6.0), st, plates, wings=True)
        keel0, keel1 = -108.0, 112.0
        truss(c, (keel0, 0.0, -18.0), (keel1, 0.0, -18.0), 5.5, bay=10.0, chord=1.2, web=0.6, kind="truss")
        for i, x in enumerate((-70.0, 5.0, 80.0)):
            hopper(c, x, 0.0, 0.0, 70.0, 56.0, 36.0, rng, loaded=rng.random() < 0.9)
            for sy in (-1, 1):                                                  # cradle arms from the keel up to the tub
                beams(c, np.array([[x - 24.0, 0.0, -18.0]]), np.array([[x - 24.0, sy * 26.0, -16.0]]), 1.2, mat="Frame", kind="truss")
                beams(c, np.array([[x + 24.0, 0.0, -18.0]]), np.array([[x + 24.0, sy * 26.0, -16.0]]), 1.2, mat="Frame", kind="truss")
        crew_block(c, rec, 114.0, 152.0, 13.0, 11.0, st, plates, "CERES", zo=-8.0)
        probe(c, xb, r=3.8, L=8.0, z=-8.0 + 11.0 * 0.0)
        K2.mast(c, Xf((126.0, 0.0, -8.0 + 11.0), I3, 1.0), 10.0, dish=4.0, arms=2, beacon=True)
    else:
        drive_block(c, rec, xs, -100.0, 16.0, 14.0, 5.0, (-6.0, 6.0), (-6.0, 6.0), st, plates, wings=True)
        cab = [(x, LF.chamfer_rect(w_, h_, 0.3, top=0.8), 14.0 + h_) for x, w_, h_ in ((-146.0, 9.0, 5.0), (-138.0, 11.0, 9.0), (-116.0, 11.0, 10.0), (-108.0, 8.0, 6.0))]
        cb = hull_loft(c, cab, st, plates, ends=False)
        H.end_face(c, np.array(cab[0][1]), -146.0, -1.0, st, zo=cab[0][2], plate=False)
        H.end_face(c, np.array(cab[-1][1]), -108.0, 1.0, st, zo=cab[-1][2], plate=False)
        for k in (2, 6):
            K2.window_band(c, cb.zone(k), 0.42, -140.0, -112.0, rows=2, lift=0.4, pitch_w=2.4, runs=(3, 7))
        girder(c, (-100.0, 0.0, 0.0), (144.0, 0.0, 0.0), 8.0, 3.2, mat="Frame", bay=10.0, chord=1.0, web=0.5, kind="truss")
        girder(c, (-100.0, 0.0, 0.0), (144.0, 0.0, 0.0), 3.2, 8.0, mat="Frame", bay=10.0, chord=1.0, web=0.5, kind="truss", up=(0.0, 1.0, 0.0))
        for i in range(7):                                                      # pairs of skips along the girder
            x = -78.0 + i * 33.0
            for sy in (-1, 1):
                hopper(c, x, sy * 24.0, 0.0, 28.0, 36.0, 24.0, rng, loaded=rng.random() < 0.85)
                beams(c, np.array([[x, 0.0, 0.0]]), np.array([[x, sy * 20.0, -6.0]]), 1.2, mat="Frame", kind="truss")
        probe(c, xb, r=3.6, L=7.0)
        truss(c, (144.0, 0.0, 0.0), (xb - 6.0, 0.0, 0.0), 2.6, bay=7.0, chord=0.7, web=0.4, kind="truss")
    running_lights(c, rec, xb, xs, 16.0, 16.0, -20.0, size=1.7, glow=360.0)
    rec.lamps_along((-60.0, 0.0, 22.0), (100.0, 0.0, 22.0), 6, WARM, 2.0, 200.0, STEADY)
    finish(c, plates, st, 0.4, 0.25)
    return {"rec": rec, "length_m": 320.0, "cam": [-30.0, 22.0, 55.0], "margin": 0.07, "lens_flat": 70.0, "cams": [[-110.0, 20.0, 55.0], [60.0, 35.0, 55.0]]}


REGISTRY = {
    "SM_VESSEL_Freighter_A": dict(fac="G", seed=131, cls="vessel", build=build_freighter_a),
    "SM_VESSEL_Freighter_B": dict(fac="G", seed=132, cls="vessel", build=build_freighter_b),
    "SM_VESSEL_Freighter_C": dict(fac="G", seed=133, cls="vessel", build=build_freighter_c),
    "SM_VESSEL_Ore_A": dict(fac="G", seed=141, cls="vessel", build=lambda c: build_ore(c, "A")),
    "SM_VESSEL_Ore_B": dict(fac="G", seed=142, cls="vessel", build=lambda c: build_ore(c, "B")),
    "SM_VESSEL_Tug_A": dict(fac="G", seed=101, cls="vessel", build=lambda c: build_tug(c, "A")),
    "SM_VESSEL_Tug_B": dict(fac="G", seed=102, cls="vessel", build=lambda c: build_tug(c, "B")),
    "SM_VESSEL_Tanker_A": dict(fac="G", seed=111, cls="vessel", build=lambda c: build_tanker(c, "A")),
    "SM_VESSEL_Tanker_B": dict(fac="G", seed=112, cls="vessel", build=lambda c: build_tanker(c, "B")),
    "SM_VESSEL_Liner_A": dict(fac="G", seed=121, cls="vessel", build=lambda c: build_liner(c, "A")),
    "SM_VESSEL_Liner_B": dict(fac="G", seed=122, cls="vessel", build=lambda c: build_liner(c, "B")),
}
