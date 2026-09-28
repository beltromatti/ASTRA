# ASTRA

Simulatore in prima persona: sei il capitano di una nave capitale viva, con un equipaggio guidato da modelli AI che parla la tua lingua, dentro un universo generato da un unico seed. Motore: Unreal Engine 5.8.3 (macOS, Apple Silicon).

- **Visione e architettura:** [docs/PIANO.md](docs/PIANO.md)
- **Stato dei lavori (sempre aggiornato):** [docs/STATO.md](docs/STATO.md)
- **Ricerche (14 report con le fonti):** [docs/ricerca/00-INDICE.md](docs/ricerca/00-INDICE.md)
- **Le tue idee:** [docs/IDEE.md](docs/IDEE.md) · **Cose che servono da te:** [docs/RICHIESTE.md](docs/RICHIESTE.md)
- **Registro licenze degli asset di terzi:** [docs/LICENZE.md](docs/LICENZE.md)

## Struttura
| Cartella | Contenuto |
|---|---|
| `/` (radice) | Progetto Unreal (`ASTRA.uproject`, `Config/`, `Content/`, `Source/`, `Plugins/`) |
| `docs/` | Piano, stato, ricerche, Bibbia di ASTRA, guida di stile, licenze |
| `mind/` | Servizio AI "astra-mind" (gateway dei modelli, agenti, Regista della guerra) |
| `voice/` | Servizio voce "astra-voice" (riconoscimento, sintesi, labiale) |
| `art/` | Pipeline artistica: script Blender, specifiche degli asset, sorgenti |
| `tools/` | Strumenti di sviluppo: controllo dell'editor, benchmark, test di prestazioni |

Le chiavi API stanno in `.env` (mai su git: vedi `.env.example`).
