# Brief ARTE-SCAFI (F2, del lead): le navi al livello di EVE e di Star Trek

Le parole dell'utente: «inizia ad usare realmente asset terzi inseriti perfettamente e fusi in quello che c'è già per portare… al next level di
fotorealismo e stile futuristico di Star Trek e EVE Online; prenditi delle immagini di EVE Online per capire lo stile futuristico delle sue navi e la
qualità dello spazio… possiamo usare intelligentemente asset nostri e asset terzi e fusione e editing 3D serio»; «navi enormi più lente e mastodontiche
e cinematiche, caccia e navi più piccole più eleganti».

Oggi (schermo principale a 2–4 km, 5/10): il Vigilant è uno scafo a blocchi ricoperto di «greeble» con i motori accesi, leggibile ma rumoroso; il
Praetorian dal basso è una pila di scatole con un blocco motori enorme; le navi del Mandato scure con luci arancio. Mancano: silhouette eleganti e
riconoscibili per fazione, pannellatura vera (linee, giunti, decalcomanie, numeri di scafo, usura), materiali PBR metallici credibili, centinaia di
finestre accese, luci di servizio, e una luce che le scolpisca (bordo, riflessi della nebulosa e del pianeta).

## La direzione (decidi tu i dettagli, con anteprime che guardi)
1. **Silhouette per fazione**: ASTRA (la Federazione del Nucleo: linee pulite, superfici continue chiare con accenti blu, gondole e dischi alla Star Trek
   moderno; l'Aquila portaerei-incrociatore, il Praetorian corazzata, il Vigilant cacciatorpediniere), il Mandato (scuro, spigoloso, gotico-industriale,
   motori grandi, armature a lame: un'eco di EVE Amarr/Minmatar senza copiarli), le Gilde (industriali, moduli, gru, cisterne). Le proporzioni dicono
   la stazza: le capitali enormi e lente, i caccia piccoli ed eleganti.
2. **Superfici**: pannellatura multi-scala (piastre, giunti, linee di servizio), decalcomanie (nome e numero di scafo, insegne di fazione, strisce di
   pericolo, numeri dei ponti), usura e bruciature dove serve, finestre emissive a centinaia (che si spengono con i danni: il contratto di
   `GetDamageView` c'è già), luci di posizione e di servizio. Texture a strati riusabili (trim sheet, atlanti di decalcomanie, maschere per fazione)
   invece di una texture per nave: memoria e coerenza.
3. **Asset di terzi dove valgono**: kit di superfici, decalcomanie, greeble di qualità, materiali PBR (Poly Haven, ambientCG, Fab gratuiti, Sketchfab CC):
   fusi nei generatori, mai incollati; tutto nel registro delle licenze.
4. **Prestazioni**: Nanite per gli scafi, istanze per i dettagli ripetuti, materiali con pochi campionamenti; decine di capitali e centinaia di caccia
   in battaglia sull'Air (SCALA.md): misura i triangoli, i materiali e le texture per nave.
5. **Compatibilità**: dagli scafi dipendono molte cose, e vanno rigenerate tutte, con i loro banchi. Scrivi i passi di reimportazione esatti.
   - i pezzi di rottura (`_SecBow/_SecMid/_SecStern`);
   - i punti dei motori (`fx_nozzles.json`, `thrusters.json`);
   - le luci di posizione (`extract_nav_lights.py`);
   - i solidi di SPAZIO-VIVO (`space3_solids.py`);
   - le decalcomanie di danno e i piani di FLOTTA-VIVA;
   - dal 5/10 le **mappe di profondità della pelle**, su cui colpi, fuochi e segni si posano:
     `blender -b --factory-startup --python-exit-code 1 -P tools/art/war_fx_hull_surface.py` →
     `python3 tools/art/war_fx_data.py --manifest art/export/ships_v3/manifest.json` → `AstraWarFXSurface.inl`, `AstraWarFXData.inl`, da ricompilare.

## Prove
Anteprime Blender (Cycles o Eevee) di ogni classe da vicino, a 2 km e a 20 km, di fronte a quelle di oggi; il lead le vede nel gioco (schermo
principale, finestrone, il Falcon) e giudica.

## Vincoli
- Non tuoi: la simulazione (BATTAGLIA-3), gli effetti delle armi (VFX-2, dopo), gli interni. Nessuna regola della guerra cambia.
- Niente editor né gioco: generi in Blender headless, esporti, scrivi gli script d'importazione; l'importazione la fa il lead.

## File tuoi
`art/blender/shipgen3*.py`, `art/blender/ship3_*.py` (e nuovi moduli), i materiali delle navi (`tools/ue_scripts/make_ship_materials.py`, `make_hull_*.py`),
`tools/ue_scripts/import_ships_v3.py`, le texture e gli asset in `art/_downloads/`, `docs/STILE.md §12` (le navi), `docs/LICENZE.md` per ciò che entra.

---

# Stato alla chiusura (5/10 sera, l'aiutante ARTE-SCAFI)

Chiuso su richiesta del lead prima di avere una nave nuova completa e vista nel gioco. **Regola applicata: il gioco non passa a una nave fatta a metà.** Nessun file che il
gioco legge è stato toccato: mesh, `manifest.json`, `data/war/fx_*.json`, `Source/ASTRA/AstraWarFX*.inl`, `data/ship/nav_lights.json`, `data/ship/plans/*`, `data/space/*` sono
quelli di oggi. Le navi del gioco restano le v3. Ramo: `worktree-agent-a4ab20c747ff922fd`.

## Cosa è fatto
1. **Gli strumenti di anteprima** (`art/blender/ship3_render.py`), nuove viste di `shipgen3.py -- --preview`:
   - `--views range`: la nave come il gioco la mostra a distanza, a **2 km** e a **20 km**: `_screen` è lo schermo principale (feed 1280 × 534, la nave occupa il 60 % della
     larghezza, come lo zoom automatico di `AstraViewscreen`), `_eye` è la finestra della plancia a occhio nudo (90° su 1600 × 900, il campo del giocatore), ritagliata attorno alla
     nave **alla sua grandezza vera in pixel** (il Vigilant a 2 km è ~120 px, a 20 km ~12 px: è ciò che silhouette, tinta e poche luci devono reggere da sole);
   - `--views blueprint`: alzati ortogonali di fianco, dall'alto e di fronte (silhouette e proporzioni; prua a destra, babordo in alto nella vista dall'alto).
   Un giro completo costa ~12 s (Eevee): `blender -b --factory-startup --python-exit-code 1 -P art/blender/shipgen3.py -- --only Vigilant --no-export --no-pieces --preview <cartella> --views three_quarter,range,blueprint --samples 32`.
   Provate su un caccia e su un cacciatorpediniere; i triangoli non cambiano (Vigilant 132.699, Falcon 32.494: identici al manifest).
2. **Il riferimento «prima»** del Vigilant, per i confronti: `docs/progressi/scafi/prima/` (tre quarti, 2 km e 20 km nelle due forme, i tre alzati).
3. **`art/blender/ship3_form.py`** (preparatorio, non usato da nessuna nave): gli scafi scolpiti. Una tabella di stazioni (`hw`, `zt`, `zb`, ... a curve monotone) diventa anelli
   di 44 punti dalla topologia fissa (chiglia, ventre, sentina, mascone, fianco, spalla, bordo di coperta, bombatura), quindi un indice di punto è una linea dello scafo e una
   fila di lati è una **fascia** (`BandZone`, con l'interfaccia di `ship3_loft.Zone`) che piastre, strisce di finestre e fascia blu seguono. Provato offline (numpy): la curva riproduce
   i nodi ed è monotona, ogni anello è convesso e antiorario, i punti di una fascia sui vertici sono i vertici, le normali escono, una fascia di un lato è uguale alla `Zone`.
4. **La catena di rigenerazione è provata a vuoto sul Vigilant di oggi**: `shipgen3.py --only Vigilant` → FBX e manifest, `ship_hull_probe.py --only vigilant`, `ship_class_plans.py`:
   deterministica (stessi numeri del manifest, sonda identica byte per byte). Quindi rigenerare dopo un cambio di scafo si può fare tutto offline, in pochi minuti.

## Cosa manca
1. **La nave nuova.** Nessuna classe è stata portata a v4. Il Vigilant era il candidato (nessun vincolo di interni come l'Aquila; la pianta di FLOTTA-VIVA si rigenera dalla sonda).
2. **`ship3_loft.slab` con i punti di rottura delle fasce** (`BandZone.w_breaks`): oggi una piastra su una fascia di più lati sarebbe piatta (una corda della superficie). Va aggiunto,
   in modo compatibile (le `Zone` di oggi non hanno `w_breaks`: stessa geometria bit per bit, da verificare con i triangoli di tutte le navi): nel `loop(poly)` dello slab, un punto per
   ogni rottura sui due lati trasversali (`_edge_at_w`), con le sole rotture strettamente dentro il poligono interno (così tutti gli anelli hanno lo stesso numero di punti).
3. **Disegno del Vigilant v4**, la mia proposta (da guardare nelle anteprime prima di fidarsene):
   - scafo a lama: stazioni da x = −118 (poppa dello scafo) a +150, mezza larghezza 17,5 m a metà nave, coperta da +10 a −9,6, prua che si affila (0,4 m alla punta);
   - torre di comando scolpita, spazzata, nel terzo di poppa (x −118..−62: lontana ≥ 6 m dal piano di taglio a −58), ponte di comando in una fascia vetrata, cupola dei sensori, albero;
   - due **gondole** di motori su piloni spazzati che sono anche i radiatori (pannello scuro corrugato, materiale `Radiator`), x −68..−146, bocche `R = 4,6` con l'origine a x = −146
     (così il minimo di x resta −156); nessun pezzo oltre i piani di taglio ±58;
   - armi dove le vuole la simulazione (`data/war/classes.json`): torrette a rotaia dorsali a prua (x ≈ 95) e a poppa dietro la torre, canna fissa nella prua, due batterie laser
     sui fianchi a metà nave, un VLS 4 × 2, due canali di difesa di punto; baia dell'hangar ventrale a x −8..22 (14 × 5 m);
   - un disco deflettore azzurro sotto la prua, strisce blu sotto le gondole (materiale `Glow`), file di finestre e luci di servizio.
4. **Nessuna texture e nessun materiale nuovo** (trim sheet, atlante di decalcomanie, maschere per fazione: non iniziati). Nessun asset di terzi è entrato (nessuna riga nuova in LICENZE).
   Gli asset già scaricati che servirebbero per un trim sheet di scafo: `art/_downloads/ambientcg/` (Metal032, Metal046A, MetalPlates017A, SheetMetal002, DiamondPlate008C, ...).
5. Le altre classi (Praetorian, Aquila, Mandato, Guilde, caccia) sono intatte.

## Come riprendere (ordine consigliato, un cancello per tappa)
1. Slab con le rotture (punto 2 sopra) → `shipgen3 --report` su **tutte** le navi: i triangoli devono restare identici a `manifest.json` di oggi.
2. Blockout del Vigilant v4 in un modulo nuovo (`ship3_astra3.py`) con `ship3_form.FormHull`: solo pelli, nessuna piastra; guardare `--views blueprint,range`; rifinire la silhouette
   a confronto con `docs/progressi/scafi/prima/`. Poi piastre, fascia blu, finestre, torrette, gondole, dettagli, luci.
3. Cancelli prima di consegnare (tutti, o niente): ≤ ~400 k triangoli e tre pezzi di rottura coerenti; `check_ships3.py`; `shipgen3.py -- --only Vigilant` nel checkout principale
   (il manifest su disco si fonde); poi, **nell'ordine**:
   `tools/ue_scripts/extract_nav_lights.py` · `blender -b ... -P tools/art/war_fx_nozzles.py` · `blender -b ... -P tools/art/war_fx_hull_surface.py -- --only SM_SHIP_ASTRA_Vigilant` ·
   `python3 tools/art/war_fx_data.py --manifest art/export/ships_v3/manifest.json` (**serve il manifest completo**, altrimenti le altre navi perdono i pezzi) · da ricompilare ·
   `blender -b ... --python art/blender/ship_hull_probe.py -- --only vigilant` · `python3 art/blender/ship_class_plans.py --only vigilant` (**0 problemi**) ·
   `blender -b ... -P art/blender/space3_solids.py -- --only vigilant` · `blender -b ... -P art/blender/space3_thrusters.py -- --only vigilant` · `tools/space.py sync` ·
   nell'editor `tools/ue.py pyfile tools/ue_scripts/import_ships_v3.py` con `ONLY = ["Vigilant"]` (il lead; materiali: solo istanze, `make_ship_materials_v3.py` non ricostruisce i master esistenti).
4. Il lead guarda il Vigilant nel gioco (schermo principale a 2–4 km, il finestrone, il Falcon vicino) prima che si passi a un'altra classe.

## Vincoli scoperti (da non dimenticare cambiando uno scafo)
- **Il riquadro**: i limiti di oggi del Vigilant sono x −156,46..150,70, y ±26,96, z −16,41..48,18 (305,9 × 53,7 × 64,3 m), tagli a x = 58 e −58 (`data/war/classes.json`: `hull_m`, `cuts_x_m`).
  Restare entro pochi % evita di toccare la simulazione e gli effetti. L'unica deviazione prevista (gondole a y ±32) allarga la larghezza del riquadro, non lo sposta.
- **Il nome sul fianco** (`AstraHullName.cpp`): un decal largo il 22 % della lunghezza (8–90 m), alto un quarto, centrato a x = Min.X + 0,6 · Size.X (≈ +27,6 m per il Vigilant) e a z = Min.Z + 0,33 · Size.Z,
  proiettato dentro da ±(Max.Y + 1,5 m) per 0,3 · Size.Y + 2 m, su entrambi i fianchi: quel campo (x −6..61, z −3..14) deve restare liscio e senza nomi o numeri in geometria
  (lo STATO lo chiede già: i numeri per nave sono solo del decal).
- **I motori per gli effetti**: `war_fx_nozzles.py` sostituisce l'attributo `ship3_kit2.engine_nozzle`: ogni bocca va costruita con `K2.engine_nozzle(...)` chiamato dal modulo (mai `from ... import`);
  le bocche principali guardano indietro (dir.x < −0,5, `detail` > 0), al più 8 finiscono nella tabella; i blocchi di manovra sono `K2.thruster_cluster` (bocche `detail` 0, che `space3_thrusters.py` legge come «quad»).
- **Le luci di via** (`shipgen3.nav_lights`): rossa e verde sui punti più larghi a metà nave (|x − centro| < 30 % della lunghezza: oggi la punta delle ali dei radiatori), bianca in cima, rossa sul ventre.
- **Le rotture**: `make_all_cuts` taglia l'anello dello scafo a ogni piano (deve essere convesso e antiorario in (y, z)); nessuna piastra attraversa un piano; i dettagli stanno ad almeno 6–8 m; una struttura che attraversa
  il taglio (una torre, una pinna) va data a `cap_extras`.
- **La pianta degli interni** (`ship_class_specs_b.py`, VIGILANT): ponti a z 10,5 · 6,0 · 1,5 · −3,0 · −7,5 (altezza libera 4,2) devono stare dentro la pelle misurata; hangar a x −8..22 con bocca ventrale (x 7, z −9, 14 × 5 m);
  portelli a x 20 e −30 (ponti 3 e 4), sala del ponte a x −106..−80. **Problema già presente**: da BATTAGLIA-3 `classes.json` ha un affusto in più per Styx (5), Acheron (6), Vigilant (5), Praetorian (7) — la canna fissa di prua —
  e le specifiche ne nominano uno in meno (`PROBLEM mounts: the class has 5, the spec names 4`): rigenerare le piante **sposta i ruoli** (il terzo affusto prende il ruolo `laser_port`). Le piante nel repo sono ancora quelle di prima, coerenti con sé stesse.
  Prima di rigenerare serve, nelle specifiche, un ruolo `gun_bow` (e una stanza che lo serva) per ognuna delle quattro classi: è un file di FLOTTA-VIVA.
- **Materiali**: `make_ship_materials_v3.py` si ferma se un master esiste (ricostruire in posto manda in crash l'editor); le istanze si possono creare e riassegnare; un master nuovo ha un nome nuovo.
