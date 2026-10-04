"""ABBORDAGGI-3 — the boarding kit: what the decks of a boarded ship are dressed with (pure Python, no bpy).

The single place of the kit's names and sizes: `art/blender/board_kit.py` builds the meshes to these sizes, the importer (`tools/ue_scripts/import_board_kit.py`) and the game's dressing
(`Source/ASTRA/AstraBoardDress.*`, which reads `data/ship/board_kit.json` that the generator writes) place them by them.

A piece has its own frame (the layout frame of the Aquila's kit: X forward, Y to starboard, Z up; metres in Blender, centimetres in the engine):

  wall pieces      x along the wall to the viewer's right (as he faces the wall from the room), y INTO THE ROOM from the wall's inner face (the relief grows towards +y), z up from the floor
  ceiling pieces   x along the run, y across it, z DOWN from the ceiling's plane (the piece hangs: z <= 0)
  floor pieces     x, y on the floor, z up from it (a few centimetres)
  opening pieces   x across the opening (the middle of the opening is x = 0), y through the wall (the plane between the two rooms is y = 0), z up from the floor
  props, bodies    origin on the floor under the middle of the footprint; x is the front (the side a man uses), y to his right, z up

A mesh is one static mesh of the instanced set of its kind: the game makes one instanced component for each kind that a deck uses (a draw for each).
"""
from __future__ import annotations

# material slots (the engine's instances of the same name: tools/ue_scripts/make_board_materials.py makes them from M_ASTRA_Hard / M_ASTRA_Emissive; the lamps are the bridge's palette lamps)
PLATE = "MI_BRD_Plating"          # basalt plates (the Mandate's hulls are basalt and graphite: docs/STILE.md §3)
FRAME = "MI_BRD_Frame"            # graphite frames and ribs
IRON = "MI_BRD_Iron"              # black iron: the oldest, heaviest parts
COPPER = "MI_BRD_Copper"          # oxidised copper pipes and fittings
VERD = "MI_BRD_Verdigris"         # verdigris: the green of old copper, the Mandate's second accent
DECK = "MI_BRD_Deck"              # diamond plate
HAZARD = "MI_BRD_Hazard"          # hazard paint: worn amber
SOOT = "MI_BRD_Soot"              # black: soot, burnt plating
STENCIL = "MI_BRD_Stencil"        # stencil paint: bronze-white, worn (their lettering)
CLOTH = "MI_BRD_Cloth"            # rust-red cloth: banners, bedding
UNIFORM = "MI_BRD_Uniform"        # dark uniform cloth (the fallen)
RUBBER = "MI_ASTRA_Rubber"        # cable jackets (the Aquila's own)
LAMP = "MI_BRG3_Lamps"            # the palette's emissive cells (amber, red...)
LAMP_DIM = "MI_BRG3_LampsDim"
LAMP_HOT = "MI_BRG3_LampsHot"
SCREEN = "MI_BRD_Screen"          # a dead console's screen: dark glass with a trace of amber

SLOTS = [PLATE, FRAME, IRON, COPPER, VERD, DECK, HAZARD, SOOT, STENCIL, CLOTH, UNIFORM, SCREEN]      # the ones the board kit makes (the rest are the Aquila's)

# the sizes the game places by (metres): wall bays are modules of BAY_W; ceiling runs of RUN_L; floor plates of PLATE_M
BAY_W = 2.0
BAY_H = 2.6
RIB_W, RIB_D, RIB_H = 0.22, 0.16, 3.0
RUN_L = 2.0
PLATE_M = 2.0
DOOR_W, DOOR_H = 1.6, 2.4         # a pressure door's opening (the plan's: AAstraDoor)
BLAST_W, BLAST_H = 2.0, 2.4       # a section bulkhead's
FRAME_DEPTH = 0.40                # an opening's frame stands in both walls (the two rooms' 12 cm walls side by side, and a little more)

# the pieces: key -> (mesh name, kind of frame, collides, what it is). Sizes are measured from the built mesh and written to data/ship/board_kit.json.
PIECES = {
    # walls: 2 m bays (and a 1 m filler), full-height ribs, the cornice, the lintel band
    "wall_a": ("SM_BRD_WallA", "wall", False, "riveted plate bay with a handrail and a stencil panel"),
    "wall_b": ("SM_BRD_WallB", "wall", False, "pipe bank: three runs of copper with a valve wheel"),
    "wall_c": ("SM_BRD_WallC", "wall", False, "louvre and junction box"),
    "wall_d": ("SM_BRD_WallD", "wall", False, "locker front"),
    "wall_e": ("SM_BRD_WallE", "wall", False, "hatch bay"),
    "wall_f": ("SM_BRD_WallF", "wall", False, "burnt and torn bay (a room the war has damaged)"),
    "wall_motto": ("SM_BRD_WallMotto", "wall", False, "plate bay with the Mandate's motto stencilled across it"),
    "wall_hold": ("SM_BRD_WallHold", "wall", False, "plate bay stencilled HOLD FAST"),
    "wall_plain": ("SM_BRD_WallPlain", "wall", False, "1 m filler"),
    "rib": ("SM_BRD_Rib", "wall", False, "full-height structural rib"),
    "cornice": ("SM_BRD_Cornice", "wall", False, "beam along the top of a tall wall"),
    "header": ("SM_BRD_Header", "wall", False, "band over a door, up to the ceiling"),
    # ceilings
    "pipes": ("SM_BRD_Pipes", "ceiling", False, "two pipes on clamps"),
    "tray": ("SM_BRD_Tray", "ceiling", False, "cable tray"),
    "lamp": ("SM_BRD_Lamp", "ceiling", False, "caged lamp, lit"),
    "lamp_dead": ("SM_BRD_LampDead", "ceiling", False, "caged lamp, dark (the war has taken its power)"),
    "lamp_red": ("SM_BRD_LampRed", "ceiling", False, "caged lamp, the red of emergency lighting"),
    "vent": ("SM_BRD_Vent", "ceiling", False, "ceiling grille"),
    "cables": ("SM_BRD_Cables", "ceiling", False, "cable bundle hanging from a torn panel"),
    # floors
    "floor": ("SM_BRD_Floor", "floor", False, "2 x 2 m diamond plate"),
    "threshold": ("SM_BRD_Threshold", "floor", False, "hazard threshold at a door"),
    "guide": ("SM_BRD_Guide", "floor", False, "floor guide light, 2 m"),
    "debris": ("SM_BRD_Debris", "floor", False, "torn plating on the floor"),
    # openings
    "jamb": ("SM_BRD_Jamb", "opening", False, "door jamb"),
    "door_header": ("SM_BRD_DoorHeader", "opening", False, "door header"),
    "blast_jamb": ("SM_BRD_BlastJamb", "opening", False, "pressure bulkhead jamb"),
    "blast_header": ("SM_BRD_BlastHeader", "opening", False, "pressure bulkhead header with the beacon"),
    "blast_leaf": ("SM_BRD_BlastLeaf", "opening", False, "the leaf of a pressure bulkhead"),
    # props
    "crate": ("SM_BRD_Crate", "prop", True, "supply crate"),
    "crate_long": ("SM_BRD_CrateLong", "prop", True, "long crate"),
    "barrel": ("SM_BRD_Barrel", "prop", True, "drum"),
    "locker": ("SM_BRD_Locker", "prop", True, "locker"),
    "rack": ("SM_BRD_Rack", "prop", True, "storage rack"),
    "bunk": ("SM_BRD_Bunk", "prop", True, "double bunk"),
    "table": ("SM_BRD_Table", "prop", True, "table"),
    "bench": ("SM_BRD_Bench", "prop", True, "bench"),
    "console": ("SM_BRD_Console", "prop", True, "console"),
    "machine": ("SM_BRD_Machine", "prop", True, "pump set"),
    "motor": ("SM_BRD_Motor", "prop", True, "motor housing"),
    "tank": ("SM_BRD_Tank", "prop", True, "tank"),
    "reactor": ("SM_BRD_Reactor", "prop", True, "reactor stack"),
    "breech": ("SM_BRD_Breech", "prop", True, "gun breech"),
    "bed": ("SM_BRD_Bed", "prop", True, "ward bed"),
    "cell": ("SM_BRD_Cell", "prop", True, "cell"),
    "barrier": ("SM_BRD_Barrier", "prop", True, "low barricade (cover)"),
    "banner": ("SM_BRD_Banner", "prop", False, "banner with the ferry mark"),
    # the fallen
    "body_a": ("SM_BRD_BodyA", "body", False, "a fallen man, on his back"),
    "body_b": ("SM_BRD_BodyB", "body", False, "a fallen man, face down"),
    "body_c": ("SM_BRD_BodyC", "body", False, "a fallen man, on his side"),
}

# the lettering the kit carries (English: the game's language; the Mandate's own words)
MOTTO = "WE FERRY OUR PEOPLE BEYOND THE NIGHT"
