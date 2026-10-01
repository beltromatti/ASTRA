"""ASN Aquila interior kit (NAVE): the Blender toolkit of the ship's interior. It builds on the bridge v3 toolkit
(bridge3_lib: the frame builder FB, the shared materials, the lamp palette) and adds the ship's label atlas, the parts builder
that uses it, a few small builders and the preview materials (Eevee, headless) for the new MI_SHIP_* slots.

Conventions (docs/STILE.md §11, docs/NAVE.md): every builder works in LAYOUT coordinates (X forward, Y starboard, Z up, metres):
FB mirrors Y on the way out, so the FBX meshes land exactly on the plan in Unreal. Material slots are the names of the Unreal
instances (MI_ASTRA_*, MI_BRG3_*, MI_SHIP_*); the labels of the ship share ONE slot (MI_SHIP_Labels) and pick their tile by UV.
"""
from __future__ import annotations

import json
import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import bridge3_lib as L  # noqa: E402
import bridge3_preview as PV  # noqa: E402
from bridge3_lib import FB, T, Rx, Ry, Rz, frame, lerp, polar  # noqa: E402

ROOT = L.ROOT
MAIN_CHECKOUT = PV.MAIN_CHECKOUT
SHIP_CACHE = [os.path.join(ROOT, "art", "_cache", "ship"), os.path.join(MAIN_CHECKOUT, "art", "_cache", "ship")]

# ------------------------------------------------------------------------------------------------------------ materials
STRUCT, TRIM, RUBBER, COMPOSITE, IVORY, DECK, DGLASS = L.STRUCT, L.TRIM, L.RUBBER, L.COMPOSITE, L.IVORY, L.DECK, L.DGLASS
LAMP, LAMP_DIM, LAMP_HOT, GLASS, LEATHER = L.LAMP, L.LAMP_DIM, L.LAMP_HOT, L.GLASS, L.LEATHER
LABEL = "MI_SHIP_Labels"
# new hard-surface instances (parent M_ASTRA_Hard with a tint and a cloth / paint texture: tools/ue_scripts/build_ship_interior.py)
LAMINATE = "MI_SHIP_Laminate"        # pale grey-blue work surfaces
STEEL = "MI_SHIP_Steel"              # bright stainless steel (galley, lab): brushed, metallic
FABRIC_NAVY, FABRIC_RUST, FABRIC_GREY, FABRIC_SAND = "MI_SHIP_FabricNavy", "MI_SHIP_FabricRust", "MI_SHIP_FabricGrey", "MI_SHIP_FabricSand"
BEDDING = "MI_SHIP_Bedding"          # sheets and pillows
WOOD = "MI_SHIP_Wood"                # dark wood veneer (cabin furniture, library)
CRATE_OLIVE, CRATE_ORANGE, CRATE_BLUE, CRATE_GREY = "MI_SHIP_CrateOlive", "MI_SHIP_CrateOrange", "MI_SHIP_CrateBlue", "MI_SHIP_CrateGrey"
LEAF = "MI_SHIP_Leaf"                # plants
TILE = "MI_SHIP_Tile"                # white wall / floor tile (galley, heads, lab)
PAINT_RED = "MI_SHIP_PaintRed"       # red fire-safety paint (hydrants, extinguishers), hazard yellow is in the labels
SOIL = "MI_SHIP_Soil"                # planters
NEW_SLOTS = [LABEL, LAMINATE, STEEL, FABRIC_NAVY, FABRIC_RUST, FABRIC_GREY, FABRIC_SAND, BEDDING, WOOD, CRATE_OLIVE, CRATE_ORANGE,
             CRATE_BLUE, CRATE_GREY, LEAF, TILE, PAINT_RED, SOIL]

# ------------------------------------------------------------------------------------------------------------ the atlas
LABELS: dict[str, tuple[float, float, float, float]] = {}
LABEL_TEXT: dict[str, str] = {}
ATLAS_PX = [4096.0, 4096.0]              # the atlas's size in pixels (labels.json says: it is taller than wide since NAVE-3)


def find_cache(name: str) -> str | None:
    for d in SHIP_CACHE:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


def load_labels() -> dict:
    path = find_cache("labels.json")
    if path is None:
        raise RuntimeError("art/_cache/ship/labels.json missing: run  uv run --python /opt/homebrew/bin/python3.13 --with pillow "
                           "--with numpy python tools/art/ship_textures.py")
    data = json.load(open(path, encoding="utf-8"))
    LABELS.clear()
    LABEL_TEXT.clear()
    for k, v in data["rects"].items():
        LABELS[k] = tuple(v)
    for k, t in data.get("text", {}).items():
        LABEL_TEXT.setdefault(t, k)
    ATLAS_PX[:] = [float(v) for v in data.get("size", [4096, 4096])]
    return LABELS


class SFB(FB):
    """Frame builder with the ship's label atlas (same tile names as the bridge atlas, plus the ship's own)."""

    def label(self, center, w: float, h: float, facing, cell: str, up=(0, 0, 1), atlas=None):
        cell = LABEL_TEXT.get(cell, cell)
        r = LABELS.get(cell)
        if r is None:
            raise KeyError(f"label {cell!r} is not in the ship atlas")
        u0, v0, u1, v1 = r
        return self.screen(center, w, h, LABEL, facing, up=up, u_range=(u0, u1), v_range=(v0, v1))

    def label_fit(self, center, w: float, cell: str, facing, up=(0, 0, 1)):
        """A label of width w with the tile's own aspect ratio."""
        cell = LABEL_TEXT.get(cell, cell)
        u0, v0, u1, v1 = LABELS[cell]
        aspect = ((u1 - u0) * ATLAS_PX[0]) / ((v1 - v0) * ATLAS_PX[1])
        return self.label(center, w, w / aspect, facing, cell, up=up)


class SParts(L.Parts):
    """Parts (body / fine / emissive / soft groups) built with SFB."""

    def __init__(self, bevel: float = 0.006, fine_bevel: float = 0.003, angle: float = 35.0) -> None:
        super().__init__(bevel, fine_bevel, angle)
        for name in ("body", "fine", "emit", "soft"):
            getattr(self, name).bm.free()
            setattr(self, name, SFB())


# ---------------------------------------------------------------------------------------------------- small builders
def lamp_strip(fb: FB, p0, p1, w: float, h: float, cell: str, mat: str = LAMP_DIM):
    """A lamp bar between two points (any direction): a thin box lying along p0 -> p1."""
    a, b = Vector(p0), Vector(p1)
    d = b - a
    ln = d.length
    if ln < 1e-4:
        return
    yaw = math.degrees(math.atan2(d.y, d.x))
    mid = (a + b) / 2
    fb.lamp_cbox((mid.x, mid.y, mid.z), (ln, w, h), cell, mat, Rz(yaw))


def bolt(fb: FB, p, r: float = 0.009, h: float = 0.007, axis=(0, 1, 0), mat: str = TRIM):
    a = Vector(p)
    d = Vector(axis).normalized() * h
    fb.cyl(a, a + d, r, mat, seg=8)


def rbox(fb: FB, lo, hi, mat: str, inset: float = 0.0):
    """A box shrunk by `inset` on every side (panel pockets)."""
    fb.box((lo[0] + inset, lo[1] + inset, lo[2] + inset), (hi[0] - inset, hi[1] - inset, hi[2] - inset), mat)


def frame_rect(fb: FB, x0: float, x1: float, y0: float, y1: float, z0: float, z1: float, t: float, mat: str = TRIM,
               axis: str = "y", depth: float = 0.06):
    """A rectangular frame (four bars of width t) in the plane spanning (u, z): axis 'y' = a frame on a wall that faces along y
    (u = x), 'x' = a frame on a wall that faces along x (u = y); `depth` is the frame's thickness across the wall."""
    if axis == "y":
        fb.box((x0, y0, z0), (x1, y1, z0 + t), mat)
        fb.box((x0, y0, z1 - t), (x1, y1, z1), mat)
        fb.box((x0, y0, z0 + t), (x0 + t, y1, z1 - t), mat)
        fb.box((x1 - t, y0, z0 + t), (x1, y1, z1 - t), mat)
    else:
        fb.box((x0, y0, z0), (x1, y1, z0 + t), mat)
        fb.box((x0, y0, z1 - t), (x1, y1, z1), mat)
        fb.box((x0, y0, z0 + t), (x1, y0 + t, z1 - t), mat)
        fb.box((x0, y1 - t, z0 + t), (x1, y1, z1 - t), mat)


# ---------------------------------------------------------------------------------------------------- preview materials
def _label_mat(strength: float = 1.6) -> bpy.types.Material:
    mt = PV.Mat(LABEL)
    path = find_cache("T_SHIP_Labels.png")
    bsdf = mt.node("ShaderNodeBsdfPrincipled", 500, 0)
    bsdf.inputs["Base Color"].default_value = (0.02, 0.02, 0.025, 1)
    bsdf.inputs["Roughness"].default_value = 0.35
    bsdf.inputs["Emission Strength"].default_value = strength
    t = mt.image(path, x=-300, y=0)
    mt.link(t, "Color", bsdf, "Emission Color")
    mt.link(t, "Color", bsdf, "Base Color")
    mt.link(bsdf, "BSDF", mt.out, "Surface")
    return mt.m


def _fix_palette_path() -> None:
    """The lamp palette lives in art/_cache/bridge3 of the checkout that ran the bridge textures; a worktree may not have it."""
    if not os.path.exists(os.path.join(L.CACHE, "T_BRG3_Lamps.png")):
        alt = os.path.join(MAIN_CHECKOUT, "art", "_cache", "bridge3")
        if os.path.exists(os.path.join(alt, "T_BRG3_Lamps.png")):
            L.CACHE = alt


def srgb(h: str):
    return PV.srgb_to_linear(h)


def make_preview_materials() -> None:
    """Every material of the scene by slot name: the bridge v3's (MI_ASTRA_*, MI_BRG3_*) and the ship's MI_SHIP_*."""
    _fix_palette_path()
    PV.make_materials({})
    for im in bpy.data.images:                       # the palette keeps the alert weight in its alpha: the preview must not premultiply the colour by it
        if "Lamps" in im.name:
            im.alpha_mode = "CHANNEL_PACKED"
    pbr = PV.pbr
    pbr(LAMINATE, (0.42, 0.46, 0.50), "PanelPaint", 1.0, (0.28, 0.42), 0.0, 0.0, 0.25, 0.3)
    pbr(STEEL, (0.62, 0.64, 0.66), "Brushed", 1.0, (0.20, 0.36), 0.0, 1.0, 0.5, 0.6)
    pbr(FABRIC_NAVY, (0.030, 0.050, 0.11), "Linen", 3.0, (0.55, 0.8), 0.0, 0.0, 0.5, 0.7)
    pbr(FABRIC_RUST, (0.22, 0.075, 0.04), "Linen", 3.0, (0.55, 0.8), 0.0, 0.0, 0.5, 0.7)
    pbr(FABRIC_GREY, (0.12, 0.125, 0.13), "Linen", 3.0, (0.55, 0.8), 0.0, 0.0, 0.5, 0.7)
    pbr(FABRIC_SAND, (0.36, 0.30, 0.20), "Linen", 3.0, (0.55, 0.8), 0.0, 0.0, 0.5, 0.7)
    pbr(BEDDING, (0.62, 0.64, 0.66), "Cotton", 3.0, (0.6, 0.85), 0.0, 0.0, 0.5, 0.6)
    pbr(WOOD, (0.20, 0.11, 0.06), "WoodDark", 1.0, (0.28, 0.5), 0.0, 0.0, 0.7, 0.8)
    pbr(CRATE_OLIVE, (0.10, 0.13, 0.055), "PanelPaint", 1.0, (0.5, 0.7), 0.0, 0.0, 0.25, 0.3)
    pbr(CRATE_ORANGE, (0.55, 0.20, 0.03), "PanelPaint", 1.0, (0.5, 0.7), 0.0, 0.0, 0.25, 0.3)
    pbr(CRATE_BLUE, (0.045, 0.09, 0.20), "PanelPaint", 1.0, (0.5, 0.7), 0.0, 0.0, 0.25, 0.3)
    pbr(CRATE_GREY, (0.22, 0.23, 0.24), "PanelPaint", 1.0, (0.5, 0.7), 0.0, 0.0, 0.25, 0.3)
    pbr(LEAF, (0.045, 0.20, 0.04), "Linen", 4.0, (0.45, 0.65), 0.0, 0.0, 0.5, 0.6)
    pbr(TILE, (0.62, 0.64, 0.62), "PanelPaint", 1.0, (0.12, 0.25), 0.0, 0.0, 0.2, 0.3, coat=0.3, coat_rough=0.1)
    pbr(PAINT_RED, (0.46, 0.035, 0.025), "PanelPaint", 1.0, (0.3, 0.5), 0.0, 0.0, 0.2, 0.3)
    pbr(SOIL, (0.035, 0.022, 0.014), "Linen", 4.0, (0.7, 0.9), 0.0, 0.0, 0.5, 0.8)
    _label_mat(1.4)
    for m in bpy.data.materials:                                  # anything else the scene uses gets a neutral grey
        if not m.use_nodes or not m.node_tree.nodes:
            pbr(m.name, (0.3, 0.3, 0.3))
