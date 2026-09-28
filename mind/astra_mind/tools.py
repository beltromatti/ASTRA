"""Typed ship tools: the only way the crew changes the ship. The game (UAstraShipSubsystem) implements each one and
answers with a result; `speak` is handled by the mind itself (text -> voice)."""
from __future__ import annotations

from typing import Any

from .crew import CREW


def _fn(name: str, desc: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required, "additionalProperties": False}}}


SPEAK = _fn("speak", "An officer speaks aloud on the bridge (one call per line, in speaking order).", {
    "speaker": {"type": "string", "enum": list(CREW)},
    "text": {"type": "string", "description": "The spoken line, in the Captain's language, max ~25 words"},
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
        "system_name": {"type": "string", "description": "destination system, English name (known_systems in the state, "
                                                         "Fleet's orders, or any system the Captain names)"}},
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
    _fn("fire_weapons", "Tactical: engage a contact with a weapon group. Railguns (range 10 km) and lasers (4 km) fire "
                        "`salvo` volleys at their cadence (railguns one volley every 7 s; 12 = sustained fire, about 1.5 "
                        "minutes); if the target is still beyond range they stay assigned and open fire by themselves "
                        "once it closes. Missiles (25 km) launch `salvo` missiles at once (max 8; the VLS then cycles 14 s).", {
        "weapon": {"type": "string", "enum": ["railguns", "lasers", "missiles", "torpedoes"]},
        "contact_id": {"type": "string"},
        "salvo": {"type": "integer", "minimum": 1, "maximum": 12}}, ["weapon", "contact_id", "salvo"]),
    _fn("cease_fire", "Tactical: stop all our offensive fire at once (queued volleys cancelled; point defense stays on).",
        {}, []),
    _fn("set_point_defense", "Tactical: point-defence mode.", {
        "mode": {"type": "string", "enum": ["auto", "hold", "free"]}}, ["mode"]),
    _fn("launch_squadron", "Flight Control: launch a flight group (alpha = 8 Falcon fighters, bravo = 7 Hammer torpedo "
                            "bombers, drones = 12 Wasp drones) or re-task it if airborne. Missions: cap = patrol around the "
                            "Aquila shooting down incoming missiles; strike = attack a contact (bombers make a torpedo run "
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
    _fn("hail", "Communications: open a channel to a contact (or 'fleet' for the 7th Fleet net).", {
        "contact_id": {"type": "string"},
        "intent": {"type": "string", "enum": ["identify", "warn", "demand_surrender", "request_support", "negotiate", "report"]},
        "message": {"type": "string", "description": "What we transmit, in English (the Interpreter translates)"}},
        ["contact_id", "intent", "message"]),
    _fn("end_transmission", "Communications: close the open channel (e.g. with an enemy commander).", {}, []),
    _fn("set_emcon", "Science & Sensors: emission control (silent = passive sensors only).", {
        "level": {"type": "string", "enum": ["silent", "restricted", "full"]}}, ["level"]),
    _fn("active_scan", "Science & Sensors: active radar/lidar ping or focused scan of a contact (reveals our position).", {
        "contact_id": {"type": "string", "description": "Contact id, or empty string for a full sweep"}}, ["contact_id"]),
]

ALL_TOOLS = [SPEAK] + SHIP_TOOLS
SHIP_TOOL_NAMES = {t["function"]["name"] for t in SHIP_TOOLS}
