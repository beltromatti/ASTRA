"""The user's real games of 5 October 2026 (00:16-01:26), turned into replayable cases.

    uv run python -m bench.games_extract [--mind LOG] [--game LOG ...] [--out DIR]       (from mind/)

Sources (read only): the mind's log (`~/Library/Application Support/Epic/ASTRA/Saved/Logs/astra-mind.log`, from the line that starts «2026-10-05 00:16:30») and the game's own logs
(`~/Library/Logs/ASTRA/ASTRA-backup-2026.10.04-22.19.38.log`, `...23.02.37.log`, `...23.26.11.log`: UTC; the mind's log is local time, UTC+2). What they hold, session by session
(S1 a resumed campaign, S2 and S3 two new ones):

  captain     every word of the Captain's: the STT lines («STT 0.09s after the key (...) [it] text») and the typed ones («the Captain types: text»), with how long the first line of the
              crew's answer took and what it said (the `turn` line);
  producers   every line anybody produced for the bridge's speaker, with the time it was produced (the end of the pulse or turn that made it, from the mind's log) and its text (from
              what the game heard, or from the mind's «not spoken» record when it never was): the crew's reports and answers, the allied captains, Fleet command, the flight net, the
              marine net, the Mandate's commanders, the Transporter Room's Chief, the people aboard;
  events      the game's `[Event]` lines the mind was given (with their `report` flag);
  recorded    what really happened to them: heard (when its voice began) or never said (and why).

The cases are written as JSON to bench/data/games_2026-10-05/ and replayed through the real server by `bench.voci3_games`. The extraction is mechanical bookkeeping: a pulse that
said N lines is paired, in order, with the first N lines of its class that the record has seen no earlier; the lines no pulse explains are produced where they were first heard."""
from __future__ import annotations

import argparse
import datetime as dt
import difflib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

HOME = Path.home()
MIND_LOG = HOME / "Library/Application Support/Epic/ASTRA/Saved/Logs/astra-mind.log"
GAME_LOGS = sorted((HOME / "Library/Logs/ASTRA").glob("ASTRA*.log"))      # (the game rotates its log at each start: S1-S3 are the «backup» files of 22.19.38, 23.02.37 and 23.26.11 UTC)
OUT = Path(__file__).resolve().parent / "data" / "games_2026-10-05"
START = "2026-10-05 00:16:30"
UTC_TO_LOCAL = dt.timedelta(hours=2)

CREW_KEYS = {"xo", "helm", "ops", "tactical", "comms", "sensors", "engineering", "flight", "chief", "doctor"}
FLIGHT_KEYS = {"cag", "alpha_lead", "alpha_2", "alpha_3", "bravo_lead", "bravo_2", "deck_chief"}
ENEMY_KEYS = ("cmdr_", "solm", "kade", "vael", "quill", "hale", "thale", "dorn", "morrow")

_MIND = re.compile(r"^(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d),(\d{3}) (\S+) (.*)$")
_GAME = re.compile(r"^\[(\d{4})\.(\d\d)\.(\d\d)-(\d\d)\.(\d\d)\.(\d\d):(\d{3})\]\[\s*\d+\]LogASTRA: (.*)$")


def klass(key: str) -> str:
    """Who a speaker id belongs to: the bridge's crew, the people aboard, the Transporter Room's Chief, Fleet command, the flight net, the marine net, the Mandate's commanders, or
    an allied captain (anything else: the 7th Fleet's captains have ids of their own: castellan, okoro, aldana, ally_t44...)."""
    if key in CREW_KEYS:
        return "crew"
    if key.startswith(("npc", "patient", "mess")):
        return "person"
    if key == "xfer_chief":
        return "xfer"
    if key in ("admiral", "director"):
        return "admiral"
    if key in FLIGHT_KEYS:
        return "flight"
    if key.startswith("marine") or key == "reyes":
        return "marines"
    if key.startswith(ENEMY_KEYS):
        return "enemy"
    return "allied"


def _t(s: str, ms: str) -> dt.datetime:
    return dt.datetime.strptime(s, "%Y-%m-%d %H:%M:%S") + dt.timedelta(milliseconds=int(ms))


def read_mind(path: Path) -> list[tuple[dt.datetime, str, str]]:
    rows: list[tuple[dt.datetime, str, str]] = []
    started = False
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not started:
            started = line.startswith(START)
            if not started:
                continue
        m = _MIND.match(line)
        if m:
            rows.append((_t(m.group(1), m.group(2)), m.group(3), m.group(4)))
    return rows


def read_game(paths: list[Path]) -> list[tuple[dt.datetime, str]]:
    rows: list[tuple[dt.datetime, str]] = []
    for p in paths:
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8", errors="replace").splitlines():
            m = _GAME.match(line)
            if m:
                y, mo, d, h, mi, s, ms = (int(x) for x in m.groups()[:7])
                rows.append((dt.datetime(y, mo, d, h, mi, s, ms * 1000) + UTC_TO_LOCAL, m.group(8)))
    rows.sort(key=lambda r: r[0])
    return rows


def split_lines(joined: str) -> list[tuple[str, str]]:
    """«xo: text | helm: text» -> [(xo, text), (helm, text)] (the log joins a turn's lines with ' | ')."""
    out: list[tuple[str, str]] = []
    for part in joined.split(" | "):
        who, sep, text = part.partition(": ")
        if sep and re.fullmatch(r"[a-z_0-9]+", who):
            out.append((who, text.strip()))
        elif out:
            out[-1] = (out[-1][0], out[-1][1] + " | " + part)
    return out


def sessions(rows: list[tuple[dt.datetime, str, str]]) -> list[tuple[str, dt.datetime, dt.datetime]]:
    """(name, first connected, disconnected) of each game session in the mind's log."""
    out, begin = [], None
    for t, lg, msg in rows:
        if lg == "astra.mind" and msg == "game connected":
            begin = t
        elif lg == "astra.mind" and msg == "game disconnected" and begin is not None:
            out.append((f"s{len(out) + 1}", begin, t))
            begin = None
    return out


# ------------------------------------------------------------------------------------------------ one session
def extract(name: str, t0: dt.datetime, t1: dt.datetime, mind: list[tuple[dt.datetime, str, str]], game: list[tuple[dt.datetime, str]]) -> dict:
    def rel(t: dt.datetime) -> float:
        return round((t - t0).total_seconds(), 2)

    mrows = [(t, lg, msg) for t, lg, msg in mind if t0 <= t <= t1]
    grows = [(t, msg) for t, msg in game if t0 - dt.timedelta(seconds=1) <= t <= t1]
    # --- what the game heard
    spoken: list[dict] = []
    for t, msg in grows:
        m = re.match(r"\[Crew\] ([a-z_0-9]+): (.*)", msg)
        if m:
            spoken.append({"t": rel(t), "speaker": m.group(1), "text": m.group(2)})
    # --- what the stage dropped, and what was thought again
    dropped: list[dict] = []
    rethought: list[dict] = []
    for t, lg, msg in mrows:
        m = re.match(r"line (\d+) \(([a-z_0-9]+), (answer|urgent|normal|low)\) not spoken: ([a-z_0-9]+) — (.*)", msg)
        if lg == "astra.speech" and m:
            dropped.append({"t": rel(t), "id": int(m.group(1)), "speaker": m.group(2), "prio": m.group(3), "reason": m.group(4), "text": m.group(5)})
        m = re.match(r"line (\d+) \(([a-z_0-9]+)\) thought again after (\d+) s: (.*)", msg)
        if lg == "astra.speech" and m and "not worth saying" not in m.group(4):
            rethought.append({"t": rel(t), "id": int(m.group(1)), "speaker": m.group(2), "waited_s": int(m.group(3))})
    # --- the Captain
    captain: list[dict] = []
    for t, lg, msg in mrows:
        m = re.match(r"STT ([\d.]+)s after the key .*?\[(\w+)\] (.*)", msg)
        if lg == "astra.mind" and m:
            if m.group(3).strip():
                captain.append({"t": rel(t), "text": m.group(3).strip(), "lang": m.group(2), "how": "voice"})
            continue
        m = re.match(r"the Captain types: (.*)", msg)
        if lg == "astra.mind" and m:
            captain.append({"t": rel(t), "text": m.group(1).strip(), "lang": "it", "how": "typed"})
    # --- the producers whose words the log has whole: the crew's turns, the people aboard, the Mandate's commanders on the channel, the Transporter Room's Chief
    prod: list[dict] = []
    turns: list[dict] = []
    for t, lg, msg in mrows:
        m = re.match(r"turn ([\d.]+)s \(first line ([\d.]+)s\) cost \$[\d.]+: (.*)", msg)
        if lg == "astra.mind" and m:
            total, first = float(m.group(1)), float(m.group(2))
            lines = split_lines(m.group(3))
            turns.append({"end": rel(t), "total_s": total, "first_s": first, "lines": lines})
            for k, (who, text) in enumerate(lines):
                prod.append({"t": round(max(0.0, rel(t) - total + first + k * 0.9), 2), "kind": "answer", "speaker": who, "text": text, "urgent": False})
            continue
        m = re.match(r"event turn ([\d.]+)s: (.*)", msg)
        if lg == "astra.mind" and m and m.group(2) != "(no report)":
            for k, (who, text) in enumerate(split_lines(m.group(2))):
                prod.append({"t": round(max(0.0, rel(t) - 0.25 + k * 0.5), 2), "kind": "report", "speaker": who, "text": text, "urgent": False})
            continue
        m = re.match(r"crew answer ([\d.]+)s .*?: (.*)", msg)
        if lg == "astra.npc" and m and not m.group(2).startswith("("):
            for k, (who, text) in enumerate(split_lines(m.group(2))):
                prod.append({"t": round(rel(t) - 0.2 + k * 0.4, 2), "kind": "person", "speaker": who, "text": text, "answer": True})
            continue
        m = re.match(r"(.+?) ([\d.]+)s: (.*)", msg)
        if lg == "astra.enemy" and m:
            prod.append({"t": round(rel(t) - 0.2, 2), "kind": "enemy", "speaker": "_enemy", "name": m.group(1), "text": m.group(3), "answer": False})
            continue
        m = re.match(r"the Chief \((\w+)\) ([\d.]+)s \$[\d.]+: (.*)", msg)
        if lg == "astra.transporter" and m:
            for part in m.group(3).split(" | "):
                if part.startswith("say: "):
                    prod.append({"t": round(rel(t) - 0.2, 2), "kind": "xfer", "speaker": "xfer_chief", "text": part[5:].strip(), "answer": m.group(1) in ("order", "captain")})
            continue
    # --- everybody else: the nets' people, Fleet command, the Mandate's commanders. A pulse that said N lines (its end is when the lines were produced) is paired, in order,
    # with the first N lines of its class the record has that were seen no earlier (heard, or never said); the texts and who spoke them come from the record
    pool: list[dict] = []                                           # every line of the record that is not the crew's: oldest first
    for s_ in spoken:
        pool.append({"key": s_["speaker"], "seen": s_["t"], "text": s_["text"], "prio": None, "dropped": None, "used": False})
    for d in dropped:
        if not d["reason"].startswith("merged_into"):
            pool.append({"key": d["speaker"], "seen": d["t"], "text": d["text"], "prio": d["prio"], "dropped": d["reason"], "used": False})
    pool = [l for l in pool if klass(l["key"]) != "crew"]
    pool.sort(key=lambda x: x["seen"])

    def take(cls: str, after: float, near_text: str = "") -> dict | None:
        """The first unused line of a class seen no earlier than `after` (or, with a text, the most similar within a few minutes)."""
        if near_text:
            best, hit = 0.0, None
            for l in pool:
                if l["used"] or klass(l["key"]) != cls or not (after - 2.0 <= l["seen"] <= after + 150.0):
                    continue
                r = difflib.SequenceMatcher(None, near_text[:70].lower(), l["text"][:70].lower()).ratio()
                if r > best:
                    best, hit = r, l
            if hit is not None and best >= 0.5:
                hit["used"] = True
                return hit
            return None
        for l in pool:
            if not l["used"] and klass(l["key"]) == cls and l["seen"] >= after - 2.0:
                l["used"] = True
                return l
        return None

    for p in prod:                                                  # (the people whose words the log has whole: who spoke them is looked up in the record)
        if p["kind"] in ("person", "xfer", "enemy"):
            l = take(p["kind"], p["t"], p["text"])
            if l is not None:
                p["speaker"] = l["key"]
                p["urgent"] = l["prio"] == "urgent"
            elif p["speaker"] == "_enemy":
                p["speaker"] = "cmdr_unknown"
    pulses: list[tuple[str, dict]] = []                             # (class, pulse)
    for t, lg, msg in mrows:
        if lg == "astra.war_minds":
            m = re.match(r"(.+?) ([\d.]+)s \$[\d.]+ \((.*?)\): (.*)", msg)
            if m:
                for x in m.group(4).split(" | "):
                    if x in ("say", "transmit"):
                        pulses.append(("allied" if x == "say" else "enemy", {"t": rel(t), "answer": "a word for you" in m.group(3), "via": x}))
        elif lg == "astra.strategy":
            m = re.match(r"(.+?) ([\d.]+)s \$[\d.]+ \((.*?)\): (.*)", msg)
            if m and "Rourke" in m.group(1):
                for x in m.group(4).split(" | "):
                    if x.endswith("tell_captain"):
                        pulses.append(("admiral", {"t": rel(t), "answer": "spoke to Fleet command" in m.group(3), "via": "tell_captain"}))
        elif lg in ("astra.flight", "astra.marines"):
            m = re.match(r"(?:flight|marine) net ([\d.]+)s \$[\d.]+ \((.*?)\): (.*)", msg)
            if m:
                for x in m.group(3).split(" | "):
                    if x.startswith("say:"):
                        pulses.append(("flight" if lg == "astra.flight" else "marines", {"t": rel(t), "answer": "speaking to the net" in m.group(2), "via": "net"}))
    pulses.sort(key=lambda cp: cp[1]["t"])
    leftovers = 0
    for cls, p in pulses:
        l = take(cls, p["t"])
        if l is None:
            leftovers += 1
            continue
        prod.append({"t": round(max(0.0, p["t"] - 0.3), 2), "kind": "net", "speaker": l["key"], "text": l["text"], "urgent": l["prio"] == "urgent", "answer": p["answer"], "via": p["via"]})
    for l in pool:                                                  # what the record has that no pulse explains (the story's own voices, a pulse the log does not show): produced where it was seen
        if not l["used"]:
            prod.append({"t": round(max(0.0, l["seen"] - 0.2), 2), "kind": "other", "speaker": l["key"], "text": l["text"], "urgent": l["prio"] == "urgent", "answer": False})
    prod.sort(key=lambda p: p["t"])
    events = []
    for t, msg in grows:
        m = re.match(r"\[Event\](?: \((report)\))? (.*)", msg)
        if m:
            events.append({"t": rel(t), "text": m.group(2), "report": bool(m.group(1))})
    # --- what each Captain's word was answered with
    for c in captain:
        nxt = next((tn for tn in turns if tn["end"] >= c["t"] - 0.05 and tn["end"] - tn["total_s"] <= c["t"] + 8.0), None)
        c["reply"] = {"first_s": nxt["first_s"], "total_s": nxt["total_s"], "lines": nxt["lines"]} if nxt else None
    return {"session": name, "start": t0.isoformat(timespec="seconds"), "duration_s": rel(t1), "captain": captain, "producers": prod, "events": events,
            "recorded": {"spoken": spoken, "dropped": dropped, "rethought": rethought}, "unpaired_pulses": leftovers}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mind", default=str(MIND_LOG))
    ap.add_argument("--game", nargs="*", default=[str(p) for p in GAME_LOGS])
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    mind = read_mind(Path(args.mind))
    game = read_game([Path(p) for p in args.game])
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, t0, t1 in sessions(mind):
        case = extract(name, t0, t1, mind, game)
        (out / f"{name}.json").write_text(json.dumps(case, ensure_ascii=False, indent=1), encoding="utf-8")
        kinds: dict[str, int] = defaultdict(int)
        for p in case["producers"]:
            kinds[p["kind"]] += 1
        rec = case["recorded"]
        merged = sum(1 for d in rec["dropped"] if d["reason"].startswith("merged_into"))
        print(f"{name}: {case['duration_s'] / 60:.1f} min, {len(case['captain'])} Captain's words, {len(case['producers'])} lines produced {dict(kinds)}, {len(case['events'])} events; "
              f"the record: {len(rec['spoken'])} heard, {len(rec['dropped'])} never said ({merged} of them merged into others); unpaired pulses {case['unpaired_pulses']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
