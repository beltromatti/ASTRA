"""ASTRA ships: the specs of the Mandate's Styx and Acheron and of ASTRA's Vigilant (FLOTTA-VIVA; see ship_class_specs.py for the format and the shared tables).
Positions are in the mesh's own frame; a key room asked where its row has no room moves to the nearest place (the generator says so in the plan's notes)."""
from __future__ import annotations

from ship_class_specs import ASTRA_NAMES, MANDATE_NAMES, RANKS_ASTRA, RANKS_MANDATE, K, finalize

# ======================================================================================================================== Styx
# Kharon Mandate destroyer, 387 m (x -212..175): a long spear of a bow (the spinal rail), swept armour sponsons, the tower and the stern block aft.
# 140 aboard, sixteen of them the Ferry Guard; a small bay for a flight of three Harpies in the waist.
STYX = dict(
    key="styx", style="mandate", label="Kharon Mandate destroyer, Styx class", wall=2.5, room_scale=1.5, names=MANDATE_NAMES,
    sections=[("A", 176.0, 30.0), ("B", 30.0, -78.0), ("C", -78.0, -140.0), ("D", -140.0, -213.0)],
    decks=[
        dict(id=1, name="Helm", programme="the Helm at the top of the stern block", z=16.0, clear=4.4, body=False, x=(-175.0, -60.0), layout="spine"),
        dict(id=2, name="Gun Deck", programme="the dorsal rail, laser batteries, fire control, sensors", z=11.0, clear=4.4, x=(-212.0, 25.0), profile="weapons"),
        dict(id=3, name="Command Deck", programme="war table, signals, the Ferryman's quarters, the armoury", z=6.0, clear=4.4, strip=True, profile="crew"),
        dict(id=4, name="Crew Deck", programme="berths, mess, the surgeon's berth", z=1.5, clear=4.4, profile="services"),
        dict(id=5, name="Boarding Deck", programme="the Skiff hatches, magazines, damage parties", z=-3.0, clear=4.4, strip=True, profile="machinery"),
        dict(id=6, name="Machinery Deck", programme="reactor, drives, the flight bay", z=-7.5, clear=4.4, profile="machinery"),
        dict(id=7, name="Keel", programme="reaction mass and coolant", z=-13.0, clear=4.4, layout="spine", profile="tanks"),
    ],
    halls=[
        dict(id="helm", kind="bridge", name="The Helm", x=(-118.0, -92.0), decks=[1], role="bridge", crew=10),
        dict(id="bow_gun", kind="weapons", name="Spinal Rail Breech", x=(48.0, 70.0), decks=[3, 4, 5], entry=5, role="gun_bow"),
        dict(id="dorsal_gun", kind="weapons", name="Dorsal Rail Breech", x=(-28.0, -12.0), decks=[2, 3], entry=3, role="gun_dorsal"),
        dict(id="bay", kind="hangar", name="Harpy Bay", x=(-76.0, -48.0), decks=[5, 6], entry=6, role="hangar"),
        dict(id="reactor", kind="engineering", name="Reactor Hall", x=(-150.0, -116.0), decks=[4, 5, 6], entry=6, role="engineering"),
        dict(id="drive", kind="engines", name="Drive Room", x=(-206.0, -176.0), decks=[5, 6], entry=6, role="drives"),
    ],
    keys=[
        K(1, "IP", -150.0, 10.0, "comms", role="comms"),
        K(2, "IS", -90.0, 14.0, "weapons_control", role="fire_control"), K(2, "IP", -90.0, 14.0, "sensors", role="sensors"),
        K(2, "IP", -45.0, 14.0, "weapons", role="laser_port", name="Laser Battery (port)"), K(2, "IS", -45.0, 14.0, "weapons", role="laser_starboard", name="Laser Battery (starboard)"),
        K(3, "IS", -60.0, 16.0, "cic", role="cic"), K(3, "IS", -100.0, 14.0, "quarters", role="captain"), K(3, "IP", -100.0, 12.0, "armory", role="armory"),
        K(3, "IP", -60.0, 10.0, "brig", role="brig"), K(3, "IS", -135.0, 12.0, "wardroom"),
        K(4, "IS", -45.0, 14.0, "medbay", role="medbay"), K(4, "IP", -100.0, 9.0, "damage_control", role="dc_central"), K(4, "IS", 10.0, 9.0, "damage_control"),
        K(5, "IP", -20.0, 14.0, "magazine", role="magazine"), K(5, "IS", -20.0, 14.0, "magazine"), K(5, "IP", -100.0, 9.0, "damage_control"),
        K(6, "IP", 0.0, 14.0, "magazine"), K(6, "IS", 0.0, 12.0, "damage_control"),
    ],
    stairs=[dict(id="stair_helm", row="IS", x=-68.0), dict(id="stair_fore", row="IP", x=20.0), dict(id="stair_mid", row="IS", x=-95.0), dict(id="stair_aft", row="IP", x=-130.0),
            dict(id="stair_bow", row="IS", x=35.0)],
    docks=[dict(id="hatch_s3", deck=3, side=1, x=0.0), dict(id="hatch_p3", deck=3, side=-1, x=-105.0), dict(id="hatch_p5", deck=5, side=-1, x=-30.0), dict(id="hatch_s5", deck=5, side=1, x=-100.0),
           dict(id="mouth_bay", kind="mouth", hall="bay", face="ventral", x=-62.0, z=-9.0, width=12.0, height=5.0)],
    mounts=["gun_bow", "gun_dorsal", "laser_port", "laser_starboard"],
    crew=dict(complement=140, marines=16, watches=3, ranks=RANKS_MANDATE,
              shares=dict(bridge=0.06, control=0.07, gunnery=0.09, magazine=0.05, engineering=0.16, damage_control=0.12, medical=0.04, flight=0.05, sensors=0.04),
              billets=[dict(role="captain", at="bridge", fx=0.35), dict(role="executive_officer", at="cic"), dict(role="tactical_officer", at="fire_control"),
                       dict(role="chief_engineer", at="engineering"), dict(role="medical_officer", at="medbay"), dict(role="security_chief", at="armory"),
                       dict(role="flight_officer", at="hangar")]),
    dc=dict(parties=3, size=4),
)

# ======================================================================================================================== Acheron
# Kharon Mandate cruiser, 587 m (x -323..264): the flagship class. A heavy stern with the drives, a waist with the launch bays, armoured shoulders, the tower
# amidships, the spinal rail gun between two blades forward and 48 missile cells in two magazines. 380 aboard, forty of them the Ferry Guard.
ACHERON = dict(
    key="acheron", style="mandate", label="Kharon Mandate cruiser, Acheron class", wall=2.5, room_scale=2.0, names=dict(MANDATE_NAMES, quarters="Archon's Suite"),
    sections=[("A", 265.0, 95.0), ("B", 95.0, 10.0), ("C", 10.0, -80.0), ("D", -80.0, -168.0), ("E", -168.0, -245.0), ("F", -245.0, -324.0)],
    decks=[
        dict(id=1, name="Gun Deck", programme="the dorsal rail, laser batteries, sensors, fire control, the Helm", z=15.0, clear=5.4, profile="weapons"),
        dict(id=2, name="Command Deck", programme="the armoury, offices, the Archon's suite", z=9.0, clear=5.4, strip=True, profile="crew"),
        dict(id=3, name="Crew Deck", programme="berths, mess, the surgeon's berth", z=3.0, clear=5.4, profile="services"),
        dict(id=4, name="Boarding Deck", programme="Skiff hatches, VLS magazines, damage parties", z=-3.0, clear=5.4, strip=True, profile="magazine"),
        dict(id=5, name="Machinery Deck", programme="reactor, drives, the launch bays", z=-9.0, clear=5.4, profile="machinery"),
        dict(id=6, name="Hold Deck", programme="stores, workshops", z=-15.0, clear=5.4, profile="stores"),
        dict(id=7, name="Keel", programme="reaction mass and coolant", z=-21.0, clear=5.0, layout="spine", profile="tanks"),
    ],
    halls=[
        dict(id="helm", kind="bridge", name="The Helm", x=(-44.0, -14.0), decks=[1, 2], entry=2, role="bridge", crew=20),
        dict(id="spinal", kind="weapons", name="Spinal Rail Breech", x=(150.0, 200.0), decks=[3, 4, 5], entry=5, role="gun_bow", half=7.0),
        dict(id="dorsal_gun", kind="weapons", name="Dorsal Rail Breech", x=(50.0, 74.0), decks=[1, 2], entry=2, role="gun_dorsal"),
        dict(id="vls_a", kind="magazine", name="VLS Magazine (fore)", x=(112.0, 136.0), decks=[3, 4, 5], entry=5, role="magazine"),
        dict(id="vls_b", kind="magazine", name="VLS Magazine (aft)", x=(-70.0, -46.0), decks=[3, 4, 5], entry=5),
        dict(id="bays", kind="hangar", name="Launch Bays", x=(14.0, 62.0), decks=[4, 5], entry=5, role="hangar"),
        dict(id="reactor", kind="engineering", name="Reactor Hall", x=(-190.0, -150.0), decks=[3, 4, 5], entry=5, role="engineering"),
        dict(id="drive_a", kind="engines", name="Drive Room", x=(-312.0, -262.0), decks=[3, 4, 5], entry=5, role="drives"),
    ],
    keys=[
        K(1, "IS", -100.0, 18.0, "weapons_control", role="fire_control"), K(1, "IP", -100.0, 18.0, "sensors", role="sensors"),
        K(1, "IP", -150.0, 22.0, "weapons", role="laser_port", name="Laser Battery (port)"), K(1, "IS", -150.0, 22.0, "weapons", role="laser_starboard", name="Laser Battery (starboard)"),
        K(1, "IS", 20.0, 18.0, "weapons", role="laser_dorsal", name="Dorsal Laser House"), K(1, "IP", 20.0, 16.0, "comms", role="comms"),
        K(2, "IS", -70.0, 22.0, "armory", role="armory"), K(2, "IP", -70.0, 14.0, "brig", role="brig"), K(2, "IS", -130.0, 20.0, "wardroom"),
        K(2, "IS", 10.0, 20.0, "cic", role="cic"), K(2, "IP", 10.0, 20.0, "quarters", role="captain"),
        K(3, "IS", -110.0, 20.0, "medbay", role="medbay"), K(3, "IP", -30.0, 12.0, "damage_control", role="dc_central"), K(3, "IS", 90.0, 12.0, "damage_control"),
        K(4, "IP", -20.0, 12.0, "damage_control"), K(4, "IS", -120.0, 12.0, "damage_control"),
        K(5, "IP", -110.0, 16.0, "machinery"), K(5, "IS", -110.0, 16.0, "air_plant"),
    ],
    stairs=[dict(id="stair_tower", row="IS", x=-10.0), dict(id="stair_fore", row="IP", x=85.0), dict(id="stair_mid", row="IS", x=-100.0), dict(id="stair_aft", row="IP", x=-140.0),
            dict(id="stair_stern", row="IS", x=-230.0), dict(id="stair_bow", row="IP", x=230.0)],
    docks=[dict(id="hatch_s2", deck=2, side=1, x=-10.0), dict(id="hatch_p2", deck=2, side=-1, x=-60.0), dict(id="hatch_s4", deck=4, side=1, x=-100.0), dict(id="hatch_p4", deck=4, side=-1, x=-20.0),
           dict(id="hatch_s4b", deck=4, side=1, x=-250.0), dict(id="hatch_p2b", deck=2, side=-1, x=-210.0),
           dict(id="mouth_bay", kind="mouth", hall="bays", face="ventral", x=38.0, z=-12.0, width=30.0, height=8.0)],
    mounts=["gun_bow", "gun_dorsal", "laser_port", "laser_starboard", "laser_dorsal"],
    crew=dict(complement=380, marines=40, watches=3, ranks=RANKS_MANDATE,
              shares=dict(bridge=0.04, control=0.07, gunnery=0.08, magazine=0.06, engineering=0.14, damage_control=0.10, medical=0.04, flight=0.10, sensors=0.03),
              billets=[dict(role="captain", at="bridge", fx=0.35), dict(role="executive_officer", at="cic"), dict(role="tactical_officer", at="fire_control"),
                       dict(role="chief_engineer", at="engineering"), dict(role="medical_officer", at="medbay"), dict(role="security_chief", at="armory"),
                       dict(role="flight_officer", at="hangar")]),
    dc=dict(parties=4, size=5),
)

# ======================================================================================================================== Vigilant
# ASTRA destroyer, 306 m (x -156..150): the 7th Fleet's escort. A narrow hull, the bridge in a small tower aft of the middle, two dorsal rail turrets, laser
# batteries on the flanks, a small hangar for a section of fighters. 118 aboard, twelve of them marines.
VIGILANT = dict(
    key="vigilant", style="astra", label="ASTRA destroyer, Vigilant class", wall=2.0, room_scale=1.1, names=ASTRA_NAMES,
    sections=[("A", 151.0, 58.0), ("B", 58.0, 0.0), ("C", 0.0, -58.0), ("D", -58.0, -105.0), ("E", -105.0, -157.0)],
    decks=[
        dict(id=1, name="Bridge", programme="the bridge in its tower", z=10.5, clear=4.2, body=False, x=(-124.0, -58.0), layout="spine"),
        dict(id=2, name="Weapons Deck", programme="rail turrets' breeches, laser batteries, fire control", z=6.0, clear=4.2, x=(-142.0, 85.0), profile="weapons"),
        dict(id=3, name="Command Deck", programme="CIC, the captain's quarters, the armoury", z=1.5, clear=4.2, strip=True, profile="crew"),
        dict(id=4, name="Crew Deck", programme="berths, mess, sickbay", z=-3.0, clear=4.2, strip=True, profile="services"),
        dict(id=5, name="Machinery Deck", programme="reactor, drives, magazines, the hangar", z=-7.5, clear=4.2, profile="machinery"),
    ],
    halls=[
        dict(id="bridge", kind="bridge", name="Bridge", x=(-106.0, -80.0), decks=[1], role="bridge", crew=10),
        dict(id="gun_fore", kind="weapons", name="Rail Turret Breech (fore)", x=(38.0, 56.0), decks=[2, 3], entry=3, role="gun_dorsal_fore"),
        dict(id="gun_aft", kind="weapons", name="Rail Turret Breech (aft)", x=(-124.0, -108.0), decks=[2, 3], entry=3, role="gun_dorsal_aft"),
        dict(id="hangar", kind="hangar", name="Hangar", x=(-8.0, 22.0), decks=[4, 5], entry=5, role="hangar"),
        dict(id="reactor", kind="engineering", name="Main Engineering", x=(-100.0, -76.0), decks=[3, 4, 5], entry=5, role="engineering"),
        dict(id="drive", kind="engines", name="Drive Room", x=(-126.0, -112.0), decks=[4, 5], entry=5, role="drives"),
    ],
    keys=[
        K(1, "IP", -100.0, 8.0, "comms", role="comms"),
        K(2, "IS", -50.0, 12.0, "weapons_control", role="fire_control"), K(2, "IP", -50.0, 12.0, "sensors", role="sensors"),
        K(2, "IP", -10.0, 14.0, "weapons", role="laser_port", name="Laser Battery (port)"), K(2, "IS", -10.0, 14.0, "weapons", role="laser_starboard", name="Laser Battery (starboard)"),
        K(3, "IS", -45.0, 14.0, "cic", role="cic"), K(3, "IS", -20.0, 12.0, "quarters", role="captain"), K(3, "IP", -45.0, 12.0, "armory", role="armory"),
        K(3, "IP", -20.0, 9.0, "brig", role="brig"), K(3, "IS", 24.0, 12.0, "wardroom"),
        K(4, "IS", -45.0, 14.0, "medbay", role="medbay"), K(4, "IP", 30.0, 9.0, "damage_control", role="dc_central"), K(4, "IS", -105.0, 9.0, "damage_control"),
        K(5, "IP", 40.0, 14.0, "magazine", role="magazine"), K(5, "IS", 40.0, 14.0, "magazine"), K(5, "IP", -50.0, 9.0, "damage_control"),
    ],
    stairs=[dict(id="stair_bridge", row="IS", x=-64.0), dict(id="stair_bridge2", row="IP", x=-116.0), dict(id="stair_fore", row="IP", x=26.0), dict(id="stair_mid", row="IS", x=-30.0)],
    docks=[dict(id="hatch_s3", deck=3, side=1, x=20.0), dict(id="hatch_p3", deck=3, side=-1, x=-30.0), dict(id="hatch_p4", deck=4, side=-1, x=25.0), dict(id="hatch_s4", deck=4, side=1, x=-30.0),
           dict(id="mouth_hangar", kind="mouth", hall="hangar", face="ventral", x=7.0, z=-9.0, width=14.0, height=5.0)],
    mounts=["gun_dorsal_fore", "gun_dorsal_aft", "laser_port", "laser_starboard"],
    crew=dict(complement=118, marines=12, watches=3, ranks=RANKS_ASTRA,
              shares=dict(bridge=0.06, control=0.08, gunnery=0.09, magazine=0.05, engineering=0.16, damage_control=0.12, medical=0.04, flight=0.05, sensors=0.04),
              billets=[dict(role="captain", at="bridge", fx=0.35), dict(role="executive_officer", at="cic"), dict(role="tactical_officer", at="fire_control"),
                       dict(role="chief_engineer", at="engineering"), dict(role="medical_officer", at="medbay"), dict(role="security_chief", at="armory"),
                       dict(role="flight_officer", at="hangar")]),
    dc=dict(parties=3, size=4),
)

SPECS = {"styx": finalize(STYX), "acheron": finalize(ACHERON), "vigilant": finalize(VIGILANT)}
