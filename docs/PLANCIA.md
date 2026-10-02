# La plancia, i corridoi, l'abitacolo del Falcon e gli alloggi del Capitano: livello film (ARTE-PLANCIA-2, 2/10)

La prima partita ha dato il verdetto («sembrano degli uffici del 2026, non una plancia da nave spaziale»); la seconda
passata (fase F1) porta quattro ambienti allo stesso livello, nel linguaggio di [STILE.md §11](STILE.md): la plancia
dell'**ASN Aquila** (Ponte 1 · Sezione A), l'abitacolo del **Falcon**, i due **corridoi del Ponte 1** e gli **alloggi del
Capitano**. Tutto è procedurale (Blender in modalità headless), sullo stesso attrezzo (`art/blender/bridge3_lib.py`), con
pochi materiali condivisi e geometria Nanite. Le anteprime stanno in [progressi/arte_plancia_2](progressi/arte_plancia_2/)
(`bridge/`, `cockpit/`, `corridor/`, `quarters/`): sono rendering Eevee delle mesh con i materiali dell'anteprima, non
catture del gioco (gli schermi vivi sono segnaposto, la luce di Unreal è un'altra).

## 1. Cosa è cambiato

### La plancia (`bridge_v3.py` e i moduli `bridge3_*.py`)
- **Pavimento** (`bridge3_floor.py`, nuovo; prima nel guscio): piastre polari in linea con le nervature del soffitto (ogni 10°
  dalla pedana), a giunti sfalsati nel pozzo; quadrante a bussola in carbonio e ottone attorno al tavolo olografico (rilevamenti ogni
  30° in lettere vere, quattro frecce luminose); lo stemma **ASTRA Navy** in ottone e luce con il motto («CONCORD · LAW · LIGHT»)
  a poppa, rivolto verso chi entra; la stella a otto punte del Capitano sulla pedana; la luce viene da intarsi (trattini e tratti
  corti, non linee infinite).
- **Soffitto** (`bridge3_ceiling.py`): un quinto dei pannelli è un campo di luce calda con un filetto d'ottone: luce d'architettura
  che vira al rosso con l'allarme (celle della palette con peso d'allarme, nessuna luce nuova).
- **Pareti** (`bridge3_walls.py`): le nicchie delle postazioni sono un portale di tre cornici arrotondate che rientrano nel muro con
  il vetro curvo senza cornice, bordi accesi e aureola; vani d'attrezzatura con schermi statici; lo schermo generale a muro con due
  cornici che escono dal muro e il banner sopra.
- **Console** (`bridge3_consoles.py`, `bridge3_controls.py`): il proiettore olografico al posto delle aste, serigrafie, il ticker,
  filetti d'ottone, comandi con più dettaglio; **tavolo olografico** (`bridge3_table.py`) con lunetta d'ottone e piano di vetro scuro.
- **Atlante dei decori** (`tools/art/bridge3_decor.py`, nuovo): pagine di schermi statici (gli «schermi spenti» non sono più neri:
  pannelli di stato, grafici, mappe, elenchi), bagliori e serigrafie dei piani di vetro; è una texture (`T_BRG3_Decor`,
  2048 x 4096) con l'istanza `MI_BRG3_Decor` sul master degli schermi; i punti degli UV 0–1 degli `SCREEN_<postazione>_<n>`
  vivi **non sono cambiati**.
- **Vita** (`bridge3_life.py`, nuovo): un ripiano personale sulla guancia di ogni console con le cose di chi ci siede (globo,
  tazze, pad, cuffie, pianta, il modello del Falcon, una foto), il tavolino del Capitano con la tazza e il pad, due fioriere sulle
  ali. I tre prop nuovi hanno la loro impronta nei controlli del layout (`data/ship/aquila_bridge.json`, `props`).
- **Ottone** come linea calda del ponte di comando (`MI_BRG3_Brass`), **navy** (`MI_BRG3_Navy`, #16294F) per le livree.
- Posizioni di sedili, postazioni e poltrona del Capitano **invariate**.

### I corridoi del Ponte 1 (`kit_corridor.py`, riscritto; stessi nomi, misure e origini del kit v2)
Zoccolo blu navy a pannelli, pareti avorio sopra il corrimano d'ottone, nervature a portale con un filo di luce calda, passerella
sopra una trincea illuminata, canale di luce a soffitto con griglie e canaline, pannelli con schermo del decoro / feritoie /
portello d'accesso con targa / lamelle di luce, paratia con strisce di pericolo e barre di stato, battente a due ante blu,
parete di fondo con estintore, kit di pronto soccorso e le targhe degli equipaggiamenti.
`shell(name, window=True, door=(x0, larghezza, altezza))` costruisce il modulo con la finestra **e** la porta della sala
riunioni (muro +Y del modulo) in un solo pezzo: sostituisce il corpo di `ship_rooms_bridge.corridor_door`.

### L'abitacolo del Falcon (`cockpit.py`, riscritto; `tools/ue_scripts/import_cockpit.py`, nuovo)
Dall'occhio del pilota (l'origine della mesh = la telecamera del pawn): archi del tettuccio con rivestimento, filo di luce e
bulloni, il coperchio antiriflesso con il proiettore dell'HUD (l'HUD lo disegna il gioco, il centro in alto resta libero), il
cruscotto con tre schermi con tasti morbidi, strumenti di riserva, motore, pannello degli avvisi, banchi di interruttori con le
protezioni; le consolle laterali (manetta e comunicazioni a sinistra, sensori, armamento e braccio di espulsione a destra), la
cloche, il sedile con imbracatura, cuciture a contrasto, anello di espulsione e distintivo ASTRA; fuori: il muso con la striscia
navy e i pannelli di servizio, le ali con gli stemmi, le derive e i motori dello scafo Falcon v3. Gli schermi dell'abitacolo
sono **pagine statiche** del decoro (nessuno slot `SCREEN_*`).

### Gli alloggi del Capitano (`quarters_room.py`, nuovo; `quarters.py`, `build_quarters.py`)
Zoccolo di noce a pannelli sotto un corrimano d'ottone, pareti crema a pannelli con pilastri, moquette blu in una cornice di
legno con la rosa dei venti in ottone, due tappeti di lana (amaranto con banda blu e filo d'ottone), soffitto a cassettoni con
luce nascosta e faretti, la galleria di poppa (grande vetrata con montanti di legno, tende, panca), la scrivania con
terminale e lampada, la poltrona del Capitano, sedie, divano, tavolino, poltrona, cuccetta in alcova con partizione,
libreria, cucina con la macchina del caffè, credenza con la culla del modello dell'Aquila, carta dei settori, orologio,
barometro, il berretto sul gancio, il guidone. Il blocco esterno (`SM_SHIP_ASTRA_AquilaBridgeBlock`) ha la **bocca del
corridoio** aperta nella faccia anteriore dell'alloggiamento dell'ascensore (x −21,0; y −5,5…−2,3; z 0…2,5) e **non ha più la
faccia superiore del piedistallo** sotto l'alloggiamento.

## 2. Regole di stile aggiunte a §11
1. **Mai una superficie liscia senza una ragione**: ogni parete ha zoccolo, filetto, giunzione o un oggetto; ogni piano di
   lavoro ha serigrafia.
2. **Due linee calde** (ottone e luce calda) ripetute in ogni ambiente; il resto freddo (navy, grafite, avorio).
3. **Le scritte sono geometria** (Barlow Condensed) o pagine dell'atlante dei decori; mai testo in una texture grande.
4. **Gli schermi spenti non sono neri**: pagine statiche dell'atlante (`MI_BRG3_Decor`); gli schermi vivi (`SCREEN_*`) restano
   quelli dei contratti delle postazioni.
5. **La vita sta sulle superfici**: tazze, pad, piante, un modello, una foto; sempre piccoli e con un'impronta nel layout.
6. **Nessuna luce dinamica nuova**: la luce viene dai materiali emissivi (palette `T_BRG3_Lamps`: le celle con peso 1 virano al
   rosso con l'allarme) e dalle luci già nel layout.

## 3. Numeri misurati (esportazione headless, Blender 5.2.2)
| Ambiente | Mesh | Triangoli | Slot materiali |
|---|---|---|---|
| Plancia (tutta) | 32 uniche | 835 675 unici (952 219 con le istanze) — prima 797 k / 919 k | 18 condivisi + 27 schermi `SCREEN_*` |
| Abitacolo del Falcon | 1 (`SM_CRAFT_ASTRA_Falcon_Cockpit`) | 71 672 | 15 (12 della plancia v3 e 3 dello scafo Falcon) |
| Corridoio | `Shell_4m` 8 110, `ShellWindow_4m` 8 418, `Bulkhead` 2 332, `DoorLeaf` 432, `EndCap` 828, `WindowGlass` 24, pannelli 272–776 | — | condivisi della plancia + `MI_BRG3_Navy` |
| Alloggi | `SM_QTR_Room` 60 354, `SM_QTR_Glass` 48, blocco esterno 1 668 | — | 22 |

Luci della plancia: 21 (17 rettangolari, 2 faretti, 2 puntiformi), **nessuna aggiunta**. Texture nuova: `T_BRG3_Decor`
(2048 x 4096, atlante).

## 4. Rigenerare e importare (ordine)
Dalla radice del progetto:
1. `uv run --python /opt/homebrew/bin/python3.13 --with pillow --with numpy python tools/art/bridge3_textures.py` (atlanti
   delle etichette e dei decori in `art/_cache/bridge3`; `--atlas-only` per rifare solo l'atlante). **Serve a tutti i generatori
   sotto** (leggono `labels.json` e `decor.json`).
2. `blender -b --factory-startup --python-exit-code 1 -P art/blender/bridge_v3.py -- art/export/bridge_v3`
3. `tools/ue.py pyfile tools/ue_scripts/make_bridge_v3_materials.py` (anche `MI_BRG3_Navy`, `MI_BRG3_Brass`, `MI_BRG3_Decor`)
4. `tools/ue.py pyfile tools/ue_scripts/build_bridge.py` (importa e piazza la plancia)
5. Corridoi: `blender … -P art/blender/kit_corridor.py -- art/export/kit_corridor`, poi `tools/ue_scripts/import_kit.py` con i valori
   di serie; poi (ri)esportare `SM_SHIP_BridgeCorridorDoor` da `ship_rooms_bridge.corridor_door`.
6. Abitacolo: `blender … -P art/blender/cockpit.py -- art/export/cockpit`, poi `tools/ue.py pyfile tools/ue_scripts/import_cockpit.py`
   (prima devono esserci le istanze di `make_bridge_v3_materials.py` e `make_ship_materials_v3.py`).
7. Alloggi: `blender … -P art/blender/quarters.py -- art/export/quarters`, poi `tools/ue.py pyfile tools/ue_scripts/build_quarters.py`
   (crea i materiali della cabina, reimporta anche il blocco esterno con la bocca aperta).

Anteprime: `bridge_v3.py --no-export --preview <cartella> --views seated,standing,…`, `kit_corridor.py … --preview`,
`cockpit.py … --preview` e `quarters_room.py -- --preview <cartella>` (variabili d'ambiente nelle docstring dei file).

## 5. Limiti noti
- L'abitacolo non ha schermi vivi: lo schermo principale è una pagina statica. Un display vivo sarebbe una scelta di C++
  (`AstraFighterPawn`): se serve, basta uno slot `SCREEN_cockpit_1` in più nella mesh.
- L'abitacolo non ha luci proprie nel gioco (solo i filetti luminosi dei materiali): una luce di riempimento debole nel pawn
  (canale di illuminazione dell'abitacolo) lo farebbe leggere meglio nell'ombra.
- Il soffitto del corridoio è scuro per scelta (la luce viene dalle strisce e dai portali): visto da sotto è il punto meno ricco.
- Le anteprime mostrano il vetro con il cielo stellato dell'anteprima, non quello del gioco.
