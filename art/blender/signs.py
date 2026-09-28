"""SM_SIGN_Plate: a 1 m x 1 m backlit sign, its lit face looking +X (UV 0..1 across the face, text readable from the
front), a thin dark frame and back. Placed and scaled in Unreal (tools/ue_scripts/place_signage.py).

blender -b --factory-startup --python-exit-code 1 -P art/blender/signs.py -- art/export/signs
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
from mathutils import Matrix  # noqa: E402

FACE = "MI_SIGN_Face"
FRAME = A.MAT_STRUCTURE


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    out = argv[0] if argv else "art/export/signs"
    A.reset_scene()
    b = A.Builder()
    # the frame and back: a shallow tray 1.0 x 1.0 m, 3 cm deep, behind the face
    b.box((-0.02, 0, 0), (0.03, 1.04, 1.04), FRAME)
    # the lit face, 1 x 1 m at x = 0, facing +X: a quad with its own UVs (u to the viewer's right, v down)
    b.screen(Matrix.Translation((0.002, 0, 0)) @ Matrix.Diagonal((0.004, 1.0, 1.0, 1.0)), FACE)
    obj = b.to_object("SM_SIGN_Plate")
    A.export_fbx(obj, os.path.join(out, "SM_SIGN_Plate.fbx"))
    print("SIGNS_OK", A.stats(obj))


if __name__ == "__main__":
    main()
