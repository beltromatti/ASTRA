"""ASN Aquila interior kit: Eevee previews (headless) of the modules, the rooms and the deck. Preview only: nothing here is exported.

The assembled scene places LINKED instances of the built meshes where the plan puts them (layout coordinates: X forward, Y
starboard; Blender space mirrors Y), adds the lights of the zone lights of the plan near the camera, and renders views.
"""
from __future__ import annotations

import math
import os

import bpy
from mathutils import Matrix, Vector

import sys

import ship_lib as SL
import bridge3_preview as PV

sys.path.insert(0, os.path.join(SL.ROOT, "tools", "ue_scripts"))          # bridge3_layout (kelvin_to_rgb)


def instance(obj, pos, yaw: float, name: str | None = None, mirror_y: bool = False):
    """A linked duplicate of `obj` placed at layout `pos` (x, y, z) with layout `yaw` (degrees, +x towards +y)."""
    inst = bpy.data.objects.new(name or obj.name, obj.data)
    bpy.context.scene.collection.objects.link(inst)
    inst.matrix_world = Matrix.Translation((pos[0], -pos[1], pos[2])) @ Matrix.Rotation(-math.radians(yaw), 4, "Z")
    return inst


def setup(width: int = 1600, height: int = 900, samples: int = 40, exposure: float = 0.0, world=(0.0, 0.0, 0.0)) -> None:
    SL.make_preview_materials()
    PV.set_world(world, 1.0)
    PV.configure_render(width, height, samples, exposure=exposure)


def light_at(name: str, pos, energy: float = 220.0, color=(1.0, 0.92, 0.82), size: float = 0.25, shadow: bool = False,
             kind: str = "POINT", radius: float | None = None):
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy
    ld.color = color
    if kind == "POINT":
        ld.shadow_soft_size = size
    ld.use_shadow = shadow
    o = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(o)
    o.location = (pos[0], -pos[1], pos[2])
    return o


def rect_light(name: str, pos, size, energy: float, color=(1.0, 0.95, 0.85), shadow: bool = False, direction=(0, 0, -1)):
    """An area light at layout `pos`, `size` = (x, y) metres, aimed along `direction` (layout coords)."""
    ld = bpy.data.lights.new(name, "AREA")
    ld.shape = "RECTANGLE"
    ld.size, ld.size_y = size
    ld.energy = energy
    ld.color = color
    ld.use_shadow = shadow
    o = bpy.data.objects.new(name, ld)
    bpy.context.scene.collection.objects.link(o)
    o.location = (pos[0], -pos[1], pos[2])
    d = Vector((direction[0], -direction[1], direction[2])).normalized()
    o.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return o


def camera(name: str, eye, yaw: float, pitch: float, fov: float = 80.0):
    return PV.add_camera(name, eye, yaw, pitch, fov)


def render(cam, path: str) -> str:
    return PV.render(cam, path)


def look_camera(name: str, eye, target, fov: float = 80.0):
    dx, dy, dz = target[0] - eye[0], target[1] - eye[1], target[2] - eye[2]
    yaw = math.degrees(math.atan2(dy, dx))
    pitch = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
    return PV.add_camera(name, eye, yaw, pitch, fov)


def spec_lights(spec: dict, origin=(0.0, 0.0, 0.0), yaw: float = 0.0, gain: float = 1.0, shadows: bool = False) -> list:
    """The zone lights of a prefab spec (ship_spec) as Blender area lights at the prefab's placement (layout coordinates)."""
    import ship_plan as P
    out = []
    kelvin = None
    import bridge3_layout as LAY
    for l in spec.get("lights", []):
        w = P.place_local(origin, yaw, l["pos"][0], l["pos"][1], l["pos"][2])
        col = LAY.kelvin_to_rgb(l.get("temperature", 4500))
        sx, sy = l["size"]
        if (yaw % 180.0) != 0.0:
            sx, sy = sy, sx
        ld = bpy.data.lights.new("zl", "AREA")
        ld.shape = "RECTANGLE"
        ld.size, ld.size_y = max(0.2, sx), max(0.2, sy)
        ld.energy = l["lumens"] * 0.03 * gain * (1.0 + 0.4 * math.log10(1 + sx * sy))
        ld.color = col
        ld.use_shadow = shadows
        o = bpy.data.objects.new("zl", ld)
        bpy.context.scene.collection.objects.link(o)
        o.location = (w[0], -w[1], w[2])
        out.append(o)
    return out


def plan_camera(name: str, x0: float, x1: float, y0: float, y1: float, z_cut: float, aspect: float = 16 / 9):
    """An orthographic camera looking straight down at the plan box (layout coordinates), cutting everything above z_cut."""
    cd = bpy.data.cameras.new(name)
    cd.type = "ORTHO"
    w, h = x1 - x0, y1 - y0
    cd.ortho_scale = max(w, h * aspect) * 1.04
    cd.clip_start = 0.001
    cd.clip_end = 200.0
    o = bpy.data.objects.new(name, cd)
    bpy.context.scene.collection.objects.link(o)
    o.location = ((x0 + x1) / 2, -(y0 + y1) / 2, z_cut)
    o.rotation_euler = (0.0, 0.0, 0.0)
    o.rotation_euler = (0, 0, 0)
    return o


def flat_light(strength: float = 2.6):
    """A shadowless sun straight down: lights every floor evenly (plan views)."""
    ld = bpy.data.lights.new("plan_sun", "SUN")
    ld.energy = strength
    ld.use_shadow = False
    o = bpy.data.objects.new("plan_sun", ld)
    bpy.context.scene.collection.objects.link(o)
    o.rotation_euler = (0, 0, 0)
    return o
