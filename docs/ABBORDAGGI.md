# ABBORDAGGI — combattere a bordo (F5.1)

*Documento del modulo ABBORDAGGI (2026-10-02). Cosa fa il gioco quando il combattimento arriva dentro l'Aquila, come funziona, come si prova e cosa misura. I nomi nel gioco
sono in inglese; il documento in italiano. Vedi anche il brief [brief/ABBORDAGGI.md](brief/ABBORDAGGI.md), [DISTRUZIONE.md](DISTRUZIONE.md) §2.6 (le persone e il Capitano),
[VITA.md](VITA.md) (gli 80 marine del ruolino), [VOLO.md](VOLO.md) (la rete di volo, di cui la rete dei marine è la sorella) e [ARCHITETTURA.md](ARCHITETTURA.md) §1bis
(il principio delle intelligenze).*

## 1. In breve

Un abbordaggio è una battaglia vera nei corridoi: il Capitano può restare in plancia o scendere a combattere con un fucile in mano; i marine dell'Aquila, persone del
ruolino di VITA, rispondono all'allarme; una squadra del Mandato entra da una breccia e va all'Ingegneria per prendere il reattore. Tutto è **codice di squadra** (gambe,
copertura, fuoco di soppressione, aggiramento, ritirata) tranne ciò che è giudizio: chi comanda i marine è una **persona**, il Maggiore Tomás Reyes, e i capisquadra sono
persone del ruolino; parlano al Capitano, ne eseguono gli ordini con strumenti veri e agiscono da soli dove il drill non basta.

Le quattro parti del brief, come sono fatte:

1. **Il nucleo FPS** — un fucile (AR-181) e una pistola (M27S) si prendono dal rastrello dell'armeria del Ponte 8 (E); braccia in prima persona con le animazioni del
   mannequin (impugnare, mirare con il destro, sparare, rinculo, ricaricare con R, cambiare arma), colpi a raggio con tracciante breve, impatti e suoni; il movimento è quello
   del personaggio (C accucciato, C tenuto sdraiato, Spazio salto, Shift corsa) e l'arma ne cambia il prezzo (passo, mira, cono dei colpi).
2. **Il danno alle persone**, costruito sul modello di DISTRUZIONE: i marine colpiti sono feriti (vanno in Medbay dal ruolino) o caduti (con il nome); il Capitano ha una
   forza e un trauma nel modello del danno; a terra sanguina e la catena della nave lo porta via o lo perde (XO al comando, abbandono nave, inchiesta, «THE CAPTAIN IS LOST»).
3. **I combattenti** — la squadra d'abbordaggio del Mandato (squadre di fanti con IA di squadra) e i marine dell'Aquila (la guardia accorre, la squadra di reazione si arma),
   fino a 22 corpi alla volta intorno al Capitano, il resto è simulazione senza corpo.
4. **L'evento** — il comando `boarding` (o la console) apre la breccia, chiude le paratie di sezione, porta la nave in allarme rosso, chiama i marine; la plancia lo riferisce;
   il Capitano è libero di combattere o restare; la fine (respinti, presa dell'Ingegneria, il Capitano caduto) segue la catena che esiste.

L'intelligenza è nel prompt, nel contesto e negli strumenti, mai in filtri di codice sulle parole (§1bis): il codice porta i fatti, tiene l'orologio, controlla l'autorità
degli ordini e li passa al gioco. Con `ASTRA_MARINE_MINDS=0` la rete dei marine è spenta e la plancia riferisce come prima (i marine combattono comunque, con il drill).

## 2. Come si prova

**Nel gioco** (il lead): il progetto compilato, gli asset importati (§11).

| Cosa | Come |
|---|---|
| Prendere le armi | Ponte 8, l'armeria: **E** davanti al rastrello (se il livello non ne ha uno, il gioco ne mette uno al centro dell'armeria quando il Capitano è vicino); `astra.armory.here` ne mette uno davanti a te; `astra.weapons.give` / `astra.weapons.stow` danno e tolgono il kit ovunque |
| Sparare | tasto sinistro (il fucile è automatico, la pistola un colpo a clic); destro: mirare (campo più stretto, giro più lento, cono più chiuso); **R** ricarica; **1** fucile, **2** pistola, **Q** l'arma di prima, **H** in fondina, rotella: cambia; correre abbassa l'arma; **F1** la scheda dei tasti |
| Il poligono del Ponte 8 | `d8_firing_range_*` nella pianta: il rastrello e un bersaglio qualsiasi (i marine di guardia sono corpi veri) bastano per provare mira, rinculo e ricarica |
| Un abbordaggio | `astra.board.start [navette 1..4] [id della stanza in cui tagliano]` (il comando `boarding` del gioco: `{skiffs, boarders, breach, source, lockdown, warn_s}`); `astra.board.end` lo chiude; `astra.board.info` ne dà i numeri; `astra.board.debug 1` disegna i soldati, `2` anche i luoghi delle squadre, la via del Mandato e l'imboscata dei marine; `astra.board.picture` scrive nel log il quadro che la mente legge |
| Ordini ai marine | a voce («Reyes, tieni il corridoio fuori dall'ingegneria», «Reaction Uno, con me», «chiudi le paratie»), o `astra.board.cmd marine_order {"squad":"all","task":"hold","place":"engineering"}` / `astra.board.cmd lockdown {"sealed":true}` |
| Regolare le braccia | `astra.fps.hip_x/_y/_z`, `astra.fps.ads_x/_y/_z` (dove sta la mira rispetto alla camera, in cm), `astra.fps.arms 0` (solo l'arma, il ripiego) |
| Altri | `astra.board.friendlyfire 1` (i colpi del Capitano feriscono anche i marine); `astra.board.takeover_fatal 0` (se il Mandato prende l'Ingegneria il combattimento finisce e basta, senza il collasso del reattore) |

**Senza il gioco** (i banchi, §9): `tools/boarding.py` (la simulazione sulla pianta vera), `mind/bench/marines_unit.py`, `marines_server.py` (modello finto), `marines_live.py` (modello
vero, centesimi).

## 3. La simulazione di squadra

`AstraBoardMap.*` — la pianta come la vede un soldato: dalle facce condivise delle stanze nascono **portali** (aperto, porta, paratia di pressione, scala, ascensore), una
**rotta A\*** sui portali (le stanze sono scatole convesse), la **linea di vista** (un raggio che attraversa una faccia è fermato salvo una porta aperta) e le **tacche**: gli
angoli accanto a ogni varco, dove un uomo sta al riparo e si affaccia per sparare. 3234 stanze (pianta v2) si leggono in 200 ms su un worker; un percorso costa 0,07 ms.

`AstraBoardSim.*`, `AstraBoardAI.cpp` — la simulazione, deterministica dal seme, a 10 Hz con la percezione sfalsata a 4 Hz (0,03-0,06 ms a passo con tutti i soldati):

- **Il soldato**: percepisce (vede dove la linea di vista è aperta, sente gli spari), sceglie una tacca, vi resta al riparo, si affaccia, spara, ricarica al coperto, è
  soppresso da ciò che gli passa vicino, cade (a terra: sanguina, muore in 85 s se nessuno lo porta via).
- **Il Mandato**: colonna sulla via dell'Ingegneria; al contatto una squadra fissa e una coppia aggira; assalto; **taglia le paratie sigillate in circa 22 s** (evento `Cut`); ripiega
  quando una squadra ha perso più del 55%; se si ferma, spinge dopo 40 s.
- **I marine** (senza ordini): corrono all'**imboscata** (il varco della via del Mandato dove vincono la corsa, scelto con una ricerca a fette), ne prendono gli angoli, non
  cedono terreno da soli; la guardia parte subito, la squadra di reazione (2 squadre da 6) dopo 25 s all'armeria, la riserva (dormienti che si svegliano e si armano) man mano.
- **Gli ordini** (`Order`, quelli della mente): `hold` (prendi gli angoli del luogo e tienilo), `advance` (vai in colonna, copriti se incontri il nemico), `assault` (corri là e
  combatti), `fall_back`, `follow_captain`, `rescue_captain`, `stand_down` (torna al drill). Un luogo si dice con l'id del piano, o `captain`, o per tipo/nome se è uno solo.
- **Il Capitano** è un soldato esterno: la sua posizione e il suo stato vengono dal gioco, i suoi colpi dalla sua mano, il suo ferimento dai colpi che lo raggiungono (il raggio
  passa per il livello vero: un armadietto, una console fanno da riparo).

### Cosa misura il banco (§9): i marine vincono, il drill è buono

Con 24 marine di guardia e 12 di reazione, paratie sigillate, 16 semi, pianta v2: una navetta (10 abbordatori) è fermata 15 volte su 16 con 7,0 marine persi (16 su 16 e 1,4 persi
se le paratie non sono sigillate: i marine arrivano prima); due navette 16 su 16 (9,9 persi); tre navette 14 su 16; solo la squadra di reazione 15 su 16; nessuno armato (i marine dormono) la nave è presa 16 su 16.

**Cosa costano gli ordini** (lo stesso combattimento, gli stessi 8 semi, pianta v1; `tools/boarding.py run --scenario orders`):

| Piano | 10 abbordatori | 20 abbordatori |
|---|---|---|
| il drill da solo | 8 respinti, 4,0 marine persi | 7 su 8 tenuti, 10,8 persi |
| tutte le squadre alle porte dell'Ingegneria (20 s) | 8 respinti, **1,2** persi | 4 su 8 tenuti, **4 prese**, 24,1 persi |
| tenere alle porte (20 s) e restituire al drill (70 s) | 5 tenuti + 3 respinti, 0,5 persi | 3 su 8 tenuti, 5 prese, 34,6 persi |
| tutte avanzano sulla breccia (80 s) | come il drill | 6 su 8 tenuti, 2 prese |
| tutte assaltano la breccia (80 s) | 8 su 8 ma 10,9 persi | **7 prese su 8**, 33,5 persi |
| tutti ripiegano sull'armeria (100 s) | **8 prese su 8** | 8 prese su 8 |

Sulla pianta v2 la lezione è la stessa (con 20: il drill 8 su 8 tenuti con 9,0 persi; assalto 3 prese; ripiegare 7 prese). Il prompt di Reyes ha queste lezioni (§7): il drill è
buono, tutti alla porta spreca i corridoi, l'assalto si paga in marine, ripiegare regala il reattore. «Follow»: dopo 60 s il 100% dei marine abili è a meno di 15 m dal Capitano.

## 4. Il Capitano con un'arma

`AstraWeapon.*` (la tabella), `AstraFpsComponent.*`, `AstraFpsHud.*`, `AstraArmory.*`, `AstraCombatFx.*`:

| | AR-181 (fucile di servizio) | M27S (pistola di ordinanza) |
|---|---|---|
| fuoco | automatico 650 colpi/min | un colpo a clic, 400/min |
| caricatore | 30 + 4 di scorta | 15 + 3 di scorta |
| danno | 22 (testa ×2,4, arti ×0,75), pieno fino a 25 m, 70% a 70 m | 30, pieno fino a 15 m, 65% a 45 m |
| ricarica | 2,3 s (a secco 2,9 s) | 1,7 s (a secco 2,1 s) |
| mira | cono 1,6° dal fianco, 0,15° dal mirino; campo 62° | 1,2° e 0,1°; campo 72° |

Le armi sono modelli gratuiti (CC-BY, registrati in [licenze.csv](licenze.csv)): *AR-181* di Frostoise e *M27S Automatic pistol* di Tuuttipingu (Sketchfab), preparati da
`art/blender/weapons.py` (UV, texture ORM e normale, prese: Muzzle, Sight, SightFront, GripL, MagWell, Eject) e importati da `tools/ue_scripts/import_weapons.py`; i suoni sono
sintetizzati (`tools/art/weapon_sounds.py`: colpo, scatto a vuoto, ricariche, impugnare, impatto, sibilo, colpo a segno), nessun campione di terzi.

- **Braccia**: la stessa mesh delle braccia del personaggio su un componente a parte, con le animazioni di fucile e pistola del mannequin (Equip, Idle_ADS, Reload, DryFire; la
  Fire è additiva, il rinculo è procedurale). Il posto dell'arma rispetto alla camera è **calcolato** dalla posa della mano destra misurata con una sonda (i numeri sono in
  `AstraWeapon.cpp`), in modo che il mirino cada sull'asse della camera: dal fianco, dal mirino e abbassata (corsa, rimessa).
- **Il colpo**: raggio dalla camera con il cono dell'arma (posizione, velocità, salto, apertura del colpo), tracciante breve dal muso, lampo, impatto (metallo, carne), il sibilo
  per chi lo sente passare, il suono; il rinculo alza il mirino e lo fa vagare, l'arma scalcia sulla spalla (molla), poi il mirino ricade in parte.
- **Lo schermo**: mirino che si apre con il cono, colpi, forza (quando ferito o in un combattimento), rosso ai bordi e archi di provenienza di un colpo ricevuto, la croce
  bianca di un colpo a segno (rossa-bianca alla testa), il suggerimento del tasto a portata («E TAKE THE RIFLE AND THE SIDEARM»), la riga dei tasti per 24 s quando si arma.
- **Il costo**: con l'arma in mano il passo cala (0,9; 0,6 dal mirino), il giro dal mirino segue il campo; da seduto, con il tablet alzato, nella lista di un ascensore, a terra
  o morto l'arma non c'è.

## 5. Il danno alle persone e il destino del Capitano

- **Marine e abbordatori**: il colpo che li raggiunge è la loro ferita (la loro armatura, la testa pesa di più); a terra sanguinano. I marine del ruolino che cadono: **morti**
  (`HarmPerson(..., dead)`: il caduto ha un nome nella memoria della nave e nella parete della Mess) o **feriti** (a fine combattimento vengono portati in Medbay con una ferita
  da arma da fuoco della tabella di VITA, di gravità 0-2). I loro corpi del gioco tornano al pool, VITA li restituisce alla loro giornata (`Commandeer`).
- **Il Capitano**: una forza 0-100; ogni colpo ne toglie la parte che passa il giubbotto (×0,8); il **trauma** che il modello del danno già conosce (`CaptainWounded`: tunnel e
  svenimento sullo schermo, la causa nel registro); 25 s senza colpi e recupera lentamente. A zero è **a terra** (non muore subito): sanguina per 85-135 s; la catena della
  nave lo porta via quando è sicuro (le **due squadre più vicine vanno da lui da sole**, per riflesso del drill, e restano intorno a lui finché non è portato via o in piedi: il
  banco misura 10 marine entro 8 m dopo 50 s, e `rescue_captain` ne manda altre) o lo perde (`CaptainDied`: «bled out from gunshot wounds»). Se il nemico lo vede a meno di 32 m la catena non può portarlo via (`CaptainContested`). Salvato, si sveglia in Medbay al 35%.
- **La fine**: se muore, tutto ciò che c'è già prende il sopravvento (l'XO al comando, l'abbandono nave, l'inchiesta, «THE CAPTAIN IS LOST»).

## 6. L'evento

`UAstraBoardSubsystem` (`AstraBoardSubsystem.cpp`, `AstraBoardEvents.cpp`, `AstraBoardMind.cpp`):

1. **L'allarme** (`StartBoarding`): le navette sono state viste `warn_s` (45 s) prima che le squadre taglino; l'allarme va a rosso; le paratie di pressione del ponte della breccia
   si chiudono (modello del danno e porte del gioco, `SealBulkhead`); i marine del ruolino vengono mobilitati: la guardia accorre, la reazione si arma all'armeria in 25 s,
   i dormienti si svegliano e si armano (VITA li «requisisce» finché dura).
2. **La breccia**: un anello di taglio incandescente e una luce calda nella stanza, scintille e suono; l'evento `boarding: the hull is cut open at ...`.
3. **I rapporti**: gli eventi `boarding: ...` (§7) arrivano alla plancia (il primo contatto, un caduto, una paratia tagliata, il Capitano a terra, la fine) e alla rete dei marine.
4. **Le paratie**: la mente le chiude e le apre (`lockdown`); il Mandato le taglia (si aprono, con scintille).
5. **La fine**: gli abbordatori respinti (`MandateRepelled`), tutti a terra (`AquilaHolds`), l'Ingegneria presa (`MandateTakes`: il reattore cede dopo circa 30 s, la catena di
   abbandono nave) o il fuoco spento (`TimedOut`); i corpi restano 75 s, i feriti vanno in Medbay, il Capitano ha un nuovo giorno.

I corpi: fino a 22 soldati entro 65 m sul ponte del Capitano hanno un corpo (mannequin con la divisa, il fucile in mano, le animazioni di camminata/corsa/ricarica/caduta);
gli altri sono solo simulazione. In una torre di scale nessuno li vede e restano nascosti finché ne escono.

## 7. La mente: la rete dei marine

`mind/astra_mind/marines.py` — **`MarineMinds`**, la sorella di `FlightMinds`: un canale (`marines`) che il Capitano ha nell'orecchio per tutta la durata di un abbordaggio e per
75 s dopo, qualunque stanza abbia sotto i piedi. Il router (la chiamata piccola di comunicazioni) decide quali delle sue parole escono sulla rete («Reyes, tieni il
corridoio», «Reaction Uno, con me», «chiudi le paratie»; non «Timoniere, rotta zero-nove-zero»); chi è chiamato risponde e agisce; i bridge officers non ne dicono nulla.

**Il cast**: il **Maggiore Tomás Reyes** (Security & Marines, dalla sala operativa del Ponte 8: nessun corpo nel gioco; voce `michael`; protettivo, secco, dice il nome del
caduto prima del numero) e il **capo di ogni squadra in campo** (una persona del ruolino: il quadro del gioco ne dà nome, grado e genere; voce stabile per nome, mai quella di
Reyes; se il capo cade, il nuovo capo prende la voce della squadra).

**Cosa fanno** (strumenti): `say` (una riga radio: il Maggiore o il capo di una squadra con qualcuno in piedi), `order` (il `marine_order` del gioco: il Maggiore ogni squadra, un
capo solo la sua), `bulkheads` (il `lockdown`: il Maggiore), `remember` (cosa una persona porterebbe con sé per settimane: salvato in `Saved/Campaign/marines.json`, per id del
ruolino), `stay_quiet`. Il risultato di un ordine è la risposta del gioco («no squad of ours is called ...», «the plan has no place ...», «'armory' fits 6 places (...)»):
chi l'ha dato la legge e risponde una volta, con la correzione se c'è.

**Quando** (il codice è meccanica): una notizia (`boarding: ...`) sveglia un impulso dopo un breve assestamento (2 s, al più 5), mai più d'uno ogni 9 s (18 s oltre il bilancio di
0,04 $ ogni dieci minuti); le parole del Capitano non aspettano mai e hanno la risposta per prime; un combattimento senza notizie per 40 s ha **uno sguardo di routine** (il
comandante può agire da sé o tacere); una notizia che *deve* essere detta (il primo contatto, un marine caduto, la fine) toglie lo strumento del silenzio dalla chiamata. Le notizie
del Mandato che sono della plancia (la nave attaccata, il Capitano a terra, il reattore) non sono prese: la plancia le riferisce e la rete le legge.

**Cosa vede il modello** (`ship_state._marines` + `ship_state.boarding`, il `_` tiene il quadro fuori dalla lavagna della plancia): i suoi uomini (le squadre con chiave, nome come
lo dice il Capitano nella sua lingua, capo, forza, dove e cosa fa, se è sotto ordini o in contatto), i nemici noti **con la loro età**, la via probabile verso l'Ingegneria, gli
accessi all'Ingegneria, l'imboscata di base, le paratie (con id), il Capitano (dove, forza, arma, e chi gli sta accanto), il registro della rete (compreso ciò che la plancia ha
detto), gli ordini del Capitano che restano. Non vede nulla del Mandato (`_mandate`). Il prompt è lungo e stabile (la cache del fornitore lo copre: ~5000 token in, 5000 in
cache a ogni impulso), la lingua del Capitano viaggia nel messaggio.

**Cosa sa un comandante** (dal banco, §3): il drill è buono; tutte le squadre alla porta dell'Ingegneria sprecano i corridoi; un assalto si paga in marine; ripiegare regala il
reattore; un luogo fuori dalla lavagna si nomina per tipo o nome e il gioco lo trova o elenca i candidati.

**Costo**: un impulso 0,3-0,7 m$ (una chiamata, 5000 token con la cache); un abbordaggio compresso di 3,5 minuti, 10 impulsi, **0,007 $**; il bilancio (0,04 $ ogni dieci minuti, oltre i quali
l'intervallo raddoppia) tiene anche un abbordaggio lunghissimo sotto 0,25 $ l'ora. Il ruolo `marines` (DeepSeek V4.1 Flash, 520 token, temperatura 0,4, ripiego `chatter`) si cambia con `ASTRA_MODEL_MARINES`.

## 8. File

| File | Cosa |
|---|---|
| `Source/ASTRA/AstraBoardMap.h/.cpp` | la pianta come la vede un soldato (portali, rotta, vista, tacche) |
| `Source/ASTRA/AstraBoardSim.h/.cpp`, `AstraBoardAI.cpp` | la simulazione di squadra (il drill, gli ordini, il Capitano esterno) |
| `Source/ASTRA/AstraBoardSubsystem.h/.cpp`, `AstraBoardEvents.cpp`, `AstraBoardMind.cpp` | l'ospite nel gioco: l'evento, i marine del ruolino, i corpi, le ferite, il Capitano, i rapporti, i comandi (`boarding`, `marine_order`, `lockdown`), il quadro per la mente, la console |
| `Source/ASTRA/AstraCombatant.h/.cpp`, `AstraCombatFx.h/.cpp` | il corpo di un soldato; tracciati, scintille, lampi, suoni (pool: nulla per colpo, nulla mentre la nave è tranquilla) |
| `Source/ASTRA/AstraWeapon.h/.cpp`, `AstraFpsComponent.h/.cpp`, `AstraFpsHud.h/.cpp`, `AstraArmory.h/.cpp` | le armi del Capitano, le braccia, lo schermo, il rastrello |
| `Source/ASTRA/AstraBoardSimCommandlet.h/.cpp`, `tools/boarding.py` | il banco senza grafica (§9) |
| `art/blender/weapons.py`, `tools/ue_scripts/import_weapons.py`, `tools/art/weapon_sounds.py` | le armi: modelli, texture, materiali, mesh con le prese, suoni |
| `mind/astra_mind/marines.py` | la rete dei marine |
| `mind/bench/marines_unit.py` (71 prove), `marines_server.py` (19), `marines_live.py` (29 scene + un abbordaggio), `marines_router.py` (30 frasi) | prove offline e dal vivo |
| `docs/licenze.csv` | AR-181 e M27S (CC-BY: attribuzione) |

**Ganci in file di altri** (piccoli e nominati, ABBORDAGGI): `ASTRACharacter.*` (il componente `Fps`, i legami dei tasti, il passo e il giro con l'arma),
`ASTRAPlayerController.*` (E al rastrello; `IsPadUp()`; la scheda dei tasti «ARMED»), `AstraInput.*` (otto azioni), `AstraDamageModel.*` (`CaptainWounded`, `CaptainContested`),
`AstraCrewRoster.cpp` (la tabella di ferite da arma da fuoco; il cognome Reyes esce dal pool: il Maggiore è uno e il localizzatore deve trovarne uno), `AstraLifeSim.*`,
`AstraLifeSubsystem.*` (`Commandeer`, `ReleaseBodyOf`: la guerra requisisce le persone), `AstraShipSubsystem.*` (i comandi, `SealBulkhead`, `HarmPerson`, `ReactorFailing`,
`boarding` e `_marines` nello stato), `mind/astra_mind/` `models.py`, `context.py`, `router.py`, `crew.py`, `server.py` (il ruolo, il canale, il router, la regola dell'equipaggio, il
filo del server).

## 9. Le prove e le misure

**Il banco senza grafica** (`python3.13 tools/boarding.py run --scenario all|map|rules|duel|squad|flank|board|orders --seeds N [--setup 0..5] [--trace] [--set "MarineSkill=0.8"]`;
usa `UnrealEditor-Cmd -nullrhi`): 16 verifiche, verdetto PASS su **entrambe le piante** (la v1 di 2270 stanze, la v2 di 3234; il banco sceglie breccia e armeria per ciò che sono):
la mappa si costruisce in 141-198 ms, 400 percorsi su 400, i portali sono sulle pareti, le tacche nelle stanze, una parete è una parete, i colpi (nove colpi: 160 morti e 240 a terra
su 400), la morte per dissanguamento a 85 s, la paratia tagliata dopo 24 s, il combattimento è identico dal seme, un duello alla pari 60/40, una squadra in campo aperto e con gli
angoli, l'aggiramento, i combattimenti sulla nave (§3), 0,02-0,07 ms a passo. `orders` aggiunge: nessuno esce dalla pianta sotto qualunque ordine, ogni combattimento finisce, «follow»
raduna, un Capitano a terra è raggiunto dalle due squadre più vicine (10 marine entro 8 m dopo 50 s, 8 combattimenti su 8).

**La mente offline** (`cd mind && .venv/bin/python -m unittest bench.marines_unit bench.marines_server`, 90 prove, 0 $, 20 s): quali eventi sono della rete e quali restano alla
plancia, e che **ogni evento che il gioco può dire è riconosciuto dalla tabella** (i testi si leggono dal sorgente C++); che i campi del quadro e gli argomenti dei comandi sono quelli
che il gioco scrive e prende (letti dal C++); la cadenza (assestamento, intervallo, bilancio, il Capitano non aspetta, lo sguardo di routine, il dopo); il prompt (stabile, i fatti che
le persone possono sapere e nessuno che non possono, la lingua nel messaggio); le voci (chiave o nome della squadra, la voce di ogni capo e il suo cambio, chi non può parlare); gli
ordini (l'autorità, `marine_order` e `lockdown` come li prende il gioco, un rifiuto che torna a chi l'ha dato, una riga dopo un ordine rifiutato non viene detta); un modello che
fallisce o si blocca passa le parole del Capitano all'XO; il canale (il router, la nota all'equipaggio, la cabina di un Falcon tiene la rete di volo); la memoria. L'intera suite offline
della mente (con ASCENSORI di main e la rete dei marine, uniti in una copia di prova): **378 prove verdi**.

**Il router sul canale dei marine** (`python -m bench.marines_router`, 0,002 $): 30 frasi in cinque lingue (ordini a una squadra, al Maggiore, alle paratie, domande, parole per il timoniere,
l'XO, il tattico, Comms, frasi miste): **30 su 30** (mediana 263 ms); la prima versione ne sbagliava una («Reaction Two, assault corridor 5-C» restava in plancia) finché la situazione del
router non ha detto come si chiamano le squadre.

**Dal vivo** (`python -m bench.marines_live [--battle] [--only NOME] [--repeat N] [--temp T]`): 29 scene contro il modello vero, il gioco finto che risponde come il C++, e un abbordaggio
compresso. Ultimo giro completo: 27 su 28 come previsto (la 28ª, «con me», un errore di squadra poi corretto con i nomi detti), tutti i controlli di macchina; le righe sono da
**leggere** (non si controllano con espressioni regolari): in italiano, inglese, spagnolo, francese e tedesco, brevi, il Maggiore e i capisquadra distinti, i caduti chiamati per nome,
nessun ordine detto e non dato nelle scene finali, ordini rifiutati dal gioco ridetti con la correzione. Ripetute (6 volte l'una): «tieni il corridoio» 6 su 6, «con me» 6 su 6, «all'attacco» 6 su 6;
a faccia a faccia con il sergente 7 su 8 (l'ottavo: «teniamo qui» senza l'ordine, su un registro del combattimento che diceva già «hold»). Costo: l'intero giro 0,015 $, l'abbordaggio compreso 0,021 $; con tutte le ripetizioni delle messe a punto, **circa 0,10 $ in totale**.

## 10. Limiti noti

- **Non provato nel gioco**: non ho potuto avviare l'editor né il gioco; il C++ compila e il banco lo prova come codice, ma gli aspetti visivi (il posto delle braccia e del mirino
  rispetto alla camera con il campo di prima persona 70° e la scala 0,6, i mesh delle armi, le animazioni dei soldati, la luce della breccia) e l'integrazione con i livelli veri
  (corpi sul pavimento, porte, il rastrello nell'armeria) si vedono solo lì. Se le armi appaiono sfaccettate: riesportare con `--smooth face` (Blender non scrive i gruppi di smussatura).
- **L'abbordaggio parte da un comando o dalla console**: il collegamento con la guerra (una navetta nemica che aggancia dopo la battaglia) non c'è; la mente può dare
  `boarding` con `_director_command("boarding", {...})` (richiesta al lead, §12).
- **Reyes non ha corpo**: comanda dalla sala operativa; i capisquadra parlano via radio (anche quando sono nella stessa stanza: la voce non cambia).
- **Le armi si importano a mano** (§11): senza gli asset il codice ripiega su barre (il gioco funziona, ma le armi sono parallelepipedi) e i suoni sono muti.
- La presa dell'Ingegneria (`astra.board.takeover_fatal 1`, predefinito) fa cedere il reattore dopo circa 30 s: la fine della nave nel modo che la nave già conosce.
- Il quadro dei marine non conosce i civili: le paratie chiuse tagliano fuori chi c'è dietro (anche i nostri); la mente lo sa, il gioco non porta in salvo nessuno.
- I capisquadra parlano di ciò che il quadro mostra (squadre, contatto, perdite, luoghi, paratie): le munizioni e il morale degli uomini non sono nel quadro, e le urla di battaglia
  (un «contatto!» di un marine qualunque, un «ricarico!») non ci sono: solo le battute dei capisquadra e del Maggiore, a impulsi.
- Il modello a volte nomina la squadra sbagliata quando il Capitano ne dice il numero a parole («Reaction Due»). Il quadro ora lo mostra come lo dice il Capitano («Reaction 2 (said
  "Reaction due")»: da 3 errori su 6 a 0 su 12 nelle ripetizioni), ma l'errore resta possibile: il Capitano lo sente («Reaction Uno: all'attacco») e può correggere.

## 11. Integrazione (per il lead)

1. **Unione**: il ramo `worktree-agent-a744b27da57aae0d4` si unisce a main senza conflitti (provato con `git merge-tree` il 2/10 contro il main di quel giorno). Dopo l'unione compilare
   (`Engine/Build/BatchFiles/Mac/Build.sh ASTRAEditor Mac Development -Project=... -WaitMutex`): i simboli condivisi che uso (`SealBulkhead`, `HarmPerson`, `CaptainWounded`,
   `Commandeer`...) sono miei e arrivano con il ramo; ho controllato che main non abbia rimosso né rinominato niente di ciò che chiamo.
2. **Asset** (una volta, con l'editor chiuso per Blender e aperto per l'import):
   - `blender -b --factory-startup -P art/blender/weapons.py` (legge `art/_downloads/weapons/`, scrive `art/export/weapons/`), poi nell'editor
     `tools/ue.py pyfile tools/ue_scripts/import_weapons.py` (texture, materiale `M_Weapon`, istanze `MI_AR181_*`/`MI_M27S_*`, mesh `SM_AR181`, `SM_AR181_Mag`, `SM_M27S` con le prese);
   - `uv run --with numpy --with soundfile --with scipy python tools/art/weapon_sounds.py` (scrive `art/_cache/audio/SW_*.wav`: nove suoni), poi
     `tools/ue.py py "ONLY=['SW_Rifle_Shot','SW_Pistol_Shot','SW_Gun_Dry','SW_Rifle_Reload','SW_Pistol_Reload','SW_Gun_Draw','SW_Bullet_Impact','SW_Bullet_Whiz','SW_Body_Hit']; exec(open('tools/ue_scripts/import_audio.py').read())"`;
   - gli altri suoni che il codice cerca (`SW_Blast_Inside`, `SW_Sparks`) sono già nel progetto; se mancano il gioco resta muto per quel suono, senza errori.
3. **Provare** (§2): `astra.armory.here` + E; poi `astra.weapons.give` per sparare ovunque; `astra.board.start` in un corridoio; `astra.board.debug 2`; parlare con Reyes.
   Se le braccia o il mirino sono fuori posto: `astra.fps.hip_*`, `astra.fps.ads_*` (i numeri finiti vanno in `AstraFpsComponent.cpp`, in cima).
4. **La mente**: `cd mind && .venv/bin/python -m unittest bench.marines_unit bench.marines_server` (90 prove); dal vivo `python -m bench.marines_live` (0,02 $).
5. **Piante**: la v2 di NAVE-3 ha altri id (`d8_armory_B1` «Marine Armory» e `d8_armory_D1` «Security Armory», nessuna `d7_capacitors_D2`): il gioco sceglie l'armeria per tipo (la prima) e
   la breccia di base con una regola (la stanza più esterna del Ponte 7 nelle sezioni di mezzo); per un'altra: `astra.board.start 1 <id>`.

## 12. Richieste fuori dai miei file

- **Il collegamento con la guerra** (`director.py` o `war_minds.py`): quando una nave nemica è agganciata e abbordante, `await self._director_command("boarding", {"skiffs": 1..3,
  "source": "the Mandate raider Lethe", "warn_s": 45})` (la rete dei marine e la plancia fanno il resto); il giocatore deve vedere la navetta nel campo (VFX: nessun lavoro mio).
- **ASCENSORI** (facoltativo): i soldati passano da un ponte all'altro solo per le **scale** (un ascensore è una vettura che è altrove: la mia rotta non lo percorre, come scelta); le
  scale bastano a collegare tutti i ponti (400 percorsi su 400 sulla pianta v2). Un abbordaggio che sigilla anche gli ascensori (così nessuno li usa per fuggire o per salire)
  sarebbe un `lockdown` esteso al loro sistema: se lo si vuole, è un comando in più che la mente già potrebbe dare.
- **STATO.md / ARCHITETTURA.md**: la rete dei marine come terza rete di persone (§1bis), le chiavi `ASTRA_MARINE_MINDS`, il ruolo `marines`.
- **Il cognome Reyes** è uscito dal pool di VITA (`AstraCrewRoster.cpp`, stessa posizione, `Reynoso`): i ruolini già salvati con quel cognome non cambiano.
