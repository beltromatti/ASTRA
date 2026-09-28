# STATO DEI LAVORI — ASTRA

*Questo file è la memoria operativa del progetto: lo aggiorno a ogni passo. Chi riprende il lavoro (io in una nuova sessione) parte da qui.*

**Ultimo aggiornamento:** 2026-09-28 (notte) · **Traguardo corrente:** M1 — La nave che si cammina

## Credito AI (OpenRouter)
| Data | Credito totale | Speso | Note |
|---|---|---|---|
| 2026-09-28 | 10,00 $ | 0,00 $ | ricarica iniziale dell'utente |
| 2026-09-28 | 10,00 $ | 0,10 $ | benchmark modelli (9 configurazioni × 40 ordini) |
| 2026-09-28 | 10,00 $ | 0,13 $ | sviluppo dell'equipaggio AI (≈0,0005 $ a turno di plancia) |

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

## M3 (anticipato) — L'equipaggio che pensa: primo anello completo funzionante
- [x] Servizio `mind/` (`uv run astra-mind`, WebSocket 8765): agente di plancia con 8 ufficiali (XO Serra, timone Ferri, operazioni Tanaka, tattico Voss, comunicazioni Martin, sensori Nair, ingegneria Mensah, volo Price), DeepSeek V4.1 Flash via OpenRouter (Together → Modal), 14 strumenti tipizzati, risposta vocale in 0,5–0,7 s dal testo
- [x] Voce: WhisperKit locale (push-to-talk) → testo; Pocket TTS locale con voci scelte dal casting automatico (docs/bench/voci_casting_2026-09-28.md)
- [x] Unreal: `UAstraMindSubsystem` (collegamento), `UAstraShipSubsystem` (stato e comandi reali: rotta/virata che ruota cielo e stella, allerta con luci, materiali e klaxon), `AAstraCrewMember` (voce spazializzata dalla postazione)
- [x] Prova: in plancia «Allarme rosso! Timoniere, virare a zero-nove-zero» → la XO conferma, il timoniere ripete l'ordine, la nave va in condizione rossa e vira; «fuoco sulla Praetorian» → Voss rifiuta (nave amica)
- [ ] Rapporti spontanei dagli eventi (rotta raggiunta, contatti), schermi con dati vivi, gesti/sguardo verso il capitano, MetaHuman e labiale

## M4 (prima versione) — Battaglia
- [x] Generatore di astronavi (`art/blender/shipgen.py`): ASTRA (Aquila, Praetorian, Vigilant), Kharon Mandate (Acheron, Styx, Lethe), mercantile delle Gilde; livree per fazione
- [x] `UAstraBattleSubsystem`: navi nel sistema (doppia precisione) disegnate attorno alla Aquila, IA d'ingaggio/fuga, railgun con anticipo, missili guidati, laser, difesa di punto, scudi, scafo, esplosioni, bagliori dei motori
- [x] Scenario «Aurelia patrol»: fregata dormiente T-11 → gruppo d'attacco dell'Archon Varek Solm (Acheron + 2 Styx) → vittoria/sconfitta/ritirata
- [x] Equipaggio collegato: contatti reali, ordini di fuoco/scansione/chiamata sulla simulazione, rapporti di danno per ponte e sezione, scossoni e luci che sfarfallano ai colpi
- [ ] Tavolo olografico con la situazione tattica viva, comunicazioni con il comandante nemico (voce e mente di Varek Solm), squadre di controllo danni visibili, bilanciamento
- [ ] Navi v2 (sagome e dettagli più belli), effetti visivi migliori (scie, esplosioni volumetriche)

## Prossimi passi
1. Tavolo olografico tattico vivo + comunicazioni con il nemico (Varek Solm, persona AI).
2. Equipaggio: schermi vivi, comportamento dei corpi (posture sedute, gesti), poi MetaHuman + labiale.
3. Navi v2 e effetti; simulazione di energia/calore (M2); hangar e caccia (M5).

## Come provarlo (per l'utente)
1. `tools/avvia_editor.sh` (o apri ASTRA.uproject); il livello iniziale è la plancia (`L_Bridge`).
2. Il servizio delle menti parte da solo al primo avvio della partita (oppure `cd mind && uv run astra-mind`).
3. Premi Play; tieni premuto **V** e parla al ponte in qualsiasi lingua (al primo uso macOS chiede il permesso del microfono), oppure dalla console (`) scrivi `astra.say Allarme rosso!`.
4. La battaglia parte da sola (dopo ~80 s si sveglia la fregata, dopo ~170 s arriva il gruppo d'attacco). Per accelerare: `astra.battle.time 168`, `astra.battle.timescale 3`.

## Note operative
- Editor: avviarlo con `tools/avvia_editor.sh` (modalità unattended: niente limite a 3 fps a schermo bloccato). Tenere `t.MaxFPS 30` quando idle, 4 durante i test di prestazioni.
- Il gioco standalone scrive i CSV in `~/Library/Application Support/Epic/UnrealEngine/5.8/Saved/Profiling/CSV`.
- `astra_editor.save()` salva sempre (EditorAssetLibrary saltava gli asset "non sporchi").
- Cubemap long-lat in Unreal: centro immagine = mondo -Y, u=0,75 = +X, alto = +Z.
- Mai più `lockable` in .gitattributes: rende i .uasset di sola lettura e Unreal non salva (errore nascosto in modalità unattended).
- Durante il PIE la EditorAssetLibrary non funziona (restituisce None): interrogare il mondo di gioco con GameplayStatics/load_object.
- Catture del gioco: `HighResShot 1920x1080` nel mondo PIE → Saved/Screenshots/MacEditor/.
- Il cielo non usa "IsSky" (non veniva disegnato nel gioco): sfera unlit ricentrata sulla camera via World Position Offset.

## Registro decisioni
- 2026-09-28 — Modelli: DeepSeek V4.1 Flash @Modal (98% ordini corretti, 100% lingua, primo comando 0,52 s, frase 1,02 s) e @Together (95%, 0,46 s) in doppio canale; scartati gpt-oss (55%), GPT-6 Luna e Groq (errori). DeepSeek diretto e GLM bloccati dalle impostazioni privacy dell'account OpenRouter (non servono).
- 2026-09-28 — Intenti istantanei: multilingual-e5-small (MIT) invece di EmbeddingGemma (accesso Google su approvazione manuale).
- 2026-09-28 — Progetto sulla Scrivania (richiesta utente); lavoro sempre su `main`.
- 2026-09-28 — Contenuti di terzi grezzi e MetaHuman generati esclusi da git (quota LFS gratuita 10 GiB); si riscaricano/rigenerano dagli script.
- 2026-09-28 — Cielo: nebulosa dipinta sulla sfera (shader world Cycles) invece che volumetrica: più controllabile, 8K in 14 s, strutture nitide.
- 2026-09-28 — Geometria: gusci dei moduli costruiti a prismi per lato (niente booleane sui gusci: la Manifold lasciava facce spurie).
- 2026-09-28 — Esposizione: cielo con compensazione parziale dell'adattamento (stelle visibili anche da interni illuminati, scelta artistica).
- 2026-09-28 — Agente di plancia: tool_choice "auto" e provider Together per primo (Modal restituisce argomenti vuoti con "required"); cronologia nel formato nativo degli strumenti (un riassunto testuale faceva rispondere il modello in prosa).
- 2026-09-28 — Nave come sistema di riferimento: la Aquila resta ferma all'origine, cielo e stella ruotano quando vira (stabile per la fisica e i personaggi a bordo); da rivedere per il multiplayer (griglie per nave).
- 2026-09-28 — Colori d'allerta calcolati nel materiale da parametri scalari (il parametro vettoriale della collezione dava float4 e il materiale non compilava).
