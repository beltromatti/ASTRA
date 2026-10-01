"""Read an arena record (Saved/War/<tag>_<seed>.mind.json): what each mind was asked, what it thought and ordered, how the orders came out.

    cd mind && .venv/bin/python -m bench.war_show live3 1 [--prompts] [--only mandate/admiral]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

WAR = Path(__file__).resolve().parents[2] / "Saved" / "War"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tag")
    ap.add_argument("seed", type=int, nargs="?", default=1)
    ap.add_argument("--prompts", action="store_true", help="print the system and user prompt of the first pulse of each seat")
    ap.add_argument("--only", default="", help="only the seats containing this text")
    ap.add_argument("--content", action="store_true", help="the model's own words around its tool calls")
    a = ap.parse_args()
    d = json.loads((WAR / f"{a.tag}_{a.seed}.mind.json").read_text())
    print(json.dumps({k: v for k, v in d["result"].items() if k not in ("minds",)}, separators=(",", ":"))[:700])
    m = d["result"]["minds"]
    print(f"minds: {m['pulses']} pulses, ${m['cost']:.4f} (${m['cost_per_hour']:.2f}/h of battle), latency median {m['latency_median']:.1f} s p90 {m['latency_p90']:.1f} s, "
          f"first call {m['first_call_median']:.1f} s, orders ok/failed {m['orders_ok']}/{m['orders_failed']}, lines {m['lines']}, tokens {m['tokens_in']}/{m['tokens_out']}")
    seen: set[str] = set()
    for p in d["pulses"]:
        if a.only and a.only not in p["seat"]:
            continue
        print(f"\n[{p['t']:6.1f}] {p['seat']} · {p['who']} · {'; '.join(p['why'])[:90]}\n         {' | '.join(p['tools']) or '(no tool call)'}  "
              f"first {p['first_call']} s, total {p['latency']} s, {p['tokens_in']}/{p['tokens_out']} tokens, ${p['cost']:.5f}" + (f"  ERROR {p['error']}" if p["error"] else ""))
        if a.content and p.get("content"):
            print("         > " + p["content"].replace("\n", "\n         > "))
        if a.prompts and p["seat"] not in seen:
            seen.add(p["seat"])
            print("----- SYSTEM -----\n" + p.get("system", "") + "\n----- USER -----\n" + p.get("user", "") + "\n------------------")
    print("\nORDERS")
    for o in d["orders"]:
        args = {k: v for k, v in o["args"].items() if k not in ("side", "by")}
        print(f"  [{o['t']:6.1f}] {o['name']} {json.dumps(args, ensure_ascii=False)} -> {'ok' if o.get('ok') else 'FAILED'}: {(o.get('detail') or '')[:170]}")
    if d.get("lines"):
        print("\nLINES (allied captains' words)")
        for l in d["lines"]:
            print(f"  [{l['t']:6.1f}] {l['speaker']} ({l['tone']}{', answer' if l.get('answer') else ''}{', URGENT' if l.get('urgent') else ''}): {l['text']}")


if __name__ == "__main__":
    main()
