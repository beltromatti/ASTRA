"""The macOS app icon: the standard rounded square (824 px on the 1024 grid) of deep space — a navy-to-black depth, a
faint nebula, a scatter of stars — with the ASTRA Navy's eight-pointed star in its double ring, glowing ice-blue (the
motto of the ship's emblem is left out: it cannot be read at icon sizes).

Run: uv run --python /opt/homebrew/bin/python3.13 --with pillow --with numpy python tools/art/app_icon.py
  -> Build/Mac/Resources/Assets.xcassets/AppIcon.appiconset (every size the Mac asks for)
"""
import json
import math
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(ROOT, "Build", "Mac", "Resources", "Assets.xcassets")
S = 1024
ICE = (190, 225, 255)
rng = np.random.default_rng(2491)


def squircle_mask(size: int, inset: int, radius: int) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle((inset, inset, size - inset - 1, size - inset - 1), radius=radius, fill=255)
    return m


def space() -> Image.Image:
    y, x = np.mgrid[0:S, 0:S] / (S - 1)
    # depth: navy at the top left, near black at the bottom right
    t = np.clip(0.55 * x + 0.65 * y, 0, 1)
    top, bottom = np.array([14, 26, 58]), np.array([2, 4, 10])
    img = (top[None, None, :] * (1 - t[..., None]) + bottom[None, None, :] * t[..., None])
    # a faint nebula: two soft blobs of violet and teal
    for cx, cy, r, col in ((0.3, 0.72, 0.32, (70, 40, 110)), (0.74, 0.3, 0.28, (20, 80, 110))):
        d = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / r
        img += np.clip(1 - d, 0, 1)[..., None] ** 2 * np.array(col)[None, None, :] * 0.55
    img = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB").convert("RGBA")
    # stars: many faint, a few bright with a small glow
    d = ImageDraw.Draw(img)
    for _ in range(420):
        px, py = rng.uniform(0, S), rng.uniform(0, S)
        b = int(rng.uniform(70, 190))
        r = rng.choice([0.6, 0.9, 1.3], p=[0.6, 0.3, 0.1])
        d.ellipse((px - r, py - r, px + r, py + r), fill=(b, b, min(255, b + 25), 255))
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for _ in range(14):
        px, py = rng.uniform(80, S - 80), rng.uniform(80, S - 80)
        gd.ellipse((px - 7, py - 7, px + 7, py + 7), fill=(200, 225, 255, 160))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(5)))
    return img


def star(size: int) -> Image.Image:
    """The emblem without its words: the eight-pointed star of light in a double ring."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = size / 2
    col = (*ICE, 255)
    d.ellipse((size * 0.06, size * 0.06, size * 0.94, size * 0.94), outline=col, width=max(2, size // 70))
    d.ellipse((size * 0.2, size * 0.2, size * 0.8, size * 0.8), outline=col, width=max(2, size // 110))
    pts = []
    for k in range(16):
        a = math.pi * k / 8
        r = size * (0.40 if k % 4 == 0 else (0.22 if k % 4 == 2 else 0.06))
        pts.append((c + r * math.sin(a), c - r * math.cos(a)))
    d.polygon(pts, fill=col)
    d.ellipse((c - size * 0.035, c - size * 0.035, c + size * 0.035, c + size * 0.035), fill=(8, 12, 24, 255))
    return img


def icon() -> Image.Image:
    inset, radius = 100, 185
    base = space()
    em = star(560)
    halo = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    halo.alpha_composite(em, ((S - 560) // 2, (S - 560) // 2))
    halo = halo.filter(ImageFilter.GaussianBlur(22))
    tint = Image.new("RGBA", (S, S), (90, 170, 255, 0))
    tint.putalpha(halo.getchannel("A").point(lambda v: int(v * 0.85)))
    base.alpha_composite(tint)
    base.alpha_composite(em, ((S - 560) // 2, (S - 560) // 2))
    # a thin bright rim, as a lit edge of the plate
    rim = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(rim).rounded_rectangle((inset + 2, inset + 2, S - inset - 3, S - inset - 3), radius=radius - 2,
                                          outline=(120, 170, 230, 110), width=4)
    base.alpha_composite(rim)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    # the soft drop shadow every macOS icon has under its plate
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    shadow.putalpha(squircle_mask(S, inset, radius).point(lambda v: int(v * 0.45)))
    out.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)), (0, 10))
    base.putalpha(squircle_mask(S, inset, radius))
    out.alpha_composite(base)
    return out


def main() -> None:
    iconset = os.path.join(OUT, "AppIcon.appiconset")
    os.makedirs(iconset, exist_ok=True)
    big = icon()
    images = []
    for pt in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            px = pt * scale
            name = f"icon_{pt}x{pt}{'@2x' if scale == 2 else ''}.png"
            big.resize((px, px), Image.LANCZOS).save(os.path.join(iconset, name))
            images.append({"filename": name, "idiom": "mac", "scale": f"{scale}x", "size": f"{pt}x{pt}"})
    with open(os.path.join(iconset, "Contents.json"), "w") as f:
        json.dump({"images": images, "info": {"author": "xcode", "version": 1}}, f, indent=2)
    with open(os.path.join(OUT, "Contents.json"), "w") as f:
        json.dump({"info": {"author": "xcode", "version": 1}}, f, indent=2)
    big.save(os.path.join(ROOT, "art", "_cache", "ui", "ASTRA_AppIcon_1024.png"))
    print("APP_ICON_OK", iconset)


if __name__ == "__main__":
    main()
