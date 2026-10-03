"""ASN Aquila interior kit (NAVE-3): the specification of the rooms the redesign adds — the medical complex's dentist, morgue and counselling office, the brig and the security
office, the life-support plants, the two computer cores, the auxiliary power plant, damage-control central, the crew's berthing bays, the senior officers' suites and the single
cabins, the chapel, the bar, the barber, the ship's store and the simulator bay, the drone bay, the hull airlock and the lifepod bay. Same conventions as ship_spec.py (the frame of
a prefab: origin on the floor at the corridor-side corner, x along the corridor, y into the room; the spots and the lamps are in it, the plan and the meshes read the same numbers).

Imported at the end of ship_spec.py.
"""
from __future__ import annotations

from ship_spec import _reg, door, light, spot


# ---- the medical complex (Deck 6) -------------------------------------------------------------------------------------------------------------------------------------------
_reg("dentist", name="Dental Clinic", kind="dental", dept="medical", L=12.0, D=16.0, h=3.4, plate="dentist",
     doors=[door("near", 6.0)], systems=["medical", "power_bus", "potable_water"],
     spots=[spot("dentist", "sit", 3.0, 7.5, 90, "medical"), spot("dental_hygienist", "sit", 9.0, 7.5, 90, "medical"), spot("patient", "sit", 3.0, 9.45, 90, "medical"),
            spot("patient", "sit", 9.0, 9.45, 90, "medical"), spot("receptionist", "sit", 9.75, 2.6, 180, "medical"), spot("dental_technician", "work", 10.2, 13.2, 180, "medical")],
     lights=[light(6.0, 4.0, 3.3, 3200, 5200, (6.0, 2.0), 800), light(6.0, 9.5, 3.3, 5200, 5600, (8.0, 6.0), 900), light(6.0, 14.0, 3.3, 2600, 5000, (8.0, 1.0), 700)])
_reg("morgue", name="Morgue", kind="morgue", dept="medical", L=12.0, D=16.0, h=3.4, plate="morgue",
     doors=[door("near", 6.0)], systems=["medical", "cold_chain", "power_bus"],
     spots=[spot("pathologist", "work", 6.0, 8.6, 90, "medical"), spot("morgue_attendant", "stand", 9.8, 3.0, 90, "medical")],
     lights=[light(6.0, 5.0, 3.3, 3600, 6200, (6.0, 2.0), 800), light(6.0, 11.0, 3.3, 4200, 6400, (8.0, 3.0), 900)])
_reg("counselling", name="Counselling & Chaplaincy", kind="counselling", dept="medical", L=12.0, D=16.0, h=3.4, plate="counselling",
     doors=[door("near", 6.0)], systems=["medical", "power_bus"],
     spots=[spot("counsellor", "sit", 3.4, 13.55, -90, "medical"), spot("crew", "sit", 3.4, 11.65, 90, "services"), spot("chaplain", "sit", 10.95, 12.4, 180, "medical"),
            spot("crew", "sit", 9.45, 12.4, 0, "services"), spot("crew", "sit", 3.91, 6.95, -90, "services"), spot("crew", "sit", 5.29, 6.95, -90, "services"),
            spot("crew", "sit", 2.55, 5.0, 0, "services"), spot("crew", "sit", 6.65, 5.0, 180, "services")],
     lights=[light(6.0, 4.0, 3.3, 2200, 3000, (6.0, 4.0), 800), light(6.0, 11.0, 3.3, 2200, 3000, (8.0, 4.0), 800)])
# ---- security (Deck 8) ------------------------------------------------------------------------------------------------------------------------------------------------------
_reg("brig", name="Brig", kind="brig", dept="security", L=24.0, D=16.0, h=3.4, plate="brig",
     doors=[door("near", 10.0)], systems=["power_bus", "life_support", "containment"],
     spots=[spot("marine", "stand", 10.0, 3.0, 90, "security"), spot("sergeant", "sit", 21.4, 8.6, 180, "security"), spot("marine", "stand", 12.0, 9.0, 0, "security"),
            spot("prisoner", "sit", 5.15, 14.5, -90, "security"), spot("prisoner", "sit", 12.15, 14.5, -90, "security"), spot("marine", "sit", 1.25, 2.6, 0, "security")],
     lights=[light(8.0, 4.0, 3.3, 4200, 4800, (8.0, 2.0), 900), light(12.0, 9.0, 3.3, 3600, 4600, (14.0, 2.0), 900), light(12.0, 14.0, 3.3, 2400, 4200, (20.0, 1.0), 800)])
_reg("security_office", name="Security Office", kind="security", dept="security", L=16.0, D=16.0, h=3.4, plate="security",
     doors=[door("near", 6.0)], systems=["power_bus", "data_trunk", "ordnance"],
     spots=[spot("duty_marine", "sit", 3.0, 3.15, -90, "security"), spot("watch_commander", "sit", 12.4, 13.55, -90, "security"), spot("marine", "sit", 8.0, 8.15, 90, "security"),
            spot("marine", "sit", 11.0, 8.15, 90, "security"), spot("military_police", "work", 12.4, 5.0, 180, "security")],
     lights=[light(8.0, 5.0, 3.3, 4200, 4800, (10.0, 3.0), 900), light(8.0, 12.0, 3.3, 3200, 4600, (10.0, 3.0), 900)])
# ---- engineering and life support (Decks 5-8, 10-12) --------------------------------------------------------------------------------------------------------------------------
_reg("air_plant", name="Atmosphere Plant", kind="machinery", dept="engineering", L=24.0, D=16.0, h=3.7, plate="air_plant",
     doors=[door("near", 10.0)], systems=["life_support", "power_bus", "compressed_air", "coolant"],
     spots=[spot("air_plant_technician", "work", 5.0, 11.0, 90, "engineering"), spot("air_plant_technician", "work", 12.85, 9.0, 0, "engineering"),
            spot("machinist", "stand", 19.0, 5.0, 90, "engineering"), spot("air_plant_technician", "sit", 22.4, 3.0, 0, "engineering")],
     lights=[light(8.0, 8.0, 3.6, 5000, 4800, (12.0, 1.0), 1000), light(18.0, 8.0, 3.6, 4500, 4800, (8.0, 1.0), 1000)])
_reg("water_plant", name="Water Reclamation Plant", kind="machinery", dept="engineering", L=24.0, D=16.0, h=3.7, plate="water_plant",
     doors=[door("near", 10.0)], systems=["life_support", "potable_water", "power_bus"],
     spots=[spot("water_tender", "work", 6.0, 9.0, 90, "engineering"), spot("water_tender", "work", 14.0, 8.0, 0, "engineering"), spot("machinist", "stand", 19.5, 4.2, 90, "engineering"),
            spot("water_tender", "sit", 22.4, 3.0, 0, "engineering")],
     lights=[light(8.0, 8.0, 3.6, 5000, 5200, (12.0, 1.0), 1000), light(18.0, 8.0, 3.6, 4500, 5200, (8.0, 1.0), 1000)])
_reg("waste_plant", name="Waste Processing Plant", kind="machinery", dept="engineering", L=24.0, D=16.0, h=3.7, plate="waste_plant",
     doors=[door("near", 10.0)], systems=["life_support", "waste", "power_bus", "compressed_air"],
     spots=[spot("recycling_hand", "work", 6.0, 9.0, 90, "engineering"), spot("recycling_hand", "work", 15.0, 9.0, 0, "engineering"), spot("machinist", "stand", 20.0, 4.4, 90, "engineering")],
     lights=[light(8.0, 8.0, 3.6, 5000, 4600, (12.0, 1.0), 1000), light(18.0, 8.0, 3.6, 4500, 4600, (8.0, 1.0), 1000)])
_reg("computer_core", name="Computer Core", kind="computer", dept="science", L=24.0, D=16.0, h=3.7, plate="computer_core",
     doors=[door("near", 10.0)], systems=["data_trunk", "power_bus", "coolant", "sensors"],
     spots=[spot("core_technician", "work", 7.3, 8.0, 90, "science"), spot("core_technician", "work", 15.86, 8.06, 90, "science"), spot("systems_officer", "sit", 22.25, 3.4, 0, "science")],
     lights=[light(8.0, 8.0, 3.6, 3200, 6800, (12.0, 1.0), 900), light(18.0, 8.0, 3.6, 3200, 6800, (8.0, 1.0), 900)])
_reg("aux_reactor", name="Auxiliary Power Plant", kind="power", dept="engineering", L=32.0, D=16.0, h=3.7, plate="aux_reactor",
     doors=[door("near", 14.0)], systems=["reactor", "power_bus", "coolant"],
     spots=[spot("power_technician", "work", 8.0, 6.0, 90, "engineering"), spot("power_technician", "work", 22.0, 6.0, 90, "engineering"), spot("power_supervisor", "sit", 30.25, 3.0, 0, "engineering"),
            spot("reactor_hand", "stand", 16.0, 11.0, 0, "engineering")],
     lights=[light(10.0, 8.0, 3.6, 5200, 4600, (12.0, 1.0), 1100), light(22.0, 8.0, 3.6, 5200, 4600, (12.0, 1.0), 1100)])
_reg("dc_central", name="Damage-Control Central", kind="damage_control", dept="engineering", L=24.0, D=16.0, h=3.6, plate="dc_central",
     doors=[door("near", 10.0)], systems=["damage_control", "data_trunk", "power_bus", "supply"],
     spots=[spot("dc_officer", "sit", 12.0, 8.9, -90, "engineering"), spot("dc_technician", "sit", 9.45, 7.4, 0, "engineering"), spot("dc_technician", "sit", 14.55, 7.4, 180, "engineering"),
            spot("dc_technician", "stand", 1.75, 4.4, 180, "engineering"), spot("dc_technician", "stand", 22.25, 7.8, 0, "engineering")],
     lights=[light(8.0, 8.0, 3.5, 4200, 5000, (10.0, 4.0), 1000), light(18.0, 8.0, 3.5, 4200, 5000, (8.0, 4.0), 1000)])
# ---- recreation, the shops, the chapel (Decks 3, 4) -------------------------------------------------------------------------------------------------------------------------
_reg("barber", name="Barber & Tailor", kind="shop", dept="services", L=12.0, D=16.0, h=3.4, plate="barber",
     doors=[door("near", 6.0)], systems=["power_bus", "potable_water"],
     spots=[spot("barber", "work", 3.0, 3.7, -90, "services"), spot("barber", "work", 9.0, 3.7, -90, "services"), spot("crew", "sit", 3.0, 2.85, -90, "services"),
            spot("crew", "sit", 9.0, 2.85, -90, "services"), spot("crew", "sit", 11.3, 7.0, 180, "services"), spot("crew", "sit", 11.3, 8.8, 180, "services"),
            spot("tailor", "sit", 3.0, 12.25, 90, "services"), spot("tailor", "work", 7.0, 11.1, 90, "services")],
     lights=[light(6.0, 5.0, 3.3, 3600, 3600, (8.0, 3.0), 800), light(6.0, 12.0, 3.3, 3600, 3600, (8.0, 3.0), 800)])
_reg("bar", name="Crew Bar", kind="lounge", dept="services", L=24.0, D=16.0, h=3.6, plate="bar",
     doors=[door("near", 10.0)], systems=["power_bus", "entertainment", "potable_water"],
     spots=[spot("bartender", "work", 18.4, 14.3, -90, "services"), spot("crew", "sit", 15.9, 11.95, 90, "services"), spot("crew", "sit", 17.2, 11.95, 90, "services"),
            spot("crew", "sit", 18.5, 11.95, 90, "services"), spot("crew", "sit", 19.8, 11.95, 90, "services"), spot("crew", "sit", 21.1, 11.95, 90, "services"),
            spot("crew", "sit", 2.55, 4.2, 0, "services"), spot("crew", "sit", 4.25, 4.2, 180, "services"), spot("crew", "sit", 2.55, 8.6, 0, "services"), spot("crew", "sit", 4.25, 8.6, 180, "services"),
            spot("crew", "eat", 8.2, 3.5, 90, "services"), spot("crew", "eat", 8.2, 4.9, -90, "services"), spot("crew", "eat", 7.35, 8.6, 0, "services"), spot("crew", "eat", 9.05, 8.6, 180, "services"),
            spot("crew", "stand", 12.0, 9.0, 180, "services")],
     lights=[light(6.0, 6.0, 3.5, 3600, 2800, (8.0, 6.0), 1000), light(18.0, 11.0, 3.5, 4200, 2900, (8.0, 2.0), 1000)])
_reg("chapel", name="Chapel", kind="chapel", dept="services", L=16.0, D=16.0, h=3.7, plate="chapel_nave",
     doors=[door("near", 6.0)], systems=["power_bus"],
     spots=[spot("crew", "sit", 4.0, 5.75, 90), spot("crew", "sit", 4.8, 5.75, 90), spot("crew", "sit", 5.6, 5.75, 90), spot("crew", "sit", 4.4, 8.75, 90), spot("crew", "sit", 5.2, 8.75, 90),
            spot("crew", "sit", 10.4, 5.75, 90), spot("crew", "sit", 11.2, 5.75, 90), spot("crew", "sit", 12.0, 5.75, 90), spot("crew", "sit", 11.6, 8.75, 90),
            spot("chaplain", "stand", 8.0, 12.9, -90, "medical")],
     lights=[light(8.0, 8.0, 3.6, 2600, 2700, (6.0, 6.0), 900), light(8.0, 14.0, 3.6, 2600, 3000, (6.0, 1.0), 800), light(8.0, 3.0, 3.6, 1400, 2800, (8.0, 1.0), 700)])
_reg("shop", name="Ship's Store", kind="shop", dept="services", L=16.0, D=16.0, h=3.4, plate="shop",
     doors=[door("near", 6.0)], systems=["power_bus", "supply"],
     spots=[spot("storekeeper", "sit", 12.95, 3.6, 180, "services"), spot("crew", "stand", 7.0, 9.1, -90), spot("crew", "stand", 7.0, 6.9, 90), spot("crew", "stand", 9.0, 9.4, 180)],
     lights=[light(8.0, 5.0, 3.3, 4200, 4200, (10.0, 3.0), 900), light(8.0, 11.0, 3.3, 4200, 4200, (10.0, 3.0), 900)])
_reg("sim_bay", name="Simulator Bay", kind="simulator", dept="flight", L=24.0, D=16.0, h=3.7, plate="sim_bay",
     doors=[door("near", 10.0)], systems=["power_bus", "data_trunk", "entertainment"],
     spots=[spot("simulator_operator", "sit", 22.4, 4.0, 0, "flight"), spot("pilot", "sit", 4.0, 8.1, 90, "flight", 0.4), spot("pilot", "sit", 8.2, 8.1, 90, "flight", 0.4),
            spot("pilot", "sit", 12.4, 8.1, 90, "flight", 0.4), spot("pilot", "sit", 16.6, 8.1, 90, "flight", 0.4), spot("crew", "stand", 18.0, 7.0, 90)],
     lights=[light(8.0, 8.0, 3.6, 2200, 5600, (12.0, 4.0), 900), light(18.0, 8.0, 3.6, 3200, 5200, (8.0, 6.0), 900)])
# the berthing bay's bunks (ship_rooms_life.berthing places them at yaw 90: head at the near-wall end, so the sleeper lies with the head towards -y): columns across the room (a 3 m
# aisle in the middle, where the table is) and the two rows; every bunk is two places, the lower at the mattress (0.60 m above the station) and the upper 0.96 m higher
BERTH_X = (1.8, 4.6, 7.4, 12.6, 15.4, 18.2, 21.0)
BERTH_Y = (4.4, 9.6)
# ---- quarters ------------------------------------------------------------------------------------------------------------------------------------------------------------------
_reg("berthing", name="Crew Berthing Bay", kind="cabins", dept="services", L=24.0, D=16.0, h=3.4, plate="berthing_bay",
     doors=[door("near", 10.0)], systems=["power_bus", "life_support"],
     spots=[spot("sleeper", "sleep", x, y, -90, "services", dz) for x in BERTH_X for y in BERTH_Y for dz in (0.0, 0.96)],
     lights=[light(6.0, 4.0, 3.2, 1500, 3000, (10.0, 0.6), 600), light(18.0, 4.0, 3.2, 1500, 3000, (8.0, 0.6), 600), light(6.0, 12.0, 3.2, 1500, 3000, (10.0, 0.6), 600),
             light(18.0, 12.0, 3.2, 1500, 3000, (8.0, 0.6), 600)])
_reg("suites", name="Senior Officers' Quarters", kind="cabins", dept="command", L=24.0, D=12.0, h=3.2, plate="suites",
     doors=[door("near", 10.0)], systems=["power_bus", "life_support"],
     spots=[spot("officer", "sleep", 2.6 + 6.0 * k, 9.0, 90, "command") for k in range(4)] + [spot("officer", "sit", 3.4 + 6.0 * k, 5.0, 90, "command") for k in range(4)],
     lights=[light(3.0, 6.0, 3.1, 1100, 3200, (4.0, 3.0), 500), light(9.0, 6.0, 3.1, 1100, 3200, (4.0, 3.0), 500), light(15.0, 6.0, 3.1, 1100, 3200, (4.0, 3.0), 500),
             light(21.0, 6.0, 3.1, 1100, 3200, (4.0, 3.0), 500), light(12.0, 1.4, 3.1, 900, 3600, (20.0, 0.6), 500)])
_reg("single_cabins", name="Officers' Cabins", kind="cabins", dept="services", L=24.0, D=4.0, h=3.2, plate="cabins_row",
     doors=[door("near", 10.0)], systems=["power_bus", "life_support"],
     spots=[spot("officer", "sleep", 2.0 + 4.0 * k, 2.4, 90, "services") for k in range(6)],
     lights=[light(4.0, 2.0, 3.1, 1000, 3200, (6.0, 0.6), 500), light(12.0, 2.0, 3.1, 1000, 3200, (6.0, 0.6), 500), light(20.0, 2.0, 3.1, 1000, 3200, (6.0, 0.6), 500)])

# ---- flight (Deck 9) -------------------------------------------------------------------------------------------------------------------------------------------------------------
_reg("drone_bay", name="Drone Bay", kind="hangar", dept="flight", L=32.0, D=16.0, h=3.7, plate="drone_bay",
     doors=[door("near", 14.0)], systems=["power_bus", "launch_tubes", "life_support"],
     spots=[spot("drone_technician", "work", 8.8, 8.0, 90, "flight"), spot("drone_technician", "work", 24.8, 8.0, 90, "flight"), spot("deck_hand", "stand", 16.0, 12.0, 90, "flight"),
            spot("drone_technician", "sit", 30.3, 2.4, 0, "flight")],
     lights=[light(10.0, 8.0, 3.6, 5200, 5400, (12.0, 6.0), 1100), light(24.0, 8.0, 3.6, 5200, 5400, (12.0, 6.0), 1100)])
# ---- the hull's galleries (decks 5-12: service corridors 2.7 m high; the rooms are 8 x 4 m on their outboard side) ----------------------------------------------------------------
_reg("airlock", name="EVA Airlock", kind="airlock", dept="engineering", L=8.0, D=4.0, h=2.7, plate="airlock",
     doors=[door("near", 2.0)], systems=["life_support", "power_bus"],
     spots=[spot("eva_technician", "stand", 2.2, 2.2, 0, "engineering")],
     lights=[light(2.0, 2.0, 2.6, 1400, 4500, (3.0, 1.4), 500), light(5.9, 2.0, 2.6, 1400, 5200, (2.0, 1.0), 500)])
_reg("pod_bay", name="Lifepod Bay", kind="lifepod", dept="neutral", L=8.0, D=4.0, h=2.7, plate="lifepods",
     doors=[door("near", 2.0)], systems=["life_support", "power_bus", "escape"],
     spots=[spot("crew", "stand", 1.5, 1.3, 90)],
     lights=[light(4.0, 1.4, 2.6, 1200, 3200, (6.0, 0.4), 500), light(4.0, 2.6, 2.6, 1200, 3200, (6.0, 0.4), 500)])
_reg("suit_locker", name="EVA Suit Lockers", kind="storage", dept="engineering", L=8.0, D=4.0, h=2.7, plate="suits",
     doors=[door("near", 2.0)], systems=["life_support", "supply"],
     spots=[spot("eva_technician", "stand", 4.0, 1.7, 90, "engineering")],
     lights=[light(2.0, 2.0, 2.6, 1400, 4200, (2.0, 1.4), 500), light(6.0, 2.0, 2.6, 1400, 4200, (2.0, 1.4), 500)])


# ---- small rooms: the 8 m and 12 m fillers of a lane and the half-depth rooms of the passage side (NAVE-3: right-sized rooms, not 16 m halls for a cupboard) ------------------------------
_reg("store_s", name="Section Stores", kind="storage", dept="flight", L=8.0, D=16.0, h=3.4, plate="stores_section",
     doors=[door("near", 2.0)], systems=["supply"],
     spots=[spot("storekeeper", "work", 5.0, 3.0, 90, "flight")],
     lights=[light(4.0, 5.0, 3.3, 3200, 4600, (6.0, 0.8), 800), light(4.0, 12.0, 3.3, 3200, 4600, (6.0, 0.8), 800)])
_reg("locker_s", name="Crew Lockers", kind="storage", dept="services", L=8.0, D=16.0, h=3.4, plate="lockers",
     doors=[door("near", 2.0)], systems=["supply"],
     spots=[spot("crew", "stand", 4.0, 3.0, 90), spot("crew", "stand", 6.0, 8.0, 180)],
     lights=[light(4.0, 5.0, 3.3, 3000, 4400, (6.0, 0.8), 800), light(4.0, 12.0, 3.3, 3000, 4400, (6.0, 0.8), 800)])
_reg("tech_s", name="Technical Space", kind="machinery", dept="engineering", L=8.0, D=16.0, h=3.4, plate="tech",
     doors=[door("near", 2.0)], systems=["power_bus", "data_trunk", "life_support"],
     spots=[spot("technician", "work", 4.0, 5.0, 90, "engineering")],
     lights=[light(4.0, 5.0, 3.3, 3200, 4600, (6.0, 0.8), 800), light(4.0, 12.0, 3.3, 3200, 4600, (6.0, 0.8), 800)])
