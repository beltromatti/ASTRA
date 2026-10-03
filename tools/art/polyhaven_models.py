"""ARTE-INTERNI: Poly Haven models (CC0, no account, no key) for the rooms of the Aquila: plants and small objects that a procedural model
cannot match (the leaves of a real fern, a real ceramic pot).

`download(id)` fetches the glTF of a model at 1K (the .gltf, its .bin and the textures it lists) into art/_downloads/polyhaven/<id>/ (gitignored);
`python3 tools/art/polyhaven_models.py <id> [<id> ...]` does it from the command line and prints the size on disk. The Blender side
(art/blender/ship_assets.py) imports the glTF, remaps its materials to MI_SHIP_* slots and puts the geometry into a room's SParts.
Every model used is in docs/licenze.csv.

`python3 tools/art/polyhaven_models.py --all` downloads every model of USED below and packs its textures as art/_cache/textures/T_PH_<Name>_{BC,N,ORM}.png (BC sRGB;
N DirectX: the glTF's OpenGL normal with the green channel flipped; ORM: R occlusion, G roughness, B metallic: the glTF's "arm" map as it is, or a "rough" map with
no occlusion and no metal); the Unreal instances (MI_SHIP_PH_*, data/ship/room_materials.json) use them with the model's own UVs.

Run: uv run --python /opt/homebrew/bin/python3.13 --with pillow --with numpy python tools/art/polyhaven_models.py --all
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request

import numpy as np
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DST = os.path.join(ROOT, "art", "_downloads", "polyhaven")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh) ASTRA-art-helper"}
RES = "1k"


def _get(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        return r.read()


def info(asset: str) -> dict:
    return json.loads(_get(f"https://api.polyhaven.com/info/{asset}"))


def download(asset: str, res: str = RES) -> str:
    """The folder of the model's glTF (its .gltf file is <folder>/<asset>_<res>.gltf)."""
    folder = os.path.join(DST, asset)
    files = json.loads(_get(f"https://api.polyhaven.com/files/{asset}"))
    entry = files["gltf"][res]["gltf"]
    gltf_name = entry["url"].rsplit("/", 1)[1]
    if os.path.exists(os.path.join(folder, gltf_name)):
        return folder
    os.makedirs(folder, exist_ok=True)
    todo = {gltf_name: entry["url"]}
    for rel, inc in entry.get("include", {}).items():
        todo[rel] = inc["url"]
    for rel, url in todo.items():
        path = os.path.join(folder, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(_get(url))
    return folder


# (poly haven id, glTF material, ASTRA name, size in px): the textures of every model that a room uses
USED = [
    ("potted_plant_02", "potted_plant_02_leaves", "Syngonium", 1024),
    ("potted_plant_04", "potted_plant_04", "Haworthia", 1024),
    ("potted_plant_01", "potted_plant_01_leaves", "FicusLeaf", 1024),
    ("potted_plant_01", "potted_plant_01_pot", "FicusWood", 512),
    ("pachira_aquatica_01", "pachira_aquatica_01_leaves", "PachiraLeaf", 1024),
    ("pachira_aquatica_01", "pachira_aquatica_01_bark", "PachiraBark", 512),
    ("fern_02", "fern_02", "Fern", 1024),
    ("calathea_orbifolia_01", "calathea_orbifolia_01", "Calathea", 1024),
    ("anthurium_botany_01", "anthurium_botany_01", "Anthurium", 1024),
]
TEX_OUT = os.path.join(ROOT, "art", "_cache", "textures")


def _img(folder: str, name: str, size: int, mode: str):
    p = os.path.join(folder, "textures", name)
    if not os.path.exists(p):
        return None
    im = Image.open(p).convert(mode)
    if im.size != (size, size):
        im = im.resize((size, size), Image.LANCZOS)
    return np.asarray(im, dtype=np.float32) / 255.0


def pack(asset: str, mat: str, out: str, size: int = 1024) -> None:
    """glTF textures -> T_PH_<out>_BC / _N / _ORM."""
    folder = download(asset)
    os.makedirs(TEX_OUT, exist_ok=True)
    bc = _img(folder, f"{mat}_diff_1k.jpg", size, "RGB")
    nm = _img(folder, f"{mat}_nor_gl_1k.jpg", size, "RGB")
    nm[..., 1] = 1.0 - nm[..., 1]                                   # OpenGL -> DirectX
    arm = _img(folder, f"{mat}_arm_1k.jpg", size, "RGB")
    if arm is None:                                                 # a separate roughness map: no occlusion, no metal
        rough = _img(folder, f"{mat}_rough_1k.jpg", size, "L")
        arm = np.dstack([np.ones_like(rough), rough, np.zeros_like(rough)])

    def save(a, suffix):
        Image.fromarray((np.clip(a, 0, 1) * 255.0 + 0.5).astype(np.uint8)).save(os.path.join(TEX_OUT, f"T_PH_{out}_{suffix}.png"), optimize=True)
    save(bc, "BC")
    save(nm, "N")
    save(arm, "ORM")
    print(f"  T_PH_{out:12s} <- {asset}/{mat} ({size}px)")


def disk_mb(folder: str) -> float:
    n = 0
    for dp, _dn, fn in os.walk(folder):
        n += sum(os.path.getsize(os.path.join(dp, f)) for f in fn)
    return n / 1048576.0


if __name__ == "__main__":
    if "--all" in sys.argv:
        for asset, mat, out, size in USED:
            pack(asset, mat, out, size)
        sys.exit(0)
    for a in sys.argv[1:]:
        f = download(a)
        i = info(a)
        print(f"{a}: {disk_mb(f):.1f} MB in {f}; authors {list(i.get('authors', {}))}, {i.get('polycount')} tris, tags {i.get('tags', [])[:6]}")
