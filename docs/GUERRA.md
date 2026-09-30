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
sezione dove vive ogni sistema, **affusti con arco di tiro**, portata preferita. Le sei facce sono nell'ordine prua, poppa,
babordo, tribordo, dorso, ventre.

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

(I valori di scudi e struttura della simulazione sono quelli della tabella per la scala e per `struct_scale`, tarati sul banco
contro il vecchio modello a valori unici: vedi "Il duello" nel §7.) Una nave senza classe (caccia, esche) resta a valori unici.

### 5.3 I danni fisici (F2.1)

Un colpo arriva da una direzione nel riferimento della nave (il punto d'ingresso nella sfera, più una dispersione lungo lo
scafo: `hit_scatter`). Da lì:

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
preavviso; l'Aquila non si spezza mai), oppure **relitto disattivato**: niente energia, alla deriva, abbordabile in F5 (reattore
spento senza esplosione, o equipaggio che abbandona sotto il 6 % dello scafo). Un relitto colpito ancora può andare in pezzi.

**Cosa possono leggere gli altri moduli**: `GetDamageView(ContactId, FDamageView&)` — con la nebbia di guerra: dettaglio 3 per
la propria parte (tutto: sistemi, affusti, reattore), 2 per una traccia ferma e classificata (scudi per faccia, piastre e
struttura per sezione, ultimo colpo), 1 per una traccia ferma (solo sventrata/brucia/si spezza), 0 niente; `ConsumeDeathEvents()`
(come è morta, dove si è rotta, asse e punto di rottura: per gli effetti visivi); `PlayerEngineFactor()` (0–1: da moltiplicare
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
- **La distanza.** Per ogni distanza da 3 a 9,5 km il gruppo confronta il suo danno al secondo con quello del nemico vicino al
  bersaglio (ponderato dalla portata reale dei due armamenti, con un bonus piccolo per la distanza lunga) e sceglie la migliore;
  se il nemico è molto più veloce resta a 5,5 km (lo raggiungerebbe comunque).
- **Il bersaglio** (fuoco concentrato, modo 3): per ogni nemico noto, la *minaccia che toglie dal campo per unità di sforzo* =
  (il danno al secondo che può fare a noi) × (il danno al secondo che le nostre navi possono fargli **adesso**, con la portata
  vera) ÷ (scafo + scudo della faccia che ci mostra). Ogni nave segue il bersaglio del gruppo se lo raggiunge, altrimenti
  spara al più vicino che raggiunge; un incrociatore corazzato non vale più del cacciatorpediniere accanto, che muore quattro
  volte più in fretta e fa la metà del male.
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
d'inviluppo** della difesa di punto (il volo non entra nella portata di un incrociatore se non per l'attacco), rientro se
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
| `hit_scatter`, `fire_dps`, `breakup_p1`, `breakup_p2` | 0,5, 0,0015, 0,25, 0,7 | dispersione dei colpi sullo scafo; incendio (quota della struttura al secondo); probabilità di rottura |
| `focus_a/m` | 3 | bersaglio: 0 nessuna concentrazione (ognuno il più vicino), 1 regola iniziale (valore della classe e quanto è battuto), 2 minaccia/sforzo con margine di avvicinamento, **3 minaccia/sforzo con la portata di adesso** |
| `flank_a/m`, `flank_ratio` | 0, 0,9 | aggiramento automatico (spento); rapporto di forza da cui scatta |
| `saturate_a/m` | 1 | salve coordinate di missili |
| `rotate_a/m` | 1 | rotazione delle navi battute |
| `retreat_ratio_a/m` | 0,38 | soglia di morale della ritirata automatica (0 = mai) |
| `range_ai_a/m` | 1 | scala la distanza scelta dal gruppo |
| `wall_a/m` | 1 | muro d'inviluppo della difesa di punto per i velivoli |

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
                       "by":"admiral"|"commander"|"captain"|"xo", "formation":"line"|"wedge"|"column"|"screen" (facoltativo)}
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
l'evento lo dice. **`formation`** da sola cambia la formazione.

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
