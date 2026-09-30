"""The mind's whole voice glue, end to end, without the game and without the language model.

A fake game (a WebSocket stand-in that timestamps everything the mind sends), a fake microphone that plays a recorded order in
real time, the real recogniser, the real voices, the real speech floor and the server's own message handling; only the crew's
language model is replaced by an agent that answers with a canned line. It measures what the Captain lives:

  - from the key going up to the transcript reaching the game
  - from the key going up to the first word of the answer (with the model taken out: the mind's own share of the wait)
  - from the key going down to the officer who was talking falling silent (the `cancel` and the last audio)
  - that nothing else speaks until the answer has, and that the floor messages follow the key

Run from mind/ (a dummy key is set: nothing is ever sent to the model):

    uv run python -m bench.voice_e2e [--lang it|en]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import struct
import sys
import time
import types
from types import SimpleNamespace

import numpy as np

os.environ.setdefault("OPENROUTER_API_KEY", "not-a-real-key")           # the client wants one; this run never calls the model

from astra_mind.voice_audio import f32_to_pcm16  # noqa: E402

from . import voice_corpus as vc  # noqa: E402
from .voice_pipeline import FakeDevice  # noqa: E402

ORDERS = {
    "it": ("Alice", "Timoniere, rotta due uno sette, avanti tutta."),
    "en": ("Samantha", "Helm, come to heading two one seven, full ahead."),
}
REPLY = {"it": "Agli ordini, Capitano: rotta due-uno-sette, avanti tutta.", "en": "Aye, Captain: heading two one seven, full ahead."}
LONG = {"it": "Capitano, tutti i ponti riferiscono di essere pronti. La sala macchine conferma che il reattore regge al novanta per cento, il tattico ha i railgun carichi "
              "e la squadriglia Alpha è sul ponte, pronta al lancio non appena darà l'ordine.",
        "en": "Captain, all decks report ready. Engineering confirms the reactor is holding at ninety percent, tactical has the railguns loaded and Alpha squadron "
              "is on the deck, ready to launch as soon as you give the order."}


class FakeWS:
    """What the game is to the mind: receives everything it sends (with the time), and hands it the messages the game would send."""

    def __init__(self) -> None:
        self.sent: list[tuple[float, str, object]] = []
        self.inbox: asyncio.Queue = asyncio.Queue()

    async def send(self, data) -> None:  # noqa: ANN001
        t = time.perf_counter()
        if isinstance(data, bytes):
            self.sent.append((t, "audio", (struct.unpack("<I", data[:4])[0], (len(data) - 4) / 2)))
        else:
            m = json.loads(data)
            self.sent.append((t, m.get("type", "?"), m))

    def push(self, msg: dict) -> float:
        self.inbox.put_nowait(json.dumps(msg))
        return time.perf_counter()

    def __aiter__(self) -> "FakeWS":
        return self

    async def __anext__(self) -> str:
        item = await self.inbox.get()
        if item is None:
            raise StopAsyncIteration
        return item

    def since(self, t0: float, kind: str) -> list[tuple[float, object]]:
        return [(t, m) for t, k, m in self.sent if k == kind and t >= t0]

    async def wait_for(self, t0: float, kind: str, pred=None, timeout: float = 20.0):  # noqa: ANN001
        end = time.perf_counter() + timeout
        while time.perf_counter() < end:
            for t, m in self.since(t0, kind):
                if pred is None or pred(m):
                    return t, m
            await asyncio.sleep(0.005)
        return None


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="it", choices=sorted(ORDERS))
    args = ap.parse_args()
    lang = args.lang

    fake = types.ModuleType("sounddevice")
    fake.RawInputStream = FakeDevice.RawInputStream
    fake.query_devices = FakeDevice.query_devices
    sys.modules["sounddevice"] = fake

    from astra_mind.crew import CREW
    from astra_mind.server import Mind

    mind = Mind()
    mind.lang = lang
    mind.stt.prior = lang
    replies: list[str] = []
    marks: dict[str, float] = {}

    async def stub_handle(text: str, language: str):  # noqa: ANN202
        """The crew's model, replaced: the helm answers with a canned line, as a turn that produced one line."""
        replies.append(text)
        marks["agent_called"] = time.perf_counter()
        await mind.agent.say("helm", REPLY[lang], language, "focused")
        marks["agent_said"] = time.perf_counter()
        return SimpleNamespace(actions=[], lines=[("helm", REPLY[lang])], t_first_line=0.0, t_end=0.0, cost=0.0, error=None)

    async def no_model(*_a, **_k):  # noqa: ANN002, ANN003, ANN202
        return None

    mind.agent.handle = stub_handle
    mind.memory.maybe_read = no_model                    # (the memory keeper would ask the model what to remember)
    print("starting the recogniser and the voices...", flush=True)
    await mind.stt.start()
    if not await mind.stt.ready():
        print("no speech recogniser available")
        return 1
    voices = [o.voice for o in CREW.values()]
    await asyncio.get_running_loop().run_in_executor(None, mind.tts.warm, lang, voices)
    tasks = [asyncio.create_task(mind.voice.run()), asyncio.create_task(mind.turn_worker())]
    ws = FakeWS()
    tasks.append(asyncio.create_task(mind.handle_client(ws)))
    await asyncio.sleep(0.2)
    ws.push({"type": "hello"})
    await asyncio.sleep(0.2)

    voice_name, text = ORDERS[lang]
    speech = f32_to_pcm16(vc.say_clip(voice_name, text))
    sp = np.frombuffer(speech, dtype="<i2")
    sp_s = len(sp) / 16000
    bad: list[str] = []
    out: dict = {"lang": lang, "order": text}

    def enqueue_speech() -> None:
        with FakeDevice.signal_lock:
            FakeDevice.queue = np.concatenate([FakeDevice.queue, sp])

    async def press_and_say(hold_extra: float = 0.2) -> float:
        """The Captain presses the key, starts talking a quarter second later, lets go 0.2 s after his last word. Returns the time of the release."""
        ws.push({"type": "ptt", "down": True})
        await asyncio.sleep(0.25)
        enqueue_speech()
        await asyncio.sleep(sp_s + hold_extra)
        return ws.push({"type": "ptt", "down": False})

    # a first, silent press: opening the device is a one-off cost (the mind keeps the microphone open afterwards)
    ws.push({"type": "ptt", "down": True})
    await asyncio.sleep(0.4)
    ws.push({"type": "ptt", "down": False})
    await asyncio.sleep(1.5)

    # ---------------------------------------------------------------- 1. an order on a quiet bridge
    t_press = time.perf_counter()
    t_up = await press_and_say()
    tr = await ws.wait_for(t_press, "transcript")
    ans = await ws.wait_for(t_up, "audio_begin")
    if tr is None:
        bad.append("no transcript reached the game")
    else:
        out["transcript"] = tr[1]["text"]
        out["key_up_to_transcript_ms"] = round((tr[0] - t_up) * 1000)
    if ans is not None:
        out["key_up_to_first_word_ms"] = round((ans[0] - t_up) * 1000)
        out["transcript_to_first_word_ms"] = round((ans[0] - tr[0]) * 1000) if tr else None
        if tr and "agent_called" in marks:
            out["transcript_to_the_crew_turn_ms"] = round((marks["agent_called"] - tr[0]) * 1000)
            out["the_crew_line_queued_to_first_word_ms"] = round((ans[0] - marks["agent_said"]) * 1000)
    else:
        bad.append("the answer never began")
    await asyncio.sleep(3.0)
    if not replies:
        bad.append("the order never reached the crew's turn")

    # ---------------------------------------------------------------- 2. the Captain talks over an officer
    t0 = time.perf_counter()
    await mind.voice.say("xo", LONG[lang], lang, "calm")
    await ws.wait_for(t0, "audio_begin", lambda m: m.get("speaker") == "xo", timeout=5.0)
    await asyncio.sleep(1.6)
    t_down = ws.push({"type": "ptt", "down": True})
    cancel = await ws.wait_for(t_down, "cancel", timeout=2.0)
    if cancel is None:
        bad.append("the officer was never told to stop")
    else:
        out["key_down_to_cancel_ms"] = round((cancel[0] - t_down) * 1000)
        out["cancel_fade_ms"] = cancel[1].get("fade_ms")
        out["cancel_reason"] = cancel[1].get("reason")
    await asyncio.sleep(0.25)
    enqueue_speech()
    await asyncio.sleep(sp_s + 0.2)
    t_up2 = ws.push({"type": "ptt", "down": False})
    ans2 = await ws.wait_for(t_up2, "audio_begin", lambda m: m.get("speaker") == "helm", timeout=10.0)
    if ans2 is None:
        bad.append("no answer after the Captain talked over the officer")
    else:
        out["over_key_up_to_first_word_ms"] = round((ans2[0] - t_up2) * 1000)
    await asyncio.sleep(1.0)
    # whoever spoke between the key going down and the answer beginning must be nobody but the answer
    if ans2 is not None:
        for t, m in ws.since(t_down, "audio_begin"):
            if t < ans2[0] - 0.001 and m.get("speaker") != "helm":
                bad.append(f"line of {m.get('speaker')} began while the Captain held the floor")
    floor = [(round((t - t_down) * 1000), m.get("state")) for t, m in ws.since(t_down, "floor")]
    out["floor_after_key_down"] = floor

    # ---------------------------------------------------------------- 3. a typed order
    t_typed = ws.push({"type": "player_text", "text": text.split(",")[0] + ", avanti tutta.", "lang": lang})
    ans3 = await ws.wait_for(t_typed, "audio_begin", timeout=10.0)
    if ans3 is None:
        bad.append("no answer to a typed order")
    else:
        out["typed_to_first_word_ms"] = round((ans3[0] - t_typed) * 1000)

    await asyncio.sleep(2.0)
    dropped = [m for _, m in ws.since(0, "line_dropped")]
    out["dropped_lines"] = [(m.get("reason"), m.get("speaker")) for m in dropped]
    out["stats"] = dict(mind.voice.stats)
    print(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    ws.inbox.put_nowait(None)
    for t in tasks:
        t.cancel()
    await mind.stt.close()
    mind.mic.close()
    if bad:
        print("PROBLEMS:", *bad, sep="\n  - ")
        return 1
    print("end to end: ok")
    return 0


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=os.environ.get("BENCH_LOG", "WARNING"))
    sys.exit(asyncio.run(main()))
