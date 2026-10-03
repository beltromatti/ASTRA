"""ASN Aquila bridge v3: the structural ceiling.

Radial ribs run from the dome above the captain to the walls and the window mullions; two ring beams carry light lines on
both faces (indirect light on the ceiling); between them dark composite panels sit on a polar grid; the dome is a shallow
ribbed cap with a ring of light and a dark lens (the "command eye"); a flush collector with a crown of emitters hangs over
the holo table; two ducts cross the back half. Nothing here hangs into the volume above the table (2.2 m of hologram).
"""
from __future__ import annotations

import math
import os
import random
import sys

from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge3_lib as L  # noqa: E402
import bridge3_shell as SH  # noqa: E402
from bridge3_lib import Parts, Ry, Rx, Rz, T, lerp, polar  # noqa: E402


def room_poly(c: SH.Ctx, window_r: float | None = None):
    """The room outline at ceiling level (convex): back wall, side walls, the window facets at `window_r` (default R - 0.3)."""
    wr = c.R - 0.30 if window_r is None else window_r
    pts = [(c.BACK_X, -c.BACK_HW), c.front_p]
    for k in (1, 2, 3, 4, 5):
        pts.append(c.arc(c.ANG[k], wr))
    pts += [c.front_s, (c.BACK_X, c.BACK_HW)]
    return pts


def ray_hit(poly, ang_deg: float, origin=(0.0, 0.0)):
    """Distance along the ray from `origin` at `ang_deg` to the convex polygon's boundary."""
    a = math.radians(ang_deg)
    dx, dy = math.cos(a), math.sin(a)
    best = None
    n = len(poly)
    for i in range(n):
        (x0, y0), (x1, y1) = poly[i], poly[(i + 1) % n]
        ex, ey = x1 - x0, y1 - y0
        den = dx * ey - dy * ex
        if abs(den) < 1e-9:
            continue
        t = ((x0 - origin[0]) * ey - (y0 - origin[1]) * ex) / den
        u = ((x0 - origin[0]) * dy - (y0 - origin[1]) * dx) / den
        if t > 0 and -1e-9 <= u <= 1 + 1e-9:
            best = t if best is None else min(best, t)
    return best


def inside_runs(poly, r: float, margin: float, step: float = 1.0):
    """Angle intervals (degrees) of the circle of radius r about the origin that lie inside the room by `margin`."""
    runs, cur = [], None
    a = 0.0
    while a <= 360.0 + 1e-6:
        ok = SH.inside_poly(poly, polar(0.0, 0.0, r, a), margin)
        if ok and cur is None:
            cur = a
        if not ok and cur is not None:
            runs.append((cur, a - step))
            cur = None
        a += step
    if cur is not None:
        runs.append((cur, 360.0))
    if len(runs) > 1 and runs[0][0] == 0.0 and runs[-1][1] >= 360.0 - 1e-6:      # a run wrapping through 0 / 360
        first = runs.pop(0)
        last = runs.pop()
        runs.append((last[0], first[1] + 360.0))
    return runs


def build_ceiling(c: SH.Ctx, name: str = "SM_BRG3_Ceiling"):
    b = Parts(bevel=0.007, fine_bevel=0.0035)
    fb, em = b.body, b.emit
    CE = c.CEIL
    poly = room_poly(c)
    cd = c.D["ceiling"]
    dc = cd["dome_center"]
    Rd = cd["dome_radius"]
    Hd = cd["dome_height"] - CE
    rings = list(cd.get("ring_radii", [6.4, 8.3]))
    ang_ribs = [10.0 * k for k in range(36)]
    rad_edges = [Rd, 4.9, rings[0], (rings[0] + rings[1]) / 2, rings[1], 9.3, 10.4, 12.2]

    # ---- the structural slab above the panels
    slab = [(c.BACK_X - 0.34, -c.BACK_HW - 0.34), (c.front_p[0], c.front_p[1] - 0.34)]
    slab += [c.arc(c.ANG[k], c.R + 0.35) for k in range(1, 6)]
    slab += [(c.front_s[0], c.front_s[1] + 0.34), (c.BACK_X - 0.34, c.BACK_HW + 0.34)]
    hole = Rd + 0.10                                              # square hole round the dome, closed above by a lid
    far = 40.0
    z_top = CE + Hd + 0.30
    for rect in (
            [(dc[0] - far, dc[1] - far), (dc[0] - hole, dc[1] - far), (dc[0] - hole, dc[1] + far), (dc[0] - far, dc[1] + far)],
            [(dc[0] + hole, dc[1] - far), (dc[0] + far, dc[1] - far), (dc[0] + far, dc[1] + far), (dc[0] + hole, dc[1] + far)],
            [(dc[0] - hole, dc[1] + hole), (dc[0] + hole, dc[1] + hole), (dc[0] + hole, dc[1] + far), (dc[0] - hole, dc[1] + far)],
            [(dc[0] - hole, dc[1] - far), (dc[0] + hole, dc[1] - far), (dc[0] + hole, dc[1] - hole), (dc[0] - hole, dc[1] - hole)]):
        cl = SH.clip_convex(slab, rect, 0.0)
        if len(cl) >= 3 and SH.poly_area(cl) > 0.05:
            fb.prism(cl, CE + 0.02, z_top, L.STRUCT)
    lid = hole + 0.30
    fb.prism([(dc[0] - lid, dc[1] - lid), (dc[0] + lid, dc[1] - lid), (dc[0] + lid, dc[1] + lid), (dc[0] - lid, dc[1] + lid)], CE + Hd + 0.02, z_top, L.STRUCT)

    # ---- panels on a polar grid (10 degree sectors x radial bands), clipped to the room
    def wedge(r0, r1, a0, a1):
        return [polar(dc[0], dc[1], r0, a0), polar(dc[0], dc[1], r0, a1), polar(dc[0], dc[1], r1, a1), polar(dc[0], dc[1], r1, a0)]

    n_pan = 0
    for a in ang_ribs:
        for bi, (r0, r1) in enumerate(zip(rad_edges[:-1], rad_edges[1:])):
            gap_a = math.degrees(0.15 / max(r0, 1.0))
            quad = wedge(r0 + 0.14, r1 - 0.14, a + gap_a, a + 10.0 - gap_a)
            cl = SH.clip_convex(quad, poly, 0.10)
            if len(cl) < 3 or SH.poly_area(cl) < 0.08:
                continue
            fb.prism(cl, CE - 0.045, CE, L.COMPOSITE)
            if SH.poly_area(cl) > 0.9:
                cx = sum(q[0] for q in cl) / len(cl)
                cy = sum(q[1] for q in cl) / len(cl)
                fb.prism([(cx + (q[0] - cx) * 0.8, cy + (q[1] - cy) * 0.8) for q in cl], CE - 0.06, CE - 0.045, L.COMPOSITE)
                n_pan += 1
                if n_pan % 5 == 0 and SH.poly_area(cl) > 1.4 and cx < 3.0:            # a recessed grille (the air of the deck)
                    with b.at(T(cx, cy, CE - 0.06) @ Rz(a + 5.0)):
                        fb.box((-0.34, -0.21, -0.006), (0.34, 0.21, 0.006), L.TRIM)
                        fb.box((-0.30, -0.17, -0.012), (0.30, 0.17, 0.0), L.RUBBER)
                        for k in range(7):
                            fb.cbox((0.0, -0.15 + k * 0.05, -0.014), (0.6, 0.012, 0.006), L.TRIM, Rx(28))
            if bi in (1, 3, 4) and (int(a // 10) % 2 == 0) and SH.poly_area(cl) > 0.5:       # about a fifth of the panels are light panels: a soft warm field in a brass hairline
                cx = sum(q[0] for q in cl) / len(cl)
                cy = sum(q[1] for q in cl) / len(cl)
                fld = [(cx + (q[0] - cx) * 0.66, cy + (q[1] - cy) * 0.66, CE - 0.0475) for q in cl]
                em.lamp_face(fld, "white_warm", (0, 0, -1), L.LAMP_DIM)
                for k in range(len(fld)):
                    p0, p1 = fld[k], fld[(k + 1) % len(fld)]
                    SH.line_lamp(em, (p0[0], p0[1]), (p1[0], p1[1]), CE - 0.0485, 0.008, 0.002, "warm_dim", L.LAMP_DIM)

    # ---- radial ribs from the dome to the walls (brushed metal, a warm line in the soffit)
    for a in ang_ribs:
        rmax = ray_hit(poly, a, dc)
        if rmax is None:
            continue
        r_in, r_out = Rd - 0.05, rmax - 0.02
        p0, p1 = polar(dc[0], dc[1], r_in, a), polar(dc[0], dc[1], r_out, a)
        ln = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        cx, cy = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        heavy = (round(a) % 20 == 0)
        w, d = (0.26, 0.36) if heavy else (0.2, 0.28)
        rot = Rz(a)
        fb.cbox((cx, cy, CE - d / 2), (ln, w, d), L.TRIM, rot)
        fb.cbox((cx, cy, CE - d - 0.012), (ln - 0.1, w - 0.07, 0.024), L.STRUCT, rot)
        em.lamp_cbox((cx, cy, CE - d - 0.026), (ln - 0.6, 0.016, 0.006), "warm_dim", L.LAMP_DIM, rot)
        r = r_in + 0.7
        while r < r_out - 0.3:                                   # clamp collars
            px, py = polar(dc[0], dc[1], r, a)
            fb.cbox((px, py, CE - d / 2), (0.09, w + 0.05, d + 0.03), L.STRUCT, rot)
            r += 1.4

    # ---- ring beams with light lines on both faces (indirect light on the ceiling)
    for rr in rings:
        for (a0, a1) in inside_runs(poly, rr, 0.35, 1.0):
            seg = max(4, int((a1 - a0) / 3.0))
            fb.arc_sweep([(-0.13, 0.0), (0.13, 0.0), (0.13, 0.34), (-0.13, 0.34)], dc[0], dc[1], rr, a0, a1, L.TRIM, seg=seg, z0=CE - 0.34)
            fb.arc_sweep([(-0.085, 0.0), (0.085, 0.0), (0.085, 0.024), (-0.085, 0.024)], dc[0], dc[1], rr, a0, a1, L.STRUCT, seg=seg,
                         z0=CE - 0.362)
            for sd in (-1, 1):
                em.lamp_arc([(sd * 0.13, 0.0), (sd * 0.138, 0.0), (sd * 0.138, 0.014), (sd * 0.13, 0.014)], dc[0], dc[1], rr, a0 + 0.5,
                            a1 - 0.5, "white_warm", L.LAMP_HOT, seg=seg, z0=CE - 0.09)

    # ---- the dome: a shallow spherical cap, ribbed and panelled, with the command "eye" at the apex
    Rs = (Rd * Rd + Hd * Hd) / (2 * Hd)
    zc = CE + Hd - Rs
    beta_max = math.asin(Rd / Rs)
    betas = [0.10 * beta_max, 0.32 * beta_max, 0.58 * beta_max, 0.80 * beta_max, beta_max]
    n_sec = 24

    def sph(beta, phi_deg, dr=0.0):
        r = Rs + dr
        return (dc[0] + r * math.sin(beta) * math.cos(math.radians(phi_deg)), dc[1] + r * math.sin(beta) * math.sin(math.radians(phi_deg)),
                zc + r * math.cos(beta))

    for k in range(n_sec):
        p0, p1 = k * 360.0 / n_sec, (k + 1) * 360.0 / n_sec
        gap = 2.2
        for j in range(len(betas) - 1):
            b0, b1 = betas[j], betas[j + 1] - 0.012
            outer = [sph(b0, p0 + gap), sph(b0, p1 - gap), sph(b1, p1 - gap), sph(b1, p0 + gap)]
            inner = [sph(b0, p0 + gap, -0.05), sph(b0, p1 - gap, -0.05), sph(b1, p1 - gap, -0.05), sph(b1, p0 + gap, -0.05)]
            fb.loft([inner, outer], L.COMPOSITE, caps=True)
        rings_pts = []
        for beta in betas:
            cp = Vector(sph(beta, p0))
            e = Vector((-math.sin(math.radians(p0)), math.cos(math.radians(p0)), 0.0))
            nrm = (cp - Vector((dc[0], dc[1], zc))).normalized()
            w = 0.09
            rings_pts.append([tuple(cp - e * w + nrm * 0.03), tuple(cp + e * w + nrm * 0.03), tuple(cp + e * w - nrm * 0.08),
                              tuple(cp - e * w - nrm * 0.08)])
        fb.loft(rings_pts, L.TRIM, caps=True)
    for j in range(1, len(betas) - 1):                            # a fine lit line in each seam between the rows of panels
        bs = betas[j] - 0.006
        em.lamp_arc([(-0.007, 0.0), (0.007, 0.0), (0.007, 0.004), (-0.007, 0.004)], dc[0], dc[1], (Rs - 0.052) * math.sin(bs), 0, 360, "white_warm",
                    L.LAMP_DIM, seg=96, z0=zc + (Rs - 0.052) * math.cos(bs), loop=True)

    def seg_rot(pa, pb):                                          # a rotation whose x axis runs along pa -> pb
        d = (Vector(pb) - Vector(pa)).normalized()
        y = Vector((0.0, 0.0, 1.0)).cross(d)
        y = y.normalized() if y.length > 1e-6 else Vector((0.0, 1.0, 0.0))
        z = d.cross(y)
        return Matrix(((d.x, y.x, z.x, 0.0), (d.y, y.y, z.y, 0.0), (d.z, y.z, z.z, 0.0), (0.0, 0.0, 0.0, 1.0)))

    for k in range(n_sec):                                        # a warm line under every rib of the dome
        ph = k * 360.0 / n_sec
        for j in range(len(betas) - 1):
            pa, pb = sph(betas[j], ph, -0.0815), sph(betas[j + 1] - 0.004, ph, -0.0815)
            ln = (Vector(pb) - Vector(pa)).length
            mid = tuple((u + v) / 2 for u, v in zip(pa, pb))
            em.lamp_cbox(mid, (ln * 0.96, 0.010, 0.004), "warm_dim", L.LAMP_DIM, seg_rot(pa, pb))
    # the rim ring where the dome meets the ceiling, with a cove line facing the dome
    fb.arc_sweep([(-0.16, 0.0), (0.16, 0.0), (0.16, 0.22), (-0.16, 0.22)], dc[0], dc[1], Rd, 0, 360, L.TRIM, seg=72, z0=CE - 0.22, loop=True)
    em.lamp_arc([(-0.176, 0.0), (-0.16, 0.0), (-0.16, 0.014), (-0.176, 0.014)], dc[0], dc[1], Rd, 0, 360, "white_warm", L.LAMP_HOT, seg=72,
                z0=CE - 0.09, loop=True)
    # the eye: a lens disc hanging under the apex of the dome, a ring of light round a dark glass lens
    def z_dome(r):                                                # the room-facing surface of the panels at radius r
        return zc + math.sqrt(max(0.0, (Rs - 0.05) ** 2 - r * r))

    r_eye = 0.95
    z_fl = z_dome(r_eye)
    fb.cyl((dc[0], dc[1], z_fl - 0.10), (dc[0], dc[1], z_fl + 0.02), r_eye + 0.12, L.TRIM, seg=56)
    fb.cyl((dc[0], dc[1], z_fl - 0.104), (dc[0], dc[1], z_fl - 0.10), r_eye + 0.03, L.STRUCT, seg=56)
    fb.cyl((dc[0], dc[1], z_fl - 0.118), (dc[0], dc[1], z_fl - 0.104), r_eye - 0.06, L.DGLASS, seg=56)
    em.lamp_arc([(r_eye - 0.11, 0.0), (r_eye - 0.05, 0.0), (r_eye - 0.05, 0.005), (r_eye - 0.11, 0.005)], dc[0], dc[1], 0.0, 0, 360, "white_cool",
                L.LAMP_HOT, seg=64, z0=z_fl - 0.1195, loop=True)
    fb.cyl((dc[0], dc[1], z_fl - 0.140), (dc[0], dc[1], z_fl - 0.118), 0.30, L.TRIM, seg=40)
    fb.cyl((dc[0], dc[1], z_fl - 0.146), (dc[0], dc[1], z_fl - 0.140), 0.24, L.DGLASS, seg=40)
    em.lamp_cyl((dc[0], dc[1], z_fl - 0.1475), (dc[0], dc[1], z_fl - 0.1455), 0.07, "white_cool", L.LAMP_HOT, seg=24)
    for k in range(12):                                           # twelve small emitters on the disc, between the ring and the centre lens
        a_ = 2 * math.pi * k / 12
        px, py = dc[0] + 0.52 * math.cos(a_), dc[1] + 0.52 * math.sin(a_)
        em.lamp_cyl((px, py, z_fl - 0.1195), (px, py, z_fl - 0.1175), 0.018, "cyan", L.LAMP, seg=8)

    # ---- the holo collector above the table: a flush lens in a ring flange, a crown of emitters
    cx0, cy0 = cd["collector_center"]
    cr = cd["collector_radius"]
    fb.cyl((cx0, cy0, CE - 0.12), (cx0, cy0, CE - 0.045), cr, L.TRIM, seg=64)
    fb.cyl((cx0, cy0, CE - 0.135), (cx0, cy0, CE - 0.12), cr - 0.14, L.DGLASS, seg=64)
    for k in range(32):
        ang = 2 * math.pi * k / 32
        px, py = cx0 + (cr - 0.07) * math.cos(ang), cy0 + (cr - 0.07) * math.sin(ang)
        em.lamp_cyl((px, py, CE - 0.125), (px, py, CE - 0.118), 0.022, "cyan", L.LAMP, seg=8)
    em.lamp_arc([(cr - 0.20, 0.0), (cr - 0.19, 0.0), (cr - 0.19, 0.01), (cr - 0.20, 0.01)], cx0, cy0, 0.0, 0, 360, "cyan", L.LAMP_DIM, seg=64,
                z0=CE - 0.137, loop=True)

    # ---- recessed downlights over the stations: a lens in a ring (the lights themselves are in the data file)
    for (lx, ly) in ((1.1, 0.0), (6.9, -2.2), (6.9, 2.2), (-2.6, 0.0)):
        rr = math.hypot(lx - dc[0], ly - dc[1])
        zb = z_dome(rr) - 0.02 if rr < Rd - 0.3 else CE - 0.045          # inside the dome the lens sits in the dome, not on the flat ceiling
        fb.cyl((lx, ly, zb - 0.055), (lx, ly, zb + 0.06), 0.13, L.TRIM, seg=24)
        fb.cyl((lx, ly, zb - 0.06), (lx, ly, zb - 0.055), 0.095, L.DGLASS, seg=24)
        em.lamp_cyl((lx, ly, zb - 0.0595), (lx, ly, zb - 0.0565), 0.075, "white_cool", L.LAMP_HOT, seg=24)

    # ---- ducts along the back half of the room, on brackets
    for y in (-4.9, 4.9):
        x0, x1 = c.BACK_X + 0.4, -4.4
        fb.cyl((x0, y, CE - 0.5), (x1, y, CE - 0.5), 0.2, L.STRUCT, seg=24)
        for i in range(int((x1 - x0) / 1.6)):
            xk = x0 + 0.5 + 1.6 * i
            fb.cyl((xk - 0.05, y, CE - 0.5), (xk + 0.05, y, CE - 0.5), 0.215, L.TRIM, seg=24)
            fb.cbox((xk, y, CE - 0.22), (0.05, 0.06, 0.32), L.TRIM)
        em.lamp_cyl((x1 - 0.02, y, CE - 0.5), (x1, y, CE - 0.5), 0.19, "amber", L.LAMP_DIM, seg=24)
    return b.build(name)
