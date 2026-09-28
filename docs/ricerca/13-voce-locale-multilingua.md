# Research 13 — Local-first multilingual voice stack & in-house lip-sync (2026-09-27)

Supersedes the cloud-first recommendation of report 03. Key constraint: on the M4 Air, **UE5 needs the GPU and 16 GB shared memory** — that matters more than which model sounds best.

## TL;DR
1. **Hybrid, local-first:** STT on the Neural Engine (ANE), runtime TTS on CPU/ANE, lip-sync on CPU → GPU left to Unreal.
2. Local TTS starts sooner than ElevenLabs (≈30–250 ms vs 150–500 ms from Italy), but **LLM TTFT (~350–800 ms est.) dominates** → TTS choice changes total delay only 10–25%; **pre-recorded instant acknowledgements matter more**.
3. ElevenLabs v3 Conversational: best emotion, most languages (70+). **Free tier = enough to evaluate, not to build on.**
4. Lip-sync: small audio-driven model → 52 ARKit shapes (any language) + phoneme track from espeak-ng → MetaHuman.

## 1. Local TTS
| Model (licence) | Langs / Italian | Voice & emotion | Streaming / first audio (their HW) | Apple Silicon evidence | Phoneme timings? | ONNX / CoreML |
|---|---|---|---|---|---|---|
| **Qwen3-TTS** 0.6B/1.7B (Apache-2.0) | 10 / strong | voice design + emotion instructions (1.7B; 0.6B limited), 3 s cross-lingual cloning | yes; 97/101 ms, RTF 0.29/0.31 (datacenter GPU) | 1.7B RTF 0.876 on M4 MBP 16 GB (idle GPU); M2 Max ≈0.55; 3–6 GB RAM | no | CoreML: Argmax TTSKit (MIT), speech-swift; ONNX none official |
| **Pocket TTS** 100M (MIT code, CC-BY-4.0 gated weights) | 6: EN, FR, DE, ES, PT, **IT** | WAV cloning, 26 presets; no emotion knob (via reference clip, UNVERIFIED) | ~200 ms (Python); C++ port claims ~30 ms | **~6× real-time on M4 Air CPU (2 cores)** | no | ONNX (community + C++ ORT port), CoreML (FluidAudio) |
| **CosyVoice3** 0.5B (Apache-2.0) | 9 / yes | emotion & speed instructions, cross-lingual cloning | ~150 ms (GPU) | MLX 4-bit RTF 0.59 on M5 Pro; lowest error in Soniqo test | no | MLX |
| Chatterbox Multilingual V3 0.5B (MIT, watermark) | 23 / yes | exaggeration knob, cloning | no official streaming | MLX on M4 slower than RT (0.71–0.76 s audio/s); 14–16 GB RAM | no | ONNX, CoreML beta |
| **Kokoro** 82M (Apache-2.0) | 8–9 / 2 weak IT voices | none | per sentence | CoreML on ANE ~23× RT | **yes (per-phoneme durations)** | ONNX + CoreML |
| Supertonic 3 ~99M (MIT code / OpenRAIL-M) | 31 (no ZH) / yes | presets; `<laugh>`, `<sigh>` | "fast on CPU" | no M4 numbers; repo archived 2026-09-09 | no (UNVERIFIED) | ONNX (C++/C# samples) |
| XTTS-v2 (NC) | 17 / yes | cloning | <200 ms GPU | slow on Mac (UNVERIFIED) | no | community |
| Fish S2 Pro 5B (NC) | 80+ | inline tags | ~100 ms H200 | MLX ~4× slower than RT → offline only | no | MLX |
| Voxtral TTS 4B (NC) | 9 / yes | cloning | 70 ms H200 | none | no | — |
| VoxCPM2 2B (Apache) | 30 / yes | design + cloning | RTF 0.3 RTX 4090 | RTF 1.76 on M4 Pro (too slow) | no | MLX |
| OmniVoice (NC weights) | 600+ | attributes, `[laughter]` | no streaming; RTF 0.025 H100 | runs on Mac GPU (speed UNVERIFIED) | no | — |
Rejected: Zonos (no IT), Higgs v3 (4B NC), VibeVoice-Realtime (EN), NeuTTS Nano & MeloTTS (no IT), Orpheus multilingual (3B research), Kani-TTS-2 (IT UNVERIFIED), Piper (flat, now GPL-3.0).
Italian/multilingual quality (subjective): ElevenLabs v3 > Qwen3 1.7B ≈ Fish S2 ≈ Voxtral > CosyVoice3 ≈ VoxCPM2 > Qwen3 0.6B ≈ Chatterbox ≈ OmniVoice > XTTS ≈ Pocket ≈ Supertonic > Kokoro/Piper. (Qwen's own Italian test beats ElevenLabs on clarity & similarity — vendor-reported.)
**On the M4:** Qwen3's 97 ms is a datacenter number; 1.7B barely real-time with idle GPU → with UE rendering both sizes likely fall behind or hitch. TTSKit (CoreML → maybe ANE, UNVERIFIED) is the Qwen3 route to test first. Fanless → throttling. **GPU-free candidates: Pocket TTS (CPU), Kokoro (ANE), Supertonic (CPU).**

## 2. ElevenLabs (Sept 2026)
| Plan | $/mo | Credits | What you get | Concurrency (Multilingual v2 · Flash) |
|---|---|---|---|---|
| Free | 0 | 10k | API access; no commercial use, attribution; Voice Library voices blocked via API (default & own designed OK); Voice Design listed; no cloning | 2 · 4 |
| Starter | 6 | 30k | commercial licence, instant voice cloning | 3 · 6 |
| Creator | 22 | 121k | professional voice cloning | 5 · 10 |
| PAYG | — | — | Flash $0.05, v2/v3 $0.10 per 1k chars | — |
Models: Flash v2.5 (32 langs incl. IT, ~75 ms, 0.5 credit/char, limited emotion); v3 Conversational (GA 2026-08-19; 70+ langs; [shouts]/[whispers]; ~280 ms). Latency from Italy: Flash 150–300 ms, v3 Conv 350–500 ms (est.; vendor quotes 150–200 ms EU WS). WebSocket gives per-character timing; one connection can multiplex several NPC voices. Free tier ≈ 20k Flash chars ≈ 20–25 min speech ≈ ~130 NPC replies/month; paid runtime ≈ $0.45–1.80 per player-hour (assumption).
**Verdict:** free tier now for side-by-side tests, auditioning hero voices, dev-time fallback for uncovered languages; not the runtime engine (quota, per-player cost, key can't live on clients, network variance). If ever a runtime dependency: Starter $6 minimum.

## 3. On-device STT
| Model (licence) | Langs / auto-detect | Streaming | Speed / accuracy | Runs on | Vocabulary |
|---|---|---|---|---|---|
| **Parakeet-TDT-0.6B-v3** (CC-BY-4.0) | 25 European; auto (no language label returned, UNVERIFIED) | sliding window | ~110× RT on M4 Pro; Italian WER 3–4% | **ANE** (FluidAudio, Apache-2.0) | none built-in (UNVERIFIED) |
| **WhisperKit large-v3-turbo** (MIT) | 99; detects language | yes; 0.46 s latency, 2.2% WER | 626 MB | **ANE** | prompt words |
| whisper.cpp + CoreML (MIT) | 99 | yes | M4 Air: 8 s audio in 1.6 s; ANE failed on macOS 26.4 beta → GPU fallback | GPU/ANE | initial prompt |
| Qwen3-ASR 0.6B/1.7B (Apache) | 30 + 22 ZH dialects; LID 96.8% | yes (server/MLX) | 1.7B 1.32% WER, RTF 0.027 on M5 Pro | GPU | UNVERIFIED |
| Voxtral Mini 4B Realtime (Apache) | 13 incl. IT | built-in, 80–2400 ms delay | needs ≥16 GB GPU | GPU | — |
| Canary-1B-v2 / Kyutai STT (EN/FR) / Moonshine v2 (EN) | too narrow or GPU-bound | | | | |
| Apple SpeechTranscriber | ~10 langs incl. IT; **no auto-detect** | yes | — | on-device | — |
Recommendation: **Parakeet v3 on ANE primary** (push-to-talk → no VAD wait; 3–8 s phrase finishes in tens of ms); **WhisperKit turbo on ANE** for language ID & non-European languages; LLM returns the language code and gets a glossary of ship/crew terms to fix recognition errors. Windows later: Parakeet via sherpa-onnx (v3 UNVERIFIED) + whisper.cpp.

## 4. In-house lip-sync
1. **Audio → 52 ARKit shapes (any language)**, run on TTS audio *before* playback (TTS is faster than RT → look-ahead, no lag).
   - v1: **`wav2arkit_cpu`** (Apache-2.0 ONNX; wav2vec2 + Alibaba LAM Audio2Expression; 52 ARKit @30 fps; ~45 ms CPU per 1 s audio claimed) → inside UE via **NNE ONNX Runtime CPU**.
   - Upgrade: **NVIDIA Audio2Face-3D v2.3** HF repo has plain `network.onnx` (75.8 MB) → ORT CPU or CoreML (NVIDIA-only ops UNVERIFIED); re-implement its ARKit conversion from the MIT SDK; v3.0 (725 MB) likely too heavy with UE on M4; NVIDIA Open Model License (emotion model only with A2F).
2. **Phoneme track:** text → phonemes via **espeak-ng** (100+ languages; **GPL-3.0 → separate process** for commercial builds); timings: TTS durations if available (Kokoro) → ElevenLabs char timing → alignment with `wav2vec2-xlsr-53-espeak-cv-ft` (Apache-2.0) (alternatives MMS-FA 158 langs NC; Qwen3-ForcedAligner 11 langs); phonemes → ~16 visemes with separate jaw & lip controls (JALI-*style* idea; **JALI is patented US 10,839,825** → own formulation).
3. **Combine:** neural model = natural motion; phoneme track enforces closures (p/b/m), labiodentals (f/v), rounding; loudness scales jaw (shouting opens wider).
4. **Beyond the mouth:** LLM tags each line with emotion + intensity (same tag drives TTS delivery) → brow/eye/cheek offsets; pitch/energy → brow raises on stress, nods on emphasis, head drop at phrase end; blinks ~15–20/min at phrase breaks + on big gaze shifts; gaze darts, head-eye coordination, breathing, listening nods while the player holds push-to-talk.
5. **Apply to MetaHuman** via Epic's `PA_MetaHuman_ARKit_Mapping` pose asset (Live Link Face path). Epic's audio-to-face solver is editor-only → use it to bake pre-recorded lines.
Expected quality ≈ Audio2Face level in any language (> uLipSync vowels-only (keep for distant NPCs) or Rhubarb (offline 2D)); < Epic's offline MetaHuman Animator. Premium later: distil Epic's editor solver outputs on thousands of multilingual clips into a small ONNX model outputting MetaHuman controls (licence UNVERIFIED). Licences: espeak-ng GPL-3 (separate process), JALI patent, EmoTalk NC, FLAME-based models need FLAME licence.

## 5. Recommended voice architecture
**(a) Dev on M4 now:** separate **voice process** beside the game — Swift part (FluidAudio, WhisperKit/TTSKit) + C++ part (Pocket TTS C++ port, ONNX Runtime); audio & face curves to UE via shared memory (lip-sync model can also run inside UE via NNE). STT on ANE, lip-sync on CPU, GPU for UE.
- Runtime TTS by language: EN/IT/FR/DE/ES/PT → **Pocket TTS** (each NPC voice cloned from saved reference clips); ZH/JA/HI → Kokoro; other covered languages → Supertonic 3; everything else → ElevenLabs (dev).
- **Qwen3-TTS 1.7B offline, not runtime:** voice design for each NPC + reference clips per emotion (calm, urgent, shouting, fear, whisper, radio) + pre-generated emotional peaks (battle shouts, screams). Promote Qwen3 0.6B via TTSKit to runtime only if RTF < 0.6 while UE hits target fps.
- Memory: voice stack ≈2–3 GB (est.); avoid Chatterbox (14–16 GB) and Qwen 1.7B (~6 GB) at runtime.
**(b) Multiplayer — speech rendered on each client (like graphics):** server runs LLM and sends ~100 bytes/line (NPC, text, language, emotion, voice ID+version, seed, start time); clients synthesize + lip-sync + spatialize → no server GPU, no keys on clients, scales with players. Not bit-identical across machines (fine): server owns timeline with estimated duration; clients pad/stretch ±5%. Player speech transcribed locally; only text to server. Server-rendered audio only for low-spec clients or ElevenLabs voices.

Latency budget (PTT release → NPC speaks):
| Stage | Local-first | ElevenLabs Flash (EU) |
|---|---|---|
| Final transcript | 50–150 ms | same |
| Pre-recorded ack starts | 100–200 ms | same |
| LLM first token + first clause | 350–800 ms (est.) | same |
| First clause → first audio | 30–250 ms | 150–300 ms (v3 350–500) |
| Playback/lip-sync buffer | 40–80 ms | same |
| **Real answer audible** | **≈0.5–1.3 s** | **≈0.6–1.4 s** |
Tricks: (1) 10–20 pre-recorded acks per NPC × language × emotion with baked face anim, chosen at PTT release by detected language, radio click covers the gap; (2) LLM streams emotion + language before text, first 3–6 words sent to TTS immediately; (3) keep warm (LLM prompt cache; per-NPC voice state loaded; Qwen3 prompt cache saves ~300 ms); (4) cache audio + face curves keyed by voice/lang/emotion/text, steer routine reports to standard phrasing, pre-generate callouts & chatter; (5) radio filter (band-pass, distortion, squelch) justifies ~200 ms and hides artifacts.

## Sources
TTS: Qwen3-TTS (GitHub, arXiv 2601.15621), Argmax argmax-oss-swift (+v1.1.0), mlx-audio Qwen3 README, Soniqo speak guide & benchmarks, drmhse tuning Qwen3-TTS on M4, mybyways, kapi2800 qwen3-tts-apple-silicon, speech-swift #106, Kyutai pocket-tts (GitHub, HF, site), PocketTTS.cpp, Chatterbox (+chatterbox-mlx), CosyVoice, Supertonic (+HF supertonic-3), XTTS-v2, Fish S2 (blog, HF), Voxtral TTS, VoxCPM, OmniVoice, Higgs Audio, Zonos, VibeVoice-Realtime, MeloTTS, piper1-gpl, Kokoro word timestamps, FluidAudio (+benchmarks). ElevenLabs: pricing, API pricing, models, voices, 40% faster, latency, websockets, v3 Conversational GA news. STT: parakeet-tdt-0.6b-v3, arXiv 2507.10860, whisper.cpp #3702, Qwen3-ASR, Voxtral Mini 4B Realtime, arXiv 2509.14128 & 2602.12241, kyutai stt, addpipe SpeechAnalyzer, sherpa-onnx. Lip-sync/UE: NVIDIA Audio2Face-3D (+SDK, HF v3.0, v2.3-Mark), arXiv 2508.16401, LAM_Audio2Expression, wav2arkit_cpu (+teacher dataset), EmoTalk, ARTalk, JALI (+patent), espeak-ng, wav2vec2-xlsr-53-espeak-cv-ft, ctc-forced-aligner, Qwen3-ForcedAligner, uLipSync, rhubarb-lip-sync, MetaHuman realtime animation & 5.8 notes, UE NNE overview, ARKitRemap.
