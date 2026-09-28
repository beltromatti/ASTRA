# STATO DEI LAVORI — ASTRA

*Questo file è la memoria operativa del progetto: lo aggiorno a ogni passo. Chi riprende il lavoro (io in una nuova sessione) parte da qui.*

**Ultimo aggiornamento:** 2026-09-28 (mattina) · **Traguardo corrente:** M4 — La battaglia (poi tavolo olografico)

## Credito AI (OpenRouter)
| Data | Credito totale | Speso | Note |
|---|---|---|---|
| 2026-09-28 | 10,00 $ | 0,00 $ | ricarica iniziale dell'utente |
| 2026-09-28 | 10,00 $ | 0,10 $ | benchmark modelli (9 configurazioni × 40 ordini) |
| 2026-09-28 | 10,00 $ | 0,13 $ | sviluppo dell'equipaggio AI (≈0,0005 $ a turno di plancia) |
| 2026-09-28 | 10,00 $ | 0,40 $ | battaglie di prova complete con comandanti nemici (≈0,001–0,002 $ a turno) |
| 2026-09-28 | 10,00 $ | 0,63 $ | squadroni, regista della guerra, ammiraglio (≈0,002 $ per decisione del regista) |
| 2026-09-28 | 10,00 $ | 0,77 $ | transiti nel Janus Gate, ordini della Flotta, prove complete del regista |

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
- [x] Plancia v2 (primo passaggio): pavimento scuro semi-lucido, soffitto a cassettoni scuri con faretti incassati, console e poltrone scure, tavolo olografico vivo, schermi vivi
- [ ] Plancia v2 (secondo passaggio): dettagli a pannelli, cavi e condotti, segnaletica e decalcomanie, usura
- [x] Si parte seduti sulla poltrona del capitano (E per alzarsi/sedersi)
- [x] Janus Gate di Aurelia all'orizzonte (anello alieno di 16 km a 110 km, bande di glifi luminosi)
- [x] Scafo dell'Aquila attorno alla plancia (visibile guardando giù dal vetro)
- [x] Pianeta New Ravenna nel finestrone (sfera analitica nel materiale del cielo: continenti, nuvole, terminatore, luci notturne, atmosfera)
- [x] Corridoi percorribili dietro la plancia (babordo e tribordo, oblò sullo scafo) con porte scorrevoli vere (AAstraDoor) e suoni
- [x] Suoni di bordo sintetizzati: railgun, VLS, siluri, difesa di punto, catapulta, porte, bip delle console, ambiente di plancia
- [ ] Esterno della Aquila (almeno la prua visibile dalla plancia), ascensore, altri ponti, segnaletica/decalcomanie

## M3 (anticipato) — L'equipaggio che pensa: primo anello completo funzionante
- [x] Servizio `mind/` (`uv run astra-mind`, WebSocket 8765): agente di plancia con 8 ufficiali (XO Serra, timone Ferri, operazioni Tanaka, tattico Voss, comunicazioni Martin, sensori Nair, ingegneria Mensah, volo Price), DeepSeek V4.1 Flash via OpenRouter (Together → Modal), 14 strumenti tipizzati, risposta vocale in 0,5–0,7 s dal testo
- [x] Voce: WhisperKit locale (push-to-talk) → testo; Pocket TTS locale con voci scelte dal casting automatico (docs/bench/voci_casting_2026-09-28.md)
- [x] Unreal: `UAstraMindSubsystem` (collegamento), `UAstraShipSubsystem` (stato e comandi reali: rotta/virata che ruota cielo e stella, allerta con luci, materiali e klaxon), `AAstraCrewMember` (voce spazializzata dalla postazione)
- [x] Prova: in plancia «Allarme rosso! Timoniere, virare a zero-nove-zero» → la XO conferma, il timoniere ripete l'ordine, la nave va in condizione rossa e vira; «fuoco sulla Praetorian» → Voss rifiuta (nave amica)
- [x] Rapporti spontanei dagli eventi (rotta raggiunta, contatti, danni), schermi con dati vivi
- [x] Equipaggio seduto alle postazioni con posa procedurale (calcolata dallo scheletro: niente animazioni esterne): mani sulla console, respiro, micro-movimenti, testa e spalle che si girano verso il capitano quando parla; la tattica resta in piedi alla ringhiera
- [x] Uniformi di reparto sui corpi provvisori (comando blu, sicurezza rossa, scienze viola, ingegneria ambra, volo giallo)
- [x] Momenti di quiete: due ufficiali chiacchierano quando la plancia è calma (casa, la Lunga Notte, la nave, i piloti...)
- [ ] MetaHuman (script pronto: tools/ue_scripts/make_crew_metahumans.py; serve l'autorizzazione Epic dell'utente, vedi RICHIESTE) e labiale, gesti

## M4 (prima versione) — Battaglia
- [x] Generatore di astronavi (`art/blender/shipgen.py`): ASTRA (Aquila, Praetorian, Vigilant), Kharon Mandate (Acheron, Styx, Lethe), mercantile delle Gilde; livree per fazione
- [x] `UAstraBattleSubsystem`: navi nel sistema (doppia precisione) disegnate attorno alla Aquila, IA d'ingaggio/fuga, railgun con anticipo, missili guidati, laser, difesa di punto, scudi, scafo, esplosioni, bagliori dei motori
- [x] Scenario «Aurelia patrol»: fregata dormiente T-11 → gruppo d'attacco dell'Archon Varek Solm (Acheron + 2 Styx) → vittoria/sconfitta/ritirata
- [x] Equipaggio collegato: contatti reali, ordini di fuoco/scansione/chiamata sulla simulazione, rapporti di danno per ponte e sezione, scossoni e luci che sfarfallano ai colpi
- [x] Comandanti nemici con mente e voce radio propria: Archon Varek Solm (Acheron), Ferryman Kade (Styx), Vael (Cocytus), Quill (Phlegethon), Warden Hale (Lethe). Leggono la battaglia dal loro lato (vista privata `_mandate`), trattano davvero e decidono: continuare, cessate il fuoco, ritirata, accettare una resa
- [x] Catena di comando del Mandato: il comandante più anziano sopravvissuto ordina a tutto il gruppo; se l'ammiraglia cade o lascia il sistema il successore apre un canale con l'Aquila
- [x] Tregua: la flotta ASTRA non spara su chi ha cessato il fuoco o si ritira; se l'Aquila spara durante una tregua il Mandato torna all'attacco e chiama furioso. Esiti: vittoria, ritirata negoziata, tregua, resa accettata, Aquila fuori combattimento
- [x] Controllo del tiro reale: salve a cadenza, ingaggio che resta assegnato fuori portata, VLS con ciclo di ricarica, `cease_fire`; intercettazione continua del timone (`intercept`, distanza d'ingaggio e virata a bordata)
- [x] Sistemi dell'Aquila: budget del reattore (700%) con effetti reali (scudi = rigenerazione e assorbimento, armi = cadenza, motori = velocità), scudi a settore che contano, danni per ponte/sezione con 4 squadre di controllo danni che arrivano e riparano; incendi non presidiati che si estendono
- [x] Equipaggio più credibile: rilettura obbligatoria degli ordini eseguiti con i dati veri, iniziativa entro la propria autorità (squadre, scudi, difesa di punto), mai azioni dichiarate e non fatte; voci che non si sovrappongono e rapporti che aspettano il silenzio (raggruppati; scartati quando parla il capitano)
- [x] Bilanciamento: gruppo d'attacco di 4 navi; esiti variabili nelle prove (da vittoria con ritirata nemica a Praetorian e Vigilant perduti, Aquila al 5%)
- [x] Tavolo olografico tattico vivo (navi per fazione e stato, missili, esplosioni, anelli con scala logaritmica, etichette che non si sovrappongono)
- [x] Schermi di plancia vivi (UAstraScreensSubsystem): display principale con tavola del controllo danni per ponte/sezione, barra tattica, console di timone, operazioni, sensori, ingegneria
- [x] Canale aperto con il nemico: gli ordini restano alla plancia, le frasi per il comandante nemico vanno sul canale (router euristico + LLM per le frasi miste)
- [x] Distruzioni: lampo, palla di fuoco (M_FX_Blast), esplosioni secondarie, onda d'urto, detriti, relitto annerito alla deriva
- [ ] Navi v2 (sagome e dettagli più belli), scie dei missili, colpi sugli scudi più ricchi

## Musica adattiva
- [x] Colonna sonora originale composta in codice (`tools/music/score.py`) e suonata con un campionatore orchestrale scritto da me (`tools/music/sampler.py`) sui campioni **VSCO 2 Community Edition (CC0)**: archi, corni, tromboni, tuba, trombe, flauto, arpa, timpani, grancassa, rullante, piatti; riverbero da sala sintetico, mastering sotto i dialoghi, loop senza cuciture. Cinque brani: **Aurelia** (calma), **Tension**, **Battle**, **Aftermath**, **Transit**
- [x] `UAstraMusicSubsystem`: sceglie l'umore dalla simulazione (nemici che combattono, missili in arrivo, allarme rosso, battaglia appena finita), dissolvenze incrociate, la musica si abbassa quando parla un ufficiale; lo stacco del transito è sincronizzato in modo che il colpo cada esattamente sull'attraversamento dell'anello. Console: `astra.music.volume 0.34`, `astra.music.mood calm|tension|battle|aftermath|auto`
- Rigenerare: `tools/music/get_samples.sh` (scarica i campioni in art/_cache), `uv run --with numpy --with scipy --with soundfile python tools/music/score.py`, poi l'import con `tools/ue_scripts/import_audio.py` (SRC=art/_cache/music, DST=/Game/ASTRA/Audio/Music)

## Danni in plancia
- [x] I colpi forti fanno andare in corto plafoniere e console (`AstraBridgeFX`): pioggia di scintille che rimbalzano sul ponte e si raffreddano dal bianco al rosso, lampo arancione che illumina la stazione, crepitio elettrico (SW_Sparks, sintetizzato); di preferenza dove il Capitano sta guardando. L'ufficiale alla console colpita si ritrae e si ripara il viso. Prova: `astra.fx.sparks`

## Equipaggio di bordo (le 560 persone)
- [x] Ruolino generato con seme fisso (`Source/ASTRA/AstraCrewRoster.*`): 420 marinai, 60 piloti con nominativo, 80 fanti di marina; nome, grado, reparto, ponte e mondo d'origine. I colpi feriscono e uccidono persone vere nel compartimento colpito, i caccia abbattuti hanno un pilota (ucciso o eiettato e recuperato); l'equipaggio li nomina, il regista li ricorda, nei momenti di quiete a volte si parla di chi non c'è più

## M5 (prima versione) — Hangar e caccia
- [x] Tre gruppi di volo reali nella simulazione: Alpha (8 Falcon), Bravo (7 Hammer, siluri), Droni (12 Wasp); lancio a cadenza dal ponte di volo (dipende dalla potenza del ponte), missioni pattuglia/attacco/scorta/disturbo/ricognizione/soccorso, perdite per la difesa di punto, rientro e riarmo
- [x] Caccia nemici (Harpy) lanciati dagli incrociatori del Mandato: razzi e cannoni sull'Aquila; la pattuglia e la difesa di punto li abbattono; scie dei missili
- [ ] Hangar camminabile, pilotare un caccia in prima persona

## M6 (prima versione) — Il regista della guerra
- [x] Regista a runtime (mind/astra_mind/director.py): a ogni esito sceglie il prossimo sviluppo (incursione, soccorso, rinforzi, rifornimento, calma) coerente con il registro della campagna, e inventa i nuovi comandanti nemici (mente e voce proprie)
- [x] Vice Admiral Adrian Rourke, comandante della Settima Flotta: trasmette gli ordini, risponde quando l'Aquila chiama la flotta, può concedere rinforzi o rifornimento
- [x] Transito attraverso i Janus Gate verso nuovi sistemi: nuovo cielo con stella (nana rossa, arancione, gialla, bianco-azzurra), luce di plancia coerente, mondo principale (oceanico, desertico, ghiacciato, vulcanico con lava, gigante gassoso, roccioso) e nebulosa virata
- [x] Il transito è una manovra vera, decisa dal Capitano («Timoniere, portaci attraverso il Gate verso Cassia»): rotta automatica a tutta forza verso la corsia d'avvicinamento, poi il campo del Gate cattura la nave (timone bloccato) e la porta nel cuore dell'anello lungo una corsia di anelli di luce, sempre più veloce, fino al lampo; all'uscita l'anello è alle spalle e la nave scivola via a ~2 km/s. Una nuova rotta prima della corsia annulla la manovra
- [x] Il regista non teletrasporta: il beat "transit" sono **ordini della Flotta** (il Gate viene sintonizzato, l'equipaggio riferisce e aspetta il Capitano). Registro dei sistemi esplorati (stesso nome = stesso posto: universo con seme); tornare ad Aurelia ripristina il cielo di casa. Se la storia resta ferma 7 minuti, il regista interviene (Rourke sollecita o la guerra arriva)
  Prove: `astra.battle.gatejump` (30 km davanti al Gate) poi `astra.battle.transit Cassia`; `astra.cmd director_beat {'beat':{'type':'transit','system_name':'Meridian'}}`
- [x] Mappa strategica della guerra: il settore **Aurelia March** (11 sistemi, Gate legati a pochi altri, fazioni, minaccia), in `mind/astra_mind/war.py`, salvata in `Saved/Campaign/war.json` a ogni cambiamento. Il regista la legge e la fa evolvere (`war_news`: sistemi che cadono o vengono ripresi, notizie sulla rete della flotta riferite dalle comunicazioni); i transiti vanno solo verso sistemi collegati; l'equipaggio la conosce
- [x] Tavolo olografico in modalità **settore** («Sensori, mappa del settore sul tavolo»): sistemi colorati per fazione, collegamenti dei Gate, anello dell'Aquila, rotta di transito che pulsa, sistemi minacciati con alone; la mappa si gira verso chi la guarda
- [ ] Riprendere una campagna salvata all'avvio (oggi ogni partita riparte dalla battaglia d'apertura; la mappa salvata è già pronta)

## Prossimi passi
1. Plancia v2 secondo passaggio (dettagli, segnaletica), navi v2, scie dei missili.
2. Corridoi collegati alla plancia (porte che si aprono), hangar camminabile.
3. Equipaggio: MetaHuman + labiale, gesti.
4. Simulazione di calore (M2); caccia nemici; mappa strategica della guerra (M6); pianeta (M7).

## Come provarlo (per l'utente)
1. `tools/avvia_editor.sh` (o apri ASTRA.uproject); il livello iniziale è la plancia (`L_Bridge`).
2. Il servizio delle menti parte da solo al primo avvio della partita (oppure `cd mind && uv run astra-mind`).
3. Premi Play: sei seduto sulla poltrona del capitano (**E** per alzarti e camminare, di nuovo **E** vicino alla poltrona per sederti; le porte in fondo portano ai corridoi). Tieni premuto **V** e parla al ponte in qualsiasi lingua (al primo uso macOS chiede il permesso del microfono), oppure dalla console (`) scrivi `astra.say Allarme rosso!`.
4. La battaglia parte da sola (dopo ~80 s si sveglia la fregata, dopo ~170 s arriva il gruppo d'attacco). Per accelerare: `astra.battle.time 168`, `astra.battle.timescale 3`.
5. Quando l'Archon Solm chiama, parlagli direttamente (canale aperto): tutto ciò che non inizia con il nome/ruolo di un ufficiale va a lui. «Comunicazioni, chiudete il canale» per chiuderlo.
6. Da terminale: `tools/ue.py pie start|stop` e `tools/ue.py pie cmd 'astra.say ...'` per provare senza toccare l'editor.
7. Il Janus Gate è a 110 km sul rilevamento 070: «Timoniere, portaci attraverso il Gate verso Cassia» (circa 2-3 minuti di avvicinamento, poi la corsia). Ogni sistema ha il suo Gate alle spalle per tornare.

## Note operative
- Prestazioni (2026-09-28, standalone 1080p, battaglia): ~19 ms di mediana (≈52 fps), limitate dalla GPU (~18,5 ms: luci 2,6, ombre 2,0, Lumen 1,6, traslucenza 1,4). Gli "scatti" da ~31 ms ogni ~12 frame non sono lavoro in più: la CPU, più veloce della GPU, si blocca in attesa delle query di occlusione (trovato con Unreal Insights da riga di comando: `-trace=cpu,frame` e `UnrealInsights -NoUI -ExecOnAnalysisCompleteCmd="TimingInsights.ExportTimingEvents ..."`). Per scendere serve ridurre il costo GPU. Diagnostica schermi: `astra.screens.profile 1`
- Ricompilare il C++: `tools/ricompila.sh` (salva, chiude editor e menti, compila, riapre e aspetta l'MCP; log in Saved/Logs/build_last.log).
- Console di prova: `astra.cmd <comando> <json con ' al posto di ">` esegue qualsiasi comando di bordo come farebbe l'equipaggio.
- La sfera del cielo è opaca e ricentrata sulla camera: il suo raggio (≈490 km, scala 12000 di SM_SkySphere) è la distanza massima visibile. Prima era 16 km e nascondeva le navi lontane.
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
