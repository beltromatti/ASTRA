# Brief ABBORDAGGI-2 (F5.2): abbordare e farsi abbordare, con navette vere e soldati veri

Scritto da ABBORDAGGI dal testo del lead (3/10) e dal codice di F5.1 (in main, provato dal lead nel gioco: `astra.board.start 1` funziona da
capo a coda). Le parole dell'utente (2/10): «abbordaggi con navette, IA di squadra e FPS», le navi nemiche e alleate che «si comportano e si
simulano come l'Aquila, per abbordaggi e PvP». Nelle partite dell'utente (2/10 sera, app impacchettata) **l'abbordaggio non è mai stato raggiunto**:
oggi parte solo da un comando di prova. F5.2 lo porta nella guerra, in tutti e due i versi.

LEGGI: CLAUDE.md; ARCHITETTURA §1bis (prompt, contesto e strumenti veri; il codice per le regole del mondo; niente filtri sulle parole) e §6;
[ABBORDAGGI.md](../ABBORDAGGI.md) (F5.1: la simulazione di squadra, l'ospite, il Capitano con l'arma, la rete dei marine); GUERRA.md (la nave
come la battaglia la vede: `FAstraBattleShip`, i velivoli, la difesa puntuale, `bDisabled`); VITA.md (i 80 marine del ruolino); DISTRUZIONE.md
(le persone, il Capitano che cade); TELETRASPORTO.md (`AstraTransport*`: le facce dello scafo, gli scudi, la portata); `mind/astra_mind/war_minds.py`
(gli strumenti degli ammiragli e dei comandanti) e `marines.py` (Reyes e i capisquadra).

## Cosa si costruisce (il testo del lead, ripreso)
1. **Le nostre truppe sulle navi nemiche.** Una nave disabilitata o abbandonata (l'Acheron di Solm, ferito a bordo, è il primo caso) può essere abbordata dai
   marine dell'Aquila. L'interno della nave si costruisce **dal piano della sua classe**: un generatore leggero va bene (i piani per classe di NAVE-3
   non esistono ancora; quando ci saranno, stesso formato, e il gioco userà quelli). Il Capitano può andare con i marine, con la navetta d'assalto o
   con il teletrasporto dove le sue regole lo permettono (TELETRASPORTO è in main: `AstraTransporter*`).
2. **Navette d'assalto visibili.** Una scialuppa del Mandato che vola fino allo scafo e si aggancia **prima** della breccia; la nostra (il Kestrel dei
   marine) che parte dall'hangar del Ponte 8. Sono oggetti veri della battaglia (come i Falcon e gli Harpy): si vedono, hanno uno scafo, **si possono
   abbattere** (la difesa puntuale e i caccia sparano loro, come a ogni velivolo); l'aggancio è ciò che apre la breccia.
3. **La guerra decide.** Le menti ordinano un abbordaggio con uno strumento vero: l'ammiraglio e i comandanti del Mandato contro l'Aquila o le sue
   consorti; il Capitano, Reyes e Rourke per i nostri. CAMPAGNA (il lavoro sullo strato strategico, in corso) può chiamarlo: interfaccia pulita (il
   comando `boarding` e uno strumento di mente) e la sua forma al lead.
4. **Gli ordini ai marine restano complessi** (squadre, formazioni, attacco e difesa) e **tutto è intelligenza da prompt e contesto**, mai filtri di
   codice sulle parole: il codice porta i fatti, la fisica e il drill; il giudizio è delle persone.

## Principi di costruzione
- **Un abbordaggio è una sola cosa vista da due lati**: attacca chi arriva dalla navetta, difende chi sta a bordo. La simulazione di squadra (F5.1) ha oggi
  due dottrine legate alle parti (il Mandato attacca, i marine difendono): diventano **dottrine di ruolo** (attacco, difesa) che le parti prendono come il
  caso vuole. Lo stesso codice, provato dallo stesso banco, serve i due versi e le navi di ogni classe.
- **Un piano per ogni nave**: la simulazione gira su una mappa di portali (`FAstraBoardMap`) costruita da un piano (formato di `aquila_plan.json`); l'Aquila
  ha il suo (3234 stanze), le altre classi hanno un piano leggero generato dai dati della classe (ponti, spina, ponte di comando, sala macchine,
  hangar, alloggi, armeria, infermeria) con la stessa forma, pochi ponti e poche centinaia di stanze: bastano alla corsa fra due portelli e al corridoio.
- **Il codice è il mondo, non il giudizio**: dove sta uno scudo, se una navetta passa la difesa puntuale, quanto dura un aggancio, chi vince una
  sparatoria, quanto costa tagliare una paratia, sono regole del mondo (con numeri provati sul banco). Cosa abbordare, quando, con quanti uomini, dove
  tagliare, cosa chiedere ai marine, sono decisioni delle menti (che leggono i fatti veri: lo scudo, la difesa puntuale, la nave abbordabile).
- **Niente numeri truccati**: una navetta che entra nell'inviluppo della difesa di una nave che spara muore (come un velivolo); si abborda ciò che non
  può difendersi (disabilitato, difesa puntuale rotta, il bersaglio che si è arreso) o ciò che la saturazione e la scorta lasciano passare. Gli
  strumenti dicono la verità alla mente («the Aquila's point defence is up: four channels»), che decide se aspettare.
- **Costo**: l'abbordaggio non aggiunge chiamate fisse; le menti nuove (strumenti) vivono nei ruoli e nelle cadenze che esistono; il combattimento è
  codice (decimi di ms a passo). Una prova dal vivo breve (≤ 0,10 $, costo riportato), il resto offline con modelli finti.

## Architettura

### 1. Navette d'assalto nella battaglia (`AstraBoardCraft.*`, ganci nominati in `AstraBattleSubsystem.*`, `AstraWarCraft.cpp`, `AstraWarShipAI.cpp`)
- Un tipo di velivolo in più (`CraftKind 3`, missione `board`): la **scialuppa d'abbordaggio del Mandato** (Skiff: 10 fanti, scafo 140, 220 m/s) e il **Kestrel**
  dell'Aquila (12 marine, scafo 200, 180 m/s). I dati sono una tabella mia (`AstraBoardCraft`): quanti ne porta ogni classe (Acheron 4 Skiff, Styx 2, Lethe 1; Aquila 2
  Kestrel dal Ponte 8, Praetorian 2, Vigilant 1), la mesh, il carico.
- **Volo**: in rotta verso un punto d'aggancio sullo scafo bersaglio (nel suo sistema di riferimento: lo segue anche se ruota), rallenta, si allinea, aggancia entro
  pochi metri a pochi m/s; **non evita l'inviluppo della difesa** (deve passarlo): la difesa puntuale lo colpisce con la sua probabilità (più bassa dei caccia, 70 di
  danno a colpo), e così i caccia nemici. Aggancio → dopo il «tempo di presa» (≈ 12 s) la breccia si apre. Abbattuta: i suoi uomini muoiono con lei (i marine sono
  caduti con il nome nel ruolino).
- **Partenza**: da una nave (la sorgente) con i posti dei velivoli (l'hangar di classe); la nostra dal portello del Ponte 8. Eventi di battaglia (`Launched`, `Docked`,
  `Destroyed`, `Departed`) letti dall'ospite come si leggono le morti (`ConsumeBoardingEvents`).
- **Si vede**: mesh nuove (Skiff, Kestrel esterno) nel flusso di `UAstraWarDraw` (istanze per nome di mesh, luci); sono fatte in Blender (come le altre navi) e
  importate; senza la mesh il gioco disegna la forma di ripiego della guerra.

### 2. La simulazione per ruoli (`AstraBoardSim.*`, `AstraBoardAI.cpp`)
- `Mission` generale: parte che attacca, parte che difende, **obiettivo** (una stanza da tenere, una persona da raggiungere e portare fuori, il ponte, la sala
  macchine, «tutti i difensori giù»), breccia e punto d'ingresso. Gli esiti (difensore tiene, attaccante prende, attaccante respinto, scaduto) con i nomi di oggi come caso
  del Mandato che attacca.
- `PlanAttack`/`PlanDefend`: la colonna sulla via dell'obiettivo, l'aggiramento, la ritirata, il taglio delle paratie (oggi del Mandato); l'imboscata, gli angoli, la
  squadra di reazione e i fucilieri di guardia (oggi dei marine). Chi attacca dall'Aquila sono i marine (con la loro abilità e la loro armatura), chi difende nell'Acheron
  è l'equipaggio e la guardia di Solm (soldati del Mandato, a un posto di guardia o in marcia).
- Gli ordini ai marine (`hold`, `advance`, `assault`, `fall_back`, `follow_captain`, `rescue_captain`, `withdraw`, `stand_down`) valgono per i due versi e per
  luoghi di qualsiasi piano; in attacco si aggiungono i luoghi della nave nemica (il ponte, l'alloggio dell'Archon, la sala macchine, l'hangar) e le formazioni
  (colonna, due ali, entrata a due squadre). Provato dal banco (nuovi scenari: l'attacco dall'Aquila a una nave tenuta dal Mandato).

### 3. I piani delle classi (`tools/ship_plan_light.py`, `data/ship/plans/<classe>_plan.json`)
- Il generatore scrive, da un piccolo modello di classe (lunghezza, larghezza, ponti, dove stanno ponte di comando e sala macchine, hangar, quanti uomini), un piano
  nel formato di `aquila_plan.json` (ponti, stanze con riquadri e uso, porte, collegamenti, scale e ascensori, l'involucro). Ha le **stanze che contano** di una nave
  abbordata: il ponte di comando e il corridoio di comando, la sala macchine con il reattore, l'hangar, gli alloggi dell'equipaggio e i camerini, l'armeria,
  l'infermeria, il brig, le camere stagne e i punti d'ingresso lungo lo scafo. Classi: Acheron, Styx, Lethe (Mandato), Praetorian, Vigilant (ASTRA).
- `FAstraDamageMap` legge un piano da un percorso qualsiasi (piccola aggiunta nominata, oggi legge solo quello dell'Aquila) e la mappa dei portali si costruisce da lì.
- **Dall'esterno all'interno**: il punto d'aggancio sullo scafo (sistema di riferimento della nave) corrisponde alla stanza di un ponte del piano che tocca l'involucro:
  è la breccia. Per l'Aquila `PickBreach` resta, ma l'aggancio la decide dal punto in cui la navetta sta.

### 4. L'ospite (`UAstraBoardSubsystem`): un abbordaggio è una *scena* con la sua mappa
- La scena ha: la nave abbordata (la sua mappa e il suo piano), il verso (in entrata o in uscita), la sorgente, le navette (quelle della battaglia), gli uomini
  (i marine del ruolino scelti per il Kestrel, o i fanti del Mandato dalle navette), l'obiettivo, e un **posto nel mondo** per i corpi (l'Aquila: il suo; un'altra
  nave: un interno in lontananza dove il Capitano può andare).
- Le fasi: *approach* (navette in volo: la nave lo sa, i marine vengono chiamati se è l'Aquila), *docked* (presa, breccia che si apre, paratie), *fight* (la simulazione,
  i corpi attorno al Capitano se è nella scena, rapporti), *aftermath* (l'esito; i feriti in infermeria; i caduti con il nome; la nave presa che cambia stato: preda,
  ancora relitto, Solm in custodia o morto, ciò che il regista deve sapere come evento della nave).
- Più scene insieme: **una osservata** (con i corpi e il Capitano) e le altre solo come simulazione (nessun corpo; i rapporti e l'esito arrivano come eventi e,
  per i nostri, dalla radio dei marine); le consorti dell'Aquila abbordate dal Mandato seguono questa strada.

### 5. Il Capitano che va
- **Con la navetta** (`captain: true`): sale con i marine (dissolvenza, rumore di motori, titolo del velivolo: nessuna navigazione); all'aggancio compare nell'interno
  della nave abbordata, all'ingresso, con l'arma in mano e i marine intorno; alla fine (o con un comando di rientro, o caduto) torna all'Aquila.
- **Col teletrasporto**: dove le regole di TELETRASPORTO lo permettono (faccia aperta: nave disabilitata, scudo giù, portata); l'ospite espone l'interno della nave abbordata come
  destinazione (una piccola interfaccia che il teletrasporto legge; il gancio nel suo codice lo chiedo al lead se non è banale).
- L'interno di una nave nemica è **geometria vera** costruita sul momento dal piano (pavimenti, pareti con i varchi delle porte, soffitti, strisce di luce, un pool di luci
  vicino al Capitano) con istanze di forme semplici e i materiali di ASTRA; sparisce quando il Capitano rientra. Lo stile è quello della bibbia (STILE.md).

### 6. La guerra decide: l'interfaccia (forma da dare a CAMPAGNA)
- **Comando `boarding` (esteso, retrocompatibile)**: `{direction: "in"|"out", target, source, craft, boarders, objective, breach, captain, lockdown, warn_s, instant}`; senza
  `direction` è un abbordaggio dell'Aquila come oggi (`skiffs`, `boarders`, `breach`, `source`, `lockdown`, `warn_s`). `target`/`source` sono una nave (id di contatto, nome,
  «aquila»). Risponde con i fatti: partito, rifiutato e perché (difesa puntuale attiva, nave non abbordabile, nessuna navetta libera, già in corso).
- **Strumento di mente `board`** (ruoli di guerra: ammiragli e comandanti di tutte e due le parti, in `war_minds.py`; `board_ship` per Reyes e l'XO nella rete dei marine): il
  contesto dà ciò che serve a decidere (le navi abbordabili e perché, le navette che ho, la difesa puntuale del bersaglio); la risposta è un fatto vero.
- **Stato per le menti** (`ship_state.boarding` e il quadro dei marine): la scena, le navette (in volo, agganciate, abbattute), il verso, l'obiettivo, i nostri e i loro, i
  luoghi della nave nemica; gli eventi di battaglia «boarding craft launched / docked / destroyed».
- **Per CAMPAGNA**: `await self._director_command("boarding", {...})` (la stessa porta di oggi); lo strumento `board` può essere dato a chi decide le flotte; l'esito è un
  evento (`boarding: ...`) che il regista legge.

### 7. Le menti dei marine all'attacco
- La rete dei marine (Reyes e i capisquadra) sa anche attaccare: il suo prompt (stabile) dice come si abborda (ingresso, spinta, formazioni, cosa si perde a spingere), il
  quadro mostra la nave nemica (stanze per uso, i nostri e ciò che si sa di loro), gli ordini sono quelli di oggi con i luoghi del piano nemico. Giudizio nelle parole, non nei filtri.

## Prove
- **Banco senza grafica** (`tools/boarding.py`, commandlet): scenari nuovi: attacco dall'Aquila a una nave tenuta dal Mandato (sull'Acheron generato: chi vince, quanto, a che
  costo, in quanto tempo; i numeri come per F5.1), difensori e attaccanti simmetrici (ruoli scambiati sullo stesso piano), il piano di ogni classe (si legge, i portali sono
  ragionevoli, ogni stanza si raggiunge), la navetta in volo contro la difesa puntuale (probabilità di arrivare per numero di canali e di navette) con la battaglia di GUERRA a
  testa bassa.
- **Mente offline** (modelli finti): gli strumenti, i rifiuti con la loro ragione, il quadro, la regola dei ruoli, il comando come lo prende il gioco (letti dal C++).
- **Dal vivo** (≤ 0,10 $, riportato): una scena con Reyes in attacco e un ordine di abbordaggio a Rourke.
- Il lead prova nel gioco: i passi nel report finale.

## File
Miei: `AstraBoardCraft.*`, `AstraBoardSim.*`, `AstraBoardAI.cpp`, `AstraBoardMap.*`, `AstraBoardSubsystem.*`, `AstraBoardEvents.cpp`, `AstraBoardMind.cpp`, `AstraBoardInterior.*` (la
geometria dell'interno), `AstraBoardSimCommandlet.*`, `tools/boarding.py`, `tools/ship_plan_light.py`, `data/ship/plans/`, `mind/astra_mind/marines.py`, `docs/ABBORDAGGI.md`.
Ganci nominati in file di altri (piccoli, elencati nel report): `AstraBattleSubsystem.h` e `AstraWarCraft.cpp`, `AstraWarShipAI.cpp` (la missione `board`, la difesa
puntuale contro le navette, gli eventi), `AstraDamageMap.*` (leggere un piano da un percorso), `AstraShipSubsystem.cpp` (il comando), `war_minds.py`, `tools.py`/`crew.py`/`router.py` (gli
strumenti e le regole dell'equipaggio), `AstraWarDraw.*` (le mesh nuove). Non miei: la plancia, la nave e i suoi interni, ASCENSORI, il teletrasporto, CAMPAGNA.

## Ordine di lavoro e consegne
1. **Questo brief**, poi la simulazione per ruoli e i piani delle classi (banco: l'attacco all'Acheron) — consegna 1.
2. Le navette nella battaglia (volo, difesa, aggancio, eventi, mesh) e l'ospite a scene (in entrata: l'Aquila abbordata da navette che si vedono; in uscita: i marine
   sull'Acheron) — consegna 2.
3. Il comando esteso, gli strumenti delle menti, i marine all'attacco, l'interfaccia per CAMPAGNA — consegna 3.
4. Il Capitano che va (navetta, teletrasporto, l'interno costruito) — consegna 4.
Ogni consegna si unisce da sola (compila, banco verde, niente a metà). Al lead dopo la 1 la forma dell'interfaccia (§6) perché la dia a CAMPAGNA.
