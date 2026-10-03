"""ASN Aquila interior kit: the room shells and the shared room machinery (bridge v3 language). The rooms themselves live in
ship_rooms_*.py; the sizes, doors, crew spots and zone lights they follow are in ship_spec.py (the plan uses the same numbers).

Room frame: origin on the floor at the corridor-side corner of the room, x along the corridor (0..L), y INTO the room (0..D), z up. The
near wall (y = 0) is the corridor's wall (its structure belongs to the corridor module: the room adds only a finish layer 5 cm thick with
the door opening and its trim); the far wall (y = D) and the side walls (x = 0, x = L) have their own 0.2 m structure and a finish layer.
"""
from __future__ import annotations

import math
import random

from mathutils import Matrix

import ship_lib as SL
import ship_furniture as F
from bridge3_lib import Rz, T, frame
from ship_catalog import CLEAR_H, DOOR_H, DOOR_W, GATE_H, GATE_W, HW, MOD, SLOT_HW
from ship_lib import (COMPOSITE, DECK, DGLASS, GLASS, IVORY, LAMP, LAMP_DIM, LAMP_HOT, RUBBER, STEEL, STRUCT, TRIM, SParts, SFB)

WS = 0.20               # structure thickness of a room's own walls
WF = 0.05               # finish layer
FIN = 0.0


class Style:
    """The look of a room: materials of the floor, the wainscot, the upper wall, the trim and the ceiling, the accent lamp colour.
    ARTE-INTERNI (`v2`, the default; ship_shell.py): `floor2` / `border` / `inlay` = a border of a second finish round the floor with a lit line between; `wall_acc` (cloth) + `wall_slat` + `wall_pattern`
    = the materials and the order of the treatments of the wall bays (panel, cloth, slats, perf); `bay` = the target width of a bay (m); `wall_wash` = a slot of light on every pilaster;
    `ceiling` = bands | cove | grid | exposed | flat; `light_cell` = the colour of the ceiling's luminous parts; `downlights`, `bands` (how many) or `band_ys` (where), `band_w`, `beam_pitch`, `beam_light`."""

    def __init__(self, floor: str = DECK, floor_mode: str = "plates", wall_lo: str = COMPOSITE, wall_hi: str = COMPOSITE, trim: str = TRIM,
                 ceil: str = COMPOSITE, accent: str = "cool_dim", strip: str = "white_cool", wain_h: float = 1.05, ribs: bool = True,
                 rib_mat: str = TRIM, skirt: str = STRUCT, light_mode: str = "strips", rail: bool = True, cove: str | None = None,
                 seams: bool = True, cove_on: bool = True, v2: bool = True, floor2: str | None = None, border: float = 0.0, inlay: str | None = None,
                 wall_acc: str = COMPOSITE, wall_slat: str = "MI_SHIP_Oak", wall_pattern: tuple | None = None, bay: float = 2.0, wall_wash: bool = True, ceiling: str = "bands",
                 light_cell: str | None = None, downlights: bool = True, bands: int = 0, beam_light: bool = True, band_ys: tuple | None = None, band_w: float = 0.42,
                 beam_pitch: float = 4.0) -> None:
        self.__dict__.update(locals())
        del self.__dict__["self"]
        if self.light_cell is None:
            self.light_cell = self.strip


def wall_matrix(name: str, L: float, D: float) -> Matrix:
    """Wall-local frame (s along the wall, t outward from its finished face, z up) in room coordinates."""
    if name == "far":                 # y = D - WS is the finished face, s along +x, t towards +y
        return Matrix(((1, 0, 0, 0), (0, 1, 0, D - WS), (0, 0, 1, 0), (0, 0, 0, 1)))
    if name == "left":                # x = WS is the finished face, s along +y, t towards -x
        return Matrix(((0, -1, 0, WS), (1, 0, 0, 0), (0, 0, 1, 0), (0, 0, 0, 1)))
    if name == "right":               # x = L - WS is the finished face, s along -y, t towards +x
        return Matrix(((0, 1, 0, L - WS), (-1, 0, 0, D), (0, 0, 1, 0), (0, 0, 0, 1)))
    if name == "near":                # y = FIN is the finished face, s along -x, t towards -y
        return Matrix(((-1, 0, 0, L), (0, -1, 0, FIN), (0, 0, 1, 0), (0, 0, 0, 1)))
    raise ValueError(name)


def wall_len(name: str, L: float, D: float) -> float:
    return L if name in ("far", "near") else D


def door_spans(name: str, doors: list, L: float, D: float) -> list[tuple[float, float, float]]:
    """(s0, s1, height) of every door opening on a wall, in the wall's own s coordinate."""
    out = []
    for d in doors:
        if d["wall"] != name:
            continue
        x = d["x"]
        w, h = d["w"], d["h"]
        if name == "near":
            s = L - x                    # the near wall's s runs along -x
        elif name == "far":
            s = x
        else:
            s = x
        out.append((s - w / 2, s + w / 2, h))
    return sorted(out)


def wall_segments(s_len: float, spans: list) -> list[tuple[float, float, float, float]]:
    """Solid pieces (s0, s1, z0, z1-open) of a wall of length s_len with openings: [(s0, s1, z_bottom, 'top')]: fully solid runs have z_bottom 0;
    the piece above an opening starts at the opening's height."""
    segs = []
    cur = 0.0
    for (a, b, h) in spans:
        if a > cur:
            segs.append((cur, a, 0.0))
        segs.append((a, b, h))
        cur = b
    if cur < s_len:
        segs.append((cur, s_len, 0.0))
    return segs


def door_trim(fb: SFB, s0: float, s1: float, h: float, t_in: float, t_out: float) -> None:
    """Jambs and header of a door opening through a wall (wall-local frame): brushed trim proud of the finish by 3 cm."""
    fb.box((s0 - 0.07, t_in - 0.03, 0.0), (s0, t_out, h + 0.07), TRIM)
    fb.box((s1, t_in - 0.03, 0.0), (s1 + 0.07, t_out, h + 0.07), TRIM)
    fb.box((s0 - 0.07, t_in - 0.03, h), (s1 + 0.07, t_out, h + 0.07), TRIM)


def wall_finish(b: SParts, name: str, L: float, D: float, H: float, st: Style, doors: list, windows: list | None = None,
                structure: bool = True) -> None:
    """One wall: structure, wainscot, upper panels, rail, skirting, ribs, cornice, with its door openings and windows (s0, s1, z0, z1)."""
    fb, fine, em = b.body, b.fine, b.emit
    sl = wall_len(name, L, D)
    spans = door_spans(name, doors, L, D)
    wins = windows or []
    M = wall_matrix(name, L, D)
    with b.at(M):
        # structure (t 0 .. WS): solid except the openings
        if structure:
            for (a, c, hb) in wall_segments(sl, spans):
                if hb > 0:
                    fb.box((a, 0.0, hb), (c, WS, H), STRUCT)
                else:
                    fb.box((a, 0.0, 0.0), (c, WS, H), STRUCT)
            for (a, c, z0, z1) in wins:
                pass
        # finish: wainscot, upper wall, rail, skirt
        for (a, c, hb) in wall_segments(sl, spans):
            zlo = hb
            if hb == 0.0:
                fb.box((a, -WF, 0.0), (c, 0.0, st.wain_h), st.wall_lo)
                fb.box((a, -WF, st.wain_h), (c, 0.0, H), st.wall_hi)
                fb.box((a, -WF - 0.014, st.wain_h - 0.03), (c, -WF, st.wain_h + 0.03), st.trim)
                fb.box((a, -WF - 0.012, 0.0), (c, -WF, 0.10), st.skirt)
            else:
                fb.box((a, -WF, hb), (c, 0.0, H), st.wall_hi)
        for (a, c, hb) in spans:
            door_trim(fine, a, c, hb, -WF, WS if structure else 0.0)
        # ribs at every 4 m of the room (they carry the ship's frames; not through openings)
        if st.ribs and name in ("far", "near"):
            xs = [k * MOD for k in range(1, int(sl // MOD) + 1) if k * MOD < sl - 0.1] if name == "far" else []
            for k, s in enumerate(xs):
                sw = sl - s if name == "far" else s
                if any(a - 0.3 < s < c + 0.3 for (a, c, _h) in spans):
                    continue
                fb.box((s - 0.10, -WF - 0.10, 0.0), (s + 0.10, -WF, H), st.rib_mat)
                fine.box((s - 0.07, -WF - 0.112, 0.06), (s + 0.07, -WF - 0.10, H - 0.06), STRUCT)
                em.lamp_box((s - 0.006, -WF - 0.118, 0.5), (s + 0.006, -WF - 0.112, H - 0.5), st.accent, LAMP_DIM)
        # cornice
        fb.box((0.0, -WF - 0.06, H - 0.06), (sl, 0.0, H), st.trim)


def build_shell(b: SParts, spec: dict, st: Style, doors: list | None = None, far_door: bool = True, windows_far: list | None = None,
                seed: int = 1, skip: tuple = (), bare: tuple = ("near",), ceil_t: float = 0.30, floor_t: float = 0.30) -> None:
    """Floor, ceiling and the four walls of a room. `skip`: walls not built here (the caller builds them: window walls); `bare`: walls that
    belong to a corridor (a finish layer only, no structure of their own); `ceil_t`, `floor_t`: the ceiling's and the floor's structure thickness (a room inside a shell that leaves no more than that)."""
    L, D, H = spec["L"], spec["D"], spec["h"]
    import ship_themes as TH
    st = TH.resolve(st, spec)                                         # ARTE-INTERNI: a room that chose no theme gets the one of its prefab (ship_themes.THEME_TABLE)
    doors = doors if doors is not None else spec["doors"]
    b._doors = doors                                                  # (dress_wall keeps clear of them)
    b._style = st                                                     # (ceiling_panels reads it)
    fb, fine, em = b.body, b.fine, b.emit
    rng = random.Random(seed)
    if st.v2:
        import ship_shell as SH
        SH.floor_v2(b, spec, st, rng, floor_t, _plate_uv)
        SH.ceiling_v2(b, spec, st, rng, ceil_t)
        SH.walls_v2(b, spec, st, doors, far_door, skip, bare, wall_matrix, door_spans, wall_segments, door_trim, rng)
        return
    # floor: structure and covering
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
                _plate_uv(fb, faces, rng)
    else:
        fb.box((0.0, 0.0, -0.012), (L, D, 0.0), st.floor)
        step = 4.0
        for k in range(1, int(L // step) + 1):
            if k * step < L and st.seams:
                fine.box((k * step - 0.01, 0.0, 0.0), (k * step + 0.01, D, 0.003), st.trim)
    # ceiling: structure and finish
    fb.box((0.0, 0.0, H), (L, D, H + ceil_t), STRUCT)
    fb.box((WS + WF, FIN + WF, H - 0.05), (L - WS - WF, D - WS - WF, H), st.ceil)
    # walls
    for name in ("left", "right", "far", "near"):
        if name in skip:
            continue
        d_list = doors
        if name == "far" and not far_door:
            d_list = [d for d in doors if d["wall"] != "far"]
        wall_finish(b, name, L, D, H, st, d_list, structure=(name not in bare))
    if not st.cove_on:
        return
    # a cove of light along the perimeter, facing up: the ceiling gets its bounce (and the room its glow) from it
    cell = st.cove or st.accent
    z = H - 0.20
    x0, x1, y0, y1 = WS + WF + 0.10, L - WS - WF - 0.10, FIN + WF + 0.10, D - WS - WF - 0.10
    door_x = [d["x"] for d in doors if d["wall"] == "near"]
    gaps = [(dx - 1.1, dx + 1.1) for dx in door_x]
    cuts = [x0] + [v for g in sorted(gaps) for v in g] + [x1]
    for a, c in zip(cuts[0::2], cuts[1::2]):
        if c - a > 0.5:
            em.lamp_box((a, y0, z), (c, y0 + 0.05, z + 0.012), cell, LAMP)
    em.lamp_box((x0, y1 - 0.05, z), (x1, y1, z + 0.012), cell, LAMP)
    em.lamp_box((x0, y0 + 0.05, z), (x0 + 0.05, y1 - 0.05, z + 0.012), cell, LAMP)
    em.lamp_box((x1 - 0.05, y0 + 0.05, z), (x1, y1 - 0.05, z + 0.012), cell, LAMP)


def _plate_uv(fb, faces, rng):
    ou, ov = rng.random() * 8.0, rng.random() * 8.0
    for f in faces:
        n = f.normal
        ax = max(range(3), key=lambda i: abs(n[i]))
        f[fb.cu] = 1
        for loop in f.loops:
            co = loop.vert.co
            u, v = ((co.y, co.z), (co.x, co.z), (co.x, co.y))[ax]
            loop[fb.uv].uv = (u + ou, v + ov)


def luminaire_strips(b: SParts, L: float, D: float, H: float, ys: list[float], cell: str = "white_cool", x0: float = 1.5, x1: float | None = None,
                     mat: str = LAMP_HOT, w: float = 0.32) -> None:
    """Linear ceiling luminaires along x (trough frame + a lamp strip), like the corridor's."""
    x1 = L - 1.5 if x1 is None else x1
    for y in ys:
        F_ = b.body
        F_.box((x0, y - w / 2 - 0.03, H - 0.075), (x1, y - w / 2, H - 0.02), TRIM)
        F_.box((x0, y + w / 2, H - 0.075), (x1, y + w / 2 + 0.03, H - 0.02), TRIM)
        F_.box((x0, y - w / 2, H - 0.027), (x1, y + w / 2, H - 0.02), STRUCT)
        b.emit.lamp_box((x0 + 0.06, y - w / 2 + 0.03, H - 0.034), (x1 - 0.06, y + w / 2 - 0.03, H - 0.028), cell, mat)


def door_plate_hint(b: SParts, spec: dict) -> None:
    """Nothing to build: the room's name plate is a separate mesh placed over the corridor's door (SM_SHIP_Plate_<plate>)."""
    return None


def place(b: SParts, x: float, y: float, yaw: float, fn, *args, z: float = 0.0, **kw):
    """Build one piece (a furniture function) at (x, y) on the floor, turned by yaw (degrees; 0 = front towards +x, 90 = towards +y)."""
    with b.at(frame(x, y, z, yaw)):
        return fn(b, *args, **kw)


def wall_label(b: SParts, x: float, y: float, z: float, facing, cell: str, w: float = 0.5, h: float | None = None, up=(0, 0, 1)) -> None:
    """A label tile on a wall (room frame): facing = the direction the label looks (into the room)."""
    b.emit.label_fit((x, y, z), w, cell, facing, up=up) if h is None else b.emit.label((x, y, z), w, h, facing, cell, up=up)


def ceiling_panels(b: SParts, L: float, D: float, H: float, nx: int, ny: int, cell: str = "white_cool", margin: float = 1.4, w: float = 1.2, d: float = 0.6,
                   mat: str = LAMP_HOT) -> None:
    """A grid of luminous ceiling panels (brushed frame, a bright lamp face). In a v2 shell (ship_shell.py) the ceiling is its own architecture (bands, cove, grid): nothing is added."""
    if getattr(getattr(b, "_style", None), "v2", False):
        return
    for i in range(nx):
        for j in range(ny):
            cx = margin + (i + 0.5) * (L - 2 * margin) / nx
            cy = margin + (j + 0.5) * (D - 2 * margin) / ny
            F.ceiling_light_panel(b, cx - w / 2, cx + w / 2, cy - d / 2, cy + d / 2, H - 0.05, cell, mat)


def window_wall(b: SParts, wall: str, L: float, D: float, H: float, st: Style, bays: int, pier: float = 0.45, sill: float = 0.55, head: float = 3.15,
                doors: list | None = None, glass: bool = True) -> list[tuple[float, float]]:
    """A wall of tall windows: `wall` is 'far' (y = D) or 'right' (x = L). The structure keeps piers between `bays` openings (sill .. head), a
    finish layer, brushed reveals, one mullion per bay and a glass pane; returns the (s0, s1) span of every bay along the wall (its own s axis,
    the same as wall_finish: 'far' along +x, 'right' along -y)."""
    sl = wall_len(wall, L, D)
    M = wall_matrix(wall, L, D)
    s_lo, s_hi = (WS if wall == "far" else WS), sl - WS
    w = ((s_hi - s_lo) - (bays + 1) * pier) / bays
    spans = []
    fb, fine = b.body, b.fine
    with b.at(M):
        fb.box((0.0, 0.0, 0.0), (sl, WS, sill), STRUCT)
        fb.box((0.0, 0.0, head), (sl, WS, H), STRUCT)
        fb.box((0.0, -WF, 0.0), (sl, 0.0, sill), st.wall_lo)
        fb.box((0.0, -WF, head), (sl, 0.0, H), st.wall_hi)
        fb.box((0.0, -WF - 0.05, sill - 0.04), (sl, 0.0, sill + 0.02), st.trim)                       # the sill: a brushed ledge
        x = s_lo
        for k in range(bays + 1):
            fb.box((x, 0.0, sill), (x + pier, WS, head), STRUCT)
            fb.box((x, -WF, sill), (x + pier, 0.0, head), st.wall_hi)
            x += pier
            if k < bays:
                spans.append((x, x + w))
                fine.box((x - 0.03, -WF - 0.03, sill), (x, WS, head), TRIM)                          # reveals
                fine.box((x + w, -WF - 0.03, sill), (x + w + 0.03, WS, head), TRIM)
                fine.box((x, -WF - 0.03, head - 0.03), (x + w, WS, head), TRIM)
                if glass:
                    fine.box((x, WS / 2 - 0.006, sill + 0.02), (x + w, WS / 2 + 0.006, head - 0.03), GLASS)
                    fine.box((x + w / 2 - 0.025, WS / 2 - 0.02, sill + 0.02), (x + w / 2 + 0.025, WS / 2 + 0.02, head - 0.03), TRIM)      # mullion
                x += w
        fb.box((0.0, -WF - 0.06, H - 0.06), (sl, 0.0, H), st.trim)                                     # cornice
    return spans


# ------------------------------------------------------------------------------------------------------------ NAVE-2: wall and ceiling dressing
DEFAULT_BAYS = ("plain", "vent", "panelboard", "conduits", "screen", "safety", "hatch", "plain")


def dress_wall(b: SParts, wall: str, L: float, D: float, H: float, s0: float, s1: float, seed: int = 1, kinds=None, accent: str = "cyan",
               accent_dim: str = "cool_dim", bay: float = 2.0, ribs: bool = True, skip=()) -> None:
    """Layered bays of the corridor's language (panels in brushed frames, vents, breaker panels, conduit bundles, screens, hatches, extinguishers) on a stretch of a
    room wall (`wall`: near, far, left, right) with a rib every bay: the walls of a working room are never flat. s0..s1 are ROOM coordinates along the wall (x for the near
    and far walls, y for the left and right ones); a bay that would cover a door of the room (build_shell records them) is left out. `skip`: bay indexes to leave."""
    import ship_walls as W
    rng = random.Random(seed * 131 + len(wall))
    kinds = kinds or DEFAULT_BAYS
    lo, hi = min(s0, s1), max(s0, s1)
    # to the wall's own s axis (see wall_matrix): near runs along -x from x = L, right along -y from y = D
    a0, a1 = (L - hi, L - lo) if wall == "near" else (D - hi, D - lo) if wall == "right" else (lo, hi)
    n = max(1, int(round((a1 - a0) / bay)))
    w = (a1 - a0) / n
    doors = [d for d in getattr(b, "_doors", []) if d["wall"] == wall]
    spans = [(sa - 0.5, sc + 0.5) for (sa, sc, _h) in door_spans(wall, doors, L, D)]
    with b.at(wall_matrix(wall, L, D) @ T(0.0, -WF, 0.0)):
        for k in range(n):
            a, c = a0 + k * w, a0 + (k + 1) * w
            clear = not any(a < sc and c > sa for (sa, sc) in spans)
            if k not in skip and clear:
                W.bay(b.soft, kinds[(k + seed) % len(kinds)], a + 0.16, c - 0.16, H, rng, accent, accent_dim)
            if ribs and not any(sa - 0.3 < a < sc + 0.3 for (sa, sc) in spans):
                W.rib(b.soft, a, 0.0, H - 0.06, accent_dim)
        if ribs and not any(sa - 0.3 < a1 < sc + 0.3 for (sa, sc) in spans):
            W.rib(b.soft, a1, 0.0, H - 0.06, accent_dim)


def ceiling_services(b: SParts, L: float, D: float, H: float, runs, x0: float = 1.0, x1: float | None = None, seed: int = 1) -> None:
    """The service run under the ceiling of a working room: `runs` = [(y, kind)] along the room's x, kind duct | pipes | tray. They hang 0.3-0.5 m below the
    ceiling between the rows of light panels, on brackets every 2 m."""
    import ship_furniture3 as H3
    rng = random.Random(seed)
    x1 = L - 1.0 if x1 is None else x1
    for y, kind in runs:
        if kind == "duct":
            H3.duct_run(b, (x0, y, H - 0.42), (x1, y, H - 0.42), 0.55, 0.36, STEEL if rng.random() < 0.5 else IVORY, 1.4)
        elif kind == "pipes":
            H3.pipe_bundle(b, (x0, y, H - 0.30), (x1, y, H - 0.30), 3, 0.05, 0.03, (0, 1, 0), None, 1.8)
        elif kind == "tray":
            b.body.box((x0, y - 0.25, H - 0.26), (x1, y + 0.25, H - 0.22), STRUCT)
            b.body.box((x0, y - 0.25, H - 0.22), (x1, y - 0.22, H - 0.10), STRUCT)
            b.body.box((x0, y + 0.22, H - 0.22), (x1, y + 0.25, H - 0.10), STRUCT)
            for k in range(4):
                b.fine.cyl((x0, y - 0.15 + k * 0.1, H - 0.19), (x1, y - 0.15 + k * 0.1, H - 0.19), 0.016, RUBBER, seg=6)
        x = x0 + 0.8
        while x < x1 - 0.3:
            b.fine.box((x - 0.02, y - 0.3, H - 0.46), (x + 0.02, y + 0.3, H - 0.02), TRIM)
            x += 2.0
