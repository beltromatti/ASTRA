# La guerra grande — progetto tecnico della fase F2

*Documento del lead (2026-09-30). Contratto per gli agenti di supporto del modulo GUERRA: cosa costruire, in che ordine,
come si prova. I nomi nel gioco sono in inglese; il documento in italiano. Vedi anche [PIANO.md](PIANO.md) §3–4 e
[ARCHITETTURA.md](ARCHITETTURA.md).*

## 0. Dove siamo (misura del 30/9 col banco senza grafica)

`tools/war.py run --seconds 600 --jump 160` (la battaglia d'apertura, senza la mente): la flotta ASTRA (Praetorian,
Vigilant, Aquila) perde tutto contro Acheron + tre Styx + Lethe in circa 11 minuti dal contatto; i caccia nemici
muoiono in un minuto. La simulazione attuale (`AstraBattleSubsystem.*`, ~5300 righe) ha già: navi e caccia, rotaie,
laser, missili, siluri, difesa di punto, scudi a bolla con un valore unico, nebbia di guerra e guerra elettronica, esche,
squadroni con missioni, un comandante nemico guidato dalla mente (ordini e tattiche), un regista a battute.
Mancano: la scala, i danni fisici per sezione e per faccia, le gerarchie, l'intelligenza di gruppo, la bellezza.

## 1. Obiettivo (il "fatto" della fase)

Una battaglia di flotta dura 30–60 minuti ad alta intensità, con decine di navi capitali e centinaia di caccia e droni;
dalla plancia la vedo tutta (schermo principale, finestrone, tavolo), le mosse contano (manovra, fuoco, energia, sensori,
caccia, flotta, trattativa), i nemici sono furbi in gruppo, e l'esito dipende da come comando — non da un copione.

## 2. Principi

1. **Due velocità**: il codice fa il continuo (navi, caccia, squadre, formazioni, bersagli, evitamento) a 10–20 Hz; le
   menti (ammiragli, comandanti di gruppo) decidono ogni 60–120 s o sugli eventi forti, con ordini da un menu chiuso.
2. **Nessun copione, nessun favore**: il regista crea situazioni e ritmo dai fatti (arrivi, rinforzi, ritirate,
   trattative), mai con numeri truccati a metà battaglia.
3. **Fisica leggibile**: masse, spinte, velocità di rotazione da nave capitale; danni dall'energia del colpo contro scudi
   per faccia e corazza per sezione; ciò che si vede sullo schermo è ciò che è successo nella simulazione.
4. **La verità e la credenza**: l'IA di ogni parte usa ciò che i suoi sensori sanno (come `GetContacts` per l'Aquila);
   la verità (`DebugState`) serve solo al banco.
5. **Si prova senza grafica**: ogni passo si misura col banco (`tools/war.py`), con scenari ripetibili e statistiche.

## 3. I passi

### F2.1 Danni fisici (modulo GUERRA-DANNI)
- **Scudi per faccia** su tutte le navi capitali: sei settori (prua, poppa, babordo, tribordo, dorso, ventre) con valore,
  rigenerazione e ridistribuzione (l'Aquila ha già i modi del tattico: `balanced/face_threat/forward/...`); il colpo
  consuma il settore da cui arriva (direzione del proiettile nel riferimento della nave).
- **Tipi di danno**: cinetico (rotaie, cannoni: gli scudi ne fermano una parte, il resto passa se il colpo è pesante),
  energia (laser e dardi: gli scudi li fermano bene, scaldano), esplosivo (missili, siluri: raggio, corazza).
- **Corazza e struttura per sezione** (prua / centro / poppa, per faccia): punti struttura per sezione; una sezione a zero
  è sventrata (sistemi persi, rischio di rottura); la nave muore per esplosione del reattore, rottura in pezzi o resta
  **relitto disattivato** (abbordabile in F5).
- **Sottosistemi** legati alle sezioni: motori (poppa: spinta e virata), batterie d'arma (per montaggio e arco di tiro),
  sensori (portata, precisione), hangar (lancio e recupero), ponte di comando (reazione più lenta), reattore (energia).
  Per l'Aquila si agganciano agli incidenti interni già esistenti (falle, incendi, condotte) e alle squadre di ops.
- **Dove si prova**: scenari del banco con bersagli fermi e colpi da facce diverse; statistiche di danno per tipo e faccia.

### F2.2 Gerarchie e intelligenza (modulo GUERRA-IA)
- **Flotta → gruppo di battaglia → nave**; **stormo → squadriglia (2–4) → caccia/drone**. Ogni livello ha uno stato e
  un ordine in vigore (come le postazioni: modo + parametri + scadenza), eseguito dal codice.
- **Gruppo di battaglia** (codice): formazioni (linea di fronte, cuneo, schermo, colonna), assegnazione dei bersagli con
  fuoco concentrato, aggiramento, rotazione delle navi danneggiate dietro lo schermo, saturazione coordinata dei missili,
  ritirata ordinata (perdite, morale, ordine), ricongiungimento.
- **Nave** (codice): tenere gli archi di tiro e la distanza giusta per il suo armamento, girare lo scudo più forte verso
  la minaccia, difesa di punto sui missili più pericolosi, evitare collisioni con navi, relitti e asteroidi.
- **Caccia** (codice): squadriglie con capo e gregari; pattuglia, scorta, attacco, intercettazione, disturbo; duello
  (curve d'inseguimento, virate di rottura, energia), passaggi d'attacco dei bombardieri (avvicinamento, sgancio, uscita),
  evitare le bolle di difesa di punto e le navi, rientro se danneggiati o scarichi. Evitamento reciproco (separazione
  e previsione a breve) per centinaia di velivoli.
- **Menti** (mind): l'ammiraglio del Mandato e i comandanti di gruppo scelgono da un menu chiuso (attacca il gruppo X,
  inchioda, aggira a sinistra/destra, schermo, ritirata, rinforza, trattativa); gli alleati ASTRA fanno lo stesso e
  **parlano con noi** (richieste, avvisi, coordinamento) — pochi messaggi, brevi, utili.
- **Dove si prova**: il banco con scenari simmetrici (le stesse forze, posizioni speculari: nessuna parte deve vincere
  sempre), scenari asimmetrici con esito atteso, e misure di "intelligenza" (fuoco concentrato, perdite evitate,
  ritirate riuscite, caccia persi contro la difesa di punto).

### F2.3 Scala e ritmo (modulo GUERRA-SCALA)
- **Scenari dai dati** (`data/war/*.json`): classi di navi (massa, spinta, virata, scudi per faccia, corazza per
  sezione, armamento con archi e cadenze, stive di caccia), flotte, posizioni, obiettivi. Battaglie fino a ~30 navi
  capitali e ~150 caccia/droni; campagna di più battaglie.
- **Simulazione a livelli di dettaglio**: ciò che è lontano dall'Aquila si aggiorna meno spesso; griglia spaziale per le
  domande di vicinanza (difesa di punto, evitamento, bersagli); proiettili in array compatti.
- **Disegno a istanze**: caccia e proiettili come istanze (ISM/HISM), niente attore per ogni oggetto; luci e particelle con
  un budget.
- **Obiettivo di prestazioni**: 1 ms di simulazione per frame con 30 navi e 150 caccia (misurato col banco); la grafica
  ha il suo gate in [ricerca/11](ricerca/11-efficienza-grafica.md).

### F2.4 Bellezza (lead + modulo GUERRA-VISTA)
- Armi alla Star Wars / Star Trek dentro la fisica di ASTRA: **dardi** (turbolaser: lampi allungati luminosi),
  **fasci** (laser con bagliore e calore), **traccianti** delle rotaie, **siluri** luminosi con scia, **esplosioni** a
  strati (lampo, sfera di fuoco, detriti, fumo, scintille), **scudi** che si accendono a esagoni nel punto d'impatto,
  **motori** con pennacchi e bagliore, **navi che si spezzano** (metà della mesh per parte con taglio luminoso, detriti,
  incendi nelle sezioni sventrate). Riferimenti: EVE Online, Star Wars (Rogue One, Andor), Star Trek (Picard, Discovery).
- Il lead prova e giudica tutto nel gioco (catture e schermo principale).

### F2.5 Il regista v2 (mind + codice)
Un regista invisibile che legge la situazione (tensione, stanchezza del giocatore, equilibrio) e crea: rinforzi da
entrambe le parti secondo la logica della campagna, trattative, eventi dello spazio (campi di detriti, tempeste di ioni,
navi civili), notizie; mai atti fissi, mai colpi di scena che cambiano i numeri di una battaglia in corso.

## 4. Il banco (per tutti i passi)

```
tools/war.py run --seconds 900 --jump 160 [--exec "astra.battle.spawn styx 12 30"] [--out Saved/War/x.json]
tools/war.py report Saved/War/x.json     # arrivi, perdite, superstiti, ultimi rapporti
tools/war.py ship Saved/War/x.json T-21  # una nave nel tempo
```
Il commandlet (`Source/ASTRA/AstraWarSimCommandlet.*`) gira con `-nullrhi` (niente GPU, anche col gioco aperto), a circa
mille volte il tempo reale. Gli agenti di supporto lo usano nel loro worktree con il loro build dell'editor
(`Engine/Build/BatchFiles/Mac/Build.sh ASTRAEditor Mac Development -Project=<worktree>/ASTRA.uproject`): **mai** il
gioco con la grafica, **mai** l'editor con la finestra (quelli restano al lead).
