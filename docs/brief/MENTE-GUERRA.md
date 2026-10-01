Modulo MENTE-GUERRA (fase F2.2 lato mente + F2.5 regista v2): le menti che comandano la guerra grande.

LEGGI PRIMA: CLAUDE.md; docs/ARCHITETTURA.md (soprattutto §1bis, il principio delle intelligenze: niente regole di codice sulle
decisioni o sulle parole dei modelli; prompt, contesto vero e strumenti veri; percezione = ciò che quella persona saprebbe, azione =
gli strumenti del suo ruolo); docs/GUERRA.md (tutto il §5 e soprattutto il §6, IL CONTRATTO: `group_order`, gli ordini, le viste per
parte `_mandate.{your_groups,enemy_groups,group_events}` e `_astra_groups`, gli eventi, i comandi che c'erano, §6.8); docs/PIANO.md
§4.1; la mente: mind/astra_mind/{enemy,director,server,context,router,crew,agent,models,openrouter,war}.py e mind/bench/.

COSA COSTRUIRE
1. I comandanti del Mandato. Oggi: `enemy.py` (EnemyAgent, COMMANDERS, CHAIN, `plan_tactics` ogni ~30 s con `command_group` →
   `mandate_tactics`) e la persona che parla sul canale aperto. Domani: il comandante più anziano sul campo è l'AMMIRAGLIO della
   parte (nell'apertura l'Archon Varek Solm sull'Acheron): legge la vista dei gruppi con la nebbia di guerra e dà `group_order`
   (by "admiral"; anche "all"), più guerra elettronica, missili e caccia con `mandate_tactics` quando serve. I capi dei gruppi
   (by "commander") pensano solo quando qualcosa riguarda il loro gruppo (eventi forti: perdite, morale che cede, ordine scaduto,
   nemico nuovo) e dentro l'intento dell'ammiraglio. La persona che parla sul canale e la mente che comanda sono la stessa persona
   (stessa memoria di ciò che ha deciso e detto). La catena di comando regge le morti (CHAIN, e il gioco già passa il comando).
2. I comandanti alleati ASTRA: il capitano di ogni nave o gruppo alleato (la Praetorian, ammiraglia della flotta locale; la
   Vigilant; i rinforzi) con carattere, voce e memoria, che comanda il suo gruppo (`group_order` by "commander", vista
   `_astra_groups`) e PARLA CON L'AQUILA sul canale della flotta: richieste, avvisi, coordinamento — pochi messaggi, brevi,
   utili, quando servono. Le richieste del Capitano all'alleato (oggi `fleet_request` le traduce in ordini nel codice) passano
   dal giudizio del comandante alleato: le riceve come parole sul canale (il router già decide cosa esce) e decide lui, secondo
   la catena di comando (se il Capitano è l'ufficiale più anziano presente, obbedisce; altrimenti valuta, e può rifiutare
   dicendo perché). Rourke (director.py) resta il comando di flotta da lontano.
3. Il Capitano e la sua flotta: l'XO ha già gli strumenti di plancia; dargli `group_order` (by "captain"/"xo") per i gruppi ASTRA che
   il Capitano comanda davvero (quando è il più anziano, o il suo gruppo), coerente col punto 2.
4. Cadenza e costo: una mente pensa ogni 60–120 s o sugli eventi forti (i `group_events` nuovi dall'ultima volta, `n` progressivo),
   mai due volte in parallelo per la stessa persona; se la mente tace o tarda, i gruppi reggono sui loro riflessi (§5 di GUERRA).
   Modelli: il tetto è DeepSeek V4 Flash (models.py, ruoli; mai la stessa richiesta a due provider). Obiettivo: tutte le menti
   della battaglia (equipaggio compreso) ≤ 1 $ l'ora. Misura il costo per decisione e per ora di battaglia.
5. (Seconda parte, dopo i comandanti) Il regista v2 (F2.5, PIANO §4.1): invisibile, niente atti fissi; legge tensione,
   stanchezza del Capitano ed equilibrio, e crea situazioni dai fatti: rinforzi per entrambe le parti secondo la logica della
   campagna (con gli scenari/gruppi di GUERRA), trattative, eventi dello spazio, notizie. Mai numeri truccati a metà battaglia.
   Oggi director.py ha `act` 1–3 e il beat `decisive`: ripensalo senza atti.

COME SI PROVA (offline: MAI il gioco con la grafica, MAI l'editor)
- Il banco senza grafica `tools/war.py` (commandlet AstraWarSim, ~1000x il tempo reale): oggi gli ordini entrano con `--at`, e
  `--views` registra ciò che le menti ricevono. Costruisci la MENTE NEL GIRO: una modalità del banco in cui la simulazione si
  ferma ai punti di decisione, manda la vista alla mente e riprende con gli ordini (il commandlet è C++ di GUERRA:
  `Source/ASTRA/AstraWarSimCommandlet.*`, `tools/war.py` — ora sono tuoi; puoi compilare nel tuo worktree con Build.sh e
  -WaitMutex, al massimo 2 commandlet alla volta).
- Misure: scenari simmetrici con le menti su una parte contro i riflessi sull'altra (le menti devono vincere più spesso),
  menti contro menti (nessuna parte vince sempre), qualità degli ordini (coerenti con la vista, niente ordini impossibili
  ripetuti, ritirate sensate), parole degli alleati (poche, brevi, utili: un giudice LLM su un campione, non espressioni
  regolari). Costo per decisione, latenza.
- La mente contro messaggi finti: mind/astra_mind/local_ship.py e i banchi in mind/bench/ (guarda come sono fatti).
- Credito AI: il conto è piccolo (~5,9 $ in tutto per il progetto): sviluppo di questo modulo ≤ 0,8 $, prove brevi, riporta la spesa.

FILE: mind/astra_mind/war_minds.py (nuovo), enemy.py, director.py, server.py (aggancio: cadenza, eventi, canali), crew.py/tools.py
(lo strumento dell'XO), context.py se serve; mind/bench/war_*.py; Source/ASTRA/AstraWarSimCommandlet.*, tools/war.py (la mente
nel giro); docs/GUERRA.md (una sezione nuova sulle menti) e i tuoi appunti. Non toccare altro C++ senza chiederlo al lead.

RAPPORTO FINALE: cosa hai costruito, le misure (vittorie, costo all'ora, latenza), i limiti, i passi d'integrazione per il lead
(che proverà tutto nel gioco vero, con la voce, e ti rimanderà i difetti).
