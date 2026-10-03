# Brief ARTE-INTERNI (F4, del lead): le stanze dell'Aquila al livello dei suoi corridoi, poi di un film

Le parole dell'utente: «una nave vera… abitata ovunque da persone intelligenti»; «più cura nei dettagli in generale»; dal piano principale,
la nave camminabile, gli **asset di terzi gratuiti** dove alzano la qualità, il fotorealismo come metro. Il riferimento resta STILE.md
(§11 e §12: Star Trek Discovery/Strange New Worlds, The Expanse, una nave militare vissuta). Visione, non elenco: decidi tu ciò che rende
queste stanze belle e vere.

LEGGI: CLAUDE.md; STILE.md; NAVE.md (la pianta v2 di NAVE-3: ponti, sezioni, stanze, programmi; §7bis luci e streaming); VITA.md (dove
stanno e cosa fanno le 560 persone: i loro posti vengono dalle stanze); `art/blender/ship_rooms*.py` (i programmi delle stanze),
`ship_furniture*.py` (i mobili, primitive di `ship_lib.SParts`), `ship_kit.py`, `ship_lib.py` (materiali), `ship_spec.py`/`ship_layout.py`
(prefab, posti e luci delle stanze: `spot(...)`, `lights[]`); `tools/ue_scripts/import_kit.py`, `build_ship_interior.py`,
`make_ship_materials*.py`; le foto del giro in `docs/progressi/interni_2026-10-02/`.

## Cosa ha visto il lead camminando (2/10, 17 stanze su tutti i ponti)
- **I corridoi di NAVE-3 reggono** (`corridor5.jpg`): pannelli, tubi, luci, targhe, estintori. Sono il livello minimo per tutto il resto.
- **Le stanze sono ancora un greybox ammobiliato.** Divani e poltrone a blocchi, lampade a cilindro, alberelli fatti di sfere
  (`concourse`, `lounge3`, `suites2`), piante come palle verdi sotto luci viola (`garden4`: Forward Garden e Hydroponics Bay sono lo stesso
  prefab), panche di legno lisce (`chapel4`), una sfera nera in mezzo all'armeria (`armory8`). La tavolozza legno e arancio sa di hotel del
  2010, non di un incrociatore del 2491. Soffitti piatti con plafoniere quadrate, pareti vuote, stanze grandi e buie (`gym4`).
- **Le cinque stanze dell'era M1** (`existing` nella pianta: Mess Hall, Crew Berthing, Medbay, Main Engineering, Flight Deck) stanno sotto i
  corridoi: la Mess Hall è quasi nera e spoglia (`mess`), il Flight Deck è un magazzino grigio con navi appoggiate (`flightdeck`), la
  Medbay è pulita ma semplice, la Sala Macchine regge (colonna del reattore, gallerie) ma è piatta.
- Le persone sono manichini: non è compito tuo (F3, MetaHuman).

## Cosa costruire
1. **Ogni tipo di stanza fatto bene**, in ordine di quanto il Capitano le vedrà: mensa e cucina, alloggi (cabine, cuccette, alloggi degli
   ufficiali), sale comuni (lounge, wardroom, biblioteca, cappella, palestra), giardini e idroponica (piante vere), infermeria, officine e
   sale macchine, armeria e poligono, laboratori, uffici e CIC, il ponte di volo. Mobili e oggetti ricchi da vicino, materiali con
   texture vere (ambientCG), luce d'architettura (gole, strisce, schermi) che non costa luci dinamiche, segni d'uso e piccoli oggetti
   della gente che ci vive.
2. **Asset di terzi dove fanno la differenza** (piante, sedie, letti, attrezzi da palestra, cucina, strumenti medici, libri, piccoli
   oggetti): **Poly Haven** (CC0, API e download senza account) e **ambientCG** (CC0). Ogni asset va in `docs/licenze.csv` (fonte, autore,
   licenza, URL, modifiche) e nel registro LICENZE.md; i file grezzi in `art/_downloads/` (non su git). Per un pezzo di Fab, Sketchfab o
   Blendkit chiedi al lead (le sessioni sono nel suo browser): nome e link, lui lo riscatta se è gratuito.
3. **Le cinque stanze M1 portate al livello nuovo**, rifatte con il kit se conviene. Il loro posto nella pianta, le porte e i posti delle
   persone restano dove sono.
4. **La luce delle stanze**: le lampade della pianta (`lights[]`) diventano luci vere solo vicino al Capitano (`AstraLampPool`). Tara
   lumen, temperatura e posizione per tipo di stanza (la Mess Hall non deve essere nera) e aggiungi luce emissiva d'architettura.

## Vincoli
- **I posti non si spostano**: stazioni, sedie, letti e tavoli dove VITA mette le persone vengono dagli `spot(...)` delle stanze. Se un
  mobile cambia, il suo posto resta coerente (la persona si siede sulla sedia vera). Rigenera la pianta e fai girare i controlli
  (`ship_checks.py`, `tools/lift.py check`, il commandlet della nave): zero problemi.
- **Non tuoi**: muri, porte e topologia della pianta (cambiali solo se un mobile lo esige, e dillo al lead); il Ponte 1 (ARTE-PLANCIA-2);
  gli ascensori e le scale (motore AstraLift*/AstraLadder*); il C++ (chiedi al lead).
- **Budget**: il gioco è già a **~8 GB su 9** di memoria con i ponti in streaming. Texture condivise (trim sheet, atlanti, 1–2K), istanze,
  Nanite dove conviene, pochi materiali master con istanze. Conta triangoli, materiali e MB di texture per ponte, prima e dopo. Niente
  luci dinamiche in più senza misura.

## Prove
Anteprime Eevee o Cycles di ogni tipo di stanza (dalla porta e dal centro, all'altezza degli occhi, 1,68 m) guardate davvero, con
l'autocritica di docs/ricerca/08 e il confronto con le foto del giro; i conteggi. Il lead importa, ricostruisce i ponti e prova nel gioco
(resa, fps, memoria).

## File tuoi
`art/blender/ship_furniture*.py`, `ship_rooms*.py` (tranne il Ponte 1 e gli ascensori), i materiali delle stanze in `ship_lib.py`, i nuovi
script per gli asset di terzi in `tools/art/`, `tools/ue_scripts/import_kit.py` e `make_ship_materials*.py` per le parti delle stanze;
`docs/NAVE.md` (una sezione sull'arte degli interni). Lancia `build_ship_interior.py` solo nel tuo worktree (l'editor del progetto
principale è del lead).
