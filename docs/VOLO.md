# VOLO — le voci del ponte di volo (la rete di volo)

*Documento del modulo VOLO (2026-10-01). Come funziona la rete di volo, cosa dice il gioco e cosa fa la mente, come si prova e cosa misura. I nomi nel gioco
sono in inglese; il documento in italiano. Vedi anche il brief [brief/VOLO.md](brief/VOLO.md), [GUERRA.md](GUERRA.md) §6 (il contratto delle squadriglie) e §8
(le menti di guerra), [ARCHITETTURA.md](ARCHITETTURA.md) §1bis (il principio delle intelligenze).*

## 1. In breve

Le squadriglie esistevano già nella guerra (Alpha: Falcon, Bravo: Hammer, i droni Wasp), ma le raccontava solo Price, l'ufficiale di volo in plancia. Adesso le
persone del ponte di volo hanno voce, carattere e memoria: il **CAG** (Lt. Cmdr. Ada «Hex» Kovac), i capi di **Alpha** e **Bravo** con i loro gregari e il
**Chief of the Deck** (il capo del ponte di volo). Sono una mente a sé, `FlightMinds` (`mind/astra_mind/flight_minds.py`), accanto all'equipaggio e a `WarMinds`:

- **Parlano quando succede qualcosa a loro**: un lancio, il primo contatto, i caccia nemici abbattuti, una perdita, un siluro, un rientro, un riarmo; poche righe radio
  nella lingua del Capitano (le notizie sono quelle del gioco: eventi `flight: ...`). Price resta il coordinatore in plancia: ciò che la rete racconta, lui non lo
  ripete (l'evento non va al turno di rapporto dell'equipaggio).
- **Il Capitano parla con loro**: Comms (Martin) apre il canale di volo (`hail` flight), che è sempre vivo in un cockpit e di persona sul ponte di volo; il router
  decide cosa delle sue parole esce sul canale (come per la rete della flotta); chi è stato chiamato risponde e agisce con `mission`, gli ordini della console di volo
  (CAP, scorta, attacco, rientro...), decidendo lui come farlo nel suo mestiere.
- **Il Capitano in volo** (Falcon, callsign Eagle): due Falcon di Alpha escono dai tubi e volano la sua ala come **Eagle 2** ed **Eagle 3** (C++: sono veri aerei della
  simulazione); parlano di ciò che vedono, colpiscono e subiscono. Il controllore resta Price.
- **Costo**: un ruolo modello piccolo (`flight`, tetto DeepSeek V4 Flash), una sola chiamata per tutto il cast, solo sulle notizie forti: **0,05 $ per ora di battaglia**
  misurato su una battaglia compressa (tetto teorico 0,12 $/ora, regolatore di spesa oltre).

L'intelligenza è nel prompt, nel contesto e negli strumenti, mai in filtri di codice sulle parole (§1bis): il codice porta i fatti, tiene l'orologio, controlla
l'autorità degli ordini e li passa al gioco; non decide cosa dice nessuno. Con `ASTRA_FLIGHT_MINDS=0` la rete è spenta e Price riferisce come prima.

## 2. File

| File | Cosa |
|---|---|
| `mind/astra_mind/flight_minds.py` | **nuovo**: il cast, la tabella delle notizie, il prompt, gli strumenti, `FlightMinds` (cadenza, pulsazioni, ordini, memoria) |
| `mind/astra_mind/models.py` | il ruolo `flight` (DeepSeek, 340 token, temperatura 0,6, ripiego `chatter`) |
| `mind/astra_mind/context.py` | il canale `flight` (`Channel.kind`, `parse(..., flight_net=)`, la descrizione per l'equipaggio) |
| `mind/astra_mind/router.py` | la frase sul canale di volo nella situazione del router (le parole per Price restano in plancia) |
| `mind/astra_mind/crew.py` | i doveri di Price e la regola per tutti: la rete di volo non è loro, Martin la apre e dice solo le parole del Capitano |
| `mind/astra_mind/tools.py` | `hail` conosce `flight` |
| `mind/astra_mind/server.py` | l'aggancio: voci radio, intercetta `hail`, notizie, turno del Capitano, sessione, `_flight_say/_execute/_unanswered` |
| `Source/ASTRA/AstraBattleSubsystem.h/.cpp`, `AstraWarCraft.cpp` | **C++ (non compilato)**: l'ala di Eagle e gli eventi nuovi (§7) |
| `mind/bench/flight_unit.py` (62 prove), `flight_server.py` (17) | offline: modello finto, nessuna rete |
| `mind/bench/flight_live.py` (32 scene), `flight_crew_live.py` (9) | dal vivo, pochi centesimi (§9) |

## 3. Il cast

Sette persone, una sola chiamata al modello per tutte (il prompt le conosce tutte e sceglie chi parla). I nomi non sono nel ruolino dell'equipaggio (468 cognomi e
76 nominativi: lo controlla una prova), le voci sono del catalogo Pocket TTS e registrate nello stadio vocale come voci radio.

| id (`speaker`) | Persona | Posto | Voce | Carattere |
|---|---|---|---|---|
| `cag` | Lt. Cmdr. Ada «Hex» Kovac | CAG (Commander Air Group) | `vera` | dura con i suoi perché li vuole a casa; frasi corte e secche; contabile dei piloti |
| `alpha_lead` | Lt. Elias «Pilgrim» Calder | capo di Alpha (8 Falcon) | `bill_boerst` | tranquillo, quasi annoiato, più calmo quanto peggio va |
| `alpha_2` | Ens. Mina «Mistral» Takeda | gregaria di Pilgrim; **Eagle 2** | `fantine` | giovane, veloce quando ha paura, esatta quando conta |
| `alpha_3` | Lt. Dov «Tern» Ashkar | gregario veterano; **Eagle 3** | `rafael` | secco, laconico, «ho il tuo sei» è una promessa |
| `bravo_lead` | Lt. Lucas «Ox» Brannock | capo di Bravo (7 Hammer) | `juergen` | lento, ruvido e gentile; i siluri sono «pesci», gli Hammer «i camion» |
| `bravo_2` | LtJG Amani «Cobalt» Rhodes | la migliore con un siluro | `azelma` | esatta, timida alla radio |
| `deck_chief` | CPO Hollis «Deck» Teague | capo del ponte di volo | `stuart_bell` | burbero, paterno, conta tutto due volte |

Ordina una squadriglia solo il suo capo (o il CAG, che le comanda tutte); i gregari, la gregaria e il Chief non danno ordini. Una squadriglia perduta («lost: no aircraft
left») non ha più voce se non quella del CAG; un gregario abbattuto in volo esce dalla rete fino alla fine di quel volo.

## 4. Quando parlano

### 4.1 Le notizie (gli eventi del gioco)

La tabella è `_KINDS` in `flight_minds.py` (una riga per formato; un formato nuovo è una riga). «Presa» = la voce è della rete e il turno di rapporto dell'equipaggio
**non** la riceve; il resto va all'equipaggio come sempre.

| Evento del gioco (testo) | Presa | Chi la dice (decide il modello) | Tace? |
|---|---|---|---|
| `flight: <sq> squadron airborne, N Falcons on CAP` | sì | il Chief, o il capo | può tacere |
| `flight: alpha squadron engaged a Harpy at N km` (**nuovo**, C++) | sì | il capo di Alpha, in due parole | può tacere |
| `flight: <sq> squadron has lost N ... killed/ejected ...` | sì | il capo della squadriglia (il CAG se è un'ora nera) | **mai muta** |
| `flight: bravo squadron torpedo run on T-21: N torpedoes away` | sì | il capo di Bravo | **mai muta** |
| `flight: <sq> squadron recovered, N of M aboard, rearming` | sì | il Chief | **mai muta** |
| `flight: <sq> squadron rearmed, N ... ready on the flight deck` | sì | il Chief | **mai muta** |
| `tactical: N Harpies splashed, M left` | sì | il capo dei caccia | mai muta in plancia; con l'ala può tacere (il gregario l'ha già detto) |
| `flight: search and rescue ...` | sì | il CAG | può tacere |
| `flight: Eagle's wing joined ...` (**nuovo**) | con l'ala | Eagle 2 / Eagle 3 si presentano | **mai muta** |
| `flight: Eagle 2 engaged a Harpy at N km` · `splashed a Harpy` · `is hit — hull N%` (**nuovi**) | con l'ala | il gregario | può tacere |
| `flight: Eagle 3 is down — the pilot ejected, ...` (**nuovo**) | con l'ala | l'altro gregario, il CAG | **mai muta** |
| `flight: launching Alpha ...` · `recalling Alpha` (i riflessi di Price) | no | Price | — |
| `flight: Eagle is down / recovered / flew into ... / has landed`, `the Captain ...` | no (ma sveglia l'ala) | Price e il XO | — |
| `flight: ... recon has identified ...` | no | Sensors | — |
| `damage report: ... deck 9 ...` (un incendio sul ponte di volo) | no (sveglia la rete) | Operations ripara; il Chief può dirlo | può tacere |

«Mai muta» è una scelta di **strumenti**, non un filtro: la pulsazione che contiene una di queste notizie non ha lo strumento `stay_quiet` (resta `say`, `mission`,
`remember`) e il messaggio dice che quella notizia si chiama a voce. Prima di questo il modello, con la lavagna che già mostrava il fatto, taceva su una perdita o un
rientro una volta su due; ora no. Tutto il resto lascia il silenzio come risposta normale.

### 4.2 La cadenza (meccanica, con un bilancio)

- Le notizie si accumulano e si leggono **insieme** dopo 2,5 s dall'ultima (al più 6 s dalla prima), e non più spesso di una pulsazione ogni **14 s**; con l'ala di Eagle
  7 s (un combattimento non aspetta). Nient'altro sveglia la rete: niente orologio, niente giro periodico.
- Le parole del Capitano sulla rete non aspettano nessuna soglia: la pulsazione parte subito e risponde per prima; se il Capitano parla a qualcun altro mentre una
  pulsazione è in corso su notizie, quella si ferma e le notizie si rileggono dopo.
- Il regolatore: oltre 0,03 $ spesi negli ultimi dieci minuti (circa 0,18 $/ora) la distanza tra le pulsazioni raddoppia.
- Una pulsazione che non finisce in 22 s non dice nulla (le notizie restano nel registro della rete); se era per il Capitano, le sue parole vanno a Price.

### 4.3 Cosa vede il modello a ogni pulsazione

Il prompt di sistema (stabile, circa 4.000 token: la cache del fornitore lo copre) ha il cast, quando si parla, come si parla, come rispondere al Capitano, il Capitano in
volo, la memoria. Il messaggio (circa 1.000 token) ha: il registro della rete (cosa è stato detto, fatto, ascoltato: anche le righe di Price), la lavagna (dove sta il
Capitano, le squadriglie, la console di volo con la delega, il quadro dei sensori, il ponte di volo, i caduti), ciò che ciascuno ricorda, le notizie nuove con la loro età,
le parole del Capitano se ci sono, la lingua e il registro di una buona riga radio (con segnaposto tra parentesi quadre, mai fatti da copiare). Non vede mai la vista del
Mandato (`_mandate`): una prova lo verifica.

## 5. Il canale di volo: il Capitano parla con loro

- **Aprirlo**: «Martin, apri il canale di volo». Comms usa `hail` con `contact_id: "flight"`; la mente intercetta il comando (non va al gioco: lì `hail` conosce i
  contatti e la flotta), segna la rete aperta e porta le parole del Capitano (`message`) sulla rete. `end_transmission` la chiude (solo se il canale vivo era questo).
- **Sempre viva**: in un cockpit (la radio del Falcon è la rete), di persona sul ponte di volo (il Chief è lì), e per 25 s dopo che uno della rete ha chiamato il
  Capitano (la sua risposta è per loro).
- **Il router decide per primo** (`router.for_party`, 2,5 s): cosa delle parole del Capitano esce sul canale. L'equipaggio sente tutto e sa che la rete è viva. Le parole
  per Price, il timoniere o un altro ufficiale restano in plancia anche a rete aperta: la rete tace (`stay_quiet`) e il ponte le esegue.
- **Parole intere alla rete → nessun turno per il ponte**: se tutto ciò che il Capitano ha detto è uscito sulla rete, il turno dell'equipaggio (una chiamata al modello
  per non dire nulla) non parte; con parole miste l'equipaggio riceve una nota («le parole X sono uscite sulla rete: non dite e non fate nulla su quelle; il resto è
  vostro»), così nessuno le ripete (Price non rilancia l'ordine di un pilota, Comms non lo racconta).
- **Il Capitano è sempre risposto**: se una pulsazione sulle sue parole finisce senza una voce (un ordine eseguito e nemmeno una parola, una correzione muta, una risposta
  vuota) c'è un giro in più, con ciò che la console ha fatto, perché risponda chi era stato chiamato; solo il silenzio dichiarato (`stay_quiet`: le parole non erano per
  la rete) lo lascia senza risposta. Se il modello fallisce o non arriva, le sue parole vanno a Price (`on_unanswered`): mai perse.
- Le righe di Price sono ascoltate dalla rete (non ripete ciò che ha detto) e le righe della rete finiscono negli eventi dell'equipaggio («over the radio, X: ...»).

## 6. Gli ordini: `mission`

Un capo (o il CAG) ordina con `mission {by, squadron, type, target, reason}`: `cap`, `escort`, `strike`, `ew`, `recon`, `sar`, `hold`, `recall`, con un bersaglio che
sia un contatto vivo sul piano. È **lo stesso ordine della console di volo** (`station` flight, `mission`): passa da `stations.normalize/to_wire` e arriva al gioco come
comando `station`, con `by` captain (se è la risposta al Capitano) o officer (di sua iniziativa). Il codice controlla:

- **l'autorità**: un capo ordina la sua squadriglia, il CAG tutte, nessun altro (il capo di Alpha che riceve «Bravo, attacca» dice di chi è, o lo fa il CAG);
- **la delega della console** (di sua iniziativa): `manual` = solo su ordine del Capitano, `advise`/`auto` come ammette la console, o un ordine permanente del Capitano;
- **la risposta del gioco**: una riga detta nello stesso giro dell'ordine è trattenuta finché la console non ha risposto; se rifiuta (nessun tale contatto, squadriglia in
  riarmo, nessun velivolo) la riga composta prima («Scorto il T-77») non si dice mai e chi ha dato l'ordine legge il perché e risponde una volta, con una riga e un ordine
  corretto se c'è modo.

Il modello decide **come** (un capo a cui è detto «copri il Vigilant» sceglie scorta o pattuglia leggendo il piano); un ordine che non si può fare o che sprecherebbe la
squadriglia (un attacco contro una cintura di difesa di punto, dei caccia mandati a fare il lavoro dei bombardieri) riceve una riga che lo dice e cosa propone.

## 7. Il Capitano in Eagle: l'ala

**C++ (non compilato, §11)** — `AstraWarCraft.cpp`, `AstraBattleSubsystem.*`:

- Quando il Capitano esce dalla catapulta in un Falcon (non dal pianeta), `LaunchPiloted` chiama `StartEagleWing`: se sul ponte ci sono Falcon di Alpha (fino a due)
  escono dai tubi della nave 3 s e 4,5 s dopo di lui, come **Eagle 2** ed **Eagle 3**. Sono velivoli normali della squadriglia (`Squadron` = Alpha) con una radio (`Radio`),
  in un volo di scorta di cui il Capitano è il capo: missione `escort` sul suo Falcon (tengono lo slot, combattono i banditi vicini a lui, rientrano feriti, sotto il 40% di
  scafo, o quando lui non c'è più). Con il Capitano che lascia il Falcon (`EndPiloted`, `LeavePiloted`, la sua distruzione) l'ala si scioglie (`EndEagleWing`: niente più
  radio) e, non avendo più il Falcon da scortare, la logica già esistente di `ThinkCraft` li manda a casa (`recall`).
- Gli eventi (`WingNotes`, `Destroy`): `flight: Eagle's wing joined — Eagle 2 and Eagle 3, two Falcons of Alpha, are on the Captain's wing`; `flight: Eagle 2 engaged a
  Harpy at 2.4 km` (una chiamata a bersaglio, almeno dieci secondi tra l'una e l'altra); `flight: Eagle 2 splashed a Harpy` (il merito va a chi ha colpito per ultimo:
  `LastHitBy`, impostato in `ApplyHitLump`); `flight: Eagle 3 is hit — hull 38%` (sotto il 70% e sotto il 35%); `flight: Eagle 3 is down — the pilot ejected, search and
  rescue is on the way` (subito, non nel rapporto di squadriglia dodici secondi dopo). Il resto (rapporto di perdita della squadriglia) non cambia.

**Mente**:

- `flight: Eagle's wing joined` forma l'ala: Alpha 2 e Alpha 3 diventano **Eagle 2 / Eagle 3** (il nome sulla rete e sullo stadio vocale), parlano a 7 s di distanza, e
  alla fine del volo (un evento `flight: Eagle is down / recovered / ...`, o il Capitano che non è più in un Falcon) tornano ai nomi di Alpha.
- Gli eventi `flight: Eagle ...` del Falcon del Capitano restano a Price e al XO (non della rete); la rete li legge e sveglia l'ala. Il controllore è Price: chiama il
  quadro (banditi per ore, distanza, avvicinamento) dai sensori; un gregario **non lo rilegge mai** al Capitano: dice cosa fa lui («tally, è mio», «ingaggio», «sono colpito»).
- Un gregario abbattuto esce dalla rete fino alla fine del volo (si è eiettato: la ricerca e soccorso lo recupera).
- **Limite dichiarato nel prompt**: nessuno strumento guida i gregari (in volo si può chiedere loro solo di parlare); se il Capitano ordina una manovra («rompi a sinistra»)
  il gregario dice cosa **fa** (sull'ala, ingaggia chi ti minaccia) e, dove diverge dall'ordine, lo dice in una parola; non dice mai di virare perché glielo hai detto.

## 8. Memoria

`remember` conserva ciò che una persona si porterebbe dietro per settimane: una promessa che il Capitano ha fatto o rotto, un suo ordine che è costato vite o le ha
salvate, un gesto gentile o crudele, la perdita di qualcuno vicino a quella persona; mai un abbattimento, un lancio o una perdita di routine, mai un dettaglio inventato.
Fino a 8 ricordi a persona (le promesse durano più a lungo), salvati con la storia in `Saved/Campaign/flight.json`, riletti a «continue», azzerati a una campagna nuova.
Tornano al modello sotto «What they remember»: possono affiorare quando conta, mai essere recitati.

## 9. Le prove e le misure

Comandi (dalla cartella `mind`, con il venv del progetto):

```
.venv/bin/python -m unittest bench.flight_unit bench.flight_server            # 62 + 17 prove, senza rete e senza costo
.venv/bin/python -m bench.flight_live --repeat 3 --cap 0.06                   # le 32 scene dal vivo (circa 0,03 $)
.venv/bin/python -m bench.flight_live --battle --only none --cap 0.05         # la battaglia compressa: pulsazioni, righe, costo all'ora (circa 0,01 $)
.venv/bin/python -m bench.flight_crew_live --budget 0.06                      # equipaggio + router + rete insieme, gioco finto (circa 0,006 $)
.venv/bin/python -m bench.flight_live --only loss_alpha --debug               # una scena, con ciò che il modello ha restituito
```

La chiave OpenRouter si legge dall'ambiente o dal `.env` del checkout principale (mai stampata). I banchi dal vivo costano pochi centesimi; `--cap` li ferma.

**Offline** (modello finto, gioco finto): la classificazione delle notizie, il cast, i prompt, la cadenza (burst, intervallo, bilancio), le voci, il silenzio, gli
strumenti senza silenzio per le notizie che si dicono, gli ordini (autorità, delega, rifiuto e correzione, console che non risponde), l'ala (nomi, scioglimento, gregario
abbattuto), la memoria, il canale (apertura, chiusura, vivo dove sta il Capitano), la risposta garantita al Capitano, e col vero `Mind`: l'equipaggio non riceve ciò che
la rete dice, Price non ripete, le parole intere alla rete non fanno turno, una rete che fallisce passa le parole a Price e un difetto nella rete non toglie la
nave all'equipaggio. Suite offline completa del `mind` (npc, stazioni, guerra, regista, voce, volo): 260 prove, tutte verdi.

**Dal vivo** (DeepSeek V4.1 Flash via OpenRouter, 32 scene × 3 ripetizioni nell'ultima corsa: 96/96 come atteso, con una sola voce nelle scene dove ne serve una;
la partenza era 83/96 prima di togliere il silenzio alle notizie che si dicono e di garantire la risposta al Capitano; il resto sta nella lettura delle righe, che si
fa a occhio, mai con un'espressione regolare):

| Cosa | Risultato |
|---|---|
| Perdita, siluri, rientro, riarmo, abbattimenti in plancia | parlano sempre (3/3), una sola voce quasi sempre: il capo di Alpha, il capo di Bravo, il Chief |
| Un lancio, il primo contatto, un incendio sul ponte, un soccorso | a volte una riga, a volte niente: il modello giudica |
| Parole per il timoniere sulla rete aperta | la rete tace 3/3; per Price 2/3 (con il router vero non arrivano alla rete: `flight_crew_live`, 9 scene su 9 come previsto) |
| Ordine al capo («copri il Vigilant», «attacca l'Acheron», «CAG, richiama tutti») | l'ordine giusto arriva alla console 3/3, con una riga di risposta; il capo non ordina la squadriglia altrui (lo fa il CAG) |
| Ordine impossibile (T-77 non sul piano; Bravo in riarmo) | rifiutato dalla console e detto: «T-77 non è sul plot», «ancora al riarmo, quarantacinque secondi», mai «lancio» a vuoto |
| In volo con l'ala | Eagle 2 / Eagle 3 si presentano, abbattono, sono colpiti, sono giù; sul pod il capo dell'ala copre il Capitano; non rileggono il quadro di Price |
| Lingue | italiano, inglese, spagnolo, francese, tedesco |

**Latenza**: la prima chiamata di strumento arriva a 0,4–1,0 s dall'inizio della pulsazione (mediana 0,5 s, al più 2,1 s con un ordine e la sua correzione); a questo si
aggiunge la sintesi vocale (non misurata qui).

**Costo**: una pulsazione costa 0,15–0,5 m$ (circa 5.000 token in ingresso, l'80% in cache, circa 100 in uscita). Battaglia compressa (23 notizie in 700 s di gioco): 20
pulsazioni, 18 righe, 3 silenzi, 0,0094 $ → **0,049 $ per ora di quella battaglia**; il caso peggiore a un'ora di fuoco continuo con una pulsazione ogni 14 s è circa
0,12 $/ora, sotto il tetto di 0,15; oltre 0,18 $/ora il regolatore raddoppia la distanza. Una frase del Capitano tutta per la rete costa il router (0,03 m$) e una pulsazione
(0,2–0,5 m$) e risparmia il turno dell'equipaggio (0,5–1 m$). **Sviluppo del modulo: circa 0,23 $** (tetto 0,3). Con l'equipaggio (0,76 $/ora) e le menti di guerra (0,02-0,17 $/ora) il totale tipico resta sotto 1 $/ora; nel caso peggiore
di tutti insieme è vicino a 1 $/ora, e il regolatore di spesa della rete di volo raddoppia la distanza tra le pulsazioni quando spende troppo.

## 10. Limiti noti

- **Il C++ non è compilato né provato**: scritto copiando i lanci di `TickSquadrons` e le convenzioni vicine, verificato a lettura su ogni nome e firma; non è mai stato
  eseguito (l'incarico non permette la compilazione). Se il gioco non compila o l'ala non esce, si guarda lì (`StartEagleWing`, `TickEagleWing`, `WingNotes`, `Destroy`).
- Nessun comando muove i gregari di Eagle (in volo la rete parla, l'ala combatte per scorta); non portano ordini «tutti ai tuoi lati» né rispondono a manovre.
- Le persone del cast sono fisse e non sono legate al ruolino dei 60 piloti: i loro nomi (e il fatto che i gregari siano «immortali» salvo un evento di abbattimento)
  sono del cast; le perdite di squadriglia nominano i piloti del ruolino come dice l'evento.
- Il gioco non emette eventi per il carburante, per l'ordigno residuo o per l'appontaggio di un singolo velivolo: la rete parla di ciò che il gioco dice (il prompt
  vieta di inventare numeri, contatti, piloti, carburante, danni).
- Il primo contatto non c'è per Bravo (i bombardieri non combattono) né per i droni in caccia.
- Il modello sbaglia qualche volta (parole per Price eseguite se arrivano alla rete, una riga in più del CAG dopo un rientro, «Ponte:» al posto di «Deck:» in italiano);
  con un buon router queste non arrivano al gioco o non pesano.
- Non è provato nel gioco vero con la grafica: lo prova il lead.

## 11. Integrazione (per il lead)

1. **Unire il ramo** `worktree-agent-a6a7b4b6fde9d0b0a` in main: nessun conflitto (simulata con `git merge-tree` contro main c4b9edb). Modifica file condivisi in modo
   stretto: `server.py` (aggancio), `crew.py` (doveri di Price e una regola), `context.py`, `router.py`, `tools.py`, `models.py` (un ruolo); i benchmark degli altri moduli
   non cambiano (suite offline completa verde).
2. **Compilare il C++** (editor chiuso: `Engine/Build/BatchFiles/Mac/Build.sh ... -WaitMutex`). Tre file: `AstraBattleSubsystem.h/.cpp`, `AstraWarCraft.cpp`. Possibile
   frizione di unione con SCALA (`AstraWarCraft.cpp`, `AstraBattleSubsystem.*`) e con DISTRUZIONE (`ApplyHitLump`: una riga, `To.LastHitBy = SourceId;`).
3. **Nessuna configurazione**: il ruolo `flight` è in `models.py`; `ASTRA_FLIGHT_MINDS=0` spegne la rete. Nessun asset da importare (le voci sono del catalogo).
4. **Provare nel gioco** (con `tools/play.py say "..."` o a voce): *«Martin, apri il canale di volo»*, poi *«Alpha Lead, copri il Vigilant»* e *«CAG, com'è la
   situazione?»*; in battaglia: perdite, siluri, rientri e abbattimenti parlano da soli; salire su un Falcon dalla catapulta e controllare `flight: Eagle's wing joined ...`
   dopo circa 5 s e le due ali sulla `plot`; parlare dal cockpit («Eagle 2, resta con me»); abbatterli per vedere `Eagle 3 is down`.
5. **Da aggiungere** nei documenti del lead: una riga in `ARCHITETTURA.md` §2 (modulo VOLO, la rete di volo: `flight_minds.py`) e in `STATO.md`.

**Richieste fuori dai miei file**: (a) compilare e provare il C++; (b) un difetto già in main, non mio: `Mind._crew_say` è definito due volte in `server.py` (circa
righe 355 e 796): la seconda nasconde la prima, quindi `memory.hear(speaker, text)` per le righe degli ufficiali non gira mai (la rete di volo usa la seconda); (c) se vuoi
che i piloti dell'ala siano gli stessi del ruolino, serve un'API `FAstraCrewRoster` per assegnare un pilota a un velivolo (oggi i gregari sono del cast e non muoiono per
il ruolino); (d) opzionale: un evento `flight: <sq> squadron landed N aircraft` per singolo appontaggio, se si vuole la voce del Chief a ogni recupero parziale.
