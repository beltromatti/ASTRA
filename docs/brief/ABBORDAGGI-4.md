# Brief ABBORDAGGI-4 (F5, del lead): l'abbordaggio che il Capitano vive e comanda

Leggi prima **docs/PARTITE_2026-10-05.md** (§2 e §3: l'utente ha provato ad abbordare l'Acheron e a raggiungere i suoi marine: dieci minuti
per capire dove fossero i Kestrel, il teletrasporto che non trovava «il ponte dei Kestrel», i Kestrel in «undici minuti» sull'obiettivo,
«Ritirate i marine» e la risposta del nemico) e **docs/ABBORDAGGI.md §14.3** (che cosa è fatto, che cosa no, le note di progetto per la
fanteria, già decise). Le parole dell'utente: «abbordaggi ricevuti realistici e reali… soldati in grado di combattere, combattimenti in
prima persona anche del capitano, soldati intelligenti e meccaniche accattivanti, con ordini di guerra molto complessi anche per le
formazioni di fanti d'attacco o difesa della nave»; «più effort ed eleganza anche nel proprio personaggio nei movimenti e azioni possibili,
spiegate anche meglio con i tasti: E per usare, WASD, spazio, C per accovacciarsi, tenere premuto C per stendersi, mouse per mirare e
sparare»; «non posso permettermi attriti».

## Che cosa deve diventare vero
1. **Il ritmo**: dall'ordine all'aggancio pochi minuti al più a distanze di battaglia (oggi «undici minuti»: rivedi lanci, velocità,
   rotte dei Kestrel e degli Skiff con la fisica vera e la difesa di punto), e il Capitano sa sempre a che punto è (l'XO, la rete dei
   marine riferita in breve — VOCI-3 cura come arriva: tu dai i fatti e gli eventi giusti).
2. **Il Capitano va con loro senza attrito**: «vengo anch'io» lo porta alla baia dei Kestrel (o lo fa salire mentre partono, o lo
   teletrasporta sulla nave quando le regole lo permettono: il percorso c'è già, `ride` e il fascio di F5.2); la baia ha un nome che tutti
   conoscono e trovano (il registro dei luoghi lo unifica il lead in LUOGHI: dimmi i nomi e gli ingressi che ti servono).
3. **La fanteria si comanda**: il punto 4 di §14.3 (i compiti `sweep`, `breach`, `take`, `ambush`, `hold_line`, `escort` con le loro
   fasi e i modificatori, nella simulazione di squadra e nelle menti dei marine), con meccaniche oneste misurate dal banco: un ordine deve
   valere qualcosa. Il Capitano a bordo dell'Acheron dà ordini a voce ai capisquadra («Alpha, entrate in sala macchine, Bravo tiene il
   corridoio») e li vede eseguire.
4. **Il Capitano in prima persona**: il punto 5 di §14.3: accovacciato, prono, riparo, mira e fuoco, ricarica, cambio arma, i tasti
   spiegati bene sullo schermo (la riga dei tasti c'è: rendila giusta per l'abbordaggio), la rete dei marine nelle sue orecchie quando è
   con loro, la morte vera se lo colpiscono.
5. **I relitti** (la richiesta di SPAZIO-VIVO-2): i pezzi `bWreck` come obiettivi d'abbordaggio con il loro percorso, se ci arrivi.

## Misure
I banchi di `tools/boarding.py` (verdi oggi) più quelli nuovi per ogni ordine (con e senza, stessa pianta e stessi semi); i tempi dall'ordine
all'aggancio a 10, 20, 40 km con e senza difesa di punto; il percorso del Capitano senza grafica (`assault --setup out_ride`, `out_dress`).

## Vincoli
- Non tuoi: le reti radio e come parlano le menti (VOCI-3: tu scrivi i fatti, gli eventi e i compiti della mente dei marine; il loro prompt
  è tuo per i compiti, il modo di riferire al Capitano è di VOCI-3: coordinatevi con me), la battaglia (BATTAGLIA-3), i luoghi (il lead).
- Compila nel tuo worktree quando serve; niente editor né gioco: le prove nel gioco le fa il lead.

## File tuoi
`AstraBoard*` (tutti), `AstraBoardDrills.cpp` (nuovo), `mind/astra_mind/marines.py` (compiti, strumenti, dottrina della fanteria), i banchi
`tools/boarding.py` e `mind/bench/marines_unit.py`, il pawn del Capitano in prima persona per ciò che serve all'abbordaggio
(`ASTRAPlayerController` / il personaggio: coordinati con me prima di toccarlo), docs/ABBORDAGGI.md.
