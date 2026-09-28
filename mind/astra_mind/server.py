"""astra-mind: the crew's minds and voices, next to the game.

WebSocket ws://127.0.0.1:8765 — JSON text frames + binary audio frames.
Game -> mind:  hello · ship_state{state} · event{text} · player_text{text,lang?} · ptt{down} · command_result{id,ok,detail}
Mind -> game:  status{...} · transcript{text,lang} · command{id,name,args,by} · line{id,speaker,name,text,lang,tone}
               audio_begin{line,speaker,rate} · <binary: uint32 LE line id + PCM16 mono> · audio_end{line} · turn_end{...}

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
from typing import Any

from lingua import Language, LanguageDetectorBuilder

from .agent import BridgeAgent, ShipLink
from .audio_in import PushToTalk
from .crew import CREW
from .enemy import COMMANDERS, EnemyAgent
from .router import route
from .director import ADMIRAL, Director
from .env import REPO_ROOT
from .local_ship import LocalShip
from .openrouter import OpenRouter, credits
from .stt import WhisperKit
from .tts import TTSEngine

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
from .port import PORT as PORT_CONTROL, PortControl, for_port, stimulus_for  # noqa: E402
EXTERNAL_SPEAKERS[PORT_CONTROL["key"]] = (f'{PORT_CONTROL["name"]} ({PORT_CONTROL["place"]})', PORT_CONTROL["voice"])

# the Captain talking to someone on the bridge (not to the enemy on an open channel): names and roles, several languages
import re as _re
_CREW_ADDRESS = _re.compile(
    r"^\W*(serra|ferri|tanaka|voss|martin|nair|mensah|price|numero uno|primo ufficiale|xo|comandante|timon\w*|helm\w*|"
    r"tattic\w*|tactical|ops|operazion\w*|operations|comunicazion\w*|comms?|sensor\w*|scienz\w*|ingegner\w*|"
    r"engineering|volo|flight|plancia|bridge|number one|chiud\w* (il )?canale|close (the )?channel|fine trasmissione|"
    r"end transmission|praetorian|vigilant|flotta|fleet|scorta|escort)\b", _re.I)


def addressed_to_crew(text: str) -> bool:
    return bool(_CREW_ADDRESS.match(text.strip()))


class Voice:
    """Serialises the crew's lines in speaking order. Synthesis runs one line ahead; each line is sent when the previous
    one has finished playing (the game plays audio as it arrives, so sending early would make officers talk over each
    other). Lines from event reports are low priority: when the Captain speaks, the unspoken ones are dropped."""

    GAP_S = 0.25                    # a breath between two lines

    def __init__(self, tts: TTSEngine, sink) -> None:  # noqa: ANN001
        self.tts = tts
        self.sink = sink            # async (kind, payload) -> None
        self.q: asyncio.Queue = asyncio.Queue()
        self._n = 0
        self.first_audio: dict[int, float] = {}
        self.enqueued: dict[int, float] = {}
        self.low_priority = False   # set while an event turn is speaking
        self.busy_until = 0.0       # monotonic time when the line being played ends

    async def say(self, speaker: str, text: str, lang: str, tone: str) -> None:
        self._n += 1
        lid = self._n
        self.enqueued[lid] = time.perf_counter()
        name = CREW[speaker].title if speaker in CREW else EXTERNAL_SPEAKERS.get(speaker, (speaker, ""))[0]
        await self.sink("json", {"type": "line", "id": lid, "speaker": speaker, "name": name, "text": text,
                                 "lang": lang, "tone": tone, "channel": speaker not in CREW})
        await self.q.put((lid, speaker, text, lang, self.low_priority))

    def busy_s(self) -> float:
        """Seconds of speech still ahead (playing + queued, estimated)."""
        return max(0.0, self.busy_until - time.monotonic()) + 3.0 * self.q.qsize()

    def drop_low_priority(self) -> int:
        keep, dropped = [], 0
        while not self.q.empty():
            item = self.q.get_nowait()
            self.q.task_done()
            if item[4]:
                dropped += 1
            else:
                keep.append(item)
        for item in keep:
            self.q.put_nowait(item)
        return dropped

    async def run(self) -> None:
        ready: asyncio.Queue = asyncio.Queue(maxsize=1)      # one line synthesised ahead

        async def synth() -> None:
            while True:
                lid, speaker, text, lang, _ = await self.q.get()
                chunks: asyncio.Queue = asyncio.Queue()
                await ready.put((lid, speaker, chunks))
                try:
                    voice = CREW[speaker].voice if speaker in CREW else EXTERNAL_SPEAKERS.get(speaker, ("", "alba"))[1]
                    async for pcm in self.tts.stream(text, voice, lang if self.tts.supported(lang) else "en"):
                        await chunks.put(pcm)
                except Exception:  # noqa: BLE001
                    log.exception("voice line %s failed", lid)
                finally:
                    await chunks.put(None)
                    self.q.task_done()

        asyncio.create_task(synth())
        rate = self.tts.sample_rate
        while True:
            lid, speaker, chunks = await ready.get()
            wait = self.busy_until - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
            await self.sink("json", {"type": "audio_begin", "line": lid, "speaker": speaker, "rate": rate})
            t_first, samples = None, 0
            while (pcm := await chunks.get()) is not None:
                if t_first is None:
                    t_first = time.monotonic()
                    self.first_audio[lid] = time.perf_counter()
                samples += len(pcm) // 2
                await self.sink("audio", struct.pack("<I", lid) + pcm)
                self.busy_until = t_first + samples / rate + self.GAP_S
            await self.sink("json", {"type": "audio_end", "line": lid})
            log.debug("voice line %d (%s): waited %.2f s, %.2f s of audio", lid, speaker, max(0.0, wait), samples / rate)


class Mind:
    def __init__(self) -> None:
        self.llm = OpenRouter()
        self.tts = TTSEngine()
        self.stt = WhisperKit()
        self.mic = PushToTalk()
        self.local = LocalShip()
        self.clients: set = set()
        self.game: GameShip | None = None
        self.voice = Voice(self.tts, self._sink)
        self.agent = BridgeAgent(self.llm, self.local, self.voice.say)
        self.enemy = EnemyAgent(self.llm, self._say_external, self._enemy_command)
        self.port = PortControl(self.llm, self._say_external)
        self.director = Director(self.llm, self._say_external, self._director_command, self._register_commander,
                                 news=self._fleet_news)
        # the Captain's log is private: the story reads it, the crew does not
        self.agent.campaign = lambda: [c for c in self.director.campaign if not c.startswith("captain's log:")]
        self.agent.war = lambda: self.director.war.crew_view()
        self.agent.mood = lambda: self.director.mood
        self.turns: asyncio.Queue = asyncio.Queue()
        self.last_activity = time.monotonic()   # the Captain spoke or something was reported
        self.captain_t = 0.0                     # the last time the Captain spoke
        self.lang_file = REPO_ROOT / "mind" / ".cache" / "captain_lang.txt"
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

    async def _port_call(self, cue: str, delay: float) -> None:
        """Port Aurelius Control speaks up (after the entry's glow has faded, or as Eagle touches down)."""
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
            if not st or not self.clients:
                continue
            idle = time.monotonic() - max(self.last_activity, self.voice.busy_until)
            hostile = any(str(c.get("status", "")).startswith("hostile") and "retreating" not in str(c.get("status", ""))
                          for c in st.get("contacts", []) or [])
            if hostile or st.get("alert") == "red" or idle < random.uniform(100, 160) or time.monotonic() - last_chat < 240:
                continue
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
            self.voice.low_priority = True
            try:
                t = await self.agent.handle_event(
                    f"bridge: a quiet moment on watch", self.lang,
                    ask=(f"A quiet moment: {pair[0]} and {pair[1]} exchange one or two short, natural lines about {topic}, "
                         "in character, knowing the Captain can hear (they may include the Captain with a glance). No orders, "
                         "no reports, no tools except speak; at most two lines in total."))
                log.info("quiet moment (%s, %s): %s", pair[0], pair[1], " | ".join(f"{s}: {x}" for s, x in t.lines))
            finally:
                self.voice.low_priority = False

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
        while True:
            await asyncio.sleep(5)
            st = self.game.state if (self.game and self.game.state) else None
            if not st or not self.clients:
                continue
            flags = tactical_flags(st)
            now = time.monotonic()
            # in a fight the bridge is never silent: only the Captain's own words hold the check back
            key = "|".join(sorted(f.split(":", 1)[0] for f in flags))
            # (the event queue itself waits for a gap in the voices before the officer speaks)
            if not flags or now - self.captain_t < 10 or now - last_t < 40 or (key == last_key and now - last_t < 100):
                continue
            last_t, last_key = now, key
            log.info("tactical check: %s", flags)
            self.last_activity = now
            await self.turns.put(("\x00event:bridge: tactical check — " + "; ".join(flags), self.lang))

    async def story_watch(self) -> None:
        """The war never stalls: when nothing has moved the story for a long while (no fight, no transit under way),
        the director decides what happens — Rourke presses the Captain, or the war comes to the Aquila."""
        while True:
            await asyncio.sleep(15)
            st = self.game.state if (self.game and self.game.state) else None
            if not st or not self.clients or not self.director.campaign or self.director.busy:
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
                    while self.voice.busy_s() > 1.2 and self.turns.empty():
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
                    try:
                        ask = TACTICAL_ASK if any(e.startswith("bridge: tactical check") for e in events) else None
                        t = await self.agent.handle_event(" | ".join(events), self.lang, ask=ask)
                    finally:
                        self.voice.low_priority = False
                    log.info("event turn %.2fs: %s", t.t_end, " | ".join(f"{s}: {x}" for s, x in t.lines) or "(no report)")
                    continue
                dropped = self.voice.drop_low_priority()      # the Captain speaks: pending reports can wait
                if dropped:
                    log.info("captain speaks: %d unspoken report lines dropped", dropped)
                if lang != self.lang:
                    self.lang = lang
                    self.lang_file.parent.mkdir(parents=True, exist_ok=True)
                    self.lang_file.write_text(lang)
                entry = captains_log_entry(text)
                if entry is not None:
                    # the Captain dictates the log: recorded (a chirp from the console), remembered by the story
                    self.record_log(entry)
                    continue
                st_now = self.game.state if (self.game and self.game.state) else {}
                if "New Ravenna" in str(st_now.get("captain", "")) and for_port(text):
                    self.director.note(f"the Captain to Port Aurelius Control: {text}")
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
                t = await self.agent.handle(text, lang)
                for name, args_, res in t.actions:
                    if name == "end_transmission":
                        self.enemy.open = False
                    if name == "hail" and res.get("ok") and str(args_.get("contact_id", "")).lower() == "fleet":
                        await self.director.admiral_reply(str(args_.get("message", "")), lang, self._battle_state())
                    if name == "hail" and res.get("ok") and "Mandate" in str(res.get("detail", "")) \
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

    async def handle_client(self, ws) -> None:  # noqa: ANN001
        self.clients.add(ws)
        self.game = GameShip(lambda m: ws.send(json.dumps(m, ensure_ascii=False)))
        await ws.send(json.dumps({"type": "status", "crew": {k: v.title for k, v in CREW.items()}, "rate": self.tts.sample_rate}))
        log.info("game connected")
        try:
            async for raw in ws:
                if isinstance(raw, bytes):
                    continue
                msg = json.loads(raw)
                kind = msg.get("type")
                if kind == "hello":
                    # a new game session: the crew starts a fresh conversation (the ship state is new too)
                    self.agent.history.clear()
                    self.enemy.reset()
                    self.port.reset()
                    log.info("new game session: conversation reset (the war waits for the Captain's choice)")
                elif kind == "campaign":
                    # the Captain chose in the title menu: a new war, or the saved one
                    if msg.get("mode") == "continue":
                        ok = self.director.load()
                        log.info("campaign continued (war map %s): %s, %d story notes", "loaded" if ok else "missing",
                                 self.director.war.current, len(self.director.campaign))
                        # the war resumes: the director decides what the Aquila meets now (after the XO's welcome)
                        asyncio.create_task(self.director.on_event(
                            f"director: campaign resumed — the Aquila is back on patrol in the {self.director.war.current} system",
                            self.lang, self._battle_state()))
                    else:
                        self.director.reset()
                        log.info("new campaign")
                    asyncio.create_task(self._send_sector())
                elif kind == "ship_state":
                    self.game.state = msg.get("state", {})
                elif kind == "event":
                    text = msg.get("text", "")
                    self.game.events.append(text)
                    if text.startswith("director:"):
                        asyncio.create_task(self.director.on_event(text, self.lang, self._battle_state()))
                    elif text.startswith("story:"):
                        self.director.note(text.split(":", 1)[1].strip())   # remembered, no new beat
                    port_cue = stimulus_for(text)
                    if port_cue:
                        asyncio.create_task(self._port_call(port_cue, 6.0 if "left the plot" in text else 1.5))
                    fallen = _fallen(text)
                    if fallen:
                        self.director.note("fallen: " + "; ".join(fallen))
                    gone = _re.search(r"\((T-\d+)[,)]", text)
                    if gone and ("destroyed" in text or "left sensor range" in text):
                        self.enemy.ship_destroyed(gone.group(1))   # nobody left on that ship to answer a hail
                    if msg.get("report"):
                        self.last_activity = time.monotonic()
                        await self.turns.put(("\x00event:" + text, self.lang))
                elif kind == "command_result":
                    self.game.resolve(msg)
                elif kind == "player_text":
                    self.last_activity = self.captain_t = time.monotonic()
                    text = msg.get("text", "").strip()
                    if text:
                        await self.turns.put((text, msg.get("lang") or detect_lang(text)))
                elif kind == "ptt":
                    if msg.get("down"):
                        ok = self.mic.start()
                        if not ok:
                            await ws.send(json.dumps({"type": "status", "mic": "unavailable"}))
                    else:
                        pcm = self.mic.stop()
                        asyncio.create_task(self._recognise(pcm))
        finally:
            self.clients.discard(ws)
            log.info("game disconnected")

    async def _recognise(self, pcm: bytes) -> None:
        if len(pcm) < 16000 * 2 * 0.3:
            return
        t0 = time.perf_counter()
        text, lang = await self.stt.transcribe(pcm)
        log.info("STT %.2fs [%s] %s", time.perf_counter() - t0, lang, text)
        self.captain_t = time.monotonic()
        await self._sink("json", {"type": "transcript", "text": text, "lang": lang})
        if text:
            await self.turns.put((text, lang))

    async def serve(self) -> None:
        import websockets
        await self.stt.start()
        asyncio.create_task(self.voice.run())
        asyncio.create_task(self.turn_worker())
        asyncio.create_task(self.quiet_moments())
        asyncio.create_task(self.story_watch())
        asyncio.create_task(self.tactical_watch())
        asyncio.create_task(self.enemy_tactics())
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self.tts.warm, "en", [o.voice for o in CREW.values()])
        log.info("astra-mind listening on ws://%s:%d", HOST, PORT)
        async with websockets.serve(self.handle_client, HOST, PORT, max_size=2 ** 22):
            await asyncio.Future()


# ---------------------------------------------------------------------------------------------- offline tools
async def offline_turns(utterances: list[str], out_dir: Path, check_audio: bool) -> None:
    llm, tts = OpenRouter(), TTSEngine()
    stt = WhisperKit() if check_audio else None
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

    voice = Voice(tts, sink)
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
    ap.add_argument("--out", default=str(REPO_ROOT / "mind" / ".cache" / "turns"))
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
    """Names of the crew killed in a report ("... Petty Officer Amara Diallo (weapons, from Mars) and ... killed; ...")."""
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


TACTICAL_ASK = ("A tactical check of the fight (the facts above come from the plot, they are true now). The XO, or the "
                "officer whose station it concerns, tells the Captain the single most important problem in one short "
                "sentence and recommends a concrete order the Captain could give (a course or intercept, a target, a "
                "flight group, shields). Do not act on your own and do not repeat what was said in the last minute. If "
                "nothing here really needs the Captain now, reply with the word SILENT and call no tool.")


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
