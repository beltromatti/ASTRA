"""Offline tests of what makes the mind portable (docs/WINDOWS.md): the door and the log the game gives it, the signals each system has, which
speech engines a machine gets, the system voices of Windows, the locked dependencies for Windows. Nothing here needs the network, a model or a
microphone, and nothing spends anything.

    cd mind && .venv/bin/python -m unittest bench.portable_unit -v

Two more groups need the machine's time and are asked for by name:
    ASTRA_TEST_BOOT=1            starts the real mind (`astra_mind.server`) the way the game does, on a free port, and asks it to stop
    ASTRA_TEST_PORTABLE_REAL=1   Pocket TTS speaks a sentence and the portable engines (the ones of a Windows PC) write it back
                                 (ASTRA_VOICE_MODELS may point at a folder that has, or will get, the Parakeet ONNX model)
"""
from __future__ import annotations

import asyncio
import base64
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
import soundfile as sf

from astra_mind import host
from astra_mind import stt as stt_module
from astra_mind import tts as tts_module
from astra_mind import voice_stt_backends as backends_module
from astra_mind.voice_stt_backends import FasterWhisperBackend, ParakeetBackend, SherpaParakeetBackend, WhisperKitBackend

MIND = Path(__file__).resolve().parents[1]


def run_python(code: str, env: dict[str, str] | None = None, timeout: float = 60.0) -> subprocess.CompletedProcess:
    """A fresh interpreter in the mind's folder (what hijacks stdout and signals must not do it to the test runner)."""
    full = {**os.environ, **(env or {})}
    return subprocess.run([sys.executable, "-c", code], cwd=MIND, env=full, capture_output=True, text=True, timeout=timeout)


class TestHost(unittest.TestCase):
    def test_port_default_and_override(self) -> None:
        self.assertEqual(host.mind_port({}), 8765)
        self.assertEqual(host.mind_port({"ASTRA_MIND_PORT": "18765"}), 18765)
        self.assertEqual(host.mind_port({"ASTRA_MIND_PORT": " 9000 "}), 9000)

    def test_a_port_that_is_not_one_falls_back(self) -> None:
        for bad in ("", "abc", "0", "80", "70000", "-5", "8765.5"):
            self.assertEqual(host.mind_port({"ASTRA_MIND_PORT": bad}), 8765, bad)

    def test_the_log_gets_python_and_native_output_and_stdout_stays_quiet(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "Logs" / "astra-mind.log"             # (the folder does not exist yet: the mind makes it)
            r = run_python("import os, sys, logging\n"
                           "from astra_mind import host\n"
                           "host.redirect_output_to_log()\n"
                           "print('from print: caffè → ·')\n"
                           "logging.basicConfig(level=logging.INFO, format='%(name)s %(message)s')\n"
                           "logging.getLogger('astra.test').info('from logging')\n"
                           "os.write(2, b'from a native library\\n')\n"
                           "os.write(1, b'and on stdout\\n')\n"
                           "sys.stderr.write('and a traceback goes here too\\n')\n", {"ASTRA_MIND_LOG": str(log)})
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertEqual((r.stdout, r.stderr), ("", ""))
            text = log.read_text(encoding="utf-8")
            for line in ("from print: caffè → ·", "astra.test from logging", "from a native library", "and on stdout", "and a traceback goes here too"):
                self.assertIn(line, text)

    def test_importing_the_package_takes_the_log(self) -> None:
        # the game names the log in the environment: even a library that fails to load at import must be able to say why
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "mind.log"
            r = run_python("import astra_mind\nprint('imported')\nraise SystemExit(3)\n", {"ASTRA_MIND_LOG": str(log)})
            self.assertEqual(r.returncode, 3)
            self.assertEqual(r.stdout, "")
            self.assertIn("imported", log.read_text(encoding="utf-8"))

    def test_no_variable_no_change(self) -> None:
        env = {k: v for k, v in os.environ.items() if k != "ASTRA_MIND_LOG"}
        r = subprocess.run([sys.executable, "-c", "from astra_mind import host\nprint(host.redirect_output_to_log())\nprint('still here')"], cwd=MIND, env=env,
                           capture_output=True, text=True)
        self.assertEqual(r.stdout.split(), ["None", "still", "here"])

    def test_the_log_is_appended_to_and_a_big_one_is_set_aside(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "mind.log"
            log.write_text("an earlier run\n", encoding="utf-8")
            run_python("from astra_mind import host\nhost.redirect_output_to_log()\nprint('second run')", {"ASTRA_MIND_LOG": str(log)})
            self.assertEqual(log.read_text(encoding="utf-8"), "an earlier run\nsecond run\n")
            with open(log, "ab") as f:                                                  # a log of a long soak: past the cap
                f.truncate(host.LOG_CAP_BYTES + 1)
            run_python("from astra_mind import host\nprint('third run')", {"ASTRA_MIND_LOG": str(log)})
            self.assertEqual(log.read_text(encoding="utf-8"), "third run\n")
            self.assertEqual(Path(str(log) + ".1").stat().st_size, host.LOG_CAP_BYTES + 1)     # (the one before is kept, as `.1`)

    def test_a_log_that_cannot_be_made_leaves_the_output_alone(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            blocker = Path(td) / "a_file"
            blocker.write_text("x", encoding="utf-8")
            r = run_python("from astra_mind import host\nprint(host.redirect_output_to_log())\nprint('still here')", {"ASTRA_MIND_LOG": str(blocker / "sub" / "mind.log")})
            self.assertEqual(r.stdout.split(), ["None", "still", "here"])

    @unittest.skipIf(sys.platform == "win32", "the Windows loop has no signal handlers: the other test covers it")
    def test_stop_handlers_on_a_loop_that_has_them(self) -> None:
        async def go() -> list[int]:
            loop = asyncio.get_running_loop()
            got: list[int] = []
            done = asyncio.Event()

            def stop(sig: int) -> None:
                got.append(sig)
                done.set()
            installed = host.install_stop_handlers(loop, stop)
            try:
                self.assertIn(int(signal.SIGTERM), installed)
                self.assertIn(int(signal.SIGINT), installed)
                os.kill(os.getpid(), signal.SIGTERM)
                await asyncio.wait_for(done.wait(), 5)
            finally:
                for s in installed:
                    loop.remove_signal_handler(s)
            return got
        self.assertEqual(asyncio.run(go()), [int(signal.SIGTERM)])

    def test_stop_handlers_where_the_loop_has_none_and_sighup_does_not_exist(self) -> None:
        # what a Windows process sees: no SIGHUP, a SIGBREAK, an event loop whose add_signal_handler raises NotImplementedError
        class NoSignalsLoop:
            def __init__(self) -> None:
                self.handed: list[tuple] = []

            def add_signal_handler(self, *args) -> None:
                raise NotImplementedError

            def call_soon_threadsafe(self, fn, *args) -> None:
                self.handed.append((fn, args))
        taken: dict[int, object] = {}
        loop = NoSignalsLoop()
        stops: list[int] = []
        sigbreak = int(signal.SIGUSR1) if hasattr(signal, "SIGUSR1") else 21
        with mock.patch.object(signal, "SIGHUP", None, create=True), mock.patch.object(signal, "SIGBREAK", sigbreak, create=True), \
                mock.patch.object(signal, "signal", side_effect=lambda s, h: taken.__setitem__(int(s), h)):
            installed = host.install_stop_handlers(loop, stops.append)       # type: ignore[arg-type]
        self.assertEqual(sorted(installed), sorted({int(signal.SIGTERM), int(signal.SIGINT), sigbreak}))
        self.assertNotIn(None, installed)
        taken[int(signal.SIGINT)](int(signal.SIGINT), None)                    # Ctrl-C: the handler hands the stop to the loop's own thread
        self.assertEqual(len(loop.handed), 1)
        fn, args = loop.handed[0]
        fn(*args)
        self.assertEqual(stops, [int(signal.SIGINT)])

    def test_a_signal_that_cannot_be_taken_is_skipped(self) -> None:
        class OffMainThreadLoop:
            def add_signal_handler(self, *args) -> None:
                raise RuntimeError("not the main thread")
        with mock.patch.object(signal, "signal", side_effect=ValueError("signal only works in main thread")):
            self.assertEqual(host.install_stop_handlers(OffMainThreadLoop(), lambda s: None), [])    # type: ignore[arg-type]


class TestSpeechEngineChoice(unittest.TestCase):
    """Which engines a machine gets (stt.default_backends), in the machines of the three systems."""

    def names(self, forced: str = "") -> list[str]:
        return [b.name for b in stt_module.default_backends(forced)]

    def test_off_has_none(self) -> None:
        self.assertEqual(self.names("off"), [])

    def test_portable_never_has_the_neural_engine_or_whisperkit(self) -> None:
        with mock.patch.object(ParakeetBackend, "available", staticmethod(lambda: True)), mock.patch.object(WhisperKitBackend, "available", staticmethod(lambda: True)):
            self.assertIn("parakeet", self.names("") + ["parakeet"])         # (sanity: without forcing, a Mac that has them uses them)
            self.assertEqual(self.names("")[0], "parakeet")
            for name in self.names("portable"):
                self.assertIn(name, ("parakeet-onnx", "faster-whisper"))
            self.assertNotIn("parakeet", self.names("portable"))
            self.assertNotIn("whisperkit", self.names("portable"))

    def test_a_windows_pc_gets_the_portable_engines_and_nothing_else(self) -> None:
        # a Windows machine: no Apple Silicon, no whisperkit-cli on the path, a mind that may download what it lacks
        with mock.patch.object(platform, "system", return_value="Windows"), mock.patch.object(platform, "machine", return_value="AMD64"), \
                mock.patch.object(shutil, "which", return_value=None), mock.patch.dict(os.environ, {"ASTRA_STT": "", "ASTRA_STT_FETCH": ""}):
            self.assertFalse(ParakeetBackend.available())
            self.assertFalse(WhisperKitBackend.available())
            self.assertTrue(backends_module.fetch_allowed())
            self.assertEqual(self.names(""), ["parakeet-onnx", "faster-whisper"])
            self.assertEqual(self.names("faster-whisper"), ["faster-whisper", "parakeet-onnx"])        # (the forced one is tried first)

    def test_an_apple_silicon_mac_does_not_download_by_itself_unless_told_to(self) -> None:
        with mock.patch.object(platform, "system", return_value="Darwin"), mock.patch.object(platform, "machine", return_value="arm64"):
            with mock.patch.dict(os.environ, {"ASTRA_STT_FETCH": ""}):
                self.assertFalse(backends_module.fetch_allowed())
            with mock.patch.dict(os.environ, {"ASTRA_STT_FETCH": "1"}):
                self.assertTrue(backends_module.fetch_allowed())
        with mock.patch.object(platform, "system", return_value="Windows"), mock.patch.dict(os.environ, {"ASTRA_STT_FETCH": "0"}):
            self.assertFalse(backends_module.fetch_allowed())

    def test_an_intel_mac_is_a_portable_machine_too(self) -> None:
        with mock.patch.object(platform, "system", return_value="Darwin"), mock.patch.object(platform, "machine", return_value="x86_64"), \
                mock.patch.dict(os.environ, {"ASTRA_STT_FETCH": ""}):
            self.assertFalse(ParakeetBackend.available())
            self.assertTrue(backends_module.fetch_allowed())


class TestPortableModelFetch(unittest.IsolatedAsyncioTestCase):
    async def test_a_missing_model_is_fetched_once_where_the_machine_does_that(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "models"
            calls: list[Path] = []

            def fake_fetch(r: Path) -> Path:
                calls.append(r)
                folder = r / backends_module.SHERPA_MODEL_NAME
                folder.mkdir(parents=True)
                (folder / "encoder.int8.onnx").write_bytes(b"x")
                return folder
            with mock.patch.dict(os.environ, {"ASTRA_STT_FETCH": "1"}), mock.patch.object(backends_module, "fetch_sherpa_model", fake_fetch):
                os.environ.pop("ASTRA_SHERPA_MODEL", None)
                b = SherpaParakeetBackend(model_dir=root / backends_module.SHERPA_MODEL_NAME)
                self.assertFalse(SherpaParakeetBackend.available(b.model_dir))
                self.assertTrue(await b._fetch())
                self.assertEqual(calls, [root])
                self.assertTrue(SherpaParakeetBackend.available(b.model_dir))

    async def test_no_download_where_it_is_not_allowed_or_the_folder_was_chosen(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            calls: list[Path] = []
            b = SherpaParakeetBackend(model_dir=Path(td) / "m")
            with mock.patch.object(backends_module, "fetch_sherpa_model", lambda r: calls.append(r)):
                with mock.patch.dict(os.environ, {"ASTRA_STT_FETCH": "0"}):
                    os.environ.pop("ASTRA_SHERPA_MODEL", None)
                    self.assertFalse(await b._fetch())
                with mock.patch.dict(os.environ, {"ASTRA_STT_FETCH": "1", "ASTRA_SHERPA_MODEL": td}):
                    self.assertFalse(await b._fetch())                       # (somebody's own folder is never replaced by a download)
            self.assertEqual(calls, [])

    async def test_a_download_that_fails_leaves_the_engine_down_and_says_so(self) -> None:
        def broken(r: Path) -> Path:
            raise OSError("no network")
        b = SherpaParakeetBackend(model_dir=Path(tempfile.gettempdir()) / "astra-no-such-model-folder")
        with mock.patch.dict(os.environ, {"ASTRA_STT_FETCH": "1"}), mock.patch.object(backends_module, "fetch_sherpa_model", broken):
            os.environ.pop("ASTRA_SHERPA_MODEL", None)
            with self.assertLogs("astra.stt", level="ERROR"):
                self.assertFalse(await b.start())


class TestSystemVoices(unittest.TestCase):
    """The voices of Windows (SAPI through PowerShell) against a PowerShell that is a stand-in; the Mac's keep working."""

    LISTING = ("\ufeffMicrosoft David Desktop|en-US|Male\r\nMicrosoft Zira Desktop|en-US|Female\r\nMicrosoft Elsa Desktop - Italian (Italy)|it-IT|Female\r\n"
               "Microsoft Hortense Desktop|fr-FR|Female\r\nMicrosoft Haruka Desktop|ja-JP|Female\r\nMicrosoft Huihui Desktop|zh-CN|Female\r\n\r\nnot a voice line\r\n")

    def fake_powershell(self, calls: list, rate: int = 22050):
        def run(cmd, **kw):
            calls.append((cmd, kw))
            script = base64.b64decode(cmd[-1]).decode("utf-16-le")
            if "GetInstalledVoices" in script:
                return subprocess.CompletedProcess(cmd, 0, self.LISTING.encode("utf-8"), b"")
            out = kw["env"]["ASTRA_SAPI_OUT"]
            t = np.arange(int(rate * 0.5)) / rate
            sf.write(out, (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32), rate, subtype="PCM_16")
            return subprocess.CompletedProcess(cmd, 0, b"", b"")
        return run

    def test_the_voices_are_listed_once_and_picked_by_language_and_sex(self) -> None:
        calls: list = []
        with mock.patch.object(subprocess, "run", self.fake_powershell(calls)):
            v = tts_module.SystemVoices("win32")
            self.assertEqual(v.pick("en", "f"), "Microsoft Zira Desktop")
            self.assertEqual(v.pick("en", "m"), "Microsoft David Desktop")
            self.assertEqual(v.pick("it", "m"), "Microsoft Elsa Desktop - Italian (Italy)")      # (a voice of the other sex beats none)
            self.assertEqual(v.pick("ja"), "Microsoft Haruka Desktop")
            self.assertEqual(v.pick("zh"), "Microsoft Huihui Desktop")
            self.assertIsNone(v.pick("ru"))
            self.assertEqual(len(calls), 1)                                                        # one PowerShell for all of that
            self.assertIn("Microsoft David Desktop", v.installed())

    def test_the_powershell_command_carries_no_text_and_decodes_back_to_the_script(self) -> None:
        cmd = tts_module.powershell_command(tts_module._SAPI_SAY)
        self.assertEqual(cmd[0], "powershell.exe")
        self.assertIn("-NoProfile", cmd)
        self.assertIn("-NonInteractive", cmd)
        self.assertEqual(cmd[-2], "-EncodedCommand")
        self.assertEqual(base64.b64decode(cmd[-1]).decode("utf-16-le"), tts_module._SAPI_SAY)
        self.assertNotIn("Speak", " ".join(cmd[:-1]))
        for var in ("ASTRA_SAPI_VOICE", "ASTRA_SAPI_OUT", "ASTRA_SAPI_TEXT"):
            self.assertIn("$env:" + var, tts_module._SAPI_SAY)

    def test_a_line_is_made_in_a_file_the_text_travels_in_the_environment_and_the_result_is_resampled(self) -> None:
        calls: list = []
        text = "Capitano, l’Acheron è a 45 km — “scudi a prua”"
        with mock.patch.object(subprocess, "run", self.fake_powershell(calls, rate=22050)):
            v = tts_module.SystemVoices("win32")
            x = v.render(text, "Microsoft Elsa Desktop - Italian (Italy)", 24000)
        cmd, kw = calls[-1]
        self.assertEqual(kw["env"]["ASTRA_SAPI_TEXT"], text)
        self.assertEqual(kw["env"]["ASTRA_SAPI_VOICE"], "Microsoft Elsa Desktop - Italian (Italy)")
        self.assertNotIn(text, " ".join(cmd))
        self.assertFalse(Path(kw["env"]["ASTRA_SAPI_OUT"]).exists(), "the temporary file is removed")
        self.assertEqual(x.dtype, np.float32)
        self.assertEqual(x.ndim, 1)
        self.assertAlmostEqual(len(x) / 24000, 0.5, delta=0.02)
        self.assertGreater(float(np.abs(x).max()), 0.2)

    def test_a_powershell_that_fails_says_so(self) -> None:
        def run(cmd, **kw):
            return subprocess.CompletedProcess(cmd, 1, b"", b"Exception calling SelectVoice")
        v = tts_module.SystemVoices("win32")
        with mock.patch.object(subprocess, "run", run):
            with self.assertRaises(RuntimeError) as c:
                v.render("hello", "No Such Voice", 24000)
        self.assertIn("SelectVoice", str(c.exception))

    def test_no_powershell_means_no_voices_not_a_crash(self) -> None:
        def run(cmd, **kw):
            raise FileNotFoundError("powershell.exe")
        with mock.patch.object(subprocess, "run", run), self.assertLogs("astra.tts", level="WARNING"):
            v = tts_module.SystemVoices("win32")
            self.assertIsNone(v.pick("en"))
            self.assertEqual(v.installed(), set())

    def test_a_system_without_voices_of_its_own(self) -> None:
        v = tts_module.SystemVoices("linux")
        self.assertIsNone(v.pick("en"))
        self.assertEqual(v.installed(), set())
        with self.assertRaises(RuntimeError):
            v.render("x", "y", 24000)
        eng = tts_module.TTSEngine()
        eng.system = v
        self.assertTrue(eng.can_speak("it"))                      # (Pocket speaks it: the model is fetched)
        self.assertFalse(eng.can_speak("ja"))                     # (nothing speaks it here)

    def test_the_mac_voices_are_chosen_as_before(self) -> None:
        v = tts_module.SystemVoices("darwin")
        with mock.patch.object(v._impl, "installed", return_value={"Alice", "Daniel", "Kyoko", "Hattori"}):
            self.assertEqual(v.pick("it", "f"), "Alice")
            self.assertEqual(v.pick("en", "m"), "Daniel")
            self.assertEqual(v.pick("ja", "f"), "Kyoko")
            self.assertEqual(v.pick("ja", "m"), "Hattori")
            self.assertEqual(v.pick("it", "m"), "Alice")           # (no Italian man installed: the woman beats none)
            self.assertIsNone(v.pick("ru"))                         # (no Russian voice installed)

    def test_the_catalogue_is_loaded_in_the_background_on_windows_only(self) -> None:
        with mock.patch.object(subprocess, "run", self.fake_powershell([])):
            w = tts_module.SystemVoices("win32")
            w.warm()
            deadline = time.time() + 5
            while w._impl._voices is None and time.time() < deadline:        # type: ignore[union-attr]
                time.sleep(0.01)
            self.assertIsNotNone(w._impl._voices)                              # type: ignore[union-attr]
        tts_module.SystemVoices("darwin").warm()                               # (nothing to do: `say` lists its voices when asked)
        tts_module.SystemVoices("linux").warm()


class TestPackaging(unittest.TestCase):
    MARKER = "sys_platform != 'darwin' or platform_machine != 'arm64'"
    PORTABLE = ("faster-whisper", "sherpa-onnx", "sherpa-onnx-core")

    def test_the_portable_engines_come_with_every_machine_that_has_no_neural_engine_helper(self) -> None:
        meta = tomllib.loads((MIND / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        deps = meta["dependencies"]
        for name in self.PORTABLE:
            self.assertTrue(any(d.replace(" ", "").startswith(name + ">=") and self.MARKER.replace(" ", "") in d.replace(" ", "") for d in deps),
                            f"{name} needs the platform marker in the dependencies")
        self.assertEqual({d.split(">=")[0] for d in meta["optional-dependencies"]["portable"]}, set(self.PORTABLE))      # (`--extra portable` still works on a Mac)

    def test_the_lock_agrees_with_the_project(self) -> None:
        lock = tomllib.loads((MIND / "uv.lock").read_text(encoding="utf-8"))
        root = next(p for p in lock["package"] if p["name"] == "astra-mind")
        by_name = {d["name"]: d for d in root["dependencies"]}
        for name in self.PORTABLE:
            self.assertIn(name, by_name, f"uv.lock is stale: run `uv lock` in mind/ ({name} is not a dependency of astra-mind)")
            self.assertIn("marker", by_name[name])
            self.assertIn("darwin", by_name[name]["marker"])

    def test_the_game_and_the_mind_agree_on_the_door(self) -> None:
        source = (MIND.parent / "Source" / "ASTRA" / "AstraMindLaunch.cpp").read_text(encoding="utf-8")
        self.assertIn("ASTRA_MIND_PORT", source)
        self.assertIn("ASTRA_MIND_LOG", source)
        self.assertEqual(host.DEFAULT_PORT, 8765)
        self.assertIn("8765", source)

    @unittest.skipUnless(shutil.which("uv"), "uv is not installed")
    def test_every_locked_package_has_a_windows_wheel(self) -> None:
        # uv resolves the lock for Windows x64 / CPython 3.13 without building anything: a dependency that has no Windows wheel (or is only a
        # source archive that would need a compiler) fails here, the day it is added, not the day somebody installs the game on a PC
        exported = subprocess.run(["uv", "export", "--frozen", "--no-hashes", "--no-emit-project"], cwd=MIND, capture_output=True, text=True)
        self.assertEqual(exported.returncode, 0, exported.stderr)
        with tempfile.TemporaryDirectory() as td:
            req = Path(td) / "requirements.txt"
            req.write_text(exported.stdout, encoding="utf-8")
            r = subprocess.run(["uv", "pip", "install", "--dry-run", "--no-deps", "--only-binary", ":all:", "--python-platform", "x86_64-pc-windows-msvc",
                                "--python-version", "3.13", "-r", str(req)], cwd=MIND, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        # (what is listed is what differs from this machine's own environment; colorama is the Windows-only package: the markers were read for Windows)
        self.assertIn("colorama==", r.stdout + r.stderr)


class TestFirstRun(unittest.TestCase):
    def test_the_check_runs_and_counts_what_stops_the_mind(self) -> None:
        from astra_mind import firstrun
        with tempfile.TemporaryDirectory() as td:
            self.assertTrue(firstrun.writable(Path(td) / "a" / "b"))
        self.assertFalse(firstrun.writable(Path(os.devnull) / "x"))
        lines = firstrun.look()
        self.assertTrue(all(level in (firstrun.OK, firstrun.WARN, firstrun.FAIL) for level, _ in lines))
        self.assertTrue(any("Python" in text for _, text in lines))
        self.assertFalse(any("sk-or" in text for _, text in lines), "a key's value is never printed")


@unittest.skipUnless(os.environ.get("ASTRA_TEST_BOOT") == "1", "ASTRA_TEST_BOOT=1 starts the real mind")
class TestBoot(unittest.TestCase):
    def test_the_mind_starts_as_the_game_starts_it(self) -> None:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        with tempfile.TemporaryDirectory() as td:
            log = Path(td) / "Logs" / "astra-mind.log"
            env = {**os.environ, "ASTRA_MIND_LOG": str(log), "ASTRA_MIND_PORT": str(port), "ASTRA_SAVED": str(Path(td) / "Saved"), "ASTRA_STT": "off",
                   "ASTRA_TTS_WARM": "0", "OPENROUTER_API_KEY": "test-only-not-a-key", "PYTHONUTF8": "1"}
            proc = subprocess.Popen([sys.executable, "-m", "astra_mind.server"], cwd=MIND, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
            try:
                deadline = time.time() + 120
                up = False
                while time.time() < deadline and proc.poll() is None:
                    try:
                        socket.create_connection(("127.0.0.1", port), timeout=1).close()
                        up = True
                        break
                    except OSError:
                        time.sleep(0.5)
                text = log.read_text(encoding="utf-8") if log.exists() else ""
                self.assertTrue(up, "the mind did not open its door: " + text[-1500:])
                self.assertIn(f"astra-mind listening on ws://127.0.0.1:{port}", text)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    proc.kill()


@unittest.skipUnless(os.environ.get("ASTRA_TEST_PORTABLE_REAL") == "1", "ASTRA_TEST_PORTABLE_REAL=1 runs the real portable engines")
class TestPortableEngines(unittest.IsolatedAsyncioTestCase):
    SENTENCE = "Helm, come to heading two one seven and full ahead."

    async def asyncSetUp(self) -> None:
        eng = tts_module.TTSEngine()
        if not eng.available("en"):
            self.skipTest("the English voice model is not in the cache")
        from astra_mind.voice_audio import f32_to_pcm16, resample
        audio = eng.render(self.SENTENCE, "alba", "en")
        self.pcm = f32_to_pcm16(resample(audio, eng.sample_rate, 16000))

    async def test_the_portable_engines_hear_the_sentence(self) -> None:
        with mock.patch.dict(os.environ, {"ASTRA_STT": "portable"}):
            rec = stt_module.Recognizer(prior="en")
        names = [b.name for b in rec.backends]
        self.assertTrue(set(names) <= {"parakeet-onnx", "faster-whisper"} and names, names)
        self.assertTrue(await rec.ready())
        for backend in rec.backends:                              # (each one on its own too: the second engine is only started when it is asked)
            solo = stt_module.Recognizer(backends=[type(backend)()], prior="en")
            self.assertTrue(await solo.ready(), backend.name)
            tr = await solo.recognise(self.pcm, 16000, raw_audio=True)
            words = tr.text.lower()
            print(f"\n   {backend.name}: {tr.text!r} ({tr.decode_s:.2f} s)")
            self.assertTrue("heading" in words and "ahead" in words, f"{backend.name} heard {tr.text!r}")
            await solo.close()
        await rec.close()


if __name__ == "__main__":
    unittest.main()
