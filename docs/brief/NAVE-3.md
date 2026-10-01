# Brief NAVE-3 (F4.3, del lead): l'Aquila progettata come una nave vera

Le parole dell'utente (2/10): la nave deve avere una logica e una pianta **realmente intelligenti, progettate esattamente come
sarebbe progettata una nave spaziale vera**: un labirinto di ambienti, tunnel, ponti, cabine, camere, posti di ricerca, armerie,
palestre, dentisti, svago, ascensori (tanti, tutti funzionanti davvero: li fa ASCENSORI), «e tanto altro: questi sono solo esempi
per farti capire la portata»; tutta abitata da esseri intelligenti con personalità e identità (VITA). «Se necessario ripensa al
progetto degli interni: deve essere tutto realistico e intelligente.» Prima l'Aquila; poi le navi alleate e nemiche, così che tutto
diventi giocabile (abbordaggi, in futuro PvP): anche se non sono ancora camminabili, **devono comportarsi come tali e simulare ciò
che accade davvero sull'Aquila**. Leggilo come visione, non come elenco da spuntare: decidi tu ciò che è meglio per ASTRA.

LEGGI: CLAUDE.md; ARCHITETTURA §1bis e §6; PIANO §3 (F4); **NAVE.md** (tutto: il piano, il reticolo di 4 m, i toni, il kit, NAVE-2);
VITA.md (le 560 persone, i posti, i mestieri per stanza: `data/ship/aquila_life.json`); **DISTRUZIONE.md** (il modello dei danni gira sul
piano: compartimenti, porte, sistemi, paratie); BIBBIA §6 (i ponti dell'Aquila); STILE.md; il codice che legge il piano
(`UAstraShipPlan`, `AstraDamageMap`, `AstraLifeSim`) solo per sapere cosa non rompere.

## Cosa ho visto camminando (il lead, 2/10)
- Il Mess Concourse del Ponte 4: una sala grande, buia e spoglia (pannelli scuri, una stele, la bacheca dei turni): «troppo grande e
  spoglia». L'infermeria: un ospedale chiaro e pulito del 2020, non una nave del futuro. Le stanze nuove (anteprime di NAVE-2) sono
  arredate, ma tutto sta su un reticolo regolare: Spine, due passaggi, corsie di 16 m.
- Il programma riempie le corsie **a ciclo**: 125 armadietti di damage control, 74 sale macchine, 51 stive, 41 magazzini secchi, 38
  serbatoi, 23 lavanderie, 26 bagni, 16 sale di raccoglimento, 11 biblioteche; mancano dentista, barbiere, prigione (brig), ufficio
  della sicurezza, obitorio, nucleo del computer, impianti di supporto vitale (aria, acqua, rifiuti), simulatori, consulenza.
- **Un solo ascensore, finto**: `lift_main` ha sei fermate in punti diversi della nave (plancia, alloggi, mensa, infermeria, macchine,
  ponte di volo) e il gioco ti sposta dietro uno schermo nero. La navetta della Spine (Ponte 5) ha le fermate ma non corre: non c'è
  una galleria tra una fermata e l'altra.

## Cosa costruire
1. **Il programma di una nave vera.** Ogni spazio esiste per una ragione e sta dove un progettista lo metterebbe; scrivi il
   ragionamento in NAVE.md (perché qui, cosa c'è accanto, chi ci lavora, quanti posti). Zone e adiacenze: il comando attorno alla
   plancia (Ponti 1–2: CIC, sala riunioni, alloggi degli ufficiali superiori); i quartieri dell'equipaggio vicino a mensa, bagni,
   lavanderia; il complesso medico (Medbay, chirurgia, **dentista**, farmacia, **obitorio**, isolamento, consulenza); la scienza
   vicino ai sensori (laboratori, Astrometrics, cartografia stellare); la sicurezza (**brig**, ufficio, armeria, caserma dei marine,
   poligono) vicino all'hangar delle navette d'assalto; l'ingegneria (reattore, potenza ausiliaria, distribuzione, **supporto vitale**:
   trattamento dell'aria, recupero dell'acqua, rifiuti); la logistica (stive, magazzini, fabbricazione, officine); il volo; le santabarbare
   nel nucleo corazzato; lo svago (palestra, **simulatori**, bar e lounge, biblioteca, cappella, **barbiere**, osservatori); **due nuclei
   del computer** ridondanti e lontani. Per ogni sezione i servizi di quartiere in proporzione alla gente che ci vive e lavora (bagni,
   armadietto di damage control al nodo, trattamento dell'aria locale, un locale tecnico), **non a ciclo**. Cuccette per 560 più ~10 %
   di riserva; i mestieri e le case di VITA tornano (`tools/life.py check`). Ogni tipo di stanza nuovo con arredo vero, posti
   (`stations`) e lampade, e il suo mestiere in `aquila_life.json`.
2. **Il labirinto.** Una circolazione realistica: corridoi principali e **corridoi di servizio** più stretti e bassi (tubi, luce più
   calda e scarsa), **tubi di Jefferies** (pozzi con scala a pioli tra i ponti in ogni sezione, cunicoli orizzontali), boccaporti,
   **camere stagne sullo scafo** con armadietti delle tute, file di **capsule di salvataggio**, stazioni di damage control. Niente sale
   enormi e vuote: il volume si spezza con struttura, chioschi, schermi, piante, colonne, gente. Un labirinto leggibile: segnaletica
   di ponte, sezione e ordinata, frecce verso ascensori, infermeria, punti di raccolta. Prestazioni: il budget per ponte di NAVE-2
   (istanze, lampade come dati) resta il metro.
3. **La rete dei turboascensori (lato piano).** Pozzi veri che attraversano i ponti, con un atrio di sbarco su ogni ponte servito: almeno
   due ascensori della plancia (Ponte 1 → giù), coppie a prua, al centro e a poppa sui due lati, ascensori di servizio in ingegneria e
   al volo, un montacarichi per stive e santabarbare. Regola di massima: da ogni punto di un ponte un ascensore a ≤ 60–80 m di cammino
   (misuralo e riportalo). Il pozzo è un volume verticale libero su tutti i suoi ponti, con l'apertura della porta di sbarco nel muro
   dell'atrio; archi `lift` tra le fermate (costo = tempo di corsa). **Il contratto con ASCENSORI** (che fa il motore: vetture, porte,
   pannelli, voce) è il formato qui sotto.
4. **La navetta della Spine (lato piano):** una galleria continua tra le fermate (una corsia-tubo lungo il Ponte 5 o sotto la Spine),
   le fermate alle due estremità, la sezione F se trovi il modo; archi `shuttle` nel grafo.
5. **Le altre navi.** Lo stesso generatore produce il piano di **ogni classe** di `data/war/classes.json` (ASTRA e Mandato, ognuno
   con il suo linguaggio: le navi del Mandato sono diverse), con ponti, compartimenti (tipo, reparto, sistemi), porte, posti,
   grafo, equipaggio, controlli; file `data/ship/plans/<classe>.json` di dimensione contenuta. Non si costruiscono ancora in Unreal: li
   useranno FLOTTA-VIVA (la simulazione degli interni delle altre navi con il modello di DISTRUZIONE) e gli abbordaggi (F5.2).
6. **L'aspetto, dove conta di più** (corridoi, atri, lobby degli ascensori): più futuro e meno ufficio, nel linguaggio della plancia v3
   (STILE.md): strisce di luce, pannelli tecnici, condotti, schermi, segnaletica. La plancia avrà più dettaglio dei corridoi: qui serve
   il carattere, non il massimo.

## Il contratto con ASCENSORI (`vertical[]` e `transit[]`, versione 2 del piano)
```
vertical[]: { "id": "tl_mid_s", "kind": "turbolift" | "bridge" | "service" | "cargo", "name": "Turbolift 3",
  "shaft": { "x": -92.0, "y": 8.0, "w": 2.8, "d": 2.8, "z": [-78.0, 0.0] },          # centro e misure interne (m), fondo e cima
  "car": { "w": 2.4, "d": 2.4, "h": 2.6 },
  "landings": [ { "deck": 4, "z": -46.0, "door": [x, y, z], "yaw": 90, "lobby": "d4_lift_B1", "node": "<nodo del grafo>" }, … ],
  "speed": 6.0, "accel": 2.0 }                                                          # m/s e m/s² (ASCENSORI li tara)
transit[]: { "id": "spine_shuttle", "path": [[x, y, z], …], "stops": [ { "id", "section", "x", "door": [x, y, z], "yaw", "room", "node" } ],
  "car": { "mesh": "SpineCar", "length": 14.0 } }
```
Le stanze esistenti (plancia, alloggi del Capitano, Mess Hall, Medbay, Berths, Main Engineering, Flight Deck) restano dove sono: puoi
avvolgerle e collegarle meglio. Le alcove del vecchio ascensore e il codice dell'ascensore (`AstraHangar`) sono di ASCENSORI.

## Prove (offline, tue)
`ship_checks.py` a 0 problemi; `tools/life.py check`; **`tools/damage.py run --scenario all` resta 46/46** (DISTRUZIONE legge il piano);
anteprime Eevee delle stanze nuove e dei corridoi (guardale davvero: autocritica in docs/ricerca/08); le piante per ponte; il budget dei
triangoli; la distanza dall'ascensore più vicino per ponte; il rapporto del programma (stanze per tipo e perché). C++: nessuno (se ti
serve leggere qualcosa di nuovo nel gioco, chiedilo al lead).

## File tuoi
`art/blender/ship_*.py` (piano, ponti, kit, arredo, controlli, scheda), `tools/art/ship_textures.py` e `ship_planview.py`, `tools/life.py`,
`data/ship/*.json` e `data/ship/plans/`, le copie in `Content/ASTRA/Data/` (`aquila_plan.json`, `aquila_life.json`),
`tools/ue_scripts/build_ship_interior.py`, `docs/NAVE.md`. **Non tuoi:** il C++, la mente, gli ascensori (ASCENSORI: `AstraLift*`,
`art/blender/ship_lift.py`, `tools/ue_scripts/build_lifts.py`), il personaggio e le armi (ABBORDAGGI).

## Consegne
Fase A (piano: programma, labirinto, pozzi, galleria) e fase B (kit: stanze nuove, corridoi di servizio, tubi di Jefferies, aspetto): un
rapporto al lead con i passi d'integrazione (esportazione del kit, `build_ship_interior.py` nell'editor). Fase C (i piani delle altre
classi): dopo, quando il lead te lo dice. Commit piccoli e frequenti.
