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
5. **Compatibilità**: i pezzi di rottura (`_SecBow/_SecMid/_SecStern`), i punti dei motori (`fx_nozzles.json`, `thrusters.json`), le luci di posizione
   (`extract_nav_lights.py`), i solidi di SPAZIO-VIVO (`space3_solids.py`), le decalcomanie di danno e i piani di FLOTTA-VIVA dipendono dagli scafi:
   rigenerali tutti, con i loro banchi, e scrivi i passi di reimportazione esatti.

## Prove
Anteprime Blender (Cycles o Eevee) di ogni classe da vicino, a 2 km e a 20 km, di fronte a quelle di oggi; il lead le vede nel gioco (schermo
principale, finestrone, il Falcon) e giudica.

## Vincoli
- Non tuoi: la simulazione (BATTAGLIA-3), gli effetti delle armi (VFX-2, dopo), gli interni. Nessuna regola della guerra cambia.
- Niente editor né gioco: generi in Blender headless, esporti, scrivi gli script d'importazione; l'importazione la fa il lead.

## File tuoi
`art/blender/shipgen3*.py`, `art/blender/ship3_*.py` (e nuovi moduli), i materiali delle navi (`tools/ue_scripts/make_ship_materials.py`, `make_hull_*.py`),
`tools/ue_scripts/import_ships_v3.py`, le texture e gli asset in `art/_downloads/`, `docs/STILE.md §12` (le navi), `docs/LICENZE.md` per ciò che entra.
