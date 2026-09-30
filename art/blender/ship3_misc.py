"""Free Guilds freighter and the Thule Watch listening post, v3.

  Freighter  bulk hauler, 340 m: a blunt crew section with a lit visor, a square truss spine carrying bays of corrugated cargo pods in
             the Guilds' mismatched colours (some bays half empty, some carrying bulk tanks), a drive section with radiators and four bells.
  Watch      Thule Watch class listening post (ASTRA), ~230 m: a truss spine, a cluster of habitat and operations modules, three great
             dishes, antenna arrays, solar and radiator wings.
"""
from __future__ import annotations

import math
from dataclasses import replace

import numpy as np

import ship3_geo as G
import ship3_hull as H
import ship3_kit2 as K2
import ship3_loft as LF
import ship3_text as TX
from ship3_astra import astra_style
from ship3_kit import Ctx, Xf

I3 = np.eye(3)
GPRE = "MI_HULL_G_"
APRE = "MI_HULL_A_"
POD_COLOURS = [("Plate", 0.28), ("Livery", 0.22), ("Blue", 0.14), ("Green", 0.10), ("Trim", 0.10), ("Frame", 0.10), ("Engine", 0.06)]
COMPANIES = ("BRIGHTWATER", "ORRERY", "HALCYON FREIGHT", "MERIDIAN CO-OP", "NEMET DEEP", "VEYRA GUILDHALL", "SABEL SALT", "TIBERIUS D2")


def guild_style() -> H.HullStyle:
    st = astra_style(0.45)
    sch = replace(st.scheme, row_w=(2.2, 4.0), plate_len=(5.0, 16.0), levels=(0.25, 0.4, 0.55), level_weights=(0.5, 0.3, 0.2), wedge=0.06, chamfer=0.07, rim=0.16, embed=0.25,
                  tone_sigma=0.15, mats=(("Plate", 0.72), ("Livery", 0.16), ("Frame", 0.12)), min_len=2.5)
    pn = replace(st.panels, min_size=(1.6, 1.0), max_size=(6.0, 3.5), seam=(0.05, 0.12), margin=0.18)
    return replace(st, scheme=sch, panels=pn, p_panels=0.4, detail_density=0.3,
                   labels=("GUILD 4471", "NO STEP", "TANK 3 · DEUTERIUM", "MIND YOUR HEAD", "CAUTION · LINE UNDER TENSION", "AIRLOCK 2"))


def _pod(c: Ctx, x: float, y: float, z: float, mat: str, rng, outer: bool, label: bool = True) -> None:
    """A cargo pod (20 x 9 x 9): a corrugated shell, door end with locking bars, corner castings, a company name and a serial."""
    g, m = c.g, c.m
    g.box((x, y, z), (20.0, 9.0, 9.0), m(mat), chamfer=0.10, kind="pod", tone=float(np.clip(0.5 + rng.normal(0, 0.13), 0.1, 0.9)))
    # vertical corrugation on the two long sides that face out (y sides) and the top/bottom
    n = 22
    xs = x - 9.4 + (np.arange(n) + 0.5) * 18.8 / n
    for sy in (-1, 1):
        cs = np.stack([xs, np.full(n, y + sy * 4.55), np.full(n, z)], axis=1)
        g.boxes(cs, (0.12, 0.10, 4.0), m(mat), chamfer=0.0, kind="pod", tone=0.5)
    for sz in (-1, 1):
        cs = np.stack([xs, np.full(n, y), np.full(n, z + sz * 4.55)], axis=1)
        g.boxes(cs, (0.12, 4.0, 0.10), m(mat), chamfer=0.0, kind="pod", tone=0.5)
    # end frames (castings) and the door end
    for sx in (-1, 1):
        g.box((x + sx * 9.85, y, z), (0.32, 9.2, 9.2), m("Frame"), chamfer=0.05, kind="pod")
        for sy in (-1, 1):
            for sz in (-1, 1):
                g.box((x + sx * 9.9, y + sy * 4.4, z + sz * 4.4), (0.5, 0.6, 0.6), m("Engine"), chamfer=0.04, kind="pod")
    for k in range(4):
        g.cylinder((x + 9.99, y - 3.0 + k * 2.0, z - 3.6), (x + 10.12, y - 3.0 + k * 2.0, z + 3.6), 0.07, 0.07, m("Engine"), seg=6, kind="pod")
    if label and outer or (label and rng.random() < 0.5):
        for sy in (-1, 1):
            if abs(y) < 1.0 and sy < 0:
                continue
            nrm = np.array([0.0, sy, 0.0])
            TX.place_text(g, str(rng.choice(COMPANIES)), np.array([x - 2.0, y + sy * 4.7, z + 1.4]), nrm, 0.95, m("Marking"), depth=0.02)
            TX.place_text(g, f"GLD-{int(rng.integers(1000, 9999))}-{int(rng.integers(0, 9))}", np.array([x + 5.0, y + sy * 4.7, z - 2.4]), nrm, 0.4, m("Marking"), depth=0.02)


def _tank(c: Ctx, x: float, y: float, z: float, mat: str, rng) -> None:
    g, m = c.g, c.m
    r, half = 7.2, 8.5
    fr = G.frame_z((1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
    prof = [(r * 0.55, -half - 1.7), (r * 0.9, -half - 0.7), (r, -half), (r, half), (r * 0.9, half + 0.7), (r * 0.55, half + 1.7)]
    g.revolve(prof, m(mat), origin=(x, y, z), frame=fr, seg=28, wear=0.5, kind="tank")
    for dx in (-6.0, 0.0, 6.0):
        g.revolve([(r + 0.02, dx - 0.4), (r + 0.3, dx - 0.4), (r + 0.3, dx + 0.4), (r + 0.02, dx + 0.4), (r + 0.02, dx - 0.4)], m("Frame"), origin=(x, y, z), frame=fr, seg=28, kind="tank")
    g.box((x, y * 0.42, z * 0.42), (3.0, 2.4 + abs(y) * 0.2, 2.4 + abs(z) * 0.2), m("Frame"), chamfer=0.06, kind="tank")


def build_freighter(c: Ctx) -> dict:
    g, rng, m = c.g, c.rng, c.m
    st = guild_style()
    x_bow, x_st = 170.0, -170.0
    g.cuts = [97.0, -101.0]
    cuts = list(g.cuts)
    plates: list = []
    # ---------------------------------------------------------------------------------------------- the crew section
    cx0, cx1 = x_bow - 64.0, x_bow
    rows = ((0.0, 9, 8, 0), (0.12, 13, 11, 0), (0.55, 13, 12, 1), (0.82, 11, 10, 1.5), (1.0, 6, 5, 1.0))
    stations = [(cx0 + t * (cx1 - cx0), LF.chamfer_rect(w_, h_, 0.3, top=0.85, bottom=0.8), z_) for t, w_, h_, z_ in rows]
    crew = LF.Loft.along_x(stations).with_stations(cuts)
    for k in range(8):
        z = crew.zone(k)
        z.skin(g, m("Frame"))
        plates += LF.plate_zone(g, z, rng, st.scheme, GPRE)
    for k in (2, 6):
        for w in (0.3, 0.55):
            K2.window_band(c, crew.zone(k), w, cx0 + 8.0, cx1 - 14.0, rows=1, lift=0.4, pitch_w=2.6)
    H.end_face(c, np.array(stations[0][1]), cx0, -1.0, st, zo=stations[0][2], plate=False)
    H.end_face(c, np.array(stations[-1][1]), cx1, 1.0, st, zo=stations[-1][2], plate=False)
    bx = x_bow - 20.0                                            # the bridge: a raised block with a wide lit visor
    br = LF.Loft.along_x([(bx - 16.0, LF.chamfer_rect(8.0, 3.2, 0.35, top=0.7), 14.0), (bx + 5.0, LF.chamfer_rect(6.5, 2.4, 0.35, top=0.55), 14.6)])
    for k in range(8):
        br.zone(k).skin(g, m("Frame"))
    g.box((bx + 5.2, 0, 15.2), (0.4, 9.5, 1.1), m("Lights"), chamfer=0.0, kind="window", aux=0.1)
    K2.mast(c, Xf((bx - 20.0, 0.0, 13.5), I3, 1.0), 14.0, dish=5.0, arms=3, beacon=True)
    K2.mast(c, Xf((bx - 8.0, 5.0, 17.6), I3, 1.0), 6.0, arms=2, beacon=False)
    g.cylinder((x_bow, 0, 1.0), (x_bow + 2.5, 0, 1.0), 3.4, 3.2, m("Frame"), seg=20, chamfer=0.1, kind="dock")
    g.cylinder((x_bow + 2.5, 0, 1.0), (x_bow + 2.8, 0, 1.0), 2.6, 2.6, m("Lights"), seg=20, kind="dock", aux=0.1)
    g.cylinder((cx0 - 8.0, 0, 0), (cx0 + 1.0, 0, 0), 6.0, 6.0, m("Frame"), seg=14, kind="neck")
    for sy in (-1, 1):                                            # the ship's name on the flanks, and her hull number
        P, N, _ = crew.zone(2 if sy > 0 else 6).frame(np.array([cx0 + 30.0]), np.array([0.8]))
        TX.place_text(g, "BRIGHTWATER", P[0] + N[0] * 0.5, N[0], 2.2, m("Marking"), depth=0.05)
        K2.nav_light(c, P[0] + N[0] * 0.3 + np.array([cx1 - cx0 - 4.0 - 30.0, 0.0, 0.0]), N[0], K2.NAV_RED if sy > 0 else K2.NAV_GREEN, 1.2)
    # ------------------------------------------------------------------------------------------------ the truss spine
    xs0, xs1 = x_st + 64.0, cx0 - 6.0
    t = 3.6
    for sy in (-1, 1):
        for sz in (-1, 1):
            g.box_between((xs0, sy * t, sz * t), (xs1, sy * t, sz * t), 1.2, 1.2, m("Frame"), chamfer=0.06, kind="truss")
    nfr = max(4, int((xs1 - xs0) / 9.0))
    for k in range(nfr + 1):
        x = xs0 + k * (xs1 - xs0) / nfr
        for (y0, z0, y1, z1) in ((-t, -t, t, -t), (-t, t, t, t), (-t, -t, -t, t), (t, -t, t, t)):
            g.box_between((x, y0, z0), (x, y1, z1), 0.7, 0.7, m("Frame"), chamfer=0.0, kind="truss")
        if k < nfr:
            x2 = xs0 + (k + 1) * (xs1 - xs0) / nfr
            za, zb = (-t, t) if k % 2 == 0 else (t, -t)
            for sy in (-1, 1):
                g.box_between((x, sy * t, za), (x2, sy * t, zb), 0.55, 0.55, m("Frame"), chamfer=0.0, kind="truss")
    for sy in (-1, 1):                                            # a service tray along the spine
        g.box(((xs0 + xs1) / 2, sy * (t + 1.3), 0.0), (xs1 - xs0, 0.6, 1.8), m("Engine"), chamfer=0.05, kind="truss")
    # ----------------------------------------------------------------------------------------------------- the cargo
    pitch = 23.0
    bays = int((xs1 - xs0 - 4.0) / pitch)
    x_first = xs0 + (xs1 - xs0 - bays * pitch) / 2 + pitch / 2
    kinds = ["pods"] * bays
    for k in rng.choice(bays, 2, replace=False):
        kinds[int(k)] = "tanks"
    kinds[int(rng.choice([k for k in range(bays) if kinds[k] == "pods"]))] = "cradle"
    off = t + 4.5 + 0.5
    cargo_mats = [x for x, _ in POD_COLOURS]
    cw = np.array([w for _, w in POD_COLOURS])
    cw = cw / cw.sum()
    for k in range(bays):
        x = x_first + k * pitch
        if kinds[k] == "tanks":
            for (ty, tz) in ((11.6, 0.0), (-11.6, 0.0), (0.0, 11.6), (0.0, -11.6)):
                _tank(c, x, ty, tz, "Plate" if rng.random() < 0.6 else "Engine", rng)
            continue
        slots = [(sy * off, sz * off, 0.85, False) for sy in (-1, 1) for sz in (-1, 1)]
        slots += [(sy * (off + 9.4), sz * off, 0.55, True) for sy in (-1, 1) for sz in (-1, 1)]
        for (y, z, p, outer) in slots:
            if kinds[k] == "cradle" and rng.random() < 0.75:
                g.box((x, y, z - math.copysign(4.6, z)), (20.0, 0.5, 0.5), m("Frame"), chamfer=0.03, kind="truss")
                continue
            if rng.random() > p:
                continue
            _pod(c, x, y, z, str(rng.choice(cargo_mats, p=cw)), rng, outer)
            if not outer:
                for sx in (-1, 1):
                    g.box((x + sx * 6.5, math.copysign(t + 0.25, y), math.copysign(t + 0.25, z)), (2.4, 1.4, 1.4), m("Frame"), chamfer=0.04, kind="truss")
    # ----------------------------------------------------------------------------------------------- the drive section
    dx0, dx1 = x_st + 8.0, xs0 + 6.0
    rows = ((0.0, 16, 14), (0.15, 17, 15), (0.7, 16, 14), (1.0, 10, 9))
    stations = [(dx0 + t_ * (dx1 - dx0), LF.chamfer_rect(w_, h_, 0.3), 0.0) for t_, w_, h_ in rows]
    drive = LF.Loft.along_x(stations).with_stations(cuts)
    for k in range(8):
        z = drive.zone(k)
        z.skin(g, m("Frame"))
        plates += LF.plate_zone(g, z, rng, st.scheme, GPRE)
    for sy in (-1, 1):                                            # fuel tanks up and down the flanks, radiator wings, fins
        for sz in (-1, 1):
            g.cylinder((dx0 + 12.0, sy * 8.0, sz * 15.5), (dx1 - 12.0, sy * 8.0, sz * 15.5), 3.2, 3.2, m("Engine"), seg=16, chamfer=0.1, kind="tank")
    K2.radiator_wing(c, Xf((dx0 + 10.0, 17.0, 0.0), I3, 1.0), 42.0, 20.0, 12.0, leaves=2)
    K2.radiator_wing(c, Xf((dx1 - 8.0, -17.0, 0.0), Xf().rot_z(180.0), 1.0), 42.0, 20.0, 12.0, leaves=2)
    for k in range(8):
        x = dx0 + 6.0 + k * (dx1 - 18.0 - dx0) / 7
        g.box((x, 0.0, 15.2 + 4.5), (0.45, 5.4, 9.0), m("Radiator"), chamfer=0.03, kind="radiator")
    g.box((x_st + 2.0 + (dx0 + 1.0 - x_st - 2.0) / 2, 0, 0), (dx0 + 1.0 - x_st - 2.0, 30.0, 28.0), m("Frame"), chamfer=0.2, kind="engine")
    K2.engine_bank(c, x_st + 2.0, [-6.5, 6.5], [-6.5, 6.5], 5.4)
    K2.nav_light(c, np.array([x_st + 4.0, 0.0, 15.3]), np.array([-0.3, 0.0, 1.0]), K2.NAV_WHITE, 1.2)
    # ---------------------------------------------------------------------------------------------------- details and cuts
    H.panelize_plates(c, plates, st)
    H.scatter_details(c, plates, st)
    H.rivet_plates(c, plates)
    from ship3_cut import make_cut
    neck = [(6.2 * math.cos(a), 6.2 * math.sin(a)) for a in np.linspace(0.0, 2 * math.pi, 14, endpoint=False)]
    faces = []
    for i, (xc, poly) in enumerate(((cuts[0], neck), (cuts[1], drive.ring_at(cuts[1])[:, 1:3]))):
        faces.append(make_cut(c, np.asarray(poly, np.float64), xc, +1, i, depth=14.0, scale=0.4))
        faces.append(make_cut(c, np.asarray(poly, np.float64), xc, -1, i + 1, depth=14.0, scale=0.4))
    return {"cuts": cuts, "cut_faces": faces, "length_m": 355.0, "cam_az": -30.0, "cam_el": 22.0, "cam_dist": 1.9, "sun_az": -50.0, "sun_el": 30.0,
            "closeups": [{"name": "cargo", "target": [-30.0, -14.0, 0.0], "normal": [0.0, -1.0, 0.3], "distance": 100.0, "span": 50.0}], "pieces_gap": 0.13}


# =================================================================================================================== the station
def build_watch(c: Ctx) -> dict:
    g, rng, m = c.g, c.rng, c.m
    st = astra_style(0.5)
    plates: list = []
    L = 220.0
    t = 4.0
    for sy in (-1, 1):
        for sz in (-1, 1):
            g.box_between((-L / 2, sy * t, sz * t), (L / 2, sy * t, sz * t), 1.3, 1.3, m("Frame"), chamfer=0.06, kind="truss")
    for k in range(23):
        x = -L / 2 + k * L / 22
        for (y0, z0, y1, z1) in ((-t, -t, t, -t), (-t, t, t, t), (-t, -t, -t, t), (t, -t, t, t)):
            g.box_between((x, y0, z0), (x, y1, z1), 0.7, 0.7, m("Frame"), chamfer=0.0, kind="truss")
        if k < 22:
            for sy in (-1, 1):
                g.box_between((x, sy * t, -t if k % 2 == 0 else t), (x + L / 22, sy * t, t if k % 2 == 0 else -t), 0.5, 0.5, m("Frame"), chamfer=0.0, kind="truss")
    # the operations core
    rows = ((-34, 10, 10), (-30, 16, 15), (-10, 18, 17), (10, 18, 17), (30, 16, 15), (34, 10, 10))
    core = LF.Loft.along_x([(x, LF.chamfer_rect(w_, h_, 0.35), 0.0) for x, w_, h_ in rows])
    sch = replace(st.scheme, row_w=(2.5, 4.5), plate_len=(5, 14), levels=(0.3, 0.5), min_len=2.5)
    for k in range(8):
        z = core.zone(k)
        z.skin(g, m("Frame"))
        plates += LF.plate_zone(g, z, rng, sch, APRE)
    for k in (2, 6):
        K2.window_band(c, core.zone(k), 0.35, -22.0, 22.0, rows=2, lift=0.4, pitch_w=2.6)
    H.end_face(c, np.array(LF.chamfer_rect(10, 10, 0.35)), -34.0, -1.0, st, plate=False)
    H.end_face(c, np.array(LF.chamfer_rect(10, 10, 0.35)), 34.0, 1.0, st, plate=False)
    P, N, _ = core.zone(6).frame(np.array([-6.0]), np.array([0.65]))
    TX.place_text(g, "THULE WATCH", P[0] + N[0] * 0.4, N[0], 2.2, m("Marking"), depth=0.05)
    TX.astra_emblem(g, P[0] + N[0] * 0.4 + np.array([16.0, 0.0, 0.0]), N[0], 6.0, m("Marking"), depth=0.05)
    # habitat drums along the spine
    for x, r in ((-60, 9.0), (55, 8.0), (-85, 6.5), (80, 6.0)):
        ring = [(r * math.cos(a), r * math.sin(a)) for a in np.linspace(0.0, 2 * math.pi, 16, endpoint=False)]
        drum = LF.Loft.along_x([(x + dx, ring, 0.0) for dx in (-12.0, 12.0)])
        dsch = replace(st.scheme, row_w=(2.0, 3.0), plate_len=(4, 10), levels=(0.25, 0.4), min_len=2.0)
        for k in range(16):
            z = drum.zone(k)
            z.skin(g, m("Frame"))
            plates += LF.plate_zone(g, z, rng, dsch, APRE)
        for j in range(3):
            g.revolve([(r + 0.02, -0.5), (r + 0.55, -0.5), (r + 0.55, 0.5), (r + 0.02, 0.5), (r + 0.02, -0.5)], m("Frame"), origin=(x - 12.0 + j * 11.0, 0, 0),
                      frame=G.frame_z((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)), seg=20, kind="drum")
        H.end_face(c, np.array(ring), x - 12.0, -1.0, st, plate=False)
        H.end_face(c, np.array(ring), x + 12.0, 1.0, st, plate=False)
    # three great dishes on pylons
    for x, y, z, r, tilt in ((-20, 0, 26, 22, 0), (70, 16, 14, 14, 35), (-100, -14, 12, 12, -30)):
        g.cylinder((x, y, 5.0), (x, y, z), 1.6, 1.6, m("Frame"), seg=10, kind="pylon")
        fr = Xf((x, y, z), np.array([[math.cos(math.radians(tilt)), 0.0, math.sin(math.radians(tilt))], [0.0, 1.0, 0.0], [-math.sin(math.radians(tilt)), 0.0, math.cos(math.radians(tilt))]]), 1.0)
        K2.dish_antenna(c, fr.sub((0.0, 0.0, 0.0), np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]])), r)
    for k in range(9):                                             # antenna masts along the spine
        x = -L / 2 + 20 + k * 22
        K2.mast(c, Xf((x, rng.choice((-1, 1)) * 4.0, rng.choice((-1, 1)) * 4.0), I3, 1.0), float(rng.uniform(10, 28)), arms=2, beacon=k % 3 == 0)
    K2.antenna_farm(c, Xf((-10.0, 0.0, 17.5), I3, 1.0), 10.0, 16.0, n=8)
    # solar and radiator wings on both flanks
    for sy in (-1, 1):
        for k in range(3):
            x = -95.0 + k * 40.0
            y0 = sy * 34.0
            mat = "Radiator" if k == 1 else "Livery"
            g.box((x, y0, 0.0), (30.0, 52.0, 0.4), m(mat), chamfer=0.05, kind="wing")
            g.box((x, y0, 0.3), (30.6, 0.5, 0.6), m("Frame"), chamfer=0.03, kind="wing")
            g.box((x, y0 + sy * 25.6, 0.3), (30.6, 0.5, 0.6), m("Frame"), chamfer=0.03, kind="wing")
            for j in range(1, 12):                                     # cell rows
                g.box((x, y0 - 26.0 + j * 4.33 * 1.0, 0.25), (30.0, 0.10, 0.12), m("Frame"), chamfer=0.0, kind="wing")
            for j in range(1, 8):
                g.box((x - 15.0 + j * 3.75, y0, 0.25), (0.10, 52.0, 0.12), m("Frame"), chamfer=0.0, kind="wing")
            g.cylinder((x, sy * 5.0, 0.0), (x, sy * 8.0, 0.0), 0.8, 0.8, m("Frame"), seg=8, kind="wing")
            g.box_between((x, sy * 8.0, 0.0), (x, sy * 26.0, 0.0), 0.5, 0.5, m("Engine"), chamfer=0.02, kind="wing")
    K2.nav_light(c, np.array([L / 2, 0.0, 5.0]), np.array([1.0, 0.0, 0.0]), K2.NAV_RED, 1.4)
    K2.nav_light(c, np.array([-L / 2, 0.0, 5.0]), np.array([-1.0, 0.0, 0.0]), K2.NAV_GREEN, 1.4)
    K2.nav_light(c, np.array([0.0, 0.0, 20.0]), np.array([0.0, 0.0, 1.0]), K2.NAV_WHITE, 1.4)
    H.panelize_plates(c, plates, st)
    H.scatter_details(c, plates, st)
    H.rivet_plates(c, plates)
    return {"length_m": 232.0, "cuts": None, "cam_az": -30.0, "cam_el": 22.0, "cam_dist": 1.9, "sun_az": -50.0, "sun_el": 30.0, "closeups": []}
