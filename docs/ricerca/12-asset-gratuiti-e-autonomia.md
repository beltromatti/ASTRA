# Research 12 — Budget-0 assets & autonomous acquisition (2026-09-27)

Supersedes report 07 (paid Fab tiers) under the new "budget 0 for non-AI" rule.

## What changed in 2026
- Sketchfab & ArtStation acquired by KitBash (announced 2026-08-10); downloads continue; public search API still returns downloadable CC models (tested).
- BlenderKit renamed **Blendkit** (both domains serve the API).
- Megascans paid since 2025; still free: **starter set 1,500+ assets + 5 tree packs + 11 UE scenes**, and **Megaplants**; 2024 claims still downloadable via Bridge.
- Sonniss: no GDC 2025 bundle; 2026 bundle = 7.47 GB.
- New open music models: **Stable Audio 3** (open weights, 2026-05-20), **ACE-Step 1.5 XL** (2026-04-02).

## 1. Sources — 3D, materials, sky
| Source | Sci-fi photoreal value | Formats | Licence | API/automation | Account |
|---|---|---|---|---|---|
| **Fab permanently free Epic content** | high: Cassini Sample (shape-grammar procedural station, Saturn rings 5M+ instances), City Sample, Electric Dreams, Game Animation Sample, Lyra, Paragon characters/environments/FX, Automotive Materials (Valley of the Ancient, Infiltrator, Open World Demo UNVERIFIED) | UE projects/packs | Fab Standard (any engine; some Epic content may be UE-only, UNVERIFIED) | editor Fab window / Launcher | Epic |
| **Fab Megascans** | very high but mostly paid; free: starter set + Megaplants (Nanite, 5.7 vegetation editor) | UE, FBX; Low/Med/High/Raw | Fab Standard | editor Fab window | Epic |
| **Fab limited-time free** | varies; recent sci-fi: Modular SciFi Station (Jun 2–16), Sci-Fi Creatures Research Lab (Aug 25–Sep 8), Industrial Infrastructure (Sep 8–22) | UE & others | kept forever once claimed | §2 | Epic |
| **Poly Haven** | top-tier: 997 HDRIs (≤24k), 862 textures (≤8k, MaterialX), 521 models | EXR/HDR, JPG/PNG, blend, glTF, FBX, USD | CC0 | `api.polyhaven.com` no key; User-Agent mandatory; no site scraping | no |
| **ambientCG** | high: 2,894 assets (2,011 materials, 429 HDRIs, 127 decals, 61 atlases) | 1K–8K zips | CC0 | `ambientcg.com/api/v3/assets?...&include=downloads` no key (one-person site → throttle) | no |
| **Blendkit** (ex-BlenderKit) | medium–high: free tier 23,166 models, 40,765 materials, 4,966 HDRIs; 447 free sci-fi models; ~2,543 free CC0 models; ~2,468 free CC0 materials | .blend | CC0 or Royalty-Free (OK in games if not easily extractable; no resale) | public search `/api/v1/search/`; downloads need API key | yes |
| **Sketchfab** | mixed, some gems | glTF zip, USDZ | per model (CC0, BY, BY-SA, BY-ND, BY-NC…) | Data API v3 | yes |
| **NASA 3D Resources** | accurate references & greeble sources (ISS, craft, asteroids, sites) | 3ds, blend, fbx, glb, lwo, stl | generally not copyrighted; no endorsement/insignia; AI training restricted | GitHub `nasa/NASA-3D-Resources` | no |
| **NASA SVS maps** | critical: Deep Star Maps 4k–64k EXR (64k = 3.8 GB); CGI Moon Kit 16k EXR / 27k TIFF + 23k displacement | EXR, TIFF | credit "NASA/GSFC SVS" | direct | no |
| **Smithsonian 3D** | photoreal CC0 scans (e.g., Apollo 11 CM interior) | GLB (tiers, Draco) | CC0 (check item) | `3d-api.si.edu/api/v1.0/content/file/search?q=…&file_type=glb` no key (tested); Open Access API: api.data.gov key (1,000 req/h; DEMO 30/h) | no / free key |
| Solar System Scope / ESA-Webb | planet maps 2k/8k; nebula imagery | JPG/TIF | CC BY 4.0 (Webb visible credit) | direct | no |
| Blender Studio | Charge (photoreal factory & robots; Material Asset Library free), Singularity 2026 (painterly), Tears of Steel (quadbot free; production files need subscription) | .blend | CC BY / CC BY 4.0 | manual | free account |
| 3dtextures.me / ShareTextures / TextureCan / cgbookcase | good: 131 sci-fi textures on 3dtextures.me (1,300+ total); ShareTextures 1,700+; TextureCan 650+ | PBR maps | CC0 | none (one at a time) | no |
| TurboSquid / CGTrader free | uneven | various | games OK, no redistribution; genAI use needs TurboSquid permission | none | yes |
| KitBash3D Cargo | kitbash quality; 100+ free samples | UE/Blender plugins (macOS) | UNVERIFIED | Cargo app | yes |
| Kenney, Quaternius, OGA, itch | low (stylized) → UI/prototypes | — | mostly CC0/mixed | — | — |

## 2. Autonomous acquisition
**Fab claiming:**
1. Limited-time rotation: every 2 weeks, Tuesday 10:00 ET (14:00 UTC) → until 09:59 ET two weeks later; next 2026-10-06 (current three not sci-fi) → weekly-check job after 14:05 UTC Tuesdays.
2. In editor: UE 5.8 Fab window (Window → Get Content → Fab) → "Add to My Library" for free items; "Add to Project" imports Megascans and GLB/FBX directly; for UE-format packs one guide says Launcher only (stock 5.8 Mac behaviour unconfirmed).
3. On fab.com in the built-in browser (human logged in once): click "Add to My Library" (includes accepting the EULA). Undocumented internal endpoint `/i/listings/{uid}/add-to-library` with `X-CsrfToken` from `fab_csrftoken` cookie exists (community userscripts) — throttled, ~≤1 req/s. **ASTRA policy: prefer UI clicks at human pace; never circumvent Cloudflare/bot detection.**

**Fab downloading:** FBX/GLB/OBJ/USD directly from fab.com (My Library → download → format) where sellers provide them; UE-format packs install only via Launcher or editor plugin.
| Tool | 2026 status |
|---|---|
| Asset Manager Studio (free, unofficial) | best Mac option technically: v1.2.2 (2026-08-14) arm64 DMG; v1.1.0 CLI login via AuthKey, CLI download/export, "Fab Freebies" screen; CLI syntax UNVERIFIED. **Unofficial tool handling Epic auth → account-risk; not in the default plan.** |
| Epic Games Launcher (Mac) | official, GUI → fallback (drivable via computer-use) |
| FabCLI (zirklerite) | search/claim/claim-batch/download; Windows/Linux only; warns of suspension risk |
| legendary | UE content listing only; no Fab downloads |
| Epic Asset Manager | Linux only; Fab items missing |
| FabAssetsManager | relies on reusing Cloudflare `cf_clearance` → **avoid** |

**Other sources:**
- Sketchfab: search no auth `GET https://api.sketchfab.com/v3/search?type=models&q=…&downloadable=true&license=by`; download `GET /v3/models/{uid}/download` (401 without auth, tested); OAuth2 Bearer per docs; personal API token as `Authorization: Token …` common but UNVERIFIED; returns `gltf.url`/`usdz.url` expiring in 300 s; OAuth app registration by contacting Sketchfab; tokens 1 month, refreshable.
- Blendkit: `bk_client` local HTTP service (port 62485, OpenAPI 3.1, API key or OAuth2, standalone, macOS arm64) or headless Blender + add-on + API key; pre-alpha UE plugin `bk_unreal`.
- Mixamo: Adobe ID, no API; krazyjakee gist (UI automation, tested July 2026 in Firefox; FBX 30 fps in-place ~9 s/clip); YasinSHV console script (resumable); PySide6 macOS GUI; UI changes can break; licence royalty-free (UNVERIFIED this session).
- Poly Haven / ambientCG: plain curl w/ custom User-Agent; keep returned licence field.
- Freesound: API key → search + HQ previews; originals need OAuth2 (code 10 min, access 24 h, refresh token); limits 60/min & 2,000/day; downloads 30/min & 500/day.
- NASA images API (`images-api.nasa.gov`, no key, includes audio); Smithsonian as above.

## 3. Free audio & music
| Source | Details | Licence |
|---|---|---|
| **Sonniss GDC** | 2015–2024 + 2026; direct/torrents/mirrors, no sign-up; 2026 = 7.47 GB / 347 WAVs; 2015–2024 >200 GB (community figure) → select via per-year track-list spreadsheets | royalty-free, no attribution, no standalone redistribution, **no AI/ML training** |
| **NASA audio** | SoundCloud, Artemis Audio Library, Internet Archive reels, images API (105 hits "launch") | effectively public domain (no endorsement) |
| Freesound | API | per sound: CC0, BY 4.0, BY-NC 4.0, Sampling+ |
| BBC Sound Effects | ~33,000 WAVs | RemArc: personal/educational/research only → **OK for private build; replace before release** |
| Pixabay | music & SFX; API images/video only; no mass download | Pixabay licence (commercial OK) |
| Kenney | sci-fi/interface/impact/UI/digital packs | CC0 |
AI/open music:
- **ACE-Step 1.5**: MIT (code+weights), trained on licensed/royalty-free/synthetic data, outputs commercially usable; macOS via MLX; on 16 GB use 2B turbo + small LM, quantized/offloaded; 10 s–10 min tracks; skip XL (≥20 GB). **Main option for the score.**
- **Stable Audio 3**: Small (0.6B), Small-SFX (0.6B), Medium (2B) gated on HF; Stability Community License (free < $1M revenue); trained on licensed AudioSparx + Freesound CC; up to ~6 min. **Main option for SFX/ambience.** Stable Audio Open 1.0: 47 s SFX/loops.
- MusicGen weights CC-BY-NC → private only. CC music: Scott Buckley catalogue (CC BY 4.0, WAV, cinematic/space).

## 4. Recommended budget-0 stack (by photoreal impact)
1. Space light & backdrops: Deep Star Maps EXR, SVS Moon Kit, Solar System Scope 8k, Webb imagery, Poly Haven HDRIs (look-dev).
2. PBR surfaces/decals/trims: Poly Haven, ambientCG (decals, atlases), 3dtextures.me sci-fi, Blendkit CC0 materials, Charge material library, Megascans starter → agent bakes ASTRA's own trim & decal atlases.
3. Hard-surface bases: Cassini, fortnightly Fab freebies, free Blendkit sci-fi, Sketchfab CC0/BY, Smithsonian CC0 scans, NASA 3D, Cargo freebies.
4. Crew: MetaHuman (free, in-editor since 5.6, usable in any engine under $1M), Game Animation Sample, Mixamo.
5. Planets & city: City Sample re-skinned, Electric Dreams, Megaplants.
6. Audio: Sonniss (selected), NASA, Freesound CC0/BY, Stable Audio 3 SFX, ACE-Step music.

## Accounts/tokens (human, once)
1. Epic (2FA): log in on fab.com in the built-in browser, in the UE 5.8 Fab window, and in the Mac Launcher; check for 2024 Megascans claims; **standing approval to accept Fab's EULA on free claims**.
2. Sketchfab API token. 3. Blendkit API key. 4. Adobe ID (Mixamo login in browser; allow multiple downloads). 5. Freesound API credentials (`/apiv2/apply`, localhost redirect) + one-time OAuth2 approval. 6. api.data.gov key (Smithsonian). 7. Hugging Face read token + accept gated Stable Audio licences. 8. GitHub read-only PAT (rate limits). 9. Optional: Pixabay, KitBash Cargo, Blender Studio free, Poliigon, TurboSquid, CGTrader.
No account: Poly Haven, ambientCG, CC0 texture sites, NASA, SVS, Smithsonian 3D, Sonniss, Kenney.

**Licence ledger:** per file: source, id, URL, licence, author, attribution string, date, modifications, flags (NC / RemArc / NoAI / UE-only). Replace before release: BBC sounds, MusicGen output, BY-NC, possibly UE-only content outside Unreal.
**Risks:** undocumented Fab endpoints & Mixamo UI automation → ToS risk; human-like pacing; never circumvent Cloudflare; don't feed TurboSquid/Sonniss content to generative AI.

## Sources
Fab limited-time free forum + zerotobeast 2026-09-22 + gamefromscratch June 2026; Megascans starter on Fab (forum); Quixel on Fab & licence; CG Channel Megascans 2024; Fab docs (purchasing/downloading, exporting in Launcher, licences & pricing); UE Fab window docs; msquared import guide; Cassini news; Epic free temple assets (digitalproduction 2026-01-08); CG Channel MetaHumans any engine (2025-06); assetmanager.studio (+changelog, CLI wiki); FabCLI; legendary; Epic Asset Manager; FabAssetsManager; dcc-mcp-epic; Subtixx gist; UE forum download without launcher; Poly Haven llms.txt & API; ambientCG API v3; Blendkit pricing & licensing FAQ; bk_client; bk_unreal; Sketchfab download API, OAuth, Data API v3, KitBash acquisition blog; Mixamo gists/scripts (krazyjakee, YasinSHV, Teethree89 macOS 2026); Freesound API overview/auth/FAQ; NASA 3D Resources GitHub & site; NASA brand guidelines; SVS 4851 & 4720; Artemis audio; Internet Archive NASA reels; Smithsonian Apollo 11 CM + open access GitHub; Solar System Scope; esawebb copyright; Blender Studio Charge/Singularity licensing/Tears of Steel; 3dtextures.me; ShareTextures; TextureCan; cgbookcase; KitBash3D Cargo; TurboSquid licence; Sonniss GDC + licence + BPB 2026 bundle; BBC SFX 33,000; Pixabay API & licence; Kenney audio; ACE-Step 1.5 (GitHub, HF); Stable Audio 3 announcement + HF medium; Stable Audio Open 1.0; MusicGen large; Scott Buckley library.
