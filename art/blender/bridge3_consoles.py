"""ASN Aquila bridge v3: the consoles.

Every console is a swept "fan" wrapped round its officer: a cross-section (radius, height) swept about the officer's vertical
axis, so the work surface curves towards the hands and the controls sit radially. Officer at the origin on the floor,
facing +X, y to the right. The surface is a shallow cone (`Fan.zs`), the controls are placed in polar coordinates
(`Fan.frame`). Shells are glossy ivory composite and gunmetal, the work surface is dark glass with a live touch screen
(SCREEN_<station>_<n>), the edges glow in the department colour. Hover panels (translucent, separate mesh) sit above.
"""
from __future__ import annotations

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge3_controls as K  # noqa: E402
import bridge3_holo as HO  # noqa: E402
import bridge3_lib as L  # noqa: E402
from bridge3_lib import FB, Parts, Rx, Ry, Rz, T, frame, lerp, polar  # noqa: E402

DEPT = {"helm": "command", "ops": "command", "comms": "command", "sensors": "science", "engineering": "engineering",
        "flight": "flight", "tactical": "security"}
PLATE = {"helm": "st_helm", "ops": "st_ops", "comms": "st_comms", "sensors": "st_sensors", "engineering": "st_engineering",
         "flight": "st_flight", "tactical": "st_tactical"}


class Fan:
    """The geometry of a fan console: angle range, radii, the conical work surface."""

    def __init__(self, a: float = 58.0, r0: float = 0.50, r1: float = 1.28, z0: float = 0.80, slope: float = 0.22) -> None:
        self.a, self.r0, self.r1, self.z0, self.slope = a, r0, r1, z0, slope
        self.pitch = math.degrees(math.atan(slope))

    def zs(self, r: float) -> float:
        return self.z0 + (r - self.r0) * self.slope

    def pos(self, r: float, th: float, lift: float = 0.0):
        return (r * math.cos(math.radians(th)), r * math.sin(math.radians(th)), self.zs(r) + lift)

    def frame(self, r: float, th: float, lift: float = 0.0):
        """Local frame on the surface at polar (r, th): x uphill (radially out), y to the officer's right, z the normal."""
        x, y, z = self.pos(r, th, lift)
        return frame(x, y, z, yaw=th, pitch=self.pitch)


def sweep(fb: FB, prof, a0: float, a1: float, mat: str, seg: int = 20):
    return fb.arc_sweep(prof, 0.0, 0.0, 0.0, a0, a1, mat, seg=seg, z0=0.0)


def vent_back(fb: FB, y0: float, y1: float, z0: float, z1: float, slats: int = 6) -> None:
    """A louvred vent on the back of a console (local x is the outward normal)."""
    fb.box((0.0, y0 - 0.02, z0 - 0.02), (0.018, y1 + 0.02, z1 + 0.02), L.TRIM)
    fb.box((-0.004, y0, z0), (0.012, y1, z1), L.RUBBER)
    h = (z1 - z0) / slats
    for k in range(slats):
        fb.cbox((0.014, (y0 + y1) / 2, z0 + (k + 0.5) * h), (0.006, y1 - y0 - 0.004, h * 1.2), L.TRIM, Ry(30))


def fan_body(b: Parts, F: Fan, dept: str, station: str, spine: bool = True) -> None:
    """Shells, lip, glass, kick base, cheeks, lamps and the back of a fan console."""
    fb, fine, em = b.body, b.fine, b.emit
    a, r0, r1, zs = F.a, F.r0, F.r1, F.zs
    dim = dept + "_dim"
    # kick base and the recessed knee wall
    sweep(fb, [(0.62, 0.0), (r1 + 0.03, 0.0), (r1 + 0.03, 0.06), (0.62, 0.06)], -a, a, L.STRUCT, 24)
    sweep(fb, [(0.62, 0.06), (0.72, 0.06), (0.72, 0.66), (0.62, 0.64)], -a, a, L.COMPOSITE, 24)
    # overhanging lip: brushed edge over a softly curved underside
    sweep(fb, [(r0, F.z0 - 0.06), (r0 + 0.005, F.z0 - 0.02), (0.60, zs(0.60) - 0.012), (0.72, zs(0.72) - 0.012), (0.72, 0.64), (0.62, 0.64),
               (0.54, 0.70)], -a, a, L.TRIM, 24)
    # body under the glass: dark composite; the rear shell in gunmetal with ivory armour plates on top
    sweep(fb, [(0.72, 0.06), (1.0, 0.06), (1.0, zs(1.0) - 0.012), (0.72, zs(0.72) - 0.012)], -a, a, L.COMPOSITE, 24)
    sweep(fb, [(1.0, 0.06), (r1, 0.06), (r1, zs(r1) + 0.02), (1.0, zs(1.0) - 0.012)], -a, a, L.STRUCT, 24)
    for k0 in range(-3, 4):                                     # ivory armour plates on the rear top, with gaps between them
        th0 = k0 * (2 * a) / 7.0 - (a / 7.0) + 1.2
        th1 = th0 + (2 * a) / 7.0 - 2.4
        if th0 < -a + 1.0 or th1 > a - 1.0:
            continue
        sweep(fb, [(1.0, zs(1.0) - 0.004), (r1 + 0.006, zs(r1) + 0.024), (r1 + 0.006, zs(r1) + 0.036), (1.0, zs(1.0) + 0.008)], th0, th1,
              L.IVORY if k0 % 2 == 0 else L.COMPOSITE, 6)
    # the glass work surface (the whole fan is dark glass between the lip and the spine)
    sweep(fb, [(r0 + 0.012, zs(r0 + 0.012) - 0.002), (1.06, zs(1.06) - 0.002), (1.06, zs(1.06) + 0.0015), (r0 + 0.012, zs(r0 + 0.012) + 0.0015)],
          -a + 1.0, a - 1.0, L.DGLASS, 26)
    if spine:
        # the raised spine along the back: ivory cover, a dark emitter slot with a crown of lenses
        sweep(fb, [(1.06, zs(1.06) + 0.0015), (1.10, zs(1.10) + 0.10), (r1 - 0.02, zs(r1) + 0.13), (r1, zs(r1) + 0.02)], -a + 1.0, a - 1.0, L.IVORY, 26)
        sweep(fb, [(1.10, zs(1.10) + 0.10), (1.18, zs(1.18) + 0.115), (1.18, zs(1.18) + 0.122), (1.10, zs(1.10) + 0.107)], -a + 4.0, a - 4.0, L.STRUCT, 26)
        for k in range(-7, 8):
            th = k * (a - 8.0) / 7.0
            x, y, z = F.pos(1.14, th, 0.113)
            em.lamp_cyl((x, y, z), (x, y, z + 0.006), 0.0065, "cyan" if k % 2 else "white", L.LAMP_DIM, seg=8)
    # cheek plates at both ends of the fan: dark composite with an ivory rim, a recessed vent panel and a lit edge
    for sd in (-1, 1):
        th = sd * a
        with b.at(Rz(th)):
            pk = [(0.50, 0.68), (0.50, F.z0 + 0.03), (0.80, zs(0.80) + 0.075), (1.05, zs(1.05) + 0.095), (r1, zs(r1) + 0.06), (r1, 0.06), (0.70, 0.06)]
            fb.extrude_y(pk, -0.026, 0.026, L.COMPOSITE)
            # ivory rim along the top edge (a thin strip, a little proud of the plate) with a brass line on it
            for (xa, za), (xb, zb) in zip(pk[1:5], pk[2:6]):
                ang = math.degrees(math.atan2(zb - za, xb - xa))
                ln = math.hypot(xb - xa, zb - za)
                fb.cbox(((xa + xb) / 2, 0.0, (za + zb) / 2 - 0.012), (ln, 0.056, 0.026), L.IVORY, Ry(-ang))
                em.cbox(((xa + xb) / 2, 0.0, (za + zb) / 2 + 0.0015), (ln, 0.010, 0.004), L.BRASS, Ry(-ang))
                em.lamp_cbox(((xa + xb) / 2, 0.0, (za + zb) / 2 - 0.028), (ln, 0.06, 0.005), dept, L.LAMP, Ry(-ang))
            # a recessed vent panel on the outer face (towards the outside of the console) and bolts
            for side in (-1, 1):
                fb.box((0.80, side * 0.026, 0.28), (1.16, side * 0.031, 0.68), L.STRUCT)
                for kk in range(6):
                    fb.box((0.83, side * 0.031, 0.31 + kk * 0.058), (1.13, side * 0.035, 0.335 + kk * 0.058), L.RUBBER)
                for xx in (0.83, 1.13):
                    for zz in (0.30, 0.66):
                        fb.cyl((xx, side * 0.026, zz), (xx, side * 0.034, zz), 0.008, L.TRIM, seg=8)
    # brass: a thin line along the lip's edge and along the foot of the spine; the silkscreen of the glass; the status ticker on the spine's front
    sweep(em, [(r0 - 0.004, F.z0 - 0.034), (r0 + 0.001, F.z0 - 0.034), (r0 + 0.001, F.z0 - 0.026), (r0 - 0.004, F.z0 - 0.026)], -a + 3, a - 3, L.BRASS, 22)
    if spine:
        sweep(em, [(1.058, zs(1.058) + 0.003), (1.064, zs(1.064) + 0.003), (1.064, zs(1.064) + 0.007), (1.058, zs(1.058) + 0.007)], -a + 2, a - 2, L.BRASS, 26)
        em.decor_polar(F, "fan_" + dept, 0.52, 1.06, -(a - 1.5), a - 1.5, lift=0.0026, seg=26, tile_a=58.0, tile_r=(0.50, 1.08))
        em.decor_strip((1.0688, zs(1.06) + 0.0251), (1.0912, zs(1.06) + 0.0852), -27.0, 27.0, "ticker", seg=18, lift_out=0.002)
    # lamps: under the lip (light on the knees), along the lip, under the base
    em.lamp_arc([(0.545, 0.0), (0.60, 0.0), (0.60, 0.006), (0.545, 0.006)], 0, 0, 0, -a + 4, a - 4, dim, L.LAMP_DIM, seg=22, z0=0.658)
    em.lamp_arc([(r0 - 0.003, 0.0), (r0 + 0.002, 0.0), (r0 + 0.002, 0.008), (r0 - 0.003, 0.008)], 0, 0, 0, -a + 3, a - 3, dept, L.LAMP, seg=26,
                z0=F.z0 - 0.045)
    em.lamp_arc([(r1 + 0.031, 0.0), (r1 + 0.034, 0.0), (r1 + 0.034, 0.012), (r1 + 0.031, 0.012)], 0, 0, 0, -a + 3, a - 3, dim, L.LAMP_DIM, seg=22, z0=0.02)
    # the back of the console (the Captain's side): vents, a plate with the station name, cable trays
    for th in (-34.0, 0.0, 34.0):
        c, s = math.cos(math.radians(th)), math.sin(math.radians(th))
        with fb.at(T(r1 * c, r1 * s, 0) @ Rz(th)):
            vent_back(fb, -0.24, 0.24, 0.28, 0.62, 6)
            fb.label((0.012, 0.0, 0.83 if abs(th) < 1 else 0.79), 0.5 if abs(th) < 1 else 0.3, 0.0625 if abs(th) < 1 else 0.05, (1, 0, 0),
                     PLATE[station] if abs(th) < 1 else "small_00")
    for th in (-24.0, 24.0):                                       # brass grab handles on the back, where the Captain's hand falls
        c, s = math.cos(math.radians(th)), math.sin(math.radians(th))
        with em.at(T((r1 + 0.03) * c, (r1 + 0.03) * s, 0) @ Rz(th)):
            em.cyl((0.062, -0.11, 0.70), (0.062, 0.11, 0.70), 0.0105, L.BRASS, seg=8)
            for yy in (-0.10, 0.10):
                em.cyl((0.0, yy, 0.70), (0.062, yy, 0.70), 0.0075, L.BRASS, seg=6)
    for th in (-17.0, 17.0):
        c, s = math.cos(math.radians(th)), math.sin(math.radians(th))
        with fb.at(T((r1 + 0.03) * c, (r1 + 0.03) * s, 0) @ Rz(th)):
            fb.cyl((0.0, -0.20, 0.10), (0.0, -0.20, 0.55), 0.022, L.RUBBER, seg=10)
            fb.cyl((0.0, -0.16, 0.10), (0.0, -0.16, 0.55), 0.016, L.TRIM, seg=10)
    # the wrist rest: a padded rest whose top (0.872 m) is where the officers' hands lie
    fine.arc_sweep([(0.53, F.zs(0.53) - 0.004), (0.61, F.zs(0.61) - 0.004), (0.61, 0.868), (0.575, 0.874), (0.53, 0.868)], 0, 0, 0,
                   -30, 30, L.RUBBER, seg=16)


def touch_screen(b: Parts, F: Fan, slot: str, r: float, th: float, w: float, aspect: float = 1.6, lift: float = 0.0032) -> dict:
    """A live touch screen lying on the work surface at polar (r, th), image up = uphill; width w (across)."""
    h = w / aspect
    with b.emit.at(F.frame(r, th, lift)):
        b.emit.screen((0, 0, 0), w, h, slot, (0, 0, 1), up=(1, 0, 0))
    with b.fine.at(F.frame(r, th, 0.0)):                       # a thin brushed bezel round the glass, proud of the surface
        b.fine.box((-h / 2 - 0.012, -w / 2 - 0.012, 0.0), (-h / 2, w / 2 + 0.012, 0.006), L.STRUCT)
        b.fine.box((h / 2, -w / 2 - 0.012, 0.0), (h / 2 + 0.012, w / 2 + 0.012, 0.006), L.STRUCT)
        b.fine.box((-h / 2, -w / 2 - 0.012, 0.0), (h / 2, -w / 2, 0.006), L.STRUCT)
        b.fine.box((-h / 2, w / 2, 0.0), (h / 2, w / 2 + 0.012, 0.006), L.STRUCT)
    return {"screen": slot, "size_m": [round(w, 3), round(h, 3)], "surface": "glass"}


def hover_mounts(b: Parts, F: Fan, kind: str, dept: str) -> None:
    """The physical emitters under the hover panels: a puck on the work surface, or two slim masts on the back of the console."""
    fb, fine, em = b.body, b.fine, b.emit
    for n, (r, th, zc, w, asp, mount) in HO.PANELS.get(kind, {}).items():
        if mount == "puck":
            x, y, z = F.pos(r, th)
            fb.cyl((x, y, z - 0.004), (x, y, z + 0.016), 0.060, L.STRUCT, seg=28, r2=0.052)                        # the emitter pad
            em.cyl((x, y, z + 0.0158), (x, y, z + 0.0185), 0.056, L.BRASS, seg=28)                                  # brass collar
            fb.cyl((x, y, z + 0.0165), (x, y, z + 0.0245), 0.040, L.DGLASS, seg=24, r2=0.034)                      # the lens
            em.lamp_cyl((x, y, z + 0.0243), (x, y, z + 0.0256), 0.022, dept, L.LAMP, seg=20)
            em.lamp_arc([(0.046, 0.0), (0.050, 0.0), (0.050, 0.0035), (0.046, 0.0035)], x, y, 0.0, 0, 360, dept + "_dim", L.LAMP_DIM, seg=28,
                        z0=z + 0.0185, loop=True)
            em.decor((x, y, z + 0.0034), 0.46, 0.22, (0, 0, 1), "glow_" + dept, up=(math.cos(math.radians(th)), math.sin(math.radians(th)), 0))     # the light pool
        else:                                                    # a projector turret on the spine: the panel floats above it, the beams show where it comes from
            x, y, z = F.pos(1.18, 0.0)
            zb = z + 0.122
            fb.cyl((x, y, zb - 0.02), (x, y, zb + 0.052), 0.046, L.STRUCT, seg=28, r2=0.034)
            em.cyl((x, y, zb + 0.0505), (x, y, zb + 0.0535), 0.038, L.BRASS, seg=28)
            fb.cyl((x, y, zb + 0.052), (x, y, zb + 0.076), 0.027, L.DGLASS, seg=24, r2=0.021)
            em.lamp_cyl((x, y, zb + 0.0755), (x, y, zb + 0.0775), 0.0145, dept, L.LAMP, seg=16)
            em.lamp_arc([(0.040, 0.0), (0.0445, 0.0), (0.0445, 0.0035), (0.040, 0.0035)], x, y, 0.0, 0, 360, dept + "_dim", L.LAMP_DIM, seg=28, z0=zb + 0.0, loop=True)


# ------------------------------------------------------------------------------------------------------ console types
def build_console(kind: str, name: str, station: dict, rng_seed: int = 5):
    """kind: helm, ops, comms, sensors, engineering, flight, tactical. Returns (object, screens-info)."""
    sid = kind
    dept = DEPT[kind]
    rng = random.Random(rng_seed + sum(map(ord, kind)))
    b = Parts(bevel=0.009, fine_bevel=0.0035)
    if kind == "tactical":
        F = Fan(a=64.0, r0=0.46, r1=0.98, z0=1.0, slope=0.24)
    elif kind in ("helm", "ops"):
        F = Fan(a=58.0, r0=0.50, r1=1.28, z0=0.80, slope=0.22)
    else:
        F = Fan(a=52.0, r0=0.50, r1=1.20, z0=0.80, slope=0.22)
    fb, fine, em = b.body, b.fine, b.emit
    info = {"screens": [], "hands": station.get("hands", {}), "fan": {"a": F.a, "r0": F.r0, "r1": F.r1, "z0": F.z0, "slope": F.slope}}
    if kind != "tactical":
        fan_body(b, F, dept, kind)
    else:
        tactical_body(b, F, dept)
    hover_mounts(b, F, kind, dept)
    # ---- controls (surface frames)
    fn = {"helm": helm_controls, "ops": ops_controls, "comms": comms_controls, "sensors": sensors_controls,
          "engineering": engineering_controls, "flight": flight_controls, "tactical": tactical_controls}[kind]
    info["screens"] += fn(b, F, dept, rng)
    return b.build(name, uv_meter=0.5), info


def helm_controls(b: Parts, F: Fan, dept: str, rng: random.Random) -> list:
    fb, fine, em = b.body, b.fine, b.emit
    scr = [touch_screen(b, F, "SCREEN_helm_4", 0.86, 0.0, 0.50)]
    # the two thrust levers where the hands rest (r 0.58, +-15 deg): translation on the left, main thrust on the right
    for th, cell, lean in ((-15.0, "command", -0.08), (15.0, "flight", -0.08)):
        with b.at(F.frame(0.66, th)):
            K.thrust_lever(fb, fine, em, 0.0, 0.0, cell=cell, lean=lean)
    # attitude trackball between them, mode keys and status lamps
    with b.at(F.frame(0.6, 0.0)):
        K.trackball(fine, em, 0.0, 0.0)
    with b.at(F.frame(0.70, 0.0)):
        for k in range(-3, 4):
            K.key(fine, em, 0.0, k * 0.036, "cyan" if k else "amber", 0.024)
    # wing decks: key clusters, slider banks, dials
    for sd in (-1, 1):
        with b.at(F.frame(0.78, sd * 40.0)):
            K.key_grid(fine, em, 0.0, -0.10, 3, 6, 0.040, rng)
        with b.at(F.frame(0.98, sd * 42.0)):
            K.slider_bank(fine, em, 0.0, -0.09, 4, 0.06, 0.13, rng)
        with b.at(F.frame(0.70, sd * 52.0)):
            K.dial(fine, em, 0.0, 0.0, cell="command")
            K.dial(fine, em, 0.09, 0.0, 0.022, cell="flight")
    return scr


def ops_controls(b: Parts, F: Fan, dept: str, rng: random.Random) -> list:
    fb, fine, em = b.body, b.fine, b.emit
    scr = [touch_screen(b, F, "SCREEN_ops_4", 0.88, 0.0, 0.64)]
    with b.at(F.frame(0.62, -13.0)):
        K.dial(fine, em, 0.0, 0.0, 0.03, cell="command")
    with b.at(F.frame(0.62, 13.0)):
        K.dial(fine, em, 0.0, 0.0, 0.03, cell="command")
    for sd in (-1, 1):
        with b.at(F.frame(0.74, sd * 38.0)):
            K.slider_bank(fine, em, 0.0, -0.15, 6, 0.06, 0.16, rng, cells=("cyan", "command"))
        with b.at(F.frame(0.98, sd * 40.0)):
            K.key_grid(fine, em, 0.0, -0.10, 2, 6, 0.040, rng)
        with b.at(F.frame(0.70, sd * 52.0)):
            for k in range(3):
                K.toggle(fine, em, 0.0, -0.05 + k * 0.05, on=(k != 1), cell="green")
    return scr


def bay_common(b: Parts, F: Fan, dept: str, rng: random.Random, sid: str) -> list:
    return [touch_screen(b, F, f"SCREEN_{sid}_3", 0.86, 0.0, 0.56)]


def comms_controls(b: Parts, F: Fan, dept: str, rng: random.Random) -> list:
    fb, fine, em = b.body, b.fine, b.emit
    scr = bay_common(b, F, dept, rng, "comms")
    with b.at(F.frame(0.66, -30.0)):
        K.handset(fb, fine, em, 0.0, 0.0)
    with b.at(F.frame(0.64, 16.0)):
        K.dial(fine, em, 0.0, 0.0, 0.034, cell="command")                     # frequency wheel
        K.dial(fine, em, 0.085, 0.0, 0.02, cell="cyan")
    for sd in (-1, 1):
        with b.at(F.frame(0.92, sd * 34.0)):
            K.key_grid(fine, em, 0.0, -0.10, 3, 6, 0.040, rng, cells=("cyan", "command", "green"))
        with b.at(F.frame(0.7, sd * 42.0)):
            K.slider_bank(fine, em, 0.0, -0.06, 3, 0.06, 0.13, rng)
    return scr


def sensors_controls(b: Parts, F: Fan, dept: str, rng: random.Random) -> list:
    fb, fine, em = b.body, b.fine, b.emit
    scr = bay_common(b, F, dept, rng, "sensors")
    with b.at(F.frame(0.62, -14.0)):
        K.trackball(fine, em, 0.0, 0.0, 0.03)
    with b.at(F.frame(0.62, 14.0)):
        K.joystick(fine, em, 0.0, 0.0, "science")
    for sd in (-1, 1):
        with b.at(F.frame(0.92, sd * 34.0)):
            K.slider_bank(fine, em, 0.0, -0.12, 5, 0.06, 0.15, rng, cells=("science", "cyan"))
        with b.at(F.frame(0.72, sd * 44.0)):
            K.dial(fine, em, 0.0, 0.0, cell="science")
            K.key_grid(fine, em, 0.07, -0.06, 2, 4, 0.04, rng, cells=("science", "cyan"))
    return scr


def engineering_controls(b: Parts, F: Fan, dept: str, rng: random.Random) -> list:
    fb, fine, em = b.body, b.fine, b.emit
    scr = bay_common(b, F, dept, rng, "engineering")
    # four big power sliders under the hands: weapons, shields, engines, sensors
    for k, th in enumerate((-20.0, -7.0, 7.0, 20.0)):
        with b.at(F.frame(0.72, th)):
            K.slider(fine, em, 0.0, 0.0, 0.20, (0.35, 0.7, 0.55, 0.85)[k], ("engineering", "amber", "engineering", "amber")[k], axis="x")
            K.label_plate(fb, -0.135, 0.0, 0.05, 0.0125, ("PWR", "DATA", "COOL", "AIR")[k])
    for sd in (-1, 1):
        with b.at(F.frame(0.94, sd * 34.0)):
            for k in range(6):
                K.toggle(fine, em, 0.0, -0.13 + k * 0.05, on=rng.random() > 0.35, cell="engineering", guard=(k == 5))
        with b.at(F.frame(0.68, sd * 44.0)):
            K.dial(fine, em, 0.0, 0.0, 0.03, cell="engineering")
            K.status_strip(fine, em, 0.07, -0.08, 6, 0.028, rng)
    return scr


def flight_controls(b: Parts, F: Fan, dept: str, rng: random.Random) -> list:
    fb, fine, em = b.body, b.fine, b.emit
    scr = bay_common(b, F, dept, rng, "flight")
    # the launch control: a guarded lever on the left, a recovery stick on the right
    with b.at(F.frame(0.66, -15.0)):
        K.thrust_lever(fb, fine, em, 0.0, 0.0, cell="flight", lean=-0.07, slot=0.18)
    with b.at(F.frame(0.62, 15.0)):
        K.joystick(fine, em, 0.0, 0.0, "flight")
    for sd in (-1, 1):
        with b.at(F.frame(0.94, sd * 34.0)):
            for k in range(5):
                K.toggle(fine, em, 0.0, -0.11 + k * 0.05, on=rng.random() > 0.4, cell="flight", guard=(k in (0, 4)))
        with b.at(F.frame(0.72, sd * 42.0)):
            K.key_grid(fine, em, 0.0, -0.08, 3, 4, 0.04, rng, cells=("flight", "amber", "green"))
    return scr


def tactical_body(b: Parts, F: Fan, dept: str) -> None:
    """The standing lectern: a floating curved slab (ivory belly, dark glass top, brushed lip) on two fins and a recessed core."""
    fb, fine, em = b.body, b.fine, b.emit
    a, r0, r1, zs = F.a, F.r0, F.r1, F.zs
    dim = dept + "_dim"
    sweep(fb, [(0.5, 0.0), (r1 + 0.03, 0.0), (r1 + 0.03, 0.07), (0.5, 0.07)], -a, a, L.STRUCT, 28)                      # floor plate
    sweep(fb, [(0.70, 0.07), (r1 - 0.05, 0.07), (r1 - 0.05, zs(r1 - 0.05) - 0.10), (0.70, zs(0.70) - 0.10)], -44, 44, L.COMPOSITE, 22)  # core
    sweep(fb, [(r0, F.z0 - 0.078), (r1, zs(r1) - 0.078), (r1, zs(r1) - 0.012), (r0, F.z0 - 0.012)], -a, a, L.COMPOSITE, 30)   # the slab
    sweep(fb, [(r1, zs(r1) - 0.056), (r1 + 0.008, zs(r1) - 0.052), (r1 + 0.008, zs(r1) - 0.016), (r1, zs(r1) - 0.012)], -a, a, L.IVORY, 30)   # armour band
    for k in range(-3, 4):                                                   # bolted straps over the band
        th = k * a / 3.4
        c, s_ = math.cos(math.radians(th)), math.sin(math.radians(th))
        with fb.at(T((r1 + 0.004) * c, (r1 + 0.004) * s_, zs(r1) - 0.034) @ Rz(th)):
            fb.box((0.0, -0.035, -0.024), (0.006, 0.035, 0.024), L.TRIM)
    em.lamp_arc([(r1 - 0.004, 0.0), (r1 + 0.004, 0.0), (r1 + 0.004, 0.006), (r1 - 0.004, 0.006)], 0, 0, 0, -a + 4, a - 4, dim, L.LAMP_DIM, seg=28,
                z0=zs(r1) - 0.075)
    sweep(fb, [(r0 + 0.012, F.z0 - 0.012), (r1 - 0.012, zs(r1 - 0.012) - 0.012), (r1 - 0.012, zs(r1 - 0.012) + 0.002),
               (r0 + 0.012, F.z0 + 0.002)], -a + 1.0, a - 1.0, L.DGLASS, 30)                                              # glass top
    sweep(fb, [(r0 - 0.014, F.z0 - 0.078), (r0, F.z0 - 0.078), (r0, F.z0 + 0.008), (r0 - 0.014, F.z0 + 0.008)], -a, a, L.TRIM, 30)  # lip
    for sd in (-1, 1):                                                       # the two fins that carry the slab
        with b.at(Rz(sd * a * 0.98)):
            fb.extrude_y([(0.66, 0.07), (r1 - 0.04, 0.07), (r1 - 0.04, zs(r1 - 0.04) - 0.078), (0.66, zs(0.66) - 0.078)], -0.024, 0.024, L.COMPOSITE)
            fb.extrude_y([(0.64, 0.07), (0.70, 0.07), (0.70, zs(0.70) - 0.078), (0.64, zs(0.64) - 0.078)], -0.032, 0.032, L.TRIM)
            em.lamp_box((0.66, -0.026, 0.12), (r1 - 0.06, 0.026, 0.13), dim, L.LAMP_DIM)
    em.lamp_arc([(r0 - 0.003, 0.0), (r0 + 0.002, 0.0), (r0 + 0.002, 0.008), (r0 - 0.003, 0.008)], 0, 0, 0, -a + 3, a - 3, dept, L.LAMP, seg=28, z0=F.z0 - 0.06)
    em.lamp_arc([(0.72, 0.0), (r1 - 0.06, 0.0), (r1 - 0.06, 0.006), (0.72, 0.006)], 0, 0, 0, -40, 40, dim, L.LAMP_DIM, seg=24, z0=0.078)   # foot glow
    # the back (towards the Captain): a plate on the core, two vents
    for th in (-26.0, 0.0, 26.0):
        c, s = math.cos(math.radians(th)), math.sin(math.radians(th))
        with fb.at(T((r1 - 0.05) * c, (r1 - 0.05) * s, 0) @ Rz(th)):
            vent_back(fb, -0.16, 0.16, 0.20, 0.55, 5)
            fb.label((0.012, 0.0, 0.76), 0.5 if abs(th) < 1 else 0.3, 0.0625 if abs(th) < 1 else 0.05, (1, 0, 0),
                     PLATE["tactical"] if abs(th) < 1 else "small_00")


def tactical_controls(b: Parts, F: Fan, dept: str, rng: random.Random) -> list:
    fb, fine, em = b.body, b.fine, b.emit
    # the strip display along the arc: 8:1, the whole width of the lectern
    a = F.a - 12.0
    r = 0.70
    arc_len = math.radians(2 * a) * r
    h = arc_len / 8.0
    z_mid = F.zs(r)
    tan_half = math.radians(a)
    faces = []
    n = 22
    for k in range(n):
        t0, t1 = k / n, (k + 1) / n
        th0, th1 = lerp(-a, a, t0), lerp(-a, a, t1)
        pa, pb = F.pos(r - h / 2, th0), F.pos(r + h / 2, th0)
        pc, pd = F.pos(r + h / 2, th1), F.pos(r - h / 2, th1)
        lift = 0.0032
        pts = [(p[0], p[1], p[2] + lift) for p in (pa, pb, pc, pd)]
        # quad in viewer order: near-left, far-left, far-right, near-right seen by the officer (image up = uphill)
        b.emit._quad_b([b.emit.P(pts[0]), b.emit.P(pts[3]), b.emit.P(pts[2]), b.emit.P(pts[1])], "SCREEN_tactical_1", b.emit.N((0, 0, 1)),
                       [(t0, 0.0), (t1, 0.0), (t1, 1.0), (t0, 1.0)])
    # weapon controls: guarded toggles, selector dials, engage keys in front of the strip
    for k, th in enumerate((-30.0, -18.0, 18.0, 30.0)):
        with b.at(F.frame(0.56, th)):
            K.dial(fine, em, 0.0, 0.0, 0.026, cell="security")
    with b.at(F.frame(0.56, 0.0)):
        for k in range(-3, 4):
            K.key(fine, em, 0.0, k * 0.036, "red" if k in (-3, 3) else "security", 0.026)
    for sd in (-1, 1):
        with b.at(F.frame(0.86, sd * 42.0)):
            for k in range(5):
                K.toggle(fine, em, 0.0, -0.10 + k * 0.05, on=rng.random() > 0.4, cell="security", guard=(k in (1, 3)))
        with b.at(F.frame(0.64, sd * 52.0)):
            K.slider_bank(fine, em, 0.0, -0.09, 4, 0.06, 0.14, rng, cells=("security", "amber"))
    return [{"screen": "SCREEN_tactical_1", "size_m": [round(arc_len, 3), round(h, 3)], "surface": "glass"}]
