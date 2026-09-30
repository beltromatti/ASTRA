"""Audio DSP for the voice pipeline (numpy + scipy only, portable): resampling, loudness (ITU-R BS.1770 K-weighting and
gated integrated loudness), a look-ahead peak limiter, a streaming WSOLA time stretcher, a pause compressor and a small
energy voice-activity detector.

Every streaming class takes float32 mono chunks of any size and returns float32 chunks; `flush()` returns what is still
held back. PCM16 helpers convert at the edges. Nothing here knows about the game or the network."""
from __future__ import annotations

import math
from math import gcd

import numpy as np
from scipy.ndimage import minimum_filter1d, uniform_filter1d
from scipy.signal import lfilter, resample_poly

EPS = 1e-12


# ------------------------------------------------------------------------------------------------ PCM16 edges
def pcm16_to_f32(pcm: bytes | np.ndarray) -> np.ndarray:
    a = np.frombuffer(pcm, dtype="<i2") if isinstance(pcm, (bytes, bytearray, memoryview)) else np.asarray(pcm)
    return a.astype(np.float32) / 32768.0


def f32_to_pcm16(x: np.ndarray) -> bytes:
    return (np.clip(x, -1.0, 1.0) * 32767.0).astype("<i2").tobytes()


def db(x: float) -> float:
    return 20.0 * math.log10(max(x, EPS))


def from_db(d: float) -> float:
    return 10.0 ** (d / 20.0)


def resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    """Polyphase resampling (zero-phase, anti-aliased) of a whole signal."""
    if sr_in == sr_out or len(x) == 0:
        return x.astype(np.float32, copy=False)
    g = gcd(sr_in, sr_out)
    return resample_poly(x, sr_out // g, sr_in // g).astype(np.float32)


# ------------------------------------------------------------------------------------------------ loudness
def _k_stage1(fs: float) -> tuple[np.ndarray, np.ndarray]:
    """BS.1770 stage 1: the head-related high shelf (+4 dB above ~1.7 kHz), designed for any sample rate."""
    G, Q, fc = 3.999843853973347, 0.7071752369554196, 1681.974450955533
    K = math.tan(math.pi * fc / fs)
    Vh = 10.0 ** (G / 20.0)
    Vb = Vh ** 0.4996667741545416
    a0 = 1.0 + K / Q + K * K
    b = np.array([(Vh + Vb * K / Q + K * K) / a0, 2.0 * (K * K - Vh) / a0, (Vh - Vb * K / Q + K * K) / a0])
    a = np.array([1.0, 2.0 * (K * K - 1.0) / a0, (1.0 - K / Q + K * K) / a0])
    return b, a


def _k_stage2(fs: float) -> tuple[np.ndarray, np.ndarray]:
    """BS.1770 stage 2: the RLB high-pass (38 Hz)."""
    Q, fc = 0.5003270373238773, 38.13547087602444
    K = math.tan(math.pi * fc / fs)
    a0 = 1.0 + K / Q + K * K
    b = np.array([1.0, -2.0, 1.0])
    a = np.array([1.0, 2.0 * (K * K - 1.0) / a0, (1.0 - K / Q + K * K) / a0])
    return b, a


def k_weight(x: np.ndarray, fs: float) -> np.ndarray:
    b1, a1 = _k_stage1(fs)
    b2, a2 = _k_stage2(fs)
    return lfilter(b2, a2, lfilter(b1, a1, x.astype(np.float64)))


def integrated_lufs(x: np.ndarray, fs: float) -> float:
    """Gated integrated loudness (BS.1770-4: 400 ms blocks, 75 % overlap, -70 LUFS absolute gate, -10 LU relative gate).
    Signals shorter than one block use their whole mean square. Silence returns -70."""
    if len(x) == 0:
        return -70.0
    y = k_weight(x, fs)
    blk, step = int(0.4 * fs), int(0.1 * fs)
    if len(y) < blk:
        return -0.691 + 10.0 * math.log10(float(np.mean(y * y)) + EPS)
    c = np.concatenate([[0.0], np.cumsum(y * y)])
    starts = np.arange(0, len(y) - blk + 1, step)
    zs = (c[starts + blk] - c[starts]) / blk
    lk = -0.691 + 10.0 * np.log10(zs + EPS)
    gated = zs[lk > -70.0]
    if len(gated) == 0:
        return -70.0
    rel = -0.691 + 10.0 * math.log10(float(np.mean(gated))) - 10.0
    gated = zs[(lk > -70.0) & (lk > rel)]
    if len(gated) == 0:
        return -70.0
    return -0.691 + 10.0 * math.log10(float(np.mean(gated)))


def peak_db(x: np.ndarray) -> float:
    return db(float(np.max(np.abs(x)))) if len(x) else -120.0


def rms_db(x: np.ndarray) -> float:
    return db(float(np.sqrt(np.mean(np.square(x, dtype=np.float64))))) if len(x) else -120.0


def frame_rms_db(x: np.ndarray, frame: int) -> np.ndarray:
    """RMS level in dBFS of consecutive `frame`-sample blocks (the tail shorter than a frame is ignored)."""
    n = len(x) // frame
    if n == 0:
        return np.zeros(0)
    fr = x[: n * frame].astype(np.float64).reshape(n, frame)
    return 10.0 * np.log10(np.mean(fr * fr, axis=1) + EPS)


# ------------------------------------------------------------------------------------------------ limiter
class Limiter:
    """Look-ahead brick-wall peak limiter for streaming audio. The gain is the moving minimum of what the coming
    `lookahead_ms` of samples need, smoothed by a moving average (the attack is a ramp, not a click), then released
    exponentially (`release_ms`). Output is delayed by 3 x lookahead samples; `flush()` returns the tail. No output
    sample exceeds the ceiling."""

    def __init__(self, sr: int, ceiling_db: float = -1.5, lookahead_ms: float = 2.5, release_ms: float = 90.0) -> None:
        self.sr = sr
        self.ceiling = from_db(ceiling_db)
        self.L = max(2, int(sr * lookahead_ms / 1000.0))
        self.delay = 3 * self.L
        self._decay = math.exp(-1.0 / (sr * release_ms / 1000.0))
        self._env = 0.0                                   # gain reduction (1 - gain) at the last emitted sample
        self._tail = np.zeros(0, dtype=np.float64)        # input kept: `_ctx` emitted samples of context, then pending
        self._ctx = 0
        self.reduction_max_db = 0.0                       # deepest gain reduction so far (for the benchmark)
        self.reduced_samples = 0                          # samples with more than 1 dB of reduction
        self.samples = 0

    def process(self, x: np.ndarray) -> np.ndarray:
        buf = np.concatenate([self._tail, x.astype(np.float64)])
        emit_to = len(buf) - self.delay
        if emit_to <= self._ctx:
            self._tail = buf
            return np.zeros(0, dtype=np.float32)
        out = self._run(buf, self._ctx, emit_to)
        keep_from = max(0, emit_to - self.delay)
        self._ctx = emit_to - keep_from
        self._tail = buf[keep_from:]
        return out

    def flush(self) -> np.ndarray:
        if len(self._tail) <= self._ctx:
            return np.zeros(0, dtype=np.float32)
        buf = np.concatenate([self._tail, np.zeros(self.delay, dtype=np.float64)])
        out = self._run(buf, self._ctx, len(self._tail))
        self._tail = np.zeros(0, dtype=np.float64)
        self._ctx = 0
        return out

    def _run(self, buf: np.ndarray, a: int, b: int) -> np.ndarray:
        w = self.L + 1
        need = np.minimum(1.0, self.ceiling / np.maximum(np.abs(buf), EPS))
        # the gain that samples i .. i+L need (look-ahead), its moving minimum and a moving average: the attack becomes a
        # ramp that is complete when the peak arrives
        g = minimum_filter1d(need, size=w, origin=-(w // 2), mode="nearest")
        g = minimum_filter1d(g, size=w, mode="nearest")
        g = uniform_filter1d(g, size=w, mode="nearest")
        red = 1.0 - g[a:b]
        n = np.arange(len(red), dtype=np.float64)
        d = self._decay
        env = (d ** n) * np.maximum(self._env * d, np.maximum.accumulate(red * d ** (-n)))
        self._env = float(env[-1])
        gain = 1.0 - env
        self.reduction_max_db = max(self.reduction_max_db, -db(float(gain.min())))
        self.reduced_samples += int(np.count_nonzero(gain < 0.891))
        self.samples += len(gain)
        y = buf[a:b] * gain
        return np.clip(y, -self.ceiling, self.ceiling).astype(np.float32)


# ------------------------------------------------------------------------------------------------ WSOLA time stretch
class TimeStretcher:
    """Streaming WSOLA (waveform-similarity overlap-add) time stretch that keeps pitch and timbre: `speed` 1.15 makes
    speech 15 % faster. Frames of ~30 ms at 50 % overlap; frame k comes from the place (within +-`search_ms` of
    k x Ha) that best continues frame k-1 as it was in the original. Latency is about 60 ms; `flush()` drains the rest."""

    def __init__(self, sr: int, speed: float, frame_ms: float = 30.0, search_ms: float = 9.0) -> None:
        self.speed = max(0.5, min(2.0, float(speed)))
        self.N = int(sr * frame_ms / 1000.0) // 2 * 2
        self.Hs = self.N // 2
        self.Ha = self.Hs * self.speed
        self.delta = max(4, int(sr * search_ms / 1000.0))
        self.decim = 3                                                     # coarse search on every 3rd sample
        w = np.hanning(self.N + 1)[:-1].astype(np.float64)                # periodic Hann: 50 % overlap sums to one
        self._win = w
        self._win0 = w.copy()
        self._win0[: self.Hs] = 1.0                                        # the very first frame does not fade in
        self._x = np.zeros(0, dtype=np.float64)                            # input still needed
        self._off = 0                                                      # absolute index of _x[0]
        self._k = 0                                                        # index of the next frame
        self._prev = 0                                                     # absolute start of the previous frame
        self._acc = np.zeros(self.N, dtype=np.float64)                     # overlap-add accumulator
        self._primed = False
        self._total_in = 0

    @property
    def passthrough(self) -> bool:
        return abs(self.speed - 1.0) < 0.005

    def process(self, x: np.ndarray) -> np.ndarray:
        if self.passthrough:
            return x.astype(np.float32, copy=False)
        self._x = np.concatenate([self._x, x.astype(np.float64)])
        self._total_in += len(x)
        return self._drain(final=False)

    def flush(self) -> np.ndarray:
        if self.passthrough:
            return np.zeros(0, dtype=np.float32)
        out = self._drain(final=True)
        if self._primed:
            tail = self._acc.astype(np.float32)          # what the last frames left in the accumulator (it fades out)
            self._acc = np.zeros(self.N, dtype=np.float64)
            self._primed = False
            return np.concatenate([out, tail])
        return out

    def _seg(self, start: int, n: int) -> np.ndarray:
        """n samples from absolute position `start`, zero-padded outside what is known."""
        a = start - self._off
        lo, hi = max(a, 0), a + n
        seg = self._x[lo:hi]
        if a < 0 or len(seg) < n:
            seg = np.concatenate([np.zeros(max(0, -a)), seg, np.zeros(max(0, n - len(seg) - max(0, -a)))])
        return seg

    def _drain(self, final: bool) -> np.ndarray:
        N, Hs = self.N, self.Hs
        out: list[np.ndarray] = []
        end = self._off + len(self._x)                                      # first absolute index not yet received
        while True:
            if not self._primed:
                if (not final and len(self._x) < N) or (final and len(self._x) == 0):
                    break
                self._acc = self._seg(0, N) * self._win0
                self._prev = 0
                self._k = 1
                self._primed = True
                continue
            nominal = int(round(self._k * self.Ha))
            lo, hi = max(0, nominal - self.delta), nominal + self.delta
            need = max(hi + N, self._prev + Hs + N)
            if not final and need > end:
                break
            if final and nominal >= self._total_in + self.delta:
                break
            target = self._seg(self._prev + Hs, N)
            best = self._best(target, lo, hi)
            out.append(self._acc[:Hs].astype(np.float32))                   # this half is complete now
            acc = np.zeros(N, dtype=np.float64)
            acc[:Hs] = self._acc[Hs:]
            acc += self._seg(best, N) * self._win
            self._acc = acc
            self._prev = best
            self._k += 1
            keep = min(self._prev + Hs, max(0, int(round(self._k * self.Ha)) - self.delta)) - 2
            if keep > self._off:
                cut = min(keep - self._off, len(self._x))
                self._x = self._x[cut:]
                self._off += cut
        return np.concatenate(out) if out else np.zeros(0, dtype=np.float32)

    def _best(self, target: np.ndarray, lo: int, hi: int) -> int:
        """Start position in [lo, hi] whose N samples best continue `target` (normalised cross-correlation): a coarse
        search on a decimated signal, refined at full rate."""
        N, D = self.N, self.decim
        span = self._seg(lo, hi - lo + N)
        cands = np.lib.stride_tricks.sliding_window_view(span[:: 1], N)[:: D]          # candidates every D samples
        tgt_d = target[::D]
        cd = cands[:, ::D]
        num = cd @ tgt_d
        score = num / np.sqrt(np.einsum("ij,ij->i", cd, cd) + 1e-9)
        coarse = int(np.argmax(score)) * D
        r_lo, r_hi = max(0, coarse - D), min(hi - lo, coarse + D)
        fine = np.lib.stride_tricks.sliding_window_view(span, N)[r_lo: r_hi + 1]
        num = fine @ target
        score = num / np.sqrt(np.einsum("ij,ij->i", fine, fine) + 1e-9)
        return lo + r_lo + int(np.argmax(score))


# ------------------------------------------------------------------------------------------------ pauses
class PauseCompressor:
    """Streaming pause shortener: leading silence is cut to `lead_keep_ms`, any later pause longer than `max_pause_ms`
    is shortened to it, and trailing silence is cut to `trail_keep_ms`. Silence is judged per 10 ms frame against the
    recent speech level (`rel_db` below it) and an absolute floor. Speech samples are never touched or delayed; silent
    frames are held back until speech resumes (or `flush`)."""

    def __init__(self, sr: int, max_pause_ms: float = 300.0, lead_keep_ms: float = 30.0, trail_keep_ms: float = 80.0,
                 rel_db: float = 32.0, floor_db: float = -58.0) -> None:
        self.frame = int(sr * 0.010)
        self.max_frames = max(1, int(max_pause_ms / 10))
        self.lead_frames = max(0, int(lead_keep_ms / 10))
        self.trail_frames = max(0, int(trail_keep_ms / 10))
        self.rel_db = rel_db
        self.floor_db = floor_db
        self._carry = np.zeros(0, dtype=np.float32)
        self._ref = -120.0                       # recent speech level (dB), decays slowly
        self._started = False                    # speech has begun
        self._held: list[np.ndarray] = []        # silent frames waiting for the next speech frame
        self.cut_ms = 0.0                        # how much silence was removed (for the benchmark)

    def process(self, x: np.ndarray) -> np.ndarray:
        buf = np.concatenate([self._carry, x.astype(np.float32)])
        n = len(buf) // self.frame
        self._carry = buf[n * self.frame:]
        out: list[np.ndarray] = []
        for i in range(n):
            fr = buf[i * self.frame:(i + 1) * self.frame]
            level = 10.0 * math.log10(float(np.mean(fr * fr)) + EPS)
            self._ref = max(level, self._ref - 0.03)                  # ~3 dB per 100 frames (1 s)
            if level < max(self.floor_db, self._ref - self.rel_db):
                self._held.append(fr)
                continue
            if self._held:
                keep = self.max_frames if self._started else self.lead_frames
                out.extend(self._held[:keep] if self._started else self._held[-keep:] if keep else [])
                self.cut_ms += 10.0 * max(0, len(self._held) - keep)
                self._held = []
            self._started = True
            out.append(fr)
        return np.concatenate(out) if out else np.zeros(0, dtype=np.float32)

    def flush(self) -> np.ndarray:
        out: list[np.ndarray] = []
        if self._started:
            out.extend(self._held[: self.trail_frames])
            self.cut_ms += 10.0 * max(0, len(self._held) - self.trail_frames)
        self._held = []
        return np.concatenate(out) if out else np.zeros(0, dtype=np.float32)


# ------------------------------------------------------------------------------------------------ voice activity
def speech_frames(x: np.ndarray, sr: int, frame_ms: float = 20.0, margin_db: float = 9.0, floor_db: float = -55.0,
                  hang_ms: float = 200.0) -> np.ndarray:
    """Boolean speech mask per frame: energy above the noise floor (the 10th percentile of frame levels) plus
    `margin_db`, above an absolute floor, held for `hang_ms` after it drops (the ends of words are quiet)."""
    frame = int(sr * frame_ms / 1000.0)
    lv = frame_rms_db(x, frame)
    if len(lv) == 0:
        return np.zeros(0, dtype=bool)
    real = lv[lv > -90.0]                                   # (digital silence says nothing about the room's noise)
    noise = float(np.percentile(real, 10)) if len(real) else -90.0
    if len(real) and float(np.percentile(real, 90)) - noise < 6.0:
        # a flat recording has no quiet part to measure the room by: loud enough to be speech, or nothing
        on = lv > -45.0
    else:
        on = (lv > max(floor_db, noise + margin_db))
    hang = int(hang_ms / frame_ms)
    if hang > 0 and on.any():
        # a positive origin looks back: a frame is speech if any of the last `hang` frames was
        on = uniform_filter1d(on.astype(np.float64), size=hang * 2 + 1, mode="constant", origin=hang) > 0.0
    return on


def trim_speech(x: np.ndarray, sr: int, pad_ms: float = 150.0, **kw) -> tuple[np.ndarray, float, float]:
    """(audio from the first to the last speech frame plus `pad_ms` on both sides, fraction of frames that are speech,
    seconds of speech). Empty audio when nothing looks like speech."""
    on = speech_frames(x, sr, **kw)
    if not on.any():
        return x[:0], 0.0, 0.0
    frame = int(sr * 0.020)
    idx = np.flatnonzero(on)
    a = max(0, int(idx[0] * frame - sr * pad_ms / 1000.0))
    b = min(len(x), int((idx[-1] + 1) * frame + sr * pad_ms / 1000.0))
    return x[a:b], float(on.mean()), float(on.sum() * 0.020)
