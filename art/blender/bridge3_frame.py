"""ASN Aquila bridge v3: the window frame and glass, the back wall, the master display, the rails and the viewscreen frame."""
from __future__ import annotations

import math
import os
import random
import sys

from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import astra_bpy as A  # noqa: E402
import bridge3_lib as L  # noqa: E402
import bridge3_shell as SH  # noqa: E402
import bridge3_walls as WL  # noqa: E402
from bridge3_lib import FB, Parts, Rz, T, lerp, polar  # noqa: E402


def basis_matrix(origin, xdir, ydir) -> Matrix:
    """Local frame from an origin and the layout directions of local x and y (z up)."""
    m = Matrix.Identity(4)
    m[0][0], m[1][0] = xdir[0], xdir[1]
    m[0][1], m[1][1] = ydir[0], ydir[1]
    m[0][3], m[1][3] = origin[0], origin[1]
    return m


# ------------------------------------------------------------------------------------------------------------------ window
def build_window(c: SH.Ctx, name: str = "SM_BRG3_Window"):
    """Sill bands, head beams, mullions and the frames of the panes (the glass is a separate translucent mesh)."""
    b = Parts(bevel=0.008, fine_bevel=0.004)
    fb, em = b.body, b.emit
    CE = c.CEIL
    for k in range(len(c.ANG) - 1):
        pa, pb = c.arc(c.ANG[k]), c.arc(c.ANG[k + 1])
        Lc = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
        tdir = ((pb[0] - pa[0]) / Lc, (pb[1] - pa[1]) / Lc)
        am = (c.ANG[k] + c.ANG[k + 1]) / 2
        nout = (math.cos(am), math.sin(am))
        pm = ((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2)
        m = basis_matrix(pm, tdir, nout)
        with fb.at(m), em.at(m):
            h = Lc / 2
            # sill band: a low structural wall in front of the glass, capped in brushed metal, a light line on the cap
            fb.box((-h, -0.62, c.FLOOR_BOTTOM), (h, 0.4, c.SILL - 0.04), L.STRUCT)
            fb.box((-h, -0.66, c.SILL - 0.04), (h, -0.06, c.SILL + 0.02), L.TRIM)
            em.lamp_box((-h + 0.3, -0.6, c.SILL + 0.02), (h - 0.3, -0.56, c.SILL + 0.026), "cool_dim", L.LAMP_DIM)
            with fb.at(T(0, -0.62, 0)):
                # the visible face of the sill (0.9 m above the well floor): three layered panels, a vent, a lit foot line
                w3 = (Lc - 0.9) / 3
                for i in range(3):
                    s0 = -h + 0.45 + i * w3 + 0.03
                    s1 = -h + 0.45 + (i + 1) * w3 - 0.03
                    WL.panel(fb, s0, s1, -0.52, c.SILL - 0.12, bolts=True)
                WL.vent(fb, -0.35, 0.35, -0.42, -0.06, 5, t=-0.026)
            em.lamp_box((-h + 0.5, -0.665, -0.58), (h - 0.5, -0.658, -0.565), "cool_dim", L.LAMP_DIM)
            # head beam: chamfered soffit, a light line on the chamfer edge
            prof = [(-0.55, c.HEAD + 0.22), (-0.30, c.HEAD), (0.4, c.HEAD), (0.4, CE + 0.3), (-0.55, CE + 0.3)]
            fb.extrude_x(prof, -h, h, L.STRUCT)
            fb.extrude_x([(-0.56, c.HEAD + 0.22), (-0.30, c.HEAD - 0.02), (-0.24, c.HEAD - 0.02), (-0.50, c.HEAD + 0.24)], -h, h, L.TRIM)
            em.lamp_box((-h + 0.25, -0.31, c.HEAD - 0.024), (h - 0.25, -0.26, c.HEAD - 0.018), "white_cool", L.LAMP_HOT)
            # pane frames: rails top and bottom, on the glass plane
            fb.box((-h, 0.0, c.SILL + 0.02), (h, 0.16, c.SILL + 0.09), L.STRUCT)
            fb.box((-h, 0.0, c.HEAD - 0.09), (h, 0.16, c.HEAD), L.STRUCT)
    # mullions
    for k, a in enumerate(c.ANGD):
        heavy = k in (0, len(c.ANGD) - 1)
        w = 0.5 if heavy else 0.26
        p = c.arc(math.radians(a))
        m = T(p[0], p[1], 0) @ Rz(a)
        with fb.at(m), em.at(m):
            poly = [(-0.35, -w / 2 + 0.05), (-0.30, -w / 2), (0.35, -w / 2), (0.35, w / 2), (-0.30, w / 2), (-0.35, w / 2 - 0.05)]
            fb.prism(poly, c.FLOOR_BOTTOM, CE + 0.3, L.STRUCT)
            fb.box((-0.39, -w / 2 - 0.02, c.SILL), (-0.35, w / 2 + 0.02, c.HEAD), L.TRIM)
            fb.box((-0.40, -w / 2 + 0.03, c.SILL + 0.08), (-0.39, w / 2 - 0.03, c.HEAD - 0.08), L.STRUCT)
            em.lamp_box((-0.408, -0.007, c.SILL + 0.25), (-0.40, 0.007, c.HEAD - 0.25), "cool_dim", L.LAMP_DIM)
            for z in (c.SILL + 0.35, 1.5, 2.7, c.HEAD - 0.35):
                fb.box((-0.43, -w / 2 - 0.03, z - 0.05), (-0.35, w / 2 + 0.03, z + 0.05), L.TRIM)
                for sy in (-w / 2 + 0.02, w / 2 - 0.02):
                    fb.cyl((-0.43, sy, z), (-0.44, sy, z), 0.012, L.TRIM, seg=8)
    return b.build(name)


def build_window_glass(c: SH.Ctx, name: str = "SM_BRG3_WindowGlass"):
    fb = FB()
    for k in range(len(c.ANG) - 1):
        pa, pb = c.arc(c.ANG[k], c.R + 0.1), c.arc(c.ANG[k + 1], c.R + 0.1)
        ln = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
        ang = math.degrees(math.atan2(pb[1] - pa[1], pb[0] - pa[0]))
        fb.cbox(((pa[0] + pb[0]) / 2, (pa[1] + pb[1]) / 2, (c.SILL + c.HEAD) / 2), (0.03, ln - 0.1, c.HEAD - c.SILL - 0.16),
                L.GLASS, Rz(ang - 90.0))
    obj = fb.to_object(name)
    return A.finish(obj, bevel=0.0)


# ------------------------------------------------------------------------------------------------------------- back wall
def build_back_wall(c: SH.Ctx, name: str = "SM_BRG3_WallBack"):
    D = c.D
    b = Parts(bevel=0.006, fine_bevel=0.003)
    fb, em = b.body, b.emit
    rng = random.Random(77)
    wall = SH.Wall((c.BACK_X, -c.BACK_HW), (c.BACK_X, c.BACK_HW), 0, n_out=(-1.0, 0.0))
    Lw = wall.L
    CE = c.CEIL
    doors = sorted(D["doors"], key=lambda d: d["pos"][1])
    dsc = [d["pos"][1] + c.BACK_HW for d in doors]                      # door centres along s
    dw = doors[0]["width"]
    dh = doors[0]["height"]
    with fb.at(wall.matrix()), em.at(wall.matrix()), b.fine.at(wall.matrix()):
        # core with the door openings (the sliding leaves run in the thickness)
        edges = [0.0]
        for s in dsc:
            edges += [s - dw / 2, s + dw / 2]
        edges.append(Lw)
        for i in range(0, len(edges), 2):
            a, bnd = edges[i], edges[i + 1]
            fb.box((a, 0.0, 0.0), (bnd, 0.30, CE), L.STRUCT)
            fb.box((a, 0.30, 0.0), (bnd, 0.34, CE), L.COMPOSITE)
        for s in dsc:
            fb.box((s - dw / 2, 0.0, dh), (s + dw / 2, 0.30, CE), L.STRUCT)
            fb.box((s - dw / 2, 0.30, dh), (s + dw / 2, 0.34, CE), L.COMPOSITE)
        # door frames: brushed jambs and lintel, a command-colour line inside, threshold, status bars
        for s in dsc:
            fb.box((s - dw / 2 - 0.16, -0.06, 0.0), (s - dw / 2, 0.0, dh + 0.14), L.TRIM)
            fb.box((s + dw / 2, -0.06, 0.0), (s + dw / 2 + 0.16, 0.0, dh + 0.14), L.TRIM)
            fb.box((s - dw / 2, -0.06, dh), (s + dw / 2, 0.0, dh + 0.14), L.TRIM)
            fb.box((s - dw / 2 - 0.16, -0.075, dh + 0.14), (s + dw / 2 + 0.16, -0.02, dh + 0.19), L.STRUCT)
            fb.box((s - dw / 2 - 0.05, -0.02, 0.0), (s + dw / 2 + 0.05, 0.0, 0.02), L.TRIM)
            em.lamp_box((s - dw / 2 + 0.005, -0.03, 0.15), (s - dw / 2 + 0.02, -0.02, dh - 0.05), "command", L.LAMP)
            em.lamp_box((s + dw / 2 - 0.02, -0.03, 0.15), (s + dw / 2 - 0.005, -0.02, dh - 0.05), "command", L.LAMP)
            em.lamp_box((s - dw / 2 + 0.03, -0.03, dh - 0.03), (s + dw / 2 - 0.03, -0.02, dh - 0.016), "command", L.LAMP)
            for sd in (-1, 1):
                sx = s + sd * (dw / 2 + 0.3)
                fb.box((sx - 0.09, -0.06, 1.0), (sx + 0.09, -0.02, 1.55), L.COMPOSITE)             # the door's keypad box
                em.lamp_box((sx - 0.05, -0.064, 1.32), (sx + 0.05, -0.06, 1.42), "green", L.LAMP)
                for iz in range(3):
                    fb.box((sx - 0.05, -0.068, 1.06 + iz * 0.075), (sx + 0.05, -0.06, 1.10 + iz * 0.075), L.RUBBER)
        # rib grid: at the door frame edges and the wall ends
        ribs = [0.0] + [x for s in dsc for x in (s - dw / 2 - 0.30, s + dw / 2 + 0.30)] + [Lw]
        for s in ribs:
            WL.rib(fb, s, 0.0, WL.Z_CORNICE, wide=(s in (0.0, Lw)))
        # plinth with a light line
        for (a, bnd) in ((0.3, dsc[0] - dw / 2 - 0.3 - 0.14), (dsc[0] + dw / 2 + 0.44, dsc[1] - dw / 2 - 0.44), (dsc[1] + dw / 2 + 0.44, Lw - 0.3)):
            fb.box((a, -0.045, 0.02), (bnd, 0.0, WL.Z_PLINTH), L.TRIM)
            em.lamp_box((a + 0.15, -0.048, 0.135), (bnd - 0.15, -0.044, 0.15), "cool_dim", L.LAMP_DIM)
        # the two end sections: equipment, like the side walls
        sec_l = (0.3 + 0.1, dsc[0] - dw / 2 - 0.44)
        sec_r = (dsc[1] + dw / 2 + 0.44, Lw - 0.4)
        WL.bay_module(fb, "lockers", sec_l[0], sec_l[1], rng, "command", 1)
        WL.bay_module(fb, "safety", sec_r[0], sec_r[1], rng, "command", 2)
        # between the doors: layered panels behind the master display (the display itself is SM_BRG3_MasterDisplay)
        s0, s1 = dsc[0] + dw / 2 + 0.44, dsc[1] - dw / 2 - 0.44
        WL.panel(fb, s0, s1, WL.Z_LOW0, 1.0, bolts=True)
        WL.panel(fb, s0, s1, 3.5, 3.95, bolts=True, raised=False)
        # above the doors: layered lintel panels with a label, a cable run over everything
        for s in dsc:
            WL.panel(fb, s - 0.95, s + 0.95, dh + 0.26, 3.4, raised=False)
        WL.cable_runs(fb, 0.3, Lw - 0.3, rng)
        WL.cornice(fb, Lw)
    return b.build(name)


def build_master_display(c: SH.Ctx, name: str = "SM_BRG3_MasterDisplay"):
    """The ship-systems wall display: a brushed frame standing off the wall, the screen, a status shelf. Origin at the wall
    plane (x = back wall), centred in y, on the floor level; +x into the room."""
    md = c.D["master_display"]
    b = Parts(bevel=0.007, fine_bevel=0.003)
    fb, em = b.body, b.emit
    w, h, z0 = md["width"], md["height"], md["bottom"]
    z1 = z0 + h
    fw = 0.09
    # frame: four brushed members stepped in two layers
    fb.box((0.0, -w / 2 - fw, z0 - fw), (0.15, w / 2 + fw, z0), L.TRIM)
    fb.box((0.0, -w / 2 - fw, z1), (0.15, w / 2 + fw, z1 + 0.06), L.TRIM)
    fb.box((0.0, -w / 2 - fw, z0), (0.15, -w / 2, z1), L.TRIM)
    fb.box((0.0, w / 2, z0), (0.15, w / 2 + fw, z1), L.TRIM)
    fb.box((0.06, -w / 2 - fw - 0.05, z0 - fw - 0.05), (0.17, w / 2 + fw + 0.05, z0 - fw), L.STRUCT)
    fb.box((0.06, -w / 2 - fw - 0.05, z1 + 0.06), (0.17, w / 2 + fw + 0.05, z1 + 0.11), L.STRUCT)
    fb.box((0.0, -w / 2, z0), (0.10, w / 2, z1), L.COMPOSITE)                                    # the back plate behind the glass
    b.emit.screen((0.118, 0.0, (z0 + z1) / 2), w, h, "SCREEN_master_1", (1, 0, 0), up=(0, 0, 1))
    # a thin lit border round the picture, in the command colour
    em.lamp_box((0.114, -w / 2 - 0.004, z0 - 0.012), (0.126, w / 2 + 0.004, z0), "command", L.LAMP)
    em.lamp_box((0.114, -w / 2 - 0.004, z1), (0.126, w / 2 + 0.004, z1 + 0.012), "command", L.LAMP)
    # the shelf below: a status strip of small lamps and the ventilation slots
    fb.box((0.0, -w / 2 - fw, z0 - 0.26), (0.30, w / 2 + fw, z0 - fw - 0.05), L.STRUCT)
    fb.box((0.0, -w / 2 - fw, z0 - fw - 0.05), (0.32, w / 2 + fw, z0 - fw - 0.03), L.TRIM)
    for k in range(26):
        y = -w / 2 + 0.25 + k * (w - 0.5) / 25
        cell = "green" if k % 7 else "amber"
        em.lamp_box((0.322, y - 0.02, z0 - fw - 0.13), (0.328, y + 0.02, z0 - fw - 0.09), cell, L.LAMP_DIM)
    for k in range(10):
        y = -w / 2 + 0.6 + k * 0.1
    # brackets to the wall
    for y in (-w / 2 - 0.02, -w / 4, 0.0, w / 4, w / 2 + 0.02):
        fb.box((-0.02, y - 0.05, z0 - 0.02), (0.06, y + 0.05, z0 + 0.4), L.STRUCT)
        fb.box((-0.02, y - 0.05, z1 - 0.4), (0.06, y + 0.05, z1 + 0.02), L.STRUCT)
    return b.build(name)


# ---------------------------------------------------------------------------------------------------------------- rails
def run_box(fb: FB, p0, p1, z0: float, z1: float, w: float, mat: str, offset: float = 0.0, cell: str | None = None):
    (x0, y0), (x1, y1) = p0, p1
    ln = math.hypot(x1 - x0, y1 - y0)
    ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
    nx, ny = -(y1 - y0) / ln, (x1 - x0) / ln
    cx, cy = (x0 + x1) / 2 + nx * offset, (y0 + y1) / 2 + ny * offset
    if cell:
        return fb.lamp_cbox((cx, cy, (z0 + z1) / 2), (ln, w, z1 - z0), cell, mat, Rz(ang))
    return fb.cbox((cx, cy, (z0 + z1) / 2), (ln, w, z1 - z0), mat, Rz(ang))


def build_rails(c: SH.Ctx, name: str = "SM_BRG3_Rails", glass_name: str = "SM_BRG3_RailGlass"):
    """Railings along the well edge and the wing edges: blade posts, a handrail with a light line under it, a mid rail, a lit
    kick rail; the glass infill is a separate translucent mesh."""
    b = Parts(bevel=0.004, fine_bevel=0.002)
    fb, em = b.body, b.emit
    gl = FB()
    sw = c.STAIR_W
    runs = [((c.WELL_X - 0.08, -c.WELL_HW + sw), (c.WELL_X - 0.08, c.WELL_HW - sw), 0.0)]
    for s in (1, -1):
        runs.append(((c.WELL_X + 0.75, s * (c.WELL_HW + 0.08)), (c.xe - 0.45, s * (c.WELL_HW + 0.08)), 0.0))
    for (p0, p1, z) in runs:
        ln = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        n = max(2, int(math.ceil(ln / 1.4)) + 1)
        ang = math.degrees(math.atan2(p1[1] - p0[1], p1[0] - p0[0]))
        for k in range(n):
            f = k / (n - 1)
            x, y = lerp(p0[0], p1[0], f), lerp(p0[1], p1[1], f)
            fb.cbox((x, y, 0.5), (0.028, 0.07, 1.0), L.TRIM, Rz(ang))                    # blade post
            fb.cbox((x, y, 0.03), (0.06, 0.14, 0.06), L.STRUCT, Rz(ang))                 # foot plate
            fb.cbox((x, y, 1.03), (0.05, 0.09, 0.05), L.STRUCT, Rz(ang))                 # top cap
        # handrail, light line under it, mid rail, kick rail with a lit line
        p3a, p3b = (p0[0], p0[1], 1.06), (p1[0], p1[1], 1.06)
        fb.cyl(p3a, p3b, 0.028, L.TRIM, seg=14)
        run_box(em, p0, p1, 1.005, 1.012, 0.02, L.LAMP_DIM, cell="cool_dim")
        fb.cyl((p0[0], p0[1], 0.62), (p1[0], p1[1], 0.62), 0.011, L.TRIM, seg=8)
        run_box(fb, p0, p1, 0.06, 0.14, 0.05, L.STRUCT)
        run_box(em, p0, p1, 0.10, 0.108, 0.052, L.LAMP_DIM, cell="command_dim")
        run_box(gl, p0, p1, 0.16, 0.96, 0.012, L.GLASS)
    return b.build(name), A.finish(gl.to_object(glass_name), bevel=0.0)


# ---------------------------------------------------------------------------------------------------------- viewscreen
def viewscreen_geom(c: SH.Ctx) -> dict:
    v = c.D["viewscreen"]
    R = v["radius"]
    half = math.degrees((v["width"] / 2) / R)
    return {"R": R, "half_deg": half, "z0": v["bottom"], "z1": v["bottom"] + v["height"], "w": v["width"], "h": v["height"]}


def build_viewscreen_frame(c: SH.Ctx, name: str = "SM_BRG3_ViewscreenFrame"):
    """The projector frame of the main viewscreen: a top and a bottom emitter rail on the arc of the image, two slim pylons
    at the ends, hangers and posts. Nothing stands in the image area: switched off, the window is what you see."""
    g = viewscreen_geom(c)
    R, ha, z0, z1 = g["R"], g["half_deg"], g["z0"], g["z1"]
    b = Parts(bevel=0.006, fine_bevel=0.003)
    fb, em = b.body, b.emit
    CE = c.CEIL
    ext = ha + 1.5
    # top rail: a slanted brushed bar, an emitter slot facing the image
    fb.arc_sweep([(-0.10, 0.0), (0.07, 0.0), (0.07, 0.15), (-0.05, 0.15)], 0, 0, R, -ext, ext, L.TRIM, seg=44, z0=z1)
    fb.arc_sweep([(-0.08, -0.012), (0.05, -0.012), (0.05, 0.0), (-0.08, 0.0)], 0, 0, R, -ext, ext, L.STRUCT, seg=44, z0=z1)
    em.lamp_arc([(-0.085, 0.0), (0.0, 0.0), (0.0, 0.008), (-0.085, 0.008)], 0, 0, R, -ha, ha, "white_cool", L.LAMP_HOT, seg=44, z0=z1 - 0.02)
    # bottom rail: the mirror image, emitter slot facing up
    fb.arc_sweep([(-0.05, 0.0), (0.07, 0.0), (0.07, 0.15), (-0.10, 0.15)], 0, 0, R, -ext, ext, L.TRIM, seg=44, z0=z0 - 0.15)
    fb.arc_sweep([(-0.08, 0.0), (0.05, 0.0), (0.05, 0.012), (-0.08, 0.012)], 0, 0, R, -ext, ext, L.STRUCT, seg=44, z0=z0 - 0.162)
    em.lamp_arc([(-0.085, 0.0), (0.0, 0.0), (0.0, 0.008), (-0.085, 0.008)], 0, 0, R, -ha, ha, "white_cool", L.LAMP_HOT, seg=44, z0=z0 + 0.012)
    # pylons at both ends: slim fins from the well floor to the ceiling, an edge emitter facing the image
    for sd in (-1, 1):
        a = sd * (ha + 1.3)
        px, py = polar(0, 0, R, a)
        m = T(px, py, 0) @ Rz(a)
        with fb.at(m), em.at(m):
            fb.prism([(-0.09, -0.16), (0.09, -0.16), (0.09, 0.16), (-0.09, 0.16)], c.WELL, CE, L.TRIM)
            fb.prism([(-0.06, -0.12), (0.06, -0.12), (0.06, 0.12), (-0.06, 0.12)], c.WELL - 0.02, c.WELL + 0.25, L.STRUCT)
            fb.box((-0.10, -0.18, z0 + 0.4), (0.10, 0.18, z0 + 0.62), L.STRUCT)
            em.lamp_box((-0.093, -0.006 - sd * 0.156, z0 - 0.05), (-0.087, 0.006 - sd * 0.156, z1 + 0.05), "white_cool", L.LAMP)
    # posts under the bottom rail and hangers over the top rail
    for a in (-ha * 0.9, -ha * 0.45, 0.0, ha * 0.45, ha * 0.9):
        px, py = polar(0, 0, R + 0.0, a)
        fb.cyl((px, py, c.WELL), (px, py, z0 - 0.15), 0.035, L.TRIM, seg=12)
        fb.cyl((px, py, c.WELL), (px, py, c.WELL + 0.06), 0.09, L.STRUCT, seg=16)
        fb.cyl((px, py, z1 + 0.15), (px, py, CE + 0.02), 0.025, L.TRIM, seg=10)
    return b.build(name)


def build_viewscreen_image(c: SH.Ctx, name: str = "SM_BRG3_ViewscreenImage"):
    g = viewscreen_geom(c)
    fb = FB()
    fb.screen_arc(0.0, 0.0, g["R"], -g["half_deg"], g["half_deg"], g["z0"], g["z1"], "SCREEN_viewscreen_1", inward=True, seg=40)
    return A.finish(fb.to_object(name), bevel=0.0)
