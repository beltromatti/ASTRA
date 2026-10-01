# Brief VFX (F2.4, bozza del lead): la guerra bella

Riferimenti: EVE Online (scala, luce), Star Wars Rogue One/Andor (dardi, esplosioni), Star Trek Picard/Discovery (fasci,
scudi). Budget sull'Air: effetti con un tetto di particelle e di luci (luci dinamiche solo per i lampi grandi, brevi).

Contratto di GUERRA (non cambiarlo, chiedere al lead): `ConsumeDeathEvents` (reattore, rottura con sezione, asse e punto,
relitto disattivato), `GetDamageView` per nave (scudi per faccia con `ShieldFlash`, sezioni sventrate/in fiamme/squarciate,
`LastHitLocal`, sistemi, affusti), proiettili e raggi della simulazione (tipi: rotaie, laser/dardi, missili, siluri, PD).

1. Armi: dardi luminosi allungati (turbolaser), fasci con bagliore e calore sul bersaglio, traccianti delle rotaie,
   siluri con scia, difesa di punto (flak/traccianti). Istanze (ISM/Niagara GPU), niente attore per proiettile.
2. Scudi: esagoni che si accendono nel punto d'impatto sul settore colpito, colore per fazione, cedimento visibile a zero.
3. Esplosioni a strati: lampo, palla di fuoco, onda d'urto, detriti, fumo, scintille; secondarie nelle sezioni in fiamme.
4. Rotture: nascondere la nave intera, mettere i tre pezzi v3 (`/Game/ASTRA/Ships/Sections/*_Sec<Bow|Mid|Stern>`) nello
   stesso riferimento, impulsi dal punto di rottura, facce di taglio `MI_HULL_<f>_Cut` con `Heat` 1→0 in ~60 s, incendi e
   detriti; relitto disattivato che deriva con le luci spente.
5. Danni sugli scafi: decalcomanie `MI_ShipDamage_*` dove colpiscono i colpi veri (`LastHitLocal`), che si accumulano con un tetto.
6. Motori: pennacchi e bagliore che seguono la spinta vera.
7. Nomi e numeri per nave: oggi l'Aquila ha un nome "decal" della v2 e Praetorian/Vigilant hanno nome e numero nella
   geometria (sbagliati per le navi gemelle). Il generatore v3 esporta invece gli ancoraggi delle scritte (posizione,
   normale, altezza, lunghezza massima) e il gioco dipinge nome e numero di ogni nave lì (render target, `UAstraHullName`).
Prove: l'agente non avvia il gioco; prepara scene di prova e comandi (`astra.fx.*`) che il lead lancia e fotografa.
8. Ciò che si vede dai finestroni della plancia (la vista esterna più guardata del gioco): il tetto dell'isola sotto le finestre è
   un ventaglio di pelle liscio (ship3_astra.py, island(): `g.add(... kind="skin")`) — va pannellato a filo (niente sopra
   ISLAND_TOP + 0,2: la keep_out davanti alla finestra), con giunti, portelli, sfiati, lampade, scritte di servizio, passerelle.
