#!/usr/bin/env python3
"""MSVC shadow audit, run on the Mac: what the Mac build's clang lets pass and MSVC does not (docs/WINDOWS.md, "Il controllo di portabilita'").

This project builds with BuildSettingsVersion V7, where MSVC turns C4456 (a declaration hides a previous local), C4458 (hides a class member) and C4459
(hides a global) into errors. The Mac build's -Wshadow is the same family but not the same rule: it says nothing about a lambda's parameter that has the
name of a local or of a member of the enclosing class when the lambda does not capture it, nor about a constructor's parameter named like a field. MSVC
says something about both. So this replays the build tool's own compile commands (the .rsp files an editor build leaves in Intermediate/) for Source/ASTRA
with clang's wider shadow warnings, without -Werror and without code generation (-fsyntax-only: about a minute for the whole module), and prints the
declarations of the game's own files that MSVC would stop at:

  tools/shadow_audit.py                 every file the last build compiled
  tools/shadow_audit.py FILE.cpp ...    only these
  tools/shadow_audit.py -j 4            more at once (default 2: the machine is shared with the editor)
  tools/shadow_audit.py --all           also a member that hides an inherited one (-Wshadow-field: MSVC does not mind, it is only information)

The exit code is the number of findings. A finding is cured by renaming the inner name (a lambda's `Dots` -> `Set`): nothing else changes.
Needs the Mac toolchain and a built editor in this checkout (tools/ricompila.sh, or Build.sh ASTRAEditor Mac Development -Project=...).
"""
from __future__ import annotations

import argparse
import concurrent.futures
import os
import pathlib
import re
import shlex
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
GAME = str(ROOT / "Source/ASTRA") + "/"
UE_ROOT = pathlib.Path(os.environ.get("UE_ROOT", "/Users/Shared/Epic Games/UE_5.8"))
ENGINE_SOURCE = UE_ROOT / "Engine" / "Source"      # the build tool's include paths are relative to it
DEFAULT_CLANG = "/Applications/Xcode.app/Contents/Developer/Toolchains/XcodeDefault.xctoolchain/usr/bin/clang++"
DIAG = re.compile(r"^(?P<file>/[^:]+):(?P<line>\d+):(?P<col>\d+): (?P<kind>warning|error|note): (?P<msg>.*?)(?: \[(?P<flag>-W[\w-]+)\])?$")
# what MSVC stops at (-Wshadow itself is already an error in the Mac build); -Wshadow-field is information
MSVC_FLAGS = {"-Wshadow", "-Wshadow-uncaptured-local", "-Wshadow-field-in-constructor", "-Wshadow-ivar"}


def build_dirs() -> list[pathlib.Path]:
    """The folders with the compile commands of the game module: the editor build's, then the game's."""
    found = []
    for target in ("UnrealEditor", "ASTRA"):
        found += sorted(ROOT.glob(f"Intermediate/Build/Mac/*/{target}/*/ASTRA"))
    return [d for d in found if any(d.glob("*.o.rsp"))]


def clang() -> str:
    try:
        path = subprocess.run(["xcrun", "--find", "clang++"], capture_output=True, text=True, encoding="utf-8", timeout=30).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        path = ""
    return path if path and pathlib.Path(path).exists() else DEFAULT_CLANG


def command_for(rsp: pathlib.Path, compiler: str) -> list[str]:
    out: list[str] = []
    skip = False
    for token in shlex.split(rsp.read_text(encoding="utf-8")):
        if skip:
            skip = False
        elif token == "-o":
            skip = True
        elif token in ("-c", "-Werror", "-MD", "-fdiagnostics-color") or token.startswith("-MF"):
            pass
        else:
            out.append(token)
    return [compiler] + out + ["-fsyntax-only", "-Wshadow-all", "-Wno-error", "-fno-color-diagnostics", "-ferror-limit=0"]


def replay(command: list[str]) -> tuple[list[dict], str]:
    r = subprocess.run(command, cwd=ENGINE_SOURCE, capture_output=True, text=True, encoding="utf-8", errors="replace")
    hits: list[dict] = []
    for line in r.stderr.splitlines():
        m = DIAG.match(line)
        if not m:
            continue
        if m.group("kind") == "warning" and m.group("file").startswith(GAME):
            hits.append({"file": m.group("file")[len(GAME):], "line": m.group("line"), "col": m.group("col"), "msg": m.group("msg"), "flag": m.group("flag") or "", "hides": ""})
        elif m.group("kind") == "note" and hits and not hits[-1]["hides"] and "previous declaration" in m.group("msg"):
            where = m.group("file")
            hits[-1]["hides"] = f'{where[len(GAME):] if where.startswith(GAME) else where}:{m.group("line")}'
    return hits, ("" if r.returncode == 0 else r.stderr.strip()[-300:])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("files", nargs="*", help="source files (default: every file the last build compiled)")
    ap.add_argument("-j", type=int, default=2, help="compiles at once (default 2)")
    ap.add_argument("--all", action="store_true", help="also -Wshadow-field (information: MSVC does not stop at it)")
    args = ap.parse_args()
    dirs = build_dirs()
    if not dirs:
        print("no compile commands in Intermediate/Build/Mac: build the editor first (tools/ricompila.sh)", file=sys.stderr)
        return 1
    compiler = clang()
    if args.files:
        wanted = {pathlib.Path(f).name for f in args.files}
        rsps = [r for d in dirs[:1] for r in sorted(d.glob("*.o.rsp")) if r.name[: -len(".o.rsp")] in wanted]
    else:
        rsps = sorted(dirs[0].glob("*.o.rsp"))
    if not rsps:
        print("no compile command for those files in " + str(dirs[0].relative_to(ROOT)), file=sys.stderr)
        return 1
    t0 = time.time()
    seen: set[tuple[str, str, str, str]] = set()
    findings = failures = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.j)) as pool:
        for hits, tail in pool.map(lambda r: replay(command_for(r, compiler)), rsps):
            for h in hits:
                key = (h["file"], h["line"], h["col"], h["flag"])
                if key in seen or not (args.all or h["flag"] in MSVC_FLAGS):
                    continue
                seen.add(key)
                findings += h["flag"] in MSVC_FLAGS
                print(f'{h["file"]}:{h["line"]}:{h["col"]}: {h["msg"]} [{h["flag"]}]' + (f'  (hides the declaration at {h["hides"]})' if h["hides"] else ""))
            if tail:
                failures += 1
                print("!! a compile failed on its own: " + tail.splitlines()[-1], file=sys.stderr)
    print(f"\n{findings} finding(s) in {len(rsps)} compile commands, {time.time() - t0:.0f} s" + (f", {failures} compile failure(s)" if failures else ""))
    return findings


if __name__ == "__main__":
    sys.exit(main())
