# NAVE — l'ASN Aquila come nave vera (fasi F4.1 e NAVE-2)

Il "DNA" della nave (`data/ship/aquila_plan.json`), il kit di moduli e stanze dell'interno (Blender, nel linguaggio della plancia v3) e gli strumenti per metterli nel
livello e farli girare su un MacBook Air. **Tutti i dodici ponti sono costruiti**: il Ponte 4 (Crew Services) a mano, il Ponte 1 con lo studio del Capitano (Ready Room), gli altri dieci dal
loro programma (`ship_decks.py`): 7 275 pezzi nel piano (5 241 moduli di corridoio, 833 stanze, 831 targhe, 370 segnali di sezione), 1048 porte, 3 167 lampade, 3 815 posti (`stations`) per la gente di VITA. Sul lato del gioco
la nave non è più un livello di attori: **istanze** al posto dei moduli, **lampade come dati** con un pool di luci vere, **un sotto-livello per ponte** in streaming (§7bis). Tutto ciò che è scritto nel gioco è in inglese;
questa pagina è in italiano con i nomi ufficiali.

Stato: piano dei 12 ponti completo e verificato (**0 problemi, 0 avvisi**; 2270 compartimenti, 10797 nodi e 10931 archi del grafo, un solo componente connesso); kit di **266 mesh, 6,09 M triangoli, la più pesante 138 k** (`ShuttleBay`);
prove a raggi lungo tutti gli archi di corridoio e di porta dei 12 ponti: **0 bloccati** (18 522 raggi); 3 398 posti controllati contro l'arredo (i letti no): **0 sul mobilio**; C++ compilato nella worktree dopo l'unione con `main`;
`tools/life.py check` OK. **Non provato in Unreal** (l'editor è del lead): vedi "Limiti" e §7bis per cosa guardare camminando.

## 1. Comandi, nell'ordine

```
uv run --python /opt/homebrew/bin/python3.13 --with pillow --with numpy python tools/art/ship_textures.py          # atlante delle etichette: art/_cache/ship/
python3 art/blender/ship_plan_gen.py                                                                              # piano: data/ship/aquila_plan.json
python3 art/blender/ship_checks.py                                                                                # controlli del piano (0 problemi attesi)
python3 tools/life.py check                                                                                       # VITA: i posti e le stanze del piano coprono la vita di bordo
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python-exit-code 1 -P art/blender/ship_kit.py   # FBX + manifest in art/export/ship (qualche minuto)
python3 art/blender/ship_budget.py                                                                                # il budget per ponte (legge il manifest o --stats)
tools/ue.py pyfile tools/ue_scripts/build_ship_interior.py                                                        # il lead: materiali, kit, un sotto-livello per ponte, L_Bridge
UnrealEditor-Cmd ASTRA.uproject -run=AstraNave -nullrhi -unattended -nosound                                      # il banco senza grafica: lampade, streaming, ponti attorno al Capitano
```

Anteprime (Eevee, senza editor): `Blender -b … -P art/blender/ship_kit.py -- --no-export --no-checks --preview docs/progressi/nave --views rooms,modules,d1,d4,d6 --room-views door --samples 28`
(una stanza: `--only ReadyRoom`, con i nomi delle mesh senza `SM_SHIP_`; i punti di vista di ogni stanza sono in `ship_kit_preview.ROOM_VIEWS`). Solo i conteggi di triangoli, senza esportare:
`… -- --no-export --stats art/_cache/ship_stats.json`; solo i posti di una stanza: `… -- --no-export --spots --only Barracks`. Piano in pianta: `uv run … --with pillow python tools/art/ship_planview.py 5 out.jpg [--x0 -260 --x1 -60 --scale 6 --graph]`.
Il piano è la fonte unica: lo leggono `ship_kit.py` (quali targhe e segnali servono), `build_ship_interior.py` e il gioco (`UAstraShipPlan`, che lo cerca in `Content/ASTRA/Data/aquila_plan.json`, dove lo script lo copia, poi in `data/ship/`).

## 2. Sistema di riferimento e pila dei ponti

Come tutto il gioco: X a prua, Y a dritta, Z in su, metri (Unreal: cm, stessi assi); l'origine è il punto del pavimento della plancia sotto la poltrona del
Capitano. Lo scafo `SM_SHIP_ASTRA_Aquila` sta in (-172, 0, -62) m: coordinate dello scafo = mondo + (172, 0, 62). Ponti a passo di 4,0 m (0,3 struttura +
3,4 libero + 0,3 struttura); le stanze sono alte al più 3,7 m (il soffitto è la struttura del ponte sopra).

| Ponte | Nome | z pavimento | Contenuto (BIBBIA v0.3 §6) | Stato nel piano |
|---|---|---|---|---|
| 1 | Command | 0 | Bridge, Captain's quarters, ready room, command corridors | plancia e quarters esistenti; **Ready Room costruita** (§5.4) |
| 2 | CIC & Communications | -36,7 | CIC, briefing room, department offices, communications | **costruito** (37 stanze); torri con cappuccio |
| 3 | Crew Country | -42,0 | officers' quarters, gym (e Crew Berthing, vedi §8) | **costruito** (30 stanze); torri da 5,3 m; lo scafo è già aperto sotto il blocco (§8, punto 3) |
| 4 | Crew Services | -46,0 | Mess Hall, galley, lounge, observation deck | **costruito a mano** (75 stanze) |
| 5 | Science & Transport | -50,0 | science labs, Transporter Room (sei pedane), sensor archive; la navetta interna della Spine | **costruito** (81 stanze: Transporter Room, Astrometrics, sette fermate della navetta) |
| 6 | Medical | -54,0 | Medbay, surgery, quarantine, pharmacy | **costruito** (103 stanze): Medbay esistente, sala operatoria, quarantena e farmacia accanto |
| 7 | Engineering & Power | -58,0 | Main Engineering, reactor, power control, radiators | **costruito** (81 stanze): Engineering esistente, power control, switchgear, capacitor halls |
| 8 | Marines & Armory | -62,0 | Armory, Marine Barracks, firing range, assault-shuttle bay (due Kestrel) | **costruito** (87 stanze: caserme, poligono a 6 corsie, hangar con due Kestrel) |
| 9 | Flight | -66,0 (Flight Deck: -72,8) | Flight Deck: launch tubes, bays, aircraft workshop, control booth | **costruito** (88 stanze); il Flight Deck esistente si raggiunge solo in ascensore (§8) |
| 10 | Holds & Munitions | -70,0 | holds, munitions magazines, stores | **costruito** (80 stanze) |
| 11 | Workshops & Damage Control | -74,0 | workshops, fabrication, repairs, damage-control teams | **costruito** (82 stanze) |
| 12 | Keel | -78,0 | tanks, reaction mass, maintenance crawlways | **costruito** (88 stanze) con cunicoli stretti (tono K) |

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
i collegamenti a croce le uniscono attraverso le corsie interne (16 m di profondità) e le corsie esterne (16 m, dal passaggio verso lo scafo). Sui ponti con grandi sale (Mess sul 4, Medbay sul 6, Engineering sui 4–7, Flight Deck
sui 6–11) la Spine è spezzata in tronchi: il traffico passa dai passaggi laterali; ogni tronco ha una corsia interna di dritta con un collegamento a croce (un tronco non resta mai isolato).

**Tono K — i cunicoli della chiglia (Ponte 12).** Sulla chiglia i tre passaggi sono cunicoli di manutenzione (`SM_SHIP_K_*`, 16 mesh: dritti, con porta a sinistra o a destra, `T`, `X`, paratia, fine): 1,7 m di larghezza utile e 2,5 m di altezza dentro la stessa fessura di 4 m, pareti
spesse con file di tubi, nervature ogni 2 m, soffitto pieno e portelli stagni 1,2 × 1,95; luce ambra bassa (1500 lm per modulo); le targhe delle stanze stanno sulla parete accanto al portello, non sopra. Sono l'unico posto in cui il Capitano va a testa bassa:
il personaggio (capsula da ~70 cm) passa con ~50 cm per lato (nei portelli, 1,2 m, con ~25).

**Raccordi (`SM_SHIP_<tono>_Stub<cm>`).** Dove un passaggio finisce a una parete fuori griglia di una stanza esistente (Medbay, Main Engineering, Flight Deck), il tronco si ferma sulla prima linea della griglia e un
raccordo liscio di corridoio (lungo quanto serve: 1,5 m davanti a Main Engineering sul Ponte 7, 3,5 m davanti al Flight Deck sul 9) chiude lo spazio che resta; il piano lo posa dove crea l'atrio (`<stanza>_lobby`).

**Torri delle scale** (una colonna ogni 150–350 m: `stair_44p`, `stair_92n`, `stair_300n`, `stair_452n`): `SM_SHIP_StairTower` (due rampe a tornante, 4 m di dislivello), `…Top`/`…Bottom` per le estremità, `…StairTowerCap` sul Ponte 2 (il pozzo si chiude sul soffitto del blocco),
`…StairTower53` sul Ponte 3 (la scala da Deck 2 a Deck 3 scende di 5,3 m attraverso il ponte corazzato) e `SM_SHIP_LadderTrunk` (scala a pioli, per l'uscita di sicurezza).

## 4. Lo schema del piano (`data/ship/aquila_plan.json`, versione 1)

Compatto, generato (`ship_plan_gen.py`), letto dal gioco (`UAstraShipPlan`: **campi, tipi di arco e `p` in metri sono stabili**; i campi aggiunti da NAVE-2 sono in corsivo). Chiavi: `id, version,
generator, frame, decks, compartments, doors, vertical, transit, graph{nodes, edges}, systems, placements, notes`.

- `decks[]`: `id, name, programme, z, clear, ceiling, structure, pitch, volume, envelope{x_fwd, x_aft, half_width[[x, hw]…]}, sections[{id, x:[min, max]}]`.
- `compartments[]`: `id, deck, section, kind, name, bounds[x0, y0, x1, y1] (mondo, m), z[pavimento, soffitto], status (built | planned | existing), doors[], dept, systems[],
  stations[], lights[]`; le stanze fatte: `prefab, mesh, pos, yaw, plate, lane, size[L, D, h], crew_slots`; i corridoi: `passage, modules[i0, i1], tone` (*`tone` ora anche `K`*); le esistenti: `plane`
  (il ponte su cui poggiano), `label_deck` (il numero scritto sulla porta, se diverso), `entrance, data, capacity, spans_decks, note`.
  - `stations[]`: dove sta la gente: `id, role, kind (sit | stand | work | eat | sleep | watch), pos[x, y, z], yaw, dept` (le usa VITA; i posti seguono l'arredo vero; *z = pavimento + `dz` della scheda* per chi sta su una pedana, su un tapis roulant, in una vettura).
  - `lights[]`: `id, type (rect), pos, lumens, temperature, size[x, y], radius, shadows` (in assi del mondo): *sono le lampade* (§7bis): dati, non attori.
- `doors[]`: `id, deck, pos[x, y, z], yaw (90 = porta in un muro lungo x), width, height, kind (door | gate | blast | sliding), a, b (compartimenti), locked`, più `wall, passage, plate,
  side, boundary` (blast: `[sezione aft, sezione fwd]`), `existing` (i portali delle stanze esistenti: il piano li chiama cancelli, le loro ante statiche restano), `planned` (la porta di una stanza non modellata: un muro pieno, chiusa a chiave; *oggi non ce n'è nessuna sui ponti costruiti*).
- `graph.nodes[]`: `id, deck, p[x, y, z], kind (corridor | door_in | room | station | stair | lift | lift_core), comp`. `graph.edges[]`: `a, b, len, kind (walk | door | stair | lift),
  door, w, blast, cost`. Un nodo di corridoio per modulo (ponti costruiti) o per compartimento da 16 m (grossolani, oggi nessuno); ogni stanza ha un nodo dietro ogni porta, un `hub` al centro, un nodo per
  posto; i portelli stagni sono archi `door` con `blast: true`. Un arco `door`/`walk` tra due quote lontane più di 1,5 m (la porta del Flight Deck è 6,8 m sotto il corridoio del Ponte 9) VITA lo percorre come un ascensore. Un solo componente connesso (verificato).
- `vertical[]`: `lift_main` (turboascensore: `landings[]` con `deck, plane, room, pos, node, existing`, `ride`) e una colonna di scale per torre (`stair_<x><n|p>`: `nodes`, `towers` per ponte).
- `transit[]`: `spine_shuttle` (Ponte 5): *`stops[]` con `section, x, room, node`* (le fermate costruite: A, B, C, D, E, G, H), `status: "stops built"`; non c'è ancora una vettura che corre né un arco `shuttle` nel grafo.
- `systems`: per sistema di bordo (reactor, power_bus, coolant, radiators, sensors, comms, weapons, ordnance, life_support…) i compartimenti che lo ospitano (i corridoi portano i bus e non sono elencati).
- `placements{ponte: [...]}`: cosa mettere nel livello: `mesh, pos, yaw, folder, label, cls (module | room | sign | plate), comp` (*oggi anche sul Ponte 1: stanza, modulo con la porta, targa*).

Controlli del piano (`ship_checks.py`): dentro l'inviluppo; nessuna sovrapposizione in 3D; porte sui muri (≤ 0,65 m dai limiti del compartimento) e di misura giusta (≥ 0,9 × 1,9 m);
grafo connesso, ogni compartimento raggiunto, archi sensati, scale e ascensore raggiungibili; nessuna stanza a cavallo di due sezioni; punti fissi del canon; ogni sezione con almeno un compartimento; **il programma: ogni stanza del kit ha almeno un posizionamento e nessuna stanza fissata "cannot stand"**.
Risultato del piano attuale: 2270 compartimenti, 1056 porte, 10797 nodi, 10931 archi, **0 problemi, 0 avvisi**.

## 5. I ponti

### 5.1 Il Ponte 4 (Crew Services, z -46): a mano

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

### 5.2 Gli altri ponti: dal programma

`ship_decks.plan_deck(coarse=False)` riempie le corsie di un ponte dal suo programma (`PROGRAMME[ponte][sezione | default]`: l'elenco ciclico delle stanze di quella sezione) con le stanze che hanno una mesh. Quello che serve sapere:

- **Stanze uniche e fissate.** `UNIQUE[ponte]` sono le stanze che stanno una volta sola (il CIC sul 2; Transporter Room e Astrometrics sul 5; sala operatoria, quarantena e farmacia sul 6; hangar delle navette e poligono sull'8); `PINNED` le mette per prime in un posto fisso
  (lato della Spine e x del bordo di prua): **il CIC in sezione B del 2** (a prua di x -60 il blocco è largo solo 16,4 m per lato: la sezione A ha la sola Spine, nessuna stanza da 16 m ci sta), la Transporter Room in sezione B del 5, accanto al Medbay le tre stanze mediche del 6, **l'hangar delle navette (lato di babordo: la torre di prua occupa quello di dritta) e il poligono sull'8**, **le sette fermate della navetta sul 5**.
  Tre errori di generazione, tutti silenziosi (una stanza che non sta finiva solo in `notes`), corretti in questa consegna: un tentativo di corsia scartato non "consuma" più una stanza unica (l'Astrometrics non compariva); una stanza con due porte sullo stesso muro (l'hangar) prende `_2` per la seconda
  (prima il piano si fermava con "duplicate door"); il CIC e l'hangar non stavano dove erano fissati o programmati. `ship_checks.py` ora lo verifica: **ogni stanza del kit ha almeno un posizionamento nel piano e nessuna nota "cannot stand" resta** (il piano di prima, con questi due buchi, dà 3 problemi).
- **Dove la Spine arriva.** I tronchi della Spine finiscono contro le grandi sale di altri ponti (`obstacles`): `reach_rooms` li porta fino alla parete di una stanza esistente che ha qui l'ingresso (Medbay, Main Engineering) e li ferma sulla prima linea della griglia; un raccordo (`…_Stub<cm>`) chiude il resto.
- **Conflitti.** Il motore toglie le stanze la cui porta incontrerebbe un collegamento a croce sull'altro lato del corridoio (un modulo non può avere un ramo da una parte e una porta dall'altra) e dà la precedenza alle torri delle scale (nota nel piano: oggi una sola stanza, una `radiator_pumps` del 5).
- **Sezioni.** Nessuna stanza a cavallo di un confine di sezione (i portelli stagni stanno lì).

### 5.3 Ponte per ponte: le stanze nuove

Le misure sono interne (lunghezza × profondità × altezza, m); ogni stanza ha il suo arredo vero (nessuna sala vuota) e i suoi posti (`stations`) e lampade nella scheda `ship_spec.py`.

| Ponte | Stanza (prefab) | Misure | Cosa c'è dentro |
|---|---|---|---|
| 2 | `cic` — Combat Information Centre | 32 × 16 × 3,6 | tre grandi pannelli sulla parete di fondo (piano tattico, carta stellare, stato della nave), tavolo del piano con anello di luce, due blocchi di sei console, rack delle comunicazioni, pannello del damage control |
| 2 | `briefing`, `comms_center`, `offices`, `records` | 16 × 16, 24 × 16, 16 × 16, 12 × 16 | tavolo lungo con tre schermi e lo stemma; tre file di postazioni operatore con la parete delle reti di flotta; uffici aperti con partizioni e plotter; archivio con scaffali mobili |
| 2 | `vls_magazine`, `point_defense`, `barbette`, `sensor_room` | 24 × 16, 16 × 16, 24 × 16, 16 × 16 | due blocchi di celle di lancio verticali con carroponte e missile sull'imbracatura; quattro postazioni di tiro davanti alle camere; la base di una torretta railgun (trunk corazzato, culatta, colonne di condensatori); console e globo sensori |
| 3 | `staterooms` — Officers' Staterooms | 20 × 16 × 3,2 | otto cabine da ufficiale attorno a un atrio (letto sotto un oblò-schermo, scrivania, armadio, lavabo con specchio illuminato) |
| 3 | `wardroom`, `gym` | 24 × 16 × 3,6 / 3,7 | due tavoli da dieci posti, salotto con bar e acquario; cinque tapis roulant, panche con rastrelliere, sacco, specchi, armadietti |
| 5 | `transporter` — Transporter Room | 24 × 16 × 3,8 | sei pedane su una pedana rialzata sotto l'anello di emettitori, console, buffer di schema, cabina di decontaminazione, pedana di carico (BIBBIA §3: 8 s a ciclo) |
| 5 | `lab_astro`, `lab_bio`, `lab_phys`, `sensor_archive`, `sensor_room` | 24 × 16, 24 × 16, 24 × 16, 16 × 16, 16 × 16 | Astrometrics (stanza buia sotto le stelle: trittico di carte, tavolo olografico, sei console); acquari, banchi di crescita, freezer, microscopi; un acceleratore su telaio d'acciaio con rivelatore ad anello e cabina schermata; scaffali dati con la volta fredda |
| 5 | `radiator_pumps`, `machinery`, `machinery_b`, `dc_locker` | 24 × 16, 24 × 16, 24 × 16, 12 × 16 | collettori e pompe del refrigerante; aria e acqua; aria compressa; il deposito del damage control (armadietti con le manichette, autorespiratori, puntelli) |
| 5 | `shuttle_stop` — Spine Shuttle Stop | 24 × 12 × 3,7 | banchina con la vettura ferma e le porte aperte (14 m: tre porte, panche, mancorrenti), bocche di galleria alle due testate, linea gialla, panche, schermi, segnali (sette, una per sezione tranne la F) |
| 7 | `power_control`, `switchgear`, `capacitors` | 24 × 16 × 3,6 / 3,7 | il pannello sinottico della distribuzione con due file di console; due file di quadri ad alta tensione su tappeti isolanti con gabbia di isolamento; due banchi di condensatori su zoccoli a strisce con sbarre |
| 8 | `shuttle_bay` — Assault-Shuttle Bay | 32 × 16 × 3,7 | **due Kestrel** (11,7 m, rampe giù, collare di perforazione) davanti ai portali di lancio, banco, gabbia dei razzi, trattore, carrelli del carburante e della schiuma |
| 8 | `barracks`, `kit_room`, `firing_range` | 24 × 16, 16 × 16, 40 × 16 | otto cuccette doppie con armadi e bauli, tavolo lungo, angolo palestra; sei vani armatura e due file di armadietti; **sei corsie da 33 m** con baffle e sagome a 21 e 31 m, cabine di tiro, recinto con due cancelli |
| 9 | `flight_ops`, `pilot_ready`, `aircraft_shop` | 24 × 16, 24 × 16, 28 × 16 | la sala di controllo del volo (la "control booth" del canon, Air Boss e CAG): tre pannelli di stato, due file di console, tavolo del piano; poltrone in due blocchi con podio e armadietti delle tute; il muso di un caccia sul carrello sotto il carroponte, un turbofan, un'ala sull'attrezzatura |
| 9–10 | `magazine`, `cargo_hold` | 24 × 16, 32 × 16 | due file di rack di missili con l'argano dei munizionamenti e gli irrigatori; container impilati, pallet, carrello elevatore, portello del montacarichi |
| 11 | `fab_shop`, `repair_bay` | 28 × 16, 32 × 16 | tre stampanti a metallo, forno di fusione, cella robotica con nastro; piastre di scafo, due simulatori, tavolo con il taglio al plasma, due celle di saldatura, tute EVA e puntelli |
| 12 | `tank`, `reaction_mass`, `crawlway` | 32 × 16, 40 × 16, 16 × 16 × 3,0 | quattro serbatoi orizzontali di 11 m con il manifold; quattro vasi sferici a pressione con l'anello di tubi; l'incrocio dei cunicoli con tre tubi verticali, scala e botola |

Le stanze di servizio dei ponti 4 e 6 (cucina, magazzini, serre, cabine, biblioteca, sale di raccoglimento…) si ripetono dove il programma le chiede (§6); il Ponte 3 usa anche `offices` e `records`.

### 5.4 Il Ponte 1: lo Studio del Capitano (Ready Room)

Il blocco tra i due corridoi della plancia (canon, BIBBIA §6): **12 × 4,2 × 2,9 m** (x da -20,8 a -8,8, y da -2,1 a +2,1), a filo con la parete di poppa della plancia (-8,8) e con la testa dei corridoi (-20,8); il tetto sta a 3,2 m come quello dei corridoi.
Dentro: sul muro di poppa un **oblò** con un campo di stelle e il bordo di un pianeta sopra una credenza (il modello della nave, una caraffa, una lampada), la **scrivania del Capitano** (legno con intarsio di pelle, tre cassetti per lato) con la poltrona alta dietro e due sedie per i visitatori,
la bandiera e un mappamondo illuminato negli angoli, tre librerie dal lato della porta; verso prua un divano di fronte a un tavolino con due poltrone e una lampada, un **tavolo olografico** sotto un anello di luce e il **piano tattico** sul muro di prua. Pareti di tessuto sabbia su zoccolo di legno, moquette: è una stanza di lavoro, calda, non una sala.
Nove posti (visitatori, divano, attorno al tavolo), quattro lampade, targa `CAPTAIN'S READY ROOM · PRIVATE · COMMAND` sopra la porta. Sotto il pavimento un carenaggio di piastre di scafo (`MI_HULL_A_Plate`, l'istanza del progetto) scende nella cima dell'isola tra i due che il costruttore della plancia ha messo sotto i corridoi (`quarters.py`): visto da fuori lo Studio non galleggia.

**La porta.** I corridoi della plancia sono del vecchio kit (`SM_COR_*`, `kit_corridor.py`, piazzati da `build_bridge_v3.py` come attori di L_Bridge: tre moduli da 4 m con la finestra su quello di mezzo, x -20,8 / -16,8 / -12,8) e non hanno porte nei muri laterali. Il piano mette la porta (**1,4 × 2,2 m**, scorrevole, in (-15,8; -2,2; 0)) nel
**primo vano di parete del modulo con finestra** e sostituisce quel modulo con `SM_SHIP_BridgeCorridorDoor` (`ship_rooms_bridge.corridor_door`: lo stesso modulo con il varco, cornice, soglia e due barre di stato; materiali `MI_ASTRA_*`). `build_ship_interior.py` (flag `OPEN_READY_ROOM`) distrugge in L_Bridge il modulo con finestra (`CorrPort_Window`) e i due pannelli del vano
(`CorrPort1_0_*_R`): **va lanciato dopo `build_bridge_v3.py`**, che li rimetterebbe. La targa sta sopra l'architrave (il muro sale a 2,5 m e poi smussa: non c'è altro posto).

## 6. Il kit (`art/blender/ship_*.py`)

Linguaggio della plancia v3: composito scuro in cornici di metallo spazzolato, nervature con linee di luce, lampade a palette (`MI_BRG3_Lamps*`: la cella dice il colore: command, engineering, white_warm…), un solo slot per
tutte le etichette (`MI_SHIP_Labels`, atlante `T_SHIP_Labels`). Ogni mesh è chiusa alla luce (sovrapposizione di 2 cm, soffitti chiusi: lo scafo non ferma il sole), Nanite (quelle con un vetro restano classiche: le tre
di osservazione), collisione complessa come semplice, UV a 1 m (`box_uv`) e per cella per lampade e etichette. Budget: **266 mesh, 6,09 M triangoli in tutto, la più pesante 138 k** (i triangoli in Nanite non sono il costo;
il costo è la memoria: qualche centinaio di MB di FBX su disco, non in git).

| Gruppo | Mesh | Note |
|---|---|---|
| Moduli di corridoio (3 toni × 16) | `SM_SHIP_<S|P|K>_` `Straight_A/B/C, Door_L_A/B, Door_R_A/B, Door_LR, Gate_L/R/LR, Bulkhead, T_L, T_R, X, End` | 17–57 k triangoli (K: 3–4 k); pannelli, prese d'aria, armadietti, quadri elettrici, estintori, pronto soccorso, condotti, schermi; la Bulkhead porta il portello stagno con strisce di pericolo e il campo del segnale |
| Stanze di servizio | Galley, GalleyPass, StoreDry(+D10), StoreCold, Hold, Heads, Laundry, Hydro | cucina professionale, scaffali con casse, container ISO, docce, lavatrici, serre a tre ripiani |
| Stanze sociali | Lounge, Games, Library, Quiet, Observation(+D14), BowObs, Wardroom, Gym | salotti su tappeti, bar con sgabelli, biliardo, libri a file, sala di raccoglimento con anello di luce, finestre con vetro; mensa degli ufficiali con acquario; palestra |
| Stanze mediche | Surgery, Quarantine, Pharmacy | sala operatoria, reparto di quarantena con sei celle di vetro, farmacia con bancone a gabbia |
| Stanze di lavoro | Lab, Workshop, Armory, Cabins; LabBio, LabAstro, LabPhys, SensorArchive, SensorRoom; FabShop, RepairBay | banchi con reagenti, tavolo olografico; tornio, fresa, saldatura, carroponte; gabbia e rastrelliere; corridoio comune con otto cabine; i laboratori e le officine del §5.3 |
| Comando e armi (Ponte 2) | Cic, Briefing, CommsCenter, Offices, Records, VlsMagazine, PointDefense, Barbette | §5.3 |
| Scienza e trasporto (Ponte 5) | Transporter, ShuttleStop (+ la vettura `ship_craft.spine_car`) | §5.3 |
| Macchine e potenza | RadiatorPumps, Machinery, MachineryB, DcLocker, PowerControl, Switchgear, Capacitors | §5.3 |
| Marines e volo | ShuttleBay (+ i due Kestrel `ship_craft.kestrel`), Barracks, KitRoom, FiringRange; FlightOps, PilotReady, AircraftShop, Magazine, CargoHold | §5.3 |
| Chiglia | Tank, ReactionMass, Crawlway | §5.3 |
| Plancia | ReadyRoom, BridgeCorridorDoor | §5.4 |
| Snodi e verticali | Concourse, BerthLobby, StairTower(+Top, +Bottom, +53, +Cap), LadderTrunk | torre: due rampe a tornante, pozzo, scala a pioli con boccaporto; alta un ponte (4 m) o 5,3 m |
| Segni | `SM_SHIP_Plate_*` (una per stanza e le scale di ogni ponte), `SM_SHIP_Sign_<d><s>` (sezioni A–H dei ponti costruiti), raccordi `SM_SHIP_<S|P|K>_Stub<cm>` | etichette dell'atlante (il nuovo tag `NAVE2_TAGS` a 256 × 64: 3936 di 4096 px usati), lampada sul bordo; i numeri sulle porte delle cabine sono `CABIN 1..12`, uguali su ogni ponte |

L'arredo vive in `ship_furniture.py` … `ship_furniture8.py` (otto biblioteche per tema: sedute e tavoli, cucina, scienza, volo e sicurezza, armi, officine, ufficio e palestra); ogni funzione costruisce un pezzo nel suo sistema di riferimento (origine a terra, fronte +x) e le stanze lo piazzano con `place(b, x, y, yaw, funzione, …)`.
Gruppi di una mesh (`SParts`): `body` (smussato), `fine` (smussato fine), `soft` (senza smusso, ombreggiatura liscia a 50°: cuscini, libri, piante), `emit` (lampade e etichette dalla palette). Limiti controllati a ogni esportazione: 150 k triangoli a mesh, altezza della stanza ≤ 3,7 (struttura compresa ≤ 4,0), ingombro dentro la pianta
(−0,25 … +0,25 m di muro).

Materiali: le istanze del progetto (`MI_ASTRA_Structure/Trim/Rubber/Glass…` — anche i corridoi della plancia, `MI_BRG3_Composite/Ivory/DeckPlate/DarkGlass/Lamps*`) e **17 nuove** `MI_SHIP_*` (Laminate, Steel, Fabric×4, Bedding, Wood,
Crate×4, Leaf, Tile, PaintRed, Soil, Labels), create da `build_ship_interior.py` (padre `M_ASTRA_Hard` con i set di texture già nel progetto; Labels = `M_ASTRA_Screen` con `T_SHIP_Labels`); i valori sono quelli
delle anteprime. Nessun asset di terzi nuovo (i caratteri Barlow Condensed e IBM Plex Mono sono già in `docs/licenze.csv`).

Controlli del kit (`ship_kit.py`, a ogni esportazione): budget di triangoli, slot noti, UV finite e limitate, misure contro la scheda (`ship_spec.py`), altezza ≤ 4,0 m; **prove a raggi lungo gli archi del grafo** di ogni ponte costruito (altezze 0,35 / 1,0 / 1,75 m, contro le mesh piazzate) e
**controllo dei posti** (`check_spots`: chi sta in piedi ha una colonna libera di 22 cm dal ginocchio alla testa, chi siede un torso libero di 12 cm sopra il sedile, e sotto c'è il pavimento; un posto sul mobilio esce con il punto libero più vicino da scrivere nella scheda). Risultato sul piano finale:
**12 ponti, 18 522 raggi di corridoio e di porta, 0 bloccati; 3 398 posti controllati, 0 sul mobilio** (dentro le stanze i raggi hub → posto sono topologia: ne toccano l'arredo circa un quarto, atteso).
Le anteprime sono in `docs/progressi/nave/` (JPG sotto i 250 KB): ogni stanza nuova in una vista scelta guardandole (`room_<stanza>_<vista>.jpg`: di solito dalla porta), lo Studio del Capitano in quattro viste e la sua porta nel corridoio (`d1_*`), la fermata della navetta in due, i cunicoli (`modules_keel_*`), la pianta di ogni ponte (`plan_d<N>.jpg`) e, dei ponti 4 e 6, le viste dal piano (`d4_*`, `d6_*`).

**Mappa dei file** (`art/blender/`):

| File | Cosa contiene |
|---|---|
| `ship_plan.py`, `ship_plan_gen.py`, `ship_checks.py` | misure dei ponti e dell'inviluppo; il generatore del piano (`BUILT_DECKS`, le stanze esistenti, il grafo, `spine_shuttle`); i controlli del piano |
| `ship_layout.py`, `ship_deck4.py`, `ship_decks.py`, `ship_deck1.py` | il motore (Builder, Passage, Deck, corsie, porte, lampade); il Ponte 4 a mano; i programmi, le stanze uniche e fissate degli altri ponti; lo Studio del Capitano |
| `ship_spec.py` | la scheda di ogni stanza: misure, porte, **posti**, **lampade** (il piano e le mesh leggono gli stessi numeri) |
| `ship_catalog.py`, `ship_corridor.py`, `ship_walls.py`, `ship_signs.py` | i toni S, P, K e le misure del reticolo; i moduli di corridoio e i raccordi; i pannelli di parete; targhe e segnali |
| `ship_rooms.py` (conchiglie e `place`), `ship_rooms_service/social/med/work/hub.py` | le stanze del Ponte 4 e 6 e le torri |
| `ship_rooms_science/science2.py`, `…_engineering.py`, `…_security.py`, `…_flight.py`, `…_workshops.py`, `…_command.py`, `…_quarters.py`, `…_keel.py`, `…_bridge.py`, `…_transit.py` | le stanze di NAVE-2 per tema (§5.3, §5.4) |
| `ship_furniture.py` … `ship_furniture8.py`, `ship_craft.py`, `ship_lib.py` | l'arredo in otto biblioteche; i velivoli (Kestrel, vettura della navetta); i materiali, la palette, le etichette, `SParts` |
| `ship_kit.py`, `ship_kit_preview.py`, `ship_preview.py`, `ship_budget.py` | il generatore del kit e dei controlli; le anteprime (`rooms`, `modules`, `d1`, `d4`, `d6`); il budget per ponte |

## 7. Il gioco: cosa legge il piano (fatto dal lead) e cosa c'è da collegare

- **`UAstraShipPlan`** (C++) legge `compartments, doors, graph` (nodo più vicino, rotta A*, compartimento di un punto, porte stagne sigillate, porte a chiave), e da NAVE-2 le lampade (`GetLamps()`) e i ponti con i loro sotto-livelli. Il Capitano sa dove sta ("DECK 4 · MESS CONCOURSE · SECTION B") dal compartimento del piano
  (`AstraShipSubsystem::CaptainPlace`, `PlanRoomName`): **non cambiare `id`, `kind` e `name` dei compartimenti esistenti né il compartimento di tipo `bridge`**.
- **Porte**: una `AAstraDoor` per porta del piano (larghezza, altezza e yaw del record, cartella `Interior/Doors`, etichetta `Door_<id>`, nel sotto-livello del suo ponte); le ante scorrono di metà larghezza (il mesh è `SM_COR_DoorLeaf`: 8 cm, scorre dentro il muro). Le porte delle torri delle scale restano **chiuse a chiave** finché il ponte sopra o sotto non ha la sua mappa
  (`LOCK_STAIRS`: con tutti i ponti costruiti nessuna; importando a tappe, rilanciare i ponti già fatti quando arrivano i vicini); le porte di stanze non ancora modellate (`planned`) non si fanno (oggi non ce ne sono); i portali delle stanze esistenti non si toccano salvo `REMOVE_LIFT_LEAVES`.
- **Ascensore** (`AstraHangar`, sei tappe: Bridge, Hangar, Engineering, Medbay, Mess, Berth): il Concourse ha il suo banco (`lift.d4_concourse`, in **(-119,1; 9,0; -46,0) m**, davanti alle due porte a x -121,45, y 7,6 e 10,4). Da fare (richiesta §8): mettere `MessLanding` lì (e `BerthLanding` nell'atrio, per esempio
  (-172; 0; -46)), poi togliere le ante statiche delle alcove (`REMOVE_LIFT_LEAVES = True` distrugge le cartelle `Mess/Lift`, `Berths/Lift` e `Medbay/Lift` e mette una porta scorrevole nell'apertura) e riprovare il tragitto; **l'ascensore deve aspettare il sotto-livello della tappa** (§8, punto 1).
- **Incidenti** (DISTRUZIONE, [DISTRUZIONE.md](DISTRUZIONE.md)): non più un ponte e una sezione a caso. Il modello dei danni gira sulla pianta: un colpo entra dove GUERRA l'ha messo, attraversa i compartimenti dietro la corazza (`bounds`, `kind`, volume) e ciò che fa in ciascuno è fisica (aria, fuoco, fumo, potenza dei `systems` che ci passano); le paratie di sezione sono le porte `blast`
  (`SetDoorSealed`, i percorsi di VITA le evitano), le squadre vanno al compartimento vero. **Non cambiare `id`, `kind`, `bounds`, `systems`, le porte `blast` e il loro `boundary` senza rilanciare `tools/damage.py run --scenario all`**: il banco controlla che le paratie si chiudano, che l'aria si fermi, che le porte si trovino per posizione.
- **VITA** legge `compartments[].stations` e il grafo: i corpi nascono e camminano nei ponti caricati (i ponti non caricati restano un modello, §7bis); `tools/life.py check` verifica che ogni lavoro, posto e casa del file della vita risolva sul piano (oggi OK).

## 7bis. La nave in scala: istanze, lampade, sotto-livelli (NAVE-2)

Il vincolo: ~7000 pezzi, ~1050 porte, ~3200 lampade, memoria di gioco ≤ 9 GB, un ponte che entra in meno di un secondo, mai sotto i 45 fps camminando su un MacBook Air M4. Come attori sarebbero 7000 attori, 7000 componenti e 3200 luci: la soluzione in quattro parti.

1. **Istanze, non attori** (`AAstraDeckShell`, C++). Un attore per ponte tiene tutte le mesh del ponte come istanze (`AddInstancesChunked`): un componente per mesh **per tratto di 160 m lungo la nave** (un componente si registra e si scarta come un tutt'uno), i trasformi in un solo array piatto, nessun tick. Un ponte ha 509–791 pezzi di 25–65 mesh diverse: **106–190 componenti**
   (Ponte 4: 190; la plancia: 3; 1649 per l'intera nave). Una copia di ogni mesh in memoria comunque la usino molti ponti.
2. **Lampade come dati, un pool di luci vere** (`UAstraLampPool`). Le `lights[]` del piano (3165, ~270–350 per ponte) sono un array piatto `FAstraPlanLamp`; il pool sposta **10** `URectLightComponent` (default `astra.lamps.max`, ombre spente) sulle lampade più utili al Capitano: nella sua stanza, nel corridoio dove sta fin dove lo vede, nella stanza dietro una porta
   quando le è a meno di 9 m; sfumano in 0,35 s (`astra.lamps.fade`), la scelta si rifà 5 volte al secondo (le lampade accese tengono il posto se non sono chiaramente battute). Le lampade emissive delle mesh seguono l'allerta dalla palette; le luci del pool seguono livello di luce e allerta (`astra.lamps.gain` moltiplica i lumen del piano, 6 di default).
   Le luci delle stanze vecchie (plancia, Mess, Medbay, Engineering, Flight Deck) restano attori del livello persistente con le loro regole. Comandi: `astra.lamps 0|1`, `astra.lamps.info`.
   **Il danno** (DISTRUZIONE): il pool e le luci delle stanze vecchie seguono la stanza in cui stanno (`FAstraDamageModel::LightOf`): senza potenza restano le strisce di emergenza rosse, con un'alimentazione che cede sfarfallano, un fuoco le fa arancioni, un foro che si svuota rosse, il fumo le attenua, una stanza perduta è al buio (`astra.lamps.info` lo dice per ogni lampada accesa).
3. **Un sotto-livello per ponte, in streaming** (`UAstraDeckStreaming`). Ogni ponte costruito è una mappa `/Game/ASTRA/Maps/Decks/L_Deck01 … L_Deck12` (`ULevelStreamingDynamic` di L_Bridge, inizialmente scaricato e nascosto) con il suo guscio, le sue porte e nulla più. Il sottosistema tiene caricato il ponte del Capitano e, se non è dentro una sala, i ponti che le sue
   colonne di scale raggiungono (la plancia, che non ha scale, tiene solo il suo: **sul Ponte 1 c'è una porta sola**); scarica gli altri dopo 20 s (`astra.decks.unload_delay`), controlla a 4 Hz. L'ascensore usa `RequestAt` (chiede), `IsReadyAt` (aspetta) e `ForceReadyAt` (carica subito, bloccante, a schermo nero: l'ultima risorsa). In editor i ponti sono tutti caricati
   (si guarda la nave intera). Comandi: `astra.decks` (quali ponti ci sono e quali vuole il Capitano), `astra.decks.pin <ponte> [0|1]`, `astra.decks.all 1`. La plancia, le stanze vecchie e il cielo restano nel livello persistente.
4. **Porte attori, segnaletica istanze.** Le porte si muovono, restano `AAstraDoor` nel sotto-livello del ponte (con il ponte caricato ne tickano ~100 per ponte; sulla plancia una); targhe e segnali sono istanze del guscio.

**Lo script** (`tools/ue_scripts/build_ship_interior.py`, v2, idempotente, stampa un rapporto JSON): materiali → importazione del kit solo dei file nuovi o cambiati (`Saved/Ship/kit_stamp.json`; `REBUILD_KIT = "all"` rifà tutto) → per ogni ponte con pezzi nel piano una mappa nuova (guscio + porte) → `L_Bridge` con i sotto-livelli collegati → copia sottile del piano in `Content/ASTRA/Data`
(compartimenti con le lampade, porte, grafo; senza `placements` e `notes`) → apertura delle alcove (`REMOVE_LIFT_LEAVES`) e dello Studio del Capitano (`OPEN_READY_ROOM`). Parametri (globali prima di lanciarlo): `DECKS` (es. `[5, 8]`: solo quei ponti), `REBUILD_KIT`, `CHUNK_M`, `LOCK_STAIRS`, `REMOVE_LIFT_LEAVES`, `OPEN_READY_ROOM`, `SAVE_LEVEL`, `ROOT/LEVEL/DECK_DIR`.
Il rapporto elenca per ponte i posizionamenti, le istanze, i componenti, le mesh distinte, i triangoli, le porte e quelle chiuse a chiave, e i problemi di misure delle mesh importate.

**Il banco senza grafica** (`UAstraNaveCommandlet`, `-run=AstraNave`): sul piano vero verifica che ogni lampada sta dentro il suo compartimento, che un Capitano che percorre ogni ponte vede accendersi e spegnersi le sue lampade senza sfarfallio, poche alla volta, che la stanza dietro una porta chiusa resta buia finché non le è accanto, che i ponti voluti
attorno a un Capitano su una colonna di scale, in una sala e nella chiglia sono quelli giusti; con `-load=<ponte>` costruisce un ponte in un mondo senza renderer dalle mesh importate (Ponte 4: **60 ms**, 640 istanze in 190 componenti, 102 porte; il costo vero in cartella è la GPU, che si misura camminando).

**Budget per ponte** (`ship_budget.py`; "triangoli di istanza" = tutte le istanze viste insieme: il tetto, non ciò che sta davanti al Capitano; con Nanite i triangoli sono memoria e disco, non tempo di fotogramma):

| Ponte | pezzi | mesh | tri mesh distinte | componenti | porte | lampade | stanze |
|---|---|---|---|---|---|---|---|
| 1 | 3 | 3 | 0,06 M | 3 | 1 | 4 | 1 |
| 2 | 509 | 44 | 1,27 M | 107 | 56 | 171 | 37 |
| 3 | 523 | 36 | 0,93 M | 106 | 50 | 241 | 30 |
| 4 | 640 | 65 | 2,19 M | 190 | 102 | 242 | 75 |
| 5 | 725 | 56 | 1,88 M | 171 | 99 | 327 | 81 |
| 6 | 705 | 59 | 1,80 M | 182 | 123 | 269 | 103 |
| 7 | 665 | 43 | 1,41 M | 158 | 101 | 305 | 81 |
| 8 | 670 | 54 | 1,77 M | 155 | 106 | 311 | 87 |
| 9 | 682 | 47 | 1,59 M | 146 | 103 | 326 | 88 |
| 10 | 679 | 43 | 1,44 M | 153 | 98 | 300 | 80 |
| 11 | 683 | 44 | 1,47 M | 148 | 100 | 321 | 82 |
| 12 | 791 | 25 | 0,48 M | 130 | 109 | 350 | 88 |

Il Capitano su un ponte di mezzo ha caricato il suo e i due vicini: ~403–543 componenti, ~208–330 porte, ~654–947 lampade nei dati (10 luci vere). **Sulla plancia in battaglia (il banco di prestazioni del lead) NAVE-2 aggiunge una porta, nessun attore con tick e nessun componente di testo**.

**Cosa guardare camminando** (in ordine, con `astra.decks` e `astra.lamps.info` aperti; fps e memoria con `stat unit` e `stat memory`):

1. L'esito dello script: `bounds_problems` vuoto, per ponte le istanze uguali ai pezzi del piano, `existing entrances opened` e `ready room: 3 actors … removed` (il modulo con finestra e due pannelli) la prima volta, **0** la seconda (idempotenza).
2. **Ponte 1.** Dalla plancia al corridoio di babordo, la porta dello Studio a x -15,8 (la targa sopra): si apre, dentro la luce arriva dal pool (4 lampade), la scrivania sotto l'oblò, il tavolo olografico a prua; il corridoio non ha buchi dove c'era la finestra (la finestra è nel modulo nuovo, il vetro `CorrPort_Glass` è quello di prima).
3. **L'ascensore dalla plancia al Ponte 4, 6, 7, 9** con la richiesta di caricamento (§8): nessun fotogramma nel vuoto all'arrivo; senza la richiesta l'arrivo può essere su un ponte non ancora caricato.
4. **Scale.** Dal Ponte 4 giù fino al 12 (e su fino al 2) dalla colonna `stair_92n`: ogni porta di torre si apre, i ponti si caricano davanti al Capitano senza fermare il gioco (`astra.decks`), il Ponte 3 ha la scala da 5,3 m, il Ponte 2 il cappuccio.
5. **Ponte 5**: Transporter Room (le sei pedane), Astrometrics, una fermata della navetta (la vettura ferma, ci si sale con un gradino di 16 cm). **Ponte 8**: l'hangar con i due Kestrel (la rampa), il poligono (il cancello del recinto sulla linea porta → centro), la caserma. **Ponte 7**: l'ingresso di Main Engineering dal raccordo.
   **Ponte 9**: il Flight Deck solo in ascensore, la sala operativa. **Ponte 12**: i cunicoli (1,7 m): testa e spalle, la luce ambra, i portelli.
6. Le luci: entrando in una stanza si accendono le sue lampade in meno di mezzo secondo, mai più di 10 insieme, nessuno scatto uscendo; chi guarda da un corridoio dentro una stanza aperta la vede accesa.
7. fps camminando sui ponti 4, 5, 8 (i più pieni) e 12; memoria dopo aver percorso tutti i ponti (i vecchi si scaricano dopo 20 s).

## 8. Da sistemare fuori dai miei file (richieste al lead)

1. **L'ascensore deve aspettare il ponte** (`AstraHangar.cpp`, `RideLift` e `TryUseLift` per l'inizio, `Tick` per l'attesa). All'inizio della corsa: `if (auto* DS = GetWorld()->GetSubsystem<UAstraDeckStreaming>()) DS->RequestAt(RideTo, 30.f);`. Nel `Tick`, dove `Before < 0.9f && LiftT >= 0.9f` fa il teletrasporto: se `!DS->IsReadyAt(RideTo)`
   tenere l'auto ferma a `LiftT = 0.89f` (a schermo nero), e dopo 6 s di attesa chiamare `DS->ForceReadyAt(RideTo)`; poi proseguire. Senza, chi arriva su un ponte non ancora caricato cade nel vuoto.
2. **Crew Berthing: "Deck 3" sul piano del Ponte 4.** Il Berthing dice DECK 3 ma poggia a z -46 come la Mess (il piano di Deck 3, -42, è sotto la pelle interna dello scafo). Il piano lo registra su `plane: 4` con `label_deck: 3`, e nell'atrio c'è una targa "DECK 3".
   Due scelte: (A) tenere "Deck 3" (canon) e alzarlo di 4 m (sotto il blocco: lo scafo è già aperto, punto 3); (B, consigliata) chiamarlo **Deck 4 · Section C** e dire nella BIBBIA che il Ponte 3 ha gli alloggi ufficiali e la palestra (adesso lo sono davvero). Per (B) cambiare: `data/ship/aquila_berths.json` (`name`, `signage`),
   `AstraShipSubsystem.cpp`, `ASTRAPlayerController.cpp` (la lista delle tappe dell'ascensore), `AstraHangar.cpp` (~413) e il commento di `AstraHangar.h`, i docstring di `build_berths.py`/`berths.py`, e nell'atlante `room_deck3` (l'etichetta dell'atrio).
3. **Lo scafo sotto il blocco (Ponti 2 e 3): fatto da ARTE-NAVI, da verificare camminando.** Il blocco superiore (x hull -327,6..132,6) e l'isola erano solidi chiusi sopra lo scafo inferiore: la faccia inferiore del blocco pendeva 1,08 m sopra il pavimento del Ponte 3 e il Ponte 2 stava dentro il blocco. ARTE-NAVI (unita il 1/10) ha aperto lo scafo (`art/blender/ship3_astra.py`: il blocco e l'isola poggiano sullo scafo inferiore senza fondo e senza facce nello spazio dei ponti) e il suo controllo `nave_checks` legge **questo piano** (`decks[].envelope`: l'esterno non deve avere vertici dentro nessun ponte). Con i ponti 2 e 3 costruiti: rigenerare lo scafo e controllare camminando sul 2 e sul 3 che non si vedano piani fantasma dall'interno (faccia inferiore del blocco, pareti dell'isola); se si vedono, è lì. Lo scafo non ha collisione né ombra.
4. **Radiatori sul Ponte 5.** *Fatto da DISTRUZIONE*: `RadiatorHit` mette i danni ai radiatori sul **Ponte 7**, sezioni E–G (ala per ala), e manda la squadra al locale pompe del collettore (`radiator_pumps`) se il piano lo ha.
5. **Il Flight Deck solo in ascensore.** Il suo ingresso è un'alcova a z -72,8, il corridoio del Ponte 9 è a -66: nessun cammino a piedi (il piano lo sa: arco con salto di 6,8 m che VITA percorre come un ascensore). Se si vuole una rampa o una scala, serve una torre dedicata.
6. **Il Ponte 1 e `build_bridge_v3.py`**: lo Studio sostituisce un modulo e due pannelli del corridoio; lanciare `build_ship_interior.py` dopo `build_bridge_v3.py` (o far sapere al secondo di saltarli: etichette `CorrPort_Window`, `CorrPort1_0_*_R`).
7. **Atlante delle etichette** (`tools/art/ship_textures.py`, fuori dalla lista dei file): sono state aggiunte le targhe e i tag dei nuovi ponti (3936 di 4096 px usati: restano ~160 px di altezza; il prossimo gruppo di tag ne vuole un secondo atlante).
8. **Cottura.** Verificare che `/Game/ASTRA/Maps/Decks` (le dodici mappe) e `/Game/ASTRA/Kit/Ship` finiscano nel pacchetto (i sotto-livelli sono riferimenti deboli di L_Bridge).
9. **Prestazioni, opzionale.** Con il Capitano su un ponte di mezzo tickano ~320 `AAstraDoor` (ognuna scorre i camminatori vicini): un `TickInterval` di 0,1 s quando la porta è ferma e nessuno è a meno di 6 m basta; la compilazione unity dei file nuovi (`AstraLampPool`, `AstraDeckStreaming`, `AstraDeckShell`, `AstraNaveCommandlet`) è stata provata nella worktree.

## 9. Limiti noti

- **Non provato nell'editor.** Il kit e le anteprime sono verificati in Blender (Eevee) e con i raggi; il piano con i controlli e `tools/life.py`; il C++ compilato; lampade e ponti attorno al Capitano dal banco `-run=AstraNave`. Lo script di Unreal (parametri delle istanze, orientamento delle `RectLight`, proprietà `locked` della porta, tolleranza dei limiti dopo l'importazione: 6 cm,
  l'apertura dello Studio) e tutto ciò che è GPU (tempo di fotogramma, memoria, il carico di un ponte con i proxy di scena) vanno provati dal lead: se l'importazione dice `bounds problems` o una porta non si chiude a chiave, è lì.
- **La navetta della Spine non corre.** Ci sono le sette fermate (A, B, C, D, E, G, H) con la vettura ferma; non c'è un arco `shuttle` nel grafo né un veicolo che si muove. La sezione F non ha fermata: il suo tronco di Spine libero (20 m) è più corto di una fermata (24 m) e una stanza non può stare a cavallo del portello stagno.
- Il Ponte 4 in Unreal è scuro nelle anteprime senza luci: le luci del pool (10 alla volta) fanno la stanza; il rimbalzo delle anteprime è finto (una luce d'area sotto il soffitto), Lumen farà il suo.
- Le porte delle stanze verso il passaggio dal lato lontano (`_far`) esistono nel piano; nel Lounge e nella sala giochi aprono sul passaggio laterale.
- Sezione E del Ponte 4: solo corridoi e le stanze esterne (la sala Engineering tiene il centro); sezione H solo stores interni. Le stanze esterne finiscono a x -484 (l'inviluppo si stringe).
- L'Observation Deck e il Bow Observation hanno vetri traslucidi (mesh non Nanite); dietro non c'è altro che il cielo: lo scafo non copre le finestre. Lo stesso per l'oblò dello Studio (un campo di stelle di lampade, non un'immagine del cielo vero).
- Il reticolo è ortogonale: non c'è un modulo di curva. La scala a pioli autonoma (`SM_SHIP_LadderTrunk`) è pronta ma non piazzata.
- **VITA e i nuovi luoghi.** I marines non hanno l'hangar (`kinds: ["hangar"]`) tra i luoghi di servizio (armory, range, cabins): nessun fante sta accanto ai Kestrel, mentre gli addetti al Flight Deck e i piloti (che hanno `hangar`) useranno l'hangar delle navette come un secondo hangar; aggiungere
  `{"kinds": ["hangar"], "dept": "security", "weight": 2}` ai marines in `data/ship/aquila_life.json` (non è un mio file). Lo Studio (`ready_room`) e le fermate (`transit`) non sono tra i luoghi di servizio né di svago del file: restano deserti finché VITA non li elenca (hanno i loro posti, pronti).
- Le mesh dei ponti grossolani non esistono più (nessun ponte è grossolano), ma `plan_deck(coarse=True)` resta per provare un ponte nuovo: basta toglierlo da `BUILT_DECKS` (`ship_plan_gen.py`).
