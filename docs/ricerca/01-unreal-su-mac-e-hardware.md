# Research 01 — UE 5.8 on Apple Silicon (MacBook Air 15" M4, 16 GB) & hardware path (2026-09-27)

## Ground truth read from the installed engine (5.8.3, CL 58210709)
- `Engine/Config/Mac/DataDrivenPlatformInfo.ini`: Mac SM6 supports Nanite, HW ray tracing, path tracer, 64-bit atomics; Mac SM5 has no Nanite/RT; templates target SM6 only; mesh shaders off on Mac.
- `BaseEngine.ini`: Mac target enables RT by default (`bEnableRayTracing=true`, `RayTracingMode=Full`); installed build ships only Mac Editor + Game configs (no Server/Client targets).
- Linux/Windows platform files set `Mac:bIsEnabled=false` → a Mac cannot package Windows games or Linux servers.
- MetalFX not used by engine (only a header references it). **Live Coding is Windows-only.**
- `Apple_SDK.json`: Xcode main 26.1.1, min 15.2, max 27.9; `Mac_SDK.json`: macOS 14.0 min.
- Apple Silicon: engine counts 75% of RAM as VRAM; BaseMacEngine gives 70% of that to textures → ~8.4 GB texture pool by default on 16 GB.

## 1. Release & features
- 5.8.0 shipped 2026-06-17; 5.8.2 hotfix 08-25; 5.8.3 09-22. 5.8 = last planned UE5 release before UE6.
- Production-ready: MegaLights, Iris ("for licensees"; plugin still Beta), Mass (rewritten, off-game-thread entity creation), StateTree, PCG, World Partition, MetaHuman Creator & Animator, Movie Render Graph, Substrate (since 5.7).
- Beta: Lumen "Lite" (~2× faster than Lumen High, 60 fps PS5/handheld target).
- Experimental: Nanite Foliage (Assemblies, Voxels, Dynamic Wind), Procedural Vegetation Editor, Mesh Terrain, FastGeo streaming, VSM prefiltered distant shadows, Mover, MetaHuman Crowd, Unreal MCP & AI Assistant.
- Chaos: 5.7 parallel solver stages; 5.8 CVD & caching improvements. Nothing new specifically for space/large worlds.

## 2. macOS/Metal support in 5.8
| Feature | Mac status |
|---|---|
| Nanite + VSM | Beta, M2+ |
| Lumen SW RT | Supported |
| Lumen HW RT, MegaLights | Experimental, M2+ (HW-accelerated M3/M4) |
| Path tracer | SM6, experimental group |
| Substrate | Works (glint AA disabled on Metal) |
| TSR, Sky Atmosphere, Volumetric Clouds/Fog, Local Fog | No Mac restrictions found |
| Heterogeneous Volumes | Metal-specific code exists; no official statement (UNVERIFIED) |
| MetalFX | Not integrated (community alpha plugin only). No DLSS. |

Known Mac problems: **Xcode ≥ 26.4 fails to compile (UE-377426)**; Xcode 26 needs separate Metal Toolchain (installed on this Mac); Live Link Hub on macOS reported not launching (Aug 2026); 5.8.1–5.8.3 each fixed Metal crashes incl. an RT bug.

## 3. Real-world performance
- Base M4 Mac mini 16 GB (with fan): FP template 30–47 fps in editor; Lyra 29–45; heavy scene 20–35 (High) / 45–70 (Medium); RAM in use 13–14.4 GB.
- 15" M4 Air (fanless): Notebookcheck ~22% GPU drop under sustained load.
- Estimate for this Air: 1080p output, TSR 50–67%, Medium–High, software Lumen → ~25–35 fps in modest interiors; <20 fps when throttled or with many lights/volumetrics/MetaHumans. 1440p not realistic.

## 4. Requirements & Xcode
- Mac: min M1/M2 (feature-dependent), 16 GB; recommended **M3 + 32 GB+**; macOS Sonoma 14.5+ (Sequoia 15 recommended; Tahoe not listed); Xcode min 26.0, rec 26.1.1, **26.4 incompatible**.
- Windows: Win 11, 32 GB, DX12 GPU ≥8 GB, Visual Studio 2026; HW RT & MegaLights need RTX 20 / RX 6000 / Arc or newer.
- This Mac's Xcode 26.2 is within range and below the 26.4 breakage → **disable Xcode auto-updates.**

## 5. MetaHuman on Mac
- Creator works in-editor on macOS since 5.7 (5.8.3 ships Mac binaries).
- Animator: 5.8 adds offline + real-time facial animation on macOS (bundled CoreML models); body capture Windows-only.
- Audio-driven: offline audio-to-face works on Mac; real-time audio Live Link source ships for Mac (5.8: better model, procedural blinks, emotion detection) but depends on an editor-only module → **not shippable runtime lip-sync** (reading of plugin files, UNVERIFIED).
- Runtime cost: 8 LODs; LOD0 head ≈24k verts, 669 blendshapes, 713 joints; Mac = hair cards only (no strands); ~3–6 ms GPU per close-up MetaHuman on RTX 3070/4070 (1–4 at 60 fps); MetaHuman Crowd (experimental) for tens–thousands. On this Air: 1–2 close-up MetaHumans realistic.

## 6. Launcher vs source build
- Launcher build **cannot build dedicated servers** ("targets are not currently supported from this engine distribution") → source build required.
- Source build on Mac ≈200 GB after compile (guides advise 500 GB–1 TB free), multi-hour compile → **impossible with 55 GB free**.
- For now: PIE "Play As Client" runs a dedicated-server instance → enough to prototype server-authoritative networking.

## 7. Hardware options (USD, Sept 2026; EUR UNVERIFIED)
| Option | Price |
|---|---|
| Mac mini M6 (12-core GPU, up to 32 GB) | $899 (per agent; verify) |
| Mac mini M5 Pro (up to 20-core GPU, 64 GB, TB5) | from $1,699 |
| MacBook Pro 14" M5 Pro / M5 Max | $2,499 / $4,099 |
| MacBook Pro 16" M5 Pro / M5 Max | $2,999 / $4,399 |
| Mac Studio M5 Max / M5 Ultra | $2,499 / $5,499 |
| RTX 5070 Ti 16 GB | list $749, street ~$1,230 |
| RTX 5080 16 GB | list $999, street ~$1,650 |
| RTX 5090 32 GB | list $1,999, street ~$3,980 |
| AWS g6.2xlarge (L4) / g6e.2xlarge (L40S) | ~$0.98 / $2.24 per hour |
| Shadow PC | €32.99–49.99/month |

GPU prices inflated (memory shortage). Windows + RTX: Epic's main platform, HW RT/MegaLights/Nanite production-grade on DX12, DLSS 4.5, Live Coding, can package Windows + Linux servers; Windows = 93.95% of Steam (macOS 2.14%). Cloud g6e 160 h/month ≈ $360 → an RTX 5080 PC pays back in < 1 year.

## 8. External SSD & 16 GB tuning
- 2× TB4/USB4 ports. OWC Express 1M2 (USB4) ~3.2 GB/s; OWC Express 1M2 80G (TB5) 3.8 GB/s on TB4. Use a 2 TB PCIe 4 NVMe with DRAM cache.
- Zen/DDC can live on the external drive (Editor Preferences → General → Global, or env `UE-LocalDataCachePath`); keep projects there too.
- 16 GB settings: project `Config/Mac/MacEngine.ini` → `[TextureStreaming] PoolSizeVRAMPercentage=0` + `r.Streaming.PoolSize=2000`; Nanite streaming pool default 512 MB; `[DevOptions.Shaders] NumUnusedShaderCompilingThreads=5` (≈5 workers); `r.RayTracing=0` (SW Lumen); editor viewport 50–67% res; "Use Less CPU when in Background"; cap MetaHuman textures 2–4K; close Xcode/browser while working.

## Verdict
Realistic on the Air: learning 5.8, BP & C++ gameplay, ship interior greybox, small lit scenes (Nanite, VSM, SW Lumen, TSR) ~30 fps near 1080p, MetaHuman authoring, offline audio→face, PIE dedicated-server networking prototypes.
Not realistic: look-dev at target photoreal quality, HW RT & MegaLights (experimental on Mac), large Chaos+Niagara battles, MetaHuman crowds, planet landings with volumetric clouds at playable fps, dedicated server/source builds, Windows packaging, Live Coding.
**Disk is the first bottleneck (55 GB free), RAM the second.**

Recommended path: (1) now: 2 TB USB4 SSD; stay on 5.8.3 + Xcode 26.2. (2) minimum viable: Windows desktop 8–12 cores, 64 GB, RTX 5070 Ti/5080, 2+4 TB NVMe ≈ $2.5–3.2k. (3) ideal: 16 cores, 128 GB, RTX 5090 ≈ $6–7k. (4) Mac-only: Mac Studio M5 Max 64 GB+ (faster, but no DLSS, no stable HW RT/MegaLights, no Windows/Linux packaging).

## Sources
UE 5.8 announcement & release thread; GamesBeat; UE 5.8 release notes; 5.8.2/5.8.3 hotfix threads; Tom Looman 5.7/5.8 perf highlights; CG Channel 5.8; Epic macOS requirements 5.8; hardware specs; features by rendering path; Epic macOS parity blog; LocketGoma/MetalFX; StraySpark M5; Metal Toolchain fix; macOS 26/Xcode 26 thread; Live Link Hub Mac thread; rambod.net Mac mini M4 UE5 benchmark; Notebookcheck MBA 15 M4; Apple support specs; MetaHuman 5.7/5.8 notes, LOD specs, audio-driven animation; 80.lv MetaHuman crowds; MetaHuman perf reference (medium); server targets thread; source build disk guides; Apple newsroom Sept 2026; MacRumors; AppleInsider; Wikipedia Apple M5 & RTX 50; PassMark; Steam HW survey; AWS G6; vantage.sh; Shadow; Paperspace; Vast.ai; OWC Express 1M2 / 80G; UE DDC docs.
