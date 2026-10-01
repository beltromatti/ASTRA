"""ASN Aquila — the vertical network of the plan (NAVE-3): the turbolift shafts and their landings (the `vertical[]` records of plan version 2, the contract with ASCENSORI: docs/brief/
NAVE-3.md), the stair columns, the Jefferies trunks, and the graph arcs that go with them (`lift` between the cars of a shaft, `stair` — with `ladder: true` — between the trunk cells).

The shafts are compartments of kind `lift` that span the decks they serve; each deck has the lobby in front (a compartment of its own, kind `lobby`) and a door record for every
landing, flagged `lift` (the lift's own doors are AstraLift*'s; build_ship_interior.py leaves them). Pure Python.
"""
from __future__ import annotations

import math

import ship_design as DS
import ship_plan as P
import ship_spec as SP
from ship_catalog import CRAWL_HW, MOD, SLOT_HW, TRUNK_CLIMB_GAP, TRUNK_NICHE, TRUNK_RUNG_PITCH, TRUNK_RUNG_T
from ship_layout import Builder, rnd

LIFT_SPEED, LIFT_ACCEL = 6.0, 2.0          # m/s and m/s²: the contract's numbers (ASCENSORI tunes them)
DOOR_TIME = 4.0                            # the wait for the doors, in the arc's cost
LAND = (1.5, 1.7)                          # the landing node: 1.5 m from the shaft's face; the deck's door record is on that face
# the bridge bank (the two command shafts under the bridge's lift housing; they run from Deck 1 to the keel): inner 2.6 m, outer 3.0 m (walls 0.2 m), at x -25.8 .. -22.8; the landing doors
# are on the lobby face of the front wall, x -22.8 (as every bank's: the plan's door point is where the lift engine's fascia mounts)
BRIDGE_SHAFTS = [dict(id="tl_b1", name="Bridge Turbolift 1", decks=list(range(1, 13)), x=-24.3, y=-6.7), dict(id="tl_b2", name="Bridge Turbolift 2", decks=list(range(1, 10)), x=-24.3, y=-3.7)]
BRIDGE_IN, BRIDGE_OUT = 2.6, 3.0
BRIDGE_LOBBY = [-22.8, -8.2, -14.8, -2.0]  # the lobby on the decks below (Deck 1's is the housing's vestibule, x -22.8 .. -21.0, y -8.2 .. -1.0)


def ride_seconds(dz: float) -> float:
    """A car's ride over dz metres: accelerate, cruise, brake (a triangular profile when the run is short), and the doors."""
    d = abs(dz)
    ramp = LIFT_SPEED ** 2 / LIFT_ACCEL
    t = d / LIFT_SPEED + LIFT_SPEED / LIFT_ACCEL if d >= ramp else 2.0 * math.sqrt(d / LIFT_ACCEL)
    return round(t + DOOR_TIME, 1)


def deck_z(deck: int) -> float:
    return P.deck_z(deck)[0]


# =================================================================================================================================================== lifts
def _shaft_record(sid: str, kind: str, name: str, x: float, y: float, w: float, d: float, decks: list, landings: list) -> dict:
    z0, z1 = deck_z(max(decks)), deck_z(min(decks))
    return {"id": sid, "kind": kind, "name": name, "shaft": {"x": rnd(x), "y": rnd(y), "w": w, "d": d, "z": [rnd(z0), rnd(z1)]}, "car": {"w": 2.4, "d": 2.4, "h": 2.6},
            "landings": landings, "speed": LIFT_SPEED, "accel": LIFT_ACCEL, "decks": decks}


def _shaft_comp(B: Builder, sid: str, name: str, x: float, y: float, out: float, decks: list) -> str:
    cid = f"shaft_{sid}"
    top = min(decks)
    z0, z1 = deck_z(max(decks)), deck_z(top) + P.DECKS[top]["clear"] + P.STRUCT
    if top >= 2:
        z1 = min(z1, deck_z(top - 1) - 0.05)                       # (a shaft ends at the floor of the deck above its top stop, not inside that deck's volume)
    B.comp(cid, min(decks), "lift", f"{name} shaft", [x - out / 2, y - out / 2, x + out / 2, y + out / 2], (z0, z1), section=P.section_of(min(decks) if min(decks) > 1 else 2, x),
           dept="neutral", status="built", systems=["lift"], stations=[], spans_decks=list(decks), shaft=sid)
    return cid


def _landing(B: Builder, sid: str, shaft_cid: str, lobby_cid: str, deck: int, door_pos: tuple, yaw_into: float, land_xy: tuple, z: float, hub: str | None) -> dict:
    """One stop of a shaft on one deck: the landing door (a record flagged for the lift engine), the node in the lobby in front of it, the node in the car."""
    did = f"d{deck}_{sid}_door"
    B.door(did, deck, (door_pos[0], door_pos[1], z), 0.0 if abs(math.cos(math.radians(yaw_into))) > 0.5 else 90.0, 1.6, 2.4, lobby_cid, shaft_cid, kind="sliding", lift=sid)
    land = f"lift.{sid}.{deck}.land"
    car = f"lift.{sid}.{deck}.car"
    B.node(land, deck, land_xy[0], land_xy[1], z, "lift", lobby_cid)
    B.node(car, deck, door_pos[0] + 1.4 * math.cos(math.radians(yaw_into)), door_pos[1] + 1.4 * math.sin(math.radians(yaw_into)), z, "lift_car", shaft_cid)
    B.link(land, car, "door", door=did, width=1.6)
    if hub:
        B.link(hub, land, "walk", width=2.0)
    return {"deck": deck, "z": rnd(z), "door": [rnd(door_pos[0]), rnd(door_pos[1]), rnd(z)], "yaw": rnd(yaw_into, 1), "lobby": lobby_cid, "node": land}


def _ride_arcs(B: Builder, sid: str, decks: list) -> None:
    """A `lift` arc between the cars of every two stops of a shaft (a rider goes from any stop to any other in one ride): cost = the ride in seconds."""
    for i, a in enumerate(decks):
        for b in decks[i + 1:]:
            na, nb = B.nodes[f"lift.{sid}.{a}.car"], B.nodes[f"lift.{sid}.{b}.car"]
            e = B.link(na["id"], nb["id"], "lift", cost=ride_seconds(deck_z(a) - deck_z(b)))
            e["shaft"] = sid


def lifts(B: Builder, decks: dict) -> list:
    out = []
    n_name = 0
    # ---- the turbolift banks of the lanes (ship_design.BANKS)
    for bk in DS.BANKS:
        served = [d for d in sorted(bk["decks"]) if d in decks and bk["id"] in DS.LOG["decks"].get(d, {}).get("banks", {})]
        if not served:
            continue
        for k, dy in enumerate(SP.LIFT_SHAFTS_Y):
            n_name += 1
            sid = f"tl_{bk['id']}{k + 1}"
            role = DS.BANK_ROLES.get(bk["id"], ("turbolift", "turbolift"))[k]
            lan = []
            geo = {}
            for d in served:
                info = DS.LOG["decks"][d]["banks"][bk["id"]]
                ps = decks[d].passages[info["pid"]]
                side, x1 = info["side"], info["x1"]
                yn = ps.pos + side * SLOT_HW
                ox = x1 - 8.0 if side > 0 else x1
                sx = ox + side * 1.6                                   # the shaft's middle along x (its local x 1.6)
                sy = yn + side * dy
                fx = ox + side * 3.2                                    # the shaft's face: the landing door's plane
                geo[d] = dict(sx=sx, sy=sy, fx=fx, side=side, ox=ox, lobby=DS.bank_id(d, bk["id"]))
            sx, sy = geo[served[0]]["sx"], geo[served[0]]["sy"]
            shaft_cid = _shaft_comp(B, sid, f"Turbolift {n_name}", sx, sy, 3.2, served)
            for d in served:
                g = geo[d]
                side = g["side"]
                yaw_into = 180.0 if side > 0 else 0.0                  # from the lobby into the shaft: towards the shaft's x
                land_x = g["ox"] + side * 4.7
                lan.append(_landing(B, sid, shaft_cid, g["lobby"], d, (g["fx"], g["sy"]), yaw_into, (land_x, g["sy"]), deck_z(d), f"{g['lobby']}.hub"))
            _ride_arcs(B, sid, served)
            out.append(_shaft_record(sid, role, f"Turbolift {n_name}" if role == "turbolift" else f"{'Service' if role == 'service' else 'Freight'} Lift {n_name}", sx, sy, 2.8, 2.8, served, lan))
    return out


def bridge_lifts(B: Builder, decks: dict) -> list:
    """The two command shafts. Deck 1: the housing's vestibule; the decks below: the special lobby `d<N>_lift_b` (ship_design.bridge_bank)."""
    out = []
    for sh in BRIDGE_SHAFTS:
        sid, x, y = sh["id"], sh["x"], sh["y"]
        cid = _shaft_comp(B, sid, sh["name"], x, y, BRIDGE_OUT, sh["decks"])
        lan = []
        for d in sh["decks"]:
            z = deck_z(d)
            if d == 1:
                lobby, hub = "lift_housing_bridge", "lift_housing_bridge.hub"
            else:
                lobby, hub = f"d{d}_lift_b", f"d{d}_lift_b.hub"
            lan.append(_landing(B, sid, cid, lobby, d, (x + BRIDGE_OUT / 2, y), 180.0, (x + BRIDGE_OUT / 2 + 1.5, y), z, hub))      # (the door point on the LOBBY face of the shaft's wall, like every bank's)
        _ride_arcs(B, sid, sh["decks"])
        out.append(_shaft_record(sid, "bridge", sh["name"], x, y, BRIDGE_IN, BRIDGE_IN, sh["decks"], lan))
    return out


# ================================================================================================================================================== stairs
def stairs(B: Builder, decks: dict) -> list:
    """One vertical record per stair column: the tower compartment of every deck that has it, joined by stairs to the decks above and below (the flights are the kit's: two
    switchback flights per deck, 4 m rise; Deck 2 to Deck 3 climbs 5.3 m through the armour deck)."""
    out = []
    for (tx, side) in DS.STAIRS:
        col = {"id": f"stair_{int(abs(tx))}{'n' if tx < 0 else 'p'}", "kind": "stair", "x_min": tx, "side": side, "nodes": {}, "towers": {}, "decks": []}
        prev = None
        for n in range(2, 13):
            cid = DS.tower_id(n, tx)
            if cid not in B.comps:
                prev = None
                continue
            c = B.comps[cid]
            b = c["bounds"]
            cx, cy = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
            z = c["z"][0]
            nid = f"{cid}.stair"
            B.node(nid, n, cx, cy, z, "stair", cid)
            B.link(f"{cid}.hub", nid, "walk", width=1.5)
            if prev is not None:
                pdeck, pnid, pz = prev
                B.link(pnid, nid, "stair", cost=14.0 if abs(pz - z) < 4.5 else 24.0)
            prev = (n, nid, z)
            col["nodes"][str(n)] = nid
            col["towers"][str(n)] = cid
            col["decks"].append(n)
            col["pos"] = [rnd(cx), rnd(cy)]
        if col["decks"]:
            out.append(col)
    return out


# =================================================================================================================================================== trunks
def trunks(B: Builder, decks: dict) -> list:
    """The Jefferies trunks: for every column and side, the trunk cell of every deck that has the arm, joined by ladders (a `stair` arc with `ladder: true`: it is slower than a
    stair, so its length is stretched 1.6 times) between consecutive decks."""
    out = []
    for k, xc in enumerate(DS.JCOLS):
        for side in (+1, -1):
            sid = f"jt_{k + 1}{'s' if side > 0 else 'p'}"
            nodes, comps = {}, {}
            for d, D in sorted(decks.items()):
                for ar in D.arms:
                    if ar["side"] == side and abs(ar["x"] - xc) < 1e-6 and ar["opt"].get("trunk"):
                        aid = next(p.pid for p in D.passages.values() if p.arm_of and p.arm_of["parent"] == ar["pid"] and abs(p.pos - xc) < 1e-6)
                        ap = D.passages[aid]
                        nid = f"d{d}.{aid}.{ap.arm_of['trunk_idx']:03d}"
                        if nid in B.nodes:
                            nodes[d] = nid
                            comps[d] = B.nodes[nid]["comp"]
            if not nodes:
                continue
            ds = sorted(nodes)
            for a, b in zip(ds, ds[1:]):
                e = B.link(nodes[a], nodes[b], "stair", cost=20.0)
                e["ladder"] = True
                e["len"] = rnd(e["len"] * 1.6, 2)
            n0 = B.nodes[nodes[ds[0]]]
            out.append({"id": sid, "kind": "trunk", "name": f"Jefferies Tube J-{k + 1}{'S' if side > 0 else 'P'}", "x": n0["p"][0], "y": n0["p"][1], "shaft": {"x": n0["p"][0], "y": n0["p"][1], "w": 1.2, "d": 1.2,
                        "z": [rnd(deck_z(ds[-1])), rnd(deck_z(ds[0]) + 3.4)]}, "decks": ds, "nodes": {str(d): nodes[d] for d in ds}, "trunks": {str(d): comps[d] for d in ds},
                        **_climb(B, ds, nodes)})
    return out


def _climb(B: Builder, ds: list, nodes: dict) -> dict:
    """What a climber needs (the lead's engine makes the ladders climbable): per deck the place of the body in front of the rungs (`ladder`), the way it faces (`facing`: the yaw towards the
    rungs), the walkway point to step off to (`step`), the niche's opening in the floor (`hole`: x0, y0, x1, y1, where a walker would fall down the column) and which end of the column is
    closed on that deck. A trunk cell is the arm's first module, placed at yaw 90: its ladder niche is in the cell's aft wall (world -x), 1.1 m deep from the walkway's wall face (the
    walkway is CRAWL_HW either side of the arm's axis), the rungs' axis 1.01 m in; the cell's middle is the niche's middle along the arm."""
    top, bottom = ds[0], ds[-1]
    lan = []
    for d in ds:
        x, y, _z = B.nodes[nodes[d]]["p"]
        t = TRUNK_RUNG_T - TRUNK_CLIMB_GAP
        a, c = TRUNK_NICHE
        lan.append({"deck": d, "z": rnd(deck_z(d)), "node": nodes[d], "ladder": {"x": rnd(x - CRAWL_HW - t), "y": rnd(y)}, "facing": 180.0, "step": [rnd(x), rnd(y)],
                    "hole": [rnd(x - CRAWL_HW - 1.1), rnd(y - 2.0 + a), rnd(x - CRAWL_HW), rnd(y - 2.0 + c)],
                    "closed": "hatch" if d == top else "toe_plate" if d == bottom else None})
    return {"landings": lan, "ends": {"top": {"deck": top, "closed": "hatch"}, "bottom": {"deck": bottom, "closed": "toe_plate"}},
            "rungs": {"pitch": TRUNK_RUNG_PITCH, "rail_gap": 0.44, "z0": -0.13, "note": "the first rung is 13 cm under a deck's floor and they go on every `pitch` m; the column is open (the floor has the hole `hole`) except at its two ends"}}
