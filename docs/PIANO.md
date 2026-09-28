# ASTRA — Piano tecnico v0.2

*27 settembre 2026 · nome in codice: ASTRA · basato su 14 ricerche (indice in [ricerca/00-INDICE.md](ricerca/00-INDICE.md)) e sull'analisi diretta del tuo Mac e di Unreal 5.8.3.*

**Novità rispetto alla v0.1**
- Budget zero per tutto ciò che non è AI.
- Ogni asset rifatto su misura da me.
- Il gioco parla la lingua del giocatore.
- Voce e labiale locali, fatti in casa.
- Autonomia totale nel reperire gli asset.
- Efficienza "alla EVE" come vincolo di progetto.
- DeepSeek e OpenRouter come fornitori AI.

---

## 0. In una frase

Un simulatore in prima persona in cui sei il capitano di una nave capitale viva. Ogni sistema è davvero simulato. L'equipaggio pensa con modelli AI, parla la tua lingua e agisce solo attraverso i veri comandi della nave. Un Regista AI dà alla guerra un inizio, un'escalation, un climax e un finale sempre diversi. Il tutto gira in modo fluido su un MacBook Air, dentro un universo generato da un unico seed e pronto per il multiplayer.

---

## 1. Pilastri

**Di design** (dalla ricerca sui simulatori di plancia, report 14)
1. **Comandi attraverso le persone.** L'equipaggio è l'interfaccia: esegue, riferisce, sbaglia e ricorda.
2. **La nave è un luogo.** Ogni sistema ha una posizione fisica, i danni sono spaziali e spostarsi ha conseguenze.
3. **Realismo leggibile.** Inerzia, tempi di volo dei proiettili, calore e firme dei sensori, tarati sulle finestre di decisione di un capitano umano (5–60 secondi).
4. **Ogni postazione, non tutte insieme.** Puoi prendere timone, armi o un caccia, ma la nave nota che hai lasciato la poltrona: comanda il Primo Ufficiale.
5. **Una guerra che ricorda.** Archi narrativi diretti, perdite permanenti, finali da cui ci si può rialzare.

**Tecnici**

6. **La simulazione dice la verità, le AI sono le persone.**
7. **Leggerezza.** Il tuo MacBook Air è la macchina di riferimento: 60 fps nello spazio e almeno 45 negli interni, a caldo.
8. **Budget zero, tutto su misura.** Le risorse gratuite sono materia prima; lo stile ASTRA lo costruisco io.
9. **Qualsiasi lingua.** Il gioco ti risponde nella lingua in cui parli.
10. **Autonomia.** Dopo la preparazione iniziale, reperisco, creo, provo e miglioro da solo.

---

## 2. Cosa costruiamo nell'alpha

| La tua idea | Come la realizziamo |
|---|---|
| Entrare nella nave camminando, senza caricamenti | La nave capitale è un unico "scafo cinematico": ci cammini mentre vola, vira e viene colpita (§4.3). All'inizio è percorribile il **nucleo vivo** (plancia, spina dorsale con ascensori, sala macchine, hangar, infermeria, alloggi); le altre sezioni sono simulate e si aprono man mano |
| Plancia stile Star Trek con equipaggio che fa davvero funzionare la nave | Gli ufficiali AI usano gli **stessi comandi** che usi tu. Ordine → ripetizione → "in esecuzione" → "eseguito" oppure "impossibile, perché…" (§4.5) |
| Pilotare in prima persona guardando la plancia | Niente HUD: finestroni, tavolo tattico olografico, console con schermi reali, dispositivo da polso quando sei lontano dalla plancia |
| Dare ordini invece di fare tutto | Voce in qualsiasi lingua, oppure scrittura o menu radiale: la voce non è mai obbligatoria. Con gli **ordini permanenti** e la delega per reparto (manuale / consiglia / automatico) l'equipaggio prende iniziativa |
| Armi e scudi diretti o indiretti | "I computer mirano, il capitano sceglie le priorità": imposti dottrina, bersagli e settori degli scudi, oppure ti siedi alla postazione |
| Parlare con navi amiche e nemiche | Canali radio con capitani AI che hanno dottrina, paura e orgoglio: negoziare, bluffare, intimare la resa, chiedere rinforzi. Tutto passa dal **traduttore universale** |
| Danni granulari | Grafo dei compartimenti con pressione, ossigeno, fuoco, fumo, temperatura e radiazioni. I tempi di decompressione dipendono dalla dimensione dello squarcio. Porte stagne con condizioni di sicurezza da marina militare, campi di contenimento, squadre di riparazione a piedi, triage in infermeria |
| Hangar, caccia e droni; salire su un caccia | Tubi di lancio separati dal ponte di recupero, tempi di riarmo, missioni di squadriglia. Tu in cabina di pilotaggio mentre il Primo Ufficiale comanda la nave |
| Battaglia enorme, sensata, con inizio e fine | Un sistema stellare con pianeti, stazioni, cantieri, portale di salto e linee di rifornimento. Ammiragli AI e un Regista con atti, ritmo e finale calcolato dallo stato reale |
| Se perdi | Abbandono nave, poi tre esiti possibili: soccorso (con commissione d'inchiesta che rivede il giornale di bordo), cattura (prigionia) o deriva nella capsula. La guerra continua su un ramo in salita. C'è anche una modalità "ironman" |
| Universo infinito e persistente | Seed unico, coordinate gerarchiche e salvataggio delle sole differenze (§4.2) |
| Atterrare su un pianeta vedendo tutto | Pianeti sferici procedurali con atmosfera e rientro. È la parte più rischiosa, per questo è la tappa M7 |

**Niente codice generato dall'AI mentre giochi**: le AI agiscono solo tramite strumenti e generatori.

---

## 3. Verità scomode (aggiornate)

1. **Nessun modello AI online risponde all'istante.** Il minimo è circa 0,4 s alla prima parola; DeepSeek diretto circa 1,1 s. L'immediatezza la **progettiamo**:
   - un classificatore d'intenti locale (millisecondi);
   - una conferma vocale pre-generata;
   - l'esecuzione immediata dell'ordine;
   - la risposta dettagliata dell'AI subito dopo, in streaming.
2. **Budget zero significa più lavoro mio, non meno qualità.** Per superfici rigide, navi, interni, spazio e audio, le fonti gratuite più il lavoro su misura arrivano al livello dei pacchetti a pagamento, spesso oltre, perché tutto è coerente. Costa tempo di iterazione, e quel tempo lo metto io.
3. **Il MacBook Air resta il limite.** Il fotorealismo "furbo" alla EVE e Everspace 2 ci fa girare fluidi. Il massimo assoluto (ray tracing hardware, luci complesse) arriverà solo su macchine più potenti, con profili grafici già pronti.
4. **Voce locale di prima classe in 6 lingue**: italiano, inglese, francese, tedesco, spagnolo, portoghese. Le altre lingue sono coperte con qualità inferiore o dal piano gratuito di ElevenLabs. Il riconoscimento vocale copre 25 lingue europee in locale e 99 con Whisper.
5. **Un pianeta senza caricamenti è tecnologia nostra.** Prima un prototipo isolato, poi l'integrazione.
6. **Le pagine web di Fab e Mixamo non hanno API ufficiali.** Le uso come farebbe una persona, a ritmo umano, senza mai aggirare le protezioni.
7. **Il rischio vero è la portata.** Starship Simulator, con 200 stanze, ha rimandato l'uscita a data da destinarsi. Noi lavoriamo per **fette verticali complete**, allargate poco alla volta.

---

## 4. Architettura

### 4.1 Tre fonti di verità e il "DNA della nave"
1. **Universo** (seed): dove sono le cose e cosa sono.
2. **Simulazione** (Unreal, autoritativa): cosa succede.
3. **Menti** (servizio AI lato server): cosa decidono le persone.

Il **DNA della nave** è un unico file di dati: grafo dei compartimenti, sistemi, porte, condotte e prese. Da lì nascono la geometria dei moduli 3D, la simulazione di danni e atmosfera, i percorsi delle squadre, lo schema olografico sul tavolo tattico e la conoscenza della nave che hanno le AI. Ciò che vedi, ciò che è simulato e ciò che l'equipaggio sa coincidono sempre.

### 4.2 Universo, coordinate, persistenza
- **Albero di riferimenti:** settore galattico (interi a 64 bit) → sistema → corpo celeste (sistema rotante) → nave → stanza.
- **Bolle di simulazione** entro ±1 milione di km. I corpi lontani sono impostori in scala. In crociera l'universo si muove attorno alla nave.
- **Generatore versionato:** la stessa posizione produce sempre lo stesso contenuto, e le zone già visitate vengono congelate.
- **Persistenza** = base generata + registro delle differenze. Per ora SQLite, poi un database server.

### 4.3 La nave viva (simulazione)
- **Energia e calore.** Reattore → linee → condensatori. Ogni megawatt diventa calore, che si smaltisce con radiatori (vulnerabili e visibili ai sensori infrarossi) o con accumulatori termici limitati (per correre "silenziosi" o sparare a raffiche). L'ordine "battle short" scavalca le protezioni e scambia sicurezza per potenza.
  - Quando i railgun si caricano, **le luci calano**: il consumo si vede nella nave.
- **Sensori e guerra elettronica:**
  - firme (calore, scia del motore, emissioni, sezione radar);
  - scala di conoscenza: rilevato → tracciato → classificato → identificato → aggancio di tiro;
  - controllo delle emissioni (silenzio / ristretto / pieno);
  - disturbo che perde efficacia da vicino;
  - rilevamento passivo per soli rilevamenti angolari fino all'incrocio di due sensori;
  - esche che svaniscono;
  - pianeti e stazioni che coprono la linea di vista.
- **Difesa a strati:** caccia e droni → intercettori → difesa di punto → scudi per settore (forti contro l'energia, più deboli contro i proiettili pesanti, scaldano) → corazza per sezione → compartimenti interni.
- **Manovra.** Inerzia reale gestita da un computer di volo, con ordini di timone da marina ("vira a 045 punto 10", "capovolgi e frena", "presenta il fianco sinistro"). **I compensatori inerziali hanno un limite**: superarlo ferisce chi cammina e fa volare gli oggetti. Il timone è così legato ai danni.
- **Controllo danni:**
  - compartimenti con volume, pressione, ossigeno, temperatura, fumo, fuoco, radiazioni, energia, gravità e occupanti;
  - la costante di tempo della decompressione dipende dall'area dello squarcio: 1 m² dura secondi, 10 cm di lato minuti, 1 cm² ore;
  - fuoco = combustibile + ossigeno + calore: si spegne con le squadre oppure sfiatando la stanza, uccidendo chi è dentro;
  - porte con condizioni di sicurezza da marina: il posto di combattimento sigilla la nave;
  - campi di contenimento con priorità di distacco dei carichi;
  - lavori di riparazione parziali in battaglia; ricambi e bacino di carenaggio per le riparazioni complete;
  - triage START in infermeria;
  - morale e fatica, che cambiano rendimento e tono dell'equipaggio.
- **Camminare dentro la nave in moto:**
  - scafo cinematico mosso dal nostro modello di volo;
  - personaggi "appoggiati" allo scafo con gravità della nave;
  - oggetti sciolti simulati con fisica Chaos nello spazio locale della nave;
  - squarci unici tagliati a runtime nei pannelli dello scafo.

### 4.4 Scala del combattimento "leggibile"
- **Finestre di decisione:**
  - sotto i 5 s agiscono automatismi ed equipaggio (difesa di punto, scarti);
  - **tra 5 e 60 s decide il capitano** (salve, orientamento della corazza, scudi, emissioni);
  - sui minuti si gioca l'operativo (formazione, avvicinamento, squadriglie).
- **Distanze.** Parto da valori realistici compressi di circa 10 volte, perché la battaglia resti *visibile* in prima persona: missili e siluri da decine a centinaia di km, cannoni a rotaia da 2 a 30 km, laser sotto i 10 km, difesa di punto sotto i 2 km. Sono tutti regolabili.
- Il tavolo olografico mostra linee di elevazione, anelli di distanza, ellissi d'incertezza, linee di solo rilevamento angolare ed età del contatto.

### 4.5 Le menti

```
 Tu (voce in qualsiasi lingua / tastiera / menu radiale)
      │
      ▼
 Riconoscimento vocale sul Mac ──► classificatore d'intenti locale (ms)
      │                                   │
      │                                   ├─► conferma vocale pre-generata ("Agli ordini")
      │                                   └─► esecuzione immediata degli ordini sicuri
      ▼
┌──────────────────── GATEWAY AI "astra-mind" (lato server) ─────────────────┐
│ corsie di priorità · scadenze · richieste di riserva · cache dei prompt ·  │
│ budget · fallback · registro di replay · cruscotto costi                   │
└──▲──────────────▲──────────────▲──────────────▲───────────────▲────────────┘
 REGISTA        AMMIRAGLI      CAPITANI       UFFICIALI         EQUIPAGGIO
 (atti, ritmo,  (strategia)    (manovre)      DI PLANCIA        (centinaia,
  eventi)                                     (comandi reali)    a eventi)
   │               │              │              │                 │
┌──▼───────────────▼──────────────▼──────────────▼─────────────────▼─────────┐
│ STRATO DELLE AZIONI: comandi tipizzati · autorità · rifiuti motivati       │
└──────────────────────────────────┬─────────────────────────────────────────┘
┌──────────────────────────────────▼─────────────────────────────────────────┐
│ SIMULAZIONE DETERMINISTICA (Unreal, autoritativa) + STRATO VELOCE          │
│ (StateTree, Smart Objects, Mass) — la nave combatte anche senza AI         │
└──── eventi filtrati per importanza ──► memorie + registro di guerra ───────┘
```

- **Catena di comando a circuito chiuso.** La ripetizione dell'ordine è generata dal comando interpretato, quindi ciò che l'ufficiale dice è esattamente ciò che la simulazione farà. Se il riconoscimento vocale è incerto, l'ufficiale chiede conferma. Ogni ordine compare sul registro dei comandi.
- **Iniziativa:**
  - ordini permanenti (regole d'ingaggio, autonomia della difesa di punto, priorità delle riparazioni);
  - delega per reparto: manuale / consiglia / automatico;
  - raccomandazioni del **Primo Ufficiale** ("Consiglio scudi a prua"), che accetti con "Proceda". Il Primo Ufficiale ti fa anche da istruttore nelle esercitazioni.
- **Nebbia di guerra.** Ogni AI conosce solo ciò che vedono i suoi sensori e ciò che le viene riferito.
- **Regista della guerra**, ispirato a RimWorld e Left 4 Dead:
  - la simulazione calcola tensione, forze, fronti, atto corrente e finali possibili;
  - regole numeriche danno il ritmo;
  - il Regista sceglie eventi da un catalogo, ognuno legato a un filo narrativo;
  - il **registro di guerra** accetta solo aggiunte;
  - gli atti sono Scoppio → Escalation → Climax → Risoluzione.
- **Modalità Game Master per te.** L'interfaccia del Regista la puoi usare anche tu: "Regista, voglio un'imboscata nella fascia di asteroidi".
- **Niente gabbie cablate.** I prompt di persona, dottrina e carattere li scrivo io; i limiti sono solo fisici e di autorità.
- **Ogni ruolo AI ha una dottrina di riserva.** Senza internet la nave combatte comunque, con frasi pre-generate.
- **Qualità misurata.** Battaglie simulate senza grafica, obbedienza agli ordini, azioni non valide, coerenza tra parole e azioni, fedeltà alla lingua, costo. Nessuna modifica passa se non supera il banco di prova.

### 4.6 Modelli e tempo reale (report 09)
- **Spina dorsale: DeepSeek V4.1 Flash** (`deepseek-flash`, pesi aperti con licenza MIT, 16 miliardi di parametri attivi). È il miglior modello aperto senza ragionamento e costa $0,30 / $1,20 per milione di token; l'input già in cache costa quasi zero.
  - Ragionamento spento per equipaggio e ufficiali.
  - Basso o alto per capitani e ammiragli.
  - Massimo per il Regista, che lavora in background.
- **Doppio canale.** Tutto passa da OpenRouter (scelta dell'utente: niente chiave DeepSeek diretta). Per gli ordini critici la stessa richiesta parte in parallelo verso due provider dello stesso modello, Fireworks e Together (circa 0,4–0,5 s). Vince il primo, l'altro viene annullato e non si paga.
- **Alternative da mettere alla prova:**
  - gpt-oss-120b su Cerebras (circa 1.700 token/s, meno intelligente);
  - GLM-5.3-Flash;
  - MiniMax-M3;
  - GPT-6 Luna.
- **Intenti locali.** EmbeddingGemma-300m sul processore, 5–15 ms, oltre 100 lingue, circa 50 ordini frequenti.
- **Esecuzione speculativa.** L'AI parte già sulla trascrizione parziale e ricomincia se la frase cambia.
- **Strumenti "grossi"** ma pochi per ruolo, prompt ordinati per massimizzare la cache.
- **Costo:** circa **0,5–1,5 $ per ora di battaglia**. Di sera e nel weekend DeepSeek costa la metà.
- **Scelta finale con il benchmark nostro dall'Italia**, secondo il protocollo del report 09.

### 4.7 Voce multilingua e traduttore universale (report 13)
- **Lingua del giocatore.** Viene rilevata dalla voce (Whisper) o dalle impostazioni del Mac, e la puoi cambiare a voce. I prompt sono in inglese e l'AI indica lingua ed emozione prima del testo.
- **Nella storia, il traduttore universale neurale** spiega perché tutti ti parlano nella tua lingua. Le trasmissioni nemiche arrivano con leggeri artefatti di traduzione.
- **Riconoscimento vocale sul chip neurale del Mac** (lasciando libera la GPU):
  - Parakeet v3, 25 lingue europee, italiano con circa il 3–4% di errori;
  - WhisperKit per l'identificazione della lingua e le lingue extraeuropee;
  - un glossario di nomi della nave passato all'AI per correggere gli errori.
- **Sintesi vocale locale:**
  - **Pocket TTS** (Kyutai) sul processore, circa 6 volte il tempo reale su un M4 Air, per IT, EN, FR, DE, ES e PT;
  - Kokoro per cinese, giapponese e hindi;
  - Supertonic 3 per altre lingue;
  - ElevenLabs gratuito come riserva in sviluppo.
- **Identità delle voci.** Le progetto offline con Qwen3-TTS: design da descrizione e clip di riferimento per emozione (calmo, urgente, urlo, paura, sussurro, radio). A runtime ogni personaggio viene clonato mantenendo lo stesso timbro in tutte le lingue.
- **Conferme istantanee.** 10–20 frasi brevi per personaggio × lingua × emozione, pre-generate e con il volto già animato.
- **Latenza** dal rilascio del tasto alla risposta vera: circa 0,5–1,3 s. La conferma parte a 0,1–0,2 s e il filtro radio maschera le attese.
- **Multiplayer.** La voce viene sintetizzata su ogni computer, come la grafica: il server invia solo circa 100 byte per battuta. Nessun costo audio sul server, nessuna chiave sui computer dei giocatori.

### 4.8 Volti e labiale fatti in casa
1. **Audio → 52 espressioni facciali ARKit** con un modello ONNX leggero (`wav2arkit_cpu`, Apache-2.0) eseguito sul processore dentro Unreal. Più avanti, un aggiornamento con Audio2Face-3D di NVIDIA in formato ONNX.
2. **Traccia fonetica.**
   - Testo → fonemi con espeak-ng, oltre 100 lingue, eseguito come processo separato.
   - Fonemi allineati all'audio.
   - I fonemi forzano chiusure (p/b/m), labiodentali (f/v) e arrotondamenti. L'ampiezza apre la mandibola: chi urla spalanca la bocca.
3. **Tutto il resto del volto.** Emozione dichiarata dall'AI su sopracciglia, occhi e guance. Cenni sugli accenti della frase, battiti di palpebre alle pause, sguardo e respirazione. Mentre parli gli NPC ti ascoltano annuendo.
4. **Applicazione ai MetaHuman** tramite la mappatura ARKit di Epic. Le battute pre-generate vengono "cotte" con il risolutore offline di Epic, che dà la qualità più alta.

### 4.9 Plancia diegetica e accessibilità
- Ogni informazione ha un posto: console, tavolo olografico, dispositivo da polso, voce dell'equipaggio o allarme.
- Tre distanze di lettura; un tasto inquadra la console che guardi; testo leggibile e scalabile.
- Mai informazioni affidate solo al colore; sottotitoli facoltativi con nome di chi parla e direzione.
- Comando scritto e menu radiale sempre disponibili.

### 4.10 Personaggi e animazioni (report 10)
- **MetaHuman gratuiti creati da script:**
  - corpo, volto, pelle, occhi e capelli (a ciocche, gli unici supportati su Mac);
  - le fasi di rig e texture passano dal cloud di Epic, con login una tantum;
  - un roster YAML dell'equipaggio (nome, reparto, grado, età, corporatura) genera i personaggi.
- **Uniformi modellate da me** in Blender, un modello per reparto. Diventano abiti MetaHuman ridimensionabili (ChaosOutfitAsset); colori e mostrine di reparto e grado sono parametri.
- **Animazioni:**
  - base con il Game Animation Sample 5.8: motion matching, ragdoll fisico con recupero, sedersi;
  - Mixamo e dataset di motion capture gratuiti;
  - le animazioni mancanti (saldare, estintore, primo soccorso) arrivano dal motion capture da video sul Mac (GVHMR) o da generazione AI (Kimodo su GPU cloud gratuita, MoMask);
  - animazione procedurale: fisica sugli impatti, digitazione con cinematica inversa, gesti guidati dal tono di voce.
- **Tre livelli sul Mac:**
  - T0: fino a 3 personaggi ravvicinati con volto completo;
  - T1: 10–12 membri dell'equipaggio visibili;
  - T2: sfondo con MetaHuman Crowd e loop precotti.

### 4.11 Grafica efficiente (report 11)
- **Nello spazio, niente illuminazione globale costosa:**
  - un sole con ombre;
  - cielo e riflessi dal cubo HDR della nebulosa;
  - mappa stellare NASA da 1,7 miliardi di stelle;
  - nebulose a strati con parallasse;
  - flotte lontane come impostori e poi bagliori;
  - atmosfere con pochi campioni in orbita e nubi volumetriche solo durante il rientro.
- **Interni:**
  - **Lumen Lite** (dinamico, circa 2× più veloce di Lumen High), così squarci e incendi cambiano la luce;
  - schermi emissivi;
  - regole ferree sulle luci: al massimo 4 con ombre visibili, e le luci d'allarme cambiano solo intensità e colore;
  - fumo con volumi di nebbia locali e particelle.
- **Upscaling:** TSR al 60–67% con risoluzione dinamica. Lo sviluppo, da parte mia, di un plugin **MetalFX** (l'upscaler di Apple) vale un ulteriore 20–30% di prestazioni: è un obiettivo bonus.
- **Memoria:** il gioco resta sotto i 9 GB, con i pool di texture e Nanite impostati a mano.
- **Obiettivi misurati automaticamente dopo 10 minuti a caldo**, in Full HD:
  - spazio: 60 fps;
  - interni: 60 fps come obiettivo, 45 come minimo;
  - ogni regressione oltre il 5% blocca la modifica.
- **Profili:** A (M4 Air), B (M4 Pro/Max), C (PC con RTX).

### 4.12 Arte: io come artista 3D (report 08 e 12)
- **Pipeline:**
  - scheda tecnica;
  - concept con modelli di immagini via OpenRouter (FLUX.2, Seedream, Gemini Image; circa 0,5–2 $ ad asset);
  - sagoma in Blender da una "grammatica" di astronavi con seed;
  - forme e dettagli: booleane Manifold, smussi procedurali, normali pesate, pannellature, "greeble" come istanze;
  - UV su trim sheet (texture condivise a strisce);
  - bake di occlusione e curvatura nei colori dei vertici;
  - validazione automatica, import in Unreal con validatori;
  - catture da 2 m, 50 m e 1 km;
  - **autocritica visiva** con checklist, e ripeto finché passa.
- **Regole alla EVE:**
  - niente texture uniche sugli scafi grandi;
  - un materiale principale a strati selezionati da maschere;
  - usura e danni con maschere;
  - livree come parametri;
  - navi modulari.
- **Materia prima gratuita**, sempre rielaborata:
  - Poly Haven, ambientCG, Blendkit CC0, 3dtextures.me;
  - Megascans (set gratuito di oltre 1.500 asset), contenuti Epic gratuiti (Cassini, City Sample…) e regali Fab ogni due settimane;
  - Sketchfab CC, scansioni Smithsonian CC0, modelli NASA di hardware vero;
  - AI 3D (TRELLIS.2 sul Mac) solo per oggetti di scena secondari.
- **Generatore procedurale di navi per le flotte.** Parti modulari mie e regole di stile per fazione: varietà infinita ma coerente.
- **Guida di stile ASTRA (proposta).** Realismo militare "vissuto" alla The Expanse con l'eleganza di una flotta stellare. Scafi chiari con livrea blu per noi; per il nemico sagome angolari scure e luci ambra. La potrai cambiare tu (§6).

### 4.13 Audio e musica
- **Effetti:** archivi Sonniss GDC (royalty-free), registrazioni NASA vere, Freesound CC0/CC-BY. Effetti su misura con Stable Audio 3, un modello aperto.
- **Colonna sonora originale** generata in locale con **ACE-Step 1.5** (licenza MIT, gira sul Mac). **Musica dinamica** guidata dalla tensione del Regista.
- **Acustica spaziale:**
  - il vuoto è silenzioso, si sente solo ciò che passa per lo scafo o la tuta;
  - suoni ovattati quando cala la pressione;
  - scricchiolii dello scafo;
  - un allarme diverso per ogni pericolo;
  - un filtro radio per le comunicazioni.

### 4.14 Pianeti senza caricamenti (M7)
- Terreno sferico procedurale (cubo proiettato su sfera, quadtree) generato dal seed.
- Atmosfera Unreal spostata sul pianeta più vicino.
- Rientro con plasma, calore e vibrazioni.
- Città generate con PCG e moduli rielaborati dai contenuti Epic gratuiti.

### 4.15 Pronto per il multiplayer
- Tutto è autoritativo lato server anche in singolo giocatore; replicazione Iris dal primo giorno.
- Posizioni relative alla nave o al pianeta.
- Menti AI sul server, voce generata sui computer dei giocatori.
- Più avanti: server dedicati (servirà Unreal compilato da sorgente su un PC o in cloud) e "server meshing" sulle bolle.

---

## 5. Autonomia: come lavoro io

- **Controllo di Unreal:**
  - MCP ufficiale di Epic più le skill Epic per Claude Code;
  - un mio strumento per eseguire Python arbitrario nell'editor;
  - C++ compilato da terminale;
  - comandi automatici senza interfaccia grafica;
  - clic nell'editor e nel Launcher solo quando indispensabile.
- **Occhi:** catture su file, che guardo, critico e correggo.
- **Blender 5.2** interamente da script.
- **Reperimento asset:**
  - API (Poly Haven, ambientCG, Blendkit, Sketchfab, Smithsonian, NASA, Freesound, Hugging Face, GitHub);
  - browser integrato con i tuoi accessi per Fab e Mixamo, a ritmo umano;
  - editor di Unreal per importare da Fab;
  - facoltativo: un'attività programmata ogni due martedì che riscatta i regali Fab utili ad ASTRA.
- **Registro licenze automatico.** Per ogni file: fonte, autore, licenza, attribuzione e modifiche. Oggi non conta, ma se un giorno vorrai pubblicare sapremo esattamente cosa sostituire.
- **Qualità continua:** test automatici di prestazioni, validatori degli asset e banco di prova delle AI.
- **Versionamento** Git + Git LFS con commit frequenti. Facoltativo: backup del codice su un repository privato GitHub (gratis).

---

## 6. Cose a cui non avevi pensato (e che ho già previsto)
1. **La Bibbia di ASTRA.** Fazioni, storia, tecnologia, gradi, nomi. La scrivo io in bozza e tu la plasmi. È anche la memoria condivisa di tutte le AI: più è ricca, più l'equipaggio è credibile e coerente.
2. **IDEE.md, il tuo canale creativo.** Scrivi idee quando vuoi, anche disordinate; io le trasformo in lore e funzioni.
3. **Modalità Game Master.** Puoi dirigere tu la guerra, a voce.
4. **Il giornale di bordo come spina dorsale narrativa.** Tutto viene registrato: diario del capitano, notiziari, memorie dell'equipaggio, commissione d'inchiesta.
5. **Sconfitte che non chiudono il gioco** e una progressione di carriera: nave → squadriglia → task force.
6. **Il Primo Ufficiale come tutorial vivente.**
7. **Accessibilità.** La voce non è mai obbligatoria: ci sono comandi scritti e sottotitoli.
8. **Modalità offline.** Senza internet la nave combatte con le dottrine e le frasi pre-generate.
9. **Controllo dei costi AI:** budget per sessione, cruscotto, prezzi dimezzati la sera.
10. **Osservabilità delle AI**, alla "Mindview": vedi cosa sapeva un NPC e perché ha agito così, con replay.
11. **Registro licenze** per una futura pubblicazione.
12. **Sicurezza.** Chiavi solo nel file privato; server MCP solo in locale.
13. **Xcode bloccato**: la 26.4 rompe Unreal 5.8.
14. **Distanze compresse** per una battaglia visibile, non solo realistica.
15. **Voce sui computer dei giocatori.** Il multiplayer futuro costa poco.
16. **Unreal 6.** La 5.8 è l'ultima versione di UE5; teniamo il codice modulare per migrare.
17. **Il MacBook Air non ha ventola.** Compilazioni lunghe e test a caldo, quindi tienilo alimentato e su una superficie fresca.

---

## 7. Tabella di marcia dell'alpha

| # | Traguardo | "Fatto" quando… |
|---|---|---|
| M0 | Fondamenta | Strumenti installati e progetto creato. MCP e controllo dell'editor verificati con catture. Repository, registro licenze, bozza della Bibbia e della guida di stile. Benchmark AI eseguito e servizio vocale di base funzionante |
| M1 | La nave che si cammina | Kit modulare ASTRA mio e nucleo della nave percorribile (plancia, corridoio, ascensore, sala macchine, hangar). Spazio fotorealistico fuori dai finestroni, prestazioni entro i limiti |
| M2 | La nave che vive | Energia e calore, scudi, armi, motori, sensori, compartimenti. Console e tavolo olografico con dati reali. Pilotaggio dal timone |
| M3 | L'equipaggio che pensa | Ufficiali AI con catena di comando a circuito chiuso, voce multilingua, MetaHuman in uniforme, labiale, Primo Ufficiale |
| M4 | Battaglia | Navi nemiche dal generatore, armi, guerra elettronica, squarci, incendi, paratie, squadre di riparazione, triage |
| M5 | Hangar | Caccia e droni comandati dalla plancia; tu in cabina di pilotaggio |
| M6 | La guerra | Sistema stellare, flotte, ammiragli, diplomazia radio, Regista con finale, sconfitte che non chiudono il gioco, salvataggi |
| M7 | Il pianeta | Discesa senza caricamenti dall'orbita a una città |
| M8 | Rifinitura | Audio, luce, prestazioni, preparazione al multiplayer |

---

## 8. Rischi e contromisure

| Rischio | Contromisura |
|---|---|
| Portata enorme | Fette verticali complete; nucleo della nave prima, espansione dopo |
| Latenza AI dall'Italia | Intenti locali, conferme istantanee, doppio canale, esecuzione speculativa |
| GPU contesa sul Mac | Voce sul chip neurale e sul processore, GPU riservata a Unreal, budget in millisecondi |
| Stile incoerente tra fonti diverse | Materiali condivisi, trim sheet, decalcomanie, guida di stile, autocritica visiva |
| Automazione Fab e Mixamo fragile | Solo ritmo umano e strade ufficiali; più fonti alternative con API |
| Qualità voce in lingue minori | Voci di prima classe in 6 lingue, riserva cloud gratuita, miglioramento continuo |
| Pianeti senza caricamenti | Prototipo isolato; prima una luna senza atmosfera |
| Multiplayer vero | Architettura già autoritativa; server dedicati più avanti |
| Aggiornamenti che rompono gli strumenti | Xcode bloccato, versioni fissate, commit frequenti |

---

## 9. Fonti
Tutto è documentato nei 14 report della cartella [ricerca/](ricerca/00-INDICE.md). Questo piano sostituisce la v0.1.
