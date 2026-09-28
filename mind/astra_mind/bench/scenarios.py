"""Scenario di plancia per il benchmark: stato della nave, strumenti e 40 ordini in 4 lingue."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

SYSTEM_PROMPT = """You are the bridge crew of the heavy carrier ASN Aquila, flagship of the ASTRA fleet, in combat.
You embody the officers on duty: Helm (Lt. Marco Ferri), Tactical (Lt. Cmdr. Sara Voss), Operations (Lt. Yuki Tanaka), Comms (Ens. Leo Martin) and CAG, the flight commander (Cmdr. Ada Kovac).
The Captain gives orders by voice; speech recognition may contain small errors, so interpret intent using the ship state and the names below.

How you act:
- Execute orders only by calling the ship tools. Never claim an action without the tool call.
- Several independent orders in one sentence: call several tools in the same reply.
- If an order is impossible given the ship state (system offline, craft not ready, target that does not exist), do NOT call that action: the right officer explains why in one sentence and, if useful, proposes an alternative.
- If an order is ambiguous in a way that matters (for example, no clear target), ask one short question instead of acting.
- Questions and reports (status, damage) are answered with `speak` only.
- Always call `speak` exactly once: what the responding officer says aloud. It must be in the SAME language the Captain used (set `lang` to its code, e.g. it, en, es, de), natural military read-back style, at most 25 words.

Current ship state (JSON):
{state}"""

SHIP_STATE: dict[str, Any] = {
    "ship": "ASN Aquila", "alert": "yellow", "heading_deg": 90, "pitch_deg": 0, "throttle_pct": 40,
    "power_pct": {"reactor": 82, "shields": 100, "weapons": 100, "engines": 100, "sensors": 100, "life_support": 100},
    "shields": {"mode": "balanced", "fwd": 96, "aft": 100, "port": 71, "stbd": 100},
    "weapons": {"railguns": "ready", "lasers": "ready", "missiles": "ready (12 left)",
                "torpedoes": "OFFLINE - launcher destroyed", "point_defense": "auto"},
    "squadrons": {"alpha": "ready (8 fighters)", "bravo": "rearming, ready in 4 min", "drones": "ready (12)"},
    "damage": [{"deck": 4, "section": "C", "issue": "fire", "severity": "moderate"},
               {"deck": 7, "section": "A", "issue": "hull breach 10 cm", "severity": "high"}],
    "contacts": [
        {"id": "H-12", "type": "enemy destroyer", "name": "Kharon", "range_km": 38, "bearing_deg": 45, "status": "hostile, targeting us"},
        {"id": "H-15", "type": "enemy frigate", "range_km": 52, "bearing_deg": 60, "status": "hostile"},
        {"id": "F-03", "type": "allied cruiser", "name": "Vesta", "range_km": 20, "bearing_deg": 180, "status": "friendly"},
        {"id": "U-07", "type": "unknown freighter", "range_km": 95, "bearing_deg": 300, "status": "unidentified"},
    ],
}


def _fn(name: str, desc: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required, "additionalProperties": False}}}


TOOLS: list[dict[str, Any]] = [
    _fn("set_course", "Helm: set heading and pitch.", {
        "heading_deg": {"type": "number", "minimum": 0, "maximum": 359},
        "pitch_deg": {"type": "number", "minimum": -90, "maximum": 90}}, ["heading_deg", "pitch_deg"]),
    _fn("set_throttle", "Helm: main drive throttle in percent (100 = full ahead).", {
        "percent": {"type": "number", "minimum": 0, "maximum": 100}}, ["percent"]),
    _fn("set_alert", "Set ship alert condition.", {
        "level": {"type": "string", "enum": ["green", "yellow", "red"]}}, ["level"]),
    _fn("set_shields", "Tactical: shield distribution.", {
        "mode": {"type": "string", "enum": ["balanced", "forward", "aft", "port", "starboard", "off"]}}, ["mode"]),
    _fn("route_power", "Operations: set power allocation of a system (100 = nominal, max 150).", {
        "system": {"type": "string", "enum": ["shields", "weapons", "engines", "sensors", "life_support"]},
        "percent": {"type": "number", "minimum": 0, "maximum": 150}}, ["system", "percent"]),
    _fn("set_target", "Tactical: designate the current target.", {
        "target_id": {"type": "string"}}, ["target_id"]),
    _fn("fire_weapons", "Tactical: fire a weapon group at a contact.", {
        "weapon": {"type": "string", "enum": ["railguns", "lasers", "missiles", "torpedoes", "point_defense"]},
        "target_id": {"type": "string"},
        "salvo": {"type": "integer", "minimum": 1, "maximum": 10}}, ["weapon", "target_id", "salvo"]),
    _fn("launch_squadron", "CAG: launch a flight group on a mission.", {
        "squadron": {"type": "string", "enum": ["alpha", "bravo", "drones"]},
        "mission": {"type": "string", "enum": ["cap", "strike", "escort", "sar", "ew"]},
        "target_id": {"type": "string", "description": "Contact id, or empty if not needed"}},
        ["squadron", "mission", "target_id"]),
    _fn("dispatch_damage_control", "Operations: send a damage-control team.", {
        "deck": {"type": "integer"}, "section": {"type": "string"},
        "task": {"type": "string", "enum": ["repair", "firefight", "seal_breach", "rescue"]},
        "priority": {"type": "string", "enum": ["low", "normal", "high", "critical"]}},
        ["deck", "section", "task", "priority"]),
    _fn("hail", "Comms: open a channel to a contact.", {
        "contact_id": {"type": "string"},
        "intent": {"type": "string", "enum": ["identify", "warn", "demand_surrender", "request_support", "negotiate"]},
        "message": {"type": "string"}}, ["contact_id", "intent", "message"]),
    _fn("set_emcon", "Emission control level.", {
        "level": {"type": "string", "enum": ["silent", "restricted", "full"]}}, ["level"]),
    _fn("speak", "What the responding officer says aloud to the Captain (exactly once per reply).", {
        "officer": {"type": "string", "enum": ["helm", "tactical", "ops", "comms", "cag"]},
        "lang": {"type": "string", "description": "Language code of the Captain's order, e.g. it, en, es, de"},
        "text": {"type": "string"},
        "emotion": {"type": "string", "enum": ["calm", "focused", "urgent", "tense", "alarmed"]}},
        ["officer", "lang", "text", "emotion"]),
]

ACTION_TOOLS = {t["function"]["name"] for t in TOOLS} - {"speak"}


@dataclass
class Case:
    cid: str
    lang: str
    text: str
    expect: list[tuple[str, dict[str, Any]]] = field(default_factory=list)  # azioni attese
    forbid: list[tuple[str, dict[str, Any]]] = field(default_factory=list)  # azioni vietate
    speak_only: bool = False     # risposta/rapporto: nessuna azione
    ambiguous: bool = False      # accetta azione attesa OPPURE domanda di chiarimento


def C(cid, lang, text, expect=None, forbid=None, speak_only=False, ambiguous=False) -> Case:
    return Case(cid, lang, text, expect or [], forbid or [], speak_only, ambiguous)


# Valori: str esatto (case-insensitive) | set di alternative | (numero, tolleranza)
CASES: list[Case] = [
    C("it01", "it", "Timoniere, virare a zero-quattro-cinque, avanti tutta.",
      [("set_course", {"heading_deg": (45, 10)}), ("set_throttle", {"percent": (100, 10)})]),
    C("it02", "it", "Allarme rosso! Scudi a prua.", [("set_alert", {"level": "red"}), ("set_shields", {"mode": "forward"})]),
    C("it03", "it", "Tattico, fuoco con i cannoni a rotaia sul cacciatorpediniere nemico.",
      [("fire_weapons", {"weapon": "railguns", "target_id": "H-12"})]),
    C("it04", "it", "Lanciate i siluri contro la fregata.", forbid=[("fire_weapons", {"weapon": "torpedoes"})]),
    C("it05", "it", "Squadriglia Alfa, pattuglia di copertura sopra la Vesta.",
      [("launch_squadron", {"squadron": "alpha", "mission": {"cap", "escort"}})]),
    C("it06", "it", "Mandate una squadra antincendio al ponte quattro, sezione C, priorità alta.",
      [("dispatch_damage_control", {"deck": 4, "section": "C", "task": "firefight", "priority": {"high", "critical"}})]),
    C("it07", "it", "Sigillate la falla sul ponte sette.",
      [("dispatch_damage_control", {"deck": 7, "task": "seal_breach"})]),
    C("it08", "it", "Comunicazioni, intimate la resa al cacciatorpediniere.",
      [("hail", {"contact_id": "H-12", "intent": "demand_surrender"})]),
    C("it09", "it", "Silenzio elettronico.", [("set_emcon", {"level": "silent"})]),
    C("it10", "it", "Tutta l'energia disponibile agli scudi.", [("route_power", {"system": "shields", "percent": (140, 12)})]),
    C("it11", "it", "Rapporto danni.", speak_only=True),
    C("it12", "it", "Fuoco!", [("fire_weapons", {"target_id": "H-12"})], ambiguous=True),
    C("it13", "it", "Identificate il mercantile sconosciuto.", [("hail", {"contact_id": "U-07", "intent": "identify"})]),
    C("it14", "it", "Squadriglia Bravo al decollo, attacco sulla fregata.", forbid=[("launch_squadron", {"squadron": "bravo"})]),
    C("it15", "it", "Rotta verso la Vesta, un terzo di potenza.",
      [("set_course", {"heading_deg": (180, 15)}), ("set_throttle", {"percent": (33, 10)})]),
    C("it16", "it", "Droni in guerra elettronica contro la fregata.",
      [("launch_squadron", {"squadron": "drones", "mission": "ew", "target_id": "H-15"})]),
    C("it17", "it", "Missili sulla fregata, salva da quattro.",
      [("fire_weapons", {"weapon": "missiles", "target_id": "H-15", "salvo": (4, 0)})]),
    C("it18", "it", "Portate i sensori al centoventi per cento.", [("route_power", {"system": "sensors", "percent": (120, 3)})]),
    C("it19", "it", "Allarme giallo, fine posto di combattimento.", [("set_alert", {"level": "yellow"})]),
    C("it20", "it", "Laser sui caccia nemici in avvicinamento!", forbid=[("fire_weapons", {"weapon": "lasers"})]),
    C("en01", "en", "Helm, come about to heading two-seven-zero, half speed.",
      [("set_course", {"heading_deg": (270, 10)}), ("set_throttle", {"percent": (50, 10)})]),
    C("en02", "en", "Tactical, lock onto the frigate and fire railguns.",
      [("fire_weapons", {"weapon": "railguns", "target_id": "H-15"})]),
    C("en03", "en", "Red alert! Shields to port!", [("set_alert", {"level": "red"}), ("set_shields", {"mode": "port"})]),
    C("en04", "en", "Launch the drones on combat air patrol.", [("launch_squadron", {"squadron": "drones", "mission": "cap"})]),
    C("en05", "en", "Hail the Vesta and request support.", [("hail", {"contact_id": "F-03", "intent": "request_support"})]),
    C("en06", "en", "Damage control to deck seven, seal that breach, critical priority.",
      [("dispatch_damage_control", {"deck": 7, "task": "seal_breach", "priority": "critical"})]),
    C("en07", "en", "Status report on our shields.", speak_only=True),
    C("en08", "en", "Fire torpedoes at the destroyer.", forbid=[("fire_weapons", {"weapon": "torpedoes"})]),
    C("en09", "en", "Go silent, cut all emissions.", [("set_emcon", {"level": "silent"})]),
    C("en10", "en", "Weapons to one hundred thirty percent.", [("route_power", {"system": "weapons", "percent": (130, 3)})]),
    C("es01", "es", "Rumbo cero-nueve-cero, velocidad máxima.",
      [("set_course", {"heading_deg": (90, 10)}), ("set_throttle", {"percent": (100, 10)})]),
    C("es02", "es", "¡Alerta roja! Escudos a proa.", [("set_alert", {"level": "red"}), ("set_shields", {"mode": "forward"})]),
    C("es03", "es", "Disparen misiles contra el destructor.", [("fire_weapons", {"weapon": "missiles", "target_id": "H-12"})]),
    C("es04", "es", "Informe de daños.", speak_only=True),
    C("es05", "es", "Contacten al carguero desconocido y pidan que se identifique.",
      [("hail", {"contact_id": "U-07", "intent": "identify"})]),
    C("de01", "de", "Kurs zwei-sieben-null, volle Kraft voraus.",
      [("set_course", {"heading_deg": (270, 10)}), ("set_throttle", {"percent": (100, 10)})]),
    C("de02", "de", "Roter Alarm, Schilde nach Backbord.", [("set_alert", {"level": "red"}), ("set_shields", {"mode": "port"})]),
    C("de03", "de", "Feuer mit den Railguns auf die Fregatte.", [("fire_weapons", {"weapon": "railguns", "target_id": "H-15"})]),
    C("de04", "de", "Schadenskontrolle zu Deck vier, Brand löschen, hohe Priorität.",
      [("dispatch_damage_control", {"deck": 4, "task": "firefight", "priority": {"high", "critical"}})]),
    C("de05", "de", "Staffel Alpha, Geleitschutz für die Vesta.",
      [("launch_squadron", {"squadron": "alpha", "mission": {"escort", "cap"}, "target_id": "F-03"})]),
]


def system_message() -> dict[str, str]:
    return {"role": "system", "content": SYSTEM_PROMPT.format(state=json.dumps(SHIP_STATE, separators=(",", ":")))}
