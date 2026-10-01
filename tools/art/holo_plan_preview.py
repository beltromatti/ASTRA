#!/usr/bin/env python3
"""Draws what the holo table's tactical plot would show of a battle, as the Captain in the chair sees it (docs/SCALA.md).

The war bench writes the plan (Source/ASTRA/AstraHoloPlan.*: which ships get a name, which are a tagged group, where each label goes in the
viewer's picture plane) for the battle at chosen times:

  python3 tools/war.py run --scenario scale_30x150 --aquila --seconds 200 --holo-at "40,80,120,160"       # Saved/War/holo_<t>.json
  uv run --python /opt/homebrew/bin/python3.13 --with pillow python tools/art/holo_plan_preview.py Saved/War/holo_*.json [--out docs/progressi/scala]

One PNG a plan: the disc with its range rings, the ships' icons (the Aquila light, ASTRA blue, hostile red, unknown grey; a white ring round those that
must be named), the craft as dots, the groups as circles with their number, every label in its box with its leader line. If two boxes overlap or a label
sits on an icon, it is the layout that is wrong: the picture is the check.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

COL = {
    "aquila": (158, 242, 255),
    "astra": (56, 184, 255),
    "hostile": (255, 51, 20),
    "unknown": (158, 168, 178),
    "neutral": (242, 224, 115),
}
BG = (7, 14, 24)
SCALE = 5.2                      # pixels to the centimetre of the picture plane
W, H = 1500, 1000


def font(px: float) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for p in ("/System/Library/Fonts/Menlo.ttc", "/System/Library/Fonts/Monaco.ttf", "/Library/Fonts/Arial.ttf"):
        try:
            return ImageFont.truetype(p, max(8, int(px)))
        except OSError:
            continue
    return ImageFont.load_default()


def load(path: Path) -> dict:
    raw = path.read_bytes()
    enc = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8"
    return json.loads(raw.decode(enc))


def render(plan: dict) -> Image.Image:
    im = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(im, "RGBA")
    ux, uy = plan["us"]
    cx, cy = W / 2 - ux * SCALE, H * 0.56 + uy * SCALE          # the picture's origin; the Aquila's own spot is at the middle

    def px(p) -> tuple[float, float]:
        return cx + p[0] * SCALE, cy - p[1] * SCALE

    for k, ring in enumerate(plan["rings"]):
        d.line([px(p) for p in ring], fill=(40, 120, 170, 150 if k == 0 else 80), width=2 if k == 0 else 1)
    for p in plan["craft"]:
        x, y = px(p["p"])
        c = COL[p["side"]]
        d.ellipse([x - 1.8, y - 1.8, x + 1.8, y + 1.8], fill=c + (230,))
    for p in plan["missiles"]:
        x, y = px(p["p"])
        d.ellipse([x - 1, y - 1, x + 1, y + 1], fill=COL[p["side"]] + (200,))
    for p in plan["threats"]:
        x, y = px(p)
        ox, oy = px(plan["us"])
        d.line([(x, y), (ox, oy)], fill=(255, 51, 20, 90), width=1)
    for c in plan["clusters"]:
        x, y = px(c["p"])
        col = COL[c["side"]]
        d.ellipse([x - 5, y - 5, x + 5, y + 5], outline=col + (160,), width=1)
    for ic in plan["icons"]:
        x, y = px(ic["p"])
        r = max(3.0, ic["size"] * SCALE * 0.3)                    # (the arrowhead's own extent; the obstacle labels keep clear of is the faint circle)
        ro = ic["r"] * SCALE
        col = COL[ic["side"]]
        a = 110 if ic["beyond"] else 255
        d.ellipse([x - ro, y - ro, x + ro, y + ro], outline=col + (60,), width=1)
        d.ellipse([x - r, y - r, x + r, y + r], fill=col + (a,))
        if ic["must"]:
            d.ellipse([x - r - 3, y - r - 3, x + r + 3, y + r + 3], outline=(255, 255, 255, 220), width=2)
    for lb in plan["labels"]:
        lines = lb["text"].split("<br>")
        col = tuple(int(255 * v) for v in lb["col"])
        bw, bh = lb["w"] * SCALE, lb["h"] * SCALE                # the box the layout reckoned: the picture draws exactly it
        size = min(lb["size"] * SCALE * 0.95, bw / max(len(t) for t in lines) / 0.6)
        f = font(size)
        lh = bh / len(lines)
        x, y = px(lb["p"])                                       # the bottom centre of the text
        x0, y0, x1, y1 = x - bw / 2, y - bh, x + bw / 2, y
        if lb["leader"]:
            fx, fy = px(lb["from"])
            d.line([(fx, fy), (x, y - bh / 2)], fill=col + (140,), width=1)
        d.rectangle([x0, y0, x1, y1], fill=(0, 0, 0, 110), outline=col + ((200 if lb["tag"] else 90),))
        for n, t in enumerate(lines):
            d.text((x - d.textlength(t, font=f) / 2, y0 + n * lh + (lh - size) * 0.35), t, font=f, fill=col + (255,))
    head = (f"t = {plan['t']:.0f} s   range {plan['range_km']:.0f} km   {plan['blips']} blips   {len(plan['icons'])} ships   {len(plan['craft'])} craft   "
            f"{len(plan['labels'])} labels ({plan['dropped']} left out)   {len(plan['clusters'])} groups   {'DENSE' if plan['dense'] else 'sparse'}   tilt {plan['tilt_deg']:.0f} deg")
    d.text((16, 12), head, font=font(15), fill=(180, 220, 255, 255))
    return im


def overlaps(plan: dict) -> list[str]:
    """What the layout promised and the picture should show: no two labels cover each other, no label covers an icon (but its own). Returns the offences."""
    boxes = []
    for lb in plan["labels"]:
        x, y = lb["p"]
        boxes.append((lb["text"].split("<br>")[0], x - lb["w"] / 2, y, x + lb["w"] / 2, y + lb["h"]))
    bad = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            if min(a[3], b[3]) - max(a[1], b[1]) > 0.01 and min(a[4], b[4]) - max(a[2], b[2]) > 0.01:
                bad.append(f"labels '{a[0]}' and '{b[0]}' overlap")
    for a in boxes:
        for ic in plan["icons"]:
            x, y = ic["p"]
            dx = max(a[1] - x, 0.0, x - a[3])
            dy = max(a[2] - y, 0.0, y - a[4])
            if dx * dx + dy * dy < (ic["r"] * 0.98) ** 2 and (abs((a[1] + a[3]) / 2 - x) > 0.5 or abs(a[2] - y) > 25):
                bad.append(f"label '{a[0]}' covers the icon {ic['id']}")
    return bad


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plans", nargs="+")
    ap.add_argument("--out", default="")
    a = ap.parse_args()
    failed = 0
    for p in a.plans:
        path = Path(p)
        plan = load(path)
        out = Path(a.out) / (path.stem + ".png") if a.out else path.with_suffix(".png")
        out.parent.mkdir(parents=True, exist_ok=True)
        render(plan).save(out)
        bad = overlaps(plan)
        failed += len(bad)
        print(out, f"{len(plan['labels'])} labels, {len(bad)} overlaps")
        for b in bad[:12]:
            print("   !", b)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    sys.exit(main())
