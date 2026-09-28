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

# the Captain talking to someone on the bridge (not to the enemy on an open channel): names and roles, several languages
import re as _re
_CREW_ADDRESS = _re.compile(
    r"^\W*(serra|ferri|tanaka|voss|martin|nair|mensah|price|numero uno|primo ufficiale|xo|comandante|timon\w*|helm\w*|"
    r"tattic\w*|tactical|ops|operazion\w*|operations|comunicazion\w*|comms?|sensor\w*|scienz\w*|ingegner\w*|"
    r"engineering|volo|flight|plancia|bridge|number one|chiud\w* (il )?canale|close (the )?channel|fine trasmissione|"
    r"end transmission)\b", _re.I)


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
        self.director = Director(self.llm, self._say_external, self._director_command, self._register_commander)
        self.turns: asyncio.Queue = asyncio.Queue()
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
        return await ship.execute(name, args, self.enemy.speaker)

    def _battle_state(self) -> dict[str, Any]:
        st = dict(self.game.state) if (self.game and self.game.state) else dict(self.local.snapshot())
        st["_events"] = (self.game.events if self.game else [])[-8:]
        return st

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
                        t = await self.agent.handle_event(" | ".join(events), self.lang)
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
                to_enemy = ""
                if self.enemy.open:
                    # a channel is open: the words meant for the enemy go over it, the orders stay on the bridge
                    r = await route(self.llm, text, COMMANDERS.get(self.enemy.contact, {}).get("name", "the enemy commander"))
                    log.info("channel open, routed (%s): crew=%r enemy=%r", r.how, r.crew[:60], r.enemy[:60])
                    to_enemy = r.enemy
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
                    self.director.reset()
                    log.info("new game session: conversation reset")
                elif kind == "ship_state":
                    self.game.state = msg.get("state", {})
                elif kind == "event":
                    text = msg.get("text", "")
                    self.game.events.append(text)
                    if text.startswith("director:"):
                        asyncio.create_task(self.director.on_event(text, self.lang, self._battle_state()))
                    gone = _re.search(r"\((T-\d+)[,)]", text)
                    if gone and ("destroyed" in text or "left sensor range" in text):
                        self.enemy.ship_destroyed(gone.group(1))   # nobody left on that ship to answer a hail
                    if msg.get("report"):
                        await self.turns.put(("\x00event:" + text, self.lang))
                elif kind == "command_result":
                    self.game.resolve(msg)
                elif kind == "player_text":
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
        await self._sink("json", {"type": "transcript", "text": text, "lang": lang})
        if text:
            await self.turns.put((text, lang))

    async def serve(self) -> None:
        import websockets
        await self.stt.start()
        asyncio.create_task(self.voice.run())
        asyncio.create_task(self.turn_worker())
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
