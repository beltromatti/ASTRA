"""SPAZIO-VIVO — the Aurelia Arsenal (A-1): the Navy's orbital yards round New Ravenna, as the Aquila sees them from the bridge window at tens of kilometres and from a Falcon
a few hundred metres off.

3.3 km of spine, plated in the Navy's ivory with the navy livery band and its gold thread and ringed by lit bulkheads; on its port side three dry-dock cages, open lattice each
holding a hull in a different stage of building (frames only, half plated, nearly done), with floodlight masts, catwalks and slewing cranes (SM_PART_ArsenalCrane, its own mesh
that swings); on its starboard side the berthing piers (twelve: four for tenders, five medium, three heavy) where the traffic ties up, bow to the collar; above it the yard
control block with its windows, domes and masts; at one end the ordnance silos under their loader gantry, at the other the reactor and the great radiator sails fanned like
petals; below, the tank farm (spheres of deuterium). Name and number on the flanks.

Frame: x along the spine (the berth side is -Y in Blender = +Y in Unreal's frame), origin at the middle of the spine. The game turns the whole to face its sky.
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
from space3_places import PRE, band_plating, berth_pier, radiator_sail, skipper

I3 = np.eye(3)
SPINE_X = 1640.0
SPINE_HW, SPINE_HH = 62.0, 56.0

# the berthing piers on the starboard (-Y) flank: (x, kind)
ARSENAL_PIERS = [(-1560.0, "tender"), (-1490.0, "tender"), (-1300.0, "mid"), (-950.0, "heavy"), (-540.0, "mid"), (-130.0, "heavy"), (270.0, "mid"), (690.0, "heavy"),
                 (1100.0, "mid"), (1300.0, "mid"), (1490.0, "tender"), (1560.0, "tender")]
PIER_SPEC = {"tender": (["tug", "patrol"], 130.0, 6.5, 7.5, 150.0), "mid": (["freight", "passenger", "ore"], 420.0, 12.0, 11.5, 205.0), "heavy": (["fuel", "freight", "ore"], 640.0, 16.0, 14.5, 235.0)}
CAGES = [(-1030.0, "frames"), (-110.0, "half"), (810.0, "nearly")]
CAGE_L, CAGE_W, CAGE_H, CAGE_Y = 880.0, 260.0, 230.0, 380.0


def spine_profile(t: float) -> float:
    return LF.profile(t, [(0.0, 0.46), (0.03, 0.84), (0.07, 1.0), (0.93, 1.0), (0.97, 0.86), (1.0, 0.58)])


# ===================================================================================================================== the hull on the slip
def building_hull(c: Ctx, rec: Rec, cx: float, cy: float, L: float, hw: float, hh: float, done: float, st: H.HullStyle, plates: list, tag: str) -> None:
    """A warship on its slip: frames every 18 m, stringers, lit decks and machinery inside, plated up to `done` of her length from the stern, the bare frames beyond with plates
    waiting on the slip and a welder's flicker where the plating stops."""
    g, m, rng = c.g, c.m, c.rng
    n = int(L / 18.0)
    prof = [(0.0, 0.34), (0.06, 0.7), (0.14, 0.92), (0.26, 1.0), (0.78, 1.0), (0.92, 0.82), (1.0, 0.46)]
    xs = -L / 2 + np.arange(n + 1) * L / n
    secs = [np.array(LF.chamfer_rect(hw * LF.profile(i / n, prof), hh * LF.profile(i / n, prof), 0.3, top=0.9, bottom=0.78)) for i in range(n + 1)]
    ring = np.stack([np.column_stack([np.full(len(s), cx + xs[i]), s[:, 0] + cy, s[:, 1]]) for i, s in enumerate(secs)])             # (n+1, 8, 3)
    # frames and stringers
    k = ring.shape[1]
    p0 = ring.reshape(-1, 3)
    p1 = np.roll(ring, -1, axis=1).reshape(-1, 3)
    beams(c, p0, p1, 1.5, 1.2, mat="Frame", kind="frames")
    beams(c, ring[:-1].reshape(-1, 3), ring[1:].reshape(-1, 3), 1.4, 1.4, mat="Frame", kind="frames")
    # decks: strips of plate with a lit edge, at three heights
    for zl in (-0.34, 0.0, 0.34):
        for i in range(0, n, 3):
            xa, xb_ = cx + xs[i], cx + xs[min(n, i + 3)]
            wdt = hw * 0.74 * LF.profile((i + 1.5) / n, prof)
            g.box(((xa + xb_) / 2, cy, zl * hh), (xb_ - xa - 1.0, wdt * 2.0, 0.7), m("Plate"), chamfer=0.0, kind="deck", tone=0.4)
            g.box(((xa + xb_) / 2, cy + wdt, zl * hh + 0.5), (xb_ - xa - 1.2, 0.5, 0.3), m("Lights"), chamfer=0.0, kind="deck", aux=0.08)
            g.box(((xa + xb_) / 2, cy - wdt, zl * hh + 0.5), (xb_ - xa - 1.2, 0.5, 0.3), m("Lights"), chamfer=0.0, kind="deck", aux=0.08)
    # machinery inside: blocks and cylinders
    for _ in range(46):
        t = rng.uniform(0.1, 0.9)
        x = cx - L / 2 + t * L
        wmax = hw * 0.6 * LF.profile(t, prof)
        y = cy + rng.uniform(-wmax, wmax)
        z = rng.uniform(-hh * 0.5, hh * 0.5)
        s = rng.uniform(4.0, 12.0)
        g.box((x, y, z), (s * rng.uniform(0.8, 2.0), s, s * rng.uniform(0.6, 1.2)), m("Engine") if rng.random() < 0.5 else m("Frame"), chamfer=0.2, kind="machinery")
    # plating up to the working edge
    hull = LF.Loft.along_x([(cx + float(xs[i]), [(float(p[0]) + cy, float(p[1])) for p in secs[i]], 0.0) for i in range(n + 1)])
    x_edge = cx - L / 2 + done * L
    for zn in hull.zones():
        if done > 0.02:
            zn.skin(g, m("Frame"), a0=cx - L / 2, a1=x_edge)
            plates += LF.plate_zone(g, zn, rng, st.scheme, PRE, a_lo=cx - L / 2, a_hi=x_edge)
    # plates waiting on the slip beside the open part, a gantry hoist over the working edge
    for _ in range(8):
        px = x_edge + rng.uniform(20.0, min(L * 0.3, L * (1.0 - done)))
        py = cy + rng.choice((-1.0, 1.0)) * (hw * 1.18)
        g.box((px, py, -hh * 0.55), (rng.uniform(14.0, 30.0), rng.uniform(5.0, 9.0), 0.6), m("Plate"), chamfer=0.05, kind="stock", tone=0.45)
    rec.lamp((x_edge, cy, hh * 0.1), ORANGE, 4.0, 520.0, FLICKER, float(rng.random()) * 3.0)
    rec.lamp((x_edge - 14.0, cy + hw * 0.8, hh * 0.3), ORANGE, 3.0, 420.0, FLICKER, float(rng.random()) * 3.0)
    rec.lamp((x_edge + 12.0, cy - hw * 0.7, -hh * 0.2), ORANGE, 3.0, 420.0, FLICKER, float(rng.random()) * 3.0)
    rec.lamp((cx, cy, 0.0), WARM, 6.0, 300.0, STEADY)
    rec.lamp((cx - L * 0.25, cy, -hh * 0.2), WARM, 5.0, 260.0, STEADY)
    rec.lamp((cx + L * 0.25, cy, -hh * 0.2), WARM, 5.0, 260.0, STEADY)


def dry_dock_cage(c: Ctx, rec: Rec, cx: float, cy: float, L: float, W: float, Hc: float, i: int) -> None:
    """A slip: four lattice girders the length of the hull, a portal frame every 60 m with its bracing, catwalks along the top, floodlight masts, cross-arms to the spine."""
    g, m, rng = c.g, c.m, c.rng
    hy, hz = W / 2, Hc / 2
    corners = [(1, 1), (-1, 1), (-1, -1), (1, -1)]
    for sy, sz in corners:
        truss(c, (cx - L / 2, cy + sy * hy, sz * hz), (cx + L / 2, cy + sy * hy, sz * hz), 10.0, bay=30.0, chord=2.2, web=1.0, mat="Trim", mat_web="Frame", kind="cage")
    n = int(L / 60.0)
    pts = np.array([(sy * hy, sz * hz) for sy, sz in corners])
    a, b = [], []
    for k in range(n + 1):
        x = cx - L / 2 + k * L / n
        for j in range(4):
            p, q = pts[j], pts[(j + 1) % 4]
            a.append((x, cy + p[0], p[1])); b.append((x, cy + q[0], q[1]))
        if k % 2 == 0:
            a.append((x, cy + pts[0][0], pts[0][1])); b.append((x, cy + pts[2][0], pts[2][1]))
        else:
            a.append((x, cy + pts[1][0], pts[1][1])); b.append((x, cy + pts[3][0], pts[3][1]))
    beams(c, np.array(a), np.array(b), 1.9, 1.6, mat="Trim", kind="cage")
    # the longitudinal bracing in the roof and floor planes
    for sz in (-1, 1):
        a, b = [], []
        for k in range(n):
            x0, x1 = cx - L / 2 + k * L / n, cx - L / 2 + (k + 1) * L / n
            if k % 2 == 0:
                a.append((x0, cy - hy, sz * hz)); b.append((x1, cy + hy, sz * hz))
            else:
                a.append((x0, cy + hy, sz * hz)); b.append((x1, cy - hy, sz * hz))
        beams(c, np.array(a), np.array(b), 1.0, 0.9, mat="Frame", kind="cage")
    # catwalks along the top and the floor rails
    for sy in (-1, 1):
        g.box((cx, cy + sy * (hy - 14.0), hz + 11.5), (L - 20.0, 3.0, 0.5), m("Engine"), chamfer=0.0, kind="cage")
        for k in range(int(L / 20.0)):
            g.box((cx - L / 2 + 10.0 + k * 20.0, cy + sy * (hy - 14.0), hz + 12.7), (0.3, 0.3, 2.0), m("Frame"), chamfer=0.0, kind="cage")
        g.box((cx, cy + sy * (hy - 28.0), -hz - 11.5), (L - 20.0, 5.0, 1.2), m("Engine"), chamfer=0.1, kind="cage")                                     # the slip's rails
    # hazard stripes on the corner posts of the portals at the ends
    for end in (-1, 1):
        for sy, sz in corners:
            for k in range(8):
                g.box((cx + end * (L / 2 + 0.0), cy + sy * hy + 0.0, sz * hz + (k - 3.5) * 2.2), (1.6, 11.0, 1.1), m("Trim") if k % 2 else m("Frame"), chamfer=0.0, kind="cage")
    # floodlight masts along the roof girders, strobes at the corners
    for sy in (-1, 1):
        for k in range(8):
            x = cx - L / 2 + (k + 0.5) * L / 8
            floodlight(c, rec, np.array([x, cy + sy * (hy - 4.0), hz + 11.0]), 12.0, (0.0, -sy, -0.55), n=3, glow=760.0, size=3.6, scale=2.4)
    for end in (-1, 1):
        for sy, sz in corners:
            rec.lamp((cx + end * L / 2, cy + sy * hy, sz * hz + 12.0), WHITE, 5.0, 800.0, STROBE3, 0.17 * i + 0.1 * end)
    # cross-arms to the spine
    for dx in (-L * 0.33, L * 0.33):
        for sz in (-1, 1):
            truss(c, (cx + dx, cy - hy, sz * hz * 0.6), (cx + dx, SPINE_HW * 0.8, sz * hz * 0.6 * 0.4), 7.0, bay=24.0, chord=1.4, web=0.7, kind="arm")


# ===================================================================================================================== the crane (a part)
def build_crane(c: Ctx) -> dict:
    """A slewing yard crane: a lattice mast on a turntable, a long jib with its trolley and hook, a counter-jib with its weight. Its origin is the foot of the mast (the game
    swings it about the vertical through it); its lamps (an amber blink at the jib tip and the weight, a white strobe on top) turn with it."""
    g, m, rng = c.g, c.m, c.rng
    rec = Rec()
    truss(c, (0.0, 0.0, 0.0), (0.0, 0.0, 62.0), 5.5, bay=10.0, chord=1.2, web=0.6, kind="crane")
    g.cylinder((0, 0, 0), (0, 0, 4.0), 9.0, 9.0, m("Engine"), seg=24, chamfer=0.2, kind="crane")
    g.cylinder((0, 0, 60.0), (0, 0, 66.0), 8.0, 7.5, m("Engine"), seg=24, chamfer=0.2, kind="crane")
    g.box((0, 0, 70.0), (16.0, 12.0, 8.0), m("Plate"), chamfer=0.3, kind="crane")                                                                       # the cab
    g.box((7.5, 0.0, 70.8), (1.0, 9.0, 3.0), m("Glass"), chamfer=0.0, kind="crane")
    g.box((7.55, 0.0, 69.0), (0.3, 7.0, 0.4), m("Lights"), chamfer=0.0, kind="crane", aux=0.1)
    girder(c, (-4.0, 0.0, 69.0), (150.0, 0.0, 66.0), 7.0, 4.0, mat="Trim", bay=9.0, chord=0.9, web=0.5, kind="crane")                                  # the jib
    girder(c, (-4.0, 0.0, 69.0), (-44.0, 0.0, 69.0), 7.0, 4.0, mat="Trim", bay=9.0, chord=0.9, web=0.5, kind="crane")                                   # the counter-jib
    g.box((-48.0, 0.0, 67.0), (12.0, 9.0, 8.0), m("Frame"), chamfer=0.3, kind="crane")                                                                  # the weight
    g.box((-48.0, 0.0, 67.0), (12.2, 9.2, 1.0), m("Trim"), chamfer=0.0, kind="crane")
    for sx in (-1, 1):                                                                                                                                  # tie bars from the mast top
        beams(c, np.array([[0.0, 0.0, 78.0]]), np.array([[sx * 0.0 + (150.0 if sx > 0 else -44.0) * 0.82, 0.0, 67.5]]), 0.6, 0.6, mat="Frame", kind="crane")
    g.box((0, 0, 77.0), (3.0, 3.0, 8.0), m("Frame"), chamfer=0.1, kind="crane")
    g.box((100.0, 0.0, 62.0), (8.0, 8.0, 4.0), m("Engine"), chamfer=0.2, kind="crane")                                                                  # the trolley, its cable and hook
    g.cylinder((100.0, 0.0, 62.0), (100.0, 0.0, 22.0), 0.35, 0.35, m("Frame"), seg=6, kind="crane")
    g.box((100.0, 0.0, 20.0), (3.0, 3.0, 4.0), m("Trim"), chamfer=0.2, kind="crane")
    g.box((150.5, 0.0, 66.0), (1.2, 4.0, 4.0), m("Frame"), chamfer=0.1, kind="crane")
    rec.lamps = crane_lamps()
    return {"rec": rec, "length_m": 200.0, "cam": [-35.0, 22.0, 55.0], "margin": 0.08, "lens_flat": 70.0}


def crane_lamps() -> list:
    return [{"p": [150.0, 0.0, 70.0], "c": list(AMBERC), "s": 5.0, "i": 600.0, "pat": AMBER, "ph": 0.0},
            {"p": [-52.0, 0.0, 72.0], "c": list(AMBERC), "s": 4.0, "i": 520.0, "pat": AMBER, "ph": 0.6},
            {"p": [0.0, 0.0, 83.0], "c": list(WHITE), "s": 5.0, "i": 700.0, "pat": STROBE3, "ph": 0.3}]


CRANE_POS = [(cx - 160.0 + 40.0 * i, CAGE_Y, CAGE_H / 2 + 12.0) for i, (cx, _) in enumerate(CAGES)]


# ======================================================================================================================== the Arsenal
def build_arsenal(c: Ctx) -> dict:
    g, m, rng = c.g, c.m, c.rng
    rec = Rec()
    st = astra_style(2.4)
    st = replace(st, scheme=replace(st.scheme, mats=(("Plate", 0.98), ("Frame", 0.02)), tone_sigma=0.08),
                 panels=replace(st.panels, min_size=(7.0, 5.0), max_size=(26.0, 14.0), seam=(0.14, 0.28), margin=0.5, lifts=(0.06, 0.12, 0.2), chamfer=0.06, rim=0.14),
                 p_panels=0.16, detail_density=0.05, detail_scale=2.0, stencil_height=0.8)
    plates: list = []
    HW, HH = SPINE_HW, SPINE_HH
    # ---------------------------------------------------------------------------------------------------------------------------------- the spine
    n = 30
    xs = -SPINE_X + np.arange(n + 1) * (2 * SPINE_X / n)
    stations = [(float(x), LF.chamfer_rect(HW * spine_profile(i / n), HH * spine_profile(i / n), 0.3, top=0.9, bottom=0.8), 0.0) for i, x in enumerate(xs)]
    spine = LF.Loft.along_x(stations)
    ribs_x = [float(x) for x in np.arange(-1500.0, 1501.0, 300.0)]
    pier_x = [p[0] for p in ARSENAL_PIERS]
    roots = {1: [], -1: []}
    for x, kind in ARSENAL_PIERS:
        half = PIER_SPEC[kind][2] * 1.7 + 1.5
        roots[-1].append((x - half, x + half, 0.5 - half / (2 * HH * 0.7) - 0.01, 0.5 + half / (2 * HH * 0.7) + 0.01))
    for z in spine.zones():
        z.skin(g, m("Frame"))
    for k in range(8):
        z = spine.zone(k)
        if k in (2, 6):
            plates += band_plating(c, st, z, -SPINE_X, SPINE_X, windows=False, band=(0.40, 0.62), skip_boxes=roots[1 if k == 2 else -1],
                                   name=(-390.0, -250.0, "AURELIA ARSENAL", 9.0) if k == 6 else (330.0, 450.0, "AURELIA ARSENAL", 9.0))
        else:
            plates += LF.plate_zone(g, z, rng, st.scheme, PRE, tone_fn=lambda a, w, k=k: -0.06 if k in (0, 1, 7) else 0.0)
    H.ribs(c, spine, ribs_x, 14.0, 2.6, zones=[0, 1, 3, 4, 5, 7])
    H.end_face(c, np.array(stations[0][1]), -SPINE_X, -1.0, st, plate=False)
    H.end_face(c, np.array(stations[-1][1]), SPINE_X, 1.0, st, plate=False)
    # the bulkhead rings: a lit seam round the spine at every rib, and the lamps for the far view
    for x in ribs_x:
        ring = spine.ring_at(x)
        cen = ring.mean(axis=0)
        out = ring + G.norm(ring - cen) * 3.3
        beams(c, out, np.roll(out, -1, axis=0), 1.6, 0.7, mat="Lights", kind="ring", aux=0.08)
        for idx in (0, 2, 4, 6):
            rec.lamp(out[idx] + G.norm(ring[idx] - cen) * 1.0, WARM, 3.0, 300.0, STEADY)
    rec.lamps_along((-SPINE_X + 40.0, 0.0, HH + 3.0), (SPINE_X - 40.0, 0.0, HH + 3.0), 36, WHITE, 3.0, 480.0, CHASER, chase=0.22)
    # the service modules along the spine's top: plated units with their window decks, a gold cornice, vents and a roof lamp
    for x0 in [float(v) for v in np.arange(-1440.0, -330.0, 118.0)] + [float(v) for v in np.arange(430.0, 1070.0, 118.0)]:
        l, w, h = float(rng.uniform(70.0, 100.0)), float(rng.uniform(44.0, 74.0)), float(rng.uniform(16.0, 32.0))
        x0 += float(rng.uniform(-8.0, 8.0))
        zc = HH - 3.0 + h / 2
        g.box((x0, 0.0, zc), (l, w, h), m("Plate"), chamfer=0.5, kind="module", tone=float(np.clip(0.5 + rng.normal(0.0, 0.05), 0.3, 0.7)))
        g.box((x0, 0.0, zc + h / 2 - 1.0), (l + 0.8, w + 0.8, 1.3), m("Trim"), chamfer=0.1, kind="module")
        g.box((x0, 0.0, zc - h / 2 + 3.0), (l + 0.6, w + 0.6, 1.0), m("Livery"), chamfer=0.1, kind="module")
        for sy in (-1, 1):
            window_rows(c, np.array([x0 - l / 2 + 5.0, sy * (w / 2 + 0.1), zc - h * 0.1]), np.array([x0 + l / 2 - 5.0, sy * (w / 2 + 0.1), zc - h * 0.1]), (0.0, sy, 0.0),
                        rows=max(1, int(h // 11.0)), pitch=3.0, win=(1.8, 1.1), row_pitch=4.2, runs=(4, 12), gaps=(1, 3))
        for dxv in (-0.25, 0.25):
            g.box((x0 + dxv * l, 0.0, zc + h / 2 + 1.2), (l * 0.2, w * 0.4, 2.2), m("Frame"), chamfer=0.2, kind="module")
        if rng.random() < 0.5:
            rec.lamp((x0, 0.0, zc + h / 2 + 3.0), WARM, 3.0, 300.0, STEADY)
    # --------------------------------------------------------------------------------------------------------------------------- the dry-dock cages
    hulls = [(900.0 * 0.0 + 700.0, 56.0, 40.0), (640.0, 52.0, 36.0), (560.0, 46.0, 32.0)]
    for i, (cx, stage) in enumerate(CAGES):
        dry_dock_cage(c, rec, cx, CAGE_Y, CAGE_L, CAGE_W, CAGE_H, i)
        L_h, hw_h, hh_h = hulls[i]
        done = {"frames": 0.0, "half": 0.58, "nearly": 0.9}[stage]
        building_hull(c, rec, cx, CAGE_Y, L_h, hw_h, hh_h, done, st, plates, stage)
    for i, (px, py, pz) in enumerate(CRANE_POS):
        rec.part("SM_PART_ArsenalCrane", (px, py, pz), (0.0, 0.0, 1.0), 220.0, 0.2 * i, 62.0, lamps=crane_lamps())
    # ------------------------------------------------------------------------------------------------------------------ the berthing piers (starboard flank, -Y)
    for x, kind in ARSENAL_PIERS:
        roles, max_len, hw_, rr, tip_y = PIER_SPEC[kind]
        berth_pier(c, rec, np.array([x, -HW * 0.93, 0.0]), np.array([x, -tip_y, 0.0]), hw_, rr, roles, max_len)
    # ----------------------------------------------------------------------------------------------------------------- the yard control block above the spine
    bx0, bx1 = -250.0, 330.0
    bs = [(bx0 + t * (bx1 - bx0), LF.chamfer_rect(hw_ * 1.0, hh_ * 1.0, 0.3, top=0.82, bottom=0.9), HH + hh_ - 4.0)
          for t, hw_, hh_ in ((0.0, 38.0, 20.0), (0.08, 66.0, 36.0), (0.2, 74.0, 50.0), (0.8, 74.0, 50.0), (0.93, 60.0, 36.0), (1.0, 36.0, 22.0))]
    block = LF.Loft.along_x(bs)
    bplates: list = []
    for z in block.zones():
        z.skin(g, m("Frame"))
    for k in range(8):
        z = block.zone(k)
        if k in (2, 6):
            bplates += band_plating(c, replace(astra_style(1.4)), z, bx0, bx1, strips=(0.14, 0.27), band=(0.42, 0.60), upper_rows=(0.76, 0.86), window_lift=0.8,
                                    name=(bx0 + 170.0, bx0 + 410.0, "YARD CONTROL", 8.0))
        else:
            bplates += LF.plate_zone(g, z, rng, astra_style(1.4).scheme, PRE)
    H.end_face(c, np.array(bs[0][1]), bx0, -1.0, st, zo=bs[0][2], plate=False)
    H.end_face(c, np.array(bs[-1][1]), bx1, 1.0, st, zo=bs[-1][2], plate=False)
    top_z = HH + 96.0
    for xq, yq, rr in ((-80.0, 0.0, 22.0), (120.0, 28.0, 14.0), (120.0, -28.0, 14.0)):                              # the observation and radar domes on the roof
        g.cylinder((xq, yq, top_z - 2.0), (xq, yq, top_z + 3.0), rr * 1.12, rr * 1.05, m("Frame"), seg=28, chamfer=0.15, kind="dome")
        g.dome((xq, yq, top_z + 2.5), rr, m("Glass"), seg=28, rings=6, squash=0.7, kind="dome")
        g.revolve([(rr * 1.06, 0.4), (rr * 1.06, 1.2)], m("Lights"), origin=(xq, yq, top_z + 2.0), frame=G.frame_z((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)), seg=28, kind="dome", aux=0.1, wear=0.0)
    K2.mast(c, Xf((220.0, 0.0, top_z), I3, 1.0), 120.0, dish=22.0, arms=4, beacon=True)
    K2.mast(c, Xf((-170.0, 30.0, top_z - 8.0), I3, 1.0), 70.0, dish=10.0, arms=3, beacon=True)
    K2.antenna_farm(c, Xf((20.0, 0.0, top_z), I3, 1.0), 60.0, 120.0, n=18)
    rec.lamp((220.0, 0.0, top_z + 122.0), WHITE, 7.0, 950.0, FLASH2)
    rec.lamp((-170.0, 30.0, top_z + 72.0), RED, 5.0, 700.0, REDPULSE)
    rec.lamps_along((bx0 + 30.0, 74.5, HH + 30.0), (bx1 - 40.0, 74.5, HH + 30.0), 14, WARM, 2.6, 240.0, STEADY)
    rec.lamps_along((bx0 + 30.0, -74.5, HH + 30.0), (bx1 - 40.0, -74.5, HH + 30.0), 14, WARM, 2.6, 240.0, STEADY)
    H.panelize_plates(c, bplates, st, p=0.2)
    # ----------------------------------------------------------------------------------------------------------------- the ordnance silos, with their loader gantry
    sx0, sx1 = 1120.0, 1560.0
    g.box(((sx0 + sx1) / 2, 0.0, HH + 3.0), (sx1 - sx0, 240.0, 6.0), m("Frame"), chamfer=0.4, kind="silo")
    rows, colsn = 5, 11
    silos = []
    for i in range(rows):
        for j in range(colsn):
            x = sx0 + 24.0 + j * (sx1 - sx0 - 48.0) / (colsn - 1)
            y = (i - (rows - 1) / 2) * 42.0
            silos.append((x, y))
    for (x, y) in silos:
        g.cylinder((x, y, HH + 6.0), (x, y, HH + 70.0), 15.5, 15.5, m("Plate"), seg=18, chamfer=0.3, kind="silo")
        g.revolve([(15.7, 20.0), (16.3, 20.0), (16.3, 22.0), (15.7, 22.0), (15.7, 20.0)], m("Frame"), origin=(x, y, HH + 6.0), frame=G.frame_z((0.0, 0.0, 1.0), (1.0, 0.0, 0.0)), seg=18, kind="silo")
        g.cylinder((x, y, HH + 70.0), (x, y, HH + 71.2), 12.0, 12.0, m("Engine"), seg=18, chamfer=0.1, kind="silo")
        if rng.random() < 0.18:
            g.box((x, y, HH + 71.6), (6.0, 6.0, 0.4), m("Lights"), chamfer=0.0, kind="silo", aux=0.08)
    for yy in (-120.0, 120.0):
        truss(c, (sx0, yy, HH + 98.0), (sx1, yy, HH + 98.0), 5.0, bay=22.0, chord=1.2, web=0.6, kind="gantry")
        for x in np.linspace(sx0, sx1, 6):
            beams(c, np.array([[x, yy, HH + 6.0]]), np.array([[x, yy, HH + 98.0]]), 2.4, 2.4, mat="Frame", kind="gantry")
    for x in np.linspace(sx0, sx1, 6):
        truss(c, (x, -120.0, HH + 98.0), (x, 120.0, HH + 98.0), 4.0, bay=20.0, chord=1.0, web=0.5, kind="gantry")
    for (x, y) in ((sx0, -120.0), (sx0, 120.0), (sx1, -120.0), (sx1, 120.0)):
        rec.lamp((x, y, HH + 104.0), RED, 4.0, 700.0, REDPULSE, 0.5 * (x > 0))
        rec.lamp((x, y, HH + 104.0), WHITE, 4.0, 700.0, STROBE3, 0.2)
    # -------------------------------------------------------------------------------------------------------------------------------- the reactor and the sails
    RX = -SPINE_X - 70.0
    sphere_tank(c, (RX, 0.0, 0.0), 62.0, "Plate", seg=40, rings=16, bands=3, band_mat="Frame", kind="reactor")
    g.revolve([(61.0, -3.0), (92.0, -3.0), (92.0, 3.0), (61.0, 3.0), (61.0, -3.0)], m("Engine"), origin=(RX, 0.0, 0.0), frame=G.frame_z((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)), seg=40, kind="reactor")
    g.cylinder((RX + 55.0, 0, 0), (-SPINE_X + 2.0, 0, 0), 26.0, 30.0, m("Frame"), seg=24, chamfer=0.4, kind="reactor")
    HX = RX - 60.0
    g.cylinder((RX - 54.0, 0, 0), (HX - 90.0, 0, 0), 22.0, 14.0, m("Engine"), seg=24, chamfer=0.4, kind="reactor")
    n_sail = 6
    for k in range(n_sail):
        a = 2 * math.pi * k / n_sail + math.pi / 6
        ey, ez = math.cos(a), math.sin(a)
        centre = np.array([HX - 70.0, 150.0 * ey, 150.0 * ez])
        radiator_sail(c, centre, (1.0, 0.0, 0.0), (0.0, ey, ez), 300.0, 150.0, thick=0.8, leaves=3)
        truss(c, np.array([HX - 10.0, 25.0 * ey, 25.0 * ez]), np.array([HX - 10.0, 76.0 * ey, 76.0 * ez]), 3.2, bay=9.0, chord=0.7, web=0.35, kind="sail")
        truss(c, np.array([HX - 190.0, 25.0 * ey, 25.0 * ez]), np.array([HX - 190.0, 76.0 * ey, 76.0 * ez]), 3.2, bay=9.0, chord=0.7, web=0.35, kind="sail")
        rec.lamp(np.array([HX - 218.0, 228.0 * ey, 228.0 * ez]), RED, 4.0, 650.0, REDPULSE, 0.3 * k)
    # ------------------------------------------------------------------------------------------------------------------------------ the tank farm under the spine
    for i in range(6):
        x = -800.0 + i * 170.0
        sphere_tank(c, (x, 0.0, -HH - 70.0), 52.0, "Trim", seg=36, rings=14, bands=3, band_mat="Frame", kind="tank", wear=0.08)
        for sy in (-1, 1):
            truss(c, (x + 30.0 * sy, sy * 10.0, -HH + 2.0), (x + 22.0 * sy, sy * 25.0, -HH - 40.0), 3.0, bay=8.0, chord=0.7, web=0.35, kind="tank")
        rec.lamp((x, 0.0, -HH - 70.0 - 54.0), WARM, 2.6, 240.0, STEADY)
    # ---------------------------------------------------------------------------------------------------------------------------- lights, holds, the name on the ends
    rec.lamp((SPINE_X + 5.0, 0.0, 0.0), WHITE, 6.0, 800.0, FLASH2, 0.0)
    rec.lamp((-SPINE_X - 5.0, 0.0, HH), RED, 5.0, 700.0, REDPULSE, 0.0)
    for k in range(4):
        nav(c, rec, np.array([SPINE_X - 20.0, (-1) ** k * HW * 0.86, HH * 0.4]), np.array([0.3, (-1) ** k, 0.2]), 0.0 if k % 2 == 0 else 0.5, 3.4, glow=520.0)
    rec.hold_ring(4600.0, 10, 0.12)
    H.panelize_plates(c, plates, st, p=0.18)
    H.scatter_details(c, plates, st, density=0.1)
    H.rivet_plates(c, plates, p=0.1, min_size=(8.0, 3.0), size=0.12, spacing=(4.0, 7.0))
    return {"rec": rec, "length_m": 2 * SPINE_X, "cam": [-45.0, 24.0, 50.0], "lens_flat": 60.0, "margin": 0.04, "cams": [[-100.0, 22.0, 50.0], [25.0, 40.0, 50.0], [-150.0, 8.0, 60.0]],
            "closeups": [{"name": "slip", "target": [-110.0, 380.0, 0.0], "normal": [0.2, 0.9, 0.5], "distance": 1500.0, "span": 900.0},
                         {"name": "piers", "target": [-130.0, -200.0, 0.0], "normal": [0.2, -0.9, 0.35], "distance": 1000.0, "span": 700.0}]}


REGISTRY = {
    "SM_PLACE_Arsenal": dict(fac="A", seed=62, cls="place", build=build_arsenal, detail=0.6, **{"with": [("SM_PART_ArsenalCrane", p) for p in CRANE_POS]}),
    "SM_PART_ArsenalCrane": dict(fac="A", seed=63, cls="part", build=build_crane),
}
