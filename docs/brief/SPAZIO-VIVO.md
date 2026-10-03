# Brief SPAZIO-VIVO (F2/F4, del lead): lo spazio di Aurelia pieno di cose vere

Le parole dell'utente: «spazio più popolato e pieno di entità, movimenti di navi enormi più lenti e mastodontici e cinematici, e caccia e navi
più piccole più eleganti e più numerose che vi scorrazzano in mezzo», «molti più oggetti nello spazio», «la guerra… simulazione molto più
grande e realistica», «come EVE Online» (scala, luce, spazio vissuto). Visione, non elenco: decidi tu cosa rende lo spazio di ASTRA vivo e vero.

LEGGI: CLAUDE.md; ARCHITETTURA §1bis; GUERRA.md (la battaglia: `FAstraBattleShip`, i velivoli, i punti di riferimento `Landmarks`, §10 la
March: le flotte fra i sistemi); SCALA.md (istanze, il costo per oggetto: decine di navi, centinaia di velivoli a 60 fps sull'Air); VFX.md
(armi, scie, motori, esplosioni, relitti); STILE.md §12 (le navi v3); `Source/ASTRA/AstraWarDraw*`, `AstraBattleSubsystem.*` (come si disegna
ciò che la guerra simula), `AstraShipSubsystem` (il sistema, il pianeta, il cielo), `art/blender/shipgen3*.py`/`ship3_*.py` (le navi v3).

## Cosa costruire
1. **Traffico civile che vive di suo**: mercantili, cisterne, navette di linea, rimorchiatori fra New Ravenna, la Keeper Station, l'Arsenal,
   le raffinerie di Tiberius e il Gate; rotte con orari, attracchi, code al Gate; quando arriva la guerra scappano, si nascondono, chiedono aiuto
   (eventi per i sensori e le comunicazioni: lo spazio reagisce). Pochi dati, molto movimento: istanze, niente attore per nave lontana.
2. **Luoghi veri nello spazio**: la Keeper Station al Gate (anelli, pontili, luci, traffico), l'Arsenal con i suoi bacini, le raffinerie
   di Tiberius, boe e fari delle rotte, la cintura di Ceres a distanza; visibili e riconoscibili dal finestrone e dallo schermo principale.
3. **Ciò che la guerra lascia**: relitti che restano dove sono morti (deriva, rotazione, luci che si spengono, fuochi che si spengono), campi di
   detriti che si allargano, capsule di salvataggio con i loro fari; la ricerca e soccorso li trova. I relitti contano per il gioco (si
   investigano, si abbordano: ABBORDAGGI e FLOTTA-VIVA leggono gli stessi dati).
4. **Scala e moto cinematici**: le capitali che virano e accelerano con la loro massa (già nella simulazione: renderlo leggibile: luci di
   posizione, getti di manovra, scie), i caccia in formazioni eleganti; la distanza percepita (foschia, scala, parallasse delle stelle e del
   pianeta). Nessun cambio alle regole del moto senza il lead.

## Vincoli
- **Budget**: il gioco tiene 60 fps in battaglia con la risoluzione dinamica intorno al 50 % sull'Air; ogni ms conta. Istanze (ISM/HISM),
  Niagara GPU, LOD e distanze di cull; misure prima/dopo (`astra.war.stat`, i tempi per oggetto). Memoria: il gioco è a ~8 GB su 9.
- **Non tuoi**: le regole della battaglia e della March (GUERRA, CAMPAGNA): aggiungi eventi e oggetti con ganci nominati, chiedi al lead
  per il resto; i velivoli d'abbordaggio (ABBORDAGGI); gli interni delle navi (FLOTTA-VIVA).
- Asset di terzi solo con licenza registrata (docs/licenze.csv, LICENZE.md); generatori in Blender dove servono forme nostre.

## Prove
Banco senza grafica per il traffico (rotte, orari, reazioni alla guerra, costo per tick); anteprime delle stazioni e dei relitti; il lead
prova nel gioco (dal finestrone, dallo schermo principale, dal Falcon).

## File tuoi
Nuovi file `AstraSpaceLife*` (traffico e luoghi) e `AstraWrecks*` (relitti e detriti), i generatori Blender dei luoghi, `docs/SPAZIO.md`;
ganci nominati in `AstraBattleSubsystem`/`AstraWarDraw` e negli eventi per la mente.
