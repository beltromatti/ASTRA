# ASTRA — Architettura, moduli e contratti (v1, 30 settembre 2026)

Questo documento è il riferimento tecnico per chi sviluppa ASTRA: io (lo sviluppatore principale, "il lead") e gli
agenti di supporto che lavorano in parallelo su moduli indipendenti. Descrive gli strati del gioco, i moduli con i loro
file e proprietari, i contratti fra i moduli (i punti in cui si parlano) e il modo di lavorare. Il piano (cosa facciamo e
in che ordine) è in [PIANO.md](PIANO.md); lo stato giorno per giorno in [STATO.md](STATO.md).

## 1. Gli strati

```
 GIOCATORE ── voce / tastiera / sguardo ──┐
                                          ▼
 ┌──────────────────────── PRESENTAZIONE (Unreal) ────────────────────────┐
 │ interni e navi · VFX · schermo principale · tavolo olografico ·        │
 │ console delle postazioni · datapad · HUD del caccia · audio e voci     │
 └──────────────▲─────────────────────────────────────────▲───────────────┘
                │ legge lo stato                          │ battute, audio
 ┌──────────────┴──────── SIMULAZIONE (Unreal, C++) ──────┴───────────────┐
 │ la verità: navi, armi, sensori, danni, equipaggio (ruolino), guerra   │
 │ un unico ingresso per gli ordini: ApplyCommand(nome, argomenti JSON)  │
 └──────────────▲──────────────────────────────▲──────────────────────────┘
                │ modalità, azioni                │ eventi, istantanee
 ┌──────────────┴──── CERVELLI DI CODICE (C++) ──┴───────────────────────┐
 │ esecutori delle postazioni (timone, tiro, sensori, energia, danni,     │
 │ volo, schermo) · IA tattica delle navi e dei caccia · IA dei PNG        │
 │ girano a ogni tick: fanno lavorare la nave anche senza parole           │
 └──────────────▲─────────────────────────────────────────────────────────┘
                │ WebSocket (JSON + audio)
 ┌──────────────┴──────────── MENTI (Python, mind/) ──────────────────────┐
 │ ufficiali (agenti che impostano le modalità e parlano) · router ·      │
 │ comandanti nemici e alleati · regista della guerra · memoria ·         │
 │ voce: riconoscimento, sintesi, turni di parola                          │
 └────────────────────────────────────────────────────────────────────────┘
```

Regole che valgono ovunque:
1. **La simulazione dice la verità.** Le menti non inventano fatti: leggono istantanee ed eventi, agiscono solo con i
   comandi. Ogni comando è eseguibile da chiunque abbia l'autorità: il Capitano, un ufficiale, un'IA di codice, in futuro
   un altro giocatore in rete.
2. **Due velocità.** Il lavoro continuo lo fa il codice a ogni tick (tenere la prua sul bersaglio, tirare a cadenza,
   ruotare gli scudi verso la minaccia); le menti decidono le intenzioni (le modalità) e parlano. Un ufficiale non deve
   "chiamare" il modello per ogni colpo: imposta "ingaggia il Cocytus finché non cade" e il codice lo esegue.
3. **Costo sotto controllo.** Ogni chiamata a un modello ha un motivo, un budget e un modello scelto per quel ruolo
   (tetto: DeepSeek V4.1 Flash; modelli più piccoli dove bastano). Niente richieste duplicate su due provider.
4. **Portabilità.** Codice di gioco multipiattaforma; ciò che è solo Mac sta dietro `#if PLATFORM_MAC` con un'alternativa
   portabile (Windows) nello stesso contratto. Niente asset che esistono solo su una macchina.
5. **Pronto per la rete.** Stato autorevole in simulazione, comandi tipizzati, conoscenza per osservatore
   ([MULTIGIOCATORE.md](MULTIGIOCATORE.md)): quello che scriviamo oggi deve poter girare su un server domani.

## 2. I moduli

| Modulo | Cosa contiene | File principali | Chi |
|---|---|---|---|
| **SIM** | navi, armi, proiettili, sensori, guerra elettronica, danni, squadriglie, flotte | `AstraBattleSubsystem.*`, `AstraShipSubsystem.*`, `AstraCrewRoster.*` | lead |
| **STAZIONI** | il modello delle postazioni e i loro esecutori continui (§4) | `AstraStations.*` (nuovo) | lead |
| **VISTA** | schermo principale, sovrimpressioni AR, tavolo olografico, console, datapad, HUD del caccia | `AstraScreensSubsystem.*`, `AstraHoloTable.*`, `AstraViewscreen.*` (nuovo) | lead |
| **GIOCATORE** | input, personaggio, controller, interazione, prima persona | `AstraInput.*`, `ASTRACharacter.*`, `ASTRAPlayerController.*` | lead |
| **BANCO** | banco di prova per giocare da terminale, misure | `AstraHarness.*`, `tools/play.py`, `tools/perf/*` | lead |
| **MENTE-EQUIPAGGIO** | agenti di plancia, strumenti delle postazioni, iniziativa, router e acustica, collaborazione fra ufficiali | `mind/astra_mind/{agent,crew,tools,router}.py`, la loro colla in `server.py` | agente di supporto |
| **VOCE** | riconoscimento, sintesi, turni di parola, sottotitoli (lato mente) | `mind/astra_mind/{speech,stt,tts,audio_in,voice_casting}.py` | agente di supporto |
| **MENTE-GUERRA** | regista, comandanti nemici e alleati, gerarchie di flotta | `mind/astra_mind/{director,enemy,war,finale,loss}.py` | poi |
| **ARTE-PLANCIA** | la plancia v3 (geometria, materiali, console, poltrone), da Blender | `art/blender/bridge*.py`, `tools/ue_scripts/build_bridge*.py` | agente di supporto |
| **ARTE-NAVI / VFX** | navi v3 con pezzi di rottura, armi, motori, scudi, esplosioni | `art/blender/shipgen*.py`, `tools/ue_scripts/make_fx_*.py` | poi |
| **UMANI** | personaggi realistici, animazioni, labiale, IA dei PNG | `Source/ASTRA/AstraCrew*`, `tools/ue_scripts/make_crew_*` | poi |
| **NAVE-INTERA** | generatore della pianta dell'Aquila, ponti, cunicoli, vita di bordo | `data/ship/*`, `art/blender/ship_*` | poi |
| **PRESTAZIONI** | impostazioni di resa, risoluzione, upscaling, profili | `Config/*`, eventuale plugin | lead |

Il lead possiede l'integrazione (collegare i moduli, `ApplyCommand`, il protocollo) e **tutte le prove nel gioco vero**:
sulla macchina c'è un solo editor e una sola GPU.

## 3. Protocollo gioco ↔ mente (WebSocket `ws://127.0.0.1:8765`)

Messaggi JSON (più audio binario). Quelli esistenti restano validi; i nuovi sono marcati **v2**.

Gioco → mente:
- `hello{client}` · `ship_state{state}` (istantanea, ~1 s; subito prima di un rapporto) · `event{text, report}`
- `player_text{text, lang?, context}` e `ptt{down}` → la mente trascrive e produce `transcript{text, lang}`
- **v2** `context` accompagna ogni parola del Capitano: `{place: "bridge"|"quarters"|…, in_earshot: [id…],
  facing: id|null, channel: {party, open, muted}|null, pawn: "on_foot"|"seated"|"falcon"|"pod"}` — chi sente davvero
  (distanza, pareti, radio), a chi sta guardando il Capitano, se c'è un canale aperto e con chi.
- `command_result{id, ok, detail}`
- **v2** `stations{...}` dentro `ship_state.state.stations`: lo stato di ogni postazione (§4).

Mente → gioco:
- `command{id, name, args, by}` → `ApplyCommand`
- la voce: vedi `docs/protocollo_voce.md` (modulo VOCE): battuta mostrata quando parte l'audio, durata attesa,
  annullamento esplicito.
- `status{...}`, `transcript{...}`, `story_card{...}` e gli altri già in uso.

## 4. Il modello delle postazioni (contratto v1)

Ogni postazione di plancia è un **agente con una console vera**: ha una modalità persistente (l'intenzione in corso),
parametri, una condizione di fine, un registro delle azioni. Il codice la esegue a ogni tick; l'ufficiale (la mente) la
imposta, la cambia di sua iniziativa quando la delega lo permette, e ne riferisce. La stessa interfaccia la useranno un
giorno il Capitano o un altro giocatore seduti a quella console.

Comando unico **`station`**: `{station, mode, params, until?, note?}` → imposta la modalità; la risposta dice cosa è
cambiato. Le azioni istantanee (una salva, un'esca, un saluto) restano comandi a sé. Nello stato (`stations`):

```json
{"helm": {"officer": "helm", "mode": "intercept", "params": {"target": "T-23", "standoff_km": 6},
          "until": "target_lost", "set_by": "captain", "since": 812.4, "delegation": "auto",
          "status": "closing on T-23 at 310 m/s, 14.2 km, ETA 1:10", "last_actions": ["…"]}, "…": {}}
```

`until`: `done` (lo decide la modalità) · `target_lost` · `order` (finché non cambia l'ordine) · `time:<s>`.
`delegation`: `manual` (agisce solo sugli ordini) · `advise` (propone e aspetta «proceda») · `auto` (agisce entro gli
ordini permanenti e informa). Predefinita: `auto`.

| Postazione (ufficiale) | Modalità | Lavoro continuo del codice |
|---|---|---|
| **helm** (Ferri) | `hold` · `course{heading_deg, mark_deg, speed_pct}` · `intercept{target, standoff_km}` · `keep_on_bow{target}` · `follow{target, distance_km, side}` · `orbit{target, radius_km}` · `broadside{target, side, range_km}` · `evade{pattern}` · `retreat{toward}` · `formation{leader, slot}` · `transit{system}` | tiene rotta e distanza, insegue, presenta il fianco, schiva; **iniziativa predefinita: a nave ferma in combattimento, la prua sull'azione** (il Capitano vede la battaglia dal finestrone), salvo ordine contrario |
| **tactical** (Voss) | `engagement`: `hold_fire` · `return_fire` · `weapons_free{range_km}` · `engage{targets[], weapons[], fire: sustained/volley/conserve}`; `shields`: `balanced` · `face_threat` · `sector{…}`; `point_defense`: `auto` · `protect{id}` · `off`; `missiles`: `conserve` · `saturate` | assegna le armi ai bersagli secondo la priorità, salve a cadenza, ruota gli scudi verso la minaccia, difesa di punto |
| **sensors** (Nair) | `emcon{silent/limited/full}` · `scan{passive/sweep{every_s}/focus{target}}` · `ew{off/jam{target}}` · `sigint{on/off}` | classifica i contatti, mantiene il quadro, smaschera le esche, chiede triangolazioni |
| **ops** (Tanaka) | `viewscreen{auto/forward/target{id, zoom}/tactical/fleet/comms{party}/damage/sector/off}` · `holo{tactical{range_km}/sector/ship{id}/fleet}` · `datapad{push{page, focus}}` · `damage_control{auto/priority{what}}` | lo **schermo principale** e il **tavolo olografico** seguono l'azione (regia automatica, §5); smista le squadre di riparazione |
| **engineering** (Mensah) | `power{profile | custom{…}}` · `heat{auto/radiators{extended/retracted}}` · `reactor{normal/battle_short}` | ripartisce l'energia, gestisce il calore, coordina la sala macchine |
| **comms** (Martin) | `channel{open{party}/close/mute/unmute}` · `listen{fleet/all/enemy}` | tiene i canali, inoltra le richieste della flotta, traduce le intercettazioni |
| **flight** (Price) | per squadriglia: `mission{type: cap/escort/strike/recon/ew/sar/hold/recall, target, formation}` | lanci, formazioni, recuperi, coordinamento col ponte di volo |
| **xo** (Serra) | `standing_orders` · `delegation{station, mode}` | coordina, consiglia, prende il comando quando il Capitano è altrove |

Ordini una tantum e ordini continui: li distingue l'ufficiale dal senso della frase («una salva sul Cocytus» = azione;
«fuoco sul Cocytus» = `engage` finché non cade; «seguilo» = `intercept`/`follow` finché non cambia l'ordine). Se è
davvero ambiguo sceglie la lettura più naturale e lo dice in poche parole, oppure chiede.

## 5. Lo schermo principale e la regia

- Uno schermo olografico davanti al finestrone (trasparente quando è spento: resta la vista vera). Mostra una
  **telecamera vera** (i sensori ottici della nave: `SceneCapture` puntata sul soggetto, con lo zoom) e una
  **sovrimpressione tattica** come l'HUD del caccia ma più ricca: riquadri e nomi dei contatti (fazione, classe, distanza,
  scafo e scudi se noti), bersaglio agganciato, missili in volo, vettori, frecce per ciò che è fuori campo.
- **Regia automatica** (codice, modalità `auto`): sceglie il soggetto per priorità — ordine esplicito del Capitano o di
  Tanaka · il bersaglio del tattico · minacce in arrivo · l'evento più forte degli ultimi secondi (un'esplosione, una
  nave colpita) · l'ammiraglia nemica · la vista di prua — con inquadrature minime di qualche secondo e passaggi puliti.
- Tanaka può fissare una modalità (a voce: «sullo schermo il Cocytus», «ingrandisci», «tattico», «la flotta») e la
  rilascia quando il motivo finisce (bersaglio perso, tempo scaduto, «torna normale»).
- Anche il finestrone può mostrare i riquadri AR sui contatti visibili attraverso il vetro.

## 6. Come lavoriamo in parallelo

- **Un agente di supporto = un modulo**, con una specifica scritta dal lead (file assegnati, obiettivi, prove richieste).
  Al massimo tre alla volta. Definizione: `.claude/agents/astra-dev.md` (modello Sonnet, sforzo massimo).
- Ogni agente lavora in un **worktree git suo** (`.claude/worktrees/<nome>`, ramo `worktree-<nome>`), fa commit lì e
  non tocca `main`. Il lead rivede, prova nel gioco, unisce, e rimanda i difetti all'agente finché il modulo è perfetto;
  poi l'agente viene chiuso e ne parte un altro sul modulo successivo.
- **Solo il lead avvia l'editor, il gioco, le misure e il pacchetto** (una GPU, un editor). Gli agenti provano offline:
  test unitari, simulazioni scritte, Blender senza interfaccia con rendering di anteprima, la mente contro la nave locale
  (`mind/astra_mind/local_ship.py`) con messaggi finti.
- I contratti (questo documento, `docs/protocollo_voce.md`, lo schema di `ApplyCommand`) cambiano solo con il lead.
- I file condivisi (`server.py`, `ASTRA.Build.cs`, `Config/*`) si toccano il meno possibile e ogni modifica va
  elencata nel rapporto finale.
- Gli asset `.uasset` non si fondono: li produce uno script (Blender → FBX → `tools/ue_scripts/*`), che il lead esegue.

## 7. Il banco di prova (giocare da terminale)

`tools/play.py` guida il gioco avviato con `-astra_harness` (solo build non Shipping): tasti veri, sguardo, ordini
scritti, comandi, screenshot con l'interfaccia, e la **cronologia** di ciò che accade (battute, rapporti, comandi,
parole del Capitano) con il tempo di gioco. È il modo in cui il lead gioca, prova ogni modulo e misura l'esperienza.
Esempio: `tools/play.py launch --nomind` · `walk fwd 2` · `look 30 -5` · `say "Timoniere, prua sul Cocytus"` ·
`watch 20` · `shot plancia`.
