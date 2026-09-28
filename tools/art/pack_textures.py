"""Prepare ASTRA texture sets from CC0 sources (ambientCG) + procedural maps.

Output (art/_cache/textures/, gitignored — reproducible from the downloads):
  T_<Set>_BC.png   base color (sRGB)
  T_<Set>_N.png    normal, DirectX convention (Unreal)
  T_<Set>_ORM.png  R = ambient occlusion (1 if absent), G = roughness, B = metallic   (linear)
  T_<Set>_OP.png   opacity (only when the source has one)
  T_ASTRA_MacroNoise.png   tileable fBm noise, R/G/B = three independent octave mixes (linear)
  T_ASTRA_Scratches_M.png  scratch mask (linear)

Run: uv run --with pillow --with numpy python tools/art/pack_textures.py
"""
from __future__ import annotations

import os
import sys

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "art", "_downloads", "ambientcg")
OUT = os.path.join(ROOT, "art", "_cache", "textures")

# ASTRA name -> ambientCG id
SETS = {
    "PanelPaint": "Plastic010",
    "Gunmetal": "Metal046A",
    "DeckRubber": "Rubber004",
    "Walkway": "MetalWalkway013",
    "Brushed": "Metal032",
    # New Ravenna's ground (the terrain material blends them by slope and height)
    "Rock": "Rock035",
    "Grass": "Grass004",
    "Meadow": "Ground037",
    "Sand": "Ground054",
    "Snow": "Snow010A",
    # the walls of other worlds: red desert sandstone, and a pale rock that tints to regolith grey or blue ice
    "RockRed": "Rock029",
    "RockLight": "Rock026",
    # the medbay's cloth: blankets and curtains (a coarse linen), sheets, pillows and gowns (a fine cotton)
    "Linen": "Fabric036",
    "Cotton": "Fabric032",
    # the Captain's quarters: dark wood for the furniture and panels, a navy carpet
    "WoodDark": "Wood051",
    "Carpet": "Carpet012",
}


def load(path: str, mode: str = "L") -> np.ndarray:
    return np.asarray(Image.open(path).convert(mode), dtype=np.float32) / 255.0


def save(arr: np.ndarray, path: str) -> None:
    arr = np.clip(arr * 255.0 + 0.5, 0, 255).astype(np.uint8)
    Image.fromarray(arr).save(path, optimize=True)


def find(folder: str, suffix: str) -> str | None:
    for f in os.listdir(folder):
        if f.endswith(suffix):
            return os.path.join(folder, f)
    return None


def pack_set(name: str, acg: str) -> None:
    folder = os.path.join(SRC, acg)
    bc = find(folder, "_Color.jpg")
    n = find(folder, "_NormalDX.jpg")
    r = find(folder, "_Roughness.jpg")
    m = find(folder, "_Metalness.jpg")
    ao = find(folder, "_AmbientOcclusion.jpg")
    op = find(folder, "_Opacity.jpg")
    Image.open(bc).convert("RGB").save(os.path.join(OUT, f"T_{name}_BC.png"), optimize=True)
    Image.open(n).convert("RGB").save(os.path.join(OUT, f"T_{name}_N.png"), optimize=True)
    rough = load(r)
    shape = rough.shape
    metal = load(m) if m else np.zeros(shape, np.float32)
    occl = load(ao) if ao else np.ones(shape, np.float32)
    save(np.dstack([occl, rough, metal]), os.path.join(OUT, f"T_{name}_ORM.png"))
    if op:
        Image.open(op).convert("L").save(os.path.join(OUT, f"T_{name}_OP.png"), optimize=True)
    print(f"  {name:12s} <- {acg}: rough {rough.mean():.2f}±{rough.std():.2f}, metal {metal.mean():.2f}")


def periodic_fbm(size: int, seed: int, beta: float) -> np.ndarray:
    """Tileable noise via spectral synthesis (power spectrum ~ 1/f^beta): perfectly periodic by construction."""
    rng = np.random.default_rng(seed)
    fx = np.fft.fftfreq(size)[:, None]
    fy = np.fft.fftfreq(size)[None, :]
    f = np.sqrt(fx * fx + fy * fy)
    f[0, 0] = 1.0
    spectrum = (rng.normal(size=(size, size)) + 1j * rng.normal(size=(size, size))) / f ** (beta / 2.0)
    spectrum[0, 0] = 0.0
    field = np.real(np.fft.ifft2(spectrum))
    field = (field - field.mean()) / (field.std() + 1e-8)
    return np.clip(0.5 + 0.18 * field, 0.0, 1.0)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    print("Texture sets:")
    for name, acg in SETS.items():
        pack_set(name, acg)
    # macro variation: three different "grains" (large blotches, medium cloud, fine mottling)
    noise = np.dstack([periodic_fbm(1024, 11, 3.2), periodic_fbm(1024, 23, 2.4), periodic_fbm(1024, 37, 1.6)])
    save(noise, os.path.join(OUT, "T_ASTRA_MacroNoise.png"))
    scratches = load(find(os.path.join(SRC, "Scratches004"), "_Opacity.jpg"))
    save(scratches, os.path.join(OUT, "T_ASTRA_Scratches_M.png"))
    print("Procedural: T_ASTRA_MacroNoise, T_ASTRA_Scratches_M")
    print("OUT", OUT)


if __name__ == "__main__":
    sys.exit(main())
