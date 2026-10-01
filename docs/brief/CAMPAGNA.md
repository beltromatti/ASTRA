# Brief CAMPAGNA (F2.6, del lead): la guerra della March, a strati

Le parole dell'utente: «la guerra deve essere più grande e di strategia e lunga… guerra più grande, spazio più popolato… tempi di guerra
più lunghi e tattici ma mai noia: dobbiamo trovare sempre da fare per il Capitano, una guerra dove conta l'intelligenza e mosse rapide e
ben calibrate come una partita di scacchi blitz, ma con durata di ore… una campagna lunga ore, macrostrategie e sottostrategie, divisione
in sottosquadre, tattiche di gruppo reali… più peso alle decisioni del Capitano e più strumenti… un regista onnisciente che non si vede,
tira le fila e fa andare la guerra fino alla conclusione senza spostare le sorti in favore di qualcuno.» Visione, non elenco: decidi tu ciò
che è meglio per ASTRA.

LEGGI: CLAUDE.md; ARCHITETTURA §1bis (prompt, contesto e strumenti veri; il codice per le regole del mondo; niente filtri sulle parole né
numeri truccati) e §6; PIANO §3 (F2); **GUERRA.md tutto** (§5 com'è fatta, §6 il contratto dei comandanti, §7 il banco, §8 le menti e il
regista v2, **§9 la guerra a scala di flotte**); SCALA.md; VOLO.md; DISTRUZIONE.md; BIBBIA (il teatro di Aurelia, la March, la 7th Fleet, il
Mandato); `mind/astra_mind/war.py` (la mappa della March: sistemi, padroni, minacce, collegamenti).

## Fatto dal lead (2/10, GUERRA.md §9)
La battaglia dove sta l'Aquila è a scala di flotta: i beat portano forze in gruppi di battaglia (fino a 40 navi, ogni comandante una mente e
una voce), il regista ragiona a scala di flotte, l'apertura cresce in una battaglia di flotta (l'avanguardia dal Gate, il gruppo Constance), il
timone tiene la distanza con la retro-spinta, lo schermo stacca sulle forze che arrivano. Le menti di guerra comandano tre gruppi per parte a
1–2 m$ a decisione (~0,3 $/ora una partita intera).

## Cosa costruire: lo strato strategico
1. **La guerra va avanti dove l'Aquila non è.** Le flotte delle due parti sono entità della March (dove sono, di cosa sono fatte, rifornimenti,
   morale, ordini: difendere, razziare, assaltare, rinforzare, ritirarsi), si muovono fra i sistemi attraverso i Gate con tempi veri, e quando
   si incontrano senza l'Aquila combattono una battaglia risolta dalla stessa simulazione (il banco di GUERRA a bassa risoluzione, o un modello
   tarato su di esso): esiti veri (perdite, ritirate, sistemi che cambiano padrone), che arrivano al Capitano come notizie e cambiano ciò che il
   regista può portare. Mai numeri truccati.
2. **Chi decide la strategia.** Gli ammiragli delle due parti (Rourke per la 7th Fleet, il comando del Mandato) decidono le mosse delle flotte
   sulla mappa con strumenti veri e cadenza bassa (minuti), con la loro nebbia di guerra; il regista resta lo showrunner (ritmo, beat, tregue
   utili) e legge la mappa. Il Capitano può pesare: richieste e proposte a Rourke, ordini di Fleet che arrivano all'Aquila (andare dove serve,
   un transito, una scorta), e ciò che fa sul campo cambia la mappa (un Gate tenuto, una flotta fermata).
3. **Ore di campagna senza noia.** Il ritmo fra battaglie, tregue con cose da fare (riparare, rifornire, decidere gli schieramenti, raccogliere
   informazioni, i fili della storia), la battaglia decisiva che chiude un capitolo e la guerra che continua.
4. **Il Capitano a scala di flotta in plancia.** Ciò che manca per comandare e capire una guerra grande: il tavolo nella vista del settore con le
   flotte e i fronti, i rapporti della rete della flotta, lo schermo principale sulla flotta. Chiedi al lead ciò che serve lato plancia.
5. **Costo**: lo strato strategico con le sue menti ≤ 0,1 $/ora (cadenza, cache); il totale di una partita sotto 1 $/ora. Misura e riporta.

## Prove
Il banco senza grafica (`tools/war.py` per le battaglie; un banco nuovo della March che fa correre ore di guerra in secondi: esiti, durata,
simmetria, che il Capitano conti), la mente con un modello finto, poi poche prove dal vivo (≤ 0,15 $, riportane il costo). Il lead prova nel gioco.

## File tuoi
Da concordare con il lead all'avvio: lo strato strategico (nuovi file nella mente e, se serve, un banco nel commandlet di GUERRA),
`war.py`, `director.py` (con cura: il lead ci ha appena lavorato), `docs/GUERRA.md` (§10). Non tuoi: la plancia (il lead), la nave e i suoi
interni (NAVE-3, ASCENSORI, FLOTTA-VIVA), gli abbordaggi (ABBORDAGGI).
