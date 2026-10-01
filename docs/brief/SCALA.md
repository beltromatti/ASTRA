# Brief SCALA (F2.3, bozza del lead): la guerra grande nel gioco vero, a 60 fps

LEGGI: CLAUDE.md, ARCHITETTURA §1bis e §6 (regole di memoria), PIANO §3 (F2: «una battaglia di flotta dura 30–60 minuti ad alta
intensità, la vedo tutta»), GUERRA.md (tutto, soprattutto §5, §7.5 la scala già misurata nel banco, §6 il contratto), VFX.md (gli
effetti a istanze già fatti: dardi, tubi, bagliori, fuoco, fumo, pennacchi, detriti), ricerca/11 (il gate delle prestazioni),
il codice: `UAstraBattleSubsystem` (SpawnVisual, i velivoli: `F.Actor = SpawnActor<AStaticMeshActor>` ~righe 3020, 3057, 3791,
3846), `AstraWarCraft.cpp`, `AstraWarFX*`, `AstraNavLights.cpp`, `AstraViewscreen.cpp` (RebuildShowList, la lista degli attori
che la cattura mostra), `AstraHoloTable.cpp` (il tavolo con decine di contatti).

## Dove siamo
- La simulazione regge già la scala: `scale_30x150` (30 navi capitali, ~150 caccia, bombardieri e droni) costa 0,04–0,09 ms per
  tick nel banco (GUERRA §7.5). Il disegno no: ogni nave e ogni velivolo è un attore con la sua mesh, i suoi materiali, le luci
  di navigazione (componenti che tickano), i bagliori dei motori; il tavolo olografico e lo schermo principale scorrono tutti i
  contatti. Nel gioco vero l'apertura (6 navi, ~20 velivoli) gira a 58–60 fps sulla plancia (render thread 11–16 ms, game thread
  ~6 ms di lavoro, GPU 12–13 ms a risoluzione dinamica ~45 %): non c'è margine per 5 volte tanto senza un lavoro vero.

## Cosa costruire
1. **I velivoli a istanze**: caccia, bombardieri, droni e missili come istanze (una ISM/HISM per mesh e fazione, con i dati per
   istanza per luci e motori come fa VFX), niente attore per velivolo; le luci di navigazione e i bagliori dei motori come istanze
   o come effetti di VFX; un attore vero solo per ciò che serve davvero (il Falcon del Capitano, un velivolo inquadrato da vicino
   dallo schermo principale se la mesh a istanze non basta).
2. **Livelli di dettaglio per la distanza dall'Aquila** (simulazione e disegno): ciò che è lontano si aggiorna meno spesso e si
   disegna più semplice (mesh LOD, niente luci, niente effetti piccoli), senza salti visibili; le navi capitali lontane restano
   belle sullo schermo principale (che zooma ×50: lo streaming delle texture vede già la sua vista).
3. **Le domande per frame**: `GetContacts` e simili letti da molti consumatori (schermi, tavolo, schermo principale, HUD) a ogni
   frame: una lista per frame condivisa; il tavolo olografico con 50+ contatti leggibile (raggruppamenti per gruppo di battaglia,
   etichette che non si sovrappongono) e senza ricreare componenti (attenzione: `UTextRenderComponent` rifà il proxy di
   rendering a ogni Set*, anche a valori uguali: impostare solo ai cambi; il tavolo lo fa già con HoloSet*).
4. **Gli scenari grandi giocabili**: un modo per lanciare nel gioco vero `scale_30x150` (e una battaglia di flotta di campagna con
   rinforzi) per le prove del lead, e le misure.

## La misura di partenza (1/10, il lead, aiutanti in pausa)
`astra.war.scenario scale_30x150 aquila` (l'opzione nuova tiene l'Aquila nella battaglia, all'origine con la parte ASTRA: nella
sandbox normale era a un milione di km e non si disegnava nulla), 90 s dopo, seduto in plancia: **57–58 fps** al limite dei 60, **game
thread 13,8 ms** (WorldTickMisc 3,95, EndOfFrameUpdates 3,42, Tickables 2,53, TickActors 1,53), **render thread 14,8 ms**
(RenderOther 3,9, UpdatePrimitiveTransform 1,27, attesa visibilità 1,65), GPU 12,8 ms a risoluzione dinamica ~47 %. Il game thread
è il primo a cedere: gli attori dei velivoli e le trasformazioni dei loro componenti a ogni fotogramma.

## Il metro (il lead lo rifà nel gioco)
- Con `astra.war.scenario scale_30x150 aquila` sulla plancia (seduto al posto del Capitano, schermo principale acceso): ≥ 55 fps mediani a 1600x900 (risoluzione
  dinamica ≥ 40 %), game thread ≤ 8 ms, render thread ≤ 12 ms; memoria del gioco ≤ 9 GB.
- Nessuna regressione nell'apertura (oggi 58–60 fps).
Prove offline: il banco `tools/war.py` (simulazione) e un banco di disegno senza finestra se serve; la grafica la prova il lead.

## Coordinamento
MENTE-GUERRA è unito in main (le menti in `mind/`; il banco con la mente nel giro in `AstraWarSimCommandlet`/`tools/war.py mind`): non toccare `mind/` (se ti serve uno scenario nuovo, aggiungi
il file in `data/war/scenarios/`). DISTRUZIONE lavora sui danni interni dell'Aquila (AstraShipSubsystem, pianta, VITA): non toccarli.
Regole di memoria: al massimo 2 commandlet alla volta, UBT limitato a 4 azioni, mai due editor.
