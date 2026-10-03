"""ASN Aquila — Crew Berthing (Deck 3 · Section C), from data/ship/aquila_berths.json.

  SM_BERTH_Room      the compartment: a dark deck with a lighter aisle, blue-grey wainscot under pale panels, the ship's
                     frames every group of racks, a low ceiling crowded with cable trays and a pipe run, dimmed aisle
                     lights and red night lights at the skirting (somebody is always asleep); the lift in the forward
                     wall with the compartment's sign, the washroom door beside it; aft, a small lounge: a table with
                     four stools, the fleet news on the aft wall, a shelf of books and games, a coffee maker
  SM_BERTH_Stack_A   a stack of three racks (frame: origin on the deck at the rack's foot on the aisle, centred across it;
  SM_BERTH_Stack_B   +Y runs from the aisle to the head at the outboard wall; Z up): steel posts and pans, mattresses,
  SM_BERTH_Stack_C   rumpled blankets and pillows, a reading light and a net shelf at each head, the privacy curtains on
                     the aisle side (A: all drawn back; B: the top one closed; C: the middle one closed, the bottom half)
  SM_BERTH_Lockers   the column between two stacks (same frame): two tall lockers facing the aisle, a pier behind them

Coordinates are Unreal's (X forward, Y starboard, Z up); the helpers flip Y for Blender.
blender -b --factory-startup --python-exit-code 1 -P art/blender/berths.py -- art/export/berths [--preview <dir>]
"""
from __future__ import annotations

import json
import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
from medbay import blob, box, curtain, cyl, screen, soft  # noqa: E402
from quarters import wall_with_holes  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_berths.json"), encoding="utf-8"))
LEN, HW, H = D["length"], D["half_width"], D["height"]
ST = D["stacks"]
RW, RL, YF = ST["rack_width"], ST["rack_length"], ST["y_foot"]
LW = ST["locker_width"]
LEVELS = ST["rack_heights"]
FIN = 0.06

FLOOR, WALL, PANEL = "MI_MESS_Floor", "MI_MESS_Wall", "MI_MESS_Panel"
TABLE, SEAT = "MI_MESS_Table", "MI_MESS_Seat"
LINEN, BLANKET = "MI_MED_Linen", "MI_MED_Blanket"
LOCKER, NIGHT, READING = "MI_BERTH_Locker", "MI_BERTH_NightLight", "MI_BERTH_Reading"
SIGN, HEAD_SIGN = "MI_SIGN_Berth_3C", "MI_SIGN_Head"
NEWS = "MI_UI_Mess_News"                         # the same live page as the Mess Hall's news wall
STEEL, FRAME = A.MAT_TRIM, A.MAT_STRUCTURE
BOOKS = [LINEN, BLANKET, "MI_MED_Red", "MI_MESS_Board", LOCKER]


def group_x(g: int) -> float:
    """The forward edge of a group (two stacks and their locker column), going aft."""
    return ST["x_start"] - g * (2 * RW + LW)


# ------------------------------------------------------------------------------------------------ the compartment
def room():
    """The compartment's mesh: ARTE-INTERNI rebuilt it in the kit's language (art/blender/ship_berths.py: the same frame, the lift, the washroom door, the lounge with its four stools; the
    shell, the pilasters at the locker columns, the beams, the aisle lights and the night lights of the rooms of the plan). room_v1 below is the M1 compartment it replaces."""
    import ship_berths
    return ship_berths.room("SM_BERTH_Room")


def room_v1():
    b = A.Builder()
    rng = random.Random(3)
    lift, hd, lo = D["lift"], D["head_door"], D["lounge"]
    AW = D["aisle_half_width"]
    # the deck: structure, a dark covering, the aisle a shade lighter
    box(b, -LEN, 0, -HW, HW, -0.3, -0.02, FRAME)
    box(b, -LEN, 0, -HW, HW, -0.02, 0.0, FLOOR)
    box(b, -LEN + 0.2, -0.3, -AW + 0.1, AW - 0.1, 0.0, 0.004, PANEL)
    # the walls: wainscot to 1.0 m, pale panels above; openings: the lift, the washroom door
    lift_hole = [(lift["y"] - lift["width"] / 2, lift["y"] + lift["width"] / 2, 0.0, lift["height"])]
    head_hole = [(hd["y"] - hd["width"] / 2, hd["y"] + hd["width"] / 2, 0.0, hd["height"])]
    for (axis, p0, p1, u0, u1, holes) in (("x", -FIN, 0.0, -HW, HW, lift_hole + head_hole), ("x", -LEN, -LEN + FIN, -HW, HW, []),
                                          ("y", -HW, -HW + FIN, -LEN, 0.0, []), ("y", HW - FIN, HW, -LEN, 0.0, [])):
        wall_with_holes(b, axis, p0, p1, u0, u1, 0.0, 1.0, holes, PANEL)
        wall_with_holes(b, axis, p0, p1, u0, u1, 1.0, H, holes, WALL)
    wall_with_holes(b, "x", 0.0, 0.3, -HW - 0.05, HW + 0.05, -0.3, H + 0.3, lift_hole + head_hole, FRAME)
    box(b, -LEN - 0.3, -LEN, -HW - 0.05, HW + 0.05, -0.3, H + 0.3, FRAME)
    for ys in (-1, 1):
        wall_with_holes(b, "y", HW if ys > 0 else -HW - 0.3, HW + 0.3 if ys > 0 else -HW, -LEN - 0.3, 0.3, -0.3, H + 0.3, [], FRAME)
    # the washroom door (closed), its frame and a small sign above it
    dy0, dy1 = hd["y"] - hd["width"] / 2, hd["y"] + hd["width"] / 2
    box(b, 0.02, 0.08, dy0, dy1, 0.0, hd["height"], PANEL)
    box(b, -0.03, 0.02, dy0 + 0.05, dy1 - 0.05, 0.05, hd["height"] - 0.05, LOCKER)
    box(b, -0.06, -0.03, dy1 - 0.2, dy1 - 0.12, 0.95, 1.1, STEEL)                  # the handle
    for (y0, y1, z0, z1) in ((dy0 - 0.08, dy0, 0.0, hd["height"] + 0.08), (dy1, dy1 + 0.08, 0.0, hd["height"] + 0.08),
                             (dy0, dy1, hd["height"], hd["height"] + 0.08)):
        box(b, -0.08, 0.3, y0, y1, z0, z1, STEEL)
    screen(b, -0.012, hd["y"], hd["height"] + 0.22, 180.0, 0.56, 0.14, HEAD_SIGN)
    # the lift's frame, the compartment's sign over it, a light
    ly0, ly1 = lift["y"] - lift["width"] / 2, lift["y"] + lift["width"] / 2
    for (y0, y1, z0, z1) in ((ly0 - 0.14, ly0, 0.0, lift["height"] + 0.14), (ly1, ly1 + 0.14, 0.0, lift["height"] + 0.14),
                             (ly0, ly1, lift["height"], lift["height"] + 0.14)):
        box(b, -0.12, 0.3, y0, y1, z0, z1, STEEL)
    screen(b, -0.012, 2.35, 2.05, 180.0, 1.2, 0.3, SIGN)
    # skirting all round, and the red night lights low on the walls between the stacks
    for (y0, y1) in ((-HW + FIN, -HW + FIN + 0.04), (HW - FIN - 0.04, HW - FIN)):
        box(b, -LEN + FIN, -FIN, y0, y1, 0.0, 0.1, FRAME)
    # the ship's frames: one at each group (pilasters on the side walls, a beam across the ceiling)
    frames = [group_x(g) - 2 * RW - LW / 2 for g in range(ST["groups"])]
    for x in frames:
        for (y0, y1) in ((-HW + FIN, -HW + FIN + 0.12), (HW - FIN - 0.12, HW - FIN)):
            box(b, x - 0.12, x + 0.12, y0, y1, 0.0, H, FRAME)
        box(b, x - 0.12, x + 0.12, -HW + FIN, HW - FIN, H - 0.26, H, FRAME)
    # the ceiling: panels; over the aisle cable trays, a pipe run and the dimmed aisle lights
    box(b, -LEN, 0, -HW, HW, H, H + 0.05, WALL)
    for ys in (-1, 1):
        y = ys * (AW - 0.18)
        box(b, -LEN + 0.2, -0.2, y - 0.16, y + 0.16, H - 0.12, H - 0.1, STEEL)      # the tray
        box(b, -LEN + 0.2, -0.2, y - 0.16, y - 0.14, H - 0.16, H - 0.1, STEEL)
        box(b, -LEN + 0.2, -0.2, y + 0.14, y + 0.16, H - 0.16, H - 0.1, STEEL)
        for k in range(3):                                                        # cable bundles in it
            cyl(b, (-LEN + 0.2, y - 0.08 + k * 0.08, H - 0.13), (-0.2, y - 0.08 + k * 0.08, H - 0.13), 0.022,
                "MI_ASTRA_Rubber", seg=8)
    cyl(b, (-LEN + 0.1, 0.35, H - 0.2), (-0.1, 0.35, H - 0.2), 0.07, STEEL, seg=14)   # the pipe run
    for x in [-1.4 - k * 2.5 for k in range(int((LEN - 2.5) / 2.5))]:
        box(b, x - 0.45, x + 0.45, -0.22, 0.08, H - 0.03, H, READING)             # the dimmed aisle lights (warm)
        box(b, x - 0.5, x + 0.5, -0.26, 0.12, H - 0.06, H - 0.02, STEEL)
    # --- the lounge, aft
    t = lo["table"]
    tx, ty = t["x"], t["y"]
    box(b, tx - t["length"] / 2, tx + t["length"] / 2, ty - t["width"] / 2, ty + t["width"] / 2, t["height"] - 0.04, t["height"], TABLE)
    cyl(b, (tx, ty, 0.0), (tx, ty, t["height"] - 0.04), 0.06, STEEL, seg=12)
    box(b, tx - 0.35, tx + 0.35, ty - 0.3, ty + 0.3, 0.0, 0.03, STEEL)
    for (sx, sy) in ((tx + 0.75, ty - 0.85), (tx - 0.75, ty - 0.85), (tx + 0.75, ty + 0.85), (tx - 0.75, ty + 0.85)):
        cyl(b, (sx, sy, 0.0), (sx, sy, 0.44), 0.035, STEEL, seg=10)
        cyl(b, (sx, sy, 0.44), (sx, sy, 0.48), 0.19, SEAT, seg=20)
        cyl(b, (sx, sy, 0.02), (sx, sy, 0.04), 0.16, STEEL, seg=16)
    # a few things on the table: mugs, a deck of cards, a book face down
    for (mx, my) in ((tx + 0.4, ty - 0.2), (tx - 0.5, ty + 0.25), (tx + 0.1, ty + 0.3)):
        cyl(b, (mx, my, t["height"]), (mx, my, t["height"] + 0.1), 0.04, "MI_MESS_Cup", seg=14)
    box(b, tx - 0.15, tx - 0.06, ty - 0.1, ty + 0.04, t["height"], t["height"] + 0.02, "MI_MESS_Board")
    box(b, tx + 0.2, tx + 0.42, ty + 0.05, ty + 0.2, t["height"], t["height"] + 0.03, "MI_MED_Red")
    # the fleet news on the aft wall, in a steel frame
    sc = lo["screen"]
    sw, sh = sc["y1"] - sc["y0"], sc["z1"] - sc["z0"]
    box(b, -LEN + FIN, -LEN + FIN + 0.05, sc["y0"] - 0.06, sc["y1"] + 0.06, sc["z0"] - 0.06, sc["z1"] + 0.06, FRAME)
    screen(b, -LEN + FIN + 0.056, (sc["y0"] + sc["y1"]) / 2, (sc["z0"] + sc["z1"]) / 2, 0.0, sw, sh, NEWS)
    # a shelf of books and games on the starboard aft wall, the coffee maker beside it
    sy0 = HW - FIN - 0.3
    for z in (0.9, 1.35, 1.8):
        box(b, -LEN + 0.4, -LEN + 1.9, sy0, HW - FIN, z - 0.025, z, STEEL)
        x = -LEN + 0.45
        while x < -LEN + 1.8:
            w = rng.uniform(0.025, 0.05)
            hgt = rng.uniform(0.16, 0.27)
            if rng.random() < 0.15:
                box(b, x, x + 0.22, sy0 + 0.02, HW - FIN - 0.02, z, z + 0.06, rng.choice(BOOKS))   # a game box, flat
                x += 0.24
                continue
            box(b, x, x + w, sy0 + 0.04, HW - FIN - 0.02, z, z + hgt, rng.choice(BOOKS))
            x += w + 0.004
    box(b, -LEN + 2.2, -LEN + 2.7, HW - FIN - 0.45, HW - FIN, 0.0, 0.95, PANEL)       # the coffee maker's cabinet
    box(b, -LEN + 2.25, -LEN + 2.65, HW - FIN - 0.36, HW - FIN - 0.02, 0.95, 1.38, STEEL)
    box(b, -LEN + 2.3, -LEN + 2.6, HW - FIN - 0.37, HW - FIN - 0.35, 1.15, 1.3, "MI_ASTRA_Rubber")
    box(b, -LEN + 2.4, -LEN + 2.5, HW - FIN - 0.38, HW - FIN - 0.36, 1.32, 1.35, NIGHT)
    return A.finish(b.to_object("SM_BERTH_Room"), bevel=0.006)


# ------------------------------------------------------------------------------------------------ a stack of racks
def rack_bedding(b, h, rng, top: bool):
    """The mattress, a rumpled blanket and a pillow on the pan at height h (stack frame)."""
    blob(b, (0.0, RL / 2, h + 0.1), (RW - 0.06, RL - 0.06, 0.12), LINEN, e=0.12, ez=0.35)
    # the blanket: most of the length from the foot, rumpled (a few lumps), sometimes thrown back
    back = rng.random() < 0.35
    y0, y1 = (0.05, RL * 0.5) if back else (0.05, RL * 0.72)
    blob(b, (0.0, (y0 + y1) / 2, h + 0.175), (RW - 0.02, y1 - y0, 0.07), BLANKET, e=0.2, ez=0.5)
    for _ in range(3):
        blob(b, (rng.uniform(-0.25, 0.25), rng.uniform(y0 + 0.2, y1 - 0.2), h + 0.2), (rng.uniform(0.18, 0.32), rng.uniform(0.2, 0.4), 0.06),
             BLANKET, e=0.5, ez=0.7, yaw_deg=rng.uniform(0, 180))
    if back:
        blob(b, (0.0, y1 + 0.08, h + 0.2), (RW - 0.06, 0.2, 0.1), BLANKET, e=0.3, ez=0.6)      # the fold
    blob(b, (rng.uniform(-0.08, 0.08), RL - 0.3, h + 0.2), (0.5, 0.3, 0.1), LINEN, e=0.35, ez=0.6, yaw_deg=rng.uniform(-8, 8))


def stack(name: str, variant: str, seed: int):
    b = A.Builder()
    rng = random.Random(seed)
    top_z = LEVELS[-1] + 0.85
    # the frame: four posts, the head panel, the side sheets
    for x in (-RW / 2 + 0.02, RW / 2 - 0.02):
        for y in (0.03, RL - 0.03):
            cyl(b, (x, y, 0.0), (x, y, top_z), 0.022, STEEL, seg=10)
    box(b, -RW / 2, RW / 2, RL - 0.02, RL + 0.01, 0.0, top_z, FRAME)
    for x in (-RW / 2, RW / 2 - 0.012):
        box(b, x, x + 0.012, 0.08, RL - 0.02, 0.05, top_z, PANEL)
    box(b, -RW / 2, RW / 2, 0.0, RL + 0.01, top_z, top_z + 0.03, FRAME)                 # the top
    # the storage drawer under the bottom rack
    box(b, -RW / 2 + 0.03, RW / 2 - 0.03, 0.02, RL - 0.05, 0.03, LEVELS[0] - 0.02, LOCKER)
    box(b, -0.15, 0.15, -0.012, 0.02, LEVELS[0] - 0.12, LEVELS[0] - 0.09, STEEL)
    for i, h in enumerate(LEVELS):
        box(b, -RW / 2 + 0.01, RW / 2 - 0.01, 0.02, RL - 0.02, h, h + 0.04, STEEL)      # the pan
        box(b, -RW / 2 + 0.01, RW / 2 - 0.01, -0.01, 0.03, h + 0.04, h + 0.11, STEEL)   # the lip on the aisle side
        rack_bedding(b, h + 0.04, rng, i == len(LEVELS) - 1)
        ceil = LEVELS[i + 1] if i + 1 < len(LEVELS) else top_z
        # the reading light under the rack above, at the head, and a net shelf on the head panel
        box(b, -0.12, 0.12, RL - 0.34, RL - 0.26, ceil - 0.025, ceil - 0.005, READING)
        box(b, -0.3, 0.3, RL - 0.07, RL - 0.02, h + 0.35, h + 0.37, STEEL)
        box(b, -0.3, 0.3, RL - 0.07, RL - 0.065, h + 0.24, h + 0.37, "MI_ASTRA_Rubber")
        if rng.random() < 0.6:                                                        # something on the shelf
            box(b, -0.2, -0.05, RL - 0.07, RL - 0.03, h + 0.37, h + 0.52, rng.choice(BOOKS))
        # the curtain rail and the curtain on the aisle side
        cyl(b, (-RW / 2, -0.02, ceil - 0.03), (RW / 2, -0.02, ceil - 0.03), 0.009, STEEL, seg=8)
        closed = (variant == "B" and i == 2) or (variant == "C" and i == 1)
        half = variant == "C" and i == 0
        z0, z1 = h + 0.12, ceil - 0.04
        if closed:
            curtain(b, (-RW / 2 + 0.02, -0.04), (RW / 2 - 0.02, -0.04), z0, z1, amp=0.02, wave=0.14)
        elif half:
            curtain(b, (RW / 2 - 0.02 - RW * 0.5, -0.04), (RW / 2 - 0.02, -0.04), z0, z1, amp=0.025, wave=0.12)
        else:
            curtain(b, (RW / 2 - 0.16, -0.04), (RW / 2 - 0.02, -0.04), z0, z1, amp=0.03, wave=0.05)   # drawn back
    obj = b.to_object(name)
    return soft(obj, texel=0.6)


def lockers():
    b = A.Builder()
    w = LW
    d = 0.55
    box(b, -w / 2, w / 2, 0.0, d, 0.0, 2.1, LOCKER)                                    # the body
    for z0, z1 in ((0.05, 1.03), (1.07, 2.05)):
        box(b, -w / 2 + 0.03, w / 2 - 0.03, -0.012, 0.0, z0, z1, LOCKER)               # the door
        for k in range(4):                                                            # vents
            box(b, -0.12, 0.12, -0.016, -0.012, z1 - 0.12 - k * 0.03, z1 - 0.11 - k * 0.03, FRAME)
        box(b, w / 2 - 0.1, w / 2 - 0.07, -0.04, -0.012, (z0 + z1) / 2 - 0.08, (z0 + z1) / 2 + 0.08, STEEL)   # handle
        box(b, -0.1, 0.1, -0.015, -0.012, z0 + 0.2, z0 + 0.25, PANEL)                  # the name tag
    box(b, -w / 2, w / 2, d, RL + 0.01, 0.0, H, FRAME)                                 # the pier behind, to the wall
    cyl(b, (0.0, d + 0.2, 0.0), (0.0, d + 0.2, H), 0.05, STEEL, seg=12)
    return A.finish(b.to_object("SM_BERTH_Lockers"), bevel=0.004)


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out_dir = argv[0] if argv else "art/export/berths"
    preview = argv[argv.index("--preview") + 1] if "--preview" in argv else None
    A.reset_scene()
    A.clear_objects()
    os.makedirs(out_dir, exist_ok=True)
    objs = {"SM_BERTH_Room": room(), "SM_BERTH_Lockers": lockers()}
    for k, v in enumerate("ABC"):
        objs[f"SM_BERTH_Stack_{v}"] = stack(f"SM_BERTH_Stack_{v}", v, 11 + k)
    for nm, o in objs.items():
        A.export_fbx(o, os.path.join(out_dir, nm + ".fbx"))
        print("BERTHS_OK", nm, A.stats(o))
    if preview:
        os.makedirs(preview, exist_ok=True)
        for nm in ("SM_BERTH_Stack_C", "SM_BERTH_Lockers"):
            for other in objs.values():
                other.hide_render = other is not objs[nm]
            A.render_preview([objs[nm]], os.path.join(preview, nm + ".png"), view=(100.0, 12.0))
        interior_preview(objs, preview)


def layout():
    """Where the stacks and locker columns go (UE frame): (mesh, x, y, yaw) — the game's build script uses the same."""
    out = []
    for g in range(ST["groups"]):
        xg = ST["x_start"] - g * (2 * RW + LW)
        v = ST["variants"][g % len(ST["variants"])]
        for side in (1, -1):
            for k in range(2):
                vv = v if (k + (side > 0)) % 2 else "ABC"[("ABC".index(v) + 1) % 3]
                out.append((f"SM_BERTH_Stack_{vv}", xg - RW / 2 - k * RW, side * YF, 0.0 if side > 0 else 180.0))
            out.append(("SM_BERTH_Lockers", xg - 2 * RW - LW / 2, side * YF, 0.0 if side > 0 else 180.0))
    return out


def interior_preview(objs, preview):
    """A look down the aisle from the lift, the racks placed as in the game (Workbench render)."""
    import bpy
    for o in objs.values():
        o.hide_render = o.name not in ("SM_BERTH_Room",)
    placed = []
    for mesh, x, y, yaw in layout():
        src = objs[mesh]
        dup = src.copy()
        bpy.context.scene.collection.objects.link(dup)
        dup.location = (x, -y, 0.0)
        dup.rotation_euler = (0.0, 0.0, math.radians(-yaw))
        dup.hide_render = False
        placed.append(dup)
    for tag, loc, rot in (("aisle", (-0.8, 0.0, 1.62), (math.radians(84), 0.0, math.radians(90))),
                          ("lounge", (-17.0, -0.9, 1.7), (math.radians(80), 0.0, math.radians(100)))):
        cam_data = bpy.data.cameras.new("C_" + tag)
        cam_data.lens = 16
        cam = bpy.data.objects.new("C_" + tag, cam_data)
        bpy.context.scene.collection.objects.link(cam)
        cam.location = loc
        cam.rotation_euler = rot
        scene = bpy.context.scene
        scene.camera = cam
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.shading.light = "STUDIO"
        scene.display.shading.color_type = "MATERIAL"
        scene.display.shading.show_cavity = True
        scene.display.shading.show_shadows = False
        scene.render.resolution_x, scene.render.resolution_y = 1100, 700
        palette = {"MI_MESS_Floor": (0.18, 0.18, 0.19, 1), "MI_MESS_Wall": (0.72, 0.72, 0.7, 1), "MI_MESS_Panel": (0.36, 0.42, 0.48, 1),
                   "MI_BERTH_Locker": (0.42, 0.47, 0.5, 1), "MI_MED_Linen": (0.85, 0.85, 0.82, 1), "MI_MED_Blanket": (0.2, 0.26, 0.38, 1),
                   "MI_MED_Curtain": (0.3, 0.36, 0.42, 1), "MI_BERTH_Reading": (1.0, 0.8, 0.5, 1), "MI_BERTH_NightLight": (0.9, 0.1, 0.1, 1),
                   "MI_ASTRA_Structure": (0.1, 0.1, 0.11, 1), "MI_ASTRA_Trim": (0.5, 0.5, 0.52, 1), "MI_ASTRA_Rubber": (0.04, 0.04, 0.04, 1),
                   "MI_UI_Mess_News": (0.05, 0.2, 0.45, 1), "MI_MESS_Table": (0.4, 0.3, 0.2, 1), "MI_MESS_Seat": (0.15, 0.2, 0.3, 1)}
        for m in bpy.data.materials:
            m.diffuse_color = palette.get(m.name, (0.6, 0.6, 0.6, 1))
        scene.render.filepath = os.path.join(preview, f"berths_{tag}.png")
        bpy.ops.render.render(write_still=True)


if __name__ == "__main__":
    main()
