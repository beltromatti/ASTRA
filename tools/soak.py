#!/usr/bin/env python3
"""A long run of the game, measured: what an hour of ASTRA costs and does (the lead's soak test).

    tools/play.py launch [--nomind] ...           # the game first (the harness), then:
    tools/soak.py run MINUTES [--every 60] [--jump 170]
    tools/soak.py report [--since HH:MM] [--until HH:MM]

`run` samples the running game every `--every` seconds (game clock, frame timings, the game's memory) into Saved/Play/soak.jsonl and
kills any CrashReportClient a helper's crashed commandlet left spinning (it steals two cores and the timings with them). `report` reads
those samples, the mind's ledger (mind/.cache/spend.jsonl: every model call with its role and cost) and the harness timeline over the same
window, and prints: frame timings (median and worst), memory at the start and the end, the spend by role and per hour, and what happened
(lines spoken, reports, beats of the director, errors in the mind's log)."""
from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAY = [sys.executable, str(ROOT / "tools" / "play.py")]
SAMPLES = ROOT / "Saved" / "Play" / "soak.jsonl"
LEDGER = ROOT / "mind" / ".cache" / "spend.jsonl"
MIND_LOG = ROOT / "Saved" / "Logs" / "astra-mind.log"


def _play(*args: str, timeout: float = 60.0) -> str:
    try:
        return subprocess.run(PLAY + list(args), capture_output=True, text=True, timeout=timeout).stdout
    except subprocess.TimeoutExpired:
        return ""


def _game_pid() -> int | None:
    out = subprocess.run(["pgrep", "-f", r"UnrealEditor\.app/Contents/MacOS/UnrealEditor .*-game"], capture_output=True, text=True).stdout.split()
    return int(out[0]) if out else None


def _rss_gb(pid: int | None) -> float | None:
    if pid is None:
        return None
    out = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return round(int(out) / 1048576.0, 2) if out.isdigit() else None


def _perf() -> dict[str, float]:
    line = _play("perf", "4").strip().splitlines()[-1:] or [""]
    vals = dict(re.findall(r"(fps|game|render|gpu|dynres) ([\d.]+)", line[0]))
    return {k: float(v) for k, v in vals.items()}


def run(minutes: float, every: float, jump: float | None) -> None:
    if jump is not None:
        _play("cmd", f"astra.battle.time {jump:g}")
    SAMPLES.parent.mkdir(parents=True, exist_ok=True)
    end = time.time() + minutes * 60.0
    with SAMPLES.open("w", encoding="utf-8") as f:            # (a run starts the samples afresh: the report reads one run)
        while time.time() < end:
            time.sleep(every)
            subprocess.run(["pkill", "-f", "CrashReportClient"], capture_output=True)
            state = _play("state")
            try:
                clock = json.loads(state).get("game")
            except ValueError:
                clock = None
            row = {"t": round(time.time(), 1), "game_s": clock, "rss_gb": _rss_gb(_game_pid()), **_perf()}
            f.write(json.dumps(row) + "\n")
            f.flush()
            print(datetime.fromtimestamp(row["t"]).strftime("%H:%M:%S"), json.dumps({k: v for k, v in row.items() if k != "t"}), flush=True)


def _hm(s: str | None) -> float | None:
    if not s:
        return None
    today = datetime.now().strftime("%Y-%m-%d ")
    return datetime.strptime(today + s, "%Y-%m-%d %H:%M").timestamp()


def report(since: str | None, until: str | None) -> None:
    rows = [json.loads(l) for l in SAMPLES.read_text().splitlines() if l.strip()] if SAMPLES.exists() else []
    t0, t1 = _hm(since), _hm(until)
    if rows:
        t0 = t0 or rows[0]["t"] - 60.0
        t1 = t1 or rows[-1]["t"]
    rows = [r for r in rows if t0 is None or t0 <= r["t"] <= (t1 or 1e12)]
    if not rows and (t0 is None or t1 is None):
        print("no samples in the window (tools/soak.py run first, or give --since and --until)")
        return
    hours = max((t1 - t0) / 3600.0, 1e-6)
    print(f"window {datetime.fromtimestamp(t0):%H:%M}–{datetime.fromtimestamp(t1):%H:%M} ({hours * 60:.0f} min, {len(rows)} samples)")
    for k in ("fps", "game", "render", "gpu", "dynres"):
        v = [r[k] for r in rows if k in r]
        if v:
            worst = min(v) if k in ("fps", "dynres") else max(v)
            print(f"  {k:7s} median {statistics.median(v):6.1f}   worst {worst:6.1f}")
    mem = [r["rss_gb"] for r in rows if r.get("rss_gb")]
    if mem:
        print(f"  memory  {mem[0]:.2f} GB at the start, {mem[-1]:.2f} GB at the end, {max(mem):.2f} GB at most")
    # the spend in the window
    by_role: dict[str, float] = defaultdict(float)
    n_role: Counter = Counter()
    tokens_in, cached = 0, 0
    if LEDGER.exists():
        for l in LEDGER.read_text().splitlines():
            try:
                c = json.loads(l)
            except ValueError:
                continue
            if t0 <= c.get("t", 0) <= t1:
                by_role[c.get("role", "?")] += c.get("cost", 0.0)
                n_role[c.get("role", "?")] += 1
                tokens_in += c.get("in", 0) or 0
                cached += c.get("cached", 0) or 0
    total = sum(by_role.values())
    print(f"  spend   {total:.4f} $ in the window = {total / hours:.2f} $/hour ({sum(n_role.values())} calls, "
          f"{100.0 * cached / max(tokens_in, 1):.0f} % of the input cached)")
    for r, c in sorted(by_role.items(), key=lambda kv: -kv[1]):
        print(f"    {r:12s} {c:.4f} $  {c / hours:.3f} $/h  ({n_role[r]} calls)")
    # what happened (the harness timeline holds the whole session)
    tl = _play("timeline", "--all", timeout=120.0)
    kinds = Counter(m.group(1) for m in re.finditer(r"^\[\s*[\d.]+s\] (\w+)", tl, re.M))
    print("  timeline " + ", ".join(f"{k} {n}" for k, n in kinds.most_common()))
    beats = [l for l in tl.splitlines() if "director:" in l or "director_beat" in l]
    for l in beats[-8:]:
        print("    " + l[:170])
    if MIND_LOG.exists():
        # the log is the whole history: only the lines of the window (a traceback follows the line that logged it)
        errs, inside = [], False
        for l in MIND_LOG.read_text(errors="ignore").splitlines():
            m = re.match(r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)", l)
            if m:
                ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S").timestamp()
                inside = t0 <= ts <= t1
                if inside and (" ERROR " in l or " failed" in l):
                    errs.append(l)
        print(f"  mind log: {len(errs)} errors in the window" + (f" (last: {errs[-1][:150]})" if errs else ""))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("minutes", type=float)
    r.add_argument("--every", type=float, default=60.0)
    r.add_argument("--jump", type=float, default=None, help="astra.battle.time first (170: the strike group arrives)")
    p = sub.add_parser("report")
    p.add_argument("--since")
    p.add_argument("--until")
    a = ap.parse_args(argv)
    if a.cmd == "run":
        run(a.minutes, a.every, a.jump)
    else:
        report(a.since, a.until)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
