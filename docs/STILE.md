# Guida di stile di ASTRA (v0.1)

*Regole visive e sonore che rendono coerente tutto ciò che creo, anche quando parte da materiale gratuito di fonti diverse. Serve anche per l'autocritica delle catture (docs/ricerca/08, §7).*

## 1. Pilastri visivi
1. **Realismo vissuto.** Le cose sono funzionali, usate e riparate. L'usura ha una logica: più in sala macchine e nell'hangar, meno in plancia.
2. **L'eleganza dell'ASTRA.** Sagome pulite e curve intenzionali, mai decorazione fine a sé stessa.
3. **La luce racconta.** Lo stato della nave si legge dalla luce: allerta, danni, energia.
4. **La scala.** Dettagli a misura d'uomo (maniglie, targhe, portelli) per far sentire giganti le cose giganti.
5. **Leggerezza.** Ogni scelta rispetta i budget di prestazioni (docs/ricerca/11).

## 2. Linguaggi di design delle fazioni

### ASTRA (noi)
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

### Mandato di Kharon (nemico)
- **Scafi:** lastre di corazza angolari e brutali, asimmetriche; prue a lama rivolte in avanti.
- **Colori:** basalto e grafite, con accenti di rame ossidato e bronzo.
- **Luci:** ambra e rosso; radiatori a vista che brillano d'arancio; scia dei motori arancio-viola.
- **Sensazione:** "navi sopravvissute", rattoppate con orgoglio.

## 3. Palette (hex)
| Uso | ASTRA | Mandato |
|---|---|---|
| Scafo principale | `#E6E1D6` avorio · `#C9CCCF` grigio chiaro | `#23252A` grafite · `#3A3632` basalto |
| Struttura | `#4A4F55` canna di fucile | `#1A1B1E` nero ferro |
| Livrea / accento | `#1F3A6B` blu navale · `#B89A4E` oro | `#8C5A2B` rame · `#6E7F63` verderame |
| Luci | `#EAF4FF` bianco freddo · `#6FC3FF` azzurro | `#FFB347` ambra · `#FF4A2E` rosso |

**Interni ASTRA per reparto** (strisce luminose e mostrine):
| Reparto | Colore | Hex |
|---|---|---|
| Comando | blu | `#3E7BFA` |
| Ingegneria | ambra | `#FF9F1C` |
| Medico | verde acqua | `#2EC4B6` |
| Sicurezza | rosso | `#E63946` |
| Volo | giallo | `#FFD60A` |
| Scienza e sensori | viola | `#9B5DE5` |

## 4. Stati di luce della nave
| Stato | Luce |
|---|---|
| **Condizione verde** | Bianco caldo e neutro, strisce di reparto tenui |
| **Condizione gialla** | Accenti ambra, luce generale al 85% |
| **Condizione rossa** | Strisce rosse pulsanti lente, luce bianca al 45%, luci d'emergenza a pavimento |
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

## 6. Segnaletica e testo
- La segnaletica è **nella lingua del giocatore**: la genero con pannelli di testo localizzati, non con texture fisse. Pittogrammi universali, ponte e sezione in codice (esempio: "4-C").
- **Font (liberi, licenza OFL):** **Barlow Condensed** per segnaletica e titoli; **IBM Plex Sans** e **IBM Plex Mono** per interfacce e dati.

## 7. Interfacce diegetiche
- Pannelli scuri traslucidi, dati bianco-azzurri, avvisi ambra, criticità rosse.
- Schemi a linee, niente effetti retrò esagerati.
- Leggibilità prima di tutto: testo grande, contrasto alto, e colore mai usato da solo.
- Tavolo olografico: linee di elevazione, anelli di distanza, ellissi d'incertezza; colore per fazione (ASTRA azzurro, Mandato ambra, neutrali bianco, sconosciuti grigio).

## 8. Spazio e fotografia
- **Neri profondi** e pochi punti di colore dalla nebulosa. Per Aurelia: stella arancione e nebulosa verde-azzurra, colori complementari.
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
