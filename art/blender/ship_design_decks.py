"""ASN Aquila — the schedules of the decks (NAVE-3): see ship_design.py. Registers one function per deck in ship_design.DESIGNS. Decks 2-7 are here, 8-12 in ship_design_decks2.py.

How to read a schedule. A deck is its passages (the Spine, the Starboard and Port Passages) and the lanes of rooms along their walls (`inner` lanes: between the Spine and a
passage, 16 m deep; `outer` lanes: beyond a passage, 16 m deep, to the hull). The lifts, stairs and Jefferies arms are already in the lanes (ship_design.apply_structure). A
schedule says, lane by lane and section by section from the bow, which rooms stand there, in order; the packer lays them out, round the fixed items, and fills what is left with
the fillers of the section. A room is a prefab key (ship_spec); `key*N` repeats it; `key:Name_Of_It` renames a room's compartment (the game says "DECK 4 · SECTION D · ...");
`key?` is a room the section would like if there is room for it (it is dropped, without an error, when the section's free stretches are too short for it); `pool` first in a
section lays its rooms wherever they fit best (an industrial zone: nothing in a pool is an error); `gap:N` leaves N metres empty. What the packer cannot fill is left empty on
purpose: a void is a reserve volume, as in a real hull, and costs nothing to build.
"""
from __future__ import annotations

import ship_design as DS
from ship_catalog import GATE_H, GATE_W, MOD
from ship_layout import DesignError


def S(text: str) -> list:
    """A schedule text -> the packer's items: 'lounge bar*2 gap:4 laundry' -> [('lounge',), ('bar',), ('bar',), ('gap', 4), ('laundry',)]; 'key:Some name' renames."""
    out = []
    for tok in text.split():
        if tok == "pool":                                       # the section's items are laid wherever they fit best (an industrial zone)
            out.append(("pool",))
            continue
        optional = tok.endswith("?")                            # 'key?': laid if it fits, dropped (not an error) if it does not
        name, _, rest = tok.rstrip("?").partition(":")
        n = 1
        if "*" in name:
            name, _, k = name.partition("*")
            n = int(k)
        for _ in range(n):
            if name == "gap":
                out.append(("gap", float(rest)))
            elif rest or optional:
                opt = {"name": rest.replace("_", " ")} if rest else {}
                if optional:
                    opt["optional"] = True
                out.append((name, opt))
            else:
                out.append((name,))
    return out


COLLECT: list | None = None            # a design session (not the generator) sets a list here: a lane that does not fit is noted and the next one goes on, to see them all at once


def lane(D, pid: str, side: int, sections: dict, fill=None) -> None:
    try:
        D.flow(pid, side, {k: S(v) for k, v in sections.items()}, fill)
    except DesignError as e:
        if COLLECT is None:
            raise
        COLLECT.append(str(e))


def pieces(D, prefix: str = "SP"):
    """The Spine pieces of a deck (or the passages of another family), from the bow."""
    return sorted((p for p in D.passages.values() if p.along == "x" and p.pid.startswith(prefix)), key=lambda p: -p.a1)


# ===================================================================================================================================================== Deck 2
def deck2(D) -> None:
    """CIC & Communications, in the block (the island's base forward of x -60 is only 33 m wide: the inner lanes take rooms 12 m deep there). A: the senior officers' country (the
    suites). B: the CIC, a short walk from the bridge lifts, with the briefing room and the communications centre beside it. C: communications and intelligence. D-G: fire control
    and the weapons' spaces under the turrets (point-defence control, barbettes, the VLS magazines, the sensor rooms). H: the Auxiliary Control, the ship's second command centre,
    at the far end of the ship from the bridge. The outer strips (the block is 56 m wide, the lanes do not reach the hull) hold the watch officers' cabins by the CIC and by the
    Auxiliary Control, 4 m deep, along the passages."""
    sp = pieces(D)[0]
    FILL = ["records", "store_s", "tech_s"]
    lane(D, sp.pid, +1, {"A": "suites suites suites",
                         "B": "records cic",
                         "C": "offices:Operations_Office records offices:Intelligence_Office sensor_room:Signals_Intelligence",
                         "D": "store_s point_defense:Point-Defence_Control barbette",
                         "E": "offices:Fire-Control_Office barbette records",
                         "F": "vls_magazine point_defense sensor_room",
                         "G": "sensor_room:Aft_Sensor_Room point_defense",
                         "H": "records comms_center:Auxiliary_Control"}, FILL)
    lane(D, sp.pid, -1, {"A": "suites suites suites",
                         "B": "briefing comms_center:Communications_Centre",
                         "C": "comms_center:Fleet_Communications briefing:War_Room offices:Admin_Office",
                         "D": "tech_s point_defense:Point-Defence_Control vls_magazine",
                         "E": "barbette sensor_room records",
                         "F": "barbette vls_magazine",
                         "G": "point_defense sensor_room",
                         "H": "briefing:Auxiliary_Briefing_Room point_defense"}, FILL)
    lane(D, "SB0", +1, {"C": "single_cabins:Watch_Officers'_Cabins", "H": "single_cabins:Duty_Officers'_Cabins?"})
    lane(D, "PO0", -1, {"C": "single_cabins:Watch_Officers'_Cabins", "H": "single_cabins:Duty_Officers'_Cabins?"})


# ===================================================================================================================================================== Deck 3
def deck3(D) -> None:
    """Crew Country: the officers. A (forward): the wardroom, the officers' lounge and library, the gym. B: the executive officer's staff and staterooms. C-H (aft of the Mess
    and the Berthing, whose roofs reach into this deck's plane): the department heads' offices, the training classrooms, and the engineering and flight officers' staterooms with
    their heads and laundries at the nodes; the single cabins along the passages of the middle."""
    sp = pieces(D)
    fwd, aft = sp[0], sp[1]
    FILL = ["store_s", "locker_s", "tech_s"]
    lane(D, fwd.pid, +1, {"A": "wardroom lounge:Officers'_Lounge library:Officers'_Library", "B": "heads gym:Officers'_Gym offices:Executive_Officer's_Office?"}, FILL)
    lane(D, fwd.pid, -1, {"A": "staterooms staterooms quiet:Officers'_Quiet_Room", "B": "offices:Personnel_Office staterooms"}, FILL)
    lane(D, aft.pid, +1, {"C": "staterooms heads", "D": "offices:Department_Heads'_Offices laundry", "E": "staterooms offices:Supply_Office", "F": "heads briefing:Training_Classroom_1",
                          "G": "briefing:Training_Classroom_2 records:Training_Records?"}, FILL)
    lane(D, aft.pid, -1, {"C": "staterooms heads", "D": "briefing:Training_Classroom_3 records offices:Chaplain's_Office", "E": "staterooms offices:Engineering_Staff_Office", "F": "laundry quiet",
                          "G": "heads offices:Flight_Staff_Office"}, FILL)
    lane(D, "SB0", +1, {"D": "single_cabins", "F": "single_cabins"})
    lane(D, "PO0", -1, {"D": "single_cabins", "F": "single_cabins"})


# ===================================================================================================================================================== Deck 4
def deck4_setup(D) -> None:
    """The Mess Concourse and the Berthing Lobby, the Bow Observation: halls the Spine opens into at its ends (they take over the end of the corridor); the side passages."""
    fwd = next(p for p in D.passages.values() if p.pid.startswith("SP") and p.a1 > 80.0)
    D.set_extent(fwd.pid, -104.0, 84.0)
    for pid in ("SB0", "PO0"):
        D.set_extent(pid, None, 92.0)
        D.ends(pid, fwd="wall", aft="wall")
    for ps in D.passages.values():
        if ps.pid.startswith("SP") and ps.pid != fwd.pid:
            D.ends(ps.pid, fwd="wall", aft="wall")
    # (the Spine's forward piece is open at both ends: into the concourse aft, into the bow observation deck forward)
    D.special("d4_bow_obs", "bow_obs", (84.0, -16.0), 0.0, [84.0, -16.0, 104.0, 16.0], "A", plate="bow_obs")
    rc = D.special("d4_concourse", "concourse", (-121.7, -18.0), 0.0, [-121.7, -18.0, -104.0, 18.0], "B", plate="concourse")
    for x in (-118.0, -110.0):
        D.gate(rc, f"d4_gate_conc_sbp_{int(-x)}", "SB0", x, -1, GATE_W, GATE_H)
        D.gate(rc, f"d4_gate_conc_pp_{int(-x)}", "PO0", x, +1, GATE_W, GATE_H)
    rl = D.special("d4_berth_lobby", "berth_lobby", (-175.3, -18.0), 0.0, [-175.3, -18.0, -160.7, 18.0], "C")
    for x in (-166.0, -170.0):
        D.gate(rl, f"d4_gate_lobby_sbp_{int(-x)}", "SB0", x, -1, GATE_W, GATE_H)
        D.gate(rl, f"d4_gate_lobby_pp_{int(-x)}", "PO0", x, +1, GATE_W, GATE_H)
    D.open_ends = [("d4_concourse", fwd.pid, 0, True), ("d4_bow_obs", fwd.pid, -1, False)]


def deck4(D) -> None:
    """Crew Services. A: the forward recreation deck, the crew's high street from the bow to the Concourse. B: the hub (Concourse, Mess Hall, galley). C: the Berthing and the
    district round it (the Berthing Lobby, two berthing bays, heads, laundry). D: the crew's recreation aft of the berthing (the games rooms, the bar, the simulators). E-H: the
    engineers' district round the Main Engineering hall and the stern: berthing bays, heads, laundry, a lounge, a games room."""
    sp = pieces(D)
    fwd, mid, aft = sp[0], sp[1], sp[2]
    FILL = ["locker_s", "store_s", "tech_s"]
    # ---- the galley pass along the Mess kitchen (the Mess Hall's annex is on its port flank)
    D.anchor("PO0", +1, -124.0, ("galley_pass",))
    D.anchor("PO0", -1, -128.0, ("galley",))                  # the Main Galley, across the Port Passage from its pass (its door 10 m in: clear of the Concourse's gates)
    # ---- A: the high street. Starboard: learning and quiet at the bow, then the shops, the bar and the lounge towards the Concourse. Port: the garden, the games, the simulators.
    lane(D, fwd.pid, +1, {"A": "library:Main_Library chapel store_s shop barber bar lounge games:Card_Room? store_s offices:Crew_Services_Office?"})
    lane(D, fwd.pid, -1, {"A": "garden:Forward_Garden games sim_bay library:Technical_Library store_s gym quiet heads store_s? quiet?"})
    # ---- C-E, the Spine's middle piece (aft of the Berthing): heads and laundry at the Berthing's door, the lounge, the games rooms and the bar further aft
    # (the damage bench strikes d4_games_D2 and its neighbour d4_games_D1 and walks the Captain 80 m forward: the neighbour's forward edge must be within 45 m of D2's middle, hence the gap)
    lane(D, mid.pid, +1, {"C": "heads laundry store_s", "D": "gap:4 games games"}, FILL)
    lane(D, mid.pid, -1, {"C": "lounge:Berthing_Lounge heads", "D": "gap:4 bar sim_bay"}, FILL)
    # ---- E-H, the Spine's aft piece (aft of the Main Engineering hall): the engineers' district
    lane(D, aft.pid, +1, {"F": "store_s berthing store_s", "G": "heads laundry", "H": "games:Engineers'_Games_Room"}, FILL)
    lane(D, aft.pid, -1, {"F": "heads laundry", "G": "lounge:Engineers'_Lounge", "H": "berthing"}, FILL)
    # ---- the outer lanes (16 m rooms along the hull)
    lane(D, "SB0", +1, {"A": "store_s observation lounge store_s hydro games?", "B": "lounge:Concourse_Cafe store_s", "C": "berthing berthing", "D": "laundry heads", "E": "berthing",
                        "F": "laundry heads", "G": "lounge:Engineers'_Reading_Room?"}, FILL)
    lane(D, "PO0", -1, {"A": "store_s observation bar library quiet", "B": "store_s?", "C": "store_dry store_cold", "D": "heads laundry",
                        "F": "heads berthing laundry?", "G": "games:Engineers'_Card_Room?"}, FILL)


# ===================================================================================================================================================== Deck 5
def deck5(D) -> None:
    """Science & Transport. A-C (the bow to the middle): science, next to the sensors that look forward: the labs, the sensor rooms, the archives; the Transporter Room and
    Astrometrics in B, the computer core A in C. D-H: the machinery that serves the decks above (the coolant plants, the pumps, the air and water plants). The starboard outer lane is
    the Spine Shuttle's tunnel (ship_design_shuttle.py): nothing else stands there."""
    import ship_design_shuttle as SH
    SH.setup(D)
    sp = pieces(D)
    fwd, p2, p3, aft = sp[0], sp[1], sp[2], sp[3]
    FILL = ["store_s", "tech_s", "locker_s"]
    lane(D, fwd.pid, +1, {"A": "sensor_room:Forward_Sensor_Array lab_phys sensor_archive lab lab_bio?", "B": "transporter lab_astro lab_bio? records:Science_Records?",
                          "C": "records computer_core:Computer_Core_A store_s"}, FILL)
    lane(D, fwd.pid, -1, {"A": "sensor_room:Sensor_Array_2 lab_bio:Exobiology_Lab lab:Chemistry_Lab lab_phys:Materials_Lab sensor_room", "B": "lab:Analysis_Lab sensor_room lab_phys store_s",
                          "C": "sensor_room lab"}, FILL)
    lane(D, p2.pid, +1, {"D": "records?"}, FILL)
    lane(D, p2.pid, -1, {"D": "sensor_archive?"}, FILL)
    lane(D, p3.pid, +1, {"E": "radiator_pumps tech_s"}, FILL)
    lane(D, p3.pid, -1, {"E": "machinery tech_s"}, FILL)
    lane(D, aft.pid, +1, {"F": "tech_s", "G": "pool water_plant", "H": "pool radiator_pumps machinery_b"}, FILL)
    lane(D, aft.pid, -1, {"F": "tech_s", "G": "pool air_plant", "H": "pool machinery radiator_pumps"}, FILL)
    lane(D, "PO0", -1, {"A": "lab:Observatory_Lab lab_phys:High-Energy_Lab", "B": "hydro lab_bio lab", "C": "hydro lab_phys store_cold", "D": "pool lab store_cold sensor_archive",
                        "E": "pool radiator_pumps machinery", "F": "pool machinery_b air_plant", "G": "pool machinery water_plant", "H": "pool radiator_pumps machinery_b"}, FILL)


# ===================================================================================================================================================== Deck 6
def deck6(D) -> None:
    """Medical. C: the Medbay's own section: round its entrance (the existing hall, x -262..-232) the medical complex — two operating theatres, the pharmacy, the dental clinic,
    the isolation ward, the morgue, the counselling office, a laboratory and the records — within a minute of its door and of the lift bank D. B: hospital support (rehabilitation,
    the medicinal garden, the blood bank) and the medical staff's quarters. D-H: the engineers' district aft, near the Main Engineering hall (Decks 5-8): four berthing bays with
    their heads and laundries, the petty officers' quarters, a lounge, a gym, a library."""
    sp = pieces(D)
    fwd, p3, aft = sp[0], sp[1], sp[2]
    FILL = ["store_s", "tech_s", "locker_s"]
    lane(D, fwd.pid, +1, {"A": "store_s tech_s", "B": "gym:Rehabilitation_Gym garden:Medicinal_Garden lab:Medical_Research records store_s cabins:Medical_Staff_Quarters heads laundry?",
                          "C": "surgery surgery:Surgery_2 pharmacy dentist records:Medical_Records"}, FILL)
    lane(D, fwd.pid, -1, {"A": "store_s", "B": "store_cold:Medical_Cold_Store offices:Medical_Administration lab:Pathology_Lab heads",
                          "C": "quarantine:Isolation_Ward morgue lab:Medical_Laboratory? counselling:Counselling_&_Chaplaincy"}, FILL)
    lane(D, p3.pid, +1, {"C": "store_s", "D": "store_dry:Medical_Supplies"}, FILL)
    lane(D, p3.pid, -1, {"C": "lab:Blood_&_Tissue_Lab", "D": "store_s heads"}, FILL)
    lane(D, aft.pid, +1, {"E": "berthing", "F": "berthing", "G": "heads", "H": "gym:Engineers'_Gym"}, FILL)
    lane(D, aft.pid, -1, {"E": "berthing", "F": "heads laundry", "G": "lounge:Engineers'_Lounge", "H": "berthing"}, FILL)
    lane(D, "PO0", -1, {"B": "hydro store_cold", "C": "pool lab store_dry heads", "D": "cabins:Petty_Officers'_Quarters_2 laundry", "E": "library:Engineers'_Library garden:Aft_Garden?",
                        "F": "pool heads laundry store_dry", "G": "pool lounge:Petty_Officers'_Mess heads", "H": "pool store_s heads"}, FILL)
    lane(D, "SB0", +1, {"B": "pool lab hydro store_cold", "C": "pool lab store_cold records", "D": "cabins:Petty_Officers'_Quarters_1 heads", "E": "lounge:Engineers'_Mess gym?",
                        "F": "pool heads laundry store_dry", "G": "pool heads laundry", "H": "pool store_s"}, FILL)


# ===================================================================================================================================================== Deck 7
def deck7(D) -> None:
    """Engineering & Power. The reactor hall is the existing Main Engineering (x -372..-330). Forward of it (E): the power the hall makes — the main power control, the switchgear, the
    capacitor halls, the auxiliary reactor — so that the thick buses are short. C-D: the life-support plants (air, water, waste), amidships, close to the crew they serve (the
    Crew Country above and the Medbay), with the machinery spaces and the workshops. B: the damage-control central and the engineers' workshops, next to the bridge lifts (a
    chief engineer is a few minutes from the bridge). G-H: the stern: the radiators' pumps, the compressors, the engine controls."""
    sp = pieces(D)
    fwd, p3, aft = sp[0], sp[1], sp[2]
    FILL = ["tech_s", "store_s", "locker_s"]
    lane(D, fwd.pid, +1, {"B": "dc_central:Damage-Control_Central workshop:Engineering_Workshop machinery_b:Compressor_Room heads", "C": "air_plant:Atmosphere_Plant_1 water_plant:Water_Reclamation_Plant_1 machinery:Auxiliary_Machinery?",
                          "D": "tech_s"}, FILL)
    lane(D, fwd.pid, -1, {"B": "lounge:Engineers'_Mess offices:Engineering_Office workshop:Electrical_Shop", "C": "air_plant:Atmosphere_Plant_2 water_plant:Water_Reclamation_Plant_2 machinery:HVAC_Plant?"}, FILL)
    lane(D, p3.pid, +1, {"E": "power_control:Main_Power_Control"}, FILL)
    lane(D, p3.pid, -1, {"E": "aux_reactor:Auxiliary_Power_Plant"}, FILL)
    lane(D, aft.pid, +1, {"G": "pool machinery_b radiator_pumps", "H": "pool machinery radiator_pumps"}, FILL)
    lane(D, aft.pid, -1, {"G": "pool machinery", "H": "pool machinery_b power_control:Engine_Control"}, FILL)
    lane(D, "PO0", -1, {"B": "pool machinery machinery_b store_dry", "C": "pool machinery_b hold", "D": "pool machinery_b", "E": "pool capacitors switchgear", "F": "pool machinery capacitors",
                        "G": "pool radiator_pumps machinery_b", "H": "pool machinery radiator_pumps"}, FILL)
    lane(D, "SB0", +1, {"B": "pool machinery machinery_b hold", "C": "waste_plant:Waste_Processing_Plant machinery_b? store_dry?", "D": "pool machinery", "E": "pool switchgear power_control", "F": "pool machinery_b capacitors",
                        "G": "pool radiator_pumps machinery", "H": "pool machinery_b radiator_pumps"}, FILL)


DS.register(2, deck2)
DS.register(3, deck3)
DS.register(4, deck4, deck4_setup)
DS.register(5, deck5)
DS.register(6, deck6)
DS.register(7, deck7)

import ship_design_decks2  # noqa: E402,F401  (the lower decks' schedules register themselves)
