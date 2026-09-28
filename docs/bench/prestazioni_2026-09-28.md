# Prestazioni — primo livello di prova (L_CorridorTest), 2026-09-28

Macchina: MacBook Air M4 (GPU 10 core), 16 GB. Gioco standalone (`-game`, binari dell'editor, non "cotto"),
1920×1080 finestra, VSync spento, 1500 fotogrammi registrati col profiler CSV (analizzati gli ultimi 900).
Strumento: `tools/perf/run_perf.sh` + `tools/perf/csv_summary.py`. Macchina non ancora "a caldo" (10 min): i numeri a caldo saranno più bassi.

| Configurazione | fps mediani | fps (fotogramma p95) | GPU mediana | Voci GPU principali |
|---|---|---|---|---|
| Epic, risoluzione 100%, Lumen alto | 29,1 | 27,1 | 34,0 ms | Luci 10,1 · Lumen screen probe 6,5 · ombre 2,1 |
| Profilo A via comandi (Lumen Lite, ombre Q2, TSR 62%) | 56,9 | 52,0 | 17,5 ms | illuminazione traslucidi 3,1 · luci 1,4 |
| **Profilo A predefinito del progetto** (+ niente volume di illuminazione dei traslucidi) | **58,4** | **52,9** | **17,1 ms** | luci 4,5 · non attribuito 4,3 · ombre 1,9 · Nanite 1,0 · Lumen 0,9 |

Scelte fissate nel progetto:
- `Config/DefaultGameUserSettings.ini`: sg.ResolutionQuality 62, ombre 2, GI 1 e riflessi 1 (Lumen Lite), il resto 3.
- `Config/DefaultDeviceProfiles.ini` (Mac): `r.TranslucencyLightingVolume=0` (i nostri vetri usano l'illuminazione per pixel).

Prossimi margini se servono: campioni SMRT delle luci locali, ombre solo sulle luci vicine, luci senza ombre per le strisce lontane.
