"""The live test's sequence replayed through the mind's own glue, in virtual time.

The lead's live test (typed orders, game with -nosound) found the crew's acknowledgements played 30-45 s late, behind older reports
and an enemy's long message. This replays that shape through the real server (`Mind`: the turn worker, the router, the crew's agent
with its priority and preemption, the speech floor, the game messages), with only two things scripted: the crew's language model
(what it answers, and how long it takes) and the voice engine (a fake that speaks 16 characters a second). Time is virtual: a minute
of bridge talk runs in a fraction of a second, every message the game receives is stamped with the virtual clock, and the same
invariants as `voice_floor` are checked on what the game got.

    uv run python -m bench.voice_replay          (from mind/)        -v prints the game's view of each replay
"""
from __future__ import annotations

import asyncio
import json
import os
import struct
import sys
import traceback

os.environ.setdefault("OPENROUTER_API_KEY", "not-a-real-key")             # the client wants one; nothing here ever reaches the network

from astra_mind import models, speech  # noqa: E402
from astra_mind.openrouter import Completion, ToolCall  # noqa: E402
from astra_mind.speech import Prio  # noqa: E402

from .voice_floor import FakeTTS, Rec, Trace, check, run, timeline  # noqa: E402

ARCHON = ("Aquila, qui parla l'Arconte Varek Solm del Mandato Kharon. Siete entrati in uno spazio che appartiene ai Mondi Esterni. "
          "La vostra presenza è un insulto a ogni nave caduta alle Porte. Vi concedo una sola possibilità di ritirarvi prima che la mia flotta "
          "apra il fuoco. Abbassate le armi e arrendete la vostra nave entro due minuti.")

# what the crew's model answers, and how long it takes, by what it is asked (a piece of the Captain's words or of the event)
SCRIPT: dict[str, tuple[float, list[tuple[str, str, str]]]] = {
    "Timoniere, prua sul Cocytus": (0.88, [("helm", "Timoniere: agli ordini, prua sul Cocytus e la tengo lì.", "focused")]),
    "Tanaka, metti il Cocytus": (1.46, [("ops", "Operazioni: il Cocytus è sullo schermo principale.", "calm")]),
    "Tattico, fuoco sul Cocytus": (0.95, [("tactical", "Tattico: apro il fuoco sul Cocytus finché non cade.", "cold")]),
    "Alpha squadron": (1.0, [("flight", "Volo: la squadriglia Alpha sta decollando, sei caccia in mare entro tre minuti.", "calm")]),
    "hostile contact T-22": (1.0, [("sensors", "Sensori: contatto T-22 rilevamento zero nove zero, distanza novanta chilometri, si avvicina.", "focused")]),
    "reactor output": (1.0, [("engineering", "Macchine: il reattore è all'ottanta per cento, il circuito due è caldo ma regge.", "calm")]),
    "second contact": (1.0, [("sensors", "Sensori: secondo contatto rilevamento uno otto zero, distanza sessanta chilometri.", "focused")]),
    "opening this channel": (1.5, [("solm", ARCHON, "cold")]),
    "stand by": (0.05, []),                                                  # (the warm-up request the server sends when a game says hello: nothing is said)
    "missiles inbound": (0.8, [("tactical", "Missili in arrivo, rilevamento due sette zero! Prepararsi all'impatto!", "urgent")]),
}


class FakeGame:
    """What the game is to the mind (a WebSocket stand-in), on the virtual clock: everything it receives is recorded the way `voice_floor`
    records it, so the same trace and the same invariants apply; the messages it sends are queued for the mind."""

    def __init__(self) -> None:
        self.rec = Rec()
        self.inbox: asyncio.Queue = asyncio.Queue()

    async def send(self, data) -> None:  # noqa: ANN001
        t = asyncio.get_running_loop().time()
        if isinstance(data, bytes):
            self.rec.events.append((t, "audio", (struct.unpack("<I", data[:4])[0], len(data) - 4)))
        else:
            self.rec.events.append((t, "json", json.loads(data)))

    def push(self, msg: dict) -> None:
        self.inbox.put_nowait(json.dumps(msg))

    def __aiter__(self) -> "FakeGame":
        return self

    async def __anext__(self) -> str:
        item = await self.inbox.get()
        if item is None:
            raise StopAsyncIteration
        return item


class Replay:
    """A mind with a fake game and a scripted model, its tasks running (the speech floor, the turn worker, the connection)."""

    def __init__(self) -> None:
        self.game = FakeGame()
        self.log: list[str] = []
        self.calls = 0                                             # model calls in flight
        self.script = dict(SCRIPT)                                 # (a replay may change what the model does)
        self.asked: list[tuple[float, str, str]] = []             # (when, the script's key, what the model was asked)
        self.tasks: list[asyncio.Task] = []
        self.mind = None

    async def __aenter__(self) -> "Replay":
        from astra_mind.server import Mind
        self._ledger = models.LEDGER.write_file
        models.LEDGER.write_file = False                                  # (no spend file written)
        m = self.mind = Mind()
        m.lang = "it"
        m.tts = m.voice.tts = FakeTTS()
        m.llm.chat = self._chat                                            # the model the crew, the enemy and the router would call
        m.memory.maybe_read = self._nothing
        self.tasks = [asyncio.create_task(m.voice.run()), asyncio.create_task(m.turn_worker()), asyncio.create_task(m.handle_client(self.game))]
        await asyncio.sleep(0.1)
        self.game.push({"type": "hello"})
        await asyncio.sleep(0.1)
        return self

    async def __aexit__(self, *exc) -> None:  # noqa: ANN002
        self.game.inbox.put_nowait(None)
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        models.LEDGER.write_file = self._ledger

    @staticmethod
    async def _nothing(*_a, **_k) -> None:  # noqa: ANN002, ANN003
        return None

    async def _chat(self, *, messages, tools=None, tool_choice="auto", on_tool_call=None, **_kw) -> Completion:  # noqa: ANN001, ANN003
        """The scripted model: waits as long as the script says (virtual time), then makes the calls the script has for what it was asked."""
        t = asyncio.get_running_loop().time()
        asked = str(messages[-1].get("content", ""))
        names = {x["function"]["name"] for x in (tools or [])}
        for key, (delay, calls) in self.script.items():
            if key in asked:
                break
        else:
            self.log.append(f"{t:7.2f} the model was asked something the script does not know: {asked[:80]!r}")
            return Completion(content="SILENT", provider="script", model="script")
        self.asked.append((t, key, asked))
        self.calls += 1
        try:
            await asyncio.sleep(delay)
            comp = Completion(provider="script", model="script")
            for speaker, text, tone in calls:
                if "transmit" in names:
                    call = ToolCall(name="transmit", arguments_raw=json.dumps({"text": text, "tone": tone}))
                else:
                    call = ToolCall(name="speak", arguments_raw=json.dumps({"speaker": speaker, "text": text, "tone": tone}))
                comp.tool_calls.append(call)
                if on_tool_call is not None:
                    res = on_tool_call(call)
                    if hasattr(res, "__await__"):
                        await res
            return comp
        finally:
            self.calls -= 1

    # ------------------------------------------------------------------------------------------ what the game does
    async def at(self, t: float, msg: dict) -> None:
        await asyncio.sleep(max(0.0, t - self.now()))
        self.game.push(msg)

    def event(self, t: float, text: str):  # noqa: ANN201
        return self.at(t, {"type": "event", "text": text, "report": True})

    def order(self, t: float, text: str):  # noqa: ANN201
        return self.at(t, {"type": "player_text", "text": text, "lang": "it"})

    def now(self) -> float:
        return asyncio.get_running_loop().time()

    async def settle(self, extra: float = 2.0, limit: float = 240.0) -> None:
        t0 = self.now()
        m = self.mind
        while (m.voice._queue or m.voice._cur is not None or not m.turns.empty() or m.agent.busy() or m.voice.held or self.calls) and self.now() - t0 < limit:
            await asyncio.sleep(0.05)
        await asyncio.sleep(extra)

    def trace(self) -> Trace:
        return Trace.of(self.game.rec)


def _stamp(tr: Trace, text_part: str) -> int | None:
    """The id of the line (spoken or dropped) that has this text in it."""
    for i, p in tr.line.items():
        if text_part in p["text"]:
            return i
    return None


LAST: list[Replay] = []


# ------------------------------------------------------------------------------------------------ the replays
async def r1_live_sequence() -> list[str]:
    """The lead's live sequence through the real server: reports and an enemy message queued, three typed orders in Italian answered ~1 s
    after each: every acknowledgement is heard right after the order and before anything queued; the enemy's message is cut and comes back
    short; nothing is said late."""
    async with Replay() as r:
        LAST[:] = [r]
        await asyncio.sleep(44.0)
        jobs = [
            r.event(45.2, "flight: Alpha squadron is launching from the flight deck"),
            r.event(49.5, "sensors: hostile contact T-22 detected, bearing 090, range 90 km"),
            r.event(52.8, "engineering: reactor output at 80 percent, coolant loop two warm"),
            r.event(54.0, "transmission: T-21 — the Archon calls the Aquila"),
            r.event(60.0, "sensors: second contact detected, bearing 180, range 60 km"),
            r.order(57.9, "Timoniere, prua sul Cocytus e tienila lì"),
            r.order(67.4, "Tanaka, metti il Cocytus sullo schermo"),
            r.order(76.6, "Tattico, fuoco sul Cocytus finché non cade"),
        ]
        await asyncio.gather(*[asyncio.ensure_future(j) for j in jobs])
        await r.settle(3.0)
        tr = r.trace()
        m = r.mind
        bad = check(tr, m.voice.enqueued)
        if r.log:
            bad += r.log
        order_t = {"helm": 57.9, "ops": 67.4, "tactical": 76.6}
        for spk, t_order in order_t.items():
            ids = [i for i in tr.order() if tr.line[i]["speaker"] == spk and tr.line[i]["priority"] == "answer"]
            if not ids:
                bad.append(f"the answer of the {spk} was never heard")
                continue
            aid = ids[0]
            delay = SCRIPT[{"helm": "Timoniere, prua sul Cocytus", "ops": "Tanaka, metti il Cocytus", "tactical": "Tattico, fuoco sul Cocytus"}[spk]][0]
            late = tr.begin[aid] - t_order - delay
            if late > 0.6:
                bad.append(f"the {spk}'s answer began {late:.2f} s after the model had finished (order at {t_order}, heard at {tr.begin[aid]:.1f})")
            before = [i for i in tr.order() if t_order < tr.begin[i] < tr.begin[aid] and tr.line[i]["priority"] != "answer"]
            if before:
                bad.append(f"after the order to the {spk}, {[tr.line[i]['speaker'] for i in before]} spoke before the answer")
            for i in tr.order():
                if tr.begin[i] <= t_order < tr.end.get(i, tr.begin[i]) and tr.line[i]["priority"] != "answer":
                    if tr.reason.get(i) != "cut" or tr.cancel_t.get(i, 1e9) - t_order > 0.6:
                        bad.append(f"line {i} ({tr.line[i]['speaker']}) was talking at the order to the {spk} and was not stopped within 0.6 s")
        # nothing said later than the age a report is worth
        events_at = {"flight": 45.2, "sensors": 49.5, "engineering": 52.8}
        limit = speech.REPORT_MAX_AGE_S[Prio.NORMAL]
        for i in tr.order():
            p = tr.line[i]
            if p["priority"] == "normal" and p["speaker"] in events_at and tr.begin[i] - events_at[p["speaker"]] > limit + 0.5:
                bad.append(f"the report of {p['speaker']} was said {tr.begin[i] - events_at[p['speaker']]:.1f} s after its event (limit {limit:.0f} s)")
        arch = [i for i in tr.order() if tr.line[i]["speaker"] == "solm"]
        if not arch:
            bad.append("the enemy's message was never heard")
        else:
            if tr.reason.get(arch[-1]) != "done":
                bad.append("the enemy's message never came to its end")
            elif "Abbassate le armi" not in tr.line[arch[-1]]["text"]:
                bad.append("what the enemy asks was never said")
        return bad


async def r2_old_news_is_not_reported() -> list[str]:
    """News that waited for a quiet bridge until even its newest item is old is not reported; in a fresh batch the old item says how old it is;
    news that arrived after the bridge fell quiet is reported at once."""
    # the bridge is held by the live test's long message (64 words, about 20 s): the enemy's own budget (enemy.MAX_WORDS) would
    # clip it now, and it is the floor's rules for old news that are tested here, not how long the enemy may speak
    from astra_mind import enemy
    budget = enemy.MAX_SENTENCES, enemy.MAX_WORDS
    enemy.MAX_SENTENCES, enemy.MAX_WORDS = 99, 999
    try:
        return await _r2()
    finally:
        enemy.MAX_SENTENCES, enemy.MAX_WORDS = budget


async def _r2() -> list[str]:
    async with Replay() as r:
        LAST[:] = [r]
        await asyncio.sleep(10.0)
        # the enemy speaks for a long time; a routine report arrives in the middle of it and has to wait for quiet...
        jobs = [r.event(10.0, "transmission: T-21 — the Archon calls the Aquila"),
                r.event(14.0, "engineering: reactor output at 80 percent, coolant loop two warm"),
                # ...and a second message, with news that is old when it ends and news that arrived just before the end
                r.event(60.0, "transmission: T-21 — the Archon calls the Aquila again"),
                r.event(62.0, "engineering: reactor output at 85 percent, coolant loop two warm"),
                r.event(79.0, "sensors: hostile contact T-22 detected, bearing 090, range 90 km"),
                # ...and news on a quiet bridge
                r.event(120.0, "sensors: second contact detected, bearing 180, range 60 km")]
        await asyncio.gather(*[asyncio.ensure_future(j) for j in jobs])
        await r.settle(3.0)
        tr = r.trace()
        bad = check(tr, r.mind.voice.enqueued) + r.log
        first_batch = [a for t, k, a in r.asked if k == "reactor output" and t < 50]
        if first_batch:
            bad.append("the model was asked to report news that had waited too long for a quiet bridge")
        mixed = [a for t, k, a in r.asked if 60 < t < 100 and k != "opening this channel"]
        if len(mixed) != 1 or "[happened" not in mixed[0] or "reactor output at 85" not in mixed[0]:
            bad.append(f"the batch with old and fresh news was not one report with the old item's age: {mixed!r}")
        if not any(p["speaker"] == "sensors" and "T-22" in p["text"] for p in tr.line.values()):
            bad.append("the fresh news of the batch was not reported")
        if not any(p["speaker"] == "sensors" and "secondo contatto" in p["text"] for p in tr.line.values()):
            bad.append("news on a quiet bridge was not reported")
        if any(p["speaker"] == "engineering" for p in tr.line.values()):
            bad.append("a routine report of old news was spoken")
        return bad


async def r3_warning_during_a_hail() -> list[str]:
    """A warning of danger does not wait for the bridge to fall quiet: it is heard within about two seconds of the event, cutting the long message."""
    async with Replay() as r:
        LAST[:] = [r]
        await asyncio.sleep(10.0)
        jobs = [r.event(10.0, "transmission: T-21 — the Archon calls the Aquila"), r.event(20.0, "tactical: missiles inbound, bearing 270")]
        await asyncio.gather(*[asyncio.ensure_future(j) for j in jobs])
        await r.settle(3.0)
        tr = r.trace()
        bad = check(tr, r.mind.voice.enqueued) + r.log
        warn = [i for i in tr.order() if tr.line[i]["priority"] == "urgent"]
        if not warn:
            return bad + ["the warning was never heard"]
        heard = tr.begin[warn[0]] - 20.0
        if heard > 0.8 + 1.5:
            bad.append(f"the warning was heard {heard:.1f} s after the event")
        arch = [i for i in tr.order() if tr.line[i]["speaker"] == "solm"]
        if not arch or tr.reason.get(arch[0]) != "cut" or tr.cancel_t[arch[0]] > tr.begin[warn[0]] + 0.1:
            bad.append("the enemy's message was not stopped for the warning")
        elif len(arch) < 2 or tr.reason.get(arch[-1]) != "done" or "Abbassate le armi" not in tr.line[arch[-1]]["text"]:
            bad.append("what was left of the enemy's message never came back after the warning")
        return bad


async def r4_order_while_the_enemys_message_is_written() -> list[str]:
    """The Captain types an order while the model is still writing the enemy's message (three seconds): the order is not made to wait for it, and
    the message is written and spoken after the answer."""
    async with Replay() as r:
        LAST[:] = [r]
        r.script["opening this channel"] = (3.0, r.script["opening this channel"][1])
        await asyncio.sleep(10.0)
        jobs = [r.event(10.0, "transmission: T-21 — the Archon calls the Aquila"), r.order(10.6, "Timoniere, prua sul Cocytus e tienila lì")]
        await asyncio.gather(*[asyncio.ensure_future(j) for j in jobs])
        await r.settle(3.0)
        tr = r.trace()
        bad = check(tr, r.mind.voice.enqueued) + r.log
        ack = [i for i in tr.order() if tr.line[i]["speaker"] == "helm"]
        arch = [i for i in tr.order() if tr.line[i]["speaker"] == "solm"]
        if not ack:
            return bad + ["the order was never answered"]
        late = tr.begin[ack[0]] - 10.6 - SCRIPT["Timoniere, prua sul Cocytus"][0]
        if late > 0.6:
            bad.append(f"the answer began {late:.2f} s after the model had finished: the order waited for the enemy's message to be written")
        if not arch:
            bad.append("the enemy's message was never written and said after the order")
        elif tr.begin[arch[0]] < tr.begin[ack[0]]:
            bad.append("the enemy's message came before the answer")
        return bad


async def r5_warning_cut_off_by_an_order() -> list[str]:
    """The Captain types an order while the model is still writing a warning of danger: the order is answered at once, and the warning is written and said after
    the answer (the danger is not lost)."""
    async with Replay() as r:
        LAST[:] = [r]
        await asyncio.sleep(10.0)
        r.script["missiles inbound"] = (2.0, r.script["missiles inbound"][1])
        jobs = [r.event(10.0, "tactical: missiles inbound, bearing 270"), r.order(10.5, "Timoniere, prua sul Cocytus e tienila lì")]
        await asyncio.gather(*[asyncio.ensure_future(j) for j in jobs])
        await r.settle(3.0)
        tr = r.trace()
        bad = check(tr, r.mind.voice.enqueued) + r.log
        ack = [i for i in tr.order() if tr.line[i]["priority"] == "answer"]
        warn = [i for i in tr.order() if tr.line[i]["priority"] == "urgent"]
        if not ack:
            return bad + ["the order was never answered"]
        late = tr.begin[ack[0]] - 10.5 - SCRIPT["Timoniere, prua sul Cocytus"][0]
        if late > 0.6:
            bad.append(f"the answer began {late:.2f} s after the model had finished")
        if not warn:
            bad.append("the warning of danger was lost when the Captain took the floor")
        elif tr.begin[warn[0]] < tr.begin[ack[0]]:
            bad.append("the warning came before the answer to the Captain")
        return bad


SCENARIOS = [r1_live_sequence, r2_old_news_is_not_reported, r3_warning_during_a_hail, r4_order_while_the_enemys_message_is_written,
             r5_warning_cut_off_by_an_order]


def main() -> int:
    verbose = "-v" in sys.argv
    failed = 0
    for sc in SCENARIOS:
        try:
            bad = run(sc())
        except Exception:  # noqa: BLE001
            bad = ["crashed:\n" + traceback.format_exc()]
        print(f"{'ok  ' if not bad else 'FAIL'} {sc.__name__:28s} {(sc.__doc__ or '').strip().splitlines()[0][:100]}")
        for msg in bad:
            print("       -", msg)
        if verbose and LAST:
            for row in timeline(LAST[0].game.rec):
                print("     |", row)
            print("     | voice stats:", dict(LAST[0].mind.voice.stats))
        failed += bool(bad)
    print(f"\n{len(SCENARIOS) - failed}/{len(SCENARIOS)} replays pass")
    return 1 if failed else 0


if __name__ == "__main__":
    import logging
    logging.basicConfig(level=os.environ.get("BENCH_LOG", "WARNING"))
    sys.exit(main())
