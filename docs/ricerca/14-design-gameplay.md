# Research 14 — Game design: bridge command, combat, damage control, diegetic UI (2026-09-27)

## 1. Lessons per game
| Game | Take | Avoid |
|---|---|---|
| **Artemis** (→ Artemis Cosmos 1.0, Nov 2024) | captain has **no controls**, commands through crew; crew puts requested view on main screen; engineering pushes systems to 300% at heat/coolant cost; DC teams walk corridors (manual or auto) | needs 3–8 people |
| **EmptyEpsilon** | open-source Artemis-like; Game Master screen; Lua scenarios; repair crews must reach system rooms through doors | abstract 2D damage |
| **Space Nerds in Space** | drive a DC robot inside the ship; natural-language command pipe | hobby scale |
| **Star Trek: Bridge Crew** | solo captain orders AI crew via menu or IBM Watson voice | Watson missed ship names/wordings; **players expected NPC initiative; nobody wants to repeat orders in a crisis**; cloud dependency |
| **Pulsar: Lost Colony** | engineer's reactor/heat loop | weak bots; "useless" Scientist role |
| **Void Crew** | big levers/buttons; breakers trip on overload; hand-placed hull patches | content exhausted ~20 h |
| **Jump Space** (EA Sep 2025) | seamless station switching, on-foot, boarding | repetitive missions |
| **Starship Simulator** (UE5) | 200+ rooms/7 decks/200+ NPC crew | EA slipped to "TBA" → **scope warning** |
| **Space Engineers 2** | airtight compartments, structural destruction | block damage costly |
| **Barotrauma** | room/opening graph carrying water & air; overloaded junction boxes start fires; fight fire by sealing + cutting oxygen | licence forbids code reuse |
| **FTL** | goal "Captain Picard yelling at engineers to get shields back online"; power bars, fires, breaches, O₂, venting | pause micro, permadeath |
| **Highfleet** | active radar reveals you to ELINT; narrow 60° sweep; radio interception/encryption; detection alarm | — |
| **Nebulous: Fleet Command** | radar-equation EW (jamming burn-through), passive bearing cross-fix, fading decoys, DC teams compartment by compartment (CIC & reactor first), armor not repairable in battle | top-down, experts only |
| **Children of a Dead Earth** | missiles long range, guns 10s–100s km, lasers short; "computers aim; humans choose priorities" | decisions mostly pre-battle |
| **Homeworld 3** | zoom-out sensors; persistent fleet losses | "Mostly Negative"; support ended |
| **Starfield** | walkable modular interiors, power allocation, boarding | loading screens; interiors barely matter in combat (UNVERIFIED) |
| **Carrier Command 2** | first-person bridge, jump into any unit, supply lines — closest precedent to commanding + flying yourself | — |
| **Star Citizen 4.5** (Dec 2025) | engineering terminal with 3D schematic, fuses/relays, per-room O₂/temperature, spreading fire, venting | small low-contrast UI text complaints |
EmptyEpsilon detail: C++ on SeriousProton (MIT); **EE itself GPL-2.0**; `src`, `scripts` (Lua scenarios & ship templates), `resources`, `script_docs`; ship templates declare rooms, doors, system placement; crews path through them ("no door → can't repair"); power up to 300% per system with heat; shared coolant budget (default 10); ECS rewrite in pre-releases (EE-2026.09.22PR; stable EE-2024.12.08). **Borrow ideas (room graph, station split, GM tools), not code.**

## 2. Combat model
Principle: **computers aim, the captain sets priorities**; orders state intent (mission command).
Decision windows: <5 s automated/crew (PD, jinks); **5–60 s captain** (salvo timing, armor facing, shield facing, emissions); minutes operational (formation, approach, squadrons). Voice→LLM→sim chain must fit well within the 5 s floor.
Engagement bands (starting values, tunable):
| Layer | Range | Time | Notes |
|---|---|---|---|
| Passive detection | whole system | light-lag 8.3 min/AU | no true stealth (cold ship ~40M km, burning drive much farther) |
| Missiles/torpedoes | 200–2,000 km | 30–180 s | saturate PD; decoys & jamming |
| Railguns/coilguns | 10–300 km | 1–30 s @~10 km/s | dodge ≈ ½·a·t² (1 g, 10 s ≈ 490 m ≈ hull length) → hit chance from range × target maneuvering |
| Lasers | 1–50 km | instant | spread with distance; good vs radiators/sensors/PD/fighters; weak vs thick armor |
| Point defense | 0.5–5 km | <5 s | CIWS reach ~5 km, kills ~500 m |
Sensors/EW: fog = uncertain identity & track quality; signatures (heat, drive plume, emissions, RCS); ladder detected → tracked → classified → identified → weapons-grade lock; EMCON silent/restricted/full; noise jamming loses at close range (radar ∝ d⁴, jam ∝ d²); passive = bearing lines until cross-fix; decoys fade ~40–45 s; planets/rings/stations/star glare block LOS.
Layered defense: fighters/drones → interceptors → PD → shields per facing (power-hungry; strong vs energy, weaker vs heavy slugs; absorbing hits makes heat) → armor per section (lasers ablate slowly; kinetics punch through to compartments) → compartments.
Expanse realism: PD fires short bursts correcting for recoil; **lights dim when railguns charge** (diegetic power draw); crews suit up & depressurize before battle.
Power & heat: reactor → lines → capacitors; every MW → heat → radiators (deployable, vulnerable, bright on IR) or limited heat sinks (silent running/bursts); "battle short" trades safety for output.
Maneuvering: real momentum under flight computer; helm vocabulary ("come to 045 mark 10", "flip and burn", "present port broadside", "match velocity"); **inertial compensator limits → injuries & flying objects** (ties helm to damage control); fighters flight-assist default, decoupled optional.
Fleet & carrier: picket drones extend sensors; PD escorts overlap; formation presets; allied captains take intent-level orders; separate launch tubes & recovery bay; rearm/refuel turnaround; squadron tasks (CAP, strike, escort, SAR, EW); if captain flies, First Officer commands.

## 3. Damage control
- Compartment graph: volume, pressure, O₂, temperature, smoke, fire, radiation, power, gravity, occupants; edges = doors, hatches, vents, ducts, breaches, containment fields (area + state); simulate per compartment, VFX on top. SS14 atmos rules: intuitive ("gas flows high → low pressure"), "theatrical performance" of danger.
- Venting time constant ≈ Volume ÷ (200 × Cd × hole area) s (Cd ~0.6–1). 500 m³ room: 1 m² → ~3–4 s (explosive); 10×10 cm → ~4–7 min (urgent); 1 cm² → hours (slow leak). Breach size = urgency.
- Fire: fuel + O₂ + heat; spreads via open doors & heat through bulkheads; smoke blinds/poisons; fight with crews/suppressant or venting (kills anyone inside).
- Doors: US Navy material conditions (XRAY/YOKE/ZEBRA); battle stations auto-seals max; closed fittings open only with DC Central permission (slower teams); auto-close on pressure differential + manual override; captain can seal a compartment with crew inside; optional pre-battle depressurization doctrine.
- Containment fields: powered patches over breaches/reactor; load-shedding priority list.
- Repair jobs: captain sets priority tiers, DCO schedules; teams walk the graph with hazard gear; field repairs partial; destroyed parts need spares; full repair only in drydock; damage persists between battles.
- Casualties: START triage (immediate/delayed/minor/expectant); med bay capacity; stretcher teams; hard calls.
- Morale & fatigue (UBOAT-like watch rotation/needs) → performance and LLM dialogue tone.
- Thrill: audio muffles as pressure drops, vacuum = suit-borne sound only, hull groans, distinct alarm per hazard; lighting by alert condition, emergency strips, flicker on power loss; wind toward breaches, flying debris, zero-g when gravity plating fails; captain's walks rare & decisive, leaving the bridge costs something.

## 4. Diegetic UI rules
1. Every datum has a place (console, holo table, wrist device, crew callout, alarm).
2. Three reading distances (room/glance/operating); one button frames the focused console (Alien: Isolation focus blur).
3. Text ≥18 px (PC/VR) / 26 px (console) at 1080p in focused view, scalable to 200% (Xbox AG 101).
4. Holo table: elevation lines, range rings, uncertainty ellipses, bearing-only lines, track-quality styling, contact age (light-lag).
5. **Closed-loop voice orders:** order → crew read-back → "executing" → "complete" / "unable, <reason>"; read-back generated from the parsed command (= exactly what sim will do); ask back when ASR unsure; mirror orders on a command-log screen; always offer radial menu/typed alternative (speech never required).
6. Accessibility > diegesis: optional subtitles with speaker name, "(comms)" tag, direction arrow; ≤2 lines × ~40 chars; adjustable background (Xbox AG 104).
7. Never color alone (shape/pattern/blink/sound; palette presets).
8. Wrist/suit device (RIG/mobiGlas) for vitals, O₂, First Officer comms away from bridge.
9. Large readable physical controls; crisp military UI (not horror clunk).

## 5. Captain loop & failure states
- Minute-to-minute: sense → decide → order (voice, intent) → monitor → step in (helm/weapons/fighter/walk to crisis). Scarce resources: attention & presence.
- Delegation per department: manual / advise / auto; **standing orders** (ROE, PD autonomy, repair priorities) → crew initiative (fixes Bridge Crew's main complaint).
- Pacing: L4D-style director (build-up → peak → fade → relax) scaled to minutes; quiet stretches host repairs, triage, conversations, strategy.
- Failure: abandon-ship sequence (who reaches pods; scuttle/ram/hold) → **Rescued** (board of inquiry replays ship's log & crew testimony → new ship or demotion) / **Captured** (POW arc) / **Adrift** (survival); war continues on a losing branch you can claw back (Wing Commander); optional ironman.
- Between battles: limited drydock time, crew arcs remembered by LLM crew, green replacements, refits, promotions (ship → squadron → task force).
- Onboarding: AI First Officer runs drills, recommends ("Recommend shields to forward"), "Make it so" accepts; help fades as you improve.
- Difficulty: separate sliders (enemy skill, automation, realism aids, Director personality).

## 6. Pillars, core loop, systems
Pillars: (1) Command through people; (2) The ship is a place; (3) Readable realism; (4) Any seat, not every seat; (5) A war that remembers.
Core loop: seconds (callout → order → read-back → effect); minutes (detect → posture → engage → absorb → break off); mission (holo briefing → transit/jump → battle → aftermath); campaign (Director phase → front choice → refit/promotion/crew arcs).
Systems: power & heat; movement (main drive, RCS, jump drive); sensors (passive/active, EW, EMCON); weapons (missiles, rail/coilguns, lasers, PD); protection (shields, armor); survival (life support, compartment graph, doors, containment, gravity, DC jobs, triage); crew (skills, needs, morale, fatigue); flight ops & logistics (ammo, spares, fuel); comms & jamming; AI crew (LLM language, deterministic truth, utility AI initiative); War Director (fronts, supply lines, jump gate) with API doubling as a human **Game Master** tool (EmptyEpsilon, Artemis, Thorium).

## 7. Open source to study
| Project | Licence | Study | Reuse code? |
|---|---|---|---|
| EmptyEpsilon | GPL-2.0 | stations, power/heat/coolant, room graph, Lua, GM | ideas only |
| SeriousProton | MIT | EE engine | low value |
| Space Nerds in Space | GPL-2.0 | DC robot, speech command pipe | ideas only |
| Thorium | Apache-2.0 | human Flight Director tooling | yes |
| Space Station 14 | MIT code (assets mostly CC-BY-SA 3.0, some NC) | atmos, fire, decompression, medical | yes (C#) |
| FreeSpace 2 Open | original NC; post-2020 Unlicense | capital subsystem targeting, turret AI | study only |
| Barotrauma | source-available EULA | design via wiki | no |
Docs: Atomic Rockets (detection), CoaDE blog (weapons), Nebulous EW wiki, US Navy DC manual ch. 12, Xbox & Game Accessibility Guidelines, Valve L4D AI Director talk.

## Sources
EmptyEpsilon (GitHub, docs, releases, ECS wiki, script reference), SeriousProton, Artemis (Wikipedia, engineering wiki, Steam guide), Artemis Cosmos Steam, Road to VR & Ubisoft (Bridge Crew Watson), Pulsar (Wikipedia, Steam discussion), Void Crew (Yahoo review, wiki), Jump Space (Game8), Starship Simulator (Steam, MassivelyOP), Space Engineers 2 (Steam), Barotrauma (Wikipedia, junction box wiki, EULA), FTL (Wikipedia, GDC 1018034), Highfleet (Steam guide), Nebulous (EW & damage control wikis), CoaDE (Steam, blog posts), Atomic Rockets detection, The Expanse CQB & recap articles, Homeworld 3, Starfield, Carrier Command 2 (Steam), Star Citizen (engineering wiki, 4.5 news, UI readability thread), Alien: Isolation (Steam, HUDs&GUIs, Medium analysis), Dead Space UI (Game Developer), GDC 1017723, US Navy material conditions & DC manual ch. 12, START triage, Space Station 14 (atmos docs, GitHub, progress report 24), Game Accessibility Guidelines, Xbox AG 101/104, L4D AI Director (Booth 2009), RimWorld storytellers, Wing Commander, CIWS, angled flight deck, closed-loop communication, mission-type tactics, battleshort, Elite Dangerous, Space Nerds in Space, Thorium, FS2 Open licence.
