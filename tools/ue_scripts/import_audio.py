"""Import the ship's synthesised sounds (art/_cache/audio/*.wav, made by tools/art/ship_sounds.py) as SoundWaves in
/Game/ASTRA/Audio. Only the names in ONLY (a global, optional) are imported; loops are flagged.
Run: tools/ue.py py "ONLY=['SW_Sparks']; exec(open('tools/ue_scripts/import_audio.py').read())" """
import os

import unreal

SRC = "/Users/beltromatti/Desktop/ASTRA/art/_cache/audio"
DST = "/Game/ASTRA/Audio"
ONLY = globals().get("ONLY")
LOOPS = {"SW_Bridge_Ambience"}

tasks = []
for f in sorted(os.listdir(SRC)):
    name = os.path.splitext(f)[0]
    if not f.endswith(".wav") or (ONLY and name not in ONLY):
        continue
    t = unreal.AssetImportTask()
    t.filename = os.path.join(SRC, f)
    t.destination_path = DST
    t.destination_name = name
    t.automated = True
    t.replace_existing = True
    t.save = True
    tasks.append(t)
unreal.AssetToolsHelpers.get_asset_tools().import_asset_tasks(tasks)
done = []
for t in tasks:
    name = os.path.splitext(os.path.basename(t.filename))[0]
    sw = unreal.load_asset(f"{DST}/{name}")
    if sw and name in LOOPS:
        sw.set_editor_property("looping", True)
        unreal.EditorAssetLibrary.save_loaded_asset(sw, only_if_is_dirty=False)
    done.append((name, bool(sw), round(sw.get_editor_property("duration"), 2) if sw else None))
print(done)
