"""Preview renders of the lift kit (Blender Eevee, headless): materials that mimic the Unreal instances (matched by SLOT NAME), the kit assembled the way the C++ puts it
together (a car in its shaft at a landing, the leaves half open, the car's screen with a stand-in picture), and a few cameras: the inside of the car, the landing, a section
of the shaft, the shuttle. Only for looking at the result: nothing here is exported. Called by ship_lift.py --preview <dir>."""
from __future__ import annotations

import math
import os

import bpy
from mathutils import Vector

import ship_lift as K

SCREEN_PICTURE = None


def lin(h: str):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c) + (1.0,)


# slot -> (base colour, metallic, roughness, emission colour, emission strength, alpha)
PALETTE = {
    "MI_ASTRA_Panel": ("#D9D3C6", 0.0, 0.42, None, 0.0, 1.0),
    "MI_ASTRA_Structure": ("#2C3036", 0.55, 0.42, None, 0.0, 1.0),
    "MI_ASTRA_Floor": ("#24262A", 0.2, 0.6, None, 0.0, 1.0),
    "MI_ASTRA_Trim": ("#9EA3A9", 0.9, 0.32, None, 0.0, 1.0),
    "MI_ASTRA_Light": ("#EAF4FF", 0.0, 0.5, "#EAF4FF", 14.0, 1.0),
    "MI_ASTRA_Accent": ("#3E7BFA", 0.0, 0.5, "#3E7BFA", 5.0, 1.0),
    "MI_ASTRA_Guide": ("#6FC3FF", 0.0, 0.5, "#6FC3FF", 6.0, 1.0),
    "MI_ASTRA_Glass": ("#9FC4D6", 0.0, 0.05, None, 0.0, 0.18),
    "MI_ASTRA_Rubber": ("#0C0C0E", 0.0, 0.7, None, 0.0, 1.0),
    "MI_LIFT_Ring": ("#6FC3FF", 0.0, 0.5, "#6FC3FF", 9.0, 1.0),
    "MI_LIFT_Lamp": ("#FFB347", 0.0, 0.5, "#FFB347", 16.0, 1.0),
    "MI_LIFT_Screen": ("#06121C", 0.0, 0.2, "#38A4D8", 1.4, 1.0),
}


def preview_materials() -> None:
    for m in bpy.data.materials:
        spec = PALETTE.get(m.name)
        if not spec:
            continue
        base, metal, rough, emit, strength, alpha = spec
        m.use_nodes = True
        nt = m.node_tree
        nt.nodes.clear()
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
        bsdf.inputs["Base Color"].default_value = lin(base)
        bsdf.inputs["Metallic"].default_value = metal
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Alpha"].default_value = alpha
        if emit:
            bsdf.inputs["Emission Color"].default_value = lin(emit)
            bsdf.inputs["Emission Strength"].default_value = strength
        if alpha < 1.0:
            m.blend_method = "BLEND" if hasattr(m, "blend_method") else None
        if m.name == "MI_LIFT_Screen":
            _screen_picture(m, bsdf)


def _screen_picture(m, bsdf) -> None:
    """A stand-in for what the game paints on the car's screen: a dark ground, the deck list with a mark, a big deck number."""
    size = 512
    img = bpy.data.images.new("LiftScreenPreview", size, size, alpha=False)
    px = [0.0] * (size * size * 4)

    def rect(x0, y0, x1, y1, c):
        for y in range(max(0, y0), min(size, y1)):
            for x in range(max(0, x0), min(size, x1)):
                i = (y * size + x) * 4
                px[i:i + 4] = [c[0], c[1], c[2], 1.0]
    rect(0, 0, size, size, (0.01, 0.04, 0.07))
    rect(0, size - 56, size, size - 52, (0.1, 0.5, 0.75))
    rect(22, size - 46, 150, size - 20, (0.2, 0.75, 1.0))                     # the title
    for i in range(9):
        y1 = size - 90 - i * 44
        c = (0.05, 0.12, 0.18) if i != 3 else (0.12, 0.55, 0.85)
        rect(18, y1 - 36, size - 150, y1, c)
        rect(28, y1 - 26, 110, y1 - 10, (0.75, 0.85, 0.9))
        rect(130, y1 - 24, 130 + 110 + (i * 37) % 120, y1 - 12, (0.35, 0.45, 0.5))
    rect(size - 138, 140, size - 20, 340, (0.04, 0.12, 0.18))                     # the big deck number
    rect(size - 118, 170, size - 40, 310, (0.35, 0.85, 1.0))
    img.pixels = px
    tex = m.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = img
    m.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = 2.2


# ------------------------------------------------------------------------------------------------------------------------------ the assembly
def build_all(builders) -> dict:
    """Every mesh of the kit as an object, by name (all at the origin: the assembly moves them)."""
    objs = {}
    for name, fn in builders:
        objs[name] = fn(name)
    preview_materials()
    return objs


def dup(obj, name: str, loc=(0.0, 0.0, 0.0), scale=(1.0, 1.0, 1.0)):
    c = obj.copy()
    c.data = obj.data
    c.name = name
    c.hide_render = False                        # (a copy of a hidden original is hidden: the originals are only the models)
    c.hide_viewport = False
    c.location = loc
    c.scale = scale
    bpy.context.scene.collection.objects.link(c)
    return c


def hide_all(objs) -> None:
    for o in objs.values():
        o.hide_render = True
        o.hide_viewport = True


def assemble(objs: dict, k: str, leaf: float = 0.0, car_leaf: float = 0.0, levels: int = 2, car_z: float = 0.0) -> dict:
    """A car at a landing in its shaft: the landing's frame and leaves at the shaft's front plane, the car's leaves, the shaft's segments above and below. `leaf` and `car_leaf` are the
    doors' travel, 0 shut .. 1 open. Returns the objects made by name."""
    c = K.KIT[k]
    sd_ = c["sd"] / 2
    cd = c["d"]
    xc = sd_ - K.SILL_GAP - cd / 2                  # the car's middle in the shaft's frame
    made = {}
    # the world: the landing's door plane at X = 0, the landing floor at Z = 0; the shaft's middle is at X = -sd_
    sx = -sd_
    car = dup(objs[f"SM_LIFT_Car_{k}"], "car", (sx + xc, 0.0, car_z))
    glass = dup(objs[f"SM_LIFT_CarGlass_{k}"], "glass", (sx + xc, 0.0, car_z))
    made["car"], made["glass"] = car, glass
    scr = dup(objs["SM_LIFT_Screen"], "screen")
    S_w, S_h = (0.80, 0.50) if k == "tl" else (1.00, 0.625)
    idp = (cd - 2 * K.WALL) / 2
    iw = (c["w"] - 2 * K.WALL) / 2
    scr.location = (sx + xc + idp - 0.70, iw - 0.03, car_z + 1.50)
    scr.rotation_euler = (0.0, 0.0, math.radians(-90.0))                         # (UE yaw +90 about Z: +X to +Y; Blender flips Y, so it turns the other way)
    scr.scale = (1.0, S_w, S_h)
    made["screen"] = scr
    # the car's leaves: at the car's front wall, centre X = D/2 + wall/2 (interior D), halves slide apart by their own half-width
    opw, oph = c["opw"], c["oph"]
    closed = opw * 0.25 - 0.01
    for side in (-1, 1):                                     # (the side in Unreal's terms: its +Y is Blender's -Y, the mesh as it is at +1 and mirrored at -1)
        y = -side * (closed + opw * 0.5 * car_leaf)
        made[f"carleaf{side}"] = dup(objs[f"SM_LIFT_CarLeaf_{k}"], f"carleaf{side}", (sx + xc + idp + K.WALL / 2, y, car_z + oph / 2), (1.0, float(side), 1.0))
    land = dup(objs[f"SM_LIFT_Landing_{k}"], "landing", (0.0, 0.0, 0.0))
    made["landing"] = land
    for side in (-1, 1):
        y = -side * (closed + opw * 0.5 * leaf)
        made[f"leaf{side}"] = dup(objs[f"SM_LIFT_LandingLeaf_{k}"], f"leaf{side}", (0.035, y, oph / 2), (1.0, float(side), 1.0))
    lamp = dup(objs["SM_LIFT_CallLamp"], "lamp", (0.08, opw / 2 + 0.45, 1.16))
    made["lamp"] = lamp
    # the shaft: a door segment at the landing, plain ones above and below
    door = dup(objs[f"SM_LIFT_ShaftDoor_{k}"], "shaftdoor", (sx, 0.0, -K.DOORSEG_DOWN))
    made["shaftdoor"] = door
    for i in range(levels):
        made[f"above{i}"] = dup(objs[f"SM_LIFT_Shaft_{k}"], f"above{i}", (sx, 0.0, -K.DOORSEG_DOWN + K.DOORSEG_H + i * K.SEG_H))
        made[f"below{i}"] = dup(objs[f"SM_LIFT_Shaft_{k}"], f"below{i}", (sx, 0.0, -K.DOORSEG_DOWN - (i + 1) * K.SEG_H))
    return made


# ------------------------------------------------------------------------------------------------------------------------------ rendering
def setup_scene(size=(1280, 800)) -> None:
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE"
    sc.render.resolution_x, sc.render.resolution_y = size
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = False
    try:
        sc.eevee.taa_render_samples = 24
        sc.eevee.use_raytracing = True
    except Exception:  # noqa: BLE001
        pass
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.exposure = 0.8
    try:
        sc.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    w = bpy.data.worlds.new("LiftWorld") if not bpy.data.worlds.get("LiftWorld") else bpy.data.worlds["LiftWorld"]
    w.use_nodes = True
    bg = w.node_tree.nodes["Background"]
    bg.inputs["Color"].default_value = (0.05, 0.06, 0.07, 1.0)
    bg.inputs["Strength"].default_value = 1.0
    sc.world = w


def light(loc, energy=300.0, size=0.4, color=(1.0, 0.97, 0.92), kind="AREA", name="L"):
    d = bpy.data.lights.new(name, kind)
    d.energy = energy
    d.color = color
    if kind == "AREA":
        d.shape = "SQUARE"
        d.size = size
    ob = bpy.data.objects.new(name, d)
    ob.location = loc
    ob.rotation_euler = (math.pi, 0, 0) if kind == "AREA" else (0, 0, 0)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def clear_lights() -> None:
    for o in list(bpy.data.objects):
        if o.type == "LIGHT":
            bpy.data.objects.remove(o, do_unlink=True)


def shoot(path: str, loc, target, lens=22.0, clip=(0.02, 200.0)) -> str:
    sc = bpy.context.scene
    cam_d = bpy.data.cameras.get("LiftCam") or bpy.data.cameras.new("LiftCam")
    cam_d.lens = lens
    cam_d.clip_start, cam_d.clip_end = clip
    cam = bpy.data.objects.get("LiftCam") or bpy.data.objects.new("LiftCam", cam_d)
    if cam.name not in sc.collection.objects:
        sc.collection.objects.link(cam)
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    sc.camera = cam
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    return path


def render_all(out_dir: str, builders) -> None:
    os.makedirs(out_dir, exist_ok=True)
    objs = build_all(builders)
    setup_scene()
    hide_all(objs)
    # ---- the turbolift: the inside, looking at the back window and at the screen's wall
    made = assemble(objs, "tl", leaf=1.0, car_leaf=1.0)
    clear_lights()
    xc = 1.4 - K.SILL_GAP - 1.2 - 1.4
    light((xc, 0.0, 2.4), 1200.0, 1.2, name="cabin")
    light((1.6, 0.0, 2.0), 300.0, 0.6, color=(0.8, 0.9, 1.0), name="lobby")
    shoot(os.path.join(out_dir, "car_back.png"), (xc + 0.92, 0.35, 1.55), (xc - 1.0, 0.0, 1.25), lens=20.0)
    shoot(os.path.join(out_dir, "car_screen.png"), (xc - 0.55, -0.75, 1.55), (xc + 0.35, 1.0, 1.45), lens=22.0)
    shoot(os.path.join(out_dir, "car_door.png"), (xc - 0.85, -0.45, 1.5), (xc + 1.1, 0.0, 1.3), lens=20.0)
    # ---- the landing from the lobby: shut, then half open with the car's doors open
    for nm, lf in (("landing_shut", 0.0), ("landing_open", 1.0)):
        for o in list(made.values()):
            o.hide_render = True
        made = assemble(objs, "tl", leaf=lf, car_leaf=lf)
        clear_lights()
        light((xc, 0.0, 2.4), 1200.0, 1.2, name="cabin")
        light((2.2, 0.8, 3.0), 1600.0, 1.5, name="lobby")
        shoot(os.path.join(out_dir, nm + ".png"), (3.3, -0.5, 1.55), (0.0, 0.1, 1.3), lens=22.0)
    # ---- the shaft's lining, as the window of the car sees it and as it runs up and down: the car is out of the way
    for o in list(made.values()):
        o.hide_render = True
    made = assemble(objs, "tl", leaf=0.0, car_leaf=0.0, levels=2)
    for key in ("car", "glass", "screen", "carleaf-1", "carleaf1"):
        made[key].hide_render = True
    clear_lights()
    light((-1.0, 0.0, 2.2), 600.0, 1.0, color=(0.7, 0.85, 1.0), name="shaftlamp")
    light((0.5, 0.0, 6.5), 600.0, 1.0, color=(0.7, 0.85, 1.0), name="shaftlamp2")
    shoot(os.path.join(out_dir, "shaft_back.png"), (xc + 0.4, 0.0, 1.5), (-1.4, 0.0, 1.4), lens=26.0)
    shoot(os.path.join(out_dir, "shaft_up.png"), (xc, -0.4, -3.2), (-0.9, 0.2, 5.0), lens=20.0)
    # ---- the other kinds' cars from the door side, and the shuttle's inside
    for k in ("sv", "cg"):
        for o in list(made.values()):
            o.hide_render = True
        made = assemble(objs, k, leaf=1.0, car_leaf=1.0)
        clear_lights()
        c = K.KIT[k]
        xk = c["sd"] / 2 - K.SILL_GAP - c["d"] / 2 - c["sd"] / 2
        light((xk, 0.0, c["h"] - 0.2), 1400.0, 1.4, name="cabin")
        light((2.4, 0.5, 3.0), 1800.0, 1.5, name="lobby")
        shoot(os.path.join(out_dir, f"landing_{k}.png"), (3.8, -0.6, 1.6), (0.0, 0.1, 1.3), lens=22.0)
    for o in list(made.values()):
        o.hide_render = True
    dup(objs["SM_LIFT_Car_sh"], "shuttle", (0.0, 0.0, 0.0))
    dup(objs["SM_LIFT_CarGlass_sh"], "shuttle_glass", (0.0, 0.0, 0.0))
    dup(objs["SM_LIFT_Screen"], "shuttle_screen", (-(K.SHUTTLE["d"] - 2 * K.WALL) / 2 + 0.04, 0.0, 1.65), (1.0, 1.40, 0.88))
    closed = K.SHUTTLE["opw"] * 0.25 - 0.01
    for y in K.SHUTTLE["doors"]:
        for side in (-1, 1):
            dup(objs["SM_LIFT_CarLeaf_sh"], f"shleaf{y}{side}", ((K.SHUTTLE["d"] - 2 * K.WALL) / 2 + K.WALL / 2, y - side * closed, K.SHUTTLE["oph"] / 2), (1.0, float(side), 1.0))
    clear_lights()
    for y in (-4.5, 0.0, 4.5):
        light((0.0, y, 2.7), 700.0, 1.0, name=f"s{y}")
    shoot(os.path.join(out_dir, "shuttle_inside.png"), (0.55, 5.8, 1.55), (-0.3, -2.0, 1.4), lens=18.0)
    shoot(os.path.join(out_dir, "shuttle_screen.png"), (0.9, -2.5, 1.5), (-1.2, 0.0, 1.6), lens=22.0)
    print("LIFT_PREVIEWS_OK", out_dir)
