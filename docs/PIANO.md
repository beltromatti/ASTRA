# ASTRA — Piano v0.3

*30 settembre 2026 · sostituisce la v0.2 · scritto dopo la prima partita vera del Capitano con l'app e il suo "flusso di
coscienza" sulle priorità. Architettura, moduli e contratti: [ARCHITETTURA.md](ARCHITETTURA.md). Stato: [STATO.md](STATO.md).*

> **Lingua del gioco: inglese** (nomi, lore, scritte, interfacce). Gli NPC parlano la lingua del giocatore.

---

## 0. L'obiettivo di questa fetta

**Una guerra stellare in cui sei il Capitano di una nave viva: grande, intelligente, cinematica e spietata, da giocare per
settimane senza mai annoiarsi.** Se questa fetta è perfetta, dimostra che ASTRA può diventare un universo intero,
multigiocatore, abitato da giocatori e da persone intelligenti: la stessa architettura crescerà fino a lì.

Il metro di giudizio è uno solo: **il Capitano ci gioca un mese di fila e non si stanca mai.** Ogni minuto ha qualcosa da
decidere; ogni decisione pesa; la bravura cambia l'esito; ogni volta la guerra è diversa; e ciò che vedi è bello e vero.

## 1. Cosa ci ha insegnato la prima partita (29 settembre)

- **Il cervello è avanti, il corpo è indietro.** Memoria, regista, trattative, stile di comando imparato: funzionano e
  stupiscono. Ma l'aspetto è da prototipo, le persone sono manichini, la plancia sembra un ufficio.
- **Il Capitano non poteva camminare né guardarsi intorno** (gli asset di input del template non erano mai stati copiati):
  corretto il 30/9, con controlli veri da prima persona.
- **La battaglia non si vedeva.** Le navi sono puntini a 5–15 km, il timone non tiene l'azione davanti, lo schermo
  principale è una tabella. Le navi nemiche morivano senza essere mai state viste.
- **L'equipaggio esegue ma non gioca.** Aspetta gli ordini, non tiene un ordine nel tempo, parla troppo, a volte non parla
  affatto (sottotitoli senza voce), le parole del Capitano finivano al nemico con il canale aperto.
- **La guerra è troppo piccola e troppo veloce**: poche navi, finita in pochi minuti, senza strategia di gruppo.
- **L'immagine è sgranata**: per stare nei 60 fps il 3D veniva disegnato al 50% di 1710×1107 e ingrandito quattro volte.

## 2. Pilastri

1. **Il Capitano comanda persone vere.** Ogni postazione è un agente attivo con una console vera: pilota la nave nel suo
   ambito ogni secondo, tiene gli ordini nel tempo, prende iniziative entro la delega, collabora con gli altri.
2. **Vedi la guerra.** Il timone tiene l'azione davanti alla prua, lo schermo principale la segue e la ingrandisce, il
   tavolo olografico te la mette davanti in 3D. Niente morti invisibili.
3. **Due eserciti che pensano.** Gerarchie, sottosquadre, tattiche di gruppo, ritirate e offensive vere, da entrambe le
   parti; sopra, un regista invisibile che crea la storia senza favorire nessuno.
4. **La nave è un luogo vero.** Tutta percorribile, piena di gente che fa cose vere; si rompe davvero, dentro e fuori.
5. **Realismo fisico leggibile.** Danni dalla fisica (energia dei colpi, corazza, scudi), distanze e masse realistiche,
   tempi di manovra da nave capitale; lo zoom dello schermo principale rende visibile ciò che è lontano.
6. **Scacchi lampo che durano ore.** Tante mosse rapide e ben calibrate, tante leve (manovra, fuoco, energia, sensori,
   caccia, flotta, trattativa, abbordaggio), l'esito che dipende dalla bravura, la campagna che dura giorni.
7. **Bellezza efficiente.** Fotorealismo "furbo" alla EVE Online sul MacBook Air M4, senza sgranature; codice portabile
   su Windows, ottimizzato a fondo sul Mac.
8. **Intelligenza ovunque, costo sotto controllo.** Cervelli di codice per il lavoro continuo, modelli linguistici per
   decidere e parlare; DeepSeek V4.1 Flash come tetto di costo, modelli più piccoli dove bastano.

## 3. Le fasi

| Fase | Cosa | "Fatta" quando… |
|---|---|---|
| **F0** Fondamenta per lavorare in parallelo | controlli in prima persona, banco di prova da terminale, architettura a moduli, agenti di supporto | ✓ controlli e banco (30/9); in corso: documenti e primi agenti |
| **F1** La plancia viva | postazioni vere con modalità continue · equipaggio agente (iniziativa, ordini continui, collaborazione, frasi brevi) · router con l'acustica della stanza e la radio · voce veloce e pulita, turni di parola, priorità al Capitano · schermo principale con telecamera, zoom, sovrimpressione tattica e regia · tavolo olografico davanti alla poltrona · datapad comandabile · plancia v3 futuristica curata al dettaglio · immagine nitida a 60 fps | giocando mezz'ora in plancia vedo sempre l'azione, l'equipaggio pilota la nave con me e senza di me, non si perde una parola, e la plancia è bella |
| **F2** La guerra grande | simulazione in scala (decine di navi capitali, centinaia di caccia e droni, migliaia di colpi) · danni fisici, corazze, scudi · navi capitali lente e maestose, caccia agili con piloti che evitano le collisioni · armi e motori belli (alla Star Wars e Star Trek) · navi che si spezzano · più oggetti nello spazio · eserciti con gerarchie e sottosquadre (menti per ammiragli e comandanti, codice per navi e caccia) · regista v2 senza atti prefissati · alleati che parlano fra loro e con noi | una battaglia di flotta dura 30–60 minuti ad alta intensità, la vedo tutta, le mosse contano, e la campagna può durare giorni |
| **F3** Persone vere | umani realistici (MetaHuman) per tutti, anche marinai e fanti · animazioni vere, labiale · cervelli di codice per i PNG con memoria, modelli piccoli dove servono, LLM quando ci parli | nessun manichino in vista; chi incontro fa qualcosa e mi risponde |
| **F4** La nave intera e la distruzione | l'Aquila percorribile per davvero (ponti, corridoi, cunicoli, laboratori, cucine, stive) generata da un'unica pianta · equipaggio ovunque · squarci, campi di contenimento, paratie, incendi, decompressione, squadre di riparazione visibili, morti vere · mappa olografica della nave (e delle navi scansionate) | cammino durante la battaglia e trovo i danni veri dove sono avvenuti; posso morire |
| **F5** Abbordaggi e prima persona | navette d'assalto (nostre e nemiche), fanti con IA di squadra, combattimento in prima persona anche del Capitano, ordini alle formazioni d'attacco e difesa | un abbordaggio ricevuto è una battaglia vera nei corridoi |
| **F6** Teletrasporto | sala teletrasporto, operatori, comandi, limiti fisici alla Star Trek (portata, scudi, interferenze), per chiunque | trasporto persone e cose con effetti e regole credibili |
| **F7** Il pianeta (demo) | discesa coerente col resto; resta una prova per il futuro universo di pianeti a grandezza reale | la discesa è bella e senza stacchi evidenti |
| **F8** Rete e Windows | i primi passi di [MULTIGIOCATORE.md](MULTIGIOCATORE.md), il build per Windows | due Capitani nello stesso sistema; l'app gira su Windows |

Ordine: **F1 → F2** sono la linea principale (il lead); F3 e F4 procedono in parallelo con gli agenti di supporto
(arte, generatori, menti) appena i contratti lo permettono; F5 dopo F4; F6 dopo F4; F7 quando conviene; F8 si prepara
sempre (architettura) e si fa alla fine della fetta.

## 4. Decisioni tecniche

### 4.1 Menti e modelli
- **Tetto di costo: DeepSeek V4.1 Flash** (0,30 / 1,20 $ per milione di token). Per ogni ruolo scegliamo il modello più
  piccolo e veloce che mantiene la qualità necessaria, misurandolo sul nostro banco (router e chiacchiere dei piloti con
  modelli piccoli; ufficiali, comandanti e regista con Flash). **Mai la stessa richiesta a due provider**: si paga due volte.
- **Cervelli di codice per il continuo** (esecutori delle postazioni, IA delle navi e dei caccia, IA dei PNG); le menti
  entrano quando c'è da decidere o da parlare. Obiettivo: **≤ 1 $ per ora di battaglia** anche con decine di menti.
- **Router con il contesto della stanza**: chi sente davvero (distanza, pareti, radio), a chi guarda il Capitano, canali
  aperti. Sulla plancia tutti sentono il Capitano, come nella realtà; il nemico sente solo ciò che passa sul canale.
- Il gioco non deve funzionare offline: i modelli locali servono dove bastano (riconoscimento, sintesi, classificatori),
  non come ripiego.

### 4.2 Voce
Riconoscimento sul chip neurale (obiettivo ≤ 0,4 s dal rilascio del tasto), sintesi veloce e con volume costante, un
solo oratore alla volta in plancia, il Capitano sempre per primo, nessuna battuta persa in silenzio, sottotitoli che
restano quanto serve a leggerli. Modulo VOCE: [protocollo_voce.md](protocollo_voce.md).

### 4.3 Simulazione
Passo fisso, doppia precisione, la nave del giocatore come riferimento; dati compatti per scalare (navi, caccia,
proiettili in array, disegnati con istanze e particelle). Danni fisici: energia cinetica e termica del colpo contro
corazza per sezione e scudi (forti contro l'energia, meno contro i proiettili pesanti, consumano energia e scaldano).
Livelli di dettaglio anche nella simulazione (ciò che è lontano si aggiorna meno spesso).

### 4.4 La guerra
Mappa strategica viva (flotte che si muovono fra i sistemi, rifornimenti, obiettivi); battaglie di teatro con eserciti a
gerarchia: ammiraglio (mente) → comandanti di gruppo (menti) → navi (codice) → caccia (codice). Il regista è invisibile:
crea situazioni, ritmo e trama dai fatti, senza favorire nessuno e senza atti prefissati.

### 4.5 Grafica e prestazioni
Obiettivo: **60 fps con il 3D ad almeno il 70% di 1710×1107** sull'Air (niente sgranature). Strada: trovare e togliere le
inefficienze vere (misure per passaggio), illuminazione globale più furba negli interni, un upscaler migliore (MetalFX su
Mac, con TSR come alternativa portabile), materiali e asset di qualità (nostri fusi con asset gratuiti di terzi), profili
per macchine più potenti e per Windows.

### 4.6 Persone
MetaHuman per tutti i personaggi (serve una tua autorizzazione Epic di un minuto: vedi RICHIESTE), animazioni vere
(Game Animation Sample, motion matching), labiale dall'audio; tre livelli di dettaglio secondo la distanza.

### 4.7 La nave intera e la distruzione
Un'unica pianta dati dell'Aquila (il "DNA della nave": compartimenti, porte, condotte, sistemi) da cui nascono la
geometria, la simulazione dei danni, i percorsi dell'equipaggio e la mappa olografica. Stati per compartimento (pressione,
fuoco, fumo, squarci, energia) con effetti visibili; squadre di riparazione che camminano e lavorano davvero.

## 5. Rischi e contromisure

| Rischio | Contromisura |
|---|---|
| Portata enorme | fasi con criteri di "fatto", moduli indipendenti, agenti in parallelo, prove continue col banco |
| Costi dei modelli con tante menti | cervelli di codice per il continuo, modelli piccoli dove bastano, budget per ruolo e per ora |
| Prestazioni con battaglie grandi | istanze, particelle GPU, livelli di dettaglio nella simulazione e nella grafica, misure automatiche |
| Qualità grafica sul Mac | asset di qualità rielaborati, materiali stratificati, upscaler migliore, illuminazione furba |
| Agenti in parallelo sulla stessa macchina | worktree separati, file assegnati, contratti scritti, prove nel gioco solo dal lead |
| Umani realistici | MetaHuman (autorizzazione Epic); nel frattempo tutto il resto va avanti |
| Rotture da aggiornamenti | Xcode e motore fissati, commit frequenti |

## 6. Come lavoriamo

Il lead dirige l'architettura, integra e prova tutto nel gioco vero con il banco di prova; fino a tre agenti di supporto
(Sonnet, sforzo massimo) sviluppano moduli indipendenti in worktree separati e iterano sui difetti trovati dal lead
finché il modulo è perfetto. Dettagli in [ARCHITETTURA.md §6](ARCHITETTURA.md). Lo stato di tutto in [STATO.md](STATO.md).
