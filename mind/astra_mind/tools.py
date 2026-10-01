"""Typed ship tools: the only way the crew changes the ship. The game (UAstraShipSubsystem) implements each one and
answers with a result; `speak` is handled by the mind itself (text -> voice)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import stations as station_model
from .crew import CREW


def _fn(name: str, desc: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required, "additionalProperties": False}}}


PATIENTS = [f"patient{i}" for i in range(1, 13)]   # the Medbay's twelve beds (the wounded speak as their bed)
MESS = [f"mess{i}" for i in range(1, 13)] + ["mess_cook"]   # the Mess Hall's places at table, and its cook

SPEAK = _fn("speak", "Someone aboard speaks aloud: an officer, a wounded crewman in the Medbay, or someone off duty in "
                     "the Mess Hall (one call per line, in speaking order). Short and specific: one sentence, and an "
                     "acknowledgement always says WHAT was set or answered (never a bare 'aye').", {
    "speaker": {"type": "string", "enum": list(CREW) + PATIENTS + MESS},
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
    _fn("hail", "Communications: open a channel to a contact (or 'fleet' for the 7th Fleet net).", {
        "contact_id": {"type": "string"},
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
                                "of your prompt): it takes effect at once and stands until changed or `for_s` runs out; the answer says what the "
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

ALL_TOOLS = [SPEAK, STANDING] + SHIP_TOOLS
SHIP_TOOL_NAMES = {t["function"]["name"] for t in SHIP_TOOLS} | {"group_order"}


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
          "dismiss_visitor": "captain", "abandon_ship": "xo", "group_order": "xo"}
LEGACY_INITIATIVE = {"dispatch_damage_control", "set_shields", "set_point_defense", "set_radiators", "launch_decoys"}


@dataclass
class ToolSet:
    """What the crew may call this turn."""
    tools: list[dict[str, Any]]
    names: set[str]
    available: dict[str, list[str] | None] | None       # the consoles on line (None: an older build, legacy tools only)

    @property
    def stations(self) -> bool:
        return self.available is not None


def has_groups(state: dict[str, Any] | None) -> bool:
    """The game reports our battle groups (`_astra_groups` in its state): the XO can give them orders."""
    g = (state or {}).get("_astra_groups")
    return isinstance(g, dict) and bool(g.get("your_groups"))


def tools_for(state: dict[str, Any] | None) -> ToolSet:
    """The tools that fit the game build (`stations` in its state or not)."""
    avail = station_model.available_from_state(state)
    if avail is None:
        return ToolSet(list(ALL_TOOLS), {t["function"]["name"] for t in ALL_TOOLS}, None)
    hidden: set[str] = set()
    for s in avail:
        hidden |= SUPERSEDED.get(s, set())
    tools: list[dict[str, Any]] = [SPEAK, STANDING, station_model.tool_schema(avail)]
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
