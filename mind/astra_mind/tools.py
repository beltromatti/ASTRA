"""Typed ship tools: the only way the crew changes the ship. The game (UAstraShipSubsystem) implements each one and
answers with a result; `speak` is handled by the mind itself (text -> voice)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import stations as station_model
from .crew import CREW
from .transporter import TO_HELP, WHO_HELP


def _fn(name: str, desc: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required, "additionalProperties": False}}}


PATIENTS = [f"patient{i}" for i in range(1, 13)]   # the Medbay's twelve beds (the wounded speak as their bed)
MESS = [f"mess{i}" for i in range(1, 13)] + ["mess_cook"]   # the Mess Hall's places at table, and its cook

SPEAK = _fn("speak", "Someone aboard speaks aloud: an officer, a wounded crewman in the Medbay, someone off duty in "
                     "the Mess Hall, or the ship's computer (`computer`: only in a lift, where it answers the Captain's travel orders) "
                     "(one call per line, in speaking order). Short and specific: one sentence, and an "
                     "acknowledgement always says WHAT was set or answered (never a bare 'aye').", {
    "speaker": {"type": "string", "enum": list(CREW) + PATIENTS + MESS + ["computer"]},
    "text": {"type": "string", "description": "The spoken line, in the Captain's language: usually one short sentence "
                                              "(6-16 words); two only when the second carries something needed; more only "
                                              "when the Captain asked for a report or an explanation"},
    "tone": {"type": "string", "enum": ["calm", "focused", "urgent", "tense", "alarmed", "warm", "dry"]}},
    ["speaker", "text", "tone"])

SHIP_TOOLS: list[dict[str, Any]] = [
    _fn("set_course", "Helm: new heading (0-359, relative to the system plane) and mark/pitch (-90..90).", {
        "heading_deg": {"type": "number", "minimum": 0, "maximum": 359.99},
        "mark_deg": {"type": "number", "minimum": -90, "maximum": 90}}, ["heading_deg", "mark_deg"]),
    _fn("intercept", "Helm: continuous intercept of a contact — the course follows it; at the standoff range the ship "
                     "turns broadside (all turrets bear) and holds that range. A set_course cancels it.", {
        "contact_id": {"type": "string"},
        "standoff_km": {"type": "number", "minimum": 1, "maximum": 30,
                        "description": "range to hold: railguns reach 10 km, lasers 4 km"}}, ["contact_id", "standoff_km"]),
    _fn("transit_gate", "Helm: take the Aquila through the system's Janus Gate to another star system. The helm flies at "
                        "full ahead to the gate's approach lane (see janus_gate in the state for where it is), then the "
                        "gate's field takes the ship and draws her through the ring: once in the lane there is no turning "
                        "back. Everything in this system (enemies, allies, wrecks) stays behind. Only on the Captain's "
                        "explicit order. A set_course or intercept before the lane cancels the approach.", {
        "system_name": {"type": "string", "description": "destination system: one the gate here is bound to (see "
                                                         "janus_gate and the March), usually the one Fleet ordered"}},
        ["system_name"]),
    _fn("set_throttle", "Helm: main drive throttle in percent (0 = all stop, 33 = one third, 50 = half, 100 = full = 480 m/s).", {
        "percent": {"type": "number", "minimum": 0, "maximum": 100}}, ["percent"]),
    _fn("set_alert", "Set the ship's alert condition (lighting, stations, doors follow it).", {
        "level": {"type": "string", "enum": ["green", "yellow", "red"]}}, ["level"]),
    _fn("set_shields", "Tactical: raise/lower shields or reinforce one sector (hits on that side cost the shields far less, "
                       "hits elsewhere more; balanced = even). Face the sector towards the enemy's fire.", {
        "mode": {"type": "string", "enum": ["balanced", "forward", "aft", "port", "starboard", "dorsal", "ventral", "off"]}},
        ["mode"]),
    _fn("route_power", "Operations: power allocation of a system in percent of nominal (100 = nominal, max 150). The six "
                        "systems share a reactor budget of 700% (all at 100 = 600): boosting beyond it needs a cut elsewhere "
                        "first. Shields power = regeneration and stopping power; weapons = railgun cadence; engines = speed.", {
        "system": {"type": "string", "enum": ["shields", "weapons", "engines", "sensors", "life_support", "flight_deck"]},
        "percent": {"type": "number", "minimum": 0, "maximum": 150}}, ["system", "percent"]),
    _fn("set_target", "Tactical: designate the current target (a contact id from the state).", {
        "contact_id": {"type": "string"}}, ["contact_id"]),
    _fn("fire_weapons", "Tactical: engage a contact with a weapon group (it needs a track: never a bearing-only contact — except missiles at a jammer). Railguns (range 10 km) and lasers (4 km) fire "
                        "`salvo` volleys at their cadence (railguns one volley every 7 s; 12 = sustained fire, about 1.5 "
                        "minutes); if the target is still beyond range they stay assigned and open fire by themselves "
                        "once it closes. Missiles (25 km) launch `salvo` missiles at once (max 8; the VLS then cycles 14 s); at a "
                        "jamming contact they fly home-on-jam, without a range.", {
        "weapon": {"type": "string", "enum": ["railguns", "lasers", "missiles", "torpedoes"]},
        "contact_id": {"type": "string"},
        "salvo": {"type": "integer", "minimum": 1, "maximum": 12}}, ["weapon", "contact_id", "salvo"]),
    _fn("cease_fire", "Tactical: stop all our offensive fire at once (queued volleys cancelled; point defense stays on).",
        {}, []),
    _fn("launch_decoys", "Tactical: flares and chaff off her flanks for 18 s: about half the missiles on their terminal run at "
                         "the Aquila lose her. Two of eight aboard each launch; best just before a salvo arrives.", {}, []),
    _fn("set_point_defense", "Tactical: point-defence mode.", {
        "mode": {"type": "string", "enum": ["auto", "hold", "free"]}}, ["mode"]),
    _fn("launch_squadron", "Flight Control: launch a flight group (alpha = 8 Falcon fighters, bravo = 7 Hammer torpedo "
                            "bombers, drones = 12 Wasp drones) or re-task it if airborne. Missions: cap = patrol close around the "
                            "Aquila (within about 3 km) shooting down incoming missiles and fighters; strike = attack a contact (bombers make a torpedo run "
                            "then return, fighters strafe); escort = protect a friendly or civilian ship; ew = jam an enemy ship's fire "
                            "control; recon = identify a contact (or the nearest unknown one); sar = rescue survivors at the "
                            "last wreck. Enemy point defence shoots at them.", {
        "squadron": {"type": "string", "enum": ["alpha", "bravo", "drones"]},
        "mission": {"type": "string", "enum": ["cap", "strike", "escort", "sar", "ew", "recon"]},
        "contact_id": {"type": "string", "description": "Target or escorted contact id; empty string if none"}},
        ["squadron", "mission", "contact_id"]),
    _fn("recall_squadron", "Flight Control: recall a flight group to the flight deck.", {
        "squadron": {"type": "string", "enum": ["alpha", "bravo", "drones"]}}, ["squadron"]),
    _fn("dispatch_damage_control", "Operations: send one of the 4 damage-control teams to an incident in the ship state's "
                                    "damage list (deck + section letter). Unattended fires spread and burn the structure.", {
        "deck": {"type": "integer", "minimum": 1, "maximum": 12}, "section": {"type": "string"},
        "task": {"type": "string", "enum": ["repair", "firefight", "seal_breach", "rescue"]},
        "priority": {"type": "string", "enum": ["low", "normal", "high", "critical"]}},
        ["deck", "section", "task", "priority"]),
    _fn("set_radiators", "Engineering: extend or retract the radiator wings. Extended they shed heat almost three times "
                          "faster, but the hot panels make the Aquila easier to detect (even under silent EMCON) and they "
                          "can be shot away (damaged radiators shed less until repaired).", {
        "state": {"type": "string", "enum": ["extended", "retracted"]}}, ["state"]),
    _fn("vent_heat", "Engineering: emergency coolant dump — sheds a third of the heat at once (three charges aboard); "
                     "the plume gives the ship away to every sensor for half a minute.", {}, []),
    _fn("hail", "Communications: open a channel to a contact (or 'fleet' for the 7th Fleet net, or 'flight' for the flight net: the CAG, the squadron leaders and their "
                "wingmen, the Chief of the Deck; what the Captain says to them then goes out on it and they answer for themselves).", {
        "contact_id": {"type": "string", "description": "a contact id, 'fleet' or 'flight'"},
        "intent": {"type": "string", "enum": ["identify", "warn", "demand_surrender", "request_support", "negotiate", "report"]},
        "message": {"type": "string", "description": "What we transmit, in English (the Interpreter translates)"}},
        ["contact_id", "intent", "message"]),
    _fn("end_transmission", "Communications: close the open channel (e.g. with an enemy commander).", {}, []),
    _fn("fleet_request", "Communications: pass the Captain's REQUEST to the captains of the friendly warships in company (the 7th "
                         "Fleet ships on the plot) over the fleet net. They are people: the captain judges it by the chain of command and "
                         "answers over the radio (an acknowledgement, or the reason it cannot be done) and gives the order to his group "
                         "himself. For a direct order from the Captain as the senior officer, the XO's group_order is the tool.", {
        "ship": {"type": "string", "description": "contact id of one friendly warship (e.g. T-01) or 'all'"},
        "request": {"type": "string", "enum": ["focus_fire", "engage_freely", "cover_us", "close_in", "stand_off", "hold_fire"],
                    "description": "focus_fire: concentrate on the target; engage_freely: pick their own targets; "
                                   "cover_us: stay between the Aquila and the enemy; close_in: knife-fight range; "
                                   "stand_off: hold at railgun range, out of the enemy's lasers; hold_fire: cease fire"},
        "target": {"type": "string", "description": "focus_fire: the contact id to concentrate on"}},
        ["ship", "request"]),
    _fn("holo_display", "Science & Sensors: what the holo table in the middle of the bridge shows — the tactical plot "
                        "(the battle around the Aquila), the sector map (the systems of the March, who holds them, "
                        "the gate links, where the Aquila is) or a ship close up (the Aquila in cutaway, deck by deck: the "
                        "damage where it is and the damage-control teams; or, with a target, a scanned ship's sections and "
                        "shield faces).", {
        "mode": {"type": "string", "enum": ["tactical", "sector", "ship"]},
        "target": {"type": "string", "description": "ship mode only, optional: the contact id of a scanned ship (T-21)"}}, ["mode"]),
    _fn("crew_locate", "The personnel file and the internal locator (any officer, at any console): who someone aboard is and where "
                       "they are right now — rank, department, job and watch, the deck, section and room they are in and what they are "
                       "doing, or that they lie wounded in the Medbay or fell. Ask by a name (\"Kowalski\", \"Lieutenant Sato\", a "
                       "pilot's call sign) or a job (\"the cook\", \"a flight-deck officer\"). Call it on its own, before speaking: what "
                       "it finds comes back to you, and you tell the Captain that and nothing more. Of the 560 aboard you know the "
                       "bridge and the heads of department; anyone else you look up before saying anything about them.", {
        "who": {"type": "string", "description": "a surname, a rank and name, a call sign or a job, in English (the file is kept in "
                                                 "English: \"cook\", \"Lieutenant Sato\")"}}, ["who"]),
    _fn("abandon_ship", "ABANDON SHIP: the evacuation of the Aquila to the lifepods; Engineering overloads the reactor so the "
                        "enemy cannot take her, and she is lost in about two minutes. Only on the Captain's explicit order to "
                        "abandon ship (never proposed as done, never on initiative).", {}, []),
    _fn("dismiss_visitor", "The officer who came to the Captain's quarters in person (`visitor` in the state) goes back "
                           "to their station: when the Captain lets them go, or the conversation is over.", {}, []),
    _fn("set_emcon", "Science & Sensors: emission control (silent = passive sensors only).", {
        "level": {"type": "string", "enum": ["silent", "restricted", "full"]}}, ["level"]),
    _fn("active_scan", "Science & Sensors: active radar/lidar ping (every contact within 90 km tracked and classified) or a "
                       "focused scan of a contact (identifies it within 60 km). It reveals our position to everyone.", {
        "contact_id": {"type": "string", "description": "Contact id, or empty string for a full sweep"}}, ["contact_id"]),
]

# the Transporter Room (docs/TELETRASPORTO.md): Operations or the XO hand the Captain's order to the Chief, who is a person of her own (transporter.py); the mind takes the call
# (server.py: the `transporter` hook), it never goes to the game as a command of the bridge's
TRANSPORTER = _fn("transporter", "Operations or the XO: hand the Captain's order to the Transporter Room (Deck 5), where Chief Petty Officer Rhea Ostrander runs the lattice "
                                 "transport. She checks it against the beam's rules, carries it out or tells the Captain why not, and answers for herself in her own voice: you only "
                                 "relay, in the Captain's own terms, and do not promise or narrate the result. beam: who goes where; energize: the Captain's word for a lock she is "
                                 "holding; abort: cancel what is in the beam; ask: a question for her (what can reach the Vigilant, who is away, why not). Only on the Captain's "
                                 "order, never on your own initiative.", {
    "action": {"type": "string", "enum": ["beam", "energize", "abort", "ask"]},
    "who": {"type": "array", "items": {"type": "string"}, "description": WHO_HELP},
    "to": {"type": "string", "description": TO_HELP},
    "from": {"type": "string", "description": "leave out when they are where they stand; 'surface' or a contact id to bring them back from there"},
    "energize": {"type": "string", "enum": ["auto", "hold"], "description": "hold: the lock waits for the Captain's word (then `energize`); leave out for auto"},
    "shield_window": {"type": "boolean", "description": "our shields held down for the cycle: only when the Captain says so (or has said it is all right) with enemies about"},
    "override": {"type": "array", "items": {"type": "string", "enum": ["hazard", "weak_lock"]},
                 "description": "the Captain's OWN word to take a risk (land them in a compartment with fire, smoke or no air; beam on a lock under 55%): never on an officer's say-so"},
    "id": {"type": "string", "description": "the transport's id (X3) for energize or abort; leave out for the one waiting or under way"},
    "question": {"type": "string", "description": "ask only: what the Captain wants to know, in his words"}}, ["action"])
SHIP_TOOLS.append(TRANSPORTER)
# Flight Control: the Captain flying a Falcon (Eagle) is brought aboard by the deck's recovery guidance (an automatic carrier landing)
EAGLE_RECOVER = _fn("eagle_recover", "Flight: bring the Captain's Falcon (Eagle) aboard with the deck's recovery guidance — it flies her clear of the hull, to the gate "
                                     "in front of the bow and in through the port tube (about half a minute). Only while the Captain is flying and within 8 km; for when "
                                     "he asks to be brought home, or must be. He can take the stick back at any time.", {
    "by": {"type": "string", "description": "who calls it, for the log (Flight Control)"}}, [])
SHIP_TOOLS.append(EAGLE_RECOVER)

# The Captain's weapons (docs/ABBORDAGGI.md): the armourer of the Marine Armory takes one up to him; the game has the rack, the locker and the delivery, and tells the crew where the weapons are
# (`arms` in the ship state: a build without it does not have the tool)
ISSUE_WEAPON = _fn("issue_weapon", "The XO (or any officer the Captain asks): send the armourer of the Marine Armory (Deck 8) up with a weapon for the Captain. The weapon really leaves the "
                                   "rack, a marine takes it up the ship at a run, and after the time the result gives it is in the Captain's hands wherever he is on foot. kind: `pistol` "
                                   "(the M27S sidearm), `rifle` (the AR-181) or `kit` (both). Only for the Captain, when he asks for a weapon or an officer is told to arm him; the result "
                                   "says who is bringing it and how long, or why not (he carries it already, the rack has none, he is flying): say that, never a promise of your own.", {
    "kind": {"type": "string", "enum": ["pistol", "rifle", "kit"]},
    "who": {"type": "string", "enum": ["captain"], "description": "who is issued the weapon: the Captain (the only one)"}}, ["kind"])
SHIP_TOOLS.append(ISSUE_WEAPON)

# Boarding an enemy ship with the Aquila's marines (docs/ABBORDAGGI.md, F5.2): the game has the boats (the Kestrels of the shuttle bay on Deck 8), the hatches, the shields that hold the boats
# off, the point defence and the fighters that shoot at them, and the fight; the tool is the order. `boarding_boats` in the ship state (the boats free, the marines fit to go) is what says this
# build has them; `boarding_options` lists what a boat could dock at now.
BOARD_FACES = ["port", "starboard", "dorsal", "ventral", "bow", "stern"]
BOARD_OBJECTIVES = ["captain", "bridge", "engineering", "armory", "medbay", "brig", "comms", "hangar"]
BOARD_SHIP = _fn("board_ship", "The XO (or any officer the Captain asks): board an enemy ship with the Aquila's marines. They go in the Aquila's assault shuttles (Kestrels, twelve marines each, from the "
                               "shuttle bay on Deck 8): the boats leave the bay, cross to the target and dock at a hatch on her hull, and the marines cut in and fight their way to the objective. The "
                               "boats are shot at by the target's point defence and her fighters on the way in, and cannot dock through a shield that holds on the face they come to (they wait off the "
                               "hull and turn back): `boarding_options` in the ship state lists the ships a boat could dock at now and what each has to stop them. The result says what was launched, "
                               "from where, at which hatches and how long it takes, and the facts that make it risky, or why not: say that, never a promise of your own. Only on the Captain's order. "
                               "`call_off` turns the boats back and tells the marines to come out.", {
    "action": {"type": "string", "enum": ["launch", "call_off"], "description": "launch (the default) or call_off"},
    "target": {"type": "string", "description": "launch: the ship to board: her contact id (T-30) or name from the plot"},
    "boats": {"type": "integer", "minimum": 1, "maximum": 2, "description": "how many Kestrels (twelve marines each); leave out for both"},
    "face": {"type": "string", "enum": BOARD_FACES, "description": "the side of the target the boats dock on; leave out for the side nearest the Aquila"},
    "objective": {"type": "string", "enum": BOARD_OBJECTIVES, "description": "what the marines fight for: captain (the commander's suite: a ship's commander is taken there) · bridge · engineering (her reactor) · "
                                                                              "armory · medbay · brig · comms · hangar; leave out for the commander's suite"},
    "marines": {"type": "integer", "minimum": 4, "maximum": 24, "description": "how many marines in all (the boats' full loads when left out)"},
    "captain": {"type": "boolean", "description": "true only when the Captain himself says he goes with the marines: he rides in the first Kestrel (the screen goes dark for the flight), fights on the other "
                                                  "ship with his rifle and comes home in the boat; if that boat is shot down he is in it. Never on your own initiative"}}, [])
SHIP_TOOLS.append(BOARD_SHIP)

DEPARTMENTS = ["xo", "helm", "ops", "tactical", "comms", "sensors", "engineering", "flight"]
# what a standing order lets each department do by itself when an event calls for it
DEPT_TOOLS = {"tactical": {"set_target", "fire_weapons", "cease_fire", "set_shields", "set_point_defense", "launch_decoys"},
              "helm": {"set_course", "intercept", "set_throttle"},
              "ops": {"route_power", "dispatch_damage_control"},
              "engineering": {"set_radiators", "vent_heat", "route_power"},
              "flight": {"launch_squadron", "recall_squadron"},
              "sensors": {"active_scan", "set_emcon", "holo_display"},
              "comms": {"hail", "fleet_request"},
              "xo": {"set_alert", "group_order"}}

# handled by the mind (not a ship command): the Captain's orders that last
STANDING = _fn("standing_order", "Record (or cancel) a STANDING ORDER: an order of the Captain's meant to last, which a "
                                 "department carries out by itself whenever the situation calls for it (weapons free on "
                                 "hostiles inside a range, keep a combat air patrol up, keep the heat under a limit, hold "
                                 "EMCON unless fired on...). Only when the Captain gives one or withdraws one.", {
    "action": {"type": "string", "enum": ["set", "cancel"]},
    "department": {"type": "string", "enum": DEPARTMENTS + ["all"]},
    "order": {"type": "string", "description": "set: the order restated precisely in English, with its conditions and "
                                               "limits (what, when, against what, what never)"}},
    ["action", "department", "order"])

# The XO's direct order to one of our battle groups (docs/GUERRA.md §6.2): only on a game that reports its groups (`_astra_groups`), and the mind
# lets it through only when the Captain is the senior officer present (war_minds.WarMinds.captain_is_senior). A REQUEST to an allied captain is
# `fleet_request`; an ORDER is this.
GROUP_ORDER = _fn("group_order", "XO: the Captain's DIRECT ORDER to one of our battle groups (the groups and their captains are in the fleet board "
                                "in [The bridge now]): it takes effect at once and stands until changed or `for_s` runs out; the answer says what the "
                                "group will do or why it cannot. Only while the Captain is the senior officer present, and only when the Captain "
                                "orders it (a plain request to an allied captain is Communications' fleet_request, and he judges it). "
                                "attack: every ship that can reach `target` fires on it and the group closes to `range_km`; pin: hold the enemy "
                                "at long range; flank_left/flank_right; screen: ring `target` (a friendly ship, AQUILA); withdraw: break off in "
                                "order; regroup; reinforce: go to the group `target`; hold; auto: back to the group's own judgement.", {
    "group": {"type": "string", "description": "the group's name as the fleet board lists it (or the id of one of its ships)"},
    "order": {"type": "string", "enum": ["auto", "attack", "pin", "flank_left", "flank_right", "screen", "withdraw", "regroup", "reinforce", "hold"]},
    "target": {"type": "string", "description": "attack/pin/flank: an enemy contact id on the plot or \"group of <id>\"; screen: the ship to protect; "
                                                "reinforce: the group's name"},
    "range_km": {"type": "number", "description": "the distance (1.5-12 km) to hold from the target; leave out for the group's own choice"},
    "for_s": {"type": "number", "description": "seconds the order stands (then auto); leave out for until changed"},
    "formation": {"type": "string", "enum": ["line", "wedge", "column", "screen"]}},
    ["group", "order"])

# The officers' silent tool and the Captain's speaker for the radio nets (both the mind's own: nothing goes to the ship, docs/protocollo_voce.md §5ter, astra_mind/nets.py)
CONSOLE_LOG = _fn("console_log", "Write ONE line on a console's log, silently: nobody hears it. It shows on that console and on the Captain's datapad (the log page), where he reads "
                                 "it whenever he wants. It is for what is routine or already on the boards and changes nothing the Captain must do now: a range that moved, a "
                                 "rearm complete, a fire put out, a repair team's progress, an ally's new position or heading, net traffic you will not relay, what you set on your "
                                 "own console on your own initiative. Not for what he must hear (that is `speak`: a danger, a decision, an answer, a loss) and not for an order he "
                                 "gave (the board shows it). Telegraphic and in English, it is the ship's record, about 100 characters at most; `notice` only for the few lines "
                                 "worth a glance. Call it in the same turn as, or instead of, `speak`.", {
    "station": {"type": "string", "enum": ["xo", "helm", "ops", "tactical", "comms", "sensors", "engineering", "flight"], "description": "the console whose log it is: your own"},
    "text": {"type": "string", "description": "the line, e.g. \"T-11 range 49.5 km, opening\", \"Alpha rearmed, 8 ready\", \"Praetorian holding the screen at 4.5 km\""},
    "kind": {"type": "string", "enum": ["routine", "notice"], "description": "routine (the default) or notice (worth a glance)"}}, ["station", "text"])

NET_SPEAKER = _fn("net_speaker", "Put a radio net on the bridge's speaker, or take it off. Only when the Captain asks (\"put the flight net on the speaker\", \"voglio sentire la "
                                "flotta\", \"togli la rete di volo\"): the net's voices are then heard as they speak, nobody relays them, until he says to take it off. With the net "
                                "off the speaker, the officer who has the watch on it (Comms the fleet net, Flight Control the flight net, the XO the marines) tells him what he "
                                "must know and the rest is on the logs. The flight net is his own radio while he is in a cockpit or on the flight deck.", {
    "net": {"type": "string", "enum": ["fleet", "flight", "marines"]},
    "on": {"type": "boolean", "description": "true: on the speaker; false: off it"}}, ["net", "on"])

ALL_TOOLS = [SPEAK, STANDING, CONSOLE_LOG, NET_SPEAKER] + SHIP_TOOLS
SHIP_TOOL_NAMES = {t["function"]["name"] for t in SHIP_TOOLS} | {"group_order", "lift_go"}
SILENT_TOOLS = {"console_log"}               # tools that are no action to read back to the Captain: a turn that only wrote the log needs no "what was done"


def lift_tool(lift: Any) -> dict[str, Any]:
    """`lift_go`: the ship's computer takes the lift car the Captain is in to one of its stops. It exists only while the Captain is in a car (the game's `context.lift`),
    and its `destination` is one of THAT car's stops — the model chooses an id from the list, the code does not read the Captain's words (docs/ARCHITETTURA.md §1bis)."""
    ids = list(lift.ids)
    listing = "; ".join(s.text for s in lift.stops)
    return _fn("lift_go", f"Lift: the ship's computer takes the car the Captain is in ({lift.name}) to one of its stops: the car really moves (the doors close, it runs to the stop, "
                          "the doors open there); the Captain stays aboard. Call it when he asks to go somewhere and the stop is on this car's list, in the same reply as the computer's "
                          "one short line (speak); the result says when the car gets there. Never for a stop this car does not have, and never for the nearest stop instead.", {
        "destination": {"type": "string", "enum": ids, "description": f"the stop to take him to: {listing}"}}, ["destination"])
LOOKUPS = {"crew_locate"}            # tools that only read: what they find goes back to the officer, who then tells the Captain


# ================================================================================================ the stations (v2)
# A game build that reports `stations` in the ship state has live consoles: the persistent behaviours go through the one
# `station` tool and the legacy tools they replace are hidden; what stays are the ONE-OFF actions. A build without
# `stations` keeps the legacy tools as they were, so the mind never breaks against an older game.
SUPERSEDED = {
    "helm": {"set_course", "set_throttle", "intercept", "transit_gate"},
    "tactical": {"set_target", "set_shields", "set_point_defense"},
    "sensors": {"set_emcon"},
    "ops": {"holo_display"},
    "engineering": {"set_radiators"},
    "flight": {"launch_squadron", "recall_squadron"},
}
# how the one-off tools read next to the station tool (the division of labour: one act here, a standing behaviour there)
_ONE_OFF = {
    "fire_weapons": " ONE-OFF: fires now and is done (a salvo). To keep firing until a target falls, to fire at will, or to "
                    "keep a weapon group on a target, set tactical's `engage` / `weapons_free` mode with `station` instead.",
    "cease_fire": " ONE-OFF: stops all fire right now; `hold_fire` (station) keeps them quiet until ordered.",
    "launch_decoys": " ONE-OFF, against an incoming salvo.",
    "active_scan": " ONE-OFF ping (a focused one identifies a contact); repeated pings are sensors' `scan_sweep` mode.",
    "dispatch_damage_control": " ONE-OFF dispatch to a named incident; letting the teams choose is ops' `dc_auto` / `dc_priority` mode.",
    "route_power": " ONE system, right now; whole profiles are engineering's `power_profile` / `power_custom` modes.",
    "vent_heat": " ONE-OFF (three charges); managing the heat is engineering's `heat_auto` mode.",
}
_OWNER = {"set_course": "helm", "set_throttle": "helm", "intercept": "helm", "transit_gate": "helm", "set_alert": "xo",
          "set_shields": "tactical", "route_power": "ops", "set_target": "tactical", "fire_weapons": "tactical",
          "set_point_defense": "tactical", "launch_squadron": "flight", "recall_squadron": "flight",
          "dispatch_damage_control": "ops", "hail": "comms", "set_emcon": "sensors", "active_scan": "sensors",
          "launch_decoys": "tactical", "holo_display": "sensors", "end_transmission": "comms", "cease_fire": "tactical",
          "fleet_request": "comms", "set_radiators": "engineering", "vent_heat": "engineering",
          "dismiss_visitor": "captain", "abandon_ship": "xo", "group_order": "xo", "crew_locate": "ops", "transporter": "ops", "lift_go": "computer", "eagle_recover": "flight",
          "issue_weapon": "xo", "board_ship": "xo", "net_speaker": "comms", "console_log": "xo"}
LEGACY_INITIATIVE = {"dispatch_damage_control", "set_shields", "set_point_defense", "set_radiators", "launch_decoys"}


@dataclass
class ToolSet:
    """What the crew may call this turn."""
    tools: list[dict[str, Any]]
    names: set[str]
    available: dict[str, list[str] | None] | None       # the consoles on line (None: an older build, legacy tools only)
    lift: bool = False                                   # the Captain is in a lift car: `lift_go` is on the list and the ship's computer may speak

    @property
    def stations(self) -> bool:
        return self.available is not None


def has_groups(state: dict[str, Any] | None) -> bool:
    """The game reports our battle groups (`_astra_groups` in its state): the XO can give them orders."""
    g = (state or {}).get("_astra_groups")
    return isinstance(g, dict) and bool(g.get("your_groups"))


def tools_for(state: dict[str, Any] | None, ctx: Any = None) -> ToolSet:
    """The tools that fit the game build (`stations` in its state or not; the Transporter Room's relay only when the build has the room), and the room: inside a lift car
    (`ctx.lift`, from the game's context) the ship's computer has `lift_go`."""
    ts = _tools_for_build(state)
    if not (state or {}).get("transporter"):
        tools = [t for t in ts.tools if t["function"]["name"] != "transporter"]
        ts = ToolSet(tools, {t["function"]["name"] for t in tools}, ts.available)
    if not (state or {}).get("arms"):                      # (a game without the Captain's weapons has no armourer to call)
        tools = [t for t in ts.tools if t["function"]["name"] != "issue_weapon"]
        ts = ToolSet(tools, {t["function"]["name"] for t in tools}, ts.available)
    if not (state or {}).get("boarding_boats"):            # (nor boats to send marines in)
        tools = [t for t in ts.tools if t["function"]["name"] != "board_ship"]
        ts = ToolSet(tools, {t["function"]["name"] for t in tools}, ts.available)
    lift = getattr(ctx, "lift", None)
    if lift is not None and lift.stops:
        ts.tools.append(lift_tool(lift))
        ts.names.add("lift_go")
        ts.lift = True
    return ts


def _tools_for_build(state: dict[str, Any] | None) -> ToolSet:
    avail = station_model.available_from_state(state)
    if avail is None:
        return ToolSet(list(ALL_TOOLS), {t["function"]["name"] for t in ALL_TOOLS}, None)
    hidden: set[str] = set()
    for s in avail:
        hidden |= SUPERSEDED.get(s, set())
    tools: list[dict[str, Any]] = [SPEAK, STANDING, CONSOLE_LOG, NET_SPEAKER, station_model.tool_schema(avail)]
    if has_groups(state):
        tools.append(GROUP_ORDER)
    for t in SHIP_TOOLS:
        name = t["function"]["name"]
        if name in hidden:
            continue
        if name in _ONE_OFF:
            t = {"type": "function", "function": {**t["function"], "description": t["function"]["description"] + _ONE_OFF[name]}}
        tools.append(t)
    return ToolSet(tools, {t["function"]["name"] for t in tools}, avail)


def owner_of(name: str, args: dict[str, Any] | None = None) -> str:
    """Who acts when a tool is called (the officer id recorded as the command's `by`)."""
    if name == "station":
        return str((args or {}).get("station") or "xo")
    return _OWNER.get(name, "xo")


def initiative_names(state: dict[str, Any] | None, standing: list[dict[str, str]]) -> set[str]:
    """The tools an officer may use on their own at an event or a watch. Legacy build: the usual few plus a standing
    order's department. Consoles: the defensive one-offs and `station` (each call is then checked by
    stations.may_on_initiative against the delegation and the standing orders)."""
    ts = tools_for(state)
    allowed = ({"station", "launch_decoys", "dispatch_damage_control"} if ts.stations else set(LEGACY_INITIATIVE))
    for o in standing:
        allowed |= DEPT_TOOLS.get(o.get("department", ""), set())
    return allowed & ts.names
