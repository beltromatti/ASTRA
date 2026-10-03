"""ABBORDAGGI: the Captain's arms for the weapons, /Game/ASTRA/Weapons/SKM_ASTRA_Arms.

The mannequin's mesh is a whole body. Held in front of a camera that rides on the Captain's eyes (and that places the arms so that the weapon sits where it should on the
screen), its head, shoulders and chest fill the view and the arms hang from them. What the weapons need is the arms alone: this cuts the mannequin down to the arms: the upper arm (to the shoulder joint),
the forearm and the hand with its fingers (every bone stays, so the mannequin's animations play on it unchanged and the hand sockets, which are the skeleton's,
are there), with the mannequin's own two materials. The arms are moved about on their own (UAstraFpsComponent solves them to the weapon from shoulders that stand below the picture),
so the vertices near the shoulder must follow the arm's bones alone: the few per cent of weight that the chest and the clavicles held there would drag them, once the arm is moved away from
them, into long spikes; their weight is given to the arm's own bones. Idempotent: the asset is made again each time.

Run in the editor: tools/ue.py pyfile tools/ue_scripts/make_fp_arms.py
"""
import unreal

SRC = "/Game/Characters/Mannequins/Meshes/SKM_Manny_Simple"
DST_DIR = "/Game/ASTRA/Weapons"
DST_NAME = "SKM_ASTRA_Arms"
# the bones whose skin stays (by their name's start): the whole upper arm (it ends at the shoulder joint: the clavicle and the chest stay out), the forearm with its twists, the hand and the fingers
KEEP = ("upperarm", "lowerarm", "hand", "index", "middle", "ring", "pinky", "thumb")

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

    # the skin follows the arm's bones alone: what the chest and the clavicles held on the vertices left goes to the arm's own bones (renormalised)
    dm, plist2, _gaps = Queries.get_all_vertex_positions(dm, False)
    nv2 = len(Lists.convert_vector_list_to_array(plist2))
    foreign = set()
    for v in range(nv2):
        dm, ws, ok = Bones.get_vertex_bone_weights(dm, v)
        for w in ws:
            if w.weight > 0.0 and not names.get(w.bone_index, "").startswith(KEEP):
                foreign.add(names.get(w.bone_index, ""))
    log("bones other than the arm's that held weight on the arms:", sorted(foreign))
    if foreign:
        dm = dm.prune_bone_weights([unreal.Name(n) for n in sorted(foreign)], unreal.GeometryScriptPruneBoneWeightsOptions())
    left = 0
    for v in range(nv2):
        dm, ws, ok = Bones.get_vertex_bone_weights(dm, v)
        left += 1 if (not ws or any(w.weight > 0.0 and not names.get(w.bone_index, "").startswith(KEEP) for w in ws)) else 0
    log("vertices whose skin is not the arm's alone after the fix:", left, "of", nv2)
    if left:
        raise RuntimeError("the arms' skin still holds weight on other bones")

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
