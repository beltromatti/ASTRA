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
# tone K = the crawlways: a 1.7 m wide, 2.5 m high maintenance tunnel in the same 4 x 4 m slot (the walls are 1.15 m thick: pipes, frames; the hatch of a room is a
# short tunnel through them). They are the keel's three passages (Deck 12) and, since NAVE-3, the Jefferies arms that reach a trunk from a passage (docs/NAVE.md §4)
# tone V = the service corridors (NAVE-3): 2.1 m wide, 2.7 m high, the same slot (walls 0.95 m of pipes, chases and breaker boxes), a low warm light: the hull galleries
# along the flanks of Decks 5-12, where the lifepods, the airlocks and the repair stations are
# tone T = the Spine shuttle's tunnel (NAVE-3): 3.5 m wide, 3.25 m high, a track bed and a service ledge; nobody walks it, the car runs in it
CRAWL_HW, CRAWL_H = 0.85, 2.5
SERV_HW, SERV_H = 1.05, 2.7
TUNNEL_HW, TUNNEL_H = 1.75, 3.25
TONE_DIMS = {"S": (1.55, 3.4), "P": (1.55, 3.4), "K": (CRAWL_HW, CRAWL_H), "V": (SERV_HW, SERV_H), "T": (TUNNEL_HW, TUNNEL_H)}    # tone -> (half of the clear width, clear height)
TONES = {"S": {"accent": "command", "accent_dim": "command_dim", "strip": "white_cool"},        # the spine
         "P": {"accent": "engineering", "accent_dim": "engineering_dim", "strip": "white_warm"},   # the passages
         "K": {"accent": "engineering", "accent_dim": "engineering_dim", "strip": "white_warm"},   # the crawlways
         "V": {"accent": "amber", "accent_dim": "amber_dim", "strip": "white_warm"},               # the service corridors
         "T": {"accent": "cyan", "accent_dim": "cyan_dim", "strip": "white_cool"}}                 # the shuttle tunnel
# the corridor lengths of a walker's world: the width a person passes (VITA, the route finder) for an edge of each tone
TONE_WALK_W = {"S": 3.1, "P": 3.1, "K": 1.7, "V": 2.1, "T": 3.5}

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
}
# which module names exist for which tone (the whole family is built for the corridor tones S, P, K and the service tone V)
TONE_FAMILY = ["Straight_A", "Straight_B", "Straight_C", "Door_L_A", "Door_L_B", "Door_R_A", "Door_R_B", "Door_LR", "Gate_L",
               "Gate_R", "Gate_LR", "Bulkhead", "T_L", "T_R", "X", "End"]
# the shuttle tunnel has a short family: straight cells (two variants), the section's blast gate and the closed end of the line (the depot's wall)
TUNNEL_FAMILY = ["Straight_A", "Straight_B", "Bulkhead", "End"]
# a trunk module (NAVE-3): the 4 x 4 cell of a Jefferies arm that holds the vertical shaft and its ladder (K tone); three variants: a deck in the middle of the
# column (open above and below), the top of the column (a roof) and the bottom (a floor)
TRUNK_SUFFIXES = [t + e for t in ("Trunk", "TrunkTop", "TrunkBottom") for e in ("", "EndFwd", "EndAft")]     # (EndFwd / EndAft: a one-module arm's cell, closed on its far end)


def tone_family(tone: str) -> list[str]:
    if tone == "T":
        return TUNNEL_FAMILY
    return TONE_FAMILY + (TRUNK_SUFFIXES if tone == "K" else [])


def module_mesh(tone: str, suffix: str) -> str:
    return f"SM_SHIP_{tone}_{suffix}"


# ------------------------------------------------------------------------------------------------ lifts (NAVE-3)
# A turbolift shaft is 2.8 x 2.8 m inside (the car is 2.4 x 2.4 x 2.6: docs/brief/ASCENSORI.md), 3.2 x 3.2 m with its walls; a bank is a lobby 8 m long and as deep as the lane
# (16 m) between a main corridor and the passage beyond it, the shafts along its aft wall, so that it is also a cross link
LIFT_IN = 2.8                  # a shaft's clear width and depth
LIFT_OUT = 3.2                 # ... with its walls
LIFT_DOOR_W, LIFT_DOOR_H = 1.6, 2.4    # the landing opening in the lobby's wall (the lift's own frame and leaves go in it: AstraLift*, brief ASCENSORI)
# the bridge's lift housing on Deck 1: the block behind the port corridor's end (x -25.8 .. -21.0, y -8.2 .. -1.0: its outside is art/blender/quarters.py's `SM_SHIP_ASTRA_AquilaBridgeBlock`, a
# closed shell with a chamfered section: vertical faces up to z 3.15, the roof at 3.5) holds the vestibule of the two command shafts and the shafts' tubes (ship_rooms_lifts.lift_housing_bridge)
BRIDGE_SHAFT_X = -24.3             # the two command shafts' middle along x (3.0 m outside, 2.6 m inside)
BRIDGE_SHAFT_Y = (-6.7, -3.7)      # ... and their middle along y
HOUSING_ORIGIN = (-20.8, -1.22)    # where the housing's mesh is placed (yaw 180: its x runs aft, its y to port): the corridor's end, and 2 cm inside the block's starboard face
HOUSING_D = 6.96                   # its width (to 2 cm inside the block's port face, y -8.2)
TRUNK_IN = 1.2                 # a Jefferies trunk's clear width and depth (a ladder shaft)
TRUNK_NICHE = (1.45, 2.55)     # the trunk cell's ladder niche: its extent along the cell (m from the cell's aft end); the niche is 1.1 m deep, in the cell's aft wall (world -x: the cell is placed at yaw 90)
TRUNK_RUNG_T = 1.01            # the rungs' axis: this far into the niche from the walkway's wall face (the walkway's half width, CRAWL_HW, is where the niche starts)
TRUNK_CLIMB_GAP = 0.35         # where a climber's body centre goes: this far in front of the rungs' axis
TRUNK_RUNG_PITCH = 4.0 / 14    # the rungs' spacing: 14 to a deck (the deck pitch, 4 m), so the pattern is the same on every deck and the ladder runs unbroken through the floors (0.2857 m)
TRUNK_RUNG_Z0 = -0.13          # a deck's first rung: this far under its floor; rung k is at z0 + k * pitch
TRUNK_RAIL_GAP = 0.44          # the rails stand this far apart
TRUNK_HATCH = (1.0, 2.0)       # the hatch from a passage to a trunk cell

# ------------------------------------------------------------------------------------------------ wayfinding (ship_signs.py builds the meshes, ship_wayfinding.py places them)
WAY_ROW_H = 0.30               # a blade sign's row (pictogram, destination, arrow) is this tall; a blade is its frame (SM_SHIP_WayBlade_<rows>) with one SM_SHIP_WayRow_<dest><arrow> per row
WAY_HANGER = 0.26              # the rods from the ceiling to the top of the frame
WAY_FRAME_PAD = 0.03           # the frame's margin above the first row


# ------------------------------------------------------------------------------------------------ vertical links
STAIR_RISE = 4.0               # deck to deck
STAIR_TOWER = (8.0, 8.0)       # plan footprint of a stair tower (x, y) in local frame: a 2 x 2 cell block
