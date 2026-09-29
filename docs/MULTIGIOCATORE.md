# ASTRA — Il multigiocatore (M8): progetto tecnico

Obiettivo: più Capitani nello stesso universo, ognuno con la propria nave e il proprio equipaggio intelligente, con la
guerra condivisa. Il gioco oggi è in giocatore singolo, ma quasi tutto è già costruito in modo da poter passare al
server. Qui scrivo cosa c'è, cosa cambia e in che ordine.

## Com'è fatto oggi
- **La simulazione** vive in sottosistemi del mondo: `UAstraBattleSubsystem` (tutte le navi, i proiettili, i sensori,
  gli squadroni), `UAstraShipSubsystem` (lo stato dell'Aquila: potenza, calore, danni, rotta), `UAstraCampaignSubsystem`
  (salvataggi). Tutto si muove in un sistema di riferimento proprio (metri, con l'Aquila come `Ships[0]`), convertito in
  coordinate del mondo solo per la grafica (`ToWorld`).
- **Un unico punto d'ingresso per gli ordini**: ogni ordine, dell'equipaggio o della console, passa da
  `UAstraShipSubsystem::ApplyCommand(Name, Args)` con argomenti JSON. È esattamente la forma di una chiamata al server.
- **La mente** (`mind/`) è un servizio separato, collegato via WebSocket: riceve lo stato della nave in JSON ogni pochi
  decimi di secondo e gli eventi, e manda comandi e voci. Non tocca mai il motore di gioco direttamente.
- **La nebbia di guerra** è già un modello di conoscenza: `Track`, `bClassified`, `bIdentified`, per ogni contatto, dal
  punto di vista dell'Aquila; il Mandato ha il suo (`bPlayerTracked`).
- **Gli schermi, il tavolo olografico e il datapad** leggono da funzioni che producono una vista già filtrata dalla
  nebbia (`GetHoloBlips`, `ContactsJson`): in rete diventano la vista che il server manda a ogni client.

## Cosa cambia
1. **Autorità del server**. Un server dedicato esegue `UAstraBattleSubsystem` per un sistema stellare (i Janus Gate sono
   i confini naturali: un server per sistema, un transito è un passaggio di server). I client non simulano: disegnano.
2. **Più navi dei giocatori**. `Ships[0]` diventa "la nave di ciascun giocatore": ogni `FAstraBattleShip` di un
   giocatore ha un `OwnerPlayer`; le funzioni che oggi usano `Ships[0]` prendono l'indice della nave del giocatore.
3. **Conoscenza per nave**. I campi di nebbia (`Track`, `bClassified`, `bIdentified`, `TrackHold`) escono dalla nave
   osservata e diventano una tabella per osservatore: `Knowledge[Observer][Contact]`. `TickSensors` gira una volta per
   ogni nave di giocatore (e per la flotta, che condivide via datalink come oggi). Il disturbo e le esche funzionano
   già così: dipendono dalla geometria fra osservatore e contatto.
4. **Replica**. Un attore replicato per sistema (`AAstraSystemState`) porta:
   - le navi visibili a ciascun client, come `FFastArraySerializer` (posizione, assetto, velocità, scudi, stato),
     filtrate per rilevanza: il client riceve solo ciò che la sua nave conosce (niente trucchi con la nebbia);
   - i proiettili e le esplosioni vicine;
   - lo stato della propria nave (`UAstraShipSubsystem` diventa un componente replicato solo al proprietario).
5. **Ordini come RPC**. `ApplyCommand` diventa `Server_ApplyCommand(Name, JsonArgs)` sul `PlayerController`: il server
   controlla che il giocatore comandi la propria nave e risponde con lo stesso `OutDetail` di oggi.
6. **Le menti restano sul server**. Ogni nave di giocatore ha la sua mente (equipaggio, memoria, stile del Capitano,
   legami); il servizio `mind/` diventa multi-nave: una connessione per nave, stato e storia separati. Il Regista della
   guerra diventa uno per server (la guerra è condivisa), con archi personali per ogni Capitano. La voce del Capitano si
   trascrive sul client (WhisperKit locale) e arriva al server come testo; le voci dell'equipaggio si sintetizzano sul
   client a partire dal testo (nessun audio in rete).
7. **I comandanti nemici** restano menti del server e vedono tutti i Capitani del sistema (la loro vista del Mandato,
   `MandateViewJson`, già elenca più navi ASTRA).
8. **Gli interni** (plancia, ponti, equipaggio che cammina) sono per nave e locali: ogni client disegna gli interni
   della propria nave; un altro giocatore a bordo (cooperativo sulla stessa nave) sarebbe un secondo pawn replicato.

## In che ordine
1. Estrarre la nave del giocatore da `Ships[0]` (indice per giocatore) senza cambiare il comportamento in singolo.
2. Tabella di conoscenza per osservatore; `TickSensors` per ogni osservatore.
3. `AAstraSystemState` replicato e client che disegnano dalla replica (prima in "listen server" sulla stessa macchina).
4. `Server_ApplyCommand` e validazione.
5. Mente multi-nave e Regista condiviso.
6. Server dedicato per sistema e transiti fra server.

Il passo 1 e il 2 si possono fare subito, a giocatore singolo, senza rischi: rendono il codice pronto e la nebbia più
generale (servono anche per le navi alleate "intelligenti").
