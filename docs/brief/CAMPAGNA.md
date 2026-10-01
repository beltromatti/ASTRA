# Brief CAMPAGNA (F2.6, del lead): la guerra della campagna a scala di flotte

Le parole dell'utente: «la guerra deve essere più grande e di strategia e lunga: non è possibile che io non abbia mai visto la maggior
parte delle navi nemiche e che a caso mi dicano distrutta una, distrutta l'altra… guerra più grande, spazio più popolato, movimenti di navi
enormi più lenti, mastodontici e cinematici, caccia e navi più piccole più eleganti e più numerosi che vi scorrazzano in mezzo… tempi di
guerra più lunghi e tattici ma mai noia: dobbiamo trovare sempre da fare per il Capitano, una guerra dove conta l'intelligenza e mosse
rapide e ben calibrate come una partita di scacchi blitz, ma con durata di ore… una campagna lunga ore, macrostrategie e sottostrategie,
divisione in sottosquadre, tattiche di gruppo reali… più peso alle decisioni del Capitano e più strumenti… un regista onnisciente che non si
vede, tira le fila e fa andare la guerra fino alla conclusione senza spostare le sorti in favore di qualcuno.» Visione, non elenco: decidi tu
ciò che è meglio per ASTRA.

LEGGI: CLAUDE.md; ARCHITETTURA §1bis (prompt, contesto e strumenti veri; il codice per le regole del mondo; niente filtri sulle parole né
numeri truccati) e §6; PIANO §3 (F2); **GUERRA.md tutto** (§5 com'è fatta, §6 il contratto dei comandanti, §7 il banco, §8 le menti e il
regista v2); SCALA.md (cosa regge il disegno: `scale_30x150` a 60 fps dalla plancia, `fleet_battle` con 71 navi e 137 velivoli); VOLO.md
(la rete di volo); DISTRUZIONE.md (i danni interni dell'Aquila); BIBBIA (il teatro di Aurelia, la March, la 7th Fleet, il Mandato).

## Dove siamo (2/10)
- Il motore regge la scala (SCALA), le menti di guerra pensano per gruppi con la catena di comando e costano poco (0,02–0,17 $/ora
  nell'apertura), il regista v2 sceglie i beat senza atti leggendo il polso della guerra.
- Ma la campagna è piccola: l'apertura scritta in `AstraBattleSubsystem::TickScenario` (Aquila, Praetorian, Vigilant, il mercantile;
  il Lethe, poi a 170 s l'Acheron con tre Styx) e il regista che **nel prompt** dimensiona le incursioni a 1–4 navi, i rinforzi a 1–2
  cacciatorpediniere, la battaglia decisiva a 4–8 navi (`director.py` ~181), con tagli nel codice (`[:8]`, `[:3]`, `[:2]`).
- Il lead l'ha giocata il 2/10: l'equipaggio è pronto e veloce, ma la battaglia si riduce a un incrocio di sei navi e a un inseguimento.

## Cosa costruire
1. **La guerra di Aurelia come guerra di flotte.** La 7th Fleet è una flotta vera nel sistema (gruppi di battaglia con i loro capitani e
   le loro menti, in posti che hanno un senso: il Janus Gate e la Keeper Station, l'orbita di New Ravenna, l'Arsenale, le raffinerie di
   Tiberius) e il Mandato arriva con le sue flotte (ammiragli, gruppi, portaerei con stormi). I luoghi contano: chi li tiene, cosa
   difendono, cosa costa perderli. La guerra **va avanti anche dove l'Aquila non è** (gli scontri lontani risolti dalla stessa simulazione,
   a risoluzione più bassa, con esiti veri che il Capitano sente sulla rete e vede sul tavolo).
2. **L'apertura che cresce.** L'aggancio di oggi resta un buon inizio (un contatto freddo, il mercantile, un gruppo d'attacco), ma la
   battaglia deve allargarsi a una battaglia di flotte nel giro di minuti, con più fronti e scelte vere per il Capitano (dove portare
   l'Aquila, chi coprire, dove lanciare lo stormo, quando ritirarsi), e durare a lungo senza vuoti.
3. **Il regista a scala.** Incursioni, rinforzi e battaglie decisive dimensionati per la scala che il motore regge (gruppi interi,
   portaerei con stormi, decine di navi nelle battaglie grandi), con il ritmo giusto: lunghe ore di campagna con battaglie, tregue utili
   (riparazioni, rifornimenti, decisioni di schieramento, informazioni da raccogliere) e mai noia. Sempre senza truccare: ciò che arriva in
   una battaglia in corso si vede arrivare.
4. **Il Capitano a scala di flotta.** Gli strumenti per comandare quando è il più anziano presente (l'XO e `group_order`, le richieste a
   Rourke, lo stormo), e le informazioni per decidere: il tavolo nella vista del settore e della flotta, lo schermo principale sulla flotta,
   i rapporti dei gruppi alleati sulla rete. Chiedi al lead ciò che serve lato plancia.
5. **Costo**: le menti di guerra a scala di flotta ≤ 0,3 $/ora (seggi, cadenza, cache: misura e riporta); il totale di una partita
   resta sotto 1 $/ora.

## Prove
Il banco senza grafica (`tools/war.py`, l'apertura con `--opening`, `fleet_battle`, molti semi): durata, esiti, perdite, simmetria, che
le mosse del Capitano contino (A/B con un Capitano passivo e uno sensato); la mente con un modello finto, poi poche prove dal vivo
(≤ 0,15 $, riportane il costo). Il lead prova nel gioco.

## File tuoi
`AstraBattleSubsystem.*` per l'apertura, gli scenari e le battaglie lontane (attento: SCALA, VOLO e DISTRUZIONE ci hanno lavorato: leggi prima
di cambiare), `data/war/*`, nella mente `director.py`, `war_minds.py`, `war.py`, `enemy.py` (e le loro prove), `tools/war.py`,
`docs/GUERRA.md`. Non tuoi: la plancia (il lead), la nave e i suoi interni (NAVE-3, ASCENSORI, FLOTTA-VIVA), gli abbordaggi (ABBORDAGGI: la
navetta d'assalto che aggancia è il suo evento; tu puoi farne una mossa del Mandato quando sarà unito).
