"""Scenarios for what VOCI-3 asked of the speech floor (astra_mind/speech.py): nothing addressed to the Captain is ever lost to the machinery. Same harness as
`voice_floor` (virtual time, a fake voice engine, a fake game that records everything it receives, the same invariants).

    uv run python -m bench.voci3_floor           (from mind/)        -v prints the game's view of each scenario

The 5 October games lost an answer to a re-think that timed out (the helm's), another to a voice that was not made in 12 s (the engineer's), and the admiral's calls to the
queue's size. An answer to the Captain (`answer=True`) and a line addressed to him (`addressed=True`) are `protected`: they are never dropped for the queue's length, an age, a
producer's `stale_if`, a voice that could not be made (it is asked for again, and then he reads it: a `notice`) or a re-think that failed (it is said as it stands). The rest of
the floor's rules are unchanged (and `voice_floor` still passes)."""
from __future__ import annotations

import asyncio
import sys
import traceback

from astra_mind import speech
from astra_mind.speech import MAX_QUEUED, SYNTH_RETRIES

from .voice_floor import LAST, LONG, Bridge, FakeTTS, Trace, check, run, timeline


class FlakyTTS(FakeTTS):
    """A voice engine that fails the first `fail_first[text]` times a text is asked for (the machine was busy), then makes it."""

    def __init__(self, **kw) -> None:  # noqa: ANN003
        super().__init__(**kw)
        self.fail_first: dict[str, int] = {}
        self.asked: dict[str, int] = {}

    def stream(self, text: str, voice: str, lang: str, tone: str | None = None):  # noqa: ANN201
        n = self.asked[text] = self.asked.get(text, 0) + 1
        if n <= self.fail_first.get(text, 0):
            self.fail.add(text)
        else:
            self.fail.discard(text)
        return super().stream(text, voice, lang, tone)


def trace_of(b: Bridge) -> Trace:
    """The game's view of the floor; a `notice` (a line the voice could not make, sent as text) counts as delivered."""
    tr = b.trace()
    tr.notices = {}
    for _, kind, p in b.rec.events:
        if kind == "json" and p.get("type") == "notice":
            tr.notices[p["id"]] = p
            tr.dropped[p["id"]] = "noticed"            # (it is neither heard nor dropped: the invariant that nothing vanishes is checked against it)
    return tr


# ------------------------------------------------------------------------------------------------ scenarios
async def v01_the_queue_never_loses_an_answer_or_a_call() -> list[str]:
    """More lines wait than the queue holds: the chatter and the reports are dropped (declared), and not one answer to the Captain or call addressed to him."""
    async with Bridge() as b:
        await b.say("busy", "xo", LONG)
        for i in range(8):
            await b.say(f"a{i}", ["helm", "ops", "tactical", "sensors"][i % 4], f"Answer number {i}, to what the Captain asked.", answer=True)
        for i in range(8):
            await b.say(f"c{i}", "admiral", f"Call number {i} from Fleet command to the Aquila.", addressed=True)
        for i in range(10):
            await b.say(f"r{i}", "sensors", f"Report number {i}, nothing the Captain must hear.")
        await b.settle(2.0, limit=400.0)
        tr = trace_of(b)
        bad = [m for m in check(tr, b.enq) if not m.startswith("I9")]       # (eight answers at once wait behind one another: that is not what is measured here)
        for i in range(8):
            for key in (f"a{i}", f"c{i}"):
                lid = b.ids[key]
                why = str(tr.dropped.get(lid, ""))
                into = int(why.rsplit("_", 1)[1]) if why.startswith("merged_into_") else None     # (one officer's consecutive lines become one: the words are said)
                if lid not in tr.begin and (into is None or into not in tr.begin):
                    bad.append(f"{key} was never said ({why or 'no word'})")
        n = sum(1 for r in tr.dropped.values() if r == "overflow")
        if n < 5:
            bad.append(f"the unprotected reports should have overflowed the queue, {n} did")
        if len(b.voice._queue) > MAX_QUEUED:
            bad.append("the queue never came back under its limit")
        return bad


async def v02_an_age_does_not_lose_them() -> list[str]:
    """A producer's expiry and its `stale_if` drop a report; not an answer to the Captain or a call addressed to him."""
    async with Bridge() as b:
        await b.say("busy", "xo", LONG + " " + LONG)
        await b.say("report", "sensors", "A report with a short life, waiting behind a long speech.", expires_s=1.0)
        await b.say("answer", "helm", "The answer to his order, with a short life it must not have.", answer=True, expires_s=1.0)
        await b.say("call", "admiral", "A call to the Aquila, that a producer thinks stale.", addressed=True, stale_if=lambda: True)
        await b.say("stale", "ops", "A report its producer finds stale by the time it would start.", stale_if=lambda: True)
        await b.settle(2.0)
        tr = trace_of(b)
        bad = check(tr, b.enq)
        for key in ("answer", "call"):
            if b.ids[key] not in tr.begin:
                bad.append(f"{key} was lost ({tr.dropped.get(b.ids[key])})")
        for key in ("report", "stale"):
            if b.ids[key] in tr.begin:
                bad.append(f"{key} should have been dropped")
        return bad


async def v03_a_voice_that_stumbles_is_asked_again() -> list[str]:
    """The voice of an answer, and of a call to the Captain, fails the first time (the machine was busy): it is asked for again and the line is heard; a report in the
    same case is dropped, declared."""
    async with Bridge() as b:
        tts = b.tts = b.voice.tts = FlakyTTS()
        tts.fail_first = {"The answer to the order.": 1, "A call from Fleet command.": SYNTH_RETRIES, "A report that stumbles.": 1}
        await b.say("answer", "helm", "The answer to the order.", answer=True)
        await b.say("call", "admiral", "A call from Fleet command.", addressed=True)
        await b.say("report", "sensors", "A report that stumbles.")
        await b.settle(2.0)
        tr = trace_of(b)
        bad = check(tr, b.enq)
        if b.ids["answer"] not in tr.begin:
            bad.append(f"the answer was lost ({tr.dropped.get(b.ids['answer'])})")
        if b.ids["call"] not in tr.begin:
            bad.append(f"the call that failed {SYNTH_RETRIES} times and then worked was lost ({tr.dropped.get(b.ids['call'])})")
        if tr.dropped.get(b.ids["report"]) != "synth_failed":
            bad.append(f"the report that stumbled should be dropped, declared: {tr.dropped.get(b.ids['report'])}")
        if tts.asked["The answer to the order."] != 2:
            bad.append(f"the answer's voice was asked for {tts.asked['The answer to the order.']} times, not 2")
        return bad


async def v04_a_voice_that_cannot_be_made_is_read() -> list[str]:
    """The voice of a line addressed to the Captain never comes: after its retries the game gets the line as text (a `notice`), the officers' record has it as heard, and
    it never shows as dropped; the line after it is said."""
    async with Bridge() as b:
        tts = b.tts = b.voice.tts = FlakyTTS()
        tts.fail_first = {"The admiral's order, whose voice never comes.": 99, "The answer whose voice never comes either.": 99}
        await b.say("call", "admiral", "The admiral's order, whose voice never comes.", addressed=True)
        await b.say("answer", "helm", "The answer whose voice never comes either.", answer=True)
        await b.say("next", "xo", "The next line, which has a voice.")
        await b.settle(2.0)
        tr = trace_of(b)
        bad = check(tr, b.enq)
        for key in ("call", "answer"):
            lid = b.ids[key]
            if lid not in tr.notices:
                bad.append(f"{key}: the game was not sent the line as a notice ({tr.dropped.get(lid)})")
            elif tr.notices[lid]["text"] not in ("The admiral's order, whose voice never comes.", "The answer whose voice never comes either."):
                bad.append(f"{key}: the notice does not carry the line")
            elif tr.notices[lid]["hold_s"] < 2.0:
                bad.append(f"{key}: the notice is not held long enough to read ({tr.notices[lid]['hold_s']})")
            if lid in tr.begin:
                bad.append(f"{key}: announced as a voice with none")
        if b.ids["next"] not in tr.begin:
            bad.append("the line after them was not said")
        said = [who for _, who, _, _ in b.voice.heard_since(60)]
        if not any("admiral" in w.lower() for w in said):
            bad.append(f"the officers' record of what the Captain has does not have the notice: {said}")
        if b.voice.stats["noticed"] != 2:
            bad.append(f"noticed counter {b.voice.stats['noticed']}")
        return bad


async def v05_a_rethink_that_fails_does_not_lose_them() -> list[str]:
    """A re-think that does not answer in time, or blows up, loses a report (declared) and nothing the Captain is waiting for: the answer and the call are said as they
    stand. A re-think that answers with nothing (the officer's own word: it no longer matters) still withdraws a line: that is not the machine's failure."""
    async with Bridge() as b:
        seen: list[str] = []

        def hook(kind: str):
            async def rethink(text: str, waited: float, cut_after: str) -> str | None:
                seen.append(kind)
                if kind == "slow":
                    await asyncio.sleep(60.0)
                if kind == "boom":
                    raise RuntimeError("the model fell over")
                return None                                                            # ("nothing worth saying now")
            return rethink

        await b.say("busy", "xo", LONG + " " + LONG + " " + LONG)
        await b.say("answer", "helm", "The helm's answer, which waited behind the long speech.", answer=True, rethink=hook("slow"))
        await b.say("call", "admiral", "Fleet command's call, whose re-think blows up.", addressed=True, rethink=hook("boom"))
        await b.say("report", "ops", "A report whose re-think times out.", rethink=hook("slow"))
        await b.say("withdrawn", "tactical", "A report its officer withdraws when asked again.", rethink=hook("none"))
        await b.settle(2.0, limit=500.0)
        tr = trace_of(b)
        bad = check(tr, b.enq)
        for key in ("answer", "call"):
            if b.ids[key] not in tr.begin:
                bad.append(f"{key} was lost ({tr.dropped.get(b.ids[key])})")
        if tr.dropped.get(b.ids["report"]) != "rethink_timeout":
            bad.append(f"the report whose re-think timed out: {tr.dropped.get(b.ids['report'])}")
        if tr.dropped.get(b.ids["withdrawn"]) != "rethought":
            bad.append(f"the officer's own 'not worth saying' should withdraw the line: {tr.dropped.get(b.ids['withdrawn'])}")
        return bad


async def v06_a_call_cut_by_the_captain_is_said_again() -> list[str]:
    """The Captain takes the floor in the middle of a call addressed to him and then speaks again and again: the call is taken up after each answer (as many times as it
    needs, however long it takes), never dropped for its age; a report in the same case is not repeated past its age."""
    async with Bridge() as b:
        await b.say("call", "admiral", "Aquila, Fleet command. " + LONG + " " + LONG, addressed=True)
        await b.say("report", "sensors", "Sensors. " + LONG + " " + LONG)
        await asyncio.sleep(0.5)
        for i in range(4):
            b.voice.captain_begin()
            await asyncio.sleep(0.4)
            b.voice.captain_end(True)
            await b.say(f"answer{i}", "helm", f"Helm. Answer number {i} to what the Captain said.", answer=True)
            await b.settle(0.2)
            await asyncio.sleep(0.3)
        await b.settle(3.0, limit=400.0)
        tr = trace_of(b)
        bad = check(tr, b.enq)
        said = " ".join(tr.spoken_texts())
        if said.count("Aquila, Fleet command.") < 2:
            bad.append("the call was not taken up again after the Captain's turns")
        if tr.dropped and any(r in ("expired", "stale", "overflow") for i, r in tr.dropped.items() if tr.line.get(i, {}).get("speaker") == "admiral"):
            bad.append(f"the call was dropped: {tr.dropped}")
        return bad


async def v07_a_call_is_not_replaced_by_chatter_on_its_topic() -> list[str]:
    """A newer line on the topic of a waiting call replaces it only if it is itself an answer or a call; a report on the same topic is the one dropped."""
    async with Bridge() as b:
        await b.say("busy", "xo", LONG)
        await b.say("call", "admiral", "The call to the Aquila about the Gate.", addressed=True, topic="gate")
        await b.say("report", "sensors", "A report about the Gate, newer than the call.", topic="gate")
        await b.settle(2.0)
        tr = trace_of(b)
        bad = check(tr, b.enq)
        if b.ids["call"] not in tr.begin:
            bad.append("the call was replaced by a report")
        if tr.dropped.get(b.ids["report"]) != "superseded":
            bad.append(f"the report should be the one superseded: {tr.dropped.get(b.ids['report'])}")
        return bad


async def v08_the_line_message_says_it_is_addressed() -> list[str]:
    """The game is told which lines are addressed to the Captain (`line.addressed`), for its subtitles."""
    async with Bridge() as b:
        await b.say("call", "admiral", "A call to the Aquila.", addressed=True)
        await b.say("plain", "sensors", "Just a report.")
        await b.settle(1.0)
        tr = trace_of(b)
        bad = check(tr, b.enq)
        if tr.line[b.ids["call"]].get("addressed") is not True or tr.line[b.ids["plain"]].get("addressed") is not False:
            bad.append(f"line.addressed: {tr.line[b.ids['call']].get('addressed')} / {tr.line[b.ids['plain']].get('addressed')}")
        return bad


SCENARIOS = [v01_the_queue_never_loses_an_answer_or_a_call, v02_an_age_does_not_lose_them, v03_a_voice_that_stumbles_is_asked_again,
             v04_a_voice_that_cannot_be_made_is_read, v05_a_rethink_that_fails_does_not_lose_them, v06_a_call_cut_by_the_captain_is_said_again,
             v07_a_call_is_not_replaced_by_chatter_on_its_topic, v08_the_line_message_says_it_is_addressed]


def main() -> int:
    verbose = "-v" in sys.argv
    only = [a for a in sys.argv[1:] if not a.startswith("-")]
    scenarios = [s for s in SCENARIOS if not only or any(s.__name__.startswith(o) for o in only)]
    failed = 0
    for sc in scenarios:
        try:
            bad = run(sc())
        except Exception:  # noqa: BLE001
            bad = ["crashed:\n" + traceback.format_exc()]
        print(f"{'ok  ' if not bad else 'FAIL'} {sc.__name__:56s} {(sc.__doc__ or '').strip().splitlines()[0][:70]}")
        for m in bad:
            print("       -", m)
        if verbose and LAST:
            for row in timeline(LAST[0].rec):
                print("     |", row)
        failed += bool(bad)
    print(f"\n{len(scenarios) - failed}/{len(scenarios)} scenarios pass")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
