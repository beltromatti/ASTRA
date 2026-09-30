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


def spot(role: str, kind: str, x: float, y: float, yaw: float, dept: str = "services") -> dict:
    return {"role": role, "kind": kind, "x": x, "y": y, "yaw": yaw, "dept": dept}


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
     spots=[spot("cook", "work", 8.0, 15.9, 90), spot("cook", "work", 11.0, 15.9, 90), spot("cook", "work", 14.0, 15.9, 90),
            spot("cook", "work", 17.0, 15.9, 90), spot("cook", "work", 9.0, 8.2, 90), spot("steward", "work", 13.0, 8.2, 90),
            spot("dishwasher", "work", 21.5, 5.5, 0), spot("chief_cook", "stand", 13.0, 3.2, 90)],
     lights=[light(8.0, 6.0, 3.5, 7000, 5000, (7.0, 0.9)), light(17.0, 6.0, 3.5, 7000, 5000, (7.0, 0.9)),
             light(12.0, 12.5, 3.5, 9000, 4800, (16.0, 0.9)), light(3.0, 9.0, 3.5, 3000, 4200, (2.0, 8.0))])
_reg("galley_pass", name="Galley Pass", kind="galley", dept="services", L=24.0, D=4.0, h=3.4, plate="galley",
     doors=[door("near", 10.0)], systems=["food_service", "dumbwaiter"],
     spots=[spot("steward", "work", 8.0, 2.0, 90), spot("steward", "work", 14.0, 2.0, 90)],
     lights=[light(12.0, 2.0, 3.3, 3500, 4800, (14.0, 0.5))])
_reg("lounge", name="Crew Lounge", kind="lounge", dept="services", L=24.0, D=16.0, h=3.6, plate="lounge",
     doors=[door("near", 10.0), door("far", 14.0)], systems=["power_bus", "entertainment"],
     spots=[spot("crew", "sit", 4.0, 4.0, 45), spot("crew", "sit", 4.0, 6.5, -45), spot("crew", "sit", 7.6, 5.2, 180),
            spot("crew", "sit", 4.0, 11.5, 45), spot("crew", "sit", 4.0, 14.0, -45), spot("crew", "sit", 7.6, 12.6, 180),
            spot("crew", "sit", 14.5, 4.0, 90), spot("crew", "sit", 17.5, 4.0, 90), spot("crew", "sit", 20.0, 4.6, 180),
            spot("crew", "eat", 19.0, 12.8, 0), spot("crew", "sit", 21.4, 10.0, 180), spot("crew", "sit", 21.4, 12.0, 180)],
     lights=[light(6.0, 8.0, 3.5, 5200, 3200, (8.0, 8.0)), light(18.0, 5.0, 3.5, 4200, 3400, (8.0, 3.0)),
             light(18.0, 12.0, 3.5, 4200, 3400, (8.0, 3.0))])
_reg("games", name="Games Room", kind="lounge", dept="services", L=24.0, D=16.0, h=3.6, plate="games",
     doors=[door("near", 10.0), door("far", 14.0)], systems=["power_bus", "entertainment"],
     spots=[spot("crew", "sit", 5.0, 5.0, 0), spot("crew", "sit", 7.0, 5.0, 180), spot("crew", "sit", 5.0, 11.0, 0), spot("crew", "sit", 7.0, 11.0, 180),
            spot("crew", "sit", 12.0, 4.0, 0), spot("crew", "sit", 14.0, 4.0, 180), spot("crew", "stand", 19.0, 12.0, 90),
            spot("crew", "stand", 21.0, 12.0, 90)],
     lights=[light(6.0, 8.0, 3.5, 4500, 4000, (8.0, 8.0)), light(18.0, 8.0, 3.5, 4500, 3600, (8.0, 8.0))])
_reg("library", name="Library", kind="library", dept="services", L=16.0, D=16.0, h=3.6, plate="library",
     doors=[door("near", 6.0)], systems=["power_bus"],
     spots=[spot("crew", "sit", 5.0, 8.0, 90), spot("crew", "sit", 8.0, 8.0, 90), spot("crew", "sit", 11.5, 5.0, 180),
            spot("librarian", "work", 13.0, 3.0, 0)],
     lights=[light(8.0, 8.0, 3.5, 4500, 3300, (8.0, 8.0))])
_reg("observation", name="Observation Deck", kind="observation", dept="command", L=24.0, D=16.0, h=3.7, plate="observation",
     doors=[door("near", 10.0)], systems=["power_bus"],
     spots=[spot("crew", "watch", 5.0, 14.0, 90), spot("crew", "watch", 8.0, 14.0, 90), spot("crew", "watch", 11.0, 14.0, 90),
            spot("crew", "watch", 14.0, 14.0, 90), spot("crew", "watch", 17.0, 14.0, 90), spot("crew", "watch", 20.0, 14.0, 90),
            spot("crew", "sit", 6.0, 7.0, 0), spot("crew", "sit", 18.0, 7.0, 180)],
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
     spots=[spot("botanist", "work", 8.0, 8.0, 0, "science"), spot("botanist", "work", 16.0, 8.0, 180, "science")],
     lights=[light(12.0, 8.0, 3.3, 3500, 7000, (20.0, 12.0), 1100)])
_reg("quiet", name="Quiet Room", kind="chapel", dept="services", L=12.0, D=16.0, h=3.6, plate="chapel",
     doors=[door("near", 6.0)], systems=["power_bus"],
     spots=[spot("crew", "sit", 4.0, 9.0, 0), spot("crew", "sit", 8.0, 9.0, 180), spot("crew", "sit", 6.0, 12.0, 90)],
     lights=[light(6.0, 8.0, 3.5, 1500, 2700, (5.0, 5.0))])
# ---- the rest of the kit (Decks 3, 5, 8, 10, 11 of the canon): built and previewed, placed when their decks are built -------
_reg("lab", name="Science Lab", kind="lab", dept="science", L=24.0, D=16.0, h=3.6, plate="lab",
     doors=[door("near", 10.0)], systems=["sensors", "power_bus", "data_trunk"],
     spots=[spot("scientist", "work", 5.0, 13.0, 90, "science"), spot("scientist", "work", 9.0, 13.0, 90, "science"),
            spot("scientist", "work", 13.0, 13.0, 90, "science"), spot("scientist", "work", 17.0, 13.0, 90, "science"),
            spot("scientist", "work", 8.5, 7.5, 0, "science"), spot("lead_scientist", "work", 19.0, 6.0, 180, "science")],
     lights=[light(6.0, 8.0, 3.5, 6500, 5600, (8.0, 8.0)), light(18.0, 8.0, 3.5, 6500, 5600, (8.0, 8.0))])
_reg("workshop", name="Machine Shop", kind="workshop", dept="engineering", L=28.0, D=16.0, h=3.7, plate="workshop",
     doors=[door("near", 10.0)], systems=["power_bus", "compressed_air", "damage_control"],
     spots=[spot("machinist", "work", 7.0, 8.0, 90, "engineering"), spot("machinist", "work", 12.0, 8.0, 90, "engineering"),
            spot("welder", "work", 22.0, 12.0, 0, "engineering"), spot("fitter", "work", 17.0, 15.5, 90, "engineering")],
     lights=[light(9.0, 9.0, 3.7, 7000, 4800, (12.0, 1.0)), light(21.0, 9.0, 3.7, 7000, 4800, (12.0, 1.0)),
             light(14.0, 15.0, 3.7, 5000, 5200, (20.0, 0.8))])
_reg("armory", name="Armory", kind="armory", dept="security", L=16.0, D=16.0, h=3.4, plate="armory",
     doors=[door("near", 6.0)], systems=["ordnance", "power_bus"],
     spots=[spot("armorer", "work", 5.0, 3.4, 0, "security"), spot("guard", "stand", 9.0, 2.2, 90, "security")],
     lights=[light(8.0, 6.0, 3.3, 5500, 5000, (10.0, 1.0)), light(8.0, 12.0, 3.3, 5500, 5000, (10.0, 1.0))])
_reg("cabins", name="Crew Cabins", kind="cabins", dept="services", L=20.0, D=16.0, h=3.2, plate="cabins",
     doors=[door("near", 10.0)], systems=["power_bus", "life_support"],
     spots=[spot("sleeper", "sleep", 2.2 + 3.3 * i, 3.0 + 6.4, 90) for i in range(4)],
     lights=[light(10.0, 8.0, 3.1, 2500, 3400, (14.0, 0.6))])
# ---- specials (their own frames: see ship_rooms.py): concourse, stair tower, bow observation ---------------------------------
_reg("concourse", name="Mess Concourse", kind="concourse", dept="services", L=17.7, D=36.0, h=3.8, plate="concourse", doors=[],
     systems=["power_bus", "life_support"], special=True,
     spots=[spot("crew", "stand", 5.0, 10.0, 90), spot("crew", "sit", 8.0, 16.0, 0), spot("crew", "sit", 8.0, 20.0, 0),
            spot("crew", "stand", 14.0, 27.0, 180), spot("crew", "sit", 8.0, 24.0, 0), spot("crew", "sit", 8.0, 12.0, 180)],
     lights=[light(9.0, 18.0, 3.7, 9000, 4200, (10.0, 2.0), 1400), light(9.0, 8.0, 3.7, 5000, 3600, (6.0, 2.0), 1100),
             light(9.0, 28.0, 3.7, 5000, 3600, (6.0, 2.0), 1100)])
_reg("berth_lobby", name="Berthing Lobby", kind="concourse", dept="services", L=14.6, D=36.0, h=3.6, plate=None, doors=[],
     systems=["power_bus", "life_support"], special=True,
     spots=[spot("crew", "sit", 4.0, 9.0, 0), spot("crew", "stand", 9.0, 24.0, 180)],
     lights=[light(7.3, 18.0, 3.5, 4500, 3600, (8.0, 3.0), 1200), light(7.3, 8.0, 3.5, 2500, 3200, (5.0, 2.0), 900),
             light(7.3, 28.0, 3.5, 2500, 3200, (5.0, 2.0), 900)])
_reg("stair_tower", name="Stair Tower", kind="stairs", dept="neutral", L=8.0, D=8.0, h=3.4, plate="stairs", doors=[door("near", 2.0)],
     systems=["power_bus"], special=True, spots=[], lights=[light(4.0, 4.0, 3.3, 3000, 4500, (3.0, 3.0), 800)])
_reg("bow_obs", name="Bow Observation", kind="observation", dept="command", L=20.0, D=32.0, h=3.8, plate="bow_obs", doors=[],
     systems=["power_bus"], special=True,
     spots=[spot("crew", "watch", 4.0 + 3.0 * i, 26.0, 90) for i in range(5)] + [spot("crew", "sit", 6.0, 12.0, 90)],
     lights=[light(10.0, 16.0, 3.7, 3200, 6200, (12.0, 1.0), 1200)])


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
_plan("surgery", "Surgery", "surgery", "medical", 16.0, 16.0, 3.6, ["medical", "power_bus"], ("surgeon", "nurse"), 3, 6.0, lm=6500, temp=6000)
_plan("quarantine", "Quarantine Ward", "quarantine", "medical", 24.0, 16.0, 3.6, ["medical", "life_support"], ("nurse",), 3, 10.0)
_plan("pharmacy", "Pharmacy", "pharmacy", "medical", 12.0, 16.0, 3.4, ["medical", "supply"], ("pharmacist",), 1, 6.0)
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


def prefab(key: str) -> dict:
    return PREFABS[key]


def door_world_offsets(key: str) -> list[float]:
    return [d["x"] for d in PREFABS[key]["doors"] if d["wall"] == "near"]
