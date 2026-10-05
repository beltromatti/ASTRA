"""Offline tests of the marine net (astra_mind/marines.py) against a scripted model: no network, no cost, no voices.

    cd mind && .venv/bin/python -m unittest bench.marines_unit -v

What is checked is the plumbing the behaviour stands on: which game events are the net's (and which stay with the bridge), and that every event the game can tell is one the
table knows (the templates are read from the C++ source); that the picture and the commands the mind reads and sends are the ones the game writes and takes (the field names are
read from the C++ source too); that a burst of news makes one pulse after a short settle and not more than the budget allows, that the Captain's words never wait and answer first
and that a quiet fight is looked at once in a while; that the prompt carries the facts the people may know (the squads, the places' ids, what is known of the boarders and how old,
the bulkheads, the net's log with the bridge's lines) and none they may not, with the language in the user message so that the stable system prompt stays cacheable; that a voice
reaches the stage with the right speaker, priority and answer flag, that a squad's leader has a name and a voice of their own that follow the person when the leader changes, and
that a squad with no one able never speaks; that `order` reaches the game as `marine_order` and `bulkheads` as `lockdown` with the authority checked (the Major any squad, a
leader only his own), that a refused order comes back to the one who gave it for one correction, and that a model that fails or stalls on the Captain's words hands them to the
bridge; that the net is live while a boarding is on, a little after it, and not otherwise; and that memories are kept, loaded and forgotten with the campaign. Whether a line is
in character, in the Captain's language and short is for the real model, by ear (bench/marines_live.py)."""
from __future__ import annotations

import asyncio
import json
import re
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest import mock

from astra_mind import marines as mm
from astra_mind import models
from astra_mind.local_ship import LocalShip
from astra_mind.medbay import FREE_VOICES
from astra_mind.tts import GENDER, VOICES
from bench.flight_unit import Clock, ScriptedLLM

models.LEDGER.write_file = False

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "Source" / "ASTRA"

# the game's own words (AstraBoardEvents.cpp, AstraBoardSubsystem.cpp, AstraBoardSim.cpp), with the places and names the game would put in
PLACE = "deck 5 section C (Corridor 5-C starboard)"
DOCKED = (f"boarding: the Mandate raider Lethe has docked 2 assault craft on the hull at {PLACE}: about 20 boarders, going for Main Engineering; the section bulkheads are closing "
          "and the marines are being called to arms")
BREACH = f"boarding: the hull is cut open at {PLACE}: boarders are coming through"
CONTACT = f"boarding: contact: Sergeant Priya Castillo sees the boarders at {PLACE}"
DEAD = f"boarding: Private Tariq Hassan is dead at {PLACE}, killed by a Mandate rifleman"
DOWN = f"boarding: Sergeant Jonas Weber is down, wounded, at {PLACE}"
CUT = "boarding: the Mandate cut through the bulkhead at deck 5 section B (Corridor 5-B)"
RETREAT = "boarding: Mandate Squad Two is breaking off and falling back to the breach"
RESCUE = "boarding: the marines have reached the Captain and are covering him"
TALLY = "boarding: marines: 1 dead, 2 down; boarders: 7 dead or down, 11 still fighting"
CAPTAIN_DOWN = "boarding: the Captain is down"
LOST = "boarding: Main Engineering is lost: the reactor's containment is failing"
BEATEN = "boarding: the boarders are beaten: Main Engineering is secure and the deck is ours. marines: 2 dead, 3 wounded; boarders: 9 dead, 4 wounded, 3 got away"
TAKEOVER = "boarding: the boarders hold Main Engineering and are working on the reactor: its containment will fail in about half a minute. marines: 6 dead, 4 wounded"

# the boats' boardings (AstraBoardAssault.cpp): the Mandate's skiffs at the Aquila, the Aquila's Kestrels at another ship
LAUNCHED = ("boarding: the Mandate raider Charon has launched 2 assault craft at the Aquila (about 20 boarders): they will be at her hull in about 48 seconds, at deck 9 section E (EVA Airlock), "
            "deck 6 section C (EVA Airlock), going for Main Engineering; the section bulkheads are closing and the marines are being called to arms")
LATCHED = ("boarding: the Aquila's Kestrel 1 has latched to Hulk at deck 5 section A (Boarding Lock) and cut in: 12 marines are through, going for the commander's suite; "
           "she holds about 19 of her people at their posts")
CUT_IN = "boarding: Kestrel 2 has cut in at deck 5 section E (Boarding Lock): 12 marines are through"
SKIFF_LOST = "boarding: Skiff 2 has been destroyed (shot down by the point defence of the Aquila): its 10 boarders are lost with it"
KESTREL_LOST = "boarding: Kestrel 2 was destroyed (shot down by the point defence of Hulk) with 12 marines aboard"
TURNED_BACK = "boarding: Skiff 1 has turned back (the shield on her port face held (100%): the craft cannot dock through it)"
NOT_ONE = "boarding: not one boarder reached the ship: every boat was destroyed or turned back; the marines stand down"
OURS = ("boarding: Hulk is ours: the marines hold deck 1 section B (Archon's Suite) and her people have laid down their arms; her commander and the survivors of her crew are in custody. "
        "marines: 11 dead, 0 wounded; her crew: 8 dead, 0 wounded, 0 got away")
FAILED = "boarding: the boarding of Hulk has failed: every marine on her decks is down or out, and she holds. marines: 12 dead, 0 wounded; her crew: 4 dead, 2 wounded, 0 got away"
PULLED_OUT = "boarding: the marines have broken off and are back in their boats: Hulk still holds out. marines: 5 dead, 1 wounded; her crew: 3 dead, 0 wounded, 0 got away"
SENDING = "boarding: the Aquila is sending 2 Kestrels with 24 marines to board Hulk"
HOME = "boarding: Kestrel 2 is back in the boat bay: 12 marines aboard"
CAPTAIN_RIDES = "boarding: the Captain rides with the marines in Kestrel 1"
CAPTAIN_IN = "boarding: the Captain is aboard Hulk with the marines, in deck 5 section A (Boarding Lock): going for deck 1 section B (Archon's Suite)"
CAPTAIN_BACK = "boarding: the Captain is called back to the boat (the fight is over)"
CAPTAIN_OFF = "boarding: the Captain is off the other ship's decks (carried out): the marines fight on without him"
CAPTAIN_HOME = "boarding: the Captain is back aboard the Aquila: the boat bay on Deck 8"
CAPTAIN_BOAT = "boarding: the Captain was in the boat: it was destroyed (shot down by the point defence of Hulk)"

# the infantry orders' news (AstraBoardDrills.cpp: a squad's drill moves on; AstraBoardSim.cpp: a door a squad shut is cut, overridden, opened again)
DRILL_NEWS = {
    "stacked": ("boarding: Reaction 1 is stacked at deck 4 section C (Berthing Lobby), ready to go in", False, False),
    "charge": ("boarding: Reaction 1 is setting a charge on the bulkhead at deck 2 section G (Spine)", False, False),
    "charged": ("boarding: Reaction 1 charged the bulkhead at deck 2 section G (Spine)", False, False, "charge"),
    "sync": ("boarding: Reaction 2: all of sync 1000 are at their doors: in together", False, False),
    "going_in": ("boarding: Reaction 1 is going in at deck 4 section C (Berthing Lobby)", False, False),
    "cleared": ("boarding: Reaction 1 has cleared deck 4 section C (Berthing Lobby)", True, False),
    "swept": ("boarding: Reaction 1 has swept deck 4 section C: 4 rooms clear", True, True),
    "sprung": ("boarding: Reaction 2 has sprung the ambush at deck 7 section D (Starboard Passage) (found: they open fire)", True, True),
    "ambush_off": ("boarding: Reaction 2 gives up the ambush at deck 7 section D (Starboard Passage): nobody came; they hold it with their fire free", True, False),
    "no_way": ("boarding: Reaction 1 has no way to deck 4 section C (Berthing Lobby)", True, True),
    "sealed_behind": ("boarding: Reaction 1 closed the bulkhead at deck 7 section D (Starboard Passage) behind them", False, False),
    "cut": ("boarding: the Mandate overrode the bulkhead at deck 2 section G (Spine)", True, False),
}
OPENED_AGAIN = "boarding: the bulkhead at deck 2 section G (Spine) was opened again"

PICTURE: dict[str, Any] = {
    "elapsed_s": 74, "breach": PLACE, "breach_open": True, "objective": "deck 7 section B (Main Engineering)", "objective_id": "engineering",
    "squads": [
        {"name": "Reaction 1", "able": 6, "down": 0, "dead": 0, "doing": "advance", "under_orders": False, "in_contact": False, "leader": "Sergeant Priya Castillo",
         "leader_id": "npc412", "leader_rank": "Sergeant", "leader_gender": "f", "where": "deck 6 section C (Corridor 6-C)", "where_id": "corridor_6c"},
        {"name": "Reaction 2", "able": 5, "down": 1, "dead": 0, "doing": "hold", "under_orders": True, "in_contact": True, "leader": "Sergeant Jonas Weber",
         "leader_id": "npc87", "leader_rank": "Sergeant", "leader_gender": "m", "where": PLACE, "where_id": "corridor_5c_s", "note": "hold the Spine junction"},
        {"name": "Watch 1", "able": 0, "down": 2, "dead": 2, "doing": "hold", "under_orders": False, "in_contact": False, "leader": "Private Tariq Hassan",
         "leader_id": "npc19", "leader_rank": "Private", "leader_gender": "m", "where": "deck 5 section B (Corridor 5-B)", "where_id": "corridor_5b"},
        {"name": "Reserve 1", "able": 2, "down": 0, "dead": 0, "still_arming_or_waking": 3, "doing": "advance", "under_orders": False, "in_contact": False,
         "leader": "Private Ines Alvarado", "leader_id": "npc230", "leader_rank": "Private", "leader_gender": "f", "where": "deck 8 section C (Armory)", "where_id": "d8_armory_C1"},
    ],
    "hostiles_known": [{"where": PLACE, "where_id": "corridor_5c_s", "count": 6, "age_s": 12}, {"where": "deck 5 section B (Corridor 5-B)", "where_id": "corridor_5b", "count": 2, "age_s": 31}],
    "bulkheads": [{"id": "BLK-D5-12", "between": "deck 5 section C (Corridor 5-C starboard) | deck 5 section B (Corridor 5-B)", "sealed": True},
                  {"id": "BLK-D5-14", "between": "deck 5 section B (Corridor 5-B) | deck 5 section A (Spine)", "sealed": False}],
    "likely_approach": [{"id": "corridor_5c_s", "name": PLACE}, {"id": "corridor_5b", "name": "deck 5 section B (Corridor 5-B)"}, {"id": "d7_corridor_B1", "name": "deck 7 section B (Corridor 7-B)"}],
    "objective_entrances": [{"id": "d7_corridor_B1", "name": "deck 7 section B (Corridor 7-B)"}, {"id": "d7_stair_44p", "name": "deck 7 section C (Stairs 44p)"}],
    "default_ambush": {"between": "deck 5 section B (Corridor 5-B) | deck 5 section A (Spine)", "id_a": "corridor_5b", "id_b": "spine_5a"},
    "captain": {"where": "deck 1 section A (Bridge)", "where_id": "bridge", "down": False, "strength_pct": 100},
    "recent": ["38s: order to Reaction 2: hold at deck 5 section C (Corridor 5-C starboard)", "61s: Mandate Squad One is cutting the bulkhead"],
}
BOARDING: dict[str, Any] = {
    "active": True, "elapsed_s": 74, "source": "the Mandate raider Lethe", "breach": PLACE, "breach_open": True, "objective": "deck 7 section B (Main Engineering)",
    "hostiles": f"6 at {PLACE}; 2 at deck 5 section B (Corridor 5-B)", "marines": {"able": 13, "down": 3, "dead": 2}, "boarders_known_losses": {"down_or_dead": 7, "left_ship": 0},
    "bulkheads_sealed": 3, "captain": {"strength_pct": 100, "down": False}, "recent": ["61s: Mandate Squad One is cutting the bulkhead"],
}


# the marines attacking a ship (role: attacking): the picture the game writes then (the holders' default ambush is not in it: it is the other side's plan)
ATTACK_PICTURE: dict[str, Any] = {
    "elapsed_s": 52, "role": "attacking", "ship": "Hulk", "ship_class": "Kharon Mandate cruiser, Acheron class", "breach": "deck 5 section A (Boarding Lock)", "breach_open": True,
    "objective": "deck 1 section B (Archon's Suite)", "objective_id": "d1_quarters_B1",
    "squads": [
        {"name": "Boarding Alpha", "able": 6, "down": 0, "dead": 0, "doing": "advance", "under_orders": False, "in_contact": True, "leader": "Sergeant Keiko Tahir",
         "leader_id": "npc301", "leader_rank": "Sergeant", "leader_gender": "f", "where": "deck 4 section A (Stair Tower)", "where_id": "d4_stairs_A1"},
        {"name": "Boarding Bravo", "able": 5, "down": 1, "dead": 0, "doing": "hold", "under_orders": True, "in_contact": False, "leader": "Sergeant Jonas Vasilyev",
         "leader_id": "npc302", "leader_rank": "Sergeant", "leader_gender": "m", "where": "deck 1 section A (Spine)", "where_id": "d1_corridor_A1"},
    ],
    "hostiles_known": [{"where": "deck 1 section B (Spine)", "where_id": "d1_corridor_B1", "count": 4, "age_s": 9}],
    "bulkheads": [{"id": "door_0117", "between": "deck 1 section A (Spine) | deck 1 section B (Spine)", "sealed": True}],
    "likely_approach": [{"id": "d5_lock_A1", "name": "deck 5 section A (Boarding Lock)"}, {"id": "d1_corridor_B1", "name": "deck 1 section B (Spine)"}],
    "objective_entrances": [{"id": "d1_corridor_B1", "name": "deck 1 section B (Spine)"}],
    "recent": ["12s: Boarding Alpha: advance"],
}
ATTACK_BOARDING: dict[str, Any] = {
    "active": True, "direction": "out", "ship": "Hulk", "elapsed_s": 52, "source": "ASN Aquila", "breach": "deck 5 section A (Boarding Lock)", "breach_open": True,
    "objective": "deck 1 section B (Archon's Suite)", "hostiles": "no hostile contact on the internal sensors", "marines": {"able": 11, "down": 1, "dead": 0},
    "defenders_known_losses": {"down_or_dead": 3, "left_ship": 0}, "bulkheads_sealed": 1, "recent": ["12s: Boarding Alpha: advance"],
}


def ship_state(fight: bool = True, **over: Any) -> dict[str, Any]:
    """What the game's snapshot carries in a boarding: the crew's state, the bridge's `boarding` and the marines' `_marines` picture, and the Mandate's own view (which the
    net must never read)."""
    st = json.loads(json.dumps(LocalShip(stations=True, fight=True).snapshot()))
    st["captain"] = "on the bridge"
    st["casualties"] = "none"
    st["_mandate"] = {"your_ships": [{"id": "T-21", "secret_plan": "flank the Aquila at 04:12"}]}
    if fight:
        st["boarding"] = json.loads(json.dumps(BOARDING))
        st["_marines"] = json.loads(json.dumps(PICTURE))
    st.update(over)
    return st


class Bed:
    """A marine net with its stage, its game and its clock, all scripted."""

    def __init__(self, tmp: str) -> None:
        self.llm = ScriptedLLM()
        self.clock = Clock()
        self.lines: list[dict[str, Any]] = []
        self.commands: list[tuple[str, dict[str, Any], str]] = []
        self.results: dict[str, dict[str, Any]] = {}
        self.voices: dict[str, tuple[str, str]] = {}
        self.unanswered: list[list[str]] = []
        self.m = mm.MarineMinds(self.llm, self._say, self._execute, lang=lambda: "it", clock=self.clock,
                                register_voice=lambda k, n, v: self.voices.__setitem__(k, (n, v)), path=lambda: str(Path(tmp) / "marines.json"))
        self.m.on_unanswered = self._unanswered

    async def _say(self, key: str, text: str, lang: str, tone: str, *, urgent: bool = False, answer: bool = False, direct: bool = False) -> None:
        self.lines.append({"speaker": key, "text": text, "lang": lang, "tone": tone, "urgent": urgent, "answer": answer, "direct": direct})

    async def _execute(self, name: str, args: dict[str, Any], by: str) -> dict[str, Any]:
        self.commands.append((name, args, by))
        return dict(self.results.get(name) or {"ok": True, "detail": "done"})

    async def _unanswered(self, words: list[str]) -> None:
        self.unanswered.append(words)

    def at(self, dt: float) -> None:
        self.clock.t += dt

    async def settle(self, wait: float = 0.15) -> None:
        for _ in range(60):
            t = self.m._task
            if t is None or t.done():
                break
            await asyncio.sleep(wait / 6)
        await asyncio.sleep(0.02)

    def user(self, n: int = -1) -> str:
        return str(self.llm.requests[n]["messages"][-1]["content"])


# ------------------------------------------------------------------------------------------------ what the game tells and takes
class Classification(unittest.TestCase):
    def test_the_marines_own_news_is_the_nets_and_the_ships_is_the_bridges(self) -> None:
        for text, kind, take in ((DOCKED, "docked", False), (BREACH, "breach", False), (CONTACT, "contact", True), (DEAD, "dead", True), (DOWN, "down", True), (CUT, "cut", True),
                                 (RETREAT, "retreat", True), (RESCUE, "rescue", True), (CAPTAIN_DOWN, "captain_down", False), (LOST, "lost", False), (BEATEN, "outcome", True),
                                 (TAKEOVER, "takeover", False)):
            k = mm.classify(text)
            self.assertIsNotNone(k, text)
            self.assertEqual((k.name, k.take), (kind, take), text)

    def test_the_boats_boardings_are_known_too(self) -> None:
        # a fight begins for the net at the Mandate's launch, or at the first of the marines' boats to cut in; the boats' own news is the bridge's, except the marines lost in their boat
        for text, kind, take, wake, call in ((LAUNCHED, "docked", False, True, False), (LATCHED, "docked", False, True, False), (CUT_IN, "breach", False, True, False),
                                             (SKIFF_LOST, "boat_lost", False, True, False), (KESTREL_LOST, "boat_lost", True, True, True), (TURNED_BACK, "boat_back", False, True, False),
                                             (NOT_ONE, "outcome", True, True, True), (OURS, "outcome", True, True, True), (FAILED, "outcome", True, True, True),
                                             (PULLED_OUT, "outcome", True, True, True), (SENDING, "assault_log", False, False, False), (HOME, "home", False, False, False),
                                             (CAPTAIN_RIDES, "assault_log", False, False, False), (CAPTAIN_IN, "captain_in", False, True, False), (CAPTAIN_BACK, "assault_log", False, False, False),
                                             (CAPTAIN_OFF, "captain_off", False, True, False), (CAPTAIN_HOME, "assault_log", False, False, False), (CAPTAIN_BOAT, "assault_log", False, False, False)):
            k = mm.classify(text)
            self.assertIsNotNone(k, text)
            self.assertEqual((k.name, k.take, k.wake, k.call), (kind, take, wake, call), text)

    def test_the_infantry_orders_news_is_the_nets_own(self) -> None:
        # what changes the Captain's picture wakes the net (a room cleared, a place swept, an ambush sprung or given up, no way in); the steps between stay in the log
        for label, (text, wake, call, *name) in DRILL_NEWS.items():
            k = mm.classify(text)
            self.assertIsNotNone(k, text)
            self.assertEqual((k.name, k.take, k.wake, k.call), (name[0] if name else label, True, wake, call), text)
        k = mm.classify(OPENED_AGAIN)
        self.assertEqual((k.name, k.take, k.wake), ("sealed_behind", True, False))

    def test_what_must_be_called_aloud(self) -> None:
        for text in (CONTACT, DEAD, BEATEN):
            self.assertTrue(mm.classify(text).call, text)
        for text in (DOCKED, DOWN, CUT, RETREAT, CAPTAIN_DOWN, LOST, TAKEOVER):
            self.assertFalse(mm.classify(text).call, text)

    def test_the_tally_and_the_called_off_only_go_in_the_log(self) -> None:
        for text in (TALLY, "boarding: the boarding is called off (console)"):
            self.assertFalse(mm.classify(text).wake, text)
            self.assertFalse(mm.classify(text).take, text)

    def test_what_is_not_a_boarding_is_not_the_nets(self) -> None:
        for text in ("tactical: three missiles incoming", "flight: alpha squadron airborne, 8 Falcons on CAP", "damage report: hull breach at deck 6 section B",
                     "the Captain went into the Captain's quarters", ""):
            self.assertIsNone(mm.classify(text), text)

    def test_a_template_the_table_does_not_know_still_wakes_the_net_and_stays_with_the_bridge(self) -> None:
        k = mm.classify("boarding: the boarders have set charges on a bulkhead")
        self.assertEqual((k.name, k.take, k.wake), ("other", False, True))

    def test_the_net_off_takes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            m = Bed(tmp).m
            m.disabled = True
            self.assertFalse(m.on_event(CONTACT))
            self.assertFalse(m.takes(CONTACT))
            self.assertEqual(m._events, [])
            self.assertFalse(m.net_live(ship_state()))

    def test_on_event_says_what_the_server_does_with_it(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            m = Bed(tmp).m
            self.assertFalse(m.on_event(DOCKED))                           # the bridge reports the alarm; the net looks at it all the same
            self.assertTrue(m.on_event(CONTACT))                           # the net tells it: the crew's report turn does not
            self.assertFalse(m.on_event(TALLY))                            # log only
            self.assertEqual([e.kind for e in m._events], ["docked", "contact"])
            self.assertFalse(m.on_event("tactical: three missiles incoming"))


def _templates(path: Path) -> list[str]:
    """The texts the game tells with `Tell(...)` in a C++ file, as format strings (what is in `TEXT("...")` right after `Tell(`)."""
    src = path.read_text(encoding="utf-8")
    return re.findall(r'Tell\(\s*(?:FString::Printf\(\s*)?TEXT\("((?:[^"\\]|\\.)*)"\)', src)


def _filled(fmt: str) -> str:
    out = re.sub(r"%\.?\d*[sdf]", lambda m: {"s": "Sample", "d": "3", "f": "74"}[m.group(0)[-1]], fmt).replace("%%", "%")
    return out.replace('\\"', '"')


class GameContract(unittest.TestCase):
    """The mind and the game's C++ must agree: the events the game tells, the fields of the picture, the arguments of the commands (read from the source)."""

    def setUp(self) -> None:
        if not (SRC / "AstraBoardEvents.cpp").exists():
            self.skipTest("the game's source is not in this checkout")

    def test_every_event_the_game_tells_is_one_the_table_knows(self) -> None:
        texts = []
        for name in ("AstraBoardEvents.cpp", "AstraBoardSubsystem.cpp", "AstraBoardMind.cpp", "AstraBoardAssault.cpp", "AstraBoardRide.cpp"):
            texts += _templates(SRC / name)
        texts += re.findall(r'TEXT\("(the Mandate cut through the bulkhead[^"]*)"\)', (SRC / "AstraBoardSim.cpp").read_text(encoding="utf-8"))       # (told as `Tell(E.Text)`)
        self.assertGreaterEqual(len(texts), 14)                                  # (the regex did find them: a rename in the C++ must not make this test pass on nothing)
        for fmt in texts:
            text = "boarding: " + _filled(fmt)
            k = mm.classify(text)
            self.assertIsNotNone(k, text)
            self.assertNotEqual(k.name, "other", f"the game tells «{text}» and the marine net's table does not know it")

    def test_every_drill_news_the_game_tells_is_one_the_table_knows(self) -> None:
        drills = (SRC / "AstraBoardDrills.cpp").read_text(encoding="utf-8")
        sim = (SRC / "AstraBoardSim.cpp").read_text(encoding="utf-8")
        found = re.findall(r'Announce\(\w+, FString::Printf\(TEXT\("((?:[^"\\]|\\.)*)"\)', drills)                                  # a squad's drill moves on
        found += re.findall(r'Emit\(EEvent::(?:Sealed|Cut),[^;]*?TEXT\("((?:[^"\\]|\\.)*)"\)', drills)                            # a door shut behind a squad, a charge
        found += re.findall(r'TEXT\("(%s (?:cut through|overrode) the bulkhead at %s|the bulkhead at %s was opened again)"\)', sim)       # a shut door cut, overridden, opened again
        self.assertGreaterEqual(len(found), 12)
        for fmt in found:
            text = "boarding: " + _filled(fmt)
            text = text.replace("boarding: Sample overrode", "boarding: the Mandate overrode").replace("boarding: Sample cut through", "boarding: the Mandate cut through")
            k = mm.classify(text)
            self.assertIsNotNone(k, text)
            self.assertNotEqual(k.name, "other", f"the game tells «{text}» and the marine net's table does not know it")
            self.assertTrue(k.take, text)                                                # (a drill's news is the marines' own: the bridge's report turn does not say it)

    def test_the_boarding_snapshot_says_where_the_captain_is(self) -> None:
        # the keys the minds read to know whether the Captain is with the marines (VOCI-3: who hears him on the marine net)
        src = (SRC / "AstraBoardMind.cpp").read_text(encoding="utf-8")
        self.assertIn('SetBoolField(TEXT("captain_aboard"), bCaptainAboard)', src)
        self.assertIn('SetBoolField(TEXT("captain_with_marines"), bCaptainAboard || Ride != ERide::None)', src)

    def test_the_picture_is_what_the_game_writes(self) -> None:
        src = (SRC / "AstraBoardMind.cpp").read_text(encoding="utf-8")
        fields = set(re.findall(r'(?:SetStringField|SetNumberField|SetBoolField|SetArrayField|SetObjectField)\(TEXT\("([a-z_]+)"\)', src))
        read = {"elapsed_s", "breach", "breach_open", "objective", "objective_id", "squads", "name", "able", "down", "dead", "still_arming_or_waking", "doing", "under_orders", "in_contact",
                "leader", "leader_id", "leader_gender", "where", "where_id", "note", "hostiles_known", "count", "age_s", "bulkheads", "id", "between", "sealed", "likely_approach",
                "objective_entrances", "default_ambush", "id_a", "id_b", "captain", "strength_pct", "recent", "active", "marines", "boarders_known_losses", "down_or_dead",
                "left_ship", "hostiles", "armed", "role", "ship", "ship_class", "defenders_known_losses", "direction", "drill", "in_a_sync", "fire_held", "seal_behind", "objective_doors"}
        self.assertEqual(read - fields, set())
        for row in PICTURE["squads"]:                                              # the fixture has what the game writes, nothing it does not
            self.assertLessEqual(set(row), fields)
        self.assertEqual(set(PICTURE) - fields, set())
        self.assertEqual(set(BOARDING) - fields, {"source"} - fields)
        for row in ATTACK_PICTURE["squads"]:
            self.assertLessEqual(set(row), fields)
        self.assertEqual(set(ATTACK_PICTURE) - fields, set())
        self.assertEqual(set(ATTACK_BOARDING) - fields, {"source"} - fields)

    def test_the_ship_state_carries_the_picture_where_the_net_reads_it(self) -> None:
        src = (SRC / "AstraShipSubsystem.cpp").read_text(encoding="utf-8")
        self.assertIn('SetObjectField(TEXT("_marines"), Board->MarinesPicture())', src)
        self.assertIn('SetObjectField(TEXT("boarding"), Board->Snapshot())', src)

    def test_the_commands_take_what_the_net_sends(self) -> None:
        src = (SRC / "AstraBoardMind.cpp").read_text(encoding="utf-8")
        for arg in ("squad", "task", "place", "note", "doors", "sealed", "scope"):
            self.assertIn(f'TEXT("{arg}")', src, arg)
        for task in mm.TASKS:
            self.assertIn(f'TEXT("{task}")', src, task)
        self.assertIn('Name == TEXT("marine_order")', src)
        self.assertIn('Name == TEXT("lockdown")', src)
        self.assertIn('Name == TEXT("marine_order")', (SRC / "AstraShipSubsystem.cpp").read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------------------ the people
class People(unittest.IsolatedAsyncioTestCase):
    def test_the_major_is_the_lores(self) -> None:
        r = mm.REYES
        self.assertEqual((r.title, r.key), ("Major Tomás Reyes", "reyes"))                # docs/BIBBIA.md: Security & Marines
        self.assertIn(r.voice, VOICES)
        self.assertEqual(GENDER[r.voice], r.gender)
        self.assertTrue(r.bio and r.post and r.radio)

    def test_the_roster_has_no_other_reyes(self) -> None:
        src = SRC / "AstraCrewRoster.cpp"
        if not src.exists():
            self.skipTest("the roster's source is not in this checkout")
        m = re.search(r"LastNames\[\] = \{(.*?)\};", src.read_text(encoding="utf-8"), re.S)
        self.assertNotIn("Reyes", set(re.findall(r'TEXT\("([^"]+)"\)', m.group(1))))        # (crew_locate must find one Reyes)

    def test_a_squad_is_named_as_the_captain_says_it(self) -> None:
        self.assertEqual(mm.spoken("Reaction 2", "it"), "Reaction due")
        self.assertEqual(mm.spoken("Watch 3", "en"), "Watch three")
        self.assertEqual(mm.spoken("Reserve 1", "fr"), "Reserve un")
        self.assertEqual(mm.spoken("Reaction 2", "de"), "Reaction zwei")
        self.assertEqual(mm.spoken("Reaction 2", "ja"), "Reaction 2")                     # (a language with no table: the digit as it is)
        self.assertEqual(mm.spoken("Watch 12", "it"), "Watch 12")                         # (two digits: left alone)

    def test_a_squads_voice_follows_its_name(self) -> None:
        self.assertEqual(mm.squad_key("Reaction 1"), "marine_reaction_1")
        self.assertEqual(mm.squad_key("Watch 12"), "marine_watch_12")
        self.assertEqual(mm.squad_key(""), "marine_squad")

    def test_a_leaders_voice_is_stable_a_free_one_and_never_the_majors(self) -> None:
        for name, g in (("Sergeant Priya Castillo", "f"), ("Sergeant Jonas Weber", "m"), ("Private Tariq Hassan", "m"), ("Captain Amira Nasser", "f")):
            v = mm.leader_voice(name, g)
            self.assertEqual(v, mm.leader_voice(name, g))
            self.assertIn(v, FREE_VOICES[g])
            self.assertEqual(GENDER[v], g)
            self.assertNotEqual(v, mm.REYES.voice)
        for _ in range(3):
            self.assertNotEqual(mm.leader_voice("x", "m"), "")

    def test_the_major_is_registered_for_the_stage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bed = Bed(tmp)
            self.assertEqual(bed.voices["reyes"], ("Reyes (Major Tomás Reyes)", "michael"))


# ------------------------------------------------------------------------------------------------ what the people read
class Prompts(unittest.IsolatedAsyncioTestCase):
    def test_the_system_prompt_is_stable_and_complete(self) -> None:
        a, b = mm.system_prompt(), mm.system_prompt()
        self.assertEqual(a, b)
        for needle in ("Major Tomás Reyes", "marine net", "stay_quiet", "order", "bulkheads", "remember", "default ambush", "ONLY with tool calls", "Main Engineering", "marine who falls"):
            self.assertIn(needle, a)
        for task in mm.TASKS:
            self.assertIn(task, a)
        self.assertNotIn("Italian", a)                                                  # the language rides with the user message: the cache survives a change of language
        self.assertNotIn("{world}", a)

    def test_the_tools_are_what_the_prompt_says(self) -> None:
        names = [t["function"]["name"] for t in mm.TOOLS]
        self.assertEqual(names, ["say", "order", "bulkheads", "remember", "stay_quiet"])
        self.assertNotIn("stay_quiet", [t["function"]["name"] for t in mm.TOOLS_MUST])
        order = next(t for t in mm.TOOLS if t["function"]["name"] == "order")["function"]["parameters"]
        self.assertEqual(order["properties"]["task"]["enum"], list(mm.TASKS))
        self.assertEqual(order["required"], ["by", "squad", "task"])

    def test_the_user_message_carries_what_the_people_may_know(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bed = Bed(tmp)
            st = ship_state(captain="in a corridor on deck 6, with a rifle")
            bed.m.feed(st)
            bed.m.heard("the bridge: Commander Elena Serra (Executive Officer)", "Marines, boarders on deck five.")
            bed.m.on_event(CONTACT)
            user = bed.m._compose(st, bed.m._events, [], ["news on the net (below)"], "it")
            for needle in ("the bridge: Commander Elena Serra (Executive Officer): Marines, boarders on deck five.", "Sergeant Priya Castillo sees the boarders", "74 s since the alarm",
                           "Main Engineering) [id engineering]", "marine_reaction_1 — Reaction 1 (said \"Reaction uno\"); leader Sergeant Priya Castillo: 6 able", "marine_reaction_2 — Reaction 2 (said \"Reaction due\")", "doing: advance",
                           "under orders; in contact", "note: hold the Spine junction", "3 still arming or waking", "marine_watch_1 — Watch 1 (said \"Watch uno\"); leader Private Tariq Hassan: 0 able, 2 down, 2 dead",
                           "6 at deck 5 section C (Corridor 5-C starboard) [id corridor_5c_s], 12 s ago", "[id d7_corridor_B1]", "the default ambush", "[ids corridor_5b, spine_5a]",
                           "BLK-D5-12 between", "SEALED", "BLK-D5-14", "the count: marines 13 able, 3 down, 2 dead", "where the Captain is: in a corridor on deck 6", "Italian", "Capitano",
                           "boarding: contact"):
                self.assertIn(needle, user)
            self.assertNotIn("secret_plan", user)                                        # the Mandate's own view is nobody's here (docs/ARCHITETTURA.md §1bis, point 2)
            self.assertNotIn("flank the Aquila", user)
            self.assertNotIn("_mandate", user)

    def test_the_prompt_teaches_the_assault_and_the_withdrawal(self) -> None:
        s = mm.system_prompt()
        for needle in ("WHEN THE MARINES BOARD A SHIP", "role: attacking", "`withdraw`", "another ship's are not yours to seal", "bleeds out in about two minutes", "The Captain may have come with the marines"):
            self.assertIn(needle, s)
        self.assertIn("withdraw", mm.TASKS)
        bulk = next(t for t in mm.TOOLS if t["function"]["name"] == "bulkheads")["function"]["description"]
        self.assertIn("only while the marines DEFEND", bulk)

    def test_the_prompt_teaches_the_infantry_orders_with_the_games_numbers(self) -> None:
        s = mm.system_prompt()
        for needle in ("THE INFANTRY ORDERS", "take:", "breach:", "sweep:", "ambush:", "escort_captain", "seal_behind", "68 times in 96", "51 and 56 times in 72", "82 times", "on the column", "66", "What does not work: spreading a squad thin"):
            self.assertIn(needle, s)
        for task in ("sweep", "breach", "take", "ambush", "escort_captain"):
            self.assertIn(task, mm.TASKS)
        order = next(t for t in mm.TOOLS if t["function"]["name"] == "order")["function"]
        props = order["parameters"]["properties"]
        for k in ("fire", "seal_behind", "cover", "sync", "inside"):
            self.assertIn(k, props)
        self.assertEqual(props["fire"]["enum"], ["held", "free"])
        self.assertEqual(order["parameters"]["required"], ["by", "squad", "task"])
        self.assertIn("deck 7 section D", props["place"]["description"])

    def test_the_board_shows_what_each_squads_drill_is_doing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bed = Bed(tmp)
            st = ship_state()
            st["_marines"]["squads"][0].update({"doing": "take", "under_orders": True, "drill": "taking deck 4 section C (Berthing Lobby): stacked at the door (waiting for the squads of its sync)", "in_a_sync": True})
            st["_marines"]["squads"][1].update({"doing": "ambush", "drill": "hidden at deck 7 section D (Starboard Passage), fire held, 31 s", "fire_held": True})
            st["_marines"]["objective_doors"] = [{"id": "d7_door_eng_1", "between": "deck 7 section F (Main Engineering lobby) | deck 7 section F (Main Engineering)", "sealed": True}]
            bed.m.feed(st)
            board = bed.m._board(st, "en")
            for needle in ("doing: take (under orders; in a sync: its doors and another squad's, in together); drill: taking deck 4 section C (Berthing Lobby): stacked at the door",
                           "drill: hidden at deck 7 section D (Starboard Passage), fire held, 31 s", "the objective's own doors (what a breach names): d7_door_eng_1 between", "SEALED"):
                self.assertIn(needle, board)

    def test_the_marines_attacking_read_the_assault_not_the_defence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bed = Bed(tmp)
            st = ship_state(fight=False)
            st["boarding"] = json.loads(json.dumps(ATTACK_BOARDING))
            st["_marines"] = json.loads(json.dumps(ATTACK_PICTURE))
            bed.m.feed(st)
            board = bed.m._board(st, "en")
            for needle in ("the assault: your marines are boarding Hulk (Kharon Mandate cruiser, Acheron class)", "52 s since the first boat cut in", "the objective is deck 1 section B (Archon's Suite)",
                           "[id d1_quarters_B1]", "of the ship's people 3 known down or dead", "the ship's people as they are known", "4 at deck 1 section B (Spine) [id d1_corridor_B1], 9 s ago",
                           "your likely way from the hatch to the objective", "the ways into the objective", "the pressure bulkheads near your hatch", "marine_boarding_alpha — Boarding Alpha",
                           "leader Sergeant Keiko Tahir: 6 able"):
                self.assertIn(needle, board)
            for hidden in ("default ambush", "the boarders as they are known", "Main Engineering", "boarders' likely way", "the alarm"):
                self.assertNotIn(hidden, board)
            self.assertEqual(bed.m.present(), ["reyes", "marine_boarding_alpha", "marine_boarding_bravo"])

    def test_the_marines_defending_still_read_the_defence(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bed = Bed(tmp)
            bed.m.feed(ship_state())
            board = bed.m._board(ship_state(), "en")
            self.assertIn("the boarders as they are known", board)
            self.assertIn("the default ambush", board)
            self.assertNotIn("the assault: your marines", board)

    def test_the_squad_in_the_captains_room_is_said_so(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bed = Bed(tmp)
            st = ship_state()
            st["_marines"]["captain"] = {"where": PLACE, "where_id": "corridor_5c_s", "down": False, "strength_pct": 80}
            bed.m.feed(st)
            board = bed.m._board(st)
            captain = next(r for r in board.splitlines() if "the Captain in the fight" in r)
            self.assertIn("in the same room as Sergeant Jonas Weber", captain)
            self.assertNotIn("Priya Castillo", captain)                                   # (Reaction 1 is elsewhere)
            self.assertIn("80% strength", captain)

    def test_how_the_captain_stands_and_who_has_him_in_sight_is_on_the_board(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bed = Bed(tmp)
            st = ship_state()
            st["_marines"]["captain"] = {"where": PLACE, "where_id": "corridor_5c_s", "down": False, "strength_pct": 100, "posture": "crouched", "leaning": "left", "seen_by": 2, "nearest_seer_m": 14}
            bed.m.feed(st)
            captain = next(r for r in bed.m._board(st).splitlines() if "the Captain in the fight" in r)
            self.assertIn("crouched, leaning left", captain)
            self.assertIn("2 of the enemy have him in sight now, the nearest at 14 m", captain)
            st["_marines"]["captain"] = {"where": PLACE, "where_id": "corridor_5c_s", "down": False, "strength_pct": 100, "posture": "standing", "seen_by": 0}
            bed.m.feed(st)
            captain = next(r for r in bed.m._board(st).splitlines() if "the Captain in the fight" in r)
            self.assertIn("standing", captain)
            self.assertNotIn("in sight", captain)                                          # (nobody has him in sight: nothing to say of it)

    def test_what_is_the_bridges_news_says_so(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bed = Bed(tmp)
            bed.m.on_event(DOCKED)
            bed.m.on_event(DEAD)
            user = bed.m._compose(ship_state(), bed.m._events, [], ["news on the net (below)"], "it")
            docked = next(r for r in user.splitlines() if "has docked" in r)
            dead = next(r for r in user.splitlines() if "is dead at" in r)
            self.assertIn("the bridge's news", docked)                                  # (not the net's to tell: it speaks only if its marines or its drill are touched)
            self.assertNotIn("the bridge's news", dead)

    def test_the_captains_words_and_the_language_are_in_the_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bed = Bed(tmp)
            bed.m.feed(ship_state())
            msg = mm.Message(bed.clock.t - 2, "Reyes, tieni il corridoio fuori dall'ingegneria", "it")
            user = bed.m._compose(ship_state(), [], [msg], ["the Captain is speaking on the net (below): answer him first"], "it")
            self.assertIn("THE CAPTAIN SAYS (over the net)", user)
            self.assertIn("Reyes, tieni il corridoio", user)
            self.assertNotIn("WHAT THE CAPTAIN HAS SAID", user)                          # (his words of this very look are not also "said before")
            en = bed.m._compose(ship_state(), [], [], ["x"], "en")
            self.assertIn("English", en)
            self.assertIn("Reaction One: contact", en)                                  # the register in the Captain's language
            self.assertIn("who can speak (the `speaker` key): reyes (Reyes)", en.replace("Who can speak", "who can speak"))

    async def test_what_the_captain_ordered_stands_in_the_next_look(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bed = Bed(tmp)
            bed.m.feed(ship_state())
            bed.m.captain_to_net("Reyes, hold the corridor outside Engineering", "en")
            bed.m._inbox.clear()
            user = bed.m._compose(ship_state(), [], [], ["x"], "en")
            self.assertIn("WHAT THE CAPTAIN HAS SAID ON THE NET IN THIS FIGHT", user)
            self.assertIn("hold the corridor outside Engineering", user)

    def test_a_squad_with_no_one_able_has_no_voice(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bed = Bed(tmp)
            bed.m.feed(ship_state())
            self.assertEqual(bed.m.present(), ["reyes", "marine_reaction_1", "marine_reaction_2", "marine_reserve_1"])         # (Watch 1 has nobody on its feet)
            self.assertIn("marine_watch_1", bed.m._board(ship_state()))                    # (the board still shows what became of it)

    def test_no_board_is_said_so(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bed = Bed(tmp)
            self.assertIn("the board is dark", bed.m._board({}))

    def test_what_a_person_remembers_comes_back_to_them(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bed = Bed(tmp)
            bed.m.feed(ship_state())
            bed.m._remember({"speaker": "reyes", "kind": "loss", "memory": "Reyes lost Hassan at the Spine junction and the Captain said his name afterwards."})
            bed.m._remember({"speaker": "Reaction 1", "kind": "order", "memory": "Castillo was told to hold at the armory while her people died on deck five; she has not forgotten."})
            user = bed.m._compose(ship_state(), [], [], ["x"], "en")
            self.assertIn("WHAT THEY REMEMBER", user)
            self.assertIn("Reyes lost Hassan", user)
            self.assertIn("Castillo was told to hold", user)
            self.assertNotIn("WHAT THEY REMEMBER", Bed(tmp + "/other").m._compose(ship_state(), [], [], ["x"], "en"))


# ------------------------------------------------------------------------------------------------ the fight's life
class Assault(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.bed = Bed(self.tmp.name)
        self.m = self.bed.m

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_the_net_begins_at_the_launch_or_at_the_first_cut_in(self) -> None:
        self.m.on_event(LAUNCHED)
        self.assertTrue(self.m.active)
        self.m.reset()
        self.assertFalse(self.m.active)
        self.m.on_event(SENDING)                                                     # (the order alone: the marines are not in a fight yet)
        self.assertFalse(self.m.active)
        self.m.on_event(LATCHED)
        self.assertTrue(self.m.active)

    async def test_a_withdrawal_goes_to_the_game_as_the_marines_order(self) -> None:
        st = ship_state(fight=False)
        st["boarding"] = json.loads(json.dumps(ATTACK_BOARDING))
        st["_marines"] = json.loads(json.dumps(ATTACK_PICTURE))
        self.m.feed(st)
        self.bed.llm.say(("order", {"by": "reyes", "squad": "Boarding Bravo", "task": "withdraw", "reason": "one down, the objective is two corridors away"}),
                         ("say", {"speaker": "reyes", "text": "Bravo, out through the lock.", "tone": "focused"}))
        self.m.captain_to_net("Reyes, tira fuori Bravo", "it")
        await self.bed.settle()
        orders = [c for c in self.bed.commands if c[0] == "marine_order"]
        self.assertEqual(orders[0][1]["task"], "withdraw")
        self.assertEqual(orders[0][1]["squad"], "Boarding Bravo")


class Lifecycle(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.bed = Bed(self.tmp.name)
        self.m = self.bed.m

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def test_the_net_is_live_while_a_boarding_is_on_and_a_little_after(self) -> None:
        self.assertFalse(self.m.net_live(ship_state(fight=False)))
        self.m.on_event(DOCKED)
        self.assertTrue(self.m.net_live({}))                                        # the alarm: the first state is not in yet
        self.m.feed(ship_state())
        self.assertTrue(self.m.net_live(ship_state()))
        self.bed.at(300)
        self.assertTrue(self.m.net_live(ship_state()))
        self.m.feed(ship_state(fight=False))                                        # the game stops showing the fight: it is over
        self.assertFalse(self.m.active)
        self.assertTrue(self.m.net_live(ship_state(fight=False)))                   # the count, a thank-you
        self.bed.at(mm.AFTERMATH_S - 1)
        self.assertTrue(self.m.net_live(ship_state(fight=False)))
        self.bed.at(2)
        self.assertFalse(self.m.net_live(ship_state(fight=False)))
        self.assertTrue(self.m.net_live(ship_state(fight=False), heard_ago=10.0))   # somebody on the net called the Captain a moment ago
        self.assertFalse(self.m.net_live(ship_state(fight=False), heard_ago=mm.EXCHANGE_S + 1))

    async def test_a_fight_that_was_on_when_the_mind_joined_is_joined(self) -> None:
        self.assertFalse(self.m.active)
        self.m.feed(ship_state())
        self.assertTrue(self.m.active)

    async def test_the_end_of_the_fight_is_seen_once_the_game_has_shown_it(self) -> None:
        self.m.on_event(DOCKED)
        self.m.feed(ship_state(fight=False))                                        # (a state from before the game's first one with the fight in it)
        self.assertTrue(self.m.active)
        self.m.feed(ship_state())
        self.m.feed(ship_state(fight=False))
        self.assertFalse(self.m.active)

    async def test_a_new_boarding_starts_with_a_clean_net(self) -> None:
        self.m.on_event(DOCKED)
        self.m.feed(ship_state())
        self.m.heard("the bridge: Lieutenant Commander Sara Voss (Tactical)", "They will go for the reactor.")
        self.m.captain_to_net("hold the corridor", "en")
        self.m.feed(ship_state(fight=False))
        self.assertIn("They will go for the reactor", self.m._recall())
        self.m.on_event(DOCKED)                                                     # the next one
        self.assertTrue(self.m.active)
        self.assertEqual(list(self.m.log), [])
        self.assertEqual(list(self.m.captain_words), [])
        self.assertEqual(self.m.squads, {})

    async def test_the_bridge_is_heard_only_in_a_fight(self) -> None:
        self.m.heard("the bridge: x", "before the alarm")
        self.assertEqual(list(self.m.log), [])
        self.m.on_event(DOCKED)
        self.m.heard("the bridge: x", "after it")
        self.assertEqual([t for _, _, t in self.m.log], ["after it"])

    async def test_reset_empties_the_net(self) -> None:
        self.m.on_event(DOCKED)
        self.m.feed(ship_state())
        self.m.reset()
        self.assertFalse(self.m.active)
        self.assertEqual((self.m._events, self.m.squads, list(self.m.log)), ([], {}, []))

    async def test_the_voice_stage_learns_each_leader_and_the_new_one_when_the_leader_falls(self) -> None:
        self.m.feed(ship_state())
        name, voice = self.bed.voices["marine_reaction_1"]
        self.assertEqual(name, "Sergeant Priya Castillo (Reaction 1)")
        self.assertEqual(voice, mm.leader_voice("Sergeant Priya Castillo", "f"))
        self.assertNotEqual(voice, mm.REYES.voice)
        st = ship_state()
        st["_marines"]["squads"][0].update(leader="Private Omar Haddad", leader_id="npc301", leader_gender="m", leader_rank="Private")
        self.m.feed(st)
        self.assertEqual(self.bed.voices["marine_reaction_1"], ("Private Omar Haddad (Reaction 1)", mm.leader_voice("Private Omar Haddad", "m")))
        self.assertEqual(self.m.radio("marine_reaction_1"), "Reaction 1 (Private Omar Haddad)")
        self.assertEqual(self.m.radio("reyes"), "Reyes")


# ------------------------------------------------------------------------------------------------ the pulses
class Pulses(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.bed = Bed(self.tmp.name)
        self.m = self.bed.m
        self.st = ship_state()
        self.quiet = ("stay_quiet", {"reason": "the drill has it"})

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def news(self, *texts: str, wait_s: float = mm.SETTLE_S + 0.5) -> None:
        for t in texts:
            self.m.on_event(t)
        self.m.feed(self.st)
        self.bed.at(wait_s)
        self.m.feed(self.st)
        await self.bed.settle()

    async def test_the_alarm_is_looked_at_once_it_has_settled(self) -> None:
        self.bed.llm.say(("say", {"speaker": "reyes", "text": "Reaction in venticinque secondi, Capitano.", "tone": "focused"}))
        self.m.on_event(DOCKED)
        self.m.feed(self.st)
        await self.bed.settle()
        self.assertEqual(self.bed.llm.requests, [])                                   # (a burst of news is read together: not yet)
        self.bed.at(mm.SETTLE_S + 0.5)
        self.m.feed(self.st)
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 1)
        self.assertEqual([(l["speaker"], l["lang"], l["answer"]) for l in self.bed.lines], [("reyes", "it", False)])
        self.assertEqual(self.bed.llm.requests[0]["max_tokens"], models.role("marines").max_tokens)

    async def test_a_burst_of_news_is_one_pulse(self) -> None:
        self.bed.llm.say(("say", {"speaker": "marine_reaction_2", "text": "Contatto, sei ostili. Teniamo.", "tone": "tense", "urgent": True}))
        self.m.feed(self.st)
        self.m.on_event(CONTACT)
        self.bed.at(1.0)
        self.m.on_event(DEAD)
        self.bed.at(1.0)
        self.m.on_event(DOWN)
        self.m.feed(self.st)
        await self.bed.settle()
        self.assertEqual(self.bed.llm.requests, [])
        self.bed.at(mm.SETTLE_S + 0.2)
        self.m.feed(self.st)
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 1)
        user = self.bed.user()
        for text in (CONTACT, DEAD, DOWN):
            self.assertIn(text, user)
        self.assertTrue(self.bed.lines[0]["urgent"])

    async def test_a_burst_that_never_settles_is_read_after_the_longest_wait(self) -> None:
        self.bed.llm.say(self.quiet)
        self.m.feed(self.st)
        for _ in range(4):
            self.m.on_event(DOWN)
            self.bed.at(mm.SETTLE_S - 0.5)
            self.m.feed(self.st)
        await self.bed.settle()
        self.assertGreaterEqual(len(self.bed.llm.requests), 1)

    async def test_news_waits_for_the_gap_and_the_budget_stretches_it(self) -> None:
        self.bed.llm.say(self.quiet)
        await self.news(CONTACT)
        self.assertEqual(len(self.bed.llm.requests), 1)
        self.m.on_event(DOWN)
        self.bed.at(mm.SETTLE_S + 0.5)
        self.m.feed(self.st)
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 1)                               # (the gap: not yet)
        self.bed.at(mm.MIN_GAP_S)
        self.m.feed(self.st)
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 2)
        self.m._spent.append((self.bed.clock(), mm.BUDGET_USD * 2))                   # the net has been talking a lot: the gap doubles
        self.m.on_event(DOWN)
        self.bed.at(mm.MIN_GAP_S + 0.5)
        self.m.feed(self.st)
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 2)
        self.bed.at(mm.MIN_GAP_S)
        self.m.feed(self.st)
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 3)

    async def test_the_captain_never_waits_and_is_answered_first(self) -> None:
        self.bed.llm.say(self.quiet)
        await self.news(CONTACT)
        self.bed.llm.replies = [[("say", {"speaker": "reyes", "text": "Tengo il corridoio, Capitano.", "tone": "calm"})]]
        self.m.captain_to_net("Reyes, tieni il corridoio", "it")                      # (inside the gap: his words do not wait for it)
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 2)
        self.assertIn("Reyes, tieni il corridoio", self.bed.user())
        self.assertEqual((self.bed.lines[-1]["speaker"], self.bed.lines[-1]["answer"]), ("reyes", True))

    async def test_the_captains_language_is_the_messages_not_the_servers(self) -> None:
        self.bed.llm.say(("say", {"speaker": "reyes", "text": "Aye, Captain.", "tone": "calm"}))
        self.m.feed(self.st)
        self.m.captain_to_net("Major, report.", "en")
        await self.bed.settle()
        self.assertEqual(self.bed.lines[0]["lang"], "en")
        self.assertIn("English", self.bed.user())

    async def test_a_quiet_fight_is_looked_at_once_in_a_while(self) -> None:
        self.bed.llm.say(self.quiet)
        self.m.on_event(DOCKED)
        self.m.feed(self.st)
        self.bed.at(mm.SETTLE_S + 0.5)
        self.m.feed(self.st)
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 1)
        self.bed.at(mm.WATCH_S - 5)
        self.m.feed(self.st)
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 1)                               # (nothing new, not long enough)
        self.bed.at(6)
        self.m.feed(self.st)
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 2)
        self.assertIn("no news for", self.bed.user())
        self.assertEqual(self.m.stats["watch"], 1)
        self.assertIn("stayed quiet: the drill has it", self.m._recall())
        self.bed.at(mm.WATCH_S - 5)
        self.m.feed(self.st)
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 2)                               # (and not again at once)

    async def test_no_fight_no_look(self) -> None:
        self.bed.llm.say(self.quiet)
        quiet = ship_state(fight=False)
        for _ in range(5):
            self.bed.at(100)
            self.m.feed(quiet)
            await self.bed.settle()
        self.assertEqual(self.bed.llm.requests, [])

    async def test_the_debrief_reads_the_last_board_after_the_fight(self) -> None:
        self.bed.llm.say(("say", {"speaker": "reyes", "text": "Il ponte è nostro, Capitano. Due morti.", "tone": "grim"}))
        self.m.on_event(DOCKED)
        self.m.feed(self.st)
        self.m.on_event(BEATEN)
        self.m.feed(ship_state(fight=False))                                         # (the game has already stopped showing the fight when the news is read)
        self.bed.at(mm.SETTLE_S + 0.5)
        self.m.feed(ship_state(fight=False))
        await self.bed.settle()
        user = self.bed.user()
        self.assertIn("THE FIGHT IS OVER", user)
        self.assertIn("marine_reaction_1", user)                                      # (the last picture: who was where)
        self.assertIn(BEATEN, user)
        self.assertEqual(self.bed.lines[0]["speaker"], "reyes")

    async def test_what_must_be_called_leaves_no_way_to_stay_quiet(self) -> None:
        self.bed.llm.say(("say", {"speaker": "marine_reaction_2", "text": "Contatto.", "tone": "tense"}))
        await self.news(CONTACT)
        tools = {t["function"]["name"] for t in self.bed.llm.requests[-1]["tools"]}
        self.assertEqual(tools, {"say", "order", "bulkheads", "remember"})
        self.bed.at(mm.MIN_GAP_S + 1)
        await self.news(DOWN)
        tools = {t["function"]["name"] for t in self.bed.llm.requests[-1]["tools"]}
        self.assertIn("stay_quiet", tools)

    async def test_the_captain_speaking_cuts_a_pulse_on_news_and_the_news_is_read_again(self) -> None:
        self.bed.llm.delay = 5.0
        self.bed.llm.say(self.quiet)
        self.m.on_event(CONTACT)
        self.m.feed(self.st)
        self.bed.at(mm.SETTLE_S + 0.5)
        self.m.feed(self.st)
        await asyncio.sleep(0.05)
        self.assertEqual(self.m.preempt(), 1)
        await asyncio.sleep(0.05)
        self.assertEqual([e.kind for e in self.m._events], ["contact"])               # (what it had not said is read again)
        self.bed.llm.delay = 0.0
        self.bed.at(mm.MIN_GAP_S + 1)
        self.m.feed(self.st)
        await self.bed.settle()
        self.assertIn(CONTACT, self.bed.user())

    async def test_a_pulse_that_answers_the_captain_is_not_cut(self) -> None:
        self.bed.llm.delay = 0.3
        self.bed.llm.say(("say", {"speaker": "reyes", "text": "Qui Reyes.", "tone": "calm"}))
        self.m.feed(self.st)
        self.m.captain_to_net("Reyes?", "it")
        await asyncio.sleep(0.05)
        self.assertEqual(self.m.preempt(), 0)
        await self.bed.settle(1.0)
        self.assertEqual([l["text"] for l in self.bed.lines], ["Qui Reyes."])

    async def test_a_model_that_fails_hands_the_captains_words_to_the_bridge(self) -> None:
        self.bed.llm.error = "provider down"
        self.m.feed(self.st)
        self.m.captain_to_net("Reyes, rapporto", "it")
        await self.bed.settle()
        self.assertEqual(self.bed.unanswered, [["Reyes, rapporto"]])
        self.assertEqual(self.bed.lines, [])

    async def test_a_model_that_stalls_says_nothing_and_hands_the_captains_words_over(self) -> None:
        self.bed.llm.delay = 5.0
        self.m.feed(self.st)
        with mock.patch.object(mm, "PULSE_TIMEOUT_S", 0.1):
            self.m.captain_to_net("Reyes, rapporto", "it")
            await self.bed.settle(1.0)
        self.assertEqual(self.bed.unanswered, [["Reyes, rapporto"]])
        self.assertEqual(self.m.pulses[-1]["error"], "timeout")

    async def test_a_model_that_fails_on_news_loses_nothing_but_the_pulse(self) -> None:
        self.bed.llm.error = "provider down"
        await self.news(CONTACT)
        self.assertEqual(self.bed.unanswered, [])
        self.assertEqual(self.m.stats["pulses"], 1)
        self.assertTrue(self.m.pulses[-1]["error"])

    async def test_what_the_model_wrote_in_prose_is_asked_for_again_in_the_tools(self) -> None:
        self.bed.llm.content = "Reaction Due tiene il corridoio."
        self.bed.llm.replies = [[], [("say", {"speaker": "marine_reaction_2", "text": "Tengo il corridoio.", "tone": "calm"})]]
        await self.news(DOWN)
        self.assertEqual(len(self.bed.llm.requests), 2)
        self.assertEqual([l["text"] for l in self.bed.lines], ["Tengo il corridoio."])    # (the prose itself was never said: §1bis, no guessing from the text)
        self.assertTrue(self.m.pulses[-1]["asked_again"])

    async def test_the_system_prompt_is_the_same_every_time_and_the_message_is_last(self) -> None:
        self.bed.llm.say(self.quiet)
        await self.news(CONTACT)
        self.bed.at(mm.MIN_GAP_S + 1)
        await self.news(DOWN)
        a, b = self.bed.llm.requests
        self.assertEqual(a["messages"][0], b["messages"][0])
        self.assertEqual([m["role"] for m in a["messages"]], ["system", "user"])
        self.assertNotEqual(a["messages"][1], b["messages"][1])

    async def test_the_summary_counts_what_happened(self) -> None:
        self.bed.llm.say(("say", {"speaker": "reyes", "text": "Reaction Uno contatto.", "tone": "tense"}))
        await self.news(CONTACT)
        s = self.m.summary()
        self.assertEqual((s["pulses"], s["lines"], s["errors"]), (1, 1, 0))
        self.assertAlmostEqual(s["cost"], 0.0004, places=5)


# ------------------------------------------------------------------------------------------------ voices, orders, the Captain's talk
class Voices(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.bed = Bed(self.tmp.name)
        self.m = self.bed.m
        self.m.feed(ship_state())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def say(self, **a: Any) -> dict[str, int]:
        rec = {"lines": 0}
        await self.m._say({"tone": "calm", **a}, "it", False, rec)
        return rec

    async def test_the_major_and_the_leaders_reach_the_stage_by_their_keys(self) -> None:
        await self.say(speaker="reyes", text="Chiudo il corridoio, Capitano.")
        await self.say(speaker="marine_reaction_2", text="Contatto, sei ostili.", tone="tense", urgent=True)
        self.assertEqual([(l["speaker"], l["urgent"], l["tone"]) for l in self.bed.lines], [("reyes", False, "calm"), ("marine_reaction_2", True, "tense")])
        self.assertIn("Reaction 2 (Sergeant Jonas Weber): Contatto", self.m._recall())

    async def test_a_squad_by_its_name_is_the_same_squad(self) -> None:
        await self.say(speaker="Reaction 1", text="Ci muoviamo.")
        await self.say(speaker="REYES", text="Ricevuto.")
        self.assertEqual([l["speaker"] for l in self.bed.lines], ["marine_reaction_1", "reyes"])

    async def test_nobody_else_speaks(self) -> None:
        rec = await self.say(speaker="marine_watch_1", text="Siamo a terra.")                  # (nobody of Watch 1 is on his feet)
        await self.say(speaker="xo", text="Capitano, abbordaggio.")
        await self.say(speaker="marine_reaction_9", text="Chi sono?")
        await self.say(speaker="reyes", text="x")                                               # (a line of one letter is no line)
        self.assertEqual(self.bed.lines, [])
        self.assertEqual(rec["lines"], 0)

    async def test_an_unknown_tone_is_calm(self) -> None:
        await self.say(speaker="reyes", text="Capitano.", tone="sarcastic")
        self.assertEqual(self.bed.lines[0]["tone"], "calm")

    async def test_a_line_that_calls_the_captain_is_a_direct_call_and_an_answer_is_not_marked_twice(self) -> None:
        # the marine says the line is for the Captain (`to_captain`): it reaches his speaker in the marine's own voice (nets.py: direct); the news is the XO's to tell
        await self.say(speaker="reyes", text="Capitano, Reaction Due è tagliata fuori: mi serve un suo ordine.", to_captain=True)
        await self.say(speaker="marine_reaction_1", text="Contatto, sei ostili.", tone="tense")
        self.assertEqual([(l["speaker"], l["direct"], l["answer"]) for l in self.bed.lines], [("reyes", True, False), ("marine_reaction_1", False, False)])
        rec = {"lines": 0}
        await self.m._say({"speaker": "reyes", "text": "Ricevuto, Capitano. Reaction Due si ritira.", "tone": "calm", "to_captain": True}, "it", True, rec)          # (an answer to his words reaches him anyway)
        self.assertEqual((self.bed.lines[-1]["answer"], self.bed.lines[-1]["direct"]), (True, False))

    def test_the_say_tool_has_the_call_and_the_prompt_says_who_hears_whom(self) -> None:
        say = next(t for t in mm.TOOLS if t["function"]["name"] == "say")["function"]
        self.assertIn("to_captain", say["parameters"]["properties"])
        self.assertEqual(say["parameters"]["required"], ["speaker", "text", "tone"])
        s = mm.system_prompt()
        for needle in ("Who hears you.", "the XO has the watch on your net", "`to_captain`", "your net is his radio"):
            self.assertIn(needle, s)

    def test_the_captain_is_with_the_marines_when_the_game_says_so(self) -> None:
        st = ship_state()
        self.assertFalse(mm.with_marines(st))
        st["boarding"]["captain_with_marines"] = True
        self.assertTrue(mm.with_marines(st))
        self.assertFalse(mm.with_marines(ship_state(fight=False)))
        self.assertFalse(mm.with_marines(None))
        self.assertFalse(mm.with_marines({"boarding": {"captain_with_marines": False, "captain_aboard": False}}))


class Orders(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.bed = Bed(self.tmp.name)
        self.m = self.bed.m
        self.st = ship_state()
        self.m.feed(self.st)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def test_the_major_orders_any_squad_and_it_goes_to_the_game_as_marine_order(self) -> None:
        r = await self.m._command("order", {"by": "reyes", "squad": "Reaction 1", "task": "hold", "place": "d7_corridor_B1", "reason": "the way into Engineering"})
        self.assertTrue(r["ok"])
        self.assertEqual(self.bed.commands, [("marine_order", {"squad": "Reaction 1", "task": "hold", "place": "d7_corridor_B1", "note": "the way into Engineering"}, "reyes")])

    async def test_the_infantry_orders_reach_the_game_with_what_goes_with_them(self) -> None:
        await self.m._command("order", {"by": "reyes", "squad": "all", "task": "take", "place": "deck 7 section D", "sync": "Go", "reason": "the junction before Engineering"})
        await self.m._command("order", {"by": "reyes", "squad": "Reaction 2", "task": "AMBUSH", "place": "corridor_5b", "fire": "Held", "cover": "d7_corridor_B1"})
        await self.m._command("order", {"by": "reyes", "squad": "Reaction 1", "task": "withdraw", "seal_behind": True})
        await self.m._command("order", {"by": "reyes", "squad": "Reaction 1", "task": "hold", "place": "d7_corridor_B1", "inside": "true", "seal_behind": False})
        await self.m._command("order", {"by": "reyes", "squad": "Reaction 2", "task": "escort_captain"})
        sent = [c[1] for c in self.bed.commands]
        self.assertEqual(sent, [{"squad": "all", "task": "take", "place": "deck 7 section D", "note": "the junction before Engineering", "sync": "go"},
                                {"squad": "Reaction 2", "task": "ambush", "place": "corridor_5b", "fire": "held", "cover": "d7_corridor_B1"},
                                {"squad": "Reaction 1", "task": "withdraw", "seal_behind": True},
                                {"squad": "Reaction 1", "task": "hold", "place": "d7_corridor_B1", "inside": True},
                                {"squad": "Reaction 2", "task": "escort_captain"}])                   # (what is not said is not sent: a false flag is no flag)

    async def test_a_squad_by_its_key_goes_to_the_game_by_its_name(self) -> None:
        await self.m._command("order", {"by": "reyes", "squad": "marine_reaction_2", "task": "FALL_BACK", "place": "captain"})
        self.assertEqual(self.bed.commands[0][1], {"squad": "Reaction 2", "task": "fall_back", "place": "captain"})
        self.bed.commands.clear()
        await self.m._command("order", {"by": "reyes", "squad": "all", "task": "stand_down"})
        self.assertEqual(self.bed.commands, [("marine_order", {"squad": "all", "task": "stand_down"}, "reyes")])

    async def test_a_leader_orders_only_his_own_squad(self) -> None:
        ok = await self.m._command("order", {"by": "marine_reaction_2", "squad": "Reaction 2", "task": "assault", "place": "corridor_5b"})
        self.assertTrue(ok["ok"])
        self.assertEqual(self.bed.commands[-1][2], "marine_reaction_2")
        n = len(self.bed.commands)
        for squad in ("Reaction 1", "all", "reaction", "marine_reserve_1"):
            r = await self.m._command("order", {"by": "marine_reaction_2", "squad": squad, "task": "hold"})
            self.assertFalse(r["ok"], squad)
            self.assertIn("commands only Reaction 2", r["detail"])
        r = await self.m._command("order", {"by": "marine_reaction_9", "squad": "Reaction 1", "task": "hold"})
        self.assertFalse(r["ok"])
        r = await self.m._command("order", {"by": "xo", "squad": "all", "task": "hold"})
        self.assertFalse(r["ok"])
        self.assertEqual(len(self.bed.commands), n)                                              # (nothing refused reached the game)

    async def test_the_bulkheads_are_the_majors(self) -> None:
        await self.m._command("bulkheads", {"action": "seal", "doors": ["BLK-D5-12", " BLK-D5-14 "], "reason": "slow them"})
        await self.m._command("bulkheads", {"action": "open"})
        await self.m._command("bulkheads", {"action": "seal", "doors": []})
        await self.m._command("bulkheads", {"action": "seal", "doors": "BLK-D5-12"})            # (not a list: the whole breach section, not a guess)
        self.assertEqual(self.bed.commands, [("lockdown", {"sealed": True, "doors": ["BLK-D5-12", "BLK-D5-14"]}, "reyes"), ("lockdown", {"sealed": False, "scope": "breach_section"}, "reyes"),
                                             ("lockdown", {"sealed": True, "scope": "breach_section"}, "reyes"), ("lockdown", {"sealed": True, "scope": "breach_section"}, "reyes")])

    async def test_a_game_that_does_not_answer_is_said_so(self) -> None:
        async def slow(*a: Any) -> dict[str, Any]:
            raise asyncio.TimeoutError
        self.m.execute = slow
        r = await self.m._command("order", {"by": "reyes", "squad": "all", "task": "hold"})
        self.assertEqual((r["ok"], r["detail"]), (False, "no response from the game"))
        async def broken(*a: Any) -> dict[str, Any]:
            raise RuntimeError("socket closed")
        self.m.execute = broken
        r = await self.m._command("bulkheads", {"action": "seal"})
        self.assertFalse(r["ok"])
        self.assertIn("socket closed", r["detail"])

    async def test_the_line_after_an_order_waits_for_the_game_and_is_not_said_if_it_refused(self) -> None:
        self.bed.llm.replies = [[("order", {"by": "reyes", "squad": "Reaction 1", "task": "hold", "place": "the hangar"}),
                                 ("say", {"speaker": "reyes", "text": "Reaction Uno tiene l'hangar.", "tone": "calm"})],
                                [("say", {"speaker": "reyes", "text": "Non conosco quel posto, Capitano: tengo l'ingresso dell'ingegneria?", "tone": "calm"}),
                                 ("order", {"by": "reyes", "squad": "Reaction 1", "task": "hold", "place": "d7_corridor_B1"})]]
        self.bed.results["marine_order"] = {"ok": False, "detail": "the plan has no place 'the hangar' (use an id from the picture)"}
        calls = {"n": 0}
        real = self.bed._execute

        async def second_time_ok(name: str, args: dict[str, Any], by: str) -> dict[str, Any]:
            calls["n"] += 1
            if calls["n"] == 2:
                self.bed.results["marine_order"] = {"ok": True, "detail": "Reaction 1: hold at deck 7 section B (Corridor 7-B)"}
            return await real(name, args, by)
        self.m.execute = second_time_ok
        self.m.captain_to_net("Reaction Uno, tenete l'hangar", "it")
        await self.bed.settle(1.0)
        self.assertEqual([l["text"] for l in self.bed.lines], ["Non conosco quel posto, Capitano: tengo l'ingresso dell'ingegneria?"])    # (the first line, composed before the answer, was never said)
        self.assertEqual([c[1]["place"] for c in self.bed.commands], ["the hangar", "d7_corridor_B1"])
        again = self.bed.llm.requests[1]["messages"]
        self.assertTrue(any(m.get("role") == "tool" and "FAILED: the plan has no place" in m["content"] for m in again))      # (the one who gave it read why)
        self.assertEqual(self.m.pulses[-1]["held"], 1)
        self.assertEqual((self.m.pulses[-1]["ok"], self.m.pulses[-1]["failed"]), (1, 1))
        self.assertIn("ordered Reaction 1: hold at the hangar => FAILED", self.m._recall())

    async def test_the_line_after_an_order_that_went_through_is_said(self) -> None:
        self.bed.llm.replies = [[("order", {"by": "reyes", "squad": "Reaction 2", "task": "follow_captain"}),
                                 ("say", {"speaker": "marine_reaction_2", "text": "Con lei, Capitano.", "tone": "calm"})]]
        self.m.captain_to_net("Reaction Due, con me", "it")
        await self.bed.settle(1.0)
        self.assertEqual([c[0] for c in self.bed.commands], ["marine_order"])
        self.assertEqual([l["text"] for l in self.bed.lines], ["Con lei, Capitano."])
        self.assertEqual(len(self.bed.llm.requests), 1)                                             # (no second look: it all went through)


class Rethink(unittest.IsolatedAsyncioTestCase):
    """The speech floor asks a person to think again about a line that waited: a model that fails gives the line back as it stands (that is not the marine's word that it no longer matters)."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.bed = Bed(self.tmp.name)
        self.m = self.bed.m
        self.m.feed(ship_state())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def test_a_model_that_fails_gives_the_line_back_as_it_stands(self) -> None:
        self.bed.llm.error = "provider down"
        self.assertEqual(await self.m.rethink("reyes", "Reaction Due ha preso il bivio.", 14.0, "", "it"), "Reaction Due ha preso il bivio.")
        self.assertEqual(await self.m.rethink("marine_reaction_2", "Contatto, sei ostili.", 9.0, "Contatto", "it"), "Contatto, sei ostili.")

    async def test_a_marine_who_says_it_again_or_lets_it_go_is_believed(self) -> None:
        self.bed.llm.replies = [[("say", {"speaker": "reyes", "text": "Reaction Due tiene il bivio, tre ostili a terra.", "tone": "calm"})]]
        self.assertEqual(await self.m.rethink("reyes", "Reaction Due ha preso il bivio.", 14.0, "", "it"), "Reaction Due tiene il bivio, tre ostili a terra.")
        self.bed.llm.replies = [[("stay_quiet", {"reason": "the Captain has it"})]]
        self.assertIsNone(await self.m.rethink("reyes", "Reaction Due ha preso il bivio.", 14.0, "", "it"))

    async def test_a_line_of_someone_who_is_not_on_the_net_is_left_as_it_is(self) -> None:
        self.assertEqual(await self.m.rethink("marine_nobody_9", "Dove siete?", 12.0, "", "it"), "Dove siete?")


class CaptainTalk(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.bed = Bed(self.tmp.name)
        self.m = self.bed.m
        self.m.feed(ship_state())

    def tearDown(self) -> None:
        self.tmp.cleanup()

    async def test_an_order_with_no_word_said_is_answered_by_whoever_he_called(self) -> None:
        self.bed.llm.replies = [[("order", {"by": "reyes", "squad": "all", "task": "fall_back", "place": "captain"})],
                                [("say", {"speaker": "reyes", "text": "Tutti verso di lei, Capitano.", "tone": "calm"})]]
        self.m.captain_to_net("Tutti indietro, da me", "it")
        await self.bed.settle(1.0)
        self.assertEqual(len(self.bed.llm.requests), 2)
        self.assertIn("has not heard a voice answer him", self.bed.user())
        self.assertIn("order({", self.bed.user())                                                  # (what was done so far, for the one who answers)
        self.assertEqual([(l["speaker"], l["answer"]) for l in self.bed.lines], [("reyes", True)])

    async def test_words_that_were_not_for_the_net_are_left_to_the_bridge(self) -> None:
        self.bed.llm.say(("stay_quiet", {"reason": "the Captain is talking to the helm"}))
        self.m.captain_to_net("Helm, bring us about", "en")
        await self.bed.settle()
        self.assertEqual(len(self.bed.llm.requests), 1)                                           # (no second try: a deliberate silence is an answer)
        self.assertEqual((self.bed.lines, self.bed.unanswered), ([], []))

    async def test_nobody_answering_is_asked_again_once_then_the_bridge_has_the_words(self) -> None:
        self.bed.llm.replies = [[], []]
        self.m.captain_to_net("Reyes, rapporto", "it")
        await self.bed.settle(1.0)
        self.assertEqual(self.bed.lines, [])
        self.assertLessEqual(len(self.bed.llm.requests), 2)

    async def test_the_leader_at_hand_answers_for_his_squad_and_orders_it(self) -> None:
        st = ship_state()
        st["_marines"]["captain"] = {"where": PLACE, "where_id": "corridor_5c_s", "down": False, "strength_pct": 90}
        self.m.feed(st)
        self.bed.llm.replies = [[("order", {"by": "marine_reaction_2", "squad": "Reaction 2", "task": "hold", "place": "captain"}),
                                 ("say", {"speaker": "marine_reaction_2", "text": "Teniamo qui, Capitano.", "tone": "focused"})]]
        self.m.captain_to_net("Sergente, tenete questo corridoio", "it")
        await self.bed.settle(1.0)
        self.assertEqual(self.bed.commands, [("marine_order", {"squad": "Reaction 2", "task": "hold", "place": "captain"}, "marine_reaction_2")])
        self.assertEqual([(l["speaker"], l["answer"]) for l in self.bed.lines], [("marine_reaction_2", True)])
        self.assertIn("in the same room as Sergeant Jonas Weber", self.bed.user())

    async def test_reyes_orders_on_his_own_in_a_look_and_says_so(self) -> None:
        self.bed.llm.replies = [[("bulkheads", {"action": "seal", "doors": ["BLK-D5-14"], "reason": "the way to the Spine"}),
                                 ("say", {"speaker": "reyes", "text": "Chiudo la paratia sulla Spine, Capitano.", "tone": "focused"})]]
        self.m.on_event(CUT)
        self.bed.at(mm.SETTLE_S + 0.5)
        self.m.feed(ship_state())
        await self.bed.settle(1.0)
        self.assertEqual(self.bed.commands, [("lockdown", {"sealed": True, "doors": ["BLK-D5-14"]}, "reyes")])
        self.assertEqual([(l["speaker"], l["answer"]) for l in self.bed.lines], [("reyes", False)])                  # (his own initiative: not an answer)
        self.assertIn("Reyes ordered bulkheads seal ['BLK-D5-14'] => ok", self.m._recall())


class Memories(unittest.TestCase):
    def test_a_memory_is_kept_loaded_and_forgotten_with_the_campaign(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            a = Bed(tmp)
            a.m.feed(ship_state())
            a.m._remember({"speaker": "reyes", "kind": "promise", "memory": "The Captain promised Reyes that no marine would hold a bulkhead alone again."})
            a.m._remember({"speaker": "marine_reaction_1", "kind": "loss", "memory": "Castillo lost Hassan holding the junction on the Captain's order."})
            a.m._remember({"speaker": "marine_reaction_1", "kind": "loss", "memory": "castillo lost hassan holding the junction on the captain's order."})      # (the same thing, once)
            a.m._remember({"speaker": "xo", "kind": "moment", "memory": "Nobody's."})
            a.m._remember({"speaker": "reyes", "kind": "moment", "memory": ""})
            self.assertEqual(sorted(a.m.memories), ["npc412", "reyes"])
            self.assertEqual(len(a.m.memories["npc412"]), 1)
            b = Bed(tmp)
            self.assertTrue(b.m.load())
            self.assertEqual(b.m.memories, a.m.memories)
            b.m.new_campaign()
            self.assertEqual(b.m.memories, {})
            self.assertFalse(Bed(tmp).m.load() and Bed(tmp).m.memories)

    def test_the_oldest_routine_memory_goes_first_and_a_promise_stays(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            m = Bed(tmp).m
            m._remember({"speaker": "reyes", "kind": "promise", "memory": "A promise."})
            for i in range(mm.MEMORY_PER * 2 + 4):
                m._remember({"speaker": "reyes", "kind": "moment", "memory": f"A moment {i}."})
            mems = m.memories["reyes"]
            self.assertEqual(len(mems), mm.MEMORY_PER * 2)
            self.assertEqual(mems[0]["memory"], "A promise.")

    def test_a_missing_or_broken_file_is_no_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            m = Bed(tmp).m
            self.assertFalse(m.load())
            Path(tmp, "marines.json").write_text("{not json", encoding="utf-8")
            self.assertFalse(m.load())
            m.path = lambda: None
            self.assertFalse(m.load())
            m.save()                                                                            # (no path: nothing is written, nothing breaks)


if __name__ == "__main__":
    unittest.main()
