# Gli effetti della guerra — com'è fatto il modulo VFX (fase F2.4, "la guerra bella")

*Documento del modulo VFX (2026-10-01). Cosa c'è nel codice, perché è fatto così, come si prova, come si mette in servizio e come
si tara. I nomi nel gioco e nei dati sono in inglese; il documento in italiano. Il contratto con la simulazione è in
[GUERRA.md](GUERRA.md) (§5.3 morte e danni, §6.8 effetti visivi); lo stile e l'esposizione in [STILE.md](STILE.md).*

**Stato: visto nel gioco (il lead, 5/10) e rifatto per le battaglie lunghe da VFX-2 (5/10, §2bis, §19).** La prima versione fu costruita senza
avviare l'editor né il gioco (regola dei moduli di supporto): il codice C++ compila e gira sul banco (`tools/war.py`, senza grafica), gli shader sono
compilati con il DXC del motore, lo script dei materiali è controllato contro lo stub Python dell'editor. VFX-2 l'ha provata nel gioco di prova del
suo worktree (porta 8771, con `astra.fx.series` e la camera libera `astra.fx.cam`, §12): ciò che dice questo documento della resa è misurato lì.

## 1. Il principio

La simulazione (`AstraBattleSubsystem.*`, `AstraWarDamage.cpp`) dice **cosa succede**; `UAstraWarFX` lo **disegna**. Niente di
quello che disegna torna alla guerra. Tre regole guidano tutto:

1. **Nessun attore per colpo, per scintilla, per fiamma.** Ogni genere di effetto è un livello di istanze
   (`UInstancedStaticMeshComponent`, un solo componente e un solo materiale per livello, quindi una chiamata di disegno), scritto in
   blocco una volta a frame: le trasformazioni e 12 numeri per istanza (§3). Gli unici attori sono quelli che servono davvero:
   un guscio per nave capitale per gli scudi (creato quando la nave è vicina, invisibile finché non ondeggia, distrutto con la nave), i tre
   pezzi di una nave spezzata, e il guasto sullo scafo (un decal).
2. **La simulazione degli effetti è C++ semplice, nel riferimento del sistema (metri).** Il riferimento dell'Aquila si applica solo
   quando le istanze si scrivono (`FFrame::ToWorld`). Per questo gira anche sul banco senza grafica (`-nullrhi`): lì i livelli
   contano e non disegnano, e il costo degli effetti entra nelle misure della guerra (cvar `astra.fx.sim`).
3. **Tutto è volume con bordo morbido, mai un piano.** Vedi §2: è ciò che fa reggere gli effetti sia a occhio nudo dalla plancia
   (pochi pixel) sia nella telecamera dello schermo principale (FOV fino a 0,3°, ×40–×80 su una nave a 10–30 km).

Perché non Niagara: ogni sistema Niagara è un asset da comporre nell'editor (non si può fare in modo affidabile dallo script),
costa un'unità di tick per emettitore, e la guerra ha bisogno di decine di migliaia di particelle per frame che sono già dati
della simulazione. Con le istanze la CPU paga qualche centesimo di millisecondo a frame (§13); la GPU paga solo la sovrapposizione
(additiva e traslucida) di ciò che è grande sullo schermo.

## 2. Perché reggono lo zoom (la regola più importante)

Il problema delle prime versioni: a ×60 un "tavolo" (anello visto di taglio) o un rettangolo sfaccettato (la bolla dello scudo, il
lampo di un colpo) diventano lastre enormi e sfocate. Ora:

- **Le forme sono solo due: sfere (dardi, lampi, palle di fuoco, fumo, scudi) e tubi (fasci, scie, pennacchi).** Nessuna mesh piatta.
- **Una sfera è disegnata come un disco rivolto allo schermo.** Lo shader usa la normale in spazio vista (`VN.xy`) per sapere dove
  si trova il pixel sul disco: un fotogramma di fuoco, le braccia di un riverbero, un'onda d'urto ("il bordo di un guscio che si
  allarga") sono sempre tondi, da qualunque lato guardi la telecamera e a qualunque ingrandimento. I bordi vanno a zero prima del
  contorno della mesh (`rim`): i poligoni della sfera a bassa risoluzione non si vedono mai.
- **Un bagliore ha il profilo di una "point-spread function"** (centro stretto, ali lunghe che vanno a zero), non un gradiente
  piatto: l'estensione visibile è circa il 0,6 della sfera, quindi le sfere si disegnano `GlowK = 1.7` volte più grandi del
  bagliore che rappresentano.
- **Un tubo calcola la sezione dalla sua direzione radiale** (la locale `(x, y, 0)` portata in mondo) e dal vettore della
  telecamera, non dalla normale della mesh (il cilindro del motore ha normali piatte): nucleo bianco, alone, estremità che
  sfumano. Visto da qualunque angolo è un cilindro luminoso morbido.
- **Dimensione minima in pixel, nel vertex shader.** I vertici di un tubo sottile o di una sfera piccola sono spinti fuori in modo
  che il raggio non scenda mai sotto mezza `MinPx` pixel: la larghezza di un pixel a quella distanza è calcolata dal campo visivo
  e dalla dimensione della vista che sta disegnando (`ViewProperty`: `TAN_HALF_FIELD_OF_VIEW`, `VIEW_SIZE`), quindi vale per la
  plancia come per la telecamera dello schermo principale. Il pennacchio ha il suo (si restringe verso la punta e tiene il minimo).
- **Le dimensioni sono in metri, non in pixel.** Un dardo di 5 × 300 m a 20 km è una scia di qualche pixel a occhio nudo e un
  bastoncino luminoso morbido a ×60: volume e scie crescono con lo zoom, il pavimento in pixel serve solo da lontano.
- **Fuoco e fumo sfumano con la profondità** (SceneDepth contro PixelDepth): dove un volume attraversa uno scafo non c'è un taglio
  netto.
- Gli attori degli effetti hanno il tag `ASTRA.Sky`: la telecamera dello schermo principale (lista "show only") li vede come il cielo.
  Non si tocca `AstraViewscreen.cpp`: le sue schede del bersaglio dicono già IN ITS GUNS / IN OUR RAILS / OUT OF RANGE.

Le prove fatte senza il motore: `tools/art/war_fx_shader_preview.py` (porta numpy degli shader di scudo, dardi e bagliori: le
immagini in `docs/progressi/vfx/`), `tools/art/war_fx_hlsl_check.py` (ogni snippet Custom-node compilato con il DXC del motore,
11 su 11).

## 2bis. Come si illumina una cosa sottile (VFX-2, 5/10: perché il fuoco «non si vedeva»)

Un dardo, un fascio, una scia, una scintilla sono cilindri lunghi e sottili. La prima versione li illuminava con il Fresnel (quanto la superficie
guarda l'occhio), che su un cilindro vale al massimo **sin θ**, con θ l'angolo fra la vista e l'asse: **visti da dietro o lungo la linea di tiro un
dardo era un disco nero e un fascio un alone appena percettibile** (`tools/art/war_fx_view_angles.py` li disegna da 90° a 0°, vecchio contro nuovo).
Ma tutte le telecamere che vedono «il nostro fuoco» stanno dietro o lungo la linea di tiro: lo schermo principale (a 1 km dal ponte, davanti alla
prua), il ponte, la ripresa «ASN AQUILA · FIRING ON ...» che sta sulla scia dei cannoni. Ora (`war_fx_hlsl.py`, DART e TUBE):

- il profilo trasversale è quello della canna **normalizzato per sin θ** (1 sulla linea di mezzo della striscia, 0 sul bordo, qualunque angolo; il
  minimo 0,12 evita che gli ultimi gradi esplodano);
- i **dischi di testa e di coda** sono ombreggiati come dischi (tondi, luminosi al centro): di faccia un dardo è un bagliore tondo della sua larghezza;
- ciò che corre lungo l'asse (la coda che sfuma, le estremità, il decadimento di una scia) vale **solo quanto l'asse sta di traverso alla vista**
  (`side`, da sin θ) e si media via quando non lo è: niente sparisce dietro il proprio scorcio;
- il dardo è un fuso (la sagoma si assottiglia alle punte) solo di lato; i dardi sono cilindri (non più sfere allungate: una sfera allungata vista di
  punta è un ago), come i tubi.

Il fatto che il dardo sia visibile non basta: a 12 km/s la scheggia è un punto che attraversa il cielo in pochi fotogrammi. Quello che dice
dove va il fuoco è la **scia** (§5): una linea dal cannone alla scheggia, luminosa alla testa e spenta alla coda (stile 5 del tubo).

Nota sullo schermo principale (`AstraViewscreen.cpp`, del lead): quando è puntato su un bersaglio con ingrandimento forte, **taglia con il piano vicino i
tre quarti del percorso verso il soggetto** (per non avere velivoli enormi e sfocati). È giusto per i velivoli, ma toglie anche tutto il volo delle
schegge: restano gli ultimi 7,5 km su 30 (0,6 s su 2,5 s di volo). Le schegge nell'inquadratura «ASN AQUILA · FIRING ON ...» (che non taglia) si vedono
dal cannone al bersaglio.

## 3. I file

| File | Cosa contiene |
|---|---|
| `Source/ASTRA/AstraWarFX.h` | i tipi (`FLayer`, `FPuff`, `FSpark`, `FBeam`, `FTrack`, `FGhost`, `FShield`, `FShipFx`, `FPiece`, `FDebris`...), i tetti, `UAstraWarFX` e i suoi ganci |
| `Source/ASTRA/AstraWarFX.cpp` | i livelli, il frame, i colpi (`DrawShots`), i fasci, le particelle, le luci, i cvar |
| `Source/ASTRA/AstraWarFXEvents.cpp` | lampi, fumo, onda d'urto, `Explosion`, scudi (`ShieldHit`), i colpi per tipo (`OnHit`), le morti |
| `Source/ASTRA/AstraWarFXHull.cpp` | tabella per nave, punti sullo scafo, la bocca dei cannoni, i segni di danno, fuochi e sfiati, spegnimento, pezzi, scudi, motori |
| `Source/ASTRA/AstraWarFXTest.cpp` | i comandi `astra.fx.*` (anche `series`, `cam`, `reset`: §12) |
| `Source/ASTRA/AstraWarFXData.inl` | **generato**: campane dei motori, pezzi e facce di taglio per ogni nave (non si modifica a mano) |
| `tools/ue_scripts/make_war_fx.py` | i materiali e le texture nell'editor |
| `tools/ue_scripts/war_fx_hlsl.py` | gli shader (testo semplice, uno per Custom node) |
| `tools/art/war_fx_textures.py` | i flipbook del fuoco e del fumo (`art/_cache/fx`, non in git) e le anteprime |
| `tools/art/war_fx_nozzles.py`, `war_fx_data.py` | le campane dei motori (Blender, dai generatori delle navi: `data/war/fx_nozzles.json`) e la tabella C++ |
| `tools/art/war_fx_shader_preview.py`, `war_fx_hlsl_check.py` + `dxc_check.cpp`, `war_fx_script_check.py` | le prove offline del §2 |
| `tools/art/war_fx_view_angles.py` | dardo, fascio e scia visti da 90° a 0° (vecchio contro nuovo): la prova del §2bis |
| `docs/progressi/vfx/vfx2_*.png` | le catture dal gioco di prova di VFX-2 (salve, missili, battaglia, reattore, rottura) |

La tabella per nave si rigenera solo quando cambia uno scafo: `blender -b --factory-startup -P tools/art/war_fx_nozzles.py`
e poi `python3 tools/art/war_fx_data.py` (il manifesto delle sezioni `art/export/ships_v3/manifest.json` non è in git).

## 4. I livelli, i materiali, i dati per istanza

| Livello | Forma | Materiale | Tetto | Priorità | Disegna |
|---|---|---|---|---|---|
| `Smokes` | sfera | `M_WAR_Smoke` (traslucente) | 220 | −2 | nuvole di fumo (flipbook `T_WAR_Smoke`) |
| `Fires` | sfera | `M_WAR_Fire` (additivo) | 200 | 0 | palle di fuoco (flipbook `T_WAR_Fire`) |
| `Plumes` | cilindro | `M_WAR_Plume` | 220 | 1 | pennacchi dei motori |
| `Tubes` | cilindro | `M_WAR_Tube` | 2000 | 2 | fasci laser, traccianti, **scie delle schegge, fiamma e fumo dei missili, scarico dei caccia** |
| `Darts` | cilindro (fuso) | `M_WAR_Dart` | 1500 | 3 | colpi di rotaia, scintille, perle delle scie dei missili |
| `Glows` | sfera | `M_WAR_Glow` | 700 | 4 | lampi, riverberi, punti caldi, bagliore dei motori, bordo delle onde d'urto |
| `DebrisL` | cubo | `M_WAR_Debris` (opaco, illuminato) | 140 | 0 | frammenti di scafo |

Più: `M_WAR_Shield` (il guscio, un attore per nave), `M_WAR_DamageDecal` e le otto `MI_WAR_Damage_<Burn|Hole|Torn|Impact|Strafe|Melt|Gouge|Blast>`
(decal profondi dall'atlante `T_ShipDamage_A/N`; se mancano si ripiega su `MI_ShipDamage_*` del generatore delle navi).

**I dati per istanza** (`AstraFx::Fill`, 12 float, `PerInstanceCustomData`): 0–2 colore, 3 intensità, 4 età, 5 P1, 6 P2, 7 seme,
8 larghezza (m), 9 lunghezza (m), 10–11 riservati. P1/P2 dicono allo shader cosa disegnare: dardo `Style` 0 colpo / 2 perla di una
scia / 3 scintilla; tubo `Style` 1 fascio / 2 scia di perle (P2: l'età alla testa) / 4 tracciante / **5 scia luminosa** (P2: il decadimento, e^-P2 alla coda contro 1 alla testa); bagliore `Kind` 0 palla / 1 lampo con strisce / 2 riverbero / 3 bordo di
onda d'urto; pennacchio: 0 ASTRA, 1 Mandate (P1) e il balbettio del motore malato (P2).

Esposizione: fissa nello spazio, EV100 6,6 (STILE §8): un emissivo di ~116 legge come bianco. Intensità usate: colpo 700, scia 190, fascio 520,
cannone 420, difesa di punto 360, **fuoco 85** (era 190: sommati, i fuochi di una nave che salta facevano uno schermo di 5000), bagliori 110–460, pennacchio 70,
fumo 45 (colore 0,42/0,40/0,38), guscio dello scudo 48 × `Gain` (l'intensità). Con l'esposizione dei mondi (EV 8,3, quasi due stop più scura) gli effetti leggono più deboli, nello schermo principale (EV 5,6, un diaframma più
aperto) più forti: si regola con `astra.fx.intensity`.

## 5. Le armi

Il tiro è disegnato **dalla bocca del cannone**, non dal punto dove la simulazione fa nascere il proiettile: `MuzzleOf` sceglie un
affusto del tipo giusto (`FAstraMount`) il cui arco di tiro contiene la mira, a turno, e il raggio dall'asse della nave lungo la
mira esce dal box dello scafo dove sta il cannone. Il colpo parte lì e si raddrizza sulla traiettoria vera in `OffsetTau`
(0,22 s per le rotaie, 0,55 i missili, 0,9 i siluri): nasce dal cannone e arriva dove la simulazione dice.

| Arma | Come si vede |
|---|---|
| **Rotaia** | un **dardo** (cilindro ombreggiato a fuso, bianco-caldo alla testa; lunghezza `clamp(velocità × 0,05, 90, 560)` m, larghezza `clamp(3,2 + danno × 0,055, 4, 9)` m) e la sua **scia**: un tubo dal cannone alla scheggia, lungo fino a 1,1 s di volo (13 km), luminoso alla testa e `e^-κ` alla coda (τ 0,42 s), che resta appeso dopo l'impatto e si spegne (`FWake`, 160); **il lampo alla bocca è della misura del cannone** (`R × 0,03` m, 3–14): nucleo bianco, bagliore con le strisce, un getto di scintilla lunga lungo la mira, un anello che si allarga, scintille e una luce sullo scafo intorno (8 luci in tutto) |
| **Laser** | un tubo dalla bocca al bersaglio, disegnato in 0,06 s, tiene e si assottiglia; larghezza `Radius × 0,016` (2,5–7 m); **il nucleo tiene il colore della parte** (azzurro o rosso, non bianco puro); alone alle due estremità, il calore sul bersaglio (bagliore + scintille + macchia di bruciatura); se il bersaglio ha lo scudo, il fascio finisce sul guscio |
| **Cannoni dei caccia**, Falcon del Capitano | raffiche di traccianti (tubi `Style` 4), 2 per fascio, 70 m × 1,1 m; un lampo alla bocca (`astra.fx.muzzle`) |
| **Caccia (scarico)** | entro 14 km una **striscia dello scarico** lungo la prua (30–320 m secondo la spinta, tubo di stile 5): una squadriglia che vira disegna archi nel cielo |
| **Difesa di punto** | un flusso di 4 traccianti, 38 m × 0,9 m; l'abbattimento: lampo + nuvoletta di fumo + scintille (`Flak`) |
| **Missili, siluri, razzi** | testa luminosa e **fiamma del motore** (tubo corto e caldo dietro la testa); scia di perle (un punto ogni 0,1 s, 9 punti: più larghe, scure e fredde con l'età) e **fumo lungo** (un punto ogni mezzo secondo per quattro secondi, tubi pallidi che si spengono lungo la traiettoria vera: dove il missile è stato, quindi anche dove ha virato); **sbuffi di gas di assetto** quando il cercatore vira forte (accelerazione laterale oltre 40 m/s²); alla fine del colpo la scia resta 1–1,5 s e svanisce (`FGhost`) |
| **Esche** | un piccolo sole caldo che deriva e si spegne (`Decoy`) |

Colori (`ShotColor`): le due parti si leggono a colpo d'occhio. ASTRA = azzurri (rotaia 0,42/0,70/1,00; laser 0,22/0,58/1,00;
missile 0,62/0,82/1,00), Mandate = arancio/rosso (rotaia 1,00/0,42/0,12; laser 1,00/0,16/0,07; missile 1,00/0,46/0,16); la difesa
di punto è ambra per tutti. Il colore del colpo che arriva è quello di chi spara: l'esplosione sul bersaglio usa il colore del tipo
d'arma, il guscio dello scudo quello della nave che lo porta.

## 6. Gli scudi

Un **guscio ellissoidale per nave** (assi = box dello scafo × 1,14 + 10 m in lunghezza, × 1,55 + 12 m di fianco e in altezza),
additivo, a due facce (si vede anche da dentro: l'Aquila dal suo ponte). Il materiale disegna un **reticolo di esagoni in spazio
metrico** (tre piani mescolati alla potenza 8: nessuna deformazione ai poli), con celle di `clamp(Radius × 0,035, 5, 18)` m:

- **Il colpo** (`ShieldHit`) aggiunge una *ondulazione* al guscio (fino a 6 alla volta: direzione sul guscio, forza, raggio, età,
  stress, seme): gli esagoni si accendono nel punto d'impatto, l'onda si allarga e svanisce in circa un secondo. Intorno: un lampo
  e qualche scintilla sul guscio. Lo **stress** del settore (1 − quanto ne resta) fa tremolare le celle e crepitare i bordi.
- **Il crollo** (`bSectorFell`): l'intera faccia si accende e lampeggia per 1,4 s, con un lampo bianco-azzurro, un getto di
  scintille e una luce.
- Il guscio di una nave capitale è creato **appena la nave è abbastanza vicina da contare** (entro 150 km) e sta lì invisibile (è il componente a non
  essere visibile, mai l'attore: lo schermo principale rifà la lista degli attori che mostra ogni mezzo secondo e lascia fuori gli attori nascosti,
  quindi un guscio creato al primo colpo gli mancherebbe per metà dell'ondulazione). Si vede **solo mentre qualcosa ondeggia**; sparisce con la nave.
- Colore: ASTRA azzurro (0,28/0,60/1,00), Mandate ambra (1,00/0,50/0,14).
- Le navi senza modello di danni (i caccia): un lampo bluastro.

Parametri del materiale per istanza dinamica: `Axes`, `Color`, `HexSize`, `Gain`, `Hit0..5`, `Info0..5`, `Collapse`.

## 7. Le esplosioni a strati

`Explosion(Pos, Vel, R, bAstra, Power)` (la stessa per un caccia che muore, un colpo pesante, un'esplosione secondaria, il
reattore dell'Aquila: cambiano raggio e potenza):

1. **lampo**: bianco, tondo, con le strisce anamorfiche (bagliore `Kind` 1; la striscia orizzontale è più corta di prima), **breve** (0,12–0,36 s secondo la potenza; era 0,3–0,96: due lampi sommati facevano mezzo secondo di schermo bianco);
2. **palla di fuoco**: da 1 a 5 "billow" dal flipbook di fuoco (un po' scostati l'uno dall'altro), 1,5–4 s, dalla temperatura bianca ai
   rossi di brace, **a un'intensità (85) tale che il corpo del fuoco resta sotto il bianco dell'esposizione e i billow si vedono**: il bianco è lasciato al nucleo;
3. **alone** che indugia un attimo, e **scintille** (12–46, fino a un centinaio nelle più grandi: tracce lunghe che si raffreddano,
   bianco-caldo, colore del metallo, rosso);
4. **fumo**: nuvole del flipbook di fumo (4–7,5 s) con una brace interna che si spegne;
5. **onda d'urto** (potenza oltre 0,45): il bordo di un guscio che si allarga (un anello da qualunque lato lo guardi, ora sottile: il 2 % del raggio);
6. **detriti**: cubi illuminati (2–8, fino a una ventina) che girano e brillano finché sono caldi, lasciando scintille;
7. **luce**: un lampo di luce sugli scafi vicini (candele ∝ R²·√P, 0,3–1,3 s; solo le più forti per l'occhio, §10).

Tutte le intensità e le durate di una esplosione si cambiano **a gioco acceso** con `astra.war.tune fx_<nome> <valore>` (la tabella di taratura della guerra, senza compilare):
`fx_blast` (1: tutto insieme), `fx_flash` (420), `fx_fire` (85), `fx_halo` (12), `fx_smoke` (45), `fx_wave` (90), `fx_light` (4000: candele per R²), `fx_reactor_flash` (380),
`fx_reactor_light` (4e9), `fx_cut_flash` (520: il lampo al taglio di una rottura), `fx_break_light` (1e9). I valori scritti qui sono quelli di serie.

**La sezione che va a zero** (`GutBurst`, quando `GuttedT` diventa 0): lo scoppio del suo cuore, il rivestimento che salta: un lampo, una palla di fuoco, un anello sullo scafo, dieci lastre di rivestimento e una pioggia di scintille, una luce. Poi brucia e sfiata (sotto).

**Esplosioni secondarie nelle sezioni che bruciano**: una sezione con fuoco (`Burn` oltre 8 s) fa ogni tanto una piccola esplosione
dentro lo scafo (una sventrata, ogni 2,5–7 s; una che brucia soltanto, ogni 7–16 s): una nave in fiamme non è mai quieta. Sono
anche i fuochi continui (palle di fuoco che escono dalla sezione, con fumo e luci), gli sfiati (getti bianchi dalla breccia, `Breach`)
e, mentre lo scafo si spezza (`bBreakingUp`), esplosioni dentro lo scafo sempre più ravvicinate.

## 8. Le rotture

Il contratto della simulazione è `FAstraDeathEvent` (come è morta, sezione, asse e punto di rottura, `CutBowX/CutSternX`, velocità di
separazione). Il modulo lo riceve **direttamente da `Destroy()`** (non consuma la coda `ConsumeDeathEvents`, che resta com'è).

- **Rottura (`Breakup`)**: nello stesso frame lo scafo intero sparisce all'occhio della plancia e al suo posto compaiono i **tre pezzi** v3
  (`SM_SHIP_<Faction>_<Name>_Sec<Bow|Mid|Stern>`), alla stessa posizione e assetto: *l'immagine non cambia* nell'istante della rottura. (Lo
  schermo principale, che conosce gli attori nuovi solo al giro successivo della sua lista, ogni 0,5 s, per 0,75 s continua a vedere lo scafo
  intero, portato avanti da qui sulla sua rotta: lo scafo è "visibile solo nelle catture" e i pezzi "nascosti nelle catture"; poi i ruoli si
  pareggiano e lo scafo viene distrutto. Niente salti sul bersaglio nello schermo.) I pezzi si separano con la quantità di moto giusta (il gruppo
  che si stacca contro il resto, in proporzione alle lunghezze), ruotano piano attorno al loro baricentro, e **le facce di taglio** (`MI_HULL_<f>_Cut`) partono roventi (`Heat` 1 → 0 in ~60 s) e
  alimentano fuochi, scintille e fumo finché sono calde; le finestre si spengono con un balbettio in 2,5 s. Un lampo e una fontana di
  scintille al punto di rottura, l'onda d'urto, quattro esplosioni lungo le due metà e, mentre si allontanano, **altre cinque minori fino a 4 s** (i magazzini, le linee, le celle che vanno uno dopo l'altro). Ogni pezzo diventa un ostacolo (`Wrecks`) per le navi
  che girano intorno.
- **Reattore (`ReactorBreach`)**: i pezzi sono scagliati via dalla palla di fuoco, carbonizzati (le superfici scure), e bruciano più forte;
  un lampo breve (0,2 s, 380: nel gioco il bianco pieno era questo, 950 per 0,9 s) e una palla di fuoco il cui cuore caldo si raffredda in billow lungo tutta la nave, due onde d'urto, sette scoppi minori in 1,6 s, una luce forte. L'Aquila (`OnAquilaBreach`): una catena di
  esplosioni lungo lo scafo e il lampo del reattore.
- **Scafo spento (`DisableShip`)**: nessuna esplosione; una scarica di scintille lungo lo scafo, poi le luci si spengono in 3,5 s con
  balbettio, i lampeggianti spariscono, il motore muore: un relitto alla deriva, buio. (Resta abbordabile: non cambia nulla per la guerra.)
- **Altre fini** di una nave capitale (e i caccia, i droni): `OnShipDestroyed` restituisce `false` e resta la vecchia esplosione; i caccia
  usano `OnCraftDestroyed` (una `Explosion`).
- **Tetti**: al massimo 36 pezzi (12 navi spezzate); oltre, i più vecchi spariscono; i pezzi oltre i 250 km vengono distrutti.

## 9. Il danno sullo scafo (decal)

Dove un colpo ha davvero toccato lo scafo (la posizione dell'impatto e la normale della faccia, per l'Aquila una traccia contro la
sua mesh del livello) si dipinge un decal profondo (60 m, 8–52 m di lato secondo il danno) con la macchia giusta per l'arma:
laser → bruciatura/fusione (`Burn`, `Melt`); cannone → raffica (`Strafe`); missili e siluri → squarcio o esplosione (`Hole` se il danno
sullo scafo supera 90, `Blast`); rotaie → strappo, impatto, solco (`Torn` oltre 70, `Impact`, `Gouge`). Il decal parte con la brace
(`Heat` 1) che si spegne in meno di un minuto. **Tetti**: 8 + 4 × classe per nave (il più vecchio di quello scafo se ne va), 150 in
tutto, al massimo 3 per frame, e solo per i colpi che hanno passato scudo e corazza (`Felt > 8`).

## 10. I motori e le luci

- **Motori**: ogni campana (posizioni dalla tabella generata) ha un pennacchio (tubo di lunghezza `R × (5 + 25 × spinta)`, larghezza
  1,9 R, che si stringe verso la punta con i diamanti d'urto, bianco-azzurro per ASTRA, ambra per il Mandate) e un bagliore sull'orlo.
  La spinta è quella vera: l'accelerazione lungo la prua rispetto a quanto i motori danno (`MaxAccel × EngineFactor`), smussata, con una
  spinta di crociera (0,16) per chi è in moto; un motore ferito balbetta (`Sput`); uno spento non c'è. I caccia hanno un solo bagliore.
- **Luci**: 8 luci puntiformi in un pool, in candele, **solo sul canale di illuminazione 1** (gli scafi esterni sono sui canali 0+1, gli
  interni solo sul 0: nessun lampo entra in plancia), scelte a ogni frame per forza *vista dall'occhio* (un'esplosione grande e lontana non
  scaccia una piccola vicina). Si usano per le esplosioni, il crollo di uno scudo, le rotture, i colpi pesanti. Cvar `astra.fx.lights`.

## 11. Il budget

I tetti stanno in `AstraWarFX.h` (`namespace AstraFx`) e sono pensati per il MacBook Air (senza ventola):
istanze 1500 dardi, 1200 tubi, 700 bagliori, 200 fuochi, 220 fumi, 220 pennacchi, 140 detriti; liste di particelle: 900 nuvole, 1800
scintille, 360 fasci, 140 detriti simulati (quando sono pieni il più vecchio cede il posto); 36 pezzi; 8 luci. **Chi lancia particelle chiede posto** (`Room(livello)`,
`RoomSparks()`): più il livello è pieno, meno ne lancia (le scintille scendono fino al 12%, i fuochi fino al 40%): la più grande
esplosione di una battaglia non spinge fuori le scintille del resto e un fuoco lungo non riempie il cielo di fumo. Un livello che si riempie
scarta (e conta, `astra.fx.stats`): mai un crash o un'allocazione.

Costo per frame: nessuna allocazione a regime (gli array sono riservati all'avvio), una scrittura in blocco per livello, il calcolo delle
istanze nel riferimento dell'Aquila. A distanza (dall'occhio): gli effetti sono tagliati oltre 160–190 km; le scintille si diradano oltre
60 km (a 160 km ne resta un sesto), i detriti si lanciano solo entro 40 km, il fumo entro 90 km, i fuochi dei pezzi entro 120 km; le scie dei
missili tengono 3 segmenti oltre 40 km. Così una battaglia lontana non consuma il posto di un'esplosione vicina. I decal e i gusci sono i soli oggetti del motore da gestire (§9, §6).

## 12. I comandi di prova (`astra.fx.*`)

Girano il vero codice della guerra (`ApplyHit`, `FireRail`, `Destroy`...): ciò che mostrano è ciò che la guerra mostrerà.

| Comando | Cosa fa e cosa aspettarsi |
|---|---|
| `astra.fx.swatch [secondi 40]` | **il primo da provare.** Una fila di ogni genere di effetto a 1,2 km davanti alla plancia, nei colori delle due parti, senza navi: sopra i bagliori (palla ASTRA, lampo bianco, lampo Mandate, riverbero Mandate, anello d'onda, palla Mandate, lampo laser ASTRA e Mandate, che invecchiano insieme); a occhio i colpi (ASTRA, Mandate, scintilla), il missile con la sua scia di perle, i due laser (ASTRA, Mandate), il tracciante del cannone e quello della difesa di punto; sotto i due pennacchi (azzurro, ambra), un frammento freddo e uno caldo, due palle di fuoco, un fumo scuro e uno pallido. Il log dice la stessa cosa. Se uno di questi è sbagliato, è sbagliato il materiale, non la guerra. `0` lo toglie. |
| `astra.fx.scene [km 6] [rotta 0]` | un Acheron (Mandate, `FX-T`) a quella distanza e rotta, un Praetorian ASTRA (`FX-A`) e uno Styx (`FX-S`) ai lati: fermi, muti |
| `astra.fx.fire <rail\|laser\|missile\|torpedo\|pd\|cannon\|all> [n] [da S\|A\|T\|aquila] [su T\|A\|S\|aquila]` | `all`: una per tipo a 1,2 s |
| `astra.fx.shield [bow\|stern\|port\|starboard\|dorsal\|ventral] [n 4] [su T]` | colpi sullo scudo di una faccia: esagoni che si accendono, onde, e dopo un po' il crollo |
| `astra.fx.hit <rail\|laser\|missile\|torpedo\|cannon> [danno 40] [faccia] [su T]` | un colpo che passa lo scudo: lampo, scintille, esplosione, macchia sullo scafo |
| `astra.fx.burn [su T]` | fuochi e sfiati in ogni sezione, una sventrata (e le sue esplosioni secondarie) |
| `astra.fx.break <bow\|mid\|stern\|reactor\|disable> [su T]` | la fine della nave, come la guerra la chiude |
| `astra.fx.clear` | le navi della scena spariscono (senza esplosione) |
| `astra.fx.reset` | tutto ciò che gli effetti tengono sparisce: i pezzi dell'ultima rottura, le particelle, le macchie, i gusci (un cielo pulito per la prova dopo; senza, i relitti dell'ultima rottura restano e lo schermo principale li inquadra al posto del bersaglio nuovo, che ha lo stesso id) |
| `astra.fx.stats` | cosa c'è e cosa costa (istanze ora/picco per livello, scartati, particelle, scie, pezzi, macchie, luci, ms/frame **senza il tempo delle catture di prova**) |
| `astra.fx.series <prefisso> [n 8] [ogni_s 0,25] [vs] [cam] [do <comando>]` | **n immagini della vista del gioco** (senza interfaccia) a intervalli dell'orologio degli effetti, dal fotogramma del comando; dopo `do` il comando da provare (`astra.fx.series b 30 0.1 cam do fire rail 3 aquila T`: una salva a passi). `vs` aggiunge il feed dello schermo principale (`<prefisso>_NN_vs.png`), `cam` la camera libera (`_NN_cam.png`). Una prova che prima era un colpo di screenshot a caso. |
| `astra.fx.cam <x> <y> <z> <yaw> <pitch> [fov 60]` \| `broadside [T]` \| `off` | una **camera libera di prova**: una SceneCapture che vede tutto ciò che vedrebbe la plancia (stesso EV 6,6), da dove la metti (metri nel riferimento del ponte: x avanti, y a dritta, z su; il centro dello scafo dell'Aquila è 172 m a poppa e 62 m sotto il ponte). `broadside` è la ripresa «ASN AQUILA · FIRING ON ...» dello schermo principale (320 m dietro il suo centro, 210 di lato, 100 su, lungo la linea di tiro, 46°) **senza passare dalla regia**: si prova il fuoco senza aspettare che il regista tagli. |

Cvar: `astra.fx.enable` (0 spegne tutto: si torna al vecchio disegno, da cambiare prima della battaglia), `astra.fx.intensity` (0,1–6, la
luminosità di tutto), `astra.fx.density` (0,2–2: quante particelle), `astra.fx.lights` (0 niente luci), `astra.fx.sim` (1: la
simulazione degli effetti gira anche dove non si disegna, cioè sul banco), `astra.fx.log N` (i contatori nel log ogni N secondi), **`astra.fx.wake`** (0–3: la luminosità delle righe
che scie e caccia disegnano; 0 le toglie) e **`astra.fx.muzzle`** (0,2–3: la misura del lampo alla bocca). Le intensità delle esplosioni: `astra.war.tune fx_*` (§7).

**Le prove di VFX-2 si fanno così** (nessun editor, il gioco di prova del worktree: `ASTRA_HARNESS_PORT=8771 tools/play.py launch --nomind --res 1280x720`): `astra.fx.scene 25 0`,
`astra.fx.cam broadside T`, `astra.cmd fire_weapons {'weapon':'railguns','contact_id':'FX-T','salvo':3}`, `astra.fx.series bc 60 0.15 cam`; per un'esplosione `astra.fx.reset`, `astra.fx.scene 5 0`,
`astra.fx.cam 1500 800 100 -12.9 1.2 35` e `astra.fx.series rc 30 0.12 cam do break reactor T`.

## 13. Misure (banco senza grafica, MacBook Air M4)

Sono i costi CPU della *simulazione e dello staging* degli effetti (il banco non ha GPU), misurati con `astra.fx.log` dentro
`tools/war.py run`:

| Scenario | Effetti, media per frame | Tick intero della battaglia | Picchi dei livelli (istanze / tetto) |
|---|---|---|---|
| apertura (Aurelia, 120 s: 9 navi, 14 caccia) | 0,01–0,02 ms | 0,035 ms | tutti sotto un decimo dei tetti |
| `scale_30x150` (300 s: 30 navi, 148 caccia, 5+2 reattori, 2 rotture, 66 colpi) | 0,02–0,055 ms (max 0,2–0,6 ms nei frame delle esplosioni) | 0,11–0,31 ms | dardi 1247/1500, bagliori 405/700, fuochi 149/200, fumi 200/220, pennacchi 86/220, detriti al tetto (140); nessuno scarto |

(Le due righe del tick variano da una prova all'altra con il carico della macchina: il lead usa il gioco mentre il banco gira.) I
livelli restano dentro i tetti anche nella battaglia più grande; il tetto dei detriti è raggiunto e funziona come deve (il chunk più vecchio
cede il posto a uno nuovo). **Il costo della GPU non è ancora misurato in modo pulito: vedi §19**; il gate di [ricerca/11](ricerca/11-efficienza-grafica.md) resta il riferimento.

## 14. I ganci nel resto del codice (tutti)

Il modulo tocca il codice della guerra solo dove serve; tutti i punti, perché il lead li veda in una pagina:

- `AstraBattleSubsystem.h`: dichiarazioni anticipate, `FAstraProjectile::FxSlot`, `friend class UAstraWarFX` e `friend struct FAstraWarFXTest`, i
  sovraccarichi `AddFlash(..., EAstraFxFlash)` e `AddBeam(..., EAstraFxShot, FromId, ToId)`, `WarFX` e `FxOn()`.
- `AstraBattleSubsystem.cpp`: `OnWorldBeginPlay` crea e inizializza `WarFX` prima di creare i visuali; `SpawnVisual` non fa più la bolla dello
  scudo né il bagliore del motore se gli effetti sono accesi; `FireRail`/`FireMissile` non creano l'attore del proiettile e chiedono la sua scia a
  `WarFX->OnProjectile`; `FireLaser` dice il tipo e le due navi del fascio; `Destroy()` costruisce prima l'evento di morte e poi chiama
  `OnCraftDestroyed`/`OnShipDestroyed` (se restituisce `false` resta la vecchia esplosione e il relitto); `AquilaBlasts`/`AquilaBreach`,
  `LaunchDecoys`, le esche del Falcon, `FirePilotGuns`, `ApplyHitLump`; `ClearSystem` (`WarFX->ClearAll()`); `Tick` chiama `WarFX->Tick`.
- `AstraWarDamage.cpp`: `ApplyHitModel` riempie un `FAstraFxHit` e lo passa a `OnHit` (senza gli effetti, il vecchio lampo e la vecchia macchia);
  `DisableShip` chiama `OnShipDisabled`.
- `AstraWarShipAI.cpp` (difesa di punto) e `AstraWarCraft.cpp` (cannoni): i fasci e i lampi dell'abbattimento dicono di che genere sono.

Nessuno cambia la simulazione: se `astra.fx.enable 0` o mancano i materiali (`M_WAR_*`), il gioco disegna come prima.

## 15. Messa in servizio (per il lead)

1. Unire il ramo e ricompilare (il C++ è completo).
2. Le texture dei fuochi e dei fumi (una volta; non sono in git):
   `uv run --python /opt/homebrew/bin/python3.13 --with numpy --with pillow python tools/art/war_fx_textures.py`
   (scrive `art/_cache/fx/T_WAR_Fire.png` e `T_WAR_Smoke.png`; con `--preview docs/progressi/vfx` anche i fogli di controllo).
3. Nell'editor, **senza PIE**: `tools/ue.py pyfile tools/ue_scripts/make_war_fx.py` — importa le texture e fa i materiali `M_WAR_*`,
   `M_WAR_DamageDecal` e le otto `MI_WAR_Damage_*`. Ogni materiale ha il suo try/except: il log finale dice quali sono fatti e quali no, e uno
   che fallisce non ferma gli altri. Il gioco tace e ripiega sul disegno vecchio finché ne manca uno dei sette essenziali (dardo, tubo,
   bagliore, fuoco, fumo, pennacchio, scudo); i detriti e i decal hanno il loro ripiego.
4. Avviare il gioco, in una battaglia o fuori: `astra.fx.swatch`, poi `astra.fx.scene 6 0` e i comandi del §12.
5. Guardare, nell'ordine: **(a)** il log all'avvio (`[WarFX] effects ready ...`; se dice "materials missing" lo script non è passato);
   **(b)** `astra.fx.swatch`: ogni elemento deve leggersi (se il materiale è nero o bianco: l'intensità, vedi §16; se è un quadrato: lo
   shader del disco non compila, vedi il log degli shader); **(c)** la stessa fila nello schermo principale con zoom ×40–×80 (puntandolo al
   punto davanti alla prua): niente lastre, niente rettangoli, i bagliori restano tondi; **(d)** `astra.fx.shield bow 40` su `FX-T`, vista dalla
   plancia e dal posto di Ops; **(e)** `astra.fx.break mid`, `reactor`, `disable`.

## 16. Come tarare (cosa girare e dove)

| Sintomo | Manopola |
|---|---|
| tutto troppo chiaro / spento | `astra.fx.intensity`; poi le intensità nei `Fill(...)` di `AstraWarFX.cpp` (colpo 700, fascio 520...), `AstraWarFXEvents.cpp` (esplosioni) |
| i bagliori troppo larghi o stretti | `GlowK` (AstraWarFX.h) e i raggi in `Explosion`/`OnHit`; i profili in `war_fx_hlsl.py` (`GLOW`) |
| i colpi troppo grossi/sottili a distanza | larghezza e lunghezza in `DrawShots`; il minimo in pixel (`MinPx` nei materiali, `make_war_fx.py`) |
| troppo fumo / fuoco | `astra.fx.density`; i tetti; `Smoke()`/`Explosion()` in `AstraWarFXEvents.cpp` |
| scudi troppo vistosi o invisibili | `Gain` (`TickShields`), `HexSize`, raggio e forza della ondulazione in `ShieldHit`; lo shader `SHIELD` |
| le luci bruciano gli scafi | `astra.fx.lights`; le candele nelle `AddLight` |
| esplosioni secondarie troppo frequenti | gli intervalli in `HullEmitters` (`BlastT`) |
| i pennacchi corti o lunghi | `DrawDrives`: `Len = R × (5 + 25 × spinta)`, `Width = 1,9 R` |
| le macchie sullo scafo grandi/piccole | `AddScar`: `Half`, i tetti per nave |
| le righe delle scie troppe, lunghe o forti | `astra.fx.wake`; `WakeSeconds` e `WakeTau` in `AstraWarFX.cpp`; `190.f * Intensity * WakeGain` nelle `Fill` della scia |
| l'esplosione bianca / senza struttura / senza fumo | `astra.war.tune fx_fire`, `fx_flash`, `fx_smoke`, `fx_wave`, `fx_blast` (§7), a gioco acceso; la durata del lampo in `Explosion` |
| i fasci o le scie troppo bianche, senza il colore della parte | `war_fx_hlsl.py`: TUBE (`core * 0.85` nel fascio, `core * 0.5` nella scia) |

Le immagini delle prove (`docs/progressi/vfx/*.png`) mostrano com'è pensato: lo scudo visto da fuori e dalla plancia, il crollo, i bagliori,
i dardi, i fasci e i pennacchi, i fogli del fuoco e del fumo.

## 17. Limiti noti

- **Prova nel gioco di prova di un solo giocatore** (VFX-2): le catture e le misure del §19 sono del suo worktree, a 1280×720, con la macchina carica (4 commandlet e il gioco del lead insieme: 6–40 fps): i
  costi della GPU sono ordini di grandezza, non il gate del MacBook Air.
- **TSR e traslucenti**: i bagliori e le scie additivi sono senza velocità; se sotto il TSR si vede un'ombra residua dietro i colpi veloci
  si accende "Output Translucent Velocity" nei materiali (non si può senza vederlo).
- **I fuochi sono sul box dello scafo**, non sulla mesh: su uno scafo molto rastremato un fuoco può stare un poco fuori dalla superficie
  (la tabella dei pezzi e delle facce di taglio è invece esatta, viene dal generatore).
- **I puff dei motori di manovra (RCS)** ci sono solo per i missili (gas di assetto quando il cercatore vira); non per le navi capitali. Niente nomi e numeri sugli scafi né il "tetto dell'isola" del brief: non fatti.
- **`SM_WAR_Ball`** (una sfera più fine per gli scudi) non è fornita: si usa la sfera del motore; basta fare la mesh in
  `/Game/ASTRA/FX/SM_WAR_Ball` e viene usata.
- **Cambiare `astra.fx.enable` a battaglia in corso**: i colpi già in volo non hanno l'attore (non lo hanno mai creato) e restano invisibili
  fino alla fine; si cambia prima della battaglia.
- **Lo schermo principale vede la separazione dei pezzi 0,75 s dopo la plancia** (§8): è il prezzo di non avere salti sul bersaglio; sparirebbe
  se la lista degli attori dello schermo si potesse aggiornare subito (§18). Lampi, fuoco e scintille della rottura ci sono da subito in entrambi.
- **Lo schermo principale a ingrandimento forte dentro una palla di fuoco** (la regia taglia sul pezzo del relitto a x8, FOV 7°, mentre la palla di fuoco di 300 m lo avvolge) vede solo la nube, anche a intensità basse: serve un'inquadratura larga quanto la palla di fuoco finché brucia (`GetBlasts`, §19).

## 18. Richieste fuori dal modulo (per il lead)

- `M_ASTRA_DamageDecal` (ARTE-NAVI) collega il pin RGB del parametro `AtlasRect` e poi ne maschera l'alfa: un vettore RGB non ha alfa, il
  decal non può funzionare così. Il modulo usa il suo `M_WAR_DamageDecal`; il vecchio si può togliere.
- La bolla dello scudo (`ShieldBubble`) e il bagliore del motore (`DriveFlare`) non vengono più creati quando gli effetti sono accesi:
  `C.Flare` dello schermo principale è già null-safe.
- Opzionale, in `AstraViewscreen`: oggi `RebuildShowList()` gira ogni 0,5 s e gli attori nuovi mancano allo schermo fino al giro successivo; il modulo
  lo aggira (gusci creati in anticipo, scafo intero portato avanti per 0,75 s dopo una rottura). Se la funzione fosse pubblica e fosse chiamabile
  da `UAstraWarFX` subito dopo aver creato i tre pezzi, il giro di attesa non servirebbe più.
- **Dopo ogni unione di VFX-2 si rilancia `tools/ue_scripts/make_war_fx.py`** (l'editor, una volta): gli shader dei materiali `M_WAR_*` sono cambiati (cilindri e tubi
  con la luce normalizzata, §2bis) e i `.uasset` generati **non** sono nel commit (non si uniscono: sono binari rigenerabili).
- Per la regia dello schermo principale, `UAstraWarFX::GetBlasts(TArray<AstraFx::FBlastView>&)` dà le esplosioni vive (posizione, raggio, età, nave, se è dell'Aquila, se è un reattore):
  una palla di fuoco di 300 m ha bisogno di un'inquadratura larga quanto lei finché brucia; a ×8 dentro la palla la camera vede solo la nube. Il modulo non tocca `AstraViewscreen`.
- La ripresa **Broadside** («ASN AQUILA · FIRING ON ...») è l'inquadratura giusta per il fuoco: il nostro tiro vi corre per 2,5 km davanti alla camera. Vale la pena che la regia
  la scelga ogni volta che l'Aquila apre il fuoco e non solo a cavallo di un ordine del Capitano.

## 19. VFX-2 (5/10): il fuoco si legge, le esplosioni hanno forma, i colpi lasciano un segno

Il punto di partenza ([PARTITE_2026-10-05.md](PARTITE_2026-10-05.md), il lead): un reattore che salta a 5 km era un lampo bianco che accecava plancia e schermo per un secondo e mezzo; il fuoco
a 20–45 km sullo schermo principale era poco visibile; la ripresa «FIRING ON ...» mostrava l'Aquila che sparava senza che lo sparo si vedesse. Il lavoro è in tre tappe, ognuna misurata nel gioco di prova
(porta 8771) con le immagini a passi di `astra.fx.series` e la camera libera `astra.fx.cam` (§12). Le anteprime sono in `docs/progressi/vfx/vfx2_*.png`.

**Tappa 1: il fuoco a ogni distanza.** La causa (§2bis) non era l'intensità: un cilindro o una sfera stirata vista di fianco ha il bordo in ombra e, vista di punta, un'ellisse piccola;
il bagliore alla Fresnel di un corpo sottile non supera `sin θ`, e le righe dei colpi sparivano proprio nelle viste da dietro e lungo la linea di tiro, cioè dove il giocatore le guarda. Ora il profilo
è normalizzato su `sin θ` (minimo 0,12), i dischi di estremità sono ombreggiati come dischi, le dissolvenze lungo l'asse pesano con `smoothstep(0,05; 0,35; sin θ)` (`tools/art/war_fx_view_angles.py` lo mostra da 90° a testa in su,
vecchio contro nuovo: `docs/progressi/vfx/view_angles.png`). Sopra, la scheggia ha la sua **scia** (tubo di stile 5, §5), il cannone il suo **lampo**, i missili il **fumo lungo** e i gas di assetto, i caccia la **striscia dello scarico**.
Il colore dice di chi è: azzurro/bianco per ASTRA, arancio/rosso per il Mandate; il nucleo di un fascio non è più bianco puro.

**Tappa 2: le esplosioni.** Un reattore non acceca più: il lampo è di 0,2 s (380) invece di 0,9 s (950), il corpo del fuoco resta sotto il bianco dell'esposizione (85) e i billow si vedono. Misurato sulla cattura
della camera libera a 3,6 km con FOV 35°: i pixel bianchi al picco sono il **2,4 %** (prima 96–99 % per mezzo secondo); sul feed dello schermo principale (un'unità di esposizione più chiaro) il 13,5 % per 0,2 s.
La sequenza è: lampo breve, palla di fuoco con nucleo e fiamme, fumo scuro (45, tono 0,42/0,40/0,38), anello sottile, scoppi secondari, luce sugli scafi. La rottura in tre pezzi (`_SecBow/_SecMid/_SecStern`) ha il lampo al taglio (520, 0,3 s), le
facce roventi, quattro scoppi lungo le metà e **cinque minori fino a 4 s**; la sezione sventrata ha il suo `GutBurst` (§7); `OnAquilaBreach` è riscritta in modo analogo. Tutte le intensità sono a gioco acceso con `astra.war.tune fx_*` (§7).

**Tappa 3: i colpi lasciano un segno.** Scudo a esagoni, macchie dello scafo (`GetDamageView` e decal, §9), sfiati e fuochi, finestre che si spengono per sezione e le sezioni che scoppiano per conto loro (`GutBurst`) fanno parte
del modulo dal 1/10; in VFX-2 è nuovo lo scoppio della sezione sventrata. Le macchie sullo scafo illuminato dal Sole **non sono ancora state verificate a occhio** nel gioco di prova (lo scafo del banco era sul lato notte).

**Come vederlo.** `astra.fx.scene 25 0` + `astra.fx.cam broadside T` + `astra.cmd fire_weapons {"weapon":"railguns","contact_id":"FX-T","salvo":3}` + `astra.fx.series bc 60 0.15 cam`: la salva dell'Aquila vista dal Broadside;
`astra.fx.reset`, `astra.fx.scene 5 0`, `astra.fx.cam 1500 800 100 -12.9 1.2 35`, `astra.fx.series rc 30 0.12 cam do break reactor T`: il reattore a 3,6 km.

**Costo.** Il banco (CPU, senza grafica) dà 0,02–0,055 ms/frame per gli effetti nella battaglia più grande (30 navi e 148 caccia, §13: misure di prima delle scie; con le scie e il fumo lungo il tetto dei tubi è salito a 2000 e il picco si legge con `astra.fx.stats`); in gioco `astra.fx.stats` conta ora le scie (`wakes`) insieme a tubi, pezzi, macchie e luci e **non include il tempo delle
catture di prova**. La misura pulita della GPU (milisecondi con un'esplosione che riempie lo schermo) è la prova che manca (§17): il gioco di prova ha girato carico (4 commandlet più il gioco del lead) e i suoi fps non sono il gate del MacBook Air.
