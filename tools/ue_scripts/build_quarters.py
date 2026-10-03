"""Builds the Captain's quarters (Deck 1 · Section A) into the bridge level, from data/ship/aquila_quarters.json: the
wood and carpet textures and the cabin's screens, the materials (walnut, a navy carpet, a warm wall paint, cognac leather; the cabin mesh
art/blender/quarters_room.py also uses the medbay's linen / blanket / red, the bridge v3's brass / ivory / lamps / decor and, for the plants and
the globe, the ship kit's MI_SHIP_Leaf / Soil / CrateBlue), the kit (art/export/quarters, art/blender/quarters.py),
the bulkhead and door at the end of the starboard corridor, the cabin and its windows, the block outside (hull plates,
the bridge lift's housing, the fairings under the corridors), the warm lights (tagged ASTRA.Zone.Quarters: on only
while the Captain is there), the Aquila's model on the sideboard, the ship's plaque, and the AAstraQuarters actor (the
bunk: rest). Idempotent: the "Quarters" folder is replaced. Not during PIE, after the C++ module with AAstraQuarters:
  tools/ue.py pyfile tools/ue_scripts/build_quarters.py
"""
import json
import os

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
KIT = "/Game/ASTRA/Kit/Quarters"
CK = "/Game/ASTRA/Kit/Interior/Corridor"
MI_DIR = "/Game/ASTRA/Materials/Instances"
TEX = "/Game/ASTRA/Materials/Textures"
UI_TEX = "/Game/ASTRA/UI/Textures"
M = 100.0
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
D = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_quarters.json")))
OX, OY, OZ = D["world_origin"]
ZONE = "ASTRA.Zone.Quarters"
log = []


def import_png(src_dir, names, dst):
    tasks = []
    for n in names:
        t = unreal.AssetImportTask()
        t.filename = os.path.join(src_dir, n + ".png")
        t.destination_path = dst
        t.automated = True
        t.replace_existing = True
        t.save = False
        tasks.append(t)
    tools.import_asset_tasks(tasks)
    for n in names:
        tx = eal.load_asset(f"{dst}/{n}")
        if n.endswith("_N"):
            tx.set_editor_property("srgb", False)
            tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
            tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD_NORMAL_MAP)
        elif n.endswith("_ORM"):
            tx.set_editor_property("srgb", False)
            tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
            tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
        else:
            tx.set_editor_property("srgb", True)
            tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
        eal.save_loaded_asset(tx, only_if_is_dirty=False)


import_png(os.path.join(ROOT, "art", "_cache", "textures"), [f"T_{s}_{k}" for s in ("WoodDark", "Carpet") for k in ("BC", "N", "ORM")], TEX)
import_png(os.path.join(ROOT, "art", "_cache", "ui"), ["T_UI_Quarters_Map", "T_UI_Quarters_Log"], UI_TEX)
log.append("textures")


def mi(name, parent_path, scalars=None, vectors=None, textures=None):
    p = f"{MI_DIR}/{name}"
    inst = eal.load_asset(p) if eal.does_asset_exist(p) else tools.create_asset(name, MI_DIR, unreal.MaterialInstanceConstant,
                                                                                 unreal.MaterialInstanceConstantFactoryNew())
    mel.set_material_instance_parent(inst, eal.load_asset(parent_path))
    for k, v in (scalars or {}).items():
        mel.set_material_instance_scalar_parameter_value(inst, k, v)
    for k, v in (vectors or {}).items():
        mel.set_material_instance_vector_parameter_value(inst, k, unreal.LinearColor(*v, 1.0))
    for k, v in (textures or {}).items():
        mel.set_material_instance_texture_parameter_value(inst, k, eal.load_asset(v))
    mel.update_material_instance(inst)
    eal.save_loaded_asset(inst, only_if_is_dirty=False)


HARD = "/Game/ASTRA/Materials/M_ASTRA_Hard"
SCREEN = "/Game/ASTRA/Materials/M_ASTRA_Screen"


def hard(name, tint, rough, tex, uv=1.0, normal=0.5, influence=1.0, macro=0.04):
    mi(name, HARD, {"RoughnessMin": rough[0], "RoughnessMax": rough[1], "MetallicFromMap": 0.0, "MetallicBias": 0.0,
                    "BaseColorMapInfluence": influence, "NormalStrength": normal, "UVScale": uv, "MacroBrightness": macro,
                    "ScratchRoughness": 0.02, "RoughnessVariation": 0.05}, {"Tint": tint},
       {"BaseColorMap": f"{TEX}/T_{tex}_BC", "NormalMap": f"{TEX}/T_{tex}_N", "ORMMap": f"{TEX}/T_{tex}_ORM"})


# a captain's cabin in a warship: dark polished wood, a navy carpet (the grey carpet texture under a deep blue tint), warm pale walls, cognac leather
hard("MI_QTR_Wood", (1.0, 0.92, 0.86), (0.28, 0.46), "WoodDark", uv=1.2, normal=0.6)
hard("MI_QTR_Carpet", (0.17, 0.23, 0.44), (0.85, 0.96), "Carpet", uv=2.5, normal=0.8)
hard("MI_QTR_Rug", (0.22, 0.045, 0.040), (0.85, 0.96), "Carpet", uv=3.0, normal=0.8)             # the wool rugs: the same weave in oxblood
hard("MI_QTR_Wall", (0.58, 0.54, 0.48), (0.5, 0.65), "PanelPaint", uv=1.0, normal=0.3, influence=0.3)
hard("MI_QTR_Leather", (0.40, 0.17, 0.075), (0.30, 0.50), "LeatherBlack", uv=2.0, normal=0.7, influence=0.9, macro=0.05)
# the ship kit's instances that the plants and the globe of the props use (made by build_ship_interior.py; only made here if that has not run yet)
for name, tset, tint, uvs, rough, infl, nrm in (("MI_SHIP_Leaf", "Linen", (0.045, 0.20, 0.04), 4.0, (0.45, 0.65), 0.5, 0.6), ("MI_SHIP_Soil", "Linen", (0.035, 0.022, 0.014), 4.0, (0.7, 0.9), 0.5, 0.8),
                                                 ("MI_SHIP_CrateBlue", "PanelPaint", (0.045, 0.09, 0.20), 1.0, (0.5, 0.7), 0.25, 0.3)):
    if not eal.does_asset_exist(f"{MI_DIR}/{name}"):
        hard(name, tint, rough, tset, uv=uvs, normal=nrm, influence=infl)
mi("MI_QTR_Map", SCREEN, {"Intensity": 9.0, "Roughness": 0.35, "FlipU": 0.0, "FlipV": 0.0}, None, {"ScreenTexture": f"{UI_TEX}/T_UI_Quarters_Map"})
mi("MI_QTR_Log", SCREEN, {"Intensity": 9.0, "Roughness": 0.35, "FlipU": 0.0, "FlipV": 0.0}, None, {"ScreenTexture": f"{UI_TEX}/T_UI_Quarters_Log"})
log.append("materials")

for a in eas.get_all_level_actors():
    if str(a.get_folder_path()).startswith("Quarters"):
        eas.destroy_actor(a)
for path in eal.list_assets(KIT, recursive=False, include_folder=False):
    if not eal.delete_asset(path):
        log.append(f"could not delete {path}")
SRC = os.path.join(ROOT, "art", "export", "quarters")
DST = KIT
NANITE = True
exec(open(os.path.join(ROOT, "tools", "ue_scripts", "import_kit.py")).read())


def V(x, y, z):
    return unreal.Vector((OX + x) * M, (OY + y) * M, (OZ + z) * M)


def W(x, y, z):
    return unreal.Vector(x * M, y * M, z * M)


def place(path, loc, yaw=0.0, label=None, folder="Quarters", scale=None):
    asset = eal.load_asset(path)
    a = eas.spawn_actor_from_object(asset, loc, unreal.Rotator(roll=0, pitch=0, yaw=yaw))
    if scale:
        a.set_actor_scale3d(unreal.Vector(*scale))
    a.set_actor_label(label or asset.get_name())
    a.set_folder_path(folder)
    return a


place(f"{KIT}/SM_QTR_Room", V(0, 0, 0), label="Quarters_Room")
g = place(f"{KIT}/SM_QTR_Glass", V(0, 0, 0), label="Quarters_Glass")
g.static_mesh_component.set_editor_property("cast_shadow", False)
place(f"{KIT}/SM_SHIP_ASTRA_AquilaBridgeBlock", V(0, 0, 0), label="Aquila_BridgeBlock", folder="Quarters/Outside")

# ---- the starboard corridor ends in a bulkhead with a door (it had a blank end cap)
xe = D["corridor_end_x"]
for a in eas.get_all_level_actors():
    if a.get_actor_label() == "CorrStbd_EndCap":
        eas.destroy_actor(a)
        log.append("end cap removed")
place(f"{CK}/SM_COR_Bulkhead", W(xe, OY, 0.0), 180.0, label="Quarters_Bulkhead", folder="Quarters/Door")
door = eas.spawn_actor_from_class(unreal.AstraDoor, W(xe - 0.25, OY, 0.0), unreal.Rotator())
door.set_editor_property("width", D["door"]["width"] * M)
door.set_editor_property("height", D["door"]["height"] * M)
door.set_actor_label("Door_Quarters")
door.set_folder_path("Quarters/Door")


# ---- warm light: downlights over the sitting area, the desk and the bunk, the desk lamp, the reading light
def light(cls, x, y, z, label, intensity, color, radius, shadows=False, pitch=-90.0, yaw=0.0, cone=None, size=None):
    a = eas.spawn_actor_from_class(cls, V(x, y, z), unreal.Rotator(roll=0, pitch=pitch, yaw=yaw))
    c = a.get_component_by_class(unreal.LocalLightComponent)
    c.set_editor_property("intensity_units", unreal.LightUnits.LUMENS)
    c.set_editor_property("intensity", intensity)
    c.set_editor_property("attenuation_radius", radius)
    c.set_editor_property("use_temperature", True)
    c.set_editor_property("temperature", color)
    c.set_editor_property("cast_shadows", shadows)
    if cone and isinstance(c, unreal.SpotLightComponent):
        c.set_editor_property("outer_cone_angle", cone[0])
        c.set_editor_property("inner_cone_angle", cone[1])
    if size and isinstance(c, unreal.RectLightComponent):
        c.set_editor_property("source_width", size[0] * M)
        c.set_editor_property("source_height", size[1] * M)
    a.set_actor_label(label)
    a.set_folder_path("Quarters/Lighting")
    a.tags = [ZONE]
    return a


H = D["height"]
light(unreal.RectLight, -4.3, 0.0, H - 0.2, "Quarters_Cove", 5200, 3100.0, 900, size=(5.6, 5.0))
light(unreal.SpotLight, -4.3, -3.6, H - 0.02, "Quarters_Down_Sofa", 1400, 2900.0, 600, shadows=True, cone=(48.0, 20.0))
light(unreal.SpotLight, -7.2, 2.4, H - 0.02, "Quarters_Down_Desk", 1400, 2900.0, 600, cone=(44.0, 18.0))
light(unreal.SpotLight, -1.6, 2.2, H - 0.02, "Quarters_Down_Galley", 900, 3000.0, 500, cone=(44.0, 18.0))
dk = D["desk"]
light(unreal.PointLight, dk["x"] - 0.45 + 0.12, dk["y"] + 0.88, 1.08, "Quarters_DeskLamp", 450, 2700.0, 260)
bk = D["bunk"]
light(unreal.SpotLight, bk["x0"] - 0.55, -D["half_width"] + 0.3, 1.26, "Quarters_ReadingLight", 300, 2700.0, 300, pitch=-60.0, yaw=90.0,
      cone=(40.0, 16.0))
log.append("lights")

# ---- the Aquila's model on the sideboard (780 m at 1:1000: 78 cm), and the ship's plaque above the sofa
mp = D["model_pedestal"]
model = place("/Game/ASTRA/Ships/SM_SHIP_ASTRA_Aquila", V(mp["x"], D["half_width"] - 0.3, 1.12), 0.0, label="Quarters_AquilaModel",
              scale=(0.001, 0.001, 0.001))
model.tags = [unreal.Name("ASTRA.Interior")]
mc = model.get_component_by_class(unreal.StaticMeshComponent)
mc.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
plate = eal.load_asset("/Game/ASTRA/Kit/Signage/SM_SIGN_Plate")
sf = D["sofa"]
s = eas.spawn_actor_from_object(plate, V((sf["x0"] + sf["x1"]) / 2, -D["half_width"] + 0.06, 1.72), unreal.Rotator(roll=0, pitch=0, yaw=90.0))
s.set_actor_scale3d(unreal.Vector(1.0, 1.7, 0.425))
smc = s.get_component_by_class(unreal.StaticMeshComponent)
for i, sm in enumerate(plate.get_editor_property("static_materials")):
    if str(sm.get_editor_property("material_slot_name")).startswith("MI_SIGN_Face"):
        smc.set_material(i, eal.load_asset(f"{MI_DIR}/MI_SIGN_Aquila"))
smc.set_editor_property("cast_shadow", False)
s.set_actor_label("Quarters_Plaque")
s.set_folder_path("Quarters")

# ---- the cabin's controller: its lights, the bunk
q = eas.spawn_actor_from_class(unreal.AstraQuarters, V(0, 0, 0), unreal.Rotator())
q.set_editor_property("bunk_spot", unreal.Vector(((bk["x0"] + bk["x1"]) / 2) * M, (bk["y1"] + 0.55) * M, 0.0))
q.set_editor_property("cabin_min", unreal.Vector(-(D["length"] + 0.3) * M, -(D["half_width"] + 0.1) * M, -60.0))
q.set_editor_property("cabin_max", unreal.Vector(0.4 * M, (D["half_width"] + 0.1) * M, (H + 0.5) * M))
q.set_actor_label("Quarters_Controller")
q.set_folder_path("Quarters")
unreal.EditorLevelLibrary.save_current_level()
print(json.dumps(log))
