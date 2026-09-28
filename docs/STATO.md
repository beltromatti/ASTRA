# STATO DEI LAVORI — ASTRA

*Questo file è la memoria operativa del progetto: lo aggiorno a ogni passo. Chi riprende il lavoro (io in una nuova sessione) parte da qui.*

**Ultimo aggiornamento:** 2026-09-28 (notte) · **Traguardo corrente:** M1 — La nave che si cammina

## Credito AI (OpenRouter)
| Data | Credito totale | Speso | Note |
|---|---|---|---|
| 2026-09-28 | 10,00 $ | 0,00 $ | ricarica iniziale dell'utente |
| 2026-09-28 | 10,00 $ | 0,10 $ | benchmark modelli (9 configurazioni × 40 ordini) |

Regola: sotto i 3 $ residui aggiungo una voce in RICHIESTE.md e riduco le spese AI non essenziali (benchmark, immagini).

## Preparazione (checklist dell'utente) — completata 2026-09-28
- [x] Chiavi nel `.env`: OpenRouter, Sketchfab, Blendkit (recuperata da me), Hugging Face, Freesound, api.data.gov — tutte verificate con chiamate reali.
- [x] DeepSeek diretto: **non usato** (scelta dell'utente) → DeepSeek V4.1 Flash via OpenRouter, doppio canale tra due provider (Modal + Together).
- [x] ElevenLabs: non usato per ora (voce locale).
- [x] GitHub: gh CLI autenticato via SSH come `beltromatti`.
- [x] Accessi nel browser integrato: Fab, Sketchfab, Blendkit, Hugging Face, Freesound, Mixamo, GitHub, OpenRouter.
- [x] Core Data MetaHuman installato (6 GB). Aggiornamenti automatici App Store spenti. Scrivania non sincronizzata con iCloud.
- [x] Permessi di controllo: Unreal Editor, Epic Games Launcher, Finder, schermo intero (per questa sessione).
- [x] Strumenti: git-lfs 3.8, uv 0.12, espeak-ng 1.52, Blender 5.2.2 LTS.

## M0 — Fondamenta
- [x] Cartella progetto `~/Desktop/ASTRA`, documenti spostati, `.env` protetto (gitignore + hook anti-segreti)
- [x] Repository git + LFS, repo privato GitHub `beltromatti/ASTRA`, push
- [x] Plugin Claude Code ufficiale Epic (skill Unreal) v3.1.1
- [x] Progetto Unreal C++ ASTRA dal template First Person, configurato per M4 16 GB (SM6, niente RT hardware, Substrate spento, pool di memoria)
- [x] MCP ufficiale attivo + toolset `AstraAgentTools` (Python arbitrario) + client `tools/ue.py`; verifica con catture (docs/progressi/)
- [x] Guida di stile (docs/STILE.md) + Bibbia di ASTRA (docs/BIBBIA.md) — bozze v0.1
- [x] Benchmark modelli AI → scelta: DeepSeek V4.1 Flash (Modal + Together in doppio canale) per ufficiali/equipaggio; Ling 3.0 Flash per chiacchiere; MiniMax-M3 candidato per capitani/ammiragli (docs/bench/)
- [x] Catena vocale di base verificata: Pocket TTS italiano 60 ms al primo audio (×8 tempo reale, CPU), WhisperKit 0,6 s su un ordine di 4 s con lingua automatica e glossario (docs/bench/voce_2026-09-28.md). Labiale e voci su misura → M3
- [x] Test di prestazioni automatici (CsvProfile): `tools/perf/run_perf.sh` (gate automatico ancora da agganciare)

## M1 — La nave che si cammina (in corso)
- [x] Materiali master ASTRA (M_ASTRA_Hard/Emissive/Glass) + 11 istanze dalla palette; texture CC0 ambientCG impacchettate (`tools/art/pack_textures.py`)
- [x] Kit del corridoio v2 (`art/blender/kit_corridor.py`): gusci a prismi, 7 pannelli a varianti, canaletta tecnica sotto griglia, strisce di reparto, finestrone
- [x] Livello `L_CorridorTest` (24,5 m, paratia, finestrone) — 58 fps a 1080p col profilo A (docs/bench/prestazioni_2026-09-28.md)
- [x] Plancia v1 dai dati (`data/ship/aquila_bridge.json` → `art/blender/bridge.py` → `L_Bridge`): pozzo del timone, pedana, 9 postazioni, cupola, finestrone a 6 facce
- [x] Cielo di Aurelia: stelle NASA + nebulosa Teal Veil procedurale 8K (`art/blender/sky_aurelia.py`), stella Aurelia nel materiale del cielo, orientamento pilotabile
- [ ] Plancia v2: pavimento scuro, soffitto a cassettoni, poltrone rifatte, schermi con interfacce, ologramma sul tavolo
- [ ] Esterno della Aquila (almeno la prua visibile dalla plancia), pianeta New Ravenna
- [ ] Movimento in prima persona nella nave, ascensore, segnaletica/decalcomanie

## Prossimi passi
1. Plancia v2 (arte) — breve.
2. **Anello equipaggio AI (nucleo di M3)**: servizio `mind/` (WebSocket) con STT locale → DeepSeek V4.1 Flash con strumenti → TTS locale; in Unreal: sottosistema C++ di connessione, cattura microfono (push-to-talk), voce spazializzata, stato nave con comandi (allerta, rotta, scudi…) che cambiano davvero la nave (luci di allerta).
3. Simulazione nave (M2) e poi battaglia (M4).

## Note operative
- Editor: avviarlo con `tools/avvia_editor.sh` (modalità unattended: niente limite a 3 fps a schermo bloccato). Tenere `t.MaxFPS 30` quando idle, 4 durante i test di prestazioni.
- Il gioco standalone scrive i CSV in `~/Library/Application Support/Epic/UnrealEngine/5.8/Saved/Profiling/CSV`.
- `astra_editor.save()` salva sempre (EditorAssetLibrary saltava gli asset "non sporchi").
- Cubemap long-lat in Unreal: centro immagine = mondo -Y, u=0,75 = +X, alto = +Z.

## Registro decisioni
- 2026-09-28 — Modelli: DeepSeek V4.1 Flash @Modal (98% ordini corretti, 100% lingua, primo comando 0,52 s, frase 1,02 s) e @Together (95%, 0,46 s) in doppio canale; scartati gpt-oss (55%), GPT-6 Luna e Groq (errori). DeepSeek diretto e GLM bloccati dalle impostazioni privacy dell'account OpenRouter (non servono).
- 2026-09-28 — Intenti istantanei: multilingual-e5-small (MIT) invece di EmbeddingGemma (accesso Google su approvazione manuale).
- 2026-09-28 — Progetto sulla Scrivania (richiesta utente); lavoro sempre su `main`.
- 2026-09-28 — Contenuti di terzi grezzi e MetaHuman generati esclusi da git (quota LFS gratuita 10 GiB); si riscaricano/rigenerano dagli script.
- 2026-09-28 — Cielo: nebulosa dipinta sulla sfera (shader world Cycles) invece che volumetrica: più controllabile, 8K in 14 s, strutture nitide.
- 2026-09-28 — Geometria: gusci dei moduli costruiti a prismi per lato (niente booleane sui gusci: la Manifold lasciava facce spurie).
- 2026-09-28 — Esposizione: cielo con compensazione parziale dell'adattamento (stelle visibili anche da interni illuminati, scelta artistica).
