# Brief BATTAGLIA-3 (F2, del lead): battaglie epiche, continue, decise dal Capitano

Leggi prima **docs/PARTITE_2026-10-05.md** (le partite vere dell'utente). Le sue parole: «non è possibile che questi fight durino dieci
secondi: le armi non possono arrivare solo così a 10 km»; «timoniere… non guidi attivamente per tenerci sui nemici e quindi ce li perdiamo
e il resto della flotta li uccide e non ci pensiamo noi»; «il gameplay va rivoluzionato e aggiustato e molto bilanciato per essere più
epico ed entusiasmante, con battaglie epiche, distruzioni, effetti speciali, azione continua»; dal prompt principale: «scontri
nave/nave, nave/caccia, caccia/caccia… danni che dipendono dalla fisica reale e corazza e scudi», «una guerra dove contano intelligenza e
mosse rapide e ben calibrate come in una partita di scacchi blitz, ma lunga ore», «movimenti di navi enormi più lenti e mastodontici».

Oggi: railgun a 8–10 km, laser a 4, missili a 25; le distanze preferite dell'IA 4–9 km; dentro i 10 km una nave muore in tre salve (l'Erinys
in 10 s), fuori tutti tacciono; il Mandate (450–500 m/s di crociera) è più veloce dell'Aquila (288; 480 con tutta la potenza ai motori) e
si ritira appena è dentro, così l'Aquila insegue da dietro e perde; calore al 105 % in uno scontro normale (armi e scudi al 55 %); 20–32
incendi con 4 squadre; molte uccisioni dei caccia e degli alleati fuori quadro. **Visione, non elenco: decidi tu come si combatte in ASTRA**;
ciò che segue è la direzione.

## Che cosa deve diventare vero
1. **Lo scontro è continuo e si vede**: le navi si scambiano fuoco per minuti a distanze di decine di km (le armi arrivano lontano, la
   precisione cala con la distanza, con la sezione del bersaglio, con le sue manovre e i disturbi), il fuoco si vede (dallo schermo
   principale ingrandito e dal finestrone quando sono vicine: scie dei proiettili, raggi, impatti, scudi che si accendono a esagoni,
   pezzi che saltano). Niente silenzio fra «fuori portata» e «morta in tre salve».
2. **Le navi muoiono in minuti, a pezzi**: scudi per settore che cedono, corazza per faccia, sezioni e sistemi colpiti (motori → più lenta,
   batterie → meno fuoco, sensori → meno precisione, hangar → niente lanci), incendi e falle che contano; una corvetta in decine di secondi,
   un cacciatorpediniere in un paio di minuti, un incrociatore in molti, una capitale in una battaglia. Il modello fisico dei danni c'è già
   (GUERRA, DISTRUZIONE, FLOTTA-VIVA): usalo, non riscriverlo.
3. **Il Capitano decide l'esito**: la scelta del bersaglio e del sistema da colpire, la distanza e l'assetto (bordata, prua, taglio della
   rotta), la potenza (scudi, armi, motori), quando lanciare i caccia e i missili (saturazione contro la difesa di punto), il fuoco
   concentrato con gli alleati: ognuna cambia la battaglia in modo misurabile. L'Aquila è la nave che picchia più forte da lontano; i caccia
   coprono, inseguono e finiscono; le capitali non rincorrono i cacciatorpediniere: li tengono sotto tiro.
4. **Il timone e le armi manovrano da sé, bene**: tenere la distanza e l'arco che fanno sparare più armi, tagliare la rotta a chi si ritira
   invece di inseguirlo in coda, mettere la faccia forte verso la minaccia, evitare le collisioni (il timoniere lo propone già: deve saperlo
   fare da solo). Gli esecutori sono in `AstraStations` (`TickHelm`, `TickTactical`): rendili bravi.
5. **Il nemico si batte**: impegna con un piano (il comandante e l'ammiraglio sono menti: dagli i numeri giusti per decidere — forze, danni,
   morale — e il morale non deve crollare al primo contatto), si ritira quando perde davvero, si raggruppa, torna con i rinforzi.
6. **I sistemi pesano senza paralizzare**: il calore è una scelta (fuoco sostenuto sì, sovraccarico a rischio), il controllo dei danni
   regge una battaglia (le squadre di una nave da 560 persone, i sistemi automatici di spegnimento, i compartimenti che si isolano).

## Misure (banco senza grafica: `tools/war.py` run/batch/ab/sweep/duel, `AstraWarSimCommandlet`)
Durata degli scontri e delle battaglie (oggi pochi secondi di fuoco vero), tempo con il fuoco in corso sul totale, chi uccide chi (l'Aquila
deve contare), distanze di scontro, quante ritirate e quando, calore massimo, incendi aperti, colpi per uccisione; prima e dopo, con molti
semi. Obiettivi indicativi: un duello Aquila–Styx 1–3 minuti di fuoco continuo, una battaglia di flotta 10–20 minuti, il fuoco in corso per
la maggior parte dello scontro, l'Aquila guidata dal timone automatico che non perde un nemico in ritirata più lento di lei.

## Vincoli
- **Prestazioni**: decine di navi e centinaia di velivoli a 60 fps sull'Air (SCALA.md); più colpi in volo vuol dire più costo: istanze,
  pool, niente attore per proiettile; misura (`astra.war.stat`, `astra.war.perf`).
- **Non tuoi**: le menti (mind/, VOCI-3 le sta rifacendo: se un comandante deve ragionare diversamente, scrivi la richiesta con il testo),
  gli abbordaggi (ABBORDAGGI-4), lo schermo principale (il lead: se la regia deve inquadrare scambi lunghi, dimmelo con i dati che le servono).
- I numeri delle classi stanno in `data/war/classes.json` (e `tools/war.py embed` per la tabella compilata); docs/GUERRA.md va aggiornato.
- Compila nel tuo worktree (Build.sh con -WaitMutex) quando serve; niente editor, niente gioco: le prove nel gioco le fa il lead.

## File tuoi
`AstraBattleSubsystem.*` (armi, colpi, danni, ritirate), `AstraWarShipAI.cpp`, `AstraWarDamage.cpp`, `AstraWarGroups.cpp`,
`AstraWarOrders.cpp`, `AstraWarClasses.*`, `AstraWarStats.cpp`, `AstraWarSimCommandlet.cpp`, `AstraWarFX*` per la leggibilità del fuoco
lontano, `AstraStations.cpp` (gli esecutori del timone e del tattico), il calore e le squadre in `AstraShipSubsystem` (`TickHeat`,
`NumDamageTeams` e ciò che ci sta intorno) e in `AstraDamageModel*`, `data/war/`, `tools/war.py`, docs/GUERRA.md.
