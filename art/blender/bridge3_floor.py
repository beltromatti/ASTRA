"""ASN Aquila bridge v3: the deck (ARTE-PLANCIA-2).

The floor mirrors the ceiling: the upper deck is plated in a polar grid whose radial seams line up with the ribs of the ceiling (every
10 degrees from the dais), the well is plated in running bond round a *compass dial* inlaid round the holographic table (dark carbon,
brass rings, a bearing scale with numerals, four lit chevrons), the dais carries the Captain's compass star, and the aft half carries the
ASTRA Navy emblem in brass and light with its motto in real lettering, facing the way you walk in from the doors. Light comes from
inlays (dashes and short runs, not endless lines), brass is the warm line of the command deck, everything small (hatches, cable
trunking, sockets, vents) sits where the crew would put it. Origin = bridge origin, layout coordinates, Z up.
"""
from __future__ import annotations

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bridge3_lib as L  # noqa: E402
import bridge3_shell as SH  # noqa: E402
from bridge3_lib import FB, Parts, Rz, lerp, polar  # noqa: E402

PLATE_T = 0.012


def ring_poly(cx: float, cy: float, r: float, n: int = 64, a0: float = 0.0, a1: float = 360.0):
    return [polar(cx, cy, r, lerp(a0, a1, k / n)) for k in range(n + 1 if a1 - a0 < 359.99 else n)]


def annulus_sector(cx, cy, r0, r1, a0, a1, gap_m: float = 0.0):
    """A convex quad (trapezoid on the chords) between the radii r0, r1 and the angles a0, a1 (degrees), shrunk by gap_m on every side."""
    g_r = gap_m
    g_a0 = math.degrees(gap_m / max(r0, 0.5) / 2.0)
    g_a1 = math.degrees(gap_m / max(r1, 0.5) / 2.0)
    return [polar(cx, cy, r0 + g_r, a0 + g_a0), polar(cx, cy, r0 + g_r, a1 - g_a0), polar(cx, cy, r1 - g_r, a1 - g_a1), polar(cx, cy, r1 - g_r, a0 + g_a1)]


def lamp_dash(em: FB, cx, cy, r, a0, a1, z, cell: str, w: float = 0.02, mat: str = L.LAMP_DIM, h: float = 0.004):
    """An arc of light as short straight runs (one per ~4 degrees)."""
    n = max(1, int(abs(a1 - a0) / 4.0))
    for k in range(n):
        p0 = polar(cx, cy, r, lerp(a0, a1, k / n))
        p1 = polar(cx, cy, r, lerp(a0, a1, (k + 1) / n))
        SH.line_lamp(em, p0, p1, z, w, h, cell, mat)


def brass_arc(fb: FB, cx, cy, r, a0, a1, z, w: float = 0.02, h: float = 0.006):
    """A brass inlay along an arc: swept profile (flush with the deck, standing `h` proud)."""
    n = max(2, int(abs(a1 - a0) / 4.0))
    fb.arc_sweep([(-w / 2, 0.0), (w / 2, 0.0), (w / 2, h), (-w / 2, h)], cx, cy, r, a0, a1, L.BRASS, seg=n, z0=z, loop=(a1 - a0 >= 359.99))


def brass_line(fb: FB, p0, p1, z, w: float = 0.02, h: float = 0.006):
    (x0, y0), (x1, y1) = p0, p1
    ln = math.hypot(x1 - x0, y1 - y0)
    if ln < 1e-4:
        return
    ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
    fb.cbox(((x0 + x1) / 2, (y0 + y1) / 2, z + h / 2), (ln, w, h), L.BRASS, Rz(ang))


def star_poly(cx, cy, r_long: float, r_diag: float, r_short: float, rot_deg: float = 0.0):
    """The eight-pointed compass star of the emblem (16 vertices, long points N/E/S/W at rot 0 = +x forward)."""
    pts = []
    for k in range(16):
        rad = {0: r_long, 2: r_diag}.get(k % 4, r_short)
        pts.append(polar(cx, cy, rad, rot_deg + 22.5 * k))
    return pts


def ring_text(fb: FB, text: str, cx, cy, r, mid_deg: float, z, height: float, mat: str, cell: str | None, bottom: bool, tracking: float = 0.035):
    """Letters along an arc on the floor, readable from outside the circle at the top (bottom=False: letters stand on the arc, their tops
    point outwards) or from inside at the bottom (bottom=True: the tops point to the centre). `mid_deg` = the middle of the text, in degrees
    from +x towards +y (layout)."""
    widths = [L.text_proto(ch)["width"] * (height / 0.70) if ch != " " else height * 0.45 for ch in text]
    total = sum(widths) + tracking * (len(text) - 1)
    a_total = math.degrees(total / r)
    a = mid_deg - a_total / 2 if not bottom else mid_deg + a_total / 2
    for ch, wch in zip(text, widths):
        half = math.degrees((wch / 2 + tracking / 2) / r)
        a_c = a + half if not bottom else a - half
        if ch != " ":
            x, y = polar(cx, cy, r, a_c)
            out = (math.cos(math.radians(a_c)), math.sin(math.radians(a_c)), 0.0)
            up = out if not bottom else (-out[0], -out[1], 0.0)
            fb.text(ch, (x, y, z), height, (0, 0, 1), mat, up=up, cell=cell)
        a += 2 * half if not bottom else -2 * half


# =============================================================================================================== the big pieces
def compass_dial(b: Parts, c: SH.Ctx, z: float) -> None:
    """The dial round the holographic table (well floor): carbon annulus, brass rings, bearing scale and numerals, four chevrons."""
    fb, em, fine = b.body, b.emit, b.fine
    tx, ty = c.table
    r_in, r_out = c.table_r + 0.12, 2.45
    # the annulus: 24 carbon sectors with hairline gaps (the gaps show the structure under them)
    for k in range(24):
        quad = annulus_sector(tx, ty, r_in, r_out, k * 15.0, (k + 1) * 15.0, 0.014)
        fb.prism(quad, z - PLATE_T, z + 0.002, L.COMPOSITE)
    # brass: the inner and outer edge, one ring in the middle of the scale band
    brass_arc(fb, tx, ty, r_in + 0.015, 0, 360, z + 0.002, 0.03, 0.005)
    brass_arc(fb, tx, ty, r_out - 0.02, 0, 360, z + 0.002, 0.045, 0.007)
    brass_arc(fb, tx, ty, 2.04, 0, 360, z + 0.002, 0.014, 0.004)
    # the lit track between the inner edge and the scale
    lamp_dash(em, tx, ty, 1.74, 0, 360, z + 0.002, "command_dim", 0.016)
    lamp_dash(em, tx, ty, 1.90, 0, 360, z + 0.002, "cool_dim", 0.008)
    # the bearing scale: a tick every 5 degrees, longer every 30, numerals at every 30 except the four cardinal points (those are words)
    for k in range(72):
        a = 5.0 * k
        long_ = (k % 6 == 0)
        px, py = polar(tx, ty, 2.075 if not long_ else 2.115, a)
        em.cbox((px, py, z + 0.0035), (0.15 if long_ else 0.075, 0.009 if long_ else 0.006, 0.004), L.BRASS, Rz(a))
    cards = {0: "FWD", 90: "STBD", 180: "AFT", 270: "PORT"}
    for a in range(0, 360, 30):
        px, py = polar(tx, ty, 2.30, float(a))
        out = (math.cos(math.radians(a)), math.sin(math.radians(a)), 0.0)
        if a in cards:                                              # the words are lit, the numbers are brass
            em.text(cards[a], (px, py, z + 0.0035), 0.075, (0, 0, 1), L.LAMP_DIM, up=out, cell="warm_dim" if a == 0 else "cool_dim", tracking=0.012)
        else:
            fine.text(f"{a:03d}", (px, py, z + 0.0035), 0.06, (0, 0, 1), L.BRASS, up=out, tracking=0.008)
    # chevrons (lit) pointing outwards on the four cardinal points, the bow one in amber
    for a, cell in ((0.0, "amber"), (90.0, "command"), (180.0, "command"), (270.0, "command")):
        tip = polar(tx, ty, r_in + 0.46, a)
        left = polar(tx, ty, r_in + 0.12, a - 9.0)
        right = polar(tx, ty, r_in + 0.12, a + 9.0)
        mid = polar(tx, ty, r_in + 0.24, a)
        em.lamp_face([(*left, z + 0.0036), (*tip, z + 0.0036), (*right, z + 0.0036), (*mid, z + 0.0036)], cell, (0, 0, 1), L.LAMP)
    # eight lit spokes between the track and the inner edge
    for k in range(8):
        a = 45.0 * k + 22.5
        SH.line_lamp(em, polar(tx, ty, r_in + 0.06, a), polar(tx, ty, r_in + 0.26, a), z + 0.0025, 0.012, 0.003, "cool_dim", L.LAMP_DIM)


def compass_star_inlay(b: Parts, cx, cy, z: float, r: float, rot: float, text: bool, big: bool) -> None:
    """The ASTRA Navy emblem as an inlay: a dark carbon disc, brass double ring, the eight-pointed star in brass with a lit rim, and
    (big) the motto in lettering. rot = the direction of the long 'north' point (degrees from +x towards +y: 0 = forward)."""
    fb, em = b.body, b.emit
    fb.prism(ring_poly(cx, cy, r * 1.04, 72), z - 0.004, z + 0.004, L.COMPOSITE)
    for ri, ro in ((0.90 * r, 0.97 * r), (0.58 * r, 0.63 * r)):
        brass_arc(fb, cx, cy, (ri + ro) / 2, 0, 360, z + 0.004, ro - ri, 0.006)
    brass_arc(fb, cx, cy, r * 1.035, 0, 360, z + 0.004, 0.02, 0.008)
    star = star_poly(cx, cy, 0.72 * r, 0.40 * r, 0.11 * r, rot)
    fb.prism(star, z + 0.004, z + 0.010, L.BRASS)
    star_in = star_poly(cx, cy, 0.66 * r, 0.35 * r, 0.085 * r, rot)
    for k in range(16):
        p0, p1 = star_in[k], star_in[(k + 1) % 16]
        SH.line_lamp(em, p0, p1, z + 0.0105, 0.014 if big else 0.01, 0.003, "command", L.LAMP_DIM)
    fb.cyl((cx, cy, z + 0.010), (cx, cy, z + 0.014), 0.065 * r, L.DGLASS, seg=24)
    em.lamp_cyl((cx, cy, z + 0.0142), (cx, cy, z + 0.0155), 0.03 * r, "command", L.LAMP, seg=16)
    if text:
        ring_text(em, "ASTRA NAVY", cx, cy, 0.775 * r, rot, z + 0.0045, 0.115 * r, L.LAMP_DIM, "warm_dim", bottom=False, tracking=0.06 * r)
        ring_text(em, "CONCORD · LAW · LIGHT", cx, cy, 0.775 * r, rot + 180.0, z + 0.0045, 0.095 * r, L.LAMP_DIM, "warm_dim", bottom=True, tracking=0.035 * r)


# ================================================================================================================== the deck
def build_deck(c: SH.Ctx, name: str = "SM_BRG3_Deck"):
    b = Parts(bevel=0.005, fine_bevel=0.003)
    b.bevel_segments = 1
    fb, em = b.body, b.emit
    rng = random.Random(3)
    yw = c.side_wall_y(c.WELL_X, 1)
    UP, WL, DS = c.UPPER, c.WELL, c.DAIS
    tx, ty = c.table

    # ---- base slabs (the structural deck under the plates)
    upper = [(c.BACK_X, -c.BACK_HW), (c.WELL_X, -yw), (c.WELL_X, yw), (c.BACK_X, c.BACK_HW)]
    wings = []
    for s in (1, -1):
        wings.append([(c.WELL_X, s * c.WELL_HW), (c.xe, s * c.WELL_HW), c.arc(c.ANG[5] if s > 0 else -c.ANG[5]),
                      c.arc(c.ANG[-1] if s > 0 else -c.ANG[-1]), (c.WELL_X, s * yw)])
    a_m20, a_0, a_20 = c.arc(c.ANG[2]), c.arc(c.ANG[3]), c.arc(c.ANG[4])
    well = [(c.WELL_X, -c.WELL_HW), (c.xe, -c.WELL_HW), a_m20, a_0, a_20, (c.xe, c.WELL_HW), (c.WELL_X, c.WELL_HW)]
    for poly, z in [(upper, UP)] + [(w, UP) for w in wings] + [(well, WL)]:
        fb.prism(poly, c.FLOOR_BOTTOM, z - 0.012, L.STRUCT)

    dais_poly = SH.ellipse_poly(0.0, 0.0, c.dais_hx, c.dais_hy, 40, grow=0.16)
    stair_boxes = [(c.WELL_X - 0.05, y - c.STAIR_W / 2 - 0.05, c.WELL_X + 0.85, y + c.STAIR_W / 2 + 0.05) for y in c.STAIR_Y]
    EMB_X, EMB_R = -5.95, 2.10                                   # the big emblem: centre and radius
    hatches = []

    def in_stairs_poly(clipped):
        return any(all(b0[0] <= q[0] <= b0[2] and b0[1] <= q[1] <= b0[3] for q in clipped) for b0 in stair_boxes)

    def add_plate(clipped, z, mat=L.DECK, hatch_ok=True):
        faces = fb.prism(clipped, z - PLATE_T, z, mat)
        SH.plate_uv(fb, faces, rng, 1.0)
        if SH.poly_area(clipped) > 0.45:                           # four countersunk bolts, a hand's width in from the corners
            cx_ = sum(q[0] for q in clipped) / len(clipped)
            cy_ = sum(q[1] for q in clipped) / len(clipped)
            for q in clipped:
                d = math.hypot(q[0] - cx_, q[1] - cy_)
                k = min(0.12 / max(d, 0.2), 0.5)
                bx, by = q[0] + (cx_ - q[0]) * k, q[1] + (cy_ - q[1]) * k
                em.face([(bx + 0.0085 * math.cos(math.radians(60 * j)), by + 0.0085 * math.sin(math.radians(60 * j)), z + 0.0009) for j in range(6)],
                        L.TRIM, (0, 0, 1))
        if hatch_ok and rng.random() < 0.05 and SH.poly_area(clipped) > 1.4:
            cx_ = sum(q[0] for q in clipped) / len(clipped)
            cy_ = sum(q[1] for q in clipped) / len(clipped)
            hatches.append((cx_, cy_, z))

    # ---- upper deck: polar plates, 10 degree sectors (the ceiling's ribs), radial bands from the dais; the emblem covers its own disc
    radii = [1.0, 2.35, 3.7, 5.1, 6.6, 8.2, 10.0, 12.2]
    for k in range(36):
        for r0, r1 in zip(radii[:-1], radii[1:]):
            quad = annulus_sector(0.0, 0.0, r0, r1, k * 10.0, (k + 1) * 10.0, 0.016)
            clipped = SH.clip_convex(quad, upper, 0.03)
            if len(clipped) < 3 or SH.poly_area(clipped) < 0.03:
                continue
            if all(SH.inside_poly(dais_poly, q, 0.0) for q in clipped):
                continue
            ex = [math.hypot(q[0] - EMB_X, q[1]) for q in clipped]
            if all(e < EMB_R * 1.06 for e in ex):                  # hidden under the emblem's disc
                continue
            add_plate(clipped, UP, hatch_ok=(r0 > 3.0 and ((k + int(r0)) % 3 == 0)))
    for w in wings:                                                # the wings beside the well: running bond, as the well's
        plates_bond(fb, w, UP, add_plate)
    # ---- well: running-bond plates outside the dial, the dial's own sectors inside
    dial_r = 2.45

    def skip_well(clipped):
        return in_stairs_poly(clipped) or all(math.hypot(q[0] - tx, q[1] - ty) < dial_r + 0.02 for q in clipped)

    plates_bond(fb, well, WL, add_plate, skip=skip_well, pw=1.8, ph=0.9)
    fb.prism(ring_poly(tx, ty, c.table_r + 0.14, 48), WL - PLATE_T, WL, L.DECK)          # the floor under the table's dish
    compass_dial(b, c, WL)

    # ---- hatch plates: a groove, two flush pull rings, a hinge side
    for (hx, hy, hz) in hatches[:8]:
        fb.box((hx - 0.36, hy - 0.26, hz), (hx + 0.36, hy + 0.26, hz + 0.006), L.TRIM)
        fb.box((hx - 0.33, hy - 0.23, hz + 0.006), (hx + 0.33, hy + 0.23, hz + 0.01), L.DECK)
        for sx in (-0.2, 0.2):
            fb.cyl((hx + sx, hy, hz + 0.012), (hx + sx, hy, hz + 0.016), 0.035, L.TRIM, seg=14)
        for sx in (-0.3, 0.3):
            for sy in (-0.2, 0.2):
                fb.cyl((hx + sx, hy + sy, hz + 0.01), (hx + sx, hy + sy, hz + 0.014), 0.008, L.TRIM, seg=8)
        em.lamp_box((hx + 0.24, hy - 0.2, hz + 0.01), (hx + 0.3, hy - 0.18, hz + 0.0115), "green_dim", L.LAMP_DIM)

    # ---- the big emblem in the aft half, 'north' = forward
    compass_star_inlay(b, EMB_X, 0.0, UP, EMB_R, 0.0, text=True, big=True)

    # ---- the command dais: a raised platform with a lit lip, the Captain's compass star on its top
    fb.prism(SH.ellipse_poly(0, 0, c.dais_hx, c.dais_hy, 40), UP - 0.05, DS - 0.03, L.STRUCT)
    fb.prism(SH.ellipse_poly(0, 0, c.dais_hx - 0.02, c.dais_hy - 0.02, 40), DS - 0.03, DS, L.DECK)
    ring_in = SH.ellipse_poly(0, 0, c.dais_hx - 0.02, c.dais_hy - 0.02, 40)
    ring_out = SH.ellipse_poly(0, 0, c.dais_hx + 0.05, c.dais_hy + 0.05, 40)
    n = len(ring_in)
    for k in range(n):
        kk = (k + 1) % n
        fb.prism([ring_in[k], ring_out[k], ring_out[kk], ring_in[kk]], DS - 0.05, DS + 0.012, L.BRASS)
    pts = SH.ellipse_poly(0, 0, c.dais_hx + 0.06, c.dais_hy + 0.06, 40)
    for k in range(len(pts)):
        SH.line_lamp(em, pts[k], pts[(k + 1) % len(pts)], UP + 0.012, 0.03, 0.006, "command", L.LAMP)
    for rx, ry in ((c.dais_hx - 0.2, c.dais_hy - 0.2), (c.dais_hx - 0.36, c.dais_hy - 0.36)):
        pts = SH.ellipse_poly(0, 0, rx, ry, 56)
        for k in range(len(pts)):
            SH.line_lamp(em, pts[k], pts[(k + 1) % len(pts)], DS, 0.012, 0.003, "command_dim", L.LAMP_DIM)
    compass_star_inlay(b, 0.0, 0.0, DS, 1.02, 0.0, text=False, big=False)

    # ---- stairs into the well (three drops of 0.2 m), brass nosings with guide lights, side skirts
    sw = c.STAIR_W
    for yc in c.STAIR_Y:
        for k, (x0, x1, ztop) in enumerate(((c.WELL_X, c.WELL_X + 0.35, WL + 0.4), (c.WELL_X + 0.35, c.WELL_X + 0.7, WL + 0.2))):
            fb.box((x0, yc - sw / 2, WL), (x1, yc + sw / 2, ztop), L.STRUCT)
            fb.box((x0 + 0.01, yc - sw / 2 + 0.03, ztop - 0.012), (x1 - 0.005, yc + sw / 2 - 0.03, ztop), L.DECK)
            fb.box((x0 - 0.005, yc - sw / 2, ztop - 0.04), (x0 + 0.05, yc + sw / 2, ztop + 0.004), L.BRASS)              # nosing
            em.lamp_box((x0 - 0.008, yc - sw / 2 + 0.06, ztop - 0.03), (x0 - 0.004, yc + sw / 2 - 0.06, ztop - 0.012), "guide", L.LAMP_DIM)
        for s in (-1, 1):
            fb.box((c.WELL_X - 0.02, yc + s * (sw / 2) - 0.02, WL), (c.WELL_X + 0.75, yc + s * (sw / 2) + 0.02, WL + 0.5), L.TRIM)
    # the well edge: nosing, brass line, lamp dashes (the safety-stripe decal is laid over it by place_signage)
    y0, y1 = -c.WELL_HW + sw, c.WELL_HW - sw
    fb.box((c.WELL_X - 0.05, y0, UP - 0.045), (c.WELL_X + 0.03, y1, UP + 0.004), L.TRIM)
    SH.line_lamp(em, (c.WELL_X + 0.031, y0 + 0.05), (c.WELL_X + 0.031, y1 - 0.05), UP - 0.034, 0.014, 0.004, "command", L.LAMP)
    for s in (1, -1):                                              # the wing edges
        xa, xb = c.WELL_X + 0.7 + 0.05, c.xe - 0.05
        ya, yb = sorted((s * c.WELL_HW - 0.05, s * c.WELL_HW + 0.03))
        fb.box((xa, ya, UP - 0.045), (xb, yb, UP + 0.004), L.TRIM)

    # ---- inlaid light: two rings round the dais (broken into dashes with brass beside them), the approach tracks to the emblem, the stair guides
    on_upper = lambda p: p[0] < c.WELL_X - 0.2 and abs(p[1]) < c.side_wall_y(p[0], 1) - 0.5
    for grow, cell in ((0.38, "command_dim"), (0.9, "cool_dim")):
        pts = SH.ellipse_poly(0, 0, c.dais_hx + grow, c.dais_hy + grow, 120)
        for p0, p1 in zip(pts, pts[1:] + pts[:1]):
            if on_upper(p0) and on_upper(p1):
                SH.line_lamp(em, p0, p1, UP, 0.02, 0.004, cell, L.LAMP_DIM, frame_w=0.05)
    pts = SH.ellipse_poly(0, 0, c.dais_hx + 0.52, c.dais_hy + 0.52, 120)
    for p0, p1 in zip(pts, pts[1:] + pts[:1]):
        if on_upper(p0) and on_upper(p1):
            brass_line(fb, p0, p1, UP, 0.012, 0.004)
    # the approach: two tracks of dashes from the emblem's forward point past the lectern to the dais, chevrons between them
    for sd in (-1, 1):
        for k in range(6):
            x0 = EMB_X + EMB_R + 0.25 + k * 0.32
            SH.line_lamp(em, (x0, sd * 1.15), (x0 + 0.2, sd * 1.15), UP, 0.024, 0.004, "command_dim", L.LAMP_DIM, frame_w=0.04)
    for k in range(3):
        x = EMB_X + EMB_R + 0.35 + k * 0.5
        for sd in (-1, 1):
            SH.line_lamp(em, (x - 0.14, sd * 0.2 + sd * 0.0), (x, 0.0), UP, 0.03, 0.004, "command", L.LAMP_DIM)
    for yc in c.STAIR_Y:
        pts = [(c.WELL_X + 0.8, yc), (c.WELL_X + 1.6, yc * 0.85), (tx - 1.4 * math.cos(math.radians(40)), math.copysign(1.0, yc) * 1.2)]
        for a_, b_ in zip(pts[:-1], pts[1:]):
            SH.line_lamp(em, a_, b_, WL, 0.02, 0.004, "command_dim", L.LAMP_DIM, frame_w=0.05)

    # ---- the walls' foot: a light run along the plinth line 0.45 m out (side walls and back wall, interrupted at the doors and the bays)
    # (the plinth lamps are on the walls themselves; this is the floor's own wash)

    # ---- legends on the deck: MIND THE STEP at the top of each stair, COMMAND DAIS on the dais front
    for yc in c.STAIR_Y:
        fb.label((c.WELL_X - 0.42, yc, UP + 0.0025), 0.9, 0.1125, (0, 0, 1), "deck_step", up=(1, 0, 0))
    fb.label((c.dais_hx - 0.36, 0.0, DS + 0.0025), 0.9, 0.1125, (0, 0, 1), "deck_dais", up=(-1, 0, 0))
    return b.build(name)


def plates_bond(fb: FB, poly, z: float, add_plate, skip=None, pw: float = 1.8, ph: float = 0.9, gap: float = 0.016) -> None:
    """Running-bond plates pw x ph clipped to the convex polygon `poly` (the well and the wings)."""
    xs = [p[0] for p in poly]
    ys = [p[1] for p in poly]
    j0 = int(math.floor(min(ys) / ph)) - 1
    j1 = int(math.ceil(max(ys) / ph)) + 1
    for j in range(j0, j1 + 1):
        off = (pw / 2) if j % 2 else 0.0
        i0 = int(math.floor((min(xs) - off) / pw)) - 1
        i1 = int(math.ceil((max(xs) - off) / pw)) + 1
        for i in range(i0, i1 + 1):
            x0, x1 = i * pw + off + gap / 2, (i + 1) * pw + off - gap / 2
            y0, y1 = j * ph + gap / 2, (j + 1) * ph - gap / 2
            clipped = SH.clip_convex([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], poly, 0.03)
            if len(clipped) < 3 or SH.poly_area(clipped) < 0.02:
                continue
            if skip and skip(clipped):
                continue
            add_plate(clipped, z)
