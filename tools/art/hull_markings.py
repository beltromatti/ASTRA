"""Hull markings: a ship's name and hull number painted on her flanks, with the ASTRA Navy emblem (Barlow Condensed —
OFL). Navy-blue paint on a transparent ground: the decal material (M_ASTRA_HullDecal) lays it onto the plating.

  T_HULL_Name_Aquila   "ASN AQUILA · CVC-01" (the first carrier cruiser of her class)

Run: uv run --with pillow python tools/art/hull_markings.py -> art/_cache/signage/T_HULL_*.png
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from signage import OUT, TITLE, emblem  # noqa: E402

PAINT = (255, 255, 255)   # the material tints it (navy on the Aquila's pale plating)


def spaced(d: ImageDraw.ImageDraw, xy, text: str, f: ImageFont.FreeTypeFont, spacing: float, fill) -> float:
    """Draws text with extra letter spacing (stencilled hull lettering is wide); returns the width drawn."""
    x, y = xy
    for ch in text:
        d.text((x, y), ch, font=f, fill=fill)
        x += d.textlength(ch, font=f) + spacing
    return x - xy[0] - spacing


def width(text: str, f: ImageFont.FreeTypeFont, spacing: float) -> float:
    img = Image.new("L", (8, 8))
    d = ImageDraw.Draw(img)
    return sum(d.textlength(ch, font=f) for ch in text) + spacing * (len(text) - 1)


def hull_name(name: str, number: str, out: str) -> None:
    W, H = 4096, 1024
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # the emblem, then the name, and the hull number under it; a rule between them
    em = emblem(760, color=PAINT)
    img.alpha_composite(em, (60, (H - 760) // 2))
    big = ImageFont.truetype(TITLE, 560)
    small = ImageFont.truetype(TITLE, 250)
    x0 = 900
    wn = width(name, big, 40)
    scale = min(1.0, (W - x0 - 60) / wn)
    if scale < 1.0:
        big = ImageFont.truetype(TITLE, int(560 * scale))
        wn = width(name, big, 40 * scale)
    spaced(d, (x0, 40), name, big, 40 * scale, (*PAINT, 255))
    d.rectangle((x0, 640, x0 + wn, 662), fill=(*PAINT, 255))
    spaced(d, (x0 + 6, 690), number, small, 60, (*PAINT, 255))
    img.save(out)


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    hull_name("ASN AQUILA", "CVC-01", os.path.join(OUT, "T_HULL_Name_Aquila.png"))
    # the sisters that carry her name after a loss (the Captain's new command): CVC-03, then -04, -05
    for n in (3, 4, 5):
        hull_name("ASN AQUILA", f"CVC-0{n}", os.path.join(OUT, f"T_HULL_Name_Aquila_0{n}.png"))
    print("hull markings ->", OUT)


if __name__ == "__main__":
    main()
