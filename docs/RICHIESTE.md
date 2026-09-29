# Cose che servono da te

Qui scrivo solo ciò che **non posso fare io** (per regole di sicurezza: creare account, inserire password o codici, pagare). Non mi fermo mai ad aspettare: continuo con altro e riprendo quando hai fatto.

## Aperte

### 2026-09-29 — Finestre di permesso di macOS in sospeso (quando torni, 1 minuto)
Provando la prima app pacchettizzata di ASTRA dalla cartella del progetto sul Desktop, i processi Python della mente
hanno chiesto a macOS di accedere alla **Scrivania**. Sul tuo schermo ci sono probabilmente una o più finestre
«… vorrebbe accedere ai file nella cartella Scrivania» (per **Python**, forse per **dotnet**/UnrealBuildTool o per **ASTRA**).
Io non posso rispondere a finestre di permesso di sistema.
- Finché restano aperte, macOS mette in coda altre richieste: **la compilazione del C++ è ferma** (UnrealBuildTool resta
  in attesa). Nel frattempo lavoro su ciò che non richiede di compilare.
- Cosa fare: rispondi alle finestre. **Consenti** per Python/dotnet (sono gli strumenti di sviluppo che già usano il
  progetto sul Desktop); per ASTRA puoi anche negare, perché d'ora in poi l'app si installa in `~/Applications` e tiene
  i suoi dati in `~/Library/Application Support/ASTRA`, fuori dalle cartelle protette.
- Poi scrivimi "permessi fatti" (o riavvia semplicemente la sessione): riprendo a compilare e pubblico il datapad.


### 2026-09-28 — Autorizzare l'account Epic nell'editor per i MetaHuman (una volta, 1 minuto)
Per trasformare l'equipaggio da manichini a **MetaHuman** realistici, Unreal usa il servizio Epic di *auto-rigging* dei volti:
richiede che tu autorizzi una volta il tuo account Epic nell'editor (io non posso accedere né concedere autorizzazioni).
- Stanotte, provandolo, l'editor ha aperto da solo una pagina Epic di autorizzazione nel browser: puoi chiuderla, è scaduta.
- Quando torni: apri l'editor e scrivimi "vai coi MetaHuman". Lancerò `tools/ue_scripts/make_crew_metahumans.py`;
  quando si apre la pagina Epic nel browser, accedi e clicca **Autorizza**. Da lì in poi il servizio resta autorizzato
  e creo e assemblo io gli otto ufficiali (preset scelti per nome e origine, pelle, occhi e corporatura su misura).
- Nel frattempo l'equipaggio resta con i manichini seduti in posa procedurale (funziona tutto lo stesso).

### 2026-09-28 — Permesso microfono (quando torni, 10 secondi)
Al primo uso del push-to-talk (tasto **V** in partita) macOS chiederà il permesso di usare il microfono: clicca **Consenti**.
Senza permesso l'equipaggio funziona comunque con i comandi scritti (console: `astra.say <testo>`). Io non posso concedere permessi di sistema.

## Chiuse
- 2026-09-28 — Chiavi API, account gratuiti, accessi nel browser, Core Data MetaHuman, aggiornamenti Xcode bloccati. ✓

