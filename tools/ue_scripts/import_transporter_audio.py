"""Import the Transporter Room's sounds (art/_cache/audio/SW_Xport_*.wav of the list below, made by tools/art/transporter_sounds.py) as SoundWaves in
/Game/ASTRA/Audio/Transporter, the hum flagged as looping. What the game does with them: AstraTransportFx.cpp (the charge-up, the dematerialization and the
rematerialization at the subject's feet, the lock's chirp, the fault's buzz, the pads' hum while a cycle runs). The game is tolerant of any of them being missing.
Run: uv run --with numpy --with soundfile --with scipy python tools/art/transporter_sounds.py
     tools/ue.py py "exec(open('tools/ue_scripts/import_transporter_audio.py').read())"
"""
import os

import unreal

ROOT = os.environ.get("ASTRA_ROOT", "/Users/beltromatti/Desktop/ASTRA")
SRC = globals().get("SRC", os.path.join(ROOT, "art", "_cache", "audio"))
DST = "/Game/ASTRA/Audio/Transporter"
NAMES = ["SW_Xport_Energize", "SW_Xport_Demat", "SW_Xport_Remat", "SW_Xport_Lock", "SW_Xport_Fault", "SW_Xport_Hum"]
LOOPS = {"SW_Xport_Hum"}

tasks = []
for name in NAMES:
    path = os.path.join(SRC, name + ".wav")
    if not os.path.exists(path):
        print("missing", path)
        continue
    t = unreal.AssetImportTask()
    t.filename = path
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
print("TRANSPORTER_AUDIO_OK", done)
