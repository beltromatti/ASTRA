# NAVE — l'ASN Aquila come nave vera (fasi F4.1, NAVE-2 e NAVE-3)

Il "DNA" della nave (`data/ship/aquila_plan.json`), il kit di moduli e stanze dell'interno (Blender, nel linguaggio della plancia v3) e gli strumenti per metterli nel livello e farli girare su un MacBook Air. **Tutti i dodici ponti sono costruiti.**
NAVE-3 ha **ripensato l'interno come lo pianificherebbe una nave vera**: un programma ragionato (§5: ogni spazio sta dove sta per una ragione), un labirinto credibile con corridoi di servizio, gallerie dello scafo e tubi di Jefferies (§6), **34 pozzi di turboascensore** con 291 approdi (§7: il contratto con ASCENSORI), la **navetta della Spine** in un tunnel sul Ponte 5
con otto fermate (§8) e una segnaletica calcolata sul grafo (§9). Sul lato del gioco la nave non è un livello di attori: **istanze** al posto dei moduli, **lampade come dati** con un pool di luci vere, **un sotto-livello per ponte** in streaming (§11bis). Tutto ciò che è scritto nel gioco è in inglese; questa pagina è in italiano con i nomi ufficiali.

Stato (piano versione 2): **3 234 compartimenti** (1 065 stanze del programma), 2 028 porte, 13 730 nodi e 15 298 archi del grafo (un solo componente connesso), 4 538 lampade, 4 096 posti (`stations`), 746 posti letto; **0 problemi, 0 avvisi** in `ship_checks.py`;
`tools/life.py check` OK; `tools/damage.py run --scenario all` **46/46**; kit con prove a raggi lungo tutti gli archi di corridoio e di porta dei 12 ponti: **0 bloccati**, e controllo dei posti (con il sedile sotto chi siede): **0 sul mobilio**.
**Non provato in Unreal** (l'editor è del lead): vedi §14 e §11bis per cosa guardare camminando.

## 1. Comandi, nell'ordine

```
uv run --python /opt/homebrew/bin/python3.13 --with pillow --with numpy python tools/art/ship_textures.py          # atlante delle etichette: art/_cache/ship/
uv run --python /opt/homebrew/bin/python3.13 --with pillow --with numpy python tools/art/interior_textures.py      # ARTE-INTERNI: le texture 1K ambientCG delle stanze (CC0, senza account): art/_cache/textures/
uv run --python /opt/homebrew/bin/python3.13 --with pillow --with numpy python tools/art/polyhaven_models.py --all # i modelli Poly Haven delle piante (CC0) e le loro texture
python3 art/blender/ship_plan_gen.py                                                                              # piano: data/ship/aquila_plan.json + la copia sottile Content/ASTRA/Data/aquila_plan.json
python3 art/blender/ship_checks.py                                                                                # controlli del piano (0 problemi attesi)
python3 tools/life.py check && python3 tools/life.py stage                                                        # VITA: posti, stanze, case; copia il file della vita accanto al piano
python3 tools/damage.py run --scenario all                                                                        # DISTRUZIONE: 46/46 sul piano vero (serve l'editor compilato per questa copia)
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python-exit-code 1 -P art/blender/ship_kit.py   # FBX + manifest in art/export/ship (una decina di minuti)
python3 art/blender/ship_budget.py                                                                                # il budget per ponte (legge il manifest o --stats)
tools/ue.py pyfile tools/ue_scripts/build_ship_interior.py                                                        # il lead: materiali (anche MI_SHIP_* di room_materials.json), kit, un sotto-livello per ponte, L_Bridge
blender -b --factory-startup --python-exit-code 1 -P art/blender/<messhall|berths|medbay|engineering|hangar>.py   # le cinque stanze M1 (FBX in art/export/<nome>), poi nell'editor:
tools/ue.py pyfile tools/ue_scripts/build_<messhall|berths|medbay|engineering|hangar>.py                          # idempotenti: sostituiscono la loro cartella e rifanno le luci
UnrealEditor-Cmd ASTRA.uproject -run=AstraNave -nullrhi -unattended -nosound                                      # il banco senza grafica: lampade, streaming, ponti attorno al Capitano
```

Anteprime (Eevee, senza editor): `Blender -b … -P art/blender/ship_kit.py -- --no-export --no-checks --preview docs/progressi/nave --views rooms,modules,modules3,car,signs --samples 28`
(una stanza: `--only ReadyRoom`, con i nomi delle mesh senza `SM_SHIP_`; `--room-views door,corner_a,plan`: la vista `plan` mostra dall'alto **i posti** come dischi colorati con la freccia dello sguardo — verde in piedi, giallo al lavoro, blu seduto, arancio a mensa, rosa a dormire —, il modo più veloce per vedere una sedia senza nessuno o uno sguardo contro il muro; i punti di vista di ogni stanza sono in `ship_kit_preview.ROOM_VIEWS`).
Solo i conteggi di triangoli, senza esportare: `… -- --no-export --stats art/_cache/ship_stats.json`; solo i posti e le rotte: `… -- --no-export --plan data/ship/aquila_plan.json --spots --only Barracks` (senza `--only` anche le rotte di tutti i ponti). Piano in pianta: `uv run … --with pillow python tools/art/ship_planview.py 5 out.jpg [--x0 -260 --x1 -60 --scale 6 --graph]`.
Il piano è la fonte unica: lo leggono `ship_kit.py` (quali targhe, cartelli e segnali servono), `build_ship_interior.py` e il gioco (`UAstraShipPlan`, che lo cerca in `Content/ASTRA/Data/aquila_plan.json`, poi in `data/ship/`), VITA, DISTRUZIONE e ASCENSORI.

## 2. Sistema di riferimento e pila dei ponti

Come tutto il gioco: X a prua, Y a dritta, Z in su, metri (Unreal: cm, stessi assi); l'origine è il punto del pavimento della plancia sotto la poltrona del Capitano. Lo scafo `SM_SHIP_ASTRA_Aquila` sta in (-172, 0, -62) m: coordinate dello scafo = mondo + (172, 0, 62). Ponti a passo di 4,0 m (0,3 struttura + 3,4 libero + 0,3 struttura); le stanze sono alte al più 3,7 m (il soffitto è la struttura del ponte sopra).

| Ponte | Nome | z pavimento | Contenuto (BIBBIA v0.3 §6) | Stato nel piano |
|---|---|---|---|---|
| 1 | Command | 0 | Bridge, Captain's quarters, ready room, command corridors | plancia e quarters esistenti; **Ready Room costruita** (§5.3) |
| 2 | CIC & Communications | -36,7 | CIC, briefing, uffici dei reparti, comunicazioni, torrette | **costruito**: CIC, Auxiliary Control, suite degli ufficiali, VLS, barbette |
| 3 | Crew Country | -42,0 | alloggi degli ufficiali, palestra, wardroom | **costruito**: wardroom, camere e cabine, uffici e aule |
| 4 | Crew Services | -46,0 | Mess Hall, cambusa, lounge, osservazione | **costruito**: Mess Concourse, Berthing, bar, cappella, negozio, simulatori |
| 5 | Science & Transport | -50,0 | laboratori, Transporter Room, archivio sensori; **la navetta interna della Spine** | **costruito**: laboratori, Transporter, nucleo A, impianti; **tunnel e otto fermate della navetta** |
| 6 | Medical | -54,0 | Medbay, sala operatoria, quarantena, farmacia | **costruito**: il complesso medico con dentista, obitorio, counselling |
| 7 | Engineering & Power | -58,0 | Main Engineering, reattore, controllo di potenza, radiatori | **costruito**: potenza, centrale ausiliaria, aria-acqua-rifiuti, DC centrale |
| 8 | Marines & Armory | -62,0 | armeria, caserma, poligono, hangar delle navette d'assalto | **costruito**: caserme, cella, ufficio della sicurezza, nucleo B |
| 9 | Flight | -66,0 (Flight Deck: -72,8) | Flight Deck: tubi di lancio, hangar, officina, cabina di controllo | **costruito**: operazioni, droni, alloggi dei piloti, stive |
| 10 | Holds & Munitions | -70,0 | stive, depositi di munizioni, magazzini | **costruito**: il nucleo corazzato |
| 11 | Workshops & Damage Control | -74,0 | officine, fabbricazione, riparazioni, squadre del DC | **costruito**: il cantiere |
| 12 | Keel | -78,0 | serbatoi, massa di reazione, cunicoli di manutenzione | **costruito** con cunicoli stretti (tono K) |

Le stanze **esistenti stanno dove sono** (mai spostate): il piano le registra alle posizioni dei loro file di dati (`compartments` con `status: existing`, `data`: il file). Volumi speciali: la sala di Main Engineering (14 m) occupa anche i piani dei ponti 4–6 in x -372..-330, |y| < 15; il Flight Deck (20 m) attraversa i ponti 6–11 in x 60..218, |y| < 29 (`spans_decks`).
**Sezioni A–H** da prua a poppa, per ponte (`decks[].sections`); i limiti stanno su una griglia di 4 m e ogni sezione è una zona con portelli stagni ai confini. Sul Ponte 4: A [104, -104], B [-104, -160], C [-160, -248], D [-248, -320], E [-320, -384], F [-384, -440], G [-440, -484], H [-484, -524].
**Inviluppo** (`decks[].envelope`): la mezza larghezza utile per x, calcolata dalla matematica dello scafo meno 1,5 m di parete; nessun compartimento esce dall'inviluppo (controllo).

## 3. Il reticolo di 4 m

Corridoio = "fessura" di 4 m (3,1 m liberi + 0,45 di parete per lato); moduli lunghi 4 m con l'origine sul pavimento, sull'asse, all'estremità di poppa (`x` 0..4); giunzioni 4 × 4; le stanze sono multiple di 4 m e le loro porte cadono sul centro di un modulo (x locale ≡ 2 mod 4). Stanza: origine sul pavimento
all'angolo lato corridoio, x lungo il corridoio, y **dentro** la stanza; a sinistra (babordo) il layout ruota di 180°, lungo y di ±90°. Porte 1,6 × 2,4 (`AAstraDoor`), cancelli 3,2 × 3,0, portello stagno di sezione 2,0 × 2,5, boccaporti 0,95 × 2,1.
I toni dei corridoi sono cinque (S, P, K, V, T: tabella del §6); i tronchi della Spine finiscono contro le grandi sale delle stanze esistenti (`reach_rooms`): un raccordo (`SM_SHIP_<tono>_Stub<cm>`) chiude lo spazio che resta. **Torri delle scale** (colonne a x +44, −92, −300, −452 …): `SM_SHIP_StairTower` (due rampe a tornante, 4 m di dislivello), `…Top`/`…Bottom`, `…Cap` sul Ponte 2, `…53` sul 3 (5,3 m attraverso il ponte corazzato).

## 4. Lo schema del piano (`data/ship/aquila_plan.json`, versione 2)

Compatto, generato (`ship_plan_gen.py`), letto dal gioco (`UAstraShipPlan`: **campi, tipi di arco e `p` in metri sono stabili**; quelli aggiunti da NAVE-3 sono in corsivo). Chiavi: `id, version (2), generator, frame, decks, compartments, doors, vertical, transit, graph{nodes, edges}, systems, placements, notes`.

- `decks[]`: `id, name, programme, z, clear, ceiling, structure, pitch, volume, envelope{x_fwd, x_aft, half_width[[x, hw]…]}, sections[{id, x:[min, max]}]`.
- `compartments[]`: `id, deck, section, kind, name, bounds[x0, y0, x1, y1] (mondo, m), z[pavimento, soffitto], status (built | planned | existing), doors[], dept, systems[], stations[], lights[]`; le stanze fatte: `prefab, mesh, pos, yaw, plate, lane, size[L, D, h], crew_slots`; i corridoi: `passage, modules[i0, i1], tone` (*S, P, K, V, T*);
  le esistenti: `plane, label_deck, entrance, data, capacity, spans_decks, note`. *Nuovi `kind`*: `lobby` (lobby degli ascensori), `lift` (il pozzo: compartimento che attraversa i ponti, `spans_decks, shaft`), `trunk` (cella di un tubo di Jefferies), `tunnel` e `transit` (la navetta), `lifepod`, `airlock`, `dental`, `morgue`, `counselling`, `brig`, `security`, `computer`, `simulator`, `shop`, `chapel`…
  - `stations[]`: `id, role, kind (sit | stand | work | eat | sleep | watch), pos[x, y, z], yaw, dept` (le usa VITA; i posti seguono l'arredo vero: **chi siede ha un sedile sotto i fianchi**, controllato; *z = pavimento + `dz`* per chi sta su una pedana o in un simulatore).
  - `lights[]`: `id, type (rect), pos, lumens, temperature, size[x, y], radius, shadows`: *sono le lampade*, dati e non attori.
- `doors[]`: `id, deck, pos[x, y, z], yaw, width, height, kind (door | gate | blast | sliding), a, b, locked`, più `wall, passage, plate, side, boundary` (blast: `[sezione aft, sezione fwd]`), `existing`, `planned`, *`lift`: l'id del pozzo, per le porte d'approdo (di ASCENSORI: `build_ship_interior.py` le salta)*.
- `graph.nodes[]`: `id, deck, p[x, y, z], kind (corridor | door_in | room | station | stair | lift | lift_car | trunk | platform), comp, passage`. `graph.edges[]`: `a, b, len, kind (walk | door | stair | lift | shuttle), door, w, blast, cost`, *`shaft`* (gli archi `lift`), *`ladder: true`* (gli archi `stair` dei tubi di Jefferies).
  Un nodo di corridoio per modulo; ogni stanza ha un nodo dietro ogni porta, un `hub` al centro, un nodo per posto; i portelli stagni sono archi `door` con `blast: true`. Un arco `door`/`walk` tra due quote lontane più di 1,5 m (la porta del Flight Deck è 6,8 m sotto il corridoio del Ponte 9) VITA lo percorre come un ascensore. Un solo componente connesso (verificato).
- *`vertical[]`* (§7): `turbolift | bridge | service | cargo` (pozzi con `landings[]`), `stair` (una colonna di scale per torre: `nodes`, `towers`) e `trunk` (tubi di Jefferies: `nodes` per ponte, `trunks`, `landings[]` con i campi della salita: §6). *`transit[]`* (§8): `spine_shuttle` con `path[]`, `stops[]` (le otto fermate A–H), `car{mesh, length}`, `speed, accel, dwell, gauge`.
- `systems`: per sistema di bordo i compartimenti che lo ospitano. `placements{ponte: [...]}`: cosa mettere nel livello: `mesh, pos, yaw, folder, label, cls (module | room | sign | plate), comp`.

Controlli del piano (`ship_checks.py`): dentro l'inviluppo; nessuna sovrapposizione in 3D; porte sui muri e di misura giusta; grafo connesso, ogni compartimento raggiunto; nessuna stanza a cavallo di due sezioni; punti fissi del canon; **il programma** (le stanze richieste, i posti letto e le scialuppe per tutti: §5); **la rete verticale** (ogni pozzo ferma dove dice, pozzi e lobby dove i record li mettono, scale e tubi senza ponti mancanti, **nodo di attesa a 0 cm dalla posizione davanti alla porta d'approdo**,
la navetta con un arco `shuttle` tra le fermate e un tunnel lungo tutto il percorso); la **distanza a piedi dall'ascensore più vicino** per ponte (avviso sopra 100 m al 90° percentile; 110 per la chiglia). Risultato del piano attuale: **0 problemi, 0 avvisi**.

## 5. Il programma: la nave progettata come una nave vera (NAVE-3)

Il piano di NAVE-2 riempiva le corsie in modo ciclico (125 armadietti del damage control, 23 lavanderie, nessun dentista, nessuna cella, nessun nucleo di calcolo). NAVE-3 lo rifà **dal progetto, non dal ciclo**: ogni spazio sta dove sta per una ragione, e la ragione è scritta accanto allo spazio
(`ship_design.py`: le strutture fisse e il loro `why`; `ship_design_decks.py`, `ship_design_decks2.py`: un programma per ponte, con il commento del perché). Il metodo ha quattro livelli, nell'ordine in cui si decidono:

1. **Le strutture fisse** (`ship_design.py`): i passaggi (la Spine y 0, lo Starboard e il Port Passage y ±20), le **banche degli ascensori** (§7), le **torri delle scale** con il loro posto del damage control, le **colonne dei tubi di Jefferies** (§6), le **gallerie dello scafo** (§6) e il banco di comando sotto la plancia. Stanno alle stesse x su ogni ponte che le serve: una colonna è una colonna.
2. **I programmi** (`ship_design_decks*.py`): per ogni ponte e sezione un elenco di stanze con una sintassi minima (`key`, `key*N`, `key:Nome_Con_Trattini`, `key?` se facoltativa, `pool`, `gap:N`): non un ciclo, una lista scritta. Le stanze **esistenti** (plancia, alloggi del Capitano, Mess Hall, Medbay, Berths, Main Engineering, Flight Deck) restano dove sono e il resto si organizza attorno.
3. **L'impaginatore** (`ship_layout.py`, `Deck.flow`): riempie ogni corsia da 16 m (o da 8 m, o da 4 m: le stanze di servizio) dalla paratia di prua della sezione verso poppa, **attorno alle strutture fisse**, rispettando le regole di occupazione del corridoio (un modulo con un ramo da una parte non ha una porta dall'altra; due porte sullo stesso modulo no) e il confine di sezione (nessuna stanza lo scavalca). Una stanza che non sta
   **non sparisce in silenzio**: il piano si ferma con un errore (`DesignError`) o la mette tra gli opzionali `?`.
4. **I controlli** (`ship_checks.py`, `_check_programme`): ogni stanza che il programma deve avere c'è (`REQUIRED`: dentista, obitorio, nucleo di calcolo A e B, cella, ufficio della sicurezza, centrali del damage control, impianti dell'aria, dell'acqua e dei rifiuti…); **posti letto per 560 persone più la riserva del 10 %** (616: oggi 746, di cui 662 nelle stanze nuove e 84 negli esistenti), **scialuppe per tutti** (40 capsule da 20 posti = 800), nessuna stanza fuori dall'inviluppo o a cavallo di una paratia.

### 5.1 Chi sta dove, e perché

| Reparto | Dove | Perché lì |
|---|---|---|
| Comando | Ponte 1 (plancia, Ready Room); Ponte 2 sezioni A–C: suite degli ufficiali superiori, **CIC** (B), comunicazioni, briefing; **Auxiliary Control** (H) | il CIC è a pochi minuti dagli ascensori di plancia; l'Auxiliary Control è il secondo centro di comando, il più lontano possibile dalla plancia |
| Armi | Ponte 2 D–G: controllo del fuoco, torri e barbette, **VLS**; Ponte 10: **depositi di munizioni nel nucleo corazzato** (sezioni C–E, il centro, la corazza più spessa); Ponte 8: armeria dei marines e armeria della sicurezza | i depositi stanno il più lontano dallo scafo esterno, con la Spine come via delle munizioni; le torri sotto le torrette che servono |
| Scienza | Ponte 5 A–C: laboratori, sensori, archivi, **Transporter Room** e **Astrometrics** (B), **nucleo di calcolo A** (C); nucleo B sul Ponte 8 H | vicino ai sensori che guardano a prua; i due nuclei, lontani tra loro (ridondanza) |
| Medico | Ponte 6, sezione C attorno all'ingresso del Medbay esistente: **due sale operatorie, farmacia, dentista, reparto di isolamento, obitorio, ambulatorio di counselling e cappellano**, laboratorio, archivi; B: riabilitazione, giardino medico, banca del sangue | un complesso a un minuto dalla porta del Medbay e dalla banca d'ascensori D |
| Sicurezza e marines | Ponte 8: **hangar delle navette d'assalto con due Kestrel**, armeria, kit di abbordaggio (B); caserme, palestra, **poligono** (C); **cella, ufficio della sicurezza**, sala interrogatori, deposito prove (D) | la caserma a un ascensore dalla baia; il Master-at-Arms a pochi minuti da ovunque, tra i marines e la banca del Berthing |
| Ingegneria e potenza | Ponte 7: **Main Engineering** (esistente), **controllo di potenza, quadri, banchi di condensatori, centrale ausiliaria** davanti alla sala (E: i bus restano corti); **impianti dell'aria, dell'acqua e dei rifiuti** a metà nave (C–D: vicino a chi servono), compressori, pompe dei radiatori (G–H); **damage control centrale** (B, vicino agli ascensori di plancia, con due gemelle: Ponte 8 H e Ponte 11) | chi comanda la macchina è a pochi minuti dalla plancia; le tre centrali del DC sono lontane tra loro |
| Volo | Ponte 9: operazioni di volo, sale di attesa, officine avioniche, **hangar dei droni**, munizioni degli aerei, alloggi dei piloti; il Flight Deck (esistente) a prua; ascensore merci della banca Flight | tutto ciò che serve a un velivolo a meno di un minuto dal ponte |
| Logistica | Ponti 10–11: stive, celle frigorifere, magazzini secchi, **fabbricazione e riparazione** (cantiere della nave), ricambi | il cantiere sotto il Flight Deck, i magazzini nel nucleo |
| Servizi | Ponte 4 (la "via principale" dei marinai: **Mess Concourse** con caffè e negozio, Mess Hall, cambusa, **bar, cappella, negozio, barbiere e sarto, biblioteca, sale giochi, simulatori**, palestra, osservazione, serra); cabine e **bagni, lavanderie e magazzini di sezione** accanto a ogni gruppo di cuccette | gli alloggi non sono un ciclo: **ogni gruppo di 28 cuccette ha i suoi bagni e la sua lavanderia nello stesso nodo** |
| Alloggi | ufficiali: Ponte 2 (suite), 3 (camere); sottufficiali e equipaggio: **14 sale cuccette da 28** sui Ponti 4, 6, 9, 11 più il Crew Berthing esistente (84); marines: 4 caserme sul Ponte 8; piloti: Ponte 9; **12 cabine singole** sui Ponti 2–3 | vicino a mensa, bagni, lavanderia e al proprio posto di lavoro |
| Salvataggio | **40 baie di capsule** da 20 posti (800) e **40 camere stagne con armadietti delle tute** (Ponti 5–7, 9, 11) nelle gallerie dello scafo; una stazione del DC a ogni torre | l'uscita è sempre a poche decine di metri da un corridoio |

La somma: **1 065 stanze del programma** e 211 tra lobby, torri e pozzi, su **3 234 compartimenti** (con i 1 719 tratti di corridoio, le 168 celle dei tubi e i 33 tratti di tunnel).

### 5.2 Ponte per ponte

| Ponte | Cosa è | Il disegno |
|---|---|---|
| 1 Command | la plancia, gli alloggi del Capitano, la **Ready Room** (§5.3) | esistente; la lobby dei due ascensori di plancia sotto il suo pozzo (x −24,3) |
| 2 CIC & Communications | il cervello della nave | A: suite degli ufficiali superiori; **B: CIC con briefing e comunicazioni**; C: comunicazioni e intelligence; D–G: controllo del fuoco, difesa di punto, barbette, **VLS**; **H: Auxiliary Control**; strisce esterne: cabine degli ufficiali di guardia |
| 3 Crew Country | gli ufficiali | A: **wardroom**, salotto e biblioteca degli ufficiali, palestra; B: ufficio dell'esecutivo e camere; C–H: uffici dei capi reparto, aule di addestramento, camere con bagni e lavanderie ai nodi; cabine singole lungo i passaggi |
| 4 Crew Services | la via principale | A: **la strada dei marinai** dal Bow Observation al Concourse (biblioteca, cappella, negozio, barbiere, bar, lounge, sala giochi, serra, simulatori, palestra); B: **Mess Concourse, Mess Hall, cambusa**; C: Berthing e il suo atrio con due sale cuccette, bagni, lavanderia; D: **svago aft** (giochi, bar, simulatori); E–H: il quartiere degli ingegneri attorno a Main Engineering |
| 5 Science & Transport | scienza e **la navetta** | A–C: laboratori, sensori, archivi, **Transporter, Astrometrics, nucleo A**; D–H: impianti che servono i ponti sopra (refrigerante, pompe, aria, acqua); **la corsia esterna di dritta è il tunnel della navetta** (§8) |
| 6 Medical | il complesso medico | §5.1; D–H: quartiere degli ingegneri (4 sale cuccette, sottufficiali, lounge, palestra, biblioteca) |
| 7 Engineering & Power | macchina e potenza | §5.1: sala reattore (esistente), centrale ausiliaria, controllo, quadri, condensatori davanti; aria-acqua-rifiuti a metà nave; DC centrale vicino agli ascensori di plancia |
| 8 Security & Marines | abbordaggio e ordine | §5.1; E–F: officine accanto alla base della sala di Main Engineering (alta quattro ponti); G–H: nucleo B e DC centrale di poppa |
| 9 Flight Operations | il ponte di volo | C: operazioni, sale d'attesa, officine, droni; D–E: alloggi dell'Air Group; F–H: stive |
| 10 Cargo & Magazines | il nucleo corazzato | depositi al centro, stive e celle a prua e a poppa, l'ascensore merci in mezzo alle stive |
| 11 Fabrication & Repair | il cantiere | riparazione e fabbricazione sotto il Flight Deck, officine, ricambi, la terza centrale del DC |
| 12 Keel | serbatoi | combustibile, refrigerante, massa di reazione, il sistema di cunicoli (tono K); nessuno ci vive |

### 5.3 Il Ponte 1: lo Studio del Capitano (Ready Room)

Il blocco tra i due corridoi della plancia (canon, BIBBIA §6): **12 × 4,2 × 2,9 m** (x da -20,8 a -8,8, y da -2,1 a +2,1), a filo con la parete di poppa della plancia (-8,8) e con la testa dei corridoi (-20,8); il tetto sta a 3,2 m come quello dei corridoi.
Dentro: sul muro di poppa un **oblò** con un campo di stelle e il bordo di un pianeta sopra una credenza, la **scrivania del Capitano** con la poltrona alta dietro e due sedie per i visitatori, la bandiera e un mappamondo illuminato negli angoli, tre librerie; verso prua un divano di fronte a un tavolino con due poltrone e una lampada,
un **tavolo olografico** sotto un anello di luce e il **piano tattico** sul muro di prua: una stanza di lavoro, calda, non una sala. Nove posti, quattro lampade, targa `CAPTAIN'S READY ROOM · PRIVATE · COMMAND` sopra la porta.

**La porta.** I corridoi della plancia sono del vecchio kit (`SM_COR_*`, piazzati da `build_bridge_v3.py` come attori di L_Bridge) e non hanno porte nei muri laterali. Il piano mette la porta (**1,4 × 2,2 m**, scorrevole, in (-15,8; -2,2; 0)) nel primo vano di parete del modulo con finestra e sostituisce quel modulo con `SM_SHIP_BridgeCorridorDoor`.
`build_ship_interior.py` (flag `OPEN_READY_ROOM`) distrugge in L_Bridge il modulo con finestra (`CorrPort_Window`) e i due pannelli del vano (`CorrPort1_0_*_R`): **va lanciato dopo `build_bridge_v3.py`**.

### 5.4 Le stanze per tipo (il rapporto del programma)

Quante stanze di ogni tipo, quanti m² e su quali ponti (il nome è quello ufficiale della scheda `ship_spec.py`). Le lobby degli ascensori (146) e le torri delle scale (66) non sono elencate.

- **Comando** (51 stanze): Department Offices ×14 (3584 m², P. 2,3,4,6,7,8); Records & Archive ×15 (2880 m², P. 2,3,5,6,8,9); Briefing Room ×8 (2048 m², P. 2,3,8,9); Senior Officers' Quarters ×6 (1728 m², P. 2); Communications Centre ×3 (1152 m², P. 2); Observation Deck ×2 (768 m², P. 4); Bow Observation ×1 (640 m², P. 4); Combat Information Centre ×1 (512 m², P. 2); Officers' Wardroom ×1 (384 m², P. 3).
- **Scienza** (56 stanze): Cold Stores ×13 (4992 m², P. 4,5,6,9,10); Science Lab ×13 (4992 m², P. 5,6,8); Hydroponics Bay ×7 (2688 m², P. 4,5,6); Sensor Array Room ×10 (2560 m², P. 2,5); Physics Lab ×5 (1920 m², P. 5); Biology Lab ×2 (768 m², P. 5); Computer Core ×2 (768 m², P. 5,8); Sensor Archive ×2 (512 m², P. 5); Transporter Room ×1 (384 m², P. 5); Astrometrics ×1 (384 m², P. 5).
- **Medico** (7 stanze): Surgery ×2 (512 m², P. 6); Quarantine Ward ×1 (384 m², P. 6); Morgue ×1 (192 m², P. 6); Pharmacy ×1 (192 m², P. 6); Counselling & Chaplaincy ×1 (192 m², P. 6); Dental Clinic ×1 (192 m², P. 6).
- **Sicurezza** (38 stanze): Munitions Magazine ×14 (5376 m², P. 8,9,10); Point-Defence Control ×6 (1536 m², P. 2); Turret Barbette ×4 (1536 m², P. 2); Marine Barracks ×4 (1536 m², P. 8); VLS Magazine ×3 (1152 m², P. 2); Firing Range ×1 (640 m², P. 8); Assault-Shuttle Bay ×1 (512 m², P. 8); Armory ×2 (512 m², P. 8); Brig ×1 (384 m², P. 8); Kit Room ×1 (256 m², P. 8); Security Office ×1 (256 m², P. 8).
- **Ingegneria e impianti** (369 stanze): Technical Space ×113 (14464 m², P. 2,3,4,5,6,7,8,9,10,11); Maintenance Crawlway Hub ×34 (8704 m², P. 12); Machinery Space ×19 (7296 m², P. 5,7,8,11); Machine Shop ×15 (6720 m², P. 7,8,11); Compressor Room ×16 (6144 m², P. 5,7,8,11); Damage-Control Station ×65 (4160 m², P. 2,3,4,5,6,7,8,9,10,11,12); Radiator Manifold ×9 (3456 m², P. 5,7); Fabrication Shop ×5 (2240 m², P. 11); Atmosphere Plant ×4 (1536 m², P. 5,7,8); Water Reclamation Plant ×4 (1536 m², P. 5,7); Repair Bay ×3 (1536 m², P. 11); EVA Airlock ×40 (1280 m², P. 5,6,7,9,11); Damage-Control Central ×3 (1152 m², P. 7,8,11); EVA Suit Lockers ×32 (1024 m², P. 7,9,11); Switchgear Hall ×2 (768 m², P. 7,8); Power Control ×2 (768 m², P. 7); Auxiliary Power Plant ×1 (512 m², P. 7); Waste Processing Plant ×1 (384 m², P. 7); Capacitor Hall ×1 (384 m², P. 7).
- **Volo e stive** (218 stanze): Section Stores ×125 (16000 m², P. 2,3,4,5,6,7,8,9,10,11); General Stores ×40 (15360 m², P. 7,8,9,10,11); Dry Stores ×26 (9984 m², P. 4,6,7,8,9,10,11); Cargo Hold ×19 (9728 m², P. 9,10); Aircraft Workshop ×2 (896 m², P. 9); Simulator Bay ×2 (768 m², P. 4); Pilots' Ready Room ×2 (768 m², P. 9); Drone Bay ×1 (512 m², P. 9); Flight Operations ×1 (384 m², P. 9).
- **Servizi e alloggi** (236 stanze): Crew Lockers ×98 (12544 m², P. 3,4,5,6,7,8,9,10,11); Heads · Showers ×37 (7104 m², P. 3,4,6,7,8,9,11); Crew Berthing Bay ×14 (5376 m², P. 4,6,9,11); Crew Lounge ×13 (4992 m², P. 3,4,6,7,8,9); Laundry ×21 (4032 m², P. 3,4,6,8,9,11); Crew Cabins ×9 (2880 m², P. 6,9); Gymnasium ×6 (2304 m², P. 3,4,6,8,9); Officers' Staterooms ×7 (2240 m², P. 3); Games Room ×5 (1920 m², P. 4); Library ×5 (1280 m², P. 3,4,6); Crew Bar ×3 (1152 m², P. 4); Quiet Room ×5 (960 m², P. 3,4,9); Mess Concourse ×1 (637 m², P. 4); Officers' Cabins ×6 (576 m², P. 2,3); Berthing Lobby ×1 (526 m², P. 4); Main Galley ×1 (384 m², P. 4); Chapel ×1 (256 m², P. 4); Ship's Store ×1 (256 m², P. 4); Barber & Tailor ×1 (192 m², P. 4); Galley Pass ×1 (96 m², P. 4).
- **Salvataggio e transito** (82 stanze): Reaction-Mass Tank ×17 (10880 m², P. 12); Fuel & Coolant Tank ×17 (8704 m², P. 12); Spine Shuttle Stop ×6 (2304 m², P. 5); Lifepod Bay ×40 (1280 m², P. 5,6); Spine Shuttle Stop (Bow Terminal) ×1 (384 m², P. 5); Spine Shuttle Stop (Stern Terminal) ×1 (384 m², P. 5).

## 6. Il labirinto: corridoi principali e di servizio, gallerie, tubi di Jefferies

Una nave vera non è una scacchiera di corridoi uguali. Sotto la rete principale (la Spine e i due Passage, larghi, luminosi, con i segnali) NAVE-3 mette **la rete di chi fa funzionare la nave**: stretta, bassa, calda di luce, con i suoi cancelli, che il Capitano può prendere per scorciatoia.

| Tono | Cos'è | Misure utili | Dove |
|---|---|---|---|
| **S** | la Spine (centrale, y 0) | 3,1 m × 3,4 m, luce bianco-fredda, accento "command" | ponti 2–11 |
| **P** | Starboard e Port Passage (y ±20) | 3,1 × 3,4, luce calda | ponti 2–11 |
| **K** | cunicoli: le braccia dei tubi di Jefferies e la chiglia | 1,7 × 2,5, luce ambra, portelli stagni 1,2 × 1,95 | ponte 12 e le braccia su tutti i ponti |
| **V** | **corridoi di servizio**: le gallerie dello scafo (sotto) | 2,1 × 2,7 m, luce ambra calda, tubi, nervature, armadietti | ponti 5–11, lungo lo scafo |
| **T** | il **tunnel della navetta** | 3,5 × 3,25, binari e strisce di guida | ponte 5 (§8) |

**Tubi di Jefferies.** Otto **colonne** (x +10, −50, −158, −206, −274, −342, −406, −474), una per lato su ogni ponte: **16 tubi** (`vertical[]` `kind: "trunk"`), scale a pioli 1,2 × 1,2 m che vanno dal ponte più alto della colonna alla chiglia. Dal muro esterno di ogni passaggio parte un **braccio** (un cunicolo K, 16 m dove lo scafo lo consente): il suo primo modulo è la **cella del tubo** (un'alcova con il pozzo della scala, con varianti `Trunk`, `TrunkTop`, `TrunkBottom`), il resto è un cunicolo orizzontale. Un arco `stair` con `ladder: true` unisce due celle di ponti vicini.
**Il record `trunk` per chi lo scala** (ASCENSORI, la scala a pioli del gioco; versione 2 del contratto): `id, x, y, nodes{ponte: nodo}, trunks{ponte: cella}, landings[], ends, rungs`. Ogni approdo (uno per ponte) ha `deck, z, node` e i campi della salita, tutti in metri nel sistema della nave: `ladder{x, y}` = il centro del corpo di chi si aggrappa (davanti ai pioli: 0,35 m dall'asse dei pioli, cioè `x del nodo − 1,51`), `facing` = l'imbardata verso i pioli (180: la nicchia è sempre sul lato −x del braccio, perché la cella è piazzata a imbardata 90), `step[x, y]` = il punto del camminamento dove si scende dalla scala (il nodo), `hole[x0, y0, x1, y1]` = l'impronta della nicchia (1,1 × 1,1 m, che comincia a 0,85 m dall'asse del cunicolo: chi cammina al centro non la sfiora): **sul pavimento è aperta** (nel modulo lì non c'è soletta: chi ci mette un piede cade lungo la colonna, la scala è la sola via) tranne dove `closed` è `"toe_plate"`; `closed` = `"hatch"` sul ponte più alto della colonna (il soffitto della nicchia è chiuso da un portello: la scala non esce dal ponte), `"toe_plate"` sul più basso (la chiglia: il fondo della nicchia è chiuso da una piastra con battiscopa), altrimenti `null`. `ends{top, bottom}` ripete i due ponti chiusi; `rungs{pitch: 0,2857, per_deck: 14, rail_gap: 0,44, z0: -0,13}`: il piolo k di un ponte sta a `z del ponte + z0 + k × pitch` (il primo 13 cm sotto il pavimento), 14 pioli ogni 4 m, quindi lo schema è lo stesso su ogni ponte e la scala corre senza salti attraverso i solai; i montanti distano 0,44 m. Il piano e il modulo leggono le stesse costanti (`ship_catalog.TRUNK_*`): una cella che cambiasse misura sposterebbe anche questi punti.
**Gallerie dello scafo** (`ship_design.GALLERIES`, tono V, 36 m): lungo lo scafo dei ponti 5–11, un corridoio di servizio con **camere stagne** (con armadietti delle tute), **baie di capsule di salvataggio** e le stanze di servizio da 8 × 4 m sul lato esterno; il braccio di un tubo sbocca nella galleria (arco nel grafo). Ogni torre delle scale ha dietro la sua **stazione del damage control** (8 × 8 m: armadietto, manichette, respiratori, puntelli, il piano della sezione).

I portelli: ogni cambio di tono e ogni confine di sezione ha il suo (cancello, portello stagno: i `blast` del grafo). **Segnaletica e ordinate** (§9) dicono in che ponte, sezione e frame si è.

## 7. Gli ascensori: la rete e il contratto con ASCENSORI

**Trentaquattro pozzi** (`vertical[]`, 291 approdi): 29 turboascensori, 2 di plancia, 2 di servizio (banche Engineering e Flight), 1 merci (Flight). Una banca è una **lobby 8 × 16 m** (due porte, panche, piante, linee di guida, un elenco del ponte sulla parete) tra la Spine e il passaggio oltre, o in una corsia esterna (una porta sola). I pozzi attraversano più ponti: l'asse è sempre lo stesso, il pavimento e il soffitto della lobby non hanno soletta dentro il pozzo.

| Banca | x | Ponti | Perché lì |
|---|---|---|---|
| bridge ×2 | −24,3 | 1–12 e 1–9 | sotto la plancia: il Capitano scende da qui |
| f Flight | +52 | 4–12 | il bivio verso prua: Flight Deck, baia d'assalto, volo, chiglia di prua (servizio + merci) |
| c Concourse | −80 | 2–9 | il centro dell'equipaggio: Concourse e Mess, CIC sopra, Medbay sotto |
| d Berthing | −204 | 2–9 | il Crew Berthing, gli ufficiali, il complesso medico |
| e Engineering | −308 | 2–12 | l'ingresso di Main Engineering, impianti, officine (con un ascensore di servizio) |
| g Aft / h Stern | −404 / −444 | 2–12 / 4–12 | gli spazi di poppa, le macchine, la chiglia |
| m1 m2 n1 n2 k1 k2 r1 r2 s1 s2 | −160, −16, −240, −364, −500 | 4/6–12 | **ascensori laterali** nelle corsie esterne, un paio per lato in ogni zona: da dritta partono dal Ponte 6 (la corsia di dritta del 5 è il tunnel) |

**Distanza a piedi dall'ascensore più vicino** (da ogni punto di corridoio del ponte, misurata sul grafo, in m): mediana / 90° percentile / massimo — Ponte 2: 48 / 84 / 116; 3: 48 / 88 / 132; 4: 40 / 80 / 124; 5: 40 / 92 / 144; 6: 32 / 56 / 88; 7: 32 / 56 / 84; 8: 32 / 60 / 88; 9: 32 / 60 / 88; 10: 40 / 68 / 92; 11: 40 / 68 / 92; 12 (la chiglia): 44 / 100 / 196 (la punta di prua dei serbatoi).
(NAVE-2 aveva un ascensore finto in tutto.) I punti lontani sono le estremità delle braccia e la corsia di dritta dei Ponti 2–4, dove un pozzo continuo passerebbe sul tunnel del 5.

**Il contratto `vertical[]` (versione 2).** Per ogni pozzo: `id, kind (turbolift | bridge | service | cargo), name, shaft{x, y, w, d, z[fondo, cima]}, car{w, d, h}, landings[], speed, accel, decks`. Un approdo: `deck, z, door[x, y, z], yaw (da dentro la lobby verso il pozzo), lobby (il compartimento), node (il nodo del grafo dove si aspetta)`.
**Il nodo di attesa sta nel grafo e a 1,5 m davanti alla porta d'approdo (0 cm di scarto: ASCENSORI lo cerca per posizione entro 90 cm; `ship_checks` lo verifica per ogni approdo)**. Le porte d'approdo sono nel piano con il flag `lift: <id del pozzo>`: **sono di ASCENSORI** (`UAstraLiftSubsystem` costruisce vetture, ante, pannelli e voce dal piano all'inizio del gioco); `build_ship_interior.py` le salta.
**Un solo piano porta per ogni approdo**: il punto `door` sta sulla **faccia della parete del pozzo che guarda la lobby** (per i pozzi di una banca normale e per quelli del ponte: bridge `x + 1,5` su ogni ponte, Deck 1 compreso, con il nodo d'attesa a `x + 3,0`). L'`AAstraLiftLanding` tollera un punto fino a 0,6 m dentro il pozzo, ma il piano non ne ha bisogno.
Gli archi `lift` collegano le vetture di due fermate (costo = tempo di corsa + porte: 6 m/s, 2 m/s², 4 s); la rete è completa per pozzo (ogni fermata raggiunge ogni altra con una corsa). **Chi disegna cosa a un approdo**: il kit (`LiftBank`, `LiftBankO`, `LiftBankB` e, sul Ponte 1, `LiftHousingBridge`) fa la lobby, le pareti del pozzo (0,2 m, con il vano 1,6 × 2,4 sulla porta), **la cornice della porta** (stipiti e architrave di metallo spazzolato, a 12 cm dalla parete, con le strisce luminose), l'indicatore con le frecce su/giù, il pannello di chiamata di fianco e la soglia, il pittogramma tra le due porte e le linee di guida sul pavimento; le ante, la fascia, il cartello del ponte e le luci dello stipite sono dell'`AAstraLiftLanding`: nel gioco i due si leggono come una porta sola (provato dal lead sulle banche), e `lift_bank_b` e l'alloggiamento del Ponte 1 hanno la stessa cornice e lo stesso pannello delle altre, con i punti porta sulla stessa faccia (`_frame_door`, una funzione sola per ogni parete).

**Il Ponte 1: l'alloggiamento dei due ascensori del ponte.** Il corridoio di babordo del Ponte 1 (vecchio, BRG3) finiva in un tappo (`CorrPort_EndCap`) con un finto ascensore (ante statiche e il cartello LIFT, `build_hangar.py`); dietro c'è il **blocco** `SM_SHIP_ASTRA_AquilaBridgeBlock` (`quarters.py`): un guscio chiuso di sezione smussata (x −25,8..−21,0, y −8,2..−1,0; le facce verticali arrivano a z 3,15, il tetto è a 3,5), con facce a un solo lato: da dentro non si vede e un pozzo ci stava all'aperto; il suo piedistallo ha una faccia in su a z −0,3, un pavimento 0,3 m sotto il Ponte 1 dentro i pozzi. Ora l'interno c'è: **`SM_SHIP_LiftHousingBridge`** (`ship_rooms_lifts.lift_housing_bridge`, 2 × 6,96 × 2,9 m, piazzata a imbardata 180 in (−20,8; −1,22) da `ship_deck1.build_housing`): la parete di prua dove stava il tappo (x −20,8..−21,0) con **la bocca del corridoio** (3,2 × 2,5: la sezione verticale del corridoio, sopra un architrave), il **vestibolo** (1,7 m libero × 6,7, panca, pianta, due luminarie, una luce e due posti in piedi nel piano), la parete dei pozzi (x −22,8..−23,0) con le due porte (cornice, indicatore, pannello di chiamata: come le banche) e i **due tubi** (3,0 fuori, 2,6 dentro) fino a un **tetto chiuso**, nessuna soletta dentro i tubi. Sta dentro il blocco: a 2 cm dai suoi piani, alta al più 3,12 (il piano dei pozzi dice 3,7: il tetto del blocco è a 3,5); **l'unica parte che ne esce** è la parete di prua (0,2 m davanti alla faccia di prua del blocco, a x −21,0) per y −8,2..−5,7 e −2,1..−1,0, dove il tappo non c'era (anteprime: `docs/progressi/nave/room_lift_housing_bridge_lifts.jpg`, `room_lift_housing_bridge_corner_a.jpg`).
`build_ship_interior.py` (`OPEN_BRIDGE_LIFT = True`) toglie il vecchio: **il tappo, le ante statiche e il cartello** (cartella `Hangar/Lift`, `Lift_Bridge_*`) e la **collisione del blocco** (`Aquila_BridgeBlock`: è solo un esterno, e il pavimento del suo piedistallo tratteneva chi stava in vettura quando partiva); il log elenca gli altri attori che stanno nell'impronta dei pozzi al livello del pavimento. Va lanciato dopo `build_bridge_v3.py`, `build_hangar.py` e `build_quarters.py`, che li rimetterebbero.

## 8. La navetta della Spine

BIBBIA §6: "il corridoio centrale lungo la nave con la navetta interna". Corre sul **Ponte 5** per tutta la lunghezza della nave, da prua a poppa, in un **tunnel** (tono T, 3,5 m di larghezza, 3,25 di altezza) lungo la mezzeria della corsia esterna di dritta (**y = 30**), tra **otto sale di fermata** (A–H, una per sezione, compresa la F), ciascuna una stanza di quella corsia, 24 × 16 m: la banchina lungo la parete dello Starboard Passage (6,4 m, con striscia tattile, linea gialla, panche, tabelloni, colonne), il letto del binario dietro (due rotaie, traversine, linea di guida), le bocche del tunnel nelle testate; i capolinea (A a prua, H a poppa) hanno la bocca da un lato e **i respingenti** contro la parete chiusa.
Perché la corsia esterna di dritta: la Spine del Ponte 5 è spezzata dalle sale delle stanze esistenti (Mess, Berths, Medbay, Main Engineering: tronchi da 24 a 304 m) e serve agli ascensori; lo Starboard Passage è continuo, e la corsia oltre è libera: **l'unica linea retta attraverso la nave**. Il prezzo: la banca Mess di dritta (m1) parte dal Ponte 6 e le braccia di Jefferies di dritta sul 5 sono solo la loro cella.
**Il piano**: un nodo `platform` per sala, archi `shuttle` tra sale consecutive (costo = la corsa in secondi più la sosta; larghezza 0,05 m: dentro il tunnel passa solo un passeggero, e il modello dei danni legge un arco di tipo ignoto come un'apertura di quella larghezza), e il record `transit[]` (versione 2): `id: spine_shuttle, deck, path[], stops[{id, section, x, door[x, y, z], yaw, room, node}], car{mesh: "SpineCar", length: 14}, speed, accel, dwell, gauge`.
**La vettura non è nelle sale** (ASCENSORI la fa correre): la mesh `SM_SHIP_SpineCar` (14 m, porte sul lato −y = quello della banchina, naso +x) è un pezzo a parte.
**Le bocche del tunnel sono buchi veri**: ogni parete di testata di una sala (3,5 × 3,25, l'asse a y = 30) è tagliata, per le fermate B–G dai due lati e per i capolinea dal lato aperto (A a poppa, H a prua): la vettura si sposta senza spazzare, ma chi è dentro no, e un muro lo avrebbe tolto di sotto ai piedi. La cornice (stipiti con strisce di pericolo, lampade) resta, il vetro scuro del vecchio finto ingresso no. **L'ingombro della vettura** (14 × 2,8 × 2,9, il pavimento a 0,16 m, sull'asse) è libero: il kit lo controlla (`ship_kit.car_clearance`: un vertice dentro, o un triangolo che attraversa le facce, è un problema) sulle celle `T_Straight_A/B`, sul cancello `T_Bulkhead` e sulle sale; ha trovato e fatto correggere tre cose: la **banchina di servizio** del tunnel (alzata 0,22, ora 0,11: sotto il pavimento della vettura), il **condotto e i pendini** sul soffitto (ora non più bassi di 3,08 m: il tetto della vettura è a 3,06) e l'**apertura del cancello** di sezione (3,0 → 3,15).

## 9. La segnaletica (wayfinding)

Una nave di 744 m si legge dai cartelli. Quattro tipi, tutti istanze del guscio del ponte (nessun attore); i cartelli di sezione di NAVE-2 (sui portelli, a due facce) restano.

- **Cartelli a lama** (`SM_SHIP_WayBlade_<righe>` + `SM_SHIP_WayRow_<meta><direzione>`): appesi al soffitto di traverso alla Spine e ai Passage, **a coppie schiena a schiena** (una faccia per verso di marcia), agli incroci, ai cancelli delle lobby e al più ogni 48 m. Una riga è un pittogramma, un nome (TURBOLIFTS, STAIRS, MEDBAY, LIFEPODS, e per ponte BRIDGE, MESS HALL, ENGINEERING, FLIGHT DECK, SPINE SHUTTLE, BRIG) e una freccia **calcolata, non disegnata a mano**: per ogni cartello e ogni meta si cerca sul grafo il cammino più corto (Dijkstra dalle mete all'indietro) e dai primi 5 m si legge se la meta sta **avanti, a sinistra o a destra** di chi guarda (quel che sta dietro è sull'altra faccia). Al più tre righe, nell'ordine di importanza del ponte.
- **Ordinate** (`SM_SHIP_Frame_<n>`: "FR 134", una per 4 m da prua, la 0 a x = +216): sotto i cartelli di sezione dei portelli e nelle lobby.
- **Elenchi dei ponti** (`SM_SHIP_Directory_<ponte>`): lo schermo con i luoghi principali per sezione, sulla parete di ogni lobby di ascensori sopra la panca ("YOU ARE HERE · FOLLOW THE BLADE SIGNS").
- **Targhe delle stanze** (`SM_SHIP_Plate_*`) sopra ogni porta, come prima.
Numeri: 969 facce in 508 appese, 504 ordinate, 134 elenchi; **29 mesh** dicono tutto (3 cornici e 26 righe), più 53 ordinate e 11 elenchi.

## 10. Il kit (`art/blender/ship_*.py`)

Linguaggio della plancia v3: composito scuro in cornici di metallo spazzolato, nervature con linee di luce, lampade a palette (`MI_BRG3_Lamps*`: la cella dice il colore), un solo slot per tutte le etichette (`MI_SHIP_Labels`, atlante `T_SHIP_Labels`, 4096 × 6144: 425 tile). Ogni mesh è chiusa alla luce, Nanite (quelle con un vetro restano classiche),
collisione complessa come semplice, UV a 1 m e per cella per lampade e etichette. Budget (dopo ARTE-INTERNI, §10.4): **446 mesh, 6,61 M triangoli in tutto, la più pesante 149 k** (i triangoli in Nanite non sono il costo; il costo è la memoria: FBX su disco, non in git).
Come "più futuro e meno ufficio" (NAVE-3): corridoi con strisce di luce, pannelli tecnici, condotti, schermi e segnaletica; **l'atrio dell'Aquila non è più una sala vuota** (il Mess Concourse e l'atrio del Berthing sono stati rifatti, §10.2).

| Gruppo | Mesh | Note |
|---|---|---|
| Moduli di corridoio (5 toni) | `SM_SHIP_<S|P|K|V|T>_` `Straight_A/B/C, Door_*, Gate_*, Bulkhead, T_L, T_R, X, End` + `Trunk*` (celle dei tubi) | **V**: corridoio di servizio, 2,1 × 2,7 m, luce ambra calda, tubi in vista, nervature, armadietti (`ship_corridor2.py`); **T**: tunnel della navetta con cancello di paratia e respingenti; K con la cella del tubo (alcova con la scala a pioli) |
| Salute e cura | Dentist, Morgue, Counselling (`ship_rooms_care.py`); Surgery, Quarantine, Pharmacy ripresi con lo stesso guscio (`ship_rooms_med.clinic_style`) | due poltrone da dentista con unità e lampada; parete di cassetti frigoriferi e tavolo autoptico; sala di ascolto con divano, scrivania e un angolo per il cappellano. **Il complesso medico non è più un ospedale del 2020**: pavimento scuro a piastre, pareti avorio, un binario spazzolato a 1,2 m, nervature e cornice di luce verde acqua (il colore del reparto, STILE.md); il Medbay esistente (non mio) è rimasto bianco |
| Sicurezza | Brig (5 celle con sbarre, cuccetta, WC, sgabello e lampada di stato; scrivania di guardia rialzata), SecurityOffice (`ship_rooms_care.py`) | celle 2 e 4 occupate |
| Impianti | AirPlant, WaterPlant, WastePlant, ComputerCore, AuxReactor, DcCentral (`ship_rooms_plants.py`) | scrubber di CO₂ e elettrolizzatori; serbatoi, filtri, pompe; vasi a pressione e compattatore; file di rack con corridoi freddi; un piccolo reattore su zoccolo; il tavolo del piano dei danni con le console lungo le pareti |
| Vita di bordo | Barber, Bar, Chapel, Shop, SimBay, Berthing (sala cuccette da 28), Suites, SingleCabins, DroneBay (`ship_rooms_life.py`) | **sedili veri sotto ogni posto**; le cuccette a due livelli con armadietti |
| Scafo | Airlock, PodBay (con la capsula ovoidale `lifepod` su culla), SuitLocker, DcStation (`ship_rooms_hull.py`) | camera stagne con portello rotondo, armadietti delle tute, capsula da 20 posti con oblò e portello |
| Ascensori | LiftBank, LiftBankO, LiftBankB, LiftHousingBridge (`ship_rooms_lifts.py`) | lobby con le porte d'approdo (vano 1,6 × 2,4, cornice, indicatore su/giù, pannello di chiamata, soglia), il pittogramma tra le porte, le linee di guida; **i pozzi con pareti da 0,2 m**; sul Ponte 1 l'interno del blocco dietro il corridoio di babordo (§7); ante e cartello del ponte sono dell'`AAstraLiftLanding` |
| Navetta | ShuttleStop, ShuttleStopBow, ShuttleStopStern (`ship_rooms_transit.py`); SpineCar (`ship_craft.py`) | 24 × 16: banchina, binari, bocche del tunnel, respingenti; la vettura da 14 m (bianca con fascia blu, porte aperte sul lato banchina) è una mesh a parte |
| Segnaletica | WayBlade_1..3, WayRow_<meta><freccia> (26), Frame_<n>, Directory_<ponte> (`ship_signs.py`) | §9 |
| Snodi | Concourse, BerthLobby (rifatti), StairTower(+Top, Bottom, 53, Cap), LadderTrunk | §10.2 |
| Il resto | tutte le stanze di NAVE-2 (laboratori, officine, armi, volo, chiglia, social, servizi: `ship_rooms_*.py`) | guscio v2, temi, materiali e luci nuovi per tutte; arredi e dettagli rifatti per le sale comuni, gli alloggi, i giardini, i locali medici e quelli umidi (§10.4) |

L'arredo vive in `ship_furniture.py` … `ship_furniture9.py` (nove biblioteche; la nuova: poltrona del dentista, parete dell'obitorio, cella, banco di guardia, panche delle cappelle, sedia del barbiere, simulatore, capsula di salvataggio, scrubber, elettrolizzatore, reattore ausiliario, chiosco…); ogni funzione costruisce un pezzo (origine a terra, fronte +x) e le stanze lo piazzano con `place(b, x, y, yaw, funzione, …)`.
Gruppi di una mesh (`SParts`): `body` (smussato), `fine`, `soft` (senza smusso: cuscini, libri, piante, **le doghe di una parete**), `emit` (lampade e etichette). Limiti controllati a ogni esportazione: 150 k triangoli a mesh, altezza ≤ 3,7 (struttura compresa ≤ 4,0), ingombro dentro la pianta.

### 10.1 Controlli del kit (a ogni esportazione)

Budget di triangoli, slot noti, UV finite, misure contro la scheda (`ship_spec.py`); **prove a raggi lungo gli archi del grafo** di ogni ponte costruito (altezze 0,35 / 1,0 / 1,75 m, contro le mesh piazzate) e **controllo dei posti** (`check_spots`): chi sta in piedi ha una colonna libera di 22 cm dal ginocchio alla testa, chi siede un torso libero di 12 cm sopra il sedile **e un sedile sotto i fianchi (la prima superficie sotto di lui è a 30–80 cm dal pavimento)**, e sotto c'è il pavimento;
un posto sul mobilio esce con il punto libero più vicino da scrivere nella scheda. Risultato sul piano finale: **12 ponti, ~25 000 raggi di corridoio e di porta, 0 bloccati; ~4 100 posti controllati, 0 sul mobilio** (dentro le stanze i raggi hub → posto sono topologia: ne toccano l'arredo circa un quarto, atteso).
Le anteprime sono in `docs/progressi/nave/` (JPG sotto i 250 KB).

### 10.2 Il Mess Concourse e l'atrio del Berthing (la critica del lead: "troppo grande, buio, spoglio")

Il vecchio Concourse (17,7 × 36 × 3,7 m) era un salone vuoto con un'aiuola al centro e due pareti scure. Ora è **una strada, non una sala**: un'**aiuola-giardino con un albero** sotto un anello di luce tra il portale della Mess Hall e la Spine; **da una parte un caffè** (bancone con retrobanco e macchina del caffè, quattro sgabelli, tavoli con sedie, un divano su un tappeto rosso) e **dall'altra il negozio di bordo** (banco con cassa, scaffali, un espositore e una gruccia di abiti, tappeto blu), ciascuno **sotto un controsoffitto basso di luce calda su quattro colonnine** che abbassa la scala e dà un bordo alla zona;
la parete di poppa (la porta della Mess Hall) **rivestita di doghe di legno retroilluminate**, la parete di prua con **grandi schermi come finestre sulle stelle**; pareti e soffitto chiari su pavimento scuro, un campo di 36 pannelli luminosi, linee di guida sul pavimento, la stele dell'elenco accanto al portale, otto vasi alle estremità. I finti ascensori della vecchia parete di poppa sono spariti (gli ascensori sono le lobby del §7).
23 posti nel Concourse (prima 8), 7 lampade nei dati (prima 3). **L'atrio del Berthing** (14,6 × 36) ha le stesse doghe attorno alla porta del Crew Berthing, un tappeto-corridoio fino allo schermo del ruolino con tre anelli di luce sospesi, due angoli di salotto sotto un controsoffitto caldo.

### 10.3 Le stanze di NAVE-2 (ancora valide)

Misure interne (lunghezza × profondità × altezza, m); ogni stanza ha il suo arredo vero, i suoi posti (`stations`) e le sue lampade nella scheda `ship_spec.py`.

| Ponte | Stanza (prefab) | Misure | Cosa c'è dentro |
|---|---|---|---|
| 2 | `cic` — Combat Information Centre | 32 × 16 × 3,6 | tre grandi pannelli sulla parete di fondo (piano tattico, carta stellare, stato della nave), tavolo del piano con anello di luce, due blocchi di sei console, rack delle comunicazioni, pannello del damage control |
| 2 | `briefing`, `comms_center`, `offices`, `records` | 16 × 16, 24 × 16, 16 × 16, 12 × 16 | tavolo lungo con tre schermi e lo stemma; tre file di postazioni operatore con la parete delle reti di flotta; uffici aperti con partizioni e plotter; archivio con scaffali mobili |
| 2 | `vls_magazine`, `point_defense`, `barbette`, `sensor_room` | 24 × 16, 16 × 16, 24 × 16, 16 × 16 | due blocchi di celle di lancio verticali con carroponte e missile sull'imbracatura; quattro postazioni di tiro davanti alle camere; la base di una torretta railgun (trunk corazzato, culatta, colonne di condensatori); console e globo sensori |
| 3 | `staterooms` — Officers' Staterooms | 20 × 16 × 3,2 | otto cabine da ufficiale attorno a un atrio (letto sotto un oblò-schermo, scrivania, armadio, lavabo con specchio illuminato) |
| 3 | `wardroom`, `gym` | 24 × 16 × 3,6 / 3,7 | due tavoli da dieci posti, salotto con bar e acquario; cinque tapis roulant, panche con rastrelliere, sacco, specchi, armadietti |
| 5 | `transporter` — Transporter Room | 24 × 16 × 3,8 | sei pedane su una pedana rialzata sotto l'anello di emettitori, console, buffer di schema, cabina di decontaminazione, pedana di carico (BIBBIA §3: 8 s a ciclo) |
| 5 | `lab_astro`, `lab_bio`, `lab_phys`, `sensor_archive`, `sensor_room` | 24 × 16, 24 × 16, 24 × 16, 16 × 16, 16 × 16 | Astrometrics (stanza buia sotto le stelle: trittico di carte, tavolo olografico, sei console); acquari, banchi di crescita, freezer, microscopi; un acceleratore su telaio d'acciaio con rivelatore ad anello e cabina schermata; scaffali dati con la volta fredda |
| 7 | `power_control`, `switchgear`, `capacitors` | 24 × 16 × 3,6 / 3,7 | il pannello sinottico della distribuzione con due file di console; due file di quadri ad alta tensione su tappeti isolanti con gabbia di isolamento; due banchi di condensatori su zoccoli a strisce con sbarre |
| 8 | `shuttle_bay` — Assault-Shuttle Bay | 32 × 16 × 3,7 | **due Kestrel** (11,7 m, rampe giù, collare di perforazione) davanti ai portali di lancio, banco, gabbia dei razzi, trattore, carrelli del carburante e della schiuma |
| 8 | `barracks`, `kit_room`, `firing_range` | 24 × 16, 16 × 16, 40 × 16 | otto cuccette doppie con armadi e bauli, tavolo lungo, angolo palestra; sei vani armatura e due file di armadietti; **sei corsie da 33 m** con baffle e sagome a 21 e 31 m, cabine di tiro, recinto con due cancelli |
| 9 | `flight_ops`, `pilot_ready`, `aircraft_shop` | 24 × 16, 24 × 16, 28 × 16 | la sala di controllo del volo (la "control booth" del canon, Air Boss e CAG): tre pannelli di stato, due file di console, tavolo del piano; poltrone in due blocchi con podio e armadietti delle tute; il muso di un caccia sul carrello sotto il carroponte, un turbofan, un'ala sull'attrezzatura |
| 9–10 | `magazine`, `cargo_hold` | 24 × 16, 32 × 16 | due file di rack di missili con l'argano dei munizionamenti e gli irrigatori; container impilati, pallet, carrello elevatore, portello del montacarichi |
| 11 | `fab_shop`, `repair_bay` | 28 × 16, 32 × 16 | tre stampanti a metallo, forno di fusione, cella robotica con nastro; piastre di scafo, due simulatori, tavolo con il taglio al plasma, due celle di saldatura, tute EVA e puntelli |
| 12 | `tank`, `reaction_mass`, `crawlway` | 32 × 16, 40 × 16, 16 × 16 × 3,0 | quattro serbatoi orizzontali di 11 m con il manifold; quattro vasi sferici a pressione con l'anello di tubi; l'incrocio dei cunicoli con tre tubi verticali, scala e botola |
| 5 | `radiator_pumps`, `machinery`, `machinery_b` | 24 × 16 | collettori e pompe del refrigerante (la postazione di controllo ha ora la sedia dal lato dello schermo); aria e acqua; aria compressa |

**Mappa dei file** (`art/blender/`):

| File | Cosa contiene |
|---|---|
| `ship_plan.py`, `ship_plan_gen.py`, `ship_checks.py` | misure dei ponti e dell'inviluppo; il generatore del piano (e la copia sottile per il gioco); i controlli del piano |
| `ship_layout.py`, `ship_design.py`, `ship_decks.py`, `ship_design_decks.py`, `ship_design_decks2.py` | **il motore** (Builder, Passage, Deck, corsie, porte, collegamenti, gallerie e braccia); **le strutture fisse e le gallerie**; la geometria dei passaggi (`ship_decks.py`: dove passano e come toccano le stanze esistenti); **i programmi dei ponti 2–7 e 8–12** |
| `ship_vertical.py`, `ship_design_shuttle.py`, `ship_wayfinding.py` | **la rete verticale** (pozzi, approdi, scale, tubi); **la navetta**; **la segnaletica** calcolata sul grafo |
| `ship_spec.py`, `ship_spec3.py` | la scheda di ogni stanza: misure, porte, **posti**, **lampade** (il piano e le mesh leggono gli stessi numeri); `ship_spec3` le stanze di NAVE-3 |
| `ship_catalog.py`, `ship_corridor.py`, `ship_corridor2.py`, `ship_walls.py`, `ship_signs.py` | i toni S P K V T e le misure; i moduli di corridoio (K e le celle dei tubi in `ship_corridor`, V e T in `ship_corridor2`); i pannelli di parete; targhe, segnali, cartelli |
| `ship_rooms.py` (conchiglie e `place`), `ship_rooms_*.py` | le stanze per tema; di NAVE-3: `_care`, `_plants`, `_life`, `_hull`, `_lifts`, `_transit` (rifatto), `_hub` (Concourse e Berthing) |
| `ship_furniture.py` … `ship_furniture9.py`, `ship_craft.py`, `ship_lib.py` | l'arredo; i velivoli (Kestrel, vettura della navetta); i materiali, la palette, le etichette, `SParts` |
| `ship_shell.py`, `ship_themes.py`, `ship_mk.py`, `ship_decor.py` (ARTE-INTERNI) | il guscio v2; i temi per tipo di stanza; le forme (scatola arrotondata, cuscino, tornio, foglia, rilievo); i tappeti, i quadri e il resto di ciò che fa vivere una stanza |
| `ship_furn2.py`, `ship_furn3.py`, `ship_furn4.py`, `ship_cabin.py`, `ship_wet.py`, `ship_plants.py`, `ship_assets.py` | arredi di seconda e terza generazione (le funzioni vecchie delegano); palestra, cappella, sala giochi, uffici; attrezzatura medica; cabine; bagni e lavanderie; le piante; i modelli Poly Haven |
| `ship_mess.py`, `ship_berths.py`, `ship_medbay.py`, `ship_engineering.py`, `ship_hangar.py` | le cinque stanze M1 nel linguaggio del kit (i generatori vecchi li chiamano; `*_v1` restano) |
| `data/ship/room_materials.json`, `tools/ue_scripts/ship_room_materials.py` | la tabella dei 54 materiali delle stanze, per le anteprime e per Unreal |
| `ship_kit.py`, `ship_kit_preview.py`, `ship_preview.py`, `ship_budget.py` | il generatore del kit e dei controlli; le anteprime (`rooms`, `modules`, `modules3`, `car`, `signs`, `d1`, `d4`, `d6`, con i posti nella vista `plan`); il budget per ponte |

### 10.4 L'arte degli interni (ARTE-INTERNI)

Dopo il giro del 2/10 le stanze erano «un greybox ammobiliato» sotto corridoi che reggevano ([brief/ARTE-INTERNI.md](brief/ARTE-INTERNI.md)). Questo lavoro porta **tutti i tipi di stanza al linguaggio dei corridoi** (guscio, luce, materiali veri, piante vere) e **rifà da zero**, nell'ordine in cui il Capitano le vede: la mensa e la cucina, gli alloggi (cabine, suite, camerate, cuccette), le sale comuni (wardroom, lounge, biblioteca, cappella, palestra, sala giochi, osservatorio), i giardini e l'idroponica, l'infermeria e i locali medici, i bagni e le lavanderie; e **le cinque stanze dell'era M1** (Mess Hall, Crew Berthing, Medbay, Main Engineering, Flight Deck), sempre allo stesso posto, con le stesse porte e gli stessi posti. Anteprime guardate stanza per stanza in `docs/progressi/interni_2026-10-03/`.

**Gli strati** (cosa c'è di nuovo e dove ritoccarlo):

| Strato | File | Cosa |
|---|---|---|
| Guscio v2 | `ship_shell.py`, `ship_rooms.Style` | pavimento con bordo e intarsio; pareti a campate con pilastri e fessura di luce sui frame (`bay`, `bay_edges`: dove cadono i pilastri, parete per parete) e un trattamento per campata (pannelli, tessuto, doghe di legno, lamiera forata, piastrelle); soffitti veri: strisce luminose tra le travi, gola attorno a un soffitto rialzato, griglia acustica, struttura a vista |
| Temi | `ship_themes.py` (`THEME_TABLE`) | l'aspetto per tipo di stanza, come lo vuole STILE.md: *living* (moquette di lana, legno, intonaco, gola calda 3200 K), *mess*, *crew*, *medical* (piastrelle bianche, verde acqua, 5200 K), *lab*, *command* (blu-grigio), *security* (canna di fucile e rosso), *flight*, *tech* (lamiera mandorlata, ambra, struttura a vista), *store*. **Per cambiare una stanza si cambia la sua riga della tabella**, non il generatore |
| Materiali | `data/ship/room_materials.json` → `ship_lib.py` (anteprime) e `tools/ue_scripts/ship_room_materials.py` (Unreal) | **54 istanze di `M_ASTRA_Hard`** (tinta, scala delle UV, rugosità, normale) da 29 set di texture; una tabella sola per Blender e per Unreal; i set della plancia (`Brushed`, `PanelPaint`, `Cotton`, `Linen`, `WoodDark`) restano quelli del progetto |
| Texture | `tools/art/interior_textures.py`, `tools/art/polyhaven_models.py` | 17 set 1K da ambientCG (CC0: moquette di lana, legni, piastrelle bianche piccole/grandi/esagonali, terrazzo, lamiera mandorlata, piastre ottagonali, intonaco, pelle liscia e capitonné, sughero, tessuto grosso, prato, muschio, terra), 9 set delle piante Poly Haven (CC0), 3 procedurali (pannello forato, atlante delle foglie, **tavolozza di 64 colori**: libri, stoviglie, cibo, giocattoli, tutto ciò che è piccolo e colorato ha **un solo slot**). Fonti e licenze in `licenze.csv` |
| Piante | `ship_assets.py`, `ship_plants.py` | 7 modelli Poly Haven (felce, calatea, antúrio, albero della fortuna, ficus, singonio, haworthia: 12 varianti, più 4 a un quinto dei triangoli per le aiuole) decimati e versati nella mesh della stanza; piante procedurali con **foglie vere** (`ship_mk.leaf`: sansevieria, palma, lattughe, erbe, pomodori, rampicanti, ciuffi d'erba, fiori, parete verde); i **giardini** hanno aiuole di muschio e prato con rilievi (`ship_mk.terrain`), un albero della fortuna per aiuola, sassi di fiume, rampicanti dalla pergola e tre pareti verdi |
| Arredi | `ship_mk.py` (forme: scatola arrotondata, cuscino, tornio, foglia, rilievo), `ship_furn2.py` (sedute, tavoli, scaffali, lampade, cucina), `ship_furn3.py` (palestra con ring e pedana, acquario, modellino della nave, cappella, sala giochi, sedia e postazione d'ufficio), `ship_furn4.py` (attrezzatura medica), `ship_cabin.py` (cabine con finestra sullo spazio: stelle e il bordo di Aurelia, boiserie, lampada, comodino, scrivania), `ship_wet.py` (bagni, docce, lavanderie), `ship_decor.py` (tappeti, quadri, bacheche, tazze, libri), `ship_themes.py` | gli arredi vecchi (`ship_furniture*.py`) **delegano** ai nuovi con gli stessi ingombri e lo stesso fronte, quindi le stanze e i posti non si spostano |
| Luce | `ship_spec.retune_lights()` (e `LIGHT_LEVEL`) | le lampade del piano (`lights[]`) hanno una **densità per tipo di stanza** (lumen del piano per m²: cucina 105, idroponica 120, lounge e biblioteca 80, cabine 70, cappella 58, osservatorio 45, medico 100–105, officine 85–95, depositi 70…) e una temperatura (cucina 4800 K, lounge 3300, cappella 2900, medico 5400…): prima una stanza aveva 10–45 contro i ~106 di un corridoio. **`LIGHT_LEVEL` (1.0) in `ship_spec.py` scala tutto**: cambiarlo e rigenerare il piano. Ogni cabina ha la sua lampada. In più c'è luce d'architettura che non costa luci dinamiche: strisce, gole, zoccoli di luce per reparto, schermi |

**Le cinque stanze M1** (`ship_mess.py`, `ship_berths.py`, `ship_medbay.py`, `ship_engineering.py`, `ship_hangar.py`; i vecchi generatori `messhall.py`, `berths.py`, `medbay.py`, `engineering.py`, `hangar.py` li chiamano, le versioni vecchie restano come `*_v1`; frame, porte e posti invariati). Le luci di queste stanze sono **attori** (non lampade del piano, quindi senza il guadagno `astra.lamps.gain`) e si regolano in `tools/ue_scripts/build_*.py`:

| Stanza | Cosa | Triangoli prima → dopo | Luci |
|---|---|---|---|
| Mess Hall | pavimento di terrazzo con corsia ardesia, pareti di noce e intonaco a campate con pilastri luminosi, soffitto a strisce tra le travi sui frame della nave, tavoli di rovere con bordo d'acciaio su piede a colonna e panche imbottite, banco di servizio con il cibo, cucina visibile oltre il passaplatti (forni, cappa, pentole appese, scaffali), parete delle erbe, stendardi, piante | 54 k → 92 k (22 → 37 slot) | quattro file, `LIGHT_GAIN = 5` (la sala era quasi nera: 100 lm per tutto il locale) |
| Crew Berthing | campate con pilastri sui frame dei portelli, corsia chiara, travi sui frame, vassoi e tubo sopra la corsia, salottino con tavolo, sgabelli, mensola e angolo caffè, luci calde smorzate e luci rosse di notte | sala 22 k → 16 k (le cuccette `SM_BERTH_Stack_*` sono quelle di prima) | corsia da 14 000 a 26 000 lm |
| Medbay | corsia a campate con pilastri dove si dividono i letti, tende plissettate su binari, comodino e sedia per ogni letto, banco infermieri, parete dei rifornimenti, console centrale, **sala operatoria** (tavolo, lampade gemelle, anestesia, scanner, carrello d'emergenza, armadi sterili) | 117 k → 82 k (17 → 27 slot) | invariate |
| Main Engineering | campate rivestite, macchine sotto i ballatoi, anello di luce e console attorno alla fossa del reattore, carroponte, lampade a campana sui tralicci, condotti e passerelle: la mesh nuova `SM_ENG_Detail` sta sopra la sala vecchia | 80 k → 139 k | 12 luci alte da 24 000 lm e 8 di ballatoio da 14 000 lm (erano 12 da 5200 lm: la sala era nera) |
| Flight Deck | segni sul ponte, linee di sicurezza, contorno degli stalli, attrezzatura di terra lungo le pareti, campate rivestite, carroponte, fari dei tubi: la mesh nuova `SM_HGR_Detail` sta sopra il ponte | 40 k → 208 k (una mesh da 168 k: Nanite) | 18 fari da 60 000 lm (erano 26 000) e 10 fari di parete da 32 000 lm |

**Numeri** (kit completo, `ship_kit.py --stats`; "prima" = la base `c0a9c36`):

| | Prima | Dopo |
|---|---|---|
| mesh del kit / triangoli in tutto | 445 / 7,54 M | 446 / **6,61 M** (il calo viene dai corridoi alleggeriti di ARTE-PLANCIA-2, già in `main`; le sole stanze: 96 mesh e 5,95 M → 97 mesh e 5,91 M, media 61 k, la più pesante `hydro` 149 k, prima 138 k) |
| triangoli delle sole stanze di tutti i ponti se tutto fosse in vista (istanze) | 54,1 M | **48,6 M** (−10 %) |
| slot di materiale per mesh di stanza (media / massima) | 16 / 25 | **21 / 44** (`lounge`; poi `games` 39, `cabins` e `staterooms` 38, `wardroom` 36, `concourse` 35) |
| materiali diversi usati dalle stanze | 30 | 75 |
| texture nuove | — | 29 set a 1K ≈ **74 MB** se fossero tutti residenti (BC1/BC5, mip compresi); un ponte ne usa 8–28 (il Ponte 4, 28: 71 MB) |

Per ponte (triangoli delle sole stanze, mesh distinte, prima → dopo; il resto del kit è dei corridoi): Ponte 2 0,74 → 0,84 M · 3 0,73 → 1,06 · 4 1,52 → 1,99 · 5 1,72 → 1,43 · 6 1,40 → 1,71 · 7 1,54 → 1,32 · 8 1,97 → 1,68 · 9 1,46 → 1,38 · 10 0,67 → 0,50 · 11 0,95 → 0,76 · 12 0,34 → 0,29. **Gli slot salgono del 30 %** (da 4 067 a 5 284 sulle mesh distinte): è il prezzo dell'aspetto; con Nanite i materiali visibili insieme pesano meno degli slot, ma è la prima cosa da misurare nel `lounge` (44) e nei giardini.

**Prove** (offline, il lead prova il resto): kit completo con prove — 12 ponti, **0 rotte bloccate, 0 posti sul mobilio**, nessun problema di mesh; `ship_checks.py` **0 problemi, 0 avvisi**; `tools/life.py check` OK; `tools/lift.py check` OK; piano rigenerato (`LIGHT_LEVEL = 1.0`: 4 538 lampade, 120 in più per le cabine). Anteprime Eevee di ogni tipo di stanza dalla porta e da due angoli all'altezza degli occhi (1,68 m), con la vista dall'alto dei posti; prova senza Unreal di `ship_room_materials.py` contro un modulo `unreal` finto (54 istanze, 162 texture legate, i file delle texture presenti).

**Limiti e cose da guardare nel gioco**
- **Non provato in Unreal** (l'editor è del lead): l'importazione delle texture, le istanze, le mesh Nanite con 40 e più slot (`lounge`), la resa di prato, muschio e foglie a due facce sotto Lumen, le luci attori delle stanze M1 (hanno più luce di prima: se una stanza costa troppo, le manopole sono i numeri in `build_*.py`; se il locale è troppo chiaro o scuro, `LIGHT_LEVEL`).
- **Restavano com'erano** (generatori vecchi, non toccati; **rifatti il 4/10, §10.5**): le cuccette `SM_BERTH_Stack_*` (12–13 k triangoli l'una, 28 per sala: quasi tutti i ~390 k triangoli del Crew Berthing), `SM_MED_Bed` e le coperte dei pazienti, gli armadietti; i materiali `MI_MED_*`, `MI_MESS_*`, `MI_BERTH_*`, `MI_ENG_*` restano del progetto per ciò che non è stato rifatto (nelle anteprime offline escono bianchi).
- **Rifinite meno** (guscio v2, tema, materiali e luce nuovi, arredo dei generatori precedenti salvo dove detto; **dal 4/10 restano così solo le sale di comando, i laboratori, le officine, gli impianti, l'armeria, il poligono e le sale volo: §10.5**): CIC, briefing, comunicazioni, uffici (solo sedia e postazione), archivi, laboratori, officine, impianti, armeria, poligono, sale volo, brig, teletrasporto, hangar delle navette, capsule di salvataggio. Sono il prossimo lavoro naturale.
- Le sale grandi dell'era M1 non sono mesh del kit: il controllo dei 150 k triangoli per mesh non le riguarda (`SM_HGR_Detail` ne ha 168 k).

**Ricostruire** (nell'ordine; i primi due solo la prima volta e quando cambiano le texture): `interior_textures.py` e `polyhaven_models.py --all` (§1) → `ship_plan_gen.py` (il piano porta le luci e i posti nuovi) → `ship_kit.py` (FBX in `art/export/ship`) → `tools/ue.py pyfile tools/ue_scripts/build_ship_interior.py` (importa il kit, fa le istanze `MI_SHIP_*` da `room_materials.json`, rimette i ponti) → le cinque M1: generatore Blender e `build_<stanza>.py` (§1).

### 10.5 L'arte degli interni, secondo giro (ARTE-INTERNI-2, 4/10)

Riparte da ciò che il Capitano ha visto in gioco dopo il primo giro: il giardino con un «cielo aperto» (un piano blu-grigio), la biblioteca con un pavimento liscio sotto scaffali ricchi, le cabine con un muro subito davanti, e le stanze rimaste «meno rifinite». Anteprime guardate (altezza degli occhi, 1,68 m): `docs/progressi/interni_2026-10-04/`.

**Fatto**

| Cosa | Come |
|---|---|
| Giardini (`garden`) | soffitto vero (`ceiling="none"` più capriate ogni 4 m, cielo di pixel in cornici sopra il sentiero, che si legge come schermo, luci di crescita sopra le aiuole, irrigazione, condotto), tre lampade del piano (luce del sentiero e due di crescita: `ship_spec.py`, piano rigenerato), aiuole con piante leggere: 136 k → 110 k triangoli |
| Biblioteca | pavimento di doghe di rovere con filetti d'ottone e tre tappeti, soffitto a cassettoni, mappamondo, scala, schedari, plinto con il modello della nave; libri a 4–8 triangoli (`SFB.swatch_slab`): 147 k → 87 k |
| Salotto, giochi, osservatorio, Bow Observation | pavimenti di doghe e tessere (caffè a scacchiera di terrazzo, tessere nere), nuvole acustiche, tappeti; Bow Observation arredato (rosa dei venti in pietra e ottone, tavolo stellare, bar, salotti, cielo di stelle con anello di luce): 104 k → 69 k |
| Cabine, stanze, suite | l'ingresso delle suite non è più un muro vuoto; oggetti personali in ogni cabina (foto, poltrona, lampada, mensola; chitarra o medaglie) |
| Barbiere e sartoria | scacchiera, palo, poltrone di pelle, lavaggio, caschi, bottiglie, stoffe, manichini, specchio a tre ante |
| Camere stagne e tute | tute EVA vere (busto rigido, cuscinetti, soffietti, zaino, casco con visiera) al posto dei manichini a scatole |
| Depositi | merce vera: cartoni con nastro ed etichetta, ceste, sacchi, latte, valigie, fusti, bombole, bancali (`ship_stock.py`) |
| Crew Berthing | `SM_BERTH_Stack_A/B/C` rifatte nel linguaggio del kit (montanti, piani, fiancate, tasca a rete con libro e foto, luce di lettura, targhetta, materasso, coperta, cuscino, tende a pieghe vere color ruggine: la Red watch; cassetto sotto): **4,1–4,3 k triangoli l'una, prima 12,5 k**; stesso frame e stesse altezze (materasso a +0,2 m sul piano: i sette dormienti di `build_berths.py` e le cuccette di `life.py` restano dove sono); armadietti `SM_BERTH_Lockers` (0,6 k) con prese d'aria forate, numero e spia. Il colore delle tende è la costante `CURTAIN` di `ship_berth_racks.py` |
| Medbay | `SM_MED_Bed` rifatto (`ship_med_bed.py`: 2,4 k, prima 4,6 k): piano in due sezioni con lo schienale a 20°, materasso e cuscino, testiera e pediera, sponde, asta della flebo con sacca e pompa, unità di testaletto (prese dei gas, luce, targhetta) e monitor su braccio **nello stesso rettangolo** che `SM_MED_Vitals` copre; coperte dei pazienti nei tessuti del kit e a metà dei triangoli (6,2 k, prima 11,7 k) |
| Quarantine | il letto d'isolamento del kit (`ship_furn4.hospital_bed`) aveva lo schienale che calava verso la testa: ora sale |

**Ganci nuovi** (opt-in: una stanza cambia solo se la scelgo): `Style(floor_fn=, ceiling_fn=, floor_grid=, floor_guide=)` e `ceiling="none"` in `ship_shell.py` e `ship_rooms.py`; pavimenti di doghe, tessere e a zone, tappeti ornati, cassettoni, nuvole, capriate e schermi di cielo in `ship_surfaces.py`; griglia dei giunti e linee guida dipinte nei temi comando, equipaggio, medico e laboratorio (`ship_themes.py`).

**Costo** (kit completo, `ship_measure.py` e `ship_cost.py`; «prima» = la base del 3/10, tutte le cifre sulle mesh distinte di ogni ponte): triangoli delle sole stanze **13,03 M → 10,18 M (−22 %)**; l'intero kit (446 mesh) da 6,61 M a **5,42 M**; la stanza più pesante 149 k → 131 k (`hydro`; poi `cabins` 131 k e `staterooms` 130 k: il limite è 150 k); slot 5 284 → 5 177; set di texture per ponte da −1 a −4 (stima a 2,67 MB il set: il Ponte 4 da 80 a 69 MB). Per ponte (M di triangoli): 2 0,84 → 0,69 · 3 1,06 → 0,79 · 4 1,98 → 1,47 · 5 1,43 → 1,12 · 6 1,71 → 1,30 · 7 1,32 → 0,99 · 8 1,68 → 1,31 · 9 1,38 → 1,15 · 10 0,50 → 0,41 · 11 0,76 → 0,66 · 12 0,29 → 0,25. Come:
1. **la minuteria delle stanze (gruppo `fine`) non è più smussata** (`SParts.FINE_DIET`, acceso da `ship_kit.build_mesh` solo per le stanze; ombreggiatura liscia per angolo): 12 triangoli a scatola invece di 44, 28 a un'asticella invece di 92, −19 % dei triangoli del kit con lo stesso aspetto da un metro in su;
2. **piante leggere** (alberi, vasi e aiuole a metà dei triangoli o meno: stesso aspetto da un metro in su), vasi torniti nel gruppo morbido, **niente più antúrio, ficus e zebrata** (la pianta da scrivania è un singonio piccolo): tre set di texture e tre slot in meno in ogni ponte che li usava;
3. cuccette, armadietti, letti e coperte come sopra.

Gli slot restano alti nel `lounge` (44) e in `games` (40): l'unione dei materiali quasi uguali (bianchi) non è stata fatta, i legni (`Wood`, `Walnut`) sono davvero diversi.

**Strumenti nuovi** (`art/blender/`): `ship_measure.py` (triangoli, slot e firma geometrica di ogni mesh: `-- --json out.json [--only A,B]`), `ship_cost.py` (prima/dopo per ponte, firme cambiate), `ship_profile.py` (dove vanno i triangoli di una stanza, funzione per funzione), `ship_industrial.py` (tubi con colori di servizio, valvole, manometri, passerelle, copricavi, corsie, scarichi, avvolgitubo, lavaocchi: provato in una scena, **non ancora usato da nessuna stanza**).

**Resta** (indagine con anteprime il 4/10, nessuna modifica): le stanze di comando (CIC, briefing, comunicazioni, uffici, archivi: pavimenti piatti, poco in mezzo alla sala), le officine, gli impianti e i macchinari (grandi sale scure con poche macchine e il pavimento piatto: servono tubi tra le macchine, passerelle, corsie e pezzi grandi più dettagliati: serbatoi, pompe, torni, armadi), l'armeria e il poligono, le sale volo; e **le stanze di servizio più ripetute** (Technical Space ×113, depositi di sezione ×125, spogliatoi ×98, stazioni DC ×65: armadietti neri, sale spoglie). `ship_industrial.py` è pensato per queste.

**Ricostruire** (il piano è già rigenerato e nel ramo; 93 stanze hanno una firma diversa): `ship_kit.py` (FBX in `art/export/ship`) → `berths.py -- art/export/berths` e `medbay.py -- art/export/medbay` (cuccette, armadietti, letto, coperte) → nell'editor `build_berths.py` e `build_medbay.py`, poi `build_ship_interior.py` (importa solo gli FBX cambiati; crea `MI_SHIP_TileBlack` da `room_materials.json`).

## 11. Il gioco: cosa legge il piano

- **`UAstraShipPlan`** (C++) legge `compartments, doors, graph`, le lampade (`GetLamps()`), i ponti con i loro sotto-livelli e, da NAVE-3, `vertical[]` e `transit[]` (**ASCENSORI**: `UAstraLiftSubsystem` costruisce pozzi, vetture, ante, pannelli e voce dal piano all'inizio del gioco; `FindRide` cerca il nodo di attesa per posizione, 90 cm). Il Capitano sa dove sta ("DECK 4 · MESS CONCOURSE · SECTION B") dal compartimento del piano: **non cambiare `id`, `kind` e `name` dei compartimenti esistenti né il compartimento di tipo `bridge`**.
- **Porte**: una `AAstraDoor` per porta del piano **esclusa quella con il flag `lift`** (nome `Door_<id>`, cartella `Interior/Doors`, nel sotto-livello del ponte). Le porte delle torri delle scale restano chiuse a chiave finché il ponte vicino non ha la mappa (`LOCK_STAIRS`).
- **Incidenti** (DISTRUZIONE): il modello dei danni gira sulla pianta; le paratie di sezione sono le porte `blast`. **Il banco (`tools/damage.py run --scenario all`) nomina quattro compartimenti del Ponte 4**: `d4_games_D1`, `d4_games_D2`, `d4_store_dry_C1`, `d4_spm_D3` (la Spine in sezione D: per questo il pezzo di Spine del Ponte 4 che la contiene si chiama `SPM`), e un controllo ("lascia andare gli effetti quando il Capitano è lontano") **dipende dalla geometria**:
  gli effetti stanno dentro 35 m dal Capitano e la stanza vicina `d4_games_D1` deve stare entro 45 m dal centro di `d4_games_D2` (e il bar accanto più indietro di 35 m dopo gli 80 m): per questo due stanze del Ponte 4 hanno 4 m di vuoto davanti (`gap:4`). **Non cambiare** le posizioni di queste quattro stanze senza rilanciare il banco (46/46).
- **VITA** legge `compartments[].stations` e il grafo; `tools/life.py check` verifica che ogni lavoro, posto e casa del file della vita risolva sul piano (con le stanze nuove: dentista, obitorio, counselling, cella, ufficio della sicurezza, nuclei di calcolo, simulatori, camere stagne e capsule, negozio; case: le sale cuccette dei Ponti 4, 6, 9, 11 e le cabine; **nessun posto letto resta senza un selettore di casa**, controllato).

## 11bis. La nave in scala: istanze, lampade, sotto-livelli (NAVE-2, valido anche per NAVE-3)

Il vincolo: ~12 000 pezzi, ~1 750 porte-attore, ~4 400 lampade, memoria di gioco ≤ 9 GB, un ponte che entra in meno di un secondo, mai sotto i 45 fps camminando su un MacBook Air M4.

1. **Istanze, non attori** (`AAstraDeckShell`). Un attore per ponte tiene tutte le mesh del ponte come istanze (`AddInstancesChunked`): un componente per mesh **per tratto di 160 m lungo la nave**, i trasformi in un solo array piatto, nessun tick. Con NAVE-3 un ponte ha **851–1 426 pezzi** (la segnaletica è circa un quarto dei pezzi in più: le lame e le ordinate sono istanze piccole) di 33–100 mesh diverse.
2. **Lampade come dati, un pool di luci vere** (`UAstraLampPool`): le `lights[]` del piano sono un array piatto; il pool sposta **10** `URectLightComponent` (ombre spente) sulle lampade più utili al Capitano, sfumano in 0,35 s, la scelta si rifà 5 volte al secondo; `astra.lamps.gain` (6) moltiplica i lumen del piano. Il danno (DISTRUZIONE) le segue (strisce rosse senza potenza, sfarfallio, fuoco).
3. **Un sotto-livello per ponte, in streaming** (`UAstraDeckStreaming`): `/Game/ASTRA/Maps/Decks/L_Deck01 … L_Deck12`; il Capitano tiene caricato il suo ponte e quelli che le sue scale raggiungono (e, in ascensore, quello della tappa: `RequestAt`).
4. **Porte attori, segnaletica istanze.** Le porte restano `AAstraDoor` (una lontana dal Capitano tick-a 4 volte al secondo: `AstraDoor.cpp`); i cartelli, le targhe e le ordinate sono istanze del guscio.

**Lo script** (`tools/ue_scripts/build_ship_interior.py`, v2, idempotente, rapporto JSON): materiali → importazione del kit (solo i file nuovi o cambiati; `REBUILD_KIT = "all"` rifà tutto) → per ogni ponte una mappa nuova (guscio + porte **senza quelle `lift`**) → `L_Bridge` con i sotto-livelli → copia sottile del piano in `Content/ASTRA/Data` → apertura delle entrate delle stanze esistenti (`REMOVE_LIFT_LEAVES`: le ante statiche delle vecchie alcove; la porta si mette una volta) e dello Studio (`OPEN_READY_ROOM`).
Parametri: `DECKS`, `REBUILD_KIT`, `CHUNK_M`, `LOCK_STAIRS`, `REMOVE_LIFT_LEAVES`, `OPEN_READY_ROOM`, `SAVE_LEVEL`, `ROOT/LEVEL/DECK_DIR`.

**Budget per ponte** (`ship_budget.py`; "triangoli di istanza" = tutte le istanze viste insieme: il tetto, non ciò che sta davanti al Capitano; con Nanite i triangoli sono memoria e disco):

| Ponte | pezzi | mesh | tri mesh distinte | componenti | porte | lampade | stanze |
|---|---|---|---|---|---|---|---|
| 1 | 3 | 3 | 0,06 M | 3 | 1 | 4 | 1 |
| 2 | 851 | 95 | 1,70 M | 221 | 96 | 222 | 63 |
| 3 | 911 | 102 | 1,76 M | 255 | 103 | 282 | 65 |
| 4 | 1 157 | 129 | 2,70 M | 336 | 164 | 376 | 117 |
| 5 | 1 426 | 138 | 2,82 M | 368 | 169 | 456 | 113 |
| 6 | 1 382 | 138 | 2,40 M | 371 | 208 | 480 | 162 |
| 7 | 1 318 | 136 | 2,66 M | 350 | 179 | 446 | 137 |
| 8 | 1 199 | 136 | 2,94 M | 337 | 159 | 397 | 118 |
| 9 | 1 380 | 136 | 2,49 M | 353 | 182 | 460 | 145 |
| 10 | 1 255 | 96 | 1,74 M | 301 | 153 | 395 | 115 |
| 11 | 1 350 | 122 | 2,08 M | 348 | 179 | 458 | 139 |
| 12 | 1 086 | 54 | 0,54 M | 200 | 136 | 382 | 95 |

(NAVE-2: 509–791 pezzi, 106–190 componenti per ponte: il raddoppio è la segnaletica, le stanze di servizio e le nuove banche.) Le porte sono quelle che diventano attori: **le porte d'approdo degli ascensori (`lift`) non sono contate**.

Il Capitano su un ponte di mezzo ha caricato il suo e i due vicini: **~850–1 090 componenti, ~440–560 porte, ~1 250–1 380 lampade nei dati (10 luci vere); la plancia, in battaglia, ha una porta e nessun componente in più**. Il tetto delle porte-attore residenti è stato portato da 400 a 600 (le stanze e le porte sono il doppio di NAVE-2; una porta lontana tick-a 4 Hz): è il numero da guardare camminando.

**Cosa guardare camminando** (con `astra.decks` e `astra.lamps.info` aperti; fps e memoria con `stat unit` e `stat memory`):

1. L'esito dello script: `bounds_problems` vuoto, per ponte le istanze uguali ai pezzi del piano, `existing entrances opened` la prima volta, 0 la seconda.
2. **Gli ascensori** (ASCENSORI): dalla plancia con i due ascensori di plancia ai Ponti 4, 6, 7, 9; le lobby di una banca (la cornice di una porta con le ante dell'`AAstraLiftLanding`, l'elenco del ponte); la distanza a piedi dall'ascensore più vicino (a occhio ≤ 80 m); i cartelli a lama con le frecce giuste ("TURBOLIFTS →" porta davvero a una lobby).
3. **Il Ponte 4**: il nuovo **Mess Concourse** (caffè, negozio, giardino, doghe, schermi), la strada dei marinai, l'atrio del Berthing; **il Ponte 5**: la navetta (la banchina, il tunnel, i respingenti ai capolinea; la vettura la fa correre ASCENSORI); **Ponte 6**: il complesso medico (dentista, obitorio, counselling); **Ponte 8**: cella, caserme, hangar con i Kestrel; **Ponte 7**: gli impianti.
4. **Il labirinto**: da una torre delle scale a una galleria dello scafo (tono V), le camere stagne e le capsule, un tubo di Jefferies (la scala a pioli), un cunicolo K.
5. Le luci: entrando in una stanza si accendono le sue lampade in meno di mezzo secondo, mai più di 10 insieme. fps camminando sui Ponti 4, 5, 8 (i più pieni) e 12; memoria dopo aver percorso tutti i ponti.

## 12. Prove e risultati (offline)

| Prova | Risultato |
|---|---|
| `ship_checks.py` (piano versione 2) | **0 problemi, 0 avvisi**: 3 234 compartimenti, nessuna sovrapposizione, un solo componente connesso, programma completo, 746 posti letto per 560 (+33 %), 800 posti in capsule, pozzi e approdi, nodo di attesa a 0 cm, navetta |
| `tools/life.py check` | OK; 644 posti letto in 46 stanze, nessuno senza una casa |
| `tools/damage.py run --scenario all` | **46/46 PASS** (con l'editor compilato di `main` e il piano nuovo) |
| `ship_kit.py` (kit completo con prove) | 0 problemi di mesh; **0 rotte bloccate, 0 posti sul mobilio** su 12 ponti; **l'ingombro della vettura della navetta libero** (celle del tunnel e sale: `car_clearance`, che sulle vecchie versioni trova la banchina, il condotto, il cancello e le pareti di testata) |
| ARTE-INTERNI (§10.4) | kit completo: 446 mesh, 6,61 M triangoli, **0 rotte bloccate, 0 posti sul mobilio**; piano rigenerato: `ship_checks.py` **0 problemi, 0 avvisi**, `tools/life.py check` OK, `tools/lift.py check` OK; anteprime di ogni stanza in `docs/progressi/interni_2026-10-03/` |
| Anteprime Eevee | guardate davvero, stanza per stanza (le critiche: sedili senza nessuno, sguardi contro il muro, caschi nel varco di una porta, pozzi chiusi sulle porte, specchi neri, partizione del dentista, atrio vuoto, frecce a specchio: tutte corrette) |

**Distanza dall'ascensore più vicino** (§7) e **programma** (§5.1) sono i numeri di progetto: la mediana a piedi dall'ascensore è di 32–48 m su tutti i ponti d'equipaggio, il 90° percentile 56–92 m.

## 13. Richieste al lead (fuori dai miei file)

1. **DISTRUZIONE (C++): profili per i tipi nuovi.** Il modello dei danni tratta `lobby`, `lift` (pozzo), `trunk`, `tunnel`, `transit`, `lifepod`, `airlock`, `dental`, `morgue`, `counselling`, `computer`, `simulator`, `shop` come stanze qualunque per volume. Un pozzo di ascensore o un tubo di Jefferies **non porta fumo e aria da un ponte all'altro** (un compartimento per pozzo): se lo si vuole, serve codice. Gli archi `shuttle` hanno larghezza 0,05 m (il banco li legge come un'apertura); gli archi `stair` con `ladder: true` sono i tubi di Jefferies (nessuna regola nel modello).
2. **Il banco dei danni nomina compartimenti del Ponte 4 per id** (`d4_games_D1/D2`, `d4_store_dry_C1`, `d4_spm_D3`): reggono finché il layout non cambia; scegliere per tipo e posizione toglierebbe questa dipendenza.
3. **VITA e la navetta:** il piano ha gli archi `shuttle` e le otto fermate (`platform`); il file della vita non manda nessuno in navetta (non è una regola di casa: il C++ sceglie i percorsi sul grafo; un arco `shuttle` costa tempo di corsa + sosta).
4. **Atlante e importazione:** `T_SHIP_Labels.png` è ora 4096 × 6144; il kit sono ~430 mesh (la prima importazione è lunga: lasciare `REBUILD_KIT = "changed"` dopo la prima). `Content/ASTRA/Data/aquila_plan.json` (5,5 MB) e `aquila_life.json` sono i file che il gioco legge: vanno nel commit.
5. **Le stanze vecchie e le loro alcove** (Mess Hall, Berths, Medbay): le entrate sono dei vecchi attori di L_Bridge; `REMOVE_LIFT_LEAVES` toglie le ante statiche (cartelle `Mess/Lift`, `Berths/Lift`, `Medbay/Lift`) e mette la porta: se ASCENSORI le ha già tolte, lo script lo dice (`the door is there already`).
6. **`tools/lift.py check` (ASCENSORI) e il piano porta.** Il controllo in Python accetta una porta d'approdo a 0,15 m dalla faccia interna del pozzo; il piano la mette, per tutti i 291 approdi, sulla faccia della lobby, a 0,20 m (§7), dentro la tolleranza del motore (0–0,6 m): il controllo va allargato a 0,6, altrimenti segnala tutti gli approdi con lo stesso scarto.
7. **I tubi di Jefferies si scalano solo se il gioco lo fa** (campi del record `trunk`, §6: `ladder`, `facing`, `step`, `hole`, `closed`, `rungs`). La nicchia è un buco di 1,1 × 1,1 m nel pavimento di ogni ponte tranne la chiglia: senza il volume della scala, chi vi mette un piede cade lungo la colonna.
8. **Il blocco esterno dei pozzi del ponte (`art/blender/quarters.py`, non mio).** `SM_SHIP_ASTRA_AquilaBridgeBlock` è un guscio chiuso e vuoto con un piedistallo pieno; ora l'alloggiamento del Ponte 1 ha il suo interno e `build_ship_interior.py` gli toglie la collisione (`OPEN_BRIDGE_LIFT`). Se un giorno lo si vuole di nuovo solido o cavo, va fatto lì (la faccia in su del piedistallo, a z −0,3 su tutta l'impronta 4,8 × 7,2, è quella che tratteneva chi era in vettura), e la parete di prua dell'alloggiamento, 0,2 m davanti alla faccia di prua del blocco, va rivista.

**Ancora aperti da NAVE-2** (non sono cambiati):
- **Crew Berthing: "Deck 3" sul piano del Ponte 4.** Il Berthing dice DECK 3 ma poggia a z -46 come la Mess. Il piano lo registra su `plane: 4` con `label_deck: 3`. Consigliato: chiamarlo **Deck 4 · Section C** (la BIBBIA: il Ponte 3 ha gli alloggi ufficiali e la palestra, adesso lo sono davvero) cambiando `data/ship/aquila_berths.json`, `AstraShipSubsystem.cpp`, `ASTRAPlayerController.cpp`, i docstring di `build_berths.py`/`berths.py` e l'etichetta `room_deck3`.
- **Lo scafo sotto il blocco (Ponti 2 e 3)**: aperto da ARTE-NAVI; con i ponti costruiti, controllare camminando sul 2 e sul 3 che non si vedano piani fantasma dall'interno (faccia inferiore del blocco, pareti dell'isola). Lo scafo non ha collisione né ombra.
- **Il Flight Deck solo in ascensore**: il suo ingresso è un'alcova a z -72,8, il corridoio del Ponte 9 è a -66 (un arco con salto di 6,8 m che VITA percorre come un ascensore); per una rampa serve una torre dedicata.
- **Il Ponte 1 e `build_bridge_v3.py`**: lo Studio sostituisce un modulo e due pannelli del corridoio; lanciare `build_ship_interior.py` dopo `build_bridge_v3.py`.
- **Cottura**: verificare che `/Game/ASTRA/Maps/Decks` (le dodici mappe) e `/Game/ASTRA/Kit/Ship` finiscano nel pacchetto (i sotto-livelli sono riferimenti deboli di L_Bridge).

## 14. Limiti noti

- **Gli interni di ARTE-INTERNI** (§10.4): non provati in Unreal; 21 slot di materiale per stanza in media (massimo 44 nel `lounge`); restano meno rifinite le sale di comando, i laboratori, le officine, gli impianti, l'armeria, le sale volo e i depositi.
- **Non provato nell'editor.** Il kit e le anteprime sono verificati in Blender (Eevee) e con i raggi; il piano con i controlli, `tools/life.py` e il banco dei danni; ciò che è GPU (tempo di fotogramma, memoria, il carico di un ponte con 1 400 istanze) va provato dal lead.
- **I pozzi e le vetture** non sono mie: il kit ha le lobby e i pozzi (pareti), non le vetture né le ante d'approdo; **la vettura della navetta** è una mesh a parte e la sua corsa è di ASCENSORI.
- **Le altre navi** (fase C: un piano per ogni classe di `data/war/classes.json`): non ancora, quando il lead lo chiede.
- Le gallerie e le braccia (toni V e K) non hanno cartelli a lama (solo targhe e ordinate): ci si orienta con i cartelli dei passaggi e con le targhe delle camere stagne e delle capsule.
- La chiglia (Ponte 12): la punta di prua dei serbatoi dista fino a 196 m dall'ascensore più vicino (solo serbatoi e cunicoli); gli ambienti d'equipaggio sono tutti entro il 90° percentile di 100 m.
- L'Observation Deck e il Bow Observation hanno vetri traslucidi (mesh non Nanite). Il reticolo è ortogonale (nessuna curva). La scala a pioli autonoma (`SM_SHIP_LadderTrunk`) è pronta ma non piazzata.
- Il Concourse ha molti più posti (23): VITA lo userà come luogo di svago e come mensa di riserva più di prima.
