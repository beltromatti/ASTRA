"""ASN Aquila bridge v3: physical controls for the consoles (keys, sliders, dials, toggles, levers, trackballs, joysticks).

Everything is built in the LOCAL frame of the work surface where the control sits: origin on the surface, local x along the
slope (away from the officer, uphill), local y across (the officer's right), local z along the surface normal (up).
Lit parts go to the emissive builder (`em`), solid parts to the body (`fb`) or the fine builder (`fine`): the callers pass
the three builders; nothing here knows about a particular console.
"""
from __future__ import annotations

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge3_lib as L  # noqa: E402
from bridge3_lib import FB, Rx, Ry, Rz, T, lerp  # noqa: E402


def key(fine: FB, em: FB, x: float, y: float, cell: str = "cyan", size: float = 0.024, h: float = 0.009, shell: str = L.IVORY) -> None:
    """A square keycap on a dark bezel with a lit face."""
    fine.box((x - size / 2 - 0.003, y - size / 2 - 0.003, -0.002), (x + size / 2 + 0.003, y + size / 2 + 0.003, 0.003), L.STRUCT)
    fine.box((x - size / 2, y - size / 2, 0.0), (x + size / 2, y + size / 2, h), shell)
    em.lamp_box((x - size / 2 + 0.004, y - size / 2 + 0.004, h), (x + size / 2 - 0.004, y + size / 2 - 0.004, h + 0.0015), cell, L.LAMP_DIM)


def key_grid(fine: FB, em: FB, x0: float, y0: float, rows: int, cols: int, pitch: float, rng: random.Random,
             cells=("cyan", "cyan", "cyan", "white", "amber", "green"), size: float = 0.024) -> None:
    for r in range(rows):
        for c in range(cols):
            key(fine, em, x0 + r * pitch, y0 + c * pitch, rng.choice(cells), size)


def slider(fine: FB, em: FB, x: float, y: float, length: float = 0.14, pos: float = 0.5, cell: str = "cyan", axis: str = "x") -> None:
    """A slider on a slot: dark track, a lit scale line beside it, a ribbed knob at `pos` (0..1)."""
    if axis == "x":
        fine.box((x - length / 2, y - 0.008, -0.002), (x + length / 2, y + 0.008, 0.004), L.STRUCT)
        fine.box((x - length / 2 + 0.005, y - 0.003, 0.004), (x + length / 2 - 0.005, y + 0.003, 0.006), L.RUBBER)
        em.lamp_box((x - length / 2, y + 0.012, 0.0), (x + length / 2, y + 0.0145, 0.002), cell, L.LAMP_DIM)
        kx = x - length / 2 + 0.02 + (length - 0.04) * pos
        fine.box((kx - 0.011, y - 0.014, 0.004), (kx + 0.011, y + 0.014, 0.020), L.IVORY)
        em.lamp_box((kx - 0.0015, y - 0.014, 0.0205), (kx + 0.0015, y + 0.014, 0.0215), cell, L.LAMP)
        for k in (-1, 0, 1):
            fine.box((kx + k * 0.006 - 0.0007, y - 0.014, 0.0195), (kx + k * 0.006 + 0.0007, y + 0.014, 0.0205), L.STRUCT)
    else:
        fine.box((x - 0.008, y - length / 2, -0.002), (x + 0.008, y + length / 2, 0.004), L.STRUCT)
        fine.box((x - 0.003, y - length / 2 + 0.005, 0.004), (x + 0.003, y + length / 2 - 0.005, 0.006), L.RUBBER)
        em.lamp_box((x + 0.012, y - length / 2, 0.0), (x + 0.0145, y + length / 2, 0.002), cell, L.LAMP_DIM)
        ky = y - length / 2 + 0.02 + (length - 0.04) * pos
        fine.box((x - 0.014, ky - 0.011, 0.004), (x + 0.014, ky + 0.011, 0.020), L.IVORY)
        em.lamp_box((x - 0.014, ky - 0.0015, 0.0205), (x + 0.014, ky + 0.0015, 0.0215), cell, L.LAMP)


def slider_bank(fine: FB, em: FB, x: float, y0: float, n: int, pitch: float, length: float, rng: random.Random, cells=("cyan", "amber", "green")) -> None:
    for k in range(n):
        slider(fine, em, x, y0 + k * pitch, length, rng.random(), rng.choice(cells), axis="x")


def dial(fine: FB, em: FB, x: float, y: float, r: float = 0.028, h: float = 0.022, cell: str = "cyan", ticks: bool = True) -> None:
    """A knurled rotary control: a base ring with a lit collar, the knob, an indicator line, tick marks round it."""
    fine.cyl((x, y, -0.002), (x, y, 0.006), r + 0.010, L.STRUCT, seg=20)
    em.lamp_cyl((x, y, 0.0055), (x, y, 0.0075), r + 0.006, cell, L.LAMP_DIM, seg=20)
    fine.cyl((x, y, 0.006), (x, y, 0.006 + h), r, L.TRIM, seg=20)
    fine.cyl((x, y, 0.006 + h), (x, y, 0.008 + h), r - 0.003, L.STRUCT, seg=20)
    em.lamp_box((x - 0.0015, y, 0.0085 + h), (x + r - 0.004, y + 0.0015, 0.0095 + h), "white", L.LAMP)
    if ticks:
        for k in range(11):
            a = math.radians(-135 + 27 * k)
            tx, ty = x + (r + 0.016) * math.cos(a), y + (r + 0.016) * math.sin(a)
            fine.cbox((tx, ty, 0.0015), (0.003, 0.006, 0.003), L.TRIM, Rz(math.degrees(a)))


def toggle(fine: FB, em: FB, x: float, y: float, on: bool = True, cell: str = "green", guard: bool = False) -> None:
    """A lever toggle switch on a small plate, optionally under a flip guard (a red one for the weapons)."""
    fine.box((x - 0.016, y - 0.014, -0.002), (x + 0.016, y + 0.014, 0.004), L.STRUCT)
    fine.cyl((x, y, 0.004), (x, y, 0.012), 0.008, L.TRIM, seg=10)
    lean = -0.014 if on else 0.014
    fine.cyl((x, y, 0.010), (x + lean, y, 0.034), 0.0045, L.TRIM, seg=8, r2=0.006)
    em.lamp_box((x + 0.02, y - 0.004, 0.0), (x + 0.026, y + 0.004, 0.0015), cell, L.LAMP)
    if guard:
        fine.box((x - 0.02, y - 0.02, 0.0), (x - 0.017, y + 0.02, 0.05), L.STRUCT)
        fine.box((x - 0.02, y - 0.02, 0.05), (x + 0.022, y + 0.02, 0.054), L.STRUCT)
        em.lamp_box((x - 0.019, y - 0.018, 0.049), (x + 0.021, y + 0.018, 0.0505), "red", L.LAMP_DIM)


def thrust_lever(fb: FB, fine: FB, em: FB, x: float, y: float, height: float = 0.055, lean: float = -0.05, cell: str = "command",
                 slot: float = 0.22, label_cell: str | None = None) -> tuple:
    """A thrust lever: a slotted track, a base collar, a swept shaft and an ergonomic grip with a thumb button and a lit ring.
    (x, y) is the pivot on the surface; the grip's centre is returned in surface coordinates."""
    fine.box((x - slot / 2, y - 0.020, -0.003), (x + slot / 2, y + 0.020, 0.004), L.STRUCT)                 # the track
    fine.box((x - slot / 2 + 0.008, y - 0.006, 0.004), (x + slot / 2 - 0.008, y + 0.006, 0.0055), L.RUBBER)  # slot
    em.lamp_box((x - slot / 2, y + 0.026, 0.0), (x + slot / 2, y + 0.029, 0.002), cell, L.LAMP_DIM)          # scale
    for k in range(9):
        fine.box((x - slot / 2 + 0.01 + k * (slot - 0.02) / 8 - 0.0008, y - 0.024, 0.0), (x - slot / 2 + 0.01 + k * (slot - 0.02) / 8 + 0.0008, y - 0.020, 0.0018), L.TRIM)
    fine.cyl((x, y, 0.004), (x, y, 0.028), 0.020, L.TRIM, seg=16, r2=0.014)                                 # collar
    top = (x + lean, y, 0.004 + height)
    fine.cyl((x, y, 0.028), top, 0.0085, L.TRIM, seg=12)                                                    # shaft
    gx, gz = top[0], top[2]
    fine.cyl((gx - 0.004, y, gz - 0.006), (gx + 0.004, y, gz + 0.048), 0.017, L.RUBBER, seg=14, r2=0.021)     # grip
    fine.cyl((gx + 0.004, y, gz + 0.048), (gx + 0.004, y, gz + 0.058), 0.020, L.STRUCT, seg=14)              # cap
    fine.box((gx - 0.012, y - 0.024, gz + 0.012), (gx + 0.014, y - 0.017, gz + 0.036), L.TRIM)                # thumb rest
    em.lamp_box((gx + 0.0, y + 0.0165, gz + 0.018), (gx + 0.010, y + 0.021, gz + 0.032), cell, L.LAMP)      # thumb button light
    em.lamp_cyl((gx - 0.0045, y, gz + 0.040), (gx - 0.0035, y, gz + 0.044), 0.0215, cell, L.LAMP_DIM, seg=14)   # lit ring
    return (gx, y, gz + 0.024)


def trackball(fine: FB, em: FB, x: float, y: float, r: float = 0.028) -> None:
    fine.cyl((x, y, -0.002), (x, y, 0.010), r + 0.012, L.STRUCT, seg=20)
    em.lamp_cyl((x, y, 0.0095), (x, y, 0.0115), r + 0.008, "cyan", L.LAMP_DIM, seg=20)
    fine.sphere((x, y, 0.012 + r * 0.55), r, L.DGLASS, seg=16, rings=10)
    for a in (0, 120, 240):
        c, s = math.cos(math.radians(a)), math.sin(math.radians(a))
        fine.cyl((x + (r + 0.03) * c, y + (r + 0.03) * s, 0.0), (x + (r + 0.03) * c, y + (r + 0.03) * s, 0.008), 0.009, L.TRIM, seg=10)


def joystick(fine: FB, em: FB, x: float, y: float, cell: str = "amber") -> None:
    """A two-axis stick in a gimbal boot with a hat switch and a trigger, for fine control."""
    fine.cyl((x, y, -0.002), (x, y, 0.014), 0.036, L.STRUCT, seg=20, r2=0.030)
    fine.cyl((x, y, 0.014), (x, y, 0.034), 0.030, L.RUBBER, seg=16, r2=0.014)                                # rubber boot
    fine.cyl((x, y, 0.034), (x - 0.012, y, 0.110), 0.010, L.TRIM, seg=10)
    fine.cyl((x - 0.012, y, 0.084), (x - 0.014, y, 0.140), 0.017, L.RUBBER, seg=12, r2=0.020)
    fine.sphere((x - 0.014, y, 0.145), 0.019, L.RUBBER, seg=12, rings=8)
    em.lamp_cyl((x - 0.014, y, 0.153), (x - 0.014, y, 0.156), 0.008, cell, L.LAMP, seg=10)
    fine.box((x + 0.002, y - 0.006, 0.100), (x + 0.020, y + 0.006, 0.112), L.TRIM)                          # trigger


def status_strip(fine: FB, em: FB, x: float, y0: float, n: int, pitch: float, rng: random.Random, cells=("green", "green", "green", "amber", "cyan")) -> None:
    """A row of small round lamps in bezels."""
    for k in range(n):
        y = y0 + k * pitch
        fine.cyl((x, y, -0.002), (x, y, 0.003), 0.0085, L.STRUCT, seg=10)
        em.lamp_cyl((x, y, 0.003), (x, y, 0.0045), 0.0062, rng.choice(cells), L.LAMP_DIM, seg=10)


def handset(fb: FB, fine: FB, em: FB, x: float, y: float, yaw: float = 0.0) -> None:
    """A communications handset in its cradle."""
    with fine.at(T(x, y, 0) @ Rz(yaw)):
        fine.box((-0.05, -0.028, -0.002), (0.05, 0.028, 0.03), L.STRUCT)
        fine.box((-0.048, -0.017, 0.03), (0.048, 0.017, 0.048), L.RUBBER)
        fine.box((-0.052, -0.02, 0.026), (-0.038, 0.02, 0.058), L.RUBBER)
        fine.box((0.038, -0.02, 0.026), (0.052, 0.02, 0.058), L.RUBBER)
        em.lamp_box((-0.02, -0.004, 0.0485), (0.02, 0.004, 0.0495), "cyan", L.LAMP_DIM)


def label_plate(fb: FB, x: float, y: float, w: float, h: float, cell: str) -> None:
    fb.label((x, y, 0.0025), w, h, (0, 0, 1), cell, up=(1, 0, 0))


def wrist_rest(fine: FB, x0: float, x1: float, y0: float, y1: float) -> None:
    """A soft rubber wrist rest along the near edge of the work surface."""
    fine.box((x0, y0, 0.0), (x1, y1, 0.014), L.RUBBER)
    fine.box((x0 - 0.004, y0, 0.0), (x0, y1, 0.008), L.STRUCT)
