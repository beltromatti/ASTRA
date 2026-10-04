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
| Provare la mira dal harness | `astra.fps.aim 1` tiene giù il tasto destro **attraverso il sistema d'ingresso** (mappa, azione `IA_ASTRA_Aim`, binding del personaggio: la stessa strada del mouse vero), `astra.fps.aim 0` lo lascia; con `direct` salta il sistema d'ingresso. Così `astra.fps.fire 1/0` (tasto sinistro), `astra.fps.reload`, `astra.fps.weapon rifle\|pistol\|holster\|switch`. `astra.fps.info` dice lo stato, **quante volte l'azione è arrivata** (se resta 0 l'ingresso non arriva: non è colpa dell'arma) e dove stanno nell'inquadratura mirino, bocca, palmo sinistro voluto, mani, avambracci e spalle (angoli e «IN VIEW»: dal mirino il mirino posteriore deve stare a 0,0 e le spalle devono essere «out of view»), quanto la mano sinistra dista dal palmo voluto e quanto la presa destra dista dalla tabella (0: l'arma sta dove la tabella la mette); nel log `[Fps] aim: pressed/released` |
| Regolare le braccia | i posti dell'arma e le spalle sono nella tabella (`AstraWeapon.cpp`: `HipPlace/HipTurn`, `AdsPlace`, `LowPlace/LowTurn`, `FpFov`, `GripLHand`, `ShoulderHip*`, `ShoulderAds*`); `astra.fps.hip_x/_y/_z`, `ads_x/_y/_z`, `low_x/_y/_z` **aggiungono** cm ai posti, `astra.fps.shoulder_x/_y/_z` alle spalle e `astra.fps.fp_fov` cambia il campo: le braccia si riposizionano subito; `astra.fps.arms 0` (solo l'arma, il ripiego). **Il banco prova la tabella senza finestra** (§9): `tools/boarding.py run --scenario fps`, e `--fpsset "rifle.hip=76,15.4,-4;rifle.shoulder_l=70,-18,-58"` prova altri numeri prima di toccare la tabella |
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

- **Braccia**: il mannequin **tagliato alle braccia** (`SKM_ASTRA_Arms`, fatto da `tools/ue_scripts/make_fp_arms.py` con Geometry Script: tutto il braccio dalla spalla,
  avambraccio, mano e dita; stesso scheletro e stessi materiali, quindi le animazioni di fucile e pistola del mannequin lo muovono e le prese `HandGrip_*` sono quelle dello
  scheletro). Il corpo intero non andava: con la camera sugli occhi e l'arma dove deve stare sullo schermo, testa, spalle e petto riempivano l'inquadratura (la «forma scura
  curva» sul bordo destro era la testa). La pelle segue **solo le ossa del braccio**: il peso che clavicole e `spine_04` avevano sui vertici vicino alla spalla è dato alle ossa del
  braccio, perché un braccio spostato lontano dal corpo, con quel peso, si strappava in punte lunghe (il banco lo verifica). Se l'asset manca il gioco ripiega sulla mesh intera con la
  testa tolta (`neck_01`).
  - **Come stanno in mano** (`AstraArmsRig.*`, funzioni pure sulle trasformazioni): l'animazione gira su una mesh nascosta (l'arma sta sulla sua presa `HandGrip_R`); quello che si vede è
    una copia (`UPoseableMeshComponent`) in cui le braccia sono **risolte** ogni fotogramma (IK a due ossa, le ossa mantengono la lunghezza): la mano destra resta dove l'animazione la
    tiene (impugna il calcio come l'arma lo porta), la sinistra va al punto voluto dell'arma (`GripLHand`: sotto la metà posteriore del paramano; l'animazione la tiene dov'è la presa del
    fucile Epic, a 6-12 cm da quella del nostro), il gomito si piega da una spalla che sta **sotto il quadro**. Le spalle sono dati della tabella (`ShoulderHip*` dal fianco e abbassata,
    `ShoulderAds*` dal mirino, in mezzo mentre l'arma sale): con l'arma tenuta lontana dalla camera (non più un terzo dello schermo) le spalle di un corpo non la raggiungerebbero,
    e un braccio con la spalla nel quadro mostrerebbe il taglio. L'estremità tagliata sporge 7 cm oltre l'articolazione ed è larga 8: il banco esige l'articolazione ad almeno 11 cm fuori dal quadro,
    anche a 16:10 e sulla via dal fianco al mirino. Il palmo sinistro è dell'arma a meno di 1,5 cm (misurato 0,00) in ogni stato.
  - **Dove sta l'arma** (tabella): dal fianco il mirino posteriore del fucile a 76 cm, 15 a destra, 4 sotto, con la bocca verso il centro e il campo della prima persona a 90° (il fucile non
    è più un terzo dello schermo, e la mano destra e l'avambraccio entrano dal basso); dal mirino a 32 cm **sull'asse** (0° e 0°: la tacca è al centro, misurato a 0,000 cm); abbassata
    (corsa, rimessa) a destra e in basso, la bocca in alto a sinistra, le due mani sull'arma. Il posto è **calcolato** dalla posa della presa destra nell'animazione pronta, con i numeri che
    il **motore** dà (nella tabella: il banco li confronta a ogni giro): la sonda in Python che li aveva misurati prima dava 1,6-2,3 cm in meno e le braccia stavano fuori posto di
    quella quantità (il mirino a 4,5° a destra e 2,1° in alto visto dal lead nel gioco). La posa pronta è tenuta ferma al primo fotogramma (il respiro dell'animazione spostava il mirino di 1,6 cm).
  - **Come si tara**: sul banco, non a occhio: `tools/boarding.py run --scenario fps` (§9) e `--fpsposes FILE` scrive le pose e le braccia risolte dal motore, con cui un renderer in numpy
    (`Saved/scratch`, fuori dal repo) disegna ciò che vede la camera di prima persona per ogni stato. Con `astra.fps.info` nel gioco si controllano gli stessi numeri.
- **Il colpo**: raggio dalla camera con il cono dell'arma (posizione, velocità, salto, apertura del colpo), tracciante breve dal muso, lampo, impatto (metallo, carne), il sibilo
  per chi lo sente passare, il suono; il rinculo alza il mirino e lo fa vagare, l'arma scalcia sulla spalla (molla), poi il mirino ricade in parte.
- **Lo schermo**: mirino che si apre con il cono, colpi, forza (quando ferito o in un combattimento), rosso ai bordi e archi di provenienza di un colpo ricevuto, la croce
  bianca di un colpo a segno (rossa-bianca alla testa), il suggerimento del tasto a portata («E TAKE THE RIFLE AND THE SIDEARM»), il **cartoncino dei tasti** quando si arma (24 s la prima volta,
  6 s ai richiami, non più di uno ogni 90 s): due colonne di tasti su cappucci, l'arma (LMB fuoco, RMB mira, R ricarica, 1 fucile, 2 pistola, Q l'arma di prima, H in fondina) e il movimento
  (WASD, Shift corsa, C accucciato, C tenuto sdraiato, Spazio salto, E usa, F1 la scheda); sta **in alto a sinistra**, fuori da tutto ciò che il controller disegna in basso: i sottotitoli dell'equipaggio
  (fino a tre righe di fino a tre linee: da 60 px dal bordo a circa 310) e l'avviso del cammino (in basso a destra); la prima versione stava in basso al centro e un sottotitolo la copriva.
- **Il costo**: con l'arma in mano il passo cala (0,9; 0,6 dal mirino), il giro dal mirino segue il campo; da seduto, con il tablet alzato, nella lista di un ascensore, a terra
  o morto l'arma non c'è.

### Dove stanno le armi del Capitano e chi gliele porta (`AstraArmory.*`, `AstraBoardArms.cpp`, `AstraFpsComponent.*`; 3/10, dalle partite dell'utente)

Nelle partite dell'utente il Capitano chiese al ponte «l'arma del Capitano» e nessuno poté dargliela: l'ufficiale cercò nel personale e finì per dire che l'armaiolo avrebbe portato
una pistola, ma nulla nel gioco lo faceva (il rack c'era solo in mezzo all'armeria, e l'equipaggio non sapeva dove fosse). Ora ci sono due posti, uno strumento e una riga di contesto.

- **Due posti**, la cui scorta è della nave (`UAstraBoardSubsystem::ArmsPosts`) e di cui il rack e l'armadietto (`AAstraArmoryRack`, che fa vedere ciò che c'è) sono l'immagine mentre il Capitano
  è vicino (nel suo ponte, entro 60 m):
  - il **rack del Marine Armory** (Ponte 8, `d8_armory_B1`): il fucile AR-181 e la pistola M27S. Sta nel corridoio davanti al bancone di consegna dell'armaiolo, a destra del bancone, con la
    schiena alle sbarre della gabbia e la faccia alla porta. Il punto è calcolato dal riquadro della stanza (l'angolo accanto al corridoio, 3 m dentro e 3,6 m di traverso) e **controllato sulla mesh
    vera** (`SM_SHIP_Armory` messa dove la mette il piano, vista dall'alto con il rack disegnato): fuori dall'asse della porta e libero dal panchetto;
  - l'**armadietto del Ready Room** (Ponte 1, `ready_room`, dietro la plancia): una M27S. Sta sulla parete a babordo (la «vicina»), nel tratto di 66 cm tra la seconda carta incorniciata e la porta
    del corridoio, 18 cm di profondità, lo sportello aperto, la pistola appesa a una barra. Anche questo controllato sulla mesh vera (`SM_SHIP_ReadyRoom`).
- **E**: prende ciò che il posto ha e che lui non porta (rack: fucile e pistola; armadietto: la pistola), e se non c'è nulla da prendere rimette ciò che il posto accetta e lui ha. Il suggerimento
  dice quale («E TAKE THE SIDEARM», «E PUT THE WEAPONS BACK»), a vuoto E è di altri (la scala, il letto). Un'arma sola è un **kit parziale** (`UAstraFpsComponent::GiveWeapon`, `Carries`): con la sola
  pistola il tasto 1 dice «NO RIFLE», Q e la rotella non cambiano arma, e il cartoncino dei tasti non ha la riga del fucile. `astra.weapons.givepistol [0]` la dà (o la toglie) dalla console.
- **L'armaiolo** (`issue_weapon {kind: pistol|rifle|kit, who: captain}`): lo strumento dell'XO (`tools.py`) è il comando della nave (`UAstraBoardSubsystem::IssueWeapon`, la porta è quella di
  `boarding`/`marine_order`). L'arma **esce dal rack del Marine Armory all'istante** (il rack la mostra mancante), un marine dell'armeria (l'armaiolo del ruolino: il suo nome sta nell'avviso) la
  porta su di corsa e allo scadere del tempo gli è **in mano**, dove sta, con la riga a schermo («PETTY OFFICER … HANDS YOU THE SIDEARM»), il suono e un evento per l'equipaggio. Il tempo è quello
  della strada: 14 s per firmare l'uscita più il percorso dall'armeria al punto dove il Capitano sta (la mappa dei portali, a 3 m/s), tra 18 e 200 s. Rifiuti con la loro ragione, che il crew
  dice com'è: la porta già, il rack non ne ha (è del Capitano o è nell'armadietto), il Capitano è nell'armeria davanti al rack (E), non è a piedi (Falcon, capsula), una consegna è già in strada.
  Se nel frattempo se la prende da sé, l'arma torna sul rack; se non è a piedi per quattro minuti, anche. Da seduto la consegna arriva ma l'arma sale quando si alza.
- **L'equipaggio lo sa**: `arms` nello stato della nave (cosa porta, dove stanno le armi e cosa tengono, l'armaiolo, la consegna in corso) e una regola nel prompt (`crew.py`, `_RULE_ARMS`: dove stanno,
  l'XO chiama `issue_weapon` e dice UNA riga dal risultato, mai promettere un'arma che lo strumento non ha mandato). Prova offline: `mind/bench/arms_unit.py` (8 test).
- **Provarlo nel gioco**: (1) Ponte 1, Ready Room (dietro la plancia, porta sul corridoio di babordo): entrando, l'armadietto è sulla stessa parete della porta, subito a poppa di essa (tra la porta e la seconda carta incorniciata), a un metro da terra: «E TAKE THE SIDEARM» → pistola in mano e
  cartoncino dei tasti senza il fucile; di nuovo E → rimessa. (2) Dire all'XO «portatemi un'arma» (o «a sidearm»): «<nome> is bringing the sidearm from the Marine Armory…» con i secondi; allo scadere la
  riga a schermo e l'arma in mano. (3) Ponte 8, Marine Armory: il rack a destra del bancone (con la schiena alle sbarre): E → fucile e pistola. Console: `astra.arms.issue pistol|rifle|kit`,
  `astra.weapons.give`, `astra.weapons.givepistol`, `astra.weapons.stow`, `astra.fps.info`.

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
| `Source/ASTRA/AstraArmsRig.h/.cpp`, `tools/ue_scripts/make_fp_arms.py`, `Content/ASTRA/Weapons/SKM_ASTRA_Arms` (LFS) | le braccia: il risolutore a due ossa (funzioni pure), la mesh delle sole braccia con la pelle ripulita |
| `Source/ASTRA/AstraBoardSimCommandlet.h/.cpp`, `tools/boarding.py` | il banco senza grafica (§9), con lo scenario `fps` per le braccia |
| `art/blender/weapons.py`, `tools/ue_scripts/import_weapons.py`, `tools/art/weapon_sounds.py` | le armi: modelli, texture, materiali, mesh con le prese, suoni |
| `mind/astra_mind/marines.py` | la rete dei marine |
| `mind/bench/marines_unit.py` (71 prove), `marines_server.py` (19), `marines_live.py` (29 scene + un abbordaggio), `marines_router.py` (30 frasi) | prove offline e dal vivo |
| `docs/licenze.csv` | AR-181 e M27S (CC-BY: attribuzione) |
| `Source/ASTRA/AstraBoardCraft.h/.cpp`, `AstraBoardFlight.cpp` (F5.2) | le navette Skiff e Kestrel: i dati, il volo, l'aggancio, le regole del mondo (scudo, difesa puntuale, caccia), le sue prove (`astra.board.*`) |
| `Source/ASTRA/AstraBoardAssault.cpp`, `AstraBoardScene.h/.cpp`, `AstraBoardPlans.h/.cpp` (F5.2) | l'ospite dell'assalto: l'ordine, le barche, la scena sulla pianta della classe (o sullo stato che la guerra ha lasciato alla nave), gli esiti, il quadro per le menti |
| `Source/ASTRA/AstraBoardRide.cpp`, `AstraBoardInterior.h/.cpp` (F5.2) | il Capitano che va: la stiva della navetta, i ponti dell'altra nave fatti solidi dal piano, il ritorno |
| `Source/ASTRA/AstraBoardBeam.cpp` (F5.2) | il teletrasporto visto dall'abbordaggio: dove si sbarca accanto ai marine (la domanda), i ponti pronti, chi e' sceso e chi e' stato portato via (§13.10) |

**Ganci in file di altri** (piccoli e nominati, ABBORDAGGI): `ASTRACharacter.*` (il componente `Fps`, i legami dei tasti, il passo e il giro con l'arma),
`ASTRAPlayerController.*` (E al rastrello; `IsPadUp()`; la scheda dei tasti «ARMED»), `AstraInput.*` (otto azioni), `AstraDamageModel.*` (`CaptainWounded`, `CaptainContested`),
`AstraCrewRoster.cpp` (la tabella di ferite da arma da fuoco; il cognome Reyes esce dal pool: il Maggiore è uno e il localizzatore deve trovarne uno), `AstraLifeSim.*`,
`AstraLifeSubsystem.*` (`Commandeer`, `ReleaseBodyOf`: la guerra requisisce le persone), `AstraShipSubsystem.*` (i comandi, `SealBulkhead`, `HarmPerson`, `ReactorFailing`,
`boarding` e `_marines` nello stato), `mind/astra_mind/` `models.py`, `context.py`, `router.py`, `crew.py`, `server.py` (il ruolo, il canale, il router, la regola dell'equipaggio, il
filo del server).

## 9. Le prove e le misure

**Il banco senza grafica** (`python3.13 tools/boarding.py run --scenario all|map|rules|duel|squad|flank|board|orders --seeds N [--setup 0..5] [--trace] [--set "MarineSkill=0.8"]`;
usa `UnrealEditor-Cmd -nullrhi`): 17 verifiche, verdetto PASS su **entrambe le piante** (la v1 di 2270 stanze, la v2 di 3234; il banco sceglie breccia e armeria per ciò che sono):
la mappa si costruisce in 141-198 ms, 400 percorsi su 400, i portali sono sulle pareti, le tacche nelle stanze, una parete è una parete, i colpi (nove colpi: 121 morti e 279 a terra
su 400: un marine muore meno, §13.7), la morte per dissanguamento a 85 s, la paratia tagliata dopo 24 s, il combattimento è identico dal seme, un duello alla pari 60/40, una squadra in campo aperto e con gli
angoli, l'aggiramento, i combattimenti sulla nave (§3), 0,02-0,07 ms a passo. `orders` aggiunge: nessuno esce dalla pianta sotto qualunque ordine, ogni combattimento finisce, «follow»
raduna, un Capitano a terra è raggiunto dalle due squadre più vicine (10 marine entro 8 m dopo 50 s, 8 combattimenti su 8).

**Il banco delle braccia** (`python3.13 tools/boarding.py run --scenario fps`, 20 s, nessuna pianta e nessuna finestra; `--fpsposes FILE` scrive le pose del motore, `--fpsset "..."` prova altri
numeri): 24 prove sulla mesh vera, le animazioni vere e la tabella. Le 161 ossa e la **pelle** (nessuna influenza fuori dalle ossa del braccio); la presa destra nella posa pronta contro la
tabella (meno di 0,2 cm e 0,3°); per ogni arma e stato (fianco, mirino, abbassata): il mirino cade dove la tabella lo mette (0,000 cm), le ossa mantengono le lunghezze, le spalle stanno dove
si mettono, la mano destra è dove l'animazione la tiene, il palmo sinistro è sul punto voluto (meno di 1,5 cm), dal fianco mirino, bocca, palmo e polso destro sono nell'inquadratura a 16:9 e a
16:10, dal mirino la tacca è sull'asse (0°, 0°); le spalle sono fuori dal quadro di almeno 11 cm in ogni stato e sulla via dal fianco al mirino (misurato 12,1 cm); l'estrazione, la ricarica
e lo scatto a vuoto sono risolti in tredici fotogrammi senza rotture. Verdetto **PASS (24 su 24)**; i gomiti dal fianco: sinistro 121° (polso a 48 cm dalla spalla), destro 93° (40 cm).

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
  rispetto alla camera con la scala 0,6 della prima persona (le braccia, 2ª versione: IK, spalle sotto il quadro, campo 90°, pelle ripulita, sono provate dal banco e da rese fuori linea con le pose del motore, non ancora viste nel gioco; la 1ª versione il lead l'ha vista e ne ha dato le misure), i mesh delle armi, le animazioni dei soldati, la luce della breccia) e l'integrazione con i livelli veri
  (corpi sul pavimento, porte, il rastrello nell'armeria) si vedono solo lì. Se le armi appaiono sfaccettate: riesportare con `--smooth face` (Blender non scrive i gruppi di smussatura).
- **L'abbordaggio parte da un comando o dalla console**: il collegamento con la guerra (una navetta nemica che aggancia dopo la battaglia) non c'è; la mente può dare
  `boarding` con `_director_command("boarding", {...})` (richiesta al lead, §12).
- **Reyes non ha corpo**: comanda dalla sala operativa; i capisquadra parlano via radio (anche quando sono nella stessa stanza: la voce non cambia).
- **Gli asset delle armi sono finiti e nel ramo** (§11: `Content/ASTRA/Weapons`, nove suoni `SW_*`, via LFS); se mancassero il codice ripiega su barre (il gioco funziona, le armi sono
  parallelepipedi) e i suoni sono muti. Le armi non sono mai state viste nel gioco: la levigatura delle mesh e il peso dei materiali si giudicano solo lì.
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
2. **Asset**: già fatti e nel ramo (LFS): `Content/ASTRA/Weapons` (16 texture, `M_Weapon` e 5 istanze, `SM_AR181`, `SM_AR181_Mag`, `SM_M27S` con le prese) e nove suoni
   `Content/ASTRA/Audio/SW_*` (`Rifle_Shot`, `Pistol_Shot`, `Gun_Dry`, `Rifle_Reload`, `Pistol_Reload`, `Gun_Draw`, `Bullet_Impact`, `Bullet_Whiz`, `Body_Hit`). Non c'è nulla da
   importare: il primo avvio compila gli shader di `M_Weapon`. Per **rigenerarli** (es. levigatura delle mesh: `--smooth face`) servono i file grezzi, che non stanno in git
   (`art/_downloads/weapons/`: `ar181_frostoise.glb`, `m27s_tuuttipingu.glb`, 119 MB con l'AR-727 non usato; si copiano dal mio worktree
   `/Users/beltromatti/Desktop/ASTRA/.claude/worktrees/agent-a744b27da57aae0d4/art/_downloads/weapons/` finché esiste, o si riscaricano da Sketchfab con le stesse licenze):
   - `blender -b --factory-startup -P art/blender/weapons.py` (scrive `art/export/weapons/`), poi nell'editor `tools/ue.py pyfile tools/ue_scripts/import_weapons.py`;
   - `uv run --with numpy --with soundfile --with scipy python tools/art/weapon_sounds.py` (scrive `art/_cache/audio/SW_*.wav`), poi
     `tools/ue.py py "ONLY=['SW_Rifle_Shot','SW_Pistol_Shot','SW_Gun_Dry','SW_Rifle_Reload','SW_Pistol_Reload','SW_Gun_Draw','SW_Bullet_Impact','SW_Bullet_Whiz','SW_Body_Hit']; exec(open('tools/ue_scripts/import_audio.py').read())"`.
   Gli altri suoni che il codice cerca (`SW_Blast_Inside`, `SW_Sparks`) sono già nel progetto.
3. **Provare** (§2): `astra.armory.here` + E; poi `astra.weapons.give` per sparare ovunque; `astra.board.start` in un corridoio; `astra.board.debug 2`; parlare con Reyes.
   Le braccia: `git lfs pull` (l'asset `SKM_ASTRA_Arms` è stato rifatto), compilare, poi `astra.weapons.give`, `astra.fps.info`, `astra.fps.aim 1` e ancora `astra.fps.info` (il mirino posteriore a 0,0;
   il palmo sinistro a meno di 2 cm dal punto voluto; le spalle «out of view»). Se le braccia o il mirino sono fuori posto: `astra.fps.hip_*`, `astra.fps.ads_*`, `astra.fps.low_*`, `astra.fps.shoulder_*`
   (i numeri finiti vanno nella tabella, `AstraWeapon.cpp`).
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

## 13. F5.2 — le navette: abbordare e farsi abbordare (3/10)

*Il brief è [brief/ABBORDAGGI-2.md](brief/ABBORDAGGI-2.md). Dopo F5.1 l'abbordaggio parte da un comando di prova; qui parte dalla guerra, in tutti e due i versi, con navette vere.*

### 13.1 Le navette (`AstraBoardCraft.*`, `AstraBoardFlight.cpp`, ganci in `AstraBattleSubsystem.*`, `AstraWarCraft.cpp`, `AstraWarShipAI.cpp`, `AstraWarDraw.cpp`)

Due velivoli della battaglia (`CraftKind 3`, volo proprio, nessuna squadriglia): lo **Skiff** del Mandato (10 abbordatori, scafo 140, 220 m/s) e il **Kestrel** dell'Aquila (12 marine, scafo
200, 180 m/s). Hanno uno scafo, si vedono (mesh `SM_CRAFT_MANDATE_Skiff`, `SM_CRAFT_ASTRA_Kestrel`, fatte in Blender: `art/blender/ship3_boarding.py`), la difesa puntuale e i caccia
sparano loro come a ogni velivolo. Quante ne porta ogni classe: Acheron 4 Skiff, Styx 2, Lethe 1; Aquila 2 Kestrel (dal portello del Ponte 8, sul fianco sinistro, sulla pelle dello scafo),
Praetorian 2, Vigilant 1.

Il volo: uscita dal portello, traversata fino a un punto davanti al boccaporto (nel sistema di riferimento del bersaglio: lo segue se gira), avvicinamento lungo l'asse, aggancio (il bersaglio non
può più sparargli: è parte dello scafo), dopo il «tempo di presa» (12 s lo Skiff, 9 il Kestrel) la breccia si apre; a combattimento finito la navetta si stacca e torna. **Regole del mondo,
in codice**: passa la difesa puntuale (non la evita) e ne è colpita (una navetta isolata contro 4 canali arriva 1 volta su 3; contro 2 canali 2 su 5; i caccia in pattuglia le abbattono tutte:
`tools/boarding.py craft`), **non aggancia dove lo scudo di quella faccia regge** (aspetta 18 s fuori dallo scafo e torna indietro), aggancia dove lo scudo è sotto l'8% o la nave non ha energia.
Una navetta abbattuta porta con sé i suoi uomini (i marine sono caduti, con il nome). Gli eventi (`Launched`, `Docked`, `Destroyed`, `Aborted`, `Departed`, `Recovered`, `Lost`) li legge l'ospite.
**Un luogo del sistema non è una nave di questa guerra** (i `bFixture` di SPAZIO-VIVO: Keeper Station, l'Arsenal, la raffineria di Tiberius, la miniera di Ceres): nessuna barca vola contro uno, nessuna
parte da uno. `AssessBoarding`, `LaunchBoarding`, l'ordine in coda e `StartAssault` lo rifiutano con la ragione («X is a place of the system (a station), not a ship in this war: nobody docks a
boat at her or flies one from her»); `ListShipFacts` non li elenca, e per questo non compaiono tra le navi abbordabili che le menti leggono. Provato dal banco (`tools/boarding.py assault --setup
fixture`: una nave fatta luogo con `astra.board.fixture`, perché il banco della guerra non ha lo spazio vivo).

### 13.2 L'ospite: una scena sola alla volta (`AstraBoardAssault.cpp`, `AstraBoardSubsystem.*`)

`UAstraBoardSubsystem::StartAssault` (il comando esteso `boarding`, §13.4) dà l'ordine; `TickAssault` legge ciò che le navette fanno e ne fa il combattimento. **Un ordine alla volta** (un
secondo è rifiutato con la ragione), su **una scena** (la mappa e la pianta in cui si combatte):

- **In entrata** (le navette del Mandato sull'Aquila): la scena sono i **suoi ponti** (la mappa dei soldati della sua pianta, i corpi, il Capitano, le paratie: il combattimento di F5.1).
  Parte al **primo Skiff uscito** (allarme: i marine chiamati, le paratie di sezione chiuse intorno ai portelli, allarme rosso); ogni Skiff che aggancia apre **la sua breccia** (un anello
  luminoso, la scintilla, il suono) in un **airlock** dell'Aquila (i suoi portelli sono i suoi 40 airlock sui due fianchi: il muro esterno della pianta sta ~4,5 m dentro la pelle della mesh,
  misurata con la mesh generata: la navetta si aggancia alla pelle, la breccia è nella stanza); gli abbordatori entrano da lì. Uno Skiff abbattuto porta con sé i suoi dieci (`LoseParty`),
  uno rimandato indietro dallo scudo no (`RecallParty`); se nessuno arriva, la scena finisce con «not one boarder reached the ship». A fine combattimento le navette si staccano e tornano.
- **In uscita** (i marine dell'Aquila su una nave): i marine del ruolino che vanno (i più vicini al portello, svegli, i sergenti a capo di ogni squadra; il Maggiore resta alla rete) escono
  dalla vita della nave (`SetAway`), i Kestrel partono dopo ~25 s, e la scena è la **pianta della classe della nave abbordata** (`AstraBoardPlans::Load`, in lavoro su un worker la prima volta),
  fatta girare dalla sola simulazione: i difensori sono la gente che la guerra ha lasciato alla nave dove la tiene (§13.6: `FleetSnapshot`; senza un interno, la guarnigione del piano:
  posti di guardia, equipaggio che accorre, paratie chiuse), i nostri a squadre di sei da ogni portello. Niente corpi né Capitano (finché non va: §13.5). I caduti sono nominati e vanno al ruolino
  (`HarmPerson`), i feriti sono portati alla navetta (§13.7) e in Medbay; a fine scena i marine tornano nell'hangar con il loro Kestrel (`PlaceTransported`, e VITA ricorda la navetta, non un
  teletrasporto). Se la nave cade: `CaptureShip` (è nostra, un relitto con un equipaggio di preda) e la riga «her commander and the survivors of her crew are in custody».
- Le navi dell'Aquila abbordate dal Mandato (una consorte) seguono la stessa strada remota (attaccanti del Mandato, difensori dell'equipaggio della classe).

Il mondo dentro la simulazione (`AstraBoardSim.*`): le **squadre per navetta** (`LandParty`: gli uomini aspettano nella navetta, entrano al `ReleaseParty` dell'aggancio, muoiono con lei
(`LoseParty`) o non entrano mai (`RecallParty`)), un portello per squadra (`FSquad::BreachComp`: il ritiro e la colonna), i tempi limite contati dal primo uomo a bordo (`Mission.StartedS`).

### 13.3 La guerra decide: gli strumenti e il contesto (nessun filtro sulle parole)

- **Mandato**: `board` (ammiraglio e comandanti di gruppo, `war_minds.py`): `{target, carrier, boats, face, objective, action: launch|call_off, reason}`. Nel quadro «YOUR BOARDING BOATS»: i
  suoi portatori con gli Skiff liberi, le navi a cui una barca potrebbe agganciarsi **ora** (nessuna energia, o le facce a scudo giù, i canali della difesa puntuale, i caccia intorno, la distanza)
  e quante altre sono a scudi alzati; durante un assalto: dove sta ogni barca, e quanti dei suoi uomini combattono. La dottrina (testo stabile) dice come si perdono le navette.
- **Un'operazione in corso è dell'ammiraglio, chiunque abbia mandato le barche** (3/10, dal primo giro nel gioco: l'ammiraglio richiamò dopo 3 s le barche di un assalto lanciato dalla console, senza dire
  perché; la ragione dello strumento `board`, che lo schema esige, veniva scartata sulla strada del gioco). Ora il comando porta `by` e `reason` (anche per `call_off`); l'assalto ricorda chi l'ha
  mandato e perché e che cosa le barche incontrano al portello com'era al lancio (`met_at_launch`: lo scudo sulla faccia, i canali della difesa puntuale, i caccia, gli uomini); il quadro
  dell'ammiraglio dice «YOUR OPERATION, assault 1, 3 s old: Raider (yours) is boarding the Aquila; sent by <chi>, who gave this reason: "..."» (o, senza ragione, «on the standing plan: no
  reason is recorded: it stands until what you see below gives you one to stop it»), cosa le barche hanno incontrato, e per ogni nave abbordabile cosa e' sulla strada delle barche («nothing is in
  the boats' way (no shield on those faces, no point defence, no craft)»). La dottrina (stabile) dice di chi è l'operazione, su cosa la si richiama (barche abbattute più in fretta di come
  agganciano, uno scudo salito sulla faccia, boarders battuti, un obiettivo reso inutile: mai un dubbio sulle probabilità né un ordine che non si è dato) e che il momento migliore per abbordare,
  con lo scudo giù e la difesa muta, non è mai quello del richiamo. **Il richiamo porta chi e perché**: l'evento per il ponte è «X recalls her boats: <ragione>» (un rapporto: l'XO lo dice con le
  parole dell'ammiraglio, non solo «le barche sono tornate»). `astra.board.options [0|1]` scrive nel log il JSON che l'ammiraglio legge; `astra.board.recall <chi> <ragione>` lo prova.
- **Aquila**: `board_ship` (l'XO, solo su ordine del Capitano): `{target, boats, face, objective, marines, action: launch|call_off}`; nello stato `boarding_boats` (i Kestrel liberi, i marine
  pronti), `boarding_options` (le navi agganciabili ora, e perché), `boarding` (`.assault`: le barche, dove sono). La risposta del gioco porta i fatti (a quali portelli, in quanto tempo, se lo
  scudo di quella faccia regge, la difesa puntuale, i caccia): l'XO li dice, non promette.
- **Rete dei marine** (`marines.py`): il ruolo `attacking` (il quadro dice `role`), il compito `withdraw` (l'uscita dal portello alla barca), le frasi nuove del gioco, il prompt stabile con
  la sezione dell'assalto. I banchi: `marines_unit` (77), `war_minds_unit` (63), `assault_unit` (10), tutta la suite offline verde.

### 13.4 L'interfaccia per CAMPAGNA e per le menti

`await self._director_command("boarding", {...})` (la stessa porta di prima): `{direction: "in"|"out", target, source, craft (1..4), boarders, objective: engineering|bridge|captain|armory|medbay|brig|comms|hangar|<id>,
face: port|starboard|dorsal|ventral|bow|stern, breach: <id di un portello>, lockdown, captain, by, instant}`. Senza `direction` (o con `instant`) è l'abbordaggio di F5.1, che «semplicemente
accade». `{"action":"end"}` lo chiude. Le navi si dicono come i contatti: id (T-30), nome, o `aquila`. Risponde con i fatti: partito (ordine, portatore, portelli, tempo, avvertimenti), o rifiutato
con la ragione. L'esito è un evento `boarding: ...` (i testi di `Tell`, letti dalla rete dei marine e dal regista): «X is ours: ... her commander and the survivors of her crew are in custody»,
«the boarding of X has failed», «the boarders are beaten», «the boarders hold Main Engineering», «not one boarder reached the ship».

### 13.5 Il Capitano che va (`AstraBoardRide.cpp`, `AstraBoardInterior.*`; 3/10)

Con `captain: true` (all'XO: «vengo anch'io»; il comando `boarding`; in console la parola `ride`) il Capitano sale nel **primo Kestrel** con i suoi marine. Solo se è a piedi (non in un Falcon,
in una capsula, sul pianeta) e nessun altro giro è in corso; l'avvertimento nella risposta del gioco dice che se la navetta è abbattuta, lui è dentro. Nessuna navigazione: il giro è un titolo di
velivolo e la dissolvenza.

| Tempo | Che cosa succede |
|---|---|
| **Out** (la barca vola) | dissolvenza (0,9 s); è nella **stiva truppe** del Kestrel (una stanza sua: 6 x 3 x 2,5 m, una panca per lato, una lampada rossa, in una zona del mondo a z = -1,7e8); guarda intorno, non cammina; una riga lo avverte («KESTREL 1 · 12 MARINES · THE HULL IN 1:09», poi «CLOSING ON THE HATCH»). Se la barca è abbattuta: «the Captain was in it» (la fine che la nave già conosce: abbandono, inchiesta) |
| **Aboard** (la barca ha aggancio e breccia) | dissolvenza: è nel **portello d'abbordaggio** della nave nemica, il fucile in mano e i marine intorno. L'interno è **geometria vera** fatta sul momento dal piano della classe (pavimenti, soffitti, pareti con i varchi delle porte e dei passaggi aperti, cornici, un'anta in ogni paratia stagna che si chiude come nel combattimento, strisce di luce; istanze di cubi con i materiali di ASTRA, `MI_ASTRA_Structure/Floor/Trim/Light`), qualche stanza alla volta intorno a lui, in una zona del mondo sua (z = -1,6e8) con sei luci che lo seguono; l'attore sta alla zona e le istanze sono nel suo sistema (il piano in cm: le istanze di un ISM sono float rispetto al componente e a 1600 km dall'origine un float va a passi di 16 cm, pareti e pavimenti non si sarebbero toccati), pareti, pavimenti, soffitti, cornici e ante gettano ombra (sopra non c'è uno scafo che tenga fuori la luce della stella). I corpi dei difensori, i colpi e le ferite come sui ponti dell'Aquila. **Scale e ascensori**: ci si ferma ~1 s su una piastra illuminata e si passa al ponte vicino. Se cade e la catena della nave lo porta via, si risveglia in Medbay e i ponti spariscono; se è perduto è la fine che la nave già conosce |
| **Home** (finita la lotta, o richiamo) | «the Captain is called back to the boat»: dissolvenza, i ponti spariscono, è di nuovo nella stiva per il volo di ritorno e, a navetta rientrata, nell'hangar del Ponte 8 (il ponte dell'hangar è chiesto allo streaming mentre la navetta vola e, se non c'è ancora, lui aspetta al buio fino a sei secondi e poi viene caricato di colpo: non lo si posa su un pavimento che non c'è) |

L'equipaggio sa dove sta (`CaptainWhereText`: nello stato della nave, nel suo badge e nel «posto» del cruscotto: «AWAY · WITH THE MARINES»); l'XO ha il comando dell'Aquila e il Capitano parla alla
plancia con il suo comunicatore. Il Maggiore Reyes ha la rete dei marine.

**Il teletrasporto** è l'altra strada, dentro e fuori, con tutte le sue regole: §13.10. La navetta resta la strada di andata e di ritorno quando il fascio è bloccato («Chief, beam me up» rifiutata per uno
scudo o un disturbo: il Capo dice perché e il Kestrel al portello è lì) o quando nessuna stanza dei marine è libera dal Mandato, e resta l'unica strada su una nave che i marine non stanno abbordando.

**Le piante vere.** Le sette classi di FLOTTA-VIVA hanno sale che coprono più ponti (cannoni, sale macchine, hangar) con **due porte una sopra l'altra** sullo stesso muro: il primo costruttore
(muri interi con un buco per porta) chiudeva una porta con il pezzo di muro dell'altra. Ora un muro si fa per tratti tra i bordi delle aperture, con l'altezza meno i vuoti che vi sono, e una porta
in una sala alta sta dove sta il pavimento più alto (`FIbOpening::Bot`): `tools/boarding.py run --scenario interior` cammina ogni passaggio di ogni piano (a ginocchio e a petto, cinque linee nella
larghezza della porta) e prova a uscire da ogni parete senza porta: **sette classi su sette, 0 passaggi chiusi, 0 pareti che perdono** (la Praetorian: 12 639 solidi, costruiti in 1 ms). Una
porta alta nel muro di una sala più bassa è una porta in aria: si entra cadendo, non si risale (c'è l'altra porta, a livello del suolo, e le scale).

### 13.6 La nave com'è stata lasciata dalla guerra (richiesta di FLOTTA-VIVA)

All'inizio di uno sbarco su una nave che ha un interno (`UAstraBattleSubsystem::InsideOf`, che è `FleetSnapshot` di FLOTTA-VIVA reso pubblico: le stanze non com'erano costruite, le paratie chiuse, le
persone vive con stanza, posto, ruolo e ferite, i nominati e chi comanda) la scena parte dallo **stato in cui la guerra l'ha lasciata**, non da una nave nuova (`AstraBoardScene::Build` con
`FSpec::Inside`):

- **Chi tiene la nave** sono quelle persone dove la guerra le tiene: i marine della nave (ruolo `Marine`, `MarineDock`) tutti armati (90%), gli altri in piedi per quota (80%, al più 340 in tutto: un
  equipaggio di mille non combatte tutto, e il passo della simulazione cresce con gli uomini), gli ufficiali sempre armati e con il loro nome e grado (il capitano è chi dice la guerra; se è caduto, chi ha il
  comando lo dice il rapporto). Squadre di sei per stanza che tengono la stanza; i marine della nave vanno incontro all'allarme.
- **I feriti** giacciono dove sono (vivi, contati tra i feriti, non muoiono nel combattimento: i loro medici li hanno), le **paratie chiuse** sono quelle che la guerra ha chiuso (non il 30% a caso).
- **Le stanze**: senza corrente (< 45%) le strisce sono il rosso delle luci d'emergenza e la torcia del fucile si accende dove manca la luce; dove brucia, tre luci arancioni che tremano sulle più
  vicine. Più della metà delle stanze al buio: la nave è un relitto (stile «Emergency» anche nei corridoi con corrente).
- **Una nave disabilitata** (senza energia) resiste solo con i suoi marine (50%) e con l'8% degli altri: quelli ai quadri spenti non hanno più nulla per cui combattere. Senza un interno (mai colpita
  attraverso le piastre; il caso dei relitti fatti con `astra.board.disable`): la guarnigione del piano al 80% e le paratie a caso; se è disabilitata, i marine di bordo al 50% e il 6% degli altri.
- Il rapporto della prima riga dice la verità: «the war has left her 75 of her people under arms (298 more at their stations, 12 lying wounded) with 31 of her crew already dead; Commander X (executive
  officer) has the conn; 4 of her pressure bulkheads are shut».
- **Lo stesso file**: il caricatore del piano usa il risolutore di FLOTTA-VIVA (`FAstraFleetPlans::PathFor`: Content/ASTRA/Data/plans, poi data/ship/plans), le stanze della guerra e quelle dello sbarco
  sono le stesse nello stesso ordine (controllato a ogni scena: numero e id di alcune stanze; se non coincidono si ricade sulla guarnigione). Le **piante di ripiego sono tolte**.
- **Non scritto indietro**: i morti dello sbarco non tornano nell'interno della nave in guerra (la nave abbordata resta con i suoi in guerra finché `CaptureShip` non la rende nostra). Una richiesta a
  FLOTTA-VIVA: `FleetBoardingResult(ShipId, killed, wounded)`.

Il banco: `python3.13 tools/boarding.py run --scenario war [--class acheron] [--seeds 20]` spara a un interno di FLOTTA-VIVA (0, 14, 60, 220 colpi, e 220 colpi con la nave disabilitata), ne prende
la fotografia come il gioco e manda i marine: Acheron intera 308 armati, 17,9 marine su 24 persi (6,8 morti); disabilitata 35 armati, **3,4 persi (0,9 morti)**; Styx e Vigilant disabilitate 0-0,2.
La Praetorian disabilitata ha ancora 811 persone in piedi e 107 armati: 24 marine non la prendono (28 su 30 tenuta).

### 13.7 I feriti, e gli sbarchi che non finivano

- **I feriti sono portati alla navetta** (`FTuning::bEvacuate`, acceso dall'ospite per gli sbarchi con le navette, da una parte e dall'altra): un uomo a terra che nessun nemico vede (a meno di 15 m) è
  raggiunto dal compagno libero più vicino (mai il capo squadra, mai se la squadra resterebbe con meno di tre), che lo alza (2,5 s), lo porta al portello da cui la squadra è entrata (1,15 m/s) e
  alla navetta; **non sanguina mentre è portato** (e il primo soccorso gli dà 45 s); il suo corpo non è sul pavimento. Chi porta non combatte. Se chi porta cade, il ferito è posato dove cadde. Sotto
  il fuoco nessuno viene, e un uomo che cade nel campo di una lotta che non finisce può morire dissanguato. Gli eventi (`Carried`) arrivano all'ospite: il ruolino ha il ferito
  (`HarmPerson`), il rapporto dice «X, wounded, has been carried back to the boat by Y», la rete dei marine lo ha nel registro. Nei bilanci i feriti sono quelli a terra più i portati via
  («marines: 5 dead, 8 wounded»). Il prompt dei marine lo dice.
- **Un marine muore meno** (`LethalScale[Aquila] = 0,75`: l'armatura e la chirurgia da campo): nove colpi su 400 marine ora lasciano 121 morti e 279 a terra (erano 160 e 240).
- **Un relitto costa pochi feriti, uno sbarco contrastato perdite vere**: Acheron disabilitata (dalla guerra) 3,4 persi su 24, di cui 0,9 morti; una nave con la sua gente tutta ai posti 17,9 persi (6,8 morti),
  e per ingegneria (a 90 m dai portelli) 23,6 su 24: gli sbarchi sono una scelta, non una passeggiata.
- **Gli sbarchi che non finivano** (1 su 20 sul Vigilant con il seme 1; con le altre mete fino a 8 su 20): non era la pianta, era la simulazione, tre cose che le piante a più ponti hanno
  fatto vedere: (1) le squadre d'attacco **tenevano il vicinato** dell'obiettivo (gli angoli della stanza *e delle stanze vicine*) e restavano nel corridoio fuori dalla porta senza mai entrare:
  la presa dell'obiettivo (due uomini dentro per 70 s) non scattava, ora l'obiettivo si tiene **da dentro** (`HoldAround(..., bInside)`); (2) le distanze verso il bersaglio erano in 2D: su una
  nave a più ponti chi sta sopra l'obiettivo si crede arrivato e smette di muoversi, ora sono in 3D; (3) l'ultimo uomo di una squadra non poteva tenere da solo (servivano due): ora uno basta se
  non ne restano altri. Esito: Vigilant, i sei scenari 20 su 20 finiti (un seme su 120 non finisce); Acheron un solo scenario (ingegneria, a 90 m) ne lascia 3 su 20, e li perde.

### 13.8 Come si prova

| Cosa | Come |
|---|---|
| Il banco delle navette (volo, difesa, aggancio) | `python3.13 tools/boarding.py craft [--setup out\|shield\|pd\|pd2\|cap] [--seeds N] [--trace]` (senza grafica: la battaglia di GUERRA a testa bassa) |
| Il banco degli assalti (l'ospite, le scene, gli esiti) | `python3.13 tools/boarding.py assault [--setup in\|in_shield\|in_recall\|out\|out_ride\|out_war\|out_pd\|fixture\|all]`: il mondo del banco ha la vita (i marine del ruolino) e la guerra; le piante si leggono su un worker, i comandi si danno tardi (11 000 s). `out_ride`: il Capitano (di prova, senza pawn) sale, i ponti si fanno solidi, torna; `out_war`: una nave presa a colpi (`astra.war.fleet pound`), la scena dallo stato della guerra e il Capitano dentro |
| Le piante di FLOTTA-VIVA come i soldati le vedono | `python3.13 tools/boarding.py run --scenario plans` (7 su 7: ogni portello ha una strada al ponte, all'ingegneria, all'alloggio, all'armeria, all'infermeria, alla prigione, alle comunicazioni e all'hangar) |
| Lo sbarco su una pianta di classe (24 marine in due Kestrel, sei scenari, i morti e i feriti, i semi che non finiscono) | `python3.13 tools/boarding.py run --scenario attack --class acheron\|styx\|lethe\|vigilant\|praetorian [--seeds 20]` |
| Lo sbarco su una nave presa a colpi | `python3.13 tools/boarding.py run --scenario war --class acheron [--setup 0..4]` |
| L'interno solido di ogni classe | `python3.13 tools/boarding.py run --scenario interior [--class X] [--dump DIR]`; l'anteprima: `blender -b -P Saved/scratch/interior_view.py -- DIR/interior_X.json prefisso [portello]` (non nel repo) |
| Il quadro dell'ammiraglio | `astra.board.options 1` (il JSON che il Mandato legge delle barche e dell'operazione in corso), `astra.board.recall Archon_Varek_Solm <la ragione a parole>` (il richiamo con chi e perché); banco `tools/boarding.py assault --setup in_recall` |
| Un luogo del sistema non si abborda | `tools/boarding.py assault --setup fixture` (`astra.board.fixture <nave>` la fa luogo; nel gioco, con SPAZIO-VIVO, `astra.board.assault out K-1` risponde con la ragione) |
| Il teletrasporto dentro e fuori | `python3.13 tools/transport.py run --scenario world` (le prove «boarded: ...»: i marine sbarcano con i Kestrel, poi il Capitano e due marine dentro e fuori col fascio; dentro rifiutato da uno scudo nostro e da uno loro, fuori rifiutato da un disturbatore, 168 interrogazioni durante la lotta (ogni secondo di una battaglia di 240 s) senza che una sola offra una stanza con un soldato del Mandato dentro o in vista del punto); nel gioco `astra.xport.send captain <contatto> window` e `astra.xport.send captain "pad 1" window` (§13.10) |
| In entrata nel gioco | `astra.cmd set_shields {'mode':'off'}` (o aprire un settore con il fuoco), `astra.board.pd aquila 0` (la difesa puntuale altrimenti abbatte gli Skiff), `astra.board.assault in [portatore] [bersaglio] [barche] [faccia] [obiettivo]` (il portatore migliore si sceglie da solo); `astra.board.end` |
| In uscita nel gioco | `astra.board.disable <nave>` (un relitto) o i cannoni sulla sua faccia, poi `astra.board.assault out <nave> [portatore] [barche] [faccia] [obiettivo] [ride]` (o all'XO: «abborda l'Acheron», `board_ship`, e «vengo anch'io» per il Capitano) |
| Il Capitano nel gioco | `astra.board.assault out <nave> - 2 port - ride` (a piedi, sul ponte o dove si sta: la dissolvenza, la stiva, i ponti nemici); `astra.board.testcaptain <x> <y> <z> [yaw] \| off` per le prove senza pawn |
| Dal comando | `astra.board.cmd boarding {"direction":"out","target":"T-30","craft":2,"face":"port","objective":"captain","captain":true}` |
| Le navette a mano | `astra.board.craft <portatore> <bersaglio> [n] [faccia] [uomini]`, `astra.board.depart <ordine>`, `astra.board.assess <portatore> <bersaglio>`, `astra.board.strip\|shield\|disable\|pd <nave>` (gli stati dei bersagli) |
| Il quadro | `astra.board.info` (anche l'assalto), `astra.board.picture` (la lavagna dei marine) |

### 13.9 Limiti noti (F5.2) e richieste

- **Non provato nel gioco**: come F5.1, il banco prova il codice (volo, scene, esiti, strumenti, il Capitano di prova senza pawn, la geometria camminata dalle rotte della simulazione); il colpo
  d'occhio (anello della breccia su un airlock, i Kestrel che escono dal fianco, la dissolvenza, la stiva, i ponti solidi con i loro materiali e le loro luci) si vede solo lì. I materiali sono quelli
  dei cubi di ASTRA (`MI_ASTRA_*`): nessuna mesh di corridoio, nessuna porta che si apre (le porte sono varchi con la loro cornice).
- **Zone del mondo**: i ponti nemici stanno a z = -1,6e8 cm, la stiva a -1,7e8 (il pianeta a -1e8); come il pianeta, dipende dalla doppia precisione del mondo; il KillZ del livello è -1e10.
- **Una porta alta in una sala che copre più ponti è una porta in aria** (si cade dentro, non si risale); le scale e gli ascensori sono piastre che portano al ponte vicino con una sosta di ~1 s, non
  rampe.
- **Un abbordaggio alla volta**; se i nostri marine sono su una nave il Mandato non può abbordare l'Aquila nello stesso momento (rifiutato con la ragione).
- **I morti dello sbarco non tornano all'interno della nave in guerra** (richiesta a FLOTTA-VIVA: `FleetBoardingResult`); a fine sbarco la nave è nostra (`CaptureShip`) o resta com'era.
- **Il teletrasporto porta il Capitano solo su una nave che i marine stanno abbordando** (la sola di cui c'è un interno in libreria) e solo mentre una barca nostra è al portello; su ogni altra nave il
  Capitano resta rifiutato con la ragione. Un marine o una persona va su una nave qualunque come sempre (resta «away», senza un corpo); sulla nave abbordata un marine del ruolino entra nella lotta,
  gli altri no (la simulazione non ha altri soldati). Le modifiche ai file del teletrasporto sono elencate in §13.10.
- **Il Capitano che cade a bordo di un'altra nave** ha la fine già nota; non c'è un salvataggio con una navetta che torni a prenderlo (se nessuna barca resta, è perduto).
- **Richieste fuori dai miei file** (fatte da me, additive): `UAstraBattleSubsystem::InsideOf` (AstraBattleSubsystem.h) per leggere lo stato della guerra; `FAstraLifeSim::SetAway/PlaceTransported`
  con la frase di memoria opzionale (i marine ricordano la navetta); `Source/ASTRA/AstraShipSubsystem.cpp` (tre ritorni anticipati per dove sta il Capitano e `board_ship`); i file del teletrasporto
  (§13.10, su via libera del lead: `AstraTransporterWorld.cpp`, `AstraTransporterSubsystem.h/.cpp`, `AstraTransporterCard.cpp`, `AstraTransportBench.cpp`, `mind/astra_mind/transporter.py`, `crew.py`,
  `docs/TELETRASPORTO.md`).
- **Il FallGuard** (`AstraFallGuard.cpp`, del lead): conserva i posti in cui il Capitano ha camminato negli ultimi ~6 s e, se cade più di 2,4 s, lo rimette lì: dopo un teletrasporto lontano (la zona dei ponti
  nemici, la stiva, il pianeta) la lista ha i posti di prima, e una caduta rimetterebbe il Capitano là. Richiesta: svuotare la lista quando il Capitano si sposta di più di ~500 m tra due passi (un teletrasporto,
  mai una camminata); tre righe. Non l'ho toccato.

### 13.10 Il teletrasporto: il Capitano e i marine dentro e fuori (3/10, su richiesta del lead; `AstraBoardBeam.cpp`, e nei file di TELETRASPORTO le modifiche elencate qui sotto)

TELETRASPORTO rifiutava il Capitano su un'altra nave perché «nessun interno in libreria». Dove i marine dell'Aquila combattono a bordo di una nave, l'interno c'è (i suoi ponti si fanno solidi sul momento
dal piano della classe: §13.5) e i marine tengono una stanza: lì il fascio può posarlo. **Tutte le regole fisiche del fascio restano quelle di TELETRASPORTO** e valgono identiche per l'andata e il
ritorno: lo scudo sulla faccia che il fascio attraversa (il nostro: una finestra scudi dell'ordine del Capitano; il loro: sotto il 5% o la nave senza energia, con la ragione «shields_theirs»), la portata, il
disturbo lungo la linea (con la ragione `[jam]`), la manovra dell'Aquila, il campo del Gate, la stanza dei trasporti. Quello che il fascio non sa lo sa l'abbordaggio:

- **Dove si sbarca** (`UAstraBoardSubsystem::BeamAboardQuery`): una stanza **che i marine tengono**: uno dei nostri in piedi dentro, **nessun nemico che possa combattere dentro o vedere il punto**
  (un soldato del Mandato in vista entro 32 m, porte come sono), con aria (la soglia è quella del teletrasporto: 60%), senza fuoco né fumo, e i punti **accanto ai marine**, sul pavimento libero a più
  di 95 cm da chiunque (anche da un caduto). **Mai in uno scompartimento che il Mandato tiene, mai senza aria**: nessuna parola del Capitano supera questa regola (non c'è un `override`). Per il Capitano in
  più **una barca nostra al portello** (aggancio o uomini entrati): è la strada di casa se il fascio è bloccato. Senza un abbordaggio dei marine su quella nave il Capitano è rifiutato («no marine of ours
  is fighting aboard her: her decks are not in the pattern library, and there is nobody to materialize beside; land the marines first»); una persona va sulla nave come sempre.
- **L'ordine** (`MakeRequest`): i punti dal gioco al posto del rifiuto; se nessuna stanza è libera il rifiuto elenca **tutte** le ragioni insieme, quelle del fascio e `[arrival]` la propria. Nel
  **buffer** l'arrivo è chiesto di nuovo ogni passo (la lotta si muove mentre lo schema aspetta): se non c'è una stanza lo schema **aspetta lì** (entro i 90 s del buffer, poi è ricomposto sulle pedane da
  cui è partito) e il Capo lo dice; se l'abbordaggio è finito nel frattempo, è ricomposto subito. I ponti attorno al punto sono fatti solidi mentre lo schema è nel buffer (`BeamPrepare`): quando
  arriva c'è un pavimento.
- **Il Capitano a bordo** (`BeamedAboard`): è nel combattimento come chi è venuto in barca (stesso `Ride = Aboard`, stessi corpi, colpi e ferite, la catena della nave se cade), la barca al portello è
  la sua strada di casa. La riga a schermo, dopo 7 s: «TO COME HOME: ASK THE CHIEF TO BEAM YOU UP, OR TELL THE XO TO CALL OFF THE BOARDING». Il teletrasporto lo sa **lontano dall'Aquila** (`CaptainFeet`:
  «via» come uno sul pianeta), e «Chief, beam me up» è un `transport` di `captain` verso `a pad` (il Capo sa dov'è: `from` può mancare); mentre il suo schema è nel fascio che lo porta via è **fuori dalla
  lotta** (`SetCaptainInBeam`) e i suoi ponti restano finché lo schema non è posato; un fascio fallito (schema ricomposto sul posto) lo rimette nella lotta. Nella stiva di una barca in volo il fascio
  non aggancia («no beam locks through a boat's hull»).
- **I marine del ruolino** (`BeamedAboard/BeamedOff`): «marines 6» o per nome, dentro: uomini della simulazione in una squadra «Beamed Marines» che va all'obiettivo con gli altri; fuori («away team»,
  per nome o numero, anche chi è sbarcato dai Kestrel): escono dalla lotta (a terra sono portati via vivi e vanno in Medbay come i portati alla barca). Chi non è un marine del ruolino va via nave
  come sempre (senza corpo).
- **Quello che il Capo legge** (`ship_state.transporter.boarded_by_our_marines`): la nave, dove sta il Capitano, la strada dentro (cosa la ferma, cosa la libera, in che stanza sbarcherebbe e accanto a quanti
  marine) e, con lui a bordo, la strada fuori. Il suo prompt (stabile) dice che questa è la sola nave di cui ha l'interno, che mai si sbarca in uno scompartimento del Mandato né senza aria, che il Capitano va
  solo con una barca al portello, che «beam me up» è lo stesso fascio con le stesse regole e che, se è bloccato, il Kestrel è la strada di casa.

**Cosa ho cambiato nei file di TELETRASPORTO** (additivo, su via libera del lead del 3/10): `AstraTransporterWorld.cpp` (`CaptainFeet`: «via» sui ponti dell'altra nave, nessun fascio nella stiva di una barca;
`ResolveSubjects`: dove sta via il Capitano e un marine sbarcato; `MakeRequest`: i punti dal gioco al posto del rifiuto del Capitano; `BoardedArrival` nuova; `Preflight` con il blocco `arrival`),
`AstraTransporterSubsystem.h/.cpp` (due campi del trasporto e `ArrivalWhy`; il buffer; `Depart`, `SetSubjectAway`, `PlaceSubject`, `Finish`: le notizie al gioco; `Order`: il rifiuto unico), `AstraTransporterCard.cpp`
(`boarded_by_our_marines`), `AstraTransportBench.cpp` (le prove «boarded»), `mind/astra_mind/transporter.py` e `crew.py` (prompt e regola), `mind/bench/transporter_unit.py` e due schede vere in
`mind/bench/fixtures/transporter/`, `docs/TELETRASPORTO.md`.

**Provarlo nel gioco** (passi numerati, con le menti accese o spente): (1) un bersaglio senza energia: `astra.board.disable <contatto>` (o spararlo fino allo scudo giù); (2) `astra.board.assault out <contatto> - 2 port`
(i due Kestrel dal Ponte 8): attendere «Kestrel 1 has latched ... 12 marines are through»; (3) dalla plancia, a piedi: `astra.xport.send captain <contatto>`: rifiutato per «shields_own» (i nostri scudi) con la strada
(`window`); `astra.xport.send captain <contatto> window`: «X1 accepted: the Captain ... set down in deck N section X (...), beside N marines (...)»; il velo, la colonna, e il Capitano sui ponti dell'altra nave
(la riga a schermo ABOARD); (4) combattere con i marine; (5) a voce «Chief, beam me up» o `astra.xport.send captain "pad 1" window`: il Capitano in Transporter Room, i ponti spariscono, i marine
combattono senza di lui; (6) per vedere il rifiuto di un disturbatore: un incrociatore del Mandato che disturba (a 12-55 km) sulla linea; (7) le due marine: `astra.xport.send "marines 2" <contatto> window` e
`astra.xport.send "away team" "the pads" window`.
