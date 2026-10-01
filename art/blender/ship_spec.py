"""ASN Aquila interior kit (NAVE): the specification of the room prefabs, in pure Python: sizes, doors, the crew's spots and the
zone lights of every prefab, in the prefab's local frame. The Blender builders (ship_rooms.py) place their furniture from these
numbers and the plan generator (ship_plan_gen.py) transforms them to the world, so a room and its plan never disagree.

Local frame of a prefab: origin on the floor at the corridor-side corner of the room, x along the corridor (0..L), y INTO the
room (0..D, away from the corridor wall's outer face), z up. `near` = the wall on the corridor (y = 0); `far` = y = D; `left` = the
wall at x = 0, `right` = x = L. Doors are 1.6 x 2.4 unless said otherwise, and sit on a module centre of the corridor, so the door's
x along the wall is 2 mod 4.

A spot is a place where a person stands, sits or works: role (who), kind (stand / sit / work / sleep / eat / watch), local x, y,
yaw in degrees (0 faces +x, 90 faces +y: into the room), and `dept` of the uniform. The crew of F3/F4 uses them to be somewhere.
"""
from __future__ import annotations

from ship_catalog import DOOR_H, DOOR_W

# ---------------------------------------------------------------------------------------------------------------- helpers


def door(wall: str, x: float, w: float = DOOR_W, h: float = DOOR_H) -> dict:
    return {"wall": wall, "x": x, "w": w, "h": h}


def spot(role: str, kind: str, x: float, y: float, yaw: float, dept: str = "services", dz: float = 0.0) -> dict:
    """`dz`: how far above the room's floor the person stands (a pad on a dais, a gantry): the station's z is the floor's plus this."""
    d = {"role": role, "kind": kind, "x": x, "y": y, "yaw": yaw, "dept": dept}
    if dz:
        d["dz"] = dz
    return d


def light(x: float, y: float, z: float, lm: float, temp: float = 4500.0, size=(4.0, 1.0), radius: float = 900.0, shadows: bool = False,
          kind: str = "rect") -> dict:
    return {"type": kind, "pos": [x, y, z], "lumens": lm, "temperature": temp, "size": list(size), "radius": radius, "shadows": shadows}


def grid_lights(L: float, D: float, h: float, nx: int, ny: int, lm: float, temp: float, size=(3.0, 1.0), radius: float = 900.0):
    out = []
    for i in range(nx):
        for j in range(ny):
            out.append(light((i + 0.5) * L / nx, (j + 0.5) * D / ny, h - 0.1, lm, temp, size, radius))
    return out


# ------------------------------------------------------------------------------------------------------------ the prefabs
PREFABS: dict[str, dict] = {}


def _reg(key: str, **kw) -> None:
    kw.setdefault("key", key)
    kw.setdefault("mesh", "SM_SHIP_" + key.title().replace("_", ""))
    PREFABS[key] = kw


# ---- Deck 4: crew services --------------------------------------------------------------------------------------------
_reg("galley", name="Main Galley", kind="galley", dept="services", L=24.0, D=16.0, h=3.6, plate="galley",
     doors=[door("near", 10.0)], systems=["food_service", "potable_water", "power_bus"],
     spots=[spot("cook", "work", 8.0, 14.3, 90), spot("cook", "work", 10.5, 14.3, 90), spot("cook", "work", 12.5, 14.3, 90),
            spot("cook", "work", 14.0, 14.3, 90), spot("steward", "work", 8.0, 8.1, -90), spot("steward", "work", 13.5, 8.1, -90),
            spot("dishwasher", "work", 21.9, 9.9, 0), spot("chief_cook", "stand", 13.4, 3.2, 180)],
     lights=[light(8.0, 6.0, 3.5, 7000, 5000, (7.0, 0.9)), light(17.0, 6.0, 3.5, 7000, 5000, (7.0, 0.9)),
             light(12.0, 12.5, 3.5, 9000, 4800, (16.0, 0.9)), light(3.0, 9.0, 3.5, 3000, 4200, (2.0, 8.0))])
_reg("galley_pass", name="Galley Pass", kind="galley", dept="services", L=24.0, D=4.0, h=3.4, plate="galley",
     doors=[door("near", 10.0)], systems=["food_service", "dumbwaiter"],
     spots=[spot("steward", "work", 8.0, 2.0, 90), spot("steward", "work", 14.0, 2.0, 90)],
     lights=[light(12.0, 2.0, 3.3, 3500, 4800, (14.0, 0.5))])
_reg("lounge", name="Crew Lounge", kind="lounge", dept="services", L=24.0, D=16.0, h=3.6, plate="lounge",
     doors=[door("near", 10.0), door("far", 14.0)], systems=["power_bus", "entertainment"],
     spots=[spot("crew", "sit", 4.0, 4.0, 45), spot("crew", "sit", 4.0, 6.6, -45), spot("crew", "sit", 7.7, 4.6, 180), spot("crew", "sit", 7.7, 6.0, 180),
            spot("crew", "sit", 4.0, 11.4, 45), spot("crew", "sit", 4.0, 14.0, -45), spot("crew", "sit", 7.7, 12.0, 180), spot("crew", "sit", 7.7, 13.4, 180),
            spot("crew", "eat", 15.4, 4.3, 90), spot("crew", "eat", 15.4, 6.5, -90), spot("crew", "eat", 19.6, 4.3, 90), spot("crew", "eat", 20.7, 5.4, 180)]
           + [spot("crew", "eat", 16.4 + 1.3 * i, 11.5, 90) for i in (0, 2, 4)] + [spot("barista", "work", 19.0, 13.6, -90)],
     lights=[light(6.0, 8.0, 3.5, 5200, 3200, (8.0, 8.0)), light(18.0, 5.0, 3.5, 4200, 3400, (8.0, 3.0)),
             light(18.0, 12.0, 3.5, 4200, 3400, (8.0, 3.0))])
_reg("games", name="Games Room", kind="lounge", dept="services", L=24.0, D=16.0, h=3.6, plate="games",
     doors=[door("near", 10.0), door("far", 14.0)], systems=["power_bus", "entertainment"],
     spots=[spot("crew", "sit", 5.0, 5.0, 0), spot("crew", "sit", 7.0, 5.0, 180), spot("crew", "sit", 5.0, 11.0, 0), spot("crew", "sit", 7.0, 11.0, 180),
            spot("crew", "sit", 12.0, 4.0, 0), spot("crew", "sit", 14.0, 4.0, 180), spot("crew", "stand", 17.5, 14.1, 90),
            spot("crew", "stand", 19.5, 14.1, 90), spot("crew", "stand", 15.0, 8.0, 0), spot("crew", "stand", 19.0, 8.0, 180)],
     lights=[light(6.0, 8.0, 3.5, 4500, 4000, (8.0, 8.0)), light(18.0, 8.0, 3.5, 4500, 3600, (8.0, 8.0))])
_reg("library", name="Library", kind="library", dept="services", L=16.0, D=16.0, h=3.6, plate="library",
     doors=[door("near", 6.0)], systems=["power_bus"],
     spots=[spot("crew", "sit", 5.0, 8.0, 90), spot("crew", "sit", 8.0, 8.0, 90), spot("crew", "sit", 5.0, 10.0, -90), spot("crew", "sit", 11.6, 5.4, 180),
            spot("crew", "sit", 2.6, 4.6, 0), spot("librarian", "work", 13.15, 3.0, 0)],
     lights=[light(8.0, 8.0, 3.5, 4500, 3300, (8.0, 8.0))])
_reg("observation", name="Observation Deck", kind="observation", dept="command", L=24.0, D=16.0, h=3.7, plate="observation",
     doors=[door("near", 10.0)], systems=["power_bus"],
     spots=[spot("crew", "watch", x, 14.0, 90) for x in (5.0, 8.0, 11.0, 14.0, 16.0, 20.0)]
           + [spot("crew", "sit", 6.0, 7.0, 0), spot("crew", "sit", 9.2, 7.0, 180), spot("crew", "sit", 18.0, 7.0, 180), spot("crew", "sit", 14.8, 7.0, 0)],
     lights=[light(12.0, 9.0, 3.6, 2800, 6500, (10.0, 1.0)), light(5.0, 6.0, 3.6, 1800, 3000, (2.0, 2.0)),
             light(19.0, 6.0, 3.6, 1800, 3000, (2.0, 2.0))])
_reg("store_dry", name="Dry Stores", kind="storage", dept="flight", L=24.0, D=16.0, h=3.4, plate="stores_dry",
     doors=[door("near", 14.0)], systems=["supply"],
     spots=[spot("storekeeper", "work", 13.0, 3.0, 90, "flight"), spot("storekeeper", "stand", 15.0, 9.0, 90, "flight")],
     lights=[light(12.0, 5.0, 3.3, 5200, 4600, (16.0, 0.8)), light(12.0, 12.0, 3.3, 5200, 4600, (16.0, 0.8))])
_reg("store_cold", name="Cold Stores", kind="storage", dept="science", L=24.0, D=16.0, h=3.4, plate="stores_cold",
     doors=[door("near", 14.0)], systems=["supply", "cold_chain", "coolant"],
     spots=[spot("storekeeper", "work", 13.0, 3.0, 90, "flight")],
     lights=[light(12.0, 5.0, 3.3, 4200, 6800, (16.0, 0.8)), light(12.0, 12.0, 3.3, 4200, 6800, (16.0, 0.8))])
_reg("hold", name="General Stores", kind="storage", dept="flight", L=24.0, D=16.0, h=3.4, plate="stores",
     doors=[door("near", 10.0)], systems=["supply"],
     spots=[spot("storekeeper", "work", 9.0, 3.0, 90, "flight"), spot("handler", "work", 16.0, 9.0, 0, "flight")],
     lights=[light(12.0, 5.0, 3.3, 5200, 4600, (16.0, 0.8)), light(12.0, 12.0, 3.3, 5200, 4600, (16.0, 0.8))])
_reg("heads", name="Heads · Showers", kind="heads", dept="services", L=12.0, D=16.0, h=3.4, plate="heads",
     doors=[door("near", 6.0)], systems=["potable_water", "waste"],
     spots=[], lights=[light(6.0, 8.0, 3.3, 5000, 5000, (6.0, 8.0))])
_reg("laundry", name="Laundry", kind="laundry", dept="services", L=12.0, D=16.0, h=3.4, plate="laundry",
     doors=[door("near", 6.0)], systems=["potable_water", "power_bus"],
     spots=[spot("laundry_hand", "work", 4.0, 7.0, 90), spot("laundry_hand", "work", 8.0, 7.0, 90)],
     lights=[light(6.0, 8.0, 3.3, 5000, 4800, (6.0, 8.0))])
_reg("hydro", name="Hydroponics Bay", kind="hydroponics", dept="science", L=24.0, D=16.0, h=3.4, plate="hydro",
     doors=[door("near", 10.0)], systems=["life_support", "potable_water", "food_service"],
     spots=[spot("botanist", "work", 8.0, 7.2, 0, "science"), spot("botanist", "work", 16.0, 7.2, 180, "science")],
     lights=[light(12.0, 8.0, 3.3, 3500, 7000, (20.0, 12.0), 1100)])
_reg("quiet", name="Quiet Room", kind="chapel", dept="services", L=12.0, D=16.0, h=3.6, plate="chapel",
     doors=[door("near", 6.0)], systems=["power_bus"],
     spots=[spot("crew", "sit", 3.6, 7.6, 90), spot("crew", "sit", 8.4, 7.6, 90), spot("crew", "sit", 3.6, 9.8, 90), spot("crew", "sit", 8.4, 9.8, 90)],
     lights=[light(6.0, 8.0, 3.5, 1500, 2700, (5.0, 5.0))])
# ---- the rest of the kit (Decks 3, 5, 8, 10, 11 of the canon): built and previewed, placed when their decks are built -------
_reg("lab", name="Science Lab", kind="lab", dept="science", L=24.0, D=16.0, h=3.6, plate="lab",
     doors=[door("near", 10.0)], systems=["sensors", "power_bus", "data_trunk"],
     spots=[spot("scientist", "sit", x, 14.4, 90, "science") for x in (5.0, 9.0, 13.0, 17.0)]
           + [spot("scientist", "sit", 10.2, 7.6, -90, "science"), spot("scientist", "sit", 13.4, 11.85, -90, "science"),
              spot("lead_scientist", "work", 20.5, 7.0, 180, "science")],
     lights=[light(6.0, 8.0, 3.5, 6500, 5600, (8.0, 8.0)), light(18.0, 8.0, 3.5, 6500, 5600, (8.0, 8.0))])
_reg("workshop", name="Machine Shop", kind="workshop", dept="engineering", L=28.0, D=16.0, h=3.7, plate="workshop",
     doors=[door("near", 10.0)], systems=["power_bus", "compressed_air", "damage_control"],
     spots=[spot("machinist", "work", 5.6, 14.2, 90, "engineering"), spot("machinist", "work", 9.0, 14.2, 90, "engineering"),
            spot("machinist", "work", 12.6, 14.2, 90, "engineering"), spot("fitter", "work", 15.3, 14.3, 90, "engineering"),
            spot("machinist", "work", 8.2, 7.5, 90, "engineering"), spot("fitter", "work", 13.2, 7.5, 90, "engineering"),
            spot("welder", "work", 22.9, 11.6, 0, "engineering")],
     lights=[light(9.0, 9.0, 3.7, 7000, 4800, (12.0, 1.0)), light(21.0, 9.0, 3.7, 7000, 4800, (12.0, 1.0)),
             light(14.0, 15.0, 3.7, 5000, 5200, (20.0, 0.8))])
_reg("armory", name="Armory", kind="armory", dept="security", L=16.0, D=16.0, h=3.4, plate="armory",
     doors=[door("near", 6.0)], systems=["ordnance", "power_bus"],
     spots=[spot("armorer", "work", 6.0, 5.4, -90, "security"), spot("guard", "stand", 9.0, 2.4, 90, "security")],
     lights=[light(8.0, 6.0, 3.3, 5500, 5000, (10.0, 1.0)), light(8.0, 12.0, 3.3, 5500, 5000, (10.0, 1.0))])
_reg("cabins", name="Crew Cabins", kind="cabins", dept="services", L=20.0, D=16.0, h=3.2, plate="cabins",
     doors=[door("near", 10.0)], systems=["power_bus", "life_support"],
     spots=[spot("sleeper", "sleep", 1.34, y, 180) for y in (0.56, 4.56, 8.56, 12.56)] + [spot("sleeper", "sleep", 18.66, y, 0) for y in (0.56, 4.56, 8.56, 12.56)],
     lights=[light(10.0, 8.0, 3.1, 2500, 3400, (14.0, 0.6))])

# ---- Deck 6: the medical rooms around the Medbay (docs/BIBBIA.md §6: Medbay, surgery, quarantine, pharmacy) ---------------------
_reg("surgery", name="Surgery", kind="surgery", dept="medical", L=16.0, D=16.0, h=3.6, plate="surgery",
     doors=[door("near", 6.0)], systems=["medical", "power_bus"],
     spots=[spot("surgeon", "work", 3.9, 9.6, 0, "medical"), spot("nurse", "work", 6.6, 9.0, 180, "medical"), spot("surgeon", "work", 9.9, 9.6, 0, "medical"),
            spot("nurse", "work", 12.6, 9.0, 180, "medical")],
     lights=[light(5.0, 9.0, 3.5, 6500, 6000, (4.0, 3.0)), light(11.0, 9.0, 3.5, 6500, 6000, (4.0, 3.0)), light(8.0, 13.5, 3.5, 3500, 5600, (12.0, 1.0))])
_reg("quarantine", name="Quarantine Ward", kind="quarantine", dept="medical", L=24.0, D=16.0, h=3.6, plate="quarantine",
     doors=[door("near", 10.0)], systems=["medical", "life_support"],
     spots=[spot("nurse", "work", 13.4, 6.2, 0, "medical"), spot("nurse", "work", 16.4, 4.4, 90, "medical")]
           + [spot("patient", "sleep", 1.7 + 3.7 * k, 14.59, 90, "medical") for k in range(6)],
     lights=[light(12.0, 4.5, 3.5, 6000, 6000, (14.0, 1.0)), light(12.0, 12.8, 3.5, 4500, 5200, (20.0, 1.0))])
_reg("pharmacy", name="Pharmacy", kind="pharmacy", dept="medical", L=12.0, D=16.0, h=3.4, plate="pharmacy",
     doors=[door("near", 6.0)], systems=["medical", "supply"],
     spots=[spot("pharmacist", "work", 6.0, 5.4, -90, "medical"), spot("pharmacist", "work", 6.45, 7.4, 90, "medical")],
     lights=[light(6.0, 8.0, 3.3, 4200, 5600, (6.0, 8.0))])


def _variant(base: str, suffix: str, door_x: float) -> None:
    """The same room with its near door moved to `door_x` (the layout puts some doors on another module of the corridor): another mesh."""
    import copy
    spec = copy.deepcopy(PREFABS[base])
    spec["key"] = f"{base}_{suffix}"
    spec["mesh"] = PREFABS[base]["mesh"] + suffix.upper()
    spec["doors"] = [door("near", door_x)] + [d for d in spec["doors"] if d["wall"] != "near"]
    spec["variant_of"] = base
    PREFABS[spec["key"]] = spec


_variant("observation", "d14", 14.0)
_variant("store_dry", "d10", 10.0)
# ---- specials (their own frames: see ship_rooms.py): concourse, stair tower, bow observation ---------------------------------
_reg("concourse", name="Mess Concourse", kind="concourse", dept="services", L=17.7, D=36.0, h=3.7, plate="concourse", doors=[],
     systems=["power_bus", "life_support"], special=True,
     spots=[spot("crew", "stand", 4.0, 11.5, 180), spot("crew", "sit", 6.75, 17.0, 0), spot("crew", "sit", 6.75, 19.0, 0), spot("crew", "sit", 11.25, 17.0, 180),
            spot("crew", "sit", 11.25, 19.0, 180), spot("crew", "sit", 7.0, 1.15, 90), spot("crew", "sit", 8.4, 34.85, -90), spot("crew", "stand", 3.4, 27.0, 0)],
     lights=[light(9.0, 18.0, 3.6, 9000, 4200, (10.0, 2.0), 1400), light(9.0, 8.0, 3.6, 5000, 3600, (6.0, 2.0), 1100),
             light(9.0, 28.0, 3.6, 5000, 3600, (6.0, 2.0), 1100)])
_reg("berth_lobby", name="Berthing Lobby", kind="concourse", dept="services", L=14.6, D=36.0, h=3.6, plate=None, doors=[],
     systems=["power_bus", "life_support"], special=True,
     spots=[spot("crew", "sit", 12.4, 7.2, 180), spot("crew", "sit", 12.4, 8.8, 180), spot("crew", "sit", 8.7, 6.6, 0), spot("crew", "sit", 12.4, 27.2, 180),
            spot("crew", "sit", 12.4, 28.8, 180), spot("crew", "sit", 8.7, 29.4, 0)],
     lights=[light(7.3, 18.0, 3.5, 4500, 3600, (8.0, 3.0), 1200), light(7.3, 8.0, 3.5, 2500, 3200, (5.0, 2.0), 900),
             light(7.3, 28.0, 3.5, 2500, 3200, (5.0, 2.0), 900)])
_reg("stair_tower", name="Stair Tower", kind="stairs", dept="neutral", L=8.0, D=8.0, h=3.4, plate="stairs", doors=[door("near", 2.0)],
     systems=["power_bus"], special=True, spots=[], lights=[light(4.0, 4.0, 3.3, 3000, 4500, (3.0, 3.0), 800)])
_reg("bow_obs", name="Bow Observation", kind="observation", dept="command", L=20.0, D=32.0, h=3.7, plate="bow_obs", doors=[],
     systems=["power_bus"], special=True,
     spots=[spot("crew", "watch", 17.45 if i == 5 else 17.6, 6.0 + 4.5 * i - (0.06 if i == 5 else 0.0), 0) for i in range(6)]
           + [spot("crew", "sit", 11.6, 5.5, 0), spot("crew", "sit", 11.6, 7.5, 0), spot("crew", "sit", 11.6, 24.5, 0), spot("crew", "sit", 11.6, 26.5, 0)],
     lights=[light(10.0, 16.0, 3.6, 3200, 6200, (12.0, 1.0), 1200)])
# ---- planned rooms: typed compartments of the decks that are not modelled yet (no mesh), with real dimensions ------------------
def _plan(key: str, name: str, kind: str, dept: str, L: float, D: float, h: float, systems: list, roles=("crew",), n: int = 3, dx: float = 6.0,
          act: str = "work", lm: float = 4500.0, temp: float = 4500.0, plate: str | None = None) -> None:
    spots = []
    for i in range(n):
        spots.append(spot(roles[i % len(roles)], act, 3.0 + (L - 6.0) * (i + 0.5) / n, D * 0.55, 90, dept))
    PREFABS[key] = dict(key=key, mesh=None, name=name, kind=kind, dept=dept, L=L, D=D, h=h, plate=plate, doors=[door("near", dx)], systems=systems,
                        spots=spots, lights=[light(L / 2, D / 2, h - 0.1, lm, temp, (min(L - 4, 12.0), 1.0), 900.0)], planned=True)


_plan("cic", "Combat Information Centre", "cic", "command", 32.0, 16.0, 3.6, ["sensors", "tactical", "data_trunk", "power_bus"],
      ("tactical_officer", "sensor_operator", "plotter"), 8, 14.0, lm=6000, temp=6500)
_plan("briefing", "Briefing Room", "briefing", "command", 16.0, 16.0, 3.6, ["power_bus"], ("officer",), 6, 6.0, "sit")
_plan("comms_center", "Communications Centre", "comms", "command", 24.0, 16.0, 3.6, ["comms", "data_trunk", "power_bus"], ("comms_operator",), 4, 10.0)
_plan("offices", "Department Offices", "offices", "command", 16.0, 16.0, 3.4, ["power_bus", "data_trunk"], ("clerk", "officer"), 4, 6.0)
_plan("records", "Records & Archive", "offices", "command", 12.0, 16.0, 3.4, ["data_trunk"], ("archivist",), 2, 6.0)
_plan("vls_magazine", "VLS Magazine", "magazine", "security", 24.0, 16.0, 6.0, ["weapons", "ordnance", "power_bus"], ("loader",), 3, 10.0, lm=3500)
_plan("point_defense", "Point-Defence Control", "weapons_control", "security", 16.0, 16.0, 3.6, ["weapons", "sensors", "power_bus"], ("gunner",), 4, 6.0)
_plan("barbette", "Turret Barbette", "weapons", "security", 24.0, 16.0, 8.0, ["weapons", "power_bus", "ordnance"], ("gunner",), 4, 10.0, lm=3000)
_plan("sensor_room", "Sensor Array Room", "sensors", "science", 16.0, 16.0, 3.6, ["sensors", "data_trunk", "coolant"], ("sensor_tech",), 3, 6.0)
_plan("wardroom", "Officers' Wardroom", "wardroom", "command", 24.0, 16.0, 3.6, ["power_bus"], ("officer",), 6, 10.0, "sit", temp=3300)
_plan("staterooms", "Officers' Staterooms", "cabins", "services", 20.0, 16.0, 3.2, ["power_bus", "life_support"], ("officer",), 4, 10.0, "sleep", 2500, 3400)
_plan("gym", "Gymnasium", "gym", "services", 24.0, 16.0, 3.7, ["power_bus", "life_support"], ("crew",), 6, 10.0, "work", 5000, 5000)
_plan("transporter", "Transporter Room", "transporter", "science", 24.0, 16.0, 3.8, ["transporter", "power_bus", "data_trunk", "coolant"],
      ("transporter_chief", "operator"), 2, 10.0, lm=4500, temp=6500)
_plan("sensor_archive", "Sensor Archive", "archive", "science", 16.0, 16.0, 3.4, ["sensors", "data_trunk"], ("archivist",), 2, 6.0)
_plan("radiator_pumps", "Radiator Manifold", "machinery", "engineering", 24.0, 16.0, 3.7, ["coolant", "radiators", "power_bus"], ("machinist",), 3, 10.0)
_plan("dc_locker", "Damage Control Locker", "damage_control", "engineering", 12.0, 16.0, 3.4, ["damage_control", "supply"], ("dc_tech",), 4, 6.0)
_plan("power_control", "Power Control", "power", "engineering", 24.0, 16.0, 3.6, ["power_bus", "reactor", "data_trunk"], ("power_tech",), 4, 10.0)
_plan("machinery", "Machinery Space", "machinery", "engineering", 24.0, 16.0, 3.7, ["power_bus", "coolant", "compressed_air"], ("machinist",), 2, 10.0)
_plan("barracks", "Marine Barracks", "cabins", "security", 24.0, 16.0, 3.4, ["power_bus", "life_support"], ("marine",), 8, 10.0, "sleep", 2500, 3600)
_plan("firing_range", "Firing Range", "range", "security", 40.0, 16.0, 3.6, ["ordnance", "power_bus"], ("marine",), 6, 10.0, "work", 4000, 5600)
_plan("shuttle_bay", "Assault-Shuttle Bay", "hangar", "security", 32.0, 16.0, 3.7, ["launch_tubes", "power_bus", "life_support"], ("marine", "deck_hand"), 4, 14.0,
      lm=5000)
_plan("flight_ops", "Flight Operations", "flight_ops", "flight", 24.0, 16.0, 3.6, ["comms", "power_bus"], ("flight_officer",), 4, 10.0)
_plan("aircraft_shop", "Aircraft Workshop", "workshop", "flight", 28.0, 16.0, 3.7, ["power_bus", "compressed_air"], ("aircraft_tech",), 4, 10.0)
_plan("magazine", "Munitions Magazine", "magazine", "security", 24.0, 16.0, 3.6, ["ordnance", "power_bus"], ("loader",), 2, 10.0)
_plan("fab_shop", "Fabrication Shop", "fabrication", "engineering", 28.0, 16.0, 3.8, ["power_bus", "compressed_air", "data_trunk"], ("fabricator",), 4, 10.0)
_plan("repair_bay", "Repair Bay", "workshop", "engineering", 32.0, 16.0, 3.7, ["damage_control", "power_bus"], ("dc_tech",), 4, 10.0)
_plan("tank", "Fuel & Coolant Tank", "tank", "neutral", 32.0, 16.0, 3.4, ["coolant", "fuel"], ("machinist",), 1, 14.0)
_plan("reaction_mass", "Reaction-Mass Tank", "tank", "neutral", 40.0, 16.0, 3.4, ["reaction_mass"], ("machinist",), 1, 18.0)
_plan("crawlway", "Maintenance Crawlway Hub", "crawlway", "engineering", 16.0, 16.0, 3.0, ["power_bus", "data_trunk", "coolant"], ("dc_tech",), 2, 6.0)
_plan("cargo_hold", "Cargo Hold", "storage", "flight", 32.0, 16.0, 3.7, ["supply"], ("handler",), 2, 10.0)


# ================================================================================================================ NAVE-2: the other decks
# Rooms with meshes: these replace the planned entries above (a later registration of the same key wins). The sizes stay those of the planned rooms so
# that the plans of the decks do not move; doors on a module centre (x = 2 mod 4); `dz` is the height above the floor of a place on a platform.
_reg("transporter", name="Transporter Room", kind="transporter", dept="science", L=24.0, D=16.0, h=3.7, plate="transporter",
     doors=[door("near", 10.0)], systems=["transporter", "power_bus", "data_trunk", "coolant"],
     spots=[spot("transporter_chief", "sit", 22.6, 3.0, 0, "science"), spot("transport_operator", "sit", 8.4, 7.0, 0, "science"),
            spot("transport_operator", "sit", 8.4, 10.2, 0, "science"), spot("engineer", "work", 7.4, 13.4, 90, "engineering"),
            spot("technician", "work", 4.6, 10.8, 90, "science"), spot("technician", "stand", 3.2, 5.2, 90, "science"),
            spot("visitor", "stand", 19.0, 8.6, 180, "science", 0.312), spot("visitor", "stand", 15.0, 8.6, 0, "science", 0.312)],
     lights=[light(17.0, 8.6, 3.7, 5600, 6000, (6.0, 6.0), 1200), light(8.0, 8.6, 3.7, 4200, 5600, (5.0, 4.0), 1000), light(4.6, 13.0, 3.7, 2400, 6000, (3.0, 3.0), 800),
             light(12.0, 14.0, 3.7, 3000, 5600, (14.0, 1.0), 900)])


import math as _m


def _ring_spots(role: str, kind: str, cx: float, cy: float, r: float, angles, dept: str, face_in: bool = True) -> list:
    """Places on a circle round (cx, cy) at the given angles (degrees), facing the middle."""
    return [spot(role, kind, cx + r * _m.cos(_m.radians(a)), cy + r * _m.sin(_m.radians(a)), (a + 180.0) % 360.0 if face_in else a % 360.0, dept) for a in angles]


_reg("sensor_archive", name="Sensor Archive", kind="archive", dept="science", L=16.0, D=16.0, h=3.4, plate="archive",
     doors=[door("near", 6.0)], systems=["sensors", "data_trunk", "power_bus"],
     spots=[spot("archivist", "sit", 11.4, 1.0, 90, "science"), spot("archive_technician", "work", 1.8, 1.8, 270, "science"),
            spot("archive_technician", "work", 6.0, 8.0, 0, "science"), spot("archive_technician", "work", 9.3, 9.0, 180, "science"),
            spot("analyst", "stand", 12.6, 9.0, 0, "science")],
     lights=[light(6.0, 9.5, 3.3, 2600, 7000, (1.2, 10.0), 900), light(9.3, 9.5, 3.3, 2600, 7000, (1.2, 10.0), 900), light(12.6, 9.5, 3.3, 2600, 7000, (1.2, 10.0), 900),
             light(8.0, 2.4, 3.3, 3000, 5000, (6.0, 2.0), 800)])
_reg("sensor_room", name="Sensor Array Room", kind="sensors", dept="science", L=16.0, D=16.0, h=3.6, plate="sensors",
     doors=[door("near", 6.0)], systems=["sensors", "data_trunk", "coolant", "power_bus"],
     spots=[spot("sensor_operator", "sit", 3.4, 6.9, 90, "science"), spot("sensor_operator", "sit", 8.0, 6.9, 90, "science"),
            spot("sensor_operator", "sit", 12.6, 6.9, 90, "science"), spot("sensor_supervisor", "stand", 6.0, 11.0, 0, "science"),
            spot("sensor_tech", "work", 2.2, 7.0, 180, "science"), spot("sensor_tech", "work", 13.8, 7.0, 0, "science")],
     lights=[light(8.0, 6.0, 3.5, 4200, 6000, (12.0, 2.0), 1000), light(8.0, 12.0, 3.5, 3000, 5600, (8.0, 3.0), 900)])
_reg("lab_bio", name="Biology Lab", kind="lab", dept="science", L=24.0, D=16.0, h=3.6, plate="lab_bio",
     doors=[door("near", 10.0)], systems=["sensors", "power_bus", "data_trunk", "life_support"],
     spots=[spot("biologist", "work", 5.9, 8.6, 0, "science"), spot("biologist", "work", 17.15, 6.6, 90, "science"),
            spot("lab_technician", "work", 22.4, 10.4, 0, "science"), spot("lab_technician", "work", 22.4, 12.6, 0, "science"),
            spot("lead_scientist", "sit", 13.4, 2.0, 270, "science"), spot("biologist", "stand", 10.0, 13.4, 90, "science")],
     lights=[light(6.0, 8.0, 3.5, 6500, 5600, (8.0, 8.0)), light(18.0, 8.0, 3.5, 6500, 5600, (8.0, 8.0))])
_reg("lab_astro", name="Astrometrics", kind="lab", dept="science", L=24.0, D=16.0, h=3.6, plate="lab_astro",
     doors=[door("near", 10.0)], systems=["sensors", "power_bus", "data_trunk"],
     spots=_ring_spots("astrometrist", "sit", 12.0, 8.2, 3.6, (30, 90, 210, 270), "science") + [spot("lead_scientist", "stand", 3.0, 8.0, 0, "science")],
     lights=[light(12.0, 8.2, 3.5, 2200, 7500, (8.0, 8.0), 900), light(12.0, 14.0, 3.5, 1500, 7500, (18.0, 1.0), 900)])
_reg("lab_phys", name="Physics Lab", kind="lab", dept="science", L=24.0, D=16.0, h=3.7, plate="lab_phys",
     doors=[door("near", 10.0)], systems=["sensors", "power_bus", "data_trunk", "coolant"],
     spots=[spot("physicist", "sit", 5.0, 2.8, 90, "science"), spot("physics_technician", "work", 9.0, 9.4, 90, "science"),
            spot("physics_technician", "work", 19.6, 9.2, 90, "science"), spot("cryo_technician", "work", 20.3, 4.2, 0, "science"),
            spot("physicist", "work", 12.0, 13.7, 90, "science")],
     lights=[light(8.0, 4.0, 3.7, 3500, 6000, (6.0, 6.0)), light(12.0, 11.0, 3.7, 6500, 5600, (14.0, 4.0)), light(19.6, 11.0, 3.7, 4000, 5600, (5.0, 5.0))])


_reg("radiator_pumps", name="Radiator Manifold", kind="machinery", dept="engineering", L=24.0, D=16.0, h=3.7, plate="pumps",
     doors=[door("near", 10.0)], systems=["coolant", "radiators", "power_bus"],
     spots=[spot("machinist", "work", 5.6, 9.4, 0, "engineering"), spot("machinist", "work", 10.0, 9.4, 0, "engineering"), spot("pump_tender", "work", 14.4, 9.4, 0, "engineering"),
            spot("coolant_tender", "work", 19.0, 7.2, 0, "engineering"), spot("machinist", "sit", 7.4, 1.1, 90, "engineering"), spot("engineer", "stand", 15.6, 2.4, 90, "engineering")],
     lights=[light(8.0, 8.0, 3.6, 5000, 4500, (12.0, 1.0), 1000), light(18.0, 8.0, 3.6, 5000, 4500, (10.0, 1.0), 1000)])
_reg("machinery", name="Machinery Space", kind="machinery", dept="engineering", L=24.0, D=16.0, h=3.7, plate="machinery",
     doors=[door("near", 10.0)], systems=["power_bus", "coolant", "compressed_air", "life_support", "potable_water"],
     spots=[spot("machinist", "work", 3.4, 12.6, 90, "engineering"), spot("machinist", "work", 7.4, 12.6, 90, "engineering"), spot("machinist", "work", 11.4, 12.6, 90, "engineering"),
            spot("water_tender", "work", 18.6, 10.4, 0, "engineering"), spot("machinist", "sit", 14.0, 1.0, 270, "engineering"), spot("machinist", "work", 7.0, 6.1, 90, "engineering")],
     lights=[light(8.0, 8.0, 3.6, 5000, 4500, (12.0, 1.0), 1000), light(18.0, 8.0, 3.6, 4500, 4500, (8.0, 1.0), 1000)])
_reg("machinery_b", name="Compressor Room", kind="machinery", dept="engineering", L=24.0, D=16.0, h=3.7, plate="machinery",
     doors=[door("near", 10.0)], systems=["power_bus", "compressed_air"],
     spots=[spot("machinist", "work", 4.0, 7.2, 90, "engineering"), spot("machinist", "work", 8.4, 7.2, 90, "engineering"), spot("machinist", "work", 15.8, 9.0, 0, "engineering"),
            spot("machinist", "sit", 12.0, 3.0, 270, "engineering"), spot("engineer", "stand", 20.0, 6.5, 180, "engineering")],
     lights=[light(8.0, 8.0, 3.6, 5000, 4500, (12.0, 1.0), 1000), light(18.0, 8.0, 3.6, 4500, 4500, (8.0, 1.0), 1000)])
_reg("dc_locker", name="Damage Control Locker", kind="damage_control", dept="engineering", L=12.0, D=16.0, h=3.4, plate="dc",
     doors=[door("near", 6.0)], systems=["damage_control", "supply"],
     spots=[spot("dc_technician", "stand", 4.4, 13.2, 90, "engineering"), spot("dc_technician", "work", 6.0, 6.2, 270, "engineering"),
            spot("dc_technician", "stand", 2.0, 8.0, 180, "engineering"), spot("dc_technician", "stand", 10.2, 8.0, 0, "engineering")],
     lights=[light(6.0, 5.0, 3.3, 4200, 5000, (6.0, 1.0), 900), light(6.0, 11.0, 3.3, 4200, 5000, (6.0, 1.0), 900)])
_reg("power_control", name="Power Control", kind="power", dept="engineering", L=24.0, D=16.0, h=3.6, plate="power",
     doors=[door("near", 10.0)], systems=["power_bus", "reactor", "data_trunk"],
     spots=[spot("power_technician", "sit", 3.6, 7.35, 90, "engineering"), spot("power_technician", "sit", 8.0, 7.35, 90, "engineering"),
            spot("power_technician", "sit", 12.4, 7.35, 90, "engineering"), spot("power_technician", "sit", 3.6, 4.35, 90, "engineering"),
            spot("power_technician", "sit", 8.0, 4.35, 90, "engineering"), spot("power_supervisor", "stand", 12.4, 10.2, 90, "engineering"),
            spot("power_technician", "work", 22.0, 6.0, 180, "engineering")],
     lights=[light(8.0, 6.0, 3.5, 4800, 4500, (12.0, 3.0), 1000), light(18.0, 8.0, 3.5, 3600, 4500, (6.0, 8.0), 900)])


# ---- Deck 8: the Marines' deck ------------------------------------------------------------------------------------------------------------------------
_reg("shuttle_bay", name="Assault-Shuttle Bay", kind="hangar", dept="security", L=32.0, D=16.0, h=3.7, plate="shuttle_bay",
     doors=[door("near", 14.0), door("near", 18.0)], systems=["launch_tubes", "power_bus", "life_support"],
     spots=[spot("deck_chief", "sit", 16.0, 13.8, 90, "flight"), spot("deck_hand", "work", 1.7, 3.5, 180, "flight"), spot("deck_hand", "work", 29.6, 4.0, 0, "flight"),
            spot("marine", "stand", 8.5, 1.0, 90, "security"), spot("marine", "stand", 23.5, 1.0, 90, "security"), spot("deck_hand", "stand", 16.0, 6.0, 90, "flight"),
            spot("marine", "sit", 4.2, 0.4, 90, "security"), spot("marine", "sit", 27.8, 0.4, 90, "security")],
     lights=[light(8.5, 9.4, 3.6, 6500, 5600, (6.0, 12.0), 1300), light(23.5, 9.4, 3.6, 6500, 5600, (6.0, 12.0), 1300), light(16.0, 7.0, 3.6, 4500, 5000, (4.0, 12.0), 1100),
             light(16.0, 14.4, 3.4, 3000, 4500, (6.0, 2.0), 900)])


KESTREL_X, KESTREL_Y = (8.5, 23.5), 9.4                                  # the Kestrels' centre line across the bay and along it (shuttle_bay: nose to the far wall)
BUNK_X, BUNK_Y = tuple(round(1.9 + k * 2.93, 3) for k in range(8)), 14.75    # the barracks' eight double bunks (heads on the far wall)
RANGE_LANE_Y, RANGE_BOOTH_X = tuple(round(4.55 + 2.0 * k, 3) for k in range(6)), 5.0    # the range's six lanes and the shooters' place

_reg("barracks", name="Marine Barracks", kind="cabins", dept="security", L=24.0, D=16.0, h=3.4, plate="barracks",
     doors=[door("near", 10.0)], systems=["power_bus", "life_support"],
     spots=[spot("marine", "sleep", x, BUNK_Y, 90, "security") for x in BUNK_X] + [spot("marine", "sleep", x, BUNK_Y, 90, "security", 0.96) for x in BUNK_X]
           + [spot("marine", "sit", x, 7.35, 90, "security") for x in (15.4, 16.5, 17.6)] + [spot("marine", "sit", x, 9.45, -90, "security") for x in (15.4, 16.5, 17.6)]
           + [spot("marine", "sit", 3.95, y, 180, "security") for y in (5.6, 6.8, 8.0, 9.2)]
           + [spot("marine", "work", 21.45, 7.15, 180, "security"), spot("sergeant", "stand", 11.4, 2.6, 90, "security")],
     lights=[light(12.0, 4.0, 3.2, 2400, 3600, (14.0, 1.0), 900), light(12.0, 9.5, 3.2, 2400, 3600, (14.0, 1.0), 900), light(4.0, 7.4, 3.2, 2000, 3400, (4.0, 5.0), 800)])
_reg("kit_room", name="Kit Room", kind="armory", dept="security", L=16.0, D=16.0, h=3.4, plate="kit_room",
     doors=[door("near", 6.0)], systems=["power_bus", "ordnance"],
     spots=[spot("marine", "stand", 2.0, 4.5, 180, "security"), spot("marine", "stand", 2.0, 7.6, 180, "security"), spot("marine", "sit", 2.6, 12.9, 90, "security"),
            spot("marine", "sit", 9.8, 12.9, 90, "security"), spot("armourer", "work", 3.0, 1.6, -90, "security"), spot("marine", "stand", 8.4, 3.0, 90, "security")],
     lights=[light(8.0, 5.0, 3.3, 5000, 5600, (12.0, 1.0)), light(8.0, 11.0, 3.3, 5000, 5600, (12.0, 1.0))])
_reg("firing_range", name="Firing Range", kind="range", dept="security", L=40.0, D=16.0, h=3.6, plate="range",
     doors=[door("near", 10.0)], systems=["ordnance", "power_bus"],
     spots=[spot("marine", "work", RANGE_BOOTH_X - 0.3, y, 0, "security") for y in RANGE_LANE_Y]
           + [spot("range_officer", "sit", 15.0, 1.2, 90, "security"), spot("marine", "stand", 8.0, 1.7, 0, "security"), spot("armourer", "work", 24.0, 1.5, -90, "security")],
     lights=[light(5.0, 9.5, 3.5, 6000, 5600, (3.0, 12.0), 1200), light(15.0, 9.5, 3.4, 4500, 5200, (6.0, 12.0), 1100), light(26.0, 9.5, 3.4, 3000, 5200, (3.0, 12.0), 1000),
             light(36.0, 9.5, 3.4, 3000, 5200, (3.0, 12.0), 1000), light(15.0, 1.6, 3.4, 3500, 4800, (10.0, 2.0), 900)])


_reg("switchgear", name="Switchgear Hall", kind="power", dept="engineering", L=24.0, D=16.0, h=3.7, plate="switchgear",
     doors=[door("near", 10.0)], systems=["power_bus", "reactor"],
     spots=[spot("power_technician", "work", 4.5, 14.2, 90, "engineering"), spot("power_technician", "work", 12.0, 14.2, 90, "engineering"),
            spot("power_technician", "work", 18.0, 14.2, 90, "engineering"), spot("power_supervisor", "sit", 6.4, 1.45, 90, "engineering"),
            spot("power_technician", "stand", 12.0, 6.0, 0, "engineering")],
     lights=[light(8.0, 13.7, 3.5, 4200, 4400, (14.0, 1.0), 1000), light(18.0, 13.7, 3.5, 3600, 4400, (8.0, 1.0), 1000), light(12.0, 6.0, 3.5, 3000, 4800, (12.0, 6.0), 900)])
_reg("capacitors", name="Capacitor Hall", kind="power", dept="engineering", L=24.0, D=16.0, h=3.7, plate="capacitors",
     doors=[door("near", 10.0)], systems=["power_bus", "reactor", "coolant"],
     spots=[spot("power_technician", "sit", 6.0, 2.5, -90, "engineering"), spot("power_technician", "stand", 11.2, 7.0, 90, "engineering"),
            spot("power_technician", "work", 11.2, 11.6, 90, "engineering"), spot("power_supervisor", "stand", 12.0, 3.0, 90, "engineering")],
     lights=[light(11.2, 8.4, 3.6, 3800, 3800, (2.0, 12.0), 1000), light(6.0, 8.4, 3.6, 3000, 4200, (6.0, 8.0), 900), light(18.0, 8.4, 3.6, 3000, 4200, (6.0, 8.0), 900)])


# ---- Deck 9: flight operations, the pilots' room, the aircraft workshop, the magazine, the cargo hold ---------------------------------------------------
_reg("flight_ops", name="Flight Operations", kind="flight_ops", dept="flight", L=24.0, D=16.0, h=3.6, plate="flight_ops",
     doors=[door("near", 10.0)], systems=["comms", "power_bus", "data_trunk"],
     spots=[spot("flight_officer", "sit", x, 9.15, 90, "flight") for x in (4.5, 8.0, 16.0, 19.5)] + [spot("flight_officer", "sit", x, 4.75, 90, "flight") for x in (3.8, 7.4, 16.6, 20.2)]
           + [spot("air_boss", "stand", 10.6, 11.2, 90, "flight"), spot("cag", "stand", 13.4, 11.2, 90, "flight")],
     lights=[light(12.0, 7.0, 3.5, 4500, 5600, (14.0, 8.0), 1100), light(12.0, 12.8, 3.5, 3500, 6000, (8.0, 4.0), 900), light(12.0, 14.8, 3.4, 2500, 6500, (18.0, 1.0), 900)])
_reg("pilot_ready", name="Pilots' Ready Room", kind="flight_ops", dept="flight", L=24.0, D=16.0, h=3.6, plate="pilot_ready",
     doors=[door("near", 10.0)], systems=["power_bus", "life_support"],
     spots=[spot("pilot", "sit", x, y, 90, "flight") for y in (5.2, 7.2, 9.2) for x in (4.0, 7.4, 16.6, 20.0)]
           + [spot("pilot", "sit", 23.1, 10.0, 180, "flight"), spot("pilot", "sit", 23.1, 13.8, 180, "flight"), spot("briefing_officer", "stand", 12.0, 15.0, -90, "flight")],
     lights=[light(12.0, 8.0, 3.5, 3600, 4000, (16.0, 10.0), 1000), light(12.0, 13.0, 3.5, 2500, 5600, (8.0, 3.0), 900)])
_reg("aircraft_shop", name="Aircraft Workshop", kind="workshop", dept="flight", L=28.0, D=16.0, h=3.7, plate="aircraft_shop",
     doors=[door("near", 10.0)], systems=["power_bus", "compressed_air", "damage_control"],
     spots=[spot("aircraft_technician", "work", 1.9, 3.0, 180, "flight"), spot("aircraft_technician", "work", 1.9, 6.2, 180, "flight"),
            spot("aircraft_technician", "work", 19.5, 7.3, 90, "flight"), spot("aircraft_technician", "work", 19.5, 9.8, -90, "flight"),
            spot("aircraft_technician", "work", 6.6, 10.3, 90, "flight"), spot("aircraft_technician", "work", 11.0, 6.6, 180, "flight")],
     lights=[light(8.0, 8.0, 3.7, 6500, 5200, (10.0, 10.0), 1100), light(20.0, 8.5, 3.7, 7000, 5200, (10.0, 8.0), 1200), light(14.0, 14.5, 3.7, 4500, 5000, (20.0, 1.0), 1000)])
_reg("magazine", name="Munitions Magazine", kind="magazine", dept="security", L=24.0, D=16.0, h=3.6, plate="magazine",
     doors=[door("near", 10.0)], systems=["ordnance", "power_bus"],
     spots=[spot("loader", "work", 6.0, 12.5, 90, "security"), spot("loader", "work", 15.0, 12.5, 90, "security"), spot("loader", "work", 21.0, 12.5, 90, "security"),
            spot("loader", "work", 12.0, 4.2, 90, "security")],
     lights=[light(8.0, 8.0, 3.5, 5000, 5000, (14.0, 1.0), 1000), light(18.0, 8.0, 3.5, 4500, 5000, (8.0, 1.0), 1000)])
_reg("cargo_hold", name="Cargo Hold", kind="storage", dept="flight", L=32.0, D=16.0, h=3.7, plate="cargo",
     doors=[door("near", 10.0)], systems=["supply"],
     spots=[spot("handler", "work", 5.0, 5.7, 90, "flight"), spot("handler", "work", 23.0, 5.7, 90, "flight"), spot("handler", "work", 9.0, 5.7, 90, "flight"),
            spot("handler", "work", 16.0, 11.0, 0, "flight")],
     lights=[light(8.0, 8.0, 3.6, 5200, 4800, (12.0, 6.0), 1100), light(24.0, 8.0, 3.6, 5200, 4800, (12.0, 6.0), 1100), light(16.0, 4.0, 3.6, 4200, 4800, (8.0, 2.0), 900)])


# ---- Deck 11: fabrication and repair ----------------------------------------------------------------------------------------------------------------------
_reg("fab_shop", name="Fabrication Shop", kind="fabrication", dept="engineering", L=28.0, D=16.0, h=3.7, plate="fab",
     doors=[door("near", 10.0)], systems=["power_bus", "compressed_air", "data_trunk"],
     spots=[spot("fabricator", "work", x, 12.4, 90, "engineering") for x in (3.6, 6.4, 9.2)]
           + [spot("fabricator", "work", 17.0, 10.0, 90, "engineering"), spot("fabricator", "work", 24.0, 13.2, 90, "engineering"),
              spot("machinist", "work", 25.6, 4.0, 180, "engineering"), spot("machinist", "work", 25.6, 6.4, 180, "engineering"),
              spot("quality_inspector", "work", 22.0, 3.7, -90, "engineering")],
     lights=[light(8.0, 8.0, 3.8, 6000, 5400, (12.0, 10.0), 1100), light(20.0, 8.0, 3.8, 6000, 5400, (12.0, 10.0), 1100), light(14.0, 14.5, 3.8, 3500, 5000, (22.0, 1.0), 900)])
_reg("repair_bay", name="Repair Bay", kind="workshop", dept="engineering", L=32.0, D=16.0, h=3.7, plate="repair",
     doors=[door("near", 10.0)], systems=["damage_control", "power_bus"],
     spots=[spot("dc_technician", "work", 15.0, 6.5, -90, "engineering"), spot("dc_technician", "work", 29.3, 11.4, 0, "engineering"),
            spot("dc_technician", "work", 29.3, 8.0, 0, "engineering"), spot("dc_technician", "stand", 17.7, 12.8, 90, "engineering"),
            spot("dc_technician", "stand", 1.8, 6.0, 180, "engineering")],
     lights=[light(8.0, 8.0, 3.6, 5200, 5000, (12.0, 8.0), 1000), light(24.0, 8.0, 3.6, 5200, 5000, (12.0, 8.0), 1000), light(16.0, 13.5, 3.6, 3500, 4800, (20.0, 1.0), 900)])


# ---- Deck 2: the command deck (clear height 3.6: the VLS hall and the barbette are the lower part of tall installations) -------------------------------------
_reg("cic", name="Combat Information Centre", kind="cic", dept="command", L=32.0, D=16.0, h=3.6, plate="cic",
     doors=[door("near", 14.0)], systems=["sensors", "tactical", "data_trunk", "power_bus"],
     spots=[spot(r, "sit", x, y, 90, "command") for (x, r) in zip((3.6, 7.0, 10.4, 21.6, 25.0, 28.4), ("tactical_officer", "sensor_operator", "plotter") * 2) for y in (7.95, 4.15)]
           + [spot("combat_officer", "stand", 13.0, 11.2, 90, "command"), spot("damage_control_officer", "stand", 19.0, 11.2, 90, "command")],
     lights=[light(8.0, 7.0, 3.5, 5000, 6000, (10.0, 8.0), 1100), light(24.0, 7.0, 3.5, 5000, 6000, (10.0, 8.0), 1100), light(16.0, 12.4, 3.5, 4500, 6500, (4.0, 4.0), 1000),
             light(16.0, 14.8, 3.4, 3000, 6500, (24.0, 1.0), 900)])
_reg("briefing", name="Briefing Room", kind="briefing", dept="command", L=16.0, D=16.0, h=3.6, plate="briefing",
     doors=[door("near", 6.0)], systems=["power_bus"],
     spots=[spot("officer", "sit", 8.0 - 2.4 + k * 0.96, 7.1, 90, "command") for k in range(6)] + [spot("officer", "sit", 8.0 - 2.4 + k * 0.96, 9.7, -90, "command") for k in range(6)]
           + [spot("officer", "sit", 4.3, 8.4, 0, "command"), spot("officer", "sit", 11.7, 8.4, 180, "command")],
     lights=[light(8.0, 8.4, 3.5, 4200, 3600, (8.0, 3.0), 1000), light(8.0, 14.0, 3.5, 2500, 5600, (12.0, 1.0), 800)])
_reg("comms_center", name="Communications Centre", kind="comms", dept="command", L=24.0, D=16.0, h=3.6, plate="comms",
     doors=[door("near", 10.0)], systems=["comms", "data_trunk", "power_bus"],
     spots=[spot("comms_operator", "sit", x, y - 1.25, 90, "command") for y in (11.2, 8.0, 4.8) for x in (4.0, 7.4, 16.6, 20.0)],
     lights=[light(12.0, 7.0, 3.5, 5200, 6000, (16.0, 8.0), 1000), light(12.0, 14.6, 3.4, 3000, 6500, (18.0, 1.0), 900)])
_reg("offices", name="Department Offices", kind="offices", dept="command", L=16.0, D=16.0, h=3.4, plate="offices",
     doors=[door("near", 6.0)], systems=["power_bus", "data_trunk"],
     spots=[spot("clerk", "sit", 2.4, 4.6, 0, "command"), spot("officer", "sit", 2.4, 10.6, 0, "command"), spot("clerk", "sit", 13.6, 4.6, 180, "command"),
            spot("officer", "sit", 13.6, 10.6, 180, "command")],
     lights=[light(8.0, 8.0, 3.3, 4500, 4200, (12.0, 10.0), 1000)])
_reg("records", name="Records & Archive", kind="offices", dept="command", L=12.0, D=16.0, h=3.4, plate="records",
     doors=[door("near", 6.0)], systems=["data_trunk"],
     spots=[spot("archivist", "work", 2.55, 9.6, 90, "command"), spot("archivist", "work", 5.25, 9.6, 90, "command"), spot("archivist", "sit", 10.2, 1.5, 90, "command")],
     lights=[light(6.0, 8.0, 3.3, 3600, 4200, (8.0, 12.0), 900)])
_reg("vls_magazine", name="VLS Magazine", kind="magazine", dept="security", L=24.0, D=16.0, h=3.6, plate="vls",
     doors=[door("near", 10.0)], systems=["weapons", "ordnance", "power_bus"],
     spots=[spot("loader", "work", 12.0, 10.8, 90, "security"), spot("loader", "work", 12.0, 5.0, 90, "security"), spot("loader", "sit", 21.6, 1.7, 90, "security")],
     lights=[light(8.0, 8.0, 3.5, 4500, 5000, (10.0, 10.0), 1000), light(18.0, 8.0, 3.5, 4500, 5000, (10.0, 10.0), 1000)])
_reg("point_defense", name="Point-Defence Control", kind="weapons_control", dept="security", L=16.0, D=16.0, h=3.6, plate="pdc",
     doors=[door("near", 6.0)], systems=["weapons", "sensors", "power_bus"],
     spots=[spot("gunner", "sit", x, 9.95, 90, "security") for x in (3.2, 6.4, 9.6, 12.8)] + [spot("gunnery_chief", "sit", 8.0, 4.95, 90, "security")],
     lights=[light(8.0, 8.0, 3.5, 4500, 6000, (12.0, 10.0), 1000)])
_reg("barbette", name="Turret Barbette", kind="weapons", dept="security", L=24.0, D=16.0, h=3.6, plate="barbette",
     doors=[door("near", 10.0)], systems=["weapons", "power_bus", "ordnance"],
     spots=[spot("gunner", "work", 21.8, 8.4, 180, "security"), spot("gunner", "work", 12.2, 5.4, 0, "security"), spot("gunner", "work", 5.8, 6.6, 90, "security"),
            spot("gunner", "sit", 10.5, 1.5, 90, "security")],
     lights=[light(6.0, 8.0, 3.5, 4000, 5000, (8.0, 10.0), 1000), light(17.0, 8.4, 3.5, 4500, 5000, (6.0, 6.0), 1000)])


# ---- Deck 3: the officers' deck (clear height 3.4) -----------------------------------------------------------------------------------------------------------
STATEROOM_Y = (0.61, 4.61, 8.61, 12.61)                                    # the beds' middle across a side's four staterooms (ship_rooms_quarters.STATEROOM_BED_Y)

_reg("staterooms", name="Officers' Staterooms", kind="cabins", dept="services", L=20.0, D=16.0, h=3.2, plate="staterooms",
     doors=[door("near", 10.0)], systems=["power_bus", "life_support"],
     spots=[spot("officer", "sleep", 1.39, y, 180, "services") for y in STATEROOM_Y] + [spot("officer", "sleep", 18.61, y, 0, "services") for y in STATEROOM_Y],
     lights=[light(10.0, 8.0, 3.1, 2500, 3400, (14.0, 0.6))] + [light(xc, yc, 3.0, 900, 3400, (1.4, 1.4), 480) for xc in (2.6, 17.4) for yc in (2.0, 6.0, 10.0, 14.0)])
_reg("wardroom", name="Officers' Wardroom", kind="wardroom", dept="command", L=24.0, D=16.0, h=3.6, plate="wardroom",
     doors=[door("near", 10.0)], systems=["power_bus"],
     spots=[spot("officer", "eat", 6.4 - 1.65 + k * 1.1, y - 0.95, 90, "command") for y in (4.4, 10.8) for k in range(4)]
           + [spot("officer", "eat", 6.4 - 1.65 + k * 1.1, y + 0.95, -90, "command") for y in (4.4, 10.8) for k in range(4)]
           + [spot("officer", "sit", 14.9, 4.6, 0, "command"), spot("officer", "sit", 14.9, 11.4, 0, "command"), spot("steward", "work", 21.4, 8.0, 0, "services")],
     lights=[light(7.0, 7.5, 3.5, 3600, 3400, (12.0, 12.0), 1000), light(17.0, 8.0, 3.5, 3000, 3200, (10.0, 12.0), 1000)])
_reg("gym", name="Gymnasium", kind="gym", dept="services", L=24.0, D=16.0, h=3.7, plate="gym",
     doors=[door("near", 10.0)], systems=["power_bus", "life_support"],
     spots=[spot("crew", "work", x, 14.4, 90, "services", 0.235) for x in (3.0, 5.4, 7.8, 10.2, 12.6)] + [spot("crew", "work", 7.6, 7.0, 0, "services"), spot("crew", "work", 21.52, 7.71, 180, "services")],
     lights=[light(12.0, 8.0, 3.6, 5000, 5200, (16.0, 8.0), 1100)])


# ---- Deck 12: the keel (clear height 3.4) ---------------------------------------------------------------------------------------------------------------------
_reg("tank", name="Fuel & Coolant Tank", kind="tank", dept="neutral", L=32.0, D=16.0, h=3.4, plate="tank",
     doors=[door("near", 14.0)], systems=["coolant", "fuel"],
     spots=[spot("machinist", "work", 17.9, 5.0, 180, "engineering"), spot("machinist", "work", 14.1, 11.0, 0, "engineering"), spot("machinist", "stand", 13.0, 8.0, 0, "engineering")],
     lights=[light(7.0, 8.0, 3.3, 3500, 4200, (11.0, 3.0), 900), light(25.0, 8.0, 3.3, 3500, 4200, (11.0, 3.0), 900), light(16.0, 8.0, 3.3, 4200, 4500, (5.0, 12.0), 900)])
_reg("reaction_mass", name="Reaction-Mass Tank", kind="tank", dept="neutral", L=40.0, D=16.0, h=3.4, plate="mass",
     doors=[door("near", 18.0)], systems=["reaction_mass"],
     spots=[spot("machinist", "work", 21.5, 5.0, 180, "engineering"), spot("machinist", "work", 18.5, 12.5, 0, "engineering"), spot("machinist", "sit", 22.0, 1.5, 90, "engineering")],
     lights=[light(9.0, 8.5, 3.3, 4000, 4800, (10.0, 6.0), 1000), light(31.0, 8.5, 3.3, 4000, 4800, (10.0, 6.0), 1000), light(20.0, 8.0, 3.3, 3500, 4800, (10.0, 8.0), 900)])
_reg("crawlway", name="Maintenance Crawlway Hub", kind="crawlway", dept="engineering", L=16.0, D=16.0, h=3.0, plate="crawl",
     doors=[door("near", 6.0)], systems=["power_bus", "data_trunk", "coolant"],
     spots=[spot("dc_technician", "sit", 4.0, 15.3, -90, "engineering"), spot("dc_technician", "work", 11.0, 8.0, 90, "engineering")],
     lights=[light(8.0, 8.0, 2.9, 3200, 3000, (10.0, 10.0), 800)])



# ---- Deck 1: the Captain's ready room (hand-placed between the two corridors of the bridge complex, ship_deck1.py; clear height 2.9, as the corridors' roofs are 3.2) ----------
_reg("ready_room", name="Ready Room", kind="ready_room", dept="command", L=12.0, D=4.2, h=2.9, plate="ready_room",
     doors=[door("near", 5.0, 1.4, 2.2)], systems=["power_bus", "comms"],
     spots=[spot("officer", "sit", 3.50, 1.75, 180, "command"), spot("officer", "sit", 3.50, 2.75, 180, "command"),
            spot("officer", "sit", 7.60, 3.45, -90, "command"), spot("officer", "sit", 9.00, 3.45, -90, "command"), spot("officer", "sit", 6.95, 2.45, 0, "command"),
            spot("officer", "stand", 9.10, 1.60, 0, "command"), spot("officer", "stand", 10.45, 0.85, 90, "command"), spot("officer", "stand", 10.45, 3.15, -90, "command"),
            spot("officer", "stand", 4.85, 3.20, 90, "command")],
     lights=[light(2.3, 2.0, 2.75, 2400, 3300, (3.0, 1.2), 650), light(5.4, 2.0, 2.75, 2000, 3400, (2.0, 1.2), 600), light(8.2, 2.0, 2.75, 2400, 3300, (3.0, 1.4), 650),
             light(10.45, 2.0, 2.75, 2000, 5600, (2.0, 2.0), 600)])


def prefab(key: str) -> dict:
    return PREFABS[key]


def door_world_offsets(key: str) -> list[float]:
    return [d["x"] for d in PREFABS[key]["doors"] if d["wall"] == "near"]
