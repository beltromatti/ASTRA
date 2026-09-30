# Contratto delle postazioni — proposta del modulo MENTE-EQUIPAGGIO (v1, 30 settembre 2026)

*Per il lead: ciò che la mente scrive e legge, con i nomi esatti, così che l'esecutore C++ (`AstraStations.*`) e la mente si parlino senza
altro accordo. Coerente con [ARCHITETTURA.md §3–§5](ARCHITETTURA.md); ogni scostamento dal §4 è elencato al §8. Gli identificatori sono in inglese
(sono quelli del codice: `mind/astra_mind/stations.py` è la fonte unica, questo documento ne è la traduzione per chi scrive C++).*

**Stato lato mente.** Tutto ciò che segue è già implementato e provato offline (`mind/bench/stations_unit.py`, `stations_server.py`, `stations_scenarios.py`
contro la nave locale `local_ship.py`, che implementa questo contratto). La mente **rileva** la build: se `ship_state.state.stations` manca usa
gli strumenti di oggi (compat), se c'è usa `station`; per postazione (una build può avere solo `helm` e `tactical`: il resto resta con gli strumenti
vecchi). Se `player_text`/`ptt` non portano `context`, lo ricava dallo stato.

---

## 1. Il comando `station`

`command{id, name: "station", args, by}` → `ApplyCommand`.

```json
{"station": "helm", "mode": "intercept", "params": {"target": "T-23", "standoff_km": 6}, "until": "target_lost", "note": "seguilo a sei chilometri"}
```

| Campo | Tipo | Note |
|---|---|---|
| `station` | `helm` `tactical` `sensors` `ops` `engineering` `comms` `flight` `xo` | l'id della postazione è anche l'id dell'ufficiale (`by`) |
| `mode` | stringa | nomi piatti, univoci in tutto il gioco (§2). Ogni modo appartiene a **una lane** |
| `params` | oggetto | solo i parametri del modo (§2); la mente ha già clampato i numeri e scartato i parametri sconosciuti; il gioco **valida comunque** |
| `until` | `done` · `target_lost` · `order` · `time:<secondi>` | facoltativo: se manca vale il predefinito del modo (§2) |
| `note` | stringa ≤ 160 | il perché in poche parole (per il registro `last_actions` e la storia) |

- **Lane.** Ogni postazione ha una o più *lane*: modalità persistenti **indipendenti** (il tattico ha `engagement`, `shields`, `point_defense`, `missiles`).
  Un modo nuovo sostituisce quello attuale **della sua lane**; le altre lane non si toccano. La lane si ricava dal modo (colonna "lane" del §2);
  per `flight` la lane è lo squadrone (`alpha` `bravo` `drones`, da `params.squadron`).
- **Risposta** (`command_result`): `ok:true` con `detail` = una riga in inglese che dice **com'è la console dopo il cambio**, con i valori veri
  (`"helm: intercept T-23 (standoff 6 km) until target_lost — closing at 310 m/s, 14.2 km, ETA 1:10"`); `ok:false` con la ragione in parole semplici,
  che la mente fa leggere all'ufficiale: `no contact T-99 on the plot` · `T-31 is a bearing only: no firing solution yet` ·
  `weapons interlock: T-01 is not hostile` · `this build's tactical console does not have mode 'weapons_free'`. Un rifiuto non cambia nulla.
- **`by`**: l'id dell'ufficiale (`helm`…), `captain`, oppure `auto`. Va copiato in `set_by` della lane.
- **Bersagli** (`target`, `targets[]`, `leader`): un id di contatto dal plot (`T-23`) **o un selettore** che l'esecutore rivaluta a ogni tick:
  `tactical_target` (il primo bersaglio vivo dell'`engage` del tattico) · `nearest_hostile` · `biggest_threat` (l'ostile che ci minaccia di più: quello che spara,
  poi il più vicino). Un selettore che non risolve (nessun ostile) lascia la lane com'è e riferisce.
- **`until`**: `done` = il modo finisce da solo (virata completata, pagina spinta, scansione conclusa); `target_lost` = il bersaglio è distrutto o sparito dal plot
  (o fuori dai sensori da > 10 s); `order` = finché un ordine non lo cambia; `time:<s>` = scade. Alla fine la lane torna al **modo predefinito** (§2.9)
  con `set_by:"auto"` e l'esecutore emette l'evento del §6.
- **Delega** (`station xo delegation`): vedi §5.

## 2. Le postazioni, i modi, il lavoro del codice

Colonne: **modo** (`parametri`, `?` = facoltativo, `=` predefinito/scelte) · `until` predefinito · **autorità** (`free` = l'ufficiale può impostarlo di sua iniziativa con
delega `auto`; `engaged` = idem ma solo per servire un combattimento in corso; `captain` = solo su ordine del Capitano o ordine permanente — è la mente a
farlo rispettare, il gioco non deve) · **lavoro continuo del codice** a ogni tick.

### 2.1 `helm` — Ferri — lane `nav`

| Modo | Parametri | until | Aut. | Cosa fa il codice |
|---|---|---|---|---|
| `hold` | `speed_pct?` | order | free | annulla ogni inseguimento; mantiene la prua; con `speed_pct` porta la manetta lì (0 = tutta fermo). **In combattimento a nave ferma senza altro ordine: prua sull'azione** (ARCH §4) |
| `course` | `heading_deg`, `mark_deg?=0`, `speed_pct?` | done | captain | vira alla rotta fissa al tasso della nave capitale, poi `hold` |
| `intercept` | `target`, `standoff_km?=6`, `speed_pct?` | target_lost | engaged | come oggi `intercept`: punta il bersaglio (anticipo), chiude fino a `standoff_km`, dentro presenta il fianco e mantiene la distanza |
| `keep_on_bow` | `target` | target_lost | free | **solo assetto**: gira la prua sul bersaglio, la manetta non cambia (il Capitano lo vede dal finestrone) |
| `follow` | `target`, `distance_km?=3`, `side?=astern\|ahead\|port\|starboard` | order | engaged | tiene posizione relativa a una nave (amica o no) |
| `orbit` | `target`, `radius_km?=6` | order | engaged | gira attorno al bersaglio a quella distanza |
| `broadside` | `target`, `side?=port\|starboard\|best`, `range_km?=6` | target_lost | engaged | presenta il fianco scelto (tutte le torrette brandeggiano) e tiene la distanza |
| `evade` | `pattern?=jink\|spiral\|away` | time:30 | free | manovre schivanti (spostamenti casuali / a spirale / via dall'asse della minaccia) |
| `retreat` | `toward?=away\|gate\|fleet\|<id>`, `speed_pct?` | order | captain | rompe il contatto e fugge |
| `formation` | `leader`, `slot?=ahead\|astern\|port\|starboard\|port_quarter\|starboard_quarter` | order | captain | tiene la casella su una nave amica |
| `transit` | `system` | done | captain | come oggi `transit_gate` (corsia d'avvicinamento, poi il campo del Gate) |

`speed_pct` (0–100) è un **tetto** sulla manetta per tutti i modi di movimento. Legacy sostituiti: `set_course`, `set_throttle`, `intercept`, `transit_gate`.

### 2.2 `tactical` — Voss — lane `engagement`, `shields`, `point_defense`, `missiles`

| Lane | Modo | Parametri | until | Aut. | Cosa fa il codice |
|---|---|---|---|---|---|
| engagement | `hold_fire` | – | order | captain | nessun fuoco senza ordine |
| engagement | `return_fire` | – | order | free | **predefinito**: spara solo a chi spara a noi |
| engagement | `weapons_free` | `range_km?` | order | captain | ogni ostile tracciato entro portata (o `range_km`) a piacere |
| engagement | `engage` | `targets[]` (id, selettori o `"hostiles"`), `weapons?[]` (`railguns` `lasers` `missiles` `torpedoes`; predefinito: tutte quelle in portata), `fire?=sustained\|volley\|conserve`, `priority?=ordered\|nearest\|weakest\|biggest_threat` | target_lost | engaged | assegna le armi ai bersagli in ordine di priorità, salve a cadenza, ritarga dentro la lista quando uno cade, **resta assegnato fuori portata e apre da solo** quando entra (come oggi `fire_weapons`); `volley` = una salva per gruppo poi ferma; `conserve` = solo colpi sicuri. Non si può ingaggiare un contatto solo-rilevamento (rifiuto), né un non ostile |
| shields | `shields_balanced` | – | order | free | scudi uniformi |
| shields | `shields_face_threat` | – | order | free | ruota il settore forte verso il fuoco in arrivo, **continuamente** |
| shields | `shields_sector` | `sector=fore\|aft\|port\|starboard\|dorsal\|ventral` | order | free | settore rinforzato fisso |
| shields | `shields_off` | – | order | captain | scudi giù |
| point_defense | `pd_auto` | – | order | free | **predefinito** |
| point_defense | `pd_protect` | `target` (amico) | order | free | la difesa di punto copre prima quella nave |
| point_defense | `pd_off` | – | order | captain | spenta |
| missiles | `missiles_normal` | – | order | free | **predefinito**: come dice `engage.fire` |
| missiles | `missiles_conserve` | – | order | free | risparmia il caricatore |
| missiles | `missiles_saturate` | – | order | captain | svuota le celle in una salva sola per saturare la difesa di punto |

Restano **one-shot** (comandi di oggi): `fire_weapons` (una salva), `cease_fire` (ferma tutto ora, annulla le code), `launch_decoys`. Legacy sostituiti: `set_shields`, `set_point_defense`, `set_target`.

### 2.3 `sensors` — Nair — lane `emcon`, `scan`, `ew`, `sigint`

| Lane | Modo | Parametri | until | Aut. | Cosa fa il codice |
|---|---|---|---|---|---|
| emcon | `emcon` | `level=silent\|restricted\|full` | order | captain | come oggi `set_emcon` (cambia la firma) |
| scan | `scan_passive` | – | order | free | **predefinito**: solo passivi, tiene il quadro |
| scan | `scan_sweep` | `every_s?=30` | order | captain | ping attivo periodico (tutti lo sentono) |
| scan | `scan_focus` | `target` | done | free | scansione mirata continua su un contatto fino a identificarlo o perderlo (evento all'identificazione); su un solo-rilevamento serve a dargli una distanza (incrocio/tempo) |
| ew | `ew_off` / `ew_jam` | `target` (solo `ew_jam`) | order / target_lost | free / captain | disturbo del controllo di tiro di un contatto |
| sigint | `sigint_on` / `sigint_off` | – | order | free | ascolta i datalink del nemico: i suoi ordini di gruppo diventano eventi `sensors: sigint — …` |

One-shot: `active_scan` (un ping, o mirato). Legacy sostituito: `set_emcon`.

### 2.4 `ops` — Tanaka — lane `viewscreen`, `holo`, `datapad`, `damage_control`

Tanaka possiede **lo schermo principale, il tavolo olografico, il datapad e il controllo danni**. La potenza passa a `engineering`.

| Lane | Modo | Parametri | until | Aut. | Cosa fa il codice |
|---|---|---|---|---|---|
| viewscreen | `viewscreen_auto` | – | order | free | **predefinito**: regia automatica (ARCH §5) |
| viewscreen | `viewscreen_forward` | `zoom?` | order | free | vista ottica in avanti |
| viewscreen | `viewscreen_target` | `target`, `zoom?` | target_lost | free | telecamera sul soggetto con zoom; **quando il bersaglio muore o si perde il gioco riporta la lane ad auto** con `set_by:"auto"` e una `note` («T-11 is gone») — la mente non deve rilasciarla |
| viewscreen | `viewscreen_tactical` / `_fleet` / `_sector` / `_damage` / `_off` | – | order | free | come ARCH §5 |
| viewscreen | `viewscreen_comms` | `party?` | order | free | il canale aperto a schermo |
| holo | `holo_tactical` | `range_km?` | order | free | tavolo: battaglia attorno all'Aquila |
| holo | `holo_sector` / `holo_fleet` | – | order | free | mappa del settore / la flotta |
| holo | `holo_ship` | `target` | order | free | una nave in dettaglio |
| datapad | `datapad_push` | `page=status\|contacts\|weapons\|damage\|flight\|orders\|comms\|ship`, `focus?` | done | free | mette una pagina sul datapad del Capitano |
| damage_control | `dc_auto` | – | order | free | **predefinito**: le 4 squadre vanno dove serve di più (incendi, squarci, armi, reattore) |
| damage_control | `dc_priority` | `what=reactor\|weapons\|shields\|sensors\|engines\|life_support\|flight_deck\|fires\|breaches\|casualties` | order | free | orienta le squadre verso quella cosa per prima |

`zoom`: numero (`1`–`49`) **oppure** `"close"` `"wide"` `"max"` (come già fa il gioco; la mente accetta anche `"x12"`). One-shot: `dispatch_damage_control`.
Legacy sostituito: `holo_display`.

### 2.5 `engineering` — Mensah — lane `power`, `heat`, `reactor`

| Lane | Modo | Parametri | until | Aut. | Cosa fa il codice |
|---|---|---|---|---|---|
| power | `power_profile` | `profile=balanced\|offense\|defense\|engines\|sensors\|flight_ops` | order | free | distribuisce il budget del reattore (700 %) per profilo (es. `offense` = armi 130 / scudi 100 / motori 100…: le tabelle le decide il lead) |
| power | `power_custom` | `shields_pct?`, `weapons_pct?`, `engines_pct?`, `sensors_pct?`, `life_support_pct?`, `flight_deck_pct?` (0–150) | order | free | come `route_power` su più sistemi insieme; rifiuta se sfora il budget |
| heat | `heat_auto` | `limit_pct?=70` | order | free | radiatori fuori/dentro e cadenza frenata per restare sotto il tetto |
| heat | `heat_radiators` | `state=extended\|retracted` | order | free | radiatori fissi |
| reactor | `reactor_normal` | – | order | free | **predefinito** |
| reactor | `reactor_battle_short` | – | time:120 | captain | corto circuito di sicurezza: più potenza per 120 s a rischio di cedimento del contenimento (regole al lead) |

One-shot: `route_power` (un sistema), `vent_heat` (sfiato di emergenza). Legacy sostituito: `set_radiators`.

### 2.4b `comms` — Martin — lane `channel`, `listen`

`channel_mute` / `channel_unmute` (la voce del Capitano non esce / esce sul canale aperto; **predefinito** `channel_unmute`) · `listen_off` (**predefinito**) / `listen_fleet` /
`listen_enemy` / `listen_all` (ascolto e traduzione delle intercettazioni: diventano eventi `comms: intercepted — …`). Aprire e chiudere un canale restano `hail` e
`end_transmission` (non sono modi). One-shot: `hail`, `end_transmission`, `fleet_request`.

### 2.6 `flight` — Price — una lane per squadrone (`alpha`, `bravo`, `drones`)

`mission` — `squadron`, `type=cap|escort|strike|recon|ew|sar|hold|recall`, `target?`, `formation?=wedge|line|screen|trail`, `rtb_when?=mauled|winchester|target_dead|never`
· until `done`. **Lancia** lo squadrone o lo riassegna se è in volo (quindi sostituisce `launch_squadron`/`recall_squadron`, che restano accettati); `hold` = resta in ponte,
`recall` = rientra. `rtb_when` dà all'esecutore il criterio di rientro autonomo (evento `flight: … returning`). La CAP resta entro 3 km dall'Aquila.

### 2.7 `xo` — Serra — lane `delegation`

`delegation` — `station=helm|tactical|sensors|ops|engineering|comms|flight`, `level=manual|advise|auto`. Salva il livello in `stations.<station>.delegation`. Nient'altro:
gli ordini permanenti restano il comando `standing_orders{orders:[…]}` che la mente già manda; `set_alert` resta one-shot dell'XO.

### 2.8 Autorità: cosa fa rispettare la mente

Con delega `manual` un ufficiale non imposta modi di sua iniziativa; con `advise` propone e aspetta il «proceda»; con `auto` agisce **tranne** i modi `captain`
(salvo ordine permanente del suo reparto) e sempre tranne `transit`, `retreat`, la delega, `abandon_ship`, aprire/chiudere un canale col nemico. Le richieste del Capitano non hanno filtri.
Il gioco non deve rifiutare per autorità: accetta ciò che arriva (registrando `by`).

### 2.9 Modi predefiniti (dove torna una lane a fine modo) e stato iniziale

`helm.nav=hold` · `tactical.engagement=return_fire`, `shields=shields_balanced`, `point_defense=pd_auto`, `missiles=missiles_normal` · `sensors.emcon=emcon{level:restricted}`,
`scan=scan_passive`, `ew=ew_off`, `sigint=sigint_off` · `ops.viewscreen=viewscreen_auto`, `holo=holo_tactical`, `damage_control=dc_auto` (`datapad`: nessuno) ·
`engineering.power=power_profile{balanced}`, `heat=heat_auto{70}`, `reactor=reactor_normal` · `comms.channel=channel_unmute`, `listen=listen_off` ·
`flight.<squadrone>=mission{type:hold}` · `xo`: nessuna lane (solo `delegation` per postazione, predefinita `auto`).

## 3. Lo stato: `ship_state.state.stations` (ogni ~1 s e prima di un rapporto)

```json
"sim_time_s": 812.4,
"viewscreen": "target: ordered, T-23 (Cocytus), zoom x6",
"stations": {
  "helm": {"officer": "helm", "delegation": "auto",
           "modes": ["hold", "course", "intercept", "keep_on_bow", "follow", "orbit", "broadside", "evade", "retreat", "formation", "transit"],
           "lanes": {"nav": {"mode": "intercept", "params": {"target": "T-23", "standoff_km": 6}, "until": "target_lost",
                             "set_by": "captain", "since": 790.1, "status": "closing on T-23 at 310 m/s, 14.2 km, ETA 1:10"}},
           "last_actions": ["captain: intercept {'target': 'T-23'}"]},
  "tactical": {"officer": "tactical", "delegation": "auto",
               "lanes": {"engagement": {"mode": "engage", "params": {"targets": ["T-23"], "fire": "sustained"}, "until": "target_lost", "set_by": "tactical",
                                        "since": 805.0, "status": "engaging T-23 at 14.2 km (waiting: out of railgun reach), its hull 100%"},
                         "shields": {"mode": "shields_balanced", "params": {}, "until": "order", "set_by": "auto", "since": 0.0, "status": ""}}},
  "…": {}
}
```

- **`lanes`** obbligatorio per le postazioni multi-lane (vedi §8). Una postazione a lane unica può usare la forma piatta di ARCH §4 (`mode`, `params`, `until`, `set_by`, `since`, `status` al livello della postazione): la mente legge entrambe.
- **`since`** e `sim_time_s`: stesso orologio (secondi di gioco); la mente mostra «da N s». **`status`**: una riga in inglese, con i valori veri (velocità, distanza, ETA, scafo del bersaglio…): è ciò che l'ufficiale legge per parlare.
- **`modes`** (facoltativo): i modi che **questa build** supporta per la postazione. Se c'è, la mente restringe l'enum dello strumento e la tabella ai soli modi elencati:
  si può consegnare per gradi (prima `helm`+`tactical`+`ops`, poi il resto). Se manca, si assumono tutti quelli del §2. Una postazione assente da `stations` resta sugli strumenti vecchi.
- **`delegation`**: `manual` `advise` `auto` (predefinita `auto`). **`last_actions`**: gli ultimi 2–4 cambi (`"<by>: <mode> <params>"`).
- **`viewscreen`** (già in `main`): la riga di ciò che c'è sullo schermo principale; la mente la mostra nel quadro delle console e la usa per capire se il canale è «a schermo».
- Restano invariati tutti i campi di oggi (`helm` come stringa, `weapons.*`, `contacts[]`, …): l'avvisatore tattico e le vecchie build li leggono ancora.

## 4. I comandi che restano (one-shot)

`fire_weapons{weapon,contact_id,salvo}` · `cease_fire` · `launch_decoys` · `active_scan{contact_id}` · `dispatch_damage_control{deck,section,task,priority}` ·
`route_power{system,percent}` · `vent_heat` · `set_alert{level}` · `hail{contact_id,intent,message}` · `end_transmission` · `fleet_request{ship,request,target?}` ·
`abandon_ship` · `dismiss_visitor` · `standing_orders{orders[]}`. **I comandi legacy sostituiti** (`set_course`, `set_throttle`, `intercept`, `transit_gate`, `set_shields`,
`set_point_defense`, `set_target`, `set_emcon`, `set_radiators`, `holo_display`, `launch_squadron`, `recall_squadron`) **devono restare accettati**: una mente vecchia o la console `astra.cmd` li usa.
Ciascuno dovrebbe **impostare la lane corrispondente** (`set_by` = chi comanda), così lo stato è unico.

## 5. `context` (gioco → mente) e la delega

Come già in `main` (commit f413615), su **ogni** `player_text` e `ptt` (giù e su; la mente usa l'ultimo prima della trascrizione):

```json
"context": {"place": "bridge|corridors|captains_quarters|main_engineering|mess_hall|crew_berthing|medbay|flight_deck|in_a_falcon|planetside",
            "place_name": "DECK 4 · MESS HALL", "pawn": "on_foot|seated|falcon|pod",
            "in_earshot": ["xo","helm","ops"], "facing": "helm"|null,
            "channel": {"party": "T-21"|"fleet", "open": true, "muted": false}|null}
```

Cosa ne fa la mente (`context.py`, `router.py`): `in_earshot` ridotto agli id che conosce (ufficiali, `chief`, `doctor`, `patientN`, `messN`, `mess_cook`; scarta gli extra come `deck1`);
`facing` = a chi parla per primo in mancanza di un nome; `channel` decide se le parole possono uscire: **solo** se è `open` e non `muted` il router valuta il destinatario;
`heard_s` (da quanto tempo la controparte ha parlato) lo tiene la mente. Estensioni **facoltative** che la mente già capisce: `channel.kind` (`enemy|fleet|ally|port`; se manca lo ricava da `party` e dal plot),
`channel.screen: true` se la controparte è a schermo (la mente lo ricava anche da `viewscreen`).
Il canale è aperto da un `hail`/`transmission: T-xx — …` e chiuso da `end_transmission`/`channel_closed`, come oggi.

**Delega.** Il Capitano la cambia a voce («Voss, decidi tu» → `auto`, «solo su mio ordine» → `manual`, «proponimi le manovre» → `advise`); la mente manda `station{station:"xo", mode:"delegation", params:{station:"tactical", level:"manual"}}`;
il gioco la salva e la riporta in `stations.<st>.delegation`. Non ha altri effetti lato codice: è la mente a rispettarla.

## 6. Eventi che gli esecutori devono emettere (`event{text, report}`)

Il testo comincia **sempre con l'id della postazione** e i due punti (la mente assegna così l'ufficiale). La mente ascolta **tutti** gli eventi (anche `report:false`) per decidere quando fare un controllo
d'iniziativa; con `report:true` l'ufficiale ne parla subito (rapporto, coalescenza come oggi). Regola: `report:true` solo per ciò che il Capitano deve sapere e che non ha causato lui; `false` per i passaggi di routine.

| Evento (testo) | report | Quando |
|---|---|---|
| `helm: <mode> of <T-id> ended, the contact is gone — holding course <hdg>` | true | un `intercept`/`follow`/`broadside`/`orbit`/`keep_on_bow` finisce per `target_lost` (già così per `intercept`) |
| `helm: turn complete, steady on course <hdg> mark <m>` | false | fine di un `course` |
| `helm: <mode> ended — <perché>` | false | `time:<s>` scaduto, `until:done` |
| `tactical: <T-id> (<name>) destroyed` | true | un bersaglio cade (già così) |
| `tactical: engage complete — <ids> destroyed or lost, back to return fire` | false | la lista dell'`engage` è finita |
| `tactical: <T-id> out of reach: <r> km, the railguns reach <R> km` | false | una volta per bersaglio assegnato fuori portata |
| `tactical: weapons free lapses — no hostile in range` | false | `weapons_free` senza bersagli per > 30 s |
| `sensors: new contact <T-id>, bearing <brg>, <emissioni>` | true | nuovo contatto (già così, con «bearing only» se non ha distanza) |
| `sensors: <T-id> identified — <class> <name>, <r> km, bearing <brg>` | true | fine di `scan_focus` per identificazione |
| `sensors: track lost on <T-id>` / `sensors: <T-id> unmasked — a decoy` | true | traccia persa / esca smascherata |
| `sensors: sigint — <cosa dice il nemico ai suoi>` | true | con `sigint_on`, un ordine di gruppo intercettato |
| `ops: viewscreen back to auto — <T-id> is gone` | false | la lane `viewscreen` si rilascia da sola (`set_by:"auto"`) |
| `engineering: heat <n>% and rising — radiators <state>` | true | al superamento di 70 % e 90 % (già così) |
| `engineering: battle short ends — output back to normal` | true | scade `reactor_battle_short` |
| `comms: intercepted — <party>: <testo tradotto>` | true | con `listen_*` |
| `flight: <squadron> mauled: <n> of <m> lost` | true | perdite ≥ 50 % |
| `flight: <squadron> winchester` / `flight: <squadron> returning (<motivo>)` | true / false | fine armi / rientro per `rtb_when` |
| `station: <officer> mode <mode> (<by>)` | false | facoltativo: ogni cambio di lane non dovuto alla mente (es. rilascio automatico) |

## 7. Come provarlo (per il lead)

1. Senza toccare la mente: `astra.cmd station {'station':'helm','mode':'intercept','params':{'target':'T-23','standoff_km':6}}` e guardare la riga `stations.helm.lanes.nav` nello stato.
2. La mente contro il gioco: avvia il gioco; nel log (`Saved/Logs/astra-mind.log`) compaiono `watch check`, `channel open with …, routed (rules|llm, N ms)` e le `station` inviate. Il banco:
   `tools/play.py say "Tattico, fuoco sul Cocytus"` → atteso un `command station tactical engage {targets:[T-23]}` e una riga breve dell'ufficiale;
   «una salva sul Cocytus» → `fire_weapons` (nessun modo); «sullo schermo il Cocytus, ingrandisci» → `station ops viewscreen_target{target, zoom}`; «Voss, solo su mio ordine» → `station xo delegation`.
3. Offline, senza gioco: `cd mind && .venv/bin/python -m unittest bench.stations_unit bench.stations_server` (0 $), poi `-m bench.stations_scenarios --langs it,en` (~0,08 $).
4. Modelli dei ruoli: `mind/astra_mind/models.py`; per cambiarne uno senza toccare il codice: variabile `ASTRA_MODEL_<RUOLO>=modello@provider1,provider2` (`CREW`, `WATCH`, `ROUTER`, `CHATTER`).

## 8. Cosa cambia rispetto ad ARCHITETTURA §4 (elenco esplicito)

1. **Postazioni a più lane.** §4 ha un `mode` per postazione; tattico, sensori, ops, ingegneria, comunicazioni e volo hanno modalità indipendenti che convivono (scudi ≠ fuoco ≠ difesa di punto). Lo stato ha `lanes{lane:{mode,params,until,set_by,since,status}}`; la forma piatta resta valida per `helm`.
2. **Nomi dei modi piatti e univoci**, con il prefisso della lane dove non è la lane principale (`shields_face_threat`, `pd_protect`, `viewscreen_target`, `scan_focus`, `heat_auto`…) invece di «shields: face_threat». Il comando resta `{station, mode, params, until?, note?}`.
3. **Selettori di bersaglio** (`tactical_target`, `nearest_hostile`, `biggest_threat`): lasciano lavorare il codice senza richiamare il modello (l'helm tiene la prua su ciò che spara il tattico).
4. **`speed_pct`** come tetto sulla manetta di tutti i modi di movimento del timone.
5. **`until`** con quattro valori (`done`, `target_lost`, `order`, `time:<s>`) e il **ritorno al predefinito** della lane con `set_by:"auto"` (§2.9).
6. **`modes[]`** nello stato di ogni postazione: annuncio delle capacità della build, per consegnare per gradi.
7. **Ops** possiede anche il controllo danni (`dc_auto`, `dc_priority`); **engineering** possiede la potenza (`power_profile`, `power_custom`) e il calore; `route_power` resta one-shot di engineering.
8. **`comms`**: aprire/chiudere il canale resta `hail`/`end_transmission`; i modi sono solo `channel_mute/unmute` e `listen_*`. **`xo`**: solo `delegation`; gli ordini permanenti restano il comando `standing_orders`.
9. **`flight mission`** porta `formation` e `rtb_when`; una lane per squadrone.
10. **`viewscreen_target.zoom`** = numero o `close|wide|max`; il rilascio a fine bersaglio lo fa il gioco (come da messaggio del lead).
11. **Eventi** con testo fisso e prefisso di postazione (§6), `report` deciso dal tipo.
12. **Estensioni facoltative di `context`**: `channel.kind`, `channel.screen`; `heard_s` non serve al gioco (lo tiene la mente).

Modi con effetto nuovo da progettare lato C++ (non esistono ancora nel gioco): `keep_on_bow` (assetto solo), `follow`, `orbit`, `formation`, `evade`, `retreat`, `shields_face_threat`, `pd_protect`, `missiles_*`,
`scan_sweep`, `scan_focus`, `ew_*`, `sigint_*`, `heat_auto`, `reactor_battle_short`, i profili di potenza, `dc_priority`, `holo_ship`, `datapad_push`, i criteri `rtb_when`. Quelli con equivalente in un comando di oggi
(`intercept`, `course`, `transit`, `emcon`, `hold_fire`≈`cease_fire`, `weapons_free`≈un ordine permanente eseguito dal codice, `mission`≈`launch_squadron`, `shields_sector`≈`set_shields`) si possono agganciare subito.
