"""ASN Aquila — the coarse plans of the decks that are not modelled yet (Decks 2, 3, 5-12): the same topology as Deck 4 (the Spine at y = 0, the
Starboard and Port Passages at y = +-20, cross links, lanes of rooms on the 4 m grid) but planned only: typed compartments with real
bounds, doors and graph nodes, no meshes. The programme of every deck is the canon of docs/BIBBIA.md §6.

`plan_deck(B, deck)` fills the deck with rooms from its programme, skipping what would cross an existing room, leave the hull's envelope or
straddle a section boundary; the passages stop in front of the existing rooms (the Medbay, Main Engineering, the Flight Deck) whose doors
they reach. Deck 1 is the bridge complex and is registered by ship_plan_gen.existing().
"""
from __future__ import annotations

import random

import ship_plan as P
import ship_spec as SP
from ship_layout import Builder, Deck, Passage
from ship_catalog import MOD, SLOT_HW

SP_Y, SBP_Y, PP_Y = 0.0, 20.0, -20.0
GRID0 = -524.0                                 # every passage's module grid starts here (module edges at multiples of 4)

PROGRAMME = {
    2: {"default": ["offices", "records", "comms_center", "offices", "point_defense"],
        "A": ["cic", "briefing", "comms_center", "offices"], "B": ["offices", "records", "point_defense", "briefing", "offices"],
        "C": ["vls_magazine", "sensor_room", "offices", "comms_center"], "D": ["vls_magazine", "point_defense", "sensor_room", "offices"],
        "E": ["barbette", "point_defense", "offices"], "F": ["barbette", "offices", "sensor_room"], "G": ["sensor_room", "offices", "machinery"]},
    3: {"default": ["staterooms", "staterooms", "offices", "gym"], "A": ["wardroom", "gym", "staterooms"], "B": ["staterooms", "staterooms", "offices"],
        "C": ["staterooms", "gym", "staterooms"], "H": ["machinery", "staterooms"]},
    5: {"default": ["lab", "sensor_archive", "lab", "sensor_room"], "A": ["lab", "sensor_archive", "sensor_room"],
        "B": ["transporter", "lab", "lab", "sensor_archive"], "C": ["lab", "transporter", "sensor_room", "lab"], "D": ["lab", "hydro", "lab", "sensor_archive"],
        "E": ["radiator_pumps", "machinery", "lab"], "F": ["radiator_pumps", "machinery", "sensor_room"], "G": ["radiator_pumps", "machinery"],
        "H": ["machinery", "dc_locker"]},
    6: {"default": ["quarantine", "pharmacy", "dc_locker", "surgery"], "A": ["surgery", "pharmacy", "dc_locker"],
        "B": ["quarantine", "pharmacy", "surgery", "dc_locker"], "C": ["surgery", "dc_locker", "quarantine"], "D": ["quarantine", "pharmacy", "surgery"],
        "H": ["machinery", "dc_locker"]},
    7: {"default": ["power_control", "machinery", "dc_locker", "machinery"], "A": ["power_control", "machinery"], "B": ["power_control", "machinery", "dc_locker"],
        "E": ["radiator_pumps", "machinery"], "F": ["power_control", "machinery", "dc_locker"], "G": ["radiator_pumps", "machinery", "power_control"],
        "H": ["machinery", "dc_locker", "machinery"]},
    8: {"default": ["barracks", "barracks", "dc_locker", "machinery"], "A": ["shuttle_bay", "barracks"], "B": ["barracks", "firing_range", "armory"],
        "C": ["armory", "barracks", "firing_range"], "D": ["barracks", "armory", "barracks"], "H": ["machinery", "dc_locker"]},
    9: {"default": ["cargo_hold", "machinery", "cargo_hold"], "A": [], "B": [], "C": ["flight_ops", "aircraft_shop", "magazine"],
        "D": ["aircraft_shop", "flight_ops", "magazine"], "E": ["magazine", "cargo_hold", "flight_ops"], "H": ["machinery", "dc_locker"]},
    10: {"default": ["cargo_hold", "magazine", "hold", "cargo_hold"], "A": ["cargo_hold", "hold", "magazine"], "H": ["machinery", "hold"]},
    11: {"default": ["workshop", "fab_shop", "repair_bay", "dc_locker"], "A": ["repair_bay", "dc_locker", "workshop"], "H": ["machinery", "dc_locker"]},
    12: {"default": ["tank", "reaction_mass", "crawlway", "tank"], "A": ["tank", "crawlway"], "H": ["crawlway", "tank"]},
}


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


def rooms_for(deck: int, sec: str, side: int, k0: int) -> list[str]:
    prog = PROGRAMME[deck]
    cyc = prog.get(sec, prog["default"])
    if not cyc:
        return []
    n = len(cyc)
    return [cyc[(k0 + i + (0 if side > 0 else 1)) % n] for i in range(n)]


def fill_lane(deck: int, ps: Passage, side: int, env: dict, obs: list, partner: Passage | None, placed: list, force: bool = False) -> list:
    """The item list of a lane along passage piece `ps` on `side`: rooms of the programme packed from the forward end aft. `force`: a cross link
    in the first free slot (a piece must never be cut off from the side passages)."""
    secs = P.sections(deck)
    yn = ps.pos + side * SLOT_HW
    x = ps.a1
    items: list = []
    k = 0
    if force and partner is not None:
        xc = x - 6.0
        ya, yb = ps.pos + side * SLOT_HW, partner.pos - side * SLOT_HW
        rect = [xc - 2.0, min(ya, yb), xc + 2.0, max(ya, yb)]
        if partner.a0 <= xc - 2.0 and partner.a1 >= xc + 2.0 and ps.a0 <= xc - 2.0 and not hits(rect, obs) and not any(P.rect_overlap(rect, r) for r in placed):
            items += [("gap", 4.0), ("link", partner.pid)]
            placed.append(rect)
            x -= 8.0
    rng = random.Random(deck * 100 + (1 if side > 0 else 2) + int(ps.a0))
    guard = 0
    while x - 8.0 >= ps.a0 and guard < 400:
        guard += 1
        sec_letter = P.section_of(deck, x - 0.1)
        sx0, sx1 = next(((a, b) for (l, a, b) in secs if l == sec_letter), (ps.a0, ps.a1))
        lo = max(sx0, ps.a0)
        if abs(x - sx1) < 1e-6:                                                  # the section starts here: the bulkhead's slot, then a cross link
            items.append(("gap", 4.0))
            x -= 4.0
            if partner is not None and x - 4.0 >= lo:
                xc = x - 2.0
                ya, yb = ps.pos + side * SLOT_HW, partner.pos - side * SLOT_HW
                rect = [xc - 2.0, min(ya, yb), xc + 2.0, max(ya, yb)]
                pa = partner.a0 <= xc - 2.0 and partner.a1 >= xc + 2.0
                if pa and not hits(rect, obs) and not any(P.rect_overlap(rect, r) for r in placed):
                    items.append(("link", partner.pid))
                    placed.append(rect)
                    x -= 4.0
                    continue
            continue
        cyc = rooms_for(deck, sec_letter, side, k)
        if not cyc:
            gap = x - lo
            items.append(("gap", gap))
            x -= gap
            continue
        key = cyc[k % len(cyc)]
        k += 1
        spec = SP.PREFABS[key]
        L, D = spec["L"], spec["D"]
        if x - L < lo - 1e-6:
            gap = x - lo
            items.append(("gap", gap))
            x -= gap
            continue
        ya, yb = yn, yn + side * D
        rect = [x - L, min(ya, yb), x, max(ya, yb)]
        hw = min(P.half_width_at(env, x - L) or 0.0, P.half_width_at(env, x) or 0.0)
        if abs(yb) > hw or hits(rect, obs) or any(P.rect_overlap(rect, r, 0.05) for r in placed):
            items.append(("gap", L))
            x -= L
            continue
        items.append((key,))
        placed.append(rect)
        x -= L
    if x - ps.a0 > 1e-6:
        items.append(("gap", x - ps.a0))
    return items


def plan_deck(B: Builder, deck: int, towers: list | None = None) -> Deck:
    """`towers`: [(x_min, side)] stair-tower columns of the built deck, reserved on this deck too (each is an 8 x 8 m room off the Spine)."""
    D = Deck(B, deck, f"d{deck}", coarse=True)
    env = D.env
    obs = obstacles(deck)
    xh = (int(env["x_fwd"] // MOD)) * MOD
    xl = -524.0 if deck >= 3 else (int((env["x_aft"] + MOD) // MOD)) * MOD
    if deck == 2:
        xl = -496.0
    sp = [D.passage(f"SP{i}", "S", "x", SP_Y, a0, a1, "Spine") for i, (a0, a1) in enumerate(free_pieces(deck, SP_Y, env, obs, xh, xl))]
    sbp = [D.passage(f"SB{i}", "P", "x", SBP_Y, a0, a1, "Starboard Passage") for i, (a0, a1) in enumerate(free_pieces(deck, SBP_Y, env, obs, xh, xl))]
    pp = [D.passage(f"PO{i}", "P", "x", PP_Y, a0, a1, "Port Passage") for i, (a0, a1) in enumerate(free_pieces(deck, PP_Y, env, obs, xh, xl))]
    placed: list = []
    for (tx, tside) in (towers or []):
        for ps in sp:
            if ps.a0 <= tx and tx + 8.0 <= ps.a1:
                rect = [tx, 2.0, tx + 8.0, 10.0] if tside > 0 else [tx, -10.0, tx + 8.0, -2.0]
                hw = P.half_width_at(env, tx) or 0.0
                if not hits(rect, obs) and hw > 12.0:
                    D.lane(ps.pid, tside, tx + 8.0, [("stair_tower", {"id": f"d{deck}_stair_{int(abs(tx))}{'n' if tx < 0 else 'p'}"})], "stairs")
                    placed.append(rect)
    for ps in sp:
        for side, partners in ((+1, sbp), (-1, pp)):
            partner = next((p for p in partners if p.a0 <= ps.a0 + 2 and p.a1 >= ps.a1 - 2), None) or (partners[0] if partners else None)
            partner = partner if partner and partner.a0 <= ps.a1 and partner.a1 >= ps.a0 else None
            snap = list(placed)
            items = fill_lane(deck, ps, side, env, obs, partner, placed)
            if partner is not None and not any(it[0] == "link" for it in items) and side > 0:
                placed[:] = snap
                items = fill_lane(deck, ps, side, env, obs, partner, placed, force=True)
            D.lane(ps.pid, side, ps.a1, items, "I_s" if side > 0 else "I_p")
    # outer lanes off the side passages, only where the hull is wide enough for 16 m rooms
    for group, side in ((sbp, +1), (pp, -1)):
        for ps in group:
            items = fill_lane(deck, ps, side, env, obs, None, placed)
            D.lane(ps.pid, side, ps.a1, items, "O_s" if side > 0 else "O_p")
    return D
