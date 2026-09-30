"""Kharon Mandate ships v3 (docs/STILE.md §2): brutal, angular, asymmetric; thick basalt and graphite plates set at angles, oxidised
copper patches bolted on with pride, welded seams, exposed structure between the plates, blades raked forward, radiators that glow
orange, amber slits and a single red pulse for lights, engines orange-violet. "Survivor ships": patched, never pretty.

  Acheron   cruiser, ~520 m: heavy stern, a waist with the launch bays, armoured shoulders, two blades round the spinal rail gun
  Styx      destroyer, ~340 m: a long spear of a bow, swept armour sponsons with radiators at the stern
  Lethe     frigate, ~220 m: a compact armoured arrowhead
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
import ship3_panels as PN
import ship3_text as TX
from ship3_cut import make_all_cuts
from ship3_kit import Ctx, Xf

PRE = "MI_HULL_M_"
I3 = np.eye(3)
COPPER, VERD = "Livery", "Trim"


def mandate_style(scale: float = 1.0) -> H.HullStyle:
    """Thick angled plates, wide seams, strong tone swings; a few copper plates and verdigris access covers."""
    s = scale
    return H.HullStyle(
        scheme=LF.Scheme(row_w=(4.0 * s, 8.5 * s), plate_len=(9 * s, 34 * s), gap_a=(0.4, 0.9), gap_w=(0.5, 1.1), levels=(0.8, 1.2, 1.7),
                         level_weights=(0.35, 0.4, 0.25), wedge=0.3, shear=(3.0 * s, 2.0 * s), chamfer=0.16, rim=0.4, embed=0.5, tone_sigma=0.16,
                         mats=(("Plate", 0.90), ("Frame", 0.06), (COPPER, 0.04)), min_len=4.0),
        panels=PN.PanelStyle(min_size=(2.6, 1.8), max_size=(10.0, 6.0), seam=(0.10, 0.22), margin=0.3, lifts=(0.05, 0.10, 0.18),
                             lift_w=(0.4, 0.35, 0.25), chamfer=0.05, rim=0.1, p_stop=0.3, tone_sigma=0.06, p_alt=0.07),
        p_panels=0.35, detail_density=0.32,
        weights={"hatch": 2, "vent": 3, "blister": 0.6, "lamp": 0.8, "cable": 3, "stencil": 0.5},
        labels=("KHARON", "FERRY MARK 12", "NO STEP", "MAGAZINE", "REACTOR SHIELD", "REMEMBER THE SILENCE", "WE CARRY", "COOLANT"),
        stencil_height=0.4, alt_mats=("Frame", VERD))


def blade_ring(w: float, h: float, skew: float) -> list:
    return LF.blade(w, h, skew)


def patches(c: Ctx, plates, style: H.HullStyle, p: float = 0.16) -> int:
    """Copper and bronze doublers bolted over the plates, rivets round their edges, and welded beads along some seams."""
    g, rng, m = c.g, c.rng, c.m
    n = 0
    for pl in plates:
        if rng.random() > p * c.detail:
            continue
        la, lw = pl.size_m()
        if la < 4.0 or lw < 2.4:
            continue
        zone = pl.zone
        u0, v0 = rng.uniform(0.1, 0.45), rng.uniform(0.08, 0.4)
        du, dv = rng.uniform(0.25, 0.5), rng.uniform(0.3, 0.55)
        a0, a1 = pl.a0 + (pl.a1 - pl.a0) * u0, pl.a0 + (pl.a1 - pl.a0) * min(0.95, u0 + du)
        w0, w1 = pl.w0 + (pl.w1 - pl.w0) * v0, pl.w0 + (pl.w1 - pl.w0) * min(0.95, v0 + dv)
        if (a1 - a0) < 2.0 or (w1 - w0) * zone.sw(0.5 * (a0 + a1)) < 1.4:
            continue
        outline = np.array([[a0, w0], [a1, w0], [a1, w1], [a0, w1]])
        mat = m(COPPER) if rng.random() < 0.65 else m(VERD)
        lift = float(rng.uniform(0.10, 0.22))
        if not LF.slab(g, zone, outline, mat, pl.thick, lift, lift, 0.05, 0.16, 0.06, tone=float(np.clip(0.5 + rng.normal(0, 0.12), 0.1, 0.9)), kind="patch"):
            continue
        # rivets round the patch (5-sided studs every 0.7 m)
        sw = zone.sw(0.5 * (a0 + a1))
        per = 2 * ((a1 - a0) + (w1 - w0) * sw)
        k = max(6, int(per / 0.7))
        t = np.linspace(0.0, 1.0, k, endpoint=False)
        edge = []
        L1, L2 = (a1 - a0), (w1 - w0) * sw
        for tt in t:
            d = tt * (2 * L1 + 2 * L2)
            if d < L1:
                edge.append((a0 + d, w0 + 0.05 / sw))
            elif d < L1 + L2:
                edge.append((a1 - 0.05, w0 + (d - L1) / sw))
            elif d < 2 * L1 + L2:
                edge.append((a1 - (d - L1 - L2), w1 - 0.05 / sw))
            else:
                edge.append((a0 + 0.05, w1 - (d - 2 * L1 - L2) / sw))
        edge = np.array(edge)
        Pp, Nn, _ = zone.frame(edge[:, 0], edge[:, 1])
        base = pl.thick(edge[:, 0]) + lift
        g.cylinders(Pp + Nn * (base[:, None] - 0.02), Pp + Nn * (base[:, None] + 0.10), 0.075, m("Frame"), seg=5, kind="rivet")
        n += 1
    return n


def welds(c: Ctx, plates, p: float = 0.18) -> None:
    """A welded bead along one long edge of some plates (verdigris-stained bronze)."""
    g, rng, m = c.g, c.rng, c.m
    for pl in plates:
        if rng.random() > p * c.detail:
            continue
        la, lw = pl.size_m()
        if la < 6.0:
            continue
        w = pl.w0 + 0.03 if rng.random() < 0.5 else pl.w1 - 0.03
        A = np.linspace(pl.a0 + 0.5, pl.a1 - 0.5, max(3, int(la / 4.0)))
        P, N, _ = pl.zone.frame(A, np.full(len(A), w))
        top = pl.thick(A) + 0.05
        Q = P + N * top[:, None]
        for i in range(len(A) - 1):
            g.box_between(Q[i], Q[i + 1], 0.13, 0.10, m(VERD), chamfer=0.02, kind="weld")


def tally_marks(c: Ctx, zone, a: float, w: float, count: int, height: float = 1.4) -> None:
    """Painted tally strokes (each one a crossing of the river): groups of five, the fifth across the four."""
    g, m = c.g, c.m
    P0, N0, T0 = zone.frame(np.array([a]), np.array([w]))
    N, T = N0[0], T0[0]
    up = G.norm(np.cross(N, T))
    x = 0.0
    for i in range(count):
        if i % 5 == 4:
            p = P0[0] + N * 0.42 + T * (x - 2.0 * 0.32 - 0.16)
            g.box(p, (1.7, 0.10, 0.06), m("Marking"), frame=np.stack([T, up, N]), chamfer=0.0, kind="text")
            x += 0.55
        else:
            p = P0[0] + N * 0.42 + T * x
            g.box(p, (0.10, height, 0.06), m("Marking"), frame=np.stack([T, up, N]), chamfer=0.0, kind="text")
            x += 0.32


# ==================================================================================================================== ships
class MandateShip:
    """A Mandate ship from a spec: a lofted body in blade sections, blades, sponsons, armour slabs, tower, spinal gun, radiators..."""

    def __init__(self, c: Ctx, spec: dict):
        self.c, self.g, self.rng, self.sp = c, c.g, c.rng, spec
        self.cuts = list(spec["cuts"])
        self.g.cuts = list(self.cuts)
        self.s = spec["scale"]
        self.st = mandate_style(self.s)
        self.plates: list[LF.Plate] = []
        b = spec["body"]
        n = max(8, int((b["x1"] - b["x0"]) / (14 * self.s)))
        st = []
        for i in range(n + 1):
            t = i / n
            st.append((b["x0"] + t * (b["x1"] - b["x0"]), LF.blade(b["W"] * LF.profile(t, b["wp"]), b["H"] * LF.profile(t, b["hp"]), b["skew"]),
                       b["H"] * LF.profile(t, b["zp"])))
        self.hull = LF.Loft.along_x(st).with_stations(self.cuts)
        self.b = b

    def wat(self, x: float) -> float:
        b = self.b
        return b["W"] * LF.profile((x - b["x0"]) / (b["x1"] - b["x0"]), b["wp"])

    def hat(self, x: float) -> float:
        b = self.b
        return b["H"] * LF.profile((x - b["x0"]) / (b["x1"] - b["x0"]), b["hp"])

    def zat(self, x: float) -> float:
        b = self.b
        return b["H"] * LF.profile((x - b["x0"]) / (b["x1"] - b["x0"]), b["zp"])

    # ---------------------------------------------------------------------------------------------- body
    def plate_loft(self, loft: LF.Loft, scheme=None, zones=range(8), voids=()) -> list:
        c, g, rng = self.c, self.g, self.rng
        out = []
        for k in zones:
            z = loft.zone(k)
            z.skin(g, c.m("Frame"))
            out += LF.plate_zone(g, z, rng, scheme or self.st.scheme, PRE, voids=voids)
        return out

    def body(self) -> None:
        sp = self.sp
        self.plates += self.plate_loft(self.hull)
        b = self.b
        H.end_face(self.c, np.array(LF.blade(b["W"] * LF.profile(0.0, b["wp"]), b["H"] * LF.profile(0.0, b["hp"]), b["skew"])), b["x0"], -1.0, self.st,
                   zo=self.zat(b["x0"]))
        if sp.get("body_bow_cap", True):
            H.end_face(self.c, np.array(LF.blade(b["W"] * LF.profile(1.0, b["wp"]), b["H"] * LF.profile(1.0, b["hp"]), b["skew"])), b["x1"], 1.0, self.st,
                       zo=self.zat(b["x1"]))

    def slab_loft(self, x0: float, x1: float, yc: float, w0: float, w1: float, h0: float, h1: float, zc: float, scheme=None, nst: int = 4) -> LF.Loft:
        """An armour slab: a chamfered box lofted between two sections, centred at y = yc."""
        st = []
        for x in np.linspace(x0, x1, nst):
            t = (x - x0) / max(1e-9, x1 - x0)
            sec = np.array(LF.chamfer_rect(w0 + (w1 - w0) * t, h0 + (h1 - h0) * t, 0.4))
            sec[:, 0] += yc
            st.append((x, sec, zc))
        loft = LF.Loft.along_x(st).with_stations(self.cuts)
        self.plates += self.plate_loft(loft, scheme)
        return loft

    def blades(self) -> None:
        d = self.sp.get("blades")
        if not d:
            return
        c, g, rng, s = self.c, self.g, self.rng, self.s
        sch = replace(self.st.scheme, row_w=(3.0 * s, 6.0 * s), plate_len=(8 * s, 24 * s), shear=(2.0 * s, 1.5 * s))
        for side in (-1, 1):
            st = []
            m = 12
            for i in range(m + 1):
                t = i / m
                x = d["x0"] + t * (d["x1"] - d["x0"])
                w = d["w"] * LF.profile(t, [(0, 1.0), (0.55, 0.85), (1.0, 0.16)])
                h = d["h"] * LF.profile(t, [(0, 1.0), (0.7, 0.7), (1.0, 0.2)])
                sec = np.array(LF.blade(w, h, 0.25 * side))
                sec[:, 0] += side * (d["gap"] + w)
                st.append((x, sec, d["z"] + d["lift"] * t * t))
            loft = LF.Loft.along_x(st).with_stations(self.cuts)
            self.plates += self.plate_loft(loft, sch)
            if side > 0:
                K2.nav_light(c, np.array([d["x1"] - 2.0 * s, side * (d["gap"] + d["w"] * 0.2), d["z"] + d["lift"] + 4.0 * s]), np.array([0.6, side * 0.4, 0.5]),
                             K2.NAV_RED, 1.4 * s, pulse=True)
        # the spinal gun between them: rails, accelerator rings, muzzle
        if d.get("spinal"):
            sg = d["spinal"]
            zc = sg["z"]
            x0, x1, r = sg["x0"], sg["x1"], sg["r"]
            g.cylinder((x0, 0, zc), (x1, 0, zc + sg.get("rise", 0.0)), r, r * 0.92, c.m("Frame"), seg=18, kind="spinal")
            k = sg["rings"]
            for i in range(k):
                x = x0 + (i + 0.5) * (x1 - x0 - 12 * s) / k
                z = zc + sg.get("rise", 0.0) * (x - x0) / (x1 - x0)
                g.revolve([(r * 1.05, 0.0), (r * 1.7, 0.0), (r * 1.7, 3.0 * s), (r * 1.05, 3.0 * s), (r * 1.05, 0.0)], c.m(COPPER if i % 2 else "Engine"),
                          origin=(x, 0, z), frame=G.frame_z((1.0, 0.0, 0.0), (0.0, 0.0, 1.0)), seg=22, wear=0.7, kind="spinal")
            g.cylinder((x1 - 10 * s, 0, zc + sg.get("rise", 0.0)), (x1 - 2 * s, 0, zc + sg.get("rise", 0.0) + 0.2), r * 1.45, r * 1.2, c.m("Engine"), seg=18, chamfer=0.2, kind="spinal")
            g.cylinder((x1 - 2.2 * s, 0, zc + sg.get("rise", 0.0)), (x1 - 1.8 * s, 0, zc + sg.get("rise", 0.0)), r * 0.7, r * 0.7, c.m("Glow"), seg=16, kind="spinal")

    def tower(self) -> None:
        d = self.sp.get("tower")
        if not d:
            return
        c, g, rng, s = self.c, self.g, self.rng, self.s
        z = d["z"]
        levels = d["levels"]                                    # [(x0, x1, hy, height, dy)] bottom to top; each narrower
        sch = replace(self.st.scheme, row_w=(3.0 * s, 5.0 * s), plate_len=(6 * s, 14 * s), levels=(0.6, 0.9), level_weights=(0.5, 0.5), wedge=0.0, shear=(0.0, 0.0), min_len=3.0)
        ztop = z
        for (x0, x1, hy, h, dy, tx0, tx1, thy) in levels:
            loft = LF.Loft([ztop, ztop + h], [self.ring(x0, x1, hy, ztop, dy, 0.28), self.ring(tx0, tx1, thy, ztop + h, dy, 0.32)])
            for zz in loft.zones():
                zz.skin(g, c.m("Frame"))
                self.plates += LF.plate_tower(g, zz, rng, sch, PRE)
            ring = loft.R[-1]
            cen = ring.mean(axis=0)
            V = np.vstack([ring, cen])
            kk = len(ring)
            F = np.stack([np.arange(kk), (np.arange(kk) + 1) % kk, np.full(kk, kk)], axis=1)
            if np.sum(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])[:, 2]) < 0:
                F = F[:, [0, 2, 1]]
            g.add(V, F, c.m("Frame"), a1=(0.0, 0.6), kind="skin")
            # amber slits
            for zone in (loft.zone(0), loft.zone(4)):
                Pz, Nz, _ = zone.frame(np.array([ztop + 0.5 * h]), np.array([0.5]))
                g.boxes(Pz + Nz * 0.4, (0.5 * (x1 - x0) * 0.5, 0.28, 0.06), c.m("Lights"), frames=G.frames_z(Nz, (1.0, 0.0, 0.0)),
                        chamfer=0.0, kind="window", aux=float(rng.random() * 0.6))
            ztop += h
        top = ztop
        mx = d.get("mast_x", 0.0)
        K2.mast(c, Xf((mx, d["levels"][-1][4], top), I3, 1.0), 24.0 * s, dish=4.5 * s, arms=3, beacon=False)
        K2.mast(c, Xf((mx + 10 * s, d["levels"][-1][4] + 3 * s, top - 1.0), I3, 1.0), 13.0 * s, dish=4.5 * s, arms=2, beacon=False)
        K2.nav_light(c, np.array([mx, d["levels"][-1][4], top + 24.0 * s]), np.array([0.0, 0.0, 1.0]), K2.NAV_RED, 1.4 * s, pulse=True)

    @staticmethod
    def ring(x0, x1, hy, z, dy, c):
        cc = c * min(x1 - x0, 2 * hy)
        pts = [(x0 + cc, -hy), (x1 - cc, -hy), (x1, -hy + cc), (x1, hy - cc), (x1 - cc, hy), (x0 + cc, hy), (x0, hy - cc), (x0, -hy + cc)]
        return np.array([(x, y + dy, z) for x, y in pts])

    # ------------------------------------------------------------------------------------------------ parts
    def radiators(self) -> None:
        """Rows of raked fins glowing orange with the ship's heat (the Radiator slot is emissive on Mandate ships)."""
        c, g, s = self.c, self.g, self.s
        for x0, x1, y, z, ht, n, rake in self.sp.get("radiators", []):
            step = (x1 - x0) / max(1, n - 1)
            for k in range(n):
                x = x0 + k * step
                g.box((x + rake * ht / 2, y, z + ht / 2), (0.9 * s, max(1.0, ht * 0.6), ht), c.m("Radiator"), chamfer=0.05, kind="radiator")
                if k % 3 == 0:
                    g.box((x + rake * ht / 2, y, z + ht + 0.3), (1.3 * s, max(1.0, ht * 0.6) + 0.6, 0.5), c.m("Frame"), chamfer=0.04, kind="radiator")
            g.box(((x0 + x1) / 2, y, z - 0.4), (x1 - x0 + 3.0, max(1.0, ht * 0.6) + 1.2, 0.8), c.m("Frame"), chamfer=0.06, kind="radiator")

    def weapons(self) -> None:
        c, g, s = self.c, self.g, self.s
        sp = self.sp
        for x, y, z, sc, nb, up in sp.get("turrets", []):
            xf = Xf((x, y, z), I3 if up else np.array([[1.0, 0.0, 0.0], [0.0, -1.0, 0.0], [0.0, 0.0, -1.0]]), sc)
            K.railgun_turret(c, xf, barrels=nb, elev=6.0 if up else -6.0, style="mandate")
            g.keep_out((x - 9 * sc, y - 9 * sc, z - 12 * sc if not up else z - 1), (x + 9 * sc, y + 9 * sc, z + 12 * sc if up else z + 10 * sc))
        for x, y, z, cols, rows in sp.get("vls", []):
            K.vls_bank(c, Xf((x, y, z), I3, 1.0), cols, rows, 3.0 * s, open_frac=0.10)
            g.keep_out((x - cols * 1.6 * s, y - rows * 1.6 * s, z - 1), (x + cols * 1.6 * s, y + rows * 1.6 * s, z + 3))
        for x, y, z in sp.get("pd", []):
            K.pd_mount(c, Xf((x, y, z), I3, 0.8 * s), style="mandate")
            g.keep_out((x - 3, y - 3, z - 1), (x + 3, y + 3, z + 4))

    def hangars(self) -> None:
        c, s = self.c, self.s
        for x, y, z, w, h, side in self.sp.get("hangars", []):
            fr = G.frame_x((0.0, side, 0.0), (0.0, 0.0, 1.0))
            K2.hangar_mouth(c, Xf((x, y, z), fr, 1.0), w, h, 12.0 * s)
            self.g.keep_out((x - w / 2 - 4, y - 8, z - h / 2 - 4), (x + w / 2 + 4, y + 8, z + h / 2 + 4))

    def engines(self) -> None:
        c, g, rng = self.c, self.g, self.rng
        e = self.sp["engines"]
        b = self.b
        sec = LF.blade(e["w"], e["h"], 0.0)
        xa, xb = b["x0"] - e["len"], b["x0"]
        blk = LF.Loft.along_x([(x, sec, self.zat(b["x0"]) + e.get("dz", 0.0)) for x in (xa, 0.5 * (xa + xb), xb)])
        sch = replace(self.st.scheme, row_w=(3.0, 5.0), plate_len=(8, 20), levels=(0.7, 1.0), level_weights=(0.6, 0.4), mats=(("Frame", 0.8), ("Plate", 0.2)))
        self.plates += self.plate_loft(blk, sch)
        H.end_face(c, np.array(sec), xa, -1.0, self.st, zo=self.zat(b["x0"]) + e.get("dz", 0.0), plate=False)
        for R, ys, zs in e["banks"]:
            K2.engine_bank(c, xa, ys, [z + self.zat(b["x0"]) + e.get("dz", 0.0) for z in zs], R, style="mandate")

    def lights(self) -> None:
        """A Mandate ship runs dark: one pulsing red light (amber slits are on the tower and the waist)."""
        pass

    def markings(self) -> None:
        c, g, sp = self.c, self.g, self.sp
        m = sp.get("marks")
        if not m:
            return
        for k in (2, 6):
            zone = self.hull.zone(k)
            P, N, _ = zone.frame(np.array([m["x"]]), np.array([0.5]))
            TX.mandate_mark(g, P[0] + N[0] * 0.5, N[0], m["d"], c.m("Marking"))
            tally_marks(c, zone, m["x"] - m["d"] * 1.5, 0.52, m.get("tally", 12), height=m["d"] * 0.16)
        z4 = self.hull.zone(4)
        if m.get("deck_name"):
            P, N, _ = z4.frame(np.array([m["deck_x"]]), np.array([0.5]))
            TX.place_text(g, m["deck_name"], P[0] + N[0] * 0.8, N[0], m["d"] * 0.8, c.m("Marking"), up=(1.0, 0.0, 0.0), depth=0.08)

    def caps(self) -> list:
        return make_all_cuts(self.c, self.hull, self.cuts, extras_fn=None, depth=self.sp.get("cap_depth", 26.0), scale=self.sp.get("cap_scale", 1.0))

    def flank_armour(self, x0: float, x1: float, seed_mat=(("Plate", 0.6), ("Frame", 0.2), (COPPER, 0.2))) -> None:
        """Armour slabs bolted along both flanks between x0 and x1 (v2's shoulders, thicker and plated)."""
        rng, s = self.rng, self.s
        for side in (-1, 1):
            x = x0
            while x < x1:
                ln = rng.uniform(30, 56) * s
                xm = min(x + ln, x1)
                if any(x < xc < xm for xc in self.cuts):
                    xm = min(xm, next(xc for xc in sorted(self.cuts, reverse=True) if x < xc < xm) - 0.5)
                if xm - x < 8.0:
                    x = xm + 6.0
                    continue
                xmid = 0.5 * (x + xm)
                w, hh = self.wat(xmid), self.hat(xmid) * rng.uniform(0.5, 0.75)
                zc = self.zat(xmid) + rng.uniform(-0.3, 0.05) * self.hat(x)
                sch = replace(self.st.scheme, mats=seed_mat, row_w=(2.5 * s, 5.0 * s), plate_len=(6 * s, 18 * s), levels=(0.6, 0.9), level_weights=(0.5, 0.5))
                self.slab_loft(x, xm, side * (w + 3.4 * s), 1.6 * s, 1.6 * s, hh, hh * 0.85, zc, sch)
                x = xm + rng.uniform(5, 14) * s

    def keel(self, x0: float, x1: float, depth: float, h0: float = 0.4, h1: float = 0.25) -> None:
        """A ventral blade keel, deepest amidships (two lofts meeting at the deepest point)."""
        s = self.s
        b = self.b
        xm = 0.5 * (x0 + x1)
        zb = self.zat(xm) - self.hat(xm) * 0.95
        self.slab_loft(x0, xm, 0.0, 2.2 * s, 2.6 * s, depth * h0, depth, zb - depth * 0.55, nst=3)
        self.slab_loft(xm, x1, 0.0, 2.6 * s, 1.4 * s, depth, depth * h1, zb - depth * 0.55, nst=3)

    def build(self, details: bool = True) -> None:
        self.body()
        self.blades()
        for fn in self.sp.get("extra", []):
            fn(self)
        self.tower()
        self.engines()
        self.radiators()
        self.weapons()
        self.hangars()
        self.markings()
        if details:
            H.panelize_plates(self.c, self.plates, self.st)
            H.scatter_details(self.c, self.plates, self.st)
            patches(self.c, self.plates, self.st)
            welds(self.c, self.plates)


# ==================================================================================================================== specs
def top_at(ship: MandateShip, x: float, y: float) -> float:
    """The z of the hull's upper surface at (x, y), from the section polygon there."""
    import ship3_cut as CT
    ex = CT.slice_extent(ship.hull.ring_at(x)[:, 1:3], 0, y - 0.05, y + 0.05)
    return ex[1] if ex else float(ship.hull.ring_at(x)[:, 2].max())


def acheron_spec() -> dict:
    s = 520.0 / 460.0
    L = 520.0
    W, H = 38 * s, 30 * s
    x_st, x_fr = -L / 2, L * 0.22
    body = dict(x0=x_st, x1=x_fr, W=W, H=H, skew=-0.1, wp=[(0.0, 0.95), (0.22, 1.0), (0.3, 0.74), (0.52, 0.74), (0.6, 1.06), (0.9, 1.0), (1.0, 0.86)],
                hp=[(0.0, 1.0), (0.22, 1.0), (0.3, 0.78), (0.52, 0.8), (0.62, 1.0), (1.0, 0.76)], zp=[(0.0, 0.0), (0.8, 0.0), (1.0, 0.1)])
    return dict(scale=s, L=L, cuts=(95.0, -168.0), body=body, cap_depth=30.0, cap_scale=1.13,
                blades=dict(x0=x_fr - 8 * s, x1=L / 2, w=14 * s, h=21 * s, gap=12 * s, z=H * 0.1, lift=9 * s,
                            spinal=dict(x0=x_fr - 10 * s, x1=L / 2 - 10 * s, r=3.4 * s, z=H * 0.2, rise=4 * s, rings=7)),
                engines=dict(len=34 * s, w=W * 1.02, h=H * 1.05, dz=0.0,
                             banks=[(min(W, H) * 0.34, [-W * 0.62, 0.0, W * 0.62], [-H * 0.12]), (min(W, H) * 0.17, [-W * 0.45, W * 0.45], [H * 0.62])]),
                marks=dict(x=46.0, d=9.0, tally=12, deck_x=-120.0, deck_name="KHARON"))


def styx_spec() -> dict:
    s = 340.0 / 260.0
    L = 340.0
    W, H = 20 * s, 17 * s
    x_st, x_fr = -L / 2, L * 0.12
    body = dict(x0=x_st, x1=x_fr, W=W, H=H, skew=0.12, wp=[(0.0, 0.9), (0.2, 1.0), (0.7, 0.95), (1.0, 0.7)], hp=[(0.0, 1.0), (0.6, 0.95), (1.0, 0.7)],
                zp=[(0.0, 0.0), (1.0, 0.05)])
    return dict(scale=s, L=L, cuts=(30.0, -78.0), body=body, cap_depth=22.0, cap_scale=0.8,
                engines=dict(len=20 * s, w=W * 0.96, h=H * 1.0, banks=[(min(W, H) * 0.34, [-W * 0.31, W * 0.31], [0.0])]),
                marks=dict(x=-20.0, d=6.0, tally=9))


def lethe_spec() -> dict:
    s = 220.0 / 160.0
    L = 220.0
    W, H = 22 * s, 11 * s
    x_st, x_fr = -L / 2 + 10 * s, L / 2
    body = dict(x0=x_st, x1=x_fr, W=W, H=H, skew=0.15, wp=[(0.0, 0.85), (0.25, 1.0), (0.55, 0.8), (0.85, 0.4), (1.0, 0.06)],
                hp=[(0.0, 1.0), (0.4, 1.0), (0.85, 0.6), (1.0, 0.2)], zp=[(0.0, 0.0), (1.0, 0.25)])
    return dict(scale=s, L=L, cuts=(45.0, -46.0), body=body, cap_depth=16.0, cap_scale=0.55, body_bow_cap=False,
                engines=dict(len=14 * s, w=W * 0.7, h=H * 0.95, banks=[(min(W * 0.7, H) * 0.34, [-W * 0.22, W * 0.22], [0.0])]),
                marks=dict(x=10.0, d=4.0, tally=7))


def _spear(ship: MandateShip) -> None:
    """The Styx's bow: a long spear of a blade section, a third of the ship, with the spinal rail's rings along its back."""
    c, g, s = ship.c, ship.g, ship.s
    x0, x1 = ship.b["x1"] - 6 * s, ship.sp["L"] / 2
    m = 12
    st = []
    W, H = ship.b["W"], ship.b["H"]
    for i in range(m + 1):
        t = i / m
        x = x0 + t * (x1 - x0)
        st.append((x, LF.blade(W * 0.7 * LF.profile(t, [(0, 1.0), (0.5, 0.6), (1.0, 0.1)]), H * 0.7 * LF.profile(t, [(0, 1.0), (0.7, 0.55), (1.0, 0.18)]), 0.12),
                   H * 0.05 + 4 * s * t))
    loft = LF.Loft.along_x(st).with_stations(ship.cuts)
    ship.plates += ship.plate_loft(loft, replace(ship.st.scheme, row_w=(3.0 * s, 5.5 * s), plate_len=(8 * s, 20 * s)))
    K2.nav_light(c, np.array([x1 - 1.0 * s, 0.0, H * 0.05 + 4 * s + H * 0.12]), np.array([0.7, 0.0, 0.7]), K2.NAV_RED, 1.4 * s, pulse=True)
    for k in range(6):
        t = 0.18 + 0.12 * k
        x = x0 + t * (x1 - x0)
        z = H * 0.05 + 4 * s * t + H * 0.7 * LF.profile(t, [(0, 1.0), (0.7, 0.55), (1.0, 0.18)]) * 0.92
        g.box((x, 0, z + 0.4 * s), (1.6 * s, 4.4 * s * (1 - 0.6 * t), 0.9 * s), c.m(COPPER if k % 2 else "Engine"), chamfer=0.08, kind="spinal")


def _styx_extras(ship: MandateShip) -> None:
    s, W = ship.s, ship.b["W"]
    x_st = ship.b["x0"]
    _spear(ship)
    sch = replace(ship.st.scheme, row_w=(2.5 * s, 4.5 * s), plate_len=(6 * s, 16 * s))
    for side in (-1, 1):
        ship.slab_loft(x_st + 8 * s, x_st + 62 * s, side * (W + 5.5 * s), 4 * s, 2 * s, 6 * s, 3 * s, -2 * s, sch)
    ship.keel(x_st + 30 * s, ship.b["x1"], 9 * s)
    ship.flank_armour(x_st + 68 * s, ship.b["x1"] - 16 * s)


def _lethe_extras(ship: MandateShip) -> None:
    s, H = ship.s, ship.b["H"]
    x_st = ship.b["x0"]
    ship.slab_loft(x_st + 44 * s, x_st + 66 * s, 0.0, 6 * s, 3 * s, 3.5 * s, 2.5 * s, H * 0.95 + 3 * s, nst=3)
    K2.mast(ship.c, Xf((x_st + 52 * s, 0.0, H * 0.95 + 6.5 * s + 3 * s), I3, 1.0), 9 * s, dish=2.5, arms=2, beacon=False)


def _acheron_extras(ship: MandateShip) -> None:
    s = ship.s
    x_st, x_fr = ship.b["x0"], ship.b["x1"]
    ship.keel(x_st + 40 * s, x_fr - 10 * s, 16 * s)
    ship.flank_armour(x_st + 26 * s, x_st + 0.28 * (x_fr - x_st))
    ship.flank_armour(x_st + 0.58 * (x_fr - x_st), x_fr - 24 * s)


def _mandate_hooks(ship: MandateShip, name: str) -> None:
    """Tower, weapons, radiators and hangars placed on the finished hull (heights come from its sections)."""
    s, W, H = ship.s, ship.b["W"], ship.b["H"]
    x_st, x_fr = ship.b["x0"], ship.b["x1"]
    sp = ship.sp
    if name == "acheron":
        xt = x_st + 0.64 * (x_fr - x_st)
        zt = top_at(ship, xt, -15.0) - 1.5
        dy = -0.36 * W
        sp["tower"] = dict(z=zt, mast_x=xt + 6.0, levels=[
            (xt - 48, xt + 32, 14.0, 12.0, dy, xt - 40, xt + 28, 11.0),
            (xt - 34, xt + 40, 10.0, 14.0, dy, xt - 22, xt + 44, 6.5),
            (xt - 20, xt + 22, 6.0, 9.0, dy, xt - 14, xt + 20, 4.5)])
        xm = x_st + 0.41 * (x_fr - x_st)
        sp["hangars"] = [(xm, side * ship.wat(xm) * 0.99, ship.zat(xm) - 6 * s, 44 * s, 14 * s, side) for side in (-1, 1)]
        t1x = x_fr - 30 * s
        xa = x_st + 0.72 * (x_fr - x_st)
        sp["turrets"] = [(t1x, 0.10 * W, top_at(ship, t1x, 0.10 * W) + 0.4, 1.45, 3, True), (t1x, -0.28 * W, top_at(ship, t1x, -0.28 * W) + 0.4, 1.45, 3, True),
                         (-200.0, -0.05 * W, top_at(ship, -200.0, -0.05 * W) + 0.4, 1.45, 3, True),
                         (x_fr - 50 * s, 0.45 * W, ship.zat(x_fr - 50 * s) - ship.hat(x_fr - 50 * s) * 0.86, 1.0, 2, False),
                         (xa, -0.45 * W, ship.zat(xa) - ship.hat(xa) * 0.86, 1.0, 2, False)]
        vx = [x_fr - 64 * s, x_fr - 100 * s]
        sp["vls"] = [(x, y, top_at(ship, x, y) + 0.4, 4, 3) for x in vx for y in (-0.22 * W, 0.04 * W)]
        sp["pd"] = [(x, y, top_at(ship, x, y) + 0.2) for x, y in ((90.0, -0.2 * W), (30.0, 0.05 * W), (-60.0, 0.1 * W), (-130.0, -0.1 * W))]
        sp["radiators"] = [(-250.0, -180.0, sy * 0.3 * W, top_at(ship, -215.0, sy * 0.3 * W) - 1.0, 13.6 * s, 12, 0.3) for sy in (-1, 1)]
    elif name == "styx":
        xtw = x_st + 0.55 * (x_fr - x_st)
        zt = top_at(ship, xtw, W * 0.2) - 1.0
        dy = W * 0.2
        f = 0.62
        sp["tower"] = dict(z=zt, mast_x=xtw, levels=[
            (xtw - 44 * s * f, xtw + 30 * s * f, 12 * s * f, 10 * s, dy, xtw - 36 * s * f, xtw + 26 * s * f, 9 * s * f),
            (xtw - 26 * s * f, xtw + 38 * s * f, 9 * s * f, 8 * s, dy, xtw - 18 * s * f, xtw + 20 * s * f, 5 * s * f)])
        t1, t2 = x_fr - 18 * s, x_st + 0.3 * (x_fr - x_st)
        xv = x_st + 0.6 * (x_fr - x_st)
        sp["turrets"] = [(t1, 0.0, top_at(ship, t1, 0.0) + 0.4, 0.72 * s, 2, True), (t2, 0.0, top_at(ship, t2, 0.0) + 0.4, 0.72 * s, 2, True),
                         (xv, 0.0, ship.zat(xv) - ship.hat(xv) * 0.95, 0.6 * s, 2, False)]
        sp["vls"] = [(x_fr - 40 * s, -W * 0.3, top_at(ship, x_fr - 40 * s, -W * 0.3) + 0.4, 3, 2), (x_fr - 60 * s, W * 0.2, top_at(ship, x_fr - 60 * s, W * 0.2) + 0.4, 3, 2)]
        sp["pd"] = [(-20.0, W * 0.1, top_at(ship, -20.0, W * 0.1) + 0.2), (-140.0, -W * 0.1, top_at(ship, -140.0, -W * 0.1) + 0.2)]
        sp["radiators"] = [(x_st + 14 * s, x_st + 52 * s, sy * (W + 7 * s), 2 * s, 7 * s, 6, 0.25) for sy in (-1, 1)]
    elif name == "lethe":
        t1 = x_fr - 40 * s
        sp["turrets"] = [(t1, 0.0, top_at(ship, t1, 0.0) + 0.3, 0.55 * s, 2, True)]
        sp["radiators"] = [(x_st + 22 * s, x_st + 42 * s, sy * W * 0.45, top_at(ship, x_st + 30 * s, sy * W * 0.45) - 0.5, 5 * s, 5, 0.3) for sy in (-1, 1)]
        sp["pd"] = [(0.0, W * 0.05, top_at(ship, 0.0, W * 0.05) + 0.2)]


def _build(c: Ctx, spec: dict, name: str, extras, extra_info: dict) -> dict:
    ship = MandateShip(c, spec)
    ship.body()
    ship.blades()
    extras(ship)
    _mandate_hooks(ship, name)
    ship.tower()
    ship.engines()
    ship.radiators()
    ship.weapons()
    ship.hangars()
    ship.markings()
    H.panelize_plates(c, ship.plates, ship.st)
    H.scatter_details(c, ship.plates, ship.st)
    patches(c, ship.plates, ship.st)
    welds(c, ship.plates)
    faces = ship.caps()
    info = {"cuts": list(ship.cuts), "cut_faces": faces, "length_m": spec["L"] + spec["engines"]["len"]}
    info.update(extra_info)
    return info


def build_acheron(c: Ctx) -> dict:
    return _build(c, acheron_spec(), "acheron", _acheron_extras,
                  {"cam_az": -30.0, "cam_el": 20.0, "cam_dist": 1.9, "sun_az": -55.0, "sun_el": 30.0,
                   "closeups": [{"name": "waist", "target": [-100.0, -38.0, 0.0], "normal": [0.0, -1.0, 0.25], "distance": 110.0, "span": 50.0},
                                {"name": "tower", "target": [-30.0, -15.0, 50.0], "normal": [0.2, -0.9, 0.35], "distance": 110.0, "span": 50.0}],
                   "pieces_gap": 0.11})


def build_styx(c: Ctx) -> dict:
    return _build(c, styx_spec(), "styx", _styx_extras,
                  {"cam_az": -30.0, "cam_el": 20.0, "cam_dist": 1.9, "sun_az": -55.0, "sun_el": 30.0,
                   "closeups": [{"name": "stern", "target": [-120.0, -30.0, 5.0], "normal": [-0.3, -0.9, 0.3], "distance": 100.0, "span": 50.0}],
                   "pieces_gap": 0.13})


def build_lethe(c: Ctx) -> dict:
    return _build(c, lethe_spec(), "lethe", _lethe_extras,
                  {"cam_az": -30.0, "cam_el": 20.0, "cam_dist": 1.9, "sun_az": -55.0, "sun_el": 30.0,
                   "closeups": [{"name": "hull", "target": [-20.0, -20.0, 5.0], "normal": [0.0, -1.0, 0.4], "distance": 90.0, "span": 40.0}],
                   "pieces_gap": 0.14})
