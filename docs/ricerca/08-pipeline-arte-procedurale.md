# Research 08 — ASTRA art pipeline: procedural hard-surface, texturing, AI assist (2026-09-27)

## 1. Procedural hard-surface modeling in Blender 5.2 (all headless-scriptable)
- **Hulls:** spine curve + 5–12 cross-section profiles → loft (`bmesh.ops.bridge_loops`, GN "Curve to Mesh", or sampled grid); 5.2 adds NURBS order/weight nodes. Softer industrial shapes: creased subdivision cage → apply → cut. Mirror by default.
- **Cuts/panel lines:** Boolean modifier with **Manifold** solver (4.5+; fast/robust; inputs must be manifold). Panel seams as real geometry (`inset_region` + 1–3 cm push, or thin cutter strips) — free on Nanite.
- **Edges/normals:** Blender 5.2 **Mesh Bevel node** (fully procedural bevels in GN) or Bevel modifier (angle-limited, 2–3 segments on silhouette edges, 1 elsewhere, Harden Normals) → Weighted Normal (Keep Sharp) + Smooth by Angle. `use_auto_smooth` and `bgl` gone in 5.x (breaks old add-ons).
- **Greebles/plating:** GN face selection (attribute/noise/vertex group) → Extrude Mesh + Scale Elements; instance on points from a kit collection, normal-aligned, 3-tier size hierarchy; keep instances unrealized and export transforms as JSON → UE ISM (never bake into hull). GN-based Array modifier (5.0) for radial engine/radiator arrays.
- **Modular interiors:** parametric kit on 0.5 m grid; modules 2/4/8 m; doors ~1.2×2.2 m; corridors ≥2.4 m wide, ~3 m high; pivots on grid corners; empties as sockets for lights/props/decals.
- **Trim-sheet UVs:** script assigns strip faces (loops along bevels) to trim rows (V = row band, U = world length × texel density); big flat faces cube-projected at fixed density: ~512 px/m exteriors, ~1024 px/m interiors.
- LL3M (2025): LLM agents writing Blender code + critiquing their renders is a viable modeling approach (= ASTRA's approach).

| Tool | Licence | Headless? | Blender 5.x? | Verdict |
|---|---|---|---|---|
| bpy / bmesh / Geometry Nodes | GPL | yes | yes | **primary** |
| Extra Mesh Objects 0.4.1 | GPL-3 | yes (ops) | 4.2+ | pipes, gears, beams |
| Bool Tool 2.1 | GPL-3 | needs UI | 4.5+ | not needed |
| MACHIN3tools | UNVERIFIED | no | ≤4.5 listed | skip |
| Sverchok | GPL-3 | UNVERIFIED | 5.1 listed | optional |
| Tissue 0.3.71 | GPL-2+ | yes | issues on 5.0 | optional |
| SpaceshipGenerator (a1studmuffin / ldo fork) | MIT | yes | ≤3.1 | **port algorithm (~300 lines bmesh) as seeded blockout generator** |
| TexTools | GPL (UNVERIFIED) | ops | 5.x UNVERIFIED | texel density, bakes, trim wrap |
| Texel Density Checker 2026.1.1 | GPL-3 | ops | 4.2+ | validation |
| DeepBump | GPL | CLI (ONNX CPU) | add-on | normal/height from image |
| Material Maker 1.5 | MIT | CLI `--export-material --target Unreal` needs GPU context (no `--headless`); macOS CLI UNVERIFIED | n/a | tileable procedural PBR |
| ArmorPaint/ArmorLab | source open, binaries paid | no | n/a | skip |
| UE Texture Graph 5.8 | engine | BP nodes; Python UNVERIFIED | n/a | fallback: material → render target → export |
Kitbash raw material you can ship: NASA 3D Resources (US gov, no copyright; strip insignia), Smithsonian Open Access CC0 (e.g., Apollo 11 CM). Quaternius/Kenney CC0 low-poly → blockouts/scale only.

## 2. Texturing on budget 0
- Shared fleet library: two 4K **trim sheets** (hull, interior) baked in Cycles (Metal) from procedurally modeled high-poly strips (normal, AO, height, curvature, ID); ~12 tiling 2K materials (ambientCG, Poly Haven CC0 + Material Maker graphs); 3–4 tiling 1K detail normals; one 4K RGBA **decal atlas** (stencils, labels, hazard stripes, leaks, scorch) from **3DTexel CC0 decals (280+)** + our generated vector graphics.
- Unique data without unique textures: bake AO/curvature/cavity to **vertex colors** on dense Nanite meshes (Cycles bakes to color attribute); 1–2K UV1 mask only for low-density meshes.
- UE master materials: `M_Hull` (4 tiling layers by vertex color/ID; detail normal via BlendAngleCorrectedNormals; world-space macro noise vs tiling; edge wear & dirt from vertex color; paint/faction tint params; emissive by ID) + `M_Trim`, `M_DecalDBuffer`, `M_Glass`, `M_Emissive`; everything else = material instances.
- Decals: **DBuffer projected decals** (Nanite-compatible; mesh decals are not). POM only on flat inserts (grates) or non-Nanite parts. RVT = terrain tool, skip for ships.
- EVE-style channel packing: BaseColor+Roughness BC7; normals BC5; AO/Metal/Height/Mask linear BC7.

## 3. AI assistance
| Option | Access | M4 16 GB? | Cost/speed | Value |
|---|---|---|---|---|
| **OpenRouter image models** (`POST /api/v1/images`; 52 models as of 2026-09-11) | paid API | n/a | gpt-image-2 $0.006–0.0135 (high ≈35×); FLUX.2 pro $0.03/MP, max $0.07/MP (seeds); Seedream 5 lite/pro $0.035/$0.09 @2048²; Gemini 3 Pro Image $0.134 (≤14 reference images); Recraft v4.1 vector $0.08 (SVG) | **high**: concept frames, orthographic turnarounds, insignia/decal SVGs, grime masks, nebula skyboxes |
| TRELLIS.2 (4B) | MIT (+DINOv3 gated, RMBG-2.0 CC BY-NC → feed pre-masked RGBA) | trellis2mlx validated on 16 GB M2 Pro, ~21 min/textured GLB | free | medium: props/greeble raw shapes after cleanup; "melted" edges → never hero hulls |
| Hunyuan3D 2.1 / 2mini | Tencent licence excludes EU/UK/KR | MPS port (~6 min shape on 24 GB M4 Pro) | free | avoid if EU-based |
| SF3D / SPAR3D | Stability Community | MPS experimental; 32 GB rec. | fast | low |
| TripoSG (MIT) / Step1X-3D (Apache) | open | CUDA only | HF Spaces | low–medium |
| HF ZeroGPU via `gradio_client` | account + token | n/a | 2 min anon / 5 min free / 40 min PRO per day | occasional full-res TRELLIS.2 |
| Meshy/Tripo/Rodin free tiers | no API on free | n/a | Meshy 100 credits/mo CC BY 4.0 | not automatable → skip |
| **StableMaterials** | OpenRAIL | yes (MPS) | 512² tileable | full PBR set from text/image |
| CHORD (Ubisoft) | research-only | CUDA | — | don't ship |
| Real-ESRGAN via upscayl-ncnn (arm64/MoltenVK) | AGPL backend | yes | fast | upscale albedo/decals (not normals) |

## 4. EVE / Star Citizen / Everspace 2 lessons
- **EVE (Trinity):** 3 packed textures per hull (albedo+rough; normal XY+AO; paint/glow/dirt/material-ID); 4-material shader selected by greyscale ID map (no material splits); capitals: tiled primary UVs + secondary unique UV for AO only; vertex color for damage/dirt; projected decals for hull breaches; separate paint masks (cheap faction variants/skins); an old hull shipped with 2×1024² + 1×512².
- **Star Citizen:** one master material (~25 sub-materials); exterior tiling ~512 px/m, few UV shells; trims baked from high-poly strips; POM decal "floaters" for split lines/vents/panels; vertex color for wear & burn; ships assembled at runtime from functional pieces (variants, per-piece damage & LODs).
- **Everspace 2:** modular hulls/wings/engines/cockpits; per-pixel detail from floaters, decals, emissives.
- **ASTRA rules:** no unique textures on big hulls; one master material with mask-selected layers; unique info in vertex color or low-res UV1 mask; panel lines as geometry on Nanite heroes, trims/POM floaters elsewhere; wear/damage via masks; livery via material params; ships from functional modules; strict PBR ranges, no shader hacks.

## 5. Blender → UE 5.8 on M4
- Mac: Nanite/VSM/MegaLights/HW Lumen need M2+ and are experimental/beta on Mac; fanless Air throttles → never run Cycles bakes and UE editor simultaneously.
- Nanite ≈14.4 bytes/triangle on disk (1M tris ≈ 14 MB). Capital ship ≤10–20M unique tris split into ≤1–3M modules; greebles/windows/antennas as instances. Fighters 100–300k tris; drones 20–60k. Keep modules mid-poly with real bevels so a near-full-res fallback stays affordable if Nanite is off on Mac.
- Nanite yes: opaque/masked static hulls, interiors, kit parts. No: glass (translucent), mesh decals, WPO-deformed parts. ≤4–6 material slots per module.
- Normals: triangulate + export custom normals (FBX "normals only"); UE import "Import Normals" + MikkTSpace; don't bake bevels into normals.
- Collision: author simple collision (UCX_/UBX_), box sets per module for walkable interiors (complex collision uses coarse Nanite fallback).
- LOD/fleets: Nanite replaces LODs; non-Nanite parts auto-LOD; distant fleets = Nanite instances; very distant = emissive sprites. Nanite Assemblies experimental (foliage-oriented) → watch, don't depend. PCG (production since 5.7) + Geometry Script for in-editor dressing.
- Validation: Blender pre-export script + UE Python validators (`EditorValidatorBase`) on every import (tris, slots, Nanite flag, collision, UV count, texture size/compression, naming).

## 6. ASTRA art pipeline (end to end)
1. `specs/<asset>.json` (class, dimensions, faction language, palette, budgets, seed).
2. Concept (`concept.py` via OpenRouter): 4 seeded FLUX.2 frames; orthographic side/top/front sheet via Gemini 3 Pro Image w/ references; decal SVGs via Recraft (~$0.5–2/asset).
3. Blockout (`blender -b -P blockout.py -- spec.json`): spine/loft grammar + modules; render 6 ortho + 3 perspective silhouettes (EEVEE) → visual critique vs concept → iterate.
4. Forms/detail: Manifold booleans → Mesh Bevel/Bevel → Weighted Normal → panel insets/plating → greeble scatter → `instances.json`.
5. Interiors: kit generator on 0.5 m grid → room-graph layout (`layout.json`) with light/prop sockets.
6. UVs/masks: trim/cube UVs at target density; Metal device; bake AO/curvature/cavity to color attributes (or UV1 masks).
7. Material library: trim bakes, Material Maker exports, CC0 tileables, decal atlas, channel-packing script.
8. Blender validation (tris, n-gons, non-manifold, applied transforms, texel density ±15%, slots, naming, UCX present) → JSON report; failures block export.
9. Export FBX/glTF per module + `instances.json`, `decals.json`, collision meshes.
10. UE import (Python/Interchange): Nanite flags, material instances, spawn ISMs & decals from JSON, run validators.
11. Capture: fixed lighting presets (hard sun w/ dark side, rim, interior); camera rig at 2 m / 50 m / 1 km; high-res screenshots + `stat gpu`.
12. Self-review vs checklist → fix list → loop to step 4/6/7; commit when all pass.

## 7. Self-review checklist
- Silhouette readable & faction-identifiable as black shape at 1 km; primary/secondary/tertiary ≈60/30/10 with rest areas.
- Scale cues (windows, hatches, lights, labels, handrails) at human scale; detail density matches size (no "toy" look).
- Edges: bevel highlights at mid-distance; no shading gradients on flat faces.
- Materials: roughness variation everywhere; albedo in PBR range (non-metals ~30–240 sRGB); no plastic look; tiling invisible at all 3 distances.
- Decals: correct scale/orientation, readable, no stretching/z-fighting/floating.
- Lighting: hard key, deep shadows, AO in cavities; purposeful emissives (red port / green starboard nav lights); bloom not blown out.
- Interiors: correct door/ceiling/corridor sizes; trims aligned at seams; no light leaks; walkable collision.
- Technical: no seams/UV stretch; normal Y DirectX convention; textures streamed before capture; frame-time/tris/memory budgets met.

## Sources
SpaceshipGenerator (a1studmuffin; ldo fork releases); Blender extensions (Bool Tool, Tissue, Extra Mesh Objects, Texel Density Checker); MACHIN3tools; Sverchok; TexTools; GreebleGenerator; Blender 5.2 GN, 4.5 modeling, 5.0 Python API release notes; Material Maker CLI docs + 1.5 article + Material Maker MCP; armortools; UE Texture Graph docs; OpenRouter image models blog + image API announcement; TRELLIS.2, trellis2mlx, trellis-mac; hunyuan3d-2.1-mac port + Tencent licence; Stable Fast 3D; SPAR3D; Step1X-3D; HF ZeroGPU docs; Meshy free plan; Hyper3D pricing; Tripo free plan (costbench); StableMaterials; DeepBump; Ubisoft CHORD; upscayl-ncnn; arXiv 2508.08228 (LL3M); EVE news (V5++, Rubicon 1.1 art, Scorpion textures, PBR); 80.lv industrial design; Star Citizen ship pipeline comm-link; Everspace 2 Kickstarter post; UE Nanite docs/technical details/assemblies; UE macOS requirements; Tom Looman 5.8; EditorValidatorBase; PCG production-ready 5.7; 3dtexel decals; ambientCG; NASA-3D-Resources GitHub; Smithsonian 3D CC0; Quaternius modular sci-fi megakit; Kenney space kit.
