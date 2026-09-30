# Navi v3 (ARTE-NAVI): scafi al livello di EVE Online, pronti a rompersi

Generatore di scafi v3: geometria vera a ogni scala (piastre a strati con smussi, pannelli, portelli, sfiati, finestre, antenne, cannoni,
ugelli con profondità), scritte in geometria, pezzi di rottura con facce di taglio bruciate, materiali con usura e luci per scafo.
Questa cartella contiene le anteprime (Eevee, cielo e luce di Aurelia: stella arancione, nebulosa Teal Veil) e questa nota.

## Anteprime

Per ogni nave, in `docs/progressi/navi_v3/`:

| File | Che cosa mostra |
|---|---|
| `<Nome>_three_quarter.jpg` | la nave intera, tre quarti, luce radente arancione e riempimento turchese |
| `<Nome>_closeup_<zona>.jpg` | zoom ×300: una toppa di scafo di 50 m riempie lo schermo (camera a 110 m, obiettivo 79 mm; 30-40 m per le navi piccole); ogni nave ha 1-4 toppe (fianco, ponte, torre, ventre, poppa, giunzione dell'isola) |
| `<Nome>_pieces.jpg` | i tre pezzi di rottura (Bow, Mid, Stern) staccati, con le facce di taglio |
| `<Nome>_cutface.jpg` | la faccia di taglio anteriore del pezzo Mid da vicino: fascia di corazza strappata, fodera, paratia, ponti interni, travi, lastre piegate, braci |
| `Falcon`, `Hammer`, `Wasp`, `Harpy`, `Watch` | tre quarti (velivoli e stazione non si rompono) |

`_overview.jpg` riunisce in una sola immagine le dodici viste a tre quarti.

Navi: Aquila, Praetorian, Vigilant (ASTRA Navy); Acheron, Styx, Lethe (Kharon Mandate); Freighter «Brightwater» (Free Guilds); stazione Thule Watch;
velivoli Falcon, Hammer, Wasp (ASTRA) e Harpy (Mandate).

## Come si rigenera (dalla radice del progetto)

```
# 1. texture procedurali di usura e danno (una volta): art/_cache/textures/ (non in git)
uv run --python /opt/homebrew/bin/python3.13 --with numpy --with pillow python tools/art/ship3_textures.py

# 2. mesh FBX + manifest (circa 4 minuti, ~800 MB di FBX, non in git): art/export/ships_v3/
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python-exit-code 1 -P art/blender/shipgen3.py -- --report
#    solo alcune: ... -- --only Aquila,Falcon      senza pezzi: --no-pieces       meno dettagli sparsi: --detail 0.6

# 3. controllo dei file esportati (li rilegge in Blender e li confronta con manifest.json; --fast salta i più pesanti)
/Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python-exit-code 1 -P art/blender/check_ships3.py -- --fast

# 4. Unreal (le esegue il lead; editor aperto): materiali, poi mesh (uno alla volta: Nanite di 1,5 M triangoli), poi le luci di navigazione
tools/ue.py pyfile tools/ue_scripts/make_ship_materials_v3.py
tools/ue.py pyfile tools/ue_scripts/import_ships_v3.py          # ONLY = ["Aquila", ...] per farne alcune; NO_SECTIONS = True salta i pezzi
tools/ue.py pyfile tools/ue_scripts/extract_nav_lights.py

# anteprime (Eevee, senza editor): una cartella qualsiasi
Blender -b --factory-startup -P art/blender/shipgen3.py -- --no-export --preview docs/progressi/navi_v3 --samples 48
#    --only Praetorian  --views three_quarter,closeup,pieces,cutface  --cam az,el[,lens[,elev. della luce]] --tag _nome
```

## Numeri (manifest.json)

| Mesh | Triangoli | Misure x × y × z (m) | Slot | Pezzi di rottura (triangoli) |
|---|---:|---|---:|---|
| `SM_SHIP_ASTRA_Aquila` | 750,355 | 799 × 140 × 92 | 11 | 761,315 (Bow 101,466 + Mid 344,603 + Stern 315,246) |
| `SM_SHIP_ASTRA_Praetorian` | 1,435,868 | 1129 × 184 × 220 | 11 | 1,448,772 (Bow 253,484 + Mid 775,802 + Stern 419,486) |
| `SM_SHIP_ASTRA_Vigilant` | 132,699 | 306 × 54 × 64 | 11 | 139,171 (Bow 25,288 + Mid 61,060 + Stern 52,823) |
| `SM_SHIP_MANDATE_Acheron` | 478,138 | 587 × 105 × 149 | 10 | 488,610 (Bow 94,783 + Mid 258,552 + Stern 135,275) |
| `SM_SHIP_MANDATE_Styx` | 180,768 | 387 × 81 × 115 | 10 | 189,536 (Bow 33,757 + Mid 83,907 + Stern 71,872) |
| `SM_SHIP_MANDATE_Lethe` | 83,363 | 240 × 61 × 57 | 9 | 90,383 (Bow 15,165 + Mid 43,018 + Stern 32,200) |
| `SM_SHIP_GUILD_Freighter` | 309,520 | 352 × 73 × 47 | 12 | 315,528 (Bow 38,423 + Mid 228,383 + Stern 48,722) |
| `SM_STATION_ASTRA_Watch` | 55,501 | 221 × 120 × 66 | 9 | — |
| `SM_CRAFT_ASTRA_Falcon` | 32,494 | 18 × 13 × 4 | 8 | — |
| `SM_CRAFT_ASTRA_Hammer` | 61,638 | 26 × 23 × 6 | 8 | — |
| `SM_CRAFT_ASTRA_Wasp` | 51,328 | 9 × 3 × 3 | 8 | — |
| `SM_CRAFT_MANDATE_Harpy` | 20,490 | 17 × 13 × 5 | 9 | — |

Totale navi e velivoli intere: 3,592,162 triangoli.

Budget: Nanite, al massimo 3 M triangoli per nave grande (la più pesante, il Praetorian, sta a circa metà) e 150 k per velivolo. Texture
nuove: `T_ShipWear_M` 2048² (5,6 MB), `T_ShipDamage_A` 4096×2048 (11 MB), `T_ShipDamage_N` 4096×2048 (11 MB): circa 28 MB contro i 400 MB di budget.
Le misure sono gli ingombri veri (scafo + sezione motori + campane + antenne): lo scafo dell'Acheron è 520 m, l'insieme 587 m; lo Styx 340 m (insieme 387);
il Lethe 220 m (240); il Freighter 340 m (352); il Praetorian 1100 m (1129); l'Aquila 780 m (799).

## Come sono fatti

- **Motore geometrico** (`ship3_geo.py`, numpy): ogni oggetto è un blocco di triangoli con dati per vertice; scafo a sezioni (`ship3_loft.py`),
  piastre a strati con uno smusso, un bordo consumato e il piede incassato (`slab`), pannelli per partizione binaria (`ship3_panels.py`),
  parti (torri, batterie, VLS, radiatori, ugelli, antenne, bocche di hangar: `ship3_kit*.py`), lettere vere dal carattere Barlow Condensed (`ship3_text.py`).
- **Dati per vertice** nei set UV (il motore li legge in `M_ASTRA_HullV3`): UV0 proiezione metrica a scatola (1 unità = 8 m), UV1 = (usura, sporco),
  UV2 = (tono della piastra, fuliggine / numero della finestra / codice colore della luce di via). Nessun colore di vertice e nessuna texture per nave.
- **Materiali** (`tools/ue_scripts/make_ship_materials_v3.py`; tavolozza in `art/blender/ship3_palette.py`, la stessa delle anteprime): vernice sopra metallo nudo che
  spunta dove la geometria dice (bordi e smussi), macchie e strisce di sporco, graffi, tono per piastra, finestre accese/spente con un lampeggio diverso per scafo
  (`M_ASTRA_ShipLight`), luci di via (rossa a sinistra, verde a dritta, bianca a poppa, rossa pulsante in chiglia; Mandate: una sola rossa pulsante), radiatori
  (parametro `Intensity` come prima), facce di taglio bruciate con braci (`M_ASTRA_ShipCut`, parametro `Heat`), decalcomanie di danno (`M_ASTRA_DamageDecal`).
- **Pezzi di rottura**: piani di taglio (`cuts_x_m`, prua per prima), stesso sistema di riferimento della nave intera, fascia di corazza strappata, fodera,
  paratia di fondo, ponti e ossature, travi, lastre piegate; `pivot_m` è il baricentro di ogni pezzo (per farlo ruotare su sé stesso).
- **Aquila aperta sul basso** (`docs/NAVE.md` §8.2): il blocco superiore e l'isola non hanno fondo né facce dentro lo scafo inferiore; `nave_checks` legge
  `data/ship/aquila_plan.json` e conta i vertici dell'esterno nei volumi liberi dei ponti 2-12: 0.

## Nel gioco

- **Importazione**: `/Game/ASTRA/Ships/SM_*` (stessi nomi di prima: il gioco non cambia), pezzi in `/Game/ASTRA/Ships/Sections/SM_SHIP_<Fazione>_<Nome>_Sec<Bow|Mid|Stern>`.
  Nanite, collisione complessa come semplice, materiali assegnati per nome dello slot (`MI_HULL_<A|M|G>_<Plate|Frame|Livery|Trim|Marking|Engine|Glow|Lights|Nav|Radiator|Cut|Glass|Blue|Green>`).
- **Rottura**: i pezzi stanno nello stesso sistema di riferimento della nave intera: a rottura si nasconde la mesh intera e si mettono i tre pezzi alla stessa trasformazione
  (l'immagine non cambia), poi gli impulsi. `manifest.json` dà per ogni nave grande `cuts_x_m` (piani di taglio, prua per prima), `sections` (limiti in x), `cut_faces` (centro, normale, estensione
  di ogni faccia di taglio, in assi di Unreal) e `pivot_m` per pezzo. La faccia di taglio usa lo slot `MI_HULL_<f>_Cut`: un'istanza dinamica con `Heat` da 1 a 0 spegne le braci.
- **Danni**: `MI_ShipDamage_<Burn|Hole|Torn|Impact|Strafe|Melt|Gouge|Blast>` sono decalcomanie deferred (atlante `T_ShipDamage_A`, parametri `Heat`, `Breach`, `Fade` come le cicatrici del gioco).
- **Luci**: `Intensity` dei radiatori come prima (il calore dell'Aquila); finestre e luci di via in `M_ASTRA_ShipLight` (modalità 0 finestre, 1 luci di via, 2 scia dei motori, 3 pannelli).
- **Misure**: sono cambiate rispetto alla v2 (Aquila 799 × 140 × 92 m contro 826 × 197 × 167; Praetorian 1129 contro 975 m): ricontrollare i raggi usati dal gioco
  (`extract_nav_lights.py` legge le mesh nuove).
