"""Look at a rendered cue: loudness over time, peaks, the loop seam, and a spectrogram image (for checking without ears).
uv run --with numpy --with scipy --with soundfile --with matplotlib python tools/music/inspect_audio.py file.wav out.png"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import soundfile as sf  # noqa: E402
from scipy.signal import spectrogram  # noqa: E402

x, sr = sf.read(sys.argv[1], always_2d=True)
mono = x.mean(axis=1)
win = int(0.5 * sr)
rms = np.array([np.sqrt(np.mean(mono[i:i + win] ** 2)) for i in range(0, len(mono) - win, win)])
db = 20 * np.log10(rms + 1e-9)
print(f"{sys.argv[1].split('/')[-1]}: {len(mono) / sr:.1f} s, peak {20 * np.log10(np.abs(x).max()):.1f} dBFS, "
      f"rms {20 * np.log10(np.sqrt(np.mean(mono ** 2))):.1f} dBFS, min/max 0.5s-rms {db.min():.1f}/{db.max():.1f} dB")
seam = np.abs(x[-1] - x[0]).max()
d1 = np.abs(np.diff(x[-200:], axis=0)).max()
print(f"loop seam jump {seam:.4f} (typical step at the end {d1:.4f})")
f, t, S = spectrogram(mono, sr, nperseg=4096, noverlap=3072)
fig, ax = plt.subplots(2, 1, figsize=(14, 7), gridspec_kw={"height_ratios": [3, 1]})
ax[0].pcolormesh(t, f, 10 * np.log10(S + 1e-12), shading="auto", vmin=-110, vmax=-30, cmap="magma")
ax[0].set_yscale("symlog", linthresh=200)
ax[0].set_ylim(30, 16000)
ax[1].plot(np.arange(len(db)) * 0.5, db)
ax[1].set_ylim(-60, 0)
plt.tight_layout()
plt.savefig(sys.argv[2], dpi=70)
