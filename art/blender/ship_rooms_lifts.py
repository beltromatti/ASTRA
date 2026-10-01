"""ASN Aquila interior kit (NAVE-3): the turbolift lobbies — the bank of two shafts between a main corridor and the passage beyond (lift_bank: gates on both sides; lift_bank_o: in an outer
lane, one gate), the command lobby under the bridge (lift_bank_b) and the Deck 1 housing of the same two command shafts (lift_housing_bridge). A lobby is a hall with the lifts' doors on
one long wall and the shafts behind it (their walls, 0.2 m thick, run through every deck: the floor and the ceiling of the lobby have no slab where a shaft is, so the shaft is one free volume
from the top deck to the bottom one, as the plan's `lift` compartments say; the cars, the doors' leaves and the machinery are the lift engine's: AstraLift*). The kit draws the door's frame, its
indicator, the call panel and the sill, the engine its leaves and what goes with them: the two read as one door (the plan's landing door is on the lobby face of the shaft's wall).
Frames and sizes: ship_rooms.py / ship_spec.py."""
from __future__ import annotations

import ship_furniture as F
import ship_spec as SPEC
from bridge3_lib import T
from ship_catalog import BRIDGE_SHAFT_Y, GATE_H, GATE_W, HOUSING_ORIGIN, LIFT_DOOR_H, LIFT_DOOR_W, LIFT_IN, LIFT_OUT
from ship_lib import COMPOSITE, DECK, DGLASS, FABRIC_GREY, FABRIC_NAVY, LAMP, LAMP_DIM, LAMP_HOT, STEEL, STRUCT, TRIM, SParts
from ship_rooms import Style, WF, WS, build_shell, dress_wall, place, wall_matrix

X0 = 3.0                               # the shaft strip's depth: the lobby's own shell starts here (its left wall's structure is x 3.0 .. 3.2, the plane of the landing doors)
KIOSK = (7.3, 12.6)                    # where the plan puts the deck's directory (SM_SHIP_Directory_<deck>), in the lobby's frame
PORTAL_H = 2.5                         # the corridor's mouth into the Deck 1 housing: the old corridor's walls are vertical up to 2.5 m, its roof chamfers from there


def _frame_door(b: SParts, wall: str, L: float, D: float, s: float, accent: str, compact: bool = False) -> None:
    """The landing door's frame on a lobby wall, drawn in the wall's own frame (s along the wall, t outward from its finished face, z up; the lobby is the t < 0 side): a brushed frame round the
    opening, a header with the up and down arrows, the call panel beside it (on the +s side) and a sill; the door's leaves are the lift engine's. `compact`: a low room (the Deck 1 housing has
    no space over the header): the arrows sit on the header itself."""
    w, h = LIFT_DOOR_W, LIFT_DOOR_H
    t = -WF                                                                                         # the wall's finished surface (its finish layer is t -0.05 .. 0)
    with b.at(wall_matrix(wall, L, D)):
        b.body.box((s - w / 2 - 0.16, t - 0.12, 0.0), (s - w / 2, t, h + 0.3), TRIM)
        b.body.box((s + w / 2, t - 0.12, 0.0), (s + w / 2 + 0.16, t, h + 0.3), TRIM)
        b.body.box((s - w / 2 - 0.16, t - 0.12, h), (s + w / 2 + 0.16, t, h + 0.3), TRIM)
        b.fine.box((s - w / 2, t - 0.2, 0.0), (s + w / 2, t, 0.012), STEEL)
        b.emit.lamp_box((s - w / 2 - 0.12, t - 0.126, 0.3), (s - w / 2 - 0.08, t - 0.121, h - 0.2), accent, LAMP_DIM)
        b.emit.lamp_box((s + w / 2 + 0.08, t - 0.126, 0.3), (s + w / 2 + 0.12, t - 0.121, h - 0.2), accent, LAMP_DIM)
        if compact:
            b.fine.box((s - 0.32, t - 0.125, h + 0.05), (s + 0.32, t - 0.12, h + 0.25), DGLASS)       # the indicator: a dark glass strip on the header's face
            zc, face = h + 0.15, t - 0.1255
        else:
            b.fine.box((s - 0.34, t - 0.1, h + 0.34), (s + 0.34, t, h + 0.62), TRIM)                  # the indicator over the door
            b.fine.box((s - 0.32, t - 0.105, h + 0.36), (s + 0.32, t - 0.1, h + 0.6), DGLASS)
            zc, face = h + 0.48, t - 0.1055
        b.emit.label((s - 0.16, face, zc), 0.2, 0.2, (0, -1, 0), "arrow_up")
        b.emit.label((s + 0.16, face, zc), 0.2, 0.2, (0, -1, 0), "arrow_down")
        b.fine.box((s + w / 2 + 0.22, t - 0.07, 1.0), (s + w / 2 + 0.46, t, 1.4), TRIM)              # the call panel: two buttons and a lamp
        for k, cell in enumerate(("amber", "ice")):
            b.emit.lamp_box((s + w / 2 + 0.29, t - 0.076, 1.22 - 0.13 * k), (s + w / 2 + 0.39, t - 0.071, 1.27 - 0.13 * k), cell, LAMP)
        b.emit.lamp_box((s + w / 2 + 0.33, t - 0.075, 1.34), (s + w / 2 + 0.37, t - 0.071, 1.37), "green", LAMP)


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


def _tubes(b: SParts, x0: float, ys: tuple, h: float, roof_t: float | None = None, back_inset: float = 0.0) -> None:
    """The two command shafts' tubes (3.0 m outside, 2.6 inside, walls of 0.2 m) behind the shell's aft wall, which is their front wall: sides and back, from the floor structure up to the roof
    (open at the top and the bottom: the shaft goes on through the decks) or, with `roof_t`, to a closed roof of that thickness; no slab inside a tube. `x0`: where the tubes start (the shell's
    aft face); `back_inset`: how far the back wall stops short of 3.0 m (so as not to share a plane with the block outside)."""
    fb = b.body
    hi = 1.5
    top = h + (0.3 if roof_t is None else roof_t)
    for y0 in ys:
        fb.box((x0, y0 - hi, -0.3), (x0 + 2.8, y0 - 1.3, top), STRUCT)
        fb.box((x0, y0 + 1.3, -0.3), (x0 + 2.8, y0 + hi, top), STRUCT)
        fb.box((x0 + 2.6, y0 - hi, -0.3), (x0 + 2.8 - back_inset, y0 + hi, top), STRUCT)
        if roof_t is not None:
            fb.box((x0, y0 - hi, h), (x0 + 2.8 - back_inset, y0 + hi, top), STRUCT)


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
            _frame_door(b, "left", li, D, y0, "cyan_dim")
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
    """8 x 6.2 x 3.7: the command lobby on the decks under the bridge — a small hall against the Spine's port wall, one gate, the two command lifts' doors with their frames and call panels in the
    aft wall (the shafts, 3 m squares, stand behind it: x 8 .. 11; its structure, x 8 .. 8.2, is their front wall: the plan's landing doors are on its lobby face), blue light, a bench and a plant."""
    spec = SPEC.PREFABS["lift_bank_b"]
    L, D, H = spec["L"], spec["D"], spec["h"]
    near_x = spec["doors"][0]["x"]
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent="command_dim", cove="white_cool", strip="white_cool", rib_mat=TRIM, skirt=STRUCT)
    ys = (1.7, 4.7)
    doors = [{"wall": "near", "x": near_x, "w": GATE_W, "h": GATE_H}] + [{"wall": "right", "x": D - y, "w": LIFT_DOOR_W, "h": LIFT_DOOR_H} for y in ys]
    lw = L + 0.2                                                                                           # the shell's aft wall (structure x 8.0 .. 8.2) IS the shafts' front wall
    build_shell(b, dict(spec, L=lw), st, doors=doors)
    _tubes(b, lw, ys, H)
    for y in ys:
        _frame_door(b, "right", lw, D, D - y, "command_dim")
    place(b, 1.0, D - 0.6, 0, F.bench, 1.6, 0.45, 0.46, FABRIC_NAVY)
    place(b, 0.7, 0.9, 0, F.potted_plant, 1.3, 9)
    b.emit.label((lw - WS - WF - 0.003, 3.2, 1.9), 0.55, 0.55, (-1, 0, 0), "pict_bridge")
    for xs in (2.0, 4.0, 6.0):
        b.body.box((xs - 0.17, 0.6, H - 0.07), (xs - 0.13, D - 0.6, H - 0.01), TRIM)
        b.body.box((xs + 0.13, 0.6, H - 0.07), (xs + 0.17, D - 0.6, H - 0.01), TRIM)
        b.emit.lamp_box((xs - 0.13, 0.6, H - 0.04), (xs + 0.13, D - 0.6, H - 0.032), "white_cool", LAMP_HOT)
    return b.build(name)


def lift_housing_bridge(name: str = "SM_SHIP_LiftHousingBridge"):
    """2 x 6.96 x 2.9: the housing of the two command lifts on Deck 1, in the block behind the port corridor's end (placed at yaw 180: x runs aft from the corridor's mouth, y to port): the fore
    wall (x 0 .. 0.2, where the corridor's end cap stood) has the corridor's 3.2 m mouth, the aft wall (x 2.0 .. 2.2) the two lifts' doors with their frames and call panels, and behind it the
    shafts' tubes (x 2.2 .. 5.0) go up to a closed roof; a bench and a plant in the vestibule, blue light. Low (the block outside leaves 3.15 m) and 2 cm inside it, so as not to share a plane
    with the faces of `SM_SHIP_ASTRA_AquilaBridgeBlock`. The plan's landing doors are on the lobby face of the aft wall (x 2.0, the world's x -22.8)."""
    spec = SPEC.PREFABS["lift_housing_bridge"]
    L, D, H = spec["L"], spec["D"], spec["h"]
    oy = HOUSING_ORIGIN[1]
    ys = tuple(oy - wy for wy in BRIDGE_SHAFT_Y)                                                           # the shafts' middle in the mesh's frame (to port of its origin)
    portal = oy + 3.9                                                                                      # the corridor's centre line, y -3.9
    lw = L + 0.2                                                                                           # the shell's aft wall IS the shafts' front wall
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent="command_dim", cove="white_cool", strip="white_cool", rib_mat=TRIM, skirt=STRUCT)
    doors = [{"wall": "left", "x": portal, "w": 3.2, "h": PORTAL_H}] + [{"wall": "right", "x": D - y, "w": LIFT_DOOR_W, "h": LIFT_DOOR_H} for y in ys]
    build_shell(b, dict(spec, L=lw), st, doors=doors, bare=(), ceil_t=0.22)
    _tubes(b, lw, ys, H, roof_t=0.22, back_inset=0.03)
    for y in ys:
        _frame_door(b, "right", lw, D, D - y, "command_dim", compact=True)
    place(b, 1.1, 0.30, 90, F.bench, 1.4, 0.45, 0.46, FABRIC_NAVY)
    place(b, 0.9, D - 0.65, 0, F.potted_plant, 1.2, 9)
    b.emit.label((lw - WS - WF - 0.003, (ys[0] + ys[1]) / 2, 1.9), 0.55, 0.55, (-1, 0, 0), "pict_bridge")
    for xs in (0.8, 1.45):
        b.body.box((xs - 0.17, 0.5, H - 0.07), (xs - 0.13, D - 0.5, H - 0.01), TRIM)
        b.body.box((xs + 0.13, 0.5, H - 0.07), (xs + 0.17, D - 0.5, H - 0.01), TRIM)
        b.emit.lamp_box((xs - 0.13, 0.5, H - 0.04), (xs + 0.13, D - 0.5, H - 0.032), "white_cool", LAMP_HOT)
    return b.build(name)
