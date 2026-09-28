# Cosa mi serve da te, una volta sola (v2)

> **✅ Completato il 2026-09-28.** Varianti rispetto a questa lista:
> - niente chiave DeepSeek, perché DeepSeek si usa via OpenRouter;
> - niente ElevenLabs per ora;
> - GitHub funziona tramite l'accesso già fatto con gh;
> - la chiave Blendkit l'ho recuperata io dal tuo profilo;
> - il progetto vive in `~/Desktop/ASTRA`.
>
> Da qui in poi le eventuali nuove richieste le trovi in [RICHIESTE.md](RICHIESTE.md).

Tempo stimato: **30–45 minuti**. **Non devi comprare niente**: l'unica spesa è il credito AI. Dopo lavoro io in autonomia.

---

## 1. Decisioni: già prese ✓
- Nome in codice **ASTRA** ✓
- **Lingua automatica**: il gioco parla la lingua del giocatore ✓
- **Budget zero** per tutto ciò che non è AI ✓
- AI tramite **DeepSeek + OpenRouter** ✓
- **ElevenLabs**: nessun abbonamento. Il piano gratuito basta come confronto di qualità e come riserva per le lingue non coperte ✓

**Facoltativo, la parte creativa.** Se vuoi, dimmi qualcosa sul mondo: il nome della tua nave, le fazioni, il tono (Star Trek luminoso o The Expanse crudo), un'epoca storica. Se non dici nulla propongo io, e potrai cambiare tutto in qualsiasi momento.

---

## 2. Credito AI (l'unica spesa)
1. **DeepSeek**: su [platform.deepseek.com](https://platform.deepseek.com) ricarica circa 10 $, poi crea una API key.
2. **OpenRouter**: su [openrouter.ai](https://openrouter.ai) carica 10–20 $ di crediti, poi crea una chiave in Keys.
3. Su entrambi imposta un **limite di spesa**.

Stima durante lo sviluppo: **circa 10–30 € al mese** (benchmark, concept art, prove di gioco). DeepSeek costa la metà la sera e nel weekend.

---

## 3. Account gratuiti per la mia autonomia (15–20 minuti)
Crea gli account; le chiavi le incolli tutte nel file privato (sezione 4).

| # | Servizio | Cosa fare | Chiave nel file |
|---|---|---|---|
| 1 | [Sketchfab](https://sketchfab.com) | Crea l'account, poi Settings → Password & API → copia l'**API token** | `SKETCHFAB_API_TOKEN` |
| 2 | [Blendkit](https://www.blendkit.com) (ex BlenderKit) | Crea l'account, poi Profile → copia l'**API key** | `BLENDKIT_API_KEY` |
| 3 | [Hugging Face](https://huggingface.co) | Crea l'account, poi Settings → Access Tokens → nuovo token di tipo **Read** | `HF_TOKEN` |
| 4 | [Freesound](https://freesound.org) | Crea l'account e vai su [freesound.org/apiv2/apply](https://freesound.org/apiv2/apply). Nome: ASTRA; indirizzo di ritorno (callback): `http://localhost` | `FREESOUND_CLIENT_ID`, `FREESOUND_CLIENT_SECRET` |
| 5 | Adobe ID (per [Mixamo](https://www.mixamo.com)) | Crea l'account, oppure usa uno che hai; l'accesso lo fai nel browser dell'app (sezione 5) | — |
| 6 | *Facoltativo*: [ElevenLabs](https://elevenlabs.io), piano gratuito | Developers → API Keys | `ELEVENLABS_API_KEY` |
| 7 | *Facoltativo*: [api.data.gov](https://api.data.gov/signup) | Chiave gratuita per le scansioni 3D dello Smithsonian | `DATA_GOV_API_KEY` |
| 8 | *Facoltativo*: [GitHub](https://github.com/settings/tokens) | Token di sola lettura (download più veloci) | `GITHUB_TOKEN` |

**Hugging Face, modelli "gated".** Alcuni modelli open-source chiedono di accettare la licenza con un clic. Puoi farlo tu (pagine qui sotto), oppure autorizzarmi a farlo nel browser dell'app (sezione 6):
- [kyutai/pocket-tts](https://huggingface.co/kyutai/pocket-tts), la voce locale;
- [google/embeddinggemma-300m](https://huggingface.co/google/embeddinggemma-300m), per riconoscere gli ordini all'istante;
- [stabilityai/stable-audio-3-medium](https://huggingface.co/stabilityai/stable-audio-3-medium), per gli effetti sonori;
- eventuali altri te li segnalo man mano.

---

## 4. Dove mettere le chiavi
Il file è già pronto e leggibile solo dal tuo utente. Aprilo con:

```bash
open -e ~/.config/astra/secrets.env
```

Incolla ogni valore dopo il segno `=` e salva. **Non incollare le chiavi in chat**: i miei programmi le leggono dal file senza mai mostrarle.

---

## 5. Due accessi, quando ti apro le pagine (5 minuti)
Io non inserisco mai password: le pagine le apro io, l'accesso lo fai tu.
1. **Browser integrato dell'app**: accedi a **fab.com** (account Epic) e a **mixamo.com** (Adobe ID).
2. **Unreal Editor**: la prima volta che creo un MetaHuman comparirà l'accesso Epic per la parte cloud. Accedi una volta.

---

## 6. Autorizzazioni (rispondi "ok, autorizzo")
Per il progetto ASTRA, fino a tua revoca, mi autorizzi a:
1. **Installare** software gratuito e open-source necessario al progetto, tramite Homebrew, pip, npm, GitHub e Hugging Face:
   - Blender 5.2, git-lfs, uv, espeak-ng;
   - il plugin ufficiale Epic per Claude Code;
   - RealtimeMeshComponent;
   - i modelli di voce e labiale.
2. **Scaricare** asset gratuiti da queste fonti: Poly Haven, ambientCG, Blendkit, Sketchfab, NASA, ESA/Webb, Smithsonian, contenuti gratuiti di Fab, Mixamo, Freesound, Sonniss, Kenney, GitHub, Hugging Face. **Per i singoli download sopra i 5 GB ti chiedo prima.**
3. **Aggiungere alla tua libreria Fab articoli gratuiti**, accettandone la licenza standard, a ritmo umano.
4. **Accettare le licenze dei modelli gratuiti "gated"** su Hugging Face necessari al progetto.
5. **Usare il browser integrato con i tuoi accessi** solo per queste attività. **Mai acquisti, mai modifiche alle impostazioni dei tuoi account.**
6. **Controllare Unreal Editor, Epic Games Launcher e Blender.** Quando macOS o l'app chiedono il permesso, approva. Più avanti ti verrà chiesto il **microfono**, per i comandi vocali.
7. **Facoltativo**: un'attività automatica ogni due martedì che riscatta i regali gratuiti di Fab utili ad ASTRA.
8. **Facoltativo**: un backup del codice (non degli asset pesanti) su un tuo repository privato GitHub, gratis.
9. **Spostare questa sessione** nella cartella del progetto, `~/Developer/ASTRA`. Ti comparirà una richiesta di conferma.

---

## 7. Xcode: blocca gli aggiornamenti (1 minuto)
App Store → Impostazioni → disattiva "Aggiornamenti automatici". **Xcode 26.4 o successivo rompe la compilazione di Unreal 5.8**; il tuo 26.2 va benissimo.

---

## 8. Epic Games Launcher: una spunta (2 minuti)
Unreal Engine → Libreria → sulla versione **5.8**, freccia ▾ → **Opzioni** → spunta il **Core Data di MetaHuman Creator** (la voce può chiamarsi in modo simile) → Applica. Scarica qualche GB e serve per creare l'equipaggio.

---

## 9. Mentre lavoro
- Tieni il Mac alimentato e su una superficie fresca: non ha ventola, e le compilazioni sono lunghe.
- Se puoi, chiudi Docker e le finestre pesanti di Chrome: liberano RAM.
- Non serve guardare. Ti aggiorno con immagini e video dei progressi, e ti chiedo di scegliere solo le cose creative (voci, stile, nomi).

---

## Dopo il tuo "ok": cosa faccio io (M0, fondamenta)
1. Installo gli strumenti e creo il progetto ASTRA, configurato per il MacBook Air (profili grafici, memoria, cache).
2. Attivo l'MCP ufficiale di Epic, le skill Epic e il mio canale Python, e verifico tutto con catture dall'editor.
3. Preparo il repository, il registro licenze e le bozze della **Bibbia di ASTRA** e della **guida di stile**.
4. Faccio il **benchmark dei modelli AI dall'Italia** (DeepSeek diretto contro OpenRouter, qualità in italiano e in altre lingue, affidabilità dei comandi).
5. Monto il servizio vocale locale: riconoscimento, voci, labiale. Poi ti mando le **voci da ascoltare alla cieca** e scegli tu quelle dell'equipaggio.
6. Parto con **M1: la nave che si cammina**.
