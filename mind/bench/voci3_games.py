"""The user's games of 5 October replayed through the real server, with and without the nets (docs/brief/VOCI-3.md, «Misure»).

    uv run python -m bench.voci3_games [s2 s3] [--to fleet|aquila] [--relay urgent|addressed|all|none] [-v]       (from mind/)
    uv run python -m unittest bench.voci3_games                                                                   (the checks)

What is replayed (bench/data/games_2026-10-05/*.json, made by `bench.games_extract` from the app's logs): every word of the Captain's, at its time, with the crew's answer that really
came (its lines and how long the model took); every line that anybody produced for the bridge's speaker (the crew's reports, the allied captains, Fleet command, the flight and marine
nets, the Mandate's commanders, the Transporter Room's Chief, the people aboard), at the time it was produced and with its words. The lines go in through the real server's own
routes (`Mind._crew_say`, `_ally_say`, `_flight_say`, `_marines_say`, `_rourke_say`, `_say_external`, the Captain's turn worker, the speech floor with its priorities, its re-thinks and its
queue), on a virtual clock and a voice engine that speaks 16 characters a second, as the game's logs show the real one did. Only the models are scripted: the Captain's answer is the
recorded one; a person's re-think of a waiting line keeps it with the probability the logs show for that kind of person (`KEEP`: the crew say the updated line, an allied captain lets
two lines in three go, an answer to the Captain is always kept); the listener of a net (Comms for the fleet, Price for the flight net, the XO for the marines) follows `--relay`:
tells the Captain in one line (a speak) what the sender called urgent (`urgent`, the default), urgent or addressed to him (`addressed`), everything (`all`) or nothing (`none`), and
writes the rest on the console's log. `--to` says what the allied captains' own `to` is for a line that was not an answer or urgent: `fleet` (traffic for the net, what the new `say`
tool asks of them: the default) or `aquila` (the worst case: all of it is meant for the Captain).

What it measures, per session and per way of running it (OLD: ASTRA_NETS=0, every net speaks on the bridge; NEW: the nets as they now are) and as it really was (REAL, from the logs):
the lines the Captain heard (per minute: the mean, and in the busy minutes, those in which the real game said six or more), what he never heard and why (withdrawn by their own
officers' re-think, or lost to the machinery: a full queue, an age, a voice or a re-think that failed), answers to him (the first heard how long after he spoke, any lost), the
admiral's replies heard, and what went to the logs instead. The offline replay shows the plumbing and the routing (what reaches the Captain's ears and what does not, that nothing
addressed to him is lost); what the officers actually choose to tell him, and in how few words, is the models' and is measured on the real ones (bench/voci3_live.py). The text of the
crew's own reports is the recorded one: the doctrine's effect on them is not in these numbers."""
from __future__ import annotations

import asyncio
import difflib
import json
import os
import random
import re
import sys
import unittest
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

os.environ.setdefault("OPENROUTER_API_KEY", "not-a-real-key")             # the client wants one; nothing here ever reaches the network

from astra_mind import models  # noqa: E402
from astra_mind.openrouter import Completion, ToolCall  # noqa: E402

from .games_extract import klass  # noqa: E402
from .voice_floor import FakeTTS, Trace, run  # noqa: E402
from .voice_replay import FakeGame  # noqa: E402

DATA = Path(__file__).resolve().parent / "data" / "games_2026-10-05"
BUSY_LINES_PER_MIN = 6                  # a minute of the real game is busy (a fight) when the bridge said this many lines in it
NET_CLASSES = ("allied", "admiral", "flight", "marines")
LISTENERS = {"fleet": "comms", "flight": "flight", "marine": "xo"}
CONSOLE_OF = {"fleet": "comms", "flight": "flight", "marine": "xo"}
# how likely a person is to still say a line that waited (a re-think that answers with the line, as it stands or updated, against nothing), by what the logs of S2 show: the crew
# always said the updated line (not one crew line was let go by its own officer in 43 minutes), the allied captains let 41 of 74 go, the flight net's people 11 of 19
KEEP = {"crew": 1.0, "allied": 0.30, "flight": 0.50, "marines": 0.50, "admiral": 1.0}
MACHINERY = {"overflow", "expired", "stale", "synth_failed", "synth_timeout", "rethink_timeout", "rethink_failed", "no_audio"}   # what the stage lost on its own (not an officer's word)


def load(name: str) -> dict:
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


# ------------------------------------------------------------------------------------------------ the scripted models
class Models:
    """What stands in for the language models: the recorded answer to the Captain, the listener of a net, the re-think of a line that waited."""

    def __init__(self, case: dict, relay: str, seed: int) -> None:
        self.relay = relay
        self.rng = random.Random(seed)
        self.by_text = {c["text"]: c for c in case["captain"]}
        self.calls: Counter = Counter()
        self.listener_turns = 0
        self.relayed = 0
        self.logged = 0
        self.mind = None

    async def chat(self, *, messages, tools=None, tool_choice="auto", on_tool_call=None, **_kw) -> Completion:  # noqa: ANN001, ANN003
        """The model behind the crew's turns: the recorded answer to the Captain, the listener's turn."""
        comp = Completion(provider="script", model="script")
        last = str(messages[-1].get("content", ""))
        names = {x["function"]["name"] for x in (tools or [])}

        async def call(name: str, args: dict) -> None:
            tc = ToolCall(name=name, arguments_raw=json.dumps(args, ensure_ascii=False))
            comp.tool_calls.append(tc)
            if on_tool_call is not None:
                r = on_tool_call(tc)
                if hasattr(r, "__await__"):
                    await r
        m = re.search(r"\n\nCaptain: (.*?)(?:\n\[|$)", last, re.S)
        if m and "speak" in names:
            c = self.by_text.get(m.group(1).strip())
            reply = (c or {}).get("reply")
            self.calls["captain"] += 1
            if not reply:
                await asyncio.sleep(1.0)
                return comp                                   # (the crew did not answer: the log had no turn for these words)
            await asyncio.sleep(reply["first_s"])
            for k, (who, text) in enumerate(reply["lines"]):
                if k:
                    await asyncio.sleep(0.9)
                await call("speak", {"speaker": who, "text": text, "tone": "focused"})
            return comp
        if "net: traffic on the" in last and "[Ship systems event" in last:
            self.calls["listener"] += 1
            self.listener_turns += 1
            await asyncio.sleep(1.0)
            block = last.split("[Ship systems event, not the Captain speaking] ", 1)[-1]
            block = re.split(r"NET TRAFFIC \(the «net:»|NEWS \(the events above", block, maxsplit=1)[0]          # (the event itself: the ask that follows it talks of [URGENT] and calls too)
            net = re.search(r"net: traffic on the (fleet|flight|marine) net", block).group(1)
            urgent = "[URGENT]" in block
            addressed = "and calls the Captain" in block
            first = re.search(r"«(.*?)»", block, re.S)
            tell = first is not None and (self.relay == "all" or (self.relay in ("urgent", "addressed") and urgent) or (self.relay == "addressed" and addressed))
            if tell:
                self.relayed += 1
                await call("speak", {"speaker": LISTENERS[net], "text": "Capitano, " + first.group(1)[:80], "tone": "focused"})
            else:
                self.logged += 1
                await call("console_log", {"station": CONSOLE_OF[net], "text": (first.group(1) if first else "traffic")[:90]})
            return comp
        return comp                                           # (the warm-up and anything else: nothing is said)

    async def rethink(self, speaker: str, text: str, waited: float, cut_after: str, lang: str) -> str | None:
        """A person thinks again about a line that waited: an answer to the Captain (or a line addressed to him) is always kept; the rest by `KEEP` of their kind."""
        self.calls["rethink"] += 1
        await asyncio.sleep(0.9)
        line = next((l for l in self.mind.voice._queue if l.text == text and l.speaker == speaker), None) if self.mind is not None else None
        if line is not None and line.protected:
            return text
        return text if self.rng.random() < KEEP.get(klass(speaker), 1.0) else None


# ------------------------------------------------------------------------------------------------ one replay
@dataclass
class Result:
    name: str
    mode: str
    minutes: float
    heard: list[dict] = field(default_factory=list)              # the lines the Captain heard: {t, speaker, class, priority, text, id}
    drops: list[dict] = field(default_factory=list)              # the lines the stage dropped: {t, id, speaker, class, prio, protected, reason}
    answers: list[dict] = field(default_factory=list)            # per Captain's word: {t, text, first_s, lines}
    net_traffic: int = 0
    net_traffic_aloud: int = 0
    console_logs: int = 0
    listener_turns: int = 0
    relayed: int = 0
    notices: int = 0
    produced: Counter = field(default_factory=Counter)

    def per_minute(self, only: set[int] | None = None) -> list[int]:
        n = int(self.minutes) + 1
        cnt = [0] * n
        for h in self.heard:
            cnt[min(n - 1, int(h["t"] // 60))] += 1
        return [c for i, c in enumerate(cnt) if only is None or i in only]


class Replay:
    def __init__(self, case: dict, *, nets: bool, relay: str = "urgent", to: str = "fleet", seed: int = 7) -> None:
        self.case = case
        self.nets = nets
        self.to = to
        self.models = Models(case, relay, seed)
        self.game = FakeGame()
        self.mind = None
        self.t0 = 0.0
        self.drops: list[dict] = []

    def now(self) -> float:
        return asyncio.get_running_loop().time() - self.t0

    async def at(self, t: float, make) -> None:  # noqa: ANN001
        await asyncio.sleep(max(0.0, t - self.now()))
        asyncio.ensure_future(make())

    async def play(self) -> Result:
        from astra_mind import server
        from astra_mind.server import Mind
        self.urgent_rx = server._URGENT_EVENT
        ledger = models.LEDGER.write_file
        models.LEDGER.write_file = False
        m = self.mind = Mind()
        self.models.mind = m
        m.lang = "it"
        m.tts = m.voice.tts = FakeTTS()
        m.llm.chat = self.models.chat
        for who in (m.agent, m.war, m.flight, m.marines, m.xfer):
            who.rethink = self.models.rethink
        m.memory.maybe_read = self._nothing
        m.nets.enabled = self.nets
        drop = m.voice._drop

        def noted(line, reason: str) -> None:                     # (the stage's own record of what it lets go, with what kind of line it was)
            self.drops.append({"t": self.now(), "id": line.id, "speaker": line.speaker, "class": klass(line.speaker), "prio": line.prio.name.lower(), "protected": line.protected,
                               "reason": reason})
            drop(line, reason)
        m.voice._drop = noted
        tasks = [asyncio.create_task(m.voice.run()), asyncio.create_task(m.turn_worker()), asyncio.create_task(m.handle_client(self.game))]
        try:
            await asyncio.sleep(0.1)
            self.game.push({"type": "hello"})
            self.game.push({"type": "ship_state", "state": m.local.snapshot()})
            await asyncio.sleep(0.1)
            self.t0 = asyncio.get_running_loop().time()
            jobs = []
            for c in self.case["captain"]:
                lead = 1.5 if c["how"] == "voice" else 0.0         # (the key goes down this long before his words are recognised)
                jobs.append(asyncio.ensure_future(self.at(max(0.0, c["t"] - lead), lambda c=c: self.captain(c))))
            for p in self.case["producers"]:
                if p["kind"] != "answer":
                    jobs.append(asyncio.ensure_future(self.at(p["t"], lambda p=p: self.produce(p))))
            await asyncio.gather(*jobs)
            await self.settle(self.case["duration_s"])
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            models.LEDGER.write_file = ledger
        return self.result()

    @staticmethod
    async def _nothing(*_a, **_k) -> None:  # noqa: ANN002, ANN003
        return None

    async def settle(self, until: float, limit: float = 900.0) -> None:
        m = self.mind
        await asyncio.sleep(max(0.0, until - self.now()))
        t1 = self.now()
        while (m.voice._queue or m.voice._cur is not None or not m.turns.empty() or m.agent.busy()) and self.now() - t1 < limit:
            await asyncio.sleep(0.2)
        await asyncio.sleep(20.0)

    # ------------------------------------------------------------------------------------------ the game's side
    async def captain(self, c: dict) -> None:
        """A word of the Captain's: typed (the game sends it as text) or spoken (the key goes down: whoever talks stops; the recognised words arrive as a turn 1.5 s later)."""
        m = self.mind
        if c["how"] == "typed":
            self.game.push({"type": "player_text", "text": c["text"], "lang": c["lang"]})
            return
        m.voice.captain_begin()
        m._captain_speaks()
        await asyncio.sleep(1.4)
        m.voice.captain_end(None)
        await asyncio.sleep(0.1)
        m.captain_t = asyncio.get_running_loop().time()
        await m.turns.put((c["text"], c["lang"], None))

    def _urgent_before(self, t: float) -> bool:
        return any(e["report"] and t - 30.0 <= e["t"] <= t and self.urgent_rx.search(e["text"]) for e in self.case["events"])

    async def produce(self, p: dict) -> None:
        """A line somebody produced for the bridge: by the route the server gives that kind of voice."""
        m = self.mind
        who, text, kind = p["speaker"], p["text"], p["kind"]
        cls = klass(who)
        loop_t = asyncio.get_running_loop().time()
        if kind == "report" or cls == "crew":
            m.voice.low_priority = True
            m.voice.report_since = loop_t - 0.2
            if self._urgent_before(p["t"]):
                m.voice.urgent = True
            await m._crew_say(who, text, "it", "focused")
        elif cls == "allied":
            urgent = bool(p.get("urgent"))
            answer = bool(p.get("answer"))
            to = "aquila" if (answer or urgent or self.to == "aquila") else "fleet"
            await m._ally_say(who, text, "it", "calm", urgent=urgent, answer=answer, to=to)
        elif cls == "admiral" and kind == "net":
            await m._rourke_say(who, text, "it", "measured", answer=bool(p.get("answer")))
        elif cls == "flight":
            await m._flight_say(who, text, "it", "calm", urgent=bool(p.get("urgent")), answer=bool(p.get("answer")))
        elif cls == "marines":
            await m._marines_say(who, text, "it", "calm", urgent=bool(p.get("urgent")), answer=bool(p.get("answer")))
        elif cls == "xfer":
            await m._xfer_say(who, text, "it", "calm", priority_urgent=bool(p.get("urgent")), answer=bool(p.get("answer")))
        elif cls == "person":
            await m.voice.say(who, text, "it", "calm", answer=True)
        else:                                                    # a Mandate commander on the channel, Fleet command's own calls, the story's voices: said TO the Captain
            await m._say_external(who, text, "it", "cold")

    # ------------------------------------------------------------------------------------------ what happened
    def result(self) -> Result:
        case = self.case
        tr = Trace.of(self.game.rec)
        res = Result(case["session"], "NEW" if self.nets else "OLD", case["duration_s"] / 60.0)
        for p in case["producers"]:
            if p["kind"] != "answer":
                res.produced[klass(p["speaker"])] += 1
        for t, kind, p in self.game.rec.events:
            if kind != "json":
                continue
            ty = p.get("type")
            if ty == "notice":
                res.notices += 1
            elif ty == "net_traffic":
                res.net_traffic += 1
                res.net_traffic_aloud += 1 if p.get("aloud") else 0
            elif ty == "console_log":
                res.console_logs += 1
        for i in tr.order():
            line = tr.line[i]
            res.heard.append({"t": tr.begin[i], "speaker": line["speaker"], "class": klass(line["speaker"]), "priority": line["priority"], "text": line["text"], "id": i,
                              "addressed": bool(line.get("addressed"))})
        res.drops = self.drops
        said = sorted(h["t"] for h in res.heard if h["priority"] == "answer")
        for c in case["captain"]:
            nxt = next((t for t in said if t >= c["t"] - 0.5), None)
            expect = len(c["reply"]["lines"]) if c.get("reply") else 0
            res.answers.append({"t": c["t"], "text": c["text"], "first_s": (nxt - c["t"]) if (nxt is not None and expect and nxt - c["t"] < 30.0) else None, "lines": expect})
        res.listener_turns, res.relayed = self.models.listener_turns, self.models.relayed
        return res


# ------------------------------------------------------------------------------------------------ the real game, for comparison
def real(case: dict) -> Result:
    res = Result(case["session"], "REAL", case["duration_s"] / 60.0)
    for s in case["recorded"]["spoken"]:
        res.heard.append({"t": s["t"], "speaker": s["speaker"], "class": klass(s["speaker"]), "priority": "?", "text": s["text"], "id": 0, "addressed": False})
    for d in case["recorded"]["dropped"]:
        res.drops.append({"t": d["t"], "id": d["id"], "speaker": d["speaker"], "class": klass(d["speaker"]), "prio": d["prio"], "protected": d["prio"] == "answer", "reason": d["reason"]})
    for c in case["captain"]:
        res.answers.append({"t": c["t"], "text": c["text"], "first_s": (c["reply"]["first_s"] if c.get("reply") else None), "lines": len(c["reply"]["lines"]) if c.get("reply") else 0})
    return res


def busy_minutes(case: dict) -> set[int]:
    cnt = Counter(int(s["t"] // 60) for s in case["recorded"]["spoken"])
    return {m for m, n in cnt.items() if n >= BUSY_LINES_PER_MIN}


def repetitions(res: Result, window_s: float = 60.0, ratio: float = 0.72) -> int:
    """Lines the Captain heard that nearly repeat one he heard in the last minute (the text's similarity: a proxy for the ear)."""
    n = 0
    hs = sorted(res.heard, key=lambda h: h["t"])
    for i, h in enumerate(hs):
        words = h["text"].lower().split()
        for g in reversed(hs[:i]):
            if h["t"] - g["t"] > window_s:
                break
            if difflib.SequenceMatcher(None, words, g["text"].lower().split()).ratio() >= ratio:
                n += 1
                break
    return n


def percentile(xs: list[float], p: float) -> float:
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))] if xs else float("nan")


def summarize(case: dict, res: Result) -> dict:
    busy = busy_minutes(case)
    pm = res.per_minute()
    pb = res.per_minute(busy) if busy else []
    firsts = [a["first_s"] for a in res.answers if a["first_s"] is not None]
    by_class = Counter(h["class"] for h in res.heard)
    lost = [d for d in res.drops if d["reason"] in MACHINERY]
    return {"mode": res.mode, "heard": len(res.heard), "per_min": len(res.heard) / max(res.minutes, 1.0), "busy_per_min": (sum(pb) / len(pb)) if pb else float("nan"),
            "peak": max(pm) if pm else 0, "withdrawn": sum(1 for d in res.drops if d["reason"] == "rethought"), "lost": len(lost), "lost_protected": sum(1 for d in lost if d["protected"]),
            "lost_by_class": dict(Counter(d["class"] for d in lost)), "net_at_speaker": sum(by_class[c] for c in NET_CLASSES), "crew_at_speaker": by_class["crew"],
            "other_at_speaker": len(res.heard) - sum(by_class[c] for c in NET_CLASSES) - by_class["crew"], "first_median": percentile(firsts, 0.5), "first_p90": percentile(firsts, 0.9),
            "answered": len(firsts), "net_logged": res.net_traffic - res.net_traffic_aloud, "console_logs": res.console_logs, "listener_turns": res.listener_turns,
            "relayed": res.relayed, "repeats": repetitions(res), "notices": res.notices, "admiral_heard": by_class["admiral"], "busy_minutes": len(busy),
            "reasons": dict(Counter(d["reason"].split("_into_")[0] for d in res.drops))}


def run_session(name: str, **kw) -> tuple[dict, Result]:
    case = load(name)
    return case, run(Replay(case, **kw).play())


def report(name: str, to: str, relay: str) -> list[dict]:
    case = load(name)
    rows = [summarize(case, real(case))]
    for nets in (False, True):
        case_, res = run_session(name, nets=nets, to=to, relay=relay)
        rows.append(summarize(case_, res))
    rows[0]["mode"], rows[1]["mode"], rows[2]["mode"] = "REAL (the logs)", "OLD (nets on speaker)", f"NEW to={to} relay={relay}"
    print(f"\n== {name}: {case['duration_s'] / 60:.1f} min, {len(case['captain'])} Captain's words, {sum(1 for p in case['producers'] if p['kind'] != 'answer') + sum(len(c['reply']['lines']) for c in case['captain'] if c.get('reply'))} lines produced for "
          f"the bridge; {rows[0]['busy_minutes']} busy minutes in the real game (>= {BUSY_LINES_PER_MIN} lines said)")
    cols = [("said", "heard"), ("/min", "per_min"), ("busy/min", "busy_per_min"), ("peak", "peak"), ("nets", "net_at_speaker"), ("crew", "crew_at_speaker"), ("others", "other_at_speaker"),
            ("withdrawn", "withdrawn"), ("lost", "lost"), ("lost ans", "lost_protected"), ("1st med", "first_median"), ("1st p90", "first_p90"), ("repeats", "repeats"),
            ("on logs", "net_logged"), ("console", "console_logs"), ("listener", "listener_turns"), ("told", "relayed")]
    print(f"{'':23s}" + "".join(f"{c[0]:>10s}" for c in cols))
    for r in rows:
        print(f"{r['mode']:23s}" + "".join((f"{r[k]:10.1f}" if isinstance(r.get(k), float) else f"{r.get(k)!s:>10}") for _, k in cols))
    for r in rows:
        print(f"   {r['mode'].split()[0]:5s} lost by class {r['lost_by_class']}, drops by reason {r['reasons']}")
    return rows


def main() -> int:
    argv = sys.argv[1:]
    opt = {a: argv[i + 1] for i, a in enumerate(argv) if a in ("--to", "--relay") and i + 1 < len(argv)}
    names = [a for a in argv if re.fullmatch(r"s\d", a)] or ["s2", "s3"]
    for n in names:
        report(n, opt.get("--to", "fleet"), opt.get("--relay", "urgent"))
    return 0


# ------------------------------------------------------------------------------------------------ checks
class TestGamesReplay(unittest.TestCase):
    """The plumbing, on the real games: with the nets, nothing addressed to the Captain is lost, the nets no longer fill the bridge, and the answers come as fast as the model's."""

    runs: dict = {}

    @classmethod
    def setUpClass(cls) -> None:
        for name in ("s2", "s3"):
            case, new = run_session(name, nets=True, to="fleet", relay="urgent")
            _, old = run_session(name, nets=False, to="fleet", relay="urgent")
            cls.runs[name] = (case, old, new)

    def test_nothing_addressed_to_the_captain_is_lost(self) -> None:
        for name, (case, old, new) in self.runs.items():
            self.assertEqual([d for d in new.drops if d["protected"] and d["reason"] in MACHINERY], [], name)
            self.assertEqual([d for d in old.drops if d["protected"] and d["reason"] in MACHINERY], [], name)

    def test_the_nets_no_longer_fill_the_bridge(self) -> None:
        for name, (case, old, new) in self.runs.items():
            so, sn = summarize(case, old), summarize(case, new)
            self.assertLess(sn["net_at_speaker"], so["net_at_speaker"] * 0.6, f"{name}: {sn['net_at_speaker']} net lines said against {so['net_at_speaker']}")
            self.assertLessEqual(sn["lost"], so["lost"], name)
            self.assertGreater(sn["net_logged"], 0, name)

    def test_what_reaches_the_speaker_from_a_net_is_the_captains_own(self) -> None:
        """Every net line that was said was an answer to him, a call to him in the sender's voice, or sent urgent (and told by its listener, an officer's line)."""
        for name, (case, old, new) in self.runs.items():
            own = {p["text"][:40] for p in case["producers"] if p["kind"] in ("net", "other") and (p.get("answer") or p["speaker"] == "admiral" or p.get("urgent"))}
            for h in new.heard:
                if h["class"] in NET_CLASSES:
                    self.assertTrue(h["priority"] in ("answer", "urgent") or h["text"][:40] in own, f"{name}: {h}")

    def test_the_admirals_replies_are_heard(self) -> None:
        for name, (case, old, new) in self.runs.items():
            replies = [p for p in case["producers"] if p["speaker"] == "admiral" and p.get("answer")]
            heard = [h for h in new.heard if h["speaker"] == "admiral" and h["priority"] == "answer"]
            self.assertEqual(len(heard), len(replies), name)

    def test_the_first_answer_comes_as_fast_as_the_model_gives_it(self) -> None:
        for name, (case, old, new) in self.runs.items():
            s = summarize(case, new)
            self.assertLess(s["first_median"], 2.0, name)
            self.assertLess(s["first_p90"], 3.5, name)


if __name__ == "__main__":
    sys.exit(main())
