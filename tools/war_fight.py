#!/usr/bin/env python3
"""What a battle was like to watch, from the bench's fight log (stats.fight in a record of tools/war.py): how continuous the fire was, how
accurate it was at each range, who killed whom, who broke off and when, how hot and how burning the Aquila got. BATTAGLIA-3 (docs/GUERRA.md).

  tools/war.py fight Saved/War/run.json                 one record
  tools/war.py fight --tag batch                        every Saved/War/batch_<seed>.json: a line per seed and the mean
  tools/war.py fight --tag a --vs b                     two batches side by side (the mean of each)

Definitions (all in battle seconds; the chart has one cell per second, bit 1 = an ASTRA warship fired, 2 = a Mandate warship fired, 4 = a blow
struck an ASTRA warship, 8 = a blow struck a Mandate warship):
  action          the first cell with anything in it to the last: the fight, as far as anyone could watch it
  fire share      the cells of the action where a warship (not a craft) fired, over the length of the action: "is there fire going on"
  silence         a run of cells with no fire at all inside the action (the dead stretches between a fight and the next)
  engagement      the warships' fire, split where a silence lasts longer than 20 s
  a kill          a warship destroyed or left disabled (a craft is counted apart), credited to whoever struck it last
"""
from __future__ import annotations

import json
import math
import statistics
from pathlib import Path

WEAPONS = ["rail", "laser", "missile", "torpedo", "rocket", "cannon"]
BUCKETS = [0, 2, 5, 10, 15, 20, 30, 40, 50, 70]
GAP_S = 20                                  # a silence longer than this ends an engagement


def _load(path: Path) -> dict:
    raw = Path(path).read_bytes()
    enc = "utf-16" if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else "utf-8"
    return json.loads(raw.decode(enc))


def _bucket_name(i: int) -> str:
    lo = BUCKETS[i]
    return f"{lo}+" if i == len(BUCKETS) - 1 else f"{lo}-{BUCKETS[i + 1]}"


def fight_of(d: dict) -> dict:
    """The measures of one record (the dict a line of the table is made from)."""
    st = d.get("stats", {})
    f = st.get("fight")
    m: dict = {"t": d.get("battle_seconds", 0.0), "has_log": f is not None}
    if f is None:
        return m
    bins = [int(c, 16) for c in f.get("bins", "")]
    first = next((i for i, v in enumerate(bins) if v), None)
    last = max((i for i, v in enumerate(bins) if v), default=None)
    m["action_s"] = (last - first + 1) if first is not None else 0
    m["first"], m["last"] = first, last
    if first is None:
        m.update(fire_share=0.0, action_share=0.0, longest_silence=0, silences=0, engagements=[], longest_engagement=0, cap_fire_s=0)
    else:
        span = bins[first:last + 1]
        cap = [1 if v & 3 else 0 for v in span]
        anyv = [1 if v else 0 for v in span]
        m["cap_fire_s"] = sum(cap)
        m["fire_share"] = sum(cap) / len(span)
        m["action_share"] = sum(anyv) / len(span)
        # silences: runs of cells with no warship fire at all
        runs, run = [], 0
        for c in cap:
            if c:
                if run:
                    runs.append(run)
                run = 0
            else:
                run += 1
        if run:
            runs.append(run)
        m["longest_silence"] = max(runs, default=0)
        m["silences"] = sum(1 for r in runs if r > 15)
        # engagements: the fire split where the silence lasts longer than GAP_S
        eng, start, quiet = [], None, 0
        for i, c in enumerate(cap):
            if c:
                if start is None:
                    start = i
                quiet = 0
                endi = i
            elif start is not None:
                quiet += 1
                if quiet > GAP_S:
                    eng.append((first + start, first + endi + 1))
                    start = None
        if start is not None:
            eng.append((first + start, first + endi + 1))
        m["engagements"] = eng
        m["longest_engagement"] = max((b - a for a, b in eng), default=0)
    # the accuracy at each range, per side and weapon
    acc = f.get("accuracy", {})
    m["accuracy"] = acc
    shots_by_bucket = [0] * len(BUCKETS)
    hits_by_bucket = [0] * len(BUCKETS)
    for side in ("astra", "mandate"):
        for w in ("rail", "laser", "missile", "torpedo", "rocket"):
            x = acc.get(side, {}).get(w)
            if not x:
                continue
            for i in range(len(BUCKETS)):
                shots_by_bucket[i] += x["shots"][i]
                hits_by_bucket[i] += x["hits"][i]
    m["shots_by_bucket"], m["hits_by_bucket"] = shots_by_bucket, hits_by_bucket
    # the median range of the warships' shots (rails and lasers: the guns; the missiles and torpedoes are their own story)
    rail_shots = [0] * len(BUCKETS)
    for side in ("astra", "mandate"):
        x = acc.get(side, {}).get("rail")
        if x:
            for i in range(len(BUCKETS)):
                rail_shots[i] += x["shots"][i]
    tot = sum(rail_shots)
    if tot:
        acc_n, med = 0, 0
        for i, n in enumerate(rail_shots):
            acc_n += n
            if acc_n >= tot / 2:
                med = i
                break
        m["rail_median_bucket"] = _bucket_name(med)
        m["rail_shots"] = tot
    # the kills
    kills = f.get("kills", [])
    cap_kills = [k for k in kills if not k["victim_craft"]]
    craft_kills = [k for k in kills if k["victim_craft"]]
    m["capital_kills"] = len(cap_kills)
    m["craft_kills"] = len(craft_kills)

    def cat(k: dict) -> str:
        if k["killer_aquila"]:
            return "aquila"
        if k["killer_side"] == "none":
            return "unknown"
        return f"{k['killer_side']}_{'craft' if k['killer_craft'] else 'ship'}"

    by = {}
    for k in cap_kills:
        by.setdefault(f"{k['victim_side']} lost to {cat(k)}", []).append(k)
    m["kills_by"] = {key: len(v) for key, v in sorted(by.items())}
    m["kill_weapons"] = {}
    for k in cap_kills:
        m["kill_weapons"][k["weapon"]] = m["kill_weapons"].get(k["weapon"], 0) + 1
    m["kill_times"] = sorted(round(k["t"]) for k in cap_kills)
    m["kills_ranges"] = [k["range_km"] for k in cap_kills if k["range_km"] >= 0 and not k["killer_craft"]]
    m["fleeing_kills"] = sum(1 for k in cap_kills if k["fleeing"])
    # the shots a side needed to put a warship out of action
    for si, side in enumerate(("astra", "mandate")):
        shots = 0
        for w in ("rail", "laser", "missile", "torpedo", "rocket"):
            x = acc.get(side, {}).get(w)
            if x:
                shots += sum(x["shots"])
        won = sum(1 for k in cap_kills if k["killer_side"] == side)
        m[f"shots_per_kill_{side}"] = (shots / won) if won else None
        m[f"shots_{side}"] = shots
    m["friendly_hits"] = f.get("friendly_hits_astra", 0) + f.get("friendly_hits_mandate", 0)
    m["retreats"] = f.get("retreats", [])
    # the Aquila's layer in the frames
    heat = [fr_s["ship_layer"] for fr in d.get("frames", []) for fr_s in fr["ships"] if fr_s.get("ship_layer")]
    if heat:
        m["heat_max"] = max(h["heat_pct"] for h in heat)
        step = (d["frames"][1]["t"] - d["frames"][0]["t"]) if len(d["frames"]) > 1 else 5.0
        m["heat_over70_s"] = step * sum(1 for h in heat if h["heat_pct"] >= 70)
        m["heat_over90_s"] = step * sum(1 for h in heat if h["heat_pct"] >= 90)
        m["incidents_max"] = max(h["incidents"] for h in heat)
        m["fires_max"] = max(h["fires"] for h in heat)
        m["teams_busy_max"] = max(h["teams_busy"] for h in heat)
        m["teams"] = heat[0]["teams"]
    return m


def _mean(vals: list[float]) -> tuple[float, float]:
    vals = [v for v in vals if v is not None]
    if not vals:
        return float("nan"), 0.0
    return statistics.mean(vals), (statistics.pstdev(vals) / math.sqrt(len(vals)) if len(vals) > 1 else 0.0)


def _fmt_acc(rows: list[dict]) -> list[str]:
    """Accuracy by range, over the rows: hits over shots of the guns (rails, lasers) and of the guided weapons."""
    out = []
    for label, weapons in (("guns (rails, lasers)", ("rail", "laser")), ("rails", ("rail",)), ("missiles, torpedoes", ("missile", "torpedo"))):
        cells = []
        for i in range(len(BUCKETS)):
            sh = hi = 0
            for r in rows:
                for side in ("astra", "mandate"):
                    for w in weapons:
                        x = r.get("accuracy", {}).get(side, {}).get(w)
                        if x:
                            sh += x["shots"][i]
                            hi += x["hits"][i]
            cells.append(f"{100 * hi / sh:3.0f}% of {sh:<5d}" if sh >= 5 else "      -       ")
        out.append(f"  hit rate {label:<20} " + " ".join(f"{c:>14}" for c in cells))
    head = f"  by range, km {'':<17} " + " ".join(f"{_bucket_name(i):>14}" for i in range(len(BUCKETS)))
    return [head] + out


def print_rows(rows: list[dict], names: list[str], detail: bool = True) -> None:
    for name, m in zip(names, rows):
        if not m.get("has_log"):
            print(f"  {name:>8}  (no fight log in this record: made before the log was added)")
            continue
        kb = ", ".join(f"{k}: {v}" for k, v in m["kills_by"].items()) or "no warship put out of action"
        heat = f"  heat max {m['heat_max']:.0f}% (>=90% for {m['heat_over90_s']:.0f} s), incidents max {m['incidents_max']} (fires {m['fires_max']}), teams busy max {m['teams_busy_max']}/{m['teams']}" if "heat_max" in m else ""
        print(f"  {name:>8}  battle {m['t']:5.0f} s  action {m['action_s']:4d} s  fire {100 * m['fire_share']:3.0f}% of it  longest silence {m['longest_silence']:3d} s"
              f"  engagements {len(m['engagements'])} (longest {m['longest_engagement']} s)  kills {m['capital_kills']} (craft {m['craft_kills']}); {kb}{heat}")
        if m["retreats"] and detail:
            print("            retreats: " + "; ".join(f"{r['t']:.0f} s {r['side']} {r['what']}" for r in m["retreats"][:6]) + (" ..." if len(m["retreats"]) > 6 else ""))
    ok = [m for m in rows if m.get("has_log")]
    if not ok:
        return
    def line(label: str, f, fmt="{:.1f}") -> None:
        v, e = _mean([f(m) for m in ok])
        if v == v:
            print(f"    {label:<44} {fmt.format(v)} ± {fmt.format(e)}")
    print(f"  over {len(ok)} battle(s):")
    line("battle length (s)", lambda m: m["t"], "{:.0f}")
    line("action: first shot to last (s)", lambda m: m["action_s"], "{:.0f}")
    line("fire share of the action (%)", lambda m: 100 * m["fire_share"], "{:.0f}")
    line("longest silence inside the action (s)", lambda m: m["longest_silence"], "{:.0f}")
    line("silences longer than 15 s", lambda m: m["silences"], "{:.1f}")
    line("engagements (fire split by 20 s of silence)", lambda m: len(m["engagements"]), "{:.1f}")
    line("longest engagement (s)", lambda m: m["longest_engagement"], "{:.0f}")
    line("warships put out of action", lambda m: m["capital_kills"], "{:.1f}")
    line("  ... by the Aquila", lambda m: sum(v for k, v in m["kills_by"].items() if k.endswith("to aquila")), "{:.2f}")
    line("  ... by ASTRA craft", lambda m: sum(v for k, v in m["kills_by"].items() if k.endswith("to astra_craft")), "{:.2f}")
    line("  ... by ASTRA ships (not the Aquila)", lambda m: sum(v for k, v in m["kills_by"].items() if k.endswith("to astra_ship")), "{:.2f}")
    line("  ... by Mandate craft", lambda m: sum(v for k, v in m["kills_by"].items() if k.endswith("to mandate_craft")), "{:.2f}")
    line("  ... by Mandate ships", lambda m: sum(v for k, v in m["kills_by"].items() if k.endswith("to mandate_ship")), "{:.2f}")
    line("  ... not credited", lambda m: sum(v for k, v in m["kills_by"].items() if k.endswith("to unknown")), "{:.2f}")
    line("  ... while breaking off", lambda m: m["fleeing_kills"], "{:.2f}")
    wk: dict[str, float] = {}
    for m in ok:
        for w, n in m["kill_weapons"].items():
            wk[w] = wk.get(w, 0) + n / len(ok)
    if wk:
        print("    the blow that finished them (per battle)      " + ", ".join(f"{w} {n:.1f}" for w, n in sorted(wk.items(), key=lambda x: -x[1])))
    line("ASTRA shots per kill", lambda m: m["shots_per_kill_astra"], "{:.0f}")
    line("Mandate shots per kill", lambda m: m["shots_per_kill_mandate"], "{:.0f}")
    line("rails hit a ship of their own side", lambda m: m["friendly_hits"], "{:.1f}")
    line("retreats (groups, and ships too hurt)", lambda m: len(m["retreats"]), "{:.1f}")
    if any("heat_max" in m for m in ok):
        line("Aquila: heat at the worst (%)", lambda m: m.get("heat_max"), "{:.0f}")
        line("Aquila: seconds at 90% heat or more", lambda m: m.get("heat_over90_s"), "{:.0f}")
        line("Aquila: most incidents open at once", lambda m: m.get("incidents_max"), "{:.1f}")
        line("Aquila: most fires open at once", lambda m: m.get("fires_max"), "{:.1f}")
    for ln in _fmt_acc(ok):
        print(ln)
    meds = [m.get("rail_median_bucket") for m in ok if m.get("rail_median_bucket")]
    if meds:
        print(f"  median range of the railguns' shots, by battle: {', '.join(meds[:12])}")


def cmd_fight(a) -> None:
    root = Path(__file__).resolve().parent.parent / "Saved" / "War"

    def paths_of(tag: str) -> list[Path]:
        return sorted(root.glob(f"{tag}_*.json"), key=lambda p: int(p.stem.split("_")[-1]) if p.stem.split("_")[-1].isdigit() else 0)

    if a.path:
        recs = [Path(p) for p in a.path]
        rows = [fight_of(_load(p)) for p in recs]
        print_rows(rows, [p.stem for p in recs], detail=True)
        return
    groups = [a.tag] + ([a.vs] if a.vs else [])
    for tag in groups:
        ps = paths_of(tag)
        print(f"== {tag}: {len(ps)} record(s)")
        rows = [fight_of(_load(p)) for p in ps]
        print_rows(rows, [p.stem.split("_")[-1] for p in ps], detail=not a.brief)
