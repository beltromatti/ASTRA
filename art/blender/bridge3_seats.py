"""ASN Aquila bridge v3: the seats. Sculpted shells on column bases, no castors, no office chairs.

A shell is a lofted surface: a side profile (seat pan curving up into the backrest and the headrest) with a width law and side
bolsters, thickened into a closed solid; the backrest is split into panels with thin gaps, a shark-fin spine rises behind it
and carries a light line in the department colour; the leather cushions are inset lofts on top. Origin = seat centre on the
floor, facing +X. The crew seat surface is at 0.50 m (their hips sit at 0.62 m); the command chairs (the Captain's, the XO's)
have slim armrest pods with live touch screens (SCREEN_captain_1/2, SCREEN_xo_1).
"""
from __future__ import annotations

import math
import os
import sys

from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge3_controls as K  # noqa: E402
import bridge3_lib as L  # noqa: E402
from bridge3_lib import Parts, Ry, T  # noqa: E402


def catmull(points, n_per: int = 6):
    """Catmull-Rom spline through 2D points (open curve), n_per samples per span."""
    pts = [Vector(p) for p in points]
    ext = [pts[0] * 2 - pts[1]] + pts + [pts[-1] * 2 - pts[-2]]
    out = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        for k in range(n_per):
            t = k / n_per
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(pts[-1])
    return [(v.x, v.y) for v in out]


def interp_table(table, t: float) -> float:
    """Smoothstep-blended piecewise lookup in [(t0, v0), (t1, v1), ...]."""
    if t <= table[0][0]:
        return table[0][1]
    for (t0, v0), (t1, v1) in zip(table[:-1], table[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            f = f * f * (3 - 2 * f)
            return v0 + (v1 - v0) * f
    return table[-1][1]


def shell_rings(profile, width_tab, bolster_tab, nv: int, thick: float, v_span: float = 1.0, lift: float = 0.0, span=(0.0, 1.0)):
    """Rings for FB.loft: each ring is a closed loop (front surface across the width, then the back surface returning).
    The front surface is `lift` above the profile, the back one `lift - thick`; the width and the bolsters follow the tables."""
    n = len(profile)
    rings = []
    for i in range(n):
        t = i / (n - 1)
        if not (span[0] - 1e-9 <= t <= span[1] + 1e-9):
            continue
        p = Vector(profile[i])
        pa, pb = Vector(profile[max(i - 1, 0)]), Vector(profile[min(i + 1, n - 1)])
        tan = (pb - pa).normalized()
        nrm = Vector((-tan.y, tan.x))                              # towards the sitter (front / up)
        if nrm.x < 0 and nrm.y < 0.2:
            nrm = -nrm
        w = interp_table(width_tab, t)
        bo = interp_table(bolster_tab, t)
        front, back = [], []
        for j in range(nv):
            v = -v_span + 2 * v_span * j / (nv - 1)
            off = bo * (v * v)
            q = p + nrm * (off + lift)
            front.append((q.x, v * w, q.y))
            qb = p + nrm * (off + lift - thick * (1.0 - 0.35 * v * v))
            back.append((qb.x, v * w * 0.985, qb.y))
        rings.append(front + list(reversed(back)))
    return rings


def chair_shell_parts(b: Parts, scale: float = 1.0, command: bool = False, captain: bool = False, dept: str = "command") -> None:
    """The shell, the cushions, the fin and the column of a seat. `command`: taller, wider, wing bolsters, ivory shell;
    crew seats have a gunmetal shell with an ivory shoulder band. `captain`: the tallest."""
    fb, fine, em, soft = b.body, b.fine, b.emit, b.soft
    s = scale
    top = 1.30 if not command else (1.52 if captain else 1.42)
    ctrl = [(0.31, 0.470), (0.24, 0.478), (0.08, 0.468), (-0.10, 0.468), (-0.19, 0.500), (-0.245, 0.610), (-0.275, 0.760),
            (-0.290, 0.920), (-0.285, 1.070), (-0.270, 1.190), (-0.255, 1.30)]
    ctrl = [(x * s, z) for x, z in ctrl]
    ctrl = [(x, z if z <= 0.5 else 0.5 + (z - 0.5) * (top - 0.5) / 0.80) for x, z in ctrl]
    prof = catmull(ctrl, 5)
    wtab = [(0.0, 0.225 * s), (0.20, 0.235 * s), (0.42, 0.230 * s), (0.55, 0.205 * s), (0.72, 0.235 * s), (0.86, 0.255 * s),
            (1.0, (0.16 if not command else 0.24) * s)]
    btab = [(0.0, 0.020), (0.3, 0.045), (0.45, 0.04), (0.6, 0.06), (0.85, 0.10 if command else 0.075), (1.0, 0.11 if command else 0.06)]
    base_mat = L.IVORY if command else L.STRUCT
    band_mat = L.IVORY if command else L.STRUCT
    # the shell in three panels with hairline gaps: seat + lumbar, shoulders, the headrest crown
    fb.loft(shell_rings(prof, wtab, btab, 15, 0.038, span=(0.0, 0.60)), base_mat, caps=True)
    fb.loft(shell_rings(prof, wtab, btab, 15, 0.038, span=(0.625, 0.885)), band_mat, caps=True)
    fb.loft(shell_rings(prof, wtab, btab, 13, 0.038, span=(0.905, 1.0)), base_mat, caps=True)
    # leather cushions: the seat in two segments, one long back cushion with two stitched grooves, a headrest pad
    pads = [((0.04, 0.27), 0.93), ((0.29, 0.50), 0.93), ((0.55, 0.885), 0.92)]
    for (sp, vs) in pads:
        soft.loft(shell_rings(prof, [(t, w * 0.96) for t, w in wtab], btab, 13, 0.05, v_span=vs, lift=0.054, span=sp), L.LEATHER, caps=True)
    soft.loft(shell_rings(prof, [(0.0, 0.14 * s), (1.0, 0.14 * s)], [(0.0, 0.03), (1.0, 0.03)], 11, 0.045, v_span=0.70, lift=0.049,
                          span=(0.925, 0.99)), L.LEATHER, caps=True)
    for z in (0.79, 0.94):                                       # stitched grooves across the back cushion
        zz = z * (top / 1.30) if not command else z * (top / 1.30)
        fine.box((-0.262 * s - 0.03 * (zz - 0.79), -0.19 * s, zz), (-0.226 * s, 0.19 * s, zz + 0.006), L.STRUCT)
    # the shark-fin spine behind the shell: a slim plate with a lit rear edge in the department colour
    z0f, zt = 0.60, top - 0.05
    fin = [(-0.285 * s, z0f), (-0.36 * s, z0f + 0.03), (-0.415 * s, z0f + 0.25), (-0.385 * s, (z0f + zt) / 2 + 0.12), (-0.30 * s, zt),
           (-0.275 * s, zt - 0.1)]
    fb.extrude_y(fin, -0.017, 0.017, L.STRUCT if command else L.TRIM)
    em.lamp_cbox((-0.395 * s, 0.0, (z0f + zt) / 2 - 0.02), (0.008, 0.024, (zt - z0f) * 0.7), dept, L.LAMP, Ry(-4))
    for z in (0.66, 0.86, 1.06):                                # clamp bands round the fin
        if z < zt - 0.05:
            fb.box((-0.36 * s - 0.01 * (z - 0.6), -0.024, z - 0.02), (-0.31 * s, 0.024, z + 0.02), L.TRIM)
    # the back of the shell: panel grooves across, rivets, a release handle with a warning lamp
    for zz in (0.72, 0.90, 1.08):
        if zz < top - 0.1:
            fine.box((-0.30 * s - 0.028 * (zz - 0.6) - 0.004, -0.23 * s, zz), (-0.278 * s - 0.028 * (zz - 0.6), 0.23 * s, zz + 0.005), L.STRUCT)
    for sd in (-1, 1):
        for zz in (0.68, 0.98):
            if zz < top - 0.12:
                for yy in (0.09, 0.19):
                    fine.cyl((-0.315 * s - 0.03 * (zz - 0.6), sd * yy * s, zz), (-0.325 * s - 0.03 * (zz - 0.6), sd * yy * s, zz), 0.009, L.TRIM, seg=8)
    fine.box((-0.372 * s - 0.03, -0.045, 0.795), (-0.352 * s - 0.03, 0.045, 0.83), L.RUBBER)
    em.lamp_box((-0.3735 * s - 0.03, -0.03, 0.833), (-0.372 * s - 0.03, 0.03, 0.842), "amber", L.LAMP_DIM)
    # harness: rings at the shoulders, folded straps down the shell sides with buckles
    for sd in (-1, 1):
        zr = 0.95 * (top / 1.30)
        fine.cyl((-0.27 * s, sd * 0.25 * s, zr), (-0.27 * s, sd * 0.285 * s, zr), 0.017, L.TRIM, seg=12)
        fine.box((-0.318 * s, sd * 0.238 * s - 0.021, 0.50), (-0.30 * s, sd * 0.238 * s + 0.021, zr - 0.06), L.RUBBER)
        fine.box((-0.325 * s, sd * 0.238 * s - 0.029, 0.60), (-0.295 * s, sd * 0.238 * s + 0.029, 0.68), L.TRIM)
    # suspension: two angled dampers from the column collar up to the seat shell, a swivel ring
    for sd in (-1, 1):
        fine.cyl((0.0, sd * 0.06, 0.40), (-0.08 * s, sd * 0.20 * s, 0.48), 0.014, L.TRIM, seg=10)
        fine.cyl((0.0, sd * 0.06, 0.40), (-0.04 * s, sd * 0.13 * s, 0.44), 0.020, L.STRUCT, seg=10)
    # column base: a flared floor plate, the stem, a collar under the seat, a footrest ring on spokes (crew)
    base_r = 0.30 * s * (1.25 if command else 1.0)
    fb.cyl((0, 0, 0.0), (0, 0, 0.05), base_r, L.STRUCT, seg=36, r2=base_r * 0.62)
    fb.cyl((0, 0, 0.05), (0, 0, 0.40), 0.07 * s, L.TRIM, seg=24, r2=0.055 * s)
    fb.cyl((0, 0, 0.36), (0, 0, 0.445), 0.16 * s, L.STRUCT, seg=32, r2=0.19 * s)
    fb.cyl((0, 0, 0.445), (0, 0, 0.462), 0.215 * s, L.TRIM, seg=32)
    em.lamp_cyl((0, 0, 0.0), (0, 0, 0.004), base_r + 0.006, dept + "_dim", L.LAMP_DIM, seg=36)
    if not command:
        fine.arc_sweep([(-0.012, -0.012), (0.012, -0.012), (0.012, 0.012), (-0.012, 0.012)], 0, 0, 0.30 * s, 0, 360, L.TRIM, seg=40, z0=0.20, loop=True)
        for k in range(4):
            a = math.radians(45 + 90 * k)
            fine.cyl((0.06 * math.cos(a), 0.06 * math.sin(a), 0.20), (0.30 * s * math.cos(a), 0.30 * s * math.sin(a), 0.20), 0.011, L.TRIM, seg=8)


def build_chair_crew(name: str = "SM_BRG3_ChairCrew"):
    b = Parts(bevel=0.006, fine_bevel=0.003)
    chair_shell_parts(b, 1.0, command=False)
    # short seat-side armrest pads on posts (the hands work on the console; these are for resting between orders)
    for sd in (-1, 1):
        b.fine.box((-0.05, sd * 0.285 - 0.025, 0.50), (0.14, sd * 0.285 + 0.025, 0.505), L.RUBBER)
        b.fine.box((-0.02, sd * 0.285 - 0.012, 0.44), (0.03, sd * 0.285 + 0.012, 0.50), L.TRIM)
    return b.build(name, uv_meter=0.25)


def armrest_pod(b: Parts, sd: int, slot: str | None, dept: str, scale: float = 1.0) -> dict | None:
    """A command chair's armrest: a slim sculpted pod on a swept arm, with a touch screen and a small control cluster."""
    fb, fine, em = b.body, b.fine, b.emit
    y0 = sd * 0.335 * scale
    top = 0.755
    x0, x1 = -0.16, 0.34
    prof = [(x0, 0.655), (x0, top + 0.025), (x1 - 0.12, top + 0.01), (x1, top - 0.03), (x1, 0.665), (0.0, 0.645)]
    fb.extrude_y(prof, y0 - 0.088, y0 + 0.088, L.COMPOSITE)
    fb.extrude_y([(x0 + 0.01, top + 0.012), (x0 + 0.01, top + 0.03), (x1 - 0.12, top + 0.014), (x1 - 0.005, top - 0.026), (x1 - 0.005, top - 0.034),
                  (x1 - 0.12, top + 0.004)], y0 - 0.091, y0 + 0.091, L.IVORY)
    fb.box((x0 + 0.045, y0 - 0.076, top + 0.004), (x1 - 0.13, y0 + 0.076, top + 0.012), L.DGLASS)
    em.lamp_box((x0 + 0.03, y0 + sd * 0.089, top - 0.05), (x1 - 0.05, y0 + sd * 0.093, top - 0.038), dept, L.LAMP)
    info = None
    if slot:
        w, h = 0.21, 0.13
        cx = (x0 + x1 - 0.13) / 2 + 0.005
        b.emit.screen((cx, y0, top + 0.0135), w, h, slot, (0, 0, 1), up=(1, 0, 0))
        info = {"screen": slot, "size_m": [w, h], "surface": "armrest"}
    with b.at(T(x1 - 0.07, y0, top - 0.024) @ Ry(-8)):
        for k in range(-2, 3):
            K.key(fine, em, 0.0, k * 0.026, "cyan" if k else "amber", 0.019)
    # the swept arm from the seat side up to the pod, with a pivot ring
    fb.extrude_y([(-0.12, 0.47), (-0.03, 0.47), (0.06, 0.655), (-0.04, 0.655)], y0 - sd * 0.075 - 0.016, y0 - sd * 0.075 + 0.016, L.STRUCT)
    fb.cyl((-0.08, y0 - sd * 0.06, 0.585), (-0.08, y0 - sd * 0.10, 0.585), 0.026, L.TRIM, seg=14)
    return info


def build_chair_command(name: str, captain: bool, screens: list[str]):
    """The Captain's chair (captain=True) or the XO's: taller shell, wing bolsters, armrest pods, a heavy lit pedestal."""
    b = Parts(bevel=0.007, fine_bevel=0.0035)
    scale = 1.10 if captain else 0.98
    chair_shell_parts(b, scale, command=True, captain=captain)
    infos = []
    for i, sd in enumerate((-1, 1)):
        slot = screens[i] if i < len(screens) else None
        info = armrest_pod(b, sd, slot, "command", scale)
        if info:
            infos.append(info)
    # a name plate on the back of the chair (towards the tactical officer behind it)
    b.body.label((-0.40 * scale, 0.0, 0.82), 0.44, 0.055, (-1, 0, 0), "st_captain" if captain else "st_xo", up=(0, 0, 1))
    return b.build(name, uv_meter=0.25), infos
