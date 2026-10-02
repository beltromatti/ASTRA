#!/usr/bin/env python3
"""A/B of a rendering setting in the running game, the way the lead measures (docs/ricerca/11): the same scene, the two values interleaved
cycle after cycle (a battle changes under the measure: interleaving spreads that over both sides), the median of each.

    tools/play.py launch --nomind ...            # the game first, in the scene to measure (astra.battle.time 170: the strike group)
    tools/perf_ab.py "r.Shadow.Virtual.Enable" 1 0 [--cycles 5] [--seconds 6] [--fixed 50] [--also "cvar value" ...]

`--fixed N` turns the dynamic resolution off and renders at N % for the measure (the GPU time then answers the question directly; with the
dynamic resolution on, the GPU stays at its budget and the resolution it settles at is the answer: both are printed). `--also` sets other
console variables first, for both sides. At the end every value goes back to what it was (the dynamic resolution too)."""
from __future__ import annotations

import argparse
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAY = [sys.executable, str(ROOT / "tools" / "play.py")]


def play(*args: str, timeout: float = 60.0) -> str:
    return subprocess.run(PLAY + list(args), capture_output=True, text=True, timeout=timeout).stdout


def cmd(c: str) -> None:
    play("cmd", c)


def perf(seconds: float) -> dict[str, float]:
    line = (play("perf", f"{seconds:g}").strip().splitlines() or [""])[-1]
    return {k: float(v) for k, v in re.findall(r"(fps|game|render|gpu|dynres) ([\d.]+)", line)}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cvar")
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--cycles", type=int, default=5)
    ap.add_argument("--seconds", type=float, default=6.0)
    ap.add_argument("--settle", type=float, default=2.0, help="seconds after a change before measuring (shaders, caches, the dynamic resolution)")
    ap.add_argument("--fixed", type=float, default=None, help="render at this screen percentage, dynamic resolution off")
    ap.add_argument("--also", action="append", default=[], help='"cvar value" set for both sides first')
    a = ap.parse_args(argv)
    for x in a.also:
        cmd(x)
    if a.fixed:
        cmd("r.DynamicRes.OperationMode 0")
        cmd(f"r.ScreenPercentage {a.fixed:g}")
    res: dict[str, list[dict[str, float]]] = {"A": [], "B": []}
    try:
        for c in range(a.cycles):
            for side, val in (("A", a.a), ("B", a.b)) if c % 2 == 0 else (("B", a.b), ("A", a.a)):
                cmd(f"{a.cvar} {val}")
                time.sleep(a.settle)
                p = perf(a.seconds)
                res[side].append(p)
                print(f"cycle {c + 1} {side} ({a.cvar} {val}): " + "  ".join(f"{k} {v:g}" for k, v in p.items()), flush=True)
    finally:
        cmd(f"{a.cvar} {a.a}")
        if a.fixed:
            cmd("r.DynamicRes.OperationMode 2")
    print()
    for k in ("gpu", "render", "game", "fps", "dynres"):
        va = [p[k] for p in res["A"] if k in p]
        vb = [p[k] for p in res["B"] if k in p]
        if va and vb:
            ma, mb = statistics.median(va), statistics.median(vb)
            print(f"{k:7s} A {ma:7.2f}   B {mb:7.2f}   B-A {mb - ma:+7.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
