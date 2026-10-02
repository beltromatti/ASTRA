"""ABBORDAGGI: the Captain's arms for the weapons, /Game/ASTRA/Weapons/SKM_ASTRA_Arms.

The mannequin's mesh is a whole body. Held in front of a camera that rides on the Captain's eyes (and that places the arms so that the weapon sits where it should on the
screen), its head, shoulders and chest fill the view and the arms hang from them. What the weapons need is the arms alone: this cuts the mannequin down to the lower half of the
upper arm, the forearm and the hand with its fingers (every bone stays, so the mannequin's animations play on it unchanged and the hand sockets, which are the skeleton's,
are there), with the mannequin's own two materials. Idempotent: the asset is made again each time.

Run in the editor: tools/ue.py pyfile tools/ue_scripts/make_fp_arms.py
"""
import unreal

SRC = "/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple"
DST_DIR = "/Game/ASTRA/Weapons"
DST_NAME = "SKM_ASTRA_Arms"
# the bones whose skin stays (by their name's start): the elbow end of the upper arm (its second twist segment), the forearm with its twists, the hand and the fingers
KEEP = ("upperarm_twist_02", "lowerarm", "hand", "index", "middle", "ring", "pinky", "thumb")

eal = unreal.EditorAssetLibrary
Assets = unreal.GeometryScript_AssetUtils
NewAssets = unreal.GeometryScript_NewAssetUtils
Queries = unreal.GeometryScript_MeshQueries
Bones = unreal.GeometryScript_BoneWeights
Lists = unreal.GeometryScript_List


def log(*a):
    unreal.log("[ARMS] " + " ".join(str(x) for x in a))


def main():
    src = eal.load_asset(SRC)
    if src is None:
        raise RuntimeError("the mannequin mesh is not in the project: " + SRC)
    dm = unreal.DynamicMesh()
    dm, outcome = Assets.copy_mesh_from_skeletal_mesh(src, dm, unreal.GeometryScriptCopyMeshFromAssetOptions(), unreal.GeometryScriptMeshReadLOD())
    if outcome != unreal.GeometryScriptOutcomePins.SUCCESS:
        raise RuntimeError("could not read the mannequin mesh")

    dm, infos = Bones.get_all_bones_info(dm)
    names = {b.index: str(b.name) for b in infos}
    dm, plist, _gaps = Queries.get_all_vertex_positions(dm, False)
    nv = len(Lists.convert_vector_list_to_array(plist))
    keep = [False] * nv
    for v in range(nv):
        dm, w, ok = Bones.get_largest_vertex_bone_weight(dm, v)
        keep[v] = bool(ok) and names.get(w.bone_index, "").startswith(KEEP)
    dm, tlist, _gaps = Queries.get_all_triangle_indices(dm, False)
    tris = Lists.convert_triangle_list_to_array(tlist)
    drop = [i for i, t in enumerate(tris) if not (keep[t.x] and keep[t.y] and keep[t.z])]
    log("vertices", nv, "triangles", len(tris), "dropped", len(drop))
    dm, removed = dm.delete_triangles_from_mesh(Lists.convert_array_to_index_list(drop, unreal.GeometryScriptIndexType.TRIANGLE))
    dm = dm.remove_unused_vertices()
    dm = dm.compact_mesh()

    # the new asset: same skeleton, same two materials (by slot name)
    mats = {}
    for slot in src.get_editor_property("materials"):
        mats[slot.get_editor_property("material_slot_name")] = slot.get_editor_property("material_interface")
    opts = unreal.GeometryScriptCreateNewSkeletalMeshAssetOptions()
    opts.set_editor_property("materials", mats)
    opts.set_editor_property("enable_recompute_normals", False)
    opts.set_editor_property("enable_recompute_tangents", False)
    path = DST_DIR + "/" + DST_NAME
    if eal.does_asset_exist(path):
        eal.delete_asset(path)
    asset, outcome = NewAssets.create_new_skeletal_mesh_asset_from_mesh(dm, src.get_editor_property("skeleton"), path, opts)
    if asset is None or outcome != unreal.GeometryScriptOutcomePins.SUCCESS:
        raise RuntimeError("could not make the arms asset")
    # the arms move far from where the mesh stands in its reference pose (the component is placed by the weapon code): generous bounds so that it is never culled
    asset.set_editor_property("positive_bounds_extension", unreal.Vector(80.0, 80.0, 160.0))
    asset.set_editor_property("negative_bounds_extension", unreal.Vector(80.0, 80.0, 160.0))
    eal.save_loaded_asset(asset, only_if_is_dirty=False)
    log("made", path, "with", len(Lists.convert_triangle_list_to_array(Queries.get_all_triangle_indices(dm, False)[1])), "triangles")


try:
    main()
except Exception:
    import traceback
    unreal.log_error("[ARMS] " + traceback.format_exc())
