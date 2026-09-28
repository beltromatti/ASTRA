# Research 10 — Crew characters & animation on budget 0 (UE 5.8.3, M4 16 GB) (2026-09-27)

## Main findings
1. **Blocker: MetaHuman Creator "Core Data" (optional content) is NOT installed** (`Engine/Plugins/MetaHuman/MetaHumanCharacter/Content/Optional` missing). The MetaHumanGenerator MCP toolset only registers when `is_optional_content_installed()` is true → enable Core Data in the Epic Launcher (UE 5.8 → Options).
2. **Assembling a MetaHuman needs Epic's cloud + an Epic account** (`CanBuildMetaHuman()` requires cloud face rig + downloaded high-res texture sources). Login via Epic account portal in a browser once, then remembered (`LoginUsingPersist`; persistence duration UNVERIFIED).
3. **Mac: hair = cards only** (no strands, no RT). 5.8 known issue: editor crash on Mac loading presets with HW RT on → `r.HairStrands.Raytracing 0`.
4. Best free animation base: **Game Animation Sample (GASP) 5.8** + Mixamo + free mocap datasets; gaps (welding, extinguisher, first aid) → video mocap on Apple Silicon (GVHMR fork) or Kimodo on a free cloud GPU.
5. **UE 5.8 AnimGen is NOT text-to-motion**: a neural movement controller trained on your own animation DB (training CUDA or slow CPU on Mac).

## 1. MetaHuman in 5.8 on macOS (Creator plugin Beta, Mac binaries; Animator face capture on Mac in 5.8; body capture Windows-only)
| Task | How (agent) | Cloud? |
|---|---|---|
| Create, basic body, skin tone, eye color | **MetaHumanGenerator MCP** (exp., off by default): `create`, `begin_edit`, `get/set_body_shape` (masc/fem, fat, muscularity, height 135–220 cm), `get/set_skin_tone`, `get/set_eye_color`, `end_edit` | no |
| Full body measurements | Python `MetaHumanCharacterEditorSubsystem.get/set_body_constraints`, `commit_body_state` | no |
| Face shape | `set_face_model_coefficients` (face PCA, new in 5.8), `translate_face_landmarks`, `import_from_identity/face_dna/template`, `conform_to_target_meshes` (5.8 Mesh-to-MetaHuman, any topology) | no |
| Skin/makeup/eyes | `commit_skin/makeup/eyes_settings` (local preview textures) | no |
| Hair & outfits | `internal_collection.try_add_item_from_wardrobe_item("Hair"/"Outfits", WI)` + slot selection + instance params (`PrimaryColorShirt`, `Melanin`…) | no |
| Face rig | `request_auto_rigging` (`JOINTS_ONLY` / `JOINTS_AND_BLENDSHAPES`, `blocking=True`) | **yes** |
| Texture sources | `skin_settings.desired_texture_sources_resolutions` (2k/4k/8k per map; default 2k) → `request_texture_sources` | **yes** |
| Assemble | `build_meta_human` (pipeline CINEMATIC/OPTIMIZED/UEFN; quality LOW–CINEMATIC; baked textures 256–8k) | local, after the 2 cloud steps |
Example scripts: `.../MetaHumanCharacter/Content/Python/examples/` (auto-rig, texture download, assembly, clothing, grooms).
LODs: head LOD0 24k verts / 669 blendshapes / 713 joints; LOD3 2.5k / 283 joints; LOD7 130 / 26 joints. Body 30.5k (LOD0) → 1.5k (LOD3). "UE Optimized" Medium = card hair. HairCardGenerator (exp.) runs on Mac (cards from strand grooms).
MetaHuman Crowd (exp.): Mass + Mover + SmartObjects + ChaosOutfitAsset; near = full actors; far = instanced skinned meshes (no post-process ABP → no correctives); hair → cards; high LODs removed; face/body anim baked to loops (`MetaHumanCrowdAnimationConfig`); sample on Fab; Mac/Metal UNVERIFIED; `MetaHumanCharacterUAF` editor module Windows-only.

## 2. Uniforms on budget 0
- 5.8 `ChaosOutfitAsset` (Beta): templates `OutfitAssetTemplate`, `MakeResizableOutfitTemplate`, `ResizeOutfitTemplate`; cloth nodes `SkeletalMeshImport`, `StaticMeshImport`, `USDImport`, `TransferSkinWeights`, `MeshWrap`, `Remesh`, `GenerateResizableProxy`, RBF resizing, sim config. Input paths: A FBX render mesh only; B USD from Marvelous/CLO (paid); C render mesh + hand-made sim mesh.
- Agent tools: **DataflowAgent MCP** builds the outfit graph (`CreateDataflowCompatibleAssetFromTemplate`, `AddNode`, `ConnectNodePins`, `SetVariable`); ChaosClothAssetToolset (6 tools) only attaches/converts cloth.
- Gap: `TryAddItemFromPrincipalAsset` not exposed to Python → need a Wardrobe Item asset: duplicate `WI_DefaultGarment` and repoint `PrincipalAsset`, or write a small C++ editor wrapper (both UNVERIFIED).
- Free starting assets: Epic **MetaHuman Clothing Construction Presets, Set of 4** (free on Fab; 4 body presets + FBX for 4 sizes; if FBX import scrambled → `Interchange.FeatureFlags.Import.FBX 0`); Core Data default garment (color param) + stock hairstyles. No free sci-fi MetaHuman outfit found (Techwear/Sportswear/MetaWardrobe prices UNVERIFIED; free Paladin set until 2026-10-06).
- **Blender recipe (free, headless):** copy neck-to-wrist/ankle faces of preset body → push out 3–6 mm, Solidify for collars/cuffs, loop-cut seams → boots/belt/insignia as separate skinned parts → reuse body UVs, bake 2k normal+AO from procedural detail → RGB department mask (primary panel, secondary, trim) → UE import path A → `TransferSkinWeights` from MetaHuman body → resizable outfit → department color/insignia via material params. Sim mesh only for coats/fire jackets; straps/hems via 5.8 Control Rig Dynamics (exp., ~5× cheaper than Chaos Cloth per Epic). Fabric textures Poly Haven/ambientCG.

## 3. Free animation sources
| Source | Licence | Access | Use |
|---|---|---|---|
| **GASP 5.8** (Epic, Fab) | Epic/Fab terms | UEFN mannequin anims + motion-matching DBs | 500+ anims; 5.8 adds physics ragdoll (fall protection, injury, flail, roll, motion-matched recovery), bench sitting via Smart Objects + StateTree, multi-character pose-search interactions, look-at solver (exp.); on MetaHumans via runtime retarget (`ABP_GenericRetarget`, tag `RTG_UEFN_to_Metahuman_nrw`) |
| **Mixamo** | free, royalty-free, Adobe ID | FBX; bulk scripts use browser `access_token` | typing, sitting, salute, kneel, carry, injured, scared, talking (names UNVERIFIED); unmaintained, 2025 outages; bulk scraping may break ToS |
| CMU | free incl. commercial, no resale | BVH (cgspeed), FBX (HF) | 2,548 clips everyday actions/pantomime |
| Bandai Namco | CC BY-NC 4.0 | BVH | daily acts, hand actions, walking styles |
| LAFAN1 | CC BY-NC-ND 4.0 | BVH 30 fps, 4.6 h | fall/get up, push & stumble, crawl, aiming |
| 100STYLE | CC BY 4.0 | BVH | 100 walking styles |
| Quaternius UAL | CC0 | FBX/GLB 120+ | sit, push, crouch (less realistic) |
| ActorCore/Rokoko | account; terms UNVERIFIED | FBX | supplementary |
| BONES-SEED | academic/startups only | — | not usable |
Retargeting: UE 5.8 auto-builds retarget rigs for Mixamo, UE4/UE5 mannequin, Rigify, Rokoko, Xsens, HumanIK, Daz, CC4, Meshcapade… (local source); batch via Python `IKRetargetBatchOperation.run_batch_retarget`. No free clips found for welding, extinguisher, bandaging/CPR, bracing against a console.

## 4. AI-generated & video-captured motion
| Tool | Output | On M4 16 GB? | Licence |
|---|---|---|---|
| **UE AnimGen** + Fab "AnimGen Example" | runtime controller (Idle, TrajectoryFollow, MoveToTarget, TrajectoryInteraction, Tagged styles) | inference on CPU (Mac binaries); training CUDA or very slow CPU | Epic |
| MoMask | BVH (foot IK opt.) | yes, CPU; HF Space on CPU | code MIT; model trained on research-only data |
| **Kimodo** (NVIDIA, Mar 2026) | NPZ for SOMA/G1/SMPL-X; text, keyframes, hand/foot targets, paths | no (~17 GB VRAM; <3 GB with text encoder on CPU) → free Kaggle/Colab GPU | **SOMA weights: NVIDIA Open Model License (commercial OK)**; SMPL-X weights R&D-only |
| HY-Motion 1.0 (Tencent) | SMPL-H → FBX | no (24–26 GB VRAM) | licence excludes EU/UK/KR |
| EMAGE | speech → body+hands+face; BVH script | HF Space/Colab | UNVERIFIED |
| **GVHMR** (Apple Silicon fork `westnt/gvhmr-pr`) | video → SMPL-X | yes, except CUDA-only DPVO camera module | non-commercial; SMPL/SMPL-X registration |
| SAM 3D Body (Meta) | image → body mesh | per frame + smoothing (UNVERIFIED) | MHR rig permissive commercial |
SMPL → MetaHuman: NPZ→FBX in Blender (or MoMask BVH) → rename joints to Mixamo/UE names → UE auto retarget rig → batch retarget → cleanup (foot lock, hand poses — training data lacks fingers, root motion).

## 5. Procedural/physics animation (fewer clips)
| Need | UE 5.8 system |
|---|---|
| Walking on a tilting deck | Motion Matching (PoseSearch) + Chooser, stride/orientation/slope warping, Mover (exp.) |
| Hits, shakes, falls, bracing | **PhysicsControl**: partial upper-body physics on jolts; full ragdoll + recovery on heavy hits (GASP 5.8); brace = Chooser pose + FBIK hands to nearest handhold |
| Console sitting/typing, panel repair, extinguisher, med bay | **Smart Objects + StateTree** (enter/loop/exit) aligned by **Motion Warping** (Beta); typing = seated loop + Control Rig hand IK to key targets with noise & finger curl |
| Two-person actions (wounded care, salutes) | Pose Search Interaction assets; ContextualAnimation (exp.) |
| Talking gestures | nothing built-in for body (audio-driven anim is face-only) → lip-sync energy/pitch peaks drive Chooser upper-body beat gestures + Control Rig nods/look-at; optionally bake EMAGE clips per scripted line |
MCP helpers: StateTreeToolset (crew task logic), PhysicsToolsets (bodies/constraints), AnimationAssistantToolset (Control Rig keying in Sequencer + FBX I/O; 5.8 Sequencer auto-bake → hand-key a salute and bake it).

## 6. Recommended pipeline
1. Setup: install Core Data; enable MetaHuman Creator, MetaHumanGenerator, ChaosOutfitAsset, DataflowAgent, PoseSearch, Chooser, MotionWarping, PhysicsControl, SmartObjects, StateTree; `r.HairStrands.Raytracing 0`.
2. Crew roster YAML (name, dept, rank, age, build) → MCP body/skin/eye tools → Python seeded face coefficients (≈±2σ, safe ranges UNVERIFIED), hair, makeup.
3. Uniforms: one per department in Blender → UE path A → resizable outfit via DataflowAgent → Wardrobe Item; per crew: outfit slot + dept/rank color params.
4. Cloud & build: auto-rig `JOINTS_ONLY` (blendshapes only for hero faces), textures at tier resolution → `build_meta_human(OPTIMIZED, tier)` → screenshot + profile.
5. Animation: GASP base (retarget offline to MetaHuman skeleton, rebuild pose-search DBs) + Mixamo/LAFAN1/Bandai/100STYLE task clips; gaps: GVHMR video mocap → Kimodo (SOMA) → MoMask drafts; single retarget + Control Rig cleanup pass.
6. Behavior: StateTree crew jobs over Smart Objects; ship-hit event → brace/stagger/fall by intensity & distance; procedural gaze & gestures.

Runtime tiers on M4 (estimates; profile a 10-min sustained run):
| Tier | Who | Build | Textures | Face/anim |
|---|---|---|---|---|
| T0 | ≤3 speakers/close-ups; comms captains via scene capture ≤720p @30 Hz | Optimized Medium (cards) | face 4k, rest 2k | full face rig |
| T1 | ≤10–12 named crew in view | Optimized Medium/Low | 2k face, 1k body | JOINTS_ONLY, LOD sync, anim budget allocator; cloth off beyond ~5 m |
| T2 | background crew | Optimized Low → MetaHuman Crowd (fallback shared loops / AnimToTexture) | ≤1k | baked loops, no live face |
Texture pool ~1.5–2 GB.

One-time human actions: Epic (enable Core Data in Launcher; sign in once in UE for MetaHuman cloud; claim free Fab items GASP, AnimGen Example, MetaHuman Crowd sample, Clothing Construction Presets); Adobe ID for Mixamo (browser session/access_token); Hugging Face account + token; SMPL & SMPL-X registrations (MPI) for GVHMR / SMPL-X Blender add-on; optional Kaggle/Google (free GPU for Kimodo), Reallusion/Rokoko.

## Sources
MetaHuman 5.8 release notes & announcement; MetaHuman Crowds docs + Fab sample; Creator getting started; platform & LOD specs; known issues 5.8; hair strands on Mac thread; UE 5.8 release notes; CG Channel 5.8; wardrobe items; parametric clothing; Clothing Construction Presets (forum + Fab); Fab free rotation (zerotobeast); GASP 5.8 (projprod, Fab) + GASP with MetaHuman docs; auto retargeting docs; Mixamo status (cinevva) + MixamoHarvester; Bandai Namco dataset; LAFAN1; 100STYLE (Zenodo); CMU cgspeed; Quaternius UAL; BONES-SEED; AnimGen tutorial + Fab example; HY-Motion (+licence); Kimodo (GitHub, arXiv 2603.15546, kimodo.cpp); MoMask; EMAGE (PantoMatrix); GVHMR (Apple Silicon fork + licence); SAM 3D Body. Local: MetaHumanGenerator metahuman.py; MetaHumanCharacter Python examples; MetaHumanCharacterEditorSubsystem.cpp (CanBuildMetaHuman); MetaHumanCharacterEditorModule.cpp (optional content); MetaHumanCloudAuthentication.cpp; MetaHumanCrowd; ChaosOutfitAsset; Toolsets (ChaosClothAssetToolset, DataflowAgent, AnimationAssistantToolset, PhysicsToolsets); Experimental/Animation/AnimGen; IKRigAutoCharacterizer.cpp.
