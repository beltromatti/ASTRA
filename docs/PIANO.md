# ASTRA — Piano v0.7

*5 ottobre 2026 · aggiorna la v0.6 (2/10). Nuovo: **il gameplay prima di tutto**. Le partite dell'utente del 5/10 ([PARTITE_2026-10-05.md](PARTITE_2026-10-05.md))
dicono che tutto c'è ma il Capitano non ha il controllo: troppe voci, risposte perse, scontri di secondi decisi da altri, attriti nei luoghi.
La v0.7 rifà il cuore del gioco (§0bis) prima di aggiungere altro. Architettura, moduli e contratti: [ARCHITETTURA.md](ARCHITETTURA.md).
Stato: [STATO.md](STATO.md).*

> **Lingua del gioco: inglese** (nomi, lore, scritte, interfacce). Gli NPC parlano la lingua del giocatore.

---

## 0bis. Il cuore del gioco (v0.7): chiarezza, controllo, battaglie epiche

Il Capitano **comanda, non micro-gestisce**: vede tutto, decide spesso, e la nave combatte bene da sola ma in modo brillante con lui.
Quattro pilastri, ognuno con il suo modulo e le sue misure (le partite vere come banco):

| Pilastro | Che cosa deve essere vero | Chi | Misura |
|---|---|---|---|
| **Chiarezza** | l'XO dà il quadro; gli altri parlano per la loro console quando serve, brevi; le reti radio (flotta, volo, marine, nemico) hanno chi le ascolta e riferisce; la routine sta sui registri e sul datapad; nessuna risposta al Capitano persa | VOCI-3 | battute in plancia al minuto in battaglia (oggi ~7, con 2 su 5 mai dette), ripetizioni, risposte perse (oggi 4 dell'ammiraglio), latenza della prima risposta |
| **Controllo** | l'iniziativa degli ufficiali sta dentro l'autorità data e si annuncia; il Capitano la cambia a parole; il timone e le armi eseguono e manovrano bene da soli | VOCI-3 · BATTAGLIA-3 | iniziative non chieste, ordini persi, nemici in ritirata persi dal timone |
| **Battaglie epiche e continue** | fuoco per minuti a decine di km, precisione che cala con la distanza, navi che muoiono a pezzi in minuti, nemico che si batte per un piano, calore e incendi che pesano senza paralizzare, tutto visibile | BATTAGLIA-3 · il lead (regia dello schermo) | durata degli scontri (oggi secondi), tempo con il fuoco in corso, chi uccide chi, ritirate premature |
| **Niente attriti** | i luoghi con un solo nome per tutti (teletrasporto, XO, comparse), la posizione del Capitano sempre fresca, l'abbordaggio in minuti e il Capitano con i suoi marine | il lead (LUOGHI) · ABBORDAGGI-4 | tentativi per arrivare dove si vuole, tempi d'abbordaggio |

Il lead gioca partite intere come un giocatore dopo ogni traguardo, con la stessa lista di misure, e rimanda ai moduli ciò che trova.
Poi, sullo stesso cuore: la plancia al dettaglio e le persone vere (MetaHuman), la guerra più grande, la nave intera, il pianeta.

## 0. L'obiettivo di questa fetta

**Una guerra stellare in cui sei il Capitano di una nave viva: grande, intelligente, cinematica e spietata, da giocare per
settimane senza mai annoiarsi.** Se questa fetta è perfetta, dimostra che ASTRA può diventare un universo intero,
multigiocatore, abitato da giocatori e da persone intelligenti: la stessa architettura crescerà fino a lì.

Il metro di giudizio è uno solo: **il Capitano ci gioca un mese di fila e non si stanca mai.**
- Ogni minuto ha qualcosa da decidere e ogni decisione pesa.
- La bravura cambia l'esito, e ogni volta la guerra è diversa.
- Ciò che vedi è bello e vero.

## 1. Il principio che guida tutto: intelligenza

ASTRA è il gioco più intelligente che esista. Le sue persone sono modelli intelligenti a cui diamo:
- **un buon carattere e una buona dottrina**, scritti nel prompt;
- **i sensi di chi fanno**: vedono ciò che la loro console mostra e sentono ciò che si dice nella stanza e sui canali
  che ascoltano, mai la verità nascosta;
- **le mani di chi fanno**: gli strumenti veri del loro ruolo, gli stessi che userebbe un giocatore umano.

Il codice è il corpo e la fisica: simulazione, lavoro continuo avviato da un agente, automazioni di bordo, meccanica della
conversazione. Mai filtri, tagli o regole sulle parole e sulle decisioni dei modelli: si migliorano i prompt, il contesto,
gli strumenti e la scelta del modello. Si valuta ciò che gli agenti fanno, giocando, non con espressioni regolari sul loro
testo. È un principio da applicare caso per caso, non un dogma (dettagli: [ARCHITETTURA.md §1bis](ARCHITETTURA.md)).

Il 30/9 sera questo principio è stato applicato:
- all'equipaggio: le sue parole arrivano come le dice;
- al router: un modello decide cosa esce su un canale aperto;
- ai messaggi del nemico: la brevità è della persona;
- al palco della voce (1/10): le battute che hanno aspettato o sono state interrotte le ripensa chi le doveva dire (§4.2).

## 2. Dove siamo (4/10)

| Area | Stato |
|---|---|
| **Controlli in prima persona**, banco di prova da terminale | fatto; strumenti del lead: `tools/play.py`, `tools/soak.py` (costo e tempi di un'ora), `tools/perf_ab.py` (A/B di prestazioni), `astra.debug.under/lookat` |
| **Plancia viva** (F1) | quasi fatta: postazioni vere, schermo principale intelligente (la sua telecamera cede il passo quando il fotogramma sfora), tavolo olografico (anche la guerra della March nella vista del settore), datapad, finestrone in realtà aumentata, HUD del caccia, equipaggio agente che vede ciò che è stato detto e ciò che aspetta di esserlo, plancia v3 **rifinita da ARTE-PLANCIA-2** (ottone, luce calda, corridoi del Ponte 1, alloggi del Capitano, abitacolo del Falcon), voce v2 col palco che ripensa, ordini del Capitano che non si perdono più. Mancano: le persone vere (F3), l'immagine più nitida (RETINA da provare) |
| **Guerra grande** (F2) | fatta la battaglia a scala di flotte; **lo spazio vivo** (SPAZIO-VIVO, primo traguardo nel gioco: Keeper Station, Arsenal, raffineria, miniera, 37 navi civili con orari e reazioni alla guerra; in corso relitti, detriti, capsule e il moto leggibile delle capitali); lo schermo principale pulito a ogni zoom; **fatta CAMPAGNA** (la guerra della March: flotte, Gate, rifornimenti, due menti strategiche, Rourke; le forze arrivano da 85–120 km e si vedono venire, la March gioca anche l'apertura; [GUERRA.md §10](GUERRA.md)). Costo misurato delle partite dell'utente: **1,20 $/ora** (prompt dell'equipaggio riordinato: ~15 % in meno) |
| **Persone vere** (F3) | ferma: serve l'autorizzazione Epic per i MetaHuman (RICHIESTE) |
| **La nave intera** (F4) | fatta: la pianta di NAVE-3 nel gioco (3234 compartimenti, 34 turboascensori e la navetta, tubi di Jefferies, atrio della plancia; nessun buco nei pavimenti, e una rete contro le cadute), 560 persone (VITA), danni interni veri (DISTRUZIONE), **le stanze rifatte da ARTE-INTERNI** (~97 tipi: mensa, alloggi, sale comuni, giardini con piante vere, infermeria, sala macchine, ponte di volo; viste nel gioco), **FLOTTA-VIVA** (le altre navi con la pianta della loro classe, equipaggio, comandante e modello dei danni: nel gioco l'Acheron perde gente e comandante prima di spezzarsi) |
| **Abbordaggi e prima persona** (F5) | F5.1 unito e provato; **braccia giuste** (cinematica inversa, tacca sull'asse in mira); in volo il Capitano torna a bordo con la guida di recupero (F o Flight Control); **le armi del Capitano** (armeria, armadietto del Ready Room, «portatemi un'arma»); **F5.2 nel gioco** (navette Skiff e Kestrel vere: partono, i marine si mobilitano, caccia, difesa di punto e scudi le fermano come devono); in corso: il Capitano che va all'abbordaggio (navetta o teletrasporto), lo scontro visto dentro l'Aquila |
| **Teletrasporto** (F6) | fatto e provato: sala, Capo con la sua mente, regole alla Star Trek, effetti |
| Pianeta (F7) · Rete e Windows (F8) | F7 dopo; **F8 Windows avviato** (WINDOWS: avvio della mente senza zsh, dati per piattaforma, MetalFX solo Mac, mente con il riconoscimento portabile, script di pacchetto e controllo di portabilità) |

## 3. Le fasi

| Fase | Cosa | "Fatta" quando… |
|---|---|---|
| **F1** La plancia viva | postazioni vere · equipaggio agente con iniziativa · router con la stanza e i canali · voce veloce e pulita · schermo principale, tavolo, datapad integrati e comandati da ops · plancia curata · immagine nitida | in mezz'ora di battaglia vedo sempre l'azione, l'equipaggio pilota la nave con me e senza di me, non si perde una parola, la plancia è bella |
| **F2** La guerra grande | danni fisici · gerarchie (flotta → gruppo → nave; stormo → squadriglia → caccia) · menti di ammiragli, comandanti e alleati che parlano fra loro e con noi · scala (decine di capitali, centinaia di caccia) · bellezza (armi, motori, scudi, esplosioni, navi che si spezzano) · regista v2 senza atti | una battaglia di flotta dura 30–60 minuti ad alta intensità, la vedo tutta, le mosse contano, la campagna dura giorni |
| **F3** Persone vere | MetaHuman per tutti (anche marinai, fanti e il Capitano) · animazioni vere · labiale · cervelli di codice con memoria per i PNG, un modello quando ci parli | nessun manichino in vista; chi incontro fa qualcosa e mi risponde |
| **F4** La nave intera e la distruzione | l'Aquila percorribile da una sola pianta · la vita di bordo (VITA): persone che fanno lavori veri, turni, mense, laboratori · squarci, campi di contenimento, paratie, incendi, decompressione, squadre di riparazione visibili, morti vere · mappa olografica della nave e delle navi scansionate · **F4.3: la pianta di una nave vera** (programma ragionato, labirinto di corridoi di servizio e tubi di Jefferies, turboascensori e navetta che si muovono davvero) · **FLOTTA-VIVA**: le altre navi con la loro pianta, il loro equipaggio e lo stesso modello dei danni, simulate senza grafica | cammino durante la battaglia e trovo i danni veri dove sono avvenuti; posso morire; prendo un ascensore vero per qualsiasi ponte; un colpo su una nave nemica uccide gente vera e spegne sistemi veri |
| **F5** Abbordaggi e prima persona | navette d'assalto nostre e nemiche · fanti con IA di squadra · combattimento in prima persona anche del Capitano · ordini alle formazioni d'attacco e difesa | un abbordaggio ricevuto è una battaglia vera nei corridoi |
| **F6** Teletrasporto | sala, operatori, comandi; limiti alla Star Trek (portata, scudi, interferenze); per chiunque; animazioni e persone che ragionano sul contesto | trasporto persone e cose con effetti e regole credibili |
| **F7** Il pianeta (demo) | discesa coerente col resto; prova per il futuro universo di pianeti veri | la discesa è bella e senza stacchi evidenti |
| **F8** Rete e Windows | i primi passi di [MULTIGIOCATORE.md](MULTIGIOCATORE.md), il build per Windows | due Capitani nello stesso sistema; l'app gira su Windows |

Ordine: **F1 → F2** sono la linea principale. F4 procede in parallelo (NAVE, poi VITA, poi DISTRUZIONE). F3 riparte
appena arriva l'autorizzazione Epic. F5 viene dopo F4.2, F6 dopo F4.1. F7 quando conviene. F8 si prepara sempre
(architettura) e si fa alla fine della fetta.

## 4. Decisioni tecniche

### 4.1 Menti e modelli
- **Tetto di costo: DeepSeek V4.1 Flash.** Per ogni ruolo il modello più piccolo e veloce che mantiene la qualità,
  misurato sui nostri banchi. **Mai la stessa richiesta a due provider.** Obiettivo: ≤ 1 $ per ora di battaglia.
- **Equipaggio di plancia**: un agente per turno che parla come l'ufficiale di competenza e agisce dalle console.
  Vede la somma delle console della plancia e sente la stanza. Si valuterà di dare a ogni ufficiale la sua console come
  strumento da interrogare (percezione ancora più vera) quando la latenza lo permette.
  La collaborazione fra ufficiali avviene nello stesso turno e nei turni di iniziativa (la «guardia»).
- **Router**: nella stanza tutti sentono tutto. Su un canale aperto, cosa esce lo decide l'ufficiale alle comunicazioni
  (un modello veloce: 260 ms mediani, 93–95 % sui 734 casi annotati, 100 % in tedesco, inglese, spagnolo e francese).
- **Nemici e alleati**: un comandante con mente per ogni nave capitale che conta. Un ammiraglio per parte sceglie fra gli
  ordini di gruppo di GUERRA (attacca, inchioda, aggira, schermo, ritirata, rinforzi, tieni, trattativa). Il codice
  guida navi e caccia; le menti decidono ogni 60–120 s o sugli eventi forti. Gli alleati parlano fra loro e con noi:
  pochi messaggi, brevi, utili.
- **Regista v2**: invisibile. Legge tensione, stanchezza del giocatore ed equilibrio, e crea situazioni, rinforzi da
  entrambe le parti, trattative ed eventi dello spazio. Mai atti fissi, mai numeri truccati.
- **PNG secondari** (VITA): cervelli di codice con memoria e mestieri veri; un modello piccolo quando qualcuno ci parla.

### 4.2 Voce
Pronta e provata:
- riconoscimento sul Neural Engine (≈0,2 s dal rilascio del tasto);
- sintesi ×1,12 a volume uniforme;
- un oratore alla volta, il Capitano sempre per primo;
- sottotitoli che durano quanto serve a leggerli;
- radio vs voce nella stanza con isteresi e muri.

**Fatto il 1/10, per il principio §1**: le battute rimaste in coda troppo a lungo, o interrotte a metà, le ripensa chi le
doveva dire, con lo stato di adesso, appena prima di dirle: le dice aggiornate, le cambia o le lascia cadere (aggancio
`rethink`). Spariti lo scarto per età, il riassunto «prima e ultima frase» e il taglio alla prima frase quando c'è coda.
Resta meccanica solo la priorità del Capitano.

### 4.3 Simulazione e guerra
- Passo fisso, doppia precisione, la nave del giocatore come riferimento.
- Danni fisici per tipo (cinetico, energia, esplosivo), faccia e sezione.
- Gerarchie e intelligenza di gruppo nel codice, decisioni nelle menti.
- Scenari dai dati (`data/war/*.json`).
- Livelli di dettaglio nella simulazione, istanze per caccia e proiettili.
- Si misura col banco senza grafica (`tools/war.py`).

### 4.4 La nave e la distruzione
Un'unica pianta dati dell'Aquila (il DNA: compartimenti, porte, condotte, sistemi, grafo dei percorsi). Da lì nascono:
- la geometria (kit di Blender);
- la simulazione dei danni per compartimento (pressione, fuoco, fumo, squarci, energia);
- i percorsi dell'equipaggio e delle squadre (`UAstraShipPlan`: 0,1 ms a percorso);
- la mappa olografica.

Le navi esterne hanno pezzi di sezione per spezzarsi.

### 4.5 Grafica e prestazioni
Obiettivo: **60 fps con il 3D ad almeno il 70 %** sull'Air, nessuna sgranatura.

Misure del 30/9 a macchina scarica:
- ~27 ms di GPU al 100 %, ~17,5 ms al 70 %;
- un costo fisso di ~9–10 ms più ~14 ms per milione di pixel.

Già fatto:
- riflessi Lumen solo sulle superfici lucide;
- filtro delle ombre del sole più leggero;
- la risoluzione dinamica sale al ~50–55 %.

Prossimi passi:
- raggi delle luci grandi della plancia (~1 ms);
- materiali della plancia più leggeri (~1–1,5 ms);
- un upscaler MetalFX nostro al posto di TSR (da studiare: più qualità a parità di costo);
- la modalità 30 fps del menu per chi vuole l'immagine piena.

Qualità: asset di terzi (Fab, Quixel, ambientCG) fusi con i nostri, materiali a strati; riferimento EVE Online per navi e
spazio, Star Trek e Star Wars per armi e interni.

### 4.6 Persone
MetaHuman per tutti (serve la tua autorizzazione Epic di un minuto), animazioni vere (motion matching), labiale
dall'audio, tre livelli di dettaglio secondo la distanza.

### 4.7 Portabilità
Codice di gioco multipiattaforma. Ciò che è solo Mac (Parakeet sul Neural Engine, MetalFX) ha un'alternativa portabile
nello stesso contratto: Parakeet ONNX su CPU, TSR.

## 5. Moduli e agenti di supporto

Fino a tre agenti (Sonnet 5.5, sforzo massimo) su moduli indipendenti, ognuno nel suo worktree. Il lead dirige,
integra, prova nel gioco vero, e li chiude quando il modulo è perfetto. Brief in `docs/brief/`.

| Fatti e uniti | Adesso (5/10) | Poi (appena si libera un posto) |
|---|---|---|
| MENTE-EQUIPAGGIO, ARTE-PLANCIA, VOCE, NAVE, NAVE-2, ARTE-NAVI, GUERRA, VITA, METALFX, VFX, MENTE-GUERRA, SCALA, DISTRUZIONE, VOLO, NAVE-3, ASCENSORI, ABBORDAGGI (F5.1, F5.2, ABBORDAGGI-3: ponti vestiti, esercitazione, libri), TELETRASPORTO, ARTE-PLANCIA-2, CAMPAGNA, ARTE-INTERNI e ARTE-INTERNI-2, FLOTTA-VIVA, SPAZIO-VIVO e SPAZIO-VIVO-2, WINDOWS | **VOCI-3** (chiarezza e controllo: reti, palco, registro silenzioso, dottrina) · **BATTAGLIA-3** (scontri continui e lunghi, timone e tiro bravi, nemico che si batte) · **ABBORDAGGI-4** (ritmo, il Capitano con i marine, la fanteria comandata, la prima persona); il lead: **LUOGHI** e le prove | ARTE-SCAFI (le navi al livello di EVE: materiali, dettagli, luci) · PRESTAZIONI-GPU · VFX-2 (le armi alle nuove distanze, dopo BATTAGLIA-3) · ARTE-INTERNI-3 (sale comando, officine, stive, le stanze ripetute) |

Il lead, intanto: l'integrazione e le prove di ogni modulo; **partite intere giocate da Capitano** (plancia, battaglia, nave) e la
rifinitura di ciò che trova; le prestazioni; la plancia al dettaglio.

## 6. Rischi e contromisure

| Rischio | Contromisura |
|---|---|
| Portata enorme | fasi con criteri di "fatto", moduli indipendenti, tre agenti in parallelo, prove continue col banco |
| Costi dei modelli con tante menti | cervelli di codice per il continuo, modelli piccoli dove bastano, budget per ruolo e per ora, misure |
| Intelligenza fragile (regole che si rompono) | il principio §1: prompt, contesto e strumenti, niente filtri; banchi sui fatti, prove giocate |
| Prestazioni sull'Air senza ventola | misure A/B alternate, costi fissi ridotti, upscaler migliore, modalità 30 fps |
| Qualità grafica sul Mac | asset di qualità rielaborati, materiali stratificati, luce furba |
| Agenti in parallelo sulla stessa macchina | worktree separati, file assegnati, contratti scritti, prove nel gioco solo dal lead |
| Umani realistici | MetaHuman (autorizzazione Epic); nel frattempo tutto il resto va avanti |
| Limiti d'uso dei modelli degli agenti | commit piccoli e frequenti: un'interruzione non perde lavoro; il lead riprende i moduli se serve |

## 7. Come lavoriamo

Il lead dirige l'architettura, integra e prova tutto nel gioco vero con il banco di prova (`tools/play.py`). Gli agenti
di supporto sviluppano moduli indipendenti in worktree separati e iterano sui difetti trovati dal lead finché il modulo è
perfetto. Dettagli in [ARCHITETTURA.md §6](ARCHITETTURA.md). Lo stato di tutto in [STATO.md](STATO.md).
