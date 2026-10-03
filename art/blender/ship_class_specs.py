"""ASTRA ships: the spec of every class plan (FLOTTA-VIVA, docs/FLOTTA-VIVA.md §2): the ship's deck stack, its sections, the key rooms placed where
they have to be and why, the halls that take several decks, the stair columns, the boarding hatches, the profile of each deck's fill, the crew.
The builder (ship_class_build.py) lays out the rest. Positions are in the mesh's own frame (X to the bow, Y to starboard, Z up, metres): the
hull_m box of data/war/classes.json, the pictures of the hulls in docs/progressi/flotta/.

Sections run from the bow (A) to the stern; the boundaries include the cuts of the class (the planes where the break-up pieces are cut: a section
the war gutted is whole sections of this plan). Rows: IP/IS the inner rows to port/starboard of the spine, OP/OS the outer rows beyond the passages.
Each key room is `K(deck, row, x, length, kind, ...)`: a room centred on x. Kinds are those of ship_class_engine.KINDS.
"""
from __future__ import annotations

# ======================================================================================================================== shared
MANDATE_NAMES = {
    "bridge": "The Helm", "quarters": "Ferryman's Quarters", "cabins": "Oarsmen's Berths", "berthing": "Oarsmen's Berthing", "mess": "Oarsmen's Mess",
    "wardroom": "Wardens' Mess", "chapel": "Hall of the Ferried", "armory": "Ferry Guard Armoury", "medbay": "Surgeon's Berth", "brig": "Brig",
    "cic": "War Table", "comms": "Signal Room", "weapons": "Gun Deck", "engines": "Drive Room", "engineering": "Reactor Hall", "hangar": "Skiff Bay",
    "damage_control": "Damage Party Station", "storage": "Stores", "heads": "Washrooms",
}
ASTRA_NAMES = {"bridge": "Bridge", "cic": "Combat Information Centre", "quarters": "Captain's Quarters", "armory": "Marine Armoury", "engineering": "Main Engineering"}

RANKS_MANDATE = {"captain": "Ferryman", "executive_officer": "Warden", "tactical_officer": "Warden", "chief_engineer": "Warden", "medical_officer": "Warden",
                 "security_chief": "Warden", "flight_officer": "Warden", "officer": "Warden", "rating": "Oarsman", "marine": "Ferry Guard"}
RANKS_ASTRA = {"captain": "Captain", "executive_officer": "Commander", "tactical_officer": "Lieutenant Commander", "chief_engineer": "Lieutenant Commander",
               "medical_officer": "Surgeon Commander", "security_chief": "Major", "flight_officer": "Lieutenant Commander", "officer": "Lieutenant", "rating": "Crewman",
               "marine": "Private"}
RANKS_GUILD = {"captain": "Master", "executive_officer": "First Mate", "tactical_officer": "Mate", "chief_engineer": "Chief Engineer", "medical_officer": "Medic",
               "security_chief": "Boatswain", "flight_officer": "Mate", "officer": "Mate", "rating": "Hand", "marine": "Guard"}

# how a deck's rows are filled where no key room is: (kind, nominal length in metres), repeated along the row (and scaled by the class's room_scale)
PROFILES = {
    "weapons": dict(IP=[("storage", 12), ("machinery", 8)], IS=[("machinery", 8), ("storage", 12)], OP=[("storage", 10), ("machinery", 10)], OS=[("machinery", 10), ("storage", 10)]),
    "command": dict(IP=[("offices", 10), ("briefing", 10), ("offices", 10), ("storage", 8)], IS=[("offices", 10), ("storage", 8), ("briefing", 10)],
                    OP=[("cabins", 12), ("heads", 6)], OS=[("cabins", 12), ("heads", 6)]),
    "crew": dict(IP=[("cabins", 14), ("heads", 6), ("cabins", 14), ("storage", 8)], IS=[("cabins", 14), ("laundry", 6), ("cabins", 14), ("lounge", 10)],
                 OP=[("cabins", 12), ("storage", 8)], OS=[("cabins", 12), ("storage", 8)]),
    "services": dict(IP=[("berthing", 16), ("heads", 7), ("berthing", 16), ("gym", 10)], IS=[("mess", 16), ("galley", 10), ("lounge", 12), ("berthing", 16)],
                     OP=[("storage", 10), ("laundry", 6)], OS=[("storage", 10), ("laundry", 6)]),
    "machinery": dict(IP=[("machinery", 12), ("workshop", 10), ("storage", 8)], IS=[("machinery", 12), ("air_plant", 8), ("storage", 8)],
                      OP=[("machinery", 10), ("storage", 10)], OS=[("machinery", 10), ("storage", 10)]),
    "magazine": dict(IP=[("magazine", 14), ("storage", 8)], IS=[("magazine", 14), ("storage", 8)], OP=[("storage", 10), ("machinery", 8)], OS=[("storage", 10), ("machinery", 8)]),
    "stores": dict(IP=[("storage", 16)], IS=[("storage", 16)], OP=[("storage", 14)], OS=[("storage", 14)]),
    "tanks": dict(IP=[("tank", 24)], IS=[("tank", 24)], OP=[("tank", 20)], OS=[("tank", 20)]),
    "cargo": dict(IP=[("cargo", 24)], IS=[("cargo", 24)], OP=[("cargo", 20)], OS=[("cargo", 20)]),
}


def K(deck, row, x, length, kind, role=None, name=None, **kw):
    """A key room: on a deck, in a row, centred on x."""
    d = dict(deck=deck, row=row, x=x, len=length, kind=kind)
    if role:
        d["role"] = role
    if name:
        d["name"] = name
    d.update(kw)
    return d


def finalize(spec: dict) -> dict:
    """The spec's fill from the decks' profiles."""
    fill = spec.setdefault("fill", {})
    for d in spec["decks"]:
        p = d.get("profile")
        if p and d["id"] not in fill:
            fill[d["id"]] = PROFILES[p]
    return spec


# ======================================================================================================================== Lethe
# Kharon Mandate frigate, 240 m: a compact armoured arrowhead (scout and raider): a bow gun, a dorsal rail, laser batteries to both sides, eight
# missile cells, a boat bay for a Skiff, a reactor and the drives aft. 62 aboard, ten of them the Ferry Guard. The Helm in the tower amidships.
LETHE = dict(
    key="lethe", style="mandate", label="Kharon Mandate frigate, Lethe class", wall=2.5, room_scale=0.9, names=MANDATE_NAMES,
    sections=[("A", 114.0, 45.0), ("B", 45.0, -2.0), ("C", -2.0, -46.0), ("D", -46.0, -127.0)],
    decks=[
        dict(id=1, name="Helm", programme="the Helm and the mast", z=12.0, clear=4.5, body=False, foot=dict(x=(-45.0, -23.0), hw=7.5), layout="spine", profile="command"),
        dict(id=2, name="Gun Deck", programme="the dorsal rail, laser batteries, fire control, sensors", z=7.0, clear=4.4, profile="weapons"),
        dict(id=3, name="Command Deck", programme="war table, signals, the Ferryman's quarters, the armoury", z=2.0, clear=4.4, strip=True, profile="crew"),
        dict(id=4, name="Crew Deck", programme="berths, mess, the surgeon's berth, the Skiff Bay", z=-3.0, clear=4.4, strip=True, profile="services"),
        dict(id=5, name="Magazine Deck", programme="missile magazines, machinery, damage parties", z=-8.0, clear=4.4, profile="machinery"),
        dict(id=6, name="Keel", programme="reaction mass and coolant", z=-13.0, clear=4.4, layout="spine", profile="tanks"),
    ],
    halls=[
        dict(id="helm", kind="bridge", name="The Helm", x=(-36.0, -26.0), decks=[1], role="bridge", crew=10),
        dict(id="bow_gun", kind="weapons", name="Bow Rail Breech", x=(52.0, 70.0), decks=[3, 4], entry=4, role="gun_bow"),
        dict(id="dorsal_gun", kind="weapons", name="Dorsal Rail Breech", x=(4.0, 18.0), decks=[2, 3], entry=3, role="gun_dorsal"),
        dict(id="boat_bay", kind="hangar", name="Skiff Bay", x=(14.0, 36.0), decks=[4, 5], entry=5, role="hangar"),
        dict(id="reactor", kind="engineering", name="Reactor Hall", x=(-90.0, -64.0), decks=[3, 4, 5], entry=5, role="engineering"),
        dict(id="drive", kind="engines", name="Drive Room", x=(-105.0, -95.0), decks=[5], entry=5, role="drives"),
    ],
    keys=[
        K(1, "IP", -41.0, 8.0, "comms", role="comms"),
        K(2, "IS", -36.0, 10.0, "weapons_control", role="fire_control"), K(2, "IP", -36.0, 10.0, "sensors", role="sensors"),
        K(2, "OP", 20.0, 12.0, "weapons", role="laser_port", name="Laser Battery (port)"), K(2, "OS", 20.0, 12.0, "weapons", role="laser_starboard", name="Laser Battery (starboard)"),
        K(3, "IS", -40.0, 14.0, "cic", role="cic"), K(3, "IS", -25.0, 12.0, "quarters", role="captain"), K(3, "IS", -10.0, 12.0, "wardroom"),
        K(3, "IP", -38.0, 12.0, "armory", role="armory"), K(3, "IP", -24.0, 10.0, "brig", role="brig"),
        K(4, "IS", -20.0, 14.0, "medbay", role="medbay"), K(4, "IP", -50.0, 9.0, "damage_control", role="dc_central"), K(4, "IS", 42.0, 9.0, "damage_control"),
        K(5, "IP", -12.0, 14.0, "magazine", role="magazine"), K(5, "IS", -12.0, 14.0, "magazine"), K(5, "IP", -45.0, 9.0, "damage_control"),
    ],
    stairs=[dict(id="stair_helm", row="IS", x=-41.0), dict(id="stair_mid", row="IP", x=-4.0), dict(id="stair_fore", row="IS", x=40.0), dict(id="stair_aft", row="IP", x=-58.0)],
    docks=[dict(id="hatch_s3", deck=3, side=1, x=30.0), dict(id="hatch_p3", deck=3, side=-1, x=-30.0),
           dict(id="hatch_p4", deck=4, side=-1, x=30.0), dict(id="hatch_s4", deck=4, side=1, x=-30.0),
           dict(id="mouth_skiff", kind="mouth", hall="boat_bay", face="starboard", x=25.0, z=-6.0, width=8.0, height=5.0)],
    crew=dict(complement=62, marines=10, watches=3, ranks=RANKS_MANDATE,
              shares=dict(bridge=0.08, control=0.09, gunnery=0.10, magazine=0.06, engineering=0.18, damage_control=0.14, medical=0.04, flight=0.06, sensors=0.04),
              billets=[dict(role="captain", at="bridge", fx=0.35), dict(role="executive_officer", at="cic"), dict(role="tactical_officer", at="fire_control"),
                       dict(role="chief_engineer", at="engineering"), dict(role="medical_officer", at="medbay"), dict(role="security_chief", at="armory"),
                       dict(role="flight_officer", at="hangar")]),
    mounts=["gun_bow", "gun_dorsal", "laser_port", "laser_starboard"],
    dc=dict(parties=2, size=4),
)

SPECS = {"lethe": finalize(LETHE)}
