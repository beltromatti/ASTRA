# Brief DISTRUZIONE (F4.2, bozza del lead): i danni dentro l'Aquila, dove avvengono davvero

LEGGI: CLAUDE.md, ARCHITETTURA §1bis, PIANO §3 (F4), NAVE.md (la pianta: compartimenti, porte, portelli stagni `blast`, grafo),
VITA.md (le persone, le squadre che camminano, `RosterIn`, `RepairEtaSeconds`, `PlanChanged`), GUERRA.md §5.3 e §6.8 (i danni
fisici per sezione e faccia: dove arriva un colpo sull'Aquila), il codice: `UAstraShipSubsystem::OnHullHit` / `TickDamage` /
`dispatch_damage_control`, `UAstraShipPlan`, `UAstraLifeSubsystem`, il tavolo olografico (`holo ship`) e la pagina danni del datapad.

1. Il colpo nel posto giusto: dal punto d'impatto vero (sezione e faccia di GUERRA, direzione) al compartimento della pianta che
   sta dietro la corazza lì (`CompartmentAt`, i ponti e l'inviluppo); l'energia che passa decide cosa succede: falla, incendio,
   condotta, sistema; più compartimenti per i colpi forti. Via il ponte e la sezione a caso di oggi.
2. Il modello fisico per compartimento (codice: è fisica, non giudizio): pressione e aria (una falla svuota il compartimento e
   tira verso lo squarcio; i portelli stagni di sezione si chiudono, la pianta lo sa: `SetDoorSealed`, e VITA rifà i percorsi),
   campi di contenimento sulle falle (si accendono, costano energia, possono cedere), fuoco che cresce e si estende ai vicini
   attraverso le porte aperte, fumo, temperatura, energia e luci di emergenza, sistemi della nave che perdono potenza per i
   compartimenti dove passano (`systems` nella pianta).
3. Le persone: chi è in un compartimento colpito (VITA `RosterIn`) è ferito o muore secondo cosa succede; le squadre di
   riparazione camminano davvero (VITA) e lavorano sul posto; i feriti vanno in Medbay. Il Capitano può morire (in un
   compartimento che si svuota o brucia): la catena di comando e la fine della partita già esistono (l'XO prende il comando;
   abbandono nave; inchiesta).
4. Ciò che si vede camminando: effetti nei ponti costruiti (scintille, fumo, fiamme, sfiati, luce rossa d'emergenza, campi di
   contenimento visibili sullo squarcio, porte stagne chiuse con la scritta), e suoni. Budget: l'Air (pochi emettitori, solo
   vicino al Capitano).
5. Ciò che si sa: tavolo olografico e datapad (già fatti per ponte e sezione: portarli al compartimento), rapporti
   dell'equipaggio (gli eventi `damage report`, con il posto vero), schermo di ops.
Prove offline: un banco senza grafica (come `AstraLifeSim`/`AstraWarSim`) con colpi scriptati e verifiche (aria che esce e si
ferma ai portelli, fuoco che si estende e si spegne, squadre che arrivano, morti e feriti coerenti con i posti); il lead prova
nel gioco camminando durante la battaglia.

## Aggiornamento del lead (1/10, dopo la prima battaglia vera dopo GUERRA)

**Lo stato di partenza da sostituire** (`Source/ASTRA/AstraShipSubsystem.cpp`): `OnHullHit(Felt, ShieldTook, FromDir)` (chiamato da
`AstraWarDamage.cpp::ApplyHitModel`, che conosce anche il punto d'impatto `HitPos`, la faccia e la sezione di GUERRA) crea incidenti
su ponte e sezione **a caso** (falla, fuoco, condotto che toglie il 15 % al sistema), `RadiatorHit` strappa le ali dei radiatori,
`TickHeat` fa saltare condotti sopra il 92 % di calore, `PowerFactor` riduce scudi/armi/motori/sensori. Con i volumi di fuoco di
GUERRA era una spirale: sotto il fuoco concentrato dell'intero gruppo d'attacco a 2-3 km l'Aquila moriva in 3,5 minuti (calore
26 → 95 % in 30 s, tre radiatori in 15 s, scudi ridotti di metà dai condotti moltiplicati). Il lead ha messo un **tampone**
(commit 353506f, valori nei commenti): calore degli scudi dimezzato, un radiatore ogni 20 s e in proporzione al colpo, incidenti
con probabilità `Felt/100` (0,1–0,7), condotti additivi con minimo 55 %, guasti da calore ogni 18–26 s; Aquila 4200 di scafo,
1500 di scudi, ricarica 6, difesa di punto 6 canali. Senza Capitano ora regge ~4,5 minuti a bruciapelo contro quattro navi.
**Il tuo modello lo sostituisce**: gli effetti interni devono nascere da dove il colpo arriva davvero e da ciò che c'è dietro la
corazza (la pianta: compartimenti, `systems`, porte `blast`), non da tiri di dado; e non devono raddoppiare ciò che GUERRA già
calcola (i suoi `Sys[]` per sezione: motori, sensori, hangar, ponte, reattore, e `PlayerEngineFactor`/`RepairPlayerSystems`).

**Il metro** (misuralo nel tuo banco e scrivilo nel rapporto, il lead lo rifà nel gioco con `tools/survive.sh`:
`tools/play.py launch --nomind`, `astra.battle.time 170`, poi dopo l'arrivo (t ≥ 185) `astra.cmd mandate_tactics
{"focus":"AQUILA","stance":"flank","missiles":"salvo","ew":"jam"}`, e lo stato con `tools/play.py ship` ogni 15 s):
- nessuna spirale: la nave degrada in proporzione ai danni veri, e le squadre che arrivano la rimettono in piedi;
- a parità di fuoco il tempo di sopravvivenza non scende sotto quello di oggi (≥ 4,5 minuti senza Capitano), e una battaglia
  normale (il Capitano che tiene la distanza, la flotta che concentra il fuoco) dura decine di minuti;
- chi muore o è ferito era davvero lì (VITA `RosterIn`), e il numero è credibile (non decine a ogni colpo).

**Interfacce già pronte da usare**: `UAstraShipPlan::CompartmentAt/DeckAt/GetDecks/FindRoute/SetDoorSealed` (porte `bBlast` di
sezione), `UAstraLifeSubsystem::RosterIn/RepairEtaSeconds/Sim().PlanChanged()/LocatorText`, il contesto del Capitano con
`deck` e `section` (`CaptainContext`), `CaptainPlace()` dalla pianta. Il tavolo olografico (`AstraHoloTable::TickShip`) e la pagina
DAMAGE del datapad (`AstraScreensSubsystem::DrawPadDamage`) mostrano ponte × sezione: portali ai compartimenti.

**Coordinamento**: NAVE-2 è al lavoro sui ponti e rigenera `data/ship/aquila_plan.json` (`art/blender/ship_plan_gen.py`): tu la
pianta la LEGGI a runtime; se ti serve un dato nuovo nella pianta (per esempio il compartimento dietro ogni tratto di corazza, o
dove passano i condotti), scrivilo nel rapporto o chiedilo al lead, non modificare il generatore. MENTE-GUERRA lavora in
`mind/` e in `AstraWarSimCommandlet`: non toccarli. Prestazioni: niente attori che tickano per ogni compartimento (2251), niente
`TextRenderComponent` aggiornati a ogni fotogramma; gli effetti visibili solo vicino al Capitano. Regole di memoria: al massimo
2 commandlet alla volta, UBT limitato a 4 azioni, mai due editor.
