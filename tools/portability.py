#!/usr/bin/env python3
"""Portability check: flags Mac-only (or Windows-hostile) code in Source/, Plugins/ and mind/, so that the project stays portable
(docs/WINDOWS.md, "Il controllo di portabilita'"). Runs anywhere, with nothing but Python 3.11+.

  tools/portability.py                the check: every finding that is not allowed, one per line; the exit code is their number
  tools/portability.py --allowed      also list what the allowlist lets through, with the reason
  tools/portability.py --lock         also check that the mind's locked dependencies install for Windows x64 (needs uv: no network, no build)
  tools/portability.py --selftest     the rules against samples they must and must not catch
  tools/portability.py PATH ...       only these files or folders

A spot that is Mac-only (or POSIX-only) on purpose carries `portable-ok: why` in a comment on its own line or the line above, and the
`why` says where the other systems are served. Whole files or folders that are Mac-only by design are in ALLOW_PATHS below. Comments and
docstrings are not code: a Mac path in one is not a finding.

What it looks for (RULES): hard-coded Mac folders; shells and shell-only tools (zsh, osascript, pgrep...); Apple frameworks; PLATFORM_MAC and
Darwin checks (each needs its alternative named); POSIX-only Python (SIGHUP, add_signal_handler, fork, fcntl...); text files opened without an
encoding (Windows reads them in its code page); os.rename (fails over an existing file on Windows); POSIX roots (/tmp, /dev/null); $HOME;
POSIX-only headers and GCC-only constructs in C++; an #include whose letter case is not the file's (Linux). And three structure checks:
Mac-only plugins are allow-listed to the Mac in the .uproject and the .uplugin and no game code includes them; every Mac engine setting has a
Windows twin or is named Mac-only.
"""
from __future__ import annotations

import argparse
import fnmatch
import io
import json
import re
import subprocess
import sys
import tempfile
import tokenize
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCAN = ("Source", "Plugins", "mind")
SKIP_DIRS = {".venv", "__pycache__", ".cache", ".ruff_cache", ".build", ".swiftpm", "node_modules", "Intermediate", "Binaries", "Saved", ".git"}
LANGS = {".cpp": "cpp", ".h": "cpp", ".inl": "cpp", ".cs": "cpp", ".mm": "cpp", ".m": "cpp", ".py": "py", ".swift": "swift", ".sh": "sh"}
MARKER = "portable-ok"

# Whole files or folders that are Mac-only (or developer-only) by design: (glob, rule or "*", why). The glob is matched against the path from the repository root.
ALLOW_PATHS: list[tuple[str, str, str]] = [
    ("Plugins/AstraMetalFX/*", "*", "the MetalFX upscaler: a Mac-only plugin, allow-listed to the Mac in the .uproject and the .uplugin (structure check below); other systems keep TSR"),
    ("mind/stt_server/*", "*", "the Swift helper for Parakeet on the Neural Engine: Apple Silicon only; the portable engines (sherpa-onnx, faster-whisper) serve every other machine"),
    ("Source/ASTRA/AstraMindLaunchCommandlet.cpp", "*", "the launcher's self-test: made-up Mac, Windows and Linux machines, a shell for the probe"),
    ("Source/ASTRA/AstraMindLaunch.cpp", "mac-path", "the launcher's data: where each system keeps its data and its tools (the Mac's among them, the others beside it)"),
    ("Source/ASTRA/AstraMindLaunch.cpp", "tmp-path", "the launcher's data: the folders each system's tools are usually installed in"),
    ("Source/ASTRA/AstraMindLaunch.cpp", "platform-macro", "ThisHost(): which of the launcher's systems this build is"),
    ("Source/ASTRA/AstraMindLaunch.h", "platform-macro", "ThisHost(): which of the launcher's systems this build is"),
    ("mind/bench/portable_unit.py", "*", "the tests of portability: they name the Mac's and Windows' folders and signals on purpose"),
    ("mind/bench/*", "tmp-path", "developer benches: scratch files in /tmp"),
    ("mind/bench/*", "mac-say", "developer benches: the crew's `say` tool by name, and the Mac's voices to make a test corpus"),
    ("mind/bench/*", "locale-text-io", "developer benches: their files are ASCII and are read where they are written"),
    ("mind/bench/*", "mac-path", "developer benches: the engine's own folder on the developer's machine (UE_ROOT / ASTRA_UE_CMD override it)"),
    ("mind/astra_mind/bench/*", "*", "developer benches"),
]


@dataclass(frozen=True)
class Rule:
    id: str
    langs: frozenset[str]
    pattern: re.Pattern[str]
    why: str


def rule(id: str, langs: str, pattern: str, why: str, flags: int = 0) -> Rule:
    return Rule(id, frozenset(langs.split()), re.compile(pattern, flags), why)


RULES: list[Rule] = [
    rule("mac-path", "cpp py swift sh",
         r"/Users/|/opt/homebrew|/System/Library|\.app/Contents|Contents/(?:MacOS|Resources)|~/Library|/Library/|Library/Application Support|/usr/local/(?:bin|lib)\b",
         "a Mac folder written into the code: ask the system where it is (FPlatformProcess, Path.home(), an environment variable) or name it per system"),
    rule("shell", "cpp py sh",
         r"/bin/(?:zsh|bash|sh|csh)\b|\bzsh\s+-l|\bos\.system\(|\bshell\s*=\s*True|\bPopen\([^)]*\bshell\b",
         "a shell does not exist the same everywhere: start the program itself, with its arguments and its environment"),
    rule("mac-tool", "cpp py",
         r"""["'](?:afplay|osascript|pbcopy|pbpaste|screencapture|launchctl|codesign|xcrun|PlistBuddy|hdiutil|sips|mdfind|caffeinate|pgrep|pkill|killall|lsof)["']""",
         "a program that only the Mac (or only POSIX) has"),
    rule("mac-say", "py", r"""\[\s*["'](?:say|open)["']\s*,""",
         "macOS's `say` or `open`: needs the other systems' way (SAPI for the voices) next to it"),
    rule("mac-framework", "cpp",
         r"\b(?:NSString|NSBundle|NSWorkspace|NSApplication|NSFileManager|CFBundle|MTL[A-Z][A-Za-z]+|CoreML|CoreAudio|AVFoundation)\b|@autoreleasepool|#import\b|<(?:Cocoa|Metal|MetalFX|Foundation|AppKit)/",
         "an Apple framework: only for a Mac-only plugin or behind PLATFORM_MAC with a portable alternative"),
    rule("mac-framework-py", "py", r"^\s*(?:import|from)\s+(?:objc|AppKit|Foundation|Quartz|CoreFoundation|coremltools|mlx|rumps)\b",
         "an Apple library: behind a platform check, with the portable engine next to it", re.M),
    rule("platform-macro", "cpp", r"\b(?:PLATFORM_MAC|PLATFORM_APPLE|PLATFORM_IOS|PLATFORM_TVOS|__APPLE__|TARGET_OS_MAC)\b",
         "a Mac-only branch: it needs its portable alternative, named in a `portable-ok: ...` comment"),
    rule("darwin-check", "py", r"""sys\.platform\s*==\s*["']darwin["']|platform\.system\(\)\s*(?:==|!=)\s*["']Darwin["']""",
         "a Mac branch: it needs its portable alternative, named in a `portable-ok: ...` comment"),
    rule("posix-only", "py",
         r"\bsignal\.(?:SIGHUP|SIGUSR1|SIGUSR2|SIGALRM|SIGQUIT|SIGPIPE|SIGCHLD)\b|\.add_signal_handler\(|\bos\.(?:fork|forkpty|getuid|geteuid|getgid|setsid|killpg|getpgid|mkfifo|nice|uname|chown|lchown)\(|"
         r"^\s*(?:import|from)\s+(?:fcntl|termios|pty|tty|grp|pwd|resource|syslog)\b|\bsignal\.alarm\(",
         "does not exist on Windows (host.install_stop_handlers has the signals each system has)", re.M),
    rule("rename", "py", r"\bos\.rename\(", "fails on Windows when the target exists: os.replace"),
    rule("tmp-path", "cpp py", r"""["'](?:/tmp/|/var/|/dev/null|/etc/|/usr/|/opt/|/home/)""",
         "a POSIX folder: tempfile, os.devnull, the user's folders by their system calls"),
    rule("env-home", "cpp py", r"""GetEnvironmentVariable\(\s*TEXT\(\s*"HOME"\s*\)\s*\)|os\.environ(?:\[|\.get\()\s*["']HOME["']|\$HOME\b""",
         "HOME does not exist on Windows (USERPROFILE): Path.home(), FPlatformProcess::UserSettingsDir()"),
    rule("posix-header", "cpp", r"#\s*include\s*<(?:unistd|sys/[a-z_]+|pthread|dlfcn|dirent|mach/[a-z_/]+|libproc|fcntl|termios|arpa/inet|netinet/[a-z_]+|poll|signal)\.h>",
         "a POSIX header: the engine's own platform layer has what is needed"),
    rule("gcc-only", "cpp", r"\b__attribute__\b|\b__builtin_[a-z_]+|\b__restrict__\b|\btypeof\s*\(|\b__asm__\b",
         "does not compile with MSVC"),
]


# ------------------------------------------------------------------------------------------------------------------ masking: comments and docstrings are not code
def _blank(out: list[str], a: int, b: int) -> None:
    for i in range(a, min(b, len(out))):
        if out[i] != "\n":
            out[i] = " "


def mask_cpp(text: str) -> str:
    """The text with its comments blanked (same length, same lines); strings are kept."""
    out = list(text)
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c == "/" and text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            _blank(out, i, j)
            i = j
        elif c == "/" and text.startswith("/*", i):
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            _blank(out, i, j)
            i = j
        elif c in "\"'":
            i += 1
            while i < n and text[i] != c and text[i] != "\n":
                i += 2 if text[i] == "\\" else 1
            i += 1
        else:
            i += 1
    return "".join(out)


def mask_py(text: str) -> str:
    """The text with its comments and docstrings blanked (same length, same lines); other strings are kept."""
    out = list(text)
    starts = [0]
    for line in text.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    toks: list[tokenize.TokenInfo] = []
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return text
    significant = [t for t in toks if t.type not in (tokenize.COMMENT, tokenize.NL)]
    for k, t in enumerate(significant):
        if t.type != tokenize.STRING:
            continue
        before = significant[k - 1].type if k else tokenize.NEWLINE
        after = significant[k + 1].type if k + 1 < len(significant) else tokenize.NEWLINE
        if before in (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT) and after == tokenize.NEWLINE:
            _blank(out, starts[t.start[0] - 1] + t.start[1], starts[t.end[0] - 1] + t.end[1])
    for t in toks:
        if t.type == tokenize.COMMENT:
            _blank(out, starts[t.start[0] - 1] + t.start[1], starts[t.end[0] - 1] + t.end[1])
    return "".join(out)


def masked(text: str, lang: str) -> str:
    return mask_cpp(text) if lang == "cpp" else mask_py(text) if lang == "py" else text


# ------------------------------------------------------------------------------------------------------------------ findings
@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    text: str
    why: str
    allowed: str = ""          # "" for a finding; else why it is let through

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: [{self.rule}] {self.text.strip()[:140]}  -- {self.why}" + (f"  (allowed: {self.allowed})" if self.allowed else "")


def balanced_args(text: str, open_paren: int) -> str:
    """The text between the parenthesis at `open_paren` and its mate (to the end when there is none)."""
    depth, i, n, quote = 0, open_paren, len(text), ""
    while i < n:
        c = text[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = ""
        elif c in "\"'":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren + 1:i]
        i += 1
    return text[open_paren + 1:]


def locale_io(code: str) -> list[tuple[int, str]]:
    """(offset, text) of text files opened or written without an encoding (Python)."""
    hits: list[tuple[int, str]] = []
    for m in re.finditer(r"\.(?:read_text|write_text)\(", code):
        if "encoding" not in balanced_args(code, m.end() - 1):
            hits.append((m.start(), m.group(0)))
    for m in re.finditer(r"(?<![\w.])open\(", code):
        args = balanced_args(code, m.end() - 1)
        binary = re.search(r"""["'][rwaxt+]*b[rwaxt+]*["']""", args) is not None
        if not binary and "encoding" not in args:
            hits.append((m.start(), "open("))
    return hits


def include_case(text: str, path: Path, project_files: dict[str, str]) -> list[tuple[int, str]]:
    """(offset, text) of `#include "X"` whose letter case is not the file's (a project file that exists under another case)."""
    hits = []
    for m in re.finditer(r'^\s*#\s*include\s*"([^"]+)"', text, re.M):
        want = m.group(1).replace("\\", "/")
        exact = project_files.get(want.lower())
        if exact is not None and exact != want and not exact.endswith("/" + want):
            hits.append((m.start(), m.group(0).strip()))
    return hits


def index_project_files() -> dict[str, str]:
    """lower-case relative path -> its real spelling, for every header of Source/ and the plugins' Public/Private folders (matched by the end of the path)."""
    files: dict[str, str] = {}
    for base in ("Source", "Plugins"):
        for p in (ROOT / base).rglob("*"):
            if p.suffix in (".h", ".inl", ".hpp") and not (set(p.parts) & SKIP_DIRS):
                files[p.name.lower()] = p.name
    return files


def allowed_by_path(rel: str, rule_id: str) -> str:
    for glob, rid, why in ALLOW_PATHS:
        if fnmatch.fnmatch(rel, glob) and rid in ("*", rule_id):
            return why
    return ""


def marker_near(lines: list[str], line_no: int) -> str:
    for idx in (line_no - 1, line_no - 2):
        if 0 <= idx < len(lines) and MARKER in lines[idx]:
            m = re.search(MARKER + r":?\s*(.*)", lines[idx])
            return (m.group(1).strip(" */#-") if m else "") or "marked"
    return ""


def scan_text(rel: str, text: str, lang: str, project_files: dict[str, str] | None = None) -> list[Finding]:
    code = masked(text, lang)
    lines = text.splitlines()
    out: list[Finding] = []

    def add(offset: int, rule_id: str, why: str) -> None:
        line = code.count("\n", 0, offset) + 1
        excerpt = lines[line - 1] if line - 1 < len(lines) else ""
        out.append(Finding(rel, line, rule_id, excerpt, why, marker_near(lines, line) or allowed_by_path(rel, rule_id)))

    for r in RULES:
        if lang in r.langs:
            for m in r.pattern.finditer(code):
                add(m.start(), r.id, r.why)
    if lang == "py":
        for off, _ in locale_io(code):
            add(off, "locale-text-io", "a text file opened without encoding= is read in the system's code page on Windows: say encoding=\"utf-8\"")
    if lang == "cpp" and project_files is not None:
        for off, _ in include_case(code, Path(rel), project_files):
            add(off, "include-case", "the file's name has another letter case (Linux tells them apart)")
    return out


def scan_files(paths: list[Path]) -> list[Finding]:
    project_files = index_project_files()
    found: list[Finding] = []
    for p in paths:
        lang = LANGS.get(p.suffix)
        if lang is None:
            continue
        rel = p.resolve().relative_to(ROOT).as_posix()
        try:
            text = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        found += scan_text(rel, text, lang, project_files)
    return found


def collect(args: list[str]) -> list[Path]:
    roots = [Path(a).resolve() for a in args] if args else [ROOT / d for d in SCAN]
    files: list[Path] = []
    for r in roots:
        if r.is_file():
            files.append(r)
        elif r.is_dir():
            files += [p for p in sorted(r.rglob("*")) if p.is_file() and not (set(p.relative_to(r).parts[:-1]) & SKIP_DIRS)]
    return files


# ------------------------------------------------------------------------------------------------------------------ structure checks
MAC_ONLY_ENGINE_KEYS = {
    "r.Streaming.PoolSize": "the Mac's unified memory: a PC's texture pool follows its VRAM (70 %)",
    "r.ShaderCompiler.MemoryLimit": "the Mac's 16 GB shared with the GPU",
    "PoolSizeVRAMPercentage": "the Mac's unified memory",
    "r.AstraMetalFX": "the MetalFX plugin exists on the Mac only",
}


def ini_keys(path: Path) -> dict[str, str]:
    keys: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and line[0] not in ";[#" and "=" in line:
            k, v = line.split("=", 1)
            keys[k.strip().lstrip("+-.")] = v.strip()
    return keys


def structure_findings(root: Path = ROOT) -> list[Finding]:
    out: list[Finding] = []

    def bad(path: str, rule_id: str, text: str, why: str) -> None:
        out.append(Finding(path, 0, rule_id, text, why))

    # Mac-only plugins (the ones with Objective-C++ or Apple frameworks) are Mac-only everywhere they are declared
    uproject = json.loads((root / "ASTRA.uproject").read_text(encoding="utf-8"))
    declared = {p["Name"]: p for p in uproject.get("Plugins", [])}
    for plugin in sorted((root / "Plugins").glob("*/*.uplugin")):
        folder = plugin.parent
        sources = [f for f in folder.rglob("*") if f.suffix in (".cpp", ".h", ".mm", ".cs")]
        if not (any(f.suffix == ".mm" for f in sources) or any("MetalFX" in f.read_text(encoding="utf-8", errors="replace")[:4000] for f in sources)):
            continue
        name = plugin.stem
        desc = json.loads(plugin.read_text(encoding="utf-8"))
        rel = plugin.relative_to(root).as_posix()
        if not all([m.lower() for m in mod.get("PlatformAllowList", [])] == ["mac"] for mod in desc.get("Modules", [])):
            bad(rel, "structure", name, 'a Mac-only plugin: every module needs "PlatformAllowList": ["Mac"]')
        if [p.lower() for p in desc.get("SupportedTargetPlatforms", [])] != ["mac"]:
            bad(rel, "structure", name, 'a Mac-only plugin: "SupportedTargetPlatforms": ["Mac"]')
        entry = declared.get(name)
        if entry is None or [p.lower() for p in entry.get("PlatformAllowList", [])] != ["mac"]:
            bad("ASTRA.uproject", "structure", name, 'a Mac-only plugin must be listed with "PlatformAllowList": ["Mac"], or Windows builds it')
        for src in (root / "Source").rglob("*"):
            if src.suffix in (".cpp", ".h", ".cs") and f'"{name}' in src.read_text(encoding="utf-8", errors="replace"):
                bad(src.relative_to(root).as_posix(), "structure", name, "game code includes a Mac-only plugin: a Windows build would not find it")
    # every engine setting of the Mac has its twin on Windows, or is named Mac-only here
    mac, win = root / "Config/Mac/MacEngine.ini", root / "Config/Windows/WindowsEngine.ini"
    if mac.exists():
        if not win.exists():
            bad("Config/Windows/WindowsEngine.ini", "config-parity", "(missing)", "the Mac has Config/Mac/MacEngine.ini: Windows needs its twin")
        else:
            have = ini_keys(win)
            for key in sorted(ini_keys(mac)):
                if key not in have and key not in MAC_ONLY_ENGINE_KEYS:
                    bad("Config/Mac/MacEngine.ini", "config-parity", key, "no twin in Config/Windows/WindowsEngine.ini: add it there, or name it Mac-only in tools/portability.py")
    return out


# ------------------------------------------------------------------------------------------------------------------ the lock
def lock_findings() -> list[Finding]:
    """Does every locked dependency of the mind install for Windows x64 / CPython 3.13 without building anything? (uv resolves the lock for that
    system on its own: a package with no Windows wheel fails it, the day it is added.) Windows on ARM is not a target: ctranslate2 has no wheel."""
    mind = ROOT / "mind"
    try:
        exported = subprocess.run(["uv", "export", "--frozen", "--no-hashes", "--no-emit-project"], cwd=mind, capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        return [Finding("mind/uv.lock", 0, "lock", "uv", f"uv could not be run ({exc}): install it to check the lock")]
    if exported.returncode != 0:
        return [Finding("mind/uv.lock", 0, "lock", "uv export", exported.stderr.strip()[-300:])]
    with tempfile.TemporaryDirectory() as td:
        req = Path(td) / "requirements.txt"
        req.write_text(exported.stdout, encoding="utf-8")
        r = subprocess.run(["uv", "pip", "install", "--dry-run", "--no-deps", "--only-binary", ":all:", "--python-platform", "x86_64-pc-windows-msvc",
                            "--python-version", "3.13", "-r", str(req)], cwd=mind, capture_output=True, text=True, timeout=300)
    if r.returncode != 0:
        return [Finding("mind/uv.lock", 0, "lock", "Windows x64", (r.stderr.strip().splitlines() or ["uv failed"])[-1][:300])]
    return []


# ------------------------------------------------------------------------------------------------------------------ self-test
SAMPLES: list[tuple[str, str, str, bool]] = [
    # (language, source, rule, must it be found?)
    ("cpp", 'FPlatformProcess::CreateProc(TEXT("/bin/zsh"), *Cmd, true, true, true, nullptr, 0, nullptr, nullptr);', "shell", True),
    ("cpp", '// the old way ran /bin/zsh -lc here\nint X = 0;', "shell", False),
    ("cpp", 'const FString Home = Env / TEXT("Library/Application Support/ASTRA");', "mac-path", True),
    ("cpp", '/* the packaged game lives in /Users/me/Applications */ int X;', "mac-path", False),
    ("cpp", '#if PLATFORM_MAC\nint X;\n#endif', "platform-macro", True),
    ("cpp", '#if PLATFORM_MAC // portable-ok: Windows has WindowsGameUserSettings.ini\nint X;\n#endif', "platform-macro", True),
    ("cpp", '#include <unistd.h>', "posix-header", True),
    ("cpp", 'int X = __builtin_popcount(Y);', "gcc-only", True),
    ("cpp", 'NSString* S = [NSString stringWithUTF8String:"x"];', "mac-framework", True),
    ("cpp", 'FString H = FPlatformMisc::GetEnvironmentVariable(TEXT("HOME")) / TEXT("x");', "env-home", True),
    ("cpp", 'FString H = FPlatformMisc::GetEnvironmentVariable(TEXT("LOCALAPPDATA"));', "env-home", False),
    ("py", 'subprocess.run(["say", "-v", voice, text])', "mac-say", True),
    ("py", 'msg = {"open": True, "say": "hello"}', "mac-say", False),
    ("py", 'subprocess.run(["osascript", "-e", "beep"])', "mac-tool", True),
    ("py", 'if sys.platform == "darwin":\n    pass', "darwin-check", True),
    ("py", 'for sig in (signal.SIGTERM, signal.SIGHUP):\n    pass', "posix-only", True),
    ("py", 'loop.add_signal_handler(sig, cb)', "posix-only", True),
    ("py", 'for name in ("SIGTERM", "SIGHUP"):\n    sig = getattr(signal, name, None)', "posix-only", False),
    ("py", 'import fcntl', "posix-only", True),
    ("py", 'text = path.read_text()', "locale-text-io", True),
    ("py", 'text = path.read_text(encoding="utf-8")', "locale-text-io", False),
    ("py", 'path.write_text(json.dumps(data, indent=1), encoding="utf-8")', "locale-text-io", False),
    ("py", 'path.write_text(json.dumps(data, indent=1))', "locale-text-io", True),
    ("py", 'with open(path, "w") as f:\n    f.write(x)', "locale-text-io", True),
    ("py", 'with open(path, "w", encoding="utf-8") as f:\n    f.write(x)', "locale-text-io", False),
    ("py", 'with open(path, "rb") as f:\n    data = f.read()', "locale-text-io", False),
    ("py", 'with open(\n    path, "w",\n    encoding="utf-8") as f:\n    pass', "locale-text-io", False),
    ("py", 'wave.open(name, "wb")', "locale-text-io", False),
    ("py", 'os.rename(a, b)', "rename", True),
    ("py", 'os.replace(a, b)', "rename", False),
    ("py", 'out = "/tmp/astra/out.json"', "tmp-path", True),
    ("py", '"""the docstring says /tmp/ and /Users/me and osascript"""\nx = 1', "tmp-path", False),
    ("py", 'x = 1  # /Users/me is the lead\n', "mac-path", False),
    ("py", 'p = Path("/Users/me/ASTRA")', "mac-path", True),
    ("py", 'home = os.environ.get("HOME")', "env-home", True),
]


def structure_selftest() -> int:
    """The structure checks against small made-up trees: a clean one, and one with each mistake."""
    failures = 0

    def tree(td: Path, *, plugin_modules: str = '[{"Name": "MacThing", "Type": "Runtime", "PlatformAllowList": ["Mac"]}]', supported: str = '["Mac"]',
             entry: str = '{"Name": "MacThing", "Enabled": true, "PlatformAllowList": ["Mac"]}', game_code: str = "int X;", mac_ini: str = "r.A=1\n", win_ini: str | None = "r.A=1\n") -> Path:
        (td / "Plugins/MacThing/Source").mkdir(parents=True)
        (td / "Plugins/MacThing/Source/Bridge.mm").write_text("// metal\n", encoding="utf-8")
        (td / "Plugins/MacThing/MacThing.uplugin").write_text(f'{{"Modules": {plugin_modules}, "SupportedTargetPlatforms": {supported}}}', encoding="utf-8")
        (td / "ASTRA.uproject").write_text(f'{{"Plugins": [{entry}]}}', encoding="utf-8")
        (td / "Source/ASTRA").mkdir(parents=True)
        (td / "Source/ASTRA/Game.cpp").write_text(game_code, encoding="utf-8")
        (td / "Config/Mac").mkdir(parents=True)
        (td / "Config/Mac/MacEngine.ini").write_text(mac_ini, encoding="utf-8")
        if win_ini is not None:
            (td / "Config/Windows").mkdir(parents=True)
            (td / "Config/Windows/WindowsEngine.ini").write_text(win_ini, encoding="utf-8")
        return td

    cases = [
        ("a clean tree has nothing to say", {}, 0),
        ("a Mac-only plugin whose module is not allow-listed to the Mac", {"plugin_modules": '[{"Name": "MacThing", "Type": "Runtime"}]'}, 1),
        ("... whose descriptor supports every platform", {"supported": '["Mac", "Win64"]'}, 1),
        ("... that the .uproject does not allow-list", {"entry": '{"Name": "MacThing", "Enabled": true}'}, 1),
        ("... that game code includes", {"game_code": '#include "MacThingModule.h"\n'}, 1),
        ("a Mac engine setting with no Windows twin", {"mac_ini": "r.A=1\nr.B=2\n"}, 1),
        ("... unless it is named Mac-only", {"mac_ini": "r.A=1\nr.Streaming.PoolSize=2000\n"}, 0),
        ("no Windows engine file at all", {"win_ini": None}, 1),
    ]
    for label, kw, want in cases:
        with tempfile.TemporaryDirectory() as td:
            got = len(structure_findings(tree(Path(td), **kw)))
        ok = got == want
        failures += not ok
        print(("ok   " if ok else "FAIL ") + f"structure       {label}" + ("" if ok else f" (found {got}, wanted {want})"))
    return failures


def selftest() -> int:
    failures = 0
    for lang, source, rule_id, must in SAMPLES:
        hits = [f for f in scan_text("sample." + ("cpp" if lang == "cpp" else "py"), source, lang) if f.rule == rule_id]
        ok = bool(hits) == must
        failures += not ok
        print(("ok   " if ok else "FAIL ") + f"{rule_id:15} {'finds' if must else 'passes'}: {source.splitlines()[0][:80]!r}")
    marked = [f for f in scan_text("sample.cpp", SAMPLES[5][1], "cpp") if f.rule == "platform-macro"]
    ok = bool(marked) and all(f.allowed for f in marked)
    failures += not ok
    print(("ok   " if ok else "FAIL ") + "a `portable-ok` comment on the line lets it through, with its reason")
    failures += structure_selftest()
    print(f"\n{'all samples behave' if not failures else str(failures) + ' FAILED'}")
    return failures


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("paths", nargs="*", help="files or folders (default: Source/, Plugins/, mind/)")
    ap.add_argument("--allowed", action="store_true", help="also list what the allowlist lets through")
    ap.add_argument("--lock", action="store_true", help="also check the mind's locked dependencies for Windows x64 (uv)")
    ap.add_argument("--selftest", action="store_true", help="run the rules against samples")
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    findings = scan_files(collect(args.paths))
    if not args.paths:
        findings += structure_findings()
    if args.lock:
        findings += lock_findings()
    bad = [f for f in findings if not f.allowed]
    if args.allowed:
        for f in findings:
            if f.allowed:
                print(f)
    for f in bad:
        print(f)
    print(f"\n{len(bad)} finding(s) not allowed, {len(findings) - len(bad)} allowed" + ("" if bad else ": the code is portable as far as this check can tell"))
    return len(bad)


if __name__ == "__main__":
    sys.exit(main())
