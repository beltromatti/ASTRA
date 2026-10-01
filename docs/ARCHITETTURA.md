# ASTRA — Architettura, moduli e contratti (v1.1, 30 settembre 2026)

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

## 1bis. Come nascono le intelligenze di ASTRA (filosofia di progetto)

La parola chiave del progetto è **intelligenza**, ovunque. Le entità di ASTRA (ufficiali, comandanti, piloti, equipaggio,
il regista) devono comportarsi come persone intelligenti. I modelli di oggi lo sono: si parte da lì.

1. **L'intelligenza la danno i modelli, guidati da buoni prompt e dal contesto giusto. Non i filtri nel codice.**
   Nessun taglio delle loro parole, nessuna riscrittura con espressioni regolari, nessuna lista di parole «vietate»,
   nessun controllo automatico di «verità» su ciò che dicono. Queste reti di sicurezza diventano un imbuto: si aggiusta un
   caso e se ne rompe un altro. Se un agente sbaglia si corregge il suo prompt (ruolo, carattere, dottrina, maniere),
   il contesto che riceve, il disegno dei suoi strumenti o il modello scelto per quel ruolo.
2. **Percezione = ciò che quella persona potrebbe percepire.** Ognuno riceve ciò che il suo ruolo vede e sente: le
   console della sua postazione (l'equipaggio di plancia, insieme, le console della plancia), ciò che si dice nella stanza
   e sui canali che ascolta, la nebbia di guerra. Mai la verità nascosta: il vero stato del nemico, i piani del regista,
   ciò che nessun sensore mostra. Il nemico vede con i sensori della sua parte. Niente barare.
3. **Azione = gli strumenti che quella persona avrebbe.** Un ufficiale agisce dalla sua console (modalità `station`,
   azioni istantanee), la stessa interfaccia che userebbe un giocatore umano seduto lì. Un comandante agisce dando ordini
   dalla sua dottrina (ordini di gruppo), un PNG con le azioni del suo mestiere. Nessun comando «di servizio» fuori dal
   ruolo.
4. **Il codice è il corpo e la fisica, non il giudizio.** Il codice fa:
   - la simulazione;
   - il lavoro continuo che un agente ha avviato (gli esecutori delle postazioni, come un pilota automatico);
   - le automazioni che una nave vera ha (difesa di punto, esche contro una salva, esercitazioni). Ognuna ha un
     ufficiale che la «possiede», è annunciata e si può revocare;
   - la meccanica della conversazione (chi ha fisicamente la parola, la priorità assoluta della voce del Capitano);
   - la rete.

   Il codice non decide cosa dice qualcuno, se un rapporto vale ancora la pena, a chi erano rivolte le parole del
   Capitano.
5. **Ripensare, non scartare.** Quando il tempo passa (un rapporto rimasto in coda dietro una plancia occupata), l'agente
   lo ripensa con lo stato di adesso: lo dice aggiornato, lo cambia o lo lascia cadere. Nessun codice lo scarta per età.
6. **Si valuta ciò che gli agenti fanno, non come lo scrivono.** I banchi controllano i fatti:
   - quale strumento è stato chiamato, con che bersaglio;
   - l'esito nella simulazione;
   - la latenza e il costo.

   Per la qualità del parlato si gioca (il lead prova nel gioco vero) o si usa un modello giudice. Mai espressioni
   regolari sul testo.
7. **Il modello giusto per ogni ruolo.** Tetto di costo DeepSeek V4.1 Flash, modelli più piccoli e veloci dove bastano.
   Per il lavoro di routine dei PNG, cervelli di codice con memoria; un modello quando qualcuno ci parla. Poche chiamate,
   buone: in un solo turno l'agente agisce e parla; un secondo turno solo per leggere i risultati quando servono.
8. **Caso per caso.** Questo è un principio, non un dogma. Per ogni meccanismo ci si chiede: è giudizio (→ il modello,
   col prompt, il contesto e gli strumenti) o meccanica (→ il codice)?

Conseguenze sul codice che c'è (da fare, vedi [PIANO.md](PIANO.md)):
- `agent.py`: via i filtri sulle battute. Da togliere:
  - `_tighten`, che taglia le battute lunghe;
  - `_deconsole`, che riscrive i nomi delle modalità;
  - i «signorsì» trattenuti per lista di parole;
  - le euristiche che riconoscono «ragionamenti» e «strumenti» nel testo;
  - il recupero della prosa come battuta.

  Si parla solo con `speak`. Se il modello non ha parlato, gli si chiede di rispondere (un nuovo turno), senza
  indovinare dal testo.
- `router.py`: con un canale aperto, a decidere se le parole del Capitano erano anche per l'interlocutore esterno sarà un
  modello veloce con il contesto (chi c'è sul canale, cosa ha appena detto, dove guarda il Capitano). È il giudizio
  dell'ufficiale alle comunicazioni. Sparisce lo strato di regole in cinque lingue. L'equipaggio sente comunque tutto (è
  nella stanza) e decide da sé se rispondere.
- `speech.py`: le battute rimaste troppo a lungo in coda vengono ripensate dall'agente (per il punto 5) invece di
  scadere per soglia. Resta meccanica la priorità assoluta del Capitano sul canale audio.
- Gli agenti che ricevono lo stato intero della nave lo ricevono perché è la somma delle console della plancia. Il prompt
  di ogni ufficiale mette davanti la sua console.

## 2. I moduli

| Modulo | Cosa contiene | File principali | Chi |
|---|---|---|---|
| **SIM / GUERRA** | navi, armi, proiettili, sensori, guerra elettronica, danni fisici per sezione e faccia, gruppi di battaglia, squadriglie, flotte, scenari, la scala (velivoli a istanze, liste condivise: SCALA), i beat del regista in gruppi di battaglia e l'apertura che cresce (GUERRA.md §9) | `AstraBattleSubsystem.*`, `AstraWar*.*`, `data/war/*`, `AstraShipSubsystem.*`, `AstraCrewRoster.*` | GUERRA e SCALA uniti; lead (CAMPAGNA §9); poi CAMPAGNA (lo strato strategico) |
| **STAZIONI** | il modello delle postazioni e i loro esecutori continui (§4) | `AstraStations.*` (nuovo) | lead |
| **VISTA** | schermo principale, sovrimpressioni AR, tavolo olografico, console, datapad, HUD del caccia | `AstraScreensSubsystem.*`, `AstraHoloTable.*`, `AstraViewscreen.*` (nuovo) | lead |
| **GIOCATORE** | input, personaggio, controller, interazione, prima persona | `AstraInput.*`, `ASTRACharacter.*`, `ASTRAPlayerController.*` | lead |
| **BANCO** | banco di prova per giocare da terminale, misure | `AstraHarness.*`, `tools/play.py`, `tools/perf/*` | lead |
| **MENTE-EQUIPAGGIO** | agenti di plancia, strumenti delle postazioni, iniziativa, router e acustica, collaborazione fra ufficiali | `mind/astra_mind/{agent,crew,tools,router}.py`, la loro colla in `server.py` | unito il 30/9; ora lead |
| **VOCE** | riconoscimento, sintesi, turni di parola, sottotitoli (lato mente e lato gioco: `AstraVoiceWave.*`) | `mind/astra_mind/{speech,stt,tts,audio_in,voice_casting}.py`, `docs/protocollo_voce.md` | unito il 30/9; ora lead |
| **MENTE-GUERRA** | ammiraglio e comandanti del Mandato, capitani alleati che parlano, l'XO con `group_order`, regista v2 (a scala di flotte dal 2/10) | `mind/astra_mind/{war_minds,director,enemy,war}.py`, banco `tools/war.py mind` (GUERRA.md §8–9) | unita 1/10; ora lead |
| **VOLO** | la rete di volo: CAG, capi squadriglia, gregari, Chief of the Deck; l'ala di Eagle | `mind/astra_mind/flight_minds.py`, l'ala in `AstraBattleSubsystem`/`AstraWarCraft` (VOLO.md) | unito il 2/10 |
| **ARTE-PLANCIA** | la plancia v3 (geometria, materiali, console, poltrone), da Blender | `art/blender/bridge*.py`, `tools/ue_scripts/build_bridge*.py` | unito il 30/9 |
| **ARTE-NAVI / VFX** | navi v3 con pezzi di rottura e decalcomanie di danno (ARTE-NAVI, unita il 1/10); armi, motori, scudi, esplosioni, rotture nel gioco (VFX: poi, sul contratto di GUERRA `ConsumeDeathEvents` / `GetDamageView`) | `art/blender/shipgen3.py`, `art/blender/ship3_*.py`, `tools/ue_scripts/*ship*v3*`, `make_fx_*.py` | ARTE-NAVI unita; VFX poi |
| **UMANI** | personaggi realistici, animazioni, labiale, IA dei PNG | `Source/ASTRA/AstraCrew*`, `tools/ue_scripts/make_crew_*` | poi |
| **NAVE-INTERA** | la pianta dell'Aquila (compartimenti, porte, grafo dei percorsi), il kit dei corridoi e delle stanze, i ponti; F4.3: la pianta di una nave vera e i piani delle altre classi | `data/ship/aquila_plan.json`, `art/blender/ship_*`, `tools/ue_scripts/build_ship_interior.py`; lato gioco `AstraShipPlan.*` (lead) | NAVE e NAVE-2 unite; **NAVE-3** (agente, in corso) |
| **ASCENSORI** | turboascensori e navetta della Spine veri (vetture che si muovono, porte, pannelli, voce, passeggeri di VITA) | `AstraLift*.*`, `art/blender/ship_lift.py`, `tools/ue_scripts/build_lifts.py` | **ASCENSORI** (agente, in corso) |
| **DISTRUZIONE** | i danni dentro l'Aquila per compartimento: falle, campi di contenimento, fuoco e fumo, paratie, potenza, persone, il Capitano; gli effetti vicino a lui | `AstraDamage*.*`, `tools/damage.py` (DISTRUZIONE.md) | unito il 2/10 |
| **ABBORDAGGI** | prima persona con armi, danno alle persone, marine e squadre d'abbordaggio del Mandato con IA di squadra, l'abbordaggio ricevuto | da definire nel ramo (brief `docs/brief/ABBORDAGGI.md`) | **ABBORDAGGI** (agente, F5.1, in corso) |
| **VITA** | le ~560 persone dell'Aquila sul grafo dei percorsi: turni, lavori, pasti, sonno, posti di combattimento, squadre di riparazione, feriti; corpi vicino al Capitano; memoria in codice, un modello quando il Capitano ci parla | `AstraLife*.*`, `data/ship/aquila_life.json`, `tools/life.py` | unita il 30/9; ora lead (NAVE-3 ne aggiorna i dati) |
| **PRESTAZIONI** | impostazioni di resa, risoluzione, upscaling, profili, menu SETTINGS, prove di durata | `Config/*`, `AstraSettings.*`, plugin MetalFX, `tools/soak.py` | lead (METALFX unito il 1/10) |

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

Comando unico **`station`**: `{station, aspect?, mode, params?, until?, note?, delegation?, by?}` → imposta la modalità
di un **aspetto** della postazione (il tattico ne ha quattro: ingaggio, scudi, difesa di punto, missili; il volo uno per
squadriglia); `aspect` si può omettere quando il nome del modo basta a dedurlo; `by` (`captain|officer|xo|auto|default`)
dice chi l'ha dato. La risposta dice cosa è cambiato. Le azioni istantanee (una salva, un'esca, un saluto) restano
comandi a sé. Nello stato (`ship_state.state.stations`, implementato in `AstraStations.cpp`):

```json
{"helm": {"officer": "helm", "delegation": "auto",
          "status": "KEEP ON BOW Cocytus at 22.4 km · heading 077 mark 3 · 288 m/s (throttle 60%)",
          "modes": {"course": {"mode": "keep_on_bow", "params": {"target": "T-23"}, "until": "target_lost",
                               "set_by": "captain", "for_s": 42}},
          "recent": ["course keep_on_bow: keep on bow Cocytus, 27.0 km (bow on Cocytus)", "…"]}, "…": {}}
```
Accanto a `stations`: `action_target` (il contatto di cui si occupa la battaglia ora: il bersaglio del tattico, altrimenti
l'ostile più vicino) e `viewscreen` (la riga di cosa c'è sullo schermo principale).

`until`: `done` (lo decide la modalità) · `target_lost` · `order` (finché non cambia l'ordine) · `time:<s>` (poi l'aspetto
torna al suo modo predefinito, con i suoi effetti). `delegation`: `manual` (agisce solo sugli ordini) · `advise` (propone e
aspetta «proceda») · `auto` (agisce entro gli ordini permanenti e informa; il codice ha anche i suoi **riflessi**: Alpha in
pattuglia quando il nemico si avvicina, esche contro le salve, potenza di combattimento — mai sopra un modo dato dal
Capitano o da un ufficiale). Predefinita: `auto`.

Bersagli speciali: `target: "action"` (timone `keep_on_bow`, schermo `target`, sensori `focus`) segue la battaglia e
viene rivalutato a ogni passo; `engage {targets: ["hostiles"]}` è un ordine permanente su ogni nave ostile (la migliore a
portata, prima chi ci spara; mai un inseguimento; senza ostili aspetta).

| Postazione (ufficiale) | Modalità | Lavoro continuo del codice |
|---|---|---|
| **helm** (Ferri) | `hold` · `course{heading_deg, mark_deg, speed_pct}` · `intercept{target, standoff_km}` · `keep_on_bow{target}` · `follow{target, distance_km, side}` · `orbit{target, radius_km}` · `broadside{target, side, range_km}` · `evade{pattern}` · `retreat{toward}` · `formation{leader, slot}` · `transit{system}` | tiene rotta e distanza, insegue, presenta il fianco, schiva; **iniziativa predefinita: a nave ferma in combattimento, la prua sull'azione** (il Capitano vede la battaglia dal finestrone), salvo ordine contrario |
| **tactical** (Voss) | `engagement`: `hold_fire` · `return_fire` · `weapons_free{range_km}` · `engage{targets[], weapons[], fire: sustained/volley/conserve}`; `shields`: `balanced` · `face_threat` · `sector{…}`; `point_defense`: `auto` · `protect{id}` · `off`; `missiles`: `conserve` · `saturate` | assegna le armi ai bersagli secondo la priorità, salve a cadenza, ruota gli scudi verso la minaccia, difesa di punto |
| **sensors** (Nair) | `emcon{silent/restricted/limited/full}` · `scan{passive/sweep{every_s}/focus{target}}` (guerra elettronica e intercettazioni: più avanti, con la fase F2) | classifica i contatti, mantiene il quadro, smaschera le esche, chiede triangolazioni |
| **ops** (Tanaka) | `viewscreen{auto/forward/target{target, zoom}/tactical/fleet/sector/comms{party}/damage/off}` · `holo{tactical/sector/ship{id}}` · `datapad{push{page: overview/contact/damage/fleet/orders, focus}}` · `damage_control{auto/priority{what}}` | lo **schermo principale** e il **tavolo olografico** seguono l'azione (regia automatica, §5); smista le squadre di riparazione |
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
- **La memoria è una sola (16 GB)**: al massimo 2 commandlet contemporanei per agente (una simulazione della guerra
  grande arriva a 1,5 GB); le compilazioni UE sono limitate a 4 processi per tutti
  (`~/Library/Application Support/Unreal Engine/UnrealBuildTool/BuildConfiguration.xml`, `MaxParallelActions`: un
  clang su un modulo UE prende 0,6–1,4 GB). Il 1/10 quattro simulazioni più una compilazione a 10 processi hanno
  portato lo swap a 9 GB e fermato l'editor del lead.
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
