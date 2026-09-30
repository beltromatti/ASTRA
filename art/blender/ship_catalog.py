"""ASN Aquila interior kit (NAVE): the catalogue of modules and room prefabs, in pure Python (no bpy): the single source of
the kit's dimensions, shared by the Blender generator (art/blender/ship_kit.py), the plan generator (ship_plan_gen.py),
the layout checks (ship_checks.py) and the Unreal import script (tools/ue_scripts/build_ship_interior.py).

The grid. Everything is laid out on a 4 m grid in plan (X forward, Y starboard, Z up; metres; the bridge floor point under
the Captain's chair is the origin of the world). A corridor is a 4 m wide "slot": 3.1 m clear between the finished walls and
0.45 m of wall on each side (finish + structure), so a corridor module is 4 m long and 4 m wide, a junction is a 4 x 4 cell,
and rooms that line a corridor are multiples of 4 m in both directions with their doors on a module centre.

Module frame (Blender/Unreal mesh space, layout convention: X forward, Y starboard, Z up): origin on the floor, on the
centre line, at the AFT end of the module; the module runs to x = 4. Rooms: origin on the floor at the corridor-side corner
of the room, x along the corridor, y INTO the room (away from the corridor wall's outer face), z up. To put a room on the
port side of a corridor (or to the aft of a passage that runs along y) the layout rotates it (yaw 180 / +-90).
"""
from __future__ import annotations

MOD = 4.0                      # module length and slot width
CLEAR_W = 3.1                  # corridor clear width between the finished walls
HW = CLEAR_W / 2               # 1.55
WALL_T = 0.45                  # a corridor wall: finish + structure (the room behind it adds its own 0.25 finish)
SLOT_HW = HW + WALL_T          # 2.0: half of the 4 m slot
CLEAR_H = 3.4                  # clear height of a standard deck (floor to ceiling plane)
STRUCT_T = 0.3                 # floor structure below / ceiling structure above (deck pitch 4.0 = 0.3 + 3.4 + 0.3)
ROOM_WALL = 0.25               # the wall of a room prefab on its own side (finish + structure)
DOOR_W, DOOR_H = 1.6, 2.4      # the standard pressure door (AAstraDoor: width 160, height 240)
GATE_W, GATE_H = 3.2, 3.0      # a wide portal into a big space (two door leaves)
BLAST_W, BLAST_H = 2.0, 2.5    # the section blast door (2.0 wide: its two leaves slide into the frame's pillars and stay inside the 4 m slot)
HATCH_W, HATCH_H = 1.0, 2.0    # a cabin door

# palette cells of the corridor accents (tone -> (ribs/guide, ceiling strip))
TONES = {"S": {"accent": "command", "accent_dim": "command_dim", "strip": "white_cool"},        # the spine
         "P": {"accent": "engineering", "accent_dim": "engineering_dim", "strip": "white_warm"}}   # the passages

# ------------------------------------------------------------------------------------------------ corridor modules
# name suffix -> (left wall, right wall, aft end, fwd end); left = port (-y) when facing forward (+x), right = starboard.
# wall: "wall" plain | "door" | "gate" (3.2 m portal) | "branch" (a 3.1 m passage leaves the corridor here, open to the cell)
# end: "open" | "closed" (a bulkhead wall across the corridor) | "blast" (the section blast door frame)
CORRIDOR_SPECS = {
    "Straight_A": ("wall", "wall", "open", "open"),
    "Straight_B": ("wall", "wall", "open", "open"),
    "Straight_C": ("wall", "wall", "open", "open"),
    "Door_L_A": ("door", "wall", "open", "open"),
    "Door_L_B": ("door", "wall", "open", "open"),
    "Door_R_A": ("wall", "door", "open", "open"),
    "Door_R_B": ("wall", "door", "open", "open"),
    "Door_LR": ("door", "door", "open", "open"),
    "Gate_L": ("gate", "wall", "open", "open"),
    "Gate_R": ("wall", "gate", "open", "open"),
    "Gate_LR": ("gate", "gate", "open", "open"),
    "Bulkhead": ("wall", "wall", "open", "blast"),
    "T_L": ("branch", "wall", "open", "open"),
    "T_R": ("wall", "branch", "open", "open"),
    "X": ("branch", "branch", "open", "open"),
    "End": ("wall", "wall", "open", "closed"),
    "Corner_L": ("wall", "wall", "open", "open"),     # a turn to port: special geometry (see ship_corridor.corner)
}
# which module names exist for which tone (the whole family is built for both tones)
TONE_FAMILY = ["Straight_A", "Straight_B", "Straight_C", "Door_L_A", "Door_L_B", "Door_R_A", "Door_R_B", "Door_LR", "Gate_L",
               "Gate_R", "Gate_LR", "Bulkhead", "T_L", "T_R", "X", "End"]


def module_mesh(tone: str, suffix: str) -> str:
    return f"SM_SHIP_{tone}_{suffix}"


# ------------------------------------------------------------------------------------------------ vertical links
STAIR_RISE = 4.0               # deck to deck
STAIR_TOWER = (8.0, 8.0)       # plan footprint of a stair tower (x, y) in local frame: a 2 x 2 cell block
