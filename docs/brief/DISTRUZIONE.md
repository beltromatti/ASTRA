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
