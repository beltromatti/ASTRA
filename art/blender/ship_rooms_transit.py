"""ASN Aquila interior kit: the Spine shuttle's stops (NAVE-2, Deck 5; docs/BIBBIA.md §6: "the central corridor along the ship with the internal shuttle").

The shuttle runs along Deck 5 in a tunnel parallel to the Spine; at the middle of every section the line comes up into a platform hall that opens on the Spine by a door. A stop is
a lane room of the plan (the plan pins one per section, ship_decks.PINNED): 24 x 12 x 3.7, the platform along the Spine's side, the car standing at it with its doors open (14 m,
ship_craft.spine_car) on a track bed that disappears into a tunnel mouth in either end wall, a service ledge behind the car. The line itself (a car that moves, a `shuttle` edge in the
graph) is not modelled: a stop is a place to wait, to sit, to look at the route and to step into the car. Frame and sizes: ship_rooms.py / ship_spec.py."""
from __future__ import annotations

import ship_craft as CR
import ship_furniture as F
import ship_spec as SPEC
from ship_lib import (COMPOSITE, DECK, DGLASS, FABRIC_NAVY, IVORY, LAMP, LAMP_DIM, RUBBER, STEEL, STRUCT, TRIM, SParts)
from ship_rooms import (Style, WF, WS, build_shell, ceiling_services, dress_wall, luminaire_strips, place, wall_label)

TRACK_Y0, TRACK_Y1 = 6.10, 9.30                  # the track bed across the hall (the platform ends at 6.1)
CAR_X, CAR_Y = 12.0, 7.6                         # the car's middle: along the hall, across it
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
    for yy in (RAILS[0], RAILS[1]):                                   # the rails run on into the dark
        b.fine.box((min(xd0, xd1), yy - 0.035, 0.0), (max(xd0, xd1) + sx * 0.0, yy + 0.035, 0.026), TRIM)
    xs0, xs1 = x_face + sx * 0.14, x_face + sx * 0.152
    b.emit.lamp_box((min(xs0, xs1), yc - 0.12, h + 0.26), (max(xs0, xs1), yc + 0.12, h + 0.38), "red", LAMP_DIM)
    b.emit.lamp_box((min(xs0, xs1), yc - 0.12 - 0.34, h + 0.26), (max(xs0, xs1), yc + 0.12 - 0.34, h + 0.38), "green", LAMP_DIM)
    b.emit.label((x_face + sx * 0.142, yc, 0.9), 3.0, 0.12, (sx, 0, 0), "hazard_h", up=(0, 0, 1))


def shuttle_stop(name: str = "SM_SHIP_ShuttleStop"):
    """24 x 12 x 3.7: the platform hall of a stop of the Spine shuttle."""
    spec, L, D, H_ = _dims("shuttle_stop")
    b = SParts(bevel=0.005, fine_bevel=0.003)
    st = Style(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=COMPOSITE, wain_h=1.2, ceil=COMPOSITE, accent="cyan_dim", cove="white_cool", rib_mat=TRIM, skirt=STRUCT)
    build_shell(b, spec, st)
    yf = D - WS - WF
    xl, xr = WS + WF, L - WS - WF
    # the track: a dark bed, two rails, a guide line; the platform's edge (a tactile strip and the yellow line)
    b.soft.box((xl, TRACK_Y0, 0.0), (xr, TRACK_Y1, 0.007), RUBBER)
    for yy in RAILS:
        b.body.box((xl, yy - 0.035, 0.0), (xr, yy + 0.035, 0.026), TRIM)
    b.emit.lamp_box((xl + 0.1, CAR_Y - 0.02, 0.0), (xr - 0.1, CAR_Y + 0.02, 0.008), "cyan_dim", LAMP_DIM)
    b.soft.box((xl, 5.62, 0.0), (xr, TRACK_Y0, 0.012), STEEL)
    for xc in (3.2, 9.0, 14.8, 20.6):
        F.hazard_stripe(b, (xc, 5.88, 0.0125), 5.8, 0.20, (0, 0, 1), up=(0, 1, 0))
    # the tunnel mouths and what is round them
    tunnel_mouth(b, xl, +1)
    tunnel_mouth(b, xr, -1)
    dress_wall(b, "left", L, D, H_, 0.6, 5.5, 1, kinds=("plain", "panelboard"), accent="cyan", accent_dim="cyan_dim")
    dress_wall(b, "left", L, D, H_, 9.7, 11.5, 2, kinds=("plain", "vent"), accent="cyan", accent_dim="cyan_dim")
    dress_wall(b, "right", L, D, H_, 0.6, 5.5, 3, kinds=("plain", "panelboard"), accent="cyan", accent_dim="cyan_dim")
    dress_wall(b, "right", L, D, H_, 9.7, 11.5, 4, kinds=("plain", "vent"), accent="cyan", accent_dim="cyan_dim")
    # the service ledge behind the car: equipment bays on the far wall (the track's, power and signals), a big pictogram
    dress_wall(b, "far", L, D, H_, 1.0, 11.0, 5, kinds=("panelboard", "conduits", "plain", "vent", "safety"), accent="cyan", accent_dim="cyan_dim")
    dress_wall(b, "far", L, D, H_, 13.0, 23.0, 6, kinds=("panelboard", "plain", "vent", "conduits", "plain"), accent="cyan", accent_dim="cyan_dim")
    wall_label(b, 12.0, yf - 0.002, 2.55, (0, -1, 0), "pict_shuttle", 1.1)
    # the car, standing at the platform with its doors open
    place(b, CAR_X, CAR_Y, 0, CR.spine_car)
    # the platform: benches facing the line, the route boards, the sign over the door
    for xb in (5.5, 18.5):
        place(b, xb, 2.5, 90, F.bench, 2.4, 0.45, 0.46, FABRIC_NAVY)
    for xs in (4.2, 15.6):
        place(b, xs, WF + 0.06, 90, F.wall_screen, 1.5, 0.84, "scr_dir", z=1.75)
    place(b, 7.8, WF + 0.06, 90, F.wall_screen, 1.0, 0.56, "scr_sched", z=1.75)
    place(b, 18.4, WF + 0.06, 90, F.wall_screen, 1.0, 0.56, "scr_map", z=1.75)
    wall_label(b, 10.0, WF + 0.002, 2.95, (0, 1, 0), "room_shuttle_stop", 2.4)
    for xp in (3.0, 21.0):
        b.body.cyl((xp, 4.2, 0.0), (xp, 4.2, H_), 0.14, STRUCT, seg=14)                  # two columns on the platform
        b.fine.cyl((xp, 4.2, 0.0), (xp, 4.2, 0.12), 0.19, TRIM, seg=14)
        b.fine.cyl((xp, 4.2, H_ - 0.12), (xp, 4.2, H_), 0.19, TRIM, seg=14)
        b.emit.lamp_cyl((xp, 4.2, 1.20), (xp, 4.2, 1.26), 0.152, "cyan_dim", LAMP_DIM, seg=14)
    # ceiling: three lines of strips (over the platform, its edge and the car), services over the far side
    luminaire_strips(b, L, D, H_, [2.6, 5.9, 9.6], "white_cool", x0=1.4, x1=L - 1.4)
    ceiling_services(b, L, D, H_, [(11.2, "duct"), (7.6, "tray")], x0=1.6, x1=L - 1.6, seed=5)
    return b.build(name)
