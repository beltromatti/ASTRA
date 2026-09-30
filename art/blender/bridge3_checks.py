"""ASN Aquila bridge v3: layout checks (pure Python). Footprints of the furniture in the layout frame, minimum distances between
them and to the walls, the well edge and the rails, and the clearance along the officers' walking routes. The generator prints
the table and writes it into the manifest: the layout is verified, not eyeballed.
"""
from __future__ import annotations

import math


def circle(cx: float, cy: float, r: float, n: int = 40):
    return [(cx + r * math.cos(2 * math.pi * k / n), cy + r * math.sin(2 * math.pi * k / n)) for k in range(n)]


def rot(p, yaw_deg: float):
    a = math.radians(yaw_deg)
    return (p[0] * math.cos(a) - p[1] * math.sin(a), p[0] * math.sin(a) + p[1] * math.cos(a))


def place(poly_local, pos, yaw_deg: float):
    out = []
    for p in poly_local:
        q = rot(p, yaw_deg)
        out.append((q[0] + pos[0], q[1] + pos[1]))
    return out


def fan_local(a: float, r0: float, r1: float, n: int = 16):
    pts = [(r1 * math.cos(math.radians(-a + 2 * a * k / n)), r1 * math.sin(math.radians(-a + 2 * a * k / n))) for k in range(n + 1)]
    pts += [(r0 * math.cos(math.radians(a - 2 * a * k / n)), r0 * math.sin(math.radians(a - 2 * a * k / n))) for k in range(n + 1)]
    return pts


def rect_local(x0, x1, y0, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def seg_dist(p, a, b) -> float:
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    ln2 = dx * dx + dy * dy
    t = 0.0 if ln2 < 1e-12 else max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / ln2))
    return math.hypot(p[0] - (ax + t * dx), p[1] - (ay + t * dy))


def inside(poly, p) -> bool:
    n = len(poly)
    c = False
    j = n - 1
    for i in range(n):
        (xi, yi), (xj, yj) = poly[i], poly[j]
        if (yi > p[1]) != (yj > p[1]) and p[0] < (xj - xi) * (p[1] - yi) / (yj - yi + 1e-18) + xi:
            c = not c
        j = i
    return c


def poly_dist(A, B) -> float:
    """Minimum distance between two polygons (0 when they overlap), by vertices and edges."""
    if any(inside(B, p) for p in A) or any(inside(A, p) for p in B):
        return 0.0
    best = 1e9
    for poly, other in ((A, B), (B, A)):
        for p in poly:
            for i in range(len(other)):
                best = min(best, seg_dist(p, other[i], other[(i + 1) % len(other)]))
    return best


def point_poly_dist(p, poly) -> float:
    if inside(poly, p):
        return 0.0
    return min(seg_dist(p, poly[i], poly[(i + 1) % len(poly)]) for i in range(len(poly)))


def footprints(D: dict, fans: dict) -> dict:
    """Named footprints (polygons in layout xy). `fans` gives the fan parameters per console kind: {kind: (a, r0, r1)}."""
    out = {}
    tx, ty = D["holo_table"]["pos"]
    out["table"] = circle(tx, ty, D["holo_table"]["radius"] + 0.02, 48)
    dh = D["dais"]
    out["dais"] = [(dh["half_x"] * math.cos(2 * math.pi * k / 48), dh["half_y"] * math.sin(2 * math.pi * k / 48)) for k in range(48)]
    for st in D["stations"]:
        sid, pos, yaw = st["id"], st["pos"], st["yaw"]
        if st.get("type") in fans:
            a, r0, r1 = fans[st["type"]]
            out[f"{sid}_console"] = place(fan_local(a, r0, r1 + 0.03), pos, yaw)
        if st["kind"] in ("console_seated", "xo_chair", "captain_chair"):
            out[f"{sid}_chair"] = place(circle(0.0, 0.0, 0.31, 20), pos, yaw)
        if st["kind"] in ("xo_chair", "captain_chair"):
            out[f"{sid}_chair"] = place(rect_local(-0.30, 0.36, -0.46, 0.46), pos, yaw)
    for p in D.get("props", []):
        out[f"{p['id']}"] = place(rect_local(-0.30, 0.36, -0.46, 0.46), p["pos"], p.get("yaw", 0.0))
    sw = D["well"]["stair_width"]
    for i, y in enumerate(D["well"]["stairs_y"]):
        out[f"stairs_{'port' if y < 0 else 'starboard'}"] = rect_local(D["well"]["edge_x"], D["well"]["edge_x"] + 0.75, y - sw / 2, y + sw / 2)
    return out


def check_layout(D: dict, fans: dict, walls) -> dict:
    """Pairwise clearances and the distance of each footprint to the walls. Returns {"pairs": [...], "walls": [...], "problems": [...]}."""
    fp = footprints(D, fans)
    names = sorted(fp)
    pairs, problems = [], []
    intended = lambda a, b: a.split("_")[0] == b.split("_")[0]           # a station's chair and console
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if intended(a, b):
                continue
            d = poly_dist(fp[a], fp[b])
            if d < 1.2:
                pairs.append({"a": a, "b": b, "min_distance_m": round(d, 2)})
                if d < 0.30 and not ({a, b} <= {"dais", "captain_chair", "xo_chair", "guest_chair"} or "dais" in (a, b)):
                    problems.append(f"{a} and {b} are only {d:.2f} m apart")
    wall_rows = []
    for nm in names:
        if nm in ("dais", "table") or nm.startswith("stairs"):
            continue
        dmin = 9.0
        for w in walls:
            for p in fp[nm]:
                t = w.t_of(*p)                       # outward distance beyond the inner face (>0 = inside the wall)
                if w.s_of(*p) < -0.1 or w.s_of(*p) > w.L + 0.1:
                    continue
                dmin = min(dmin, -t)
        wall_rows.append({"name": nm, "wall_distance_m": round(dmin, 2)})
        if dmin < 0.02:
            problems.append(f"{nm} touches a wall ({dmin:.2f} m)")
    return {"pairs": pairs, "walls": wall_rows, "problems": problems, "footprints": {k: [[round(x, 3), round(y, 3)] for x, y in v] for k, v in fp.items()}}


def check_routes(D: dict, fans: dict, clearance: float = 0.5) -> list:
    """Distance from every route segment to every footprint (except the walker's own seat)."""
    fp = footprints(D, fans)
    rows = []
    for st_id, route in D.get("routes", {}).get("to_starboard_door", {}).items():
        worst = (9.0, "")
        for (a, b) in zip(route[:-1], route[1:]):
            for nm, poly in fp.items():
                if nm.startswith(st_id + "_") or nm.startswith("stairs_") or (nm == "dais" and st_id in ("captain", "xo")):
                    continue
                n = 12
                for k in range(n + 1):
                    p = (a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n)
                    d = point_poly_dist(p, poly)
                    if d < worst[0]:
                        worst = (d, nm)
        rows.append({"route": st_id, "min_clearance_m": round(worst[0], 2), "nearest": worst[1], "ok": worst[0] >= clearance})
    return rows
