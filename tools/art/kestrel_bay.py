"""Blender: export the bay and its two separate, movable parked Kestrels. Run from the repository root."""
from pathlib import Path
import sys
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root / 'art/blender'))
import astra_bpy as A
import ship_lib as SL
import ship_craft as C
import ship_rooms_security as R
SL.load_labels()
out = root / 'art/export/ship'
out.mkdir(parents=True, exist_ok=True)
A.clear_objects()
bay = R.shuttle_bay()
A.export_fbx(bay, str(out / 'SM_SHIP_ShuttleBay.fbx'))
for i, side in enumerate((-1, 1), 1):
    A.clear_objects()
    parts = SL.SParts(bevel=0.005, fine_bevel=0.0)
    C.kestrel(parts, side, f'eq_k{i}')
    name = f'SM_SHIP_KestrelParked{i}'
    craft = parts.build(name)
    A.export_fbx(craft, str(out / (name + '.fbx')))
    print(name, A.stats(craft))

A.clear_objects()
parts = SL.SParts(bevel=0.005, fine_bevel=0.0)
parts.body.box((0.0, -2.27, 0.05), (0.14, 2.27, 3.31), SL.CRATE_GREY)
for z in (0.8, 1.6, 2.4):
    parts.body.box((0.14, -2.23, z), (0.18, 2.23, z + 0.07), SL.STRUCT)
parts.emit.label((0.185, 0.0, 3.11), 4.3, 0.2, (1, 0, 0), 'hazard_h')
leaf = parts.build('SM_SHIP_KestrelDoor')
A.export_fbx(leaf, str(out / 'SM_SHIP_KestrelDoor.fbx'))
