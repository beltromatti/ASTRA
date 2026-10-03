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
*Stato (1/10): la parte di simulazione (classi e scenari dai dati, griglia, scala 30 navi + 150 velivoli) è fatta dal modulo GUERRA (§5, §7.5); il disegno a istanze (velivoli e luci), le domande per fotogramma condivise, il tavolo olografico con 50+ contatti e gli scenari grandi giocabili (battaglia di flotta con rinforzi) sono del modulo SCALA: [SCALA.md](SCALA.md). Scritto, compilato e provato sul banco; da misurare nel gioco.*
- **Scenari dai dati** (`data/war/*.json`): classi di navi (massa, spinta, virata, scudi per faccia, corazza per
  sezione, armamento con archi e cadenze, stive di caccia), flotte, posizioni, obiettivi. Battaglie fino a ~30 navi
  capitali e ~150 caccia/droni; campagna di più battaglie.
- **Simulazione a livelli di dettaglio**: ciò che è lontano dall'Aquila si aggiorna meno spesso; griglia spaziale per le
  domande di vicinanza (difesa di punto, evitamento, bersagli); proiettili in array compatti. *(La griglia e gli array compatti ci sono; i livelli per distanza non servono: 0,1–0,3 ms a tick con 30 + 150 e col doppio, SCALA §5.)*
- **Disegno a istanze**: caccia e proiettili come istanze (ISM/HISM), niente attore per ogni oggetto; luci e particelle con
  un budget. *(Fatto: proiettili e particelle da VFX, velivoli e luci di navigazione da SCALA, [SCALA.md](SCALA.md) §3.)*
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
`sym_fighters` (soli caccia), `asym_3to2`, `asym_2to1`, `scale_30x150` (15 navi e 75 velivoli a parte), `scale_60x300` (il doppio), `fleet_battle` (una battaglia di flotta di campagna: 37 navi e un centinaio di velivoli all'inizio, sette ondate di rinforzi, fino a 71 navi e 137 velivoli insieme). Un file può avere anche `"waves"` (rinforzi: `{"at_s", "side", "group"}`, annunciati nella riga degli eventi di gruppo) e `"aquila"` (l'Aquila nella battaglia: `{"at_km", "heading", "speed", "wings"}`); nel gioco `astra.war.scenario <nome> aquila [hold|speed=|heading=|at=x,y,z]` (SCALA §9).

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
dall'Aquila, disegno a istanze) è F2.3 e non riguarda la simulazione: il disegno a istanze, le liste condivise e il tavolo sono in [SCALA.md](SCALA.md), dove si misura anche il costo di un tick con la battaglia di flotta (71 navi e 137 velivoli insieme: 0,19 ms di media, 0,27 al 95°); la simulazione non ha bisogno di livelli di dettaglio.

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
  più radi per i lontani dall'Aquila (F2.3: misurato, oggi non serve, [SCALA.md](SCALA.md) §5).


## 8. Le menti di guerra (MENTE-GUERRA: F2.2 lato mente e F2.5)

*Scritto a fine lavoro del modulo MENTE-GUERRA (1/10/2026): cosa c'è, come si prova, cosa misura il banco con la mente nel giro. I nomi nel
gioco sono in inglese; il documento in italiano. Il contratto con cui le menti agiscono è il §6; i principi sono in
[ARCHITETTURA.md](ARCHITETTURA.md) §1bis (nessun filtro sulle parole o sulle decisioni dei modelli: prompt, contesto vero, strumenti veri).*

### 8.1 In breve

Il codice di GUERRA è il **corpo** della flotta (formazioni, tiro, evasione, difesa di punto, riflessi). Qui c'è il **giudizio**. Una mente
è una chiamata a un modello (un *giro*, `pulse`) con tre cose: **cosa può sapere quella persona** (i suoi gruppi per intero, il nemico come lo
vedono i sensori della sua parte, gli eventi dei suoi gruppi, il registro di ciò che ha deciso, detto e sentito), **gli strumenti del suo
grado** e un prompt con il suo carattere e la dottrina. Niente regole di codice sulle decisioni o sulle parole.

| chi pensa | cosa vede | cosa può fare |
|---|---|---|
| **Ammiraglio del Mandato** (il comandante più anziano vivo: l'Archon Varek Solm sull'Acheron; il gioco passa il comando con `commands_the_strike_group`) | tutti i suoi gruppi, i nemici in nebbia di guerra, guerra elettronica, caccia, la sua intelligence sul Capitano | `group_order` (by `admiral`, un gruppo o `all`), `fleet_ops` (= `mandate_tactics`: missili, caccia, guerra elettronica), `decide` (= `enemy_order`: ritirata dal sistema), `transmit` (solo con un canale aperto) |
| **Comandante di un gruppo del Mandato** (il capo di ogni altro gruppo) | il suo gruppo per intero, gli altri in una riga, l'intento dell'ammiraglio | `group_order` per il suo gruppo (by `commander`), `report` all'ammiraglio |
| **Capitano alleato ASTRA** (il capo di ogni gruppo ASTRA: la Praetorian per il picchetto; chi arriva col regista) | i suoi gruppi, i nemici come li tiene la flotta (`_astra_groups`), l'Aquila e i vicini, la catena di comando, le parole del Capitano | `group_order` (by `commander`), `weapons_posture`, `say` (parla con l'Aquila sulla rete della flotta), `no_change` |
| **Il Capitano** (tramite l'XO) | la tabella della flotta nel prompt dell'equipaggio | `group_order` (by `captain`) solo se è il più anziano presente; `fleet_request` = una *richiesta* che il capitano alleato giudica |

Una chiamata dà voce a più capitani: i capitani delle altre navi di un gruppo (il comandante del Vigilant nel picchetto) parlano con la propria voce
nella stessa chiamata (`say` con `speaker`); non danno ordini al gruppo.

### 8.2 I file

| file | cosa contiene |
|---|---|
| `mind/astra_mind/war_minds.py` (nuovo) | `WarMinds`: i seggi, la cadenza, il quadro per parte, gli strumenti, la memoria comune, la catena di comando, i capitani alleati, le misure |
| `mind/astra_mind/enemy.py` | la persona sul canale aperto (`EnemyAgent`, `COMMANDERS`, `CHAIN`): ora legge lo stesso quadro e lo stesso registro dell'ammiraglio (è la stessa persona); via `plan_tactics` |
| `mind/astra_mind/director.py` | il regista v2 e Rourke (§8.7) |
| `mind/astra_mind/server.py` | l'aggancio (§8.9) |
| `mind/astra_mind/crew.py`, `tools.py` | lo strumento dell'XO (`group_order`), `fleet_request` come richiesta, la tabella della flotta nel prompt |
| `mind/astra_mind/models.py` | ruoli `admiral`, `commander`, `talk`, `director` (il registro dei costi li conta) |
| `mind/bench/war_arena.py`, `war_mock.py`, `war_show.py`, `war_quality.py`, `war_judge.py`, `war_crew_live.py`, `war_director_live.py`, `war_scenes_live.py` | la mente nel giro, i modelli finti, il lettore dei record, la qualità degli ordini, il giudice delle parole, le prove dal vivo (equipaggio, regista, due scene: l'Aquila sotto il fuoco e la formazione) |
| `mind/bench/war_minds_unit.py`, `war_server.py`, `war_director_unit.py` | le prove offline (71, con le 106 di prima: 177) |
| `Source/ASTRA/AstraWarSimCommandlet.*` | il commandlet con `-mind=<cartella>` |
| `tools/war.py mind ...` | un solo ingresso per l'arena |

### 8.3 Chi pensa: i seggi e la catena di comando

Un **seggio** è una posizione di comando (`mandate/admiral`, `mandate/group/<nome>`, `astra/group/<nome>`); la persona che lo tiene è il
capitano della **nave capo** del gruppo (`leader` nella vista) e cambia quando il gioco cambia il capo: chi subentra guarda subito il quadro
con le parole «avete appena preso il comando da...» e legge il registro di chi c'era prima (la memoria è del lato, non della persona). Un gruppo
che non c'è più perde il suo seggio.

**Catena di comando ASTRA** (fatti, non verdetti: cosa significano per un ordine lo giudica il capitano). Ogni capitano ha un grado
(`RANK_ORDER`) e una precedenza; il Capitano dell'Aquila è, per nomina della Flotta, al comando tattico del picchetto di Aurelia
(precedenza 0), quindi il più anziano presente **a meno che** non sia presente un ufficiale di grado superiore (un contrammiraglio che arriva
con una forza, inventato dal regista). La catena è nel prompt di ogni capitano alleato e nella tabella della flotta dell'XO. Il capitano alleato
**obbedisce** al più anziano presente (può aggiungere una protesta o un'idea migliore; rifiuta solo ciò che non si può fare o che getterebbe la
nave per niente, dicendo perché e cosa fa invece); se chi comanda non è il più anziano presente, pesa la richiesta e può rifiutare. L'XO può
dare `group_order` (ordine diretto del Capitano) solo se il Capitano è il più anziano presente: altrimenti lo strumento risponde che si chiede
al più anziano sulla rete della flotta.

**Rourke** (`director.py`) resta il comando di flotta da lontano: risponde a ciò che è per il comando (il Capitano lo chiama, chiede aiuto),
tace se le parole erano per un capitano (la rete è condivisa: lo sa dal prompt), e può concedere rinforzi o rifornimenti (`grant`).

### 8.4 Cadenza e costo

Una mente pensa ogni **60–120 s** (periodo estratto una volta per sguardo: 80 s × 0,85–1,25 l'ammiraglio, 100 s × 0,85–1,25 un capitano
alleato), e solo se il quadro è cambiato (impronta: ordini, stati, scafi a gradini del 20 %, distanze a gradini di 4 km), oppure **sugli
eventi**: i `group_events` nuovi (la lettura aspetta 3 s che la raffica finisca, al più 8 s; minimo 20 s fra due giri per l'ammiraglio, 25 s per
un capitano), un nemico mai visto sul piano, l'Aquila che si allontana di 4 km dal gruppo dall'ultimo sguardo (l'avviso successivo ne vuole il
doppio, poi il quadruplo, fino a 8 volte; riparte quando l'Aquila torna fra le sue navi; che si avvicini è sempre una notizia), l'Aquila che
perde protezione in fretta (scudi giù di 30 punti o scafo di 8 dall'ultimo sguardo), un messaggio per lui. Il primo sguardo viene 8 s dopo
l'inizio del combattimento. I comandanti di gruppo del Mandato non hanno orologio: pensano solo per eventi del loro gruppo. **Mai due volte
insieme per la stessa persona**; un giro che non finisce in 28 s lascia il gruppo ai suoi riflessi. Una parola del Capitano sulla rete della
flotta, o una richiesta dell'XO, sveglia subito i capitani interessati (anche senza combattimento).

Un giro è **una chiamata** (più una correzione se un ordine è stato rifiutato: legge perché e lo corregge una volta; più una richiesta se il
modello ha chiuso senza alcuno strumento: «hai finito senza chiamare nulla: decidi ora», senza leggere ciò che aveva scritto). Il prompt di
sistema è lungo e stabile (carattere, dottrina), il quadro corto: la cache dei fornitori lo sconta (da 1,3 a 0,35 m$ la chiamata). Il modello
pensa ad alta voce in poche frasi e poi chiama gli strumenti (`no_change` se non c'è nulla da cambiare: una scelta, non un silenzio). Se un
giro fallisce o scade prima che il capitano abbia risposto a una richiesta del Capitano, la richiesta va alle navi come prima: non si perde.

### 8.5 Cosa legge e cosa può fare

Il quadro è testo compatto (circa 0,6–1,5 KB, 400–900 token): i gruppi propri con membri, scafo, scudi (le facce solo se una è sotto il 90 %),
missili, stato; i gruppi nemici come li tiene la parte; per il Mandato anche i caccia, le esche, l'ufficiale di guerra elettronica e le navi
ASTRA *sul suo piano* (la nebbia di guerra vale anche per lui); per un capitano alleato l'Aquila (scafo, scudi, velocità, rotta, cosa fa il
timone, e che scafo e scudi aveva al suo ultimo sguardo), le navi amiche attorno a lei, **le navi nemiche più vicine a lei con la distanza e
quali sono dentro la portata dei laser**, e i contatti con la sola direzione (qualunque può essere un'esca). Sotto: gli eventi nuovi dei suoi
gruppi, i messaggi per lui, il suo **registro** (ordini con la ragione e l'esito, parole dette e sentite sulla rete, passaggi di comando),
e per un subordinato l'intento dell'ammiraglio (la `reason` dell'ultimo ordine). Gli strumenti sono quelli della tabella del §8.1; il
codice li esegue come comandi del gioco (`group_order` con `side` e `by` aggiunti, la `reason` tolta) e rifiuta solo ciò che il grado non
permette (un comandante ordina il suo gruppo, non un altro).

### 8.6 Il Capitano e la sua flotta

- **Richiesta** (l'ufficiale alle comunicazioni, `fleet_request`): non va più alle navi ma al capitano alleato, come parole (`The Captain
  asks...`); lui giudica, ordina il suo gruppo e risponde per radio (un'assenso, o il perché non può). Se la nave nominata non ha un capitano
  con una mente, o se il modello non risponde, la richiesta va alle navi come prima (`fleet_request` del gioco): non si perde mai.
- **Ordine diretto** (l'XO, `group_order`, by `captain`): vale subito, solo se il Capitano è il più anziano presente; il capitano è
  avvisato (lo legge nel registro e nel quadro: `order in force ... by captain`) e non lo disfa se non per forza maggiore.
- **Parole del Capitano sulla rete** (canale `fleet`, o a una nave): il router decide cosa esce; i capitani alleati lo sentono tutti e ognuno
  giudica se era per lui (il più anziano risponde per la flotta; Rourke tace se erano per una nave). Le risposte escono come voci radio
  (priorità «risposta»: passano avanti ai rapporti).
- **I capitani parlano da soli** (pochi messaggi, brevi, utili: lo dice il prompt, nessun filtro): un avviso che il Capitano può aver perso,
  una richiesta, ciò che stanno facendo e lo riguarda (l'Aquila si è allontanata dal picchetto e lo dicono), una perdita. Gli alleati si
  parlano fra loro con `say` a un altro capitano (che si sveglia, e il Capitano sente). Una riga rimasta troppo in coda la ripensa chi
  doveva dirla (`rethink`). Il prompt chiede la riga più corta: il nominativo e solo ciò che per il Capitano è **nuovo** (non il suo ordine, la
  formazione tenuta, la distanza, né ciò che ha già detto).
- **L'Aquila sotto il fuoco** (dalla prima battaglia vera col gioco: il gruppo d'attacco chiude a 2–3 km e senza il Capitano la uccide in circa 4,5
  minuti, e la Praetorian non si concentra sugli attaccanti): il capitano alleato si sveglia quando gli scudi o lo scafo dell'Aquila calano in fretta
  (30 punti di scudo o 8 di scafo dall'ultimo sguardo: `AQUILA_SHIELD_DROP`, `AQUILA_HULL_DROP`, al più ogni 25 s), il quadro gli dice cos'erano al
  suo ultimo sguardo e quali navi nemiche le sono più vicine (e quali dentro la portata dei laser), e il prompt gli dice di agire subito senza
  aspettare la parola del Capitano — sparare su chi la colpisce o farle schermo — e di dirlo in una riga. Provato dal vivo su una scena (§8.10).
  La leva del Capitano è l'XO: «picchetto, attacca l'Acheron a 3 km» è un `group_order` diretto (§8.1).

### 8.7 Il regista v2 (F2.5)

`director.py`, senza atti: via `act`, `act_beats`, `ACTS`; resta il capitolo (`arc`) che si chiude con la battaglia decisiva, che il regista
sceglie quando la guerra ha radunato le due parti, non per un contatore. Legge il **polso**, fatti e non verdetti, calcolati dal codice
dallo stato (`Director.observe` a ogni stato, `pulse_facts`): la **tensione** (minuti di combattimento e di pace negli ultimi 20, il
combattimento in corso e quanti combattimenti di fila dall'ultima vera pace di 3 minuti), la **stanchezza del Capitano** (minuti di sessione,
da quanto è sotto pressione, scafo, scudi, missili, calore, perdite, incidenti aperti, gli ultimi beat con quanto tempo fa), l'**equilibrio**
(forze sul piano per classe, chi tiene cosa nella March con le minacce); più il registro della campagna, il tavolo e i **fili aperti** (`threads`:
ciò che ogni parte sta facendo o radunando, le promesse, i misteri; li riscrive a ogni beat e li salva con la storia).

Cosa può fare: i beat di prima (`raid`, `distress`, `reinforcements`, `resupply`, `calm`, `transit`, `investigate`, `decisive`, `war_news`) più
**`none`** (la guerra corre, con la ragione) e **`negotiation`** (un comandante del Mandato già sul piano chiama l'Aquila: `caller`, `terms`;
il server apre il canale dal suo lato col percorso di `transmission:` e la sua mente dice la sua parte; nessun numero cambia). I **rinforzi**
sono di **entrambe** le parti: `reinforcements` è la 7th Fleet (ogni nave con un `captain` inventato: nome, grado, bio, sesso → una voce e una
mente, `WarMinds.register_ally`), `raid` è la seconda ondata del Mandato (con il suo `commander`); in una battaglia in corso arrivano con un
ritardo di 2–7 minuti (visibili sui sensori), mai come un salvataggio. **Mai numeri truccati**: nessun beat cambia le navi già nella
battaglia; durante un combattimento il codice lascia passare solo `reinforcements`, `raid`, `negotiation`, `none` (le regole del mondo, non
un filtro sulle parole: un transito in mezzo ai cannoni non esiste). Uno sguardo alle **battaglie lunghe**: dopo 150 s di combattimento e
poi ogni 4 minuti (`battle_due`, `battle_pulse`), a bassa spesa, il regista può aggiungere ciò che la guerra porterebbe, o niente.

### 8.8 Il banco con la mente nel giro (`mind/bench/war_arena.py`, `tools/war.py mind`)

```
tools/war.py mind --scenario sym_small --seeds 1-8 --minds mandate --no-ops --model live --budget 0.1
tools/war.py mind --opening --jump 160 --seconds 450 --minds astra --model live --captain "200:fleet:Praetorian, concentrate on the Acheron;260:request:T-02:cover_us"
tools/war.py mind --scenario sym_small --seeds 1-8 --minds mandate --no-ops --model close --range 4.5     # il comandante a copione (nessuna spesa)
cd mind && .venv/bin/python -m bench.war_show <tag> <seed> [--content] [--prompts]      # i giri, gli ordini e le parole di un record
cd mind && .venv/bin/python -m bench.war_quality <tag> [--seeds 1-8]                     # la qualità degli ordini di un gruppo di battaglie
cd mind && .venv/bin/python -m bench.war_judge <tag> <seed>                              # un modello giudica le parole dei capitani alleati
cd mind && .venv/bin/python -m bench.war_scenes_live                                     # due scene col modello vero: l'Aquila sotto il fuoco, la formazione
```

I riflessi contro i riflessi (il termine di paragone) si fanno con `tools/war.py batch --scenario sym_small --seeds 24 --exec "astra.war.tune
shield_scale 1.5;astra.war.tune armour_scale 1.5;astra.war.tune struct_scale 1.8"`.

Il commandlet con `-mind=<cartella> [-mind_dt=0.5] [-mind_speed=1]` si ferma ogni `mind_dt` secondi di battaglia, scrive `s_<k>.json` (le
viste `_mandate` e `_astra_groups`, i contatti dell'Aquila, i conteggi, gli eventi e i risultati dei comandi del giro prima) e aspetta
`r_<k>.json` (i comandi dati dalle menti, eseguiti con `ApplyCommand`, e se qualcuna sta ancora pensando). **Finché una mente pensa il mondo
corre a tempo reale** (non aspetta un modello che ci mette secondi, come nel gioco); altrimenti corre al massimo. L'arena è il «gioco»: usa le
stesse funzioni Python (`WarMinds.feed`, gli stessi prompt e strumenti), con il tempo di battaglia come orologio. `--model close` è un
comandante a copione (attacca la nave più preziosa e malconcia a una distanza fissa): stima cosa può fare l'interfaccia degli ordini, a
costo zero; `--model live` è il modello vero (`--budget` ferma la spesa). `--no-ops` toglie all'ammiraglio del Mandato missili, caccia e
guerra elettronica (lo scontro equo contro le menti ASTRA, che non li hanno). `--captain` è un Capitano a copione (parole sulla rete,
richieste, ordini diretti, a tempi di battaglia). `--range` e `--formation` dicono al comandante a copione che distanza e che formazione
ordinare, `--reissue` che ripeta l'ordine a ogni sguardo, `--formation-doctrine` accende la formazione nella dottrina dei modelli veri (§8.10). Lo
scenario base è con la durezza di main (`astra.war.tune shield_scale 1.5;
armour_scale 1.5; struct_scale 1.8`, default dell'arena: `--tune ""` per quella del ramo).

### 8.9 L'aggancio al server (`mind/astra_mind/server.py`)

Tutte le modifiche a `server.py` (nient'altro è toccato fuori dai file del modulo, a parte `crew.py` e `tools.py` per l'XO):

- `GameShip(send, intercept=...)` e `execute(name, args, by, direct=False)`: dei comandi della plancia due passano prima dalla mente,
  `fleet_request` (la richiesta dell'ufficiale comunicazioni va al capitano alleato come parole: `Mind._fleet_request`) e `group_order`
  (l'ordine diretto dell'XO, solo se il Capitano è il più anziano: `Mind._captain_group_order`). Le menti dei comandanti usano `direct=True`
  (`Mind._war_execute`): vanno dritte alle navi.
- `Mind.__init__`: crea `WarMinds` (`self.war`) con `_ally_say` (la voce radio dei capitani alleati), il canale aperto, l'intelligence sul
  Capitano e `director.note`; `ASTRA_WAR_MINDS=0` le spegne (i gruppi combattono sui riflessi, come prima), `ASTRA_WAR_FORMATION=1` accende la formazione nella dottrina; `enemy.war`, `director.war_minds` e
  `director.negotiate` (`_negotiate`: il regista fa chiamare l'Aquila da un comandante del Mandato).
- Stato della nave (`ship_state`): `Mind._war_look(state)` = `director.observe(state)` (il polso della storia), `war.feed(state)` (le menti
  guardano la battaglia e avviano i giri dovuti), `_fleet_board` nello stato (la tabella della flotta per l'XO, che `crew.bridge_now` porta con
  l'ultimo messaggio del turno). Un difetto in questa lettura è contenuto (registrato, mai propagato): non taglia l'equipaggio dalla nave.
- Via `enemy_tactics` (il vecchio ciclo del Mandato ogni 40 s): lo sostituisce l'ammiraglio.
- `story_watch`: lo sguardo del regista alle battaglie lunghe (`battle_due`/`battle_pulse`).
- Parole del Capitano: `_to_party` e `hail` verso `fleet` o una nave alleata passano a `war.captain_to_fleet` e `war.kick()`;
  `_can_answer` conta anche i capitani alleati.
- `war.reset()` a ogni nuova sessione e a ogni ripresa della campagna; `EXTERNAL_SPEAKERS` conosce i capitani del picchetto (gli altri si
  registrano quando arrivano).

### 8.10 Misure (1/10/2026; durezza di main: scudi 1,5, corazze 1,5, strutture 1,8; `deepseek/deepseek-v4.1-flash`, provider together/modal)

**Come si legge.** «Vantaggio» = navi sopravvissute a fine battaglia (ritirate comprese) della parte considerata meno quelle dell'altra, su
semi uguali; «± » è l'errore standard. «Mente / riflessi / pari» sono i semi vinti dalla parte con la mente, dall'altra, e i pari. Il termine
di paragone giusto è **la stessa parte coi soli riflessi** (stessa durezza, stessi semi, stessa durata), non lo zero: nei banchi con la
durezza di main la parte creata per seconda è in vantaggio anche senza menti.

**I riflessi contro i riflessi con la durezza di main** (`tools/war.py batch ... --exec "astra.war.tune shield_scale 1.5;..."`):

| scenario | semi | ASTRA / Mandato / pari | vantaggio di ASTRA |
|---|---|---|---|
| sym_small (ASTRA creata per prima) | 24 | 6 / 16 / 2 | **−0,58 ± 0,21** |
| sym_small, 1200 s invece di 600 | 24 | 6 / 16 / 2 | −0,67 ± 0,23 |
| sym_small_rev (Mandato creato per primo) | 24 | 13 / 6 / 5 | **+0,33 ± 0,18** |
| sym_small coi valori del ramo (durezza di prima) | 24 | 13 / 11 / 0 | +0,00 ± 0,32 |
| sym_two | 16 | 3 / 6 / 7 | −0,31 ± 0,23 |
| sym_medium | 16 | 9 / 5 / 2 | +0,31 ± 0,49 |

**Trovato per strada, da guardare** (non è di questo modulo): con la durezza 1,5/1,5/1,8 **il vantaggio segue l'ordine di creazione** — nel
sym_small la parte creata per seconda vince di circa mezza nave su tre (il segno si rovescia con `sym_small_rev`), mentre con la durezza di
prima i due lati erano pari (§7.2). Nel gioco le navi di ASTRA nascono prima del Mandato: se il difetto è nel mondo (l'ordine in cui le navi
sono servite in un tick: scudi, danni) il Mandato parte con mezza nave di vantaggio. Le misure qui sotto ne tengono conto (si confronta sempre
con la stessa parte senza mente).

**Il margine dell'interfaccia** (comandante a copione, costo zero, 8 semi, 600 s, sul lato del Mandato: «attacca la nave più preziosa e
malconcia a una distanza fissa e tienila finché serve»; mostra cosa può dare lo strumento degli ordini, non cosa dà un modello):

| scenario | distanza ordinata | mente / riflessi / pari | vantaggio della mente | contro i riflessi (Δ) |
|---|---|---|---|---|
| sym_small | 3,2 km | 2 / 3 / 3 | −0,25 ± 0,46 | −0,83 |
| | 4,2 km | 5 / 2 / 1 | +0,12 ± 0,45 | −0,46 |
| | **4,5 km** | **7 / 0 / 1** | **+0,88 ± 0,12** | **+0,30** |
| | 4,8 km | 5 / 1 / 2 | +0,38 ± 0,35 | −0,20 |
| | 5,5 km | 4 / 4 / 0 | 0,00 ± 0,35 | −0,58 |
| sym_small, lo stesso ordine ripetuto a ogni sguardo | 4,5 km | 7 / 0 / 1 | +0,88 ± 0,12 | +0,30 (ripetere non costa nulla) |
| sym_medium | 3,2 km | 6 / 2 / 0 | +0,50 ± 0,43 | +0,81 |
| | 4,5 km | 3 / 3 / 2 | −0,25 ± 0,52 | +0,06 |
| sym_two | 3,2 km | 6 / 1 / 1 | +1,00 ± 0,47 | +0,69 |
| | 4,5 km | 0 / 7 / 1 | −2,25 ± 0,39 | **−2,56** |
| asym_3to2, sulla parte più debole | 3,2 km | 0 / 6 / 0 | −4,33 ± 0,19 | (il numero vince) |

Lo stesso comandante a copione **sul lato di ASTRA** (la parte creata per prima: coi riflessi sta −0,58 ± 0,21), sym_small, 16 semi: il picco è lo
stesso (4,5 km) e il guadagno sui riflessi è maggiore.

| distanza ordinata | mente / riflessi / pari | vantaggio della mente | contro i riflessi (Δ) |
|---|---|---|---|
| 3,2 km | 6 / 7 / 3 | −0,12 ± 0,33 | +0,46 |
| 4,2 km | 8 / 7 / 1 | −0,12 ± 0,30 | +0,46 |
| **4,5 km** | **12 / 3 / 1** | **+0,44 ± 0,26** | **+1,02** |
| 4,8 km | 8 / 7 / 1 | −0,31 ± 0,35 | +0,27 |

Il modello vero dalla parte di ASTRA (+1,14 ± 0,28, sotto) arriva dove arriva il comandante a copione col suo numero migliore (+1,02 ± 0,33).

La **distanza è la leva**, e dipende da quante navi combattono insieme: un gruppo piccolo ha un picco netto a 4,5 km (appena oltre i 4 km dei
laser: solo rotaie e missili; 4,2 e 4,8 ne cedono quasi tutto), due gruppi o sei navi vogliono 3,2 (a 4,5 la coda di una formazione profonda non
raggiunge il bersaglio e si perde più di due navi). Le tre costanti di `war_minds.py` (`LASER_KM`, `SMALL_GROUP_KM`, `DEEP_GROUP_KM`) vengono da
qui: **se cambiano le armi o la durezza, rifare lo scorrimento** (`tools/war.py mind --scenario sym_small --seeds 1-8 --minds mandate --no-ops
--model close --range 4.2`, e così via) e aggiornarle; il testo della dottrina le segue.

**La formazione è la seconda leva** (stesso comandante a copione sul lato del Mandato, 8 semi, la formazione `line` ordinata insieme all'attacco; i
riflessi tengono il cuneo):

| scenario | formazione e distanza | mente / riflessi / pari | vantaggio della mente | contro i riflessi (Δ) |
|---|---|---|---|---|
| sym_small | cuneo, 4,5 km | 7 / 0 / 1 | +0,88 ± 0,12 | +0,30 |
| | **linea, 3,2 km** | **8 / 0 / 0** | **+1,50 ± 0,18** | **+0,92** |
| | linea, 4,0 km | 5 / 2 / 1 | +0,25 ± 0,39 | −0,33 |
| | linea, 4,5 km | 0 / 8 / 0 | −1,38 ± 0,17 | −1,96 |
| | colonna, 4,5 km | 0 / 8 / 0 | −2,25 ± 0,15 | −2,83 |
| sym_two | cuneo, 3,2 km | 6 / 1 / 1 | +1,00 ± 0,47 | +0,69 |
| | **linea, 2,8 km** | 8 / 0 / 0 | **+2,50 ± 0,35** | **+2,19** |
| | linea, 3,2 km | 8 / 0 / 0 | +2,12 ± 0,28 | +1,81 |
| | linea, 3,6 km | 7 / 0 / 1 | +2,00 ± 0,31 | +1,69 |
| | linea, 4,5 km | 2 / 5 / 1 | −1,00 ± 0,53 | −1,31 |
| sym_medium | cuneo, 3,2 km | 6 / 2 / 0 | +0,50 ± 0,43 | +0,81 |
| | linea, 2,8 km | 8 / 0 / 0 | +2,38 ± 0,25 | +2,69 |
| | **linea, 3,2 km** | 8 / 0 / 0 | **+2,38 ± 0,17** | **+2,69** |
| | linea, 3,8 km | 8 / 0 / 0 | +1,75 ± 0,23 | +2,06 |
| | linea, 4,5 km | 8 / 0 / 0 | +1,88 ± 0,21 | +2,19 |
| sym_small, lato ASTRA (16 semi) | cuneo, 4,5 km | 12 / 3 / 1 | +0,44 ± 0,26 | +1,02 |
| | linea, 4,5 km | 3 / 10 / 3 | −0,75 ± 0,27 | −0,17 |

Una **linea di fronte che chiude a circa 3 km** è l'ordine più forte che il banco abbia trovato fra pari (circa una nave su tre, e da due a due e
mezza su sei): tutte le navi stanno alla stessa distanza dal nemico e tutte le armi battono, mentre il cuneo dei riflessi ne tiene metà fuori dal
tiro. Tenuta a 4,5 km la stessa linea perde (con tre navi o con due gruppi), e la colonna è la peggiore forma per combattere (le navi dietro non
sparano mai). **Il prezzo è il ritmo**: se entrambe le parti ordinano la linea a 3,2 km (comandante a copione da tutte e due, 16 semi sym_small) il
bilancio resta pari (ASTRA 4 / Mandato 2 / pari 10: +0,12 ± 0,26) ma il combattimento è quasi il doppio più sanguinoso: dopo 600 s sopravvivono 2,0
navi su 6 (coi riflessi 3,9; col cuneo a 4,5 km da tutte e due 3,1), e 3,75 su 12 nei due gruppi (coi riflessi 7,2). Per questo la dottrina con la
formazione è un **interruttore spento** (`WarMinds.formation_doctrine`, `ASTRA_WAR_FORMATION=1`, `--formation-doctrine`): il lead decide, giocando,
se vuole battaglie così. Col modello vero e l'interruttore acceso (sym_small, mente sul Mandato) 6 semi su 6 (§ sotto): 11 ordini d'attacco su 12 sono
«linea a 3,2 km».

**Il modello vero** (stessi semi e durezza; `--no-ops`: l'ammiraglio del Mandato ha solo gli ordini di gruppo, come le menti ASTRA; la mente di
ASTRA nei banchi simmetrici è un «ammiraglio del banco» sopra tutti i suoi gruppi (`--astra-admiral`: le navi dei semi non hanno capitani con un
nome), con la stessa dottrina; i capitani alleati veri, Castellan e Okoro, si provano nell'apertura):

| prova | semi | mente / riflessi / pari | vantaggio della mente | stessa parte coi riflessi | contro i riflessi (Δ) | spesa |
|---|---|---|---|---|---|---|
| sym_small, mente su ASTRA (creata per prima) | 16 | **11 / 2 / 3** | **+0,56 ± 0,18** | −0,58 ± 0,21 | **+1,14 ± 0,28** | 0,054 $ |
| sym_small, mente sul Mandato (creato per secondo) | 16 | 11 / 3 / 2 | +0,50 ± 0,25 | +0,58 ± 0,21 | −0,08 ± 0,33 | 0,059 $ |
| sym_small, menti su entrambe (ASTRA − Mandato) | 12 | 6 / 5 / 1 | +0,08 ± 0,34 | −0,58 ± 0,21 | +0,66 ± 0,40 | 0,088 $ |
| sym_two, ammiraglio + comandante del 2° gruppo (Mandato) | 8 | 4 / 1 / 3 | +0,88 ± 0,41 | +0,31 ± 0,23 | +0,57 ± 0,47 | 0,097 $ |
| sym_two, con «conta le navi che combattono insieme» | 8 (6 validi) | 4 / 3 / 1 | +0,50 ± 0,47 | +0,31 ± 0,23 | +0,19 ± 0,52 | 0,080 $ |
| sym_medium, 6 navi in un gruppo (Mandato) | 8 | 5 / 3 / 0 | +0,62 ± 0,58 | −0,31 ± 0,49 | +0,93 ± 0,76 | 0,045 $ |
| sym_small, mente sul Mandato, **con la formazione in dottrina** (`ASTRA_WAR_FORMATION=1`) | 6 | **6 / 0 / 0** | **+1,67 ± 0,19** | +0,58 ± 0,21 | **+1,09 ± 0,28** | 0,022 $ |
| *prima della taratura (dottrina «chiudi e finisci», 4,5–5 km)*: mente su ASTRA | 8 | 5 / 2 / 1 | +0,38 ± 0,30 | −0,58 | +0,96 | 0,026 $ |
| *idem*, mente sul Mandato | 8 | 3 / 4 / 1 | −0,25 ± 0,49 | +0,58 | −0,83 | 0,034 $ |
| *idem*, menti su entrambe (ASTRA − Mandato) | 8 | 2 / 2 / 4 | −0,12 ± 0,33 | −0,58 | +0,46 ± 0,39 | 0,060 $ |

Lettura onesta. **La mente dà una parte vera ma modesta**: dalla parte di ASTRA (quella in svantaggio nel banco) porta i semi vinti da 6 su
24 a 11 su 16 e mezza nave in più su tre di quanto i riflessi non lasciassero (+1,1 ± 0,3: 4σ); dalla parte del Mandato nel sym_small (già
avanti di 0,6 senza mente) conserva il vantaggio senza accrescerlo; nei due gruppi e nelle sei navi i guadagni vanno nel verso giusto ma entro
l'errore (+0,6 ± 0,5; +0,9 ± 0,8). Con menti dalle due parti **nessuna parte vince sempre** (6 / 5 / 1 e prima 2 / 2 / 4). Gli ordini della
prima dottrina costavano mezza nave dal lato del Mandato: la taratura della distanza (e il «non chiudere su un pari») ha cambiato il segno.
Il banco misura il giudizio **di battaglia fra pari senza Capitano né guerra elettronica**, contro riflessi decenti, con 3 navi per parte:
non risolve differenze di un decimo di nave e non vede le cose per cui la mente c'è davvero (nebbia di guerra, esche, missili, il Capitano
che parla, la successione). Il paragone vero lo darà il gioco.

**Qualità degli ordini** (`bench.war_quality`, dai fatti registrati: nessuna lettura delle parole del modello):

| prova | ordini | accettati / rifiutati | rifiuto ripetuto | ritirate sensate / dubbie | ordini rovesciati in 20 s | `no_change` |
|---|---|---|---|---|---|---|
| sym_small Mandato (16 semi) | 53 | 52 / 1 | 0 | 3 / 0 | 0 | 61 % |
| sym_small ASTRA (16 semi) | 41 | 41 / 0 | 0 | 3 / 2 | 1 | 65 % |
| sym_small menti su entrambe (12 semi) | 82 | 81 / 1 | 0 | 11 / 0 | 3 | 50 % |
| sym_two (8 semi, ammiraglio + comandante) | 110 | 107 / 3 | 0 | 4 / 0 (+4 non valutabili) | 17 | 27 % |

5 rifiuti su 286 ordini: quattro volte un bersaglio morto un attimo prima («'A-01' is not a hostile warship on your plot»: il modello corregge
una volta nello stesso giro, tre volte con successo; la quarta nominò il gruppo del bersaglio morto e riuscì al giro dopo) e una volta un
ordine senza il campo `order`. Mai lo stesso ordine impossibile due volte; ritirate quando il gruppo era il più debole o il morale cedeva
(«dubbie» = si è ritirato un gruppo più forte con il morale intatto: 2 casi su 16 semi, tutti di una stessa mente ASTRA). Nei due gruppi 17
ordini su 110 sono ordini di un comandante che completa o rimpiazza quello dell'ammiraglio nei 20 s successivi (spesso lo stesso ordine con la
distanza che l'altro non aveva dato): è il prezzo di due menti sullo stesso piano. Metà dei giri finisce con `no_change` ragionato («l'ordine
in vigore serve»): una scelta, non un silenzio.

**Costo e latenza** (giri veri, tutti i giri senza errore delle prove sopra; il prompt di sistema, lungo e stabile, sta nella cache del fornitore):

| chi pensa | giri | per giro | all'ora di battaglia | giro intero: mediana / p90 / max | primo strumento (mediana) | token in / out per giro |
|---|---|---|---|---|---|---|
| un ammiraglio (m1, m2: una parte con la mente) | 261 | 0,42–0,45 m$ | **0,02 $** | 0,8–1,1 / 2,0–2,5 / 3,5–13,2 s | 0,7–1,0 s | 2,6–2,8 k / 150–180 |
| due ammiragli (uno per parte) | 206 | 0,43 m$ | 0,046 $ | 0,8 / 2,0 / 9,6 s | 0,7 s | 2,7 k / 170 |
| ammiraglio + comandante del secondo gruppo | 197 | 0,81–0,82 m$ | 0,064–0,073 $ | 2,0 / 3,0 / 5,6 s | 1,2–1,3 s | 3,6 k / 320 |
| un gruppo di sei navi | 84 | 0,53 m$ | 0,029 $ | 1,5 / 2,5 / 4,1 s | 1,2 s | 3,1 k / 205 |
| il capitano alleato dell'apertura (con un Capitano a copione) | 31 | 0,73 m$ | 0,054 $ | 2,4 / 3,0 / 4,0 s | 1,5 s | 4,6 k / 290 |
| apertura, entrambe le parti (ammiraglio, comandante, capitano alleato) | 106 | 0,70–0,90 m$ | 0,09–0,17 $ | 1,1–1,5 / 2,5 / 4,1 s | 0,9 s | 4,1–4,5 k / 250–330 |

Tutte le menti di guerra di una battaglia costano **da 0,02 a 0,17 $ l'ora** (l'obiettivo era 1 $ l'ora per tutte, equipaggio compreso: con
l'equipaggio a 0,76 $ l'ora misurati dal lead nel gioco vero dopo la divisione del prompt, la somma sta fra 0,78 e 0,93 $ l'ora). Alle chiamate
dell'equipaggio le menti di guerra aggiungono solo la tabella della flotta dell'XO (120 token col picchetto, 300 nella battaglia più grande, nell'ultimo
messaggio: da 1 a 3 % di una chiamata); le loro righe radio non fanno parlare l'equipaggio (sono eventi del contesto, non turni). Il caso peggiore possibile (quattro comandanti di gruppo del Mandato e due capitani ASTRA, tutti
svegliati al ritmo minimo consentito, 25 s, per un'ora intera, a 0,8 m$ a giro, più l'ammiraglio ogni 20 s) è di circa 0,8 $ l'ora: il ritmo
minimo è un limite, non quel che succede (nelle prove un giro ogni 45–80 s per mente). Nessun giro è scaduto (28 s) in nessuna prova (tranne i giri del tetto di spesa, scartati); il
peggiore ha impiegato 13 s (un fornitore lento: il client ritenta una volta sul secondo, mai in parallelo, per un primo token oltre i 5 s).

**L'apertura, i capitani alleati e un Capitano a copione** (`--opening --jump 160`, l'Aquila sui riflessi: parole sulla rete della flotta a 175 s,
una richiesta alla Vigilant a 235 s, una domanda a 300 s, un ordine diretto a 385 s, un'esortazione a 450 s):

- **La capitana alleata** (Castellan, con Okoro che parla per la Vigilant) ordina il picchetto al primo contatto (`screen` sull'Aquila a 4,5 km o
  `attack` sul Lethe) e lo dice in una riga («Praetorian and Vigilant in screen on you, holding four point five. One contact, the Lethe, closing
  from two hundred»); risponde alle parole del Capitano in 1–3 s con i numeri veri (scudi e missili di entrambe le navi: «Shields full, twelve
  missiles in the cells. Vigilant full, six»); la richiesta indirizzata alla Vigilant la prende di solito Okoro con la sua voce («Already between
  you and them, four point five, holding»); un ordine diretto del Capitano su un bersaglio già morto viene rifiutato dal gioco e lo si vede nel
  registro; quando l'ordine diretto è valido lo esegue anche se avrebbe scelto altro e lo dice in una riga («On the Acheron at four point five,
  closing now. The three Styx are breaking off»); la regola «dissentire non è rifiutare» è nata da una prova in cui un ordine diretto era stato
  disfatto un secondo dopo.
- **Il dato del lead dell'1/10** (con i soli riflessi gli alleati restano in formazione mentre l'Aquila avanza e non la seguono né la avvisano):
  qui l'Aquila sui riflessi si allontana (7, 12, 18, 24 km in 90 s) e la capitana lo dice a ogni salto («You have drawn to 7 km and my screen is
  no longer between you and the Acheron group: closing back onto your engaged side. If you mean to open the range, say so and I will conform»),
  ricompone l'arco (`screen` di nuovo) e, a 24 km, passa a impegnare il gruppo nemico («my screen is a formality at that gap»); a scafo zero offre
  il soccorso e chiede un faro. Ripeteva l'avviso troppo spesso (4 in 90 s): ora la soglia raddoppia a ogni avviso (fino a 8 volte) e riparte
  quando l'Aquila torna fra le sue navi (prove nel banco unitario).
- **Giudice** (`bench.war_judge`, `openai/gpt-oss-120b`, un'altra famiglia dei capitani che sono DeepSeek; punteggi da 1 a 5 e «avrebbe taciuto»;
  rumoroso: lo stesso testo può prendere voti diversi, serve a scoprire difetti, non a classificare), righe delle prove:
  prima serie (3 semi, 24 righe) utilità 3,2, brevità 3,3, verità 3,9, carattere 4,6, tempestività 3,9, «avrebbe taciuto» 2 su 24;
  dopo le correzioni dei prompt (2 semi validi, 19 righe) **utilità 4,1, brevità 3,3, verità 4,6, carattere 4,7, tempestività 4,5**, «avrebbe
  taciuto» 1 su 19 (una riga sull'Aquila a scafo zero, artefatto del banco). Righe al minuto: 0,7–1,7 con un Capitano che parla cinque volte in
  otto minuti e un'Aquila che scappa (da un terzo alla metà sono risposte a lui). La brevità resta il punto debole (due o tre frasi: «a bit wordy for radio»).
- **L'ammiraglio del Mandato nell'apertura**: il primo sguardo (8 s dopo l'inizio, 168 s) cade **prima** che il gruppo d'attacco arrivi (170 s)
  e vede solo il Lethe (forza 0,3 contro 2,8, morale 0,09): a quel punto l'ammiraglio è Hale. Nelle prime prove (3 semi) ordinò il ritiro del
  Lethe e `decide: withdraw` («il combattimento è perso prima di cominciare»), e in un seme su tre chi subentrò (Solm) tenne il ritiro: il gruppo
  d'attacco se ne andò senza combattere. Dopo i prompt («il primo sguardo è un quadro parziale», «chi subentra giudica da capo», `decide` è la
  decisione di un ammiraglio battuto) due semi validi su quattro (gli altri due sono stati troncati dal tetto di spesa): in uno Hale tiene il
  Lethe a 4,5 km «per vedere cosa è davvero il nemico: non lo butterò via al primo sguardo»; nell'altro ordina ancora il ritiro (il gioco risponde
  «own ship only (1 ship)»: tocca la sola fregata); in entrambi Solm, subentrato, combatte («Hale ordered a withdrawal on a picture of one broken
  frigate: I judge afresh on mine») e, dove serve, annulla il ritiro a 250 s (`continue_attack`). **È una trappola vera dell'apertura**: chi la
  rivede nel gioco guardi il registro dell'ammiraglio nei primi 180 s.
- **L'Aquila sotto il fuoco** (`bench.war_scenes_live`, scena a copione col modello vero, 0,23 m$; il banco non può farlo da sé perché la sua Aquila
  regge, e la richiesta del lead dopo la prima battaglia vera era proprio questa): l'Aquila passa da 100 %/100 % a 61 %/8 % in 35 s, T-21 a 2,4 km e
  T-22 a 3,1 km da lei, il picchetto a 6 km. La capitana si sveglia per «the Aquila is losing her shields or hull fast», ordina `attack` su T-21 a 3,2 km
  («Aquila's shields are down and her hull is falling to T-21 and T-22 at knife range: close on the Acheron») e dice, con tono urgente: «Aquila,
  Praetorian: closing on the Acheron and the Styx on your bow, engaging at 3 km. We are coming between you and them.» Con la formazione in dottrina
  (un'altra scena) l'ammiraglio del Mandato al primo sguardo di tre navi contro tre ordina `attack` su A-01 a 3,2 km in formazione `line`.

### 8.11 Limiti, e cosa chiede al resto

- **Il giudizio vero si prova nel gioco.** Il banco misura battaglie fra pari, 3–6 navi per parte, senza Capitano né il resto dello spazio, contro
  riflessi decenti; i margini sono di mezza nave e non risolvono differenze di un decimo. Quello per cui le menti ci sono (nebbia di guerra, esche,
  missili, il Capitano che parla, la successione, le parole degli alleati) si vede giocando, con la voce. Il banco non ha lo strato della nave (calore,
  condotti): la sua Aquila regge più di quella vera, quindi «l'Aquila sotto il fuoco» si prova solo in una scena a copione (§8.10).
- **Le costanti della dottrina sono fisica del momento** (§8.10): portata dei laser, distanze di 4,5 e 3,2 km. Se cambiano armi o durezza, rifare lo
  scorrimento col banco. Il testo dice «le rotaie a 8–10 km, i laser a 4»: viene da `data/war/classes.json`.
- **La formazione è una leva che il modello usa bene e che cambia il ritmo** (§8.10): con la linea a 3,2 km da entrambe le parti si perde il doppio
  delle navi nello stesso tempo. È spenta di default; la decisione è del lead, che sa che ritmo vuole.
- **La durezza di main ha reso il banco di simmetria dipendente dall'ordine di creazione** (§8.10): da guardare nel mondo di GUERRA (non è di questo
  modulo). Finché non è chiarito, ogni confronto va fatto con la stessa parte senza mente.
- **Gli eventi di gruppo sono testo**: la mente di un comandante di gruppo del Mandato si sveglia sugli eventi il cui testo comincia col nome del
  gruppo (`group_events[].text`); se il C++ cambia il formato la mente smette di svegliarsi per quel gruppo (l'ammiraglio non dipende da questo).
- **Due menti sullo stesso piano si rimpiazzano gli ordini** (ammiraglio e comandante di gruppo: 17 ordini su 110 nei due gruppi, spesso lo stesso
  ordine con la distanza che l'altro non aveva dato). Non ha fatto danni nelle misure; se nel gioco disturba, il prompt del comandante può dire che
  un ordine in vigore dell'ammiraglio non si rimpiazza ma si completa o si riferisce.
- **Il giudice delle parole è un modello** (di un'altra famiglia, rumoroso, un campione di 43 righe): scopre difetti, non classifica. Nei banchi
  l'Aquila è sui riflessi e a scafo zero «si allontana»: le righe su un'Aquila morta sono un artefatto del banco, non dei capitani.
- **Brevità**: le parole dei capitani alleati erano di due o tre frasi (il giudice: «a bit wordy for radio»); la regola «solo ciò che è nuovo per
  il Capitano» le accorcia (una prova dal vivo: righe di una o due frasi, il nominativo e la notizia), ma la voce lunga si sente.
- **La tabella della flotta nel prompt dell'equipaggio**: quella dell'XO (120 token con il picchetto, 300 nella battaglia più grande) viaggia con
  l'ultimo messaggio del turno (`crew.bridge_now`) e mai nel prompt di sistema: la cache del fornitore copre il resto, come ha voluto il lead.
- **Due prove di `bench.npc_server` falliscono anche su main** (`test_nobody_near_nobody_asked`, `test_the_officers_are_told_the_captain_is_among_the_crew`):
  il testo di `npc.py` è cambiato (il gioco decide chi sente il Capitano) e la prova no. Non sono di questo modulo.
- **Niente prova nel gioco vero**, con la voce, il Capitano che comanda l'Aquila e gli errori della rete: è il passo del lead.

### 8.12 Integrazione (passi esatti)

1. **Unire il ramo** `worktree-agent-adfe3daf93e51bd02`: contiene già due unioni di main (la seconda con la divisione del prompt dell'equipaggio
   di aa68778: la tabella della flotta è in `bridge_now`). Se main è andato avanti, conflitti possibili solo in `crew.py` e `tools.py` (si tengono
   entrambi i lati: la `crew_locate` e i `LOOKUPS` di main, il `"group_order"` dell'XO nostro); `director.py` è riscritto (prendere il ramo);
   `docs/GUERRA.md` riceve solo questo §8.
2. **Nessuna modifica al C++ del gioco**: cambia solo il commandlet del banco (`Source/ASTRA/AstraWarSimCommandlet.*`, `-mind=<cartella>`, e ora
   anche gli scudi dell'Aquila nello stato). Per usare il banco: ricompilare l'editor (`Build.sh`, già provato sull'unione) e `tools/war.py mind ...`.
3. **Variabili** (`.env` o ambiente): `ASTRA_WAR_MINDS=0` spegne le menti (i gruppi tornano ai riflessi, la richiesta del Capitano alle navi come
   prima); `ASTRA_WAR_FORMATION=1` accende la formazione nella dottrina (§8.10); `ASTRA_MODEL_ADMIRAL`, `ASTRA_MODEL_COMMANDER`, `ASTRA_MODEL_TALK`,
   `ASTRA_MODEL_DIRECTOR` (`modello@fornitore1,fornitore2`) cambiano il modello di un ruolo; `ASTRA_UE_CMD` dà il percorso dell'`UnrealEditor-Cmd` al
   banco (Windows).
4. **Manopole** in `war_minds.py`: `PERIODIC_S`, `MIN_GAP_S`, `FIRST_PULSE_S`, `SEPARATION_KM`, `AQUILA_HULL_DROP`, `AQUILA_SHIELD_DROP`, `SETTLE_S`,
   `QUIET_END_S`, `PULSE_TIMEOUT_S`, e le costanti fisiche della dottrina (`LASER_KM`, `SMALL_GROUP_KM`, `DEEP_GROUP_KM`, `LINE_KM`); in `director.py`:
   `BATTLE_PULSE_FIRST_S`, `BATTLE_PULSE_EVERY_S`, `CALM_AFTER_S`, `IN_BATTLE_BEATS`.
5. **Cosa guardare nel gioco**: il registro del server (`astra.war_minds`) ha una riga per giro (chi, durata, costo, motivi, strumenti), e
   `war.summary()` i totali; nei primi 180 s dell'apertura il registro dell'ammiraglio del Mandato (§8.10); le voci radio dei capitani alleati con il
   loro nome (Castellan, Okoro) e quelle dell'ammiraglio solo a canale aperto; l'Aquila sotto il fuoco (la capitana che chiude sugli attaccanti e lo
   dice); l'XO che dà `group_order` («XO, il picchetto attacchi l'Acheron a 4,5 km»); una richiesta alle comunicazioni («cover us» alla Vigilant) che
   torna come risposta del capitano; Rourke che tace se le parole erano per una nave.
6. **Prove offline**: `cd mind && .venv/bin/python -m unittest bench.stations_unit bench.stations_server bench.npc_unit bench.npc_server
   bench.voice_units bench.war_minds_unit bench.war_server bench.war_director_unit` (181 prove, nessuna rete; due di `npc_server` falliscono anche su
   main). Dal vivo (pochi decimi di centesimo l'una): `python -m bench.war_crew_live`, `python -m bench.war_director_live`,
   `python -m bench.war_scenes_live`.

## 9. La guerra della campagna a scala di flotte (CAMPAGNA, il lead, 2/10)

Il motore regge una battaglia di flotta (SCALA) e le menti pensano per gruppi (MENTE-GUERRA), ma la campagna restava piccola: il regista
dimensionava le incursioni a 1–4 navi e i rinforzi a 1–2 cacciatorpediniere, con tagli nel codice a 8 navi. Ora:

- **Forze in gruppi di battaglia** (`groups` in un beat `raid`, `reinforcements` o `decisive`): ogni gruppo ha nome, formazione (`wedge`,
  `line`, `column`, `screen`), navi con il capo per primo (al più 10), stormi delle sue portaerei (`wings`: `carrier` = indice della nave,
  `kind` fighter/bomber/drone, `n`, `mission`), il suo posto (`offset_km`: verso l'Aquila e alla sua destra, dal punto d'arrivo del beat) e il
  suo obiettivo (`goes_for`: `aquila`, `escorts`, `gate`, o un contatto). Al più 40 navi per beat (`MaxBeatShips`). Il Mandato entra al buio con la
  nebbia di guerra (scoperto dai sensori), la 7th Fleet è sul piano. Gli id dei contatti seguono l'ordine dei gruppi (il capo di ogni gruppo per
  primo): la mente dà a ogni capo del Mandato il suo `commander` (una mente e una voce) e a ogni nave alleata il suo `captain`
  (`Director._register_groups`). Un beat può arrivare in un punto fisso (`at_m`, metri nel sistema: la bocca del Janus Gate).
- **Il regista a scala di flotte** (`director.py`): incursioni da un gruppo (2–6 navi) a vere forze (10–30), la 7th Fleet che risponde con gruppi,
  la battaglia decisiva di 20–40 navi contro la flotta radunata; la guerra cresce per la sua logica (sonde e incursioni prima delle forze, forze
  prima dell'assalto); mai truccare. Una campagna nuova comincia con i fili `OPENING_THREADS` (la flotta d'interdizione del Mandato si raduna
  oltre il Gate; la 7th Fleet tiene New Ravenna). Dal vivo (`bench.war_director_live`, 0,007 $): una prima sonda da 4 navi, un rifornimento dopo una
  vittoria, `none` in una battaglia che va da sola.
- **L'apertura cresce in una battaglia di flotta** (`TickScenario`, terza fase): 330 s (`VanguardAfterS`) dopo il gruppo d'attacco di Solm il
  Janus Gate si attiva; 50 s dopo l'**avanguardia della flotta d'interdizione** esce dalla bocca del Gate in tre gruppi (la portaerei Nyx con 8
  caccia e 4 bombardieri e una Styx di scorta, T-31–T-32; la linea di Styx di Ferryman Ilse Dorn, T-33–T-36; il cuneo di Lethe di Ferryman Cael
  Morrow, T-37–T-38; comanda Warden Sabine Thale, sotto Solm nella catena); la Flotta annuncia il **gruppo di battaglia Constance** (la Praetorian
  ASN Constance di Captain Ines Aldana, T-03, e tre Vigilant con il loro stormo, T-04–T-06), che arriva da New Ravenna 170 s dopo. Non dopo una
  resa o sotto una tregua. Provato con la mente: 11 ostili e 6 amici, caccia, siluri, incendi a bordo (fino a 16), ~0,3 $/ora, 60 fps con gli
  aiutanti fermi.
- **Il timone tiene la distanza** (`keep_on_bow` con `standoff_km`) e ha la **retro-spinta** (fino al 30 % della velocità piena,
  `UAstraShipSubsystem::ReverseThrottlePct`): frena da 480 m/s in tempo e indietreggia se il bersaglio entra.

Prove nel gioco senza mente: `astra.cmd director_beat {'beat':{'type':'raid','delay_s':5,'range_km':45,'bearing_deg':60,'groups':[...]}}`;
l'apertura intera in pochi minuti: `astra.battle.time 170`, poi `astra.battle.time 510` (la terza fase parte subito).

## 10. La March: la guerra a scala di campagna (CAMPAGNA F2.6, helper CAMPAGNA, 3/10)

La richiesta dell'utente, alla lettera: la guerra «più grande, di strategia e lunga… come una partita di scacchi blitz, ma con durata di ore»,
con «macrostrategie e sottostrategie, sottosquadre, tattiche di gruppo reali», «più peso alle decisioni del Capitano», «un regista onnisciente che
non si vede… senza spostare le sorti in favore di qualcuno». Dalle sue partite del 2/10: la guerra era troppo veloce (il primo gruppo d'attacco battuto in
sei minuti, un'incursione «già a distanza di coltello», l'Aquila distrutta da otto navi in cinque), i nemici comparivano e morivano senza essere visti.

### 10.1 In breve

- **Due livelli di dettaglio.** Il sistema dove sta l'Aquila è la **simulazione vera** (C++: le menti tattiche, il Capitano, 60 fps). Tutti gli altri
  sistemi dell'Aurelia March (11 in tutto) sono la **March** (`mind/astra_mind/march.py`): flotte di navi vere (classe, nome, scafo, rifornimenti, stormi, comandante), 11
  ordini, Gate, nebbia di guerra, cantieri, depositi, assedi, volontà dei popoli; le sue battaglie le risolve un **modello di battaglia taratato sul banco
  della guerra** (28 esperimenti della simulazione vera). Una flotta che arriva dove sta l'Aquila diventa le navi che ha davvero (`director_beat`) e
  quello che le accade torna nella flotta (scafi, perdite, fughe, volontà dei popoli): non esistono due guerre.
- **Due menti strategiche con strumenti veri** (`strategy.py`, ruolo `strategy`, DeepSeek V4.1 Flash): il Vice Admiral Adrian Rourke (ASTRA) e l'Archon
  Isolde Skarn (il Mandato) leggono ciò che il loro comando può leggere e muovono le flotte (`fleet_order`, `split_fleet`, `merge_fleets`, `set_build`,
  `set_plan`, `assess`, `parley`; Rourke anche `tell_captain`, `task_aquila`, `send_tender`). Il codice non filtra mai ciò che decidono: solo meccanica.
- **Il regista è onnisciente e non vede**: vede la guerra com'è (`director_view`), non può creare forze né spostare un sistema raccontandolo; può solo dare il
  ritmo con fatti veri (`start_beat` calm/investigate/negotiation/none, `war_news`, `reveal`, `pressure`). Le forze sono della March e arrivano al passo della March.
- **Ritmo.** Le forze arrivano da lontano (la bocca del Gate, ≥ 85 km), a colonna, con l'avviso del Gate e i minuti che servono per raggiungere l'Aquila; chi comanda
  sa sempre il piano del suo comando e cosa sta arrivando (`field_brief`). Una prima apertura giocata dalla March (opzionale, vedi 10.7) toglie l'ultimo arrivo
  a distanza di coltello (il gruppo d'attacco a 25 km dopo 170 s).
- **Costo**: ~0,0017 $ a occhiata (3.200 token in, 180 out); 0,03–0,05 $/ora a regime, 0,062 $/ora nell'apertura più movimentata misurata (18 occhiate in 30
  minuti, due menti): sotto il tetto di 0,1 $/ora. Con `ASTRA_STRATEGY_MINDS=0` le flotte vanno sui riflessi (costo zero).

### 10.2 I file

| File | Cosa |
|---|---|
| `mind/astra_mind/march.py` | la March: mondo, flotte, ordini, Gate, nebbia (tracce), cantieri, assedi, volontà, pace, quadro per le menti (`picture`, `field_brief`), tavolo olografico (`holo`), apertura giocata dalla March (`march_opening`) |
| `mind/astra_mind/march_battle.py` | il modello di battaglia (Lanchester a gruppi di fuoco, scudi, missili contro difesa puntuale, stormi, ritirate per assetto, fuga per velocità di virata, fortuna); 35 costanti in `march_calibration.json` |
| `mind/astra_mind/march_data.py` | i dati (nessun numero nel codice): classi, sistemi, ordine di battaglia (5 flotte ASTRA, 8 del Mandato), nomi, persone, `PACE`, `MARCH_OPENING` |
| `mind/astra_mind/march_auto.py` | i riflessi (`AutoAdmiral`): "safety" (le menti sono in servizio) e "full" (nessuna mente: banco, guerra mentre il Capitano è perso, mente caduta) |
| `mind/astra_mind/strategy.py` | le due menti: cadenza, quadro, strumenti, diario, `rourke_reply`, costo |
| `mind/astra_mind/march_glue.py` | la colla con la simulazione vera (10.6) |
| ganci additivi | `server.py` (`_start_march`, `_rourke_say`, `_march_news`, `_war_first`, `ASTRA_OPENING`), `director.py` (il regista onnisciente), `war_minds.py` (`strategic`: il piano del comando ai comandanti sul campo), `war.py` (il `WarMap` non cambia proprietari/minacce che la March non ha deciso), `crew.py`, `models.py` |
| banchi | `bench/march_unit.py` (46), `strategy_unit.py` (29), `march_glue_unit.py` (42), `march_server.py` (13), `march_soak.py` (1), `march_pace.py` (2), `march_sim.py`, `march_live.py`, `march_mock.py` |
| strumenti | `tools/march.py` (`sim`, `live`, `pace`, `cal`, `test`), `tools/march_calibrate.py`, `data/march/cal_cpp.json` |

### 10.3 Le regole del mondo (tutte in `march_data.py`/`PACE`: un designer le cambia senza toccare il codice)

- **Mappa**: Concordia (capitale ASTRA), Meridian, Aurelia, Cassia, Veyra (delle Gilde Libere: chiusa alle navi da guerra, nessuno vi combatte), Thule, Ophir, Erebus,
  Nemet, Niflheim, Kharon (capitale del Mandato); in ogni sistema due zone, il Gate (Keeper Station e i suoi cannoni) e il mondo (pianeta e cantieri).
- **Gate**: un salto = 95 s + 4 s a nave (×1,3 se la flotta corre al buio), 25 s per riformarsi all'uscita; l'apertura del Gate si vede 75 s prima dell'arrivo da un
  posto d'ascolto nel sistema (non se la flotta è al buio). Ordini e notizie viaggiano per i Gate: 8 s + 20 s a salto dal comando (Aurelia per ASTRA, Erebus per il Mandato).
- **Ordini** (11): `hold`, `move`, `defend`, `assault`, `raid`, `blockade`, `reinforce`, `escort`, `withdraw`, `recon`, `refit`; assetto `bold`/`steady`/`cautious`,
  posizione `gate`/`world`, `dark`. Una flotta non si divide e non si riunisce in battaglia o in un Gate (`split_fleet`/`merge_fleets`: le sottosquadre).
- **Nebbia di guerra**: ogni parte legge le proprie flotte esattamente e quelle nemiche per **tracce** (età, stima, livello 1 conteggio / 2 classi / 3 identificata);
  un posto d'ascolto vede la propria zona e sente i Gate che si aprono; `reveal` del regista dà una traccia vera.
- **Cantieri e depositi**: ogni sistema fa punti-flotta all'ora (`set_build` sceglie la classe); i depositi riparano (~15 minuti per una nave a metà) e
  riforniscono solo le flotte di casa. **Assedi**: il tempo cresce col valore del sistema (`siege_s` 420–2400 s); un sistema di nessuno si rivendica in 420 s.
- **Volontà dei popoli**: ASTRA 0,78, Mandato 0,86 all'inizio, usura ~0,058/ora, −0,004 per punto-flotta perso, +0,0015 per punto distrutto; sotto 0,30 un governo vuole la pace
  (`parley`). La guerra finisce se cade una capitale, se la volontà di un popolo si spegne, o per armistizio di entrambi.
- **Cosa non esiste**: la sorte decisa dal regista; un cambio di proprietario o di minaccia che la March non abbia prodotto (`WarMap.update` lo rifiuta).

### 10.4 Il modello di battaglia e la taratura

Fuoco diretto e missili contro difesa puntuale con **gruppi di fuoco** (la concentrazione vince, la dispersione perde navi), scudi che tornano e scafo, stormi (caccia,
bombardieri, droni), difensore e fortificazioni, ritirata per assetto **solo dopo il contatto**, nave sotto il 27 % di scafo che se ne va, tempo di fuga per velocità di
virata (una corazzata che volta le spalle tardi non scappa), fortuna per battaglia. 35 costanti libere, trovate con una ricerca a coordinate (`tools/march.py cal fit`)
contro i **28 esperimenti della simulazione vera** (`data/march/cal_cpp.json`: due flotte a 30 km, 24 battaglie ciascuno, in entrambi gli ordini di creazione).

| Misura (modello contro simulazione vera) | Valore |
|---|---|
| perdita della ricerca (60 battaglie a esperimento, seme 7) | 73,5 |
| perdita su estrazioni nuove (200 battaglie, semi 1–3) | 93–95 (3,4 a esperimento) |
| stesso vincitore | 22–23 esperimenti su 28 |
| errore medio sulle navi rimaste al vincitore | 0,8 navi |
| errore medio sul tempo di decisione | ~130 s (la simulazione vera: 285–900 s, tipico 450–530) |

Limite onesto: la taratura è su scontri di 3–30 navi senza l'Aquila; la ricerca si adatta un poco al suo campione (73,5 → 94 su campioni nuovi). Due prove del modello
(`test_the_model_matches_the_war_bench`, `test_a_beaten_fleet_breaks_off_and_the_slow_are_caught`) custodiscono ciò che la taratura ottiene.

### 10.5 Le menti strategiche

- **Chi**: Vice Admiral Adrian Rourke (ASTRA, `key admiral`) e Archon Isolde Skarn (Mandato, `key skarn`: «una flotta è una cosa finita da spendere solo dove prende
  un Gate»). Il quadro (`March.picture(side)`) è ciò che quel comando può sapere: le proprie flotte esatte, le tracce nemiche con la loro età, le notizie arrivate (in
  ordine di ricezione: i Gate consegnano fuori ordine), il piano e il diario di ciò che ha deciso, la volontà dei popoli; per Rourke anche dove sta l'Aquila, a che
  distanza dal Gate e che cosa le ha chiesto il Capitano.
- **Cadenza**: una prima occhiata a 420 s **o appena un Gate si apre verso il cielo dell'Aquila** (o un fatto grave), poi per notizie (peso ≥ 2, dopo 6–15 s perché
  una raffica si legga insieme, mai più spesso di 75 s) e ogni ~330 s (×0,85–1,25) solo se il quadro è cambiato; le parole del Capitano a Rourke sono immediate
  (un'occhiata in corso si annulla e ricomincia con le sue parole). Fino a due giri di modello per occhiata (`assess`, un rifiuto, nessuna chiamata).
- **Strumenti**: ogni risposta dice cosa la flotta farà (rotta, tempo, cosa si sa del posto) o perché non può; `assess` dà la stima dello stato maggiore con le regole
  della guerra, **non vieta nulla**. Una flotta giocata dal gioco (con l'Aquila) non si muove sulla mappa: l'ordine resta sul suo registro come intento che i suoi comandanti
  leggono (`field_brief`).
- **Fallimento**: un modello che non risponde in 45 s o tre volte di fila lascia le flotte ai riflessi "full" (nessuna spesa, la guerra non si ferma).
- **Il Capitano**: parlare a Rourke (rete di flotta) è una **occhiata** immediata con le sue parole; `task_aquila` è un ordine del servizio ad andare altrove (il Capitano
  decide, la guerra va avanti comunque); `send_tender` rifornisce l'Aquila (uno ogni quarto d'ora).

### 10.6 La colla con la simulazione vera (`march_glue.py`)

Non giudica nulla: porta fatti nei due sensi.

- **Dove sta l'Aquila**: dallo stato del Gate (nella corsia di un Gate, o arrivata in un sistema) la March sa quale sistema è reale; le flotte che il gioco giocava tornano
  sulla mappa dove stanno quando lei parte; un arrivo prende le flotte del nuovo sistema.
- **Dentro**: una flotta della March che arriva al suo sistema (dal Gate, o già presente quando lei arriva) è mandata come le navi che ha davvero, **un beat per gruppo di
  battaglia**, ogni nave con il suo scafo (`hull_pct`), missili, stormi, capitani/comandanti (da `war_minds.ALLIES` e `enemy.COMMANDERS` per chiave); al più 36 navi di
  guerra insieme (SCALA), le altre aspettano 90 s nel Gate. Una flotta ASTRA che passa soltanto non si materializza; quella del Mandato sì, sempre.
- **Fuori**: ogni secondo le viste del gioco (`_astra_groups`, `_mandate`, `contacts`, gli eventi) dicono che ne è delle navi: scafi, perdite (che pesano sul conto e sulla
  volontà), fughe (navi che escono dal sistema: una flotta di sbandati che si ritira); la battaglia vera finita chiude il capitolo (battaglia maggiore ≥ 8 perdite, capitale
  persa o valore ≥ 7: ≥ 40 min dalla precedente) e la guerra finita chiude l'arco (`_end_arc`).
- **L'apertura del gioco**: le flotte che il copione del gioco porta da sé (il picchetto, Lethe, il gruppo d'attacco, l'avanguardia, il soccorso) si **adottano** dagli id dei contatti
  dell'ordine di battaglia; una che non arriva entro 30 minuti è della mappa.
- **La guerra senza l'Aquila**: se è persa, `fast_forward` (3 ore di guerra in ~0,6 s, riflessi pieni per entrambe le parti); i bollettini della guerra lontana arrivano sul
  ponte come notizie della rete di flotta (`comms`), tenuti durante gli scontri tranne i fatti urgenti, al più uno ogni 25 s; il tavolo olografico riceve `sector.march` ogni 10 s.

### 10.7 Il ritmo: arrivi da lontano, e l'apertura giocata dalla March

Cosa è fatto (modulo mente, nel gioco com'è):

- **Mai a distanza di coltello**: ogni forza del Mandato (e ogni flotta amica che non era già lì) entra a **≥ 85 km** dall'Aquila (la bocca del Gate se il Gate è lontano:
  all'apertura è a 110 km; altrimenti spinta a 85 km e al più 120, il limite del gioco), sul rilevamento del Gate; le flotte già presenti quando lei arriva a 70 km.
- **A colonna**: le navi passano il Gate una dopo l'altra (4 s a nave): un beat per gruppo di battaglia, ognuno con il ritardo delle navi che lo precedono; una flotta di
  più gruppi non arriva tutta insieme.
- **L'avviso del Gate** dice anche i minuti: «una forza di circa 5 navi sta passando fra 75 s; il Gate è a 110 km dall'Aquila, e a 450 m/s servono circa 4 min 04 s dopo per
  raggiungerla» (avviso sul ponte, quadro di Rourke, tavolo olografico con `eta_s`). Chi comanda sul campo legge cosa sta arrivando e quando (`field_brief`).
- **Il regista non crea più incursioni**: in modalità March le forze sono solo della March (una incursione è una mossa strategica con costo e tempo di viaggio).

**L'apertura giocata dalla March** (opzionale; `ASTRA_OPENING=script` la spegne; serve una piccola modifica C++, vedi 10.11): una campagna nuova chiede al gioco di spegnere
il copione dell'apertura (`opening {"script": false}`: niente gruppo d'attacco a 25 km dopo 170 s, avanguardia e soccorso). Se risponde `ok`, le tre flotte sono della guerra:
il gruppo d'attacco di Solm sta a Thule e **parte alle 150 s** (la prima mossa del Mandato, per orologio), l'avanguardia aspetta a Thule la parola dell'Archon, il gruppo
Constance a Meridian quella dell'Ammiraglio. Se il gioco non conosce il comando o rifiuta, **non cambia nulla** (il copione resta). L'apertura, nel banco (`bench/march_pace.py`):

| | copione del gioco | giocata dalla March |
|---|---|---|
| primo avviso del Gate | nessuno per il gruppo d'attacco (l'avanguardia: a 500 s) | **~200 s** (75 s prima dell'arrivo) |
| arrivo del gruppo d'attacco | 170 s, a 25 km | ~275 s, a 106 km (bocca del Gate) |
| primi cannoni (missili a 25 km) | **170 s** | **~455 s** (7,5 minuti) |
| avviso → primi cannoni | 0 s | **255 s** (4 min 15 s) |
| soccorso | ~720 s, già deciso | quando Rourke lo manda (al primo sguardo, ~210 s: Constance da Meridian, il grosso da Cassia) |

Il gruppo d'attacco apre il canale all'arrivo (Archon Solm: 14 s dopo il passaggio, con il gruppo ancora a 4 minuti: il Capitano ha l'avvicinamento per parlare).
La prima occhiata di Rourke non aspetta i 420 s se un Gate si apre verso l'Aquila: dal vivo (10.10) dice, ~10 s dopo l'avviso, «il Gate di Aurelia si apre: circa quattro navi, due
Acheron e due Styx, fra un minuto, su di lei quattro minuti dopo. Il gruppo Constance viene da Meridian, il grosso da Cassia».

### 10.8 Il regista onnisciente (`director.py`, ganci additivi)

Con la March il regista legge `director_view()` (la guerra com'è, di entrambe le parti) e ha quattro strumenti: `start_beat` (`calm`, `investigate`, `negotiation`, `none`: niente
incursioni né rinforzi, sono della March), `war_news` (senza proprietario né minaccia: la March decide chi tiene cosa), `reveal` (solo il canale: il testo del rapporto lo scrive la
March, con i fatti veri), `pressure` (il governo di una parte chiede una cosa per un tempo: dà ritmo senza scegliere un vincitore). Non ha `transmit` né `grant`: Rourke parla
per mezzo della March (`rourke_reply`). Il regista cura il ritmo della storia (pause, trattative, rivelazioni), **mai la sorte**.

### 10.9 Il Capitano: cosa conta

Nel mondo simmetrico i riflessi danno 45/55 (ASTRA 42, Mandato 52, armistizio 26 su 120 guerre: 44,7 % ± 5,2 dei decisi); nel mondo vero la partita è asimmetrica per
costruzione (la 7th Fleet e la Home Fleet contro la flotta d'interdizione) e le scelte del Capitano pesano (`march_sim`, 60 guerre da 12 ore, riflessi per entrambe le parti):

| Capitano (stand-in) | ASTRA / Mandato / armistizio | quota ASTRA dei decisi | fine |
|---|---|---|---|
| non c'è | 41 / 9 / 10 | 82 % | 4,8 h |
| fermo (idle) | 25 / 17 / 18 | 60 % | 5,9 h (l'Aquila persa in 53 guerre) |
| una nave della flotta (fleet) | 38 / 9 / 13 | 81 % | 4,9 h |
| accorre dove c'è minaccia (defender) | 32 / 11 / 17 | 74 % | 6,0 h |
| va a colpire ciò che batte (hunter) | 32 / 13 / 15 | 71 % | 5,1 h |

Le guerre durano ore (p10 4,2 h, p90 7,0 h) e nessuna resta aperta oltre le 12.

### 10.10 Il banco e i risultati (3/10; tutto senza motore, senza rete tranne dove indicato)

- **Test** (`tools/march.py test`): 133 della March (46 + 29 + 42 + 13 + 1 + 2) e **460** della suite offline completa (`unittest discover -s bench -p "*_unit.py"`), tutti verdi.
- **Soak** (`bench/march_soak.py`: la colla contro un gioco finto che combatte, due menti a riflessi, l'Aquila che viaggia, 6 semi × 3 ore): **zero violazioni** (nessuna nave
  due volte o in due posti, nessuna del gioco ignota alla mappa, nessuna giocata mentre l'Aquila è in una corsia, perdite uguali nei due mondi), zero errori della colla.
- **Il ritmo** (`bench/march_pace.py`, 6 semi × 3 ore, riflessi: il pavimento; il gioco finto con l'avvicinamento e i danni adattati alle durate del banco):

| | copione | March |
|---|---|---|
| primo contatto (3 navi in battaglia) | 170 s | 453 s |
| avviso prima dei cannoni | nessuno | 255 s |
| scontri a partita (3 h) | 4 | 4 |
| navi perse all'ora (entrambe le parti, tutta la guerra) | 4,1 | 4,6 |
| punti di decisione del Capitano all'ora (Gate verso di lei, arrivi, offerte di pace, assedi, sistemi presi, ordini del governo) | 4,0 | 5,4 |
| tratti di quiete (> 15 min senza una scelta) all'ora | 0,89 | 0,72 |

  I riflessi soli lasciano tratti quieti lunghi (fino a 2 ore in un seme): è il pavimento. Le menti vere e il regista lo riempiono (qui sotto).
- **Dal vivo con le menti vere** (`bench.march_pace --live`, 30 minuti di guerra con l'apertura della March nel gioco finto, **0,0312 $**, 18 occhiate, mediana 1,6 s): Rourke alla
  prima occhiata (210 s) manda Constance e il grosso e avvisa il Capitano con i minuti; Skarn manda l'avanguardia e poi ritira ciò che si trova contro dodici navi; a 1.000 s
  Rourke dice che a Thule si raduna una forza di dodici navi, a 1.555 s Thule è del Mandato: 9 punti di decisione e 7 comunicazioni di Rourke in 30 minuti. Il costo
  dell'apertura è il più alto della partita: 0,062 $/ora; a regime 0,03–0,05 $/ora (prove da 1–4 ore).
- **Taratura e guerre**: vedi 10.4 e 10.9. Simmetria (120 guerre `--world sym`): 44,7 % ± 5,2. Dottrine scambiate (`--swap`): ASTRA 33, Mandato 5, armistizio 22: a decidere
  la parte è la geografia dell'ordine di battaglia, non la dottrina.

### 10.11 Limiti noti e richieste (fuori dai miei file)

Richieste al C++ (nell'ordine di quanto cambiano la partita):

1. **`dark` per beat/gruppo** (`ArriveBeat` e `ArriveGroups`: oggi un gruppo `raid` entra sempre `bFog` + `bDark`, la firma ×0,33 e si accende a 20 km: un Acheron è un rilevamento a ~20 km, uno
   Styx a ~15, cioè dentro la portata dei missili (25 km), **qualunque sia la distanza da cui arriva**). Basta `bool bDarkBeat = true; Beat->TryGetBoolField("dark", bDarkBeat); S.bDark = bDarkBeat;` (la
   March manda `dark` in ogni beat: falso per ciò che non corre al buio). Con la firma intera (`SignatureKmOf`) un Acheron è un rilevamento a ~61 km (2,3 minuti a 450 m/s) e una traccia a ~25 km, uno Styx
   a ~46 e ~19 km.
1b. **Keeper Station come sensore** (opzionale, ma è ciò che fa «vedere arrivare» per minuti): in `TickSensors` il Gate (`Landmarks[GateLandmark]`) legge come una nave ASTRA con radar attivo di ~60 km
   (`Best = Max(Best, Sense(GatePos, 60, false))`, tracce condivise per datalink come già quelle della 7th Fleet): una forza che esce dalla bocca del Gate a 110 km dall'Aquila è una traccia
   (classificata, poi identificata) per gran parte del suo volo, al buio o no.
2. **`opening {"script": false}`** (`AstraShipSubsystem::ApplyCommand` → `UAstraBattleSubsystem::SetOpeningScript`): un membro `bOpeningScript = true`; con `false` le fasi 2 e 3 di `TickScenario`
   (gruppo d'attacco, avanguardia, soccorso, le note di comunicazione) non partono; risponde `ok` solo se il copione non è già cominciato (`StageDone < 2`), altrimenti `ok: false`. La fase 1 (Lethe
   che si sveglia a 80 s, il picchetto, il mercantile) resta. Senza questo comando l'apertura resta quella del copione (alternativa minima: la fase 2 con `ScheduleOpeningForce` alla bocca del Gate
   con l'avviso del Gate 75 s prima, come già fa l'avanguardia).
3. `range_km` oltre 120 (oggi `Clamp(6, 120)`), se il Gate sta più lontano; opzionale: `engagement_active` strutturato nello stato.
4. Il **tavolo olografico** deve disegnare `sector.march` (flotte con `eta_s`, battaglie, volontà): il dato c'è, il disegno no.
5. La **durata degli scontri** è una manopola di GUERRA (danni di `classes.json`): nel banco della guerra durano 5–15 minuti (3–6 cacciatorpediniere a parte: 400–530 s), più i
   3–4 minuti di avvicinamento; se per le ore si vogliono scontri più lunghi si scala il danno, non la March. L'abbordaggio non è collegato alla March.

Limiti miei: l'**apertura giocata dalla March non è provata nel gioco** (solo contro il gioco finto, il server vero con un gioco scritto e le menti vere); il comportamento a lungo
(ore) delle menti vere è provato solo a riflessi e per 30 minuti dal vivo (il credito per le prove dal vivo si è chiuso a 0,135 $ su 0,15 $); le menti ripetono a volte la stessa
comunicazione (si tratta nel prompt, mai con un filtro); i riflessi soli lasciano quiete lunghe; MAX 36 navi di guerra insieme nel gioco; un fleet «scriptato» non prende ordini.

### 10.12 Integrazione e prova in gioco

1. `git merge worktree-agent-a64cdaf64f0a8b7c2` su `main` (nessuna dipendenza nuova, nessun asset). Interruttori: `ASTRA_MARCH=0` (il regista fa la guerra come prima), `ASTRA_STRATEGY_MINDS=0`
   (flotte ai riflessi, nessuna spesa), `ASTRA_OPENING=script` (non chiede l'apertura alla March).
2. **Senza modifiche al C++**: una campagna nuova parte con il copione (il gioco risponde «unknown command opening» e la March lo lascia fare); da lì la guerra è della March: le menti
   a cadenza, gli arrivi da lontano e a colonna, i bollettini sul ponte. Nel log (`astra-mind.log`): `the game keeps its opening script`, `the game plays …`, righe `Vice Admiral Adrian Rourke … $0.00xxx
   (…): fleet_order…`.
3. **Con le due modifiche (1 e 2 sopra)**: `the game's opening script is off: the March plays F-M1, F-M3, F-A3`; a ~190 s il bollettino del Gate («…fra 75 s; il Gate è a 110 km…»), a ~200–215 s Rourke
   che parla, a ~260 s il beat `raid` (4 navi, ≥ 85 km), ~14 s dopo la chiamata di Solm, a ~455 s i primi cannoni; il soccorso del Constance/del grosso a ~10 minuti.
4. Cosa guardare: i tempi sopra; che Rourke non si ripeta troppo (sette comunicazioni in 30 minuti in un'apertura movimentata); che le flotte che arrivano non siano mai a distanza di coltello; che il
   Capitano abbia sempre qualcosa da decidere (punti di decisione in 10.10); il costo (`tools/march.py live --hours 1 --cap 0.05`, con la chiave).
5. Comandi: `tools/march.py test` · `tools/march.py sim --seeds 1-60 --hours 12 --captain none,idle,fleet,defender,hunter` · `tools/march.py pace --hours 3 --seeds 1-6` ·
   `tools/march.py pace --live --hours 0.5 --seeds 1 --cap 0.035` · `tools/march.py cal model`.
