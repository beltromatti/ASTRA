"""ASN Aquila interior kit: the science rooms of Deck 5 (NAVE-2) — the Transporter Room (six pads), the sensor archive, the sensor array room and the
laboratories (biology, astrometrics, physics, chemistry). Frames and sizes: ship_rooms.py / ship_spec.py."""
from __future__ import annotations

import math
import random

import ship_furniture as F
import ship_furniture2 as G
import ship_furniture3 as H
import ship_spec as SPEC
import ship_walls as W
from bridge3_lib import Rx, Rz, T, frame
from ship_lib import (BEDDING, COMPOSITE, CRATE_BLUE, CRATE_GREY, CRATE_OLIVE, CRATE_ORANGE, DECK, DGLASS, FABRIC_GREY, FABRIC_NAVY, FABRIC_RUST,
                      FABRIC_SAND, GLASS, IVORY, LAMINATE, LAMP, LAMP_DIM, LAMP_HOT, LEAF, PAINT_RED, RUBBER, SOIL, STEEL, STRUCT, TILE, TRIM, WOOD,
                      SParts, lamp_strip)
from ship_rooms import (Style, WF, WS, build_shell, ceiling_panels, ceiling_services, dress_wall, luminaire_strips, place, wall_finish, wall_label,
                        wall_matrix)
from ship_rooms_hub import on_wall


def _dims(key: str):
    s = SPEC.PREFABS[key]
    return s, s["L"], s["D"], s["h"]


# ---------------------------------------------------------------------------------------------------------------------- transporter
def transporter(name: str = "SM_SHIP_Transporter"):
    """24 x 16 x 3.8: the pad platform (six pads on a raised dais, the emitter ring overhead) in the far right of the room, the control console facing it, a row of
    pattern buffers along the far wall, a decontamination booth and equipment lockers on the left wall, a cargo pad with a trolley and crates in the back corner."""
    spec, L, D, H_ = _dims("transporter")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent="science_dim", cove="science_dim",
               rib_mat=TRIM, skirt=STRUCT)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    cx, cy = 17.0, 8.6                                                      # the platform's centre
    with b.at(T(cx, cy, 0.0)):
        H.transporter_dais(b, 3.3, 6, 0.62, 2.0, 0.30)
        H.emitter_ring(b, 3.0, 2.95, 6, 2.0, H_)
    # the control console between its operators and the platform (they face +x over a low console), the operators' chairs
    place(b, 10.0, 8.6, 180, H.work_console, 4.4, "science", 3, ["scr_map", "scr_lab", "scr_ship", "scr_data"], True, False)
    place(b, 8.4, 7.0, 0, H.chair_op, FABRIC_NAVY)
    place(b, 8.4, 10.2, 0, H.chair_op, FABRIC_NAVY)
    # the chief's desk by the right wall, with a wall display above it
    place(b, xr - 0.45, 3.0, 180, F.desk, 1.6, 0.7, 0.76, LAMINATE, True)
    place(b, xr - 0.45, 3.0, 180, F.monitor, 0.5, 0.3, "scr_sched", False, z=0.76)
    place(b, xr - 1.4, 3.0, 0, H.chair_op, FABRIC_RUST)
    place(b, xr - 0.02, 7.0, 180, H.wall_rack_panel, 4.2, 2.4, "scr_ship", "cyan")
    # pattern buffers along the far wall, between ribs, their feed conduits to the ceiling
    for k in range(5):
        place(b, 4.2 + k * 3.0, yf - 0.62, 0, H.pattern_buffer, 2.7, 0.42, "cyan")
        b.body.box((4.2 + k * 3.0 - 0.18, yf - 0.34, 2.7), (4.2 + k * 3.0 + 0.18, yf, H_), STRUCT)
    on_wall(b, "far", L, D, W.cable_runs, b.body, 2.4, 21.6, H_, random.Random(3), True, 2)
    # the left wall: a decontamination booth, bio-filter lockers, a sink and an eyewash
    place(b, xl + 0.8, 3.2, 90, H.decon_booth, 1.5, 1.5, 2.4)
    place(b, xl + 0.3, 6.4, 0, F.locker_row, 4, 0.45, 1.95, 0.5, COMPOSITE)
    place(b, xl + 0.45, 10.6, 0, F.steel_sink_unit, 1.2, 0.7)
    on_wall(b, "left", L, D, W.first_aid, b.body, 12.4, 1.4)
    on_wall(b, "left", L, D, W.extinguisher, b.body, 13.2, 0.0)
    # the cargo transporter: a small platform with a hazard border, a trolley and crates
    with b.at(T(4.6, 13.0, 0.0)):
        b.body.box((-1.4, -1.4, 0.0), (1.4, 1.4, 0.18), STRUCT)
        b.body.box((-1.45, -1.45, 0.17), (1.45, 1.45, 0.20), TRIM)
        b.emit.label((0.0, -1.25, 0.205), 2.4, 0.16, (0, 0, 1), "hazard_h", up=(0, 1, 0))
        b.emit.label((0.0, 1.25, 0.205), 2.4, 0.16, (0, 0, 1), "hazard_h", up=(0, 1, 0))
        with b.at(T(0.0, 0.0, 0.2)):
            H.transporter_pad(b, 0.8)
        H.lamp_ring(b.emit, 0.0, 0.0, 3.35, 0.7, 0.1, 0.008, "cyan", LAMP, 24)
        H.ring(b.body, 0.0, 0.0, 3.2, 0.7, 0.14, 0.15, COMPOSITE, 24)
        b.body.cyl((0, 0, 3.35), (0, 0, H_), 0.12, TRIM, seg=8)
    place(b, 7.6, 14.0, 90, F.pallet, 1.2, 0.8)
    for j in range(3):
        place(b, 7.6, 14.0, 90 + 6 * j, F.crate, 0.8, 0.55, 0.45, [CRATE_OLIVE, CRATE_GREY, CRATE_ORANGE][j], None, False, z=0.145 + 0.45 * j)
    # floor guide lines from the door to the platform and the console
    lamp_strip(b.emit, (10.0, 0.5, 0.006), (10.0, 5.4, 0.006), 0.04, 0.004, "science", LAMP_DIM)
    lamp_strip(b.emit, (10.0, 12.2, 0.006), (13.6, 12.2, 0.006), 0.04, 0.004, "guide", LAMP_DIM)
    # the walls and the ceiling are working surfaces too
    dress_wall(b, "far", L, D, H_, 17.6, 23.6, 1, accent="science", accent_dim="science_dim", kinds=("panelboard", "conduits", "vent"))
    dress_wall(b, "near", L, D, H_, 12.0, 23.5, 2, accent="science", accent_dim="science_dim", kinds=("plain", "vent", "safety", "screen"))
    dress_wall(b, "near", L, D, H_, 0.5, 8.0, 3, accent="science", accent_dim="science_dim", kinds=("plain", "panelboard", "vent", "hatch"))
    ceiling_services(b, L, D, H_, [(5.2, "duct"), (11.8, "pipes")], 1.0, 22.5, 4)
    ceiling_panels(b, L, D, H_, 3, 3, "white_cool", 1.8, 1.2, 0.6, LAMP_HOT)
    return b.build(name)
