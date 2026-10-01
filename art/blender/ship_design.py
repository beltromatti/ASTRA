"""ASN Aquila — the design of the interior (NAVE-3): the ship planned the way a ship is, a programme with reasons (docs/NAVE.md §3-4).

Three layers:

  1. the STRUCTURE: what stacks from deck to deck and so has one place for the whole ship — the turbolift banks, the stair towers, the Jefferies columns (trunks and their
     arms). `apply_structure(D)` puts them in the lanes of every deck as fixed items (anchors);
  2. the DECKS: for every deck a schedule (ship_design_*.py): the passages' pieces, the rooms of every lane section by section, in the order a designer would put them, which
     the packer (ship_layout.Deck.flow) lays out round the fixed items with fillers for what is left;
  3. the PLAN's vertical part and the shuttle's line, written by ship_plan_gen from what the decks recorded here (`LOG`).

Pure Python (no bpy). `python3 art/blender/ship_design.py [--deck N]` prints the table of a deck's lanes.
"""
from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ship_plan as P  # noqa: E402
import ship_spec as SP  # noqa: E402
import ship_decks as DK  # noqa: E402  (obstacles, free_pieces, reach_rooms: the geometry of the passages)
from ship_catalog import GATE_H, GATE_W, MOD, SLOT_HW  # noqa: E402
from ship_layout import Builder, Deck, DesignError, Passage, rnd  # noqa: E402

SP_Y, SBP_Y, PP_Y = 0.0, 20.0, -20.0
GRID0 = DK.GRID0

# ======================================================================================================================== the structure
# The Jefferies columns: a K crawlway (the arm) leaves each side passage's outer wall at these x (the middle of its 4 m slot) on every deck; its first module is the trunk cell,
# a vertical ladder shaft 1.2 m square that runs from the top deck of the column to the keel. Eight columns, one a section or so, on both sides: sixteen trunks on a deck.
JCOLS = [10.0, -50.0, -142.0, -206.0, -274.0, -342.0, -406.0, -474.0]
ARM_REACH = 16.0                      # the arm's length where the hull allows it (the outer lane's depth); shorter on the decks whose hull is narrow

# The turbolift banks: two shafts side by side, 8 m x 16 m, in the lane of the passage `pid` ("SP" = the Spine's pieces, "SBP"/"PP" = a side passage's outer lane), at x_fwd (the
# forward edge). Both shafts of a bank serve the same decks. A bank is a lobby (and a cross link) where it stops and the lift's service room where it passes.
BANKS = [
    dict(id="f", name="Flight", x=52.0, pid="SP", side=+1, decks=range(4, 12), why="the bow: the Flight Deck's alcove, the assault bay, flight operations, the magazines"),
    dict(id="c", name="Concourse", x=-80.0, pid="SP", side=+1, decks=range(2, 10), why="the crew's centre: the Concourse and the Mess, the library and the shops, the CIC above, the Medbay below"),
    dict(id="d", name="Berthing", x=-204.0, pid="SP", side=-1, decks=range(2, 10), why="the Berthing, the officers' country and the medical complex"),
    dict(id="e", name="Engineering", x=-308.0, pid="SP", side=-1, decks=range(2, 13), why="Main Engineering's entrance, the life-support plants, the stores and the workshops below"),
    dict(id="g", name="Aft", x=-404.0, pid="SP", side=-1, decks=range(2, 13), why="the aft crew spaces, the stern machinery and the keel"),
    dict(id="h", name="Stern", x=-444.0, pid="SP", side=-1, decks=range(4, 13), why="the engine rooms and the radiators' pumps"),
    dict(id="m1", name="Mess starboard", x=-148.0, pid="SBP", side=+1, decks=range(4, 13), why="the Mess Hall's flank and the Berthing: the outer lane, because the Mess hides the Spine here"),
    dict(id="m2", name="Mess port", x=-148.0, pid="PP", side=-1, decks=range(4, 13), why="the same on the port side"),
]
# The stair towers: 8 x 8 m off the Spine (x of the aft edge, side), a column through every deck; an 8 x 8 damage-control station stands behind each, on the passage
STAIRS = [(28.0, +1), (-92.0, -1), (-216.0, +1), (-292.0, +1), (-408.0, +1), (-472.0, +1)]

LOG: dict = {"banks": {}, "stairs": {}, "arms": {}, "decks": {}}


def tower_id(deck: int, x_min: float) -> str:
    return f"d{deck}_stair_{int(abs(x_min))}{'n' if x_min < 0 else 'p'}"


def bank_id(deck: int, bank: str) -> str:
    return f"d{deck}_lift_{bank}"


# ============================================================================================================================ a deck
def new_deck(B: Builder, deck: int, keel: bool = False) -> Deck:
    """The deck's passages (the Spine, the Starboard and Port Passages, in the free pieces between the halls of the existing rooms) and their partners."""
    D = Deck(B, deck, f"d{deck}")
    env = D.env
    obs = DK.obstacles(deck)
    xh = (int(env["x_fwd"] // MOD)) * MOD
    xl = -524.0 if deck >= 3 else -496.0
    spine = DK.reach_rooms(deck, SP_Y, DK.free_pieces(deck, SP_Y, env, obs, xh, xl))
    K = "K" if keel else None
    for i, (a0, a1) in enumerate(spine):
        D.passage(f"SP{i}", K or "S", "x", SP_Y, a0, a1, "Keel Crawlway" if keel else "Spine")
    for i, (a0, a1) in enumerate(DK.free_pieces(deck, SBP_Y, env, obs, xh, xl)):
        D.passage(f"SB{i}", K or "P", "x", SBP_Y, a0, a1, "Starboard Crawlway" if keel else "Starboard Passage")
    for i, (a0, a1) in enumerate(DK.free_pieces(deck, PP_Y, env, obs, xh, xl)):
        D.passage(f"PO{i}", K or "P", "x", PP_Y, a0, a1, "Port Crawlway" if keel else "Port Passage")
    D.reserve_bulkheads()
    for o in obs:                                                           # the halls of the existing rooms: nothing is laid on them
        D.rects.append((o[0], o[1], o[2], o[3], "an existing hall"))
    for pid, ps in D.passages.items():
        if pid.startswith("SP"):
            for side, prefix in ((+1, "SB"), (-1, "PO")):
                cand = [q for q in D.passages.values() if q.pid.startswith(prefix) and q.a0 <= ps.a1 and q.a1 >= ps.a0]
                if cand:
                    best = max(cand, key=lambda q: min(q.a1, ps.a1) - max(q.a0, ps.a0))
                    D.partner[(pid, side)] = best.pid
                    D.partner[(best.pid, -side)] = pid
    return D


def piece_at(D: Deck, prefix: str, x0: float, x1: float, pos: float | None = None) -> Passage | None:
    """The passage of the family `prefix` (SP, SB, PO) that covers [x0, x1]."""
    for ps in D.passages.values():
        if ps.along == "x" and ps.pid.startswith(prefix) and (pos is None or abs(ps.pos - pos) < 1e-6) and ps.a0 <= x0 + 1e-6 and ps.a1 >= x1 - 1e-6 and ps.pid[2:3] != "J":
            return ps
    return None


BRIDGE_LOBBY = (-22.8, -8.2, -14.8, -2.0)      # the command lift's lobby on the decks below the bridge (the shafts stand aft of it: ship_vertical.BRIDGE_SHAFTS)


def bridge_bank(D: Deck) -> None:
    """The command turbolifts' lobby on a deck below the bridge: a special room against the Spine's port wall, at x -22.8 .. -14.8; the lane's 16 m round it are reserved."""
    ps = piece_at(D, "SP", -28.0, -12.0)
    if ps is None:
        LOG["decks"][D.deck]["skipped"].append("bridge bank")
        return
    D.anchor(ps.pid, -1, -12.0, ("gap", 16.0))
    cid = f"d{D.deck}_lift_b"
    x0, y0, x1, y1 = BRIDGE_LOBBY
    r = D.special(cid, "lift_bank_b", (x1, y1), 180.0, [x0, y0, x1, y1], P.section_of(D.deck, (x0 + x1) / 2), name="Command Turbolift Lobby")
    D.gate(r, f"d{D.deck}_gate_lift_b", ps.pid, -18.0, -1, GATE_W, GATE_H)
    LOG["decks"][D.deck]["banks"]["b"] = dict(pid=ps.pid, side=-1, x1=-14.8, key="lift_bank_b")


def apply_structure(D: Deck, towers: bool = True, banks: bool = True, arms: bool = True) -> None:
    """The fixed items of the ship on this deck (see the module's docstring). Whatever cannot stand here (an obstacle: a hall) is left out and said in LOG."""
    deck = D.deck
    obs = DK.obstacles(deck)
    log = LOG["decks"].setdefault(deck, {"banks": {}, "towers": [], "arms": [], "skipped": []})
    if banks and deck >= 2:
        bridge_bank(D)
    if towers:
        for (tx, side) in STAIRS:
            ps = piece_at(D, "SP", tx, tx + 8.0)
            rect = [tx, 2.0, tx + 8.0, 10.0] if side > 0 else [tx, -10.0, tx + 8.0, -2.0]
            hw = P.half_width_at(D.env, tx) or 0.0
            if ps is None or DK.hits(rect, obs) or hw <= 12.0:
                log["skipped"].append(f"stair {tx:+.0f}")
                continue
            D.anchor(ps.pid, side, tx + 8.0, ("stair_tower", {"id": tower_id(deck, tx)}), back="dc_station")
            log["towers"].append(tx)
    if banks:
        for bk in BANKS:
            if deck not in bk["decks"]:
                continue
            stop = True                                       # both shafts stop on every deck of their range (a lift of the bridge's kind would not: NAVE-3 §4)
            x1 = bk["x"]
            if bk["pid"] == "SP":
                ps = piece_at(D, "SP", x1 - 8.0, x1)
                rect = [x1 - 8.0, 2.0 if bk["side"] > 0 else -18.0, x1, 18.0 if bk["side"] > 0 else -2.0]
                inner = True
            else:
                ps = piece_at(D, "SB" if bk["pid"] == "SBP" else "PO", x1 - 8.0, x1)
                rect = [x1 - 8.0, 22.0 if bk["side"] > 0 else -38.0, x1, 38.0 if bk["side"] > 0 else -22.0]
                inner = False
            hw = min(P.half_width_at(D.env, x1 - 8.0) or 0.0, P.half_width_at(D.env, x1) or 0.0)
            if ps is None or DK.hits(rect, obs) or hw < max(abs(rect[1]), abs(rect[3])) + 0.5:
                log["skipped"].append(f"bank {bk['id']}")
                continue
            key = ("lift_bank" if inner else "lift_bank_o") if stop else ("lift_pass" if inner else "lift_pass_o")
            D.anchor(ps.pid, bk["side"], x1, (key, {"id": bank_id(deck, bk["id"]), "bank": bk["id"], "name": f"{bk['name']} Turbolift Lobby" if stop else f"{bk['name']} Lift Service Room"}))
            log["banks"][bk["id"]] = dict(pid=ps.pid, side=bk["side"], x1=x1, key=key)
    if arms:
        for k, xc in enumerate(JCOLS):
            for side, prefix in ((+1, "SB"), (-1, "PO")):
                n = arm_modules(D, xc, side)
                if n == 0:
                    log["skipped"].append(f"arm J{k + 1}{'S' if side > 0 else 'P'}")
                    continue
                ps = piece_at(D, prefix, xc - 2.0, xc + 2.0)
                if ps is None:
                    log["skipped"].append(f"arm J{k + 1}{'S' if side > 0 else 'P'} (no passage)")
                    continue
                top = trunk_variant(deck, k)
                try:
                    D.anchor(ps.pid, side, xc + 2.0, ("arm", n, "K", {"trunk": top, "name": f"Jefferies Tube J-{k + 1}{'S' if side > 0 else 'P'}", "col": k, "end": "wall"}))
                except DesignError as e:                          # (a bulkhead's slot at this x on this deck: the column starts one deck lower)
                    log["skipped"].append(f"arm J{k + 1}{'S' if side > 0 else 'P'}: {e}")
                    continue
                log["arms"].append((k, side, n))


_ARMS: dict = {}


def arm_n(deck: int, xc: float, side: int) -> int:
    """How many 4 m modules the hull lets a Jefferies arm have at xc, on one side of this deck (0: none). Pure geometry: the outer lane beyond the side passage."""
    key = (deck, xc, side)
    if key in _ARMS:
        return _ARMS[key]
    env = P.envelope(deck)
    obs = DK.obstacles(deck)
    n = 0
    for k in range(1, int(ARM_REACH / MOD) + 1):
        y0, y1 = (22.0 + (k - 1) * MOD, 22.0 + k * MOD) if side > 0 else (-22.0 - k * MOD, -22.0 - (k - 1) * MOD)
        hw = min(P.half_width_at(env, xc - 2.0) or 0.0, P.half_width_at(env, xc + 2.0) or 0.0)
        if DK.hits([xc - 2.0, y0, xc + 2.0, y1], obs) or hw < max(abs(y0), abs(y1)) + 0.01:
            break
        n = k
    _ARMS[key] = n
    return n


def arm_modules(D: Deck, xc: float, side: int) -> int:
    return arm_n(D.deck, xc, side)


def trunk_variant(deck: int, col: int, side: int = 0) -> str:
    """The trunk cell of a deck: the top of the column on the highest deck that has an arm at this column, the bottom on the lowest, a through shaft between. (Both sides have
    the same decks: the hull is symmetric.)"""
    have = [d for d in range(2, 13) if arm_n(d, JCOLS[col], +1) > 0]
    if deck == min(have):
        return "TrunkTop"
    if deck == max(have):
        return "TrunkBottom"
    return "Trunk"


# ============================================================================================================================ the decks
DESIGNS: dict = {}                       # deck -> function(D): the schedule of the deck (ship_design_*.py register theirs here)
SETUPS: dict = {}                        # deck -> function(D), called first: the extents of the passages, the special rooms (a hall that takes over the end of a corridor)


def register(deck: int, schedule, setup=None) -> None:
    DESIGNS[deck] = schedule
    if setup is not None:
        SETUPS[deck] = setup


def default_design(D: Deck) -> None:
    """A deck with no schedule yet: every lane of every passage filled with stores (a stand-in while the decks are being written)."""
    for pid, ps in list(D.passages.items()):
        if ps.along != "x":
            continue
        for side in ((+1, -1) if pid.startswith("SP") else (+1,) if pid.startswith("SB") else (-1,)):
            D.flow(pid, side, {}, ["store_dry", "heads", "hold"])


def build_all(B: Builder, only: tuple | None = None) -> dict:
    """Every deck of the lower hull and the block (2-12): passages, structure, schedule, emitted. Deck 1 (the bridge complex) is ship_plan_gen's."""
    import ship_design_decks  # noqa: F401  (registers the schedules)
    decks = {}
    for deck in range(2, 13):
        if only and deck not in only:
            continue
        D = new_deck(B, deck, keel=(deck == 12))
        if deck in SETUPS:
            SETUPS[deck](D)
        apply_structure(D)
        DESIGNS.get(deck, default_design)(D)
        D.emit()
        D.finish_doors()
        decks[deck] = D
    return decks


# ================================================================================================================================ reports
def lane_table(D: Deck) -> str:
    """The table of a deck's lanes: for every lane the items from the bow to the stern with their extents (a gap is written `gap`)."""
    out = [f"DECK {D.deck}"]
    for (pid, side), log in sorted(D.lane_log.items(), key=lambda kv: (kv[0][0], -kv[0][1])):
        items = sorted(log, key=lambda t: -t[0])
        parts = []
        for (x1, x0, what) in items:
            parts.append(f"{what}[{x1:.0f}..{x0:.0f}]")
        out.append(f"  {pid}{side:+d}: " + " ".join(parts))
    return "\n".join(out)


def lane_runs(D: Deck, pid: str, side: int) -> dict:
    """The free stretches of a lane by section (before anything is flowed): {letter: [(forward edge, aft edge, length)]} — the room the schedule has to fill. The bulkhead's slot
    and the cross link after it are counted as taken."""
    ps = D.passages[pid]
    out = {}
    anchors = sorted(D.anchors.get((pid, side), []), key=lambda a: -a["x1"])
    link = bool(D.partner.get((pid, side)))
    for k, (letter, xmin, xmax) in enumerate(P.sections(D.deck)):
        lo, hi = max(xmin, ps.a0), min(xmax, ps.a1)
        if hi - lo < 4.0 - 1e-6:
            continue
        obs = [(a["x0"], a["x1"]) for a in anchors if a["x1"] > lo + 1e-6 and a["x0"] < hi - 1e-6]
        if k > 0 and abs(hi - xmax) < 1e-6:
            obs.append((hi - MOD, hi))
            if link and not any(min(o1, hi - MOD) - max(o0, hi - 2 * MOD) > 1e-6 for (o0, o1) in obs):
                obs.append((hi - 2 * MOD, hi - MOD))
        obs.sort(key=lambda o: -o[1])
        runs, cur = [], hi
        for (o0, o1) in obs:
            if o1 < cur - 1e-6:
                runs.append((cur, max(o1, lo)))
            cur = min(cur, o0)
        if cur - lo > 1e-6:
            runs.append((cur, lo))
        out[letter] = [(a, b, a - b) for (a, b) in runs if a - b > 1e-6]
    return out


def runs_table(D: Deck) -> str:
    lines = [f"DECK {D.deck} free runs (forward edge .. aft edge = length)"]
    for pid in sorted(D.passages):
        ps = D.passages[pid]
        if ps.along != "x":
            continue
        for side in (+1, -1):
            if pid.startswith("SB") and side < 0 or pid.startswith("PO") and side > 0:
                continue
            r = lane_runs(D, pid, side)
            parts = [f"{l}: " + " ".join(f"{a:.0f}..{b:.0f}={n:.0f}" for a, b, n in v) for l, v in r.items()]
            lines.append(f"  {pid}{side:+d} [{ps.a1:.0f}..{ps.a0:.0f}]  " + " | ".join(parts))
    return "\n".join(lines)
