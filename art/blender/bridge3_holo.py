"""ASN Aquila bridge v3: the hover panels of the consoles (translucent, a separate classic mesh per station).

A hover panel is a flat plane facing the officer's eyes with its live page (SCREEN_<station>_<n>, UVs 0..1) and four lit corner
brackets; the physical emitter under it (a puck or a pair of masts) is part of the opaque console mesh. Positions are in the
console frame (officer at the origin on the floor, facing +X); polar (r, th): r metres from the officer, th degrees to the right.
"""
from __future__ import annotations

import os
import sys

from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import bridge3_lib as L  # noqa: E402
from bridge3_lib import FB, polar  # noqa: E402

EYE = {"helm": 1.24, "ops": 1.24, "comms": 1.24, "sensors": 1.24, "engineering": 1.24, "flight": 1.24, "tactical": 1.66}
DEPT_CELL = {"helm": "command", "ops": "command", "comms": "command", "sensors": "science", "engineering": "engineering",
             "flight": "flight", "tactical": "security"}

# slot number -> (r, th, z centre, width, aspect, mount)   mount: "puck" (on the work surface) or "mast" (two masts)
PANELS = {
    "helm": {1: (1.02, -34.0, 1.18, 0.62, 1.6, "puck"), 2: (1.02, 34.0, 1.18, 0.62, 1.6, "puck"), 3: (1.36, 0.0, 1.70, 0.64, 1.6, "mast")},
    "ops": {1: (1.02, -34.0, 1.18, 0.62, 1.6, "puck"), 2: (1.02, 34.0, 1.18, 0.62, 1.6, "puck"), 3: (1.36, 0.0, 1.70, 0.64, 1.6, "mast")},
    "comms": {2: (0.98, 38.0, 1.20, 0.56, 1.6, "puck")},
    "sensors": {2: (0.98, 38.0, 1.20, 0.56, 1.6, "puck")},
    "engineering": {2: (0.98, 38.0, 1.20, 0.56, 1.6, "puck")},
    "flight": {2: (0.98, 38.0, 1.20, 0.56, 1.6, "puck")},
    "tactical": {2: (0.86, 0.0, 1.36, 0.64, 1.6, "puck")},
}


def panel_center(kind: str, n: int) -> Vector:
    r, th, zc, _w, _asp, _mount = PANELS[kind][n]
    x, y = polar(0, 0, r, th)
    return Vector((x, y, zc))


def panel_basis(kind: str, n: int):
    """(centre, facing, right, up) of a panel in console coordinates: it faces the officer's eyes (a little flattened)."""
    c = panel_center(kind, n)
    facing = Vector((-c.x, -c.y, (EYE[kind] - c.z) * 0.55)).normalized()
    right = facing.cross(Vector((0, 0, 1)))                 # layout frame is left-handed: right = facing x up
    right = right.normalized() if right.length > 1e-6 else Vector((0, 1, 0))
    up = right.cross(facing).normalized()
    return c, facing, right, up


def build_holo_panels(kind: str, name: str):
    """Translucent hover panels of one console kind: planes with lit corner brackets."""
    fb = FB()
    infos = []
    dept = DEPT_CELL[kind]
    for n, (_r, _th, _zc, w, asp, _mount) in sorted(PANELS[kind].items()):
        c, facing, right, up = panel_basis(kind, n)
        h = w / asp
        slot = f"SCREEN_{kind}_{n}"
        fb.screen(tuple(c), w, h, slot, tuple(facing), up=(0, 0, 1))
        front = tuple(facing)
        for sx in (-1, 1):
            for sy in (-1, 1):
                p = c + right * (sx * w / 2) + up * (sy * h / 2) + facing * 0.002
                for (ax, ln, cross_ax, cross_sgn) in ((right, 0.07, up, sy), (up, 0.05, right, sx)):
                    inward = -sx if ax is right else -sy
                    a0 = p
                    a1 = p + ax * (inward * ln)
                    t = 0.006
                    d = cross_ax * (-cross_sgn * t)
                    fb.lamp_face([tuple(a0), tuple(a1), tuple(a1 + d), tuple(a0 + d)], dept, front, L.LAMP)
        infos.append({"screen": slot, "size_m": [round(w, 3), round(h, 3)], "surface": "hover", "center": [round(v, 3) for v in c]})
    return A.finish(fb.to_object(name), bevel=0.0), infos
