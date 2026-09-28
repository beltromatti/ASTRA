"""The Aquila's lifepods (art/blender/lifepod.py): the textures (the pod's status displays, the hatches' plates), the
materials, the three meshes (/Game/ASTRA/Kit/Lifepod), and the two hatches off Corridor 1-A — 1-A on the port wall by
the lift, 1-B on the starboard wall towards the Captain's quarters — each in place of the wall bay 0_1 (its two panels
are hidden, not deleted). Idempotent: the "Lifepods" folder is replaced. Not during PIE, after the C++ module is built
(AAstraLifepodHatch): tools/ue.py pyfile tools/ue_scripts/build_lifepods.py
"""
import os

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
KIT = "/Game/ASTRA/Kit/Lifepod"
MI_DIR = "/Game/ASTRA/Materials/Instances"
TEX = "/Game/ASTRA/Materials/Textures"
UI_TEX = "/Game/ASTRA/UI/Textures"
SIGN_TEX = "/Game/ASTRA/UI/Signage"
eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
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
        tx.set_editor_property("srgb", True)
        tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
        eal.save_loaded_asset(tx, only_if_is_dirty=False)


import_png(os.path.join(ROOT, "art", "_cache", "ui"), ["T_UI_Pod_Status"], UI_TEX)
import_png(os.path.join(ROOT, "art", "_cache", "signage"), ["T_SIGN_Lifepod_1A", "T_SIGN_Lifepod_1B"], SIGN_TEX)
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
EMI = "/Game/ASTRA/Materials/M_ASTRA_Emissive"
SCREEN = "/Game/ASTRA/Materials/M_ASTRA_Screen"


def hard(name, tint, rough, tex="PanelPaint", uv=1.0, normal=0.4, influence=0.3, macro=0.05):
    mi(name, HARD, {"RoughnessMin": rough[0], "RoughnessMax": rough[1], "MetallicFromMap": 0.0, "MetallicBias": 0.0,
                    "BaseColorMapInfluence": influence, "NormalStrength": normal, "UVScale": uv, "MacroBrightness": macro,
                    "ScratchRoughness": 0.08, "RoughnessVariation": 0.08}, {"Tint": tint},
       {"BaseColorMap": f"{TEX}/T_{tex}_BC", "NormalMap": f"{TEX}/T_{tex}_N", "ORMMap": f"{TEX}/T_{tex}_ORM"})


# safety yellow and black, worn at the edges; the pods' red emergency strip; the hatch's status lamp (the game sets its
# colour); the pod's two displays; the hatches' plates
hard("MI_POD_Yellow", (0.62, 0.42, 0.02), (0.35, 0.55), normal=0.5, influence=0.35, macro=0.1)
hard("MI_POD_Black", (0.018, 0.018, 0.02), (0.4, 0.6), normal=0.5, influence=0.3)
mi("MI_POD_RedLight", EMI, {"Intensity": 30.0, "AlertColorWeight": 0.0, "LightDimWeight": 0.0},
   {"EmissiveColor": (1.0, 0.08, 0.03), "BaseColor": (0.05, 0.01, 0.01)})
mi("MI_POD_Status", EMI, {"Intensity": 6.0, "AlertColorWeight": 0.0, "LightDimWeight": 0.0},
   {"EmissiveColor": (0.1, 1.0, 0.3), "BaseColor": (0.02, 0.02, 0.02)})
mi("MI_POD_Screen", SCREEN, {"Intensity": 6.0, "Roughness": 0.3, "FlipU": 0.0, "FlipV": 0.0}, None,
   {"ScreenTexture": f"{UI_TEX}/T_UI_Pod_Status"})
for pod in ("1A", "1B"):
    mi(f"MI_SIGN_Lifepod_{pod}", SCREEN, {"Intensity": 8.0, "Roughness": 0.4, "FlipU": 0.0, "FlipV": 0.0}, None,
       {"ScreenTexture": f"{SIGN_TEX}/T_SIGN_Lifepod_{pod}"})
log.append("materials")

for a in eas.get_all_level_actors():
    if str(a.get_folder_path()).startswith("Lifepods"):
        eas.destroy_actor(a)

SRC = os.path.join(ROOT, "art", "export", "lifepod")
DST = KIT
NANITE = True
exec(open(os.path.join(ROOT, "tools", "ue_scripts", "import_kit.py")).read())
log.append("kit")

# the hatches: bay 0_1 of each corridor (x -18.66 .. -16.94 m), the outboard wall's face at y -/+5.49 m
HATCH = eal.load_asset(f"{KIT}/SM_POD_Hatch")
cls = unreal.load_class(None, "/Script/ASTRA.AstraLifepodHatch")
by_label = {a.get_actor_label(): a for a in eas.get_all_level_actors()}
for name, y, yaw, launch, panels in (
        ("1-A", -549.0, 90.0, unreal.Vector(-0.25, -1.0, 0.45), ("CorrPort0_1_PanelLow_Vent_L", "CorrPort0_1_PanelUp_Plain_L")),
        ("1-B", 549.0, -90.0, unreal.Vector(-0.25, 1.0, 0.45), ("CorrStbd0_1_PanelLow_Plain_R", "CorrStbd0_1_PanelUp_Plain_R"))):
    for label in panels:
        p = by_label.get(label)
        if p:
            p.set_actor_hidden_in_game(True)
            p.set_actor_enable_collision(False)
            p.set_is_temporarily_hidden_in_editor(True)
    h = eas.spawn_actor_from_class(cls, unreal.Vector(-1780.0, y, 0.0), unreal.Rotator(roll=0.0, pitch=0.0, yaw=yaw))
    h.set_actor_label(f"Lifepod_Hatch_{name}")
    h.set_folder_path("Lifepods")
    h.set_editor_property("pod_name", name)
    h.set_editor_property("launch_dir", launch)
    mc = h.get_component_by_class(unreal.StaticMeshComponent)
    mc.set_static_mesh(HATCH)
    slot = mc.get_material_index("MI_SIGN_Lifepod_1A")
    if name == "1-B" and slot >= 0:
        mc.set_material(slot, eal.load_asset(f"{MI_DIR}/MI_SIGN_Lifepod_1B"))
    log.append(f"hatch {name}")

unreal.EditorLevelLibrary.save_current_level()
print(log)
