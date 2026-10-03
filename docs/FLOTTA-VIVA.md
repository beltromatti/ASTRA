# Le altre navi vivono come l'Aquila — modulo FLOTTA-VIVA (F4.4)

*Documento del modulo FLOTTA-VIVA (2026-10-03). I nomi nel gioco sono in inglese; il documento in italiano. Vedi anche
[DISTRUZIONE.md](DISTRUZIONE.md) (il modello dei danni che qui gira su altre navi), [NAVE.md](NAVE.md) (le piante), [GUERRA.md](GUERRA.md)
(il colpo che arriva e i sistemi di una nave in battaglia), [SCALA.md](SCALA.md) (il costo per nave), [ABBORDAGGI.md](ABBORDAGGI.md)
(chi entra) e il brief [brief/FLOTTA-VIVA.md](brief/FLOTTA-VIVA.md).*

## 0. In breve

Fino a ieri solo l'Aquila aveva un dentro: una nave di GUERRA era tre sezioni, sei sistemi e un po' di fuoco a caso. Ora **ogni nave della
guerra che non è l'Aquila ha, al primo colpo che passa scudo e corazza, un interno vero**: la pianta della sua classe
(`data/ship/plans/<classe>.json`, sette classi, generate da uno script), un equipaggio leggero (il ruolino della classe: chi sta in plancia,
ai cannoni, in sala macchine, nelle squadre danni, con il capitano e la sua catena di comando con un nome), e **lo stesso modello dei
danni dell'Aquila** (`FAstraDamageModel`, codice puro) che ci gira sopra:

- un colpo di GUERRA **entra dove è arrivato** (faccia, punto, direzione), attraversa le stanze dietro la corazza e si spende in ciascuna:
  falle, aria che esce, fuochi che passano per le porte aperte, condotti tagliati, paratie di sezione che si chiudono, stanze perdute;
- **chi muore o si fa male era davvero lì** (il ruolino mette la gente nei posti di combattimento della classe);
- squadre danni astratte **camminano** (sulla pianta, con i tempi di percorrenza delle porte e delle scale) fin dove serve e lavorano
  sul posto, con i tempi che il modello ha già per l'Aquila;
- **ciò che ne esce torna a GUERRA**: la potenza che ciascuna assegnazione ancora porta (scudi, armi, motori, sensori, hangar), le stanze
  e le persone che servono motori, sensori, hangar, ponte, reattore e **ciascuna arma** (la sua barbetta, il suo deposito), il fuoco che
  consuma la struttura, i fuochi e le falle che gli effetti disegnano, **la nave che resta senza equipaggio e diventa un relitto**, la gente
  persa con la nave quando salta;
- **ciò che ne sanno le menti**: il capitano di una nave sa cosa brucia a bordo, quanti ne ha persi, chi ha il comando e quanta potenza
  hanno ancora cannoni e motori (`aboard`); un osservatore vede da fuori ciò che si vede (falle che sfiatano, finestre spente, punti caldi,
  segni vitali di una traccia classificata: `seen_aboard`), con la nebbia di guerra di oggi;
- **ciò che si vede**: fuochi e atmosfera che esce nei punti veri dello scafo, finestre che si spengono in proporzione alle stanze senza
  corrente, fuochi e falle al loro posto nel tavolo olografico (`holo ship`), la gente nella sua riga.

Costa poco: una nave che non è stata colpita non ha un interno (si fa al primo colpo che passa), una nave calma non costa nulla tra un colpo
e l'altro, e la fisica gira a passi di 0,5 s (quella dell'Aquila a 0,2 s). Misurato (§7.4): 60 navi da guerra per 300 s di battaglia, **+0,16 ms ogni 0,1 s
di battaglia** (0,027 ms di un fotogramma a 60 fps in media), la chiamata peggiore 0,28 ms.

**Le prove** (§7, `tools/fleet.py`): un colpo tracciato dentro una nave nemica, faccia per faccia, con le stanze attraversate e chi c'era; una
nave pestata sulla prua che **si spezza dove la struttura ha ceduto** (il banco confronta la sezione dove la scafo si rompe con le stanze
perse dall'interno: coincidono, 3 semi su 3); battaglie intere con e senza gli interni: **gli esiti non si spostano** (entro il rumore, §7.3)
e le perdite di persone sono credibili.

## 1. I file

| Cosa | Dove |
|---|---|
| **Il piano di classe** come lo legge il gioco: la mappa dei compartimenti (la stessa dell'Aquila: `FAstraDamageMap`), il ruolino, le squadre con i tempi di percorrenza, i ruoli delle stanze, le stanze che servono le armi. Caricato **una volta per classe**, su un thread di lavoro, e condiviso | `Source/ASTRA/AstraFleetPlan.*` (`FAstraFleetPlans::Find / Prefetch / PathFor / LoadFile`, `FFleetClassPlan`) |
| **L'interno di una nave** (codice puro, niente attori, deterministico dal seme): il modello dei danni sul piano di classe, la gente, le squadre astratte, cosa torna a GUERRA | `Source/ASTRA/AstraFleetInterior.*` (`FAstraShipInterior`) |
| Cosa si dice di un interno: alle menti della parte (`BriefJson`), ai sensori di chi guarda (`SeenJson`, `FillView`), al banco (`BooksJson`), per gli abbordaggi (`Snapshot`), per gli effetti (`FxPoints`) | `Source/ASTRA/AstraFleetViews.cpp` |
| **Gli agganci con GUERRA**: nascita dell'interno, tick, cosa torna (`FleetFactor`, `FleetSys`), le statistiche, la console `astra.fleet.*` | `Source/ASTRA/AstraFleetHooks.cpp` (metodi di `UAstraBattleSubsystem`) |
| **Le piante delle sette classi** (`acheron styx lethe praetorian vigilant freighter station`) e le sonde degli scafi da cui nascono | `data/ship/plans/<classe>.json`, `data/ship/plans/hulls/<classe>.json` (copie per il gioco impacchettato: `Content/ASTRA/Data/plans/`) |
| **Il generatore delle piante** (Python puro; Blender serve solo per ripetere le sonde) | `art/blender/ship_hull_probe.py`, `ship_class_hull.py`, `ship_class_engine.py`, `ship_class_build.py`, `ship_class_wire.py`, `ship_class_finish.py`, `ship_class_checks.py`, `ship_class_plans.py`; le specifiche per classe in `ship_class_specs.py`, `_b.py`, `_c.py`; il disegno di una pianta: `tools/art/fleet_planview.py` |
| **Il banco** | `tools/fleet.py` (`trace`, `breaks`, `cost`, `ab`, `plans`), sopra `tools/war.py` |
| **Le menti**: come si leggono `aboard` e `seen_aboard`, e la dottrina | `mind/astra_mind/war_minds.py` (`aboard_line`, `seen_line`, `_member_line`, `render_enemy`, `render_astra_extras`, `mandate_extras`), prove in `mind/bench/fleet_views_unit.py` |

Cambiamenti in file di altri moduli (tutti **additivi**, elencati in §10): `AstraDamageMap/Model` (il caricatore per percorso, l'origine
della pianta nel sistema dello scafo, i ponti del corpo, il passo della fisica), `AstraBattleSubsystem`, `AstraWarDamage`, `AstraWarOrders`,
`AstraBattleQueries`, `AstraWarTypes.h`, `AstraWarShipAI`, `AstraWarScenario`, `AstraWarSimCommandlet`, `AstraWarFXHull` e `AstraWarFX.h`,
`AstraHoloTable.cpp`.

## 2. Il piano di classe

### 2.1 Il formato

Lo stesso di `data/ship/aquila_plan.json` (così il modello, gli abbordaggi e gli schermi lo leggono con lo stesso codice), con in più quello
che chiedevano gli abbordaggi:

- **`frame` / `origin_in_hull`**: la pianta è nel sistema della mesh dello scafo (X avanti, Y a dritta, Z in alto, metri; l'origine è quella
  della mesh): `origin_in_hull = [0, 0, 0]`. Quella dell'Aquila dice (172, 0, 62) (la sua pianta nasce dal pavimento della plancia). Il
  caricatore ha un solo punto d'ingresso: `FAstraDamageMap::Load(Percorso, Errore)` e `OriginInHullM`.
- **`docks`**: i punti d'attracco e i portelli: `{id, comp, face, pos, normal, deck, kind, width, height}` (portelli di ormeggio a lato, bocche
  dell'hangar a prua o a poppa), per gli abbordaggi.
- **`graph` e `doors`**: solo scale e porte collegano i ponti (niente buchi nei pavimenti), **paratie stagne di sezione** (`bBlast`) a ogni confine
  di sezione e un **fianco** (un percorso fra le sezioni che resta aperto a una paratia chiusa).
- **`objectives`**: stanza di ciascun obiettivo (ponte, ingegneria, alloggio del comandante, armeria, infermeria, brig, comunicazioni, hangar...),
  più i ruoli delle altre (sensori, controllo del fuoco, i caricatori, i motori, le batterie).
- **`garrison`**: dove sta la gente in allarme (comp, ruolo, n), la somma è l'equipaggio; **`roster`**: gradi, turni, posti degli ufficiali (`billets`),
  le quote per ruolo; **`crew`** è solo il numero (come lo leggono gli abbordaggi e i piani di ripiego).
- **`halls`** con `spans_decks` (hangar, sala macchine su più ponti), **`style`** (come si chiamano le stanze: gli Acheron del Mandate hanno
  «Oarsmen's Berths», le navi di ASTRA «Mess Hall»; luci e arredi per quando si camminerà), **`mounts`** (la stanza che serve ciascuna arma, nell'ordine di
  `data/war/classes.json`), **`damage_control`** (le squadre: dove stanno, quanti sono).

### 2.2 Il generatore

`python3 art/blender/ship_class_plans.py [--only acheron,styx] [--no-stage] [--no-check] [--decks]`. Passi:

1. **Sonda dello scafo** (`ship_hull_probe.py`, Blender senza testa: già eseguita, i profili stanno in `data/ship/plans/hulls/`): per ogni FBX la sezione a
   ogni X, il ventre, il dorso. Il resto è Python puro.
2. **Inviluppo** (`ship_class_hull.py`): il volume in cui possono stare i ponti, liscio, inscritto nella pelle misurata (con `skin_slack` dove la sonda è
   inaffidabile: telai aperti di mercantile e stazione).
3. **Ponti** (`ship_class_engine.py`): quota del pavimento, altezza libera, disposizione (`full` a tutta larghezza o `spine`: un corridoio con stanze ai
   lati), impronta forzata dove la torre è più stretta dello scafo, striscia per i portelli.
4. **Costruzione** (`ship_class_build.py`): dorsale (spine), passaggi, corridoi trasversali, sale (`halls`), scale, attracchi, stanze chiave
   (`keys`: ponte, ingegneria, armeria, infermeria...), file di stanze riempitive (cabine, depositi, laboratori) interne ed esterne.
5. **Collegamenti** (`ship_class_wire.py`): porte, grafo, paratie di sezione e fianco, sistemi per stanza (potenza, aria, munizioni...).
6. **Finitura** (`ship_class_finish.py`): garrison, posti degli ufficiali, squadre danni, ruoli delle armi, obiettivi, dock.
7. **Controlli** (`ship_class_checks.py`, **0 problemi per le sette classi**): ogni stanza sta nell'inviluppo; nessuna sovrapposizione; ogni porta è
   su un muro; ogni dock raggiunge ponte, ingegneria e comandante **a piedi** (anche con la paratia di sezione chiusa, per il fianco); la
   somma del garrison è l'equipaggio; gli obiettivi ci sono; ogni arma ha la sua stanza.

Le specifiche (`ship_class_specs*.py`): `sections` (le lettere A..H e le X di confine), `decks`, `halls`, `keys`, `stairs`, `docks`, `mounts`, `crew`, `dc`.
Aggiungere una classe = una specifica e una sonda; cambiare le stanze di una = ritoccare la sua specifica e rilanciare.

### 2.3 Le sette classi

| Classe | Scafo | Ponti | Stanze | Porte | Attracchi | Equipaggio | Marines | Squadre danni |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `lethe` | Kharon Mandate frigate | 6 | 270 | 254 | 5 | 62 | 10 | 2 |
| `styx` | Kharon Mandate destroyer | 7 | 394 | 410 | 5 | 140 | 16 | 3 |
| `acheron` | Kharon Mandate cruiser | 7 | 753 | 829 | 7 | 380 | 40 | 4 |
| `praetorian` | ASTRA battleship | 10 | 761 | 873 | 9 | 1020 | 100 | 6 |
| `vigilant` | ASTRA destroyer | 5 | 187 | 184 | 5 | 118 | 12 | 3 |
| `freighter` | Free Guilds freighter | 4 | 96 | 93 | 6 | 34 | 0 | 2 |
| `station` | ASTRA listening post | 6 | 83 | 81 | 5 | 48 | 4 | 2 |

Gli abbordaggi le hanno già lette con il loro caricatore: `tools/boarding.py run --scenario plans` (sette controlli, **sette passati**: ogni dock ha una strada a
ponte, ingegneria, alloggio del comandante, armeria, infermeria, brig, comunicazioni e hangar).

## 3. L'interno di una nave

### 3.1 Nasce al primo colpo che passa

`UAstraBattleSubsystem::FleetEnsure` crea `FAstraShipInterior` al primo colpo che supera scudo e corazza di una nave che ha un piano
(non l'Aquila, non i velivoli, non le esche). Una nave mai colpita non costa nulla: né memoria né tempo. La pianta della classe si legge **una volta**, su
un thread di lavoro, quando la prima nave della classe entra nella battaglia (`Prefetch` in `InitShipModel`): al primo colpo è già pronta (senza, il primo colpo
costava 45 ms).

### 3.2 La gente

`BuildCrew`: dal `garrison` della pianta (posti di combattimento: plancia, controllo, cannonieri, caricatori, ingegneria, squadre danni, medici, ponte di volo,
sensori, marines, riserva) nascono le persone; gli ufficiali dei `billets` sono **nominati** (capitano, esecutivo, tattico, capo macchine, medico, capo della
sicurezza, ufficiale di volo: nomi dei due lati, nessuno di quelli del cast dell'Aquila) e occupano il loro posto; i membri di ogni squadra danni sono mani di
controllo danni portate nella stanza di ritrovo della squadra. Il ruolo di ciascuno conta per ciò che torna a GUERRA (§4).

### 3.3 Il modello

Lo stesso `FAstraDamageModel` dell'Aquila (DISTRUZIONE §2): il colpo entra (`Impact`: faccia e punto dello scafo → punto della pianta → cammino di al più 5 stanze),
si deposita (`Deposit`: foro, fuoco, potenza, rottami), colpisce chi era lì (`BlastPeople`), e la fisica gira: aria che esce e si livella, campi di contenimento, fuoco e
fumo, paratie di sezione, esposizione delle persone. Differenze, per il costo:

- **passo 0,5 s** (`SetStep`: l'Aquila 0,2 s). La fisica sta ferma tra un passo e l'altro; la precisione cala, il comportamento no (le prove dell'Aquila, 46 su 46,
  girano ancora a 0,2 s);
- **al più 10 incidenti** contemporanei (`MaxIncidents`);
- le persone non sono 560 corpi con le loro vite: sono un elenco con stanza, posizione, ruolo e stato (in piedi, ferito, morto); **i feriti vanno in infermeria**
  dopo un po' (25 s) se c'è ancora;
- **le squadre danni** sono astratte ma non finte: ogni squadra ha i tempi di percorrenza dalla sua stanza a ogni stanza della nave (Dijkstra precalcolato sulla pianta, con porte
  e scale), cammina quel tempo, poi lavora l'incidente con il tempo che il modello dà per quella cosa (un foro, un fuoco, un condotto) moltiplicato per quanta della squadra è rimasta.

Una nave **calma** (nessuna stanza attiva, nessun incidente, nessun ferito da portare, nessuna squadra al lavoro) non fa nulla: `Tick` torna subito.

## 4. Cosa torna a GUERRA

GUERRA non viene riscritta: **moltiplica i suoi stati di scafo per ciò che l'interno dà**, al momento dell'uso (mai scritti nei sistemi persistenti: una stanza riparata
restituisce tutto).

| Cosa | Da dove | Dove la usa GUERRA |
|---|---|---|
| Potenza di ciascuna assegnazione (scudi, armi, motori, sensori, aria, ponte di volo) | `Factor(categoria)` del modello: la distribuzione, con il pavimento 0,5 dell'anello di riserva | `ShieldPower`, `WeaponPower`, `EngineFactor` (0,6 + 0,4·F), `SensorFactor`, `HangarFactor` |
| Motori, sensori, hangar, ponte, reattore | `SysFit`: la stanza (tessuto e potenza; per ponte e reattore il solo tessuto) × le persone che ci lavorano | `Sys[]` × `FleetSys`: `EngineFactor`, `SensorFactor`, `HangarFactor`, `ThinkDelay` del comando, il reattore critico e la morte per reattore |
| **Ogni arma** | `MountFit(m)`: la stanza della sua barbetta o del suo deposito (alimentazione e tessuto) | `FAstraMount::Feed`: la cadenza e la gittata dell'arma |
| Gli artiglieri e i caricatori | `WeaponCrew()` = 0,4 + 0,6·√(media dei gruppi che restano) | `WeaponPower` |
| Il fuoco e le falle | le stanze che bruciano e sfiatano per sezione | `Burn[]`, `Breach[]` delle sezioni (gli effetti), e **la struttura che il fuoco consuma** (`AddHullDelta`: al posto del tasso piatto di GUERRA, che per una nave con un interno non si applica più) |
| L'equipaggio | `CrewStrength()` (in piedi + metà dei feriti, sul totale) | sotto il 12 % (`astra.fleet.crew_min`, almeno 6 persone) la nave è **un relitto** («her crew is dead») |
| Le notizie | `CollectNews`: l'equipaggio che scende a tre quarti, a metà, a un quarto; il capitano ferito o morto e chi ha il comando; armi o motori giù di un quinto; un fuoco in un deposito di munizioni | `NoteGroupEvent` per la parte della nave (al più una ogni `astra.fleet.news_gap` = 10 s) |
| La gente quando la nave salta | `LoseWithShip()`: tutti quelli a bordo, in piedi o feriti, sono persi con lei («destroyed with all hands»), contati a parte dai morti per i colpi | i libri della battaglia |

Interruttori e messa a punto (console o `--exec` del banco): `astra.fleet.interior 0|1` (spento, GUERRA è com'era prima di FLOTTA-VIVA), `astra.fleet.power_k` (quanto di ciò che l'interno
perde torna a GUERRA: 1 tutto, 0 niente: l'interno si legge soltanto), `astra.fleet.crew_min`, `astra.fleet.news_gap`.

## 5. Cosa sanno le menti e i sensori

### 5.1 Alle menti di guerra

- **`aboard`** sotto una nave della propria parte (cosa sa il suo capitano): `crew {fit, wounded, killed, of}` (solo dopo le prime perdite), `command` (solo se il capitano non è in piedi: chi ha il
  comando), `fires`, `breaches`, `rooms_without_power`, `power_pct` (le assegnazioni che non portano più tutto), `pressure_bulkheads_shut`, `worst` (i tre incidenti peggiori, con la squadra che ci lavora o «no party
  free»), `damage_parties` («2 of 3 at work»), `rooms` (ponte, ingegneria, armeria, infermeria, comunicazioni, hangar: solo se non sono a posto). **Nessuna chiave dove non c'è nulla da dire**: una nave non colpita
  non costa un token.
- **`seen_aboard`** sotto un'altra nave, in base a quanto bene la conoscono i sensori: la vista (`breaches_venting`, `windows_dark_in`) e, per una traccia classificata, le emissioni (`fires_aboard`,
  `life_signs_pct` al cinque per cento, `power_pct` al dieci per cento).
- Dove stanno: `your_groups[].members[].aboard`, `enemy_groups[].ships[].seen_aboard` (le viste dei gruppi), `your_ships[].aboard` e `astra_ships[].seen_aboard` (la vista dell'ammiraglio del Mandate),
  `contacts[]` (la lista dei contatti del Capitano: `aboard` per le navi di ASTRA via collegamento dati, `seen_aboard` per le altre).
- **Python**: `war_minds.py` rende queste chiavi in una riga («aboard: crew 182 fit, 31 wounded, 17 killed of 230; Commander ... is dead; Lieutenant Commander ... has the conn; 2 fires, 1 breach venting, ...») e
  la dottrina dice come si leggono: **un prompt, non un filtro** (una nave con metà dell'equipaggio perso, i cannoni a un terzo o il deposito in fiamme non combatte come dice il suo scafo; di un nemico si vede solo l'esterno).
  Prove senza rete: `mind/bench/fleet_views_unit.py` (16 prove, due delle quali fanno tutto il cammino: una vista come la manda il gioco, un impulso di una mente, il prompt che il modello riceve) e
  `bench.war_minds_unit` (53, invariate); tutte le 484 prove unitarie della mente passano. Nessuna chiamata a un modello: 0 $ spesi.

### 5.2 Ai sensori e al tavolo olografico

`GetDamageView` ha ora `Fleet` (`FAstraFleetView`): i punti dei fuochi e delle falle nel sistema dello scafo (metri), le stanze senza corrente, i segni vitali (Detail 2) o la gente in piedi/ferita/morta,
le squadre al lavoro e chi ha il comando (Detail 3: la propria parte). Il tavolo olografico (`holo ship`) mette un segno arancione per ogni fuoco e uno rosso per ogni falla al loro posto sul diagramma
laterale e una riga («3 FIRES · 2 BREACHES · LIFE SIGNS ~65% · 18 ROOMS DARK» per una traccia classificata; «CREW 182 FIT · 31 WOUNDED · 17 KILLED OF 230 · CAPTAIN DOWN · DAMAGE PARTIES 2/3» per le nostre).

## 6. Cosa si vede da fuori (VFX)

- **Fuochi e atmosfera** (`HullEmitters`): una nave con un interno brucia e perde aria **dove lo fanno le sue stanze**: il punto è quello della stanza (dove è nato il fuoco, dove è entrato il colpo), portato
  sulla faccia della scatola dello scafo più vicina (`FleetFxPoint`); l'elenco si rinfresca 2,5 volte al secondo (`FleetFxRefresh`). Dove l'interno non ha punti per una sezione resta il punto a caso di prima.
- **Finestre**: `LitFraction` del materiale delle luci (`MI_HULL_<A|M|G>_Lights`) = 0,65 × la quota di stanze ancora alimentate (con un guadagno di 1,25: una nave che ha perso un quarto delle stanze è
  per un quarto buia). Il materiale ha **una sola frazione globale**: «nelle sezioni senza potenza» per sezione chiede un ritocco del materiale (§11).
- **La rottura**: la nave si spezza **nella sezione la cui struttura ha ceduto** (la regola di GUERRA: `OnSectionGutted` → `BreakSection`); l'interno la segue (`GutSection` perde tutte le stanze di quella sezione e
  uccide chi c'era). Il banco lo controlla (§7.2).

## 7. Il banco (`tools/fleet.py`)

Senza testa (`-nullrhi`), niente finestra, niente GPU, **nessuna chiamata a modelli**: non costa nulla. Serve la compilazione dell'editor di questo checkout.

### 7.1 Un colpo tracciato

`tools/fleet.py trace --class acheron --faces bow,port,dorsal,ventral --damage 400`: spara un colpo da 400 su ciascuna faccia di un Acheron fermo e racconta l'interno: dove entra, le stanze che
attraversa, chi c'era, cosa brucia e cosa si perde. Un esempio (dorsale):

> dorsal (mid section) enters at deck 1 section D (Laser Battery (port)); crosses 5 room(s): deck 1 section D (Laser Battery (port)) -> deck 2 section D (Stores) -> deck 3 section D (Gymnasium) -> deck 4 section D (Stores) -> deck 5 section D (Machine Shop); 0 killed, 2 wounded, a breach, a fire, a conduit cut

Dalla console, in gioco: `astra.fleet.hit <contatto> <faccia> [danno] [rail|laser|missile]` (stampa il cammino), `astra.fleet.pound` (molti colpi), `astra.fleet.strike <contatto> <stanza>` (un colpo in una stanza),
`astra.fleet.info [contatto]`; nel banco `astra.war.fleet <...>` li mette in coda dietro ai `spawn`.

### 7.2 Una nave che si spezza dove la struttura ha ceduto

`tools/fleet.py breaks --class acheron --face bow` (cinque giri di sei colpi da 150 sulla prua, uno ogni 4 s, con la rottura al primo cedimento): GUERRA dichiara «the bow section is gutted, the hull is breaking up» e
poi «the hull broke apart at the bow»; **l'interno ha perso 123 stanze su 123 della prua e 0 su 404 del mezzo e 0 su 226 della poppa**; chi stava a prua è morto (16 persone), gli altri 364 sono persi con la nave. Tre semi su tre: PASS.

### 7.3 Le battaglie con e senza (esiti, perdite)

`tools/fleet.py ab --scenarios sym_small,sym_medium,sym_two,asym_2to1 --seeds 12`: lo stesso scenario, con `astra.fleet.interior 0` (GUERRA com'era) e `1`. Risultati: vedi la tabella sotto (riempita dal banco; i semi e le deviazioni
standard sono quelle del banco di GUERRA).

12 semi per scenario, 900 s di battaglia, i due lati con le stesse navi (le sim_*) o ASTRA con il doppio (asym_2to1). «Sopravvissuti» sono le navi da guerra rimaste (anche andate via) a fine battaglia; «margine» è
quelli di ASTRA meno quelli del Mandate, con l'errore standard della media.

| Scenario | Senza interni (GUERRA com'era): sopravvissuti ASTRA / Mandate, margine | Con gli interni | Il margine si sposta di |
|---|---|---|---|
| `sym_small` (3 contro 3) | 1,8 / 2,0 — −0,17 ± 0,41 | 2,1 / 2,1 — 0,00 ± 0,37 | +0,17 ± 0,55 |
| `sym_medium` (6 contro 6) | 2,7 / 3,2 — −0,58 ± 0,52 | 3,4 / 2,8 — +0,67 ± 0,50 | +1,25 ± 0,72 |
| `sym_two` (6 contro 6, due gruppi per lato) | 3,2 / 3,9 — −0,67 ± 0,32 | 3,3 / 3,5 — −0,17 ± 0,28 | +0,50 ± 0,43 |
| `asym_2to1` (6 contro 3) | 6,0 / 1,0 — +5,00 | 6,0 / 0,8 — +5,17 ± 0,11 | +0,17 ± 0,11 |

**Gli esiti non si spostano**: il segno è lo stesso ovunque (leggermente a favore di ASTRA, dentro il rumore: la stessa scena a lati invertiti, `sym_small_rev`, dà +0,31 senza e +0,19 con) e i sopravvissuti totali variano di meno di
mezza nave. Le **perdite di persone** (per battaglia, `sym_medium`): 10 navi su 12 hanno un interno; delle 2372 persone a bordo i colpi ne uccidono 503 (21 %) e ne feriscono 146 (6 %); altre 890 si perdono con le navi
che saltano (in media sei navi su dodici sono distrutte); 275 fuochi, 342 falle. In `sym_small` (3 contro 3): 133 morti e 58 feriti per i colpi su 1087 a bordo, 380 persi con le navi. Sono le cifre di una battaglia
decisiva fra navi da guerra, non di una scaramuccia.

### 7.4 Il costo, per N navi

`tools/fleet.py cost --scenario scale_60x300 --seconds 300` (e `scale_30x150`), il costo dell'interno misurato dentro il gioco (non il mondo intero):

| Scenario | Navi da guerra | Con un interno a fine battaglia | Colpi | Tick di GUERRA senza → con (media / p95) | Gli interni | La chiamata peggiore |
|---|---:|---:|---:|---|---|---:|
| `scale_30x150`, 120 s | 30 | 22 | 534 | 0,179 → 0,195 ms / 0,278 → 0,298 ms (**+0,016 ms, +9 %**) | 20 ms in tutto: 0,17 ms ogni secondo di battaglia (0,008 ms per nave) | 0,06 ms |
| `scale_60x300`, 300 s | 60 | 50 | 3636 | 0,406 → 0,567 ms / 0,977 → 1,074 ms (**+0,161 ms, +40 %**) | 372 ms in tutto: 1,24 ms ogni secondo di battaglia (0,025 ms per nave) | 0,28 ms |

(Il tick del banco è di 0,1 s di battaglia: i +0,161 ms sono 1,6 ms ogni secondo di battaglia, **0,027 ms di un fotogramma a 60 fps in media**, lo 0,16 % di un core.)

**Prova di resistenza**: `scale_60x300` per 900 s di battaglia (31 navi di ASTRA contro 30 del Mandate, 296 velivoli al picco): 53 interni costruiti (il più caro 0,05 ms: l'equipaggio e il modello), 5123 colpi,
292 652 tick di nave, **1044 ms in tutto = 1,16 ms ogni secondo di battaglia**, la chiamata peggiore 0,17 ms, il tick di GUERRA 0,29 ms in media e al massimo 1,0 ms; nessun avviso né errore nel registro; le perdite
(ASTRA 1178 morti e 1391 persi con le navi su 6170 a bordo delle navi colpite, Mandate 1649 e 2355 su 6558) sono di una guerra, non di una scaramuccia. La pianta di una classe si legge su un thread di lavoro quando nasce
la prima nave della classe (21-70 ms a classe, una volta): nel banco, che combatte 900 s di battaglia in 3,6 s di orologio, il primo colpo deve aspettarla (27 ms al massimo: `plan_wait_ms_max`, per avere la stessa risposta a
ogni prova); **nel gioco non aspetta mai** (`Find` senza attesa: la nave resta senza interno finché il thread non ha finito, al colpo dopo ce l'ha).

Il passo di fisica degli interni (ogni 0,5 s per nave) è la spesa maggiore: la chiamata peggiore dura 0,28 ms con 60 navi. Il costo cresce con le navi **colpite**, non con quelle in campo: ogni interno parte dal suo primo
colpo, quindi i passi delle navi non cadono tutti nello stesso fotogramma.

## 8. Per gli abbordaggi (F5.2)

- Le **piante** hanno già tutto ciò che chiedevano (sette punti: frame e origine, `docks`, scale e porte con paratie e fianco, `objectives`, `garrison`, sale su più ponti, stile): vedi §2 e `tools/boarding.py run --scenario plans`.
- Lo **stato dell'interno** quando una squadra entra: `UAstraBattleSubsystem::FleetSnapshot(ShipId, FFleetSnapshot&)` dà le stanze che non sono a posto (aria, foro, fuoco, fumo, calore, potenza, rottami, perduta, sigillata),
  le paratie chiuse (id delle porte della pianta), le persone vive con stanza, posizione, ruolo e ferite, i nominati (capitano, ufficiali) e chi ha il comando. Una stanza non elencata è com'è nella pianta.
  Quando una squadra entra davvero, la scena si costruisce dalla pianta (come per l'Aquila) con quello stato: l'aria, il fuoco, le luci, i morti.
- La nave che si è **arresa o è un relitto** (equipaggio sotto il 12 %, «her crew is dead») resta con il suo interno: i morti dove sono caduti, i fuochi che bruciano finché le squadre non li spengono.

## 9. Come si integra

1. `git merge worktree-agent-afc317b58aa5f3fa7` (il ramo di FLOTTA-VIVA ha già `main` dentro).
2. Ricompilare l'editor (`tools/ricompila.sh`): nuovi file `AstraFleet*.cpp/.h`, modifiche additive in altri; nessuna nuova dipendenza, nessun asset.
3. Le piante per il gioco impacchettato sono già copiate in `Content/ASTRA/Data/plans/` (la cartella `ASTRA/Data` è già in `DirectoriesToAlwaysStageAsNonUFS`); il gioco le cerca lì per prime, poi in `data/ship/plans/`.
4. Prova: `python3 tools/fleet.py trace`, `python3 tools/fleet.py breaks`, `python3 tools/damage.py run --scenario all` (46 su 46), `python3 tools/boarding.py run --scenario plans`, `cd mind && .venv/bin/python -m unittest bench.fleet_views_unit bench.war_minds_unit`.
5. In gioco: `astra.fleet.info` elenca le navi che hanno un interno e cosa ne è; `astra.fleet.interior 0` lo spegne (GUERRA com'era).

## 10. Cambiamenti in file di altri moduli (tutti additivi)

| File | Cosa |
|---|---|
| `AstraDamageMap.h/.cpp` | `Load(Percorso, Errore)` (il caricatore unico: lo stesso che usano gli abbordaggi), `OriginInHullM`, i ponti del corpo (`FirstBodyDeck`, `LastBodyDeck`, `IsBody`, `bBody`), tipi di stanza in più (profili) |
| `AstraDamageModel.h/.cpp` | usa l'origine e i ponti del corpo (invece di 172, 0, 62 e dei ponti dell'Aquila), `SetStep` / `StepS` (il passo della fisica per istanza; l'Aquila resta a 0,2 s) |
| `AstraBattleSubsystem.h/.cpp` | `TSharedPtr<FAstraShipInterior> Interior` e `FleetNewsT` in `FAstraBattleShip`, `Fleet` in `FDamageView`, le dichiarazioni `Fleet*`, `FleetOnDestroyed` in `Destroy`, `FleetBriefInto` nelle viste (`MandateViewJson`, contatti) |
| `AstraWarDamage.cpp` | `FleetEnsure` e `FleetOnHit` in `ApplyHit`, `FleetOnGutted` in `OnSectionGutted`, `FleetTick` in `TickDamageState`; `EngineFactor`, `PowerFactorOf`, `SensorFactor`, `HangarFactor`, il reattore e `ThinkDelay` moltiplicano per `FleetSys`; il fuoco piatto di GUERRA non consuma la struttura di una nave con un interno; `Prefetch` della pianta; `Fleet` nella vista dei danni |
| `AstraWarOrders.cpp` | `aboard` e `seen_aboard` nelle viste dei gruppi |
| `AstraBattleQueries.cpp` | i libri dell'interno (`interior`) nel record di ogni nave |
| `AstraWarTypes.h`, `AstraWarShipAI.cpp` | `FAstraMount::Feed` e `Fit()` (l'arma serve per quanto la sua stanza regge) |
| `AstraWarScenario.cpp` | `astra.war.fleet` (i comandi `astra.fleet.*` in coda del banco) |
| `AstraWarSimCommandlet.cpp` | `stats.fleet` nel record |
| `AstraWarFXHull.cpp`, `AstraWarFX.h` | `FleetFxRefresh`, `FleetFxPoint`, i punti dei fuochi e delle falle e la frazione di luce per nave |
| `AstraHoloTable.cpp` | i segni dei fuochi e delle falle e la riga della gente in `TickScannedShip` |

## 11. Limiti noti e passi successivi

- **Le finestre si spengono per nave, non per sezione**: il materiale delle luci ha un solo `LitFraction`. Per spegnere solo le sezioni senza corrente serve un ritocco del materiale (tre scalari `SecLit0..2` e una maschera sulla X
  del vertice rispetto ai tagli di classe): non l'ho fatto perché non posso provarlo senza editor.
- **La gente è un elenco, non corpi**: i morti non si vedono, i feriti non camminano fino all'infermeria (ci «arrivano» dopo 25 s). Quando si camminerà dentro una nave (abbordaggi) servirà metterli come attori dal `Snapshot`.
- **La rottura di GUERRA resta probabilistica** (25 % al primo cedimento, 70 % al secondo, certa al terzo): l'interno la segue, non la decide.
- **Una nave distrutta perde tutti** («with all hands»): niente capsule di salvataggio per le altre navi.
- **Il passo di 0,5 s** perde un po' di dettaglio nei fuochi molto veloci (un deposito che salta): le prove dell'Aquila restano a 0,2 s.
- **Le piante hanno stanze plausibili, non progetti**: nomi, arredi e luci per camminarle sono un lavoro dell'arte interna (ARTE-INTERNI) quando servirà.
- **Taratura**: `power_k`, `crew_min`, la soglia delle notizie sono scelte mie, misurate sul banco (§7.3); il lead le ritocca dopo averle viste in gioco.
