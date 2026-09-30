"""ASN Aquila bridge v3: the side walls and the back wall.

A wall is composed, never flat: a structural core, layered dark-composite panels in brushed frames, structural ribs with
light lines, a utility handrail, cable trays and conduits, a lit cornice, and per bay a piece of equipment (lockers, vents,
hatches, breaker panels, extinguishers, first aid). The four station bays are recesses with a large curved live screen.
Wall-local frame: s along the wall (aft -> front), t outward (0 = inner face, negative = into the room), z up.
"""
from __future__ import annotations

import math
import os
import random
import sys

from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge3_lib as L  # noqa: E402
import bridge3_shell as SH  # noqa: E402
from bridge3_lib import FB, Parts, T, Rx, Ry, Rz, lerp, polar  # noqa: E402

RIB_W = 0.20
RIB_T = 0.13
Z_PLINTH = 0.32
Z_LOW0, Z_LOW1 = 0.37, 1.10
Z_UP0, Z_UP1 = 1.30, 3.42
Z_CORNICE = 4.02
DEPT_OF = {"comms": "command", "sensors": "science", "engineering": "engineering", "flight": "flight",
           "helm": "command", "ops": "command", "tactical": "security", "xo": "command", "captain": "command"}


# ------------------------------------------------------------------------------------------------------ small pieces
def bolt(fb: FB, s: float, z: float, t: float = 0.0, r: float = 0.009, h: float = 0.007) -> None:
    fb.cyl((s, t, z), (s, t - h, z), r, L.TRIM, seg=8)


def bolts_rect(fb: FB, s0: float, s1: float, z0: float, z1: float, t: float, inset: float = 0.05) -> None:
    for s in (s0 + inset, s1 - inset):
        for z in (z0 + inset, z1 - inset):
            bolt(fb, s, z, t)


def panel(fb: FB, s0: float, s1: float, z0: float, z1: float, mat: str = L.COMPOSITE, fw: float = 0.028, proud: float = 0.026,
          raised: bool = True, bolts: bool = True) -> None:
    """A layered wall panel: composite slab, brushed frame, raised centre field, four bolts."""
    fb.box((s0, -proud, z0), (s1, 0.0, z1), mat)
    tf = -proud - 0.012
    fb.box((s0, tf, z0), (s1, -proud, z0 + fw), L.TRIM)
    fb.box((s0, tf, z1 - fw), (s1, -proud, z1), L.TRIM)
    fb.box((s0, tf, z0 + fw), (s0 + fw, -proud, z1 - fw), L.TRIM)
    fb.box((s1 - fw, tf, z0 + fw), (s1, -proud, z1 - fw), L.TRIM)
    if raised and (s1 - s0) > 0.3 and (z1 - z0) > 0.3:
        fb.box((s0 + fw + 0.035, -proud - 0.007, z0 + fw + 0.035), (s1 - fw - 0.035, -proud, z1 - fw - 0.035), mat)
    if bolts:
        bolts_rect(fb, s0, s1, z0, z1, tf, 0.04)


def vent(fb: FB, s0: float, s1: float, z0: float, z1: float, slats: int = 8, t: float = 0.0) -> None:
    """A louvred grille: bezel, dark plenum, slanted slats."""
    fb.box((s0 - 0.03, t - 0.034, z0 - 0.03), (s1 + 0.03, t - 0.004, z1 + 0.03), L.TRIM)
    fb.box((s0, t - 0.036, z0), (s1, t - 0.02, z1), L.RUBBER)
    h = (z1 - z0) / slats
    for k in range(slats):
        zc = z0 + (k + 0.5) * h
        fb.cbox(((s0 + s1) / 2, t - 0.03, zc), (s1 - s0 - 0.01, 0.006, h * 1.25), L.TRIM, Rx(-32))


def hatch(fb: FB, sc: float, zc: float, w: float, h: float, label: str | None = None, dept: str = "command") -> None:
    """An access hatch: frame, door plate, recessed handle, four latches, an indicator lamp, an optional label above."""
    s0, s1, z0, z1 = sc - w / 2, sc + w / 2, zc - h / 2, zc + h / 2
    fb.box((s0 - 0.04, -0.05, z0 - 0.04), (s1 + 0.04, -0.008, z1 + 0.04), L.TRIM)
    fb.box((s0, -0.06, z0), (s1, -0.05, z1), L.COMPOSITE)
    fb.box((s0 + 0.05, -0.066, z0 + 0.05), (s1 - 0.05, -0.06, z1 - 0.05), L.STRUCT)
    fb.box((sc - 0.11, -0.085, zc - 0.03), (sc + 0.11, -0.06, zc + 0.03), L.TRIM)                      # handle
    fb.box((sc - 0.09, -0.078, zc - 0.018), (sc + 0.09, -0.06, zc + 0.018), L.RUBBER)
    for s in (s0 + 0.05, s1 - 0.05):
        for z in (z0 + 0.06, z1 - 0.06):
            fb.cyl((s, -0.066, z), (s, -0.082, z), 0.018, L.TRIM, seg=10)
    fb.lamp_box((s1 - 0.05, -0.068, zc + h * 0.25), (s1 - 0.03, -0.062, zc + h * 0.25 + 0.05), "green", L.LAMP)
    if label:
        fb.label((sc, -0.03, z1 + 0.10), min(w, 0.6), min(w, 0.6) / 4, (0, -1, 0), label)


def locker_bank(fb: FB, s0: float, s1: float, z0: float, z1: float, n: int, labels: list[str], dept: str) -> None:
    """A bank of tall equipment lockers: doors with recessed pulls, vent slots, small status lamps, labels."""
    w = (s1 - s0) / n
    fb.box((s0 - 0.03, -0.06, z0 - 0.03), (s1 + 0.03, -0.01, z1 + 0.03), L.TRIM)
    for k in range(n):
        a, b = s0 + k * w + 0.012, s0 + (k + 1) * w - 0.012
        fb.box((a, -0.075, z0), (b, -0.05, z1), L.COMPOSITE)
        fb.box((a + 0.03, -0.082, z0 + 0.03), (b - 0.03, -0.075, z1 - 0.03), L.STRUCT)
        fb.box((b - 0.09, -0.098, (z0 + z1) / 2 - 0.15), (b - 0.06, -0.075, (z0 + z1) / 2 + 0.15), L.TRIM)      # pull
        for j in range(3):
            fb.box((a + 0.06, -0.09, z1 - 0.14 - j * 0.035), (b - 0.06, -0.082, z1 - 0.12 - j * 0.035), L.RUBBER)  # vent slots
        fb.lamp_box((a + 0.05, -0.088, z0 + 0.12), (a + 0.09, -0.082, z0 + 0.14), dept if k % 2 == 0 else "green", L.LAMP)
        if k < len(labels):
            fb.label(((a + b) / 2, -0.08, z1 - 0.34), min(w - 0.1, 0.5), min(w - 0.1, 0.5) / 4, (0, -1, 0), labels[k])


def breaker_panel(fb: FB, s0: float, s1: float, z0: float, z1: float, rng: random.Random, label: str) -> None:
    """A breaker / circuit panel: dark board, rows of switches with lit indicators, a hazard-striped header."""
    fb.box((s0 - 0.03, -0.055, z0 - 0.03), (s1 + 0.03, -0.01, z1 + 0.03), L.TRIM)
    fb.box((s0, -0.06, z0), (s1, -0.04, z1), L.COMPOSITE)
    fb.label(((s0 + s1) / 2, -0.062, z1 - 0.06), (s1 - s0) - 0.1, 0.09, (0, -1, 0), "hazard")
    rows = max(2, int((z1 - z0 - 0.3) / 0.13))
    cols = max(3, int((s1 - s0 - 0.1) / 0.11))
    for r in range(rows):
        for cix in range(cols):
            s = s0 + 0.08 + cix * ((s1 - s0 - 0.16) / max(1, cols - 1))
            z = z0 + 0.1 + r * 0.13
            fb.box((s - 0.022, -0.075, z - 0.028), (s + 0.022, -0.06, z + 0.028), L.RUBBER)
            fb.box((s - 0.008, -0.088, z - 0.01), (s + 0.008, -0.075, z + 0.012 if rng.random() < 0.5 else z - 0.004), L.TRIM)
            cell = rng.choice(["green", "green", "green", "amber", "cyan", "ice"])
            fb.lamp_box((s - 0.006, -0.062, z + 0.035), (s + 0.006, -0.058, z + 0.045), cell, L.LAMP_DIM)
    fb.label(((s0 + s1) / 2, -0.045, z0 + 0.06), min(s1 - s0 - 0.1, 0.7), min(s1 - s0 - 0.1, 0.7) / 4, (0, -1, 0), label)


def extinguisher(fb: FB, s: float, z0: float) -> None:
    fb.box((s - 0.11, -0.05, z0 + 0.05), (s + 0.11, -0.01, z0 + 0.55), L.STRUCT)                   # cabinet back
    fb.cyl((s, -0.12, z0 + 0.1), (s, -0.12, z0 + 0.5), 0.065, L.STRUCT, seg=16)                    # the cylinder
    fb.cyl((s, -0.12, z0 + 0.19), (s, -0.12, z0 + 0.3), 0.068, L.RUBBER, seg=16)
    fb.lamp_cyl((s, -0.12, z0 + 0.4), (s, -0.12, z0 + 0.46), 0.069, "red", L.LAMP_DIM, seg=16)      # the red band
    fb.cyl((s, -0.12, z0 + 0.5), (s, -0.12, z0 + 0.56), 0.02, L.TRIM, seg=8)                        # valve
    fb.box((s - 0.1, -0.15, z0 + 0.28), (s + 0.1, -0.125, z0 + 0.3), L.TRIM)                       # strap
    fb.label((s, -0.02, z0 + 0.7), 0.34, 0.085, (0, -1, 0), "tag_02")


def first_aid(fb: FB, s: float, zc: float) -> None:
    fb.box((s - 0.2, -0.09, zc - 0.17), (s + 0.2, -0.02, zc + 0.17), L.IVORY)
    fb.box((s - 0.17, -0.098, zc - 0.14), (s + 0.17, -0.09, zc + 0.14), L.COMPOSITE)
    fb.label((s, -0.1, zc), 0.16, 0.16, (0, -1, 0), "icon_aid")
    fb.box((s + 0.14, -0.108, zc - 0.03), (s + 0.16, -0.098, zc + 0.03), L.TRIM)


def conduit_bundle(fb: FB, s0: float, z0: float, z1: float, n: int = 4, r: float = 0.04) -> None:
    """A vertical bundle of pipes with clamps every 0.6 m (a service riser)."""
    mats = [L.TRIM, L.STRUCT, L.TRIM, L.RUBBER]
    for k in range(n):
        s = s0 + k * (2 * r + 0.012)
        fb.cyl((s, -r - 0.03, z0), (s, -r - 0.03, z1), r, mats[k % 4], seg=14)
    zc = z0 + 0.3
    while zc < z1 - 0.1:
        fb.box((s0 - r - 0.012, -0.03, zc - 0.02), (s0 + (n - 1) * (2 * r + 0.012) + r + 0.012, -0.02 - 2 * r - 0.03, zc + 0.02), L.STRUCT)
        zc += 0.6


# --------------------------------------------------------------------------------------------------------- ribs / cornice
def rib(fb: FB, s: float, z0: float, z1: float, wide: bool = False) -> None:
    w = RIB_W * (1.5 if wide else 1.0)
    fb.box((s - w / 2, -RIB_T, z0), (s + w / 2, 0.0, z1), L.TRIM)
    fb.box((s - w / 2 + 0.03, -RIB_T - 0.012, z0 + 0.05), (s + w / 2 - 0.03, -RIB_T, z1 - 0.05), L.STRUCT)
    fb.lamp_box((s - 0.007, -RIB_T - 0.02, z0 + 0.5), (s + 0.007, -RIB_T - 0.012, z1 - 0.55), "cool_dim", L.LAMP_DIM)
    for z in (0.34, 1.16, 2.3, 3.44):                     # clamp plates
        fb.box((s - w / 2 - 0.03, -RIB_T - 0.03, z - 0.06), (s + w / 2 + 0.03, -0.0, z + 0.06), L.TRIM)
        for dz in (-0.035, 0.035):
            for ds in (-w / 2 + 0.0, w / 2 - 0.0):
                bolt(fb, s + ds, z + dz, -RIB_T - 0.03, 0.01, 0.008)


def cornice(fb: FB, L_wall: float) -> None:
    """The top of the wall: a deep ledge with an upstand, a warm strip in the trough that washes the ceiling edge."""
    fb.box((0.0, -0.32, Z_CORNICE), (L_wall, 0.0, Z_CORNICE + 0.06), L.STRUCT)                       # ledge
    fb.box((0.0, -0.32, Z_CORNICE + 0.06), (L_wall, -0.27, Z_CORNICE + 0.19), L.TRIM)                # upstand
    fb.box((0.0, -0.27, Z_CORNICE + 0.06), (L_wall, 0.0, Z_CORNICE + 0.10), L.COMPOSITE)             # trough floor
    fb.lamp_box((0.05, -0.24, Z_CORNICE + 0.10), (L_wall - 0.05, -0.10, Z_CORNICE + 0.115), "white_warm", L.LAMP_HOT)   # the strip
    fb.box((0.0, -0.10, Z_CORNICE + 0.06), (L_wall, 0.0, Z_CORNICE + 0.16), L.STRUCT)                # back lip


def utility_rail(fb: FB, s0: float, s1: float) -> None:
    """A handrail with a light channel under it, on brackets."""
    z = 1.02
    fb.cyl((s0, -0.095, z), (s1, -0.095, z), 0.02, L.TRIM, seg=12)
    k = 0
    s = s0 + 0.15
    while s < s1 - 0.05:
        fb.box((s - 0.015, -0.095, z - 0.035), (s + 0.015, -0.012, z + 0.035), L.TRIM)
        s += 0.85
    fb.lamp_box((s0 + 0.05, -0.052, z - 0.075), (s1 - 0.05, -0.048, z - 0.066), "cool_dim", L.LAMP_DIM)


def cable_runs(fb: FB, s0: float, s1: float, rng: random.Random) -> None:
    """Two conduits, a cable tray with cables, a lit line: the ceiling-side service zone of the wall (z 3.5 - 4.0)."""
    fb.cyl((s0, -0.075, 3.9), (s1, -0.075, 3.9), 0.045, L.TRIM, seg=16)
    fb.cyl((s0, -0.09, 3.78), (s1, -0.09, 3.78), 0.028, L.STRUCT, seg=12)
    fb.box((s0, -0.2, 3.5), (s1, -0.01, 3.56), L.STRUCT)                                          # tray floor
    fb.box((s0, -0.2, 3.5), (s1, -0.195, 3.66), L.STRUCT)
    fb.box((s0, -0.015, 3.5), (s1, -0.01, 3.66), L.STRUCT)
    for k in range(5):
        fb.cyl((s0, -0.06 - 0.028 * k, 3.6), (s1, -0.06 - 0.028 * k, 3.6), 0.012, L.RUBBER, seg=8)
    s = s0 + 0.3
    while s < s1 - 0.1:
        fb.box((s - 0.02, -0.21, 3.5), (s + 0.02, -0.0, 3.7), L.TRIM)      # tray brackets
        s += 1.0


# ------------------------------------------------------------------------------------------------------------ bay types
def bay_module(fb: FB, kind: str, s0: float, s1: float, rng: random.Random, dept: str, tag: int) -> None:
    """Fill one plain bay (clear width s0..s1) with layered panels and one piece of equipment."""
    sc = (s0 + s1) / 2
    if kind == "plain":
        panel(fb, s0, s1, Z_LOW0, Z_LOW1)
        panel(fb, s0, s1, Z_UP0, 2.30)
        panel(fb, s0, s1, 2.34, Z_UP1)
        fb.label((sc, -0.05, 2.05), 0.5, 0.125, (0, -1, 0), "tag_13")
    elif kind == "vent":
        panel(fb, s0, s1, Z_LOW0, Z_LOW1)
        vent(fb, sc - 0.5, sc + 0.5, 0.5, 0.95, 7)
        panel(fb, s0, s1, Z_UP0, Z_UP1)
        vent(fb, sc - 0.45, sc + 0.45, 2.55, 3.05, 6, -0.03)
        fb.label((sc, -0.06, 1.75), 0.5, 0.125, (0, -1, 0), "tag_07")
    elif kind == "lockers":
        panel(fb, s0, s1, Z_LOW0, Z_LOW1 - 0.05, bolts=False)
        locker_bank(fb, s0 + 0.05, s1 - 0.05, 0.4, 1.06, 2, ["tag_09", "tag_00"], dept)
        panel(fb, s0, s1, Z_UP0, Z_UP1)
        fb.label((sc - 0.35, -0.06, 1.7), 0.18, 0.18, (0, -1, 0), "icon_eva")
        fb.label((sc + 0.25, -0.06, 1.7), 0.18, 0.18, (0, -1, 0), "icon_exit")
    elif kind == "panelboard":
        panel(fb, s0, s1, Z_LOW0, Z_LOW1)
        breaker_panel(fb, s0 + 0.12, s1 - 0.12, 1.36, 2.35, rng, "tag_12")
        panel(fb, s0, s1, 2.42, Z_UP1)
        fb.label((sc, -0.06, 0.75), 0.5, 0.125, (0, -1, 0), "tag_06")
    elif kind == "conduits":
        panel(fb, s0, s1, Z_LOW0, Z_LOW1)
        conduit_bundle(fb, s0 + 0.35, 0.34, 3.45, 5, 0.04)
        panel(fb, s0, s0 + 0.28, Z_UP0, Z_UP1, raised=False)
        panel(fb, s1 - 0.28, s1, Z_UP0, Z_UP1, raised=False)
        fb.label((s1 - 0.14, -0.06, 1.55), 0.24, 0.06, (0, -1, 0), "small_00")
    elif kind == "hatch":
        panel(fb, s0, s1, Z_LOW0, Z_LOW1)
        hatch(fb, sc, 0.78, 0.62, 0.62, "tag_11", dept)
        panel(fb, s0, s1, Z_UP0, Z_UP1)
        vent(fb, sc - 0.4, sc + 0.4, 2.05, 2.5, 6, -0.03)
    elif kind == "safety":
        panel(fb, s0, s1, Z_LOW0, Z_LOW1)
        extinguisher(fb, sc - 0.4, 0.42)
        first_aid(fb, sc + 0.32, 0.75)
        fb.label((sc + 0.32, -0.02, 1.08), 0.34, 0.085, (0, -1, 0), "tag_01")
        panel(fb, s0, s1, Z_UP0, Z_UP1)
        fb.label((sc, -0.06, 1.75), 0.5, 0.125, (0, -1, 0), "tag_10")
    else:
        panel(fb, s0, s1, Z_LOW0, Z_LOW1)
        panel(fb, s0, s1, Z_UP0, Z_UP1)


# ----------------------------------------------------------------------------------------------------- station bay (wall)
def station_bay(b: Parts, wall: SH.Wall, sc: float, station: dict, dept: str, slot: str) -> dict:
    """A recess in the wall with a large concave live screen, a lit surround, a task light and the station plate.
    Returns geometry info for the manifest (screen size, arc)."""
    fb, fine, em = b.body, b.fine, b.emit
    half = 1.50                                   # half width of the opening
    z_lo, z_hi = 0.98, 2.92
    core_t = 0.30
    # surround: brushed frame around the opening, a dept-colour lamp line on its inner edge
    fb.box((sc - half - 0.16, -0.075, z_lo - 0.16), (sc + half + 0.16, 0.0, z_lo), L.TRIM)
    fb.box((sc - half - 0.16, -0.075, z_hi), (sc + half + 0.16, 0.0, z_hi + 0.16), L.TRIM)
    fb.box((sc - half - 0.16, -0.075, z_lo), (sc - half, 0.0, z_hi), L.TRIM)
    fb.box((sc + half, -0.075, z_lo), (sc + half + 0.16, 0.0, z_hi), L.TRIM)
    fb.box((sc - half - 0.16, -0.098, z_hi + 0.16), (sc + half + 0.16, -0.075, z_hi + 0.19), L.STRUCT)
    cell = dept
    em.lamp_box((sc - half + 0.02, -0.004, z_hi - 0.03), (sc + half - 0.02, 0.006, z_hi - 0.014), cell, L.LAMP)
    em.lamp_box((sc - half + 0.02, -0.004, z_lo + 0.014), (sc + half - 0.02, 0.006, z_lo + 0.03), cell, L.LAMP)
    # the curved screen: R = 3.0, 2.4 m chord, centre recessed 0.27 (the alcove's back is the wall's outer skin)
    R = 3.0
    phi = math.degrees(math.asin(1.2 / R))
    cx, ct = sc, 0.27 - R
    z0s, z1s = 1.18, 2.68
    b.emit.screen_arc(cx, ct, R, 90 - phi, 90 + phi, z0s, z1s, slot, inward=True, seg=28)
    # bezel round the screen: brushed rails above and below (swept on the same arc), dark stiles at the ends
    rail = [(-0.02, 0.0), (0.07, 0.0), (0.07, 0.05), (-0.02, 0.05)]
    fb.arc_sweep(rail, cx, ct, R, 90 - phi - 3.2, 90 + phi + 3.2, L.TRIM, seg=30, z0=z1s)
    fb.arc_sweep(rail, cx, ct, R, 90 - phi - 3.2, 90 + phi + 3.2, L.TRIM, seg=30, z0=z0s - 0.05)
    for a in (90 - phi - 1.6, 90 + phi + 1.6):
        fb.arc_sweep([(-0.02, 0.0), (0.07, 0.0), (0.07, 0.0 + z1s - z0s + 0.1), (-0.02, z1s - z0s + 0.1)], cx, ct, R, a - 1.6, a + 1.6,
                     L.STRUCT, seg=2, z0=z0s - 0.05)
    # task light bar above, plate below
    em.lamp_box((sc - 0.9, -0.04, z_hi + 0.19), (sc + 0.9, -0.03, z_hi + 0.205), "white_warm", L.LAMP)
    fb.label((sc, -0.079, z_hi + 0.31), 0.9, 0.1125, (0, -1, 0), {"comms": "st_comms", "sensors": "st_sensors", "engineering": "st_engineering",
                                                               "flight": "st_flight"}[station["id"]])
    return {"screen": slot, "size_m": [2 * 1.2 * (1.0), z1s - z0s], "radius": R, "arc_deg": 2 * phi}


# ================================================================================================================== build
def build_side_wall(c: SH.Ctx, side: int, name: str, stations: list[dict]):
    """One side wall (side +1 starboard, -1 port) as a single mesh. Origin = bridge origin, in layout coordinates."""
    wall = c.walls[side]
    b = Parts(bevel=0.006, fine_bevel=0.003)
    fb, em = b.body, b.emit
    rng = random.Random(41 if side > 0 else 43)
    Lw = wall.L
    P = c.D["walls"].get("bay_pitch", 1.7)
    nb = int(round(Lw / P))
    Pe = Lw / nb
    info: dict = {"screens": []}
    bay_first: dict[int, dict] = {}                       # first module -> station (a station bay covers two modules)
    covered: set[int] = set()
    skip_ribs = set()
    for st in stations:
        if st.get("bay") and st["bay"]["wall"] == ("starboard" if side > 0 else "port"):
            k0 = int(round(st["bay"]["s"] / Pe)) - 1
            bay_first[k0] = st
            covered.update((k0, k0 + 1))
            skip_ribs.add(k0 + 1)                          # no rib in the middle of a station bay
    with fb.at(wall.matrix()), em.at(wall.matrix()), b.fine.at(wall.matrix()):
        # ---- structural core: full height except in the station recesses
        cuts = []
        for k0 in bay_first:
            sc = (k0 + 1) * Pe
            cuts.append((sc - 1.5, sc + 1.5))
        segs = []
        cur = 0.0
        for (a, bnd) in sorted(cuts):
            segs.append((cur, a))
            cur = bnd
        segs.append((cur, Lw))
        for (a, bnd) in segs:
            fb.box((a, 0.0, 0.0), (bnd, 0.30, c.CEIL), L.STRUCT)
        for (a, bnd) in cuts:
            fb.box((a, 0.0, 0.0), (bnd, 0.30, 0.98), L.STRUCT)
            fb.box((a, 0.0, 2.92), (bnd, 0.30, c.CEIL), L.STRUCT)
        fb.box((0.0, 0.30, 0.0), (Lw, 0.34, c.CEIL), L.COMPOSITE)                                    # outer skin
        # ---- plinth and its light channel
        for k in range(nb):
            s0, s1 = k * Pe + RIB_W / 2 + 0.02, (k + 1) * Pe - RIB_W / 2 - 0.02
            fb.box((s0 if k not in skip_ribs else k * Pe, -0.045, 0.02), (s1 if (k + 1) not in skip_ribs else (k + 1) * Pe, 0.0, Z_PLINTH), L.TRIM)
            em.lamp_box((s0 + 0.1, -0.048, 0.135), (s1 - 0.1, -0.044, 0.15), "cool_dim", L.LAMP_DIM)
        # ---- ribs
        for k in range(nb + 1):
            if k in skip_ribs:
                continue
            rib(fb, k * Pe, 0.0, Z_CORNICE, wide=(k in (0, nb)))
        # ---- bays
        plain = ["lockers", "panelboard", "conduits", "safety", "hatch", "vent", "plain"]
        pattern = {1: {0: "lockers", 1: "panelboard", 6: "hatch", 7: "safety"},
                   -1: {0: "hatch", 1: "lockers", 6: "panelboard", 7: "conduits"}}[side]
        for k in range(nb):
            s0, s1 = k * Pe + RIB_W / 2 + 0.03, (k + 1) * Pe - RIB_W / 2 - 0.03
            if k in covered:
                continue
            bay_module(fb, pattern.get(k, "plain"), s0, s1, rng, "command", k)
        # ---- the station recesses (screens go to the emissive part)
        for k0, st in bay_first.items():
            sc = (k0 + 1) * Pe
            slot = f"SCREEN_{st['id']}_1"
            dept = DEPT_OF.get(st["id"], "command")
            # panels beside and below the recess
            info["screens"].append(station_bay(b, wall, sc, st, dept, slot))
            for (a, bnd) in ((sc - Pe - RIB_W / 2 + 0.05, sc - 1.66), (sc + 1.66, sc + Pe + RIB_W / 2 - 0.05)):
                if bnd - a > 0.15:
                    panel(fb, a, bnd, Z_LOW0, 3.42, raised=False)
            panel(fb, sc - 1.5, sc + 1.5, Z_LOW0, 0.94, bolts=True)
        # ---- utility rail (not across the station recesses) and the service zone
        s = 0.2
        spans = []
        for (a, bnd) in sorted(cuts):
            spans.append((s, a - 0.2))
            s = bnd + 0.2
        spans.append((s, Lw - 0.2))
        for (a, bnd) in spans:
            if bnd - a > 0.5:
                utility_rail(fb, a, bnd)
        cable_runs(fb, 0.2, Lw - 0.2, rng)
        cornice(fb, Lw)
        fb.label(((nb - 0.5) * Pe, -0.055, 3.3), 1.0, 0.125, (0, -1, 0), "deck_bridge")
        fb.label((0.5 * Pe, -0.055, 3.3), 1.0, 0.125, (0, -1, 0), "deck_bridge")
    obj = b.build(name)
    return obj, info
