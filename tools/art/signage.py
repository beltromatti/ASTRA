"""The bridge's signage and markings, drawn with the project's fonts (Barlow Condensed, IBM Plex Mono — OFL):

  T_SIGN_<station>     backlit station plates (dark plate, lit lettering, a section code)
  T_SIGN_Aquila        the ship's name plate with the ASTRA Navy emblem, over the master display
  T_SIGN_Door_<side>   over the doors: where they lead
  T_DECAL_Emblem       the emblem inlaid in the well floor (alpha)
  T_DECAL_Edge         the safety edge of the well (alpha)

Run: uv run --with pillow python tools/art/signage.py -> art/_cache/signage/*.png
"""
import math
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FONTS = os.path.join(ROOT, "art", "_downloads", "fonts")
OUT = os.path.join(ROOT, "art", "_cache", "signage")
TITLE = os.path.join(FONTS, "BarlowCondensed-SemiBold.ttf")
MONO = os.path.join(FONTS, "IBMPlexMono-Medium.ttf")
ICE = (190, 225, 255)
DIM = (110, 140, 170)
PLATE = (12, 14, 18)


def font(path, size):
    return ImageFont.truetype(path, size)


def emblem(size: int, color=ICE, bg=None) -> Image.Image:
    """ASTRA Navy: an eight-pointed star of light in a double ring, the motto around it."""
    img = Image.new("RGBA", (size, size), bg or (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = size / 2
    col = (*color, 255)
    d.ellipse((size * 0.03, size * 0.03, size * 0.97, size * 0.97), outline=col, width=max(2, size // 90))
    d.ellipse((size * 0.2, size * 0.2, size * 0.8, size * 0.8), outline=col, width=max(2, size // 130))
    # the star: four long points (the compass), four short ones between them
    pts = []
    for k in range(16):
        a = math.pi * k / 8
        if k % 4 == 0:
            r = size * 0.36
        elif k % 4 == 2:
            r = size * 0.2
        else:
            r = size * 0.055
        pts.append((c + r * math.sin(a), c - r * math.cos(a)))
    d.polygon(pts, fill=col)
    d.ellipse((c - size * 0.035, c - size * 0.035, c + size * 0.035, c + size * 0.035), fill=(8, 10, 14, 255))
    # the words on the ring: ASTRA NAVY above, the motto below
    f = font(TITLE, int(size * 0.075))

    def arc(text, radius, start_deg, span_deg, upper=True):
        n = len(text)
        for i, ch in enumerate(text):
            t = (i + 0.5) / n
            ang = math.radians(start_deg + span_deg * t)
            x = c + radius * math.sin(ang)
            y = c - radius * math.cos(ang)
            glyph = Image.new("RGBA", (int(size * 0.12), int(size * 0.12)), (0, 0, 0, 0))
            gd = ImageDraw.Draw(glyph)
            gd.text((glyph.width / 2, glyph.height / 2), ch, font=f, fill=col, anchor="mm")
            rot = -math.degrees(ang) if upper else 180 - math.degrees(ang)
            glyph = glyph.rotate(rot, resample=Image.BICUBIC)
            img.alpha_composite(glyph, (int(x - glyph.width / 2), int(y - glyph.height / 2)))
    arc("ASTRA NAVY", size * 0.405, -52, 104, True)
    arc("CONCORD · LAW · LIGHT", size * 0.405, 232, -104, False)
    return img


def plate(w: int, h: int, title: str, code: str, accent=(60, 130, 230), title_scale: float = 0.56) -> Image.Image:
    img = Image.new("RGBA", (w, h), (*PLATE, 255))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w - 1, h - 1), outline=(40, 46, 56, 255), width=4)
    d.rectangle((0, 0, int(h * 0.09), h), fill=(*accent, 255))           # the department's colour bar
    ft = font(TITLE, int(h * title_scale))
    fm = font(MONO, int(h * 0.16))
    d.text((int(h * 0.3), h * 0.44), title, font=ft, fill=(*ICE, 255), anchor="lm")
    d.text((w - int(h * 0.18), h * 0.8), code, font=fm, fill=(*DIM, 255), anchor="rm")
    return img.filter(ImageFilter.GaussianBlur(0.6))


DEPT = {"helm": (70, 150, 255), "ops": (240, 170, 40), "tactical": (220, 60, 50), "comms": (240, 170, 40),
        "sensors": (60, 200, 190), "engineering": (240, 170, 40), "flight": (70, 150, 255), "xo": (230, 230, 240)}
NAMES = {"helm": "HELM", "ops": "OPERATIONS", "tactical": "TACTICAL", "comms": "COMMUNICATIONS", "sensors": "SCIENCE & SENSORS",
         "engineering": "ENGINEERING", "flight": "FLIGHT CONTROL"}


def main():
    os.makedirs(OUT, exist_ok=True)
    for i, (sid, name) in enumerate(NAMES.items()):
        plate(1024, 192, name, f"DECK 1 · BRIDGE · STATION {i + 1:02d}", DEPT[sid]).save(os.path.join(OUT, f"T_SIGN_{sid.capitalize()}.png"))
    # the ship's name plate: the emblem, the name, the line
    w, h = 2048, 512
    for hull, suffix in (("CVC-01", ""), ("CVC-03", "_03"), ("CVC-04", "_04"), ("CVC-05", "_05")):
        img = Image.new("RGBA", (w, h), (*PLATE, 255))
        d = ImageDraw.Draw(img)
        d.rectangle((0, 0, w - 1, h - 1), outline=(40, 46, 56, 255), width=6)
        em = emblem(420, ICE)
        img.alpha_composite(em, (46, 46))
        d.text((530, 250), "ASN AQUILA", font=font(TITLE, 250), fill=(*ICE, 255), anchor="lm")
        d.text((538, 420), f"{hull} · CARRIER CRUISER · 7TH FLEET", font=font(MONO, 50), fill=(*DIM, 255), anchor="lm")
        img.filter(ImageFilter.GaussianBlur(0.5)).save(os.path.join(OUT, f"T_SIGN_Aquila{suffix}.png"))
    for side, word, direction in (("Port", "PORT", -1), ("Starboard", "STARBOARD", 1)):
        p = plate(1024, 256, "CORRIDOR 1-A", f"{word} · DECK 1 · TO THE SPINE", (230, 230, 240))
        pd = ImageDraw.Draw(p)
        ax, ay, s2 = 930, 100, 46     # the arrow, drawn (the fonts have no arrows)
        pts = [(ax - s2, ay - 14), (ax + 4, ay - 14), (ax + 4, ay - 40), (ax + s2 + 10, ay), (ax + 4, ay + 40), (ax + 4, ay + 14), (ax - s2, ay + 14)]
        if direction < 0:
            pts = [(2 * ax - x, y) for x, y in pts]
        pd.polygon(pts, fill=(*ICE, 255))
        p.save(os.path.join(OUT, f"T_SIGN_Door_{side}.png"))
    # the lift between the bridge and the flight deck, and the flight deck's own wall sign
    for name in ("Lift_Bridge", "Lift_Hangar"):
        plate(1024, 256, "LIFT", "DECKS 1 · 4 · 6 · 7 · 9 · PRESS TO CALL", (240, 170, 40)).save(os.path.join(OUT, f"T_SIGN_{name}.png"))
    # the rooms the lift opens into: their names over the doors
    plate(1024, 256, "MAIN ENGINEERING", "DECK 7 · SECTION F", (240, 170, 40), title_scale=0.42).save(os.path.join(OUT, "T_SIGN_Room_Engineering.png"))
    med = plate(1024, 256, "MEDBAY", "DECK 6 · SECTION C", (46, 196, 182))
    md = ImageDraw.Draw(med)
    cx, cy, a, b = 1024 - 150, 100, 20, 62            # the medical cross: universal, white on teal
    md.rectangle((cx - 78, cy - 78, cx + 78, cy + 78), fill=(46, 196, 182, 255))
    md.rectangle((cx - a, cy - b, cx + a, cy + b), fill=(*ICE, 255))
    md.rectangle((cx - b, cy - a, cx + b, cy + a), fill=(*ICE, 255))
    med.save(os.path.join(OUT, "T_SIGN_Room_Medbay.png"))
    plate(1024, 256, "MESS HALL", "DECK 4 · SECTION B", (240, 200, 120)).save(os.path.join(OUT, "T_SIGN_Room_Mess.png"))
    # the lifepods off Corridor 1-A: the hatch's plate (yellow: emergency equipment)
    for pod, side in (("1A", "PORT"), ("1B", "STARBOARD")):
        plate(1024, 256, f"LIFEPOD {pod[0]}-{pod[1]}", f"DECK 1 · {side} · 6 PERSONS", (250, 190, 40)).save(os.path.join(OUT, f"T_SIGN_Lifepod_{pod}.png"))
    w2, h2 = 2048, 512
    fd = Image.new("RGBA", (w2, h2), (*PLATE, 255))
    dd = ImageDraw.Draw(fd)
    dd.rectangle((0, 0, w2 - 1, h2 - 1), outline=(40, 46, 56, 255), width=6)
    fd.alpha_composite(emblem(400, ICE), (56, 56))
    dd.text((520, 230), "FLIGHT DECK", font=font(TITLE, 230), fill=(*ICE, 255), anchor="lm")
    dd.text((528, 410), "DECK 9 · SECTION B · ALPHA · BRAVO · DRONES", font=font(MONO, 50), fill=(*DIM, 255), anchor="lm")
    fd.save(os.path.join(OUT, "T_SIGN_FlightDeck.png"))
    # floor decals (white on transparent: the material tints and blends them)
    emblem(1024, (235, 238, 242)).save(os.path.join(OUT, "T_DECAL_Emblem.png"))
    edge = Image.new("RGBA", (1024, 64), (0, 0, 0, 0))
    ed = ImageDraw.Draw(edge)
    for x in range(-64, 1024, 48):   # safety chevrons along the well's edge
        ed.polygon([(x, 64), (x + 24, 64), (x + 48, 0), (x + 24, 0)], fill=(235, 190, 40, 255))
    edge.save(os.path.join(OUT, "T_DECAL_Edge.png"))
    print("SIGNAGE_OK", sorted(os.listdir(OUT)))


if __name__ == "__main__":
    main()
