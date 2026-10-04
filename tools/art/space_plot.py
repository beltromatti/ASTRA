#!/usr/bin/env python3
"""A plan of a system's living space from a record of the bench (tools/space.py run): the places, the lanes, and where the vessels and patrols were (a track for each vessel,
coloured by what it was doing), seen from above (x to the right, y up: the system frame, km) and from the side. For looking at whether the traffic goes where the lanes go.

  uv run --python /opt/homebrew/bin/python3.13 --with pillow python tools/art/space_plot.py Saved/Space/run.json --out docs/progressi/spazio/plan_aurelia.png [--at 1800] [--span 260]
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

STATE_COL = {"docked": (120, 120, 130), "departing": (255, 210, 120), "cruise": (120, 200, 255), "docking": (255, 210, 120), "holding": (255, 160, 60), "gate_out": (255, 255, 255),
             "gate_in": (255, 255, 255), "fleeing": (255, 70, 60), "hiding": (170, 60, 200), "away": (40, 40, 40)}
KIND_COL = {"gate": (180, 120, 255), "keeper": (120, 255, 200), "arsenal": (120, 170, 255), "refinery": (255, 160, 80), "station": (255, 230, 120), "orbit": (150, 150, 255), "belt": (200, 160, 120)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("record")
    p.add_argument("--out", default="Saved/Space/plan.png")
    p.add_argument("--span", type=float, default=270.0, help="half-width of the plan, km")
    p.add_argument("--size", type=int, default=1500)
    p.add_argument("--at", type=float, default=-1.0, help="only the vessels at this battle time (a dot each) instead of the tracks")
    a = p.parse_args()
    d = json.loads(Path(a.record).read_text())
    W = a.size
    img = Image.new("RGB", (W, W + W // 3), (8, 10, 18))
    dr = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 15)
    except OSError:
        font = ImageFont.load_default()
    s = W / (2 * a.span)

    def top(x, y):
        return (W / 2 + x * s, W / 2 - y * s)

    def side(x, z):
        return (W / 2 + x * s, W + W // 6 - z * s * 2.2)

    # rings of range
    for r in (50, 100, 150, 200, 250):
        c = top(0, 0)
        dr.ellipse((c[0] - r * s, c[1] - r * s, c[0] + r * s, c[1] + r * s), outline=(30, 36, 52))
        dr.text((c[0] + r * s * 0.707, c[1] - r * s * 0.707), f"{r} km", fill=(70, 80, 100), font=font)
    # lanes
    for l in d["layout"]["lanes"]:
        pts = l["km"]
        dr.line([top(x, y) for x, y, z in pts], fill=(60, 80, 120), width=2)
        dr.line([side(x, z) for x, y, z in pts], fill=(60, 80, 120), width=1)
    for n in d["layout"]["nodes"]:
        x, y, z = n["km"]
        col = KIND_COL.get(n["kind"], (255, 255, 255))
        t = top(x, y)
        dr.ellipse((t[0] - 7, t[1] - 7, t[0] + 7, t[1] + 7), outline=col, width=2)
        dr.text((t[0] + 10, t[1] - 8), n["name"], fill=col, font=font)
        q = side(x, z)
        dr.ellipse((q[0] - 4, q[1] - 4, q[0] + 4, q[1] + 4), outline=col)
    c = top(0, 0)
    dr.line((c[0] - 10, c[1], c[0] + 10, c[1]), fill=(255, 255, 255))
    dr.line((c[0], c[1] - 10, c[0], c[1] + 10), fill=(255, 255, 255))
    dr.text((c[0] + 8, c[1] + 6), "the Aquila comes in", fill=(255, 255, 255), font=font)
    # the vessels
    for f in d["frames"]:
        if a.at >= 0 and abs(f["t"] - a.at) > d["frames"][1]["t"] - d["frames"][0]["t"]:
            continue
        for v in f["v"]:
            vid, state, x, y, z, speed, alert = v
            col = STATE_COL.get(state, (200, 200, 200))
            t = top(x, y)
            r = 3 if a.at >= 0 else 1
            dr.ellipse((t[0] - r, t[1] - r, t[0] + r, t[1] + r), fill=col)
            q = side(x, z)
            dr.ellipse((q[0] - 1, q[1] - 1, q[0] + 1, q[1] + 1), fill=col)
        for pt in f["p"]:
            pid, st, x, y, z = pt
            t = top(x, y)
            dr.ellipse((t[0] - 1, t[1] - 1, t[0] + 1, t[1] + 1), fill=(255, 255, 160) if st == 0 else (255, 120, 120))
    # the key
    y0 = 10
    for k, col in STATE_COL.items():
        dr.rectangle((10, y0, 22, y0 + 12), fill=col)
        dr.text((28, y0 - 2), k, fill=(200, 200, 210), font=font)
        y0 += 20
    dr.text((W - 420, 10), f"{d['system']} seed {d['seed']} {d['battle_seconds']:.0f} s", fill=(200, 200, 210), font=font)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    img.save(a.out)
    print(a.out)


if __name__ == "__main__":
    main()
