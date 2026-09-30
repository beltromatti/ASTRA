"""ASTRA Navy ships v3 (docs/STILE.md §2): long layered ivory plates on a gunmetal structure, a navy livery band with a thin gold
thread, white hull numbers, folding radiators on the flanks, warm windows, white-blue drives.

  Aquila     carrier cruiser, 780 m (the player's ship: the hull envelope, the island that carries the bridge and the bow launch
             tubes are exactly the v2 ones — the interiors are built inside them, see data/ship/aquila_*.json)
  Praetorian battleship, ~1100 m
  Vigilant   destroyer, ~300 m
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np

import ship3_cut
import ship3_geo as G
import ship3_hull as H
import ship3_kit as K
import ship3_kit2 as K2
import ship3_loft as LF
import ship3_panels as PN
import ship3_text as TX
from ship3_cut import make_all_cuts
from ship3_kit import Ctx, Xf

PRE = "MI_HULL_A_"
NAVY, GOLD = "Livery", "Trim"
I3 = np.eye(3)


def astra_style(scale: float = 1.0) -> H.HullStyle:
    """The Navy's plating: long plates in staggered rows, three thickness levels, a slight wedge (layered like feathers)."""
    s = scale
    return H.HullStyle(
        scheme=LF.Scheme(row_w=(3.4 * s, 6.6 * s), plate_len=(14 * s, 52 * s), gap_a=(0.28, 0.55), gap_w=(0.3, 0.65), levels=(0.42, 0.62, 0.85),
                         level_weights=(0.5, 0.32, 0.18), wedge=0.16, chamfer=0.10, rim=0.28, embed=0.35, tone_sigma=0.12,
                         mats=(("Plate", 0.93), ("Frame", 0.07)), min_len=5.0),
        panels=PN.PanelStyle(min_size=(2.4, 1.6), max_size=(9.0, 5.5), seam=(0.07, 0.16), margin=0.25, lifts=(0.035, 0.07, 0.11),
                             lift_w=(0.45, 0.35, 0.2), chamfer=0.03, rim=0.07, p_stop=0.35, tone_sigma=0.045, p_alt=0.05),
        p_panels=0.42, detail_density=0.34,
        weights={"hatch": 3, "vent": 2, "blister": 1, "lamp": 1, "cable": 2, "stencil": 0.6},
        labels=("ACCESS 4C-12", "COOLANT", "NO STEP", "DECK 4 · SECTION C", "AUTHORIZED PERSONNEL ONLY", "FUEL", "O2 SUPPLY", "HATCH 7B",
                "CAUTION"), stencil_height=0.3)


def astra_sec(w: float, h: float) -> list:
    """ASTRA's calm hull section: a wide deck, sloping shoulders, tall flanks, a narrower keel."""
    return LF.chamfer_rect(w, h, 0.3, top=0.9, bottom=0.72)


def ring_rect(x0: float, x1: float, hy: float, z: float, c: float) -> np.ndarray:
    """A chamfered rectangle ring (x, y) at height z as 3D points: a tower's footprint."""
    pts = [(x0 + c, -hy), (x1 - c, -hy), (x1, -hy + c), (x1, hy - c), (x1 - c, hy), (x0 + c, hy), (x0, hy - c), (x0, -hy + c)]
    return np.array([(x, y, z) for x, y in pts])


def top_z(loft: LF.Loft, x: float) -> float:
    return float(loft.ring_at(x)[:, 2].max())


def flat_field(c: Ctx, zone, a0, a1, w0, w1, mat: str = "Plate", t: float = 0.4) -> LF.Plate | None:
    """One big flat plate (no seams, no panels): a clean field for lettering, an emblem or the name decal."""
    outline = np.array([[a0, w0], [a1, w0], [a1, w1], [a0, w1]])
    if LF.slab(c.g, zone, outline, c.m(mat), lambda a: np.zeros_like(a), t, t, 0.10, 0.3, 0.35, tone=0.5, kind="plate"):
        return LF.Plate(zone, a0, a1, w0, w1, t, t, c.m(mat), 0.5, outline)
    return None


def mark(c: Ctx, plate: LF.Plate, a: float, w: float, text: str, height: float, up=(0.0, 0.0, 1.0), mat: str = "Marking", depth: float = 0.05) -> float:
    P, N, T = plate.top(np.array([a]), np.array([w]), 0.0)
    return TX.place_text(c.g, text, P[0], N[0], height, c.m(mat), up=up, depth=depth)


def on_zone(zone, a: float, w: float, lift: float = 0.0, ex=(1.0, 0.0, 0.0)):
    """(point, frame rows) standing on a zone at (a, w), z along the surface normal, x as close to `ex` as possible."""
    P, N, _ = zone.frame(np.array([a]), np.array([w]))
    return P[0] + N[0] * lift, G.frame_z(N[0], ex)


def flank_plating(c: Ctx, st: H.HullStyle, z: LF.Zone, voids, cuts, x_span, name_span=None, strips=((0.10, 0.148), (0.27, 0.318)),
                  band=(0.52, 0.715), lower_top: float = 0.485, upper_from: float = 0.75, window_lift: float = 0.76, band_row=(3.6, 4.2)) -> list:
    """A vertical flank, the Navy's way: plates below the navy band with window strips (ribbons carrying rows of lit and dark
    windows), the band with its gold thread above and below, plates over it. name_span: an x range kept clear for a flat field
    (the game projects a name decal there). Returns the plates."""
    g, rng, s = c.g, c.rng, st.scheme
    clear = (lambda x0, x1, w0, w1: x1 > name_span[0] and x0 < name_span[1]) if name_span else None
    out: list = []
    strip = replace(s, row_w=(1.4, 1.8), plate_len=(50, 120), levels=(0.7,), level_weights=(1.0,), wedge=0.0, mats=(("Frame", 1.0),),
                    gap_w=(0.02, 0.03), tone_sigma=0.04)
    edges_w = [0.0] + [x for r in strips for x in r] + [lower_top]
    for i in range(0, len(edges_w) - 1, 2):
        out += LF.plate_zone(g, z, rng, s, PRE, w_lo=edges_w[i], w_hi=edges_w[i + 1], skip=clear, voids=voids)
    edges = [x_span[0]] + [x for r in voids for x in r] + [x_span[1]]
    spans = [(edges[i], edges[i + 1]) for i in range(0, len(edges) - 1, 2)]
    for lo, hi in strips:
        out += LF.plate_zone(g, z, rng, strip, PRE, w_lo=lo, w_hi=hi, skip=clear, voids=voids)
        for sa, sb in spans:                                          # rows of windows along the strip, between the ribs
            pieces = [(sa, sb)]
            if name_span:
                pieces = [(sa, min(sb, name_span[0])), (max(sa, name_span[1]), sb)]
            for lo_a, hi_a in pieces:
                for xc in cuts:                                        # the cut planes stay clear
                    if lo_a < xc < hi_a:
                        pieces.append((xc + 4.0, hi_a))
                        hi_a = xc - 4.0
                        break
                if hi_a - lo_a > 12.0:
                    K2.window_band(c, z, 0.5 * (lo + hi), lo_a + 2.0, hi_a - 2.0, rows=1, lift=window_lift)
    navy = replace(s, row_w=band_row, plate_len=(30, 90), mats=((NAVY, 1.0),), levels=(0.5,), level_weights=(1.0,), wedge=0.0, tone_sigma=0.05)
    gold = replace(s, row_w=(0.4, 0.5), plate_len=(40, 120), mats=((GOLD, 1.0),), levels=(0.58,), level_weights=(1.0,), wedge=0.0,
                   gap_w=(0.02, 0.03), chamfer=0.05, rim=0.1, tone_sigma=0.03)
    out += LF.plate_zone(g, z, rng, navy, PRE, w_lo=band[0], w_hi=band[1], voids=voids)
    out += LF.plate_zone(g, z, rng, gold, PRE, w_lo=band[0] - 0.028, w_hi=band[0] - 0.005, voids=voids)
    out += LF.plate_zone(g, z, rng, gold, PRE, w_lo=band[1] + 0.005, w_hi=band[1] + 0.028, voids=voids)
    out += LF.plate_zone(g, z, rng, s, PRE, w_lo=upper_from, w_hi=1.0, voids=voids)
    if name_span:
        flat_field(c, z, name_span[0] + 4.0, name_span[1] - 4.0, 0.03, lower_top - 0.015, "Plate", 0.4)
    return out


# ------------------------------------------------------------------------------------------------------------ the Aquila
class Aquila:
    """The Aquila's build: one method per part, so the pieces read like the ship's own list of works."""
    L, W, H = 780.0, 50.0, 24.0
    X_ST, X_BW = -372.0, 390.0
    ISLAND_TOP = 60.4
    NAME_SPAN = (143.0, 217.0)          # x range of the flank fields kept clear for the game's name decal

    def __init__(self, c: Ctx, cuts=(236.0, -105.0), features: bool = True):
        self.c, self.g, self.rng = c, c.g, c.rng
        self.cuts = list(cuts)
        self.g.cuts = list(cuts)
        self.st = astra_style()
        self.features = features
        wp = [(0.0, 0.9), (0.08, 1.0), (0.72, 1.0), (1.0, 0.62)]
        hp = [(0.0, 0.95), (0.1, 1.0), (0.75, 1.0), (1.0, 0.72)]
        n = max(10, int((self.X_BW - self.X_ST) / 16))
        stations = [(self.X_ST + (i / n) * (self.X_BW - self.X_ST), astra_sec(self.W * LF.profile(i / n, wp), self.H * LF.profile(i / n, hp)),
                     -self.H * 0.15 * max(0.0, (i / n - 0.8) / 0.2)) for i in range(n + 1)]
        self.hull = LF.Loft.along_x(stations).with_stations(cuts)
        self.bow_sec = astra_sec(self.W * LF.profile(1.0, wp), self.H * LF.profile(1.0, hp))
        self.stern_sec = astra_sec(self.W * LF.profile(0.0, wp), self.H * LF.profile(0.0, hp))
        self.bow_zo = -self.H * 0.15
        self.plates: list[LF.Plate] = []
        self.rib_x = [float(x) for x in np.arange(-340.0, 381.0, 60.0) if all(abs(x - xc) > 12 for xc in cuts)]
        self.deck_fields = [(292.0, 320.0, 0.20, 0.80), (364.0, 388.0, 0.12, 0.88)]     # flat fields on the bow deck: emblem, hull number
        self.g.keep_out((150.0, -16.0, self.ISLAND_TOP + 0.2), (215.0, 16.0, 90.0))       # nothing rises in front of the bridge window

    # ----------------------------------------------------------------------------------------------------- hull
    def flank(self, z: LF.Zone, voids) -> list:
        return flank_plating(self.c, self.st, z, voids, self.cuts, (self.X_ST + 8.0, self.X_BW - 40.0), self.NAME_SPAN)

    def plate_hull(self) -> None:
        c, g, rng = self.c, self.g, self.rng
        voids = [(x - 0.9, x + 0.9) for x in self.rib_x]
        for z in self.hull.zones():
            z.skin(g, c.m("Frame"))
        fields = self.deck_fields
        for k in range(8):
            z = self.hull.zone(k)
            if k in (2, 6):
                pl = self.flank(z, voids)
            elif k == 4:
                pl = LF.plate_zone(g, z, rng, self.st.scheme, PRE, voids=voids,
                                   skip=lambda x0, x1, w0, w1: any(x1 > f[0] and x0 < f[1] and w1 > f[2] and w0 < f[3] for f in fields))
                for f in fields:
                    flat_field(c, z, f[0] + 0.5, f[1] - 0.5, f[2], f[3], "Plate", 0.4)
            else:
                dark = -0.10 if k in (0, 1, 7) else 0.0
                pl = LF.plate_zone(g, z, rng, self.st.scheme, PRE, tone_fn=lambda a, w, d=dark: d, voids=voids)
            self.plates += pl
        H.ribs(c, self.hull, self.rib_x, 1.8, 1.25)

    # ---------------------------------------------------------------------------------------------- upper deck
    def upper_deck(self) -> None:
        c, g, rng = self.c, self.g, self.rng
        L = self.L
        up0, up1 = -L * 0.42, L * 0.17
        uw, uh = self.W * 0.6, 9.0
        un = max(6, int((up1 - up0) / 16))
        zo = self.H * 0.92 + uh - 1.0
        prof = [(0, 0.85), (0.15, 1.0), (0.85, 1.0), (1.0, 0.7)]
        stations = [(up0 + (i / un) * (up1 - up0), LF.chamfer_rect(uw * LF.profile(i / un, prof), uh, 0.35, top=0.8), zo) for i in range(un + 1)]
        deck = LF.Loft.along_x(stations).with_stations(self.cuts)
        self.deck = deck
        self.deck_top = zo + uh
        voids = [(-150 - 15, -150 + 15), (-240 - 15, -240 + 15), (-20 - 11, -20 + 11)]        # the aft turrets' mounts and the missile banks
        for k in range(2, 7):
            z = deck.zone(k)
            z.skin(g, c.m("Frame"))
            self.plates += LF.plate_zone(g, z, rng, self.st.scheme, PRE, voids=voids if k == 4 else ())
        # the forward end of the upper deck stands free of the island: close it
        H.end_face(c, np.array(stations[-1][1]), up1, 1.0, self.st, zo=zo)

    # ------------------------------------------------------------------------------------------------ island
    def island(self) -> None:
        """The tower that carries the bridge: same footprints and heights as v2 (the bridge floor is at z 62, the top at 60.4)."""
        c, g, rng = self.c, self.g, self.rng
        ib = self.H * 1.0 * 0.9
        top = self.ISLAND_TOP
        sch = replace(self.st.scheme, row_w=(2.6, 4.2), plate_len=(6.0, 16.0), levels=(0.4,), level_weights=(1.0,), wedge=0.0, chamfer=0.08, rim=0.2, min_len=3.0)
        loftA = LF.Loft([ib, top], [ring_rect(112.0, 212.0, 19.0, ib, 0.18 * 38.0), ring_rect(152.0, 184.0, 11.5, top, 0.18 * 23.0)])
        loftB = LF.Loft([ib, ib + 22.0], [ring_rect(96.0, 150.0, 15.0, ib, 0.2 * 30.0), ring_rect(118.0, 150.0, 10.0, ib + 22.0, 0.2 * 20.0)])
        self.island_lofts = (loftA, loftB)
        for loft, cap in ((loftA, True), (loftB, True)):
            for z in loft.zones():
                z.skin(g, c.m("Frame"))
                self.plates += LF.plate_tower(g, z, rng, sch, PRE)
            if cap:
                ring = loft.R[-1]
                cen = ring.mean(axis=0)
                V = np.vstack([ring, cen])
                k = len(ring)
                F = np.stack([np.arange(k), (np.arange(k) + 1) % k, np.full(k, k)], axis=1)
                a_, b_, c_ = V[F[:, 0]], V[F[:, 1]], V[F[:, 2]]
                if np.sum(np.cross(b_ - a_, c_ - a_)[:, 2]) < 0:
                    F = F[:, [0, 2, 1]]
                g.add(V, F, c.m("Frame"), a1=(0.0, 0.5), kind="skin")
        # decks of lit windows on the tower's long sides and its raked front
        for z in (loftA.zone(0), loftA.zone(4)):
            for zz in np.arange(ib + 5.0, top - 4.0, 6.5):
                K2.window_row(c, z, float(zz), 0.10, 0.90, lift=0.5)
        z = loftA.zone(2)
        for zz in np.arange(ib + 6.0, top - 12.0, 7.0):
            K2.window_row(c, z, float(zz), 0.15, 0.85, lift=0.5)
        # the sensor tower on the forward base
        for zone in (loftB.zone(0), loftB.zone(4)):
            for zz in np.arange(ib + 4.0, ib + 19.0, 6.0):
                K2.window_row(c, zone, float(zz), 0.12, 0.88, lift=0.5, win=(1.1, 0.7))

    # ------------------------------------------------------------------------------------------ keel and spine
    def keel_and_spine(self) -> None:
        c, g, rng = self.c, self.g, self.rng
        x0, x1 = self.X_ST + 40.0, 132.6
        sch = replace(self.st.scheme, row_w=(3.0, 5.5), plate_len=(12, 40), levels=(0.4, 0.6), level_weights=(0.6, 0.4), mats=(("Frame", 0.85), ("Plate", 0.15)))
        st = [(x, LF.chamfer_rect(22.5 - (x - x0) / (x1 - x0) * 7.5, 4.0 - (x - x0) / (x1 - x0), 0.35), -25.3 + (x - x0) / (x1 - x0) * 0.5)
              for x in np.linspace(x0, x1, 9)]
        keel = LF.Loft.along_x(st).with_stations(self.cuts)
        self.keel = keel
        for k in (0, 1, 2, 6, 7):
            z = keel.zone(k)
            z.skin(g, c.m("Frame"))
            self.plates += LF.plate_zone(g, z, rng, sch, PRE, tone_fn=lambda a, w: -0.12)
        # the dorsal spine, interrupted where the aft turrets stand
        sp = replace(self.st.scheme, row_w=(2.0, 3.6), plate_len=(8, 26), levels=(0.35, 0.5), level_weights=(0.6, 0.4))
        self.spines = []
        for a0, a1 in ((-306.0, -258.0), (-222.0, -174.0), (-128.0, -40.0), (-4.0, 92.0)):
            zsp = self.deck_top + 2.2
            stations = [(x, LF.chamfer_rect(9.6 - (x + 306) / 400 * 1.8, 3.0, 0.4), zsp) for x in np.linspace(a0, a1, 4)]
            spine = LF.Loft.along_x(stations).with_stations(self.cuts)
            self.spines.append(spine)
            for k in (2, 3, 4, 5, 6):
                z = spine.zone(k)
                z.skin(g, c.m("Frame"))
                self.plates += LF.plate_zone(g, z, rng, sp, PRE)

    # ---------------------------------------------------------------------------------------- bow, stern, drive
    def ends(self) -> None:
        """The bow face with its two launch-tube mouths (open: the hangar's own tubes are seen through them) and the stern face."""
        c = self.c
        holes = [(y - 13.3, y + 13.3, -4.32 - 6.8, -4.32 + 6.8) for y in (14.9, -14.9)]
        H.end_face(c, np.array(self.bow_sec), self.X_BW, 1.0, self.st, holes=holes, zo=self.bow_zo)
        for sy in (-1, 1):
            K2.hangar_mouth(c, Xf((self.X_BW, sy * 14.9, -4.32), I3, 1.0), 26.0, 13.0, 8.0)
        H.end_face(c, np.array(self.stern_sec), self.X_ST, -1.0, self.st)

    def engines(self) -> None:
        """The thrust structure behind the stern face and its six drive bells (3 x 2), thruster quads at the corners."""
        c, g, rng = self.c, self.g, self.rng
        sec = LF.chamfer_rect(40.0, 22.8, 0.3)
        blk = LF.Loft.along_x([(x, sec, 0.0) for x in (-388.0, -374.0, -360.0)])
        sch = replace(self.st.scheme, row_w=(3.0, 5.0), plate_len=(8, 20), levels=(0.5, 0.8), level_weights=(0.6, 0.4), mats=(("Frame", 0.8), ("Plate", 0.2)))
        for z in blk.zones():
            z.skin(g, c.m("Frame"))
            self.plates += LF.plate_zone(g, z, rng, sch, PRE)
        H.end_face(c, np.array(sec), -388.0, -1.0, self.st)
        K2.engine_bank(c, -388.0, [-21.0, 0.0, 21.0], [-10.5, 10.5], 9.0)
        for sy in (-1, 1):
            for sz in (-1, 1):
                fr = G.frame_z((0.0, sy, 0.0), (0.0, 0.0, 1.0))
                K2.thruster_cluster(c, Xf((-372.0, sy * 41.5, sz * 17.0), fr, 1.0), 0.9)

    # ------------------------------------------------------------------------------------------------ weapons
    def weapons(self) -> None:
        """4 twin railgun turrets, 12 laser batteries, 2 VLS banks, 2 torpedo tubes, 24 point-defence mounts (docs/BIBBIA.md §6)."""
        c, g = self.c, self.g
        hull = self.hull
        for x, where in ((275.0, "hull"), (335.0, "hull"), (-150.0, "deck"), (-240.0, "deck")):
            z0 = (top_z(hull, x) if where == "hull" else self.deck_top) + 0.3
            K.railgun_turret(c, Xf((x, 0.0, z0), I3, 1.5), barrels=2, elev=8.0)
            g.keep_out((x - 12, -12, z0 - 1), (x + 12, 12, z0 + 10))
        for sy in (-1, 1):
            z0 = self.deck_top + 0.4
            K.vls_bank(c, Xf((-20.0, sy * 16.0, z0), I3, 1.0), 6, 4, 3.2)
            g.keep_out((-32, sy * 16 - 8, z0 - 1), (-8, sy * 16 + 8, z0 + 3))
        lasers = {3: [-290, -200, -60, 60, 170, 300], 5: [-250, -160, 0, 110, 250, 340]}
        for k, xs in lasers.items():
            zone = hull.zone(k)
            for x in xs:
                P, R = on_zone(zone, float(x), 0.5, 0.5)
                K.laser_battery(c, Xf(P, R, 1.0))
                g.keep_out(P - 5, P + 5)
        xs = [x for x in np.arange(-330.0, 381.0, 30.0) if all(abs(x - xc) > 10 for xc in self.cuts)]
        for i, x in enumerate(xs):
            k = 3 if i % 2 == 0 else 5
            P, R = on_zone(hull.zone(k), float(x), 0.86, 0.5)
            K.pd_mount(c, Xf(P, R, 1.0))
            g.keep_out(P - 3, P + 3)
        for k in (2, 6):
            P, N, _ = hull.zone(k).frame(np.array([352.0]), np.array([0.3]))
            torpedo_tube(c, Xf(P[0] + N[0] * 0.4, G.frame_x(N[0], (0.0, 0.0, 1.0)), 1.0))
            g.keep_out(P[0] - 6, P[0] + 6)

    # ---------------------------------------------------------------------------------------------- radiators
    def radiators(self) -> None:
        """Folding radiator wings on the shoulders: three panels of 70 m per side, half open."""
        c = self.c
        for sy in (1, -1):
            for x0 in (-322.0, -252.0, -182.0):
                xf = Xf((x0, 45.0, 18.3), I3, 1.0) if sy > 0 else Xf((x0 + 66.0, -45.0, 18.3), Xf().rot_z(180.0), 1.0)
                K2.radiator_wing(c, xf, 66.0, 30.0, 35.0)
                lo = (x0, 40.0, 0.0) if sy > 0 else (x0, -80.0, 0.0)
                hi = (x0 + 66.0, 80.0, 90.0) if sy > 0 else (x0 + 66.0, -40.0, 90.0)
                self.g.keep_out(lo, hi)

    # ---------------------------------------------------------------------------------------------------- belly
    def belly(self) -> None:
        """What hangs under the ship: cargo doors and sensor drums on the flat keel, tow hardpoints, point-defence mounts looking down.
        Nothing crosses a cut plane (the pieces must stay clean) and nothing goes above the hull's bottom face."""
        c, g, rng = self.c, self.g, self.rng
        hull, keel = self.hull, self.keel
        ok = lambda x, half: all(abs(x - xc) > half + 6.0 for xc in self.cuts)                      # noqa: E731
        for zone, x, w in ((keel.zone(0), -290.0, 0.5), (keel.zone(0), -205.0, 0.5), (keel.zone(0), -40.0, 0.5), (keel.zone(0), 60.0, 0.5),
                           (hull.zone(0), 170.0, 0.5), (hull.zone(0), 318.0, 0.5)):
            if not ok(x, 13.0):
                continue
            P, R = on_zone(zone, x, w, 0.0)
            K2.cargo_door(c, Xf(P, R, 1.0), 26.0, 14.0)
            g.keep_out(P - np.array([16.0, 9.0, 8.0]), P + np.array([16.0, 9.0, 8.0]))
        for zone, x, w in ((hull.zone(0), 240.0 + 0.0, 0.5), (hull.zone(0), 360.0, 0.5), (keel.zone(0), -120.0, 0.5)):
            if not ok(x, 4.0):
                continue
            P, R = on_zone(zone, x, w, 0.0)
            K2.sensor_cluster(c, Xf(P, R, 1.0), 3.4)
            g.keep_out(P - np.array([5.0, 5.0, 5.0]), P + np.array([5.0, 5.0, 5.0]))
        for zone, xs, ws in ((hull.zone(0), (150.0, 290.0, 345.0), (0.10, 0.90)), (keel.zone(0), (-320.0, -240.0, -160.0, -80.0, 0.0, 100.0), (0.15, 0.85))):
            for x in xs:
                for w in ws:
                    if not ok(x, 4.0):
                        continue
                    P, R = on_zone(zone, x, w, 0.0)
                    if rng.random() < 0.6:                                                        # most places get a lug, some a point-defence mount
                        K2.tow_lug(c, Xf(P, R, 1.0))
                        g.keep_out(P - 3.0, P + 3.0)
                    else:
                        K.pd_mount(c, Xf(P, R, 1.0))
                        g.keep_out(P - 3.0, P + 3.0)

    # ----------------------------------------------------------------------------------------------- antennas
    def antennas(self) -> None:
        c = self.c
        for x, y in ((-282.0, -14.0), (-200.0, 14.0), (-84.0, -14.0), (42.0, 14.0)):
            K2.antenna_farm(c, Xf((x, y, self.deck_top + 0.4), I3, 1.0), 12.0, 18.0, n=8)
            self.g.keep_out((x - 10, y - 7, self.deck_top), (x + 10, y + 7, self.deck_top + 15))
        K2.mast(c, Xf((136.0, 10.0, self.deck_top + 0.4), I3, 1.0), 14.0, dish=3.0, arms=3, beacon=True)

    # ------------------------------------------------------------------------------------------ running lights
    def lights(self) -> None:
        """Red to port, green to starboard, white aft, and the keel's pulsing red (docs/BIBBIA.md §6)."""
        c, hull = self.c, self.hull
        for k, col in ((3, K2.NAV_RED), (5, K2.NAV_GREEN)):
            P, N, _ = hull.zone(k).frame(np.array([372.0]), np.array([0.5]))
            K2.nav_light(c, P[0] + N[0] * 0.4, N[0], col, 1.6)
        for sy in (-1, 1):
            K2.nav_light(c, np.array([-390.0, sy * 34.0, 22.8]), np.array([-0.3, sy * 0.3, 0.9]), K2.NAV_WHITE, 1.6)
        K2.nav_light(c, np.array([0.0, 0.0, -29.4]), np.array([0.0, 0.0, -1.0]), K2.NAV_RED, 2.0, pulse=True)

    # -------------------------------------------------------------------------------------------- markings
    def markings(self) -> None:
        """CVC-01 in white on the navy band of both flanks, the ASTRA Navy emblem and the number on the bow deck."""
        c, g, hull = self.c, self.g, self.hull
        for k in (2, 6):
            P, N, _ = hull.zone(k).frame(np.array([322.0]), np.array([0.618]))
            TX.place_text(g, "CVC-01", P[0] + N[0] * 0.5, N[0], 3.0, c.m("Marking"), depth=0.06)
        zone = hull.zone(4)
        for a0, a1, w0, w1, what in ((292.0, 320.0, 0.20, 0.80, "emblem"), (364.0, 388.0, 0.12, 0.88, "number")):
            P, N, _ = zone.frame(np.array([0.5 * (a0 + a1)]), np.array([0.5 * (w0 + w1)]))
            base = P[0] + N[0] * 0.4
            if what == "emblem":
                TX.astra_emblem(g, base, N[0], 22.0, c.m("Marking"), up=(1.0, 0.0, 0.0), depth=0.08)
            else:
                TX.place_text(g, "CVC-01", base, N[0], 8.0, c.m("Marking"), up=(1.0, 0.0, 0.0), depth=0.08)

    # ------------------------------------------------------------------------------------- pieces (cut faces)
    def cap_extras(self, xc: float) -> list:
        """Other structures the cut plane passes through, as (section polygon, side, z limit): the parts outside the hull's own section."""
        ex = []
        top = top_z(self.hull, xc)
        bot = float(self.hull.ring_at(xc)[:, 2].min())
        for loft, side, lim in [(self.deck, 1, top)] + [(sp, 1, top) for sp in self.spines] + [(self.keel, -1, bot)]:
            if loft.a[0] + 1.0 < xc < loft.a[-1] - 1.0:
                ex.append((loft.ring_at(xc)[:, 1:3], side, lim))
        return ex

    def caps(self) -> list:
        return make_all_cuts(self.c, self.hull, self.cuts, extras_fn=self.cap_extras, depth=30.0)

    # ------------------------------------------------------------------------------------------------- build
    def build(self, details: bool = True) -> None:
        c = self.c
        self.plate_hull()
        self.upper_deck()
        self.island()
        self.keel_and_spine()
        self.ends()
        self.engines()
        if self.features:
            self.weapons()
            self.belly()
            self.radiators()
            self.antennas()
            self.lights()
            self.markings()
        if details:
            H.panelize_plates(c, self.plates, self.st)
            H.scatter_details(c, self.plates, self.st)
            H.rivet_plates(c, self.plates)


def torpedo_tube(c: Ctx, xf: Xf) -> None:
    """A torpedo tube in the hull flank (local x out of the hull): armoured ring, dark bore, a door swung open."""
    g, m = c.g, c.m
    xf.cyl(g, (-0.6, 0, 0), (1.3, 0, 0), 3.7, 3.5, m("Frame"), seg=24, ch=0.18, kind="torpedo")
    xf.cyl(g, (1.28, 0, 0), (1.34, 0, 0), 3.0, 3.0, m("Engine"), seg=24, kind="torpedo")
    for k in range(8):
        a = 2 * np.pi * k / 8
        xf.cyl(g, (1.3, 3.3 * np.cos(a), 3.3 * np.sin(a)), (1.55, 3.3 * np.cos(a), 3.3 * np.sin(a)), 0.16, 0.14, m("Frame"), seg=6, kind="torpedo")
    door = xf.sub((1.3, 0.0, 3.8), xf.rot_y(-70.0))
    door.box(g, (0, 0, -3.8), (0.35, 6.6, 6.8), m("Plate"), ch=0.08, kind="torpedo")


# The spaces built inside the Aquila's hull (data/ship/aquila_*.json, hull frame = world + (172, 0, 62)): nothing of the exterior may
# stand in them. (lo, hi) boxes in metres: the hangar with its two launch tubes, the bridge, the decks that have interiors.
INTERIORS = {
    "hangar": ((232.0, -28.0, -10.8), (377.0, 28.0, 9.2)),
    "tube_port": ((377.0, 1.9, -10.8), (390.0, 27.9, 2.2)),
    "tube_starboard": ((377.0, -27.9, -10.8), (390.0, -1.9, 2.2)),
    "bridge": ((163.5, -8.7, 62.0), (182.0, 8.7, 66.2)),
    "engineering": ((-158.0, -14.0, 4.0), (-116.0, 14.0, 18.0)),
    "medbay": ((-60.0, -9.0, 8.0), (-30.0, 9.0, 12.2)),
    "mess": ((50.0, -10.0, 16.0), (88.0, 10.0, 19.8)),
    "berths": ((-28.0, -3.6, 16.0), (-4.0, 3.6, 19.3)),
}


def aquila_checks(g: G.Geo) -> dict:
    """Vertices of the exterior standing inside an interior space (shrunk by 25 cm), and above the bridge: both must be zero."""
    V = np.concatenate([ch["V"] for ch in g.chunks if not ch["cap"]]).astype(np.float64)
    out = {"vertices": int(len(V))}
    for name, (lo, hi) in INTERIORS.items():
        lo_, hi_ = np.array(lo) + 0.25, np.array(hi) - 0.25
        inside = np.all((V > lo_) & (V < hi_), axis=1)
        out[f"inside_{name}"] = int(inside.sum())
    above = np.all((V > np.array([150.0, -16.0, 60.7])) & (V < np.array([215.0, 16.0, 200.0])), axis=1)
    out["above_island_top"] = int(above.sum())
    out["ok"] = all(v == 0 for k, v in out.items() if k.startswith("inside_") or k == "above_island_top")
    return out


def build_aquila(c: Ctx) -> dict:
    """shipgen3 entry: the whole Aquila, its cut faces, and the camera rigs of its previews."""
    a = Aquila(c)
    a.build()
    faces = a.caps()
    info = {"cuts": list(a.cuts), "cut_faces": faces, "length_m": 800.0, "checks": aquila_checks(c.g),
            "cam_az": -32.0, "cam_el": 18.0, "cam_dist": 1.9, "sun_az": -50.0, "sun_el": 26.0,
            "closeups": [{"name": "flank", "target": [60.0, -50.0, 3.0], "normal": [0.0, -1.0, 0.0], "distance": 110.0, "span": 50.0},
                         {"name": "bowdeck", "target": [285.0, 0.0, 24.0], "normal": [-0.35, -0.55, 0.75], "distance": 110.0, "span": 50.0},
                         {"name": "belly", "target": [-45.0, 0.0, -27.0], "normal": [0.2, -0.25, -0.95], "distance": 110.0, "span": 50.0, "key_el": -38.0}],
            "pieces_gap": 0.10, "pieces_az": 24.0, "pieces_dist": 2.4}
    return info
