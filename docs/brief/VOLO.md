# Brief VOLO (bozza del lead): i piloti, il CAG e il ponte di volo hanno una voce

Dalla visione dell'utente: «personaggi importanti attivi (medico, ingegneria, **piloti, capo hangar**)». Oggi il medico e il capo
macchine parlano; i piloti no: le squadriglie esistono nella guerra (Alpha: Falcon, Bravo: Hammer, droni Wasp; lanci, attacchi,
perdite, rientri: gli eventi `flight: ...` di `AstraBattleSubsystem`), ma le riferisce solo Price, l'ufficiale di volo in
plancia. Il CAG (Lt. Cmdr. Ada «Hex» Kovac) è un nome nel prompt dell'equipaggio. Quando il Capitano vola un Falcon (callsign
Eagle) c'è solo il controllore.

LEGGI: CLAUDE.md, ARCHITETTURA §1bis (il principio delle intelligenze: prompt, contesto vero, strumenti veri; niente filtri di
codice sulle parole), §6; docs/GUERRA.md (squadriglie, velivoli, §6 il contratto e le viste); la mente: `crew.py` (i ruoli,
Price), `server.py` (il turno del Capitano, il router, gli eventi), `router.py` (cosa esce su un canale), `models.py` (ruoli e
costi), `voice_casting.py`; i banchi in `mind/bench/`.

## Cosa costruire
1. **Le voci del volo**: i capi squadriglia (Alpha Lead, Bravo Lead), qualche gregario, il CAG, il capo del ponte di volo (il
   «Chief of the Deck»: lanci, rientri, riarmo, i velivoli danneggiati, gli incidenti in hangar) con nome (il ruolino ha già un
   nominativo per ogni pilota), carattere, voce e memoria; parlano sul canale di volo **quando succede qualcosa a loro**
   (ingaggio, abbattimento, perdita, siluri lanciati, carburante, rientro, appontaggio), poche righe brevi e radio, nella lingua
   del Capitano. Price resta l'ufficiale in plancia che coordina: non devono parlare in due della stessa cosa.
2. **Il Capitano parla con loro**: «Alpha Lead, copri il Vigilant» passa per il router (il canale di volo, come il canale della
   flotta) e il capo squadriglia risponde e agisce con gli strumenti della sua squadriglia (gli stessi ordini che oggi dà la
   console di volo: CAP, scorta, attacco a un bersaglio, rientro), decidendo lui come eseguirli nel suo mestiere.
3. **Il Capitano in volo** (Falcon, callsign Eagle): i gregari volano con lui e parlano (avvisi, bersagli, «ho il tuo sei»), il
   controllore resta Price.
4. **Costo**: un ruolo piccolo e veloce (il tetto è DeepSeek V4 Flash); parlano solo per eventi forti, mai due volte la stessa
   cosa; obiettivo: le voci del volo ≤ 0,15 $ per ora di battaglia. Misura e riporta.

## Prove
Offline (mai il gioco con la grafica): banco con eventi di volo finti e un modello finto (come `bench/npc_unit.py`), poi un banco
dal vivo da pochi centesimi (come `bench/npc_live.py`): parlano quando devono, tacciono quando no, rispondono al Capitano e
agiscono. Il lead prova nel gioco in battaglia e in volo.

## Coordinamento
MENTE-GUERRA ha riscritto `server.py` (comandanti, alleati, il canale della flotta, la cadenza delle menti): parti dal suo lavoro
unito in main e aggancia il volo accanto al canale della flotta, senza duplicarlo.
