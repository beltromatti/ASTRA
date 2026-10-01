# La vita a bordo — modulo VITA

*Documento del modulo VITA (2026-10-01). I nomi nel gioco sono in inglese; il documento in italiano. Vedi anche
[ARCHITETTURA.md](ARCHITETTURA.md) §1bis (come nascono le intelligenze) e [NAVE.md](NAVE.md) (la pianta che le persone
percorrono).*

## 0. In breve

Le 560 persone dell'ASN Aquila (420 marinai, 60 piloti, 80 marines: il ruolino `FAstraCrewRoster`) **vivono sulla pianta
della nave**: dormono nelle brande, mangiano nel Mess Hall, lavorano ai loro posti, corrono ai posti di combattimento
quando suona l'allarme, accorrono sugli incidenti, vanno in Medbay quando sono feriti. Tutte, sempre, ma in due modi:

- **Simulazione leggera per tutti** (`FAstraLifeSim`, codice puro, nessun attore): ogni persona è pensata circa una volta al
  secondo di gioco; costa in media **0,0024 ms a fotogramma** per l'intera nave (misurato a 60 fps su 30 ore di bordo).
- **Corpi veri solo dove c'è il Capitano** (`AAstraLifeBody`, una riserva di al più 40 attori): chi è nei compartimenti
  vicini cammina sui percorsi del piano, le porte si aprono per lui, si ferma al suo posto, si siede al tavolo, dorme nella
  sua branda. Chi si allontana torna alla riserva senza che nessuno lo veda sparire; chi serve non appare mai in vista.

Quando il Capitano parla a qualcuno vicino, **un modello piccolo e veloce** (il ruolo `npc`, DeepSeek V4.1 Flash) interpreta
quella persona dalla sua identità, dal mestiere, da ciò che sta facendo, da ciò che ricorda delle ultime ore e da ciò che
uno del suo reparto potrebbe sapere della nave: risponde, oppure *passa* (le parole erano per un altro).

Principi (ARCHITETTURA §1bis): nessuna coreografia scritta (ciò che una persona fa è funzione di mestiere, ora e stato della
nave, con scarti suoi dal seme); l'intelligenza delle risposte la danno il modello e il contesto, non filtri nel codice; la
percezione è ciò che quella persona potrebbe percepire (nessuna onniscienza).

## 1. I file

| Cosa | Dove |
|---|---|
| Dati: la pianta e le tabelle della vita | `Source/ASTRA/AstraLifeData.*` (carica `data/ship/aquila_plan.json` e `aquila_life.json` su un thread di lavoro) |
| La simulazione (turni, giorno, allarme, squadre, feriti, memoria) | `Source/ASTRA/AstraLifeSim.*` |
| Il sottosistema (orologio, ruolino e danni dalla nave, gestione dei corpi, JSON per le menti) | `Source/ASTRA/AstraLifeSubsystem.*` |
| Il corpo (membro dell'equipaggio che cammina, sta, siede, dorme) | `Source/ASTRA/AstraLifeBody.*` |
| Il banco senza testa (un giorno di bordo, le verifiche) | `Source/ASTRA/AstraLifeSimCommandlet.*` (`-run=AstraLifeSim`) |
| Registro dei camminatori per le porte (documentato, piccolo) | `Source/ASTRA/AstraDoor.*` (`AstraDoors::AddWalker/RemoveWalker/Walkers`) |
| Tabelle della vita: orologio, turni, giorno, reparti, case, svaghi, squadre, posti dei grandi saloni, 84 brande e 84 posti del Mess | `data/ship/aquila_life.json` |
| Strumenti: controllo della copertura, cottura delle brande e dei posti, copia per il gioco, lancio del banco | `tools/life.py` |
| La mente delle persone | `mind/astra_mind/npc.py` (ruolo `npc` in `models.py`, colla minima in `server.py`) |
| Prove della mente | `mind/bench/npc_unit.py`, `npc_server.py` (offline), `npc_live.py` (dal vivo, ~1 centesimo) |

## 2. La giornata di bordo

**L'orologio.** 12 secondi di nave per secondo di gioco: un'ora di bordo sono 5 minuti di gioco, un giorno di bordo due ore;
una traversata della nave (300 m) è meno di un'ora di bordo. Il cammino è in tempo reale mentre l'orologio corre, quindi
ognuno parte *in anticipo* di quanto ci mette (anticipi per il turno e per i pasti, calcolati dalla distanza).
`astra.life.hour <0..24>` rimette tutti dove l'orario li vuole; `astra.life.scale` cambia la velocità.

**I turni.** Red (00–08), Gold (08–16), Blue (16–24), 187 / 187 / 186 persone, bilanciati per reparto (al più 1 di scarto).

**Il giorno di una persona**, in ore dall'inizio del suo turno (tabella `day`): servizio, pasto a metà turno (circa 4 h, ±1),
servizio fino alle 8, un'ora per riprendersi, pasto dopo il turno, tempo libero, sonno da circa 12 h per circa 7,5 h,
risveglio (15–70 s per alzarsi), pasto prima del turno, un poco di tempo libero, in cammino verso il posto. Gli scarti
(j1..j4, durata del sonno, ritardo di risveglio) sono propri di ognuno e vengono dal seme: nessuno mangia o va a letto
nello stesso minuto, e lo stesso seme dà lo stesso giorno (verificato con un hash dello stato).

**Dove.**
- *Casa*: marines e ufficiali nelle cabine, marinai nel Crew Berthing (poi cabine); una branda è di chi ha il turno sveglio
  (le brande sono condivise fra i turni). Le 84 brande sono bake dei rack del Berthing (`tools/life.py bake`).
- *Posto di servizio*: per reparto (12), con quote per tipo di stanza e il peso della stanza (capienza per stato:
  `planned` 1, `built` 2,5, `existing` 3: si trovano più persone dove il Capitano può vederle, ma ogni ponte vive).
  I grandi saloni (Main Engineering, Flight Deck, Medbay, Mess) hanno posti propri (`halls`).
- *Svago*: otto gusti con intensità per persona dal seme (lounge, library, chapel, observation, gym, hydroponics,
  concourse, cabin); va in un posto del tipo vicino a lui e con spazio.
- *Pasti*: nel Mess Hall; se è pieno, a un tavolo di un salone o su una panca; solo se non c'è un posto in tutta la nave,
  in piedi nel salone più vicino (nel banco: 3,5 % dei pasti, nei cambi di guardia).

**La nave parla.**
- *Red alert*: tutti ai posti di combattimento (nel banco il 100 % di 560 entro 5 minuti di gioco), i dormienti si alzano
  (ritardo di risveglio) e corrono. Yellow: i reparti "yellow" tornano al posto. La fine dell'allarme li rimette nel giorno.
- *Incidente* (`FAstraDamage`): la squadra di riparazione è formata da sei persone della damage control, le più vicine e
  sveglie (engineering se sono poche); corrono al passo di corsa (360 cm/s) sul percorso vero del piano; lavorano finché la
  nave dà l'incidente per riparato; poi tornano al loro giorno. Posizione e stato delle squadre (`mustering`, `on the way`,
  `working`) sono nell'istantanea per le menti. Il tempo che serve (`RepairEtaSeconds`) viene dai percorsi veri, non dalla
  linea d'aria: nel banco 15 s stimati contro 14 s, 67 contro 68, 63 contro 70.
- *Feriti* (ruolino, `Status 1`): vanno in Medbay al letto del ruolino (o su una branda), i guariti tornano al servizio;
  i morti escono dalla simulazione e gli amici lo ricordano.

**La memoria** (in codice, compatta): fino a 8 voci pesate per persona (1 passeggero .. 3 indimenticabile; la più debole e
vecchia cade per prima): l'allarme, essere ferito, un amico ferito o morto, essere in sezione quando è scoppiato un incendio
o una falla, la squadra in cui si è lavorato, la dimissione dalla Medbay. Le voci escono come righe inglesi brevi con l'ora
di bordo; la mente le gioca nella lingua del Capitano.

## 3. I corpi

- **Chi ha un corpo.** Fino a 40 (`max_bodies`, più 4 ancora in vista) fra le persone entro 95 m (rilascio a 115 m) e nella
  stessa fascia di altezza (420 cm; in un salone alto, tutta l'altezza). Vince chi è più vicino, con un piccolo vantaggio a
  chi sta davanti allo sguardo del Capitano; chi ce l'ha già lo tiene (isteresi 0,7). Chi sta in stanze non costruite
  (`planned`) non ha corpo; chi è su un posto di un attore del livello (`external`: i letti della Medbay, 7 sdraiati del
  Berthing) è già rappresentato da quello.
- **Nessuno appare in vista.** Un corpo nuovo nasce solo dove il Capitano non guarda (oltre 65° dalla linea di vista), non può
  vedere (una traccia di visibilità trova un muro) o non distingue (oltre 45 m); gli altri aspettano. Alla comparsa del
  Capitano in un posto nuovo (ascensore, dissolvenza) i corpi nascono subito, otto alla volta. Chi non serve più resta finché
  è in vista. Nella prova a piedi del banco: 345 corpi creati, **0 apparsi entro 40 m davanti al Capitano**.
- **La riserva** si scalda un corpo alla volta (mai uno solo per fotogramma, non in un fotogramma già lungo) mentre il
  Capitano è in plancia; in tutto 40 attori. Il gestore gira a 4 Hz, costa 0,03 ms a chiamata (1,9 ms nel peggiore, a un salto).
- **Camminata.** Il corpo percorre il tempo-percorso del piano (stesso passo della persona, anche la corsa a 300–360 cm/s),
  tiene la destra (26 cm) e gira intorno al Capitano e agli altri (rallenta davanti, aggira, dopo 2,5 s forza il passaggio);
  l'animazione segue il passo (`MF_Unarmed_Walk_Fwd`, `Jog`); le porte si aprono per lui (`AstraDoors`).
  In ascensore e nelle scale (tempo, non distanza) il corpo è nascosto: nessuno lo vede dentro.
- **Pose.** In piedi (`MM_Idle` a fase e velocità proprie), seduto al tavolo o alla consolle (le pose procedurali di
  `AAstraCrewMember`), sdraiato in branda. Se parla col Capitano, si gira verso di lui.
- **Pensa poco quando nessuno guarda.** A ogni fotogramma se visto o in parola; altrimenti ogni 0,1 s (in piedi, in cammino)
  o 0,5 s (seduto, sdraiato); le ombre si spengono oltre 14 m; il resto è `OnlyTickPoseWhenRendered` e URO della base.
- **Voce.** Il corpo è un `AAstraCrewMember` con `StationId` `npc<n° del ruolino>`: le righe della mente per quel `speaker`
  escono dalla sua bocca, spazializzate; se non ha un corpo (si è allontanato), escono come voce non in scena.

## 4. La mente delle persone

`mind/astra_mind/npc.py`. Il gioco manda con le parole del Capitano `context.people`: chi è a portata d'orecchio (corpo, muri
e porte compresi), con identità, mestiere, turno, cosa sta facendo e dove, memoria, amici, distanza e se il Capitano li guarda
(`UAstraLifeSubsystem::ListenersJson`). Il server prende al più 3 persone (quella guardata, poi le più vicine, entro 4,5 m)
e fa **una sola chiamata** al modello con: la scena, ogni persona con ciò che *uno del suo reparto* potrebbe sapere della
nave (un cuoco il menù e le notizie della flotta; un ingegnere il reattore e le tavole dei danni; un tecnico dei sensori il
quadro dei contatti; nessuno il piano del nemico) e ciò che si sono detti col Capitano le volte scorse (4 scambi per persona,
salvati in `mind/.cache/npc_talk.json`, azzerati a una campagna nuova).

Il modello decide: **`say`** (una riga per chiamata, al più 3, per una persona elencata) oppure **`pass`** (le parole erano per un
ufficiale, per il computer, per la radio, per tutta la nave, o il Capitano pensava ad alta voce). I nomi degli ufficiali sono
nel prompt. Il codice porta i fatti, apre il turno e tiene il conto: se una persona risponde, **gli ufficiali di plancia non
rispondono** (il loro turno attende il verdetto, 4 s al massimo); se passano o tacciono o sbagliano, il turno della plancia
va avanti subito. Il Capitano che riparla taglia chi stava per rispondere. Niente filtri sulle parole del modello.

**Prova dal vivo** (`bench/npc_live.py`, 16 scene in sei lingue: domande dirette, ordini al timoniere, "computer", "Number
One", la radio, il Capitano che pensa ad alta voce, il piano segreto del nemico, un ordine che una parola non può eseguire):

| Modello | come atteso | prima riga | costo a chiamata |
|---|---|---|---|
| DeepSeek V4.1 Flash (Together, Modal) — **scelto** | 16 su 16 | 0,5 s (max 1,0 s) | 0,22 m$ |
| gpt-oss-120b (Crusoe), stessa richiesta | 15 su 16 | 0,7 s (max 3,7 s) | 0,12 m$ |

Prima dello strumento `pass` e dei nomi degli ufficiali nel prompt entrambi rispondevano a ciò che non era per loro (il
tecnico dei sensori rispondeva al "computer", l'ingegnere a "Number One"). `tool_choice: required` non funziona su gpt-oss
(il provider cade su un altro endpoint e risponde vuoto): si resta su `auto`. Spesa totale delle prove: circa 3 centesimi.

## 5. Prestazioni (misurate)

| Cosa | Numero |
|---|---|
| Tutta la nave, a 60 fps, 30 ore di bordo (540 000 fotogrammi) | media **0,0024 ms**, p99 0,084 ms, p99,9 0,31 ms, peggiore 0,53 ms (un percorso lungo) |
| Un percorso | 0,14–0,16 ms in media, 0,5 ms al peggio (6 700 in 30 ore di bordo: uno ogni 1,3 s di gioco) |
| Gestore dei corpi | 0,03 ms a chiamata (4 Hz), 1,9 ms al salto |
| Corpi | il budget vero: `stat Astra` mostra `Life`, `LifeBodies`, `LifeBody`, `LifeBodyCount`, `LifeWalking` |

I percorsi sono a bilancio di tempo (`RouteBudgetS` 0,12 ms a fotogramma, almeno uno quando qualcuno aspetta; il più vicino
al Capitano per primo): quando suona l'allarme 560 persone si accodano e l'ultima aspetta fino a ~110 s di gioco, senza costo
per i fotogrammi.

## 6. Come si prova

Il banco non apre né editor né gioco (`-nullrhi -unattended`): può girare mentre l'utente lavora.

```
tools/life.py check                          # il file della vita risolve sulla pianta? (nessun motore)
tools/life.py run --scenario day   --hours 30   # un giorno e mezzo: allarme, 4 incidenti, 3 incidenti di prova, feriti e guariti
tools/life.py run --scenario quiet --hours 30 --step 0.0166667   # nessun evento, a 60 fps: il costo a fotogramma
tools/life.py run --scenario walk  --hours 1 --hour 11.5         # un Capitano di prova cammina (Mess, Concourse, Berthing, Medbay, Engineering, Flight Deck)
tools/life.py report Saved/Life/run.json    # il verbale (campioni ogni 5 minuti di bordo)
cd mind && .venv/bin/python -m unittest bench.npc_unit bench.npc_server -v            # offline
cd mind && .venv/bin/python -m bench.npc_live [--model modello@fornitore]              # dal vivo, ~1 centesimo
```

`day` verifica (25 controlli): ognuno ha casa, posto e posto di combattimento; i turni sono bilanciati; ovunque si arriva
(2 240 percorsi, nessuno senza strada); ogni turno prende il ponte e dorme; l'allarme è risposto; i feriti arrivano in
Medbay e i guariti tornano; le squadre vanno a incidenti veri e di prova e arrivano entro 1,3 volte il tempo detto più 15 s;
ognuno mangia i tre pasti; i commensali hanno un posto; nessuno resta bloccato; nessuno resta in una squadra che non c'è
più; l'intera nave costa meno di 0,3 ms; lo stesso seme dà lo stesso giorno. `walk` verifica: la riserva non supera il tetto,
nessuno appare davanti al Capitano, i corpi pensano e stanno dov'è la persona, la lista delle porte è corta, il gestore è leggero.

Comandi nel gioco: `astra.life.info` (orologio, chi fa cosa, corpi, costo), `astra.life.who <numero | parte del nome>` (una
persona, cosa fa e ricorda), `astra.life.hour`, `astra.life.scale`; variabili `astra.life.max_bodies` (-1: il numero del file; 0: nessun corpo, gira solo la simulazione: per vedere cosa costano),
`astra.life.walk_natural` / `jog_natural` (velocità dei cicli di camminata: se i piedi pattinano), `astra.life.lane_cm`,
`astra.life.shadow_m`.

## 7. Integrazione (cosa deve fare il lead)

1. **Il codice si compila da sé**: il sottosistema parte con il mondo (`OnWorldBeginPlay`), carica i dati su un thread di
   lavoro (70–180 ms) e comincia quando il ruolino c'è. Nessun attore da piazzare nel livello. `tools/life.py stage` copia
   `aquila_life.json` in `Content/ASTRA/Data` (già confezionato come file sciolto da `DefaultGame.ini`).
2. **Il contesto delle parole** (`UAstraShipSubsystem::CaptainContext`, dentro `if (Cam && ...)`, dopo `in_earshot`):
   ```cpp
   if (const UAstraLifeSubsystem* Life = GetWorld()->GetSubsystem<UAstraLifeSubsystem>())
   {
       C->SetArrayField(TEXT("people"), Life->ListenersJson(Eye, Look, 6));
   }
   ```
   (`in_earshot` e `facing` già includono i corpi: sono `AAstraCrewMember` con `StationId` `npc<n>`.) Senza questo, la mente
   non sa chi c'è; il resto del suo lavoro è già in `server.py`.
3. **L'istantanea per le menti** (`UAstraShipSubsystem::Snapshot`, prima di `return S;`):
   ```cpp
   if (const UAstraLifeSubsystem* Life = GetWorld() ? GetWorld()->GetSubsystem<UAstraLifeSubsystem>() : nullptr; Life && Life->IsRunning())
   {
       S->SetObjectField(TEXT("life"), Life->SnapshotJson());   // orologio, chi fa cosa, squadre, persone vicine
   }
   ```
   (la mente legge `life.clock` per datare le memorie e, se il contesto non ha `people`, `life.people_near`).
4. **I tempi di arrivo delle squadre**: in `dispatch_damage_control`, il `Travel` della squadra può venire da
   `Life->RepairEtaSeconds(Deck, Section, Id)` (secondi veri sui percorsi) invece della formula: la riparazione comincia
   quando la squadra è lì.
5. **Chi si fa male**: la scelta delle vittime di un colpo può usare `Life->RosterIn(Deck, Section)` (chi è davvero in quella
   sezione, indici del ruolino): i ponti del ruolino sono quelli vecchi, quelli della pianta sono altri.
6. **I posti del livello** (Mess, Berthing, Medbay): `Life->Sim().WhoIsAt(<station id>)` dice chi dovrebbe stare in un posto
   di un attore esistente (`mess1`..., `sleeperK`, `patientN`).
7. **Porte stagne**: quando se ne sigilla una, `Life->Sim().PlanChanged()` rifà i percorsi in corso.
8. **Compilazione unity**: `TagSky` è dichiarato in `AstraViewscreen.cpp:1192` e in `AstraShipSubsystem.cpp:53` (spazio
   anonimo): nello stesso blocco unity non compila. Rinominare uno dei due.

## 8. Limiti noti

- Le scale delle torri sono tempo, non gradini: dentro la torre il corpo è nascosto e riappare sul pianerottolo; i
  pianerottoli non costruiti non hanno corpi (le persone di quei ponti non si vedono).
- I letti della Medbay e i posti dei livelli sono attori del livello: la persona non ha un corpo suo lì. Non ci sono corpi
  sdraiati per i feriti in transito.
- Un solo ciclo di idle e un solo cammino (i Mannequin di Epic) con le uniformi di reparto: la varietà è nei nomi e nei
  tempi, non nei gesti. Niente lavoro animato al posto di servizio.
- Gli attori `AstraWalker` del livello (se restano) possono raddoppiare i corpi della stessa persona nel Mess.
- Il giorno di bordo e la memoria non sono ancora nel salvataggio della campagna (l'orologio riparte da `start_hour`).
- La mente delle persone non conosce le altre persone del salone se non sono nella stessa conversazione (una sola
  chiamata per frase del Capitano, con al più 3 persone).
