"""Aurelia system sky: NASA starmap + the Teal Veil nebula, painted procedurally on the celestial sphere
by a Cycles world shader (domain-warped fBm clouds, ridged filaments, absorbing dust lanes), rendered as an
equirectangular HDR panorama for Unreal's sky cubemap.

Usage:
  blender -b --factory-startup --python-exit-code 1 -P art/blender/sky_aurelia.py -- <out.hdr> [--res 8192] [--seed 7]
      [--preview out.png] [--glow 1.0]
"""
from __future__ import annotations

import math
import os
import sys

import bpy
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STARMAP = os.path.join(ROOT, "art", "_downloads", "nasa_svs", "starmap_2020_8k_gal.exr")


def arg(name, default):
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    return type(default)(argv[argv.index(name) + 1]) if name in argv else default


def setup_gpu():
    prefs = bpy.context.preferences.addons["cycles"].preferences
    try:
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = d.type == "METAL"
        bpy.context.scene.cycles.device = "GPU"
    except TypeError:
        bpy.context.scene.cycles.device = "CPU"


class G:
    """Tiny node-graph helper for the world shader."""

    def __init__(self, nt):
        self.nt = nt
        self.x = -2000

    def n(self, kind, **props):
        node = self.nt.nodes.new(kind)
        node.location = (self.x, 0)
        self.x += 40
        for k, v in props.items():
            if k.startswith("in_"):
                node.inputs[k[3:]].default_value = v
            else:
                setattr(node, k, v)
        return node

    def link(self, a, b):
        self.nt.links.new(a, b)

    def math(self, op, a, b=None, c=None):
        m = self.n("ShaderNodeMath", operation=op)
        for i, v in enumerate((a, b, c)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                m.inputs[i].default_value = v
            else:
                self.link(v, m.inputs[i])
        return m.outputs[0]

    def vmath(self, op, a, b=None, scale=None):
        m = self.n("ShaderNodeVectorMath", operation=op)
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, tuple):
                m.inputs[i].default_value = v
            else:
                self.link(v, m.inputs[i])
        if scale is not None:
            m.inputs["Scale"].default_value = scale
        return m.outputs[0] if op not in ("DOT_PRODUCT", "LENGTH", "DISTANCE") else m.outputs["Value"]

    def noise(self, vec, scale, w, detail=8.0, rough=0.55, distortion=0.0, lac=2.0):
        t = self.n("ShaderNodeTexNoise", noise_dimensions="4D")
        t.inputs["Scale"].default_value = scale
        t.inputs["W"].default_value = w
        t.inputs["Detail"].default_value = detail
        t.inputs["Roughness"].default_value = rough
        t.inputs["Distortion"].default_value = distortion
        t.inputs["Lacunarity"].default_value = lac
        self.link(vec, t.inputs["Vector"])
        return t

    def smooth(self, x, lo, hi):
        m = self.n("ShaderNodeMapRange", interpolation_type="SMOOTHSTEP")
        m.inputs["From Min"].default_value = lo
        m.inputs["From Max"].default_value = hi
        self.link(x, m.inputs["Value"])
        return m.outputs["Result"]

    def ramp(self, x, stops):
        r = self.n("ShaderNodeValToRGB")
        cr = r.color_ramp
        cr.elements[0].position, cr.elements[0].color = stops[0]
        cr.elements[1].position, cr.elements[1].color = stops[1]
        for pos, col in stops[2:]:
            e = cr.elements.new(pos)
            e.color = col
        self.link(x, r.inputs["Fac"])
        return r.outputs["Color"]


def build_world(seed: int, glow: float):
    world = bpy.data.worlds.new("AureliaSky")
    world.use_nodes = True
    nt = world.node_tree
    for node in list(nt.nodes):
        nt.nodes.remove(node)
    g = G(nt)
    out = g.n("ShaderNodeOutputWorld")
    tc = g.n("ShaderNodeTexCoord")
    D = tc.outputs["Generated"]                              # view direction (world)
    # --- starmap
    env = g.n("ShaderNodeTexEnvironment", projection="EQUIRECTANGULAR")
    env.image = bpy.data.images.load(STARMAP)
    g.link(D, env.inputs["Vector"])
    # --- nebula region: a great band tilted across the sky, centred on direction C
    C = (math.cos(math.radians(8)) * math.cos(math.radians(10)), math.cos(math.radians(8)) * math.sin(math.radians(10)),
         math.sin(math.radians(8)))
    # the band's pole (normal): the veil lies near the great circle orthogonal to P, concentrated around C
    P = (-0.28, 0.42, 0.86)
    pn = math.sqrt(sum(v * v for v in P))
    P = tuple(v / pn for v in P)
    # domain warp of the direction, two levels (IQ-style)
    w1 = g.noise(D, 1.6, seed * 1.37, detail=4.0, rough=0.5)
    warp1 = g.vmath("SUBTRACT", w1.outputs["Color"], (0.5, 0.5, 0.5))
    D1 = g.vmath("ADD", D, g.vmath("SCALE", warp1, scale=0.55))
    w2 = g.noise(D1, 3.2, seed * 2.11 + 3.0, detail=5.0, rough=0.55)
    warp2 = g.vmath("SUBTRACT", w2.outputs["Color"], (0.5, 0.5, 0.5))
    D2 = g.vmath("ADD", D1, g.vmath("SCALE", warp2, scale=0.28))
    # band mask: distance from the great circle (|dot(D, P)|) and angular distance from C (both warped)
    dp = g.vmath("DOT_PRODUCT", D1, P)
    band = g.math("SUBTRACT", 1.0, g.smooth(g.math("ABSOLUTE", dp), 0.05, 0.42))
    dc = g.vmath("DOT_PRODUCT", D1, C)
    reach = g.smooth(dc, -0.15, 0.75)
    region = g.math("MULTIPLY", band, reach)
    # soft cloud body
    body = g.noise(D2, 2.4, seed * 0.77, detail=9.0, rough=0.6)
    body_v = g.smooth(body.outputs["Fac"], 0.42, 0.78)
    clouds = g.math("MULTIPLY", body_v, region)
    # ridged filaments
    rn = g.noise(D2, 6.5, seed * 3.3 + 1.0, detail=10.0, rough=0.62, distortion=0.25)
    ridge = g.math("SUBTRACT", 1.0, g.math("ABSOLUTE", g.math("MULTIPLY_ADD", rn.outputs["Fac"], 2.0, -1.0)))
    ridge = g.math("POWER", ridge, 6.0)
    rn2 = g.noise(D2, 17.0, seed * 5.1 + 2.0, detail=6.0, rough=0.6)
    ridge2 = g.math("SUBTRACT", 1.0, g.math("ABSOLUTE", g.math("MULTIPLY_ADD", rn2.outputs["Fac"], 2.0, -1.0)))
    ridge2 = g.math("POWER", ridge2, 4.0)
    fil = g.math("MULTIPLY", g.math("MULTIPLY_ADD", ridge2, 0.6, 0.4), ridge)
    filaments = g.math("MULTIPLY", fil, g.math("MULTIPLY_ADD", clouds, 1.5, 0.15))
    filaments = g.math("MULTIPLY", filaments, region)
    # colour field
    cn = g.noise(D1, 1.9, seed * 4.4, detail=3.0, rough=0.5)
    cstretch = g.smooth(cn.outputs["Fac"], 0.34, 0.68)
    col = g.ramp(cstretch, [
        (0.02, (0.03, 0.20, 0.90, 1)),    # deep blue
        (0.30, (0.02, 0.70, 0.72, 1)),    # teal
        (0.52, (0.20, 0.92, 0.78, 1)),    # pale teal-green
        (0.74, (0.10, 0.52, 1.00, 1)),    # azure
        (0.88, (0.18, 0.55, 0.95, 1)),    # azure-teal
        (0.985, (0.80, 0.30, 0.46, 1)),   # rose (small H-alpha pockets)
    ])
    # hot cores: the brightest filaments whiten
    hot = g.math("MULTIPLY", g.smooth(filaments, 0.18, 0.55), 0.55)
    colw = g.n("ShaderNodeMix", data_type="RGBA", blend_type="MIX")
    g.link(hot, colw.inputs["Factor"])
    g.link(col, colw.inputs[6])
    colw.inputs[7].default_value = (0.85, 1.0, 0.96, 1)
    col = colw.outputs[2]
    # emission = colour * (0.35 clouds + 1.4 filaments) * glow
    lum = g.math("MULTIPLY_ADD", filaments, 1.4, g.math("MULTIPLY", clouds, 0.35))
    lum = g.math("MULTIPLY", lum, 0.085 * glow)
    emis = g.n("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
    emis.inputs["Factor"].default_value = 1.0
    g.link(col, emis.inputs[6])
    emis_rgb = emis.outputs[2]
    lum_rgb = g.n("ShaderNodeCombineColor")
    for i in range(3):
        g.link(lum, lum_rgb.inputs[i])
    g.link(lum_rgb.outputs[0], emis.inputs[7])
    # dust lanes: dark fractal absorption within and around the veil (dims the starmap behind it)
    dn = g.noise(D2, 4.1, seed * 6.6 + 7.0, detail=9.0, rough=0.6)
    dust = g.math("MULTIPLY", g.smooth(dn.outputs["Fac"], 0.5, 0.7), g.math("MULTIPLY", region, 0.92))
    trans = g.math("SUBTRACT", 1.0, dust)
    stars = g.n("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
    stars.inputs["Factor"].default_value = 1.0
    g.link(env.outputs["Color"], stars.inputs[6])
    t_rgb = g.n("ShaderNodeCombineColor")
    for i in range(3):
        g.link(trans, t_rgb.inputs[i])
    g.link(t_rgb.outputs[0], stars.inputs[7])
    # nebula emission is also partly obscured by its own dust (depth cue)
    emis_d = g.n("ShaderNodeMix", data_type="RGBA", blend_type="MULTIPLY")
    emis_d.inputs["Factor"].default_value = 0.6
    g.link(emis_rgb, emis_d.inputs[6])
    g.link(t_rgb.outputs[0], emis_d.inputs[7])
    total = g.n("ShaderNodeMix", data_type="RGBA", blend_type="ADD")
    total.inputs["Factor"].default_value = 1.0
    g.link(stars.outputs[2], total.inputs[6])
    g.link(emis_d.outputs[2], total.inputs[7])
    bg = g.n("ShaderNodeBackground")
    g.link(total.outputs[2], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 1.0
    g.link(bg.outputs[0], out.inputs["Surface"])
    return world


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    out = argv[0]
    res = arg("--res", 8192)
    seed = arg("--seed", 7)
    glow = arg("--glow", 1.0)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    setup_gpu()
    scene.cycles.samples = 4
    scene.cycles.use_denoising = False
    scene.cycles.pixel_filter_type = "BLACKMAN_HARRIS"
    scene.cycles.filter_width = 1.2
    scene.render.resolution_x = res
    scene.render.resolution_y = res // 2
    scene.view_settings.view_transform = "Standard"
    scene.render.image_settings.file_format = "HDR"
    scene.world = build_world(seed, glow)
    cam_data = bpy.data.cameras.new("Pano")
    cam_data.type = "PANO"
    cam_data.panorama_type = "EQUIRECTANGULAR"
    cam = bpy.data.objects.new("Pano", cam_data)
    scene.collection.objects.link(cam)
    cam.rotation_euler = (math.pi / 2, 0.0, -math.pi / 2)     # image centre = +X, up = +Z
    scene.camera = cam
    scene.render.filepath = out
    bpy.ops.render.render(write_still=True)
    print("SKY_OK", out)
    if "--preview" in argv:
        prev = argv[argv.index("--preview") + 1]
        img = bpy.data.images.load(out)
        w, h = img.size
        px = np.empty(w * h * 4, np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(h, w, 4)[::4, ::4, :3]
        k = 1.0 / max(1e-6, float(np.percentile(px, 99.7)))
        t = px * k * 1.5
        t = t / (1 + t)
        t = np.clip(t, 0, 1) ** (1 / 2.2)
        hh, ww, _ = t.shape
        o = bpy.data.images.new("prev", ww, hh, alpha=False)
        o.pixels.foreach_set(np.concatenate([t, np.ones((hh, ww, 1), np.float32)], axis=2).astype(np.float32).ravel())
        o.filepath_raw = prev
        o.file_format = "PNG"
        o.save()
        print("PREVIEW", prev)


main()
