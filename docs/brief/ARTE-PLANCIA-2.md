# Brief ARTE-PLANCIA-2 (F1, del lead): ciò che il Capitano guarda di più, al livello di un film

Le parole dell'utente: «migliora nettamente graficamente anche le varie postazioni e monitor, sembrano degli uffici del 2026, non una
plancia da nave spaziale futuristica con tecnologie del futuro: tutta la plancia deve essere ricurata nel minimo dettaglio visivo»; «più cura
nei dettagli in generale»; «migliora anche quello del caccia». Il riferimento resta STILE.md §11 (Star Trek Discovery/Strange New Worlds, The
Expanse, EVE Online). Visione, non elenco: decidi tu ciò che rende questi posti belli e veri.

LEGGI: CLAUDE.md; STILE.md (§11 la plancia v3, §12 le navi v3); `art/blender/bridge3_*.py` e `bridge_v3.py` (il generatore della plancia v3:
guscio, telaio, pareti, soffitto, console, comandi, sedute, tavolo, ologramma), `art/blender/cockpit.py` (l'abitacolo del Falcon),
`art/blender/ship_rooms_bridge.py`, `ship_rooms_quarters.py`, `kit_corridor.py` (i corridoi del Ponte 1 e gli alloggi del Capitano, dell'era M1);
`tools/ue_scripts/build_bridge_v3.py`, `make_bridge_v3_materials.py` (come entrano nel livello); le anteprime `docs/progressi/bridge_v3/`.

## Cosa ha visto il lead giocando (2/10)
- La plancia v3 regge (console scolpite, sedute a guscio, soffitto strutturale), ma ha ancora grandi pavimenti lisci, poche luci
  d'architettura, console che da vicino sono semplici, poca vita sulle superfici (segni d'uso, targhe, piccole cose della gente che ci lavora).
- **L'abitacolo del Falcon è grezzo**: un telaio color sabbia senza dettaglio, nessuno strumento fisico, niente che dica «caccia del 2491».
- **I corridoi del Ponte 1** (dalla plancia all'ascensore e agli alloggi) sono ancora quelli beige del primo prototipo: un ufficio.
- Gli schermi delle console sono veri (li disegna il gioco: `SCREEN_<postazione>_<n>`, coordinate 0–1): restano dove sono e con le loro UV.

## Il confine con NAVE-3 (2/10, deciso dal lead)
NAVE-3 ha rifatto la pianta (v2) e ora costruisce sul Ponte 1 l'**atrio dei turboascensori della plancia** (`lift_housing_bridge`, x −22,8..−21,0,
y −8,2..−1,0, e i due pozzi tl_b1/tl_b2 a x −25,8..−22,8): vestibolo, tubi dei pozzi, tetto, e in `build_ship_interior.py` l'apertura del fondo del
corridoio di babordo (oggi chiuso dalla vecchia alcova «LIFT» con due ante finte). Tutto ciò che sta a poppa di x −20,8 sul Ponte 1 è suo; tuoi
sono la plancia, i due corridoi `corridor_1a_port`/`_starboard` fino a x −20,8 (il loro fondo resta APERTO verso l'atrio), gli alloggi del Capitano,
la ready room solo se serve (è un prefab di NAVE-3: chiedi). Gli ascensori sono del motore (AstraLift*: porte, cornici, vetture): non si toccano.

## Cosa costruire
1. **La plancia al minimo dettaglio**: pavimento con canali di luce e intarsi, luce d'architettura (gole, bordi, strisce che virano al rosso in
   allarme), console ricche da vicino (comandi fisici, pannelli olografici, maniglie, targhe), pareti composte, piccoli oggetti di chi ci lavora,
   usura dove si tocca. Le postazioni, i sedili e gli schermi restano nei loro posti (la gente di VITA e l'equipaggio ci si siede; gli schermi
   sono vivi).
2. **L'abitacolo del Falcon**: un vero caccia — telaio, strumenti, comandi, cinghie, il tettuccio con i suoi montanti — nel linguaggio delle navi v3;
   la vista resta libera dove l'HUD proietta.
3. **I corridoi del Ponte 1 e gli alloggi del Capitano** nello stesso linguaggio della plancia (coordinati con NAVE-3, che rifà il kit degli altri
   ponti: chiedi al lead dove passa il confine).
4. **Budget**: Nanite dove conviene, pochi materiali condivisi (trim sheet, decalcomanie), nessuna luce in più senza misura (la plancia in
   battaglia regge 60 fps con la risoluzione dinamica al 45–50 %: ogni ms conta). Anteprime Eevee dai punti che contano (la poltrona, ogni
   postazione, la porta, l'abitacolo) guardate davvero, con l'autocritica di docs/ricerca/08.

## Prove
Anteprime e conteggi (triangoli, materiali, luci); il lead importa e prova nel gioco (prestazioni dalla poltrona in battaglia, la resa vera).

## File tuoi
`art/blender/bridge3_*.py`, `bridge_v3.py`, `cockpit.py`, `ship_rooms_bridge.py`, `ship_rooms_quarters.py`, `kit_corridor.py`, i loro script
d'importazione in `tools/ue_scripts/` (`build_bridge_v3.py`, `make_bridge_v3_materials.py`, quelli dell'abitacolo e dei corridoi del Ponte 1),
`docs/STILE.md` (§11). Non tuoi: il C++ (se un posto o uno schermo cambia, chiedilo al lead), il kit dei ponti 2–12 (NAVE-3), gli ascensori (ASCENSORI).
