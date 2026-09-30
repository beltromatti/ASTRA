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

Colla nel server (le sole righe di `server.py` toccate, elenco nel rapporto): `ptt`/`player_text` → `captain_begin/end/input` e poi `_captain_speaks()` del modulo dell'equipaggio (`agent.preempt()`: le chiamate al modello in corso si fermano; `voice.drop_low_priority()`; il gancio `voice.captain_speaks()`); `turn_worker` → `captain_turn_begin/end` attorno al turno del Capitano; `quiet_moments` → `voice.chatter`; la coda dei turni (`_TurnQueue`) mette l'ora d'arrivo agli eventi e il turno di evento passa a `voice.report_since` l'ora della notizia più recente; un avviso di pericolo (`_URGENT_EVENT`) non aspetta il ponte silenzioso; il messaggio che il nemico sta scrivendo (`enemy.respond` per una `transmission:`) si ferma appena il Capitano prende la parola (`voice.preemptible`) e si scrive dopo il suo ordine. Un rapporto tagliato dal Capitano lo ferma `agent.preempt()`.

`voice.captain_speaks()` è il gancio che il server chiama quando il Capitano comincia a parlare: chi parla si ferma (alla prossima pausa entro mezzo secondo, altrimenti una dissolvenza rapida) e le righe `LOW` in coda sono scartate; si può chiamare più volte e accanto a `captain_begin/captain_input` (una riga già in fase di stop resta com'è); con il tasto giù non fa altro, senza tasto prende anche il palco per la risposta, come un ordine scritto (che non ferma una risposta già in corso a un ordine precedente). Il palco accetta anche un motore di voce della prima versione (il cui `stream` è un generatore asincrono di PCM senza tono né arresto): i doppioni di prova di altri moduli continuano a funzionare.

## 6. Regolazioni (variabili d'ambiente)

| Variabile | Predefinito | Cosa fa |
|---|---|---|
| `ASTRA_TTS_SPEED` | 1.12 | velocità del parlato (1.0 = quella del modello; ±0,06 secondo il tono) |
| `ASTRA_TTS_LUFS` | −19 | volume di ogni voce |
| `ASTRA_TTS_PAUSE_MS` | 300 | pausa più lunga tenuta dentro una riga |
| `ASTRA_TTS_RESIDENT` | 2 | modelli di lingua tenuti in memoria (~430 MB l'uno) |
| `ASTRA_STT` | `parakeet` | motore provato per primo: `parakeet` (Neural Engine), `parakeet-onnx` (CPU), `whisperkit`, `faster-whisper` |
| `ASTRA_STT_MODEL` | `ultra` | modello Parakeet: `ultra`, `v3`, `redux` |
| `ASTRA_STT_BIN` | — | percorso dell'helper `astra-stt` |
| `ASTRA_SHERPA_MODEL` | `<modelli>/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8` | modello del Parakeet su CPU (`python -m astra_mind.stt --fetch-portable`) |
| `ASTRA_FW_MODEL` | `small` | modello di faster-whisper |
| `ASTRA_VOICE_MODELS` | `<home>/voice/models` | dove cercare i modelli di Whisper/Parakeet |
| `ASTRA_MIC` | `auto` | `always` (microfono sempre aperto), `ptt` (aperto solo a tasto premuto), `auto` |
| `ASTRA_VOICE_QOS` | 1 | priorità dei thread della voce (macOS) |

## 7. Come si prova (dalla cartella `mind/`)

```
uv run python -m bench.voice_units            # 84 controlli veloci (audio, nomi, lingua, riconoscitore con motori finti, regole del testo tagliato)
uv run python -m bench.voice_floor -v         # 30 scenari del palco con orologio virtuale (-v: la cronologia vista dal gioco)
uv run python -m bench.voice_replay -v        # 4 rifacimenti del test dal vivo del capo attraverso il server vero (agente, router, palco), modello e voci finti
uv run python -m bench.voice_pipeline stt --backends parakeet-ultra,whisperkit-baseline   # riconoscimento: WER e latenza, motori alternati clip per clip
uv run python -m bench.voice_pipeline live tts mic floor mem   # (più sezioni di seguito) dal tasto al testo, sintesi, microfono, palco con voce vera, memoria
uv run python -m bench.voice_pipeline report  # il rapporto in docs/bench/voce_<data>.md (dopo aver girato le sezioni)
uv run python -m bench.voice_e2e --lang it  # tutto il collegamento da capo a fondo: gioco finto, microfono finto che suona un ordine registrato, riconoscimento e voci
                                             # veri, palco vero, modello di linguaggio finto (nessuna chiamata di rete): dal rilascio del tasto al testo, alla prima parola
                                             # della risposta, dalla pressione all'officer che tace
uv run python -m astra_mind.stt               # quali motori di riconoscimento ci sono su questa macchina
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
| Windows / Linux / Mac senza il helper | Parakeet ONNX su CPU e faster-whisper | `uv sync --extra portable` e `uv run python -m astra_mind.stt --fetch-portable` (~490 MB) | — |

`tools/pacchetto.sh` copia `mind/` con `rsync`: la cartella di compilazione di Swift non deve finirci (900 MB); con `build.sh` com'è ora non si trova più dentro `mind/`, ma per le cartelle `.build` già esistenti conviene aggiungere `--exclude .build --exclude .swiftpm`.

## 9. Il riconoscimento del parlato, passo per passo (per chi lo tocca)

1. **Tasto giù** — `captain_begin()`: chi parla si ferma entro mezzo secondo. Il microfono (`audio_in.py`) tiene sempre gli ultimi 300 ms già ascoltati (pre-roll) e li consegna subito alla sessione di riconoscimento, poi ogni blocco da 20 ms. Se la periferica è una cuffia Bluetooth si apre il microfono del computer (la cuffia passerebbe alla qualità da telefono e il suono del gioco cala).
2. **Mentre il tasto è premuto** — circa ogni secondo la sessione (`RecognitionSession`) fa decodificare a Parakeet quello che è stato detto fin lì (una *bozza*: ~0,12 s per una frase di 5 s sul Neural Engine). Le bozze si fanno solo se il primo motore è veloce, è pronto e parla la lingua dell'ultimo ordine; non chiamano mai il secondo motore.
3. **Tasto su** — 100 ms di post-roll (l'ultimo suono deve uscire dai buffer del sistema). Se l'ultima bozza copre tutto il parlato è la risposta e il testo esce subito; se dopo la bozza c'è ancora parlato, una decodifica completa (~0,06–0,12 s). **Secondo parere**: la frase va anche a Whisper large-v3-turbo (WhisperKit, ~1,8 s) solo se Parakeet ha confidenza sotto `ESCALATE_CONF` (0,84) **e** nel testo non c'è nessuna parola che un ufficiale di plancia direbbe (è quello che Parakeet scrive per una lingua che non conosce: giapponese romanizzato con confidenza 0,63–0,80), oppure se la lingua dell'ultimo ordine non è tra le 25 europee. Sulle lingue europee Whisper non fa meglio di Parakeet (misurato: WER 17,2 % contro 14,0 % sulle stesse frasi pulite; peggio in inglese, italiano, spagnolo, olandese) e costa 1,8 s: mandargli tutte le frasi con confidenza sotto 0,86 avrebbe fatto attendere il 6 % delle frasi pulite, il 14 % delle rumorose e il 54 % di quelle in battaglia per un risultato peggiore; con la regola attuale attende lo 0,5 %, l'1 % e l'11 %. `_arbitrate` sceglie il testo (un secondo parere in una lingua che Parakeet non legge vince sempre).
4. **Silenzio tagliato** — prima e dopo il parlato (rilevatore a energia, 220 ms di margine): Whisper «sente» sottotitoli nel silenzio, e un tasto premuto per sbaglio non arriva mai a un motore.
5. **Nomi e lingua** — `voice_glossary.py` corregge i nomi del gioco (alias, somiglianza fonetica per i nomi lunghi, il nome dell'ufficiale a inizio frase, il nome «a pezzi» tipo *Janusgate*); `voice_lang.py` decide la lingua tra 26 candidate (le sette delle voci locali, più quelle per cui esiste una voce di sistema o che si parlano ai giochi) pesando testo, vocabolario di plancia, lingua detta dal motore e lingua dell'ordine precedente (un «Mi sentite?» resta italiano anche dopo tre ordini in inglese). Una lingua europea fuori dalle 26 (bulgaro, croato, lituano…) viene riconosciuta bene ma risposta nella candidata più vicina.
6. **`transcript`** al gioco e turno all'equipaggio; le risposte escono nella lingua del Capitano (`lang`).

Motori (`voice_stt_backends.py`, un'interfaccia sola: `start`, `transcribe`, `stop`): `ParakeetBackend` (helper Swift sul Neural Engine, Apple Silicon), `SherpaParakeetBackend` (lo stesso modello in ONNX su CPU: Windows, Linux, Mac senza helper), `WhisperKitBackend` (99 lingue, dice la lingua, accetta i nomi come suggerimento), `FasterWhisperBackend` (CPU, portabile). L'ordine di prova è quello: il primo che parte è il motore veloce, il secondo la riserva. `ASTRA_STT` cambia il primo.

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
