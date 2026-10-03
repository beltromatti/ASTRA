"""ASTRA ships: the hull a class plan must lie inside (FLOTTA-VIVA, docs/FLOTTA-VIVA.md §2).

Reads the profile that ship_hull_probe.py measured on the exported mesh (data/ship/plans/hulls/<class>.json) and answers, in the mesh's own
frame (X to the bow, Y to starboard, Z up, metres): how far out the skin stands at a station and a height (conservatively: what a room can
safely be inside of), where the body of the hull starts and ends, and where a hatch on the skin would be. Pure Python (no numpy, no Blender):
the plan generator runs anywhere `python3` does.

The probe's numbers are the plating's vertices, and a plate or a turret is a few of them out of many: the profile is smoothed (a median along
the ship, then a minimum over a short stretch: a room is never put where only a detail stands) and it is the *inside* of that skin the plan uses.
"""
from __future__ import annotations

import json
import math
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
HULLS = os.path.join(ROOT, "data", "ship", "plans", "hulls")


def _median(v):
    s = sorted(v)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


class Hull:
    """The measured skin of one class (see ship_hull_probe.py for the file's meaning)."""

    def __init__(self, key: str, path: str | None = None):
        self.key = key
        p = json.load(open(path or os.path.join(HULLS, key + ".json"), encoding="utf-8"))
        self.x0, self.dx, self.nx = p["x0"], p["dx"], p["nx"]
        self.z0, self.dz, self.nz = p["z0"], p["dz"], p["nz"]
        self.bounds = p["bounds"]
        self.mesh = p.get("mesh", "")
        nan = float("nan")
        raw = {s: [[nan if c is None else c for c in row] for row in p[s]] for s in ("right", "left")}
        # per band along the ship: a median over +-3 stations, then the minimum over +-2 (spikes up and down go; the skin stays)
        self.R = self._smooth(raw["right"])
        self.L = self._smooth(raw["left"])
        self.lane_edges = p["lane_edges"]
        self.lane_top = p["lane_top"]
        self.lane_bot = p["lane_bot"]

    def _smooth(self, M):
        nx, nz = self.nx, self.nz
        out = [[float("nan")] * nz for _ in range(nx)]
        for k in range(nz):
            col = [M[i][k] for i in range(nx)]
            med = [float("nan")] * nx
            for i in range(nx):
                seg = [v for v in col[max(0, i - 3): i + 4] if v == v]
                if len(seg) >= 2:
                    med[i] = _median(seg)
            for i in range(nx):
                seg = [v for v in med[max(0, i - 2): i + 3] if v == v]
                if seg:
                    out[i][k] = min(seg)
        return out

    # ------------------------------------------------------------------------------------------------------ the skin
    def _i(self, x: float) -> int:
        return max(0, min(self.nx - 1, int((x - self.x0) / self.dx)))

    def _ks(self, za: float, zb: float):
        k0 = max(0, int(math.floor((za - self.z0) / self.dz)))
        k1 = min(self.nz - 1, int(math.floor((zb - self.z0) / self.dz)))
        return range(k0, k1 + 1)

    def half_width(self, x: float, za: float, zb: float) -> float:
        """The distance from the axis to the skin, to the nearer side, over the heights za..zb: the median of the bands there (a recess in one band, a hatch
        or a vent, is not where the hull ends; 0: no body there)."""
        i = self._i(x)
        vals = []
        for k in self._ks(za, zb):
            band = [M[i][k] for M in (self.R, self.L) if M[i][k] == M[i][k]]
            if len(band) == 2:
                vals.append(min(band))
            elif band:
                vals.append(band[0])
        return _median(vals) if vals else 0.0

    def side_skin(self, x: float, z: float, side: int) -> float:
        """The skin on one side (+1 starboard, -1 port) at x and height z, with a little reach about z (the nearest measured band when this one is empty)."""
        M = self.R if side > 0 else self.L
        i = self._i(x)
        k = max(0, min(self.nz - 1, int((z - self.z0) / self.dz)))
        for d in (0, 1, -1, 2, -2, 3, -3):
            kk = k + d
            if 0 <= kk < self.nz:
                for di in (0, -1, 1):
                    ii = i + di
                    if 0 <= ii < self.nx:
                        v = M[ii][kk]
                        if v == v:
                            return v
        return 0.0

    # ------------------------------------------------------------------------------------------------------ the body
    def x_range(self):
        return self.bounds["min"][0], self.bounds["max"][0]

    def body_z(self, x_a: float, x_b: float, lanes=(0, 1, 2, 3)):
        """(bottom, top) of the hull's body between x_a and x_b: the median over the stations of the keel and of the top of the central lanes (a tower is not the body)."""
        bots, tops = [], []
        for i in range(self._i(x_a), self._i(x_b) + 1):
            for j in lanes:
                t, b = self.lane_top[i][j], self.lane_bot[i][j]
                if t is not None and b is not None:
                    tops.append(t)
                    bots.append(b)
        if not tops:
            return self.bounds["min"][2], self.bounds["max"][2]
        return _median(bots), _median(tops)

    def lane_z(self, x_a: float, x_b: float, lane: int):
        """(bottom, top) medians of one lane (0..8 across the ship, in |y| / the widest) between x_a and x_b, or None."""
        bots, tops = [], []
        for i in range(self._i(x_a), self._i(x_b) + 1):
            t, b = self.lane_top[i][lane], self.lane_bot[i][lane]
            if t is not None and b is not None:
                tops.append(t)
                bots.append(b)
        return (_median(bots), _median(tops)) if tops else None


def load(key: str) -> Hull:
    return Hull(key)


if __name__ == "__main__":
    import sys

    for key in sys.argv[1:] or ["lethe", "styx", "acheron", "vigilant", "praetorian", "freighter", "station"]:
        h = Hull(key)
        xa, xb = h.x_range()
        print(f"== {key}: x {xa:.0f}..{xb:.0f}  z {h.bounds['min'][2]:.0f}..{h.bounds['max'][2]:.0f}  y {h.bounds['min'][1]:.0f}..{h.bounds['max'][1]:.0f}")
        n = 12
        for s in range(n):
            a = xa + (xb - xa) * s / n
            b = xa + (xb - xa) * (s + 1) / n
            bz = h.body_z(a, b)
            hw = [h.half_width(0.5 * (a + b), bz[0] + f * (bz[1] - bz[0]), bz[0] + (f + 0.25) * (bz[1] - bz[0])) for f in (0.0, 0.25, 0.5, 0.75)]
            print(f"   x {a:7.0f}..{b:7.0f}  body z {bz[0]:6.1f}..{bz[1]:6.1f}  inscribed hw by quarter-height {['%.1f' % v for v in hw]}")
