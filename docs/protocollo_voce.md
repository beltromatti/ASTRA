# Protocollo della voce (versione 2) e cosa deve fare il gioco

*Per chi scrive il C++ del gioco (`AstraMindSubsystem`, `AstraCrewMember`, `ASTRAPlayerController`, `AstraMusicSubsystem`). Il lato Python è già fatto (`mind/astra_mind/speech.py`, `tts.py`, `stt.py`, `audio_in.py`); qui c'è tutto ciò che il gioco deve sapere e fare, e la diagnosi dei difetti che il giocatore ha segnalato.*

Il protocollo è **additivo**: un gioco che non cambia nulla continua a funzionare, e alcune cose migliorano già da sole (sezione 1). Le cose nuove il gioco le riconosce dal campo `voice: 2` nel messaggio `status` che la mente manda a ogni connessione.

## 0. Sintesi: cosa è emerso e cosa serve al gioco

| # | Sintomo del giocatore | Causa | Dove si corregge |
|---|---|---|---|
| 1 | «il testo compare e nessuno parla» | **`BeginChannelLine` non riproduce mai nulla**: `UGameplayStatics::CreateSound2D(World, nullptr, …)` restituisce `nullptr` quando il suono è nullo (sorgente del motore 5.8, `GameplayStatics.cpp:1653`: `if (!Sound || …) return nullptr;`), quindi `ChannelAudio` è sempre nullo e la funzione esce senza suonare. Tutte le voci che non sono di un ufficiale «vicino» passano di lì: comandanti nemici, ammiraglio, regista, controllo del porto, soccorritori e giudici, e ogni ufficiale a più di 25 m (il Capo macchine e la dottoressa dalla plancia, chiunque quando il Capitano è al ponte di volo) | **gioco** (sezione 4.1) |
| 2 | «il testo lampeggia» / sparisce prima della voce | il gioco toglie il sottotitolo 2,5 s dopo `audio_end`, ma la mente mandava `audio_end` quando aveva *finito di inviare* l'audio (6–9× il tempo reale), non quando era finito di suonare: una riga di 8 s restava a schermo circa 3,8 s | **già risolto dalla mente** (l'audio ora va a passo e `audio_end` arriva alla fine dell'ascolto); regola nuova per il gioco nella sezione 3.1 |
| 3 | «il volume cala moltissimo senza motivo» | (a) **le dieci voci uscivano con volumi diversi di 12,8 dB** (misurato: da −18,5 LUFS Nair a −31,3 LUFS Okonkwo, tutte molto basse); (b) la curva di attenuazione del gioco è lineare e ignora `dBAttenuationAtMax`; (c) il passaggio «vicino/radio» a 25 m avviene per riga, senza isteresi, e la radio ha un filtro passa-banda; (d) la musica si abbassa a pompa tra una riga e l'altra e può restare abbassata | (a) **già risolto dalla mente** (−19 LUFS in media per tutte le voci, σ 1,2 dB tra le righe contro 3,0 prima: `docs/bench/voce_2026-09-30.md` §5); (b)(c)(d) **gioco** (sezione 4.2–4.4) |
| 4 | «a volte smettono di parlare a caso» | una nuova riga dello stesso ufficiale rimpiazzava (`SetSound`) quella in corso se la stima della mente sul suo termine era ottimista; la mente si bloccava quando cambiava lingua (21 s per caricare il modello spagnolo, «controllando gli aggiornamenti» in rete); righe di rapporto scartate in silenzio | **già risolto dalla mente** (modelli in cache senza rete, pre-caricati; ogni scarto è dichiarato); il gioco deve obbedire a `cancel` (sezione 3.2) |
| 5 | «i miei ordini si perdono o hanno risposta molto dopo» | il riconoscimento durava 1,8–2,1 s a frase breve; la risposta aspettava in coda dietro la riga in corso (fino a 8 s) e dietro ogni turno di evento in volo | **già risolto dalla mente** (Parakeet sul Neural Engine, sessione incrementale, il tasto prende il palco) |
| 6 | «le risposte agli ordini scritti suonano 30–45 s dopo, dietro rapporti vecchi e un messaggio lungo del nemico» (test dal vivo del capo su `main`: i turni erano pronti in 0,9–1,5 s) | il `speech.py` di `main` è una coda FIFO: la risposta al Capitano aspetta come ogni altra riga; un rapporto sull'evento aspetta un ponte silenzioso e poi suona anche se la notizia ha 22 s; un messaggio del nemico di 20 s tiene il ponte fino alla fine. **Il gioco non riordina nulla**: `OnText` e `OnBinary` agiscono nell'ordine d'arrivo e `BeginLine` sostituisce l'audio di quell'ufficiale, non c'è coda nel gioco | **già risolto dalla mente** (sezione 5: la risposta passa prima di tutto e ferma la riga in corso, le notizie vecchie non si dicono, il messaggio lungo si interrompe e riprende, un avviso di pericolo non aspetta); `bench/voice_replay.py` rifà la sequenza del test attraverso il server vero |

L'unica correzione **indispensabile** al gioco è la 1 (senza, le voci esterne restano mute). Le altre si sentono già con il gioco com'è, e migliorano ancora se il gioco segue le sezioni 3 e 4.

**Elenco per il C++, in ordine di importanza**

1. `BeginChannelLine`: creare la `USoundWaveProcedural` prima e passarla a `CreateSound2D` (4.1). *Senza questo le voci esterne e lontane non si sentono mai.*
2. `audio_begin`: mostrare il sottotitolo con la regola `hold_s` (3.1); `audio_end`/`cancel` come in 3.1–3.2.
3. `cancel`: `FadeOut(fade_ms)`, svuotare la coda procedurale (`ResetAudio()`), fermare (3.2).
4. Mandare `voice_status` (`started`, `stalled`, `failed`, `finished`) (2.2).
5. Attenuazione delle voci di bordo con `NaturalSound` (4.2) e una decisione vicino/radio per ufficiale con isteresi 22/28 m (4.3); radio con `SetVolumeMultiplier(1.5)` (4.1).
6. Musica abbassata dal messaggio `floor`, non da `IsSpeaking()` (4.4).
7. (Facoltativo) abbassare l'audio del gioco mentre il tasto della voce è premuto (3.3).

**Fatto nel gioco (30/9, lead): 1–6**, provati dal vivo in una battaglia intera (voci a bordo e via radio `started` in 20–70 ms e `finished` a fine ascolto, il comandante della Lethe e l'equipaggio dalla scialuppa via radio, il tasto che ferma la riga in corso). Come:
- `UAstraVoiceWave` (`Source/ASTRA/AstraVoiceWave.*`): la wave procedurale di una voce, che conta i byte messi in coda; `UAstraMindSubsystem` tiene per ogni riga in ascolto la wave, il punto in cui comincia e quanti byte ha ricevuto, e da lì manda `started` (i primi byte suonati), `stalled` (coda vuota per più di 250 ms prima di `audio_end`, una volta per riga), `failed` (nessuna componente, `Play()` non parte, o due secondi di audio arrivato senza che nulla suoni) e `finished` (coda svuotata dopo `audio_end`; poi la componente si ferma, così una voce finita non tiene occupato un canale audio del motore).
- Una riga che comincia mentre la precedente dello stesso ufficiale (o della radio) suona ancora si accoda sulla stessa wave: nessun `SetSound` su una voce che suona.
- Vicino o radio: per ufficiale, con isteresi 22/28 m, e radio anche quando un muro o una porta chiusa sta tra lui e il Capitano (lo stesso controllo del contesto `in_earshot`).
- Sottotitoli: `max(hold_s, audio_end + 1 s)`, finché la voce continua restano; `cancel` li sfuma in 0,35 s.
- Musica: abbassata a 0,55 quando `floor` non è `idle` (attacco 0,15 s, tenuta 0,5 s, rilascio 0,8 s); con una mente di protocollo 1, dalle voci degli ufficiali come prima.

**Trovato nella prova dal vivo (corretto nella mente)**: `PushToTalk.start()` apriva il microfono dentro il ciclo degli eventi; quando macOS non risponde (la richiesta del permesso del microfono in attesa) PortAudio resta fermo dentro CoreAudio e con lui **tutta la mente** (niente più voci né risposte, per minuti). Ora `PushToTalk.begin()` lo apre in un thread e aspetta al massimo 2 s (`OPEN_WAIT_S`): altrimenti quel tasto non registra, la mente continua, e il tasto successivo trova il microfono pronto. `ASTRA_MIC=off` fa premere il tasto senza aprire alcun dispositivo (per le prove).

## 1. Cosa cambia per il gioco così com'è (senza toccare il C++)

- `line` arriva **quando la voce parte** (prima arrivava all'accodamento): il gioco non lo mostra da nessuna parte (lo conserva e mostra il sottotitolo a `audio_begin`), quindi non c'è più un sottotitolo per una riga che poi viene scartata.
- L'audio è **a passo**: mai più di 0,45 s in anticipo sul tempo reale (prima arrivava tutto in un secondo). La coda procedurale del gioco resta corta, e `audio_end` arriva alla fine dell'ascolto.
- Una riga che la sintesi non riesce a produrre **non genera più sottotitolo** (prima: `audio_begin` + `audio_end` senza audio).
- Il volume di tutte le voci è lo stesso (−19 LUFS integrati in media, σ 1,2 dB tra le righe, picchi sotto −1,5 dBFS), le pause tra frasi sono accorciate (mai più di 0,3 s), e il parlato è più veloce del 12 % senza cambiare il timbro.
- Un messaggio che il gioco non conosce (`cancel`, `line_dropped`, `floor`) viene ignorato dal suo `OnText` (cade fuori dalla catena di `if`).

## 2. Messaggi

Tutti JSON in frame di testo, tranne l'audio (frame binario). Formato dell'audio invariato: `uint32 little-endian` con l'id della riga, poi PCM16 mono alla frequenza `rate`.

### 2.1 Mente → gioco

**`status`** (a ogni connessione): `{"type":"status","crew":{id: titolo,…},"rate":24000,"voice":2}`. `voice: 2` = questo protocollo. (Come prima può arrivare anche `{"type":"status","mic":"unavailable"}`.)

**`transcript`** (invariato): `{"type":"transcript","text":"…","lang":"it"}`. Arriva quando il testo del Capitano è pronto (≤ 0,4 s dal rilascio del tasto); `lang` è la lingua in cui parlava (l'equipaggio risponderà in quella). Va mostrato in cima come prima.

**`line`** — *una riga sta per essere ascoltata*. Il gioco la **conserva**, non la mostra ancora.

| campo | tipo | significato |
|---|---|---|
| `id` | int | identificatore della riga (unico nella sessione, cresce) |
| `speaker` | string | id di chi parla: stazione di plancia (`xo`, `helm`…), `chief`, `doctor`, `patientN`, `messN`, `mess_cook`, chiave di un personaggio (`solm`, `admiral`, `director`, `port_control`, `finder`, `captor`…) |
| `name` | string | nome da mostrare (il gioco ne prende il cognome) |
| `text` | string | il testo così com'è detto (dopo eventuale unione o accorciamento) |
| `lang` | string | lingua del testo |
| `tone` | string | `calm`, `focused`, `measured`, `cold`, `warm`, `furious`… (colora la resa; per ora solo la velocità) |
| `channel` | bool | `true` se non è un ufficiale a bordo (radio, nemico, ammiraglio…) |
| `priority` | string | `answer` · `urgent` · `normal` · `low` |
| `answer` | bool | è la risposta al Capitano |
| `addressed` | bool | è rivolta al Capitano (un ordine dell'ammiraglio alla Aquila, una chiamata che deve prendere): come una risposta, la mente non la perde mai (sezione 5bis) |
| `topic` | string\|null | argomento dichiarato dal produttore |
| `est_s` | float | durata prevista dell'audio, in secondi |
| `hold_s` | float | quanto deve restare a schermo il sottotitolo (regola in 3.1) |
| `rate` | int | frequenza del PCM che segue |

**`audio_begin`**: `{"type":"audio_begin","line":12,"speaker":"helm","rate":24000,"est_s":3.4,"hold_s":4.5}`. Segue `line` di pochi millisecondi. **Qui** il gioco mostra il sottotitolo e avvia la voce (`BeginLine` / `BeginChannelLine`).

**audio**: frame binari `uint32 id` + PCM16, blocchi da ~80 ms, **a passo** (il primo mezzo secondo subito, poi al ritmo di ascolto).

**`audio_end`**: `{"type":"audio_end","line":12,"dur_s":3.31,"reason":"done"}`. È inviato **alla fine prevista dell'ascolto** (non quando finisce l'invio). `reason`: `done` (finita) o `cut` (interrotta: è preceduta da un `cancel`).

**`cancel`** — *ferma questa riga adesso*: `{"type":"cancel","line":12,"reason":"captain","fade_ms":140}`. `reason` ∈ `captain` (il Capitano ha preso la parola), `answer_first` (arriva la risposta al Capitano), `urgent_first` (arriva un avviso di pericolo), `new_session`, `no_listener`, `cleared`. `fade_ms`: 40 se la mente ha trovato una pausa entro mezzo secondo (si ferma in una pausa), 140 se ferma a metà parola.

**`line_dropped`** — *informativo*: una riga accodata che non verrà mai detta: `{"type":"line_dropped","id":13,"speaker":"sensors","text":"…","reason":"expired"}`. `reason` ∈ `captain_spoke` (chiacchiera scartata quando il Capitano parla), `superseded` (una riga più recente sullo stesso argomento, o il resto di un messaggio interrotto il cui autore ha risposto al Capitano), `expired` (troppo tempo in coda, o un rapporto su una notizia ormai vecchia), `stale`, `overflow`, `synth_failed`, `synth_timeout`, `no_audio` (solo punteggiatura: la voce non fa alcun suono), `no_listener`, `empty`, `merged_into_<id>` (unita a un'altra riga: il suo testo è dentro quella), `new_session`, `cleared`. Il gioco non deve fare nulla (non ne ha mai visto il `line`); può scriverlo nel log.

**`floor`** — chi ha la parola: `{"type":"floor","state":"idle|crew|captain","line":12|null}`. `captain` da quando il Capitano preme il tasto (o manda un ordine scritto) finché la sua risposta non comincia; `crew` mentre una riga è in ascolto; `idle` altrimenti. Serve ad abbassare la musica (sezione 4.4) senza indovinare dal contenuto della coda audio.

**`notice`** — *una riga rivolta al Capitano la cui voce non si è riusciuta a fare*: `{"type":"notice","id":14,"speaker":"comms","name":"…","text":"…","lang":"it","tone":"…","channel":false,"priority":"answer","answer":true,"addressed":false,"hold_s":4.8,"why":"…"}`. La mente l'ha chiesta due volte alla sintesi (`SYNTH_RETRIES`) e non è venuta (macchina occupata, modello inciampato): il Capitano la **legge**. Il gioco la mostra come sottotitolo senza voce (`hold_s`, almeno 3 s) e la tiene nel registro delle comunicazioni; non arriva mai `line`/`audio_*` per quell'id. Non succede quasi mai: era il destino, il 5/10, di due risposte al Capitano e di un avviso (`synth_timeout`).

**`net_traffic`** — *una riga detta su una rete radio* (flotta, volo, marines), ascoltata o no dal Capitano: `{"type":"net_traffic","net":"fleet|flight|marines","console":"comms|flight|xo","speaker":"solm","name":"…","text":"…","lang":"it","urgent":false,"addressed":false,"aloud":false,"answer":false}`. **Non si voce mai da questo messaggio**: serve alla console e al taccuino (sezione 5ter). `aloud` = la riga è andata anche all'altoparlante del ponte (e arriva il suo `line`); `addressed` = è per il Capitano; `urgent` = chi parla dice «pericolo ora».

**`console_log`** — *una riga silenziosa sul registro di una console*: `{"type":"console_log","station":"xo|helm|ops|tactical|comms|sensors|engineering|flight","text":"…","kind":"routine|notice","by":"…"}`. La scrive un ufficiale con lo strumento `console_log`: la routine della sua console, che il Capitano legge sulla console o sul taccuino quando vuole e che nessuno dice a voce. `kind: notice` = una riga che l'ufficiale ha voluto far notare (il gioco la evidenzia).

**`net_speaker`** — *il Capitano ha messo una rete sull'altoparlante* (o l'ha tolta): `{"type":"net_speaker","net":"flight","on":true}`. Finché una rete è lì le sue voci si ascoltano com'erano prima delle reti (ogni riga con il suo `line`); la console lo mostra. Lo stato non si salva: a `hello` (nuova sessione) nessuna rete è sull'altoparlante.

### 2.2 Gioco → mente

- `ptt{down:bool}`, `player_text{text,lang?}`: **invariati** e sono i due modi in cui il Capitano prende la parola. La mente li tratta alla lettera: alla pressione del tasto (o all'arrivo del testo) chi parla si ferma entro mezzo secondo; il gioco **non** deve fare nulla per l'interruzione.
- **`voice_status`** (nuovo, *fortemente consigliato*): `{"type":"voice_status","line":12,"state":"started|stalled|failed|finished","detail":"…"}`. È l'unica prova che una voce sia stata davvero ascoltata: la mente lo registra (i `failed` e gli `stalled` sono avvisi nel log). Oggi il gioco non lo dice mai: per questo «il testo compare e nessuno parla» è rimasto invisibile per tutta la partita.
  - `started`: la componente audio ha cominciato a riprodurre la riga;
  - `stalled`: la coda procedurale è rimasta vuota più di 250 ms mentre la riga non era finita;
  - `failed`: non è stato possibile riprodurla (nessuna componente, nessun attore, `Play()` fallito);
  - `finished`: la coda si è svuotata dopo `audio_end`.

## 3. Regole per il gioco

### 3.1 Sottotitoli

1. Si mostrano a **`audio_begin`**, con il testo di `line`. Mai prima, mai al posto della voce.
2. Restano fino a **`max(t_audio_begin + hold_s, t_audio_end + 1,0 s)`**, con dissolvenza di 0,35 s. `hold_s = min(12, max(est_s + 1,0, 1,4 + caratteri / 17))`: dura quanto l'audio più un secondo, oppure quanto serve a leggerlo (17 caratteri al secondo più 1,4 s di attacco), il maggiore, al massimo 12 s. (Oggi: `EndAge + 2,5 s`, e `4 + 0,07 × caratteri` se non arriva `audio_end`.)
3. A **`cancel`** il sottotitolo di quella riga sfuma in 0,35 s (il testo non viene più detto). Una riga interrotta e poi ripetuta arriva con un id nuovo.
4. Al massimo tre righe, la più vecchia esce per prima (come ora).
5. Le parole del Capitano (`transcript`, ordine scritto) restano com'è.

### 3.2 Audio di una riga

1. A `audio_begin`: nuova `USoundWaveProcedural` (`SetSampleRate(rate)`, mono, `bLooping=false`), componente audio in `Play()`.
2. A ogni frame binario: `QueueAudio`. La coda non supera mai ~0,5 s (la mente va a passo: `LEAD_S = 0,45` in `speech.py`). Uno scatto del gioco più lungo di quello (un caricamento, la compilazione di uno shader) svuota la coda e la voce si interrompe per un attimo: la mente non può accorgersene da sola, lo sa solo se il gioco manda `voice_status: stalled` (che registra nel log come avviso). Se il gioco implementa `cancel` (punto 3) si può portare `LEAD_S` a 0,8 s per assorbire scatti più lunghi: l'unico costo è che un gioco che ignora `cancel` finirebbe la riga in corso fino a 0,8 s dopo.
3. **A `cancel`**: `Voice->FadeOut(fade_ms/1000, 0.f)`, poi `CurrentWave->ResetAudio()` e stop della componente; se la mente manda anche `audio_end{reason:"cut"}` va ignorato. Con un gioco che ignora `cancel` la voce finisce comunque entro 0,45 s (è quanto audio c'è in coda).
4. Non chiamare `SetSound` su una componente che sta ancora suonando la riga precedente: con il protocollo 2 due righe dello stesso ufficiale non si sovrappongono (l'audio di una finisce prima che parta l'altra), ma un `cancel` mancato la troncherebbe.
5. Mandare `voice_status` (sezione 2.2). In particolare **`failed` quando `Play()` non parte o il componente manca**.

### 3.3 Il Capitano parla (per l'interfaccia)

- Tasto giù: il gioco può abbassare del tutto (−12 dB, 0,15 s) il proprio audio finché il tasto è premuto e riportarlo su al rilascio (0,5 s): riduce quanto del gioco rientra nel microfono. Facoltativo; la mente comunque ferma le voci.
- `floor{state:"captain"}` è il momento giusto per un piccolo indicatore («ti sta ascoltando»).

## 4. Diagnosi e correzioni consigliate (C++)

### 4.1 Voci esterne e lontane: mute (causa certa)

`AstraMindSubsystem.cpp`, `BeginChannelLine`:

```cpp
ChannelAudio = UGameplayStatics::CreateSound2D(World, nullptr, 1.f, 1.f, 0.f, nullptr, true, false);   // nullptr: il motore ritorna nullptr
…
if (!ChannelAudio) { return; }        // ← esce sempre; ChannelLine non viene nemmeno impostato: anche l'audio in arrivo è scartato
```

`UGameplayStatics::CreateSound2D` comincia con `if (!Sound || !GEngine || !GEngine->UseSound()) return nullptr;` (5.8, `Private/GameplayStatics.cpp:1653`). Correzione: creare prima la wave e passarla.

```cpp
ChannelWave = NewObject<USoundWaveProcedural>(this);       // (vedi 3.2: una wave nuova per riga)
… SetSampleRate, NumChannels, SoundGroup …
if (!ChannelAudio || !IsValid(ChannelAudio))
{
    ChannelAudio = UGameplayStatics::CreateSound2D(World, ChannelWave, 1.f, 1.f, 0.f, nullptr, true, false);
    if (ChannelAudio) { /* filtri passa-banda, come ora */ }
}
else { ChannelAudio->SetSound(ChannelWave); }
if (!ChannelAudio) { SendVoiceStatus(LineId, "failed", "no audio component"); return; }
ChannelLine = LineId;
ChannelAudio->Play();
```

Chi passa da questo percorso (tutto silenzioso oggi): `solm`, `kade`, `vael`, `quill`, `hale` e ogni comandante nemico registrato, `admiral`, `director`, `port_control`, `finder`, `captor`, `board*`, e **ogni ufficiale con attore a più di 25 m** (il Capo `chief` in sala macchine e la dottoressa `doctor` in infermeria quando il Capitano è in plancia; tutti quando è al ponte di volo o su New Ravenna).

Il volume della radio: i filtri (passa-alto 320 Hz, passa-basso 3,6 kHz) tolgono in media 3,5 dB di sonorità sulle voci della mente (da 1,5 a 7 dB secondo la voce; misurato con filtri a 1, 2 e 4 poli, stesso risultato); compensarli con `SetVolumeMultiplier(1.5)` così la radio non suona più piano delle voci a bordo.

### 4.2 Attenuazione delle voci a bordo

`AstraCrewMember.cpp` (creazione dell'attenuazione, righe ~52–59) imposta `dBAttenuationAtMax = -18` ma lascia `DistanceAlgorithm` al valore di default (**Linear**, costruttore di `FBaseAttenuationSettings`), e con Linear `dBAttenuationAtMax` è ignorato (vale solo per `NaturalSound`, `Attenuation.h`). Risultato: piena fino a 3 m, poi ampiezza lineare fino a zero a 28 m: −3 dB a 10 m, −6 dB a 15 m, −10 dB a 20 m, −16 dB a 24 m. Un Capitano che cammina per la plancia sente le voci salire e scendere a ogni passo.

Impostazione consigliata (un ufficiale nella stessa stanza si sente sempre bene; il volume cala dolcemente e si ferma):

```cpp
Att->Attenuation.DistanceAlgorithm   = EAttenuationDistanceModel::NaturalSound;
Att->Attenuation.AttenuationShapeExtents = FVector(800.f);          // 8 m a volume pieno
Att->Attenuation.FalloffDistance     = 2200.f;
Att->Attenuation.dBAttenuationAtMax  = -8.f;                        // e da lì non scende più:
Att->Attenuation.FalloffMode         = ENaturalSoundFalloffMode::Hold;
```

### 4.3 «Vicino» o «radio»: una decisione per ufficiale, con isteresi

Oggi (`audio_begin`): `bNear = Dist(camera, attore) < 2500` valutato **a ogni riga**. Un Capitano fermo a 25 m sente lo stesso ufficiale ora piano nella stanza (−16 dB), ora in radio a volume pieno, riga per riga. Consiglio: stato per ufficiale (`bOnRadio`), si passa alla radio oltre **28 m** e si torna in stanza sotto **22 m**; mai a metà riga; la radio è sempre udibile (4.1).

### 4.4 Musica: abbassarla dal protocollo, non da `IsSpeaking()`

`AstraMusicSubsystem::Tick` abbassa a 0,55 quando un qualsiasi `AAstraCrewMember::IsSpeaking()` (`AvailableByteCount > 0`), risale con costante 1,2/s: tra due righe (pausa di 0,3 s) la musica risale un poco e ricade (pompa), e se una wave conserva byte non consumati (componente fermata, culling) `IsSpeaking()` resta vero e la musica **resta abbassata** finché quell'ufficiale non parla di nuovo. Le voci esterne (canale) non abbassano affatto la musica. Consigliato: duck = 0,55 quando `floor.state != "idle"` (ricevuto dalla mente), attacco 0,15 s, tenuta 0,5 s dopo il ritorno a `idle`, rilascio 0,8 s; azzerato su `cancel` e sulla chiusura della connessione.

### 4.5 Se dopo queste correzioni «nessuno parla» capita ancora

Ora `voice_status` lo dice: nel log della mente (`~/Library/Application Support/Epic/ASTRA/Saved/Logs/astra-mind.log`) compare `the game says line N is failed/stalled`. Le ipotesi da verificare, non provate: (a) troppi suoni attivi e la componente della voce esclusa dal motore (`AudioMaxChannels` di default 32; `stat sounds`); (b) `Play()` su una componente non attiva.

## 5. Il palco del parlato lato mente (per chi scrive produttori Python)

**Aggiornamento 30/9 sera (principio delle intelligenze, [ARCHITETTURA §1bis](ARCHITETTURA.md)).** Il palco non riscrive né scarta più per regola ciò che dicono le persone.
- **Battute dell'equipaggio.** Portano l'aggancio `rethink` (server `_crew_say` → `agent.rethink`). Quando arriva il loro turno dopo più di `RETHINK_AFTER_S` (8 s) di attesa, o dopo essere state interrotte, l'ufficiale le ripensa con lo stato di adesso: le dice aggiornate, le cambia o tace (`line_dropped{reason:"rethought"}`). Il ripensamento avviene una volta sola, quando la voce corrente sta per finire, e intanto il palco va avanti.
- **Voci dall'esterno.** Senza aggancio, la parte persa di un messaggio interrotto si ripete com'era, dalla frase interrotta: chi parla alla radio non ha smesso, è la plancia che ha dato la precedenza al Capitano.
- **Regole tolte.** Via il riassunto «prima e ultima frase», il taglio alla prima frase quando c'è coda e il salto dei turni di rapporto per notizie «troppo vecchie». Le notizie arrivano agli ufficiali con la loro età (`[happened N s ago]`) e sono loro a giudicare.
- **Meccanica che resta.** La priorità del Capitano, un oratore alla volta, la chiacchiera che tace quando il Capitano parla, lo scarto dichiarato delle righe senza aggancio.

`voice.say(speaker, text, lang, tone, *, priority=None, topic=None, expires_s=None, stale_if=None, answer=None)` — l'unica chiamata necessaria (le firme e gli attributi che il server usava prima continuano a funzionare: `busy_s()`, `busy_until`, `low_priority`, `drop_low_priority()`, `q.join()`, `first_audio`, `enqueued`).

| Priorità | Chi | Scadenza di default | Regola |
|---|---|---|---|
| `Prio.ANSWER` | risposta al Capitano (dentro `captain_turn_begin/end`, o `answer=True`) | 90 s | passa prima di tutto; ferma la riga in corso al prossimo respiro (≤ 0,5 s) |
| `Prio.URGENT` | pericolo ora (`voice.urgent = True` o `priority=`) | 25 s | ferma una riga normale con più di 1,5 s davanti |
| `Prio.NORMAL` | rapporti, eventi, comunicazioni | 60 s; **un rapporto (riga di un turno di evento) 18 s dopo la notizia** | in coda, nell'ordine; con oltre 14 s di parlato in attesa le righe lunghe (> 170 caratteri) si accorciano: una riga dell'equipaggio alla prima frase, un messaggio da fuori (nemico, ammiraglio) a come comincia e a ciò che chiede (prima e ultima frase) |
| `Prio.LOW` | chiacchiere (`voice.chatter = True`), avventori della mensa e pazienti | 15 s | scartate quando il Capitano prende la parola |

- **Il Capitano ha il palco.** `voice.captain_begin()` (tasto giù o ordine scritto): la riga in corso si ferma alla prossima pausa entro 0,5 s (`fade_ms` 40) o sfuma a metà parola (140 ms); nessuno comincia finché la sua risposta non parte (al massimo 8 s dopo il rilascio; `captain_end(False)` se non ha detto nulla lo rilascia subito); mentre il tasto è premuto non comincia nessuno, nemmeno la risposta tardiva a un ordine precedente (viene preparata intanto e parte al rilascio); per tutto il turno del Capitano (`captain_turn_begin` … `captain_turn_end`, al massimo 25 s) i rapporti aspettano, perché il modello scrive le righe dei vari ufficiali a uno o due secondi l'una dall'altra e un rapporto non deve partire nell'intervallo (per essere tagliato dalla riga dopo); le righe `LOW` in coda sono scartate (`captain_spoke`); quelle `NORMAL` e `URGENT` aspettano e, finita la risposta, parlano nell'ordine in cui erano. Una riga interrotta riprende dopo, dalla frase che era in corso (vedi sotto).
- **Ordine scritto e ordine a voce**: il tasto premuto ferma chiunque parli, anche la risposta a un ordine precedente (il Capitano parla, la sua voce entra nel microfono). Un **ordine scritto** ferma tutto tranne una risposta già in corso a un suo ordine precedente (non parla sopra nessuno: quella finisce, e la nuova la segue).
- **Una riga tagliata riprende dalla frase interrotta**: ciò che non è stato ascoltato si dice dopo, dalla frase che era in corso (o dalla successiva se quella era quasi finita), non da capo; se il resto supera 10 s è ridotto alla prima e all'ultima frase (di un messaggio: come comincia e ciò che chiede), così un messaggio interrotto non tiene il ponte per tutta la sua lunghezza una seconda volta. Riprende fino a tre volte, finché è ancora notizia (25 s per l'equipaggio, 60 s per chi parla da fuori), e passa **davanti** a ciò che è stato accodato dopo di lei. Non si riprendono le risposte (il Capitano ha parlato di nuovo) né le chiacchiere. Se chi è stato interrotto risponde intanto al Capitano, la risposta prende il posto del resto (`superseded`).
- **Notizie vecchie**: un rapporto è utile pochi secondi dopo ciò che racconta. La riga di un turno di evento non ancora detta 18 s dopo la notizia più recente del turno (30 s per un avviso di pericolo) è scartata e dichiarata (`expired`), mai detta in ritardo; `voice.report_since` è il momento della notizia (senza, si conta dall'accodamento) e un produttore che passa `expires_s` decide da sé. Il server aggiunge due cose: se anche l'ultima notizia in attesa di un ponte silenzioso ha più di 12 s il turno non si fa (le notizie restano nello stato della nave); in un turno fresco le notizie con più di 8 s dicono quanti secondi hanno (`[happened 19 s ago]`, l'equipaggio ne parla al passato o tace). Restano fuori le notizie che sono una richiesta di parlare (chiamata del controllo di volo, rapporto dopo l'azione, notizie della rete della flotta, una visita alla porta) e gli avvisi di pericolo.
- **Argomento**: una riga con `topic` sostituisce una più vecchia non ancora detta con lo stesso `topic` (`superseded`), a meno che la vecchia sia più importante.
- **Scadenza** e **`stale_if`**: un rapporto che non ha parlato entro la scadenza (o per cui `stale_if()` risponde `True` al momento di partire) è scartato e dichiarato.
- **Unione**: due frasi dello stesso ufficiale, stessa priorità, accodate a meno di 4 s l'una dall'altra e non ancora in sintesi, diventano una sola riga (un respiro, un sottotitolo).
- **Turni**: una voce sola alla volta, con un respiro di 0,34 s tra voci diverse, 0,18 s tra due frasi della stessa, 0,1 s prima di una risposta al Capitano.
- **Mai in silenzio**: ogni scarto va nel log, nei contatori (`voice.stats`) e al gioco come `line_dropped`.
- **Un tasto che non sale**: se il gioco perde il messaggio `ptt up` (o si chiude con il tasto premuto), dopo `KEY_STUCK_S` = 45 s il tasto è considerato rilasciato e l'equipaggio riprende a parlare; alla disconnessione e a `hello` (nuova sessione) `clear()` libera il palco e scarta tutto quello che era in coda.

Colla nel server (le sole righe di `server.py` toccate, elenco nel rapporto): `ptt`/`player_text` → `captain_begin/end/input` e poi `_captain_speaks()` del modulo dell'equipaggio (`agent.preempt()`: le chiamate al modello in corso si fermano; `voice.drop_low_priority()`; il gancio `voice.captain_speaks()`); `turn_worker` → `captain_turn_begin/end` attorno al turno del Capitano; `quiet_moments` → `voice.chatter`; la coda dei turni (`_TurnQueue`) mette l'ora d'arrivo agli eventi e il turno di evento passa a `voice.report_since` l'ora della notizia più recente; un avviso di pericolo (`_URGENT_EVENT`) non aspetta il ponte silenzioso; il messaggio che il nemico sta scrivendo (`enemy.respond` per una `transmission:`) si ferma appena il Capitano prende la parola (`voice.preemptible`) e si scrive dopo il suo ordine; un avviso di pericolo che `agent.preempt()` ferma mentre si scrive si riaccoda e si dice dopo la risposta al Capitano (l'equipaggio tace se l'ordine lo copriva già). Un rapporto tagliato dal Capitano lo ferma `agent.preempt()`.

`voice.captain_speaks()` è il gancio che il server chiama quando il Capitano comincia a parlare: chi parla si ferma (alla prossima pausa entro mezzo secondo, altrimenti una dissolvenza rapida) e le righe `LOW` in coda sono scartate; si può chiamare più volte e accanto a `captain_begin/captain_input` (una riga già in fase di stop resta com'è); con il tasto giù non fa altro, senza tasto prende anche il palco per la risposta, come un ordine scritto (che non ferma una risposta già in corso a un ordine precedente). Il palco accetta anche un motore di voce della prima versione (il cui `stream` è un generatore asincrono di PCM senza tono né arresto): i doppioni di prova di altri moduli continuano a funzionare.

## 5bis. Ciò che è rivolto al Capitano non si perde (VOCI-3)

Il 5/10 due risposte al Capitano e un avviso sono andati perduti (`synth_timeout`), e nelle battaglie fitte la coda piena (`MAX_QUEUED` = 10) scartava righe urgenti e risposte insieme alla chiacchiera. Ora una riga è **protetta** (`Line.protected`) se è una risposta (`Prio.ANSWER`) o è `addressed` (rivolta a lui: `voice.say(..., addressed=True)`):

- **Niente scadenza né `stale_if`**: si dice quando arriva il suo turno (nessun «notizia vecchia»). Se ci sono più righe di quante la coda ne tenga, le vittime sono solo le non protette (`overflow`).
- **Voce non fatta** (la sintesi fallisce, non risponde entro `SYNTH_TIMEOUT_S`, o produce silenzio): la mente la richiede alla sintesi fino a due volte (`SYNTH_RETRIES`, il contatore `tries`); alla terza il Capitano **la legge**: messaggio `notice` (sezione 2.1), e la riga conta come detta nel registro di ciò che il ponte ha detto (gli ufficiali non la ripetono). Contatori: `voice.stats["synth_again"]`, `["noticed"]`.
- **Ripensamento** (`rethink`) scaduto o fallito: la riga si dice com'era, non si perde. Solo chi l'ha scritta la può ritirare: un ripensamento che risponde `None` per scelta (la cosa non conta più) dà `line_dropped{reason:"rethought"}`, com'era.
- **Interrotta dal Capitano** riprende fino a 8 volte (`MAX_RESUMES_ADDRESSED`, 3 per le altre) e non invecchia mai.
- Un ripensamento che finisce con uno scarto **sveglia il palco** (prima la riga dopo poteva restare in coda per sempre: una svista del palco trovata dal banco).

Chi mette `addressed`: `_say_external` (comandanti del Mandato sul canale, la chiamata di Fleet command, il controllo del porto: tutto ciò che è detto *a lui*), `_ally_say(..., to="aquila")` e `_rourke_say(direct=True)` quando la riga è una chiamata a lui nella voce di chi parla, e una riga di rete che chiama il Capitano (sezione 5ter, la dice il suo ascoltatore).

**Un avviso di pericolo, o una chiamata a lui su una rete, non si perde nemmeno se il Capitano parla subito.** Il turno di rapporto aspetta fino a 3 s che la riga in corso finisca e 0,6 s che arrivi ciò che accompagna l'avviso: se in quel lasco arrivano le parole del Capitano, prima rispondono a lui (il rapporto era in attesa), ma l'avviso (`_URGENT_EVENT`) e il traffico di rete che lo chiama (`nets.CALL_MARK`) tornano in coda e si dicono dopo il suo ordine (l'ufficiale tace se l'ordine li copriva già). Prima di VOCI-3 le notizie raccolte in quel lasco sparivano tutte (`bench.voice_replay` r5 falliva); le notizie semplici restano nello stato della nave e nella cronologia, come sempre.

## 5ter. Le reti radio, i registri delle console e chi ascolta (VOCI-3)

Il 5/10 la flotta, il volo e i marines parlavano tutti sull'unico altoparlante del ponte: ~480 righe in 70 minuti, un terzo mai ascoltato, le stesse notizie da tre bocche e gli ordini del Capitano perduti dietro. Ora una **rete** (`astra_mind/nets.py`) ha un **ascoltatore**, l'ufficiale che ha il turno su quel canale, e il Capitano sente il ponte come un ponte vero: l'XO per il quadro, gli altri ufficiali per la loro console solo quando serve, il resto sul registro.

| Rete | `net` | Ascoltatore | Console (`net_traffic.console`) |
|---|---|---|---|
| Rete della flotta (Fleet command, i capitani alleati) | `fleet` | Comunicazioni (`comms`) | `comms` |
| Rete del volo (CAG, caposquadriglia, Capo del Ponte) | `flight` | Controllo di volo (`flight`, Price) | `flight` |
| Rete dei marine (maggiore Reyes, capisquadra) | `marines` | l'XO | `xo` |

**Cosa arriva all'altoparlante da solo** (e non passa dall'ascoltatore): (1) la **risposta** a una parola del Capitano (`answer`: l'ammiraglio che gli risponde, un capitano a una sua richiesta: passa prima di tutto e non si perde); (2) una **chiamata diretta** a lui nella voce di chi parla (`direct`: l'ordine di Fleet alla Aquila); (3) una rete che il Capitano ha **messo sull'altoparlante** («metti la rete del volo sull'altoparlante», strumento `net_speaker`, che solo un suo turno può usare) e finché non dice di toglierla; (4) la rete del volo mentre è **in una cabina di pilotaggio o sul ponte di volo** (è la sua radio: `Mind._flight_presence`); (5) la rete dei marine mentre il Capitano è **con i marine**, nella loro barca all'andata o al ritorno o sui ponti della nave che abbordano (è la sua radio: `Mind._marines_presence`, che legge `ship_state.boarding.captain_with_marines`; `captain_aboard` dice solo i ponti dell'altra nave); (6) una riga di un marine che **lo chiama** (lo strumento `say` dei marine ha `to_captain`: una decisione o un ordine che solo lui può dare, o un pericolo per lui su cui deve agire adesso; arriva come `direct`, nella voce di chi parla), mentre le notizie e il quadro sono dell'XO. Le reti dei comandanti del Mandato non sono reti: chi lo chiama gli parla (5bis, `addressed`).

**Tutto il resto è traffico di rete** (`Nets.post`): va registrato (`net_traffic`, sezione 2.1: consoles e taccuino) e consegnato all'ascoltatore come **evento del suo turno** (`net: traffic on the fleet net — N lines the Captain has NOT heard … Comms has the watch on this net: …`, con l'età di ogni riga e chi la manda; `[URGENT]` se il mittente ha detto «pericolo ora»; «and calls the Captain» se è per lui). Il turno è un turno dell'equipaggio come gli altri: l'ascoltatore decide con la sua dottrina (`agent.NET_ASK`, `crew._NETS`) se dire una riga al Capitano (`speak`: è la *sua* voce, in italiano o come parla il Capitano, e passa dal palco con le sue priorità) o scrivere la routine sul registro con `console_log` (silenzioso). Un messaggio per gli altri alla rete (un capitano a un altro: `to` ≠ `aquila`/`fleet`) si registra e basta: nessuno viene svegliato.

**Con quale richiesta** (`agent.net_ask`): un turno di sole notizie di rete è chiesto con la **sola dottrina dell'ascoltatore** (`NET_ASK`: «TELL HIM» o «LOG IT», con le condizioni scritte); se nello stesso turno ci sono altre notizie, la richiesta generale (`EVENT_ASK`, «riferisci») la precede. Misurato dal vivo (`bench.voci3_live`, il modello dell'equipaggio, 0,0003 $ a turno): con la richiesta generale per prima gli ascoltatori leggevano a voce la routine (posizioni, «rearmed», «squad in position») in 14 prove su 24; con la sola dottrina scritta come due elenchi (cosa dirgli, cosa solo registrare) 28 prove su 28 fanno la cosa giusta: la routine sul registro senza una parola, e una riga dell'ascoltatore per l'urgente, la chiamata a lui, il pilota o il marine a terra.

**I tempi** (`nets.py`): il traffico urgente va all'ascoltatore subito, quello rivolto al Capitano dopo `ADDRESSED_BATCH_S` = 1,2 s (un respiro per ciò che arriva con esso), la routine insieme dopo `ROUTINE_BATCH_S` = 12 s dalla prima riga. Un turno d'ascolto con una sola riga di registro e nessun `speak` non entra nella conversazione dell'equipaggio (non c'è nulla da ricordare).

**`console_log`** (strumento degli ufficiali, in ogni loro turno): scrive una riga su una console (`xo`, `helm`, `ops`, `tactical`, `comms`, `sensors`, `engineering`, `flight`; `kind` `routine` o `notice`) e sul taccuino; nessuno la sente. Il registro tiene le ultime 40 righe per console (`LOG_KEEP`) e il traffico le ultime 80 per rete (`TRAFFIC_KEEP`).

**Cosa sanno gli ufficiali**: la testa dello stato del ponte (`[The bridge now]`) porta «sulle reti e sui registri delle console, NON detto a voce» (`Nets.digest`: le ultime 12 righe degli ultimi 150 s, le reti sull'altoparlante in testa), così nessuno ripete a voce ciò che è già sul registro e chi parla sa che «nessuno ha detto nulla» non vuol dire che la rete taccia.

**Il gioco** (C++, `AstraMindSubsystem` / `AstraScreensSubsystem`): `net_traffic` e `console_log` finiscono in `NetLines` (160 righe) e nel cronometro (`FAstraTimeline`, «net»/«log»); la console Comunicazioni mostra il traffico della rete della flotta, la console Volo quello della rete del volo; il taccuino ha una pagina **LOG** (Tab, ruota delle pagine) con tutto, anche i marine: le righe già ascoltate in grigio, quelle da notare in ambra, quelle urgenti in rosso; `net_speaker` fa dire alla testata della pagina quali reti sono sull'altoparlante. (Il C++ di VOCI-3 non è stato compilato dall'aiutante: lo compila il capo.)

**Interruttore**: `ASTRA_NETS=0` rimette il vecchio instradamento (ogni rete parla sull'altoparlante, nessun ascoltatore: sono le stesse linee di prima e il banco `bench.voci3_games` lo usa come termine di confronto, `OLD`). Si cambia al prossimo avvio della mente.

## 5quater. Gli ordini dati senza parole: il quadrante dei comandi (VOCI-3)

Il Capitano può dare un ordine senza dire nulla (tasto G tenuto premuto: modi delle stazioni tactical/helm/flight/ops, `set_alert`): il gioco lo esegue (`ApplyCommand`, `by=captain`) e manda alla mente `event{text:"bridge: the Captain gave an order from his command wheel, without a word: <cosa> (<dettaglio del comando>)", report:true}` (`crew.WHEEL_EVENT`). Per la mente **è un suo ordine come uno detto a voce**: `Mind._wheel_turn` lo prende subito, in un turno suo (non aspetta un ponte silenzioso, non si unisce alle altre notizie), dentro `captain_turn_begin` (la riga è una **risposta**: passa prima di tutto e non si perde), con il solo strumento `speak` (la console ha già fatto ciò che è stato ordinato: nessuno lo ripete) e senza gli ordini permanenti. L'ufficiale della stazione (l'XO per l'allarme) conferma in una parola o due, nessun altro parla (`agent.WHEEL_ASK` e la regola «The command wheel» in `crew._RULE_BASE`), senza domande né spiegazioni né ripetere ciò che il quadrante mostra; una riga sola solo se il comando non è passato o fa male alla nave in un modo che il Capitano può non vedere. L'ordine resta nella conversazione (l'osservatore di iniziativa lo legge tra gli ultimi ordini, `initiative.recent_orders`) e non è una notizia per l'osservatore (`Watch.note`). Più ordini in pochi secondi sono più turni, ciascuno confermato dal suo ufficiale. Il gioco manda `report:true` solo se vuole la conferma a voce; con `report:false` la mente non dice nulla.

## 5quinquies. La parola del ponte, il controllo e i canali: dottrina e orchestrazione (VOCI-3, tappe 2 e 3)

Il Capitano sente ogni parola detta in plancia: ogni parola deve meritarsi il posto. Tutto qui è **prompt e orchestrazione** (nessun filtro sulle parole dei modelli, `docs/ARCHITETTURA.md` §1bis): i modelli decidono, il codice decide quando li interpella e che cosa vedono.

**Una voce per il quadro** (`crew._speech_rules`, `agent.EVENT_ASK`, `agent.NET_ASK`, `agent.WHEEL_ASK`, `initiative.WATCH_ASK`).
- L'XO è la voce del quadro e dei consigli (una frase di dieci-venti parole: che cosa è cambiato, che cosa significa, che cosa potrebbe fare). Gli altri ufficiali parlano per la loro console in tre casi: il Capitano li ha chiamati o ha dato un ordine alla loro stazione (una conferma brevissima: l'ordine e basta, niente distanze, niente posizioni del nemico, niente consigli); un pericolo nel loro campo su cui può agire adesso (una salva in arrivo, una falla, il reattore o il calore al limite, una squadriglia persa); una decisione che è sua nel loro campo. Tutto il resto è routine e va sul registro della console (`console_log`).
- Il turno di notizie (`EVENT_ASK`) ha come predefinito il **silenzio**: «il Capitano agirebbe diversamente, o starebbe peggio, se nessuno lo dicesse a voce?». Tre elenchi: SAY IT (una riga dall'XO, o dall'ufficiale solo per pericolo/decisione/chiamata), LOG IT (`console_log`, nessun `speak`), SAY NOTHING (già detto da chiunque con altre parole, già in coda, lo stesso quadro di nuovo, il suo stesso ordine che torna, notizia invecchiata). Prima di parlare l'ufficiale legge «Said aloud» (che ora dice: *il Capitano l'ha SENTITO: mai più, nemmeno con altre parole o da un altro ufficiale*) e dice solo ciò che è NUOVO. Nel turno di notizie i «Recent events» sono etichettati: la notizia di questo turno è l'evento in fondo al messaggio, un'altra più vecchia era la notizia di un altro turno e non si riferisce di nuovo.
- **Chiamate di sistema** (soccorsi di mercantili, notizie di convogli, un porto che chiama): sono delle Comunicazioni. La prima in una riga (chi, quanto lontano, chi la insegue); le seguenti, finché il Capitano non ha risposto, sul registro delle comunicazioni o, se insieme cambiano il quadro, in UNA riga raggruppata («altri due mercantili chiamano, sono sul registro»). In uno scontro il Capitano sente di una chiamata solo se l'Aquila può farci davvero qualcosa adesso (a portata, in tempo).
- Una conferma che fallisce (`agent._follow_up`): se la riga che l'ufficiale aveva già detto spiegava già il perché, non si dice due volte (nessuno strumento). Le conferme di un ordine a voce sono «l'ordine letto con il valore che serve» (`_ACK`, la descrizione di `speak`).
- L'osservatore (`initiative.py`) scrive sul registro ciò che imposta dentro gli ordini per tenere viva la console (un nuovo bersaglio dopo un abbattimento, la scansione, gli scudi, lo schermo) e dice una riga solo per ciò che cambia lo scontro (un lancio, un richiamo) o che richiede una parola del Capitano; per le squadriglie, dove la delegazione è `advise`, PROPONE in una riga («Alpha in pattuglia?»).

**Il ritmo del quadro** (`server.py`, il lavoratore dei turni). Il 5/10, in tre minuti di battaglia, 86 notizie da riferire e un turno di rapporto per ciascuna: 10 battute al minuto, la stessa situazione ripetuta da tre bocche. Ora un turno di rapporto per notizie di routine parte `PICTURE_GAP_S` = 20 s dopo la fine di uno che ha parlato (`REPORT_GAP_S` = 10 s dopo uno che ha taciuto: il modello non si interpella a ogni notizia, la spesa in battaglia era 1,07 $/ora contro 0,90 prima) e le notizie arrivate intanto si leggono insieme, ciascuna con la sua età; un avviso di pericolo (`_URGENT_EVENT`) non aspetta il quadro ma, dopo uno detto, aspetta `URGENT_GAP_S` = 6 s (le «breach» e i «missiles inbound» di una battaglia arrivano ogni pochi secondi: ciò che arriva intanto si dice insieme); una chiamata di un comandante nemico (`transmission:`), del controllore di volo a un Capitano in cabina, o una chiamata a lui su una rete (`_presses`) non aspettano.

**La delegazione** (`delegation.py`, `Mind.delegation_sync`). Il gioco parte ogni volta con `auto` su ogni console e dimentica ciò che il Capitano ha detto; il 5/10 questo voleva dire squadriglie lanciate e inseguimenti iniziati da nessuno. La mente: (1) in una **campagna nuova** mette `advise` a ciò che impegna la nave (`flight`, `helm`: l'ufficiale propone, il Capitano dice «via»; un riflesso del gioco, come la pattuglia di Alpha, non scatta più da solo perché `OnAuto(flight)` è falso); (2) **tiene ciò che il Capitano dice** («nessuno lancia senza il mio ordine», «Voss, decidi tu», «da qui in poi fate da soli»: la chiamata dell'XO al modo `delegation`, riuscita, in un suo turno) in `<cartella della campagna>/delegation.json` e lo rimette nel gioco a ogni avvio (`delegation_sync`, comando `station` dell'XO, in silenzio, finché il Capitano ha scelto la campagna e le console sono in linea). Il resto delle regole (`stations.may_on_initiative`: ciò che per modo è del Capitano, gli ordini permanenti, `advise` e `manual`) è invariato.

**Il canale giusto** (`Mind.channel_watch`, `router.py`). Il 5/10 il canale con la flotta è rimasto aperto diciotto minuti dopo la risposta dell'ammiraglio, e quel che il Capitano diceva ai suoi («dove posso trovare i Kestrel?», «abbordate la Acheron subito, mandate tutti i marine», «ritirate i marine»: gli ultimi due su un canale del nemico) è uscito sul canale. Ora (1) un canale con la flotta, un alleato o un nemico è aperto per uno scambio (`_channel_opened`: un `hail`, una `transmission:`, o un canale che il gioco dice aperto quando il Capitano parla): senza nulla passato per `CHANNEL_IDLE_S` = 75 s (né una parola loro, né una sua verso di loro) le Comunicazioni lo chiudono in silenzio (`end_transmission`, una nota sul registro delle comunicazioni; il Capitano lo riapre con una parola; non si chiude mentre il Capitano parla); (2) il giudizio del router (`PROMPT`) sa che cosa è nostro e non esce mai: i sistemi della nave, i caccia (Alpha, Bravo, i droni), le barche (i Kestrel), i marine, il teletrasporto, «dove posso trovare...», e un ordine imperativo su ciò che è nostro non si dice a `{party}` a meno che lo nomini o gli risponda. Provato con `bench.voci3_router` (venti frasi vere del 5/10, un canale aperto, cinque prove ciascuna): 95 decisioni su 95 giuste (prima: «ritirate i marine» sul canale del nemico 3 prove su 3). (3) **Sulla rete della flotta si sveglia solo a chi è rivolta la frase.** Prima ogni frase del Capitano sulla rete della flotta svegliava ogni capitano alleato e l'ammiraglio (con quattro gruppi, cinque chiamate al modello, circa 0,005 $ al prezzo medio di 0,00093 $ a chiamata del registro della spesa, quasi sempre per «nessun cambiamento»). Ora il router, che già decide che cosa esce, dice anche **a chi** (`Route.to`, `router.parse_to`; solo sui canali della flotta, dove c'è da scegliere): l'ammiraglio (Rourke, il comando di flotta, «ammiraglio»), una nave o il suo capitano (come li ha chiamati il Capitano) o tutti (la flotta, «tutti», o non è chiaro). `Mind._to_party` sveglia solo quelli: all'ammiraglio solo `director.admiral_reply`; a una nave solo il comando del suo gruppo (`war.captain_to_fleet(..., to=nave)`, e l'ammiraglio non risponde per lei); a tutti come prima; un nome che nessuno porta vale «tutti» (mai nessuno: una parola del Capitano non si perde). Una chiamata al modello invece di cinque per frase (ammiraglio o una nave). `bench.voci3_router` ora giudica anche il destinatario (23 frasi): 46 decisioni su 46 giuste in due prove, 0,002 $ (92 su 92 in quattro prove con un vocabolario del codice più largo, poi ridotto alle sole parole del protocollo: `admiral`, `all`, e come le scrive il modello in inglese; il modello scrive «admiral», «all» o il nome della nave come l'ha detto il Capitano). Chi guarda il costo: la rete della flotta è una parte piccola della spesa (una frase del Capitano ogni tanto), il risparmio è circa 0,004 $ per frase a una nave o all'ammiraglio; la frase a tutta la flotta costa come prima.

**Gli alleati** (`war_minds.py`). Il serbatoio dei capitani alleati era di sei: la settima nave senza nome aveva un capitano già in uso, il capo di un gruppo che passava da una nave all'altra «prendeva il comando da se stesso» ogni due secondi: 226 chiamate al modello in una sessione (circa un quarto della spesa). Ora i capitani sono quattordici e si prende il primo nome non ancora in uso; un cambio di capo è una successione solo se il nome cambia (due navi con un capitano solo non passano il comando) e si dice una volta ogni `TAKEOVER_GAP_S` = 90 s per posto.

**Misure** (`bench.voci3_battle`, tempo reale, i minuti più fitti del 5/10: S3 da 360 s, 46 notizie da riferire in due minuti, 6 parole del Capitano, attraverso il server vero e il modello vero dell'equipaggio; la nave è finta e statica, quindi le cifre misurano il PARLATO, non il giudizio sul combattimento; le prime due minuti di ogni prova):

| | battute | al minuto | di rapporto | risposte | parole per battuta | oltre 22 parole | XO sui rapporti | righe sui registri |
|---|---|---|---|---|---|---|---|---|
| prima di VOCI-3 | 16 | 8,0 | 10 | 6 | 23,1 | 8 | 0 % | 0 |
| dottrina senza ritmo (`PICTURE_GAP_S` assente) | 14 | 7,0 | 8 | 6 | 17,2 | 2 | 88 % | 26 (in tre minuti) |
| dottrina, ritmo del quadro, avvisi a 6 s | 8 | 4,0 | 2 | 6 | 16,8 | 2 | 50 % | 21 |

Le risposte al Capitano (una per sua parola, subito: prima risposta 1,1–1,5 s) non cambiano: sono ciò che ha chiesto. La dottrina da sola spostò la voce (l'XO dal 0 al ~90 % dei rapporti, il routine sui registri, le battute più corte) ma non il numero: i rapporti restavano uno per ogni gruppo di notizie (15 in tre minuti); il numero lo fa il ritmo. Il limite del banco: una sola finestra e una sola prova per configurazione (la spesa: 0,03–0,05 $ ciascuna), un modello a temperatura 0,4: le versioni intermedie della dottrina davano da 8 a 13 rapporti nei due minuti, e la varianza tra due prove della stessa non è misurata; la cifra buona è l'ordine di grandezza (da 10 a 2–8 rapporti in due minuti), non la seconda cifra. Le tre chiamate di soccorso dei mercantili (`bench.voci3_live --only distress`): con la richiesta generale una battuta per chiamata, tre prove su tre; con la richiesta propria (`SYSTEM_CALL_ASK`: la prima in una riga delle Comunicazioni, le altre sul registro) tre su tre una sola battuta, nel registro le altre due.

## 6. Regolazioni (variabili d'ambiente)

| Variabile | Predefinito | Cosa fa |
|---|---|---|
| `ASTRA_TTS_SPEED` | 1.12 | velocità del parlato (1.0 = quella del modello; ±0,06 secondo il tono). Nessun costo di comprensibilità misurabile fino a ×1,20: WER del riconoscitore sulle voci a ×1,00 / ×1,12 / ×1,20 = 16,7 / 16,6 / 16,8 % in media sulle sette lingue (tre voci, tre frasi per lingua), e con dieci voci e quattro frasi 13,6 / 16,6 / 15,7 % in olandese, 27,1 / 23,7 / 26,0 % in italiano: differenze dentro il rumore |
| `ASTRA_TTS_LUFS` | −19 | volume di ogni voce |
| `ASTRA_TTS_PAUSE_MS` | 300 | pausa più lunga tenuta dentro una riga |
| `ASTRA_TTS_RESIDENT` | 2 | modelli di lingua tenuti in memoria (~430 MB l'uno) |
| `ASTRA_STT` | `parakeet` | motore provato per primo: `parakeet` (Neural Engine), `parakeet-onnx` (CPU), `whisperkit`, `faster-whisper`; `portable` = solo i motori che girano ovunque (Parakeet ONNX, faster-whisper: il percorso di Windows, forzato su un Mac per provarlo); `off` = nessun motore (si scrive) |
| `ASTRA_STT_FETCH` | `1` dove non c'è l'helper, `0` su Apple Silicon | `1`/`0`: la mente scarica da sola il modello Parakeet ONNX mancante (~490 MB) alla prima partita |
| `ASTRA_STT_MODEL` | `ultra` | modello Parakeet: `ultra`, `v3`, `redux` |
| `ASTRA_STT_BIN` | — | percorso dell'helper `astra-stt` |
| `ASTRA_SHERPA_MODEL` | `<modelli>/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8` | modello del Parakeet su CPU (`python -m astra_mind.stt --fetch-portable`) |
| `ASTRA_FW_MODEL` | `small` | modello di faster-whisper |
| `ASTRA_VOICE_MODELS` | `<home>/voice/models` | dove cercare i modelli di Whisper/Parakeet |
| `ASTRA_MIC` | `auto` | `always` (microfono sempre aperto), `ptt` (aperto solo a tasto premuto), `off` (nessun dispositivo: il tasto prende la parola e registra silenzio; per le prove), `auto` |
| `ASTRA_VOICE_QOS` | 1 | priorità dei thread della voce (macOS) |
| `ASTRA_NETS` | 1 | `0` = il vecchio instradamento: le reti della flotta, del volo e dei marine parlano tutte sull'altoparlante e nessun ascoltatore le legge (sezione 5ter; serve da confronto nei banchi e come rete di sicurezza) |
| `ASTRA_MIND_LOG`, `ASTRA_MIND_PORT`, `ASTRA_TTS_WARM` | — / 8765 / 1 | il file in cui la mente scrive il suo log (lo imposta il gioco); la porta (la legge anche il gioco); `0` = nessuna voce caricata in anticipo (prove). Vedi [WINDOWS.md](WINDOWS.md) §4.5 |

## 7. Come si prova (dalla cartella `mind/`)

```
uv run python -m bench.voice_units            # 84 controlli veloci (audio, nomi, lingua, riconoscitore con motori finti, regole del testo tagliato)
uv run python -m bench.voice_floor -v         # 30 scenari del palco con orologio virtuale (-v: la cronologia vista dal gioco)
uv run python -m bench.voice_replay -v        # 5 rifacimenti del test dal vivo del capo attraverso il server vero (agente, router, palco), modello e voci finti
uv run python -m unittest bench.voci3_unit    # le reti, il registro, lo strumento `console_log`, l'altoparlante, le righe rivolte al Capitano, il quadrante dei comandi, il ritmo del quadro, la delegazione, i canali, a chi è rivolta la frase sulla rete della flotta (69 controlli, nessuna rete)
uv run python -m unittest bench.war_minds_unit    # le menti della guerra (capitani alleati, nemici, successioni, `FanOutTests`: una frase per una nave sveglia solo quella nave) (71 controlli, nessuna rete)
uv run python -m bench.voci3_floor -v         # 8 scenari del palco e delle reti con orologio virtuale (una risposta mai persa, la voce rifatta e poi `notice`, ...)
uv run python -m bench.voci3_games s2 s3      # le partite del 5/10 (bench/data/games_2026-10-05, ricavate dai log con bench/games_extract.py) rimesse nel server vero: REAL / OLD / NEW
uv run python -m bench.voci3_live --only nets --runs 4   # (modello vero, chiave nell'ambiente, ~0,01 $) gli ascoltatori delle reti e le conferme del quadrante dei comandi, giudicati dalle chiamate agli strumenti
uv run python -m bench.voci3_router --runs 5          # (modello vero, ~0,005 $) che cosa esce su un canale aperto, e a chi sulla rete della flotta: ventitré frasi vere del 5/10
uv run python -m unittest bench.voci3_names   # i nomi del glossario sulle 116 frasi vere del 5/10 (cambiano solo i nomi, mai una parola) e sulle parole di Whisper (con ASTRA_VOICE_MODELS); `-m bench.voci3_names --audit --scene` stampa le cifre del §9
uv run python -m bench.voci3_battle s3 --from 360 --to 480 -v   # (modello vero, tempo reale, ~0,04 $) due minuti di battaglia vera attraverso il server: chi parla, quanto, che cosa va sui registri
uv run python -m bench.voice_pipeline stt --backends parakeet-ultra,whisperkit-baseline   # riconoscimento: WER e latenza, motori alternati clip per clip
uv run python -m bench.voice_pipeline live tts mic floor mem   # (più sezioni di seguito) dal tasto al testo, sintesi, microfono, palco con voce vera, memoria
uv run python -m bench.voice_pipeline report  # il rapporto in docs/bench/voce_<data>.md (dopo aver girato le sezioni)
uv run python -m bench.voice_e2e --lang it  # tutto il collegamento da capo a fondo: gioco finto, microfono finto che suona un ordine registrato, riconoscimento e voci
                                             # veri, palco vero, modello di linguaggio finto (nessuna chiamata di rete): dal rilascio del tasto al testo, alla prima parola
                                             # della risposta, dalla pressione all'officer che tace
uv run python -m astra_mind.stt               # quali motori di riconoscimento ci sono su questa macchina
uv run python -m unittest bench.portable_unit -v   # il percorso portabile (Windows): scelta dei motori, log, porta, segnali, voci SAPI (docs/WINDOWS.md §7)
ASTRA_TEST_PORTABLE_REAL=1 uv run python -m unittest bench.portable_unit.TestPortableEngines   # Pocket TTS parla, Parakeet ONNX e faster-whisper ascoltano
uv run python -m astra_mind.firstrun --check  # lo sguardo alla macchina (chiave, microfono, librerie che caricano, modelli, voci di sistema)
uv run python -m astra_mind.tts               # quali modelli e voci sono in cache
```

## 8. Installazione e pacchetto (per chi assembla l'app)

| Cosa | Dove | Come si ottiene | Peso |
|---|---|---|---|
| Ambiente Python (scipy, num2words nuovi) | `mind/.venv` (nell'app: lo crea uv al primo avvio) | `uv sync` | — |
| Helper `astra-stt` (Parakeet sul Neural Engine) | `mind/stt_server/bin/astra-stt` (trovato da solo anche in `<app>/Contents/Resources/mind/stt_server/bin/`) | `mind/stt_server/build.sh` (Xcode 26.2; la compilazione sta in `~/Library/Caches/ASTRA`, non dentro `mind/`) | 17 MB |
| Modello Parakeet Ultra (Core ML int8) | `<modelli>/parakeet-ultra-coreml` se c'è, altrimenti `~/Library/Application Support/FluidAudio/Models` | `uv run python -m astra_mind.stt --fetch` (scarica ~600 MB e compila per il Neural Engine: 1–3 minuti la prima volta, poi 0,5 s). **Per un'app che non deve toccare la rete**: copiare quella cartella in `voice/models/` (che `tools/pacchetto.sh` già copia in Application Support) | 600 MB |
| WhisperKit (riserva: le lingue oltre le 25 europee, e il caso in cui Parakeet non parta) | `whisperkit-cli` (Homebrew) e `<modelli>/models/argmaxinc/whisperkit-coreml/…turbo` | già presenti; su una macchina nuova la prima volta il Neural Engine compila il modello (minuti): `uv run python -m astra_mind.stt --warm-whisper` lo fa in anticipo | 1,6 GB, si carica solo se serve e si scarica dopo 10 minuti di inattività |
| Pocket TTS, sette lingue | cache Hugging Face (`~/.cache/huggingface`, usata senza rete quando c'è tutto) | `uv run python -m astra_mind.tts --fetch` (~440 MB per lingua; due lingue restano in memoria). Finché il modello di una lingua non è sulla macchina (un'installazione nuova) la riga la dice una voce di sistema macOS invece di aspettare il download, che la mente fa in background all'avvio per la lingua del Capitano e per l'inglese | 3 GB |
| Guadagni e sostituzioni delle voci | `mind/astra_mind/voice_gains.json`, `voice_overrides.json` | nel repository; si rigenerano con `uv run python -m astra_mind.voice_casting` (25 minuti) | 20 KB |
| Windows / Linux / Mac senza il helper | Parakeet ONNX su CPU e faster-whisper | `uv sync` li prende da solo (dipendenze con marcatore di piattaforma; sul Mac con l'helper `--extra portable` per provarli); il modello Parakeet ONNX (~490 MB) si scarica alla prima partita o con `--fetch-portable`, quello di faster-whisper con `--fetch-whisper`; `python -m astra_mind.firstrun` fa tutto (`tools/windows/Setup-ASTRA.ps1`: [WINDOWS.md](WINDOWS.md)) | — |

`tools/pacchetto.sh` copia `mind/` con `rsync`: la cartella di compilazione di Swift non deve finirci (900 MB); con `build.sh` com'è ora non si trova più dentro `mind/`, ma per le cartelle `.build` già esistenti conviene aggiungere `--exclude .build --exclude .swiftpm`.

## 9. Il riconoscimento del parlato, passo per passo (per chi lo tocca)

1. **Tasto giù** — `captain_begin()`: chi parla si ferma entro mezzo secondo. Il microfono (`audio_in.py`) tiene sempre gli ultimi 300 ms già ascoltati (pre-roll) e li consegna subito alla sessione di riconoscimento, poi ogni blocco da 20 ms. Se la periferica è una cuffia Bluetooth si apre il microfono del computer (la cuffia passerebbe alla qualità da telefono e il suono del gioco cala).
2. **Mentre il tasto è premuto** — circa ogni secondo la sessione (`RecognitionSession`) fa decodificare a Parakeet quello che è stato detto fin lì (una *bozza*: ~0,12 s per una frase di 5 s sul Neural Engine). Le bozze si fanno solo se il primo motore è veloce, è pronto e parla la lingua dell'ultimo ordine; non chiamano mai il secondo motore.
3. **Tasto su** — 100 ms di post-roll (l'ultimo suono deve uscire dai buffer del sistema). Se l'ultima bozza copre tutto il parlato è la risposta e il testo esce subito; se dopo la bozza c'è ancora parlato, una decodifica completa (~0,06–0,12 s). **Secondo parere**: la frase va anche a Whisper large-v3-turbo (WhisperKit, ~1,8 s) solo se Parakeet ha confidenza sotto `ESCALATE_CONF` (0,84) **e** nel testo non c'è nessuna parola che un ufficiale di plancia direbbe (è quello che Parakeet scrive per una lingua che non conosce: giapponese romanizzato con confidenza 0,63–0,80), oppure se la lingua dell'ultimo ordine non è tra le 25 europee. Sulle lingue europee Whisper non fa meglio di Parakeet (misurato: WER 17,2 % contro 14,0 % sulle stesse frasi pulite; peggio in inglese, italiano, spagnolo, olandese) e costa 1,8 s: mandargli tutte le frasi con confidenza sotto 0,86 avrebbe fatto attendere il 6 % delle frasi pulite, il 14 % delle rumorose e il 54 % di quelle in battaglia per un risultato peggiore; con la regola attuale attende lo 0,5 %, l'1 % e l'11 %. `_arbitrate` sceglie il testo (un secondo parere in una lingua che Parakeet non legge vince sempre).
4. **Silenzio tagliato** — prima e dopo il parlato (rilevatore a energia, 220 ms di margine): Whisper «sente» sottotitoli nel silenzio, e un tasto premuto per sbaglio non arriva mai a un motore.
5. **Nomi e lingua** — `voice_glossary.py` corregge i nomi del gioco (alias, somiglianza fonetica per i nomi lunghi, il nome dell'ufficiale a inizio frase, il nome «a pezzi» tipo *Janusgate*); `voice_lang.py` decide la lingua tra 26 candidate (le sette delle voci locali, più quelle per cui esiste una voce di sistema o che si parlano ai giochi) pesando testo, vocabolario di plancia, lingua detta dal motore e lingua dell'ordine precedente (un «Mi sentite?» resta italiano anche dopo tre ordini in inglese). Una lingua europea fuori dalle 26 (bulgaro, croato, lituano…) viene riconosciuta bene ma risposta nella candidata più vicina.
6. **`transcript`** al gioco e turno all'equipaggio; le risposte escono nella lingua del Capitano (`lang`).

Motori (`voice_stt_backends.py`, un'interfaccia sola: `start`, `transcribe`, `stop`): `ParakeetBackend` (helper Swift sul Neural Engine, Apple Silicon), `SherpaParakeetBackend` (lo stesso modello in ONNX su CPU: Windows, Linux, Mac senza helper), `WhisperKitBackend` (99 lingue, dice la lingua, accetta i nomi come suggerimento), `FasterWhisperBackend` (CPU, portabile). L'ordine di prova è quello: il primo che parte è il motore veloce, il secondo la riserva. `ASTRA_STT` cambia il primo.

**I nomi della campagna al riconoscitore (VOCI-3, 5/10): misurato, e il glossario non diventa «vivo».** L'idea: dare al glossario i nomi che la partita ha adesso (navi e comandanti della mappa, capitani alleati inventati, flotte della Marcia) e farli cercare con una somiglianza più larga. Le 116 frasi dette a voce dal Capitano il 5/10 (`bench/data/games_2026-10-05`) mostrano il problema e dicono perché non conviene. (1) I nomi sbagliati sono circa la metà di quelli detti («Toul» e «Tool» per Thule, «Renis» e «Lerinis» per l'Erinys, «plegeton», «Taratus», «solmo», «Chestrel», «Rourg»), ma i modelli dell'equipaggio li hanno letti giusti dalla situazione della nave quasi sempre (il timoniere ha preso «la lettera» per la Lethe, il tattico «le Renis» per l'Erinys; su una trentina di frasi con un nome storpiato un solo rifiuto netto, l'XO su «Toul» che il glossario ora corregge, e due volte il timoniere ha preso «Tool» per il Janus Gate). Il glossario serve per ciò che si vede (sottotitolo) e per ciò che leggono router e capitani alleati. (2) Parakeet, il motore veloce, non prende un suggerimento: gli si può solo correggere il testo dopo. (3) Una corrispondenza più larga per i 45 nomi in gioco (somiglianza fonetica ≥ 0,75–0,80, anche nomi corti) recupera 2–4 dei 13 errori veri e prende per un nome da 42 a 173 parole comuni delle lingue su 24 mila del vocabolario di Whisper (carol → Charon, mesa → Mensah, stato → Sato, casa → Cassia, tale → Thule, solo → Solm): scarta più di quanto corregge. Il glossario resta quello di prima (nomi lunghi per somiglianza stretta, il resto per alias che sono spellature vere e mai parole): sulle 24 mila parole comuni ne riscrive 5, tutte volute (acron, foss, sticks, tule, vos), 28 su 234 mila dell'inglese. Fatto: gli alias delle spellature vere del 5/10 che non sono parole (plegeton, taratus, renis, lerinis, solmo, chestrel, keglex, kellex, rourg), e `Constance` non più per somiglianza (la verifica ha trovato che riscriveva «constante», parola dello spagnolo, del portoghese e del francese). La leva vera per i nomi su Parakeet è dentro il motore (vocabolario personalizzato dell'helper Swift con FluidAudio, o gli hotword di sherpa-onnx per il percorso portabile): non è fatta, tocca `mind/stt_server/Sources/astra-stt/main.swift` e un modello CoreML in più, e va misurata sulla voce del Capitano. Prove: `python -m unittest bench.voci3_names` (le 116 frasi vere: solo i nomi cambiano, mai una parola; `ASTRA_VOICE_MODELS` per il test sulle parole di Whisper), `python -m bench.voci3_names --audit --scene` (le cifre sopra).

**Il percorso portabile è più debole** (misurato sulle stesse frasi, docs/bench/voce_2026-09-30.md): Parakeet ONNX su CPU (esportazione int8) ha WER pulito 31,8 % contro 17,7 % dell'helper sul Neural Engine, mediana 141 ms contro 67 ms; faster-whisper `small` come riserva 3,8 s per frase (p95 7 s) e WER 32,6 %. Bastano per giocare, non per la qualità di riferimento. Le varianti quantizzate di WhisperKit (632 MB, `small`) sono state provate per accorciare la riserva sul Mac e scartate: non sono più veloci (1,74–1,78 s, quanto il modello intero) e sbagliano molto di più (WER pulito 38 % e 52 %).

**Limite del percorso portabile**: Parakeet ONNX non dà una confidenza confrontabile con quella dell'helper (l'esportazione int8 scrive perfino «Captain» per il turco «Kaptan»), quindi lì non c'è il passaggio automatico a Whisper per una lingua non europea alla prima frase: si imposta la lingua del Capitano (il file `captain_lang.txt` nella cartella della cache, che la mente scrive da sola quando cambia lingua) e da quel momento le frasi vanno a faster-whisper. Sul Mac con l'helper il passaggio è automatico (6 frasi su 6 in sei lingue non europee).

## 10. Come si legge il log della mente (`astra-mind.log`)

| Riga | Cosa vuol dire |
|---|---|
| `STT 0.27s after the key (decode 0.06s, parakeet, from the partial) [it] Timoniere, rotta 217, avanti tutta.` | dal rilascio del tasto al testo 0,27 s (100 ms sono il post-roll del microfono); `from the partial` = il testo era già pronto da una bozza fatta mentre il Capitano parlava; `[it]` la lingua che l'equipaggio userà |
| `Parakeet ready in 0.6 s` / `WhisperKit ready in 3.3 s` / `TTS model italian loaded in 1.8 s` | avvii dei motori (la prima volta su una macchina molto di più: modello scaricato e compilato) |
| `line 7 (sensors, normal) not spoken: expired — …` | una riga che non verrà mai detta, con il motivo (stessi valori di `line_dropped`); mai in silenzio |
| `line 7 merged into line 6 (sensors)` / `line 7 shortened (240 -> 96 chars, 18 s of speech waiting)` | l'unione di due frasi dello stesso ufficiale / l'accorciamento di una riga lunga quando c'è troppo parlato in attesa |
| `line 9 was cut at 30 %: the rest of it is said again as line 12 after the floor is free` | interrotta dal Capitano (o da un avviso): il resto, dalla frase che era in corso, si dice dopo la risposta (`it is`: tutta, se era appena cominciata) |
| `line 12 (flight): a report of something that happened 22 s ago is old news` | la notizia era troppo vecchia quando la riga è stata scritta: scartata (`line_dropped: expired`) |
| `3 event(s) not reported: the newest was 18 s ago, the bridge was busy: …` | le notizie hanno aspettato un ponte silenzioso finché anche l'ultima è vecchia: nessun rapporto, restano nello stato della nave |
| `a report was being written when the Captain took the floor: it waits` | il messaggio del nemico (o un altro lavoro prelazionabile) si stava scrivendo quando il Capitano ha parlato: si scrive dopo il suo ordine |
| `the game says line 12 is failed (no audio component)` | **il gioco non ha potuto riprodurre la riga** (`voice_status`): è il segnale di «il testo compare e nessuno parla» |
| `the game says line 12 is stalled` | la coda audio del gioco si è svuotata a riga non finita (scatto del gioco) |
| `the key has been down for 45 s: taken as released` | un `ptt up` è andato perso: l'equipaggio riprende a parlare |
| `the floor is released: no answer to the Captain came within 8 s` | il modello non ha risposto in tempo: i rapporti riprendono |
| `whisperkit is not ready yet: this phrase goes without it` | Whisper sta ancora compilando il suo modello: questa frase è andata solo a Parakeet |
| `TTS: 31 s of audio for 120 characters: stopped (the model did not find the end)` | la sintesi non trovava la fine della riga: tagliata (di norma mai) |
