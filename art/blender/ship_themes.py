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

from ship_lib import (CARPET_MOSS, CARPET_RUST, CARPET_SAND, CARPET_SLATE, COMPOSITE, DECK, IVORY, OAK, PERF, PLASTER_IVORY, PLASTER_SAGE, PLASTER_SLATE, PLASTER_TEAL, PLATING, RUBBER, STEEL,
                      STRUCT, TEAK, TERRAZZO, TILE_FLOOR, TILE_HEX, TILE_WALL, TRIM, TREAD, WALNUT, WEAVE_SAND, WEAVE_SLATE, WEAVE_TEAL, WHITE_GLOSS)
from ship_rooms import Style


def living(**kw) -> Style:
    d = dict(floor=CARPET_SLATE, floor_mode="covering", floor2=CARPET_SAND, border=0.5, inlay="warm_dim", wall_lo=WALNUT, wall_hi=PLASTER_IVORY, wall_acc=OAK, wain_h=0.95,
             wall_pattern=("panel", "cloth", "panel", "slats"), bay=2.4, ceil=IVORY, accent="warm_dim", strip="white_warm", light_cell="white_warm", rib_mat=TRIM, skirt=WALNUT,
             seams=False, ceiling="cove", trim=TRIM)
    d.update(kw)
    return Style(**d)


def mess(**kw) -> Style:
    d = dict(floor=TERRAZZO, floor_mode="covering", floor2=CARPET_SLATE, border=0.0, wall_lo=WALNUT, wall_hi=PLASTER_IVORY, wall_acc=OAK, wain_h=1.05, wall_pattern=("panel", "panel", "slats", "panel"),
             bay=2.0, ceil=IVORY, accent="warm_dim", strip="white_warm", light_cell="white_warm", skirt=STEEL, seams=False, ceiling="bands")
    d.update(kw)
    return Style(**d)


def crew(**kw) -> Style:
    d = dict(floor=CARPET_SLATE, floor_mode="covering", floor2=CARPET_SAND, border=0.0, wall_lo=PLASTER_SLATE, wall_hi=PLASTER_IVORY, wall_acc=WEAVE_SLATE, wain_h=1.0,
             wall_pattern=("panel", "cloth", "panel"), bay=2.0, ceil=IVORY, accent="cyan_dim", strip="white_warm", light_cell="white_warm", skirt=STEEL, seams=False, ceiling="bands")
    d.update(kw)
    return Style(**d)


def medical(**kw) -> Style:
    d = dict(floor=TILE_FLOOR, floor_mode="covering", floor2=TILE_HEX, border=0.0, wall_lo=TILE_WALL, wall_hi=PLASTER_IVORY, wall_acc=PLASTER_TEAL, wain_h=1.25,
             wall_pattern=("panel", "panel", "cloth"), bay=2.0, ceil=IVORY, accent="medical_dim", strip="white_cool", light_cell="white_cool", skirt=STEEL, seams=False, ceiling="grid",
             trim=STEEL, rib_mat=STEEL)
    d.update(kw)
    return Style(**d)


def lab(**kw) -> Style:
    d = dict(floor=TILE_FLOOR, floor_mode="covering", wall_lo=PLASTER_SLATE, wall_hi=PLASTER_IVORY, wall_acc=PERF, wain_h=1.1, wall_pattern=("panel", "perf", "panel"), bay=2.0,
             ceil=IVORY, accent="science_dim", strip="white_cool", light_cell="white_cool", skirt=STEEL, seams=False, ceiling="grid")
    d.update(kw)
    return Style(**d)


def command(**kw) -> Style:
    d = dict(floor=CARPET_SLATE, floor_mode="covering", wall_lo=PLASTER_SLATE, wall_hi=PLASTER_SLATE, wall_acc=WEAVE_SLATE, wain_h=1.05, wall_pattern=("panel", "cloth", "panel", "perf"),
             bay=2.0, ceil=COMPOSITE, accent="command_dim", strip="white_cool", light_cell="white_cool", skirt=STRUCT, seams=False, ceiling="bands")
    d.update(kw)
    return Style(**d)


def security(**kw) -> Style:
    d = dict(floor=PLATING, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=PLASTER_SLATE, wall_acc=PERF, wain_h=1.1, wall_pattern=("panel", "perf", "panel"), bay=2.0, ceil=COMPOSITE,
             accent="security_dim", strip="white_cool", light_cell="white_cool", skirt=STRUCT, ceiling="bands")
    d.update(kw)
    return Style(**d)


def flight(**kw) -> Style:
    d = dict(floor=PLATING, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=PLASTER_SLATE, wall_acc=PERF, wain_h=1.1, wall_pattern=("panel", "perf", "panel"), bay=2.0, ceil=COMPOSITE,
             accent="flight_dim", strip="white_cool", light_cell="white_cool", skirt=STRUCT, ceiling="bands")
    d.update(kw)
    return Style(**d)


def tech(**kw) -> Style:
    d = dict(floor=TREAD, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=PLASTER_SLATE, wall_acc=PERF, wain_h=1.2, wall_pattern=("panel", "panel", "perf"), bay=2.0, ceil=COMPOSITE,
             accent="engineering_dim", strip="white_cool", light_cell="white_cool", skirt=STRUCT, ceiling="exposed", rib_mat=TRIM)
    d.update(kw)
    return Style(**d)


def store(**kw) -> Style:
    d = dict(floor=DECK, floor_mode="plates", wall_lo=COMPOSITE, wall_hi=PLASTER_SLATE, wall_acc=PERF, wain_h=1.2, wall_pattern=("panel",), bay=3.0, ceil=COMPOSITE,
             accent="amber_dim", strip="white_cool", light_cell="white_cool", skirt=STRUCT, ceiling="exposed")
    d.update(kw)
    return Style(**d)
