"""Bridge v3 layout, shared by the Blender generator (art/blender/bridge_v3.py: manifest and preview) and the Unreal build
script (tools/ue_scripts/build_bridge_v3.py): one place that turns data/ship/aquila_bridge.json into the list of placements.
Pure Python (no bpy, no unreal). Frame: Unreal (X forward, Y starboard, Z up), metres, yaw in degrees toward +Y.
"""
from __future__ import annotations

import json
import math
import os

PREFIX = "SM_BRG3_"

ENV_MESHES = ["Deck", "WallPort", "WallStarboard", "WallBack", "Ceiling", "Window", "WindowGlass", "Rails", "RailGlass",
              "ViewscreenFrame", "ViewscreenImage"]
# meshes with a translucent slot stay classic (no Nanite): see the Nanite notes in docs/STATO.md
TRANSLUCENT = {"WindowGlass", "RailGlass", "ViewscreenImage"}


def load(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def level_z(D: dict, name: str) -> float:
    return float(D["levels"][name])


def placements(D: dict) -> list[dict]:
    """Every static mesh actor of the bridge: mesh, position (x, y, z metres), yaw, label, folder, station."""
    out: list[dict] = []
    for n in ENV_MESHES:
        out.append({"mesh": PREFIX + n, "pos": [0.0, 0.0, 0.0], "yaw": 0.0, "label": f"Bridge_{n}", "folder": "Bridge"})
    md = D["master_display"]
    out.append({"mesh": PREFIX + "MasterDisplay", "pos": [md["pos"][0], md["pos"][1], 0.0], "yaw": 0.0, "label": "MasterDisplay",
                "folder": "Bridge"})
    ht = D["holo_table"]
    out.append({"mesh": PREFIX + "HoloTable", "pos": [ht["pos"][0], ht["pos"][1], level_z(D, ht.get("level", "well"))], "yaw": 0.0,
                "label": "HoloTable", "folder": "Bridge"})
    for st in D["stations"]:
        z = level_z(D, st["level"])
        x, y = st["pos"]
        base = {"pos": [x, y, z], "yaw": float(st["yaw"]), "station": st["id"], "folder": "Bridge/Stations"}
        if st.get("mesh"):       # the console (or, for the command chairs, the chair itself)
            out.append(dict(base, mesh=st["mesh"], label=f"Station_{st['id']}_" + ("Console" if st.get("type") else "Chair")))
        if st.get("chair"):
            out.append(dict(base, mesh=st["chair"], label=f"Station_{st['id']}_Chair"))
        if st.get("holo"):
            out.append(dict(base, mesh=st["holo"], label=f"Station_{st['id']}_Holo"))
    for p in D.get("props", []):
        out.append({"mesh": p["mesh"], "pos": [p["pos"][0], p["pos"][1], level_z(D, p["level"])], "yaw": float(p.get("yaw", 0.0)),
                    "label": f"Prop_{p['id']}", "folder": "Bridge/Props"})
    return out


def is_translucent(mesh_name: str) -> bool:
    n = mesh_name[len(PREFIX):] if mesh_name.startswith(PREFIX) else mesh_name
    return n in TRANSLUCENT or n.startswith("Holo") and n != "HoloTable"


def kelvin_to_rgb(k: float) -> tuple[float, float, float]:
    """Approximate sRGB colour (0..1) of a black body at k kelvin (Tanner Helland)."""
    t = max(1000.0, min(40000.0, k)) / 100.0
    if t <= 66:
        r = 255.0
        g = 99.4708025861 * math.log(t) - 161.1195681661
    else:
        r = 329.698727446 * ((t - 60) ** -0.1332047592)
        g = 288.1221695283 * ((t - 60) ** -0.0755148492)
    if t >= 66:
        b = 255.0
    elif t <= 19:
        b = 0.0
    else:
        b = 138.5177312231 * math.log(t - 10) - 305.0447927307
    return tuple(max(0.0, min(255.0, v)) / 255.0 for v in (r, g, b))


def direction_to_pitch_yaw(d) -> tuple[float, float]:
    """Unreal pitch / yaw (degrees) of a forward vector."""
    n = math.sqrt(d[0] ** 2 + d[1] ** 2 + d[2] ** 2)
    x, y, z = d[0] / n, d[1] / n, d[2] / n
    return math.degrees(math.asin(z)), math.degrees(math.atan2(y, x))
