"""Preview renders of the bridge v3 (Blender Eevee, headless): materials that mimic the Unreal instances, the lights of the
data file, a starfield outside, placeholder UI on the live screens, and the cameras of docs/progressi/bridge_v3.

Only for looking at the result: nothing here is exported. Materials are matched by SLOT NAME (the Unreal instance names).
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

MAIN_CHECKOUT = "/Users/beltromatti/Desktop/ASTRA"
TEX_DIRS = [os.path.join(L.ROOT, "art", "_cache", "textures"), os.path.join(MAIN_CHECKOUT, "art", "_cache", "textures")]
UI_DIRS = [os.path.join(L.ROOT, "art", "_cache", "ui"), os.path.join(MAIN_CHECKOUT, "art", "_cache", "ui")]
SKY_DIRS = [os.path.join(L.ROOT, "art", "_cache", "sky"), os.path.join(MAIN_CHECKOUT, "art", "_cache", "sky")]


def find(dirs, name):
    for d in dirs:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


def srgb_to_linear(h: str):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


# ---------------------------------------------------------------------------------------------------------- materials
class Mat:
    def __init__(self, name: str) -> None:
        self.m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        self.m.use_nodes = True
        self.nt = self.m.node_tree
        self.nt.nodes.clear()
        self.out = self.nt.nodes.new("ShaderNodeOutputMaterial")
        self.out.location = (900, 0)
        self.y = 0

    def node(self, kind: str, x: float = 0.0, y: float = 0.0, **kw):
        n = self.nt.nodes.new(kind)
        n.location = (x, y)
        for k, v in kw.items():
            setattr(n, k, v)
        return n

    def link(self, a, out, b, inp):
        self.nt.links.new(a.outputs[out], b.inputs[inp])

    def image(self, path: str, non_color: bool = False, interp: str = "Linear", x=-800, y=0):
        n = self.node("ShaderNodeTexImage", x, y)
        img = bpy.data.images.load(path, check_existing=True)
        if non_color:
            img.colorspace_settings.name = "Non-Color"
        n.image = img
        n.interpolation = interp
        return n


def _uv_scaled(mt: Mat, scale: float, x=-1200, y=0):
    uv = mt.node("ShaderNodeTexCoord", x, y)
    mp = mt.node("ShaderNodeMapping", x + 200, y)
    mp.inputs["Scale"].default_value = (scale, scale, scale)
    mt.link(uv, "UV", mp, "Vector")
    return mp


def pbr(name: str, tint, tex: str | None = None, uv_scale: float = 1.0, rough=(0.3, 0.5), metal=0.0, metal_from_map: float = 0.0,
        influence: float = 0.5, normal: float = 0.6, coat: float = 0.0, coat_rough: float = 0.1, spec: float = 0.5,
        emission=None, alpha: float | None = None) -> bpy.types.Material:
    mt = Mat(name)
    bsdf = mt.node("ShaderNodeBsdfPrincipled", 600, 0)
    mt.link(bsdf, "BSDF", mt.out, "Surface")
    tint = tuple(tint) + (1.0,)
    bsdf.inputs["Base Color"].default_value = tint
    bsdf.inputs["Metallic"].default_value = metal
    bsdf.inputs["Roughness"].default_value = (rough[0] + rough[1]) / 2
    bsdf.inputs["Specular IOR Level"].default_value = spec
    if coat > 0:
        bsdf.inputs["Coat Weight"].default_value = coat
        bsdf.inputs["Coat Roughness"].default_value = coat_rough
    if tex:
        bc = find(TEX_DIRS, f"T_{tex}_BC.png")
        nm = find(TEX_DIRS, f"T_{tex}_N.png")
        orm = find(TEX_DIRS, f"T_{tex}_ORM.png")
        mp = _uv_scaled(mt, uv_scale)
        if bc:
            t = mt.image(bc, x=-700, y=300)
            mt.link(mp, "Vector", t, "Vector")
            mix = mt.node("ShaderNodeMix", -300, 300, data_type="RGBA")
            mix.inputs["Factor"].default_value = influence
            mix.inputs["A"].default_value = (1, 1, 1, 1)
            mt.link(t, "Color", mix, "B")
            mul = mt.node("ShaderNodeMix", 0, 300, data_type="RGBA", blend_type="MULTIPLY")
            mul.inputs["Factor"].default_value = 1.0
            mt.link(mix, "Result", mul, "A")
            mul.inputs["B"].default_value = tint
            mt.link(mul, "Result", bsdf, "Base Color")
        if orm:
            t = mt.image(orm, non_color=True, x=-700, y=0)
            mt.link(mp, "Vector", t, "Vector")
            sep = mt.node("ShaderNodeSeparateColor", -400, 0)
            mt.link(t, "Color", sep, "Color")
            mr = mt.node("ShaderNodeMapRange", -150, 0)
            mr.inputs["To Min"].default_value = rough[0]
            mr.inputs["To Max"].default_value = rough[1]
            mt.link(sep, "Green", mr, "Value")
            mt.link(mr, "Result", bsdf, "Roughness")
            if metal_from_map > 0:
                mm = mt.node("ShaderNodeMath", -150, -200, operation="MULTIPLY")
                mm.inputs[1].default_value = metal_from_map
                mt.link(sep, "Blue", mm, 0)
                ma = mt.node("ShaderNodeMath", 50, -200, operation="ADD")
                ma.inputs[1].default_value = metal
                mt.link(mm, 0, ma, 0)
                mt.link(ma, 0, bsdf, "Metallic")
        if nm and normal > 0:
            t = mt.image(nm, non_color=True, x=-700, y=-300)
            mt.link(mp, "Vector", t, "Vector")
            sep = mt.node("ShaderNodeSeparateColor", -450, -300)
            mt.link(t, "Color", sep, "Color")
            inv = mt.node("ShaderNodeMath", -300, -380, operation="SUBTRACT")
            inv.inputs[0].default_value = 1.0
            mt.link(sep, "Green", inv, 1)
            comb = mt.node("ShaderNodeCombineColor", -150, -300)
            mt.link(sep, "Red", comb, "Red")
            mt.link(inv, 0, comb, "Green")
            mt.link(sep, "Blue", comb, "Blue")
            nn = mt.node("ShaderNodeNormalMap", 100, -300)
            nn.inputs["Strength"].default_value = normal
            mt.link(comb, "Color", nn, "Color")
            mt.link(nn, "Normal", bsdf, "Normal")
    if emission:
        bsdf.inputs["Emission Color"].default_value = emission[0] + (1.0,)
        bsdf.inputs["Emission Strength"].default_value = emission[1]
    if alpha is not None:
        bsdf.inputs["Alpha"].default_value = alpha
        mt.m.surface_render_method = "BLENDED"
    return mt.m


def emissive(name: str, color, strength: float) -> bpy.types.Material:
    mt = Mat(name)
    em = mt.node("ShaderNodeEmission", 300, 0)
    em.inputs["Color"].default_value = tuple(color) + (1.0,)
    em.inputs["Strength"].default_value = strength
    mt.link(em, "Emission", mt.out, "Surface")
    return mt.m


def palette_lamp(name: str, strength: float) -> bpy.types.Material:
    mt = Mat(name)
    path = find([os.path.join(L.CACHE)], "T_BRG3_Lamps.png")
    em = mt.node("ShaderNodeEmission", 300, 0)
    em.inputs["Strength"].default_value = strength
    t = mt.image(path, interp="Closest", x=-300, y=0)
    t.image.alpha_mode = "CHANNEL_PACKED"          # the alpha is the alert weight: it must not darken the colour (weight 0 = black otherwise)
    mt.link(t, "Color", em, "Color")
    mt.link(em, "Emission", mt.out, "Surface")
    return mt.m


def screen_mat(name: str, page: str | None, strength: float = 2.6, hover: bool = False) -> bpy.types.Material:
    mt = Mat(name)
    page = "Helm_Touch" if page == "Touch" else page                     # the armrest pads show the touch page (MI_ASTRA_ScreenTouch)
    path = find(UI_DIRS, f"T_UI_{page}.png") if page else None
    if hover:
        # additive-looking hologram: emission over transparency; the back side (seen from behind) is much dimmer
        tr = mt.node("ShaderNodeBsdfTransparent", 200, 100)
        em = mt.node("ShaderNodeEmission", 200, -100)
        geo = mt.node("ShaderNodeNewGeometry", -100, 250)
        back = mt.node("ShaderNodeMath", 100, 250, operation="MULTIPLY_ADD")
        back.inputs[1].default_value = -0.82
        back.inputs[2].default_value = 1.0
        mt.link(geo, "Backfacing", back, 0)
        gain = mt.node("ShaderNodeMath", 300, 250, operation="MULTIPLY")
        gain.inputs[1].default_value = strength * 1.6
        mt.link(back, 0, gain, 0)
        mt.link(gain, 0, em, "Strength")
        add = mt.node("ShaderNodeAddShader", 450, 0)
        mt.link(tr, "BSDF", add, 0)
        mt.link(em, "Emission", add, 1)
        mt.link(add, "Shader", mt.out, "Surface")
        if path:
            t = mt.image(path, x=-300, y=-100)
            mt.link(t, "Color", em, "Color")
        else:
            em.inputs["Color"].default_value = (0.2, 0.5, 1.0, 1.0)
        mt.m.surface_render_method = "BLENDED"
        return mt.m
    bsdf = mt.node("ShaderNodeBsdfPrincipled", 500, 0)
    bsdf.inputs["Base Color"].default_value = (0.01, 0.012, 0.015, 1)
    bsdf.inputs["Roughness"].default_value = 0.35
    bsdf.inputs["Emission Strength"].default_value = strength
    if path:
        t = mt.image(path, x=-300, y=0)
        mt.link(t, "Color", bsdf, "Emission Color")
    else:
        bsdf.inputs["Emission Color"].default_value = (0.05, 0.2, 0.5, 1)
    mt.link(bsdf, "BSDF", mt.out, "Surface")
    return mt.m


def glass(name: str, tint=(0.02, 0.03, 0.035), alpha: float = 0.10) -> bpy.types.Material:
    mt = Mat(name)
    bsdf = mt.node("ShaderNodeBsdfPrincipled", 500, 0)
    bsdf.inputs["Base Color"].default_value = tint + (1.0,)
    bsdf.inputs["Roughness"].default_value = 0.04
    bsdf.inputs["Alpha"].default_value = alpha
    bsdf.inputs["Specular IOR Level"].default_value = 0.25
    mt.link(bsdf, "BSDF", mt.out, "Surface")
    mt.m.surface_render_method = "BLENDED"
    return mt.m


def label_mat(name: str, strength: float = 1.6) -> bpy.types.Material:
    mt = Mat(name)
    path = find([L.CACHE], "T_BRG3_Labels.png")
    bsdf = mt.node("ShaderNodeBsdfPrincipled", 500, 0)
    bsdf.inputs["Base Color"].default_value = (0.02, 0.02, 0.025, 1)
    bsdf.inputs["Roughness"].default_value = 0.35
    bsdf.inputs["Emission Strength"].default_value = strength
    t = mt.image(path, x=-300, y=0)
    mt.link(t, "Color", bsdf, "Emission Color")
    mt.link(t, "Color", bsdf, "Base Color")
    mt.link(bsdf, "BSDF", mt.out, "Surface")
    return mt.m


def decor_mat(name: str, strength: float = 1.8) -> bpy.types.Material:
    """The decor atlas (static display pages, soft glows): dark glass that emits the page (the instance is a M_ASTRA_Screen)."""
    mt = Mat(name)
    path = find([L.CACHE], "T_BRG3_Decor.png")
    bsdf = mt.node("ShaderNodeBsdfPrincipled", 500, 0)
    bsdf.inputs["Base Color"].default_value = (0.01, 0.012, 0.015, 1)
    bsdf.inputs["Roughness"].default_value = 0.30
    bsdf.inputs["Emission Strength"].default_value = strength
    t = mt.image(path, x=-300, y=0)
    mt.link(t, "Color", bsdf, "Emission Color")
    mt.link(bsdf, "BSDF", mt.out, "Surface")
    return mt.m


def make_materials(screen_pages: dict[str, dict]) -> None:
    """Configure every material of the scene by name (Unreal instance names / SCREEN_ slots)."""
    ivory = srgb_to_linear("#E6E1D6")
    gunmetal = srgb_to_linear("#4A4F55")
    pbr(L.STRUCT, [c * 1.05 for c in gunmetal], "Gunmetal", 1.0, (0.28, 0.62), 0.0, 1.0, 0.5, 0.8)
    pbr(L.TRIM, (0.62, 0.64, 0.67), "Brushed", 1.0, (0.22, 0.45), 0.0, 1.0, 0.6, 0.7)
    pbr(L.RUBBER, (0.045, 0.047, 0.05), "DeckRubber", 1.0, (0.55, 0.8), 0.0, 0.0, 0.5, 0.5)
    pbr(L.LEATHER, (0.05, 0.055, 0.075), "LeatherBlack", 2.0, (0.3, 0.5), 0.0, 0.0, 0.7, 0.9, coat=0.15, coat_rough=0.25)
    pbr(L.COMPOSITE, (0.05, 0.056, 0.07), "Carbon", 4.0, (0.22, 0.42), 0.0, 0.3, 0.35, 0.5, coat=0.5, coat_rough=0.12)
    pbr(L.IVORY, srgb_to_linear("#A9AAA8"), "PanelPaint", 1.0, (0.16, 0.3), 0.0, 0.0, 0.3, 0.4, coat=0.3, coat_rough=0.12)
    pbr(L.DECK, (0.30, 0.32, 0.36), "BRG3_DeckGrain", 2.5, (0.34, 0.62), 0.0, 0.9, 0.85, 1.0)
    pbr(L.DGLASS, (0.003, 0.004, 0.006), None, 1.0, (0.30, 0.38), 0.0, 0.0, 0.0, 0.0, coat=0.0, spec=0.28)
    palette_lamp(L.LAMP, 7.0)
    palette_lamp(L.LAMP_DIM, 2.4)
    palette_lamp(L.LAMP_HOT, 22.0)
    label_mat(L.LABEL, 1.4)
    decor_mat(L.DECOR, float(os.environ.get("BRG3_DECOR", "1.8")))
    pbr(L.BRASS, srgb_to_linear("#B89A4E"), "Brushed", 1.0, (0.24, 0.42), 1.0, 0.0, 0.15, 0.5)
    glass(L.GLASS)
    for slot, info in screen_pages.items():
        surf = info.get("surface")
        if slot in bpy.data.materials:
            if surf == "viewscreen":
                gl = glass(slot, (0.02, 0.05, 0.09), 0.06)
                gl.node_tree.nodes["Principled BSDF"].inputs["Emission Color"].default_value = (0.05, 0.16, 0.34, 1)
                gl.node_tree.nodes["Principled BSDF"].inputs["Emission Strength"].default_value = 0.3
            else:
                screen_mat(slot, info.get("page"), strength=2.6 if surf != "wall" else 2.2, hover=(surf == "hover"))
    # anything still empty gets a neutral grey so the scene never renders pink
    for m in bpy.data.materials:
        if not m.use_nodes or not m.node_tree.nodes:
            pbr(m.name, (0.3, 0.3, 0.3))


# ------------------------------------------------------------------------------------------------------------- scene
def clear_scene_lights_and_cameras() -> None:
    for o in list(bpy.context.scene.objects):
        if o.type in {"LIGHT", "CAMERA"}:
            bpy.data.objects.remove(o, do_unlink=True)


def sky_dome(yaw_deg: float = 0.0, strength: float = float(os.environ.get("BRG3_SKY", "0.16"))) -> None:
    """A sky sphere far outside the window with the Aurelia star map as emission (the world itself stays black)."""
    path = find(SKY_DIRS, "T_Sky_Aurelia_preview.png")
    bpy.ops.mesh.primitive_uv_sphere_add(radius=400.0, segments=64, ring_count=32, location=(0, 0, 0))
    o = bpy.context.active_object
    o.name = "PreviewSky"
    bpy.ops.object.shade_smooth()
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.flip_normals()
    bpy.ops.object.mode_set(mode="OBJECT")
    o.rotation_euler = (0, 0, math.radians(yaw_deg))
    mt = Mat("PreviewSkyMat")
    em = mt.node("ShaderNodeEmission", 300, 0)
    em.inputs["Strength"].default_value = strength
    if path:
        t = mt.image(path, x=-300, y=0)
        mt.link(t, "Color", em, "Color")
    mt.link(em, "Emission", mt.out, "Surface")
    o.data.materials.append(mt.m)
    o.visible_shadow = False
    o.visible_glossy = True
    o.visible_diffuse = True


def set_world(color=(0.0, 0.0, 0.0), strength: float = 1.0) -> None:
    w = bpy.data.worlds.new("PreviewWorld")
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = color + (1.0,)
    bg.inputs["Strength"].default_value = strength
    bpy.context.scene.world = w


def add_light(kind: str, name: str, loc_layout, energy: float, color=(1, 1, 1), size=(1.0, 1.0), rot_euler=None, target=None,
              spot_angle: float = 60.0, blend: float = 0.5, shadow: bool = True, shape: str = "RECTANGLE"):
    """Light from layout coordinates: kind AREA (rect, faces `target` or straight down), POINT, SPOT."""
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy
    ld.color = color
    if kind == "AREA":
        ld.shape = shape
        ld.size = size[0]
        if shape == "RECTANGLE":
            ld.size_y = size[1]
    if kind == "SPOT":
        ld.spot_size = math.radians(spot_angle)
        ld.spot_blend = blend
        ld.shadow_soft_size = 0.05
    if kind == "POINT":
        ld.shadow_soft_size = 0.08
    ld.use_shadow = shadow
    o = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(o)
    o.location = (loc_layout[0], -loc_layout[1], loc_layout[2])
    if target is not None:
        d = Vector((target[0] - loc_layout[0], -(target[1] - loc_layout[1]), target[2] - loc_layout[2]))
        o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    else:
        o.rotation_euler = (0, 0, 0) if rot_euler is None else rot_euler       # default: pointing straight down
    return o


def add_camera(name: str, eye_layout, yaw: float, pitch: float, fov_deg: float = 90.0, roll: float = 0.0):
    cd = bpy.data.cameras.new(name)
    cd.sensor_fit = "HORIZONTAL"
    cd.angle = math.radians(fov_deg)
    cd.clip_start = 0.05
    cd.clip_end = 2000
    o = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(o)
    ya, pa = math.radians(yaw), math.radians(pitch)
    d = Vector((math.cos(pa) * math.cos(ya), -math.cos(pa) * math.sin(ya), math.sin(pa)))     # layout yaw (+y) -> Blender -y
    o.location = (eye_layout[0], -eye_layout[1], eye_layout[2])
    o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    if roll:
        o.rotation_euler.rotate_axis("Z", math.radians(roll))
    return o


def configure_render(w: int = 1600, h: int = 900, samples: int = 48, raytrace: bool = True, exposure: float = 0.0) -> None:
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = 100
    ee = sc.eevee
    ee.taa_render_samples = samples
    ee.use_raytracing = raytrace
    if raytrace:
        ee.ray_tracing_method = "SCREEN"
        ee.ray_tracing_options.use_denoise = True
        ee.ray_tracing_options.resolution_scale = "1"
        ee.use_fast_gi = True
        ee.fast_gi_method = "GLOBAL_ILLUMINATION"
    ee.use_shadows = True
    ee.shadow_ray_count = 2
    ee.shadow_step_count = 6
    for name, val in (("view_transform", "AgX"), ("look", "AgX - Medium High Contrast")):
        try:
            setattr(sc.view_settings, name, val)
        except TypeError:
            pass
    sc.view_settings.exposure = exposure
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = 90


def render(camera, path: str) -> str:
    sc = bpy.context.scene
    sc.camera = camera
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


# ----------------------------------------------------------------------------------------------------------------- lights
GAIN = float(os.environ.get("BRG3_GAIN", "1.0"))


def json_lights(D: dict, lay, gain: float = 1.0) -> list:
    """The `lights` of the data file as Blender lights (the same list build_bridge_v3.py places in Unreal)."""
    made = []
    for ld in D.get("lights", []):
        col = tuple(v / 255.0 for v in ld["color"]) if "color" in ld else lay.kelvin_to_rgb(ld.get("temperature", 5600))
        lm = ld["lumens"]
        pos = ld["pos"]
        d = Vector((ld["dir"][0], -ld["dir"][1], ld["dir"][2])) if "dir" in ld else Vector((0, 0, -1))
        d.normalize()
        typ = ld["type"]
        if typ == "rect":
            bl = bpy.data.lights.new(ld["id"], "AREA")
            bl.shape = "RECTANGLE"
            bl.size, bl.size_y = ld["size"][0], ld["size"][1]
            bl.energy = lm * 0.030 * gain * (1.0 + 0.4 * math.log10(1 + ld["size"][0] * ld["size"][1]))
            if ld["size"][0] > 8:                      # long cove strips: the energy is per whole light
                bl.energy *= 1.0
        elif typ == "spot":
            bl = bpy.data.lights.new(ld["id"], "SPOT")
            bl.spot_size = math.radians(ld.get("outer", 50) * 2)
            bl.spot_blend = max(0.05, min(1.0, (ld.get("outer", 50) - ld.get("inner", 20)) / ld.get("outer", 50)))
            bl.shadow_soft_size = 0.12
            bl.energy = lm * 0.16 * gain
        else:
            bl = bpy.data.lights.new(ld["id"], "POINT")
            bl.shadow_soft_size = 0.1
            bl.energy = lm * 0.16 * gain
        bl.color = col
        if "specular" in ld:
            bl.specular_factor = float(ld["specular"])
        bl.use_shadow = bool(ld.get("shadows", False))
        o = bpy.data.objects.new(ld["id"], bl)
        bpy.context.scene.collection.objects.link(o)
        o.location = (pos[0], -pos[1], pos[2])
        z = -d
        along = ld.get("along")
        if along is not None:
            x = Vector((along[0], -along[1], along[2]))
            x = (x - z * x.dot(z))
            if x.length < 1e-6:
                x = Vector((1, 0, 0))
            x.normalize()
        else:
            x = z.cross(Vector((0, 0, 1)))
            if x.length < 1e-6:
                x = Vector((1, 0, 0))
            x.normalize()
        y = z.cross(x).normalized()
        rot = Matrix(((x.x, y.x, z.x), (x.y, y.y, z.y), (x.z, y.z, z.z)))
        o.rotation_euler = rot.to_euler()
        made.append(o)
    return made


# -------------------------------------------------------------------------------------------- preview-only placeholders
def _np():
    import numpy as np
    return np


def _vnoise3(p, seed: int = 0):
    """3D value noise in [0, 1] on an (..., 3) array of points (smoothstep-interpolated lattice hash)."""
    np = _np()
    rng = np.random.default_rng(seed)
    table = rng.random(256).astype(np.float32)
    perm = rng.permutation(256)
    i = np.floor(p).astype(np.int64)
    f = (p - i).astype(np.float32)
    f = f * f * (3 - 2 * f)

    def h(ix, iy, iz):
        return table[perm[(perm[(perm[ix & 255] + iy) & 255] + iz) & 255]]

    out = 0.0
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (f[..., 0] if dx else 1 - f[..., 0]) * (f[..., 1] if dy else 1 - f[..., 1]) * (f[..., 2] if dz else 1 - f[..., 2])
                out = out + w * h(i[..., 0] + dx, i[..., 1] + dy, i[..., 2] + dz)
    return out


def _fbm3(p, octaves: int = 6, seed: int = 0):
    v, amp, tot = 0.0, 0.5, 0.0
    for o in range(octaves):
        v = v + amp * _vnoise3(p * (2.0 ** o), seed + o * 17)
        tot += amp
        amp *= 0.5
    return v / tot


def _poly_mask(np, xx, yy, pts):
    """Even-odd point-in-polygon on the grids xx, yy for the polygon `pts` [(x, y), ...]."""
    inside = np.zeros(xx.shape, bool)
    n = len(pts)
    for k in range(n):
        x0, y0 = pts[k]
        x1, y1 = pts[(k + 1) % n]
        if y0 == y1:
            continue
        cond = ((y0 > yy) != (y1 > yy)) & (xx < (x1 - x0) * (yy - y0) / (y1 - y0) + x0)
        inside ^= cond
    return inside


def viewscreen_placeholder(on: bool = True) -> None:
    """Preview only: what the main viewscreen may show (a lit planet with clouds and an atmosphere, two hostile warships with
    contact brackets, a debris streak) so the ON state can be judged next to the OFF one (the game draws the real thing: a
    SceneCapture plus the tactical overlay)."""
    if "SCREEN_viewscreen_1" not in bpy.data.materials or not on:
        return
    np = _np()
    w, h = 1920, 800
    rng = np.random.default_rng(3)
    img = np.zeros((h, w, 3), np.float32)
    # starfield: many faint stars, a few bright ones with a tint
    st = rng.random((h, w))
    img += (st > 0.9975)[..., None] * (rng.random((h, w, 1)).astype(np.float32) ** 3 * 0.9 + 0.05)
    tint = np.array([1.0, 0.92, 0.85], np.float32)
    img += (st > 0.99985)[..., None] * tint * 1.2
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    # the planet: a big lit sphere at the lower left, sun from the upper right (noise only where the disc is)
    cx, cy, r = 0.20 * w, 0.78 * h, 0.72 * h
    dx, dy = (xx - cx) / r, (yy - cy) / r
    d2 = dx * dx + dy * dy
    inside = d2 < 1.0
    nz = np.sqrt(np.clip(1 - d2, 0, 1))
    n3 = np.stack([dx, dy, nz], axis=-1).astype(np.float32)
    sun = np.array([0.55, -0.45, 0.70], np.float32)
    sun /= np.linalg.norm(sun)
    ndl_full = np.clip((n3 * sun).sum(-1), 0, 1)
    P = n3[inside]
    ph = 0.4
    rot = np.array([[np.cos(ph), 0, np.sin(ph)], [0, 1, 0], [-np.sin(ph), 0, np.cos(ph)]], np.float32)
    q = P @ rot
    lat = np.abs(P[:, 1])
    height = _fbm3(q * 2.2 + 5.0, 6, 11)
    land = height > 0.52
    ocean = np.array([0.02, 0.07, 0.17], np.float32)
    shallow = np.array([0.03, 0.16, 0.24], np.float32)
    green = np.array([0.08, 0.17, 0.06], np.float32)
    dry = np.array([0.24, 0.19, 0.10], np.float32)
    moist = _fbm3(q * 3.1 + 40.0, 4, 31)
    landcol = (green * (1 - moist[:, None]) + dry * moist[:, None]) * (0.7 + 0.9 * (height[:, None] - 0.5))
    depth = np.clip((0.52 - height[:, None]) * 4, 0, 1)
    seacol = ocean * (1 - 0.6 * depth) + shallow * np.clip(1 - (0.52 - height[:, None]) * 12, 0, 1) * 0.5
    col = np.where(land[:, None], landcol, seacol)
    ice = np.clip((lat * 1.35 - 0.86) * 9, 0, 1)
    col = col * (1 - ice[:, None]) + np.array([0.7, 0.75, 0.8], np.float32) * ice[:, None]
    cl = _fbm3(q * 3.4 + 90.0, 6, 51)
    cloud = np.clip((cl - 0.52) * 3.2, 0, 1) * 0.85
    col = col * (1 - cloud[:, None]) + np.array([0.85, 0.88, 0.92], np.float32) * cloud[:, None]
    ndl = ndl_full[inside]
    lit = col * (0.02 + 1.9 * ndl[:, None] ** 0.9)
    hv = sun + np.array([0, 0, 1], np.float32)
    hv /= np.linalg.norm(hv)
    glint = np.exp(-(1 - np.clip((P * hv).sum(-1), 0, 1)) * 60) * (~land) * (1 - cloud)
    lit = lit + glint[:, None] * np.array([0.5, 0.55, 0.6], np.float32) * 0.8
    term = np.clip((P * sun).sum(-1) * 4 + 0.35, 0, 1)
    city = (_fbm3(q * 14 + 200, 3, 71) > 0.66) & land & (ndl < 0.05)
    lit = lit + city[:, None] * np.array([0.6, 0.4, 0.15], np.float32) * (1 - term[:, None]) * 0.5
    pl = np.zeros((h, w, 3), np.float32)
    pl[inside] = lit
    disc = np.clip((1.0 - np.sqrt(d2)) * r / 1.5, 0.0, 1.0)
    img = img * (1 - disc[..., None]) + pl * disc[..., None]
    rim = np.sqrt(d2)
    atm = np.exp(-((rim - 1.0) / 0.018) ** 2) * np.clip(ndl_full * 1.4 + 0.12, 0, 1)
    atm2 = np.exp(-np.clip(rim - 1.0, 0, 9) / 0.03) * (rim > 1.0) * np.clip(ndl_full * 1.3 + 0.1, 0, 1) * 0.5
    img += (atm + atm2)[..., None] * np.array([0.10, 0.32, 0.85], np.float32) * 1.3
    # two hostile warships: wedge hulls with superstructure and lit windows, orange engine glow; one far away
    def ship(sx, sy, L, sc, ang_deg):
        nonlocal img
        ca, sa = np.cos(np.radians(ang_deg)), np.sin(np.radians(ang_deg))
        u = ((xx - sx) * ca + (yy - sy) * sa) / (L * 0.5)
        v = (-(xx - sx) * sa + (yy - sy) * ca) / (L * 0.5)
        hull = [(-1.0, -0.13), (-0.55, -0.20), (0.45, -0.15), (1.0, -0.02), (1.0, 0.03), (0.45, 0.13), (-0.55, 0.19), (-1.0, 0.11)]
        tower = [(-0.60, -0.20), (-0.30, -0.34), (0.05, -0.31), (0.12, -0.16)]
        wing = [(-0.85, 0.11), (-0.55, 0.19), (-0.45, 0.34), (-0.80, 0.30)]
        m = _poly_mask(np, u, v, hull)
        mt = _poly_mask(np, u, v, tower)
        mw = _poly_mask(np, u, v, wing)
        body = m | mt | mw
        shade = np.clip(0.55 - v * 1.4, 0.15, 1.0)
        base = np.array([0.075, 0.07, 0.07], np.float32) * shade[..., None]
        base = base + (mt[..., None] * np.array([0.02, 0.02, 0.025], np.float32))
        panels = (np.sin(u * 60) * np.sin(v * 50) > 0.85)[..., None] * np.array([0.05, 0.05, 0.06], np.float32)
        win = ((np.sin(u * 90) > 0.93) & (np.abs(v - 0.02) < 0.03) & m)[..., None] * np.array([1.0, 0.75, 0.4], np.float32) * 0.9
        img = np.where(body[..., None], base + panels + win, img)
        gx = -1.0
        glow = np.exp(-(((u - gx) / (0.10 * sc)) ** 2 + ((v + 0.02) / 0.10) ** 2)) + 0.6 * np.exp(-(((u - gx + 0.12) / (0.25 * sc)) ** 2 + ((v + 0.02) / 0.05) ** 2))
        img = img + glow[..., None] * np.array([1.0, 0.42, 0.10], np.float32) * 1.4
        # contact brackets round the hull
        bx0, bx1, by0, by1 = sx - L * 0.56, sx + L * 0.56, sy - L * 0.20, sy + L * 0.20
        arm = L * 0.07
        for (px, py, ex, ey) in ((bx0, by0, 1, 1), (bx1, by0, -1, 1), (bx0, by1, 1, -1), (bx1, by1, -1, -1)):
            for t in range(int(arm)):
                for (ox, oy) in ((ex * t, 0), (0, ey * t)):
                    x0, y0 = int(px + ox), int(py + oy)
                    if 0 <= x0 < w - 2 and 0 <= y0 < h - 2:
                        img[y0:y0 + 2, x0:x0 + 2] = (1.0, 0.45, 0.2)
    ship(0.66 * w, 0.44 * h, 0.30 * w, 1.0, -4.0)
    ship(0.86 * w, 0.30 * h, 0.12 * w, 0.6, -8.0)
    image = bpy.data.images.new("preview_viewscreen", w, h, alpha=False, float_buffer=True)
    rgba = np.concatenate([np.clip(img[::-1], 0.0, 8.0), np.ones((h, w, 1), np.float32)], axis=2).astype(np.float32)
    image.pixels.foreach_set(rgba.ravel())
    m = bpy.data.materials["SCREEN_viewscreen_1"]
    m.use_nodes = True
    m.node_tree.nodes.clear()
    out = m.node_tree.nodes.new("ShaderNodeOutputMaterial")
    tex = m.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = image
    em = m.node_tree.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 1.1
    tr = m.node_tree.nodes.new("ShaderNodeBsdfTransparent")
    mix = m.node_tree.nodes.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = 0.94
    m.node_tree.links.new(tex.outputs["Color"], em.inputs["Color"])
    m.node_tree.links.new(tr.outputs["BSDF"], mix.inputs[1])
    m.node_tree.links.new(em.outputs["Emission"], mix.inputs[2])
    m.node_tree.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    m.surface_render_method = "BLENDED"


def holo_plot(D: dict) -> None:
    """Preview only: a placeholder tactical plot over the table (rings, bearing spokes, friendly and hostile icons) at the height
    AstraHoloTable draws it (24 cm above the top), to check that the volume above the table is clear and how it reads."""
    np = _np()
    ht = D["holo_table"]
    from mathutils import Vector
    top_z = D["levels"][ht.get("level", "well")] + ht["height"]
    pr = ht.get("plot_radius", 1.2)
    n = 1024
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float32)
    px, py = (xx / n * 2 - 1), (yy / n * 2 - 1)
    d = np.sqrt(px * px + py * py)
    a = np.arctan2(py, px)
    rings = np.exp(-((np.abs(((d * 4.0) % 1.0) - 0.5) - 0.5) / 0.012) ** 2)
    spokes = np.exp(-((np.abs(((a / (2 * np.pi) * 12.0) % 1.0) - 0.5) - 0.5) / 0.006) ** 2) * np.clip(d * 5 - 0.3, 0, 1)
    rim = np.exp(-((d - 0.985) / 0.012) ** 2)
    edge = np.clip((1.0 - d) / 0.03, 0, 1)
    val = (0.05 + 0.32 * rings + 0.16 * spokes + 0.9 * rim) * edge
    img = np.zeros((n, n, 4), np.float32)
    img[..., 0], img[..., 1], img[..., 2] = val * 0.25, val * 0.7, val * 1.0
    img[..., 3] = np.clip(val * 1.6, 0, 1)
    image = bpy.data.images.new("preview_plot", n, n, alpha=True, float_buffer=True)
    image.pixels.foreach_set(img[::-1].ravel())
    mat = bpy.data.materials.new("PreviewPlot")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = image
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Strength"].default_value = 6.0
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(tex.outputs["Color"], em.inputs["Color"])
    nt.links.new(tex.outputs["Alpha"], mix.inputs["Fac"])
    nt.links.new(tr.outputs["BSDF"], mix.inputs[1])
    nt.links.new(em.outputs["Emission"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    mat.surface_render_method = "BLENDED"
    bpy.ops.mesh.primitive_plane_add(size=2 * pr, location=(ht["pos"][0], -ht["pos"][1], top_z + 0.24))
    o = bpy.context.active_object
    o.name = "PreviewPlot"
    o.data.materials.append(mat)
    # icons: friendly (cyan), hostile (amber), a vector line
    def icon(x, y, z, cell, kind):
        ic = emissive("PreviewIcon_" + cell, (0.2, 0.7, 1.0) if cell == "f" else (1.0, 0.55, 0.12), 14.0)
        if kind == "ship":
            bpy.ops.mesh.primitive_cone_add(vertices=3, radius1=0.035, depth=0.11, location=(ht["pos"][0] + x, -(ht["pos"][1] + y), top_z + 0.24 + z),
                                            rotation=(0, math.radians(90), math.radians(-y * 20)))
        else:
            bpy.ops.mesh.primitive_ico_sphere_add(radius=0.022, subdivisions=1, location=(ht["pos"][0] + x, -(ht["pos"][1] + y), top_z + 0.24 + z))
        oo = bpy.context.active_object
        oo.data.materials.append(ic)
        st = bpy.data.objects.new("stem", None)
        return oo
    for (x, y, z, c, k) in ((-0.15, 0.0, 0.02, "f", "ship"), (-0.35, 0.28, 0.0, "f", "ship"), (-0.3, -0.32, 0.03, "f", "ship"),
                            (0.62, 0.15, 0.06, "h", "ship"), (0.78, -0.2, 0.0, "h", "ship"), (0.5, -0.45, 0.09, "h", "ship"),
                            (0.85, 0.3, -0.03, "h", "dot"), (0.1, 0.5, 0.0, "f", "dot")):
        icon(x, y, z, c, k)


# ------------------------------------------------------------------------------------------------------------------ studio
STUDIO_VIEWS = {
    "front": (3.4, 0.0, 1.25), "back": (-3.4, 0.0, 1.25), "side": (0.0, -3.4, 1.15), "q34": (2.5, -2.5, 1.7), "q34b": (-2.4, 2.4, 1.6),
    "top": (1.6, -1.3, 3.4), "low": (2.3, 1.6, 0.55),
}


def studio(objs: list, out_dir: str, views: list | None = None, fov: float = 34.0, target=(0.0, 0.0, 0.78)) -> None:
    """Preview only: every prop alone on a dark deck patch under a soft key, a cool rim and a warm fill (a quick way to judge a
    shape without the room). One JPG per object and view: studio_<mesh>_<view>.jpg."""
    views = views or ["front", "back", "side", "q34"]
    if os.environ.get("BRG3_TARGET"):
        target = tuple(float(v) for v in os.environ["BRG3_TARGET"].split(","))
    fov = float(os.environ.get("BRG3_FOV", fov))
    set_world((0.012, 0.013, 0.017), 1.0)
    configure_render(1200, 800, int(os.environ.get("BRG3_SAMPLES", "24")))
    bpy.ops.mesh.primitive_plane_add(size=14.0, location=(0, 0, 0))
    floor = bpy.context.active_object
    floor.name = "StudioFloor"
    floor.data.materials.append(pbr("StudioFloor", (0.05, 0.052, 0.058), None, 1.0, (0.30, 0.42), 0.0, 0.0, 0.0, 0.0, coat=0.0, spec=0.4))
    if os.environ.get("BRG3_DEBUG_MATS"):                       # flat identification colours per material
        colors = {L.STRUCT: (1, 0, 0), L.TRIM: (0, 1, 0), L.RUBBER: (0, 0, 1), L.LEATHER: (1, 1, 0), L.COMPOSITE: (1, 0, 1), L.IVORY: (1, 1, 1),
                  L.DECK: (0.4, 0.4, 0.4), L.DGLASS: (0, 1, 1), L.GLASS: (0.5, 0.2, 0.8)}
        for m in bpy.data.materials:
            col = colors.get(m.name, (1.0, 0.5, 0.0) if m.name.startswith("SCREEN_") else (0.3, 0.3, 0.3))
            emissive(m.name, col, 1.0)
    add_light("AREA", "Key", (2.4, 2.6, 3.4), 900.0, (1.0, 0.96, 0.9), size=(2.6, 2.6), target=target)
    add_light("AREA", "Rim", (-2.6, -2.2, 2.6), 700.0, (0.7, 0.85, 1.0), size=(1.2, 3.0), target=target)
    add_light("AREA", "Fill", (3.2, -2.8, 1.6), 160.0, (1.0, 0.9, 0.8), size=(3.0, 3.0), target=target)
    add_light("AREA", "Top", (0.0, 0.0, 4.2), 300.0, (1.0, 1.0, 1.0), size=(3.0, 3.0), target=target)
    tx, ty, tz = target
    for o in objs:
        for q in objs:
            q.hide_render = q is not o
        for v in views:
            ex, ey, ez = STUDIO_VIEWS[v]
            dx, dy, dz = tx - ex, ty - ey, tz - ez
            yaw = math.degrees(math.atan2(dy, dx))
            pitch = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
            cam = add_camera(f"cam_{v}", (ex, ey, ez), yaw, pitch, fov)
            render(cam, os.path.join(out_dir, f"studio_{o.name.replace('SM_BRG3_', '')}_{v}.jpg"))
            print("rendered", o.name, v)
