"""A top-down view of a deck of data/ship/aquila_plan.json (compartments, passages, doors, walk graph, envelope, sections): the quick way
to read a layout. Pure PIL, no Blender.

Run: uv run --python /opt/homebrew/bin/python3.13 --with pillow python tools/art/ship_planview.py <deck> <out.jpg> [--x0 X --x1 X]
     [--scale PX_PER_M] [--plan path] [--graph] [--by kind]  (x0 = the aft limit, x1 = the forward limit of the window, metres)
Rooms are coloured by department (command blue, engineering orange, science violet, medical teal, security red, flight yellow, services green, neutral grey; NAVE-3), the corridors by tone (the Spine
and the Passages blue, the crawlways and the service galleries brown, the shuttle's tunnel cyan), the lift lobbies and shafts white, the Jefferies cells brown; `--by kind` gives the old colours.
"""
from __future__ import annotations

import json
import math
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FONT = "/Users/beltromatti/Desktop/ASTRA/art/_downloads/fonts/BarlowCondensed-SemiBold.ttf"

KIND_COLOUR = {"corridor": (46, 60, 82), "mess": (200, 150, 70), "berthing": (150, 120, 190), "concourse": (70, 140, 110), "galley": (210, 120, 70),
               "lounge": (120, 90, 150), "library": (140, 100, 70), "observation": (60, 100, 170), "storage": (110, 110, 70), "heads": (90, 130, 140),
               "laundry": (90, 120, 150), "hydroponics": (60, 140, 60), "chapel": (150, 150, 170), "stairs": (170, 170, 60), "lab": (130, 80, 200),
               "workshop": (190, 130, 40), "armory": (190, 60, 60), "cabins": (110, 90, 130), "medbay": (46, 196, 182), "engineering": (255, 159, 28),
               "hangar": (200, 180, 40), "bridge": (62, 123, 250), "quarters": (62, 123, 250), "lift": (200, 200, 200)}


DEPT_COLOUR = {"command": (62, 123, 250), "engineering": (255, 159, 28), "science": (150, 100, 230), "medical": (46, 196, 182), "security": (220, 70, 70), "flight": (210, 190, 50),
               "services": (100, 170, 100), "neutral": (150, 150, 150)}
TONE_COLOUR = {"S": (60, 80, 112), "P": (50, 64, 88), "K": (96, 72, 48), "V": (120, 92, 44), "T": (60, 120, 150)}
KIND_OVERRIDE = {"lobby": (235, 235, 235), "lift": (200, 225, 255), "stairs": (190, 190, 70), "trunk": (170, 120, 70), "tunnel": (60, 120, 150), "transit": (70, 170, 200)}


def main() -> None:
    argv = sys.argv[1:]
    deck = int(argv[0])
    out = argv[1]
    opt = {"--x0": None, "--x1": None, "--scale": "3.0", "--plan": os.path.join(ROOT, "data", "ship", "aquila_plan.json")}
    for k in list(opt):
        if k in argv:
            opt[k] = argv[argv.index(k) + 1]
    show_graph = "--graph" in argv
    by_kind = "--by" in argv and argv[argv.index("--by") + 1] == "kind"
    plan = json.load(open(opt["--plan"], encoding="utf-8"))
    comps = [c for c in plan["compartments"] if c["deck"] == deck or c.get("plane") == deck]
    doors = [d for d in plan["doors"] if d["deck"] == deck]
    deckrec = next((d for d in plan.get("decks", []) if d["id"] == deck), None)
    xs = [c["bounds"][0] for c in comps] + [c["bounds"][2] for c in comps]
    x0 = float(opt["--x0"]) if opt["--x0"] else min(xs) - 5
    x1 = float(opt["--x1"]) if opt["--x1"] else max(xs) + 5
    sc = float(opt["--scale"])
    ymax = 48.0
    W, H = int((x1 - x0) * sc) + 40, int(2 * ymax * sc) + 60
    img = Image.new("RGB", (W, H), (12, 14, 18))
    d = ImageDraw.Draw(img)
    f = ImageFont.truetype(FONT, max(9, int(sc * 3.4)))
    fs = ImageFont.truetype(FONT, max(8, int(sc * 2.4)))

    def P(x: float, y: float):
        return (20 + (x1 - x) * sc, 30 + (y + ymax) * sc)          # bow to the left, starboard down

    # envelope
    if deckrec and deckrec.get("envelope", {}).get("half_width"):
        pts = [(p[0], p[1]) for p in deckrec["envelope"]["half_width"] if x0 <= p[0] <= x1]
        d.line([P(x, y) for x, y in pts], fill=(70, 70, 40), width=1)
        d.line([P(x, -y) for x, y in pts], fill=(70, 70, 40), width=1)
    # sections
    if deckrec:
        for s in deckrec["sections"]:
            for xb in s["x"]:
                if x0 <= xb <= x1:
                    d.line([P(xb, -ymax), P(xb, ymax)], fill=(90, 40, 40), width=1)
            xm = (s["x"][0] + s["x"][1]) / 2
            if x0 <= xm <= x1:
                d.text(P(xm, -ymax + 1.0), s["id"], font=f, fill=(200, 90, 90), anchor="mm")
    for c in comps:
        b = c["bounds"]
        if by_kind:
            colour = KIND_COLOUR.get(c["kind"], (80, 80, 80))
        elif c["kind"] == "corridor":
            colour = TONE_COLOUR.get(c.get("tone"), (46, 60, 82))
        else:
            colour = KIND_OVERRIDE.get(c["kind"]) or DEPT_COLOUR.get(c.get("dept"), (80, 80, 80))
        a1, a2 = P(b[2], b[1]), P(b[0], b[3])
        if c["kind"] == "corridor":
            d.rectangle([a1, a2], fill=colour, outline=(20, 24, 32))
        else:
            fill = tuple(int(v * 0.55) for v in colour) if c.get("status") != "existing" else tuple(int(v * 0.75) for v in colour)
            d.rectangle([a1, a2], fill=fill, outline=colour)
            label = c["name"] if (b[2] - b[0]) * sc > 60 else ""
            if label:
                d.text(((a1[0] + a2[0]) / 2, (a1[1] + a2[1]) / 2), label, font=fs, fill=(235, 235, 235), anchor="mm")
        for k in ("annex",):
            if c.get(k):
                ab = c[k]
                d.rectangle([P(ab[2], ab[1]), P(ab[0], ab[3])], outline=colour)
    for dr in doors:
        x, y = dr["pos"][0], dr["pos"][1]
        w = dr["width"]
        if dr["kind"] == "blast":
            d.line([P(x, y - 1.3), P(x, y + 1.3)], fill=(230, 60, 50), width=2)
        elif abs(dr["yaw"] - 90.0) < 1:
            d.line([P(x - w / 2, y), P(x + w / 2, y)], fill=(250, 230, 100), width=2)
        else:
            d.line([P(x, y - w / 2), P(x, y + w / 2)], fill=(250, 230, 100), width=2)
    if show_graph:
        nodes = {n["id"]: n for n in plan["graph"]["nodes"] if n["deck"] == deck}
        for e in plan["graph"]["edges"]:
            a, b = nodes.get(e["a"]), nodes.get(e["b"])
            if a and b:
                d.line([P(a["p"][0], a["p"][1]), P(b["p"][0], b["p"][1])], fill=(80, 200, 120) if e["kind"] == "walk" else (230, 120, 200), width=1)
        for n in nodes.values():
            x, y = P(n["p"][0], n["p"][1])
            d.ellipse((x - 1.5, y - 1.5, x + 1.5, y + 1.5), fill=(200, 255, 200))
    if not by_kind:                                                                                       # the legend
        lx = 24
        for k, col in list(DEPT_COLOUR.items()) + [("Spine / Passages", TONE_COLOUR["S"]), ("service / crawl", TONE_COLOUR["V"]), ("shuttle tunnel", TONE_COLOUR["T"]), ("lifts", KIND_OVERRIDE["lobby"])]:
            d.rectangle((lx, H - 22, lx + 12, H - 10), fill=col)
            d.text((lx + 16, H - 16), k, font=fs, fill=(190, 190, 190), anchor="lm")
            lx += 24 + int(d.textlength(k, font=fs))
    # x ruler
    step = 20
    xr = math.ceil(x0 / step) * step
    while xr <= x1:
        px, py = P(xr, ymax)
        d.line([(px, py), (px, py + 6)], fill=(150, 150, 150))
        d.text((px, py + 8), str(int(xr)), font=fs, fill=(150, 150, 150), anchor="mt")
        xr += step
    img.save(out, quality=88)
    print("wrote", out, img.size)


if __name__ == "__main__":
    main()
