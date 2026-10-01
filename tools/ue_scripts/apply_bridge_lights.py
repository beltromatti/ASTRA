"""The bridge lights' reach (attenuation radius) as data/ship/aquila_bridge.json says now, applied to the lights already in the level
by their label, without rebuilding the bridge (build_bridge_v3.py builds them in the first place, with their lumens and shadows,
which this leaves as they are). Saves the level.
  tools/ue.py pyfile tools/ue_scripts/apply_bridge_lights.py
"""
import json

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
data = json.load(open(f"{ROOT}/data/ship/aquila_bridge.json"))
lights = data.get("lights") or data["lighting"]["lights"]
by_label = {a.get_actor_label(): a for a in eas.get_all_level_actors()}
done, missing = [], []
for ld in lights:
    a = by_label.get(ld["id"])
    c = a.get_component_by_class(unreal.LocalLightComponent) if a else None
    if not c:
        missing.append(ld["id"])
        continue
    c.set_editor_property("attenuation_radius", float(ld.get("radius", 1000.0)))
    done.append(ld["id"])
unreal.EditorLevelLibrary.save_current_level()
print(json.dumps({"applied": len(done), "missing": missing}))
