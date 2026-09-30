# NAVE — l'ASN Aquila come nave vera (fase F4.1)

Il "DNA" della nave (`data/ship/aquila_plan.json`), il kit di moduli e stanze dell'interno (Blender, nel linguaggio della plancia v3), il
**Ponte 4 (Crew Services) costruito da capo a coda** e gli strumenti per metterlo nel livello. Tutto ciò che è scritto nel gioco è in inglese;
questa pagina è in italiano con i nomi ufficiali.

Stato: piano dei 12 ponti completo e verificato (0 problemi, 0 avvisi); Ponte 4 con mesh (640 posizionamenti); gli altri ponti hanno un piano
"grossolano" ma vero (compartimenti tipizzati con misure, porte, scale, grafo). Non provato in Unreal (l'editor è del lead): vedi "Limiti".

## 1. Comandi, nell'ordine

```
uv run --python /opt/homebrew/bin/python3.13 --with pillow --with numpy python tools/art/ship_textures.py          # atlante delle etichette: art/_cache/ship/
python3 art/blender/ship_plan_gen.py                                                                              # piano: data/ship/aquila_plan.json
python3 art/blender/ship_checks.py                                                                                # controlli del piano (0 problemi attesi)
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python-exit-code 1 -P art/blender/ship_kit.py   # FBX + manifest in art/export/ship
tools/ue.py pyfile tools/ue_scripts/build_ship_interior.py                                                        # il lead: materiali, kit, Ponte 4 in L_Bridge
```

Anteprime (Eevee, senza editor): `Blender -b … -P art/blender/ship_kit.py -- --no-export --no-checks --preview docs/progressi/nave --views rooms,modules,d4 --room-views best --samples 36`.
Un solo pezzo: `… -- --only Galley,S_Bulkhead,Sign_4B --no-export`. Piano in pianta: `uv run … --with pillow python tools/art/ship_planview.py 4 out.jpg [--x0 -260 --x1 -60 --scale 6 --graph]`.
Il piano è la fonte unica: lo leggono `ship_kit.py` (quali targhe e segnali servono), `build_ship_interior.py` e il gioco (`UAstraShipPlan`, che lo cerca in
`Content/ASTRA/Data/aquila_plan.json`, dove lo script lo copia, poi in `data/ship/`).

## 2. Sistema di riferimento e pila dei ponti

Come tutto il gioco: X a prua, Y a dritta, Z in su, metri (Unreal: cm, stessi assi); l'origine è il punto del pavimento della plancia sotto la poltrona del
Capitano. Lo scafo `SM_SHIP_ASTRA_Aquila` sta in (-172, 0, -62) m: coordinate dello scafo = mondo + (172, 0, 62). Ponti a passo di 4,0 m (0,3 struttura +
3,4 libero + 0,3 struttura); le stanze sono alte al più 3,7 m (il soffitto è la struttura del ponte sopra).

| Ponte | Nome | z pavimento | Contenuto (BIBBIA v0.3 §6) | Stato nel piano |
|---|---|---|---|---|
| 1 | Command | 0 | Bridge, Captain's quarters, ready room, command corridors | esistente (plancia, quarters), ready room pianificata |
| 2 | CIC & Communications | -36,7 | CIC, briefing room, department offices, communications | grossolano |
| 3 | Crew Country | -42,0 | officers' quarters, gym (e Crew Berthing, vedi §8) | grossolano; **serve la correzione dello scafo** (§8) |
| 4 | Crew Services | -46,0 | Mess Hall, galley, lounge, observation deck | **costruito** (mesh, porte, luci) |
| 5 | Science & Transport | -50,0 | science labs, Transporter Room (sei pedane), sensor archive; la navetta interna della Spine | grossolano |
| 6 | Medical | -54,0 | Medbay, surgery, quarantine, pharmacy | Medbay esistente, il resto grossolano |
| 7 | Engineering & Power | -58,0 | Main Engineering, reactor, power control, radiators | Engineering esistente, il resto grossolano |
| 8 | Marines & Armory | -62,0 | Armory, Marine Barracks, firing range, assault-shuttle bay (due Kestrel) | grossolano |
| 9 | Flight | -66,0 (Flight Deck: -72,8) | Flight Deck: launch tubes, bays, aircraft workshop, control booth | Flight Deck esistente, il resto grossolano |
| 10 | Holds & Munitions | -70,0 | holds, munitions magazines, stores | grossolano |
| 11 | Workshops & Damage Control | -74,0 | workshops, fabrication, repairs, damage-control teams | grossolano |
| 12 | Keel | -78,0 | tanks, reaction mass, maintenance crawlways | grossolano |

Le stanze **esistenti stanno dove sono** (mai spostate): il piano le registra alle posizioni dei loro file di dati (`compartments` con `status: existing`,
`data`: il file). Volumi speciali: la sala di Main Engineering (14 m) occupa anche i piani dei ponti 4–6 in x -372..-330, |y| < 15 (spazio riservato); il
Flight Deck (20 m) attraversa i ponti 6–11 in x 60..218, |y| < 29 (`spans_decks`).

**Sezioni A–H** da prua a poppa, per ponte (`decks[].sections`); i limiti stanno su una griglia di 4 m e ogni sezione è una zona con portelli stagni ai confini.
Punti fissi del canon: Mess B (Ponte 4), Berthing C, Medbay C (Ponte 6), Main Engineering F (Ponte 7), Flight Deck B (Ponte 9). Sul Ponte 4: A [104, -104],
B [-104, -160], C [-160, -248], D [-248, -320], E [-320, -384], F [-384, -440], G [-440, -484], H [-484, -524].

**Inviluppo** (`decks[].envelope`): la mezza larghezza utile per x, calcolata dalla matematica dello scafo (`shipgen2.astra_ship2`: sezioni ottagonali smussate, blocco
superiore, isola) meno 1,5 m di parete; nessun compartimento esce dall'inviluppo (controllo).

## 3. Il reticolo di 4 m

Corridoio = "fessura" di 4 m (3,1 m liberi + 0,45 di parete per lato); moduli lunghi 4 m con l'origine sul pavimento, sull'asse, all'estremità di poppa
(`x` 0..4); giunzioni 4 × 4; le stanze sono multiple di 4 m e le loro porte cadono sul centro di un modulo (x locale ≡ 2 mod 4). Stanza: origine sul pavimento
all'angolo lato corridoio, x lungo il corridoio, y **dentro** la stanza; a sinistra (babordo) il layout ruota di 180°, lungo y di ±90°. Porte 1,6 × 2,4 (`AAstraDoor`:
larghezza 160, altezza 240), cancelli 3,2 × 3,0, portello stagno di sezione 2,0 × 2,5 (le due ante scorrono nei pilastri e restano nella fessura), boccaporti cabina 0,95 × 2,1.

**The Spine** (tono S, accento "command", luce bianco-fredda) è il corridoio centrale (y = 0) e i due **Starboard/Port Passage** (tono P, "engineering", caldo) a y = ±20;
i collegamenti a croce le uniscono attraverso le corsie interne (16 m di profondità) e le corsie esterne (16 m, dal passaggio verso lo scafo). Sul Ponte 4 la Spine è spezzata
dalla sala Mess e dal Concourse: il traffico passa dai passaggi laterali (SPF prua, SPM mezzo, SPA poppa).

## 4. Lo schema del piano (`data/ship/aquila_plan.json`, versione 1)

Compatto, generato (`ship_plan_gen.py`), letto dal gioco (`UAstraShipPlan`: **campi, tipi di arco e `p` in metri sono stabili**: se cambiano, dirlo). Chiavi: `id, version,
generator, frame, decks, compartments, doors, vertical, transit, graph{nodes, edges}, systems, placements, notes`.

- `decks[]`: `id, name, programme, z, clear, ceiling, structure, pitch, volume, envelope{x_fwd, x_aft, half_width[[x, hw]…]}, sections[{id, x:[min, max]}]`.
- `compartments[]`: `id, deck, section, kind, name, bounds[x0, y0, x1, y1] (mondo, m), z[pavimento, soffitto], status (built | planned | existing), doors[], dept, systems[],
  stations[], lights[]`; le stanze fatte: `prefab, mesh, pos, yaw, plate, lane, size[L, D, h], crew_slots`; i corridoi: `passage, modules[i0, i1], tone`; le esistenti: `plane`
  (il ponte su cui poggiano), `label_deck` (il numero scritto sulla porta, se diverso), `entrance, data, capacity, spans_decks, note`.
  - `stations[]`: dove sta la gente: `id, role, kind (sit | stand | work | eat | sleep | watch), pos[x, y, z], yaw, dept` (le usa il posizionamento dell'equipaggio; i posti seguono l'arredo vero).
  - `lights[]`: `id, type (rect), pos, lumens, temperature, size[x, y], radius, shadows` (in assi del mondo): il modello per le luci di zona.
- `doors[]`: `id, deck, pos[x, y, z], yaw (90 = porta in un muro lungo x), width, height, kind (door | gate | blast | sliding), a, b (compartimenti), locked`, più `wall, passage, plate,
  side, boundary` (blast: `[sezione aft, sezione fwd]`), `existing` (i portali delle stanze esistenti: il piano li chiama cancelli, le loro ante statiche restano).
- `graph.nodes[]`: `id, deck, p[x, y, z], kind (corridor | door_in | room | station | stair | lift | lift_core), comp`. `graph.edges[]`: `a, b, len, kind (walk | door | stair | lift),
  door, w, blast, cost`. Un nodo di corridoio per modulo (ponti costruiti) o per compartimento da 16 m (grossolani); ogni stanza ha un nodo dietro ogni porta, un `hub` al centro, un nodo per
  posto; i portelli stagni sono archi `door` con `blast: true`. Un solo componente connesso (verificato): ogni compartimento è raggiungibile.
- `vertical[]`: `lift_main` (turboascensore: `landings[]` con `deck, plane, room, pos, node, existing`, `ride`) e una colonna di scale per torre (`stair_<x><n|p>`: `nodes`, `towers` per ponte).
- `transit[]`: `spine_shuttle` (Ponte 5, riservata, pianificata: fermata in ogni sezione).
- `systems`: per sistema di bordo (reactor, power_bus, coolant, radiators, sensors, comms, weapons, ordnance, life_support…) i compartimenti che lo ospitano (i corridoi portano i bus e non sono elencati).
- `placements{ponte: [...]}`: cosa mettere nel livello: `mesh, pos, yaw, folder, label, cls (module | room | sign | plate), comp`.

Controlli del piano (`ship_checks.py`): dentro l'inviluppo; nessuna sovrapposizione in 3D; porte sui muri (≤ 0,65 m dai limiti del compartimento) e di misura giusta (≥ 0,9 × 1,9 m);
grafo connesso, ogni compartimento raggiunto, archi sensati, scale e ascensore raggiungibili; nessuna stanza a cavallo di due sezioni; punti fissi del canon; ogni sezione con almeno un compartimento.
Risultato del piano attuale: 2266 compartimenti, 1048 porte, 3804 nodi, 3940 archi, **0 problemi, 0 avvisi**.

## 5. Il Ponte 4 (Crew Services, z -46)

Costruito da `ship_deck4.py` con il motore `ship_layout.py` (Builder/Passage/Deck): passaggi, corsie con elenchi espliciti (le somme tornano al metro), collegamenti a croce, torri delle scale,
specials a mano. Mappa (immagini `docs/progressi/nave/d4_plan*.jpg`):

- **A** [104 → -104] — the forward recreation deck: Bow Observation (20 × 32, finestra panoramica a prua), Library, Games Room, Quiet Room, Hydroponics Bay, stores, heads, laundry, Crew Lounge accanto
  al Concourse, due Observation Deck sui fianchi; la torre delle scale di prua (x 44).
- **B** [-104 → -160] — the hub: **Mess Concourse** (17,7 × 36: portale della Mess Hall, banco degli ascensori, stele con la mappa, isola di piante, panche), Mess Hall (esistente), Main Galley con Galley Pass,
  Dry Stores, un Observation Deck; la torre delle scale (x -92).
- **C** [-160 → -248] — Berthing Lobby (atrio di Crew Berthing, esistente), Cold Stores, stores.
- **D–G** — la Spine verso poppa (la sala Engineering occupa il centro tra x -329 e -373: i passaggi laterali portano il traffico), stanze interne ed esterne fino a x -484 (l'inviluppo si stringe a poppa),
  torri delle scale a x -300 e -452. **H** ha solo corridoi e stores interni.
- Numeri: 202 compartimenti (125 tratti di corridoio da 16 m), 455 moduli, 75 stanze, 72 targhe, 38 segnali di sezione; 74 porte, 10 cancelli, 20 portelli stagni (uno per confine di sezione e passaggio); 242 luci, 290 posti.
- Segnaletica: targa sopra ogni porta (`SM_SHIP_Plate_<stanza>`, lato corridoio) e segnale di sezione a due facce su ogni portello (`SM_SHIP_Sign_<ponte><sezione>`: "DECK 4 · SECTION E" dice in che sezione sei).

## 6. Il kit (`art/blender/ship_*.py`)

Linguaggio della plancia v3: composito scuro in cornici di metallo spazzolato, nervature con linee di luce, lampade a palette (`MI_BRG3_Lamps*`: la cella dice il colore: command, engineering, white_warm…), un solo slot per
tutte le etichette (`MI_SHIP_Labels`, atlante `T_SHIP_Labels`). Ogni mesh è chiusa alla luce (sovrapposizione di 2 cm, soffitti chiusi: lo scafo non ferma il sole), Nanite (quelle con un vetro restano classiche: le tre
di osservazione), collisione complessa come semplice, UV a 1 m (`box_uv`) e per cella per lampade e etichette. Budget: **79 mesh, 2,76 M triangoli in tutto, la più pesante 131 k** (i triangoli in Nanite non sono il costo;
il costo è la memoria: circa 160 MB di FBX su disco, non in git).

| Gruppo | Mesh | Note |
|---|---|---|
| Moduli di corridoio (2 toni × 16) | `SM_SHIP_<S|P>_` `Straight_A/B/C, Door_L_A/B, Door_R_A/B, Door_LR, Gate_L/R/LR, Bulkhead, T_L, T_R, X, End` | 17–57 k triangoli; pannelli, prese d'aria, armadietti, quadri elettrici, estintori, pronto soccorso, condotti, schermi; la Bulkhead porta il portello stagno con strisce di pericolo e il campo del segnale |
| Stanze di servizio | Galley, GalleyPass, StoreDry(+D10), StoreCold, Hold, Heads, Laundry, Hydro | cucina professionale (fuochi, cappa, celle frigo, isole con pentole appese), scaffali con casse, container ISO, docce, lavatrici, serre a tre ripiani |
| Stanze sociali | Lounge, Games, Library, Quiet, Observation(+D14), BowObs | salotti su tappeti, bar con sgabelli, biliardo, sale da gioco, libri a file, sala di raccoglimento con anello di luce, finestre con vetro |
| Stanze di lavoro | Lab, Workshop, Armory, Cabins | banchi con scaffali di reagenti, cappe, tavolo olografico; torni, fresa, saldatura, carroponte; gabbia, rastrelliere, manichini; corridoio comune e otto cabine con cuccette |
| Snodi e verticali | Concourse, BerthLobby, StairTower(+Top, +Bottom), LadderTrunk | torre: due rampe a tornante, pozzo, scala a pioli con boccaporto; alta un ponte (4 m) |
| Segni | `SM_SHIP_Plate_*` (13), `SM_SHIP_Sign_<d><s>` (8) | etichette dell'atlante, lampada sul bordo |

Materiali: le istanze del progetto (`MI_ASTRA_Structure/Trim/Rubber/Glass`, `MI_BRG3_Composite/Ivory/DeckPlate/DarkGlass/Lamps*`) e **17 nuove** `MI_SHIP_*` (Laminate, Steel, Fabric×4, Bedding, Wood,
Crate×4, Leaf, Tile, PaintRed, Soil, Labels), create da `build_ship_interior.py` (padre `M_ASTRA_Hard` con i set di texture già nel progetto; Labels = `M_ASTRA_Screen` con `T_SHIP_Labels`); i valori sono quelli
delle anteprime. Nessun asset di terzi nuovo (i caratteri Barlow Condensed e IBM Plex Mono sono già in `docs/licenze.csv`).

Controlli del kit (`ship_kit.py`, a ogni esportazione): budget di triangoli, slot noti, UV finite e limitate, misure contro la scheda (`ship_spec.py`), altezza ≤ 4,0 m; e **prove a raggi lungo gli archi del grafo** sul Ponte 4
(altezze 0,35 / 1,0 / 1,75 m, contro le mesh piazzate): **1626 raggi di corridoio e di porta, 0 bloccati** (dentro le stanze i nodi "hub" e "posto" sono topologia: 192 su 1149 raggi toccano l'arredo, atteso).
Le anteprime sono in `docs/progressi/nave/` (43 JPG, ciascuna < 250 KB): pianta del Ponte 4 (intera, snodo, poppa), moduli in fila (`modules_*`), viste del ponte dal piano (`d4_*`: la Spine da prua, la porta del Lounge, il portello con il segnale,
un cancello del Concourse, una giunzione, la torre, il passaggio laterale, tre piante in sezione), ogni stanza (`room_*`).

## 7. Il gioco: cosa legge il piano (fatto dal lead) e cosa c'è da collegare

- **`UAstraShipPlan`** (C++ del lead) legge `compartments, doors, graph` (nodo più vicino, rotta A*, compartimento di un punto, porte stagne sigillate, porte a chiave). Le stanze esistenti e il Ponte 4 sono nel piano; ogni cambio di nomi va detto.
- **Luci di zona** (`UAstraZoneLights`): le luci hanno il tag `ASTRA.ZoneLight.<compartimento>` (lo mette lo script), senza ombre; ne restano accese le 8 più vicine. Non hanno il tag `ASTRA.ShipLight` (l'allerta e il livello di luce non le toccano: se si vuole, aggiungerlo in `add_light`;
  le lampade emissive delle mesh seguono già l'allerta dalla palette).
- **Porte**: una `AAstraDoor` per porta del piano (larghezza, altezza e yaw del record, cartella `Interior/Deck04/Doors`, etichetta `Door_<id>`); le ante scorrono di metà larghezza. Le porte delle torri delle scale restano **chiuse a chiave** finché i ponti sopra e sotto non sono costruiti
  (`LOCK_STAIRS`); i portali delle stanze esistenti non si toccano.
- **Ascensore** (`AstraHangar`, sei tappe: Bridge, Hangar, Engineering, Medbay, Mess, Berth): il Concourse ha il suo banco (`lift.d4_concourse`, in **(-119,1; 9,0; -46,0) m**, davanti alle due porte a x -121,45, y 7,6 e 10,4). Da fare: mettere `MessLanding` lì (e `BerthLanding` nell'atrio, per esempio
  (-172; 0; -46)), poi togliere le ante statiche delle alcove (`REMOVE_LIFT_LEAVES = True` distrugge le cartelle `Mess/Lift` e `Berths/Lift`) e riprovare il tragitto; finché non si fa il vecchio comportamento resta.
- **Incidenti** (`AstraShipSubsystem`: fuochi e danni scelgono un ponte 2–11 e una sezione A–H): il piano dà per ogni (ponte, sezione) i compartimenti veri: scegliere un corridoio o una stanza di quel ponte e sezione e usarne `bounds` per il punto.

## 8. Da sistemare fuori dai miei file (richieste al lead)

1. **Crew Berthing: "Deck 3" sul piano del Ponte 4.** Il Berthing dice DECK 3 ma poggia a z -46 come la Mess (il piano di Deck 3, -42, è sotto la pelle interna dello scafo). Il piano lo registra su `plane: 4` con `label_deck: 3`, e nell'atrio c'è una targa "DECK 3".
   Due scelte: (A) tenere "Deck 3" (canon) e alzarlo di 4 m con la correzione dello scafo qui sotto; (B, consigliata) chiamarlo **Deck 4 · Section C** e dire nella BIBBIA che il Ponte 3 ha gli alloggi ufficiali e la palestra. Per (B) cambiare: `data/ship/aquila_berths.json` (`name`, `signage`),
   `AstraShipSubsystem.cpp` (righe ~1592 e ~1638), `ASTRAPlayerController.cpp` (~519: la lista delle tappe dell'ascensore), `AstraHangar.cpp` (~413) e il commento di `AstraHangar.h` (~44), i docstring di `build_berths.py`/`berths.py`, e nell'atlante `room_deck3` (l'etichetta dell'atrio).
2. **Correzione dello scafo per il Ponte 3 e per il 2.** Il blocco superiore (x hull -327,6..132,6, |y| < 30, hull z 21,08..39,08: mondo -40,92..-22,92) e l'isola sono solidi chiusi che si sovrappongono allo scafo inferiore; la faccia inferiore del blocco (mondo -40,92) pende a 1,08 m sopra il pavimento del Ponte 3
   (-42), e l'interno del Ponte 2 (-36,7) sta dentro il blocco. Serve togliere il fondo del blocco (e dell'isola) dove sovrasta lo scafo (`art/blender/shipgen2.py`, ARTE-NAVI), altrimenti si vedono piani fantasma dall'interno. Lo scafo non ha collisione né ombra e non si vede da dentro (facce rovesciate).
3. **Radiatori sul Ponte 5.** `AstraShipSubsystem.cpp` ~786: `D.Deck = 5` per i danni ai radiatori; nel canon i radiatori sono sul **Ponte 7** (Engineering & Power) nelle sezioni E–G. Basta `Deck = 7`.
4. **Navetta della Spine.** Nel piano è solo riservata (Ponte 5, `transit[0]`, fermate a metà di ogni sezione): un giorno un arco `shuttle` nel grafo e un veicolo sulle guide della linea di mezzeria.
5. **Ponti ancora grossolani** (2, 3, 5–12): sono compartimenti tipizzati e navigabili nel grafo, senza moduli né stanze modellate; per costruirne uno basta scrivere `ship_deck<N>.py` come `ship_deck4.py` (passaggi, corsie con elenchi, torri) e le stanze mancanti in `ship_rooms_*.py`/`ship_spec.py`: il generatore (`--only`, il registro del kit), i controlli, le anteprime e lo script di Unreal funzionano già per qualsiasi ponte (`DECKS = [3, 4]`).

## 9. Limiti noti

- **Non provato nell'editor.** Il kit e le anteprime sono verificati in Blender (Eevee) e con i raggi; lo script di Unreal (parametri delle istanze, orientamento delle `RectLight`, proprietà `locked` della porta, tolleranza dei limiti dopo l'importazione: 6 cm) va provato dal lead;
  se l'importazione dice `bounds problems` o una porta non si chiude a chiave, è lì.
- Il Ponte 4 in Unreal è scuro nelle anteprime senza luci: le luci di zona (8 alla volta) fanno la sala; il rimbalzo delle anteprime è finto (una luce d'area sotto il soffitto), Lumen farà il suo.
- Le mesh del Ponte 4 non sono ottimizzate per l'istanza: 455 moduli sono attori statici (Nanite regge; le luci sono il costo, per questo la zona).
- Le porte delle stanze verso il passaggio dal lato lontano (`_far`) esistono nel piano; nel Lounge e nella sala giochi aprono sul passaggio laterale.
- Sezione E del Ponte 4: solo corridoi e le stanze esterne (la sala Engineering tiene il centro); sezione H solo stores interni. Le stanze esterne finiscono a x -484 (l'inviluppo si stringe).
- L'Observation Deck e il Bow Observation hanno vetri traslucidi (mesh non Nanite); dietro non c'è altro che il cielo: lo scafo non copre le finestre.
- Il reticolo è ortogonale: non c'è un modulo di curva. La scala a pioli autonoma (`SM_SHIP_LadderTrunk`, per i cunicoli del Ponte 12) e le varianti della torre (`StairTowerTop` per il ponte più alto, `StairTowerBottom` per il più basso) sono pronte ma non piazzate sul Ponte 4.
