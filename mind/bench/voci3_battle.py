"""A slice of a real battle through the real server and the real crew model: who speaks, how often, how long, and what goes on the log instead.

    (OPENROUTER_API_KEY in the environment)   cd mind && python -m bench.voci3_battle [s3] [--from 400 --to 640] [--cap 0.10] [-v] [--out file.json]

The 5 October games (bench/data/games_2026-10-05, made by `bench.games_extract` from the app's logs) are replayed in REAL time through `Mind` itself: every news item the
game reported (`event`, `report: true`) arrives at its time, every word of the Captain's that the crew answered at the time he said it (as a typed order), the turn worker, the
crew's agent with its prompts and tools, the speech floor and its voice (a fake engine that speaks 16 characters a second) run as in the game. Only the ship is a stand-in: the local
fight (a Mandate destroyer closing, another circling), a static state: the events talk about the 5 October ships, so what the officers say about ranges and names is not to be
read as judgement; what is measured is the TALK: how many lines the Captain hears a minute, from whom, how long they are, how often a line repeats one of the last minute, what the
officers write on the consoles' logs instead (`console_log`), and how long the first answer to the Captain takes. The same file runs on an older checkout (the merge base of VOCI-3)
to compare: nothing here needs the nets or the logs (they are counted when they exist).

Real spend: a few cents for a few minutes of battle (the cap stops the run; the ledger is this checkout's `mind/.cache/spend.jsonl`)."""
from __future__ import annotations

import argparse
import asyncio
import difflib
import json
import os
import re
import sys
import time
from collections import Counter

os.environ.setdefault("ASTRA_TTS_WARM", "0")

from astra_mind import models  # noqa: E402

from .games_extract import klass  # noqa: E402
from .voice_floor import FakeTTS, Trace  # noqa: E402
from .voice_replay import FakeGame  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "games_2026-10-05")
CREW = ("xo", "helm", "ops", "tactical", "comms", "sensors", "engineering", "flight", "chief", "doctor")


def load(name: str) -> dict:
    with open(os.path.join(DATA, f"{name}.json"), encoding="utf-8") as f:
        return json.load(f)


def words(text: str) -> int:
    return len(text.split())


def similar(a: str, b: str, ratio: float = 0.72) -> bool:
    return difflib.SequenceMatcher(None, a.lower().split(), b.lower().split()).ratio() >= ratio


class LiveGame(FakeGame):
    """The game as the crew's tools see it: every command is carried out (the ship is a stand-in, so nothing changes on the boards)."""

    async def send(self, data) -> None:  # noqa: ANN001
        await super().send(data)
        if isinstance(data, str):
            msg = json.loads(data)
            if msg.get("type") == "command":
                self.push({"type": "command_result", "id": msg["id"], "ok": True, "detail": f"{msg.get('name')} carried out"})


class Slice:
    """One run of a window of a recorded game through the real server."""

    def __init__(self, case: dict, t0: float, t1: float, lang: str = "it") -> None:
        self.case, self.t0, self.t1, self.lang = case, t0, t1, lang
        self.game = LiveGame()
        self.mind = None
        self.cost0 = models.LEDGER.total
        self.calls0 = models.LEDGER.calls
        self.words_of_captain: list[dict] = []
        self.events: list[dict] = []

    def plan(self) -> list[tuple[float, str, dict]]:
        out: list[tuple[float, str, dict]] = []
        for e in self.case["events"]:
            if self.t0 <= e["t"] <= self.t1:
                out.append((e["t"], "event", {"type": "event", "text": e["text"], "report": bool(e.get("report"))}))
                self.events.append(e)
        for c in self.case["captain"]:
            if self.t0 <= c["t"] <= self.t1 and c.get("reply"):                      # (the words the crew answered in the real game: orders and questions for the bridge)
                out.append((c["t"], "captain", {"type": "player_text", "text": c["text"], "lang": c.get("lang") or self.lang}))
                self.words_of_captain.append(c)
        return sorted(out, key=lambda x: x[0])

    async def play(self) -> None:
        from astra_mind.local_ship import LocalShip
        from astra_mind.server import Mind
        m = self.mind = Mind()
        m.lang = self.lang
        m.tts = m.voice.tts = FakeTTS()
        m.local = LocalShip(stations=True, fight=True)

        async def nothing(*_a, **_k) -> None:  # noqa: ANN002, ANN003
            return None
        m.memory.maybe_read = nothing
        tasks = [asyncio.create_task(m.voice.run()), asyncio.create_task(m.turn_worker()), asyncio.create_task(m.handle_client(self.game))]
        try:
            self.game.push({"type": "hello"})
            self.game.push({"type": "ship_state", "state": m.local.snapshot()})
            await asyncio.sleep(2.5)                                                  # (the warm-up of the route)
            loop = asyncio.get_running_loop()
            self.t_start = loop.time()
            self.sent_at: dict[str, float] = {}
            for t, kind, msg in self.plan():
                await asyncio.sleep(max(0.0, self.t_start + (t - self.t0) - loop.time()))
                if kind == "captain":
                    self.sent_at[msg["text"]] = loop.time() - self.t_start
                self.game.push(msg)
            await asyncio.sleep(1.0)
            t1 = loop.time()
            while (m.voice._queue or m.voice._cur is not None or not m.turns.empty() or m.agent.busy() or m.voice.held) and loop.time() - t1 < 90.0:
                await asyncio.sleep(0.3)
            await asyncio.sleep(3.0)
        finally:
            self.game.inbox.put_nowait(None)
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    # ------------------------------------------------------------------------------------------ what happened
    def report(self, verbose: bool = False) -> dict:
        tr = Trace.of(self.game.rec)
        minutes = max(1e-9, (self.t1 - self.t0) / 60.0)
        said = []
        for i in tr.order():
            line = tr.line[i]
            said.append({"t": round(tr.begin[i] - self.t_start, 1), "who": line["speaker"], "prio": line["priority"], "text": line["text"], "words": words(line["text"]),
                         "addressed": bool(line.get("addressed"))})
        logs = [dict(p) for _, k, p in self.game.rec.events if k == "json" and p.get("type") == "console_log"]
        drops = Counter(str(r).split("_into_")[0] for r in tr.dropped.values())
        crew = [s for s in said if s["who"] in CREW]
        reports = [s for s in crew if s["prio"] != "answer"]
        answers = [s for s in crew if s["prio"] == "answer"]
        by_who = Counter(s["who"] for s in crew)
        repeats = 0
        for k, s in enumerate(crew):
            for g in reversed(crew[:k]):
                if s["t"] - g["t"] > 60.0:
                    break
                if similar(s["text"], g["text"]):
                    repeats += 1
                    break
        firsts = []
        for c in self.words_of_captain:
            t = self.sent_at.get(c["text"])
            nxt = next((s["t"] for s in answers if t is not None and s["t"] >= t), None)
            if t is not None and nxt is not None and nxt - t < 30.0:
                firsts.append(nxt - t)
        firsts.sort()
        out = {"window_s": [self.t0, self.t1], "captain_words": len(self.words_of_captain), "report_events": sum(1 for e in self.events if e.get("report")),
               "lines": len(said), "lines_per_min": round(len(said) / minutes, 2), "crew_lines": len(crew), "reports": len(reports), "answers": len(answers),
               "answers_per_word": round(len(answers) / max(1, len(self.words_of_captain)), 2), "words_per_line": round(sum(s["words"] for s in said) / max(1, len(said)), 1),
               "long_lines": sum(1 for s in said if s["words"] > 22), "xo_share_of_reports": round(sum(1 for s in reports if s["who"] == "xo") / max(1, len(reports)), 2),
               "by_speaker": dict(by_who.most_common()), "console_logs": len(logs), "log_by_console": dict(Counter(p.get("station") for p in logs)), "repeats": repeats,
               "first_answer_s": round(firsts[len(firsts) // 2], 2) if firsts else None, "dropped": dict(drops), "model_calls": models.LEDGER.calls - self.calls0,
               "spend_usd": round(models.LEDGER.total - self.cost0, 5)}
        if verbose:
            print("\n".join(f"  {s['t']:6.1f} {s['prio'][:3]:3s} {s['who']:11s} {s['words']:2d}w  {s['text']}" for s in said))
            for p in logs:
                print(f"  (log) {p.get('station')}: {p.get('text')}")
        out["said"] = said
        out["logs"] = [{"station": p.get("station"), "text": p.get("text")} for p in logs]
        return out


async def main_async(args: argparse.Namespace) -> int:
    case = load(args.session)
    t0 = args.t_from if args.t_from is not None else 0.0
    t1 = args.t_to if args.t_to is not None else min(case["duration_s"], t0 + 240.0)
    s = Slice(case, t0, t1)
    t_wall = time.perf_counter()
    try:
        await s.play()
    except models.SpendCapReached as exc:
        print(f"STOPPED: {exc}")
    rep = s.report(verbose=args.verbose)
    brief = {k: v for k, v in rep.items() if k not in ("said", "logs")}
    print(f"\n== {args.session} {t0:.0f}-{t1:.0f} s ({(t1 - t0) / 60:.1f} min), {time.perf_counter() - t_wall:.0f} s of wall clock")
    for k, v in brief.items():
        print(f"   {k:22s} {v}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("session", nargs="?", default="s3")
    ap.add_argument("--from", dest="t_from", type=float, default=None)
    ap.add_argument("--to", dest="t_to", type=float, default=None)
    ap.add_argument("--cap", type=float, default=0.12)
    ap.add_argument("--out", default="")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()
    models.LEDGER.cap = args.cap
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
