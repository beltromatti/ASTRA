# Brief NAVE-2 (bozza del lead): tutti i ponti dell'Aquila, e che reggano

Base: NAVE (docs/NAVE.md): piano dei 12 ponti completo (2251 compartimenti), kit di 96 modelli, Ponte 4 a mano e Ponte 6 dal
programma (`ship_decks.plan_deck(coarse=False)`), `build_ship_interior.py` (lead), `UAstraShipPlan` nel gioco.

1. Stanze nuove del kit (linguaggio plancia v3, BIBBIA §6), per i programmi dei ponti:
   Ponte 2 CIC, briefing room, uffici, comunicazioni; Ponte 3 alloggi ufficiali, palestra; Ponte 5 laboratori, Transporter
   Room (sei pedane: servirà a F6), archivio sensori; Ponte 7 power control, sale macchine; Ponte 8 Armory, Marine Barracks,
   poligono, assault-shuttle bay (due Kestrel: servirà a F5); Ponte 9 officine del ponte di volo, control booth; Ponte 10
   stive e santabarbara; Ponte 11 officine, fabbricazione, damage control; Ponte 12 cunicoli di chiglia (scala a pioli già pronta).
   Priorità: 5, 8, 7, 9, 2, 3, 11, 10, 12, 1 (ready room).
2. Scala: tutti i ponti costruiti significano ~8000 moduli, ~1300 porte, ~3000 lampade. Serve:
   - istanze (ISM/HISM per mesh e per ponte) al posto degli attori statici per i moduli ripetuti;
   - le lampade come dati (posizione, colore, lumen nel piano) e un pool di ~8 luci vere spostate dove serve (oggi 487
     attori lampada per due ponti);
   - un sotto-livello per ponte caricato quando il Capitano è su quel ponte o su quelli accanto (level streaming), con
     l'ascensore che aspetta il caricamento; porte e segnaletica restano attori nel sotto-livello del loro ponte.
   Budget: memoria del gioco ≤ 9 GB, caricamento di un ponte < 1 s, nessun calo sotto 45 fps camminando.
3. Prove offline: `ship_checks.py` a 0 problemi, anteprime Eevee di ogni stanza nuova e dei ponti, budget di triangoli e di
   draw call per ponte calcolati. Il lead importa, cammina ogni ponte nel gioco e rimanda i difetti.
File: `art/blender/ship_*.py`, `data/ship/aquila_plan.json` (generato), `tools/ue_scripts/build_ship_interior.py` (streaming,
istanze), `Source/ASTRA/AstraShipPlan.*` solo se servono campi nuovi (dirlo), un eventuale `AstraZoneLights.*` nuovo.
Non toccare: la plancia, Mess, Medbay, Engineering, Flight Deck, Berths esistenti (restano dove sono).
