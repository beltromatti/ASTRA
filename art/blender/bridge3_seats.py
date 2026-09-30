"""ASN Aquila bridge v3: the seats. Monocoque shells on pedestals: no castors, no office chairs.

A seat is a few lofted parts along one side profile (seat pan curving up into the backrest): every part is a chain of rounded
"bean" sections (superellipses: a broad front, a soft rim, a thinner back), so the shell has no sharp slab edges and closes with
rounded ends. The seat pan and the back are separate shell parts with a hairline gap, the leather cushions sit on the front, a
carbon inset panel sits on the back, a fin with a light line rises behind. The command chairs (the Captain's, the XO's) are ivory
with slim sculpted armrest pods holding live touch screens (SCREEN_captain_1/2, SCREEN_xo_1); the crew seats are gunmetal.

Origin = seat centre on the floor, facing +X. The cushion top is at 0.525 m (the officers' hips sit at 0.62 m).
"""
from __future__ import annotations

import math
import os
import sys

from mathutils import Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge3_controls as K  # noqa: E402
import bridge3_lib as L  # noqa: E402
from bridge3_lib import Parts, Rx, Ry, Rz, T  # noqa: E402


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


def sgnpow(x: float, p: float) -> float:
    return math.copysign(abs(x) ** p, x) if x else 0.0


# ------------------------------------------------------------------------------------------------------------- the profile
class Profile:
    """The side profile of the sitter-facing surface: the seat from its front edge to the rear corner, then the back up to the
    top. Parts are cut by a fraction (0..1) of the seat length or of the back length."""

    def __init__(self, ctrl, corner_index: int, n_per: int = 8) -> None:
        self.pts = [Vector(p) for p in catmull(ctrl, n_per)]
        self.u = [0.0]
        for a, b in zip(self.pts[:-1], self.pts[1:]):
            self.u.append(self.u[-1] + (b - a).length)
        self.u_corner = self.u[corner_index * n_per]
        self.u_end = self.u[-1]

    def u_of(self, kind: str, g: float) -> float:
        return g * self.u_corner if kind == "seat" else self.u_corner + g * (self.u_end - self.u_corner)

    def at(self, u: float):
        """(point, unit tangent, unit normal towards the sitter) at arc length u."""
        u = max(0.0, min(self.u_end, u))
        i = 0
        while i < len(self.u) - 2 and self.u[i + 1] < u:
            i += 1
        f = (u - self.u[i]) / max(1e-9, self.u[i + 1] - self.u[i])
        p = self.pts[i] + (self.pts[i + 1] - self.pts[i]) * f
        j0, j1 = max(i - 1, 0), min(i + 2, len(self.pts) - 1)
        tan = (self.pts[j1] - self.pts[j0]).normalized()
        nrm = Vector((-tan.y, tan.x))
        ref_t = min(1.0, max(0.0, (p.y - 0.50) / 0.30))              # low: up is "towards the sitter"; high: forward is
        ref = Vector((ref_t, 1.0 - ref_t))
        if nrm.dot(ref) < 0:
            nrm = -nrm
        return p, tan, nrm

    def z_to_g(self, z: float) -> float:
        """Back fraction where the profile passes the height z."""
        best = min(range(len(self.pts)), key=lambda i: abs(self.pts[i].y - z) if self.u[i] >= self.u_corner else 1e9)
        return (self.u[best] - self.u_corner) / (self.u_end - self.u_corner)


class Laws:
    """Width, side wrap and thickness of the seat and the back as functions of the fraction along each part."""

    def __init__(self, s: float, command: bool) -> None:
        self.s = s
        self.w_seat = [(0.0, 0.180 * s), (0.22, 0.212 * s), (0.6, 0.224 * s), (1.0, 0.205 * s)]
        self.bo_seat = [(0.0, 0.010), (0.5, 0.034), (1.0, 0.046)]
        self.th_seat = [(0.0, 0.032), (1.0, 0.052)]
        if command:
            self.w_back = [(0.0, 0.200 * s), (0.22, 0.190 * s), (0.42, 0.205 * s), (0.66, 0.240 * s), (0.84, 0.228 * s), (1.0, 0.150 * s)]
            self.bo_back = [(0.0, 0.05), (0.4, 0.07), (0.66, 0.125), (1.0, 0.07)]
        else:
            self.w_back = [(0.0, 0.190 * s), (0.25, 0.176 * s), (0.45, 0.186 * s), (0.68, 0.226 * s), (0.86, 0.230 * s), (1.0, 0.160 * s)]
            self.bo_back = [(0.0, 0.05), (0.4, 0.06), (0.7, 0.10), (1.0, 0.06)]
        self.th_back = [(0.0, 0.048), (0.5, 0.040), (1.0, 0.032)]

    def w(self, kind, g):
        return interp_table(self.w_seat if kind == "seat" else self.w_back, g)

    def bo(self, kind, g):
        return interp_table(self.bo_seat if kind == "seat" else self.bo_back, g)

    def th(self, kind, g):
        return interp_table(self.th_seat if kind == "seat" else self.th_back, g)


def bean_part(fb, prof: Profile, laws: Laws, kind: str, g0: float, g1: float, mat: str, w_scale: float = 1.0, lift=0.0, thick=None,
              cap0: float = 0.0, cap1: float = 0.0, e: float = 3.4, nphi: int = 30, nres: int = 18, wrap: float = 1.0, w_minus: float = 0.0):
    """A shell part between the fractions g0..g1 of the seat or the back: rounded sections perpendicular to the profile.
    `lift` (m, number or f(g)) moves the front face off the profile towards the sitter; `thick` (number or f(g)) is the
    thickness behind the front face (default: the shell's own); `cap0/cap1` (m) close the ends with rounded caps."""
    u0, u1 = prof.u_of(kind, g0), prof.u_of(kind, g1)
    n = max(4, nres)

    def ring(g, p, nrm, k=1.0):
        lf = lift(g) if callable(lift) else lift
        th = (thick(g) if callable(thick) else thick) if thick is not None else laws.th(kind, g)
        w = max(0.004, laws.w(kind, g) * w_scale - w_minus)
        bo = laws.bo(kind, g) * wrap
        pts = []
        for j in range(nphi):
            phi = 2 * math.pi * (j + 0.5) / nphi
            v = sgnpow(math.cos(phi), 2.0 / e)
            m = sgnpow(math.sin(phi), 2.0 / e)
            q = p + nrm * (lf + bo * v * v * w_scale * w_scale + th * k * 0.5 * (m - 1.0))
            pts.append((q.x, v * w * k, q.y))
        return pts

    rings = []
    if cap0 > 0:
        p, tan, nrm = prof.at(u0)
        for s_ in (0.985, 0.94, 0.85, 0.70, 0.50, 0.25):
            k = math.cos(s_ * math.pi / 2)
            rings.append(ring(g0, p - tan * cap0 * math.sin(s_ * math.pi / 2), nrm, k))
    for i in range(n + 1):
        f = i / n
        g = g0 + (g1 - g0) * f
        p, tan, nrm = prof.at(u0 + (u1 - u0) * f)
        rings.append(ring(g, p, nrm))
    if cap1 > 0:
        p, tan, nrm = prof.at(u1)
        for s_ in (0.25, 0.50, 0.70, 0.85, 0.94, 0.985):
            k = math.cos(s_ * math.pi / 2)
            rings.append(ring(g1, p + tan * cap1 * math.sin(s_ * math.pi / 2), nrm, k))
    return fb.loft(rings, mat, caps=True)


def on_profile(prof: Profile, kind: str, g: float, off: float = 0.0):
    """Position (x, z), tangent angle (degrees, about y) and normal of the profile point at fraction g, `off` m along the normal."""
    p, tan, nrm = prof.at(prof.u_of(kind, g))
    q = p + nrm * off
    ang = math.degrees(math.atan2(tan.y, tan.x))
    return q, ang, nrm


# ---------------------------------------------------------------------------------------------------- the seat and its base
def chair_shell_parts(b: Parts, scale: float = 1.0, command: bool = False, captain: bool = False, dept: str = "command") -> Profile:
    """The shells, cushions, fin, harness and pedestal. `command`: ivory, taller, wing bolsters; crew: gunmetal."""
    fb, fine, em, soft = b.body, b.fine, b.emit, b.soft
    s = scale
    top = 1.27 if not command else (1.42 if captain else 1.36)
    ctrl = [(0.30, 0.440), (0.27, 0.462), (0.20, 0.478), (0.05, 0.480), (-0.11, 0.482), (-0.19, 0.505), (-0.238, 0.60), (-0.262, 0.74),
            (-0.278, 0.90), (-0.278, 1.04), (-0.262, 1.16), (-0.244, 1.27)]
    ctrl = [(x * s, z if z <= 0.5 else 0.5 + (z - 0.5) * (top - 0.5) / 0.77) for x, z in ctrl]
    prof = Profile(ctrl, corner_index=5)
    laws = Laws(s, command)
    shell = L.IVORY if command else L.STRUCT
    inset = L.COMPOSITE
    # ---- shells: the seat pan and the back with a hairline gap, the back closed by a rounded top
    bean_part(fb, prof, laws, "seat", 0.0, 1.0, shell, cap0=0.05, cap1=0.03, nres=18, e=4.6, nphi=36)
    bean_part(fb, prof, laws, "back", 0.03, 1.0, shell, cap0=0.03, cap1=0.06, nres=36, e=4.6, nphi=36)
    # the carbon inset on the back of the shell (a proud panel) and a slim ridge along the spine
    bean_part(fb, prof, laws, "back", 0.10, 0.955, inset, w_scale=0.72, lift=lambda g: -laws.th("back", g) + 0.004, thick=0.014, cap0=0.02, cap1=0.03,
              nres=24, e=5.0)
    # ---- cushions: seat, one long back cushion, a headrest pillow; rounded, smooth-shaded
    bean_part(soft, prof, laws, "seat", 0.05, 0.98, L.LEATHER, w_scale=0.90, lift=0.050, thick=0.056, cap0=0.02, cap1=0.02, nres=14, e=2.8)
    bean_part(soft, prof, laws, "back", 0.10, 0.80, L.LEATHER, w_scale=0.86, lift=0.048, thick=0.054, cap0=0.02, cap1=0.03, nres=22, e=2.8)
    bean_part(soft, prof, laws, "back", 0.845, 0.975, L.LEATHER, w_scale=0.62, lift=0.052, thick=0.058, cap0=0.03, cap1=0.03, nres=8, e=2.6)
    # stitched grooves across the back cushion, piping at the seat
    for g in (0.30, 0.50):
        q, ang, nrm = on_profile(prof, "back", g, 0.0505)
        fine.cbox((q.x, 0.0, q.y), (0.004, 2 * laws.w("back", g) * 0.66, 0.006), L.STRUCT, Ry(-(ang - 90.0)))
    # ---- the fin behind the back: a slim plate with a lit rear edge in the department colour
    g_fin = 0.42 if command else 0.18                              # command chairs: the fin starts above the name plate
    q_lo, _, _ = on_profile(prof, "back", g_fin, -laws.th("back", g_fin))
    q_hi, _, _ = on_profile(prof, "back", 0.98, -laws.th("back", 0.98))
    z0f, zt = q_lo.y - 0.02, q_hi.y - 0.02
    fin = [(q_lo.x - 0.005, z0f), (q_lo.x - 0.08 * s, z0f + 0.03), (q_lo.x - 0.13 * s, z0f + 0.25), (q_lo.x - 0.095 * s, (z0f + zt) / 2 + 0.12),
           (q_hi.x - 0.01, zt), (q_hi.x + 0.02, zt - 0.10), (q_lo.x + 0.03, z0f + 0.08)]
    fb.extrude_y(fin, -0.016, 0.016, L.TRIM if not command else L.STRUCT)
    em.lamp_cbox((q_lo.x - 0.105 * s, 0.0, (z0f + zt) / 2 - 0.02), (0.008, 0.022, (zt - z0f) * 0.68), dept, L.LAMP, Ry(-4))
    for z in (0.66, 0.90, 1.12):                                 # clamp bands round the fin
        if z0f + 0.04 < z < zt - 0.04:
            fb.box((q_lo.x - 0.058 * s - 0.01 * (z - 0.6), -0.022, z - 0.02), (q_lo.x + 0.01, 0.022, z + 0.02), L.TRIM)
    # ---- the back of the shell: a name-plate boss, a release handle with a warning lamp, rivets
    qb, angb, _ = on_profile(prof, "back", 0.24, -laws.th("back", 0.24) - 0.014)
    if command:
        bw, bh = 0.20, 0.09
        xr = qb.x - 0.01
        fb.box((xr, -bw * s, qb.y - bh), (xr + 0.05, bw * s, qb.y + bh), L.TRIM)
        fine.cbox((xr - 0.0005, 0.0, qb.y), (0.001, bw * 1.8 * s, bh * 1.22), L.STRUCT)
    qh, _, _ = on_profile(prof, "back", 0.52, -laws.th("back", 0.52) - 0.02)
    hy = 0.115 * s if command else 0.0                             # the release handle beside the fin on the command chairs
    fine.box((qh.x - 0.03, hy - 0.05, qh.y - 0.02), (qh.x + 0.055, hy + 0.05, qh.y + 0.02), L.RUBBER)
    em.lamp_box((qh.x - 0.0325, hy - 0.03, qh.y + 0.022), (qh.x - 0.031, hy + 0.03, qh.y + 0.031), "amber", L.LAMP_DIM)
    for sd in (-1, 1):
        for g in (0.12, 0.42, 0.72):
            for yy in (0.10, 0.17):
                w_g = laws.w("back", g)
                if yy * s < w_g * 0.58:
                    q, ang, nrm = on_profile(prof, "back", g, -laws.th("back", g) + laws.bo("back", g) * (yy * s / w_g) ** 2)
                    fine.cyl((q.x, sd * yy * s, q.y), (q.x - 0.012, sd * yy * s, q.y), 0.009, L.TRIM, seg=8)
    # ---- harness hard points: a ring at each shoulder rim (the straps are clipped on for a jump)
    for sd in (-1, 1):
        wy = laws.w("back", 0.74)
        qr, _, _ = on_profile(prof, "back", 0.74, laws.bo("back", 0.74) * 0.92 - laws.th("back", 0.74) * 0.5)
        fine.cyl((qr.x, sd * (wy - 0.02), qr.y + 0.03), (qr.x, sd * (wy + 0.03), qr.y + 0.03), 0.016, L.TRIM, seg=12)
    # ---- suspension, swivel collar and the pedestal
    for sd in (-1, 1):
        fine.cyl((0.0, sd * 0.06, 0.34), (-0.06 * s, sd * 0.19 * s, 0.415), 0.014, L.TRIM, seg=10)
        fine.cyl((0.0, sd * 0.06, 0.34), (-0.03 * s, sd * 0.12 * s, 0.38), 0.020, L.STRUCT, seg=10)
    base_r = 0.30 * s * (1.25 if command else 1.0)
    fb.cyl((0, 0, 0.0), (0, 0, 0.05), base_r, L.STRUCT, seg=40, r2=base_r * 0.62)
    fb.cyl((0, 0, 0.05), (0, 0, 0.36), 0.075 * s, L.TRIM, seg=28, r2=0.055 * s)
    fb.cyl((0, 0, 0.30), (0, 0, 0.395), 0.15 * s, L.STRUCT, seg=32, r2=0.19 * s)
    fb.cyl((0, 0, 0.395), (0, 0, 0.412), 0.20 * s, L.TRIM, seg=32)
    em.lamp_cyl((0, 0, 0.0), (0, 0, 0.004), base_r + 0.006, dept + "_dim", L.LAMP_DIM, seg=40)
    em.lamp_arc([(0.163 * s, 0.0), (0.168 * s, 0.0), (0.168 * s, 0.006), (0.163 * s, 0.006)], 0, 0, 0, 0, 360, dept, L.LAMP_DIM, seg=32, z0=0.332, loop=True)
    return prof


def build_chair_crew(name: str = "SM_BRG3_ChairCrew"):
    b = Parts(bevel=0.006, fine_bevel=0.003, angle=60.0)
    prof = chair_shell_parts(b, 1.0, command=False)
    # a cable bundle from the base to the console (the seat is wired to it)
    b.fine.tube([(0.05, 0.0, 0.05), (0.32, 0.0, 0.03), (0.55, 0.02, 0.02)], 0.014, L.RUBBER, seg=8)
    return b.build(name, uv_meter=0.25)


def armrest_pod(b: Parts, sd: int, slot: str | None, dept: str, scale: float = 1.0) -> dict | None:
    """A command chair's armrest: a slim sculpted pod on a swept arm, a touch screen and a small control cluster."""
    fb, fine, em = b.body, b.fine, b.emit
    y0 = sd * 0.345 * scale
    top = 0.760
    x0, x1 = -0.15, 0.32
    n = 12
    rings = []
    for i in range(n + 1):
        f = i / n
        x = x0 + (x1 - x0) * f
        hw = 0.068 * (0.82 + 0.18 * math.sin(math.pi * min(1.0, f * 1.15))) * (1.0 - 0.28 * max(0.0, f - 0.82) / 0.18)
        zc = top - 0.030 + 0.05 * f * f
        th = 0.060
        pts = []
        for j in range(26):
            phi = 2 * math.pi * (j + 0.5) / 26
            v = sgnpow(math.cos(phi), 0.5)
            m = sgnpow(math.sin(phi), 0.5)
            pts.append((x, y0 + v * hw, zc + m * th / 2))
        rings.append(pts)
    # rounded ends: two shrinking rings at each end
    def shrink(ring, k):
        cx = sum(p[0] for p in ring) / len(ring)
        cy = sum(p[1] for p in ring) / len(ring)
        cz = sum(p[2] for p in ring) / len(ring)
        return [(cx + (p[0] - cx), cy + (p[1] - cy) * k, cz + (p[2] - cz) * k) for p in ring]
    r0, r1 = rings[0], rings[-1]
    cap0 = [shrink([(p[0] - 0.024 * (1 - k), p[1], p[2]) for p in r0], k) for k in (0.82, 0.55, 0.18)]
    cap1 = [shrink([(p[0] + 0.036 * (1 - k), p[1], p[2]) for p in r1], k) for k in (0.82, 0.55, 0.18)]
    fb.loft(list(reversed(cap0)) + rings + cap1, L.IVORY, caps=True)
    xa, xb = x0 + 0.05, x1 - 0.06
    slope = lambda x: 0.1 * ((x - x0) / (x1 - x0)) / (x1 - x0)
    zt = lambda x: top + 0.05 * ((x - x0) / (x1 - x0)) ** 2
    cx = (xa + xb) / 2
    tilt = math.degrees(math.atan(slope(cx)))
    fb.cbox((cx, y0, zt(cx) + 0.0035), (xb - xa, 0.102, 0.012), L.DGLASS, Ry(-tilt))
    em.lamp_box((x0 + 0.13, y0 + sd * 0.0655, top - 0.036), (x1 - 0.13, y0 + sd * 0.0685, top - 0.028), dept, L.LAMP)
    info = None
    if slot:
        w, h = 0.20, 0.098
        with b.emit.at(T(cx, y0, zt(cx) + 0.0102) @ Ry(-tilt)):
            b.emit.screen((0, 0, 0), w, h, slot, (0, 0, 1), up=(1, 0, 0))
        info = {"screen": slot, "size_m": [w, h], "surface": "armrest"}
    kx = x1 - 0.042
    with b.at(T(kx, y0, zt(kx) + 0.001) @ Ry(-math.degrees(math.atan(slope(kx))))):
        for k in range(-2, 3):
            K.key(fine, em, 0.0, k * 0.022, "cyan" if k else "amber", 0.016)
    # the arm from the seat side up under the pod: a plate on a cross pin, with a pivot ring
    fb.extrude_y([(-0.11, 0.46), (-0.02, 0.46), (0.07, top - 0.052), (-0.07, top - 0.052)], y0 - sd * 0.03 - 0.014, y0 - sd * 0.03 + 0.014, L.STRUCT)
    fb.cyl((-0.07, sd * 0.19, 0.545), (-0.07, y0 - sd * 0.03, 0.545), 0.020, L.TRIM, seg=14)
    fb.cyl((-0.07, y0 - sd * 0.03 + sd * 0.014, 0.545), (-0.07, y0 - sd * 0.03 + sd * 0.026, 0.545), 0.028, L.STRUCT, seg=16)
    return info


def build_chair_command(name: str, captain: bool, screens: list[str]):
    """The Captain's chair (captain=True) or the XO's: taller shell, wing bolsters, armrest pods, a heavy lit pedestal."""
    b = Parts(bevel=0.006, fine_bevel=0.0035, angle=60.0)
    scale = 1.08 if captain else 0.98
    prof = chair_shell_parts(b, scale, command=True, captain=captain)
    infos = []
    for i, sd in enumerate((-1, 1)):
        slot = screens[i] if i < len(screens) else None
        info = armrest_pod(b, sd, slot, "command", scale)
        if info:
            infos.append(info)
    # the name plate on the boss at the back of the chair (towards the tactical officer behind it)
    laws = Laws(scale, True)
    qb, _, _ = on_profile(prof, "back", 0.24, -laws.th("back", 0.24) - 0.014)
    b.body.label((qb.x - 0.0115, 0.0, qb.y), 0.34 * scale, 0.043, (-1, 0, 0), "st_captain" if captain else "st_xo", up=(0, 0, 1))
    return b.build(name, uv_meter=0.25), infos
