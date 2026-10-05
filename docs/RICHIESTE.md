# Cose che servono da te

Qui scrivo solo ciò che **non posso fare io** (per regole di sicurezza: creare account, inserire password o codici, pagare). Non mi fermo mai ad aspettare: continuo con altro e riprendo quando hai fatto.

## Aperte

### 2026-10-05 — Accept Apple's updated developer agreement (2 minutes), then the release gets notarized
Notarization of ASTRA 0.1.0-alpha was refused by Apple with *HTTP 403: a required agreement is missing or has expired*: the account
holder has to accept the current Apple Developer Program License Agreement. Sign in at https://developer.apple.com/account (and
https://appstoreconnect.apple.com, Business / Agreements, if it asks there too) and accept what is pending. Then tell me "notarizza" and I run
`tools/release_mac.sh 0.1.0-alpha --skip-build` (it signs, notarizes, staples and zips the same build) and replace the release's file.
Until then the published app is signed with your Developer ID but not notarized: macOS asks players to choose Open Anyway once.

### 2026-10-05 — Windows build (when you have a PC with UE 5.8.3 and Visual Studio 2022)
Unreal cannot build Windows from a Mac. On the PC: `tools\windows\Setup-EpicContent.ps1`, then
`powershell -NoProfile -ExecutionPolicy Bypass -File tools\windows\Pacchetto-Windows.ps1 -Config Shipping -Zip`, and send me the zip's path
(or attach it to the release yourself: `gh release upload v0.1.0-alpha <zip>`).

### 2026-09-28 — Autorizzare l'account Epic nell'editor per i MetaHuman (una volta, 1 minuto) — ORA PRIORITARIO (fase F3: umani realistici per tutti)
Per trasformare l'equipaggio da manichini a **MetaHuman** realistici, Unreal usa il servizio Epic di *auto-rigging* dei volti:
richiede che tu autorizzi una volta il tuo account Epic nell'editor (io non posso accedere né concedere autorizzazioni).
- Stanotte, provandolo, l'editor ha aperto da solo una pagina Epic di autorizzazione nel browser: puoi chiuderla, è scaduta.
- Quando torni: apri l'editor e scrivimi "vai coi MetaHuman". Lancerò `tools/ue_scripts/make_crew_metahumans.py`;
  quando si apre la pagina Epic nel browser, accedi e clicca **Autorizza**. Da lì in poi il servizio resta autorizzato
  e creo e assemblo io gli otto ufficiali (preset scelti per nome e origine, pelle, occhi e corporatura su misura).
- Nel frattempo l'equipaggio resta con i manichini seduti in posa procedurale (funziona tutto lo stesso).


### 2026-10-02 — Provare l'impostazione RETINA (un minuto, quando giochi)
Nell'app (~/Applications/ASTRA.app, rifatta oggi) il menu IMPOSTAZIONI ha una riga nuova, **RETINA**: FULL (di serie) ricostruisce
l'immagine ai pixel veri del tuo display; HALF è come prima (metà dei pixel, raddoppiati dalla finestra: quello che vedevi pixelato).
Io non posso vedere l'app a schermo intero sul tuo display (gira solo in primo piano): dimmi se con FULL l'immagine è nitida e se il gioco
resta fluido (le tue impostazioni sono a 30 fps: c'è margine). Se è troppo pesante, HALF o IMAGE su SMOOTH.

## Chiuse

### 2026-10-05 — Credito OpenRouter: ricaricato dall'utente (13,27 $ residui alle 13:40) ✓

- 2026-10-02 — Credito OpenRouter: ricaricato (20 $ in tutto; 13,37 $ residui al 2/10 pomeriggio). Grazie. ✓
- 2026-09-29 — Finestre di permesso di macOS dopo la prova dell'app dal Desktop: risolte, la compilazione è ripartita. ✓
- 2026-09-29 — Permesso del microfono: concesso (la prima partita ha usato la voce). ✓
- 2026-09-28 — Chiavi API, account gratuiti, accessi nel browser, Core Data MetaHuman, aggiornamenti Xcode bloccati. ✓

