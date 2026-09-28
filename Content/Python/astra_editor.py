"""Shared editor helpers for ASTRA's automation scripts (tools/ue_scripts/*). Import with:
    import importlib, astra_editor; importlib.reload(astra_editor)"""
import unreal

eal = unreal.EditorAssetLibrary
MI_DIR = "/Game/ASTRA/Materials/Instances"


def save(asset) -> bool:
    """Always save (EditorAssetLibrary.save_loaded_asset skips packages it does not consider dirty)."""
    return eal.save_loaded_asset(asset, only_if_is_dirty=False)


def assign_materials_by_slot(folder: str, mi_dir: str = MI_DIR, delete_stubs: bool = True) -> list:
    """Every static mesh in `folder`: slot named X gets <mi_dir>/X when it exists.
    Then deletes the placeholder materials/instances the FBX import created in `folder`."""
    report = []
    stubs = set()
    for path in eal.list_assets(folder, recursive=False, include_folder=False):
        mesh = eal.load_asset(path)
        if not isinstance(mesh, unreal.StaticMesh):
            continue
        mesh.modify()
        changed = []
        for i, sm in enumerate(mesh.get_editor_property("static_materials")):
            slot = str(sm.get_editor_property("material_slot_name"))
            old = sm.get_editor_property("material_interface")
            if old and old.get_path_name().startswith(folder + "/"):
                stubs.add(old.get_path_name().split(".")[0])
            target = f"{mi_dir}/{slot}"
            if eal.does_asset_exist(target):
                mesh.set_material(i, eal.load_asset(target))
                changed.append(slot)
        # verify before touching anything else: a failed assignment must never lead to deleting what is in use
        for i, sm in enumerate(mesh.get_editor_property("static_materials")):
            mi = sm.get_editor_property("material_interface")
            if mi and mi.get_path_name().startswith(folder + "/"):
                raise RuntimeError(f"{mesh.get_name()} slot {i} still uses {mi.get_path_name()}")
        save(mesh)
        report.append((mesh.get_name(), changed))
    if delete_stubs:
        for s in sorted(stubs):
            if eal.does_asset_exist(s):
                eal.delete_asset(s)
    return report
