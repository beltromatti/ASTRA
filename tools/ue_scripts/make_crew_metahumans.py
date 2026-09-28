"""The bridge crew as MetaHumans (UE 5.8 MetaHuman Creator in the editor, driven from Python).

Each officer starts from an Epic preset chosen for their name, age and origin, gets their own skin, eyes and build, is
auto-rigged (Epic's cloud service: needs the user's Epic account authorised in the editor once — see docs/RICHIESTE.md)
and assembled with the Optimized pipeline into /Game/ASTRA/Crew/MetaHumans/Built/<name>.

tools/ue.py pyfile tools/ue_scripts/make_crew_metahumans.py        (ONLY=MH_Serra,MH_Ferri to limit)
"""
import json
import time

import unreal

eal = unreal.EditorAssetLibrary
s = unreal.get_editor_subsystem(unreal.MetaHumanCharacterEditorSubsystem)
DIR = "/Game/ASTRA/Crew/MetaHumans"
BUILT = "/Game/ASTRA/Crew/MetaHumans/Built"
PRESETS = "/MetaHumanCharacter/Optional/Presets"

# station: (asset, preset, skin (lightness, redness), eyes (temperature, brightness), body)
CREW = {
    "xo": ("MH_Serra", "Jelena", (0.32, 0.55), (0.75, 0.35), dict(masculine_feminine=0.85, fat=0.3, muscularity=0.5, height_cm=171)),
    "helm": ("MH_Ferri", "Lorenzo", (0.38, 0.6), (0.85, 0.25), dict(masculine_feminine=0.15, fat=0.3, muscularity=0.6, height_cm=178)),
    "ops": ("MH_Tanaka", "Aoi", (0.3, 0.5), (0.9, 0.15), dict(masculine_feminine=0.9, fat=0.3, muscularity=0.4, height_cm=160)),
    "tactical": ("MH_Voss", "Grace", (0.15, 0.6), (0.2, 0.7), dict(masculine_feminine=0.78, fat=0.25, muscularity=0.7, height_cm=174)),
    "comms": ("MH_Martin", "Cameron", (0.22, 0.65), (0.35, 0.6), dict(masculine_feminine=0.2, fat=0.3, muscularity=0.45, height_cm=176)),
    "sensors": ("MH_Nair", "Sunita", (0.6, 0.55), (0.9, 0.2), dict(masculine_feminine=0.88, fat=0.3, muscularity=0.4, height_cm=163)),
    "engineering": ("MH_Mensah", "Isaiah", (0.88, 0.5), (0.9, 0.15), dict(masculine_feminine=0.15, fat=0.35, muscularity=0.6, height_cm=180)),
    "flight": ("MH_Price", "Bruce", (0.2, 0.62), (0.25, 0.65), dict(masculine_feminine=0.12, fat=0.25, muscularity=0.65, height_cm=182)),
}
ONLY = [n for n in globals().get("ONLY", "").split(",") if n]
report = []


def body(ch, params):
    cons = s.get_body_constraints(character=ch, scale_measurement_ranges_with_height=False)
    names = {"masculine_feminine": "Masculine/Feminine", "fat": "Fat", "muscularity": "Muscularity", "height_cm": "Height"}
    by = {str(c.name): c for c in cons}
    for k, v in params.items():
        c = by.get(names[k])
        if not c:
            continue
        c.is_active = True
        lo, hi = float(c.min_measurement), float(c.max_measurement)
        c.target_measurement = min(max(v, lo), hi) if k == "height_cm" else lo + (hi - lo) * min(max(v, 0.0), 1.0)
    s.set_body_constraints(character=ch, body_constraints=list(by.values()))
    s.commit_body_state(character=ch)
    unreal.MetaHumanGeneratorSubsystemWrapper.reset_neck_to_body(ch)


for station, (name, preset, skin, eyes, build) in CREW.items():
    if ONLY and name not in ONLY:
        continue
    path = f"{DIR}/{name}"
    ch = eal.load_asset(path) if eal.does_asset_exist(path) else eal.duplicate_asset(f"{PRESETS}/{preset}", path)
    if not ch or not s.try_add_object_to_edit(character=ch):
        report.append({"crew": name, "error": "cannot open for editing"})
        continue
    try:
        ss = ch.skin_settings
        ss.skin.u, ss.skin.v = skin
        s.commit_skin_settings(character=ch, skin_settings=ss)
        es = ch.eyes_settings
        for eye in (es.eye_left, es.eye_right):
            eye.iris.primary_color_u = eye.iris.secondary_color_u = eyes[0]
            eye.iris.primary_color_v = eye.iris.secondary_color_v = eyes[1]
        s.commit_eyes_settings(character=ch, eyes_settings=es)
        body(ch, build)
        if not s.can_build_meta_human(ch, False):
            params = unreal.MetaHumanCharacterAutoRiggingRequestParams()
            params.blocking = True
            s.request_auto_rigging(ch, params)
            t0 = time.time()
            while not s.can_build_meta_human(ch, False) and time.time() - t0 < 240:
                time.sleep(2)
        if not s.can_build_meta_human(ch, True):
            report.append({"crew": name, "error": "not rigged (authorise the Epic account in the editor: docs/RICHIESTE.md)"})
            continue
        bp = unreal.MetaHumanCharacterEditorBuildParameters()
        bp.pipeline_type = unreal.MetaHumanDefaultPipelineType.OPTIMIZED
        bp.pipeline_quality = unreal.MetaHumanQualityLevel.MEDIUM
        bp.name_override = name
        s.build_meta_human(ch, bp)
        eal.save_loaded_asset(ch, only_if_is_dirty=False)
        report.append({"crew": name, "station": station, "preset": preset, "built": True})
    finally:
        s.remove_object_to_edit(ch)
print(json.dumps(report, indent=1))
