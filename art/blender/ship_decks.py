"""ASN Aquila — the coarse plans of the decks that are not modelled yet (Decks 2, 3, 5-12): the same topology as Deck 4 (the Spine at y = 0, the
Starboard and Port Passages at y = +-20, cross links, lanes of rooms on the 4 m grid) but planned only: typed compartments with real
bounds, doors and graph nodes, no meshes. The programme of every deck is the canon of docs/BIBBIA.md §6.

`plan_deck(B, deck)` fills the deck with rooms from its programme, skipping what would cross an existing room, leave the hull's envelope or
straddle a section boundary; the passages stop in front of the existing rooms (the Medbay, Main Engineering, the Flight Deck) whose doors
they reach. Deck 1 is the bridge complex and is registered by ship_plan_gen.existing().
"""
from __future__ import annotations

import math
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
    3: {"default": ["staterooms", "staterooms", "offices", "gym", "staterooms", "records"], "A": ["wardroom", "gym", "staterooms", "offices"],
        "B": ["staterooms", "staterooms", "offices", "staterooms", "wardroom"], "C": ["staterooms", "gym", "staterooms", "records", "offices"],
        "D": ["staterooms", "staterooms", "offices", "gym"], "E": ["staterooms", "offices", "staterooms", "staterooms"], "F": ["staterooms", "staterooms", "gym", "offices"],
        "G": ["staterooms", "offices", "staterooms"], "H": ["machinery", "staterooms"]},
    5: {"default": ["lab", "sensor_archive", "lab_bio", "sensor_room"], "A": ["lab_bio", "lab", "sensor_room", "hydro", "lab_phys"],
        "B": ["lab", "sensor_archive", "lab_astro", "lab_bio"], "C": ["lab_phys", "lab", "lab_bio", "sensor_room", "lab"],
        "D": ["lab_astro", "hydro", "lab", "sensor_archive"], "E": ["radiator_pumps", "machinery", "dc_locker", "machinery_b"],
        "F": ["radiator_pumps", "machinery_b", "sensor_room", "dc_locker"], "G": ["machinery", "radiator_pumps", "dc_locker"],
        "H": ["machinery_b", "dc_locker", "machinery"]},
    6: {"default": ["store_cold", "laundry", "heads", "store_dry", "cabins", "quiet", "library", "hydro", "lab"],
        "A": ["store_dry", "store_cold", "laundry", "heads", "hold"], "B": ["cabins", "store_dry", "lab", "heads", "laundry", "store_cold", "quiet", "library"],
        "C": ["store_cold", "cabins", "lab", "dc_locker", "store_dry", "heads"], "D": ["cabins", "store_dry", "laundry", "heads", "hydro"],
        "E": ["hydro", "store_cold", "heads", "lab"], "F": ["cabins", "library", "quiet", "laundry"], "G": ["store_dry", "laundry", "heads", "quiet"],
        "H": ["machinery", "dc_locker"]},
    7: {"default": ["machinery", "dc_locker", "machinery_b", "power_control"], "A": ["machinery", "dc_locker"],
        "B": ["power_control", "switchgear", "machinery", "dc_locker", "capacitors", "machinery_b"], "C": ["switchgear", "capacitors", "power_control", "machinery", "radiator_pumps"],
        "D": ["power_control", "machinery_b", "dc_locker", "capacitors"], "E": ["radiator_pumps", "machinery", "switchgear", "dc_locker"],
        "F": ["power_control", "capacitors", "machinery_b", "dc_locker", "machinery"], "G": ["radiator_pumps", "machinery", "power_control", "switchgear"],
        "H": ["machinery", "dc_locker", "machinery_b"]},
    8: {"default": ["store_dry", "hold", "machinery", "dc_locker", "workshop"], "B": ["barracks", "kit_room", "barracks", "lounge", "heads", "armory"],
        "C": ["armory", "barracks", "laundry", "barracks", "kit_room", "heads", "store_dry"], "D": ["barracks", "hold", "barracks", "store_dry", "laundry", "dc_locker"],
        "F": ["workshop", "machinery", "dc_locker", "hold"], "G": ["hold", "store_dry", "machinery"], "H": ["machinery", "dc_locker"]},
    9: {"default": ["cargo_hold", "machinery", "cargo_hold", "dc_locker", "store_dry"], "A": [], "B": [],
        "C": ["flight_ops", "pilot_ready", "aircraft_shop", "magazine", "flight_ops", "pilot_ready"], "D": ["aircraft_shop", "magazine", "pilot_ready", "cargo_hold", "flight_ops", "dc_locker"],
        "E": ["magazine", "cargo_hold", "aircraft_shop", "store_dry", "machinery"], "F": ["cargo_hold", "hold", "magazine", "dc_locker"],
        "G": ["cargo_hold", "store_dry", "machinery", "hold"], "H": ["machinery", "dc_locker"]},
    10: {"default": ["cargo_hold", "magazine", "hold", "store_dry", "cargo_hold", "store_cold", "dc_locker"], "A": ["cargo_hold", "hold", "magazine"],
         "B": ["magazine", "magazine", "cargo_hold", "hold", "store_dry"], "C": ["cargo_hold", "hold", "store_cold", "store_dry", "magazine", "dc_locker"],
         "D": ["magazine", "cargo_hold", "hold", "store_cold", "dc_locker"], "E": ["cargo_hold", "store_dry", "hold", "magazine", "machinery"],
         "F": ["hold", "cargo_hold", "store_cold", "dc_locker"], "G": ["cargo_hold", "hold", "store_dry", "machinery"], "H": ["machinery", "hold", "dc_locker"]},
    11: {"default": ["workshop", "fab_shop", "repair_bay", "dc_locker", "machinery", "hold"], "A": ["repair_bay", "dc_locker", "workshop"],
         "B": ["fab_shop", "workshop", "dc_locker", "fab_shop", "repair_bay"], "C": ["repair_bay", "dc_locker", "workshop", "fab_shop", "machinery_b"],
         "D": ["workshop", "repair_bay", "fab_shop", "hold"], "E": ["fab_shop", "machinery", "dc_locker", "workshop"], "F": ["repair_bay", "workshop", "dc_locker", "machinery"],
         "G": ["hold", "store_dry", "machinery", "dc_locker"], "H": ["machinery", "dc_locker"]},
    12: {"default": ["tank", "reaction_mass", "crawlway", "tank", "dc_locker"], "A": ["tank", "crawlway", "tank"], "B": ["reaction_mass", "tank", "crawlway", "tank"],
         "C": ["tank", "tank", "crawlway", "reaction_mass"], "D": ["reaction_mass", "crawlway", "tank", "dc_locker"], "E": ["tank", "crawlway", "tank", "tank"],
         "F": ["tank", "reaction_mass", "crawlway", "tank"], "G": ["tank", "crawlway", "dc_locker", "tank"], "H": ["crawlway", "tank", "dc_locker"]},
}


UNIQUE = {2: {"cic"}, 5: {"transporter", "lab_astro"}, 6: {"surgery", "quarantine", "pharmacy"}, 8: {"shuttle_bay", "firing_range"}}      # rooms that stand once on their deck
# rooms placed first, at a fixed place: (key, side of the Spine, x of the room's forward edge). Deck 6: the medical rooms next to the Medbay's entrance,
# on the starboard side of the Spine (the Medbay's own door is at x -232)
# Deck 5 also has the Spine shuttle's stops, one per section on the Spine's pieces between the halls of the decks above and below (A 88..112, B -24..0, C -108..-84, D -228..-204,
# E -304..-280, G -440..-416, H -504..-480). Section F has none: the 20 m of its Spine that the Main Engineering hall's keep-out leaves are shorter than a stop, and a room may not
# straddle a section's bulkhead. A stop never takes the whole starboard lane of a piece of Spine (the cross link to the Starboard Passage lives there).
# Deck 2: the CIC, in the first section where the block is wide enough for a 16 m room (the block is only 16.4 m to a side forward of x -60: Section A has the Spine and nothing else), on the
# starboard side behind the section's first cross link
PINNED = {2: [("cic", +1, -68.0)],
          5: [("transporter", +1, 4.0), ("shuttle_stop", +1, 112.0), ("shuttle_stop", -1, 0.0), ("shuttle_stop", +1, -84.0), ("shuttle_stop", -1, -204.0),
              ("shuttle_stop", -1, -280.0), ("shuttle_stop", +1, -416.0), ("shuttle_stop", -1, -480.0)],
          8: [("shuttle_bay", -1, 52.0), ("firing_range", -1, 16.0)],      # (the bay on the port side: the bow stair tower (x 44..52) stands on the starboard side of that stretch)
          6: [("pharmacy", +1, -216.0), ("surgery", +1, -200.0), ("quarantine", +1, -176.0)]}


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


def rooms_for(deck: int, sec: str, side: int, k0: int) -> list[str]:
    prog = PROGRAMME[deck]
    cyc = prog.get(sec, prog["default"])
    if not cyc:
        return []
    n = len(cyc)
    return [cyc[(k0 + i + (0 if side > 0 else 1)) % n] for i in range(n)]


def fill_lane(deck: int, ps: Passage, side: int, env: dict, obs: list, partner: Passage | None, placed: list, force: bool = False,
              used: set | None = None) -> list:
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
        unique = UNIQUE.get(deck, set())
        key = None
        for j in range(len(cyc)):                                               # the next room of the cycle that may still stand on this deck
            cand = cyc[(k + j) % len(cyc)]
            if cand in unique and used is not None and cand in used:
                continue
            key = cand
            k += j + 1
            break
        if key is None:
            k += 1
            gap = min(x - lo, 8.0)
            items.append(("gap", gap))
            x -= gap
            continue
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
        if used is not None and key in unique:
            used.add(key)
        x -= L
    if x - ps.a0 > 1e-6:
        items.append(("gap", x - ps.a0))
    return items


def plan_deck(B: Builder, deck: int, towers: list | None = None, coarse: bool = True) -> Deck:
    """`towers`: [(x_min, side)] stair-tower columns of the built deck, reserved on this deck too (each is an 8 x 8 m room off the Spine).
    `coarse=False`: the deck is built for real (corridor modules, the rooms of the programme that have meshes, plates, signs); a room of the programme
    without a mesh yet stays a planned compartment behind a plain wall (its door is in the plan, locked, and no opening is cut in the corridor)."""
    D = Deck(B, deck, f"d{deck}", coarse=coarse)
    env = D.env
    obs = obstacles(deck)
    xh = (int(env["x_fwd"] // MOD)) * MOD
    xl = -524.0 if deck >= 3 else (int((env["x_aft"] + MOD) // MOD)) * MOD
    if deck == 2:
        xl = -496.0
    spine = free_pieces(deck, SP_Y, env, obs, xh, xl)
    if not coarse:
        spine = reach_rooms(deck, SP_Y, spine)
    keel = deck == 12 and not coarse                                            # the keel's passages are maintenance crawlways (tone K)
    sp = [D.passage(f"SP{i}", "K" if keel else "S", "x", SP_Y, a0, a1, "Keel Crawlway" if keel else "Spine") for i, (a0, a1) in enumerate(spine)]
    sbp = [D.passage(f"SB{i}", "K" if keel else "P", "x", SBP_Y, a0, a1, "Starboard Crawlway" if keel else "Starboard Passage")
           for i, (a0, a1) in enumerate(free_pieces(deck, SBP_Y, env, obs, xh, xl))]
    pp = [D.passage(f"PO{i}", "K" if keel else "P", "x", PP_Y, a0, a1, "Port Crawlway" if keel else "Port Passage") for i, (a0, a1) in enumerate(free_pieces(deck, PP_Y, env, obs, xh, xl))]
    placed: list = []
    used: set = set()
    for (tx, tside) in (towers or []):
        for ps in sp:
            if ps.a0 <= tx and tx + 8.0 <= ps.a1:
                rect = [tx, 2.0, tx + 8.0, 10.0] if tside > 0 else [tx, -10.0, tx + 8.0, -2.0]
                hw = P.half_width_at(env, tx) or 0.0
                if not hits(rect, obs) and hw > 12.0:
                    D.lane(ps.pid, tside, tx + 8.0, [("stair_tower", {"id": f"d{deck}_stair_{int(abs(tx))}{'n' if tx < 0 else 'p'}"})], "stairs")
                    placed.append(rect)
    for (key, side, xs) in PINNED.get(deck, []) if not coarse else []:
        spec = SP.PREFABS[key]
        ps = next((q for q in sp if q.a0 <= xs - spec["L"] and xs <= q.a1), None)
        if ps is None:
            B.notes.append(f"deck {deck}: {key} cannot stand at x {xs} (no Spine there)")
            continue
        ya, yb = ps.pos + side * SLOT_HW, ps.pos + side * (SLOT_HW + spec["D"])
        rect = [xs - spec["L"], min(ya, yb), xs, max(ya, yb)]
        if hits(rect, obs) or any(P.rect_overlap(rect, r, 0.05) for r in placed):
            B.notes.append(f"deck {deck}: {key} cannot stand at x {xs} (something is in the way)")
            continue
        D.lane(ps.pid, side, xs, [(key,)], "pinned")
        placed.append(rect)
        used.add(key)
    for ps in sp:
        for side, partners in ((+1, sbp), (-1, pp)):
            partner = next((p for p in partners if p.a0 <= ps.a0 + 2 and p.a1 >= ps.a1 - 2), None) or (partners[0] if partners else None)
            partner = partner if partner and partner.a0 <= ps.a1 and partner.a1 >= ps.a0 else None
            snap, snap_used = list(placed), set(used)
            items = fill_lane(deck, ps, side, env, obs, partner, placed, used=used)
            if partner is not None and not any(it[0] == "link" for it in items) and side > 0:
                placed[:] = snap
                used.clear()                                                    # the rooms of the discarded try are free again (a unique room must not be lost with it)
                used.update(snap_used)
                items = fill_lane(deck, ps, side, env, obs, partner, placed, force=True, used=used)
            D.lane(ps.pid, side, ps.a1, items, "I_s" if side > 0 else "I_p")
    # outer lanes off the side passages, only where the hull is wide enough for 16 m rooms
    for group, side in ((sbp, +1), (pp, -1)):
        for ps in group:
            items = fill_lane(deck, ps, side, env, obs, None, placed, used=used)
            D.lane(ps.pid, side, ps.a1, items, "O_s" if side > 0 else "O_p")
    if not coarse:
        dropped = D.resolve_conflicts()
        if dropped:
            B.notes.append(f"deck {deck}: {len(dropped)} rooms of the programme left out where their door would meet a cross link: {sorted(set(dropped))}")
    return D
