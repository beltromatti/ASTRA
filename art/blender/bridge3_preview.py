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
    mt.link(t, "Color", em, "Color")
    mt.link(em, "Emission", mt.out, "Surface")
    return mt.m


def screen_mat(name: str, page: str | None, strength: float = 2.6, hover: bool = False) -> bpy.types.Material:
    mt = Mat(name)
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
    pbr(L.DGLASS, (0.003, 0.004, 0.006), None, 1.0, (0.10, 0.16), 0.0, 0.0, 0.0, 0.0, coat=0.0, spec=0.35)
    palette_lamp(L.LAMP, 7.0)
    palette_lamp(L.LAMP_DIM, 2.4)
    palette_lamp(L.LAMP_HOT, 22.0)
    label_mat(L.LABEL, 1.4)
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


def viewscreen_placeholder(on: bool = True) -> None:
    """Preview only: what the main viewscreen may show (a planet, two hostile ships, contact brackets) so the ON state can be judged
    next to the OFF one (the game draws the real thing: a SceneCapture plus the tactical overlay)."""
    if "SCREEN_viewscreen_1" not in bpy.data.materials or not on:
        return
    np = _np()
    w, h = 1920, 800
    rng = np.random.default_rng(3)
    img = np.zeros((h, w, 3), np.float32)
    img += 0.004
    stars = rng.random((h, w)) > 0.9985
    img += stars[..., None] * rng.random((h, w, 1)).astype(np.float32) * 0.9
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    # the planet: lit from the upper right, a thin atmosphere
    cx, cy, r = 0.24 * w, 0.32 * h, 0.52 * h
    d = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    disc = np.clip((r - d) / 2.0, 0.0, 1.0)
    nx, ny = (xx - cx) / r, (yy - cy) / r
    nz = np.sqrt(np.clip(1 - nx * nx - ny * ny, 0, 1))
    light = np.clip(nx * 0.55 + ny * 0.35 + nz * 0.6, 0, 1)
    ocean = np.array([0.03, 0.10, 0.22], np.float32)
    land = np.array([0.12, 0.16, 0.08], np.float32)
    n = np.sin(xx * 0.013) * np.sin(yy * 0.021 + xx * 0.004) + 0.5 * np.sin(xx * 0.05 + yy * 0.03)
    col = np.where((n > 0.25)[..., None], land, ocean) * (0.15 + 1.6 * light[..., None])
    img = img * (1 - disc[..., None]) + col * disc[..., None]
    atm = np.exp(-((d - r) / (0.025 * r)) ** 2) * np.clip(light * 1.3 + 0.1, 0, 1)
    img += atm[..., None] * np.array([0.12, 0.35, 0.8], np.float32) * 1.4
    # two hostile ships: dark hulls with an orange engine glow, and a distant one
    for (sx, sy, sa, sb, sc) in ((0.68, 0.46, 0.15, 0.028, 1.0), (0.83, 0.30, 0.07, 0.014, 0.6)):
        ex, ey = sx * w, sy * h
        a, b = sa * w, sb * h
        m = np.clip(1.0 - (((xx - ex) / a) ** 2 + ((yy - ey) / b) ** 2), 0, 1)
        m = np.clip(m * 6.0, 0, 1)
        hull = np.array([0.05, 0.045, 0.045], np.float32) + 0.25 * np.clip(-(yy - ey) / b, 0, 1)[..., None] * np.array([0.3, 0.22, 0.15], np.float32)
        img = img * (1 - m[..., None]) + hull * m[..., None]
        glow = np.exp(-(((xx - (ex + a * 0.95)) / (0.03 * w * sc)) ** 2 + ((yy - ey) / (0.012 * h)) ** 2))
        img += glow[..., None] * np.array([1.0, 0.45, 0.12], np.float32) * 1.6
        # contact brackets
        pad = 0.035 * w * sc
        for (bx, by) in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            px0, py0 = ex + bx * (a + pad), ey + by * (b + pad * 0.5)
            for k in range(3):
                for t in range(int(0.028 * w * sc)):
                    for (ox, oy) in ((-bx * t, 0), (0, -by * t)):
                        x0, y0 = int(px0 + ox), int(py0 + oy)
                        if 0 <= x0 < w and 0 <= y0 < h:
                            img[max(0, y0 - k):y0 + 1, x0] = (1.0, 0.45, 0.2)
    image = bpy.data.images.new("preview_viewscreen", w, h, alpha=False, float_buffer=True)
    rgba = np.concatenate([img[::-1], np.ones((h, w, 1), np.float32)], axis=2)
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
