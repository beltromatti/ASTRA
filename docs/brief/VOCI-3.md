# Brief VOCI-3 (F1, del lead): una plancia chiara, un Capitano in controllo

Leggi prima **docs/PARTITE_2026-10-05.md**: le partite vere dell'utente e i loro numeri (480 battute in 70 minuti, più di 150 mai dette,
quattro risposte dell'ammiraglio perse per traboccamento, alleati che danno la posizione a ogni chilometro, iniziative non chieste).
Le sue parole: «parlate troppo, troppe persone che ripetono le stesse cose; certe cose le voglio sapere dal primo ufficiale che è
l'unico che mi può dare anche dei consigli… gli altri devono parlare un pochino di meno ma essere precisi e fare quello che dico»;
«sento di non aver il controllo e troppe robe random e noisy»; «a volte si perdono i miei ordini o rispondono molto dopo».

**Il principio di ASTRA resta**: niente filtri, tagli o limiti di codice sulle parole e sulle decisioni dei modelli (ARCHITETTURA §1bis,
la memoria del progetto): si migliorano i prompt, il contesto, gli strumenti e l'orchestrazione. Il traboccamento di oggi è un limite di
codice che butta via ciò che i modelli dicono: va reso inutile dall'orchestrazione, non spostato più in là.

LEGGI: CLAUDE.md, ARCHITETTURA §1bis e la parte sulla mente, `mind/astra_mind/speech.py` (il palco: priorità, ripensamenti, coda),
`server.py` (chi produce battute e come arrivano al palco), `crew.py` e `agent.py` (l'equipaggio, i suoi strumenti, i turni per evento),
`initiative.py` (i controlli di guardia), `war_minds.py` (comandanti alleati e nemici), `flight_minds.py` (la rete di volo), `marines.py`,
`strategy.py` (l'ammiraglio), `transporter.py`, `npc.py`, `router.py`, `context.py`; docs/protocollo_voce.md; lato gioco
`AstraMindSubsystem` (i messaggi) e `AstraScreensSubsystem` (`DrawComms`, `DrawFlight`, il datapad).

## Che cosa deve diventare vero
1. **Le reti hanno chi le ascolta**. La rete della flotta (alleati, ammiraglio), la rete di volo (CAG, capi squadriglia, capo hangar),
   la rete dei marine e i canali con il nemico non vanno all'altoparlante della plancia: ci vanno i loro messaggi come traffico di quella
   rete, visibili sui registri delle console (comunicazioni, volo; il datapad), e l'ufficiale che la ascolta (comunicazioni, volo, l'XO
   per i marine) decide da sé che cosa riferire al Capitano e come, in breve. Ciò che è **rivolto al Capitano** (l'ammiraglio che gli
   risponde, un alleato che risponde a una sua domanda, il nemico su un canale che il Capitano ha aperto) arriva in plancia come risposta e
   **non si perde mai**. Il Capitano può dire «mettete la rete di volo in altoparlante» e la sente, finché non dice di toglierla.
2. **Una voce per il quadro**: l'XO dà la situazione e i consigli; gli altri parlano per la loro console quando il Capitano li chiama,
   quando eseguono un suo ordine (una conferma breve) o quando c'è da decidere o un pericolo nel loro campo. Tutto il resto (distanze che
   cambiano, riarmi, incendi spenti, rotte degli alleati) va **sul registro**: dai agli ufficiali uno strumento vero per scrivere sulla
   loro console e sul datapad senza parlare, e insegna nel prompt quando usarlo. Niente ripetizioni: chi parla sa che cosa è già stato
   detto in plancia nell'ultimo minuto e da chi, e che cosa aspetta di esserlo.
3. **Il Capitano ha la precedenza e la risposta subito**: quando parla, risponde chi è interessato, prima di tutti, in breve; ciò che gli
   altri stavano per dire si ripensa (già c'è) senza moltiplicarsi. Nessun suo ordine resta senza risposta.
4. **Il controllo**: un ufficiale prende iniziativa dentro l'autorità che il Capitano gli ha dato (difesa, routine della sua console,
   ciò che la dottrina e gli ordini permanenti dicono), e la annuncia in una riga; ciò che impegna la nave (lanciare un attacco, cambiare
   rotta per inseguire, aprire il fuoco su un nuovo bersaglio fuori dagli ordini) lo propone o lo fa solo se il Capitano l'ha delegato. Il
   Capitano lo cambia a parole («nessuno lancia senza il mio ordine», «da qui in poi fate da soli») e resta (la memoria e lo stato delle
   postazioni: `delegation` esiste già in `AstraStations`).
5. **Il canale giusto**: un canale con la flotta o con il nemico si apre per uno scambio e si chiude quando lo scambio è finito, o a
   parole; ciò che il Capitano dice all'equipaggio non esce mai su un canale aperto (oggi «dove trovo i Kestrel?» è andato alla flotta).
6. **I richiami del sistema** (mercantili che chiedono aiuto, notizie, convogli) arrivano alle comunicazioni, che li riferisce quando
   contano per il Capitano adesso, non come allarmi a pioggia.

## Misure (banco offline, con la mente simulata e le partite registrate come casi)
- Rifai le partite del 5/10 dai registri (gli eventi e le battute del Capitano in ordine e coi tempi) in un banco: battute in plancia al
  minuto, battute mai dette, ripetizioni, latenza della prima risposta al Capitano, risposte dell'ammiraglio arrivate. Obiettivi indicativi:
  in battaglia ≤ 4–6 battute al minuto in plancia, zero risposte al Capitano perse, prima risposta < 1,5 s, nessuna notizia ripetuta.
- Spesa: ogni prova con modelli veri breve e misurata; la media per ora di gioco non deve salire (oggi ~1,20 $/ora).

## Vincoli
- Non tuoi: la simulazione della battaglia (BATTAGLIA-3), gli abbordaggi (ABBORDAGGI-4), il teletrasporto come meccanica (`AstraTransporter*`:
  il lead), i luoghi e il localizzatore (il lead: LUOGHI). Se ti serve un dato nuovo dal gioco, aggiungilo al protocollo con un messaggio
  nominato e scrivi il lato C++ piccolo e commentato in `AstraMindSubsystem` / `AstraScreensSubsystem` (le pagine comunicazioni e volo e il
  datapad sono tue per questo lavoro); il resto del C++ no.
- Lingue: il gioco è in inglese; gli NPC parlano la lingua del giocatore (oggi italiano): prova in entrambe.

## File tuoi
`mind/astra_mind/` (speech, server, crew, agent, tools, initiative, context, router, war_minds, flight_minds, strategy, npc,
director solo per come le sue notizie arrivano), i banchi in `mind/bench/`, docs/protocollo_voce.md, docs/MENTE.md (o il capitolo della
mente in ARCHITETTURA, chiedi), e le parti C++ dette sopra. **Non tuoi**: `marines.py` (ABBORDAGGI-4 lo sta rifacendo: la rete dei marine
la instradi nel palco per chi parla e per canale, senza toccare il file; se ti serve una sua modifica scrivila come richiesta) e
`transporter.py` (il lead, per i luoghi: il Capo del teletrasporto lo instradi allo stesso modo).
