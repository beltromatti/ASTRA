# La guerra grande a 60 fps — com'è fatto il modulo SCALA (fase F2.3)

*Documento del modulo SCALA (2026-10-01). Cosa c'è nel codice, perché è fatto così, come si prova, come si mette in servizio e come si
tara. I nomi nel gioco e nei dati sono in inglese; il documento in italiano. Il progetto del modulo è in
[brief/SCALA.md](brief/SCALA.md); la simulazione che regge la scala è in [GUERRA.md](GUERRA.md) (§5, §7.5); gli effetti a istanze da cui
questo lavoro prende il metodo sono in [VFX.md](VFX.md).*

**Stato: scritto, compilato e provato sul banco (senza grafica); mai visto nel motore.** Il modulo è stato costruito senza avviare
l'editor né il gioco (regola dei moduli di supporto). Tutto ciò che si può provare con la simulazione è provato: i velivoli e le luci a
istanze lasciano la simulazione identica (stessi esiti, seme per seme), il tavolo olografico è controllato su immagini disegnate dal
banco partendo da battaglie vere, gli scenari nuovi girano. Quello che nessuno ha ancora potuto fare è guardare il disegno e misurare i
fotogrammi: il primo passo del lead è la lista del §11, la misura è quella del brief (`astra.war.scenario scale_30x150 aquila`, §9).

## 1. Il problema e il principio

Con 30 navi capitali e 150 velivoli attorno all'Aquila il gioco teneva 57–58 fps ma il game thread era a 13,8 ms e il render thread a
14,8 ms (misura del lead dalla plancia: WorldTickMisc 3,95, EndOfFrameUpdates 3,42, Tickables 2,53, TickActors 1,53; render:
RenderOther 3,9, UpdatePrimitiveTransform 1,27, attesa della visibilità 1,65; GPU 12,8 ms a risoluzione dinamica ~47 %). La simulazione non
c'entra (0,04–0,09 ms a tick: GUERRA §7.5): il costo era nel **disegno e nelle domande che ognuno fa a ogni fotogramma**. Ogni velivolo era un
attore con la sua mesh, un componente per le luci di navigazione che tickava, un componente e un materiale dinamico per ogni lampada
(712 componenti per i 148 velivoli di picco, più quelli delle navi); il tavolo olografico faceva per ogni contatto, velivoli compresi, un
disegno di icona, stelo, vettore, linea guida e un testo; una dozzina di lettori (schermi, tavolo, schermo principale, HUD della finestra, Falcon)
rifaceva ciascuno la sua lista dei contatti.

Il principio è quello degli effetti di VFX: **il costo deve crescere con ciò che si vede, non con ciò che c'è**. Un componente istanziato per
tipo di scafo, un solo livello di lampade, una lista condivisa per fotogramma, e un tavolo che decide che cosa mostrare prima di toccare un
componente.

## 2. I file

| File | Cosa contiene |
|---|---|
| `Source/ASTRA/AstraWarDraw.h/.cpp` | **`UAstraWarDraw`**: gli scafi dei velivoli (una ISM per tipo di scafo, slot stabili, vettori di moto veri) e le luci di tutte le navi (un solo livello `M_WAR_Glow`); `AstraDraw::MakeComp` (il componente istanziato, usato anche dal tavolo) |
| `Source/ASTRA/AstraNavLights.h/.cpp` | la tavola delle lampade (`FAstraNavLamp`, `LampsFor`) e gli schemi di lampeggio (`PatternOn`), condivisi fra il componente di prima (Aquila, capsule di salvataggio) e le luci a istanze |
| `Source/ASTRA/AstraBattleSubsystem.h/.cpp` | `SpawnVisual` chiede a `UAstraWarDraw` di prendersi il velivolo; le liste condivise; i contatori di costo (`PerfReport`, `stat astra`); `StartCampaign` fuori riga e `Prewarm` |
| `Source/ASTRA/AstraBattleQueries.cpp` | le liste condivise per fotogramma: `Contacts()`, `HoloBlips()`, `PlotCounts()` (e le copie di `GetContacts` / `GetHoloBlips` per chi le modifica) |
| `Source/ASTRA/AstraHoloPlan.h/.cpp` | **il piano del tavolo**: funzioni pure su dati puri (raggruppamenti, nomi, etichette collocate); il banco lo esegue su battaglie vere |
| `Source/ASTRA/AstraHoloTable.cpp` | l'esecutore del tavolo: icone, steli e vettori mostrati una volta per fotogramma, testi cambiati al più 4 volte al secondo, velivoli e missili come punti di un solo componente istanziato |
| `Source/ASTRA/AstraViewscreen.cpp`, `AstraScreensSubsystem.cpp`, `AstraWindowHud.cpp`, `AstraFighterPawn.cpp` | leggono le liste condivise; lo schermo principale: la lente per i velivoli istanziati, croci al posto dei riquadri quando i contatti sono molti, al più 12 etichette piene |
| `Source/ASTRA/AstraWarScenario.cpp` | gli scenari grandi: i rinforzi (`waves`), l'Aquila nel file e sul comando |
| `Source/ASTRA/AstraWarPerf.cpp` | `astra.war.stat` e `astra.war.perf`: cosa tiene e cosa costa la guerra nel gioco vero |
| `Source/ASTRA/AstraWarSimCommandlet.cpp`, `tools/war.py` | il banco: `--aquila`, `--aquila-opts`, `--holo-at`; nel record `stats.draw` e `stats.plot` |
| `tools/art/holo_plan_preview.py` | disegna il piano del tavolo da un record del banco e controlla sovrapposizioni (etichetta su etichetta, etichetta su icona) |
| `tools/ue_scripts/make_scala_materials.py` | da eseguire **una volta** nell'editor: marca i materiali degli scafi dei velivoli "Used with Instanced Static Meshes" (§4.3) |
| `data/war/scenarios/fleet_battle.json` | la battaglia di flotta da campagna con rinforzi (§9) |
| `docs/progressi/scala/` | immagini del piano del tavolo sulla battaglia di flotta e sulla scala |

Un piccolo ritocco fuori dal modulo, perché un banco senza finestra potesse misurare il disegno: `AstraWarFX.cpp`, `BeginFrame`: origine e
velocità degli effetti seguono l'Aquila quando è viva in una sandbox (prima la sandbox la parcheggiava a un milione di km e tutto ciò che stava
attorno all'origine era "lontano" per gli effetti).

## 3. I velivoli a istanze (`UAstraWarDraw`)

**Niente attore, niente componente, niente tick per velivolo.** Un velivolo è una riga della simulazione (`FAstraBattleShip`); al
`SpawnVisual` la battaglia chiede a `UAstraWarDraw::Claim` se lo disegna lei. Se sì (`DrawKind >= 0`) non si crea nessun attore, e la nave
non avrà il componente delle luci (`bDrawLamps`). Una volta per fotogramma, dopo che la battaglia ha mosso le navi e prima degli effetti,
`Tick` scrive tutte le posizioni:

- **Una ISM per tipo di scafo** (Falcon, Hammer, Wasp, Harpy), a pagine di 96 istanze (`PageSize`): una battaglia più grossa fa nascere
  un'altra pagina. Le istanze sono create tutte insieme, nascoste (scala 0,0001), e **ogni velivolo tiene lo slot** per tutta la sua vita:
  vivo, la sua istanza si sposta; morto, atterrato o fuori portata, lo slot si nasconde e torna libero.
- **Vettori di moto veri.** Con le istanze il TSR (l'upscaler temporale) non può sapere come si muove uno scafo che fa 14 m a fotogramma: ogni
  istanza ha la sua trasformazione precedente (`SetHasPerInstancePrevTransforms` e `BatchUpdateInstancesTransforms` con le due liste). Un velivolo
  appena comparso non ha passato (non si sbava dal posto che il suo slot occupava prima).
- **Restano attori**: il Falcon del Capitano (è un pawn, non un velivolo della simulazione), i velivoli pilotati (`bPiloted`) e quelli il cui
  scafo non si può disegnare a istanze (mesh mancante, o materiali senza il flag, §4). `Claim` li rifiuta e `SpawnVisual` prosegue per la
  vecchia strada.
- **Livelli di dettaglio per distanza dall'Aquila** (§5): lo scafo di un velivolo si disegna fino a 80 km (`astra.war.draw.hull_km`);
  oltre, resta solo il suo bagliore. Nessuno scatto: il passaggio da istanza a niente è sotto il pixel; le mesh Nanite si semplificano da sole.
- **La lente dello schermo principale.** Quando la telecamera dello schermo principale è zoomata su un bersaglio lontano (FOV < 12°), i nostri
  velivoli più vicini della metà della distanza del bersaglio le passerebbero davanti come forme enormi e sfocate. Prima si nascondevano alla
  cattura attore per attore (`HiddenActors`); ora sono in un **secondo insieme di pagine** (`Sets[1]`) che la cattura esclude
  (`HiddenComponents`, da `GetNearLensComponents`): un velivolo passa da un insieme all'altro una volta, quando attraversa la soglia. Il
  velivolo mostrato (`LensExempt`) non è mai nascosto.
- **Prezzo**: `Tick` costa in media 0,004 ms sul banco con 148 velivoli e 186–232 lampade (massimo 0,016 ms); con 296 velivoli e 430 lampade 0,009 ms
  (massimo 0,023). Sostituisce 148 attori e 712 componenti (296 e 1424 nel doppio): i numeri "di prima" sono contati dal modulo stesso con la
  stessa regola della vecchia strada (`stats.draw.actors_it_replaces_peak`, `components_it_replaces_peak`).

### 3.1 Le luci

Tutte le lampade di tutte le navi, velivoli e navi capitali, sono **istanze di `M_WAR_Glow`** (il bagliore di VFX: colore, intensità e
dimensione per istanza, minimo 3 pixel, dissolvenza morbida con la profondità) in **un solo livello** (`AstraFx::FLayer`, 1400 istanze di
capienza, `CapLamps`). Il livello è riscritto ogni fotogramma con le sole lampade accese: la parte buia di un lampo non è un'istanza.

- La tavola delle lampade (dove sta ciascuna, colore, dimensione, intensità, schema) è quella di prima (`data/ship/nav_lights.json` letta
  da `UAstraNavLights::LampsFor`), e gli schemi (fisso, doppio lampo bianco, impulso rosso lento) sono `UAstraNavLights::PatternOn`: il
  componente di prima (Aquila, capsule) e le istanze usano lo stesso codice, quindi lo stesso aspetto.
- **Livelli di dettaglio**: le luci di un velivolo sfumano con la distanza, le fisse prima (fra 7,5 e 15 km, `astra.war.lamps.craft_km` / 2), il
  lampo bianco dopo (fra 18 e 30 km, `astra.war.lamps.craft_km`); le luci di una nave capitale restano fino ai limiti del sistema (sfumano
  fra 180 e 250 km). Nessuna soglia è un salto (curva morbida). Le navi disattivate o relitto non accendono luci.
- Ogni nave ha la sua fase: due navi non lampeggiano insieme.
- La luminosità (`astra.war.lamps`, che segue anche `astra.fx.intensity` degli effetti) è la stessa tavola di intensità di prima, in una scala
  vicina a quella dei bagliori degli effetti (160–900 contro i 160–700 di VFX): è **una stima da guardare**, non una misura.

## 4. Cosa serve perché funzioni

1. **I materiali degli scafi dei velivoli** devono avere il flag "Used with Instanced Static Meshes": l'istanza di una mesh Nanite il cui
   materiale non lo ha viene disegnata con il materiale di default (grigio), e in un gioco il motore non può impostare il flag (solo un editor che
   non sta giocando, al primo uso). `tools/ue.py pyfile tools/ue_scripts/make_scala_materials.py`, **una volta**, nell'editor: marca i materiali di
   base degli scafi dei quattro velivoli, controlla quelli di `M_WAR_*` e salva (`SCALA_MATERIALS_OK` in uscita). Poi riavviare: i shader della
   permutazione istanziata si compilano alla prima volta (qualche minuto di attesa).
2. **La guardia a runtime**: finché il flag non c'è, `UAstraWarDraw::KindFor` lo vede (`GetUsageByFlag(MATUSAGE_InstancedStaticMeshes)`),
   scrive nel log `[WarDraw] SM_CRAFT_...: its materials (...) are not flagged ... so its craft stay actors` e quei velivoli restano attori come prima
   (le loro luci invece sono già a istanze: un componente in meno per velivolo). Nessun velivolo grigio: o istanze giuste o la vecchia strada.
3. `M_WAR_Glow` (`tools/ue_scripts/make_war_fx.py`, di VFX) deve esistere; senza, tutto il modulo resta spento (`[WarDraw] M_WAR_Glow missing`).

## 5. I livelli di dettaglio

| Cosa | Dove | Come |
|---|---|---|
| Scafo di un velivolo | disegno | istanza fino a 80 km (`astra.war.draw.hull_km`), poi niente (resta il bagliore delle luci fino al suo limite) |
| Luci di un velivolo | disegno | fisse sfumano fra 7,5 e 15 km, lampo fra 18 e 30 km (`astra.war.lamps.craft_km`) |
| Luci di una nave capitale | disegno | fino a 180 km, sfumano a 250 |
| Mesh delle navi capitali | disegno | Nanite (da sé); gli scafi restano attori: sono pochi e gli effetti li usano (pezzi, graffi, luci che si spengono) |
| Velivoli vicini alla lente | disegno | insieme di pagine separato, escluso dalla cattura dello schermo principale (§3) |
| Etichette e icone del tavolo | tavolo | raggruppamenti, punti, budget di etichette (§7) |
| Contatti dello schermo principale | schermo | croci al posto dei riquadri sopra 48 contatti, al più 12 etichette piene (poi solo la sigla) |
| Simulazione | — | **non serve, e non è stata fatta** (vedi sotto) |

**Perché nessun livello di dettaglio nella simulazione.** Il brief lo chiedeva "dove serve". Misurato sul banco (seme 1, 300 s): 30 navi +
148 velivoli costano **0,11 ms a tick in media** (p95 0,24, massimo 0,33); con 60 + 296 **0,32 ms** (p95 0,79, massimo 0,97); la battaglia di flotta
del §9 (fino a 71 navi e 137 velivoli insieme) 0,19 ms (p95 0,27). Il budget del game thread è 8 ms: la simulazione è il 2–4 % anche col doppio
della scala. Un simulatore "a frequenze diverse per la distanza" aggiungerebbe complessità e toglierebbe il determinismo seme per seme che
rende la simulazione provabile, per un guadagno che il game thread non vedrebbe. Se la simulazione crescerà (menti più pesanti, più navi) la leva
che il §7.8 di GUERRA già nomina — separazione e ricerca dei bersagli più radi per i velivoli lontani — è lì; oggi non conviene.

## 6. Le domande per fotogramma, condivise

Prima: ogni lettore (schermo principale, le schermate, il tavolo, l'HUD della finestra, i velivoli del Capitano, le postazioni) chiamava
`GetContacts` / `GetHoloBlips` e ne riceveva una copia fatta per lui (143 contatti e 168 punti a 120 s sul banco: 0,015–0,05 ms ogni volta; una
dozzina di volte per fotogramma). Ora:

- `UAstraBattleSubsystem::Contacts()`, `HoloBlips()`, `PlotCounts()` (navi e velivoli per parte, missili) sono costruite **una volta per passo
  della battaglia** (`PlotStamp`, incrementato a fine tick, a ogni nave nuova e a ogni `ClearSystem`) alla prima lettura e restituite per
  riferimento a chi le chiede dopo. Il costo di una costruzione sul banco: 0,013–0,05 ms con 140–350 contatti.
- I lettori che non devono cambiare la lista la leggono per riferimento: schermo principale (`PlotRef`), schermate (la pagina dei sensori
  ordina un array di puntatori, non la lista condivisa), HUD della finestra, il Falcon. `GetContacts` e `GetHoloBlips` restano **copie** per
  chi le modifica o le tiene oltre il passo (le postazioni: un puntatore nella lista condivisa sarebbe sospeso al passo dopo).
- I punti per il tavolo (`FAstraHoloBlip`) costano meno: il capo-volo e il conteggio di ogni squadriglia si trovano in un solo passo (prima: una
  ricerca quadratica), i missili cercano il bersaglio con l'indice per id, il nome e il contatto dei velivoli solo per il capo-volo; i punti ora
  portano `bFiringAtUs`, `Id` e `Squadron`, che il piano del tavolo usa.

## 7. Il tavolo olografico con 50 contatti e più

Con cinquanta contatti e più il tavolo di prima era una torre di testo su un mucchio di componenti: per ogni contatto un'icona, uno stelo, un
vettore, una linea guida, un'etichetta che saliva sopra le altre nel piano dell'osservatore (6 passate) e il cui testo era riscritto ogni
fotogramma. Ora il tavolo **decide prima cosa mostrare** (`AstraHoloPlan`, funzioni pure) e poi lo mostra (`AstraHoloTable.cpp`).

### 7.1 Il piano (`AstraHoloPlan::Make`)

- **I velivoli sono punti**, non icone: un solo componente istanziato per il tavolo (`M_WAR_Glow`, 700 istanze, un colore per istanza: ASTRA,
  ostili, altri; i missili più luminosi), e **un cartellino per squadriglia** (sigla, numero, distanza; al più 6), non per velivolo.
- **Le navi sono raggruppate quando sono molte** (più di dieci oltre l'Aquila): le navi della stessa parte che volano insieme (vicine
  meno di `clamp(0,12 × portata, 2,5, 8)` km, 1,3 volte tanto se erano già insieme al fotogramma prima: nessun sfarfallio al bordo) sono **un
  cartellino** con parte, numero, distanza e rilevamento ("MANDATE x8 / 55 km · 007"); i gruppi di meno di tre non si raggruppano.
- **Chi ha un nome proprio** in una folla: l'Aquila, il bersaglio del controllo del fuoco, chi ci spara (le sei navi più vicine; le prime dodici
  hanno la loro linea rossa verso l'Aquila) e le otto più vicine fra le altre che non sono in un gruppo; il tetto è 16 etichette.
- **Icone più piccole nella folla** (`sqrt(10/N) × 1,25`, fra 0,5 e 1): una flotta non è un mucchio di punte di freccia. Steli e vettori solo
  per chi conta, quando il tavolo è fitto.
- **Le etichette si collocano nel piano dell'osservatore** (come lo vede chi è seduto, con l'inclinazione del proiettore), in otto posti attorno
  alla sua icona su fino a cinque anelli (due per le non obbligatorie: se non trovano posto non si mostrano; le obbligatorie sì, dove coprono meno): a
  destra, a sinistra, sopra, sotto e le quattro diagonali, un'altezza di etichetta più in fuori a ogni anello, con una linea guida
  dall'anello 2 in poi. **Nessuna etichetta copre un'altra etichetta né un'icona**, e **ricordano il posto** da un fotogramma all'altro (finché è
  libero): niente salti.
- Costo del piano sul banco: 0,01–0,02 ms a piano con 150 contatti.

### 7.2 L'esecutore (`AstraHoloTable.cpp`)

- Il piano è rifatto **30 volte al secondo** sopra 80 punti (in un trentesimo di secondo sul tavolo non cambia nulla che un occhio veda); sotto,
  a ogni fotogramma.
- **Niente componenti ricreati**: icone, steli, vettori, linee guida e testi stanno in pool. Steli e vettori si mostrano **una volta per
  fotogramma** (prima si accendevano e si spegnevano nello stesso fotogramma e rifacevano lo stato di render due volte: `PooledQuiet`).
- **I testi si cambiano solo ai cambi**, e al più 4 volte al secondo per etichetta (le etichette sono legate al loro posto di testo dalla
  chiave della nave o del gruppo, quindi un'etichetta che resta resta sullo stesso componente). Gli `HoloSet*` esistevano; qui contano le
  scritture: ogni `Set*` di un `UTextRenderComponent` rifà il proxy di render, anche a valori uguali.
- **`astra.holo.dots`** (default 1): intensità dei punti dei velivoli e dei missili (sono istanze del bagliore di guerra, non del materiale del
  tavolo: se risultano troppo vivi o troppo spenti si tara qui senza ricompilare).

### 7.3 Come è controllato (senza il motore)

Il banco esegue il piano su una battaglia vera e ne scrive il risultato: `tools/war.py run --scenario fleet_battle --seconds 420 --holo-at
60,140,200,260,330,400` scrive `Saved/War/holo_<t>.json`, e `uv run --python /opt/homebrew/bin/python3.13 --with pillow python
tools/art/holo_plan_preview.py Saved/War/holo_*.json --out <dir>` lo disegna (il disco con gli anelli di portata, le icone, i punti, i gruppi,
ogni etichetta nel suo riquadro e con la sua linea guida) e **controlla** le sovrapposizioni (esce con 1 se ce n'è). Risultato sulla battaglia
di flotta e sulla scala (6 + 2 piani, da 31 a 66 navi e fino a 144 velivoli): 9–15 etichette per piano, **0 sovrapposizioni**, 2–6 gruppi.
Le immagini: `docs/progressi/scala/holo_fleet_060s.png` (l'inizio: gruppi, stormi, l'Aquila), `holo_fleet_260s.png` (la mischia, con 53 navi e
104 velivoli), `holo_fleet_400s.png` (le linee guida lunghe), `holo_scale_080s.png` (la misura del brief a 80 s).

Quello che il banco non può giudicare è l'aspetto: la dimensione dei caratteri, la luminosità dei punti, quanto sia bello. Lo giudica il lead.

## 8. Lo schermo principale, le schermate, l'HUD della finestra

- **Schermo principale** (`AstraViewscreen.cpp`): legge la lista condivisa; con più di 48 contatti disegna i velivoli come **croci** (al più 96
  segni) e le navi con riquadro, e dà l'etichetta piena ad al più 12 (poi solo la sigla); la lente per i velivoli istanziati (§3).
- **Schermate** (`AstraScreensSubsystem.cpp`): le pagine leggono `Contacts()` / `HoloBlips()` / `PlotCounts()`; la pagina dei sensori ordina
  un array di puntatori.
- **HUD della finestra** (`AstraWindowHud.cpp`): già scartava i velivoli oltre 6 km e i contatti non tracciati; ora legge la lista condivisa.
- **Falcon del Capitano** (`AstraFighterPawn.cpp`): la lista condivisa.

## 9. Gli scenari grandi

Comandi nel gioco (console) e nel banco:

```
astra.war.scenario scale_30x150 aquila              # la misura del brief: l'Aquila ferma all'origine, tra le due flotte
astra.war.scenario scale_30x150 aquila at=-34,0,0   # la stessa battaglia con l'Aquila 34 km indietro, dietro la linea ASTRA: regge a lungo
astra.war.scenario fleet_battle                     # la battaglia di flotta di campagna con rinforzi (l'Aquila è nel file)
astra.war.scenario <nome> aquila hold|speed=<m/s>|heading=<gradi>|at=<x_km>,<y_km>,<z_km>
tools/war.py run --scenario fleet_battle --seconds 900 [--aquila-opts "at=-34,0,0;speed=0"] [--holo-at 60,260]
```

- **`aquila`** (parola sul comando, oppure `"aquila"` nel file) tiene l'Aquila nella battaglia con la parte ASTRA, **ferma dove la si
  mette** (l'origine, o dove dice il file o `at=`), prua verso +x, il timone a riposo: la stessa prova ogni volta. `speed=` e `heading=` la
  mettono in moto. Le opzioni possono stare prima o dopo la parola `aquila`.
- **Il file** (`data/war/scenarios/<nome>.json`, formato in testa a `AstraWarScenario.cpp` e in [GUERRA.md](GUERRA.md) §7) ha ora, oltre ai
  gruppi di ogni parte, **`"waves"`** (i rinforzi: `{"at_s": secondi di battaglia, "side": "astra"|"mandate", "group": {un gruppo come gli
  altri, con i suoi velivoli e il suo "protects"}}`; al suo tempo il gruppo nasce, si annuncia nella riga degli eventi di gruppo — "reinforcements
  arriving: M-22 (lethe), ..." — e il "protects" si risolve sui gruppi già in battaglia) e **`"aquila": {"at_km", "heading", "speed", "wings"}`**
  (dove sta, come va e il suo stormo, che parte dai suoi tubi di prua come nel gioco).
- **`fleet_battle`**: l'Aquila ferma 16 km dietro la linea della 7th Fleet (due Praetorian con i loro hangar, ali di cacciatorpediniere ai
  fianchi), l'Interdiction Fleet del Mandato da est (tre portaerei Acheron con scorta, una linea di Styx, due cunei di razziatori): 37 navi
  e un centinaio di velivoli all'inizio, **sette ondate** (razziatori a 90 s, colonna di soccorso ASTRA a 170 s, secondo gruppo di portaerei
  a 200 s, linea di Styx a 330 s, flottiglia di cacciatorpediniere ASTRA a 380 s, terzo gruppo di portaerei a 460 s, seconda colonna di soccorso
  a 560 s): **fino a 71 navi e 137 velivoli insieme**, più di 800 s di azione (seme 1: l'Aquila a fine prova al 76 %, 38 navi ASTRA e 28 del Mandato
  vive, 160 velivoli del Mandato lanciati e 102 ASTRA). La classe delle navi non ha altra portaerei ASTRA che l'Aquila: il suo stormo parte da lei e
  le due Praetorian ospitano ali (una licenza del banco).
- **L'Aquila all'origine in `scale_30x150` muore a 90 s circa** (seme 1–4, uguale): è sola tra le due flotte e tutti i bombardieri (30 siluri)
  vanno su di lei. È la misura del brief (il lead misura a 90 s dal lancio, poco prima), ma per un tratto di misura lungo conviene `at=-34,0,0`
  (regge 400 s) o `fleet_battle`.

## 10. Misure (offline: il banco senza grafica)

Banco, seme 1, `-nullrhi`, un Mac condiviso con altri lavori (i tempi variano da una prova all'altra).

| | prima | dopo |
|---|---|---|
| esito della simulazione (`scale_30x150`, 300 s, seme 1): stati finali, eventi, fotogrammi | | **identici** (solo percorso del file e tempo di muro differiscono) |
| tick della battaglia, 30 + 148 (media / p95 / max) | 0,12 / 0,27 / 0,51 ms | 0,11 / 0,24 / 0,33 ms |
| disegno a istanze, 30 + 148 (media / max) | — | 0,004 / 0,016 ms |
| tick della battaglia, 60 + 296 (media / p95 / max) | | 0,32 / 0,79 / 0,97 ms (disegno 0,009 / 0,023 ms) |
| tick della battaglia, battaglia di flotta, 71 navi + 137 velivoli al picco | | 0,19 / 0,27 / 0,35 ms |
| attori e componenti dei velivoli e delle luci, 30 + 148 | 148 attori, 712 componenti (più le luci delle navi) | 4 pagine + 1 livello di luci (5 componenti) |
| attori e componenti, 60 + 296 | 296 attori, 1424 componenti | 5 pagine + 1 livello |
| lista dei contatti, 143 contatti | 0,015–0,05 ms × circa 12 lettori a fotogramma | una volta per passo, per riferimento |
| piano del tavolo, 150 contatti | (le etichette: un testo riscritto per contatto, a ogni fotogramma) | 0,01–0,02 ms, al più 30 volte al secondo, 16 etichette |
| sovrapposizioni delle etichette del tavolo | non misurate | 0 su 8 piani (battaglia di flotta e scala) |

**Quello che non si è potuto misurare**: i fotogrammi, il tempo del game thread e del render thread, la GPU, la memoria. La stima onesta, dal
conto dei componenti (gli attori dei velivoli e le loro trasformazioni a fine fotogramma erano il grosso di EndOfFrameUpdates e di
UpdatePrimitiveTransform, e le luci erano il grosso dei componenti che tickavano): i 148 attori e i circa 700 componenti spariscono, restano 30
attori di navi, i loro nomi dipinti, gli effetti di VFX e il tavolo; il game thread dovrebbe scendere di parecchi millisecondi dai 13,8 ms.
Dove cadrà non si sa: lo dice `astra.war.perf` (§11), lo decide il lead.

## 11. Per il lead: messa in servizio e prova

1. Unire il ramo (`worktree-agent-aca3648e81d0b72d5`) e ricompilare l'editor come sempre (`tools/ricompila.sh`).
2. **Una volta**, nell'editor: `tools/ue.py pyfile tools/ue_scripts/make_scala_materials.py` (si aspetta `SCALA_MATERIALS_OK`), chiudere,
   riaprire. Al primo avvio i shader istanziati si compilano.
3. Nel gioco, in plancia, schermo principale acceso: `astra.war.scenario scale_30x150 aquila at=-34,0,0` (l'Aquila regge); 90 s dopo,
   `astra.war.stat` (cosa tiene il disegno a istanze, il costo delle liste, i contatori degli effetti, e il censimento del mondo: attori,
   componenti primitivi, istanze, testi, decalcomanie, luci, componenti con tick) e `astra.war.perf` (il tick della battaglia diviso in
   simulazione, spostamento degli scafi, disegno a istanze, effetti: dall'ultima chiamata). Poi `stat astra` e `stat unit` / `stat game` come
   sempre: ci sono `Battle tick`, `War draw`, `War FX`, `Holo table`, `Viewscreen`.
4. **Prova A/B con la vecchia strada**: `astra.war.draw 0` *prima* di lanciare lo scenario (i velivoli già in cielo restano come nati e
   continuano a muoversi); il confronto è sullo stesso scenario.
5. Se i velivoli sono grigi o mancano: il log dice perché (`[WarDraw] ...`); se sono troppo chiare o troppo scure le luci: `astra.war.lamps` (e
   `astra.fx.intensity`); se i punti del tavolo: `astra.holo.dots`.
6. `fleet_battle` per vedere la guerra grande per una decina di minuti con i rinforzi; `scale_60x300` (senza l'Aquila: `astra.war.scenario
   scale_60x300 aquila at=-34,0,0` per vederla) per il doppio.

Tarature (cvar):

| cvar | default | cosa fa |
|---|---|---|
| `astra.war.draw` | 1 | velivoli e luci a istanze (0: la vecchia strada per ciò che nasce da quel momento) |
| `astra.war.draw.hull_km` | 80 | portata dello scafo di un velivolo (km) |
| `astra.war.lamps` | 1 | intensità delle luci di navigazione a istanze (0: nessuna); segue `astra.fx.intensity` |
| `astra.war.lamps.craft_km` | 30 | portata del lampo di un velivolo (le luci fisse metà) |
| `astra.holo.dots` | 1 | intensità dei punti dei velivoli e dei missili sul tavolo |

## 12. Limiti noti e rischi

- **Mai visto nel motore.** Gli scafi a istanze, le luci e i punti del tavolo non sono stati guardati: i punti da guardare per primi sono il
  colore e la dimensione degli scafi (se i materiali sono giusti), la luminosità delle luci e dei punti (stime), le etichette del tavolo
  (la dimensione dei caratteri) e lo schermo principale quando è zoomato con i nostri velivoli vicini (la lente).
- **Il flag dei materiali** (§4): senza lo script, i velivoli restano attori; è scritto nel log, non è un guasto.
- **Nomi dipinti sugli scafi** (`AstraHullName`, di prima): ogni nave ASTRA capitale ha un render target 2048 × 512 e due decalcomanie, creati alla
  nascita; con 38 navi ASTRA (la battaglia di flotta) sono circa 150 MB e un colpetto di qualche millisecondo per ogni ondata che arriva. Non si è
  toccato (è un gusto del lead e fuori dal modulo), ma se la GPU o la memoria restano oltre il budget è il primo posto dove guardare:
  `astra.war.stat` conta le decalcomanie.
- **Gli scafi delle navi capitali restano attori** (30–70): sono pochi, e VFX li usa.
- **Simulazione identica, non più veloce**: il modulo non l'ha toccata; il suo costo (0,1–0,3 ms) era già piccolo.
- **Il banco non vede le prestazioni di render**: la sua misura è il costo CPU del piano, delle liste e della preparazione delle istanze.
- **L'Aquila all'origine tra le due flotte muore a 90 s** (§9); la misura del brief va fatta prima, oppure con `at=`.
- `astra.war.stat` conta i componenti con un tick dei soli attori: i tick dei sottosistemi sono in `stat game`.
