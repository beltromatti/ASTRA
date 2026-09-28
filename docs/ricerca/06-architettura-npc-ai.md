# Research 06 — LLM-driven NPCs, multi-agent sim, AI storyteller (2026-09-27)

Raw research report produced during the initial research phase. Numbers marked *est.* are estimates; UNVERIFIED items could not be confirmed.

## 1. State of the art 2024–2026 — key facts
- **PUBG Ally (Krafton + NVIDIA ACE, 2026 public tests):** on-device Mistral-NeMo-Minitron-2B + ASR + TTS within leftover VRAM of 8 GB GPUs. Cloud rejected: "too slow for live squad communication". Behavior tree = "System 1" at tick rate; SLM = "System 2"; game actions never wait on the LLM. Tools are "the only ground truth"; stable prompt prefix for KV-cache reuse; teacher→student distillation; narrow scope; automated tool-use evals + A/B + 1,000+ playtesters.
- **inZOI Smart Zoi (2025):** 0.5B on-device; end-of-day reflection rewrites schedules. NVIDIA Audio2Face open-sourced (with UE5 plugin).
- **Ubisoft NEO NPC → Teammates (Nov 2025):** Snowdrop + Gemini + middleware; "behavior trees, and then we add a layer with our LLM to take decisions"; cut the LLM wherever a controller does better.
- **Epic:** AI Darth Vader (May 2025) = Gemini 2.0 Flash + ElevenLabs Flash v2.5; profanity jailbreak hotfixed in 30 min. **UEFN Conversations** (ex-Persona device; experimental since 16 Apr 2026) = Gemini 3.1 Flash-Lite + ElevenLabs; creator prompt + facts; gameplay hooks via Structured Output (numbers/bools/enums) consumed by Verse; session memory; bans medical/romantic personas.
- **Where Winds Meet (NetEase, Nov 2025):** the LLM both narrates and judges quest completion → exploits ("Solid Snake method", bracketed fictional actions), NSFW RP. Damage limited only because rewards were minor.
- **Sony leaked Aloy prototype (2025):** Whisper + Llama 3 + GPT-4 — judged flat.
- **Middleware:** Inworld pivoted to *Runtime* (Oct 2025, C++ graph orchestration, provider-agnostic; claims ~200 ms and >95% cost cut — UNVERIFIED). Convai: Prompt-to-Action, Narrative Graph, Mindview debugger.
- **Indies/mods:** Suck Up! (token-metered), 1001 Nights (language as mechanic), Vaudeville (48% positive: slow, grating), Dead Meat (moved on-device), Whispers from the Star (Very Positive; ~1.5 s lag; launch traffic 10–50×). Skyrim mods: Mantella (per-NPC summaries), SkyrimNet (importance-decayed memories, fast model for actions + smart model for dialogue, TTS starts on first sentence).
- July 2026 survey of 53 AI-native games: core problem = "organizing semantic openness into stable gameplay".

**Lessons:** LLM never the source of truth / judge; two-speed AI; structured output + tools are the gameplay bridge; latency is a design problem; narrow well-described facts/actions beat prompt warnings; players attack free-text channels immediately; test with many real players early.

## 2. Multi-agent research
- Generative Agents (Stanford): memory stream (recency/importance/relevance), reflection, planning; 25 agents × 2 days cost thousands of $ → constant polling doesn't scale.
- Lyfe Agents (option-action, summarize-and-forget: 10–100× cheaper); Affordable Generative Agents (learned policies replace repeated calls).
- Project Sid / PIANO (Altera, 1000+ agents): parallel modules at different speeds; bottlenecked Cognitive Controller → speech follows decisions (fixes say/do mismatch); action-awareness module checks expected vs observed.
- AI Town: single-threaded engine step; LLM calls in background; results arrive as inputs next tick (non-blocking).
- Hierarchies: HLA (slow LLM + fast small model + reactive executor, ~50% better in Overcooked), DeepMind Talker–Reasoner, HIMA (StarCraft II), Meta CICERO (dialogue from planned intents). MINDcraft: up to 15% drop when agents must explain plans in prose → keep inter-agent messages structured.
- Game Master pattern: DeepMind Concordia (GM grounds intents into outcomes), Snow Globe (LLM adjudicators for wargames).
- Warning: Rivera et al. FAccT'24 — all 5 LLMs escalated unpredictably in wargames (arms races, rare nuclear use) → admirals need doctrine + sim-enforced escalation limits; Director may exploit it for climaxes.

## 3. Storytellers & war coherence
- RimWorld (GDC 2017): "not a game – a story generator"; "unexpected, disproportional pushback"; mechanics must include loss and recovery; apophenia. Cassandra: 4.6 days on / 6 off, ≥1.9 days between major threats, threat points scale with wealth/colonists + adaptation.
- Left 4 Dead AI Director (Booth 2009): intensity → Build Up → Sustain Peak (3–5 s) → Peak Fade → Relax (30–45 s); "adjusts pacing, not difficulty"; crude but works.
- LLM narrators: Hidden Door (commit world state before prose; decide consequences first; meaningful failure). AI Dungeon Story Cards. NCP-Bench (Aug 2026): best model kept narrative commitments only 42% after 20 turns; fact conflicts 40–68%. Orchestrated Reality: canonical JSON entity tree + Plan–Diff–Validate–Apply. EpisodeSim "World Master" tracks obligations.
- Implication: war lives in the sim + a structured append-only **war ledger**; LLM selects/dramatizes beats inside a numeric pacing envelope; endings computed from real state.

## 4. Engineering patterns
- Affordances not guardrails: typed strict-schema tools mirroring real ship controls (`set_power`, `fire`, `dispatch_dc`...); sim rejects with reasons ("capacitor 12%") so officers answer in character; chain of command = sim fact.
- Role-filtered, salience-ranked, delta world snapshots (0.5–1.5k tokens est.), stable key order, rounded numbers; observation tools for detail.
- Prompt caching: tools → world bible → persona → [cache breakpoint] → ledger/memories → volatile snapshot/event. No timestamps in the prefix. Pre-warm caches at battle start.
- Memory: episodic log w/ importance & decay; semantic beliefs via batched reflection; relationships; promises in the ledger; lazy retrieval only for the NPC being addressed.
- Persona sheets (identity, rank, competence, values, fears, speech style + 3 sample lines, relationships, secrets) drafted offline by a stronger model.
- Latency hiding: streaming ASR → instant pre-generated ack ("Aye, Captain"); fast path for ~50 common orders; officers speak after tool results; sentence-streamed TTS; pre-generated chatter keyed to state hashes.
- AI gateway with priority lanes: P0 player-addressed, P1 combat command, P2 proactive reports, P3 crew/Director (batchable); deadlines; debounce/merge; cancel stale (generation counter); per-session token budget.
- Graceful degradation: every LLM role has StateTree/utility fallback + canned lines; ship must fight with the API down.
- Replay: deterministic sim; log LLM req/resp with tick, seed, state hash; replay by substitution.
- Evaluation: headless simulated battles; metrics: order compliance, invalid-tool rate, time-to-act, speech–action contradictions, pacing vs target curve, ending reached, cost/hour; LLM judges for character consistency; gate prompt/model changes on results.
- Multiplayer: server-side AI; player speech as quoted data; authority checks in tools; never grant progress on model judgment alone; moderation; rate limits; red-teaming (OWASP LLM01).

## 5. Recommended architecture (from the report)
```
Player voice ─► streaming ASR ─► router ─► instant ack bark (pre-generated)
┌──────────────────────── AI GATEWAY (server-side) ─────────────────────────┐
│ priority lanes · deadlines · budgets · prompt cache · model routing ·     │
│ fallbacks · replay log (request/response + tick + state hash)             │
└──────▲────────────▲─────────────▲──────────────▲───────────────▲──────────┘
  WAR DIRECTOR    ADMIRALS     CAPTAINS       BRIDGE OFFICERS    CREW ×100s
  pacing rules +  strategic    operational    tools on order/    talk + batched
  LLM showrunner  (minutes)    (≥20 s)        event              reflection
      │beats        │orders      │orders         │tool calls        │intents
┌─────▼────────────▼────────────▼───────────────▼──────────────────▼────────┐
│ AFFORDANCE/VALIDATION: typed tools · authority · budgets · reject reasons │
└─────────────────────────────────┬─────────────────────────────────────────┘
┌─────────────────────────────────▼─────────────────────────────────────────┐
│ DETERMINISTIC SIM (UE5, authoritative): power, shields, weapons, damage,  │
│ hangar, fleets, war map · FAST LAYER: Mass + StateTree + Smart Objects    │
└─────── event bus (debounced, salience-scored) ─► memory + war ledger ─────┘
```

| Agent | Trigger | Model tier | Latency target | Calls/h (est.) |
|---|---|---|---|---|
| Bridge officers (8) | order addressed; debounced critical event | fast mid-tier cloud or local 4–8B | ack <0.3 s, action <1.5 s | 200–350 |
| Crew (100s) | player talks to them; dept reflection ~5 min | small | <1.5 s | 80–120 |
| Captains (~6) | significant state change, ≥20 s apart | mid-tier | ≤3 s | 150–300 |
| Admirals (2–3) | phase change, heavy losses, every 3–5 min | strong | ≤10 s async | 30–50 |
| War Director | pacing thresholds, act gates, post-battle | strongest | async | 6–12 (+1–3 heavy) |

≈500–800 calls per battle hour (single player). Director loop: sim computes tension / war score / threat points / act / open threads / reachable endings → rules set envelope (threat budget, cooldowns, relax windows, mandatory beats, rising ending pressure) → LLM showrunner picks typed beats that must advance a named thread → validator applies or rejects (1 retry, then procedural) → append-only ledger → acts Outbreak → Escalation → Climax → Resolution with min/max durations and a war clock; epilogue written from what actually happened.

Stronger model belongs offline as a "prompt compiler" (role prompts, persona sheets, doctrine), refined against the headless battle eval, then frozen/versioned.

## 6. Top 10 pitfalls
1. LLM as source of truth/judge. 2. Speech–action mismatch (act first, then speak from result). 3. Unhidden latency. 4. Polling every agent every tick. 5. Free text carrying authority. 6. Lossy summaries without a commitments ledger. 7. Director writing prose instead of changing state (no stakes). 8. Homogeneous escalation / over-repeated traits. 9. Silent cost regressions (cache-busting timestamps, 10–50× launch spikes). 10. No evaluation harness.

## Sources
See the agent report (kept in session transcript); key: NVIDIA PUBG Ally blog, Audio2Face-3D SDK, Ubisoft Teammates (gamedeveloper.com, variety.com), Fortnite Vader incidents, UEFN Conversations (wccftech), Where Winds Meet analyses, Inworld Runtime blog, Convai docs, arXiv 2304.03442, 2310.02172, 2402.02053, 2411.00114, AI Town ARCHITECTURE.md, arXiv 2504.17950, 2312.15224, 2410.08328, 2508.06042, Meta CICERO, DeepMind Concordia, arXiv 2507.08892, 2404.11446, 2401.03408, TinyTroupe, RimWorld GDC 2017 slides, L4D AI Director (Booth 2009), Hidden Door design review (Ian Bicking), NCP-Bench arXiv 2608.08160, arXiv 2606.16014, 2609.01167, OWASP LLM01, Anthropic prompt-caching & pricing docs, ElevenLabs models docs.
