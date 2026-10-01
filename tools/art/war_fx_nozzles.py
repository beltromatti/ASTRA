"""Where the drive bells of every ship are, for the engine plumes of the war's visual effects (AstraWarFX).

Runs the ship generators (art/blender/shipgen3.py) with a spy on the drive-bell builder: nothing is exported and the hulls are
built with almost no scattered detail, so it takes about a minute. For every ship it records the bells (their throat centre, the
direction the exhaust leaves along, the throat radius, the lip's distance from the throat) in the ship's own frame as the game
sees it (x forward, y starboard, z up: the FBX export mirrors Blender's y, so y is negated here), in metres, and writes
data/war/fx_nozzles.json. tools/art/war_fx_data.py turns that and the break-up manifest into Source/ASTRA/AstraWarFXData.inl.

  /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python-exit-code 1 -P tools/art/war_fx_nozzles.py
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "art", "blender"))

import bpy  # noqa: E402,F401  (the generators import it)
import numpy as np  # noqa: E402

import ship3_kit2 as K2  # noqa: E402
import shipgen3 as SG  # noqa: E402

OUT = os.path.join(ROOT, "data", "war", "fx_nozzles.json")
BELL_LIP = 2.14          # the lip of a bell stands this many throat radii down the exhaust from the origin (ship3_kit2.engine_nozzle)

records: list[dict] = []


def spy(c, xf, R, style="astra", detail=1):
    """Stands in for ship3_kit2.engine_nozzle: notes the bell, builds nothing."""
    o = np.asarray(xf.o, np.float64)
    d = np.asarray(xf.R, np.float64)[2]                 # local +z (the exhaust direction) in the ship frame: row 2 of the row basis
    d = d / max(np.linalg.norm(d), 1e-9)
    r = float(R) * float(xf.s)
    records.append({"pos": [round(float(o[0]), 3), round(float(-o[1]), 3), round(float(o[2]), 3)],
                    "dir": [round(float(d[0]), 4), round(float(-d[1]), 4), round(float(d[2]), 4)],
                    "r": round(r, 3), "lip": round(BELL_LIP * r, 3), "detail": int(detail)})


def main() -> None:
    K2.engine_nozzle = spy                                # engine_bank and the craft builders call it through the module
    reg = SG.registry()
    args = {"seed": 0, "detail": 0.02, "export": False, "pieces": False}
    result: dict = {}
    for name, spec in reg.items():
        records.clear()
        try:
            SG.build_ship(name, spec, args)
        except Exception as ex:                            # one ship failing must not lose the others
            print(f"{name}: FAILED {ex!r}")
            continue
        bells = [dict(r) for r in records]
        # main drive bells: aft-facing, and not the little attitude-thruster bells (detail 0)
        main_bells = [b for b in bells if b["dir"][0] < -0.5 and b["detail"] > 0] or [b for b in bells if b["dir"][0] < -0.5]
        thrusters = [b for b in bells if b not in main_bells]
        result[name] = {"main": main_bells, "thrusters": thrusters}
        print(f"{name}: {len(main_bells)} drive bells, {len(thrusters)} thruster bells")
        for b in main_bells[:3]:
            print("    ", b)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"_doc": "Drive bells per ship mesh, ship frame (x forward, y starboard, z up), metres; tools/art/war_fx_nozzles.py",
                   "ships": result}, fh, indent=1)
    print("written", OUT)
    print("WAR_FX_NOZZLES_OK")


if __name__ == "__main__":
    main()
