"""ASTRA ships v3: the paint palette, one table for the Blender previews (ship3_preview.py) and the Unreal material instances
(tools/ue_scripts/make_ship_materials_v3.py loads this file too: no Blender imports here). Colours are docs/STILE.md §3, in sRGB hex.

PAINT[faction][part] = (paint tint, bare-metal tint, paint metallic, roughness min, roughness max)
"""

PAINT = {
    # ASTRA Navy: ivory and light-grey ceramic plates on a gunmetal frame, navy livery with a gold thread
    "A": dict(Plate=("#D6D2C7", "#8A8F96", 0.0, 0.30, 0.55), Frame=("#4A4F55", "#7A7F86", 0.35, 0.28, 0.55),
              Livery=("#1F3A6B", "#8A8F96", 0.0, 0.28, 0.50), Trim=("#B89A4E", "#C9B26B", 0.55, 0.24, 0.42),
              Marking=("#E9E6DD", "#8A8F96", 0.0, 0.35, 0.55), Engine=("#5B5F66", "#8A8F96", 0.85, 0.30, 0.50)),
    # Kharon Mandate: basalt and graphite blades, oxidised copper and verdigris, bronze
    "M": dict(Plate=("#4A4540", "#54514D", 0.0, 0.42, 0.78), Frame=("#1F2023", "#4A4A4C", 0.30, 0.30, 0.62),
              Livery=("#8C5A2B", "#9A7A55", 0.70, 0.30, 0.55), Trim=("#6E7F63", "#6A7A60", 0.50, 0.35, 0.65),
              Marking=("#B78A55", "#8A8F96", 0.0, 0.40, 0.70), Engine=("#3A3B40", "#6A6C70", 0.80, 0.35, 0.55)),
    # Guild freighters: worn utility paint, coloured containers
    "G": dict(Plate=("#9C927C", "#7B7F84", 0.0, 0.35, 0.75), Frame=("#44484C", "#7B7F84", 0.30, 0.30, 0.70),
              Livery=("#A2561B", "#7B7F84", 0.0, 0.40, 0.70), Trim=("#C9B25A", "#8A8F96", 0.0, 0.35, 0.60),
              Marking=("#E4E1D8", "#7B7F84", 0.0, 0.35, 0.55), Engine=("#6A6C70", "#8A8F96", 0.85, 0.35, 0.55),
              Blue=("#2C5A8C", "#7B7F84", 0.0, 0.35, 0.65), Green=("#3B6B4A", "#7B7F84", 0.0, 0.35, 0.65)),
}

# per faction: (window/light colour, light intensity, drive glow colour, drive glow intensity, lit fraction of the windows)
LIGHTS = {"A": ((1.0, 0.90, 0.75), 40.0, (0.55, 0.78, 1.0), 90.0, 0.65),
          "M": ((1.0, 0.68, 0.25), 40.0, (1.0, 0.42, 0.28), 90.0, 0.35),
          "G": ((1.0, 0.95, 0.85), 30.0, (0.90, 0.90, 1.0), 60.0, 0.55)}

# radiators: (dark panel colour, glow colour, glow intensity at rest: the game raises it with the ship's heat)
RADIATOR = {"A": ("#2A2D31", (1.0, 0.24, 0.05), 0.0), "M": ("#2A1A10", (1.0, 0.33, 0.07), 14.0), "G": ("#303236", (1.0, 0.33, 0.07), 0.0)}

# running lights (ASTRA: red port, green starboard, white stern; Mandate: a single red pulse)
NAVS = {"A": ((1.0, 0.05, 0.03), (0.1, 1.0, 0.2), (1.0, 0.95, 0.9)), "M": ((1.0, 0.06, 0.03), (1.0, 0.06, 0.03), (1.0, 0.06, 0.03)),
        "G": ((1.0, 0.05, 0.03), (0.1, 1.0, 0.2), (1.0, 0.95, 0.9))}


def srgb_to_linear(h: str) -> list:
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
