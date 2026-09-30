# Guida di stile di ASTRA (v0.3)

*Regole visive e sonore che rendono coerente tutto ciò che creo, anche quando parte da materiale gratuito di fonti diverse. Serve anche per l'autocritica delle catture (docs/ricerca/08, §7).*

## 1. Pilastri visivi
1. **Realismo vissuto.** Le cose sono funzionali, usate e riparate. L'usura ha una logica: più in sala macchine e nell'hangar, meno in plancia.
2. **L'eleganza dell'ASTRA.** Sagome pulite e curve intenzionali, mai decorazione fine a sé stessa.
3. **La luce racconta.** Lo stato della nave si legge dalla luce: allerta, danni, energia.
4. **La scala.** Dettagli a misura d'uomo (maniglie, targhe, portelli) per far sentire giganti le cose giganti.
5. **Leggerezza.** Ogni scelta rispetta i budget di prestazioni (docs/ricerca/11).

## 2. Linguaggi di design delle fazioni

### ASTRA Navy (noi)
- **Scafi:**
  - forme lunghe e orizzontali, a strati, con una "spina" dorsale;
  - prua affilata ma non aggressiva;
  - piastre ceramiche avorio o grigio chiaro su una struttura in metallo canna di fucile;
  - radiatori ripiegabili sui fianchi.
- **Livrea:** fasce blu navale con un sottile filo oro; numeri di scafo in bianco.
- **Luci:**
  - di navigazione bianche e azzurre, rossa a sinistra e verde a dritta;
  - scia dei motori bianco-blu;
  - finestre bianco caldo.

### Kharon Mandate (nemico)
- **Scafi:** lastre di corazza angolari e brutali, asimmetriche; prue a lama rivolte in avanti.
- **Colori:** basalto e grafite, con accenti di rame ossidato e bronzo.
- **Luci:** ambra e rosso; radiatori a vista che brillano d'arancio; scia dei motori arancio-viola.
- **Sensazione:** "navi sopravvissute", rattoppate con orgoglio.

## 3. Palette (hex)
| Uso | ASTRA Navy | Kharon Mandate |
|---|---|---|
| Scafo principale | `#E6E1D6` avorio · `#C9CCCF` grigio chiaro | `#23252A` grafite · `#3A3632` basalto |
| Struttura | `#4A4F55` canna di fucile | `#1A1B1E` nero ferro |
| Livrea / accento | `#1F3A6B` blu navale · `#B89A4E` oro | `#8C5A2B` rame · `#6E7F63` verderame |
| Luci | `#EAF4FF` bianco freddo · `#6FC3FF` azzurro | `#FFB347` ambra · `#FF4A2E` rosso |

**Interni ASTRA per reparto** (strisce luminose e mostrine):
| Reparto | Colore | Hex |
|---|---|---|
| Command | blu | `#3E7BFA` |
| Engineering | ambra | `#FF9F1C` |
| Medical | verde acqua | `#2EC4B6` |
| Security | rosso | `#E63946` |
| Flight | giallo | `#FFD60A` |
| Science & Sensors | viola | `#9B5DE5` |

## 4. Stati di luce della nave
| Stato | Luce |
|---|---|
| **Condition Green** | Bianco caldo e neutro, strisce di reparto tenui |
| **Condition Yellow** | Accenti ambra, luce generale al 85% |
| **Condition Red** | Strisce rosse pulsanti lente, luce bianca al 45%, luci d'emergenza a pavimento |
| **Blackout** | Solo strisce d'emergenza e segnaletica fotoluminescente, e il fumo diventa visibile |
| **Carica dei railgun** | Calo del 10–20% per mezzo secondo su tutta la nave |

## 5. Materiali
- **PBR fisico rigoroso:** albedo non metallici tra circa 30 e 240 sRGB, metalli puri, rugosità sempre variata.
- **Texture condivise** alla EVE:
  - due trim sheet (scafo, interni);
  - materiali ripetibili da fonti CC0;
  - un atlante di decalcomanie;
  - maschere di usura e sporco nei colori dei vertici;
  - livree come parametri di materiale.
- **Usura:** bordi consumati dove si passa, colature sotto le prese d'aria, bruciature vicino agli ugelli, graffi sulle maniglie.

## 6. Lingua, segnaletica e testo
- **Lingua del gioco: inglese.** Segnaletica, interfacce, nomi di luoghi, navi e fazioni, log e schermi sono in inglese. Solo gli NPC parlano la lingua del giocatore (tramite "the Interpreter").
- Segnaletica con pittogrammi universali e codici di ponte e sezione in stile navale, per esempio **"DECK 4 · SECTION C"**, **"ENGINEERING"**, **"FLIGHT DECK"**, **"MEDBAY"**, **"AUTHORIZED PERSONNEL ONLY"**.
- **Font (liberi, licenza OFL):** **Barlow Condensed** per segnaletica e titoli; **IBM Plex Sans** e **IBM Plex Mono** per interfacce e dati.

## 7. Interfacce diegetiche
- Pannelli scuri traslucidi, dati bianco-azzurri, avvisi ambra, criticità rosse.
- Schemi a linee, niente effetti retrò esagerati.
- Leggibilità prima di tutto: testo grande, contrasto alto, e colore mai usato da solo.
- Tavolo olografico: linee di elevazione, anelli di distanza, ellissi d'incertezza; colore per fazione (ASTRA azzurro, Mandate ambra, neutrali bianco, unknown grigio).

## 8. Spazio e fotografia
- **Neri profondi** e pochi punti di colore dalla nebulosa. Per Aurelia: stella arancione e nebulosa verde-azzurra (the Teal Veil), colori complementari.
- **Esposizione fisica per zona** e tonemapper filmico ACES.
- Bloom moderato; lens flare solo per stelle, motori ed esplosioni; grana leggera; aberrazione cromatica minima.
- Profondità di campo solo nei momenti cinematografici.

## 9. Suono
- Meccanico e concreto. Nel vuoto si sente solo ciò che passa attraverso lo scafo o la tuta; ronzio del reattore diverso per zona.
- Radio con filtro, scatto di trasmissione e fruscio.
- Allarmi distinti per pericolo: incendio, decompressione, impatto imminente, collisione.
- Colonna sonora orchestrale-elettronica generata con ACE-Step 1.5, dinamica secondo la tensione del Regista.

## 10. Riferimenti di atmosfera
| Opera | Cosa prendiamo |
|---|---|
| **The Expanse** | Interni vissuti e fisica credibile |
| **Star Trek** (Discovery, Picard) | L'eleganza della plancia |
| **EVE Online** | Nebulose e sagome delle navi |
| **Battlestar Galactica** (2004) | La grinta del centro di comando e del controllo danni |
| **Alien: Isolation** | Il tatto delle console |
| **Homeworld** | La scala delle flotte |
| **Interstellar** | Il realismo |

## 11. La plancia v3: linguaggio visivo (30/9)
La prima partita l'ha detto chiaro: la plancia v2 sembra un ufficio del 2026 (pareti beige piatte, sedie e scrivanie da
ufficio, monitor comuni, plafoniere). La v3 deve sembrare **il ponte di comando di una nave da guerra del 2491**.

**Riferimenti:**
- **Star Trek Discovery e Strange New Worlds**: plance luminose, console scolpite, vetro curvo, pannelli olografici sospesi;
- **The Expanse**: tutto è funzionale e tattile, schermi a strati, maniglie, cinghie, cavi dove servono;
- **EVE Online**: materiali scuri con linee di pannello sottili, bordi luminosi, strati di sporco discreti, interfacce
  traslucide a linee sottili e cerchi.

**Regole:**
1. **Niente superfici piatte e vuote.** Ogni parete è composta: pannelli a strati in composito scuro con telai in metallo
   spazzolato, giunture luminose incassate, costoloni strutturali, prese d'aria, canaline, targhette, maniglie.
2. **Soffitto strutturale**: costoloni che si irradiano dalla cupola, luce indiretta nelle gole, condotti e grate
   incassati. Niente plafoniere rettangolari da ufficio.
3. **Pavimento**: piastre di metallo canna di fucile con una grana antiscivolo fine, canali luminosi incassati nel colore
   del reparto, l'emblema della ASTRA Navy intarsiato.
4. **Console scolpite**: scocche in composito avorio (`#E6E1D6`) e canna di fucile (`#4A4F55`), piani di lavoro in vetro
   scuro con interfacce emissive, pannelli olografici sospesi sopra (piani traslucidi emissivi), comandi fisici veri
   (tasti retroilluminati, manopole, cursori; al timone due leve di spinta), bordi luminosi nel colore del reparto.
5. **Sedute da nave**: gusci scolpiti con poggiatesta e braccioli con pannelli integrati, attacchi per le cinture, basi a
   colonna fissate al ponte. Mai sedie da ufficio con le ruote.
6. **Schermi**: ogni schermo è una superficie con coordinate UV 0–1 e uno slot di materiale col nome `SCREEN_<postazione>_<n>`:
   i contenuti li disegna il gioco, vivi.
7. **Luce**: la luce viene dall'architettura (gole, bordi, strisce, schermi) più pochi faretti mirati; in condizione rossa
   le strisce virano al rosso.
8. **Scala umana**: dettagli piccoli e credibili (viti, etichette "DECK 1 · SECTION A", avvisi, bocchette), usura lieve
   solo dove si tocca (bordi delle console, gradini, maniglie).
9. **Efficienza**: una manciata di materiali condivisi (trim sheet e decalcomanie), niente texture uniche enormi, geometria
   ricca dove si guarda (console, poltrone) e semplice dove no.

## 12. Le navi v3: scafi al livello di EVE Online (1/10)
Il linguaggio degli scafi dopo ARTE-NAVI (nota completa e anteprime in [progressi/navi_v3](progressi/navi_v3/README.md)):
1. **Geometria vera a ogni scala**: piastre a strati con smusso e bordo consumato, pannelli per partizione, portelli, sfiati,
   finestre, antenne, cannoni e ugelli con profondità; da 300 m di distanza una toppa di 50 m deve ancora leggersi come nave.
2. **Scritte in geometria** (Barlow Condensed): nomi e numeri di scafo, marcature di servizio, sempre in inglese.
3. **Usura con una logica**: la vernice lascia il metallo nudo sui bordi e sugli smussi, sporco e fuliggine dove passano i
   gas di scarico, un tono diverso per ogni piastra. Niente texture per nave: i dati stanno nei vertici (UV1–UV2), i
   materiali sono pochi e condivisi (`M_ASTRA_HullV3` e 14 istanze per fazione).
4. **Luci che raccontano**: finestre accese e spente con un lampeggio diverso per scafo; luci di via (rossa a sinistra,
   verde a dritta, bianca a poppa, rossa pulsante in chiglia); il Mandato ha una sola luce rossa pulsante.
5. **Fatte per rompersi**: tre pezzi (prua, centro, poppa) nello stesso riferimento della nave intera, con facce di taglio
   bruciate (corazza strappata, paratie, ponti, travi, braci che si spengono) e 8 decalcomanie di danno.
6. **Budget**: Nanite, al massimo 3 M triangoli per nave grande e 150 k per velivolo; ~28 MB di texture nuove in tutto.
