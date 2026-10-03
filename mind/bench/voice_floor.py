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
from astra_mind.speech import KEY_STUCK_S, LEAD_S, Prio, Voice
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

    def __init__(self, rtf: float = 6.0, cps: float = 16.0, first_delay: float = 0.0) -> None:
        self.rtf = rtf
        self.cps = cps
        self.first_delay = first_delay                    # the model's start-up before its first audio
        self.fail: set[str] = set()
        self.silent: set[str] = set()                    # texts it makes no sound for
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
            n = 0 if text in self.silent else math.ceil(dur / CHUNK_S)
            try:
                if self.first_delay:
                    await asyncio.sleep(self.first_delay)
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


def check(tr: Trace, enq: dict[int, float], down: list[tuple[float, float]] | None = None) -> list[str]:
    """The invariants that hold in every scenario; returns the violations. `down`: the intervals in which the Captain's key was down
    (an answer queued meanwhile is not due until he lets go)."""
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
            due = enq[lid]
            for a, z in down or []:
                if a <= due < z:
                    due = z
            if not busy and tb - due > 0.35:
                bad.append(f"I9 the answer (line {lid}) waited {tb - due:.2f} s to start")
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
    def __init__(self, rtf: float = 6.0, first_delay: float = 0.0) -> None:
        self.tts = FakeTTS(rtf=rtf, first_delay=first_delay)
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

    async def settle(self, extra: float = 1.0, limit: float = 240.0) -> None:
        """Wait (in virtual time) until everything queued has been said or dropped; a floor that never gets there fails the
        scenario's own checks instead of hanging the run."""
        t0 = self.t()
        while (self.voice._queue or self.voice._cur is not None) and self.t() - t0 < limit:
            await asyncio.sleep(0.02)
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
        if not any(t.startswith("Engineering confirms") for t in later):
            bad.append("the rest of the interrupted report (from the sentence that was cut) was not said again")
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
        after = sorted(t for t in tr.begin.values() if t >= t_up)
        if not after or after[0] - t_up > 0.7:
            bad.append(f"nobody went on within 0.7 s of a key press with no speech ({after[0] - t_up:.2f} s)" if after else "nobody went on")
        texts = [tr.line[i]["text"] for i in tr.order() if tr.begin[i] >= t_up]
        if not any("Weapons are cold" in t for t in texts):
            bad.append("the held report was never said")
        if not any("Nothing new" in t for t in texts):
            bad.append("the report the key had cut off was not said again (it had hardly begun)")
        return bad


async def s05_floor_timeout() -> list[str]:
    """No answer comes within the timeout: the others go on, and a late answer still goes first."""
    async with Bridge() as b:
        await b.say("r1", "sensors", "Sensors. Contact lost on the long range plot, recommend an active sweep.")
        await asyncio.sleep(0.1)                                          # (the report has just begun: the key cuts it, the rest of it is said again)
        b.voice.captain_begin()
        await asyncio.sleep(0.5)
        b.voice.captain_end(None)
        t_up = b.t()
        await asyncio.sleep(speech.TURN_TIMEOUT_S + 1.0)
        tr = b.trace()
        bad = []
        again = [i for i in tr.order() if tr.begin[i] > t_up and "Contact lost on the long range plot" in tr.line[i]["text"]]
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


async def s10_rethink() -> list[str]:
    """A report that waited behind a long backlog is not shortened by the floor: whoever was going to say it thinks again (the rethink
    hook, called with how long it waited) and says it as it stands now, or lets it go; a line without a hook is said in full."""
    async with Bridge() as b:
        asked: list[tuple[str, float, str]] = []

        def hook(new: str | None):
            async def rethink(text: str, waited: float, cut_after: str) -> str | None:
                asked.append((text, waited, cut_after))
                await asyncio.sleep(0.4)                                # (a small model call)
                return new
            return rethink

        await b.say("busy", "xo", LONG + " " + LONG)
        long_sensors = "Sensors. " + "The plot shows several contacts moving in formation across the sector, all of them consistent with a patrol. " * 3
        await b.say("long", "sensors", long_sensors)                                        # no hook: said in full
        await b.say("upd", "ops", "Operations: damage control is on the fire in section D.", rethink=hook("Operations: the fire in D is out."))
        await b.say("gone", "helm", "Helm: we are holding the bearing.", rethink=hook(None))
        await b.settle()
        tr = b.trace()
        bad = check(tr, b.enq)
        spoken = tr.spoken_texts()
        if long_sensors.strip() not in [t.strip() for t in spoken]:
            bad.append("a line without a hook was changed by the floor")
        if len(asked) != 2 or any(w < speech.RETHINK_AFTER_S for _, w, _ in asked):
            bad.append(f"the two waiting lines were not thought again after waiting: {asked}")
        if "Operations: the fire in D is out." not in spoken:
            bad.append("the re-thought line was not said as it stands now")
        if any("holding the bearing" in t for t in spoken) or tr.dropped.get(b.ids["gone"]) != "rethought":
            bad.append(f"the line its speaker let go was said or not declared ({tr.dropped.get(b.ids['gone'])!r})")
        # what the room heard is what was said: the re-thought words, not the first ones, and nothing of the line let go
        heard = [w for _, _, w, _ in b.voice.heard_since(3600.0)]
        if "Operations: the fire in D is out." not in heard or any("section D" in w or "holding the bearing" in w for w in heard):
            bad.append(f"the record of what was heard is not what was said: {heard}")
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


async def s19_stuck_key() -> list[str]:
    """The game's 'key up' never arrives: the crew is not silenced for good (a key down for KEY_STUCK_S is taken as released)."""
    async with Bridge() as b:
        b.voice.captain_begin()
        await b.say("r", "sensors", SENT)
        await asyncio.sleep(KEY_STUCK_S - 5.0)
        bad = []
        if b.ids["r"] in b.trace().begin:
            bad.append("a report was said while the key was (as far as the mind knew) still down")
        await asyncio.sleep(10.0)
        await b.settle(1.0)
        tr = b.trace()
        bad += check(tr, b.enq)
        if b.ids["r"] not in tr.begin:
            bad.append("the crew stayed silent after the key had been down for too long")
        if tr.floor and tr.floor[-1][1] != "idle":
            bad.append(f"the floor ended as {tr.floor[-1][1]}")
        return bad


async def s20_new_session() -> list[str]:
    """The game goes away with the key down and comes back: the new session starts with a free floor and nothing left over."""
    async with Bridge() as b:
        await b.say("old", "xo", LONG)
        await asyncio.sleep(1.5)
        b.voice.captain_begin()
        await asyncio.sleep(0.5)
        b.voice.muted = True
        await b.voice.clear("no_listener")                        # the connection closed, the key still 'down'
        await asyncio.sleep(0.5)
        b.voice.muted = False                                      # a new connection
        await b.voice.clear("new_session")
        t0 = b.t()
        await b.say("new", "sensors", "Sensors. Contact bearing two seven zero, range forty.")
        await b.settle(1.0)
        tr = b.trace()
        bad = check(tr, b.enq)
        if b.ids["new"] not in tr.begin:
            bad.append("the first line of the new session was never said")
        elif tr.begin[b.ids["new"]] - t0 > 0.8:
            bad.append(f"the first line of the new session waited {tr.begin[b.ids['new']] - t0:.2f} s")
        if b.voice.held:
            bad.append("the floor is still held")
        return bad


async def s21_late_answer() -> list[str]:
    """The Captain speaks again while the answer to his previous order is still being written: the late answer waits until he lets go of the key, then follows."""
    async with Bridge() as b:
        b.voice.captain_input()                                    # order 1, typed
        await asyncio.sleep(1.0)
        t_down = b.t()
        b.voice.captain_begin()                                    # order 2, spoken: the key goes down
        await asyncio.sleep(0.5)
        b.voice.captain_turn_begin()
        await b.say("late", "helm", "Aye, Captain, coming to two one seven.", answer=True)   # ... and the answer to order 1 arrives
        b.voice.captain_turn_end()
        await asyncio.sleep(1.0)                                   # still talking
        t_up = b.t()
        started_while_down = b.ids["late"] in b.trace().begin
        b.voice.captain_end(None)
        await b.settle(2.0)
        tr = b.trace()
        bad = check(tr, b.enq, down=[(t_down, t_up)])
        if started_while_down:
            bad.append("the late answer began while the Captain still held the key")
        if b.ids["late"] not in tr.begin:
            bad.append("the late answer was never said")
        elif tr.begin[b.ids["late"]] - t_up > 0.6:
            bad.append(f"the late answer waited {tr.begin[b.ids['late']] - t_up:.2f} s after the key went up")
        return bad


async def s22_turn_with_two_answers() -> list[str]:
    """The crew's model streams two officers' answers two seconds apart while a report waits: the report does not start in the gap between them."""
    async with Bridge() as b:
        await b.say("busy", "xo", LONG)                                # something is being said when the Captain speaks
        await asyncio.sleep(0.5)
        b.voice.captain_begin()
        await asyncio.sleep(0.6)
        b.voice.captain_end(None)
        await b.say("report", "sensors", "Sensors. New contact bearing two seven zero, range forty kilometres, closing.")
        await asyncio.sleep(0.3)
        b.voice.captain_turn_begin()
        await b.say("a", "helm", "Aye, Captain, coming to two one seven.", answer=True)
        await asyncio.sleep(4.0)                                       # the model is still writing the second officer's line
        await b.say("b", "tactical", "Tactical, weapons ready.", answer=True)
        b.voice.captain_turn_end()
        await b.settle(2.0)
        tr = b.trace()
        bad = check(tr, b.enq)
        order = tr.order()
        if b.ids["a"] not in tr.begin or b.ids["b"] not in tr.begin:
            return bad + [f"an answer was never said: order {order}"]
        between = [i for i in order if tr.begin[b.ids["a"]] < tr.begin[i] < tr.begin[b.ids["b"]]]
        if between:
            bad.append(f"lines {between} began between the two answers")
        cut = [i for i in order if tr.reason.get(i) == "cut" and i != b.ids["busy"]]
        if cut:
            bad.append(f"lines {cut} were cut (a line that started in the gap between the answers is cut by the second)")
        if b.ids["report"] not in tr.begin or tr.begin[b.ids["report"]] < tr.begin[b.ids["b"]]:
            bad.append("the report was not said after the answers")
        return bad


async def s23_no_audio() -> list[str]:
    """A line the voice makes no sound for (only punctuation) is dropped and declared: no subtitle without a voice, and the next line is said."""
    async with Bridge() as b:
        b.tts.silent = {"..."}
        await b.say("empty", "sensors", "...")
        await b.say("next", "helm", "Helm here, all steady.")
        await b.settle(1.0)
        tr = b.trace()
        bad = check(tr, b.enq)
        if b.ids["empty"] in tr.begin:
            bad.append("a line with no sound was announced")
        if tr.dropped.get(b.ids["empty"]) != "no_audio":
            bad.append(f"the empty line was dropped as {tr.dropped.get(b.ids['empty'])!r}")
        if b.ids["next"] not in tr.begin:
            bad.append("the line after it was never said")
        return bad


async def s24_startup_delay() -> list[str]:
    """The model takes 0.4 s to start and then makes speech twice as fast as it plays: the line starts with its first audio, not after a
    buffer sized as if the voice were slow (its start-up delay is not its speed)."""
    async with Bridge(rtf=2.0, first_delay=0.4) as b:
        # one line to let the floor learn how fast this voice goes, then the one that counts
        await b.say("warm", "sensors", "Sensors here, nothing new to report on any bearing at all.")
        await b.settle(1.0)
        await b.say("l", "helm", "Helm here: coming to two one seven, half ahead, all steady and nothing to report.")
        await b.settle(1.0)
        tr = b.trace()
        bad = check(tr, b.enq)
        wait = tr.begin[b.ids["l"]] - b.enq[b.ids["l"]]
        if wait > 0.4 + 0.4:
            bad.append(f"the line began {wait:.2f} s after it was queued: more than the model's 0.4 s start-up and a breath")
        return bad


async def s25_hook() -> list[str]:
    """The server's `captain_speaks()` hook, alone or twice or next to the key: the line in flight is cut, the chatter is dropped, nothing starts until the answer."""
    async with Bridge() as b:
        await b.say("long", "xo", LONG)
        await b.say("chat", "helm", "Nice quiet watch, isn't it? Reminds me of home.", priority="low")
        await b.say("rep", "sensors", "Sensors. Two new contacts, bearing zero nine zero.")
        await asyncio.sleep(2.0)
        t0 = b.t()
        b.voice.captain_speaks()                                       # no key down: it takes the floor like a typed order
        b.voice.captain_speaks()                                       # (twice: the same)
        await asyncio.sleep(1.2)
        began = [i for i, t in b.trace().begin.items() if t > t0]
        b.voice.captain_turn_begin()
        await b.say("ans", "helm", "Aye, Captain.", answer=True)
        b.voice.captain_turn_end()
        await b.settle(2.0)
        tr = b.trace()
        bad = check(tr, b.enq)
        if began:
            bad.append(f"lines {began} began while the Captain held the floor")
        if tr.reason.get(b.ids["long"]) != "cut" or tr.cancel_t.get(b.ids["long"], 1e9) - t0 > 0.6:
            bad.append("the line in flight was not cut within 0.6 s")
        if tr.dropped.get(b.ids["chat"]) != "captain_spoke":
            bad.append(f"the chatter was {tr.dropped.get(b.ids['chat'])!r}, not dropped as captain_spoke")
        order = tr.order()
        if b.ids["ans"] not in order or (b.ids["rep"] in order and order.index(b.ids["rep"]) < order.index(b.ids["ans"])):
            bad.append(f"the answer did not come first: {order}")
        # next to the key: with it down the hook only cuts and drops
        b.voice.captain_begin()
        b.voice.captain_speaks()
        await asyncio.sleep(0.3)
        held = b.voice.held
        b.voice.captain_end(False)
        if not held:
            bad.append("the floor was not held with the key down")
        return bad


class LegacyTTS:
    """A voice engine of the first version: `stream` is an async generator of PCM chunks (no tone, no stop, no `can_speak`); what a scripted
    engine in another module's tests looks like."""

    sample_rate = RATE

    def supported(self, lang: str) -> bool:
        return True

    async def stream(self, text: str, voice: str, lang: str):  # noqa: ANN201
        for _ in range(math.ceil(max(0.9, len(text) / 16.0) / CHUNK_S)):
            await asyncio.sleep(CHUNK_S / 6.0)
            yield CHUNK


async def s26_first_version_engine() -> list[str]:
    """A voice engine with the first version's interface still works, and a line of it can be cut like any other."""
    async with Bridge() as b:
        b.voice.tts = LegacyTTS()
        await b.say("a", "sensors", SENT)
        await b.say("b", "helm", "Helm here, all steady.")
        await asyncio.sleep(1.0)
        b.voice.captain_begin()
        await asyncio.sleep(0.4)
        b.voice.captain_end(None)
        await asyncio.sleep(0.3)
        b.voice.captain_turn_begin()
        await b.say("ans", "helm", "Aye, Captain.", answer=True)
        b.voice.captain_turn_end()
        await b.settle(2.0)
        tr = b.trace()
        bad = check(tr, b.enq)
        if b.ids["ans"] not in tr.begin:
            bad.append("the answer was never said")
        if tr.reason.get(b.ids["a"]) != "cut":
            bad.append("the line in flight was not cut")
        return bad


ARCHON = ("Aquila, this is Archon Varek Solm of the Kharon Mandate. You have entered space that belongs to the Outer Worlds. "
          "Your presence here is an insult to every ship that fell at the gates. I give you one chance to withdraw before my fleet opens fire. "
          "Stand down your weapons and surrender your vessel within two minutes.")


async def s27_live_replay() -> list[str]:
    """The live test's sequence (game clock): reports queued, an enemy message in flight, and three typed orders answered about a second
    after each: every answer starts within a second and before anything queued; stale reports are dropped, not said late; the
    enemy's message is cut and what was missed of it is replayed after the answers (as it was: the enemy did not stop talking)."""
    async with Bridge() as b:
        await asyncio.sleep(44.0)
        born: dict[str, float] = {}
        orders: dict[str, float] = {}

        async def report(key: str, speaker: str, text: str, at: float, event_at: float, urgent: bool = False) -> None:
            """A report turn's line: produced at `at` for an event that happened at `event_at` (a task of its own, like a model call)."""
            await asyncio.sleep(max(0.0, at - b.t()))
            b.voice.low_priority = True
            b.voice.report_since = event_at
            born[key] = event_at
            await b.say(key, speaker, text)

        async def hail(key: str, speaker: str, text: str, at: float) -> None:
            """A message from the enemy on the open channel (the enemy module's own task: no report flags, not part of a Captain's turn)."""
            await asyncio.sleep(max(0.0, at - b.t()))
            await b.say(key, speaker, text)

        async def order(key: str, at: float, delay: float, speaker: str, text: str) -> None:
            """A typed order at `at`: what the server does (the floor is taken, whoever talks stops), then the crew's turn, whose model
            call is a task made after the turn began, answers `delay` seconds later."""
            await asyncio.sleep(max(0.0, at - b.t()))
            orders[key] = b.t()
            b.voice.captain_input()
            b.voice.captain_speaks()

            async def turn() -> None:
                b.voice.captain_turn_begin()
                try:
                    async def model_call() -> None:
                        await asyncio.sleep(delay)
                        await b.say(key, speaker, text)                 # (no flag: the turn says it is an answer)
                    await asyncio.ensure_future(model_call())
                    await asyncio.sleep(1.5)                            # the rest of the turn (the ship carries the order out)
                finally:
                    b.voice.captain_turn_end()
            await turn()

        jobs = [
            report("nair", "sensors", "Sensors. Contact T-22 bearing zero nine zero, range ninety kilometres, closing slowly.", 47.0, 46.6),
            report("mensah", "engineering", "Engineering. Reactor at eighty percent, coolant loop two is warm but holding.", 53.0, 52.7),
            hail("archon", "solm", ARCHON, 55.0),
            report("nair2", "sensors", "Sensors. Second contact bearing one eight zero, range sixty kilometres.", 60.0, 59.6),
            report("price", "flight", "Flight. Alpha squadron is launching, six fighters away in three minutes.", 67.5, 45.2),
            order("o1", 57.9, 0.88, "helm", "Helm, aye. Coming to heading two one seven and holding it."),
            order("o2", 67.4, 1.46, "ops", "Ops, aye. The Cocytus is on the main screen."),
            order("o3", 76.6, 0.95, "tactical", "Tactical, aye. Firing on the Cocytus until she goes down."),
        ]
        await asyncio.gather(*[asyncio.ensure_future(j) for j in jobs])
        await b.settle(3.0)
        tr = b.trace()
        bad = check(tr, b.enq)
        # (1) every answer starts within a second of being said, before anything else queued, and cuts the line in flight
        for key in ("o1", "o2", "o3"):
            aid = b.ids[key]
            if aid not in tr.begin:
                bad.append(f"the answer {key} was never said")
                continue
            wait = tr.begin[aid] - b.enq[aid]
            if wait > 1.0:
                bad.append(f"the answer {key} started {wait:.2f} s after it was said (the order was {b.enq[aid] - orders[key]:.2f} s before)")
            since = [i for i in tr.order() if orders[key] < tr.begin[i] < tr.begin[aid] and tr.line[i]["priority"] != "answer"]
            if since:
                bad.append(f"after the order {key}, {[tr.line[i]['speaker'] for i in since]} began before the answer")
            ahead = [i for i in tr.order() if tr.begin[i] <= orders[key] < tr.end.get(i, tr.begin[i]) and tr.line[i]["priority"] != "answer"]
            for i in ahead:
                if tr.reason.get(i) != "cut" or tr.cancel_t.get(i, 1e9) - orders[key] > 0.6:
                    bad.append(f"line {i} ({tr.line[i]['speaker']}) was in flight at the order {key} and was not stopped within 0.6 s")
        # (2) a report is said within REPORT_MAX_AGE_S of its event, or dropped and declared
        limit = speech.REPORT_MAX_AGE_S[Prio.NORMAL]
        for key, ev in born.items():
            lid = b.ids[key]
            if lid in tr.begin and tr.begin[lid] > ev + limit + 0.01 and key != "archon":
                bad.append(f"the report {key} began {tr.begin[lid] - ev:.1f} s after its event (limit {limit:.0f} s)")
        if tr.dropped.get(b.ids["price"]) != "expired":
            bad.append(f"the report of the 22-second-old launch was {tr.dropped.get(b.ids['price'])!r}, not dropped as expired")
        if b.ids["nair2"] in tr.begin and tr.begin[b.ids["nair2"]] > 59.6 + limit:
            bad.append("a report that had waited past its age was said late")
        # (3) the enemy's message: cut by the orders that find it in flight, and what is left of it comes back short, after the answer
        arch = [i for i in tr.order() if tr.line[i]["speaker"] == "solm"]
        cuts = [i for i in arch if tr.reason.get(i) == "cut"]
        if not cuts:
            bad.append("the enemy's message was not cut by an order")
        for i in cuts:
            if not any(0.0 <= tr.cancel_t[i] - t <= 0.6 for t in orders.values()):
                bad.append(f"the enemy's message (line {i}) was cut at {tr.cancel_t[i]:.2f}, not within 0.6 s of an order")
        if not arch or tr.reason.get(arch[-1]) != "done":
            bad.append("the end of the enemy's message was never said")
        else:
            last = arch[-1]
            dur = tr.end[last] - tr.begin[last]
            if dur > 30.0:
                bad.append(f"what was left of the message took the floor for {dur:.1f} s")   # (the missed part, replayed as it was)
            if "Stand down" not in tr.line[last]["text"]:
                bad.append("the point of the message (what it asks) was not said")
            if tr.begin[last] < tr.end[b.ids["o3"]]:
                bad.append("the rest of the message came before the last answer")
        return bad


async def s28_typed_order_over_an_answer() -> list[str]:
    """A typed order arrives while the answer to the previous one is being said: that answer is finished (a typed order talks over nobody), the new
    one follows; a spoken order (the key) does stop it."""
    async with Bridge() as b:
        await b.say("a1", "helm", "Helm, aye. Coming to heading two one seven and holding it steady, Captain.", answer=True)
        await asyncio.sleep(1.0)
        b.voice.captain_input()
        await asyncio.sleep(1.0)
        await b.say("a2", "ops", "Ops, aye. The Cocytus is on the main screen.", answer=True)
        await b.settle(2.0)
        await b.say("a3", "tactical", "Tactical, aye. Firing on the Cocytus until she goes down, standing by.", answer=True)
        await asyncio.sleep(1.0)
        t_key = b.t()
        b.voice.captain_begin()
        await asyncio.sleep(1.0)
        b.voice.captain_end(False)
        await b.settle(1.0)
        tr = b.trace()
        bad = check(tr, b.enq)
        if tr.reason.get(b.ids["a1"]) != "done":
            bad.append(f"the answer to the earlier order was {tr.reason.get(b.ids['a1'])!r}: a typed order cut it")
        if b.ids["a2"] not in tr.begin or tr.begin[b.ids["a2"]] < tr.end[b.ids["a1"]]:
            bad.append("the new answer did not follow the earlier one")
        if tr.reason.get(b.ids["a3"]) != "cut" or tr.cancel_t.get(b.ids["a3"], 1e9) - t_key > 0.6:
            bad.append("a spoken order (the key down) did not stop the answer in flight within 0.6 s")
        return bad


async def s29_report_age() -> list[str]:
    """A report is worth saying for a few seconds after its event: older it is dropped and declared, a warning of danger lasts longer, a producer's
    own expiry is respected, and with no event time the age counts from the moment the line was queued."""
    async with Bridge() as b:
        await asyncio.sleep(100.0)
        now = b.t()

        async def one(key: str, flag: str, born: float | None, text: str, **kw) -> None:  # noqa: ANN003
            async def go() -> None:
                if flag == "urgent":
                    b.voice.urgent = True
                else:
                    b.voice.low_priority = True
                b.voice.report_since = born
                await b.say(key, "sensors", text, **kw)
            await asyncio.ensure_future(go())

        await one("fresh", "report", now - 5.0, "Sensors. Contact bearing zero nine zero.")
        await one("stale", "report", now - 25.0, "Sensors. Contact bearing one eight zero.")
        await one("urgent_old", "urgent", now - 25.0, "Missiles inbound, bearing two seven zero!")
        await one("urgent_stale", "urgent", now - 35.0, "Hull breach on deck four!")
        await one("own_expiry", "report", now - 25.0, "Sensors. Contact bearing two seven zero.", expires_s=40.0)
        await b.settle(1.0)
        # no event time: counted from the moment the line was queued, behind an answer that is long (an answer is never cut down)
        await b.say("busy", "xo", LONG + " " + LONG + " " + LONG, answer=True)
        await one("waits", "report", None, "Sensors. New contact, bearing zero four five.")
        await b.settle(1.0)
        tr = b.trace()
        bad = check(tr, b.enq)
        for key, said in (("fresh", True), ("urgent_old", True), ("own_expiry", True), ("stale", False), ("urgent_stale", False), ("waits", False)):
            lid = b.ids[key]
            if said and lid not in tr.begin:
                bad.append(f"{key}: not said ({tr.dropped.get(lid)!r})")
            if not said and (lid in tr.begin or tr.dropped.get(lid) != "expired"):
                bad.append(f"{key}: {'said late' if lid in tr.begin else repr(tr.dropped.get(lid))}, not dropped as expired")
        return bad


async def s30_reply_replaces_the_rest() -> list[str]:
    """The Captain talks over the enemy's long message and it answers him: the reply is heard, and the rest of the message is not said after it."""
    async with Bridge() as b:
        await b.say("hail", "solm", ARCHON)
        await asyncio.sleep(4.0)
        b.voice.captain_begin()
        await asyncio.sleep(1.0)
        b.voice.captain_end(None)
        await asyncio.sleep(0.4)
        b.voice.captain_turn_begin()
        await b.say("reply", "solm", "Captain, I hear you. We shall speak again.", answer=True)
        b.voice.captain_turn_end()
        await b.settle(2.0)
        tr = b.trace()
        bad = check(tr, b.enq)
        said = [tr.line[i]["text"] for i in tr.order() if tr.line[i]["speaker"] == "solm"]
        if tr.reason.get(b.ids["hail"]) != "cut":
            bad.append("the message was not cut by the Captain")
        if len(said) != 2 or not said[1].startswith("Captain, I hear you"):
            bad.append(f"expected the message, cut, then the reply and nothing more from the enemy; heard: {said!r}")
        return bad


SCENARIOS = [s01_turns, s02_barge_in, s03_typed_order, s04_no_speech, s05_floor_timeout, s06_topic, s07_expiry, s08_overflow, s09_merge,
             s10_rethink, s11_urgent, s12_synth_failure, s13_slow_synthesis, s14_burst, s15_double_press, s16_answer_interrupted,
             s17_flags, s18_compat, s19_stuck_key, s20_new_session, s21_late_answer, s22_turn_with_two_answers, s23_no_audio, s24_startup_delay, s25_hook, s26_first_version_engine, s27_live_replay, s28_typed_order_over_an_answer, s29_report_age, s30_reply_replaces_the_rest]


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
