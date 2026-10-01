"""ASN Aquila — the Spine Shuttle's line (NAVE-3; docs/BIBBIA.md §6: "the central corridor along the ship with the internal shuttle", docs/NAVE.md §6).

The line runs along Deck 5 (Science & Transport) for the whole length of the ship, from the bow terminal to the stern terminal, in a tunnel (tone T: 3.5 m wide, 3.25 m high: the car
is 14 m x 2.8 m) along the middle of the starboard outer lane (y = 30), and stops in eight halls, one for every section: the halls are rooms of that lane (prefab `shuttle_stop`,
24 x 16 m: the platform along the Starboard Passage's wall, the track bed behind it, the tunnel's mouths in the end walls), and the tunnel is the stretch between two halls.

Why the starboard outer lane. The Spine of Deck 5 is cut by the halls of the existing rooms (the Mess, the Berths, the Medbay, Main Engineering: pieces of 24 to 304 m), and the lifts
want it; the Starboard Passage is continuous from the bow to the stern, and the lane beyond it is free of the halls (their y is at most 15 m): the one straight line through the whole ship.
Its price: the Mess lift bank on this side (m1) starts at Deck 6, and the Jefferies arms on this side of Deck 5 are only their trunk cell (y 22-26, clear of the tunnel at 28-32).

The plan (`plan()`): a platform node in every hall, `shuttle` edges between consecutive halls (cost: the ride in seconds, the dwell included; width 0.05 m: nothing but a passenger
goes down a tunnel, and the damage model reads an edge of unknown kind as an opening of that width), and the `transit[]` record of the v2 contract (docs/brief/NAVE-3.md).
"""
from __future__ import annotations

import math

import ship_design as DS
import ship_plan as P
from ship_layout import Builder, DesignError, rnd

DECK = DS.SHUTTLE_DECK
LINE_Y = DS.SHUTTLE_Y
HALL_L = 24.0
# the halls, by their forward edge (x): A is the bow terminal, H the stern terminal. Each lies between two Jefferies columns (ship_design.JCOLS) and clear of the bulkhead slots.
STOPS = [("A", 88.0), ("B", -12.0), ("C", -100.0), ("D", -228.0), ("E", -296.0), ("F", -352.0), ("G", -420.0), ("H", -500.0)]
CRUISE, ACCEL, DWELL = 20.0, 2.5, 10.0         # m/s, m/s², s at an intermediate stop (the contract's numbers: ASCENSORI tunes them)
CAR_L = 14.0
TOP_Y, DOOR_Y = LINE_Y, LINE_Y - 1.4           # the car's axis; its doors, on the platform side (-y), are on the car's wall
PLATFORM_Y = 22.0 + 5.2                         # where a passenger waits: the platform's middle (the hall's local y 5.2)


def hall_id(letter: str) -> str:
    return f"d{DECK}_shuttle_{letter}"


def hall_key(letter: str) -> str:
    return "shuttle_stop_bow" if letter == STOPS[0][0] else "shuttle_stop_stern" if letter == STOPS[-1][0] else "shuttle_stop"


def setup(D) -> None:
    """Deck 5: the eight halls (anchored in the starboard outer lane) and the tunnel between them."""
    sb = DS.piece_at(D, "SB", STOPS[-1][1] - 1.0, STOPS[0][1] + 1.0)
    if sb is None:
        raise DesignError("deck 5: the Starboard Passage does not run the whole length of the line")
    for letter, xf in STOPS:
        D.anchor(sb.pid, +1, xf, (hall_key(letter), {"id": hall_id(letter), "name": f"Spine Shuttle · Stop {letter}", "stop": letter}))
    for k in range(len(STOPS) - 1):
        a_fwd = STOPS[k][1] - HALL_L                       # the aft edge of this hall
        b_aft = STOPS[k + 1][1]                            # the forward edge of the next
        if a_fwd - b_aft < 4.0 - 1e-6:
            continue
        pid = f"TU{k}"
        D.passage(pid, "T", "x", LINE_Y, b_aft, a_fwd, "Spine Shuttle Tunnel")
        D.section_bulkheads([pid])
    DS.LOG["shuttle"] = {"halls": [(l, x) for l, x in STOPS]}


def ride_seconds(d: float) -> float:
    """A ride of d metres: accelerate, cruise, brake (a triangular profile when the run is short), plus the dwell at the stop it ends at."""
    ramp = CRUISE ** 2 / ACCEL
    t = d / CRUISE + CRUISE / ACCEL if d >= ramp else 2.0 * math.sqrt(d / ACCEL)
    return round(t + DWELL, 1)


def plan(B: Builder, decks: dict) -> dict:
    """The line's nodes and edges in the graph, and the `transit[]` record. A platform node per hall (joined to the hall's hub); a `shuttle` edge between consecutive halls."""
    D = decks.get(DECK)
    if D is None:
        return {}
    z = P.deck_z(DECK)[0]
    stops, nodes = [], []
    for letter, xf in STOPS:
        cid = hall_id(letter)
        if cid not in B.comps:
            continue
        xc = xf - HALL_L / 2
        nid = f"{cid}.platform"
        B.node(nid, DECK, xc, PLATFORM_Y, z, "platform", cid)
        B.link(f"{cid}.hub", nid, "walk", width=3.0)
        nodes.append((letter, xc, nid))
        stops.append({"id": letter, "section": P.section_of(DECK, xc), "x": rnd(xc), "door": [rnd(xc), rnd(DOOR_Y), rnd(z)], "yaw": 90.0, "room": cid, "node": nid})
    for (la, xa, na), (lb, xb, nb) in zip(nodes, nodes[1:]):
        e = B.link(na, nb, "shuttle", width=0.05, cost=ride_seconds(abs(xa - xb)))
        e["line"] = "spine_shuttle"
    path = [[rnd(x), rnd(TOP_Y), rnd(z)] for (_, x, _) in nodes]
    return {"id": "spine_shuttle", "kind": "shuttle", "name": "Spine Shuttle", "deck": DECK, "path": path, "stops": stops, "car": {"mesh": "SpineCar", "length": CAR_L},
            "speed": CRUISE, "accel": ACCEL, "dwell": DWELL, "gauge": 1.3, "status": "built"}
