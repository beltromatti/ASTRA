# Contratto delle postazioni — come la mente parla al gioco (v2, 30 settembre 2026)

*Per il lead. Il gioco ha già le postazioni (`UAstraStationsSubsystem`, `Source/ASTRA/AstraStations.*`, `main` a f6092c7) e la mente le parla **con le parole
del gioco**: questo documento dice quali sono, come la mente traduce i suoi nomi nei loro, cosa legge dallo stato, cosa si aspetta dagli eventi e cosa
chiede in più al C++. Coerente con [ARCHITETTURA.md §3–§5](ARCHITETTURA.md); ciò che va aggiornato nel §4 di quel file è al §9. Gli identificatori sono in
inglese (sono quelli del codice: `mind/astra_mind/stations.py` è la fonte unica, questo documento ne è la traduzione per chi scrive C++).*

**Come è stato verificato.** Leggendo il C++ di `main` (`AstraStations.cpp/.h`: `Defaults`, `ModeTable`, `ModeChoices`, `SetMode`, `Enter`, i `Tick*` e `StationsJson`;
`AstraShipSubsystem.cpp`: `ApplyCommand`, `CaptainContext`, `Snapshot`; `AstraScreensSubsystem.cpp`: `PushPad`; `AstraBattleSubsystem.cpp`: `LaunchSquadron`,
`ContactsJson`; `AstraViewscreen.cpp`: la lettura dell'ordine di ops) — **non contro il gioco in esecuzione** (per regola niente editor). Il banco
`mind/bench/stations_unit.py`, classe `WireTest`, contiene una copia del vocabolario del gioco (`GAME_ASPECTS`, `GAME_MODES`, `GAME_PARAM_KEYS`, uno stato di esempio
scritto come `StationsJson`) e **fallisce se un modo dell'equipaggio esce con parole che il gioco non conosce**: se cambiate il C++ cambiate anche quella tabella e `stations.py`
(un solo posto: `_build()`), e i test dicono cosa manca.

---

## 1. Due vocabolari, un adattatore

- **Quello dell'equipaggio** (ciò che il modello vede nello strumento `station` e nel quadro delle console): un nome piatto e autoesplicativo per modo
  (`shields_face_threat`, `viewscreen_target`, `scan_focus`, `heat_auto`, `mission`…). Serve a far scegliere al modello il modo giusto dal senso delle parole
  del Capitano; è già validato con il modello vero (`bench/stations_scenarios.py`).
- **Quello del gioco**: `{station, aspect, mode, params}`. Un **aspetto** (`aspect`, la *lane* della prima versione di questo documento) è una modalità persistente
  indipendente di una postazione: `course`, `engagement`, `shields`, `point_defense`, `missiles`, `emcon`, `scan`, `viewscreen`, `holo`, `datapad`, `damage_control`, `power`,
  `heat`, `reactor`, `channel`, `listen`; per `flight` un aspetto per squadrone (`alpha`, `bravo`, `drones`); `xo` ha `delegation`.
- `stations.to_wire(cmd, by, state)` traduce un comando controllato dell'equipaggio in quello del gioco; `stations.from_wire(args)` lo rilegge (lo usa la nave
  locale dei test, che parla come il gioco); `stations.lanes_of(station)` legge lo stato del gioco nei nomi dell'equipaggio. Un modo che la mente non conosce (una build
  più nuova) è mostrato col nome del gioco, non scartato.

## 2. Il comando `station`, come esce dalla mente

`command{id, name: "station", args, by}` → `ApplyCommand` → `SetMode`. La mente manda **sempre** l'aspetto esplicito (niente ambiguità di `AspectFor`):

```json
{"station": "helm", "aspect": "course", "mode": "intercept", "params": {"target": "T-23", "standoff_km": 6},
 "until": "target_lost", "note": "seguilo a sei chilometri", "by": "captain"}
```

| Campo | Note |
|---|---|
| `station` | `helm` `tactical` `sensors` `ops` `engineering` `comms` `flight` `xo` (è anche l'id dell'ufficiale; il `by` del messaggio è l'ufficiale che agisce: il gioco lo usa per il *chirp* della console) |
| `aspect` | l'aspetto del gioco (§3); per `flight` lo squadrone |
| `mode` | il nome del gioco (§3); per `flight` il tipo di missione (`cap` `escort` `strike` `ew` `recon` `sar` `hold` `recall`) |
| `params` | solo quelli che il C++ legge (`target`, `targets[]`, `weapons[]`, `fire`, `standoff_km`, `speed_pct`, `heading_deg`, `mark_deg`, `distance_km`, `side`, `slot`, `radius_km`, `direction`, `range_km`, `every_s`, `zoom`, `party`, `page`, `focus`, `what`, `sector`, `system`, `squadron`, `station`, `delegation`, `face_action`, e per `power custom` i nomi dei sistemi). La mente ha già limitato i numeri e scartato il resto |
| `until` | sempre esplicito: quello scelto dal modello o il predefinito del modo (§3) |
| `note` | ≤ 160 caratteri, il perché in poche parole (finisce nel registro `recent`) |
| `by` (dentro `args`) | **`captain`** se l'ordine viene dal Capitano, **`officer`** se è iniziativa dell'ufficiale. È dove `ApplyCommand` lo legge per `set_by` (il `by` a livello di messaggio resta l'id dell'ufficiale) |

**Cosa fa la mente prima di spedire** (tutto in `stations.py`, provato offline): `broadside.side: best` → `auto`; `shields_sector` → il modo diretto (`forward` `aft` `port` `starboard` `dorsal` `ventral`,
«fore/front/rear/left/right» sono capiti); `power_profile`/`emcon`/`heat_radiators` → il modo del gioco è il valore scelto; `power_custom` → i nomi dei sistemi senza `_pct`; `mission` →
aspetto = squadrone, modo = tipo; `delegation` → `station xo`, `params {station, delegation}`; `zoom` è un numero 0,25–8 (moltiplicatore dell'inquadratura) **o** `close` `max` `wide` come nel
gioco; «tutto fermo/mezza velocità/tutta avanti» = `course` **solo con `speed_pct`** (il C++ tiene la rotta se manca `heading_deg`). I bersagli vanno **come sono**: gli id (`T-23`), **`action`**
(rivalutato dal gioco a ogni passo: quello di cui parla il combattimento ora, cioè il bersaglio del tattico, altrimenti l'ostile più vicino; la mente lo offre solo per `keep_on_bow`, `viewscreen target` e `scan focus`)
e, in un `engage`, **`hostiles`** (un ordine permanente del gioco: l'ostile migliore a portata, i nuovi compresi; la mente non lo espande più).

**Risposta** (`command_result`): la mente la fa leggere all'ufficiale, con i valori veri; i rifiuti del gioco sono già parole adatte (`no contact T-99 on the plot`, `T-31 is only a bearing (no range)…`,
`none of those contacts is a live hostile on the plot`). Le autorità (`free`/`engaged`/`captain`, delega, ordini permanenti, `transit`/`retreat` mai di iniziativa) le fa rispettare la mente;
il gioco accetta ciò che arriva.

## 3. Le postazioni: nomi dell'equipaggio ↔ modi del gioco

Colonne: **aspetto** · nome dell'equipaggio · **modo del gioco** · parametri (`?` facoltativo, `=` predefinito/scelte) · `until` predefinito (quello che il gioco fa davvero) · autorità
(`free` = l'ufficiale con delega `auto` lo può impostare da sé; `engaged` = idem ma per servire un combattimento; `captain` = solo su ordine o ordine permanente).

### helm — Ferri

| Aspetto | Equipaggio | Gioco | Parametri | until | Aut. |
|---|---|---|---|---|---|
| `course` | `hold` | `hold` | face_action?=True | order | free |
| `course` | `course` | `course` | heading_deg?, mark_deg?, speed_pct? (almeno uno) | order | captain |
| `course` | `intercept` | `intercept` | target, standoff_km?=6, speed_pct? | target_lost | engaged |
| `course` | `keep_on_bow` | `keep_on_bow` | target (id \| `action`) | target_lost | free |
| `course` | `follow` | `follow` | target, distance_km?=2, side?=astern\|port\|starboard\|above\|below | target_lost | engaged |
| `course` | `orbit` | `orbit` | target, radius_km?=8, direction?=ccw\|cw | target_lost | engaged |
| `course` | `broadside` | `broadside` | target, side?=port\|starboard\|best (→ `auto`), range_km?=8 | target_lost | engaged |
| `course` | `evade` | `evade` | – | time:45 | free |
| `course` | `retreat` | `retreat` | – | order | captain |
| `course` | `formation` | `formation` | target? (senza: l'ammiraglia), slot?=astern\|port\|starboard\|above\|below, distance_km?=3 | target_lost | captain |
| `course` | `transit` | `transit` | system | order | captain |

`hold` è il predefinito e il C++ già porta la prua sull'azione da solo in combattimento (`face_action` vero): l'iniziativa del timone parte da lì. `intercept` legge `action` solo all'ingresso (la rotta si dà lì): la mente non lo offre.

### tactical — Voss

| Aspetto | Equipaggio | Gioco | Parametri | until | Aut. |
|---|---|---|---|---|---|
| `engagement` | `hold_fire` | `hold_fire` | – | order | captain |
| `engagement` | `return_fire` | `return_fire` | – | order | free |
| `engagement` | `weapons_free` | `weapons_free` | range_km? | order | captain |
| `engagement` | `engage` | `engage` | targets (id… \| `hostiles`), weapons?, fire?=sustained\|volley\|conserve | target_lost | engaged |
| `shields` | `shields_balanced` | `balanced` | – | order | free |
| `shields` | `shields_face_threat` | `face_threat` | – | order | free |
| `shields` | `shields_sector` | `forward` `aft` `port` `starboard` `dorsal` `ventral` | sector | order | free |
| `shields` | `shields_off` | `shields_off` | – | order | captain |
| `point_defense` | `pd_auto` | `pd_auto` | – | order | free |
| `point_defense` | `pd_protect` | `protect` | target | order | free |
| `point_defense` | `pd_off` | `pd_off` | – | order | captain |
| `missiles` | `missiles_normal` | `normal` | – | order | free |
| `missiles` | `missiles_conserve` | `conserve` | – | order | free |
| `missiles` | `missiles_saturate` | `saturate` | – | order | captain |

### sensors — Nair

| Aspetto | Equipaggio | Gioco | Parametri | until | Aut. |
|---|---|---|---|---|---|
| `emcon` | `emcon` | `silent` `restricted` `full` | level | order | captain |
| `scan` | `scan_passive` | `passive` | – | order | free |
| `scan` | `scan_sweep` | `sweep` | every_s?=60 (≥ 15) | order | captain |
| `scan` | `scan_focus` | `focus` | target (id \| `action`) | target_lost | free |

### ops — Tanaka (schermo principale, tavolo olografico, datapad, controllo danni)

| Aspetto | Equipaggio | Gioco | Parametri | until | Aut. |
|---|---|---|---|---|---|
| `viewscreen` | `viewscreen_auto` | `auto` | – | order | free |
| `viewscreen` | `viewscreen_forward` | `forward` | zoom? | order | free |
| `viewscreen` | `viewscreen_target` | `target` | target (id \| `action`), zoom? | target_lost | free |
| `viewscreen` | `viewscreen_tactical` `_fleet` `_sector` `_damage` `_off` | `tactical` `fleet` `sector` `damage` `off` | – | order | free |
| `viewscreen` | `viewscreen_comms` | `comms` | party? | order | free |
| `holo` | `holo_tactical` `holo_sector` | `tactical` `sector` | – | order | free |
| `holo` | `holo_ship` | `ship` | target | order | free |
| `datapad` | `datapad_push` | `push` | page=overview\|contact\|damage\|fleet\|orders, focus? | order | free |
| `damage_control` | `dc_auto` | `auto` | – | order | free |
| `damage_control` | `dc_priority` | `priority` | what | order | free |

`zoom`: `close` (×2) `max` (×4) `wide` (×0,4) o un numero 0,25–8 (moltiplicatore dell'inquadratura, 1 = il soggetto riempie il quadro). Il rilascio quando il bersaglio muore lo fa il gioco (`ReleaseOrder`, `set_by:"auto"`).

### engineering — Mensah

| Aspetto | Equipaggio | Gioco | Parametri | until | Aut. |
|---|---|---|---|---|---|
| `power` | `power_profile` | `balanced` `combat` `evasive` `silent` `shields` `weapons` `engines` | profile | order | free |
| `power` | `power_custom` | `custom` | shields_pct?, weapons_pct?, engines_pct?, sensors_pct?, life_support_pct?, flight_deck_pct? (→ `shields`, `weapons`, …) | order | free |
| `heat` | `heat_auto` | `auto` | – | order | free |
| `heat` | `heat_radiators` | `extended` `retracted` | state | order | free |
| `reactor` | `reactor_normal` | `normal` | – | order | free |
| `reactor` | `reactor_battle_short` | `battle_short` | – (bilancio 800 % invece di 700 %, +0,3 %/s di calore; `normal` lo riporta a 700 % scalando le assegnazioni sopra il nominale) | order | captain |

### comms — Martin · flight — Price · xo — Serra

| Aspetto | Equipaggio | Gioco | Parametri | until | Aut. |
|---|---|---|---|---|---|
| `channel` | `channel_mute` `channel_unmute` | `mute` `unmute` | – | order | free |
| `listen` | `listen_fleet` `listen_enemy` `listen_all` | `fleet` `enemy` `all` | – | order | free |
| `alpha` `bravo` `drones` | `mission` | il tipo (`cap` `escort` `strike` `ew` `recon` `sar` `hold` `recall`) | squadron, type, target? | order | free |
| `delegation` | `delegation` | `delegation` | station, level=manual\|advise\|auto (→ `params.station`, `params.delegation`) | order | free |

**Non ci sono** (il gioco li ha tolti dalle sue tabelle, la mente non li offre): `ew`/`sigint`, `holo fleet`,
`listen off`, i profili `offense`/`defense`/`flight_ops` (i profili del gioco sono `combat`/`shields`/`weapons`…), le pagine `weapons`/`flight`/`comms`/`ship` del datapad, `formation` e `rtb_when` per gli squadroni,
`heat_auto{limit_pct}`. **Stato iniziale** (`Defaults()`): `hold` · `return_fire`, `face_threat`, `pd_auto`, `normal` · `emcon` (della nave), `passive` · `auto`, `tactical`, `auto`, `push` · `balanced`, `auto`, `normal` · `close`, `fleet` · squadroni `hold`.

## 4. Lo stato: `ship_state.state.stations` e `viewscreen`

Come lo scrive `StationsJson()` (la mente lo legge così, senza altro):

```json
"stations": {"helm": {"officer": "helm", "delegation": "auto",
                      "status": "INTERCEPT T-23 at 14.2 km · heading 122 mark 0 · 310 m/s (throttle 64%)",
                      "modes": {"course": {"mode": "intercept", "params": {"target": "T-23", "standoff_km": 6}, "until": "target_lost", "set_by": "captain", "for_s": 84}},
                      "recent": ["course intercept: intercepting T-23"]}, "…": {}},
"viewscreen": "target: ordered, T-23 (Cocytus), zoom x8",
"action_target": "T-23"
```

`action_target` (in cima a `ship_state`, accanto a `stations`) è ciò che «`action`» vuol dire ora: la mente lo scrive nel quadro («the action now: T-23 (Cocytus)», oppure «none — no fight, the consoles on `action` are waiting»).
La mente ne ricava il **quadro delle console** del prompt (`[course] intercept(target=T-23,standoff_km=6) until target_lost by captain, 84 s ago || <status> | last: …`), la delega, e — per l'iniziativa —
«le decisioni che il plot lascia aperte» (`Watch.due`: un rilevamento senza scansione, un ostile senza fuoco assegnato, un mirino su un bersaglio sparito). `stations.<id>.supports: [...]` (facoltativo, oggi assente)
restringerebbe i modi offerti per postazione, per consegnare per gradi. Una postazione assente da `stations` resta sugli strumenti vecchi; senza `stations` la mente usa solo gli strumenti di oggi (compatibilità).
`contacts[]` come oggi (`id, class, name?, status, range_km?, bearing_deg, hull_pct…`): da lì la mente prende gli id che deve mandare.

## 5. I comandi che restano (one-shot)

`fire_weapons{weapon,contact_id,salvo}` · `cease_fire` · `launch_decoys` · `active_scan{contact_id}` · `dispatch_damage_control{deck,section,task,priority}` · `route_power{system,percent}` · `vent_heat` ·
`set_alert{level}` · `hail{contact_id,intent,message}` · `end_transmission` · `fleet_request{ship,request,target?}` · `abandon_ship` · `dismiss_visitor` · `standing_orders{orders[]}` · `set_target`.
I comandi che una postazione sostituisce (`set_course`, `set_throttle`, `intercept`, `transit_gate`, `set_shields`, `set_point_defense`, `set_emcon`, `set_radiators`, `holo_display`, `launch_squadron`, `recall_squadron`) la mente
**li nasconde al modello solo per le postazioni presenti nello stato**, ma il gioco deve tenerli accettati (una mente vecchia, `astra.cmd`).

## 6. `context` e delega

Come già in `main`: su ogni `player_text` e `ptt` (giù e su; la mente usa l'ultimo prima della trascrizione) `context = {place, place_name, pawn, in_earshot[], facing, channel{party,open,muted}|null}`. La mente
riduce `in_earshot` agli id che conosce (scarta `deck1`, `sleeper3`…), usa `facing` per chi risponde per primo, decide col router se le parole possono uscire sul canale (**solo** con canale aperto e non zittito).
Come `channel.muted` oggi è sempre falso, la mente lo considera zittito anche quando **comms ha il modo `mute`** (`stations.comms.modes.channel.mode == "mute"`): l'effetto vero lo fa il router, il gioco non deve fare altro.
Estensioni facoltative capite: `channel.kind` (`enemy|fleet|ally|port`, altrimenti dedotto dal plot), `channel.screen`. **Delega**: «Voss, decidi tu» → `station xo delegation{station:"tactical", delegation:"auto"}`;
il gioco la salva (`stations.<st>.delegation`), la rispetta la mente.

## 7. Eventi

Il gioco emette già (`Act`/`Expire` con `report`) `"<postazione>: <testo>"`: la mente li ascolta **tutti** per decidere quando fare un controllo d'iniziativa; con `report:true` l'ufficiale ne parla subito.
Quelli che ci sono e che la mente sa usare: `helm|tactical|sensors: <modo> ended (<perché>): back to <predefinito>` (`Expire`: bersaglio sparito o distrutto, tempo scaduto, l'intercetta è stata interrotta),
`tactical: engaging <nave> (was <id>)` / `no firing solution on <nave> (a bearing only): asking the sensors for a track`, `engineering: heat N%: radiators extended…`, `flight: <sq>'s target <T> is gone: … back on combat air patrol`,
`sensors: new contact …`, `tactical: <T> (<nome>) destroyed`. La nave locale dei test (`local_ship.py`) emette gli stessi testi.

## 8. Richieste al gioco

**Fatte** (`main` 333cb1e, la mente è già allineata): `target: "action"` rivalutato a ogni passo (timone `keep_on_bow`, schermo, scansione; con nessun combattimento il modo aspetta invece di scadere) e `action_target` nello stato; `engage` su `hostiles` come ordine
permanente; `until: time:<s>` che riporta **qualsiasi** aspetto al modo predefinito; `reactor battle_short` vero (800 %, +0,3 %/s di calore, eventi nei due sensi); `ew`/`sigint`/`holo fleet` tolti dalle tabelle.

**Ancora aperte** (nulla blocca la mente):

1. **`Expire` ricolloca solo l'etichetta.** Un `time:<s>` scaduto su `reactor battle_short`, `power`, `emcon`, `holo`… rimette il modo predefinito nello stato ma **non richiama `Enter`**: la nave resta com'era (battle short ancora acceso con il modo `normal`, profilo di potenza
   ancora `combat`, EMCON ancora `silent`). La mente per questo **non manda `time:`** per quei modi (il solo `time:` che manda è `evade`, del timone, dove basta la prua). Se si vuole, in `Expire` chiamare `Enter` sul predefinito (o `SetBattleShort(false)` e simili).
2. **Pagine del datapad**: la mente offre le cinque del gioco; `weapons`, `flight`, `comms` permetterebbero a Tanaka di rispondere a più richieste («mandami lo stato dei caccia»).
3. **`channel open{party}`** imposta il modo senza aprire nulla (l'apertura resta `hail`); va bene, la mente usa solo `mute`/`unmute` — che il gioco non fa rispettare (§6): se lo farà, basta rispettare lo stesso modo.
4. **`engage` con `action`** senza combattimento è rifiutato (`none of those contacts is a live hostile`): la mente non lo offre (per «tutti» c'è `hostiles`).
5. **`evade{pattern}`**: il parametro non è letto (la mente non lo manda). **`engage` su un contatto solo-rilevamento** è accettato (poi chiede ai sensori una traccia): la mente non lo chiede mai.

## 9. Cosa aggiornare in ARCHITETTURA §4 (il testo del gioco è già avanti rispetto al documento)

1. Lo **stato** implementato è `stations.<id> = {officer, delegation, status, modes: {aspetto: {mode, params?, until, set_by, for_s}}, recent[]}` (non `mode/params/until/set_by/since/last_actions` al livello della postazione).
2. Il comando è `{station, aspect?, mode, params?, until?, note?, delegation?, by?}`: **`aspect`** esplicito (o dedotto dalla tabella), **`by` dentro `args`** (è lì che `ApplyCommand` lo legge per `set_by`: `captain|officer|xo|auto|default`).
3. La tabella dei modi è quella del §3 (per aspetto); `flight` ha un aspetto per squadrone; `xo` ha `delegation` con `{station, delegation}`.
4. `until` ha quattro valori; `target_lost` per i modi con bersaglio del timone è ciò che il codice fa sempre (`Expire` → `hold` con report, salvo con `action`: aspetta); `time:<s>` riporta l'aspetto al predefinito (§3, e la nota del §8.1); i predefiniti sono nel §3.
5. `viewscreen` e **`action_target`** a livello di `ship_state`; `zoom` = numero 0,25–8 o `close|max|wide`; `target` = id o `action`; `engage.targets` = id o `hostiles` (ordine permanente).
6. Le richieste ancora aperte del §8.

## 10. Come provarlo

1. Senza la mente: `astra.cmd station {"station":"helm","aspect":"course","mode":"intercept","params":{"target":"T-23","standoff_km":6},"by":"captain"}` e guardare `stations.helm.modes.course` in `/state`.
2. La mente contro il gioco: nel log della mente compaiono `watch check`, `channel open with …, routed (rules|llm, N ms)` e le `station` inviate (aspetto, modo, `by`).
   Attesi: «Voss, fuoco sul Cocytus» → `station tactical engagement engage {targets:[T-23]}` + una riga breve; «una salva sul Cocytus» → `fire_weapons` (nessun modo); «sullo schermo il Cocytus, ingrandisci» →
   `station ops viewscreen target {target, zoom}`; «Voss, solo su mio ordine» → `station xo delegation`; «ferma la nave» → `station helm course {speed_pct: 0}`.
3. Offline, 0 $: `cd mind && .venv/bin/python -m unittest bench.stations_unit bench.stations_server` (93 prove: la classe `WireTest` è l'allarme contro la deriva dal C++), poi con il modello vero
   `-m bench.stations_scenarios --langs it,en` (≈ 0,09 $).
4. Modelli dei ruoli: `mind/astra_mind/models.py`; per cambiarne uno senza toccare il codice: `ASTRA_MODEL_<RUOLO>=modello@provider1,provider2` (`CREW`, `WATCH`, `ROUTER`, `CHATTER`).
