"""ARTE-INTERNI: the texture sets of the Aquila's rooms, from CC0 ambientCG materials (no account, no key).

For every set below: download the 1K-JPG zip (once; art/_downloads/ambientcg/<id>/, gitignored), then pack
  art/_cache/textures/T_<Set>_BC.png   base colour, sRGB (`neutral`: a grey detail map, so that the instance's Tint gives the colour)
  art/_cache/textures/T_<Set>_N.png    normal, DirectX convention
  art/_cache/textures/T_<Set>_ORM.png  R = ambient occlusion (1 when the source has none), G = roughness, B = metallic (linear)
at 1024 px: a room's surfaces are seen at 1-2 m, one texel is a millimetre. make_materials.py imports every T_*.png of that folder
(by suffix: _BC, _N, the rest as masks); tools/ue_scripts/ship_room_materials.py makes the MI_SHIP_* instances that use them.
`python3 tools/art/interior_textures.py --sheet` also writes art/_cache/textures/_preview_interior.png (every set, tiled 2 x 2).

Run: uv run --python /opt/homebrew/bin/python3.13 --with pillow --with numpy python tools/art/interior_textures.py
Sources and licence: docs/licenze.csv (ambientCG, Lennart Demes, CC0).
"""
from __future__ import annotations

import io
import os
import sys
import urllib.request
import zipfile

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "art", "_downloads", "ambientcg")
OUT = os.path.join(ROOT, "art", "_cache", "textures")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh) ASTRA-art-helper"}
SIZE = 1024

# ASTRA name -> (ambientCG id, neutral amount). neutral = 1.0: the colour map becomes a grey detail map around mid-grey (the instance's Tint is the
# colour: albedo = Tint x 0.5 x detail); 0.0 keeps the photographed colours; in between mixes the two.
SETS: dict[str, tuple[str, float]] = {
    "CarpetWool": ("Carpet016", 1.0),         # cut-pile wool: lounges, wardroom, library, officers' quarters
    "WoodAsh": ("Wood095", 1.0),              # pale smooth wood grain: tables, slats, panelling (tinted from honey to walnut)
    "WoodDeck": ("WoodFloor051", 1.0),        # plank deck with joints: wardroom, chapel, officers' quarters (tinted dark teak)
    "TileSmall": ("Tiles133A", 0.0),          # glossy white square tiles with a thin grout: galley, heads, laboratory walls
    "TileBig": ("Tiles107", 0.0),             # large white glossy tiles: medical floors and walls
    "TileHex": ("Tiles071", 0.0),             # white hexagon mosaic: medical and wet-room floors
    "Terrazzo": ("Terrazzo004", 1.0),         # pale terrazzo: halls, concourse, garden paths
    "Perforated": ("", 0.0),                  # (procedural, below) hex-pitched perforated panel: acoustic panels, vents, ceiling tiles
    "DiamondPlate": ("DiamondPlate008C", 0.0),  # tread plate: engineering and workshop floors, stair treads
    "PlatesSciFi": ("MetalPlates017A", 0.0),  # octagonal floor / wall plating (the ship's own deck language)
    "Plaster": ("PaintedPlaster017", 1.0),    # painted wall with a fine texture: bulkheads of living spaces
    "LeatherSoft": ("Leather004", 1.0),       # smooth soft leather, tinted: sofas, bar stools, seat backs
    "LeatherTufted": ("Leather012", 1.0),     # button-tufted leather (the buttons are in the normal map): sofa backs, headboards
    "Cork": ("Cork004", 0.0),                 # notice boards
    "FabricWoven": ("Fabric062", 1.0),        # coarse woven upholstery / wall cloth, tinted
    "LeafAtlas": ("", 0.0),                   # (procedural, leaf_atlas) the surface of the leaves of the procedural plants: four kinds in a 2 x 2 atlas
}

NEUTRAL_LINEAR = 0.8                          # a neutral map's median in linear light: Tint ~ 1.25 x the albedo wanted


def fetch(acg: str) -> str:
    folder = os.path.join(SRC, acg)
    if os.path.isdir(folder) and any(f.endswith("_Color.jpg") for f in os.listdir(folder)):
        return folder
    url = f"https://ambientcg.com/get?file={acg}_1K-JPG.zip"
    print(f"  downloading {url}")
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    os.makedirs(folder, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in z.namelist():
            if n.lower().endswith((".jpg", ".png")) and "_NormalGL" not in n and not n.endswith(f"{acg}.png"):
                z.extract(n, folder)
    return folder


def find(folder: str, suffix: str) -> str | None:
    for f in sorted(os.listdir(folder)):
        if f.endswith(suffix):
            return os.path.join(folder, f)
    return None


def to_linear(c: np.ndarray) -> np.ndarray:
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c: np.ndarray) -> np.ndarray:
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(np.clip(c, 0, None), 1 / 2.4) - 0.055)


def load(path: str, mode: str = "RGB") -> np.ndarray:
    im = Image.open(path).convert(mode)
    if im.size != (SIZE, SIZE):
        im = im.resize((SIZE, SIZE), Image.LANCZOS)
    return np.asarray(im, dtype=np.float32) / 255.0


def save(arr: np.ndarray, path: str) -> None:
    Image.fromarray((np.clip(arr, 0, 1) * 255.0 + 0.5).astype(np.uint8)).save(path, optimize=True)


def perforated(name: str) -> None:
    """A procedural panel: round holes on a hexagonal pitch (6 mm holes, 10 mm pitch, 2 x 2 tiles in the 1 m texture: ~25 holes per 25 cm), a dark void in each, a soft
    bevelled rim in the normal map, ambient occlusion in the holes. Tileable (the pitch divides the texture)."""
    n = SIZE
    rows = 40                                                            # hex rows across the texture (an even number: it tiles)
    pitch = n / rows
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    row = np.floor(yy / (pitch * 0.8660254))
    off = (row % 2) * 0.5 * pitch
    cx = (np.floor((xx - off) / pitch) + 0.5) * pitch + off
    cy = (row + 0.5) * pitch * 0.8660254
    d = np.hypot(xx - cx, yy - cy) / pitch                                # 0 at a hole's centre, in pitches
    hole = np.clip((0.30 - d) / 0.03, 0.0, 1.0)                           # radius 0.30 pitch with a 1-px-ish soft edge
    rim = np.clip((0.40 - d) / 0.10, 0.0, 1.0) * (1.0 - hole)
    base = 0.62 + 0.05 * np.sin(xx * 0.05) * 0.0
    bc = np.dstack([base * (1.0 - hole) + 0.015 * hole] * 3)
    gy, gx = np.gradient(d.astype(np.float32))
    nx_, ny_ = -gx * rim * 6.0, -gy * rim * 6.0
    nz = np.sqrt(np.clip(1.0 - nx_ * nx_ - ny_ * ny_, 0.0, 1.0))
    nm = np.dstack([nx_ * 0.5 + 0.5, ny_ * 0.5 + 0.5, nz * 0.5 + 0.5])
    ao = 1.0 - 0.8 * hole - 0.25 * rim
    rough = 0.42 + 0.3 * hole
    metal = (1.0 - hole) * 0.85
    save(bc, os.path.join(OUT, f"T_{name}_BC.png"))
    save(nm, os.path.join(OUT, f"T_{name}_N.png"))
    save(np.dstack([ao, rough, metal]), os.path.join(OUT, f"T_{name}_ORM.png"))
    print(f"  {name:14s} <- procedural perforated panel ({rows} hex rows)")


def pack(name: str, acg: str, neutral: float) -> None:
    if name == "Perforated":
        return perforated(name)
    if name == "LeafAtlas":
        return leaf_atlas(name)
    folder = fetch(acg)
    bc = load(find(folder, "_Color.jpg"))
    nm_path = find(folder, "_NormalDX.jpg") or find(folder, "_NormalGL.jpg")
    nm = load(nm_path)
    if "_NormalGL" in nm_path:                      # OpenGL -> DirectX: flip green
        nm[..., 1] = 1.0 - nm[..., 1]
    rough = load(find(folder, "_Roughness.jpg"), "L")
    metal_p, ao_p = find(folder, "_Metalness.jpg"), find(folder, "_AmbientOcclusion.jpg")
    metal = load(metal_p, "L") if metal_p else np.zeros_like(rough)
    ao = load(ao_p, "L") if ao_p else np.ones_like(rough)
    if neutral > 0.0:
        lum = (to_linear(bc) * np.array([0.2126, 0.7152, 0.0722], np.float32)).sum(-1)
        grey = lum / max(float(np.median(lum)), 1e-4)                  # detail around 1.0 (linear)
        grey = np.clip(grey * NEUTRAL_LINEAR, 0.12, 1.0)
        grey_s = to_srgb(np.clip(grey, 0, 1))
        bc = bc * (1.0 - neutral) + np.dstack([grey_s] * 3) * neutral
    save(bc, os.path.join(OUT, f"T_{name}_BC.png"))
    save(nm, os.path.join(OUT, f"T_{name}_N.png"))
    save(np.dstack([ao, rough, metal]), os.path.join(OUT, f"T_{name}_ORM.png"))
    print(f"  {name:14s} <- {acg:18s} rough {rough.mean():.2f}  metal {metal.mean():.2f}  ao {ao.mean():.2f}  neutral {neutral}")


def _seg_dist(xx, yy, ax, ay, bx, by):
    """Distance of every pixel to the segment a-b (pixel units) and the position t along it."""
    vx, vy = bx - ax, by - ay
    ln2 = vx * vx + vy * vy + 1e-9
    t = np.clip(((xx - ax) * vx + (yy - ay) * vy) / ln2, 0.0, 1.0)
    return np.hypot(xx - (ax + t * vx), yy - (ay + t * vy)), t


def leaf_atlas(name: str = "LeafAtlas") -> None:
    """The surface of a leaf, four kinds in a 2 x 2 atlas (each tile: u across the blade, v from the base up to the tip; the outline is the mesh's, not the texture's):
    0 broadleaf (dark glossy green, pinnate veins), 1 fresh lettuce / herb (light, a thick pale midrib), 2 grass / grain / leek (parallel veins), 3 young tomato leaf (yellow-green,
    matte, a hint of red in the veins). Colour with veins and mottling, the veins in relief in the normal map and as a little ambient occlusion beside them."""
    T = SIZE // 2
    yy, xx = np.mgrid[0:T, 0:T].astype(np.float32)
    rng = np.random.default_rng(4)
    atlas_bc = np.zeros((SIZE, SIZE, 3), np.float32)
    atlas_n = np.zeros((SIZE, SIZE, 3), np.float32)
    atlas_orm = np.zeros((SIZE, SIZE, 3), np.float32)
    # smooth mottling shared by the kinds (low-frequency noise from a few random sines: tileable enough inside one leaf)
    def mottle(seed):
        r = np.random.default_rng(seed)
        out = np.zeros((T, T), np.float32)
        for _ in range(7):
            fx, fy = r.uniform(1.0, 6.0), r.uniform(1.0, 6.0)
            ph = r.uniform(0, 6.28)
            out += np.sin(xx / T * 6.283 * fx + yy / T * 6.283 * fy + ph) * r.uniform(0.3, 1.0)
        return out / 4.0
    kinds = [
        dict(base=(0.085, 0.30, 0.075), rib=(0.50, 0.66, 0.30), edge=0.55, n_veins=11, rib_w=0.022, vein_w=0.007, rough=0.38, angle=0.20, rib_taper=0.7),
        dict(base=(0.30, 0.52, 0.12), rib=(0.82, 0.90, 0.58), edge=0.80, n_veins=9, rib_w=0.05, vein_w=0.012, rough=0.5, angle=0.26, rib_taper=0.5),
        dict(base=(0.13, 0.36, 0.07), rib=(0.40, 0.58, 0.25), edge=0.7, n_veins=0, rib_w=0.012, vein_w=0.006, rough=0.5, angle=0.0, rib_taper=1.0),
        dict(base=(0.28, 0.45, 0.10), rib=(0.55, 0.62, 0.25), edge=0.7, n_veins=8, rib_w=0.018, vein_w=0.008, rough=0.6, angle=0.22, rib_taper=0.6),
    ]
    for k, kd in enumerate(kinds):
        u = xx / T                                                          # across the blade
        v = 1.0 - yy / T                                                    # base (0) .. tip (1)
        col = np.zeros((T, T, 3), np.float32)
        relief = np.zeros((T, T), np.float32)
        base = np.array(kd["base"], np.float32)
        m = mottle(10 + k)
        edge = np.clip(np.abs(u - 0.5) * 2.0, 0, 1)
        shade = 1.0 + 0.18 * m - (1.0 - kd["edge"]) * 0.5 * edge ** 2
        for c in range(3):
            col[..., c] = base[c] * shade
        rib_w = kd["rib_w"] * (1.0 - (1.0 - kd["rib_taper"]) * v)
        d_rib = np.abs(u - 0.5)
        rib = np.clip(1.0 - d_rib / rib_w, 0.0, 1.0)
        veins = np.zeros((T, T), np.float32)
        if kd["n_veins"]:
            for j in range(kd["n_veins"]):
                v0 = (j + 0.5) / kd["n_veins"] * 0.92
                for side in (-1, 1):
                    ax, ay = 0.5, v0
                    bx, by = 0.5 + side * 0.47, min(v0 + 0.26 * kd["angle"] / 0.2 * (1.0 - 0.3 * v0), 0.99)
                    dd, _t = _seg_dist(u, v, ax, ay, bx, by)
                    veins = np.maximum(veins, np.clip(1.0 - dd / kd["vein_w"], 0.0, 1.0) * (1.0 - 0.5 * _t))
        else:                                                               # parallel veins (grass, leek)
            for j in range(-6, 7):
                uu = 0.5 + j * 0.065
                veins = np.maximum(veins, np.clip(1.0 - np.abs(u - uu) / kd["vein_w"], 0.0, 1.0) * (0.55 if j else 1.0))
        vein = np.maximum(rib, veins)
        rc = np.array(kd["rib"], np.float32)
        for c in range(3):
            col[..., c] = col[..., c] * (1.0 - 0.8 * vein) + rc[c] * 0.8 * vein
        col += rng.normal(0, 0.006, col.shape).astype(np.float32)           # a little grain
        relief = vein * 0.6 - 0.15 * np.clip(1.0 - vein * 3.0, 0, 1) * 0.0
        gy, gx = np.gradient(relief)
        nx_, ny_ = -gx * 22.0, gy * 22.0
        nz = np.sqrt(np.clip(1.0 - nx_ ** 2 - ny_ ** 2, 0.0, 1.0))
        nm = np.dstack([nx_ * 0.5 + 0.5, ny_ * 0.5 + 0.5, nz * 0.5 + 0.5])
        ao = 1.0 - 0.25 * np.clip(np.abs(gx) + np.abs(gy), 0, 1) * 6.0 * 0.0 - 0.18 * edge ** 3
        rough = np.full((T, T), kd["rough"], np.float32) - 0.12 * vein
        ox, oy = (k % 2) * T, (k // 2) * T
        atlas_bc[oy:oy + T, ox:ox + T] = np.clip(col, 0, 1) ** (1 / 2.2)
        atlas_n[oy:oy + T, ox:ox + T] = nm
        atlas_orm[oy:oy + T, ox:ox + T] = np.dstack([ao, rough, np.zeros_like(rough)])
    save(atlas_bc, os.path.join(OUT, f"T_{name}_BC.png"))
    save(atlas_n, os.path.join(OUT, f"T_{name}_N.png"))
    save(atlas_orm, os.path.join(OUT, f"T_{name}_ORM.png"))
    print(f"  {name:14s} <- procedural leaf atlas (4 kinds)")


def sheet() -> None:
    names = list(SETS)
    cols = 5
    cell = 360
    rows = (len(names) + cols - 1) // cols
    im = Image.new("RGB", (cols * cell, rows * cell), (24, 24, 24))
    from PIL import ImageDraw
    dr = ImageDraw.Draw(im)
    for k, n in enumerate(names):
        p = os.path.join(OUT, f"T_{n}_BC.png")
        if not os.path.exists(p):
            continue
        t = Image.open(p).convert("RGB").resize((cell // 2 - 2, cell // 2 - 2))
        x, y = (k % cols) * cell, (k // cols) * cell
        for i in range(2):
            for j in range(2):
                im.paste(t, (x + 2 + i * (cell // 2 - 2), y + 2 + j * (cell // 2 - 2)))
        dr.text((x + 6, y + 6), n, fill=(255, 255, 0))
    path = os.path.join(OUT, "_preview_interior.png")
    im.save(path)
    print("sheet", path)


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    print("Interior texture sets (ambientCG, CC0):")
    for name, (acg, neutral) in SETS.items():
        if only and name not in only:
            continue
        pack(name, acg, neutral)
    if "--sheet" in sys.argv:
        sheet()
    return 0


if __name__ == "__main__":
    sys.exit(main())
