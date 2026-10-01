"""The quality of the orders in a batch of arena records, from facts the bench holds (nothing here reads a model's words):

    cd mind && .venv/bin/python -m bench.war_quality <tag> [--seeds 1-8]

  accepted/refused   the game refuses an order the view could not support (no such group, a target that is not on the plot, a ship it does not command)
  repeated           the same refused order (side, group, order, target) given again within 3 minutes: an impossible order insisted on
  off plot           orders naming a target that was not on the commander's plot when it was given
  withdrawals        what the group's side knew when it was told to withdraw: sensible = it was the weaker (strength under 0.85 of the enemy near it) or its
                     morale was going (under 0.35); doubtful = clearly the stronger (1.3 or more) and its morale holding (0.5 or more)
  flip-flops         a group's order replaced by a different one within 20 s
  looks              pulses, the share that called `no_change`, orders per pulse, cost per pulse and per hour of battle, latency

The context of each order (strength, morale, the order in force, whether the target was on the plot) is recorded by the arena at the moment the order is given."""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path
from typing import Any

WAR = Path(__file__).resolve().parents[2] / "Saved" / "War"


def analyse(d: dict[str, Any]) -> dict[str, Any]:
    orders = [o for o in d["orders"] if o["name"] == "group_order"]
    ok = [o for o in orders if o.get("ok")]
    bad = [o for o in orders if not o.get("ok")]

    def key(o: dict[str, Any]) -> tuple:
        a = o["args"]
        return (a.get("side"), str(a.get("group", "")).lower(), a.get("order"), a.get("target"))
    repeated, last = 0, {}
    for o in orders:
        if o.get("ok"):
            continue
        k = key(o)
        if k in last and o["t"] - last[k] <= 180.0:
            repeated += 1
        last[k] = o["t"]
    withdrawals = {"sensible": 0, "doubtful": 0, "neutral": 0, "unknown": 0}
    for o in ok:
        if o["args"].get("order") != "withdraw":
            continue
        c = o.get("ctx") or {}
        s, e, m = c.get("strength"), c.get("enemy_near"), c.get("morale")
        if s is None or e is None:
            withdrawals["unknown"] += 1
        elif float(s) < 0.85 * float(e) or (m is not None and float(m) < 0.35):
            withdrawals["sensible"] += 1
        elif float(s) >= 1.3 * float(e) and (m is None or float(m) >= 0.5):
            withdrawals["doubtful"] += 1
        else:
            withdrawals["neutral"] += 1
    flips, prev = 0, {}
    for o in ok:
        k = (o["args"].get("side"), str(o["args"].get("group", "")).lower())
        cur = (o["args"].get("order"), o["args"].get("target"))
        if k in prev and o["t"] - prev[k][0] <= 20.0 and prev[k][1] != cur:
            flips += 1
        prev[k] = (o["t"], cur)
    off_plot = sum(1 for o in orders if (o.get("ctx") or {}).get("target_on_plot") is False)
    m = d["result"]["minds"]
    no_change = sum(int(v.get("no_change", 0)) for v in m["by_seat"].values())
    pulses = max(1, m["pulses"])
    return {"orders": len(orders), "accepted": len(ok), "refused": len(bad), "repeated": repeated, "off_plot": off_plot, "withdrawals": withdrawals, "flips": flips,
            "pulses": m["pulses"], "no_change_share": no_change / pulses, "orders_per_pulse": len(orders) / pulses, "cost_per_pulse": m["cost"] / pulses,
            "cost_per_hour": m["cost_per_hour"], "latency_median": m["latency_median"], "latency_p90": m["latency_p90"], "errors": m["errors"]}


def parse_seeds(text: str) -> list[int]:
    if "-" in text:
        lo, hi = text.split("-")
        return list(range(int(lo), int(hi) + 1))
    return [int(x) for x in text.split(",")]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tag")
    ap.add_argument("--seeds", default="1-8")
    a = ap.parse_args()
    rows = []
    for seed in parse_seeds(a.seeds):
        p = WAR / f"{a.tag}_{seed}.mind.json"
        if not p.exists():
            continue
        r = analyse(json.loads(p.read_text()))
        rows.append(r)
        w = r["withdrawals"]
        print(f"  seed {seed:>3}  orders {r['orders']:>3} (refused {r['refused']}, repeated {r['repeated']}, off plot {r['off_plot']})  withdraw {w['sensible']}/{w['doubtful']}/{w['neutral']}"
              f"  flips {r['flips']}  pulses {r['pulses']} no_change {100 * r['no_change_share']:.0f}%  ${r['cost_per_pulse'] * 1000:.2f} m/pulse  latency {r['latency_median']:.1f}/{r['latency_p90']:.1f} s")
    if not rows:
        print("no records")
        return
    tot = {k: sum(r[k] for r in rows) for k in ("orders", "accepted", "refused", "repeated", "off_plot", "flips", "pulses", "errors")}
    wd = {k: sum(r["withdrawals"][k] for r in rows) for k in rows[0]["withdrawals"]}
    print(f"== {a.tag}: {len(rows)} battles, {tot['orders']} orders ({tot['accepted']} accepted, {tot['refused']} refused, {tot['repeated']} impossible ones repeated, "
          f"{tot['off_plot']} on a target off the plot), withdrawals sensible/doubtful/neutral/unknown {wd['sensible']}/{wd['doubtful']}/{wd['neutral']}/{wd['unknown']}, "
          f"flip-flops {tot['flips']}; {tot['pulses']} looks ({tot['errors']} errors), no_change {100 * statistics.mean(r['no_change_share'] for r in rows):.0f}%, "
          f"{statistics.mean(r['orders_per_pulse'] for r in rows):.2f} orders per look, ${1000 * statistics.mean(r['cost_per_pulse'] for r in rows):.2f} m per look, "
          f"${statistics.mean(r['cost_per_hour'] for r in rows):.2f}/h of battle, latency median {statistics.mean(r['latency_median'] for r in rows):.1f} s "
          f"p90 {statistics.mean(r['latency_p90'] for r in rows):.1f} s")


if __name__ == "__main__":
    main()
