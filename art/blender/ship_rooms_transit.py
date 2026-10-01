"""ASN Aquila interior kit: the Spine shuttle's stops (NAVE-2, Deck 5; docs/BIBBIA.md §6: "the central corridor along the ship with the internal shuttle"; NAVE-3 made the line real:
ship_design_shuttle.py).

The line runs the whole length of Deck 5 in a tunnel along the middle of the starboard outer lane (y = 30 in the ship's frame) and stops in eight halls, one for every section. A stop is a
lane room of the plan, 24 x 16 x 3.7, built against the Starboard Passage's wall: the platform (6.4 m deep, with its tactile strip and yellow line at the edge, benches, route boards, two
columns), the track bed behind it (the line's axis is y = 8 in the hall's frame: two rails, sleepers, a guide line) that disappears into a tunnel mouth in either end wall, and a service
ledge with the track's equipment bays on the far wall. The car is not part of the hall: it arrives and stops (ASCENSORI; the mesh SM_SHIP_SpineCar). The terminals (bow and stern) have one
mouth; the track ends in a pair of buffers against the closed wall. Frame and sizes: ship_rooms.py / ship_spec.py."""
from __future__ import annotations

import ship_furniture as F
import ship_spec as SPEC
from ship_lib import (COMPOSITE, DECK, DGLASS, FABRIC_NAVY, LAMP_DIM, PAINT_RED, RUBBER, STEEL, STRUCT, TRIM, SParts)
from ship_rooms import Style, WF, WS, build_shell, ceiling_services, dress_wall, luminaire_strips, place, wall_label

TRACK_Y0, TRACK_Y1 = 6.40, 9.60                  # the track bed across the hall (the platform ends at 6.4)
CAR_Y = 8.0                                      # the line's axis across the hall
RAILS = (CAR_Y - 0.65, CAR_Y + 0.65)


def _dims(key: str):
    s = SPEC.PREFABS[key]
    return s, s["L"], s["D"], s["h"]


def tunnel_mouth(b: SParts, x_face: float, sx: int, yc: float = CAR_Y, w: float = 3.5, h: float = 3.25) -> None:
    """A tunnel mouth on an end wall (sx = +1 on the left wall facing +x, -1 on the right wall): a dark opening in a heavy brushed frame with a signal lamp and a hazard stripe."""
    y0, y1 = yc - w / 2, yc + w / 2
    xa, xb = (x_face, x_face + sx * 0.14)
    lo, hi = min(xa, xb), max(xa, xb)
    b.body.box((lo, y0 - 0.18, 0.0), (hi, y0, h + 0.18), TRIM)
    b.body.box((lo, y1, 0.0), (hi, y1 + 0.18, h + 0.18), TRIM)
    b.body.box((lo, y0, h), (hi, y1, h + 0.18), TRIM)
    xd0, xd1 = (x_face, x_face + sx * 0.03)
    b.body.box((min(xd0, xd1), y0, 0.0), (max(xd0, xd1), y1, h), DGLASS)
    for yy in RAILS:                                                  # the rails run on into the dark
        b.fine.box((min(xd0, xd1), yy - 0.035, 0.0), (max(xd0, xd1), yy + 0.035, 0.026), TRIM)
    xs0, xs1 = x_face + sx * 0.14, x_face + sx * 0.152
    b.emit.lamp_box((min(xs0, xs1), yc - 0.12, h + 0.26), (max(xs0, xs1), yc + 0.12, h + 0.38), "red", LAMP_DIM)
    b.emit.lamp_box((min(xs0, xs1), yc - 0.12 - 0.34, h + 0.26), (max(xs0, xs1), yc + 0.12 - 0.34, h + 0.38), "green", LAMP_DIM)
    b.emit.label((x_face + sx * 0.142, yc, 0.9), 3.0, 0.12, (sx, 0, 0), "hazard_h", up=(0, 0, 1))


def buffers(b: SParts, x_face: float, sx: int) -> None:
    """The end of the line against a closed wall: a pair of hydraulic buffers on a stout frame and a red board (sx = +1 for a wall at the hall's aft end, -1 for its forward one)."""
    for y in RAILS:
        b.body.box((x_face, y - 0.2, 0.1), (x_face + sx * 0.12, y + 0.2, 0.75), STRUCT)
        b.fine.cyl((x_face + sx * 0.12, y, 0.45), (x_face + sx * 0.8, y, 0.45), 0.09, TRIM, seg=12)
        b.fine.cyl((x_face + sx * 0.8, y, 0.45), (x_face + sx * 0.95, y, 0.45), 0.14, PAINT_RED, seg=12)
    b.emit.label((x_face + sx * 0.003, CAR_Y, 2.4), 1.2, 0.3, (sx, 0, 0), "hazard")
    b.emit.lamp_box((x_face + sx * 0.003, CAR_Y - 0.1, 2.9), (x_face + sx * 0.02, CAR_Y + 0.1, 3.1), "red", LAMP_DIM)


def _stop(name: str, key: str):
    spec, L, D, H_ = _dims(key)
    mouth_aft, mouth_fwd = spec["mouths"]
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent="cyan_dim", cove="white_cool", rib_mat=TRIM, skirt=STRUCT)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    # the track: a dark bed, two rails on sleepers, a guide line; the platform's edge: a tactile strip, a yellow line, hazard stripes
    b.soft.box((xl, TRACK_Y0, 0.0), (xr, TRACK_Y1, 0.007), RUBBER)
    for yy in RAILS:
        b.body.box((xl, yy - 0.035, 0.0), (xr, yy + 0.035, 0.026), TRIM)
    for xs in [xl + 0.4 + 0.8 * k for k in range(int((xr - xl - 0.8) / 0.8) + 1)]:
        b.fine.box((xs - 0.11, TRACK_Y0 + 0.2, 0.0), (xs + 0.11, TRACK_Y1 - 0.2, 0.012), STRUCT)
    b.emit.lamp_box((xl + 0.1, CAR_Y - 0.02, 0.0), (xr - 0.1, CAR_Y + 0.02, 0.008), "cyan_dim", LAMP_DIM)
    b.soft.box((xl, TRACK_Y0 - 0.5, 0.0), (xr, TRACK_Y0, 0.012), STEEL)
    for xc in (3.2, 9.0, 14.8, 20.6):
        F.hazard_stripe(b, (xc, TRACK_Y0 - 0.45, 0.0125), 5.8, 0.20, (0, 0, 1), up=(0, 1, 0))
    # the tunnel mouths in the end walls (the terminals' closed end has the buffers instead)
    for (is_open, x_face, sx) in ((mouth_aft, xl, +1), (mouth_fwd, xr, -1)):
        if is_open:
            tunnel_mouth(b, x_face, sx)
        else:
            buffers(b, x_face, sx)
    dress_wall(b, "left", L, D, H_, 0.6, 5.5, 1, kinds=("plain", "panelboard"), accent="cyan", accent_dim="cyan_dim")
    dress_wall(b, "left", L, D, H_, 9.8, 15.5, 2, kinds=("plain", "vent"), accent="cyan", accent_dim="cyan_dim")
    dress_wall(b, "right", L, D, H_, 0.6, 5.5, 3, kinds=("plain", "panelboard"), accent="cyan", accent_dim="cyan_dim")
    dress_wall(b, "right", L, D, H_, 9.8, 15.5, 4, kinds=("plain", "vent"), accent="cyan", accent_dim="cyan_dim")
    # the far wall: the track's equipment bays, a big pictogram
    dress_wall(b, "far", L, D, H_, 1.0, 11.0, 5, kinds=("panelboard", "conduits", "plain", "vent", "safety"), accent="cyan", accent_dim="cyan_dim")
    dress_wall(b, "far", L, D, H_, 13.0, 23.0, 6, kinds=("panelboard", "plain", "vent", "conduits", "plain"), accent="cyan", accent_dim="cyan_dim")
    wall_label(b, 12.0, yf - 0.002, 2.55, (0, -1, 0), "pict_shuttle", 1.1)
    # the platform: benches facing the line, the route boards and the sign on the corridor wall, columns
    for xb in (4.4, 14.0):
        place(b, xb, 4.6, -90, F.bench, 2.4, 0.45, 0.46, FABRIC_NAVY)
    for xs, tile in ((5.4, "scr_dir"), (13.4, "scr_sched"), (21.4, "scr_map")):
        place(b, xs, WF + 0.06, 90, F.wall_screen, 1.4, 0.8, tile, z=1.75)
    for xp in (3.0, 21.0):
        b.body.cyl((xp, 5.4, 0.0), (xp, 5.4, H_), 0.14, STRUCT, seg=14)                  # two columns on the platform
        b.fine.cyl((xp, 5.4, 0.0), (xp, 5.4, 0.12), 0.19, TRIM, seg=14)
        b.fine.cyl((xp, 5.4, H_ - 0.12), (xp, 5.4, H_), 0.19, TRIM, seg=14)
        b.emit.lamp_cyl((xp, 5.4, 1.20), (xp, 5.4, 1.26), 0.152, "cyan_dim", LAMP_DIM, seg=14)
    luminaire_strips(b, L, D, H_, [2.6, 5.9, 8.0, 13.5], "white_cool", x0=1.4, x1=L - 1.4)
    ceiling_services(b, L, D, H_, [(11.2, "duct"), (7.2, "tray")], x0=1.6, x1=L - 1.6, seed=5)
    return b.build(name)


def shuttle_stop(name: str = "SM_SHIP_ShuttleStop"):
    """24 x 16 x 3.7: a through stop of the line, a mouth in each end wall."""
    return _stop(name, "shuttle_stop")


def shuttle_stop_bow(name: str = "SM_SHIP_ShuttleStopBow"):
    """The bow terminal: the tunnel enters at the aft end only; the track ends in buffers against the forward wall."""
    return _stop(name, "shuttle_stop_bow")


def shuttle_stop_stern(name: str = "SM_SHIP_ShuttleStopStern"):
    """The stern terminal: the tunnel enters at the forward end only; the track ends in buffers against the aft wall."""
    return _stop(name, "shuttle_stop_stern")
