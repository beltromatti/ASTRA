"""Textures of the ship's interior kit (NAVE): the label atlas of the corridors and rooms. Output in art/_cache/ship/
(gitignored, reproducible with this script):

  art/_cache/ship/T_SHIP_Labels.png + labels.json   label atlas (4096 x 4096): every tile of the bridge v3 atlas (same names,
        so the bridge wall builders can be reused as they are), the section signs "DECK n · SECTION X" (n 1-12, X A-H), the
        section codes "4C-07" of Deck 4, the room name plates over the doors, pictograms (stairs, lift, ladder, heads, galley,
        arrows) and a few static screen faces (news, menu, a lab plot, a ship's directory)

Fonts: Barlow Condensed and IBM Plex Mono (OFL, art/_downloads/fonts). The lamp palette (T_BRG3_Lamps) and the packed PBR sets
are the bridge v3's: nothing else is generated here.

Run: uv run --python /opt/homebrew/bin/python3.13 --with pillow --with numpy python tools/art/ship_textures.py
"""
from __future__ import annotations

import json
import math
import os
import sys

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import bridge3_textures as B3  # noqa: E402   (fonts, plate/tag/stripes/icon drawing, the bridge's tile lists)

OUT = os.path.join(ROOT, "art", "_cache", "ship")
ATLAS = 4096

TITLE, MONO = B3.TITLE, B3.MONO
ICE, DIM, PLATE_BG = B3.ICE, B3.DIM, B3.PLATE
DEPT = dict(B3.DEPT)
DEPT["services"] = (95, 200, 120)
DEPT["neutral"] = (150, 165, 180)

# ------------------------------------------------------------------------------------------------ what goes in the atlas
SECTIONS = "ABCDEFGH"
DECK_TAG = {1: "command", 2: "command", 3: "services", 4: "services", 5: "science", 6: "medical", 7: "engineering", 8: "security",
            9: "flight", 10: "neutral", 11: "engineering", 12: "neutral"}

# room name plates: key -> (title, subtitle, department colour)
ROOMS = {
    "mess": ("MESS HALL", "OFF-DUTY WATCHES", "services"), "galley": ("GALLEY", "AUTHORIZED PERSONNEL", "services"),
    "lounge": ("CREW LOUNGE", "QUIET HOURS 2200-0600", "services"), "games": ("GAMES ROOM", "RECREATION", "services"),
    "library": ("LIBRARY", "SILENCE", "services"), "observation": ("OBSERVATION DECK", "VIEWING GALLERY", "command"),
    "stores_dry": ("DRY STORES", "GALLEY SUPPLY", "flight"), "stores_cold": ("COLD STORES", "-18 C", "science"),
    "stores": ("GENERAL STORES", "SUPPLY", "flight"), "heads": ("HEADS · SHOWERS", "", "neutral"), "laundry": ("LAUNDRY", "", "neutral"),
    "hydro": ("HYDROPONICS", "GROWTH BAY", "services"), "chapel": ("QUIET ROOM", "ALL FAITHS", "neutral"),
    "shop": ("SHIP'S STORE", "OPEN 0700-2100", "services"), "canteen": ("CANTEEN", "", "services"),
    "concourse": ("CONCOURSE", "MESS · LOUNGE · GALLEY", "services"), "lab": ("SCIENCE LAB", "SAMPLE HANDLING", "science"),
    "workshop": ("WORKSHOP", "MACHINE SHOP", "engineering"), "armory": ("ARMORY", "SECURITY · AUTHORIZED ONLY", "security"),
    "cabins": ("CREW CABINS", "QUIET", "services"), "dc": ("DAMAGE CONTROL", "REPAIR LOCKER", "engineering"),
    "machinery": ("MACHINERY SPACE", "AUTHORIZED PERSONNEL", "engineering"), "lift": ("LIFT", "DECKS 1 · 3 · 4 · 6 · 7 · 9", "command"),
    "stairs": ("STAIRS", "UP · DOWN", "neutral"), "shuttle": ("SPINE SHUTTLE", "DECK 5 PLATFORM", "command"),
    "bow_obs": ("BOW OBSERVATION", "FORWARD VIEW", "command"), "restricted": ("RESTRICTED", "AUTHORIZED PERSONNEL ONLY", "security"),
    "deck5": ("DECK 5", "SECTION B · RESTRICTED", "science"), "deck3": ("DECK 3", "SECTION B · RESTRICTED", "services"),
    "berthing": ("CREW BERTHING", "RED WATCH · QUIET", "services"), "mess_lobby": ("MESS HALL", "MAIN ENTRANCE", "services"),
    "directory": ("SHIP DIRECTORY", "DECKS 1-12 · SECTIONS A-H", "command"), "dumbwaiter": ("DUMBWAITER", "GALLEY · MESS", "services"),
    "ready": ("READY ROOM", "", "command"), "trunk": ("ESCAPE TRUNK", "DECK 3 / DECK 5", "neutral"),
    "medbay": ("MEDBAY", "MEDICAL · AUTHORIZED", "medical"), "surgery": ("SURGERY", "STERILE AREA", "medical"),
    "quarantine": ("QUARANTINE", "ISOLATION WARD", "medical"), "pharmacy": ("PHARMACY", "CONTROLLED SUBSTANCES", "medical"),
}
# NAVE-2: the rooms of the other decks (docs/NAVE.md §10); their plates are 512 x 64 (the same 8:1 as the older 768 x 96: the plate mesh does not change)
_OLD_ROOMS = set(ROOMS)
ROOMS.update({
    # Deck 2: CIC & Communications
    "cic": ("COMBAT INFORMATION CENTRE", "CIC · AUTHORIZED PERSONNEL ONLY", "command"), "briefing": ("BRIEFING ROOM", "OPERATIONS BRIEFINGS", "command"),
    "comms": ("COMMUNICATIONS CENTRE", "FLEET NET · SUBSPACE RELAY", "command"), "offices": ("DEPARTMENT OFFICES", "ADMINISTRATION", "command"),
    "records": ("RECORDS & ARCHIVE", "SHIP'S LOG · PERSONNEL FILES", "command"), "pdc": ("POINT-DEFENCE CONTROL", "FIRE CONTROL · AUTHORIZED ONLY", "security"),
    "vls": ("VLS MAGAZINE", "MISSILE HANDLING · NO NAKED FLAME", "security"), "barbette": ("TURRET BARBETTE", "RAILGUN MOUNT · LIVE SHELLS", "security"),
    "sensors": ("SENSOR ARRAY ROOM", "PASSIVE · ACTIVE · EW", "science"),
    # Deck 3: Crew Country
    "wardroom": ("OFFICERS' WARDROOM", "MESS · LOUNGE", "services"), "staterooms": ("OFFICERS' STATEROOMS", "QUIET HOURS", "services"),
    "gym": ("GYMNASIUM", "PHYSICAL TRAINING", "services"),
    # Deck 5: Science & Transport
    "transporter": ("TRANSPORTER ROOM", "AUTHORIZED PERSONNEL ONLY", "science"), "archive": ("SENSOR ARCHIVE", "DATA STACKS · COLD STORAGE", "science"),
    "lab_bio": ("BIOLOGY LAB", "SAMPLES · QUARANTINE PROTOCOL", "science"), "lab_astro": ("ASTROMETRICS", "STELLAR CARTOGRAPHY", "science"),
    "lab_phys": ("PHYSICS LAB", "HIGH ENERGY · SHIELDED", "science"), "lab_chem": ("CHEMISTRY LAB", "FUME HOODS · NO FOOD", "science"),
    "shuttle_stop": ("SPINE SHUTTLE", "PLATFORM · STAND BEHIND THE LINE", "command"),
    # Deck 7: Engineering & Power
    "power": ("POWER CONTROL", "GRID · BUS · REACTOR TAPS", "engineering"), "pumps": ("RADIATOR MANIFOLD", "COOLANT LOOPS 1-4", "engineering"),
    "switchgear": ("SWITCHGEAR", "HIGH VOLTAGE", "engineering"), "capacitors": ("CAPACITOR HALL", "STORED ENERGY · KEEP OUT", "engineering"),
    # Deck 8: Marines & Armory
    "barracks": ("MARINE BARRACKS", "A COMPANY · 1ST PLATOON", "security"), "range": ("FIRING RANGE", "LIVE FIRE · HEARING PROTECTION", "security"),
    "shuttle_bay": ("ASSAULT SHUTTLE BAY", "KESTREL 1 · KESTREL 2", "security"), "kit_room": ("KIT ROOM", "BATTLE DRESS · ARMOUR", "security"),
    # Deck 9: Flight
    "flight_ops": ("FLIGHT OPERATIONS", "AIR BOSS · CAG", "flight"), "aircraft_shop": ("AIRCRAFT WORKSHOP", "AVIONICS · AIRFRAME", "flight"),
    "magazine": ("MUNITIONS MAGAZINE", "ORDNANCE · AUTHORIZED ONLY", "security"), "cargo": ("CARGO HOLD", "SUPPLY · SECURE LOADS", "flight"),
    "booth": ("CONTROL BOOTH", "PRIMARY FLY", "flight"), "pilot_ready": ("PILOT READY ROOM", "BRIEF · SUIT UP", "flight"),
    # Deck 10-12
    "fab": ("FABRICATION SHOP", "PRINTERS · CASTING", "engineering"), "repair": ("REPAIR BAY", "HULL PATCH · SPARES", "engineering"),
    "tank": ("FUEL & COOLANT TANK", "LEVEL GAUGE · VENT", "neutral"), "mass": ("REACTION-MASS TANK", "PRESSURE VESSEL", "neutral"),
    "crawl": ("MAINTENANCE CRAWLWAY", "CREW ACCESS · 1 AT A TIME", "engineering"), "hold_bulk": ("BULK HOLD", "PALLETS · CONTAINERS", "flight"),
    "fire_hall": ("FIRE & DAMAGE CONTROL", "CENTRAL · TEAM 1-4", "engineering"),
    # Deck 1
    "ready_room": ("CAPTAIN'S READY ROOM", "PRIVATE · COMMAND", "command"),
})
for _d in range(2, 13):                 # the plate over a stair tower's door says where the flights go from this deck
    ROOMS[f"stairs_{_d}"] = ("STAIRS", f"UP DECK {_d - 1} · DOWN DECK {_d + 1}" if _d < 12 else "UP DECK 11", "neutral")

CODES_PER_SECTION = 12         # cabin numbers 1..12

EQUIPMENT_TAGS = {"eq_vent": "VENT", "eq_breaker": "BREAKER PANEL", "eq_maint": "MAINTENANCE ACCESS", "eq_comm": "COMM RELAY",
                  "eq_hydrant": "FIRE HYDRANT", "eq_water": "POTABLE WATER", "eq_air": "AIR HANDLING", "eq_dc": "DC LOCKER",
                  "eq_cable": "CABLE TRUNK", "eq_pipe": "COOLANT LINE", "eq_gas": "GAS · NO OPEN FLAME", "eq_food": "FOOD SERVICE",
                  "eq_lab": "SAMPLES · DO NOT DISTURB", "eq_tools": "TOOLS · SIGN OUT", "eq_ammo": "AMMUNITION · SECURE",
                  "eq_stores": "SUPPLY · COUNT BEFORE SIGNING", "eq_laundry": "LAUNDRY", "eq_recycle": "RECYCLING", "eq_notice": "NOTICES",
                  "eq_clean": "KEEP CLEAR", "eq_quiet": "QUIET", "eq_watch": "WATCH BILL"}
# NAVE-2: tags of the new rooms (placed by name from art/blender/ship_rooms_*.py): small tiles (256 x 64) to keep the atlas inside 4096 px
NAVE2_TAGS = {
    # Deck 8
    "eq_k1": "KESTREL 1", "eq_k2": "KESTREL 2", "eq_launch": "LAUNCH TUBE · KEEP CLEAR", "eq_range": "LIVE FIRE · EAR PROTECTION", "eq_clear": "CLEAR WEAPON · SAFE",
    "eq_lane1": "LANE 1", "eq_lane2": "LANE 2", "eq_lane3": "LANE 3", "eq_lane4": "LANE 4", "eq_lane5": "LANE 5", "eq_lane6": "LANE 6",
    "eq_helmets": "HELMETS · SIGN OUT", "eq_kit": "PERSONAL KIT", "eq_armour": "BATTLE DRESS · CHECK SEALS", "eq_roster": "SQUAD ROSTER", "eq_gpu": "GROUND POWER",
    "eq_fuel": "FUEL · NO NAKED FLAME",
}


def draw_arrow(kind: str, s: int = 128) -> Image.Image:
    img = Image.new("RGBA", (s, s), (20, 20, 22, 255))
    d = ImageDraw.Draw(img)
    c = s / 2
    m = s * 0.16
    pts = [(m, c - s * 0.13), (s * 0.55, c - s * 0.13), (s * 0.55, c - s * 0.30), (s - m, c), (s * 0.55, c + s * 0.30),
           (s * 0.55, c + s * 0.13), (m, c + s * 0.13)]
    ang = {"fwd": 0, "stbd": 90, "aft": 180, "port": 270}[kind]
    a = math.radians(ang)
    rot = [(c + (x - c) * math.cos(a) - (y - c) * math.sin(a), c + (x - c) * math.sin(a) + (y - c) * math.cos(a)) for x, y in pts]
    d.polygon(rot, fill=(*ICE, 255))
    d.rectangle((0, 0, s - 1, s - 1), outline=(46, 54, 66, 255), width=3)
    return img


def draw_pictogram(kind: str, s: int = 128) -> Image.Image:
    img = Image.new("RGBA", (s, s), (20, 20, 22, 255))
    d = ImageDraw.Draw(img)
    fg = (*ICE, 255)
    m = s * 0.14
    if kind == "stairs":
        n = 5
        for k in range(n):
            x0 = m + k * (s - 2 * m) / n
            y0 = s - m - (k + 1) * (s - 2 * m) / n
            d.rectangle((x0, y0, s - m, s - m), fill=fg)
            d.line((x0, y0, s - m, y0), fill=(20, 20, 22, 255), width=2)
    elif kind == "lift":
        d.rectangle((m, m, s - m, s - m), outline=fg, width=int(s * 0.05))
        d.line((s / 2, m, s / 2, s - m), fill=fg, width=int(s * 0.04))
        d.polygon([(s * 0.32, s * 0.45), (s * 0.42, s * 0.28), (s * 0.22, s * 0.28)], fill=fg)
        d.polygon([(s * 0.68, s * 0.55), (s * 0.78, s * 0.72), (s * 0.58, s * 0.72)], fill=fg)
    elif kind == "ladder":
        d.line((s * 0.32, m, s * 0.32, s - m), fill=fg, width=int(s * 0.06))
        d.line((s * 0.68, m, s * 0.68, s - m), fill=fg, width=int(s * 0.06))
        for k in range(5):
            y = m + (k + 0.5) * (s - 2 * m) / 5
            d.line((s * 0.32, y, s * 0.68, y), fill=fg, width=int(s * 0.05))
    elif kind == "heads":
        d.ellipse((s * 0.36, s * 0.14, s * 0.64, s * 0.36), fill=fg)
        d.rectangle((s * 0.30, s * 0.42, s * 0.70, s * 0.86), fill=fg)
        d.rectangle((s * 0.30, s * 0.62, s * 0.36, s * 0.86), fill=(20, 20, 22, 255))
        d.rectangle((s * 0.64, s * 0.62, s * 0.70, s * 0.86), fill=(20, 20, 22, 255))
    elif kind == "galley":
        d.rectangle((s * 0.30, m, s * 0.36, s - m), fill=fg)                    # fork
        for k in range(3):
            d.rectangle((s * (0.22 + 0.06 * k), m, s * (0.25 + 0.06 * k), s * 0.42), fill=fg)
        d.polygon([(s * 0.62, m), (s * 0.78, s * 0.45), (s * 0.66, s * 0.45), (s * 0.66, s - m), (s * 0.60, s - m)], fill=fg)  # knife
    elif kind == "obs":
        d.ellipse((m, s * 0.30, s - m, s * 0.70), outline=fg, width=int(s * 0.05))
        d.ellipse((s * 0.40, s * 0.40, s * 0.60, s * 0.60), fill=fg)
        for k in range(5):
            a = math.radians(200 + k * 35)
            d.line((s / 2 + math.cos(a) * s * 0.22, s * 0.28 + math.sin(a) * s * 0.10, s / 2 + math.cos(a) * s * 0.32,
                    s * 0.22 + math.sin(a) * s * 0.14), fill=fg, width=int(s * 0.03))
    elif kind == "shuttle":
        d.rounded_rectangle((m, s * 0.32, s - m, s * 0.62), radius=int(s * 0.1), outline=fg, width=int(s * 0.05))
        d.line((m, s * 0.75, s - m, s * 0.75), fill=fg, width=int(s * 0.05))
        for k in range(3):
            d.rectangle((s * (0.26 + 0.18 * k), s * 0.40, s * (0.36 + 0.18 * k), s * 0.5), fill=fg)
    d.rectangle((0, 0, s - 1, s - 1), outline=(46, 54, 66, 255), width=3)
    return img


def screen_face(kind: str, w: int = 512, h: int = 288) -> Image.Image:
    """Static screen faces (dark UI with ice-blue lines): news, menu, a lab plot, a directory of the ship."""
    img = Image.new("RGBA", (w, h), (8, 11, 15, 255))
    d = ImageDraw.Draw(img)
    f_title, f_mono, f_small = B3.font(TITLE, 30), B3.font(MONO, 15), B3.font(MONO, 12)
    d.rectangle((0, 0, w - 1, h - 1), outline=(46, 70, 100, 255), width=3)
    d.rectangle((0, 0, w, 44), fill=(14, 22, 32, 255))
    titles = {"news": "FLEET NET · NEWS", "menu": "TODAY'S MENU", "lab": "SAMPLE 07 · SPECTRUM", "dir": "SHIP DIRECTORY",
              "sched": "WATCH BILL", "map": "AURELIA MARCH", "star": "STELLAR CARTOGRAPHY", "tac": "TACTICAL PLOT", "ship": "SHIP STATUS",
              "data": "ARCHIVE INDEX", "wave": "SIGNAL ANALYSIS"}
    d.text((16, 22), titles.get(kind, kind.upper()), font=f_title, fill=(*ICE, 255), anchor="lm")
    if kind == "news":
        for k, t in enumerate(["7TH FLEET HOLDS AURELIA GATE", "MERIDIAN CONVOY DELAYED 2 DAYS", "CASSIA PRIME: TALKS CONTINUE",
                                "THULE WATCH STILL SILENT", "WEATHER: NEW RAVENNA CLEAR"]):
            y = 64 + k * 40
            d.rectangle((16, y, 22, y + 22), fill=(*DEPT["command"], 255))
            d.text((34, y + 11), t, font=f_mono, fill=(*ICE, 255), anchor="lm")
            d.line((34, y + 30, w - 20, y + 30), fill=(30, 44, 60, 255), width=1)
    elif kind == "menu":
        for k, (a, b) in enumerate([("BRAISED LAMB · BARLEY", "1"), ("AURELIAN RICE · VEGETABLES", "2"), ("HYDRO GREENS · SOUP", "3"),
                                    ("COFFEE · MERIDIAN", "FREE")]):
            y = 64 + k * 50
            d.text((20, y), a, font=f_mono, fill=(*ICE, 255))
            d.text((w - 30, y), b, font=f_mono, fill=(*DIM, 255), anchor="ra")
    elif kind == "lab":
        for r in range(1, 5):
            d.ellipse((w * 0.5 - r * 40, h * 0.62 - r * 30, w * 0.5 + r * 40, h * 0.62 + r * 30), outline=(30, 56, 84, 255))
        pts = [(24 + i * 10, h * 0.72 - 50 * math.exp(-((i - 24) / 6.0) ** 2) - 24 * math.exp(-((i - 10) / 4.0) ** 2) - 10 * math.sin(i)) for i in range(48)]
        d.line(pts, fill=(*DEPT["science"], 255), width=3)
        d.text((16, h - 22), "PEAK 3.2 eV · CONFIDENCE 0.94", font=f_small, fill=(*DIM, 255))
    elif kind == "dir":
        for k in range(12):
            y = 56 + k * 18
            d.text((20, y), f"DECK {k + 1:>2}", font=f_small, fill=(*ICE, 255))
            d.line((90, y + 9, w - 20, y + 9), fill=(30, 44, 60, 255), width=1)
    elif kind == "sched":
        for k, t in enumerate(["RED WATCH   0000-0800", "GOLD WATCH  0800-1600", "BLUE WATCH  1600-2400", "MESS: 0630 1130 1730 2330"]):
            d.text((20, 64 + k * 38), t, font=f_mono, fill=(*ICE, 255))
    elif kind == "map":
        import random
        rng = random.Random(4)
        pts = [(60 + rng.random() * (w - 120), 70 + rng.random() * (h - 100)) for _ in range(11)]
        for i, p in enumerate(pts):
            for q in pts[i + 1:i + 3]:
                d.line((*p, *q), fill=(30, 56, 84, 255), width=2)
        for p in pts:
            d.ellipse((p[0] - 5, p[1] - 5, p[0] + 5, p[1] + 5), outline=(*ICE, 255), width=2)
    elif kind == "star":                                  # a star chart: a field of stars, constellation lines, a ringed target
        import random
        rng = random.Random(11)
        for _ in range(160):
            x, y = 12 + rng.random() * (w - 24), 54 + rng.random() * (h - 66)
            r = rng.choice((1, 1, 1, 2))
            d.ellipse((x - r, y - r, x + r, y + r), fill=(*ICE, 255))
        pts = [(70 + rng.random() * (w - 140), 80 + rng.random() * (h - 110)) for _ in range(9)]
        for a, b in zip(pts, pts[1:]):
            d.line((*a, *b), fill=(*DEPT["science"], 255), width=2)
        for p in pts:
            d.ellipse((p[0] - 4, p[1] - 4, p[0] + 4, p[1] + 4), outline=(*ICE, 255), width=2)
        c = pts[4]
        for rr in (14, 26):
            d.ellipse((c[0] - rr, c[1] - rr, c[0] + rr, c[1] + rr), outline=(*DEPT["command"], 255), width=2)
        d.text((16, h - 20), "AURELIA · SECTOR 7 · 1:40 000 000", font=f_small, fill=(*DIM, 255))
    elif kind == "tac":                                    # a tactical plot: range rings, a bearing line, contacts
        import random
        rng = random.Random(7)
        cx, cy = w * 0.5, h * 0.60
        for r in range(1, 5):
            d.ellipse((cx - r * 62, cy - r * 46, cx + r * 62, cy + r * 46), outline=(30, 56, 84, 255), width=1)
        d.line((cx, cy, cx + 150, cy - 80), fill=(*DEPT["command"], 255), width=2)
        d.polygon([(cx, cy - 8), (cx - 6, cy + 6), (cx + 6, cy + 6)], fill=(*ICE, 255))
        for k in range(6):
            x, y = cx + (rng.random() - 0.5) * 380, cy + (rng.random() - 0.5) * 150
            col = DEPT["security"] if k % 3 == 0 else ICE
            d.rectangle((x - 5, y - 5, x + 5, y + 5), outline=(*col, 255), width=2)
        d.text((16, h - 20), "TRACKS 12 · HOSTILE 3 · RANGE 28 KM", font=f_small, fill=(*DIM, 255))
    elif kind == "ship":                                   # the ship's side profile in lines, with the deck lines
        d.polygon([(30, 150), (90, 120), (330, 118), (440, 140), (490, 150), (440, 176), (90, 178)], outline=(*ICE, 255), width=2)
        for k in range(1, 7):
            d.line((60 + k * 62, 124, 60 + k * 62, 172), fill=(30, 56, 84, 255), width=1)
        for k in range(1, 5):
            d.line((70, 118 + k * 12, 470, 118 + k * 12), fill=(30, 56, 84, 255), width=1)
        d.rectangle((190, 96, 330, 120), outline=(*ICE, 255), width=2)
        d.rectangle((250, 70, 300, 96), outline=(*DEPT["command"], 255), width=2)
        d.rectangle((330, 140, 392, 160), fill=(*DEPT["medical"], 255))
        d.text((16, h - 20), "ASN AQUILA · CVC-01 · DECKS 1-12", font=f_small, fill=(*DIM, 255))
    elif kind == "data":                                   # rows of figures
        import random
        rng = random.Random(3)
        for k in range(11):
            y = 58 + k * 20
            d.text((18, y), "%02d  %08X  %6.2f" % (k + 1, rng.getrandbits(32), rng.random() * 100), font=f_small, fill=(*ICE, 255))
            d.rectangle((300, y + 3, 300 + int(rng.random() * 190), y + 11), fill=(*DEPT["science"], 255))
    elif kind == "wave":                                   # waveforms
        for row, (col, amp, fr) in enumerate(((DEPT["science"], 26, 0.16), (DEPT["command"], 18, 0.31), (DEPT["medical"], 22, 0.09))):
            y0 = 92 + row * 66
            d.line([(14 + i * 5, y0 + amp * math.sin(i * fr * 3.1 + row)) for i in range(98)], fill=(*col, 255), width=2)
            d.line((14, y0, w - 14, y0), fill=(30, 44, 60, 255), width=1)
    return img


# ------------------------------------------------------------------------------------------------------------ the atlas
def build() -> None:
    os.makedirs(OUT, exist_ok=True)
    tiles: list[tuple[str, Image.Image, str]] = []          # (name, image, text)

    def add(name: str, img: Image.Image, text: str = "") -> None:
        tiles.append((name, img.convert("RGBA"), text))

    # ---- the bridge v3 atlas, tile for tile (same names and sizes)
    for name, title, sub, dept in B3.STATIONS:
        add(name, B3.plate(1024, 128, title, sub, B3.DEPT[dept]), title)
    for name, title, sub in B3.DECK_LEGENDS:
        add(name, B3.plate(1024, 128, title, sub, B3.DEPT["command"]), title)
    add("hazard", B3.stripes(1024, 64))
    add("hazard_h", B3.stripes(512, 64, 28))
    for i, t in enumerate(B3.TAGS):
        add(f"tag_{i:02d}", B3.tag(512, 128, t, warn=(i in (8,))), t)
    for i, t in enumerate(B3.SMALL):
        add(f"small_{i:02d}", B3.tag(256, 64, t, warn=(t in ("CAUTION", "STOP"))), t)
    for k in ("hv", "fire", "exit", "aid", "eva", "rad", "no_step"):
        add(f"icon_{k}", B3.icon(k))
    # ---- new: generic equipment tags (the bridge's carry the bridge's own deck codes), section signs, codes, room plates,
    #      pictograms, screens
    for k, t in EQUIPMENT_TAGS.items():
        add(k, B3.tag(512, 128, t), t)
    for k, t in NAVE2_TAGS.items():
        add(k, B3.tag(256, 64, t), t)
    for d in range(1, 13):
        for x in SECTIONS:
            add(f"sec_{d}{x}", B3.plate(512, 64, f"DECK {d} · SECTION {x}", "", DEPT[DECK_TAG[d]]),
                f"DECK {d} · SECTION {x}")
    for n in range(1, CODES_PER_SECTION + 1):                       # the numbers on the doors of the cabins (a cabin block is the same on every deck)
        add(f"cabin_{n:02d}", B3.tag(256, 64, f"CABIN {n}"), f"CABIN {n}")
    for key, (title, sub, dept) in ROOMS.items():
        w, h = (768, 96) if key in _OLD_ROOMS or key.startswith("stairs_") else (512, 64)
        add(f"room_{key}", B3.plate(w, h, title, sub, DEPT[dept]), title)
    for k in ("fwd", "aft", "port", "stbd"):
        add(f"arrow_{k}", draw_arrow(k))
    for k in ("stairs", "lift", "ladder", "heads", "galley", "obs", "shuttle"):
        add(f"pict_{k}", draw_pictogram(k))
    for k in ("news", "menu", "lab", "dir", "sched", "map", "star", "tac", "ship", "data", "wave"):
        add(f"scr_{k}", screen_face(k))

    # shelf packing, tallest first
    order = sorted(range(len(tiles)), key=lambda i: (-tiles[i][1].size[1], -tiles[i][1].size[0]))
    img = Image.new("RGBA", (ATLAS, ATLAS), (*PLATE_BG, 255))
    rects: dict[str, tuple[int, int, int, int]] = {}
    x = y = row_h = 0
    for i in order:
        name, tile, _t = tiles[i]
        w, h = tile.size
        if x + w > ATLAS:
            x, y, row_h = 0, y + row_h, 0
        if y + h > ATLAS:
            raise RuntimeError("the label atlas is full: raise ATLAS or shrink the tiles")
        img.paste(tile, (x, y))
        rects[name] = (x, y, w, h)
        x += w
        row_h = max(row_h, h)
    used = y + row_h
    img.convert("RGB").save(os.path.join(OUT, "T_SHIP_Labels.png"), optimize=True)
    uv = {k: [px / ATLAS, 1.0 - (py + h) / ATLAS, (px + w) / ATLAS, 1.0 - py / ATLAS] for k, (px, py, w, h) in rects.items()}
    text = {name: t for name, _img, t in tiles if t}
    with open(os.path.join(OUT, "labels.json"), "w", encoding="utf-8") as fh:
        json.dump({"size": [ATLAS, ATLAS], "rects": uv, "px": {k: list(v) for k, v in rects.items()}, "text": text,
                   "rooms": {k: f"room_{k}" for k in ROOMS}}, fh, indent=1)
    print(f"  ship label atlas: {len(rects)} tiles, {used}/{ATLAS} px used -> {OUT}")


if __name__ == "__main__":
    build()
