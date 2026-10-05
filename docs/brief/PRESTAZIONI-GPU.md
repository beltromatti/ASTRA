# Brief PRESTAZIONI-GPU (del lead): un'immagine nitida e un ritmo fermo in battaglia, sull'Air

Obiettivi (CLAUDE.md, docs/ricerca/11): MacBook Air M4 16 GB, senza ventola; 60 fps nello spazio, ≥ 45 negli interni a caldo; il gioco
≤ 9 GB. L'utente gioca con le sue impostazioni: 30 fps, «Retina» acceso (l'uscita a 3420×2214), qualità 2, pavimento dell'immagine 33 %.

## Che cosa ho misurato (il lead, 5/10, gioco di prova dall'editor in finestra 1600×900, macchina con altre compilazioni in corso)
- **In battaglia (`-astra_decisive`) la risoluzione dinamica sta al pavimento**: 33–36 % a 60 fps di obiettivo, GPU 12–16 ms, render
  thread 16–80 ms (molto rumoroso), 46–50 fps. A 30 fps di obiettivo sale all'80–90 %.
- **Fotogrammi a blocchi con MetalFX** (`r.AstraMetalFX 1`, il predefinito): dopo un lampo forte (un reattore che salta a 5 km), con
  la ruota degli ordini aperta, in battaglia. Misura sui fotogrammi della plancia (quota dei passi orizzontali piatti fra pixel vicini):
  MetalFX 0,34–0,39, TSR 0,22–0,23 nella stessa scena; a occhio i bordi della finestra a gradini e scie fantasma, con TSR nitidi
  (`Saved/Play/ex4.png` contro `tx4.png`, `ab_1_3.png` contro `ab_0_3.png`, `fx2.png`, `wheel1.png`, `gatelive.png`). Il registro
  del plugin dice spesso «encoding a MetalFX frame took 5–7 ms on the Metal submission thread», a volte 100+ ms.
- Il confronto delle prestazioni MetalFX/TSR a 1600×900 è dentro il rumore; **a 3420×2214 (lo schermo dell'utente) non l'ho misurato**
  (aprire il gioco a tutto schermo mentre l'utente usa il Mac non si fa; il pacchetto non avanza se la sua finestra non è visibile).

## Che cosa deve diventare vero
1. Nessun fotogramma a blocchi: capisci perché MetalFX li fa (la storia scartata dopo un salto di luminosità? l'esposizione passata allo
   scaler, `preExposure`, `EyeAdaptation`? i vettori di moto delle cose traslucide e degli effetti? il getto della dinamica di risoluzione?)
   e correggi; oppure, misure alla mano anche all'uscita Retina, scegli TSR come predefinito. MetalFX resta un'opzione solo se vince davvero.
2. I costi principali di una battaglia dalla plancia, misurati (Unreal Insights, `stat gpu`, `ProfileGPU`, A/B alternati sulla stessa scena):
   Lumen (GI e riflessi), ombre virtuali, traslucenze (tavolo olografico, pannelli sospesi, effetti della guerra), la telecamera dello schermo
   principale (una seconda vista), Nanite, il pianeta; e tagliati dove l'occhio non vede differenza. Ogni scelta con la sua misura.
3. Un pavimento d'immagine che regge: in battaglia ≥ 50 % a 60 fps nel gioco di prova 1600×900, e la stessa qualità percepita alle
   impostazioni dell'utente. Il render thread senza picchi (quel 16–80 ms va capito: è la GPU che aspetta, la sottomissione di MetalFX,
   o il gioco?).

## Prove
Il gioco di prova (`tools/play.py launch --nomind --args="-astra_decisive"`, `tools/play.py perf`, `cmd`, `shot`) quando il lead non ne
ha uno aperto (una partita alla volta: usa un'altra porta con `ASTRA_HARNESS_PORT` e dillo prima al lead); `astra.metalfx.status`,
`astra.war.perf`, `astra.fx.stats`. Misure su macchina tranquilla (niente compilazioni degli altri: chiedile al lead), alternate, ripetute.

## File tuoi
`Config/Mac/MacEngine.ini` e gli altri `.ini` di resa, `Plugins/AstraMetalFX/`, `Source/ASTRA/AstraSettings.*` (la pagina delle
impostazioni e i pavimenti), i materiali solo dove una misura lo chiede (con il loro proprietario), docs/ricerca/11 e 15, docs/STATO.md
§ «Prestazioni» (la tabella delle misure).
