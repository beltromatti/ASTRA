"""ASN Aquila — the geometry of a deck's passages (NAVE-2, kept by NAVE-3): where the Spine and the two side passages can run on a deck (`free_pieces`: grid-aligned stretches inside the hull's
envelope and clear of the halls of the existing rooms) and how they meet the entrance of an existing room (`reach_rooms`). The programmes are not here any more: every deck is laid out from
its schedule by ship_design.py and ship_design_decks*.py (the old cyclic fill of this module is gone).
"""
from __future__ import annotations

import math

import ship_plan as P
from ship_catalog import MOD, SLOT_HW

SP_Y, SBP_Y, PP_Y = 0.0, 20.0, -20.0
GRID0 = -524.0                                 # every passage's module grid starts here (module edges at multiples of 4)


def obstacles(deck: int) -> list[list[float]]:
    """Boxes of the existing rooms that occupy this deck's plane (with a 0.4 m margin)."""
    z0, z1 = P.deck_z(deck)
    z0, z1 = z0 - P.STRUCT, z1 + P.STRUCT
    return [r["box"] for r in P.existing_rooms(0.4) if r["box"][5] > z0 + 0.05 and r["box"][4] < z1 - 0.05]


def hits(rect, obs) -> bool:
    return any(P.rect_overlap(rect, [b[0], b[1], b[2], b[3]]) for b in obs)


def free_pieces(deck: int, y_c: float, env: dict, obs: list, x_hi: float, x_lo: float, min_len: float = 24.0):
    """Grid-aligned intervals [a0, a1] of the passage at y_c that lie inside the envelope and clear of the obstacles."""
    pieces = []
    cur = None
    a = GRID0 + MOD * int((x_lo - GRID0) // MOD)
    while a + MOD <= x_hi + 1e-6:
        ok = True
        hw = min(P.half_width_at(env, a) or 0.0, P.half_width_at(env, a + MOD) or 0.0)
        if hw < abs(y_c) + SLOT_HW + 0.5:
            ok = False
        if ok and hits([a, y_c - SLOT_HW, a + MOD, y_c + SLOT_HW], obs):
            ok = False
        if ok:
            cur = [a, a + MOD] if cur is None else [cur[0], a + MOD]
        elif cur is not None:
            pieces.append(cur)
            cur = None
        a += MOD
    if cur is not None:
        pieces.append(cur)
    return [p for p in pieces if p[1] - p[0] >= min_len]


def reach_rooms(deck: int, y_c: float, pieces: list, reach: float = 8.0) -> list:
    """On a built deck a passage that stops in front of the entrance of an existing room that stands on this deck's plane (the Medbay on Deck 6) runs on to the
    room's wall, so that the corridor meets the door: the piece that ends within `reach` m of the entrance wall is extended to the grid line at or just beyond the
    wall's outer face (it runs up to 0.4 m into the wall)."""
    z0, _z1 = P.deck_z(deck)
    out = [list(p) for p in pieces]
    for r in P.existing_rooms(0.0):
        e = r.get("entrance")
        bx = r["box"]
        if not e or abs(e["z"] - z0) > 0.6 or not (bx[1] < y_c < bx[3]):
            continue
        for p in out:
            if e["wall"] == "fwd" and 0.0 <= p[0] - bx[2] <= reach:              # the piece lies forward of the room: its aft end meets the forward wall
                p[0] = GRID0 + MOD * math.ceil((bx[2] - 0.4 - GRID0) / MOD - 1e-9)       # (the first grid line that is not more than 0.4 m inside the wall: a wall that is off
            elif e["wall"] == "aft" and 0.0 <= bx[0] - p[1] <= reach:            #  the 4 m grid leaves a gap of less than 4 m that the plan fills with a lobby)
                p[1] = GRID0 + MOD * math.floor((bx[0] + 0.4 - GRID0) / MOD + 1e-9)
    return [tuple(p) for p in out]
