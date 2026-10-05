# Brief VFX-2 (F2, del lead): le battaglie si vedono — fuoco, colpi, esplosioni, distruzione

Le parole dell'utente (5/10, dopo le sue partite): «battaglie epiche, distruzioni, effetti speciali, azione continua»; dal prompt principale:
«effetti delle armi», «la distruzione», «le navi che si spezzano». Leggi prima **docs/PARTITE_2026-10-05.md**, **docs/VFX.md** (il modulo
che c'è: livelli di istanze, niente Niagara, sfere e tubi a bordo morbido, minimo in pixel) e **docs/GUERRA.md** dopo BATTAGLIA-3 (le armi
alle nuove distanze: decine di km, precisione che cala con la distanza, navi che muoiono a pezzi in minuti).

## Che cosa ho visto nel gioco (il lead, 5/10, `Saved/Play/ex*.png`, `bs_*.png`, `fx*.png`)
- **Un reattore che salta a 5 km è un lampo bianco che riempie il finestrone e lo schermo principale** per un secondo e mezzo: niente
  forma (la palla di fuoco, l'onda d'urto, i pezzi), poi più niente. Il relitto e i pezzi che si allontanano non si vedono; lo schermo
  passa al bersaglio dopo 5 s. Dopo il lampo alcuni fotogrammi escono a blocchi (MetalFX: vedi PRESTAZIONI-GPU).
- Lo scudo che si accende a esagoni sul bersaglio si legge bene (schermo principale ×1–×8).
- Dalla plancia, uno scontro a 20+ km è fatto di puntini e di etichette; lo schermo principale (il telescopio) mostra il bersaglio con
  le scie; la nuova inquadratura **«ASN AQUILA · FIRING ON …»** (il lead, `AstraViewscreen.cpp`, EShot::Broadside) mostra l'Aquila da
  fuori mentre spara: il fascio laser e le scie dei railgun partono dallo scafo verso il bersaglio. È lì che il fuoco deve impressionare.

## Che cosa deve diventare vero
1. **Il fuoco si legge a ogni distanza e su ogni inquadratura**: railgun (proiettili luminosi con la scia, il lampo alla bocca e il
   rinculo sullo scafo), laser (il fascio con il suo nucleo e il bagliore), missili e siluri (il motore, la scia di fumo, le correzioni),
   difesa di punto (le raffiche traccianti, i missili abbattuti), caccia (cannoni, virate, scie dei motori). A 30 km con lo zoom dello
   schermo principale come da vicino dal finestrone. Il colore dice di chi è (ASTRA azzurro/bianco, il Mandato arancio/rosso).
2. **Il colpo che arriva ha conseguenze visibili**: sullo scudo (esagoni, il settore che cede e si spegne), sulla corazza (scintille,
   metallo fuso, il segno che resta: il contratto `GetDamageView` e i decal ci sono), dentro (sfiati di atmosfera, fuochi dalle falle,
   le luci delle finestre che si spengono a sezioni).
3. **Una nave che muore muore in un modo che si ricorda**: esplosioni secondarie lungo lo scafo per qualche secondo, il reattore che
   salta con una palla di fuoco che ha struttura (nucleo, fiamme, fumo, onda d'urto ad anello, lampo breve), la nave che si spezza nei suoi
   tre pezzi (`_SecBow/_SecMid/_SecStern`, già nel gioco) che ruotano via bruciando, detriti e scintille, un relitto che resta e brucia
   nel cielo. Il lampo è intenso ma breve e non acceca la plancia (l'esposizione della plancia è fissa, EV100 6,6: misura).
4. **La regia lo mostra** (il lead la cura in `AstraViewscreen.cpp`): dimmi che cosa ti serve dallo schermo principale (un'inquadratura del
   relitto che si spezza tenuta più a lungo, un taglio sull'impatto) e i dati che lo dicono; li aggiungo io o li scrivi tu con il mio via.
5. **Prestazioni**: decine di navi e centinaia di velivoli (SCALA.md): istanze, pool, nessun attore per colpo; misura `astra.fx.stats`,
   `astra.war.perf`, e il costo della GPU della sovrapposizione (additiva e traslucida) quando un'esplosione riempie lo schermo.

## Prove
`astra.fx.scene / fire / hit / burn / break / swatch` (davanti alla plancia), `-astra_decisive` (una battaglia vera davanti alla plancia),
`astra.viewscreen.dump` (l'immagine dello schermo principale). Il lead guarda nel gioco e giudica; tu fai le anteprime offline (`tools/art/
war_fx_shader_preview.py`, `war_fx_hlsl_check.py`) e le catture che puoi.

## Vincoli
- Non tuoi: la simulazione e le regole delle armi (BATTAGLIA-3), lo schermo principale (il lead), le navi (ARTE-SCAFI). Nessuna regola
  della guerra cambia.
- File tuoi: `AstraWarFX*`, `AstraWarDraw*` per ciò che disegna, `tools/ue_scripts/make_war_fx.py`, `war_fx_hlsl.py`, `tools/art/war_fx_*`,
  docs/VFX.md; texture e flipbook in `art/_cache/fx` (generati) o `art/_downloads/` (di terzi, nel registro delle licenze).
