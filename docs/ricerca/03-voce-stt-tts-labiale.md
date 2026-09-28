# Research 03 — Voice stack: STT, TTS, lip-sync (2026-09-27)

USD list prices; UNVERIFIED = not confirmed for Sept 2026. Web-search quota ran out early; vendor pages read directly.

## 1. STT (player voice commands)
| Option | Latency | Price | Italian | Custom vocab | Notes |
|---|---|---|---|---|---|
| **Apple SpeechTranscriber** (macOS 26, on-device) | volatile results near-instant; final UNVERIFIED | free | yes (42 locales / 22 langs) | no (only older DictationTranscriber has custom phrases) | Swift async API → C++ via Swift lib with `@_cdecl` or helper process (MIT `ohr` example); one language per instance; OS-managed model (no app memory); Mac only |
| WhisperKit large-v3-turbo (MIT) | 0.46 s/word (M3 Max ANE); M4 Air UNVERIFIED | free | yes | prompt | runs on Neural Engine (no GPU contention with UE); 0.6 GB |
| whisper.cpp | chunked | free | yes | prompt | cross-platform; wrapped for UE by Georgy Dev *Runtime Speech Recognizer* |
| Groq whisper-large-v3-turbo | per-utterance HTTP, ~216× RT | $0.04/h (10 s min) | yes | prompt ≤224 tok | cheapest cloud; no partials |
| **Deepgram Flux Multilingual** (GA 2026-04-29) | end-of-turn <400 ms | $0.0078/min (+$0.0013 keyterms) | yes | keyterms ≤500 tok | best turn detection (hands-free); self-hostable |
| OpenAI gpt-live-transcribe (2026-07-29) | adjustable delay | $0.017/min | yes | keywords + context | no VAD; gpt-4o-transcribe $0.006/min, mini $0.003 |
| **ElevenLabs Scribe v2 Realtime** | ~150 ms + network | $0.39/h (+$0.05 keyterms) | yes | keyterms | batch Scribe v2 2.2% WER (AA, English) |
| AssemblyAI Universal-3 Pro Streaming | median ~150 ms | $0.45/h | yes, code-switching | ≤1,000 words | older Universal-Streaming Multilingual $0.15/h |
| Speechmatics | partials <500 ms; final ≥0.7 s | ~$0.24/h (UNVERIFIED RT) | yes | dictionary | 0.7 s floor too slow |
| Gemini 3.5 Transcribe Live | UNVERIFIED | ≈$0.009/min | yes | UNVERIFIED | batch 2.6% WER |
No independent Italian streaming benchmark → build our own test set (ship/system names over battle audio). Design > vendor: **push-to-talk** (release = end of turn, billing only while talking, no game-audio triggers), headset/AEC, give the LLM the list of valid names to fix mishearings.

## 2. TTS (NPC voices)
Artificial Analysis Speech Arena Sept 2026 (English-weighted): 1 Cartesia Sonic 3.6 (1277), 2 Gemini 3.8 Flash TTS (1268), 3 Qwen-Audio-3.0-TTS-Plus, 4 Inworld Realtime TTS-2 (1244), 5 Gemini 3.8 Flash-Lite TTS; ElevenLabs v3 Conversational 12th (1197), MiniMax 2.8 HD 16th, Eleven v3 17th, Fish S2.1 Pro 21st. **No Italian ranking → blind Italian listening test required.**

| Model | TTFA | $/1M chars | Italian | Voices/design/clone | Emotion | Lip-sync data |
|---|---|---|---|---|---|---|
| ElevenLabs Flash v2.5 | ~75 ms | 50 | yes | huge library, Voice Design v3 (70+ langs), cloning | weak | char timings (WS) |
| ElevenLabs v3 Conversational | ~280 ms | 50 (v3 non-RT 100) | yes | same | audio tags (shout, fear…) | UNVERIFIED |
| Cartesia Sonic 3.6 (GA 2026-08-27) | "<90 ms" | ~37–49 | yes | clone from 10 s | emotion controls English-only | word+phoneme timings |
| Inworld Realtime TTS-2 / TTS-2 Flash | 100 / 20 ms (P90 server) | 25 / 15 (≤5 enterprise) | "200+ langs", IT quality UNVERIFIED | voice design from text; clone 5–15 s | style instructions, non-verbals | **phonemes + 13 visemes** (+~100 ms) |
| Gemini 3.8 Flash / Flash-Lite TTS | UNVERIFIED | ~16.5 / ~11 (promo to 2026-12-31, then 2×) | yes | 30 voices, design, cloning | style prompts, inline tags | UNVERIFIED |
| MiniMax Speech 2.8 Turbo / HD | UNVERIFIED | 60 / 100 | yes | design $3/voice, clone $1.5/voice | emotion param | word timings |
| OpenAI gpt-4o-mini-tts | UNVERIFIED | ≈18 (est.) | yes ("optimized for English") | 13 voices | instructions | — |
| Fish Audio S2.1 Pro | ~100 ms | 15 per 1M bytes | lowest tier | cloning | bracket tags | — |
| Hume Octave 2 | ~100 ms | 50–150 | yes | design English-only | acting "coming soon" | word+phoneme |
| Rime | 37 ms | 30–50 | **no** | — | — | — |
Local/open (commercial): **Qwen3-TTS** (Jan 2026, Apache-2.0; Italian, design, clone 3 s, emotion by instruction; 97 ms on GPU; Argmax TTSKit on Apple Silicon) = best offline; Chatterbox Multilingual V3 (MIT; Italian; emotion intensity; watermark) second. Kokoro only 2 Italian voices (grade C). VibeVoice-Realtime not for commercial use. Orpheus es/it = research, Llama license. Not usable: Kyutai (EN/FR), IndexTTS2 (ZH/EN, restrictive), F5-TTS (non-commercial), Sesame CSM & Dia (EN only).
Licensing: commercial use needs paid tiers (Cartesia free tier forbids it; Inworld paid tiers grant commercial license). Written consent for any cloned actor.

## 3. Speech-to-speech for one-on-one NPCs
- OpenAI gpt-realtime-2.1: ~$0.019/min in, $0.077/min out (context re-billed each turn; caching helps); mini ~$0.006 / $0.024.
- Gemini 3.8 Live: $0.005/min in, $0.018/min out; non-blocking function calls; tone adaptation; 15-min resumable sessions; ephemeral tokens.
- Pros: fastest, natural interruption, expressive, native tool calls. Cons: vendor voice sets only (can't give dozens of crew distinct voices), one live session per NPC, less control over text (lore, moderation, logs).
- **Verdict:** STT→LLM→TTS backbone; optionally Gemini Live for special 1:1 scenes.

## 4. Runtime lip-sync
| Option | Shippable | Mac | Notes |
|---|---|---|---|
| **Georgy Dev Runtime MetaHuman Lip Sync** (Fab) | yes, CPU 10 ms steps | yes (Win/Mac/Linux/iOS/Android/Quest; UE 5.0–5.8) | Standard (14 visemes), Realistic (81 face controls), Mood (12 moods); audio-based → any language incl. Italian; streamed TTS via Runtime Audio Importer; price UNVERIFIED |
| MetaHuman Animator from audio (Epic) | **no** (5.8 notes: "Editor-only solution; not a runtime or player-facing feature") | face anim on macOS since 5.8 | offline 30 fps → pre-bake scripted/cutscene lines |
| NVIDIA Audio2Face-3D (open-sourced 2025-09-24) | NVIDIA GPUs only (CUDA ≥12.8 + TensorRT) | **no** | UE plugin v2.5 for 5.4–5.6 |
| OVR Lipsync | EOL | — | avoid |
| TTS vendor timings → visemes | yes | yes | Inworld visemes, Cartesia phonemes, ElevenLabs char timings, Azure visemes/blendshapes → fine for background NPCs |

## 5. Recommended stack
**(a) Dev on the M4 Air now:** STT = Apple SpeechTranscriber via Swift bridge + push-to-talk (compare vs Scribe v2 Realtime with keyterms; WhisperKit on ANE if local vocab hints needed; no Whisper on GPU alongside UE). TTS = ElevenLabs (Flash v2.5 routine; v3 Conversational combat/fear; Voice Design v3 for dozens of Italian crew voices); Inworld TTS-2 as challenger; blind Italian test (30 lines: calm, shouting, fear, radio) incl. Gemini 3.8 Flash TTS, Sonic 3.6, MiniMax 2.8. Radio = UE filter chain (band-pass + distortion). Faces = Georgy Dev Realistic/Mood; MetaHuman Animator offline for cutscenes. Latency: PTT release→text 150–300 ms + LLM first sentence 300–500 ms + TTS first audio 75–280 ms + network ≈ 0.7–1.1 s → stream LLM→TTS by sentence; instant pre-generated per-voice ack ("Agli ordini, Capitano").
**(b) Shipped multiplayer:** keys on backend; crew agents server-side; PTT Opus → server → cloud STT (Scribe v2 RT or Flux for hands-free); local Apple/whisper.cpp fallback; NPC lines generated once server-side, streamed to clients in earshot, cached; clients compute lip-sync (or send Inworld visemes) → cost scales with lines, not listeners; at volume Inworld enterprise (≤$5/1M chars) or Gemini Flash TTS for chatter, ElevenLabs for hero voices.

Cost per talkative hour (12k chars NPC speech, 5 min PTT; LLM excluded except S2S):
| Stack | STT | TTS | ≈ Total |
|---|---|---|---|
| Scribe v2 RT + ElevenLabs Flash/v3 Conv | $0.04 | $0.60 | **$0.64** |
| Flux Multilingual + Inworld TTS-2 | $0.05 | $0.30 | **$0.35** |
| Local STT + Gemini 3.8 Flash TTS | $0 | $0.20 ($0.41 from 2027) | **$0.20** |
| AssemblyAI U-S Multilingual + Inworld enterprise | $0.01 | $0.06 | **$0.07** |
| S2S Gemini 3.8 Live | — | — | ~$0.30 + re-billed context |
| S2S gpt-realtime-2.1 / mini | — | — | ~$1.25 / ~$0.39 + context |
Always-open mic: Scribe $0.39/h, Flux $0.55/h, gpt-live-transcribe $1.02/h.

## 6. Keys to request (ranked)
1. **ElevenLabs** (TTS + Voice Design + Scribe v2 RT; paid plan). 2. **Inworld** (TTS-2 / Flash; visemes; cheapest top-ranked at scale). 3. **Google Gemini API** (3.8 Flash TTS, 3.8 Live, 3.5 Transcribe; free dev tier). 4. **Deepgram** (Flux; $200 free credit). 5. Optional: OpenAI, Cartesia, AssemblyAI.
No key: Apple Speech, WhisperKit/TTSKit, Qwen3-TTS, Chatterbox. Georgy Dev plugins bought on Fab.

## Sources
Apple WWDC25 277, SpeechTranscriber/AnalysisContext docs, ohr, argmax-oss-swift, arXiv 2507.10860, Georgy Dev docs, Groq STT docs, Deepgram pricing/Flux/keyterm, OpenAI pricing & transcription/realtime docs, ElevenLabs pricing/models/Scribe v2 RT/WS stream-input, AssemblyAI U3 Pro streaming & pricing, Speechmatics docs/pricing, Gemini pricing/models/speech-generation/live-guide, Artificial Analysis STT & TTS leaderboards, Cartesia pricing/models/changelog/emotion/WS/terms, Inworld pricing/TTS/models/release notes/timestamps, Google Chirp 3 HD, MiniMax pricing/T2A, OpenAI TTS & gpt-4o-mini-tts, Fish Audio pricing/models, Hume pricing/TTS, Rime pricing, Qwen3-TTS, Chatterbox, Kokoro voices, VibeVoice, Kyutai DSM, IndexTTS, Orpheus (+ es_it research release), F5-TTS, Sesame CSM, Dia, gpt-realtime-2.1 & realtime costs, Georgy Dev Runtime MetaHuman Lip Sync, Epic MetaHuman audio-driven/realtime/5.7/5.8 notes & known issues, NVIDIA Audio2Face-3D SDK/models/blog/ACE archive, Meta OVR Lipsync, Azure viseme docs.
