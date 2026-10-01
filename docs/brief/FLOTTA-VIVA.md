# Brief FLOTTA-VIVA (F4.4, del lead): le altre navi vivono come l'Aquila

Le parole dell'utente (2/10): prima l'Aquila, poi le navi alleate e nemiche, «così che tutto diventi giocabile… anche se non sono
realmente ancora riempite, le altre navi si devono comportare come tali e simulare perfettamente ciò che accade invece realmente
sull'Aquila, in ottica in futuro di allineare tutto e rendere tutto completo»; e dal piano principale: «sulle altre navi equipaggio,
danni interni e dinamiche interne vanno bene simulate, ma cinematica e distruzioni reali quanto l'Aquila dall'esterno… con gli stessi
esiti e possibilità dell'Aquila». Visione, non elenco: decidi tu ciò che è meglio per ASTRA.

LEGGI: CLAUDE.md; ARCHITETTURA §1bis e §6; **DISTRUZIONE.md** (il modello per compartimento: codice puro, deterministico, senza attori:
nasce per girare anche altrove); **NAVE.md** e i piani delle classi di NAVE-3 (`data/ship/plans/<classe>.json`, la sua fase C); VITA.md
(come vivono le 560 persone dell'Aquila: turni, posti, squadre); GUERRA.md (§5.3 i danni fisici per sezione e i sottosistemi: oggi lo
stato interno di una nave di GUERRA è a grana di sezione; §5.4 cosa sa ciascuna parte; §6 la vista per parte delle menti); SCALA.md
(il costo per nave conta: decine di navi).

## Cosa costruire
1. **Ogni nave ha un interno vero**: il piano della sua classe (NAVE-3), un equipaggio (un ruolino leggero: quanti, dove sono per turno e
   per posto di combattimento, chi ha un nome che conta: il capitano e chi lo segue nella catena), i suoi sistemi sui compartimenti.
2. **Lo stesso modello dei danni dell'Aquila**: un colpo di GUERRA su un'altra nave entra dove è arrivato e attraversa i suoi
   compartimenti (falle, fuoco, paratie, potenza, morti e feriti tra chi era lì), con le sue squadre astratte che riparano; ciò che ne
   esce torna a GUERRA (armi, motori, scudi, sensori, hangar che rallentano o si spengono) e alle menti di guerra (il capitano sa cosa
   brucia a bordo e quanti ha perso: decide con quello). A risoluzione più bassa e con un costo misurato per decine di navi.
3. **Ciò che si vede da fuori**: le rotture e le falle di una nave vengono dai suoi compartimenti veri (la nave si spezza dove la
   struttura ha ceduto, l'atmosfera esce dove ci sono falle aperte, le luci delle finestre si spengono nelle sezioni senza potenza),
   con gli effetti di VFX.
4. **Ciò che sanno i sensori**: la vista dei danni di una nave scansionata (`GetDamageView`, il tavolo olografico in `holo ship`) mostra
   ciò che il modello dice, con la nebbia di guerra di oggi.
5. **Pronta per gli abbordaggi** (F5.2): una squadra che entra in una nave nemica trova il suo piano e la sua gente dove il modello li
   mette; l'interno si costruirà dal piano quando servirà camminarlo.

## Prove
Il banco senza grafica: battaglie di `tools/war.py` con il modello acceso su tutte le navi (costo per tick, esiti rispetto a oggi, perdite
credibili), un colpo tracciato dentro una nave nemica, una nave che si spezza dove la struttura ha ceduto. Il lead prova nel gioco.

## File tuoi
Da definire con il lead all'avvio (dipende da cosa avranno toccato NAVE-3, DISTRUZIONE e CAMPAGNA): il modello per le navi (nuovi file
accanto ad `AstraDamageModel`), l'aggancio in `AstraBattleSubsystem`/`AstraWarDamage` e nella vista delle menti, `docs/FLOTTA-VIVA.md`.
