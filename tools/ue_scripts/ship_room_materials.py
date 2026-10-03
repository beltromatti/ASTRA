"""ARTE-INTERNI: the finishes of the Aquila's rooms in Unreal — the textures (art/_cache/textures: tools/art/interior_textures.py, tools/art/polyhaven_models.py) and one
MI_SHIP_* instance of M_ASTRA_Hard for every entry of data/ship/room_materials.json (the Blender previews read the same table).

Run on its own (editor, not PIE):   tools/ue.py pyfile tools/ue_scripts/ship_room_materials.py
or from build_ship_interior.py, which calls build() after its own MI_SHIP_* instances.

For every entry: Tint = the table's colour (sRGB hex) x `k` in linear light; UVScale, RoughnessMin/Max, MetallicFromMap/MetallicBias, BaseColorMapInfluence, NormalStrength as in the
table; the texture set T_<set>_BC / _N / _ORM (imported here when missing: sRGB colour, DirectX normal, masks); `two_sided`: true makes the instance two-sided (a leaf is one surface).
`uv_mode: mesh` entries (the leaf atlas, the swatch palette, the Poly Haven models) keep the mesh's own UVs (UVScale 1).
"""
import json
import os

import unreal

ROOT = globals().get("ROOT", os.environ.get("ASTRA_ROOT", "/Users/beltromatti/Desktop/ASTRA"))
TABLE = ROOT + "/data/ship/room_materials.json"
TEX_SRC = ROOT + "/art/_cache/textures"
MAT_DST = "/Game/ASTRA/Materials"
TEX_DST = MAT_DST + "/Textures"
MI_DIR = MAT_DST + "/Instances"

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
tools = unreal.AssetToolsHelpers.get_asset_tools()


def srgb_to_linear(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return [x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c]


def _stamp_file():
    return unreal.Paths.project_saved_dir() + "Ship/room_textures.json"


def import_set(name, log, stamp):
    """T_<name>_BC / _N / _ORM from art/_cache/textures when they are not in the project yet or the file changed since the last import (the stamp is the file's size, kept in Saved/Ship)."""
    tasks, todo = [], []
    for suffix in ("BC", "N", "ORM"):
        tname = f"T_{name}_{suffix}"
        src = f"{TEX_SRC}/{tname}.png"
        if not os.path.exists(src):
            raise RuntimeError(f"{src} missing: run tools/art/interior_textures.py / tools/art/polyhaven_models.py --all")
        size = os.path.getsize(src)
        if eal.does_asset_exist(f"{TEX_DST}/{tname}") and stamp.get(tname) == size:
            continue
        stamp[tname] = size
        t = unreal.AssetImportTask()
        t.filename = src
        t.destination_path = TEX_DST
        t.automated = True
        t.replace_existing = True
        t.save = False
        tasks.append(t)
        todo.append(tname)
    if not tasks:
        return
    tools.import_asset_tasks(tasks)
    for tname in todo:
        tx = eal.load_asset(f"{TEX_DST}/{tname}")
        if tname.endswith("_N"):
            tx.set_editor_property("srgb", False)
            tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
            tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD_NORMAL_MAP)
        elif tname.endswith("_BC"):
            tx.set_editor_property("srgb", True)
            tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_DEFAULT)
            tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
        else:
            tx.set_editor_property("srgb", False)
            tx.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
            tx.set_editor_property("lod_group", unreal.TextureGroup.TEXTUREGROUP_WORLD)
        eal.save_loaded_asset(tx, only_if_is_dirty=False)
    log.append(f"textures of {name}: {len(todo)} imported")


def build(log=None):
    """Imports the texture sets and makes (or updates) every MI_SHIP_* instance of the table; returns the names made."""
    log = log if log is not None else []
    table = json.load(open(TABLE, encoding="utf-8"))["materials"]
    hard = eal.load_asset(f"{MAT_DST}/M_ASTRA_Hard")
    if hard is None:
        raise RuntimeError("M_ASTRA_Hard missing: run make_materials.py first")
    stamp_path = _stamp_file()
    stamp = json.load(open(stamp_path, encoding="utf-8")) if os.path.exists(stamp_path) else {}
    for sname in sorted({e["set"] for e in table.values()}):
        if sname in ("Brushed", "PanelPaint", "Cotton", "Linen", "WoodDark"):             # the project's own sets (make_materials.py imports them)
            continue
        import_set(sname, log, stamp)
    os.makedirs(os.path.dirname(stamp_path), exist_ok=True)
    json.dump(stamp, open(stamp_path, "w", encoding="utf-8"), indent=0)
    made = []
    for name, e in table.items():
        tint = [c * e.get("k", 1.0) for c in srgb_to_linear(e["tint"])]
        mesh_uv = e.get("uv_mode") == "mesh"
        rough = e.get("rough", [0.4, 0.7])
        path = f"{MI_DIR}/{name}"
        mi = eal.load_asset(path) if eal.does_asset_exist(path) else tools.create_asset(name, MI_DIR, unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        if mi.get_editor_property("parent") != hard:
            mel.set_material_instance_parent(mi, hard)
        scalars = {"UVScale": 1.0 if mesh_uv else float(e.get("uv", 1.0)), "RoughnessMin": rough[0], "RoughnessMax": rough[1], "MetallicFromMap": float(e.get("metal_map", 0.0)),
                   "MetallicBias": float(e.get("metal_bias", 0.0)), "BaseColorMapInfluence": float(e.get("influence", 1.0)), "NormalStrength": float(e.get("normal", 0.6)),
                   "MacroBrightness": 0.0 if mesh_uv else 0.05, "ScratchRoughness": 0.0 if mesh_uv else 0.03, "RoughnessVariation": 0.0 if mesh_uv else 0.06}
        for k, v in scalars.items():
            mel.set_material_instance_scalar_parameter_value(mi, k, v)
        mel.set_material_instance_vector_parameter_value(mi, "Tint", unreal.LinearColor(tint[0], tint[1], tint[2], 1.0))
        for param, suffix in (("BaseColorMap", "BC"), ("NormalMap", "N"), ("ORMMap", "ORM")):
            tx = eal.load_asset(f"{TEX_DST}/T_{e['set']}_{suffix}")
            if tx is None:
                raise RuntimeError(f"{name}: texture T_{e['set']}_{suffix} missing")
            mel.set_material_instance_texture_parameter_value(mi, param, tx)
        if e.get("two_sided"):
            ov = mi.get_editor_property("base_property_overrides")
            ov.set_editor_property("override_two_sided", True)
            ov.set_editor_property("two_sided", True)
            mi.set_editor_property("base_property_overrides", ov)
        mel.update_material_instance(mi)
        eal.save_loaded_asset(mi, only_if_is_dirty=False)
        made.append(name)
    log.append(f"{len(made)} room finishes (data/ship/room_materials.json)")
    return made


if __name__ == "__main__":
    _log = []
    _made = build(_log)
    print(json.dumps({"made": len(_made), "log": _log}, indent=1))
