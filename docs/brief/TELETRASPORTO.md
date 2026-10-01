# Brief TELETRASPORTO (F6, bozza del lead): la sala del teletrasporto, con regole alla Star Trek

Dalla visione dell'utente: «una sala del teletrasporto con i limiti di Star Trek», per chiunque, con animazioni e persone che
ragionano sul contesto. Il PIANO (F6, «fatta quando: trasporto persone e cose con effetti e regole credibili») la mette dopo F4.1, che
è finita: la **Transporter Room** esiste (Ponte 5, sezione B, `d5_transporter_B1`: sei pedane su una piattaforma, la console, i
cilindri), con le sue postazioni nella pianta; VITA ci mette già i tecnici (`transporter` nei turni dei sensori).

LEGGI: CLAUDE.md; ARCHITETTURA §1bis (le intelligenze: prompt, contesto e strumenti veri; il codice per la fisica e le regole del
mondo) e §6; PIANO §3 (F6); NAVE.md (la sala, le postazioni, il grafo); VITA.md (le persone e le loro postazioni); GUERRA.md (navi,
scudi per faccia, portate, disturbo elettronico); il pianeta (`AstraWorldSurface`, la discesa del Falcon); la mente (`crew.py`,
`tools.py`, `stations.py`: gli strumenti dell'equipaggio; `npc.py`: la gente di bordo).

## Cosa costruire
1. **Le regole (codice: è il mondo)**: chi e cosa si trasporta (persone, carichi), da dove a dove (pedana ↔ pedana, da sito a sito
   dentro l'Aquila, verso una nave alleata, verso la superficie del pianeta della demo), con i limiti: portata, scudi abbassati alle
   due estremità (una faccia degli scudi di GUERRA basta abbassarla?), disturbo elettronico e campi (il Janus Gate), un aggancio che
   richiede tempo e si può perdere, energia dal reattore, guasti se la sala o l'energia sono danneggiate (DISTRUZIONE). Un banco senza
   grafica con casi scriptati.
2. **La sala viva**: il capo della sala (un personaggio con nome, carattere e voce: gli si parla, ragiona sul contesto come la gente
   di bordo, `npc.py`, e risponde dei suoi limiti) e i tecnici di VITA alle console; la console mostra gli agganci e lo stato.
3. **Gli ordini**: l'equipaggio di plancia ha lo strumento vero (ops o l'XO danno l'ordine, il capo della sala esegue o dice perché
   non può); il Capitano può chiederlo a voce in plancia o dalla sala; nelle regole dell'equipaggio, cosa richiede la parola del
   Capitano.
4. **Ciò che si vede e si sente**: la smaterializzazione e la rimaterializzazione (un effetto su chi viene trasportato: luce,
   particelle, dissolvenza del materiale, il suono), sul Capitano in prima persona (lo schermo che si dissolve e si ricompone), con un
   budget da MacBook Air.

## Prove
Offline il banco delle regole e le prove della mente con un modello finto; il lead prova nel gioco (la sala, un trasporto interno, uno
verso il pianeta, uno negato dagli scudi in battaglia).

## Coordinamento
Nei limiti del modulo: niente abbordaggi (F5, dopo DISTRUZIONE) se non come interfaccia (trasportare una squadra sarà la stessa
regola). Gli altri moduli in corso: DISTRUZIONE (danni interni), SCALA (disegno della guerra), VOLO (piloti nella mente).
