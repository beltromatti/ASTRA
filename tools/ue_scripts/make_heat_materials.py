"""The ASTRA radiators can glow: MI_HULL_A_Radiator becomes an emissive instance (dark panel, a dull red-orange heat
glow at Intensity 0 when cold). The game raises the glow on the Aquila's own radiators with her heat
(UAstraShipSubsystem, a dynamic instance on her hull); the other ASTRA ships keep them cold.
  tools/ue.py pyfile tools/ue_scripts/make_heat_materials.py
"""
import json

import unreal

eal = unreal.EditorAssetLibrary
mel = unreal.MaterialEditingLibrary
p = "/Game/ASTRA/Materials/Instances/MI_HULL_A_Radiator"
mi = eal.load_asset(p)
mel.set_material_instance_parent(mi, eal.load_asset("/Game/ASTRA/Materials/M_ASTRA_Emissive"))
for k, v in (("Intensity", 0.0), ("PulseSpeed", 0.0), ("PulseAmount", 0.0), ("AlertColorWeight", 0.0), ("LightDimWeight", 0.0),
             ("Roughness", 0.55)):
    mel.set_material_instance_scalar_parameter_value(mi, k, v)
mel.set_material_instance_vector_parameter_value(mi, "BaseColor", unreal.LinearColor(0.024, 0.027, 0.031, 1.0))
mel.set_material_instance_vector_parameter_value(mi, "EmissiveColor", unreal.LinearColor(1.0, 0.24, 0.05, 1.0))
mel.update_material_instance(mi)
eal.save_loaded_asset(mi, only_if_is_dirty=False)
print(json.dumps({"radiator": mi.get_editor_property("parent").get_name()}))
