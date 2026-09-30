"""ASTRA ships v3 — panels on plates: a binary partition of each plate's top into panels (thin slabs with the seams between
them), and the `Panel` handle the greeble pass uses to stand things on the surface (hatches, vents, blisters, labels)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

import ship3_geo as G
import ship3_loft as LF
from ship3_loft import Plate


@dataclass
class PanelStyle:
    """How a plate's top is panelled."""
    min_size: tuple = (2.4, 1.6)          # metres (along, across)
    max_size: tuple = (9.0, 5.5)
    seam: tuple = (0.07, 0.16)
    margin: float = 0.25
    lifts: tuple = (0.035, 0.07, 0.11)
    lift_w: tuple = (0.45, 0.35, 0.2)
    chamfer: float = 0.03
    rim: float = 0.07
    p_stop: float = 0.35                  # chance to stop splitting a panel that is already small enough
    tone_sigma: float = 0.045
    p_alt: float = 0.05                   # chance of an access panel in another material


@dataclass
class Panel:
    plate: Plate
    quad: np.ndarray                      # (4,2) corners in (a, w): the panel's outline on the plate
    lift: float
    mat: str

    def size_m(self):
        q = self.quad
        sw = self.plate.zone.sw(float(q[:, 0].mean()))
        la = 0.5 * (abs(q[1, 0] - q[0, 0]) + abs(q[2, 0] - q[3, 0]))
        lw = 0.5 * (abs(q[3, 1] - q[0, 1]) + abs(q[2, 1] - q[1, 1])) * sw
        return la, lw

    def pts(self, uv) -> tuple:
        """uv (n,2) unit coordinates on the panel -> (P (n,3), N (n,3), T (n,3)) on its top surface."""
        q = self.quad
        uv = np.atleast_2d(np.asarray(uv, np.float64))
        u, v = uv[:, 0:1], uv[:, 1:2]
        aw = q[0] * (1 - u) * (1 - v) + q[1] * u * (1 - v) + q[2] * u * v + q[3] * (1 - u) * v
        return self.plate.top(aw[:, 0], aw[:, 1], self.lift)

    def frame_at(self, u: float, v: float):
        """(P (3,), R (3,3) rows = axes with z the normal and x along the hull) at unit coordinates."""
        P, N, T = self.pts([[u, v]])
        return P[0], G.frame_z(N[0], T[0])


def _bilinear(q: np.ndarray, u: float, v: float) -> np.ndarray:
    return q[0] * (1 - u) * (1 - v) + q[1] * u * (1 - v) + q[2] * u * v + q[3] * (1 - u) * v


def _bsp(rng, u0, u1, v0, v1, la, lw, sty: PanelStyle, out: list) -> None:
    """Recursive partition of a unit rectangle whose real size is la x lw metres."""
    A, B = (u1 - u0) * la, (v1 - v0) * lw
    can_a, can_b = A >= 2 * sty.min_size[0], B >= 2 * sty.min_size[1]
    if not can_a and not can_b:
        out.append((u0, u1, v0, v1))
        return
    if A <= sty.max_size[0] and B <= sty.max_size[1] and rng.random() < sty.p_stop:
        out.append((u0, u1, v0, v1))
        return
    along = can_a and (not can_b or (A / sty.min_size[0]) * rng.uniform(0.7, 1.3) >= (B / sty.min_size[1]))
    r = rng.uniform(0.32, 0.68)
    if along:
        um = u0 + (u1 - u0) * r
        _bsp(rng, u0, um, v0, v1, la, lw, sty, out)
        _bsp(rng, um, u1, v0, v1, la, lw, sty, out)
    else:
        vm = v0 + (v1 - v0) * r
        _bsp(rng, u0, u1, v0, vm, la, lw, sty, out)
        _bsp(rng, u0, u1, vm, v1, la, lw, sty, out)


def panelize(g: G.Geo, plate: Plate, rng: np.random.Generator, sty: PanelStyle, prefix: str, alt_mats=("Frame",)) -> list[Panel]:
    """Panels on a plate's top; the plate keeps them in `plate.panels` for the greeble pass."""
    am = 0.5 * (plate.a0 + plate.a1)
    sw = plate.zone.sw(am)
    q = LF._inset_quad(plate.outline, sty.margin, sw)
    la, lw = plate.size_m()
    la, lw = la - 2 * sty.margin, lw - 2 * sty.margin
    if la < sty.min_size[0] or lw < sty.min_size[1]:
        return []
    leaves: list = []
    _bsp(rng, 0.0, 1.0, 0.0, 1.0, la, lw, sty, leaves)
    panels: list[Panel] = []
    for (u0, u1, v0, v1) in leaves:
        seam = rng.uniform(*sty.seam)
        du, dv = 0.5 * seam / max(la, 1e-6), 0.5 * seam / max(lw, 1e-6)
        uu0 = u0 + (du if u0 > 1e-9 else 0.0)
        uu1 = u1 - (du if u1 < 1 - 1e-9 else 0.0)
        vv0 = v0 + (dv if v0 > 1e-9 else 0.0)
        vv1 = v1 - (dv if v1 < 1 - 1e-9 else 0.0)
        if uu1 - uu0 < 0.01 or vv1 - vv0 < 0.01:
            continue
        quad = np.array([_bilinear(q, uu0, vv0), _bilinear(q, uu1, vv0), _bilinear(q, uu1, vv1), _bilinear(q, uu0, vv1)])
        pw = np.array(sty.lift_w, float) if len(sty.lift_w) == len(sty.lifts) else np.ones(len(sty.lifts))
        lift = float(rng.choice(sty.lifts, p=pw / pw.sum()))
        mat = plate.mat
        if rng.random() < sty.p_alt:
            mat = prefix + str(rng.choice(alt_mats))
        tone = float(np.clip(plate.tone + rng.normal(0.0, sty.tone_sigma), 0.02, 0.98))
        if LF.slab(g, plate.zone, quad, mat, plate.thick, lift, lift, sty.chamfer, sty.rim, 0.05, tone=tone, kind="panel",
                   stations=True, wall_grime=0.5):
            panels.append(Panel(plate, quad, lift, mat))
    plate.panels = panels
    return panels
