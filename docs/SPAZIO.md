# Lo spazio vivo — il modulo SPAZIO-VIVO (F2/F4)

*Documento del modulo SPAZIO-VIVO (2026-10-04). I nomi nel gioco e nei dati sono in inglese; il documento in italiano. Il progetto del modulo è in
[brief/SPAZIO-VIVO.md](brief/SPAZIO-VIVO.md); la guerra che ci sta sopra è in [GUERRA.md](GUERRA.md), il modo di disegnare a istanze in [SCALA.md](SCALA.md)
e [VFX.md](VFX.md), gli interni delle altre navi in [FLOTTA-VIVA.md](FLOTTA-VIVA.md), chi sale a bordo in [ABBORDAGGI.md](ABBORDAGGI.md).*

**Stato.** Scritto, compilato e provato sul banco senza grafica (`tools/space.py test`: 31 prove su 31). **Mai visto nel motore da chi l'ha scritto** (le regole
dei moduli di supporto: nessun editor, nessuna GPU): il primo passo del lead è la lista del §8. Parti:

| Parte | Stato |
|---|---|
| **M1** I luoghi veri (Keeper Station, Arsenal, raffineria di Tiberius, miniera di Ceres), il traffico civile, la cintura, le boe | unito e importato dal lead (3/10–4/10) |
| **M2** Ciò che la guerra lascia: i relitti, i campi di detriti, le capsule di salvataggio con i fari, il salvataggio, la persistenza | questo documento, §3–§7 |
| **M3** Il moto delle capitali reso leggibile (getti di manovra, scie) e le strutture solide per il Falcon del Capitano | in lavorazione (§9) |

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
| `Source/ASTRA/AstraSpaceLifeSimCommandlet.*` | il banco: `-run=AstraSpaceSim` (`-seconds`, `-at`, `-exec`, `-selftest`, `-wrecktest`) e i controlli di invarianti |
| `tools/space.py` | `run`, `report`, `test`, `wrecktest`, `sync`, `meshes` |
| `tools/art/space_plot.py`, `tools/art/wrecks_plot.py` | le mappe del traffico e di ciò che la guerra ha lasciato, da un record del banco |
| `art/blender/spacegen3.py`, `space3_*.py` | i generatori Blender dei luoghi, degli scafi civili, delle rocce, dei detriti, delle capsule, delle boe |
| `art/blender/space3_wreck_scene.py` | un sito di relitti **come lo mettono i dati**, reso con le mesh vere (le sezioni del generatore delle navi, i detriti, le capsule) |
| `tools/ue_scripts/import_space_v3.py`, **`make_space_materials.py`** | l'importazione delle mesh; il flag «Used with Instanced Static Meshes» sui materiali degli scafi (da eseguire una volta, §8) |
| `data/space/space.json`, `data/space/meshes.json` | i dati (luoghi, corsie, giri, pattuglie, cintura) e la tavola delle mesh (luci, ugelli, attracchi); copia in `Content/ASTRA/Data/space` (`tools/space.py sync`) |

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

Variabili: `astra.space.wrecks` (1/0: i relitti si registrano o no), `astra.space.wrecks.km` (220: fino a dove si disegnano i pezzi), `astra.space.wrecks.chunks` (420).
`astra.space.reactions` resta com'era: **non è un riparo per il crash di `Explode`** (corretto su main), è l'interruttore di prova con cui il banco isola il traffico dalla guerra
dell'apertura (0: il traffico non la sente; 2: sente solo l'ostile finto di `astra.space.alert`).

**Il banco** (`tools/space.py test`, 31 prove, ~3 minuti):
- il traffico (M1): un'ora di pace, un ostile sulle corsie, la porta del Gate, determinismo;
- **`wrecktest`** (nessun mondo, 0,1 s): 1800 perdite (le tre fini, sei classi, con e senza interno): le persone tornano, nessun faro senza sopravvissuti, nessun NaN; determinismo byte per
  byte; il moto è punto + velocità, i detriti restano nel raggio del campo più veloce, a un secondo come a quattro giorni; il file torna com'era e costa poco; i limiti; gli eventi (il faro
  una volta e con **tutte** le capsule, il silenzio, lo sguardo da vicino anche dal Falcon, in battaglia sono notizie); il soccorso; la consegna senza salti; **la tavola degli equipaggi
  uguale ai piani**;
- **quattro navi perse in un mondo** (una per ogni fine): registrate, capsule, i fari sentiti, uno sguardo, il soccorso detto e contato, il salvataggio rileggibile, **il ripristino a metà**;
  lo stesso scenario due volte (stessi eventi); **40 relitti insieme**: le invarianti reggono e costa meno di 0,1 ms a tick.

## 8. Messa in servizio (per il lead)

1. `git merge worktree-agent-aa357b4b05aab282f` (il ramo prosegue quello di `worktree-agent-a7d3df7e6454139e6`: contiene M1 e ha già unito main), poi la solita ricompilazione.
2. **Una volta**, nell'editor: `tools/ue.py pyfile tools/ue_scripts/make_space_materials.py` (marca per le istanze i materiali di base delle sezioni delle navi, dei detriti e delle
   capsule; stampa `SPACE_MATERIALS_OK`), poi riavviare (gli shader della permutazione istanziata si compilano una volta).
3. Nel gioco, con il banco (`tools/play.py`) o la console: `astra.space.lose T-02 breakup 1` (il Vigilant della scorta si spezza al centro), poi `astra.space.look wreck 1.5`: l'Aquila a
   1,5 km dal pezzo più vicino. Per i **primi 80 s** i pezzi sono attori degli effetti (fuochi sui tagli); a 80 s passano a istanze **scure**: la prova è che non saltino e che le finestre
   siano spente. Se sono grigi: il passo 2.
4. Dopo 20–60 s: la riga **«sensors: distress beacons …»** (quattro capsule), i fari che lampeggiano sul cielo (`astra.space.look pod 3`), poi `flight` con missione `sar` (a voce:
   «Price, soccorso alle capsule») o `astra.space.rescue 10`: la riga di salvataggio.
5. `astra.space.wrecks.list`, `astra.space.stat`: i numeri. Salvataggio e ripresa: `astra.space.wrecks.resume` (distruttivo) e il log «resume check: SAME».
6. Il costo: `astra.space.stat` con una battaglia vera, e `stat astra` per il fotogramma (la voce «Space life»).

**Cosa guardare per primo**: (a) che le sezioni istanziate abbiano il materiale giusto (scuro, non grigio) e tengano la posizione dopo il passaggio a 80 s; (b) che i detriti si vedano da
vicino (3–22 km) e non pesino; (c) che i fari si vedano da lontano; (d) la memoria del gioco (era a ~8 GB su 9): le mesh dei detriti e delle capsule sono poche migliaia di triangoli.

## 9. Ganci in file di altri moduli (tutti piccoli, tutti commentati, due commit separati)

| File | Cosa | Perché |
|---|---|---|
| `AstraBattleSubsystem.cpp` `Destroy` | `Space->OnShipLost(S, E, bFxDone)` dopo `DeathEvents.Add(E)`; il vecchio `LastWreckPos/Name` solo se lo spazio non è attivo | il gancio nominato |
| `AstraBattleSubsystem.cpp` `SaveJson`, `ResumeFrom`, `StartCampaign` | `space` nel salvataggio; `NewCampaign` + `LoadSaved` prima di `Arrive`; `NewCampaign` | la persistenza |
| `AstraBattleSubsystem.cpp` `LaunchSquadron` | la missione `sar` si può dare anche se `HasBeacons()` | il soccorso |
| `AstraWarCraft.cpp` ramo `sar` | un ramo nuovo prima del vecchio: ogni velivolo vola al suo faro e prende le capsule | il soccorso |
| `AstraWarFX.h` / `AstraWarFXHull.cpp` | `GetPieces()` (una riga), `ReleasePiece(ShipId, Section)` (una funzione) | la consegna dei pezzi |

Richieste al lead (non le ho fatte io, sono di altri moduli):
1. **FLOTTA-VIVA**: `FAstraShipInterior::LoseWithShip` scrive «lost with all hands (N aboard)»; con le capsule non è vero. Suggerisco di togliere «with all hands» (e «N aboard» diventa «N aboard
   when she went»): chi si è salvato lo dice il faro. Oggi l'equipaggio può sentire «lost with all hands» e poi «distress beacons … 19 survivors».
2. **CAMPAGNA**: `UAstraCampaignSubsystem::NewCommand` scrive `battle` vuoto: il relitto dell'Aquila precedente (e tutto ciò che la guerra ha lasciato) non c'è nel nuovo comando. Se si vuole
   che ci sia, basta copiare `battle.space` dal salvataggio vecchio nel nuovo.
3. **MENTE-EQUIPAGGIO**: nei prompt dei sensori (Nair) e del volo (Price) due righe su `space.wrecks` e sulla missione `sar` (vedi §3.5 e §4): oggi lo leggono dallo stato senza che il prompt lo nomini.
4. Il tasto del Falcon per prendere a bordo una capsula (`RescueTake` c'è: basta chiamarla): chi pilota il Falcon non può ancora raccogliere nessuno.

## 10. Limiti noti e cosa farei dopo

- **Mai visto nel motore**: l'aspetto dei pezzi morti (la copia dinamica dei materiali per slot), le dimensioni dei detriti e dei fari, i costi di render. Il banco misura il costo di CPU
  del modulo (con le istanze contate, non scritte); il resto lo misura il lead.
- **Le navi disattivate** (`bDisabled`: derelitti abbordabili) non si registrano: spariscono con il sistema com'era. È il passo naturale dopo: registrarle quando il sistema si lascia e
  rimetterle come contatti derelitti al ritorno (serve `SpawnClass` + lo stato spento della guerra: l'ho lasciato fuori perché tocca le regole).
- I relitti **non sono contatti** del piano tattico né del tavolo olografico: si vedono dal finestrone e dallo schermo principale, si sentono dai fari, e `space.wrecks.nearest` li dice alle menti.
- Nessun danno da detriti, nessuna collisione con i pezzi (il Falcon ci passa attraverso: §M3 per le strutture; per i relitti lo faccio con lo stesso gancio se il lead vuole).
- `HandOverS` è 80 s fisso (le facce di taglio si raffreddano in 60 s): se VFX cambia quel tempo va cambiato anche qui.
- Le ore di campagna che passano senza giocare (la mente fa passare «settimane») non invecchiano i relitti: il gancio c'è (`AdvanceWrecks`), va chiamato da chi sa quanto è passato.
