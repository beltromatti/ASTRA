# STATO DEI LAVORI — ASTRA

*Questo file è la memoria operativa del progetto: lo aggiorno a ogni passo. Chi riprende il lavoro (io in una nuova sessione) parte da qui.*

**Ultimo aggiornamento:** 2026-09-28 · **Traguardo corrente:** M0 — Fondamenta (in corso)

## Credito AI (OpenRouter)
| Data | Credito totale | Speso | Note |
|---|---|---|---|
| 2026-09-28 | 10,00 $ | 0,00 $ | ricarica iniziale dell'utente |

Regola: sotto i 3 $ residui aggiungo una voce in RICHIESTE.md e riduco le spese AI non essenziali (benchmark, immagini).

## Preparazione (checklist dell'utente) — completata 2026-09-28
- [x] Chiavi nel `.env`: OpenRouter, Sketchfab, Blendkit (recuperata da me), Hugging Face, Freesound, api.data.gov — tutte verificate con chiamate reali.
- [x] DeepSeek diretto: **non usato** (scelta dell'utente) → DeepSeek V4.1 Flash via OpenRouter, doppio canale tra due provider (Fireworks + Together).
- [x] ElevenLabs: non usato per ora (voce locale).
- [x] GitHub: gh CLI autenticato via SSH come `beltromatti`.
- [x] Accessi nel browser integrato: Fab, Sketchfab, Blendkit, Hugging Face, Freesound, Mixamo, GitHub, OpenRouter.
- [x] Core Data MetaHuman installato (6 GB). Aggiornamenti automatici App Store spenti. Scrivania non sincronizzata con iCloud.
- [x] Permessi di controllo: Unreal Editor, Epic Games Launcher, Finder, schermo intero (per questa sessione).
- [x] Strumenti: git-lfs 3.8, uv 0.12, espeak-ng 1.52, Blender 5.2.2 LTS.

## M0 — Fondamenta
- [x] Cartella progetto `~/Desktop/ASTRA`, documenti spostati, `.env` protetto (gitignore + hook anti-segreti)
- [ ] Repository git + LFS, repo privato GitHub `beltromatti/ASTRA`, primo push
- [ ] Plugin Claude Code ufficiale Epic (skill Unreal)
- [ ] Progetto Unreal C++ ASTRA dal template First Person, configurato per M4 16 GB (SM6, niente RT hardware, pool di memoria, Lumen Lite, TSR)
- [ ] MCP ufficiale attivo + toolset `AgentPythonTools` (Python arbitrario) + client MCP da terminale; verifica con catture
- [ ] Guida di stile ASTRA + Bibbia di ASTRA (bozza)
- [ ] Benchmark modelli AI via OpenRouter (latenza dall'Italia, tool calling, italiano/multilingua) → scelta finale
- [ ] Servizio voce di base (Parakeet/WhisperKit + Pocket TTS + labiale) e prova end-to-end
- [ ] Test di prestazioni automatici (CsvProfile) con gate

## Prossimi passi
1. Git + GitHub, poi progetto Unreal.

## Registro decisioni
- 2026-09-28 — Progetto sulla Scrivania (richiesta utente); lavoro sempre su `main`.
- 2026-09-28 — Contenuti di terzi grezzi e MetaHuman generati esclusi da git (quota LFS gratuita 10 GiB); si riscaricano/rigenerano dagli script.
