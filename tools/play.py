#!/usr/bin/env python3
"""Play ASTRA like a person, from the terminal — the client of the playtest harness (Source/ASTRA/AstraHarness.*).

  tools/play.py launch [--map /Game/ASTRA/Maps/L_Bridge] [--res 1600x900] [--continue] [--nomind] [--sound] [--args "..."]
  tools/play.py state                     where the Captain is, posture, view, fps, menu, game clock
  tools/play.py perf [SECONDS] [--label]  median frame timings: fps, game thread, render thread, GPU, dynamic resolution
  tools/play.py ship [key ...]            the ship snapshot the crew sees (optionally only some keys)
  tools/play.py timeline [--all|--last N] what happened since the last call (lines, reports, commands, inputs)
  tools/play.py watch SECONDS             print what happens for a while
  tools/play.py key W [--hold 2] [--nowait] · down W · up W      real key presses through Slate
  tools/play.py walk fwd|back|left|right SECONDS [--run]
  tools/play.py look YAW [PITCH]          degrees (right and up positive)
  tools/play.py tp X Y [YAW [PITCH]] [--z Z]  the Captain on foot at a point of the bridge (metres), for pictures
  tools/play.py say "text"                a typed order to the crew (like T)
  tools/play.py cmd "console command"
  tools/play.py shot [name] [--noui]      screenshot (with the UI unless --noui): prints the PNG path
  tools/play.py quit

The game runs from the editor binary (-game, windowed, no Shipping). Every entry of the timeline carries the game clock,
so a test can reason about order and delays like a player who remembers what happened when.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = Path("/Users/Shared/Epic Games/UE_5.8/Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor")
PLAY_DIR = ROOT / "Saved" / "Play"
PORT = int(os.environ.get("ASTRA_HARNESS_PORT", "8770"))
BASE = f"http://127.0.0.1:{PORT}"
LAST = PLAY_DIR / ".timeline_last"


def call(path: str, body: dict | None = None, timeout: float = 10.0) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=data, method="GET" if body is None else "POST",
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read().decode("utf-8", "replace")
    return json.loads(raw) if raw.strip() else {}


def alive() -> bool:
    try:
        call("/state", timeout=2.0)
        return True
    except (urllib.error.URLError, ConnectionError, TimeoutError, OSError, json.JSONDecodeError):
        return False


def fmt_entry(e: dict) -> str:
    g = e.get("game", -1)
    clock = f"{g:8.1f}s" if g is not None and g >= 0 else "     -  "
    return f"[{clock}] {e.get('kind', '?'):7} {e.get('text', '')}"


def timeline(since: float) -> tuple[list[dict], float]:
    t = call(f"/timeline?since={since}")
    return t.get("entries", []), float(t.get("now", since))


def port_free() -> bool:
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def game_process() -> bool:
    return subprocess.run(["pgrep", "-f", f"astra_harness_port={PORT}"], capture_output=True).returncode == 0


def cmd_launch(a: argparse.Namespace) -> None:
    if alive():
        print("a harness game is already running; `tools/play.py quit` first")
        return
    # a game still closing keeps the port: the new one would run without the harness
    for _ in range(40):
        if not game_process():
            break
        time.sleep(0.5)
    else:
        subprocess.run(["pkill", "-f", f"astra_harness_port={PORT}"], check=False)
        time.sleep(2.0)
    # the last game's connections linger a while in TIME_WAIT and the engine's listener cannot bind until they go
    for _ in range(120):
        if port_free():
            break
        time.sleep(0.5)
    PLAY_DIR.mkdir(parents=True, exist_ok=True)
    w, h = a.res.split("x")
    args = [str(ENGINE), str(ROOT / "ASTRA.uproject"), a.map, "-game", "-windowed", f"-ResX={w}", f"-ResY={h}",
            "-astra_harness", f"-astra_harness_port={PORT}", "-unattended", "-NoVerifyGC",
            "-astra_campaign=continue" if a.cont else "-astra_campaign=new"]
    if a.nomind:
        args.append("-astra_nomind")
    if not a.sound:
        args.append("-nosound")
    if a.args:
        args += a.args.split()
    log = open(PLAY_DIR / "game_stdout.log", "w")
    subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, cwd=str(ROOT), start_new_session=True)
    t0 = time.time()
    while time.time() - t0 < 240:
        time.sleep(1.0)
        if alive():
            st = call("/state")
            if st.get("pawn", {}).get("class"):
                LAST.write_text(str(st.get("real", 0.0)))
                print(f"game up in {time.time() - t0:.0f} s: {json.dumps(st)}")
                return
    print("the game did not answer in 240 s (see Saved/Play/game_stdout.log)")
    sys.exit(1)


def cmd_state(_: argparse.Namespace) -> None:
    print(json.dumps(call("/state"), ensure_ascii=False))


def cmd_ship(a: argparse.Namespace) -> None:
    s = call("/ship")
    if a.keys:
        s = {k: s.get(k) for k in a.keys}
    print(json.dumps(s, ensure_ascii=False, indent=1))


def cmd_timeline(a: argparse.Namespace) -> None:
    since = 0.0 if a.all else float(LAST.read_text()) if LAST.exists() else 0.0
    entries, now = timeline(since)
    if a.last:
        entries = entries[-a.last:]
    for e in entries:
        print(fmt_entry(e))
    LAST.write_text(str(now))


def cmd_watch(a: argparse.Namespace) -> None:
    since = float(LAST.read_text()) if LAST.exists() else call("/state").get("real", 0.0)
    end = time.time() + a.seconds
    while time.time() < end:
        entries, now = timeline(since)
        for e in entries:
            print(fmt_entry(e), flush=True)
        since = now
        time.sleep(0.5)
    LAST.write_text(str(since))


def cmd_key(a: argparse.Namespace) -> None:
    action = {"key": "tap", "down": "down", "up": "up"}[a.cmd]
    print(json.dumps(call("/key", {"key": a.key, "action": action, "hold": a.hold})))
    if action == "tap" and not a.nowait:
        time.sleep(a.hold + 0.15)


def cmd_walk(a: argparse.Namespace) -> None:
    key = {"fwd": "W", "back": "S", "left": "A", "right": "D"}[a.dir]
    if a.run:
        call("/key", {"key": "LeftShift", "action": "down"})
    call("/key", {"key": key, "action": "tap", "hold": a.seconds})
    time.sleep(a.seconds + 0.2)
    if a.run:
        call("/key", {"key": "LeftShift", "action": "up"})
    print(json.dumps(call("/state").get("pawn", {})))


def cmd_look(a: argparse.Namespace) -> None:
    print(json.dumps(call("/look", {"yaw": a.yaw, "pitch": a.pitch})))


def cmd_tp(a: argparse.Namespace) -> None:
    print(json.dumps(call("/teleport", {"x": a.x, "y": a.y, "z": a.z, "yaw": a.yaw, "pitch": a.pitch})))


def cmd_perf(a: argparse.Namespace) -> None:
    """Median frame timings over a few seconds (like stat unit): fps, game thread, render thread, GPU, dynamic resolution."""
    keys = ("game_ms", "render_ms", "gpu_ms", "dynres_pct")
    samples: dict[str, list[float]] = {k: [] for k in keys}
    fps: list[float] = []
    end = time.time() + a.seconds
    while time.time() < end:
        st = call("/state")
        fps.append(float(st.get("fps", 0)))
        for k in keys:
            v = st.get("perf", {}).get(k)
            if isinstance(v, (int, float)):
                samples[k].append(float(v))
        time.sleep(0.25)

    def med(xs: list[float]) -> float:
        xs = sorted(xs)
        return xs[len(xs) // 2] if xs else float("nan")
    print(f"{a.label + ': ' if a.label else ''}fps {med(fps):.1f} · game {med(samples['game_ms']):.1f} ms · render {med(samples['render_ms']):.1f} ms"
          f" · gpu {med(samples['gpu_ms']):.1f} ms · dynres {med(samples['dynres_pct']):.0f}%")


def cmd_say(a: argparse.Namespace) -> None:
    print(json.dumps(call("/say", {"text": a.text})))


def cmd_cmd(a: argparse.Namespace) -> None:
    r = call("/cmd", {"cmd": a.command})
    print(r.get("out", "") or json.dumps(r))


def cmd_shot(a: argparse.Namespace) -> None:
    PLAY_DIR.mkdir(parents=True, exist_ok=True)
    name = a.name or time.strftime("shot_%H%M%S")
    path = (PLAY_DIR / f"{name}.png").resolve()
    call("/shot", {"path": str(path), "ui": not a.noui})
    t0, size = time.time(), -1
    while time.time() - t0 < 15:
        time.sleep(0.25)
        if path.exists():
            s = path.stat().st_size
            if s > 0 and s == size:
                print(path)
                return
            size = s
    print(f"no screenshot after 15 s ({path})")
    sys.exit(1)


def cmd_quit(_: argparse.Namespace) -> None:
    try:
        call("/quit", {})
    except (urllib.error.URLError, OSError):
        pass
    # the game closes in a few seconds; make sure (a harness game is always ours)
    for _ in range(60):
        time.sleep(0.5)
        if not alive() and not game_process():
            print("game closed")
            return
    subprocess.run(["pkill", "-f", f"astra_harness_port={PORT}"], check=False)
    print("game killed (it did not close by itself)")


def main() -> None:
    ap = argparse.ArgumentParser(prog="play.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("launch")
    p.add_argument("--map", default="/Game/ASTRA/Maps/L_Bridge")
    p.add_argument("--res", default="1600x900")
    p.add_argument("--continue", dest="cont", action="store_true")
    p.add_argument("--nomind", action="store_true")
    p.add_argument("--sound", action="store_true")
    p.add_argument("--args", default="")
    p.set_defaults(fn=cmd_launch)
    sub.add_parser("state").set_defaults(fn=cmd_state)
    p = sub.add_parser("ship")
    p.add_argument("keys", nargs="*")
    p.set_defaults(fn=cmd_ship)
    p = sub.add_parser("timeline")
    p.add_argument("--all", action="store_true")
    p.add_argument("--last", type=int, default=0)
    p.set_defaults(fn=cmd_timeline)
    p = sub.add_parser("watch")
    p.add_argument("seconds", type=float)
    p.set_defaults(fn=cmd_watch)
    for name in ("key", "down", "up"):
        p = sub.add_parser(name)
        p.add_argument("key")
        p.add_argument("--hold", type=float, default=0.12)
        p.add_argument("--nowait", action="store_true")
        p.set_defaults(fn=cmd_key)
    p = sub.add_parser("walk")
    p.add_argument("dir", choices=["fwd", "back", "left", "right"])
    p.add_argument("seconds", type=float)
    p.add_argument("--run", action="store_true")
    p.set_defaults(fn=cmd_walk)
    p = sub.add_parser("look")
    p.add_argument("yaw", type=float)
    p.add_argument("pitch", type=float, nargs="?", default=0.0)
    p.set_defaults(fn=cmd_look)
    p = sub.add_parser("tp", help="the Captain on foot at x y [z] metres (bridge frame), looking yaw [pitch]")
    p.add_argument("x", type=float)
    p.add_argument("y", type=float)
    p.add_argument("yaw", type=float, nargs="?", default=0.0)
    p.add_argument("pitch", type=float, nargs="?", default=0.0)
    p.add_argument("--z", type=float, default=0.0)
    p.set_defaults(fn=cmd_tp)
    p = sub.add_parser("perf", help="median frame timings over a few seconds")
    p.add_argument("seconds", type=float, nargs="?", default=6.0)
    p.add_argument("--label", default="")
    p.set_defaults(fn=cmd_perf)
    p = sub.add_parser("say")
    p.add_argument("text")
    p.set_defaults(fn=cmd_say)
    p = sub.add_parser("cmd")
    p.add_argument("command")
    p.set_defaults(fn=cmd_cmd)
    p = sub.add_parser("shot")
    p.add_argument("name", nargs="?")
    p.add_argument("--noui", action="store_true")
    p.set_defaults(fn=cmd_shot)
    sub.add_parser("quit").set_defaults(fn=cmd_quit)
    a = ap.parse_args()
    try:
        a.fn(a)
    except (urllib.error.URLError, ConnectionError, OSError) as e:
        print(f"no harness game on {BASE} ({e}); start one with `tools/play.py launch`")
        sys.exit(2)


if __name__ == "__main__":
    main()
