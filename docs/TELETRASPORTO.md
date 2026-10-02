# TELETRASPORTO — la Transporter Room e il lattice di trasporto (F6)

Il brief è `docs/brief/TELETRASPORTO.md`; il canone è BIBBIA §4. Questa pagina dice **cosa c'è**, **dove sta**, **come si prova** e **cosa manca**.
Tutto il testo del gioco è in inglese; qui i nomi ufficiali restano inglesi.

## 1. In breve

Un trasportatore «alla Star Trek» per chiunque e qualunque cosa: il Capitano, l'equipaggio (i 560 di VITA), una squadra di marine, un carico fino a 2 t, da una
stanza all'altra della nave, da una pedana a una stanza, verso una nave alleata a portata, verso la superficie del pianeta della demo (e di ritorno). Le regole sono
**codice** (il mondo: `AstraTransportRules.*` più il sottosistema), il **Capo della sala** è una persona con una mente sua (Chief Petty Officer Rhea Ostrander,
`mind/astra_mind/transporter.py`) che legge la console e esegue o dice perché no, l'ordine passa da Operations o dall'XO come strumento vero (`transporter`), e l'effetto
visivo e sonoro (colonne di luce, fantasma del corpo, schermo del Capitano) è a istanze, senza Niagara.

| Cosa | Dove |
| --- | --- |
| I numeri di tutto (portata, ciclo, aggancio, scudi, disturbo, stanza, pedane) | `data/ship/aquila_transport.json` |
| Le regole (pure, deterministiche, senza attori) | `Source/ASTRA/AstraTransportRules.{h,cpp}` |
| Il mondo: sala, pedane, ordini, ciclo, buffer, persone fuori nave | `Source/ASTRA/AstraTransporterSubsystem.{h,cpp}`, `…World.cpp` (lo scafo, i contatti, le parole di un ordine), `…Card.cpp` (la scheda, i comandi) |
| Ciò che si vede e si sente | `Source/ASTRA/AstraTransportFx.{h,cpp}`, `AstraTransportConsole.{h,cpp}` (lo schermo a parete) |
| La mente | `mind/astra_mind/transporter.py` (+ `tools.py`, `crew.py`, `context.py`, `models.py`, `server.py`) |
| I banchi | `tools/transport.py run` (regole + mondo senza grafica), `mind/bench/transporter_unit.py` (modello finto), `mind/bench/transporter_live.py` (modello vero, ~0,002 $ a scena) |
| Gli asset | `tools/ue_scripts/make_transporter_fx.py`, `tools/art/transporter_sounds.py`, `tools/ue_scripts/import_transporter_audio.py` |

## 2. La fisica del fascio (regole nel codice)

- **Chi e cosa**: il Capitano (non può essere portato su un'altra nave: non c'è interno in libreria, né da un Falcon o una capsula), una persona (nome, grado, mansione,
  `npc17`, «marines 6», «pad 3», «away team»), un carico fino a 2 000 kg a pedana (pedana cargo). Sei persone per ciclo. Non si trasporta chi tiene un posto con un attore
  suo (le postazioni di plancia, i letti dell'infermeria) né chi sta in una stanza **schermata dallo schema** (`magazine`, `armory`, `quarantine`: né uscita né arrivo).
- **Da dove a dove**: pedana ↔ pedana, da sito a sito dentro l'Aquila (da dove si sta, il fascio non esce dallo scafo: nessuno scudo conta), verso una nave alleata o
  nemica a portata, verso la superficie del mondo sotto (campo d'atterraggio) e ritorno. Dall'**infermeria** due pedane d'emergenza (`med1`, `med2`) con un sistema a parte
  (400 km) che funziona anche con la sala principale spenta.
- **Gli scudi, faccia per faccia** (GUERRA ha sei settori: prua, poppa, babordo, tribordo, dorsale, ventrale). Il fascio **esce dalla faccia dello scafo che guarda il
  bersaglio** (scatola normalizzata: una nave lunga 800 m e larga 140 è «di fianco» molto prima di una sfera) **ed entra dalla faccia che guarda noi**. *Una faccia aperta
  per capo basta*: aperta = scudo giù, nave disabilitata, o settore con ≤ 5 % di carica. GUERRA non sa abbassare una faccia sola: per la nostra nave la **finestra scudi**
  (`shield_window`) tiene giù *tutti* gli scudi per il ciclo (Tactical `shields_off`, poi rimette il modo di prima: `face_threat` o altro), e un settore abbattuto in
  combattimento è già aperto. Un alleato apre la sua faccia per il ciclo a parola del suo capitano (non se è in combattimento: un nemico entro 12 km). Un nemico: il settore va
  abbattuto sotto il 5 % o la nave disabilitata. Una traccia non classificata (nessuna scheda degli scudi) non si può mirare: rifiuto «unknown».
- **Portata** 30 000 km (scalata dall'energia della sala e dei sensori), **disturbo** lungo la linea (un capitale Mandate con la strobo: campana di 9° attorno alla sua
  direzione, dimezzata a 60 km, bruciato solo da vicino; il suolo in mano al Mandate disturba), **manovra** (accelerazione > 9 m/s² o virata > 2°/s: no; fra 3 e 9, 0,8 e 2: costa
  qualità), **campo del Janus Gate** (dentro 25 km o nella corsia: mai; fino a 60 km costa).
- **Energia e guasti**: 8 s e 40 MW (+6 per soggetto in più) a ciclo, che in battaglia **si tolgono agli scudi** (−20 % di potenza scudi mentre un ciclo gira) e +0,6 % di
  calore. La sala ha il suo stato dal **modello dei danni** (`d5_transporter_B1`: potenza, rottura, aria, fuoco, fumo, calore): sotto il 12 % di potenza o in
  fiamme non si fa nulla, fra 12 e 60 % ci si mette di più e la qualità cala. Reattore spento: niente fascio.
- **L'aggancio** si costruisce in tempo (1,5 s dentro, 3,5 verso una nave, 5 verso terra, +0,6 s ogni 1000 km, +2 s su un nemico) e ha una qualità che segue le condizioni
  (portata, disturbo, manovra, Gate, energia della sala, sensori e calore solo fuori dallo scafo); si degrada in fretta, si recupera piano, si **perde** se resta sotto il 25 %.
  Un aggancio sotto il 55 % non basta, salvo la **parola del Capitano** (`override: weak_lock`), che lo costruisce a soglie basse e ne accetta il rischio.
- **Il ciclo**: carica 0,4 s → smaterializzazione 3,6 s (chi parte è ancora dov'è) → il **buffer** (il pattern è fuori nave: VITA lo tiene «in transito») → rimaterializzazione
  3,6 s (appare a destinazione) → assestamento 0,4 s. Il buffer tiene 90 s al massimo: se l'aggancio si perde con qualcuno dentro, la console lo ricostruisce; scaduto, richiama
  il pattern **alle pedane da cui è partito** (i carichi si perdono). Un arrivo può essere **ritardato** (2-10 s nel buffer), **fuori bersaglio** (un altro posto della stanza, o
  qualche metro fuori sul terreno), e solo con un aggancio **forzato** sotto il 30 % può **disperdersi** (la gente viene ricomposta sulle pedane di partenza, scossa; il carico è perso).
  Le probabilità vengono dalla qualità: a qualità piena non succede mai niente di strano.
- **Un ordine non si sposta dietro le spalle**: «pedana 3» occupata è rifiutata (`occupied`), non dirottata su un'altra. Un posto dove arrivano fuoco, fumo, poca aria è rifiutato
  (`hazard`) salvo la parola del Capitano (`override: hazard`). Chi è già in un trasporto in corso non si può ordinare di nuovo; un secondo ordine si accoda dietro il primo (fino a quattro).
- **Chi è fuori nave**: sulla superficie o su una nave resta «away» (VITA non lo simula, non si trova a bordo; il localizzatore dice dov'è; la scheda lo elenca); si riporta con
  «away team» o per nome. Se l'Aquila attraversa un Gate lasciandoli, restano **lasciati indietro** e fuori portata.

## 3. La sala viva

- **Dove**: la Transporter Room è `d5_transporter_B1` (Ponte 5, sezione B), che il sottosistema trova **dalla pianta** (nessuna coordinata fissa: quando NAVE-3 la sposta,
  le pedane la seguono; `tools/transport.py check` dice se `data/ship/aquila_transport.json` e il kit tornano). Sei pedane in cerchio sulla piattaforma (centro locale 17,0; 8,6, raggio
  2,0), la pedana cargo (4,6; 13,0), l'emettitore in alto (altezza 2,95), il Capo in piedi dietro i due operatori e davanti alla console (8,4; 8,6), lo schermo a parete sul pannello
  della parete di fondo. I tecnici sono i **tecnici di VITA** (i due operatori seduti, l'ingegnere, i tecnici: nei turni dei sensori); il Capo è un attore in più (`AAstraCrewMember`
  `xfer_chief`) che esiste solo quando il Capitano è nei paraggi (altrimenti parla all'interfono).
- **Lo schermo a parete** (`AAstraTransportConsole`): le sei pedane con chi ci sta e il loro stato, le sei facce degli scudi con la carica e la faccia che il fascio attraversa,
  accelerazione, virata, disturbo, distanza dal Gate, i trasporti in corso (fase, aggancio, qualità, cosa lo ostacola) e *cosa si può raggiungere adesso* (sì/no e perché).
  Si ridisegna 4 volte al secondo solo se il Capitano è vicino. `astra.xport.dump` lo scrive in PNG.
- **La scheda** (`ship_state.transporter`, `SnapshotJson()`): la stessa console come la legge il Capo, con le `options` già valutate (per la superficie, ogni nave nel raggio, le
  pedane d'emergenza: «ok», oppure cosa lo impedisce e cosa lo risolverebbe), i trasporti, chi è fuori nave, chi c'è nella sala. Le notizie della sala arrivano come eventi
  `transporter: …`; il pericolo (un aggancio perso con qualcuno nel buffer, un pattern perso) lo marca il **mondo** con `URGENT:`, il Python non lo indovina dalle parole.

## 4. Gli ordini sono strumenti veri

- Comandi del gioco (`ApplyCommand`): `transport {who[], to, from?, energize: auto|hold, shield_window?, override[]?}`, `transport_energize {id?}`, `transport_abort {id?}`. La risposta
  è in inglese semplice con i numeri («X3 accepted: … lock in about 3.5 s at 100%, then a 8.0 s cycle, 40 MW; our shields will be held down for the cycle») o il rifiuto
  con **ogni** ostacolo e cosa lo risolve (`[shields_own] … (to clear it: …)`).
- **Plancia → Capo**: Operations (Tanaka) o l'XO (Serra) hanno lo strumento `transporter` (`beam`, `energize`, `abort`, `ask`): passano l'ordine del Capitano nei suoi termini
  e dicono **una** riga; il Capo risponde per sé. Mai di iniziativa: ogni trasporto è un ordine del Capitano (`initiative_names` non lo include). La regola dell'equipaggio
  (`crew.py`) dice cosa richiede la **parola del Capitano**: lui stesso, qualunque cosa su una nave nemica o un mondo del Mandate, la finestra scudi con nemici in giro, ogni `override`.
- **Il Capitano parla al Capo** in sala (o ne è a portata d'orecchio): la sua mente decide se le parole erano per lei (`say`) o no (`pass`: il cancello della plancia segue il suo
  verdetto, insieme a quello degli NPC); lui ha la precedenza e il suo turno di sole notizie si interrompe, quello che risponde a lui no.
- **Il Capo** (`TransporterRoom`): un modello (ruolo `transporter`, DeepSeek flash, ~0,0005 $ a chiamata) con la scheda in mano, gli strumenti `say`, `transport`, `energize`, `abort`,
  `locate` (il localizzatore del personale), `pass`; fino a due riletture per leggere un rifiuto o un ordine eseguito in silenzio. **Se il modello cade o tace**, la console esegue l'ordine
  della plancia *com'è stato scritto* e lo dice (un rifiuto suo, invece, resta: è una decisione). Ricorda le ultime parole con il Capitano e il suo bilancio (inviati, persi, annullati,
  rifiutati) fra le sessioni (`mind/.cache/xfer_journal.json`, azzerato da una campagna nuova).

## 5. Ciò che si vede e si sente

Tre strati a istanze (scintille 420, colonne 12, anelli 12: un componente e un materiale ciascuno, come gli effetti della guerra e dei danni), una luce calda, nessun attore per
scintilla. Su ogni soggetto: una **colonna** morbida di luce con bande che salgono e un fronte luminoso che la percorre dai piedi alla testa, scintille che salgono (smaterializzazione)
o convergono (rimaterializzazione), e il **fantasma del corpo**: il corpo vero (un `AAstraLifeBody` o il Capo) sparisce e al suo posto c'è la sua stessa mesh in un materiale che la
mangia dai piedi in su (o la forma), seguendo la posa viva. Gli **anelli delle pedane** dicono lo stato (spenta, occupata, aggancio in corso a segmenti che girano, agganciata, in
ciclo, guasta a sfarfallio); il **ronzio** gira finché un ciclo dura. Per il **Capitano** (che non ha un corpo visibile) lo schermo: celle di luce che si accendono a caso, scintille,
un velo bianco-oro che lo copre alla partenza e lo lascia piano alla ricomposizione; i controlli sono bloccati. Suoni (originali, sintetizzati): carica, smaterializzazione,
rimaterializzazione, chirp d'aggancio, guasto, ronzio. `astra.xport.gain` scala la luce di tutti gli effetti (l'esposizione dell'interno può volerne più o meno; i suoni no),
`astra.xport.fx 0` spegne gli effetti e i suoni anche nel mezzo di un trasporto (colonne, fantasmi, luce, velo del Capitano spariscono, i corpi tornano visibili) senza toccare le
regole. Niente degli effetti è necessario alle regole: un asset mancante si salta con una riga nel log.
Lo **schermo a parete** mette il quadro sul piano del motore leggendo la posizione locale (u = 0,5 − x/100, v = 0,5 − y/100: gli assi del motore sono mancini, e visto dal lato della
normale con la y in su il piano ha la x verso la SINISTRA di chi guarda).

## 6. I banchi e i risultati

- `tools/transport.py run --scenario all` (senza finestra, `-nullrhi`, ~15-25 s): **67 prove delle regole** (le facce a entrambe le estremità, la portata, il disturbo lungo la linea, la
  manovra, il Gate, lo stato della sala, l'aggancio, gli arrivi) e **38 del mondo** in un mondo senza grafica con la pianta vera (la v2 di NAVE-3, 3234 compartimenti), i 560 di VITA, il modello dei danni e la
  battaglia: ordini dentro la nave, il ciclo con le sue fasi, la coda, l'aggancio tenuto fino alla parola, l'annullo a metà, la finestra scudi (giù per il ciclo, su dopo), una
  squadra su una nave alleata e il richiamo, un abbordaggio su una nave senza scudi, la discesa sul pianeta e il ritorno, un carico, la manovra dell'Aquila (la scheda mostra virata e
  spinta, una spinta forte nega il fascio con `[motion]`), i disturbatori (la prova si fa solo se in plancia ce n'è uno: le regole coprono la strobo), la stanza senza energia, e il
  costo (il tick sotto il millisecondo; la scheda per la mente, una volta al secondo, 0,08 ms con i contatti di una battaglia). Le pedane si confrontano con le postazioni di
  pedana della pianta (le due «visitor» di NAVE-3 stanno sulle pedane 1 e 4), non con numeri fissi: la sala è passata da x −20..4 a x 0..24 nella pianta v2 e le pedane l'hanno seguita.
  **105/105.** (Il processo del commandlet esce con codice 1 perché nella copia di lavoro i `.uasset` sono ancora puntatori LFS e il motore conta i loro errori di caricamento: il
  verdetto è la riga `VERDICT: PASS`, e `tools/transport.py` lo legge da lì.)
- `tools/transport.py run --scenario shapes`: sonda sulle forme base del motore, lette dai vertici (il piano è 100 × 100 cm in XY con la normale in su, cilindro, sfera e cubo ±50 cm):
  conferma le ipotesi dello schermo a parete e delle colonne di luce.
- `mind/bench/transporter_unit.py` (modello finto, anche sulle carte vere scritte dal gioco): **34 prove**. Tutta la mente offline dopo l'unione con main (flight, lift, marines, npc,
  stations, war, transporter: `python -m unittest bench.flight_server bench.flight_unit bench.lift_server bench.lift_unit bench.marines_server bench.marines_unit bench.npc_server
  bench.npc_unit bench.stations_server bench.stations_unit bench.transporter_unit bench.war_director_unit bench.war_minds_unit bench.war_server`): **412 prove verdi**.
- `mind/bench/transporter_live.py` (modello vero, il Capo da sola): 8 scene, **~0,002 $ a giro**. `mind/bench/transporter_crew_live.py` (modello vero, **tutta la catena**: il Capitano
  parla in plancia, Operations o l'XO passano l'ordine, il Capo lo esegue sulla console o dice perché no; la console risponde dalla carta vera): 6 scene, **~0,006 $ a scena**.
  Costo totale dei miei giri dal vivo: ~0,044 $.
- `tools/art/transporter_fx_check.py`: i 5 shader compilano con il DXC del motore e lo script dei materiali è controllato contro lo stub dell'editor (nessun editor).
- `tools/transport.py check`: la pianta e il kit tornano (13/13).

## 7. Cosa provare nel gioco (per il lead)

1. Una volta: `tools/ue.py pyfile tools/ue_scripts/make_transporter_fx.py` (i materiali), `uv run --with numpy --with soundfile --with scipy python tools/art/transporter_sounds.py` e
   `tools/ue.py py "exec(open('tools/ue_scripts/import_transporter_audio.py').read())"` (i suoni), `tools/transport.py stage` (il file dei numeri), poi ricompilare.
2. **La sala**: `astra.xport.room` (il Capitano in sala davanti alla piattaforma). Si vedono gli anelli delle pedane, il Capo in piedi dietro gli operatori, lo schermo a parete.
   Parlargli: «Chief, where does the transporter reach?»; `astra.xport.card` stampa quello che legge; `astra.xport.dump` disegna lo schermo.
3. **Un trasporto dentro la nave**: dalla sala, «Chief, send me to Main Engineering» (o `astra.xport.send captain "Main Engineering"`): il velo, la colonna, la ricomposizione in sala macchine.
   Poi «Chief, send Lieutenant Sato to the bridge» e guardare i corpi di VITA dissolversi.
4. **Il pianeta**: a Ponte, «Chief, take me to the surface»: gli scudi sono su, quindi il Capo (o Operations) dice che serve la finestra scudi; dire «fallo con la finestra» o
   `astra.xport.send captain surface window`. Atterra al campo; `astra.xport.send captain "pad 3" window` o «Chief, one to beam up» (da terra: tramite Operations) per tornare.
5. **Negato dagli scudi in battaglia**: con un nemico a portata (scenario di battaglia): `astra.xport.send "marines 4" T-xx`: rifiuto per scudi nostri e suoi, con cosa lo risolve.
   Abbattuto il settore sotto il 5 % e con `window` (la parola del Capitano) la squadra passa; la scheda dice chi è «away» e dove.
6. Se qualcosa non torna: `astra.xport.info`, `astra.xport.fx 0`, `astra.xport.gain 2`, `astra.xport.reset`.

Comandi: `astra.xport.send <chi> <dove> [from=…] [hold] [window] [hazard] [weak]`, `astra.xport.energize [X3]`, `astra.xport.abort [X3]`, `astra.xport.room`, `astra.xport.info`,
`astra.xport.card`, `astra.xport.dump`, `astra.xport.reset`; variabili `astra.xport.fx`, `astra.xport.gain`.

## 8. Ganci in file degli altri (da rivedere nel merge)

Tutti piccoli e marcati `TELETRASPORTO`: **VITA** (`AstraLifeSim.*`, `AstraLifeSubsystem.*`: persone «in transito» o «fuori nave» non si simulano e non si trovano a bordo, un corpo
mostrato subito per chi arriva, il localizzatore sa chi non c'è); **nave** (`AstraShipSubsystem.cpp`: il comando `transport*`, la scheda in `ship_state`, i 40 MW del ciclo tolti agli
scudi in `PowerFactor`); **battaglia** (`AstraBattleSubsystem.*`: `GateDistanceKm()`); **mente** (`models.py` il ruolo `transporter`, `tools.py` lo strumento `transporter` e il filtro
quando la nave non ha la sala, `crew.py` la regola e la riga della sala in plancia, `context.py` il parlante `xfer_chief`, `server.py` il Capo come quinta rete accanto a PNG, volo
e marine, `initiative.py` la scheda del Capo fuori dal prompt dell'ispezione); **scale** (`AstraLadderSubsystem.*`: `Release(Pawn)`, il Capitano che sale una scala e viene teletrasportato
resta libero). L'unione con main (ABBORDAGGI, ascensori, la pianta v2) ha avuto conflitti solo dove le due parti aggiungevano accanto: i marine presi da una lotta (`bCommandeered`) e
le persone in transito o fuori nave non hanno corpo né passi (la condizione ha tutte e tre); la scheda ha insieme `transporter` e `boarding`; il server tiene la rete dei marine e il
Capo; `tools_for(state, ctx)` tiene il filtro della sala e la vettura dell'ascensore. Chi i marine hanno preso per una lotta non si teletrasporta e non entra nelle squadre (`[subject]`).

## 9. Limiti noti e richieste

- Gli **effetti non si sono potuti vedere** (nessun editor né GPU nel mio lavoro): shader e script sono controllati offline, la geometria e le luminosità no. `astra.xport.gain` e
  le costanti in `AstraTransportFx.cpp` sono la manopola. La riga dello schermo a parete (`AstraTransportConsole.cpp`) è un layout calcolato a mano: verificarlo con `astra.xport.dump`.
- Il Capo è dietro gli operatori (stand 8,4; 8,6, cioè fra le due sedie e la console). **Richiesta a NAVE-3 / al lead, la più importante per la sala**: nella pianta v2 la stanza ha
  ancora la postazione `d5_transporter_B1.s0` (`transporter_chief`, seduta alla scrivania in fondo, a 14 m dalla piattaforma), che VITA riempie con una persona anonima: la sala avrebbe
  due «capi» e il Capitano che dice «Chief» potrebbe essere sentito da tutte e due (la mente dei PNG e la mia). Mettere `"station": "xfer_chief"` su `s0` (VITA lascia libere le
  postazioni con un attore proprio, come per i tecnici di plancia) e il Capo è solo lei, in piedi alla console; una postazione `stand` con quel nome la sposta altrove.
- Chi è fuori nave **non parla** (sulla superficie gli NPC trasportati non hanno un corpo né una mente: serve ABBORDAGGI/VITA); i carichi sono casse a terra, senza fisica.
- Dove il Capitano sta salendo una scala di Jefferies il fascio lo prende dalla scala (`Release`): dematerializza sui pioli e riappare a destinazione, mai appeso.
- Il Capitano **non può essere portato su un'altra nave** (nessun interno in libreria) né mentre è in un Falcon; se l'Aquila attraversa un Gate col Capitano a terra, il gioco
  non lo impedisce (richiesta al lead: il transito dovrebbe rifiutare con qualcuno fuori nave, o richiamarlo prima).
- Una pedana in più, il carico oltre i 2 t, i trasporti fra due navi: fuori dal brief.
- La lista dei fuori nave **non è salvata** nella campagna (si perde al riavvio: le persone «away» tornano a bordo); `SaveJson`/`ResumeFrom` della nave sono il posto.
- Il «ferito» dello scatter (una forzatura sotto il 30 %) non esiste: nessuno si fa male; serve un `HarmCrew(roster, cause)` pubblico sulla nave (richiesta).
