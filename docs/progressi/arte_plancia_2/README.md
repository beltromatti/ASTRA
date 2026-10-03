# ARTE-PLANCIA-2: anteprime (2/10)

Rendering **Eevee** delle mesh generate da Blender (1600 x 900, 64–96 campioni), con i materiali dell'anteprima
(`art/blender/bridge3_preview.py`), il cielo stellato dell'anteprima e le luci del layout. **Non sono catture del gioco**: gli
schermi vivi (`SCREEN_*`) sono segnaposto e la luce di Unreal (Lumen) è un'altra. Il testo di accompagnamento è in
[../../PLANCIA.md](../../PLANCIA.md).

| Cartella | Comando (dalla radice del progetto) | Inquadrature |
|---|---|---|
| `bridge/` | `blender -b --factory-startup -P art/blender/bridge_v3.py -- --no-export --preview <cartella> --views … --samples 64` | `seated` (dal seggio del Capitano), `standing`, `deck_aft`, `back` (dal timone verso poppa), `aft_wall` (lo schermo generale), `port`, `starboard`, `helm_close`, `chair_close`, `well` (il tavolo), `ceiling`; `seated_active` e `standing_active` con `BRG3_VIEWSCREEN=on BRG3_HOLO=1` (immagine e tracciato segnaposto); `overview` e `plan` con `BRG3_NOCEILING=1` (spaccato: viste `overview` e `top_open`) |
| `cockpit/` | `… -P art/blender/cockpit.py -- --no-export --preview <cartella> --views … --samples 96` | `pilot` (dall'occhio, come in gioco), `pilot_low` (guardando in basso), `dash`, `dash_close`, `hood`, `left`, `right`, `throttle`, `sensors`, `knees`, `back` (il sedile), `up`, `outside` |
| `corridor/` | `… -P art/blender/kit_corridor.py -- --no-export --preview <cartella> --views … --samples 64` | `run` / `run_back` (12 m di corridoio con il modulo con la finestra al centro), `window`, `wall`, `wall_low`, `floor`, `ceiling`, `door` / `door_back` (la paratia con le ante), `cap` (parete di fondo), `doormod` (pannello), `doormod_door` (il modulo con la porta della sala riunioni: `KC_DOORMODULE=1`) |
| `quarters/` | `… -P art/blender/quarters_room.py -- --preview <cartella> --views … --samples 64` | `entry`, `sofa`, `desk`, `deskclose`, `bunk`, `bunkclose`, `galley`, `bookcase`, `sideboard`, `door`, `window`, `ceiling`, `hooks`, `seat` |

Variabili d'ambiente (esposizione, guadagno delle luci, dimensioni) nelle docstring dei generatori.
