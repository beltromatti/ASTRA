"""Shared editor helpers for ASTRA's automation scripts (tools/ue_scripts/*). Import with:
    import importlib, astra_editor; importlib.reload(astra_editor)"""
import unreal

eal = unreal.EditorAssetLibrary
MI_DIR = "/Game/ASTRA/Materials/Instances"


def save(asset) -> bool:
    """Always save (EditorAssetLibrary.save_loaded_asset skips packages it does not consider dirty)."""
    return eal.save_loaded_asset(asset, only_if_is_dirty=False)


def assign_materials_by_slot(folder: str, mi_dir: str = MI_DIR, delete_stubs: bool = True, asset_paths: list[str] | None = None) -> list:
    """Every static mesh in `folder`: slot named X gets <mi_dir>/X when it exists.
    Then deletes the placeholder materials/instances the FBX import created in `folder`."""
    report = []
    stubs = set()
    for path in (asset_paths if asset_paths is not None else eal.list_assets(folder, recursive=False, include_folder=False)):
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


SKY_MI = "/Game/ASTRA/Space/MI_ASTRA_SpaceSky_Aurelia"
SKY_CUBE = "/Game/ASTRA/Space/T_Sky_Aurelia_8k"


def setup_space(sky_yaw_deg: float = 0.0, sky_pitch_deg: float = 0.0) -> str:
    """Current level: sky sphere uses the Aurelia sky instance rotated by yaw/pitch, the star disk is aligned with
    the 'Sun_Aurelia' directional light, the SkyLight uses the same cubemap. Returns a short report."""
    import math
    eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    mel = unreal.MaterialEditingLibrary
    mi = eal.load_asset(SKY_MI)
    y, p = math.radians(sky_yaw_deg), math.radians(sky_pitch_deg)
    # world->sky rotation = Ry(-p) * Rz(-y): rows are the sky basis expressed in world space
    cy, sy, cp, sp = math.cos(y), math.sin(y), math.cos(p), math.sin(p)
    ax = (cp * cy, cp * sy, sp)
    ay = (-sy, cy, 0.0)
    az = (-sp * cy, -sp * sy, cp)
    for name, v in (("SkyAxisX", ax), ("SkyAxisY", ay), ("SkyAxisZ", az)):
        mel.set_material_instance_vector_parameter_value(mi, name, unreal.LinearColor(v[0], v[1], v[2], 0.0))
    sun = None
    for a in eas.get_all_level_actors():
        if a.get_actor_label() == "Sun_Aurelia":
            sun = a
    if sun:
        f = sun.get_actor_forward_vector()
        mel.set_material_instance_vector_parameter_value(mi, "SunDirection", unreal.LinearColor(-f.x, -f.y, -f.z, 0.0))
    # New Ravenna: ahead, to port and a little low at the start (given in world space, stored in the sky frame)
    w = (0.8, -0.5, -0.1)
    nw = math.sqrt(sum(c * c for c in w))
    w = tuple(c / nw for c in w)
    ps = tuple(sum(w[k] * axis[k] for k in range(3)) for axis in (ax, ay, az))
    mel.set_material_instance_vector_parameter_value(mi, "PlanetDirection", unreal.LinearColor(ps[0], ps[1], ps[2], 0.0))
    mel.update_material_instance(mi)
    save(mi)
    for a in eas.get_all_level_actors():
        if a.get_actor_label() == "SpaceSky":
            a.get_component_by_class(unreal.StaticMeshComponent).set_material(0, mi)
        c = a.get_component_by_class(unreal.SkyLightComponent) if hasattr(a, "get_component_by_class") else None
        if c:
            c.set_editor_property("source_type", unreal.SkyLightSourceType.SLS_SPECIFIED_CUBEMAP)
            c.set_editor_property("cubemap", eal.load_asset(SKY_CUBE))
            c.recapture_sky()
    return f"sky yaw {sky_yaw_deg} pitch {sky_pitch_deg}, sun {'synced' if sun else 'missing'}"
