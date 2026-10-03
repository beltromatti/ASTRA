"""A look at a class plan (data/ship/plans/<class>.json, docs/FLOTTA-VIVA.md): every deck from above, one under the other, the rooms by department,
the corridors, the doors (the pressure bulkheads red), the stair towers, the boarding hatches on the skin (green dots), the hull's outline as the
probe measured it, and a side view (x, z) of the decks and the halls. Pure PIL, no Blender.

Run: uv run --python /opt/homebrew/bin/python3.13 --with pillow python tools/art/fleet_planview.py <class> <out.png> [--scale PX_PER_M] [--decks 2,3] [--graph]
"""
from __future__ import annotations

import json
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DEPT = {"command": (62, 123, 250), "engineering": (255, 159, 28), "science": (150, 100, 230), "medical": (46, 196, 182), "security": (220, 70, 70),
        "flight": (210, 190, 50), "services": (100, 170, 100), "logistics": (120, 110, 70), "neutral": (110, 110, 120)}
CORR = (52, 66, 90)


def font(size: int):
    try:
        return ImageFont.load_default(size)
    except TypeError:
        return ImageFont.load_default()


def main():
    argv = sys.argv[1:]
    key, out = argv[0], argv[1]
    sc = float(argv[argv.index("--scale") + 1]) if "--scale" in argv else 3.0
    only = [int(v) for v in argv[argv.index("--decks") + 1].split(",")] if "--decks" in argv else None
    show_graph = "--graph" in argv
    plan = json.load(open(os.path.join(ROOT, "data", "ship", "plans", key + ".json"), encoding="utf-8"))
    hull = json.load(open(os.path.join(ROOT, "data", "ship", "plans", "hulls", key + ".json"), encoding="utf-8"))
    decks = [d for d in plan["decks"] if not only or d["id"] in only]
    xa = min(d["envelope"]["x_aft"] for d in plan["decks"]) - 6
    xf = max(d["envelope"]["x_fwd"] for d in plan["decks"]) + 6
    ym = max(max(h for _, h in d["envelope"]["half_width"]) for d in plan["decks"]) + 6
    ym = max(ym, hull["wmax"] * 0.6)
    pw = int((xf - xa) * sc) + 40
    ph = int(2 * ym * sc) + 34
    side_h = int((max(d["z"] + d["clear"] for d in plan["decks"]) - min(d["z"] for d in plan["decks"]) + 8) * sc) + 40
    img = Image.new("RGB", (pw, ph * len(decks) + side_h + 10), (12, 14, 18))
    dr = ImageDraw.Draw(img)
    f10, f12, f16 = font(max(8, int(sc * 2.6))), font(max(10, int(sc * 3.4))), font(14)
    by_id = {c["id"]: c for c in plan["compartments"]}

    def P(x, y, oy):
        return (20 + (x - xa) * sc, oy + 22 + (ym + y) * sc)

    for n, d in enumerate(decks):
        oy = n * ph
        dr.text((20, oy + 4), f"DECK {d['id']}  {d['name']}  z {d['z']:.1f}..{d['ceiling']:.1f}  {'body' if d.get('body', True) else 'superstructure'}", fill=(220, 220, 220), font=f16)
        # the envelope
        pts = d["envelope"]["half_width"]
        poly = [P(x, h, oy) for x, h in pts] + [P(x, -h, oy) for x, h in reversed(pts)]
        dr.polygon(poly, outline=(70, 80, 100))
        # section boundaries
        for s in d["sections"]:
            for xx in s["x"]:
                dr.line([P(xx, -ym, oy), P(xx, ym, oy)], fill=(40, 44, 52))
            dr.text(P(0.5 * (s["x"][0] + s["x"][1]), -ym + 1, oy), s["id"], fill=(120, 120, 130), font=f12)
        for c in plan["compartments"]:
            if c["deck"] != d["id"] and not (c.get("spans_decks") and d["id"] in c["spans_decks"]):
                continue
            x0, y0, x1, y1 = c["bounds"]
            a, b = P(x0, y0, oy), P(x1, y1, oy)
            hall = c.get("spans_decks") and c["deck"] != d["id"]
            col = CORR if c["kind"] == "corridor" else DEPT.get(c["dept"], (130, 130, 130))
            if c["kind"] == "stairs":
                col = (200, 200, 70)
            if c["kind"] in ("airlock", "vestibule"):
                col = (60, 200, 120)
            fill = tuple(int(v * (0.35 if not hall else 0.2)) for v in col)
            dr.rectangle([a, b], fill=fill, outline=col)
            if (x1 - x0) * sc > 38 and (y1 - y0) * sc > 12 and c["kind"] not in ("corridor",):
                dr.text((a[0] + 3, a[1] + 2), c["kind"] if c["kind"] != "storage" else "stor", fill=(235, 235, 235), font=f10)
        for dr_ in plan["doors"]:
            if dr_["deck"] != d["id"]:
                continue
            x, y, _ = dr_["pos"]
            p = P(x, y, oy)
            if dr_["kind"] == "blast":
                dr.rectangle([p[0] - 2, p[1] - 6, p[0] + 2, p[1] + 6], fill=(255, 60, 60))
            else:
                dr.ellipse([p[0] - 2, p[1] - 2, p[0] + 2, p[1] + 2], fill=(255, 230, 120))
        for dk in plan["docks"]:
            if dk["deck"] == d["id"]:
                p = P(dk["pos"][0], dk["pos"][1], oy)
                dr.ellipse([p[0] - 5, p[1] - 5, p[0] + 5, p[1] + 5], fill=(60, 255, 140), outline=(255, 255, 255))
        if show_graph:
            nodes = {n_["id"]: n_ for n_ in plan["graph"]["nodes"]}
            for e in plan["graph"]["edges"]:
                a_, b_ = nodes[e["a"]], nodes[e["b"]]
                if a_["deck"] == d["id"] and b_["deck"] == d["id"]:
                    dr.line([P(a_["p"][0], a_["p"][1], oy), P(b_["p"][0], b_["p"][1], oy)], fill=(255, 255, 255), width=1)
    # the side view
    oy = ph * len(decks) + 4
    zmin = min(d["z"] for d in plan["decks"]) - 4
    zmax = max(d["ceiling"] for d in plan["decks"]) + 4
    dr.text((20, oy), "SIDE VIEW (x to the bow, z up): decks, halls (outlined), docks", fill=(220, 220, 220), font=f16)

    def Q(x, z):
        return (20 + (x - xa) * sc, oy + 22 + (zmax - z) * sc)

    for d in plan["decks"]:
        dr.rectangle([Q(d["envelope"]["x_aft"], d["ceiling"]), Q(d["envelope"]["x_fwd"], d["z"])], outline=(70, 80, 100))
    for c in plan["compartments"]:
        if c.get("spans_decks") or c["kind"] in ("bridge",):
            col = DEPT.get(c["dept"], (130, 130, 130))
            dr.rectangle([Q(c["bounds"][0], c["z"][1]), Q(c["bounds"][2], c["z"][0])], outline=col, width=2)
            dr.text(Q(c["bounds"][0] + 1, c["z"][1] - 1), c["kind"], fill=col, font=f10)
    for dk in plan["docks"]:
        p = Q(dk["pos"][0], dk["pos"][2])
        dr.ellipse([p[0] - 5, p[1] - 5, p[0] + 5, p[1] + 5], fill=(60, 255, 140), outline=(255, 255, 255))
    img.save(out)
    print(f"{out}: {img.size[0]}x{img.size[1]}")


if __name__ == "__main__":
    main()
