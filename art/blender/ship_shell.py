"""ASN Aquila interior kit (ARTE-INTERNI): the room shell, second generation — a floor with a border and an inlay line, walls in bays (pilasters with a light slot, framed panels,
a different treatment from bay to bay: panels, wall cloth, wood slats, perforated sheet, tile), and ceilings that are architecture, not a flat slab with square lamps (luminous bands
between beams, a cove round a raised ceiling, a grid of acoustic tiles, an exposed structure). Called by ship_rooms.build_shell when the Style has `v2` (the default).

Frames and sizes as ship_rooms.py: room frame x 0..L along the corridor, y 0..D into the room, z up; the wall frames (ship_rooms.wall_matrix): s along the wall, t outward from its
finished face (so the room is at negative t), z up.
"""
from __future__ import annotations

import math
import random

from bridge3_lib import T
from ship_lib import (COMPOSITE, DECK, IVORY, LAMP, LAMP_DIM, LAMP_HOT, PERF, STEEL, STRUCT, TRIM, SParts)

WS = 0.20
WF = 0.05
FIN = 0.0
POST_W, POST_D = 0.07, 0.035               # a pilaster: width along the wall, how far it stands off the finish


def _wall_len(name: str, L: float, D: float) -> float:
    return L if name in ("far", "near") else D


# ---------------------------------------------------------------------------------------------------------------------------------- floor
def floor_v2(b: SParts, spec: dict, st, rng: random.Random, floor_t: float, plate_uv) -> None:
    L, D = spec["L"], spec["D"]
    fb, fine, em = b.body, b.fine, b.emit
    fb.box((0.0, 0.0, -floor_t), (L, D, -0.012), STRUCT)
    if st.floor_mode == "plates":
        rows = int(D // 1.0)
        for j in range(rows):
            y0, y1 = j * D / rows + 0.008, (j + 1) * D / rows - 0.008
            cuts = [0.0] + [k * 2.0 + (1.0 if j % 2 else 0.0) for k in range(int(L // 2.0) + 1)] + [L]
            cuts = sorted({round(c, 3) for c in cuts if 0.0 <= c <= L})
            for a, c in zip(cuts, cuts[1:]):
                if c - a < 0.3:
                    continue
                faces = fb.box((a + 0.008, y0, -0.012), (c - 0.008, y1, 0.0), st.floor)
                plate_uv(fb, faces, rng)
        return
    if st.border > 0.0 and st.floor2:
        bd = st.border
        x0, x1, y0, y1 = bd, L - bd, bd, D - bd
        fb.box((x0, y0, -0.012), (x1, y1, 0.0), st.floor)
        # the border: four strips of the second finish; the near side (the corridor's wall) stays open at the doors
        doors = [d for d in spec["doors"] if d["wall"] == "near"]
        fb.box((0.0, D - bd, -0.012), (L, D, 0.0), st.floor2)
        fb.box((0.0, bd, -0.012), (bd, D - bd, 0.0), st.floor2)
        fb.box((L - bd, bd, -0.012), (L, D - bd, 0.0), st.floor2)
        cuts = [0.0] + [v for d in sorted(doors, key=lambda d: d["x"]) for v in (d["x"] - d["w"] / 2 - 0.2, d["x"] + d["w"] / 2 + 0.2)] + [L]
        for a, c in zip(cuts[0::2], cuts[1::2]):
            if c - a > 0.1:
                fb.box((a, 0.0, -0.012), (c, bd, 0.0), st.floor2)
        for d in doors:                                                     # the doorway is floored with the field's finish
            fb.box((d["x"] - d["w"] / 2 - 0.2, 0.0, -0.012), (d["x"] + d["w"] / 2 + 0.2, bd, 0.0), st.floor)
        if st.inlay:                                                        # a thin lit line between the field and the border
            e = 0.012
            em.lamp_box((x0 - e, y0 - e, 0.0), (x1 + e, y0, 0.004), st.inlay, LAMP_DIM) if False else None
            em.lamp_box((x0, y1, 0.0), (x1, y1 + e, 0.004), st.inlay, LAMP_DIM)
            em.lamp_box((x0 - e, y0, 0.0), (x0, y1 + e, 0.004), st.inlay, LAMP_DIM)
            em.lamp_box((x1, y0, 0.0), (x1 + e, y1 + e, 0.004), st.inlay, LAMP_DIM)
    else:
        fb.box((0.0, 0.0, -0.012), (L, D, 0.0), st.floor)
    step = 4.0
    for k in range(1, int(L // step) + 1):
        if k * step < L and st.seams:
            fine.box((k * step - 0.01, 0.0, 0.0), (k * step + 0.01, D, 0.003), st.trim)


# ---------------------------------------------------------------------------------------------------------------------------------- walls
def _bay_edges(a: float, c: float, target: float) -> list[float]:
    n = max(1, int(round((c - a) / target)))
    return [a + (c - a) * k / n for k in range(n + 1)]


def _upper_panel(b: SParts, mode: str, x0: float, x1: float, z0: float, z1: float, st, rng: random.Random) -> None:
    """The upper part of one bay, between two pilasters (wall frame: finish layer at t -WF..0): framed panel, wall cloth, wood slats, perforated sheet."""
    fb, fine, soft, em = b.body, b.fine, b.soft, b.emit
    g = 0.012
    xa, xb = x0 + POST_W / 2 + g, x1 - POST_W / 2 - g
    if xb - xa < 0.2:
        return
    if mode == "cloth":
        fine.box((xa, -WF - 0.012, z0 + 0.12), (xb, -WF + 0.002, z1 - 0.12), st.wall_acc)
        for (ya, yb) in ((z0 + 0.08, z0 + 0.12), (z1 - 0.12, z1 - 0.08)):
            fine.box((xa, -WF - 0.016, ya), (xb, -WF + 0.002, yb), st.trim)
        fine.box((xa, -WF - 0.016, z0 + 0.12), (xa + 0.035, -WF + 0.002, z1 - 0.12), st.trim)
        fine.box((xb - 0.035, -WF - 0.016, z0 + 0.12), (xb, -WF + 0.002, z1 - 0.12), st.trim)
        fb.box((xa, -WF, z0), (xb, -0.0, z1), st.wall_hi)
    elif mode == "slats":
        fb.box((xa, -WF, z0), (xb, 0.0, z1), STRUCT)
        w = 0.034
        n = max(2, int((xb - xa) / 0.065))
        pitch = (xb - xa) / n
        for k in range(n):
            xs = xa + k * pitch + (pitch - w) / 2
            b.soft.box((xs, -WF - 0.035, z0 + 0.02), (xs + w, -WF + 0.0, z1 - 0.02), st.wall_slat)
        em.lamp_box((xa, -WF - 0.002, z0 + 0.005), (xb, -WF + 0.0, z0 + 0.02), st.accent, LAMP_DIM)
    elif mode == "perf":
        fb.box((xa, -WF, z0), (xb, 0.0, z1), STRUCT)
        fine.box((xa + 0.03, -WF - 0.016, z0 + 0.1), (xb - 0.03, -WF + 0.002, z1 - 0.1), PERF)
        for (ya, yb) in ((z0 + 0.06, z0 + 0.1), (z1 - 0.1, z1 - 0.06)):
            fine.box((xa + 0.02, -WF - 0.02, ya), (xb - 0.02, -WF + 0.002, yb), st.trim)
    elif mode == "mirror":
        fb.box((xa, -WF, z0), (xb, 0.0, z1), st.wall_hi)
    else:                                                                    # panel: a pale panel in a slim frame
        fb.box((xa, -WF, z0), (xb, 0.0, z1), st.wall_hi)
        fine.box((xa + 0.03, -WF - 0.007, z0 + 0.06), (xb - 0.03, -WF + 0.001, z1 - 0.06), st.wall_hi)
        for (ya, yb) in ((z0 + 0.06, z0 + 0.075), (z1 - 0.075, z1 - 0.06)):
            fine.box((xa + 0.03, -WF - 0.011, ya), (xb - 0.03, -WF + 0.001, yb), st.trim)


def wall_v2(b: SParts, name: str, L: float, D: float, H: float, st, doors: list, structure: bool, wall_matrix, door_spans, wall_segments, door_trim,
            rng: random.Random) -> None:
    """One wall in bays: structure, then for every solid run between openings a row of bays (lower panel, upper treatment) between pilasters, with a light slot on each pilaster,
    a rail, a skirt and a cornice."""
    fb, fine, em = b.body, b.fine, b.emit
    sl = _wall_len(name, L, D)
    spans = door_spans(name, doors, L, D)
    M = wall_matrix(name, L, D)
    pattern = st.wall_pattern or ("panel",)
    bay_i = 0
    with b.at(M):
        if structure:
            for (a, c, hb) in wall_segments(sl, spans):
                fb.box((a, 0.0, hb if hb > 0 else 0.0), (c, WS, H), STRUCT)
        for (a, c, hb) in wall_segments(sl, spans):
            if hb > 0:                                                       # the header over a door
                fb.box((a, -WF, hb), (c, 0.0, H), st.wall_hi)
                continue
            edges = _bay_edges(a, c, st.bay)
            for k in range(len(edges) - 1):
                x0, x1 = edges[k], edges[k + 1]
                xa, xb = x0 + POST_W / 2 + 0.01, x1 - POST_W / 2 - 0.01
                if xb - xa < 0.15:
                    continue
                fb.box((xa, -WF, 0.0), (xb, 0.0, st.wain_h), st.wall_lo)                              # the wainscot panel
                fine.box((xa + 0.025, -WF - 0.006, 0.16), (xb - 0.025, -WF + 0.001, st.wain_h - 0.07), st.wall_lo)
                _upper_panel(b, pattern[bay_i % len(pattern)], x0, x1, st.wain_h, H - 0.05, st, rng)
                bay_i += 1
            for k, xe in enumerate(edges):                                  # pilasters: a post of the rib material with a slot of light
                end = k in (0, len(edges) - 1)
                if end and (xe <= 0.01 or xe >= sl - 0.01):
                    continue
                fb.box((xe - POST_W / 2, -WF - POST_D, 0.0), (xe + POST_W / 2, 0.0, H - 0.06), st.rib_mat)
                fine.box((xe - POST_W / 2 + 0.012, -WF - POST_D - 0.006, 0.12), (xe + POST_W / 2 - 0.012, -WF - POST_D, H - 0.2), STRUCT)
                if st.wall_wash:
                    em.lamp_box((xe - 0.007, -WF - POST_D - 0.012, 0.5), (xe + 0.007, -WF - POST_D - 0.006, H - 0.4), st.accent, LAMP_DIM)
            fb.box((a, -WF - 0.02, st.wain_h - 0.03), (c, -WF + 0.0, st.wain_h + 0.03), st.trim)         # the rail between wainscot and upper wall
            fb.box((a, -WF - 0.012, 0.0), (c, -WF, 0.10), st.skirt)                                       # the skirting
            if getattr(st, "baseboard_light", False):
                em.lamp_box((a + 0.05, -WF - 0.016, 0.115), (c - 0.05, -WF - 0.011, 0.13), st.accent, LAMP_DIM)
        sills = {}
        for d in doors:                                                         # an opening with a sill (a serving pass, a window): the wall under it
            z0 = d.get("z0", 0.0)
            if d["wall"] != name or z0 <= 0.0:
                continue
            s_mid = (L - d["x"]) if name == "near" else d["x"]
            a, c = s_mid - d["w"] / 2, s_mid + d["w"] / 2
            sills[(round(a, 3), round(c, 3))] = z0
            if structure:
                fb.box((a, 0.0, 0.0), (c, WS, z0), STRUCT)
            fb.box((a, -WF, 0.0), (c, 0.0, z0), st.wall_lo)
            fb.box((a - 0.02, -WF - 0.03, z0 - 0.04), (c + 0.02, -WF + 0.0, z0), st.trim)
        for (a, c, hb) in spans:
            z0 = sills.get((round(a, 3), round(c, 3)))
            if z0 is None:
                door_trim(fine, a, c, hb, -WF, WS if structure else 0.0)
            else:                                                               # a window's reveal: jambs between the sill and the head, a header
                t_out = WS if structure else 0.0
                fine.box((a - 0.05, -WF - 0.03, z0), (a, t_out, hb + 0.05), st.trim)
                fine.box((c, -WF - 0.03, z0), (c + 0.05, t_out, hb + 0.05), st.trim)
                fine.box((a - 0.05, -WF - 0.03, hb), (c + 0.05, t_out, hb + 0.05), st.trim)
        fb.box((0.0, -WF - 0.05, H - 0.06), (sl, 0.0, H), st.trim)                                       # the cornice


def walls_v2(b: SParts, spec: dict, st, doors: list, far_door: bool, skip: tuple, bare: tuple, wall_matrix, door_spans, wall_segments, door_trim, rng) -> None:
    L, D, H = spec["L"], spec["D"], spec["h"]
    for name in ("left", "right", "far", "near"):
        if name in skip:
            continue
        d_list = doors
        if name == "far" and not far_door:
            d_list = [d for d in doors if d["wall"] != "far"]
        wall_v2(b, name, L, D, H, st, d_list, name not in bare, wall_matrix, door_spans, wall_segments, door_trim, rng)


# ---------------------------------------------------------------------------------------------------------------------------------- ceiling
def downlight(b: SParts, x: float, y: float, z: float, r: float, cell: str, hot: bool = True) -> None:
    """A recessed round downlight: a brushed trim ring and a bright disc, flush with the ceiling at height z."""
    b.soft.cyl((x, y, z - 0.035), (x, y, z), r + 0.018, TRIM, seg=14)
    b.emit.lamp_cyl((x, y, z - 0.04), (x, y, z - 0.034), r, cell, LAMP_HOT if hot else LAMP, seg=14)


def band(b: SParts, x0: float, x1: float, yc: float, w: float, z: float, cell: str, mat: str = LAMP_HOT, frame_mat: str = TRIM) -> None:
    """A luminous band set into the ceiling: a frame (brushed) and a diffuser flush with it, along x."""
    t = 0.03
    b.body.box((x0, yc - w / 2 - t, z - 0.07), (x1, yc - w / 2, z), frame_mat)
    b.body.box((x0, yc + w / 2, z - 0.07), (x1, yc + w / 2 + t, z), frame_mat)
    b.body.box((x0 - t, yc - w / 2 - t, z - 0.07), (x0, yc + w / 2 + t, z), frame_mat)
    b.body.box((x1, yc - w / 2 - t, z - 0.07), (x1 + t, yc + w / 2 + t, z), frame_mat)
    b.soft.box((x0, yc - w / 2, z - 0.03), (x1, yc + w / 2, z - 0.02), STRUCT)
    b.emit.lamp_box((x0 + 0.02, yc - w / 2 + 0.02, z - 0.045), (x1 - 0.02, yc + w / 2 - 0.02, z - 0.04), cell, mat)


def beams(b: SParts, spec: dict, st, xs: list[float], depth: float = 0.16) -> None:
    """Structural beams across the room (along y) at the given x: a brushed-edged box in the rib material with a thin light slot on each flank (the ship's frames)."""
    L, D, H = spec["L"], spec["D"], spec["h"]
    for x in xs:
        b.body.box((x - 0.13, WS + WF, H - 0.05 - depth), (x + 0.13, D - WS - WF, H - 0.05), st.rib_mat)
        b.fine.box((x - 0.14, WS + WF, H - 0.05 - depth - 0.012), (x + 0.14, D - WS - WF, H - 0.05 - depth), STRUCT)
        if st.beam_light:
            b.emit.lamp_box((x - 0.133, WS + WF + 0.3, H - 0.05 - depth * 0.55), (x - 0.13, D - WS - WF - 0.3, H - 0.05 - depth * 0.55 + 0.02), st.accent, LAMP_DIM)
            b.emit.lamp_box((x + 0.13, WS + WF + 0.3, H - 0.05 - depth * 0.55), (x + 0.133, D - WS - WF - 0.3, H - 0.05 - depth * 0.55 + 0.02), st.accent, LAMP_DIM)


def tile_joints(b: SParts, spec: dict, st, pitch: float = 0.6, z_off: float = 0.0) -> None:
    """The reveals of a ceiling of tiles: thin dark lines every `pitch` metres both ways (a grid ceiling)."""
    L, D, H = spec["L"], spec["D"], spec["h"]
    x = WS + WF + pitch
    while x < L - WS - WF - 0.1:
        b.soft.box((x - 0.004, WS + WF, H - 0.052), (x + 0.004, D - WS - WF, H - 0.05), STRUCT)
        x += pitch
    y = FIN + WF + pitch
    while y < D - WS - WF - 0.1:
        b.soft.box((WS + WF, y - 0.004, H - 0.052), (L - WS - WF, y + 0.004, H - 0.05), STRUCT)
        y += pitch


def ceiling_v2(b: SParts, spec: dict, st, rng: random.Random, ceil_t: float) -> None:
    L, D, H = spec["L"], spec["D"], spec["h"]
    fb, fine, em = b.body, b.fine, b.emit
    fb.box((0.0, 0.0, H), (L, D, H + ceil_t), STRUCT)                                    # the deck above
    x0, x1, y0, y1 = WS + WF, L - WS - WF, FIN + WF, D - WS - WF
    mode = st.ceiling
    cell = st.light_cell
    pitch = getattr(st, "beam_pitch", 4.0)
    beam_xs = [k * pitch for k in range(1, int(L // pitch) + 1) if k * pitch < L - 0.5]
    if mode == "cove":
        # a raised centre and a lowered rim: the soffit (0.55 m wide, 14 cm lower) round the room, a lit cove in the step facing up, downlights in the rim
        rim, drop = 0.55, 0.14
        fb.box((x0, y0, H - 0.05 - drop), (x1, y0 + rim, H - 0.05), st.ceil)
        fb.box((x0, y1 - rim, H - 0.05 - drop), (x1, y1, H - 0.05), st.ceil)
        fb.box((x0, y0 + rim, H - 0.05 - drop), (x0 + rim, y1 - rim, H - 0.05), st.ceil)
        fb.box((x1 - rim, y0 + rim, H - 0.05 - drop), (x1, y1 - rim, H - 0.05), st.ceil)
        fb.box((x0 + rim, y0 + rim, H - 0.05 - 0.002), (x1 - rim, y1 - rim, H - 0.05), st.ceil)
        z = H - 0.05 - drop
        e = 0.045
        em.lamp_box((x0 + rim, y0 + rim - e, z), (x1 - rim, y0 + rim, z + 0.01), cell, LAMP_HOT) if False else None
        # the step's inner faces carry the strip: a thin lamp box on the ledge, facing the centre
        em.lamp_box((x0 + rim, y0 + rim - 0.03, z - 0.012), (x1 - rim, y0 + rim, z), cell, LAMP_HOT)
        em.lamp_box((x0 + rim, y1 - rim, z - 0.012), (x1 - rim, y1 - rim + 0.03, z), cell, LAMP_HOT)
        em.lamp_box((x0 + rim - 0.03, y0 + rim, z - 0.012), (x0 + rim, y1 - rim, z), cell, LAMP_HOT)
        em.lamp_box((x1 - rim, y0 + rim, z - 0.012), (x1 - rim + 0.03, y1 - rim, z), cell, LAMP_HOT)
        # a luminous glow band in the raised ceiling above the cove (the diffuse light that the cove throws up): a recessed panel the length of the centre
        fine.box((x0 + rim + 0.05, y0 + rim + 0.05, H - 0.05 - 0.004), (x1 - rim - 0.05, y1 - rim - 0.05, H - 0.05), st.ceil)
        # downlights along the rim and across the centre
        n = max(3, int((x1 - x0) / 2.2))
        for k in range(n):
            xx = x0 + (k + 0.5) * (x1 - x0) / n
            downlight(b, xx, y0 + rim / 2 + 0.02, H - 0.05 - drop, 0.065, cell, False)
            downlight(b, xx, y1 - rim / 2 - 0.02, H - 0.05 - drop, 0.065, cell, False)
        ny = max(1, int((y1 - y0 - 2 * rim) / 2.4))
        for j in range(ny):
            yy = y0 + rim + (j + 0.5) * (y1 - y0 - 2 * rim) / ny
            for k in range(max(2, n // 2)):
                xx = x0 + rim + (k + 0.5) * (x1 - x0 - 2 * rim) / max(2, n // 2)
                downlight(b, xx, yy, H - 0.05, 0.075, cell, True)
        tile_joints(b, spec, st, 1.2)
    elif mode == "grid":
        fb.box((x0, y0, H - 0.05), (x1, y1, H - 0.05 + 0.001), st.ceil)
        tile_joints(b, spec, st, 0.6)
        ny = max(1, int(round((y1 - y0) / 4.0)))
        nx = max(1, int(round((x1 - x0) / 4.0)))
        for j in range(ny):
            for k in range(nx):
                xc = x0 + (k + 0.5) * (x1 - x0) / nx
                yc = y0 + (j + 0.5) * (y1 - y0) / ny
                panel = (1.2, 0.6)
                for dx in (-0.65, 0.65):
                    for dy in ((-0.0,)):
                        band(b, xc + dx - panel[0] / 2, xc + dx + panel[0] / 2, yc, panel[1], H - 0.05, cell, LAMP_HOT)
        beams(b, spec, st, beam_xs, 0.12)
    elif mode == "exposed":
        # the structure shows: the deck's underside, beams every 4 m and a pair of long luminaires hung between them
        beams(b, spec, st, beam_xs, 0.28)
        ny = max(1, int(round((y1 - y0) / 5.0)))
        for j in range(ny):
            yc = y0 + (j + 0.5) * (y1 - y0) / ny
            for k in range(len(beam_xs) + 1):
                xa = (beam_xs[k - 1] + 0.4) if k > 0 else x0 + 0.4
                xb = (beam_xs[k] - 0.4) if k < len(beam_xs) else x1 - 0.4
                if xb - xa > 1.0:
                    band(b, xa, xb, yc, 0.3, H - 0.05 - 0.2, cell, LAMP_HOT, STEEL)
                    fine.box((xa + 0.3, yc - 0.01, H - 0.05 - 0.2), (xa + 0.32, yc + 0.01, H - 0.05), TRIM)
                    fine.box((xb - 0.32, yc - 0.01, H - 0.05 - 0.2), (xb - 0.3, yc + 0.01, H - 0.05), TRIM)
    elif mode == "flat":
        fb.box((x0, y0, H - 0.05), (x1, y1, H), st.ceil)
    else:                                                                                  # bands (the default): luminous bands between the beams, downlights between the bands
        fb.box((x0, y0, H - 0.05), (x1, y1, H - 0.05 + 0.001), st.ceil)
        tile_joints(b, spec, st, 1.2)
        beams(b, spec, st, beam_xs, 0.16)
        nbands = st.bands or max(1, int(round((y1 - y0) / 4.5)))
        ys = list(st.band_ys) if getattr(st, "band_ys", None) else [y0 + (j + 0.5) * (y1 - y0) / nbands for j in range(nbands)]
        for yc in ys:
            for k in range(len(beam_xs) + 1):
                xa = (beam_xs[k - 1] + 0.35) if k > 0 else x0 + 0.5
                xb = (beam_xs[k] - 0.35) if k < len(beam_xs) else x1 - 0.5
                if xb - xa > 1.2:
                    band(b, xa, xb, yc, getattr(st, "band_w", 0.42), H - 0.05, cell, LAMP_HOT)
        if st.downlights:
            for j in range(nbands + 1):
                yy = y0 + j * (y1 - y0) / nbands
                if j == 0:
                    yy = y0 + 0.9
                elif j == nbands:
                    yy = y1 - 0.9
                n = max(2, int((x1 - x0) / 2.4))
                for k in range(n):
                    downlight(b, x0 + (k + 0.5) * (x1 - x0) / n, yy, H - 0.05, 0.065, cell, False)
