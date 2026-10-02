#!/usr/bin/env python3
"""The war of the March, from the command line (docs/GUERRA.md §10): the abstract war the Aquila's fleet is part of, its high commands' minds, the battle model's calibration
and the offline tests. Never starts the editor or the game: the March is Python, and the only engine process in all of this is the headless commandlet that tools/war.py (and
`cal cpp`) runs.

  tools/march.py sim  [--seeds 1-60 --hours 12 --captain none,idle,fleet,defender,hunter --skill 1.25 --world march|sym --swap --jobs 3]
                                       hours of war in seconds with the code's own reflexes for both sides: who wins, how long it lasts, whether the sides are fair, whether the
                                       Captain counts (mind/bench/march_sim.py)
  tools/march.py live [--hours 1 --seed 3 --cap 0.05 --mock --journal --trace FILE]
                                       a war played by the two high commands' minds (the real model, its cost counted; --mock: a scripted model, no cost): the layer's cost an
                                       hour, the latency of a look, what they decided (mind/bench/march_live.py)
  tools/march.py cal  cpp|model|fit|list ...
                                       the battle model against the war bench's own battles (tools/march_calibrate.py)
  tools/march.py test                  the March's, the minds', the join's and the server's offline tests (no network, no cost)

`live` needs the OpenRouter key: it is read from the main checkout's .env and handed to the process through its environment, never printed."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIND = ROOT / "mind"


def python() -> str:
    """The project's own interpreter (the mind's venv), else this one."""
    for cand in (MIND / ".venv" / "bin" / "python", MIND / ".venv" / "Scripts" / "python.exe"):
        if cand.exists():
            return str(cand)
    return sys.executable


def key_env() -> dict[str, str]:
    """The environment for a live run: the key from the .env of this checkout, or of the main one (a worktree has none)."""
    env = dict(os.environ)
    if "OPENROUTER_API_KEY" in env:
        return env
    here = ROOT
    for _ in range(6):
        f = here / ".env"
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                if line.startswith("OPENROUTER_API_KEY="):
                    env["OPENROUTER_API_KEY"] = line.split("=", 1)[1].strip()
                    return env
        here = here.parent
    return env


def run(args: list[str], env: dict[str, str] | None = None) -> int:
    return subprocess.run([python(), *args], cwd=MIND, env=env).returncode


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    cmd, rest = sys.argv[1], sys.argv[2:]
    if cmd == "sim":
        return run(["-m", "bench.march_sim", *rest])
    if cmd == "live":
        return run(["-m", "bench.march_live", *rest], env=key_env() if "--mock" not in rest else None)
    if cmd == "cal":
        return subprocess.run([python(), str(ROOT / "tools" / "march_calibrate.py"), *rest], cwd=MIND).returncode
    if cmd == "test":
        return run(["-m", "unittest", "bench.march_unit", "bench.strategy_unit", "bench.march_glue_unit", "bench.march_server", "bench.march_soak", *rest])
    print(f"unknown command '{cmd}'\n{__doc__}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
