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
*Stato (30/9): fatto dal modulo GUERRA: com'è fatto nel §5.3, misure nel §7.*
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
*Stato (30/9): fatto dal modulo GUERRA: com'è fatto nei §5.4–5.7, il contratto delle menti nel §6, misure nel §7.*
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
*Stato (30/9): la parte di simulazione (classi e scenari dai dati, griglia, scala 30 navi + 150 velivoli) è fatta dal modulo GUERRA (§5, §7.5); il disegno a istanze resta.*
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

## 5. Com'è fatto (F2.1 e F2.2, modulo GUERRA)

*Scritto a fine lavoro del modulo: cosa c'è nel codice, come si tara, i limiti noti. I numeri misurati sono nel §7. I nomi nel
gioco e nei dati sono in inglese.*

### 5.1 I file

| file | cosa contiene |
|---|---|
| `data/war/classes.json` | la tabella delle classi (vedi 5.2); `python3 tools/war.py embed` la riscrive in `AstraWarClassesData.inl` (il gioco la incorpora; il banco la ricarica dal file all'avvio) |
| `AstraWarTypes.h`, `AstraWarClasses.*` | facce, sezioni, sistemi; `FAstraMount` (arco di tiro), `FAstraShipDamage`, `FAstraDeathEvent`; la tabella delle classi e le variabili di taratura (`astra.war.tune`) |
| `AstraWarDamage.cpp` | il modello dei danni (F2.1): scudi a sei settori, corazza e struttura per sezione, sistemi, affusti, morte; `GetDamageView`, `ConsumeDeathEvents` |
| `AstraWarStats.*` | le statistiche del banco (danni per tipo e faccia, perdite per causa, fuoco concentrato, tempo per tick) |
| `AstraWarKnowledge.cpp` | cosa sa ciascuna parte (sensori, memoria), griglia spaziale, indice degli id |
| `AstraWarAI.h` | gruppi di battaglia, voli, griglia |
| `AstraWarGroups.cpp` | il gruppo: guida, formazioni, bersaglio, distanza, rotazione, salve, morale, ritirata, ordini |
| `AstraWarShipAI.cpp` | la nave: distanza, archi, scudo, evitamento, difesa di punto |
| `AstraWarCraft.cpp` | i velivoli: voli, modello di volo, duello, passaggi d'attacco, rientro |
| `AstraWarOrders.cpp` | gli strumenti dei comandanti: `group_order`, le viste per parte, gli eventi (vedi §6) |
| `AstraWarScenario.cpp` | comandi di console `astra.war.sandbox/spawn/wing/scenario/tune` e il caricamento di `data/war/scenarios/*.json` |
| `AstraWarSimCommandlet.cpp` | il banco: più semi in un processo (`-seeds=N`), `-scenario=`, `-at=`, `-views` |
| `AstraBattleSubsystem.*`, `AstraBattleQueries.cpp` | l'integrazione nella simulazione esistente (tick, proiettili, morti), `GetContacts`, `DebugState`, `GetWeaponRanges` |

Fuori dal modulo è toccato solo `AstraShipSubsystem.cpp`, con un inoltro di due righe (il comando `group_order` e la chiave
`_astra_groups` dello snapshot). Niente in `mind/`, `Content/`, `Config/`, nelle postazioni, nello schermo principale, nel
tavolo olografico, nel regolatore del giocatore.

### 5.2 Le classi

Una classe è una riga di `data/war/classes.json`: scafo, scudi (× una scala), spinta, virata, crociera, corazza, quote della
struttura per sezione (prua / centro / poppa), corazza per faccia, ripartizione degli scudi sulle sei facce, armamento,
sezione dove vive ogni sistema, **affusti con arco di tiro**, portata preferita, e le **misure vere dello scafo**: `hull_m`
(la mesh v3 in metri: estremi dell'asse dall'origine della mesh, larghezza, altezza: la scatola che un colpo incontra),
`cuts_x_m` (dove sono tagliati i pezzi di rottura: il taglio di prua e quello di poppa, su x), `radius` (l'estremo dello
scafo più lontano dall'origine: serve a tutto ciò che è "grandezza" — spaziatura delle formazioni, evitamento, sfera di
prima scrematura dei colpi, dimensione degli effetti) e `tier` (quanto conta: 3 nave capitale, 2 incrociatore, 1
cacciatorpediniere o mercantile, 0 più piccole: ciò che prima dipendeva da soglie sul raggio — firma, disturbo, celle dei
missili, esche dei raid, punti sul tavolo — usa il tier). Le sei facce sono nell'ordine prua, poppa, babordo, tribordo,
dorso, ventre. Le misure vengono da `art/export/ships_v3/manifest.json` (ARTE-NAVI): se un modello cambia, si
aggiornano i numeri qui e si rilancia `python3 tools/war.py embed`.

| classe | ruolo | scafo | scudi | spinta m/s² | virata °/s | crociera m/s | rotaia (colpi × danno / ciclo, portata) | laser | missili | difesa di punto |
|---|---|---|---|---|---|---|---|---|---|---|
| aquila | Aquila-class carrier cruiser | 3000 | 1100 ×2,0 | 15 | 3 | 288 | 4×55 / 7 s, 10 km | 18 / 5 s, 4 km | 96 | 4 canali, 2 km |
| praetorian | ASTRA battleship | 5200 | 2000 ×2,0 | 12 | 2,2 | 300 | 4×72 / 9 s, 10 km | 18 / 5 s, 4 km | 24 | 4 canali, 2 km |
| vigilant | ASTRA destroyer | 1200 | 500 ×1,5 | 18 | 4,5 | 300 | 2×55 / 7 s, 8 km | 18 / 3,3 s, 4 km | 12 | 2 canali, 2 km |
| acheron | Kharon Mandate cruiser | 3600 | 1500 ×2,0 | 15 | 3 | 450 | 3×85 / 8 s, 8 km | 18 / 5 s, 4 km | 32 | 3 canali, 2 km |
| styx | Kharon Mandate destroyer | 1300 | 500 ×1,5 | 18 | 4,5 | 450 | 2×60 / 9 s, 8 km | 18 / 3,3 s, 4 km | 16 | 2 canali, 2 km |
| lethe | Kharon Mandate frigate | 520 | 220 ×1,5 | 22 | 6 | 500 | 2×55 / 8 s, 8 km | 18 / 3,3 s, 4 km | 8 | 2 canali, 2 km |
| freighter | Free Guilds freighter | 700 | 60 ×2,0 | 8 | 2 | 180 | - | - | - | - |
| station | listening post | 5000 | - | 0 | 0 | 0 | - | - | - | - |

Le misure vere (lunghezza × larghezza × altezza in metri; x dalla poppa alla prua; tagli di prua e di poppa):

| classe | lunghezza × larghezza × altezza | x | tagli (prua, poppa) | `radius` | `tier` |
|---|---|---|---|---|---|
| aquila | 799 × 140 × 92 | −407 … +392 | +236, −105 | 407 | 3 |
| praetorian | 1129 × 184 × 220 | −579 … +550 | +215, −215 | 579 | 3 |
| acheron | 587 × 105 × 149 | −323 … +264 | +95, −168 | 323 | 2 |
| vigilant | 306 × 54 × 64 | −156 … +150 | +58, −58 | 156 | 1 |
| styx | 387 × 81 × 115 | −212 … +175 | +30, −78 | 212 | 1 |
| lethe | 240 × 61 × 57 | −127 … +113 | +45, −46 | 127 | 0 |
| freighter | 352 × 73 × 47 | −180 … +173 | +97, −101 | 180 | 1 |
| station | 221 × 120 × 66 | (±110) | - | 111 | 0 |

(I valori di scudi e struttura della simulazione sono quelli della tabella per la scala e per `struct_scale`, tarati sul banco
contro il vecchio modello a valori unici: vedi "Il duello" nel §7.) Una nave senza classe (caccia, esche) resta a valori unici
e si colpisce come una sfera di `Radius`.

### 5.3 I danni fisici (F2.1)

Il gioco disegna le mesh in scala vera, quindi ciò che si vede colpito deve essere ciò che la simulazione colpisce: lo scafo di
una nave con classe è una **scatola** delle misure vere (test delle lastre contro il percorso del proiettile, del raggio laser,
della raffica di un caccia o del cannone del Falcon del Capitano; prima una sfera di `radius`, enorme sul fianco di una
nave lunga e sottile). Il punto dove il percorso **entra** nella scatola dice la **faccia** (quella su cui cade il punto:
prua, poppa, babordo, tribordo, dorso, ventre) e, con la posizione lungo lo scafo contro i **piani di taglio** della classe, la
**sezione** (prua oltre il taglio di prua, poppa oltre quello di poppa, centro in mezzo); la mira cade dove il cannoniere sceglie e la
caduta dei colpi li disperde lungo lo scafo (`hit_scatter`, frazione della semilunghezza). Da lì:

1. **Il settore di scudo** della faccia colpita prende la parte che il tipo di danno gli lascia prendere. Ogni settore ha una
   capacità (la quota della faccia × la riserva totale). Si rigenera; il generatore può spostare la capacità da un settore
   all'altro (`SetShieldFocus`: l'Aquila con i modi del tattico, le altre navi da sole sulla minaccia principale, ogni 1,5 s),
   e l'energia in eccesso di un settore ridimensionato passa da un serbatoio a una velocità finita (10 % della riserva al
   secondo): una riallocazione non è istantanea.
2. **La piastra di corazza** della faccia e della sezione colpite prende una parte di ciò che è passato (un colpo pesante ne
   ignora una parte) e si consuma.
3. **La struttura della sezione** (prua, centro, poppa) prende il resto e, a zero, "trabocca" sulle vicine. Una sezione a zero
   è **sventrata**: ciò che ci viveva è perso, brucia e perde aria.
4. **Sistemi e affusti** della sezione si degradano col danno (fragilità per sistema, esposizione per faccia: i motori si vedono
   da poppa, i sensori da prua e dall'alto, il reattore sta dentro). Motori → spinta e virata; affusti → cadenza e archi;
   sensori → portata; hangar → lancio e recupero; ponte → ritardo di reazione (fino a 3 s); reattore → energia di scudi e armi.

| tipo di danno (colpi) | scudo ferma | corazza prende | ignora la corazza oltre | trabocca sulle sezioni vicine | danno ai sistemi |
|---|---|---|---|---|---|
| energia (laser, difesa di punto) | 95 % | 30 % | - | 0 | ×0,8 |
| cinetico (rotaie, cannoni) | 85 % (fino al 43 % per un colpo pesante) | 55 % | 60 | 0 | ×1,0 |
| esplosivo (missili, siluri, razzi) | 75 % (fino al 49 %) | 40 % | 100 | 30 % | ×1,4 |

**Morte** (tre modi): esplosione del reattore (30 %, 50 % sotto mezzo scafo, quando il reattore è distrutto), rottura dello
scafo lungo una sezione sventrata (25 % alla prima, 70 % alla seconda, sicura alla terza; ×1,5 al centro; dopo 2,5–8 s di
preavviso; l'Aquila non si spezza mai; il **punto di rottura** degli eventi e della vista dei danni cade sul **taglio vero**
della sezione che cede: il taglio di prua per la prua, quello di poppa per la poppa, a metà fra i due per il centro; `CutBowX`
e `CutSternX` danno i due piani in metri sull'asse, riferimento della nave, per chi monta i tre pezzi), oppure **relitto disattivato**: niente energia, alla deriva, abbordabile in F5 (reattore
spento senza esplosione, o equipaggio che abbandona sotto il 6 % dello scafo). Un relitto colpito ancora può andare in pezzi.

**Cosa possono leggere gli altri moduli**: `GetDamageView(ContactId, FDamageView&)` — con la nebbia di guerra: dettaglio 3 per
la propria parte (tutto: sistemi, affusti, reattore), 2 per una traccia ferma e classificata (scudi per faccia, piastre e
struttura per sezione, ultimo colpo), 1 per una traccia ferma (solo sventrata/brucia/si spezza), 0 niente; `ConsumeDeathEvents()`
(come è morta, dove si è rotta, asse, punto di rottura e i due piani di taglio: per gli effetti visivi); `PlayerEngineFactor()` (0–1: da moltiplicare
alla velocità del timone); `RepairPlayerSystems(Amount)` (le squadre dei danni dell'Aquila rimettono in sesto sistemi e affusti
nelle sezioni non sventrate).

### 5.4 Cosa sa ciascuna parte

Ogni parte ha la **sua** conoscenza (`AstraWarKnowledge.cpp`), aggiornata a 4 Hz: una nave è "vista" se una nave nemica la
tiene dentro la portata dei sensori (della classe, ridotta dai danni ai sensori) moltiplicata per la sua firma (a freddo o
oscurata: un terzo); se ne ricorda la posizione e la velocità: una nave resta "nota" 25 s dopo l'ultima volta (4 s i velivoli) e
la sua posizione si stima con l'ultima velocità vista. Gruppi, navi e velivoli decidono **solo** su questo. La verità (`DebugState`) serve
al banco. L'Aquila (il giocatore) è vista dal Mandato secondo le regole di rilevamento già esistenti (`TickDetection`).

### 5.5 Il gruppo di battaglia (F2.2)

Un gruppo è un pugno di navi con un capo, una formazione (linea, cuneo, colonna, schermo), uno stato (*engage*, *withdraw*,
*regroup*) e un ordine in vigore (vedi §6). Pensa ogni 0,4 s; le navi ogni 0,1 s, sfasate.

- **La guida.** Un punto che porta il gruppo alla distanza giusta e lo tiene lì; le navi volano ai loro posti in formazione
  attorno alla guida. La guida è una "nave" del gruppo: accelera e frena a 0,55 della spinta della più lenta e comincia a
  frenare in tempo anche con il nemico che arriva dall'altra parte (senza questo due gruppi che si avvicinano a 300 m/s si
  attraversano: una nave capitale ha bisogno di chilometri per fermarsi). L'asse è misurato dalla guida verso il nemico, non
  dal centro delle navi.
- **La distanza.** Per ogni distanza da 3 km al massimo dell'armamento (0,92 della portata della rotaia più corta, al più 9,5 km)
  il gruppo confronta il suo danno al secondo con quello del nemico vicino al bersaglio, ciascuno con la sua portata vera, e
  sceglie la migliore. A parità (portate uguali, il caso normale) decide una **preferenza debole** (15 %) per la distanza a cui
  *tutta* la formazione raggiunge il nemico, non solo la prima fila del cuneo: 0,6 della portata della rotaia meno 0,3 della
  profondità della formazione, circa 4 km per rotaie da 8 km. Un vantaggio di portata (uno spostamento netto del rapporto
  dei danni) pesa più della preferenza: chi ha la portata maggiore si tiene fuori da quella dell'altro. Se il nemico è molto
  più veloce (1,25×) resta a 5,5 km (lo raggiungerebbe comunque). **Il banco** (§7.3): contro un gruppo che tiene una distanza
  fissa, chi **chiude** vince, e il vantaggio cresce fino a 2–3 km; un gruppo che tiene il massimo della portata lascia
  indietro metà del cuneo e perde da 0,5 a 2 navi su 6. Per questo la distanza è la leva principale del combattimento e la
  mente può sceglierla (`range_km` in `group_order`, §6.2), mentre il riflesso di riserva resta a una distanza media.
- **Il bersaglio** (fuoco concentrato, modo 1): per ogni nemico noto un punteggio = il valore della sua classe (il capo del
  gruppo nemico ×1,15: incrociatori e corazzate valgono più dei cacciatorpediniere) × (0,5 + quanto è battuto: scafo e scudo della
  faccia che ci mostra) × quanto il gruppo lo raggiunge; con una tenuta del 40 % sul bersaglio in corso (niente tentennamenti),
  un bonus se mira a ciò che proteggiamo e un malus se fugge. Ogni nave segue il bersaglio del gruppo se lo raggiunge, altrimenti
  spara al più vicino che raggiunge. **Il banco** (§7.3): la regola batte il "ognuno il più vicino" di 0,6–1,0 navi in
  combattimenti da 3 + 3 e da 6 + 6, e la regola "minaccia tolta per unità di sforzo" (modi 2 e 3: i cacciatorpediniere muoiono
  prima, ma senza tener conto della geometria del cuneo) di 0,6–2,3; con due gruppi da 3 il modo 2 fa meglio di 0,8 (un solo caso su
  quattro). Quel che conta è **concentrare**: spezzare il fuoco costa da una a due navi su sei.
- **Salve coordinate di missili.** Le navi tengono le celle finché ce ne sono abbastanza per saturare la difesa di punto del
  bersaglio (3 + 1,6 per canale), poi tutte insieme: ognuna parte al suo tempo di volo prima dell'istante comune
  (*time on target*). Una nave a meno di 0,6 s dall'essere pronta è tenuta anch'essa (il pensiero del gruppo gira ogni 0,4 s).
- **Rotazione.** Le navi più battute (prontezza < 0,5) passano dietro la linea (3,8 km) mentre ce n'è una in forma che la tiene.
- **Morale e ritirata.** La forza del gruppo (valore × prontezza delle navi) più quella dei gruppi alleati entro 30 km, contro
  quella dei nemici noti entro 45 km: sotto 0,38 (o perdite oltre il 60 % e rapporto sotto 0,8) per 14 s il gruppo si ritira
  in ordine (la nave in migliore forma copre la retirata se sono almeno tre), esce dal contatto (oltre 38 km), si riforma
  e rientra quando il morale è tornato a 0,75 o dopo 150 s. **Questo vale solo per un gruppo senza un ordine in vigore**:
  è il comportamento di un gruppo senza mente; qualunque ordine lo scavalca (per ritirarsi la mente ordina `withdraw`).
- **Aggiramento.** Esiste (vedi l'ordine `flank_left`/`flank_right`) ma l'**automatico è spento per default** (`flank_a/m` = 0):
  il banco lo trova dannoso (vedi §7): la nave staccata diventa il bersaglio di tutta la linea nemica.

### 5.6 La nave

Ogni nave capitale, sui suoi ordini di gruppo, sceglie: la distanza (quella del gruppo); **la prua** fra nove orientamenti
candidati (in base a quante canne dei suoi affusti coprono il bersaglio in quell'assetto e a quanto è pieno e spesso il
settore di scudo che sarebbe colpito); il bersaglio (quello del gruppo se lo raggiunge, altrimenti il più vicino); l'**evitamento**
di navi e relitti (punto di minimo avvicinamento); la **difesa di punto** sui missili più pericolosi per prima (poi i velivoli
nel suo inviluppo). Un riflesso del capitano: sotto il 28 % di scafo e con i motori, la nave si stacca dal combattimento
(solo se non c'è un ordine in vigore sul gruppo).

### 5.7 I velivoli

Stormo → squadriglia → **volo** di 3 bombardieri o 4 caccia/droni (capo e gregari). Un modello di volo cinematico (accelerazione
e virata massime per tipo), missioni (*cap*, *escort*, *strike*, *intercept*, *ew*, *recon*, *sar*), duello (inseguimento, virata
di rottura, allungo), passaggi dei bombardieri (avvicinamento, sgancio del siluro o dei razzi, uscita), un **muro
d'inviluppo** della difesa di punto (i caccia, i droni e le squadre di disturbo non entrano nella portata di un incrociatore;
i **bombardieri sì**: il muro li teneva fuori dal punto di sgancio e non sganciavano, vedi §7.6), rientro se
danneggiati, scarichi o a fine missione, e separazione fra velivoli con la griglia (centinaia di velivoli a costo contenuto).
Gli stormi lanciati per scenario si assegnano da soli i bersagli (`bAuto`).

### 5.8 Il banco

```
python3 tools/war.py run    --scenario sym_small --seconds 300 --seed 3 [--views] [--at "60=astra.cmd group_order {...}"]
python3 tools/war.py batch  --scenario sym_medium --seeds 96                      # una riga per seme e la media
python3 tools/war.py sweep  --scenario sym_small --seeds 96 --features flank=1,focus,saturate,rotate,retreat_ratio
python3 tools/war.py ab     --scenario ... --a "astra.war.tune x 1" --b "astra.war.tune x 0"
python3 tools/war.py groups Saved/War/x.json      # i gruppi nel tempo: stato, ordine, guida, asse, navi
python3 tools/war.py views  Saved/War/x.json      # ciò che le menti ricevono (registrato con --views)
python3 tools/war.py duel --shooter acheron --target praetorian --range 5   # il modello dei danni, da ogni faccia
python3 tools/war.py embed                         # dopo aver toccato data/war/classes.json
```
Il commandlet gira con `-nullrhi` (mai la grafica), deterministico per seme (`-seed=N`), anche più semi in un processo
(`-seeds=N`). **Scenari** (`data/war/scenarios/*.json`; `"mirror": true` = la parte del Mandato è quella ASTRA ruotata di
mezzo giro attorno all'origine): `sym_small` (1 Acheron + 2 Styx a parte), `sym_small_rev` (come sopra con il Mandato creato per
primo), `sym_medium` (2 + 4), `sym_two` (due gruppi da 3), `sym_air` (incrociatori portaerei con caccia e bombardieri),
`sym_fighters` (soli caccia), `asym_3to2`, `asym_2to1`, `scale_30x150` (15 navi e 75 velivoli a parte).

**Variabili di taratura** (`astra.war.tune <nome> <valore>`, dal banco con `--exec`; valori di default):

| nome | default | cosa fa |
|---|---|---|
| `shield_scale`, `armour_scale`, `struct_scale` | 1, 1, 1,2 | scale globali di scudi, corazza e struttura |
| `hit_scatter`, `fire_dps`, `breakup_p1`, `breakup_p2` | 0,5, 0,0015, 0,25, 0,7 | dispersione dei colpi lungo lo scafo (× 1,3 della semilunghezza); incendio (quota della struttura al secondo); probabilità di rottura |
| `focus_a/m` | 1 | bersaglio: 0 nessuna concentrazione (ognuno il più vicino), **1 valore della classe e quanto è battuto**, 2 minaccia tolta per unità di sforzo (con margine di avvicinamento), 3 lo stesso con la portata di adesso |
| `flank_a/m`, `flank_ratio` | 0, 0,9 | aggiramento automatico (spento); rapporto di forza da cui scatta |
| `saturate_a/m` | 1 | salve coordinate di missili |
| `rotate_a/m` | 1 | rotazione delle navi battute |
| `retreat_ratio_a/m` | 0,38 | soglia di morale della ritirata automatica (0 = mai) |
| `range_ai_a/m` | 1 | scala la distanza scelta dal gruppo (0,5 = la metà: più vicino) |
| `wall_a/m` | 3 | muro d'inviluppo della difesa di punto per i velivoli: 0 nessuno, 1 tutti, 2 solo i bombardieri, **3 tutti fuorché i bombardieri** |

(`_a` = lato ASTRA, `_m` = lato Mandato: si provano su un lato solo in uno scenario simmetrico.)

### 5.9 Limiti noti

- Tutta la tattica del gruppo è un **riflesso di riserva**: il giudizio vero (chi attacca chi, quando ritirarsi, se aggirare)
  spetta alle menti con gli strumenti del §6. Il banco misura i riflessi, non le menti.
- Il **tempo di pensiero della mente** non è nel banco (gli ordini si danno con `--at`): una mente appesa per minuti lascia i
  gruppi sui loro riflessi, che sono pensati per reggere da soli.
- L'aggiramento non paga contro una linea che concentra il fuoco sulla nave staccata: va ordinato con giudizio (per esempio per
  attirare il fuoco, o con molta superiorità), non lasciato al riflesso.
- Le navi volano in 3D ma le formazioni e i moti d'aggiramento sono nel piano; le distanze sono in metri e i tempi in secondi di
  battaglia (i numeri del §7 sono in secondi di battaglia).
- Il modello dei danni non simula il pilotaggio del giocatore: il timone dell'Aquila va moltiplicato per `PlayerEngineFactor()` dal
  lead, e le squadre dei danni devono chiamare `RepairPlayerSystems` (vedi §6.8).

## 6. Il contratto dei comandanti (le menti)

### 6.1 Il principio

Il codice è il **corpo** della flotta: fisica, formazioni, tiro, evasione, sensori, e gli **strumenti** con cui un comandante
agisce. Il giudizio sopra questo (chi attacca chi, quando ritirarsi, se aggirare, che cosa dire) è della mente, guidata da un
buon *system prompt* e da strumenti veri; il codice non filtra né corregge ciò che la mente decide. Dove il codice deve decidere
(un gruppo senza mente: il suo morale, la sua ritirata, la sua scelta dei bersagli) è **semplice** e **cede** a qualunque ordine:
finché un ordine è in vigore (`order_in_force` ≠ `auto`) il gruppo non si ritira da solo e le sue navi non rompono il
contatto da sole; `auto` restituisce il giudizio al gruppo. Gli strumenti dicono **la verità** (distanze, tempi, cosa faranno le
navi, quante navi nemiche battono un punto): informazione, mai un divieto strategico. Vengono rifiutati solo gli ordini
impossibili o non permessi (gruppo inesistente, bersaglio che non si vede, chi non può dare ordini a quella parte).

### 6.2 Il comando `group_order`

Un solo comando, sulla strada dei comandi esistente (`UAstraShipSubsystem::ApplyCommand` → `UAstraBattleSubsystem::GroupOrderCommand`):

```
astra.cmd group_order {"side":"mandate"|"astra", "group":<nome, id o una sua nave>|"all", "order":<ordine>,
                       "target":<id di contatto o "group of <id>", dove serve>, "for_s":<secondi, facoltativo>,
                       "by":"admiral"|"commander"|"captain"|"xo", "range_km":<km, facoltativo>,
                       "formation":"line"|"wedge"|"column"|"screen" (facoltativo)}
```

Nel gioco lo strumento è lo stesso che le altre chiamate (nome `group_order`, argomenti in JSON); il risultato è **ok / failed** più
un testo in inglese semplice (`detail`) che dice che cosa farà il gruppo. Esempi veri del banco:

```
ok: Vanguard (mirror): attacking A-01 (acheron), 22.0 km away: every ship that can reach it fires on it, the group closes to 7.0 km
    (on its firing line in ~50 s); while this order stands the group does not break off by itself (for 40 s, then back to its own judgement)
ok: Vanguard: flanking left on M-01 (acheron), 1 ship swinging to its beam, ~50 s to get there; 2 enemy ships have that point inside
    their gun range; the rest of the line holds the enemy's attention; while this order stands the group does not break off by itself
FAILED: ASTRA groups take orders from the Captain (through the XO) or from an allied commander (by: "captain", "xo" or "commander")
FAILED: no Mandate group 'nope' (yours: Vanguard (mirror))
FAILED: unknown order 'dance': auto, attack, pin, flank_left, flank_right, screen, withdraw, regroup, reinforce or hold
```

**Chi può ordinare cosa** (`by` è obbligatorio): i gruppi del Mandato prendono ordini dall'`admiral` (tutti, anche `"group":"all"`) o da
un `commander` (un gruppo alla volta); i gruppi ASTRA dal `captain` (tramite l'`xo`: è lui a chiamare lo strumento per il
Capitano), dall'`xo` o da un `commander` alleato. Un'altra combinazione è rifiutata con la frase sopra. La parte a cui si dà un
ordine è `side`; un ordine a una parte è sempre sui **suoi** gruppi.

**`group`**: il nome del gruppo come appare in `your_groups[].name` (esatto, oppure una parte del nome se è una sola), il suo `id` numerico, l'id di contatto di
una sua nave ("A-02"), oppure `"all"` (non per un `commander` del Mandato).

**`target`**: per `attack`, `pin`, `flank_left`, `flank_right` — un **id di contatto nemico** che la parte **tiene sui sensori** ("M-01",
"AQUILA" per il Mandato); se è scritto `"group of M-01"` l'ordine riguarda tutto il gruppo di quella nave; senza bersaglio vale il
bersaglio scelto dal gruppo (`attack` senza bersaglio = "tenete duro e premete"). Per `screen` — la nave amica da proteggere; per
`reinforce` — il nome del gruppo amico a cui andare. Ignorato per `auto`, `withdraw`, `regroup`, `hold`. Un bersaglio che la parte non vede:
`failed: you hold no track on M-05 now`.

**`for_s`**: durata in secondi (0 o assente = finché non cambia; massimo 3600). Allo scadere il gruppo torna ad `auto` e
l'evento lo dice. **`range_km`**: la distanza a cui il gruppo tiene il bersaglio (da 1,5 a 12 km): **sta sopra la scelta del gruppo**
e dura quanto l'ordine; è la leva del comandante sul combattimento (chi chiude, contro chi tiene la distanza, vince: §7.3).
**`formation`** da sola cambia la formazione.

### 6.3 Gli ordini

| ordine | cosa fa il gruppo |
|---|---|
| `auto` | il suo giudizio: bersagli, distanza, morale e ritirata |
| `attack` | fuoco su un bersaglio (una nave, o le navi di un gruppo nemico); il gruppo si porta alla distanza giusta |
| `pin` | tiene il nemico a lungo raggio (fino a 9 km) e lo impegna senza avvicinarsi |
| `flank_left`, `flank_right` | una o due navi agili e in forma (non il capo) fanno un arco attorno al nemico fino alla sua fiancata (105° dall'asse, alla distanza d'ingaggio) mentre la linea lo tiene impegnato; ≈ 50–90 s; **le navi staccate attirano il fuoco di tutta la linea nemica**: il risultato lo dice |
| `screen` | le navi si dispongono ad arco a 2,5 km o più dalla nave protetta, dalla parte del nemico |
| `withdraw` | rompe il contatto in ordine (la nave in miglior forma copre la retirata), verso un punto di raccolta (dietro la nave protetta, o al portale per il Mandato); fuori contatto (38 km) si ferma e si riforma |
| `regroup` | si ferma dov'è e si riforma, armi libere; non si ritira da sola anche se premuta |
| `reinforce` | va ad appoggiare il gruppo amico indicato |
| `hold` | tiene la posizione e spara a ciò che entra in portata |

Ogni ordine in vigore (tutti tranne `auto`) toglie al gruppo la ritirata automatica e alle navi il riflesso di staccarsi quando sono
ferite: a ritirarsi, il gruppo, ci pensa la mente.

### 6.4 La vista dei gruppi per parte

Un oggetto `{ "your_groups": [...], "enemy_groups": [...], "group_events": [...] }` per parte, **con la nebbia di guerra**:
i gruppi propri si leggono per intero (il collegamento dati), quelli nemici come li vede quella parte (le navi che ha sui
sensori, classe solo se classificata).

- **Mandato**: dentro `_mandate` (già dato alle menti nemiche dallo snapshot), le chiavi `your_groups`, `enemy_groups`, `group_events`.
- **ASTRA**: la **nuova** chiave `_astra_groups` dello snapshot (`UAstraShipSubsystem::Snapshot`), con le stesse tre chiavi; per i comandanti
  alleati.

`your_groups[]`:

```
{"id":2, "name":"Vanguard", "state":"engaged"|"withdrawing"|"regrouping", "formation":"wedge",
 "order_in_force":"auto", "order_by":"admiral", "order_seconds_left":82, "order_target":"A-01"      // gli ultimi tre solo con un ordine in vigore
 "leader":"A-01", "focus_fire_on":"M-03", "engagement_range_km":7,
 "your_strength":3.6, "enemy_strength_near":3.6, "allied_strength_near":0, "morale":0.82,
 "members":[{"id":"A-01","class":"acheron","hull_pct":84,"shields_pct":62,
             "shield_faces_pct":[29,100,100,70,100,100],   // bow, stern, port, starboard, dorsal, ventral; solo se una faccia è sotto il 90 %
             "missiles":20, "status":"flank"|"reserve"|"rear_guard"|"disabled"|"breaking off, too damaged"|"withdrawing as ordered" // se non è in formazione
           }, ...]}
```

`enemy_groups[]` (le navi nemiche tenute sui sensori, raggruppate come volano):

```
{"label":"group of M-01", "ships":[{"id":"M-01","class":"acheron"|"unknown","hull_pct":90,"shields_pct":86,"status":"breaking off"}, ...],
 "range_km":21.4, "nearest_ship_km":19.9, "bearing_deg":240}    // da: l'Aquila (ASTRA) o la ammiraglia del gruppo d'attacco (Mandato)
```
`hull_pct` e `shields_pct` ci sono solo se la parte ha quel dato (traccia ferma). `label` è "group of" e l'id di contatto più basso del gruppo:
si può usare come `target` in `group_order` così com'è.

**Dimensione**: da 1,4 KB (6 navi) a circa 5,5 KB per parte con 15 navi in 4 gruppi (il massimo misurato nel banco di scala).

### 6.5 Gli eventi

Righe brevi in inglese, ognuna col nome del gruppo. Per il **Mandato** stanno **solo** in `group_events` della sua vista (con `n`
progressivo — per sapere cosa è nuovo —, `ago_s`, `text`; gli ultimi 180 s, al massimo 16): il flusso comune degli eventi alimenta
gli schermi della plancia e i prompt dell'equipaggio e non deve portare la situazione interna del nemico. Per **ASTRA** le stesse
righe vanno anche sul flusso comune come `fleet: <riga>` (senza `report`, quindi l'equipaggio non parla da sé ma le legge nel
contesto).

| quando | riga |
|---|---|
| si ritira | `Vanguard: breaking off, it is being beaten (5 ships, strength 1.5 against 8.6, morale 0.14)` (oppure `, as ordered`, `, the commander's order`) |
| premuta mentre si riforma | `Vanguard: pressed while regrouping, falling back again (the enemy is on it)` |
| si riforma | `Vanguard: out of contact, regrouping with 5 ships` / `as ordered, regrouping with N ships` |
| rientra | `Vanguard: back in the fight with 5 ships (rested and reformed, morale 0.80)` |
| il morale cede | `Vanguard: morale is breaking (0.33), strength 3.0 against 7.5; with no order in force it will break off` |
| aggiramento | `Vanguard: flank swing begun by A-03, left round M-01` — `Vanguard: flank in position, A-03 is on the beam of M-01` |
| nave persa | `Vanguard: lost A-03 (styx), the reactor went; 5 of 6 ships left` (oppure `the hull broke apart`, `destroyed`, `disabled, the reactor scrammed`) |
| rinforzi | `Interdiction Squadron: reinforcements arriving: M-07 (styx), M-08 (styx)` |
| ordine scaduto | `Vanguard: its order has run out, back to its own judgement` |

### 6.6 I comandi che c'erano già

- `mandate_tactics` (la mente del comandante del Mandato): `focus`, `stance`, `missiles`, `fighters`, `ew`, `ships` come prima, **più** il
  menu dei gruppi: `order` (come sopra, più `attack_group`), `target`, `group` (il nome di un gruppo proprio o `"all"`; in
  mancanza il gruppo del comandante), `reinforce_group`, `formation`, `duration_s`. Usa `by:"admiral"`. `group_order` è la forma
  completa e rigorosa; `mandate_tactics` resta per compatibilità.
- `fleet_request` (il Capitano alle navi in compagnia, per l'XO): `focus_fire` → ordine `attack` sul gruppo della nave, `cover_us` →
  `screen` (a protezione dell'Aquila), `stand_off` → `pin`, `engage_freely` e `close_in` → `auto` (`hold_fire` non tocca i gruppi).
- `enemy_order` (il comandante nemico: continua l'attacco, cessate il fuoco, ritirata, resa): segna le navi; il gruppo se ne
  accorge (la ritirata ordinata sposta il gruppo in *withdraw*).

### 6.7 `GetWeaponRanges`

`FWeaponRanges UAstraBattleSubsystem::GetWeaponRanges(const FString& ContactId = FString()) const` — in km: `RailKm`, `LaserKm`,
`MissileKm`, `PointDefenseKm`. Id vuoto = le armi dell'Aquila; un id di contatto = la portata della **sua classe** se l'Aquila la
ha classificata (nebbia di guerra), altrimenti zeri. Sono i numeri che il codice di tiro usa davvero (la tabella delle classi,
o ciò che uno scenario ha messo sulla nave).

### 6.8 Cosa deve fare il lead

1. **Menti**: chiamare `group_order` dalle menti dell'ammiraglio e dei comandanti (Mandato) e dei comandanti alleati (ASTRA), leggere
   `_mandate.{your_groups,enemy_groups,group_events}` e `_astra_groups`, e fare reagire le menti agli eventi. Il codice si regge da sé
   se la mente non parla (i riflessi del §5).
2. **Effetti visivi** (F2.4): `ConsumeDeathEvents()` ogni frame (rottura: asse e punto; reattore; relitto), `GetDamageView()` per scudi
   a esagoni per faccia (`ShieldFlash`, `LastHitLocal`), sezioni che bruciano/perdono aria.
3. **Timone dell'Aquila**: moltiplicare la velocità per `PlayerEngineFactor()`; le **squadre dei danni**: chiamare
   `RepairPlayerSystems(Amount)` quando lavorano.
4. **Bilanciamento**: col nuovo modello l'apertura è una battaglia pari (vedi §7); la difficoltà va tarata sul gioco vero
   (con le menti e con il Capitano), non sul banco.

## 7. Risultati del banco

*Misurati il 30/9 e l'1/10/2026 col banco senza grafica (`tools/war.py`, commandlet `AstraWarSim`, `-nullrhi`), sul ramo del
modulo GUERRA con main unito (le navi v3 comprese), all'ultimo commit di questa sezione. Ogni riga dice quanti semi e con che
scarto: "vantaggio dei superstiti" = navi da guerra vive (o uscite dal teatro) di ASTRA meno quelle del Mandato, media sui semi ±
errore standard; sotto 2σ una differenza non è una prova. "(a/m/p)" = semi in cui ASTRA era avanti / il Mandato avanti / pari. Tutto
si rifà coi comandi del §5.8 (i semi sono 1…N e le due parti dello stesso scenario vedono gli stessi numeri casuali: un confronto
cambia una cosa sola). Le misure di tempo sono prese su un Mac condiviso con altri lavori: dove variano, si dice.*

### 7.1 L'apertura: prima e dopo (12 semi, `tools/war.py batch --seeds 12`, 900 s dal contatto)

Stessa battaglia d'apertura (Aquila + Praetorian + Vigilant contro Acheron + tre Styx + Lethe, otto caccia contro sei Harpy),
nessun ordine del Capitano, nessuna mente. "Prima" è la simulazione a valori unici e IA vecchia (commit b6cfce2: solo la
strumentazione del banco); "dopo" è il ramo a questo commit.

| | prima | dopo |
|---|---|---|
| esito per seme (ASTRA avanti / Mandato avanti / pari) | 0 / 12 / 0 | **1 / 7 / 4** |
| vantaggio dei superstiti | −2,08 ± 0,28 | **-0,83 ± 0,28** |
| scorta ASTRA viva (su 2) | 0,3 ± 0,7 | **2,0 ± 0,0** |
| navi del Mandato vive (su 5) | 0,1 ± 0,3 | 2,6 ± 0,9 |
| scafo dell'Aquila a fine prova (media) | 44 % ± 43 | **68,0 % ± 11,3** |
| caccia ASTRA persi (su 8) | 6,6 ± 2,2 (5,4 alla difesa di punto) | **0,0** |
| costo per tick della battaglia | 0,008 ms | 0,024 ms |

**La partenza era bimodale**: in 4 semi su 12 l'Aquila usciva intatta (96–100 %), negli altri era distrutta o a meno del 10 % (la
scorta ASTRA moriva in 10 semi su 12), quindi la media dello scafo diceva poco. "Dopo" le battaglie si assomigliano e sono
**pari**: senza che il Capitano faccia nulla, l'Aquila resta in media a due terzi di scafo, la scorta sopravvive e il Mandato perde due
navi su cinque. Con l'ordine `attack` sull'Aquila a tutti i gruppi del Mandato dal secondo 5 (12 semi): scafo dell'Aquila **79,2 % ± 13,2**, scorta ASTRA viva 1,9 su 2, Mandato 2,6 su 5 (vantaggio dei superstiti -0,83 ± 0,23).

I dati dal vivo del lead (un gruppo d'attacco che distrugge l'Aquila 5 minuti dopo l'arrivo, con la mente appesa per 3) non si
riproducono nel banco. Quel che il banco mostra è dove l'Aquila è fragile: la **poppa**. Il reattore dell'Aquila sta nella sezione
di poppa: due Acheron a 5 km la mettono fuori in 18 s da poppa contro 51–58 s dalle altre facce (§7.4). Una nave che mostra la poppa
al nemico senza che il timoniere la giri o il tattico sposti gli scudi è il suo punto debole; i valori (`facing_armour`,
`shield_alloc`, `systems` dell'`aquila` in `data/war/classes.json`) vanno tarati sul gioco vero, con le menti e il Capitano.

### 7.2 Simmetria (nessuna parte deve vincere sempre)

Le stesse forze a parti invertite (il Mandato è la parte ASTRA ruotata di mezzo giro); il vantaggio dei superstiti deve essere
zero entro l'errore. Con l'ordine di creazione delle navi invertito (`*_rev`) un difetto che seguisse quell'ordine cambierebbe di segno.

| scenario | semi | ASTRA avanti / Mandato avanti / pari | vantaggio dei superstiti | differenza dei velivoli persi |
|---|---|---|---|---|
| sym_small: 1 Acheron + 2 Styx | 96 | 47 / 43 / 6 | +0,22 ± 0,17 | +0,0 ± 0,0 |
| sym_small_rev (Mandato creato per primo) | 96 | 47 / 48 / 1 | +0,07 ± 0,17 | +0,0 ± 0,0 |
| sym_medium: 2 Acheron + 4 Styx | 96 | 44 / 51 / 1 | -0,29 ± 0,24 | +0,0 ± 0,0 |
| sym_two: due gruppi da 3 | 96 | 51 / 45 / 0 | +0,12 ± 0,22 | +0,0 ± 0,0 |
| sym_two_rev (Mandato per primo) | 96 | 44 / 51 / 1 | -0,09 ± 0,22 | +0,0 ± 0,0 |
| sym_air: portaerei con 8 caccia e 6 bombardieri | 48 | 22 / 22 / 4 | -0,12 ± 0,25 | +0,0 ± 0,5 |
| sym_air_rev (Mandato per primo) | 48 | 21 / 22 / 5 | -0,21 ± 0,27 | +0,3 ± 0,6 |
| sym_fighters: soli caccia | 48 | 0 / 0 / 48 | +0,00 ± 0,00 | -0,2 ± 0,7 |

Tutti zero entro 2σ, in entrambi gli ordini di creazione: nessun lato vince sempre e nessun difetto segue l'ordine. (I soli caccia
non affondano navi: tutti pari; le perdite di velivoli sono uguali.)

### 7.3 Cosa vale ogni comportamento (A/B: spento o cambiato per la sola parte ASTRA)

Stesso scenario, il comportamento spento (o cambiato) per ASTRA contro il controllo dove entrambe hanno tutto: un numero negativo
= senza quel comportamento ASTRA va peggio (il comportamento vale). 96 semi per i simmetrici, 48 per i disuguali.

| | sym_small (3 + 3) | sym_medium (6 + 6) | sym_two (2 × 3) | asym_3to2 | asym_2to1 |
|---|---|---|---|---|---|
| controllo: tutto acceso per entrambe (vantaggio dei superstiti) | +0,22 ± 0,17 (47/43/6) | -0,29 ± 0,24 (44/51/1) | +0,12 ± 0,22 (51/45/0) | +5,04 ± 0,10 (48/0/0) | +5,88 ± 0,05 (48/0/0) |
| aggiramento automatico **acceso** (spento per default) | +0,22 ± 0,17 (47/43/6) | -0,79 ± 0,22 (33/62/1) | +0,12 ± 0,22 (51/45/0) | +5,10 ± 0,11 (48/0/0) | +5,85 ± 0,05 (48/0/0) |
| fuoco: ognuno il più vicino, nessuna concentrazione | -0,64 ± 0,19 (28/68/0) | -0,99 ± 0,26 (31/62/3) | -1,05 ± 0,29 (30/65/1) | +5,00 ± 0,11 (48/0/0) | +5,92 ± 0,04 (48/0/0) |
| fuoco: minaccia/sforzo con margine di avvicinamento | -0,60 ± 0,16 (23/62/11) | -2,32 ± 0,14 (1/90/5) | +0,79 ± 0,29 (48/40/8) | - | - |
| fuoco: minaccia/sforzo con la portata di adesso | -0,74 ± 0,14 (13/64/19) | -1,82 ± 0,15 (3/88/5) | +0,23 ± 0,29 (43/49/4) | - | - |
| salve coordinate di missili **spente** | +0,07 ± 0,15 (45/49/2) | -1,36 ± 0,22 (25/71/0) | -0,39 ± 0,20 (40/54/2) | - | - |
| rotazione delle navi battute **spenta** | -0,02 ± 0,17 (46/41/9) | -0,82 ± 0,22 (33/62/1) | -0,44 ± 0,21 (38/56/2) | +5,08 ± 0,10 (48/0/0) | +5,88 ± 0,05 (48/0/0) |
| ritirata automatica **spenta** | +0,03 ± 0,19 (48/45/3) | -0,49 ± 0,25 (45/50/1) | -0,22 ± 0,26 (52/43/1) | +5,04 ± 0,10 (48/0/0) | +5,88 ± 0,05 (48/0/0) |
| distanza d'ingaggio × 0,7 | +0,02 ± 0,16 (45/49/2) | +0,17 ± 0,23 (51/43/2) | +1,28 ± 0,16 (74/20/2) | - | - |
| distanza d'ingaggio × 1,25 (5 km) | +0,42 ± 0,17 (58/34/4) | +0,10 ± 0,23 (50/44/2) | -2,15 ± 0,13 (7/88/1) | - | - |

Lettura:

- **Concentrare il fuoco** (la regola per valore e vulnerabilità contro "ognuno spara al più vicino"): vale da 0,6 a 1,0 navi in
  tutti e tre i simmetrici (−0,64, −0,99, −1,05 senza). Le regole "minaccia per unità di sforzo" (modi 2 e 3) fanno peggio in
  3 + 3 e 6 + 6 (da −0,6 a −2,3: scelgono i cacciatorpediniere di coda, che la prima fila non raggiunge) e meglio con due gruppi da 3
  (+0,8 e +0,2): nessuna vince ovunque, la regola per valore è la migliore o la seconda in tutti. Con le portaerei (§7.6) il "più
  vicino" fa meglio (+1,3): il valore di classe manda il fuoco sulla portaerei invece che sulla scorta che la copre.
- **Salve coordinate di missili**: nulla in 3 + 3; vale 1,4 navi in 6 + 6 e 0,4 con due gruppi: serve dove c'è una difesa di
  punto da saturare. Prima di un difetto corretto durante il lavoro (le navi vedevano le celle pronte solo dopo averle già
  sparate, e il controllo non scattava mai) l'interruttore non cambiava nulla.
- **Rotazione delle navi battute**: nulla in 3 + 3, vale 0,8 in 6 + 6 e 0,4 con due gruppi.
- **Ritirata automatica** (il riflesso di un gruppo senza mente): da 0 a 0,5 navi, mai negativa.
- **Distanza d'ingaggio**: il default (circa 4 km) è a un punto dove ×0,7 o ×1,25 non cambiano più di ±0,4 in 3 + 3 e 6 + 6; con
  due gruppi da 3 chiudere vale +1,3 e tenere 5 km costa 2,2 navi. La storia è più netta: con la prima versione del gruppo, che teneva la
  distanza massima della rotaia (7 km), un gruppo che chiudeva a 2,8–4 km guadagnava da 0,5 a 2 navi su 6 contro uno che teneva 7 km
  (e poi, scendendo ancora, fino a +2,4 e +2,9 a 2,0 km contro 4): chi tiene il massimo lascia indietro metà del cuneo. La distanza è la
  **leva principale** del combattimento: il default è una distanza media, la mente sceglie la sua (`range_km`).
- **Aggiramento automatico**: fa peggio in 6 + 6 (−0,5 sul controllo) e uguale altrove: la nave staccata è il bersaglio di tutta la linea.
  Spento per default; resta come ordine (`flank_left`/`flank_right`).
- **Superiorità** (3 a 2 e 2 a 1): vinti 48 semi su 48 con 5,0 e 5,9 navi di vantaggio; nessun comportamento sposta nulla (il numero
  conta più di tutto).

### 7.4 Il duello: il modello dei danni su un bersaglio fermo

Due navi ferme a 5 km sparano a un bersaglio passivo, da ciascuna faccia (6 semi). Ogni cella: danno totale incassato quando il
bersaglio diventa relitto o muore (tempo in secondi). Riferimento: la simulazione a valori unici, scafo + scudi della classe.

| 2 × tiratore → bersaglio | riferimento (scafo + scudi) | prua | poppa | babordo | tribordo | dorso | ventre |
|---|---|---|---|---|---|---|---|
| acheron → praetorian | 7200 | 8992 (106 s) | 6163 (72 s) | 6923 (80 s) | 7076 (80 s) | 6885 (81 s) | 6815 (78 s) |
| acheron → acheron | 5100 | 5856 (67 s) | 4702 (54 s) | 4212 (48 s) | 4365 (52 s) | 4428 (52 s) | 4236 (50 s) |
| acheron → aquila | 4100 | 4682 (58 s) | 2228 (18 s) | 4318 (51 s) | 4316 (54 s) | 4322 (54 s) | 4511 (54 s) |
| styx → styx | 1800 | 1757 (47 s) | 1400 (31 s) | 1632 (39 s) | 1773 (45 s) | 1728 (47 s) | 1437 (35 s) |
| styx → vigilant | 1700 | 1687 (44 s) | 1475 (36 s) | 1307 (29 s) | 1343 (30 s) | 1303 (28 s) | 1387 (32 s) |
| lethe → styx | 1800 | 1778 (47 s) | 1531 (35 s) | 1687 (41 s) | 1632 (39 s) | 1531 (35 s) | 1632 (39 s) |

La prua è la faccia più forte (scudi e corazza più grossi); i fianchi e il dorso valgono 0,6–0,9 del riferimento per le navi grosse e
quasi il riferimento per le piccole; la poppa è debole per l'Aquila (reattore a poppa). I cacciatorpediniere stanno tra 0,65 e 1,0 del
riferimento a seconda della faccia: il modello a sei facce non fa morire le navi più in fretta, le fa morire diversamente.

### 7.5 La scala

Quindici navi e settantacinque velivoli a parte (trenta navi capitali e centocinquanta caccia, bombardieri e droni in tutto), quattro
gruppi per parte, 36 km di distanza, 900 s di battaglia; il doppio (60 + 300) per vedere il margine. Costo per tick della battaglia
(10 Hz: il passo del banco è 0,1 s), media / p95 / p99 / massimo, e dove va il tempo (media in ms):

| scenario e seme | navi + velivoli al massimo | media | p95 | p99 | max | conoscenza | gruppi | navi | velivoli | proiettili ed effetti |
|---|---|---|---|---|---|---|---|---|---|---|
| scale_30x150, seme 1 | 30 + 148 | 0,090 | 0,27 | 0,34 | 0,81 | 0,003 | 0,002 | 0,014 | **0,061** | 0,006 |
| scale_30x150, seme 2 | 30 + 148 | 0,039 | 0,19 | 0,24 | 0,40 | 0,001 | 0,001 | 0,009 | 0,021 | 0,005 |
| scale_30x150, seme 3 | 30 + 148 | 0,051 | 0,20 | 0,25 | 0,41 | 0,002 | 0,001 | 0,009 | 0,033 | 0,004 |
| scale_30x150, 3600 s | 30 + 148 | 0,038 | 0,16 | 0,33 | 0,56 | 0,002 | 0,001 | 0,009 | 0,023 | 0,002 |
| scale_60x300, seme 2 | 60 + 296 | 0,278 | 1,03 | 1,29 | 1,64 | 0,009 | 0,006 | 0,046 | **0,182** | 0,029 |
| scale_60x300, seme 1 | 60 + 296 | 0,642 | 2,4 | 3,2 | 8,8 | 0,021 | 0,022 | 0,109 | 0,389 | 0,085 |

**Obiettivo del lead: 1 ms per frame con 30 navi e 150 velivoli. Misurato: da 0,04 a 0,09 ms di media, 0,2–0,3 ms al 95° e al 99°
percentile, 0,4–0,8 ms al massimo**: un decimo del budget, e il picco resta sotto 1 ms. Col doppio di tutto (60 + 300, fuori dall'obiettivo)
la media è 0,3–0,6 ms e il 95° percentile 1–2,4 ms, con picchi rari (fino a 8,8 ms in un tick, tutto nella voce dei velivoli, su un Mac
condiviso con altri lavori: le misure di tempo variano da una prova all'altra). I velivoli sono la voce più grossa (circa mezzo
microsecondo ciascuno al tick). **Ottimizzazioni fatte con questo banco** (campionatore di macOS sul commandlet, risultati
identici seme per seme prima e dopo): la ricerca dei bersagli dei velivoli (una portata di 30 km toccava migliaia di celle della griglia: ora
scorre la lista dei velivoli nemici, che sono poche centinaia), la domanda "il Mandato ha cessato il fuoco" (una passata sulle navi per ogni
velivolo a ogni tick: ora una volta per tick), la conoscenza (le portate dei sensori calcolate una volta per osservatore) e la lista dei
contatti dell'Aquila (`GetContacts`, letta da molti schermi a ogni frame: classe ed etichetta restano in memoria finché non cambia ciò che si sa). Prima: 60 + 300
seme 1 aveva media 0,94 ms, p95 3,4, max 6,8; 30 + 150 seme 2 media 0,13, p95 0,57, max 1,7. In `perf.phases` del record il
tempo di ogni tick è diviso in conoscenza, gruppi, squadriglie, navi, velivoli, proiettili. Il lavoro di scala vero (livelli di dettaglio per ciò che è lontano
dall'Aquila, disegno a istanze) è F2.3: da lì in poi la voce da guardare è quella dei velivoli.

### 7.6 I velivoli

`sym_air`: un incrociatore con otto caccia e sei bombardieri e due cacciatorpediniere per parte (48 semi). Cosa vale il muro d'inviluppo
della difesa di punto e altre scelte:

| | vantaggio dei superstiti (a/m/p) | velivoli persi (ASTRA meno Mandato: positivo = ASTRA ne perde meno) |
|---|---|---|
| controllo (tutto acceso per entrambe) | −0,12 ± 0,25 (22/22/4) | 0,0 ± 0,5 |
| muro per i caccia ma non per i bombardieri (**il default**, `wall=3`) contro nessun muro per ASTRA | −0,19 ± 0,28 (19/26/3) | **−4,1 ± 0,5** (ASTRA perde 4 velivoli in più) |
| muro per **tutti** i velivoli, bombardieri compresi (`wall=1`) | **−2,04 ± 0,15** (2/43/3) | +4,0 ± 0,6 |
| muro solo per i bombardieri (`wall=2`) | **−2,04 ± 0,14** (1/45/2) | +1,2 ± 0,6 |
| fuoco: ognuno il più vicino (`focus_a 0`) | **+1,29 ± 0,20** (34/4/10) | −5,1 ± 0,6 |
| ritirata automatica spenta | −0,25 ± 0,28 (22/21/5) | 0,0 ± 0,5 |

I bombardieri **non devono rispettare** il muro: lo sgancio dei siluri è a 4 km, il muro sta a 3–3,4 km, ma la correzione che li tiene fuori gli
impedisce di allinearsi in tempo e non sganciano (−2 navi). I caccia e i droni sì: senza muro perdono quattro velivoli in più per lo stesso
risultato in navi. Perdite tipiche in un duello di portaerei: da 10 a 12 velivoli su 14 per parte, quasi tutti ai cannoni dei caccia, pochissimi alla difesa
di punto. Scenario dei soli caccia (48 semi): nessuna nave affondata, 0,2 ± 0,7 velivoli di differenza.

### 7.7 Il contratto dei comandanti alla prova

- **`group_order`** provato dal banco con `--at` (esempi veri nel §6.2): ordine accettato e descritto, rifiutato (parte sbagliata per chi
  ordina, gruppo o bersaglio inesistente, ordine sconosciuto, bersaglio non visto), con `for_s` che scade, con `range_km`
  (a 2,5 km il gruppo tiene davvero 2,5 km), con `formation` da sola, `group:"all"`.
- **Viste** (`tools/war.py views`): da 1,2 KB (6 navi) a 4,3 KB al massimo con 15 navi per parte in 4 gruppi (3,2 KB nella prova dei rinforzi,
  2,6 KB a fine battaglia): "pochi KB". Gli eventi arrivano coi nomi dei gruppi: ritirata, morale che cede, ricomposizione, aggiramento,
  nave persa, rinforzi, ordine scaduto.
- **Rinforzi del regista nell'apertura** (`director_beat` incursione a 100 s, rinforzi a 300 s, soccorso a 420 s; seme 5, 1050 s): nessun crash,
  i gruppi nascono e vengono nominati ("Raid group T-40", "7th Fleet picket: reinforcements arriving: T-43 (vigilant), T-44 (vigilant)"), le
  ritirate e le ricomposizioni si ripetono come gli eventi dicono; l'Aquila cade a 422 s (due gruppi nemici nuovi su un'apertura non risolta).
- **Ordini del Capitano** (`fleet_request`, cioè la strada di prima) e `mandate_tactics` con il menu dei gruppi: provati, passano dagli
  stessi ordini di gruppo.

### 7.8 Cosa resta

- Il giudizio vero (chi attacca chi, quando ritirarsi, a che distanza combattere, se aggirare) è delle menti: il banco non le ha, misura i
  riflessi e gli strumenti. Quando le menti sono cablate (§6.8) va rifatto il bilanciamento dell'apertura con loro e col Capitano.
- La poppa debole dell'Aquila e la forza dell'apertura (pari, senza il Capitano) sono valori di `data/war/classes.json`.
- Il costo dei velivoli è la prima voce se si vuole il doppio: la separazione fra velivoli e la ricerca dei bersagli si possono rendere
  più radi per i lontani dall'Aquila (F2.3).
