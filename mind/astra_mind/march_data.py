"""The data of the war of the March (docs/GUERRA.md §10): what each ship class is worth in a fleet battle, what each system is worth and makes, who
starts where (the order of battle), and the people the fleets are given. Everything the strategic layer (march.py) counts with lives here, in plain
numbers a designer can change: the model code has no number of its own that matters.

The class numbers come from data/war/classes.json (hull, shields, rails, lasers, missiles, point defence, speed) and the model constants that turn them
into a fleet battle are fitted against the war bench of the simulation (tools/march_calibrate.py, data/march/cal_cpp.json): march_battle.py.

All names are English (the game's language); ship names are drawn from lists so that a fleet that appears has names that fit its side: the Mandate's
from the underworld and the Outer Worlds, ASTRA's from virtues, birds of prey and old navy names."""
from __future__ import annotations

from typing import Any

# ------------------------------------------------------------------------------------------------ the classes
# hull and shield are the class table's (shield = shield x its class scale); `rail` and `laser` are damage per second with every barrel firing, `missiles`
# the load, `pd` the point-defence channels, `speed` the cruise in m/s. `value` is the simulation's own weight of the class in a commander's choice of
# target (AstraWarGroups.cpp TargetValue); `worth` is what a ship is worth in a fleet, in destroyers (the square root of its guns times its plating, against a
# Styx's: what the war bench's battles say), and `cost` what a yard spends on one, in fleet points (the same unit); `wing` the craft a carrier of that
# class launches: fighters, bombers; `turn` degrees per second (a battleship needs more than a minute to turn her back on the enemy: a fleet of slow ships
# that breaks off late does not get away). `side` says whose class it is (a fleet is never mixed).
CLASSES: dict[str, dict[str, Any]] = {
    "aquila": dict(side="astra", hull=4200, shield=3000, regen=6.0, rail=31.4, laser=21.6, missiles=96, pd=6, speed=288, tier=3, value=1.7, cost=0.00, worth=2.80,
                   wing=(12, 6), turn=3.0, label="Aquila-class carrier cruiser"),
    "praetorian": dict(side="astra", hull=5200, shield=4000, regen=8.0, rail=32.0, laser=10.8, missiles=24, pd=4, speed=300, tier=3, value=1.3, cost=3.00, worth=3.00,
                       wing=(14, 5), turn=2.2, label="Praetorian-class battleship"),
    "vigilant": dict(side="astra", hull=1200, shield=750, regen=5.0, rail=15.7, laser=10.9, missiles=12, pd=2, speed=300, tier=1, value=0.85, cost=1.00, worth=1.00,
                     wing=(0, 0), turn=4.5, label="Vigilant-class destroyer"),
    "acheron": dict(side="mandate", hull=3600, shield=3000, regen=4.0, rail=31.9, laser=10.8, missiles=32, pd=3, speed=450, tier=2, value=1.25, cost=2.50, worth=2.50,
                    wing=(16, 5), turn=3.0, label="Acheron-class cruiser"),
    "styx": dict(side="mandate", hull=1300, shield=750, regen=4.0, rail=13.3, laser=10.9, missiles=16, pd=2, speed=450, tier=1, value=0.85, cost=1.00, worth=1.00,
                 wing=(0, 0), turn=4.5, label="Styx-class destroyer"),
    "lethe": dict(side="mandate", hull=520, shield=330, regen=4.0, rail=13.8, laser=10.9, missiles=8, pd=2, speed=500, tier=0, value=0.7, cost=0.65, worth=0.65,
                  wing=(0, 0), turn=6.0, label="Lethe-class frigate"),
}
SIDE_CLASSES = {"astra": ("praetorian", "vigilant"), "mandate": ("acheron", "styx", "lethe")}
CARRIERS = ("acheron", "praetorian", "aquila")                       # the classes that launch wings
CAPITAL = ("praetorian", "acheron", "aquila")
BUILD_ORDER = {"astra": ("vigilant", "praetorian"), "mandate": ("styx", "lethe", "acheron")}

# ------------------------------------------------------------------------------------------------ the systems
# value 0-10: what holding it is worth (the war's weight; also the siege time); yard: fleet points per hour its yards make; depot: repairs and resupplies
# friendly fleets; fort: the static defences at the Gate and in orbit, in destroyers' worth (1 = a Vigilant's guns and plating); siege_s: how long a fleet that
# holds the system with nothing left to oppose it needs to take it; post: who has a working
# listening post there at the start (the fog of war: a post sees the fleets in the system and the Gate wakes into it); `home`: the capital of that side;
# crossing_s: how long a fleet takes to cross the system (the Gate to the world and back: sieges and raids wait for it).
SYSTEMS: dict[str, dict[str, Any]] = {
    "Concordia": dict(value=10, yard=4.2, depot=True, fort=8, siege_s=2400, post=("astra",), home="astra", crossing_s=240,
                      note="the ASTRA capital: the Senate, the Admiralty and the Home Fleet's yards, three Gates from the front"),
    "Meridian": dict(value=7, yard=0.8, depot=True, fort=2, siege_s=900, post=("astra",), home="", crossing_s=150,
                     note="the breadbasket of the March: its grain feeds New Ravenna and the fleets; a Gate hub between the capital, Aurelia and Veyra"),
    "Aurelia": dict(value=9, yard=3.4, depot=True, fort=5, siege_s=1500, post=("astra",), home="", crossing_s=180,
                    note="home of the 7th Fleet: New Ravenna and Port Aurelius, the Aurelia Arsenal, the deuterium refineries of Tiberius; Janus Gate Aurelia and "
                         "Keeper Station"),
    "Cassia": dict(value=4, yard=1.8, depot=True, fort=2, siege_s=600, post=("astra",), home="", crossing_s=120,
                   note="ice mines and deuterium and the small Cassia Yards; lightly defended"),
    "Veyra": dict(value=5, yard=0.0, depot=False, fort=0, siege_s=0, post=(), home="", crossing_s=120, neutral=True,
                  note="the Guildhall of the March: Free Guilds trade hub and neutral ground where neither side may fight; spies and smugglers see every fleet that passes"),
    "Thule": dict(value=3, yard=0.0, depot=False, fort=0, siege_s=420, post=(), home="", crossing_s=150,
                  note="the frontier: Thule Watch, the ASTRA listening post, has been silent for days; nobody holds it and whoever stands there unopposed can claim it"),
    "Ophir": dict(value=4, yard=0.4, depot=True, fort=2, siege_s=600, post=("mandate",), home="", crossing_s=150,
                  note="a famine world of the Long Night, the Mandate's recruiting ground: bitter and loyal, it fills the crews"),
    "Erebus": dict(value=6, yard=2.0, depot=True, fort=5, siege_s=1200, post=("mandate",), home="", crossing_s=150,
                   note="Erebus Anchorage, the Mandate's forward base where the strike fleets muster and refit"),
    "Nemet": dict(value=4, yard=0.6, depot=True, fort=2, siege_s=600, post=("mandate",), home="", crossing_s=150,
                  note="drowned cities and fishing fleets, restless under Mandate rule, trading quietly with Veyra"),
    "Niflheim": dict(value=5, yard=1.4, depot=True, fort=2, siege_s=720, post=("mandate",), home="", crossing_s=150,
                     note="ice colonies and the Mandate's shipbreakers, who turn wrecks into warships"),
    "Kharon": dict(value=10, yard=2.8, depot=True, fort=8, siege_s=2400, post=("mandate",), home="mandate", crossing_s=240,
                   note="the Mandate capital, seat of the Archons and the Hall of the Ferried"),
}
# what each yard builds by default (a class and its share of the yard's points); the admirals change it with `set_production`
YARD_DEFAULT: dict[str, str] = {"Concordia": "praetorian", "Meridian": "vigilant", "Aurelia": "vigilant", "Cassia": "vigilant", "Erebus": "styx", "Kharon": "acheron", "Niflheim": "lethe",
                                "Ophir": "lethe", "Nemet": "styx"}
HQ = {"astra": "Aurelia", "mandate": "Erebus"}                       # where each side's high command sits (orders and reports take the Gates to travel)
CAPITALS = {"astra": "Concordia", "mandate": "Kharon"}
FRONT_FROM = {"astra": "Aurelia", "mandate": "Erebus"}               # the systems each side's war starts from

# ------------------------------------------------------------------------------------------------ names
MANDATE_SHIPS = {
    "acheron": ["Nyx", "Erebos", "Avernus", "Minos", "Rhadamanthus", "Persephone", "Hecate", "Tisiphone", "Megaera", "Alecto", "Cerberus", "Hydra"],
    "styx": ["Asphodel", "Tartarus", "Hypnos", "Thanatos", "Erinys", "Eurydice", "Aeacus", "Sisyphus", "Tantalus", "Ixion", "Orthrus", "Lamia", "Empusa", "Mormo",
             "Gorgon", "Charybdis", "Scylla", "Phorcys", "Ker", "Oneiros", "Geryon", "Echidna", "Typhon", "Briareos"],
    "lethe": ["Moros", "Keres", "Ananke", "Eris", "Nemesis", "Hybris", "Lyssa", "Apate", "Dysnomia", "Limos", "Algea", "Phonos", "Ate", "Horkos", "Oizys", "Momus"],
}
ASTRA_SHIPS = {
    "praetorian": ["Resolute", "Constance", "Valiant", "Bulwark", "Sovereign", "Concord", "Dauntless", "Vindicator", "Unyielding", "Stalwart"],
    "vigilant": ["Steadfast", "Valour", "Kestrel", "Vigilance", "Fortitude", "Prudence", "Temperance", "Clemency", "Verity", "Probity", "Harrier", "Osprey",
                 "Merlin", "Peregrine", "Condor", "Sentinel", "Aegis", "Intrepid", "Endeavour", "Accord", "Albatross", "Ardent", "Tenacity", "Gallant", "Honour"],
}

# the people who command: pools to draw from when a fleet needs a leader the story has not named (the director's beats name their own). Voices are the
# catalogue's (mind/astra_mind/tts.py), spread so that two leaders on one channel do not sound alike.
MANDATE_PEOPLE: list[dict[str, Any]] = [
    dict(name="Ferryman Yusra Hadid", rank="Ferryman (ship captain)", voice="jane", gender="f",
         bio="A ration-line pilot of the Long Night who lost her convoy to a Core freighter that would not stop; precise, dry, hard on herself first."),
    dict(name="Warden Corvin Tarsk", rank="Warden (group commander)", voice="charles", gender="m",
         bio="A shipbreaker's son from Niflheim who builds fleets out of wrecks and fights as if every hull were borrowed; patient, thrifty with lives."),
    dict(name="Ferryman Odalys Renk", rank="Ferryman (ship captain)", voice="vera", gender="f",
         bio="Thirty years in the Mandate's destroyers; speaks in short orders and never repeats one; her crews would follow her through a Gate that is closing."),
    dict(name="Ferryman Brannoch Vey", rank="Ferryman (ship captain)", voice="rafael", gender="m",
         bio="A hot-blooded raider captain from Ophir who treats a flank as a personal challenge; brave, careless of orders that keep him back."),
    dict(name="Warden Ilsabet Moorn", rank="Warden (group commander)", voice="lola", gender="f",
         bio="An analyst turned commander who counts before she fights and fights only when the count favours her; cold, courteous, never surprised twice."),
    dict(name="Ferryman Tavish Orrin", rank="Ferryman (ship captain)", voice="jean", gender="m",
         bio="A former ice miner with a gambler's nerve; loyal to whoever shared his rations in the Silence, which is the whole of his politics."),
    dict(name="Ferryman Edda Valk", rank="Ferryman (ship captain)", voice="mary", gender="f",
         bio="Raised in the Hall of the Ferried among the names of the dead; solemn, exact, believes every ship lost is a name added to a wall she must answer to."),
    dict(name="Warden Luca Brandt", rank="Warden (group commander)", voice="giovanni", gender="m",
         bio="A gunnery officer who learned fleet command by watching the Core's carriers; admires them and intends to burn them."),
    dict(name="Ferryman Sunniva Aske", rank="Ferryman (ship captain)", voice="caro_davy", gender="f",
         bio="A frigate captain from Nemet who trades with Veyra on the quiet and knows every Gate's tuning schedule; sly, well informed, careful of her ships."),
    dict(name="Ferryman Halloran Pike", rank="Ferryman (ship captain)", voice="peter_yearsley", gender="m",
         bio="Lost two brothers to the Silence and speaks of the Core as one speaks of weather; grim, steady under fire, honest to a fault."),
    dict(name="Warden Zefir Dacosta", rank="Warden (group commander)", voice="stuart_bell", gender="m",
         bio="A flight officer who flies with his wings; wants carriers in the van and the war won in the first week."),
    dict(name="Ferryman Rook Maddaloni", rank="Ferryman (ship captain)", voice="paul", gender="m",
         bio="A veteran who keeps a small notebook of every officer he has seen die for a bad order; he does not give them."),
]
ASTRA_PEOPLE: list[dict[str, Any]] = [
    dict(name="Captain Priyanka Rao", rank="Captain", voice="estelle", gender="f",
         bio="A destroyer squadron commander from the Aurelia Arsenal's own school; quick, exact, believes in initiative and writes her orders on one line."),
    dict(name="Commander Tomasz Wisniewski", rank="Commander", voice="juergen", gender="m",
         bio="A gunnery officer who counts shots and trusts numbers over hunches; blunt, methodical, sparing with praise."),
    dict(name="Captain Amadou Keita", rank="Captain", voice="michael", gender="m",
         bio="A veteran of the Gate campaigns before the Silence ended; calm, unhurried, a story for every ship; he does not like to be rushed and always arrives."),
    dict(name="Commander Lucia Ferrer", rank="Commander", voice="cosette", gender="f",
         bio="A former fighter pilot who took a destroyer after her squadron was lost; impatient with caution, loyal to her crew to a fault."),
    dict(name="Captain Hiroshi Arai", rank="Captain", voice="george", gender="m",
         bio="A logistics officer promoted into command by a war that ran out of captains; he knows where every missile in his fleet is and fights accordingly."),
    dict(name="Commander Elif Demir", rank="Commander", voice="anna", gender="f",
         bio="Young, brilliant, sleepless; she knows her ship's every system and says so; a little too eager for the fight."),
    dict(name="Captain Magnus Sorensen", rank="Captain", voice="marius", gender="m",
         bio="A Core Worlds aristocrat who earned his command the hard way; courteous, proud, wary of the Mandate's tricks."),
    dict(name="Commander Zainab Okafor", rank="Commander", voice="fantine", gender="f",
         bio="A damage-control specialist who commands a ship as she would a flooding compartment: calmly, from the inside out."),
    dict(name="Captain Rafael Quintero", rank="Captain", voice="javert", gender="m",
         bio="Strict, formal, a believer in the rules of engagement because he has seen what happens without them; fair to a fault."),
    dict(name="Commander Ingrid Lund", rank="Commander", voice="eponine", gender="f",
         bio="A Cassia-born officer who grew up under the Yards' cranes; defends her home with something that is not quite professional calm."),
    dict(name="Captain Dmitri Volkov", rank="Captain", voice="daan", gender="m",
         bio="A carrier man who dislikes battleships and says so; loves his wings, mourns every pilot by name."),
    dict(name="Commander Mei-Ling Zhou", rank="Commander", voice="azelma", gender="f",
         bio="A navigator turned destroyer captain; sees a battle as a geometry problem and is rarely wrong about the angles."),
]

# the two strategic commanders: Rourke is the director's (director.ADMIRAL); the Mandate's high command is new
MANDATE_HIGH_COMMAND: dict[str, Any] = dict(
    key="skarn", name="Archon Isolde Skarn", rank="Archon (commander of the Interdiction Fleet)", voice="caro_davy", gender="f",
    ship="the Interdiction Fleet's command at Erebus Anchorage",
    bio="Born on a ration line in the last years of the Silence and an Archon at forty-four; she believes the Gates are the only thing worth the dead and that a "
        "fleet is a finite thing that must be spent only where it takes a Gate. Patient, cold, economical with ships and with words, she wants Aurelia and will "
        "take ten systems slowly rather than lose the fleet in one battle. She respects an enemy who is good and never underestimates one who is lucky.")
ASTRA_HIGH_COMMAND: dict[str, Any] = dict(
    key="admiral", name="Vice Admiral Adrian Rourke", rank="Vice Admiral", voice="george", gender="m", ship="7th Fleet command, New Ravenna",
    bio="Commander of the 7th Fleet. Sixty-one, a veteran of the last Gate campaigns before the Silence ended; calm, dry, fiercely protective of his captains, "
        "allergic to heroics that waste ships. He trusts the Aquila's captain and says so rarely.")

# ------------------------------------------------------------------------------------------------ the order of battle
# The fleets at the start of a campaign. `ships`: class and the number (names are drawn); `wings`: carriers' craft [(carrier index in the fleet, kind, n)];
# `commander`: a person (or a key into the pools); `contacts`: the opening's own ship ids when the war's simulation spawns the fleet itself (the Aurelia
# opening: enemy.COMMANDERS, war_minds.ALLIES): a fleet with `scripted` is brought in by the game's script, not by the March, and its arrival time in the
# bench is the script's. `groups`: how the fleet is split in battle groups when it is materialised ([name, formation, [ship indices]]).
ORBAT: list[dict[str, Any]] = [
    # ---- ASTRA: the 7th Fleet and the Home Fleet
    # the main body was drawn to Cassia by a false distress call: it is one Gate away from the picket when the Mandate comes through at Aurelia
    dict(id="F-A1", side="astra", name="7th Fleet Main Body", where="Cassia", supply=0.9, morale=0.8,
         ships=[("praetorian", "ASN Valiant"), ("praetorian", "ASN Bulwark")] + [("vigilant", n) for n in
                ("ASN Vigilance", "ASN Fortitude", "ASN Prudence", "ASN Temperance", "ASN Clemency", "ASN Verity")],
         wings=[(0, "fighter", 14), (0, "bomber", 5), (1, "fighter", 14), (1, "bomber", 5)],
         commander=dict(name="Rear Admiral Odile Marchetti", rank="Rear Admiral", voice="alba", gender="f",
                        bio="Commands the 7th Fleet's main body under Rourke; thirty years of carrier work, a clipped manner, and a habit of asking a captain what he would do "
                            "before she says what she would."),
         order=dict(kind="hold", target="Cassia", stance="steady", reason="answered a distress call from the Cassia Yards that was false: it has found nothing", position="gate")),
    dict(id="F-A2", side="astra", name="Aurelia Picket", where="Aurelia", supply=1.0, morale=0.85, tactical_command="captain",
         ships=[("praetorian", "ASN Praetorian"), ("vigilant", "ASN Vigilant")], wings=[(0, "fighter", 8)], contacts=["T-01", "T-02"],
         commander=dict(key="castellan"),
         order=dict(kind="defend", target="Aurelia", stance="steady", reason="the picket at the Janus Gate, with the Aquila at its heart")),
    dict(id="F-A3", side="astra", name="Battle Group Constance", where="Aurelia", supply=1.0, morale=0.85, scripted="relief", arrives_s=730,
         ships=[("praetorian", "ASN Constance"), ("vigilant", "ASN Steadfast"), ("vigilant", "ASN Valour"), ("vigilant", "ASN Kestrel")],
         wings=[(0, "fighter", 8)], contacts=["T-03", "T-04", "T-05", "T-06"],
         commander=dict(key="aldana"), order=dict(kind="reinforce", target="F-A2", stance="steady", reason="reinforce the Aurelia picket", position="world")),
    dict(id="F-A4", side="astra", name="Cassia Squadron", where="Cassia", supply=1.0, morale=0.75,
         ships=[("vigilant", "ASN Harrier"), ("vigilant", "ASN Osprey")], wings=[],
         order=dict(kind="defend", target="Cassia", stance="steady", reason="guard the Yards", position="world")),
    dict(id="F-A5", side="astra", name="Home Fleet", where="Concordia", supply=1.0, morale=0.8,
         ships=[("praetorian", "ASN Sovereign"), ("praetorian", "ASN Concord")] + [("vigilant", n) for n in ("ASN Merlin", "ASN Peregrine", "ASN Sentinel", "ASN Aegis")],
         wings=[(0, "fighter", 14), (0, "bomber", 5)], commander=dict(name="Rear Admiral Joaquim Faro", rank="Rear Admiral", voice="giovanni", gender="m",
                                                                      bio="Commands the Home Fleet at Concordia; a politician's admiral who knows the Senate's mind and keeps the fleet where the Senate can see it."),
         order=dict(kind="defend", target="Concordia", stance="cautious", reason="the Senate's fleet: it guards the capital until the Senate says otherwise", position="world")),
    # ---- the Mandate: the Interdiction Fleet and the homeland
    dict(id="F-M1", side="mandate", name="Strike Group Solm", where="Thule", supply=0.95, morale=0.85, scripted="opening", arrives_s=170, dark=True,
         ships=[("acheron", "Acheron"), ("styx", "Styx"), ("styx", "Cocytus"), ("styx", "Phlegethon")], wings=[(0, "fighter", 4)],
         contacts=["T-21", "T-22", "T-23", "T-24"], commander=dict(key="solm"),
         order=dict(kind="assault", target="Aurelia", stance="bold", reason="seize Janus Gate Aurelia and Keeper Station; test the picket")),
    dict(id="F-M2", side="mandate", name="Lethe Hale", where="Aurelia", supply=0.9, morale=0.8, dark=True,
         ships=[("lethe", "Lethe")], contacts=["T-11"], commander=dict(key="hale"),
         order=dict(kind="recon", target="Aurelia", stance="cautious", reason="the eyes of the strike group: watch the picket and stay alive")),
    dict(id="F-M3", side="mandate", name="Interdiction Vanguard", where="Thule", supply=0.95, morale=0.85, scripted="vanguard", arrives_s=560, dark=True,
         ships=[("acheron", "Nyx"), ("styx", "Asphodel"), ("styx", "Tartarus"), ("styx", "Hypnos"), ("styx", "Thanatos"), ("styx", "Erinys"), ("lethe", "Moros"),
                ("lethe", "Keres")], wings=[(0, "fighter", 8), (0, "bomber", 4)],
         contacts=["T-31", "T-32", "T-33", "T-34", "T-35", "T-36", "T-37", "T-38"], commander=dict(key="thale"),
         groups=[["Interdiction Vanguard", "column", [0, 1], "thale"], ["Styx Line Dorn", "line", [2, 3, 4, 5], "dorn"], ["Raider Wedge Morrow", "wedge", [6, 7], "morrow"]],
         order=dict(kind="assault", target="Aurelia", stance="bold", reason="follow the strike group through the Gate and finish what it begins")),
    dict(id="F-M4", side="mandate", name="Interdiction Fleet Main Body", where="Erebus", supply=1.0, morale=0.85,
         ships=[("acheron", "Erebos"), ("acheron", "Avernus"), ("acheron", "Minos")] + [("styx", n) for n in
                ("Eurydice", "Aeacus", "Sisyphus", "Tantalus", "Ixion", "Orthrus", "Lamia", "Empusa")] + [("lethe", n) for n in ("Ananke", "Eris", "Nemesis", "Hybris")],
         wings=[(0, "fighter", 16), (0, "bomber", 5), (1, "fighter", 16), (1, "bomber", 5), (2, "fighter", 16), (2, "drone", 6)],
         commander=dict(name="Warden Zefir Dacosta", rank="Warden (group commander)", voice="stuart_bell", gender="m",
                        bio="Leads the Interdiction Fleet's carriers under the Archon; a flight officer who wants the war won in the first week."),
         order=dict(kind="hold", target="Erebus", stance="steady", reason="the main body musters and refits at the Anchorage while the vanguard tests the picket", position="world")),
    dict(id="F-M5", side="mandate", name="Kharon Home Guard", where="Kharon", supply=1.0, morale=0.8,
         ships=[("acheron", "Rhadamanthus"), ("acheron", "Persephone")] + [("styx", n) for n in ("Geryon", "Echidna", "Typhon", "Briareos")], wings=[(0, "fighter", 16), (1, "fighter", 16)],
         order=dict(kind="defend", target="Kharon", stance="cautious", reason="the Hall's guard: it does not leave the capital", position="world")),
    dict(id="F-M6", side="mandate", name="Ophir Garrison", where="Ophir", supply=1.0, morale=0.75, ships=[("styx", "Charybdis"), ("styx", "Scylla")], wings=[],
         order=dict(kind="defend", target="Ophir", stance="steady", reason="guard the recruiting ground", position="world")),
    dict(id="F-M7", side="mandate", name="Nemet Squadron", where="Nemet", supply=1.0, morale=0.7, ships=[("styx", "Phorcys"), ("lethe", "Ker"), ("lethe", "Oneiros")], wings=[],
         order=dict(kind="defend", target="Nemet", stance="steady", reason="keep Nemet quiet and Veyra watched", position="world")),
    dict(id="F-M8", side="mandate", name="Breakers' Flotilla", where="Niflheim", supply=1.0, morale=0.75, ships=[("lethe", "Lyssa"), ("lethe", "Apate"), ("lethe", "Dysnomia")],
         wings=[], order=dict(kind="defend", target="Niflheim", stance="steady", reason="guard the breaking yards", position="world")),
]
PEOPLE_FOR_FLEET = {"F-M4": "Warden Zefir Dacosta"}

# The opening as the March plays it. The game's own script brings three fleets by itself (the strike group at 25 km after 170 s, the vanguard, the relief); when the game switches
# that script off (the `opening` command with `script: false`, ASTRA_OPENING in docs/GUERRA.md §10) the three are the war's own fleets from the start: they stand where a war would
# have them, and the Interdiction Fleet opens its campaign the way the script did, but through the Gate: the strike group is sent at the set time (the scenario's first move, made by
# the clock like the script's was), so the Gate's warning is seen, the group comes from the Gate's mouth far out and closes for minutes, and the Aquila has the time a war gives her.
# The vanguard waits at Thule for the Archon's word and the relief at Meridian for the Admiral's: what they do next is the war's (the minds', and the Captain's words to Rourke).
MARCH_OPENING: dict[str, Any] = dict(
    fleets={
        "F-M1": dict(where="Thule", dark=False, hail=True,       # (Archon Solm opens a channel to the Aquila when he comes through, as he does in the script: she has the approach to talk)
                     order=dict(kind="hold", target="Thule", stance="bold", by="story", reason="the strike group waits at Thule for the hour the Archon has set")),
        "F-M3": dict(where="Thule", dark=False,
                     order=dict(kind="hold", target="Thule", stance="steady", reason="the vanguard waits at Thule for the strike group's work and the Archon's word")),
        "F-A3": dict(where="Meridian",
                     order=dict(kind="hold", target="Meridian", stance="steady", reason="Battle Group Constance musters at Meridian, one Gate from the Aurelia picket: it comes on the Admiral's word")),
    },
    plan=[dict(at_s=150.0, side="mandate", fleet="F-M1", kind="assault", target="Aurelia", stance="bold", dark=False,
               reason="seize Janus Gate Aurelia and Keeper Station; test the picket")],
)

# ------------------------------------------------------------------------------------------------ the war's pace (the bench tunes these)
PACE: dict[str, float] = dict(
    hop_base_s=95.0, hop_per_ship_s=4.0,            # a Gate jump: retuning and cycling, and a fleet's ships going through one after another
    exit_form_s=25.0,                               # a fleet that has jumped forms up before it can fight or move on
    warn_s=75.0,                                    # the Gate's cycling is seen this long before a fleet arrives (a force not running dark)
    order_hop_s=20.0, order_base_s=8.0,             # orders and reports take the Gates: this long a hop, plus this long to give them
    repair_per_s=0.0011,                            # hull fraction a yard puts back per second in a depot system (about 15 minutes for a ship that was half gone)
    resupply_per_s=0.0030,                          # supply regained per second in a depot system
    supply_per_hop=0.025, supply_per_battle_s=0.0004, supply_idle_per_s=0.00002,
    morale_recover_per_s=0.0004,
    siege_base_s=300.0,                             # time an unopposed fleet needs to take a system, times (0.5 + value / 10)
    claim_s=420.0,                                  # time an unopposed fleet needs to claim a system nobody holds
    siege_scale=1.0,                                # (a tuning of all the sieges at once)
    fort_regen_per_s=0.0008,
    wreck_salvage=0.25,                             # the Mandate's shipbreakers: the share of the points of the ships lost on ground it holds that come back as hulls
    battle_max_s=1500.0,
    will_start={"astra": 0.78, "mandate": 0.86},
    will_decay_per_s=0.000016,                      # a war wears a people down (about 0.08 an hour); victories, taken ground and a safe homeland hold it up
    will_home_per_s=0.000008,                       # ... what a side's held systems give back, by their worth (a lost province gives nothing)
    peace_will=0.30,                                # below this a government wants peace
    detect_wake_dark=0.0,
)
