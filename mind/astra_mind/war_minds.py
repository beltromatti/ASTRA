"""The minds that command the war: the Mandate's admiral and group commanders, the ASTRA allied captains (docs/GUERRA.md §6 is the
contract they act through, §8 how they work).

The code of the simulation is the body of a fleet (formations, fire, evasion, point defence, reflexes); here is its judgement. A commander
reads what their side could know (their own groups in full, the enemy as their sensors hold it, the events that happened to their groups),
decides, and acts with the tools of their rank: `group_order` (a battle group's order: attack, pin, flank, screen, withdraw, regroup,
reinforce, hold, with a target, a range, a duration), `fleet_ops` (the Mandate's missiles, fighters and electronic war), `decide` (leave the
system), `say` (an allied captain's words to the Aquila on the fleet net), `report` (a captain's word to the admiral). Nothing here
decides for them or filters what they say (docs/ARCHITETTURA.md §1bis): the code carries facts, keeps the clock, and runs the tools.

Two velocities (docs/GUERRA.md §2): the groups run on their reflexes all the time; a mind thinks every 60-120 s or when something strong
happens to its group (a loss, a morale that breaks, an order that ran out, a new enemy, a word from the Captain), never twice at once for the
same person, and when it is slow or silent the groups simply hold on their reflexes.

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
from .crew import CAPTAIN_WORD, LANG_NAMES, WORLD
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
SETTLE_S = 3.0                                          # a burst of events is read together: wait for it to end (at most MAX_SETTLE_S)
MAX_SETTLE_S = 8.0
QUIET_END_S = 75.0                                      # a fight with nothing happening for this long is over
PULSE_TIMEOUT_S = 28.0                                  # a model that has not finished by now is left to its reflexes
ROUND2_TIMEOUT_S = 12.0
LOG_LINES = 16                                          # what a commander remembers of the last orders, words and news
LOG_KEEP = 80

ORDERS = ("auto", "attack", "pin", "flank_left", "flank_right", "screen", "withdraw", "regroup", "reinforce", "hold")
FORMATIONS = ("line", "wedge", "column", "screen")

# ------------------------------------------------------------------------------------------------ the ASTRA captains
# (ASTRA names are of the Core Worlds' mixed peoples; the captains of the opening are fixed, any other ship gets one from the pool or from the
# director's beat. The voices are Pocket TTS catalogue voices not used by the bridge crew, the admiral or the Mandate's captains.)
ALLIES: dict[str, dict[str, Any]] = {
    "T-01": dict(key="castellan", name="Captain Rhea Castellan", rank="Captain", ship="the battleship ASN Praetorian, the 7th Fleet's flagship at Aurelia",
                 voice="estelle", gender="f", precedence=1,
                 mission="Fleet's orders for the Aurelia picket: hold the approach to New Ravenna and the Janus Gate with the Aquila as the heart of the line; the "
                         "picket fights where the carrier can support it and keeps her covered; the Aquila's captain commands the picket in action.",
                 bio="Twenty-six years in the fleet, the last three as the Praetorian's captain. Formal, patient and unsentimental: she has buried "
                     "crews before and wastes no ship. She trusts Vice Admiral Rourke and serves the Aquila's captain with the loyalty the service "
                     "demands and the honest opinion nobody asked for. She speaks in plain complete sentences and never raises her voice."),
    "T-02": dict(key="okoro", name="Commander Daniel Okoro", rank="Commander", ship="the destroyer ASN Vigilant, in the Praetorian's picket",
                 voice="paul", gender="m", precedence=2,
                 bio="Thirty-four, the youngest destroyer captain of the 7th Fleet; Castellan taught him. Quick, confident, a little reckless, "
                     "he wants the Aquila's captain to notice his ship. Talks fast and jokes under fire, but never about the crew."),
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

DECIDE = _fn("decide", "A decision about the whole fight for your fleet, taking effect at once. withdraw: the fight is lost or pointless, every ship "
                       "breaks off and leaves the system through the Janus Gate (your crews' lives). continue_attack: undo a withdrawal or ceasefire. "
                       "hold_fire and accept_surrender are for what you agreed with the Captain over the channel.", {
    "order": {"type": "string", "enum": ["continue_attack", "hold_fire", "withdraw", "accept_surrender"]},
    "reason": {"type": "string"}}, ["order", "reason"])

REPORT = _fn("report", "A short word to your admiral, by datalink: what you cannot do, what you see that they do not, what you need. The admiral reads "
                       "it at once if `urgent`, otherwise at their next look.", {
    "text": {"type": "string", "description": "one or two sentences"},
    "urgent": {"type": "boolean", "description": "true only if the admiral must decide now"}}, ["text"])

NO_CHANGE = _fn("no_change", "You have looked at the picture and nothing needs changing: the orders that stand, or the group's own judgement, serve. "
                             "Say in one sentence why (it goes in your log). Call this instead of inventing an order.", {
    "reason": {"type": "string"}}, ["reason"])

POSTURE = _fn("weapons_posture", "Your group's weapons posture. hold_fire: every ship of the group stops shooting (a ceasefire, a truce being talked, "
                                 "a target that must not be hit); weapons_free: the group fights again.", {
    "posture": {"type": "string", "enum": ["hold_fire", "weapons_free"]},
    "reason": {"type": "string"}}, ["posture", "reason"])


def say_tool(speakers: list[str]) -> dict[str, Any]:
    return _fn("say", "Say something over the fleet net: the Aquila's Captain, and every allied ship, hear it. Radio speech: one or two short sentences, "
                      "in the language of the Captain (names in English). Silence is normal: speak when it helps (a warning the Captain may have "
                      "missed, a request you need answered, what you are doing that concerns the Aquila, an answer to what was said to you).", {
        "speaker": {"type": "string", "enum": speakers, "description": "which captain of your group speaks (default: the group's commander)"},
        "to": {"type": "string", "description": "who it is for: \"aquila\" (the Captain), \"fleet\" (everyone), or the id of an allied commander; only an "
                                                "addressed allied commander is woken by it"},
        "text": {"type": "string"},
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


def _member_line(m: dict[str, Any], ew: dict[str, Any] | None = None) -> str:
    bits = [f"{m.get('id', '?')} {m.get('class', '?')} hull {_pct(m.get('hull_pct'))} shields {_pct(m.get('shields_pct'))}"]
    faces = m.get("shield_faces_pct")
    if isinstance(faces, list) and len(faces) == 6:
        bits.append("faces " + " ".join(f"{n} {int(v)}" for n, v in zip(FACES, faces)))
    if m.get("missiles") is not None:
        bits.append(f"{m['missiles']} missiles")
    if m.get("status"):
        bits.append(str(m["status"]))
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
                          + (f" ({s['status']})" if s.get("status") else "") for s in g.get("ships") or [])
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
                         + (f", {s['shields']}" if s.get("shields") and s["shields"] != "balanced" else ""))
    if astra:
        lines.append(" ASTRA ships on your plot: " + "; ".join(astra))
    return "\n".join(lines), ew_by_id


def render_astra_extras(state: dict[str, Any]) -> str:
    """What an allied captain reads of the Aquila and of the ships about, from the fleet datalink: the carrier's state, the friendly ships'
    positions about her, the contacts that are only a bearing."""
    out = []
    bits = []
    for k, label in (("hull_pct", "hull"), ("alert", "alert")):
        if state.get(k) is not None:
            bits.append(f"{label} {state[k]}{'%' if k == 'hull_pct' else ''}")
    sh = (state.get("shields") or {}).get("strength_pct")
    if sh is not None:
        bits.append(f"shields {sh}%")
    for k, label, unit in (("speed_mps", "speed", " m/s"), ("heading_deg", "heading", "°")):
        if state.get(k) is not None:
            bits.append(f"{label} {state[k]}{unit}")
    if state.get("helm"):
        bits.append(f"helm: {state['helm']}")
    if state.get("target"):
        bits.append(f"her target {state['target']}")
    if bits:
        out.append(" The ASN Aquila (the Captain's ship): " + ", ".join(bits))
    friends, bearings = [], []
    for c in state.get("contacts") or []:
        st = str(c.get("status", ""))
        if st == "friendly":
            friends.append(f"{c.get('id')} {str(c.get('name') or c.get('class') or '').split(' (')[0]} {_km(c.get('range_km'))} from the Aquila, "
                           f"bearing {c.get('bearing_deg', '?')}°, hull {_pct(c.get('hull_pct'))}")
        elif st.startswith(("bearing only", "JAMMING")):
            bearings.append(f"{c.get('id')} bearing {c.get('bearing_deg', '?')}°" + (" (jamming)" if st.startswith("JAMMING") else ""))
    if friends:
        out.append(" Friendly ships about the Aquila: " + "; ".join(friends))
    if bearings:
        out.append(" Contacts with a bearing and no range (any may be a decoy): " + "; ".join(bearings))
    return "\n".join(out)


def picture(side: str, kind: str, group: str, view: dict[str, Any], state: dict[str, Any]) -> str:
    """What a commander reads of the battle: their groups (the admiral's: all in full; a group commander's: their own in full), the enemy as their
    sensors hold it, and what their seat needs besides (the Mandate admiral's fleet operations; an allied captain's Aquila and neighbours)."""
    only = None if kind == "admiral" else group
    if side == "mandate":
        extra, ew = mandate_extras(view)
        text = (f"YOUR GROUPS\n{render_groups(view, only=only, ew_by_id=ew)}\nENEMY GROUPS (ASTRA, as your sensors hold them)\n{render_enemy(view)}")
        return text + (f"\nYOUR FLEET OPERATIONS\n{extra}" if kind == "admiral" else "")
    text = f"YOUR GROUPS\n{render_groups(view, only=only)}\nENEMY GROUPS (as the fleet's sensors hold them)\n{render_enemy(view)}"
    ex = render_astra_extras(state)
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
    return own, foe


# ------------------------------------------------------------------------------------------------ the prompts
DOCTRINE = """How a fleet fights (what your officers and your own years have taught you)
- Guns: railguns reach 8-10 km and do most of the killing; lasers reach 4 km. Missiles reach far but one at a time they are shot down by point
  defence: by default each group already holds its cells until enough are ready to saturate the target's point defence, then fires them all
  together, timed to land at once, and that is the fleet's strongest punch. `salvo` forces every cell out now; `conserve` keeps them back, and
  only a reason justifies it (a long fight ahead and a magazine running dry, not a feeling). Fighters and bombers are shot at by point defence
  and by the enemy's own fighters.
- The groups run on reflexes all the time: they pick targets (concentrating fire), hold a range of about 4 km, pull their battered ships behind
  the line, and break off when they are clearly losing. The reflexes are decent. YOUR orders override them: while an order stands the group does
  not break off by itself, so withdrawing when it is lost is YOUR decision, and so is releasing it (`auto`) when the order has served.
- Range is the main lever between equals. A line that holds at the maximum railgun range leaves half its wedge out of the fight; the side that
  closes to 2.5-4 km brings every gun to bear and usually wins, at a price in damage to the closing ships. Against a heavier enemy, closing under
  its lasers is costly; against a lighter or already battered one it is the kill. A group shut out by range loses to one that closes.
- Concentrate fire: shots spread over several ships lose one or two ships in six against a line that focuses. Name the target that matters most
  and can be killed (a capital ship whose shield face is down or whose hull is going, a ship about to fall); do not chase a distant destroyer
  with a cruiser still unhurt.
- A flank sends one or two agile ships to the enemy's beam; the whole enemy line then fires on them. It pays with clear superiority, or as bait;
  against equals it costs ships. `screen` rings a friend (the Aquila) with the group's ships on the enemy's side; `pin` holds the enemy at long range
  without closing; `reinforce` sends the group to another; `regroup` stops and reforms; `hold` keeps the position.
- An order stands until you change it or its time runs out; do not repeat an order that already stands (the picture shows `order in force`).
  Change the plan when the battle gives a reason: a target crippled or about to fall, a group's morale breaking, a ship or a group lost, a new
  enemy on the plot, the order run out, the balance of strength moved, the enemy breaking off. Otherwise keep what works.
- A group's reflexes do not know your intent: tell the group in its order what you mean (the target, the range, how long)."""

MANDATE_ADMIRAL = """You are {name}, {rank} of the Kharon Mandate, aboard {ship}, commanding the Mandate's forces in {where}. {bio}
{mission}

{doctrine}

Fight like the best officer of your navy. The Kharon Mandate's way: attacks fast and concentrated, missile saturation, electronic silence and
deception (jam once found, decoys while their radar is not on you), your crews' lives weighed against the objective: when the fight is lost or
pointless, a withdrawal that saves your crews is not dishonour (`decide` withdraw). Know your ships' strengths (railguns 8-10 km against their
lasers at 4 km: a battered group is a kill if you close) and the information war: the ASTRA can shoot only what they track.

{commands}
Your group commanders are the leaders of the other groups: they think about their own group inside your intent, and `report` to you. Your orders
carry a `reason`: your subordinates read it as your intent.
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
the tools; always end with a tool call."""

ASTRA_COMMANDER = """You are {name} of the ASTRA Navy, commanding {ship}. {bio}
You command {group}: {ships}. You are an officer of the 7th Fleet defending {where}, and you fight beside the ASN Aquila, the first of her class,
whose captain (the Captain) is on the other end of the fleet net. {mission}

{world}

{doctrine}

Your orders: `group_order` for your group (by name). You also have the weapons posture (`weapons_posture`), and you talk over the fleet net with `say`
(the Aquila's Captain and the allied ships hear it; the Captain's language, names in English; radio speech, one or two short sentences).
How you talk: the fleet net is not a chat. You speak when it helps the Captain or the fleet: a warning he may have missed, a request you need
answered, what you are doing that concerns him (you are breaking off, you are closing to cover the Aquila), the answer to what he asked you, a
loss. Most of the time you say nothing and act. Never narrate the picture back to him. Never speak for the sake of speaking. {voices}

The chain of command and the Captain's words
- {chain}
- The Captain's requests reach you as words ("From the Captain, over the fleet net: ..."), or as an order he gave your group directly (the picture
  shows an order in force `by captain`: it stands; do not undo it unless the battle makes it impossible, and then tell him why in a line).
- Orders from the senior officer present are carried out, like any naval officer does: you may add a short protest or a better idea, and you do
  what he said. You decline only when it cannot be done, or would throw your ship away for nothing the senior officer could want; then you say so in a
  line, and say what you do instead. When the one who gives the order is not the senior officer present, weigh it against the senior officer's
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
                  channel_open: bool = False, ops: bool = True) -> str:
    if seat.kind == "admiral" and seat.side == "mandate":
        s = MANDATE_ADMIRAL.format(name=cmd.name, rank=cmd.rank, ship=cmd.ship, where=where, bio=cmd.bio, mission=mission, doctrine=DOCTRINE,
                                   commands=COMMANDS_OPS if ops else COMMANDS_PLAIN)
        if channel_open:
            s += ("\n\nA channel with the ASTRA captain is OPEN: they hear what you `transmit`. Silence is the usual: speak only when the picture "
                  "changed what you would say to them (a demand, a warning, an answer); one to three short sentences, formal military radio, cold "
                  "dignity, true to the battle below (what you say must match what your ships are really doing).")
        return s
    if seat.kind == "admiral":
        return ASTRA_BENCH_ADMIRAL.format(name=cmd.name, rank=cmd.rank, ship=cmd.ship, bio=cmd.bio, doctrine=DOCTRINE)
    if seat.side == "mandate":
        return MANDATE_COMMANDER.format(name=cmd.name, rank=cmd.rank, ship=cmd.ship, bio=cmd.bio, mission=mission, doctrine=DOCTRINE, where=where,
                                        group=seat.group, admiral_name=admiral_name or "the admiral")
    return ASTRA_COMMANDER.format(name=cmd.name, rank=cmd.rank, ship=cmd.ship, bio=cmd.bio, group=seat.group, ships=ships, where=where, mission=mission,
                                  world=WORLD, doctrine=DOCTRINE, chain=chain, voices=voices)


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
    aquila_km: float | None = None                      # (ASTRA group) how far from the Aquila it was at the last look
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
                 trace: Callable[[dict[str, Any]], None] | None = None) -> None:
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
        self.minds: dict[str, Mind] = {}
        self.allies: dict[str, Commander] = {}           # ASTRA captains by ship contact id
        self.pool_used = 0
        self.logs: dict[str, deque[tuple[float, str]]] = {"mandate": deque(maxlen=LOG_KEEP), "astra": deque(maxlen=LOG_KEEP)}
        self.pulses: list[dict[str, Any]] = []           # one record per pulse (the bench's costs and latencies)
        self.state: dict[str, Any] = {}
        self.admiral_contact: dict[str, str] = {}        # side -> the contact id of the commander in charge (to see a succession)
        self.t0 = self.clock()
        self.disabled = False

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
            return Commander(key=p.get("key", "cmdr_" + re.sub(r"\W", "", contact.lower())), contact=contact,
                             name=p.get("name", f"the commander of {contact}"), rank=p.get("rank", "Ferryman (ship captain)"),
                             ship=p.get("ship", "a Mandate warship"), bio=p.get("bio", "A hard, tired officer of the Outer Worlds."),
                             voice=p.get("voice", "stuart_bell"), side="mandate", mission=p.get("mission", ""))
        if contact in self.allies:
            return self.allies[contact]
        fixed = ALLIES.get(contact)
        if fixed is not None:
            return self.register_ally(contact, fixed)
        p = dict(ALLY_POOL[self.pool_used % len(ALLY_POOL)])         # a ship the story has not named a captain for: one from the pool
        self.pool_used += 1
        p["ship"] = f"the {cls or 'warship'} {contact}"
        p["key"] = "ally_" + re.sub(r"\W", "", contact.lower())
        return self.register_ally(contact, p)

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
                    self.journal(side, "command", f"the command of {seat.group or 'the fleet'} passed from {mind.commander.name} to {cmd.name} ({cmd.contact})")
                    mind.takeover = f"you have just taken command of {seat.group or 'the fleet'} from {mind.commander.name}"
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
                if settled and gap >= MIN_GAP_S[seat.role]:
                    if mine:
                        why.append("news for your group" if seat.kind == "group" else "news of the fleet")
                    if mind.new_enemy:
                        why.append("new enemy on the plot: " + ", ".join(mind.new_enemy[:6]))
            if not why and seat.side == "astra" and seat.kind == "group" and gap >= MIN_GAP_S[seat.role]:
                cur = aquila_km(view, state, seat.group)
                if cur is not None and mind.aquila_km is not None and abs(cur - mind.aquila_km) >= SEPARATION_KM:
                    why.append(f"the Aquila has {'drawn away from' if cur > mind.aquila_km else 'closed on'} your group")
                    mind.why_extra.append(f"The Aquila is now {cur:.0f} km from your ships (it was {mind.aquila_km:.0f} km at your last look).")
            if not why and mind.inbox and gap >= MIN_GAP_S[seat.role] / 2:
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
            if not hit:
                for g in v.get("your_groups") or []:
                    if m.seat.kind == "admiral" or g.get("name") == m.seat.group:
                        for x in g.get("members") or []:
                            cap = self.allies.get(str(x.get("id")))
                            names = [str(x.get("id")).lower()] + ([cap.key.lower(), cap.ship.lower(), cap.name.lower()] if cap else [])
                            hit = hit or any(want == n or (len(want) > 3 and want in n) for n in names)
            if hit:
                m.inbox.append(msg)
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
        rec: dict[str, Any] = {"t": round(now - self.t0, 1), "seat": seat.id, "who": cmd.name, "why": why, "tools": [], "ok": 0, "failed": 0, "lines": 0,
                               "cost": 0.0, "latency": 0.0, "first_call": None, "tokens_in": 0, "tokens_out": 0, "error": ""}
        CURRENT.set(mind)
        CURRENT_VIEW.set((view, state))
        try:
            system, user, tools = self._compose(mind, view, state, new_events, new_enemy, inbox, why)
            if self.trace is not None:
                rec["system"], rec["user"] = system, user
            await asyncio.wait_for(self._run(mind, system, user, tools, rec, inbox, view), timeout=PULSE_TIMEOUT_S)
        except asyncio.TimeoutError:
            rec["error"] = "timeout"
            log.warning("%s (%s): no decision in %.0f s: the group holds on its reflexes", cmd.name, seat.id, PULSE_TIMEOUT_S)
        except asyncio.CancelledError:
            rec["error"] = "cancelled"
            raise
        except Exception as exc:  # noqa: BLE001
            rec["error"] = f"{type(exc).__name__}: {exc}"[:120]
            log.exception("%s (%s): the pulse failed", cmd.name, seat.id)
            if rec["error"] and rec["error"] != "cancelled":
                await self._fallback(inbox)
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
        mission = f"Your orders: {cmd.mission}" if cmd.mission else ""
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
                               ships=ships, voices=voices, channel_open=channel_open, ops=self.ops)
        pic = picture(side, seat.kind, seat.group, view, state)
        intent = ""
        if seat.kind == "admiral" and side == "mandate":
            style = self.intel()
            if style:
                intent = ("\nWhat Mandate intelligence has learned of the Aquila's captain from earlier fights (use it: lay the trap their habits walk "
                          f"into): {style}")
        if seat.kind == "group" and side == "mandate" and admiral is not None:
            intent = (f"\nThe admiral's last intent: {admiral.intent}" if admiral.intent else "\nThe admiral has not given orders yet.")
        if mind.why_extra:
            intent += "\n" + "\n".join(mind.why_extra)
            mind.why_extra = []
        msgs = ""
        if inbox:
            msgs = "\nMESSAGES FOR YOU\n" + "\n".join(f" {max(0, self.clock() - m.t):.0f} s ago · {self._src(m)}: {m.text}" for m in inbox)
        enemy_note = f"\nNew enemy ships on your plot since your last look: {', '.join(new_enemy)}" if new_enemy else ""
        user = (f"WHAT YOU HAVE DECIDED AND SAID, AND WHAT YOU HEARD (your log, newest last)\n{self.recall(side)}\n\n"
                f"{pic}\nEVENTS SINCE YOUR LAST LOOK (newest last)\n{render_events(new_events)}{enemy_note}{intent}{msgs}\n\n"
                f"You are looking now because: {'; '.join(why)}. The Captain's language is {LANG_NAMES.get(lang, lang)} (what you say aloud is in it).\n"
                "Decide: give your orders with the tools, or call no_change.")
        tools: list[dict[str, Any]] = []
        if seat.kind == "admiral":
            tools = [group_order_tool("admiral")] + ([FLEET_OPS, DECIDE] if side == "mandate" and self.ops else []) + [NO_CHANGE]
            if channel_open:
                tools.append(TRANSMIT)
        elif side == "mandate":
            tools = [group_order_tool("commander"), REPORT, NO_CHANGE]
        else:
            tools = [group_order_tool("commander"), say_tool(speakers), POSTURE, NO_CHANGE]
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
        failed = [(n, a, r) for n, a, r in results if not r.get("ok")]
        if failed:
            await asyncio.wait_for(self._round2(mind, system, user, tools, rec, comp, results, failed, by_captain), timeout=ROUND2_TIMEOUT_S)

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
            if call.name in ("group_order", "fleet_ops", "decide", "weapons_posture"):
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
        await self.say(speaker.key, text, lang, str(a.get("tone", "calm")), urgent=urgent, answer=answer)
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
        system = system_prompt(mind.seat, cmd, self.where(self.state), cmd.mission, chain=self.chain_facts(view, self.state))
        user = (f"{render_groups(view, only=mind.seat.group)}\nENEMY\n{render_enemy(view)}\n{render_astra_extras(self.state)}\n\n{ask}")
        said: list[str] = []
        CURRENT.set(mind)
        CURRENT_VIEW.set((view, self.state))

        async def on_call(call: ToolCall) -> None:
            if call.name == "say" and str((call.arguments() or {}).get("text") or "").strip():
                said.append(str(call.arguments()["text"]).strip())

        comp = await models.chat(self.llm, COMMANDER_ROLE, messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                                 tools=[say_tool([cmd.key]), NO_CHANGE], tool_choice="auto", on_tool_call=on_call, max_tokens=140)
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
