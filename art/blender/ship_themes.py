"""ASN Aquila interior kit (ARTE-INTERNI): the looks of the ship's rooms, by what a room is for. Each theme returns a ship_rooms.Style (floor, walls, ceiling, light colour); a room takes one
and overrides what it needs (`living(floor=CARPET_MOSS)`). The ship's rooms are not all the same room: the crew's own spaces are warm and soft (wool carpet, wood, plaster, a cove of light),
the work spaces are cool and hard (tread plate, brushed metal, bands of white light), the medical rooms are white and teal, command is deep blue-grey with blue light, the machinery is
gunmetal with amber (docs/STILE.md §3: the department colours are the accent: Command blue, Engineering amber, Medical teal, Security red, Flight yellow, Science violet).

  living    wardroom, lounge, library, officers' quarters, the bar: carpet or teak, plaster and wood, a cove, warm 3200 K
  mess      mess hall, concourse, galley seating: terrazzo or rubber floor, pale walls, long bands, neutral-warm 3800 K
  crew      berthing, cabins, gym, heads, laundry: pale blue-grey, light carpet or rubber, soft neutral light, blue accents
  medical   medbay, surgery, ward, pharmacy: white tile and plaster, teal accent, cool 5200 K
  lab       science rooms: pale, glossy, violet accent
  command   CIC, briefing, comms, bridge-adjacent: slate plaster, dark carpet, blue accent
  security  armory, brig, barracks, range: gunmetal, red accent
  flight    flight ops, ready rooms, hangars: grey, yellow accent
  tech      machinery, power, workshops: tread plate, gunmetal, amber accent, exposed ceiling
  store     stores, cargo, utility: deck plate, grey, cool light
"""
from __future__ import annotations

from ship_lib import (RUBBER as _RUBBER_FLOOR, CARPET_MOSS, CARPET_RUST, CARPET_SAND, CARPET_SLATE, COMPOSITE, DECK, IVORY, OAK, PERF, PLASTER_IVORY, PLASTER_SAGE, PLASTER_SLATE, PLASTER_TEAL, PLATING, RUBBER, STEEL,
                      STRUCT, TEAK, TERRAZZO, TILE_FLOOR, TILE_HEX, TILE_WALL, TRIM, TREAD, WALNUT, WEAVE_SAND, WEAVE_SLATE, WEAVE_TEAL, WHITE_GLOSS)
from ship_rooms import Style


def _themed(st: Style) -> Style:
    st.themed = True
    return st


def living(**kw) -> Style:
    d = dict(floor=CARPET_SLATE, floor_mode="covering", floor2=CARPET_SAND, border=0.5, inlay="warm_dim", wall_lo=WALNUT, wall_hi=PLASTER_IVORY, wall_acc=OAK, wain_h=0.95,
             wall_pattern=("panel", "cloth", "panel", "slats"), bay=2.4, ceil=PLASTER_IVORY, accent="warm_dim", strip="white_warm", light_cell="white_warm", rib_mat=TRIM, skirt=WALNUT,
             seams=False, ceiling="cove", trim=TRIM)
    d.update(kw)
    return _themed(Style(**d))


def mess(**kw) -> Style:
    d = dict(floor=TERRAZZO, floor_mode="covering", floor2=CARPET_SLATE, border=0.0, wall_lo=WALNUT, wall_hi=PLASTER_IVORY, wall_acc=OAK, wain_h=1.05, wall_pattern=("panel", "panel", "slats", "panel"),
             bay=2.0, ceil=PLASTER_IVORY, accent="warm_dim", strip="white_warm", light_cell="white_warm", skirt=STEEL, seams=False, ceiling="bands")
    d.update(kw)
    return _themed(Style(**d))


def crew(**kw) -> Style:
    d = dict(baseboard_light=True, floor=CARPET_SLATE, floor_mode="covering", floor2=CARPET_SAND, border=0.0, wall_lo=PLASTER_SLATE, wall_hi=PLASTER_IVORY, wall_acc=WEAVE_SLATE, wain_h=1.0,
             wall_pattern=("panel", "cloth", "panel"), bay=2.0, ceil=PLASTER_IVORY, accent="cyan_dim", strip="white_warm", light_cell="white_warm", skirt=STEEL, seams=False, ceiling="bands")
    d.update(kw)
    return _themed(Style(**d))


def medical(**kw) -> Style:
    d = dict(baseboard_light=True, floor=TILE_FLOOR, floor_mode="covering", floor2=TILE_HEX, border=0.0, wall_lo=TILE_WALL, wall_hi=PLASTER_IVORY, wall_acc=PLASTER_TEAL, wain_h=1.25,
             wall_pattern=("panel", "panel", "cloth"), bay=2.0, ceil=PLASTER_IVORY, accent="medical_dim", strip="white_cool", light_cell="white_cool", skirt=STEEL, seams=False, ceiling="grid",
             trim=STEEL, rib_mat=STEEL)
    d.update(kw)
    return _themed(Style(**d))


def lab(**kw) -> Style:
    d = dict(baseboard_light=True, floor=TILE_FLOOR, floor_mode="covering", wall_lo=PLASTER_SLATE, wall_hi=PLASTER_IVORY, wall_acc=PERF, wain_h=1.1, wall_pattern=("panel", "perf", "panel"), bay=2.0,
             ceil=PLASTER_IVORY, accent="science_dim", strip="white_cool", light_cell="white_cool", skirt=STEEL, seams=False, ceiling="grid")
    d.update(kw)
    return _themed(Style(**d))


def command(**kw) -> Style:
    d = dict(baseboard_light=True, floor=CARPET_SLATE, floor_mode="covering", wall_lo=PLASTER_SLATE, wall_hi=PLASTER_SLATE, wall_acc=WEAVE_SLATE, wain_h=1.05, wall_pattern=("panel", "cloth", "panel", "perf"),
             bay=2.0, ceil=COMPOSITE, accent="command_dim", strip="white_cool", light_cell="white_cool", skirt=STRUCT, seams=False, ceiling="bands")
    d.update(kw)
    return _themed(Style(**d))


def security(**kw) -> Style:
    d = dict(baseboard_light=True, floor=PLATING, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=PLASTER_SLATE, wall_acc=PERF, wain_h=1.1, wall_pattern=("panel", "perf", "panel"), bay=2.0, ceil=COMPOSITE,
             accent="security_dim", strip="white_cool", light_cell="white_cool", skirt=STRUCT, ceiling="bands")
    d.update(kw)
    return _themed(Style(**d))


def flight(**kw) -> Style:
    d = dict(baseboard_light=True, floor=PLATING, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=PLASTER_SLATE, wall_acc=PERF, wain_h=1.1, wall_pattern=("panel", "perf", "panel"), bay=2.0, ceil=COMPOSITE,
             accent="flight_dim", strip="white_cool", light_cell="white_cool", skirt=STRUCT, ceiling="bands")
    d.update(kw)
    return _themed(Style(**d))


def tech(**kw) -> Style:
    d = dict(baseboard_light=True, floor=TREAD, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=PLASTER_SLATE, wall_acc=PERF, wain_h=1.2, wall_pattern=("panel", "panel", "perf"), bay=2.0, ceil=COMPOSITE,
             accent="engineering_dim", strip="white_cool", light_cell="white_cool", skirt=STRUCT, ceiling="exposed", rib_mat=TRIM)
    d.update(kw)
    return _themed(Style(**d))


def store(**kw) -> Style:
    d = dict(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=PLASTER_SLATE, wall_acc=PERF, wain_h=1.2, wall_pattern=("panel",), bay=3.0, ceil=COMPOSITE,
             accent="amber_dim", strip="white_cool", light_cell="white_cool", skirt=STRUCT, ceiling="exposed")
    d.update(kw)
    return _themed(Style(**d))


def galley(**kw) -> Style:
    d = dict(baseboard_light=True, floor=TILE_FLOOR, floor_mode="covering", wall_lo=TILE_WALL, wall_hi=PLASTER_IVORY, wall_acc=PERF, wain_h=1.9, wall_pattern=("panel", "panel", "perf"), bay=2.0, ceil=IVORY,
             accent="warm_dim", strip="white_warm", light_cell="white_warm", skirt=STEEL, seams=False, ceiling="grid", trim=STEEL, rib_mat=STEEL)
    d.update(kw)
    return _themed(Style(**d))


def wet(**kw) -> Style:
    """Heads, showers, laundry: tile everywhere."""
    d = dict(floor=TILE_FLOOR, floor_mode="covering", wall_lo=TILE_WALL, wall_hi=TILE_WALL, wall_acc=PERF, wain_h=2.4, wall_pattern=("panel",), bay=3.0, ceil=PLASTER_IVORY, accent="cyan_dim",
             strip="white_cool", light_cell="white_cool", skirt=STEEL, seams=False, ceiling="grid", trim=STEEL, rib_mat=STEEL, wall_wash=False)
    d.update(kw)
    return _themed(Style(**d))


# ---------------------------------------------------------------------------------------------------------------------- by room
# prefab key -> (theme, overrides). A room that chooses its own theme in its function (a Style made by one of the functions above) keeps it; every other room gets the theme of
# this table when build_shell sees it (resolve): one place to tune the look of the whole ship by what a room is for.
THEME_TABLE: dict[str, tuple] = {
    # crew services (Deck 4 and the quarters)
    "bar": ("living", dict(accent="amber_dim", wall_lo=WALNUT, floor=TEAK, floor2=CARPET_SLATE, border=0.0, ceiling="cove")),
    "games": ("living", dict(wall_lo=PLASTER_SLATE, wall_hi=PLASTER_SLATE, accent="violet", floor=CARPET_SLATE, floor2=CARPET_RUST, wall_pattern=("panel", "perf", "panel"))),
    "library": ("living", dict(wall_pattern=("slats", "panel", "cloth", "slats"))),
    "quiet": ("living", dict(floor=CARPET_SAND, floor2=CARPET_SLATE, wall_hi=PLASTER_IVORY, accent="warm_dim", ceiling="cove", wall_pattern=("cloth", "panel"))),
    "chapel": ("living", dict(floor=TEAK, floor2=CARPET_SLATE, border=0.0, wall_lo=PLASTER_IVORY, wall_hi=PLASTER_IVORY, accent="warm_dim", wall_pattern=("panel", "cloth"), ceiling="cove")),
    "observation": ("living", dict(floor=CARPET_SLATE, floor2=CARPET_SLATE, border=0.0, wall_hi=PLASTER_SLATE, wall_lo=PLASTER_SLATE, accent="cool_dim", strip="white_cool", light_cell="white_cool",
                                   ceiling="flat")),
    "concourse": ("mess", dict(ceiling="flat", accent="warm_dim", wall_pattern=("panel", "slats", "panel"))),
    "berth_lobby": ("living", dict(ceiling="flat", floor=CARPET_SLATE, floor2=CARPET_SAND, border=0.0)),
    "bow_obs": ("living", dict(floor=CARPET_SLATE, floor2=CARPET_SLATE, border=0.0, wall_hi=PLASTER_SLATE, wall_lo=PLASTER_SLATE, accent="cool_dim", strip="white_cool", light_cell="white_cool",
                               ceiling="flat")),
    "shop": ("mess", dict(accent="warm_dim")),
    "barber": ("mess", dict(floor=TILE_FLOOR, accent="warm_dim")),
    "wardroom": ("living", dict(floor=TEAK, floor2=CARPET_SLATE, border=0.0, accent="warm_dim", wall_pattern=("panel", "slats", "cloth", "panel"))),
    "staterooms": ("living", dict(wall_pattern=("panel", "cloth"), floor=CARPET_SAND, floor2=CARPET_SLATE)),
    "suites": ("living", dict(wall_pattern=("panel", "cloth"), floor=CARPET_SAND, floor2=CARPET_SLATE)),
    "single_cabins": ("living", dict(wall_pattern=("panel", "cloth"), floor=CARPET_SAND, floor2=CARPET_SLATE, border=0.0, ceiling="grid")),
    "cabins": ("crew", dict(floor=CARPET_SAND, floor2=CARPET_SLATE)),
    "berthing": ("crew", dict()),
    "barracks": ("crew", dict(accent="security_dim", floor=CARPET_SLATE, wall_lo=PLASTER_SLATE)),
    "gym": ("crew", dict(floor=_RUBBER_FLOOR, floor2=None, wall_lo=PLASTER_SLATE, accent="amber_dim", strip="white_cool", light_cell="white_cool", wall_pattern=("panel", "mirror", "panel"))),
    "heads": ("wet", dict()),
    "laundry": ("wet", dict(floor=TILE_FLOOR)),
    "galley": ("galley", dict()),
    "galley_pass": ("galley", dict()),
    "hydro": ("lab", dict()),
    "garden": ("living", dict()),
    # stores
    "store_dry": ("store", dict()), "store_cold": ("store", dict(accent="cyan_dim", wall_hi=PLASTER_SLATE)), "hold": ("store", dict()), "cargo_hold": ("store", dict()),
    "store_s": ("store", dict()), "locker_s": ("store", dict()), "tech_s": ("tech", dict()),
    # science and medical
    "lab": ("lab", dict()), "lab_bio": ("lab", dict(wall_lo=PLASTER_SAGE, accent="green_dim")), "lab_phys": ("lab", dict()),
    "lab_astro": ("command", dict(accent="science_dim", wall_hi=PLASTER_SLATE, ceiling="flat", light_cell="cool_dim")),
    "sensor_room": ("lab", dict(wall_lo=PLASTER_SLATE)), "sensor_archive": ("lab", dict(wall_lo=PLASTER_SLATE)), "computer_core": ("tech", dict(accent="science_dim", floor=PLATING)),
    "transporter": ("lab", dict(wall_lo=PLASTER_SLATE, accent="science_dim", floor=PLATING, floor_mode="plates")),
    "surgery": ("medical", dict()), "quarantine": ("medical", dict(accent="red_dim")), "pharmacy": ("medical", dict()), "dentist": ("medical", dict()),
    "morgue": ("medical", dict(accent="cool_dim", wall_lo=TILE_WALL)), "counselling": ("living", dict(floor=CARPET_SAND, floor2=CARPET_SLATE, accent="medical_dim", wall_pattern=("panel", "cloth"))),
    # command
    "cic": ("command", dict()), "briefing": ("command", dict()), "comms_center": ("command", dict()), "offices": ("command", dict(floor=CARPET_SLATE, wall_hi=PLASTER_IVORY, ceiling="grid")),
    "records": ("command", dict(wall_hi=PLASTER_IVORY, ceiling="grid")), "point_defense": ("security", dict(accent="command_dim")), "barbette": ("security", dict()),
    "vls_magazine": ("security", dict()),
    # security and marines
    "armory": ("security", dict()), "kit_room": ("security", dict()), "firing_range": ("security", dict(ceiling="exposed")), "brig": ("security", dict()),
    "security_office": ("command", dict(accent="security_dim", floor=CARPET_SLATE)), "shuttle_bay": ("flight", dict(ceiling="exposed")), "magazine": ("security", dict(ceiling="exposed")),
    # flight
    "flight_ops": ("flight", dict(floor=CARPET_SLATE, floor_mode="covering", wall_hi=PLASTER_SLATE)), "pilot_ready": ("flight", dict(floor=CARPET_SLATE, floor_mode="covering")),
    "aircraft_shop": ("tech", dict(accent="flight_dim")), "drone_bay": ("tech", dict(accent="flight_dim")), "sim_bay": ("flight", dict(accent="cyan_dim")),
    # engineering and the hull
    "workshop": ("tech", dict()), "fab_shop": ("tech", dict(floor=PLATING)), "repair_bay": ("tech", dict()), "machinery": ("tech", dict()), "machinery_b": ("tech", dict()),
    "radiator_pumps": ("tech", dict()), "power_control": ("tech", dict(floor=PLATING, ceiling="bands")), "switchgear": ("tech", dict()), "capacitors": ("tech", dict()),
    "air_plant": ("tech", dict(accent="cyan_dim")), "water_plant": ("tech", dict(accent="cyan_dim")), "waste_plant": ("tech", dict(accent="amber_dim")),
    "aux_reactor": ("tech", dict()), "dc_central": ("tech", dict(accent="red_dim", ceiling="bands")), "dc_station": ("tech", dict(accent="red_dim", ceiling="bands")),
    "airlock": ("tech", dict(accent="cyan_dim", ceiling="flat")), "pod_bay": ("tech", dict(accent="amber_dim", ceiling="flat")), "suit_locker": ("tech", dict(ceiling="flat")),
    "tank": ("store", dict()), "reaction_mass": ("store", dict()), "crawlway": ("tech", dict(ceiling="flat")),
    "shuttle_stop": ("tech", dict(accent="white_dim", ceiling="bands", floor=TERRAZZO, floor_mode="covering")),
}
THEME_DEFAULT = ("store", dict())
V2_EXCLUDE = {"ready_room", "lift_bank", "lift_bank_o", "lift_bank_b", "lift_housing_bridge", "stair_tower"}   # not this module's: Deck 1 (ARTE-PLANCIA-2), the lifts and the stairs (engine)


def resolve(st: Style, spec: dict) -> Style:
    """The style a room gets: its own if it chose one of the themes above (st.themed), the table's for its prefab otherwise; the excluded rooms keep the older shell."""
    key = spec.get("key", "")
    if key in V2_EXCLUDE:
        st.v2 = False
        return st
    if getattr(st, "themed", False):
        return st
    name, over = THEME_TABLE.get(key.replace("shuttle_stop_bow", "shuttle_stop").replace("shuttle_stop_stern", "shuttle_stop"), THEME_DEFAULT)
    return globals()[name](**over)
