"""What differs between the operating systems the mind runs on, in one place. The game starts the mind on macOS, Windows and
Linux, detached and with no console to write to, so:

- the log: `redirect_output_to_log()` sends everything the process prints (Python and native libraries alike) to the file the
  game names in ASTRA_MIND_LOG: appended to, with a size cap, and in UTF-8 whatever the console's code page is;
- stopping: `install_stop_handlers()` asks the event loop for the signals this system has (SIGHUP does not exist on Windows and
  its event loops cannot take signal handlers: the signal module's own are used there);
- the door: `mind_port()`, ASTRA_MIND_PORT (the game reads the same variable), 8765 by default.

Nothing here is macOS only or Windows only in what it asks of the caller: the differences are inside.
"""
from __future__ import annotations

import asyncio
import faulthandler
import os
import signal
import sys
from pathlib import Path
from typing import Callable, Mapping

DEFAULT_PORT = 8765
LOG_CAP_BYTES = 20 * 1024 * 1024          # a log above this is set aside (as `.1`, the one before it lost) when the mind starts

_redirected: Path | None = None


def mind_port(environ: Mapping[str, str] | None = None) -> int:
    """The port the mind listens on (and the game connects to): ASTRA_MIND_PORT when it is a usable port, else 8765. A machine where
    8765 is taken (Windows keeps ranges of ports for itself) sets it for both sides."""
    raw = (os.environ if environ is None else environ).get("ASTRA_MIND_PORT", "").strip()
    try:
        port = int(raw)
    except ValueError:
        return DEFAULT_PORT
    return port if 1024 <= port <= 65535 else DEFAULT_PORT


def _set_aside_if_big(path: Path) -> None:
    try:
        if path.stat().st_size > LOG_CAP_BYTES:
            os.replace(path, path.with_name(path.name + ".1"))
    except OSError:
        pass                                   # not there yet, or another process holds it: it is appended to as it is


def redirect_output_to_log(target: str | os.PathLike[str] | None = None) -> Path | None:
    """Send stdout and stderr (the descriptors, so that PortAudio, ONNX Runtime, torch and every child process follow) to a log file,
    appending. `target` defaults to ASTRA_MIND_LOG; without either nothing changes (a mind run by hand keeps its terminal). Returns the
    file, or None when there was none to use. Done once: the first call wins."""
    global _redirected
    if _redirected is not None:
        return _redirected
    name = os.fspath(target) if target else os.environ.get("ASTRA_MIND_LOG", "")
    if not name:
        return None
    path = Path(name)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        _set_aside_if_big(path)
        log_file = open(path, "ab", buffering=0)
    except OSError:
        return None
    for stream in (sys.stdout, sys.stderr):            # (None when the process was started without a console)
        try:
            stream.flush()
        except Exception:  # noqa: BLE001
            pass
    os.dup2(log_file.fileno(), 1)
    os.dup2(log_file.fileno(), 2)
    log_file.close()                                    # (descriptors 1 and 2 keep the file open)
    sys.stdout = open(1, "w", encoding="utf-8", errors="replace", newline="\n", buffering=1, closefd=False)
    sys.stderr = open(2, "w", encoding="utf-8", errors="backslashreplace", newline="\n", buffering=1, closefd=False)
    faulthandler.enable(file=sys.stderr, all_threads=True)       # a native crash leaves its stacks in the log
    _redirected = path
    return path


def install_stop_handlers(loop: asyncio.AbstractEventLoop, stop: Callable[[int], None]) -> list[int]:
    """Call `stop(signal number)` when the system asks the mind to end (the game closing it, Ctrl-C). The signals each system has are
    used: SIGTERM, SIGHUP and SIGINT on macOS and Linux, SIGTERM, SIGINT and SIGBREAK (Ctrl-Break) on Windows. A Windows process that
    is simply terminated (what the game does when it quits) gets no signal at all: nothing the mind keeps depends on one. Returns the
    signals that were installed."""
    installed: list[int] = []
    for name in ("SIGTERM", "SIGHUP", "SIGINT", "SIGBREAK"):
        sig = getattr(signal, name, None)
        if sig is None:
            continue
        try:
            loop.add_signal_handler(sig, stop, sig)       # portable-ok: the Windows loops raise NotImplementedError: the signal module's handler follows
        except (NotImplementedError, RuntimeError):
            # the Windows event loops have no add_signal_handler: the signal module's handler runs in the main thread, and hands over to the loop
            try:
                signal.signal(sig, lambda s, _frame: loop.call_soon_threadsafe(stop, s))
            except (OSError, ValueError):
                continue                                # (not the main thread, or a signal this system will not take)
        installed.append(int(sig))
    return installed
