"""ASN Aquila: painted and inlaid marks on the bridge v3 toolkit (ARTE-PLANCIA-2): rings, the compass star and the ASTRA Navy roundel, as flat geometry on a surface (the Falcon's wings and
nose, the Captain's quarters' walls). All of it goes to the builder it is given, in the frame the caller stands in; the faces look towards `facing`, the picture's up is `up`.
"""
from __future__ import annotations

import math
import os
import sys

from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bridge3_lib import FB  # noqa: E402


def _basis(facing, up):
    f = Vector(facing).normalized()
    u = Vector(up) - f * Vector(up).dot(f)
    u = u.normalized()
    return f, u, f.cross(u)


def annulus(fb: FB, c, r0: float, r1: float, mat: str, facing, up, seg: int = 36) -> None:
    """A flat ring (r0 inside, r1 outside) round `c`, lying on a surface with its face towards `facing`."""
    f, u, r_ = _basis(facing, up)
    for k in range(seg):
        a0, a1 = 2 * math.pi * k / seg, 2 * math.pi * (k + 1) / seg
        pts = [tuple(Vector(c) + (r_ * math.cos(a) + u * math.sin(a)) * r) for (a, r) in ((a0, r0), (a1, r0), (a1, r1), (a0, r1))]
        fb.face(pts, mat, tuple(f))


def disc(fb: FB, c, r: float, mat: str, facing, up, seg: int = 36) -> None:
    """A flat disc of radius r round `c`."""
    f, u, r_ = _basis(facing, up)
    fb.face([tuple(Vector(c) + (r_ * math.cos(2 * math.pi * k / seg) + u * math.sin(2 * math.pi * k / seg)) * r) for k in range(seg)], mat, tuple(f))


def compass_star(fb: FB, c, r: float, mat: str, facing, up, long_: float = 0.74, short: float = 0.50, width: float = 0.085) -> None:
    """The ASTRA compass star: four long points (up and down, left and right), four short ones between them, as kites."""
    f, u, r_ = _basis(facing, up)
    c = Vector(c)
    for k in range(8):
        a = math.radians(45.0 * k)
        d = u * math.cos(a) + r_ * math.sin(a)
        side = f.cross(d)
        ln = r * (long_ if k % 2 == 0 else short)
        wd = r * width if k % 2 == 0 else r * width * 0.8
        fb.face([tuple(c), tuple(c + d * ln * 0.28 - side * wd), tuple(c + d * ln), tuple(c + d * ln * 0.28 + side * wd)], mat, tuple(f))


def emblem(fb: FB, c, r: float, mat: str, facing, up) -> None:
    """The ASTRA Navy roundel painted on a surface: a double ring and the compass star."""
    annulus(fb, c, r * 0.90, r, mat, facing, up)
    annulus(fb, c, r * 0.80, r * 0.84, mat, facing, up)
    compass_star(fb, c, r, mat, facing, up)
