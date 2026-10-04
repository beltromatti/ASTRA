# WINDOWS — ASTRA su Windows senza un grande rifacimento (F8)

*Scritto il 4/10/2026 dal modulo WINDOWS. Obiettivo: il giorno in cui qualcuno ha un PC Windows con la stessa versione di Unreal (5.8.3) e Visual Studio,
portare ASTRA lì costa una mattina di compilazione e una prova, non un rifacimento. Da un Mac non si può compilare per Windows (Unreal non fa
cross-compilazione da macOS: `docs/ricerca/01`), quindi tutto ciò che è solo-Windows è piccolo, isolato dietro guardie, e **tutto il resto è provato qui**.
Contratti: [ARCHITETTURA.md §1, regola 4](ARCHITETTURA.md). Piano: [PIANO.md](PIANO.md) F8.*

## 1. In breve

| Cosa | Stato | Come lo so |
|---|---|---|
| Il gioco avvia la mente (Python) su Mac, Windows e Linux **senza una shell** | fatto, provato sul Mac con la mente vera | comando `AstraMindLaunch` (§7): 78 controlli, anche il lancio vero della mente di sviluppo e di un pacchetto finto |
| Il log della mente lo scrive la mente (`ASTRA_MIND_LOG`), le sue uscite native comprese | fatto, provato | `bench/portable_unit.py` (processi veri) e il lancio vero |
| La mente parte su Windows (`SIGHUP` e `add_signal_handler` non ci sono: prima il suo `serve()` cadeva subito) | corretto, provato con segnali e cicli finti | `bench/portable_unit.py` |
| Ascolto portabile (Parakeet ONNX + faster-whisper), scelta e ripiego | provato **con i motori veri** su una frase di Pocket TTS | `ASTRA_TEST_PORTABLE_REAL=1`: `parakeet-onnx` 0,10 s, `faster-whisper` 1,7 s |
| Dipendenze: tutte con ruota per Windows x64 | provato con uv, senza rete né compilazioni | `tools/portability.py --lock` |
| Voci di sistema per le lingue senza Pocket TTS (SAPI) | scritto e provato con un PowerShell finto; **da sentire su un PC** | `bench/portable_unit.py` |
| Impostazioni, plugin MetalFX, schermo intero, risoluzione dinamica | fatto (§5) | compilato, controllo di struttura |
| Pacchetto Windows (`tools/windows/`) | scritto, analizzato con il parser di PowerShell e provato con un `uv.exe` finto; **da eseguire su un PC** | §6 |
| Compilazione MSVC di `Source/ASTRA` (più di 200 file) | **non verificabile qui**; i rischi che MSVC ha e clang no (codice irraggiungibile, ombre) sono tolti o cercati dal controllo (§7.3, §8) | il primo lavoro sul PC (§6) |

Quello che resta non provato senza un PC è elencato in §7.3.

## 2. L'audit: ogni punto solo-Mac, cosa fa, la risposta per Windows

### 2.1 Il gioco (C++, `Source/ASTRA`, plugin, configurazione)

| Punto | Cosa fa | Risposta per Windows | Stato |
|---|---|---|---|
| `AstraMindSubsystem.cpp::LaunchMind` | avviava `/bin/zsh -lc "cd … && exec uv run --frozen astra-mind >> log"`, con le cartelle dell'app (`Contents/Resources/mind`) e `~/Library/Application Support/ASTRA` | `AstraMindLaunch.{h,cpp}`: `CreateProc` su `uv` con argomenti, cartella di lavoro e ambiente; cartelle e nomi per sistema (§3) | fatto |
| login shell (`-l`) | dava a `uv` il PATH del profilo dell'utente (Homebrew) | il PATH del figlio è quello del gioco più le cartelle note degli strumenti (§3.2): **unica differenza sul Mac** | fatto, dichiarato |
| log con `>>` della shell | il log nasceva dalla redirezione | la mente apre da sola `ASTRA_MIND_LOG` (§4.4) | fatto |
| `ASTRA.cpp` (`#if !WITH_EDITOR && PLATFORM_MAC`) | porta l'app a schermo intero quando è in primo piano (una finestra creata a schermo intero può non partire mai su macOS) | su Windows il problema non c'è: `Config/Windows/WindowsGameUserSettings.ini` parte già a schermo intero senza bordi | fatto (marcato `portable-ok`) |
| `AstraSettings.*` riga RETINA | uscita 3D ai pixel veri del display: `r.SecondaryScreenPercentage.GameViewport` e il pavimento della risoluzione dinamica dimezzato | la riga e l'effetto esistono solo sul Mac; altrove nessuna riga, nessuna variabile toccata (§5) | fatto |
| `AstraSettings.h::Buttons[7]` | **difetto latente**: 8 righe (BACK compresa) scrivevano nel settimo posto di un vettore di sette | `Buttons[8]` e un `static_assert` | corretto |
| `Plugins/AstraMetalFX` | upscaler MetalFX al posto di TSR; Objective-C++ | già solo-Mac: `SupportedTargetPlatforms: ["Mac"]` nel `.uplugin`, `PlatformAllowList: ["Mac"]` nel modulo e nella voce di `ASTRA.uproject`; **nessun** file di `Source/ASTRA` lo include. Verificato dal controllo di struttura | già a posto |
| `Config/Mac/MacEngine.ini` | risoluzione dinamica sempre accesa (`OperationMode=2`), TSR, ombre, Lumen, memoria dell'Air | `Config/Windows/WindowsEngine.ini`: gli stessi valori che servono al codice del gioco e all'immagine, **non** quelli di memoria; tutti da tarare sul primo PC (§9) | fatto |
| `Config/DefaultDeviceProfiles.ini` | profilo Mac senza il volume di luce dei traslucidi | stessa riga per `[Windows DeviceProfile]` | fatto |
| `DefaultEngine.ini` | RHI di Windows: DX12 con SM6 (Nanite, Lumen, VSM); sezioni Mac/Xcode | già pronto per Windows; le sezioni `MacTargetPlatform`/`XcodeProjectSettings` sono ignorate | già a posto |
| `Build/Mac/Resources` | diritti, microfono, icona dell'app | niente da fare per Windows (il microfono è un'impostazione del sistema, §6.3); l'icona di `ASTRA.exe` è `Build/Windows/Application.ico`, fatta dalla stessa arte con `tools/art/app_icon_windows.py` (e `.gitignore` la lascia passare) | fatto |
| `t.IdleWhenNotForeground 1` (`!WITH_EDITOR`) | l'app non disegna in secondo piano (batteria e calore di un Air) | vale anche su Windows: una finestra dietro le altre non disegna. **Da decidere** guardando un PC | invariato |
| resto di `Source/ASTRA` | — | `grep` di `PLATFORM_*`, `FPlatformMisc::`, `/Users`, `/bin`, `HOME`, `NS*`, Metal: **nessun'altra** dipendenza dal Mac | verificato |

### 2.2 La mente (Python, `mind/`)

| Punto | Cosa fa | Risposta per Windows | Stato |
|---|---|---|---|
| `server.py::serve` `signal.SIGHUP` + `loop.add_signal_handler` | ferma la mente (e l'helper dell'ascolto) su SIGTERM/SIGHUP/SIGINT | `host.install_stop_handlers`: i segnali che ogni sistema ha, e il gestore del modulo `signal` dove il ciclo non ne ha (Windows: SIGTERM, SIGINT, SIGBREAK) | **corretto: su Windows cadeva all'avvio** |
| stampe, `logging`, scritture native | andavano alla shell | `host.redirect_output_to_log`: descrittori 1 e 2 sul file, `faulthandler`, tetto di 20 MB, UTF-8 | fatto |
| porta fissa 8765 | — | `ASTRA_MIND_PORT` (stessa regola nel gioco e nella mente): Windows tiene per sé intervalli di porte | fatto |
| `voice_stt_backends.py` Parakeet sul Neural Engine | helper Swift (`mind/stt_server`), solo Apple Silicon | `SherpaParakeetBackend`: lo stesso modello in ONNX su CPU (WER 31,8 % contro 17,7 %: `docs/protocollo_voce.md` §9) | già c'era; ora si scarica da solo dove non c'è l'helper |
| WhisperKit (`whisperkit-cli`) | Whisper sul Neural Engine | `shutil.which` non lo trova su Windows: sparisce da solo; `FasterWhisperBackend` è la riserva | già a posto |
| scelta dei motori | `ASTRA_STT` cambiava solo il primo | `ASTRA_STT=portable` (solo i motori portabili: la prova su un Mac), `off` (nessuno); `default_backends()` | fatto |
| `tts.py::SystemVoices` | `say` di macOS per le lingue senza Pocket TTS e mentre un modello si scarica | `_WindowsVoices`: SAPI tramite PowerShell (§4.3); Linux: nessuna voce di sistema | fatto, da sentire su un PC |
| `voice_qos.py` | classe di qualità del servizio di macOS per i thread della voce | non fa nulla altrove (già così); Windows non ha il problema dei core a bassa potenza di un Air | invariato |
| `audio_in.py` | PortAudio (`sounddevice`): multipiattaforma; scelta del microfono interno se il predefinito è Bluetooth | aggiunti i nomi dei portatili Windows (`Microphone Array`, `Integrated`) | fatto |
| percorsi | `pathlib` e `os.path.join` ovunque; `os.replace` per le scritture atomiche | nessuna modifica | verificato |
| codifica dei file di testo | dodici `read_text()`/`write_text()` senza `encoding` (Windows legge in cp1252) | `encoding="utf-8"` (il contenuto è ASCII: nessun effetto sul Mac); `PYTHONUTF8=1` nell'ambiente del figlio come cintura | fatto |
| dipendenze | `faster-whisper`, `sherpa-onnx` solo nell'extra `portable` | dipendenze normali con marcatore `sys_platform != 'darwin' or platform_machine != 'arm64'`: `uv sync` su Windows le prende; sul Mac con l'helper no (`--extra portable` per provarle) | fatto, `uv.lock` rifatto |
| ruote per Windows | — | tutte presenti per Windows x64 (CPython 3.13); **Windows su ARM no** (`ctranslate2` non ha ruota) | verificato |
| cache dei modelli di Hugging Face | collegamenti simbolici: su Windows richiedono il Modo sviluppatore | `huggingface_hub` ricade sulla copia da solo; `HF_HUB_DISABLE_SYMLINKS_WARNING=1` evita l'avviso | fatto |

### 2.3 Pacchetto e strumenti

| Punto | Cosa fa | Risposta per Windows |
|---|---|---|
| `tools/pacchetto.sh` | `RunUAT BuildCookRun` per Mac, la mente in `Contents/Resources/mind`, dati in Application Support, `codesign`, `PlistBuddy`, `rsync`, `cp -c` | `tools/windows/Pacchetto-Windows.ps1` (§6) + `Setup-ASTRA.ps1`/`.bat` per la prima configurazione |
| `tools/ricompila.sh`, `avvia_editor.sh`, `perf/*.sh`, `survive.sh` | strumenti dello sviluppatore Mac (zsh, `pgrep`, percorsi di Epic) | restano così: sono del Mac del lead. Per compilare su Windows vedi §6.2; il `pkill -f astra-mind` di `ricompila.sh` ha il suo gemello in `tools/windows/Stop-Mind.ps1` |
| `tools/play.py` | lancia il gioco col banco di prova | ora: `UE_ROOT`, `UnrealEditor.exe`, `ASTRA.exe` con `--app`, `Get-CimInstance`/`taskkill` al posto di `pgrep`/`pkill`, processo staccato di Windows |
| `tools/damage.py`, `life.py`, `lift.py`, `boarding.py`, `transport.py` | lanciano i comandi senza grafica | già usano `UE_ROOT` e il percorso di Windows. **Non ancora**: `tools/war.py` e `tools/space.py` (una riga ciascuno, come in `damage.py`), `tools/soak.py` (`pgrep`) |
| `tools/art/*`, `tools/ue_scripts/*`, Blender | arte e importazioni dentro l'editor o Blender | strumenti di sviluppo, nessun codice di gioco: invariati |

## 3. Come il gioco avvia la mente (`AstraMindLaunch`)

Un solo pezzo di logica per tutti i sistemi, in `Source/ASTRA/AstraMindLaunch.{h,cpp}`. Ciò che cambia tra i sistemi è **dato**, chiesto a una `FMachine`
(le cartelle del gioco, le variabili d'ambiente, l'esistenza dei file): il gioco la riempie dal sistema (`FMachine::Live()`), il comando di prova con
macchine inventate. Solo `Start()` tocca il sistema, con le chiamate portabili del motore (`CreateProc`, `SetEnvironmentVar`).

### 3.1 Dove sta la mente, dove sta uv, dove stanno i dati

| Cosa | Ordine di ricerca (il primo che esiste) |
|---|---|
| **la cartella della mente** (quella con `pyproject.toml`) | `ASTRA_MIND_DIR`; `ProjectDir/mind` (il repository: sviluppo); `ExeDir/../Resources/mind` (app del Mac); `RootDir/mind` (pacchetto Windows o Linux, accanto alla cartella `Engine`) |
| **uv** | `ASTRA_UV` (un percorso); `<mind>/bin/uv(.exe)` (quello che viaggia col gioco); le cartelle del PATH; poi `~/.local/bin`, `~/.cargo/bin`, `/opt/homebrew/bin`, `/usr/local/bin` (Mac e Linux) o `%USERPROFILE%\.local\bin`, `%USERPROFILE%\.cargo\bin`, `%LOCALAPPDATA%\Microsoft\WinGet\Links` (Windows) |
| **i dati della mente** (solo se è "impacchettata", cioè non è quella del repository) | `ASTRA_HOME` se c'è; Mac: `~/Library/Application Support/ASTRA`; Windows: `%LOCALAPPDATA%\ASTRA`; Linux: `$XDG_DATA_HOME/ASTRA` o `~/.local/share/ASTRA`; in mancanza di una "casa": `Saved/ASTRA` |

Una mente impacchettata tiene **tutto** nella sua cartella dei dati: la chiave (`.env`), i modelli della voce (`voice/models`), le cache, e l'ambiente Python
(`UV_PROJECT_ENVIRONMENT=<dati>/venv`). Quella del repository usa `mind/.venv` (il default di uv), come sempre.

### 3.2 Cosa vede il processo figlio

`uv run --frozen astra-mind` (gli stessi argomenti di prima) nella cartella della mente, nascosto e staccato (`CreateProc(..., detached, hidden, reallyhidden)`:
su Windows `CREATE_NO_WINDOW`, su Mac/Linux `stdin/stdout/stderr` su `/dev/null` e un gruppo di processi suo), con queste variabili in più rispetto a quelle del gioco
(impostate un istante e **restituite** subito dopo: l'ambiente del gioco resta com'era):

| Variabile | Valore | Dove |
|---|---|---|
| `ASTRA_SAVED` | la cartella `Saved` del gioco (con la barra in fondo, come prima) | sempre |
| `ASTRA_MIND_LOG` | `Saved/Logs/astra-mind.log` (lo stesso file di prima) | sempre |
| `ASTRA_HOME`, `UV_PROJECT_ENVIRONMENT` | la cartella dei dati; `<dati>/venv` | mente impacchettata |
| `PYTHONUTF8=1` | i file di testo sono UTF-8 qualunque sia la tabella dei caratteri della console | Windows e Linux (sul Mac è già così) |
| `HF_HUB_DISABLE_SYMLINKS_WARNING=1` | niente avviso sui collegamenti | Windows |
| `PATH` | quello del gioco + le cartelle degli strumenti che mancano (Homebrew, `~/.local/bin`, …) | quando manca qualcosa |

### 3.3 Cosa succede se qualcosa manca o si ferma

- uv o la cartella della mente non si trovano: errore nel log del gioco (`[Mind] launched astra-mind (FAILED): …`) e una scritta a schermo che dice cosa cercare.
- Prima partita su una macchina senza ambiente Python: una scritta avvisa che le menti si stanno installando (minuti, serve la rete); il gioco va avanti.
- Se la mente che il gioco ha avviato si ferma (nessuna chiave, una libreria che non carica, un guasto): `[Mind] the mind stopped (exit code N)` nel log del gioco e a schermo, con il percorso del
  suo log (su Windows anche «Setup-ASTRA.bat shows what went wrong»); se intanto un'altra mente serve il gioco (una lasciata da una sessione precedente: la nuova ha trovato la porta presa) non si dice nulla.
- Il gioco scrive **una sua riga** nel log della mente (`2026-10-04 05:26:58,207 astra.game starting the mind: …`, e `… the mind failed: its process exited with code N …` se si ferma): uv può cadere
  prima che Python scriva qualcosa (niente rete al primo avvio, un lock rifiutato) e la storia sta così in un posto solo. Sullo stesso formato dei messaggi della mente (`tools/soak.py` li legge uguali).
- Chiudere il gioco impacchettato termina la mente e i suoi figli (`TerminateProc(..., KillTree=true)`: su Windows percorre l'albero dei processi). Se il gioco cade, la mente
  resta ma si ferma da sola dopo 20 minuti senza nessuno (`idle_exit`).

### 3.4 Cosa cambia sul Mac, e cosa no

Uguale: gli argomenti, la cartella di lavoro, `ASTRA_SAVED`, `ASTRA_HOME`, `UV_PROJECT_ENVIRONMENT`, la cartella dei dati, il file di log, la durata di vita della mente, l'app nel
suo bundle. **Diverso**: (1) niente shell di login: il PATH del figlio è quello del gioco più le cartelle note, non quello che il profilo dell'utente costruiva (Python.framework, nvm, …:
alla mente servono `uv`, `whisperkit-cli` e `say`, che stanno in `/opt/homebrew/bin`, `~/.local/bin` e `/usr/bin`); (2) in più `ASTRA_MIND_LOG`; (3) una scritta se il Mac non ha uv; (4) le righe `astra.game` del gioco nel log della mente.

## 4. La mente su Windows

### 4.1 Ambiente e dipendenze
`uv sync --frozen` su Windows installa Python 3.13 (uv lo scarica), PyTorch per CPU (Pocket TTS), `onnxruntime`, `sherpa-onnx`, `faster-whisper` e il resto: circa 2,5 GB. Servono il
**Microsoft Visual C++ Redistributable 2015-2022 x64** (PyTorch e ONNX Runtime): lo installa anche il programma dei prerequisiti di Unreal (il pacchetto si fa con `-prereqs`).
`firstrun` prova a caricare `torch` e `onnxruntime` e, se fallisce, lo dice con il collegamento ufficiale.

### 4.2 Ascolto
Sul Mac l'helper Swift con Parakeet sul Neural Engine (25 lingue europee, mediana 67 ms); altrove `SherpaParakeetBackend` (Parakeet TDT 0.6B v3 int8, ONNX su CPU: 0,10 s su una frase corta qui) e
`FasterWhisperBackend` (`small`, 1,7 s) come riserva per le lingue non europee e per le frasi incerte. Scelta in `stt.default_backends()`; `ASTRA_STT` = il nome di un motore (provato per
primo), `portable` (solo i portabili) oppure `off` (nessuno). Il modello Parakeet ONNX (circa 490 MB da scaricare, 670 MB su disco, da `github.com/k2-fsa/sherpa-onnx`) si scarica da solo alla prima
partita dove non c'è l'helper (`ASTRA_STT_FETCH=1`/`0` forza); faster-whisper scarica il suo da Hugging Face alla prima frase che lo chiede. Limite già noto del percorso portabile
([protocollo_voce.md](protocollo_voce.md) §9): Parakeet ONNX non dà una confidenza confrontabile, quindi il passaggio automatico a Whisper per una lingua non europea alla prima frase non c'è:
si fissa la lingua del Capitano (`captain_lang.txt`) e da lì le frasi vanno a Whisper.

### 4.3 Voce
Pocket TTS (CPU) è uguale su tutti i sistemi. Le lingue che non conosce (giapponese, russo, …) e le sette lingue **finché il loro modello non è scaricato** (440 MB l'una, in
background) le dicono le voci del sistema: macOS `say`; Windows SAPI tramite PowerShell (`System.Speech`): le voci installate scelte per lingua e sesso, l'elenco compilato in
background all'avvio, il testo passato in una variabile d'ambiente e lo script in `-EncodedCommand` (nessun testo diventa mai parte di una riga di comando). Una riga costa un secondo
o due (un PowerShell da avviare): è un ripiego, non la voce del gioco. Su Linux nessuna voce di sistema: una lingua senza Pocket TTS va al modello inglese, o è dichiarata non
producibile se la scrittura non è latina (come sempre).

### 4.4 Il resto
- **Log**: `host.redirect_output_to_log` (descrittori 1 e 2 sul file, anche per PortAudio/ONNX/torch; `faulthandler`; se supera 20 MB viene messo da parte come `.1`) è chiamato da `astra_mind/__init__.py`:
  prima di qualunque importazione pesante, così anche una libreria che non carica dice perché. Senza `ASTRA_MIND_LOG` (la mente avviata a mano, i banchi) non cambia nulla.
- **Segnali**: terminare il processo (come fa il gioco) non manda segnali su Windows: la mente non tiene nulla che ne dipenda (i salvataggi sono scritture atomiche, file temporaneo e `os.replace`: un processo ucciso di colpo non lascia file a metà).
- **Microfono**: `sounddevice` apre il predefinito; Windows 10/11 chiede *Impostazioni → Privacy e sicurezza → Microfono → "Consenti alle app desktop di accedere al microfono"*: se è spento la mente
  dice `mic: unavailable` e il gioco lo scrive a schermo con il percorso delle impostazioni. Un auricolare Bluetooth passa al profilo telefonico quando si apre l'ingresso (anche su Windows): si
  usa il microfono del portatile come sul Mac.
- **Firewall**: la mente ascolta solo su `127.0.0.1`: Windows Defender Firewall non chiede nulla.

### 4.5 Tutte le variabili d'ambiente
| Variabile | Chi la legge | Effetto |
|---|---|---|
| `ASTRA_MIND_DIR`, `ASTRA_UV`, `ASTRA_HOME` | il gioco | dove sta la mente, quale uv, dove stanno i dati (§3.1) |
| `ASTRA_MIND_PORT` | gioco e mente | la porta (default 8765, accettate 1024-65535) |
| `ASTRA_MIND_LOG` | la mente (l'imposta il gioco) | il file di log; senza, la mente tiene il suo terminale |
| `ASTRA_SAVED` | la mente (l'imposta il gioco) | dove sta la campagna |
| `ASTRA_STT` | la mente | `parakeet`, `parakeet-onnx`, `whisperkit`, `faster-whisper` (primo), `portable`, `off` |
| `ASTRA_STT_FETCH` | la mente | `1`/`0`: scarica da sola (o no) un modello di ascolto mancante (default: sì dove non c'è l'helper) |
| `ASTRA_STT_MODEL`, `ASTRA_SHERPA_MODEL`, `ASTRA_FW_MODEL`, `ASTRA_VOICE_MODELS`, `ASTRA_STT_BIN` | la mente | modello dell'helper, cartella del modello ONNX, modello di faster-whisper, radice dei modelli, percorso dell'helper |
| `ASTRA_TTS_WARM` | la mente | `0`: nessuna voce caricata in anticipo (prove) |
| `ASTRA_MIC` | la mente | `auto`, `always`, `ptt`, `off` (come prima) |

## 5. Grafica, impostazioni e finestra

- **TSR** è il metodo di antialiasing del progetto (`r.AntiAliasingMethod=4` in `DefaultEngine.ini`): su Windows non c'è altro in gioco, e il plugin MetalFX non viene né compilato né caricato.
- **La pagina SETTINGS** mostra GRAPHICS, IMAGE, FRAME RATE, MUSIC, VOICES, SUBTITLES e BACK; la riga RETINA (e `r.SecondaryScreenPercentage.GameViewport`) esiste solo sul Mac. IMAGE e FRAME RATE
  lavorano sulla risoluzione dinamica, che `Config/Windows/WindowsEngine.ini` accende (`r.DynamicRes.OperationMode=2`).
- **Alta risoluzione (DPI)**: il motore, per un gioco non "high-DPI aware", fa disegnare la finestra alla risoluzione logica e la fa ingrandire da Windows: su uno schermo scalato al 150 % l'immagine è un po'
  morbida ma costa meno. `bAllowHighDPIInGameMode=False` resta il default (scritto in `WindowsEngine.ini`). Per i pixel veri: `True`, e va aggiunta una riga alla pagina SETTINGS per l'uscita a metà
  risoluzione (il RETINA del Mac). **Decisione da prendere guardando un portatile 4K.**
- **Finestra**: `WindowsGameUserSettings.ini` parte a schermo intero senza bordi (`FullscreenMode=1`); il `Version` resta quello del file di base.
- **Dove salva il gioco**: per un pacchetto non "installato" `Saved` sta accanto al gioco (`Windows\ASTRA\Saved`): la cartella deve essere scrivibile (non Program Files) oppure si avvia con `-SaveToUserDir`
  (`%LOCALAPPDATA%\ASTRA\Saved`).
- **Requisiti**: RHI DX12 con Shader Model 6 (`DefaultGraphicsRHI_DX12`, `PCD3D_SM6`: Nanite, Lumen, VSM), Windows 10 o 11, GPU con 8 GB o più (`docs/ricerca/01`).

## 6. Il giorno del PC Windows: il pacchetto

### 6.1 Cosa serve sul PC
- Windows 10 21H2 o 11, 32 GB di RAM consigliati, una GPU DX12 con 8 GB, 150 GB liberi (repository con LFS + intermedi + pacchetto), in un disco **veloce**.
- **Unreal Engine 5.8.3** dall'Epic Games Launcher (la stessa versione del Mac), con il componente "Visual Studio" se lo chiede.
- **Visual Studio 2022 17.14** (MSVC 14.44.35207 o successivo) **oppure Visual Studio 2026 18.0** (MSVC 14.50.35723 o successivo: le precedenti 14.50 hanno errori interni del compilatore): carico di lavoro
  *Sviluppo di giochi con C++* (`Microsoft.VisualStudio.Workload.NativeGame`), SDK di Windows 11 `10.0.22621.0`, .NET Framework 4.6.2 targeting pack. L'elenco esatto sta in
  `Engine/Config/Windows/Windows_SDK.json` dell'installazione di Unreal. Le versioni vietate (17.9, 17.10…) fanno compilare codice che si schianta: non usarle.
- **Git** e **Git LFS** (il repository tiene i contenuti pesanti in LFS: `git lfs pull`), **uv** (`winget install --id astral-sh.uv -e`: finisce in `%LOCALAPPDATA%\Microsoft\WinGet\Links`, o l'installatore ufficiale in `%USERPROFILE%\.local\bin`).
- Clonare in un percorso **corto** (`C:\ASTRA`): i percorsi dei contenuti sono lunghi e Windows ferma i 260 caratteri (se serve, abilitare i percorsi lunghi è una scelta del PC, non di questo progetto).

### 6.2 Passi (in ordine)
1. `git clone` del repository in `C:\ASTRA`, poi `git lfs pull`; sul ramo che include `worktree-agent-a77d0ce415fad4f4a` (o `main` dopo l'unione).
2. Prima di compilare, i controlli che non servono Unreal: `python tools\portability.py` (zero risultati attesi), `python tools\portability.py --lock` (se c'è uv).
3. **Compilare l'editor**: `"C:\Program Files\Epic Games\UE_5.8\Engine\Build\BatchFiles\Build.bat" ASTRAEditor Win64 Development -Project="C:\ASTRA\ASTRA.uproject" -WaitMutex`.
   Qui arriveranno gli errori MSVC (§6.4): sono il lavoro vero della giornata. Poi `ASTRA Win64 Development` (il gioco).
4. Prova senza grafica, come sul Mac: `"C:\Program Files\Epic Games\UE_5.8\Engine\Binaries\Win64\UnrealEditor-Cmd.exe" C:\ASTRA\ASTRA.uproject -run=AstraMindLaunch -launch=dev -nullrhi -unattended -nosound -nopause` (e `-launch=packaged`): avvia la mente vera
   con la stessa funzione del gioco, la raggiunge con un client WebSocket, la ferma. Prima serve la mente: `cd mind && uv sync --frozen`.
5. **Il pacchetto**: `powershell -NoProfile -ExecutionPolicy Bypass -File tools\windows\Pacchetto-Windows.ps1` (opzioni `-Config Shipping`, `-Zip`, `-SoloMente`). Fa `RunUAT BuildCookRun -platform=Win64 … -prereqs`,
   poi mette in `Packaged\Windows\` la mente (`mind\`: sorgenti, `uv.lock`, **non** l'helper del Mac), un `uv.exe` in `mind\bin\`, `Setup-ASTRA.ps1`/`.bat` e un `README-WINDOWS.txt`. La cottura degli shader
   la prima volta dura ore. Se `UAT` fallisce: `Saved\Logs\package_last_windows.log`.
6. Sul PC di prova (il proprio o un altro): copiare `Packaged\Windows` in una cartella scrivibile e lanciare **`Setup-ASTRA.bat`** una volta (rete accesa; `-EnvFile C:\percorso\.env` per la chiave
   delle menti, che finisce in `%LOCALAPPDATA%\ASTRA\.env`, o nella cartella di `ASTRA_HOME` se c'è, e non viene mai stampata). Poi `ASTRA.exe`.

### 6.3 Cosa guardare nella prima partita
1. Finestra a schermo intero senza bordi alla risoluzione del desktop; la pagina SETTINGS senza RETINA; il gioco a 60 fps (o la risoluzione dinamica che scende).
2. `Saved\Logs\ASTRA.log` (Development): `[Mind] starting the mind from …`, `[Mind] launched astra-mind (ok): …`, poi `[Mind] connected` entro pochi secondi (la prima volta senza ambiente: minuti).
3. `Saved\Logs\astra-mind.log`: `astra-mind listening on ws://127.0.0.1:8765`, i motori (`parakeet-onnx`, `faster-whisper`), i modelli delle voci in caricamento, `game connected`.
4. Il microfono: premere il tasto di parola e dire un ordine: `STT … [en] …` nel log della mente. Se il microfono è negato: la scritta a schermo e `Impostazioni → Privacy → Microfono`.
5. Le voci: l'equipaggio parla (le battute passano dal gioco, `UAstraVoiceWave`); nei primi minuti, finché i modelli non sono scaricati, parlano le voci SAPI (se il PC ha una voce per la lingua).
6. Chiudere il gioco: i processi `uv.exe`/`python.exe` della mente spariscono dal Task Manager (se non spariscono: la mente si ferma da sola dopo 20 minuti; `tools\windows\Stop-Mind.ps1` la ferma subito, come il `pkill -f astra-mind` di `ricompila.sh`).
7. Con `tools/play.py launch --app C:\...\Windows` (variabile `UE_ROOT` per il motore) si gioca da terminale come sul Mac.

### 6.4 Problemi probabili e dove guardare
| Sintomo | Probabile causa | Dove / cosa fare |
|---|---|---|
| errori `C2…`, `C4…` o `error LNK` nei file di `Source/ASTRA` | codice mai compilato con MSVC (macro di Windows come `min`/`max`/`GetObject`/`SendMessage` che entrano in conflitto con nomi nostri, conversioni implicite, intestazioni mancanti, `-Wshadow` che sui blocchi di unità può dare errori) | correggere caso per caso; `-DisableUnity` isola un file alla volta (provato sul Mac: compila) |
| `uv non trovato` a schermo | né `mind\bin\uv.exe` né uv nel PATH | rilanciare il pacchetto con `-Uv`, o `winget install --id astral-sh.uv -e`, o `ASTRA_UV` |
| `the mind stopped (exit code 1)` poco dopo l'avvio | niente chiave (`RuntimeError: Chiave mancante nel .env`) o una libreria che non carica | `astra-mind.log`; `Setup-ASTRA.bat` ricontrolla tutto |
| `OSError: [WinError 126]` / `DLL load failed` in torch o onnxruntime | manca il Visual C++ Redistributable | `Engine\Extras\Redist\en-us\UEPrereqSetup_x64.exe` nel pacchetto (lo mette `-prereqs`), o `https://aka.ms/vs/17/release/vc_redist.x64.exe` |
| la mente non si connette, nessun errore | la porta 8765 è riservata o presa | variabile di sistema `ASTRA_MIND_PORT=18765` (vale per gioco e mente) |
| `uv sync` fallisce | rete assente o filtrata; antivirus che mette in quarantena `uv.exe`/`python.exe` | rilanciare `Setup-ASTRA.bat`: ciò che è scaricato resta; escludere la cartella di `%LOCALAPPDATA%\ASTRA` dall'antivirus |
| `Setup-ASTRA.ps1` "l'esecuzione di script è disabilitata" | criterio di esecuzione di PowerShell | usare `Setup-ASTRA.bat` (passa `-ExecutionPolicy Bypass` per quella sola esecuzione: non cambia nessuna impostazione del sistema) |
| il gioco cuoce con "path too long" | repository in un percorso lungo | clonare in `C:\ASTRA` |
| `uv sync` si ferma con un percorso troppo lungo dentro `%LOCALAPPDATA%\ASTRA\venv` | un profilo utente dal nome lungo più le cartelle profonde dei pacchetti Python | variabile di sistema `ASTRA_HOME=C:\ASTRA-data` (la leggono il gioco, la mente e `Setup-ASTRA.bat`, e il venv nasce lì) |
| il gioco salva in un posto in cui non può scrivere | pacchetto sotto Program Files | una cartella scrivibile, o `-SaveToUserDir` |
| voce robotica per una lingua di Pocket TTS | il modello non è ancora scaricato: parla SAPI | attendere (o `Setup-ASTRA.bat -Langs en,it`) |

## 7. Come l'ho verificato (sul Mac) e cosa no

### 7.1 Comandi (si ripetono tutti)
```
# gioco: logica per sistema + lancio vero (serve l'editor compilato per questo checkout)
UnrealEditor-Cmd ASTRA.uproject -run=AstraMindLaunch [-probe] [-launch=dev|packaged] -nullrhi -unattended -nosound -nopause
Engine/Build/BatchFiles/Mac/Build.sh ASTRAEditor Mac Development -Project="$PWD/ASTRA.uproject" -WaitMutex [-DisableUnity | -DisableAdaptiveUnity]

# mente
cd mind && .venv/bin/python -m unittest bench.portable_unit -v                     # 35 prove, senza rete né modelli
ASTRA_TEST_BOOT=1 .venv/bin/python -m unittest bench.portable_unit.TestBoot          # la mente vera su una porta libera
ASTRA_TEST_PORTABLE_REAL=1 ASTRA_VOICE_MODELS=<cartella> .venv/bin/python -m unittest bench.portable_unit.TestPortableEngines   # Pocket TTS parla, i motori di Windows ascoltano
.venv/bin/python -m unittest discover -s bench -t . -p "*_unit.py"                  # 549 prove della mente
.venv/bin/python -m astra_mind.firstrun --check                                      # lo sguardo alla macchina

# progetto
python tools/portability.py [--allowed] [--lock] [--selftest]
```

### 7.2 Risultati (4/10/2026, MacBook Air M4)
- Compilazione dell'editor: pulita (nessun avviso nei miei file), anche con `-DisableUnity` (ogni file da solo) e `-DisableAdaptiveUnity` (tutti nei blocchi).
- `AstraMindLaunch`: **78/78** con `-probe -launch=dev` e **73/73** con `-launch=packaged`: 61 controlli di logica con macchine inventate (checkout Mac, app Mac, pacchetto Windows, checkout Windows, Linux, uv in ognuno dei suoi posti, PATH nella forma di
  ciascun sistema, maiuscole e minuscole, variabili che cambiano mente/uv/dati, la porta), la macchina vera, `-probe` (un vero `CreateProc` che scrive il suo ambiente e il controllo che l'ambiente del gioco
  sia tornato com'era), `-launch=dev` (la mente vera dal venv del repository: il client WebSocket del gioco si connette dopo 4 s, la mente scrive "game connected" nel suo log, `TerminateProc` la ferma) e
  `-launch=packaged` (una copia della mente in un finto `ASTRA.app/Contents/Resources/mind`, dati propri, uv crea il venv nuovo in 20 s, stessi controlli).
- `bench.portable_unit` 35 prove OK (porta, log da processi veri con scritture native e tetto, segnali con e senza SIGHUP, scelta dei motori su macchine Windows/Mac Intel/Apple Silicon finte, SAPI con un
  PowerShell finto, lock e pyproject d'accordo, ruote di Windows, controllo di portabilità, caricamento nativo); 549 prove `*_unit` e 82 prove `*_server` della mente: tutte OK.
- Motori portabili **veri**, forzati con `ASTRA_STT=portable`: la frase «Helm, come to heading two one seven and full ahead.» fatta da Pocket TTS → `parakeet-onnx`: «Helm. Come to heading 217 and full ahead.» in
  0,10 s; `faster-whisper`: «Come to heading 217 and full ahead.» in 1,69 s.
- Gli script PowerShell: analizzati con il parser di PowerShell 7.6 (nessun errore, nessuna sintassi che la 5.1 non legga, solo ASCII), `Setup-ASTRA.ps1` eseguito contro un pacchetto finto con un `uv.exe`
  finto e variabili d'ambiente di Windows (cartella dei dati, chiave copiata e mai stampata, `uv sync --frozen` e `uv run … firstrun` chiamati nella cartella giusta con l'ambiente giusto, uscite di
  errore), e la ricerca dei processi di `play.py` (la riga di PowerShell si analizza).

### 7.3 Non verificabile senza un PC Windows
La compilazione MSVC; `CreateProcess`/`SetEnvironmentVariable` veri (letto `WindowsPlatformProcess.cpp` del motore: `detached`+`reallyhidden` = `CREATE_NO_WINDOW`, l'ambiente si eredita, la cartella di lavoro è
rispettata, `TerminateProc(KillTree)` percorre l'albero); PowerShell 5.1 vero e le voci SAPI; l'installazione vera di uv e delle ruote; DWM, la modalità finestra e il DPI; il microfono e
WASAPI; l'antivirus. Tutto ciò sta nell'elenco della prima giornata (§6.3-6.4).

Di MSVC si sa però che cosa è un **errore** in questo progetto (`DefaultBuildSettings = V7`, letto in `CppCompileWarnings.cs` del motore): ombre di variabili (C4456-C4459: la scansione `-Wshadow` di clang
le prende tutte, e l'ho fatta passare anche sui blocchi di unità), macro non definita in un `#if` (C4668: i miei `#if` usano solo macro del motore), tipo di ritorno mancante (C4715) e codice
irraggiungibile (C4702). Quest'ultimo è il rischio vero: MSVC può segnalare come irraggiungibile il ramo morto di un `if` su una costante di compilazione (il motore stesso lo silenzia in più punti con
`PRAGMA_DISABLE_UNREACHABLE_CODE_WARNINGS`), clang no. Ho tolto quei rami dal mio codice (le impostazioni e il comando di prova
sceglievano con `constexpr bool bMac = PLATFORM_MAC`: ora scelgono il preprocessore) e la regola `constant-condition` di `tools/portability.py` li cerca (§8). Se il primo giro MSVC protesta ancora per
C4702 in un file, si isola con `#pragma warning(disable: 4702)` (`PRAGMA_DISABLE_UNREACHABLE_CODE_WARNINGS` del motore) intorno a quel punto, o `if constexpr`.

## 8. Il controllo di portabilità (`tools/portability.py`)

Gira ovunque con il solo Python, in due secondi, e segnala il codice solo-Mac (o ostile a Windows) **nuovo** in `Source/`, `Plugins/` e `mind/`; le eccezioni volute sono dichiarate.

| Regola | Segnala |
|---|---|
| `mac-path`, `shell`, `mac-tool`, `mac-say`, `mac-framework*` | cartelle del Mac nel codice, shell e programmi che hanno solo Mac o POSIX (`zsh`, `osascript`, `pgrep`, `say`), framework Apple |
| `platform-macro`, `darwin-check` | `PLATFORM_MAC`/`Darwin`: ogni ramo Mac deve nominare la sua alternativa in un commento `portable-ok: …` |
| `posix-only`, `rename`, `tmp-path`, `env-home` | `SIGHUP`, `add_signal_handler`, `fork`, `fcntl`…; `os.rename`; `/tmp`, `/dev/null`; `$HOME` |
| `locale-text-io` | `open()`/`read_text()`/`write_text()` di testo senza `encoding=`, e `subprocess` con `text=True` senza `encoding=` (Windows legge in cp1252; provato anche forzando una codifica ASCII sulle 549 prove della mente: tutte passano) |
| `posix-header`, `gcc-only`, `include-case` | intestazioni POSIX, costrutti solo GCC/clang, `#include` con le maiuscole sbagliate (Linux) |
| `constant-condition` | un `if` (o `?:`, `&&`, `\|\|`) su una costante di compilazione (`PLATFORM_*`, `WITH_*`, `UE_BUILD_*`, `ThisHost()`): per MSVC il ramo che non può girare può essere codice irraggiungibile (C4702), che con `BuildSettingsVersion.V7` è un **errore**; clang non lo dice e il Mac non lo mostrerebbe mai. Si sceglie con `#if`, con `if constexpr` o con un valore che il compilatore non può calcolare in anticipo |
| `structure` | un plugin solo-Mac deve essere `PlatformAllowList: ["Mac"]` nel `.uproject` e nel `.uplugin` e nessun file di gioco può includerlo |
| `config-parity` | ogni impostazione di `MacEngine.ini` ha il suo gemello in `WindowsEngine.ini`, o è dichiarata solo-Mac (`MAC_ONLY_ENGINE_KEYS`) |
| `--lock` | ogni pacchetto del `uv.lock` si installa per Windows x64 (CPython 3.13) senza compilare |

Commenti e docstring non sono codice. Un punto voluto porta `portable-ok: perché` su quella riga o sulla precedente; cartelle intere solo-Mac (il plugin MetalFX, l'helper Swift) stanno in `ALLOW_PATHS`
nello script, con il motivo. `--selftest` prova le regole contro esempi che devono e non devono prendere (e le strutture contro alberi finti). Oggi: **0 risultati non ammessi**, 274 ammessi (quasi tutti il
plugin e l'helper). Gira anche da `bench.portable_unit`.

## 9. Dopo la prima partita: decisioni e tarature
- `Config/Windows/WindowsEngine.ini`: tutti i valori sono quelli dell'Air; un PC con una RTX alza i pavimenti e le qualità (Lumen, ombre) e può togliere il compromesso di `r.Lumen.Reflections.MaxRoughnessToTrace`.
- `bAllowHighDPIInGameMode` (§5) e una riga SETTINGS per l'uscita a metà risoluzione.
- `t.IdleWhenNotForeground` su Windows (un gioco in secondo piano che si ferma: voluto?).
- `tools/war.py`, `tools/space.py`, `tools/soak.py`: stesso `UE_ROOT` e la ricerca dei processi senza `pgrep` (una riga ciascuno, come in `damage.py`/`play.py`).
- Windows su ARM: non è un obiettivo (`ctranslate2` non ha la ruota per `win_arm64`, e nel lock la ruota di PyTorch per Windows c'è solo per x64).
- Voci di sistema di Linux (`espeak-ng`) se mai servisse Linux.
