"""SPAZIO-VIVO — the places of the Aurelia system, built from the ASTRA ship kit: Keeper Station (and its turning control ring), the Aurelia Arsenal (and its
cranes), the Tiberius refinery and the Ceres mining station.

A place is seen from tens of kilometres first (a lit shape, lamps that blink, a silhouette you can name), then from the bridge window at a few kilometres (the
plates, the windows, the ships at their piers), and a Falcon pilot can fly along it. So each is built in layers of size: the great forms (a spine, a ring, a gantry),
the structure that gives scale (trusses with a bay every 12-16 m, plated hull, window decks), and the small hardware (collars, floodlights, hatches, lettering).

Each builder returns {"rec": Rec, ...}: what the game must know of the mesh (space3_common.Rec) and the preview's wishes (spacegen3.render_views).
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
from ship3_astra import astra_sec, astra_style, flat_field, mark
from ship3_kit import Ctx, Xf
from space3_common import (AMBER, AMBERC, BEACON, CHASER, FLASH2, FLICKER, GREEN, ORANGE, RED, REDPULSE, STEADY, STROBE3, TEAL, UP, WARM, WHITE, Rec, beams, collar,
                           floodlight, frames_x, girder, nav, new_like, pipes, rot_x_deg, rot_y_deg, rot_z_deg, sphere_tank, stamp, tank_cyl, text_on, truss,
                           window_rows, windows_at)

I3 = np.eye(3)
PRE = "MI_HULL_A_"


def sched(t: float, pts) -> float:
    return LF.profile(t, pts)


def hull_stations(x0: float, x1: float, n: int, hw: float, hh: float, wp, hp, zo=lambda t: 0.0, c: float = 0.3, top: float = 0.9, bottom: float = 0.75) -> list:
    out = []
    for i in range(n + 1):
        t = i / n
        out.append((x0 + t * (x1 - x0), LF.chamfer_rect(hw * LF.profile(t, wp), hh * LF.profile(t, hp), c, top=top, bottom=bottom), zo(t)))
    return out


def skipper(boxes):
    """A plate_zone `skip` from rectangles (a0, a1, w0, w1): a plate that touches one is left out (a pier's root, a hatch)."""
    if not boxes:
        return None
    return lambda a0, a1, w0, w1: any(a1 > b[0] and a0 < b[1] and w1 > b[2] and w0 < b[3] for b in boxes)


def band_plating(c: Ctx, st: H.HullStyle, z, a0: float, a1: float, voids=(), strips=(0.12, 0.25), band=(0.40, 0.62), upper_rows=(0.80, 0.90), windows: bool = True,
                 window_lift: float = 0.8, name=None, skip_boxes=()) -> list:
    """A flank in the Navy's way for a station: ivory plates with rows of windows below, a navy livery band with its gold thread, plates and more windows above.
    `name` = (a_start, a_end, text, letter height): a flat navy field in the band with the name in white letters. `skip_boxes`: rectangles (a0, a1, w0, w1) left bare."""
    g, rng, s = c.g, c.rng, st.scheme
    out: list = []
    vs = list(voids)
    sk = skipper(skip_boxes)
    if name:
        vs.append((name[0] - 2.0, name[1] + 2.0))
    lower = (0.0, band[0] - 0.035)
    out += LF.plate_zone(g, z, rng, s, PRE, w_lo=lower[0], w_hi=lower[1], voids=vs, skip=sk)
    out += LF.plate_zone(g, z, rng, s, PRE, w_lo=band[1] + 0.035, w_hi=1.0, voids=vs, skip=sk)
    navy = replace(s, row_w=(band[1] - band[0]) * z.sw(0.5 * (a0 + a1)) * np.array([0.5, 0.52]), plate_len=(28, 80), mats=(("Livery", 1.0),), levels=(0.5,), level_weights=(1.0,),
                   wedge=0.0, tone_sigma=0.05)
    gold = replace(s, row_w=(0.5, 0.6), plate_len=(40, 120), mats=(("Trim", 1.0),), levels=(0.58,), level_weights=(1.0,), wedge=0.0, gap_w=(0.02, 0.03), chamfer=0.05, rim=0.1,
                   tone_sigma=0.03)
    out += LF.plate_zone(g, z, rng, navy, PRE, w_lo=band[0], w_hi=band[1], voids=vs, skip=sk)
    out += LF.plate_zone(g, z, rng, gold, PRE, w_lo=band[0] - 0.03, w_hi=band[0] - 0.006, voids=vs, skip=sk)
    out += LF.plate_zone(g, z, rng, gold, PRE, w_lo=band[1] + 0.006, w_hi=band[1] + 0.03, voids=vs, skip=sk)
    if windows:
        pieces = [(a0, a1)]
        if name or voids:
            cut = sorted(vs)
            pieces, a = [], a0
            for v0, v1 in cut:
                if v0 > a:
                    pieces.append((a, v0))
                a = max(a, v1)
            if a < a1:
                pieces.append((a, a1))
        for lo, hi in pieces:
            if hi - lo < 14.0:
                continue
            for w in strips:
                K2.window_band(c, z, w, lo + 3.0, hi - 3.0, rows=1, lift=window_lift)
            for w in upper_rows:
                K2.window_band(c, z, w, lo + 3.0, hi - 3.0, rows=1, lift=window_lift + 0.2)
    if name:
        a_s, a_e, text, th = name
        pl = flat_field(c, z, a_s, a_e, band[0] + 0.01, band[1] - 0.01, "Livery", 0.45)
        if pl is not None:
            mark(c, pl, 0.5 * (a_s + a_e), 0.5 * (band[0] + band[1]), text, th, mat="Marking", depth=0.35)
    return out


# ===================================================================================================================== KEEPER STATION
KEEPER_X = (-250.0, 380.0)        # the core hull
KEEPER_RING_X = 262.0             # where the control ring turns
KEEPER_RING_R = 285.0             # its centre line
KEEPER_HUB_R = 58.0               # the static collar the ring's sleeve turns on
KEEPER_RING_HW, KEEPER_RING_HH = 22.0, 19.0


def keeper_ring_section(hw: float = KEEPER_RING_HW, hh: float = KEEPER_RING_HH) -> list:
    return LF.chamfer_rect(hw, hh, 0.32, top=0.9, bottom=0.9)


def build_keeper_ring(c: Ctx) -> dict:
    """The control ring: a plated habitat ring (a lit deck of windows all round, a navy band, floodlights) on four spokes and a sleeve that turns on the station's hub.
    Built about its own origin with the turning axis along X: the game turns it about the station's X axis through the hub."""
    g, m, rng = c.g, c.m, c.rng
    rec = Rec()
    st = astra_style(1.5)
    R, hw, hh = KEEPER_RING_R, KEEPER_RING_HW, KEEPER_RING_HH
    ns = 132
    th = np.linspace(0.0, 2.0 * math.pi, ns + 1)
    sec = np.array(keeper_ring_section(hw, hh))                       # (y, z) -> (axial, radial)
    rings = []
    for t in th:
        pts = [(s[0], (R + s[1]) * math.cos(t), (R + s[1]) * math.sin(t)) for s in sec]
        rings.append(pts)
    loft = LF.Loft(th * R, rings)
    plates: list = []
    # chamfer_rect order: 0 bottom, 1 bottom-right, 2 right (+axial), 3 top-right, 4 top (outer), 5 top-left, 6 left (-axial), 7 bottom-left
    sides = {2: "+X", 6: "-X"}
    for k in range(8):
        z = loft.zone(k)
        z.skin(g, m("Frame"))
        if k in (2, 6):
            plates += band_plating(c, st, z, 0.0, 2.0 * math.pi * R, strips=(0.10, 0.25), band=(0.42, 0.60), upper_rows=(0.78,), window_lift=0.7)
        elif k == 4:
            navy = replace(st.scheme, mats=(("Livery", 0.62), ("Plate", 0.38)), plate_len=(30, 90), row_w=(5.0, 9.0))
            plates += LF.plate_zone(g, z, rng, navy, PRE)
        else:
            plates += LF.plate_zone(g, z, rng, st.scheme, PRE, tone_fn=lambda a, w: -0.06)
    H.panelize_plates(c, plates, st, p=0.22)
    H.scatter_details(c, plates, st, density=0.2)
    H.rivet_plates(c, plates, p=0.15)
    # a deck of lit windows on the inner face (the ring's floor looks at the hub: seen from the inside of the ring)
    zi = loft.zone(0)
    K2.window_band(c, zi, 0.5, 0.0, 2.0 * math.pi * R, rows=1, lift=0.6, runs=(6, 22), gap=(6.0, 18.0))
    # ribs round the ring (frame stations)
    H.ribs(c, loft, [x for x in np.arange(40.0, 2.0 * math.pi * R - 30.0, 98.0)], 2.2, 1.2)
    # spokes: four tubes from a sleeve on the hub to the ring's inner face
    r_in = R - hh
    for k in range(4):
        a = math.pi / 2 * k + math.pi / 4
        ey, ez = math.cos(a), math.sin(a)
        p0 = np.array([0.0, KEEPER_HUB_R * 1.1 * ey, KEEPER_HUB_R * 1.1 * ez])
        p1 = np.array([0.0, (r_in + 1.0) * ey, (r_in + 1.0) * ez])
        g.cylinder(p0, p1, 9.0, 8.0, m("Plate"), seg=18, chamfer=0.1, kind="spoke")
        for q in np.linspace(0.18, 0.92, 7):                                  # bands along the spoke
            pc = p0 + (p1 - p0) * q
            g.cylinder(pc - (p1 - p0) / np.linalg.norm(p1 - p0) * 1.6, pc + (p1 - p0) / np.linalg.norm(p1 - p0) * 1.6, 9.6, 9.6, m("Frame"), seg=18, chamfer=0.04, kind="spoke")
        win = p0 + (p1 - p0) * 0.5
        # a lit cabin strip on the spoke (lift cabin)
        n_ = G.norm(np.array([0.0, -ez, ey]))
        windows_at(c, np.array([win + n_ * 8.4 + (p1 - p0) / np.linalg.norm(p1 - p0) * d for d in np.linspace(-30, 30, 7)]),
                   np.tile(n_, (7, 1)), np.tile(G.norm(p1 - p0), (7, 1)), win=(2.4, 1.2))
    # the sleeve: a drum round the hub's collar
    g.cylinder((-17.0, 0, 0), (17.0, 0, 0), KEEPER_HUB_R + 9.0, KEEPER_HUB_R + 9.0, m("Engine"), seg=36, chamfer=0.3, kind="sleeve")
    g.revolve([(KEEPER_HUB_R + 9.2, -19.0), (KEEPER_HUB_R + 12.0, -19.0), (KEEPER_HUB_R + 12.0, -14.0), (KEEPER_HUB_R + 9.2, -14.0), (KEEPER_HUB_R + 9.2, -19.0)], m("Trim"),
              origin=(0, 0, 0), frame=G.frame_z((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)), seg=36, kind="sleeve")
    # floodlights round the rim and running lights (the ring's own lamps, turning with it)
    for k in range(16):
        a = 2.0 * math.pi * k / 16
        ey, ez = math.cos(a), math.sin(a)
        for sx in (-1, 1):
            p = np.array([sx * (hw + 1.4), (R + 1.0) * ey, (R + 1.0) * ez])
            g.box(p, (1.8, 2.4, 2.4), m("Frame"), frame=G.frame_z((sx, 0.0, 0.0), (0.0, ey, ez)), chamfer=0.1, kind="lamp")
            g.box(p + np.array([sx * 1.0, 0.0, 0.0]), (0.15, 1.9, 1.9), m("Lights"), frame=G.frame_z((sx, 0.0, 0.0), (0.0, ey, ez)), chamfer=0.0, kind="lamp", aux=0.1)
    for k in range(4):
        a = math.pi / 2 * k + math.pi / 4
        K2.nav_light(c, np.array([0.0, (R + hh + 0.4) * math.cos(a), (R + hh + 0.4) * math.sin(a)]), np.array([0.0, math.cos(a), math.sin(a)]), (0.0, 0.5, 0.0, 0.5)[k], 1.8)
        a2 = math.pi / 2 * k
        K2.nav_light(c, np.array([0.0, (R + hh + 0.4) * math.cos(a2), (R + hh + 0.4) * math.sin(a2)]), np.array([0.0, math.cos(a2), math.sin(a2)]), 1.0, 1.8)
    for lp in keeper_ring_lamps():
        rec.lamps.append(lp)
    return {"rec": rec, "length_m": 2 * (R + hh), "cam": [-35.0, 28.0, 60.0], "lens_flat": 70.0}


def keeper_ring_lamps() -> list:
    """The ring's lamps in its own frame (they turn with it): red and green running lights on the diagonals, white strobes on the axes, a row of warm floods round the rim."""
    R, hh, hw = KEEPER_RING_R, KEEPER_RING_HH, KEEPER_RING_HW
    out = []
    for k in range(4):
        a = math.pi / 2 * k + math.pi / 4
        out.append({"p": [0.0, (R + hh + 3.0) * math.cos(a), (R + hh + 3.0) * math.sin(a)], "c": list((RED, GREEN, RED, GREEN)[k]), "s": 6.0, "i": 700.0, "pat": STEADY, "ph": 0.0})
        a2 = math.pi / 2 * k
        out.append({"p": [0.0, (R + hh + 3.0) * math.cos(a2), (R + hh + 3.0) * math.sin(a2)], "c": list(WHITE), "s": 7.0, "i": 900.0, "pat": FLASH2, "ph": 0.25 * k})
    for k in range(32):
        a = 2.0 * math.pi * (k + 0.5) / 32
        out.append({"p": [hw + 2.0, (R + 1.0) * math.cos(a), (R + 1.0) * math.sin(a)], "c": list(WARM), "s": 4.0, "i": 380.0, "pat": STEADY, "ph": 0.0})
    return out


def radiator_sail(c: Ctx, centre, along, across, length: float, span: float, thick: float = 0.6, leaves: int = 3) -> None:
    """A flat radiator sail: `centre` its middle, `along` the unit vector of its length, `across` the unit vector of its span (the sail's plane is spanned by the two). A
    frame, leaves of dark panel with a corrugation of heat pipes, headers at the ends and a spine."""
    centre, along, across = np.asarray(centre, np.float64), G.norm(along), G.norm(across)
    nrm = np.cross(along, across)
    for i in range(leaves):
        s0 = -span / 2 + span * i / leaves
        s1 = -span / 2 + span * (i + 1) / leaves
        sm = 0.5 * (s0 + s1)
        fr = np.stack([along, across, nrm])
        c.g.box(centre + across * sm, (length - 1.0, (s1 - s0) - 1.2, thick), c.m("Radiator"), frame=fr, chamfer=0.05, kind="radiator")
        for e in (-1, 1):
            c.g.box(centre + across * sm + along * (e * (length / 2 - 0.4)), (0.9, (s1 - s0) - 0.6, thick + 0.5), c.m("Engine"), frame=fr, chamfer=0.06, kind="radiator")
        for e in (s0 + 0.5, s1 - 0.5):
            c.g.box(centre + across * e, (length, 0.9, thick + 0.5), c.m("Engine"), frame=fr, chamfer=0.06, kind="radiator")
        n = max(6, int(length / 3.0))
        xs = (np.arange(n) + 0.5) / n * (length - 4.0) - (length - 4.0) / 2
        P = centre[None] + along[None] * xs[:, None] + across[None] * sm + nrm[None] * (thick / 2 + 0.12)
        c.g.boxes(P, (0.16, (s1 - s0) / 2 - 1.3, 0.12), c.m("Frame"), frames=fr, chamfer=0.0, kind="radiator")
    c.g.box(centre, (length * 0.96, 1.4, 1.4), c.m("Frame"), frame=np.stack([along, across, nrm]), chamfer=0.1, kind="radiator")


def berth_pier(c: Ctx, rec: Rec, root, tip, hw: float, r: float, roles, max_len: float, floods: int = 2) -> None:
    """A berthing pier from `root` (on the hull) to `tip` (where a hull's bow meets the collar): a lattice boom, a root block on the hull, the collar, floodlights on outriggers,
    a strobe at the tip; the berth goes into the table."""
    g, m, rng = c.g, c.m, c.rng
    root, tip = np.asarray(root, np.float64), np.asarray(tip, np.float64)
    out = G.norm(tip - root)
    L = float(np.linalg.norm(tip - root))
    truss(c, root + out * 4.0, tip - out * 7.0, hw, bay=max(7.0, hw * 2.0), chord=0.35 + hw * 0.07, web=0.22 + hw * 0.035, kind="pier")
    side = G.norm(np.cross(out, UP))
    fr = G.frame_z(out, (0.0, 0.0, 1.0) if abs(out[2]) < 0.9 else (1.0, 0.0, 0.0))
    g.box(root + out * 6.0, (hw * 3.4, hw * 3.4, 12.0), m("Frame"), frame=fr, chamfer=0.3, kind="pier")             # the root block on the hull
    g.box(root + out * 6.0, (hw * 3.0, hw * 3.0, 12.5), m("Plate"), frame=fr, chamfer=0.25, kind="pier")
    for f in np.linspace(0.30, 0.82, floods):
        base = root + out * (L * f)
        for s in (-1, 1):
            q = base + side * (hw + 1.0) * s
            g.box_between(base + side * hw * s, q + side * 2.0 * s, 0.4, 0.4, m("Engine"), kind="lamp")
            g.box(q + side * 2.6 * s, (1.8, 1.0, 1.0), m("Frame"), frame=G.frame_z(side * s, (0.0, 0.0, 1.0)), chamfer=0.06, kind="lamp")
            g.box(q + side * 3.2 * s, (0.12, 1.5, 0.8), m("Lights"), frame=G.frame_z(side * s, (0.0, 0.0, 1.0)), chamfer=0.0, kind="lamp", aux=0.1)
    collar(c, tip, out, r=r, depth=max(5.0, r * 0.55))
    rec.dock(tip, out, max_len, roles)
    rec.lamp(tip - out * 3.0 + UP * (r * 1.25), WHITE, 2.4, 650.0, STROBE3, phase=float(rng.random()))
    rec.lamp(tip - out * 3.0 - UP * (r * 1.25), AMBERC, 2.0, 420.0, AMBER, phase=float(rng.random()))


def build_keeper(c: Ctx) -> dict:
    """Keeper Station (K-1): the Janus Gate's traffic-control and tuning station, ASTRA's. A 630 m core (decks of lit windows, the livery band, berthing piers on both
    flanks: four tender berths, four medium, two heavy), a forward truss of capacitor banks and radiator sails running 250 m towards the Gate, and at the end of it the
    tuning array: six dishes on a hexagonal frame round a needle emitter, all looking at the Gate (-X). The control ring turns on the hub aft (SM_PLACE_KeeperRing,
    its own mesh); the stern is a launch bay for the patrol Falcons, a control tower and a farm of antennas."""
    g, m, rng = c.g, c.m, c.rng
    rec = Rec()
    st = astra_style(1.3)
    plates: list = []
    X0, X1 = KEEPER_X
    HW, HH = 54.0, 46.0
    # ------------------------------------------------------------------------------------------------------------------ the core
    wp = [(0.0, 0.58), (0.05, 0.92), (0.10, 1.0), (0.90, 1.0), (0.96, 0.9), (1.0, 0.68)]
    stations = hull_stations(X0, X1, 36, HW, HH, wp, wp)
    core = LF.Loft.along_x(stations)
    piers = [(-215.0, 1, "tender"), (-215.0, -1, "tender"), (-145.0, 1, "tender"), (-145.0, -1, "tender"), (-55.0, 1, "heavy"), (-55.0, -1, "heavy"),
             (25.0, 1, "mid"), (25.0, -1, "mid"), (145.0, 1, "mid"), (145.0, -1, "mid")]
    pier_x = sorted({p[0] for p in piers})
    PIER_HW = {"tender": 4.6, "mid": 8.4, "heavy": 10.5}
    voids = [(KEEPER_RING_X - 30.0, KEEPER_RING_X + 30.0)]
    roots = {1: [], -1: []}                                                  # per flank: where a pier's root block stands (a, a, w, w on the zone)
    for x, side_, kind in piers:
        half = PIER_HW[kind] * 1.7 + 1.5
        wz = half / (2.0 * HH * 0.7)
        roots[side_].append((x - half, x + half, 0.5 - wz - 0.01, 0.5 + wz + 0.01))
    for z in core.zones():
        z.skin(g, m("Frame"))
    name_span = (176.0, 238.0)
    for k in range(8):
        z = core.zone(k)
        if k in (2, 6):
            plates += band_plating(c, st, z, X0, X1, voids=voids, strips=(0.13, 0.26), band=(0.40, 0.62), upper_rows=(0.80, 0.90), window_lift=0.8,
                                   name=(name_span[0] + 2.0, name_span[1] - 2.0, "KEEPER STATION", 7.0), skip_boxes=roots[1 if k == 2 else -1])
        elif k == 4:
            plates += LF.plate_zone(g, z, rng, st.scheme, PRE, voids=[(KEEPER_RING_X - 30.0, KEEPER_RING_X + 30.0)])
        else:
            plates += LF.plate_zone(g, z, rng, st.scheme, PRE, tone_fn=lambda a, w: -0.06 if k in (0, 1, 7) else 0.0, voids=[(KEEPER_RING_X - 30.0, KEEPER_RING_X + 30.0)])
    H.ribs(c, core, [x for x in np.arange(X0 + 40.0, X1 - 30.0, 52.0) if all(abs(x - v) > 22 for v in pier_x) and abs(x - KEEPER_RING_X) > 34], 1.6, 1.2,
           zones=[0, 1, 3, 4, 5, 7])
    sec0 = np.array(stations[0][1])
    sec1 = np.array(stations[-1][1])
    H.end_face(c, sec0, X0, -1.0, st, plate=False)
    H.end_face(c, sec1, X1, 1.0, st, holes=[(-21.0, 21.0, -10.0, 10.0)])
    # the launch bay at the stern
    K2.hangar_mouth(c, Xf((X1, 0.0, 0.0), I3, 1.0), 42.0, 20.0, 14.0)
    for sx in (-1, 1):
        rec.lamp((X1 + 3.0, sx * 24.0, 11.0), WHITE, 2.4, 520.0, STROBE3, phase=0.1 * sx)
    # the hub collar the ring turns on (static), with a bearing race
    cx = KEEPER_RING_X
    g.cylinder((cx - 30.0, 0, 0), (cx + 30.0, 0, 0), KEEPER_HUB_R, KEEPER_HUB_R, m("Frame"), seg=40, chamfer=0.4, kind="hub")
    for dx in (-26.0, 26.0):
        g.revolve([(KEEPER_HUB_R - 0.2, dx - 1.2), (KEEPER_HUB_R + 2.4, dx - 1.2), (KEEPER_HUB_R + 2.4, dx + 1.2), (KEEPER_HUB_R - 0.2, dx + 1.2), (KEEPER_HUB_R - 0.2, dx - 1.2)],
                  m("Trim"), origin=(cx, 0, 0), frame=G.frame_z((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)), seg=40, kind="hub")
    # ---------------------------------------------------------------------------------------------------------- the berthing piers
    P_ROLE = {"tender": (["tug", "patrol"], 130.0, 4.6, 7.5, 95.0), "mid": (["freight", "passenger", "ore"], 380.0, 8.4, 11.5, 140.0),
              "heavy": (["fuel", "freight", "ore"], 600.0, 10.5, 14.5, 165.0)}
    for x, side_, kind in piers:
        roles, max_len, hw_, rr, tip_y = P_ROLE[kind]
        root = np.array([x, side_ * (HW * 0.93), 0.0])
        tip = np.array([x, side_ * tip_y, 0.0])
        berth_pier(c, rec, root, tip, hw_, rr, roles, max_len)
    # ---------------------------------------------------------------------------------------------------- the forward truss and its banks
    TX0, TX1 = -505.0, X0
    fr_t = truss(c, (TX1, 0.0, 0.0), (TX0, 0.0, 0.0), 15.0, bay=15.0, chord=1.1, web=0.55, kind="truss")
    for sy in (-1, 1):
        for sz in (-1, 1):
            p0 = np.array([-285.0, sy * 40.0, sz * 40.0])
            p1 = np.array([-470.0, sy * 40.0, sz * 40.0])
            tank_cyl(c, p0, p1, 14.5, "Plate", seg=28, bands=6, band_mat="Frame", kind="capacitor")
            fx = G.frame_z((1.0, 0.0, 0.0), (0.0, 0.0, 1.0))
            for q in np.linspace(-300.0, -455.0, 6):                                                # lit rings on the banks
                g.revolve([(14.9, -0.7), (14.9, 0.7)], m("Lights"), origin=(q, sy * 40.0, sz * 40.0), frame=fx, seg=28, kind="capacitor", aux=0.08, wear=0.0)
            # struts to the truss
            for xq in (-310.0, -380.0, -450.0):
                beams(c, np.array([[xq, sy * 15.0, sz * 15.0]]), np.array([[xq, sy * 40.0, sz * 40.0]]), 1.4, mat="Frame", kind="truss")
    # radiator sails above and below the truss (vertical, edge-on to the Gate)
    for sz in (-1, 1):
        for xs_ in (-345.0, -435.0):
            radiator_sail(c, np.array([xs_, 0.0, sz * 95.0]), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0), 84.0, 150.0, leaves=3)
            beams(c, np.array([[xs_, 0.0, sz * 18.0]]), np.array([[xs_, 0.0, sz * 22.0]]), 2.4, mat="Engine", kind="truss")
    # ------------------------------------------------------------------------------------------------------------ the tuning array
    AX = -505.0                                                                                       # the hub of the array
    g.cylinder((AX + 6.0, 0, 0), (AX - 46.0, 0, 0), 24.0, 20.0, m("Plate"), seg=32, chamfer=0.6, kind="array")
    g.cylinder((AX - 40.0, 0, 0), (AX - 64.0, 0, 0), 20.0, 16.0, m("Engine"), seg=32, chamfer=0.4, kind="array")
    HR = 112.0                                                                                        # circumradius of the hexagonal frame
    nodes = []
    for k in range(6):
        a = math.pi / 3 * k + math.pi / 6
        nodes.append(np.array([AX - 34.0, HR * math.cos(a), HR * math.sin(a)]))
    for k in range(6):
        truss(c, nodes[k], nodes[(k + 1) % 6], 3.4, bay=11.0, chord=0.7, web=0.35, kind="array")
        truss(c, np.array([AX - 22.0, 0.0, 0.0]) + (nodes[k] - np.array([AX - 34.0, 0.0, 0.0])) * 0.22, nodes[k], 4.0, bay=12.0, chord=0.8, web=0.4, kind="array")
        d = Xf(nodes[k] + np.array([-3.0, 0.0, 0.0]), frames_x((-1.0, -0.14 * math.cos(math.pi / 3 * k + math.pi / 6), -0.14 * math.sin(math.pi / 3 * k + math.pi / 6)))[0], 1.0)
        g.cylinder(nodes[k] + np.array([6.0, 0.0, 0.0]), nodes[k] + np.array([-5.0, 0.0, 0.0]), 6.0, 6.0, m("Engine"), seg=16, chamfer=0.2, kind="array")
        K2.dish_antenna(c, d, 33.0)
        rec.lamp(nodes[k] + np.array([-34.0, 0.0, 0.0]), TEAL, 3.0, 380.0, STEADY)
    # the needle emitter and its coils
    NX = AX - 60.0
    g.cylinder((NX + 4.0, 0, 0), (NX - 150.0, 0, 0), 9.0, 1.4, m("Engine"), seg=18, kind="needle")
    for q, rr in ((NX - 18.0, 20.0), (NX - 50.0, 16.5), (NX - 80.0, 13.5), (NX - 108.0, 10.5)):
        g.revolve([(rr - 3.5, q - 3.0), (rr + 1.5, q - 3.0), (rr + 1.5, q + 3.0), (rr - 3.5, q + 3.0), (rr - 3.5, q - 3.0)], m("Frame"), origin=(0, 0, 0), frame=G.frame_z((1.0, 0.0, 0.0), (0, 0, 1)),
                  seg=28, kind="needle")
        g.revolve([(rr - 3.6, q - 0.6), (rr - 3.6, q + 0.6)], m("Glow"), origin=(0, 0, 0), frame=G.frame_z((1.0, 0.0, 0.0), (0, 0, 1)), seg=28, kind="needle")
    g.cylinder((NX - 150.0, 0, 0), (NX - 158.0, 0, 0), 1.6, 1.0, m("Glow"), seg=10, kind="needle")
    rec.lamp((NX - 158.0, 0.0, 0.0), TEAL, 9.0, 900.0, FLICKER, 0.0)
    rec.lamp((NX - 158.0, 0.0, 0.0), WHITE, 3.0, 700.0, STEADY)
    # ---------------------------------------------------------------------------------------------- the control block, tower and antennas
    cb = LF.Loft.along_x([(x, LF.chamfer_rect(w_, h_, 0.28, top=0.8), HH * 0.78 + h_) for x, w_, h_ in
                          ((296.0, 22.0, 9.0), (306.0, 28.0, 14.0), (340.0, 28.0, 14.0), (366.0, 22.0, 11.0))])
    cplates: list = []
    for k in range(8):
        zc = cb.zone(k)
        zc.skin(g, m("Frame"))
        cplates += LF.plate_zone(g, zc, rng, replace(st.scheme, row_w=(2.0, 3.6), plate_len=(5.0, 14.0), levels=(0.3, 0.5), min_len=2.5), PRE)
    for k in (2, 6):                                                                                    # the control room's window decks
        K2.window_band(c, cb.zone(k), 0.36, 300.0, 362.0, rows=2, lift=0.5, pitch_w=2.6, win=(2.2, 1.1), runs=(8, 20), gap=(1.0, 3.0))
    H.end_face(c, np.array(LF.chamfer_rect(22.0, 11.0, 0.28, top=0.8)), 366.0, 1.0, st, zo=HH * 0.78 + 11.0, plate=False)
    H.end_face(c, np.array(LF.chamfer_rect(22.0, 9.0, 0.28, top=0.8)), 296.0, -1.0, st, zo=HH * 0.78 + 9.0, plate=False)
    g.box((366.5, 0.0, HH * 0.78 + 12.0), (0.5, 30.0, 6.0), m("Lights"), chamfer=0.0, kind="window", aux=0.05)           # the great window on the stern face
    H.panelize_plates(c, cplates, st, p=0.3)
    for xt, yt, ht in ((331.0, 0.0, 150.0), (352.0, 17.0, 60.0), (352.0, -17.0, 60.0)):
        K2.mast(c, Xf((xt, yt, HH * 0.78 + 26.0), I3, 1.0), ht, dish=14.0 if ht > 100 else 0.0, arms=3, beacon=True)
    rec.lamp((331.0, 0.0, HH * 0.78 + 26.0 + 150.0 + 1.5), WHITE, 5.0, 900.0, FLASH2)
    rec.lamp((352.0, 17.0, HH * 0.78 + 26.0 + 61.0), RED, 3.5, 600.0, REDPULSE)
    rec.lamp((352.0, -17.0, HH * 0.78 + 26.0 + 61.0), RED, 3.5, 600.0, REDPULSE, 0.4)
    for sy in (-1, 1):                                                                                  # the lit launch bay
        g.box((X1 - 13.5, sy * 19.5, 0.0), (0.4, 1.4, 17.0), m("Lights"), chamfer=0.0, kind="hangar", aux=0.05)
    g.box((X1 - 13.8, 0.0, 0.0), (0.4, 40.0, 18.0), m("Lights"), chamfer=0.0, kind="hangar", aux=0.12)
    K2.antenna_farm(c, Xf((-10.0, 0.0, HH * 0.9), I3, 1.0), 30.0, 90.0, n=14)
    K2.antenna_farm(c, Xf((140.0, 0.0, -HH * 0.9), Xf().rot_x(180.0), 1.0), 28.0, 80.0, n=10)
    # a name and a number on the dorsal deck
    text_on(c, "KEEPER", (-120.0, 0.0, HH * 0.995), (0.0, 0.0, 1.0), 17.0, up=(1.0, 0.0, 0.0), depth=0.4)
    # running lights: red to port (+Y), green to starboard (-Y), white aft and at the array
    for xq in (X1 - 3.0, X0 + 30.0):
        nav(c, rec, np.array([xq, HW * 0.62, HH * 0.9]), np.array([0.3, 1.0, 0.3]), 0.0, 1.8, glow=420.0)
        nav(c, rec, np.array([xq, -HW * 0.62, HH * 0.9]), np.array([0.3, -1.0, 0.3]), 0.5, 1.8, glow=420.0)
    nav(c, rec, np.array([X1 + 0.5, 0.0, HH * 0.6]), np.array([1.0, 0.0, 0.0]), 1.0, 1.6, glow=380.0)
    # deck lights for the far view: rows along the flanks, a chaser on the dorsal spine
    for sy in (-1, 1):
        for zz, ph in ((-14.0, 0.0), (12.0, 0.5), (30.0, 0.9)):
            rec.lamps_along((X0 + 30.0, sy * (HW + 1.5), zz), (X1 - 40.0, sy * (HW + 1.5), zz), 22, WARM, 2.2, 230.0, STEADY)
    rec.lamps_along((X0 + 20.0, 0.0, HH + 1.5), (X1 - 20.0, 0.0, HH + 1.5), 24, WHITE, 2.0, 520.0, CHASER, chase=0.18)
    rec.hold_ring(2400.0, 8, 0.12)
    H.panelize_plates(c, plates, st)
    H.scatter_details(c, plates, st, density=0.18)
    H.rivet_plates(c, plates, p=0.2)
    rec.part("SM_PLACE_KeeperRing", (KEEPER_RING_X, 0.0, 0.0), (1.0, 0.0, 0.0), 90.0, 0.0, 0.0, lamps=keeper_ring_lamps())
    return {"rec": rec, "length_m": 1400.0, "cam": [-40.0, 20.0, 55.0], "lens_flat": 70.0, "cams": [[115.0, 14.0, 55.0], [-105.0, 18.0, 55.0], [15.0, 58.0, 55.0]],
            "closeups": [{"name": "pier", "target": [25.0, 150.0, 0.0], "normal": [0.3, 0.9, 0.35], "distance": 260.0, "span": 150.0},
                         {"name": "array", "target": [-560.0, 0.0, 0.0], "normal": [-0.8, -0.5, 0.3], "distance": 520.0, "span": 330.0}]}


REGISTRY = {
    "SM_PLACE_Keeper": dict(fac="A", seed=60, cls="place", build=build_keeper, detail=0.7, **{"with": [("SM_PLACE_KeeperRing", (KEEPER_RING_X, 0.0, 0.0))]}),
    "SM_PLACE_KeeperRing": dict(fac="A", seed=61, cls="part", build=build_keeper_ring),
}
