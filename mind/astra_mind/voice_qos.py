"""Scheduling priority for the voice threads.

The mind runs next to a game that keeps every performance core busy. macOS gives an ordinary thread of a background-ish
process whatever is left, often an efficiency core, and the text-to-speech that runs at 6-9x real time on a free core drops
to 2-3x: the first sound of an answer comes 100-400 ms late and a long line can fall behind its own playback (a gap, a stutter,
a voice that seems to stop). Raising the quality-of-service class of the threads that make speech to USER_INITIATED puts
them on the performance cores again. Insurance rather than a proven gain: A/B runs next to the Unreal editor were not consistent
(one showed 2.5x -> 8x real time, later ones nothing), the call is free, and it cannot make the speech slower.

macOS only (ctypes into libSystem); elsewhere a no-op. ASTRA_VOICE_QOS=0 switches it off."""
from __future__ import annotations

import ctypes
import logging
import sys

log = logging.getLogger("astra.qos")

QOS_USER_INTERACTIVE = 0x21
QOS_USER_INITIATED = 0x19
QOS_DEFAULT = 0x15

_libc = None


def _lib():
    global _libc
    if _libc is None and sys.platform == "darwin":       # portable-ok: macOS's scheduler classes; other systems keep their own priorities (a no-op here)
        try:
            _libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib")       # portable-ok: macOS's libSystem
        except OSError:
            _libc = False
    return _libc or None


def boost_thread(qos: int = QOS_USER_INITIATED) -> bool:
    """Raise the calling thread's quality of service (threads it creates afterwards inherit it). True when applied."""
    lib = _lib()
    if lib is None:
        return False
    try:
        return lib.pthread_set_qos_class_self_np(qos, 0) == 0
    except Exception:  # noqa: BLE001
        log.debug("could not set the QoS class", exc_info=True)
        return False
