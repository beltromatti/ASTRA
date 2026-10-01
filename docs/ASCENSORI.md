# ASCENSORI — i turboascensori e la navetta della Spine (F4.3)

*Le parole dell'utente (2/10): «la nave è piena di ascensori, non solo quello principale del ponte di comando, e gli ascensori devono funzionare veramente, come in Star Trek: non essere dei teletrasporti o caricatori di livello. Devi entrare fisicamente, selezionare il piano, e l'ascensore deve muoversi su e giù veramente, in tutti gli ascensori, futuristici.» E la nave è abitata: anche la gente di bordo li usa.*

Brief: [brief/ASCENSORI.md](brief/ASCENSORI.md). Il contratto con il piano della nave: [brief/NAVE-3.md](brief/NAVE-3.md) (`vertical[]` e `transit[]`, versione 2). Le intelligenze (la voce del Capitano passa da prompt e strumenti veri, mai da parole chiave nel codice): [ARCHITETTURA.md](ARCHITETTURA.md) §1bis.

## 1. Com'è fatto

Un turboascensore (**turbolift**), un montacarichi (**cargo lift**) o la navetta della Spine (**Spine Shuttle**) è una **vettura vera**: un attore cinematico (`AAstraLiftCar`) che percorre un tracciato (verticale nel suo pozzo, orizzontale per la navetta) con un profilo di velocità morbido, porta chi è a bordo, apre le porte solo al pianerottolo e non le chiude mai su qualcuno. Non c'è né dissolvenza né teletrasporto né caricamento di livello: il Capitano sale, la vettura parte, il pozzo gli scorre fuori dalla finestra, la vettura frena, le porte si aprono sul ponte d'arrivo.

```
piano (vertical[] / transit[], v2)
   └─ FAstraLiftNetwork (AstraLiftData)      linee, fermate (ponte, id "d4"/"sec_a", etichetta, nome del ponte, luoghi notevoli), percorso, misure
        └─ UAstraLiftSubsystem               costruisce pozzi, vetture e pianerottoli nel livello sempre caricato (una linea a fotogramma, la più vicina al Capitano per prima)
             ├─ AAstraLiftCar + FAstraLiftBrain      la vettura e il suo cervello (puro: nessun attore): moto, porte, smistamento
             ├─ AAstraLiftLanding / AAstraLiftShaft  le porte di sbarco col pannello, la targa e la lampada; il rivestimento del pozzo a istanze
             ├─ lo schermo della vettura             un canvas render target disegnato dallo stato (l'elenco dei ponti e dei luoghi)
             ├─ FAstraLiftRider                      la persona che usa la vettura (la gente di VITA, gli attori del banco)
             └─ la voce                              lift_go (strumento della mente) + context.lift
```

File (tutti `Source/ASTRA/AstraLift*`): `Brain` (moto e smistamento), `Data` (lettura del piano), `Car` (vettura, pianerottolo, pozzo, misure), `Subsystem` e `Screen` (Capitano, schermo, voce, streaming, equipaggio), `Rider` (passeggero), `TestRig` e `SimCommandlet` (campo di prova e banco). Il resto: `art/blender/ship_lift.py` (mesh), `tools/ue_scripts/build_lifts.py` (progetto), `tools/art/lift_sounds.py` (suoni), `tools/lift.py` (piano di prova, controllo, banco), la mente in `mind/astra_mind/{context,tools,agent,server}.py`.

## 2. Il moto

Profilo **smoothstep** in forma chiusa (`FAstraLiftProfile`): la velocità sale con una smoothstep al picco, lo tiene, scende allo stesso modo; l'accelerazione inizia e finisce a zero, quindi non c'è strappo, solo una spinta morbida alla partenza e all'arresto. La posizione a ogni istante è esatta (nessuna integrazione numerica, nessuna deriva). Sulle tratte corte il picco è quello che la distanza permette e l'accelerazione è più dolce («si sente e non annoia»).

| tratta | tempo | picco |
|---|---|---|
| 4 m (un ponte) | 3,8 s | 2,1 m/s |
| 16 m | 6,2 s | 5,2 m/s |
| 37 m | 9,4 s | 7,8 m/s |
| 66 m (Ponte 1 → 9) | 13,1 s (16,5 s con le porte) | 8,0 m/s |

Numeri di linea (dal piano, `speed` e `accel`): turboascensore 8 m/s e 2,5 m/s², montacarichi di servizio 5 m/s e 1,5 m/s², navetta 16 m/s e 2,2 m/s². Una fermata chiesta durante la crociera si aggiunge se la frenata non deve cominciare prima di 0,4 s (`Retarget`), altrimenti aspetta il giro dopo.

**Il Capitano a bordo.** La vettura ha come pavimento un `UBoxComponent` cinematico: il `CharacterMovement` del Capitano lo prende per base mobile, quindi viaggia con la vettura e non cade a nessuna velocità. L'ordine dei tick conta: la vettura gira in `TG_PrePhysics` e muove il corpo prima del movimento del personaggio, così il Capitano trova il pavimento dove lo aspetta. Misurato nel banco con un personaggio vero in un mondo che ticka (collisione e movimento reali): Ponte 1 → 9 arriva a **0,0 cm** dal punto in cui stava nella vettura (limite 2 cm), mai fuori dal pavimento, mai in caduta, anche a 30 fps; la vettura è ferma al pianerottolo entro 0,1 cm.

## 3. Lo smistamento

`FAstraLiftBrain`: **controllo collettivo**. La vettura tiene la direzione finché c'è una fermata avanti, si ferma per le chiamate dei pianerottoli che vanno dalla sua parte e per quelle fatte da dentro, e si gira all'ultima. Ogni pozzo ha la sua vettura e il suo pannello a ogni pianerottolo (le coppie di pozzi accanto si dividono la gente: chi preme l'altro pannello aspetta l'altra vettura). Una vettura piena passa oltre le chiamate dei pianerottoli (il bypass per il peso di un ascensore vero); una vettura vuota ferma non resta mai ferma con una chiamata in attesa. Porte: 1,1 s di corsa, aperte 3,5 s (1,2 s dopo che qualcuno dentro ha scelto), tornano indietro se qualcuno entra nella soglia mentre si chiudono.

Ora di punta nel banco (brain puro, 20 persone che chiamano e scelgono a caso): un pozzo solo, 20 su 20 consegnate in 215 s, attesa media 51 s, 95° percentile 96 s, peggiore 120 s; una coppia di pozzi che si dividono le stesse 20 persone, attesa media 32 s, peggiore 99 s; nessuna vettura ferma con chiamate in attesa, nessuna violazione delle invarianti (porte aperte solo a vettura ferma a quel pianerottolo, mai due pianerottoli aperti).

## 4. Usarli come una persona

- **Al pianerottolo** un pannello a sinistra della porta: **E** chiama la vettura (la lampada si accende, la vedi arrivare, le porte si aprono insieme).
- **Dentro**, **E** apre sullo **schermo della vettura** (sulla parete a destra di chi entra, disegnato come le altre console) l'elenco dei ponti con il nome e i luoghi notevoli (Bridge, Main Engineering, Medbay, Mess Hall, Flight Deck, Armory, Transporter Room…). **W/S**, frecce, rotella, o il mouse (il raggio dello sguardo sullo schermo) spostano il segno; **E**, Invio, Spazio o clic scelgono; **1–9** vanno a quel ponte; **Esc** chiude. Lo schermo dice dove si va e a che ponte si è (`▼ DECK 7`, `DECK 7 · ARRIVING` se il ponte non è ancora pronto).
- **Con la voce**: dentro una vettura il Capitano dice «Deck seven», «ponte sette», «portami in sala macchine», «un piano più su», «Section C»; vedi §6.
- Il pozzo ha guide, cavi e anelli di luce a ogni ponte; la finestra della vettura mostra il fondo del pozzo con il numero del ponte che passa (la targa dell'atrio è sopra la porta, il numero grande è sul fondo del pozzo). Suoni: ronzio che cresce di volume e di tono con la velocità, un tonfo morbido alla partenza e all'arresto, il segnale di arrivo, le porte (quelle di sempre).
- La **capsula di salvataggio 1-A** sta accanto alle porte dell'ascensore della plancia: lì E è dell'ascensore (l'eccezione è in `ASTRAPlayerController`, `IsNearPanel`).

## 5. Lo streaming dei ponti senza schermi neri

All'inizio di un viaggio la sottosistema chiede a `UAstraDeckStreaming` il ponte d'arrivo (`RequestAt`), e la vettura frena in tempo. Se all'arrivo il ponte non c'è, la vettura **aspetta al pianerottolo a porte chiuse** (lo schermo dice «DECK 7 · ARRIVING») e solo dopo 6 s, in ultimo, chiama `ForceReadyAt`. Mai uno schermo nero, mai una vettura che apre sul vuoto. Pozzi, vetture e pianerottoli stanno nel livello sempre caricato: la vettura non corre mai nel vuoto. `RideFeet()` dice a chi guarda dove sta andando il Capitano (l'atrio d'arrivo, non ogni ponte che attraversa a 8 m/s): VITA lo usa per fare le persone intorno all'atrio prima che le porte si aprano (`AstraLifeSubsystem::ManageBodies`); lo streaming dei ponti dovrebbe fare lo stesso (richiesta al lead, §9).

## 6. La voce («Deck seven»)

Nessuna lista di parole nel codice. Il gioco manda con le parole del Capitano il contesto della vettura in cui sta (`context.lift`, `UAstraLiftSubsystem::ContextJson`: quale vettura, dove sta o va, le fermate che serve con id, etichetta, nome del ponte e luoghi notevoli); la mente (`mind/astra_mind`) lo legge, e **dentro una vettura** dà al modello:

- uno strumento vero **`lift_go`** con `destination` = una delle fermate **di quella vettura** (l'enum cambia con la vettura: una navetta ha le sezioni, un turboascensore i ponti); fuori da una vettura lo strumento non esiste;
- un paragrafo nella stanza che dice cosa fa il computer di bordo (qualunque lingua, qualunque modo di nominare la fermata: un numero, il nome del ponte, un luogo, «giù», «uno più su», «dove sono i feriti»; la scelta è del modello), che le fermate sono elencate dall'alto in basso (o come corre la linea), che **la fermata più vicina non sostituisce quella che non c'è**, e che gli ufficiali restano fuori;
- una voce propria, **`computer`** (voce `estelle`, mai un ufficiale): chiama `lift_go` e dice **nello stesso turno** una riga breve nella lingua del Capitano che nomina dove va come lo direbbe la gente di quella lingua (un solo giro di modello: la battuta arriva con il comando in 0,6–0,9 s).

**La gente in vettura non ruba le parole al computer.** Un passeggero che sta di fronte al Capitano sente «Deck seven» e il suo modello (`npc`) rispondeva («Deck seven, signore? Io scendo alla quattro…»): la risposta di una persona zittisce il turno degli ufficiali, e `lift_go` non partiva mai (trovato con la prova dal vivo `rider_deck`). Ora la mente dice alla persona, nel «dove si trova il Capitano», che è in una vettura, che il computer di bordo lo porta dove chiede e che le parole che chiedono una corsa sono del computer (`server._captain_turn`); le parole davvero per il passeggero («da quanto sei a bordo?») restano sue. Prova: `lift_server.test_the_people_aboard_are_told_a_ride_is_the_computers`, e dal vivo `rider_deck`, `rider_place_it`, `rider_chat` (3 su 3).

`GoByVoice` (C++) accetta l'id della fermata, o il ponte o il luogo, rifiuta ciò che la vettura non serve con un messaggio che la mente rilegge, e fa partire la vettura per davvero. Prove: `mind/bench/lift_unit.py` (15, la logica con un modello finto: la riga del contesto che il gioco manda, lo strumento solo in vettura con le fermate di quella vettura, la voce del computer solo lì, una fermata che non c'è non muove niente, la rilettura dopo un ordine fallito), `mind/bench/lift_server.py` (7, il collegamento col gioco finto: il comando `lift_go` arriva con `by: computer`, la voce è quella del computer, fuori dalla vettura niente, la gente a bordo è avvertita), `mind/bench/lift_live.py` (12 scene contro il modello vero in cinque lingue, tre con un passeggero che guarda il Capitano: tutte come previsto, circa 0,0007 $ a scena; `lift_live.py -v` mostra cosa fa la mente; `--model` confronta altri modelli). L'intera suite della mente: 272 prove verdi.

## 7. La gente di bordo

`FAstraLiftRider` porta un attore da un pianerottolo a un altro come una persona: preme la chiamata (e la ripremere ogni 6 s: una chiamata servita quando nessuno poteva salire non si perde), aspetta una vettura che stia lì con le porte aperte e vada dalla sua parte, **prende un posto** (mai quello del Capitano: mezzo metro almeno), cammina dentro per la corsia della porta, **viaggia attaccato alla vettura** (esatto a qualsiasi frequenza di tick), scende dove le porte si aprono al suo ponte e va al punto in cui il percorso lo vuole. Mentre cammina è un «walker» delle porte (`AstraDoors`), che la vettura legge: le porte non si chiudono mai su di lui. Se le porte si chiudono mentre è ancora fuori, richiama; se si chiudono mentre è dentro che sta uscendo, la vettura lo porta oltre e lui ripreme il suo piano.

Il corpo di VITA (`AstraLifeBody`) ha un modo `Lift`: se il tratto verticale del percorso della persona è un tratto del piano delle vetture (`FindRide`), il corpo lo percorre per davvero con il rider; altrimenti il tempo astratto di prima (nascosto, `Speed.LiftS` secondi). Lontano dal Capitano nessun corpo: resta il tempo astratto. `UAstraLifeSubsystem::ManageBodies` fa le persone intorno all'atrio dove il Capitano sta andando mentre viaggia. Lo stesso per la navetta (un tratto orizzontale lungo tra due fermate).

Prova (banco, scenario `riders`, attori di prova guidati dallo stesso rider, in una vettura vera in un mondo che ticka): 20 persone in 90 s, 20 su 20 consegnate; porte mai chiuse su un camminatore né vettura in moto con uno in soglia; nessuno sulla stessa posizione; con il Capitano in vettura nessuno prende il suo posto (il più vicino a 52 cm); la navetta con 8 persone, 8 su 8.

## 8. Le mesh, il piano, i suoni

**Il kit** (`art/blender/ship_lift.py`, Blender 5.2 headless, anteprime Eevee in `ship_lift_preview.py`): 27 mesh, in `Content/ASTRA/Kit/Lift`. Per ogni tipo (`tl` turbolift, `sv` service, `cg` cargo): la cabina (pavimento antiscivolo con luce di guida, pareti a pannelli con fascia colore e montanti, finestra sul pozzo, corrimano, soffitto a nervature con pannello luminoso, cornice dello schermo con i pulsanti), il vetro, il battente, la cornice del pianerottolo (rivestimento, spalle, pannello di chiamata con la sede della lampada, targa del ponte, frecce, soglia), il battente del pianerottolo, il segmento di pozzo da 4 m (guide a T, staffe, cavi, strisce di luce ogni metro) e quello da 3,2 m con l'apertura. La navetta (`sh`): la vettura di 14 m con tre porte, finestre panoramiche, pali e uno schermo grande al centro, e il vetro. In più la lampada di chiamata, il palo di chiamata della navetta e il quad dello schermo. Misure nominali per tipo (tabella `KIT` in Blender, `LiftNominal` in `AstraLiftCar.cpp`): le mesh si scalano alle misure del piano. Budget: cabina 8,9 k triangoli, cornice del pianerottolo 2,7 k, segmenti di pozzo 0,4–0,5 k, navetta 15 k.

**Il piano.** La sottosistema legge `vertical[]` e `transit[]` v2 di `data/ship/aquila_plan.json` (o di `astra.lifts.plan <file>`); il piano non ha ancora i pozzi veri (NAVE-3 li sta facendo): finché non arrivano si prova su `data/ship/test/lifts_fixture.json` (`tools/lift.py fixture`: tre pozzi, uno coppia del primo, un servizio, la navetta). `tools/lift.py check [piano]` controlla il contratto (porta sulla parete del pozzo, la vettura entra, tutte le porte dalla stessa parte, le fermate lungo la linea, i nodi del grafo lì).

**I suoni** (`tools/art/lift_sounds.py`, sintetizzati): `SW_Lift_Hum` (ciclo senza giunta, energia sopra i 100 Hz perché gli altoparlanti di un portatile la suonano), `SW_Lift_Thump`, `SW_Lift_Chime`.

## 9. Integrazione (per il lead)

1. **Compilare** (la worktree compila pulita): il codice nuovo è `AstraLift*`, `AstraLiftRider.*`, e piccoli agganci in `ASTRAPlayerController` (l'interazione), `AstraHangar` (tolto l'ascensore finto: restano le luci delle stanze vecchie), `AstraLifeBody`/`AstraLifeSubsystem` (i passeggeri).
2. **Generare** (artefatti non in git):
   `blender -b --factory-startup --python-exit-code 1 -P art/blender/ship_lift.py -- art/export/ship_lift` (con `--preview art/_cache/lift` per le anteprime);
   `uv run --with numpy --with soundfile --with scipy python tools/art/lift_sounds.py`.
3. **Nell'editor**: `tools/ue.py pyfile tools/ue_scripts/build_lifts.py` (suoni, istanze `MI_LIFT_*`, mesh, controllo); con `TEST=True` anche `L_LiftTest` (un rig con il piano di prova, luce e un PlayerStart davanti al primo turboascensore): è il posto per provare le vetture senza i ponti veri. Per usare il piano di prova nel livello vero: console `astra.lifts.plan data/ship/test/lifts_fixture.json` prima del BeginPlay.
4. **Due righe nei file del lead** (senza queste la voce non arriva al gioco):
   - `UAstraShipSubsystem::CaptainContext()`, prima del `return C`: `if (const UAstraLiftSubsystem* L = GetWorld()->GetSubsystem<UAstraLiftSubsystem>()) { if (TSharedPtr<FJsonObject> J = L->ContextJson(); J.IsValid()) { C->SetObjectField(TEXT("lift"), J); } }`
   - `UAstraShipSubsystem::ApplyCommand()`, con gli altri nomi: `if (Name == TEXT("lift_go")) { UAstraLiftSubsystem* L = GetWorld() ? GetWorld()->GetSubsystem<UAstraLiftSubsystem>() : nullptr; return L ? L->GoByVoice(Args, OutDetail) : false; }`
5. **VITA**: `speed.lift_s` del piano della vita va portato al numero che `astra.lifts.info` stampa («a ride between two decks takes … s»): l'abstract ride delle persone che nessuno vede deve durare quanto un viaggio vero.
6. **Streaming dei ponti**: `UAstraDeckStreaming` dovrebbe guardare `UAstraLiftSubsystem::RideFeet()` quando è vero (l'atrio d'arrivo) invece del Capitano che attraversa i ponti.

## 10. Cosa guardare nel gioco

`astra.lifts.info` (dove sta ogni vettura, cosa fa, se il Capitano è dentro, e la durata media di un viaggio); `astra.lifts.call <linea> <ponte>`; `astra.lifts.go <ponte>`; `astra.lifts.context` (cosa riceve la mente); `stat Lifts`. Cose da provare: chiamare una vettura da un pianerottolo e guardarla arrivare, entrare, aprire l'elenco con E, scegliere con W/S ed E e col mouse, il viaggio Ponte 1 → 9 (nessuno scatto a 8 m/s, il pozzo che scorre dalla finestra), uscire, dire «Deck seven» e «portami in sala macchine» da dentro, vedere la gente che aspetta, sale e viaggia con te, la navetta («Section H»).

## 11. Prove e costi

Banco senza grafica: `tools/lift.py run` (comando `UnrealEditor-Cmd -run=AstraLiftSim -unattended -nullrhi -nosound -nopause`): **37 prove su 37**: piano (anche il percorso di una persona su una vettura: `FindRide`), moto (esatto ai due capi, nessuna rottura di continuità), cervello (chiamata, chiamata dove la vettura sta, il giro, la fermata aggiunta in crociera e quella chiesta troppo tardi, le porte che aspettano il ponte, quelle che non si chiudono su qualcuno), ora di punta, un personaggio che viaggia Ponte 1 → 9 e 9 → 5, le porte che aspettano il Capitano, la voce, lo streaming, la navetta, i passeggeri, il costo. **Costo: 12 vetture ferme = 0,28 µs a fotogramma di media (limite 50 µs); 12 vetture in moto insieme = 0,19 ms a fotogramma** (tutte e dodici, che non succede mai).

Costo AI delle prove dal vivo della voce: circa 0,05 $ in tutto (0,0477 $ le prime nove scene e la taratura del prompt, 0,0018 $ le scene con il passeggero) (una trentina di scene brevi, la maggior parte per tarare il prompt; la scena a regime costa 0,0002–0,0008 $, e un ordine di ascensore è una sola chiamata).

## 12. Limiti noti

- Il piano vero con i pozzi non c'è ancora: tutto è provato sul piano di prova (le coordinate delle fermate del piano vero devono combaciare con i nodi del grafo entro 90 cm, `FindRide`).
- `FAstraLifeRoute::Kind` (VITA) classifica un tratto verticale con lo stesso XY come scala: per i passeggeri non conta (decide `FindRide`), ma l'abstract ride dura `StairsS` e non `LiftS` per quei tratti.
- La targa del ponte e il numero sul fondo del pozzo sono `UTextRenderComponent` col materiale del testo olografico: l'orientamento è quello delle scritte di DISTRUZIONE (fronte a +X della cornice), da controllare a occhio nel gioco.
- Le mesh sono modellate al nominale per tipo e scalate alle misure del piano: una differenza oltre il 15% deforma i dettagli sottili.
- La luce del campo di prova è una prima approssimazione.
