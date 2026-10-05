#!/usr/bin/env python3
"""A contact sheet of a series of pictures from the war's visual effects (astra.fx.series: Saved/Play/<prefix>_NN.png, _NN_cam.png, _NN_vs.png), and numbers from them.

  uv run --python /opt/homebrew/bin/python3.13 --with numpy --with pillow python tools/art/war_fx_series_sheet.py <prefix> [--suffix _cam|_vs|""] [--cols 6] [--tile 340]
                                                                                     [--first 0] [--count 40] [--stats] [--dir Saved/Play]

--suffix picks the series' picture: "" the game's own view (no UI), "_cam" the free camera (astra.fx.cam), "_vs" the main viewscreen's feed. The sheet is written next to the pictures
(<prefix><suffix>_sheet.png), the frame's number in yellow in a corner. --stats prints, for each frame, how bright it is (the mean luma, the share of pixels over 0.9 and over 0.5 in display
terms, and the box round those over 0.6): "it blinds the bridge" and "it is hard to see" as numbers (docs/VFX.md §13, §19).
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("prefix")
    ap.add_argument("--suffix", default="")
    ap.add_argument("--cols", type=int, default=6)
    ap.add_argument("--tile", type=int, default=340)
    ap.add_argument("--first", type=int, default=0)
    ap.add_argument("--count", type=int, default=40)
    ap.add_argument("--stats", action="store_true")
    ap.add_argument("--dir", default=os.path.join(ROOT, "Saved", "Play"))
    a = ap.parse_args()
    files = sorted(glob.glob(os.path.join(a.dir, f"{a.prefix}_[0-9][0-9]{a.suffix}.png")))[a.first:a.first + a.count]
    if not files:
        print("no pictures")
        return 1
    tiles = []
    for f in files:
        im = Image.open(f).convert("RGB")
        if a.stats:
            arr = np.asarray(im, np.float32) / 255.0
            luma = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
            ys, xs = np.nonzero(luma > 0.6)
            box = (int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())) if len(xs) else None
            print(f"{os.path.basename(f):26s} mean {luma.mean():.3f}  white {100 * float((luma > 0.9).mean()):5.1f}%  >0.5 {100 * float((luma > 0.5).mean()):5.1f}%  bbox>0.6 {box}")
        th = int(im.height * a.tile / im.width)
        im = im.resize((a.tile, th), Image.LANCZOS)
        ImageDraw.Draw(im).text((4, 2), os.path.basename(f)[len(a.prefix) + 1:len(a.prefix) + 3], fill=(255, 255, 0))
        tiles.append(im)
    th = tiles[0].height
    rows = (len(tiles) + a.cols - 1) // a.cols
    sheet = Image.new("RGB", (a.tile * a.cols, th * rows))
    for k, t in enumerate(tiles):
        sheet.paste(t, ((k % a.cols) * a.tile, (k // a.cols) * th))
    out = os.path.join(a.dir, f"{a.prefix}{a.suffix}_sheet.png")
    sheet.save(out)
    print(len(files), "pictures ->", out, sheet.size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
