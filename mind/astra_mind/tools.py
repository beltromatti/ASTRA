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
    _fn("set_course", "Helm: new heading (0-359, relative to the Aurelia system plane) and mark/pitch (-90..90).", {
        "heading_deg": {"type": "number", "minimum": 0, "maximum": 359.99},
        "mark_deg": {"type": "number", "minimum": -90, "maximum": 90}}, ["heading_deg", "mark_deg"]),
    _fn("set_throttle", "Helm: main drive throttle in percent (0 = all stop, 33 = one third, 50 = half, 100 = full).", {
        "percent": {"type": "number", "minimum": 0, "maximum": 100}}, ["percent"]),
    _fn("set_alert", "Set the ship's alert condition (lighting, stations, doors follow it).", {
        "level": {"type": "string", "enum": ["green", "yellow", "red"]}}, ["level"]),
    _fn("set_shields", "Tactical: raise/lower shields or focus them on a sector.", {
        "mode": {"type": "string", "enum": ["balanced", "forward", "aft", "port", "starboard", "dorsal", "ventral", "off"]}},
        ["mode"]),
    _fn("route_power", "Operations: power allocation of a system in percent of nominal (100 = nominal, max 150).", {
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
    _fn("launch_squadron", "Flight Control: launch a flight group on a mission.", {
        "squadron": {"type": "string", "enum": ["alpha", "bravo", "drones"]},
        "mission": {"type": "string", "enum": ["cap", "strike", "escort", "sar", "ew", "recon"]},
        "contact_id": {"type": "string", "description": "Target or escorted contact id; empty string if none"}},
        ["squadron", "mission", "contact_id"]),
    _fn("recall_squadron", "Flight Control: recall a flight group to the flight deck.", {
        "squadron": {"type": "string", "enum": ["alpha", "bravo", "drones"]}}, ["squadron"]),
    _fn("dispatch_damage_control", "Operations: send a damage-control team.", {
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
