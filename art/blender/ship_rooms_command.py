"""ASN Aquila interior kit: the rooms of the command deck (NAVE-2, Deck 2) — the Combat Information Centre, the briefing room, the communications centre, the offices, the
records archive, the VLS magazine, point-defence control and the turret barbette. The sensor room is the one of Deck 5 (ship_rooms_science2.py). Frames and sizes:
ship_rooms.py / ship_spec.py."""
from __future__ import annotations

import math

import ship_furniture as F
import ship_furniture2 as G
import ship_furniture3 as H
import ship_furniture6 as K6
import ship_furniture8 as K8
import ship_spec as SPEC
import ship_walls as W
from bridge3_lib import T
from ship_lib import (BEDDING, COMPOSITE, CRATE_GREY, CRATE_ORANGE, DECK, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST, FABRIC_SAND, LAMINATE, LAMP_DIM, LAMP_HOT, RUBBER,
                      STEEL, STRUCT, TRIM, WOOD, SParts)
from ship_rooms import (Style, WF, WS, build_shell, ceiling_panels, ceiling_services, dress_wall, place)
from ship_rooms_hub import on_wall


def _dims(key: str):
    s = SPEC.PREFABS[key]
    return s, s["L"], s["D"], s["h"]


def _style(accent: str = "command_dim", cove: str = "white_cool", lo: str = COMPOSITE, hi: str = COMPOSITE, floor: str = DECK, mode: str = "plates", wain: float = 1.2) -> Style:
    return Style(floor=floor, floor_mode=mode, wall_lo=lo, wall_hi=hi, wain_h=wain, ceil=COMPOSITE, accent=accent, cove=cove, rib_mat=TRIM, skirt=STRUCT)


# ---------------------------------------------------------------------------------------------------------------------- CIC
def cic(name: str = "SM_SHIP_Cic"):
    """32 x 16 x 3.6: the Combat Information Centre. Three big boards across the far wall (the tactical plot, the star chart, the ship's status), the plot table and its ring of light
    in front of them, two banks of six operator consoles (two rows of three) facing the boards on each side of a wide aisle, the communications racks on the left wall and the
    damage control board on the right."""
    spec, L, D, H_ = _dims("cic")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _style("command_dim", "white_cool"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for x, tile in ((5.0, "scr_tac"), (16.0, "scr_star"), (27.0, "scr_ship")):
        place(b, x, yf - 0.02, -90, H.wall_rack_panel, 8.0, 2.6, tile, "command")
    b.emit.label_fit((16.0, yf - 0.01, 3.2), 3.4, "st_tactical", (0, -1, 0))
    tiles = ["scr_tac", "scr_ship", "scr_map", "scr_data"]
    for bank, xs in (("left", (3.6, 7.0, 10.4)), ("right", (21.6, 25.0, 28.4))):
        for k, x in enumerate(xs):
            place(b, x, 9.2, -90, H.work_console, 3.0, "command", 2, tiles[k:] + tiles[:k], True, True)
            place(b, x, 7.95, 90, H.chair_op, FABRIC_NAVY)
            place(b, x, 5.4, -90, H.work_console, 3.0, "command", 2, tiles[k + 1:] + tiles[:k + 1], False, False)
            place(b, x, 4.15, 90, H.chair_op, FABRIC_NAVY)
    place(b, 16.0, 12.4, 0, G.holo_table, 1.6, 0.95)
    with b.at(T(16.0, 12.4, H_ - 0.35)):                                                                                # the ring of light over the plot table
        H.ring(b.body, 0.0, 0.0, 0.0, 1.9, 0.14, 0.12, TRIM, 40)
        H.lamp_ring(b.emit, 0.0, 0.0, -0.01, 1.9, 0.14, 0.012, "cyan", LAMP_DIM, 40)
        for k in range(4):
            a = math.pi / 2 * k + math.pi / 4
            b.soft.cyl((2.0 * math.cos(a), 2.0 * math.sin(a), 0.12), (2.0 * math.cos(a), 2.0 * math.sin(a), 0.35), 0.012, TRIM, seg=5)
    for dx in (-2.4, 2.4):
        place(b, 16.0 + dx, 12.4, 0, F.stool, 0.19, 0.72, FABRIC_RUST)
    place(b, xl + 0.45, 6.4, 0, H.rack_row, 5, 0.62, 0.95, 2.2, "cyan", 3)
    place(b, xl + 0.45, 11.6, 0, H.rack_row, 3, 0.62, 0.95, 2.2, "cyan", 4)
    b.emit.label_fit((xl + 0.002, 9.6, 2.6), 1.6, "st_comms", (1, 0, 0))
    place(b, xr - 0.02, 8.0, 180, H.wall_rack_panel, 5.2, 2.4, "scr_ship", "red")
    b.emit.label_fit((xr - 0.002, 11.4, 2.7), 1.4, "eq_dc", (-1, 0, 0))
    b.emit.label_fit((14.4, WF + 0.002, 2.0), 1.0, "eq_watch", (0, 1, 0))
    on_wall(b, "near", L, D, W.first_aid, b.body, L - 18.6, 1.4)
    on_wall(b, "near", L, D, W.extinguisher, b.body, L - 19.4, 0.0)
    dress_wall(b, "near", L, D, H_, 0.5, 12.0, 1, accent="command", accent_dim="command_dim", kinds=("plain", "vent", "panelboard", "safety"))
    dress_wall(b, "near", L, D, H_, 16.0, 31.5, 2, accent="command", accent_dim="command_dim", kinds=("plain", "conduits", "vent", "screen"))
    ceiling_services(b, L, D, H_, [(2.2, "tray"), (14.8, "tray")], 1.0, 31.0, 4)
    ceiling_panels(b, L, D, H_, 6, 3, "white_cool", 1.6, 1.2, 0.5, LAMP_HOT)
    return b.build(name)


# ---------------------------------------------------------------------------------------------------------------------- briefing room
def briefing(name: str = "SM_SHIP_Briefing"):
    """16 x 16 x 3.6: a long table with a chair at each place and one at each end, a wall of three displays and the ship's crest board behind the head of the table, a credenza
    with a coffee machine, a bookcase, framed charts on the side walls."""
    spec, L, D, H_ = _dims("briefing")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _style("command_dim", "white_warm", lo=WOOD, hi=COMPOSITE, wain=1.0))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    place(b, 8.0, 8.4, 0, K8.conference_table, 6.4, 1.6, 6)
    for k in range(6):
        x = 8.0 - 2.4 + k * 0.96
        place(b, x, 7.1, 90, H.chair_op, FABRIC_NAVY)
        place(b, x, 9.7, -90, H.chair_op, FABRIC_NAVY)
    place(b, 4.3, 8.4, 0, H.chair_op, FABRIC_RUST)
    place(b, 11.7, 8.4, 180, H.chair_op, FABRIC_RUST)
    for x, tile in ((4.2, "scr_map"), (8.0, "scr_tac"), (11.8, "scr_ship")):
        place(b, x, yf - 0.02, -90, F.wall_screen, 3.2, 1.8, tile, z=1.9)
    place(b, 8.0, 2.0, 90, F.counter, 3.0, 0.6, 0.92, STEEL, COMPOSITE, True, False)
    place(b, 6.6, 1.9, 90, G.coffee_machine)
    place(b, xr - 0.2, 11.0, 180, F.shelf, 2.4, 0.34, 2.0, 5)
    place(b, xl, 5.0, 0, F.wall_screen, 2.0, 1.2, "scr_star", z=1.8)
    place(b, xr - 0.02, 5.0, 180, F.wall_screen, 2.0, 1.2, "scr_sched", z=1.8)
    place(b, 2.0, 14.4, 0, F.potted_plant, 1.3, 5)
    place(b, 14.0, 14.4, 0, F.potted_plant, 1.2, 6)
    b.soft.box((xl, 12.4, 0.9), (xl + 0.03, 14.0, 2.7), FABRIC_NAVY)                                                    # the ship's banner
    b.soft.box((xl + 0.03, 12.4, 2.62), (xl + 0.04, 14.0, 2.7), CRATE_ORANGE)
    on_wall(b, "near", L, D, W.first_aid, b.body, L - 12.0, 1.4)
    dress_wall(b, "near", L, D, H_, 8.0, 15.5, 1, accent="command", accent_dim="command_dim", kinds=("plain", "panelboard"))
    ceiling_panels(b, L, D, H_, 3, 3, "white_warm", 1.6, 1.2, 0.6, LAMP_HOT)
    return b.build(name)


# ---------------------------------------------------------------------------------------------------------------------- communications
def comms_center(name: str = "SM_SHIP_CommsCenter"):
    """24 x 16 x 3.6: three rows of operator stations facing the far wall (four a row, the aisle in the middle), a wall of fleet-net displays and the subspace relay status, the
    relay racks on the left wall and the antenna mast mimic on the right."""
    spec, L, D, H_, = _dims("comms_center")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _style("command_dim", "white_cool"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    place(b, 6.0, yf - 0.02, -90, H.wall_rack_panel, 5.6, 2.6, "scr_map", "command")
    place(b, 12.0, yf - 0.02, -90, H.wall_rack_panel, 5.6, 2.6, "scr_data", "command")
    place(b, 18.0, yf - 0.02, -90, H.wall_rack_panel, 5.6, 2.6, "scr_wave", "command")
    b.emit.label_fit((12.0, yf - 0.01, 3.2), 3.2, "st_comms", (0, -1, 0))
    tiles = ["scr_data", "scr_wave", "scr_map", "scr_ship"]
    for r, y in enumerate((11.2, 8.0, 4.8)):
        for k, x in enumerate((4.0, 7.4, 16.6, 20.0)):
            place(b, x, y, -90, H.work_console, 2.6, "command", 2 if r == 0 else 1, tiles[k:] + tiles[:k], r == 0, r == 0)
            place(b, x, y - 1.25, 90, H.chair_op, FABRIC_NAVY)
    place(b, xl + 0.45, 6.0, 0, H.rack_row, 6, 0.62, 0.95, 2.2, "cyan", 7)
    place(b, xl + 0.45, 10.4, 0, H.rack_row, 4, 0.62, 0.95, 2.2, "cyan", 8)
    place(b, xr - 0.02, 9.0, 180, H.wall_rack_panel, 5.0, 2.6, "scr_tac", "command")
    b.emit.label_fit((xr - 0.002, 12.4, 2.7), 1.4, "eq_comm", (-1, 0, 0))
    b.emit.label_fit((12.4, WF + 0.002, 2.0), 1.0, "eq_notice", (0, 1, 0))
    on_wall(b, "near", L, D, W.first_aid, b.body, L - 17.4, 1.4)
    on_wall(b, "near", L, D, W.extinguisher, b.body, L - 18.2, 0.0)
    dress_wall(b, "near", L, D, H_, 0.5, 8.0, 1, accent="command", accent_dim="command_dim", kinds=("plain", "vent", "panelboard", "safety"))
    dress_wall(b, "near", L, D, H_, 13.0, 23.5, 2, accent="command", accent_dim="command_dim", kinds=("plain", "conduits", "vent"))
    ceiling_services(b, L, D, H_, [(2.0, "tray"), (14.4, "tray")], 1.0, 23.0, 5)
    ceiling_panels(b, L, D, H_, 4, 3, "white_cool", 1.6, 1.2, 0.5, LAMP_HOT)
    return b.build(name)


# ---------------------------------------------------------------------------------------------------------------------- offices
def offices(name: str = "SM_SHIP_Offices"):
    """16 x 16 x 3.4: a department's open office. Four desks with their partitions in two columns, the clerks facing each other's backs, a table with a plotter in the middle, filing
    cabinets and shelves along the walls, a notice board, a potted plant in every corner."""
    spec, L, D, H_ = _dims("offices")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    build_shell(b, spec, _style("command_dim", "white_warm", lo=FABRIC_SAND, hi=COMPOSITE, floor=FABRIC_GREY, mode="covering", wain=1.0))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for y in (4.6, 10.6):
        place(b, 3.6, y, 0, K8.desk_pod, 1.4, 0.8)
        place(b, 2.4, y, 0, H.chair_op, FABRIC_NAVY)
        place(b, 12.4, y, 180, K8.desk_pod, 1.4, 0.8)
        place(b, 13.6, y, 180, H.chair_op, FABRIC_NAVY)
    place(b, 8.0, 13.2, 0, F.table, 2.0, 1.0, 0.8, LAMINATE, TRIM, False)
    with b.at(T(8.0, 13.2, 0.8)):
        b.body.box((-0.5, -0.3, 0.0), (0.4, 0.3, 0.3), CRATE_GREY)
        b.soft.box((-0.5, -0.3, 0.3), (0.4, 0.3, 0.33), STRUCT)
        b.soft.box((0.5, -0.25, 0.0), (0.8, 0.25, 0.03), BEDDING)
    place(b, xl + 0.35, 8.0, 0, K8.filing_cabinet, 4, 0.5, 1.35)
    place(b, xr - 0.35, 8.0, 180, K8.filing_cabinet, 4, 0.5, 1.35)
    place(b, 4.0, yf - 0.2, -90, F.shelf, 2.4, 0.34, 2.0, 5)
    place(b, 12.0, yf - 0.2, -90, F.shelf, 2.4, 0.34, 2.0, 5)
    place(b, 8.0, yf - 0.02, -90, F.wall_screen, 2.2, 1.2, "scr_sched", z=1.9)
    for (x, y) in ((1.2, 1.4), (14.8, 1.4), (1.2, 14.6), (14.8, 14.6)):
        place(b, x, y, 0, F.potted_plant, 1.3, int(x + y))
    b.emit.label_fit((3.2, WF + 0.002, 1.9), 1.0, "eq_notice", (0, 1, 0))
    on_wall(b, "near", L, D, W.first_aid, b.body, L - 9.6, 1.4)
    dress_wall(b, "near", L, D, H_, 8.5, 15.5, 1, accent="command", accent_dim="command_dim", kinds=("plain", "panelboard"))
    ceiling_panels(b, L, D, H_, 3, 3, "white_warm", 1.6, 1.2, 0.6, LAMP_HOT)
    return b.build(name)


def records(name: str = "SM_SHIP_Records"):
    """12 x 16 x 3.4: the ship's records and archive. Three moving shelf units of file boxes in a row with their aisles, a reading table with a lamp, an index terminal by the door,
    cabinets of personnel files along the right wall."""
    spec, L, D, H_ = _dims("records")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    build_shell(b, spec, _style("command_dim", "white_warm", lo=WOOD, hi=COMPOSITE, wain=1.0))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for x in (1.2, 3.9, 6.6):
        place(b, x, 9.6, 0, K8.compact_shelving, 6.0, 0.9, 2.2)
    place(b, 9.8, 12.4, 0, F.table, 1.8, 1.0, 0.76, WOOD, TRIM, False)
    for dy in (-0.6, 0.6):
        place(b, 9.1, 12.4 + dy, 0, F.chair, FABRIC_RUST)
    place(b, 9.8, 12.4, 0, F.monitor, 0.4, 0.26, "scr_data", False, z=0.76)
    place(b, 10.2, 2.4, 90, F.desk, 1.4, 0.7, 0.78, STEEL, False)
    place(b, 10.2, 2.6, -90, F.monitor, 0.5, 0.3, "scr_data", False, z=0.78)
    place(b, 10.2, 1.5, 90, H.chair_op, FABRIC_RUST)
    place(b, xr - 0.35, 6.4, 180, K8.filing_cabinet, 4, 0.5, 1.35)
    place(b, xr - 0.35, 8.8, 180, K8.filing_cabinet, 4, 0.5, 1.35)
    b.emit.label_fit((xl + 0.002, 4.0, 2.4), 1.0, "eq_notice", (1, 0, 0))
    dress_wall(b, "near", L, D, H_, 0.5, 4.6, 1, accent="command", accent_dim="command_dim", kinds=("plain", "panelboard"))
    ceiling_panels(b, L, D, H_, 2, 3, "white_warm", 1.4, 1.0, 0.5, LAMP_HOT)
    return b.build(name)


# ---------------------------------------------------------------------------------------------------------------------- weapons
def vls_magazine(name: str = "SM_SHIP_VlsMagazine"):
    """24 x 16 x 3.6: the reload hall of the vertical launch cells. Two blocks of forty cells' worth of steel tubes (four columns by five rows each) rising to the ceiling with their
    caps and gas vents, the aisle between them with a gantry rail and a missile on its sling, the hoist head by the far wall, sprinkler mains and a hazard border round each block."""
    spec, L, D, H_ = _dims("vls_magazine")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    build_shell(b, spec, _style("security_dim", "white_warm", lo=CRATE_GREY, hi=COMPOSITE))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    k = 0
    for gx in (3.2, 15.8):
        for r in range(5):
            for c in range(4):
                place(b, gx + c * 1.6, 5.4 + r * 1.6, 0, K8.vls_cell, H_ - 0.7, k)
                k += 1
        b.soft.box((gx - 0.9, 4.4, 0.0), (gx + 3 * 1.6 + 0.9, 12.8 + 0.8, 0.012), CRATE_ORANGE)
        b.soft.box((gx - 0.8, 4.5, 0.012), (gx + 3 * 1.6 + 0.8, 12.7 + 0.8, 0.016), RUBBER)
    with b.at(T(1.0, 0.0, 0.0)):
        G.overhead_rail(b, 22.0, 8.4, H_ - 0.45, 11.0)
    for x in (3.0, 8.0, 13.0, 18.0, 22.0):
        b.soft.cyl((x, 8.4, H_ - 0.45), (x, 8.4, H_), 0.03, TRIM, seg=6)
    with b.at(T(12.0, 8.4, 0.0)):                                                                                       # a missile on its sling under the hoist
        b.soft.tube([(0.0, 0.0, H_ - 1.0), (-0.5, 0.0, H_ - 1.6), (-0.9, 0.0, 1.4)], 0.012, TRIM, seg=5)
        b.soft.tube([(0.0, 0.0, H_ - 1.0), (0.5, 0.0, H_ - 1.6), (0.9, 0.0, 1.4)], 0.012, TRIM, seg=5)
        with b.at(T(0.0, 0.0, 1.25)):
            K6.missile(b, 2.4, 0.12)
    place(b, 12.0, 13.4, 0, K6.hoist_platform, 1.9)
    for y in (3.0, 14.2):
        K6.sprinkler_line(b, (1.0, y, H_ - 0.28), (L - 1.0, y, H_ - 0.28))
    place(b, 21.6, 2.6, 90, F.desk, 1.6, 0.7, 0.8, STEEL, False)
    place(b, 21.6, 2.8, -90, F.monitor, 0.5, 0.3, "scr_sched", False, z=0.8)
    place(b, 21.6, 1.7, 90, H.chair_op, FABRIC_RUST)
    b.emit.label_fit((xl + 0.002, 8.0, 2.4), 1.6, "eq_ammo", (1, 0, 0))
    on_wall(b, "near", L, D, W.extinguisher, b.body, L - 7.4, 0.0)
    on_wall(b, "near", L, D, W.first_aid, b.body, L - 8.0, 1.4)
    dress_wall(b, "near", L, D, H_, 0.5, 8.0, 1, accent="security", accent_dim="security_dim", kinds=("plain", "vent", "safety", "panelboard"))
    dress_wall(b, "near", L, D, H_, 13.0, 19.0, 2, accent="security", accent_dim="security_dim", kinds=("plain", "safety", "conduits"))
    ceiling_panels(b, L, D, H_, 4, 3, "white_warm", 1.6, 1.2, 0.5, LAMP_HOT)
    return b.build(name)


def point_defense(name: str = "SM_SHIP_PointDefense"):
    """16 x 16 x 3.6: point-defence control. Four gunners' stations in a row facing four big gun-camera displays on the far wall, the chief's double console behind them, the weapons
    status board on the left wall and the gun-bay interlocks on the right."""
    spec, L, D, H_ = _dims("point_defense")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    build_shell(b, spec, _style("security_dim", "white_cool"))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    for x, tile in ((3.2, "scr_tac"), (6.4, "scr_star"), (9.6, "scr_tac"), (12.8, "scr_map")):
        place(b, x, yf - 0.02, -90, F.wall_screen, 2.9, 1.8, tile, z=2.0)
    for x in (3.2, 6.4, 9.6, 12.8):
        place(b, x, 11.2, -90, H.work_console, 2.4, "security", 2, ["scr_tac", "scr_data"], True, True)
        place(b, x, 9.95, 90, H.chair_op, FABRIC_RUST)
    place(b, 8.0, 6.2, -90, H.work_console, 4.4, "security", 3, ["scr_tac", "scr_ship", "scr_data", "scr_map"], False, False)
    place(b, 8.0, 4.95, 90, H.chair_op, FABRIC_RUST)
    place(b, xl + 0.02, 7.0, 0, H.wall_rack_panel, 4.6, 2.4, "scr_ship", "red")
    place(b, xr - 0.4, 6.0, 180, H.hv_cabinet, 0.9, 0.72, 2.2, 3)
    b.emit.label_fit((xr - 0.002, 9.4, 2.4), 1.4, "eq_ammo", (-1, 0, 0))
    b.emit.label_fit((6.4, WF + 0.002, 2.0), 1.0, "eq_watch", (0, 1, 0))
    on_wall(b, "near", L, D, W.first_aid, b.body, L - 9.4, 1.4)
    dress_wall(b, "near", L, D, H_, 0.5, 4.0, 1, accent="security", accent_dim="security_dim", kinds=("plain", "vent", "safety"))
    dress_wall(b, "near", L, D, H_, 8.0, 15.5, 2, accent="security", accent_dim="security_dim", kinds=("plain", "panelboard", "conduits"))
    ceiling_services(b, L, D, H_, [(2.4, "tray")], 1.0, 15.0, 3)
    ceiling_panels(b, L, D, H_, 3, 3, "white_cool", 1.6, 1.2, 0.5, LAMP_HOT)
    return b.build(name)


def barbette(name: str = "SM_SHIP_Barbette"):
    """24 x 16 x 3.6: the lower mount of a railgun turret. The armoured trunk of the turret fills the right half of the room, floor to ceiling, with its ring bearing, hatch and
    rams; to its left the railgun's breech with the capacitor columns on both sides and the loading tray; the shell hoist stands in the far corner; the gun crew's lockers and the
    control post by the door."""
    spec, L, D, H_ = _dims("barbette")
    b = SParts(bevel=0.005, fine_bevel=0.0)
    build_shell(b, spec, _style("security_dim", "white_warm", lo=CRATE_GREY, hi=COMPOSITE))
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    place(b, 17.2, 8.4, 0, K8.turret_trunk, 2.8, H_)
    place(b, 4.4, 8.6, 180, K8.railgun_breech)
    b.body.box((xr - 1.4, yf - 1.2, 0.0), (xr - 0.4, yf - 0.2, H_), STRUCT)                                              # the shell hoist column
    b.body.box((xr - 1.5, yf - 1.3, 1.2), (xr - 0.3, yf - 0.1, 1.6), CRATE_ORANGE)
    b.emit.label_fit((xr - 1.4 - 0.002, yf - 0.7, 2.4), 0.9, "eq_ammo", (-1, 0, 0))
    place(b, xl + 0.4, 3.0, 0, F.locker_row, 5, 0.5, 2.0, 0.55, CRATE_GREY)
    place(b, 10.5, 2.3, 90, F.desk, 1.8, 0.7, 0.8, STEEL, False)
    place(b, 10.5, 2.5, -90, F.monitor, 0.5, 0.3, "scr_ship", False, z=0.8)
    place(b, 10.5, 1.5, 90, H.chair_op, FABRIC_RUST)
    for y in (2.8, 13.8):
        K6.sprinkler_line(b, (1.0, y, H_ - 0.28), (L - 1.0, y, H_ - 0.28))
    on_wall(b, "near", L, D, W.first_aid, b.body, L - 7.4, 1.4)
    on_wall(b, "near", L, D, W.extinguisher, b.body, L - 8.0, 0.0)
    dress_wall(b, "near", L, D, H_, 12.0, 23.5, 1, accent="security", accent_dim="security_dim", kinds=("plain", "safety", "conduits", "vent"))
    dress_wall(b, "far", L, D, H_, 8.0, 15.0, 2, accent="security", accent_dim="security_dim", kinds=("panelboard", "vent", "conduits"))
    ceiling_panels(b, L, D, H_, 4, 3, "white_warm", 1.6, 1.2, 0.5, LAMP_HOT)
    return b.build(name)
