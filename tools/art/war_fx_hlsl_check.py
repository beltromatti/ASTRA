#!/usr/bin/env python3
"""Compiles every Custom-node shader of the war's effects (tools/ue_scripts/war_fx_hlsl.py) with the DXC the engine ships, each wrapped in a
function with the typed inputs its material connects to it, so a typo or a type mismatch shows here and not in the editor's shader compiler.

  python3 tools/art/war_fx_hlsl_check.py

Builds tools/art/dxc_check.cpp into a temporary folder the first time (clang++ from Xcode, the engine's DXC library and headers).
Beside "ok" it prints the size of each compiled shader (instructions, texture reads, transcendental ops: a rough proxy for what one pixel of it costs).
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools", "ue_scripts"))
import war_fx_hlsl as H  # noqa: E402

UE = "/Users/Shared/Epic Games/UE_5.8"
INCLUDE = UE + "/Engine/Source/ThirdParty/ShaderConductor/ShaderConductor/External/DirectXShaderCompiler/include"

F, F2, F3, F4 = "float", "float2", "float3", "float4"
# name -> (snippet, return type, [(input name, type)]), as the materials of make_war_fx.py connect them
SNIPPETS = {
    "MINSIZE": (H.MINSIZE, F3, [("RadW", F3), ("WPrel", F3), ("TanHalf", F2), ("ViewSz", F2), ("MinPx", F)]),
    "MINSIZE_PLUME": (H.MINSIZE_PLUME, F3, [("RadW", F3), ("WPrel", F3), ("TanHalf", F2), ("ViewSz", F2), ("MinPx", F), ("LZ", F)]),
    "DART": (H.DART, F3, [("NW", F3), ("CamV", F3), ("LP", F3), ("AxisW", F3), ("Col", F3), ("Inten", F), ("Age", F), ("Style", F), ("P2", F), ("Seed", F), ("Tm", F)]),
    "TUBE": (H.TUBE, F3, [("NW", F3), ("CamV", F3), ("LP", F3), ("AxisW", F3), ("LenM", F), ("Col", F3), ("Inten", F), ("Age", F), ("Style", F), ("P2", F), ("Seed", F), ("Tm", F)]),
    "GLOW": (H.GLOW, F3, [("Fr", F), ("VN", F3), ("Col", F3), ("Inten", F), ("Age", F), ("Kind", F), ("Seed", F), ("Tm", F)]),
    "FIRE_UV": (H.FIRE_UV, F4, [("VN", F3), ("Age", F), ("Seed", F)]),
    "FIRE_W": (H.FIRE_W, F, [("Age", F)]),
    "FIRE_SHADE": (H.FIRE_SHADE, F3, [("TA", F3), ("TB", F3), ("W", F), ("VN", F3), ("Col", F3), ("Inten", F)]),
    "SMOKE_SHADE": (H.SMOKE_SHADE, F4, [("TA", F3), ("TB", F3), ("W", F), ("VN", F3), ("Col", F3), ("Inten", F), ("Age", F), ("Dark", F), ("Glow", F)]),
    "PLUME": (H.PLUME, F3, [("NW", F3), ("CamV", F3), ("LP", F3), ("LenM", F), ("Inten", F), ("Faction", F), ("Sputter", F), ("Seed", F), ("Tm", F)]),
    "SHIELD": (H.SHIELD, F3, [("LP", F3), ("Tm", F), ("Axes", F4), ("Col", F4), ("HexSize", F), ("Gain", F), ("Collapse", F4)]
               + [(f"Hit{i}", F4) for i in range(6)] + [(f"Info{i}", F4) for i in range(6)]),
}
CONSTS = {F: "0.5", F2: "float2(0.5, 0.5)", F3: "float3(0.5, 0.5, 0.5)", F4: "float4(0.5, 0.5, 0.5, 0.5)"}


def wrapper(code: str, ret: str, inputs) -> str:
    """The node's code as a function and a pixel shader that calls it. The inputs come from a constant buffer (not constants: the compiler would fold the whole
    node into a value and the size it reports would be nothing), the way a material's parameters and interpolants arrive."""
    params = ", ".join(f"{t} {n}" for n, t in inputs)
    swz = {F: ".x", F2: ".xy", F3: ".xyz", F4: ""}
    args = ", ".join(f"K[{i}]{swz[t]}" for i, (_, t) in enumerate(inputs))
    call = f"CustomExpression0({args})"
    out = {F: f"float4({call}, 0, 0, 1)", F3: f"float4({call}, 1)", F4: call}[ret]
    return (f"cbuffer Inputs : register(b0) {{ float4 K[{len(inputs)}]; }}\n\n{ret} CustomExpression0({params})\n{{\n{code}\n}}\n\n"
            f"float4 main() : SV_Target\n{{\n    return {out};\n}}\n")


def build_runner(folder: str) -> str:
    exe = os.path.join(folder, "dxc_check")
    src = os.path.join(ROOT, "tools", "art", "dxc_check.cpp")
    if not os.path.exists(exe) or os.path.getmtime(exe) < os.path.getmtime(src):
        subprocess.run(["clang++", "-std=c++17", "-fms-extensions", "-Wno-everything", f"-I{INCLUDE}", src, "-o", exe, "-ldl"], check=True)
    return exe


def main() -> int:
    folder = os.environ.get("WAR_FX_CHECK_DIR") or tempfile.mkdtemp(prefix="war_fx_hlsl_")
    os.makedirs(folder, exist_ok=True)
    exe = build_runner(folder)
    bad = 0
    for name, (code, ret, inputs) in SNIPPETS.items():
        path = os.path.join(folder, name + ".hlsl")
        with open(path, "w") as fh:
            fh.write(wrapper(code, ret, inputs))
        r = subprocess.run([exe, path], capture_output=True, text=True, cwd=folder, env=dict(os.environ, DXC_STATS="1"))
        stats = [l[len("STATS "):] for l in r.stdout.splitlines() if l.startswith("STATS ")]
        msgs = [l for l in (r.stdout + r.stderr).splitlines() if "DXIL signing" not in l and l.strip() and l.strip() != "COMPILED" and not l.startswith("STATS ")]
        ok = r.returncode == 0
        print(f"{'ok  ' if ok else 'FAIL'} {name:14s} {stats[0] if stats else ''}")
        for l in msgs[:20]:
            print("     " + l)
        bad += 0 if ok else 1
    print(f"{len(SNIPPETS) - bad}/{len(SNIPPETS)} compile")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
