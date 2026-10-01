# Brief ABBORDAGGI (F5.1, bozza del lead): combattere a bordo in prima persona

Dalla visione dell'utente: «abbordaggi con navette, IA di squadra e FPS» con i comandi WASD, E, Space, C per accucciarsi, C tenuto
per sdraiarsi, mouse per mirare e sparare. Il PIANO (F5, «fatta quando: un abbordaggio ricevuto è una battaglia vera nei corridoi»).
F5.1 è la prima metà: **il combattimento a bordo dell'Aquila**: il Capitano e i marine contro una squadra del Mandato che ha
abbordato. F5.2 (dopo): le navette d'assalto (i Kestrel del Ponte 8) e l'abbordaggio delle navi nemiche.

LEGGI: CLAUDE.md; ARCHITETTURA §1bis (le intelligenze) e §6; PIANO §3 (F5); NAVE.md (i ponti, il grafo, le porte stagne, l'armeria e il
poligono del Ponte 8, la caserma dei marine); VITA.md (i 80 marine del ruolino, le loro postazioni e i posti di combattimento);
**DISTRUZIONE.md** (in main dal 2/10: §2.6 le persone e il Capitano: chi è nella stanza si ferisce o muore per ipossia, ustione, fumo,
trauma; i feriti vanno in Medbay; il Capitano sviene e muore, e la catena esiste: XO al comando, abbandono nave, inchiesta, «THE
CAPTAIN IS LOST»; costruisci il danno da arma **su questo modello**, non accanto); il codice del giocatore (`ASTRACharacter.*`: posture,
movimento; `ASTRAPlayerController.*`: l'interazione con E e l'aiuto dei tasti); il template di Epic con la variante Shooter
(`/Users/Shared/Epic Games/UE_5.8/Templates/TP_FirstPerson/Source/TP_FirstPerson/Variant_Shooter/`: portaarmi, raccolta, proiettili,
PNG con StateTree ed EQS) come riferimento di codice — le sue armi sono giocattoli (dardi di schiuma): non adatte allo stile.

## Dove siamo (2/10)
In main: GUERRA, MENTE-GUERRA (le menti di guerra: ammiragli, comandanti, catena di comando), SCALA, DISTRUZIONE, VOLO (la rete di volo:
CAG, capi squadriglia, Chief of the Deck), VITA (560 persone). In corso accanto a te: **NAVE-3** (la pianta pensata come una nave vera:
programma, labirinto, tubi di Jefferies, pozzi degli ascensori, poi i piani delle altre classi) e **ASCENSORI** (turboascensori e navetta
veri). L'utente vuole un vero gioco in prima persona: «più effort ed eleganza nel proprio personaggio, nei movimenti e nelle azioni
possibili, spiegate anche meglio con i tasti» (E per usare, WASD, Space, C accucciato, C tenuto sdraiato, mouse per mirare e sparare
con un'arma), e gli abbordaggi come arma e difesa di tutte le navi grandi (F5.2).

## Cosa costruire
1. **Il nucleo FPS** (lead del GIOCATORE: lavora sul personaggio con cura, il gioco di plancia e il cammino non devono cambiare):
   armi da prendere all'armeria (un fucile e una pistola di bordo, da asset di terzi gratuiti e realistici in stile sci-fi: Fab
   gratuiti, Sketchfab CC0/CC-BY, registrati in docs/LICENZE.md; niente acquisti), braccia e animazioni in prima persona (impugnare,
   mirare con il destro, sparare, rinculo, ricaricare con R, cambiare arma), colpi a raggio con proiettili traccianti brevi, impatti,
   suoni; la mira e il movimento con le posture che esistono (C accucciato, C tenuto sdraiato, Space salto).
2. **Il danno alle persone**: punti vita e ferite per i personaggi (il Capitano compreso: può morire, la catena di comando esiste),
   i feriti del ruolino che vanno in Medbay (VITA, `FAstraCrewRoster`), i caduti con un nome.
3. **I combattenti**: una squadra d'abbordaggio del Mandato (fanti con IA di squadra: copertura, fuoco di soppressione, aggiramento,
   ritirata; partono da un punto d'irruzione: una falla, un portello) e i marine dell'Aquila (VITA: quelli di guardia accorrono, la
   squadra di reazione si arma); il capo squadra dei marine è una persona con cui il Capitano parla (gli ordini a voce passano dalla
   mente come per la gente di bordo: «tenete il corridoio», «con me»), il resto è codice di squadra.
4. **L'evento**: un abbordaggio ricevuto in battaglia (GUERRA: una navetta nemica che aggancia; o a comando per le prove), con
   l'equipaggio di plancia che lo riferisce, le porte stagne, i marine, il Capitano che può andare a combattere o restare in plancia.

## Prove
Un banco senza grafica per l'IA di squadra (arena con il grafo dei ponti: chi vince, perdite, tempi) e per le regole del danno; il
lead prova nel gioco (prendere le armi, il poligono del Ponte 8, un abbordaggio in un corridoio).

## Coordinamento
NAVE-3 (piano e kit), ASCENSORI (`AstraLift*`, l'interazione con gli ascensori nel controller), TELETRASPORTO (dopo) e il lead (plancia)
lavorano accanto: non toccare i loro file; ciò che serve da loro (una stanza, un punto d'irruzione nel piano, un cambio nel controller
fuori dalla tua parte), chiedilo al lead. Nel controller e nel personaggio tieni le tue modifiche raccolte e nominate (ASCENSORI tocca
solo l'interazione con gli ascensori).
