#!/usr/bin/env python3
"""Compiles every Custom-node shader of the transporter's effects (tools/ue_scripts/transporter_fx_hlsl.py) with the DXC the engine ships, each wrapped in a function with the
typed inputs its material connects to it (tools/ue_scripts/make_transporter_fx.py), so a typo or a type mismatch shows here and not in the editor's shader compiler. It says the
shaders compile; it cannot say they look right (that is the lead's eye in the game, with astra.xport.gain to scale them).

  python3 tools/art/transporter_fx_check.py

Builds tools/art/dxc_check.cpp into a temporary folder the first time (clang++ from Xcode, the engine's DXC library and headers), like the war's own check.
Then runs tools/art/war_fx_script_check.py on the material script (no editor: every class, property and pin it uses is looked up in the editor's own Python stub).
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools", "ue_scripts"))
import transporter_fx_hlsl as H  # noqa: E402

_spec = importlib.util.spec_from_file_location("war_fx_hlsl_check", os.path.join(ROOT, "tools", "art", "war_fx_hlsl_check.py"))
W = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(W)               # type: ignore[union-attr]

F, F3 = W.F, W.F3
SNIPPETS = {
    "SPARKLE": (H.SPARKLE, F3, [("Fr", F), ("Col", F3), ("Inten", F), ("Age", F), ("Seed", F), ("Tm", F)]),
    "COLUMN": (H.COLUMN, F3, [("Fr", F), ("LZ", F), ("Col", F3), ("Inten", F), ("Prog", F), ("Dir", F), ("Fade", F), ("Seed", F), ("Tm", F)]),
    "RING": (H.RING, F3, [("LP", F3), ("Col", F3), ("Inten", F), ("Mode", F), ("Seed", F), ("Tm", F)]),
    "GHOST": (H.GHOST, F3, [("WP", F3), ("Fr", F), ("FeetZ", F), ("Height", F), ("Prog", F), ("Dir", F), ("Gain", F), ("Col", F3), ("Tm", F)]),
}


def compile_all() -> int:
    folder = os.environ.get("XPORT_FX_CHECK_DIR") or tempfile.mkdtemp(prefix="xport_fx_hlsl_")
    os.makedirs(folder, exist_ok=True)
    exe = W.build_runner(folder)
    bad = 0
    for name, (code, ret, inputs) in SNIPPETS.items():
        path = os.path.join(folder, name + ".hlsl")
        with open(path, "w") as fh:
            fh.write(W.wrapper(code, ret, inputs))
        r = subprocess.run([exe, path], capture_output=True, text=True)
        msgs = [l for l in (r.stdout + r.stderr).splitlines() if "DXIL signing" not in l and l.strip() and l.strip() != "COMPILED"]
        ok = r.returncode == 0
        print(f"{'ok  ' if ok else 'FAIL'} {name}")
        for l in msgs[:20]:
            print("     " + l)
        bad += 0 if ok else 1
    print(f"{len(SNIPPETS) - bad}/{len(SNIPPETS)} compile")
    return bad


def script_check() -> int:
    r = subprocess.run([sys.executable, os.path.join(ROOT, "tools", "art", "war_fx_script_check.py"), "--script", os.path.join(ROOT, "tools", "ue_scripts", "make_transporter_fx.py")],
                       capture_output=True, text=True)
    tail = [l for l in r.stdout.splitlines() if l.strip()][-3:]
    print("\n".join(tail) if tail else r.stderr[-400:])
    return 0 if "WAR_FX_SCRIPT_CHECK_OK" in r.stdout else 1


def main() -> int:
    bad = compile_all()
    bad += script_check()
    print("TRANSPORTER_FX_CHECK_OK" if not bad else "TRANSPORTER_FX_CHECK_FAILED")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
