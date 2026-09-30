"""Prints the station branches of UAstraShipSubsystem::VisitRouteFor (Source/ASTRA/AstraShipSubsystem.cpp) for the bridge v3
layout, from data/ship/aquila_bridge.json (routes.to_starboard_door): paste the output over the `if (S == "helm" || S == "ops")
... else if (S == "comms" || S == "sensors") { ... }` chain and keep the final `else` (officers from another deck) and the
common tail (P(-9.2f, 3.9f) ...). The first waypoint of a route is the station itself (C->GetActorLocation()), so it is left
out; heights in cm follow the levels of the data file (well -60, upper 0, dais +20).

  python3 tools/ue_scripts/bridge3_routes_cpp.py
"""
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = json.load(open(os.path.join(ROOT, "data", "ship", "aquila_bridge.json"), encoding="utf-8"))
Z_CM = {k: round(v * 100) for k, v in D["levels"].items()}
ORDER = ["helm", "ops", "engineering", "flight", "tactical", "xo", "comms", "sensors"]


def f(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return (s if "." in s else s + ".0") + "f"


def branch(sid: str, first: bool) -> str:
    pts = D["routes"]["to_starboard_door"][sid][1:]
    out = [f'\t{"if" if first else "else if"} (S == TEXT("{sid}"))', "\t{", "\t\tR.Add(C->GetActorLocation());"]
    for x, y, lv in pts:
        z = Z_CM[lv]
        out.append(f"\t\tP({f(x)}, {f(y)}" + (f", {f(float(z))}" if z else "") + ");")
    out.append("\t}")
    return "\n".join(out)


print("\t// bridge v3 (data/ship/aquila_bridge.json routes.to_starboard_door): the helm goes round the holo table and up the port stairs")
print("\n".join(branch(s, i == 0) for i, s in enumerate(ORDER)))
