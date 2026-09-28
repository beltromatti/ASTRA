# Research 04 — Tooling for autonomous UE 5.8.3 + Blender development (2026-09-27)

Checked local engine source (5.8.3, CL 58210709) + web. UNVERIFIED = not confirmed.

## 1. Official Unreal MCP (Engine/Plugins/Experimental/ModelContextProtocol)
- In-editor HTTP server (MCP spec 2025-11-25), no stdio. Localhost only, rejects cross-origin browser requests, **no auth** (any local process can drive the editor). Tool calls run sequentially on the game thread.
- Tool search on by default: only `list_toolsets`, `describe_toolset`, `call_tool`. ~52 toolsets / ~830 tools (community probe of 5.8.0). Fully-qualified names e.g. `EditorToolset.EditorAppToolset`, `editor_toolset.toolsets.actor.ActorTools`, `PCGToolset.PCGToolset`. Project skills via `AgentSkillToolset.ListSkills` / `GetSkills`.
- `execute_tool_script` ≠ arbitrary `unreal` Python: no `unreal` module; imports only json/math/datetime/copy/re/time; exec/eval/compile/input/breakpoint/help removed; read-only `open()` limited to project + Saved/; script defines `run() -> dict` and calls `execute_tool("<Toolset>.<tool>", json)`. Python-level allowlist, not a hardened sandbox. Since 5.8.1 a failing script no longer rolls back as one transaction.
- Missing: console-command tool, arbitrary Python; `StaticMeshTools.import_file` FBX/OBJ only (glTF via Python/Interchange); **Live Coding Windows-only** → LiveCodingToolset useless on Mac.
- **Screenshots come back as text**: CaptureViewport returns ~2.8 MB base64 PNG as text → Claude Code saves to file instead of showing an image. Prefer writing PNGs to disk and reading them.
- Community-reported bugs (5.8.0 field notes): CaptureViewport ignores captureTransform & renders no particles; failed `set_properties` can wipe touched props, never fires PostEditChange; `find_actors` stops at 20 results; `create_level_sequence` overwrites; PCG `GetNodeDataView` can hang; `DrawSpline` waits for human; HTTP 502 ≈ editor crashed.
- 5.8.1 fixed response framing + a Blueprint crash; 5.8.3 no MCP fixes. `unreal_mcp_proxy` not in 5.8.3 launcher build. AIAssistant (Epic Developer Assistant web panel) and MCPClientToolset not needed.

### Setup with Claude Code
1. `.uproject` Plugins: `{"Name":"ModelContextProtocol","Enabled":true},{"Name":"AllToolsets","Enabled":true},{"Name":"PythonScriptPlugin","Enabled":true},{"Name":"EditorScriptingUtilities","Enabled":true}`. AllToolsets excludes LiveCoding, MetaHumanGenerator (needs MetaHuman optional content), MVVM, ChaosClothAsset, SequencerAnimMixer → enable individually if needed.
2. `<Project>/Saved/Config/MacEditor/EditorPerProjectUserSettings.ini`:
   ```ini
   [/Script/ModelContextProtocolEngine.ModelContextProtocolSettings]
   bAutoStartServer=True
   ServerPortNumber=8000
   bEnableToolSearch=True
   [/Script/PythonScriptPlugin.PythonScriptPluginUserSettings]
   bDeveloperMode=True
   ```
   (Developer mode generates `Intermediate/PythonStub/unreal.py`.) Block risky PCG tools in `Config/DefaultEditorPerProjectUserSettings.ini`:
   ```ini
   [/Script/ToolsetRegistry.ToolsetRegistrySettings]
   +BlockedNames=GetNodeDataView
   +BlockedNames=DrawSpline
   ```
3. Disable Editor Preferences › Performance › "Use Less CPU when in Background" (otherwise calls crawl when unfocused — inference).
4. Launch: `".../UnrealEditor.app/Contents/MacOS/UnrealEditor" /abs/Proj.uproject -ModelContextProtocolStartServer` (+ `-ModelContextProtocolPort=N`).
5. `.mcp.json` next to .uproject (console `ModelContextProtocol.GenerateClientConfig ClaudeCode` or by hand):
   `{"mcpServers":{"unreal-mcp":{"type":"http","url":"http://127.0.0.1:8000/mcp","timeout":600000}}}`
6. `MAX_MCP_OUTPUT_TOKENS=60000`; raise `CLAUDE_CODE_MCP_TOOL_IDLE_TIMEOUT` (HTTP default 5 min).
7. Epic skills plugin for Claude Code: `/plugin install unreal-engine-skills-for-claude-code@claude-plugins-official` (v3.1.1).
8. Verify via `list_toolsets`. Console: `ModelContextProtocol.StartServer/StopServer/RefreshTools`; log `LogModelContextProtocol`.

### Key tools
- EditorAppToolset (C++): CaptureViewport (grid/labels), CaptureEditorImage, CaptureAssetImage, Get/SetCameraTransform, FocusOnActors, Get/SelectActors, GetVisibleActors, WorldPosToScreenCoords, ScreenCoordsToWorld, OpenEditorForAsset, StartPIE (Simulate, spawn transform, warm-up), StopPIE, IsPIERunning, SearchCVars. LogsToolset: GetLogEntries, Get/SetVerbosity.
- EditorToolset (Python): SceneTools (20: load_level, find_actors, add_to_scene_from_asset/_class, trace_world, merge_actors, level instances), ActorTools (17), AssetTools (21: find/duplicate/move/delete/save, referencers, read/write_file), BlueprintTools (53: create, compile, create_node, connect_pins, add_variable, write/read_graph_dsl), MaterialTools (22), MaterialInstanceTools (13), StaticMeshTools (16: import_file, set_nanite_enabled, generate_lods, convex collisions, set_material), ObjectTools (get/set/reset_properties), Primitive/Texture/DataTable/CurveTable/StringTable.
- PCGToolset (30): CreateGraph, GetGraphStructure, AddNode, AddSubgraphNode, UpdateNode, ConnectNodePins, SetGraphParams, SpawnGraphInstance, ExecuteGraphInstance, ListNativeNodes, GetNativeNodeSchema, + PCGSpatialToolset.RunPCGInstantGraph.
- NiagaraToolsets (56): CreateNiagaraSystem, AddEmitter, AddModule, AddRenderer, SetStackInputData, SetEmitterData, AddUserVariables, GetSystemSummary, GetSystemCompileState, GetStackIssues, ApplyStackIssueFix, component SetSystem/SetVariable.
- UMGToolSet (23): CreateWidgetBlueprint, AddWidget, MoveWidget, WrapWidgets, BindToEventProperty, CompileWidgetBlueprint.
- StateTreeToolset (9, read-only). PhysicsAssetToolset (17). LiveCodingToolset (CompileLiveCoding — Windows only). MetaHumanToolset: begin_edit, create, set_body_shape, set_skin_tone, set_eye_color, end_edit.
- SlateInspectorToolset: Snapshot, Screenshot, Click, Type, PressKey, Drag, WaitFor, FillForm (can type into editor console → covers missing console tool). AutomationTestToolset (RunTests, GetTestResults), ConfigSettingsToolset, PluginToolset, SequencerTools (140).

## 2. Arbitrary editor Python + visual verification
- Remote execution still present (`PythonScriptPlugin/Content/Python/remote_execution.py`): UDP multicast discovery 239.0.0.1:6766 bound to 127.0.0.1; client listens TCP 127.0.0.1:6776, editor connects back; modes ExecuteFile/ExecuteStatement/EvaluateStatement; results `{success, result, output:[{type, output}]}`. Enable `bRemoteExecution=True` in `[/Script/PythonScriptPlugin.PythonScriptPluginSettings]` (DefaultEngine.ini). **macOS risk:** multicast discovery historically flaky on Macs (Local Network privacy since Sequoia; one report of editor hang) — UNVERIFIED on 26.6.
- **Most robust: arbitrary Python through the already-working MCP connection** via a small project toolset (pattern from Epic's create-toolset skill, UNVERIFIED):
  ```python
  # Content/Python/agent_tools.py   (init_unreal.py: import agent_tools; agent_tools.REG.register())
  import contextlib, io, traceback, unreal, toolset_registry
  from toolset_registry.registration import Registration
  @unreal.uclass()
  class AgentPythonTools(unreal.ToolsetDefinition):
      """Runs arbitrary editor Python for a trusted local agent."""
      @toolset_registry.tool_call
      @staticmethod
      def run_python(code: str) -> str:
          """Runs code on the game thread; returns stdout/stderr and repr of `result`."""
          buf, g = io.StringIO(), {"unreal": unreal}
          with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
              try: exec(code, g)
              except Exception: traceback.print_exc()
          return buf.getvalue() + (f"\nresult={g['result']!r}" if "result" in g else "")
  REG = Registration([AgentPythonTools])
  ```
  Alternative: VibeUE (community; plugs into Epic's registry; adds execute_python_code etc.).
- Remote Control API fallback: `PUT http://127.0.0.1:30010/remote/object/call` on `/Script/PythonScriptPlugin.Default__PythonScriptLibrary` → `ExecutePythonCommandEx` (needs `bEnableRemotePythonExecution=True` in `[/Script/RemoteControlCommon.RemoteControlSettings]`; set `RemoteControlWebsocketServerBindAddress=127.0.0.1` since WS defaults to 0.0.0.0:30020).
- Headless: `UnrealEditor-Cmd Proj.uproject -run=pythonscript -script="/abs/job.py args" -unattended -nullrhi -stdout -FullStdOutLogOutput`; or `UnrealEditor Proj.uproject -ExecutePythonScript=/abs/job.py` (rendering; end with `unreal.SystemLibrary.quit_editor()`). Not while the interactive editor has the project open.
- Screenshots: write PNGs to `Saved/Agent/`, shrink with `sips -Z 1568`, view with Read. Capture via `unreal.AutomationLibrary.take_high_res_screenshot(w,h,path,camera=cam)` (async; poll file), SceneCapture2D → render target → `RenderingLibrary.export_render_target` (Lumen fidelity UNVERIFIED), `HighResShot`, Movie Render Queue for beauty shots, `screencapture -l<windowID>`.

## 3. Community Unreal MCP servers
| Server | Stars / last push | Transport | UE 5.8 / Mac | Verdict |
|---|---|---|---|---|
| **VibeUE** | 705 / 09-26 | plugs into Epic registry & :8000 | 5-8 branch, Mac build script | only one worth adding (execute_python_code, landscape/foliage, undo checkpoints, profiling, GLB import); Xcode build; some tools call external APIs |
| ChiR24/Unreal_mcp | 890 / 09-25 | own server :3000/:8091 | 5.8 fixes in Sept | beta 0.6, revisit later |
| db-lyon/ue-mcp | 369 / 09-27 | replaces official server | 5.8 | don't pair with official |
| Monolith | 316 / 09-09 | HTTP :9316 all interfaces, no auth | 5.7/5.8 | avoid |
| GenOrca / UnrealClaude / flopperam | 144 / 905 / 1,085 | TCP/HTTP | stale / ≤5.7 | skip |
| chongdashu / kvick-games / runreal | 2025 | — | 5.4–5.5 era | abandoned |

## 4. Blender
- Blender **5.2.2 LTS** (2026-09-15), Homebrew cask 5.2.2 arm64, binary `/Applications/Blender.app/Contents/MacOS/Blender`. 5.x Apple Silicon only; 5.1 → Python 3.13, ignores user site-packages (`--python-use-system-env`); 5.0 renamed `BLENDER_EEVEE_NEXT` → `BLENDER_EEVEE`.
- Headless: `Blender -b --factory-startup --python-exit-code 1 -P pipe.py -- args` (import glTF → decimate → `uv.smart_project` → Cycles bake w/ Metal → export FBX/GLB/USD).
- MCP: `ahujasid/mcp-for-blender` (ex blender-mcp, 29.5k★): code exec, viewport screenshots, Poly Haven, Sketchfab, Rodin, Hunyuan3D; `claude mcp add blender -e DISABLE_TELEMETRY=true -- uvx mcp-for-blender` + add-on (port 9876, no auth). Blender Lab MCP v1.0.3 alternative.
- Blender → UE 5.8: FBX via Interchange or GLB (packed ORM matches UE); USD import production-ready with USDImporter; scale 1.0 + applied transforms, ship noses +X; Nanite: high poly fine, triangulate, export normals, few material slots, no translucency; `UCX_` collision, `SOCKET_` sockets; ORM packed sRGB off; flip normal green if needed. Send to Unreal: Epic repo dormant (poly-hammer fork 2.6.7, depends on remote exec) → skip.

## 5. AI hard-surface asset generation
| Tool | Output | API | ~Cost/model |
|---|---|---|---|
| **Meshy 7.1** | quad/tri remesh w/ target polycount, UVs, PBR ≤8K | REST | $0.60–0.80 (Pro $20/mo) |
| Tripo (API v3.1; P2.0 quad web-only) | quad/smart low-poly, PBR | REST prepaid | $0.35–0.65 |
| Rodin Gen-2.5 | quad, PBR ≤12K | Business plan only ($120/mo) | ~$0.29 |
| Hunyuan3D 3.1 API / 2.1 open weights | retopo, PBR | Tencent Cloud | ~$0.35 |
| TRELLIS.2 (MIT) | dense tris, PBR | none | free; Mac ports ~21 min/asset, experimental |
- Hunyuan3D 2.1 open-weights license (incl. outputs) **void in EU/UK/South Korea** → not usable from Italy; texturing needs ~21 GB anyway.
- CSM and Luma Genie appear discontinued (UNVERIFIED).
- AI output still softens bevels/greebles → mid-ground props only; hero ships procedurally in Blender or UE Geometry Script.
- Space backgrounds: **NASA SVS Deep Star Maps 2020** (65,536×32,768 EXR, credit NASA/GSFC SVS); ESA/Webb imagery CC BY 4.0; Blockade Skybox AI 8192×4096 native (16K upscaled), commercial use needs Business plan.

## 6. Recommended setup
1. MCP: official `unreal-mcp` + Epic skills plugin; arbitrary Python via the `AgentPythonTools` project toolset (no build) or VibeUE (Xcode build, pinned commit); keep a `remote_execution.py` client as fallback; Blender via headless CLI scripts (mcp-for-blender optional). No other community Unreal servers.
2. UE plugins: ModelContextProtocol, AllToolsets, PythonScriptPlugin, EditorScriptingUtilities, GeometryScripting, ModelingToolsEditorMode, PCG (+ PCGGeometryScriptInterop), MovieRenderPipeline, USDImporter (if USD).
3. Minimize C++ churn on Mac: each change = quit editor → `Engine/Build/BatchFiles/Mac/Build.sh <Proj>Editor Mac Development -Project=...` → relaunch. Save before bulk ops; one change at a time.
4. Local tools: `brew install uv git-lfs`, `brew install --cask blender` (OpenImageIO optional). Already present: sips, ffmpeg, node, gh.
5. Machine limits: little disk, 16 GB RAM → no local 3D-gen models; watch the DDC.
6. Keys: `MESHY_API_KEY` (primary); optional `TRIPO_API_KEY`; optional Sketchfab token. Skip Rodin/Blockade unless Business pricing is OK.

## Sources
Epic: unreal-mcp-in-unreal-editor docs; UE 5.8 release notes; github.com/EpicGames/unreal-engine-skills-for-claude-code-plugin; 5.8.1 & 5.8.3 hotfix threads. MCP issues/guides: forum threads (connections drop; crash behind HTTP 502); PavelVyny/ue58-mcp-field-notes; ludusengine.com setup; tc-imba/ue-official-mcp. Claude Code MCP docs. Remote exec on Mac: poly-hammer BlenderTools #19; Apple dev forums 809211; per-simmons/unreal-agent-harness. Community servers: VibeUE, ChiR24/Unreal_mcp, db-lyon/ue-mcp, tumourlove/monolith, GenOrca, Natfii/UnrealClaude, flopperam, chongdashu, runreal. Blender: brew cask json; 5.2 release notes; ahujasid/mcp-for-blender; Blender Lab MCP; poly-hammer BlenderTools. AI gen & imagery: Meshy pricing; Tripo pricing; Rodin Gen-2.5 docs; Hunyuan3D-2.1; TRELLIS.2; Blockade exports; NASA SVS 4851; esawebb.org/copyright; polyhaven.com/license.
