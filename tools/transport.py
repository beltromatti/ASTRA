#!/usr/bin/env python3
"""TELETRASPORTO, the lattice transport of the ASN Aquila (Source/ASTRA/AstraTransport*.cpp, docs/TELETRASPORTO.md): the bench and the staging.

  tools/transport.py run [--scenario all|rules|world] [--seed 1] [--out Saved/Transport/run.json] [--verbose]
                                       the commandlet AstraTransport: the rules of the beam on scripted cases (the shields' faces at both ends, range, jamming
                                       along the line, the ship's motion, a Gate's field, the room's power and hazards, the lock's life, the arrival's rolls) and
                                       the whole subsystem in a headless world on the real plan and the real battle; prints each check and the verdict
  tools/transport.py check             does data/ship/aquila_transport.json still describe the room the plan and the kit build? (no engine: Python only)
  tools/transport.py stage             copies data/ship/aquila_transport.json to Content/ASTRA/Data (the game reads that copy first; `tools/life.py stage` does
                                       the same for the plan and the life tables)

`run` needs the editor target built for this checkout (Build.sh ASTRAEditor Mac Development -Project=... -WaitMutex) and uses -nullrhi: it never opens a window
or touches the GPU, so it can run while the game or the editor is open (one engine process of ~1.5 GB).
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_UE = Path(os.environ["UE_ROOT"]) if os.environ.get("UE_ROOT") else Path("/Users/Shared/Epic Games/UE_5.8" if sys.platform == "darwin" else "C:/Program Files/Epic Games/UE_5.8")
ENGINE = _UE / ("Engine/Binaries/Mac/UnrealEditor-Cmd" if sys.platform == "darwin" else "Engine/Binaries/Win64/UnrealEditor-Cmd.exe")
OUT = ROOT / "Saved" / "Transport"
DATA = ROOT / "data" / "ship" / "aquila_transport.json"
PLAN = ROOT / "data" / "ship" / "aquila_plan.json"
MEDBAY = ROOT / "data" / "ship" / "aquila_medbay.json"
KIT = ROOT / "art" / "blender" / "ship_rooms_science.py"


def cmd_run(a: argparse.Namespace) -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    out = (ROOT / a.out).resolve()
    log = OUT / "last_run.log"
    args = [str(ENGINE), str(ROOT / "ASTRA.uproject"), "-run=AstraTransport", f"-scenario={a.scenario}", f"-seed={a.seed}", f"-out={out}",
            "-nullrhi", "-unattended", "-nosound", "-nopause", "-nosplash", "-NoVerifyGC", "-stdout", "-FullStdOutLogOutput"]
    t0 = time.time()
    with open(log, "w") as f:
        p = subprocess.Popen(args, stdout=f, stderr=subprocess.STDOUT, cwd=str(ROOT))
        while p.poll() is None:
            time.sleep(0.5)
            try:
                with open(log, "rb") as r:
                    r.seek(max(0, log.stat().st_size - 40000))
                    tail = r.read().decode(errors="replace")
            except OSError:
                tail = ""
            crashed = "Critical error" in tail or "Assertion failed" in tail
            if crashed or time.time() - t0 > a.timeout:
                time.sleep(2.0 if crashed else 0.0)
                p.kill()
                p.wait()
                print(f"   the transport bench {'crashed' if crashed else 'did not finish in time'}: killed (log {log})")
                break
        rc = p.returncode
    subprocess.run(["pkill", "-f", "CrashReportClient"], check=False)           # (a crash leaves its reporter behind)
    text = log.read_text(errors="replace").splitlines()
    lines = [l[l.find("[Transport]"):] for l in text if "[Transport]" in l]
    for l in lines[-(600 if a.verbose else 200):]:
        print(l)
    print(f"exit {rc} in {time.time() - t0:.0f} s; log {log}")
    return 0 if any("VERDICT: PASS" in l for l in lines) else 1


def cmd_check(_: argparse.Namespace) -> int:
    """Does data/ship/aquila_transport.json still describe the room the plan and the kit build? (no engine: Python only)"""
    data = json.loads(DATA.read_text(encoding="utf-8"))
    plan = json.loads(PLAN.read_text(encoding="utf-8"))
    lay = data["room"]["layout"]
    kind = data["room"]["kind"]
    out: list[tuple[bool, str]] = []

    def ck(ok: bool, text: str) -> None:
        out.append((ok, text))

    room = next((c for c in plan["compartments"] if c.get("kind") == kind and c.get("status") in ("built", "existing")), None)
    ck(room is not None, f"the plan has a built compartment of kind `{kind}`")
    if room is None:
        return _report(out)
    pos, yaw = room["pos"], float(room.get("yaw", 0.0))
    b = room["bounds"]                                    # x0, y0, x1, y1 (m)
    # the game takes the room's frame from its box: yaw 0 on the starboard side (the corner at the box's minimum), 180 on the port side (the maximum)
    stbd = (b[1] + b[3]) / 2 >= 0
    want_yaw = 0.0 if stbd else 180.0
    corner = (b[0], b[1]) if stbd else (b[2], b[3])
    ck(abs(yaw - want_yaw) < 0.5, f"the room's yaw is {yaw:.0f}: the game assumes {want_yaw:.0f} for a room on the {'starboard' if stbd else 'port'} side")
    ck(abs(pos[0] - corner[0]) < 0.01 and abs(pos[1] - corner[1]) < 0.01, f"the room's `pos` ({pos[0]:.1f}, {pos[1]:.1f}) is the box's {'minimum' if stbd else 'maximum'} corner ({corner[0]:.1f}, {corner[1]:.1f})")
    th = math.radians(yaw)

    def world(lx: float, ly: float) -> tuple[float, float]:
        return (pos[0] + lx * math.cos(th) - ly * math.sin(th), pos[1] + lx * math.sin(th) + ly * math.cos(th))

    # the pads: the plan's visitor stations stand on pads 1 and 4 (the kit's own platform), the operators sit behind the chief's stand
    cx, cy = lay["dais"]["center"]
    ring = lay["dais"]["ring_m"]
    pads = [world(cx + ring * math.cos(math.radians(lay["dais"]["first_deg"] + 60 * i)), cy + ring * math.sin(math.radians(lay["dais"]["first_deg"] + 60 * i))) for i in range(lay["dais"]["pads"])]
    visitors = [st for st in room.get("stations", []) if st.get("role") == "visitor"]
    for st in visitors:
        d = min(math.hypot(st["pos"][0] - px, st["pos"][1] - py) for px, py in pads)
        ck(d < 0.35, f"visitor station {st['id']} stands on a pad ({d:.2f} m from the nearest)")
    ops = [st for st in room.get("stations", []) if st.get("role") == "transport_operator"]
    if len(ops) >= 2:
        sx, sy = lay["chief"]["stand"]
        wx, wy = world(sx, sy)
        mid = (sum(o["pos"][1] for o in ops) / len(ops))
        ck(abs(wx - ops[0]["pos"][0]) < 0.4 and abs(wy - mid) < 0.5, f"the Chief's stand ({wx:.1f}, {wy:.1f}) is behind the operators' chairs (x {ops[0]['pos'][0]:.1f}, y centre {mid:.1f})")
    # the kit: the numbers the data repeats
    src = KIT.read_text(encoding="utf-8") if KIT.exists() else ""
    fn = src[src.find("def transporter("):] if src else ""
    fn = fn[:fn.find("\n    return b.build")] if fn else ""
    m = re.search(r"cx, cy = ([\d.]+), ([\d.]+)", fn)
    ck(bool(m) and abs(float(m.group(1)) - cx) < 1e-6 and abs(float(m.group(2)) - cy) < 1e-6, f"the kit's platform centre {m.groups() if m else '?'} is the data's ({cx}, {cy})")
    m = re.search(r"transporter_dais\(b, ([\d.]+), (\d+), ([\d.]+), ([\d.]+), ([\d.]+)\)", fn)
    ck(bool(m) and int(m.group(2)) == lay["dais"]["pads"] and abs(float(m.group(3)) - lay["dais"]["pad_r_m"]) < 1e-6 and abs(float(m.group(4)) - ring) < 1e-6,
       f"the kit's dais (pads, pad radius, ring) {m.groups()[1:4] if m else '?'} is the data's ({lay['dais']['pads']}, {lay['dais']['pad_r_m']}, {ring})")
    m = re.search(r"b\.at\(T\(([\d.]+), ([\d.]+), 0\.0\)\):\s*\n\s*b\.body\.box\(\(-1\.4", fn)
    ck(bool(m) and abs(float(m.group(1)) - lay["cargo"]["center"][0]) < 1e-6 and abs(float(m.group(2)) - lay["cargo"]["center"][1]) < 1e-6, f"the kit's cargo platform {m.groups() if m else '?'} is the data's {lay['cargo']['center']}")
    m = re.search(r"wall_rack_panel, ([\d.]+), ([\d.]+)", fn)
    ck(bool(m) and lay["wall_screen"]["size_m"][0] <= float(m.group(1)) and lay["wall_screen"]["size_m"][1] <= float(m.group(2)),
       f"the wall screen {lay['wall_screen']['size_m']} fits the kit's wall panel {tuple(map(float, m.groups())) if m else '?'}")
    # the Medbay's emergency pads: the data's world positions against the Medbay's own frame
    med = json.loads(MEDBAY.read_text(encoding="utf-8")) if MEDBAY.exists() else {}
    o = med.get("world_origin")
    for e in data.get("emergency", []):
        if o:
            ok = abs(e["pos"][0] - (o[0] - 6.0)) < 0.2 and abs(abs(e["pos"][1]) - 1.8) < 0.2 and abs(e["pos"][2] - o[2]) < 0.1
            ck(ok, f"emergency pad {e['id']} at {e['pos']} is in the Medbay's aisle (its origin {o}, local x -6, y +-1.8)")
    ck(data["limits"]["pads"] == lay["dais"]["pads"], f"the limit of pads ({data['limits']['pads']}) is the platform's ({lay['dais']['pads']})")
    return _report(out)


def _report(out: list[tuple[bool, str]]) -> int:
    for ok, text in out:
        print(("ok      " if ok else "CHANGED ") + text)
    bad = [t for ok, t in out if not ok]
    print(f"{len(out) - len(bad)}/{len(out)} agree" + ("" if not bad else ": change data/ship/aquila_transport.json (room.layout, emergency) to follow the plan and the kit, then tools/transport.py stage"))
    return 1 if bad else 0


def cmd_stage(_: argparse.Namespace) -> int:
    dst = ROOT / "Content" / "ASTRA" / "Data"
    dst.mkdir(parents=True, exist_ok=True)
    (dst / DATA.name).write_bytes(DATA.read_bytes())
    print(f"{DATA.relative_to(ROOT)} -> {(dst / DATA.name).relative_to(ROOT)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--scenario", default="all", help="all | rules | world")
    r.add_argument("--seed", type=int, default=1)
    r.add_argument("--out", default="Saved/Transport/run.json")
    r.add_argument("--timeout", type=int, default=900)
    r.add_argument("--verbose", action="store_true")
    r.set_defaults(fn=cmd_run)
    sub.add_parser("stage").set_defaults(fn=cmd_stage)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
