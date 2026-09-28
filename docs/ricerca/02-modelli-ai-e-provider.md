# Research 02 — Runtime LLM stack for NPC crews (2026-09-27)

All figures accessed 2026-09-27. **II** = Artificial Analysis Intelligence Index v4.3.2 (harder scale: cheap models ≈10–45). AA speeds = 72-h medians with 10k-token input (a 3k cached prompt should see lower TTFT). These models post-date Claude's training data → **must be verified with our own benchmark**.

## 1. Key findings
- New cheap generation: GPT-6 Luna (22 Sep), DeepSeek V4.1 Flash (10 Sep; MIT; 552B total / 16B active), Qwen3.8 (Aug–Sep), Gemini 3.7 & 3.8 Flash.
- Cerebras self-serve: only gpt-oss-120b and Qwen3.8-27B; everything else Enterprise ("Dedicated"); EU capacity reported for end-2026.
- Groq: GroqCloud still runs after NVIDIA's Dec-2025 licence deal (~$20B reported; Ross & Madra joined NVIDIA); new CEO, $3.5B valuation (Aug 2026), repositioning as general cloud on NVIDIA HW; self-serve down to gpt-oss-120b/20b + previews.
- SambaNova deprioritising cloud (self-serve 60 RPM).
- **TTFT < 300 ms not reliable from Italy**: best AA TTFT 0.21–0.5 s (+~0.1 s EU→US est.) → hide with canned "Aye, Captain" + streaming.
- **Use Chinese weights, not Chinese APIs, for player data**: Garante's Jan-2025 order vs DeepSeek appears still in force → run MIT/Apache weights on US/EU hosts. Alibaba Frankfurt EU mode = only Chinese API worth evaluating.
- EU residency on serverless: first-party only (OpenAI eu.api w/ approval, Google `eu`, Mistral api.eu, Claude via Bedrock EU incl. Milan or Vertex; +10%); Alibaba Frankfurt; open-weight hosts (Fireworks, Together, Nebius, Baseten) EU only on dedicated; EU clouds (Scaleway, OVHcloud, IONOS, Regolo/Seeweb) fewer models, slow/unmeasured.

## 2. Comparison
| Model (II) | Provider | tok/s | TTFT | $ in/out (cached) /1M | Caching | Tools/JSON | EU | Notes |
|---|---|---|---|---|---|---|---|---|
| **DeepSeek V4.1 Flash** (no-reasoning 25; max 39) | Fireworks / Together / Baseten | 364 / 260 / 240 | 0.50 / 0.42 / 0.55 s | 0.30/1.20 (0.006) | auto | ✓; 0.09% tool-call error on Fireworks (OpenRouter data) | dedicated only | speeds on AA max-effort endpoints; AutomationBench-AA 68.9% (#2); DeepSeek API 243 tok/s, 1.16 s |
| **GPT-6 Luna** (none 18; low 21) | OpenAI / Azure | 143 | 0.73 s | 0.10/0.50 (0.01) | auto ≥1,024 tok | strict schema + tools | eu.api | Tier 2 5,000 RPM |
| **Qwen3.8-27B** (no-reasoning 20; low 26) | Cerebras | ~1,850 (vendor) | not measured | 0.99/1.49 (no discount) | none | tools, parallel, strict | ✗ | Apache-2.0 |
| gpt-oss-120b (low 10) | Cerebras | 1,737 | 0.48 s | 0.35/0.75 | none | strict | ✗ | AA endpoint accuracy 87% |
| gpt-oss-120b | Groq | 475 | 0.68 s | 0.15/0.60 (0.075) | 50% | strict JSON not w/ streaming/tools | Helsinki DC, no pinning | Flex 10× limits |
| gpt-oss-20b (9) | Groq | 934 | 0.79 s | 0.075/0.30 (0.037) | 50% | ✓ | as above | |
| GLM-5.3-Flash (42, reasoning) | Baseten / Fireworks | 182 / 184 | 0.53 / 1.35 s | 0.15/0.50 (0.03) | auto | ✓ | dedicated | MIT; 18B active |
| MiniMax-M3 (29) | Together / Fireworks | 138 / 157 | 0.69 / 1.01 s | 0.30/1.20 (0.06) | auto | ✓ | – | IFBench 82.9% |
| Gemini 3.7 Flash (low 37) | Google | 314 | 1.19 s | 0.75/3.75 (0.075)* | implicit ≥4,096 | ✓ | `eu` | thinking can't be fully off |
| Gemini 3.8 Flash (med 40; high 41) | Google | 306 | ~30 s (high) | 0.75/3.75 (0.075)* | same | ✓ | `eu` | *promo to 2026-12-31, then 1.50/7.50 |
| Claude Haiku 4.5 (no-reasoning 15) | Anthropic | 81 | 0.68 s | 1/5 (0.10) | explicit ≥4,096 | strict tools | Bedrock/Vertex | BFCL v4 68.7% (#6) |
| Claude Sonnet 5 (no-reasoning 23; max 38) | Anthropic | 66 | 1.3 s | 2/10 (0.20) | explicit | ✓ | same | |
| Mistral Small 4 (no-reasoning 9) | Mistral | 160 | 0.73 s | 0.15/0.60 (0.015) | auto | ✓ | api.eu | Apache-2.0 |
| Qwen3.8-Flash-Next (40) | Alibaba | 57 | 2.5 s | 0.15/0.47 | ~89% off | ✓ | Frankfurt (UNVERIFIED) | 6B active; no fast host yet |
| MiMo-V2.6-Pro (46) | Xiaomi | 44 | 3.8 s | 0.43/0.87 | ~99% off | UNVERIFIED | UNVERIFIED | 6 days old |
Not shortlisted: Gemini 3.5 Flash-Lite (349 tok/s but 9.9 s TTFT, thinking can't be off); xAI grok-4.3 ($1.25/$2.50, II 14; Grok Fast retired May 2026); Kimi K3 ($3/$15, slow); DeepInfra/Novita/SiliconFlow (slower/less accurate/no EU); diffusion Celeris-1 & Mercury 2.5 (fast but II 6/12).

## 3. Concurrency
Average battle ≈0.6 calls/s, but bursts (300 orders in 10 s ≈ 1,800 RPM) → size for bursts.
- Cerebras Developer: gpt-oss-120b 1,000 RPM / 3M TPM (no documented concurrency cap); Qwen3.8-27B 300 RPM / 750K TPM.
- Groq Developer limits UNVERIFIED; Flex 10× best-effort (HTTP 498 fail-fast); SLA enterprise only.
- Fireworks 6,000 RPM/account, adaptive TPM; Priority +25%. Together dynamic (penalises bursts). Baseten 120 RPM default. DeepInfra 200 concurrent/model. Nebius 60 RPM ramping 20×. OpenAI 500 (T1) → 30,000 (T5) RPM. Anthropic 1,000–10,000 RPM. DeepSeek 2,500 concurrent. Google spend throttle $10/$50/$200 per 10 min (T1–3). Too small w/o contract: MiniMax 200 RPM, Kimi 300, SambaNova 60.

## 4. Recommended tiers
- **(A) Crew brain:** DeepSeek V4.1 Flash, thinking off, on Fireworks (+ Together as 2nd host). Highest II among fast non-reasoning (25 vs Qwen3.8-27B 20, Luna 18, gpt-oss-120b 10); 260–364 tok/s, ~0.4–0.5 s TTFT; cached input ≈ free; MIT weights portable (dedicated EU possible). Challengers: Qwen3.8-27B on Cerebras (fastest; ~8× cost, no cache discount), GPT-6 Luna (effort none; cheapest, strict schemas, EU), GLM-5.3-Flash (thinking off), Gemini 3.7 Flash low (II 37, ~1.2 s, EU).
- **(B) Captains/admirals/Director:** DeepSeek V4.1 Flash high/max reasoning (II 39, ~12 s end-to-end, pennies/hour, same integration). Alternatives: Gemini 3.8 Flash (II 40–41, EU), MiMo-V2.6-Pro (II 46, very new), GLM-5.3-Flash (II 42). A/B Claude Sonnet 5 / Opus 5.5 for Director prose (few calls).
- **(C) Chatter/barks:** GPT-6 Luna effort none (multilingual, EU); Batch/Flex −50% to pre-generate pools. Alt: gpt-oss-20b on Groq (EN), Mistral Small 4 api.eu.
- **(D) Fallbacks:** same weights on another host (Fireworks/Together/Baseten; Scaleway Paris has older DeepSeek V4 Flash €0.40/€0.80); other family (GPT-6 Luna, Groq gpt-oss-120b Flex); last resort OpenRouter w/ fallbacks (EU endpoint needs Business/Enterprise).

## 5. Cost per intense battle-hour
Assumptions: crew 2,000 calls × (500 fresh + 2,500 cached in, 200 out); strategic 120 × (2,000 fresh + 6,000 cached, 800 out) (+R = +1,500 reasoning tokens); barks 1,000 × (1k in 80% cached, 50 out). List prices, cache-write ignored.
| Tier | Model/host | $/h cached | $/h uncached |
|---|---|---|---|
| A | DeepSeek V4.1 Flash (Fireworks/Together) | **0.81** | 2.28 |
| A | GPT-6 Luna none | **0.35** (EU 0.39) | 0.80 |
| A | gpt-oss-120b Groq / Cerebras | 0.77 / 2.40 | 1.14 / 2.40 |
| A | Qwen3.8-27B Cerebras | 6.54 | 6.54 |
| A | Gemini 3.7 Flash low (promo→2027) | † | 6.00 → 12.00 |
| A | Claude Haiku 4.5 | † | 8.00 |
| B | DeepSeek V4.1 Flash max | 0.19 (+R 0.41) | |
| B | GLM-5.3-Flash | 0.11 (+R 0.20) | |
| B | Gemini 3.8 Flash (promo→2027) | 0.59→1.19 (+R 1.27→2.54) | |
| B | GPT-6 Sol / Claude Sonnet 5 | 1.58 (+R 3.38) | |
| B | Claude Opus 5.5 | 3.17 (+R 6.77) | |
| C | GPT-6 Luna, 1,000 barks | 0.05 | |
† 3k prompt below the 4,096-token caching minimum.
**Recommended stack (A + B w/ reasoning + C) ≈ $1.3 per battle-hour**; fastest crew + premium director ≈ $8/h. Keep static prompts/tool schemas byte-identical at the front. Voice likely costs more than LLMs (e.g., 2,000 lines × 100 chars at $12.50–25/1M chars = $2.5–5/h).

## 6. OpenRouter
Pinning `provider:{only:["cerebras"], allow_fallbacks:false}` (or `order`); `require_parameters`, `quantizations`, `sort`, `max_price`; suffixes `:nitro`, `:floor`, `:exacto`. Tool calls & json_schema normalised (strict only where provider supports). Auto Exacto on by default for tool calls (reorders by tool-call error rate) → pin providers & log `provider` for clean benchmarks. ~15 ms added (staff); a competitor test found TTFT on par, throughput ~10% lower. No token markup; card top-ups 5.5% fee; BYOK free to $25k/month then 5%. Provider rate limits apply; caching passes through with sticky routing. **Ideal single key for benchmarking.**

## 7. Local option
MacBook Air M4 16 GB (MLX/llama.cpp): dev use only (~10.7 GB GPU-usable, throttling, competes with Unreal); 1–4B models ~35–90 tok/s (est.); 20B/30B-A3B don't fit; uncached 2k prompt 5–9 s TTFT on 4–8B (est.). Apple Foundation Models: ~3B on-device, guided generation (@Generable), tool calling, Italian; macOS 27 improves tools & 8K context; ~85 tok/s, 0.27 s TTFT on M4 Max (community); Mac-only, Swift-first (C bindings exist); PCC model not callable from servers; acceptable-use bans content that "promote or enable violence" (risk for combat). → prototyping aid only.

## 8. NPC platforms
Inworld: mainly voice infra + no-markup model router; no visible UE SDK. NVIDIA ACE (NVIGI): on-device RTX; Nemotron Nano 9B (tools, Italian); UE 5.4–5.7 plugins → optional offline mode only. Convai: UE 5.8 actions, ~1.06 s first text, pricing UNVERIFIED. None beats direct provider APIs for hundreds of concurrent server-side tool calls.

## 9. API keys (ranked)
1. **OpenRouter** (all benchmarking with one key). 2. Fireworks (production DeepSeek V4.1 Flash / GLM-5.3-Flash / MiniMax-M3). 3. Cerebras Developer (measure Qwen3.8-27B & real limits; ask sales re Enterprise/EU). 4. OpenAI (GPT-6 Luna/Sol; start EU residency approval early). 5. Google (AI Studio now; `eu` later). 6. Groq Developer + Flex (fallback). 7. Together (2nd DeepSeek host; disable retention). 8. Optional: Anthropic (Director prose), Mistral/Scaleway (EU sovereign).
Don't use DeepSeek/Kimi/MiniMax/Xiaomi first-party APIs for player data; skip SambaNova.
Still UNVERIFIED: Italian quality per model (add Italian to our eval), Cerebras TTFT for Qwen3.8-27B, Groq Developer limits, Alibaba Frankfurt model list.

## Sources
Artificial Analysis (leaderboards, II v4.3.2, DeepSeek V4.1 Flash providers (+non-reasoning), gpt-oss-120b/20b providers, GPT-6 Luna, Qwen3.8 27B, Gemini 3.8 Flash, Gemini 3.5 Flash-Lite, MiniMax-M3, Cerebras, Groq, AutomationBench-AA, Endpoint Accuracy Index 2026-08-04, Multilingual), BFCL v4; Cerebras models/qwen-3.8-27b/rate limits; Groq models/rate limits/prompt caching/flex/newsroom; TechCrunch 2026-08-17; SambaNova limits; Fireworks pricing/rate limits/data residency; Together pricing/limits; Baseten; DeepInfra; Nebius; Scaleway; OVHcloud; Regolo; DeepSeek pricing/limits/V4.1 Flash card; Garante order 10097450; Alibaba regions/pricing; Z.ai pricing; Kimi limits; MiniMax limits; OpenAI GPT-6 Luna & data residency; Azure models; Gemini pricing/limits; Claude pricing/deprecations/rate limits/data residency; Mistral pricing/regional; xAI models; Celeris; OpenRouter provider selection/Auto Exacto/structured outputs/prompt caching/FAQ/endpoints API; HN latency comment; Opper router latency 2026-04-21; llama.cpp Apple Silicon bench; Apple MLX M5; WWDC26 FM session; Apple FM 2025 update & acceptable use; apple_fm_sdk; community bench; Inworld pricing/router/fastest-API guide; NVIDIA NVIGI (+plugins); Convai docs.
