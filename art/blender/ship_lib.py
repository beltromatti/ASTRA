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

import bmesh
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
# ARTE-INTERNI: textured finishes. The table of their parameters is data/ship/room_materials.json (the Blender previews below and the Unreal instances made by
# tools/ue_scripts/ship_room_materials.py read the same entries); the texture sets are packed by tools/art/interior_textures.py and tools/art/polyhaven_models.py.
CARPET_SLATE, CARPET_SAND, CARPET_RUST, CARPET_MOSS = "MI_SHIP_CarpetSlate", "MI_SHIP_CarpetSand", "MI_SHIP_CarpetRust", "MI_SHIP_CarpetMoss"    # cut-pile wool carpet
TEAK = "MI_SHIP_Teak"                    # plank deck, dark teak
OAK, WALNUT = "MI_SHIP_Oak", "MI_SHIP_Walnut"                  # smooth wood grain: honey oak (tables, slats), walnut (panelling, bar fronts)
TERRAZZO = "MI_SHIP_Terrazzo"            # pale speckled floor
TERRAZZO_DARK = "MI_SHIP_TerrazzoDark"   # the same in mid grey (the mess hall)
TILE_FLOOR, TILE_HEX, TILE_WALL = "MI_SHIP_TileFloor", "MI_SHIP_TileHex", "MI_SHIP_TileWall"          # glossy tiles: floors, hex mosaic, wall tiles
TREAD, PLATING = "MI_SHIP_Tread", "MI_SHIP_Plating"             # diamond tread plate; octagonal plating
PLASTER_IVORY, PLASTER_SAGE, PLASTER_SLATE, PLASTER_TEAL = "MI_SHIP_PlasterIvory", "MI_SHIP_PlasterSage", "MI_SHIP_PlasterSlate", "MI_SHIP_PlasterTeal"   # painted walls
PERF = "MI_SHIP_Perf"                    # perforated acoustic panel
CORK = "MI_SHIP_Cork"                    # notice boards
LEATHER_TAN, LEATHER_NAVY, LEATHER_OX, LEATHER_CREAM = "MI_SHIP_LeatherTan", "MI_SHIP_LeatherNavy", "MI_SHIP_LeatherOx", "MI_SHIP_LeatherCream"
TUFT_NAVY, TUFT_SAND = "MI_SHIP_TuftNavy", "MI_SHIP_TuftSand"   # button-tufted leather
WEAVE_TEAL, WEAVE_SAND, WEAVE_SLATE, WEAVE_RUST = "MI_SHIP_WeaveTeal", "MI_SHIP_WeaveSand", "MI_SHIP_WeaveSlate", "MI_SHIP_WeaveRust"        # woven upholstery
BRASS, COPPER = "MI_SHIP_Brass", "MI_SHIP_Copper"               # warm metals (lamps, rails, kitchen)
WHITE_GLOSS, CERAMIC = "MI_SHIP_WhiteGloss", "MI_SHIP_CeramicWhite"   # appliance plastic; pots, crockery, sanitaryware
TERRACOTTA = "MI_SHIP_Terracotta"
PAPER = "MI_SHIP_Paper"
STEM, BARK = "MI_SHIP_Stem", "MI_SHIP_Bark"                     # plants
GRASS, MOSS, EARTH = "MI_SHIP_Grass", "MI_SHIP_Moss", "MI_SHIP_Earth"   # the ground of the gardens (ambientCG Grass004, Moss002, Ground037)
LEAF_GREEN, LETTUCE, FRUIT = "MI_SHIP_LeafGreen", "MI_SHIP_Lettuce", "MI_SHIP_Fruit"
SWATCH = "MI_SHIP_Swatch"                # every small coloured thing (books, crockery, boxes, food, toys): ONE slot, the colour is picked from a 64-colour palette by UV cell
# palette of T_Swatch_BC (8 x 8 cells, row-major from the top-left); tools/art/interior_textures.SWATCH_COLORS paints the same order
SWATCH_NAMES = ["navy", "oxblood", "forest", "mustard", "slate", "teal", "rust", "cream",
                "charcoal", "tan", "denim", "olive", "plum", "rose", "sand", "white",
                "red", "orange", "yellow", "green", "cyan", "blue", "purple", "magenta",
                "grey1", "grey2", "grey3", "grey4", "grey5", "grey6", "grey7", "grey8",
                "w_oak", "w_honey", "w_walnut", "w_ebony", "w_birch", "w_cherry", "w_teak", "w_pine",
                "f_apple", "f_orange", "f_banana", "f_lettuce", "f_tomato", "f_carrot", "f_bread", "f_cheese",
                "m_teal", "m_white", "m_blood", "m_saline", "m_purple", "m_yellow", "m_orange", "m_green",
                "brass", "copper", "steel", "rubber", "glass", "paper", "cork", "leather"]
SWATCH_INDEX = {n: i for i, n in enumerate(SWATCH_NAMES)}
BOOK_COLORS = ["navy", "oxblood", "forest", "mustard", "slate", "teal", "rust", "cream", "charcoal", "tan", "denim", "olive", "plum", "sand", "white"]
ROOM_MATERIAL_FILE = os.path.join(ROOT, "data", "ship", "room_materials.json")
ROOM_MATERIALS: dict = {}               # name -> the entry of room_materials.json (read once)


def _load_room_materials() -> dict:
    if not ROOM_MATERIALS:
        with open(ROOM_MATERIAL_FILE, encoding="utf-8") as fh:
            ROOM_MATERIALS.update(json.load(fh)["materials"])
    return ROOM_MATERIALS


ROOM_SLOTS = list(_load_room_materials())
NEW_SLOTS = [LABEL, LAMINATE, STEEL, FABRIC_NAVY, FABRIC_RUST, FABRIC_GREY, FABRIC_SAND, BEDDING, WOOD, CRATE_OLIVE, CRATE_ORANGE,
             CRATE_BLUE, CRATE_GREY, LEAF, TILE, PAINT_RED, SOIL] + ROOM_SLOTS

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

    # -- primitives without the whole-mesh normal recalculation (bmesh.ops.recalc_face_normals costs time proportional to the whole mesh: a room with two thousand boxes took a minute):
    #    a cube, a cone or a sphere made by bmesh is outward-facing in its own matrix; a matrix that mirrors (the builder's frame always does) turns it inside out, so reverse it
    def _fast(self, faces, mat: str, m: Matrix):
        idx = self.mi(mat)
        for f in faces:
            f.material_index = idx
        if m.determinant() < 0:
            bmesh.ops.reverse_faces(self.bm, faces=faces)
        return faces

    _CUBE = [(-0.5, -0.5, -0.5), (0.5, -0.5, -0.5), (0.5, 0.5, -0.5), (-0.5, 0.5, -0.5), (-0.5, -0.5, 0.5), (0.5, -0.5, 0.5), (0.5, 0.5, 0.5), (-0.5, 0.5, 0.5)]
    _CUBE_FACES = [(0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (1, 2, 6, 5), (2, 3, 7, 6), (3, 0, 4, 7)]       # outward-facing when the matrix does not mirror

    def cbox(self, center, size, mat: str, rot: Matrix | None = None):
        """A box: eight vertices and six quads made directly (no bmesh operator: those cost time proportional to the whole mesh)."""
        m = self.frame @ T(*center) @ (rot if rot is not None else Matrix.Identity(4)) @ Matrix.Diagonal((size[0], size[1], size[2], 1.0))
        vs = [self.bm.verts.new(m @ Vector(c)) for c in self._CUBE]
        flip = m.determinant() < 0
        idx = self.mi(mat)
        faces = []
        for q in self._CUBE_FACES:
            f = self.bm.faces.new([vs[i] for i in (reversed(q) if flip else q)])
            f.material_index = idx
            faces.append(f)
        return faces

    def cyl(self, p0, p1, r: float, mat: str, seg: int = 16, r2: float | None = None, caps: bool = True):
        """A cylinder or cone frustum from p0 (radius r) to p1 (radius r2), made directly."""
        a, b = Vector(p0), Vector(p1)
        d = b - a
        if d.length < 1e-9:
            return []
        rot = Vector((0.0, 0.0, 1.0)).rotation_difference(d.normalized()).to_matrix().to_4x4()
        m = self.frame @ T(*a) @ rot
        ln = d.length
        r2 = r if r2 is None else r2
        ring0, ring1 = [], []
        for j in range(seg):
            ang = 2.0 * math.pi * j / seg
            c, s_ = math.cos(ang), math.sin(ang)
            ring0.append(self.bm.verts.new(m @ Vector((r * c, r * s_, 0.0))))
            ring1.append(self.bm.verts.new(m @ Vector((r2 * c, r2 * s_, ln))))
        flip = m.determinant() < 0
        idx = self.mi(mat)
        faces = []

        def face(vs):
            f = self.bm.faces.new(list(reversed(vs)) if flip else vs)
            f.material_index = idx
            faces.append(f)
        for j in range(seg):
            k = (j + 1) % seg
            face([ring0[j], ring0[k], ring1[k], ring1[j]])
        if caps:
            face(list(reversed(ring0)))
            face(list(ring1))
        return faces

    def sphere(self, center, r: float, mat: str, seg: int = 16, rings: int = 10, squash=(1.0, 1.0, 1.0)):
        m = self.frame @ T(*center) @ Matrix.Diagonal((r * squash[0], r * squash[1], r * squash[2], 1.0))
        geom = bmesh.ops.create_uvsphere(self.bm, u_segments=seg, v_segments=rings, radius=1.0, matrix=m)
        return self._fast(self._faces_of(geom["verts"]), mat, m)

    # -- the colour swatch: one material for every small coloured thing (the palette cell is the UV of every face)
    def paint(self, faces, color):
        """Give already built faces (a box, a rounded box, a lathe) a palette colour (a name of SWATCH_NAMES or a cell index) and the swatch material."""
        uv = swatch_uv(color)
        idx = self.mi(SWATCH)
        for f in faces:
            f.material_index = idx
        self._paint(faces, uv)
        return faces

    def swatch_box(self, lo, hi, color):
        return self.paint(self.box(lo, hi, SWATCH), color)

    def swatch_cyl(self, p0, p1, r: float, color, seg: int = 12, r2: float | None = None):
        return self.paint(self.cyl(p0, p1, r, SWATCH, seg=seg, r2=r2), color)


def swatch_uv(color) -> tuple[float, float]:
    i = SWATCH_INDEX[color] if isinstance(color, str) else int(color)
    return ((i % 8 + 0.5) / 8.0, 1.0 - (i // 8 + 0.5) / 8.0)


class SParts(L.Parts):
    """Parts (body / fine / emissive / soft groups) built with SFB."""

    BEVEL_SEGMENTS = {"body": 1, "fine": 1}              # ARTE-INTERNI: one segment (a chamfer): a bevelled box was ~120 triangles with two, now ~45; at 5 mm nobody sees the difference

    def __init__(self, bevel: float = 0.006, fine_bevel: float = 0.003, angle: float = 35.0) -> None:
        super().__init__(bevel, fine_bevel, angle)
        for name in ("body", "fine", "emit", "soft"):
            getattr(self, name).bm.free()
            setattr(self, name, SFB())

    def build(self, name: str, uv_meter: float = 1.0):
        """Parts.build with the bevel segments of BEVEL_SEGMENTS per group."""
        objs = []
        for tag, fb, bev in (("body", self.body, self.bevel), ("fine", self.fine, self.fine_bevel), ("soft", self.soft, self.soft_bevel), ("emit", self.emit, 0.0)):
            if len(fb.bm.faces) == 0:
                fb.bm.free()
                continue
            o = fb.to_object(f"{name}_{tag}")
            if bev > 0:
                A.bevel_and_normals(o, width=bev, segments=self.BEVEL_SEGMENTS.get(tag, 2), angle_deg=self.angle)
            A.box_uv(o, texel_m=uv_meter)
            if tag == "soft":                                      # cushions and other organic parts: smooth shading
                bpy.ops.object.select_all(action="DESELECT")
                o.select_set(True)
                bpy.context.view_layer.objects.active = o
                bpy.ops.object.shade_smooth_by_angle(angle=math.radians(50))
            objs.append(o)
        if not objs:
            raise RuntimeError(f"{name}: empty mesh")
        return A.join(objs, name)


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
    for name, e in _load_room_materials().items():                 # ARTE-INTERNI: the finishes of data/ship/room_materials.json
        tint = tuple(c * e.get("k", 1.0) for c in PV.srgb_to_linear(e["tint"]))
        pbr(name, tint, e["set"], e.get("uv", 1.0), tuple(e.get("rough", (0.4, 0.7))), e.get("metal_bias", 0.0), e.get("metal_map", 0.0),
            e.get("influence", 1.0), e.get("normal", 0.6), e.get("coat", 0.0), e.get("coat_rough", 0.12), 0.5)
    _label_mat(1.4)
    for m in bpy.data.materials:                                  # anything else the scene uses gets a neutral grey
        if not m.use_nodes or not m.node_tree.nodes:
            pbr(m.name, (0.3, 0.3, 0.3))
