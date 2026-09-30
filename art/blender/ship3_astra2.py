"""ASTRA Navy warships v3, generic builder: the Praetorian (battleship, ~1100 m) and the Vigilant (destroyer, ~300 m).

One `Warship` class builds a ship from a spec: a lofted hull, a raised citadel or deck structure, a command tower with a bridge wing,
turrets on pedestals, missile banks, laser batteries, point defence, torpedo tubes, folding radiators, drive bells, running lights and
the Navy's markings. The Aquila (ship3_astra.py) is the same design language with its own fixed envelope.
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
import ship3_text as TX
from ship3_astra import (GOLD, NAVY, PRE, astra_sec, astra_style, flank_plating, flat_field, on_zone, ring_rect, top_z)
from ship3_cut import make_all_cuts
from ship3_kit import Ctx, Xf

I3 = np.eye(3)


class Warship:
    """Builds one ASTRA warship from a spec dict (see PRAETORIAN and VIGILANT below)."""

    def __init__(self, c: Ctx, spec: dict):
        self.c, self.g, self.rng, self.sp = c, c.g, c.rng, spec
        self.cuts = list(spec["cuts"])
        self.g.cuts = list(self.cuts)
        self.st = astra_style(spec.get("plate_scale", 1.0))
        self.plates: list[LF.Plate] = []
        W, Hh = spec["W"], spec["H"]
        x0, x1 = spec["x_st"], spec["x_bw"]
        n = max(10, int((x1 - x0) / spec.get("station_step", 16.0)))
        wp, hp = spec["wp"], spec["hp"]
        self.wp, self.hp = wp, hp
        stations = [(x0 + (i / n) * (x1 - x0), astra_sec(W * LF.profile(i / n, wp), Hh * LF.profile(i / n, hp)), 0.0) for i in range(n + 1)]
        self.hull = LF.Loft.along_x(stations).with_stations(self.cuts)
        self.bow_sec = astra_sec(W * LF.profile(1.0, wp), Hh * LF.profile(1.0, hp))
        self.stern_sec = astra_sec(W * LF.profile(0.0, wp), Hh * LF.profile(0.0, hp))
        self.rib_x = [float(x) for x in np.arange(x0 + 25.0, x1 - 20.0, spec.get("rib_step", 60.0)) if all(abs(x - xc) > 12 for xc in self.cuts)]
        self.deck = None
        self.deck_top = None
        self.spines: list = []
        self.keel = None

    # ---------------------------------------------------------------------------------------------------- hull
    def plate_hull(self) -> None:
        c, g, rng, sp = self.c, self.g, self.rng, self.sp
        voids = [(x - 0.9, x + 0.9) for x in self.rib_x]
        for z in self.hull.zones():
            z.skin(g, c.m("Frame"))
        x_span = (sp["x_st"] + 6.0, sp["x_bw"] - sp.get("window_stop", 40.0))
        for k in range(8):
            z = self.hull.zone(k)
            if k in (2, 6):
                fl = sp.get("flank", {})
                self.plates += flank_plating(c, self.st, z, voids, self.cuts, x_span, sp.get("name_span"), **fl)
            else:
                dark = -0.10 if k in (0, 1, 7) else 0.0
                self.plates += LF.plate_zone(g, z, rng, self.st.scheme, PRE, tone_fn=lambda a, w, d=dark: d, voids=voids)
        H.ribs(c, self.hull, self.rib_x, 1.8, 1.25)

    def citadel(self) -> None:
        """A raised deck structure on the hull (the battleship's armoured citadel): a chamfered loft with plated sides."""
        d = self.sp.get("citadel")
        if not d:
            return
        c, g, rng = self.c, self.g, self.rng
        Hh = self.sp["H"]
        n = max(6, int((d["x1"] - d["x0"]) / 14.0))
        zo = Hh * 0.9 + d["h"] - 1.0
        stations = [(d["x0"] + (i / n) * (d["x1"] - d["x0"]), LF.chamfer_rect(d["w"] * LF.profile(i / n, d.get("prof", [(0, 0.8), (0.12, 1.0), (0.88, 1.0), (1, 0.75)])),
                                                                                 d["h"], 0.35, top=0.8), zo) for i in range(n + 1)]
        deck = LF.Loft.along_x(stations).with_stations(self.cuts)
        self.deck = deck
        self.deck_top = zo + d["h"]
        sch = replace(self.st.scheme, levels=(0.7, 1.0, 1.35), level_weights=(0.4, 0.4, 0.2), row_w=(4.0, 7.0), plate_len=(16, 60))
        voids = d.get("voids", [])
        for k in range(2, 7):
            z = deck.zone(k)
            z.skin(g, c.m("Frame"))
            self.plates += LF.plate_zone(g, z, rng, sch, PRE, voids=voids if k == 4 else ())
        H.end_face(c, np.array(stations[-1][1]), d["x1"], 1.0, self.st, zo=zo)
        H.end_face(c, np.array(stations[0][1]), d["x0"], -1.0, self.st, zo=zo)
        # windows on the citadel's flanks
        for k in (2, 6):
            for w in (0.30, 0.62):
                K2.window_band(c, deck.zone(k), w, d["x0"] + 12.0, d["x1"] - 12.0, rows=1, lift=0.8)

    def tower(self) -> None:
        d = self.sp.get("tower")
        if not d:
            return
        c, g, rng = self.c, self.g, self.rng
        z0 = top_z(self.hull, 0.5 * (d["x0"] + d["x1"])) if self.deck is None else self.deck_top
        z0 = d.get("z0", z0 - 2.0)
        zt = z0 + d["h"]
        sch = replace(self.st.scheme, row_w=(2.6, 4.2), plate_len=(6.0, 16.0), levels=(0.45,), level_weights=(1.0,), wedge=0.0, chamfer=0.08, rim=0.2, min_len=3.0)
        loft = LF.Loft([z0, zt], [ring_rect(d["x0"], d["x1"], d["hy"], z0, 0.18 * min(d["x1"] - d["x0"], 2 * d["hy"])),
                                  ring_rect(d["tx0"], d["tx1"], d["thy"], zt, 0.18 * min(d["tx1"] - d["tx0"], 2 * d["thy"]))])
        for z in loft.zones():
            z.skin(g, c.m("Frame"))
            self.plates += LF.plate_tower(g, z, rng, sch, PRE)
        ring = loft.R[-1]
        cen = ring.mean(axis=0)
        V = np.vstack([ring, cen])
        k = len(ring)
        F = np.stack([np.arange(k), (np.arange(k) + 1) % k, np.full(k, k)], axis=1)
        if np.sum(np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])[:, 2]) < 0:
            F = F[:, [0, 2, 1]]
        g.add(V, F, c.m("Frame"), a1=(0.0, 0.5), kind="skin")
        for zone in (loft.zone(0), loft.zone(4), loft.zone(2)):
            for zz in np.arange(z0 + 6.0, zt - 4.0, 6.5):
                K2.window_row(c, zone, float(zz), 0.10, 0.90, lift=0.5)
        # the bridge wing: a wide platform across the tower
        wz = z0 + d["h"] * d.get("wing_at", 0.62)
        xw0, xw1 = d["x0"] + 4.0, d["x1"] - 4.0
        wing = LF.Loft.along_x([(x, LF.chamfer_rect(d.get("wing", 46.0), 3.0, 0.3), wz) for x in (xw0, 0.5 * (xw0 + xw1), xw1)])
        wsch = replace(self.st.scheme, row_w=(3.0, 5.0), plate_len=(8, 20), levels=(0.4, 0.6), level_weights=(0.5, 0.5), mats=(("Plate", 0.8), ("Frame", 0.2)))
        for kk in range(8):
            z = wing.zone(kk)
            z.skin(g, c.m("Frame"))
            self.plates += LF.plate_zone(g, z, rng, wsch, PRE)
        for sy in (-1, 1):
            K2.window_band(c, wing.zone(2 if sy > 0 else 6), 0.5, xw0 + 3, xw1 - 3, rows=1, lift=0.5)
        H.end_face(c, np.array(LF.chamfer_rect(d.get("wing", 46.0), 3.0, 0.3)), xw1, 1.0, self.st, zo=wz)
        H.end_face(c, np.array(LF.chamfer_rect(d.get("wing", 46.0), 3.0, 0.3)), xw0, -1.0, self.st, zo=wz)
        K2.antenna_farm(c, Xf((0.5 * (d["tx0"] + d["tx1"]), 0.0, zt + 0.2), I3, 1.0), min(d["thy"] * 1.6, 14.0), min(d["tx1"] - d["tx0"], 20.0), n=9)
        K2.mast(c, Xf((d["tx0"] + 2.0, d["thy"] * 0.5, zt + 0.3), I3, 1.0), 18.0, dish=4.0, arms=3, beacon=True)
        g.keep_out((d["x0"] - 2, -d["hy"] - 2, z0), (d["x1"] + 2, d["hy"] + 2, zt + 30))

    # ---------------------------------------------------------------------------------------------- ends, drive
    def ends(self) -> None:
        c, sp = self.c, self.sp
        H.end_face(c, np.array(self.bow_sec), sp["x_bw"], 1.0, self.st)
        H.end_face(c, np.array(self.stern_sec), sp["x_st"], -1.0, self.st)

    def engines(self) -> None:
        c, g, rng, sp = self.c, self.g, self.rng, self.sp
        e = sp["engines"]
        Hh = sp["H"]
        sec = LF.chamfer_rect(e["w"], e["h"], 0.3)
        xa, xb = sp["x_st"] - e["len"], sp["x_st"]
        blk = LF.Loft.along_x([(x, sec, 0.0) for x in (xa, 0.5 * (xa + xb), xb)])
        sch = replace(self.st.scheme, row_w=(3.0, 5.0), plate_len=(8, 20), levels=(0.5, 0.8), level_weights=(0.6, 0.4), mats=(("Frame", 0.8), ("Plate", 0.2)))
        for z in blk.zones():
            z.skin(g, c.m("Frame"))
            self.plates += LF.plate_zone(g, z, rng, sch, PRE)
        H.end_face(c, np.array(sec), xa, -1.0, self.st)
        K2.engine_bank(c, xa, e["ys"], e["zs"], e["R"])
        for sy in (-1, 1):
            for sz in (-1, 1):
                fr = G.frame_z((0.0, sy, 0.0), (0.0, 0.0, 1.0))
                K2.thruster_cluster(c, Xf((xb - 4.0, sy * (e["w"] + 1.5), sz * e["h"] * 0.75), fr, 1.0), e.get("rcs", 0.9))

    # --------------------------------------------------------------------------------------------- hardware
    def hardware(self) -> None:
        c, g, rng, sp = self.c, self.g, self.rng, self.sp
        hull = self.hull
        for x, y, s, nb, elev, ped, where in sp["turrets"]:
            base = top_z(hull, x) if where == "hull" or self.deck is None else self.deck_top
            if where == "deck" and self.deck is not None and self.deck.a[0] < x < self.deck.a[-1]:
                base = top_z(self.deck, x)
            z0 = base + 0.3
            if ped > 0.0:                                                     # the pedestal a superfiring turret stands on
                r = 6.6 * s
                pe = LF.Loft.along_x([(x - r * 1.25, LF.chamfer_rect(r * 1.2, ped / 2, 0.25), z0 + ped / 2 - 0.4), (x + r * 1.25, LF.chamfer_rect(r * 1.2, ped / 2, 0.25), z0 + ped / 2 - 0.4)])
                for kk in range(2, 7):
                    z = pe.zone(kk)
                    z.skin(g, c.m("Frame"))
                    self.plates += LF.plate_zone(g, z, rng, replace(self.st.scheme, row_w=(2.5, 4.0), plate_len=(6, 14), levels=(0.4,), level_weights=(1.0,), min_len=3.0), PRE)
                H.end_face(c, np.array(LF.chamfer_rect(r * 1.2, ped / 2, 0.25)), x + r * 1.25, 1.0, self.st, zo=z0 + ped / 2 - 0.4, plate=False)
                H.end_face(c, np.array(LF.chamfer_rect(r * 1.2, ped / 2, 0.25)), x - r * 1.25, -1.0, self.st, zo=z0 + ped / 2 - 0.4, plate=False)
                z0 += ped
            K.railgun_turret(c, Xf((x, y, z0), I3, s), barrels=nb, elev=elev)
            g.keep_out((x - 9 * s, y - 9 * s, z0 - 1), (x + 9 * s, y + 9 * s, z0 + 9 * s))
        for x, y, cols, rows in sp.get("vls", []):
            base = (top_z(self.deck, x) if self.deck is not None and self.deck.a[0] < x < self.deck.a[-1] else top_z(hull, x)) + 0.4
            K.vls_bank(c, Xf((x, y, base), I3, 1.0), cols, rows, 3.2)
            g.keep_out((x - cols * 1.7, y - rows * 1.7, base - 1), (x + cols * 1.7, y + rows * 1.7, base + 3))
        for k, xs in sp.get("lasers", {}).items():
            for x in xs:
                P, R = on_zone(hull.zone(int(k)), float(x), 0.5, 0.5)
                K.laser_battery(c, Xf(P, R, sp.get("laser_scale", 1.0)))
                g.keep_out(P - 5, P + 5)
        for i, x in enumerate(sp.get("pd", [])):
            P, R = on_zone(hull.zone(3 if i % 2 == 0 else 5), float(x), 0.86, 0.5)
            K.pd_mount(c, Xf(P, R, sp.get("pd_scale", 1.0)))
            g.keep_out(P - 3, P + 3)
        for x, w in sp.get("torps", []):
            for k in (2, 6):
                P, N, _ = hull.zone(k).frame(np.array([float(x)]), np.array([float(w)]))
                from ship3_astra import torpedo_tube
                torpedo_tube(c, Xf(P[0] + N[0] * 0.4, G.frame_x(N[0], (0.0, 0.0, 1.0)), sp.get("torp_scale", 1.0)))
                g.keep_out(P[0] - 6, P[0] + 6)
        for x0, ln, span, op in sp.get("radiators", []):
            for sy in (1, -1):
                hy = sp["W"] * 0.9
                hz = sp["H"] * 0.76
                xf = Xf((x0, hy, hz), I3, 1.0) if sy > 0 else Xf((x0 + ln, -hy, hz), Xf().rot_z(180.0), 1.0)
                K2.radiator_wing(c, xf, ln, span, op)
                g.keep_out((x0, -1000 if sy < 0 else hy - 5, 0), (x0 + ln, -hy + 5 if sy < 0 else 1000, 200))
        for k, x in ((3, sp["x_bw"] - 18.0), (5, sp["x_bw"] - 18.0)):
            P, N, _ = hull.zone(k).frame(np.array([x]), np.array([0.5]))
            K2.nav_light(c, P[0] + N[0] * 0.4, N[0], K2.NAV_RED if k == 3 else K2.NAV_GREEN, 1.6)
        for sy in (-1, 1):
            K2.nav_light(c, np.array([sp["x_st"] - sp["engines"]["len"] + 3.0, sy * sp["engines"]["w"] * 0.85, sp["engines"]["h"] * 0.98]), np.array([-0.3, sy * 0.3, 0.9]), K2.NAV_WHITE, 1.6)
        K2.nav_light(c, np.array([0.0, 0.0, -sp["H"] - 6.0]), np.array([0.0, 0.0, -1.0]), K2.NAV_RED, 2.0, pulse=True)

    def belly(self) -> None:
        """Cargo doors, sensor drums, tow hardpoints and point-defence mounts on the flat bottom (spec key "belly"). Nothing crosses a cut."""
        b = self.sp.get("belly")
        if not b:
            return
        c, g, rng = self.c, self.g, self.rng
        s = b.get("scale", 1.0)
        z = self.hull.zone(0)
        ok = lambda x, half: all(abs(x - xc) > half + 6.0 for xc in self.cuts)                      # noqa: E731
        for x in b.get("doors", []):
            if ok(x, 13.0 * s):
                P, R = on_zone(z, float(x), 0.5, 0.0)
                K2.cargo_door(c, Xf(P, R, 1.0), 26.0 * s, 14.0 * s)
                g.keep_out(P - np.array([16.0, 9.0, 8.0]) * s, P + np.array([16.0, 9.0, 8.0]) * s)
        for x in b.get("sensors", []):
            if ok(x, 4.0 * s):
                P, R = on_zone(z, float(x), 0.5, 0.0)
                K2.sensor_cluster(c, Xf(P, R, 1.0), 3.4 * s)
                g.keep_out(P - 5.0 * s, P + 5.0 * s)
        for x in b.get("hardpoints", []):
            for w in b.get("rows", (0.15, 0.85)):
                if not ok(x, 4.0 * s):
                    continue
                P, R = on_zone(z, float(x), float(w), 0.0)
                if rng.random() < 0.6:
                    K2.tow_lug(c, Xf(P, R, s))
                else:
                    K.pd_mount(c, Xf(P, R, s))
                g.keep_out(P - 3.0 * s, P + 3.0 * s)

    def markings(self) -> None:
        c, g, sp = self.c, self.g, self.sp
        hull = self.hull
        m = sp.get("marks")
        if not m:
            return
        for k in (2, 6):
            P, N, _ = hull.zone(k).frame(np.array([m["x"]]), np.array([m.get("w", 0.618)]))
            TX.place_text(g, m["number"], P[0] + N[0] * 0.5, N[0], m.get("h", 3.0), c.m("Marking"), depth=0.06)
            if m.get("name"):
                P2, N2, _ = hull.zone(k).frame(np.array([m["name_x"]]), np.array([0.30]))
                TX.place_text(g, m["name"], P2[0] + N2[0] * 0.4, N2[0], m.get("name_h", 4.0), c.m("Marking"), depth=0.06)
        if "emblem_at" in m:
            ex, ew, dia = m["emblem_at"]
            zone = hull.zone(4)
            outline_c = 0.5 * dia
            field = flat_field(c, zone, ex - dia * 0.6, ex + dia * 0.6, ew - dia * 0.6 / zone.sw(ex), ew + dia * 0.6 / zone.sw(ex), "Plate", 0.4)
            P, N, _ = zone.frame(np.array([ex]), np.array([ew]))
            TX.astra_emblem(g, P[0] + N[0] * 0.4, N[0], dia, c.m("Marking"), up=(1.0, 0.0, 0.0), depth=0.08)

    # ---------------------------------------------------------------------------------------------- caps
    def cap_extras(self, xc: float) -> list:
        ex = []
        top = top_z(self.hull, xc)
        for loft in [self.deck] + self.spines:
            if loft is not None and loft.a[0] + 1.0 < xc < loft.a[-1] - 1.0:
                ex.append((loft.ring_at(xc)[:, 1:3], 1, top))
        return ex

    def caps(self) -> list:
        return make_all_cuts(self.c, self.hull, self.cuts, extras_fn=self.cap_extras, depth=self.sp.get("cap_depth", 30.0), scale=self.sp.get("cap_scale", 1.0))

    def build(self, details: bool = True) -> None:
        c = self.c
        self.plate_hull()
        self.citadel()
        self.tower()
        self.ends()
        self.engines()
        self.hardware()
        self.belly()
        self.markings()
        if details:
            H.panelize_plates(c, self.plates, self.st)
            H.scatter_details(c, self.plates, self.st)
            H.rivet_plates(c, self.plates)


# ================================================================================================================ specs
PRAETORIAN = dict(
    L=1100.0, x_st=-528.0, x_bw=550.0, W=70.0, H=32.0, plate_scale=1.25, station_step=20.0, rib_step=72.0, window_stop=60.0,
    wp=[(0.0, 0.88), (0.08, 1.0), (0.60, 1.0), (0.84, 0.62), (0.96, 0.24), (1.0, 0.10)], hp=[(0.0, 0.9), (0.1, 1.0), (0.7, 1.0), (1.0, 0.45)],
    cuts=(215.0, -215.0),
    citadel=dict(x0=-190.0, x1=190.0, w=44.0, h=16.0, prof=[(0, 0.85), (0.1, 1.0), (0.9, 1.0), (1, 0.8)], voids=[(-20.0, 20.0)]),
    tower=dict(x0=-150.0, x1=-40.0, hy=22.0, tx0=-125.0, tx1=-65.0, thy=12.0, h=105.0, wing=48.0, wing_at=0.6),
    turrets=[(x, 0.0, 2.6, 3, 8.0, ped, "hull") for x, ped in ((445.0, 0.0), (350.0, 8.0), (255.0, 16.0))] +
            [(x, 0.0, 2.6, 3, 8.0, ped, "hull") for x, ped in ((-445.0, 0.0), (-350.0, 8.0), (-255.0, 16.0))],
    vls=[(40.0, 22.0, 6, 4), (40.0, -22.0, 6, 4), (-70.0, 22.0, 6, 4), (-70.0, -22.0, 6, 4)],
    lasers={"3": [-480, -420, -330, -140, -30, 100, 300, 400], "5": [-450, -380, -300, -100, 20, 150, 350, 470]},
    pd=list(np.arange(-500.0, 520.0, 36.0)),
    torps=[(430.0, 0.3), (-40.0, 0.25)],
    radiators=[(-500.0, 80.0, 34.0, 32.0), (-410.0, 80.0, 34.0, 32.0), (-320.0, 80.0, 34.0, 32.0)],
    engines=dict(len=26.0, w=52.0, h=27.0, ys=[-26.0, 0.0, 26.0], zs=[-11.0, 11.0], R=11.5, rcs=1.1),
    marks=dict(x=420.0, number="BB-07", h=4.0, name="ASN PRAETORIAN", name_x=-330.0, name_h=5.0, emblem_at=(300.0, 0.5, 26.0)),
    cap_scale=1.25, cap_depth=36.0,
    belly=dict(scale=1.6, doors=[-400.0, -120.0, 100.0, 340.0, 480.0], sensors=[-470.0, -270.0, 10.0, 270.0, 520.0],
               hardpoints=[-500.0, -330.0, -180.0, 50.0, 170.0, 290.0, 410.0]),
)

VIGILANT = dict(
    L=300.0, x_st=-135.0, x_bw=150.0, W=18.0, H=9.5, plate_scale=0.55, station_step=10.0, rib_step=40.0, window_stop=15.0,
    wp=[(0.0, 0.85), (0.12, 1.0), (0.62, 1.0), (0.9, 0.5), (1.0, 0.1)], hp=[(0.0, 0.9), (0.1, 1.0), (0.7, 0.95), (1.0, 0.4)],
    cuts=(58.0, -58.0),
    citadel=None,
    tower=dict(x0=-20.0, x1=25.0, hy=8.0, tx0=-8.0, tx1=14.0, thy=4.5, h=22.0, wing=12.0, wing_at=0.55),
    turrets=[(95.0, 0.0, 0.9, 2, 8.0, 0.0, "hull"), (-95.0, 0.0, 0.9, 2, 8.0, 0.0, "hull")],
    vls=[(-50.0, 0.0, 4, 2)],
    lasers={"3": [-30, 30], "5": [-10, 50]},
    laser_scale=0.6, pd_scale=0.7,
    pd=list(np.arange(-100.0, 120.0, 30.0)),
    torps=[(90.0, 0.3)], torp_scale=0.5,
    radiators=[(-110.0, 36.0, 12.0, 30.0)],
    engines=dict(len=11.0, w=14.0, h=7.5, ys=[-5.5, 5.5], zs=[0.0], R=4.6, rcs=0.5),
    marks=dict(x=110.0, number="DD-114", h=1.7, name="ASN VIGILANT", name_x=-70.0, name_h=2.2),
    flank=dict(band=(0.52, 0.72), strips=((0.14, 0.20),), lower_top=0.485, band_row=(2.6, 3.2)),
    cap_scale=0.5, cap_depth=16.0,
    belly=dict(scale=0.5, doors=[-70.0, 20.0, 110.0], sensors=[-10.0, 130.0], hardpoints=[-110.0, -40.0, 75.0], rows=(0.2, 0.8)),
)


def _build(c: Ctx, spec: dict, extra: dict) -> dict:
    ship = Warship(c, spec)
    ship.build()
    faces = ship.caps()
    info = {"cuts": list(ship.cuts), "cut_faces": faces, "length_m": spec["L"] + spec["engines"]["len"] + 12.0}
    info.update(extra)
    return info


def build_praetorian(c: Ctx) -> dict:
    return _build(c, PRAETORIAN, {"cam_az": -30.0, "cam_el": 16.0, "cam_dist": 1.9, "sun_az": -50.0, "sun_el": 26.0,
                                  "closeups": [{"name": "tower", "target": [-95.0, -20.0, 75.0], "normal": [-0.3, -0.9, 0.3], "distance": 120.0, "span": 50.0},
                                               {"name": "turrets", "target": [350.0, 0.0, 44.0], "normal": [-0.4, -0.5, 0.75], "distance": 130.0, "span": 50.0}],
                                  "pieces_gap": 0.09, "pieces_dist": 2.3})


def build_vigilant(c: Ctx) -> dict:
    return _build(c, VIGILANT, {"cam_az": -30.0, "cam_el": 18.0, "cam_dist": 1.9, "sun_az": -50.0, "sun_el": 26.0,
                                "closeups": [{"name": "bow", "target": [95.0, 0.0, 12.0], "normal": [-0.3, -0.6, 0.75], "distance": 60.0, "span": 30.0}],
                                "pieces_gap": 0.14})
