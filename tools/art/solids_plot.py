#!/usr/bin/env python3
"""The solid parts of the places' hulls (data/space/solids.json, art/blender/space3_solids.py) drawn as the game tests them: each mesh seen from above (x to the right, y up), from the side (x to
the right, z up) and from the front (y to the right, z up), as the shadow its boxes cast, with the Captain's Falcon to scale (the orange mark, 12 m) and the boxes' count. A picture to check that
a ring has its hole, that bays are open, that a hull is whole.

  uv run --python /opt/homebrew/bin/python3.13 --with pillow python tools/art/solids_plot.py --out docs/progressi/spazio/place_solids.jpg [--only SM_PLACE_Keeper,SM_PLACE_Arsenal]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent.parent


def shadow(boxes: np.ndarray, cell: float, origin, axes: tuple[int, int], scale: float, lo: tuple[float, float], size: tuple[int, int]) -> Image.Image:
    """The projection of the boxes on two of the axes (a count of how many boxes' depth the view looks through, darker where it is deeper), as an image."""
    w, h = size
    acc = np.zeros((h, w), np.float32)
    for b in boxes:
        a0 = (origin[axes[0]] + b[axes[0]] * cell - lo[0]) * scale
        a1 = (origin[axes[0]] + (b[axes[0]] + b[3 + axes[0]]) * cell - lo[0]) * scale
        c0 = (origin[axes[1]] + b[axes[1]] * cell - lo[1]) * scale
        c1 = (origin[axes[1]] + (b[axes[1]] + b[3 + axes[1]]) * cell - lo[1]) * scale
        x0, x1 = int(a0) + 20, max(int(a1), int(a0) + 1) + 20
        y1, y0 = h - 14 - int(c0), h - 14 - max(int(c1), int(c0) + 1)
        acc[max(y0, 0):max(y1, 0), max(x0, 0):max(x1, 0)] += 1.0
    img = np.zeros((h, w, 3), np.uint8)
    img[:] = (8, 10, 18)
    m = acc > 0
    depth = np.clip(acc / 6.0, 0.0, 1.0)
    img[m] = (np.array((70, 120, 190)) + depth[m, None] * np.array((60, 80, 60))).astype(np.uint8)
    return Image.fromarray(img)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--solids", default=str(ROOT / "data" / "space" / "solids.json"))
    p.add_argument("--out", default=str(ROOT / "Saved" / "Space" / "place_solids.jpg"))
    p.add_argument("--only", default="")
    p.add_argument("--width", type=int, default=1500)
    a = p.parse_args()
    d = json.loads(Path(a.solids).read_text())["meshes"]
    names = [n for n in d if not a.only or n in a.only.split(",")]
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 15)
        big = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 19)
    except OSError:
        font = big = ImageFont.load_default()
    W = a.width
    panels: list[tuple[str, str, Image.Image]] = []
    for name in names:
        m = d[name]
        cell = m["cell"]
        origin = m["origin"]
        boxes = np.array(m["boxes"], np.int64)
        lo3 = [origin[k] + boxes[:, k].min() * cell for k in range(3)]
        hi3 = [origin[k] + (boxes[:, k] + boxes[:, 3 + k]).max() * cell for k in range(3)]
        ext = [hi3[k] - lo3[k] for k in range(3)]
        scale = min((W - 40) / max(ext[0], 1.0), 430.0 / max(ext[1], ext[2], 1.0))
        views = (("from above", (0, 1)), ("from the side", (0, 2)), ("from the front", (1, 2)))
        head = f"{name}: {len(boxes)} boxes of cell {cell:g} m, {ext[0]:.0f} x {ext[1]:.0f} x {ext[2]:.0f} m (the orange mark is the Falcon, 12 m)"
        for i, (label, ax) in enumerate(views):
            w = int(ext[ax[0]] * scale) + 40
            h = int(ext[ax[1]] * scale) + 30
            img = shadow(boxes, cell, origin, ax, scale, (lo3[ax[0]], lo3[ax[1]]), (max(w, 60), h))
            dr = ImageDraw.Draw(img)
            dr.rectangle((24, 8, 24 + 12 * scale, 8 + 3 * scale), fill=(255, 150, 60))
            panels.append((head if i == 0 else "", label, img))
    H = sum(img.height + 34 + (30 if head else 0) for head, _, img in panels)
    sheet = Image.new("RGB", (W, H), (8, 10, 18))
    dr = ImageDraw.Draw(sheet)
    y = 0
    for head, label, img in panels:
        if head:
            dr.text((14, y + 6), head, fill=(230, 235, 245), font=big)
            y += 30
        dr.text((14, y + 2), label, fill=(140, 150, 170), font=font)
        sheet.paste(img, (0, y + 20))
        y += img.height + 34
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=86) if out.suffix.lower() in (".jpg", ".jpeg") else sheet.save(out)
    print(out)


if __name__ == "__main__":
    main()
