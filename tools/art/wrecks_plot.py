#!/usr/bin/env python3
"""A map of what the war has left in a system, from a record of the bench (tools/space.py run: its "wrecks" section): each ship lost with her field of debris (a ring: how far her farthest
chunk has got), her pieces (squares), her lifepods (dots: green while the beacon calls, grey when silent), the Aquila with the range her sensors hear a beacon at, the Gate and the places.
Seen from above (x to the right, y up: the system frame, km) and from the side.

  uv run --python /opt/homebrew/bin/python3.13 --with pillow python tools/art/wrecks_plot.py Saved/Space/stress.json --out docs/progressi/spazio/wrecks_map.jpg [--span 90]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FACTION_COL = {0: (110, 190, 255), 1: (255, 130, 90), 2: (230, 210, 120)}      # ASTRA, the Mandate, the rest
KIND_COL = {"gate": (180, 120, 255), "keeper": (120, 255, 200), "arsenal": (120, 170, 255), "refinery": (255, 160, 80), "station": (255, 230, 120), "orbit": (150, 150, 255), "belt": (200, 160, 120)}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("record")
    p.add_argument("--out", default="Saved/Space/wrecks_map.jpg")
    p.add_argument("--span", type=float, default=0.0, help="half-width of the map, km (0: to fit the wreckage)")
    p.add_argument("--size", type=int, default=1500)
    a = p.parse_args()
    d = json.loads(Path(a.record).read_text())
    w = d.get("wrecks")
    if not w:
        raise SystemExit("this record has no wrecks section (run the bench with losses: astra.space.lose)")
    W = a.size
    aq = w["aquila_km"]
    pts = [(aq[0], aq[1])]
    for s in w["sites"]:
        pts += [(q[0], q[1]) for q in s["pieces"]] + [(s["field_mid"][0], s["field_mid"][1])]
    span = a.span or max(30.0, 1.15 * max(max(abs(x - aq[0]), abs(y - aq[1])) for x, y in pts))
    img = Image.new("RGB", (W, W + W // 4), (8, 10, 18))
    dr = ImageDraw.Draw(img, "RGBA")
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 14)
        big = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 20)
    except OSError:
        font = big = ImageFont.load_default()
    s = W / (2 * span)

    def top(x, y):
        return (W / 2 + (x - aq[0]) * s, W / 2 - (y - aq[1]) * s)

    def side(x, z):
        return (W / 2 + (x - aq[0]) * s, W + W // 8 - (z - aq[2]) * s * 1.6)

    # rings of range from the Aquila, the one her sensors hear a beacon at drawn apart
    step = 10 if span < 70 else (20 if span < 160 else 50)
    r = step
    while r < span * 1.45:
        c = top(aq[0], aq[1])
        dr.ellipse((c[0] - r * s, c[1] - r * s, c[0] + r * s, c[1] + r * s), outline=(30, 36, 52))
        dr.text((c[0] + r * s * 0.707 + 4, c[1] - r * s * 0.707), f"{r} km", fill=(70, 80, 100), font=font)
        r += step
    br = w["beacon_km"]
    c = top(aq[0], aq[1])
    dr.ellipse((c[0] - br * s, c[1] - br * s, c[0] + br * s, c[1] + br * s), outline=(90, 200, 150, 160), width=2)
    dr.text((c[0] - 95, c[1] - br * s - 22), f"beacons heard to {br:.0f} km", fill=(90, 200, 150), font=font)
    # the places
    for n in d["layout"]["nodes"]:
        x, y, z = n["km"]
        col = KIND_COL.get(n["kind"], (255, 255, 255))
        t = top(x, y)
        if -40 < t[0] < W + 40 and -40 < t[1] < W + 40:
            dr.ellipse((t[0] - 7, t[1] - 7, t[0] + 7, t[1] + 7), outline=col, width=2)
            dr.text((t[0] + 10, t[1] - 8) if t[0] < W - 230 else (t[0] - 10 - 8.4 * len(n["name"]), t[1] - 8), n["name"], fill=col, font=font)
    g = top(w["gate_km"][0], w["gate_km"][1])
    dr.ellipse((g[0] - 9, g[1] - 9, g[0] + 9, g[1] + 9), outline=(180, 120, 255), width=3)
    # the Aquila
    dr.line((c[0] - 11, c[1], c[0] + 11, c[1]), fill=(255, 255, 255), width=2)
    dr.line((c[0], c[1] - 11, c[0], c[1] + 11), fill=(255, 255, 255), width=2)
    dr.text((c[0] + 12, c[1] + 6), "the Aquila", fill=(255, 255, 255), font=font)
    # the wreckage
    alive = silent = recovered = 0
    for site in w["sites"]:
        col = FACTION_COL.get(site["faction"], (200, 200, 200))
        m = site["field_mid"]
        t = top(m[0], m[1])
        rr = site["field_km"] * s
        dr.ellipse((t[0] - rr, t[1] - rr, t[0] + rr, t[1] + rr), fill=col + (14,), outline=col + (60,))
        for q in site["pieces"]:
            u = top(q[0], q[1])
            dr.rectangle((u[0] - 3, u[1] - 3, u[0] + 3, u[1] + 3), fill=col)
        for pod in site["pods"]:
            u = top(pod["p"][0], pod["p"][1])
            if pod["state"] == 1:
                recovered += 1
                dr.ellipse((u[0] - 3, u[1] - 3, u[0] + 3, u[1] + 3), outline=(90, 200, 150))
            elif pod["beacon"]:
                alive += 1
                dr.ellipse((u[0] - 4, u[1] - 4, u[0] + 4, u[1] + 4), fill=(120, 255, 170))
                dr.ellipse((u[0] - 9, u[1] - 9, u[0] + 9, u[1] + 9), outline=(120, 255, 170, 120))
            else:
                silent += 1
                dr.ellipse((u[0] - 3, u[1] - 3, u[0] + 3, u[1] + 3), fill=(130, 130, 140))
    # the side view of the same (on a clear panel: the rings of the plan do not run into it)
    dr.rectangle((0, W + 1, W, W + W // 4), fill=(8, 10, 18, 255))
    dr.line((0, W + 4, W, W + 4), fill=(30, 36, 52))
    for site in w["sites"]:
        col = FACTION_COL.get(site["faction"], (200, 200, 200))
        for q in site["pieces"]:
            u = side(q[0], q[2])
            dr.rectangle((u[0] - 2, u[1] - 2, u[0] + 2, u[1] + 2), fill=col)
        for pod in site["pods"]:
            if pod["state"] != 1:
                u = side(pod["p"][0], pod["p"][2])
                dr.ellipse((u[0] - 2, u[1] - 2, u[0] + 2, u[1] + 2), fill=(120, 255, 170) if pod["beacon"] else (130, 130, 140))
    dr.text((10, W + 12), "side view (x to the right, height exaggerated 1.6x)", fill=(120, 130, 150), font=font)
    # the key and the title
    y0 = 12
    for label, col in (("ASTRA wreck: her field's reach (disc), her pieces (squares)", FACTION_COL[0]), ("the Mandate's", FACTION_COL[1]), ("the Guilds'", FACTION_COL[2])):
        dr.rectangle((12, y0, 24, y0 + 12), fill=col)
        dr.text((32, y0 - 2), label, fill=(200, 200, 210), font=font)
        y0 += 20
    for label, col in (("lifepod, its beacon calling", (120, 255, 170)), ("lifepod, silent (the air is out)", (130, 130, 140)), ("lifepod taken aboard", (90, 200, 150))):
        dr.ellipse((13, y0 + 1, 23, y0 + 11), fill=col if "taken" not in label else None, outline=col)
        dr.text((32, y0 - 2), label, fill=(200, 200, 210), font=font)
        y0 += 20
    dr.text((W - 560, 12), f"what the war left in {d['system']}: {len(w['sites'])} ships lost", fill=(220, 225, 235), font=big)
    dr.text((W - 560, 40), f"{w['clock'] / 60:.0f} min of the war, {alive} lifepods calling, {silent} silent, {recovered} taken aboard", fill=(170, 180, 195), font=font)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, quality=88) if out.suffix.lower() in (".jpg", ".jpeg") else img.save(out)
    print(out)


if __name__ == "__main__":
    main()
