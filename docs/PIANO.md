# ASTRA — Piano v0.4

*30 settembre 2026, sera · sostituisce la v0.3. Scritto dopo la prima giornata di lavoro con gli agenti di supporto: la voce
integrata e provata nel gioco, le misure pulite delle prestazioni, e il principio delle intelligenze ribadito dal Capitano.
Architettura, moduli e contratti: [ARCHITETTURA.md](ARCHITETTURA.md). Stato: [STATO.md](STATO.md).*

> **Lingua del gioco: inglese** (nomi, lore, scritte, interfacce). Gli NPC parlano la lingua del giocatore.

---

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

## 2. Dove siamo (1/10)

| Area | Stato |
|---|---|
| **Controlli in prima persona**, banco di prova da terminale | fatto |
| **Plancia viva** (F1) | quasi fatta. Pronti: postazioni vere, schermo principale intelligente, tavolo olografico leggibile dalla poltrona, datapad, finestrone in realtà aumentata, HUD del caccia, equipaggio agente, plancia v3, menu SETTINGS. La voce v2 è provata dal vivo: parla anche chi è fuori plancia, sottotitoli giusti, il Capitano sempre per primo. Il palco della voce ripensa invece di scartare. Mancano: la plancia curata nel minimo dettaglio, le persone vere (F3), l'immagine nitida (§4.5) |
| **Guerra grande** (F2) | in corso (GUERRA). Fatto F2.1: danni fisici, scudi a sei settori, corazza e struttura per sezione, sottosistemi, relitti. F2.2 a metà: gruppi di battaglia, squadriglie di caccia. Da fare: menti di ammiragli e comandanti, scala, bellezza, regista v2 |
| **Persone vere** (F3) | ferma: serve la tua autorizzazione Epic per i MetaHuman (RICHIESTE) |
| **La nave intera** (F4.1) | NAVE unita: il DNA dell'Aquila (12 ponti, 2251 compartimenti, 1034 porte, grafo di 4450 luoghi), il kit di 96 modelli; il Ponte 4 (la Spina, la mensa, gli alloggi) e il Ponte 6 (Medical) sono nel livello e si camminano a 57 fps. Il gioco legge la pianta e trova i percorsi (`UAstraShipPlan`, 0,1 ms). In corso: VITA (la vita di bordo); da fare: gli altri ponti |
| **Navi v3** | ARTE-NAVI unita: esterni alla qualità di EVE Online, pezzi di sezione per la rottura, decalcomanie di danno; import nell'editor e prova nel gioco in corso |
| Distruzione (F4.2) · Abbordaggi e prima persona (F5) · Teletrasporto (F6) · Pianeta (F7) · Rete e Windows (F8) | da fare |

## 3. Le fasi

| Fase | Cosa | "Fatta" quando… |
|---|---|---|
| **F1** La plancia viva | postazioni vere · equipaggio agente con iniziativa · router con la stanza e i canali · voce veloce e pulita · schermo principale, tavolo, datapad integrati e comandati da ops · plancia curata · immagine nitida | in mezz'ora di battaglia vedo sempre l'azione, l'equipaggio pilota la nave con me e senza di me, non si perde una parola, la plancia è bella |
| **F2** La guerra grande | danni fisici · gerarchie (flotta → gruppo → nave; stormo → squadriglia → caccia) · menti di ammiragli, comandanti e alleati che parlano fra loro e con noi · scala (decine di capitali, centinaia di caccia) · bellezza (armi, motori, scudi, esplosioni, navi che si spezzano) · regista v2 senza atti | una battaglia di flotta dura 30–60 minuti ad alta intensità, la vedo tutta, le mosse contano, la campagna dura giorni |
| **F3** Persone vere | MetaHuman per tutti (anche marinai, fanti e il Capitano) · animazioni vere · labiale · cervelli di codice con memoria per i PNG, un modello quando ci parli | nessun manichino in vista; chi incontro fa qualcosa e mi risponde |
| **F4** La nave intera e la distruzione | l'Aquila percorribile da una sola pianta · la vita di bordo (VITA): persone che fanno lavori veri, turni, mense, laboratori · squarci, campi di contenimento, paratie, incendi, decompressione, squadre di riparazione visibili, morti vere · mappa olografica della nave e delle navi scansionate | cammino durante la battaglia e trovo i danni veri dove sono avvenuti; posso morire |
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
integra, prova nel gioco vero, e li chiude quando il modulo è perfetto.

| Adesso | Poi (appena si libera un posto) |
|---|---|
| **GUERRA** (F2.1–F2.2: danni, gruppi, squadriglie; contratto per le menti) | **MENTE-GUERRA** (ammiragli, comandanti, alleati che parlano, regista v2) · **SCALA** (F2.3) |
| **VITA** (la vita di bordo sul grafo dei percorsi; dopo NAVE, unita il 30/9) | **DISTRUZIONE** (F4.2) · **NAVE-2** (gli altri ponti) |
| **METALFX** (upscaler; dopo ARTE-NAVI, unita il 1/10) | **VFX** (armi, motori, scudi, esplosioni, rotture: F2.4) |

Il lead, intanto:
- l'integrazione di ogni modulo (le navi v3 nel gioco, poi GUERRA e VITA);
- le prove nel gioco;
- le prestazioni;
- la plancia al dettaglio;
- il collegamento delle menti di guerra al contratto di GUERRA.

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
