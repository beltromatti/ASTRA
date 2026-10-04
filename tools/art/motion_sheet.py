#!/usr/bin/env python3
"""A contact sheet of the capital ships' manoeuvring jets (art/blender/space3_motion_scene.py): one row for each manoeuvre, the stern and the bow of the ship, captioned with the jets that burn.

  uv run --python /opt/homebrew/bin/python3.13 --with pillow python tools/art/motion_sheet.py <dir with the tiles> --class aquila --out docs/progressi/spazio/jets_aquila.jpg
"""
from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

CAPTIONS = [
    ("yaw", "a turn to starboard begins: the jets that start it, at full"),
    ("trim", "the turn is held: a faint trim, blinking"),
    ("stop", "the turn ends: the other jets stop it"),
    ("brake", "braking at full acceleration: the jets that face forward"),
    ("slide", "sliding to starboard across her heading"),
    ("pitch", "the nose goes down"),
]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("dir")
    p.add_argument("--class", dest="cls", default="aquila")
    p.add_argument("--out", required=True)
    p.add_argument("--tile", type=int, default=720, help="width of a tile")
    a = p.parse_args()
    d = Path(a.dir)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 16)
        big = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 21)
    except OSError:
        font = big = ImageFont.load_default()
    rows = [(k, c) for k, c in CAPTIONS if (d / f"jets_{a.cls}_{k}_stern.jpg").exists()]
    first = Image.open(d / f"jets_{a.cls}_{rows[0][0]}_stern.jpg")
    W = a.tile
    H = int(first.height * W / first.width)
    cap = 34
    sheet = Image.new("RGB", (W * 2, (H + cap) * len(rows) + 40), (8, 10, 18))
    dr = ImageDraw.Draw(sheet)
    dr.text((12, 8), f"the {a.cls}'s manoeuvring jets, as the game fires them (stern on the left, bow on the right)", fill=(230, 235, 245), font=big)
    for r, (k, cap_text) in enumerate(rows):
        y = 40 + r * (H + cap)
        for c, view in enumerate(("stern", "bow")):
            im = Image.open(d / f"jets_{a.cls}_{k}_{view}.jpg").convert("RGB").resize((W, H), Image.LANCZOS)
            sheet.paste(im, (c * W, y + cap))
        dr.text((12, y + 8), cap_text, fill=(205, 210, 220), font=font)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=86)
    print(out, sheet.size)


if __name__ == "__main__":
    main()
