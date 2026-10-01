# I danni dentro l'Aquila — modulo DISTRUZIONE (F4.2)

*Documento del modulo DISTRUZIONE (2026-10-01). I nomi nel gioco sono in inglese; il documento in italiano. Vedi anche
[NAVE.md](NAVE.md) (la pianta su cui il modello gira), [VITA.md](VITA.md) (le persone che ci sono davvero), [GUERRA.md](GUERRA.md)
(il colpo che arriva) e il brief [brief/DISTRUZIONE.md](brief/DISTRUZIONE.md).*

## 0. In breve

Prima, quando la battaglia diceva «lo scafo è stato colpito», la nave sceglieva a sorte un ponte e una sezione e ci metteva un
incidente (un fuoco, una falla, un condotto), con un «tampone» che smorzava la spirale. Ora **un colpo entra dove è arrivato**: il
punto e la faccia dello scafo che GUERRA ha colpito (`ApplyHitModel`) diventano un punto della pianta, il colpo attraversa le
stanze dietro la corazza spendendosi in ciascuna, e **ciò che fa in una stanza è fisica**: un foro che lascia uscire l'aria
(e il campo di contenimento che si forma sul foro, regge, si logora, cede), un fuoco che cresce sul combustibile che c'è e passa
per le porte aperte, fumo e calore, condotti tagliati che tolgono potenza ai sistemi che ci passano, paratie di sezione che
si chiudono dietro l'aria che se ne va. **Chi muore o si fa male era davvero lì** (le 560 persone di VITA, nelle stanze in cui stanno),
le squadre di controllo danni (le squadre di VITA) **camminano fin lì e lavorano sul posto**, i feriti vanno in Medbay,
**il Capitano può morire** (la catena c'è già: il XO prende il comando, l'abbandono nave, l'inchiesta).

Le cifre, dal banco (sei semi, il gruppo d'attacco che concentra il fuoco sull'Aquila per dieci minuti: §6): **272 colpi, 117 arrivano
dentro, 36 fori, 64 fuochi, in media 1 morto e 6 feriti** (nove colpi su dieci cadono in stanze vuote: macchine, serbatoi, depositi),
**lo scafo non scende mai sotto il 16 %** e l'abbandono non scatta mai in dieci minuti (il «tampone» vecchio faceva abbandonare in 2 semi su 6 dopo
~290 s), **nessuna spirale**: i danni crescono in proporzione ai colpi veri, le squadre li rimettono in piedi e quello che resta è
poco. Un colpo costa nel modello microsecondi; il modello intero in media 0,1 ms per ogni 0,1 s di gioco, picchi di 0,4 ms (§7).

## 1. I file

| Cosa | Dove |
|---|---|
| La pianta come la vuole il modello: compartimenti (volume, stanze vicine, sistemi che ci passano), porte, paratie di sezione, profili di materiale | `Source/ASTRA/AstraDamageMap.*` (carica `data/ship/aquila_plan.json` su un thread di lavoro) |
| **Il modello** (codice puro: niente attori, niente mondo, deterministico dal seme) | `Source/ASTRA/AstraDamageModel.*` |
| I tipi che il modello, la nave e gli schermi condividono (`FAstraDamage`, `FAstraHullHit`) | `Source/ASTRA/AstraDamageTypes.h` |
| La nave che lo possiede: gli passa i colpi e le squadre, ne legge gli incidenti e la potenza, il Capitano, i portelli | `Source/ASTRA/AstraShipSubsystem.*` (`OnHullHit`, `TickInterior`, `TickDamage`, `TickCaptainFate`) |
| Gli effetti vicino al Capitano (fiamme, fumo, campi, scintille, segni sui portelli, suoni) | `Source/ASTRA/AstraDamageFx.*` |
| Il banco senza testa (`-run=AstraDamageSim`) e il suo lanciatore | `Source/ASTRA/AstraDamageSimCommandlet.*`, `tools/damage.py` |
| Suoni (sintetizzati, nessun audio di terzi) e la loro importazione | `tools/art/damage_sounds.py`, `tools/ue_scripts/import_damage_audio.py` |

Cambiamenti in file di altri moduli (piccoli, elencati in §10): `AstraWarDamage.cpp` (il colpo passa al modello come `FAstraHullHit`),
VITA (`AstraLifeSim/AstraLifeSubsystem`: `SiteOfIncident`, `RepairEtaFor`), `AstraShipPlan` (rotta attraverso una paratia chiusa),
`AstraLampPool` (le lampade seguono il danno), `AstraDoor` (registro dei portelli caricati), schermi e tavolo olografico.

## 2. Il modello

### 2.1 Dal colpo di GUERRA al compartimento

GUERRA dà un `FAstraHullHit`: dove ha colpito sullo scafo (metri nel sistema della mesh dello scafo), la faccia, la direzione in cui
viaggiava, il tipo (cinetico, a energia, esplosivo), cosa hanno preso scudo, corazza e struttura, e **`Felt`** = ciò che lo scafo ne ha
sentito (struttura + un quarto della corazza). Sotto `Felt` 3 non succede nulla dentro.

- **Entrata** (`SkinEntry`): il sistema della pianta è quello dello scafo spostato di (172, 0, 62); la scatola di GUERRA e la pianta
  hanno altezze diverse, quindi l'altezza del colpo sulla scatola (−1..1) si porta sul corpo dei ponti dalla chiglia al soffitto
  del Ponte 2. Il colpo entra dove l'inviluppo del ponte (`halfwidth`) dà la corazza a quell'altezza.
- **Cammino** (`Impact`): una marcia di 1 m alla volta lungo la direzione, fino a `clamp(14 + 0,6·Felt, 14, 70)` m, nei compartimenti
  (`CompartmentAt`, con 35 cm di tolleranza). Prima della prima stanza il colpo perde energia `e^(−T/22)` (T = metri di scafo); ogni stanza
  ne trattiene la sua parte (`Fill` del profilo: un deposito molto, un corridoio poco) e il resto va avanti ×0,85. Al più 5 stanze.
- Un'esplosione che esplode dentro scaglia l'onda anche nelle stanze vicine della prima (non oltre le paratie di sezione).

### 2.2 Cosa fa un colpo in una stanza (`Deposit`)

Dipende dal tipo (cinetico: fori; energia: fuoco e potenza; esplosivo: tutto) e dal **profilo** del tipo di stanza (`AstraDamageMap.cpp`: quanto
prende fuoco, quanto combustibile ha, quanta energia regge prima di rovinarsi, quanto è spessa la sua potenza, se ha estinzione fissa,
se è un deposito di munizioni). Le stanze grandi (hangar, sala macchine) non si accendono né perdono tutta la potenza per un colpo solo
(`DmSize`: radice del rapporto fra 1500 m³ e il volume).

- **Foro**: solo nella stanza dove il colpo entra, con energia ≥ 4: area `0,035·hole·tipo·(E−3,5)^0,9` m² (fino a 6 per colpo, 8 in tutto);
  da 0,12 m² è un incidente («hull breach»), sotto si richiude da solo (§2.8).
- **Fuoco**: `E/40 · tipo · accendibilità · dimensione · aria`; nasce dove il colpo è caduto (`FireAt`).
- **Potenza**: `E/45 · spessore dei condotti · dimensione`. Un corridoio porta il bus che alimenta le stanze lungo di esso: perdono parte della
  potenza anche loro.
- **Rottami** (`Wreck`): `E/Hard`; a 1 la stanza è perduta (niente aria, niente potenza). Un deposito di munizioni con un fuoco che nessuno
  spegne e senza potenza per l'estinzione **salta** (300 di energia nella stanza e nelle vicine).
- **Vittime** (`BlastPeople`): chi stava vicino al cammino del colpo (zone letali e ferenti attorno ad esso, con raggi per tipo: 2,4/1,8/3,4 m
  letali, 5/3,5/7 m ferenti, che crescono con la radice dell'energia). Il Capitano ha la sua riga (§2.6).

### 2.3 L'aria, i campi, le paratie

- **Pressione** per stanza (1 = nominale; 0,6 ancora a proprio agio, sotto 0,35 si sviene). Un foro la fa uscire come `P' = −(60 m/s · A / V)·P`
  (`astra.damage.vent`; prova: la Games Room, 1498 m³, foro 0,89 m²: 0,46 dopo 20 s, 0,23 dopo 40, come dice la legge). Tra due stanze
  comunicanti la pressione si livella (esponenziale, `astra.damage.mix`) attraverso l'apertura che c'è: corridoio aperto sempre, porta
  aperta secondo l'allarme, il traffico e le squadre al lavoro (`Openness`).
- **Impianti dell'aria**: rimettono l'aria che manca (con la loro portata e la potenza dell'assegnazione `life_support`); lo fanno poco finché la sezione
  perde (i suoi corridoi non possono respirare più di una falla), molto quando è chiusa e l'aria deve tornare.
- **Campo di contenimento** sul foro: si forma 1,2–3,2 s dopo (secondo la potenza della stanza), regge fino a 2,4 m² a piena potenza
  (`astra.damage.field_cap`), si logora per ogni colpo che cade nella stanza e cede a stress 1; ricade a 4–6 s dopo, poi si riforma. Ogni campo costa
  alla vita di bordo (`PowerNow.FieldLoad`: ~2 % l'uno: l'assegnazione `life_support` scende della metà del carico, le altre di un decimo); i
  campi si danno ai fori più grandi finché c'è carico.
- **Chiusura delle stanze** che perdono aria (le loro porte tengono dentro aria, fumo e fuoco) e **paratie di sezione**: una sezione i cui corridoi
  perdono aria (o bruciano, o si riempiono di fumo) viene isolata 2,5 s dopo: le paratie ai suoi due capi si chiudono, e si riaprono 8 s dopo che
  è di nuovo a posto. La chiusura passa alla pianta (`UAstraShipPlan::SetDoorSealed`: VITA rifà i percorsi, `PlanChanged`) e al portello del livello
  (`AAstraDoor::bLocked`, con il suo segno rosso, §3).

### 2.4 Il fuoco

Crescita logistica sul combustibile (`Fuel`, che si consuma) e sull'aria (`O2`), più lenta nelle stanze grandi; si spegne da sola quando il
combustibile finisce (680 s senza nessuno, nel banco), con l'aria che manca, con l'**estinzione fissa** (macchine, depositi, hangar: scatta se il
fuoco ha tenuto 6 s ed è forte e la stanza ha potenza; 22 s di scarica), o con la squadra. Passa a ogni stanza vicina per ogni apertura (corridoio
aperto, porta aperta, porta sfondata da un colpo forte). Fa fumo (sale, si diffonde per le aperture, esce da un foro) e calore (a 0,5 una persona
si brucia); mangia struttura dello scafo (`StructureBurn` → `PlayerInternalDamage`, `astra.damage.burn`) e scalda la nave (`AddHeat`).

### 2.5 La potenza: dalle stanze alle sei assegnazioni

Ogni stanza ha una potenza (1 = come costruita). I sistemi del piano che passano per una stanza (`systems`: reattore, refrigerante, armi, munizioni, sensori,
dorsale dati, vita, catapulte, bus di potenza, motori) perdono quel che la stanza perde. Ogni **assegnazione** dell'equipaggio (`shields`, `weapons`,
`engines`, `sensors`, `life_support`, `flight_deck`) è una media pesata dei sistemi che la fanno (per esempio gli scudi: 50 % reattore, 30 % refrigerante,
20 % bus), e ne tiene almeno la metà (`astra.damage.power_floor`: l'anello di riserva). `UAstraShipSubsystem::PowerFactor` è assegnazione × quel
fattore; **non raddoppia** i `Sys[]` di GUERRA (motori, sensori, hangar, ponte, reattore dello scafo), che continuano a contare per conto loro.

Le sezioni che GUERRA dichiara **sventrate** (struttura perduta: `GetDamageView("AQUILA")`) sono perdute con chi ci viveva (§2.6): niente aria, niente potenza,
nessun incidente.

### 2.6 Le persone e il Capitano

- **Chi c'è**: `PeopleIn` chiede a VITA le persone fisicamente in una stanza (posizione, se sono in squadra, se sono al posto). Un colpo e un pericolo
  (aria < 0,6, fuoco > 0,2, fumo > 0,5, calore > 0,45) lavorano su **chi è lì**, e solo su di loro: la voce dei feriti nel rapporto dice i nomi veri (il
  banco controlla che nessun nome sia di uno non presente).
- **Esposizione**: ognuno ha un tempo per uscire (1,5–4 s, più la strada alla porta a 3 m/s, più 3–12 s se era al posto); mentre c'è dose di
  ipossia, ustione e fumo; a ipossia 12 / ustione 6 / fumo 25 cade, a 75 / 14 / 60 muore; se esce con una dose forte esce ferito. Le squadre in tuta non
  ne soffrono.
- I feriti vanno in Medbay (VITA). Un morto è nel ruolino con la causa («hull breach», «fire», «conduit damage») e l'inchiesta lo racconta.
- **Il Capitano** (`TickCaptain`, ogni 0,25 s): ipossia, ustione, fumo e trauma nella stanza in cui sta (la pianta, a piedi). La vista si chiude dall'ipossia
  e dal dolore (`Peril`), il fumo fitto scurisce di grigio-bruno; cade (Down) e il XO prende il comando e manda la squadra più vicina; se nessuno viene, muore
  (la Games Room con un foro di 0,9 m²: vista chiusa a 8 s, a terra a 21 s, morto dopo 117 s; con una squadra mandata subito si sveglia in Medbay dopo
  ~50 s). Il Capitano morto riapre l'ultimo salvataggio dopo la carta («THE CAPTAIN IS LOST»); `astra.damage.captain 0` lo rende invulnerabile.

### 2.7 Gli incidenti e le squadre

Gli incidenti (`FAstraDamage`: foro, fuoco, condotto; al più 28 aperti, i peggiori) sono la vista del modello per le squadre e gli schermi: hanno compartimento
(`CompId`, `Place`), `Severity`, una nota («field holding, air 40 %, hole 1.2 m2») e la squadra. La squadra (le 4 di VITA) parte dalla stazione del Ponte 6, **cammina
per la pianta** (`Life->RepairEtaSeconds`, anche attraverso una paratia chiusa: +14 m di costo) e **lavora attraverso il modello**: un foro si chiude, un fuoco si
spegne, un condotto si ripara quando il modello lo dice, nel tempo che la gravità richiede (`WorkSeconds`: 14+34·gravità s per un foro, 8+14 per un fuoco,
10+22 per un condotto). Il tavolo olografico e il datapad (§3) mostrano la squadra che cammina e lavora. Anche i danni ai radiatori (ponte 7, sezioni E–G,
ala per ala) sono incidenti della nave e passano per lo stesso elenco.

### 2.8 Cosa guarisce da solo

Quel che è troppo piccolo per un incidente si rimargina: un foro sotto 0,12 m² lo chiude la sigillante della corazza in ~25 s, un po' di potenza persa
(sopra 0,85) la rimette in strada l'anello in ~40 s. Senza, ogni battaglia lascerebbe la nave un po' più storpia per sempre (il banco lo mostrò: 21 campi
sopra fori minuscoli, 33 % della vita di bordo). Le rovine di struttura (rottami parziali o perduti) restano fino al cantiere.

## 3. Come si vede, si sente, si legge

**Le luci** (`AstraLampPool`, NAVE-2, e le luci delle stanze vecchie in `AstraShipSubsystem::UpdateAlertVisuals`): ogni stanza dice quanta luce restano
alle sue lampade (`LightOf`): senza potenza restano le **strisce di emergenza rosse** (14 %), con un'alimentazione che cede **sfarfallano**, per un colpo
appena caduto sfarfallano due secondi e mezzo, un fuoco le fa arancioni e sfarfallanti, un foro che si svuota le fa rosse, il fumo le attenua, una stanza
perduta è al buio. Il pool (10 lampade vicine al Capitano) le legge ogni 0,2 s; nessun costo oltre.

**Gli schermi**: il **tavolo olografico** (sezione della nave, un ponte per fila) accende il compartimento vero lungo la fila del suo ponte, l'anello e
la squadra vanno lì, le etichette dei peggiori otto hanno il luogo («FIRE · 4D · GAMES ROOM / TEAM 2 · 40%»), le paratie chiuse sono barre bianche;
la pagina **DAMAGE del datapad** fa lo stesso (compartimenti accesi, paratie, l'elenco dei peggiori con luogo, tipo e come sta, «n bulkheads sealed · m fields»);
la griglia di **Ops** (ponti × sezioni) mostra l'incidente peggiore di ogni cella con il posto e il cammino della squadra; le pagine di Ops ed Engineering dicono
la **potenza vera** della stanza (non più il «−20 %» scritto a mano). L'evento «damage report» dell'equipaggio ha il luogo vero.

**Gli effetti** (`AstraDamageFx`), solo per i pericoli più vicini (35 m dall'occhio, al più due ponti), solo sui ponti caricati
(`UAstraDeckStreaming::IsReadyAt`) e con pochi pezzi in pool (nessun attore per compartimento, niente testo ridisegnato): **fiamme** (3 al massimo per fuoco, una dove è
nato, le altre intorno man mano che cresce; materiale `M_FX_Blast`) con un pennacchio di fumo (`M_FX_Smoke`) e **due luci arancioni** sulle due stanze più vicine; **fumo**
sotto il soffitto verso il Capitano; **nebbia bianca** dell'estinzione; sul **foro** il **campo di contenimento** (disco di luce, ciano se regge e più agitato quanto più è
sforzato, ambra mentre si forma, rosso e a pezzi se cede), la **bruciatura** sulla parete (il decal di scoppio della battaglia, `M_FX_ScorchDecal`, con `Breach`) e, se nulla tiene il foro,
**l'aria che fugge in strisce** verso di esso; **scintille** dai condotti tagliati (tramite `AAstraBridgeFX::Burst`, con il suo lampo e il suo suono) ogni 1–3 s; al **colpo**, il botto
(`SW_Blast_Inside`) con una pioggia di scintille e, se apre una falla, `SW_Decompression`. I **portelli di sezione chiusi** portano su entrambe le facce «PRESSURE BULKHEAD / SEALED»
in rosso (testo fatto la prima volta e solo mostrato o nascosto dopo) e sbattono (`SW_Bulkhead_Slam`). **Suoni in ciclo**, uno per tipo, sulla sorgente più vicina e con
attenuazione: fuoco, aria che esce, ronzio del campo, estinzione. I suoni vanno sintetizzati e importati (§8); senza, l'effetto è muto e basta.

**Portelli e ponti che si caricano dopo**: una paratia sigillata mentre il suo ponte non era caricato si chiude quando il ponte si carica (`AstraDoors::OnPlaced`,
corrispondenza per posizione con `FAstraDamageMap::DoorNear`); il portello si riapre con la paratia.

## 4. Parametri e comandi

| Variabile | Cosa |
|---|---|
| `astra.damage.hole`, `.fire`, `.casualties` (1,5), `.burn` | scala dei fori, degli incendi, delle vittime, della struttura mangiata dal fuoco |
| `astra.damage.vent` (60 m/s), `.mix` (25), `.field_cap` (2,4 m²), `.fields` (0/1) | l'aria che esce, il livellamento, i campi |
| `astra.damage.doors` (1), `.power_floor` (0,5), `.captain` (1), `.auto_seal` (1) | quanto stanno aperte le porte, l'anello di riserva, il Capitano mortale, le paratie automatiche |
| `astra.damage.fx` (1), `.fx.reach` (35 m), `.fx.glow`, `.fx.smoke`, `.fx.volume`, `.fx.fires/.hazes/.vents/.sparks` | gli effetti: acceso, portata, luminosità di fiamme e campi, spessore del fumo, volume, quanti per tipo |
| `astra.lamps.*` | il pool di lampade di NAVE-2 |

Comandi: `astra.damage.info` (stato del modello, costo, la potenza che resta alle sei assegnazioni, il Capitano e gli incidenti aperti uno per riga), `astra.damage.strike [here|id o nome] [energia 40] [kinetic|energy|explosive] [nohole]`
(un colpo in un compartimento, «here» è quello del Capitano), `astra.damage.reset`, `astra.damage.fx.info`, `astra.lamps.info`; `stat Interior`, `stat Astra` (Damage FX, Lamp pool).
Se le fiamme o il campo sono troppo forti o troppo deboli nel gioco, `astra.damage.fx.glow`; se il fumo è nero o invisibile, `astra.damage.fx.smoke` (le intensità sono state scelte
senza vederle: la scala degli emissivi dell'interno è la stessa del tavolo olografico).

## 5. Il banco (`tools/damage.py`)

`tools/damage.py run [--scenario all|trace|air|fire|people|captain|fx|fxlive|survive] [--seed 1] [--seconds 600] [--set "astra.damage.hole=1.2,..."]` lancia
`UnrealEditor-Cmd -run=AstraDamageSim -nullrhi` (nessuna finestra, nessuna GPU: si può lanciare con l'editor e il gioco aperti; al più due processi alla volta) e scrive
`Saved/Damage/run.json`; `batch --seeds 6` ripete una prova con più semi. Il banco non usa le menti (nessuna spesa AI). Legge la pianta del repository
(`data/ship/aquila_plan.json`) nelle prove sul modello solo, e la copia in `Content/ASTRA/Data` (quella del gioco) nelle prove con il mondo.

| Scenario | Cosa prova |
|---|---|
| `trace` | 6000 colpi da 30 su ogni faccia: il 89 % arriva a un compartimento, 973 prime stanze diverse su 11 ponti, mediana dell'energia che arriva 24 su 30 |
| `air` | la legge dello sfogo (0,46 a 20 s dove la formula dice 0,49); le porte tengono l'aria; il campo regge, cede, si riforma; **sei paratie si chiudono** ai capi della sezione e **l'aria non passa**: le due sezioni vicine tengono tutta la loro; una squadra chiude la falla in 30 s e l'aria torna in 150 |
| `fire` | un fuoco cresce e si propaga (5 stanze), si spegne da solo senza combustibile (680 s), la squadra lo spegne in 18 s, l'estinzione salva un deposito, senza potenza salta |
| `people` (mondo intero con le 560 persone) | 23 stanze hanno 4+ persone; un colpo ferisce solo chi c'era (nessun nome di chi non c'era); non è una strage (14 su 206); le stanze aperte si svuotano in tempo; i feriti sono in cammino o curati; una sezione sventrata prende chi ci viveva |
| `captain` | sviene in aria sottile (21 s), muore se nessuno viene (117 s), la squadra lo porta fuori (46 s) |
| `fx` | il foro trovato sulla parete con la normale verso fuori, nulla fuori portata o sui ponti non caricati, le fiamme dentro la stanza e sempre uguali, i budget e l'ordine per distanza, le luci che seguono il danno (strisce rosse a 0,14, sfarfallio a un'alimentazione che cede, buio nelle stanze perdute), i portelli trovati per posizione (352 su 352) |
| `fxlive` | gli effetti fatti e mossi in un mondo vero (con le mesh e il materiale del motore): un ponte in fiamme dà 6 fiamme, 11 nuvole, strisce, 2 luci, 2 bruciature, entro i budget, 0,04 ms a tick, regge una raccolta dei rifiuti, rilascia tutto quando il Capitano è lontano; un portello caricato dopo il sigillo si chiude, porta il segno, si riapre con la paratia |
| `survive` | l'Aquila sotto il fuoco concentrato del gruppo d'attacco (§6) |

Il banco ha trovato: aria che gli impianti rimettevano più in fretta di quanto una falla la perdesse; fuochi che non si spegnevano mai o saltavano tre volte; fuochi che non
si propagavano perché la stanza chiudeva le porte; un ordine di porte che non apriva mai; vittime che saturavano; stanze grandi che prendevano fuoco per intero da un colpo; un
arresto in `AstraBridgeFX::Burst` (attore che non ha ancora cominciato a giocare) e due strutture `FAstraDamage` diverse nello stesso eseguibile (una regola di una definizione).

## 6. Il metro

Il metro del brief, misurato con sei semi (`tools/damage.py batch --seeds 6 --scenario survive`): la battaglia di apertura, il gruppo d'attacco del Mandato arriva a t = 180 s, a t ≥ 185
`mandate_tactics {focus AQUILA, stance flank, missiles salvo, ew jam}`; il Capitano non c'è (nessuna squadra al Capitano); 10 minuti di battaglia.

| | media | minimo – massimo |
|---|---|---|
| colpi / arrivati dentro | 272 / 117 | 212–322 / 80–168 |
| fori / fuochi | 36 / 64 | 15–55 / 11–150 |
| scafo dopo 10 min | 42 % | 17–72 % |
| scafo ≤ 50 % | 4 semi su 6, dopo 170–200 s dall'arrivo | |
| scafo ≤ 20 % | 1 seme su 6, dopo 226 s | |
| scafo ≤ 5 % / abbandono nave | mai | |
| morti / feriti (totali) | 1 / 6 (5 semi su 6); 188 / 103 nel seme in cui una sezione è stata sventrata dalla guerra | 0–3 / 3–9 |
| stanze in gioco al massimo / incidenti al massimo | 480 / 28 (la sezione sventrata ne mette 1800) | |
| persone nelle stanze attraversate da un colpo | 12 colpi su 117 attraversano una stanza con qualcuno (di media 12 persone) | |

Vincoli del brief: **nessuna spirale** (gli incidenti sono al tetto di 28 ma si chiudono man mano che le squadre arrivano: a battaglia finita non ne restano); **la sopravvivenza non scende**
(oltre 10 minuti in tutti i semi, contro i ~290 s dopo l'arrivo dei semi peggiori del vecchio «tampone»); **chi muore o è ferito era là** (il banco lo verifica a ogni colpo) e **il numero è credibile**
(0–3 morti e 3–9 feriti per battaglia, mai decine per colpo; solo una sezione sventrata ne porta via 188). `astra.damage.casualties 3` porta i morti a 1,8: la scala
delle vittime dipende da dove stanno le persone più che dal coefficiente.

**Cosa deve rifare il lead nel gioco**: `tools/survive.sh` (la stessa prova, nel gioco vero, senza mente: `incidents` ogni 15 s); camminare durante la battaglia fino a un fuoco e a un foro (§8:
comandi per provare senza aspettare), guardare le luci rosse, il campo, i portelli chiusi con il segno, il tavolo e il datapad.

## 7. Costo

- **Il modello**: la fisica fa un passo ogni 0,2 s di gioco e solo sulle stanze «in gioco» (quelle che non sono come costruite: 0 a nave intatta, 50–500 in battaglia, 1800 se una
  sezione è sventrata); a 60 fps i fotogrammi di mezzo non costano nulla e ogni dodicesimo fa il suo passo. Nel banco (un tick ogni 0,1 s) la media è 0,1 ms (0,0–0,3 fra i semi), il tick peggiore
  0,4 ms in media (2,1 ms nel seme con la sezione sventrata, il peggiore); `stat Interior` lo dice nel gioco. Il colpo (`Impact`) è una marcia di ~14–70 passi su una griglia: microsecondi. La pianta (2270 compartimenti, 1056 porte, 2398 legami)
  si carica su un thread di lavoro in ~130 ms.
- **Le luci**: dieci lampade già nel pool; letta del danno ogni 0,2 s (dieci ricerche) e lo sfarfallio a 12 Hz. Le luci delle stanze vecchie: una ricerca per luce a fotogramma.
- **Gli effetti**: la scelta (`FAstraFxPlanner::Plan`) costa 0,0005 ms quattro volte al secondo; le parti vive (al massimo 12 fiamme, 16 nuvole, 4 campi, 40 strisce, 2 luci,
  3 decal, 4 suoni) costano 0,04 ms a tick con un ponte in fiamme (misurato in un mondo senza grafica: il lavoro sul thread di gioco, non lo shading). Su una MacBook Air il costo vero
  è la sovrapposizione dei traslucidi (nuvole di fumo) e il decal: i budget sono comandi (`astra.damage.fx.hazes/.fires`).
- **Gli schermi**: il tavolo e il datapad ridisegnano solo quando sono guardati, come prima; l'elenco ordinato ha ≤ 28 voci.

## 8. Integrazione (cosa deve fare il lead)

1. **Compilare** (editor chiuso: niente Live Coding su Mac): `tools/ricompila.sh` o `Build.sh ASTRAEditor Mac Development`. I file nuovi sono già nel modulo; la compilazione unity è provata
   (i nomi anonimi del banco sono unici: `FCheck`/`Checks`/`Check` di `AstraNaveCommandlet` sono stati rinominati perché si scontravano con quelli di VITA nello stesso blocco).
2. **Il suono** (una volta): `uv run --with numpy --with soundfile --with scipy python tools/art/damage_sounds.py` (scrive `art/_cache/audio/SW_*.wav`), poi con l'editor aperto
   `tools/ue.py py "exec(open('tools/ue_scripts/import_damage_audio.py').read())"`. Mancando un suono l'effetto è muto e il log dice quanti ne ha trovati (`[DamageFx] ... sounds N of 4 loops`).
3. **La pianta in `Content/ASTRA/Data`** deve essere quella nuova (2270 compartimenti: `tools/life.py stage` dopo ogni rigenerazione): il gioco legge prima quella.
4. **Provare senza aspettare la battaglia**: nel gioco, camminando fino a una stanza, `astra.damage.strike here 80 explosive` (foro e fuoco nella stanza dove sei), `astra.damage.strike 40 energy` in
   un'altra, `astra.damage.info`, `astra.damage.fx.info`, `astra.damage.reset`. Con la battaglia: `tools/survive.sh` e camminare verso i fuochi.
5. **Il Capitano morto**: la catena esistente (XO al comando, abbandono nave, inchiesta) riparte dall'ultimo salvataggio dopo la carta «THE CAPTAIN IS LOST» (9 s): provarla una volta con
   `astra.damage.captain 1` e un foro grosso nella stanza dove si sta fermi.

## 9. Limiti noti

- **Gli effetti non sono stati visti**: il banco li ha fatti e mossi nel codice (con le mesh e un materiale del motore), nessuno li ha guardati con la GPU. Intensità dei materiali (`M_FX_Blast`, `M_FX_Smoke`),
  posizione e dimensione del campo e del decal sulla parete, altezza del testo sui portelli, scala delle fiamme: da regolare nel gioco (le variabili sopra, poi le costanti in `AstraDamageFx.cpp`).
- **Il fumo visto da dentro** non si disegna (le nuvole sono sfere a una faccia): la stanza fumosa si vede dal fuori e il Capitano dentro ha lo schermo che scurisce di grigio-bruno.
- **Corpi**: chi muore o si fa male scompare dal ruolino (come in VITA); non c'è un cadavere sul pavimento. Le squadre sono i corpi di VITA solo quando sono vicine al Capitano.
- **I morti sono pochi** per come sono fatti i colpi (il 90 % cade in stanze vuote): la cifra è onesta, non drammatica; una sezione sventrata è l'eccezione.
- **Le luci delle stanze vecchie** sono modulate per la stanza in cui stanno le lampade (posizione); una luce sul confine di due stanze segue quella che la contiene.
- **I sensori e le armi** non hanno un compartimento «bersaglio»: perdono potenza solo per i condotti, non per un colpo alle torrette (è il `Sys[]` di GUERRA).
- Il Capitano non nella nave (Falcon, pianeta, capsula) è fuori dal raggio dei compartimenti.

## 10. Fuori dai miei file (cosa ho toccato e cosa chiedo)

Toccati (piccoli, nei rapporti di unione): `AstraWarDamage.cpp` (costruisce e passa il `FAstraHullHit`); `AstraLifeSim.*`, `AstraLifeSubsystem.*` (la sede di un incidente e il tempo di arrivo di una
squadra per compartimento); `AstraShipPlan.*` (`FindRoute` e `EdgeCost` con la scelta di passare per un portello sigillato); `AstraNaveCommandlet.cpp` (rinomina di tre nomi); `AstraLampPool.*`
(il danno alle lampade); `AstraDoor.*` (elenco dei portelli caricati e l'evento di quando uno comincia a giocare); `AstraScreensSubsystem.cpp` e `AstraHoloTable.cpp` (i compartimenti al posto
della sezione). Non ho toccato `art/blender/ship_plan_gen.py`, `data/ship/aquila_plan.json`, `mind/`, `AstraWarSimCommandlet`.

Richieste: nessuna obbligatoria. Utili: (1) nella pianta, un campo per compartimento che dica se tocca la corazza e da che lato (oggi il modello lo ricava dal volume; basta); (2) per i corpi dei
morti e dei feriti nel luogo del colpo, un'idea per VITA (un corpo a terra finché qualcuno non lo porta via).
