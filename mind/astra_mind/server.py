"""astra-mind: the crew's minds and voices, next to the game.

WebSocket ws://127.0.0.1:8765 — JSON text frames + binary audio frames.
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
import signal
import struct
import sys
import time
import wave
from pathlib import Path
from typing import Any

from lingua import Language, LanguageDetectorBuilder

from .agent import BridgeAgent, ShipLink
from .audio_in import PushToTalk
from .crew import CREW
from .enemy import COMMANDERS, EnemyAgent
from .style import StyleKeeper
from .router import route
from .director import ADMIRAL, Director
from .env import CACHE
from .local_ship import LocalShip
from .openrouter import OpenRouter, credits
from .stt import Recognizer
from .voice_lang import resolve_language
from .speech import Voice
from .tts import TTSEngine
from .voice_qos import boost_thread

log = logging.getLogger("astra.mind")
HOST, PORT = "127.0.0.1", 8765

_LANGS = {Language.ITALIAN: "it", Language.ENGLISH: "en", Language.SPANISH: "es", Language.FRENCH: "fr",
          Language.GERMAN: "de", Language.PORTUGUESE: "pt", Language.DUTCH: "nl"}
_DETECT = LanguageDetectorBuilder.from_languages(*_LANGS).build()


def detect_lang(text: str, default: str = "en") -> str:
    lang = _DETECT.detect_language_of(text)
    return _LANGS.get(lang, default) if lang else default


class GameShip:
    """ShipLink backed by the game: commands go to Unreal, which answers with the authoritative result."""

    def __init__(self, send) -> None:  # noqa: ANN001
        self._send = send
        self.state: dict[str, Any] = {}
        self.events: list[str] = []
        self._waiting: dict[str, asyncio.Future] = {}
        self._n = 0

    def snapshot(self) -> dict[str, Any]:
        return self.state

    def recent_events(self) -> list[str]:
        return self.events[-8:]

    async def execute(self, name: str, args: dict[str, Any], by: str) -> dict[str, Any]:
        self._n += 1
        cid = f"c{self._n}"
        fut = asyncio.get_running_loop().create_future()
        self._waiting[cid] = fut
        await self._send({"type": "command", "id": cid, "name": name, "args": args, "by": by})
        try:
            return await asyncio.wait_for(fut, timeout=2.5)
        finally:
            self._waiting.pop(cid, None)

    def resolve(self, msg: dict[str, Any]) -> None:
        fut = self._waiting.get(msg.get("id", ""))
        if fut and not fut.done():
            fut.set_result({"ok": bool(msg.get("ok")), "detail": msg.get("detail", "")})


EXTERNAL_SPEAKERS = {c["key"]: (f'{c["name"]} ({c["ship"]})', c["voice"]) for c in COMMANDERS.values()}
EXTERNAL_SPEAKERS[ADMIRAL["key"]] = (f'{ADMIRAL["name"]} ({ADMIRAL["ship"]})', ADMIRAL["voice"])
from .port import PORT as PORT_CONTROL, FieldControl, for_field, stimulus_for, world_of  # noqa: E402
from .medbay import patient_voice  # noqa: E402
from .mess import MessTalk  # noqa: E402
from .visits import VisitPlanner  # noqa: E402
from .loss import Aftermath  # noqa: E402
from .finale import Finale  # noqa: E402
from .memory import MemoryKeeper  # noqa: E402
EXTERNAL_SPEAKERS[PORT_CONTROL["key"]] = (f'{PORT_CONTROL["name"]} ({PORT_CONTROL["place"]})', PORT_CONTROL["voice"])
EXTERNAL_SPEAKERS["director"] = ("The Director (game master)", "paul")

# the player talking to the story itself (game master mode): "Regista, ...", "Director, ...", "Narratore, ..."
import re as _re  # noqa: E402
# events whose report is a warning of danger: the crew says them before any routine talk (voice priority URGENT)
_URGENT_EVENT = _re.compile(r"missiles? inbound|rockets? inbound|hull integrity critical|containment failing|abandon ship|breach", _re.I)
_GM_ADDRESS = _re.compile(r"^\W*(regista|director|narrat\w*|game ?master|gm|réalisateur|directeur|director de juego|spielleiter|erzähler)\b[\s,:;.!-]*", _re.I)

# the Captain talking to someone on the bridge (not to the enemy on an open channel): names and roles, several languages
import re as _re
_CREW_ADDRESS = _re.compile(
    r"^\W*(serra|ferri|tanaka|voss|martin|nair|mensah|price|okonkwo|capo|chief|lindqvist|dottor\w*|doctor|doc|"
    r"numero uno|primo ufficiale|xo|comandante|timon\w*|helm\w*|"
    r"tattic\w*|tactical|ops|operazion\w*|operations|comunicazion\w*|comms?|sensor\w*|scienz\w*|ingegner\w*|"
    r"engineering|volo|flight|plancia|bridge|number one|chiud\w* (il )?canale|close (the )?channel|fine trasmissione|"
    r"end transmission|praetorian|vigilant|flotta|fleet|scorta|escort)\b", _re.I)


def speaker_identity(speaker: str) -> tuple[str, str, bool]:
    """(display name, voice, aboard) of anyone who can speak: a bridge officer or someone on a channel or in a room."""
    if speaker in CREW:
        return CREW[speaker].title, CREW[speaker].voice, True
    name, voice = EXTERNAL_SPEAKERS.get(speaker, (speaker, "alba"))
    return name, voice, False


def addressed_to_crew(text: str) -> bool:
    return bool(_CREW_ADDRESS.match(text.strip()))


class Mind:
    def __init__(self) -> None:
        self.llm = OpenRouter()
        self.tts = TTSEngine()
        self.stt = Recognizer()
        self.mic = PushToTalk()
        self._ptt_session = None                # the recognition session of the key press being held
        self.local = LocalShip()
        self.clients: set = set()
        self.game: GameShip | None = None
        self.voice = Voice(self.tts, self._sink, speaker_identity)
        self.agent = BridgeAgent(self.llm, self.local, self.voice.say)
        self.enemy = EnemyAgent(self.llm, self._say_external, self._enemy_command)
        self.port = FieldControl(self.llm, self._say_external, self._register_field)
        self.mess = MessTalk(self.llm, self.voice.say)
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
        self.agent.say = self._crew_say
        # the Captain's log is private: the story reads it, the crew does not
        self.agent.campaign = lambda: [c for c in self.director.campaign if not c.startswith("captain's log:")]
        self.agent.war = lambda: self.director.war.crew_view()
        self.agent.mood = lambda: self.director.mood
        self.agent.bonds = lambda: "\n".join(f"- {line}" for line in self.director.bonds_lines())
        self.agent.standing = self.director.standing        # one list: the agent keeps it, the story saves it
        self.turns: asyncio.Queue = asyncio.Queue()
        self.last_activity = time.monotonic()   # the Captain spoke or something was reported
        self.captain_t = 0.0                     # the last time the Captain spoke
        self.lang_file = CACHE / "captain_lang.txt"
        self.lang = self.lang_file.read_text().strip() if self.lang_file.exists() else "en"   # the Captain's language

    async def _sink(self, kind: str, payload: Any) -> None:
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send(json.dumps(payload, ensure_ascii=False) if kind == "json" else payload)
            except Exception:  # noqa: BLE001
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    async def _say_external(self, speaker: str, text: str, lang: str, tone: str) -> None:
        """Voices from outside the bridge (enemy commanders, the admiral): heard by the crew too."""
        if self.game is not None:
            who = EXTERNAL_SPEAKERS.get(speaker, (speaker, ""))[0]
            self.game.events.append(f"over the radio, {who}: {text}")
        await self.voice.say(speaker, text, lang, tone)

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

    async def _crew_say(self, speaker: str, text: str, lang: str, tone: str) -> None:
        """The crew's lines: voiced, and heard by the memory keeper (an officer remembers what passed with the Captain)."""
        if speaker in CREW:
            self.memory.hear(speaker, text)
        await self.voice.say(speaker, text, lang, tone)

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
                    t = await self.agent.handle_event(
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
                    t = await self.agent.handle_event(
                        f"bridge: a quiet moment on watch", self.lang,
                        ask=(f"A quiet moment. {who} turns to the Captain, off the record, with one short personal line: "
                             "something that officer has been meaning to say or ask — from what they remember of the Captain "
                             "and of their conversations, from how they stand with the Captain, or from what the ship has "
                             "lived through (a question about someone the Captain spoke of, a promise, a thanks, a doubt "
                             "about an order, something about themselves). One line, human and specific, never a report; it "
                             "invites an answer. Only speak, only that officer."))
                    log.info("personal moment (%s): %s", who, " | ".join(f"{s}: {x}" for s, x in t.lines))
                else:
                    t = await self.agent.handle_event(
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

    async def enemy_tactics(self) -> None:
        """The Mandate fights with its head: while its strike group is attacking, its senior commander reads the battle
        every ~40 s and commands the ships by datalink (focus of fire, stance, missile salvos, fighters). The Aquila's
        sensors see what the ships do, and the bridge reacts."""
        from .enemy import plan_tactics
        first_seen = 0.0
        last = 0.0
        while True:
            await asyncio.sleep(4)
            st = self.game.state if (self.game and self.game.state) else None
            if not st or not self.clients:
                continue
            view = st.get("_mandate") if isinstance(st.get("_mandate"), dict) else {}
            fighting = [s_ for s_ in view.get("your_ships", []) if s_.get("state") == "attacking"]
            if not fighting:
                if first_seen:
                    # the fight is over: the next one starts from a clean slate of orders
                    self.enemy.last_orders = "none yet: each ship fights the nearest enemy at standard range"
                    self.enemy.last_focus = ""
                first_seen = 0.0
                continue
            now = time.monotonic()
            if not first_seen:
                first_seen = now
            if now - first_seen < 20 or now - last < 40:
                continue
            last = now
            try:
                orders = await plan_tactics(self.enemy, self._battle_state(), note=self.director.note)
                if orders:
                    log.info("Mandate tactics: %s", orders)
            except Exception:  # noqa: BLE001
                log.exception("enemy tactics failed")

    async def tactical_watch(self) -> None:
        """In a fight the crew watches the big picture for the Captain: when something important is going wrong
        (weapons assigned out of reach while the helm chases another contact, a friendly ship dying, shields failing,
        hostiles close and untouched, magazines running dry) the XO or the officer concerned says so, once, with a
        recommendation. The problems are found here, from the telemetry; the officer only phrases them."""
        last_t, last_key = 0.0, ""
        pictures: set[str] = set()                  # blind pictures already put to the Captain (once each)
        while True:
            await asyncio.sleep(5)
            st = self.game.state if (self.game and self.game.state) else None
            if not st or not self.clients or st.get("abandon") or self.aftermath.active:
                continue
            flags = tactical_flags(st)
            info = picture_flag(st)
            if info and info[0] not in pictures and len(flags) < 3:
                flags.append(info[1])
            now = time.monotonic()
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
            gate = str(st.get("janus_gate", ""))
            if hostile or st.get("alert") == "red" or quiet < 420 or "under way" in gate or "lane" in gate:
                continue
            why = "the Captain has not acted on Fleet's transit orders" if "Fleet orders" in gate else "nothing has happened"
            log.info("story stalled for %.0f s: %s", quiet, why)
            asyncio.create_task(self.director.on_event(f"director: story stalled — {why} for {int(quiet // 60)} minutes",
                                                       self.lang, self._battle_state()))

    async def turn_worker(self) -> None:
        while True:
            text, lang = await self.turns.get()
            try:
                self.agent.ship = self.game if (self.game and self.game.state) else self.local
                if text.startswith("\x00event:"):
                    # let the bridge fall quiet first (reports must not pile up behind the voices), then coalesce:
                    # everything that happened meanwhile becomes one report turn; the Captain's words are never merged
                    # or delayed behind events
                    while (self.voice.busy_s() > 1.2 or self.voice.held) and self.turns.empty():
                        await asyncio.sleep(0.2)
                    events = [text[len("\x00event:"):]]
                    pending = []
                    while not self.turns.empty():
                        nxt = self.turns.get_nowait()
                        (events if nxt[0].startswith("\x00event:") else pending).append(
                            nxt[0][len("\x00event:"):] if nxt[0].startswith("\x00event:") else nxt)
                    for p in pending:
                        await self.turns.put(p)
                    if pending:
                        continue          # the Captain spoke: answer first, the events stay in the state/history
                    transmissions = [e for e in events if e.startswith("transmission:")]
                    events = [e for e in events if not e.startswith("transmission:")]
                    for tr in transmissions:
                        # "transmission: T-22 — why": that captain calls the Aquila (arrival, succession, broken ceasefire)
                        m = _re.match(r"transmission:\s*(T-\d+)\s*—\s*(.*)", tr)
                        if m and m.group(1) not in COMMANDERS:
                            # nobody gave this captain a mind yet: a Mandate officer with the ship's name on the call sign
                            ship = _re.search(r"aboard the ([\w' -]+)", m.group(2))
                            self._register_commander(m.group(1), {
                                "name": f"the commander of the {ship.group(1) if ship else 'raid group'}",
                                "rank": "Ferryman (ship captain)", "ship": f"the {ship.group(1) if ship else 'Mandate warship'}",
                                "bio": "A hard, tired officer of the Outer Worlds who has lost friends to the Core's guns and "
                                       "wants the Gates for his people; proud, laconic, honest.",
                                "voice": "stuart_bell"})
                        if m and self.enemy.open_channel(m.group(1)):
                            await self.enemy.respond(f"[Situation: {m.group(2)}. You are the one opening this channel: make "
                                                     "your transmission to the Aquila's captain.]", self.lang, self._battle_state())
                    if not events:
                        continue
                    self.voice.low_priority = True
                    if any(_URGENT_EVENT.search(e) for e in events):
                        self.voice.urgent = True          # (danger now: it does not wait behind small talk or a routine report)
                    try:
                        ask = FLIGHT_CALL_ASK if any(e.startswith("flight: controller call") for e in events) else \
                            AFTER_ACTION_ASK if any(e.startswith("bridge: after-action") for e in events) else \
                            TACTICAL_ASK if any(e.startswith("bridge: tactical check") for e in events) else \
                            VISIT_ASK if any("has come to the Captain's quarters in person" in e for e in events) else None
                        t = await self.voice.preemptible(self.agent.handle_event(" | ".join(events), self.lang, ask=ask))
                    finally:
                        self.voice.low_priority = False
                    if t is None:                     # the Captain took the floor while the report was being written: it waits
                        for e in events:              # behind his order (nothing is lost: it is put back in the queue)
                            await self.turns.put(("\x00event:" + e, self.lang))
                        continue
                    log.info("event turn %.2fs: %s", t.t_end, " | ".join(f"{s}: {x}" for s, x in t.lines) or "(no report)")
                    continue
                self.voice.captain_turn_begin()               # what is said from here to the end of this turn answers the Captain
                dropped = self.voice.drop_low_priority()      # the Captain speaks: small talk is no longer worth saying
                if dropped:
                    log.info("captain speaks: %d unspoken small-talk lines dropped", dropped)
                if lang != self.lang:
                    asyncio.create_task(self.tts.prepare(lang, [o.voice for o in CREW.values()]))   # the crew will answer in it
                    self.lang = lang
                    self.lang_file.parent.mkdir(parents=True, exist_ok=True)
                    self.lang_file.write_text(lang)
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
                to_enemy = ""
                if self.enemy.open:
                    # a channel is open: the words meant for the enemy go over it, the orders stay on the bridge
                    r = await route(self.llm, text, COMMANDERS.get(self.enemy.contact, {}).get("name", "the enemy commander"))
                    log.info("channel open, routed (%s): crew=%r enemy=%r", r.how, r.crew[:60], r.enemy[:60])
                    to_enemy = r.enemy
                    if r.enemy:
                        who = COMMANDERS.get(self.enemy.contact, {}).get("name", "the Mandate commander")
                        self.director.note(f"the Captain to {who} over the channel: {r.enemy}")
                    if not r.crew:
                        await self.enemy.respond(f"[The ASTRA captain, over the open channel]: {to_enemy}", lang, self._battle_state())
                        continue
                    text = r.crew
                self.memory.hear("Captain", text)
                t = await self.agent.handle(text, lang)
                self.style.captain_order(text, t.actions)
                asyncio.create_task(self.memory.maybe_read())
                for name, args_, res in t.actions:
                    if name == "end_transmission":
                        self.enemy.open = False
                    if name == "hail" and res.get("ok") and str(args_.get("contact_id", "")).lower() == "fleet":
                        await self.director.admiral_reply(str(args_.get("message", "")), lang, self._battle_state())
                    # (open_channel knows who has a commander to answer: a contact not yet classified, a decoy, a
                    # friendly ship never do)
                    if name == "hail" and res.get("ok") and str(args_.get("contact_id", "")).lower() != "fleet" \
                            and self.enemy.open_channel(str(args_.get("contact_id", "")).upper()):
                        await self.enemy.respond(f"[The ASTRA ship hails you. Their message: {args_.get('message', '')}]",
                                                 lang, self._battle_state())
                if to_enemy and self.enemy.open:
                    await self.enemy.respond(f"[The ASTRA captain, over the open channel]: {to_enemy}", lang, self._battle_state())
                await self._sink("json", {"type": "turn_end", "first_line_s": t.t_first_line, "total_s": round(t.t_end, 3),
                                          "cost": t.cost, "actions": [[n, a, r] for n, a, r in t.actions], "error": t.error})
                log.info("turn %.2fs (first line %.2fs) cost $%.5f: %s", t.t_end, t.t_first_line or -1, t.cost,
                         " | ".join(f"{s}: {x}" for s, x in t.lines))
            except Exception:  # noqa: BLE001
                log.exception("turn failed")
            finally:
                self.voice.captain_turn_end()             # (no line came out of the Captain's turn: his floor is released)

    async def handle_client(self, ws) -> None:  # noqa: ANN001
        self.clients.add(ws)
        self.voice.muted = False
        self.game = GameShip(lambda m: ws.send(json.dumps(m, ensure_ascii=False)))
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
                    # a new game session: the crew starts a fresh conversation (the ship state is new too)
                    self.agent.history.clear()
                    self.enemy.reset()
                    self.port.reset()
                    await self.voice.clear("new_session")     # what the last session had not said yet is not said in this one
                    log.info("new game session: conversation reset (the war waits for the Captain's choice)")
                elif kind == "campaign":
                    # the Captain chose in the title menu: a new war, or the saved one
                    if msg.get("mode") == "continue":
                        new_command = self.aftermath.resume_note
                        ok = self.director.load(note=f"NEW COMMAND: {new_command}" if new_command else "")
                        log.info("campaign continued (war map %s): %s, %d story notes", "loaded" if ok else "missing",
                                 self.director.war.current, len(self.director.campaign))
                        # the war resumes: the director decides what the Aquila meets now (after the XO's welcome)
                        if new_command:
                            # after the loss: a new ship, weeks later; the crew's memory of the pod and the hearing is
                            # the story's now (the campaign notes), not the bridge's conversation
                            self.aftermath.resume_note = ""
                            self.aftermath.reset()
                            self.agent.history.clear()
                            self.enemy.reset()
                            resume = (f"director: campaign resumed — the Captain takes command of the new Aquila at New Ravenna "
                                      f"({new_command}); weeks have passed and the March moved on: tell what changed with "
                                      f"war_news, then the first beat for the new ship")
                        else:
                            resume = f"director: campaign resumed — the Aquila is back on patrol in the {self.director.war.current} system"
                        if new_command and self.director.decisive:
                            # the Aquila was lost in the decisive battle: that battle's outcome ends the arc first
                            self.director.decisive = False
                            asyncio.create_task(self.director._end_arc(
                                f"engagement over — the decisive battle was fought on without the Aquila, lost in it ({new_command})",
                                self.lang, self._battle_state()))
                        else:
                            asyncio.create_task(self.director.on_event(resume, self.lang, self._battle_state()))
                    else:
                        self.director.reset()
                        self.style.reset()
                        log.info("new campaign")
                    asyncio.create_task(self._send_sector())
                elif kind == "ship_state":
                    self.game.state = msg.get("state", {})
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
                    if text.startswith("director: the Aquila is lost"):
                        # the story of the loss: who finds the Captain, the board, a new command (mind/astra_mind/loss.py)
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
                    if msg.get("report") and not self.aftermath.muted:
                        self.last_activity = time.monotonic()
                        await self.turns.put(("\x00event:" + text, self.lang))
                elif kind == "command_result":
                    self.game.resolve(msg)
                elif kind == "voice_status":
                    # the game's own word on a line (started, stalled, failed): the only proof that a voice was really heard
                    self.voice.game_status(msg)
                elif kind == "player_text":
                    self.last_activity = self.captain_t = time.monotonic()
                    text = msg.get("text", "").strip()
                    if text:
                        self.voice.captain_input()             # a typed order takes the floor like a spoken one
                        await self.turns.put((text, msg.get("lang") or resolve_language(text, self.lang)[0]))
                elif kind == "ptt":
                    if msg.get("down"):
                        self.voice.captain_begin()             # whoever talks stops at the end of the phrase; the floor is his
                        self._ptt_session = self.stt.session()
                        if not self.mic.start(self._ptt_session.feed):
                            self.voice.captain_end(False)
                            await ws.send(json.dumps({"type": "status", "mic": "unavailable"}))
                    else:
                        self.voice.captain_end(None)           # (his order is coming: the floor stays his until it is answered)
                        asyncio.create_task(self._recognise())
        finally:
            self.clients.discard(ws)
            if not self.clients:
                self.voice.muted = True                        # nobody is listening: nothing more is made or queued
                await self.voice.clear("no_listener")
            log.info("game disconnected")

    async def _recognise(self) -> None:
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
        await self.turns.put((tr.text, tr.lang))

    def _quit(self, sig: int) -> None:
        log.info("signal %d: the mind stops", sig)
        self.stt.stop_server()
        os._exit(0)

    async def serve(self) -> None:
        import websockets
        # the game closing (or anyone stopping the mind) takes the speech server down with it
        for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
            asyncio.get_running_loop().add_signal_handler(sig, self._quit, sig)
        await self.stt.start()
        asyncio.create_task(self.voice.run())
        asyncio.create_task(self.turn_worker())
        asyncio.create_task(self.quiet_moments())
        asyncio.create_task(self.story_watch())
        asyncio.create_task(self.mess_talk())
        asyncio.create_task(self.tactical_watch())
        asyncio.create_task(self.enemy_tactics())
        asyncio.create_task(self.standing_sync())
        asyncio.create_task(self.idle_exit())
        asyncio.create_task(self.flight_controller())
        loop = asyncio.get_running_loop()
        boost_thread()                                # this thread (the audio's pacing) on the performance cores, like the game

        async def warm_voices() -> None:
            # the Captain's language first, then English (the two stay in memory); in the background: the door opens at once (a first
            # start downloads the models: minutes), and a line said before they are ready is said by a system voice
            for lg in dict.fromkeys([self.lang, "en"]):
                await loop.run_in_executor(None, self.tts.warm, lg, [o.voice for o in CREW.values()])
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
        lines = [args.say] if args.say else [l.strip() for l in Path(args.script).read_text().splitlines() if l.strip() and not l.startswith("#")]
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
