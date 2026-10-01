# STATO DEI LAVORI — ASTRA

*Questo file è la memoria operativa del progetto: lo aggiorno a ogni passo. Chi riprende il lavoro (io in una nuova sessione) parte da qui.*

**Ultimo aggiornamento:** 2026-10-01 sera · **Traguardo corrente:** Piano v0.4 ([PIANO.md](PIANO.md)): F1 da chiudere, F2 e F4 in parallelo con gli agenti di supporto ([ARCHITETTURA.md](ARCHITETTURA.md)); **principio delle intelligenze** ([ARCHITETTURA §1bis](ARCHITETTURA.md))

## Piano v0.4 — dove siamo (aggiornato a ogni passo)
| Fase | Stato |
|---|---|
| **F0** Fondamenta | ✓ controlli in prima persona, banco di prova da terminale, architettura a moduli, agenti di supporto |
| **F1** La plancia viva | quasi fatta. ✓ Già pronto: **postazioni vere** (modalità persistenti eseguite a 10 Hz); **schermo principale** intelligente (telecamera, zoom, regia, sovrimpressione, scheda del canale); **tavolo olografico** leggibile dalla poltrona (si inclina verso chi guarda; rilevamenti veri, minacce, linea al bersaglio); **datapad** spinto da ops; **finestrone** in realtà aumentata; **HUD del Falcon**; **equipaggio agente** (MENTE-EQUIPAGGIO); **plancia v3**; **menu SETTINGS**; **voce v2 provata dal vivo** (parla anche chi è fuori plancia, sottotitoli giusti, «● LISTENING», il Capitano sempre per primo). ✓ **Principio delle intelligenze** applicato: le parole dell'equipaggio arrivano come le dice (via tagli, riscritture, liste di parole); il router lascia sentire tutto alla stanza e fa decidere a un modello cosa esce su un canale aperto (93–95 % sui 734 casi, 260 ms); la brevità del nemico è nel suo prompt. ✓ Il palco della voce **ripensa** invece di scartare (chi doveva dire una battuta rimasta in coda o interrotta la ridice con lo stato di adesso, la cambia o la lascia cadere). Da fare: la plancia curata nel minimo dettaglio, l'immagine nitida |
| **F2** La guerra grande | in corso (GUERRA): ✓ F2.1 danni fisici; F2.2 gerarchie a metà (gruppi di battaglia, squadriglie); poi le menti di guerra (lead), la scala, la bellezza, il regista v2 |
| **F3** Persone vere | ferma sull'autorizzazione Epic per i MetaHuman (RICHIESTE) |
| **F4** La nave intera e la distruzione | in corso: ✓ **NAVE unita** (pianta dell'Aquila: 2251 compartimenti, 1034 porte, grafo di 4450 luoghi; kit di 96 modelli; Ponte 4 e Ponte 6 costruiti; `UAstraShipPlan` trova i percorsi in 0,1 ms); Ponti 4 e 6 nel livello e camminati (57 fps nella Spina); **VITA** (la vita di bordo) in corso |
| **F5** Abbordaggi · **F6** Teletrasporto · **F7** Pianeta · **F8** Rete e Windows | da fare |

**Agenti di supporto attivi** (worktree in `.claude/worktrees/`, rami `worktree-*`; il lead prova nel gioco, unisce, rimanda i difetti):
- **GUERRA** — F2.1 fatto, F2.2 in corso: gruppi di battaglia, squadriglie, e il contratto per le menti (`group_order`, viste per parte, eventi; `GetWeaponRanges()` per tavolo e schermo) (`docs/GUERRA.md`).
- **METALFX** — un upscaler MetalFX (Apple) al posto di TSR sul Mac: prima la fattibilità (come far girare MetalFX dentro il fotogramma di Unreal senza toccare il motore), poi il plugin con interruttore `r.AstraMetalFX` e TSR come riserva; il lead confronta le immagini a parità di costo.
- **VITA** — le ~560 persone dell'Aquila sul grafo dei percorsi: turni, lavori veri, pasti, sonno, posti di combattimento, squadre di riparazione che camminano fino ai danni, feriti in infermeria; corpi solo vicino al Capitano (≤ ~40), memoria in codice, un modello piccolo quando il Capitano ci parla.
- Chiusi: ~~MENTE-EQUIPAGGIO~~, ~~ARTE-PLANCIA~~, ~~VOCE~~, ~~NAVE~~ (unita e importata il 30/9 sera: Ponti 4 e 6 nel livello, `docs/NAVE.md`), ~~ARTE-NAVI~~ (unita il 1/10: 12 navi e velivoli v3 con 21 pezzi di rottura (prua, centro e poppa di 7 navi), materiali a strati con usura, 8 decalcomanie di danno, lo scafo dell'Aquila aperto sotto il blocco per i Ponti 2–3; anteprime in `docs/progressi/navi_v3/`).

**Prove d'integrazione del lead (1/10 notte, rami locali `integ-*`, non pubblicati):**
- **GUERRA** (main + F2.2 parte 3): si unisce senza conflitti e compila; nel gioco la battaglia d'apertura è intensa e credibile
  (riflessi, caccia, missili, esche, danni, calore al 97 %, scafo 88 % in 2,5 minuti senza mente), 59,7 fps a macchina scarica. Difetti
  trovati e corretti su main: scintille delle console a ogni colpo (4 in 15 s) e incendi interni a ogni colpo (sei ponti in 30 s).
  Da fare all'unione: `PlayerEngineFactor()` al timone, `RepairPlayerSystems()` dalle squadre, `GetWeaponRanges()` su tavolo e schermo.
- **METALFX**: al primo giro il plugin si spegneva (il colore che arriva all'upscaler nel gioco vero è R11G11B10F, voleva RGBA16F);
  corretto dall'aiutante in un'ora. Al secondo giro **funziona**: 1,3 ms di MetalFX, a pari risoluzione (50 %) ~1 ms meno del TSR e
  immagine alla pari; con la risoluzione dinamica si assesta al **54 %** contro il 40–42 % del TSR (+70 % di pixel). Da sistemare
  prima dell'unione: la risoluzione dinamica non vede il suo 1,3 ms (56–57 fps) e il render thread sale a ~19 ms; poi la prova del moto.

**Fatto dal lead il 1/10 notte:** la **mappa olografica della nave** (`holo ship`): lo spaccato dell'Aquila sul tavolo, ponte per
riga, sezioni col colore del danno, incidenti con squadra e progresso, squadre che camminano dal Ponte 6, il Capitano dov'è; ops e la
mente la conoscono (prima `holo ship` ricadeva sul piano tattico). Prossimo: le navi scansionate (`GetDamageView` di GUERRA).

**1/10 mattina — il nuovo giro:**
- **GUERRA e VITA unite** (compilazione unity ok, provate nel gioco: 560 persone, 40 corpi attorno al Capitano sul Ponte 4, 60 fps)
  e collegate: motori danneggiati al timone (velocità e virata), squadre che riparano anche sistemi e affusti, squadre che arrivano
  col tempo vero dei percorsi, vittime di un colpo tra chi era davvero in quella sezione, persone vicine nel contesto delle parole e
  vita di bordo nell'istantanea della mente. **METALFX unito** (risoluzione dinamica 45–48 % contro 41–43 % a 60 fps).
- **Tavolo olografico**: anelli di gittata di rotaie e laser; sulla linea del bersaglio se lo raggiungiamo e se siamo nei suoi cannoni
  (rossa allora); **`holo ship` con un bersaglio**: la nave scansionata come ologramma della sua mesh, sezioni con la struttura, facce
  di scudo, ciò che brucia o si rompe, sistemi e affusti per le nostre navi (vista dei danni di GUERRA con la nebbia di guerra).
- **Schermo principale**: le schede dicono IN ITS GUNS / IN OUR RAILS / OUT OF RANGE; la telecamera non vede più lo scafo dell'Aquila
  tranne nella vista da fuori. Le «lastre» che restano con lo zoom forte sono gli effetti grezzi dei colpi (anelli d'urto, bolle
  degli scudi): li rifà VFX.
- **La gente di bordo parla davvero** (provato nel gioco con la mente, Mess Concourse del Ponte 4): chiamato per nome a 14 m, un
  tenente del ponte di volo risponde lui (prima un filtro di 4,5 m nel codice lo escludeva e rispondeva l'XO inventando); un ordine
  «Ponte, qui il Capitano…» detto guardando un marinaio resta del ponte. Gli ufficiali hanno l'**anagrafe e il localizzatore**
  (`crew_locate`): «chi è il cuoco di turno e dov'è?» → il Crewman Tiago Sirin, nella cucina principale a 43 m, gli altri due
  cuochi fuori servizio. Ruolino rifatto: 468 cognomi (mai più sette Kowalski, mai i cognomi del cast), un nominativo per pilota,
  il mestiere segue il grado (niente tenenti magazzinieri). Il posto del Capitano viene dalla pianta («DECK 4 · MESS CONCOURSE ·
  SECTION B», con ponte e sezione nel contesto; prima diceva «flight deck» su tutti i ponti bassi). Con `-nosound` le voci
  risultano «silent», non più «failed». Dettagli in [VITA.md §8](VITA.md).
- **1/10 pomeriggio** (limite d'uso raggiunto a metà giro; tutto compilato, provato e pubblicato):
  - **Prestazioni in battaglia**: da 51 a 58–60 fps mediani (etichette del tavolo che rifacevano il proxy a ogni fotogramma,
    1339 luci di navigazione senza lampade che tickavano, corpi di VITA parcheggiati, niente log AI); render thread da 22,6 a 11–16 ms.
    Tolti due spam del log a ogni fotogramma (sole Stationary ruotato; MetalFX che non riusciva a scrivere `TargetedGPUHeadRoomPercentage`:
    ora la risoluzione dinamica tiene davvero conto di MetalFX, +7 punti di margine).
  - **Ritmo dei rapporti** (prima battaglia con la mente dopo GUERRA: 0,26 $ in 7 minuti, battute in coda fino a 61 s): gli avvisi
    urgenti raccolgono per 0,6 s ciò che arriva con loro e aspettano la fine della battuta in corso; una battuta ripensata alla volta;
    il prompt chiede le una o due cose che contano. **Da riprovare dal vivo** (costo e coda).
  - **VFX unito** (armi, scudi a esagoni, esplosioni a strati, rotture coi pezzi v3, tutto a istanze; materiali `M_WAR_*` creati
    nell'editor, `[WarFX] effects ready`). Fuoco, fumo, traccianti, bagliori e scarichi visti nel gioco e buoni. **Difetto da
    rimandare all'aiutante VFX**: l'onda d'urto (`astra.fx.swatch`, quinta colonna in alto) è un anello scuro a segmenti invece che
    luminoso (`Saved/Play/fx_ring.png`).
  - **Equilibrio**: con tutto il gruppo d'attacco su di lei a 2–3 km (postura «flank») l'Aquila moriva in ~3,5 minuti anche senza
    mente: lo strato dei danni interni (scritto prima di GUERRA) era una spirale (calore 26→95 % in 30 s, tre radiatori in 15 s,
    condotti che si moltiplicavano). Tampone in attesa di DISTRUZIONE: calore degli scudi dimezzato, radiatori uno ogni 20 s e in
    proporzione al colpo, incidenti meno frequenti, condotti additivi con minimo 55 %; Aquila più robusta (scafo 4200, scudi 1500,
    ricarica 6, difesa di punto 6 canali). Senza Capitano regge ~4,5 minuti a bruciapelo contro quattro navi: il resto è tattica
    (Praetorian che concentra il fuoco: le menti alleate di MENTE-GUERRA) e scelte del Capitano. Nota: il banco `tools/war.py` non ha
    lo strato della nave, e un `mandate_tactics` dato prima dell'arrivo del gruppo (t<180) non ha effetto.
  - **Schermo principale**: la cattura è registrata come vista per lo streaming delle texture (a ×30 gli scafi erano a blocchi).
    Scoperta: **Nanite ignora i canali di luce** (`NaniteShading.cpp`: `bUsesLightingChannels = false // TODO`): le luci solo sul
    canale 1 (la luce del pianeta, il riempimento `astra.light.fill`, ora a 0) non toccano le navi. Il sole resta fisso rispetto alla
    nave (resa validata); farlo ruotare con l'assetto rende nere le navi in controluce sullo schermo: serve un'altra via (esposizione
    propria della cattura, o il riempimento sul canale 0 con l'interno schermato).
- **1/10 sera** — ripreso dopo il limite d'uso:
  - **Costo della plancia in battaglia**: con la raccolta degli eventi e il prompt diviso (ciò che cambia a ogni turno nell'ultimo
    messaggio, `crew.bridge_now`: la cache copre prompt di sistema e storia, 40 → 57 %) una battaglia di 7,5 minuti con un Capitano
    sensato costa **0,76 $/ora** per l'equipaggio (era 2,25 $/ora a inizio giornata). Le proposte non raccolte non si ripetono.
  - **Battaglia di prova con la mente** (formazione con la Praetorian, fuoco concentrato): il Mandato abbatte prima il Vigilant,
    poi stringe l'Aquila a 2 km; il nostro fuoco concentrato riduce l'Acheron a relitto. Le voci con l'audio vero partono tutte
    (anche via radio dal Ponte 4): i «failed» erano solo `-nosound`.
  - L'«anello scuro» di VFX era il Janus Gate dietro la fila di campioni: gli effetti sono a posto.
  - Aiutanti: **MENTE-GUERRA** e **NAVE-2** ripresi dopo il limite di sessione; **DISTRUZIONE** avviato (brief aggiornato con la
    spirale dei danni interni, il tampone e il metro `tools/survive.sh`). In costruzione l'app aggiornata (`tools/pacchetto.sh`).
- **Aiutanti al lavoro** (brief in `docs/brief/`): **MENTE-GUERRA** (ammiragli, comandanti, alleati che parlano, l'XO con
  `group_order`, la mente nel giro del banco, poi il regista v2), **VFX** (armi, scudi, esplosioni, rotture coi pezzi v3, danni sugli
  scafi, motori), **NAVE-2** (tutti i ponti: stanze nuove, istanze, luci come dati, un sotto-livello per ponte). Poi DISTRUZIONE,
  SCALA, abbordaggi, teletrasporto.

**Banco della guerra senza grafica**: `tools/war.py run|report|ship|ab` (commandlet `AstraWarSim`, ~1000× il tempo reale, deterministico per seme; vedi [GUERRA.md](GUERRA.md)).

**Strumenti di prova del lead** (gioco con `tools/play.py launch --nomind`; `tools/play.py tp X Y YAW PITCH` per le foto): `astra.battle.time 170` (arriva il gruppo d'attacco), `astra.cmd station {...}`, `astra.viewscreen.dump` (l'immagine dello schermo principale a piena risoluzione), `astra.screens.dump <Pagina>` (una console su PNG), `/state` con `context`.

## Navi v3 nel gioco (1/10 notte)
- **Importate** (12 navi e velivoli + 21 pezzi di rottura, `import_ships_v3.py`: 0 problemi), luci di navigazione rilette dalle mesh nuove
  (`extract_nav_lights.py`: era quadratico, 20 minuti bloccati → pochi secondi).
- **Il materiale `M_ASTRA_HullV3` non aveva mai compilato** (campionatore della mappa d'usura «Masks» su una texture BC7): nel gioco le
  navi v3 avevano il materiale di ripiego del motore (griglia grigia, marrone sotto il sole arancione, a scacchi). Corretto; in più
  usura e variazione macro ora vengono da una proiezione nello spazio della nave (le UV0 sono ancorate per triangolo: a scala
  frazionaria facevano scacchi diagonali). `patch_ship_materials_localuv.py` corregge in posto (ricostruire da zero un materiale in
  uso manda in crash l'editor: `make_ship_materials_v3.py` ora si ferma con un messaggio invece di cancellare).
- **Nel gioco**: la prua dell'Aquila vista dalla plancia è bellissima (piastre di toni diversi, torrette, sensori); Praetorian e
  Mandato leggibili sullo schermo principale fino allo zoom ×230. **Da sistemare** (con il modulo VFX o un passaggio sulle navi):
  graffi e strisce della mappa d'usura troppo grossi sulle superfici viste da pochi metri (sotto i finestroni); la superficie liscia
  lasciata dal generatore attorno alla plancia (senza dettagli); nomi e numeri per nave (oggi Praetorian e Vigilant hanno nome e
  numero nella geometria, sbagliati per le gemelle; l'Aquila ha ancora la decalcomania v2 del nome, forse a vuoto sul fianco più stretto).
- **Prestazioni** in battaglia dalla poltrona, aiutanti in pausa: 59,9 fps, game 8,2 ms, render 8,0 ms, GPU 14,4 ms con la risoluzione
  dinamica al 41 % (prima 50–55 %): il materiale v3 è pesante (382 istruzioni) e la cattura dello schermo principale disegna la nave
  inquadrata a tutto schermo. Con gli aiutanti al lavoro (2 simulazioni + 1 compilazione) il render thread sale a 30 ms (40 fps):
  le misure si fanno sempre con i loro processi sospesi (`kill -STOP`/`-CONT`).
- **Schermo principale nitido** (1/10 notte): la cattura della telecamera aveva l'antialiasing temporale spento (default delle
  catture 2D in UE: ripiego su FXAA) e le navi v3 erano «a puntini»; ora ha il suo TSR (storia propria) e rende a 640x267 con
  mipmap, le scritte a 1280x534: la Praetorian a x6–x10 si legge come in un film. Costo a 20 Hz con uno scafo a tutto schermo
  ~1,5–2 ms (una cattura rende sempre al 100 % del suo bersaglio, senza risoluzione dinamica). Prima: 1280x534 senza AA, ~3 ms.
- Ripartizione GPU al 70 % in battaglia (CSV `csvprofile` con `r.GPUCsvStatsEnabled 1`): ombre 2,1 + proiezione 0,7, luci locali
  3,1 (clustered 1,6 + deferred 1,5), Nanite 2,7, traslucidi 1,3, GI di Lumen 1,3 + scena 0,9, post 0,75. Prove A/B: raggi delle
  luci di plancia a 0,7 → −0,6 ms, ombre dei due faretti → −0,5 ms (comandi `astra.lights.radius|shadows`, non ancora applicati).

## Prestazioni (misure pulite 30/9 sera: macchina scarica, finestra 1600×900, plancia v3 in battaglia, prove A/B alternate)
- **Costo GPU**: ~27 ms al 100 %, ~17,5 al 70 %, ~12,6 al 50 %, ~12 al 40 %: un costo fisso di ~9–10 ms (ombre ~1,6, GI Lumen ~1,1,
  post-processing ~1,1, riflessi ~0,8, TSR ~0,7 più la sua parte alla risoluzione d'uscita, traslucidi ~0,7, personaggi ~0,6,
  Nanite) più ~14 ms per milione di pixel. La telecamera dello schermo principale a 20 Hz costa ormai ~0.
- **Al 70 %, spegnendo una cosa per volta**: TSR→TAA −2,9 ms, ombre dinamiche −3,6 (sole ~2,2, due spot ~1,1), riflessi Lumen −2,6
  (quasi tutti dalle superfici ruvide), 17 luci rettangolari −1,8, GI Lumen −1,4, traslucidi −1,0; le ombre virtuali restano la
  scelta giusta (le mappe classiche +4,4 ms); qualità di aggiornamento di TSR e densità delle sonde GI: nessun guadagno.
- **Applicato** (MacEngine.ini): riflessi tracciati solo sotto rugosità 0,25 e filtro del sole 4×2 raggi: −2,5 ms a chip caldo.
  TSR resta: a parità di costo è più nitido di TAA con più pixel (TAA perde le righe sottili e fa scalini sul bordo delle ombre).
- **Risultato**: la risoluzione dinamica si assesta al ~50–55 % a 60 fps (prima ~45 %); per il 70 % servono ~5 ms. Strade: raggi
  delle luci grandi (12–18 m, ~1 ms), materiali della plancia più leggeri (la loro ombreggiatura Nanite ~3 ms al 70 %), un
  upscaler MetalFX al posto di TSR (da valutare: plugin nostro), la modalità 30 fps del menu (immagine quasi piena).
- Il chip senza ventola si scalda in pochi minuti (la stessa scena passa da 17 a 21 ms): misure sempre alternate A/B.

## Credito AI (OpenRouter)
| Data | Credito totale | Speso | Note |
|---|---|---|---|
| 2026-09-28 | 10,00 $ | 0,00 $ | ricarica iniziale dell'utente |
| 2026-09-28 | 10,00 $ | 0,10 $ | benchmark modelli (9 configurazioni × 40 ordini) |
| 2026-09-28 | 10,00 $ | 0,13 $ | sviluppo dell'equipaggio AI (≈0,0005 $ a turno di plancia) |
| 2026-09-28 | 10,00 $ | 0,40 $ | battaglie di prova complete con comandanti nemici (≈0,001–0,002 $ a turno) |
| 2026-09-28 | 10,00 $ | 0,63 $ | squadroni, regista della guerra, ammiraglio (≈0,002 $ per decisione del regista) |
| 2026-09-28 | 10,00 $ | 0,77 $ | transiti nel Janus Gate, ordini della Flotta, prove complete del regista |
| 2026-09-28 | 10,00 $ | 1,16 $ | indagini sui relitti, campagne complete di prova, consigliere tattico, umore dell'equipaggio |
| 2026-09-28 | 10,00 $ | 1,44 $ | diario del capitano, tattica del Mandato, Port Aurelius Control, sala macchine, infermeria (dialoghi con medico e feriti) |
| 2026-09-28 | 10,00 $ | 1,74 $ | legami tra ufficiali, riposo del Capitano, calore e furtività (reazioni dell'equipaggio), discese sui mondi generati |
| 2026-09-28 | 10,00 $ | 1,96 $ | controllori di campo, flak, mensa (conversazioni ai tavoli), visite degli ufficiali in cabina |
| 2026-09-29 | 10,00 $ | 2,26 $ | abbandono nave e inchiesta (prove complete in gioco e fuori), ordini permanenti, finale d'arco, Game Master |
| 2026-09-29 | 10,00 $ | 2,62 $ | memoria degli ufficiali, nebbia di guerra, disturbo e inganni del Mandato (comandante nemico che sceglie la guerra elettronica) |
| 2026-09-29 | 10,00 $ | 2,70 $ | stile di comando del Capitano, rapporto post-azione, quadro cieco, controllore di volo, notizie da casa, prove offline dell'equipaggio |
| 2026-09-29 | 10,00 $ | 2,79 $ | misure di prestazioni per l'app (la mente partiva anche nelle prove: ora `-astra_nomind`) |
| 2026-09-29 | 10,00 $ | 3,12 $ | **prima partita dell'utente** con l'app (≈35 minuti, due sessioni: 0,33 $, cioè ≈0,5–0,6 $ l'ora di gioco con regista, nemici e memoria) |
| 2026-09-30 | 10,00 $ | 3,56 $ | agenti di supporto: prove del router su più modelli (MENTE-EQUIPAGGIO ≈0,22 $ in 1192 chiamate) |
| 2026-09-30 | 10,00 $ | 3,84 $ | MENTE-EQUIPAGGIO completato (0,40 $ in tutto), prova della mente nel gioco vero |
| 2026-09-30 | 10,00 $ | 3,93 $ | prova dal vivo della voce v2 (una battaglia intera fino all'abbandono nave) |
| 2026-10-01 | 10,00 $ | 4,69 $ | banchi di MENTE-GUERRA con le menti nel giro, prove nel gioco di GUERRA, VITA e della gente di bordo (≈0,5 m$ a risposta di un NPC) |

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
- [x] **Memoria degli ufficiali** (`mind/astra_mind/memory.py`):
  - ogni otto battute scambiate un custode della memoria rilegge cosa è stato detto e tiene solo ciò che un ufficiale ricorderebbe dopo settimane: cose personali che il Capitano ha raccontato, promesse fatte (o infrante), confidenze e come il Capitano le ha accolte, momenti che hanno segnato. Mai ordini o rapporti di routine;
  - le memorie sono in terza persona, per non confondere di chi siano: fino a 14 per ufficiale, e le promesse si tengono per ultime;
  - vanno nel prompt dell'equipaggio (affiorano quando contano, senza essere recitate) e si salvano con la storia; le promesse arrivano anche al regista e al finale;
  - prova reale: «Ferri sa che il fratello del Capitano pilota i Falcon nella Terza Flotta», «Lindqvist tiene il Capitano alla sua promessa di scendere in infermeria dopo ogni battaglia», «Voss ha raccontato al Capitano perché ha lasciato il Mandato; il Capitano ha chiesto e ascoltato».
- [x] **Gli ufficiali si rivolgono al Capitano**: nei momenti di quiete, a volte, invece di chiacchierare tra loro, un ufficiale si volta verso il Capitano con una battuta personale, fuori servizio. Nasce da ciò che ricorda del Capitano e da come stanno le cose tra loro, e invita a rispondere. Prove reali: Ferri: «Capitano, una domanda fuori servizio: suo fratello vola ancora sui Falcon con la Terza Flotta?»; Voss: «Capitano, quando ha ascoltato la mia storia non ha detto niente, e per questo le sono grata».
- [x] **Ordini permanenti** (il capitano sceglie le priorità, l'equipaggio le applica): «Tattico, fuoco libero su qualsiasi nave del Mandato entro dieci chilometri, mai sui civili», «Macchine, il calore gestitelo voi sotto il sessanta per cento». L'ufficiale li registra (`standing_order`, riformulati con condizioni e limiti), li conferma e da lì agisce da solo quando la situazione li riguarda; si revocano a voce («armi in sicura, solo su mio ordine»). Ogni ordine in vigore mette nelle mani del suo reparto gli strumenti relativi agli eventi (tattico: bersaglio, fuoco, scudi; macchine: radiatori, sfiato, potenza; volo: squadriglie; …). Gli ordini finiscono nel prompt dell'equipaggio e si salvano con la campagna. Prova reale: la Lethe entra a 8,6 km → «ordine permanente in vigore, apro il fuoco. Quattro missili in volo, scudi rinforzati a poppa»; calore al 67 % → «radiatori fuori, come da ordine permanente»
- [x] **Sottotitoli veri** (prima c'erano solo le didascalie di debug, spente nelle build di rilascio): ogni battuta compare quando parte la sua voce e resta un paio di secondi dopo la fine. Il nome è il cognome di chi parla, nel colore del suo reparto o del suo canale (radio, Mandato, ammiraglio, regista); al massimo tre righe, su un fondo scuro. Le parole del Capitano, dette o scritte, compaiono in cima.
- [x] **Ordini scritti** (la voce non è mai obbligatoria): **T** apre una riga in basso («CAPTAIN · to the crew, in any language · Enter sends · Esc cancels»), Invio la manda all'equipaggio come se fosse detta (stessa lingua automatica), Esc annulla; funziona ovunque, anche in volo. La riga tiene il fuoco finché è aperta. Prova automatica attraverso Slate stesso: `AstraTypeTest "testo"` (apre, digita tasto per tasto, preme Invio)
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

## Aspetto degli scafi (piastre, luce del pianeta)
- [x] **Piastre di scafo a scala nave** su tutte le navi: trama procedurale piastrellabile di 32 m (`tools/art/hull_panels.py`: tono di ogni piastra, giunture, rivetti, portelli, griglie, pezze, sporco nelle giunture) nel nuovo master `M_ASTRA_Hull` (`tools/ue_scripts/make_hull_material.py`) sopra il livello di dettaglio; pesi per parte in `make_ship_materials.py` (vernici forti sulle piastre, meno su telai e motori). Vernici abbassate perché al sole (EV fisso 6,6) non brucino nel bianco
- [x] **Luce riflessa dal pianeta** (earthshine): una seconda luce direzionale dal pianeta, colorata dal suo tipo, intensità secondo fase e grandezza nel cielo; senza ombre e solo sul canale di illuminazione 1 (scafi, Gate, detriti: gli interni non la ricevono). Il fianco in ombra delle navi prende l'azzurro di New Ravenna
- [x] Bagliori dei motori morbidi (`M_FX_Flare`) e dimensionati sulla telecamera
- [x] **Mercantile v2** delle Free Guilds (portacontainer a traliccio: sezione equipaggio, baie di container colorati, cisterne, sezione motori con ali radianti)
- Costo: ~+0,4 ms a 1080p in battaglia (mediana 19,7 ms)

## Plancia: segnaletica
- [x] Emblema della ASTRA Navy (stella a otto punte in doppio anello, "ASTRA NAVY", "CONCORD · LAW · LIGHT"), insegna "ASN AQUILA · CVC-01" sopra lo schermo principale, targhe retroilluminate delle stazioni col colore del reparto, cartelli "CORRIDOR 1-A" sopra le porte, emblema intarsiato nel pavimento del pozzo, chevron di sicurezza sul bordo. Rigenerare: `uv run --with pillow python tools/art/signage.py`, `blender ... art/blender/signs.py`, `tools/ue.py pyfile tools/ue_scripts/place_signage.py`

## Navi v2
- [x] Nuovo generatore procedurale hard-surface (`art/blender/hullkit.py` + `shipgen2.py`): scafi a griglia con sezioni smussate e piastre di corazza in rilievo e incassate (inset per regioni), lastre di corazza sui fianchi, torri di comando, torrette con canne e manicotti, griglie VLS, bocche d'hangar illuminate, blocchi motore a più ugelli, radiatori a lamelle, ali radianti pieghevoli, strisce di luci di bordo leggibili a chilometri, luci di navigazione
- [x] Mandato: **Acheron** (prua a doppia lama attorno al cannone spinale ad anelli, vita con gli hangar dei caccia, chiglia, torre asimmetrica), **Styx** (lunga prua a lancia, sponson posteriori con radiatori), **Lethe** (cuneo compatto). ASTRA: **Aquila** (bocche di lancio a prua, isola inclinata che porta la plancia: dal finestrone si vede la prua), **Praetorian** (cittadella e sei torri trinate), **Vigilant**
- Rigenerare: `blender -b --factory-startup --python-exit-code 1 -P art/blender/shipgen2.py -- art/export/ships_v2 [--preview <cartella>]`, poi `import_kit.py` con SRC=art/export/ships_v2, DST=/Game/ASTRA/Ships (i caccia restano quelli di shipgen.py v1)

## Musica adattiva
- [x] Colonna sonora originale composta in codice (`tools/music/score.py`) e suonata con un campionatore orchestrale scritto da me (`tools/music/sampler.py`) sui campioni **VSCO 2 Community Edition (CC0)**: archi, corni, tromboni, tuba, trombe, flauto, arpa, timpani, grancassa, rullante, piatti; riverbero da sala sintetico, mastering sotto i dialoghi, loop senza cuciture. Cinque brani: **Aurelia** (calma), **Tension**, **Battle**, **Aftermath**, **Transit**
- [x] `UAstraMusicSubsystem`: sceglie l'umore dalla simulazione (nemici che combattono, missili in arrivo, allarme rosso, battaglia appena finita), dissolvenze incrociate, la musica si abbassa quando parla un ufficiale; lo stacco del transito è sincronizzato in modo che il colpo cada esattamente sull'attraversamento dell'anello. Console: `astra.music.volume 0.34`, `astra.music.mood calm|tension|battle|aftermath|auto`
- Rigenerare: `tools/music/get_samples.sh` (scarica i campioni in art/_cache), `uv run --with numpy --with scipy --with soundfile python tools/music/score.py`, poi l'import con `tools/ue_scripts/import_audio.py` (SRC=art/_cache/music, DST=/Game/ASTRA/Audio/Music)

## Equipaggio che ragiona sulla battaglia
- [x] **Consigliere tattico**: in combattimento la mente calcola dalla telemetria i problemi seri (armi assegnate a un bersaglio fuori portata mentre il timone insegue un altro contatto, navi amiche o civili in crisi, scudi bassi, ostili vicini non ingaggiati, missili agli sgoccioli, scafo critico) e l'XO o l'ufficiale competente lo dice al Capitano con una raccomandazione concreta, al massimo ogni 40 s, mai mentre il Capitano parla. Trovato giocando: senza, l'Aquila inseguiva la fregata mentre le scorte morivano da sole
- [x] Una sospensione del fuoco del Mandato è una **tregua**, non la fine della battaglia: l'ingaggio finisce con navi distrutte o in ritirata, con la resa, o se la tregua regge due minuti (poi il nemico si ritira verso il Gate); i caccia nemici non decollano mentre il loro comandante tiene il fuoco
- [x] Bilanciamento della battaglia d'apertura: la Praetorian è la nave più robusta in campo; se l'Aquila resta a guardare le scorte reggono a lungo ma l'Aquila viene martellata; se combatte bene la vittoria arriva con perdite (caccia, piloti, mercantile) e il nemico si ritira malconcio. Console `astra.battle.status` per il bilanciamento

## Il nemico che ragiona (tattica del Mandato)
- [x] Il comandante più alto in grado del Mandato **comanda davvero il suo gruppo**: ogni ~40 s di battaglia legge la situazione dai suoi sensori (le sue navi, bersagli, distanze, scudi e settori rinforzati dell'ASTRA, caccia in volo) e dà ordini via datalink (`command_group`): **fuoco concentrato** su una nave, **postura** (standard, ravvicinata sotto i laser, a distanza 8-9 km fuori dai laser, **aggiramento** verso il settore di scudo debole, schermo dell'ammiraglia), **salve di missili simultanee** per saturare la difesa di punto o risparmio, lancio o trattenimento dei caccia, e **ritirata** quando la battaglia è persa (per salvare gli equipaggi)
- [x] La simulazione esegue gli ordini (`EnemyTactics` in C++) e i sensori dell'Aquila vedono ciò che si vede davvero («spostano il fuoco su di noi», «si allargano per aggirarci, lontano dal settore rinforzato», «aprono la distanza»): l'equipaggio reagisce (Voss riequilibra gli scudi, l'XO propone di interporsi per salvare il Vigilant)
- [x] Esempio reale: Solm vede gli scudi di prua rinforzati → aggira; vede i missili abbattuti uno alla volta → salva simultanea; il Vigilant indebolito → fuoco concentrato da distanza; gruppo a pezzi → ritirata con motivazione in personaggio. Le svolte (nuovo bersaglio, ritirata) finiscono nel registro della storia
- [x] **Il Capitano coordina la flotta**: «Praetorian, Vigilant: concentrate il fuoco sull'Acheron» → le comunicazioni inoltrano via datalink (`fleet_request`: fuoco concentrato, copriteci, stringete, restate a distanza, cessate il fuoco, fuoco libero) e le navi confermano ed eseguono
- Bilanciamento: salva massima 6 celle per incrociatore, 3 per cacciatorpediniere, poi ricarica doppia; primi ordini 20 s dopo l'inizio. Con un Capitano pronto la vittoria costa (Vigilant perso, Aquila all'84%); un Capitano passivo viene punito

## Danni in plancia
- [x] I colpi forti fanno andare in corto plafoniere e console (`AstraBridgeFX`): pioggia di scintille che rimbalzano sul ponte e si raffreddano dal bianco al rosso, lampo arancione che illumina la stazione, crepitio elettrico (SW_Sparks, sintetizzato); di preferenza dove il Capitano sta guardando. L'ufficiale alla console colpita si ritrae e si ripara il viso. Prova: `astra.fx.sparks`

## Equipaggio di bordo (le 560 persone)
- [x] Ruolino generato con seme fisso (`Source/ASTRA/AstraCrewRoster.*`): 420 marinai, 60 piloti con nominativo, 80 fanti di marina; nome, grado, reparto, ponte e mondo d'origine. I colpi feriscono e uccidono persone vere nel compartimento colpito, i caccia abbattuti hanno un pilota (ucciso o eiettato e recuperato); l'equipaggio li nomina, il regista li ricorda, nei momenti di quiete a volte si parla di chi non c'è più

## M5 (prima versione) — Hangar e caccia
- [x] Tre gruppi di volo reali nella simulazione: Alpha (8 Falcon), Bravo (7 Hammer, siluri), Droni (12 Wasp); lancio a cadenza dal ponte di volo (dipende dalla potenza del ponte), missioni pattuglia/attacco/scorta/disturbo/ricognizione/soccorso, perdite per la difesa di punto, rientro e riarmo
- [x] Caccia nemici (Harpy) lanciati dagli incrociatori del Mandato: razzi e cannoni sull'Aquila; la pattuglia e la difesa di punto li abbattono; scie dei missili
- [x] **Ponte di volo percorribile** (Deck 9, `art/blender/hangar.py`, `tools/ue_scripts/build_hangar.py`, dati in `data/ship/aquila_hangar.json`): navata di 145 × 56 m allineata alla prua dell'Aquila v2, due tubi di lancio che sboccano nelle bocche di prua (con campi di contenimento), binari delle catapulte, passerelle, cabina di controllo vetrata, 8 Falcon e 7 Hammer negli stalli, 12 Wasp nelle rastrelliere, personale di ponte. I velivoli seguono la simulazione: al lancio rullano fino al binario e vengono catapultati nel tubo (suono della catapulta), all'atterraggio tornano negli stalli; i caccia della simulazione ora nascono proprio dalle bocche di prua. Le luci dell'hangar si accendono solo quando il Capitano è laggiù
- [x] **Ascensore** tra il corridoio di babordo della plancia e il ponte di volo (E davanti alle porte; console `AstraUse`)
- [x] **Pilotare un Falcon in prima persona** (`AstraFighterPawn`, abitacolo `art/blender/cockpit.py`): sul ponte di volo, **E** accanto a un Falcon di Alpha → nell'abitacolo sulla catapulta di sinistra (vista vera dell'hangar, dei caccia parcheggiati e dei tubi); **W** per dare motore e la catapulta ti spara fuori dalla bocca di prua. In volo: mouse = cloche virtuale (beccheggio/imbardata), A/D rollio, W/S manetta (X a zero), Q/E e Spazio/Ctrl traslazioni, Shift postbruciatore, Alt per guardarsi intorno, **tasto sinistro cannoni**, **destro missile** sul bersaglio agganciato (12°, 6 km, 1,2 s). HUD proiettato sul tettuccio: reticolo, cloche, parentesi sui nemici, riquadro d'aggancio con distanza, **indicatore di anticipo** per i cannoni, freccia verso l'Aquila, velocità/manetta, scafo, scudi, missili. Il modello di volo è nel riferimento della portaerei (manetta a zero = in formazione con l'Aquila). **F** vicino alla bocca del tubo per rientrare; se ti abbattono ti eietti e un Wasp riporta la capsula. Il Falcon è una vera unità della simulazione: i nemici e la difesa di punto possono colpirlo, i tuoi colpi e missili fanno danni veri; l'equipaggio sa dove sei (l'XO prende il comando, Price ti segue sul canale di controllo) e puoi dare ordini al ponte via radio (V)
- [x] Duelli: due Harpy si staccano e inseguono il Falcon del Capitano quando è vicino (cannoni in coda, razzi a guida); la difesa di punto delle navi nemiche lo colpisce con molti colpi piccoli (c'è tempo per sganciarsi); **C: esche** (4 salve di chaff/flare: la maggior parte dei cercatori perde il bersaglio); colpi sentiti in cabina (scossa, rumore), allarme missile che lampeggia sull'HUD. Suoni dell'abitacolo sintetizzati: motori legati a manetta e postbruciatore, bip del cercatore, tono d'aggancio, allarme missile
- Prova: `astra.battle.spawn harpies 8 0` (un cacciatorpediniere che lancia quattro Harpy), `astra.fly.home`, `astra.fly.face <contatto>`; comandi del pawn da console: `AstraThrottle`, `AstraStick`, `AstraGuns`, `AstraMissile`, `AstraLand`
- [x] **M7 (prima versione) — Discesa su New Ravenna**: in volo, col muso sul pianeta, **G** avvia il rientro (plasma che avvolge il tettuccio, rombo, scossoni); al culmine la zona di superficie prende il posto dello spazio e il Falcon esce a 8,5 km sopra il mare a sud della baia di Port Aurelius, con le nuvole sotto. Volo in atmosfera (330 m/s, postbruciatore 520), collisioni con terreno e mare, **F** per posarsi (sotto 90 m e 75 m/s), **E** per scendere a piedi, di nuovo **E** accanto al Falcon per risalire, **W** per decollare; oltre 14 km di quota si torna in orbita accanto all'Aquila. Schianto = eiezione, soccorso di Port Aurelius e ritorno sul ponte di volo (Falcon perso). Intanto la guerra continua lassù e l'equipaggio ti segue via radio
- Tecnica: la zona di superficie è nello stesso mondo, 1000 km sotto la plancia (tag `ASTRA.Planet.NewRavenna`, costruita da `tools/ue_scripts/build_newravenna.py`): terreno Nanite (`art/blender/terrain.py`: 16 tessere da 3 km a 8 m + anello di 64 km, erosione, baia, promontori, isole, catena innevata), oceano (`M_NR_Ocean`, onde procedurali `tools/art/water_normals.py`), `SkyAtmosphere` (raggio 6000 km), nuvole volumetriche, nebbia, luce del cielo in tempo reale; `UAstraShipSubsystem::SetPlanetside` scambia cielo, luci ed esposizione. Materiale `M_ASTRA_Terrain` (`tools/ue_scripts/make_planet_materials.py`) con texture CC0 ambientCG (Rock035, Grass004, Ground037, Ground054, Snow010A). KillZ del livello a -1e10
- Prova da console: `astra.fly.face planet` poi `AstraDescend`; `AstraFacePlanet x y z` (m, zona); `astra.planet go|back` (a piedi allo spazioporto e ritorno); avvio con `-astra_planet` per le misure
- Prestazioni sul pianeta (1080p, standalone): ~19,7 ms di mediana, come la battaglia nello spazio (nuvole volumetriche + atmosfera + terreno Nanite)
- [x] Gamepad per il Falcon: stick sinistro vola, destro imbardata/sollevamento, grilletti manetta, A cannoni, B missile, RB postbruciatore, LB esche, Y recupero/atterraggio, X discesa
- [x] **Port Aurelius**: spazioporto sul pianoro sopra la baia (`art/blender/spaceport.py`: piazzale in cemento con linee di rullaggio, 5 piazzole con anello dipinto, frecce e luci di bordo, torre di controllo con cabina vetrata e faro, 3 hangar, terminal vetrato) e la città lungo la baia (243 edifici in tre tipi: torri di vetro, blocchi a fasce, blocchi a gradoni, disposti dal generatore del terreno); il Falcon ha il carrello
- [x] **Port Aurelius Control** (`mind/astra_mind/port.py`): il controllore Dario Vance (voce propria, via radio) chiama Eagle appena uscito dal rientro, assegna una piazzola, dà vento e rotta, risponde quando lo si chiama («Port Aurelius, qui Eagle...», «Torre...»), accoglie all'atterraggio e saluta alla partenza; conosce la guerra come la sente la gente di New Ravenna («quaggiù tutti col fiato sospeso per le notizie da Thule»)

- [x] **Gli scafi sono solidi** (`UAstraBattleSubsystem::PilotCollision`): un Falcon che vola contro l'Aquila (il raggio del suo movimento contro le collisioni complesse dello scafo, tranne all'imbocco del tubo di lancio e recupero) o contro un'altra nave (il riquadro orientato del suo scafo) è perduto. Parte il solito recupero: eiezione, un Wasp esce a prendere la capsula. Prova reale: «Eagle flew into the Aquila's hull» → «la capsula del Capitano è a bordo, illeso». Le zone di bordo (Sala Macchine, Infermeria, Mensa) contano solo il Capitano a piedi.

## Sala Macchine (Deck 7) e ascensore a tre ponti
- [x] **Main Engineering** (`art/blender/engineering.py`, `tools/ue_scripts/build_engineering.py`, dati in `data/ship/aquila_engineering.json`): sala di 42 × 28 × 14 m a poppa dell'isola, il **nucleo del reattore** dal pozzo al soffitto (doghe scure, fessure da cui si vede il plasma azzurro che pulsa, bobine di contenimento), condotti che si irradiano verso le pareti, balconata con scale, linee del refrigerante blu, console dei tecnici, e il **tavolo del display di sistema** con lo schema vivo della nave; luci di zona accese solo quando il Capitano è laggiù
- [x] Il **Capo ingegnere Emeka Okonkwo** («il Vecchio»: burbero, paterno, chiama la nave «lei») è un ufficiale dell'equipaggio con voce propria: in sala macchine risponde di persona, altrimenti via interfono; i tecnici di guardia sono ai loro posti
- [x] **Ascensore a tre ponti**: E alle porte apre il pannello (1 plancia · Deck 1, 2 sala macchine · Deck 7, 3 ponte di volo · Deck 9); l'equipaggio sa dove si trova il Capitano
- [x] Quando il Capitano è lontano dalla plancia (ponte di volo, sala macchine, Falcon, New Ravenna) le voci degli ufficiali arrivano via interfono/radio

## Infermeria (Deck 6) e ascensore a quattro ponti
- [x] **Medbay** (`art/blender/medbay.py`, `tools/ue_scripts/build_medbay.py`, dati in `data/ship/aquila_medbay.json`): reparto di 30 × 18 m nello scafo inferiore, un ponte sopra la sala macchine. Pavimento chiaro in resina, pareti bianche a pannelli con lesene, corrimano paracolpi, luce indiretta a sguscio; **12 letti** con schienale rialzato di 20°, materasso e cuscino, sponde, testaletto a parete (gas medicali, luce, chiamata), **monitor dei parametri vitali** su braccio e asta della flebo; **tende a pieghe** tirate tra i letti e raccolte sul corridoio (binari a soffitto); banco di guardia con schermi, armadi delle scorte a vetrina, lavabo, **tabellone del reparto**; bancone centrale con schermi su due lati e il terminale del medico; **sala operatoria** dietro una vetrata con porta scorrevole: tavolo operatorio, due lampade scialitiche, carrello d'anestesia, carrelli dei ferri, **scanner diagnostico ad anello**, armadi e display con la scansione; croci mediche luminose. Tessuti CC0 ambientCG (Fabric036 lino, Fabric032 cotone), schermi medici disegnati (`tools/art/ui_screens.py med`: monitor normale e d'allarme, standby, tabellone, scanner). Luci di zona accese solo quando il Capitano è lì
- [x] **I feriti veri del ruolino nei letti**: ogni ferito ha una **ferita** coerente con ciò che ha colpito il compartimento (breccia: decompressione, barotrauma, schegge; incendio: ustioni, fumo; condotti: folgorazioni, aritmie; eiezione dei piloti: fratture, ipotermia), una **condizione** (stabile, grave, critico) e un **letto** (oltre 12: brande nel passaggio). Le condizioni evolvono col giro dei medici ogni minuto: i critici migliorano o, raramente, **muoiono per le ferite** (lo riferisce il medico, il regista lo ricorda), i gravi si stabilizzano, gli stabili tornano in servizio. Tutto salvato nella campagna
- [x] Nei letti ci sono i **pazienti** (`AAstraPatient`): manichini sdraiati con posa procedurale nuova (`Lying`: schiena sullo schienale, gambe distese, mani sul ventre o lungo i fianchi, respiro lento, la testa si gira e si china verso il Capitano quando parla), camice, **coperta modellata sul corpo** fino alla vita con il risvolto del lenzuolo, monitor acceso (con allarmi se critico); letti vuoti rifatti con la coperta piegata e il monitor in standby
- [x] **Surgeon Commander Irene Lindqvist**, medico di bordo (dalla bibbia): ufficiale dell'equipaggio con voce propria, pragmatica e brutalmente sincera; in infermeria risponde di persona, altrimenti via interfono. Esempio reale: «Nove feriti, Capitano. Tre critici… La Fujita è la peggiore: ustioni di terzo grado su entrambe le gambe. Se non regge le prossime ore, le amputo sotto il ginocchio.»
- [x] **I feriti parlano**: in infermeria il Capitano può rivolgersi a un paziente per nome; risponde lui, con una voce sua (scelta per genere tra le voci libere) e parole sue, secondo ferita e condizione (i critici sono sedati: spiega il medico). Esempio reale (1,3 s): «Bruciature di secondo grado su braccia e mani, Capitano. Un condotto è saltato in batteria… La dottoressa dice che le dita tornano. Non è la prima volta che mi brucio, e la batteria due è ancora mia.»
- [x] **Ascensore a quattro ponti**: 1 plancia · Deck 1, 2 infermeria · Deck 6, 3 sala macchine · Deck 7, 4 ponte di volo · Deck 9 (tasti 1-4). Targhe nuove sopra le porte (MEDBAY con la croce, MAIN ENGINEERING che prima prendeva in prestito una targa di plancia)
- [x] **Legami tra ufficiali e Capitano**: a ogni svolta il regista aggiorna, solo per chi è cambiato, come ogni ufficiale vede il Capitano e perché (fiducia guadagnata o persa, dubbi su un ordine, lealtà, risentimento, un debito), salvato in `story.json`; l'equipaggio lo lascia trasparire nel modo di parlare. La nave registra dove va il Capitano (infermeria, sala macchine): esempio reale dopo la prima vittoria, *«Lindqvist watched the Captain come down to Deck 6 and stand among the wounded instead of staying on the bridge — she will remember that»*, *«Serra held the conn… she trusts the Captain a little more for leaving the bridge in her hands»*, e il regista ha dato una pausa «per sentire cosa pensa l'equipaggio del Capitano che è sceso in infermeria»
- [x] Ogni letto ha la sua posizione vista dall'ingresso («la seconda a destra entrando dall'ascensore»): medico e feriti la dicono giusta; ogni evento di bordo ora è anche nel log (`[Event]`)
- Prove: `astra.medbay admit 8` (feriti da colpi casuali), `astra.medbay care 10` (dieci minuti di cure), `astra.medbay go` (nel reparto); avvio con `-astra_medbay` per le misure
- Prestazioni (standalone 1080p, profilo A): 19,0 ms di GPU in infermeria, come la plancia (erano 25,3 ms con 32 luci di cui 10 con ombre: ora 11 luci lunghe, 3 con ombre)

## Mensa (Deck 4) e ascensore a cinque ponti
- [x] **La Mensa** (Mess Hall, Deck 4 · Section B; `art/blender/messhall.py`, `tools/ue_scripts/build_messhall.py`, dati in `data/ship/aquila_mess.json`):
  - sala di 38 × 20 m a mezza nave, con i costoloni della nave e le travi, pannelli luminosi sopra i tavoli, condotti;
  - banco del rancio con le vaschette di cibo e il parafiato, e oltre il passavivande la cucina (forni, fornelli, pentole);
  - lavagna del menù: agnello brasato con orzo, riso aureliano, verdure dall'idroponica B, caffè vero da Meridian;
  - angolo bevande, dodici tavoli lunghi con panche imbottite, bacheca con i biglietti, fontanella, verdure idroponiche sotto la luce di crescita;
  - due grandi **schermi vivi** a poppa:
    - «FLEET NEWS»: la Marca sistema per sistema e le ultime notizie della rete di flotta, dalla mente;
    - «IN MEMORIAM»: i nomi dei caduti dell'Aquila presi dal ruolino, con il reparto.
- [x] L'equipaggio fuori servizio:
  - dodici persone vere del ruolino ai tavoli, con il vassoio davanti e l'uniforme del loro reparto; cambiano a ogni turno di mezz'ora, mai sotto gli occhi del Capitano, e chi viene ferito o ucciso lascia il posto a un altro;
  - il cuoco, Petty Officer Tomas Wren, dietro il banco;
  - due persone che vanno e vengono tra banco e tavoli.
- [x] **Conversazioni ascoltate** (`mind/astra_mind/mess.py`): mentre il Capitano è in mensa, ogni 35-70 s due o tre persone allo stesso tavolo parlano tra loro, con la loro voce e dal loro posto. Temi: il lavoro sul loro ponte, gli amici in infermeria, casa, la guerra, le decisioni del Capitano come le hanno capite. Il testo nasce da chi sono e da cosa ha vissuto la nave (eventi, caduti, campagna, umore, legami). Esempi reali:
  - all'ingresso: «Attenzione, il Capitano è appena entrato. Niente scenate, continuiamo a mangiare»;
  - «sul deck 7 stamattina hanno ricaricato i banchi VLS come se domani si sparasse. Nessuno ci dice niente».
- [x] Il Capitano può parlare con loro, per nome, al tavolo o al cuoco; risponde l'agente dell'equipaggio con i loro id (`mess3`, `mess_cook`). Esempio: «Buongiorno, Capitano! … il rancio oggi è da ammiraglio, se mi permette» (Wren) e «Confermo, Capitano: la zuppa vale il turno di guardia. Anche se il pane è di ieri».
- [x] Ascensore a **cinque ponti** (tasti 1-5): Bridge · Mess Hall · Medbay · Main Engineering · Flight Deck. I cartelli dicono «DECKS 1 · 4 · 6 · 7 · 9».
- Le voci di mensa e infermeria partono sempre dal posto di chi parla: un tavolo lontano si sente più piano, mai via radio.
- Prestazioni (1080p, standalone, editor chiuso): 18,8 ms di mediana. Quattro luci lunghe, una per fila di tavoli, al posto di otto: le luci passano da 3 a 2 ms. Avvio di prova: `-astra_mess`.

## Alloggi del Capitano (Deck 1)
- [x] **Captain's quarters** (`art/blender/quarters.py`, `tools/ue_scripts/build_quarters.py`, dati in `data/ship/aquila_quarters.json`): la porta in fondo al corridoio di dritta (prima un tappo cieco, ora paratia con porta scorrevole) apre sulla cabina del Capitano, 8,6 × 9,2 m: moquette blu, legno scuro (boiserie, mobili), pareti calde, soffitto a cassettoni con luce indiretta e faretti; scrivania sotto il **finestrone di poppa** con terminale del diario di bordo, lampada, tazza; poltrona del Capitano e due sedie; divano, tavolino e poltrona; **branda** nell'alcova con luce da lettura e mensola (libri, una foto); libreria; angolo cottura con la **macchina del caffè**; credenza sotto l'oblò di dritta con il **modellino dell'Aquila** (1:1000); la **carta dell'Aurelia March** a parete (disegnata dai dati della guerra, `tools/art/ui_screens.py quarters`); la targa della nave. Legno Wood051 e moquette Carpet012 (CC0 ambientCG). Luci calde di zona accese solo con il Capitano dentro
- [x] **La vista**: dal finestrone si vede l'intera Aquila che si allunga verso poppa sotto New Ravenna
- [x] **Riposare**: E accanto alla branda → dissolvenza al nero, «RESTING · the XO has the conn»; il mondo corre 6 volte più veloce (battaglie, cure dell'infermeria, il regista) finché succede qualcosa che il Capitano deve sapere: allora l'XO lo sveglia (esempio reale: dopo 1,1 minuti di nave la fregata T-11 accende i motori e il Capitano si sveglia con i rapporti di Sensori e Tattica); altrimenti ci si alza da soli (E) o dopo 150 s reali, e l'XO fa il punto. L'equipaggio sa se il Capitano è in cabina o dorme
- [x] **Visite degli ufficiali** (`mind/astra_mind/visits.py`, `UAstraShipSubsystem::StartVisit/TickVisit`, `AAstraCrewMember::Visit/Leave`): quando il Capitano entra in cabina, dopo una ventina di secondi la storia decide se qualcuno ha un motivo per venire **di persona** — mai per i rapporti di routine (quelli passano dall'interfono), solo per ciò che va detto faccia a faccia: la dottoressa con i morti di una battaglia, l'XO con un dubbio che in plancia non esprime, il Capo macchine con una protesta, un ufficiale con una questione personale (il suo legame col Capitano). Decide dagli eventi, dalla campagna, dai caduti, dall'umore e dai legami; il più delle volte non viene nessuno (al massimo una visita ogni 12 minuti). Prova offline su tre situazioni: inizio tranquillo → nessuno; dopo una battaglia con due morti → la dottoressa, «per dire i nomi e lo stato dei feriti faccia a faccia, e dire chiaramente quanto è costato»; dopo che il Capitano ha scavalcato due volte Okonkwo tenendo il motore al 150 % → il Capo macchine, «tre dei miei sono in infermeria con ustioni… non lo dirà all'interfono»
  - l'ufficiale lascia davvero il suo posto e **cammina**: dalla sua postazione (giù dalla pedana di comando, su per le scale del pozzo, dietro il tavolo olografico), fuori dalla porta di dritta e lungo il corridoio 1-A; dottoressa e Capo salgono con l'ascensore e attraversano la plancia dal corridoio di babordo. Le porte si aprono per chi cammina
  - alla porta della cabina si ferma: suona il **campanello** (due note, sintetizzato: `SW_Door_Chime`), poi entra, si ferma un passo e mezzo dentro e guarda il Capitano; parla per primo, con la sua voce, dal punto in cui sta. Esempio reale (dottoressa): «Capitano, sono salita io perché non volevo che lo leggesse in un rapporto…»
  - è una conversazione vera: il Capitano risponde senza nominarlo; quando lo congeda («torni pure dai suoi pazienti») l'equipaggio chiama `dismiss_visitor` e lei saluta: «Grazie a lei, Capitano. Se mi vuole, sono in Medbay, ponte sei.» Se ne va da solo dopo 150 s di silenzio, se il Capitano esce (o si mette a dormire) e, in **allarme rosso**, torna di corsa alla sua postazione
  - prove: `astra.cmd visit {'officer':'doctor','reason':'...'}` (con il Capitano in cabina), `astra.walk <postazione> [back]` per guardare il percorso senza visita
- [x] **Fuori**: il blocco della cabina rivestito di piastre di scafo con i suoi finestroni illuminati, su un piedistallo che affonda nel pendio di poppa dell'isola; accanto la torre dell'ascensore di plancia; carenature sotto i due corridoi dietro la plancia (prima galleggiavano sopra l'isola) — `SM_SHIP_ASTRA_AquilaBridgeBlock`, con la luce del pianeta come lo scafo

## La perdita dell'Aquila: abbandono nave, capsule, inchiesta, nuovo comando
Prima, a scafo zero, la nave veniva «distrutta» senza conseguenze. Ora perdere è una svolta della storia, mai un vicolo cieco.
- [x] **Abbandono nave** (`UAstraShipSubsystem::StartAbandon`): per ordine del Capitano (strumento `abandon_ship`; l'XO lo contesta una volta se la nave non è spacciata; il reattore viene sovraccaricato perché il nemico non la prenda) oppure da solo quando lo scafo arriva a zero (il contenimento del reattore cede).
  - conto alla rovescia: 110 s su ordine, 70 s se cede il reattore;
  - allarme rosso, motori fermi, e l'**allarme generale delle marine vere**: 7 suoni brevi e 1 lungo (`SW_Abandon_Alarm`, sintetizzato), che si ripete finché il Capitano è a bordo;
  - l'equipaggio parla corto e concitato: l'XO lo annuncia a tutti e indirizza il Capitano alle capsule, gli ufficiali contano la loro gente;
  - la percentuale di evacuati cresce nel tempo, con gli annunci a 60, 30 e 10 secondi.
- [x] **Le perdite dipendono dalla decisione**: ordinare presto salva più persone. Prova reale: 97 % evacuati con l'ordine dato presto, circa 88 % se si aspetta il cedimento del reattore. Chi non riesce a uscire viene preso dal ruolino vero (`FAstraCrewRoster::LostWithShip`: prima i feriti critici che non si potevano spostare, poi i macchinisti rimasti al reattore) e finisce sul muro della memoria.
- [x] **Le capsule** (`art/blender/lifepod.py`, `tools/ue_scripts/build_lifepods.py`, `AAstraLifepodHatch`, `AAstraLifepod`):
  - due portelli nel corridoio 1-A: **1-A** a babordo accanto all'ascensore, **1-B** a dritta verso la cabina del Capitano;
  - ogni portello ha la cornice gialla e nera, la porta con l'oblò rosso, il cartello e una spia: verde = sigillato, ambra lampeggiante = imbarco, rossa = partita;
  - **E** al portello: il Capitano entra nella capsula, legato al sedile davanti all'oblò. Si sentono i bulloni esplosivi, la rotaia e il motore; poi la deriva a circa 26 m/s, e i giroscopi tengono l'oblò puntato sulla nave (il mouse guarda intorno);
  - dai fianchi dell'Aquila escono decine di altre capsule, ognuna col suo faro arancione di soccorso;
  - se il tempo scade, Serra trascina il Capitano nell'ultima capsula.
- [x] **La fine, vista dall'oblò** (circa 2-3 km): esplosioni che corrono lungo lo scafo, poi la rottura del reattore a poppa (lampo bianco, palla di fuoco, anello d'onda d'urto, detriti). Lo scafo resta bruciato e scuro con le braci nelle ferite; il nome e le luci di navigazione spariscono. Nella capsula si sente e si sente tremare (`SW_Breach_Felt`), e gli ufficiali parlano dalla radio delle altre capsule.
- [x] **Dopo** (`mind/astra_mind/loss.py`):
  - il regista decide dallo stato vero chi trova la capsula: un soccorso della 7ª Flotta, la cattura da parte del Mandato, oppure ore o giorni alla deriva;
  - poi una voce alla radio e cartelli su schermo nero (`story_card`);
  - se il Capitano è catturato: un ufficiale del Mandato lo interroga (interattivo, a voce o per iscritto), poi arriva lo scambio di prigionieri;
  - poi la **Commissione d'inchiesta** della 7ª Flotta, **interattiva**: presiede Rourke, siedono il capitano Okafor e il comandante Vale (giudice avvocato). Leggono il **diario del Capitano** e la campagna, fanno almeno tre domande a turno e il Capitano risponde con parole sue. Prova reale: «Ho visto il suo diario… Parliamo della tattica, non della poesia»;
  - il verdetto (encomio, proscioglimento o biasimo) e poi il **nuovo comando**: la gemella CVC-03, ribattezzata Aquila, qualche settimana dopo;
  - il salvataggio viene riscritto: nave nuova, santabarbara e gruppo aereo pieni, i caduti restano caduti, i feriti sono guariti. Il livello riparte, l'XO dà il benvenuto a bordo e il regista racconta cosa è cambiato nella Marca;
  - la nuova nave porta il suo numero di scafo (CVC-03, poi -04, -05): lo dicono il nome sui fianchi, la targa di plancia, il display principale e il muro della memoria, che ora ricorda «CVC-01 AND CVC-03».
- Prove: `astra.cmd abandon_ship {}`, poi al portello `AstraUse` (o **E**); `slomo 5` per accelerare. Il dopo si prova anche fuori dal gioco, con un gioco finto e risposte scritte del Capitano.

## La forma della guerra: atti, battaglia decisiva, finale
- [x] **Tre atti per arco** (`director.py`: `arc`, `act`, `act_beats`, salvati con la storia):
  - I, *la tempesta si addensa*: il Mandato mette alla prova la Marca, il suo piano si scopre a pezzi;
  - II, *la Marca brucia*: l'offensiva allo scoperto, sistemi che cambiano mano, comandanti già incontrati che ritornano;
  - III, *il cancello*: le forze si radunano per la battaglia decisiva.

  Il regista sa in che atto è e quando una svolta apre il successivo.
- [x] **La battaglia decisiva** (nuovo tipo di scena `decisive`):
  - la flotta principale del Mandato (4-8 navi, un Acheron in testa, fino a 8 per ondata, con i caccia delle capitali) contro l'Aquila e i suoi alleati (1-3 navi ASTRA che si uniscono);
  - si combatte dove lo dicono la mappa e le scelte del Capitano: l'assalto del Mandato ad Aurelia, oppure l'attacco della 7ª Flotta all'Ancoraggio di Erebus;
  - prova reale: la Warden-General Isolde Marrow arriva da Thule con otto navi; Rourke: «la 7ª Flotta la incontra al gate di Aurelia, come avevate detto», ripreso dal diario del Capitano.
- [x] **Il finale dell'arco** (`finale.py`):
  - l'esito è calcolato dai fatti: prima il risultato della battaglia, poi la mappa della guerra, poi le scelte del Capitano (clemenza, promesse mantenute o infrante, ufficiali ascoltati o scavalcati). Può essere vittoria, sconfitta, stallo o armistizio (solo se la storia se l'è guadagnato);
  - Rourke parla sulla rete di flotta, poi i cartelli su schermo nero: il nome della battaglia, cosa ha deciso, 4-6 righe di epilogo sui destini delle persone come li hanno fatti i legami col Capitano, e infine «THE WAR GOES ON»;
  - la mappa della guerra viene ridisegnata e comincia un nuovo arco;
  - se l'Aquila va perduta nella battaglia decisiva, il finale si racconta dopo il nuovo comando;
  - prestazioni (standalone 1080p, editor chiuso, `-astra_decisive`: 2 cacciatorpediniere alleati e 8 navi del Mandato con i caccia delle capitali, davanti alla plancia): mediana 20,1 ms (circa 50 fps), GPU 19,9 ms, game thread 3 ms; come una battaglia normale;
  - prova reale: «The Battle of the Aurelia Gate»: vittoria col 41 % di scafo e il Resolute perduto. Nell'epilogo Voss rilegge l'ordine del drone; Lindqvist «smise di contare i vivi e cominciò a nominare i morti»; il Capitano lascia andare le navi mutilate «come era stata lasciata andare la Lethe»; i feriti di Varek riconsegnati a Veyra: «il Capitano mantiene la parola, una reputazione pericolosa in questa guerra».

- [x] **Modalità Game Master**: il giocatore parla direttamente alla storia («Regista, …», «Director, …», «Narratore, …»; anche in francese, spagnolo e tedesco). Il regista realizza il desiderio come prossima scena se nel mondo può accadere, altrimenti ne sceglie la cosa più vicina che resta coerente, e risponde fuori dal personaggio con la voce del narratore. Prova reale: «Regista, voglio che la Lethe torni, con un comandante diverso e più spietato» → «La Lethe torna, ma non è più la stessa nave: al suo timone c'è qualcuno che non ha intenzione di ripetere la clemenza di Aurelia…». Arriva un'incursione con un nuovo Ferryman cresciuto su Ophir durante la Carestia, e Rourke avverte il Capitano: «non è una preda, è un messaggio, ed è per lei».

## M2 (prima versione) — Calore e furtività
- [x] **Calore della nave** (`UAstraShipSubsystem::TickHeat`): il reattore (secondo la potenza assegnata), il motore (manetta), le salve dei railgun, i laser, i missili, gli scudi che si ricaricano e l'energia che fermano scaldano la nave; lo scafo irradia di base e i **radiatori** portano via calore, di più quanto più è caldo. Tarato: crociera ~15 %, battaglia tipica con radiatori retratti ~60-70 %, battaglia lunga e dura oltre il 100 %; con i radiatori estesi 30-50 %
- [x] **Effetti**: sopra il 70 % cadenza delle armi e rigenerazione degli scudi calano (fino al 55 % a pieno calore), sopra il 90 % anche il motore; oltre il 92 % i **condotti cedono** (incidenti veri da riparare, −20 % di potenza) e qualcuno in sala macchine si ustiona (ruolino e infermeria)
- [x] **Controlli dell'equipaggio**: `set_radiators` (estesi: dissipano 2,6 volte tanto, ma si vedono sui sensori nemici e un colpo può strapparne uno: incidente da riparare, efficacia −25 %), `vent_heat` (sfiato d'emergenza del refrigerante: −38 % di calore, 3 cariche, una colonna che tutti vedono per 30 s), più la ripartizione della potenza. Mensah e Okonkwo ne sono responsabili; la sala macchine può estendere i radiatori di sua iniziativa. Esempio reale al 94 %: «ho esteso i radiatori, ma ci rende visibili. Se non basta, propongo una sfiata di refrigerante»
- [x] **I radiatori si arroventano**: sulle ali di radiatori dell'Aquila il bagliore segue il calore; lo schermo di sala macchine in plancia mostra carico termico, radiatori e cariche di refrigerante
- [x] **Furtività** (`UAstraBattleSubsystem::TickDetection`): il Mandato può sparare solo a ciò che traccia. La **firma** dell'Aquila (EMCON silenzioso ~12 km, limitato ~30, pieno ~60, per la spinta del motore; radiatori estesi, colonna dello sfiato e scafo rovente la allargano) decide se le loro navi la trovano; sparare o una scansione attiva la tradiscono per 45 s; una traccia persa resta un minuto, poi la cercano all'ultima posizione nota. Il comandante nemico (la sua mente) sa se ha la traccia. Esempio reale: in silenzio e a motori spenti il gruppo d'attacco non trova l'Aquila e sposta il fuoco sul Vigilant; l'XO: «restiamo silenziosi e fuori portata, oppure ci schieriamo con la Flotta: la decisione è sua»
- [x] **La nebbia di guerra, dalla nostra parte** (`UAstraBattleSubsystem::TickSensors`): le navi del Mandato portate dal regista (incursioni, battaglie decisive) entrano **spente** (un terzo della loro firma) e si accendono vicino, quando sparano o quando fuggono.
  - Cosa sa l'Aquila dipende dai suoi sensori. I sensori attivi arrivano a ~55 km con EMCON pieno, ~28 km con EMCON limitato, zero in silenzio. La firma del bersaglio (classe, motore, se è spento) dà un rilevamento passivo, solo angolare: una linea senza distanza. Le navi della 7ª Flotta e i gruppi di volo condividono le tracce via datalink; una nave che spara si vede da ovunque.
  - La conoscenza cresce a gradini, e il Sensori la annuncia raggruppata: rilevamento, traccia, classe, nome.
  - Senza traccia non si spara («no firing solution: only a passive bearing»).
  - Per avere una traccia: `active_scan` (un impulso che traccia e classifica tutto entro 90 km, ma lo sentono tutti), EMCON pieno, una ricognizione di Wasp che legge il nome sullo scafo, oppure avvicinarsi.
  - Sul tavolo olografico un contatto senza distanza sta sul bordo, lungo il suo rilevamento («BEARING ONLY  NO RANGE»).
  - L'apertura della campagna resta scritta com'è.
  - Prova reale: tre navi entrano al buio a 45 km; le scorte le tracciano a 34-35 km, arrivano le classificazioni e l'equipaggio ragiona («due contatti ostili in avvicinamento: tengo gli scudi bilanciati e la difesa di punto in automatico»).
- [x] **Esche** (`launch_decoys`): razzi e chaff dai fianchi dell'Aquila per 18 s; circa metà dei missili nella corsa finale verso di lei perde il bersaglio e vola alla cieca. A bordo ce ne sono 8, se ne usano due per lancio, e il rifornimento le ricarica. Il Tattico le usa d'iniziativa come la difesa di punto. Prova reale: due missili dalla Persephone → «ho lanciato decoy e il point defence li sta ingaggiando», e il rapporto «the decoys drew off 1 missile».
- [x] **Il disturbo del Mandato** (guerra elettronica, in `TickSensors`): una nave capitale del Mandato che ha smesso di navigare spenta (si è avvicinata, ha sparato o ha sentito il nostro impulso e sa di essere stata trovata) accende i disturbatori fra 12 e 55 km.
  - La sua «strobe» ne rivela il rilevamento ma nasconde la distanza. Lungo quella linea (±25°) i nostri sensori attivi e quelli della flotta scendono al 45 %: le scorte che viaggiano dietro il disturbatore spariscono.
  - Sotto i 12 km il segnale buca il rumore (burn-through, annunciato dal Sensori).
  - Contromisure: un impulso attivo buca per 45 s (e li fa accendere tutti); due rilevamenti da punti abbastanza lontani (una nave della flotta o un gruppo di volo fuori dalla nostra linea, oltre 4°) danno per **triangolazione** una traccia senza classe; i Wasp a meno di 8 km lo leggono a vista.
  - I **missili** possono partire lo stesso, **home-on-jam** (volano sul disturbo); i railgun e i laser no, e il rifiuto spiega perché e cosa serve.
  - Sul tavolo olografico: una linea di rumore tremolante dall'Aquila verso il disturbatore, «JAMMING  NO RANGE». Nel piano dei contatti letto dall'equipaggio: stato JAMMING e le contromisure.
  - Prova reale: incursione a 85 km, impulso, l'Acheron accende i disturbatori a 54 km → Nair: «disturbo elettronico: strobo dell'Acheron su zero-due-cinque, la sua portata è nascosta e le tracce su quel rilevamento svaniscono»; il Tattico: «senza distanza i railgun tacciono, Capitano. I missili possono puntare sul disturbo»; railgun rifiutati, 2 missili partiti in home-on-jam; burn-through a 12 km, poi l'identificazione (KMS Charon).
- [x] **Gli inganni del Mandato: le esche** (`LaunchGhosts`): un incrociatore Acheron d'incursione porta 4 emettitori-esca, un cacciatorpediniere Styx 2. Un'esca è un drone che vola veloce verso un **falso rilevamento** (35-70° fuori da quello vero, alla stessa distanza) e poi si avvicina come una nave da guerra in crociera, tenendosi fuori dal radar; dopo circa cinque minuti la batteria finisce.
  - Per i nostri sensori è identica a un contatto vero visto solo per rilevamento: stesso rapporto («faint drive emissions»), stesso simbolo sul tavolo, stesso rifiuto se le si spara, stesso saluto senza risposta («hailing T-44 on all frequencies»).
  - La smaschera il primo ritorno radar (nostro entro la portata attiva, di una nave della flotta entro 30 km, anche col disturbo), un impulso attivo o un gruppo di volo a meno di 10 km: il Sensori la annuncia («a decoy: the radar return is far too small for that drive») e la toglie dal piano.
  - Prova reale: incursione spenta a 70 km, due esche lanciate → il Sensori vede solo le esche, a 043 e 005 («deboli emissioni di motore: T-44 e T-45, solo rilevamenti passivi»), mentre la vera incursione arriva spenta a 023; l'impulso smaschera le due esche e trova le due navi vere, che accendono i disturbatori.
- [x] **Il comandante nemico combatte anche la guerra dell'informazione**: `command_group` ha il campo `ew` (jam, quiet, auto, decoys).
  - Nella sua vista della battaglia, per ogni sua nave: emissioni, ordini di guerra elettronica, esche a bordo, se il nostro radar la sta illuminando, e il parere del suo **ufficiale di guerra elettronica** calcolato dal gioco (ad esempio «their radar paints us: going quiet hides nothing now; only jamming takes our range away»).
  - Prova a vuoto su tre situazioni: spento e non scoperto → quiet; illuminato a 40 km → jam; combattimento a 9 km → jam (inutile ma innocuo). Prova reale: Halvorsen tiene il gruppo spento finché l'Aquila non lo vede («my group is still outside her radar, so I stay silent and dark»).
  - Un rilevamento vero che si spegne ora viene annunciato come quello di un'esca («the bearing on T-40 has faded — it went quiet, or it was never there»); un rilevamento resta 20 s quando le emissioni calano, niente sfarfallio al limite.
- [x] **Meno fughe dalla nebbia**:
  - Un contatto noto solo per rilevamento non ha distanza, velocità né dimensione su nessun piano: il tavolo non zooma più fino alla sua distanza vera, lo schermo dei contatti scrive «—» e «BEARING ONLY», il timone lo insegue lungo il rilevamento senza distanza («range unknown»).
  - La flotta non concentra il fuoco su un rilevamento.
  - La ricognizione va solo verso ciò che è sul piano.
  - Le fregate di un'incursione puntano le navi ASTRA, mai un'altra nave che si trova nel sistema.
  - L'ammiraglio non conosce distanze, classi, nomi né trucchi di un'incursione spenta.
  - Il Regista rispetta i dettagli delle richieste esplicite del giocatore.
  - Le incursioni arrivano a 25-60 km, così il gioco dei sensori ha tempo di svolgersi.
- [x] **La nebbia regge in ogni rapporto**: il nome di una nave del Mandato compare solo dopo l'identificazione (lancio dei caccia, danni, fuga, distruzione, missioni dei gruppi di volo, richieste alla flotta); prima è «a Kharon Mandate cruiser, Acheron class (T-41)» o solo «T-41». Sul tavolo, un contatto classificato mostra la sua classe («T-41  ACHERON CLASS») invece di «UNKNOWN».
- Prove: `astra.heat <percento>`; `astra.cmd set_radiators {'state':'extended'}`, `astra.cmd vent_heat {}`; `astra.battle.status` elenca ogni nave con rilevamento, distanza, traccia e disturbo

## Alloggi dell'equipaggio (Deck 3 · Section C)
- [x] **Crew Berthing** (`data/ship/aquila_berths.json`, `art/blender/berths.py`, `tools/ue_scripts/build_berths.py`): un compartimento di 24 × 7 m, basso e in penombra (qualcuno dorme sempre).
  - 28 pile di tre cuccette ai due lati del corridoio: telaio d'acciaio, materassi, coperte spiegazzate, cuscini, lucina di lettura e rete portaoggetti alla testa, tende sul corridoio (tre varianti: aperte, chiusa in alto, chiusa a metà).
  - Colonne di armadietti fra le coppie di pile; canaline e un tubo sul soffitto; luci notturne rosse al battiscopa.
  - A poppa un angolo relax: tavolo con quattro sgabelli, tazze e carte, le notizie della flotta (la stessa pagina viva della mensa), una mensola di libri e giochi, la macchinetta del caffè.
  - Il cartello «CREW BERTHING · DECK 3 · SECTION C · RED WATCH · QUIET», la porta del bagno («HEAD»).
  - Sette marinai del turno Rosso dormono nelle cuccette; due che non riescono a dormire siedono al tavolo.
  - Ascensore: sesta fermata (tasti 1-6 in ordine di ponte: Bridge, Crew Berthing, Mess Hall, Medbay, Main Engineering, Flight Deck); zona luci accese solo con il Capitano presente; il datapad e l'equipaggio sanno quando il Capitano è lì.
  - Prova in gioco: il corridoio in penombra con le luci rosse notturne e le lampade di lettura calde, un marinaio che dorme nella cuccetta bassa (testa sul cuscino verso la parete), i due svegli al tavolo uno di fronte all'altro, le notizie della flotta vive sullo schermo; l'ingresso del Capitano arriva all'equipaggio («the Captain came down to Crew Berthing…»).
  - Lezioni: il compartimento a -42 m era attraversato da una superficie interna dello scafo, visibile solo da sotto (i tracciamenti verso l'alto la trovano, quelli verso il basso no): spostato a -46 m, alla quota della mensa. Luce: un terzo di quella della mensa, abbastanza per vedere chi dorme.
- [x] **Colori delle luci di quattro ponti** (mensa, infermeria, sala macchine, alloggi): in Python `unreal.Color(r, g, b, a)` posizionale prende i canali nell'ordine **B, G, R, A**; gli script creavano le luci con rosso e blu scambiati (la mensa, voluta calda, era fredda; il bagliore azzurro del reattore era arancione). Script corretti (argomenti per nome) e 46 luci del livello sistemate.

## Lo stile di comando del Capitano (la mente impara, il nemico anche)
- [x] **L'XO impara come comanda il Capitano** (`mind/astra_mind/style.py`): durante un combattimento la mente annota gli ordini del Capitano (le parole e cosa ha fatto la nave); a fine scontro («engagement over») un modello riscrive due schede, salvate con la storia:
  - la **lettura dell'XO** (per l'equipaggio, massimo 90 parole): distanza e pazienza, armi e missili, caccia, sensori ed emissioni, scudi, saluti e resa, rischi, cosa usa per primo e cosa non fa mai. L'equipaggio la usa per **anticipare** («i Falcon sono pronti per la CAP, come li vuole lei») e per avvertire quando un'abitudine è pericolosa contro ciò che ha davanti;
  - la **lettura dell'intelligence del Mandato** (massimo 60 parole): le stesse abitudini viste da fuori, e come sfruttarle. I comandanti nemici la ricevono solo dopo due scontri con l'Aquila, e la usano per tenderle trappole.
- Il Regista la legge: ogni tanto la storia mette alla prova le abitudini del Capitano (un nemico che le ha imparate, una situazione in cui la risposta solita fallisce), mai sempre e mai in modo sleale.
- Prova a vuoto su due battaglie:
  - l'XO: «The Captain opens with an active sweep of the whole volume, then launches Alpha on CAP before the first shot… Strikes hard, then closes to finish; never waits»;
  - il Mandato: «Exploit: her opening ping and hail reveal her early; hit her before she closes, or draw the salvo and break off while she is committed forward».

- [x] **Il quadro cieco** (consigliere tattico, `picture_flag`): quando sul plot ci sono solo rilevamenti senza distanza (almeno due, oppure un disturbatore), Nair lo dice una volta per ogni quadro nuovo e propone le due opzioni migliori con il loro costo, tenendo conto di come combatte il Capitano. Prova a vuoto: «tre contatti senza distanza: T-40 in jamming, e due tracce passive, forse esche. Un ping attivo ci dà tutto e smaschera le esche, ma dice a tutti dove siamo; in alternativa mando Alpha sul fianco per un cross-fix» (nessuna azione da sola).
- [x] **Il rapporto post-azione**: finito uno scontro (non la battaglia decisiva, che chiude l'arco col suo finale), dopo i rapporti l'XO dà al Capitano due o tre frasi: esito e costo, cosa ha funzionato, una lezione onesta per la prossima volta, dagli eventi veri e dagli ordini del Capitano; l'ufficiale più coinvolto può aggiungere una riga. Prova a vuoto: «Il ping ci ha dato il quadro in un colpo, ma ha anche detto a tutti dove eravamo; la prossima volta, con i jammer in giro, valuterei prima un silenzio e un ricognitore».

- [x] **Price, controllore di volo del Capitano**: quando il Capitano pilota un Falcon, il riassunto di volo per la mente elenca le minacce intorno al Falcon in posizione a orologio («a Harpy at 2 o'clock high, 3.1 km, closing») e dove si trova l'Aquila. Price chiama subito una minaccia nuova in avvicinamento, altrimenti ogni mezzo minuto circa se c'è qualcosa da dire. Prova a vuoto: «Eagle, Price: due banditi, il tuo due in alto, tre virgola uno, in chiusura; secondo a tre in piano, quattro». Prova in gioco (decollo dalla catapulta con un'incursione a 14 km): «Eagle, Price: incrociatore Acheron alla tua una in alto, nove chilometri, in chiusura e in disturbo — non farti contare»; «quattro missili in arrivo dal Charon… punta a casa, ora»; «quattro Harpy puntano l'Aquila, non te — resta basso e rientra, ti tengo la pista libera».

- [x] **Notizie da casa**: ogni tanto (circa un passo della storia su quattro, mai durante la battaglia decisiva) il Regista fa arrivare a un ufficiale qualcosa dalla sua vita fuori dalla guerra (una lettera, una nascita o un lutto, un fratello su una nave colpita, una commissione di promozione, un litigio arrivato al punto di rottura), coerente con la guerra e con chi è. L'equipaggio lo sa e lo porta con sé; nel primo momento tranquillo l'ufficiale lo dice al Capitano, fuori servizio. Salvato con la storia. Prova a vuoto: «Capitano, una cosa fuori servizio: mio fratello è sulla Tenacity, colpita a Cassia. Il bollettino lo dà ferito, non morto».

## Distribuzione: l'app ASTRA per macOS
- [x] **`tools/pacchetto.sh`**: compila, cuoce tutti i contenuti (anche quelli caricati per percorso a runtime: `/Game/ASTRA`, i manichini, le forme base del motore), impacchetta (pak + IoStore, Development) e installa **`~/Applications/ASTRA.app`** (2,1 GB).
  - La mente Python viaggia nell'app (`Contents/Resources/mind`, solo i sorgenti). Al primo avvio uv crea il suo ambiente in `~/Library/Application Support/ASTRA/venv` (Python 3.13, fissato da `mind/.python-version`; pochi secondi grazie alla cache).
  - Il gioco passa alla mente la cartella dei salvataggi (`ASTRA_SAVED`: la campagna e la storia stanno insieme) e la sua cartella dati (`ASTRA_HOME`: la chiave, i modelli della voce, le cache).
  - Chiudendo il gioco si chiude anche la mente; in ogni caso una mente senza gioco per 20 minuti si spegne da sola.
- Prova reale (installata in `~/Applications`): l'app parte, carica plancia, battaglia, schermi e hangar; la mente parte da `Contents/Resources/mind`, crea il suo ambiente in `Application Support/ASTRA/venv` e si collega in circa 80 secondi al primo avvio; chiudendo il gioco si chiude anche la mente.
- **Da sapere**:
  - l'app non va lanciata dalla Scrivania: i processi figli (Python) chiederebbero a macOS il permesso per la cartella Scrivania. Per questo si installa in `~/Applications`, e i dati della mente sono copie (la chiave, chmod 600, mai su git) e cloni APFS (i modelli della voce), non collegamenti al repository;
  - dopo aver cambiato la chiave nel `.env`, rilancia `tools/pacchetto.sh` (o copia il `.env` in `~/Library/Application Support/ASTRA/`).
- Cosa manca per distribuirla ad altri: firma e notarizzazione Apple (serve un account sviluppatore: vedi RICHIESTE se servirà), e uv e whisperkit-cli installati sul Mac di destinazione.
- [x] **App di rilascio (Shipping, 2026-09-29)**: `tools/pacchetto.sh shipping` — codice ottimizzato, niente console né statistiche, stessa app in `~/Applications/ASTRA.app`.
  - Mac: `Build/Mac/Resources/Info.Template.plist` (alta risoluzione Retina, frase del microfono, categoria giochi), identificativo `com.beltromatti.ASTRA`, versione 0.1.0, icona (`tools/art/app_icon.py`), niente sandbox (la mente è un processo figlio e parla in rete: il sandbox di Epic per Shipping, NoNet, la bloccherebbe).
  - Immagine: schermo intero, sincronizzata con lo schermo, 60 fps al massimo; il 3D passa per TSR a metà della risoluzione Retina (1710x1107 sull'Air 15") e la risoluzione dinamica lo tiene nei 16,7 ms (dal 100% al 40%, sulla plancia sta al 50% con 2 ms di margine).
  - Nel gioco Shipping non ci sono log (il motore installato dal Launcher non permette di riaccenderli); la mente scrive il suo in `~/Library/Application Support/Epic/ASTRA/Saved/Logs/astra-mind.log`.
  - Il nome nel Dock e nella barra dei menu è «ASTRA» (UE lo prende dall'eseguibile, `ASTRA-Mac-Shipping`: `pacchetto.sh` corregge `CFBundleName` prima di firmare).
  - **Avvio che si bloccava** (trovato provando l'app): se la finestra nasce a schermo intero, il motore aspetta senza limite (`FMacWindow::WaitForFullScreenTransition`) che macOS finisca la transizione, e macOS la fa solo per l'app attiva: aperta mentre un'altra app teneva il fuoco, restava al 100% di CPU prima ancora di caricare. Ora l'app nasce in finestra e va a schermo intero da sola appena è in primo piano (`Source/ASTRA/ASTRA.cpp`, `r.setres ...wf`, una volta sola; `-windowed` la tiene in finestra). Serve `Version=5` in `DefaultGameUserSettings.ini`: senza, il motore ignora la sezione quando crea la finestra (e usa il suo default, WindowedFullscreen).
  - `SButton::SimulateClick` non esiste in Shipping (Invio nel menu ora chiama direttamente l'azione della prima voce).
  - La mente spegne il suo server WhisperKit quando si chiude (segnale, 20 minuti senza gioco): prima restava orfano con il modello caricato (ne ho trovato uno vivo da 34 ore).
  - Provata (2026-09-29): parte, disegna la plancia a 1710x1107 (screenshot fatto dal gioco stesso con `-astra_later="HighResShot 1"`), la mente si collega in ~20 s quando WhisperKit è già caldo; chiudendo il gioco si chiudono mente e WhisperKit; aperta in secondo piano non si blocca più (resta ferma finché non la porti davanti: `t.IdleWhenNotForeground`). I websocket di UE girano su un thread loro: stando in un'altra app la connessione con la mente resta viva.

## Equipaggio in movimento
- [x] **La nave vive**: membri dell'equipaggio che fanno il loro giro (`AAstraWalker`, `tools/ue_scripts/place_walkers.py`): un marinaio in ciascun corridoio dietro la plancia, un'infermiera che passa tra i letti dell'infermeria, due addetti del ponte di volo tra gli stalli e le catapulte, un tecnico che gira attorno al pozzo del reattore. Personaggi con movimento vero (l'AnimBlueprint del manichino fonde fermo e camminata), soste a ogni tappa, divisa del reparto; se il Capitano sbarra loro la strada, dopo un po' tornano indietro

## M7 (seconda parte) — Le superfici di tutti i mondi, generate a runtime
- [x] Ogni sistema raggiunto dal Gate ha la superficie del suo mondo principale, **generata dal nome e dal tipo** (stesso nome = stesso mondo: universo con seme). Cinque tipi:
  - **oceanico**: arcipelaghi con montagne, scogliere e spiagge; un'isola sempre vicino al campo;
  - **desertico**: mesa e butte a gradoni con pareti di arenaria rossa stratificata, mari di dune, un canyon;
  - **ghiacciato**: calotta con creste di pressione, nunatak di roccia, catena montuosa nell'interno, mare ghiacciato a sud chiuso da una falesia di ghiaccio;
  - **roccioso senz'aria**: crateri di ogni misura (legge di potenza) con orli, ejecta e picchi centrali, un grande cratere in vista del campo, cielo nero;
  - **vulcanico**: piane di basalto, coni con cratere sommitale, canali e laghi di lava viva (croste scure che scivolano su fessure incandescenti).
  I giganti gassosi non hanno superficie.
- [x] Il mondo si costruisce in 0,1–0,5 s, nascosto dal plasma del rientro:
  - nucleo di 12 km a maglie di 24 m (16 sezioni con collisione, erosione termica con la pendenza massima propria del tipo, piazzola spianata);
  - terreno lontano di 90 km a 300 m, poi anelli d'orizzonte fino a 600 km e un mare che **curvano come il pianeta** (raggio 6000 km, lo stesso della SkyAtmosphere): nessun bordo del mondo, nemmeno da 14 km di quota;
  - cielo per tipo (atmosfera, nebbia, nuvole volumetriche) e un sole con ora e direzione proprie per ogni mondo;
  - campo d'atterraggio con piazzola, hangar e torre col faro (spento sui mondi morti).
- [x] Il Falcon scende su qualunque mondo (**G** col muso sul pianeta). Esce a 17 km dal campo, a 8,5 km di quota. Equipaggio ed eventi usano i nomi veri («Eagle has landed on Cassia Prime, near the landing field on Cassia Prime»); dopo uno schianto il soccorso arriva con un Wasp.
- [x] **Chi risponde dal campo** (`mind/astra_mind/port.py`, `FieldControl`): ogni mondo ha il suo controllore, con nome, voce e modi decisi dal nome del mondo (stesso mondo, stessa voce) e un atteggiamento che dipende da chi lo tiene nella mappa della guerra (se il mondo cambia padrone, cambia anche la voce):
  - un avamposto ASTRA è contento di vedere la Marina;
  - un porto delle Gilde è cortese e chiede la tassa d'ormeggio. Su Sabel, Controller Ines Brandt: «Atterraggio autorizzato… Tassa di ormeggio: duecento crediti Guild, pagabili al banco»;
  - un campo del Mandato sfida Eagle. Su Pyre, Warden Luca Lindgren: «Avete violato lo spazio aereo del Mandato… Le batterie di terra vi tengono sotto tiro», e poi «Se toccate il suolo, siete in arresto»;
  - un insediamento fuori mappa è diffidente;
  - un mondo silenzioso non risponde. Su Hollow, dalle comunicazioni: «nessuna risposta dal campo di Hollow su nessun canale: solo statico».
  Il Capitano lo chiama per nome («Pyre Ground Control, qui Eagle…», «torre», «campo»); la storia ricorda le discese sui mondi nemici o muti. Nello snapshot c'è ora `surface` (mondo, tipo, campo, se il Capitano è laggiù).
- [x] **Fuoco di terra del Mandato**:
  - sui mondi del Mandato le batterie aprono il fuoco su Eagle se resta entro 14 km dal campo e sotto i 6 km di quota per 20 secondi dopo la sfida del Warden (subito entro 5 km);
  - colpi di flak (lampo breve, sbuffi scuri sfrangiati, boato, scossone) sempre più precisi vicino al campo;
  - i colpi vicini danneggiano lo scafo del Falcon (sull'HUD); a zero c'è l'eiezione e il soccorso di un Wasp;
  - l'equipaggio lo sente: «fuoco da terra su Pyre, contraerea del Mandate attorno a voi — virare e salire, subito» (Price); «posso portare la Aquila in appoggio o restare fuori tiro, dica lei» (Serra);
  - chi atterra comunque vede arrivare una colonna della guarnigione dopo 40 s;
  - materiale `M_FX_Smoke` (`tools/ue_scripts/make_fx_smoke.py`); console `AstraFlakTest <m>`.
- [x] **Città sui mondi popolosi**:
  - accanto al campo sorge una cittadina o una città proporzionata alla popolazione della mappa della guerra (la mente la manda al gioco col settore): Pyre 33 blocchi, Sabel 106, Halcyon 135, Asphodel 177, Concord 285;
  - strade su una griglia di 60 m (asfalto, cordoli, tratteggi, isolati di cemento: maschera nel colore dei vertici e parametri `CityX`/`CityY`/`CityYaw` di `M_ASTRA_Terrain`), torri più alte verso il centro;
  - stile per fazione: vetro ASTRA, basse stecche dei mercati delle Gilde, blocchi a gradoni del Mandato; torri più alte nelle capitali;
  - terminal accanto alla piazzola dove la gente viaggia;
  - costo circa 0,3 ms (Concord 19,5 ms di mediana).
  Il controllore di campo sa della città («A great city spreads out a couple of kilometres from the field…»).
- [x] Robustezza: un NaN nello snapshot (gli scudi di un relitto, 0 su 0) rendeva il JSON invalido e la mente perdeva la nave. Ora le percentuali sono protette, il gioco converte qualunque nan/inf in null fuori dalle stringhe, e la mente scarta un messaggio guasto senza chiudere la connessione.
- Tecnica:
  - `FAstraWorldGen` (`Source/ASTRA/AstraWorldGen.*`): rumore di valore fbm/ridged con domain warp, crateri in una griglia di ricerca, coni; il sito è il punto più piano e asciutto entro 3,5 km (sulla calotta, non sul mare ghiacciato). I dettagli fini restano solo nel nucleo, così il terreno lontano non fa aliasing.
  - `AAstraWorldSurface` (`AstraWorldSurface.*`): ProceduralMeshComponent con tangenti e componenti statici. Le ombre del nucleo le proietta un **proxy invisibile a 48 m** (un quarto dei triangoli, stesso aspetto).
  - `UAstraShipSubsystem::WorldBelow()` crea o ricrea il mondo quando cambia il sistema.
- Materiali:
  - `M_ASTRA_Terrain` ha i nuovi parametri `RockTint`, `Shore` (spiaggia e battigia bagnata solo dove c'è un mare a quota zero) e `Strata` (stratificazioni sulle pareti); il rumore macro usa due scale, così dall'alto non si vede più la griglia;
  - istanze `MI_W_Terrain_<Tipo>` (`tools/ue_scripts/make_world_materials.py`);
  - lava `M_ASTRA_Lava` (`tools/ue_scripts/make_lava_material.py`), che da lontano si uniforma in un bagliore senza reticoli;
  - nuove rocce CC0 ambientCG: Rock029 (arenaria rossa) e Rock026 (roccia chiara).
- Prestazioni (1080p, standalone su L_Bridge, editor chiuso): mondo ghiacciato 17,7 ms di mediana, deserto 16,7 ms. Prima del proxy d'ombra e delle nuvole a metà campioni erano 23 ms. Anche le nuvole di New Ravenna ora usano metà campioni (21,5 → circa 18 ms).
- Prova:
  - `astra.battle.arrive <Sistema> [stella] [tipo] [Nome_Pianeta]` esce subito da un Gate, senza corsia (es. `astra.battle.arrive Veyra orange desert Sabel`);
  - poi `astra.planet go` (a piedi al campo), oppure Falcon + `astra.fly.face planet` + `AstraDescend`;
  - misure: `tools/perf/run_perf.sh /Game/ASTRA/Maps/L_Bridge 1500 1920 1080 -astra_world=Cassia+blue_white+ice+Cassia_Prime`.

## Scafi: segni di battaglia
- [x] **Cicatrici dove arrivano i colpi** (`UAstraBattleSubsystem::AddScar`, `tools/art/scorch.py`, `tools/ue_scripts/make_fx_scorch.py`): ogni colpo che passa gli scudi e intacca lo scafo lascia un decal nel punto d'impatto.
  - Il decal ha fuliggine irregolare, raggiere dell'esplosione, schizzi e crepe incandescenti che si raffreddano in meno di un minuto; i colpi pesanti aprono uno squarcio nero con il bordo fuso.
  - È largo 12-52 m secondo il danno, e se ne tengono al massimo 20 per scafo.
  - Sull'Aquila un raggio dall'esterno trova la piastra colpita (lo scafo ha collisioni complesse), sulle altre navi la bruciatura è proiettata verso il centro.
  - Restano sui relitti. Si vedono dalla plancia, dal Falcon e dalla capsula.

- [x] **I nomi delle navi ASTRA sui fianchi** (`UAstraHullName`, `tools/ue_scripts/make_hull_decal_rt.py`): ogni nave della 7ª Flotta che la storia porta ha il suo nome e il numero di scafo della sua classe (BB per le corazzate, DD per i cacciatorpediniere: lo stesso nome ha sempre lo stesso numero). Il nome viene disegnato a runtime col font del gioco su una render target (bianco su nero, la maschera è il canale rosso) e messo sui due fianchi come decal, con lo stesso materiale e lo stesso verso del nome dell'Aquila. Esempi: «ASN PRAETORIAN · BB-06», «ASN VIGILANT · DD-37».

## Scafi: luci di navigazione e nome
- [x] **Luci di navigazione** su ogni nave e velivolo (`UAstraNavLights`):
  - posizioni lette dalla forma vera di ogni scafo (`tools/ue_scripts/extract_nav_lights.py` → `data/ship/nav_lights.json`);
  - rossa a babordo, verde a dritta, bianca a poppa, lampeggiatore bianco doppio in cima, rosso pulsante sotto;
  - il Mandate viaggia al buio con una sola luce rossa pulsante;
  - le luci restano grandi qualche pixel anche lontano, così una flotta si legge contro le stelle.
- [x] **Nome sullo scafo dell'Aquila**:
  - «ASN AQUILA · CVC-01» con l'emblema della ASTRA Navy, su entrambi i fianchi verso prua, sotto la fascia blu;
  - decal `M_ASTRA_HullDecal`/`MI_HULL_Name_Aquila`, texture da `tools/art/hull_markings.py` (Barlow Condensed, OFL), `tools/ue_scripts/make_hull_decals.py`;
  - due lezioni: un decal di UE stende la larghezza della texture lungo il suo asse Z (va ruotato di un quarto di giro); una texture usata solo da decal creati a runtime va resa residente (`SetForceMipLevelsToBeResident`), altrimenti resta al mip più sfocato.

## M6 (prima versione) — Il regista della guerra
- [x] Regista a runtime (mind/astra_mind/director.py): a ogni esito sceglie il prossimo sviluppo (incursione, soccorso, rinforzi, rifornimento, calma) coerente con il registro della campagna, e inventa i nuovi comandanti nemici (mente e voce proprie)
- [x] Vice Admiral Adrian Rourke, comandante della Settima Flotta: trasmette gli ordini, risponde quando l'Aquila chiama la flotta, può concedere rinforzi o rifornimento
- [x] Transito attraverso i Janus Gate verso nuovi sistemi: nuovo cielo con stella (nana rossa, arancione, gialla, bianco-azzurra), luce di plancia coerente, mondo principale (oceanico, desertico, ghiacciato, vulcanico con lava, gigante gassoso, roccioso) e nebulosa virata
- [x] Il transito è una manovra vera, decisa dal Capitano («Timoniere, portaci attraverso il Gate verso Cassia»): rotta automatica a tutta forza verso la corsia d'avvicinamento, poi il campo del Gate cattura la nave (timone bloccato) e la porta nel cuore dell'anello lungo una corsia di anelli di luce, sempre più veloce, fino al lampo; all'uscita l'anello è alle spalle e la nave scivola via a ~2 km/s. Una nuova rotta prima della corsia annulla la manovra
- [x] Il regista non teletrasporta: il beat "transit" sono **ordini della Flotta** (il Gate viene sintonizzato, l'equipaggio riferisce e aspetta il Capitano). Registro dei sistemi esplorati (stesso nome = stesso posto: universo con seme); tornare ad Aurelia ripristina il cielo di casa. Se la storia resta ferma 7 minuti, il regista interviene (Rourke sollecita o la guerra arriva)
  Prove: `astra.battle.gatejump` (30 km davanti al Gate) poi `astra.battle.transit Cassia`; `astra.cmd director_beat {'beat':{'type':'transit','system_name':'Meridian'}}`
- [x] Mappa strategica della guerra: il settore **Aurelia March** (11 sistemi, Gate legati a pochi altri, fazioni, minaccia), in `mind/astra_mind/war.py`, salvata in `Saved/Campaign/war.json` a ogni cambiamento. Il regista la legge e la fa evolvere (`war_news`: sistemi che cadono o vengono ripresi, notizie sulla rete della flotta riferite dalle comunicazioni); i transiti vanno solo verso sistemi collegati; l'equipaggio la conosce
- [x] Tavolo olografico in modalità **settore** («Sensori, mappa del settore sul tavolo»): sistemi colorati per fazione, collegamenti dei Gate, anello dell'Aquila, rotta di transito che pulsa, sistemi minacciati con alone; la mappa si gira verso chi la guarda
- [x] Nuovo beat del regista **investigate**: un luogo da esplorare dove si trova l'Aquila (stazione d'ascolto muta come Thule Watch, nave da guerra o mercantile alla deriva), buio e in lenta rotazione; le **scoperte** scritte dal regista arrivano a tappe (scansione attiva; squadriglia in ricognizione o Aquila a 5 km; affiancamento a 2 km) e restano nel registro della storia; un'eventuale **imboscata** di navi del Mandato a motori spenti si accende quando l'Aquila si avvicina, e il suo comandante chiama. Nuova mesh SM_STATION_ASTRA_Watch
- [x] **Campagna salvata e ripresa**: menu iniziale (Slate, in inglese) con CONTINUE (riepilogo: sistema, scafo, caduti, ora), NEW CAMPAIGN (con conferma se c'è un salvataggio), QUIT; Esc/F10 in partita apre il menu e mette in pausa. Salvataggio automatico ogni minuto e a ogni svolta della storia: `Saved/Campaign/ship.json` (gioco: sistema, scafo, missili, squadriglie, caduti e feriti del ruolino), `war.json` e `story.json` (mente: mappa della guerra e registro della storia). Alla ripresa: la nave è in pattuglia nel sistema salvato col suo cielo, l'XO dà il bentornato con i dati veri, il regista decide subito cosa succede. Test: `tools/ue.py pie start` (nuova campagna automatica), `--continue`, `--menu`; console `astra.campaign new|continue`
- [x] **Diario del capitano**: «Diario del capitano: …» (anche *Captain's log*, *Journal du capitaine*, *Diario del capitán*, *Logbuch des Kapitäns*) viene registrato dalla console della poltrona (cinguettio) e aggiunto a `Saved/Campaign/captains_log.md` con data e sistema; l'equipaggio non lo sente (è privato), il **regista lo legge** e la storia risponde a ciò che il Capitano pensa, teme e vuole
- [x] **Umore dell'equipaggio**: a ogni svolta il regista scrive come si sente la plancia e perché, nominando gli ufficiali (lutto per i caduti, orgoglio, stanchezza, dubbi su un ordine, rabbia), e lo fa evolvere di beat in beat (salvato in `story.json`). Colora il modo in cui gli ufficiali parlano senza mai dichiararlo, e affiora nei momenti di quiete. Esempio reale dopo la prima battaglia: *«Exhausted but proud… Grief for the Vigilant sits under everything — Mensah's repair gangs work in silence, Price counts seven Hammers where there were eight»*; alla domanda sul morale Serra risponde «stanchi, ma orgogliosi di aver tenuto Aurelia. Il dolore per il Vigilant è ancora aperto…»

## Prossimi passi
- **Dalla prova dal vivo del 30/9 (dopo la voce v2), da correggere**: righe dell'equipaggio ripetute uguali a ~8 s di distanza (Voss «Il Lethe è a quarantadue chilometri…» a 50,4 e 58,8 s; Nair a 65,5 e 74,3; Serra a 83,3 e 90,9: guardare il palco della voce, ripresa dopo un taglio o rapporto riaccodato); il timoniere dice «prua due-otto-zero» mentre il comando dice rilevamento 212 (inventa la rotta); «caccia classe Lethe» per una fregata. Prestazioni: rifare le prove A/B a macchina scarica (a caldo la stessa scena va da 18 a 38 ms di GPU); indizi: risoluzione, ombre dinamiche, riflessi Lumen, TSR, traslucidi.
- **In attesa degli aiutanti**: GUERRA (API delle portate delle armi per tavolo e schermo, contratto `group_order` e viste per parte per le menti), NAVE (piano e ponte 4: `UAstraShipPlan` è già pronto in main), ARTE-NAVI (navi v3).
0. **Dalla prima partita dell'utente** (29/9, 15:43–16:15, dal log della mente; nessun crash):
   - ha dato due ordini a voce (riconoscimento 1,8–1,9 s per frasi brevi) e poi solo **scritti**: capire perché (ora il riconoscimento è ≈0,2 s dal rilascio del tasto e le voci esterne si sentono: VOCE, 30/9); mancano ancora le conferme istantanee e il classificatore d'intenti locale previsti dalla ricerca (09, 13);
   - con il canale nemico aperto, «rapporto armamenti» e «ci sono navi nemiche» sono finiti **al comandante del Mandato**: il router va corretto (in dubbio, all'equipaggio);
   - voleva **vedere** i nemici («portaci a contatto visivo», «voglio vedere a schermo i nemici»): serve lo schermo principale che inquadra il bersaglio («On screen!»);
   - molte domande di stato (velocità, portata, quante navi) e fuoco ordinato a 16 km con i railgun a 10: portate e distanze vanno lette a colpo d'occhio;
   - prima sessione: carica frontale, scafo al 23 % in due minuti, abbandono nave; è uscito 40 s dopo l'inizio della Commissione d'inchiesta (forse non era chiaro che doveva rispondere). Seconda: vittoria su Solm, 5 piloti persi, poi il regista ha legato la notizia del fratello di Price alla nave Resolve alla deriva;
   - ha aperto l'app da `Desktop/ASTRA/Packaged/Mac` invece che da `~/Applications`.
1. **Sensori, terza parte**: pianeti e stazioni che coprono la linea di vista.
2. **Altri ponti**: armeria, la Spina; volti veri per l'equipaggio (MetaHuman, attende l'autorizzazione Epic in RICHIESTE.md); esterno della plancia; conversazioni sussurrate al tavolo degli alloggi.
3. **Pilotaggio**: missioni di scorta ordinate da Price; i caccia visti dall'hangar.
4. **Mondi generati**: guarnigioni a terra visibili (mezzi, cattura), edifici più vari, luci della città.
5. **Distribuzione, seconda parte**: la firma per altri Mac (serve un account sviluppatore Apple); ~~un menu delle impostazioni grafiche nel gioco~~ (fatto il 30/9: SETTINGS nel menu — qualità, nitidezza come soglia della risoluzione dinamica 70/55/40 %, 30 o 60 fps, volumi di musica e voci, sottotitoli; salvate in GameUserSettings.ini); una cache PSO registrata (niente scatti alla prima comparsa di un effetto).
6. **M8, preparazione al multigiocatore**: progetto scritto in `docs/MULTIGIOCATORE.md`; primi passi senza rischi: la nave del giocatore come indice (non più `Ships[0]`) e la conoscenza dei sensori per osservatore.

## Come provarlo (per l'utente)
1. `tools/avvia_editor.sh` (o apri ASTRA.uproject); il livello iniziale è la plancia (`L_Bridge`).
2. Il servizio delle menti parte da solo al primo avvio della partita (oppure `cd mind && uv run astra-mind`).
3. Premi Play: sei seduto sulla poltrona del capitano (**E** per alzarti e camminare, di nuovo **E** vicino alla poltrona per sederti; le porte in fondo portano ai corridoi). Tieni premuto **V** e parla al ponte in qualsiasi lingua (al primo uso macOS chiede il permesso del microfono), oppure premi **T** e scrivi l'ordine (Invio per mandarlo).
4. La battaglia parte da sola (dopo ~80 s si sveglia la fregata, dopo ~170 s arriva il gruppo d'attacco). Per accelerare: `astra.battle.time 168`, `astra.battle.timescale 3`.
5. Vuoi qualcosa dalla storia? Chiedilo al regista: «Regista, voglio un'imboscata vicino al relitto».
6. Quando l'Archon Solm chiama, parlagli direttamente (canale aperto): tutto ciò che non inizia con il nome/ruolo di un ufficiale va a lui. «Comunicazioni, chiudete il canale» per chiuderlo.
6. Da terminale: `tools/ue.py pie start|stop` e `tools/ue.py pie cmd 'astra.say ...'` per provare senza toccare l'editor.
7. Infermeria: ascensore (E alle porte in fondo al corridoio di babordo) → tasto 4 (i tasti seguono l'ordine dei ponti: 1 plancia, 2 alloggi dell'equipaggio, 3 mensa, 4 infermeria, 5 sala macchine, 6 ponte di volo). Mensa: tasto 3 (ascolta i tavoli, parla con chi vuoi o con il cuoco Wren). Parla con la dottoressa («Dottoressa, come stanno i feriti?») o con un ferito per nome. Senza battaglia i letti sono vuoti: `astra.medbay admit 8`.
8. Cabina del Capitano: la porta in fondo al corridoio di dritta (quello senza ascensore). E accanto alla branda per riposare. Dopo una battaglia dura, restaci un po': qualcuno può bussare (per forzare una visita: `astra.cmd visit {'officer':'chief','reason':'...'}`).
9. Pilotare: scendi con l'ascensore (E davanti alle porte in fondo al corridoio di babordo), avvicinati a un Falcon di Alpha (lato sinistro dell'hangar) e premi E; W per il lancio. Rientro: torna alla bocca di prua sinistra dell'Aquila, rallenta e premi F.
10. Il Janus Gate è a 110 km sul rilevamento 070: «Timoniere, portaci attraverso il Gate verso Cassia» (circa 2-3 minuti di avvicinamento, poi la corsia). Ogni sistema ha il suo Gate alle spalle per tornare.
11. Altri mondi: attraversa un Gate (o da console `astra.battle.arrive Cassia blue_white ice Cassia_Prime`), poi lancia un Falcon, punta il pianeta e premi **G**: ogni mondo ha la sua superficie (ghiaccio, deserto, crateri, lava, isole) e il suo campo d'atterraggio.

12. **Il datapad**: premi **Tab** ovunque a bordo (a piedi): il Capitano solleva nella mano sinistra un tablet con condizione, posizione, scafo, scudi e calore, i contatti come li conoscono i sensori, fuoco, gruppi di volo, danni, ordini permanenti e le ultime parole sentite alla radio. Di nuovo Tab per abbassarlo.
13. **L'app**: `tools/pacchetto.sh shipping` costruisce e installa `~/Applications/ASTRA.app` (la build di rilascio; senza argomento: Development, con la console); aprila come qualsiasi app (la prima volta la mente impiega circa un minuto a caricare le voci). Esc apre il menu, Cmd+Q chiude.

## Note operative
- **Campagna di sviluppo**: la partita creata dalle prove (2026-09-29) è stata spostata in `Saved/Campaign_prove_2026-09-29` (l'ultima prova l'aveva lasciata con l'Aquila al 2 %): alla prossima apertura il gioco propone una campagna nuova. Per riprenderla basta rinominare la cartella in `Saved/Campaign`.
- Se UnrealBuildTool va in crash con «Segmentation fault» in `libUbaHost` (l'acceleratore di compilazione), basta rilanciare `tools/ricompila.sh`.
- **Prestazioni (2026-09-29, 1710x1107 come l'app sull'Air, risoluzione dinamica al 50%)**: plancia **15,1 ms** di mediana (p95 16,7; GPU 14,8), battaglia decisiva GPU 14,9 ms — prima 19,4 ms. Limite: la GPU (render thread e worker aspettano la GPU dentro la visibilità, dove tornano le query di occlusione: `stat dumpframe` lo mostra). Cosa ha contato:
  - **TSR**: al livello antialiasing Epic la storia è al 200% dell'uscita (3420x2214): 2,5 ms. Ora `sg.AntiAliasingQuality=2` e `r.TSR.History.ScreenPercentage=100` in `Config/Mac/MacEngine.ini` (vince anche su un vecchio GameUserSettings).
  - **Vetri** (M_ASTRA_Glass, traslucenza con luce per pixel): la cache di radianza di Lumen per i riflessi dei traslucidi costava 1 ms di marcatura delle sonde; spenta, differenza invisibile (confronto di screenshot: 1/255 di scarto medio).
  - **Luci**: le locali senza ombre in un unico passaggio clustered (`r.UseClusteredDeferredShading_ToBeRemoved=1`): da 2,3 a 1,0 ms.
  - **Schermi**: FCanvas apre un lotto nuovo a ogni cambio di tipo di elemento; `FPaint` ora accumula e disegna tessere, poi linee, poi testi: spariti gli scatti di 11 ms del ridisegno del Master (p95 da 31,6 a 20 ms).
  - **Sole**: segue le virate a passi di 0,25° (ogni rotazione di una luce direzionale butta tutta la sua cache di ombre virtuali).
  - Provati e scartati: ombre classiche al posto delle virtuali (+4 ms), bias di risoluzione delle ombre locali, query di occlusione spente (nessun guadagno).
  - Su Metal i tempi per passaggio di `ProfileGPU` sono inaffidabili: passaggi consecutivi finiscono in una sola finestra di misura (il «VSM Log Stats And Status» da 4,5 ms era il TSR). Conviene confrontare il `GPUTime` totale del CSV tra due prove.
  - Le ombre virtuali (2,3 ms) sono quasi tutte costo fisso di gestione (40 mappe: 17 livelli del sole e le facce delle luci locali): la cache funziona (49 pagine dinamiche ridisegnate a fotogramma, l'equipaggio animato).
  - Nella build dell'editor uno shader visto per la prima volta blocca il render thread ~200 ms; nell'app gli shader sono cotti e macOS tiene le pipeline compilate nella sua cache Metal dopo il primo uso.
  - Diagnostica schermi: `astra.screens.profile 1`; `astra.screens.skip 1` (schermi mai ridisegnati, per misurare).
- **Nanite, lezioni dall'infermeria**: (1) un mesh Nanite con anche un solo slot traslucido (vetro) viene disegnato dalla sua *fallback* grossolana (errore ~1% delle dimensioni: 34 cm sul reparto: pannelli del soffitto esagonali, anelli "a punte"); `import_kit.py` ora lascia classici questi mesh, e reimportare non basta (gli slot vecchi restano): cancellare e reimportare. (2) I poligoni con più di 4 lati si triangolano all'esportazione (`astra_bpy.export_fbx`): l'importatore FBX perde triangoli sui poligoni con vertici allineati. (3) I materiali assegnati a runtime a mesh Nanite devono avere il flag d'uso Nanite (impostato su M_ASTRA_Screen/Hard/Emissive). Verifica: `r.Nanite.Visualize Triangles` (nero = non Nanite) e il log (`Invalid material ... Nanite`)
- Le prestazioni si misurano solo col gioco standalone (`tools/perf/run_perf.sh <mappa> 1500 1710 1107 [-astra_medbay|-astra_mess|-astra_decisive|-astra_planet|-astra_world=Sistema+stella+tipo+Nome]`; la mente non parte, `-astra_nomind`; `ASTRA_PERF_CMDS="cvar valore, ..."` per provare impostazioni; `-astra_later="stat dumpframe -ms=0.15"` o `-astra_later="HighResShot 1"` esegue comandi dopo 25 s, gli screenshot finiscono in `~/Library/Application Support/Epic/UnrealEngine/5.8/Saved/Screenshots/MacEditor`; servono almeno 2200 fotogrammi perché il gioco sia ancora aperto) e **con l'editor chiuso** (aperto ruba la GPU: le misure raddoppiano, 42 ms invece di 18): nel PIE l'editor usa la qualità Epic (Lumen alto, ~70 ms). Il riepilogo legge anche i CSV con l'intestazione in fondo (`[HasHeaderRowAtEnd]`, quando nuove statistiche compaiono durante la cattura)
- **Pacchetto** (build di rilascio): i dati letti a runtime stanno in `Content/ASTRA/Data` (le luci di navigazione; `DefaultGame.ini` li mette sempre nel pacchetto come file sciolti); niente messaggi di debug per il giocatore (i sottotitoli e gli avvisi sono Slate). La mente viaggia nell'app (sezione Distribuzione).
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
