# Research 05 — Space-sim engineering in UE 5.8 (2026-09-27)

Facts marked **[local]** were verified in the installed UE 5.8.3 source/plugins. UNVERIFIED = could not confirm.

## 1. Universe scale & coordinates
- `UE_LARGE_WORLD_MAX` = 8,796,093,022,208 cm ≈ 88M km across (±44M km). Actors beyond ±HALF_WORLD_MAX get removed by world-bounds checks. Doubles stay 1/16 cm-precise to 5.6e14 cm (≈5.6 billion km, `UE_DOUBLE_HUGE_DISTANCE`) — the limit is the engine's, not double precision. [local EngineDefines.h, Actor.cpp]
- Rendering camera-relative with LWC tiles of 2,097,152 cm (~21 km); Niagara float relative to per-system LWC tile; Chaos uses double (FReal=double). [local]
- Origin rebasing is legacy: `UWorld::SetNewWorldOrigin` exists but the toggle shows only with World Composition; auto-rebasing follows local players' cameras (dedicated server never rebases); Chaos `SupportsOriginShifting()==false` → bodies teleported one by one. [local]
- Networking: packed vectors support LWC doubles; CMC replicates based movement relative to base (`FVector_NetQuantize100`). [local]
- Prior art: Star Citizen (64-bit, hierarchical zones = local frames per ship, nested physics grids, camera-relative rendering, object container streaming); Space Engineers (64-bit positions, 32-bit Havok clusters ≥20 km); Starship Simulator (UE5, 100-ly sectors of 1-ly cubes, never >0.5 ly from origin); KSP (floating origin + Krakensbane + scaled space); No Man's Sky (seed-regenerated hierarchy, GDC 2017).

**Recommendation:** own universe layer outside UE actors — frame tree: galaxy sector (int64³) → star system → body (rotating frame) → ship → room; every position = (frame id, double local offset), all nodes generated from the seed. Each UE server world = one **simulation bubble** (e.g., planet + orbit + fleet) within ~±1e6 km of origin; distant bodies = scaled impostors; re-center only at transitions (jumps, bubble split/merge). Cruise/warp → co-moving frame (ship near origin, far-field moves). Replicate transforms relative to their frame. Risks: materials using absolute world position; World Partition cells can't hold moving ships (ships = always-loaded actors); bubble handoff between servers.

## 2. Procedural planets, space → ground
- **Recommendation:** own cube-sphere quadtree terrain (CDLOD-style morphing chunks), generated from seed on GPU/worker threads, rendered with **RealtimeMeshComponent** (MIT core, UE 5.5–5.8; Pro on Fab advertises runtime Nanite builder — perf/Mac UNVERIFIED). Collision only near players, deterministic on server. Nanite for authored kits (rocks, buildings, ship parts) placed as instances.
- Stock Nanite can't be built at runtime in packaged games (NaniteBuilder editor-only; DynamicMeshComponent has no Nanite path). [local Engine.Build.cs]
- Voxel Plugin 2: $349/seat perpetual (custom license >$100k budget); docs target 5.6/5.7; 5.8/macOS/planets UNVERIFIED → only if caves/digging are core.
- Cesium for Unreal: custom ellipsoids (v2.7.0), Moon/Mars (v2.19.0), OriginShiftComponent, UE 5.8 support (v2.28.0); procedural needs local 3D-Tiles generator (UNVERIFIED) → reference architecture only.
- Mesh Terrain / Virtual Heightfield Mesh: experimental and planar; no sphere code in MeshPartition [local] → not for planets.
- PCG: `GenerateAtRuntime`, runtime scheduler, hierarchical grids, 3D cells (`bUse2DGrid` off) [local]; 5.8 adds GPU runtime scatter & complex attributes (street networks). Run PCG per terrain chunk in chunk-local space.
- Sky Atmosphere: seamless ground↔space with "Planet Center at Component Transform"; multiple simultaneous atmospheres "not currently supported" → move the single atmosphere to nearest planet; distant planets need custom ray-marched shell material. For space views: `r.SkyAtmosphere.FastSkyLUT 0`, `r.SkyAtmosphere.AerialPerspectiveLUT.FastApplyOnOpaque 0`. Volumetric Clouds: tracing mode 0 for ground↔space & flying through clouds.
- Entry FX: hull emissive from dynamic pressure (½ρv²), Niagara plasma sheath, heat distortion, camera shake.
- References: Starship Simulator (1:1 galaxy; seamless landings reportedly unlikely — UNVERIFIED), Cesium Moon/Mars, Arghanion's Flight System (free Fab template, UE 5.8, walk aboard/fly/land). Fab planet plugins not surveyed (UNVERIFIED).
- Risks: LOD cracks, server CPU for collision, float precision in terrain shaders (chunk-local noise).

## 3. Walking inside moving ships
- One FPhysScene per UWorld; AChaosSolverActor ≠ moving frame. [local]
- CMC: custom gravity direction, tick dependency on base, `ReplicatedBasedMovement`; 5.8 widens movement bases (`FMovementBaseInterfaceData`); based-rotation code comment assumes yaw-only. [local]
- Mover: still experimental in 5.8 (better based movement + Iris per notes); Network Prediction ticks before world tick groups → desync with ship moved in normal tick; ChaosMover README warns of poor results on moving non-physics objects. [local]
- Chaos Immediate Physics supports moving simulation space with tunable linear-accel/Coriolis/centrifugal/Euler factors. [local SimulationSpace.h]

**Recommendation — hybrid "kinematic hull":**
1. Capital ship = server-authoritative kinematic actor driven by our fixed-step flight model, ticked before characters, replicated with custom buffered interpolation; never a Chaos-simulated walkable base.
2. Characters = CMC based on hull, gravity = ship "down", control rotation stored ship-local; hits shown via scripted impulses + camera shake. Revisit Mover when out of experimental.
3. Loose props/bodies/debris inside = Chaos Immediate Physics in ship-local space, server-authoritative, replicate local transforms.
4. Cruise/warp = co-moving frame (§1).
5. "Pocket interior" only as fallback (conflicts with breaches, hangar launches, lighting; render targets expensive).
- Prior art: Star Citizen nested grids; Dual Universe local gravity per construct; orrery spike (CMC drift at 500 m/s); "physics subgrids" gist; LocalSimulation plugin (UE4/PhysX).
- Risks: base handoff (hangar → space → planet), smoothing remote players on rotating bases, server CPU for many based characters.

## 4. Destruction & damage
- Set pieces: pre-fractured Geometry Collections with `EnableNanite`; replication via `bEnableReplication`, `ReplicationAbandonAfterLevel`, `ReplicationMaxPositionAndVelocityCorrectionLevel` (only break state + coarse clusters over network); small debris cosmetic/client-only. [local]
- Unique hull holes: modular Nanite hull panels; on breach swap panel → `UDynamicMeshComponent` + Geometry Script `ApplyMeshBoolean` with seeded noise-displaced cutter (runtime-supported per Epic docs); replicate (panel id, seed, transform, radius); async collision (`bDeferCollisionUpdates`/`bUseAsyncCooking`). Keep panels small (dynamic meshes aren't Nanite).
- Look: decals + per-panel damage masks in render targets; Niagara sparks/smoke/fire; Niagara Fluids is Beta [local] → hero shots only. Decompression = custom movement mode + force volume; containment field = toggled volume; bulkheads = compartment graph.
- **MegaLights is Production-Ready in 5.8** (release notes), needs ray tracing; Mac `METAL_SM6` declares HW RT [local]; M4 perf UNVERIFIED.
- Risks: boolean cost on dense meshes, collision-rebuild hitches, Lumen/distance-field updates on edited meshes.

## 5. Large battles
- Mass Entity overhaul in 5.8 (Mass Signals in core, lock-free archetype scheduling, sparse fragments). MassGameplay (experimental): MassLOD, MassSimulationLOD, tick-rate control, MassRepresentation (ISM↔actor), MassReplication bubbles. [local]
- Rendering: Nanite instanced hulls/fighters, Niagara projectiles/impacts, Niagara Nanite renderer (experimental) for debris, Instanced Actors (experimental).
- Sim LOD: Tier 0 (<~10 km from a player) full actors+physics; Tier 1 Mass kinematic + analytic ballistics on server; Tier 2 fleet-level statistical resolution (seconds). Projectiles = server-side rays with travel time, never Chaos bodies.
- Risks: MassGameplay API churn; replication bandwidth → Iris prioritization + frame-relative quantization.

## 6. Multiplayer foundation
- Dedicated servers require a **source build** (Epic docs); Mac launcher install has no Linux platform [local] → build Linux servers in CI later (Mac cross-compile UNVERIFIED).
- Iris: "production-ready for licensees" per 5.8 notes but plugin flagged Beta and `net.Iris.UseIrisReplication` defaults 0 [local] → adopt from day one; Mover supports Iris in 5.8.
- World Partition server streaming exists, off by default (`wp.Runtime.EnableServerStreaming 0`) [local] → enable for planet cities.
- MultiServerReplication (experimental): server-to-server beacons + proxy merging several backends into one client world + player-controller migration [local] → Epic's building block toward server meshing; design bubbles to map to servers later, don't depend on it yet.
- External AI brain: server-only connection via built-in WebSockets/HTTP [local] or gRPC via TurboLink (MIT); async; outputs = suggested intents validated by server rules; deterministic fallbacks. The 5.8 Unreal MCP plugin is editor-only tooling, not runtime.
- Networked physics (resim + predictive interpolation via `UNetworkPhysicsComponent`) for player-flown fighters (see vorixo write-up, Sep 2026).

## Sources
dev.epicgames.com: large-world-coordinates, UE 5.8 release notes, sky-atmosphere, volumetric-cloud, mover, chaos-destruction, geometry-scripting, megalights, mass-entity, dedicated servers, iris, CMC networked movement; tomlooman.com UE 5.8 perf highlights; gamedevtricks.com origin rebasing; UE forums 1:1 space; starshipsimulator.co.uk; Marek Rosa (Space Engineers); starcitizen.tools (Star Engine, OCS, Replication layer); GDC Vault NMS; RealtimeMeshComponent GitHub; Voxel Plugin licensing/changelog; Cesium CHANGES.md; CDLOD (fstrugar); Hillaire EGSR 2020; Fab Arghanion flight system; Unreal Fest 2024 Mover intro; Unreal Fest Stockholm 2025 networked physics movement; vorixo phys-prediction; orrery issue 1045; Cold06 subgrids gist; LocalSimulation plugin; Dual Universe physics wiki; Jump Space Steam; The Finals; TurboLink.
Local files: EngineDefines.h, LargeWorldRenderPosition.h, PhysScene_Chaos.cpp, NetSerialization.h, Character.h, MovementBaseInterface.h, CharacterMovementComponent.cpp, SimulationSpace.h, Mover/README.md, GeometryCollectionComponent.h, Engine.Build.cs, Config/Mac/DataDrivenPlatformInfo.ini, WorldPartition.cpp, IrisConfig.cpp, MultiServerProxy.h.
