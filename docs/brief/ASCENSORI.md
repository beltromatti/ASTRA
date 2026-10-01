# Brief ASCENSORI (F4.3, del lead): turboascensori e navetta della Spine veri

Le parole dell'utente (2/10): «la nave è piena di ascensori, non solo quello principale del ponte di comando, e gli ascensori devono
funzionare veramente, come in Star Trek: **non essere dei teletrasporti o caricatori di livello**. Devi entrare fisicamente, selezionare
il piano, e l'ascensore deve muoversi su e giù veramente, in tutti gli ascensori, futuristici.» E la nave è abitata: anche la gente
di bordo li usa.

LEGGI: CLAUDE.md; ARCHITETTURA §1bis (le intelligenze: la voce del Capitano passa da prompt e strumenti veri, mai da parole chiave
nel codice) e §6; NAVE.md (§2 riferimento e ponti, §4 lo schema del piano, §7bis istanze, lampade e **`UAstraDeckStreaming`**: un
sotto-livello per ponte, `RequestAt`/`IsReadyAt`/`ForceReadyAt`); **brief NAVE-3** (lavora in parallelo e produce i pozzi nel piano: il
contratto è lì); VITA.md (le persone sul grafo, i corpi vicino al Capitano, gli archi `lift` percorsi col tempo di `speed.lift_s`); il
codice di oggi: `AstraHangar.*` (l'ascensore finto: `RideLift`, `TryUseLift`, `LiftT`, `LiftWaitS`), `ASTRAPlayerController.cpp`
(`ShowLiftMenu`, `ChooseDeck`, la porta della capsula 1-A accanto all'ascensore), `ASTRACharacter.*` (movimento, posture), le console
(`AstraScreensSubsystem`, `AstraStations`: come si disegna uno schermo vero), la mente (`router.py`, `context.py`, `tools.py`,
`crew.py`, `server.py`: come una parola arriva a chi agisce).

## Oggi
Un solo «ascensore» con sei fermate scritte nel codice (plancia, ponte di volo, Main Engineering, Medbay, Mess, Berths), in punti diversi
della nave: `RideLift` fa una dissolvenza, sposta il Capitano a `LiftT` 0,9 e aspetta al buio che il ponte di arrivo si carichi. Va
tolto (la parte del ponte di volo e dei Falcon di `AstraHangar` resta).

## Cosa costruire
1. **Il motore (C++).** `AAstraLiftCar`: la vettura, cinematica, su un percorso (verticale nei pozzi, orizzontale per la navetta) con un
   profilo di velocità morbido (accelerazione, crociera, frenata: tara i numeri perché il viaggio si senta e non annoi; 4 m per ponte);
   porte della vettura e di sbarco che si aprono insieme e non si chiudono su chi passa; porta il Capitano (CharacterMovement con la
   vettura come base, l'ordine dei tick giusto, nessuno scatto a velocità di crociera) e i corpi di VITA. `UAstraLiftSubsystem`: legge
   `vertical[]` e `transit[]` dal piano (contratto in NAVE-3), smista le chiamate (dal pianerottolo e dalla vettura; fermate lungo il
   tragitto nella stessa direzione; più vetture), dà a VITA i tempi veri; `stat Lifts`.
2. **Usarli come una persona.** E sul pannello del pianerottolo chiama la vettura (la vedi arrivare, le porte si aprono); dentro, E sul
   pannello apre l'elenco dei ponti e dei luoghi (Bridge, Main Engineering, Medbay, Mess, Flight Deck, Armory, Transporter Room…) sullo
   schermo della vettura, disegnato come le altre console; si sceglie col mouse o con W/S ed E. **Con la voce**: dentro una vettura il
   Capitano dice «Deck seven», «ponte sette», «Main Engineering»: la mente lo sa dal contesto (in quale vettura è, quali ponti serve) e
   il computer di bordo agisce con uno strumento vero (`lift_go`, ponte o luogo) e conferma con una riga breve nella lingua del Capitano;
   nessuna lista di parole nel codice. In plancia il comando resta dell'equipaggio come oggi.
3. **Il viaggio si vede e si sente.** La vettura ha una finestra o una parete di vetro sul pozzo; il pozzo ha guide, anelli di luce a
   ogni ponte, numeri di ponte che scorrono; il suono (ronzio che cresce con la velocità, un tonfo morbido alla partenza e all'arrivo,
   il segnale delle porte); il pannello dice dove si va e a che ponte si è. Linguaggio della plancia v3 (STILE.md): futuro, non ufficio.
4. **Lo streaming senza schermi neri.** Alla partenza `RequestAt` del ponte d'arrivo; la vettura frena in tempo; se il ponte è in
   ritardo aspetta al pianerottolo a porte chiuse (il pannello dice «Deck 7 · arriving») e solo in ultimo `ForceReadyAt`. Pozzi e vetture
   stanno in un livello sempre caricato (i segmenti dei pozzi come istanze): mai una vettura che corre nel vuoto.
5. **La gente li usa.** I corpi di VITA vicino al Capitano il cui percorso passa per un arco `lift` vanno al pianerottolo, chiamano,
   aspettano, salgono, viaggiano, scendono (e viaggiano con il Capitano se vanno dalla stessa parte); lontano dal Capitano resta il
   tempo astratto di VITA. Lo stesso per la navetta.
6. **La navetta della Spine** (Ponte 5): lo stesso motore su un percorso orizzontale con le sue fermate; la vettura (`ship_craft.spine_car`
   di NAVE) corre nella galleria che fa NAVE-3; pannello e voce («Section H»).
7. **Le mesh** (Blender, file tuoi): l'interno della vettura, porte e cornici di sbarco con il pannello di chiamata e il numero del ponte,
   i segmenti del pozzo (uno per altezza di ponte, a istanze); `tools/ue_scripts/build_lifts.py` le mette nel livello dal piano
   (idempotente).

## Il contratto con NAVE-3
I formati `vertical[]` e `transit[]` versione 2 sono nel brief NAVE-3. Finché il suo piano non arriva in main, prova su un piano di prova
tuo (`data/ship/test/lifts_fixture.json`: due pozzi e la navetta); il lead ti avvisa quando c'è quello vero.

## Prove (offline, tue)
Un commandlet senza grafica (`AstraLiftSim`, sul modello di `AstraNave`/`AstraWarSim`): una vettura dal Ponte 1 al 9 con un personaggio a
bordo nel mondo di gioco che ticka (arriva con la vettura entro 2 cm, nessuna caduta, porte aperte solo al pianerottolo); lo
smistamento con chiamate e 20 persone nell'ora di punta (attese, tempi, nessuna vettura ferma per sempre); il costo per fotogramma (≤ 0,05
ms con 12 vetture ferme). La mente: prove con un modello finto per la voce nella vettura (come `bench/stations_unit.py`), poi poche scene
dal vivo (≤ 0,05 $, riportane il costo). Compila nella tua worktree con `Build.sh … -WaitMutex`.

## File tuoi
`Source/ASTRA/AstraLift*.{h,cpp}` (nuovi), la parte dell'ascensore di `AstraHangar.*`, in `ASTRAPlayerController.cpp` solo
l'interazione con gli ascensori (menu, E, l'eccezione della capsula), un aggancio piccolo in `AstraLifeBody`/`AstraLifeSubsystem` per i
passeggeri, `art/blender/ship_lift.py` (nuovo), `tools/ue_scripts/build_lifts.py` (nuovo), il commandlet, nella mente le parti della
vettura in `context.py`, `router.py`, `tools.py`, `crew.py` (piccole, con le loro prove), `docs/ASCENSORI.md`. **Non tuoi:** il piano e il
kit (NAVE-3), il personaggio e le armi (ABBORDAGGI: se ti serve toccare `ASTRACharacter`, chiedilo al lead).

## Consegna
Il rapporto al lead con i passi d'integrazione (compilare, esportare le mesh, `build_lifts.py` nell'editor) e cosa guardare nel gioco.
