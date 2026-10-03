"""ASTRA ships: the specs of ASTRA's Praetorian battleship, the Free Guilds' freighter and the listening post Thule Watch (FLOTTA-VIVA; see
ship_class_specs.py for the format and the shared tables). Positions are in the mesh's own frame."""
from __future__ import annotations

from ship_class_specs import ASTRA_NAMES, RANKS_ASTRA, RANKS_GUILD, K, finalize

GUILD_NAMES = {"bridge": "Bridge", "quarters": "Master's Cabin", "cabins": "Crew Cabins", "berthing": "Crew Berths", "mess": "Mess", "galley": "Galley", "armory": "Weapons Locker",
               "medbay": "Sickbay", "engines": "Drive Section", "engineering": "Reactor Room", "cargo": "Cargo Hold", "storage": "Stores", "damage_control": "Repair Locker",
               "comms": "Radio Room", "workshop": "Workshop", "heads": "Washroom"}
STATION_NAMES = {"bridge": "Operations Centre", "quarters": "Commander's Quarters", "cabins": "Crew Quarters", "berthing": "Crew Quarters", "mess": "Mess", "armory": "Security Locker",
                 "medbay": "Infirmary", "engineering": "Reactor Hall", "hangar": "Dock Bay", "sensors": "Listening Array", "comms": "Signals Room", "computer": "Analysis Core",
                 "damage_control": "Repair Locker", "storage": "Stores", "lab": "Survey Lab"}
RANKS_STATION = dict(RANKS_ASTRA, captain="Lieutenant Commander", executive_officer="Lieutenant", tactical_officer="Lieutenant", chief_engineer="Lieutenant",
                     medical_officer="Lieutenant", security_chief="Sergeant", flight_officer="Ensign")

# ======================================================================================================================== Praetorian
# ASTRA battleship, 1129 m (x -579..550): the 7th Fleet's flagship class (ASN Constance's). A citadel of seven decks in a long armoured hull (the
# interior stops short of the ends: those are turret barbettes, drives and armour), the superstructure block on top and the tower with the bridge at the
# top of it. Rooms are bays of a section (this is a ship of a thousand people, not a hundred cabins). 1020 aboard, a hundred of them marines.
PRAETORIAN = dict(
    key="praetorian", style="astra", label="ASTRA battleship, Praetorian class", wall=3.5, room_scale=4.0, names=ASTRA_NAMES, skin_slack=6.0,
    sections=[("A", 551.0, 400.0), ("B", 400.0, 215.0), ("C", 215.0, 60.0), ("D", 60.0, -80.0), ("E", -80.0, -215.0), ("F", -215.0, -340.0), ("G", -340.0, -460.0), ("H", -460.0, -580.0)],
    decks=[
        dict(id=1, name="Bridge", programme="the bridge at the top of the tower", z=118.0, clear=8.0, body=False, foot=dict(x=(-118.0, -62.0), hw=15.0), layout="spine", profile="command"),
        dict(id=2, name="Tower Deck", programme="CIC, the Admiral's flag bridge, the captain's quarters", z=96.0, clear=8.0, body=False, foot=dict(x=(-128.0, -52.0), hw=15.0), layout="spine", profile="command"),
        dict(id=3, name="Citadel Deck", programme="officers, offices, the flag staff", z=38.0, clear=7.0, body=False, foot=dict(pts=[(-190.0, 30.0), (-150.0, 40.0), (60.0, 40.0), (125.0, 28.0)]), profile="command"),
        dict(id=4, name="Weapons Deck", programme="turret barbettes, laser batteries, fire control, sensors", z=17.0, clear=6.4, x=(-470.0, 360.0), profile="weapons"),
        dict(id=5, name="Command Deck", programme="the armoury, offices, wardroom", z=10.0, clear=6.4, strip=True, x=(-440.0, 340.0), profile="crew"),
        dict(id=6, name="Crew Deck", programme="berths and messes", z=3.0, clear=6.4, x=(-440.0, 340.0), profile="services"),
        dict(id=7, name="Services Deck", programme="sickbay, galleys, workshops", z=-4.0, clear=6.4, x=(-440.0, 340.0), profile="services"),
        dict(id=8, name="Boarding Deck", programme="barracks and the boarding hatches", z=-11.0, clear=6.4, strip=True, x=(-440.0, 340.0), profile="crew"),
        dict(id=9, name="Magazine Deck", programme="magazines, machinery, damage parties", z=-18.0, clear=6.4, x=(-560.0, 420.0), layout="spine", profile="magazine"),
        dict(id=10, name="Keel", programme="reaction mass and coolant", z=-25.0, clear=6.4, x=(-560.0, 420.0), layout="spine", profile="tanks"),
    ],
    halls=[
        dict(id="bridge", kind="bridge", name="Bridge", x=(-110.0, -70.0), decks=[1], role="bridge", crew=24),
        dict(id="turret_fore", kind="weapons", name="Forward Turret Barbette", x=(290.0, 330.0), decks=[4, 5, 6], entry=6, role="gun_dorsal_fore"),
        dict(id="turret_aft", kind="weapons", name="After Turret Barbette", x=(-430.0, -390.0), decks=[4, 5, 6], entry=6, role="gun_dorsal_aft"),
        dict(id="battery_ventral", kind="weapons", name="Ventral Battery", x=(120.0, 160.0), decks=[8, 9, 10], entry=10, role="gun_ventral"),
        dict(id="hangar", kind="hangar", name="Hangar", x=(-40.0, 100.0), decks=[6, 7, 8], entry=8, role="hangar"),
        dict(id="reactor", kind="engineering", name="Main Engineering", x=(-250.0, -170.0), decks=[7, 8, 9], entry=9, role="engineering"),
        dict(id="drives", kind="engines", name="Drive Room", x=(-540.0, -470.0), decks=[9, 10], entry=10, role="drives"),
        dict(id="magazine_a", kind="magazine", name="Forward Magazine", x=(240.0, 280.0), decks=[8, 9, 10], entry=10, role="magazine"),
        dict(id="magazine_b", kind="magazine", name="After Magazine", x=(-350.0, -310.0), decks=[8, 9, 10], entry=10),
    ],
    keys=[
        K(1, "IP", -90.0, 10.0, "comms", role="comms"),
        K(2, "IS", -90.0, 14.0, "cic", role="cic"), K(2, "IP", -90.0, 14.0, "quarters", role="captain"),
        K(3, "IS", -60.0, 30.0, "offices"), K(3, "IP", -60.0, 30.0, "briefing"),
        K(4, "IS", -150.0, 30.0, "weapons_control", role="fire_control"), K(4, "IP", -150.0, 30.0, "sensors", role="sensors"),
        K(4, "OP", 0.0, 40.0, "weapons", role="laser_port", name="Laser Battery (port)"), K(4, "OS", 0.0, 40.0, "weapons", role="laser_starboard", name="Laser Battery (starboard)"),
        K(4, "IS", 120.0, 30.0, "weapons", role="laser_dorsal", name="Dorsal Laser House"),
        K(5, "IS", -120.0, 36.0, "armory", role="armory"), K(5, "IP", -120.0, 24.0, "brig", role="brig"), K(5, "IS", -250.0, 30.0, "wardroom"), K(5, "IP", 40.0, 30.0, "comms"),
        K(7, "IS", -150.0, 36.0, "medbay", role="medbay"), K(7, "IP", -60.0, 24.0, "damage_control", role="dc_central"), K(7, "IS", 200.0, 24.0, "damage_control"),
        K(8, "IS", -300.0, 36.0, "berthing"),
        K(9, "IP", -60.0, 24.0, "damage_control"), K(9, "IS", -380.0, 24.0, "damage_control"), K(9, "IP", 150.0, 24.0, "damage_control"),
    ],
    stairs=[dict(id="stair_tower", row="IS", x=-70.0), dict(id="stair_fore", row="IP", x=240.0), dict(id="stair_mid", row="IS", x=40.0), dict(id="stair_aft", row="IP", x=-300.0),
            dict(id="stair_stern", row="IS", x=-420.0), dict(id="stair_reactor", row="IS", x=-130.0), dict(id="stair_bow", row="IP", x=320.0)],
    docks=[dict(id="hatch_s5", deck=5, side=1, x=-20.0), dict(id="hatch_p5", deck=5, side=-1, x=-200.0), dict(id="hatch_s5b", deck=5, side=1, x=-330.0), dict(id="hatch_p5b", deck=5, side=-1, x=180.0),
           dict(id="hatch_s8", deck=8, side=1, x=-160.0), dict(id="hatch_p8", deck=8, side=-1, x=60.0), dict(id="hatch_s8b", deck=8, side=1, x=200.0), dict(id="hatch_p8b", deck=8, side=-1, x=-300.0),
           dict(id="mouth_hangar", kind="mouth", hall="hangar", face="ventral", x=30.0, z=-22.0, width=60.0, height=12.0)],
    mounts=["gun_dorsal_fore", "gun_dorsal_aft", "gun_ventral", "laser_port", "laser_starboard", "laser_dorsal"],
    crew=dict(complement=1020, marines=100, watches=3, ranks=RANKS_ASTRA,
              shares=dict(bridge=0.02, control=0.05, gunnery=0.10, magazine=0.05, engineering=0.12, damage_control=0.10, medical=0.04, flight=0.06, sensors=0.03),
              billets=[dict(role="captain", at="bridge", fx=0.35), dict(role="executive_officer", at="cic"), dict(role="tactical_officer", at="fire_control"),
                       dict(role="chief_engineer", at="engineering"), dict(role="medical_officer", at="medbay"), dict(role="security_chief", at="armory"),
                       dict(role="flight_officer", at="hangar")]),
    dc=dict(parties=6, size=6),
)

# ======================================================================================================================== Freighter
# Free Guilds freighter, 352 m (x -180..173): two blocks joined by a cargo truss. The bridge and the crew forward, the drives and the reactor aft, the holds
# between, a gantry along the keel line from end to end. 34 aboard, no marines: a locker of rifles and a master who would rather talk.
FREIGHTER = dict(
    key="freighter", style="guild", label="Free Guilds freighter", wall=1.0, room_scale=1.6, names=GUILD_NAMES, skin_slack=8.0,
    sections=[("A", 174.0, 97.0), ("B", 97.0, 0.0), ("C", 0.0, -101.0), ("D", -101.0, -181.0)],
    decks=[
        dict(id=1, name="Upper Deck", programme="the bridge and the officers' cabins forward; crew cabins aft", z=7.5, clear=4.0,
             foot=dict(pts=[(-176.0, 11.0), (-112.0, 11.0), (-104.0, 0.0), (104.0, 0.0), (112.0, 11.0), (166.0, 9.0), (172.0, 5.0)]), layout="spine", profile="crew"),
        dict(id=2, name="Main Deck", programme="mess, galley, the boarding hatches; the holds", z=3.0, clear=4.0,
             foot=dict(pts=[(-176.0, 13.0), (-112.0, 13.0), (-104.0, 11.0), (104.0, 11.0), (112.0, 13.0), (166.0, 10.0), (172.0, 5.0)]), layout="spine", profile="cargo"),
        dict(id=3, name="Lower Deck", programme="the holds, the machinery", z=-1.5, clear=4.0,
             foot=dict(pts=[(-176.0, 13.0), (-112.0, 13.0), (-104.0, 11.0), (104.0, 11.0), (112.0, 13.0), (166.0, 10.0), (172.0, 5.0)]), layout="spine", profile="cargo"),
        dict(id=4, name="Keel Deck", programme="tanks and the drives' feed", z=-6.0, clear=4.0,
             foot=dict(pts=[(-176.0, 11.0), (-112.0, 11.0), (-104.0, 0.0), (104.0, 0.0), (112.0, 11.0), (166.0, 8.0)]), layout="spine", profile="tanks"),
    ],
    halls=[
        dict(id="reactor", kind="engineering", name="Reactor Room", x=(-146.0, -122.0), decks=[3, 4], entry=4, role="engineering"),
        dict(id="drives", kind="engines", name="Drive Section", x=(-174.0, -150.0), decks=[2, 3, 4], entry=4, role="drives"),
    ],
    keys=[
        K(1, "IS", 140.0, 12.0, "bridge", role="bridge"), K(1, "IP", 140.0, 12.0, "comms", role="comms"), K(1, "IP", 118.0, 10.0, "quarters", role="captain"),
        K(2, "IS", 130.0, 12.0, "mess"), K(2, "IP", 130.0, 8.0, "galley"), K(2, "IS", 112.0, 8.0, "armory", role="armory"), K(2, "IP", -120.0, 10.0, "medbay", role="medbay"),
        K(3, "IS", 130.0, 10.0, "damage_control", role="dc_central"), K(3, "IP", -120.0, 10.0, "damage_control"),
    ],
    stairs=[dict(id="stair_fore", row="IS", x=150.0), dict(id="stair_aft", row="IP", x=-112.0), dict(id="stair_aft2", row="IS", x=-156.0)],
    docks=[dict(id="hatch_s2", deck=2, side=1, x=148.0), dict(id="hatch_p2", deck=2, side=-1, x=120.0), dict(id="hatch_s3", deck=3, side=1, x=-118.0), dict(id="hatch_p3", deck=3, side=-1, x=-150.0),
           dict(id="hatch_s2b", deck=2, side=1, x=0.0), dict(id="hatch_p3b", deck=3, side=-1, x=40.0)],
    mounts=[],
    crew=dict(complement=34, marines=0, watches=3, ranks=RANKS_GUILD,
              shares=dict(bridge=0.14, control=0.06, engineering=0.26, damage_control=0.14, medical=0.04),
              billets=[dict(role="captain", at="bridge", fx=0.35), dict(role="executive_officer", at="comms"), dict(role="chief_engineer", at="engineering"),
                       dict(role="medical_officer", at="medbay"), dict(role="security_chief", at="armory")]),
    dc=dict(parties=2, size=3),
)

# ======================================================================================================================== Station
# Thule Watch, an ASTRA listening post, 221 m (x -110..110): a drum with the operations centre and the reactor, a sensor arm to one side and a dock arm to
# the other, joined to the drum by tubes. 48 aboard. Nothing on it shoots.
STATION = dict(
    key="station", style="astra", label="ASTRA listening post", wall=1.5, room_scale=1.0, names=STATION_NAMES, skin_slack=14.0,
    sections=[("A", 111.0, 40.0), ("B", 40.0, -40.0), ("C", -40.0, -111.0)],
    decks=[
        dict(id=1, name="Operations Deck", programme="the operations centre under the dome", z=11.5, clear=4.4, body=False,
             foot=dict(pts=[(-24.0, 5.0), (-18.0, 9.0), (0.0, 11.0), (18.0, 9.0), (24.0, 5.0)]), layout="spine"),
        dict(id=2, name="Command Deck", programme="signals, the commander's quarters, the analysis core", z=6.5, clear=4.4,
             foot=dict(pts=[(-30.0, 6.0), (-24.0, 12.0), (0.0, 14.5), (24.0, 12.0), (30.0, 6.0)]), layout="spine", profile="command"),
        dict(id=3, name="Array Deck", programme="the listening array (left arm), the dock bay (right arm), the drum's labs", z=2.0, clear=4.4,
             foot=dict(pts=[(-104.0, 7.5), (-50.0, 7.5), (-47.0, 2.6), (-38.0, 2.6), (-35.0, 6.0), (-30.0, 11.0), (-24.0, 14.5), (0.0, 16.0), (24.0, 14.5), (30.0, 11.0), (35.0, 6.0),
                              (38.0, 2.6), (47.0, 2.6), (50.0, 7.5), (90.0, 7.5)]), layout="spine", profile="command"),
        dict(id=4, name="Crew Deck", programme="quarters and the mess; arm workshops", z=-2.5, clear=4.4,
             foot=dict(pts=[(-104.0, 7.5), (-50.0, 7.5), (-47.0, 2.6), (-38.0, 2.6), (-35.0, 6.0), (-30.0, 11.0), (-24.0, 14.5), (0.0, 16.0), (24.0, 14.5), (30.0, 11.0), (35.0, 6.0),
                              (38.0, 2.6), (47.0, 2.6), (50.0, 7.5), (90.0, 7.5)]), layout="spine", profile="services"),
        dict(id=5, name="Machinery Deck", programme="reactor, air and water, damage parties", z=-7.0, clear=4.4,
             foot=dict(pts=[(-30.0, 8.0), (-24.0, 14.0), (0.0, 16.0), (24.0, 14.0), (30.0, 8.0)]), layout="spine", profile="machinery"),
        dict(id=6, name="Stores Deck", programme="stores and the tanks", z=-11.5, clear=4.4,
             foot=dict(pts=[(-28.0, 7.0), (-22.0, 12.0), (0.0, 14.0), (22.0, 12.0), (28.0, 7.0)]), layout="spine", profile="stores"),
    ],
    halls=[
        dict(id="ops", kind="bridge", name="Operations Centre", x=(-9.0, 9.0), decks=[1], role="bridge", crew=10),
        dict(id="reactor", kind="engineering", name="Reactor Hall", x=(-11.0, 11.0), decks=[4, 5, 6], entry=6, role="engineering"),
        dict(id="array", kind="sensors", name="Listening Array", x=(-96.0, -60.0), decks=[3, 4], entry=4, role="sensors"),
        dict(id="dock", kind="hangar", name="Dock Bay", x=(56.0, 84.0), decks=[3, 4], entry=4, role="hangar"),
    ],
    keys=[
        K(2, "IS", -12.0, 10.0, "comms", role="comms"), K(2, "IP", -12.0, 10.0, "quarters", role="captain"), K(2, "IS", 14.0, 8.0, "computer"),
        K(3, "IS", -20.0, 8.0, "armory", role="armory"), K(3, "IP", 14.0, 8.0, "lab"),
        K(4, "IS", 18.0, 8.0, "medbay", role="medbay"), K(4, "IP", -20.0, 8.0, "mess"),
        K(5, "IS", -22.0, 8.0, "damage_control", role="dc_central"), K(5, "IP", 22.0, 8.0, "damage_control"),
    ],
    stairs=[dict(id="stair_ops", row="IS", x=15.0), dict(id="stair_drum", row="IP", x=-16.0)],
    docks=[dict(id="hatch_s3", deck=3, side=1, x=12.0), dict(id="hatch_p3", deck=3, side=-1, x=-14.0), dict(id="hatch_s5", deck=5, side=1, x=-6.0), dict(id="hatch_p5", deck=5, side=-1, x=8.0),
           dict(id="mouth_dock", kind="mouth", hall="dock", face="bow", x=90.0, z=8.0, width=8.0, height=6.0, pos=[90.0, 0.0, 8.0])],
    mounts=[],
    crew=dict(complement=48, marines=4, watches=3, ranks=RANKS_STATION,
              shares=dict(bridge=0.12, control=0.08, sensors=0.25, engineering=0.15, damage_control=0.08, medical=0.04, flight=0.04),
              billets=[dict(role="captain", at="bridge", fx=0.35), dict(role="executive_officer", at="comms"), dict(role="chief_engineer", at="engineering"),
                       dict(role="medical_officer", at="medbay"), dict(role="security_chief", at="armory")]),
    dc=dict(parties=2, size=3),
)

SPECS = {"praetorian": finalize(PRAETORIAN), "freighter": finalize(FREIGHTER), "station": finalize(STATION)}
