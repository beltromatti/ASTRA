"""ASTRA ships v3 — Eevee previews that mimic the Unreal materials (only for looking: nothing here is exported).

The hull slots follow M_ASTRA_HullV3 (tools/ue_scripts/make_ship_materials_v3.py) with the same palette (ship3_palette.py), the same
wear texture (T_ShipWear_M, made by tools/art/ship3_textures.py) and the per-vertex data of the mesh: UVMap_D1 = (wear, grime),
UVMap_D2 = (tone, aux). Lit windows and lights read UVMap_D2 too. The scene is Aurelia: an orange star, the Teal Veil nebula, a
procedural sky (crisp at any zoom).
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import bpy
from mathutils import Vector

MAIN = "/Users/beltromatti/Desktop/ASTRA"
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import ship3_palette as PAL  # noqa: E402

TEX_DIRS = [os.path.join(ROOT, "art", "_cache", "textures"), os.path.join(MAIN, "art", "_cache", "textures")]


def srgb(h: str):
    return tuple(PAL.srgb_to_linear(h))


def find(dirs, name):
    for d in dirs:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


# ------------------------------------------------------------------------------------------------------------- node helpers
class NodeMat:
    def __init__(self, name: str):
        self.m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        self.m.use_nodes = True
        self.nt = self.m.node_tree
        self.nt.nodes.clear()
        self.out = self.nt.nodes.new("ShaderNodeOutputMaterial")
        self.out.location = (1800, 0)
        self._x = -1800

    def n(self, kind: str, x=0, y=0, **kw):
        node = self.nt.nodes.new(kind)
        node.location = (x, y)
        for k, v in kw.items():
            setattr(node, k, v)
        return node

    def l(self, a, out, b, inp):
        self.nt.links.new(a.outputs[out], b.inputs[inp])

    def math(self, op, a=None, b=None, clamp=False, x=0, y=0):
        """A Math node; a and b are constants or (node, output) pairs. Returns (node, 0)."""
        node = self.n("ShaderNodeMath", x, y, operation=op, use_clamp=clamp)
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                node.inputs[i].default_value = v
            else:
                self.l(v[0], v[1], node, i)
        return (node, 0)

    def mul(self, a, b, **kw):
        return self.math("MULTIPLY", a, b, **kw)

    def add(self, a, b, **kw):
        return self.math("ADD", a, b, **kw)

    def sub(self, a, b, **kw):
        return self.math("SUBTRACT", a, b, **kw)

    def sat(self, a):
        return self.math("ADD", a, 0.0, clamp=True)

    def smooth(self, v, lo, hi, out_lo=0.0, out_hi=1.0):
        node = self.n("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP", clamp=True)
        node.inputs["From Min"].default_value = lo
        node.inputs["From Max"].default_value = hi
        node.inputs["To Min"].default_value = out_lo
        node.inputs["To Max"].default_value = out_hi
        self.l(v[0], v[1], node, "Value")
        return (node, "Result")

    def lerp_f(self, a, b, t):
        node = self.n("ShaderNodeMix", data_type="FLOAT")
        for idx, v in ((2, a), (3, b)):
            if isinstance(v, (int, float)):
                node.inputs[idx].default_value = v
            else:
                self.l(v[0], v[1], node, idx)
        if isinstance(t, (int, float)):
            node.inputs[0].default_value = t
        else:
            self.l(t[0], t[1], node, 0)
        return (node, "Result")

    def lerp_c(self, a, b, t):
        """Colour mix; a and b are (node, output) pairs or RGBA tuples."""
        node = self.n("ShaderNodeMix", data_type="RGBA")
        for idx, v in ((6, a), (7, b)):
            if isinstance(v, tuple) and len(v) in (3, 4) and not hasattr(v[0], "outputs"):
                node.inputs[idx].default_value = (*v[:3], 1.0)
            else:
                self.l(v[0], v[1], node, idx)
        if isinstance(t, (int, float)):
            node.inputs[0].default_value = t
        else:
            self.l(t[0], t[1], node, 0)
        return (node, "Result")

    def scale_c(self, c, k):
        """Colour times a scalar (node output) as RGBA multiply."""
        node = self.n("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
        node.inputs[0].default_value = 1.0
        if isinstance(c, tuple) and len(c) in (3, 4) and not hasattr(c[0], "outputs"):
            node.inputs[6].default_value = (*c[:3], 1.0)
        else:
            self.l(c[0], c[1], node, 6)
        gray = self.n("ShaderNodeCombineColor")
        for ch in ("Red", "Green", "Blue"):
            self.l(k[0], k[1], gray, ch)
        self.l(gray, "Color", node, 7)
        return (node, "Result")


_IMAGES: dict = {}


def load_image(name: str, non_color: bool = True):
    if name in _IMAGES:
        return _IMAGES[name]
    p = find(TEX_DIRS, name)
    img = None
    if p:
        img = bpy.data.images.load(p, check_existing=True)
        if non_color:
            img.colorspace_settings.name = "Non-Color"
        img.alpha_mode = "CHANNEL_PACKED"
    _IMAGES[name] = img
    return img


def wear_channels(mt: NodeMat, scale: float = 0.5 / 8.0, y0: float = -400.0):
    """The wear texture (R chips, G scratches, B grime, A streaks) box-projected in object space, as the game does with the metric
    UVs (one tile per 16 m). Without the file, noise stands in for the four channels."""
    tc = mt.n("ShaderNodeTexCoord", -1900, y0)
    img = load_image("T_ShipWear_M.png")
    if img is not None:
        mp = mt.n("ShaderNodeMapping", -1700, y0)
        mp.inputs["Scale"].default_value = (scale, scale, scale)
        mt.l(tc, "Object", mp, "Vector")
        tx = mt.n("ShaderNodeTexImage", -1500, y0, image=img, projection="BOX", interpolation="Linear")
        tx.projection_blend = 0.3
        mt.l(mp, "Vector", tx, "Vector")
        sep = mt.n("ShaderNodeSeparateColor", -1250, y0)
        mt.l(tx, "Color", sep, "Color")
        return (sep, "Red"), (sep, "Green"), (sep, "Blue"), (tx, "Alpha"), tc
    outs = []
    for i, (sc, det) in enumerate(((9.0, 5.0), (30.0, 2.0), (1.2, 5.0), (6.0, 1.0))):
        nn = mt.n("ShaderNodeTexNoise", -1500, y0 - 200 * i, noise_dimensions="3D")
        nn.inputs["Scale"].default_value = sc
        nn.inputs["Detail"].default_value = det
        mt.l(tc, "Object", nn, "Vector")
        outs.append((nn, "Fac"))
    return outs[0], outs[1], outs[2], outs[3], tc


# ------------------------------------------------------------------------------------------------------------- the materials
def hull_material(name: str, fac: str, part: str, tone_amount: float | None = None, grime_gain: float | None = None) -> bpy.types.Material:
    """M_ASTRA_HullV3 for one slot: paint over bare metal, chipped where the geometry says (UVMap_D1.x), broken up by the wear
    texture; tone per plate (UVMap_D2.x), grime in recesses (UVMap_D1.y), soot streaks (UVMap_D2.y)."""
    tint_hex, bare_hex, metal_amt, r0, r1 = PAL.PAINT[fac][part]
    tone_amount = (0.20 if fac != "M" else 0.26) if tone_amount is None else tone_amount
    grime_gain = (1.0 if fac != "M" else 1.3) if grime_gain is None else grime_gain
    mt = NodeMat(name)
    bsdf = mt.n("ShaderNodeBsdfPrincipled", 1500, 0)
    mt.l(bsdf, "BSDF", mt.out, "Surface")
    uv1 = mt.n("ShaderNodeUVMap", -1900, 300, uv_map="UVMap_D1")
    uv2 = mt.n("ShaderNodeUVMap", -1900, 150, uv_map="UVMap_D2")
    s1 = mt.n("ShaderNodeSeparateXYZ", -1700, 300)
    s2 = mt.n("ShaderNodeSeparateXYZ", -1700, 150)
    mt.l(uv1, "UV", s1, "Vector")
    mt.l(uv2, "UV", s2, "Vector")
    wear, grime, tone, soot = (s1, "X"), (s1, "Y"), (s2, "X"), (s2, "Y")
    wr, wg, wb, wa, tc = wear_channels(mt)
    # macro variation (UE: T_ASTRA_MacroNoise, blotches of ~13 m)
    mn = mt.n("ShaderNodeTexNoise", -1250, -900, noise_dimensions="3D")
    mn.inputs["Scale"].default_value = 0.09
    mn.inputs["Detail"].default_value = 3.0
    mn2 = mt.n("ShaderNodeTexNoise", -1250, -1100, noise_dimensions="3D")
    mn2.inputs["Scale"].default_value = 1.7
    mn2.inputs["Detail"].default_value = 4.0
    mt.l(tc, "Object", mn, "Vector")
    mt.l(tc, "Object", mn2, "Vector")
    macro, micro = (mn, "Fac"), (mn2, "Fac")
    # paint colour
    tone_f = mt.add(mt.mul(mt.sub(tone, 0.5), 2.0 * tone_amount), 1.0)
    macro_f = mt.add(mt.mul(mt.sub(macro, 0.5), 0.2), 1.0)
    g = mt.sat(mt.mul(mt.mul(grime, grime_gain), mt.add(mt.mul(wb, 0.8), 0.6)))
    grime_f = mt.sub(1.0, mt.mul(g, 0.55))
    soot_f = mt.sub(1.0, mt.mul(mt.mul(soot, 0.6), mt.add(mt.mul(wa, 0.5), 0.5)))
    k = mt.mul(mt.mul(tone_f, macro_f), mt.mul(grime_f, soot_f))
    paint = mt.scale_c(srgb(tint_hex), k)
    # chips and scratches
    chip = mt.sat(mt.mul(mt.sub(mt.add(mt.mul(wear, 1.0), mt.mul(mt.sub(wr, 0.5), 0.9)), 0.52), 10.0))
    scr = mt.mul(mt.smooth(wg, 0.86, 0.97), 0.35)
    isbare = mt.sat(mt.math("MAXIMUM", chip, scr))
    metal_c = mt.scale_c(srgb(bare_hex), mt.add(mt.mul(wg, 0.4), 0.8))
    col = mt.lerp_c(paint, metal_c, isbare)
    mt.l(col[0], col[1], bsdf, "Base Color")
    # roughness and metal
    base_r = mt.lerp_f(r0, r1, 0.363)
    rp = mt.add(mt.add(base_r, mt.mul(g, 0.25)), mt.mul(mt.sub(micro, 0.5), 0.18))
    rough = mt.lerp_f(rp, 0.42, isbare)
    mt.l(rough[0], rough[1], bsdf, "Roughness")
    metal = mt.add(mt.mul(isbare, 0.75), metal_amt * 1.0)
    metal = mt.sat(metal)
    mt.l(metal[0], metal[1], bsdf, "Metallic")
    bsdf.inputs["Specular IOR Level"].default_value = 0.5
    # fine bump so flat plates catch a little light
    bp = mt.n("ShaderNodeBump", 1300, -300)
    bp.inputs["Strength"].default_value = 0.10
    bp.inputs["Distance"].default_value = 0.02
    mt.l(mn2, "Fac", bp, "Height")
    mt.l(bp, "Normal", bsdf, "Normal")
    return mt.m


def light_material(name: str, fac: str, strength: float = 2.6, lit_fraction: float | None = None) -> bpy.types.Material:
    """Windows and light strips: each pane (UVMap_D2.y = its id) is lit or dark, as M_ASTRA_ShipLight Mode 0."""
    col, _, _, _, lit = PAL.LIGHTS[fac]
    lit = lit if lit_fraction is None else lit_fraction
    mt = NodeMat(name)
    uv2 = mt.n("ShaderNodeUVMap", -900, 0, uv_map="UVMap_D2")
    s2 = mt.n("ShaderNodeSeparateXYZ", -700, 0)
    mt.l(uv2, "UV", s2, "Vector")
    on = mt.n("ShaderNodeMath", -500, 0, operation="LESS_THAN")
    mt.l(s2, "Y", on, 0)
    on.inputs[1].default_value = lit
    em = mt.n("ShaderNodeEmission", -100, 100)
    em.inputs["Color"].default_value = (*col, 1.0)
    em.inputs["Strength"].default_value = strength
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
    col = PAL.LIGHTS[fac][2]
    mt = NodeMat(name)
    em = mt.n("ShaderNodeEmission", 0, 0)
    em.inputs["Color"].default_value = (*col, 1.0)
    em.inputs["Strength"].default_value = strength
    mt.l(em, "Emission", mt.out, "Surface")
    return mt.m


def nav_material(name: str, strength: float = 60.0) -> bpy.types.Material:
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


def glass_material(name: str) -> bpy.types.Material:
    mt = NodeMat(name)
    bsdf = mt.n("ShaderNodeBsdfPrincipled", 0, 0)
    bsdf.inputs["Base Color"].default_value = (0.004, 0.006, 0.010, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.06
    bsdf.inputs["Specular IOR Level"].default_value = 0.9
    bsdf.inputs["Emission Color"].default_value = (0.0, 0.05, 0.12, 1.0)
    bsdf.inputs["Emission Strength"].default_value = 0.6
    mt.l(bsdf, "BSDF", mt.out, "Surface")
    return mt.m


def radiator_material(name: str, fac: str, glow: float) -> bpy.types.Material:
    """Radiators: dark panels; the Mandate's glow orange (M_ASTRA_ShipLight Mode 3), with the wear texture breaking up the glow."""
    dark_hex, ember, _ = PAL.RADIATOR[fac]
    mt = NodeMat(name)
    bsdf = mt.n("ShaderNodeBsdfPrincipled", 0, 0)
    bsdf.inputs["Base Color"].default_value = (*srgb(dark_hex), 1.0)
    bsdf.inputs["Roughness"].default_value = 0.55
    bsdf.inputs["Metallic"].default_value = 0.4
    if glow > 0:
        wr, wg, wb, wa, tc = wear_channels(mt)
        var = mt.add(mt.mul(wb, 0.7), mt.mul(wr, 0.5))
        bsdf.inputs["Emission Color"].default_value = (*ember, 1.0)
        st = mt.mul(var, glow)
        mt.l(st[0], st[1], bsdf, "Emission Strength")
    mt.l(bsdf, "BSDF", mt.out, "Surface")
    return mt.m


def cut_material(name: str, heat: float = 0.35) -> bpy.types.Material:
    """M_ASTRA_ShipCut: scorched carbon with streaks and glowing embers (heat 0..1)."""
    mt = NodeMat(name)
    uv1 = mt.n("ShaderNodeUVMap", -1900, 300, uv_map="UVMap_D1")
    s1 = mt.n("ShaderNodeSeparateXYZ", -1700, 300)
    mt.l(uv1, "UV", s1, "Vector")
    wr, wg, wb, wa, tc = wear_channels(mt, scale=0.9 / 8.0)
    bsdf = mt.n("ShaderNodeBsdfPrincipled", 1500, 0)
    k = mt.mul(mt.mul(mt.add(mt.mul(wb, 1.1), 0.55), mt.sub(1.0, mt.mul(wa, 0.4))), mt.add(mt.mul((s1, "X"), 0.6), 1.0))
    col = mt.scale_c((0.05, 0.045, 0.04), k)
    mt.l(col[0], col[1], bsdf, "Base Color")
    bsdf.inputs["Roughness"].default_value = 0.85
    bsdf.inputs["Metallic"].default_value = 0.25
    e = mt.smooth(mt.add(wr, mt.mul(wg, 0.22)), 0.70, 0.84)
    bsdf.inputs["Emission Color"].default_value = (1.0, 0.33, 0.07, 1.0)
    st = mt.mul(e, 26.0 * heat * 0.2)
    mt.l(st[0], st[1], bsdf, "Emission Strength")
    mt.l(bsdf, "BSDF", mt.out, "Surface")
    return mt.m


def make_materials(fac: str) -> dict:
    """Preview materials for one faction's slots (names MI_HULL_<fac>_<Part>) — existing ones are rebuilt in place."""
    pre = f"MI_HULL_{fac}_"
    out = {}
    for part in PAL.PAINT[fac]:
        out[part] = hull_material(pre + part, fac, part)
    out["Lights"] = light_material(pre + "Lights", fac)
    out["Glow"] = glow_material(pre + "Glow", fac, PAL.LIGHTS[fac][3] * 0.6)
    out["Nav"] = nav_material(pre + "Nav")
    out["Glass"] = glass_material(pre + "Glass")
    out["Radiator"] = radiator_material(pre + "Radiator", fac, 2.6 if fac == "M" else 0.0)
    out["Cut"] = cut_material(pre + "Cut")
    out["Decal"] = hull_material(pre + "Decal", fac, "Marking")
    return out


# ------------------------------------------------------------------------------------------------------------- scene
def set_world(strength: float = 1.0) -> None:
    """The Teal Veil as a procedural sky: a teal nebula that lights the shadows a little, and a crisp star field that only the
    camera sees (so metal does not reflect noise)."""
    old = bpy.data.worlds.get("Aurelia")
    if old:
        bpy.data.worlds.remove(old)
    w = bpy.data.worlds.new("Aurelia")
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg = nt.nodes.new("ShaderNodeBackground")
    tc = nt.nodes.new("ShaderNodeTexCoord")

    def node(kind, **kw):
        nd = nt.nodes.new(kind)
        for k, v in kw.items():
            setattr(nd, k, v)
        return nd

    def link(a, ao, b, bi):
        nt.links.new(a.outputs[ao], b.inputs[bi])

    neb = node("ShaderNodeTexNoise", noise_dimensions="3D")
    neb.inputs["Scale"].default_value = 1.5
    neb.inputs["Detail"].default_value = 9.0
    neb.inputs["Roughness"].default_value = 0.62
    neb.inputs["Distortion"].default_value = 0.6
    link(tc, "Generated", neb, "Vector")
    env = node("ShaderNodeTexNoise", noise_dimensions="3D")
    env.inputs["Scale"].default_value = 0.55
    env.inputs["Detail"].default_value = 2.0
    link(tc, "Generated", env, "Vector")
    shape = node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP", clamp=True)
    shape.inputs["From Min"].default_value = 0.38
    shape.inputs["From Max"].default_value = 0.78
    link(neb, "Fac", shape, "Value")
    envm = node("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP", clamp=True)
    envm.inputs["From Min"].default_value = 0.35
    envm.inputs["From Max"].default_value = 0.7
    envm.inputs["To Min"].default_value = 0.15
    link(env, "Fac", envm, "Value")
    fld = node("ShaderNodeMath", operation="MULTIPLY")
    link(shape, "Result", fld, 0)
    link(envm, "Result", fld, 1)
    ramp = node("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    for pos, col in ((0.2, (0.0, 0.025, 0.035, 1.0)), (0.5, (0.01, 0.12, 0.13, 1.0)), (0.85, (0.10, 0.38, 0.36, 1.0))):
        el = ramp.color_ramp.elements.new(pos)
        el.color = col
    ramp.color_ramp.elements[-1].position = 1.0
    ramp.color_ramp.elements[-1].color = (0.35, 0.72, 0.62, 1.0)
    link(fld, 0, ramp, "Fac")
    # stars: two scales, sharp
    stars = []
    for scale, rad, gain in ((420.0, 0.16, 50.0), (1100.0, 0.20, 20.0)):
        vo = node("ShaderNodeTexVoronoi", voronoi_dimensions="3D", feature="F1")
        vo.inputs["Scale"].default_value = scale
        vo.inputs["Randomness"].default_value = 1.0
        link(tc, "Generated", vo, "Vector")
        sep = node("ShaderNodeSeparateColor")
        link(vo, "Color", sep, "Color")
        fall = node("ShaderNodeMapRange", clamp=True)
        fall.inputs["From Min"].default_value = 0.0
        fall.inputs["From Max"].default_value = rad
        fall.inputs["To Min"].default_value = 1.0
        fall.inputs["To Max"].default_value = 0.0
        link(vo, "Distance", fall, "Value")
        pw = node("ShaderNodeMath", operation="POWER")
        link(sep, "Red", pw, 0)
        pw.inputs[1].default_value = 30.0
        st = node("ShaderNodeMath", operation="MULTIPLY")
        link(fall, "Result", st, 0)
        link(pw, 0, st, 1)
        gs = node("ShaderNodeMath", operation="MULTIPLY")
        link(st, 0, gs, 0)
        gs.inputs[1].default_value = gain
        stars.append(gs)
    star_sum = node("ShaderNodeMath", operation="ADD")
    link(stars[0], 0, star_sum, 0)
    link(stars[1], 0, star_sum, 1)
    lp = node("ShaderNodeLightPath")
    star_cam = node("ShaderNodeMath", operation="MULTIPLY")
    link(star_sum, 0, star_cam, 0)
    link(lp, "Is Camera Ray", star_cam, 1)
    star_col = node("ShaderNodeCombineColor")
    for i, ch in enumerate(("Red", "Green", "Blue")):
        link(star_cam, 0, star_col, ch)
    tint = node("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
    tint.inputs[0].default_value = 1.0
    link(star_col, "Color", tint, 6)
    tint.inputs[7].default_value = (1.0, 0.93, 0.86, 1.0)
    total = node("ShaderNodeMix", data_type="RGBA", blend_type="ADD")
    total.inputs[0].default_value = 1.0
    link(ramp, "Color", total, 6)
    link(tint, "Result", total, 7)
    base = node("ShaderNodeMix", data_type="RGBA", blend_type="ADD")
    base.inputs[0].default_value = 1.0
    link(total, "Result", base, 6)
    base.inputs[7].default_value = (0.003, 0.008, 0.010, 1.0)
    link(base, "Result", bg, "Color")
    bg.inputs["Strength"].default_value = strength
    link(bg, "Background", out, "Surface")
    bpy.context.scene.world = w


def add_light(kind: str, name: str, color, energy: float, size: float = 0.05):
    ld = bpy.data.lights.new(name, kind)
    ld.color = color
    ld.energy = energy
    if kind == "SUN":
        ld.angle = math.radians(size)
    o = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(o)
    return o


def _sun_at(o, to_light: Vector) -> None:
    """Point a sun object so that the light comes from the direction `to_light` (unit vector from the scene towards the light)."""
    o.rotation_euler = (-to_light).to_track_quat("-Z", "Y").to_euler()


def rig(cam_loc, target, key_az: float = 72.0, key_el: float = 28.0, key: float = 5.0, fill: float = 0.7, rim: float = 0.0,
        side: float = 1.0, world: float = 1.0) -> None:
    """The Aurelia light, placed against the view: the orange star as the key, `key_az` degrees off the camera axis (90 = across the
    frame, `side` = +1 or -1 picks the side) so the plates show their relief, and a soft teal fill from the camera's side (the
    nebula: shadows read teal). `rim` adds a small orange kicker from behind the subject."""
    for o in [o for o in bpy.data.objects if o.type == "LIGHT"]:
        bpy.data.objects.remove(o, do_unlink=True)
    set_world(world)
    fwd = Vector(target) - Vector(cam_loc)
    az0 = math.atan2(fwd.y, fwd.x)
    el = math.radians(key_el)

    def dirto(az, e):
        return Vector((math.cos(e) * math.cos(az), math.cos(e) * math.sin(az), math.sin(e)))

    a = az0 + math.pi - side * math.radians(key_az)
    k = add_light("SUN", "Aurelia", (1.0, 0.86, 0.70), key, size=0.53)
    _sun_at(k, dirto(a, el))
    f = add_light("SUN", "TealVeil", (0.32, 0.80, 0.84), fill, size=12.0)
    _sun_at(f, dirto(az0 + math.pi + side * math.radians(28.0), math.radians(14.0)))
    if rim > 0:
        r = add_light("SUN", "Kicker", (1.0, 0.66, 0.42), rim, size=1.0)
        _sun_at(r, dirto(az0 - side * math.radians(20.0), math.radians(16.0)))


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


def fit_camera(name: str, points, direction, lens: float = 50.0, aspect: float = 16 / 9, margin: float = 0.07, up=(0.0, 0.0, 1.0),
               target=None, clip_end: float = 60000.0):
    """A camera looking at `points` (N x 3, world) from `direction` (unit vector from the subject towards the camera) at the distance
    that makes them just fit the frame with `margin`, centred on their projected bounding box."""
    P = np.asarray(points, np.float64)
    if len(P) > 40000:
        P = P[np.random.default_rng(1).choice(len(P), 40000, replace=False)]
    d = np.asarray(direction, np.float64)
    d = d / np.linalg.norm(d)
    fwd = -d
    upv = np.asarray(up, np.float64)
    right = np.cross(fwd, upv)
    right /= np.linalg.norm(right)
    upc = np.cross(right, fwd)
    tx = 18.0 / lens                                             # tan of the half angle across the sensor width
    ty = tx / aspect
    tgt = (P.min(axis=0) + P.max(axis=0)) / 2 if target is None else np.asarray(target, np.float64)
    R = float(np.linalg.norm(P.max(axis=0) - P.min(axis=0))) / 2
    for _ in range(4):
        lo, hi = R * 0.3, R * 60.0
        for _ in range(40):
            dist = (lo + hi) / 2
            pos = tgt + d * dist
            rel = P - pos
            z = rel @ fwd
            if z.min() <= 0.1:
                lo = dist
                continue
            nx = np.abs((rel @ right) / z) / tx
            ny = np.abs((rel @ upc) / z) / ty
            if max(nx.max(), ny.max()) > 1.0 - margin:
                lo = dist
            else:
                hi = dist
        dist = hi
        pos = tgt + d * dist
        rel = P - pos
        z = rel @ fwd
        xs, ys = (rel @ right) / z / tx, (rel @ upc) / z / ty
        cx, cy = (xs.max() + xs.min()) / 2, (ys.max() + ys.min()) / 2
        tgt = tgt + right * cx * tx * dist + upc * cy * ty * dist                  # re-centre on the projected box
    pos = tgt + d * dist
    return camera(name, tuple(pos), tuple(tgt), lens, clip_end=max(clip_end, dist * 4)), tuple(tgt)


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
