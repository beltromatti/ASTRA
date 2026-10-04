# Lo spazio vivo — il modulo SPAZIO-VIVO (F2/F4)

*Documento del modulo SPAZIO-VIVO (2026-10-04). I nomi nel gioco e nei dati sono in inglese; il documento in italiano. Il progetto del modulo è in
[brief/SPAZIO-VIVO.md](brief/SPAZIO-VIVO.md); la guerra che ci sta sopra è in [GUERRA.md](GUERRA.md), il modo di disegnare a istanze in [SCALA.md](SCALA.md)
e [VFX.md](VFX.md), gli interni delle altre navi in [FLOTTA-VIVA.md](FLOTTA-VIVA.md), chi sale a bordo in [ABBORDAGGI.md](ABBORDAGGI.md).*

**Stato.** Scritto, compilato e provato sul banco senza grafica (`tools/space.py test`: 41 prove su 41). **Mai visto nel motore da chi l'ha scritto** (le regole
dei moduli di supporto: nessun editor, nessuna GPU): il primo passo del lead è la lista del §10. Parti:

| Parte | Stato |
|---|---|
| **M1** I luoghi veri (Keeper Station, Arsenal, raffineria di Tiberius, miniera di Ceres), il traffico civile, la cintura, le boe | unito e importato dal lead (3/10–4/10) |
| **M2** Ciò che la guerra lascia: i relitti, i campi di detriti, le capsule di salvataggio con i fari, il salvataggio, la persistenza | questo documento, §3–§7 |
| **M3** Il moto delle capitali reso leggibile (getti di manovra, scie) e gli scafi dei luoghi solidi per il Falcon del Capitano | questo documento, §8–§9 |

## 1. Che cosa è

Lo spazio di Aurelia non è più una scena vuota con una battaglia dentro: ci sono posti dove andare, navi che ci vivono, e quando la guerra passa **resta qualcosa**.
Il principio è quello di SCALA: **il costo cresce con ciò che si vede, non con ciò che c'è**. Niente attore per nave lontana, niente tick per oggetto: ogni cosa è un
record (un punto, una velocità, un assetto) più un'aritmetica che dice dov'è adesso, e si disegna a istanze solo quando è vicina.

Tutto il codice di dati e di regole è C++ semplice (niente oggetti del motore), deterministico per un seme: il banco (`tools/space.py`, commandlet `AstraSpaceSim`,
`-nullrhi`) lo fa girare per ore in secondi e lo controlla.

## 2. I file

| File | Cosa contiene |
|---|---|
| `Source/ASTRA/AstraSpaceLife.h/.cpp` | **`UAstraSpaceLife`**: il sistema messo in piedi (luoghi come contatti fixture, traffico, cintura, boe), il mondo come lo vede il traffico, gli eventi per l'equipaggio, la console. Posseduto da `UAstraBattleSubsystem` (come `UAstraWarFX`) |
| `Source/ASTRA/AstraSpaceLifeData.*`, `AstraSpaceLifeTraffic.*` | M1: i dati (`data/space/*.json`), il layout di un sistema, le rotte e il traffico (puro C++) |
| `Source/ASTRA/AstraSpaceLifeDraw.cpp`, `AstraSpaceLifeDrawUtil.h` | il disegno a istanze: le pagine di scafi (slot stabili), le luci, i pennacchi; i tre piccoli aiuti condivisi |
| **`Source/ASTRA/AstraWrecks.h/.cpp`** | **M2, il cuore**: i siti di ciò che la guerra lascia, il loro moto come aritmetica, le capsule e i loro fari, ciò che si dice all'equipaggio, il file (puro C++) |
| **`Source/ASTRA/AstraSpaceLifeWrecks.cpp`** | M2, dal lato del gioco: la perdita di una nave registrata, la consegna dei pezzi dagli effetti, il disegno, il salvataggio, i ganci del soccorso, la console |
| `Source/ASTRA/AstraWrecksTest.cpp` | le prove dei record da soli (nessun mondo: un decimo di secondo) |
| **`Source/ASTRA/AstraSpaceLifeMotion.h/.cpp`**, `AstraSpaceLifeMotionDraw.cpp`, `AstraSpaceLifeMotionTest.cpp` | **M3, i getti e le scie**: la tavola degli ugelli, l'assegnazione, la lettura del moto, la scia (puro C++); il disegno e la console (lato gioco); le prove |
| **`Source/ASTRA/AstraSpaceLifeSolids.h/.cpp`** | **M3, gli scafi dei luoghi**: le scatole di `solids.json` come mappa di bit, la prova di un punto o di un percorso, `PilotHit` (il gancio del Falcon), `astra.space.solids`, le prove |
| `Source/ASTRA/AstraSpaceLifeSimCommandlet.*` | il banco: `-run=AstraSpaceSim` (`-seconds`, `-at`, `-exec`, `-selftest`, `-wrecktest`, `-motiontest`, `-solidstest`) e i controlli di invarianti |
| `tools/space.py` | `run`, `report`, `test`, `wrecktest`, `motiontest`, `solidstest`, `sync`, `meshes` |
| `tools/art/space_plot.py`, `tools/art/wrecks_plot.py` | le mappe del traffico e di ciò che la guerra ha lasciato, da un record del banco |
| **`art/blender/space3_thrusters.py`**, `space3_motion_scene.py`, `tools/art/motion_sheet.py` | M3: dove sono gli ugelli di ogni classe (sulle mesh vere, `data/space/thrusters.json`) e le anteprime dei getti e della scia |
| **`art/blender/space3_solids.py`**, `tools/art/solids_plot.py` | M3: gli scafi dei luoghi come scatole (`data/space/solids.json`) e la loro figura |
| `art/blender/spacegen3.py`, `space3_*.py` | i generatori Blender dei luoghi, degli scafi civili, delle rocce, dei detriti, delle capsule, delle boe |
| `art/blender/space3_wreck_scene.py` | un sito di relitti **come lo mettono i dati**, reso con le mesh vere (le sezioni del generatore delle navi, i detriti, le capsule) |
| `tools/ue_scripts/import_space_v3.py`, **`make_space_materials.py`** | l'importazione delle mesh; il flag «Used with Instanced Static Meshes» sui materiali degli scafi (da eseguire una volta, §10) |
| `data/space/space.json`, `meshes.json`, **`thrusters.json`**, **`solids.json`** | i dati (luoghi, corsie, giri, pattuglie, cintura), la tavola delle mesh (luci, ugelli, attracchi), gli ugelli di manovra di ogni classe, gli scafi dei luoghi; copia in `Content/ASTRA/Data/space` (`tools/space.py sync`) |

## 3. Ciò che la guerra lascia — il disegno

Ogni nave persa è **un sito** (`AstraSpace::FSite`): chi era, come è andata, quando, ciò che restava a bordo, i suoi pezzi, il suo campo di detriti, le sue capsule.
Un sito è un record che non si muove da sé: dove sia adesso lo dice l'aritmetica (`FWrecks::PosAt`, `AttAt`, `ChunkAt`), a qualunque ora, anche dopo ore di campagna.

```
FSite { Id, System, ShipId, Name, Class, Contact, KnownAs, HullMesh, ClassKey, Faction, How, Section, DiedAt, Pos0/Vel (cornice del Gate), Radius,
        FAboard Aboard;            // le persone e le stanze del suo piano
        TArray<FPieceRec> Pieces;  // sezioni (0 prua, 1 centro, 2 poppa) o, se la guerra non l'ha spezzata, lo scafo intero bruciato: punto, velocità, assetto, spin
        FFieldRec Field;           // il campo di detriti: quanti pezzi, il seme, da dove, quanto in fretta si allarga
        TArray<FPodRec> Pods;      // le capsule: lancio, aria, stato (alla deriva, recuperata, aria finita), sopravvissuti }
```

**La cornice è quella del Gate.** L'origine della battaglia è dove entra l'Aquila: cambia a ogni sistema e a ogni ripresa. Il Gate no. I siti stanno quindi nella
cornice del Gate del loro sistema (`FSkyFrame`: dove sta e verso dove punta il suo asse) e vi tornano come erano: **un relitto a 8 km dalla Keeper Station resta a 8 km
dalla Keeper Station**. (Il Gate nasce a ogni arrivo con un rollio a caso attorno al suo asse: i relitti restano fedeli ai luoghi, non alle direzioni del pianeta e della
stella, che seguono il cielo di quella volta.)

**Il tempo.** L'orologio dei relitti è quello della battaglia più un'origine che la ripresa regola (`WreckClock`): un salvataggio ritorna con il suo orologio, e nulla invecchia
mentre il gioco è spento. `UAstraSpaceLife::AdvanceWrecks(secondi)` è il gancio per un salto di tempo della campagna (le ore passano, le capsule perdono l'aria);
`astra.space.skip` lo chiama.

### 3.1 La fine di una nave

Il gancio è `UAstraBattleSubsystem::Destroy`, **dopo** che gli effetti l'hanno disegnata: `Space->OnShipLost(S, E, bFxDone)` (una riga). Le tre fini che lasciano un relitto
sono quelle della guerra: **rottura** (`Breakup`: una sezione cede, le altre tengono), **reattore** (`ReactorBreach`), **distruzione semplice** (`Destroyed`: struttura a zero,
l'esplosione vecchia con lo scafo bruciato). Una nave *disattivata* non è persa: resta nel piano come derelitto (e non è registrata: §10).

Il sito prende:
- l'identità (nome, classe, id di contatto, `KnownAs` = come l'ha chiamata la guerra a chi guardava: la nebbia di guerra vale per le capsule come per il resto) e la classe del
  suo piano (`ClassKey`: `vigilant`, `praetorian`, `acheron`, `styx`, `lethe`, `freighter`, `station`);
- **i pezzi** come gli effetti li hanno appena fatti (`UAstraWarFX::GetPieces`): stesso punto, stessa velocità, stesso spin. Se la guerra non ha potuto spezzare lo scafo, un solo
  pezzo: lo scafo intero, bruciato;
- **ciò che restava a bordo** (§3.6);
- il campo e le capsule (sotto).

### 3.2 I pezzi e la consegna dagli effetti

Per il primo minuto i pezzi sono **attori degli effetti** (le facce di taglio che bruciano e si raffreddano in ~60 s, le finestre che si spengono, fuochi, fumo, scintille:
VFX.md §8). Il sito li segna `bInFx` e non li disegna. A **80 s** (`FWrecks::HandOverS`) il modulo prende il pezzo **dalla posizione e dall'assetto che gli effetti gli danno in
quel fotogramma** (`ReAnchor`: niente salti), chiede agli effetti di lasciarlo (`UAstraWarFX::ReleasePiece`: l'attore si distrugge) e da lì lo disegna lui, a istanze, **morto**:
finestre spente, facce di taglio fredde, luci di posizione spente, e per un reattore anche la vernice carbonizzata (come gli effetti: tinta × 0,18). Se gli effetti l'hanno già
lasciato (il loro tetto di 36 pezzi dà via i più vecchi quando dodici navi si spezzano insieme), il record continua dal punto dove nacque, subito.

**Conseguenza buona**: i relitti non dipendono più dal tetto degli effetti. Dodici navi, sessanta navi: dopo 80 s sono istanze.

I materiali: ogni pagina di un pezzo ha una copia dinamica di ogni materiale che cambia (`ApplyWreckLook`: una per slot, **non una per relitto**: tutte le istanze della pagina
la condividono). Servono i materiali di base marcati per le istanze: `tools/ue_scripts/make_space_materials.py`. Il gioco lo controlla (`GetUsageByFlag`) e lascia fuori ciò
che non sa ombreggiare dicendo nel log quale.

### 3.3 I detriti

Ogni sito ha un campo (`FFieldRec`): da 20 a 240 pezzi (`ChunkCountFor`: ~0,42 × il raggio per una rottura, 0,55 per un reattore, 0,34 per il resto), in **tre forme**
(lastra 13 m, trave 24 m, pezzo di scafo 9 m: le mesh `SM_DEBRIS_<A|M|G>_*` come sono state fatte) nel colore della parte. Nessun pezzo è conservato: ognuno è una funzione del
**seme del campo** e del suo indice (`MakeDefs` ne fa le definizioni, una volta, quando il campo si avvicina; `ChunkAt` li valuta). Si allargano: il più lento va a 0,6 m/s, il più
veloce a 14 (rottura), 22 (distruzione) o 55 (reattore); la maggior parte è lenta (esponente 2,2); girano da 1 a 35 gradi al secondo; la brace dei più caldi muore in 70 s (140 per un
reattore) e si vede come un punto di luce (lo strato dei bagliori, scritto ad ogni fotogramma, finché la brace è sopra 0,06).

Il campo è **cercato** solo se il suo bordo sta a meno di 24 km dall'Aquila, e ogni pezzo esce dal quadro dove sarebbe un punto (0,9 km per metro di grandezza, fra 3 e 22 km: una lastra di 13 m si disegna fino a 12 km). Al più
**420 pezzi** insieme (`astra.space.wrecks.chunks`), i campi più vicini per primi.

### 3.4 Le capsule di salvataggio

Quante ne partono lo dice la regola (`PodCountFor`), dalla **gente viva a bordo** quando la nave è andata:
- **rottura**: da 0,55 a 1 volta `equipaggio / 22` (almeno una, al più nove: il Vigilant da 3 a 5, la Praetorian da 5 a 9), dalle sezioni che tengono (mai da quella che cede);
- **reattore**: il lampo si porta via quasi tutto: nessuna nel 60 % dei casi, una o due nel 40 % (misurato su 600 casi: 242);
- **distruzione semplice**: poche, `0,35 × equipaggio / 22` con il caso.

Ogni capsula porta da `max(1, C/2)` a `C` persone, con `C = clamp(equipaggio / 16, 4, 12)`, **mai più di sei su dieci dei vivi** (`Escaped`; il resto è `Lost`, perso con la nave).
L'equipaggio viene dal suo interno (FLOTTA-VIVA) quando c'era, altrimenti dalla tavola dei ruolini dei piani (`ComplementOf`: 1020 Praetorian, 380 Acheron, 140 Styx, 118 Vigilant,
62 Lethe, 48 station, 34 freighter; **la prova controlla che la tavola sia ancora uguale ai piani**).

Una capsula esce dal fianco dello scafo (una faccia del suo box, lontano dall'asse), con la velocità della nave più una spinta (6–16 m/s per una rottura, 8–20 per il resto,
35–90 per un reattore); il suo assetto e il suo lento rotolare vengono da un hash (`PodPose`: nulla va salvato). Il **faro parte 20–60 s dopo il lancio** (si allontana prima dallo
scafo) e chiama finché c'è aria: **da 81 a 180 minuti** (`PodAirS` × 0,45–1). Dopo, la capsula resta lì, muta (§3.5).

### 3.5 Ciò che si dice all'equipaggio

Eventi di fatti, nelle parole dei sensori (come quelli del traffico: la mente li legge come tutti gli altri):
- **«sensors: distress beacons — …»**, una volta per relitto, **quando tutti i fari di quel relitto chiamano** (nel primo minuto): quante capsule, di chi, quanti sopravvissuti,
  l'aria *almeno* per quanto, la prima per direzione, quota e distanza (`bearing 072, mark +3, 41 km`); se i relitti sono più d'uno, una sola riga con i tre più vicini e il conto del resto.
  Entro **90 km** dall'Aquila (`FWrecks::BeaconKm`);
- **«sensors: a close look at the …»**, una volta, quando un pezzo sta a meno di **10 km** dall'Aquila (o dal Falcon del Capitano in volo): *che cosa è stato* (il nome vero:
  a quella distanza si leggono le fiancate), come è andato, da quanto, «no power, no transponder, no life signs», a quanti gradi al secondo gira (e «the torn ends still glowing»
  nel primo minuto), quante capsule sono partite, quanti pezzi di rottami in quanti chilometri;
- **«sensors: the lifepod beacons of … have gone silent»**, quando l'aria è finita senza che nessuno le abbia prese (sempre un rapporto per l'equipaggio);
- **«flight: search and rescue — the Wasps of the Aquila took 4 ASTRA lifepods of … aboard: 19 survivors»**.

**In battaglia** (`bEngagementActive`) i fari e gli sguardi sono *notizie* e non *rapporti*: non tolgono il turno all'equipaggio dallo scontro; il silenzio e il salvataggio lo sono sempre.

Alle menti il blocco `space` dello stato della nave porta ora anche `wrecks` (`UAstraSpaceLife::WreckSummaryJson`): `here` (quanti siti in questo sistema), `nearest` (fino a tre
pezzi entro 60 km: di chi, come, da quanti minuti, direzione, quota, distanza) e `lifepods` (`beacons`, `survivors`, e il più vicino con la sua aria in minuti). Piccolo apposta.

### 3.6 Per ABBORDAGGI e FLOTTA-VIVA: ciò che resta a bordo

**Un relitto tiene la sua classe, il suo id e ciò che restava a bordo.** Chi vuole leggerlo: `UAstraSpaceLife::GetWrecks()` (`const FWrecks&`):

```cpp
const AstraSpace::FSite* Site = Battle->GetSpace()->GetWrecks().FindByShip(ShipId, SystemName);   // o FindByContact("T-02", ...)
Site->ClassKey;          // vigilant: il piano data/ship/plans/vigilant.json (ABBORDAGGI: AstraBoardPlans::Load; FLOTTA-VIVA: FAstraFleetPlans::Find)
Site->Pieces[i].Section; // 0 prua, 1 centro, 2 poppa (il taglio del piano: CutBowCm / CutSternCm), 255 lo scafo intero
Site->Aboard;            // FAboard: vedi sotto
// dove sta adesso, in cornice di sistema:  Sky.ToSystem(FWrecks::PosAt(Site->Pieces[i], Now)),  con Sky = Space->SkyFrame() e Now = Space->WreckClock()
// come gira:  FWrecks::AttAt(piece, Now) (spin costante: 0,5–3 gradi al secondo)
```

`FAboard`: `Complement` (quanti ne porta la classe), `Alive` (vivi a bordo quando è andata), `Killed` (morti prima, caduti dove sono caduti), `Lost` (persi con lei), `Escaped`
(in capsula), `bInside` (i numeri sono quelli del suo interno e non una stima), **`Rooms`** (le stanze del piano che *non* erano come costruite: aria, falla, fuoco, fumo, calore,
corrente, rottami 0..1, sventrata/chiusa: `FFleetSnapshot::FRoom` com'era un attimo dopo la perdita) e `SealedDoors` (le paratie di pressione chiuse).

Per salire su una sezione la pianta e il suo stato sono qui: le stanze della sezione sono quelle dalla parte giusta del taglio, quelle fuori dal gas sono quelle sventrate, e i
morti sono `Killed` + `Lost` (la posizione dei persi con la nave non è registrata: `FFleetSnapshot::Hands` è vuoto dopo `LoseWithShip`; il banco di ABBORDAGGI può metterli
in modo deterministico nelle stanze rimaste). **Le stanze si salvano per i 12 siti più recenti** (`FWrecks::RoomSites`): i più vecchi tengono i conti.

## 4. Il soccorso

**Un ordine di soccorso** è la missione `sar` della rete di volo (VOLO): `LaunchSquadron(..., "sar", ...)`. Ora cerca i fari veri.
- `UAstraSpaceLife::HasBeacons()`: la missione si può dare se qualcosa chiama entro 90 km dall'Aquila (altrimenti «no distress beacons on the plot: nobody to rescue», com'era);
- `RescueGoal(Rank, …)`: dove vola un velivolo (il suo `CraftSlot`-esimo faro più vicino all'Aquila: **ogni velivolo di una pattuglia ha il suo**, le capsule si allontanano
  fra loro) e come si muove;
- `RescueTake(At, RadiusM, By)`: entro 1,2 km dal faro prende a bordo le capsule entro 1,5 km (`State` = recuperata: non chiamano più) e **dice all'equipaggio** cosa ha
  preso. Se non chiama più niente, la pattuglia torna a casa.

Il vecchio copione (la posizione della *ultima nave nostra persa*, «lifeboats found, 18–74 survivors picked up» a caso) resta solo se lo spazio vivo è spento
(`astra.space.enable 0`). Le capsule **nemiche** (del Mandato) si prendono come le altre: l'evento dice «(Mandate crew)» e basta; che cosa farne lo decide chi comanda.

Per provare senza una pattuglia: `astra.space.rescue [km]` (le barche dell'Aquila).

## 5. Il salvataggio e il ritorno

Il salvataggio della campagna (`ship.json`) porta in `battle.space` tutti i siti di tutti i sistemi visitati (`UAstraBattleSubsystem::SaveJson` / `ResumeFrom`, due ganci).
Il formato è fatto di **numeri interi in un'unità loro** (decimetri, decimillesimi di m/s, millisecondi): un double si stampa con 17 cifre e un decimale arrotondato non si stampa mai
corto. Misurato: **71 siti = 80 KB (1,12 KB a sito)**, la prima costruzione degli oggetti 0,5 ms, **0,007 ms** quando nulla è cambiato (ogni sito tiene il suo JSON finché non cambia),
scrittura del testo 3 ms (il salvataggio avviene ogni 60 s: un'impennata di un fotogramma). Limiti: **72 siti** in tutto (`MaxSites`: via i più vecchi senza capsule vive), via i
relitti vecchi di sei ore a più di mille chilometri dal Gate (nessun sistema li raggiungerà mai).

Alla ripresa i siti tornano **dove erano rispetto al nuovo Gate** (provato: `astra.space.wrecks.resume`, ripristino vero dal salvataggio del banco: 21 parti confrontate, la più lontana
0,10 m = il passo del file) e con il loro orologio. Una campagna nuova li azzera (`StartCampaign`).

## 6. Il costo

| Cosa | Misura (banco, M-serie sotto carico di un editor aperto) |
|---|---|
| tre perdite, una battaglia piccola | **4 µs a tick** in media per i relitti |
| **40 navi perse insieme** attorno all'Aquila, 15 minuti fra i rottami | **25 µs a tick** (picco 120 scafi e 420 pezzi istanziati; prima delle due ottimizzazioni sotto: 209 µs) |
| una perdita (`AddLoss`) | decine di µs; 40 insieme: l'impennata di un fotogramma, 1,5 ms |
| i siti | 1,1 KB l'uno in memoria e nel file |

Come è fatto per costare poco:
- **Le pagine dei relitti pendono dal componente del sistema** (lo stesso da cui pendono la cintura e le boe), con trasformazioni nella cornice del sistema: il volo dell'Aquila è
  *una* trasformazione a fotogramma, non una per relitto, e i vettori di moto per l'upscaler temporale restano veri.
- **Ciò che deriva piano si riscrive di rado**: entro 3 km a ogni fotogramma (un pezzo che passa dal finestrone), entro 10 km ogni secondo, entro 40 ogni sesto, oltre ogni ventesimo
  (`KeepHull`: tiene lo slot senza riscrivere, dice all'upscaler che è fermo).
- **Una pagina in cui nulla è cambiato non si manda** (`FInstSet::Dirty`).
- **Niente stringhe né allocazioni per pezzo per fotogramma**: l'indice dell'insieme di istanze di ogni pezzo, forma, capsula è tenuto.
- I fari delle capsule sono lampade (lo strato dei bagliori): visibili a 170 km come punti di tre pixel.
- I getti e le scie (M3) costano **10 µs a tick** con 18 navi (§8.4).

## 7. Console, variabili, banco

Console (`astra.space.*`):

| Comando | Cosa fa |
|---|---|
| `lose <contatto\|nearest> [breakup\|reactor\|destroyed] [sezione 0\|1\|2]` | perde una nave da guerra come la guerra (prova: vedere cosa resta) |
| `wrecks.list` | i siti di questo sistema: chi, come, da quanto, capsule (aria, stato), ciò che restava a bordo |
| `look wreck\|pod [km]` | l'Aquila a qualche chilometro dal pezzo o dalla capsula più vicini, prua su di essi |
| `rescue [km]` | prende a bordo le capsule vicine (le barche dell'Aquila) |
| `stat` | (esteso) il conteggio dei relitti, cosa si disegna, cosa costa |
| `skip <s>` | anche i relitti invecchiano |
| `wrecks.roundtrip` | scrive e rilegge il salvataggio dei relitti: uguale, dimensione, tempi |
| `wrecks.resume` | **distruttivo**: ripristina la battaglia dal suo stesso salvataggio (un Gate nuovo); il log dice se ogni relitto è dov'era |
| `wrecks.dump <percorso> [sito] [secondi]` | scrive un sito per `space3_wreck_scene.py` |
| `wrecks.reset` | dimentica tutti i relitti |
| `jets <contatto\|classe\|nearest> <manovra> [s]`, `motion.list` | **M3**: spara i getti di una nave a mano; che cosa chiede il moto di ogni nave (§8.5) |
| `solids [raggio] [s]`, `solids.test` | **M3**: disegna le celle piene dei luoghi vicini all'occhio; le prove nel mondo (§9) |

Variabili: `astra.space.wrecks` (1/0: i relitti si registrano o no), `astra.space.wrecks.km` (220: fino a dove si disegnano i pezzi), `astra.space.wrecks.chunks` (420).
`astra.space.reactions` resta com'era: **non è un riparo per il crash di `Explode`** (corretto su main), è l'interruttore di prova con cui il banco isola il traffico dalla guerra
dell'apertura (0: il traffico non la sente; 2: sente solo l'ostile finto di `astra.space.alert`).

**Il banco** (`tools/space.py test`, 41 prove, ~4 minuti):
- il traffico (M1): un'ora di pace, un ostile sulle corsie, la porta del Gate, determinismo;
- **`wrecktest`** (nessun mondo, 0,1 s): 1800 perdite (le tre fini, sei classi, con e senza interno): le persone tornano, nessun faro senza sopravvissuti, nessun NaN; determinismo byte per
  byte; il moto è punto + velocità, i detriti restano nel raggio del campo più veloce, a un secondo come a quattro giorni; il file torna com'era e costa poco; i limiti; gli eventi (il faro
  una volta e con **tutte** le capsule, il silenzio, lo sguardo da vicino anche dal Falcon, in battaglia sono notizie); il soccorso; la consegna senza salti; **la tavola degli equipaggi
  uguale ai piani**;
- **quattro navi perse in un mondo** (una per ogni fine): registrate, capsule, i fari sentiti, uno sguardo, il soccorso detto e contato, il salvataggio rileggibile, **il ripristino a metà**;
  lo stesso scenario due volte (stessi eventi); **40 relitti insieme**: le invarianti reggono e costa meno di 0,1 ms a tick;
- **`motiontest`** (nessun mondo, 0,02 s) e **una battaglia di dodici navi** (M3: §8.6): i getti e le scie, il costo, la mano della console;
- **`solidstest`** e **gli scafi nel mondo** (M3: §9): l'anello, i percorsi, le parti che girano dove le disegna il gioco.

## 8. Il moto delle capitali reso leggibile (M3)

**Le regole del moto non cambiano.** La guerra muove le navi come sempre (accelerazione in ogni direzione, tagliata a quella della classe; virata alla velocità della classe). Questo modulo
**legge** ciò che è successo, un fotogramma alla volta (dove sta la nave, a che velocità, verso dove punta: `AstraSpace::Observe`), e ne ricava che cosa la nave chiede ai suoi getti
di manovra e dove il suo motore lascia una scia. Niente di ciò che si disegna torna alla guerra. Il cuore è C++ semplice (`AstraSpaceLifeMotion.h/.cpp`), il disegno è di
`UAstraSpaceLife` (`AstraSpaceLifeMotionDraw.cpp`).

![i getti dell'Aquila](progressi/spazio/jets_aquila.jpg)

*(anteprima: i getti dell'Aquila come il gioco li accende per sei manovre, poppa a sinistra, prua a destra, sullo scafo vero; l'aspetto dei coni è dell'anteprima, non dei materiali del
gioco. `jets_acheron.jpg`: lo stesso per una nave del Mandato, che non ha blocchi di propulsori suoi.)*

### 8.1 Dove sono gli ugelli

`data/space/thrusters.json` (copia in `Content/ASTRA/Data/space`), fatto da `art/blender/space3_thrusters.py` (Blender senza finestra: le mesh vere, `tools/space.py sync`):

- **le navi ASTRA** (Aquila, Praetorian, Vigilant) hanno già i **blocchi di propulsori** dei generatori (`thruster_cluster`: quattro piccoli ugelli ai quattro angoli della poppa): quelli sono gli
  ugelli, nella posizione in cui il generatore li ha messi (16 per nave): **un getto esce da un ugello che si vede sullo scafo**;
- per il resto un **pacchetto standard trovato sullo scafo**: si lanciano raggi contro la mesh generata, dall'esterno, e l'ugello sta sulla prima superficie incontrata, **su un tratto piano**
  (un bordo di lastra o la canna di un cannone metterebbero il getto in aria) e su **placcatura** (non su radiatori, finestre, luci). Getti d'imbardata sui fianchi, d'assetto e di rollio su
  ponte e chiglia (fuori asse, così rollano anche), di frenata sulle spalle della prua (inclinati in fuori, così il getto libera lo scafo). Sempre in coppie speculari. Dove lo scafo si
  restringe (la lancia della Praetorian) la stazione di prua si sposta indietro, fino a dove è largo almeno la metà del massimo;
- la **tavola**: Aquila 28 (16 dei blocchi + 2 + 6 + 4), Praetorian 26, Vigilant 26, Acheron 14, Styx 14, Lethe 16, Freighter 16. In più, per ogni classe, il **centro del propulsore principale** e la
  sua larghezza (da dove parte la scia e quanto è larga), la lunghezza, e il punto attorno a cui la nave gira. Lo script controlla anche che **ogni spinta e ogni virata possibile abbia getti
  che la danno** (undici direzioni: la frenata, la spinta di lato e di quota, sei virate; la spinta in avanti è del motore).

### 8.2 Che cosa accende un getto

Un getto si accende **quando la spinta che dà e la coppia che dà vanno nel verso di ciò che il moto chiede**: nessun copione per manovra, la stessa assegnazione (`Allocate`, poche righe) accende
i getti giusti per una virata a dritta, un beccheggio, un rollio, una frenata, uno scarto, o una miscela. Ogni ugello ha la sua spinta (`-D`, l'opposto dello scarico) e la sua coppia attorno
al centro della nave (`P × spinta`, ogni asse rapportato al **migliore** ugello di quell'asse: una nave rolla con una leva corta e beccheggia con la sua lunghezza). Una quota sotto 0,15
non accende nulla (un ugello che gira la nave di poco non deve lampeggiare).

Che cosa si chiede viene dal moto, riletto ogni fotogramma:

| Cosa | Da dove | Che cosa fa |
|---|---|---|
| **il calcio** (`Kick`) | il *cambio* della velocità di virata, nel sistema della nave, rapportato alla velocità piena della classe | la simulazione gira alla velocità della classe (la velocità di virata salta all'inizio e alla fine di una virata): un **lampo dei getti che la avviano**, che muore in ~0,6 s, e lo stesso, **opposto, quando finisce** |
| **la tenuta** (`Omega`) | la velocità di virata ora, × 0,42 | una **debole guarnizione che lampeggia** finché la virata dura (un'ammissione di stile: fisicamente nessun getto spara in una virata tenuta, ma senza questa una virata lenta non si leggerebbe) |
| **la spinta** (`Lin`) | l'accelerazione nel sistema della nave, sulla piena della classe, levigata (attacco 0,18 s, rilascio 0,45 s); sotto il 10 % è il rumore dell'IA | frenata (getti che guardano avanti), scarto e salita (getti che spingono di lato). **La spinta in avanti è del motore principale** (i pennacchi di `UAstraWarFX::DrawDrives`, lasciati come sono): i getti non sparano per una spinta |

Ogni getto sale in 0,04 s e si spegne in 0,16 s, ed è **pulsato**: un propulsore spara a colpi, quindi uno debole lampeggia (la fase è sua, otto volte al secondo, con un ciclo di lavoro che segue
l'intensità) e uno forte (≥ 0,82) brucia fisso. Una nave **disattivata** (`bDisabled`) o **spenta** (`bCold`: «drives off, no emissions») non ha getti e non lascia più scia (quella che ha lasciato svanisce da sé).

### 8.3 Che cosa si disegna

- **Il getto**: un pennacchio corto (lo strato `Jets`, il cilindro e il materiale dei pennacchi della guerra: `M_WAR_Plume`) dall'ugello lungo il suo scarico, e un **bagliore** all'ugello (nello
  strato delle luci). Le dimensioni sono una frazione della lunghezza dello scafo (larghezza 0,6 %, lunghezza fino al 3,2 %, bagliore 1 %): a un ugello vero di un metro la battaglia si
  combatte a una distanza dove sarebbe un granello, quindi il getto è **esagerato e cresce con la distanza** (da 8 km in poi, fino a 2,6 volte a 21 km), e il materiale tiene comunque due pixel. Colori come
  i motori della fazione (ASTRA azzurro, Mandato arancio). Fino a **45 km** dall'Aquila (`astra.space.jets.km`), al più dieci getti accesi per nave.
- **La scia**: finché il motore lavora (`UAstraWarFX::Throttle` > 0,1, e un motore non morto: la stessa prova del pennacchio della guerra) si nota il punto dove brucia, nel sistema, ogni
  0,75 s (o ogni 5 % della lunghezza se la nave è lenta): un **nastro di perle** (`M_WAR_Dart`, lo stile 2 delle scie dei missili, ognuna sfuma lungo se stessa) che **resta dove la nave è
  passata**, si allarga con l'età (fino a 2,9 volte) e si abbassa, e dura **da 10 a 24 secondi** secondo la lunghezza (`WakeLifeFor`: l'Aquila 22 s = 6 km di scia, il Vigilant 14 s). Da vicino ogni
  pezzo, da lontano uno su due o su quattro; vicino all'occhio (sotto 60 m) niente e fino a 250 m sfuma, perché una perla vicina sarebbe un velo sullo schermo. Una nave che esce dal piano lascia la
  sua scia, che svanisce da sé.

![la scia](progressi/spazio/wake_aquila.jpg)

*(anteprima: la scia di una nave che tiene una virata a tutta velocità per tutta la vita della scia; ventotto pezzi, 6 km. L'aspetto è dell'anteprima: i materiali del gioco sono sulla guerra e
vanno tarati nel motore con `astra.space.wakes.gain`.)*

### 8.4 Costo

| Cosa | Misura (banco) |
|---|---|
| leggere una nave e accendere i getti (`Observe` + `Fire`) | **0,14 µs a nave a passo** (7 classi, 126 000 passi di voli a caso, tutte e sette) |
| una battaglia di 12 ostili in più della guerra d'apertura (18 navi lette), quattro minuti | **10 µs a tick**; al più **64 pennacchi di getto** (tetto 192) e **319 pezzi di scia** (tetto 640) insieme, **nessuno scartato** |
| memoria | una scia è 1 KB a nave; la tavola dei getti 11 KB |

Strati nuovi: due componenti a istanze (`SpaceJets`: cilindri col materiale dei pennacchi; `SpaceWakes`: sfere col materiale dei dardi) e i bagliori nello strato delle luci già esistente. Le istanze
si scrivono ogni fotogramma come le altre, le navi più vicine per prime (se uno strato si riempie vanno senza le lontane).

### 8.5 Console e variabili

| Comando | Cosa fa |
|---|---|
| `astra.space.jets <contatto\|classe\|nearest> <yaw+\|yaw-\|pitch+\|pitch-\|roll+\|roll-\|brake\|left\|right\|up\|down\|all> [secondi]` | **spara i getti di una nave a mano** (prova: vedere dove sono): `all` li accende tutti insieme per N secondi; la nave più vicina, o l'Aquila se è sola |
| `astra.space.motion.list` | per ogni nave: velocità, velocità di virata, calcio e spinta chiesti, quanti getti accesi, quante note ha la scia |
| `astra.space.stat` | (esteso) la riga `motion:` con gli strati e il costo |

`astra.space.reload` rilegge anche `thrusters.json` e `solids.json` (si cambia un dato, `tools/space.py sync`, reload: senza riavviare).

Variabili: `astra.space.motion` (1/0: tutto), `astra.space.jets.gain` (1: la luminosità dei getti; viene da `astra.fx.intensity` in più), `astra.space.jets.km` (45), `astra.space.wakes` (1/0),
`astra.space.wakes.gain` (1), `astra.space.wakes.km` (110), `astra.space.wakes.life` (1: moltiplica la durata).

### 8.6 Le prove

`tools/space.py motiontest` (nessun mondo, 0,02 s; dentro `test`): i dati (sette classi, ugelli dentro lo scafo, scarichi unitari, ogni asse con il suo migliore ugello a 1, **una spinta e una
virata per ogni verso**); **l'assegnazione contro la fisica** (77 domande: i getti che sparano spingono e girano la nave dal verso chiesto, la spinta in avanti non spara nulla, una domanda
nulla non spara nulla; la coppia fuori asse di un’imbardata o di un beccheggio è 0,36 di quella chiesta); **42 virate programmate** (sette classi, tre assi, due versi: nulla prima, il lampo
all'inizio, la guarnizione, il lampo opposto alla fine, **quiete dopo sette secondi**); frenata, spinta in avanti (nessun getto), scarti a destra e a sinistra, salite; il salto (un transito, la console
che mette l'Aquila accanto a un luogo) non è una manovra; il tempo fermo non fa NaN; la scia (le note a ritmo, il limite dell'anello, i pezzi in ordine di età e d'un pezzo solo, lo stride, una
nave ferma ne lascia una e basta, una lenta nota per distanza); l'impulso (il ciclo di lavoro segue l'intensità a 0,007); un volo di cinque minuti a caso per classe.

Nel mondo (`test`): una battaglia di dodici navi per quattro minuti (le navi sono lette, i getti sparano, le scie ci sono, nessuno strato è scartato, costa meno di 50 µs a tick) e i getti sparati a
mano dalla console.

## 9. I luoghi sono solidi per il Falcon del Capitano (M3)

Il Falcon del Capitano vola in prima persona e si perde se entra in uno scafo (`UAstraBattleSubsystem::PilotCollision`: «flight: Eagle flew into the hull of …», poi `Destroy(S, Internal)`). Per
le altre navi la prova era la scatola di contorno della mesh × 0,8; per **i luoghi** (Keeper Station, Arsenal, raffineria, miniera) quella scatola è quasi tutta aria: avrebbe schiantato il Falcon in mezzo
all'anello della Keeper e lo avrebbe lasciato passare attraverso un molo.

![gli scafi dei luoghi](progressi/spazio/place_solids.jpg)

*(i luoghi come li prova il gioco: ogni scatola è disegnata trasparente, il segno arancione è il Falcon in scala, 12 m. L'anello è visto lungo il suo asse: il buco c'è, e i quattro raggi.)*

**Come è fatto.** `art/blender/space3_solids.py` fa lo scafo di ogni luogo dalla sua mesh, come il gioco la disegna: la superficie è campionata più fitta della cella, le celle toccate si segnano
(una griglia di 3–12 m a seconda della grandezza), **ciò che è chiuso dentro si riempie** (un'area raggiungibile dal fuori resta aria: le baie dell'Arsenal restano aperte, il buco dell'anello resta
buco), e le celle si uniscono nelle scatole meno possibili (`data/space/solids.json`: da 106 a 4324 scatole per mesh, 273 KB in tutto). Il gioco le espande in una **mappa di bit** (un megabit o due a
mesh) e prova un punto con una ricerca: **4 ns**; un percorso si prova ogni mezza cella (il Falcon fa fino a 17 m a fotogramma).

| Mesh | Cella | Scatole | Pieno |
|---|---|---|---|
| Keeper Station (1114 m) | 4,3 m | 2487 | 5,9 % |
| il suo anello (612 m, gira ogni 90 s) | 3 m | 4324 | 23 % |
| Arsenal (3636 m) | 12 m | 2915 | 8,4 % |
| la sua gru (210 m, oscilla di ±62°) | 3 m | 106 | 9,8 % |
| raffineria di Tiberius (1808 m) | 6,9 m | 3097 | 9,7 % |
| miniera di Ceres (465 m) | 3 m | 2833 | 15 % |

**Le parti che girano** (l'anello della Keeper, le tre gru dell'Arsenal) hanno scatole nel loro sistema (l'origine della mesh della parte è il suo perno) e il gioco le gira **come le disegna**
(`DrawPlaces`: lo stesso orologio, lo stesso angolo): l'anello a un certo istante ha i suoi raggi dove li mostra. La prova nel mondo (`astra.space.solids.test`) lo controlla a tre orologi.

**Il gancio** (la sola modifica alla battaglia; vedi §11): `UAstraSpaceLife::PilotHit(Prev, Now, OutWhat)`, che `PilotCollision` chiama dopo il giro sulle altre navi; la risposta è «the hull of
Keeper Station», con le stesse parole di una nave, e il resto del percorso è quello di sempre (il rapporto che le menti leggono, la distruzione, il Capitano che si lancia). Nel giro generico
`PilotCollision` ora salta i `bFixture` (la scatola della mesh non ha senso per loro).

Console: `astra.space.solids [raggio m = 300] [secondi = 20]` **disegna le celle piene dei luoghi vicini all'occhio** (arancio, `DrawDebugBox`; fino a 3000 tratti): dove il Falcon si perde, da vedere con
`astra.space.look keeper 2`. `astra.space.solids.test`: le prove nel mondo (un tratto pieno è colpito, l'aria a 40 km no, l'anello a tre orologi).

Le prove da sole (`tools/space.py solidstest`, 0,02 s): i sei file di dati, il numero di scatole e di celle e quanto sono piene; **l'anello**: il mozzo è pieno, il bordo è pieno, **gli spicchi fra i raggi sono aria**
(un Falcon ci passa), i raggi sulle diagonali sono pieni, l'aria attorno è aria; un percorso lungo l'asse nello spicchio libero non colpisce, in un raggio colpisce, fuori dall'anello non colpisce; un
percorso che finisce una cella fuori dal bordo non colpisce e uno che finisce due celle dentro sì; punti a caso: la quota piena coincide con le celle; il costo (4 ns).

## 10. Messa in servizio (per il lead)

1. `git merge worktree-agent-aa357b4b05aab282f` (il ramo prosegue quello di `worktree-agent-a7d3df7e6454139e6`: contiene M1 e ha già unito main), poi la solita ricompilazione. I file di dati nuovi
   (`thrusters.json`, `solids.json`) sono **già** in `Content/ASTRA/Data/space` (copiati con `tools/space.py sync` e committati).
2. **Una volta**, nell'editor: `tools/ue.py pyfile tools/ue_scripts/make_space_materials.py` (marca per le istanze i materiali di base delle sezioni delle navi, dei detriti e delle
   capsule; stampa `SPACE_MATERIALS_OK`), poi riavviare (gli shader della permutazione istanziata si compilano una volta).
3. **Relitti** (M2). Nel gioco, con il banco (`tools/play.py`) o la console: `astra.space.lose T-02 breakup 1` (il Vigilant della scorta si spezza al centro), poi `astra.space.look wreck 1.5`: l'Aquila a
   1,5 km dal pezzo più vicino. Per i **primi 80 s** i pezzi sono attori degli effetti (fuochi sui tagli); a 80 s passano a istanze **scure**: la prova è che non saltino e che le finestre
   siano spente. Se sono grigi: il passo 2.
4. Dopo 20–60 s: la riga **«sensors: distress beacons …»** (quattro capsule), i fari che lampeggiano sul cielo (`astra.space.look pod 3`), poi `flight` con missione `sar` (a voce:
   «Price, soccorso alle capsule») o `astra.space.rescue 10`: la riga di salvataggio.
5. `astra.space.wrecks.list`, `astra.space.stat`: i numeri. Salvataggio e ripresa: `astra.space.wrecks.resume` (distruttivo) e il log «resume check: SAME».
6. **Getti di manovra** (M3). Con una battaglia in corso, guarda dal finestrone o dallo schermo principale una nave che vira o frena (le navi dell'IA lo fanno di continuo: `astra.space.motion.list` dice
   quali chiedono che cosa). Per vedere **dove sono gli ugelli** senza aspettare: `astra.space.jets nearest all 20` (tutti accesi per venti secondi sulla nave più vicina) e poi `astra.space.jets nearest yaw+ 10`,
   `brake`, `right`. Se sono troppo piccoli o troppo vivi: `astra.space.jets.gain` (un numero: 0,5 o 2). Se non si vedono affatto: `astra.space.stat` deve dire `motion: N ships read` con N > 0 e, accesi,
   `plumes` > 0; se `plumes` è 0 manca `M_WAR_Plume`, se non ci sono scie manca `M_WAR_Dart` (`tools/ue_scripts/make_war_fx.py`, il log di avvio lo dice).
7. **Scie** (M3). Seguono da sole le navi in moto: `astra.space.wakes.gain 2` le raddoppia, `astra.space.wakes.life 1.5` le allunga, `astra.space.wakes 0` le spegne. Si vedono bene dallo schermo principale su una
   nave che gira.
8. **Scafi dei luoghi** (M3). `astra.space.look keeper 2` (o `arsenal`, `tiberius`), poi `astra.space.solids 300 30`: le celle piene attorno all'occhio, in arancio, per trenta secondi. Poi in volo con il
   Falcon: nello spicchio libero dell'anello della Keeper si passa, in un raggio ci si schianta («flight: Eagle flew into the hull of Keeper Station»).

**Cosa guardare per primo**: (a) che le sezioni istanziate dei relitti abbiano il materiale giusto (scuro, non grigio) e tengano la posizione dopo il passaggio a 80 s; (b) che i detriti si vedano da
vicino (3–22 km) e non pesino; (c) che i fari si vedano da lontano; (d) **che i getti si leggano alla distanza della battaglia (5–20 km)** e non facciano rumore (qualche nave in manovra ha sempre qualche
getto che lampeggia; se è troppo, alzare `PushDead` in `AstraSpaceLifeMotion.h`); (e) **che la scia sia un nastro tenue e non un laser** (se è troppo viva: `astra.space.wakes.gain 0.4`); (f) la memoria del gioco
(era a ~8 GB su 9): le mesh dei detriti e delle capsule sono poche migliaia di triangoli, i getti e le scie non portano mesh.

## 11. Ganci in file di altri moduli (tutti piccoli, tutti commentati)

| File | Cosa | Perché |
|---|---|---|
| `AstraBattleSubsystem.cpp` `Destroy` | `Space->OnShipLost(S, E, bFxDone)` dopo `DeathEvents.Add(E)`; il vecchio `LastWreckPos/Name` solo se lo spazio non è attivo | il gancio nominato (M2) |
| `AstraBattleSubsystem.cpp` `SaveJson`, `ResumeFrom`, `StartCampaign` | `space` nel salvataggio; `NewCampaign` + `LoadSaved` prima di `Arrive`; `NewCampaign` | la persistenza (M2) |
| `AstraBattleSubsystem.cpp` `LaunchSquadron` | la missione `sar` si può dare anche se `HasBeacons()` | il soccorso (M2) |
| `AstraWarCraft.cpp` ramo `sar` | un ramo nuovo prima del vecchio: ogni velivolo vola al suo faro e prende le capsule | il soccorso (M2) |
| `AstraWarFX.h` / `AstraWarFXHull.cpp` | `GetPieces()` (una riga), `ReleasePiece(ShipId, Section)` (una funzione) | la consegna dei pezzi (M2) |
| **`AstraBattleSubsystem.cpp` `PilotCollision`** | **(M3) due modifiche, nient'altro**: (1) nel giro sulle altre navi la condizione `if (O.bPlayer \|\| O.bCraft \|\| O.Id == S.Id \|\| …` ha in più `O.bFixture` (la scatola della mesh × 0,8 non vale per i luoghi); (2) subito prima del `if (What.IsEmpty()) return false;` finale: `if (What.IsEmpty() && Space && Space->IsActive()) { Space->PilotHit(Prev, S.Pos, What); }` | il Falcon si schianta contro gli scafi dei luoghi come contro una nave (stesse parole, stessa distruzione) |

**Non ho toccato `TickPiloted`**: chiama `PilotCollision(S, S.Pos - S.Vel * Dt)` come prima e la modifica è là dentro, dove sta il giro sulle altre navi (con quel gancio il percorso dallo schianto al
rapporto e alla distruzione è unico). Nel codice di `TickPiloted` e di `PilotCollision` **non c'è alcun segnale di «too close»** oltre allo schianto («flight: Eagle flew into …», `Destroy(S, Internal)`): se
intendevi un avviso di prossimità (una voce dell'equipaggio quando il Falcon si avvicina a uno scafo), non esiste per nessuna nave e andrebbe fatto per tutte, con la stessa prova (`UAstraSpaceLife::PilotHit`
risponde anche a un percorso breve: basta un segmento che finisce a qualche decina di metri dallo scafo, o una versione con un margine).

Richieste al lead (non le ho fatte io, sono di altri moduli):
1. **FLOTTA-VIVA**: `FAstraShipInterior::LoseWithShip` scrive «lost with all hands (N aboard)»; con le capsule non è vero. Suggerisco di togliere «with all hands» (e «N aboard» diventa «N aboard
   when she went»): chi si è salvato lo dice il faro. Oggi l'equipaggio può sentire «lost with all hands» e poi «distress beacons … 19 survivors».
2. **CAMPAGNA**: `UAstraCampaignSubsystem::NewCommand` scrive `battle` vuoto: il relitto dell'Aquila precedente (e tutto ciò che la guerra ha lasciato) non c'è nel nuovo comando. Se si vuole
   che ci sia, basta copiare `battle.space` dal salvataggio vecchio nel nuovo.
3. **MENTE-EQUIPAGGIO**: nei prompt dei sensori (Nair) e del volo (Price) due righe su `space.wrecks` e sulla missione `sar` (vedi §3.5 e §4): oggi lo leggono dallo stato senza che il prompt lo nomini.
4. Il tasto del Falcon per prendere a bordo una capsula (`RescueTake` c'è: basta chiamarla): chi pilota il Falcon non può ancora raccogliere nessuno.
5. **Ugelli propri per le navi del Mandato e delle gilde** (arte, non mia): non hanno blocchi di propulsori nei generatori, quindi i loro getti escono da bocchette al filo dello scafo (il pacchetto
   standard: §8.1). Se si volesse un ugello visibile, basta mettere `thruster_cluster` in `ship3_mandate.py`/`ship3_misc.py` e rifare `space3_thrusters.py`: il resto segue.

## 12. Limiti noti e cosa farei dopo

- **Mai visto nel motore**: l'aspetto dei pezzi morti (la copia dinamica dei materiali per slot), le dimensioni dei detriti e dei fari, **l'aspetto e la luminosità dei getti e delle scie** (le costanti sono
  tarate sul calcolo, sulle anteprime e sull'esposizione 6,6 della guerra, non a occhio), i costi di render. Il banco misura il costo di CPU del modulo (con le istanze contate, non scritte); il resto lo
  misura il lead. Tutto ciò che è da tarare ha una variabile (`astra.space.jets.gain`, `wakes.gain`, `wakes.life`, `wakes.km`, `jets.km`).
- **Le navi disattivate** (`bDisabled`: derelitti abbordabili) non si registrano: spariscono con il sistema com'era. È il passo naturale dopo: registrarle quando il sistema si lascia e
  rimetterle come contatti derelitti al ritorno (serve `SpawnClass` + lo stato spento della guerra: l'ho lasciato fuori perché tocca le regole).
- I relitti **non sono contatti** del piano tattico né del tavolo olografico: si vedono dal finestrone e dallo schermo principale, si sentono dai fari, e `space.wrecks.nearest` li dice alle menti.
- Nessun danno da detriti, nessuna collisione con i pezzi dei relitti (il Falcon ci passa attraverso): il gancio c'è (`PilotHit` per i luoghi); per i relitti basterebbe lo stesso con le scatole dei loro
  pezzi, se il lead lo vuole.
- **I getti sono una lettura del moto, non la sua causa**: la guerra non spende propellente né sa dei getti. Un cambio di rotta dell'IA a scatti (la sua `Steer` cambia a pezzi) li fa lampeggiare a
  scatti; la `PushDead` (10 %) e il `DeadBand` (0,15) tolgono il rumore, non lo eliminano. **Non ci sono getti per i velivoli** (Falcon, Wasp, Harpy…): sono «le capitali»; il file degli ugelli della guerra
  ha già i sedici dei Wasp se si vuole.
- **I getti del Mandato escono dal filo dello scafo** (§8.1): da vicino (qualche centinaio di metri) si vede che non c'è un ugello. Le navi ASTRA hanno i blocchi.
- La **scia** si fa solo dove il motore lavora (`Throttle` sopra 0,1: la crociera minima della guerra è 0,16, quindi una nave in moto ne fa sempre); le navi **disattivate o spente** non ne fanno più
  (quella già fatta svanisce); le navi oltre i 137 km non la cominciano. La scia dell'Aquila sta dietro il ponte: si vede dallo schermo principale e dal finestrone quando vira.
- **Il Gate** non è tra i luoghi solidi (ha il suo trattamento nella battaglia); gli **scafi dei luoghi** sono veri a 3–12 m (il Falcon si perde se il suo *centro* entra in una cella piena: arriva a pochi
  metri dallo scafo, non ci passa dentro): una gru stretta può risultare larga quanto la sua cella.
- `HandOverS` è 80 s fisso (le facce di taglio si raffreddano in 60 s): se VFX cambia quel tempo va cambiato anche qui.
- Le ore di campagna che passano senza giocare (la mente fa passare «settimane») non invecchiano i relitti: il gancio c'è (`AdvanceWrecks`), va chiamato da chi sa quanto è passato.
