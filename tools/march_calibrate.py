#!/usr/bin/env python3
"""Calibrate the March's abstract battle model (mind/astra_mind/march_battle.py) against the war bench of the simulation (the C++ commandlet
AstraWarSim, run headless as tools/war.py runs it): the March resolves fleet battles away from the Aquila with a small model, and the model has to
give what the real simulation gives. docs/GUERRA.md §10.

  tools/march_calibrate.py cpp   [--only name,name] [--seeds 24] [--seconds 600]    run the experiments in the commandlet; writes data/march/cal_cpp.json
  tools/march_calibrate.py model [--only ...] [--runs 400]                           the same experiments through the abstract model (no engine), side by side
  tools/march_calibrate.py fit   [--iters 400]                                       search the model's global constants against cal_cpp.json
  tools/march_calibrate.py list                                                      the experiments

An experiment is two fleets (classes and numbers, wings, how many battle groups) 30 km apart; each is fought in both orders of creation (the sides' ship
order biases a tick: docs/GUERRA.md §8.10) and the results are pooled. Scenarios are written to Saved/War/cal/ and passed to the commandlet by a path
relative to data/war/scenarios; nothing is added to the repository but the aggregated results (data/march/cal_cpp.json).
Never starts the editor or the game: only the headless commandlet, at most two processes at once (tools/war.py's MAX_PROCESSES)."""
from __future__ import annotations

import argparse
import importlib.util
import json
import math
import statistics
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "mind"))
CAL_DIR = ROOT / "Saved" / "War" / "cal"
RESULTS = ROOT / "data" / "march" / "cal_cpp.json"
REL = "../../../Saved/War/cal/"            # from data/war/scenarios to Saved/War/cal


def war_tool():
    """tools/war.py, imported by path (it is a script, not a package)."""
    spec = importlib.util.spec_from_file_location("astra_war_tool", ROOT / "tools" / "war.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ------------------------------------------------------------------------------------------------ the experiments
def wings(carriers: int, fighters: int = 8, bombers: int = 4, drones: int = 0) -> list[dict[str, Any]]:
    out = []
    for c in range(carriers):
        out.append({"carrier": c, "kind": "fighter", "n": fighters, "mission": "cap", "delay": 5 + 3 * c})
        if bombers:
            out.append({"carrier": c, "kind": "bomber", "n": bombers, "mission": "strike", "delay": 30 + 8 * c})
        if drones:
            out.append({"carrier": c, "kind": "drone", "n": drones, "mission": "cap", "delay": 12 + 3 * c})
    return out


def E(a: list[tuple[str, int]], m: list[tuple[str, int]], a_wings: list[dict] | None = None, m_wings: list[dict] | None = None, groups: int = 1,
      seconds: float = 600.0, note: str = "") -> dict[str, Any]:
    return {"astra": a, "mandate": m, "astra_wings": a_wings or [], "mandate_wings": m_wings or [], "groups": groups, "seconds": seconds, "note": note}


EXPERIMENTS: dict[str, dict[str, Any]] = {
    # the destroyers of both sides: how much a ship of a class is worth against another, and the square-law ladder
    "vig3_sty3": E([("vigilant", 3)], [("styx", 3)]),
    "vig4_sty3": E([("vigilant", 4)], [("styx", 3)]),
    "vig5_sty3": E([("vigilant", 5)], [("styx", 3)]),
    "vig6_sty4": E([("vigilant", 6)], [("styx", 4)]),
    "vig4_sty4": E([("vigilant", 4)], [("styx", 4)]),
    "sty6_sty4": E([("styx", 6)], [("styx", 4)]),
    "sty5_sty5": E([("styx", 5)], [("styx", 5)]),
    # frigates and capital ships
    "leth6_sty3": E([("lethe", 6)], [("styx", 3)]),
    "leth8_vig3": E([("lethe", 8)], [("vigilant", 3)]),
    "prae1_ach1": E([("praetorian", 1)], [("acheron", 1)]),
    "prae1_ach2": E([("praetorian", 1)], [("acheron", 2)]),
    "prae2_ach2": E([("praetorian", 2)], [("acheron", 2)]),
    "prae1_sty4": E([("praetorian", 1)], [("styx", 4)]),
    "prae1vig2_ach1sty2": E([("praetorian", 1), ("vigilant", 2)], [("acheron", 1), ("styx", 2)]),
    "prae1vig3_ach1sty3": E([("praetorian", 1), ("vigilant", 3)], [("acheron", 1), ("styx", 3)]),
    "prae1vig4_ach1sty3": E([("praetorian", 1), ("vigilant", 4)], [("acheron", 1), ("styx", 3)]),
    "prae1vig2_ach1sty3": E([("praetorian", 1), ("vigilant", 2)], [("acheron", 1), ("styx", 3)]),
    "prae2vig4_ach2sty4": E([("praetorian", 2), ("vigilant", 4)], [("acheron", 2), ("styx", 4)], groups=2),
    "prae2vig4_ach2sty6": E([("praetorian", 2), ("vigilant", 4)], [("acheron", 2), ("styx", 6)], groups=2),
    # fleet scale
    "prae2vig6_ach3sty5": E([("praetorian", 2), ("vigilant", 6)], [("acheron", 3), ("styx", 5)], groups=2),
    "prae3vig9_ach4sty8": E([("praetorian", 3), ("vigilant", 9)], [("acheron", 4), ("styx", 8)], groups=3),
    "prae3vig9_ach5sty10": E([("praetorian", 3), ("vigilant", 9)], [("acheron", 5), ("styx", 10)], groups=3),
    "prae4vig12_ach5sty11lt4": E([("praetorian", 4), ("vigilant", 12)], [("acheron", 5), ("styx", 11), ("lethe", 4)], groups=4, seconds=900.0),
    # the air: a carrier's wing on its own and in a group
    "ach1w_ach1": E([("acheron", 1)], [("acheron", 1)], a_wings=wings(1), note="a carrier with a wing against the same ship without"),
    "ach1sty2w_ach1sty2": E([("acheron", 1), ("styx", 2)], [("acheron", 1), ("styx", 2)], a_wings=wings(1), note="a carrier group with a wing against none"),
    "ach2sty3w_ach2sty3w": E([("acheron", 2), ("styx", 3)], [("acheron", 2), ("styx", 3)], a_wings=wings(2), m_wings=wings(2), note="both with wings"),
    "prae2vig4w_ach2sty4w": E([("praetorian", 2), ("vigilant", 4)], [("acheron", 2), ("styx", 4)], a_wings=wings(1, 14, 5), m_wings=wings(2), groups=2),
    "prae2vig6w_ach3sty6w": E([("praetorian", 2), ("vigilant", 6)], [("acheron", 3), ("styx", 6)], a_wings=wings(2, 14, 5), m_wings=wings(3, 16, 5, 4), groups=2,
                              seconds=900.0),
}
CORE = ["vig3_sty3", "vig4_sty3", "vig5_sty3", "vig6_sty4", "sty6_sty4", "leth6_sty3", "prae1_ach1", "prae1_ach2", "prae1_sty4", "prae1vig2_ach1sty2",
        "prae1vig3_ach1sty3", "prae2vig4_ach2sty4", "prae2vig4_ach2sty6", "prae2vig6_ach3sty5", "prae3vig9_ach4sty8", "ach1w_ach1", "ach1sty2w_ach1sty2",
        "prae2vig4w_ach2sty4w"]


def groups_of(side: str, ships: list[tuple[str, int]], wings_: list[dict], n_groups: int, sign: int) -> list[dict[str, Any]]:
    """One side's battle groups: the ships split among `n_groups` (the first holds the carriers' wings), in wedges 30 km from the other side."""
    flat = [c for cls, n in ships for c in [cls] * n]
    out: list[dict[str, Any]] = []
    chunk = math.ceil(len(flat) / n_groups)
    for g in range(n_groups):
        part = flat[g * chunk:(g + 1) * chunk]
        if not part:
            continue
        counts: dict[str, int] = {}
        for c in part:
            counts[c] = counts.get(c, 0) + 1
        y = (g - (n_groups - 1) / 2) * 7.0
        spec: dict[str, Any] = {"name": f"{side} group {g + 1}", "formation": "wedge" if g == 0 else "line", "at_km": [sign * (15 + 3.0 * (g % 2)), y, 0],
                                "heading": 0 if sign < 0 else 180, "spacing_km": 1.6, "ships": [{"class": c, "n": n} for c, n in counts.items()]}
        if g == 0 and wings_:
            spec["wings"] = wings_
        out.append(spec)
    return out


def scenario(exp: dict[str, Any], first: str) -> dict[str, Any]:
    d: dict[str, Any] = {"_doc": "a calibration experiment of the March's battle model (tools/march_calibrate.py)",
                         "astra": groups_of("ASTRA", exp["astra"], exp["astra_wings"], exp["groups"], -1),
                         "mandate": groups_of("Mandate", exp["mandate"], exp["mandate_wings"], exp["groups"], +1)}
    if first == "mandate":
        d["first"] = "mandate"
    return d


# ------------------------------------------------------------------------------------------------ reading a record
def outcome(path: Path, war) -> dict[str, Any]:
    """Per side and class: how many were destroyed, left the theatre alive, are alive, with the hulls; and how long the battle lasted."""
    d = war.load(path)
    fin = d["final"]["ships"]
    res: dict[str, Any] = {"t": d["battle_seconds"]}
    for side in ("astra", "mandate"):
        by: dict[str, dict[str, Any]] = {}
        for s in fin:
            if s["side"] != side or s["craft"] or s["c"] == "AQUILA" or s["c"].startswith("EAGLE"):
                continue
            cls = s["name"].split()[0]
            row = by.setdefault(cls, {"n": 0, "destroyed": 0, "gone": 0, "alive": 0, "dark": 0, "hull": []})
            row["n"] += 1
            fate = war.fate_of(s)
            if fate == "alive":
                row["alive"] += 1
                row["hull"].append(float(s.get("hull", 0)))
            elif fate == "gone":
                row["gone"] += 1
                row["hull"].append(float(s.get("hull", 100)))
            elif fate == "disabled":
                row["dark"] += 1
            else:
                row["destroyed"] += 1
        res[side] = by
        c = d.get("stats", {}).get("craft", {}).get(side, {})
        res[side + "_craft"] = {"launched": c.get("launched", 0), "lost": c.get("lost", 0)}
    # the decision: the first time one side has no warship left that is neither dead nor running
    end = d["battle_seconds"]
    for f in d["frames"]:
        cap = {"astra": 0, "mandate": 0}
        for s in f["ships"]:
            if s["side"] in cap and not s["craft"] and s["alive"] and s["c"] != "AQUILA" and not s.get("fleeing"):
                cap[s["side"]] += 1
        if cap["astra"] == 0 or cap["mandate"] == 0:
            end = f["t"]
            break
    res["decided_s"] = end
    return res


def pool(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Mean and standard deviation across battles of what is left of each side (ships that left alive count as left)."""
    out: dict[str, Any] = {"battles": len(rows)}
    for side in ("astra", "mandate"):
        classes = sorted({c for r in rows for c in r[side]})
        table = {}
        for c in classes:
            n = statistics.mean(r[side].get(c, {}).get("n", 0) for r in rows)
            left = [r[side].get(c, {}).get("alive", 0) + r[side].get(c, {}).get("gone", 0) for r in rows]
            hull = [h for r in rows for h in r[side].get(c, {}).get("hull", [])]
            table[c] = {"n": n, "left_mean": statistics.mean(left), "left_sd": statistics.pstdev(left), "dark": statistics.mean(r[side].get(c, {}).get("dark", 0) for r in rows),
                        "hull_mean": statistics.mean(hull) if hull else 0.0}
        out[side] = table
        out[side + "_craft_lost"] = statistics.mean(r[side + "_craft"]["lost"] for r in rows)
    edges = []
    for r in rows:
        a = sum(v["alive"] + v["gone"] for v in r["astra"].values())
        m = sum(v["alive"] + v["gone"] for v in r["mandate"].values())
        edges.append(a - m)
    out["edge_mean"] = statistics.mean(edges)
    out["edge_sd"] = statistics.pstdev(edges)
    out["astra_wins"] = sum(e > 0 for e in edges) / len(edges)
    out["mandate_wins"] = sum(e < 0 for e in edges) / len(edges)
    out["decided_mean"] = statistics.mean(r["decided_s"] for r in rows)
    out["decided_sd"] = statistics.pstdev(r["decided_s"] for r in rows)
    out["edges"] = edges
    return out


# ------------------------------------------------------------------------------------------------ running the commandlet
def cmd_cpp(a: argparse.Namespace) -> None:
    war = war_tool()
    CAL_DIR.mkdir(parents=True, exist_ok=True)
    names = [n for n in (a.only.split(",") if a.only else CORE) if n]
    results = json.loads(RESULTS.read_text()) if RESULTS.exists() else {}
    half = max(1, a.seeds // 2)
    for name in names:
        exp = EXPERIMENTS[name]
        t0 = time.time()
        rows: list[dict[str, Any]] = []
        for order in ("astra", "mandate"):
            tag = f"cal_{name}_{order}"
            (CAL_DIR / f"{tag}.json").write_text(json.dumps(scenario(exp, order), indent=1))
            ns = argparse.Namespace(seconds=a.seconds or exp["seconds"], jump=-1, step=0.1, every=10.0, scenario=REL + tag, at="", views=False, aquila=False,
                                    aquila_opts="", holo_at="", exec="")
            paths = war.seeds_run(ns, tag, "", list(range(1, half + 1)), 2)
            rows += [outcome(p, war) for p in paths if p.exists()]
        results[name] = {**pool(rows), "astra_in": exp["astra"], "mandate_in": exp["mandate"], "wings": [bool(exp["astra_wings"]), bool(exp["mandate_wings"])],
                         "groups": exp["groups"], "seconds": a.seconds or exp["seconds"]}
        edges = results[name]["edges"]
        print(f"{name:26} {len(rows):3} battles in {time.time() - t0:4.0f} s: edge (ASTRA - Mandate left) {statistics.mean(edges):+.2f} ± {statistics.pstdev(edges):.2f};"
              f" ASTRA wins {results[name]['astra_wins']:.2f}, Mandate {results[name]['mandate_wins']:.2f}; decided at {results[name]['decided_mean']:.0f} s", flush=True)
        RESULTS.parent.mkdir(parents=True, exist_ok=True)
        RESULTS.write_text(json.dumps(results, indent=1))


# ------------------------------------------------------------------------------------------------ the abstract model on the same experiments
def model_fleet(side: int, ships: list[tuple[str, int]], wings_: list[dict[str, Any]], n_groups: int, params) -> list:
    """One side of an experiment as the model's units, with the craft the experiment's wings give its carriers (the first group's ship indices, as the scenario)."""
    from astra_mind import march_battle as mb
    out = mb.units(side, ships, None, params=params, fid=f"s{side}")
    chunk = math.ceil(len(out) / n_groups)
    first = out[:chunk]
    for w in wings_:
        idx = int(w.get("carrier", 0))
        if idx < len(first) and first[idx].cls in ("acheron", "praetorian", "aquila"):
            u = first[idx]
            kind = w["kind"]
            if kind == "fighter":
                u.f += w["n"]
            elif kind == "bomber":
                u.b += w["n"]
            else:
                u.d += w["n"]
    return out


def run_model(exp: dict[str, Any], runs: int, params, seed: int = 1) -> list[dict[str, Any]]:
    """`runs` battles of the model for an experiment, in the record format `pool` reads."""
    import random
    from astra_mind import march_battle as mb
    rng = random.Random(seed)
    rows = []
    for _ in range(runs):
        a = model_fleet(0, exp["astra"], exp["astra_wings"], exp["groups"], params)
        m = model_fleet(1, exp["mandate"], exp["mandate_wings"], exp["groups"], params)
        e = mb.fight(a, m, rng, params)
        row: dict[str, Any] = {"t": e.t, "decided_s": e.t}
        for side, us in (("astra", a), ("mandate", m)):
            by: dict[str, dict[str, Any]] = {}
            for u in us:
                r = by.setdefault(u.cls, {"n": 0, "destroyed": 0, "gone": 0, "alive": 0, "dark": 0, "hull": []})
                r["n"] += 1
                if not u.alive:
                    r["destroyed"] += 1
                elif u.gone:
                    r["gone"] += 1
                    r["hull"].append(100.0 * u.hull_frac)
                else:
                    r["alive"] += 1
                    r["hull"].append(100.0 * u.hull_frac)
            row[side] = by
            launched = sum(w["n"] for w in exp[side + "_wings"])
            row[side + "_craft"] = {"launched": launched, "lost": launched - sum(u.f + u.b + u.d for u in us if u.alive)}
        rows.append(row)
    return rows


def compare_line(name: str, cpp: dict[str, Any], mod: dict[str, Any]) -> str:
    def side(p: dict[str, Any], s: str) -> str:
        return ", ".join(f"{c[:4]} {x['left_mean']:.1f}" for c, x in p[s].items())
    return (f"{name:26} edge C++ {cpp['edge_mean']:+5.2f}±{cpp['edge_sd']:.2f} model {mod['edge_mean']:+5.2f}±{mod['edge_sd']:.2f} | "
            f"A wins C++ {cpp['astra_wins']:.2f} model {mod['astra_wins']:.2f}, M wins {cpp['mandate_wins']:.2f}/{mod['mandate_wins']:.2f} | "
            f"decided {cpp['decided_mean']:4.0f}/{mod['decided_mean']:4.0f} | A[{side(cpp, 'astra')} / {side(mod, 'astra')}] M[{side(cpp, 'mandate')} / {side(mod, 'mandate')}]")


def loss_of(cpp: dict[str, Any], mod: dict[str, Any]) -> float:
    """How far the model is from the bench on one experiment: ships left per class, the edge, who wins, how long it takes, the craft."""
    err = 0.0
    for s in ("astra", "mandate"):
        for c, x in cpp[s].items():
            m = mod[s].get(c, {"left_mean": 0.0})
            err += ((x["left_mean"] - m["left_mean"]) / max(1.0, x["n"]) ** 0.5) ** 2 * 1.0
    err += ((cpp["edge_mean"] - mod["edge_mean"]) / 1.2) ** 2
    err += ((cpp["astra_wins"] - mod["astra_wins"]) * 1.6) ** 2 + ((cpp["mandate_wins"] - mod["mandate_wins"]) * 1.6) ** 2
    err += ((cpp["decided_mean"] - mod["decided_mean"]) / 140.0) ** 2 * 0.6
    err += ((cpp["edge_sd"] - mod["edge_sd"]) / 1.5) ** 2 * 0.4
    for s in ("astra", "mandate"):
        if cpp[s + "_craft_lost"] or mod[s + "_craft_lost"]:
            err += ((cpp[s + "_craft_lost"] - mod[s + "_craft_lost"]) / 8.0) ** 2 * 0.4
    return err


def cmd_model(a: argparse.Namespace) -> None:
    sys.path.insert(0, str(ROOT / "mind"))
    from astra_mind import march_battle as mb
    params = mb.Params.load()
    cpp = json.loads(RESULTS.read_text())
    names = [n for n in (a.only.split(",") if a.only else list(cpp)) if n in cpp]
    total = 0.0
    for name in names:
        mod = pool(run_model(EXPERIMENTS[name], a.runs, params))
        total += loss_of(cpp[name], mod)
        print(compare_line(name, cpp[name], mod))
    print(f"loss {total:.3f} over {len(names)} experiments")


def cmd_fit(a: argparse.Namespace) -> None:
    """A random coordinate search of the model's constants: each round tries a change of one constant (or two) and keeps it if the loss over all the
    experiments goes down (the same random draws every time, so that a change is judged on the model and not on luck)."""
    sys.path.insert(0, str(ROOT / "mind"))
    import random
    from dataclasses import replace
    from astra_mind import march_battle as mb
    cpp = json.loads(RESULTS.read_text())
    names = [n for n in cpp if n in EXPERIMENTS]
    free = [n for n in a.free.split(",") if n]
    params = mb.Params.load()

    def total(p) -> float:
        return sum(loss_of(cpp[n], pool(run_model(EXPERIMENTS[n], a.runs, p, seed=7))) for n in names)

    best = total(params)
    print(f"start loss {best:.3f}", flush=True)
    rng = random.Random(a.seed)
    for it in range(a.iters):
        step = a.step * (1.0 - 0.75 * it / max(1, a.iters))                     # (the search narrows as it goes)
        picks = rng.sample(free, 2 if rng.random() < 0.3 else 1)
        change = {n: getattr(params, n) * math.exp(rng.gauss(0.0, step)) for n in picks}
        trial = replace(params, **change)
        loss = total(trial)
        if loss < best:
            best, params = loss, trial
            print(f"  it {it:4}  " + "  ".join(f"{n} {getattr(params, n):.4f}" for n in picks) + f"   loss {best:.3f}", flush=True)
    out = {"params": {f: getattr(params, f) for f in free}, "loss": best, "experiments": names, "runs": a.runs}
    existing = json.loads(mb.CAL_FILE.read_text()) if mb.CAL_FILE.exists() else {"params": {}}
    existing["params"].update(out["params"])
    existing.update({"loss": best, "experiments": names, "fitted_with": "tools/march_calibrate.py fit"})
    mb.CAL_FILE.write_text(json.dumps(existing, indent=1))
    print(f"final loss {best:.3f}; written to {mb.CAL_FILE}")


def cmd_list(_: argparse.Namespace) -> None:
    for name, e in EXPERIMENTS.items():
        print(f"{'*' if name in CORE else ' '} {name:26} ASTRA {e['astra']} {'+wings' if e['astra_wings'] else ''}  vs  Mandate {e['mandate']} {'+wings' if e['mandate_wings'] else ''}  ({e['groups']} groups)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("cpp")
    p.add_argument("--only", default="")
    p.add_argument("--seeds", type=int, default=24)
    p.add_argument("--seconds", type=float, default=0.0)
    p.set_defaults(fn=cmd_cpp)
    p = sub.add_parser("model")
    p.add_argument("--only", default="")
    p.add_argument("--runs", type=int, default=200)
    p.set_defaults(fn=cmd_model)
    p = sub.add_parser("fit")
    p.add_argument("--iters", type=int, default=300)
    p.add_argument("--runs", type=int, default=60)
    p.add_argument("--step", type=float, default=0.18)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--free", default="k_rail,k_laser,hull_w,shield_w,shield_leak,msl_frac,msl_dmg,pd_per_channel,ow,approach0,approach_per_ship,sigma_battle,sigma_step,"
                                     "ret_bold,ret_steady,ret_cautious,flee_base_s,flee_turn,flee_exposure,ramp_s,f_dps,b_dps,air_kill,air_pd,"
                                     "p_praetorian,p_vigilant,p_acheron,p_lethe,h_praetorian,h_vigilant,h_acheron,h_lethe")
    p.set_defaults(fn=cmd_fit)
    p = sub.add_parser("list")
    p.set_defaults(fn=cmd_list)
    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
