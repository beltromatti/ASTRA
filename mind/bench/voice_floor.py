"""Scripted scenarios for the speech floor (astra_mind/speech.py): a fake sink records everything the game would receive, a
fake voice engine makes audio of a known length, and the whole thing runs in virtual time (the event loop jumps to the
next timer, so a minute of bridge talk takes milliseconds). Every scenario is checked against the same invariants:

  I1  no subtitle without audio        every announced line has audio, or was cancelled within 0.3 s
  I2  one voice at a time              the lines' audio intervals do not overlap
  I3  no silent drops                  every queued line ends as heard, cancelled, or reported dropped/merged
  I4  paced audio                      never more than LEAD_S (+ one chunk) of audio ahead of real time
  I5  natural gaps                     between two lines at least 80 ms
  I6  subtitle time                    hold_s covers the audio and a second, and the reading time (17 characters/s)
  I7  the Captain first                nobody but an answer starts while the Captain holds the floor; whoever talks is
                                       stopped within 0.6 s of the Captain's first word

Run:  uv run python -m bench.voice_floor           (from mind/)        -v prints the timelines
"""
from __future__ import annotations

import asyncio
import math
import re
import struct
import sys
import traceback
from dataclasses import dataclass, field

from astra_mind import speech
from astra_mind.speech import LEAD_S, Prio, Voice
from astra_mind.tts import SpeechStream

RATE = 24000
CHUNK_S = 0.08
CHUNK = b"\x10\x00" * int(RATE * CHUNK_S)


# ------------------------------------------------------------------------------------------------ virtual time
class VirtualLoop(asyncio.SelectorEventLoop):
    """An event loop whose clock jumps to the next timer instead of waiting for it."""

    def __init__(self) -> None:
        super().__init__()
        self._vt = 0.0

    def time(self) -> float:
        return self._vt

    def _run_once(self) -> None:
        if not self._ready and self._scheduled and not self._stopping:
            self._vt = max(self._vt, self._scheduled[0]._when)
        super()._run_once()


def run(coro):
    loop = VirtualLoop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(None)


# ------------------------------------------------------------------------------------------------ fakes
class FakeTTS:
    """Audio of a known length (16 characters a second), made at `rtf` times real time, with a pause at every punctuation
    mark. `fail` is a set of texts whose synthesis raises."""

    sample_rate = RATE

    def __init__(self, rtf: float = 6.0, cps: float = 16.0) -> None:
        self.rtf = rtf
        self.cps = cps
        self.fail: set[str] = set()
        self.calls: list[str] = []

    def supported(self, lang: str) -> bool:
        return True

    def can_speak(self, lang: str) -> bool:
        return True

    def duration(self, text: str) -> float:
        return max(0.9, len(text) / self.cps)

    def stream(self, text: str, voice: str, lang: str, tone: str | None = None) -> SpeechStream:
        self.calls.append(text)
        st = SpeechStream(RATE)
        dur = self.duration(text)
        marks = [(m.start() / max(1, len(text))) * dur for m in re.finditer(r"[.,;:!?]", text) if 0 < m.start() < len(text) - 1]

        async def gen() -> None:
            n = math.ceil(dur / CHUNK_S)
            try:
                if text in self.fail:
                    await asyncio.sleep(0.05)
                    raise RuntimeError("synthesis failed (test)")
                for i in range(n):
                    if st.stop_event.is_set():
                        break
                    await asyncio.sleep(CHUNK_S / self.rtf)
                    st.samples += len(CHUNK) // 2
                    st.boundaries = [b for b in marks if b < st.samples / RATE - 0.05]
                    st.q.put_nowait(CHUNK)
            except Exception as exc:  # noqa: BLE001
                st.error = exc
            finally:
                st.done = True
                st.q.put_nowait(None)

        asyncio.get_running_loop().create_task(gen())
        return st


@dataclass
class Rec:
    events: list = field(default_factory=list)          # (t, kind, payload | (lid, nbytes))

    async def __call__(self, kind: str, payload) -> None:  # noqa: ANN001
        t = asyncio.get_running_loop().time()
        if kind == "audio":
            self.events.append((t, "audio", (struct.unpack("<I", payload[:4])[0], len(payload) - 4)))
        else:
            self.events.append((t, "json", dict(payload)))

    def json(self, type_: str):
        return [(t, p) for t, k, p in self.events if k == "json" and p.get("type") == type_]


def who(speaker: str):
    names = {"xo": "Commander Serra", "helm": "Lt. Ferri", "ops": "Lt. Tanaka", "tactical": "Lt. Cdr Voss", "sensors": "Lt. Nair",
             "engineering": "Lt. Mensah", "comms": "Ens. Martin", "flight": "Lt. Price", "chief": "Okonkwo"}
    crew = speaker in names
    return names.get(speaker, speaker), "alba", crew


# ------------------------------------------------------------------------------------------------ the trace
@dataclass
class Trace:
    begin: dict = field(default_factory=dict)
    end: dict = field(default_factory=dict)
    reason: dict = field(default_factory=dict)
    cancel_t: dict = field(default_factory=dict)
    line: dict = field(default_factory=dict)
    audio: dict = field(default_factory=dict)            # id -> [(t, seconds)]
    dropped: dict = field(default_factory=dict)          # id -> reason
    floor: list = field(default_factory=list)

    @classmethod
    def of(cls, rec: Rec) -> "Trace":
        tr = cls()
        for t, kind, p in rec.events:
            if kind == "audio":
                lid, n = p
                tr.audio.setdefault(lid, []).append((t, n / 2 / RATE))
                continue
            ty = p.get("type")
            if ty == "line":
                tr.line[p["id"]] = p
            elif ty == "audio_begin":
                tr.begin[p["line"]] = t
            elif ty == "audio_end":
                tr.end[p["line"]] = t
                tr.reason[p["line"]] = p["reason"]
            elif ty == "cancel":
                tr.cancel_t[p["line"]] = t
            elif ty == "line_dropped":
                tr.dropped[p["id"]] = p["reason"]
            elif ty == "floor":
                tr.floor.append((t, p["state"]))
        return tr

    def order(self) -> list[int]:
        return sorted(self.begin, key=lambda i: self.begin[i])

    def spoken_texts(self) -> list[str]:
        return [self.line[i]["text"] for i in self.order()]


def check(tr: Trace, enq: dict[int, float]) -> list[str]:
    """The invariants that hold in every scenario; returns the violations."""
    bad: list[str] = []
    for lid in enq:
        if lid not in tr.end and lid not in tr.dropped:
            bad.append(f"I3 line {lid} vanished (no audio_end, no line_dropped)")
    for lid, t0 in tr.begin.items():
        got = sum(s for _, s in tr.audio.get(lid, []))
        if got <= 0 and not (lid in tr.cancel_t and tr.cancel_t[lid] - t0 <= 0.3):
            bad.append(f"I1 line {lid} announced without audio")
        h, e = tr.line[lid]["hold_s"], tr.line[lid]["est_s"]
        need = min(12.0, max(e + 1.0, 1.4 + len(tr.line[lid]["text"]) / 17.0))
        if h < need - 0.02:
            bad.append(f"I6 line {lid}: hold_s {h} < {need:.2f}")
        cum = 0.0
        for t, s in tr.audio.get(lid, []):
            cum += s
            if cum > (t - t0) + LEAD_S + CHUNK_S + 0.001 + _slip(tr, lid):
                bad.append(f"I4 line {lid}: {cum:.2f} s of audio sent {t - t0:.2f} s after it began (lead {LEAD_S} s)")
                break
    order = tr.order()
    for a, b in zip(order, order[1:]):
        end_a = tr.end.get(a, tr.begin[a])
        if tr.begin[b] < end_a - 0.001:
            bad.append(f"I2 lines {a} and {b} overlap ({tr.begin[b]:.2f} < {end_a:.2f})")
        elif tr.begin[b] - end_a < 0.08 - 0.001:
            bad.append(f"I5 gap between lines {a} and {b} is {tr.begin[b] - end_a:.3f} s")
    # I7: while the floor is the Captain's only answers begin
    held_from = None
    for t, state in tr.floor:
        if state == "captain":
            held_from = t if held_from is None else held_from
        elif held_from is not None:
            for lid, tb in tr.begin.items():
                if held_from < tb < t - 0.001 and tr.line[lid]["priority"] != "answer":
                    bad.append(f"I7 line {lid} ({tr.line[lid]['priority']}) began at {tb:.2f} while the Captain held the floor ({held_from:.2f}..{t:.2f})")
            held_from = None
    # I9: an answer starts at once when nobody else is answering
    for lid, tb in tr.begin.items():
        if tr.line[lid]["priority"] == "answer" and lid in enq:
            busy = any(tr.line[o]["priority"] == "answer" and tr.begin[o] < enq[lid] < tr.end.get(o, 1e9) for o in tr.begin if o != lid)
            if not busy and tb - enq[lid] > 0.35:
                bad.append(f"I9 the answer (line {lid}) waited {tb - enq[lid]:.2f} s to start")
    return bad


def _slip(tr: Trace, lid: int) -> float:
    """Audio that ran dry (slow synthesis) shifts the listener's clock: allow what the line was late by."""
    ts = tr.audio.get(lid, [])
    if len(ts) < 2:
        return 0.0
    late = 0.0
    played = 0.0
    for (t0, s0), (t1, _) in zip(ts, ts[1:]):
        played += s0
        late = max(late, (t1 - ts[0][0]) - played)
    return max(0.0, late)


# ------------------------------------------------------------------------------------------------ the harness
LAST: list = []                       # the bridge of the scenario that ran last (for -v)


def timeline(rec: Rec) -> list[str]:
    """The game's view of a scenario, one line per message (audio chunks are summed up)."""
    out: list[str] = []
    run_id, run_bytes, run_t0, run_t1 = None, 0, 0.0, 0.0

    def flush() -> None:
        nonlocal run_id, run_bytes
        if run_id is not None:
            out.append(f"{run_t0:8.2f}  ~ audio line {run_id}: {run_bytes / 2 / RATE:.2f} s sent until {run_t1:.2f}")
        run_id, run_bytes = None, 0

    for t, kind, p in rec.events:
        if kind == "audio":
            lid, n = p
            if lid != run_id:
                flush()
                run_id, run_t0 = lid, t
            run_bytes += n
            run_t1 = t
            continue
        flush()
        ty = p.get("type")
        if ty == "line":
            out.append(f"{t:8.2f}  line {p['id']} [{p['speaker']}/{p['priority']}] est {p['est_s']} s hold {p['hold_s']} s: {p['text'][:56]}")
        elif ty in ("audio_begin",):
            continue
        else:
            out.append(f"{t:8.2f}  {ty} " + " ".join(f"{k}={v}" for k, v in p.items() if k != "type" and k != "text"))
    flush()
    return out


class Bridge:
    def __init__(self, rtf: float = 6.0) -> None:
        self.tts = FakeTTS(rtf=rtf)
        self.rec = Rec()
        self.voice = Voice(self.tts, self.rec, who)
        self.enq: dict[int, float] = {}
        self.ids: dict[str, int] = {}
        self.task: asyncio.Task | None = None

    async def __aenter__(self) -> "Bridge":
        self.task = asyncio.create_task(self.voice.run())
        return self

    async def __aexit__(self, *exc) -> None:  # noqa: ANN002
        assert self.task is not None
        LAST.clear()
        LAST.append(self)
        self.task.cancel()
        try:
            await self.task
        except asyncio.CancelledError:
            pass

    async def say(self, key: str, speaker: str, text: str, **kw) -> int:  # noqa: ANN003
        lid = await self.voice.say(speaker, text, kw.pop("lang", "en"), kw.pop("tone", "calm"), **kw)
        self.ids[key] = lid
        self.enq[lid] = asyncio.get_running_loop().time()
        return lid

    async def settle(self, extra: float = 1.0) -> None:
        await self.voice.q.join()
        await asyncio.sleep(extra)

    def trace(self) -> Trace:
        return Trace.of(self.rec)

    def t(self) -> float:
        return asyncio.get_running_loop().time()


SENT = "Captain, the contact bearing zero four five is closing fast, range fifty kilometres. We recommend going to red alert."
LONG = "Captain, all decks report ready. Engineering confirms the reactor is holding at ninety percent, tactical has the railguns loaded, and flight control has Alpha squadron on the deck."


# ------------------------------------------------------------------------------------------------ scenarios
async def s01_turns() -> list[str]:
    """Three officers queue at once: they speak one after the other, in order, with a breath between."""
    async with Bridge() as b:
        await b.say("a", "sensors", "Sensors here. New contact at two seven zero, range forty.")
        await b.say("b", "tactical", "Tactical. Shields are at full, weapons ready.")
        await b.say("c", "engineering", "Engineering. Reactor steady at seventy percent.")
        await b.settle()
        tr = b.trace()
        bad = check(tr, b.enq)
        if tr.order() != [b.ids["a"], b.ids["b"], b.ids["c"]]:
            bad.append(f"order {tr.order()}")
        return bad


async def s02_barge_in() -> list[str]:
    """The Captain speaks while an officer is in the middle of a long line: the officer stops within half a second, the
    chatter is dropped, the answer comes first, and the interrupted report is said again afterwards."""
    async with Bridge() as b:
        await b.say("long", "xo", LONG)
        await b.say("chat", "helm", "Nice quiet watch, isn't it? Reminds me of home.", priority="low")
        await b.say("rep", "sensors", "Sensors. Two new contacts, bearing zero nine zero.")
        await asyncio.sleep(3.0)
        t_down = b.t()
        b.voice.captain_begin()
        await asyncio.sleep(1.2)                                          # he talks
        b.voice.captain_end(None)
        await asyncio.sleep(0.5)                                          # speech recognition and the model
        b.voice.captain_turn_begin()
        await b.say("ans", "helm", "Helm, aye, coming to two one seven.", answer=True)
        b.voice.captain_turn_end()
        await b.settle(2.0)
        tr = b.trace()
        bad = check(tr, b.enq)
        long_id, chat_id, rep_id, ans_id = (b.ids[k] for k in ("long", "chat", "rep", "ans"))
        if tr.reason.get(long_id) != "cut":
            bad.append(f"I7 the long line was not cut ({tr.reason.get(long_id)})")
        elif tr.cancel_t[long_id] - t_down > 0.6:
            bad.append(f"I7 the long line stopped {tr.cancel_t[long_id] - t_down:.2f} s after the Captain began")
        if tr.dropped.get(chat_id) != "captain_spoke":
            bad.append(f"the chatter was not dropped as captain_spoke ({tr.dropped.get(chat_id)})")
        firsts = [i for i in tr.order() if tr.begin[i] > t_down]
        if not firsts or firsts[0] != ans_id:
            bad.append(f"I7 the answer did not come first: {[tr.line[i]['speaker'] for i in firsts]}")
        later = [tr.line[i]["text"] for i in firsts[1:]]
        if not any("Two new contacts" in t for t in later):
            bad.append("the waiting report was never said")
        if not any(t.startswith("Captain, all decks") for t in later):
            bad.append("the interrupted report was not said again")
        return bad


async def s03_typed_order() -> list[str]:
    """A typed order arrives: whoever talks is stopped, the queued report waits for the answer."""
    async with Bridge() as b:
        await b.say("r1", "sensors", "Sensors. Contact T-21 is changing course, now bearing three one zero, range twenty kilometres.")
        await b.say("r2", "tactical", "Tactical. Missiles are ready in the tubes, awaiting your word.")
        await asyncio.sleep(1.5)
        t0 = b.t()
        b.voice.captain_input()
        await asyncio.sleep(0.9)
        b.voice.captain_turn_begin()
        await b.say("ans", "xo", "Aye, Captain. Standing by.", answer=True)
        b.voice.captain_turn_end()
        await b.settle(2.0)
        tr = b.trace()
        bad = check(tr, b.enq)
        after = [i for i in tr.order() if tr.begin[i] > t0]
        if not after or after[0] != b.ids["ans"]:
            bad.append("I7 the answer to the typed order did not come first")
        if b.ids["r2"] not in tr.begin:
            bad.append("the waiting report was never said")
        return bad


async def s04_no_speech() -> list[str]:
    """The key is pressed and released without a word: the held reports go on at once."""
    async with Bridge() as b:
        await b.say("r1", "sensors", "Sensors. Nothing new on the plot, all quiet.")
        await asyncio.sleep(0.1)
        b.voice.captain_begin()
        await b.say("r2", "tactical", "Tactical. Weapons are cold and shields are up.")
        await asyncio.sleep(0.6)
        t_up = b.t()
        b.voice.captain_end(False)                                        # speech recognition heard nothing
        await b.settle(1.0)
        tr = b.trace()
        bad = check(tr, b.enq)
        if b.ids["r2"] not in tr.begin:
            bad.append("the held report was never said")
        elif tr.begin[b.ids["r2"]] - t_up > 0.7:
            bad.append(f"the held report waited {tr.begin[b.ids['r2']] - t_up:.2f} s after a key press with no speech")
        return bad


async def s05_floor_timeout() -> list[str]:
    """No answer comes within the timeout: the others go on, and a late answer still goes first."""
    async with Bridge() as b:
        await b.say("r1", "sensors", "Sensors. Contact lost on the long range plot, recommend an active sweep.")
        await asyncio.sleep(0.1)                                          # (the report has just begun: the key cuts it, it is said again)
        b.voice.captain_begin()
        await asyncio.sleep(0.5)
        b.voice.captain_end(None)
        t_up = b.t()
        await asyncio.sleep(speech.TURN_TIMEOUT_S + 1.0)
        tr = b.trace()
        bad = []
        again = [i for i in tr.order() if tr.begin[i] > t_up and tr.line[i]["text"].startswith("Sensors. Contact lost")]
        if not again:
            bad.append("the report stayed held past the timeout")
        elif not (speech.TURN_TIMEOUT_S - 0.5 <= tr.begin[again[0]] - t_up <= speech.TURN_TIMEOUT_S + 1.0):
            bad.append(f"the report started {tr.begin[again[0]] - t_up:.1f} s after the key was released")
        await b.say("r2", "tactical", LONG)
        await asyncio.sleep(1.0)
        t_late = b.t()
        b.voice.captain_turn_begin()
        await b.say("ans", "helm", "Aye, Captain, full ahead.", answer=True)
        b.voice.captain_turn_end()
        await b.settle(2.0)
        tr = b.trace()
        bad += check(tr, b.enq)
        after = [i for i in tr.order() if tr.begin[i] > t_late]
        if not after or after[0] != b.ids["ans"]:
            bad.append("I7 the late answer did not go first")
        return bad


async def s06_topic() -> list[str]:
    """A newer line on the same topic replaces an older one that has not been said."""
    async with Bridge() as b:
        await b.say("busy", "xo", LONG)
        await b.say("h1", "engineering", "Heat is at sixty percent and rising slowly.", topic="heat")
        await b.say("h2", "engineering", "Heat is now at seventy-five percent, radiators recommended.", topic="heat")
        await b.settle()
        tr = b.trace()
        bad = check(tr, b.enq)
        if tr.dropped.get(b.ids["h1"]) != "superseded":
            bad.append(f"the old heat report was not superseded ({tr.dropped.get(b.ids['h1'])})")
        if b.ids["h2"] not in tr.begin:
            bad.append("the new heat report was not said")
        return bad


async def s07_expiry() -> list[str]:
    """A report that waits too long is dropped, and says so."""
    async with Bridge() as b:
        await b.say("busy", "xo", LONG + " " + LONG)
        await b.say("old", "sensors", "Sensors. A brief flicker at zero four zero, gone now.", expires_s=2.0)
        await b.say("ok", "tactical", "Tactical. Shields nominal.")
        await b.settle()
        tr = b.trace()
        bad = check(tr, b.enq)
        if tr.dropped.get(b.ids["old"]) != "expired":
            bad.append(f"the stale report was not dropped as expired ({tr.dropped.get(b.ids['old'])})")
        if b.ids["ok"] not in tr.begin:
            bad.append("the fresh report was not said")
        return bad


async def s08_overflow() -> list[str]:
    """A flood of chatter: the queue is capped, the least important go, nothing vanishes without a word."""
    async with Bridge() as b:
        await b.say("busy", "xo", LONG)
        crew = ["helm", "ops", "comms", "sensors", "engineering", "flight"]
        for i in range(14):
            await b.say(f"c{i}", crew[i % len(crew)], f"Chatter number {i}, nothing of importance really, just talking.", priority="low")
        await b.say("real", "tactical", "Tactical. Enemy ship changing course towards us.")
        await b.settle(1.0)
        tr = b.trace()
        bad = check(tr, b.enq)
        if b.ids["real"] not in tr.begin:
            bad.append("the real report was lost in the flood")
        n_drop = sum(1 for r in tr.dropped.values() if r == "overflow")
        if n_drop < 3:
            bad.append(f"expected the flood to overflow the queue, only {n_drop} dropped")
        return bad


async def s09_merge() -> list[str]:
    """Two lines from the same officer waiting behind another speaker become one."""
    async with Bridge() as b:
        await b.say("busy", "xo", LONG)
        await b.say("m1", "sensors", "Sensors. Two contacts, bearing zero nine zero.")
        await b.say("m2", "sensors", "Both are transponding as merchants.")
        await b.settle()
        tr = b.trace()
        bad = check(tr, b.enq)
        joined = [t for t in tr.spoken_texts() if "Two contacts" in t]
        if not joined or "merchants" not in joined[0]:
            bad.append(f"the two sentences were not merged: {tr.spoken_texts()}")
        if not str(tr.dropped.get(b.ids["m2"], "")).startswith("merged_into"):
            bad.append("the merged line was not reported")
        return bad


async def s10_shorten() -> list[str]:
    """With a long backlog a long report is cut to its first sentence."""
    async with Bridge() as b:
        await b.say("busy", "xo", LONG + " " + LONG)
        for i in range(3):
            await b.say(f"f{i}", "ops", f"Operations, report {i}. All damage control teams are on station and ready to respond as needed.")
        await b.say("long", "sensors", "Sensors. " + "The plot shows several contacts moving in formation across the sector, all of them consistent with a patrol. " * 3)
        await b.settle()
        tr = b.trace()
        bad = check(tr, b.enq)
        if not any(len(t) < 200 and t.startswith("Sensors. The plot") for t in tr.spoken_texts()):
            bad.append("the long report was not shortened")
        return bad


async def s11_urgent() -> list[str]:
    """A warning of danger does not wait for a chat that has a long way to go."""
    async with Bridge() as b:
        await b.say("chat", "helm", "I was thinking about the old days on the Tenacity, when the coffee machine worked and nobody worried. " * 2, priority="low")
        await b.say("rep", "sensors", "Sensors. Routine drift report, nothing to worry about, all systems look normal from here at the moment.")
        await asyncio.sleep(1.0)
        t0 = b.t()
        await b.say("alarm", "tactical", "Missiles inbound, bearing two seven zero!", priority=Prio.URGENT)
        await b.settle()
        tr = b.trace()
        bad = check(tr, b.enq)
        if tr.begin[b.ids["alarm"]] - t0 > 1.4:
            bad.append(f"the warning waited {tr.begin[b.ids['alarm']] - t0:.2f} s")
        return bad


async def s12_synth_failure() -> list[str]:
    """A line that cannot be made is reported dropped: no subtitle, no stall, the next line is said."""
    async with Bridge() as b:
        b.tts.fail.add("Tactical. This one will fail to synthesise.")
        await b.say("a", "sensors", "Sensors. First line, all is well.")
        await b.say("bad", "tactical", "Tactical. This one will fail to synthesise.")
        await b.say("c", "engineering", "Engineering. Third line, still here.")
        await b.settle()
        tr = b.trace()
        bad = check(tr, b.enq)
        if tr.dropped.get(b.ids["bad"]) != "synth_failed":
            bad.append(f"the failed line was not reported ({tr.dropped.get(b.ids['bad'])})")
        if b.ids["bad"] in tr.line:
            bad.append("I1 a subtitle was announced for the line that failed")
        if b.ids["c"] not in tr.begin:
            bad.append("the line after the failure was not said")
        return bad


async def s13_slow_synthesis() -> list[str]:
    """The machine is busy and the voice makes speech slower than it plays: the stream keeps its pace and finishes."""
    async with Bridge(rtf=0.8) as b:
        await b.say("a", "sensors", SENT)
        await b.say("b", "tactical", "Tactical. Shields at full.")
        await b.settle(1.0)
        tr = b.trace()
        bad = check(tr, b.enq)
        for k in ("a", "b"):
            if tr.reason.get(b.ids[k]) != "done":
                bad.append(f"line {k} ended {tr.reason.get(b.ids[k])}")
        return bad


async def s14_burst() -> list[str]:
    """Ten officers have something to say at the same moment: all of them get their turn, in order."""
    async with Bridge() as b:
        for i, spk in enumerate(["xo", "helm", "ops", "tactical", "comms", "sensors", "engineering", "flight", "chief", "xo"]):
            await b.say(f"l{i}", spk, f"Report number {i} from {spk}: everything on my board is in order, Captain.")
        await b.settle()
        tr = b.trace()
        bad = check(tr, b.enq)
        if tr.order() != [b.ids[f"l{i}"] for i in range(10)]:
            bad.append(f"order {tr.order()}")
        total = tr.end[b.ids["l9"]] - tr.begin[b.ids["l0"]]
        talk = sum(tr.end[i] - tr.begin[i] for i in tr.order())
        if total > talk + 10 * 0.6:
            bad.append(f"the gaps add up to {total - talk:.1f} s for ten lines")
        return bad


async def s15_double_press() -> list[str]:
    """The Captain presses the key twice in a row: still one floor, one answer."""
    async with Bridge() as b:
        await b.say("r", "sensors", LONG)
        await asyncio.sleep(2.0)
        b.voice.captain_begin()
        await asyncio.sleep(0.4)
        b.voice.captain_end(None)
        await asyncio.sleep(0.2)
        b.voice.captain_begin()
        await asyncio.sleep(0.8)
        b.voice.captain_end(None)
        await asyncio.sleep(0.4)
        b.voice.captain_turn_begin()
        await b.say("ans", "helm", "Aye, Captain.", answer=True)
        b.voice.captain_turn_end()
        await b.settle(2.0)
        tr = b.trace()
        bad = check(tr, b.enq)
        if b.ids["ans"] not in tr.begin:
            bad.append("the answer was never said")
        return bad


async def s16_answer_interrupted() -> list[str]:
    """The Captain talks over the answer to his own previous order: the answer stops and is not repeated."""
    async with Bridge() as b:
        b.voice.captain_input()
        b.voice.captain_turn_begin()
        await b.say("ans", "helm", "Aye, Captain. Coming to heading two one seven and bringing the throttle up to half ahead, standing by for further orders.", answer=True)
        b.voice.captain_turn_end()
        await asyncio.sleep(2.0)
        t0 = b.t()
        b.voice.captain_begin()
        await asyncio.sleep(0.8)
        b.voice.captain_end(None)
        await asyncio.sleep(0.5)
        b.voice.captain_turn_begin()
        await b.say("ans2", "helm", "Aye, cancelling.", answer=True)
        b.voice.captain_turn_end()
        await b.settle(2.0)
        tr = b.trace()
        bad = check(tr, b.enq)
        if tr.reason.get(b.ids["ans"]) != "cut":
            bad.append("the first answer was not cut")
        if sum(1 for t in tr.spoken_texts() if t.startswith("Aye, Captain. Coming")) != 1:
            bad.append("the interrupted answer was repeated")
        return bad


async def s17_flags() -> list[str]:
    """The producer's flags: a task inside a Captain's turn speaks answers, chatter is low, the first version's flag is a report."""
    async with Bridge() as b:
        seen: dict[str, Prio] = {}

        async def task(key: str, setup) -> None:  # noqa: ANN001
            setup()
            lid = await b.say(key, "helm", f"Line for {key}, some words to say here.")
            seen[key] = next(l.prio for l in b.voice._queue + ([b.voice._cur] if b.voice._cur else []) if l.id == lid)

        await b.say("busy", "xo", LONG)
        await asyncio.create_task(task("answer", b.voice.captain_turn_begin))
        await asyncio.create_task(task("low_flag", lambda: setattr(b.voice, "low_priority", True)))
        await asyncio.create_task(task("chat", lambda: setattr(b.voice, "chatter", True)))
        await asyncio.create_task(task("plain", lambda: None))
        await b.say("mess", "mess3", "Pass the salt, would you.")
        seen["mess"] = next(l.prio for l in b.voice._queue if l.id == b.ids["mess"])
        b.voice.captain_turn_end()
        await b.settle(1.0)
        bad = []
        expect = {"answer": Prio.ANSWER, "low_flag": Prio.NORMAL, "chat": Prio.LOW, "plain": Prio.NORMAL, "mess": Prio.LOW}
        for k, v in expect.items():
            if seen.get(k) != v:
                bad.append(f"flag {k}: {seen.get(k)} instead of {v}")
        if b.voice.answering:
            bad.append("the answering flag leaked out of its task")
        return bad


async def s18_compat() -> list[str]:
    """What the first version exposed keeps working: busy_s, busy_until, q.join, first_audio/enqueued, drop_low_priority."""
    async with Bridge() as b:
        bad = []
        if b.voice.busy_s() != 0.0 or b.voice.busy_until != 0.0:
            bad.append("an idle voice reports busy")
        await b.say("a", "sensors", SENT)
        await b.say("c", "helm", "Chatter that will be dropped when the Captain speaks, honestly.", priority="low")
        if b.voice.busy_s() < 3.0:
            bad.append(f"busy_s {b.voice.busy_s():.1f} too small for a line and a chat waiting")
        await asyncio.sleep(1.0)
        if not b.voice.busy_until > b.t():
            bad.append("busy_until is not in the future while a line is being said")
        n = b.voice.drop_low_priority()
        if n != 1:
            bad.append(f"drop_low_priority returned {n}")
        await b.voice.q.join()
        if b.ids["a"] not in b.voice.first_audio or b.ids["a"] not in b.voice.enqueued:
            bad.append("first_audio/enqueued lost")
        if b.voice.first_audio[b.ids["a"]] - b.voice.enqueued[b.ids["a"]] > 0.5:
            bad.append("the first audio took over half a second on an idle floor")
        return bad


SCENARIOS = [s01_turns, s02_barge_in, s03_typed_order, s04_no_speech, s05_floor_timeout, s06_topic, s07_expiry, s08_overflow, s09_merge,
             s10_shorten, s11_urgent, s12_synth_failure, s13_slow_synthesis, s14_burst, s15_double_press, s16_answer_interrupted,
             s17_flags, s18_compat]


def main() -> int:
    verbose = "-v" in sys.argv
    failed = 0
    for sc in SCENARIOS:
        try:
            bad = run(sc())
        except Exception:  # noqa: BLE001
            bad = ["crashed:\n" + traceback.format_exc()]
        status = "ok  " if not bad else "FAIL"
        print(f"{status} {sc.__name__:22s} {(sc.__doc__ or '').strip().splitlines()[0][:100]}")
        for m in bad:
            print("       -", m)
        if verbose and LAST:
            for row in timeline(LAST[0].rec):
                print("     |", row)
        failed += bool(bad)
    print(f"\n{len(SCENARIOS) - failed}/{len(SCENARIOS)} scenarios pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
