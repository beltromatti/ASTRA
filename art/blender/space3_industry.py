"""SPAZIO-VIVO — the Free Guilds' places of Aurelia: the Tiberius deuterium refinery (R-1) and the Ceres mining station (C-1).

Both are built in the Guilds' paint (MI_HULL_G_*: worn, practical, mismatched, hazard yellow on rust and grey), and both are the kind of place that is lit from end to end and
never quiet: the refinery's flare burns at the tip of its stack (the game draws the flame from the table: the stack's tip and the flame's length), the mine's mass driver
runs out of the rock like a rail with its coils.

  Refinery  2 km: a long distillation spindle ringed by process collars, columns and spheres of deuterium above and below it, pipe racks along it, a hab and control block at
            one end, a flare stack at the other; six berths (four heavy ones for the tankers on one flank, two medium on the other).
  Mine      0.5 km: a rock (displaced icosphere) with a processing platform bolted to its flank, ore silos and chutes, a derrick over the pit, the mass driver running out along +X,
            three berths for the ore barges.
"""
from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

import ship3_geo as G
import ship3_hull as H
import ship3_kit2 as K2
import ship3_loft as LF
from ship3_kit import Ctx, Xf
from space3_common import (AMBER, AMBERC, CHASER, FLASH2, FLICKER, GREEN, ORANGE, RED, REDPULSE, STEADY, STROBE3, TEAL, UP, WARM, WHITE, Rec, beams, collar, floodlight,
                           girder, nav, pipes, rot_x_deg, rot_y_deg, rot_z_deg, sphere_tank, tank_cyl, text_on, truss, window_rows)
from space3_places import berth_pier, skipper
from space3_props import add_rock, rock_geometry
from space3_vessels import finish, hull_loft, vessel_style

I3 = np.eye(3)
GPRE = "MI_HULL_G_"


def industrial_style(scale: float) -> H.HullStyle:
    """The Guilds' plating for a place: the paint worn through, rust and hazard yellow among the grey."""
    st = vessel_style(scale)
    return replace(st, scheme=replace(st.scheme, mats=(("Plate", 0.72), ("Livery", 0.08), ("Frame", 0.12), ("Trim", 0.06), ("Marking", 0.02)), tone_sigma=0.1))


def ring_collar(c: Ctx, x: float, r: float, w: float, lit_windows: bool = True) -> None:
    """A process collar round a spindle at x: a heavy ring (Engine) with a lit seam and a few lit windows."""
    g, m = c.g, c.m
    fr = G.frame_z((1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    g.revolve([(r, -w / 2), (r + 9.0, -w / 2 + 2.0), (r + 9.0, w / 2 - 2.0), (r, w / 2)], m("Engine"), origin=(x, 0, 0), frame=fr, seg=40, wear=0.7, kind="collar")
    g.revolve([(r + 9.2, -0.7), (r + 9.2, 0.7)], m("Lights"), origin=(x, 0, 0), frame=fr, seg=40, wear=0.0, kind="collar", aux=0.08)


# ===================================================================================================================== TIBERIUS REFINERY
REFINERY_BERTHS = [(-500.0, -1, "heavy"), (-170.0, -1, "heavy"), (160.0, -1, "heavy"), (490.0, -1, "heavy"), (-400.0, 1, "mid"), (300.0, 1, "mid")]
REF_SPEC = {"heavy": (["fuel", "freight"], 640.0, 14.0, 14.5, 250.0), "mid": (["freight", "ore"], 420.0, 10.0, 11.5, 230.0)}


def build_refinery(c: Ctx) -> dict:
    g, m, rng = c.g, c.m, c.rng
    rec = Rec()
    st = industrial_style(2.4)
    st = replace(st, panels=replace(st.panels, min_size=(6.0, 4.0), max_size=(22.0, 12.0), seam=(0.12, 0.25), margin=0.4, lifts=(0.05, 0.1, 0.18)), p_panels=0.2, detail_density=0.06,
                 detail_scale=1.8, stencil_height=0.7)
    plates: list = []
    X0, X1 = -780.0, 700.0
    R = 70.0
    n = 26
    xs = X0 + np.arange(n + 1) * (X1 - X0) / n
    stations = []
    for i, x in enumerate(xs):
        t = i / n
        f = LF.profile(t, [(0.0, 0.5), (0.04, 0.9), (0.08, 1.0), (0.94, 1.0), (0.98, 0.84), (1.0, 0.6)])
        stations.append((float(x), LF.chamfer_rect(R * f, R * f, 0.35), 0.0))
    ber = [(x, s, k) for x, s, k in REFINERY_BERTHS]
    roots = {1: [], -1: []}
    for x, side, kind in ber:
        half = REF_SPEC[kind][2] * 1.7 + 1.5
        roots[side].append((x - half, x + half, 0.5 - half / (2 * R * 0.65) - 0.01, 0.5 + half / (2 * R * 0.65) + 0.01))

    def zone_fn(k, z):
        if k in (2, 6):
            sk = skipper(roots[1 if k == 2 else -1])
            out = LF.plate_zone(g, z, rng, st.scheme, GPRE, skip=sk)
            hz = replace(st.scheme, mats=(("Trim", 1.0),), row_w=(5.0, 6.0), plate_len=(30.0, 90.0), levels=(0.5,), level_weights=(1.0,), wedge=0.0, tone_sigma=0.04)
            out += LF.plate_zone(g, z, rng, hz, GPRE, w_lo=0.46, w_hi=0.58, a_lo=X0 + 30.0, a_hi=X1 - 30.0, skip=sk)                              # a hazard-yellow band all along
            return out
        return None

    hull = hull_loft(c, stations, st, plates, zone_fn=zone_fn, ends=False)
    H.end_face(c, np.array(stations[0][1]), X0, -1.0, st, plate=False)
    H.end_face(c, np.array(stations[-1][1]), X1, 1.0, st, plate=False)
    # the process collars along the spindle, with their lit seams, and the lamps for the far view
    for x in np.arange(-640.0, 641.0, 128.0):
        ring_collar(c, float(x), R, 14.0)
        for a in (0.0, math.pi / 2, math.pi, 3 * math.pi / 2):
            rec.lamp((float(x), (R + 10.0) * math.cos(a), (R + 10.0) * math.sin(a)), AMBERC, 3.0, 340.0, STEADY)
    # the name on both flanks
    for sy in (-1, 1):
        text_on(c, "TIBERIUS REFINERY", (-110.0, sy * (R + 1.0), 0.0), (0.0, sy, 0.0), 17.0, depth=0.5)
        text_on(c, "D2", (-110.0, sy * (R + 1.0), -22.0), (0.0, sy, 0.0), 11.0, depth=0.4)
    # ------------------------------------------------------------------------------------------------------ the spheres of deuterium, above and below the spindle
    for x in (-335.0, -5.0, 325.0):
        for sz in (-1, 1):
            sphere_tank(c, (x, 0.0, sz * 185.0), 85.0, "Trim", seg=44, rings=18, bands=3, band_mat="Frame", kind="tank", wear=0.1)
            for a in range(4):
                ang = math.pi / 2 * a + math.pi / 4
                beams(c, np.array([[x + 38.0 * math.cos(ang), 38.0 * math.sin(ang), sz * (R - 2.0)]]), np.array([[x + 36.0 * math.cos(ang), 36.0 * math.sin(ang), sz * 108.0]]), 5.0, 5.0, mat="Frame",
                      kind="tank")
            g.revolve([(34.0, -4.0), (46.0, -4.0), (46.0, 4.0), (34.0, 4.0), (34.0, -4.0)], m("Engine"), origin=(x, 0.0, sz * (R + 20.0)), frame=G.frame_z((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)), seg=24,
                      kind="tank")
            if sz > 0:
                text_on(c, "D2", (x, 0.0, sz * (185.0 + 85.0)), (0.0, 0.0, sz), 22.0, up=(1.0, 0.0, 0.0), depth=0.4)
            rec.lamp((x, 0.0, sz * (185.0 + 90.0)), RED, 4.0, 700.0, REDPULSE, 0.3 * (x > 0))
            rec.lamp((x, 85.0 * 1.02, sz * 185.0), WARM, 3.0, 300.0, STEADY)
            rec.lamp((x, -85.0 * 1.02, sz * 185.0), WARM, 3.0, 300.0, STEADY)
    # ------------------------------------------------------------------------------------------------------------- the cracking columns, pipe bridges, pipe racks
    cols = [(-700.0, 0.0, 17.0, 160.0), (-640.0, 20.0, 15.0, 130.0), (-640.0, -20.0, 15.0, 150.0), (430.0, 0.0, 18.0, 170.0), (490.0, 22.0, 15.0, 120.0), (550.0, -18.0, 16.0, 140.0)]
    for (x, y, r, h) in cols:
        z0 = R - 6.0
        g.cylinder((x, y, z0), (x, y, z0 + h), r, r * 0.92, m("Plate"), seg=26, chamfer=0.4, kind="column", wear=0.5)
        g.dome((x, y, z0 + h - 1.0), r * 0.92, m("Engine"), seg=26, rings=5, squash=0.8, kind="column")
        for zz in np.arange(z0 + 24.0, z0 + h - 10.0, 26.0):
            g.revolve([(r - 0.2, -0.5), (r + 3.6, -0.5), (r + 3.6, 0.5), (r - 0.2, 0.5)], m("Frame"), origin=(x, y, zz), frame=G.frame_z((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)), seg=26, kind="column")
            g.revolve([(r + 3.6, 0.5), (r + 3.6, 3.0)], m("Engine"), origin=(x, y, zz), frame=G.frame_z((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)), seg=26, kind="column")
        g.revolve([(r * 0.9, 0.0), (r + 1.0, 0.0), (r + 1.0, 7.0), (r * 0.9, 7.0)], m("Livery"), origin=(x, y, z0 + 8.0), frame=G.frame_z((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)), seg=26, kind="column")
        rec.lamp((x, y, z0 + h + r * 0.8), RED, 4.0, 700.0, REDPULSE, float(rng.random()))
    for (xa, xb_) in ((-700.0, -640.0), (430.0, 550.0)):
        girder(c, (xa, 0.0, R + 100.0), (xb_, 0.0, R + 100.0), 5.0, 3.0, mat="Trim", bay=10.0, chord=0.8, web=0.45, kind="pipe")
    for sy in (-1, 1):                                                                                                                     # the pipe racks along the flanks
        for zz, rr in ((46.0, 2.6), (-46.0, 2.6), (58.0, 1.8), (-58.0, 1.8)):
            yy = sy * (R * 0.78 + 4.0)
            pipes(c, np.array([[X0 + 60.0, yy, zz]]), np.array([[X1 - 60.0, yy, zz]]), rr, mat="Engine" if zz > 0 else "Trim", seg=10, kind="pipe")
            for x in np.arange(X0 + 100.0, X1 - 80.0, 70.0):
                g.box((x, yy, zz * 0.5 + math.copysign(R * 0.2, zz)), (1.4, 1.4, abs(zz) * 0.9), m("Frame"), chamfer=0.1, kind="pipe")
    # ------------------------------------------------------------------------------------------------------------------------ the hab and control block
    bs = [(x, LF.chamfer_rect(w_, h_, 0.3, top=0.85), 0.0) for x, w_, h_ in ((-1010.0, 34.0, 30.0), (-975.0, 74.0, 62.0), (-840.0, 76.0, 64.0), (-790.0, 58.0, 48.0))]
    blk = hull_loft(c, bs, st, plates, ends=False)
    H.end_face(c, np.array(bs[0][1]), -1010.0, -1.0, st, plate=False)
    H.end_face(c, np.array(bs[-1][1]), -790.0, 1.0, st, plate=False)
    for k in (2, 6):
        for w in (0.30, 0.46, 0.62, 0.78):
            K2.window_band(c, blk.zone(k), w, -960.0, -820.0, rows=1, lift=0.7, pitch_w=2.8, win=(1.8, 1.0), runs=(5, 14), gap=(2.0, 6.0))
    for sy in (-1, 1):
        text_on(c, "TIBERIUS D2", (-905.0, sy * 77.0, 0.0), (0.0, sy, 0.0), 11.0, depth=0.4)
    K2.mast(c, Xf((-900.0, 0.0, 64.0), I3, 1.0), 90.0, dish=18.0, arms=4, beacon=True)
    K2.antenna_farm(c, Xf((-900.0, 0.0, -64.0), Xf().rot_x(180.0), 1.0), 40.0, 90.0, n=10)
    rec.lamp((-900.0, 0.0, 64.0 + 92.0), WHITE, 6.0, 900.0, FLASH2)
    rec.lamps_along((-960.0, 77.0, 0.0), (-820.0, 77.0, 0.0), 8, WARM, 2.6, 260.0, STEADY)
    rec.lamps_along((-960.0, -77.0, 0.0), (-820.0, -77.0, 0.0), 8, WARM, 2.6, 260.0, STEADY)
    # ------------------------------------------------------------------------------------------------------------------------------ the flare stack
    FX = 770.0
    truss(c, (FX, 0.0, R - 6.0), (FX, 0.0, 330.0), 9.0, bay=16.0, chord=1.6, web=0.8, mat="Trim", mat_web="Frame", kind="stack")
    for zz in (120.0, 200.0, 280.0):
        g.cylinder((FX, 0, zz), (FX, 0, zz + 1.4), 14.0, 14.0, m("Engine"), seg=18, kind="stack")
        for a in range(8):
            ang = 2 * math.pi * a / 8
            g.box((FX + 14.0 * math.cos(ang), 14.0 * math.sin(ang), zz + 2.0), (0.3, 0.3, 2.4), m("Frame"), chamfer=0.0, kind="stack")
    pipes(c, np.array([[FX, 0.0, 330.0]]), np.array([[FX, 0.0, 372.0]]), 3.4, mat="Engine", seg=14, kind="stack")
    g.cylinder((FX, 0, 372.0), (FX, 0, 378.0), 4.4, 3.4, m("Frame"), seg=14, kind="stack")
    pipes(c, np.array([[X1 - 20.0, 0.0, R - 10.0]]), np.array([[FX, 0.0, R + 6.0]]), 4.0, mat="Trim", seg=10, kind="stack")
    for zz in (120.0, 220.0, 330.0):
        rec.lamp((FX + 9.0, 0.0, zz), RED, 4.0, 700.0, REDPULSE, 0.4)
    rec.set_flare((FX, 0.0, 382.0), 220.0)
    rec.lamp((FX, 0.0, 386.0), ORANGE, 9.0, 700.0, FLICKER, 0.0)
    # ------------------------------------------------------------------------------------------------------------------------------------ the berths
    for x, side, kind in ber:
        roles, max_len, hw_, rr, tip = REF_SPEC[kind]
        berth_pier(c, rec, np.array([x, side * R * 0.93, 0.0]), np.array([x, side * tip, 0.0]), hw_, rr, roles, max_len)
    # running lights and strobes
    for k in range(2):
        nav(c, rec, np.array([X1 - 40.0, (-1) ** k * R * 0.72, R * 0.6]), np.array([0.4, (-1) ** k, 0.6]), 0.0 if k == 0 else 0.5, 3.2, glow=520.0)
    rec.lamp((X1 + 4.0, 0.0, 0.0), WHITE, 6.0, 800.0, FLASH2, 0.0)
    rec.lamp((-1012.0, 0.0, 0.0), RED, 5.0, 700.0, REDPULSE, 0.0)
    rec.hold_ring(3300.0, 6, 0.12)
    finish(c, plates, st, 0.2, 0.06)
    return {"rec": rec, "length_m": 2000.0, "cam": [-40.0, 20.0, 50.0], "lens_flat": 60.0, "margin": 0.05, "cams": [[-105.0, 22.0, 50.0], [20.0, 55.0, 50.0], [-150.0, 12.0, 55.0]],
            "closeups": [{"name": "flare", "target": [770.0, 0.0, 250.0], "normal": [0.3, -0.9, 0.2], "distance": 600.0, "span": 400.0},
                         {"name": "berths", "target": [-170.0, -170.0, 0.0], "normal": [0.2, -0.9, 0.4], "distance": 700.0, "span": 600.0}]}


# =========================================================================================================== CERES MINING STATION
MINE_BERTHS = [(-150.0, "mid"), (0.0, "mid"), (150.0, "mid")]


def shifted(sec, dy: float = 0.0, dz: float = 0.0) -> list:
    return [(y + dy, z + dz) for y, z in sec]


def build_mine(c: Ctx) -> dict:
    g, m, rng = c.g, c.m, c.rng
    rec = Rec()
    st = industrial_style(1.1)
    plates: list = []
    ROCK = ("MI_SPACE_Rock", "MI_SPACE_Ore", "MI_SPACE_Ice")
    # ------------------------------------------------------------------------------------------------------------------------------------------ the rock
    rock = rock_geometry(rng, 100.0, level=5, kind="rough", ore=0.22)
    rock["V"] = rock["V"] * np.array([1.35, 0.95, 0.85])                                   # a long, lumpy body about 270 x 165 x 130 m
    add_rock(c, rock, origin=(0.0, 12.0, 0.0), mats=ROCK)
    # ------------------------------------------------------------------------------------------------------------------ the processing platform on the berth flank
    PY, PZ = -114.0, -6.0
    rows = ((-190.0, 14.0, 20.0), (-170.0, 28.0, 26.0), (170.0, 28.0, 26.0), (190.0, 14.0, 20.0))
    stations = [(x, shifted(LF.chamfer_rect(w_, h_, 0.3, top=0.9), PY, PZ), 0.0) for x, w_, h_ in rows]
    plat = hull_loft(c, stations, st, plates, ends=False)
    H.end_face(c, np.array(stations[0][1]), -190.0, -1.0, st, plate=False)
    H.end_face(c, np.array(stations[-1][1]), 190.0, 1.0, st, plate=False)
    for w in (0.3, 0.5, 0.7):
        K2.window_band(c, plat.zone(6), w, -150.0, 150.0, rows=1, lift=0.6, pitch_w=2.6, win=(1.6, 1.0), runs=(3, 9), gap=(3.0, 9.0))
    text_on(c, "CERES MINING GUILD", (0.0, PY - 28.4, PZ + 12.0), (0.0, -1.0, 0.0), 7.0, depth=0.3)
    # struts from the platform to the rock, and the chutes that feed the silos
    for x in (-150.0, -75.0, 0.0, 75.0, 150.0):
        truss(c, (x, PY + 26.0, PZ + 6.0), (x * 0.8, -48.0 if abs(x) < 120 else -30.0, PZ + 14.0), 4.0, bay=10.0, chord=0.9, web=0.5, kind="strut")
    for x in (-110.0, 0.0, 110.0):
        g.cylinder((x, PY, PZ + 24.0), (x, PY, PZ + 84.0), 17.0, 17.0, m("Plate"), seg=22, chamfer=0.4, kind="silo", wear=0.5)
        g.cylinder((x, PY, PZ + 84.0), (x, PY, PZ + 90.0), 15.0, 10.0, m("Engine"), seg=22, chamfer=0.2, kind="silo")
        girder(c, (x, -52.0, 40.0), (x, PY + 10.0, PZ + 84.0), 5.0, 3.0, mat="Trim", bay=8.0, chord=0.7, web=0.4, kind="chute")
        g.revolve([(16.5, 10.0), (18.0, 10.0), (18.0, 13.0), (16.5, 13.0), (16.5, 10.0)], m("Livery"), origin=(x, PY, PZ + 24.0), frame=G.frame_z((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)), seg=22, kind="silo")
        rec.lamp((x, PY, PZ + 94.0), RED, 3.6, 650.0, REDPULSE, float(rng.random()))
    # ------------------------------------------------------------------------------------------------------------------------------ the derrick over the pit
    DX, DY = -46.0, 18.0
    zt = 0.85 * 66.0 * math.sqrt(max(0.0, 1.0 - (DX / 135.0) ** 2 - ((DY - 12.0) / 90.0) ** 2))
    truss(c, (DX, DY, zt - 8.0), (DX, DY, zt + 92.0), 7.0, bay=11.0, chord=1.2, web=0.6, mat="Trim", mat_web="Frame", kind="derrick")
    g.box((DX, DY, zt + 96.0), (16.0, 16.0, 7.0), m("Engine"), chamfer=0.3, kind="derrick")
    for a in range(4):
        ang = math.pi / 2 * a + math.pi / 4
        beams(c, np.array([[DX + 7.0 * math.cos(ang), DY + 7.0 * math.sin(ang), zt + 90.0]]), np.array([[DX + 52.0 * math.cos(ang), DY + 52.0 * math.sin(ang), zt - 16.0]]), 0.7, 0.7, mat="Frame",
              kind="derrick")
    g.cylinder((DX, DY, zt + 100.0), (DX, DY, zt + 106.0), 3.0, 1.6, m("Frame"), seg=10, kind="derrick")
    floodlight(c, rec, np.array([DX + 8.0, DY + 8.0, zt + 99.0]), 6.0, (0.7, 0.7, -0.4), n=3, glow=760.0, size=3.4, scale=1.6)
    floodlight(c, rec, np.array([DX - 8.0, DY - 8.0, zt + 99.0]), 6.0, (-0.7, -0.7, -0.4), n=3, glow=760.0, size=3.4, scale=1.6)
    rec.lamp((DX, DY, zt + 110.0), WHITE, 6.0, 900.0, FLASH2, 0.0)
    rec.lamp((DX, DY, zt + 6.0), ORANGE, 7.0, 520.0, FLICKER, 0.0)                                                         # the pit's glow
    g.cylinder((DX - 22.0, DY, zt - 2.0), (DX + 22.0, DY, zt - 2.0), 3.0, 3.0, m("Lights"), seg=8, kind="pit", aux=0.06, wear=0.0)
    # ------------------------------------------------------------------------------------------------------------------------------------ the mass driver
    MX0, MX1 = 120.0, 268.0
    truss(c, (MX0, 12.0, 20.0), (MX1, 12.0, 20.0), 5.0, bay=12.0, chord=1.2, web=0.6, mat="Trim", mat_web="Frame", kind="driver")
    fx = G.frame_z((1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    for k, x in enumerate(np.arange(MX0 + 14.0, MX1 - 6.0, 12.0)):
        g.revolve([(9.0, -1.4), (11.0, -1.4), (11.0, 1.4), (9.0, 1.4), (9.0, -1.4)], m("Engine"), origin=(float(x), 12.0, 20.0), frame=fx, seg=24, kind="driver")
        g.revolve([(11.1, -0.3), (11.1, 0.3)], m("Glow"), origin=(float(x), 12.0, 20.0), frame=fx, seg=24, kind="driver", wear=0.0)
        if k % 3 == 0:
            rec.lamp((float(x), 12.0, 20.0 + 12.0), TEAL, 3.0, 380.0, CHASER, 0.12 * k)
    g.cylinder((MX1, 12.0, 20.0), (MX1 + 6.0, 12.0, 20.0), 11.0, 8.0, m("Frame"), seg=24, chamfer=0.3, kind="driver")
    rec.lamp((MX1 + 8.0, 12.0, 20.0), TEAL, 7.0, 700.0, FLICKER, 0.0)
    # ------------------------------------------------------------------------------------------------------------------------------------------ the berths
    for x, kind in MINE_BERTHS:
        berth_pier(c, rec, np.array([x, PY - 26.0, PZ]), np.array([x, -214.0, PZ]), 10.0, 11.5, ["ore", "freight"], 360.0)
    K2.mast(c, Xf((120.0, PY, PZ + 20.0), I3, 1.0), 40.0, dish=8.0, arms=3, beacon=True)
    K2.antenna_farm(c, Xf((0.0, PY, PZ - 22.0), Xf().rot_x(180.0), 1.0), 24.0, 60.0, n=8)
    rec.lamp((120.0, PY, PZ + 62.0), WHITE, 5.0, 800.0, FLASH2, 0.3)
    rec.lamps_along((-150.0, PY - 28.4, PZ), (150.0, PY - 28.4, PZ), 8, WARM, 2.4, 260.0, STEADY)
    for k in range(2):
        nav(c, rec, np.array([-186.0, PY + (-1) ** k * 24.0, PZ]), np.array([-0.5, (-1) ** k, 0.2]), 0.0 if k == 0 else 0.5, 2.4, glow=480.0)
    rec.hold_ring(2000.0, 4, 0.1, center=(0.0, 0.0, 100.0))
    finish(c, plates, st, 0.3, 0.1)
    return {"rec": rec, "length_m": 520.0, "cam": [-40.0, 22.0, 50.0], "lens_flat": 60.0, "margin": 0.06, "cams": [[-105.0, 24.0, 50.0], [20.0, 60.0, 50.0]]}


REGISTRY = {
    "SM_PLACE_Refinery": dict(fac="G", seed=64, cls="place", build=build_refinery, detail=0.8),
    "SM_PLACE_Mine": dict(fac="G", seed=65, cls="place", build=build_mine, detail=1.0),
}
