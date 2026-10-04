"""What a first start needs on this machine, looked at and fetched: `python -m astra_mind.firstrun [--check] [--langs en,it]`.

The mind's Python environment (uv makes it: `uv sync --frozen`) and its data folder come first; this finishes the job: the speech models
the machine's engines need (Parakeet ONNX and faster-whisper where there is no Neural Engine helper, Pocket TTS for the languages asked for)
and a look at what the machine has (the key, a microphone, the system's voices). None of it is needed to start the game, since the mind
downloads what it lacks in the background (a first start included); this only makes the first start quiet: run it once, with a network,
before playing. `--check` looks and downloads nothing. The exit code is the number of things that stop the mind from working at all.
"""
from __future__ import annotations

import argparse
import importlib.util
import logging
import os
import platform
import sys
from pathlib import Path

from .env import CACHE, HOME, SAVED, load_env
from .stt import default_backends
from .tts import MODEL_FOR_LANG, SystemVoices, cache_status, fetch_models
from .voice_stt_backends import (SHERPA_MODEL_NAME, VOICE_MODELS, ParakeetBackend, SherpaParakeetBackend, faster_whisper_cached,
                                 fetch_faster_whisper_model, fetch_sherpa_model)

OK, WARN, FAIL = "ok  ", "warn", "FAIL"


def writable(path: Path) -> bool:
    """Can the mind keep files there (the folder is made when it is not there yet)?"""
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".astra-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def load_error(name: str) -> str:
    """Why a library that is installed does not load ("" when it does, or is not installed). The ones with native code fail to load rather than to
    import: on Windows, the Microsoft Visual C++ runtime that is missing is the usual reason."""
    if not has_module(name):
        return ""
    try:
        importlib.import_module(name)
        return ""
    except Exception as exc:  # noqa: BLE001 - OSError (a DLL), ImportError, anything a native library raises
        why = f"{type(exc).__name__}: {str(exc)[:160]}"
        if platform.system() == "Windows":
            why += " (the Microsoft Visual C++ Redistributable 2015-2022 x64 is probably missing: https://aka.ms/vs/17/release/vc_redist.x64.exe)"
        return why


def input_devices() -> list[str]:
    """The names of the microphones PortAudio sees (empty when there is none, or PortAudio does not load)."""
    try:
        import sounddevice as sd
        return [str(d["name"]) for d in sd.query_devices() if d["max_input_channels"] > 0]
    except Exception:  # noqa: BLE001
        return []


def look() -> list[tuple[str, str]]:
    """What this machine has, as (level, line)."""
    out: list[tuple[str, str]] = []
    out.append((OK, f"{platform.system()} {platform.release()} {platform.machine()}, Python {platform.python_version()}"))
    for label, folder in (("data", HOME), ("saved games", SAVED), ("caches", CACHE)):
        out.append((OK, f"{label}: {folder}") if writable(folder) else (FAIL, f"{label}: {folder} cannot be written to"))
    key = bool(load_env().get("OPENROUTER_API_KEY"))
    out.append((OK, "the crew's key (OPENROUTER_API_KEY) is set") if key else
               (FAIL, f"the crew cannot think without its key: put OPENROUTER_API_KEY=... in {HOME / '.env'}"))
    for mod in ("numpy", "scipy", "soundfile", "websockets", "httpx", "lingua", "pocket_tts", "torch"):
        out.append((OK, f"{mod} is installed") if has_module(mod) else (FAIL, f"{mod} is not installed (uv sync --frozen)"))
    for mod in ("torch", "onnxruntime"):
        why = load_error(mod)
        if why:
            out.append((FAIL, f"{mod} does not load: {why}"))
    devices = input_devices()
    out.append((OK, f"microphone: {', '.join(devices[:3])}{' ...' if len(devices) > 3 else ''}") if devices else
               (WARN, "no microphone found (or PortAudio did not load): the Captain can only type"))
    engines = [b.name for b in default_backends(os.environ.get("ASTRA_STT", ""))]
    out.append((OK, f"speech recognition engines: {', '.join(engines)}") if engines else
               (WARN, "no speech recognition engine here: the Captain can only type (see --fetch / ASTRA_STT)"))
    if SherpaParakeetBackend.usable() and not SherpaParakeetBackend.available():
        out.append((WARN, f"the Parakeet ONNX model is not downloaded yet ({VOICE_MODELS / SHERPA_MODEL_NAME}, about 490 MB)"))
    if has_module("faster_whisper") and not faster_whisper_cached():
        out.append((WARN, "faster-whisper's model is not downloaded yet (about 480 MB)"))
    cached = {lang: n for lang, (model, n) in cache_status().items() if model}
    for lang, n in cached.items():
        out.append((OK, f"voice {lang}: model cached, {n} voices"))
    if not cached:
        out.append((WARN, "no voice model is downloaded yet (about 440 MB a language): the system's own voices say the crew's lines until it is"))
    system_voice = SystemVoices().pick("en")
    out.append((OK, f"the system's own voice for English: {system_voice}") if system_voice else (WARN, "the system has no voice of its own for English"))
    return out


def fetch(langs: list[str], whisper: bool, tts: bool) -> None:
    """Download what this machine's engines need and the voice models of `langs`; each piece is left alone when it is already here."""
    if SherpaParakeetBackend.usable() and not SherpaParakeetBackend.available() and not ParakeetBackend.available():
        print(f"downloading the Parakeet ONNX model (about 490 MB) into {VOICE_MODELS} ...", flush=True)
        print("  ->", fetch_sherpa_model())
    if whisper and has_module("faster_whisper") and not faster_whisper_cached():
        print("downloading faster-whisper's model (about 480 MB) ...", flush=True)
        print("  ->", fetch_faster_whisper_model())
    if tts:
        print(f"downloading the voice models for {', '.join(langs)} (about 440 MB each) ...", flush=True)
        fetch_models(langs)


def main() -> int:
    ap = argparse.ArgumentParser(prog="python -m astra_mind.firstrun", description=__doc__.split("\n\n")[0])
    ap.add_argument("--check", action="store_true", help="look only: download nothing")
    ap.add_argument("--langs", default="en", help="voice models to download (default: en; any of %s)" % ",".join(MODEL_FOR_LANG))
    ap.add_argument("--no-whisper", action="store_true", help="skip faster-whisper's model (the all-languages second opinion)")
    ap.add_argument("--no-tts", action="store_true", help="skip the voice models")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if not args.check:
        fetch([lg for lg in args.langs.split(",") if lg in MODEL_FOR_LANG] or ["en"], whisper=not args.no_whisper, tts=not args.no_tts)
    problems = 0
    for level, line in look():
        print(f"[{level}] {line}")
        problems += level == FAIL
    print("\nready" if not problems else f"\n{problems} thing(s) to fix before the crew can work")
    return problems


if __name__ == "__main__":
    sys.exit(main())
