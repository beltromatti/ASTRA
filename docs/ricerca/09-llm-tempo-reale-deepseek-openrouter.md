# Research 09 — Real-time LLM routing with DeepSeek API + OpenRouter (2026-09-27)

Supersedes the model choices of report 02 for the "DeepSeek key + OpenRouter key, no privacy constraints" setup.

## Headlines
- **DeepSeek V4.1 Flash is effectively the only DeepSeek model**: API id `deepseek-flash`; V4-Pro retired (since 2026-09-14 04:00 UTC routed to V4.1 Flash at Flash prices).
- Best open model without thinking on AA Intelligence Index (II 25); AutomationBench-AA ~69% at max thinking; half price off-peak; cached input ≈ free.
- **No hosted model feels instant** (≥ ~0.4 s TTFT before network from Italy) → the "instant" feel must come from a **local multilingual embedding intent classifier** + pre-recorded acknowledgements.

## 1. DeepSeek API
| Item | Finding |
|---|---|
| Model IDs | `deepseek-flash` = V4.1-Flash (released 2026-09-10): 552B total, 16B active generating / 8B reading input (encoder-decoder), MIT, 1M context, 384K max output, image input. Old names `deepseek-v4-flash`, `-vision-exp` map to V4.1. No separate reasoner: thinking is a setting. |
| Price /1M (peak / off-peak) | cached input $0.006 / $0.003 · uncached input $0.30 / $0.15 · output $1.20 / $0.60 |
| Off-peak | 50% off outside 01–04 & 06–10 UTC Mon–Fri (CEST 03–06 & 08–12), excl. Chinese holidays → Italian evenings/weekends half price. OpenRouter's DeepSeek listing passes through time-of-day prices. |
| Thinking | on by default ("high"); disable per request `thinking:{type:"disabled"}` or `reasoning_effort` low/high/max. In thinking mode temperature/penalties ignored. With tools, reasoning text must be sent back on later turns. |
| Tools | supported; strict mode on `/beta` base URL (`strict:true`, all props required, `additionalProperties:false`); `json_object` mode (prompt must contain "json"; can return empty content); no JSON-schema output mode documented; OpenAI/Anthropic/Responses formats. Parallel tool calls & streamed tool-call fragments not explicitly documented (UNVERIFIED). |
| Caching | automatic, disk-based, exact prefix match; segments end at end of user input, end of model output, and fixed intervals; cleared after hours–days; `prompt_cache_hit_tokens/miss_tokens` reported; no documented minimum. **A `user_id` isolates the cache → use one constant ID for the whole game.** |
| Limits | 2,500 concurrent requests/account (Flash) → then 429. Under load it keeps the connection open with keep-alive lines and only drops after 10 min without inference → **own ~2 s timeout + hedging**. |
| Speed (AA, 10K prompts, US) | direct API ~232 tok/s, TTFT ~1.11 s (thinking) / 227 tok/s, 1.13 s (no thinking). No EU measurements (expect ~1.1–1.5 s from Italy, UNVERIFIED). |
| Reliability | 99.66% uptime Jun–Sep; ~1 h outage on 2026-09-14 with status page green. |

## 2. OpenRouter candidates ($/1M in / out / cached)
| Model (II; active) | Provider | tok/s | TTFT | Price | Tools/strict | Abort stops billing |
|---|---|---|---|---|---|---|
| **DeepSeek V4.1 Flash** (25 no-think / 39 max; 16B) | Fireworks | 364 | 0.48 s | 0.22/0.66/0.007 | ✓/✓ | ✓ |
| | Together | 265 | 0.41 s | 0.30/1.20/0.006 | ✓/✓ | ✓ |
| | DeepSeek | 232 | 1.11 s | 0.15–0.30/0.60–1.20/0.003 | ✓/✓ (tool_choice "auto" only listed) | ✓ |
| | Baseten | 240 | 0.54 s | 0.30/1.20 | ✓/✗ (33K max out) | ✗ |
| **gpt-oss-120b** (12; 5.1B) | Cerebras | **1,688** | 0.48 s | 0.35/0.75/no discount | ✓/✓ | not listed |
| | SambaNova | 703 | 1.19 s | 0.14/0.95 | ✓/✗ | ✗ |
| | Groq | 475 | 0.68 s | 0.15/0.60/0.075 | ✓/✓ | ✗ |
| gpt-oss-20b | Groq | 950 | UNVERIFIED | 0.075/0.30 | ✓/✓ | ✗ |
| **GPT-6 Luna** (18/21/37; 2026-09-22) | OpenAI | 143 | 0.73 s | 0.10/0.50/0.01 (priority 0.20/1.00) | ✓/✓ | ✓ |
| | Azure (EU) | 246 (max) | UNVERIFIED | 0.11/0.55 | ✓/✓ | ✓ |
| **GLM-5.3-Flash** (42 reasoning; 18B; MIT) | Fireworks | 182 | UNVERIFIED | 0.15/0.50/0.03 | ✓/✓ | ✓ |
| | Together | 109 | 0.71 s | 0.15/0.50/0.03 | ✓/✓ | ✓ |
| **MiniMax-M3** (29; 23B; IFBench 82.9%) | Together | 146 | 0.69 s | 0.30/1.20/0.06 | ✓/✓ | ✓ |
| Qwen3.8-27B (20/34; dense) | Crusoe (fastest on OR) | 208 | slow (thinking) | ~0.07–0.45/1.9–3.2 | ✓/✓ | — |
| Qwen3.8-Flash-Next (40; 6B) | Alibaba only | 57 | 2.5 s | 0.15/0.47/0.016 | ✓/✓ | ✗ |
| MiMo-V2.6-Pro (46; 42B) / V2.6-Flash (38; 15B) | Xiaomi / DeepInfra | 44 / 60 | — | 0.435/0.87 · 0.14/0.28 | ✓/✓ | — |
- Qwen3.8-27B on Cerebras only with a separate Cerebras key (not on OpenRouter): vendor ~1,500–1,850 tok/s, $0.99/$1.49, 64K ctx free / 128K paid, "preview" tier; 150K TPM cap reported (UNVERIFIED).
- Rejected: Gemini 3.8 Flash (13–30 s TTFT with thinking, ~$0.75/$3.75), Muse Spark 1.3 ($1.25/$4.25, ~25 s TTFT), Mercury 2.5 (II 12, ~3.1 s).
- **No option reaches ≥800 tok/s AND <0.4 s TTFT.** For short tool calls TTFT dominates: 60-token call ≈ 0.64 s on V4.1 Flash (Fireworks/Together) vs ≈ 0.57 s on gpt-oss (Cerebras, but II 12).
- Smart but fast: V4.1 Flash low-effort thinking on Fireworks (~1.5–2 s), then GLM-5.3-Flash (Fireworks).
- Pinning: `provider:{order:["fireworks","together"], allow_fallbacks:true, require_parameters:true}` + `reasoning:{enabled:false}`; `sort:"latency"` / `preferred_max_latency:{p90:…}` deprioritise (don't exclude); `:nitro` may route to priority tier; `order` overrides sticky routing; without pin, `session_id` keeps provider (cache warm; expires after 10 min idle).

## 3. Intelligence per active parameter (AA II v4.3.2)
| # | Model | II / active B | II per B | Best speed |
|---|---|---|---|---|
| 1 | Qwen3.8-Flash-Next (thinking) | 40/6 | 6.7 | 57 tok/s (slow) |
| 2 | Qwen3.6-35B-A3B (thinking) | 18/3 | 6.0 | ~140 |
| 3 | Ling 3.0 Flash (thinking) | 25/5.1 | 4.9 | 373 (TTFT 3 s) |
| 4 | MiMo-V2.6-Flash | 38/15 | 2.5 | 60 |
| 5 | **DeepSeek V4.1 Flash max** | 39/16 | 2.4 | 364 |
| 6 | gpt-oss-120b | 12/5.1 | 2.4 | 1,688 |
| 7 | GLM-5.3-Flash | 42/18 | 2.3 | 182 |
| 8 | **DeepSeek V4.1 Flash no-think** | 25/16 | 1.6 | 364 (best open non-thinking) |
| 9 | Qwen3.8-27B max | 34/27 | 1.3 | Cerebras ~1,500+ |
| 10 | MiniMax-M3 | 29/23 | 1.3 | 146–179 |
| 11 | MiMo-V2.6-Pro / GLM-5.3 | 46/42, 45/40 | 1.1 | 44–87 |
Latency-weighted winner: V4.1 Flash on Fireworks/Together. Tool use: AutomationBench-AA V4.1 Flash max 68.9% (≈ GPT-6 Astra, Claude Opus 5.5); llm-stats AutomationBench V4.1 Flash 54.8%, GLM-5.3-Flash 48.8%, GPT-6 Luna 14.9%. **No independent Italian/multilingual scores for 2026 candidates → our benchmark must measure it.**

## 4. Real-time techniques
1. **Two-stage response:** local classifier picks the order → pre-recorded ack in NPC's voice & language + sim executes immediately → LLM runs in parallel for nuance/corrections/refusals (can roll back).
2. **Speculative speech:** classify every partial transcript (ms); start LLM once partial stable ~250 ms; abort/restart if final differs (prefix cache makes restarts cheap). Abort stops billing on DeepSeek/Fireworks/Together (not Groq/SambaNova/Alibaba/MiniMax).
3. **Stream tool calls:** parse args incrementally; start animation on function name; act when required args complete. `tool_choice:"required"` on command tiers (test on DeepSeek; OpenRouter lists only "auto").
4. **Fewer round trips:** coarse tools (`execute_maneuver(plan)`), multiple calls per response, 5–10 tools per role with small flat enum schemas.
5. **Cache-friendly prompt order:** shared English system prompt + tools → doctrine → persona → world summary → fast-changing state → player's words; deterministic JSON; no timestamps in prefix; append-only transcripts (DeepSeek segments end at turn boundaries).
6. **Hedging:** crew tier → DeepSeek direct + Fireworks (via OpenRouter) in parallel, first valid tool call wins, abort the other; other tiers → backup only if no first token by p90 (~10% extra cost).
7. **Structured-output cost:** native tool calls > JSON mode; cap `max_tokens`; thinking off on critical path.
8. **Connections:** pre-warmed HTTP/2 keep-alive; ignore SSE comments (`: keep-alive`); per-tier priority queues; drop stale responses (sim tick); ships keep running on behavior-tree defaults while LLM thinks.

Local intent models (M4 timings estimated):
| Model | Params | Langs | Dims/ctx | Licence | Est. M4 |
|---|---|---|---|---|---|
| multilingual-e5-small | ~118M | ~100 | 384 | MIT | ~2–5 ms |
| **EmbeddingGemma-300m** | 308M | 100+ | 768→128 / 2K | Gemma | ~5–15 ms |
| Qwen3-Embedding-0.6B | 0.6B | 100+ | 32–1024 / 32K | Apache | ~10–25 ms |
| bge-m3 | ~568M | 100+ | 1024+sparse / 8K | MIT | ~10–25 ms |
EmbeddingGemma lacks float16 support → ANE may be unsuitable; run on CPU (no GPU contention with UE). ~30 multilingual example phrasings per intent; accept only if top score clearly beats second; regex for numbers; else fall through to LLM. **No ≤1B local LLM for acks** (II 5–6, weak Italian) → pre-recorded ack bank indexed by intent × language × character.

## 5. Routing plan
| Tier | Finalists | Setting | Expected latency from Italy (UNVERIFIED) |
|---|---|---|---|
| 0 local | EmbeddingGemma / e5-small + recorded acks | — | < 50 ms |
| Crew fast path | ① V4.1 Flash via Fireworks (backup DeepSeek direct) ② gpt-oss-120b Cerebras ③ opt. Qwen3.8-27B Cerebras (extra key) | thinking off | 0.6–0.9 s to complete tool call |
| Bridge officers | ① V4.1 Flash DeepSeek direct (backup Fireworks) ② GPT-6 Luna off/low ③ GLM-5.3-Flash (Fireworks) | off/low | 0.8–1.8 s |
| Captains/admirals | ① V4.1 Flash ② GLM-5.3-Flash ③ MiniMax-M3 (Together) | low/high | 2–6 s (radio chatter meanwhile) |
| War Director (background) | ① V4.1 Flash max ② MiMo-V2.6-Pro ③ Qwen3.8-Flash-Next | max | 10–60 s off critical path |
| Chatter | ① V4.1 Flash off, off-peak ② GPT-6 Luna off ③ batch pre-generated | off | not critical |
Cost per battle-hour (150 crew LLM calls, 5 officers /15 s, 8 captains /10 s, 2 admirals /30 s, Director /60 s, 600 chatter lines, ~85% cached): **≈ $1.8 off-peak / $3.6 peak**; captain output ≈ 60% of cost; **event-driven triggering → ≈ $0.5–1.5**.

## Benchmark protocol
- From Italy (+ Frankfurt control); windows: DeepSeek peak (08–12 CEST), evening (20–23), weekend.
- 1 / 8 / 32 concurrent; ≥500 requests per config; streaming + usage on.
- Configs: V4.1 Flash direct / Fireworks / Together × thinking off/low/high; gpt-oss-120b Cerebras; GPT-6 Luna off/low; GLM-5.3-Flash Fireworks; MiniMax-M3 Together; opt. Qwen3.8-27B Cerebras.
- Speed/cost metrics: cold vs warm connect, TTFB, TTFT, time-to-tool-name, time-to-args-complete, tok/s, p50/p90/p99, errors/429/hangs, cache-hit ratio, cost/call, hedge win rate, OpenRouter overhead.
- Quality set: 200 crew orders (50 intents × IT, EN + 2 other languages, ASR noise, code-switching), 60 officer, 60 captain, 20 Director, 60 chatter scenarios with gold tool names/args checked by deterministic sim replay.
- Scoring: JSON/schema validity, exact tool+args, plan success in sim, instruction following (persona, length, reply in player's language, no English leakage), Italian quality (blind native rating 1–5 on 60 samples + LLM judge).
- Decision rule per tier: cheapest config meeting tier p90 latency budget with ≥98% valid tool calls and ≥95% language fidelity.

## Sources
DeepSeek: pricing, V4.1 news (news260910), changelog, thinking mode, KV cache, tool calls, JSON mode, rate limits, status page, 2026-09-14 outage article, arXiv 2609.19969. Artificial Analysis: leaderboard; V4.1 Flash (+providers, non-reasoning + providers); gpt-oss-120b (+providers); gpt-oss-20b providers; Qwen3.8-27B providers; GLM-5.3-Flash (+providers); GPT-6 Luna (+providers); MiniMax-M3 providers; Qwen3.8-Flash-Next; Ling 3.0 Flash; Inkling Small; Mercury 2.5; Muse Spark 1.3; open-weights & small open-weights; AutomationBench-AA; IFBench; τ²-bench; multilingual; Global-MMLU-Lite; llm-stats AutomationBench. OpenRouter endpoint listings for deepseek-v4.1-flash, gpt-oss-120b/20b, qwen3.8-27b, qwen3.8-flash, glm-5.3-flash, gpt-6-luna, minimax-m3, mimo-v2.6-flash/pro; OpenRouter docs (prompt caching, provider routing, latency, :nitro, reasoning, streaming). Cerebras models; OrcaRouter & explainx on Qwen3.8-27B; Groq models. EmbeddingGemma blog + card; Qwen3-Embedding-0.6B; multilingual-e5-small; bge-m3. Gemini 3.8 Flash pricing (eesel), AA Gemini 3.5 Flash-Lite.
