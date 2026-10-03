"""The crew's speech: who speaks when, and the rules of the floor.

One voice at a time on the bridge, each line synthesised ahead of its turn and streamed to the game at the pace it plays
(never more than `LEAD_S` ahead), so that a line can be stopped within a fraction of a second. The Captain has absolute
priority: the moment he speaks (push-to-talk down, or a typed order) whoever is talking stops at the end of the phrase
(a pause within half a second) or fades out, nobody else starts until his order has been answered, and the answer goes
first. What the others had to say is then re-evaluated by clear rules (producer's priority, topic, expiry) and is spoken,
merged, shortened or dropped: never silently (every drop is logged, counted and sent to the game as `line_dropped`).

Producers call `voice.say(speaker, text, lang, tone, ...)`; the optional keywords are the whole API:
    priority  Prio.ANSWER (a reply to the Captain) · URGENT (danger now) · NORMAL (reports) · LOW (chatter, flavour);
              left out, it follows the context: inside a Captain's turn an answer, `voice.chatter` LOW, `voice.urgent`
              URGENT, otherwise NORMAL (the first version's `voice.low_priority` flag also means a report: NORMAL)
    topic     a key ("contact:T-21", "heat"): a newer line on a topic replaces an older one that has not been said yet
    expires_s seconds after which an unsaid line is dropped (defaults per priority)
    stale_if  a callable: when it returns True at the time the line would start, the line is dropped
    rethink   a coroutine function (text, waited_s, cut_after) -> the text to say now, or None: when a line has waited long
              (`RETHINK_AFTER_S`) or was cut off half way, whoever was going to say it thinks again with the ship as it is now —
              says it updated, changes it, or lets it go (docs/ARCHITETTURA.md §1bis: the agents re-think, the code does not drop
              or shorten what they say). Without it (a canned line) a cut line resumes from the sentence that was cut off
    answer    shorthand for priority=ANSWER
A report (a line said inside a report turn: `voice.low_priority` / `voice.urgent`) that has become old news is re-thought by whoever
was going to say it (the `rethink` hook); a line without one is dropped and declared, never said late.

Game protocol (JSON text frames and binary audio); docs/protocollo_voce.md has the whole story:
    line{id,speaker,name,text,lang,tone,channel,priority,answer,topic,est_s,hold_s,rate}    a line is about to be heard
    audio_begin{line,speaker,rate,est_s,hold_s}                                              its audio starts (subtitle on)
    <binary: uint32 LE line id + PCM16 mono>                                                  paced: about real time
    audio_end{line,dur_s,reason}                                                             it has been heard (reason done or cut)
    cancel{line,reason,fade_ms}                                                              stop it now (flush the audio, fade the subtitle)
    line_dropped{id,speaker,text,reason}                                                     a line that will never be heard (informational)
    floor{state,line}                                                                        state: idle · crew · captain
"""
from __future__ import annotations

import asyncio
import contextvars
import enum
import logging
import re
import struct
from collections import Counter, deque
from dataclasses import dataclass, field
from typing import Awaitable, Callable

from .tts import SpeechStream, TTSEngine

log = logging.getLogger("astra.speech")


class Prio(enum.IntEnum):
    ANSWER = 0      # a reply to the Captain (his read-back, the enemy or the admiral answering his hail)
    URGENT = 1      # danger now: missiles inbound, a hull breach, abandon ship
    NORMAL = 2      # reports and crew business
    LOW = 3         # chatter and flavour: dropped when the Captain speaks


PRIO_NAMES = {Prio.ANSWER: "answer", Prio.URGENT: "urgent", Prio.NORMAL: "normal", Prio.LOW: "low"}
# how long an unsaid line stays worth saying (seconds after it was queued); 0: until it is said
DEFAULT_EXPIRY = {Prio.ANSWER: 90.0, Prio.URGENT: 25.0, Prio.NORMAL: 60.0, Prio.LOW: 15.0}
# a report (a line of a report turn) still unsaid this long after the event it tells of is old news: dropped, never said late
REPORT_MAX_AGE_S = {Prio.URGENT: 30.0, Prio.NORMAL: 18.0}
REPORT_LATE_S = 8.0             # (for the producers of report turns) an item older than this says how old it is: the officer judges it
RETHINK_AFTER_S = 8.0           # a line with a rethink hook that has waited this long (or was cut off) is thought again before it is said
RETHINK_TIMEOUT_S = 4.0         # ... a re-think that does not answer in this time lets the line go (declared: `rethink_timeout`)
MAX_RESUMES = 3                 # a line is taken up again at most this many times

LEAD_S = 0.45                   # audio is never sent more than this ahead of real time (so a stop is heard within it)
CUT_WINDOW_S = 0.5              # a stop looks for the end of a phrase this far ahead, else fades out at once
FADE_CUT_MS = 140               # fade-out of a stop in the middle of a word
FADE_PAUSE_MS = 40              # ... at a pause
PLAYBACK_LAG_S = 0.06           # the game starts playing this long after a chunk is sent
TURN_TIMEOUT_S = 8.0            # the floor is held for the Captain's order at most this long after he let go of the key
TURN_OPEN_MAX_S = 25.0          # a Captain's turn (the crew's model writing the answer) keeps the reports quiet at most this long
KEY_STUCK_S = 45.0              # a key held down this long is taken as released (a "key up" that never arrived must not silence the crew)
MAX_QUEUED = 10                 # more unsaid lines than this and the least important are dropped
MERGE_MAX_CHARS = 240
SYNTH_TIMEOUT_S = 12.0          # a line whose first audio takes longer than this is given up (logged, never silent)
CPS_START = 16.5                # spoken characters per second (learned per language as lines are heard)
AMBIENT = ("mess", "patient")   # people in the mess hall and the medbay: chatter unless they answer the Captain

_SENTENCE = re.compile(r"(?<=[.!?…])\s+")

# context flags of the producer's task (a contextvar: what a task sets is seen by its own say() calls and no one else's)
_ANSWERING: contextvars.ContextVar[bool] = contextvars.ContextVar("astra_answering", default=False)
_BORN: contextvars.ContextVar[float | None] = contextvars.ContextVar("astra_report_since", default=None)
_CLASS: contextvars.ContextVar[Prio | None] = contextvars.ContextVar("astra_voice_class", default=None)


@dataclass(eq=False)
class Line:
    id: int
    speaker: str
    text: str
    lang: str
    tone: str
    prio: Prio
    topic: str | None
    expires: float | None                        # loop time
    stale_if: Callable[[], bool] | None
    enq: float                                   # loop time it was queued
    name: str = ""
    crew: bool = True
    state: str = "queued"                        # queued · playing · done · dropped · cut · merged
    stream: SpeechStream | None = None
    chunks: list[bytes] = field(default_factory=list)
    gen_done: bool = False
    gen_error: bool = False
    first_ready: asyncio.Event = field(default_factory=asyncio.Event)
    synth_t: float = 0.0                         # loop time its audio began to be made
    t_first: float = 0.0                         # loop time the first of it arrived
    first_s: float = 0.0                         # seconds of audio in that first piece
    t_begin: float = 0.0                         # loop time the listener hears the first sound (estimated)
    sent_s: float = 0.0
    est_s: float = 0.0
    cut_at: float | None = None                  # loop time the line must stop at (barge-in)
    cut_reason: str = ""
    cut_fade_ms: int = FADE_CUT_MS
    resumes: int = 0                             # how many times it has been taken up again after a cut
    rethink: "Callable[[str, float, str], Awaitable[str | None]] | None" = None
    rethinking: "asyncio.Task | None" = None     # a re-think under way: the line waits for it
    thought_t: float = 0.0                       # loop time it was last thought again (or queued)
    cut_after: str = ""                          # what was heard of it before it was cut off (for the re-think)
    born: float = 0.0                            # loop time of the news it tells (a report), else when it was queued


def _sentences(text: str) -> list[str]:
    return [p for p in _SENTENCE.split(text) if p]


def _tail(text: str, played: float) -> str | None:
    """What is left of a line stopped after `played` (0..1) of it: from the start of the sentence that was being said (the listener needs
    its beginning), or from the next one when that was nearly over; None when nothing worth saying is left."""
    parts = _sentences(text)
    if len(parts) < 2:
        return text if played < 0.5 else None
    starts, pos = [], 0
    for part in parts:
        i = text.find(part, pos)
        starts.append(i)
        pos = i + len(part)
    cut = played * len(text)
    k = max(i for i, st in enumerate(starts) if st <= cut)
    if starts[k] + len(parts[k]) - cut < 0.25 * len(parts[k]):
        k += 1
    return " ".join(parts[k:]) if k < len(parts) else None


def _as_stream(obj, sample_rate: int) -> SpeechStream:  # noqa: ANN001
    """A voice engine of the first version (its `stream` is an async generator of PCM chunks: nothing to stop, no pauses known) as the
    stream the floor works with. The scripted engines of the tests are of that kind; the real engine already returns a SpeechStream."""
    if hasattr(obj, "stop") and hasattr(obj, "q"):
        return obj
    st = SpeechStream(sample_rate)

    async def pump() -> None:
        try:
            async for pcm in obj:
                st.samples += len(pcm) // 2
                st.q.put_nowait(pcm)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            st.error = exc
        finally:
            st.done = True
            st.q.put_nowait(None)

    task = asyncio.get_running_loop().create_task(pump())
    stop = st.stop

    def stop_all() -> None:
        stop()
        task.cancel()
    st.stop = stop_all
    return st


class _QueueView:
    """What the first version exposed as `voice.q` (an asyncio.Queue): enough for the offline tools (`await q.join()`)."""

    def __init__(self, voice: "Voice") -> None:
        self._v = voice

    def qsize(self) -> int:
        return len(self._v._queue)

    def empty(self) -> bool:
        return not self._v._queue

    async def join(self) -> None:
        while self._v._queue or self._v._cur is not None:
            await asyncio.sleep(0.02)


class Voice:
    def __init__(self, tts: TTSEngine, sink, who: Callable[[str], tuple[str, str, bool]]) -> None:  # noqa: ANN001
        self.tts = tts
        self.sink = sink                        # async (kind, payload) -> None
        self.who = who                          # speaker id -> (display name, voice id, is it a crew member aboard)
        self.q = _QueueView(self)
        self._n = 0
        self._queue: list[Line] = []            # lines not yet said
        self._cur: Line | None = None           # the line being said
        self._changed = asyncio.Event()
        self._last_end = float("-inf")          # loop time the last line stopped being heard
        self._last_speaker = ""
        self._captain_down = False              # the key is held / an order is being typed
        self._down_t = 0.0                      # loop time the key went down
        self._turn_pending = False              # the Captain has spoken and his answer has not started yet
        self._hold_until = 0.0
        self._open_turns = 0                    # Captain's turns being answered (captain_turn_begin .. captain_turn_end)
        self._turn_t = 0.0                      # loop time the latest one began
        self._synth_line: Line | None = None    # the line whose audio is being made (or was made last)
        self._cps: dict[str, float] = {}
        self._synth_rate = 2.5                  # audio seconds the voice makes per second once it is going (what the last lines showed)
        self._floor = ""
        self.muted = False                      # True: nobody is listening, lines are dropped at once
        self.first_audio: dict[int, float] = {}
        self.enqueued: dict[int, float] = {}
        self.stats: Counter = Counter()
        # what the room heard aloud, oldest first: (loop time it ended, who said it, the words heard, said to the end). A line thought
        # again before it was said is here as it was said, one cut off as far as it went: the officers' sense of what the Captain has heard
        self._heard: deque[tuple[float, str, str, bool]] = deque(maxlen=60)

    def waiting(self, limit: int = 8) -> list[tuple[str, str, str]]:
        """What is waiting to be said, in the order it would be said: (who, the words, how urgent). The line being said now is not here."""
        order = sorted((l for l in self._queue if l.state == "queued"), key=lambda l: (l.prio, l.enq, l.id))
        return [(l.name or self.who(l.speaker)[0], l.text, PRIO_NAMES[l.prio]) for l in order[:limit]]

    def heard_since(self, seconds: float) -> list[tuple[float, str, str, bool]]:
        """What was said aloud in the last `seconds`, oldest first: (seconds ago, who said it, the words heard, whether it was said to the end)."""
        now = self._now()
        return [(now - t, who, text, full) for t, who, text, full in self._heard if now - t <= seconds]

    # ------------------------------------------------------------------------------------------ the producer's flags
    @property
    def low_priority(self) -> bool:
        """The first version's flag: True while an event report is being produced. Per task (contextvar)."""
        return _CLASS.get() == Prio.NORMAL

    @low_priority.setter
    def low_priority(self, value: bool) -> None:
        _CLASS.set(Prio.NORMAL if value else None)

    @property
    def chatter(self) -> bool:
        return _CLASS.get() == Prio.LOW

    @chatter.setter
    def chatter(self, value: bool) -> None:
        _CLASS.set(Prio.LOW if value else None)

    @property
    def urgent(self) -> bool:
        return _CLASS.get() == Prio.URGENT

    @urgent.setter
    def urgent(self, value: bool) -> None:
        _CLASS.set(Prio.URGENT if value else None)

    @property
    def answering(self) -> bool:
        """True inside the task that is answering the Captain: every line it says is an answer."""
        return _ANSWERING.get()

    @property
    def report_since(self) -> float | None:
        """Loop time of the event the task's report lines tell of (set by the producer around a report turn; per task). A report still
        unsaid `REPORT_MAX_AGE_S` after it is dropped. None: counted from the moment the line was queued."""
        return _BORN.get()

    @report_since.setter
    def report_since(self, value: float | None) -> None:
        _BORN.set(value)

    def captain_turn_begin(self) -> None:
        """The task calling this is about to answer the Captain (the server's turn worker, for a spoken or typed order). Until it
        ends (`captain_turn_end`) the reports wait: the crew's model streams its officers' lines a second or two apart, and a
        report must not start in the gap between two of them (only to be cut by the next)."""
        if not _ANSWERING.get():
            self._open_turns += 1
            self._turn_t = self._now()
        _ANSWERING.set(True)

    def captain_turn_end(self) -> None:
        """...and has finished (safe to call from any task: only a task that began a Captain's turn ends one). If the turn
        produced no line, the floor is released at once (a silent order)."""
        was = _ANSWERING.get()
        _ANSWERING.set(False)
        if not was:
            return
        self._open_turns = max(0, self._open_turns - 1)
        if self._turn_pending and not self._captain_down and not any(l.prio == Prio.ANSWER for l in self._queue) \
                and not (self._cur is not None and self._cur.prio == Prio.ANSWER):
            self._turn_pending = False
            self._set_floor(self._floor_state())
        self._wake()

    async def preemptible(self, coro, poll: float = 0.05):
        """Await a producer's work (an LLM turn that will write a report) but give it up the moment the Captain takes the
        floor: returns its result, or None when it was cancelled. The caller puts the report back to be written after his
        order has been answered."""
        task = asyncio.ensure_future(coro)
        try:
            while True:
                done, _ = await asyncio.wait({task}, timeout=poll)
                if done:
                    return task.result()
                if self.held:
                    task.cancel()
                    await asyncio.gather(task, return_exceptions=True)
                    self.stats["preempted"] += 1
                    log.info("a report was being written when the Captain took the floor: it waits")
                    return None
        except asyncio.CancelledError:
            task.cancel()
            raise

    # ------------------------------------------------------------------------------------------ time and estimates
    @staticmethod
    def _now() -> float:
        return asyncio.get_running_loop().time()

    def _wake(self) -> None:
        self._changed.set()

    def _estimate(self, text: str, lang: str) -> float:
        return max(0.8, len(text) / self._cps.get(lang, CPS_START))

    @property
    def busy_until(self) -> float:
        """Loop time (= time.monotonic()) when the line being said ends, plus a breath; the same after it ended; 0 before any."""
        if self._cur is not None:
            return self._cur.t_begin + max(self._cur.est_s, self._cur.sent_s) + 0.3
        return self._last_end + 0.3 if self._last_end > float("-inf") else 0.0

    def speaking_s(self) -> float:
        """Seconds left of the line being said now (0: nobody is speaking)."""
        return self._remaining(self._cur) if self._cur is not None and self._cur.state == "playing" else 0.0

    def busy_s(self) -> float:
        """Seconds of speech still ahead (being said + waiting, estimated)."""
        left = 0.0
        if self._cur is not None:
            left += max(0.0, self._cur.t_begin + max(self._cur.est_s, self._cur.sent_s) - self._now())
        for l in self._queue:
            left += self._estimate(l.text, l.lang) + 0.3
        return left

    def game_status(self, msg: dict) -> None:
        """The game reports what became of a line it was given: `voice_status{line,state,detail}`, state one of started,
        stalled (the audio ran dry while the line was still being said), failed (it could not play the line at all: the
        subtitle was shown and nobody spoke), silent (a game without an audio device, a test run: the subtitle only), finished.
        Logged and counted; a failure is a warning."""
        state = str(msg.get("state", ""))
        self.stats[f"game_{state}"] += 1
        text = f"the game says line {msg.get('line')} is {state}" + (f" ({msg.get('detail')})" if msg.get("detail") else "")
        (log.warning if state in ("stalled", "failed") else log.debug)(text)

    # ------------------------------------------------------------------------------------------ enqueue
    async def say(self, speaker: str, text: str, lang: str, tone: str, *, priority: Prio | str | None = None, topic: str | None = None,
                  expires_s: float | None = None, stale_if: Callable[[], bool] | None = None, answer: bool | None = None,
                  rethink: "Callable[[str, float, str], Awaitable[str | None]] | None" = None) -> int:
        """Queue a line; returns its id. Nothing is sent to the game until the line's turn comes (see the module docstring)."""
        text = (text or "").strip()
        self._n += 1
        lid = self._n
        now = self._now()
        self.enqueued[lid] = now
        if len(self.enqueued) > 2000:
            for k in sorted(self.enqueued)[:1000]:
                self.enqueued.pop(k, None)
                self.first_audio.pop(k, None)
        name, _, crew = self.who(speaker)
        prio = self._priority(speaker, priority, answer)
        if not text:
            self._drop_info(lid, speaker, text, "empty", prio)
            return lid
        if self.muted:
            self._drop_info(lid, speaker, text, "no_listener", prio)
            return lid
        exp = DEFAULT_EXPIRY[prio] if expires_s is None else expires_s
        deadline = (now + exp) if exp else None
        born = now
        if expires_s is None and prio in REPORT_MAX_AGE_S and _CLASS.get() == prio:
            # a line of a report turn tells of news: with a rethink hook, whoever says it thinks again when it has waited (see _reap);
            # without one, it is worth saying for a few seconds after the event, never late
            born = _BORN.get() if _BORN.get() is not None else now
            if rethink is None:
                limit = born + REPORT_MAX_AGE_S[prio]
                deadline = limit if deadline is None else min(deadline, limit)
                if now >= limit:
                    log.info("line %d (%s): a report of something that happened %.0f s ago is old news", lid, speaker, now - born)
                    self._drop_info(lid, speaker, text, "expired", prio)
                    return lid
        line = Line(id=lid, speaker=speaker, text=text, lang=lang, tone=tone or "calm", prio=prio, topic=topic,
                    expires=deadline if rethink is None else None, stale_if=stale_if, enq=now, name=name, crew=crew,
                    rethink=rethink, thought_t=born, born=born)
        line.est_s = self._estimate(text, lang)
        self._enqueue(line)
        return lid

    def _priority(self, speaker: str, priority: Prio | str | None, answer: bool | None) -> Prio:
        if answer:
            return Prio.ANSWER
        if isinstance(priority, str):
            priority = {v: k for k, v in PRIO_NAMES.items()}[priority.lower()]
        if priority is not None:
            return Prio(priority)
        if _ANSWERING.get():
            return Prio.ANSWER
        if _CLASS.get() is not None:
            return _CLASS.get()
        return Prio.LOW if speaker.startswith(AMBIENT) else Prio.NORMAL

    def _enqueue(self, line: Line) -> None:
        # a newer line on the same topic replaces an older one that has not been said yet
        if line.topic:
            for old in [l for l in self._queue if l.topic == line.topic]:
                if line.prio <= old.prio:
                    self._drop(old, "superseded")
                else:
                    self._drop(line, "superseded")
                    return
        # someone cut off who now answers the Captain says no more of what he was saying: the reply takes the place of the rest
        if line.prio == Prio.ANSWER and not line.crew:
            for old in [l for l in self._queue if l.speaker == line.speaker and l.resumes]:
                self._drop(old, "superseded")
        # the same officer's next sentence joins the one still waiting (one breath, one subtitle)
        if self._queue and self._can_merge(self._queue[-1], line):
            self._merge(self._queue[-1], line)
            return
        self._queue.append(line)
        self._overflow()
        # the answer goes first; a report of danger does not wait for a chat
        cur = self._cur
        if cur is not None and cur.state == "playing":
            if line.prio == Prio.ANSWER and cur.prio != Prio.ANSWER:
                self._request_cut(cur, "answer_first")
            elif line.prio == Prio.URGENT and cur.prio >= Prio.NORMAL and self._remaining(cur) > 1.5:
                self._request_cut(cur, "urgent_first")
        self._wake()

    def _can_merge(self, a: Line, b: Line) -> bool:
        return (a.speaker == b.speaker and a.state == "queued" and a.prio == b.prio and a.prio >= Prio.NORMAL and a.lang == b.lang
                and a.tone == b.tone and not a.topic and not b.topic and b.enq - a.enq < 4.0
                and len(a.text) + len(b.text) < MERGE_MAX_CHARS and (a.stream is None or a.stream.seconds < 0.5))

    def _merge(self, a: Line, b: Line) -> None:
        a.text = f"{a.text} {b.text}"
        a.est_s = self._estimate(a.text, a.lang)
        if a.expires is not None and b.expires is not None:
            a.expires = max(a.expires, b.expires)
        if a.stream is not None:                    # its audio was only just begun: start again with the whole text
            self._reset_synth(a)
        self.stats["merged"] += 1
        self._drop_info(b.id, b.speaker, b.text, f"merged_into_{a.id}", b.prio)
        log.info("line %d merged into line %d (%s)", b.id, a.id, a.speaker)
        self._wake()

    def _overflow(self) -> None:
        while len(self._queue) > MAX_QUEUED:
            self._drop(max(self._queue, key=lambda l: (l.prio, -l.enq)), "overflow")

    # ------------------------------------------------------------------------------------------ dropping (never silent)
    def _drop_info(self, lid: int, speaker: str, text: str, reason: str, prio: Prio) -> None:
        self.stats[f"dropped_{reason.split('_into_')[0]}"] += 1
        log.info("line %d (%s, %s) not spoken: %s — %s", lid, speaker, PRIO_NAMES[prio], reason, text[:70])
        try:
            asyncio.get_running_loop().create_task(self.sink("json", {"type": "line_dropped", "id": lid, "speaker": speaker,
                                                                        "text": text[:120], "reason": reason}))
        except RuntimeError:
            pass

    def _drop(self, line: Line, reason: str) -> None:
        if line in self._queue:
            self._queue.remove(line)
        line.state = "dropped"
        self._reset_synth(line, keep_lines=True)
        if self._synth_line is line:
            self._synth_line = None
        self._drop_info(line.id, line.speaker, line.text, reason, line.prio)

    def _reap(self) -> None:
        """Expired, stale and unmakeable lines leave the queue."""
        now = self._now()
        for l in list(self._queue):
            if l.expires is not None and now > l.expires:
                self._drop(l, "expired")
            elif l.gen_error and not l.chunks:
                self._drop(l, "synth_failed")
            elif l.stream is not None and not l.first_ready.is_set() and now - l.synth_t > SYNTH_TIMEOUT_S:
                log.error("line %d: no audio within %.0f s", l.id, SYNTH_TIMEOUT_S)
                self._drop(l, "synth_timeout")
            elif l.stale_if is not None:
                try:
                    if l.stale_if():
                        self._drop(l, "stale")
                except Exception:  # noqa: BLE001
                    log.exception("stale_if failed")

    def _start_rethink(self, line: Line, now: float) -> None:
        """Whoever was going to say the line thinks again, with the ship as it is now; the line waits for the answer (the floor goes on)."""
        waited = now - line.born
        cut_after = line.cut_after

        async def go() -> None:
            try:
                new = await asyncio.wait_for(line.rethink(line.text, waited, cut_after), timeout=RETHINK_TIMEOUT_S)
                why = "rethought"
            except asyncio.TimeoutError:
                new, why = None, "rethink_timeout"
            except Exception:  # noqa: BLE001
                log.exception("line %d: the re-think failed", line.id)
                new, why = None, "rethink_failed"
            line.rethinking = None
            if line.state != "queued":
                return
            if not new or not new.strip():
                log.info("line %d (%s) thought again after %.0f s: not worth saying now", line.id, line.speaker, waited)
                self.stats["rethought_dropped"] += 1
                self._drop(line, why)
                return
            new = new.strip()
            self.stats["rethought"] += 1
            if new != line.text:
                log.info("line %d (%s) thought again after %.0f s: %r -> %r", line.id, line.speaker, waited, line.text[:60], new[:60])
                line.text, line.est_s = new, self._estimate(new, line.lang)
                self._reset_synth(line)
            line.thought_t, line.born, line.cut_after = self._now(), self._now(), ""
            self._wake()

        line.rethinking = asyncio.get_running_loop().create_task(go())

    def drop_low_priority(self) -> int:
        """The Captain speaks: chatter is no longer worth saying (reports wait their turn: see `captain_begin`)."""
        low = [l for l in self._queue if l.prio == Prio.LOW]
        for l in low:
            self._drop(l, "captain_spoke")
        return len(low)

    async def clear(self, reason: str = "cleared") -> int:
        """Nothing more will be said (the game went away, a new campaign): drop everything and stop the line being said."""
        n = len(self._queue)
        for l in list(self._queue):
            self._drop(l, reason)
        if self._cur is not None:
            self._request_cut(self._cur, reason, also_answers=True)
        self._captain_down = self._turn_pending = False        # (the game went away with the key down, or a new game begins: nobody holds the floor)
        self._hold_until = 0.0
        self._open_turns = 0
        self._set_floor(self._floor_state())
        self._wake()
        return n

    # ------------------------------------------------------------------------------------------ the Captain
    def captain_begin(self, cut_answers: bool = True) -> None:
        """The Captain starts to speak (push-to-talk down) or an order is typed: whoever talks stops at the end of the phrase
        (within half a second) and nobody starts until his order has been answered. `cut_answers` False: an answer to his earlier
        order that is being said is finished (a typed order talks over nobody)."""
        self._captain_down = True
        self._down_t = self._now()
        self._turn_pending = True
        self._hold_until = 0.0
        self.stats["captain_begin"] += 1
        self.drop_low_priority()
        if self._cur is not None:
            self._request_cut(self._cur, "captain", also_answers=cut_answers)
        self._set_floor("captain")
        self._wake()

    def captain_end(self, heard: bool | None = None) -> None:
        """The key is up. `heard` False: nothing that sounds like speech was recorded, so no order is coming."""
        self._captain_down = False
        if heard is False:
            self._turn_pending = False
        else:
            self._hold_until = self._now() + TURN_TIMEOUT_S
        self._set_floor(self._floor_state())
        self._wake()

    def captain_input(self) -> None:
        """A typed order arrives: begin and end in one. Whoever was talking is stopped, unless it is the answer to his earlier order
        (that is finished: a typed order talks over nobody, and the answer to it follows)."""
        self.captain_begin(cut_answers=False)
        self.captain_end(True)

    def captain_speaks(self) -> None:
        """The hook the server's `_captain_speaks` calls when the Captain starts to talk (his key goes down, or an order is typed):
        whoever is talking stops (at the next pause within half a second, else a fast fade) and the chatter waiting is dropped.
        Safe to call again and next to `captain_begin` / `captain_input` (a line already being stopped is left alone). With his
        key down that is all; without it, it also takes the floor for the answer, as a typed order does."""
        if self._captain_down:
            self.drop_low_priority()
            if self._cur is not None:
                self._request_cut(self._cur, "captain", also_answers=True)
            self._wake()
        else:
            self.captain_input()

    @property
    def held(self) -> bool:
        """The floor belongs to the Captain: only answers may start (and none while his key is down)."""
        if self._captain_down:
            if self._now() - self._down_t <= KEY_STUCK_S:
                return True
            log.warning("the key has been down for %.0f s: taken as released (a 'key up' that never came)", KEY_STUCK_S)
            self._captain_down = False
            self._turn_pending = False                # nobody is waiting for an order that was never finished
            self._set_floor(self._floor_state())
            return False
        if self._turn_pending:
            if self._hold_until and self._now() > self._hold_until:
                self._turn_pending = False
                log.info("the floor is released: no answer to the Captain came within %.0f s", TURN_TIMEOUT_S)
                self._set_floor(self._floor_state())
                return False
            return True
        if self._open_turns > 0:
            if self._now() - self._turn_t <= TURN_OPEN_MAX_S:
                return True
            log.warning("a Captain's turn has been open for %.0f s: the reports may go on", TURN_OPEN_MAX_S)
            self._open_turns = 0
        return False

    def _floor_state(self) -> str:
        if self._captain_down or self._turn_pending:
            return "captain"
        return "crew" if self._cur is not None else "idle"

    def _set_floor(self, state: str) -> None:
        if state == self._floor:
            return
        self._floor = state
        try:
            asyncio.get_running_loop().create_task(self.sink("json", {"type": "floor", "state": state,
                                                                       "line": self._cur.id if self._cur else None}))
        except RuntimeError:
            pass

    # ------------------------------------------------------------------------------------------ stopping a line
    def _remaining(self, line: Line) -> float:
        return max(0.0, line.t_begin + max(line.est_s, line.sent_s) - self._now())

    def _request_cut(self, line: Line, reason: str, also_answers: bool = False) -> None:
        """Ask the line being said to stop: at the next pause within CUT_WINDOW_S of where the listener is now, else with a
        fast fade-out."""
        if line.cut_at is not None or line.state != "playing":
            return
        if line.prio == Prio.ANSWER and not also_answers:
            return
        now = self._now()
        pos = max(0.0, now - line.t_begin - PLAYBACK_LAG_S)                # where in the audio the listener is
        bounds = line.stream.boundaries if line.stream is not None else []
        nxt = next((b for b in bounds if pos < b <= pos + CUT_WINDOW_S), None)
        if nxt is not None and line.t_begin + nxt > now:
            line.cut_at, line.cut_fade_ms = line.t_begin + nxt, FADE_PAUSE_MS
        else:
            line.cut_at, line.cut_fade_ms = now + 0.03, FADE_CUT_MS
        line.cut_reason = reason
        self._wake()

    # ------------------------------------------------------------------------------------------ synthesis
    def _best(self) -> Line | None:
        """The line that would be said next: the most important, the oldest of them; while the floor is the Captain's, only
        answers count."""
        self._reap()
        pool = [l for l in self._queue if l.prio == Prio.ANSWER] if self.held else list(self._queue)
        cur = self._cur
        due = cur is None or cur.state != "playing" or self._remaining(cur) < 1.5     # the next line's turn is now or nearly
        while True:
            line = min((l for l in pool if l.rethinking is None), key=lambda l: (l.prio, l.enq, l.id), default=None)
            if line is None:
                return None
            if due and line.rethink is not None and (line.cut_after or self._now() - line.thought_t > RETHINK_AFTER_S):
                # its turn has come but it has waited (or was cut off): whoever says it thinks again first — just in time, once —
                # and meanwhile the next line may go. One re-think at a time: the lines behind it are thought again when their own
                # turn comes (all of them at once, in a busy battle, were a dozen model calls for lines that then waited again)
                pool = [l for l in pool if l is not line]
                if not any(l.rethinking is not None for l in self._queue):
                    self._start_rethink(line, self._now())
                continue
            return line

    def _reset_synth(self, line: Line, keep_lines: bool = False) -> None:
        if line.stream is not None:
            line.stream.stop()
        line.stream, line.chunks, line.gen_done, line.gen_error = None, [], False, False
        line.first_ready = asyncio.Event()
        if self._synth_line is line:
            self._synth_line = None

    def _pump_synth(self) -> None:
        """Keep the next line's audio being made, one line at a time (the voices share one core)."""
        want = self._best()
        if want is None:
            return
        cur = self._synth_line
        if cur is not None and cur.state == "queued" and not cur.gen_done:
            if cur is want:
                return
            if want.prio < cur.prio:                    # something more important came in: the other one waits
                self._reset_synth(cur)
            else:
                return                                  # still making one line; the wanted one is made after it
        if want.stream is None:
            self._start_synth(want)
        elif want.gen_done:                             # the wanted line is ready: make the one after it
            nxt = min((l for l in self._queue if l is not want and l.stream is None), key=lambda l: (l.prio, l.enq, l.id), default=None)
            if nxt is not None and (not self.held or nxt.prio == Prio.ANSWER):
                self._start_synth(nxt)

    def _start_synth(self, line: Line) -> None:
        voice = self.who(line.speaker)[1]
        can = getattr(self.tts, "can_speak", None)
        lang = line.lang if (can is None or can(line.lang)) else "en"
        try:
            stream = self.tts.stream(line.text, voice, lang, tone=line.tone)
        except TypeError:                               # an engine with the first version's signature (no tone)
            stream = self.tts.stream(line.text, voice, lang)
        stream = _as_stream(stream, self.tts.sample_rate)
        line.stream = stream
        line.chunks, line.gen_done, line.gen_error = [], False, False
        line.first_ready = asyncio.Event()
        line.synth_t = self._now()
        line.t_first, line.first_s = 0.0, 0.0
        self._synth_line = line
        asyncio.get_running_loop().create_task(self._collect(line, stream))

    async def _collect(self, line: Line, stream: SpeechStream) -> None:
        """Move the generated audio into the line as it arrives."""
        try:
            async for pcm in stream:
                if stream is not line.stream:
                    return                                          # restarted with other text: this audio is stale
                if not line.chunks:
                    line.t_first, line.first_s = self._now(), len(pcm) / 2 / stream.sample_rate
                line.chunks.append(pcm)
                line.first_ready.set()
                self._wake()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("voice line %s failed", line.id)
            if stream is line.stream:
                line.gen_error = True
        finally:
            if stream is line.stream:
                line.gen_done = True
                line.first_ready.set()
                dt = self._now() - line.t_first
                if line.t_first and not line.gen_error and dt > 0.4 and stream.seconds > line.first_s:
                    rate = min(12.0, max(0.3, (stream.seconds - line.first_s) / dt))
                    self._synth_rate = 0.6 * self._synth_rate + 0.4 * rate
                self._wake()

    # ------------------------------------------------------------------------------------------ turns
    def _gap_before(self, line: Line) -> float:
        """The breath before a line: little for an answer to the Captain or a warning, more between two voices."""
        if line.prio == Prio.ANSWER:
            return 0.10
        if line.prio == Prio.URGENT:
            return 0.12
        return 0.18 if line.speaker == self._last_speaker else 0.34

    async def run(self) -> None:
        """The floor: pick the next line, wait for its turn, say it. Never returns."""
        while True:
            try:
                line = await self._next()
                await self._play(line)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - one bad line must not silence the crew
                log.exception("the voice loop failed on a line; going on")
                self._cur = None
                await asyncio.sleep(0.05)

    async def _wait(self, timeout: float | None) -> None:
        try:
            await asyncio.wait_for(self._changed.wait(), timeout=None if timeout is None else max(0.001, timeout))
        except asyncio.TimeoutError:
            pass
        self._changed.clear()

    async def _next(self) -> Line:
        """Wait for the next line to be sayable: the best one, its audio ready, its breath taken, the floor free for it."""
        while True:
            self._pump_synth()
            line = self._best()
            if line is None:
                self._set_floor(self._floor_state())
                # idle, or holding the floor for the Captain's order: wake when the hold runs out
                wait = None
                if self._captain_down:                       # (a key held for too long is let go of: see KEY_STUCK_S)
                    wait = max(0.05, self._down_t + KEY_STUCK_S - self._now())
                elif self._turn_pending and self._hold_until:
                    wait = max(0.01, self._hold_until - self._now())
                elif self._open_turns:
                    wait = max(0.05, self._turn_t + TURN_OPEN_MAX_S - self._now())
                await self._wait(wait)
                continue
            if self._captain_down:
                # he is speaking again: nobody starts, not even the answer to his earlier order (it is made meanwhile and follows
                # the moment he lets go); a key held for too long is let go of (KEY_STUCK_S)
                await self._wait(max(0.05, self._down_t + KEY_STUCK_S - self._now()))
                continue
            now = self._now()
            if line.gen_error and not line.chunks:
                self._drop(line, "synth_failed")
                continue
            if line.gen_done and not line.chunks:
                self._drop(line, "no_audio")                # (only punctuation, or a voice that made silence: a subtitle with no voice)
                continue
            if not self._can_start_smoothly(line):
                await self._wait(0.05)
                continue
            start_at = self._last_end + self._gap_before(line)
            if now < start_at:
                await self._wait(start_at - now)
                continue
            self._queue.remove(line)
            if self._synth_line is line:
                self._synth_line = None
            return line

    def _steady_rate(self, line: Line, made: float) -> float:
        """Audio seconds the voice makes per second once it is going: counted from the first audio, not from the moment the line was
        asked for (the model's start-up delay is not its speed). Until a quarter of a second of it has been seen, what the last
        lines showed."""
        dt = self._now() - line.t_first
        if dt >= 0.25 and made > line.first_s:
            return (made - line.first_s) / dt
        return self._synth_rate

    def _can_start_smoothly(self, line: Line) -> bool:
        """Has the line enough audio to start without running dry? The machine is shared with the game: when the voice makes
        speech slower than it plays (rate r < 1, audio seconds per second), playing at once would stutter, so the start waits
        until what is buffered lasts until the rest has been made (made >= total x (1 - 0.8 r), with a margin). At the usual
        rate (several times real time) that is nothing: the line starts with its first audio."""
        st = line.stream
        if st is None or not line.first_ready.is_set():
            return False
        if line.gen_done or line.chunks == []:
            return line.gen_done
        made = st.seconds
        if made <= 0.0:
            return False
        r = self._steady_rate(line, made)
        total = max(line.est_s, made)
        return made >= total * max(0.0, 1.0 - 0.8 * r) + (0.15 if r < 1.25 else 0.0)

    # ------------------------------------------------------------------------------------------ saying a line
    def _hold_for(self, line: Line, est: float) -> float:
        """How long the subtitle should stay: the audio and a second, or the time to read it (17 characters a second)."""
        return round(min(12.0, max(est + 1.0, 1.4 + len(line.text) / 17.0)), 2)

    async def _send(self, kind: str, payload) -> None:  # noqa: ANN001
        try:
            await self.sink(kind, payload)
        except Exception:  # noqa: BLE001 - a game that went away must not stop the loop
            log.debug("sink failed", exc_info=True)

    async def _play(self, line: Line) -> None:
        stream = line.stream
        assert stream is not None
        rate = stream.sample_rate
        now = self._now()
        line.state, self._cur = "playing", line
        line.t_begin = now
        est = stream.seconds if line.gen_done else max(line.est_s, stream.seconds)
        line.est_s = est
        hold = self._hold_for(line, est)
        self.first_audio[line.id] = now
        if line.prio == Prio.ANSWER:
            self._turn_pending = False               # his answer has begun: the others may follow it
        self._set_floor("crew")
        await self._send("json", {"type": "line", "id": line.id, "speaker": line.speaker, "name": line.name, "text": line.text,
                                  "lang": line.lang, "tone": line.tone, "channel": not line.crew, "priority": PRIO_NAMES[line.prio],
                                  "answer": line.prio == Prio.ANSWER, "topic": line.topic, "est_s": round(est, 2), "hold_s": hold,
                                  "rate": rate})
        await self._send("json", {"type": "audio_begin", "line": line.id, "speaker": line.speaker, "rate": rate,
                                  "est_s": round(est, 2), "hold_s": hold})
        reason = "done"
        sent = 0.0
        idx = 0
        try:
            while True:
                if line.cut_at is not None and self._now() >= line.cut_at:
                    reason = "cut"
                    break
                self._pump_synth()
                if idx < len(line.chunks):
                    pcm = line.chunks[idx]
                    now = self._now()
                    slack = (now - line.t_begin) - sent
                    if slack > 0.05:                       # the audio ran dry (slow synthesis): the listener's clock restarts here
                        line.t_begin += slack
                    due = line.t_begin + sent - LEAD_S
                    if now < due:
                        await self._pause(line, due - now)
                        continue
                    await self._send("audio", struct.pack("<I", line.id) + pcm)
                    sent += len(pcm) / 2 / rate
                    line.sent_s = sent
                    idx += 1
                    continue
                if line.gen_done:
                    break
                await self._pause(line, 0.25)
            if reason == "done":
                self._learn_pace(line, sent)
                while True:                                # everything is sent: let it play out
                    end = line.t_begin + sent
                    now = self._now()
                    if now >= end:
                        break
                    if line.cut_at is not None and now >= line.cut_at:
                        reason = "cut"
                        break
                    await self._pause(line, end - now)
        finally:
            await self._finish(line, reason, sent)

    async def _pause(self, line: Line, dt: float) -> None:
        """Sleep, but wake for a stop request (the line's cut time) or any change."""
        if line.cut_at is not None:
            dt = min(dt, max(0.0, line.cut_at - self._now()))
        await self._wait(dt)

    def _learn_pace(self, line: Line, sent: float) -> None:
        if sent > 0.5 and len(line.text) > 12:
            old = self._cps.get(line.lang, CPS_START)
            self._cps[line.lang] = 0.8 * old + 0.2 * (len(line.text) / sent)

    async def _finish(self, line: Line, reason: str, sent: float) -> None:
        now = self._now()
        line.state = "done" if reason == "done" else "cut"
        played = 1.0 if reason == "done" else min(1.0, max(0.0, (now - line.t_begin) / max(line.est_s, 0.5)))
        words = line.text if reason == "done" else line.text[:int(played * len(line.text))].strip()
        if words and sent > 0.2:
            self._heard.append((now, line.name or self.who(line.speaker)[0], words, reason == "done"))
        if line.stream is not None:
            line.stream.stop()
        if reason == "cut":
            self.stats[f"cut_{line.cut_reason or 'other'}"] += 1
            await self._send("json", {"type": "cancel", "line": line.id, "reason": line.cut_reason or "cut", "fade_ms": line.cut_fade_ms})
        await self._send("json", {"type": "audio_end", "line": line.id, "dur_s": round(sent, 2), "reason": reason})
        self.stats["spoken" if reason == "done" else "cut"] += 1
        self._last_end = now
        self._last_speaker = line.speaker
        self._cur = None
        log.debug("voice line %d (%s): %.2f s of audio, %s", line.id, line.speaker, sent, reason)
        if reason == "cut":
            self._after_cut(line, sent)
        self._set_floor(self._floor_state())
        self._wake()

    def _after_cut(self, line: Line, sent: float) -> None:
        """A line stopped half way. With a rethink hook, whoever was saying it thinks again, knowing what was heard before the cut (they
        may go on, say it differently, or let it go: the Captain has spoken since). Without one, what was not heard is said once the
        floor is free, from the sentence that was being said (the listener needs the beginning of what was cut). A line cut again goes on
        again (`MAX_RESUMES` times). It keeps its place at the front of its class, ahead of what was queued after it. Answers and chatter
        are not taken up again: he has spoken since, and small talk is not worth it."""
        now = self._now()
        played = min(1.0, max(0.0, (now - line.t_begin) / max(line.est_s, 0.5)))
        text: str | None = None
        if line.prio not in (Prio.NORMAL, Prio.URGENT) or line.cut_reason not in ("captain", "answer_first", "urgent_first"):
            why = "not repeated"
        elif now - line.enq >= (25.0 if line.crew else 60.0) or line.resumes >= MAX_RESUMES:
            why = "too old to say again"
        elif not line.crew and any(l.speaker == line.speaker and l.prio == Prio.ANSWER for l in self._queue):
            why = "the reply to the Captain takes its place"
        elif line.rethink is not None:
            text = line.text
            why = "thought again"
        else:
            text = _tail(line.text, played)
            why = "heard enough"
        if not text:
            log.info("line %d was cut at %.0f %%: %s", line.id, played * 100, why)
            return
        self._n += 1
        exp = now + (20.0 if line.crew else 40.0)
        again = Line(id=self._n, speaker=line.speaker, text=text, lang=line.lang, tone=line.tone, prio=line.prio, topic=line.topic,
                     expires=None if line.rethink else (exp if line.expires is None else min(exp, line.expires)), stale_if=line.stale_if,
                     enq=line.enq, name=line.name, crew=line.crew, resumes=line.resumes + 1, rethink=line.rethink,
                     thought_t=line.thought_t, born=line.born,
                     cut_after=line.text[:max(0, int(played * len(line.text)))].strip() if line.rethink else "")
        again.est_s = self._estimate(again.text, again.lang)
        self.enqueued[again.id] = now
        self._queue.append(again)
        self.stats["resumed"] += 1
        log.info("line %d was cut at %.0f %%: %s said again as line %d after the floor is free", line.id, played * 100,
                 "the rest of it is" if text != line.text else "it is", again.id)
