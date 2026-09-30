"""ASN Aquila interior kit: the wall furniture of the corridors and rooms in the bridge v3 language (dark composite panels in
brushed frames, structural ribs with light lines, cable trays and conduits, hatches, lockers, breaker panels, extinguishers,
first aid, vents, labels). Same pieces as bridge3_walls.py but for a 3.4 m deck and with the ship's label atlas.

Wall-local frame (every function): s along the wall, t outward from the finished face (t = 0; negative t is into the space),
z up. The caller enters it with `with parts.at(wall_matrix):`. `fb` is a SFB (ship_lib).
"""
from __future__ import annotations

import math
import random

from bridge3_lib import Rx
import ship_lib as SL
from ship_lib import (COMPOSITE, IVORY, LAMP, LAMP_DIM, LAMP_HOT, RUBBER, STRUCT, TRIM, PAINT_RED, SFB)

RIB_W = 0.20
RIB_T = 0.13


def bolt(fb: SFB, s: float, z: float, t: float = 0.0, r: float = 0.009, h: float = 0.007) -> None:
    fb.cyl((s, t, z), (s, t - h, z), r, TRIM, seg=6)


def bolts_rect(fb: SFB, s0: float, s1: float, z0: float, z1: float, t: float, inset: float = 0.05) -> None:
    for s in (s0 + inset, s1 - inset):
        for z in (z0 + inset, z1 - inset):
            bolt(fb, s, z, t)


def panel(fb: SFB, s0: float, s1: float, z0: float, z1: float, mat: str = COMPOSITE, fw: float = 0.028, proud: float = 0.026,
          raised: bool = True, bolts: bool = True) -> None:
    """A layered wall panel: composite slab, brushed frame, raised centre field, four bolts."""
    fb.box((s0, -proud, z0), (s1, 0.0, z1), mat)
    tf = -proud - 0.012
    fb.box((s0, tf, z0), (s1, -proud, z0 + fw), TRIM)
    fb.box((s0, tf, z1 - fw), (s1, -proud, z1), TRIM)
    fb.box((s0, tf, z0 + fw), (s0 + fw, -proud, z1 - fw), TRIM)
    fb.box((s1 - fw, tf, z0 + fw), (s1, -proud, z1 - fw), TRIM)
    if raised and (s1 - s0) > 0.3 and (z1 - z0) > 0.3:
        fb.box((s0 + fw + 0.035, -proud - 0.007, z0 + fw + 0.035), (s1 - fw - 0.035, -proud, z1 - fw - 0.035), mat)
    if bolts:
        bolts_rect(fb, s0, s1, z0, z1, tf, 0.04)


def vent(fb: SFB, s0: float, s1: float, z0: float, z1: float, slats: int = 7, t: float = 0.0) -> None:
    fb.box((s0 - 0.03, t - 0.034, z0 - 0.03), (s1 + 0.03, t - 0.004, z1 + 0.03), TRIM)
    fb.box((s0, t - 0.036, z0), (s1, t - 0.02, z1), RUBBER)
    h = (z1 - z0) / slats
    for k in range(slats):
        zc = z0 + (k + 0.5) * h
        fb.cbox(((s0 + s1) / 2, t - 0.03, zc), (s1 - s0 - 0.01, 0.006, h * 1.25), TRIM, Rx(-32))


def hatch(fb: SFB, sc: float, zc: float, w: float, h: float, label: str | None = None) -> None:
    s0, s1, z0, z1 = sc - w / 2, sc + w / 2, zc - h / 2, zc + h / 2
    fb.box((s0 - 0.04, -0.05, z0 - 0.04), (s1 + 0.04, -0.008, z1 + 0.04), TRIM)
    fb.box((s0, -0.06, z0), (s1, -0.05, z1), COMPOSITE)
    fb.box((s0 + 0.05, -0.066, z0 + 0.05), (s1 - 0.05, -0.06, z1 - 0.05), STRUCT)
    fb.box((sc - 0.11, -0.085, zc - 0.03), (sc + 0.11, -0.06, zc + 0.03), TRIM)
    fb.box((sc - 0.09, -0.078, zc - 0.018), (sc + 0.09, -0.06, zc + 0.018), RUBBER)
    for s in (s0 + 0.05, s1 - 0.05):
        for z in (z0 + 0.06, z1 - 0.06):
            fb.cyl((s, -0.066, z), (s, -0.082, z), 0.018, TRIM, seg=8)
    fb.lamp_box((s1 - 0.05, -0.068, zc + h * 0.25), (s1 - 0.03, -0.062, zc + h * 0.25 + 0.05), "green", LAMP)
    if label:
        fb.label((sc, -0.03, z1 + 0.10), min(w, 0.6), min(w, 0.6) / 4, (0, -1, 0), label)


def locker_bank(fb: SFB, s0: float, s1: float, z0: float, z1: float, n: int, labels: list[str], cell: str) -> None:
    w = (s1 - s0) / n
    fb.box((s0 - 0.03, -0.06, z0 - 0.03), (s1 + 0.03, -0.01, z1 + 0.03), TRIM)
    for k in range(n):
        a, b = s0 + k * w + 0.012, s0 + (k + 1) * w - 0.012
        fb.box((a, -0.075, z0), (b, -0.05, z1), COMPOSITE)
        fb.box((a + 0.03, -0.082, z0 + 0.03), (b - 0.03, -0.075, z1 - 0.03), STRUCT)
        fb.box((b - 0.09, -0.098, (z0 + z1) / 2 - 0.15), (b - 0.06, -0.075, (z0 + z1) / 2 + 0.15), TRIM)
        for j in range(3):
            fb.box((a + 0.06, -0.09, z1 - 0.14 - j * 0.035), (b - 0.06, -0.082, z1 - 0.12 - j * 0.035), RUBBER)
        fb.lamp_box((a + 0.05, -0.088, z0 + 0.12), (a + 0.09, -0.082, z0 + 0.14), cell if k % 2 == 0 else "green", LAMP)
        if k < len(labels):
            fb.label(((a + b) / 2, -0.08, z1 - 0.34), min(w - 0.1, 0.5), min(w - 0.1, 0.5) / 4, (0, -1, 0), labels[k])


def breaker_panel(fb: SFB, s0: float, s1: float, z0: float, z1: float, rng: random.Random, label: str) -> None:
    fb.box((s0 - 0.03, -0.055, z0 - 0.03), (s1 + 0.03, -0.01, z1 + 0.03), TRIM)
    fb.box((s0, -0.06, z0), (s1, -0.04, z1), COMPOSITE)
    fb.label(((s0 + s1) / 2, -0.062, z1 - 0.06), (s1 - s0) - 0.1, 0.09, (0, -1, 0), "hazard")
    rows = max(2, int((z1 - z0 - 0.3) / 0.13))
    cols = max(3, int((s1 - s0 - 0.1) / 0.11))
    for r in range(rows):
        for c in range(cols):
            s = s0 + 0.08 + c * ((s1 - s0 - 0.16) / max(1, cols - 1))
            z = z0 + 0.1 + r * 0.13
            fb.box((s - 0.022, -0.075, z - 0.028), (s + 0.022, -0.06, z + 0.028), RUBBER)
            fb.box((s - 0.008, -0.088, z - 0.01), (s + 0.008, -0.075, z + 0.012 if rng.random() < 0.5 else z - 0.004), TRIM)
            cell = rng.choice(["green", "green", "green", "amber", "cyan", "ice"])
            fb.lamp_box((s - 0.006, -0.062, z + 0.035), (s + 0.006, -0.058, z + 0.045), cell, LAMP_DIM)
    fb.label(((s0 + s1) / 2, -0.045, z0 + 0.06), min(s1 - s0 - 0.1, 0.7), min(s1 - s0 - 0.1, 0.7) / 4, (0, -1, 0), label)


def extinguisher(fb: SFB, s: float, z0: float) -> None:
    fb.box((s - 0.11, -0.05, z0 + 0.05), (s + 0.11, -0.01, z0 + 0.55), STRUCT)
    fb.cyl((s, -0.12, z0 + 0.1), (s, -0.12, z0 + 0.5), 0.065, PAINT_RED, seg=14)
    fb.cyl((s, -0.12, z0 + 0.19), (s, -0.12, z0 + 0.3), 0.068, RUBBER, seg=14)
    fb.cyl((s, -0.12, z0 + 0.5), (s, -0.12, z0 + 0.56), 0.02, TRIM, seg=8)
    fb.box((s - 0.1, -0.15, z0 + 0.28), (s + 0.1, -0.125, z0 + 0.3), TRIM)
    fb.label((s, -0.02, z0 + 0.7), 0.34, 0.085, (0, -1, 0), "tag_02")


def first_aid(fb: SFB, s: float, zc: float) -> None:
    fb.box((s - 0.2, -0.09, zc - 0.17), (s + 0.2, -0.02, zc + 0.17), IVORY)
    fb.box((s - 0.17, -0.098, zc - 0.14), (s + 0.17, -0.09, zc + 0.14), COMPOSITE)
    fb.label((s, -0.1, zc), 0.16, 0.16, (0, -1, 0), "icon_aid")
    fb.box((s + 0.14, -0.108, zc - 0.03), (s + 0.16, -0.098, zc + 0.03), TRIM)


def conduit_bundle(fb: SFB, s0: float, z0: float, z1: float, n: int = 4, r: float = 0.04) -> None:
    mats = [TRIM, STRUCT, TRIM, RUBBER]
    for k in range(n):
        s = s0 + k * (2 * r + 0.012)
        fb.cyl((s, -r - 0.03, z0), (s, -r - 0.03, z1), r, mats[k % 4], seg=12)
    zc = z0 + 0.3
    while zc < z1 - 0.1:
        fb.box((s0 - r - 0.012, -0.03, zc - 0.02), (s0 + (n - 1) * (2 * r + 0.012) + r + 0.012, -0.02 - 2 * r - 0.03, zc + 0.02), STRUCT)
        zc += 0.6


def info_screen(fb: SFB, sc: float, zc: float, w: float, h: float, tile: str) -> None:
    """A small wall display: a dark frame with a static screen face from the atlas."""
    fb.box((sc - w / 2 - 0.04, -0.055, zc - h / 2 - 0.04), (sc + w / 2 + 0.04, -0.008, zc + h / 2 + 0.04), TRIM)
    fb.box((sc - w / 2 - 0.01, -0.062, zc - h / 2 - 0.01), (sc + w / 2 + 0.01, -0.055, zc + h / 2 + 0.01), SL.DGLASS)
    fb.label((sc, -0.0625, zc), w, h, (0, -1, 0), tile)


def pictogram_plate(fb: SFB, sc: float, zc: float, size: float, tile: str) -> None:
    fb.box((sc - size / 2 - 0.02, -0.04, zc - size / 2 - 0.02), (sc + size / 2 + 0.02, -0.008, zc + size / 2 + 0.02), TRIM)
    fb.label((sc, -0.0405, zc), size, size, (0, -1, 0), tile)


# ------------------------------------------------------------------------------------------------------ ribs / rails / trays
def rib(fb: SFB, s: float, z0: float, z1: float, accent_dim: str, wide: bool = False, clamps=(0.34, 1.16, 2.35)) -> None:
    w = RIB_W * (1.5 if wide else 1.0)
    fb.box((s - w / 2, -RIB_T, z0), (s + w / 2, 0.0, z1), TRIM)
    fb.box((s - w / 2 + 0.03, -RIB_T - 0.012, z0 + 0.05), (s + w / 2 - 0.03, -RIB_T, z1 - 0.05), STRUCT)
    fb.lamp_box((s - 0.007, -RIB_T - 0.02, z0 + 0.5), (s + 0.007, -RIB_T - 0.012, z1 - 0.5), accent_dim, LAMP_DIM)
    for z in clamps:
        fb.box((s - w / 2 - 0.03, -RIB_T - 0.03, z - 0.06), (s + w / 2 + 0.03, 0.0, z + 0.06), TRIM)
        for dz in (-0.035, 0.035):
            for ds in (-w / 2, w / 2):
                bolt(fb, s + ds, z + dz, -RIB_T - 0.03, 0.01, 0.008)


def utility_rail(fb: SFB, s0: float, s1: float, accent_dim: str, z: float = 1.02) -> None:
    fb.cyl((s0, -0.095, z), (s1, -0.095, z), 0.02, TRIM, seg=10)
    s = s0 + 0.15
    while s < s1 - 0.05:
        fb.box((s - 0.015, -0.095, z - 0.035), (s + 0.015, -0.012, z + 0.035), TRIM)
        s += 0.85
    fb.lamp_box((s0 + 0.05, -0.052, z - 0.075), (s1 - 0.05, -0.048, z - 0.066), accent_dim, LAMP_DIM)


def cable_runs(fb: SFB, s0: float, s1: float, H: float, rng: random.Random, tray: bool = True, conduits: int = 2) -> None:
    """The service zone under the ceiling: a cable tray with cables and up to two conduits (z H-0.5 .. H-0.06)."""
    zt = H - 0.48
    if tray:
        fb.box((s0, -0.2, zt), (s1, -0.01, zt + 0.05), STRUCT)
        fb.box((s0, -0.2, zt), (s1, -0.195, zt + 0.15), STRUCT)
        fb.box((s0, -0.015, zt), (s1, -0.01, zt + 0.15), STRUCT)
        for k in range(4):
            fb.cyl((s0, -0.06 - 0.035 * k, zt + 0.08), (s1, -0.06 - 0.035 * k, zt + 0.08), 0.013, RUBBER, seg=6)
        s = s0 + 0.3
        while s < s1 - 0.1:
            fb.box((s - 0.02, -0.21, zt), (s + 0.02, 0.0, zt + 0.2), TRIM)
            s += 1.0
    if conduits >= 1:
        fb.cyl((s0, -0.075, H - 0.16), (s1, -0.075, H - 0.16), 0.042, TRIM, seg=12)
    if conduits >= 2:
        fb.cyl((s0, -0.09, H - 0.30), (s1, -0.09, H - 0.30), 0.028, STRUCT, seg=10)


def cornice(fb: SFB, s0: float, s1: float, H: float, cell: str = "white_warm") -> None:
    """The top of the wall: a small ledge with a warm lamp line in a trough that washes the ceiling edge."""
    fb.box((s0, -0.14, H - 0.06), (s1, 0.0, H), STRUCT)
    fb.box((s0, -0.14, H - 0.14), (s1, -0.10, H - 0.06), TRIM)
    fb.lamp_box((s0 + 0.04, -0.09, H - 0.075), (s1 - 0.04, -0.03, H - 0.066), cell, LAMP)


def plinth(fb: SFB, s0: float, s1: float, accent_dim: str) -> None:
    fb.box((s0, -0.045, 0.02), (s1, 0.0, 0.30), TRIM)
    fb.lamp_box((s0 + 0.08, -0.048, 0.135), (s1 - 0.08, -0.044, 0.15), accent_dim, LAMP_DIM)


# ------------------------------------------------------------------------------------------------------------ bay types
GENERIC_TAGS = ["tag_00", "tag_01", "tag_02", "tag_03", "tag_04", "tag_05", "tag_06", "tag_10", "tag_13", "eq_vent", "eq_breaker",
                "eq_maint", "eq_comm", "eq_hydrant", "eq_water"]


def bay(fb: SFB, kind: str, s0: float, s1: float, H: float, rng: random.Random, accent: str, accent_dim: str) -> None:
    """Fill one bay (clear width s0..s1, z 0.36 .. H - 0.5) with layered panels and one piece of equipment."""
    sc = (s0 + s1) / 2
    z_lo0, z_lo1 = 0.36, 1.05
    z_up0, z_up1 = 1.25, H - 0.55
    zm = (z_up0 + z_up1) / 2
    if kind == "plain":
        panel(fb, s0, s1, z_lo0, z_lo1)
        panel(fb, s0, s1, z_up0, zm - 0.02)
        panel(fb, s0, s1, zm + 0.02, z_up1)
        fb.label((sc, -0.05, zm), 0.5, 0.125, (0, -1, 0), "tag_13")
    elif kind == "vent":
        panel(fb, s0, s1, z_lo0, z_lo1)
        vent(fb, sc - 0.5, sc + 0.5, 0.5, 0.95, 6)
        panel(fb, s0, s1, z_up0, z_up1)
        vent(fb, sc - 0.45, sc + 0.45, zm - 0.1, zm + 0.35, 5, -0.03)
        fb.label((sc, -0.06, zm - 0.3), 0.5, 0.125, (0, -1, 0), "eq_vent")
    elif kind == "lockers":
        panel(fb, s0, s1, z_lo0, z_lo1 - 0.05, bolts=False)
        locker_bank(fb, s0 + 0.05, s1 - 0.05, 0.4, 1.06, 2, ["tag_09", "tag_00"], accent)
        panel(fb, s0, s1, z_up0, z_up1)
        fb.label((sc - 0.35, -0.06, zm), 0.18, 0.18, (0, -1, 0), "icon_eva")
        fb.label((sc + 0.25, -0.06, zm), 0.18, 0.18, (0, -1, 0), "icon_exit")
    elif kind == "panelboard":
        panel(fb, s0, s1, z_lo0, z_lo1)
        breaker_panel(fb, s0 + 0.12, s1 - 0.12, 1.3, min(2.3, z_up1 - 0.1), rng, "eq_breaker")
        fb.label((sc, -0.06, 0.75), 0.5, 0.125, (0, -1, 0), "tag_06")
    elif kind == "conduits":
        panel(fb, s0, s1, z_lo0, z_lo1)
        conduit_bundle(fb, s0 + 0.35, 0.34, z_up1, 5, 0.04)
        panel(fb, s0, s0 + 0.28, z_up0, z_up1, raised=False)
        panel(fb, s1 - 0.28, s1, z_up0, z_up1, raised=False)
        fb.label((s1 - 0.14, -0.06, 1.55), 0.24, 0.06, (0, -1, 0), "small_06")
    elif kind == "hatch":
        panel(fb, s0, s1, z_lo0, z_lo1)
        hatch(fb, sc, 0.78, 0.62, 0.62, "eq_maint")
        panel(fb, s0, s1, z_up0, z_up1)
        vent(fb, sc - 0.4, sc + 0.4, zm - 0.15, zm + 0.3, 5, -0.03)
    elif kind == "safety":
        panel(fb, s0, s1, z_lo0, z_lo1)
        extinguisher(fb, sc - 0.4, 0.42)
        first_aid(fb, sc + 0.32, 0.75)
        fb.label((sc + 0.32, -0.02, 1.08), 0.34, 0.085, (0, -1, 0), "tag_01")
        panel(fb, s0, s1, z_up0, z_up1)
        fb.label((sc, -0.06, zm), 0.5, 0.125, (0, -1, 0), "tag_10")
    elif kind == "hydrant":
        panel(fb, s0, s1, z_lo0, z_lo1)
        fb.box((sc - 0.3, -0.05, 0.42), (sc + 0.3, -0.008, 1.02), TRIM)
        fb.box((sc - 0.27, -0.09, 0.45), (sc + 0.27, -0.05, 0.99), PAINT_RED)
        fb.cyl((sc - 0.13, -0.12, 0.7), (sc - 0.13, -0.09, 0.7), 0.075, TRIM, seg=12)
        fb.cyl((sc + 0.13, -0.12, 0.7), (sc + 0.13, -0.09, 0.7), 0.075, TRIM, seg=12)
        fb.label((sc, -0.095, 0.92), 0.4, 0.07, (0, -1, 0), "eq_hydrant")
        panel(fb, s0, s1, z_up0, z_up1)
    elif kind == "screen":
        panel(fb, s0, s1, z_lo0, z_lo1)
        info_screen(fb, sc, zm + 0.05, 1.12, 0.63, rng.choice(["scr_news", "scr_sched", "scr_map"]))
        panel(fb, s0, s1, z_up0, zm - 0.5, raised=False)
        fb.label((sc, -0.05, z_up0 + 0.05), 0.5, 0.125, (0, -1, 0), "tag_13")
    else:
        panel(fb, s0, s1, z_lo0, z_lo1)
        panel(fb, s0, s1, z_up0, z_up1)
