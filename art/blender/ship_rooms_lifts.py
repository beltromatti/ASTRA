"""ASN Aquila interior kit (NAVE-3): the turbolift lobbies — the bank of two shafts between a main corridor and the passage beyond (lift_bank: gates on both sides; lift_bank_o: in an outer
lane, one gate), and the command lobby under the bridge (lift_bank_b). A lobby is a 4.8 m wide hall along the lane's depth with the lifts' doors on one long wall and the shafts
behind it (their walls, 0.2 m thick, run through every deck: the floor and the ceiling of the lobby have no slab where a shaft is, so the shaft is one free volume from the top deck to the
bottom one, as the plan's `lift` compartments say; the cars, the doors' leaves and the machinery are the lift engine's: AstraLift*). Frames and sizes: ship_rooms.py / ship_spec.py."""
from __future__ import annotations

import ship_furniture as F
import ship_spec as SPEC
from bridge3_lib import T
from ship_catalog import GATE_H, GATE_W, LIFT_DOOR_H, LIFT_DOOR_W, LIFT_IN, LIFT_OUT
from ship_lib import COMPOSITE, DECK, DGLASS, FABRIC_GREY, FABRIC_NAVY, LAMP, LAMP_DIM, LAMP_HOT, STEEL, STRUCT, TRIM, SParts
from ship_rooms import Style, WF, WS, build_shell, dress_wall, place

X0 = 3.0                               # the shaft strip's depth: the lobby's own shell starts here (its left wall's structure is x 3.0 .. 3.2, the plane of the landing doors)
KIOSK = (7.3, 12.6)                    # where the plan puts the deck's directory (SM_SHIP_Directory_<deck>), in the lobby's frame


def _frame_door(b: SParts, y0: float) -> None:
    """The landing door's frame on the lobby's left wall (shifted frame: the wall's finished face is x = 0.25): a brushed frame round the opening, a header with the up and down arrows, the
    call panel beside it and a sill; the door's leaves are the lift engine's."""
    x = WS + WF
    w, h = LIFT_DOOR_W, LIFT_DOOR_H
    b.body.box((x, y0 - w / 2 - 0.16, 0.0), (x + 0.12, y0 - w / 2, h + 0.3), TRIM)
    b.body.box((x, y0 + w / 2, 0.0), (x + 0.12, y0 + w / 2 + 0.16, h + 0.3), TRIM)
    b.body.box((x, y0 - w / 2 - 0.16, h), (x + 0.12, y0 + w / 2 + 0.16, h + 0.3), TRIM)
    b.fine.box((x + 0.0, y0 - w / 2, 0.0), (x + 0.2, y0 + w / 2, 0.012), STEEL)
    b.emit.lamp_box((x + 0.121, y0 - w / 2 - 0.12, 0.3), (x + 0.126, y0 - w / 2 - 0.08, h - 0.2), "cyan_dim", LAMP_DIM)
    b.emit.lamp_box((x + 0.121, y0 + w / 2 + 0.08, 0.3), (x + 0.126, y0 + w / 2 + 0.12, h - 0.2), "cyan_dim", LAMP_DIM)
    b.fine.box((x + 0.0, y0 - 0.34, h + 0.34), (x + 0.1, y0 + 0.34, h + 0.62), TRIM)                       # the indicator over the door
    b.fine.box((x + 0.1, y0 - 0.32, h + 0.36), (x + 0.105, y0 + 0.32, h + 0.6), DGLASS)
    b.emit.label((x + 0.1055, y0 - 0.16, h + 0.48), 0.2, 0.2, (1, 0, 0), "arrow_up")
    b.emit.label((x + 0.1055, y0 + 0.16, h + 0.48), 0.2, 0.2, (1, 0, 0), "arrow_down")
    b.fine.box((x, y0 + w / 2 + 0.22, 1.0), (x + 0.07, y0 + w / 2 + 0.46, 1.4), TRIM)                      # the call panel: two buttons and a lamp
    for k, cell in enumerate(("amber", "ice")):
        b.emit.lamp_box((x + 0.071, y0 + w / 2 + 0.29, 1.22 - 0.13 * k), (x + 0.076, y0 + w / 2 + 0.39, 1.27 - 0.13 * k), cell, LAMP)
    b.emit.lamp_box((x + 0.071, y0 + w / 2 + 0.33, 1.34), (x + 0.075, y0 + w / 2 + 0.37, 1.37), "green", LAMP)


def _shafts(b: SParts, ys: tuple, h: float) -> None:
    """The shaft strip (frame of the lobby, x 0 .. 3.0): a tube of 0.2 m walls round each shaft (clear 2.8 x 2.8) from the floor structure to the roof structure, slabs of floor and
    ceiling between and beside them with no slab inside a tube."""
    fb = b.body
    hi = LIFT_OUT / 2
    segs = []
    prev = 0.0
    for y0 in ys:
        segs.append((prev, y0 - hi))
        prev = y0 + hi
        fb.box((0.0, y0 - hi, -0.3), (0.2, y0 + hi, h + 0.3), STRUCT)                                      # the back
        fb.box((0.2, y0 - hi, -0.3), (X0, y0 - LIFT_IN / 2, h + 0.3), STRUCT)                              # the sides
        fb.box((0.2, y0 + LIFT_IN / 2, -0.3), (X0, y0 + hi, h + 0.3), STRUCT)
        b.emit.lamp_box((X0 - 0.01, y0 - LIFT_IN / 2 + 0.05, 0.3), (X0, y0 - LIFT_IN / 2 + 0.09, h - 0.3), "cyan_dim", LAMP_DIM)
    segs.append((prev, 16.0))
    for (a, c) in segs:                                                                                      # slabs beside the shafts: floor and ceiling structure, and a blank wall
        if c - a < 0.05:
            continue
        fb.box((0.0, a, -0.3), (X0, c, -0.012), STRUCT)
        fb.box((0.0, a, h), (X0, c, h + 0.3), STRUCT)
        fb.box((0.0, a, 0.0), (X0, c, h), STRUCT)


def _bank(name: str, key: str):
    spec = SPEC.PREFABS[key]
    L, D, H = spec["L"], spec["D"], spec["h"]
    near_x = next(d["x"] for d in spec["doors"] if d["wall"] == "near")
    through = any(d["wall"] == "far" for d in spec["doors"])
    li = L - X0
    inner = dict(spec, L=li)
    doors = [{"wall": "near", "x": near_x - X0, "w": GATE_W, "h": GATE_H}] + ([{"wall": "far", "x": near_x - X0, "w": GATE_W, "h": GATE_H}] if through else [])
    doors += [{"wall": "left", "x": y0, "w": LIFT_DOOR_W, "h": LIFT_DOOR_H} for y0 in SPEC.LIFT_SHAFTS_Y]
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent="cyan_dim", cove="white_cool", strip="white_cool", rib_mat=TRIM, skirt=STRUCT)
    _shafts(b, SPEC.LIFT_SHAFTS_Y, H)
    with b.at(T(X0, 0.0, 0.0)):
        build_shell(b, inner, st, doors=doors)
        xr = li - WS - WF
        for y0 in SPEC.LIFT_SHAFTS_Y:
            _frame_door(b, y0)
        b.emit.label((WS + WF + 0.002, 8.0, 1.9), 0.55, 0.55, (1, 0, 0), "pict_lift")                    # the pictogram on the pier between the doors
        b.emit.label((WS + WF + 0.002, 8.0, 1.25), 0.7, 0.175, (1, 0, 0), "eq_lift")
        b.emit.lamp_box((1.0, 0.6, 0.0), (1.05, 15.4, 0.006), "cyan_dim", LAMP_DIM)                         # a guide line along the doors' foot
        b.emit.lamp_box((1.45, 4.6, 0.0), (1.5, 11.4, 0.006), "cyan_dim", LAMP_DIM)
        place(b, xr - 0.3, 8.0, 180, F.bench, 2.4, 0.45, 0.46, FABRIC_GREY)                               # the bench, planters and the right wall's screens
        for y in (3.4, 12.6):
            place(b, xr - 0.35, y, 180, F.planter, 1.4, 0.5, 0.45, 3, int(y), True)
        dress_wall(b, "right", li, D, H, 1.0, 15.0, 3, accent="cyan", accent_dim="cyan_dim", kinds=("screen", "plain", "safety", "vent"))
        for xs in (1.4, 2.6, 3.8):                                                                         # three long luminaires down the lobby
            b.body.box((xs - 0.17, 1.5, H - 0.07), (xs - 0.13, 14.5, H - 0.01), TRIM)
            b.body.box((xs + 0.13, 1.5, H - 0.07), (xs + 0.17, 14.5, H - 0.01), TRIM)
            b.emit.lamp_box((xs - 0.13, 1.5, H - 0.04), (xs + 0.13, 14.5, H - 0.032), "white_cool", LAMP_HOT)
        if not through:                                                                                    # an outer lane's lobby ends in a blank wall: a big plan of the section
            b.emit.label((2.5, D - WS - WF - 0.003, 1.9), 3.2, 1.8, (0, -1, 0), "scr_ship")
    return b.build(name)


def lift_bank(name: str = "SM_SHIP_LiftBank"):
    """8 x 16 x 3.7: a lobby in the Spine's inner lane — two gates (the Spine's, and the passage beyond: it is also the way across), two lifts' doors with their frames and call panels on the
    aft wall, a bench and planters on the right, a screen wall, long luminaires; the shafts behind the lifts' wall."""
    return _bank(name, "lift_bank")


def lift_bank_o(name: str = "SM_SHIP_LiftBankO"):
    """8 x 16 x 3.7: the same lobby in an outer lane: one gate (the side passage's), a plan of the section on the blank wall at the far end."""
    return _bank(name, "lift_bank_o")


def lift_bank_b(name: str = "SM_SHIP_LiftBankB"):
    """8 x 6.2 x 3.7: the command lobby on the decks under the bridge — a small hall against the Spine's port wall, one gate, the two command lifts' doors in the aft wall (the shafts, 3 m
    squares, stand behind it: x 8 .. 11), blue light, a bench and a plant."""
    spec = SPEC.PREFABS["lift_bank_b"]
    L, D, H = spec["L"], spec["D"], spec["h"]
    near_x = spec["doors"][0]["x"]
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent="command_dim", cove="white_cool", strip="white_cool", rib_mat=TRIM, skirt=STRUCT)
    ys = (1.7, 4.7)
    doors = [{"wall": "near", "x": near_x, "w": GATE_W, "h": GATE_H}] + [{"wall": "right", "x": D - y, "w": LIFT_DOOR_W, "h": LIFT_DOOR_H} for y in ys]
    build_shell(b, spec, st, doors=doors)
    fb = b.body
    for y0 in ys:                                                                                          # the shafts: a 3.0 m tube behind the aft wall
        hi = 1.5
        w_, h_ = LIFT_DOOR_W, LIFT_DOOR_H
        fb.box((L, y0 - hi, -0.3), (L + 0.2, y0 - w_ / 2, H + 0.3), STRUCT)                                # the shaft's front wall, open at the door
        fb.box((L, y0 + w_ / 2, -0.3), (L + 0.2, y0 + hi, H + 0.3), STRUCT)
        fb.box((L, y0 - w_ / 2, h_, ), (L + 0.2, y0 + w_ / 2, H + 0.3), STRUCT)
        fb.box((L + 0.2, y0 - hi, -0.3), (L + 3.0, y0 - 1.3, H + 0.3), STRUCT)
        fb.box((L + 0.2, y0 + 1.3, -0.3), (L + 3.0, y0 + hi, H + 0.3), STRUCT)
        fb.box((L + 2.8, y0 - hi, -0.3), (L + 3.0, y0 + hi, H + 0.3), STRUCT)
        x = L - WS - WF
        w, h = LIFT_DOOR_W, LIFT_DOOR_H
        b.body.box((x - 0.12, y0 - w / 2 - 0.16, 0.0), (x, y0 - w / 2, h + 0.3), TRIM)
        b.body.box((x - 0.12, y0 + w / 2, 0.0), (x, y0 + w / 2 + 0.16, h + 0.3), TRIM)
        b.body.box((x - 0.12, y0 - w / 2 - 0.16, h), (x, y0 + w / 2 + 0.16, h + 0.3), TRIM)
        b.fine.box((x - 0.2, y0 - w / 2, 0.0), (x, y0 + w / 2, 0.012), STEEL)
        b.emit.lamp_box((x - 0.126, y0 - w / 2 - 0.12, 0.3), (x - 0.121, y0 - w / 2 - 0.08, h - 0.2), "command_dim", LAMP_DIM)
        b.emit.lamp_box((x - 0.126, y0 + w / 2 + 0.08, 0.3), (x - 0.121, y0 + w / 2 + 0.12, h - 0.2), "command_dim", LAMP_DIM)
        b.emit.label((x - 0.101, y0 - 0.16, h + 0.48), 0.2, 0.2, (-1, 0, 0), "arrow_up")
        b.emit.label((x - 0.101, y0 + 0.16, h + 0.48), 0.2, 0.2, (-1, 0, 0), "arrow_down")
    place(b, 1.0, D - 0.6, 0, F.bench, 1.6, 0.45, 0.46, FABRIC_NAVY)
    place(b, 0.7, 0.9, 0, F.potted_plant, 1.3, 9)
    b.emit.label((L - WS - WF - 0.003, 3.2, 1.9), 0.55, 0.55, (-1, 0, 0), "pict_bridge")
    for xs in (2.0, 4.0, 6.0):
        b.body.box((xs - 0.17, 0.6, H - 0.07), (xs - 0.13, D - 0.6, H - 0.01), TRIM)
        b.body.box((xs + 0.13, 0.6, H - 0.07), (xs + 0.17, D - 0.6, H - 0.01), TRIM)
        b.emit.lamp_box((xs - 0.13, 0.6, H - 0.04), (xs + 0.13, D - 0.6, H - 0.032), "white_cool", LAMP_HOT)
    return b.build(name)
