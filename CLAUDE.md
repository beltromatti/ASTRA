# Istruzioni permanenti per Claude — progetto ASTRA

Leggi SEMPRE prima [docs/STATO.md](docs/STATO.md) (dove siamo, cosa fare dopo) e, se serve, [docs/PIANO.md](docs/PIANO.md).

## Chi e come
- L'utente (Mattia, "beltromatti") è italiano: rispondigli in italiano. Dà la visione, **Claude dirige la tecnica** in autonomia end-to-end e contesta le idee quando c'è un modo più intelligente.
- L'utente ha dato autorizzazione ampia e permanente per il progetto (vedi docs/COSA_MI_SERVE.md §6): installazioni open-source, download gratuiti dalle fonti elencate (chiedi solo sopra i 5 GB), riscatto di articoli Fab gratuiti, licenze dei modelli "gated", uso dei suoi accessi nel browser integrato. **Mai acquisti.**
- **Regole di sicurezza invalicabili (anche con autorizzazione):** niente creazione di account, niente inserimento di password o codici OTP, nessun pagamento o trasferimento di denaro, nessuna modifica alle impostazioni di sistema/sicurezza, nessun aggiramento di CAPTCHA/Cloudflare. Se serve un nuovo account, scrivilo in docs/RICHIESTE.md e prosegui con altro (mai bloccarsi).
- Budget: **zero per tutto ciò che non è AI**. Spese AI solo tramite OpenRouter (credito limitato: tieni il conto in docs/STATO.md, avvisa in RICHIESTE.md sotto 3 $ residui). Modelli economici e veloci.

## Principi di lavoro
- **Lingua del gioco: INGLESE** (richiesta esplicita dell'utente). Nomi di lore, luoghi, navi, fazioni, segnaletica, interfacce, schermi, log, asset e codice: in inglese. Solo gli NPC rispondono nella lingua parlata dal giocatore. La documentazione per l'utente (docs/) resta in italiano, ma con i nomi ufficiali inglesi.
- Lavora sempre su `main`, commit piccoli e frequenti, push su `origin` (repo privato GitHub beltromatti/ASTRA). Messaggi di commit in italiano. Chiudi ogni messaggio di commit con:
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
- Aggiorna docs/STATO.md a ogni passo significativo (è la memoria che permette di riprendere dopo interruzioni).
- Segreti solo in `.env` (gitignored, hook pre-commit in `.githooks/`). Mai stampare valori di chiavi.
- Ogni asset di terzi va nel registro docs/LICENZE.md (fonte, autore, licenza, URL, modifiche). I contenuti grezzi di terzi stanno in `Content/ThirdParty/` o `art/_downloads/` (non su git); le rielaborazioni ASTRA in `Content/ASTRA/`.
- Qualità verificata, non a sensazione: catture visive + checklist di autocritica (docs/ricerca/08), gate di prestazioni (docs/ricerca/11), banco di prova AI (docs/ricerca/09).
- Target di riferimento: MacBook Air M4 16 GB (fanless). Obiettivi: 60 fps spazio, ≥45 fps interni a caldo; gioco ≤ 9 GB di memoria.

## Ambiente (verificato 2026-09-28)
- Progetto: `~/Desktop/ASTRA` (radice = progetto Unreal). Unreal Engine 5.8.3: `/Users/Shared/Epic Games/UE_5.8` (Core Data MetaHuman installato). Xcode 26.2 (NON aggiornare: ≥26.4 rompe UE 5.8; aggiornamenti automatici già spenti).
- Python per gli strumenti: **`/opt/homebrew/bin/python3.13` o ambienti `uv`** (il python3 di python.org non ha i certificati SSL). Blender 5.2.2 (`blender`), git-lfs, uv, espeak-ng installati.
- Controllo dell'editor: MCP ufficiale Epic (HTTP `127.0.0.1:8000/mcp`, avvio con `-ModelContextProtocolStartServer`) + toolset Python `AgentPythonTools` del progetto + fallback remote execution. Su Mac niente Live Coding: per il C++ chiudi l'editor, compila con `Engine/Build/BatchFiles/Mac/Build.sh`, riapri.
- Browser integrato dell'app: sessioni già aperte su Fab, Sketchfab, Blendkit, Hugging Face, Freesound, Mixamo, GitHub, OpenRouter.
- GitHub CLI autenticato (SSH) come `beltromatti`.
