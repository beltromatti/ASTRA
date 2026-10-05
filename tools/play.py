#!/usr/bin/env python3
"""Play ASTRA like a person, from the terminal — the client of the playtest harness (Source/ASTRA/AstraHarness.*).

  tools/play.py launch [--map /Game/ASTRA/Maps/L_Bridge] [--res 1600x900] [--continue] [--nomind] [--sound] [--args "..."] [--app ~/Applications/ASTRA.app]
  tools/play.py state                     where the Captain is, posture, view, fps, menu, game clock
  tools/play.py perf [SECONDS] [--label]  median frame timings: fps, game thread, render thread, GPU, dynamic resolution
  tools/play.py ship [key ...]            the ship snapshot the crew sees (optionally only some keys)
  tools/play.py timeline [--all|--last N] what happened since the last call (lines, reports, commands, inputs)
  tools/play.py watch SECONDS             print what happens for a while
  tools/play.py key W [--hold 2] [--nowait] · down W · up W      real key presses through Slate
  tools/play.py walk fwd|back|left|right SECONDS [--run]
  tools/play.py look YAW [PITCH]          degrees (right and up positive)
  tools/play.py tp X Y [YAW [PITCH]] [--z Z]  the Captain on foot at a point of the bridge (metres), for pictures
  tools/play.py find WORDS                actors by tag, name or class, nearest first (where things are, in metres)
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
import shlex
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WINDOWS = sys.platform == "win32"
# the editor binary that runs the game (-game): UE_ROOT is the engine's folder (the default is where the Epic Launcher puts it)
_UE = Path(os.environ["UE_ROOT"]) if os.environ.get("UE_ROOT") else Path("C:/Program Files/Epic Games/UE_5.8" if WINDOWS else "/Users/Shared/Epic Games/UE_5.8")
ENGINE = (_UE / "Engine/Binaries/Win64/UnrealEditor.exe" if WINDOWS else
          _UE / "Engine/Binaries/Mac/UnrealEditor.app/Contents/MacOS/UnrealEditor" if sys.platform == "darwin" else _UE / "Engine/Binaries/Linux/UnrealEditor")
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


def game_pids() -> list[int]:
    """The processes of the harness game on this port (their command line carries -astra_harness_port=PORT)."""
    needle = f"astra_harness_port={PORT}"
    if WINDOWS:
        # (the query's own PowerShell has the needle in its command line: it is left out)
        query = f"Get-CimInstance Win32_Process | Where-Object {{ $_.CommandLine -like '*{needle}*' -and $_.ProcessId -ne $PID }} | ForEach-Object {{ $_.ProcessId }}"
        out = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", query], capture_output=True, text=True).stdout
    else:
        out = subprocess.run(["pgrep", "-f", needle], capture_output=True, text=True).stdout
    return [int(w) for w in out.split() if w.isdigit()]


def game_process() -> bool:
    return bool(game_pids())


def kill_game() -> None:
    """A harness game is always ours: end it, and what it started."""
    if WINDOWS:
        for pid in game_pids():
            subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], capture_output=True)
    else:
        subprocess.run(["pkill", "-f", f"astra_harness_port={PORT}"], check=False)


def app_saved_dir() -> Path:
    """The packaged game's own Saved folder (the player's campaign, settings and logs)."""
    if WINDOWS:
        return Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "ASTRA" / "Saved"
    return Path.home() / "Library" / "Application Support" / "Epic" / "ASTRA" / "Saved"


def front_app() -> str:
    """The bundle path of the app in front on the Mac ("" elsewhere, or when it cannot be told)."""
    if sys.platform != "darwin":
        return ""
    try:
        import re
        asn = subprocess.run(["lsappinfo", "front"], capture_output=True, text=True, timeout=3).stdout.strip()
        out = subprocess.run(["lsappinfo", "info", "-only", "bundlepath", asn], capture_output=True, text=True, timeout=3).stdout
        m = re.search(r'"LSBundlePath"="([^"]+)"', out)
        return m.group(1) if m else ""
    except Exception:  # noqa: BLE001
        return ""


def user_idle_s() -> float:
    """Seconds since a person last touched the Mac's keyboard, mouse or trackpad (the harness's own keys do not count: they go through Slate)."""
    if sys.platform != "darwin":
        return 1e9
    try:
        out = subprocess.run(["ioreg", "-c", "IOHIDSystem"], capture_output=True, text=True, timeout=3).stdout
        for line in out.splitlines():
            if "HIDIdleTime" in line:
                return int(line.split("=")[-1].strip()) / 1e9
    except Exception:  # noqa: BLE001
        pass
    return 1e9


def campaign_arg(a: argparse.Namespace) -> list[str]:
    """The campaign the game begins: a new one (the default), the saved one (--continue), or none (--menu: the title menu, as a player sees it, with the OpenRouter key's page first)."""
    if getattr(a, "menu", False):
        return []
    return ["-astra_campaign=continue" if a.cont else "-astra_campaign=new"]


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
        kill_game()
        time.sleep(2.0)
    # the last game's connections linger a while in TIME_WAIT and the engine's listener cannot bind until they go
    for _ in range(120):
        if port_free():
            break
        time.sleep(0.5)
    PLAY_DIR.mkdir(parents=True, exist_ok=True)
    w, h = a.res.split("x")
    if a.app:
        # the packaged app as the player gets it (full screen on the Mac's own display, Retina, its own settings): a Development build has the
        # harness. No -ResX/-ResY here: the engine would keep them in the player's own GameUserSettings.ini
        app = Path(a.app).expanduser()
        if app.suffix == ".app":
            exe = next(iter(sorted((app / "Contents" / "MacOS").glob("*"))), None)
        else:
            exe = app / "ASTRA.exe" if app.is_dir() and WINDOWS else app          # (Windows: the package's folder, or ASTRA.exe itself)
        if exe is None or not exe.exists():
            print(f"no app at {app}")
            sys.exit(1)
        args = [str(exe), "-astra_harness", f"-astra_harness_port={PORT}", "-unattended"] + campaign_arg(a)
        if not a.player_save:
            # the tests keep their own Saved folder (Saved_Harness): a new campaign of the harness autosaved over the player's own war (4 Oct). Their
            # settings are copied there once, so a test sees the game as they do; their files are only read
            args.append("-saveddirsuffix=Harness")
            harness_saved = app_saved_dir().with_name("Saved_Harness")
            if not (harness_saved / "Config").exists() and (app_saved_dir() / "Config").exists():
                shutil.copytree(app_saved_dir() / "Config", harness_saved / "Config")
    else:
        args = [str(ENGINE), str(ROOT / "ASTRA.uproject"), a.map, "-game", "-windowed", f"-ResX={w}", f"-ResY={h}",
                "-astra_harness", f"-astra_harness_port={PORT}", "-unattended", "-NoVerifyGC"] + campaign_arg(a)
    if a.nomind:
        args.append("-astra_nomind")
    elif sys.platform != "win32":
        # the mind outlives the game (the next game connects to it): a mind started before the last change to its code would play the old code (5 Oct: a
        # playtest of new prompts ran on a mind started half an hour before them); the game starts a fresh one
        subprocess.run(["pkill", "-f", "astra-mind"], check=False)
        time.sleep(1.0)
    # someone may be using the Mac (5 Oct: the test window took the focus and the user's typing walked the Captain off the bridge): no splash (it brings
    # the app to the front), the game ignores the Mac's keyboard and mouse (AstraHarness: -astra_harness_input lets them through), and the app in front
    # is given the focus back once the game is up
    args.append("-nosplash")
    before = front_app()
    idle = user_idle_s()
    if idle < 120:
        print(f"the Mac is in use (last touched {idle:.0f} s ago): the game starts behind, and ignores its keyboard and mouse")
    if not a.sound:
        args.append("-nosound")
    if a.args:
        args += shlex.split(a.args)                     # (quoted values keep their spaces: --args '-ExecCmds="t.IdleWhenNotForeground 0"')
    log = open(PLAY_DIR / "game_stdout.log", "w")
    # (the game outlives this command: its own session on the Mac and Linux, detached with its own process group on Windows)
    detach = {"creationflags": subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP} if WINDOWS else {"start_new_session": True}
    subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, cwd=str(ROOT), **detach)
    t0 = time.time()
    while time.time() - t0 < 240:
        time.sleep(1.0)
        if alive():
            st = call("/state")
            if st.get("pawn", {}).get("class"):
                LAST.write_text(str(st.get("real", 0.0)))
                now = front_app()
                if before and now and now != before and not a.app:
                    subprocess.run(["open", "-a", before], check=False)          # (the focus back to whoever was working: the game keeps running behind)
                    print(f"focus given back to {Path(before).stem}")
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


def cmd_find(a: argparse.Namespace) -> None:
    r = call("/find", {"q": a.q})
    print(f"{r.get('found', 0)} found (nearest first)")
    for o in r.get("actors", []):
        print(f"  {o['dist_m']:7.1f} m  {o['loc_m']}  {o['name']}  [{o['class']}]  {o['tags']}"[:200])


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
    kill_game()
    print("game killed (it did not close by itself)")


def main() -> None:
    ap = argparse.ArgumentParser(prog="play.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("launch")
    p.add_argument("--map", default="/Game/ASTRA/Maps/L_Bridge")
    p.add_argument("--res", default="1600x900")
    p.add_argument("--continue", dest="cont", action="store_true")
    p.add_argument("--menu", action="store_true", help="no campaign: the title menu as a player sees it (the OpenRouter key's page first)")
    p.add_argument("--nomind", action="store_true")
    p.add_argument("--sound", action="store_true")
    p.add_argument("--app", default=None, help="the packaged app (Packaged/Mac/ASTRA.app or ~/Applications/ASTRA.app) instead of the editor binary")
    p.add_argument("--player-save", action="store_true", help="with --app: use the player's own Saved folder (their campaign!) instead of Saved_Harness")
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
    p = sub.add_parser("find", help="actors by tag, name or class (any case), nearest first: where things are, in metres")
    p.add_argument("q")
    p.set_defaults(fn=cmd_find)
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
