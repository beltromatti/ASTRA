"""ASTRA ships v3 — Eevee previews that mimic the Unreal materials (only for looking: nothing here is exported).

The hull slots are painted from the palette of docs/STILE.md with the per-vertex data of the mesh: UVMap_D1 = (wear, grime),
UVMap_D2 = (tone, aux). Lit windows and lights read UVMap_D2 too. The scene is Aurelia: an orange star, the Teal Veil nebula.
"""
from __future__ import annotations

import math
import os
import sys

import bpy
from mathutils import Matrix, Vector

MAIN = "/Users/beltromatti/Desktop/ASTRA"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SKY_DIRS = [os.path.join(ROOT, "art", "_cache", "sky"), os.path.join(MAIN, "art", "_cache", "sky")]


def srgb(h: str):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


# faction paints: (paint colour, bare metal, metallic of the paint, rough min, rough max, tone amount, grime darkening)
PAINTS = {
    "A": {"Plate": ("#C9C6BC", 0.0, 0.32, 0.55), "Frame": ("#4A4F55", 0.35, 0.28, 0.55), "Livery": ("#1F3A6B", 0.0, 0.3, 0.5),
          "Trim": ("#B89A4E", 0.55, 0.25, 0.4), "Marking": ("#EDEBE4", 0.0, 0.35, 0.55), "Engine": ("#5B5F66", 0.85, 0.3, 0.5),
          "Radiator": ("#2A2D31", 0.4, 0.3, 0.6), "Cut": ("#0F0D0C", 0.3, 0.6, 0.9)},
    "M": {"Plate": ("#6A645C", 0.3, 0.4, 0.75), "Frame": ("#26272B", 0.4, 0.3, 0.6), "Livery": ("#8C5A2B", 0.85, 0.3, 0.55),
          "Trim": ("#6E7F63", 0.6, 0.35, 0.65), "Marking": ("#B78A55", 0.0, 0.4, 0.7), "Engine": ("#3A3B40", 0.8, 0.35, 0.55),
          "Radiator": ("#2A1A10", 0.4, 0.3, 0.6), "Cut": ("#0F0D0C", 0.3, 0.6, 0.9)},
    "G": {"Plate": ("#A79C82", 0.0, 0.35, 0.75), "Frame": ("#44484C", 0.4, 0.3, 0.7), "Livery": ("#B85F1F", 0.0, 0.4, 0.7),
          "Trim": ("#C9B25A", 0.4, 0.3, 0.5), "Marking": ("#EDEBE4", 0.0, 0.35, 0.55), "Engine": ("#6A6C70", 0.85, 0.35, 0.55),
          "Radiator": ("#303236", 0.4, 0.35, 0.7), "Cut": ("#0F0D0C", 0.3, 0.6, 0.9)},
}
BARE = {"A": "#8A8F96", "M": "#54514D", "G": "#7B7F84"}
EMISSIVE = {"A": {"Glow": ("#8CC8FF", 60.0), "Lights": ("#FFE6BF", 26.0)},
            "M": {"Glow": ("#FF6B47", 60.0), "Lights": ("#FFAE40", 26.0)},
            "G": {"Glow": ("#E6E6FF", 40.0), "Lights": ("#FFF2D9", 20.0)}}


class NodeMat:
    def __init__(self, name: str):
        self.m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        self.m.use_nodes = True
        self.nt = self.m.node_tree
        self.nt.nodes.clear()
        self.out = self.nt.nodes.new("ShaderNodeOutputMaterial")
        self.out.location = (1400, 0)

    def n(self, kind: str, x=0, y=0, **kw):
        node = self.nt.nodes.new(kind)
        node.location = (x, y)
        for k, v in kw.items():
            setattr(node, k, v)
        return node

    def l(self, a, out, b, inp):
        self.nt.links.new(a.outputs[out], b.inputs[inp])


def _math(mt, op, a=None, b=None, x=0, y=0, clamp=False):
    node = mt.n("ShaderNodeMath", x, y, operation=op, use_clamp=clamp)
    for i, v in enumerate((a, b)):
        if v is None:
            continue
        if isinstance(v, (int, float)):
            node.inputs[i].default_value = v
        else:
            mt.l(v[0], v[1], node, i)
    return node


def hull_material(name: str, fac: str, part: str, wear_gain: float = 1.0, grime_dark: float = 0.55) -> bpy.types.Material:
    col, metal_amt, r0, r1 = PAINTS[fac][part]
    mt = NodeMat(name)
    bsdf = mt.n("ShaderNodeBsdfPrincipled", 1100, 0)
    mt.l(bsdf, "BSDF", mt.out, "Surface")
    uv1 = mt.n("ShaderNodeUVMap", -1500, 300, uv_map="UVMap_D1")
    uv2 = mt.n("ShaderNodeUVMap", -1500, 100, uv_map="UVMap_D2")
    s1 = mt.n("ShaderNodeSeparateXYZ", -1300, 300)
    s2 = mt.n("ShaderNodeSeparateXYZ", -1300, 100)
    mt.l(uv1, "UV", s1, "Vector")
    mt.l(uv2, "UV", s2, "Vector")
    wear, grime, tone, soot = (s1, "X"), (s1, "Y"), (s2, "X"), (s2, "Y")
    tc = mt.n("ShaderNodeTexCoord", -1500, -300)
    n1 = mt.n("ShaderNodeTexNoise", -1250, -250, noise_dimensions="3D")
    n1.inputs["Scale"].default_value = 0.9
    n1.inputs["Detail"].default_value = 6.0
    n2 = mt.n("ShaderNodeTexNoise", -1250, -450, noise_dimensions="3D")
    n2.inputs["Scale"].default_value = 7.0
    n2.inputs["Detail"].default_value = 3.0
    n3 = mt.n("ShaderNodeTexNoise", -1250, -650, noise_dimensions="3D")
    n3.inputs["Scale"].default_value = 0.05
    n3.inputs["Detail"].default_value = 2.0
    for nn in (n1, n2, n3):
        mt.l(tc, "Object", nn, "Vector")
    chip = _math(mt, "ADD", (n1, "Fac"), (n2, "Fac"), -1000, -300)
    chip = _math(mt, "MULTIPLY", (chip, 0), 0.5, -850, -300)
    # bare metal where the wear (0..1) plus the noise crosses a threshold
    w = _math(mt, "MULTIPLY", wear, 1.35 * wear_gain, -1000, 300)
    br = _math(mt, "SUBTRACT", (chip, 0), 0.5, -850, -420)
    br = _math(mt, "MULTIPLY", (br, 0), 0.9, -700, -420)
    w2 = _math(mt, "ADD", (w, 0), (br, 0), -600, 200)
    mr = mt.n("ShaderNodeMapRange", -450, 200, clamp=True)
    mr.inputs["From Min"].default_value = 0.52
    mr.inputs["From Max"].default_value = 0.62
    mt.l(w2, 0, mr, "Value")
    bare = (mr, "Result")
    # paint: tint x tone x macro variation x grime x soot
    tint = mt.n("ShaderNodeRGB", -900, 700)
    tint.outputs[0].default_value = (*srgb(col), 1.0)
    metal = mt.n("ShaderNodeRGB", -900, 560)
    metal.outputs[0].default_value = (*srgb(BARE[fac]), 1.0)
    tf = _math(mt, "SUBTRACT", tone, 0.5, -1000, 100)
    tf = _math(mt, "MULTIPLY", (tf, 0), 1.25, -850, 100)
    tf = _math(mt, "ADD", (tf, 0), 1.0, -700, 100)
    mac = _math(mt, "SUBTRACT", (n3, "Fac"), 0.5, -1000, -800)
    mac = _math(mt, "MULTIPLY", (mac, 0), 0.5, -850, -800)
    mac = _math(mt, "ADD", (mac, 0), 1.0, -700, -800)
    gm = _math(mt, "MULTIPLY", grime, grime_dark, -850, 0)
    gm = _math(mt, "SUBTRACT", 1.0, (gm, 0), -700, 0)
    sm = _math(mt, "MULTIPLY", soot, 0.6, -850, -60)
    sm = _math(mt, "SUBTRACT", 1.0, (sm, 0), -700, -60)
    paint = mt.n("ShaderNodeMix", -300, 500, data_type="RGBA", blend_type="MULTIPLY")
    paint.inputs["Factor"].default_value = 1.0
    mt.l(tint, "Color", paint, "A")
    fac_v = _math(mt, "MULTIPLY", (tf, 0), (gm, 0), -500, 100)
    fac_v = _math(mt, "MULTIPLY", (fac_v, 0), (sm, 0), -400, 100)
    fac_v = _math(mt, "MULTIPLY", (fac_v, 0), (mac, 0), -300, 100)
    gray = mt.n("ShaderNodeCombineColor", -200, 300)
    for ch in ("Red", "Green", "Blue"):
        mt.l(fac_v, 0, gray, ch)
    mt.l(gray, "Color", paint, "B")
    fin = mt.n("ShaderNodeMix", 0, 400, data_type="RGBA")
    mt.l(bare[0], bare[1], fin, "Factor")
    mt.l(paint, "Result", fin, "A")
    mt.l(metal, "Color", fin, "B")
    mt.l(fin, "Result", bsdf, "Base Color")
    # roughness
    rr = _math(mt, "MULTIPLY", (chip, 0), 2.0, -600, -100)
    rgh = mt.n("ShaderNodeMapRange", -400, -100)
    rgh.inputs["To Min"].default_value = r0
    rgh.inputs["To Max"].default_value = r1
    mt.l(rr, 0, rgh, "Value")
    gr25 = _math(mt, "MULTIPLY", grime, 0.25, -400, -220)
    rg2 = _math(mt, "ADD", (rgh, "Result"), (gr25, 0), -200, -100)
    rg3 = mt.n("ShaderNodeMix", 0, -100, data_type="FLOAT")
    mt.l(bare[0], bare[1], rg3, "Factor")
    mt.l(rg2, 0, rg3, "A")
    rg3.inputs["B"].default_value = 0.5
    mt.l(rg3, "Result", bsdf, "Roughness")
    # metallic: the bare metal, plus the paint's own metal (copper leaf, gold)
    bm_ = _math(mt, "MULTIPLY", (bare[0], bare[1]), 0.7, -350, -300)
    mm = _math(mt, "MAXIMUM", (bm_, 0), metal_amt, -200, -300)
    mt.l(mm, 0, bsdf, "Metallic")
    bsdf.inputs["Specular IOR Level"].default_value = 0.5
    # fine bump so flat plates catch a little light
    bp = mt.n("ShaderNodeBump", 800, -300)
    bp.inputs["Strength"].default_value = 0.18
    bp.inputs["Distance"].default_value = 0.02
    mt.l(n2, "Fac", bp, "Height")
    mt.l(bp, "Normal", bsdf, "Normal")
    return mt.m


def light_material(name: str, fac: str, strength: float, kind: str = "Lights") -> bpy.types.Material:
    """Windows and light strips: each window (UVMap_D2.y = its id) is lit or dark; lit ones flicker per id."""
    col, base = EMISSIVE[fac][kind]
    mt = NodeMat(name)
    uv2 = mt.n("ShaderNodeUVMap", -900, 0, uv_map="UVMap_D2")
    s2 = mt.n("ShaderNodeSeparateXYZ", -700, 0)
    mt.l(uv2, "UV", s2, "Vector")
    on = mt.n("ShaderNodeMath", -500, 0, operation="LESS_THAN")
    mt.l(s2, "Y", on, 0)
    on.inputs[1].default_value = 0.62
    em = mt.n("ShaderNodeEmission", -100, 100)
    em.inputs["Color"].default_value = (*srgb(col), 1.0)
    mul = mt.n("ShaderNodeMath", -300, 0, operation="MULTIPLY")
    mt.l(on, 0, mul, 0)
    mul.inputs[1].default_value = strength if strength else base
    mt.l(mul, 0, em, "Strength")
    dark = mt.n("ShaderNodeBsdfPrincipled", -100, -200)
    dark.inputs["Base Color"].default_value = (0.006, 0.01, 0.016, 1.0)
    dark.inputs["Roughness"].default_value = 0.12
    dark.inputs["Specular IOR Level"].default_value = 0.8
    mix = mt.n("ShaderNodeMixShader", 300, 0)
    mt.l(on, 0, mix, "Fac")
    mt.l(dark, "BSDF", mix, 1)
    mt.l(em, "Emission", mix, 2)
    mt.l(mix, "Shader", mt.out, "Surface")
    return mt.m


def glow_material(name: str, fac: str, strength: float = 60.0) -> bpy.types.Material:
    col, _ = EMISSIVE[fac]["Glow"]
    mt = NodeMat(name)
    em = mt.n("ShaderNodeEmission", 0, 0)
    em.inputs["Color"].default_value = (*srgb(col), 1.0)
    em.inputs["Strength"].default_value = strength
    mt.l(em, "Emission", mt.out, "Surface")
    return mt.m


def nav_material(name: str, strength: float = 120.0) -> bpy.types.Material:
    """Running lights: UVMap_D1.x is the colour code (0 red, 0.5 green, 1 white)."""
    mt = NodeMat(name)
    uv1 = mt.n("ShaderNodeUVMap", -700, 0, uv_map="UVMap_D1")
    s1 = mt.n("ShaderNodeSeparateXYZ", -500, 0)
    mt.l(uv1, "UV", s1, "Vector")
    ramp = mt.n("ShaderNodeValToRGB", -300, 0)
    ramp.color_ramp.interpolation = "CONSTANT"
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (1.0, 0.04, 0.02, 1.0)
    e1 = ramp.color_ramp.elements.new(0.3)
    e1.color = (0.05, 1.0, 0.15, 1.0)
    e2 = ramp.color_ramp.elements.new(0.75)
    e2.color = (1.0, 0.95, 0.9, 1.0)
    mt.l(s1, "X", ramp, "Fac")
    em = mt.n("ShaderNodeEmission", 0, 0)
    mt.l(ramp, "Color", em, "Color")
    em.inputs["Strength"].default_value = strength
    mt.l(em, "Emission", mt.out, "Surface")
    return mt.m


def make_materials(fac: str, prefix: str | None = None) -> dict:
    """Preview materials for one faction's slots (names MI_HULL_<fac>_<Part>) — existing ones are rebuilt in place."""
    pre = f"MI_HULL_{fac}_"
    out = {}
    for part in PAINTS[fac]:
        out[part] = hull_material(pre + part, fac, part, wear_gain=1.0 if part != "Cut" else 0.3)
    out["Lights"] = light_material(pre + "Lights", fac, EMISSIVE[fac]["Lights"][1])
    out["Glow"] = glow_material(pre + "Glow", fac, EMISSIVE[fac]["Glow"][1])
    out["Nav"] = nav_material(pre + "Nav")
    out["Decal"] = hull_material(pre + "Decal", fac, "Marking")
    return out


# ------------------------------------------------------------------------------------------------------------- scene
def find(dirs, name):
    for d in dirs:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


def set_world(strength: float = 0.5, yaw_deg: float = 0.0) -> None:
    """The Teal Veil nebula as the world (the Aurelia sky map), so metal and glass reflect something."""
    w = bpy.data.worlds.new("Aurelia")
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = strength
    path = find(SKY_DIRS, "T_Sky_Aurelia_preview.png")
    if path:
        tex = nt.nodes.new("ShaderNodeTexEnvironment")
        tex.image = bpy.data.images.load(path, check_existing=True)
        mp = nt.nodes.new("ShaderNodeMapping")
        mp.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(yaw_deg))
        tc = nt.nodes.new("ShaderNodeTexCoord")
        nt.links.new(tc.outputs["Generated"], mp.inputs["Vector"])
        nt.links.new(mp.outputs["Vector"], tex.inputs["Vector"])
        nt.links.new(tex.outputs["Color"], bg.inputs["Color"])
    else:
        bg.inputs["Color"].default_value = (0.02, 0.06, 0.07, 1.0)
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])
    bpy.context.scene.world = w


def add_light(kind: str, name: str, color, energy: float, rot_deg=(0, 0, 0), loc=(0, 0, 0), size: float = 0.05, **kw):
    ld = bpy.data.lights.new(name, kind)
    ld.color = color
    ld.energy = energy
    if kind == "SUN":
        ld.angle = math.radians(size)
    elif kind == "AREA":
        ld.size = size
        ld.size_y = kw.get("size_y", size)
    o = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = tuple(math.radians(a) for a in rot_deg)
    return o


def aurelia_lighting(sun_az: float = 35.0, sun_el: float = 28.0, sun: float = 4.2, fill: float = 0.35, world: float = 0.55) -> None:
    """The orange star as a sun (azimuth/elevation of where it sits in the sky), a teal fill from the other side, the nebula."""
    set_world(world)
    az, el = math.radians(sun_az), math.radians(sun_el)
    d = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el)))            # towards the sun
    rot = (-d).to_track_quat("-Z", "Y").to_euler()
    o = add_light("SUN", "Aurelia", (1.0, 0.62, 0.32), sun, size=0.53)
    o.rotation_euler = rot
    d2 = Vector((-d.x, -d.y, 0.35)).normalized()
    o2 = add_light("SUN", "TealVeil", (0.25, 0.75, 0.8), fill, size=8.0)
    o2.rotation_euler = (-d2).to_track_quat("-Z", "Y").to_euler()


def camera(name: str, loc, target, lens: float = 50.0, clip_end: float = 60000.0, roll: float = 0.0):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.sensor_width = 36.0
    cd.clip_start = 0.5
    cd.clip_end = clip_end
    o = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(o)
    o.location = loc
    d = Vector(target) - Vector(loc)
    o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    if roll:
        o.rotation_euler.rotate_axis("Z", math.radians(roll))
    return o


def configure(w: int = 1600, h: int = 900, samples: int = 24, exposure: float = 0.0, engine: str = "BLENDER_EEVEE") -> None:
    sc = bpy.context.scene
    sc.render.engine = engine
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.resolution_percentage = 100
    ee = sc.eevee
    ee.taa_render_samples = samples
    ee.use_raytracing = True
    try:
        ee.ray_tracing_method = "SCREEN"
        ee.ray_tracing_options.use_denoise = True
        ee.use_fast_gi = True
    except Exception:
        pass
    ee.use_shadows = True
    for name, val in (("view_transform", "AgX"), ("look", "AgX - Medium High Contrast")):
        try:
            setattr(sc.view_settings, name, val)
        except TypeError:
            pass
    sc.view_settings.exposure = exposure
    sc.render.image_settings.file_format = "JPEG"
    sc.render.image_settings.quality = 88


def render(cam, path: str) -> str:
    sc = bpy.context.scene
    sc.camera = cam
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


def close_up_lens(distance: float, span: float, sensor: float = 36.0) -> float:
    """Focal length that makes a patch `span` metres wide fill the frame at `distance` (the '×300 zoom' framing)."""
    return sensor * distance / span
