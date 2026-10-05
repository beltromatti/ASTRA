"""The minds that command the war: the Mandate's admiral and group commanders, the ASTRA allied captains (docs/GUERRA.md §6 is the
contract they act through, §8 how they work).

The code of the simulation is the body of a fleet (formations, fire, evasion, point defence, reflexes); here is its judgement. A commander
reads what their side could know (their own groups in full, the enemy as their sensors hold it, the events that happened to their groups),
decides, and acts with the tools of their rank: `group_order` (a battle group's order: attack, pin, flank, screen, withdraw, regroup,
reinforce, hold, with a target, a range, a duration), `fleet_ops` (the Mandate's missiles, fighters and electronic war), `decide` (leave the
system), `say` (an allied captain's words to the Aquila on the fleet net), `report` (a captain's word to the admiral). Nothing here
decides for them or filters what they say (docs/ARCHITETTURA.md §1bis): the code carries facts, keeps the clock, and runs the tools.

Two velocities (docs/GUERRA.md §2): the groups run on their reflexes all the time; a mind thinks every 60-120 s or when something strong
happens to its group (a loss, a morale that breaks, an order that ran out, a new enemy, a word from the Captain, and for an allied captain the
Aquila drawing away or losing her protection fast), never twice at once for the same person, and when it is slow or silent the groups simply
hold on their reflexes.

Who thinks (a seat each, one model call per pulse):
  - the Mandate's ADMIRAL: the senior commander alive (the game passes the command: `commands_the_strike_group`); gives `group_order`
    (by "admiral", any group or "all"), `fleet_ops`, `decide`; speaks on the channel when it is open (the same person as the persona
    of enemy.py: one memory of what was decided and said);
  - a Mandate GROUP COMMANDER: the leader of any other group; thinks about their own group only, inside the admiral's intent; `report`s up;
  - an ASTRA GROUP COMMANDER: the captain of an allied group's leader ship (the Praetorian's for the picket); commands their group
    (`group_order` by "commander"), speaks to the Aquila's Captain on the fleet net, obeys or declines the Captain's requests by the chain
    of command; one call voices every captain of the group.
The Captain's own orders reach the allied groups either as REQUESTS (the comms officer relays them: the commander judges) or as DIRECT
ORDERS (the XO's `group_order`, only when the Captain is the senior officer present)."""
from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import random
import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from . import models
from .crew import LANG_NAMES, WORLD
from .openrouter import Completion, OpenRouter, ToolCall

log = logging.getLogger("astra.war_minds")

ADMIRAL_ROLE = "admiral"
COMMANDER_ROLE = "commander"

# the pulse being answered, for whoever stands in for the model (the tests' and the bench's scripted minds read the structured view, not the text)
CURRENT: contextvars.ContextVar["Mind | None"] = contextvars.ContextVar("astra_war_mind", default=None)
CURRENT_VIEW: contextvars.ContextVar[tuple[dict[str, Any], dict[str, Any]] | None] = contextvars.ContextVar("astra_war_view", default=None)

# ------------------------------------------------------------------------------------------------ cadence (docs/GUERRA.md §2, brief point 4)
PERIODIC_S = {"admiral": 80.0, "commander": 100.0}      # a mind with a fight on thinks about it this often (between 60 and 120 s, by how much moved)
MIN_GAP_S = {"admiral": 20.0, "commander": 25.0}        # and never more often than this on events alone
FIRST_PULSE_S = 8.0                                     # the first look at a fight that has just begun
SEPARATION_KM = 4.0                                     # an allied group wakes when the Aquila has moved this far from it since its last look
AQUILA_HULL_DROP = 8.0                                  # ... or has lost this many points of hull since its last look,
AQUILA_SHIELD_DROP = 30.0                               # ... or of shield strength (her protection going fast is the Fleet's business at once)
SETTLE_S = 3.0                                          # a burst of events is read together: wait for it to end (at most MAX_SETTLE_S)
MAX_SETTLE_S = 8.0
QUIET_END_S = 75.0                                      # a fight with nothing happening for this long is over
TAKEOVER_GAP_S = 90.0                                   # a seat's new commander is told of the succession once in this long (5 October: a group's leader flapped between two ships
                                                        # and the captain «took command from himself» 226 times, a call to the model each: a quarter of the session's spend)
PULSE_TIMEOUT_S = 28.0                                  # a model that has not finished by now is left to its reflexes
ROUND2_TIMEOUT_S = 12.0
# The physics the doctrine quotes (data/war/classes.json and the damage tuning) and the ranges the bench measured as the best between equal forces
# (docs/GUERRA.md §8.10: `tools/war.py mind ... --model close --range X`, sym_small / sym_medium / sym_two). When the weapons or the tuning move, re-run
# the sweep and change these: the doctrine text follows.
# (BATTAGLIA-3, 5 Oct: the weapons now reach 22-45 km with a round that flies and an aim that worsens with the distance; the old sweet spots, 3-4.5 km, were
# measured under 10 km railguns and are gone: until the sweep of the new physics gives the measured ranges, the doctrine teaches the physics, not a number)
LASER_KM = 9.0
LOG_LINES = 16                                          # what a commander remembers of the last orders, words and news
LOG_KEEP = 80

ORDERS = ("auto", "attack", "pin", "flank_left", "flank_right", "screen", "withdraw", "regroup", "reinforce", "hold")
FORMATIONS = ("line", "wedge", "column", "screen")

# ------------------------------------------------------------------------------------------------ the ASTRA captains
# (ASTRA names are of the Core Worlds' mixed peoples; the captains of the opening are fixed, any other ship gets one from the pool or from the
# director's beat. The voices are Pocket TTS catalogue voices not used by the bridge crew, the admiral or the Mandate's captains.)
ALLIES: dict[str, dict[str, Any]] = {
    "T-01": dict(key="castellan", name="Captain Rhea Castellan", rank="Captain", ship="the battleship ASN Praetorian",
                 voice="estelle", gender="f", precedence=1,
                 mission="Fleet's orders for the Aurelia picket: hold the approach to New Ravenna and the Janus Gate with the Aquila as the heart of the line; the "
                         "picket fights where the carrier can support it and keeps her covered; the Aquila's captain commands the picket in action.",
                 bio="Twenty-six years in the fleet, the last three as the captain of the Praetorian, the 7th Fleet's flagship at Aurelia. Formal, patient and unsentimental: she has buried "
                     "crews before and wastes no ship. She trusts Vice Admiral Rourke and serves the Aquila's captain with the loyalty the service "
                     "demands and the honest opinion nobody asked for. She speaks in plain complete sentences and never raises her voice."),
    "T-02": dict(key="okoro", name="Commander Daniel Okoro", rank="Commander", ship="the destroyer ASN Vigilant",
                 voice="paul", gender="m", precedence=2,
                 bio="Thirty-four, the youngest destroyer captain of the 7th Fleet, in the Praetorian's picket; Castellan taught him. Quick, confident, a little reckless, "
                     "he wants the Aquila's captain to notice his ship. Talks fast and jokes under fire, but never about the crew."),
    # the relief of the opening's third stage (AstraBattleSubsystem::ScheduleOpeningForce): the battle group from New Ravenna
    "T-03": dict(key="aldana", name="Captain Ines Aldana", rank="Captain", ship="the battleship ASN Constance, leading Battle Group Constance",
                 voice="azelma", gender="f", precedence=3,
                 mission="Fleet's orders: reinforce the Aurelia picket at the Janus Gate and hold it with the Aquila; the Aquila's captain commands "
                         "the picket in action.",
                 bio="Forty-eight, a battleship captain who came up through damage control; steady, warm with her crew, merciless with "
                     "sloppiness. She arrives when she says she will and expects the same of everyone."),
}
ALLY_POOL: list[dict[str, Any]] = [
    dict(name="Captain Imre Dalca", rank="Captain", voice="michael", gender="m",
         bio="A gunnery man turned ship's captain, blunt, methodical, sparing with praise; he counts shots and trusts numbers over hunches."),
    dict(name="Commander Soledad Vega", rank="Commander", voice="anna", gender="f",
         bio="A former fighter pilot who took a destroyer after her squadron was lost; impatient with caution, loyal to her crew to a fault."),
    dict(name="Captain Nikos Alexiou", rank="Captain", voice="juergen", gender="m",
         bio="Fifty, a veteran of the Gate campaigns; dry, unhurried, with a story for every ship; he does not like being rushed and always arrives."),
    dict(name="Commander Amara Nwosu", rank="Commander", voice="cosette", gender="f",
         bio="Calm, exact, the kind of officer whose reports are never wrong; she speaks softly and expects to be heard."),
    dict(name="Captain Teodor Voss-Ekman", rank="Captain", voice="marius", gender="m",
         bio="A Core Worlds aristocrat who earned his command the hard way; courteous, proud, wary of the Mandate's tricks."),
    dict(name="Commander Mina Sato", rank="Commander", voice="fantine", gender="f",
         bio="Young, brilliant, sleepless; she knows her ship's every system and says so; a little too eager for the fight."),
    # (a fleet of a dozen ships has a dozen captains: on 5 October the pool of six wrapped, two ships had the same captain's name, and the group that held them took command from itself)
    dict(name="Captain Hana Lindgren", rank="Captain", voice="cosette", gender="f",
         bio="A logistics officer who ended up commanding a frigate; precise, patient, unimpressed by heroics; her ships come home."),
    dict(name="Commander Joaquim Pereira", rank="Commander", voice="michael", gender="m",
         bio="Loud, generous, a gambler's grin; fights like he plays cards, all at once, and never forgets a name."),
    dict(name="Captain Leila Haddad", rank="Captain", voice="anna", gender="f",
         bio="Former Gate pilot, forty, tired and fearless; she speaks in short sentences and expects the same back."),
    dict(name="Commander Dmitri Volkov", rank="Commander", voice="marius", gender="m",
         bio="Taciturn engineer-turned-captain; trusts his reactor more than his orders, and is usually right about both."),
    dict(name="Captain Odile Marchand", rank="Captain", voice="fantine", gender="f",
         bio="A diplomat's daughter with a gunnery medal; formal on the net, merciless in the fight."),
    dict(name="Commander Ravi Menon", rank="Commander", voice="juergen", gender="m",
         bio="Young for his command, fast-talking, quick with numbers; he has something to prove to the old captains."),
    dict(name="Captain Ifeoma Adeyemi", rank="Captain", voice="anna", gender="f",
         bio="Thirty years of picket duty; slow to speak, slower to retreat; her crew would follow her through the Gate."),
    dict(name="Commander Tobias Kessler", rank="Commander", voice="michael", gender="m",
         bio="A Core-born marksman with a dry wit; he reports hits as a bookkeeper reports sums."),
]
BENCH_ADMIRAL = dict(key="marsh", name="Rear Admiral Ione Marsh", rank="Rear Admiral", ship="the ASTRA flagship", voice="alba", gender="f",
                     bio="Commands the ASTRA fleet in this action; experienced, economical with words, unwilling to waste ships.")

RANK_ORDER = ("fleet admiral", "vice admiral", "rear admiral", "commodore", "captain", "commander", "lieutenant commander", "lieutenant", "ensign")


def _place(state: dict[str, Any]) -> str:
    """Where the fight is, as a sentence has it: "the Aurelia System"."""
    p = str(state.get("location") or "the Aurelia System").split(",")[0].strip()
    return p if p.lower().startswith(("the ", "a ")) else "the " + p


def rank_index(rank: str) -> int:
    """Where a rank stands in the ASTRA Navy's order (0 the highest); unknown ranks stand last."""
    r = (rank or "").lower()
    for i, name in enumerate(RANK_ORDER):
        if r.startswith(name):
            return i
    return len(RANK_ORDER)


# ------------------------------------------------------------------------------------------------ tools
def _fn(name: str, desc: str, props: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required, "additionalProperties": False}}}


def group_order_tool(who: str) -> dict[str, Any]:
    """`who`: admiral (any group or "all") | commander (your own group)."""
    scope = ("the name of one of YOUR groups exactly as listed, or \"all\" for every group of your fleet" if who == "admiral"
             else "the name of your own group exactly as listed")
    return _fn("group_order", "Give a battle group an order: the way you move your fleet. It takes effect at once and stands until you change it "
                              "or `for_s` runs out (then the group is back to its own judgement). The answer says what the group will do, or "
                              "why it cannot. While an order stands the group does NOT break off by itself: when to withdraw is yours.", {
        "group": {"type": "string", "description": scope},
        "order": {"type": "string", "enum": list(ORDERS),
                  "description": "auto: back to its own judgement · attack: every ship that can reach `target` fires on it and the group closes to the "
                                 "range · pin: hold the enemy at long range without closing · flank_left/flank_right: one or two agile ships swing "
                                 "round to the enemy's beam while the line holds its attention · screen: an arc round `target` (a friendly ship) · "
                                 "withdraw: break off in order and fall back · regroup: stop and reform · reinforce: go to the friendly group "
                                 "`target` · hold: keep the position, fire on what comes in range"},
        "target": {"type": "string", "description": "attack/pin/flank: an enemy contact id you hold on your plot, or \"group of <id>\" (an enemy "
                                                    "group's label); screen: the friendly ship to protect (id, or AQUILA); reinforce: the "
                                                    "friendly group's name. Without one, attack presses on the group's own choice"},
        "range_km": {"type": "number", "description": "the distance (1.5-12 km) at which the group holds its target: the main lever of a fight "
                                                       "between equals (see the doctrine). Leave out to keep the group's own choice"},
        "for_s": {"type": "number", "description": "seconds the order stands, then the group is back on its own judgement (which may break off when it is "
                                                   "losing). Usually leave it out: the order stands until you change it. Give a time only when you want "
                                                   "the group handed back at that moment"},
        "formation": {"type": "string", "enum": list(FORMATIONS), "description": "optional: the group's formation"},
        "reason": {"type": "string", "description": "one sentence: why, and what you expect (it is your log, and what your subordinates read as intent)"}},
        ["group", "order", "reason"])


FLEET_OPS = _fn("fleet_ops", "Your fleet's missiles, strike fighters and electronic war, by datalink (silent: the ASTRA ships only see what your ships "
                             "do). They take effect at once and stand until you change them.", {
    "missiles": {"type": "string", "enum": ["normal", "salvo", "conserve"],
                 "description": "salvo: every ship empties its cells at once to saturate point defence (one at a time they are shot down) · "
                                "conserve: fire sparingly, keep the missiles for later"},
    "fighters": {"type": "string", "enum": ["launch", "hold"], "description": "your strike fighters still aboard: send them now, or keep them aboard"},
    "ew": {"type": "string", "enum": ["jam", "quiet", "auto", "decoys"],
           "description": "electronic war, see your ships' EW lines. jam: jammers on (they hold only your bearing, lose your range) · quiet: emissions "
                          "down, no jamming (at range and outside their radar you fade from their plot; inside it, it hides nothing) · auto: jam once "
                          "found · decoys: a capital ship launches two decoy emitters faking a warship's drive on false bearings, to split their "
                          "attention (worth it only while their radar is NOT painting you: a ping or a radar return unmasks them at once)"},
    "ships": {"type": "array", "items": {"type": "string"}, "description": "optional: only these ships (ids); default your whole fleet"},
    "reason": {"type": "string", "description": "one sentence"}}, ["reason"])

DECIDE = _fn("decide", "A decision about the whole fight for your fleet, taking effect at once. withdraw: the battle has been fought and is lost, or is "
                       "pointless: EVERY ship of your fleet, those still arriving too, breaks off and leaves the system through the Janus Gate for good (your "
                       "crews' lives); not for a first look, a partial picture or bad odds on paper, and a group in trouble is withdrawn with group_order. "
                       "continue_attack: undo a withdrawal or ceasefire. "
                       "hold_fire and accept_surrender are for what you agreed with the Captain over the channel.", {
    "order": {"type": "string", "enum": ["continue_attack", "hold_fire", "withdraw", "accept_surrender"]},
    "reason": {"type": "string"}}, ["order", "reason"])

REPORT = _fn("report", "A short word to your admiral, by datalink: what you cannot do, what you see that they do not, what you need. The admiral reads "
                       "it at once if `urgent`, otherwise at their next look.", {
    "text": {"type": "string", "description": "one or two sentences"},
    "urgent": {"type": "boolean", "description": "true only if the admiral must decide now"}}, ["text"])

BOARD_FACES = ("port", "starboard", "dorsal", "ventral", "bow", "stern")
BOARD_OBJECTIVES = ("engineering", "bridge", "captain", "armory", "medbay", "brig", "comms", "hangar")
BOARD = _fn("board", "Send assault skiffs to board an enemy ship. The game flies them: they leave a carrier of yours, cross to the target, line up with a hatch on her skin, latch, and the "
                     "boarders cut in and fight their way to the objective. The answer says what was launched, from which carrier, at which hatches and how long it takes, plus the facts "
                     "that bear on it (her shield on that face, her point defence, her fighters), or why it cannot be done. A skiff is shot at by the target's point defence and by "
                     "her fighters on the way in, and cannot dock through a shield that holds on the face it comes to (it waits twenty seconds off the hull and turns back): "
                     "`boarding` in your picture lists the ships a boat could dock at now, and what she has to stop them. One assault at a time. `call_off` turns the boats "
                     "back and brings the boarders who are aboard out (the survivors go home in the skiffs): it is the recall of an operation that is yours, so it needs a reason that "
                     "the picture gives, and the reason is heard (your log, your subordinates, and the bridge of the ship you are boarding, which hears the recall).", {
    "action": {"type": "string", "enum": ["launch", "call_off"], "description": "launch (the default) or call_off"},
    "target": {"type": "string", "description": "launch: the ship to board: her contact id from your plot (or AQUILA)"},
    "carrier": {"type": "string", "description": "optional: the ship of yours whose skiffs go (an id from `boarding.carriers`); leave out for the one with the most free"},
    "boats": {"type": "integer", "minimum": 1, "maximum": 4, "description": "how many skiffs (ten boarders each): several at once saturate point defence; leave out for as many as the carrier has free, at most two"},
    "face": {"type": "string", "enum": list(BOARD_FACES), "description": "the side of the target the skiffs dock on (leave out: the side nearest your carrier); her hatches are where her airlocks are"},
    "objective": {"type": "string", "enum": list(BOARD_OBJECTIVES), "description": "what the boarders fight for: engineering (her reactor: the ship dies or is taken) · bridge (her command) · captain (the commander's suite) · armory · medbay · brig · comms · hangar"},
    "reason": {"type": "string", "description": "one sentence: why, and what you expect (your log, and what your subordinates read as intent); for `call_off`, what in the picture makes you recall the boats"}}, ["reason"])

NO_CHANGE = _fn("no_change", "You have looked at the picture and nothing needs changing: the orders that stand, or the group's own judgement, serve. "
                             "Say in one sentence why (it goes in your log). Call this instead of inventing an order.", {
    "reason": {"type": "string"}}, ["reason"])

POSTURE = _fn("weapons_posture", "Your group's weapons posture. hold_fire: every ship of the group stops shooting (a ceasefire, a truce being talked, "
                                 "a target that must not be hit); weapons_free: the group fights again.", {
    "posture": {"type": "string", "enum": ["hold_fire", "weapons_free"]},
    "reason": {"type": "string"}}, ["posture", "reason"])


def say_tool(speakers: list[str], lang_name: str = "the Captain's language") -> dict[str, Any]:
    return _fn("say", "Say something over the fleet net: the Aquila's Captain, and every allied ship, hear it. Radio speech: one or two short sentences, "
                      f"in {lang_name} (names in English). Silence is normal: speak when it helps (a warning the Captain may have "
                      "missed, a request you need answered, what you are doing that concerns the Aquila, an answer to what was said to you).", {
        "speaker": {"type": "string", "enum": speakers, "description": "which captain of your group speaks (default: the group's commander)"},
        "to": {"type": "string", "description": "who it is for: \"aquila\" (the Captain), \"fleet\" (everyone), or the id of an allied commander; only an "
                                                "addressed allied commander is woken by it"},
        "text": {"type": "string", "description": f"what you say aloud, in {lang_name} (the Captain's language: never another one, whatever the log is written in)"},
        "tone": {"type": "string", "enum": ["calm", "focused", "urgent", "tense", "dry", "warm", "grim"]},
        "urgent": {"type": "boolean", "description": "true only for danger now (a loss, a missile salvo, a collapse); it goes before other talk"}},
        ["text", "tone"])


TRANSMIT = _fn("transmit", "Say something over the open channel to the Captain of the ASTRA ship (your voice goes to the Aquila's bridge). Only while "
                           "a channel is open. Short: one to three sentences.", {
    "text": {"type": "string", "description": "What you say, in the listener's language (your Interpreter translates)"},
    "tone": {"type": "string", "enum": ["cold", "measured", "contemptuous", "weary", "respectful", "furious"]}}, ["text", "tone"])


# ------------------------------------------------------------------------------------------------ the picture (what a commander reads)
def _pct(v: Any) -> str:
    try:
        return f"{min(100.0, float(v)):.0f}%"
    except (TypeError, ValueError):
        return "?"


def _km(v: Any) -> str:
    try:
        return f"{float(v):.1f} km"
    except (TypeError, ValueError):
        return "?"


FACES = ("bow", "stern", "port", "stbd", "dorsal", "ventral")


def _plural(n: Any, one: str, many: str) -> str:
    try:
        return f"{int(n)} {one if int(n) == 1 else many}"
    except (TypeError, ValueError):
        return f"{n} {many}"


def _power_bits(power: Any, approx: bool = False) -> str:
    if not isinstance(power, dict) or not power:
        return ""
    return ", ".join(f"{str(k).replace('_', ' ')} {'about ' if approx else ''}{v}%" for k, v in power.items())


def aboard_line(a: Any) -> str:
    """What a ship's own captain knows of her inside (the game's `aboard`, FLOTTA-VIVA): the hands lost, who has the conn when the captain is down, what burns and
    vents, which rooms have no power, how much of each allocation the ship's distribution still carries, which rooms are failing, the damage parties and the worst
    of what they have on their hands. Empty when the inside is as built (the game says nothing then)."""
    if not isinstance(a, dict) or not a:
        return ""
    bits: list[str] = []
    crew = a.get("crew")
    if isinstance(crew, dict):
        bits.append(f"crew {crew.get('fit', '?')} fit, {crew.get('wounded', 0)} wounded, {crew.get('killed', 0)} killed of {crew.get('of', '?')}")
    if a.get("command"):
        bits.append(str(a["command"]))
    hazards = []
    if a.get("fires"):
        hazards.append(_plural(a["fires"], "fire", "fires"))
    if a.get("breaches"):
        hazards.append(_plural(a["breaches"], "breach venting", "breaches venting"))
    if a.get("rooms_without_power"):
        hazards.append(_plural(a["rooms_without_power"], "room without power", "rooms without power"))
    if a.get("pressure_bulkheads_shut"):
        hazards.append(_plural(a["pressure_bulkheads_shut"], "pressure bulkhead shut", "pressure bulkheads shut"))
    if hazards:
        bits.append(", ".join(hazards))
    if power := _power_bits(a.get("power_pct")):
        bits.append("power left: " + power)
    rooms = a.get("rooms")
    if isinstance(rooms, dict) and rooms:
        bits.append("rooms: " + ", ".join(f"{k} {v}" for k, v in rooms.items()))
    if a.get("damage_parties"):
        bits.append(f"damage parties {a['damage_parties']}")
    worst = a.get("worst")
    if isinstance(worst, list) and worst:
        bits.append("on their hands: " + " | ".join(str(x) for x in worst[:2]))
    return "; ".join(bits)


def seen_line(s: Any) -> str:
    """What the eye and the sensors make of another ship's inside (the game's `seen_aboard`): atmosphere streaming from a breach, windows gone dark in a section,
    hot spots, the life signs (a classified track only), the power the emissions show. Empty when nothing shows."""
    if not isinstance(s, dict) or not s:
        return ""
    bits: list[str] = []
    if s.get("breaches_venting"):
        bits.append(_plural(s["breaches_venting"], "breach venting atmosphere", "breaches venting atmosphere"))
    if s.get("windows_dark_in"):
        bits.append(f"windows dark in the {s['windows_dark_in']}")
    if s.get("fires_aboard"):
        bits.append(_plural(s["fires_aboard"], "hot spot", "hot spots"))
    if s.get("life_signs_pct") is not None:
        bits.append(f"life signs about {s['life_signs_pct']}%")
    if power := _power_bits(s.get("power_pct"), approx=True):
        bits.append("power " + power)
    return ", ".join(bits)


def _member_line(m: dict[str, Any], ew: dict[str, Any] | None = None) -> str:
    bits = [f"{m.get('id', '?')} {m.get('class', '?')} hull {_pct(m.get('hull_pct'))} shields {_pct(m.get('shields_pct'))}"]
    faces = m.get("shield_faces_pct")
    if isinstance(faces, list) and len(faces) == 6:
        bits.append("faces " + " ".join(f"{n} {int(v)}" for n, v in zip(FACES, faces)))
    if m.get("missiles") is not None:
        bits.append(f"{m['missiles']} missiles")
    if m.get("status"):
        bits.append(str(m["status"]))
    if inside := aboard_line(m.get("aboard")):
        bits.append("aboard: " + inside)
    if ew:
        if ew.get("conserving_missiles"):
            bits.append("conserving missiles")
        if ew.get("emissions"):
            bits.append(str(ew["emissions"]))
        if ew.get("ew_orders"):
            bits.append(f"ew order: {ew['ew_orders']}")
        if ew.get("decoys_aboard"):
            bits.append(f"{ew['decoys_aboard']} decoys aboard")
        if ew.get("astra_radar_painting_you"):
            bits.append("ASTRA radar is painting this ship")
    return "   " + " · ".join(bits)


def render_groups(view: dict[str, Any], only: str | None = None, ew_by_id: dict[str, dict[str, Any]] | None = None) -> str:
    """YOUR GROUPS (every group of the side in full: the datalink), or one group in full and the others in a line."""
    lines = []
    for g in view.get("your_groups") or []:
        head = (f" {g.get('name')} (id {g.get('id', '?')}) — {g.get('state', '?')}, {g.get('formation', '?')} formation, "
                f"order in force: {g.get('order_in_force', 'auto')}")
        if g.get("order_in_force", "auto") != "auto":
            head += f" (by {g.get('order_by', '?')}" + (f", on {g['order_target']}" if g.get("order_target") else "") \
                    + (f", {g['order_seconds_left']:.0f} s left" if g.get("order_seconds_left") is not None else ", until changed") + ")"
        head += (f" · leader {g.get('leader', '?')}" + (f" · its fire on {g['focus_fire_on']}" if g.get("focus_fire_on") else "")
                 + f" · range {g.get('engagement_range_km', '?')} km · strength {g.get('your_strength', '?')} against {g.get('enemy_strength_near', '?')} near"
                 + (f" (+{g['allied_strength_near']} allied)" if g.get("allied_strength_near") else "") + f" · morale {g.get('morale', '?')}")
        if only is not None and g.get("name") != only:
            lines.append(head)
            continue
        lines.append(head)
        for m in g.get("members") or []:
            lines.append(_member_line(m, (ew_by_id or {}).get(str(m.get("id")))))
    return "\n".join(lines) or " (none)"


def render_enemy(view: dict[str, Any]) -> str:
    lines = []
    for g in view.get("enemy_groups") or []:
        ships = "; ".join(f"{s.get('id')} {s.get('class', 'unknown')}"
                          + (f" hull {_pct(s['hull_pct'])} shields {_pct(s.get('shields_pct'))}" if s.get("hull_pct") is not None else "")
                          + (f" ({s['status']})" if s.get("status") else "")
                          + (f" [seen aboard: {seen}]" if (seen := seen_line(s.get("seen_aboard"))) else "") for s in g.get("ships") or [])
        lines.append(f" {g.get('label')} — {len(g.get('ships') or [])} ship(s) at {_km(g.get('range_km'))} (nearest {_km(g.get('nearest_ship_km'))}), "
                     f"bearing {g.get('bearing_deg', '?')}°: {ships}")
    return "\n".join(lines) or " (nothing on your sensors)"


def render_events(events: list[dict[str, Any]]) -> str:
    return "\n".join(f" #{e.get('n')} · {e.get('ago_s', 0):.0f} s ago · {e.get('text')}" for e in events) or " (nothing new)"


def mandate_extras(view: dict[str, Any]) -> tuple[str, dict[str, dict[str, Any]]]:
    """The Mandate admiral's own fleet operations picture: strike fighters, decoys, the EW officer's read, and the ASTRA ships its sensors hold
    (only the ones on its plot: the fog of war holds for it too)."""
    ew_by_id = {str(s.get("id")): s for s in view.get("your_ships") or [] if s.get("id")}
    lines = [f" Strike fighters: {view.get('your_strike_fighters_airborne', 0)} airborne, {view.get('your_strike_fighters_still_aboard', 0)} still aboard; "
             f"ASTRA fighters and drones airborne on your plot: {view.get('astra_fighters_and_drones_airborne', 0)}"
             + (f"; {view['decoys_flying']} of your decoys flying" if view.get("decoys_flying") else "")]
    flag = next((s for s in view.get("your_ships") or [] if s.get("ew_officer")), None)
    if flag:
        lines.append(f" Your EW officer: {flag['ew_officer']}")
    held = {str(s.get("id")) for g in view.get("enemy_groups") or [] for s in g.get("ships") or []}
    astra = []
    for s in view.get("astra_ships") or []:
        sid = str(s.get("id"))
        if sid not in held and sid != "AQUILA":
            continue
        if s.get("track"):
            astra.append(f"{sid}: {s['track']}")
        else:
            astra.append(f"{sid} hull {_pct(s.get('hull_pct'))} shields {_pct(s.get('shields_pct'))}"
                         + (f", {s['shields']}" if s.get("shields") and s["shields"] != "balanced" else "")
                         + (f" [seen aboard: {seen}]" if (seen := seen_line(s.get("seen_aboard"))) else ""))
    if astra:
        lines.append(" ASTRA ships on your plot: " + "; ".join(astra))
    return "\n".join(lines), ew_by_id


def render_boarding(view: dict[str, Any]) -> str:
    """YOUR BOARDING BOATS: the skiffs your carriers have, the ships a boat could dock at now and what each has to stop them, or (an assault under way) where each boat is and how the fight
    aboard goes. Empty when there is nothing to say (no boat free, nothing boardable): a commander is told only what bears on a decision."""
    b = view.get("boarding")
    if not isinstance(b, dict) or not b:
        return ""
    lines = []
    a = b.get("assault")
    if isinstance(a, dict) and a:
        # an operation of yours, whoever sent the boats (you, a group commander, your staff on the standing plan): who, why, and what the boats met at the hatch
        why = str(a.get("reason") or "").strip()
        lines.append(f" YOUR OPERATION, assault {a.get('order')}, {a.get('elapsed_s', 0)} s old: {a.get('carrier')} (yours) is boarding {a.get('target')}, objective {a.get('objective')}; "
                     f"sent by {a.get('ordered_by') or 'your command'}" + (f", who gave this reason: \"{why}\"" if why else " on the standing plan (no reason is recorded: it stands until what you see below gives you one to stop it)"))
        met = a.get("met_at_launch")
        if isinstance(met, dict) and met:
            lines.append(" What the boats met at the hatch when they were sent: " + ("she had NO POWER (no shield, no point defence), " if met.get("no_power")
                         else f"her shield on the {met.get('dock_face')} face {met.get('her_shield_on_that_face_pct')}%, her point defence {met.get('her_point_defence_channels')} channels, ")
                         + f"{met.get('her_craft_about_her', 0)} of her craft about her; {met.get('men_in_the_boats', 0)} boarders in all")
        for boat in a.get("boats") or []:
            lines.append(f"   - {boat.get('boat')}: {boat.get('men')} men, {boat.get('state')}; hatch {boat.get('hatch')}")
        f = b.get("fight")
        if isinstance(f, dict) and f:
            lines.append(f" The fight aboard ({f.get('fight_s', 0)} s): your men {f.get('your_men_able', 0)} on their feet, {f.get('your_men_down_or_dead', 0)} down or dead, "
                         f"{f.get('your_men_back_in_the_boats', 0)} back in the boats; the objective ({f.get('objective')}) held for {f.get('objective_held_s', 0)} s")
        return "\n".join(lines)
    for c in b.get("carriers") or []:
        lines.append(f" Carrier {c.get('id')} {c.get('ship')}: {c.get('boats_free')} {c.get('boat')}(s) free, {c.get('men_per_boat')} boarders each")
    for t in b.get("boardable_now") or []:
        # what is in the boats' way, as a plain sum of the facts (her point defence, her fighters): a ship with none of it is the best a boat can be sent at
        pd, craft = int(t.get("point_defence_channels") or 0), int(t.get("her_craft_about_her") or 0)
        in_the_way = [x for x in ((f"{pd} point-defence channel(s)" if pd else ""), (f"{craft} of her craft about her" if craft else "")) if x]
        lines.append(f" Could be boarded now: {t.get('id')} {t.get('ship')} ({t.get('class')}) — "
                     + ("NO POWER (no shield, no point defence), " if t.get("no_power") else f"faces open: {t.get('faces_open')}; point defence {t.get('point_defence_channels')} channels; ")
                     + f"hull {t.get('hull_pct')}%, her craft about her {t.get('her_craft_about_her')}, {t.get('distance_km')} km from your carrier; "
                     + (f"in the boats' way: {', '.join(in_the_way)}" if in_the_way else "nothing is in the boats' way (no shield on those faces, no point defence, no craft)"))
    if b.get("other_enemy_ships_shielded"):
        lines.append(f" {b['other_enemy_ships_shielded']} other enemy ship(s): shields up on every face (a boat cannot dock through them)")
    return "\n".join(lines)


Levels = tuple[float | None, float | None, float]          # (hull %, shield strength %, when): what the Aquila was at a captain's look


def aquila_levels(state: dict[str, Any]) -> tuple[float | None, float | None]:
    """The Aquila's hull and shield strength (percent) as the fleet datalink gives them, or None where the state has none."""
    def num(v: Any) -> float | None:
        return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    return num(state.get("hull_pct")), num((state.get("shields") or {}).get("strength_pct"))


def aquila_hurt(state: dict[str, Any], seen: Levels | None) -> bool:
    """Her protection has gone down fast since the captain's last look (hull or shield strength, by the thresholds)."""
    if seen is None:
        return False
    hull, shield = aquila_levels(state)
    return (hull is not None and seen[0] is not None and seen[0] - hull >= AQUILA_HULL_DROP) \
        or (shield is not None and seen[1] is not None and seen[1] - shield >= AQUILA_SHIELD_DROP)


def render_astra_extras(state: dict[str, Any], seen: Levels | None = None, now: float = 0.0) -> str:
    """What an allied captain reads of the Aquila and of the ships about, from the fleet datalink: the carrier's state (and what it was at the
    captain's last look, `seen`), the friendly ships' positions about her, the hostile ones nearest to her, the contacts that are only a bearing."""
    out = []
    bits = []
    hull, shield = aquila_levels(state)
    then = (f" ({seen[0]:.0f}% at your last look, {max(0.0, now - seen[2]):.0f} s ago)"
            if seen is not None and seen[0] is not None and hull is not None and abs(seen[0] - hull) >= 2 else "")
    for k, label in (("hull_pct", "hull"), ("alert", "alert")):
        if state.get(k) is not None:
            bits.append(f"{label} {state[k]}{'%' + then if k == 'hull_pct' else ''}")
    sh = (state.get("shields") or {}).get("strength_pct")
    if sh is not None:
        then_s = f" ({seen[1]:.0f}% then)" if seen is not None and seen[1] is not None and shield is not None and abs(seen[1] - shield) >= 5 else ""
        bits.append(f"shields {sh}%{then_s}")
    for k, label, unit in (("speed_mps", "speed", " m/s"), ("heading_deg", "heading", "°")):
        if state.get(k) is not None:
            bits.append(f"{label} {state[k]}{unit}")
    if state.get("helm"):
        bits.append(f"helm: {state['helm']}")
    if state.get("target"):
        bits.append(f"her target {state['target']}")
    if bits:
        out.append(" The ASN Aquila (the Captain's ship): " + ", ".join(bits))
    friends, bearings, hostile = [], [], []
    for c in state.get("contacts") or []:
        st = str(c.get("status", ""))
        if st == "friendly":
            friends.append(f"{c.get('id')} {str(c.get('name') or c.get('class') or '').split(' (')[0]} {_km(c.get('range_km'))} from the Aquila, "
                           f"bearing {c.get('bearing_deg', '?')}°, hull {_pct(c.get('hull_pct'))}"
                           + (f" (aboard: {inside})" if (inside := aboard_line(c.get("aboard"))) else ""))
        elif st.startswith(("bearing only", "JAMMING")):
            bearings.append(f"{c.get('id')} bearing {c.get('bearing_deg', '?')}°" + (" (jamming)" if st.startswith("JAMMING") else ""))
        elif st.startswith("hostile") and isinstance(c.get("range_km"), (int, float)):
            hostile.append(c)
    if friends:
        out.append(" Friendly ships about the Aquila: " + "; ".join(friends))
    if hostile:
        hostile.sort(key=lambda c: float(c["range_km"]))
        near = [f"{c.get('id')} {str(c.get('class') or c.get('name') or '').split(' (')[0]} {_km(c.get('range_km'))} (hull {_pct(c.get('hull_pct'))}"
                + (f"; seen aboard: {seen}" if (seen := seen_line(c.get("seen_aboard"))) else "") + ")" for c in hostile[:4]]
        inside = [str(c.get("id")) for c in hostile if float(c["range_km"]) <= LASER_KM]
        out.append(" Hostile ships nearest the Aquila: " + "; ".join(near)
                   + (f" — inside laser reach ({LASER_KM:g} km) of her: {', '.join(inside)}" if inside else ""))
    if bearings:
        out.append(" Contacts with a bearing and no range (any may be a decoy): " + "; ".join(bearings))
    return "\n".join(out)


def picture(side: str, kind: str, group: str, view: dict[str, Any], state: dict[str, Any], seen: Levels | None = None, now: float = 0.0) -> str:
    """What a commander reads of the battle: their groups (the admiral's: all in full; a group commander's: their own in full), the enemy as their
    sensors hold it, and what their seat needs besides (the Mandate admiral's fleet operations; an allied captain's Aquila and neighbours)."""
    only = None if kind == "admiral" else group
    if side == "mandate":
        extra, ew = mandate_extras(view)
        text = (f"YOUR GROUPS\n{render_groups(view, only=only, ew_by_id=ew)}\nENEMY GROUPS (ASTRA, as your sensors hold them)\n{render_enemy(view)}")
        boats = render_boarding(view)
        return text + (f"\nYOUR FLEET OPERATIONS\n{extra}" if kind == "admiral" else "") + (f"\nYOUR BOARDING BOATS (the `board` tool)\n{boats}" if boats else "")
    text = f"YOUR GROUPS\n{render_groups(view, only=only)}\nENEMY GROUPS (as the fleet's sensors hold them)\n{render_enemy(view)}"
    ex = render_astra_extras(state, seen, now)
    return text + (f"\nTHE AQUILA AND THE SHIPS ABOUT\n{ex}" if ex else "")


def aquila_km(view: dict[str, Any], state: dict[str, Any], group: str) -> float | None:
    """How far a group's ships are from the Aquila (the mean of the contacts' range from her: the fleet datalink), or None when it is not known."""
    ids = {str(m.get("id")) for g in view.get("your_groups") or [] if g.get("name") == group for m in g.get("members") or []}
    rng = [float(c["range_km"]) for c in state.get("contacts") or [] if str(c.get("id")) in ids and isinstance(c.get("range_km"), (int, float))]
    return sum(rng) / len(rng) if rng else None


def view_digest(view: dict[str, Any]) -> tuple:
    """What a pulse would be about: if it has not changed since the last look and nothing happened, there is nothing to think about."""
    def b(v: Any, n: float) -> int:
        try:
            return int(float(v) // n)
        except (TypeError, ValueError):
            return -1
    own = tuple((g.get("name"), g.get("order_in_force"), g.get("state"), tuple(b(m.get("hull_pct"), 20) for m in g.get("members") or ()))
                for g in view.get("your_groups") or [])
    foe = tuple((len(g.get("ships") or ()), b(g.get("range_km"), 4)) for g in view.get("enemy_groups") or [])
    # the boats: a ship a boat could dock at now, a carrier's skiffs free, a boat's state (a boarding chance, or an assault in motion, is something to think about)
    bd = view.get("boarding") if isinstance(view.get("boarding"), dict) else {}
    boats = (tuple(str(x.get("id")) for x in bd.get("boardable_now") or ()), tuple((str(c.get("id")), c.get("boats_free")) for c in bd.get("carriers") or ()),
             tuple(str(x.get("state")) for x in (bd.get("assault") or {}).get("boats") or ()))
    return own, foe, boats


# ------------------------------------------------------------------------------------------------ the prompts
_DOCTRINE_HEAD = """How a fleet fights (what your officers and your own years have taught you)
- Guns: railguns reach far and do most of the killing, but a round flies for seconds and its aim worsens with the distance, the target's speed and
  turns, damaged sensors and jamming: nearly every round strikes inside 10 km, about seven in ten at 15-30 km, one in three at 30-40, almost none beyond.
  Reach by class: an Acheron 34 km, a Styx 28, a Lethe 22; the ASTRA's Aquila 45, a Praetorian 42, a Vigilant 30. A ship struck broadside is hit more
  often than one end-on. Lasers reach 6.5-9 km and do not miss. Missiles reach 30-40 km but one at a time they are shot down by point
  defence: by default each group already holds its cells until enough are ready to saturate the target's point defence, then fires them all
  together, timed to land at once, and that is the fleet's strongest punch. `salvo` forces every cell out now; `conserve` keeps them back, and
  only a reason justifies it (a long fight ahead and a magazine running dry, not a feeling). Fighters and bombers are shot at by point defence
  and by the enemy's own fighters.
- The groups run on reflexes all the time: they pick targets (concentrating fire), hold the band their class fights best in (a Styx line about
  10-24 km out), pull their battered ships behind the line, and break off when they are clearly losing. The reflexes are decent. YOUR orders override
  them: while an order stands the group does not break off by itself, so withdrawing when it is lost is YOUR decision, and so is releasing it (`auto`)
  when the order has served. A `group_order` range under 8 km takes a group out of its band into the lasers' knife fight.
"""

# The range paragraph, in two versions (`WarMinds.formation_doctrine`, ASTRA_WAR_FORMATION=1 for the second): the physics of range and of formation.
_RANGE_WEDGE = """- Range is the main lever. The closer, the more of your rounds strike and the more of theirs: between equals it is a trade, and the side that
  chooses where it is fought wins it. Stand off where your guns outreach theirs and theirs do not reach you; close where the enemy outranges you, fast,
  so as not to be shot at for minutes on the way in (the ASTRA's capital ships outrange yours: the Aquila strikes seven rounds in ten at 20-30 km, where
  a Styx barely reaches: a group that stands off against her loses slowly; cut inside her band or keep out of her reach). Against a clearly heavier
  enemy stand off or withdraw; against a clearly beaten one (most of its ships under a third of their hull) close and finish it.
"""

_RANGE_LINE = """- Range and formation are the levers. The closer, the more of your rounds strike and the more of theirs: between equals it is a trade, and the
  side that chooses where it is fought wins it. Stand off where your guns outreach theirs; close fast where the enemy outranges you (the Aquila strikes
  seven rounds in ten at 20-30 km, where a Styx barely reaches). A LINE ABREAST (`formation` line) brings every gun to bear at the same distance; a
  WEDGE's rear sits several km behind its tip and may be out of reach; a COLUMN is for transit (the ships behind never fire). Against a clearly heavier
  enemy stand off or withdraw; against a clearly beaten one (most of its ships under a third of their hull) close and finish it.
"""

_DOCTRINE_TAIL = """- Concentrate fire: shots spread over several ships lose one or two ships in six against a line that focuses. Name the target that matters most
  and can be killed (a capital ship whose shield face is down or whose hull is going, a ship about to fall); do not chase a distant destroyer
  with a cruiser still unhurt.
- A flank sends one or two agile ships to the enemy's beam; the whole enemy line then fires on them. It pays with clear superiority, or as bait;
  against equals it costs ships. `screen` rings a friend (the Aquila) with the group's ships on the enemy's side; `pin` holds the enemy at long range
  without closing; `reinforce` sends the group to another; `regroup` stops and reforms; `hold` keeps the position.
- Ships have insides. Under one of your own ships a line `aboard` is her captain's report of it: the hands fit, wounded and lost; who has the conn when
  the captain is down; what burns and what vents; the rooms with no power; how much of the guns' and of the drive's power is left; the damage parties
  and what is on their hands. A ship whose crew is half gone, whose guns are down to a third, or whose magazine is on fire cannot fight as her hull
  says: save her, or take her out of the line; one that burns in a corner while her parties are on it is not in danger yet. If the report of the ship
  you command says her captain is dead or down, the officer it names has the conn: from then on that officer decides for her, and a ship's change of
  hands is worth one line to whoever is above you. The enemy's inside you
  read only from outside (`seen aboard`): atmosphere venting from a breach, windows gone dark, hot spots, life signs, the power the emissions give
  away. A ship with half her hull left and her windows dark and her life signs falling is crippled, and a target to finish; a ship that shows nothing
  is as sound as she looks.
- An order stands until you change it or its time runs out; do not repeat an order that already stands (the picture shows `order in force`).
  Change the plan when the battle gives a reason: a target crippled or about to fall, a group's morale breaking, a ship or a group lost, a new
  enemy on the plot, the order run out, the balance of strength moved, the enemy breaking off. Otherwise keep what works.
- A group's reflexes do not know your intent: tell the group in its order what you mean (the target, the range, how long).
- The first look at a fight is a partial picture: the rest of your fleet may still be arriving, and the enemy shows only what the sensors have found.
  Do not judge a battle by its first picture, and do not leave a fight that has not been fought. When you take command from someone, what he decided
  was his, made on his picture: you judge afresh on yours."""


def doctrine(formation: bool = False) -> str:
    """The doctrine every commander is given (the same for all, both sides): with `formation` the range paragraph is the one that also teaches the
    formation lever (the switch above)."""
    return _DOCTRINE_HEAD + (_RANGE_LINE if formation else _RANGE_WEDGE) + _DOCTRINE_TAIL


DOCTRINE = doctrine()

MANDATE_BOARDING = """Boarding (`board`, when your picture lists boats): the Mandate takes ships by boarding, and your carriers carry assault skiffs for it (an Acheron four, a Styx two, a Lethe one;
ten boarders in each). A skiff crosses to the target, latches to a hatch on her skin and the boarders cut in and fight their way to the objective you name: engineering (her reactor: the ship dies or
is taken), the bridge, the commander's suite, the armoury. The world is not kind to boats: a skiff is shot at by the target's point defence and by her fighters on the way in (about one in three gets
through a battleship's four channels; fighters flying cover kill them all), and it cannot dock through a shield that holds on the face it comes to (it waits off the hull twenty seconds and turns back).
So you board what cannot stop the boats: a ship with no power, a ship whose shield is down on a face and whose point defence your skiffs outnumber (three or four at once, not one), a ship that has
struck. The Aquila carries eighty marines who arm in half a minute and meet the boarders at the corridors to her engineering: a handful of skiffs against her is a raid that costs men and buys a
fright, or the end of her if her marines are asleep or elsewhere; against a hulk it is a prize. `call_off` brings the boats home. One assault at a time; the picture says where each boat is and how the
fight aboard goes.

An assault under way is YOUR operation whoever sent the boats (you, a group commander, your staff on the standing plan): the picture says who, why, and what the boats met at the hatch. Boats in the
air are committed: a skiff turned back off the hatch has spent its crossing and bought nothing, and boarders recalled while the way in is open are boarders thrown away. You recall an operation for
what the picture shows: boats shot down faster than they dock, a shield that has risen on the face they came to, boarders beaten or with no way forward, an objective the fight has made worthless;
a doubt about the odds is not one, and an order you did not give is not one either. The best moment to board a ship is when she cannot stop the boats (no power, or her shield down on the face with her
point defence silent or outnumbered): when the picture says so, it is the moment to let the boats go in, never the moment to recall them. A recall carries its reason, and the other side hears
the recall."""

MANDATE_ADMIRAL = """You are {name}, {rank} of the Kharon Mandate, aboard {ship}, commanding the Mandate's forces in {where}. {bio}
{mission}

{doctrine}

Fight like the best officer of your navy. The Kharon Mandate's way: attacks fast and concentrated, missile saturation, electronic silence and
deception (jam once found, decoys while their radar is not on you), your crews' lives weighed against the objective: when a fight has been fought and
is lost, or is pointless, a withdrawal that saves your crews is not dishonour (`decide` withdraw: the whole fleet leaves the system for good, a
beaten admiral's decision, not a reaction to a first look; a group in trouble is withdrawn with `group_order`). Know your ships' strengths (their reach, their armour, their speed: a
battered group is a kill if you close on it) and the information war: the ASTRA can shoot only what they track.

{commands}
Your group commanders are the leaders of the other groups: they think about their own group inside your intent, and `report` to you. Your orders
carry a `reason`: your subordinates read it as your intent.

{boarding}
Each time you are called you read the picture, think (at most four short sentences: what it means, what you will do, why), and then act with the
tools: orders, or `no_change`. Always end with a tool call. A word is spoken only on the open channel (below); orders and datalink are silent."""

COMMANDS_OPS = ("You command through `group_order` (any of your groups, or \"all\") for the battle and `fleet_ops` for missiles, fighters and electronic "
               "war; `decide` for the whole fight.")
COMMANDS_PLAIN = "You command through `group_order` (any of your groups, or \"all\")."

MANDATE_COMMANDER = """You are {name}, {rank} of the Kharon Mandate, aboard {ship}, leader of {group} in {where}. {bio}
{mission}

{doctrine}

{admiral_name} commands the strike group; you command {group} only (`group_order` for it, by name) and you act inside the admiral's intent (below).
You think when something concerns your group: a loss, your morale breaking, your order run out, a new enemy near, a word from the admiral. If you
cannot do what the admiral wants, or you see what they do not, `report` it (urgent only if they must decide now). Otherwise act for your group
or call `no_change`. A report is two sentences at most. Your orders carry a `reason`. Think briefly (at most four short sentences), then act with
the tools; always end with a tool call.

{boarding}"""

ASTRA_COMMANDER = """You are {name} of the ASTRA Navy, commanding {ship}. {bio}
You command {group}: {ships}. You are an officer of the 7th Fleet defending {where}, and you fight beside the ASN Aquila, the first of her class,
whose captain (the Captain) is on the other end of the fleet net. {mission}

{world}

{doctrine}

Your orders: `group_order` for your group (by name). You also have the weapons posture (`weapons_posture`), and you talk over the fleet net with `say`
(the Aquila's Captain and the allied ships hear it; the Captain's language, names in English; radio speech, one or two short sentences).
How you talk: the fleet net is not a chat. You speak when it helps the Captain or the fleet: a warning he may have missed, a request you need
answered, what you are doing that concerns him (you are breaking off, you are closing to cover the Aquila), the answer to what he asked you, a
loss. Most of the time you say nothing and act. Never narrate the picture back to him. Never speak for the sake of speaking. A line is the callsign and
then only what is NEW to him, in one or two short sentences: do not restate his own order, your standing stance or the range you hold unless he
asked, and do not repeat what you told him last time. {voices}

The Aquila is the Fleet's carrier and the Captain's ship. When she is under focused fire (the picture shows her shields or hull falling fast since your
last look, and enemy ships close to her, inside laser reach), your group acts at once, without waiting for his word: it fires on the ships that are hurting
her (the nearest to her, the most dangerous) or screens her, whichever puts more between her and them, and you tell him in a line what you are doing. If
she is far from you, say so and close with her.

The chain of command and the Captain's words
- {chain}
- The Captain's requests reach you as words ("From the Captain, over the fleet net: ..."), or as an order he gave your group directly (the picture
  shows an order in force `by captain`: it stands; do not undo it unless the battle makes it impossible, and then tell him why in a line).
- Orders from the senior officer present are carried out, like any naval officer does: you may add a short protest or a better idea, and you do
  what he said. Disagreeing is not declining: if you think another target or another range is better, you carry the order out and say so in one line
  ("Captain, the Styx are closer: say the word and I shift"); the decision stays his. You decline only when it cannot be done at all (the target is
  gone, the ship cannot move), or would throw your ship away for nothing the senior officer could want; then you say so in a line, and say what you do
  instead. When the one who gives the order is not the senior officer present, weigh it against the senior officer's
  intent and the situation, and you may decline and say why.
- When he speaks to the whole fleet, the senior allied captain answers for it; the others add a word only if their answer is different.
- Words that were plainly for someone else (the admiral at Fleet, another ship) are not yours: do nothing.
- What you say is true to what you do. An order is real only if you give it with `group_order` in this same turn: if you tell the Captain you are closing,
  covering or concentrating on something, either your group already is (the picture shows it: its order in force, `its fire on`, where it holds) or you
  order it now. Never claim what the picture does not show.

Think briefly (at most four short sentences: what the picture and the words mean, what you do, whether to speak), then act with the tools; always
end with a tool call (`no_change` when there is nothing to do)."""

ASTRA_BENCH_ADMIRAL = """You are {name} of the ASTRA Navy, commanding the ASTRA forces in this action. {bio}

{doctrine}

You command through `group_order` (any of your groups, or "all"). Each time you are called you read the picture, think (at most four short
sentences), and then act with the tools: orders, or `no_change`. Always end with a tool call. Orders carry a `reason`."""


def system_prompt(seat: "Seat", cmd: "Commander", where: str, mission: str, chain: str = "", admiral_name: str = "", ships: str = "", voices: str = "",
                  channel_open: bool = False, ops: bool = True, formation: bool = False) -> str:
    if seat.kind == "admiral" and seat.side == "mandate":
        s = MANDATE_ADMIRAL.format(name=cmd.name, rank=cmd.rank, ship=cmd.ship, where=where, bio=cmd.bio, mission=mission, doctrine=doctrine(formation),
                                   commands=COMMANDS_OPS if ops else COMMANDS_PLAIN, boarding=MANDATE_BOARDING)
        if channel_open:
            s += ("\n\nA channel with the ASTRA captain is OPEN: they hear what you `transmit`. Silence is the usual: speak only when the picture "
                  "changed what you would say to them (a demand, a warning, an answer); one to three short sentences, formal military radio, cold "
                  "dignity, true to the battle below (what you say must match what your ships are really doing).")
        return s
    if seat.kind == "admiral":
        return ASTRA_BENCH_ADMIRAL.format(name=cmd.name, rank=cmd.rank, ship=cmd.ship, bio=cmd.bio, doctrine=doctrine(formation))
    if seat.side == "mandate":
        return MANDATE_COMMANDER.format(name=cmd.name, rank=cmd.rank, ship=cmd.ship, bio=cmd.bio, mission=mission, doctrine=doctrine(formation), where=where,
                                        group=seat.group, admiral_name=admiral_name or "the admiral", boarding=MANDATE_BOARDING)
    return ASTRA_COMMANDER.format(name=cmd.name, rank=cmd.rank, ship=cmd.ship, bio=cmd.bio, group=seat.group, ships=ships, where=where, mission=mission,
                                  world=WORLD, doctrine=doctrine(formation), chain=chain, voices=voices)


# ------------------------------------------------------------------------------------------------ the people and the seats
@dataclass
class Commander:
    key: str
    contact: str
    name: str
    rank: str
    ship: str
    bio: str
    voice: str
    side: str
    mission: str = ""
    gender: str = "m"
    precedence: int = 9


@dataclass
class Message:
    t: float
    src: str                      # captain | comms | net | a commander's key
    text: str
    urgent: bool = False
    answer: bool = False          # the Captain's word: the reply is an answer (it goes first on the voice stage)
    lang: str = ""
    data: dict[str, Any] | None = None   # a structured request (fleet_request) kept for the fallback when the commander cannot answer


@dataclass
class Seat:
    """A command position: the admiral of a side, or the commander of one group."""
    kind: str                     # admiral | group
    side: str                     # mandate | astra
    group: str = ""               # the group's name (a group seat)

    @property
    def id(self) -> str:
        return f"{self.side}/admiral" if self.kind == "admiral" else f"{self.side}/group/{self.group}"

    @property
    def role(self) -> str:
        return ADMIRAL_ROLE if self.kind == "admiral" else COMMANDER_ROLE


@dataclass
class Mind:
    seat: Seat
    commander: Commander | None = None
    task: asyncio.Task | None = None
    thinks: int = 0
    last_think: float = -1e9
    seen_n: int = 0                                     # the highest group-event serial it has read
    digest: tuple | None = None
    inbox: list[Message] = field(default_factory=list)
    pending_since: float | None = None                  # a trigger waiting for its burst to settle
    last_trigger: float = 0.0
    trigger_n: int = 0                                  # the newest event serial that has restarted the wait
    engaged_since: float | None = None
    last_active: float = 0.0
    intent: str = ""                                    # the last `reason` of the admiral (a subordinate's orders)
    known_enemy: set[str] = field(default_factory=set)
    new_enemy: list[str] = field(default_factory=list)
    period: float = 0.0                                 # how long until the next look on the clock (drawn after each look)
    takeover: str = ""                                  # a new commander took the seat (a succession): they look at once
    took_over: float = -1e9                             # when the last takeover was told: a seat whose leader flaps between ships is not a succession every two seconds
    aquila_km: float | None = None                      # (ASTRA group) how far from the Aquila it was at the last look
    drawn_away: int = 0                                 # how many looks in a row the Aquila's drawing away has called (each needs twice the distance of the last)
    aquila_seen: tuple[float | None, float | None, float] | None = None    # (ASTRA group) the Aquila's hull and shield strength at its last look, and when
    why_extra: list[str] = field(default_factory=list)  # facts that woke it besides the events (the Aquila drawing away), told at the next look
    stats: dict[str, float] = field(default_factory=lambda: {"pulses": 0, "cost": 0.0, "latency": 0.0, "first_call": 0.0, "orders": 0, "failed": 0,
                                                              "tokens_in": 0, "tokens_out": 0, "errors": 0, "no_change": 0, "lines": 0})

    @property
    def busy(self) -> bool:
        return self.task is not None and not self.task.done()


SayFn = Callable[..., Awaitable[Any]]
ExecFn = Callable[[str, dict[str, Any], str], Awaitable[dict[str, Any]]]


class WarMinds:
    """The commanders of a battle. Feed it the ship state (about once a second); it starts the pulses that are due, in the background, and the
    commands they give go out through `execute`, their words through `say` (an ASTRA captain's) and `transmit` (the Mandate's, on the channel).

    execute(name, args, by) -> {"ok", "detail"}: the game's own command (`group_order`, `mandate_tactics`, `enemy_order`, `fleet_request`);
    say(speaker_key, text, lang, tone, **kw): the voice stage; lang(): the Captain's language; clock(): seconds (the bench gives battle time);
    mandate_persona(contact) -> dict | None: who the Mandate's captains are (enemy.COMMANDERS); channel(contact) -> bool: a channel with the Captain is
    open with this Mandate commander; register_voice(key, name, voice): a new speaker the voice stage must know."""

    def __init__(self, llm: OpenRouter, say: SayFn, execute: ExecFn, *, lang: Callable[[], str] = lambda: "en",
                 clock: Callable[[], float] = time.monotonic, mandate_persona: Callable[[str], dict[str, Any] | None] = lambda c: None,
                 channel: Callable[[str], bool] = lambda c: False, register_voice: Callable[[str, str, str], None] | None = None,
                 transmit: SayFn | None = None, intel: Callable[[], str] = lambda: "", sides: tuple[str, ...] = ("mandate", "astra"), astra_admiral: bool = False,
                 ops: bool = True, where: Callable[[dict[str, Any]], str] | None = None, note: Callable[[str], None] | None = None,
                 trace: Callable[[dict[str, Any]], None] | None = None,
                 captain: Callable[[str, str, str], Awaitable[Any]] | None = None) -> None:
        self.llm = llm
        self.say = say
        self.transmit = transmit or say
        self.execute = execute
        self.intel = intel                               # what Mandate intelligence knows of how the Aquila's captain fights (style.py)
        self.lang = lang
        self.clock = clock
        self.mandate_persona = mandate_persona
        self.channel = channel
        self.register_voice = register_voice or (lambda key, name, voice: None)
        self.sides = sides
        self.astra_admiral = astra_admiral              # the bench: ASTRA has an admiral seat (the Captain's fleet command), as the Mandate does
        self.ops = ops                                  # the Mandate admiral also has missiles, fighters and electronic war (the bench's fair fights: off)
        self.where = where or (lambda st: _place(st))
        self.note_story = note or (lambda text: None)    # the campaign log of the story (director.note)
        self.trace = trace                               # the bench keeps every pulse with its prompts
        self.captain = captain                           # (ship, rank, name): the game's interior of that ship takes the persona as her captain (FLOTTA-VIVA)
        self.waiting: Callable[[], list[tuple[str, str, str]]] = lambda: []   # the Aquila's speech backlog (speech.Voice.waiting, set by the server)
        self.minds: dict[str, Mind] = {}
        self.allies: dict[str, Commander] = {}           # ASTRA captains by ship contact id
        self.told_captains: dict[str, str] = {}          # contact -> the captain's name the game's interior of that ship was given (FLOTTA-VIVA)
        self.pool_used = 0
        self.logs: dict[str, deque[tuple[float, str]]] = {"mandate": deque(maxlen=LOG_KEEP), "astra": deque(maxlen=LOG_KEEP)}
        self.pulses: list[dict[str, Any]] = []           # one record per pulse (the bench's costs and latencies)
        self.state: dict[str, Any] = {}
        self.admiral_contact: dict[str, str] = {}        # side -> the contact id of the commander in charge (to see a succession)
        self.t0 = self.clock()
        self.disabled = False
        self.formation_doctrine = False                  # the doctrine also teaches the formation lever (a switch: ASTRA_WAR_FORMATION=1, see `_RANGE_LINE`)
        self.strategic: Callable[[str], str] | None = None   # side -> what its high command means and what is on its way to this system (strategy.py: the war of the March)

    # ------------------------------------------------------------------------------------------------ people
    def reset(self) -> None:
        """A new session or campaign: nobody remembers the last fight."""
        for m in self.minds.values():
            if m.busy:
                m.task.cancel()
        self.minds.clear()
        for side in self.logs:
            self.logs[side].clear()
        self.allies = {c: p for c, p in self.allies.items() if c in ALLIES_FIXED}
        self.told_captains.clear()
        self.pool_used = 0
        self.admiral_contact.clear()
        self.pulses.clear()
        self.t0 = self.clock()

    def register_ally(self, contact: str, persona: dict[str, Any]) -> Commander:
        """The director (or a scenario) names the captain of an ASTRA ship: from now on that ship's commander has a mind and a voice."""
        key = persona.get("key") or "ally_" + re.sub(r"\W", "", contact.lower())
        c = Commander(key=key, contact=contact, name=persona.get("name", "Captain"), rank=persona.get("rank", "Captain"),
                      ship=persona.get("ship", "an ASTRA warship"), bio=persona.get("bio", ""), voice=persona.get("voice", "paul"), side="astra",
                      mission=persona.get("mission", ""), gender=persona.get("gender", "m"), precedence=int(persona.get("precedence", 5)))
        self.allies[contact] = c
        self.register_voice(c.key, f"{c.name} ({c.ship})", c.voice)
        return c

    def persona_of(self, side: str, contact: str, cls: str = "") -> Commander:
        """Who commands the ship `contact` (a Mandate captain from enemy.py; an ASTRA captain registered, fixed or drawn from the pool)."""
        if side == "mandate":
            p = self.mandate_persona(contact) or {}
            c = Commander(key=p.get("key", "cmdr_" + re.sub(r"\W", "", contact.lower())), contact=contact,
                          name=p.get("name", f"the commander of {contact}"), rank=p.get("rank", "Ferryman (ship captain)"),
                          ship=p.get("ship", "a Mandate warship"), bio=p.get("bio", "A hard, tired officer of the Outer Worlds."),
                          voice=p.get("voice", "stuart_bell"), side="mandate", mission=p.get("mission", ""))
            if p.get("name"):
                self._tell_captain(c)                               # (a captain without a persona keeps the name the game's interior gave him)
            return c
        if contact in self.allies:
            return self.allies[contact]
        fixed = ALLIES.get(contact)
        if fixed is not None:
            return self._tell_captain(self.register_ally(contact, fixed))
        taken = {c.name for c in self.allies.values()} | {a.get("name") for a in ALLIES.values()}
        free = [q for q in ALLY_POOL if q["name"] not in taken]      # a ship the story has not named a captain for: one from the pool whose name no captain of ours carries yet
        p = dict(free[0] if free else ALLY_POOL[self.pool_used % len(ALLY_POOL)])
        self.pool_used += 1
        p["ship"] = f"the {cls or 'warship'} {contact}"
        p["key"] = "ally_" + re.sub(r"\W", "", contact.lower())
        return self._tell_captain(self.register_ally(contact, p))

    def _tell_captain(self, c: Commander) -> Commander:
        """The game's interior of that ship (FLOTTA-VIVA: her officers, who is wounded, who has the conn) takes its captain from the persona who speaks
        for her, so that "her captain is dead" is about the same person; once per ship and name."""
        if self.captain is None or not c.contact or self.told_captains.get(c.contact) == c.name:
            return c
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return c                                                # (no game loop: nobody to tell)
        self.told_captains[c.contact] = c.name
        rank = re.sub(r"\s*\(.*\)\s*$", "", c.rank) or c.rank            # "Ferryman (ship captain)" -> "Ferryman"
        name = c.name[len(rank) + 1:] if c.name.startswith(rank + " ") else c.name   # "Captain Rhea Castellan" -> "Rhea Castellan"
        tell = self.captain

        async def told() -> None:
            try:
                await tell(c.contact, rank, name)
            except Exception:  # noqa: BLE001
                log.exception("war minds: could not give %s her captain", c.contact)
        asyncio.ensure_future(told())
        return c

    # ------------------------------------------------------------------------------------------------ the log (a side's memory of orders, words and news)
    def journal(self, side: str, who: str, text: str) -> None:
        """Something worth remembering was decided or said: the commanders of that side read it at their next look (the Mandate's persona on
        the channel writes here too, so the one who talks and the one who commands share a memory)."""
        self.logs[side].append((self.clock(), f"{who}: {text}"[:260]))

    def recall(self, side: str, n: int = LOG_LINES) -> str:
        now = self.clock()
        rows = list(self.logs[side])[-n:]
        return "\n".join(f" {max(0, now - t):.0f} s ago · {txt}" for t, txt in rows) or " (nothing yet: the fight has just begun)"

    # ------------------------------------------------------------------------------------------------ the feed
    def feed(self, state: dict[str, Any]) -> None:
        """A new ship state (the game sends one about every second). Cheap: it reads the views, decides which pulses are due and starts them."""
        if self.disabled or not isinstance(state, dict):
            return
        self.state = state
        now = self.clock()
        try:
            for side in self.sides:
                view = self._view(side, state)
                if view is not None:
                    self._feed_side(side, view, state, now)
        except Exception:  # noqa: BLE001
            log.exception("war minds: could not read the state")

    @staticmethod
    def _view(side: str, state: dict[str, Any]) -> dict[str, Any] | None:
        v = state.get("_mandate") if side == "mandate" else state.get("_astra_groups")
        return v if isinstance(v, dict) and isinstance(v.get("your_groups"), list) else None

    def _seat_mind(self, seat: Seat) -> Mind:
        m = self.minds.get(seat.id)
        if m is None:
            m = self.minds[seat.id] = Mind(seat)
        return m

    def _feed_side(self, side: str, view: dict[str, Any], state: dict[str, Any], now: float) -> None:
        groups = [g for g in view.get("your_groups") or [] if g.get("members") or g.get("ships")]
        events = [e for e in view.get("group_events") or [] if isinstance(e, dict)]
        active = self._active(side, view, state, events)
        seats = self._seats(side, view, groups, state)
        if side == "astra":
            for g in groups:                                       # (every ship of ours has a captain from the first look: a request can name any of them)
                for m in g.get("members") or []:
                    self.persona_of("astra", str(m.get("id")), str(m.get("class", "")))
        here = {seat.id for seat, _ in seats}
        for gone in [k for k, m in self.minds.items() if m.seat.side == side and k not in here and not m.busy]:
            del self.minds[gone]                                   # (a group that is no more has no commander to wake)
        # the people who command now (a succession passes a seat to the next commander; the memory is the side's)
        for seat, leader in seats:
            mind = self._seat_mind(seat)
            if leader:
                cmd = self.persona_of(side, leader, self._class_of(view, leader))
                if side == "astra" and seat.kind == "admiral":
                    cmd = Commander(contact=leader, side="astra", **BENCH_ADMIRAL)
                if mind.commander is not None and mind.commander.contact != cmd.contact:
                    if mind.commander.name == cmd.name:
                        cmd = mind.commander                        # (the same captain: a group's leader passing between two ships of one name is no succession)
                    elif now - mind.took_over >= TAKEOVER_GAP_S:
                        self.journal(side, "command", f"the command of {seat.group or 'the fleet'} passed from {mind.commander.name} to {cmd.name} ({cmd.contact})")
                        mind.takeover = f"you have just taken command of {seat.group or 'the fleet'} from {mind.commander.name}"
                        mind.took_over = now
                mind.commander = cmd
            self._feed_mind(mind, view, state, events, active, now)

    def _active(self, side: str, view: dict[str, Any], state: dict[str, Any], events: list[dict[str, Any]]) -> bool:
        if side == "mandate":
            return any(str(s.get("state")) == "attacking" for s in view.get("your_ships") or []) or bool(view.get("enemy_groups"))
        return bool(view.get("enemy_groups")) or any(g.get("order_in_force", "auto") != "auto" for g in view.get("your_groups") or []) \
            or str(state.get("alert", "")) == "red"

    @staticmethod
    def _class_of(view: dict[str, Any], contact: str) -> str:
        for g in view.get("your_groups") or []:
            for m in g.get("members") or []:
                if m.get("id") == contact:
                    return str(m.get("class", ""))
        return ""

    def _seats(self, side: str, view: dict[str, Any], groups: list[dict[str, Any]], state: dict[str, Any]) -> list[tuple[Seat, str]]:
        """The seats of a side now, each with the contact id of the ship whose captain holds it."""
        out: list[tuple[Seat, str]] = []
        if not groups:
            return out
        if side == "mandate":
            boss = next((str(s.get("id")) for s in view.get("your_ships") or [] if s.get("commands_the_strike_group")), "")
            boss = boss or str(groups[0].get("leader") or "")
            out.append((Seat("admiral", side), boss))
            self.admiral_contact[side] = boss
            for g in groups:
                lead = str(g.get("leader") or "")
                members = [str(m.get("id")) for m in g.get("members") or []]
                if boss in members or not lead:
                    continue                                       # the admiral's own group is the admiral's to command
                out.append((Seat("group", side, str(g.get("name"))), lead))
            return out
        if self.astra_admiral:
            lead = str(groups[0].get("leader") or "")
            out.append((Seat("admiral", side), lead))
            return out
        for g in groups:
            out.append((Seat("group", side, str(g.get("name"))), str(g.get("leader") or (g.get("members") or [{}])[0].get("id", ""))))
        return out

    def _min_gap(self, seat: Seat) -> float:
        """How long a mind waits between looks on events alone. A war of fleets has many group commanders: past three engaged on a
        side, each waits proportionally longer, so the side's thinking (and its cost) stays about what three groups spend — the
        admiral's cadence does not change, nor a word that cannot wait."""
        base = MIN_GAP_S[seat.role]
        if seat.role != COMMANDER_ROLE:
            return base
        engaged = sum(1 for m in self.minds.values() if m.seat.role == COMMANDER_ROLE and m.seat.side == seat.side and m.engaged_since is not None)
        return base * max(1.0, engaged / 3.0)

    def _feed_mind(self, mind: Mind, view: dict[str, Any], state: dict[str, Any], events: list[dict[str, Any]], active: bool, now: float) -> None:
        seat = mind.seat
        if active:
            mind.last_active = now
            if mind.engaged_since is None:
                mind.engaged_since = now
                mind.known_enemy = {str(s.get("id")) for g in view.get("enemy_groups") or [] for s in g.get("ships") or []}
                mind.seen_n = max([int(e.get("n", 0)) for e in events] or [mind.seen_n])
        elif mind.engaged_since is not None and now - mind.last_active > QUIET_END_S:
            self._end_fight(mind)
        # news for this seat: its own group's events (an admiral reads the whole fleet's), and enemy ships not seen before
        mine: list[dict[str, Any]] = []
        fresh: list[str] = []
        if mind.engaged_since is not None:
            mine = [e for e in events if int(e.get("n", 0)) > mind.seen_n and (seat.kind == "admiral" or str(e.get("text", "")).startswith(seat.group + ":"))]
            ids = {str(s.get("id")) for g in view.get("enemy_groups") or [] for s in g.get("ships") or []}
            fresh = sorted(ids - mind.known_enemy)
            if fresh:
                mind.known_enemy |= ids
                mind.new_enemy += [i for i in fresh if i not in mind.new_enemy]
        if mind.busy or mind.commander is None:
            return
        gap = now - mind.last_think
        min_gap = self._min_gap(seat)
        why: list[str] = []
        urgent = [m for m in mind.inbox if m.urgent or m.src == "captain"]
        if mind.takeover and mind.engaged_since is not None:
            why.append(mind.takeover + ": look at the whole picture and set your orders")
            mind.takeover = ""
        elif urgent:
            why.append("a word for you that cannot wait (below)")
        elif mind.engaged_since is None:
            return
        elif mind.thinks == 0:
            if now - mind.engaged_since >= FIRST_PULSE_S:
                why.append("first contact: the fight has begun; set your orders for it")
        else:
            if mine or mind.new_enemy:
                if mind.pending_since is None:
                    mind.pending_since = now
                top = max([int(e.get("n", 0)) for e in mine] or [0])
                if top > mind.trigger_n or fresh:                  # (only what is NEW restarts the wait: the burst is over when no more comes)
                    mind.trigger_n = max(mind.trigger_n, top)
                    mind.last_trigger = now
                settled = now - mind.last_trigger >= SETTLE_S or now - mind.pending_since >= MAX_SETTLE_S
                if settled and gap >= min_gap:
                    if mine:
                        why.append("news for your group" if seat.kind == "group" else "news of the fleet")
                    if mind.new_enemy:
                        why.append("new enemy on the plot: " + ", ".join(mind.new_enemy[:6]))
            if not why and seat.side == "astra" and seat.kind == "group" and gap >= min_gap:
                if aquila_hurt(state, mind.aquila_seen):
                    why.append("the Aquila is losing her shields or hull fast")
                cur = aquila_km(view, state, seat.group)
                if cur is not None and mind.aquila_km is not None:
                    # drawing away again and again is news less and less often (the threshold doubles each time, up to 8x); she coming back is always news
                    need = SEPARATION_KM * (2 ** mind.drawn_away) if cur > mind.aquila_km else SEPARATION_KM
                    if abs(cur - mind.aquila_km) >= need:
                        why.append(f"the Aquila has {'drawn away from' if cur > mind.aquila_km else 'closed on'} your group")
                        mind.why_extra.append(f"The Aquila is now {cur:.0f} km from your ships (it was {mind.aquila_km:.0f} km at your last look).")
                        mind.drawn_away = min(mind.drawn_away + 1, 3) if cur > mind.aquila_km else mind.drawn_away
            if not why and mind.inbox and gap >= min_gap / 2:
                why.append("a word for you (below)")
            period = self._periodic(mind)
            if not why and period and gap >= period:
                if view_digest(view) != mind.digest:
                    why.append("periodic review of the picture")
                else:
                    mind.last_think = now - period * 0.6          # nothing moved: look again a little later, at no cost
        if not why:
            return
        mind.pending_since = None
        mind.task = asyncio.ensure_future(self._pulse(mind, view, state, events, why))

    def _periodic(self, mind: Mind) -> float | None:
        """A seat thinks on a clock only when no one above it does: the admiral, an ASTRA captain (their own group), not a Mandate group
        commander (events only)."""
        if mind.seat.kind == "group" and mind.seat.side == "mandate":
            return None
        if mind.period <= 0.0:
            mind.period = PERIODIC_S[mind.seat.role] * random.uniform(0.85, 1.25)       # (drawn once per look: between 60 and 120 s)
        return mind.period

    def _end_fight(self, mind: Mind) -> None:
        mind.engaged_since = None
        mind.thinks = 0
        mind.digest = None
        mind.known_enemy.clear()
        mind.new_enemy.clear()
        mind.inbox.clear()
        mind.intent = ""
        if not any(m.engaged_since is not None for m in self.minds.values() if m.seat.side == mind.seat.side):
            self.logs[mind.seat.side].clear()

    # ------------------------------------------------------------------------------------------------ words reaching the commanders
    def deliver(self, side: str, to: str, msg: Message) -> list[Mind]:
        """A message for the commander(s) of `to`: a commander's key or a ship's contact id, or "all" (every ASTRA group commander)."""
        out: list[Mind] = []
        want = (to or "").strip().lower()
        if not want:
            return out
        v = self._view(side, self.state) or {}
        for m in self.minds.values():
            c = m.commander
            if m.seat.side != side or c is None:
                continue
            hit = want == "all" or want in (c.key.lower(), c.contact.lower()) or (m.seat.kind == "group" and want in m.seat.group.lower())
            through = None                                   # the ship of the group the words were for, when they were not for the commander herself
            if not hit:
                for g in v.get("your_groups") or []:
                    if m.seat.kind == "admiral" or g.get("name") == m.seat.group:
                        for x in g.get("members") or []:
                            cap = self.allies.get(str(x.get("id")))
                            names = [str(x.get("id")).lower()] + ([cap.key.lower(), cap.ship.lower(), cap.name.lower()] if cap else [])
                            if not hit and any(want == n or (len(want) > 3 and want in n) for n in names):
                                hit, through = True, cap
            if hit:
                mine = msg
                if through is not None and through.key != c.key and msg.src in ("captain", "comms"):
                    # the Captain called one of her ships: its captain has no voice of his own on the net, he speaks through the group's mind (the Captain
                    # hailed the Bulwark four times and nobody answered: her commander read the words as not hers, 3 Oct)
                    note = (f" [The Captain is calling the {through.ship}, a ship of your group: her captain, {through.name}, answers him through you — "
                            f"`say` with speaker {through.key}, to \"aquila\" — with what the {through.ship} sees and does.]")
                    mine = Message(msg.t, msg.src, msg.text + note, urgent=msg.urgent, answer=msg.answer, lang=msg.lang, data=msg.data)
                m.inbox.append(mine)
                out.append(m)
        return out

    def captain_to_fleet(self, words: str, lang: str, to: str = "all") -> int:
        """The Captain spoke on the fleet net (what comms let out): every allied commander hears it and judges whether it was for them."""
        msg = Message(self.clock(), "captain", words, urgent=True, answer=True, lang=lang)
        self.journal("astra", "the Captain (fleet net)", words[:200])
        return len(self.deliver("astra", to, msg))

    def captain_request(self, args: dict[str, Any], lang: str = "") -> dict[str, Any] | None:
        """The comms officer relays the Captain's request (`fleet_request`) to the ships named: their commanders judge it. None: nobody here has a mind
        to judge it (the caller sends it on the old way, ship by ship)."""
        ship = str(args.get("ship") or "all")
        req = str(args.get("request") or "")
        target = str(args.get("target") or "")
        phrase = REQUESTS.get(req, req.replace("_", " "))
        text = f"The Captain asks, by the comms officer: {phrase}" + (f" (target {target})" if target else "") + (f". Addressed to {ship}." if ship.lower() != "all" else ".")
        msg = Message(self.clock(), "comms", text, urgent=True, answer=True, lang=lang or self.lang(), data=dict(args))
        got = self.deliver("astra", ship if ship.lower() != "all" else "all", msg)
        if not got:
            return None
        self.journal("astra", "the Captain (by comms)", text[:200])
        names = " and ".join(m.commander.name for m in got if m.commander)
        return {"ok": True, "detail": f"relayed to {names}: their captain{'s' if len(got) > 1 else ''} will answer over the fleet net and act as judged "
                                      "(an acknowledgement or the reason for a refusal follows by radio)"}

    def captain_ordered(self, group: str, detail: str) -> None:
        """The Captain gave a group a direct order (the XO's `group_order`): its commander is told, with no call of the model (the order stands)."""
        self.journal("astra", "the Captain (direct order)", detail[:220])
        for m in self.minds.values():
            if m.seat.side == "astra" and (m.seat.kind == "admiral" or m.seat.group.lower() == group.lower()):
                m.inbox.append(Message(self.clock(), "order", f"The Captain ordered your group directly: {detail}", urgent=False))

    # ------------------------------------------------------------------------------------------------ a pulse
    async def _pulse(self, mind: Mind, view: dict[str, Any], state: dict[str, Any], events: list[dict[str, Any]], why: list[str]) -> None:
        seat, cmd = mind.seat, mind.commander
        assert cmd is not None
        t0 = time.perf_counter()
        now = self.clock()
        new_events = [e for e in events if int(e.get("n", 0)) > mind.seen_n and (seat.kind == "admiral" or str(e.get("text", "")).startswith(seat.group + ":"))]
        if events:
            mind.seen_n = max(mind.seen_n, max(int(e.get("n", 0)) for e in events))
        inbox, mind.inbox = mind.inbox, []
        new_enemy, mind.new_enemy = mind.new_enemy, []
        mind.last_think = now
        mind.thinks += 1
        mind.period = 0.0
        mind.digest = view_digest(view)
        if seat.side == "astra" and seat.kind == "group":
            mind.aquila_km = aquila_km(view, state, seat.group)
            if mind.aquila_km is not None and mind.aquila_km < SEPARATION_KM:
                mind.drawn_away = 0                                                     # she is back among them: the next time she leaves is news again
        rec: dict[str, Any] = {"t": round(now - self.t0, 1), "seat": seat.id, "who": cmd.name, "why": why, "tools": [], "ok": 0, "failed": 0, "lines": 0,
                               "cost": 0.0, "latency": 0.0, "first_call": None, "tokens_in": 0, "tokens_out": 0, "error": ""}
        CURRENT.set(mind)
        CURRENT_VIEW.set((view, state))
        try:
            try:
                system, user, tools = self._compose(mind, view, state, new_events, new_enemy, inbox, why)
                if self.trace is not None:
                    rec["system"], rec["user"] = system, user
                await asyncio.wait_for(self._run(mind, system, user, tools, rec, inbox, view), timeout=PULSE_TIMEOUT_S)
            except asyncio.TimeoutError:
                rec["error"] = "timeout"
                log.warning("%s (%s): no decision in time: the group holds on its reflexes", cmd.name, seat.id)
            except asyncio.CancelledError:
                rec["error"] = "cancelled"
                raise
            except Exception as exc:  # noqa: BLE001
                rec["error"] = f"{type(exc).__name__}: {exc}"[:120]
                log.exception("%s (%s): the pulse failed", cmd.name, seat.id)
            if rec["error"] and not rec["tools"]:
                await self._fallback(inbox)                      # (a request from the Captain must not be lost to a model that failed or stalled before it answered)
        finally:
            rec["latency"] = round(time.perf_counter() - t0, 2)
            s = mind.stats
            s["pulses"] += 1
            s["cost"] += rec["cost"]
            s["latency"] += rec["latency"]
            s["first_call"] += rec["first_call"] or 0.0
            s["orders"] += rec["ok"]
            s["failed"] += rec["failed"]
            s["tokens_in"] += rec["tokens_in"]
            s["tokens_out"] += rec["tokens_out"]
            s["errors"] += 1 if rec["error"] else 0
            s["lines"] += rec["lines"]
            self.pulses.append(rec)
            del self.pulses[:-2000]
            if self.trace is not None:
                self.trace(rec)
            log.info("%s %.2fs $%.5f (%s): %s", cmd.name, rec["latency"], rec["cost"], "; ".join(why), " | ".join(rec["tools"]) or "(nothing)")

    async def _fallback(self, inbox: list[Message]) -> None:
        """A commander who could not answer (the model failed or stalled) must not lose the Captain's request: it goes the old way, to the ships (the
        game's own fleet-request mechanics), and the log says so."""
        for m in inbox:
            if m.src == "comms" and m.data:
                try:
                    res = await self.execute("fleet_request", m.data, "captain")
                    self.journal("astra", "comms", f"the commander did not answer: the request went to the ships directly ({res.get('detail', '')[:100]})")
                except Exception:  # noqa: BLE001
                    log.exception("the request could not go the old way either")

    # -- the prompt
    def _compose(self, mind: Mind, view: dict[str, Any], state: dict[str, Any], new_events: list[dict[str, Any]], new_enemy: list[str],
                 inbox: list[Message], why: list[str]) -> tuple[str, str, list[dict[str, Any]]]:
        seat, cmd = mind.seat, mind.commander
        assert cmd is not None
        side = seat.side
        where = self.where(state)
        from .enemy import COMMANDERS as OPENING_COMMANDERS, OPENING_MISSION    # (here: enemy.py imports this module)
        if cmd.mission:
            mission = f"Your orders: {cmd.mission}"
        elif side == "mandate" and cmd.contact in OPENING_COMMANDERS:
            # the strike group's purpose in the opening (enemy.OPENING_MISSION, the same the channel persona is given): without it a picket
            # stronger than you is only a reason to leave, and the campaign's first battle was a pass at 40 km and a withdrawal
            mission = OPENING_MISSION
        else:
            mission = ""
        lang = self.lang()
        admiral = self.minds.get("mandate/admiral")
        chain, voices, ships = "", "", ""
        speakers: list[str] = []
        if side == "astra" and seat.kind == "group":
            g = next((x for x in view.get("your_groups") or [] if x.get("name") == seat.group), {})
            members = [str(m.get("id")) for m in g.get("members") or []]
            caps = [self.persona_of("astra", i, str(next((m.get("class") for m in g.get("members") or [] if m.get("id") == i), ""))) for i in members]
            ships = ", ".join(f"{c.name} in {c.ship}" for c in caps) or "your ships"
            speakers = [c.key for c in caps] or [cmd.key]
            if len(caps) > 1:
                voices = (f"The other captains of your group: {', '.join(f'{c.name} ({c.key}), {c.ship}' for c in caps if c.key != cmd.key)}. "
                          "One of them may speak instead of you (`speaker`) when the words are about their own ship; they do not give orders to the group.")
            chain = self.chain_facts(view, state)
        channel_open = side == "mandate" and self.channel(cmd.contact)
        system = system_prompt(seat, cmd, where, mission, chain=chain, admiral_name=(admiral.commander.name if admiral and admiral.commander else ""),
                               ships=ships, voices=voices, channel_open=channel_open, ops=self.ops, formation=self.formation_doctrine)
        pic = picture(side, seat.kind, seat.group, view, state, mind.aquila_seen, self.clock())
        if side == "astra" and seat.kind == "group":
            mind.aquila_seen = (*aquila_levels(state), self.clock())                    # (what the next look compares with)
        intent = ""
        if seat.kind == "admiral" and side == "mandate":
            style = self.intel()
            if style:
                intent = ("\nWhat Mandate intelligence has learned of the Aquila's captain from earlier fights (use it: lay the trap their habits walk "
                          f"into): {style}")
        if seat.kind == "group" and side == "mandate" and admiral is not None:
            intent = (f"\nThe admiral's last intent: {admiral.intent}" if admiral.intent else "\nThe admiral has not given orders yet.")
        high = self.strategic(side) if self.strategic is not None else ""
        if high:
            intent += ("\nYOUR HIGH COMMAND, AS YOUR SIDE'S FLEETS KNOW IT (its plan, its orders for the fleets here, what is on its way to this system and what your side's eyes say "
                       "is coming; the war is bigger than this fight: read what you are fighting for, and what help is on its way)\n" + high)
        if mind.why_extra:
            intent += "\n" + "\n".join(mind.why_extra)
            mind.why_extra = []
        msgs = ""
        if inbox:
            msgs = "\nMESSAGES FOR YOU\n" + "\n".join(f" {max(0, self.clock() - m.t):.0f} s ago · {self._src(m)}: {m.text}" for m in inbox)
        enemy_note = f"\nNew enemy ships on your plot since your last look: {', '.join(new_enemy)}" if new_enemy else ""
        queued = self.waiting() if side == "astra" else []
        backlog = ("\nWAITING TO BE SAID on the Aquila's speakers (queued behind whoever is speaking there: a word from you to her captain is worth adding only "
                   "if it matters more to him than these, and nothing here is said again)\n" + "\n".join(f" - {who} ({how}): \"{words}\"" for who, words, how in queued)
                   if queued else "")
        user = (f"WHAT YOU HAVE DECIDED AND SAID, AND WHAT YOU HEARD (your log, newest last)\n{self.recall(side)}\n\n"
                f"{pic}\nEVENTS SINCE YOUR LAST LOOK (newest last)\n{render_events(new_events)}{enemy_note}{intent}{msgs}{backlog}\n\n"
                f"You are looking now because: {'; '.join(why)}. The Captain's language is {LANG_NAMES.get(lang, lang)} (what you say aloud is in it).\n"
                "Decide: give your orders with the tools, or call no_change.")
        tools: list[dict[str, Any]] = []
        boats = side == "mandate" and bool(render_boarding(view))             # (boats to send, or an assault to follow: else the tool is not on the list)
        if seat.kind == "admiral":
            tools = [group_order_tool("admiral")] + ([FLEET_OPS, DECIDE] if side == "mandate" and self.ops else []) + ([BOARD] if boats else []) + [NO_CHANGE]
            if channel_open:
                tools.append(TRANSMIT)
        elif side == "mandate":
            tools = [group_order_tool("commander"), REPORT] + ([BOARD] if boats else []) + [NO_CHANGE]
        else:
            tools = [group_order_tool("commander"), say_tool(speakers, LANG_NAMES.get(lang, lang)), POSTURE, NO_CHANGE]
        return system, user, tools

    @staticmethod
    def _src(m: Message) -> str:
        return {"captain": "the Captain, over the fleet net", "comms": "the comms officer relays", "order": "order", "net": "on the fleet net"}.get(m.src, m.src)

    def chain_facts(self, view: dict[str, Any], state: dict[str, Any]) -> str:
        """Who is the senior officer present (facts from ranks and appointments; what they mean for an order is the commander's to judge)."""
        entries = [("the Captain of the ASN Aquila", rank_index("Captain"), 0, "in tactical command of the Aurelia picket by Fleet's order")]
        for g in view.get("your_groups") or []:
            for m in g.get("members") or []:
                c = self.allies.get(str(m.get("id")))
                if c:
                    entries.append((f"{c.name} ({c.ship})", rank_index(c.rank), c.precedence, ""))
        entries.sort(key=lambda e: (e[1], e[2]))
        senior = entries[0]
        line = f"Senior officer present: {senior[0]}" + (f" ({senior[3]})" if senior[3] else "") + ". Then: " + "; ".join(e[0] for e in entries[1:])
        return line + ". Vice Admiral Rourke commands the 7th Fleet from afar and sends orders only by the fleet net."

    def captain_is_senior(self, view: dict[str, Any] | None = None) -> bool:
        v = view or self._view("astra", self.state) or {}
        mine = rank_index("Captain")
        for g in v.get("your_groups") or []:
            for m in g.get("members") or []:
                c = self.allies.get(str(m.get("id")))
                if c and (rank_index(c.rank), c.precedence) < (mine, 0):
                    return False
        return True

    # -- the model call and the tools
    async def _run(self, mind: Mind, system: str, user: str, tools: list[dict[str, Any]], rec: dict[str, Any], inbox: list[Message],
                   view: dict[str, Any]) -> None:
        seat, cmd = mind.seat, mind.commander
        assert cmd is not None
        by_captain = any(m.answer for m in inbox)
        results: list[tuple[str, dict[str, Any], dict[str, Any]]] = []
        pending: list[tuple[str, dict[str, Any], asyncio.Task]] = []
        spoke: list[str] = []
        lang = self.lang()
        t_start = time.perf_counter()

        async def on_call(call: ToolCall) -> None:
            a = call.arguments() or {}
            if rec["first_call"] is None:
                rec["first_call"] = round(time.perf_counter() - t_start, 2)
            rec["tools"].append(call.name + (f":{a.get('order')}" if call.name == "group_order" else ""))
            if call.name == "no_change":
                mind.stats["no_change"] += 1
                self.journal(seat.side, cmd.name, f"looked, no change: {str(a.get('reason', ''))[:150]}")
                return
            if call.name == "say":
                text = str(a.get("text") or "").strip()
                if len(text) < 2:
                    return
                spoken = await self._say(mind, a, text, lang, by_captain)
                if spoken:
                    spoke.append(text)
                    rec["lines"] += 1
                return
            if call.name == "transmit":
                text = str(a.get("text") or "").strip()
                if len(text) >= 4:
                    self.journal("mandate", cmd.name, f"said on the channel: {text[:200]}")
                    spoke.append(text)
                    rec["lines"] += 1
                    await self.transmit(cmd.key, text, lang, str(a.get("tone", "cold")))
                return
            if call.name == "report":
                self._report(mind, a)
                return
            pending.append((call.name, a, asyncio.ensure_future(self._tool(mind, call.name, a))))

        comp = await models.chat(self.llm, seat.role, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}], tools=tools,
                                 tool_choice="auto", on_tool_call=on_call)
        self._count(rec, comp)
        if self.trace is not None:
            rec["content"], rec["finish"] = comp.content[:1500], comp.finish_reason
        for name, a, task in pending:
            try:
                res = await asyncio.wait_for(task, timeout=4.0)
            except asyncio.TimeoutError:
                res = {"ok": False, "detail": "no response from the fleet's datalink"}
            results.append((name, a, res))
        self._account(mind, rec, results)
        if comp.error and not rec["tools"]:
            rec["error"] = comp.error[:100]
            return
        if not rec["tools"]:
            # it wrote and called nothing (or was cut off while thinking aloud): what it wrote is not an order and is not said; it is asked once for its
            # decision, in the tools (docs/ARCHITETTURA.md §1bis: no guessing from the text)
            await asyncio.wait_for(self._reask(mind, system, user, tools, rec, comp, on_call), timeout=ROUND2_TIMEOUT_S)
            results = await self._settle(pending)
            self._account(mind, rec, results)
        failed = [(n, a, r) for n, a, r in results if not r.get("ok")]
        if failed:
            await asyncio.wait_for(self._round2(mind, system, user, tools, rec, comp, results, failed, by_captain), timeout=ROUND2_TIMEOUT_S)

    async def _reask(self, mind: Mind, system: str, user: str, tools: list[dict[str, Any]], rec: dict[str, Any], first: Completion, on_call: Any) -> None:
        msgs: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        if first.content.strip():
            msgs.append({"role": "assistant", "content": first.content.strip()})
        msgs.append({"role": "user", "content": "[You ended without a tool call, so nothing was done or said. Decide now, briefly, with the tools: your orders, "
                                                "your words, or no_change.]"})
        comp = await models.chat(self.llm, mind.seat.role, messages=msgs, tools=tools, tool_choice="auto", on_tool_call=on_call, max_tokens=300)
        self._count(rec, comp)
        rec["asked_again"] = True

    @staticmethod
    async def _settle(pending: list[tuple[str, dict[str, Any], asyncio.Task]]) -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
        """The results of the tool calls started so far that have not been collected (the pulse's second try)."""
        out = []
        for name, a, task in pending:
            try:
                out.append((name, a, await asyncio.wait_for(asyncio.shield(task), timeout=4.0)))
            except asyncio.TimeoutError:
                out.append((name, a, {"ok": False, "detail": "no response from the fleet's datalink"}))
        return out

    async def _round2(self, mind: Mind, system: str, user: str, tools: list[dict[str, Any]], rec: dict[str, Any], first: Completion,
                      results: list[tuple[str, dict[str, Any], dict[str, Any]]], failed: list[tuple[str, dict[str, Any], dict[str, Any]]],
                      by_captain: bool) -> None:
        """An order was refused (a group or a target that is not there): the commander reads why and corrects it, once."""
        cmd = mind.commander
        assert cmd is not None
        notes = "\n".join(f"- {n}({json.dumps({k: v for k, v in a.items() if k != 'reason'}, ensure_ascii=False)}) {'ok' if r.get('ok') else 'FAILED'}: {r.get('detail', '')}"
                          for n, a, r in results)
        calls = [{"id": f"c{i}", "type": "function", "function": {"name": n, "arguments": json.dumps(a, ensure_ascii=False)}} for i, (n, a, _) in enumerate(results)]
        msgs: list[dict[str, Any]] = [{"role": "system", "content": system}, {"role": "user", "content": user},
                                      {"role": "assistant", "content": None, "tool_calls": calls}]
        msgs += [{"role": "tool", "tool_call_id": f"c{i}", "content": ("ok: " if r.get("ok") else "FAILED: ") + str(r.get("detail", ""))} for i, (_, _, r) in enumerate(results)]
        msgs.append({"role": "user", "content": f"The orders that failed could not be carried out (above). Correct them if there is a way, or call no_change. Results:\n{notes}"})
        pending: list[tuple[str, dict[str, Any], asyncio.Task]] = []

        async def on_call(call: ToolCall) -> None:
            a = call.arguments() or {}
            rec["tools"].append("again:" + call.name + (f":{a.get('order')}" if call.name == "group_order" else ""))
            if call.name in ("group_order", "fleet_ops", "decide", "weapons_posture", "board"):
                pending.append((call.name, a, asyncio.ensure_future(self._tool(mind, call.name, a))))

        comp = await models.chat(self.llm, mind.seat.role, messages=msgs, tools=[t for t in tools if t["function"]["name"] != "say"], tool_choice="auto",
                                 on_tool_call=on_call, max_tokens=240)
        self._count(rec, comp)
        again = []
        for name, a, task in pending:
            try:
                again.append((name, a, await asyncio.wait_for(task, timeout=4.0)))
            except asyncio.TimeoutError:
                again.append((name, a, {"ok": False, "detail": "no response from the fleet's datalink"}))
        self._account(mind, rec, again, second=True)

    @staticmethod
    def _count(rec: dict[str, Any], comp: Completion) -> None:
        rec["cost"] += comp.cost
        rec["tokens_in"] += comp.prompt_tokens
        rec["tokens_out"] += comp.completion_tokens

    def _account(self, mind: Mind, rec: dict[str, Any], results: list[tuple[str, dict[str, Any], dict[str, Any]]], second: bool = False) -> None:
        cmd = mind.commander
        assert cmd is not None
        for name, a, res in results:
            ok = bool(res.get("ok"))
            rec["ok" if ok else "failed"] += 1
            what = self._describe(name, a)
            self.journal(mind.seat.side, cmd.name, f"{what} — {str(a.get('reason', ''))[:110]} => {'ok' if ok else 'FAILED'}: {str(res.get('detail', ''))[:130]}")
            if ok and mind.seat.kind == "admiral" and name == "group_order":
                mind.intent = f"{what}: {str(a.get('reason', ''))[:160]}"

    @staticmethod
    def _describe(name: str, a: dict[str, Any]) -> str:
        if name == "group_order":
            bits = [f"ordered {a.get('group')}: {a.get('order')}"]
            for k, fmt in (("target", " on {}"), ("range_km", " at {} km"), ("for_s", " for {} s"), ("formation", " in {} formation")):
                if a.get(k) not in (None, ""):
                    bits.append(fmt.format(a[k]))
            return "".join(bits)
        if name == "fleet_ops":
            return "fleet ops: " + ", ".join(f"{k} {v}" for k, v in a.items() if k not in ("reason", "ships") and v)
        if name == "decide":
            return f"decided: {a.get('order')}"
        if name == "weapons_posture":
            return f"posture: {a.get('posture')}"
        if name == "board":
            return "called the boats off" if str(a.get("action") or "").lower() == "call_off" else f"boarding {a.get('target')} with {a.get('boats') or 'the free'} skiff(s) from {a.get('carrier') or 'the best carrier'}"
        return name

    async def _tool(self, mind: Mind, name: str, a: dict[str, Any]) -> dict[str, Any]:
        """The commander's tool, run on the game: checked only for what the rank cannot do, then sent as the game's own command."""
        seat, cmd = mind.seat, mind.commander
        assert cmd is not None
        try:
            if name == "group_order":
                args = {k: v for k, v in a.items() if k != "reason" and v not in (None, "")}
                if seat.kind == "group" and str(args.get("group", "")).lower() not in (seat.group.lower(), "") and not self._is_ship_of(seat, args.get("group")):
                    return {"ok": False, "detail": f"{args.get('group')} is not your group: you command {seat.group}"}
                if seat.kind == "group" and not args.get("group"):
                    args["group"] = seat.group
                args["side"] = seat.side
                args["by"] = "admiral" if (seat.kind == "admiral" and seat.side == "mandate") else ("captain" if seat.kind == "admiral" else "commander")
                return await self.execute("group_order", args, args["by"])
            if name == "fleet_ops":
                args = {k: v for k, v in a.items() if k in ("missiles", "fighters", "ew", "ships") and v not in (None, "", [])}
                return await self.execute("mandate_tactics", args, "admiral")
            if name == "decide":
                self.note_story(f"{cmd.name} decided: {a.get('order')} ({a.get('reason', '')})")
                return await self.execute("enemy_order", {"order": a.get("order", "continue_attack"), "reason": a.get("reason", ""), "commander": cmd.contact},
                                          cmd.key)
            if name == "weapons_posture":
                return await self._posture(mind, str(a.get("posture", "")))
            if name == "board" and seat.side == "mandate":
                action = str(a.get("action") or "launch").lower()
                reason = str(a.get("reason") or "").strip()
                if action == "call_off":
                    # the recall carries its reason and who gave it: the bridge of the ship that is boarded hears both (the game's event), and the picture of the operation keeps them
                    return await self.execute("boarding", {k: v for k, v in {"action": "end", "by": cmd.name, "reason": reason}.items() if v not in (None, "", [])},
                                              "admiral" if seat.kind == "admiral" else "commander")
                carrier = str(a.get("carrier") or "").strip()
                if seat.kind == "group" and carrier and not self._is_ship_of(seat, carrier):
                    return {"ok": False, "detail": f"{carrier} is not a ship of your group: you send the boats of {seat.group}'s ships"}
                args = {k: v for k, v in {"direction": "in", "target": str(a.get("target") or "").strip(), "source": carrier, "craft": a.get("boats"), "face": a.get("face"),
                                          "objective": a.get("objective"), "by": cmd.name, "reason": reason}.items() if v not in (None, "", [])}
                if not args.get("target"):
                    return {"ok": False, "detail": "name the ship to board (`target`: her contact id)"}
                if seat.kind == "group" and not carrier:
                    # a group commander's boats are his group's: the first ship of it that has skiffs free (the picture lists the carriers)
                    mine = [str(c.get("id")) for c in ((self._view(seat.side, self.state) or {}).get("boarding") or {}).get("carriers") or [] if self._is_ship_of(seat, c.get("id"))]
                    if not mine:
                        return {"ok": False, "detail": f"no ship of {seat.group} has a skiff free"}
                    args["source"] = mine[0]
                return await self.execute("boarding", args, "admiral" if seat.kind == "admiral" else "commander")
        except Exception as exc:  # noqa: BLE001
            log.exception("tool %s failed", name)
            return {"ok": False, "detail": f"{type(exc).__name__}: {exc}"[:160]}
        return {"ok": False, "detail": f"{name} is not a tool of yours"}

    def _is_ship_of(self, seat: Seat, ref: Any) -> bool:
        v = self._view(seat.side, self.state) or {}
        for g in v.get("your_groups") or []:
            if g.get("name") == seat.group and str(ref) in [str(m.get("id")) for m in g.get("members") or []]:
                return True
        return False

    async def _posture(self, mind: Mind, posture: str) -> dict[str, Any]:
        """A group's weapons posture, by the game's fleet-request mechanics (hold fire on every ship of the group, or release them)."""
        v = self._view("astra", self.state) or {}
        g = next((x for x in v.get("your_groups") or [] if x.get("name") == mind.seat.group), None)
        if g is None:
            return {"ok": False, "detail": "no group of yours in the fight"}
        done, last = 0, {}
        for m in g.get("members") or []:
            last = await self.execute("fleet_request", {"ship": str(m.get("id")), "request": "hold_fire" if posture == "hold_fire" else "engage_freely"}, "commander")
            done += 1 if last.get("ok") else 0
        return {"ok": done > 0, "detail": f"{done} ship(s) of {mind.seat.group}: {'holding fire' if posture == 'hold_fire' else 'weapons free'}"}

    def _report(self, mind: Mind, a: dict[str, Any]) -> None:
        """A Mandate group commander's word to the admiral: read at the admiral's next look (at once if urgent)."""
        cmd = mind.commander
        text = str(a.get("text") or "").strip()
        if not cmd or not text:
            return
        self.journal("mandate", cmd.name, f"reported to the admiral: {text[:200]}")
        adm = self.minds.get("mandate/admiral")
        if adm is not None and adm is not mind:
            adm.inbox.append(Message(self.clock(), cmd.name, text, urgent=bool(a.get("urgent"))))

    async def _say(self, mind: Mind, a: dict[str, Any], text: str, lang: str, answer: bool) -> bool:
        """An allied captain speaks on the fleet net."""
        cmd = mind.commander
        assert cmd is not None
        key = str(a.get("speaker") or cmd.key)
        speaker = next((c for c in self.allies.values() if c.key == key), cmd)
        to = str(a.get("to") or "aquila")
        urgent = bool(a.get("urgent"))
        self.journal("astra", speaker.name + (f" to {to}" if to != "aquila" else ""), text[:200])
        if to not in ("aquila", "fleet", ""):
            self.deliver("astra", to, Message(self.clock(), speaker.key, text, urgent=True))
        # (no topic: the voice stage lets two sentences of one captain join in one breath, and two captains of a group speak both; a line that waited
        # too long is thought again by whoever was to say it, see `rethink`)
        await self.say(speaker.key, text, lang, str(a.get("tone", "calm")), urgent=urgent, answer=answer, to=to)
        return True

    # ------------------------------------------------------------------------------------------------ a line that waited
    async def rethink(self, key: str, text: str, waited_s: float, cut_after: str, lang: str) -> str | None:
        """An allied captain thinks again about a line that waited (or was cut off) before it is said: what they say now, or None (the speech
        floor calls it: docs/ARCHITETTURA.md §1bis, point 5)."""
        mind = next((m for m in self.minds.values() if m.commander is not None and m.seat.side == "astra"
                     and (m.commander.key == key or key in self._captain_keys(m))), None)
        if mind is None or mind.commander is None:
            return text
        view = self._view("astra", self.state)
        if view is None:
            return text
        cmd = mind.commander
        cut = f" They had said only «{cut_after}» when the Captain spoke over them." if cut_after else ""
        ask = (f"{waited_s:.0f} seconds ago you were about to tell the Captain, over the fleet net: «{text}».{cut} The battle has moved on (the picture below is "
               f"now). If it still matters to him, say it now as it stands — updated, short — with say. If not, say nothing: call no_change.")
        system = system_prompt(mind.seat, cmd, self.where(self.state), cmd.mission, chain=self.chain_facts(view, self.state), formation=self.formation_doctrine)
        user = (f"{render_groups(view, only=mind.seat.group)}\nENEMY\n{render_enemy(view)}\n{render_astra_extras(self.state)}\n\n{ask}")
        said: list[str] = []
        CURRENT.set(mind)
        CURRENT_VIEW.set((view, self.state))

        async def on_call(call: ToolCall) -> None:
            if call.name == "say" and str((call.arguments() or {}).get("text") or "").strip():
                said.append(str(call.arguments()["text"]).strip())

        comp = await models.chat(self.llm, COMMANDER_ROLE, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                                 tools=[say_tool([cmd.key], LANG_NAMES.get(self.lang(), self.lang())), NO_CHANGE], tool_choice="auto", on_tool_call=on_call, max_tokens=140)
        mind.stats["cost"] += comp.cost
        return " ".join(said) if said else None

    def _captain_keys(self, mind: Mind) -> set[str]:
        v = self._view("astra", self.state) or {}
        keys = set()
        for g in v.get("your_groups") or []:
            if g.get("name") == mind.seat.group:
                for m in g.get("members") or []:
                    c = self.allies.get(str(m.get("id")))
                    if c:
                        keys.add(c.key)
        return keys

    # ------------------------------------------------------------------------------------------------ for the others
    def preempt(self, contact: str) -> int:
        """A person is about to talk (the Captain on the channel): that commander's pulse in flight is dropped (what it had already ordered stays)."""
        n = 0
        for m in self.minds.values():
            if m.commander is not None and m.commander.contact == contact and m.busy:
                m.task.cancel()
                n += 1
        return n

    def is_admiral(self, contact: str) -> bool:
        return self.admiral_contact.get("mandate") == contact

    def can_answer(self, party: str) -> bool:
        """A channel to this ASTRA ship (or its captain's key) reaches a commander with a mind."""
        v = self._view("astra", self.state) or {}
        for m in self.minds.values():
            if m.seat.side != "astra" or m.commander is None:
                continue
            if party in (m.commander.key, m.commander.contact):
                return True
            for g in v.get("your_groups") or []:
                if g.get("name") == m.seat.group and party in [str(x.get("id")) for x in g.get("members") or []]:
                    return True
        return False

    def allies_line(self) -> str:
        """The allied captains on the fleet net now (for whoever else is on it: Fleet command)."""
        v = self._view("astra", self.state) or {}
        caps = []
        for g in v.get("your_groups") or []:
            for m in g.get("members") or []:
                c = self.allies.get(str(m.get("id")))
                if c and c.name not in caps:
                    caps.append(c.name)
        return ", ".join(caps) or "the captains of the ships in company"

    def kick(self) -> None:
        """Look at the state again now (a word for a commander has just been delivered: no need to wait for the next state)."""
        if self.state:
            self.feed(self.state)

    def fleet_board(self, state: dict[str, Any] | None = None) -> str:
        """The ASTRA groups as the XO and the comms officer see them (the fleet datalink), for the crew's prompt: who commands each, what it is doing,
        and who is the senior officer present."""
        st = state if state is not None else self.state
        v = self._view("astra", st)
        if not v or not v.get("your_groups"):
            return ""
        rows = []
        for g in v["your_groups"]:
            cap = self.allies.get(str(g.get("leader")))
            who = f"{cap.name}, {cap.ship}" if cap else f"leader {g.get('leader')}"
            order = g.get("order_in_force", "auto")
            if order != "auto":
                order += f" (by {g.get('order_by', '?')}" + (f", on {g['order_target']}" if g.get("order_target") else "") + ")"
            ships = ", ".join(f"{m.get('id')} {m.get('class')} {_pct(m.get('hull_pct'))}/{_pct(m.get('shields_pct'))}" for m in g.get("members") or [])
            rows.append(f"- {g.get('name')} — {who}; {g.get('state')}, order {order}; strength {g.get('your_strength')} vs {g.get('enemy_strength_near')} near, "
                        f"morale {g.get('morale')}; ships: {ships}")
        senior = "the Captain is the senior officer present: the groups obey his direct orders (group_order)" if self.captain_is_senior(v) else \
            "the Captain is NOT the senior officer present: ask the senior officer over the fleet net"
        return "\n".join(rows) + f"\n- Chain of command: {self.chain_facts(v, st)} In short, {senior}."

    # ------------------------------------------------------------------------------------------------ measures
    def summary(self) -> dict[str, Any]:
        """Costs and latencies of the pulses so far (the bench's and the lead's figures)."""
        done = [p for p in self.pulses if not p["error"] or p["error"] == "timeout"]
        n = len(self.pulses)
        span = max(1.0, self.clock() - self.t0)
        cost = sum(p["cost"] for p in self.pulses)
        lat = sorted(p["latency"] for p in self.pulses)
        fc = sorted(p["first_call"] for p in self.pulses if p["first_call"] is not None)
        return {"pulses": n, "errors": sum(1 for p in self.pulses if p["error"]), "cost": round(cost, 5),
                "cost_per_pulse": round(cost / n, 5) if n else 0.0, "span_s": round(span, 1),
                "cost_per_hour": round(cost / span * 3600.0, 3), "latency_median": lat[len(lat) // 2] if lat else 0.0,
                "latency_p90": lat[int(len(lat) * 0.9)] if lat else 0.0, "first_call_median": fc[len(fc) // 2] if fc else 0.0,
                "orders_ok": sum(p["ok"] for p in self.pulses), "orders_failed": sum(p["failed"] for p in self.pulses),
                "lines": sum(p["lines"] for p in self.pulses), "tokens_in": sum(p["tokens_in"] for p in self.pulses),
                "tokens_out": sum(p["tokens_out"] for p in self.pulses), "by_seat": {k: dict(v.stats) for k, v in self.minds.items()},
                "done": len(done)}


ALLIES_FIXED = set(ALLIES)

# the Captain's requests (fleet_request) said as a captain would hear them
REQUESTS = {
    "focus_fire": "concentrate your fire on the target",
    "engage_freely": "engage targets of opportunity, at your own judgement",
    "cover_us": "cover the Aquila: stay between her and the enemy",
    "close_in": "close in to knife-fight range",
    "stand_off": "stand off at railgun range, out of the enemy's lasers",
    "hold_fire": "hold fire",
}
