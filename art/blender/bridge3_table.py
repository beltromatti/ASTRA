"""ASN Aquila bridge v3: the holographic tactical table (AAstraHoloTable stands on it).

Origin = the table centre on the floor of the well. The top is 0.95 m above the floor; the volume above it is left clear
(the hologram reaches 2.2 m above the top). A flared pedestal, a dish-shaped body, a rim ring with range ticks and a crown
of emitter lenses, a matte black projection plate and a projector lens at the centre; a marker on the bow side shows which way is forward.
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge3_lib as L  # noqa: E402
from bridge3_lib import Parts, Rz, T, polar  # noqa: E402


def build_holo_table(D: dict, name: str = "SM_BRG3_HoloTable"):
    ht = D["holo_table"]
    R = ht["radius"]
    H = ht["height"]
    plot_r = ht.get("plot_radius", R - 0.15)
    b = Parts(bevel=0.007, fine_bevel=0.0035)
    fb, fine, em = b.body, b.fine, b.emit
    rev = lambda prof, mat, z0=0.0, seg=64: fb.arc_sweep(prof, 0, 0, 0, 0, 360, mat, seg=seg, z0=z0, loop=True)

    # floor plate with a lit foot ring
    rev([(0.0 + 0.001, 0.0), (0.82, 0.0), (0.82, 0.035), (0.001, 0.035)], L.STRUCT)
    rev([(0.82, 0.0), (0.86, 0.0), (0.86, 0.02), (0.82, 0.02)], L.TRIM)
    em.lamp_arc([(0.70, 0.0), (0.74, 0.0), (0.74, 0.004), (0.70, 0.004)], 0, 0, 0, 0, 360, "command", L.LAMP, seg=72, z0=0.036, loop=True)
    # pedestal: flared cone, fins, neck with two lit bands
    rev([(0.001, 0.035), (0.64, 0.035), (0.34, 0.50), (0.001, 0.50)], L.STRUCT)
    for k in range(16):
        a = 360.0 * k / 16
        with b.at(Rz(a)):
            fb.extrude_y([(0.50, 0.08), (0.62, 0.05), (0.42, 0.44), (0.38, 0.44)], -0.03, 0.03, L.IVORY)
    rev([(0.001, 0.50), (0.36, 0.50), (0.32, 0.68), (0.001, 0.68)], L.COMPOSITE)
    em.lamp_arc([(0.332, 0.0), (0.342, 0.0), (0.342, 0.008), (0.332, 0.008)], 0, 0, 0, 0, 360, "command_dim", L.LAMP_DIM, seg=48, z0=0.56, loop=True)
    # the dish-shaped body, dark composite with an ivory belt and a lit underside ring
    rev([(0.001, 0.66), (1.28, 0.80), (1.28, 0.93), (0.001, 0.93)], L.COMPOSITE, seg=72)
    rev([(1.12, 0.795), (1.30, 0.815), (1.30, 0.86), (1.12, 0.845)], L.IVORY, seg=72)
    em.lamp_arc([(0.98, 0.0), (1.06, 0.0), (1.06, 0.004), (0.98, 0.004)], 0, 0, 0, 0, 360, "command", L.LAMP, seg=72, z0=0.783, loop=True)
    # the rim ring: brushed metal, a stepped outer band, an inner chamfer towards the glass
    rev([(plot_r + 0.02, 0.86), (R, 0.86), (R, 0.955), (plot_r + 0.02, 0.955)], L.STRUCT, seg=72)
    rev([(plot_r + 0.02, 0.953), (R - 0.004, 0.953), (R - 0.004, 0.962), (plot_r + 0.02, 0.962)], L.BRASS, seg=72)    # the brass bezel
    rev([(R, 0.84), (R + 0.02, 0.84), (R + 0.02, 0.94), (R, 0.94)], L.TRIM, seg=72)
    # the dark glass projection plate (satin: no mirror of the ceiling) and a lit line at its edge
    rev([(0.001, 0.93), (plot_r + 0.02, 0.93), (plot_r + 0.02, 0.945), (0.001, 0.945)], L.DGLASS, seg=72)
    em.lamp_arc([(plot_r + 0.004, 0.0), (plot_r + 0.02, 0.0), (plot_r + 0.02, 0.003), (plot_r + 0.004, 0.003)], 0, 0, 0, 0, 360, "cyan", L.LAMP_DIM,
                seg=96, z0=0.9455, loop=True)
    # range ticks on the rim (every 5 degrees, a longer one every 30) and the crown of emitter lenses
    rim_mid = (plot_r + 0.02 + R) / 2
    for k in range(72):
        a = 5.0 * k
        long_tick = (k % 6 == 0)
        px, py = polar(0, 0, rim_mid + 0.005, a)
        fine.cbox((px, py, 0.9565), (0.05 if long_tick else 0.028, 0.005 if long_tick else 0.003, 0.003), L.STRUCT, Rz(a))
    for k in range(48):
        a = 7.5 * k + 3.75
        px, py = polar(0, 0, plot_r + 0.055, a)
        em.lamp_cyl((px, py, 0.955), (px, py, 0.962), 0.0105, "cyan" if k % 4 else "white", L.LAMP, seg=8)
    # the bearing numerals on the brass bezel, every 30 degrees (the same dial as the floor's), read from outside
    for k in range(12):
        a = 30.0 * k
        px, py = polar(0, 0, rim_mid + 0.012, a)
        out = (math.cos(math.radians(a)), math.sin(math.radians(a)), 0.0)
        em.text(f"{int(a):03d}", (px, py, 0.9632), 0.026, (0, 0, 1), L.LAMP_DIM, up=out, cell="warm_dim", tracking=0.004)
    # the underside of the dish: a ring of light dashes and the pedestal's slits between the fins
    for k in range(36):
        a = 10.0 * k + 5.0
        p0, p1 = polar(0, 0, 1.18, a - 3.0), polar(0, 0, 1.18, a + 3.0)
        em.lamp_cbox((0.5 * (p0[0] + p1[0]), 0.5 * (p0[1] + p1[1]), 0.776), (0.1, 0.012, 0.004), "command_dim", L.LAMP_DIM, Rz(a))
    for k in range(16):
        a = 360.0 * k / 16 + 11.25
        px, py = polar(0, 0, 0.44, a)
        em.lamp_cbox((px, py, 0.27), (0.012, 0.010, 0.36), "command_dim", L.LAMP_DIM, Rz(a))
    # the bow marker: a lit chevron and the word FWD on the far side (+x)
    px, py = polar(0, 0, rim_mid, 0.0)
    em.lamp_face([(px - 0.03, py - 0.03, 0.9572), (px + 0.03, py, 0.9572), (px - 0.03, py + 0.03, 0.9572), (px - 0.012, py, 0.9572)], "amber", (0, 0, 1))
    # the projector lens at the centre: a dome in a ring, a lit collar
    fine.cyl((0, 0, 0.945), (0, 0, 0.962), 0.15, L.TRIM, seg=40)
    em.lamp_cyl((0, 0, 0.9615), (0, 0, 0.9635), 0.13, "cyan", L.LAMP_DIM, seg=40)
    fine.sphere((0, 0, 0.9625), 0.105, L.DGLASS, seg=24, rings=12, squash=(1.0, 1.0, 0.55))
    # service details: data ports and a plate on the pedestal
    for a in (30.0, 150.0, 270.0):
        px, py = polar(0, 0, 0.345, a)
        with b.at(T(px, py, 0.60) @ Rz(a)):
            fine.box((0.0, -0.05, -0.04), (0.02, 0.05, 0.04), L.TRIM)
            em.lamp_box((0.02, -0.03, -0.006), (0.024, 0.03, 0.006), "green", L.LAMP_DIM)
    return b.build(name, uv_meter=0.5)
