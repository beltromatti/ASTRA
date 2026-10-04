"""ASN Aquila — the Crew Berthing's racks and locker columns, rebuilt in the kit's language (ARTE-INTERNI-2). SM_BERTH_Stack_A/B/C and SM_BERTH_Lockers of art/blender/berths.py: the same frames, the
same sizes, the same heights, so that the places do not move (data/ship/aquila_berths.json; tools/ue_scripts/build_berths.py puts the seven sleepers on the mattresses at z = rack height + 0.2; tools/life.py
bakes the same racks for VITA's crew: `height_cm = (rack height + 0.2) * 100`; the compartment is ship_berths.room()).

  stack     a stack of three racks (frame: origin on the deck at the rack's foot on the aisle, centred across it; +Y from the aisle to the head at the outboard wall; Z up): four steel posts, a dark pan and a
            lip at every level, closed side sheets, a head panel with a net pocket (a book, a photograph), a reading lamp under the rack above, a number plate and a night light, a rubber-edged mattress, a
            turned-down blanket, a pillow, a datapad or a folded shirt in some, the storage drawer under the bottom rack, a pleated privacy curtain on a rail (A: all drawn back; B: the top one closed; C: the
            middle one closed, the bottom half). About 4 000 triangles (the first generation was 12 500)
  lockers   the column between two stacks (same frame): two tall lockers facing the aisle, each with a perforated vent, a handle, a number and a status light, over the ship's frame behind them, which
            rises to the deckhead with a cable duct and a plate

Built in layout coordinates (X forward, Y starboard, Z up); the builder mirrors Y on the way out, so the FBX lands as the first generation did.
  blender -b --factory-startup --python-exit-code 1 -P art/blender/ship_berth_racks.py -- [--stats]
"""
from __future__ import annotations

import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import ship_lib as SL  # noqa: E402
import ship_mk as MK  # noqa: E402
from ship_lib import (BEDDING, COMPOSITE, FABRIC_GREY, FABRIC_NAVY, FABRIC_SAND, LAMP_DIM, PERF, STRUCT, SWATCH, TRIM, WEAVE_RUST, SParts)  # noqa: E402

D = json.load(open(os.path.join(SL.ROOT, "data", "ship", "aquila_berths.json"), encoding="utf-8"))
ST = D["stacks"]
RW, RL, LW = ST["rack_width"], ST["rack_length"], ST["locker_width"]
LEVELS = ST["rack_heights"]
H = D["height"]
TOP = LEVELS[-1] + 0.85                  # the top of the frame (the first generation's)
SIDE = 0.012                             # the side sheets
PAN = 0.04                               # a pan: its top is `h + PAN`
MAT_TOP = 0.20                           # the mattress top over the pan's underside: where VITA lays a sleeper
HX = RW / 2
BLANKETS = (FABRIC_NAVY, FABRIC_NAVY, FABRIC_NAVY, FABRIC_NAVY, FABRIC_GREY, FABRIC_SAND)
CURTAIN = WEAVE_RUST
THROWS = ("denim", "olive", "tan", "sand", "slate", "forest")
BOOKS = ("navy", "oxblood", "forest", "mustard", "slate", "teal", "rust", "cream", "tan", "denim")


def _photo(b: SParts, x0: float, x1: float, z0: float, z1: float, color: str) -> None:
    """A flat coloured card on the head panel (a photograph, a postcard): one face of the swatch."""
    b.soft.paint([b.soft.face([(x0, RL - 0.0205, z0), (x1, RL - 0.0205, z0), (x1, RL - 0.0205, z1), (x0, RL - 0.0205, z1)], SWATCH, (0, -1, 0))], color)


def _curtain(b: SParts, x0: float, x1: float, z0: float, z1: float, mat: str, amp: float = 0.02, wave: float = 0.13, thick: float = 0.006) -> None:
    """A pleated privacy curtain along the aisle side from x0 to x1, hanging from z1 (the rail) to z0 (the hem): a thin shell lofted through three rings, the pleats a little deeper towards the
    hem (the medbay's curtains, in the rack's frame)."""
    ln = x1 - x0
    n = max(8, int(ln / wave * 4))
    rings = []
    for r in range(3):
        z = z0 + (z1 - z0) * r / 2
        a = amp * (1.3 - 0.3 * r / 2)
        fwd, back = [], []
        for k in range(n + 1):
            x = x0 + ln * k / n
            y = -0.032 + a * math.sin(2 * math.pi * (x - x0) / wave)
            fwd.append((x, y - thick / 2, z))
            back.append((x, y + thick / 2, z))
        rings.append(fwd + list(reversed(back)))
    MK.stack(b.soft, rings, mat)


def _level(b: SParts, i: int, h: float, ceil: float, rng: random.Random, number: int, mode: str) -> None:
    """One rack: the pan and its lip, the bedding, the head panel's pocket, plate and lamp, the curtain on its rail (`mode`: back | closed | half)."""
    # the pan, its lip on the aisle side, the night light
    b.body.box((-HX + SIDE, 0.0, h), (HX - SIDE, RL - 0.02, h + PAN), STRUCT)
    b.body.box((-HX + SIDE, -0.012, h + PAN), (HX - SIDE, 0.02, h + PAN + 0.065), TRIM)
    b.emit.lamp_box((HX - 0.075, -0.0125, h + PAN + 0.02), (HX - 0.05, -0.0115, h + PAN + 0.045), "red_dim", LAMP_DIM)
    # the mattress, the turned-down blanket, the pillow
    top = h + MAT_TOP
    MK.rbox(b.soft, (-HX + 0.035, 0.05, h + PAN), (HX - 0.035, RL - 0.06, top), 0.04, BEDDING, 2)
    blanket = rng.choice(BLANKETS)
    y1 = rng.uniform(1.25, 1.55)
    MK.rbox(b.soft, (-HX + 0.03, 0.045, top - 0.03), (HX - 0.03, y1, top + 0.045), 0.03, blanket, 2)
    MK.rbox(b.soft, (-HX + 0.032, y1 - 0.07, top - 0.02), (HX - 0.032, y1 + 0.075, top + 0.05), 0.025, BEDDING, 2)             # the sheet turned over
    for _ in range(2):                                                                                                         # the blanket is not flat
        MK.puff(b.soft, (rng.uniform(-0.18, 0.18), rng.uniform(0.3, y1 - 0.25), top + 0.035), (rng.uniform(0.12, 0.2), rng.uniform(0.14, 0.26), 0.034), blanket, e=0.7, nu=14, nv=6)
    MK.puff(b.soft, (rng.uniform(-0.05, 0.05), RL - 0.3, top + 0.05), (0.25, 0.16, 0.058), BEDDING, e=0.6, nu=14, nv=7)
    r = rng.random()
    if r < 0.4:                                                                                                                # a folded shirt, a towel at the foot
        b.soft.paint(MK.rbox(b.soft, (-0.17, 0.1, top + 0.04), (0.17, 0.34, top + 0.09), 0.012, SWATCH, 1), rng.choice(THROWS))
    elif r < 0.7:                                                                                                              # a datapad left on the blanket
        b.soft.swatch_box((0.02, 0.5, top + 0.043), (0.24, 0.72, top + 0.053), "charcoal")
        b.emit.lamp_box((0.035, 0.515, top + 0.0531), (0.225, 0.705, top + 0.0536), "cool_dim", LAMP_DIM)
    # the head panel: a net pocket with a book and a photograph, the number plate, the reading lamp under the rack above
    b.soft.box((-0.2, RL - 0.052, h + 0.34), (0.2, RL - 0.02, h + 0.5), FABRIC_GREY)
    b.soft.swatch_box((-0.15, RL - 0.06, h + 0.36), (-0.1, RL - 0.025, h + 0.52), rng.choice(BOOKS))
    b.soft.swatch_box((-0.09, RL - 0.058, h + 0.36), (-0.05, RL - 0.025, h + 0.49), rng.choice(BOOKS))
    _photo(b, 0.07, 0.17, h + 0.54, h + 0.65, rng.choice(("rose", "sand", "tan", "cream")))
    b.emit.label((0.0, RL - 0.0205, h + 0.7), 0.12, 0.03, (0, -1, 0), f"small_{number % 6:02d}")
    b.body.box((-0.13, RL - 0.37, ceil - 0.02), (0.13, RL - 0.27, ceil), TRIM)
    b.emit.lamp_box((-0.115, RL - 0.355, ceil - 0.022), (0.115, RL - 0.285, ceil - 0.02), "white_warm" if rng.random() < 0.35 else "warm_dim", LAMP_DIM)
    # the curtain on its rail
    b.soft.cyl((-HX + SIDE, -0.03, ceil - 0.03), (HX - SIDE, -0.03, ceil - 0.03), 0.008, TRIM, seg=6, caps=False)
    z0, z1 = h + 0.11, ceil - 0.04
    if mode == "closed":
        _curtain(b, -HX + 0.03, HX - 0.03, z0, z1, CURTAIN, 0.02, 0.13)
    elif mode == "half":
        _curtain(b, 0.0, HX - 0.03, z0, z1, CURTAIN, 0.02, 0.13)
    else:
        _curtain(b, HX - 0.17, HX - 0.03, z0, z1, CURTAIN, 0.032, 0.056)


def stack(name: str, variant: str, seed: int):
    """One stack of racks (variant A, B or C: which curtains are drawn)."""
    SL.load_labels()
    rng = random.Random(seed)
    b = SParts(bevel=0.004, fine_bevel=0.002)
    # the four steel posts (the two at the head stand inside the sheets), the head panel, the side sheets, the top
    for sx in (-HX, HX - 0.05):
        for sy in (0.0, RL - 0.05):
            b.body.box((sx, sy, 0.0), (sx + 0.05, sy + 0.05, TOP), TRIM)
    b.body.box((-HX, RL - 0.02, 0.0), (HX, RL + 0.01, TOP), STRUCT)
    for sx in (-HX, HX - SIDE):
        b.body.box((sx, 0.05, 0.05), (sx + SIDE, RL - 0.02, TOP), COMPOSITE)
    b.body.box((-HX, -0.012, TOP), (HX, RL + 0.01, TOP + 0.03), STRUCT)
    # the storage drawer under the bottom rack: a front with a pull, the number of its rack
    b.body.box((-HX + 0.03, 0.0, 0.03), (HX - 0.03, RL - 0.05, LEVELS[0] - 0.02), COMPOSITE)
    b.soft.box((-HX + 0.05, -0.012, 0.06), (HX - 0.05, 0.0, LEVELS[0] - 0.05), STRUCT)
    b.fine.box((-0.14, -0.034, LEVELS[0] - 0.15), (0.14, -0.012, LEVELS[0] - 0.12), TRIM)
    b.emit.label((HX - 0.2, -0.0125, 0.085), 0.12, 0.03, (0, -1, 0), f"small_{(seed + 1) % 6:02d}")
    for i, h in enumerate(LEVELS):
        ceil = LEVELS[i + 1] if i + 1 < len(LEVELS) else TOP
        mode = "closed" if (variant == "B" and i == 2) or (variant == "C" and i == 1) else ("half" if (variant == "C" and i == 0) else "back")
        _level(b, i, h, ceil, rng, seed * 3 + i, mode)
    return b.build(name, uv_meter=1.0)


def lockers(name: str = "SM_BERTH_Lockers"):
    """The column between two stacks: two crew lockers facing the aisle over a plinth, the ship's frame behind them to the deckhead."""
    SL.load_labels()
    b = SParts(bevel=0.004, fine_bevel=0.002)
    hw, d = LW / 2, 0.55
    b.body.box((-hw + 0.012, 0.02, 0.0), (hw - 0.012, d - 0.02, 0.08), STRUCT)
    b.body.box((-hw, 0.0, 0.08), (hw, d, 2.1), COMPOSITE)
    b.body.box((-hw - 0.008, -0.012, 2.1), (hw + 0.008, d + 0.008, 2.13), TRIM)
    for k, (z0, z1) in enumerate(((0.11, 1.06), (1.1, 2.05))):
        zm = (z0 + z1) / 2
        b.soft.box((-hw + 0.025, -0.016, z0), (hw - 0.025, 0.0, z1), TRIM)                                            # the door
        b.fine.box((hw - 0.1, -0.042, zm - 0.1), (hw - 0.072, -0.016, zm + 0.1), TRIM)                              # the handle
        b.soft.box((-hw + 0.06, -0.019, z1 - 0.19), (hw - 0.06, -0.016, z1 - 0.06), PERF)                           # the vent
        b.soft.box((-hw + 0.06, -0.019, z0 + 0.06), (hw - 0.06, -0.016, z0 + 0.13), PERF)
        b.emit.lamp_box((-hw + 0.05, -0.0185, zm - 0.02), (-hw + 0.075, -0.0165, zm + 0.0), "green" if k == 0 else "amber", LAMP_DIM)
        b.emit.label((0.0, -0.0165, z1 - 0.26), 0.17, 0.0425, (0, -1, 0), f"small_{(k * 3 + 1) % 6:02d}")
    # the ship's frame behind: it rises to the deckhead; over the lockers a cable duct on clamps, a vent and a plate
    b.body.box((-hw, d, 0.0), (hw, RL + 0.01, H), STRUCT)
    b.body.box((-hw - 0.01, d - 0.0, 2.9), (hw + 0.01, d + 0.04, 3.0), TRIM)
    b.soft.box((-hw + 0.08, d - 0.002, 2.25), (hw - 0.08, d, 2.7), PERF)
    b.fine.cyl((hw - 0.12, d + 0.07, 2.13), (hw - 0.12, d + 0.07, H - 0.1), 0.045, TRIM, seg=10)
    for z in (2.3, 2.9):
        b.fine.box((hw - 0.17, d, z), (hw - 0.07, d + 0.115, z + 0.03), TRIM)
    b.emit.label((-0.04, d - 0.0015, 2.82), 0.3, 0.075, (0, -1, 0), "tag_02")
    return b.build(name, uv_meter=1.0)


if __name__ == "__main__":
    A.reset_scene()
    for k, v in enumerate("ABC"):
        o = stack(f"SM_BERTH_Stack_{v}", v, 11 + k)
        print("BERTH_RACK", o.name, A.stats(o)["tris"], "slots", len(o.data.materials), [m.name for m in o.data.materials])
    o = lockers()
    print("BERTH_RACK", o.name, A.stats(o)["tris"], "slots", len(o.data.materials), [m.name for m in o.data.materials])
