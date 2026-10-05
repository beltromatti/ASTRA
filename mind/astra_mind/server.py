"""astra-mind: the crew's minds and voices, next to the game.

WebSocket ws://127.0.0.1:8765 (ASTRA_MIND_PORT moves it, for the game too) — JSON text frames + binary audio frames.
Game -> mind:  hello · ship_state{state} · event{text} · player_text{text,lang?} · ptt{down} · command_result{id,ok,detail}
Mind -> game:  status{...} · transcript{text,lang} · command{id,name,args,by} · turn_end{...}
               voice (docs/protocollo_voce.md): line{id,speaker,name,text,lang,tone,priority,est_s,hold_s,...} (sent when the
               voice starts) · audio_begin{line,speaker,rate,est_s,hold_s} · <binary: uint32 LE line id + PCM16 mono, paced>
               · audio_end{line,dur_s,reason} · cancel{line,reason,fade_ms} · line_dropped{id,reason} · floor{state}

Also: `astra-mind --say "text"` (one turn against the local ship model, audio to .wav) and `--script file` (a list of
utterances, timings, audio round-trip check with the recogniser).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import struct
import sys
import time
import wave
from pathlib import Path
from typing import Any, Awaitable, Callable

from lingua import Language, LanguageDetectorBuilder

from .agent import SYSTEM_CALL_ASK, WHEEL_ASK, BridgeAgent, ShipLink, net_ask, system_calls_only
from .audio_in import PushToTalk
from .crew import CREW, WHEEL_EVENT
from .enemy import COMMANDERS, EnemyAgent
from .style import StyleKeeper
from . import router as router_mod
from .context import Exchange, badge_of_raw, parse as parse_context, parse_lift
from .delegation import Delegation
from .initiative import Watch, chatter_system, recent_orders, watch_ask, watch_system
from .director import ADMIRAL, Director
from .env import CACHE, SAVED
from .host import install_stop_handlers, mind_port
from .local_ship import LocalShip
from .openrouter import OpenRouter, credits
from .stt import Recognizer
from .voice_lang import resolve_language
from .speech import REPORT_LATE_S, Prio, Voice
from .flight_minds import CAST as FLIGHT_CAST, PARTY as FLIGHT_PARTY, PARTY_ALIASES as FLIGHT_ALIASES, FlightMinds, flying as _flying, on_flight_deck as _on_flight_deck
from .marines import PARTY as MARINES_PARTY, MarineMinds, with_marines
from .nets import CALL_MARK, NET_EVENT, URGENT_MARK, Nets
from .war_minds import ALLIES, WarMinds, drawn_mandate_officer
from .march import March
from .march_glue import MarchGlue
from .strategy import StrategicMinds
from .tts import TTSEngine
from .voice_qos import boost_thread

log = logging.getLogger("astra.mind")
HOST, PORT = "127.0.0.1", mind_port()           # (ASTRA_MIND_PORT moves it, for the game too: host.py)

_LANGS = {Language.ITALIAN: "it", Language.ENGLISH: "en", Language.SPANISH: "es", Language.FRENCH: "fr",
          Language.GERMAN: "de", Language.PORTUGUESE: "pt", Language.DUTCH: "nl"}
_DETECT = LanguageDetectorBuilder.from_languages(*_LANGS).build()


def detect_lang(text: str, default: str = "en") -> str:
    lang = _DETECT.detect_language_of(text)
    return _LANGS.get(lang, default) if lang else default


class GameShip:
    """ShipLink backed by the game: commands go to Unreal, which answers with the authoritative result."""

    def __init__(self, send, intercept: dict[str, Any] | None = None) -> None:  # noqa: ANN001
        self._send = send
        self.state: dict[str, Any] = {}
        self.events: list[str] = []
        self._waiting: dict[str, asyncio.Future] = {}
        self._n = 0
        # commands the mind takes first: a request to an allied captain is judged by him (war_minds.py), an order to a group is checked against
        # the chain of command. A hook answers with a result, or None to let the command go to the game as it is.
        self.intercept = intercept or {}

    def snapshot(self) -> dict[str, Any]:
        return self.state

    def recent_events(self) -> list[str]:
        return self.events[-8:]

    async def execute(self, name: str, args: dict[str, Any], by: str, direct: bool = False) -> dict[str, Any]:
        hook = None if direct else self.intercept.get(name)
        if hook is not None:
            res = await hook(args, by)
            if res is not None:
                return res
        self._n += 1
        cid = f"c{self._n}"
        fut = asyncio.get_running_loop().create_future()
        self._waiting[cid] = fut
        await self._send({"type": "command", "id": cid, "name": name, "args": args, "by": by})
        try:
            # (the game answers in milliseconds, but a force coming onto the plot loads for a few seconds: 5 Oct, at 2.5 s an order already in force
            # came back as «no answer» and the officer told the Captain the command had failed)
            return await asyncio.wait_for(fut, timeout=6.0)
        finally:
            self._waiting.pop(cid, None)

    def resolve(self, msg: dict[str, Any]) -> None:
        fut = self._waiting.get(msg.get("id", ""))
        if fut and not fut.done():
            fut.set_result({"ok": bool(msg.get("ok")), "detail": msg.get("detail", "")})


EXTERNAL_SPEAKERS = {c["key"]: (f'{c["name"]} ({c["ship"]})', c["voice"]) for c in COMMANDERS.values()}
EXTERNAL_SPEAKERS[ADMIRAL["key"]] = (f'{ADMIRAL["name"]} ({ADMIRAL["ship"]})', ADMIRAL["voice"])
for _a in ALLIES.values():                        # the captains of the picket (war_minds.py): the ones the director adds are registered as they come
    EXTERNAL_SPEAKERS[_a["key"]] = (f'{_a["name"]} ({_a["ship"]})', _a["voice"])
for _p in FLIGHT_CAST.values():                   # the flight net's people (flight_minds.py): radio voices; FlightMinds renames the wingmen when they fly Eagle's wing
    EXTERNAL_SPEAKERS[_p.key] = (_p.display, _p.voice)
from .port import PORT as PORT_CONTROL, FieldControl, for_field, stimulus_for, world_of  # noqa: E402
from .medbay import patient_voice  # noqa: E402
from .mess import MessTalk  # noqa: E402
from .visits import VisitPlanner  # noqa: E402
from .loss import Aftermath  # noqa: E402
from .finale import Finale  # noqa: E402
from .memory import MemoryKeeper  # noqa: E402
from .npc import Npcs  # noqa: E402
from .transporter import DISPLAY as XFER_DISPLAY, SPEAKER as XFER_SPEAKER, TITLE as XFER_TITLE, VOICE as XFER_VOICE, TransporterRoom  # noqa: E402
EXTERNAL_SPEAKERS[PORT_CONTROL["key"]] = (f'{PORT_CONTROL["name"]} ({PORT_CONTROL["place"]})', PORT_CONTROL["voice"])
EXTERNAL_SPEAKERS["director"] = ("The Director (game master)", "paul")
from .story import NARRATOR, NARRATOR_NAME, NARRATOR_VOICE  # noqa: E402
EXTERNAL_SPEAKERS[NARRATOR] = (NARRATOR_NAME, NARRATOR_VOICE)          # the story's narrated cards (story.py)
EXTERNAL_SPEAKERS[XFER_SPEAKER] = (XFER_DISPLAY, XFER_VOICE)         # the Transporter Room's Chief (transporter.py)


def _both(a: "asyncio.Future[bool]", b: "asyncio.Future[bool]") -> "asyncio.Future[bool]":
    """One verdict out of two listeners' (npc.py, transporter.py): True (nobody answered, the words were for the bridge) only when both say so."""
    out: asyncio.Future = asyncio.get_running_loop().create_future()

    def check(_f) -> None:  # noqa: ANN001
        if not out.done() and a.done() and b.done():
            out.set_result(bool(a.result()) and bool(b.result()))
    a.add_done_callback(check)
    b.add_done_callback(check)
    return out


EXTERNAL_SPEAKERS["computer"] = ("Ship's computer", "estelle")          # the lifts' voice (a car the Captain is in: tools.lift_tool)

# the player talking to the story itself (game master mode): "Regista, ...", "Director, ...", "Narratore, ..."
import re as _re  # noqa: E402
# events whose report is a warning of danger: the crew says them before any routine talk (voice priority URGENT)
# (our hull breach is danger when it opens, not when it is sealed: 5 Oct, «the breach at the Reaction-Mass Tank is sealed» was told as a warning and cut,
# in a battle, the same report three times in a row)
_URGENT_EVENT = _re.compile(r"missiles? inbound|rockets? inbound|torpedoes away|hull integrity critical|containment failing|abandon ship|"
                           r"hull breach(?![^.;]*\b(?:sealed|closed|patched|held)\b)|to the reactor breach|main reactor has breached|new contacts|is cycling|"
                           r"coming through|" + _re.escape(URGENT_MARK), _re.I)    # (an enemy's «reactor breached» is her death, not our danger: it cut a hail, 5 Oct)    # (URGENT_MARK: a net's sender said it is danger now, nets.py)
URGENT_GATHER_S = 0.6          # what comes with a warning of danger joins it (a hit: its breach, fire and wounded arrive together)
URGENT_WAIT_S = 3.0            # ... and it waits for the line being said to end, this long at most
ROUTINE_WAIT_S = 25.0          # routine news waits for a quiet bridge this long at most: in a fleet battle the bridge is never quiet,
                               # and news held back for minutes (the gate cycling, told five minutes late) is worse than a busy floor
PICTURE_GAP_S = 20.0           # after a report turn that said something, the next one for routine news is this long after it: the picture is given at this pace, not at the
                               # pace of the news (5 October: 86 news items in three minutes of a battle, a report turn for each, ten lines a minute); the news that came meanwhile
                               # is read together, with its age. A warning of danger and a call to the Captain do not wait (`_presses`)
REPORT_GAP_S = 10.0            # ... and after one that said nothing, this long: the officers are asked a few times a minute, not for every item
URGENT_GAP_S = 6.0             # a warning of danger does not wait behind routine talk, but after one that was said the next waits this long: what comes meanwhile is told together
                               # (a battle's «breach» and «missiles inbound» are every few seconds: a warning turn for each was nine lines out of every seventeen, the same picture again)
CHANNEL_IDLE_S = 75.0          # a channel with the fleet, an ally or an enemy is open for an exchange: with nothing passed on it for this long Communications closes it (5 October: the
                               # fleet's stayed open for eighteen minutes after the admiral's answer, and what the Captain said to his own crew about the Kestrels went out on it)
# events that are not news but a request to speak (the flight controller calls, the after-action report, the fleet net's news, a visitor
# at the door): they are reported whenever the bridge is quiet, however long that took
_NOT_PERISHABLE = _re.compile(r"^(flight: controller call|bridge: after-action|comms: fleet net news)|has come to the Captain's quarters in person", _re.I)


# what the router says on the fleet net for whom the words are (router.REPLY_FLEET): its two words, `admiral` and `all` (and what the model writes for them when it spells them out:
# the protocol is in English), anything else is a ship or a captain, found by name (war.deliver); a name nobody answers to is everyone, so no word of the Captain's is lost
_FOR_THE_ADMIRAL = {"admiral", "rourke", "fleet command", "vice admiral", "vice admiral rourke"}
_FOR_ALL = {"all", "everyone", "everybody", "all ships", "fleet", "the fleet", ""}


def _presses(event: str) -> bool:
    """News that does not wait for the picture's pace (PICTURE_GAP_S): a hail (the enemy calls the Aquila), a call to the Captain on a net, the flight controller's call to a Captain
    in a Falcon. A warning of danger has its own way through (`_URGENT_EVENT`)."""
    return event.startswith(("transmission:", "flight: controller call")) or (event.startswith(NET_EVENT) and CALL_MARK in event)


def _outlives_the_captains_words(event: str) -> bool:
    """News that is told after the Captain's order when his words take the floor, instead of being lost to it: a warning of danger, and net traffic that calls him (its listener
    tells him: nothing addressed to him is lost). The rest of the news stays in the ship's state and the history."""
    return bool(_URGENT_EVENT.search(event)) or (event.startswith(NET_EVENT) and CALL_MARK in event)


_GM_ADDRESS = _re.compile(r"^\W*(regista|director|narrat\w*|game ?master|gm|réalisateur|directeur|director de juego|spielleiter|erzähler)\b[\s,:;.!-]*", _re.I)


def speaker_identity(speaker: str) -> tuple[str, str, bool]:
    """(display name, voice, aboard) of anyone who can speak: a bridge officer or someone on a channel or in a room."""
    if speaker in CREW:
        return CREW[speaker].title, CREW[speaker].voice, True
    name, voice = EXTERNAL_SPEAKERS.get(speaker, (speaker, "alba"))
    return name, voice, False


# the nets of people that are a channel of the Captain's (kind -> what the log says, who answers, an example of what nobody on the bridge says, who "nobody" is)
_NETS = {"flight": ("flight net", "the pilots, the CAG and the deck chief", "the CAG answers", "Price and Comms"),
         "marines": ("marine net", "Major Reyes and the squad leaders", "Reyes answers", "Tactical, the XO and Comms")}


class _TurnQueue(asyncio.Queue):
    """The turns waiting for the crew. An event that goes in is stamped with the time it arrived (loop time, a fourth item): a report of it is
    worth saying only while it is news, and the wait for a quiet bridge must not make old news of it unnoticed."""

    def put_nowait(self, item) -> None:  # noqa: ANN001
        if isinstance(item, tuple) and len(item) == 2 and str(item[0]).startswith("\x00event:"):
            item = (item[0], item[1], None, asyncio.get_running_loop().time())
        super().put_nowait(item)


class Mind:
    def __init__(self) -> None:
        self.llm = OpenRouter()
        self.llm.on_status = self._ai_status
        self.follow_voice = True                # the crew follows the language the Captain speaks (the game's LANGUAGE settings)
        self.tts = TTSEngine()
        self.stt = Recognizer()
        self.mic = PushToTalk()
        self._ptt_session = None                # the recognition session of the key press being held
        self.local = LocalShip()
        self.clients: set = set()
        self.game: GameShip | None = None
        self.voice = Voice(self.tts, self._sink, speaker_identity)
        # the radio nets and the consoles' logs (nets.py): what the people of the fleet, flight and marine nets say is traffic that its listener (an officer of the crew) reads and
        # tells the Captain what he must know; only answers to him, calls to him and the nets he asked to hear reach the speaker. ASTRA_NETS=0: everything on the speaker, as before
        self.nets = Nets(lambda m: self._sink("json", m), self._net_listen, enabled=os.environ.get("ASTRA_NETS", "1") != "0")
        self.nets.presence["flight"] = self._flight_presence
        self.nets.presence["marines"] = self._marines_presence
        self.agent = BridgeAgent(self.llm, self.local, self._crew_say)
        self.agent.nets = self.nets
        self.enemy = EnemyAgent(self.llm, self._say_external, self._enemy_command)
        self.port = FieldControl(self.llm, self._say_external, self._register_field)
        self.mess = MessTalk(self.llm, self.voice.say)
        self.npcs = Npcs(self.llm, self.voice.say, EXTERNAL_SPEAKERS)     # the ship's people when the Captain talks to them (npc.py)
        self.director = Director(self.llm, self._say_external, self._director_command, self._register_commander,
                                 news=self._fleet_news)
        self.visits = VisitPlanner(self.llm, self._director_command, self.director.note)
        self.aftermath = Aftermath(self.llm, self._say_external, self._director_command, self._register_voice, self.director,
                                   self.voice.busy_s)
        self.director.finale = Finale(self.llm, self._say_external, self._director_command, self.voice.busy_s)
        self.director.blocked = lambda: bool(((self.game.state if self.game else None) or {}).get("abandon")) or self.aftermath.active
        self.memory = MemoryKeeper(self.llm, self.director.memories, self.director.note)
        self.agent.memories = self.memory.lines
        # how this Captain commands: the XO learns it fight by fight, the Mandate's intelligence too (style.py)
        self.style = StyleKeeper(self.llm, self.director.style)
        self.agent.style = self.style.xo_line
        self.agent.home = self.director.home_lines
        self.director.captain_style = self.style.xo_line
        self.enemy.intel = self.style.mandate_line
        # the minds that command the war: the Mandate's admiral and group commanders, the allied captains (war_minds.py)
        self.war = WarMinds(self.llm, self._ally_say, self._war_execute, lang=lambda: self.lang, mandate_persona=COMMANDERS.get,
                            channel=lambda c: self.enemy.open and self.enemy.contact == c, register_voice=self._register_voice,
                            transmit=self._say_external, intel=self.style.mandate_line, note=self.director.note, captain=self._war_captain)
        self.war.disabled = os.environ.get("ASTRA_WAR_MINDS", "1") == "0"        # (ASTRA_WAR_MINDS=0: the groups fight on their reflexes, as before)
        self.war.formation_doctrine = os.environ.get("ASTRA_WAR_FORMATION", "0") == "1"   # (ASTRA_WAR_FORMATION=1: the doctrine also teaches the formation lever)
        # the flight net: the CAG, the squadron leaders and their wingmen, the Chief of the Deck (flight_minds.py)
        self.flight = FlightMinds(self.llm, self._flight_say, self._flight_execute, lang=lambda: self.lang, register_voice=self._register_voice,
                                  standing=lambda: {o["department"] for o in self.agent.standing}, path=self._flight_path)
        self.flight.disabled = os.environ.get("ASTRA_FLIGHT_MINDS", "1") == "0"           # (ASTRA_FLIGHT_MINDS=0: Price reports the flight events, as before)
        self.flight.on_unanswered = self._flight_unanswered
        # the Transporter Room's Chief (transporter.py): a person with her own mind who reads the room's console and carries out the orders the bridge relays and the Captain gives
        self.xfer = TransporterRoom(self.llm, self._xfer_say, self._xfer_execute, state=lambda: (self.game.state if self.game else None) or {}, lang=lambda: self.lang,
                                    relay=self._xfer_relay)
        self.xfer.disabled = os.environ.get("ASTRA_TRANSPORTER_MIND", "1") == "0"        # (ASTRA_TRANSPORTER_MIND=0: the bridge's orders go to the console as typed, nobody answers)
        # the marine net: Major Reyes and the squad leaders, while boarders are aboard (marines.py)
        self.marines = MarineMinds(self.llm, self._marines_say, self._marines_execute, lang=lambda: self.lang, register_voice=self._register_voice, path=self._marines_path)
        self.marines.disabled = os.environ.get("ASTRA_MARINE_MINDS", "1") == "0"          # (ASTRA_MARINE_MINDS=0: the marines fight on their drill, the bridge reports)
        self.marines.on_unanswered = self._marines_unanswered
        self.enemy.war = self.war
        self.director.war_minds = self.war
        self.director.negotiate = self._negotiate
        # the war of the March (march.py, strategy.py, march_glue.py): the fleets of both sides on the map of the Gates and the high commands that order them, joined to the real
        # simulation where the Aquila is; built when a campaign begins (ASTRA_MARCH=0: the director plays the war as before; ASTRA_STRATEGY_MINDS=0: the fleets go on on their reflexes;
        # ASTRA_OPENING=script: the game's own opening script is kept, otherwise a new campaign asks the game to switch it off and the March plays the opening)
        self.march: March | None = None
        self.strategy: StrategicMinds | None = None
        self.march_glue: MarchGlue | None = None
        self.agent.say = self._crew_say
        self.agent.heard = self.voice.heard_since          # what the bridge heard aloud, as it was said (the officers' «Said aloud»)
        self.agent.waiting = self.voice.waiting            # and what is queued behind the speaker (their «Waiting to be said»)
        self.flight.waiting = self.voice.waiting           # (the flight net sees the same backlog)
        self.war.waiting = self.voice.waiting              # (and the allied captains)
        # the Captain's log is private: the story reads it, the crew does not
        self.agent.campaign = lambda: [c for c in self.director.campaign if not c.startswith("captain's log:")]
        self.agent.war = lambda: self.director.war.crew_view()
        self.agent.mood = lambda: self.director.mood
        self.agent.bonds = lambda: "\n".join(f"- {line}" for line in self.director.bonds_lines())
        self.agent.standing = self.director.standing        # one list: the agent keeps it, the story saves it
        self.turns: asyncio.Queue = _TurnQueue()
        self.exchange = Exchange()               # who spoke last on the channel: an exchange going on (the router reads it)
        self.watch = Watch()                     # the officers' initiative watch (initiative.py)
        self.delegation = Delegation(self._delegation_path)     # how far each console's officer may act alone: the Captain's word, kept with the campaign (delegation.py)
        self._report_end = float("-inf")         # when the last report turn ended, and whether it said something: the picture's pace (PICTURE_GAP_S)
        self._report_spoke = False
        self._channel = ""                       # the party of the channel open with someone outside the ship (fleet, an ally's or an enemy's id), "" when none: it closes with the exchange
        self._ptt_ctx: dict[str, Any] | None = None   # the game's `context` for the words being spoken (ptt)
        self.last_activity = time.monotonic()   # the Captain spoke or something was reported
        self.captain_t = 0.0                     # the last time the Captain spoke
        self.lang_file = CACHE / "captain_lang.txt"
        self.lang = self.lang_file.read_text(encoding="utf-8").strip() if self.lang_file.exists() else "en"   # the Captain's language

    def _ai_status(self, state: str, detail: str) -> None:
        """OpenRouter's state changed (the credit ran out, the key was refused, the network is gone, it answers again): the game tells the
        player what to do instead of a crew that falls silent."""
        try:
            asyncio.get_running_loop().create_task(self._sink("json", {"type": "ai_status", "state": state, "detail": detail[:200]}))
        except RuntimeError:
            pass

    def _apply_language(self, msg: dict) -> None:
        """The game's LANGUAGE settings: the crew's language at the start (the first lines are in it) and whether it follows the Captain's voice."""
        lang = str(msg.get("lang") or "").strip().lower()
        if lang and lang != self.lang:
            self.lang = lang
            if hasattr(self.tts, "prepare"):
                asyncio.create_task(self.tts.prepare(lang, [o.voice for o in CREW.values()]))
        if "follow_voice" in msg:
            self.follow_voice = bool(msg.get("follow_voice"))
        log.info("language: %s (%s)", self.lang, "follows the Captain's voice" if self.follow_voice else "fixed")

    async def _sink(self, kind: str, payload: Any) -> None:
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send(json.dumps(payload, ensure_ascii=False) if kind == "json" else payload)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    async def _say_external(self, speaker: str, text: str, lang: str, tone: str, *,
                            rethink: Callable[[str, float, str], Awaitable[str | None]] | None = None) -> None:
        """Voices from outside the bridge that speak TO the Captain (a Mandate commander on the channel, Fleet command calling, the port's control, the board of inquiry): heard
        by the crew too. What is said to him is addressed to him: it is never lost to the queue (speech.py: `addressed`). `rethink`: whoever said it thinks again when
        the bridge cut it off or it waited (a Mandate commander: war_minds.rethink_transmission); without one, the rest of it is said as it stands."""
        if self.game is not None:
            who = EXTERNAL_SPEAKERS.get(speaker, (speaker, ""))[0]
            self.game.events.append(f"over the radio, {who}: {text}")
        if self.enemy.open and speaker == self.enemy.speaker:
            self.exchange.heard(self.enemy.contact, text)    # (an exchange is going on: comms knows what they just said)
        elif speaker == ADMIRAL["key"]:
            self.exchange.heard("fleet", text)
        contact = next((c for c, p in COMMANDERS.items() if p.get("key") == speaker), None) if rethink is None else None
        if contact is not None:
            async def rethink(t: str, waited: float, cut_after: str) -> str | None:
                # a Mandate commander's call that waited for the floor (or was cut off): one whose ship has gone since says nothing more (5 Oct: the
                # Tartarus's commander called the Aquila a minute after her ship blew up, twice); the others think again with the battle as it is now
                if contact in self.enemy.dead:
                    log.info("%s's call is not said: the %s is gone", speaker, contact)
                    return None
                return await self.war.rethink_transmission(speaker, t, waited, cut_after, lang)
        await self.voice.say(speaker, text, lang, tone, addressed=True, rethink=rethink)

    async def _ally_say(self, speaker: str, text: str, lang: str, tone: str, *, urgent: bool = False, answer: bool = False,
                        topic: str | None = None, to: str = "aquila") -> None:
        """An allied captain speaks on the fleet net (war_minds.py). It is NET TRAFFIC (nets.py): Communications reads it and tells the Captain what he must know, the rest is
        on the comms log and the datapad. It reaches the speaker by itself only as an `answer` to what the Captain said (it goes first), or with the fleet net on the speaker;
        a line that waited is thought again by whoever was to say it. `to`: "aquila" (the Captain: his listener has it at once), "fleet" (the net), or another captain's id
        (traffic between ships: on the log, nobody is woken for it)."""
        if self.aftermath.muted:
            return                                  # (the Aquila is gone: the story of her loss has the floor)
        who = EXTERNAL_SPEAKERS.get(speaker, (speaker, ""))[0]

        async def rethink(t: str, waited: float, cut_after: str) -> str | None:
            return await self.war.rethink(speaker, t, waited, cut_after, lang)

        async def aloud() -> None:
            if self.game is not None:
                self.game.events.append(f"over the radio, {who}: {text}")
            self.exchange.heard("fleet", text)
            await self.voice.say(speaker, text, lang, tone, priority=Prio.URGENT if urgent else None, answer=True if answer else None, topic=topic, rethink=rethink)

        await self.nets.post("fleet", speaker, who, text, lang, urgent=urgent, answer=answer, addressed=to in ("aquila", ""), quiet=to not in ("aquila", "fleet", ""),
                             aloud=aloud)

    def _start_march(self, new: bool) -> None:
        """A campaign begins (a new war, or the saved one): the March is the war from now on, with its high commands (Vice Admiral Rourke for ASTRA, the Archon for the Mandate)."""
        if os.environ.get("ASTRA_MARCH", "1") == "0":
            return
        if self.march_glue is None:
            import random
            march = March(self.director.war, seed=random.randrange(1, 10 ** 6))
            strategy = StrategicMinds(self.llm, march, self._rourke_say, lang=lambda: self.lang, intel=self.style.mandate_line, note=self.director.note)
            strategy.disabled = os.environ.get("ASTRA_STRATEGY_MINDS", "1") == "0"
            glue = MarchGlue(march, strategy, command=self._director_command, register_groups=self.director._register_groups, announce=self._march_news,
                             note=self.director.note, send_sector=self._send_sector, opening=os.environ.get("ASTRA_OPENING", "march") != "script")
            self.war.strategic = lambda side: strategy.field_brief(side, march.real_system)
            glue.on_war_over = lambda text: asyncio.create_task(self.director._end_arc(text, self.lang, self._battle_state()))
            self.director.march = glue
            self.director.rourke = None if strategy.disabled else glue.rourke_reply
            self.march, self.strategy, self.march_glue = march, strategy, glue
        self.march_glue.start(new)

    async def _rourke_say(self, speaker: str, text: str, lang: str, tone: str, *, answer: bool = False, direct: bool = False) -> None:
        """Vice Admiral Rourke speaks on the fleet net (strategy.py). A line that answers the Captain goes first, in his own voice, and is never lost. What Fleet says on its own
        is addressed to the Captain, and Communications tells him (nets.py); `direct`: a call that comes in the admiral's own voice (Fleet's order to the Aquila)."""
        if self.aftermath.muted:
            return                                  # (the Aquila is gone: the story of her loss has the floor)
        who = EXTERNAL_SPEAKERS.get(speaker, (speaker, ""))[0]

        async def aloud() -> None:
            if self.game is not None:
                self.game.events.append(f"over the radio, {who}: {text}")
            self.exchange.heard("fleet", text)
            await self.voice.say(speaker, text, lang, tone, answer=True if answer else None, addressed=direct and not answer)

        await self.nets.post("fleet", speaker, who, text, lang, answer=answer, direct=direct, addressed=True, aloud=aloud)

    async def _march_news(self, text: str) -> None:
        """What the March's war brings to the fleet net: comms relays it to the bridge (march_glue.py chooses what is worth saying)."""
        if self.aftermath.active:
            return                                  # (no bridge to relay it to: the Aquila is lost)
        self.last_activity = time.monotonic()
        await self.turns.put(("\x00event:comms: fleet net news — " + text, self.lang))

    async def _war_first(self, then: Any, went_on: bool) -> None:
        """The Captain comes back to a new ship weeks after the loss: the war went on without her (a few seconds of the March's hours), then the story resumes."""
        if went_on and self.march_glue is not None:
            try:
                await self.march_glue.fast_forward()
            except Exception:  # noqa: BLE001
                log.exception("the war could not go on without the Aquila")
        await then

    async def _war_execute(self, name: str, args: dict[str, Any], by: str) -> dict[str, Any]:
        """The commanders' orders to the game (group orders, fleet operations, decisions): straight to the ships, never through the hooks the
        Captain's own commands go through."""
        ship = self.game if (self.game and self.game.state) else None
        if ship is None:
            return {"ok": True, "detail": "(no game)"}
        return await ship.execute(name, args, by, direct=True)

    async def _war_captain(self, ship: str, rank: str, name: str) -> None:
        """A persona now speaks for a ship of the war: her interior in the game (FLOTTA-VIVA) takes the same captain."""
        res = await self._war_execute("fleet_captain", {"ship": ship, "rank": rank, "name": name}, "director")
        log.info("war: %s", res.get("detail", res))

    async def _flight_say(self, speaker: str, text: str, lang: str, tone: str, *, urgent: bool = False, answer: bool = False) -> None:
        """Someone on the flight net speaks (flight_minds.py). It is NET TRAFFIC (nets.py): Flight Control (Price) reads it and tells the Captain what he must know, the rest is on
        the flight console's log and the datapad. It reaches the speaker by itself only as the answer to the Captain's call (it goes first), with the net on the speaker, or while
        the Captain sits in a cockpit or stands on the flight deck (the net is his own radio there); a line that waited too long is thought again by whoever was to say it."""
        if self.aftermath.muted:
            return                                  # (the Aquila is gone: the story of her loss has the floor)
        who = EXTERNAL_SPEAKERS.get(speaker, (speaker, ""))[0]

        async def rethink(t: str, waited: float, cut_after: str) -> str | None:
            return await self.flight.rethink(speaker, t, waited, cut_after, lang)

        async def aloud() -> None:
            if self.game is not None:
                self.game.events.append(f"over the radio, {who}: {text}")
            self.exchange.heard(FLIGHT_PARTY, text)
            await self.voice.say(speaker, text, lang, tone, priority=Prio.URGENT if urgent else None, answer=True if answer else None, rethink=rethink)

        await self.nets.post("flight", speaker, who, text, lang, urgent=urgent, answer=answer, aloud=aloud)

    async def _flight_execute(self, name: str, args: dict[str, Any], by: str) -> dict[str, Any]:
        """A squadron's mission from its leader or the CAG: straight to the flight console (never through the hooks the Captain's own commands go through)."""
        ship = self.game if (self.game and self.game.state) else None
        if ship is None:
            return {"ok": True, "detail": "(no game)"}
        return await ship.execute(name, args, by, direct=True)

    async def _xfer_say(self, speaker: str, text: str, lang: str, tone: str, *, priority_urgent: bool = False, answer: bool = False) -> None:
        """The Transporter Room's Chief speaks: in her room the Captain hears her face to face, elsewhere over the intercom (the game decides); the bridge's crew reads
        what she said in its events, so that nobody repeats it. A line that waited is thought again by her first."""
        if self.game is not None:
            self.game.events.append(f"over the intercom, {XFER_TITLE} (Transporter Room): {text}")

        async def rethink(t: str, waited: float, cut_after: str) -> str | None:
            return await self.xfer.rethink(speaker, t, waited, cut_after, lang)
        await self.voice.say(speaker, text, lang, tone, priority=Prio.URGENT if priority_urgent else None, answer=True if answer else None, rethink=rethink)

    async def _xfer_execute(self, name: str, args: dict[str, Any], by: str) -> dict[str, Any]:
        """The Chief's console to the game: the transports and the personnel locator, straight to the ship (never through the hooks the bridge's own tools go through)."""
        ship = self.game if (self.game and self.game.state) else None
        if ship is None:
            return {"ok": False, "detail": "the ship does not answer"}
        return await ship.execute(name, args, by, direct=True)

    async def _xfer_order(self, args: dict[str, Any], by: str) -> dict[str, Any]:
        """The bridge's `transporter` tool: the order is handed to the Chief at once; she answers the Captain herself."""
        return await self.xfer.order(args, by)

    async def _xfer_relay(self, text: str) -> None:
        """The console carried an order out by itself (the Chief did not answer): the bridge is told."""
        self.last_activity = time.monotonic()
        await self.turns.put(("\x00event:" + text, self.lang))

    def _flight_path(self) -> str:
        return os.path.join(os.path.dirname(self.director.war.save_path), "flight.json")

    def _delegation_path(self) -> str:
        return os.path.join(os.path.dirname(self.director.war.save_path), "delegation.json")

    async def _flight_unanswered(self, words: list[str]) -> None:
        """The flight net could not answer the Captain (the model failed or stalled): Price takes his words, so that they are never lost."""
        self.last_activity = time.monotonic()
        await self.turns.put((f"\x00event:flight: the Captain called the flight net and nobody there answered: \"{' '.join(words)[:240]}\" — Price answers him now, "
                              "from Flight Control", self.lang))

    async def _marines_say(self, speaker: str, text: str, lang: str, tone: str, *, urgent: bool = False, answer: bool = False, direct: bool = False) -> None:
        """Someone on the marine net speaks (marines.py). It is NET TRAFFIC (nets.py): the XO reads it and tells the Captain what he must know, the rest is on the XO's log and the
        datapad. It reaches the speaker by itself as the answer to the Captain's call (it goes first), as a call to him in the speaker's own voice (`direct`: the marine says it
        is for him: a decision only he can take), with the net on the speaker, or while he is with the marines (`_marines_presence`); a line that waited too long is thought again by
        whoever was to say it (`rethink`)."""
        if self.aftermath.muted:
            return                                  # (the Aquila is gone: the story of her loss has the floor)
        who = EXTERNAL_SPEAKERS.get(speaker, (speaker, ""))[0]

        async def rethink(t: str, waited: float, cut_after: str) -> str | None:
            return await self.marines.rethink(speaker, t, waited, cut_after, lang)

        async def aloud() -> None:
            if self.game is not None:
                self.game.events.append(f"over the radio, {who}: {text}")
            self.exchange.heard(MARINES_PARTY, text)
            await self.voice.say(speaker, text, lang, tone, priority=Prio.URGENT if urgent else None, answer=True if answer else None, rethink=rethink)

        await self.nets.post("marines", speaker, who, text, lang, urgent=urgent, answer=answer, direct=direct, aloud=aloud)

    def _flight_presence(self) -> bool:
        """The Captain is on the flight net by where he is: he flies a Falcon (the cockpit's radio is the net) or stands on the flight deck (the Chief of the Deck is there)."""
        st = (self.game.state if self.game else None) or {}
        return _flying(st) or _on_flight_deck(st)

    def _marines_presence(self) -> bool:
        """The Captain is on the marine net by where he is: with the marines in their boat or on the decks of the ship they board (the boarding's `captain_with_marines`): it is his own radio."""
        st = (self.game.state if self.game else None) or {}
        return with_marines(st)

    async def _net_listen(self, net: str, text: str, urgent: bool, lang: str) -> None:
        """A net's traffic goes to its listener: an event of the crew's turn (the turn worker reads it with the rest of the news; an urgent one does not wait for a quiet bridge)."""
        self.last_activity = time.monotonic()
        await self.turns.put(("\x00event:" + NET_EVENT + text, lang or self.lang))

    async def _marines_execute(self, name: str, args: dict[str, Any], by: str) -> dict[str, Any]:
        """The marines' orders and the bulkheads (`marine_order`, `lockdown`): straight to the game (never through the hooks the Captain's own commands go through)."""
        ship = self.game if (self.game and self.game.state) else None
        if ship is None:
            return {"ok": True, "detail": "(no game)"}
        return await ship.execute(name, args, by, direct=True)

    def _marines_path(self) -> str:
        return os.path.join(os.path.dirname(self.director.war.save_path), "marines.json")

    async def _marines_unanswered(self, words: list[str]) -> None:
        """The marine net could not answer the Captain (the model failed or stalled): the XO takes his words, so that they are never lost."""
        self.last_activity = time.monotonic()
        await self.turns.put((f"\x00event:marines: the Captain called the marine net and nobody there answered: \"{' '.join(words)[:240]}\" — the XO answers him now, from the bridge",
                              self.lang))

    async def _hail_flight(self, args: dict[str, Any], by: str) -> dict[str, Any] | None:
        """Comms opens the flight net (`hail` flight): the mind keeps this channel (the game's `hail` knows contacts and the fleet). None: not for the net."""
        if str(args.get("contact_id", "")).strip().lower() not in FLIGHT_ALIASES or self.flight.disabled:
            return None
        return self.flight.open_net()

    async def _negotiate(self, contact: str, terms: str) -> bool:
        """The director has a Mandate commander call the Aquila to talk: the channel opens from his side and he says his piece (the same path as an
        arrival or a succession: `transmission:`, then the commander's mind answers the situation). False: that ship is not a hostile contact."""
        st = (self.game.state if (self.game and self.game.state) else None) or {}
        if not any(str(c.get("id", "")).upper() == contact and str(c.get("status", "")).startswith("hostile") for c in st.get("contacts", []) or []):
            return False
        self.last_activity = time.monotonic()
        await self.turns.put((f"\x00event:transmission: {contact} — you call the Aquila's captain to talk. Why: {terms}", self.lang))
        return True

    async def _fleet_request(self, args: dict[str, Any], by: str) -> dict[str, Any] | None:
        """Comms relays the Captain's request to the allied ships: their captains judge it (war_minds.py). None: nobody there has a mind to judge it,
        and the request goes to the ships the old way."""
        res = self.war.captain_request(args, self.lang)
        if res is not None:
            self.war.kick()                                   # (the captain reads it now, not at the next state)
        return res

    async def _captain_group_order(self, args: dict[str, Any], by: str) -> dict[str, Any]:
        """The XO gives one of our groups the Captain's direct order: only while the Captain is the senior officer present. The group's captain is told."""
        if not self.war.captain_is_senior():
            return {"ok": False, "detail": "the Captain is not the senior officer present: the senior officer commands the groups, ask him over the fleet net "
                                           "(fleet_request)"}
        cap = str(((self.game.state if self.game else None) or {}).get("captain", "on the bridge"))
        order = {k: v for k, v in args.items() if v not in (None, "")}
        order.update(side="astra", by="xo" if ("XO has the conn" in cap or cap.startswith("asleep")) else "captain")
        res = await self._war_execute("group_order", order, order["by"])
        if res.get("ok"):
            self.war.captain_ordered(str(args.get("group", "")), str(res.get("detail", "")))
        return res

    def _war_look(self, state: dict[str, Any]) -> None:
        """The war minds read the new ship state: the story's pulse, the commanders' look (they start the pulses that are due), the XO's board of the
        groups. A defect in them must never cut the crew off from the ship."""
        if self.aftermath.active:
            return                                  # (the Aquila is lost: the war's commanders wait for the new command; the story has the floor)
        try:
            self.director.observe(state)
            self.war.feed(state)
            state["_fleet_board"] = self.war.fleet_board(state)
        except Exception:  # noqa: BLE001
            log.exception("the war minds could not read the ship state")
        if self.march_glue is not None:
            self.march_glue.feed(state)                   # (the March: the war beyond the Aquila's sky, joined to the one in it; a defect in it is logged there)
        try:
            self.flight.feed(state)                       # (the flight net looks at the state, and starts the pulse that is due)
        except Exception:  # noqa: BLE001
            log.exception("the flight net could not read the ship state")
        try:
            self.marines.feed(state)                      # (so does the marine net: the fight's picture, and the pulse that is due)
        except Exception:  # noqa: BLE001
            log.exception("the marine net could not read the ship state")

    def record_log(self, entry: str) -> None:
        """A captain's log entry: kept in Saved/Campaign/captains_log.md, noted for the director, acknowledged."""
        path = os.path.join(os.path.dirname(self.director.war.save_path), "captains_log.md")
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"- {time.strftime('%Y-%m-%d %H:%M')} · {self.director.war.current}: {entry}\n")
        except OSError:
            log.exception("could not write the captain's log")
        self.director.note(f"captain's log: {entry}")
        asyncio.create_task(self._ack_log(entry))
        log.info("captain's log: %s", entry)

    async def _ack_log(self, entry: str) -> None:
        if not (self.game and self.game.state):
            return
        try:
            await self.game.execute("log_entry", {"text": entry[:200]}, "captain")
        except Exception:  # noqa: BLE001
            log.warning("the game did not acknowledge the log entry")

    def _register_voice(self, key: str, name: str, voice: str) -> None:
        """A voice of the story (the board, whoever finds the pod, a captor): a name on the channel and a voice."""
        EXTERNAL_SPEAKERS[key] = (name, voice)

    def _register_field(self, persona: dict[str, Any]) -> None:
        """A world's field controller gets a name and a voice on the radio."""
        EXTERNAL_SPEAKERS[persona["key"]] = (f'{persona["name"]} ({persona["place"]})', persona["voice"])

    def _sector_for(self, world: str) -> dict[str, Any] | None:
        """The March's entry for the system whose main world this is (None: a world outside the charted March)."""
        w = (world or "").strip().lower()
        for s_ in self.director.war.systems.values():
            if str(s_.get("world", "")).lower() == w:
                return s_
        return None

    def _field_world(self, world: str) -> dict[str, Any] | None:
        """Tune the field control to the world Eagle is over (its persona: who answers there, if anyone)."""
        sec = self._sector_for(world)
        surf = ((self.game.state if self.game else None) or {}).get("surface") or {}
        kind = surf.get("kind") if str(surf.get("world", "")).lower() == world.lower() else ""
        return self.port.set_world(world, kind or (sec or {}).get("planet", ""), sec)

    async def _silent_field(self, world: str, delay: float, called: bool) -> None:
        """A world gone silent: nobody answers from its field; comms says so (and the story remembers)."""
        await asyncio.sleep(delay)
        text = (f"comms: the Captain called the field on {world} — no answer on any channel, only static"
                if called else f"comms: nothing from the field on {world} — no beacon, no traffic, no answer on any channel")
        self.director.note(f"the Captain flew down to {world}: its field is dark and silent")
        self.last_activity = time.monotonic()
        await self.turns.put(("\x00event:" + text, self.lang))

    async def _port_call(self, cue: str, delay: float) -> None:
        """The world's field control speaks up (after the entry's glow has faded, or as Eagle touches down)."""
        await asyncio.sleep(delay)
        try:
            await self.port.respond(cue, self.lang, self._battle_state(), self.director.war.brief(detail=False))
        except Exception:  # noqa: BLE001
            log.exception("port control failed")

    def _first_watch(self, text: str) -> str:
        """The player's very first watch on this machine: the XO's greeting also tells, once, in her own words, how the bridge takes the Captain's orders
        (a new player knows nothing of V, G and Tab; the help card waits on F1). Every other event goes as it is."""
        if not text.startswith("bridge: the Captain has just come onto the bridge"):
            return text
        flag = SAVED / "first_watch.done"
        try:
            if flag.exists():
                return text
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.write_text(time.strftime("%Y-%m-%d %H:%M"), encoding="utf-8")
        except OSError:
            return text
        return (text + " — this is the Captain's first watch aboard: in one more short line of her own, as a good XO does for a new captain, Serra also tells "
                "them how the bridge takes their orders: they speak to the crew holding V (or type with T), the orders wheel on G gives the commonest orders of "
                "a fight without a word, the datapad on Tab shows the ship at a glance")

    async def _fleet_news(self, text: str) -> None:
        """War news from elsewhere in the March reaches the bridge over the fleet net (comms relays it)."""
        self.last_activity = time.monotonic()
        await self.turns.put(("\x00event:comms: fleet net news — " + text, self.lang))
        await self._send_sector()          # owners and threats changed: the holo table follows

    async def _send_sector(self) -> None:
        """The game learns the March: gate links, the look of each system, the plot for the holo table."""
        try:
            res = await self.game.execute("sector", self.director.war.game_payload(), "director")
            log.info("sector sent to the game: %s", res.get("detail", res))
        except Exception:  # noqa: BLE001
            log.exception("could not send the sector")

    async def _director_command(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if not (self.game and self.game.state):
            return {"ok": False, "detail": "no game"}
        return await self.game.execute(name, args, "director")

    def _register_commander(self, contact: str, persona: dict[str, Any]) -> None:
        key = self.enemy.register(contact, persona)
        EXTERNAL_SPEAKERS[key] = (f'{persona.get("name")} ({persona.get("ship")})', persona.get("voice", "stuart_bell"))
        log.info("new enemy commander %s on %s: %s", persona.get("name"), contact, persona.get("bio", "")[:120])

    async def _enemy_command(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        ship = self.game if (self.game and self.game.state) else None
        if ship is None:
            return {"ok": True, "detail": "(no game)"}
        if name == "enemy_order":
            who = COMMANDERS.get(self.enemy.contact, {}).get("name", "the Mandate commander")
            self.director.note(f"{who} decided: {args.get('order')} ({args.get('reason', '')})")
        return await ship.execute(name, args, self.enemy.speaker)

    def _visit_ctx(self) -> dict[str, Any]:
        """What the story knows when it decides whether an officer comes to the Captain's quarters."""
        return {"events": list(self.game.events)[-12:] if self.game else [],
                "campaign": [c for c in self.director.campaign if not c.startswith("captain's log:")],
                "mood": self.director.mood, "bonds": "; ".join(self.director.bonds_lines())}

    def _battle_state(self) -> dict[str, Any]:
        st = dict(self.game.state) if (self.game and self.game.state) else dict(self.local.snapshot())
        st["_events"] = (self.game.events if self.game else [])[-8:]
        return st

    QUIET_TOPICS = [
        "where they grew up and who waits for them there", "a memory of the Long Night their family still tells",
        "the Aquila's quirks as a brand-new ship (a hatch that sticks, the coffee, the smell of new wiring)",
        "the pilots of Alpha and Bravo and their superstitions", "the Teal Veil outside the window",
        "what they think the Mandate wants, and whether they understand it", "a letter or message from home",
        "the last shore leave on New Ravenna", "an old navy story about the 7th Fleet", "food in the mess",
        "what they will do when the war is over", "the strange calm of watching the plot when nothing moves"]

    async def quiet_moments(self) -> None:
        """When the bridge has been quiet for a while (no fight, nobody talking), two officers exchange a line or two."""
        import random
        last_chat = time.monotonic()
        while True:
            await asyncio.sleep(10)
            st = self.game.state if (self.game and self.game.state) else None
            if not st or not self.clients or st.get("abandon") or self.aftermath.active:
                continue
            idle = time.monotonic() - max(self.last_activity, self.voice.busy_until)
            hostile = any(str(c.get("status", "")).startswith("hostile") and "retreating" not in str(c.get("status", ""))
                          for c in st.get("contacts", []) or [])
            if hostile or st.get("alert") == "red" or idle < random.uniform(100, 160) or time.monotonic() - last_chat < 240:
                continue
            if not str(st.get("captain", "on the bridge")).startswith("on the bridge"):
                continue              # bridge talk needs the Captain on the bridge (the Mess, the Medbay, a Falcon have their own)
            last_chat = time.monotonic()
            pair = random.sample(["xo", "helm", "ops", "tactical", "comms", "sensors", "engineering", "flight"], 2)
            topic = random.choice(self.QUIET_TOPICS)
            if self.director.mood and random.random() < 0.35:   # what weighs on them now surfaces in the quiet
                topic = f"what is on their minds now (the mood aboard: {self.director.mood})"
            fallen = str(st.get("casualties", "")).split("the fallen: ", 1)
            if len(fallen) == 2 and random.random() < 0.5:   # every loss has a name: they remember them
                who = fallen[1].split("), ")[0].rstrip(")") + ")"
                topic = f"{who}, who was killed aboard: what they were like, something they said or did"
                pair = ["xo", random.choice(["ops", "tactical", "flight", "engineering"])]
            # now and then one of them turns to the Captain instead: something personal, from what they remember of
            # the Captain and how they stand (memory.py, the bonds) — a question, a thanks, a doubt; the Captain answers
            mems = self.memory.lines()
            personal = random.random() < (0.45 if (mems or self.director.bonds) else 0.2) and "Captain's quarters" not in str(st.get("captain", ""))
            # news from home not yet told: that officer brings it to the Captain first
            untold = next((h for h in self.director.home if not h.get("told") and h.get("officer") in CREW), None)
            if untold and "Captain's quarters" not in str(st.get("captain", "")) and random.random() < 0.7:
                untold["told"] = True
                self.director.save()
                self.voice.low_priority = True
                try:
                    t = await self._chatter(
                        "bridge: a quiet moment on watch", self.lang,
                        ask=(f"A quiet moment. {untold['officer']} turns to the Captain, off the record: news from home has "
                             f"reached them ({untold['news']}). In one or two short human lines, in character, they tell the "
                             "Captain — as much as they want to say; it invites an answer. Only speak, only that officer."))
                    log.info("news from home told (%s): %s", untold["officer"], " | ".join(f"{s}: {x}" for s, x in t.lines))
                finally:
                    self.voice.low_priority = False
                continue
            self.voice.chatter = True             # (small talk: the lowest priority, dropped when the Captain speaks)
            try:
                if personal:
                    who = random.choice([k for k in ("xo", "helm", "ops", "tactical", "comms", "sensors", "engineering", "flight")
                                         if k in mems or k in self.director.bonds] or ["xo", "helm", "sensors"])
                    t = await self._chatter(
                        f"bridge: a quiet moment on watch", self.lang,
                        ask=(f"A quiet moment. {who} turns to the Captain, off the record, with one short personal line: "
                             "something that officer has been meaning to say or ask — from what they remember of the Captain "
                             "and of their conversations, from how they stand with the Captain, or from what the ship has "
                             "lived through (a question about someone the Captain spoke of, a promise, a thanks, a doubt "
                             "about an order, something about themselves). One line, human and specific, never a report; it "
                             "invites an answer. Only speak, only that officer."))
                    log.info("personal moment (%s): %s", who, " | ".join(f"{s}: {x}" for s, x in t.lines))
                else:
                    t = await self._chatter(
                        f"bridge: a quiet moment on watch", self.lang,
                        ask=(f"A quiet moment: {pair[0]} and {pair[1]} exchange one or two short, natural lines about {topic}, "
                             "in character, knowing the Captain can hear (they may include the Captain with a glance). No orders, "
                             "no reports, no tools except speak; at most two lines in total."))
                    log.info("quiet moment (%s, %s): %s", pair[0], pair[1], " | ".join(f"{s}: {x}" for s, x in t.lines))
            finally:
                self.voice.chatter = False

    async def idle_exit(self) -> None:
        """A mind nobody has talked to for 20 minutes goes (a game that crashed or quit does not leave it running)."""
        alone_since = time.monotonic()
        while True:
            await asyncio.sleep(30)
            if self.clients:
                alone_since = time.monotonic()
            elif time.monotonic() - alone_since > 1200:
                log.info("no game for 20 minutes: the mind stops")
                self.stt.stop_server()
                os._exit(0)

    async def _after_action(self, outcome: str, orders: list[str]) -> None:
        """The fight is over: once the reports are out, the XO gives the Captain a short after-action — the outcome and
        its cost, what worked, one honest lesson — from what really happened and what the Captain ordered."""
        await asyncio.sleep(10)
        if self.aftermath.active or not self.clients or ((self.game.state if self.game else None) or {}).get("abandon"):
            return
        said = "; ".join(o.split(" => ")[0].strip(' -"') for o in orders[-8:]) or "(none: the crew fought it on its own)"
        await self.turns.put(("\x00event:bridge: after-action — " + outcome[:320] + ". The Captain's orders in this fight: " + said[:600],
                              self.lang))

    async def flight_controller(self) -> None:
        """The Captain in a Falcon is never alone: Price, the flight controller, calls the picture around the Falcon
        over the radio — a new threat closing at once, otherwise every half minute or so while there is one."""
        last_t, last_sig = 0.0, ""
        while True:
            await asyncio.sleep(3)
            st = self.game.state if (self.game and self.game.state) else None
            cap = str((st or {}).get("captain", ""))
            if not st or not self.clients or not cap.startswith("flying a Falcon"):
                last_sig = ""
                continue
            m = _re.search(r"around the Falcon: (.*?); the XO has the conn", cap)
            pic = m.group(1) if m else ""
            sig = _re.sub(r"[\d.]+ km|\d+ o'clock \w+", "", pic)     # who is out there, not where exactly
            now = time.monotonic()
            urgent = bool(pic) and sig != last_sig and "closing" in pic
            if now - self.captain_t < 6 or not pic or (not urgent and now - last_t < 35):
                continue
            last_t, last_sig = now, sig
            await self.turns.put(("\x00event:flight: controller call — the Captain is " + cap, self.lang))

    async def standing_sync(self) -> None:
        """The Captain's datapad lists the standing orders in force: the game gets them whenever they change (and
        again whenever it reconnects)."""
        sent: tuple[Any, str] = (None, "")
        while True:
            await asyncio.sleep(3)
            game = self.game if (self.game and self.game.state) else None
            if not game:
                continue
            now = json.dumps(self.agent.standing, ensure_ascii=False)
            if sent == (game, now):
                continue
            try:
                await game.execute("standing_orders", {"orders": [f"{o['department']}: {o['order']}" for o in self.agent.standing]},
                                   "captain")
                sent = (game, now)                   # (a game that does not know the command is not asked again)
            except Exception:  # noqa: BLE001
                log.exception("could not send the standing orders")

    def _channel_opened(self, party: str) -> None:
        """A channel is open with someone outside the ship (the Captain's hail, theirs: `transmission:`, or one the game says is open when he speaks). The flight net and the marine net
        have their own rules (a Falcon's cockpit, a boarding); this is the fleet's and the ships'."""
        p = str(party or "").strip()
        p = "fleet" if p.lower() == "fleet" else p.upper()
        if not p or p.lower() in FLIGHT_ALIASES or p.lower() in ("marines", "marine", "marine_net"):
            return
        if p != self._channel:
            self._channel = p
            self.exchange.opened(p)

    async def channel_watch(self) -> None:
        """A channel opens for an exchange and closes when it is over, or by the Captain's word: when nothing has passed on it for CHANNEL_IDLE_S (they have not spoken, he has not
        spoken to them), Communications closes it, silently, with a note on the comms log. He can open it again with a word."""
        while True:
            await asyncio.sleep(5)
            party = self._channel
            game = self.game if (self.game and self.game.state) else None
            if not party or game is None or not self.clients:
                continue
            idle = self.exchange.idle_s(party)
            if idle is None or idle < CHANNEL_IDLE_S or time.monotonic() - self.captain_t < 10.0 or self.voice.held or self.voice.speaking_s() > 0.0:
                continue
            self._channel = ""
            if self.enemy.open and str(self.enemy.contact).upper() == party:
                self.enemy.open = False
            try:
                res = await game.execute("end_transmission", {}, "comms", direct=True)
            except Exception:  # noqa: BLE001
                log.exception("the idle channel with %s could not be closed", party)
                continue
            who = self._party_names().get(party, party)
            log.info("channel with %s closed: nothing passed on it for %.0f s (%s)", party, idle, res.get("detail", ""))
            self.nets.console_log("comms", f"Channel with {who} closed: exchange over ({idle:.0f} s of silence)", kind="notice", by="comms")

    async def delegation_sync(self) -> None:
        """The game starts every launch with `auto` on every console and forgets what the Captain said: what he set (or, in a new campaign, what commits the ship waiting for his
        go) is put back as the XO's own command, silently, once the campaign is chosen and the consoles are on line (delegation.py)."""
        while True:
            await asyncio.sleep(2)
            game = self.game if (self.game and self.game.state) else None
            if game is None or not self.clients:
                continue
            for station, level in self.delegation.pending(game.state):
                self.delegation.asked(station, level)             # (a level the game refuses is not asked again until it changes)
                try:
                    res = await game.execute("station", self.delegation.wire(station, level), "xo", direct=True)
                except Exception:  # noqa: BLE001
                    log.exception("the %s console's delegation could not be put back", station)
                    continue
                log.info("delegation: %s on %s (%s)", level, station, res.get("detail", ""))

    async def tactical_watch(self) -> None:
        """In a fight the crew watches the big picture for the Captain: when something important is going wrong
        (weapons assigned out of reach while the helm chases another contact, a friendly ship dying, shields failing,
        hostiles close and untouched, magazines running dry) the XO or the officer concerned says so, once, with a
        recommendation. The problems are found here, from the telemetry; the officer only phrases them."""
        last_t, last_key = 0.0, ""
        pictures: set[str] = set()                  # blind pictures already put to the Captain (once each)
        while True:
            await asyncio.sleep(2)                       # (the old advisor's own timers are all 40 s and more)
            st = self.game.state if (self.game and self.game.state) else None
            if not st or not self.clients or st.get("abandon") or self.aftermath.active:
                continue
            flags = tactical_flags(st)
            info = picture_flag(st)
            if info and info[0] not in pictures and len(flags) < 3:
                flags.append(info[1])
            now = time.monotonic()
            if st.get("stations"):
                # live consoles: the officers' initiative watch (initiative.py) answers for the advisor too — one check, one
                # voice — on its own adaptive cadence, never while the Captain speaks or is being answered
                busy = not self.turns.empty() or self.agent.busy() or self.voice.busy_s() > 3.0
                chk = self.watch.tick(st, now, flags, None, self.captain_t, busy)
                if chk is not None:
                    if info and info[1] in flags:
                        pictures.add(info[0])                 # (a blind picture is put to the Captain once)
                    log.info("watch check (%s): %s", "event" if chk.urgent else "periodic", chk.text[:200])
                    self._watch_check = chk
                    self.last_activity = now
                    await self.turns.put(("\x00event:" + chk.text, self.lang))
                continue
            # in a fight the bridge is never silent: only the Captain's own words hold the check back
            key = "|".join(sorted(f.split(":", 1)[0] for f in flags))
            # (the event queue itself waits for a gap in the voices before the officer speaks)
            if not flags or now - self.captain_t < 10 or now - last_t < 40 or (key == last_key and now - last_t < 100):
                continue
            last_t, last_key = now, key
            if info and info[1] in flags:
                pictures.add(info[0])
            log.info("tactical check: %s", flags)
            self.last_activity = now
            await self.turns.put(("\x00event:bridge: tactical check — " + "; ".join(flags), self.lang))

    async def mess_talk(self) -> None:
        """The Mess Hall is never silent while the Captain is there: people at the tables talk among themselves
        (mind/astra_mind/mess.py), in the pauses the Captain and the reports leave."""
        while True:
            await asyncio.sleep(4)
            st = self.game.state if (self.game and self.game.state) else None
            if not st or not self.clients:
                continue
            now = time.monotonic()
            ctx = {"events": list(self.game.events)[-8:] if self.game else [], "campaign": list(self.director.campaign),
                   "mood": self.director.mood, "bonds": "; ".join(self.director.bonds_lines()), "war": self.director.war.crew_view(),
                   "casualties": st.get("casualties", ""), "menu": (st.get("mess") or {}).get("menu", "")}
            await self.mess.tick(st, self.lang, ctx, quiet_s=now - max(self.captain_t, self.last_activity),
                                 voice_busy_s=self.voice.busy_s())

    async def story_watch(self) -> None:
        """The war never stalls: when nothing has moved the story for a long while (no fight, no transit under way),
        the director decides what happens — Rourke presses the Captain, or the war comes to the Aquila."""
        while True:
            await asyncio.sleep(15)
            st = self.game.state if (self.game and self.game.state) else None
            if not st or not self.clients or not self.director.campaign or self.director.busy or st.get("abandon") or self.aftermath.active:
                continue
            quiet = time.monotonic() - self.director.last_event_t
            hostile = any(str(c.get("status", "")).startswith("hostile") for c in st.get("contacts", []) or [])
            if hostile and not self.director.decisive and self.director.battle_due():
                # a long fight is looked in on: the war may bring reinforcements for either side, a call to talk, news — or nothing
                log.info("the director looks in on a fight that has lasted %.0f s", time.monotonic() - (self.director.fight_since or 0.0))
                asyncio.create_task(self.director.battle_pulse(self.lang, self._battle_state()))
                continue
            gate = str(st.get("janus_gate", ""))
            # (two and a half minutes of nothing is long in a war played for its fighting: the director is asked, and decides what the war does about it)
            if hostile or st.get("alert") == "red" or quiet < self.director.STALL_S or "under way" in gate or "lane" in gate:
                continue
            why = "the Captain has not acted on Fleet's transit orders" if "Fleet orders" in gate else "nothing has happened"
            log.info("story stalled for %.0f s: %s", quiet, why)
            asyncio.create_task(self.director.on_event(f"director: story stalled — {why} for {int(quiet // 60)} minutes",
                                                       self.lang, self._battle_state()))

    async def turn_worker(self) -> None:
        while True:
            text, lang, *rest = await self.turns.get()       # (the Captain's words carry the game's `context` as a third item)
            raw_ctx = rest[0] if rest else None
            try:
                self.agent.ship = self.game if (self.game and self.game.state) else self.local
                if text.startswith("\x00event:"):
                    # let the bridge fall quiet first (reports must not pile up behind the voices; a warning of danger waits for
                    # nobody), then coalesce: everything that happened meanwhile becomes one report turn; the Captain's words
                    # are never merged or delayed behind events
                    # (a warning of danger does not wait for the queue: only a moment for what came with it — a hit brings its breach,
                    # its fire and its wounded in the same instant — and for the line being said to end, URGENT_WAIT_S at most; one
                    # report turn for each of them was a flood of a dozen voices a minute in a big battle)
                    events = [text[len("\x00event:"):]]
                    when = [rest[1] if len(rest) > 1 else None]           # (the time each one arrived: see _TurnQueue)
                    pending = []
                    urgent = bool(_URGENT_EVENT.search(text))
                    t_in = asyncio.get_running_loop().time()
                    while True:
                        while not self.turns.empty():
                            nxt = self.turns.get_nowait()
                            if nxt[0].startswith("\x00event:"):
                                events.append(nxt[0][len("\x00event:"):])
                                when.append(nxt[3] if len(nxt) > 3 else None)
                                urgent = urgent or bool(_URGENT_EVENT.search(nxt[0]))
                            else:
                                pending.append(nxt)
                        now_l = asyncio.get_running_loop().time()
                        waited = now_l - t_in
                        paced = now_l - self._report_end >= (PICTURE_GAP_S if self._report_spoke else REPORT_GAP_S) or any(_presses(e) for e in events)
                        warned = not self._report_spoke or now_l - self._report_end >= URGENT_GAP_S or waited >= URGENT_WAIT_S + URGENT_GAP_S
                        if pending or (not urgent and ((self.voice.busy_s() <= 1.2 and not self.voice.held and paced) or waited >= ROUTINE_WAIT_S)) or \
                                (urgent and waited >= URGENT_GATHER_S and warned and (self.voice.speaking_s() < 0.8 or waited >= URGENT_WAIT_S)):
                            break
                        await asyncio.sleep(0.1)
                    for p in pending:
                        await self.turns.put(p)
                    if pending:
                        # the Captain spoke: answer first. The news stays in the state and the history; a warning of danger, or a call to him on a net, is told after his order
                        # (its officer says nothing if the order covered it): it is not lost to the gap between the news and the turn (0.6 s to 3 s), however his words fall
                        for e, w in zip(events, when):
                            if _outlives_the_captains_words(e):
                                await self.turns.put(("\x00event:" + e, self.lang, None, w))
                        continue
                    transmissions = [e for e in events if e.startswith("transmission:")]
                    keep = [i for i, e in enumerate(events) if not e.startswith("transmission:")]
                    events, when = [events[i] for i in keep], [when[i] for i in keep]
                    for tr in transmissions:
                        # "transmission: T-22 — why": that captain calls the Aquila (arrival, succession, broken ceasefire)
                        m = _re.match(r"transmission:\s*(T-\d+)\s*—\s*(.*)", tr)
                        if m and m.group(1) not in COMMANDERS:
                            # nobody gave this captain a mind yet: a Mandate officer with the ship's name on the call sign
                            ship = _re.search(r"aboard the ([\w' -]+)", m.group(2)) or _re.search(r"— the ([\w' -]+?) \(", m.group(2))
                            drawn = drawn_mandate_officer(m.group(1), ship.group(1) if ship else "")
                            self._register_commander(m.group(1), {**drawn, "ship": f"the {ship.group(1) if ship else 'Mandate warship'}"})
                        if m and self.enemy.open_channel(m.group(1)):
                            written = await self.voice.preemptible(self.enemy.respond(
                                f"[Situation: {m.group(2)}. You are the one opening this channel: make "
                                "your transmission to the Aquila's captain.]", self.lang, self._battle_state()))
                            if written is None:      # the Captain took the floor while the message was being written: it is written after his order
                                await self.turns.put(("\x00event:" + tr, self.lang))
                    # news that waited too long for a quiet bridge is no news any more: when even the newest of it is old, nothing is reported
                    # (it stays in the ship's state); in a fresh batch the old items say how old they are, so the crew speaks of them in the
                    # past or not at all
                    if not events:
                        continue
                    now_t = asyncio.get_running_loop().time()
                    newest = max((w for w in when if w is not None), default=None)
                    # (news that waited for a quiet bridge still goes to the officers, with its age: whether it is worth saying now is
                    # theirs to judge — docs/ARCHITETTURA.md §1bis)
                    fresh_events = list(events)
                    events = [e if w is None or now_t - w <= REPORT_LATE_S else f"{e} [happened {now_t - w:.0f} s ago]" for e, w in zip(events, when)]
                    self.voice.low_priority = True
                    self.voice.report_since = newest              # (a report is worth saying for a few seconds after its news; see speech.py)
                    if any(_URGENT_EVENT.search(e) for e in events):
                        self.voice.urgent = True          # (danger now: it does not wait behind small talk or a routine report)
                    try:
                        ask = FLIGHT_CALL_ASK if any(e.startswith("flight: controller call") for e in events) else \
                            AFTER_ACTION_ASK if any(e.startswith("bridge: after-action") for e in events) else \
                            TACTICAL_ASK if any(e.startswith("bridge: tactical check") for e in events) else \
                            VISIT_ASK if any("has come to the Captain's quarters in person" in e for e in events) else None
                        if ask is None and any(e.startswith(NET_EVENT) for e in events):
                            ask = net_ask(events)                          # (net traffic among the news: the listener's doctrine, alone if the news is only traffic)
                        elif ask is None and system_calls_only(events):
                            ask = SYSTEM_CALL_ASK                          # (a distress call, the fleet net's news: Communications', the first told, the others logged)
                        t = await self._event_turn(events, ask)
                    finally:
                        self.voice.low_priority = False
                        self.voice.report_since = None
                    log.info("event turn %.2fs: %s", t.t_end, " | ".join(f"{s}: {x}" for s, x in t.lines) or "(no report)")
                    self._report_end, self._report_spoke = asyncio.get_running_loop().time(), bool(t.lines)      # (the picture's pace: PICTURE_GAP_S)
                    if getattr(t, "cancelled", False) and not t.lines:
                        # the Captain took the floor while a warning of danger was being written: it is reported after his order (the crew
                        # says nothing if what he ordered already covered it)
                        for e in [e for e in fresh_events if _outlives_the_captains_words(e)]:
                            await self.turns.put(("\x00event:" + e, self.lang))
                    continue
                self.voice.captain_turn_begin()               # what is said from here to the end of this turn answers the Captain
                dropped = self.voice.drop_low_priority()      # the Captain speaks: small talk is no longer worth saying
                if dropped:
                    log.info("captain speaks: %d unspoken small-talk lines dropped", dropped)
                if not self.follow_voice:
                    lang = self.lang                          # (the settings fix the crew's language: they answer in it whatever he speaks)
                if lang != self.lang:
                    if hasattr(self.tts, "prepare"):
                        asyncio.create_task(self.tts.prepare(lang, [o.voice for o in CREW.values()]))   # the crew will answer in it
                    self.lang = lang
                    self.lang_file.parent.mkdir(parents=True, exist_ok=True)
                    self.lang_file.write_text(lang, encoding="utf-8")
                gm = _GM_ADDRESS.match(text)
                if gm and len(text) > gm.end() + 3 and not self.aftermath.active:
                    # game master mode: the wish goes to the director, who makes it fit the world
                    log.info("game master request: %s", text)
                    asyncio.create_task(self.director.gm_request(text[gm.end():].strip(), lang, self._battle_state()))
                    continue
                if self.aftermath.wants():
                    # before the Board of Inquiry, or a Mandate officer: the Captain answers them, not the crew
                    await self.aftermath.captain_says(text)
                    continue
                entry = captains_log_entry(text)
                if entry is not None:
                    # the Captain dictates the log: recorded (a chirp from the console), remembered by the story
                    self.record_log(entry)
                    continue
                st_now = self.game.state if (self.game and self.game.state) else {}
                surf = st_now.get("surface") or {}
                if surf.get("captain_here") and surf.get("world"):
                    persona = self._field_world(surf["world"])
                    if for_field(text, persona or {"world": surf["world"]}):
                        if persona is None:
                            asyncio.create_task(self._silent_field(surf["world"], 2.0, True))
                            continue
                        self.director.note(f"the Captain to {persona['place']}: {text}")
                        await self.port.respond(f"[Eagle on the radio]: {text}", lang, self._battle_state(), self.director.war.brief(detail=False))
                        continue
                await self._captain_turn(text, lang, raw_ctx)      # (the router, the crew's turn, the party's answer)
            except Exception:  # noqa: BLE001
                log.exception("turn failed")
            finally:
                self.voice.captain_turn_end()             # (no line came out of the Captain's turn: his floor is released)

    # ---------------------------------------------------------------------------------------------- the Captain's words
    async def _crew_say(self, speaker: str, text: str, lang: str, tone: str) -> int:
        """A line of the crew's: heard by the memory keeper (an officer remembers what passed with the Captain); when its turn comes
        after a wait (or after being cut off), its officer thinks it again first."""
        if speaker in CREW:
            self.memory.hear(speaker, text)
        if speaker == "flight":
            self.flight.heard("Price (Flight Control)", text)       # (the flight net hears the controller: its people do not say again what he said)
        if speaker in CREW:
            self.marines.heard(f"the bridge: {CREW[speaker].title} ({CREW[speaker].role})", text)     # (and the marines hear the bridge in a boarding)

        async def rethink(t: str, waited: float, cut_after: str) -> str | None:
            return await self.agent.rethink(speaker, t, waited, cut_after, lang)
        return await self.voice.say(speaker, text, lang, tone, rethink=rethink)

    def _party_names(self) -> dict[str, str]:
        names = {cid: f'{c["name"]} ({c["ship"]})' for cid, c in COMMANDERS.items()}
        # the fleet channel reaches the admiral and every allied ship: comms knows which ships those are (the plot shows them)
        st = self.game.state if (self.game and self.game.state) else {}
        allies = [str(c.get("name") or c.get("id")).split(" (")[0] for c in st.get("contacts", [])
                  if str(c.get("status", "")).startswith("friendly") and c.get("name")]
        names["fleet"] = f'{ADMIRAL["name"]} and the 7th Fleet' + (f' ({", ".join(allies)})' if allies else "")
        names[FLIGHT_PARTY] = self.flight.net_name()
        names[MARINES_PARTY] = self.marines.net_name()
        return names

    def _captain_speaks(self) -> None:
        """The Captain has priority over everything: whatever the crew was doing (a report, a watch check, a chat) stops now,
        and the reports still waiting to be voiced are dropped."""
        n = self.agent.preempt() + self.npcs.preempt() + self.flight.preempt() + self.xfer.preempt() + self.marines.preempt()
        drop = getattr(self.voice, "drop_low_priority", None)        # (the voice module's side: it may give the Captain more than this)
        dropped = drop() if callable(drop) else 0
        hook = getattr(self.voice, "captain_speaks", None)           # the hook for cutting the line being spoken, if the voice has one
        if callable(hook):
            hook()
        if n or dropped:
            log.info("the Captain speaks: %d turn(s) cut off, %d unspoken line(s) dropped", n, dropped)

    def _can_answer(self, party: str) -> bool:
        """Someone answers on this channel: the admiral (and the allied captains on the fleet net), an allied captain with a mind, or a Mandate captain
        with a mind who is still alive."""
        return party == "fleet" or (party == FLIGHT_PARTY and self.flight.can_answer()) or (party == MARINES_PARTY and self.marines.can_answer()) or self.war.can_answer(party) \
            or (party in COMMANDERS and party not in self.enemy.dead)

    async def _to_party(self, party: str, words: str, lang: str, to: str = "") -> None:
        """What the Captain said TO the party on the channel goes out: the enemy commander answers, the admiral, or the allied captains (each judges
        whether the words were for them). On the fleet net `to` is whom the router found them for: only the admiral, only one ship's captain, or everyone."""
        self.exchange.said(party)
        if party == FLIGHT_PARTY:
            self.flight.captain_to_net(words, lang)                # (the CAG, the leaders, the wingmen, the Chief: whoever it was for answers)
            return
        if party == MARINES_PARTY:
            self.marines.captain_to_net(words, lang)               # (the Major, the squad leaders: whoever it was for answers)
            return
        if party == "fleet":
            who = " ".join((to or "all").lower().split())
            if who in _FOR_THE_ADMIRAL:
                await self.director.admiral_reply(words, lang, self._battle_state())      # (only Rourke: the allied captains are not woken for words to the admiral)
                return
            if who not in _FOR_ALL:
                if self.war.captain_to_fleet(words, lang, to=who):
                    self.war.kick()                                # (one ship's captain, or the group that holds her: Rourke does not answer words for a ship)
                    return
                log.info("fleet net: nobody answers to %r, the words go to everyone", who)
            self.war.captain_to_fleet(words, lang)
            self.war.kick()
            await self.director.admiral_reply(words, lang, self._battle_state())
            return
        if self.war.can_answer(party):
            self.war.captain_to_fleet(words, lang, to=party)
            self.war.kick()
            return
        if (not self.enemy.open or self.enemy.contact != party) and not self.enemy.open_channel(party):
            log.info("words for %s, but nobody answers on that channel: %s", party, words[:80])
            return
        who = COMMANDERS.get(party, {}).get("name", "the Mandate commander")
        self.director.note(f"the Captain to {who} over the channel: {words}")
        await self.enemy.respond(f"[The ASTRA captain, over the open channel]: {words}", lang, self._battle_state())

    async def _captain_turn(self, text: str, lang: str, raw_ctx: dict[str, Any] | None) -> None:
        """The Captain's words. Everyone in the room hears them: the crew's turn starts at once on all of them, and each officer judges
        whether they were meant for them. With a channel open, the comms officer's call (router.for_party, a small fast model) decides
        meanwhile what goes out on it, and whoever is there answers what reached them."""
        st = self.game.state if (self.game and self.game.state) else {}
        # the crew aboard within earshot (the game's life, npc.py): they hear the words too and judge for themselves; the officers' turn
        # waits for their word (the gate) and stays out of it when one of them answered
        people = self.npcs.listeners(raw_ctx, st)
        gate = None
        if people:
            gate = asyncio.get_running_loop().create_future()
            world = {"state": st, "war": self.director.war.crew_view(), "mood": self.director.mood, "clock": (st.get("life") or {}).get("clock")}
            where = "at " + (badge_of_raw(raw_ctx) or "somewhere aboard") + " (his badge, live: it beats anything remembered)"
            if lift := parse_lift((raw_ctx or {}).get("lift")):
                # in a lift car with them: the ship's computer runs the lift, so what asks for a ride is its to answer (tools.lift_tool), never a rider's
                where += (f", inside {lift.name}, a lift car: the ship's computer takes him wherever he asks, a deck, a place or a section, \"down\", \"one up\", in any language, so "
                          "words that ask for a ride are for the computer and the people aboard say nothing to them (unless he speaks to one of them)")
            asyncio.create_task(self.npcs.hear(text, lang, people, world, gate, where))
            if str((raw_ctx or {}).get("facing", "")).startswith("npc"):
                faced = next((p.name for p in people if p.id == raw_ctx["facing"]), "a crew member")
                raw_ctx = {**raw_ctx, "facing": faced}
        # the Chief of the Transporter Room, when she is within earshot: a person with her own mind, the words for her are hers to answer (the bridge's turn waits for her verdict too)
        self.xfer.captain_said(text, lang)
        if not self.xfer.disabled and self.xfer.in_earshot(raw_ctx):
            gate_x = asyncio.get_running_loop().create_future()
            place_x = str((raw_ctx or {}).get("place") or "")
            where_x = "in the Transporter Room" if "transporter" in place_x else "at " + (badge_of_raw(raw_ctx) or place_x or "somewhere aboard") + " (his badge, live: it beats anything remembered)"
            asyncio.create_task(self.xfer.hear(text, lang, gate_x, where_x))
            gate = gate_x if gate is None else _both(gate, gate_x)
            if self.xfer.facing(raw_ctx):
                raw_ctx = {**(raw_ctx or {}), "facing": XFER_TITLE}
        ctx = parse_context(raw_ctx, st, self.enemy, self._party_names(), self.exchange,
                            flight_net=self.flight.net_live(st, self.exchange.ago(self.exchange._heard, FLIGHT_PARTY)),
                            marine_net=self.marines.net_live(st, self.exchange.ago(self.exchange._heard, MARINES_PARTY)) and not _flying(st))
        if ctx.channel is not None and ctx.channel.open and ctx.channel.kind in ("enemy", "fleet", "ally"):
            self._channel_opened(ctx.channel.party)           # (open when he speaks, whoever opened it: it closes with the exchange)
        self.memory.hear("Captain", text)
        r = router_mod.Route()
        party_task = None
        ch = ctx.channel
        note = self.npcs.note_for_crew(people)
        if ch and ch.live and ch.kind in _NETS and self._can_answer(ch.party):
            # a net of people (the flight net, the marine net): comms decides first (a fraction of a second), and the officers are told what went out on it, so that nobody on the
            # bridge says it again (Price does not relay a pilot's order, Comms does not narrate it): the rest of the Captain's words, for the bridge, is theirs as ever
            label, who, example, included = _NETS[ch.kind]
            r = await router_mod.for_party(self.llm, text, ctx)
            log.info("%s live: out on it (%s, %.0f ms): %r", label, r.how, r.ms, r.external[:80])
            if r.external:
                await self._to_party(r.party, r.external, lang, r.to)
                if " ".join(r.external.split()) == " ".join(text.split()):
                    # every word of it went out on the net, verbatim: there is nothing left for the bridge, and the crew's turn (a model call to say nothing) is not needed
                    # (the officers see the order in the console and hear the answer on the radio, in their events)
                    log.info("the Captain's words went out on the %s whole: no turn for the bridge", label)
                    return
                note = (note + " " if note else "") + (f"The Captain's words «{r.external}» went out on the {label}: {who} answer them and carry out "
                                                       "the orders in them. That part is theirs: say and do nothing about it — no acknowledgement, no relay, "
                                                       f"no \"{example}\" ({included} included). If the Captain also said something meant for the bridge, that is yours; otherwise stay silent.")
            turn_task = asyncio.create_task(self.agent.handle(text, lang, ctx, note=note, gate=gate))
        else:
            turn_task = asyncio.create_task(self.agent.handle(text, lang, ctx, note=note, gate=gate))
            if ch and ch.live and self._can_answer(ch.party):
                r = await router_mod.for_party(self.llm, text, ctx)
                log.info("channel open with %s: out on it (%s, %.0f ms)%s: %r", ch.party, r.how, r.ms, f", for {r.to}" if r.to else "", r.external[:80])
                if r.external:
                    party_task = asyncio.create_task(self._to_party(r.party, r.external, lang, r.to))
        t = await turn_task
        if party_task is not None:
            await party_task
        if t is None or (t.cancelled and not t.actions):
            return
        self.style.captain_order(text, t.actions)
        asyncio.create_task(self.memory.maybe_read())
        for name, args_, res in t.actions:
            if name == "hail" and res.get("ok"):
                self._channel_opened(str(args_.get("contact_id", "")))
            elif name == "end_transmission":
                self._channel = ""
            if self.delegation.note_call(name, args_, res):
                log.info("delegation kept: %s", ", ".join(f"{k} {v}" for k, v in sorted(self.delegation.levels.items())))    # (his word: it stays with the campaign)
            if name == "end_transmission":
                if ctx.channel is not None and ctx.channel.kind == "flight":
                    self.flight.close_net()                       # (the channel Comms closes is the one that was live: the flight net)
                else:
                    self.enemy.open = False
            if name == "hail" and res.get("ok") and str(args_.get("contact_id", "")).strip().lower() in FLIGHT_ALIASES:
                self.flight.captain_to_net(str(args_.get("message", "")), lang, src="hail")     # (Comms opened the net: what the Captain asked it to say goes out on it)
            elif name == "hail" and res.get("ok") and str(args_.get("contact_id", "")).lower() == "fleet":
                self.war.captain_to_fleet(str(args_.get("message", "")), lang)
                self.war.kick()
                await self.director.admiral_reply(str(args_.get("message", "")), lang, self._battle_state())
            elif name == "hail" and res.get("ok") and self.war.can_answer(str(args_.get("contact_id", "")).upper()):
                self.war.captain_to_fleet(str(args_.get("message", "")), lang, to=str(args_.get("contact_id", "")).upper())
                self.war.kick()
            # (open_channel knows who has a commander to answer: a contact not yet classified, a decoy, a
            # friendly ship never do)
            if name == "hail" and res.get("ok") and str(args_.get("contact_id", "")).lower() != "fleet" \
                    and self.enemy.open_channel(str(args_.get("contact_id", "")).upper()):
                await self.enemy.respond(f"[The ASTRA ship hails you. Their message: {args_.get('message', '')}]",
                                         lang, self._battle_state())
        await self._sink("json", {"type": "turn_end", "first_line_s": t.t_first_line, "total_s": round(t.t_end, 3),
                                  "cost": t.cost, "actions": [[n, a, r_] for n, a, r_ in t.actions], "error": t.error,
                                  "route": {"to_party": r.external, "how": r.how, "ms": round(r.ms, 1)}})
        log.info("turn %.2fs (first line %.2fs) cost $%.5f: %s", t.t_end, t.t_first_line or -1, t.cost,
                 " | ".join(f"{s}: {x}" for s, x in t.lines))

    async def _chatter(self, event: str, lang: str, ask: str):
        """A quiet moment's talk: its own model role (small and cheap), a compact prompt that asks for two or three lines, only `speak`."""
        system = chatter_system(lang, self.director.mood, self.memory.lines(), "; ".join(self.director.bonds_lines()), self.director.home_lines(),
                                list(self.director.campaign), list(self.game.events)[-5:] if self.game else [])
        return await self.agent.handle_event(event, lang, ask=ask, role="chatter", system=system, history_turns=2, speak_only=True)

    async def _event_turn(self, events: list[str], ask: str | None):
        """A report turn (or the officers' watch check: its own compact prompt, its own cheaper model, only the last few exchanges)."""
        if any(e.startswith("bridge: watch") for e in events):
            st = self.game.state if (self.game and self.game.state) else self.local.snapshot()
            t = await self.agent.handle_event(" | ".join(events), self.lang, ask=watch_ask(self.lang), role="watch", history_turns=4,
                                              system=watch_system(self.lang, st, self.agent.standing_lines(), self.agent.style(),
                                                                  recent_orders(self.agent.history)))
            chk = getattr(self, "_watch_check", None)
            if chk is not None:
                self.watch.ran(chk, bool(t.lines or t.actions))
            return t
        # a bridge already talking over itself (a fleet battle: queued lines waited 75-175 s) is told so: what the officers
        # add is theirs to judge — docs/ARCHITETTURA.md §1bis
        busy = self.voice.busy_s()
        note = (f" [the bridge is busy: about {busy:.0f} s of speech is still waiting to be said — only what the Captain must hear now, "
                "in one short line, or nothing]") if busy > 12.0 else ""
        return await self.agent.handle_event(" | ".join(events) + note, self.lang, ask=ask)

    async def _wheel_turn(self, event: str) -> None:
        """An order the Captain gave from his command wheel, without a word (the game has carried it out): the officer at that station acknowledges it like a spoken one. It is not
        news: it does not wait for a quiet bridge or for other news to join it, what is said in it is an answer to the Captain (it goes first and is never lost), and the turn can
        only `speak` (the console did what was ordered: nobody orders it again). Several orders in a few seconds are several turns, each acknowledged by its own officer."""
        try:
            self.agent.ship = self.game if (self.game and self.game.state) else self.local
            self.voice.captain_turn_begin()
            t = await self.agent.handle_event(event, self.lang, ask=WHEEL_ASK, speak_only=True)
            log.info("command wheel turn %.2fs: %s", t.t_end, " | ".join(f"{s}: {x}" for s, x in t.lines) or "(no acknowledgement)")
        except Exception:  # noqa: BLE001
            log.exception("an order from the command wheel could not be acknowledged")
        finally:
            self.voice.captain_turn_end()

    async def handle_client(self, ws) -> None:  # noqa: ANN001
        self.clients.add(ws)
        self.voice.muted = False
        self.game = GameShip(lambda m: ws.send(json.dumps(m, ensure_ascii=False)),
                             intercept={"fleet_request": self._fleet_request, "group_order": self._captain_group_order, "hail": self._hail_flight,
                                        "transporter": self._xfer_order})
        await ws.send(json.dumps({"type": "status", "crew": {k: v.title for k, v in CREW.items()}, "rate": self.tts.sample_rate,
                                  "voice": 2}))       # voice protocol 2: docs/protocollo_voce.md (cancel, hold_s, floor, line_dropped)
        log.info("game connected")
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    continue
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError as e:
                    # one bad message (a NaN in the snapshot...) must not cut the crew off from the ship
                    log.warning("bad JSON from the game (%s): ...%s...", e, raw[max(0, e.pos - 160): e.pos + 60].replace("\n", " "))
                    continue
                kind = msg.get("type")
                if kind == "hello":
                    # a new game session: the crew starts a fresh conversation (the ship state is new too), in the language of the settings
                    self._apply_language(msg)
                    if getattr(self.llm, "state", "ok") != "ok":
                        await self._sink("json", {"type": "ai_status", "state": getattr(self.llm, "state", "ok"), "detail": ""})
                    self.agent.history.clear()
                    self.enemy.reset()
                    self.war.reset()
                    self.flight.reset()
                    self.xfer.reset()
                    self.marines.reset()
                    self.port.reset()
                    if self.march_glue is not None:
                        self.march_glue.stop()                # (the war waits for the Captain's choice)
                    await self.voice.clear("new_session")     # what the last session had not said yet is not said in this one
                    self.watch.reset()
                    self.exchange.reset()
                    self.nets.reset()                         # (no net on the speaker, no traffic, empty logs)
                    self._channel = ""
                    self.delegation.stop()                    # (the game starts with auto everywhere: what the Captain set goes back in once he chooses the campaign)
                    if isinstance(self.llm, OpenRouter):
                        asyncio.create_task(self._warm_up())         # (the session's first report should not pay for a cold route)
                    log.info("new game session: conversation reset (the war waits for the Captain's choice)")
                elif kind == "settings":
                    self._apply_language(msg)               # (the player changed the LANGUAGE settings during play)
                elif kind == "narrate":
                    # the introduction's narrator (AstraIntro.cpp): a line of the tour, said now in the player's language; "stop": the player skipped
                    if msg.get("stop"):
                        await self.voice.clear("intro_skipped")
                    elif (msg.get("text") or "").strip():
                        await self.voice.say(NARRATOR, msg["text"], msg.get("lang") or self.lang, "measured", priority=Prio.ANSWER, addressed=True)
                elif kind == "key_changed":
                    from .env import reload_env
                    reload_env()                            # (the player entered or replaced the OpenRouter key: the next request carries it)
                    log.info("the OpenRouter key was changed by the player")
                elif kind == "campaign":
                    # the Captain chose in the title menu: a new war, or the saved one
                    self.delegation.begin(new=msg.get("mode") != "continue")
                    if msg.get("mode") == "continue":
                        new_command = self.aftermath.resume_note
                        ok = self.director.load(note=f"NEW COMMAND: {new_command}" if new_command else "")
                        log.info("campaign continued (war map %s): %s, %d story notes", "loaded" if ok else "missing",
                                 self.director.war.current, len(self.director.campaign))
                        self.flight.load()                # (what the flight net's people remember of the Captain and of the fight so far)
                        self.marines.load()               # (and the Major's, and the squad leaders')
                        self._start_march(False)          # (and the war of the March, where it was)
                        # the war resumes: the director decides what the Aquila meets now (after the XO's welcome)
                        if new_command:
                            # after the loss: a new ship, weeks later; the crew's memory of the pod and the hearing is
                            # the story's now (the campaign notes), not the bridge's conversation
                            self.aftermath.resume_note = ""
                            self.aftermath.reset()
                            self.agent.history.clear()
                            self.enemy.reset()
                            self.war.reset()
                            self.flight.reset()
                            self.marines.reset()
                            resume = (f"director: campaign resumed — the Captain takes command of the new Aquila at New Ravenna "
                                      f"({new_command}); weeks have passed and the March moved on: tell what changed with "
                                      f"war_news, then the first beat for the new ship")
                        else:
                            resume = f"director: campaign resumed — the Aquila is back on patrol in the {self.director.war.current} system"
                        if new_command and self.director.decisive:
                            # the Aquila was lost in the decisive battle: that battle's outcome ends the arc first
                            self.director.decisive = False
                            asyncio.create_task(self._war_first(self.director._end_arc(
                                f"engagement over — the decisive battle was fought on without the Aquila, lost in it ({new_command})",
                                self.lang, self._battle_state()), True))
                        else:
                            asyncio.create_task(self._war_first(self.director.on_event(resume, self.lang, self._battle_state()), bool(new_command)))
                    else:
                        self.director.reset()
                        self.style.reset()
                        self.npcs.reset()
                        self.flight.new_campaign()
                        self.xfer.new_campaign()
                        self.marines.new_campaign()
                        self._start_march(True)
                        log.info("new campaign")
                    asyncio.create_task(self._send_sector())
                elif kind == "ship_state":
                    self.game.state = msg.get("state", {})
                    self._war_look(self.game.state)
                    for p_ in ((self.game.state.get("medbay") or {}).get("patients") or []):
                        EXTERNAL_SPEAKERS[p_["speaker"]] = (p_.get("name", p_["speaker"]), patient_voice(p_))
                    mess_ = self.game.state.get("mess") or {}
                    for d_ in mess_.get("diners") or []:
                        EXTERNAL_SPEAKERS[d_["speaker"]] = (d_.get("name", d_["speaker"]), patient_voice(d_))
                    if mess_:
                        EXTERNAL_SPEAKERS["mess_cook"] = ("Petty Officer Tomas Wren", "juergen")
                elif kind == "event":
                    text = msg.get("text", "")
                    self.game.events.append(text)
                    self.watch.note(text)                  # (what may change what the officers should do: the watch's next check)
                    if self.march_glue is not None and self.march_glue.on_event(text):
                        self.director.decisive = True      # (the March read what the game says of its ships; a major battle ends a chapter of the story: the finale tells it)
                    if text.startswith("transmission: "):
                        self._channel_opened(text[len("transmission: "):].split(" — ", 1)[0])      # (a Mandate commander calls: the channel is open)
                    elif text.startswith(("comms: channel closed", "comms: the Mandate cut the channel")):
                        self._channel = ""
                    if text.startswith("director: the Aquila is lost"):
                        # the story of the loss: who finds the Captain, the board, a new command (mind/astra_mind/loss.py). The war holds still
                        # meanwhile: the March, its raids and its news wait for the new command (5 Oct: Rourke announced waves at the Gate in the
                        # middle of the board of inquiry he chaired, and the bridge kept reporting from a ship that was gone)
                        if self.march_glue is not None:
                            self.march_glue.stop()
                        asyncio.create_task(self.aftermath.on_lost(text, self.lang))
                    elif text.startswith("director:") and not self.aftermath.active:
                        if "engagement over" in text:
                            outcome_, orders_ = text.split(":", 1)[1].strip(), list(self.style.orders)
                            asyncio.create_task(self.style.after_battle(outcome_))
                            if not self.director.decisive:          # (the decisive battle ends in the arc's finale instead)
                                asyncio.create_task(self._after_action(outcome_, orders_))
                        asyncio.create_task(self.director.on_event(text, self.lang, self._battle_state()))
                    elif text.startswith("story:"):
                        self.director.note(text.split(":", 1)[1].strip())   # remembered, no new beat
                    elif text.startswith("the Captain went into the Captain's quarters"):
                        # someone may have a reason to come by in person (mind/astra_mind/visits.py)
                        self.visits.captain_entered(lambda: (self.game.state if self.game else {}) or {}, self._visit_ctx)
                    flight_world = world_of(text) if text.startswith("flight:") else None
                    if flight_world:
                        persona = self._field_world(flight_world)
                        port_cue = stimulus_for(text, persona)
                        if port_cue:
                            asyncio.create_task(self._port_call(port_cue, 6.0 if "left the plot" in text else 1.5))
                        elif persona is None and "left the plot" in text:
                            asyncio.create_task(self._silent_field(flight_world, 8.0, False))
                        if persona and persona.get("owner") == "mandate" and "left the plot" in text:
                            self.director.note(f"the Captain flew a Falcon down to {flight_world}, a Kharon Mandate world")
                    fallen = _fallen(text)
                    if fallen:
                        self.director.note("fallen: " + "; ".join(fallen))
                    gone = _re.search(r"\((T-\d+)[,)]", text)
                    if gone and ("destroyed" in text or "left sensor range" in text):
                        self.enemy.ship_destroyed(gone.group(1))   # nobody left on that ship to answer a hail
                    taken = False
                    if not (self.aftermath.muted or self.aftermath.active):       # (the pod, the inquiry: the story has the floor)
                        try:
                            taken = self.flight.on_event(text)     # the flight net's people tell their own news (Price coordinates: he does not echo them)
                        except Exception:  # noqa: BLE001
                            log.exception("the flight net could not take an event")
                        try:
                            taken = self.xfer.on_event(text) or taken      # the Transporter Room's own news: the Chief tells it herself, the bridge does not echo it
                        except Exception:  # noqa: BLE001
                            log.exception("the Transporter Room could not take an event")
                        try:
                            taken = self.marines.on_event(text) or taken     # so do the marines (a boarding's own news is theirs; the bridge reports the ship's)
                        except Exception:  # noqa: BLE001
                            log.exception("the marine net could not take an event")
                    if msg.get("report") and not self.aftermath.muted and not taken:
                        self.last_activity = time.monotonic()
                        if text.startswith(WHEEL_EVENT):
                            # an order the Captain gave without a word (his command wheel): it is acknowledged like a spoken one, at once, in a turn of its own
                            self.captain_t = self.last_activity
                            asyncio.create_task(self._wheel_turn(text))
                        else:
                            await self.turns.put(("\x00event:" + self._first_watch(text), self.lang))
                elif kind == "command_result":
                    self.game.resolve(msg)
                elif kind == "voice_status":
                    # the game's own word on a line (started, stalled, failed): the only proof that a voice was really heard
                    self.voice.game_status(msg)
                elif kind == "player_text":
                    self.last_activity = self.captain_t = time.monotonic()
                    text = msg.get("text", "").strip()
                    if text:
                        log.info("the Captain types: %s", text)           # (as the spoken ones are: "STT ... [lang] words")
                        self.voice.captain_input()             # a typed order takes the floor like a spoken one
                        self._captain_speaks()                 # (priority: the crew's model calls stop, and the line in flight)
                        await self.turns.put((text, msg.get("lang") or resolve_language(text, self.lang)[0], msg.get("context")))
                elif kind == "ptt":
                    if msg.get("down"):
                        self.voice.captain_begin()             # whoever talks stops at the end of the phrase; the floor is his
                        self._captain_speaks()                 # (and the crew's model calls with them: agent.preempt)
                        self._ptt_ctx = msg.get("context") or self._ptt_ctx
                        self._ptt_session = self.stt.session()
                        if not await self.mic.begin(self._ptt_session.feed):
                            self.voice.captain_end(False)
                            await ws.send(json.dumps({"type": "status", "mic": "unavailable"}))
                    else:
                        self.voice.captain_end(None)           # (his order is coming: the floor stays his until it is answered)
                        asyncio.create_task(self._recognise(msg.get("context") or self._ptt_ctx))
        finally:
            self.clients.discard(ws)
            if not self.clients:
                self.voice.muted = True                        # nobody is listening: nothing more is made or queued
                await self.voice.clear("no_listener")
            log.info("game disconnected")

    async def _warm_up(self) -> None:
        """One minimal request through the crew's route (connection, provider, prompt cache) while the game is still starting."""
        try:
            await asyncio.sleep(0.4)                                 # (the game's first ship_state is in: the prompt is the real one)
            self.agent.ship = self.game if (self.game and self.game.state) else self.local
            log.info("crew route warmed in %.2fs", await self.agent.warm_up(self.lang))
        except Exception as exc:  # noqa: BLE001
            log.info("warm-up skipped: %s", exc)

    async def _recognise(self, ctx: dict[str, Any] | None = None) -> None:
        """The key is up: the last sounds, then the words (most of them were already decoded while he spoke)."""
        session, self._ptt_session = self._ptt_session, None
        rec = await self.mic.finish()
        if session is None or rec.speech_s < 0.15:
            if session is not None:
                session.cancel()
            self.voice.captain_end(False)                  # nothing was said: nobody is kept waiting for an order
            return
        tr = await session.finish(rec.raw)
        log.info("STT %.2fs after the key (decode %.2fs, %s%s) [%s] %s", tr.latency_s, tr.decode_s, tr.backend,
                 ", from the partial" if tr.partial_hit else "", tr.lang, tr.text)
        self.captain_t = time.monotonic()
        if not tr.text:
            self.voice.captain_end(False)
            return
        await self._sink("json", {"type": "transcript", "text": tr.text, "lang": tr.lang})
        await self.turns.put((tr.text, tr.lang, ctx))

    def _quit(self, sig: int) -> None:
        log.info("signal %d: the mind stops", sig)
        self.stt.stop_server()
        os._exit(0)

    async def serve(self) -> None:
        import websockets
        # the game closing (or anyone stopping the mind) takes the speech server down with it (the signals each system has: host.py)
        install_stop_handlers(asyncio.get_running_loop(), self._quit)
        await self.stt.start()
        asyncio.create_task(self.voice.run())
        asyncio.create_task(self.turn_worker())
        asyncio.create_task(self.quiet_moments())
        asyncio.create_task(self.story_watch())
        asyncio.create_task(self.mess_talk())
        asyncio.create_task(self.tactical_watch())
        asyncio.create_task(self.standing_sync())
        asyncio.create_task(self.delegation_sync())
        asyncio.create_task(self.channel_watch())
        asyncio.create_task(self.idle_exit())
        asyncio.create_task(self.flight_controller())
        loop = asyncio.get_running_loop()
        boost_thread()                                # this thread (the audio's pacing) on the performance cores, like the game

        async def warm_voices() -> None:
            # the Captain's language first, then English (the two stay in memory); in the background: the door opens at once (a first
            # start downloads the models: minutes), and a line said before they are ready is said by a system voice
            for lg in dict.fromkeys([self.lang, "en"]):
                await loop.run_in_executor(None, self.tts.warm, lg, [o.voice for o in CREW.values()])
        if os.environ.get("ASTRA_TTS_WARM", "1") != "0":      # (ASTRA_TTS_WARM=0: no voice is loaded before it is needed: tests of the door, the log and the launch)
            asyncio.create_task(warm_voices())
        log.info("astra-mind listening on ws://%s:%d", HOST, PORT)
        # a game busy for a while (loading, compiling shaders) must not lose the crew: pings wait up to 90 s
        async with websockets.serve(self.handle_client, HOST, PORT, max_size=2 ** 22, ping_interval=20, ping_timeout=90):
            await asyncio.Future()


# ---------------------------------------------------------------------------------------------- offline tools
async def offline_turns(utterances: list[str], out_dir: Path, check_audio: bool) -> None:
    llm, tts = OpenRouter(), TTSEngine()
    stt = Recognizer() if check_audio else None
    if stt:
        await stt.start()
    ship = LocalShip()
    audio: dict[int, list[bytes]] = {}
    meta: dict[int, dict[str, Any]] = {}

    async def sink(kind: str, payload: Any) -> None:
        if kind == "json" and payload.get("type") == "line":
            meta[payload["id"]] = payload
            print(f"    {payload['name']} ({payload['speaker']}, {payload['tone']}): {payload['text']}", flush=True)
        elif kind == "audio":
            lid = struct.unpack("<I", payload[:4])[0]
            audio.setdefault(lid, []).append(payload[4:])

    voice = Voice(tts, sink, speaker_identity)
    runner = asyncio.create_task(voice.run())
    agent = BridgeAgent(llm, ship, voice.say)
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        for u in utterances:
            lang = detect_lang(u)
            print(f"> Captain [{lang}]: {u}", flush=True)
            t = await agent.handle(u, lang)
            await voice.q.join()
            first_audio = [voice.first_audio[i] - voice.enqueued[i] for i in voice.first_audio if i in voice.enqueued]
            print(f"    actions: {[(n, a, r.get('ok')) for n, a, r in t.actions]}")
            print(f"    first line {t.t_first_line or -1:.2f}s · turn {t.t_end:.2f}s · tts first audio "
                  f"{(min(first_audio) if first_audio else -1) * 1000:.0f} ms · ${t.cost:.5f}", flush=True)
        for lid, chunks in audio.items():
            path = out_dir / f"line_{lid:03d}_{meta[lid]['speaker']}.wav"
            with wave.open(str(path), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(tts.sample_rate)
                w.writeframes(b"".join(chunks))
            if stt:
                import numpy as np
                pcm = np.frombuffer(b"".join(chunks), dtype="<i2").astype(np.float32)
                idx = (np.arange(int(len(pcm) * 16000 / tts.sample_rate)) * tts.sample_rate / 16000).astype(int)
                pcm16 = pcm[idx].astype("<i2").tobytes()
                heard, _ = await stt.transcribe(pcm16, language=meta[lid]["lang"], glossary=False)
                print(f"    check {path.name}: «{heard}»")
        print(f"spent ${agent.spent:.5f}")
    finally:
        runner.cancel()
        await llm.close()
        if stt:
            await stt.close()


def main() -> None:
    ap = argparse.ArgumentParser(prog="astra-mind")
    ap.add_argument("--say", help="one utterance against the local ship model")
    ap.add_argument("--script", help="file with one utterance per line")
    ap.add_argument("--out", default=str(CACHE / "turns"))
    ap.add_argument("--check-audio", action="store_true", help="re-transcribe every generated line (voice QA)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(name)s %(message)s")
    if args.say or args.script:
        lines = [args.say] if args.say else [l.strip() for l in Path(args.script).read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
        asyncio.run(offline_turns(lines, Path(args.out), args.check_audio))
        return
    asyncio.run(Mind().serve())


if __name__ == "__main__":
    sys.exit(main())


def _fallen(text: str) -> list[str]:
    """Names of the crew killed in a report ("... Petty Officer Amara Diallo (weapons, from Mars) and ... killed; ...",
    or the Medbay's "Petty Officer Amara Diallo (weapons, from Mars) has died of wounds")."""
    died = _re.match(r"medbay: (.+?) \([^)]*\) has died of wounds", text)
    if died:
        return [died.group(1)]
    out: list[str] = []
    for seg in _re.split(r"[;—]", text):
        seg = seg.strip()
        if not seg.endswith(" killed"):
            continue
        body = seg[: -len(" killed")].split("casualties: ")[-1]
        for part in body.split(" and "):
            name = _re.sub(r" \((?!call sign)[^)]*\)", "", part).strip()
            if name:
                out.append(name)
    return out


FLIGHT_CALL_ASK = ("Price, the Captain's flight controller, makes one short radio call to the Captain in the Falcon (callsign "
                   "Eagle): the most important thing around the Falcon now — a threat by clock position, high or low, its "
                   "range and whether it is closing; or the way home; or what to hit — in clipped radio style (\"Eagle, "
                   "Price: two bandits, your two o'clock high, three kilometres, closing\"), in the Captain's language. One "
                   "line, no tools; nothing new worth a call: reply SILENT.")

AFTER_ACTION_ASK = ("The fight is over. The XO gives the Captain a short after-action, two or three sentences in character: the "
                    "outcome and what it cost (hull, people, ships, fighters), what worked, and one honest lesson for the next "
                    "fight — from what really happened (the reports above) and the Captain's own orders; no flattery, no "
                    "blame. The officer most involved may add one line. No tools.")

VISIT_ASK = ("An officer has just come to the Captain's quarters in person (the event says who and why). That officer, "
             "and only that officer, speaks now with speak, face to face: a first line or two that open what they came "
             "to say, in their own voice and character, shaped by the reason, by what the ship has lived through and by "
             "how they stand with the Captain. Human and direct, not a report; then they wait for the Captain. True to "
             "the ship: names of the fallen or the wounded only from the casualties, the Medbay and the events, never "
             "invented. No tools.")
TACTICAL_ASK = ("A tactical check of the fight (the facts above come from the plot, they are true now). The XO, or the "
                "officer whose station it concerns, tells the Captain the single most important problem in one short "
                "sentence and recommends a concrete order the Captain could give (a course or intercept, a target, a "
                "flight group, shields); for a blind picture, Nair gives the two best options and what each costs, in two "
                "short sentences, weighing how this Captain usually fights. Do not act on your own — unless a standing order in force covers the problem: "
                "then that officer carries it out now and reports it — and do not repeat what was said in the last "
                "minute. If nothing here really needs the Captain now, reply with the word SILENT and call no tool.")


def picture_flag(st: dict) -> tuple[str, str] | None:
    """The information war: when the plot holds only bearings (no range: faint emissions, a jammer, perhaps decoys),
    the Captain should hear the options once — (signature of this picture, the fact for the crew)."""
    contacts = st.get("contacts", []) or []
    bearings = [c for c in contacts if str(c.get("status", "")).startswith(("bearing only", "JAMMING"))]
    if not bearings:
        return None
    jammers = [c for c in bearings if str(c.get("status", "")).startswith("JAMMING")]
    firm = [c for c in contacts if str(c.get("status", "")).startswith("hostile")]
    if len(bearings) < 2 and not jammers:
        return None
    sig = "|".join(sorted(str(c.get("id")) for c in bearings)) + "#" + "|".join(sorted(str(c.get("id")) for c in jammers))
    ids = ", ".join(f"{c.get('id')} ({int(c.get('bearing_deg', 0) or 0):03d}{', jamming' if c in jammers else ''})" for c in bearings[:5])
    options = ("missiles can fly home-on-jam; a flight group sent out on the flank gives a cross-fix (a range) or eyes on "
               "it; an active ping burns through and unmasks decoys for a moment but tells everyone where we are; or "
               "close in (burn-through inside 12 km)") if jammers else \
              ("an active ping gives ranges and unmasks decoys but tells everyone where we are; a recon flight (Wasp "
               "drones) looks without giving us away; EMCON full reaches further; or wait for them to close")
    return sig, (f"blind picture: {len(bearings)} contact(s) with no range — {ids}"
                 f"{'; ' + str(len(firm)) + ' tracked' if firm else ''}; any bearing may be a decoy. Options: {options}")


def tactical_flags(st: dict) -> list[str]:
    """What is going wrong in the fight, from the telemetry (short English facts for the crew)."""
    contacts = st.get("contacts", []) or []
    hostile = [c for c in contacts if str(c.get("status", "")) == "hostile"]
    if not hostile:
        return []
    flags = []
    weapons = st.get("weapons", {}) or {}
    rail = str(weapons.get("railguns", ""))
    helm = str(st.get("helm", ""))
    m_int = _re.search(r"intercepting (T-\d+)", helm)
    m_fire = _re.search(r"assigned to (T-\d+), waiting for it to close inside (\d+) km \(now (\d+) km\)", rail)
    if m_fire and (not m_int or m_int.group(1) != m_fire.group(1)):
        flags.append(f"out of reach: the railguns wait for {m_fire.group(1)} to close inside {m_fire.group(2)} km (now "
                     f"{m_fire.group(3)} km) but the helm is {('intercepting ' + m_int.group(1)) if m_int else 'not closing on it'}")
    for c in contacts:
        stt = str(c.get("status", ""))
        if stt not in ("friendly", "neutral"):
            continue
        hp = c.get("hull_pct")
        if isinstance(hp, (int, float)) and hp < 45:
            who = "friendly" if stt == "friendly" else "civilian"
            flags.append(f"{who} in trouble: {c.get('name', c.get('id'))} ({c.get('id')}) hull {int(hp)}%, {c.get('range_km')} km "
                         f"bearing {int(c.get('bearing_deg', 0)):03d}")
    sh = (st.get("shields") or {}).get("strength_pct")
    if isinstance(sh, (int, float)) and sh < 35:
        flags.append(f"shields low: {int(sh)}% ({(st.get('shields') or {}).get('mode', '')})")
    near = [c for c in hostile if isinstance(c.get("range_km"), (int, float)) and c["range_km"] < 9.0]
    if near and "engaging" not in rail and "assigned" not in rail:
        c = min(near, key=lambda x: x["range_km"])
        flags.append(f"hostile close and untouched: {c.get('name', c.get('id'))} ({c.get('id')}) at {c['range_km']} km, our railguns idle")
    mm = _re.match(r"(\d+) in the VLS", str(weapons.get("missiles", "")))
    if mm and int(mm.group(1)) < 16:
        flags.append(f"magazines: {mm.group(1)} missiles left")
    hull = st.get("hull_pct")
    if isinstance(hull, (int, float)) and hull < 40:
        flags.append(f"our hull {int(hull)}%")
    return flags[:3]


_LOG_START = _re.compile(r"^\s*(diario (?:di bordo )?del capitano|captain'?s log|journal (?:de bord )?du capitaine|diario del capit[aá]n|"
                         r"bit[aá]cora del capit[aá]n|logbuch des kapit[aä]ns|kapit[aä]nslogbuch)\b[\s,.:;-]*", _re.IGNORECASE)


def captains_log_entry(text: str) -> str | None:
    """'Diario del capitano: ...' -> the entry (None if the Captain is not dictating the log)."""
    m = _LOG_START.match(text or "")
    if not m:
        return None
    return text[m.end():].strip() or "(no entry)"
