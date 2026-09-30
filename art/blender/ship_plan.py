"""ASN Aquila — the ship's plan (the "DNA of the ship"): hull math, the stack of decks, the sections A-H, the volumes of the
existing rooms, geometry helpers and the loader/writer of data/ship/aquila_plan.json. Pure Python (no bpy, no unreal): it is
used by the plan generator (ship_plan_gen.py), the checks (ship_checks.py), the Blender kit (ship_kit.py) and the Unreal
import script (tools/ue_scripts/build_ship_interior.py).

Frame: X forward (towards the bow), Y starboard, Z up; metres; the origin of the world is the bridge floor point under the
Captain's chair (Unreal: cm, the same axes). The hull mesh SM_SHIP_ASTRA_Aquila is placed at world (-172, 0, -62): hull frame
= world + (172, 0, 62); the hull's own numbers (shipgen2.py astra_ship2, kind carrier) are given in the hull frame.
"""
from __future__ import annotations

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DATA_DIR = os.path.join(ROOT, "data", "ship")
PLAN_PATH = os.path.join(DATA_DIR, "aquila_plan.json")

# ------------------------------------------------------------------------------------------------------------ the hull
BRIDGE_OFFSET = (172.0, 0.0, 62.0)          # hull frame = world + BRIDGE_OFFSET (AstraBattleSubsystem.h BridgeOffset)
LENGTH = 780.0
W_MAX, H_MAX = 50.0, 24.0                   # half width / half height of the lower hull's widest section
X_ST, X_BW = -LENGTH / 2 + 18.0, LENGTH / 2  # hull-frame x of the stern cap of the lower hull and of the bow
WIDTH_PROFILE = [(0.0, 0.9), (0.08, 1.0), (0.72, 1.0), (1.0, 0.62)]      # carrier: fraction of W_MAX along the hull
HEIGHT_PROFILE = [(0.0, 0.95), (0.1, 1.0), (0.75, 1.0), (1.0, 0.72)]
SECTION_CHAMFER, SECTION_TOP, SECTION_BOTTOM = 0.3, 0.9, 0.72             # astra_sec(): chamfer_rect(w, h, 0.3, 0.9, 0.72)
BOW_DROP = 0.15                             # the bow sections sink by H*0.15*(t-0.8)/0.2 after t = 0.8
# the upper block (the "upper deck" of shipgen2: a raised body along the aft two thirds) and the island (the tower)
BLOCK = dict(x=(-327.6, 132.6), half_width=30.0, profile=[(0.0, 0.85), (0.15, 1.0), (0.85, 1.0), (1.0, 0.7)], z_centre=30.08,
             half_height=9.0, chamfer=0.35, top=0.8)
ISLAND = dict(base_x=(112.0, 212.0), base_hw=19.0, top_x=(152.0, 184.0), top_hw=11.5, z=(21.6, 60.4))
ENGINE_FRONT_X = -360.0                     # hull-frame x of the closed front cap of the stern engine block (visible from inside)
INNER_SKIN_Z = 20.7                         # hull-frame z of the block's underside (its plating reaches down to ~20.3): a face
                                            # visible from below anywhere inside the lower hull under the block (see docs/NAVE.md)


def profile(t: float, pts) -> float:
    for (t0, v0), (t1, v1) in zip(pts, pts[1:]):
        if t0 <= t <= t1:
            return v0 + (v1 - v0) * (t - t0) / max(1e-9, t1 - t0)
    return pts[-1][1]


def to_hull(x: float, y: float, z: float):
    return (x + BRIDGE_OFFSET[0], y + BRIDGE_OFFSET[1], z + BRIDGE_OFFSET[2])


def to_world(x: float, y: float, z: float):
    return (x - BRIDGE_OFFSET[0], y - BRIDGE_OFFSET[1], z - BRIDGE_OFFSET[2])


def hull_section(xh: float):
    """(half width, half height, z offset) of the lower hull at hull-frame x."""
    t = (xh - X_ST) / (X_BW - X_ST)
    return (W_MAX * profile(t, WIDTH_PROFILE), H_MAX * profile(t, HEIGHT_PROFILE), -H_MAX * BOW_DROP * max(0.0, (t - 0.8) / 0.2))


def octagon_half_width(w: float, h: float, z: float, c=SECTION_CHAMFER, top=SECTION_TOP, bottom=SECTION_BOTTOM):
    """Half width at height z (relative to the section's centre) of the chamfered section chamfer_rect(w, h, c, top, bottom)."""
    cw, ch = c * w, c * h
    right = [(w * bottom - cw, -h), (w, -h + ch), (w, h - ch), (w * top - cw, h)]
    if z < right[0][1] or z > right[-1][1]:
        return None
    for (y0, z0), (y1, z1) in zip(right, right[1:]):
        if z0 <= z <= z1:
            return y0 + (y1 - y0) * (z - z0) / max(1e-9, z1 - z0)
    return None


def lower_hull_half_width(x: float, z: float):
    """Half width of the lower hull's outer envelope at WORLD x, z (None when the point is above / below / beyond it)."""
    xh, _y, zh = to_hull(x, 0.0, z)
    if xh < X_ST or xh > X_BW:
        return None
    w, h, zo = hull_section(xh)
    return octagon_half_width(w, h, zh - zo)


def block_half_width(x: float, z: float):
    xh, _y, zh = to_hull(x, 0.0, z)
    if xh < BLOCK["x"][0] or xh > BLOCK["x"][1]:
        return None
    t = (xh - BLOCK["x"][0]) / (BLOCK["x"][1] - BLOCK["x"][0])
    w = BLOCK["half_width"] * profile(t, BLOCK["profile"])
    return octagon_half_width(w, BLOCK["half_height"], zh - BLOCK["z_centre"], BLOCK["chamfer"], BLOCK["top"], 1.0)


def island_half_width(x: float, z: float):
    """(x_min, x_max, half width) of the island's tower at world z, or None."""
    _xh, _y, zh = to_hull(x, 0.0, z)
    z0, z1 = ISLAND["z"]
    if zh < z0 or zh > z1:
        return None
    f = (zh - z0) / (z1 - z0)
    x0 = ISLAND["base_x"][0] + (ISLAND["top_x"][0] - ISLAND["base_x"][0]) * f
    x1 = ISLAND["base_x"][1] + (ISLAND["top_x"][1] - ISLAND["base_x"][1]) * f
    hw = ISLAND["base_hw"] + (ISLAND["top_hw"] - ISLAND["base_hw"]) * f
    return (x0 - BRIDGE_OFFSET[0], x1 - BRIDGE_OFFSET[0], hw)


# ------------------------------------------------------------------------------------------------------- the deck stack
# floor z (world), clear height, the name of the deck's programme (docs/BIBBIA.md §6) and the volume it lives in
DECKS = {
    1: dict(z=0.0, clear=3.4, name="Command", volume="island top"),
    2: dict(z=-36.7, clear=3.6, name="CIC & Communications", volume="block + island base"),
    3: dict(z=-42.0, clear=3.4, name="Crew Country", volume="lower hull, top deck"),
    4: dict(z=-46.0, clear=3.8, name="Crew Services", volume="lower hull"),
    5: dict(z=-50.0, clear=3.4, name="Science & Transport", volume="lower hull"),
    6: dict(z=-54.0, clear=3.4, name="Medical", volume="lower hull"),
    7: dict(z=-58.0, clear=3.4, name="Engineering & Power", volume="lower hull"),
    8: dict(z=-62.0, clear=3.4, name="Marines & Armory", volume="lower hull"),
    9: dict(z=-66.0, clear=3.4, name="Flight", volume="lower hull, bow"),
    10: dict(z=-70.0, clear=3.4, name="Holds & Munitions", volume="lower hull"),
    11: dict(z=-74.0, clear=3.4, name="Workshops & Damage Control", volume="lower hull"),
    12: dict(z=-78.0, clear=3.4, name="Keel", volume="lower hull, keel"),
}
STRUCT = 0.3                                 # floor / ceiling structure

# section boundaries per deck, bow to stern (world x, all on the 4 m grid): 9 numbers = 8 sections A-H; A is the bow-most. Deck 1 is special.
# They keep the existing rooms in the sections their signs give: Mess B, Berthing C, Medbay C, Engineering F, Flight Deck B.
SECTION_BOUNDS = {
    2: [40, -60, -120, -192, -260, -328, -392, -444, -496],
    3: [28, -60, -152, -252, -320, -380, -432, -472, -500],
    4: [104, -104, -160, -248, -320, -384, -440, -484, -524],
    5: [160, 40, -60, -172, -252, -332, -396, -460, -524],
    6: [216, 20, -132, -292, -352, -412, -452, -492, -524],
    7: [216, 40, -92, -180, -252, -316, -388, -456, -524],
    8: [216, 100, 20, -60, -172, -292, -380, -452, -524],
    9: [216, 204, 60, -28, -120, -220, -320, -420, -524],
    10: [216, 100, -12, -112, -220, -332, -420, -480, -524],
    11: [216, 100, -12, -112, -220, -332, -420, -480, -524],
    12: [200, 100, -12, -112, -220, -332, -420, -480, -524],
}
SECTION_LETTERS = "ABCDEFGH"
SPECIAL_SECTIONS = {1: [("A", -31.0, 14.0)]}          # Deck 1 is the bridge complex only: one section


def sections(deck: int):
    """[(letter, xmin, xmax)] of a deck, bow-most first."""
    if deck in SPECIAL_SECTIONS:
        return list(SPECIAL_SECTIONS[deck])
    b = SECTION_BOUNDS[deck]
    return [(SECTION_LETTERS[i], float(b[i + 1]), float(b[i])) for i in range(8)]


def section_of(deck: int, x: float) -> str:
    secs = sections(deck)
    for letter, x0, x1 in secs:
        if x0 - 1e-6 <= x <= x1 + 1e-6:
            return letter
    return secs[0][0] if x > secs[0][2] else secs[-1][0]


def deck_z(deck: int):
    d = DECKS[deck]
    return d["z"], d["z"] + d["clear"]


def envelope(deck: int, margin: float = 1.5, step: float = 4.0, min_half_width: float = 12.0):
    """The usable envelope of a deck: {x_fwd, x_aft, half_width: [[x, y]...]} where y is the half width available to walls at
    every sample (the narrower of the floor and the ceiling of the deck, minus the margin). Decks 3-12 sit in the lower hull;
    Deck 2 in the block (and the island's base forward of it); Deck 1 is the island's top (not enveloped here)."""
    z0, z1 = deck_z(deck)
    z1s = z1 + STRUCT
    samples = []
    x = 600.0
    while x > -700.0:
        lim = None
        if deck >= 3:
            ws = [lower_hull_half_width(x, zz) for zz in (z0, z0 + 1.7, z1, z1s - 0.1)]
            if all(w is not None for w in ws):
                lim = min(ws) - margin
            if x < to_world(ENGINE_FRONT_X, 0, 0)[0] + 4.0:
                lim = None
        elif deck == 2:
            isl = island_half_width(x, z0 + 1.8)
            blk = block_half_width(x, z0 + 1.8)
            if blk is not None:
                lim = blk - margin
                # the island's walls stand inside the block where they overlap: stop at the island's tower base
                if isl is not None and isl[0] - 0.0 <= x <= isl[1]:
                    lim = min(lim, isl[2] - margin)
            elif isl is not None and isl[0] <= x <= isl[1]:
                lim = isl[2] - margin
        if lim is not None and lim >= min_half_width:
            samples.append([round(x, 2), round(lim, 2)])
        x -= step
    if not samples:
        return {"x_fwd": None, "x_aft": None, "half_width": []}
    return {"x_fwd": samples[0][0], "x_aft": samples[-1][0], "half_width": samples}


def half_width_at(env: dict, x: float):
    """Half width of the envelope at x (linear between samples), None outside."""
    pts = env["half_width"]
    if not pts or x > pts[0][0] or x < pts[-1][0]:
        return None
    for (xa, ya), (xb, yb) in zip(pts, pts[1:]):
        if xb <= x <= xa:
            t = (x - xb) / max(1e-9, xa - xb)
            return yb + (ya - yb) * t
    return pts[-1][1]


# ------------------------------------------------------------------------------------------------ the existing rooms
def _j(name: str) -> dict:
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as fh:
        return json.load(fh)


def existing_rooms(m: float = 0.4) -> list[dict]:
    """The rooms the level already holds (Captain's quarters, Crew Berthing, Mess Hall, Medbay, Main Engineering, Flight Deck), as boxes
    in world metres [x0, y0, x1, y1, z0, z1] from their data files and the wall thicknesses of their builders, grown by a margin `m`
    (0.4 m for the keep-outs: everything else in the plan keeps out of them; 0 for the rooms' own bounds). `deck` is the deck the
    room's signage says; `plane_deck` the deck whose plane its floor lies in."""
    rooms = []
    mess, berth, med, eng, hang, quar = (_j("aquila_mess.json"), _j("aquila_berths.json"), _j("aquila_medbay.json"),
                                          _j("aquila_engineering.json"), _j("aquila_hangar.json"), _j("aquila_quarters.json"))

    def room(rid, name, deck, plane_deck, section, kind, box, entrance, **extra):
        d = dict(id=rid, name=name, deck=deck, plane_deck=plane_deck, section=section, kind=kind, box=[round(v, 3) for v in box],
                 entrance=entrance, existing=True)
        d.update(extra)
        rooms.append(d)

    ox, oy, oz = mess["world_origin"]
    L, hw, h = mess["length"], mess["half_width"], mess["height"]
    room("mess", "Mess Hall", 4, 4, "B", "mess", [ox - L - 0.3 - m, oy - hw - 0.3 - m, ox + 0.3 + m, oy + hw + 0.3 + m, oz - 0.3 - m, oz + h + 0.25 + m],
         dict(wall="fwd", x=ox, y=oy + mess["lift"]["y"], w=mess["lift"]["width"], h=mess["lift"]["height"], z=oz),
         annex=[ox - 9.9 - 0.15 - m, oy - hw - 2.8 - 0.3 - m, ox - 1.1 + 0.15 + m, oy - hw + m, oz - 0.3 - m, oz + h + 0.25 + m],
         data="aquila_mess.json", landing=[ox - 2.6, oy, oz])
    ox, oy, oz = berth["world_origin"]
    L, hw, h = berth["length"], berth["half_width"], berth["height"]
    room("berths", "Crew Berthing", 3, 4, "C", "berthing", [ox - L - 0.3 - m, oy - hw - 0.3 - m, ox + 0.3 + m, oy + hw + 0.3 + m, oz - 0.3 - m, oz + h + 0.3 + m],
         dict(wall="fwd", x=ox, y=oy + berth["lift"]["y"], w=berth["lift"]["width"], h=berth["lift"]["height"], z=oz),
         data="aquila_berths.json", landing=[ox - 2.0, oy, oz])
    ox, oy, oz = med["world_origin"]
    L, hw, h = med["length"], med["half_width"], med["height"]
    room("medbay", "Medbay", 6, 6, "C", "medbay", [ox - L - 0.3 - m, oy - hw - 0.3 - m, ox + 0.3 + m, oy + hw + 0.3 + m, oz - 0.3 - m, oz + h + 0.3 + m],
         dict(wall="fwd", x=ox, y=oy + med["lift"]["y"], w=med["lift"]["width"], h=med["lift"]["height"], z=oz), data="aquila_medbay.json",
         landing=[ox - 2.6, oy, oz])
    ox, oy, oz = eng["world_origin"]
    L, hw, h = eng["length"], eng["half_width"], eng["height"]
    room("engineering", "Main Engineering", 7, 7, "F", "engineering", [ox - L - 0.5 - m, oy - hw - 0.5 - m, ox + 0.5 + m, oy + hw + 0.5 + m, oz - 3.0 - m, oz + h + 0.5 + m],
         dict(wall="fwd", x=ox, y=oy + eng["lift"]["y"], w=eng["lift"]["width"], h=eng["lift"]["height"], z=oz), data="aquila_engineering.json",
         landing=[ox - 2.6, oy, oz])
    ox, oy, oz = hang["world_origin"]
    L, hw, h = hang["length"], hang["half_width"], hang["height"]
    tube = max(t["length"] for t in hang["tubes"])
    room("flight_deck", "Flight Deck", 9, 9, "B", "hangar", [ox - 0.5 - m, oy - hw - 0.5 - m, ox + L + tube + m, oy + hw + 0.5 + m, oz - 0.6 - m, oz + h + 0.3 + m],
         dict(wall="aft", x=ox, y=oy + hang["lift"]["y"], w=hang["lift"]["width"], h=hang["lift"]["height"], z=oz), data="aquila_hangar.json",
         landing=[ox + 2.5, oy, oz])
    ox, oy, oz = quar["world_origin"]
    room("quarters", "Captain's Quarters", 1, 1, "A", "quarters", [ox - quar["length"] - 0.3, oy - quar["half_width"], ox + 0.3, oy + quar["half_width"], oz - 0.3, oz + quar["height"] + 0.3],
         dict(wall="fwd", x=ox, y=oy + quar["door"]["y"], w=quar["door"]["width"], h=quar["door"]["height"], z=oz), data="aquila_quarters.json")
    return rooms


# ------------------------------------------------------------------------------------------------ geometry helpers
def rect_overlap(a, b, tol: float = 0.0) -> bool:
    """Do the plan rectangles [x0, y0, x1, y1] overlap by more than tol on both axes."""
    return min(a[2], b[2]) - max(a[0], b[0]) > tol and min(a[3], b[3]) - max(a[1], b[1]) > tol


def box_overlap(a, b, tol: float = 0.0) -> bool:
    """3D boxes [x0, y0, x1, y1, z0, z1]."""
    return (min(a[2], b[2]) - max(a[0], b[0]) > tol and min(a[3], b[3]) - max(a[1], b[1]) > tol
            and min(a[5], b[5]) - max(a[4], b[4]) > tol)


def rot(x: float, y: float, yaw_deg: float):
    a = math.radians(yaw_deg)
    c, s = math.cos(a), math.sin(a)
    return (x * c - y * s, x * s + y * c)


def place_local(origin, yaw_deg: float, lx: float, ly: float, lz: float = 0.0):
    """Local prefab point -> world: rotate by yaw (+x towards +y), then translate. origin = (x, y, z)."""
    rx, ry = rot(lx, ly, yaw_deg)
    return (origin[0] + rx, origin[1] + ry, origin[2] + lz)


def place_box(origin, yaw_deg: float, lo, hi):
    """Local axis-aligned box [(x0,y0,z0),(x1,y1,z1)] -> world axis-aligned [x0,y0,x1,y1,z0,z1] (yaw a multiple of 90)."""
    a = place_local(origin, yaw_deg, lo[0], lo[1], lo[2])
    b = place_local(origin, yaw_deg, hi[0], hi[1], hi[2])
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), max(a[2], b[2])]


# ------------------------------------------------------------------------------------------------ the JSON of the plan
def _scalar(o) -> bool:
    return o is None or isinstance(o, (bool, int, float, str))


def _fmt(o, depth: int, width: int = 150) -> str:
    """A compact, readable JSON: what fits a line goes on one line, long lists of scalars wrap, big lists / dicts take one item per line."""
    if _scalar(o):
        return json.dumps(o, ensure_ascii=False)
    flat = json.dumps(o, ensure_ascii=False, separators=(", ", ": "))
    if len(flat) + depth <= width:
        return flat
    pad = " " * (depth + 1)
    if isinstance(o, list):
        if all(_scalar(v) for v in o):
            lines, cur, n = [], [], 0
            for v in o:
                s = json.dumps(v, ensure_ascii=False)
                if cur and n + len(s) + 2 > width - depth - 2:
                    lines.append(", ".join(cur) + ",")
                    cur, n = [], 0
                cur.append(s)
                n += len(s) + 2
            lines.append(", ".join(cur))
            return "[\n" + "\n".join(pad + ln for ln in lines) + "\n" + " " * depth + "]"
        return "[\n" + ",\n".join(pad + _fmt(v, depth + 1, width) for v in o) + "\n" + " " * depth + "]"
    return "{\n" + ",\n".join(f"{pad}{json.dumps(k, ensure_ascii=False)}: {_fmt(v, depth + 1, width)}" for k, v in o.items()) + "\n" + " " * depth + "}"


def dumps(plan: dict) -> str:
    return _fmt(plan, 0) + "\n"


def save(plan: dict, path: str = PLAN_PATH) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(dumps(plan))


def load(path: str = PLAN_PATH) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
