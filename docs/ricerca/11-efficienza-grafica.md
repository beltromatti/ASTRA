# Research 11 — Efficient photorealism on UE 5.8.3 / M4 Air (2026-09-27)

**[L]** = confirmed in local engine source at /Users/Shared/Epic Games/UE_5.8. UNVERIFIED = estimate/not confirmed.

## 1. How shipped space games look photoreal cheaply
| Technique | What games do | ASTRA in UE |
|---|---|---|
| Lighting | EVE: one star + backdrop light; 68 region nebulae; "most ships … reflect the nebula"; standard PBR since 2014 | one shadowed directional (star) + one SkyLight captured once from the HDR cubemap; **no Lumen in open space** (post-process volumes switch GI method per area) [L] |
| Star field | Elite builds skybox from its galaxy model seeded with Hipparcos/Gliese | NASA Deep Star Maps 2020 (EXR ≤64K, 1.7 bn stars) → 4K/face cubemap; brightest stars as ≥1 px sprites (no shimmer) |
| Nebula volumes | EVE authors volumetrics in EmberGen | on M4: pre-rendered flipbooks on cards, 2–3 parallax layers, Niagara dust near camera; heterogeneous volumes already off at Effects ≤1 [L] |
| Atmospheres | Bruneton LUTs; Hillaire 2020 (= UE SkyAtmosphere, ground↔space) | from orbit UE ray-marches per pixel [L] → `r.SkyAtmosphere.SampleCountMax` 16–32 in orbit; clouds as 2D layer on planet; VolumetricCloud only during entry |
| Planet surfaces | Elite: cube-sphere quadtree, GPU noise, doubles, Wang tiling + triplanar, per-patch baked lighting; NMS voxel continuous generation | phase (c): WP, LWC, RVT |
| Ship detail | EVE remastered frigates ~1.2k → ~70k polys | Nanite hulls, trim sheets, tiling detail & dirt masks, DBuffer damage decals; window lights = emissive masks with per-window random flicker (not real lights) |
| Fleets | EVE GPU-driven pipeline +10–30% FPS (1,000-ship test on M1 Max 34→43 fps) | Nanite instances, Instanced Actors/Mass, Niagara mesh particles for fighters/projectiles; ImpostorBaker (exp., in 5.8) [L] for far ships → glow sprites |
| GI budget | Everspace 2: precomputed GI + SSGI, skipped Nanite/Lumen initially ("better optimization"), Lumen optional later; ships on Switch 2, Steam Deck Verified | space: SkyLight + SSAO/DFAO; interiors: Lumen Lite |
Post stack: physically based sun (~128k lux at 1 AU) with fixed EV per zone, blended at interior/exterior transitions; ACES filmic; Gaussian bloom (not convolution); image-based lens flare; light grain/vignette/CA; Local Exposure so bright screens don't blow out.

## 2. UE 5.8 on M4 — lighting & rendering
| GI option | Verdict |
|---|---|
| **Lumen Lite** (`sg.GlobalIlluminationQuality 1` + `sg.ReflectionQuality 1`; beta, ~2× faster than High) | **default for M4**: "Irradiance Field Gather" ("mid range PC and Switch 2"), 2048 lighting cache, SSR [L]; GI stays dynamic (breaches/fires change lighting) |
| Lumen High (`sg` 2) | M4 Pro/Max tier |
| Baked/hybrid | CPU Lightmass on Mac; GPU Lightmass Windows-only [L]; doesn't react to damage → static hangars/stations or Low tier only |
| MegaLights | production-ready in 5.8, docs don't list Mac; can run without HW RT [L]; high fixed cost → PC tier; if unused on Mac set `r.MegaLights.Supported=0` |
- Reflections: in Lumen Lite sharp reflections are SSR only, blended over blurry Lumen reflections; reflection captures not used as fallback [L] → large surfaces roughness ≳0.3; glass/visors/screens use a static cubemap in material; no planar reflections.
- VSM: moving/rotating lights discard cache; animated/WPO meshes re-render each frame; non-Nanite casters "much more expensive". Settings: `r.Shadow.Virtual.MaxPhysicalPages=2048` (~128 MB) [L]; local soft shadows `RayCountLocal=4`, `SamplesPerRayLocal=2`; `r.Shadow.Virtual.MarkCoarsePagesLocal=0` without volumetric fog. Rules: all hard-surface Nanite; alarm/flicker lights change intensity/color only, never move; rotating beacons = unshadowed spot + emissive cone mesh; small lights use contact shadows.
- Fog/smoke: shadow quality 2 gives volumetric fog 16 px / 64 slices [L]; damaged rooms → Local Fog Volumes + Niagara smoke.
- Nanite on Apple Silicon: SM6, M2+, macOS 15+; engine disables one faster culling path on Apple GPUs [L]. Helps: dense hulls, instanced asteroids, shadow cost. Hurts: WPO/masked materials, translucency, deforming meshes.
- Substrate: Mac defaults high-end (`ClosuresPerPixel=4`, `Glints=1`, `RoughDiffuse=1`) [L] → lower for M4 if used.
- TSR (costs more than it should on Apple Silicon per Epic): `r.ScreenPercentage` 60–67 @1080p; `r.TSR.History.ScreenPercentage=100`; `r.TSR.History.UpdateQuality=2`; `r.TSR.History.R11G11B10=1`; `r.TSR.Velocity.WeightClampingSampleCount=2`. Dynamic res works on Metal [L]: `r.DynamicRes.OperationMode=2`, frame budget, 50% floor.
- Mac project settings [L]: compile SM6 only (default builds SM5+SM6); HW RT on by default for Mac → turn off if not shipped; keep `r.Shaders.ZeroInitialise`/`BoundsChecking` unless measured otherwise; `rhi.Metal.CacheShaderPipelines=1` (memory for fewer hitches).
- Profiling on Metal: compute-encoder timing off by default (`rhi.Metal.SampleComputeEncoderTimings=0`) → set 1 when profiling (Lumen/Nanite/TSR/shadows are compute); bundled Xcode GPU Debugger plugin (`Xcode.CaptureFrame`/Shift+E → `Saved/XcodeGPUTraceCaptures`) [L]; `xcrun xctrace record --template "Metal System Trace"`; `MTL_HUD_ENABLED=1`; Unreal Insights `-trace=default,gpu,memory`. 5.8: `ProfileGPU` includes pipeline waits; `stat unit` shows VRAM budget.

## 3. Upscaling on Mac
- **MetalFX temporal: feasible, medium effort.** No UE integration; MetalFX headers bundled (spatial/temporal only) [L]. Hook = same slot as DLSS/FSR/XeSS: implement `UE::Renderer::Private::ITemporalUpscaler`, register via `SetTemporalUpscalerInterface()` from an `ISceneViewExtension` [L] (gets color, depth, velocity, jitter, exposure). Metal access via `IMetalDynamicRHI::RHIGetDevice()`, `RHIRunOnQueue()`, `GetNativeResource()` [L]. Work: UE velocity → pixel motion + camera motion, history reset on cuts, MetalFX reactive mask for particles. Community plugin LocketGoma/MetalFX (MIT, alpha v0.4, 3×/axis max, mode change needs restart). Effort 2–4 engineer-weeks (UNVERIFIED).
- MetalFX frame interpolation (`MTLFXFrameInterpolator` macOS 15+, `MTL4FXFrameInterpolator` 26+): needs temporal scaler first, writes back buffer, own present-pacing thread; Apple recommends ≥30 fps base; needs Metal RHI present changes → source build (1–2 months, UNVERIFIED).
- Expected gains (UNVERIFIED): MetalFX @50% vs TSR @67% ≈ 20–30% of resolution-bound GPU time; interpolation ≈1.6–1.9× displayed fps (no latency benefit). M5 Pro/Max neural accelerators not on M4.
- FSR RHI backend fails to load on macOS (port UNVERIFIED); FSR 4 needs RDNA4; XeSS plugin Windows-only; DLSS NVIDIA-only.
- **Recommendation: ship TSR + dynamic resolution; prototype MetalFX temporal as stretch goal.**

## 4. Memory budget (16 GB unified)
UE treats 75% RAM (12 GB) as VRAM; `r.Streaming.PoolSize=-1` → 70% (~8.4 GB); scalability normally 400–1000 MB [L] → always set pools explicitly.
| Item | M4 Air game budget |
|---|---|
| macOS + background | ~3.5–4 GB (UNVERIFIED) |
| Game process peak | ≤ 9 GB (fail > 9.5 GB) |
| Texture streaming pool | 1,200 MB (2,000 on M4 Pro/Max) |
| Nanite streaming pool | 384–512 MB (default 512) [L] |
| Shadow page pool | 2048 pages ≈128 MB [L] |
| Lumen Lite cache | 2048 atlas [L], tens of MB (UNVERIFIED) |
| Render targets @1080p | 0.6–0.9 GB (UNVERIFIED) |
| MetaHumans | Mac hair cards, LOD0 max; 2K hero / 1K crew; ≤2 heroes (~150–300 MB each, UNVERIFIED) |
Editor stability: `r.ShaderCompiler.MemoryLimit=3072`; don't cook during PIE; 5.8 memory-maps asset registry & strips unused default material textures.

## 5. ASTRA performance architecture
**Targets (M4 Air after 10-min heat soak, 1080p output, 60–67% internal):** space 60 fps (16.6 ms); interiors 60 goal / 45 floor (p95 ≤ 22.2 ms); GT & RT ≤ 8 ms each; non-Nanite draws ≤ 2,000.

GPU budget (ms, UNVERIFIED):
| Pass | Interior | Space |
|---|---|---|
| Nanite/base/velocity | 3.5 | 4.0 |
| Shadows | 2.0 | 2.0 |
| Lumen Lite+SSR / SkyLight+AO | 3.0 | 0.7 |
| Direct lights | 1.5 | 0.8 |
| Sky/backdrop | 0.3 | 1.0 |
| Translucency/Niagara/fog | 2.0 | 3.0 |
| TSR + post | 2.5 | 2.5 |
| UI/misc | 0.8 | 0.8 |
| **Total** | **15.6** | **14.8** |

Interior rules: ≤4 shadowed local lights in view (spot/rect, not point), ≤24 unshadowed, ≤3 overlapping any pixel, tight radii; screens = emissive, ≤1 rect light per console bank; fires = Niagara GPU sprites lit by translucency lighting volume, ≤3 full-screen layers, 1 flickering unshadowed light per fire cluster; breach debris Nanite → once settled set Shadow Cache Invalidation Behavior = Static; ≤40 decals in view.
Space rules: 1 shadowed directional; ≤300 simulated fighters (full mesh near, impostor from ~1.5 km, glow sprite from ~5 km); projectiles = GPU sprites/ribbons, no lights; ≤8 explosion lights at once, ≤0.5 s each; ≤50k GPU / 5k CPU particles; SkyAtmosphere samples ≤32 in orbit; no volumetric fog.

Scalability tiers:
| | A: M4 Air 16 GB | B: M4 Pro/Max | C: high-end PC |
|---|---|---|---|
| Output/res | 1080p, 60–67% dynamic | 1440p, 67–75% | 1440p–4K w/ DLSS/FSR/XeSS/TSR |
| GI/refl | 1/1 (Lumen Lite + SSR) | 2/2 | 3/3 HW RT |
| Shadows | Q2, 2048 pages | Q3 | Q3 + MegaLights interiors |
| Texture pool | 1.2 GB | 2–3 GB | 3 GB+ |

Automated perf loop (agent-runnable):
1. Build: `RunUAT.sh BuildCookRun -project=ASTRA.uproject -platform=Mac -clientconfig=Test -build -cook -stage -pak -archive`
2. Scenarios: Level Sequences for bridge, corridor fire/breach, engineering, hangar, fleet battle, orbit; perf GameMode or Epic **AutomatedPerfTesting** plugin (exp., in 5.8) [L]: `RunUAT AddAutomatedPerfTestToProject -Project=…` → BuildGraph + `RunLocalTests.sh` (perf, memory, Insights).
3. Run: `ASTRA /Game/Perf/L_Bridge -game -ResX=1920 -ResY=1080 -windowed -unattended -LLM -LLMCSV -csvGpuStats -csvMetadata=Scenario=Bridge -ExecCmds="r.VSync 0,t.MaxFPS 0,rhi.Metal.SampleComputeEncoderTimings 1"` then `CsvProfile exitoncompletion` + `CsvProfile frames=3600`; A/B in one run: `-csvABTest="r.ScreenPercentage=60,67" -csvABTestSwitchDuration=600` [L].
4. Parse `Saved/Profiling/CSV` with Python (PerfReportTool not in launcher build; CSVTools source-only) → p50/p95/p99 frame/GPU/GT/RT, per-pass GPU, peak LLM memory.
5. Gates: p95 within targets; frames > 50 ms ≤ 1/min; GT/RT p95 ≤ 8 ms; peak memory ≤ 9 GB; no VSM page-pool overflow (`r.Shadow.Virtual.Stats 1`); heat soak last-minute p50 ≤ 15% slower than first-minute; > 5% p95 regression vs baseline fails; on failure save Insights trace + `Xcode.CaptureFrame` of worst frame.

## Sources
Local: Engine/Config/{BaseScalability.ini, BaseEngine.ini, BaseDeviceProfiles.ini, Mac/BaseMacEngine.ini, Mac/DataDrivenPlatformInfo.ini}; Renderer/Public/TemporalUpscaler.h; MetalRHI (IMetalDynamicRHI.h, MetalRHI.cpp, MetalDynamicRHI.cpp, MetalRHIContext.cpp); MacPlatformMisc.cpp; Lumen.cpp; SkyAtmosphereRendering.cpp; MegaLights.cpp; DiffuseIndirectComposite.usf; Plugins XcodeGPUDebuggerPlugin, AutomatedPerfTesting, GPULightmass; CsvProfiler.cpp.
Web: Tom Looman 5.8 perf; UE 5.8 release notes; Lumen performance guide; VSM docs; MegaLights docs; TSR docs; Nanite docs; SkyAtmosphere docs; Epic macOS parity blog (snippets); LocketGoma/MetalFX; UE forum MetalFX; WWDC25 211; Apple game-porting-toolkit MetalFX frame interpolation skill; Apple Metal what's new; GPUOpen UE FSR3; UE forum FSR macOS; XeSS UE plugin; EVE (PBR, nebulae, more FPS for less CPU, Viridian in focus); 80.lv Elite Dangerous universe; Elite galaxy wiki; DSOGaming & UE interview Everspace 2; GamingOnLinux Everspace 2 final tech update (2026-09); GDC NMS continuous world generation; Hillaire EGSR 2020; Bruneton precomputed scattering; NASA SVS 4851; MetaHuman platform/LOD specs.
