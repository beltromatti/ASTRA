# 15 — MetalFX al posto di TSR (l'upscaler temporale per il Mac)

*Stato: studio di fattibilità + plugin `Plugins/AstraMetalFX` (ottobre 2026). Autore: modulo METALFX. Le prove di questo
documento si rifanno con `tools/metalfx_probe/` (programmi Objective-C++ fuori da Unreal: si compilano con
`tools/metalfx_probe/build.sh` e non toccano la GPU del gioco se non per pochi secondi).*

## 1. Perché

La prima critica dell'utente all'app è l'immagine: «bassa, pixelata». Sull'Air il 3D gira al ~50–55 % della risoluzione (la
risoluzione dinamica la porta lì per stare nei 60 fps, vedi `docs/STATO.md` «Prestazioni») e lo ricostruisce TSR, che costa
~2,9 ms a 1600×900 al 70 % (misura del lead, TSR contro TAA). MetalFX è l'upscaler temporale di Apple, scritto per questi chip:
a parità di costo dovrebbe dare più nitidezza e meno ghosting, o a parità di immagine costare meno. Il piano
([PIANO.md](../PIANO.md) §4.5) lo chiamava «un upscaler MetalFX nostro al posto di TSR (da studiare)».

## 2. Il contratto di Unreal 5.8

- Un upscaler di terze parti implementa `UE::Renderer::Private::ITemporalUpscaler`
  (`Engine/Source/Runtime/Renderer/Public/TemporalUpscaler.h`) e si installa **per ogni famiglia di viste** da una
  `FSceneViewExtensionBase::BeginRenderViewFamily` con `FSceneViewFamily::SetTemporalUpscalerInterface` (il motore lo
  impone: `SceneView.cpp` ha un `checkf` se è già messo altrove). Con l'interfaccia installata `GetMainTAAPassConfig` sceglie
  `EMainTAAPassConfig::ThirdParty` (se `r.TemporalAA.Upscaler` ≠ 0) e chiama `AddThirdPartyTemporalUpscalerPasses`
  (`PostProcessing.cpp`): **da lì non si torna a TSR dentro il frame**, quindi la scelta TSR/MetalFX va fatta prima, per vista, nel
  thread di gioco. Togliendo l'interfaccia il motore usa TSR come prima: è il nostro «fallback» e l'interruttore a caldo.
- Ingressi (`FInputs`): colore della scena post-DOF e pre-motion-blur (`SceneColor` con il suo `ViewRect`), profondità,
  velocità, `TemporalJitterPixels`, `PreExposure`, la texture di eye adaptation (1×1, l'esposizione del tonemapper in `x`) e
  la storia della frame precedente (`PrevHistory`, un oggetto nostro che il motore conserva nello stato della vista).
  Uscita: una texture alla `OutputViewRect` (origine 0,0; è il «secondary view rect»: la vista di gioco prima dell'upscale
  finale alla finestra, sul Retina la metà della finestra) e la nuova storia. **Non c'è un flag di reset**: si ricava
  (`FSceneView::bCameraCut`, `PrevHistory` nulla, cambio di dimensione, una frame renderizzata con TSR in mezzo, e un
  teletrasporto: il gioco non segnala mai i tagli di camera, quindi il plugin applica la stessa soglia che il motore usa per le
  sue storie, 75° o 100 m in un frame, `IsLargeCameraMovement` in `SceneVisibility.cpp`).
- Con un upscaler di terze parti le traslucenze «post-DOF» sono composte **prima** dell'upscaler (TSR le compone dopo, a piena
  risoluzione): vetri e ologrammi restano meno puliti. Limite da valutare nel gioco; MetalFX ha una *reactive mask* che per
  ora non sfruttiamo.
- La risoluzione dinamica chiede a ogni upscaler il suo intervallo (`GetMin/MaxUpsampleResolutionFraction`) e non esce da lì.
  I buffer di scena sono allocati al *limite alto* della risoluzione dinamica (`FSceneRenderer::GetDesiredInternalBufferSize`):
  con `MaxScreenPercentage=100` le texture sono grandi quanto l'uscita e il rettangolo disegnato ne è un angolo.

## 3. Il nodo: far girare MetalFX dentro il frame di Unreal

`MTLFXTemporalScaler` codifica il suo lavoro in un `MTLCommandBuffer` (`encodeToCommandBuffer:`), con le texture di Unreal, sul
timeline GPU di Unreal. Su D3D12/Vulkan i plugin DLSS/XeSS/FSR registrano nel command buffer del RHI
(`RHIGetGraphicsCommandList`, `RHIGetActiveVkCommandBuffer`). Su Metal, in 5.8, **non c'è**:

### 3.1 Opzione (a), il command buffer corrente del RHI: non raggiungibile da un plugin
- `IMetalDynamicRHI` (l'interfaccia pubblica) espone solo `RHIGetDevice`, `RHIRunOnQueue` e `RHICreateTexture2DFromCVMetalTexture`.
- `FRHICommandListBase::GetNativeCommandBuffer` / `IRHIComputeContext::RHIGetNativeCommandBuffer` sono **deprecate in 5.8** («i
  command buffer appartengono ai contesti RHI… usa le interfacce specifiche della piattaforma») e Metal non le implementa.
- `FMetalRHICommandContext` (con `GetCurrentCommandBuffer`, `EndComputeEncoder`, `SignalEvent`…) sta nell'header pubblico
  `MetalRHIContext.h`, ma **non è esportata**: `nm -gU libUnrealEditor-MetalRHI.dylib` elenca 98 simboli (solo `FMetalSurface`,
  `FMetalDynamicRHI::RHIGetNative*`, le vtable…), nessun metodo del contesto. Nell'editor e nel `-game` standalone (moduli
  dinamici) non si linka; solo nel pacchetto monolitico si potrebbe, e solo leggendo campi privati a offset fissi. Scartata.
- Anche potendo: per codificare MetalFX bisogna chiudere l'encoder corrente di Unreal (`EndEncoding`), che è stato interno del contesto.

### 3.2 Opzione (b), un command buffer separato sulla stessa coda, nell'ordine giusto: la via scelta
`IMetalDynamicRHI::RHIRunOnQueue(lambda, bWaitForSubmission)` accoda un *payload* senza command buffer con un
`PreExecuteCallback`; il thread di sottomissione di Metal (`RHISubmissionThread`) lo esegue **in ordine di payload**, tra il commit
dei command buffer dei payload precedenti e quelli dei successivi (`MetalSubmission.cpp`, `FlushBatchedPayloads`). Il callback
riceve la `MTLCommandQueue` di Unreal: lì creiamo il nostro command buffer, vi codifichiamo il kernel dei vettori di moto e lo
scaler, e lo committiamo. Serve solo che il payload arrivi **dopo** tutto ciò che Unreal ha registrato fin lì e **prima** di ciò
che registrerà dopo: il lavoro già tradotto dal RHI sta nel contesto, non ancora in un payload.

Lo schema che garantisce l'ordine è quello che il RHI Metal usa per il *present* (`MetalViewport.cpp`,
`RHIEndDrawingViewport`: «assicurati che tutto il lavoro precedente sia stato consegnato a RHISubmitCommandLists prima di
tradurre la lambda») e che il plugin NNE di Epic usa per eseguire ONNX/DirectML in mezzo a un frame
(`NNERuntimeORTModel.cpp`, «submit previous work here to the GPU»):

```
RDG pass (render thread):   RHICmdList.ImmediateFlush(DispatchToRHIThread);      // chiude la sottomissione corrente
                            RHICmdList.EnqueueLambda(... Submit ...);            // traduzione della sottomissione successiva
RHI thread, nella lambda:   IMetalDynamicRHI::RHIRunOnQueue(callback, false);    // payload accodato dietro a quelli di prima
Thread di sottomissione:    callback → MTLCommandBuffer nostro → commit          // tra i command buffer di Unreal
```
Perché l'ordine regge: `GRHIGlobals.SupportsConcurrentTranslateAndSubmit` è falso su Metal, quindi la traduzione di una
sottomissione aspetta la chiusura della precedente (`RHICommandList.cpp`, `Dispatch_ProcessCommandList`: prerequisito
`LastClose`, che scatta dopo `RHISubmitCommandLists`); la coda dei payload è FIFO. Il render thread non si blocca
(`DispatchToRHIThread`, non `FlushRHIThread`).

### 3.3 Ordine sulla GPU: nessun evento, basta il *hazard tracking* di Metal
Fra command buffer della stessa coda Metal non garantisce da sola che uno finisca prima che l'altro cominci (la GPU può
sovrapporli). Ma Unreal alloca tutte le sue texture da heap *placement* con `MTLHazardTrackingModeTracked`
(`MetalBuffer.cpp`: `HeapDesc->setHazardTrackingMode(Tracked)`; `MetalTexture.cpp`: `ResourceHazardTrackingModeTracked`
quando il dispositivo supporta gli heap, cioè sempre su Apple silicon): Metal ordina da sé lettura e scrittura delle stesse
texture fra command buffer, senza fence né eventi. **Provato** (`probe_hazard`): tre command buffer «produttore → scaler →
consumatore» per 200 frame senza alcuna sincronizzazione, con texture tracked (heap placement o no) **0 letture sbagliate**;
con texture untracked 285 milioni di texel sbagliati (il test discrimina). Il plugin controlla a ogni frame che le texture di
Unreal siano tracked (`MTLResource.hazardTrackingMode`) e, se un aggiornamento del motore lo cambiasse, si spegne e torna a TSR
invece di correre.

### 3.4 Costi e rischi del taglio
- Un command buffer in più e una sottomissione in più per frame (Metal RHI ne fa già una per il present). Nessuna attesa della CPU.
- Il lavoro di MetalFX **non compare nei tempi GPU di Unreal** (`stat gpu`, il tempo che usa la risoluzione dinamica): il RHI misura
  i *suoi* command buffer. La risoluzione dinamica vede quindi la GPU più libera di quanto sia, di quanto costa MetalFX
  (~1–2 ms): con MetalFX attivo conviene abbassare `r.DynamicRes.FrameTimeBudget` di quel tanto (il costo si legge con
  `astra.metalfx.status` o `stat AstraMetalFX`).
- Il callback gira sul thread di sottomissione di Metal: niente di lento lì (creare uno scaler costa 0,2–3 s: si fa prima, su un
  thread di lavoro; il callback tocca solo oggetti già pronti).
- Una texture di Unreal resta viva per MetalFX finché il suo command buffer non è finito: il plugin ne tiene un riferimento
  (Objective-C) fino al completion handler.

## 4. Cosa riceve e cosa vuole MetalFX (verificato con `tools/metalfx_probe`)

| Cosa | Unreal | MetalFX | Come |
|---|---|---|---|
| colore | `PF_FloatRGBA` (RGBA16F), rettangolo `ViewRect` | `colorTexture` RGBA16F, contenuto nell'angolo (0,0) | diretto; se `ViewRect.Min` ≠ 0 una copia blit |
| profondità | `PF_DepthStencil` = `Depth32Float_Stencil8`, **reversed Z** (1 vicino, 0 lontano) | qualunque formato di profondità va bene (accettato anche D32F_S8 nel descrittore) | diretta, `depthReversed = YES` |
| movimento | `Velocity`: RGBA16 UNORM codificato, **solo i pixel che disegnano velocità** (oggetti in moto, ossa); gli altri sono 0 | `motionTexture` RG16F: *pixel del rettangolo di ingresso, posizione precedente meno attuale, x a destra, y in giù* | kernel `astra_motion`: dinamici = decodifica della codifica di Unreal (`Common.ush`), statici = riproiezione della profondità con `ClipToPrevClip` come fa TSR |
| jitter | `TemporalJitterPixels` = spostamento dell'immagine in pixel (+x destra, +y giù) | `jitterOffsetX/Y` | **identico, senza cambiare segno** (provato con un PSNR contro la verità) |
| esposizione | colore × `PreExposure`; il tonemapper moltiplica per `Exposure` (eye adaptation `x`) | `preExposure` e `exposureTexture` (R16F 1×1) | `preExposure = View.PreExposure`; kernel `astra_exposure` copia `EyeAdaptation.x` |
| risoluzione dinamica | rettangolo che varia frame per frame dentro texture allocate al limite alto | `inputContentProperties`: fattore di scala = uscita / ingresso in **[1, 3]** (supportato da M4), `inputContentWidth/Height` per frame | scaler creato **per dimensione d'uscita** (ingresso massimo = uscita); `GetMin/MaxUpsampleResolutionFraction` = 1/3…1 |
| uscita | `FScreenPassTexture` alla `OutputViewRect` | `outputTexture` **Read+Write+RenderTarget**, privata | creata da RDG con `SRV|UAV|RenderTargetable` |

Esiti delle sonde (macchina: MacBook Air M4, macOS 26.6, Xcode 26.2, tutto con il layer di validazione Metal acceso dove indicato):
- `probe_create`: `supportsDevice` sì, `supportsMetal4FX` sì; scala supportata **[1,0, 3,0]**; creare uno scaler costa **200–600 ms** con la
  cache di sistema calda (la *prima volta in assoluto* su una macchina 1,8–3,2 s: compila le sue pipeline); `requiresSynchronousInitialization=YES`
  lo rende pronto subito (con NO torna in fretta ma va più lento finché compila). Da creare su un thread di lavoro.
- `probe_formats`: accettati a encode D32F_S8, R32F, R16F come profondità; RG16F/RG32F/RGBA16F come moto; RGBA16F/RGB10A2/RG11B10 come colore.
  **Un contenuto fuori dal range [1×, 3×] dell'uscita fa abortire MetalFX** («Actual content scale … is bigger than allowed max scale», asserzione dura con
  il layer di validazione, comportamento indefinito senza): il plugin restringe il rettangolo e i limiti della risoluzione dinamica lasciano un margine.
- `probe_quality` (scena analitica 2D con pan, verità supersampled, PSNR): jitter di Unreal tale e quale + moto «precedente − attuale» = migliore in ogni
  combinazione dei segni (27,6 dB contro 17–25 dB); moto col segno sbagliato 17 dB; senza moto 18 dB. La modalità `layout`: descrittore
  piccolo con texture grandi (come le alloca Unreal), descrittore uguale al rettangolo, descrittore uguale all'uscita: **stessa immagine** (27,6–27,7 dB).
- `probe_motion`: il kernel del plugin (lo stesso sorgente MSL che compila il plugin) contro la verità geometrica (camera che si sposta e gira, matrici con la
  convenzione a vettore-riga di Unreal e la formula di `ClipToPrevClip`, profondità in `Depth32Float_Stencil8`, un rettangolo di pixel dinamici con la codifica
  di Unreal a 16 bit, rettangolo non nell'angolo): errore massimo **0,017 px** sui pixel statici (movimenti fino a 40 px), 0,0016 px sui dinamici, esposizione giusta.
- `probe_e2e`: scena 3D (pavimento e parete con pattern ad alta frequenza), camera in moto, jitter di Unreal, profondità reversed-Z in D32F_S8, moto dal kernel:
  MetalFX **19,7–20,7 dB** contro 15,8–16,7 dB del solo bilinear del frame corrente; con moto nullo o invertito 15,6–16,2 dB (quindi il moto conta e il kernel lo dà giusto).
- `probe_core` (il codice vero del plugin, `AstraMetalFXCore.mm`, compilato nel programma di prova, senza Unreal): texture da un heap *placement tracked* con le flag d'uso di Unreal, più grandi del
  rettangolo, profondità `Depth32Float_Stencil8`, velocità UNORM, frame committati uno dietro l'altro **senza attese** (il command buffer di MetalFX in mezzo a quelli del «renderer»: solo il hazard tracking li ordina):
  19,74 dB (come `probe_e2e`), identico con texture più grandi, con il rettangolo che non parte dall'angolo (la copia) e con la risoluzione dinamica che cambia a ogni frame (20,05 dB);
  i frame sbagliati (colore senza tracking, formato, dimensione dell'uscita, uso mancante, rettangolo fuori) sono rifiutati con il motivo; rettangoli fuori scala vengono stretti (un avviso) invece di arrivare a MetalFX;
  **NaN, ±Inf e valori negativi nel colore non avvelenano l'uscita** (MetalFX li assorbe: 0 valori non finiti anche nel frame avvelenato, quindi nessun passo di pulizia); uno scaler fallito produce un'uscita nera;
  `probe_core soak 6000`: 6000 frame con rettangolo, offset, reset, velocità ed esposizione che cambiano, i tempi letti da un altro thread: 6000 completati, 0 errori, niente in volo alla fine.
- `probe_memory`: lo scaler tiene ~48 MB a 1600×900 e ~83 MB a 1710×1107 (vedi §5). `probe_hazard`: vedi §3.3.
- Controllo dei simboli del plugin compilato (`nm -u` contro gli export dei moduli del motore): ogni simbolo di Unreal che usa è esportato (non usa nulla di `MetalRHI` oltre alle chiamate virtuali
  di `IMetalDynamicRHI`); il resto sono libSystem, libc++, runtime Objective-C e i framework Metal/MetalFX (legati in modo debole).

## 5. Costo di MetalFX su questo Mac (M4 10 core)

`probe_cost`: il solo `encodeToCommandBuffer:` dello scaler (a cui il plugin aggiunge ~0,05–0,1 ms di kernel di preparazione: 0,075 ms a 640×360). Due misure
complementari, entrambe sulla GPU sotto carico continuo: «in un command buffer» = 30 scaler di fila nello stesso command buffer, tempo GPU / 30 (il costo
puro, con la GPU tenuta occupata); «uno dopo l'altro» = command buffer consecutivi, tempo di parete / frame (include il passaggio fra command buffer).
**Attenzione al rumore**: l'Air senza ventola cambia frequenza secondo lo stato termico e la macchina era condivisa (l'editor del lead sulla GPU, le
compilazioni degli altri agenti): un singolo command buffer oscilla fra 0,5 e 10+ ms, per questo i valori sono minimo–mediana di più serie.

| ingresso → uscita | scala | intervallo fra le serie (minimo dei «uno dopo l'altro» – mediana degli «in un command buffer») |
|---|---|---|
| 960×540 → 1600×900 | 60 % | 1,2 – 2,2 ms |
| 1120×630 → 1600×900 | 70 % | 1,5 – 2,2 ms |
| 1600×900 → 1600×900 | 100 % (come un TAA) | 2,0 – 2,6 ms |
| 960×540 o 1120×630 → 1710×1107 (proporzioni diverse dall'uscita) | | 2,1 – 2,6 ms |
| 855×554 → 1710×1107 | 50 % | 1,8 – 2,9 ms |
| 940×609 → 1710×1107 | 55 % | 1,8 – 2,3 ms |
| 1197×775 → 1710×1107 | 70 % | 2,1 – 2,6 ms |
| texture 1600×900 (come in Unreal), rettangolo 960×540 o 1120×630 | | 1,25 – 2,0 ms |
| texture 1712×1112, rettangolo 940×609 o 1197×775 → 1710×1107 | | 1,6 – 3,3 ms |

(due giri completi di misure a distanza di ore, con la macchina in stati termici diversi: lo stesso caso è passato da 1,4 a 2,2 ms.) Il costo dipende soprattutto dall'**uscita** (poco dalla scala): ~1,2–2,2 ms a 1600×900, ~1,8–2,9 ms a 1710×1107. Con il chip fresco e la GPU libera il singolo command buffer è sceso a 0,5–1,0 ms;
con la macchina tranquilla il plugin intero (kernel di moto + scaler) a 528×297 → 960×540 ha misurato 0,58 ms di media su 192 frame (`probe_core`). **Da aspettarsi ~1,5–2,5 ms** a 1600×900–1710×1107
sotto carico, da confrontare con i ~2,9 ms che il lead ha misurato per TSR contro TAA a 1600×900 al 70 % (il TAA stesso costa qualcosa, il TSR intero sta sui 3–3,5 ms):
un guadagno di ~1 ms e più, e un'immagine che `probe_e2e` dice migliore di un semplice filtro. Il costo della CPU del thread di sottomissione è ~25 µs per frame. Memoria (`probe_memory`, `device.currentAllocatedSize`): lo scaler tiene ~48 MB a 1600×900 e ~83 MB a 1710×1107
(157 MB a 2560×1440), più le texture del plugin (vettori di moto 7,6 MB e l'uscita 15 MB a 1710×1107): come la storia di TSR, che non viene più allocata.

## 6. Limiti e rischi noti
1. **Nessuna prova nel gioco vero** (agente senza editor): l'ordine dei command buffer, la correttezza dei vettori di moto nel gioco e l'immagine sono da verificare dal lead
   (vedi il rapporto finale e `r.AstraMetalFX.Debug`).
2. Le traslucenze sono composte prima dell'upscaler (§2); niente reactive mask né maschera dei pixel con animazione.
3. Il tempo GPU di MetalFX non entra nella misura della risoluzione dinamica (§3.4).
4. Una sola vista (niente split screen, niente scene capture: tengono TSR), colore RGBA16F (il formato di scena predefinito), nessun Windows (resta TSR).
5. Il layout di `FMetalRHICommandContext`, `MetalRHI` privato ecc. non sono usati: se Epic cambia `RHIRunOnQueue` o la sequenza `ImmediateFlush`+`EnqueueLambda` il plugin va riverificato
   a ogni aggiornamento del motore (UE 5.8.3 è fissato per il progetto).
6. Metal 4: lo scaler è quello classico su `MTLCommandBuffer` (il RHI di 5.8 non usa command buffer Metal 4).

## 7. Come si prova nel gioco (per il lead)

1. Compila con l'editor chiuso (`tools/ricompila.sh`, o `Build.sh ASTRAEditor Mac Development …`): il plugin è in `ASTRA.uproject` (solo Mac) e si compila con il progetto.
2. All'avvio il log dice `MetalFX upscaler ready`, poi `building the MetalFX scaler for an output of WxH` e `MetalFX scaler N ready` / `was built in X s`: per qualche secondo (la prima
   volta in assoluto sulla macchina 2–3 s, poi 0,2–0,6 s) la vista di gioco usa TSR, poi passa a MetalFX da sola. Se cambia la dimensione della finestra si ricostruisce (TSR nel frattempo).
3. `astra.metalfx.status` (console o `astra.cmd`): `ACTIVE` o il motivo per cui no, l'uscita, il tempo GPU dell'ultimo frame e la media. `stat AstraMetalFX` lo mostra a schermo (build Development).
   `r.AstraMetalFX.LogInterval 5` lo scrive nel log ogni 5 s.
4. **Confronto TSR / MetalFX**: `r.AstraMetalFX 0` e `1` a caldo (la storia ricomincia a ogni cambio; vale anche `r.TemporalAA.Upscaler 0`,
   l'interruttore del motore per gli upscaler di terze parti, che rimette TSR: il plugin lo riconosce). A parità di costo: fissa `r.DynamicRes.OperationMode 0` e lo stesso `r.ScreenPercentage`, leggi il tempo GPU
   totale (banco `tools/perf`/`stat gpu`) **più** il tempo di `stat AstraMetalFX` (il RHI non vede il command buffer di MetalFX, §3.4), poi alza il `r.ScreenPercentage` di MetalFX finché i totali pareggiano.
   Con la risoluzione dinamica accesa, abbassa `r.DynamicRes.FrameTimeBudget` del costo di MetalFX (o conta sul 10 % di margine `r.DynamicRes.TargetedGPUHeadRoomPercentage`, che è circa quello).
5. **Diagnosi**: `r.AstraMetalFX.Debug 1` mostra i vettori di moto (fermo e senza oggetti in moto: tutto scuro; girando la testa un colore uniforme per direzione; un oggetto in moto ha un colore suo);
   `2` colora di rosso i pixel che prendono il moto dal velocity buffer (gli altri lo prendono dalla camera). Se l'immagine ha fantasmi, scie o lampeggia: prima questi due, poi il log
   (`LogAstraMetalFX`: ogni errore e il motivo per cui è tornato a TSR), poi `r.AstraMetalFX 0`.
   Per vedere le asserzioni di MetalFX e di Metal (un contenuto fuori scala, una texture sbagliata) avvia il gioco con `MTL_DEBUG_LAYER=1` nell'ambiente.
6. **Messa a punto** (non fatta: serve l'occhio del lead): `r.Tonemapper.Sharpen` (0,6 compensa la morbidezza di TSR, con MetalFX può bastare meno); `r.ViewTextureMipBias.Offset`
   (−0,3 di base, che a 55 % dà un mip bias di −1,16: si può provare −0,5 per texture più nitide da ricostruire); `r.TemporalAASamples` (8 di base, scalato da Unreal con `1/scala²`: a 55 % sono 26 fasi di jitter).

## 8. File
- `Plugins/AstraMetalFX/` — `AstraMetalFX.uplugin`; `Source/AstraMetalFX/`: `AstraMetalFX.Build.cs`; `Public/AstraMetalFXModule.h` (stato e cvar documentati); `Private/`:
  `AstraMetalFXModule.cpp`, `AstraMetalFXManager.{h,cpp}` (cvar, contesto costruito su thread di lavoro, fallback, contatori), `AstraMetalFXViewExtension.{h,cpp}` (TSR o MetalFX per vista),
  `AstraMetalFXUpscaler.{h,cpp}` (l'`ITemporalUpscaler`, il pass RDG, la storia), `AstraMetalFXBridge.{h,mm}` (Unreal ↔ Metal: `GetNativeResource`, `RHIRunOnQueue`),
  `AstraMetalFXCore.{h,mm}` (tutto il Metal senza Unreal), `AstraMetalFXKernels.inl` (i kernel MSL).
- `tools/metalfx_probe/` — `build.sh`, `run_all.sh` (le verifiche che contano), le sonde: `probe_create`, `probe_cost`, `probe_formats`, `probe_quality`, `probe_hazard` (studio dell'API),
  `probe_motion`, `probe_e2e`, `probe_core` (il plugin contro la verità).

