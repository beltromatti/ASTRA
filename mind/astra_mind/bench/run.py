"""Esegue il benchmark dei modelli (latenza dall'Italia, correttezza dei comandi,
fedeltà alla lingua, costo) e scrive il report in docs/bench/.

Uso:  cd mind && uv run astra-bench [--configs nome1,nome2] [--limit N]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from lingua import Language, LanguageDetectorBuilder

from ..env import REPO_ROOT
from ..openrouter import Completion, OpenRouter, credits
from .scenarios import ACTION_TOOLS, CASES, TOOLS, Case, system_message


@dataclass
class Config:
    name: str
    model: str
    providers: list[str] | None
    reasoning: dict[str, Any] | None
    temperature: float | None = 0.3


CONFIGS: list[Config] = [
    Config("deepseek-v4.1-flash@together", "deepseek/deepseek-v4.1-flash", ["together"], {"enabled": False}),
    Config("deepseek-v4.1-flash@modal", "deepseek/deepseek-v4.1-flash", ["modal"], {"enabled": False}),
    Config("deepseek-v4.1-flash@deepseek", "deepseek/deepseek-v4.1-flash", ["deepseek"], {"enabled": False}),
    Config("gpt-oss-120b@groq", "openai/gpt-oss-120b", ["groq"], {"effort": "low"}),
    Config("gpt-oss-120b@cerebras", "openai/gpt-oss-120b", ["cerebras"], {"effort": "low"}),
    Config("glm-5.3-flash@together", "z-ai/glm-5.3-flash", ["together"], {"enabled": False}),
    Config("minimax-m3@parasail", "minimax/minimax-m3", ["parasail"], {"enabled": False}),
    Config("gpt-6-luna@openai", "openai/gpt-6-luna", ["openai"], {"effort": "none"}, None),
    Config("ling-3.0-flash@novita", "inclusionai/ling-3.0-flash", ["novita"], None),
]

_LANGS = {"it": Language.ITALIAN, "en": Language.ENGLISH, "es": Language.SPANISH, "de": Language.GERMAN}
_DETECTOR = LanguageDetectorBuilder.from_languages(*_LANGS.values()).build()


def _match(value: Any, spec: Any) -> bool:
    if isinstance(spec, tuple):
        try:
            return abs(float(value) - spec[0]) <= spec[1]
        except (TypeError, ValueError):
            return False
    if isinstance(spec, set):
        return str(value).lower() in {s.lower() for s in spec}
    return str(value).strip().lower() == str(spec).strip().lower()


def _call_matches(call_name: str, args: dict[str, Any], name: str, spec: dict[str, Any]) -> bool:
    return call_name == name and all(k in args and _match(args[k], v) for k, v in spec.items())


def score(case: Case, comps: list[Completion]) -> dict[str, Any]:
    """Valuta la risposta del ciclo agente (1 o 2 passi: azioni, poi eventuale frase)."""
    calls = [(c.name, c.arguments()) for comp in comps for c in comp.tool_calls]
    valid_json = all(a is not None for _, a in calls) and all(n in ACTION_TOOLS | {"speak"} for n, _ in calls)
    calls_ok = [(n, a or {}) for n, a in calls]
    actions = [(n, a) for n, a in calls_ok if n in ACTION_TOOLS]
    speaks = [a for n, a in calls_ok if n == "speak"]

    expected_ok = all(any(_call_matches(n, a, en, es) for n, a in actions) for en, es in case.expect)
    forbidden_hit = any(any(_call_matches(n, a, fn, fs) for n, a in actions) for fn, fs in case.forbid)
    if case.speak_only:
        action_ok = not actions
    elif case.ambiguous:
        action_ok = expected_ok or not actions  # agire bene oppure chiedere chiarimenti
    elif case.forbid and not case.expect:
        action_ok = not forbidden_hit
    else:
        action_ok = expected_ok and not forbidden_hit

    # la frase detta: lo strumento `speak` oppure, in mancanza, il testo libero della risposta
    content = " ".join(c.content.strip() for c in comps if c.content.strip())
    text = speaks[-1].get("text", "") if speaks else content
    lang_tag = str(speaks[-1].get("lang", "")).lower()[:2] if speaks else case.lang
    detected = _DETECTOR.detect_language_of(text) if text else None
    lang_ok = bool(text) and detected == _LANGS[case.lang] and lang_tag == case.lang
    speak_ok = bool(text) and len(text.split()) <= 40
    return {
        "valid_json": valid_json, "action_ok": action_ok, "lang_ok": lang_ok, "speak_ok": speak_ok,
        "pass": valid_json and action_ok and lang_ok and speak_ok, "steps": len(comps),
        "calls": [{"name": n, "args": a} for n, a in calls], "text": text,
    }


async def run_config(client: OpenRouter, cfg: Config, cases: list[Case]) -> dict[str, Any]:
    sysmsg = system_message()
    # riscaldamento: apre la connessione e scalda la cache del prompt (escluso dalle misure)
    await client.chat(model=cfg.model, messages=[sysmsg, {"role": "user", "content": "Ready?"}], tools=TOOLS,
                      providers=cfg.providers, reasoning=cfg.reasoning, max_tokens=200,
                      temperature=cfg.temperature)
    results = []
    for case in cases:
        user = {"role": "user", "content": case.text}
        comp = await client.chat(model=cfg.model, messages=[sysmsg, user], tools=TOOLS, providers=cfg.providers,
                                 reasoning=cfg.reasoning, max_tokens=500, temperature=cfg.temperature)
        comps = [comp]
        t_speech = comp.t_end
        needs_followup = (not comp.error and comp.tool_calls
                          and not any(c.name == "speak" for c in comp.tool_calls) and not comp.content.strip())
        if needs_followup:
            # secondo passo: la simulazione esegue le azioni e l'ufficiale riferisce
            assistant = {"role": "assistant", "content": None, "tool_calls": [
                {"id": f"call_{i}", "type": "function",
                 "function": {"name": c.name, "arguments": c.arguments_raw or "{}"}}
                for i, c in enumerate(comp.tool_calls)]}
            results_msgs = [{"role": "tool", "tool_call_id": f"call_{i}", "content": json.dumps({"ok": True})}
                            for i, _ in enumerate(comp.tool_calls)]
            follow = await client.chat(model=cfg.model, messages=[sysmsg, user, assistant, *results_msgs],
                                       tools=TOOLS, providers=cfg.providers, reasoning=cfg.reasoning,
                                       max_tokens=300, temperature=cfg.temperature)
            comps.append(follow)
            t_speech = (comp.t_end or 0) + (follow.t_end or 0)
        err = next((c.error for c in comps if c.error), "")
        sc = score(case, comps) if not err else {"pass": False, "error": err}
        results.append({"case": case.cid, "lang": case.lang, "order": case.text, **sc,
                        "provider": comp.provider, "t_first_token": comp.t_first_token,
                        "t_first_tool": comp.t_first_tool_name, "t_end": comp.t_end, "t_speech": t_speech,
                        "prompt_tokens": sum(c.prompt_tokens for c in comps),
                        "cached_tokens": sum(c.cached_tokens for c in comps),
                        "completion_tokens": sum(c.completion_tokens for c in comps),
                        "reasoning_tokens": sum(c.reasoning_tokens for c in comps),
                        "cost": sum(c.cost for c in comps), "error": err})
    ok = [r for r in results if not r.get("error")]

    def pct(key: str) -> float:
        return 100.0 * sum(1 for r in ok if r.get(key)) / max(1, len(results))

    def q(values: list[float], p: float) -> float | None:
        values = sorted(v for v in values if v is not None)
        if not values:
            return None
        return values[min(len(values) - 1, int(round(p * (len(values) - 1))))]

    firsts = [r["t_first_tool"] or r["t_first_token"] for r in ok]
    ends = [r["t_speech"] for r in ok]
    return {
        "config": asdict(cfg), "n": len(results), "errors": len(results) - len(ok),
        "pass_pct": pct("pass"), "action_pct": pct("action_ok"), "lang_pct": pct("lang_ok"),
        "json_pct": pct("valid_json"), "speak_pct": pct("speak_ok"),
        "first_p50": q(firsts, 0.5), "first_p90": q(firsts, 0.9),
        "end_p50": q(ends, 0.5), "end_p90": q(ends, 0.9),
        "cost_total": sum(r["cost"] for r in results), "cost_per_call": statistics.mean([r["cost"] for r in results]) if results else 0,
        "cached_share": (sum(r["cached_tokens"] for r in ok) / max(1, sum(r["prompt_tokens"] for r in ok))),
        "results": results,
    }


def _fmt(v: float | None, unit: str = "s") -> str:
    return "—" if v is None else f"{v:.2f} {unit}"


def write_report(summaries: list[dict[str, Any]], spent: float) -> str:
    out_dir = REPO_ROOT / "docs" / "bench"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M")
    (out_dir / f"llm_{stamp}.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=1), encoding="utf-8")
    lines = [f"# Benchmark modelli — {datetime.now():%Y-%m-%d %H:%M} (dall'Italia, via OpenRouter)", "",
             f"40 ordini di plancia (IT 20, EN 10, ES 5, DE 5). Spesa totale del benchmark: **{spent:.3f} $**.", "",
             "| Configurazione | Superati | Azioni corrette | Lingua giusta | Primo comando p50 / p90 | Frase detta p50 / p90 | Cache | $/chiamata | Errori |",
             "|---|---|---|---|---|---|---|---|---|"]
    for s in sorted(summaries, key=lambda x: (-x["pass_pct"], x["first_p50"] or 99)):
        lines.append(f"| {s['config']['name']} | **{s['pass_pct']:.0f}%** | {s['action_pct']:.0f}% | {s['lang_pct']:.0f}% | "
                     f"{_fmt(s['first_p50'])} / {_fmt(s['first_p90'])} | {_fmt(s['end_p50'])} / {_fmt(s['end_p90'])} | "
                     f"{100*s['cached_share']:.0f}% | {s['cost_per_call']*1000:.3f} m$ | {s['errors']} |")
    lines += ["", "## Casi falliti (per configurazione)", ""]
    for s in summaries:
        fails = [r for r in s["results"] if not r.get("pass")]
        lines.append(f"### {s['config']['name']} — {len(fails)} falliti")
        for r in fails[:12]:
            why = r.get("error") or ", ".join(k for k in ("valid_json", "action_ok", "lang_ok", "speak_ok") if not r.get(k))
            calls = "; ".join(f"{c['name']}({json.dumps(c['args'], ensure_ascii=False)[:90]})" for c in r.get("calls", []) if c["name"] != "speak")
            lines.append(f"- `{r['case']}` «{r['order']}» → {why} · azioni: {calls or 'nessuna'} · detto: «{(r.get('text') or '')[:100]}»")
        lines.append("")
    path = out_dir / f"llm_{stamp}.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path)


async def amain(names: list[str] | None, limit: int | None) -> None:
    before = await credits()
    cases = CASES[:limit] if limit else CASES
    configs = [c for c in CONFIGS if not names or c.name in names]
    client = OpenRouter()
    summaries = []
    try:
        for cfg in configs:
            t0 = time.perf_counter()
            s = await run_config(client, cfg, cases)
            summaries.append(s)
            print(f"{cfg.name:32s} superati {s['pass_pct']:5.1f}% | primo comando p50 {_fmt(s['first_p50'])} "
                  f"| completa p50 {_fmt(s['end_p50'])} | errori {s['errors']} | {time.perf_counter()-t0:5.1f}s", flush=True)
    finally:
        await client.close()
    after = await credits()
    spent = after["used"] - before["used"]
    print("Report:", write_report(summaries, spent), f"| spesa {spent:.4f} $ | credito residuo {after['total']-after['used']:.2f} $")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--configs", default="")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    asyncio.run(amain([c for c in args.configs.split(",") if c] or None, args.limit or None))


if __name__ == "__main__":
    main()
