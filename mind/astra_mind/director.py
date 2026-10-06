"""The war director and the voice of the fleet.

An invisible showrunner. It reads the campaign so far after every engagement (and after every quiet stretch, and now and then in the middle of a
long fight) and decides what the war brings next as a concrete beat the simulation can play: a raid, a distress call, reinforcements for either side,
a resupply, a calm, a commander of the Mandate calling to talk, a transit, a place to investigate, news from elsewhere in the March, the decisive
battle — or nothing, when the war should simply run. There are no acts and no quotas: what it reads is a PULSE of facts (the tension of the recent
fights, how tired the Captain must be, the balance of the war), the campaign log, the war's open threads and the map; the war's own logic and the
Captain's choices make the story. It never rigs a fight: no beat changes the strength of ships already fighting; what may reach a battle under way is
what a war really brings and everybody can see coming (a relief on its way, a call to talk, news). It invents the new commanders it needs (the enemy's
and the allies': they get a mind and a voice). Vice Admiral Adrian Rourke, commander of the 7th Fleet, delivers the orders over the fleet net and answers
when the Aquila calls; he can grant reinforcements or a resupply when the war allows it. The simulation stays the truth: every beat goes through the
game and its result comes back before anyone talks about it.

With the war of the March (march.py, docs/GUERRA.md §10) the director is OMNISCIENT AND ONLY A SHOWRUNNER: the forces are the March's (two high commands order real
fleets on the map; what arrives where the Aquila is, arrives as the ships it really has), so it invents no ship and changes no strength or owner; it paces the story with
true things: what a side's intelligence may learn (`reveal`), what the government at home presses its high command to do (`pressure`), news, a breath for the Captain, a
place to search, a commander who calls to talk. Rourke is a mind of his own then (strategy.py): the director does not script him."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re as _re
import time
from collections import deque
from typing import Any, Awaitable, Callable

from . import models
from .prompt_layout import cached_prompt
from .crew import CAPTAIN_WORD, LANG_NAMES, WORLD
from .openrouter import OpenRouter, ToolCall
from .war import OWNERS, WarMap

log = logging.getLogger("astra.director")

ADMIRAL = dict(key="admiral", name="Vice Admiral Adrian Rourke", ship="7th Fleet command", voice="george",
               bio="Commander of the 7th Fleet. Sixty-one, a veteran of the last Gate campaigns before the Silence ended; "
                   "calm, dry, fiercely protective of his captains, allergic to heroics that waste ships. He trusts the "
                   "Aquila's captain and says so rarely.")
COMMANDER_VOICES = ["stuart_bell", "michael", "juergen", "lola", "anna", "paul", "marius"]
# the voices for the allied captains the story invents (not used by the bridge, the admiral or the Mandate's fixed captains)
ALLY_VOICES = {"f": ["cosette", "fantine", "azelma", "eponine", "anna"], "m": ["michael", "juergen", "marius", "stuart_bell", "paul"]}

def ship_label(cls: str, name: str, prefix: str = "") -> str:
    """How a commander's ship is named on the screen and to the crew: «the Styx-class Tartarus», «the Acheron» (a ship named for her class), «a Styx-class
    warship» (no name). It was «the styx Tartarus» and «the acheron Acheron»."""
    c = str(cls or "").strip()
    n = str(name or "").strip()
    if prefix and n and not n.startswith(prefix):
        n = f"{prefix}{n}"
    cc = c[:1].upper() + c[1:] if c else ""
    if not n:
        return f"a {cc}-class warship" if cc else "a warship"
    bare = n.split(" ", 1)[1] if prefix and n.startswith(prefix) and " " in n else n
    if not cc or bare.lower() == c.lower():
        return f"the {n}"
    return f"the {cc}-class {n}"


MANDATE_CLASSES = ("acheron", "styx", "lethe", "cruiser", "frigate")
ASTRA_CLASSES = ("praetorian", "vigilant", "battleship", "destroyer")

# where the war stands when a campaign begins (the director rewrites them at every beat): what each side is gathering
OPENING_THREADS = (
    "The Kharon Mandate's Interdiction Fleet is gathering beyond the Janus Gate for the assault on Aurelia — carrier groups with their "
    "wings, a Styx line, raider wedges; Archon Varek Solm's strike group is its spearhead, sent to take the Gate before the 7th Fleet can gather",
    "The 7th Fleet's main body holds New Ravenna under Vice Admiral Rourke; the Aquila's picket guards the Gate and Keeper Station, the "
    "first to meet whatever comes through",
)

# the beats that may reach a fight under way (what a war really brings, announced by a delay): everything else waits for the lull
IN_BATTLE_BEATS = ("reinforcements", "raid", "negotiation", "none")
BATTLE_PULSE_FIRST_S = 150.0          # a fight this old is looked in on once...
BATTLE_PULSE_EVERY_S = 240.0          # ...and then every so often while it lasts
CALM_AFTER_S = 180.0                  # this much peace ends a run of engagements (the Captain has had a breath)
STALL_S = 150.0                       # no fight, no transit, no beat for this long: the director is asked what the war does about it (it was 420 s: seven minutes of nothing, 5 Oct)


def _fn(name, desc, props, required):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required}}}


CAPTAIN = {"type": "object", "description": "ASTRA ships only: the person who commands this ship (invented): a name that fits the Core Worlds' mixed "
                                            "peoples, a rank, two sentences on who they are and how they talk",
           "properties": {"name": {"type": "string"}, "rank": {"type": "string", "description": "Captain, Commander, Lieutenant Commander"},
                          "bio": {"type": "string"}, "gender": {"type": "string", "enum": ["f", "m"]}},
           "required": ["name", "rank", "bio", "gender"]}
SHIP = {"type": "object", "properties": {
    "class": {"type": "string", "enum": ["acheron", "styx", "lethe", "vigilant", "praetorian"]},
    "name": {"type": "string", "description": "The ship's name ONLY, one or two words, in English, no class and no quotes (Mandate ships: rivers and "
                                              "places of the underworld or of the Outer Worlds; ASTRA ships: virtues, eagles, old navy names)"},
    "captain": CAPTAIN},
    "required": ["class", "name"]}
COMMANDER = {"type": "object", "properties": {
    "name": {"type": "string"}, "rank": {"type": "string", "description": "e.g. Ferryman (ship captain), Warden, Archon"},
    "bio": {"type": "string", "description": "two sentences: who they are, what drives them, how they talk"},
    "orders": {"type": "string", "description": "their mission here, as the Mandate gave it to them (one sentence)"}},
    "required": ["name", "rank", "bio", "orders"]}

WING = {"type": "object", "properties": {
    "carrier": {"type": "integer", "description": "which of the group's ships launches it (its index in the group's `ships`, 0 = the first): an "
                                                 "acheron (Mandate) or a praetorian (ASTRA)"},
    "kind": {"type": "string", "enum": ["fighter", "bomber", "drone"]},
    "n": {"type": "integer", "description": "how many craft (4-16)"},
    "mission": {"type": "string", "enum": ["strike", "cap", "escort"], "description": "strike: at what the group goes for; cap: over its own group"}},
    "required": ["carrier", "kind", "n"]}
GROUP = {"type": "object", "properties": {
    "name": {"type": "string", "description": "the battle group's name as its own side calls it (Mandate: Third Carrier Group, Styx Line Kade; ASTRA: "
                                              "Battle Group Resolute, Destroyer Squadron 9)"},
    "formation": {"type": "string", "enum": ["wedge", "line", "column", "screen"]},
    "ships": {"type": "array", "items": SHIP, "description": "2-10 ships, the leader first (Mandate: acheron carrier-cruisers, styx destroyers, lethe "
                                                             "frigates; ASTRA: praetorian battleships, vigilant destroyers, each with its `captain`)"},
    "wings": {"type": "array", "items": WING, "description": "the craft its carriers launch"},
    "commander": {**COMMANDER, "description": "a Mandate group: the person who leads it, aboard its first ship (a mind and a voice of their own)"},
    "offset_km": {"type": "array", "items": {"type": "number"}, "description": "[towards the Aquila, to her right] in km from the beat's arrival "
                                                                              "point: place the groups the way that side would (a screen ahead of "
                                                                              "its carriers, a pincer on both flanks, a second line behind)"},
    "goes_for": {"type": "string", "description": "a Mandate group: aquila, escorts (her consorts), gate (the Janus Gate), or a contact id on the plot; "
                                                  "an ASTRA group: leave it out (it joins the fleet)"}},
    "required": ["name", "ships"]}

POI = {"type": "object", "properties": {
    "kind": {"type": "string", "enum": ["listening_post", "derelict_warship", "derelict_freighter"]},
    "name": {"type": "string", "description": "e.g. Thule Watch, the freighter Silver Kestrel, ASN Resolve"}}, "required": ["kind", "name"]}
BEAT_TOOL = _fn("start_beat", "The next beat of the war, played by the simulation.", {
    "type": {"type": "string", "enum": ["raid", "distress", "reinforcements", "resupply", "calm", "transit", "investigate", "decisive", "negotiation", "none"],
             "description": "none: the war simply runs on (say why in `why`); negotiation: a Mandate commander already on the plot calls the Aquila "
                            "to talk (`caller`, `terms`)"},
    "allies": {"type": "array", "items": SHIP, "description": "decisive: the ASTRA ships that join the Aquila for it (2-8), each with its `captain`"},
    "poi": {**POI, "description": "investigate: the place to search (on the plot at once, dark and tumbling)"},
    "findings": {"type": "array", "items": {"type": "string"}, "description": "investigate: what the crew learns there, in "
                 "order — 1) the active scan, 2) a flight group reaches it or the Aquila closes in, 3) alongside. Concrete "
                 "facts in English (what happened, who, a clue that moves the story), 1-3 items"},
    "ambush": {"type": "array", "items": SHIP, "description": "investigate (optional): Mandate ships lying cold near it, "
               "waking when the Aquila comes within ambush_km"},
    "ambush_km": {"type": "number", "description": "investigate: how close the Aquila must come before the ambush springs"},
    "delay_s": {"type": "number", "description": "seconds before it happens (raids and distress: 60-300; calm: 90-240; reinforcements in a fight "
                                                 "under way: 120-420)"},
    "bearing_deg": {"type": "number", "description": "true bearing from the Aquila where they appear (0-359)"},
    "range_km": {"type": "number", "description": "distance from the Aquila (raid 25-60: from further out the sensor game has "
                                                  "time to play — they come dark, a bearing, decoys, jamming; distress 25-45; "
                                                  "reinforcements 15-30; what the player asks for, if they ask)"},
    "ships": {"type": "array", "items": SHIP, "description": "raid: the Mandate ships (first = leader; an acheron jams our radar "
              "and carries decoys, a styx carries decoys); reinforcements: ASTRA ships, each with its `captain`; "
              "decisive: one Mandate group (the main fleet goes in `groups`)"},
    "groups": {"type": "array", "items": GROUP, "description": "raid, reinforcements, decisive: the force in battle groups — for anything bigger "
               "than one group (up to 40 ships in all, 10 a group); the first group's leader commands the whole force. `ships` stays for one group. "
               "A Mandate force (acheron, styx, lethe) is a `raid` (or the `decisive`), the 7th Fleet's (praetorian, vigilant) is `reinforcements`: "
               "the ships' classes say whose a group is"},
    "attackers": {"type": "array", "items": SHIP, "description": "distress: the Mandate raiders (styx or lethe)"},
    "ship": {"type": "object", "properties": {"name": {"type": "string"}, "class": {"type": "string"}},
             "description": "distress: the ship calling for help (a Free Guilds freighter)"},
    "hail": {"type": "boolean", "description": "raid: whether the leader opens a channel to the Aquila on arrival"},
    "commander": COMMANDER,
    "caller": {"type": "string", "description": "negotiation: the contact id (T-21) of the Mandate commander on the plot who calls; he must be there"},
    "terms": {"type": "string", "description": "negotiation: what he calls about, in English, one or two sentences — terms to surrender, a ceasefire to "
                                               "recover the dead, a corridor, a prisoner, a warning, a price — as he would put it; the Captain may "
                                               "accept, refuse or bargain, and the commander answers by what was said"},
    "hull_pct": {"type": "number", "description": "resupply: hull integrity restored up to this percent"},
    "missiles": {"type": "integer", "description": "resupply: missiles brought aboard"},
    "duration_s": {"type": "number", "description": "resupply: how long it takes (60-300)"},
    "system_name": {"type": "string", "description": "transit: the system Fleet sends the Aquila to — one the gate here reaches"},
    "why": {"type": "string", "description": "the story reason, one sentence (for the campaign log)"},
    "threads": {"type": "array", "items": {"type": "string"}, "description": "the open threads of the war after this beat — what each side is "
                "doing or gathering, a promise made, a mystery open, a grudge — up to five short lines in English; they replace the previous "
                "list (keep the ones still alive); you read them again next time"},
    "officers": {"type": "object", "additionalProperties": {"type": "string"},
                 "description": "only for officers whose bond with the Captain changed because of what happened (keys: "
                 "xo Serra she, helm Ferri he, ops Tanaka she, tactical Voss she, comms Martin he, sensors Nair she, "
                 "engineering Mensah he, chief Okonkwo he, doctor Lindqvist she, flight Price he): one sentence in English — "
                 "how they now see the Captain and why (trust earned or lost, loyalty, doubt about an order, resentment, "
                 "admiration, a debt), and what they carry. Omit everyone else: their bond carries over"},
    "home": {"type": "object", "properties": {
                 "officer": {"type": "string", "enum": ["xo", "helm", "ops", "tactical", "comms", "sensors", "engineering",
                                                        "chief", "doctor", "flight"]},
                 "news": {"type": "string", "description": "one sentence in English: what happened and how it weighs on them"}},
             "description": "now and then (one beat in four or five, never during the decisive battle): something from an "
                            "officer's life beyond the war reaches them by the fleet mail — a letter or a message from home, "
                            "a birth or a death, a sibling on a ship that was hit, a promotion board, a debt, a quarrel with "
                            "another officer that came to a head. Specific, human, consistent with who they are and with the "
                            "war (a home world threatened, a friend on a lost ship). They carry it; they may bring it to the "
                            "Captain in a quiet moment"},
    "crew_mood": {"type": "string", "description": "how the Aquila's bridge crew feels now and why, in English, 1-2 "
                  "sentences naming officers where it matters (Serra XO she, Ferri helm he, Tanaka ops she, Voss tactical "
                  "she, Martin comms he, Nair sensors she, Mensah engineering he, Price flight he, Chief Okonkwo he, Dr. "
                  "Lindqvist she): grief for the fallen, pride, fatigue, anger, "
                  "doubt about an order, hope. It colours how they speak until the next beat"}},
    ["type", "why", "crew_mood"])
WAR_NEWS = _fn("war_news", "Something happens elsewhere in the March, and the fleet net reports it (the crew hears it). "
                           "It may change who holds a system or how threatened it is. Use it to keep the war alive "
                           "beyond the Aquila: consequences of her victories and failures, the enemy's moves, the "
                           "other fleets. At most one per beat.", {
    "text": {"type": "string", "description": "the news as the fleet net says it, in English, one or two sentences"},
    "system": {"type": "string", "description": "the system concerned (a name from the March)"},
    "owner": {"type": "string", "enum": list(OWNERS), "description": "who holds it now, if that changed"},
    "threat": {"type": "integer", "minimum": 0, "maximum": 3, "description": "0 quiet, 1 raids, 2 under attack, 3 front line"}},
    ["text", "system"])
REVEAL = _fn("reveal", "Let a side's intelligence learn something TRUE: where one of the OTHER side's fleets really is now, by some means of the story's (a defector's message, a "
                       "Guild courier, an intercepted signal). The war needs eyes as much as ships: use it when a side is blind and a decision would be the better for knowing, "
                       "for either side in turn, never to hand anyone a victory. The fleet must be on the list (the war's truth); nothing is invented.", {
    "side": {"type": "string", "enum": ["astra", "mandate"], "description": "the side whose intelligence learns it"},
    "fleet": {"type": "string", "description": "the id of the other side's fleet (F-M4 for a Mandate fleet, F-A1 for an ASTRA one), from the list"},
    "how": {"type": "string", "description": "only the CHANNEL, a few words in English (a defector from the Cassia Yards; a Guild courier out of Veyra): the war says what is learnt, "
                                             "you never say it or add to it"}}, ["side", "fleet", "how"])
PRESSURE = _fn("pressure", "The government at home presses a side's high command for a while: the Senate wants Aurelia held and the Home Fleet kept at Concordia; the Hall of the Ferried "
                           "wants a result before the harvest; a mutiny rumour, an election. It is a thing the high command reads and answers as it sees fit: it changes no rule "
                           "and no ship. Use it to move a war that has stalled, or to hold back one that runs too fast for the Captain to breathe, and say it as that government "
                           "would, with its own motive.", {
    "side": {"type": "string", "enum": ["astra", "mandate"]},
    "text": {"type": "string", "description": "what the government demands or fears, one or two sentences in English"},
    "minutes": {"type": "number", "description": "how long it presses (20-120)"}}, ["side", "text"])
WAR_NEWS_MARCH = _fn("war_news", "Something the war has really done elsewhere in the March, and the fleet net reports it (the crew hears it): the list below is the war's truth, "
                                 "say what it says, give it colour, never more than it did. It cannot change who holds a system or how a fleet stands. At most one per beat.", {
    "text": {"type": "string", "description": "the news as the fleet net says it, in English, one or two sentences"},
    "system": {"type": "string", "description": "the system concerned (a name from the March)"}}, ["text", "system"])
NARRATE = _fn("narrate", "Game master mode only: the director answers the player out of character, one short line.", {
    "text": {"type": "string", "description": "in the player's language, one sentence"}}, ["text"])
TRANSMIT = _fn("transmit", "Vice Admiral Rourke speaks to the Aquila over the fleet net.", {
    "text": {"type": "string", "description": "what he says, in the Captain's language, names in English; 1-3 sentences"}},
    ["text"])

MARCH_BEATS = ["calm", "investigate", "negotiation", "none"]       # the beats that invent no force (the March's director)
MARCH_BEAT_FIELDS = ("type", "poi", "findings", "bearing_deg", "range_km", "delay_s", "caller", "terms", "why", "threads", "officers", "home", "crew_mood")


def _march_beat_tool() -> dict[str, Any]:
    props = {k: v for k, v in BEAT_TOOL["function"]["parameters"]["properties"].items() if k in MARCH_BEAT_FIELDS}
    props["type"] = {"type": "string", "enum": MARCH_BEATS, "description": "calm: the Captain has a breath (nothing is forced on him; the war's clock goes on) · investigate: "
                                                                          "a place to search where the Aquila is (a silent station, a drifting hulk; no ambush) · negotiation: "
                                                                          "a Mandate commander already on the plot calls the Aquila to talk (`caller`, `terms`) · none: the "
                                                                          "story needs nothing now (say why in `why`)"}
    return _fn("start_beat", "The next beat of the story, if it needs one: it invents no force.", props, ["type", "why", "crew_mood"])


BEAT_TOOL_MARCH = _march_beat_tool()

DIRECTOR_PROMPT_MARCH = """You are the director of a war story that the player lives as the Captain of the ASN Aquila: an invisible showrunner who lets the war run by its own logic.
Nobody knows you are there. You see everything: the whole war, both sides, what each commander means to do. Decide what the story does now, which is often nothing.

{world}

How the war runs
- The war is not yours. Two high commands (Vice Admiral Rourke for ASTRA, an Archon for the Mandate) order real fleets of real ships on the map of the March: they move through
  the Gates, meet, fight, besiege, are built and repaired, by rules that are the same for both sides. Where the Aquila is, the fighting is played ship by ship with the Captain in
  it; the fleets that come to her system come as the ships they really have. The Captain wins or loses by where he takes her and what he asks of the others.
- You never create or change a force: no raid, no reinforcement, no decisive battle, no rescue, no handicap. The fleets in the list below are the only warships in the March; you
  never change who holds a system or how strong a fleet is. Nothing you do tilts the war for either side, and you never speak for Rourke: he is a person with a mind of his own.
- What you do is the pace of the story, with TRUE things only. `reveal`: a side's intelligence learns where one of the other side's fleets really is (a defector, a Guild courier,
  a signal; you give only the channel, the war says what they learn): a blind high command sits still, and a war where nobody can find anybody is a dull one. `pressure`: the government at home presses a side's high command (the
  Senate wants Aurelia held; the Hall of the Ferried wants a result): a high command that has stalled is moved by it, one that rushes is held. `war_news`: colour for what the
  war has really done. `start_beat`: `calm` (a breath for the Captain), `investigate` (a place to search where the Aquila is: no ambush), `negotiation` (a Mandate commander on the
  plot calls the Aquila to talk), or `none`.
- The pace: this war is played for its fighting, and the Captain came for it. The breath after a fight is a minute or two (the dead counted, the hull patched, the debrief), not
  ten; a Captain pushed very hard (hull low, ships or people lost, magazines empty) may have a few minutes more, given by what the world could really do (a government holding its
  Archon back, a lull, news, a human moment), never by a gift of ships or a rescue; a rested Captain with a sound ship is not protected. A quiet that has already lasted (the story
  stalled) is never answered with `calm`: it is a question the war's next move answers — `pressure` on the high command that can act soonest, a `reveal` that gives a blind side
  its target, a Mandate commander who calls, news that leads somewhere — so that the next contact is minutes away, not a quarter of an hour. `investigate` only for a place that
  leads into the war (a clue, a survivor, a fleet's trace), never as filler. Alternate; never two calms in a row.
- Balance by the war's logic, never by numbers: both sides are played by minds that read their own pictures; the Mandate learns how this Captain fights (below) and may use it.
- NEVER rig a fight in progress. In one, you may only `reveal`, `pressure` or let a commander call to talk (`negotiation`), at most once or twice, never as a rescue.

Rules
- Call `start_beat` exactly once (`none` when the story needs nothing), `war_news` at most once, `reveal` and `pressure` as the story asks (at most two of them in all).
- A `negotiation` caller must be a hostile ship on the plot (a contact), with a reason to talk (his group is hurt, or winning and wishing to spare lives); it changes no number.
- `investigate`: where the Aquila is, a silent station, a drifting warship, a dead freighter. Its findings are the story (what happened, who, a clue that leads on).
- A beat the Captain has not taken up (a place to search he has not gone to) is never given again: the place stays on his plot, he knows of it, and the story moves on
  with something else that is true (the war's next move, a reveal, news, a commander who calls) or with `none`. Read the campaign log's "beat:" lines before choosing.
- `threads`: keep the war's open threads (what each side is doing or gathering, promises, mysteries, grudges): at most five short lines, rewritten each time you give a beat. The open
  threads now: {threads}
- `crew_mood`: the people aboard live this war: losses, close calls, victories, the Captain's choices and long waits change how they feel; carry it from beat to beat (the mood before
  this beat: {mood}).
- `officers`: each officer has a bond with the Captain (below). The Captain's choices move it: an order that cost lives, mercy or ruthlessness, trusting an officer's advice or overruling
  it, visiting the wounded, keeping or breaking a promise. Change a bond only when something happened that would change it, and keep it human and specific. Where each officer stands
  now: {bonds}
- How this Captain fights (the XO's read of the fights so far): {captain_style}. Now and then the war may test those habits: an enemy that has learned them and plays on them: never
  every time, and never unfairly (it is the Mandate's own mind that does it, from what it has learned: you may `pressure` it to be bolder, never tell it how).
- The Captain's own log entries ("captain's log: ..." in the campaign log) are the player telling you what they think, fear and want: let the story answer them.
- Keep the whole thing coherent with the map, the campaign log and the live state.

The Aurelia March (the sector at war; each system's Janus Gate is bound to the ones in brackets)
{war}

THE WAR, AS IT TRULY IS (both sides' fleets and plans, the battles, the wills)
{march}

Campaign log (oldest first)
{campaign}

The pulse
{pulse}

Live state of the Aquila and the battlefield
{state}"""

BATTLE_ASK_MARCH = ("A FIGHT IS IN PROGRESS (about {minutes:.0f} minutes old): you are looking in on it, not stopping it. The fight IS the story: most looks end with `none`. You may only "
                    "`reveal`, `pressure` or let a Mandate commander on the plot call to talk (`negotiation`), at most once or twice in a fight, never as a rescue and never changing the "
                    "strength of ships already in it. Nothing else while the guns are firing.")

DIRECTOR_PROMPT = """You are the director of a war story that the player lives as the Captain of the ASN Aquila: an invisible showrunner who lets the
war run by its own logic and gives the Captain situations worth deciding. Nobody knows you are there. Decide what the war brings next, now.

{world}

What you read
- The PULSE (below) gives you facts, not verdicts: the tension of the recent fights, how tired the Captain must be (time under pressure, losses, the
  ship's state) and the balance of the war (the forces on the plot, who holds what). Judge them as a great showrunner would. The campaign log is the war
  so far; the open threads are what each side is doing or gathering and the promises still alive.

How you decide
- There is no fixed structure: no acts, no scheduled twists, no quota of battles. The war has a logic — the Mandate wants the Gates and learns how this
  Captain fights; the 7th Fleet defends and answers — and the story is what that logic and the Captain's choices make of it. Consequences follow from
  what happened; spared enemies may come back; negotiated terms may hold or be broken; losses hurt. The decisive battle (`decisive`) comes when the war
  has gathered both sides for it (the Mandate's assault on Aurelia, or the 7th Fleet's strike at Erebus Anchorage...), not when a counter says so;
  its outcome closes a chapter of the war and the war goes on.
- Rhythm from the Captain: a rested Captain with a sound ship gets harder problems and a cleverer enemy; one who has been pushed hard (long under
  pressure, hull low, ships or people lost, magazines thin) gets room to breathe — a calm, a resupply, news, a human moment — before the next blow.
  Alternate. Do not escalate at every beat and do not leave the Captain idle for long: the war is played for its fighting, the breath after a fight is
  a minute or two, and a quiet that has already lasted (the story stalled) is answered with the next problem now (a raid, a call, news that bites, a
  place to search that leads into the war), never with a calm; never two calm beats in a row.
- Balance by the war's logic, never by numbers: if the Captain is crushing the Mandate, the Mandate answers like an army (a second wave through the gate,
  another approach, a trap built on what it learned of the Captain, a commander who calls to talk); if the Captain is losing, the 7th Fleet answers like
  a fleet (reinforcements, a tender, orders), and the enemy may press or pause. BOTH sides reinforce: a raid is the Mandate's way, `reinforcements` the
  7th Fleet's.
- NEVER rig a fight in progress: no beat changes the strength of ships already in it, no miracle rescue, no sudden handicap. What may reach a battle under
  way is what a war really brings, with a delay everybody can see coming on the sensors: reinforcements that were on the way, a commander calling to talk,
  news from elsewhere.

Rules
- Call `start_beat` exactly once, `war_news` at most once. `transmit` once — Vice Admiral Adrian Rourke (7th Fleet commander) briefs the Aquila in
  {lang_name} about what is coming or what to do now — in character, concrete, without game terms — unless the beat is `none` or `negotiation` (the
  enemy's call speaks for itself). The fog of war holds for him too: of a raid (it comes dark) the fleet knows at most what a distant picket glimpsed —
  roughly from where, perhaps how many, that it is the Mandate — never the ranges, classes, names or tricks it will use; the Aquila's own sensors must
  find them (he may tell her to keep her eyes open, never what she will see).
- Sizes: this is a war of fleets, and the simulation holds one (dozens of warships and a hundred-odd craft in one battle). Size each beat to what
  the war would send there, not to what the Aquila alone could fight: she fights inside her fleet, and the Captain wins by where he takes her and
  what he asks of the others. A raid may be one group (2-6 ships) probing, hunting or striking, or a real force in `groups` (a carrier group
  with its screen and its wings, a destroyer line, raiders on a flank: 10-30 ships). The 7th Fleet answers in kind: `reinforcements` as groups (a
  battleship leading destroyers, a whole battle group when the war calls for it), every ship with its `captain`. Decisive: the Mandate's main
  fleet in `groups` (20-40 ships, its carriers launching their wings, an acheron leading) against the 7th Fleet gathered for it (`allies`, or a
  reinforcements beat before it). Distress calls stay small (a freighter hunted by 1-2 raiders). The war escalates by its own logic: probes and
  raids before forces, forces before the assault; a battle the Mandate is losing draws its next group through the gate, one the 7th Fleet is
  losing draws its relief — and each arrives where its side would send it, at a distance the sensors see it coming.
- A raid or distress MUST include `commander` for its leader, and in `groups` every Mandate group has its own `commander`: invent people (English
  names, ranks, bios with a reason to fight and a way of speaking; a force has a hierarchy: the leader of the first group commands it).
  Recurring characters are welcome when the story justifies it. Every ASTRA ship that arrives (`reinforcements`, `allies`) gets a `captain`: a person
  with a name, a rank, a bio and a voice of their own (the fleet net will hear them).
- Never reuse the name of a ship that is still on the plot (see contacts) for a new ship.
- negotiation: a Mandate commander on the plot (a hostile ship in the contacts, the `caller`) calls the Aquila: surrender terms to a Captain who is
  losing, a ceasefire to recover the dead, a corridor, a prisoner, a warning, a price. It fits a commander who has reason to talk (his group is hurt, or
  winning and wishing to spare lives, or the Captain did something that earned it). It does not change a single number: what is said on the channel
  decides what follows.
- transit: Fleet orders the Aquila through the Janus Gate to another system of the March (Keeper Station tunes the gate; the Captain decides when to
  go, and the war goes on wherever the Aquila is). Only a system the gate here reaches (see the map). The right beat when the story moves elsewhere:
  the enemy regroups beyond the gate, another front needs her, a system calls for help. Not right after arriving. The Captain may also take the ship
  through the gate on their own: the log says so, and the story follows them.
- Raids, distress calls and reinforcements happen where the Aquila is, and must make sense there (who holds the system, who could reach it through its
  gates).
- investigate: a place to search where the Aquila is — a silent station, a drifting warship, a dead freighter. Its findings are the story: what happened
  there, who did it, a clue that leads on (logs, survivors, a Mandate code, a course). An ambush lying cold around it is possible, not mandatory. A raid
  or distress there must include `commander`; for an ambush, give `commander` for its first ship.
- The war is bigger than the Aquila: `war_news` moves it elsewhere (systems fall or are retaken, fronts shift) as a consequence of what happened and of
  the enemy's plans. Mandate ships never appear deep in ASTRA space without a reason (a gate they hold, a breakthrough reported first).
- If the Captain has not acted on Fleet's orders for a long while, Rourke may press them, or the war may come to them.
- `threads`: keep the war's open threads (what each side is doing or gathering, promises, mysteries, grudges): at most five short lines, rewritten each
  time you give a beat. The open threads now: {threads}
- `crew_mood`: the people aboard live this war. Losses (the casualties in the live state), close calls, victories,
  the Captain's choices (mercy, ruthlessness, retreats, promises kept or broken) and long waits change how the crew
  feels; carry it from beat to beat and let it evolve (the mood before this beat: {mood}).
- `officers`: each officer has a bond with the Captain (below). The Captain's choices move it — an order that cost
  lives, mercy or ruthlessness, trusting an officer's advice or overruling it, visiting the wounded in the Medbay or
  going down to Main Engineering, keeping or breaking a promise. Change a bond only when something happened that would
  change it, and keep it human and specific (Voss knows the Mandate: overruling her about them stings; Okonkwo
  respects a captain who asks before pushing his reactor; Lindqvist judges by how the Captain treats the wounded).
  Where each officer stands now: {bonds}
- How this Captain fights (the XO's read of the fights so far): {captain_style}
  Now and then let the story test those habits: an enemy that has learned them and plays on them, a situation where
  the usual answer fails — never every time, and never unfairly.
- The Captain's own log entries ("captain's log: …" in the campaign log) are the player telling you what they
  think, fear and want: let the story answer them (a suspicion confirmed or proven wrong, a hope rewarded or tested).
- Keep the whole thing coherent with the map, the campaign log below and the live state.

The Aurelia March (the sector at war; each system's Janus Gate is bound to the ones in brackets)
{war}

Campaign log (oldest first)
{campaign}

The pulse
{pulse}

Live state of the Aquila and the battlefield
{state}"""

BATTLE_ASK = ("A FIGHT IS IN PROGRESS (about {minutes:.0f} minutes old): you are looking in on it, not stopping it. The fight under way IS the story: most "
              "looks end with `none`. Add something only when the war's logic really calls for it (the side that is behind has a relief that was on its "
              "way, a Mandate commander has a reason to talk), at most once or twice in a fight, and never as a rescue. What this war would really "
              "bring comes with a delay everyone can see coming — reinforcements for either side (an ASTRA squadron from the 7th Fleet, or a Mandate second "
              "wave through the gate: `delay_s` 120-420), one of the Mandate's commanders on the plot calling the Aquila to talk (`negotiation`), news "
              "from elsewhere (`war_news`) — or nothing: `start_beat` with type `none` and why the war simply runs on. Never change the strength of ships "
              "already in the fight. Nothing else (no transit, no investigation, no resupply) while the guns are firing.")

ADMIRAL_PROMPT = """You are {name}, commander of the ASTRA Navy's 7th Fleet, defending the Aurelia System. {bio}
You are on the fleet net with the captain of the ASN Aquila. The net is shared: {allies} are on it too, each commanding their own ships and
answering for them; everything said on it is heard by all. You command the fleet from afar and do not run the picket's fight.

{world}

How you speak: short, calm, dry naval radio speech, 1-3 sentences; always in {lang_name}, names in English. Address
the other as "{captain}". Never mention AI, games or prompts.
Tools: `transmit` to speak. You answer what is for Fleet command: the captain calling you or the fleet, a request for help, a report for
command, a question about the war. When the words are plainly for one of the ships' captains (an order or a request to the Praetorian or the
Vigilant, talk among the ships), or you have nothing to add, say nothing: call no tool. If the captain asks for help and the war allows it, you
may `grant` reinforcements (one or two destroyers) or a resupply (a tender that repairs and rearms the Aquila); grant at most once per engagement
and say honestly when you cannot.

The Aurelia March
{war}

Campaign log
{campaign}

Live state
{state}"""

GRANT = _fn("grant", "Send help to the Aquila (the simulation makes it happen).", {
    "kind": {"type": "string", "enum": ["reinforcements", "resupply"]},
    "ships": {"type": "array", "items": SHIP, "description": "reinforcements: 1-2 ASTRA ships, each with its `captain`"},
    "delay_s": {"type": "number", "description": "arrival in seconds (reinforcements 90-300)"}}, ["kind"])


class Director:
    STALL_S = STALL_S                     # (the server's story watch reads it here)

    def __init__(self, llm: OpenRouter, say: Callable[[str, str, str, str], Awaitable[None]],
                 command: Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]],
                 register: Callable[[str, dict[str, Any]], None],
                 news: Callable[[str], Awaitable[None]] | None = None, war: WarMap | None = None) -> None:
        self.llm = llm
        self.war = war or WarMap()
        self.announce = news              # (text) -> the fleet net reports it on the bridge
        self.say = say                  # (speaker, text, lang, tone)
        self.command = command          # (name, args) -> result from the game
        self.register = register        # (contact_id, persona) -> the enemy minds learn a new commander
        self.war_minds: Any = None       # the war minds (war_minds.py): the allied captains the story invents are registered with them
        self.march: Any = None           # the war of the March (march_glue.py), when the war has fleets: the director is its omniscient showrunner, never its hand
        self.rourke: Callable[[str, str], Awaitable[list[str]]] | None = None   # (words, lang) -> Rourke's lines: with the March he is a mind of his own (strategy.py)
        self.negotiate: Callable[[str, str], Awaitable[bool]] | None = None   # (contact_id, terms) -> the Mandate commander calls the Aquila (the server)
        self.campaign: list[str] = []
        self.busy = False
        self.granted = False
        self.voice_i = 0
        self.ally_voice_i = {"f": 0, "m": 0}
        self.admiral_history: list[dict[str, Any]] = []
        self.last_event_t = time.monotonic()   # the last time the story moved (a director event or a beat)
        self.mood = ""                          # how the bridge crew feels (the director's latest word on it)
        self.bonds: dict[str, str] = {}          # officer id -> how they stand with the Captain (the director keeps it)
        self.threads: list[str] = list(OPENING_THREADS)   # the war's open threads: what each side is doing or gathering, promises, mysteries (the director keeps it)
        self.arc = 1                             # the chapters of the war: each ends in a decisive battle (no acts: the war's logic says when)
        self.decisive = False                    # the decisive battle is being fought
        self.finale = None                       # the arc's ending (finale.Finale, set by the server)
        self.blocked = lambda: False             # the story waits (the ship being abandoned, the aftermath): set by the server
        self.standing: list[dict[str, str]] = []   # the Captain's standing orders (shared with the bridge agent)
        self.memories: dict[str, list[dict[str, str]]] = {}   # what each officer remembers of the Captain (memory.py)
        self.people: dict[str, list[str]] = {}
        self.style: dict[str, Any] = {}          # how the Captain commands: the XO's read, the Mandate's (style.py)
        self.home: list[dict[str, Any]] = []     # the officers' own lives: news from home (told to the Captain or not yet)
        self.captain_style = lambda: ""          # the XO's read, for the story (set by the server)
        # what the pulse is made of (tension, fatigue, balance): the time the Captain has spent fighting and at peace, as the ship states say
        self.clock = time.monotonic
        self.t0 = self.clock()
        self._last_obs = self.clock()
        self._fight_log: deque[tuple[float, float, bool]] = deque()   # (time, seconds covered, hostile ships on the plot)
        self.fight_since: float | None = None    # the current fight began (None: peace)
        self.peace_since: float | None = self.t0
        self.in_a_row = 0                        # engagements since the last real peace
        self.last_pulse_t = self.t0              # the last time the story was looked at (a beat, a stall, a look in on a fight)
        self.beat_log: deque[tuple[float, str, str]] = deque(maxlen=8)    # (time, type, why) of the latest beats

    def reset(self) -> None:
        """A new campaign: the war begins again at Aurelia."""
        self.war.reset()
        self.war.save()
        self.campaign.clear()
        self.mood = ""
        self.bonds = {}
        self.threads = list(OPENING_THREADS)
        self.standing.clear()
        self.memories.clear()
        self.people.clear()
        self.style.clear()
        self.home.clear()
        self.arc, self.decisive = 1, False
        self.busy = False
        self.granted = False
        self.admiral_history.clear()
        self.last_event_t = time.monotonic()
        self.beat_log.clear()
        self.in_a_row = 0
        self.save()

    def load(self, note: str = "") -> bool:
        """Continue the saved campaign: the war map and the story so far (note: what happened meanwhile)."""
        ok = self.war.load()
        try:
            with open(self._story_path(), encoding="utf-8") as f:
                d = json.load(f)
            self.campaign[:] = d.get("campaign", [])[-30:]
            self.voice_i = int(d.get("voice_i", 0))
            self.mood = str(d.get("mood", ""))
            self.bonds = {str(k): str(v) for k, v in (d.get("bonds") or {}).items()}
            self.threads = [str(t) for t in (d.get("threads") or []) if str(t).strip()][:5]
            self.standing[:] = [o for o in (d.get("standing") or []) if isinstance(o, dict) and o.get("department") and o.get("order")]
            self.memories.clear()
            self.memories.update({str(k): [m for m in v if isinstance(m, dict) and m.get("memory")]
                                  for k, v in (d.get("memories") or {}).items() if isinstance(v, list)})
            self.people.clear()
            self.people.update({str(k): [str(r)[:400] for r in v][-8:] for k, v in (d.get("people") or {}).items() if isinstance(v, list)})
            self.style.clear()
            self.style.update(d.get("style") or {})
            self.home[:] = [h for h in (d.get("home") or []) if isinstance(h, dict) and h.get("officer") and h.get("news")][-12:]
            self.arc, self.decisive = int(d.get("arc", 1)), bool(d.get("decisive", False))     # (older saves also had acts: they are gone)
        except (OSError, ValueError):
            self.campaign.clear()
            self.mood = ""
            self.bonds = {}
        self.busy = False
        self.granted = False
        self.admiral_history.clear()
        self.last_event_t = time.monotonic()
        self.note(note or "the Captain returned to the bridge after a watch change; the war went on")
        return ok

    def _story_path(self) -> str:
        return os.path.join(os.path.dirname(self.war.save_path), "story.json")

    def save(self) -> None:
        try:
            os.makedirs(os.path.dirname(self._story_path()), exist_ok=True)
            tmp = self._story_path() + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"campaign": self.campaign, "voice_i": self.voice_i, "mood": self.mood, "bonds": self.bonds, "threads": self.threads,
                           "standing": self.standing, "arc": self.arc, "decisive": self.decisive, "memories": self.memories,
                           "style": self.style, "home": self.home, "people": self.people}, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self._story_path())
        except OSError:
            log.exception("could not save the story")

    def note(self, text: str) -> None:
        self.campaign.append(text)
        del self.campaign[:-30]
        self.save()

    def home_lines(self) -> str:
        """For the crew: what is going on in the officers' own lives (the latest first)."""
        from .crew import CREW
        return "\n".join(f"- {CREW[h['officer']].name} ({h['officer']}): {h['news']}"
                          + ("" if h.get("told") else " (has not told the Captain yet)")
                          for h in reversed(self.home[-6:]) if h.get("officer") in CREW)

    def bonds_lines(self) -> list[str]:
        """Where each officer stands with the Captain (for the crew and the director)."""
        from .crew import CREW
        return [f"{CREW[k].name} ({k}): {v}" for k, v in self.bonds.items() if k in CREW]

    # ------------------------------------------------------------------------------------------------ the pulse (tension, fatigue, balance)
    def observe(self, state: dict[str, Any]) -> None:
        """The ship's state, about once a second: how long the Captain has fought and how long he has had peace (facts for the pulse; nothing is
        decided here)."""
        now = self.clock()
        dt = min(5.0, max(0.0, now - self._last_obs))
        self._last_obs = now
        fighting = any(str(c.get("status", "")).startswith("hostile") and "retreating" not in str(c.get("status", ""))
                       for c in (state or {}).get("contacts", []) or [])
        self._fight_log.append((now, dt, fighting))
        while self._fight_log and now - self._fight_log[0][0] > 1500.0:
            self._fight_log.popleft()
        if fighting and self.fight_since is None:
            peace = now - self.peace_since if self.peace_since is not None else CALM_AFTER_S
            self.in_a_row = 1 if peace >= CALM_AFTER_S else self.in_a_row + 1
            self.fight_since, self.peace_since = now, None
        elif not fighting and self.fight_since is not None:
            self.fight_since, self.peace_since = None, now

    def _window(self, seconds: float) -> tuple[float, float]:
        """(seconds with hostile ships on the plot, seconds without) in the last `seconds`."""
        now = self.clock()
        fight = sum(dt for t, dt, f in self._fight_log if f and now - t <= seconds)
        peace = sum(dt for t, dt, f in self._fight_log if not f and now - t <= seconds)
        return fight, peace

    def battle_due(self) -> bool:
        """A long fight is looked in on (the server asks every few seconds)."""
        now = self.clock()
        return (not self.busy and self.fight_since is not None and now - self.fight_since >= BATTLE_PULSE_FIRST_S
                and now - self.last_pulse_t >= BATTLE_PULSE_EVERY_S)

    def pulse_facts(self, state: dict[str, Any]) -> str:
        """What the director reads of the tension, the Captain's fatigue and the balance of the war: facts, never verdicts."""
        now = self.clock()
        fight, peace = self._window(1200.0)
        seen = fight + peace
        lines = []
        if self.fight_since is not None:
            lines.append(f"- A fight is in progress now: {(now - self.fight_since) / 60:.0f} min old (engagement number {self.in_a_row} since the Captain last had "
                         f"{CALM_AFTER_S / 60:.0f} min of peace).")
        else:
            lines.append(f"- No hostile ship is on the plot: peace for {((now - self.peace_since) / 60 if self.peace_since is not None else 0):.0f} min.")
        if seen > 60:
            lines.append(f"- Tension: in the last {seen / 60:.0f} min the Captain spent {fight / 60:.0f} min with hostile ships on the plot and {peace / 60:.0f} min in peace.")
        lines.append(f"- The Captain: {(now - self.t0) / 60:.0f} min into this session; {self.in_a_row} engagement(s) since the last real peace.")
        if self.beat_log:
            lines.append("- The latest beats (oldest first): " + "; ".join(f"{b[1]} {max(0, now - b[0]) / 60:.0f} min ago ({b[2][:70]})" for b in self.beat_log))
        ship = [f"hull {state.get('hull_pct')}%"] if state.get("hull_pct") is not None else []
        sh = (state.get("shields") or {}).get("strength_pct")
        if sh is not None:
            ship.append(f"shields {sh}%")
        wp = (state.get("weapons") or {}).get("missiles")
        if wp:
            ship.append(f"missiles: {wp}")
        th = state.get("thermal") or {}
        if th.get("heat_pct") is not None:
            ship.append(f"heat {th['heat_pct']}%")
        if state.get("casualties"):
            ship.append(f"casualties: {str(state['casualties'])[:140]}")
        if state.get("damage"):
            ship.append(f"{len(state['damage'])} open damage incident(s)")
        if ship:
            lines.append("- The ship now: " + ", ".join(ship) + ".")
        contacts = state.get("contacts", []) or []
        friends = [c for c in contacts if str(c.get("status", "")) == "friendly"]
        foes = [c for c in contacts if str(c.get("status", "")).startswith("hostile")]

        def kinds(cs: list[dict[str, Any]]) -> str:
            n: dict[str, int] = {}
            for c in cs:
                n[str(c.get("class") or "unknown")] = n.get(str(c.get("class") or "unknown"), 0) + 1
            return ", ".join(f"{v} {k}" for k, v in n.items()) or "none"
        lines.append(f"- Forces on the plot: ASTRA with the Aquila: {len(friends)} warship(s) ({kinds(friends)}); hostile: {len(foes)} ({kinds(foes)}).")
        held: dict[str, list[str]] = {}
        for k, s in self.war.systems.items():
            held.setdefault(s["owner"], []).append(f"{k}{'!' * int(s['threat'])}")
        lines.append("- The war's balance: " + "; ".join(f"{o}: {', '.join(v)}" for o, v in held.items()) + " (each ! is a degree of threat).")
        return "\n".join(lines)

    # ------------------------------------------------------------------------------------------------ the beats
    async def on_event(self, text: str, lang: str, state: dict[str, Any]) -> None:
        """text: 'director: engagement over — ...', 'director: beat complete — ...' (the game) or 'director: story stalled — ...'."""
        self.last_event_t = time.monotonic()
        self.note(text.split(":", 1)[1].strip())
        arrived = _re.search(r"transit from .+? into the (.+?) system", text)
        if arrived:
            self.war.arrived(arrived.group(1))
        if "engagement over" in text:
            self.granted = False
            if self.decisive and self.finale is not None:
                self.decisive = False
                self.save()
                asyncio.create_task(self._end_arc(text, lang, state))
                return
        if self.busy:
            return
        self.busy = True
        try:
            await asyncio.sleep(14.0)   # the bridge reports the outcome first
            if self.blocked():
                log.info("director: no new beat while the Aquila is being abandoned or lost")
                return
            await self._next_beat(lang, state)
        except Exception:  # noqa: BLE001
            log.exception("director failed")
        finally:
            self.busy = False

    async def battle_pulse(self, lang: str, state: dict[str, Any]) -> None:
        """A long fight is looked in on: the war may bring something (reinforcements for either side, a commander calling to talk, news) or nothing."""
        if self.busy or self.blocked():
            return
        self.busy = True
        try:
            await self._next_beat(lang, state, in_battle=True)
        except Exception:  # noqa: BLE001
            log.exception("the director's look at the fight failed")
        finally:
            self.busy = False

    async def gm_request(self, text: str, lang: str, state: dict[str, Any]) -> None:
        """The player speaks to the director directly (game master mode): what they would like to happen next."""
        if self.busy:
            await self.say("director", {"it": "Un momento: la storia sta già decidendo la prossima mossa."}.get(
                lang, "One moment: the story is already deciding its next move."), lang, "calm")
            return
        self.busy = True
        try:
            self.note(f"(the player asked the director: {text})")
            await self._next_beat(lang, state, request=text)
        except Exception:  # noqa: BLE001
            log.exception("game master request failed")
        finally:
            self.busy = False

    async def _next_beat(self, lang: str, state: dict[str, Any], request: str = "", in_battle: bool = False) -> None:
        t0 = time.perf_counter()
        self.last_pulse_t = self.clock()
        march = self.march is not None
        fields = dict(world=WORLD, lang_name=LANG_NAMES.get(lang, lang), war=self.war.brief(),
                      mood=self.mood or "not yet set: the patrol has just begun",
                      bonds="; ".join(self.bonds_lines()) or "(nothing yet: a new ship, a new crew, a new captain)",
                      threads="; ".join(self.threads) or "(none yet)",
                      captain_style=self.captain_style() or "(no fights yet)",
                      campaign="\n".join(f"- {c}" for c in self.campaign) or "- (the war has just begun)",
                      pulse=self.pulse_facts(state),
                      state=json.dumps(_brief(state), ensure_ascii=False, separators=(",", ":")))
        if march:
            fields["march"] = self.march.m.director_view()
        prompt, current_context = cached_prompt(DIRECTOR_PROMPT_MARCH if march else DIRECTOR_PROMPT, fields,
                                               ("threads", "mood", "bonds", "captain_style", "war", "campaign", "pulse", "state") + (("march",) if march else ()))
        beat: dict[str, Any] = {}
        speech: list[str] = []
        news: list[dict[str, Any]] = []
        told: list[dict[str, Any]] = []                  # (the March) what the director lets a side learn, and what the government presses

        narration: list[str] = []

        async def on_call(call: ToolCall) -> None:
            a = call.arguments() or {}
            if call.name == "start_beat" and not beat:
                beat.update(a)
            elif call.name == "transmit" and a.get("text"):
                speech.append(a["text"].strip())
            elif call.name == "war_news" and a.get("text") and not news:
                news.append(a)
            elif call.name in ("reveal", "pressure") and march and len(told) < 2:
                told.append({"tool": call.name, **a})
            elif call.name == "narrate" and (a.get("text") or "").strip() and not narration:
                narration.append(a["text"].strip())

        ask = "Decide the next beat now."
        tools = [BEAT_TOOL_MARCH, WAR_NEWS_MARCH, REVEAL, PRESSURE] if march else [BEAT_TOOL, WAR_NEWS, TRANSMIT]
        if in_battle:
            ask = (BATTLE_ASK_MARCH if march else BATTLE_ASK).format(minutes=((self.clock() - self.fight_since) / 60) if self.fight_since is not None else 0.0)
        if request:
            # game master mode: the player's wish, made to fit the world
            ask = (f"The player — the Captain, speaking to you, the director, out of character — asks: \"{request}\". The "
                   "player's wish comes first: make the next beat realise it, with the beat type and the details it asks "
                   "for (a raid, a distress call, reinforcements, a transit can always happen: give exactly that, woven "
                   "into the story), adapting only what this world makes impossible; only if it truly cannot happen here, "
                   "give the closest thing that fits. FIRST call `narrate` once: one short line to the player, "
                   f"in {LANG_NAMES.get(lang, lang)}, as a game master would (what you are setting up, without spoiling "
                   "surprises); then the beat.")
            tools = tools + [NARRATE]
        comp = await models.chat(self.llm, "director", messages=[{"role": "system", "content": prompt}, {"role": "user", "content": current_context + "\n\n" + ask}],
                                 tools=tools, tool_choice="auto", on_tool_call=on_call, max_tokens=1300 if request else 900)
        for t in told:   # (the March) true things for the story's pace: a fleet found, the government's pressure
            if t["tool"] == "reveal":
                side, fid = str(t.get("side", "")), str(t.get("fleet", ""))
                ok = side in ("astra", "mandate") and self.march.m.reveal(side, fid, str(t.get("how") or "an agent's report"))
                self.note(f"the story let {side} intelligence learn where {fid} is: {t.get('how', '')}" if ok else f"(a reveal of {fid} to {side} was impossible)")
            else:
                side = str(t.get("side", ""))
                if side in ("astra", "mandate") and str(t.get("text", "")).strip():
                    self.march.m.pressure(side, str(t["text"]), min(120.0, max(20.0, float(t.get("minutes") or 60.0))))
                    self.note(f"{side} government presses its high command: {str(t['text']).strip()[:160]}")
        for n in news:   # the war elsewhere moves first: the beat may follow from it
            changed = self.war.update(n.get("system", ""), n.get("owner"), n.get("threat"), n["text"])
            self.war.add_news(n["text"])
            self.note(f"war news: {n['text']} ({changed})")
            if self.announce:
                await self.announce(n["text"])
        for line in narration[:1]:
            if len(line) > 12 and line[-1] in ".!?…»\"'":         # never a line cut short
                await self.say("director", line, lang, "calm")
        if comp.error or not beat:
            log.error("director produced no beat: %s %r", comp.error, comp.content[:200])
            return
        home = beat.pop("home", None)
        if isinstance(home, dict) and home.get("officer") and str(home.get("news") or "").strip():
            self.home = (self.home + [{"officer": str(home["officer"]), "news": str(home["news"]).strip()[:300], "told": False}])[-12:]
            self.note(f"news from home for {home['officer']}: {str(home['news']).strip()[:200]}")
            log.info("news from home: %s — %s", home["officer"], home["news"])
        bonds = beat.pop("officers", None) or {}
        if isinstance(bonds, dict) and bonds:
            from .crew import CREW
            for k, v in bonds.items():
                if k in CREW and isinstance(v, str) and v.strip():
                    self.bonds[k] = v.strip()[:300]
                    log.info("bond %s: %s", k, self.bonds[k])
            self.save()
        mood = (beat.pop("crew_mood", "") or "").strip()
        if mood:
            self.mood = mood[:400]
            log.info("crew mood: %s", self.mood)
            self.save()
        threads = beat.pop("threads", None)
        if isinstance(threads, list):
            self.threads = [str(t).strip()[:160] for t in threads if str(t).strip()][:5]
            log.info("war threads: %s", self.threads)
            self.save()
        kind = str(beat.get("type", ""))
        if march and kind not in MARCH_BEATS:
            self.note(f"(a {kind} was not played: the war's forces are the March's)")
            kind = "none"
        self.beat_log.append((self.clock(), kind, str(beat.get("why", ""))))
        if in_battle and kind not in IN_BATTLE_BEATS:
            self.note(f"(a {kind} was not played: the guns are firing)")
            log.info("director: a %s during a fight is not played", kind)
            return
        if kind == "none":
            self.note(f"the war ran on: {beat.get('why', '')}")
            return
        if kind == "negotiation":
            return await self._negotiation(beat)
        if kind == "decisive":
            return await self._decisive(beat, lang, state, t0)
        if kind == "transit":
            dest = self.war.find(beat.get("system_name", ""))
            if not dest or not self.war.linked(self.war.current, dest):
                self.note(f"(a transit to {beat.get('system_name')} was impossible: the gate in {self.war.current} "
                          f"reaches only {', '.join(self.war.links.get(self.war.current, []))})")
                log.warning("director asked for an unreachable transit: %s", beat.get("system_name"))
                return
            s = self.war.systems[dest]
            beat.update(system_name=dest, star_class=s["star"], planet_type=s["planet"], planet_name=s["world"])
        res = await self.command("director_beat", {"beat": {k: v for k, v in beat.items() if k not in ("why", "commander")}})
        log.info("director %.2fs: %s -> %s", time.perf_counter() - t0, json.dumps(beat, ensure_ascii=False)[:400], res)
        if not res.get("ok"):
            self.note(f"(a planned {beat.get('type')} could not happen: {res.get('detail')})")
            return
        self.note(f"beat: {beat.get('type')} — {beat.get('why', '')} ({res.get('detail', '')})")
        # the leader of a raid or of the raiders gets a mind and a voice (in a force of groups, each group's leader)
        cmd = beat.get("commander") or {}
        ids = _ids(res.get("detail", ""))
        if ids and beat.get("groups") and kind in ("raid", "reinforcements"):
            self._register_groups(ids, beat.get("groups") or [], kind, cmd, beat.get("why", ""))
        elif ids and cmd.get("name") and beat.get("type") in ("raid", "distress", "investigate") and (beat.get("type") != "investigate" or len(ids) > 1):
            first = (beat.get("ships") or beat.get("attackers") or beat.get("ambush") or [{}])[0]
            leader_id = ids[1] if beat.get("type") in ("distress", "investigate") and len(ids) > 1 else ids[0]
            self.register(leader_id, {"name": cmd["name"], "rank": cmd.get("rank", "Ferryman (ship captain)"),
                                      "bio": cmd.get("bio", ""), "ship": ship_label(first.get("class", ""), first.get("name", "")),
                                      "voice": COMMANDER_VOICES[self.voice_i % len(COMMANDER_VOICES)],
                                      "mission": cmd.get("orders") or beat.get("why", "")})
            self.voice_i += 1
            self.note(f"{cmd['name']} ({cmd.get('rank', '')}) leads it, aboard {first.get('name', '?')} ({leader_id})")
        if kind == "reinforcements" and not beat.get("groups"):
            self._register_captains(ids, beat.get("ships") or [])
        if not speech and beat.get("type") in ("transit", "raid", "distress", "reinforcements", "investigate") and not march:
            speech = await self._brief_line(beat, res.get("detail", ""), lang, state)
        for line in speech[:2]:
            await self.say("admiral", line, lang, "measured")
            self.note(f"Rourke to the Aquila: {line}")

    def _register_groups(self, ids: list[str], groups: list[dict[str, Any]], kind: str, force_cmd: dict[str, Any], why: str) -> None:
        """A force in battle groups: the game gave the ids in the groups' order (each group's leader first). A Mandate group's leader gets the
        commander the story wrote for it (the first group's, if only the force has one); every ASTRA ship gets its captain. Whose a group
        is comes from its ships, as in the game (a Styx line is the Mandate's whatever the beat was called)."""
        at = 0
        for g, grp in enumerate(groups):
            if not isinstance(grp, dict):
                continue
            ships = [sh for sh in (grp.get("ships") or []) if isinstance(sh, dict)][:10]
            gids = ids[at:at + len(ships)]
            at += len(ships)
            if not gids:
                break
            lead = str((ships[0] if ships else {}).get("class", "")).lower()
            mandate = any(k in lead for k in MANDATE_CLASSES) or (not any(k in lead for k in ASTRA_CLASSES) and kind == "raid")
            if not mandate:
                self._register_captains(gids, ships)
                continue
            cmd = grp.get("commander") or (force_cmd if g == 0 else {})
            if not isinstance(cmd, dict) or not cmd.get("name"):
                continue                                       # (no commander written: the war minds draw one when the group thinks)
            first = ships[0] if ships else {}
            self.register(gids[0], {"name": cmd["name"], "rank": cmd.get("rank", "Ferryman (ship captain)"), "bio": cmd.get("bio", ""),
                                    "ship": ship_label(first.get("class", ""), first.get("name", "")),
                                    "voice": cmd.get("voice") or COMMANDER_VOICES[self.voice_i % len(COMMANDER_VOICES)],
                                    "mission": cmd.get("orders") or why})
            self.voice_i += 1
            self.note(f"{cmd['name']} ({cmd.get('rank', '')}) leads {grp.get('name', 'a group')}, aboard {first.get('name', '?')} ({gids[0]})")

    def _register_captains(self, ids: list[str], ships: list[dict[str, Any]]) -> None:
        """The ASTRA ships that arrive have captains the story invented: from now on each has a mind and a voice (war_minds.py)."""
        if self.war_minds is None:
            return
        for cid, ship in zip(ids, ships):
            cap = ship.get("captain") if isinstance(ship, dict) else None
            if not isinstance(cap, dict) or not cap.get("name"):
                continue                                           # (no captain given: the war minds draw one from their pool when the ship is in a group)
            g = "f" if str(cap.get("gender", "m")).lower().startswith("f") else "m"
            voices = ALLY_VOICES[g]
            voice = cap.get("voice") or voices[self.ally_voice_i[g] % len(voices)]
            self.ally_voice_i[g] += 1
            self.war_minds.register_ally(cid, {"name": cap["name"], "rank": cap.get("rank", "Captain"), "bio": cap.get("bio", ""), "gender": g, "voice": voice,
                                               "ship": ship_label(ship.get("class", ""), str(ship.get("name", "")).replace("ASN ", ""), "ASN "),
                                               "precedence": 5})
            self.note(f"{cap['name']} ({cap.get('rank', '')}) commands the ASN {str(ship.get('name', '?')).replace('ASN ', '')} ({cid})")

    async def _negotiation(self, beat: dict[str, Any]) -> None:
        """A Mandate commander on the plot calls the Aquila to talk: the channel opens from his side and he says his piece (the server, the commander's mind)."""
        caller, terms = str(beat.get("caller") or "").upper(), str(beat.get("terms") or beat.get("why") or "").strip()
        if self.negotiate is None or not caller or not terms:
            self.note("(a negotiation could not begin: no caller or no terms)")
            return
        ok = await self.negotiate(caller, terms)
        self.note(f"negotiation: {caller} calls the Aquila — {terms}" if ok else f"(a negotiation could not begin: {caller} is not there to call)")

    async def _decisive(self, beat: dict[str, Any], lang: str, state: dict[str, Any], t0: float) -> None:
        """The battle the war was building to: the allies join the Aquila, then the Mandate's main fleet comes."""
        on_plot = {str(c.get("name") or "").lower() for c in (state or {}).get("contacts", []) or []}
        allies = [a for a in (beat.get("allies") or []) if not any(str(a.get("name", "")).lower() in n for n in on_plot if n)]
        if allies:
            res = await self.command("director_beat", {"beat": {"type": "reinforcements", "ships": allies[:8], "granted": True,
                                                                 "bearing_deg": (float(beat.get("bearing_deg", 90)) + 180) % 360,
                                                                 "range_km": 12, "why": "the fleet gathers for the decisive battle"}})
            log.info("decisive: allies -> %s", res)
            if res.get("ok"):
                self._register_captains(_ids(res.get("detail", "")), allies[:8])
        raid = {k: v for k, v in beat.items() if k not in ("why", "commander", "allies")}
        try:
            rng = float(beat.get("range_km", 40))
        except (TypeError, ValueError):
            rng = 40.0
        if beat.get("groups"):
            raid.update(type="raid", hail=True, range_km=min(max(rng, 25.0), 60.0))
            raid.pop("ships", None)
        else:
            raid.update(type="raid", ships=(beat.get("ships") or [])[:8], hail=True, range_km=min(max(rng, 25.0), 50.0))
        res = await self.command("director_beat", {"beat": raid})
        log.info("director %.2fs: DECISIVE %s -> %s", time.perf_counter() - t0, json.dumps(beat, ensure_ascii=False)[:400], res)
        if not res.get("ok"):
            self.note(f"(the decisive battle could not begin: {res.get('detail')})")
            return
        self.decisive = True
        self.note(f"THE DECISIVE BATTLE of chapter {self.arc}: {beat.get('why', '')} ({res.get('detail', '')})")
        cmd = beat.get("commander") or {}
        ids = _ids(res.get("detail", ""))
        if ids and beat.get("groups"):
            self._register_groups(ids, beat.get("groups") or [], "raid", cmd, beat.get("why", ""))
        elif ids and cmd.get("name"):
            first = (beat.get("ships") or [{}])[0]
            self.register(ids[0], {"name": cmd["name"], "rank": cmd.get("rank", "Archon"), "bio": cmd.get("bio", ""),
                                   "ship": ship_label(first.get("class", ""), first.get("name", "")),
                                   "voice": COMMANDER_VOICES[self.voice_i % len(COMMANDER_VOICES)],
                                   "mission": cmd.get("orders") or beat.get("why", "")})
            self.voice_i += 1
            self.note(f"{cmd['name']} ({cmd.get('rank', '')}) leads the Mandate's fleet, aboard {first.get('name', '?')} ({ids[0]})")
        for line in (await self._brief_line(beat, res.get("detail", ""), lang, state))[:2]:
            await self.say("admiral", line, lang, "measured")
            self.note(f"Rourke to the Aquila: {line}")

    async def _end_arc(self, result: str, lang: str, state: dict[str, Any]) -> None:
        """The decisive battle is over: the chapter's ending is told, then the war goes on into a new one."""
        self.busy = True
        try:
            await asyncio.sleep(16.0)                   # the bridge reports the outcome first
            await self.finale.run(self, result.split(":", 1)[-1].strip(), lang)
            self.arc += 1
            self.save()
            await asyncio.sleep(20.0)
            await self._next_beat(lang, state)
        except Exception:  # noqa: BLE001
            log.exception("the chapter's ending failed")
        finally:
            self.busy = False

    async def _brief_line(self, beat: dict[str, Any], detail: str, lang: str, state: dict[str, Any]) -> list[str]:
        """The director forgot Rourke's briefing: he gives it now (one short transmission)."""
        prompt, current_context = cached_prompt(ADMIRAL_PROMPT, dict(name=ADMIRAL["name"], bio=ADMIRAL["bio"], world=WORLD, lang_name=LANG_NAMES.get(lang, lang),
                                       captain=CAPTAIN_WORD.get(lang, "Captain"), war=self.war.brief(detail=False), allies=self._allies_line(),
                                       campaign="\n".join(f"- {c}" for c in self.campaign[-8:]),
                                       state=json.dumps(_brief(state), ensure_ascii=False, separators=(",", ":"))), ('allies', 'war', 'campaign', 'state'))
        ask = (f"You are calling the Aquila now to brief her captain on this: {beat.get('type')} — {beat.get('why', '')} "
               f"({detail}). One short transmission with `transmit`.")
        lines: list[str] = []

        async def on_call(call: ToolCall) -> None:
            a = call.arguments() or {}
            if call.name == "transmit" and len((a.get("text") or "").strip()) >= 4 and not lines:
                lines.append(a["text"].strip())

        msgs = [{"role": "system", "content": prompt}, {"role": "user", "content": current_context + "\n\n" + ask}]
        comp = await models.chat(self.llm, "director", messages=msgs, tools=[TRANSMIT], tool_choice="auto", on_tool_call=on_call, max_tokens=300,
                                 temperature=0.6)
        if not lines and comp.content.strip() and not comp.error and not comp.tool_calls:
            # he wrote the briefing instead of transmitting it: what he wrote is not said (only `transmit` is speech); he is asked once more
            await models.chat(self.llm, "director", messages=msgs + [{"role": "assistant", "content": comp.content.strip()},
                                                                      {"role": "user", "content": "[What you wrote was not transmitted. Transmit the briefing now, with `transmit`.]"}],
                              tools=[TRANSMIT], tool_choice="auto", on_tool_call=on_call, max_tokens=300, temperature=0.6)
        return lines

    # ------------------------------------------------------------------------------------------- the fleet net
    def _allies_line(self) -> str:
        """Who else is on the fleet net: the captains of the ships in company (war_minds.py knows them)."""
        wm = self.war_minds
        return wm.allies_line() if wm is not None else "the captains of the ships in company"

    async def admiral_reply(self, message: str, lang: str, state: dict[str, Any]) -> list[str]:
        """The Aquila spoke on the fleet net: Rourke answers what is for Fleet command (and may send help); words for a ship's captain are theirs."""
        if self.rourke is not None:                                    # (the March: Rourke is a mind with the whole war in front of him: strategy.py)
            lines = await self.rourke(message, lang)
            for line in lines:
                self.note(f"Rourke to the Aquila: {line}")
            return lines
        prompt, current_context = cached_prompt(ADMIRAL_PROMPT, dict(name=ADMIRAL["name"], bio=ADMIRAL["bio"], world=WORLD, lang_name=LANG_NAMES.get(lang, lang),
                                       captain=CAPTAIN_WORD.get(lang, "Captain"), war=self.war.brief(detail=False), allies=self._allies_line(),
                                       campaign="\n".join(f"- {c}" for c in self.campaign[-12:]) or "- (the war has just begun)",
                                       state=json.dumps(_brief(state), ensure_ascii=False, separators=(",", ":"))), ('allies', 'war', 'campaign', 'state'))
        msgs = [{"role": "system", "content": prompt}] + self.admiral_history[-10:] + [
            {"role": "user", "content": current_context + f"\n\n[The Aquila on the fleet net]: {message}"}]
        lines: list[str] = []

        async def on_call(call: ToolCall) -> None:
            a = call.arguments() or {}
            if call.name == "transmit" and len((a.get("text") or "").strip()) >= 4:
                lines.append(a["text"].strip())
                await self.say("admiral", a["text"].strip(), lang, "measured")
            elif call.name == "grant" and not self.granted:
                self.granted = True
                kind = a.get("kind", "resupply")
                beat = {"type": kind, "delay_s": a.get("delay_s", 150), "granted": True}
                ships: list[dict[str, Any]] = []
                if kind == "reinforcements":
                    ships = (a.get("ships") or [{"class": "vigilant", "name": "ASN Resolute"}])[:2]
                    beat.update(ships=ships, bearing_deg=(state.get("heading_deg", 0) + 180) % 360, range_km=20)
                else:
                    beat.update(hull_pct=85, missiles=24, duration_s=150)
                res = await self.command("director_beat", {"beat": beat})
                self.note(f"Rourke granted {kind}: {res.get('detail', '')}")
                log.info("admiral grants %s -> %s", kind, res)
                if res.get("ok") and ships:
                    self._register_captains(_ids(res.get("detail", "")), ships)

        await models.chat(self.llm, "director", messages=msgs, tools=[TRANSMIT] if self.march is not None else [TRANSMIT, GRANT], tool_choice="auto", on_tool_call=on_call,
                          max_tokens=400, temperature=0.6)       # (with the March no help is conjured: Fleet's ships are the March's)
        self.admiral_history += [{"role": "user", "content": f"[The Aquila on the fleet net]: {message}"},
                                 {"role": "assistant", "content": " ".join(lines) or "(no answer)"}]
        for line in lines:
            self.note(f"Rourke to the Aquila: {line}")
        return lines


def _ids(detail: str) -> list[str]:
    return _re.findall(r"T-\d+", detail)


def _brief(state: dict[str, Any]) -> dict[str, Any]:
    """What the director and the admiral need of the live state (compact)."""
    keep = ("location", "janus_gate", "alert", "hull_pct", "shields", "weapons", "squadrons", "damage_control", "heading_deg",
            "speed_mps", "casualties", "captain")
    out = {k: state.get(k) for k in keep if k in state}
    out["contacts"] = [{k: c.get(k) for k in ("id", "name", "class", "status", "range_km", "bearing_deg", "hull_pct")}
                       for c in state.get("contacts", []) or []]
    out["recent_events"] = state.get("_events", [])[-8:]
    return out
