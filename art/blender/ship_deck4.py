"""ASN Aquila — Deck 4, the first complete deck: Crew Services (docs/BIBBIA.md §6: Mess Hall, galley, lounge, observation deck).

Deck 4 floor z = -46.0 (the Mess Hall's), clear height up to 3.8, sections A-H bow to stern:
  A [104, -104]   forward recreation and stores: the bow observation deck, library, games, quiet rooms, hydroponics, stores, heads, the crew
                  lounge next to the concourse, an observation deck on each flank
  B [-104, -160]  the hub: the Mess Concourse (lift landing, stairs, directory), the Mess Hall (existing), the main galley across the port
                  passage, the galley pass along the Mess kitchen, dry stores, the starboard flank observation deck
  C [-160, -248]  Crew Berthing (existing, its lobby), cold stores, stores
  D-H             the Spine towards the stern: hydroponics, laundry, heads, stores, quiet rooms, stairs (the Engineering hall blocks the centre
                  line between x -329 and -373 on this level: the side passages carry the traffic)
The Spine is the centre-line corridor (y = 0, tone S); the Starboard and Port Passages (y = +-20, tone P) run the whole length; cross links join
them across the inner lanes. Lanes: I = the inner rooms (16 m deep) off the Spine, O = the outer rooms (16 m deep) off a side passage.
Four stair-tower columns (STAIR_COLUMNS) run through every deck of the plan.
"""
from __future__ import annotations

import ship_plan as P
from ship_catalog import GATE_H, GATE_W
from ship_layout import Builder, Deck

DECK = 4
TAG = "d4"
SP_Y, SBP_Y, PP_Y = 0.0, 20.0, -20.0
STAIR_COLUMNS = [(44.0, +1), (-92.0, -1), (-300.0, +1), (-452.0, +1)]      # (x_min of the 8 x 8 m tower, side of the spine)


def tower_id(deck: int, x_min: float) -> str:
    return f"d{deck}_stair_{int(abs(x_min))}{'n' if x_min < 0 else 'p'}"


def T(x_min: float):
    return ("stair_tower", {"id": tower_id(DECK, x_min)})


def build(B: Builder) -> Deck:
    D = Deck(B, DECK, TAG)
    D.passage("SPF", "S", "x", SP_Y, -104.0, 84.0, "Spine (fwd)")           # from the concourse to the bow observation deck
    D.passage("SPM", "S", "x", SP_Y, -328.0, -204.0, "Spine (mid)")          # aft of the Berthing to the Engineering hall
    D.passage("SPA", "S", "x", SP_Y, -524.0, -376.0, "Spine (aft)")          # aft of the Engineering hall to the stern
    D.passage("SBP", "P", "x", SBP_Y, -524.0, 92.0, "Starboard Passage")
    D.passage("PP", "P", "x", PP_Y, -524.0, 92.0, "Port Passage")
    D.ends("SBP", fwd="wall", aft="wall")
    D.ends("PP", fwd="wall", aft="wall")
    D.ends("SPM", fwd="wall", aft="wall")
    D.ends("SPA", fwd="wall", aft="wall")
    # SPF is open at the concourse (aft) and at the bow observation deck (fwd)

    # ---- the Spine, fore part (Section A): inner lanes, x 80 -> -104
    # (every list adds up: a lane runs from x_start to the section's end exactly, the cross links of both sides fall on the same module: an X)
    D.lane("SPF", +1, 80.0, [("library",), ("gap", 8), ("link", "SBP"), T(44.0), ("games",), ("hydro",), ("hold",), ("gap", 4), ("link", "SBP"),
                             ("laundry",), ("heads",), ("gap", 8), ("quiet",), ("lounge",)], "I_s spine fwd")
    D.lane("SPF", -1, 80.0, [("hold",), ("link", "PP"), ("heads",), ("laundry",), ("store_cold",), ("hydro",), ("gap", 12), ("link", "PP"), ("library",),
                             ("quiet",), ("heads",), ("gap", 8), T(-92.0), ("gap", 12)], "I_p spine fwd")
    # ---- the side passages' outer rooms (16 m deep)
    D.lane("SBP", +1, 12.0, [("observation",), ("gap", 92), ("observation", {"door_x": 14.0}), ("hold",), ("gap", 8), ("hold",), ("gap", 64)], "O_s")
    D.lane("PP", -1, 12.0, [("observation",), ("gap", 92), ("store_dry", {"door_x": 10.0}), ("galley",), ("gap", 8), ("store_cold",), ("hold",)], "O_p")
    # ---- the galley pass along the Mess kitchen (inner lane of the port passage, four metres deep)
    D.lane("PP", +1, -124.0, [("galley_pass",)], "I_p galley")
    # ---- aft of the Berthing: the mid spine, x -204 -> -328
    D.lane("SPM", +1, -204.0, [("gap", 4), ("hold",), ("gap", 16), ("hydro",), ("link", "SBP"), ("laundry",), ("gap", 4), T(-300.0), ("quiet",), ("gap", 16)],
           "I_s spine mid")
    D.lane("SPM", -1, -204.0, [("gap", 4), ("store_dry",), ("gap", 16), ("hold",), ("link", "PP"), ("library",), ("quiet",), ("gap", 24)], "I_p spine mid")
    # ---- the aft spine (stern side of the Engineering hall): sections E (8 m), F [-384, -440], G [-440, -484], H [-484, -524]
    D.lane("SPA", +1, -376.0, [("gap", 8), ("hold",), ("link", "SBP"), ("hydro",), ("gap", 8), T(-452.0), ("laundry",), ("heads",), ("gap", 8), ("hold",),
                               ("gap", 16)], "I_s spine aft")
    D.lane("SPA", -1, -376.0, [("gap", 8), ("store_dry",), ("link", "PP"), ("library",), ("quiet",), ("heads",), ("laundry",), ("gap", 20), ("hold",),
                               ("gap", 16)], "I_p spine aft")
    specials(B, D)
    return D


def specials(B: Builder, D: Deck) -> None:
    """The hub: concourse, berthing lobby, bow observation deck; their gates onto the side passages."""
    D.special("d4_bow_obs", "bow_obs", (84.0, -16.0), 0.0, [84.0, -16.0, 104.0, 16.0], "A", plate="bow_obs")
    rc = D.special("d4_concourse", "concourse", (-121.7, -18.0), 0.0, [-121.7, -18.0, -104.0, 18.0], "B", plate="concourse")
    for x in (-118.0, -110.0):
        D.gate(rc, f"d4_gate_conc_sbp_{int(-x)}", "SBP", x, -1, GATE_W, GATE_H)
        D.gate(rc, f"d4_gate_conc_pp_{int(-x)}", "PP", x, +1, GATE_W, GATE_H)
    rl = D.special("d4_berth_lobby", "berth_lobby", (-175.3, -18.0), 0.0, [-175.3, -18.0, -160.7, 18.0], "C")
    for x in (-166.0, -170.0):
        D.gate(rl, f"d4_gate_lobby_sbp_{int(-x)}", "SBP", x, -1, GATE_W, GATE_H)
        D.gate(rl, f"d4_gate_lobby_pp_{int(-x)}", "PP", x, +1, GATE_W, GATE_H)
    D.open_ends = [("d4_concourse", "SPF", 0, True), ("d4_bow_obs", "SPF", -1, False)]      # rooms the Spine's open ends run into
