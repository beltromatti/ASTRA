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


VIEWS = {"above": (0, 1), "side": (0, 2), "front": (1, 2)}
DEFAULT_VIEW = {"SM_PLACE_KeeperRing": "front", "SM_PART_ArsenalCrane": "side"}           # (a ring is seen from its axis: that is where its hole is)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--solids", default=str(ROOT / "data" / "space" / "solids.json"))
    p.add_argument("--out", default=str(ROOT / "Saved" / "Space" / "place_solids.jpg"))
    p.add_argument("--only", default="")
    p.add_argument("--cell", type=int, default=740, help="width of a panel; the sheet has two columns")
    p.add_argument("--all-views", action="store_true", help="above, side and front of each (a tall sheet) instead of one view of each")
    a = p.parse_args()
    d = json.loads(Path(a.solids).read_text())["meshes"]
    names = [n for n in d if not a.only or n in a.only.split(",")]
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 14)
        big = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 16)
    except OSError:
        font = big = ImageFont.load_default()
    panels: list[tuple[str, Image.Image]] = []
    for name in names:
        m = d[name]
        cell = m["cell"]
        origin = m["origin"]
        boxes = np.array(m["boxes"], np.int64)
        lo3 = [origin[k] + boxes[:, k].min() * cell for k in range(3)]
        hi3 = [origin[k] + (boxes[:, k] + boxes[:, 3 + k]).max() * cell for k in range(3)]
        ext = [hi3[k] - lo3[k] for k in range(3)]
        views = list(VIEWS) if a.all_views else [DEFAULT_VIEW.get(name, "above")]
        for view in views:
            ax = VIEWS[view]
            scale = min((a.cell - 40) / max(ext[ax[0]], 1.0), 300.0 / max(ext[ax[1]], 1.0))
            w = int(ext[ax[0]] * scale) + 40
            h = int(ext[ax[1]] * scale) + 30
            img = shadow(boxes, cell, origin, ax, scale, (lo3[ax[0]], lo3[ax[1]]), (max(w, 60), h))
            ImageDraw.Draw(img).rectangle((24, 8, 24 + 12 * scale, 8 + 3 * scale), fill=(255, 150, 60))
            cap = f"{name} {view}: {len(boxes)} boxes of {cell:g} m, {ext[0]:.0f} x {ext[1]:.0f} x {ext[2]:.0f} m"
            panels.append((cap, img))
    colw = a.cell
    rows: list[list[tuple[str, Image.Image]]] = []
    for i in range(0, len(panels), 2):
        rows.append(panels[i:i + 2])
    H = sum(max(im.height for _, im in r) + 30 for r in rows) + 30
    sheet = Image.new("RGB", (colw * 2, H), (8, 10, 18))
    dr = ImageDraw.Draw(sheet)
    dr.text((12, 6), "the solid parts of the places' hulls, as the game tests them for the Captain's Falcon (the orange mark is the Falcon, 12 m)", fill=(230, 235, 245), font=big)
    y = 30
    for r in rows:
        for c, (cap, im) in enumerate(r):
            dr.text((c * colw + 12, y + 2), cap, fill=(170, 180, 195), font=font)
            sheet.paste(im, (c * colw, y + 22))
        y += max(im.height for _, im in r) + 30
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=86) if out.suffix.lower() in (".jpg", ".jpeg") else sheet.save(out)
    print(out, sheet.size)


if __name__ == "__main__":
    main()
