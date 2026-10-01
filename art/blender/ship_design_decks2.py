"""ASN Aquila — the schedules of the lower decks (NAVE-3): Deck 8 (security and the Marines), 9 (flight operations), 10 (cargo and magazines), 11 (fabrication and repair), 12 (the
keel). See ship_design_decks.py for how to read a schedule; the upper decks are there."""
from __future__ import annotations

import ship_design as DS
from ship_design_decks import lane, pieces


# ===================================================================================================================================================== Deck 8
def deck8(D) -> None:
    """Security & Marines. B (the bow end, beside the Flight Deck's volume): boarding — the Assault-Shuttle Bay on the port side, the Marine Armory and the boarding kit beside the
    Spine. C: the Marines' own country — the barracks, their lounge, gym, heads and laundry, the firing range — one lift from the bay. D: the Brig and the Security Office, the
    interrogation suite, the security armory and the evidence store, between the Marines and the lift bank of the Berthing (the Master-at-Arms is a few minutes from anywhere). E-F: the
    engineers' workshops, next to the Main Engineering hall's side (the hall is four decks tall: this is its bottom). G-H: the stern: the second Computer Core and the aft
    Damage-Control Central, as far from their twins (Deck 5 and Deck 7) as the ship allows."""
    sp = pieces(D)
    fwd, aft = sp[0], sp[1]
    FILL = ["store_s", "locker_s", "tech_s"]
    # ---- the Spine's forward piece (SP1): from the bow end to the Engineering hall
    lane(D, fwd.pid, +1, {"B": "tech_s locker_s:Marine_Lockers", "C": "barracks:Marine_Barracks_1 barracks:Marine_Barracks_2 barracks:Marine_Barracks_3",
                          "D": "records:Security_Records security_office brig armory:Security_Armory offices:Interrogation_Suite?",
                          "E": "workshop:Machine_Shop workshop:Welding_Shop?", "F": "tech_s"}, FILL)
    lane(D, fwd.pid, -1, {"B": "armory:Marine_Armory kit_room:Boarding_Kit_Room", "C": "barracks:Marine_Barracks_4 lounge:Marine_Lounge store_s",
                          "D": "briefing:Security_Briefing_Room workshop:Armourer's_Shop store_dry:Evidence_Store",
                          "E": "workshop:Electrical_Shop hold:Spares_Store", "F": "tech_s"}, FILL)
    # ---- the stern: the Spine's aft piece (SP0)
    lane(D, aft.pid, +1, {"G": "machinery_b:Core_Cooling_Plant tech_s", "H": "computer_core:Computer_Core_B records tech_s"}, FILL)
    lane(D, aft.pid, -1, {"G": "air_plant:Atmosphere_Plant_Aft", "H": "dc_central:Damage-Control_Central_Aft switchgear:Aft_Switchgear"}, FILL)
    # ---- the outer lanes
    lane(D, "PO0", -1, {"B": "shuttle_bay:Assault-Shuttle_Bay", "C": "heads laundry?", "D": "firing_range:Marine_Firing_Range magazine:Small-Arms_Magazine workshop:Weapons_Workshop? kit_room:Marine_Kit_Store?",
                        "E": "pool hold store_dry workshop?", "F": "pool machinery hold", "G": "pool machinery_b hold", "H": "pool machinery radiator_pumps"}, FILL)
    lane(D, "SB0", +1, {"B": "magazine:Boarding_Munitions store_s", "C": "gym:Marine_Gym laundry heads", "D": "lab:Forensics_Lab offices:Military_Police_Office store_dry:Evidence_Lockers",
                        "E": "pool hold store_dry workshop?", "F": "pool machinery hold", "G": "pool machinery_b hold", "H": "pool machinery radiator_pumps"}, FILL)


# ===================================================================================================================================================== Deck 9
def deck9(D) -> None:
    """Flight Operations. C (behind the Flight Deck, which fills the bow of decks 6-11): flight operations and the squadron ready rooms, the avionics and the flight-deck shops, the
    drone bay and the aircraft ordnance — everything an aircraft needs within a minute of the deck. D-E: the Air Group's own country — the pilots' quarters, their lounge, the
    flight crews' berthing with its heads and laundry. F-H: cargo, behind the pilots: the cargo holds, the parts stores (the freight lift is the Flight bank's second shaft)."""
    sp = pieces(D)
    s = sp[0]
    FILL = ["store_s", "locker_s", "tech_s"]
    lane(D, s.pid, +1, {"C": "tech_s flight_ops:Flight_Operations pilot_ready:Squadron_Ready_Room store_s",
                        "D": "cabins:Pilots'_Quarters_1 cabins:Pilots'_Quarters_2 heads",
                        "E": "lounge:Pilots'_Lounge berthing:Flight_Crew_Berthing heads laundry?", "F": "store_dry:Aircraft_Parts_Store hold? aircraft_shop:Component_Shop?",
                        "G": "cargo_hold:Cargo_Hold_1 cargo_hold:Cargo_Hold_2? records:Cargo_Office?", "H": "hold:General_Stores_Aft cargo_hold?"}, FILL)
    lane(D, s.pid, -1, {"C": "pilot_ready:Squadron_Ready_Room_2 briefing:Flight_Briefing_Room aircraft_shop:Avionics_Shop",
                        "D": "cabins:Pilots'_Quarters_3 cabins:Pilots'_Quarters_4 laundry?", "E": "berthing:Flight_Crew_Berthing_2 berthing:Flight_Crew_Berthing_3 quiet?",
                        "F": "hold store_dry:Aircraft_Spares aircraft_shop:Airframe_Shop?", "G": "cargo_hold:Cargo_Hold_3 cargo_hold:Cargo_Hold_4? store_cold:Cold_Stores?",
                        "H": "pool hold cargo_hold store_dry"}, FILL)
    lane(D, "PO0", -1, {"C": "magazine:Aircraft_Ordnance_Magazine hold", "D": "cabins:Pilots'_Quarters_6 heads laundry?", "E": "pool heads laundry lounge", "F": "pool hold store_dry cargo_hold",
                        "G": "pool cargo_hold hold store_cold", "H": "pool hold store_dry cargo_hold"}, FILL)
    lane(D, "SB0", +1, {"C": "drone_bay:Drone_Bay aircraft_shop:Flight-Deck_Shop?", "D": "cabins:Pilots'_Quarters_5 heads laundry?", "E": "pool heads laundry gym", "F": "pool hold store_dry cargo_hold",
                        "G": "pool cargo_hold hold store_cold", "H": "pool hold store_dry cargo_hold"}, FILL)


# ===================================================================================================================================================== Deck 10
def deck10(D) -> None:
    """Cargo & Magazines: the armoured core of the ship. The magazines in the middle (C-E: the thickest armour), as far as can be from the outer hull, the Spine between them as the
    ammunition route; the cargo holds forward and aft, the cold stores, the dry stores; the freight lift's lobby (the Engineering bank, x -308) in the middle of the holds."""
    s = pieces(D)[0]
    FILL = ["store_s", "locker_s", "tech_s"]
    lane(D, s.pid, +1, {"B": "tech_s cargo_hold:Cargo_Hold_5", "C": "magazine:Munitions_Magazine_1 magazine:Munitions_Magazine_2 magazine:Munitions_Magazine_3?",
                        "D": "magazine:Munitions_Magazine_4 magazine:Munitions_Magazine_5 hold?", "E": "magazine:Munitions_Magazine_6 store_dry:Ordnance_Stores hold",
                        "F": "cargo_hold:Cargo_Hold_6 hold? store_dry?", "G": "cargo_hold:Cargo_Hold_7? hold", "H": "hold store_dry?"}, FILL)
    lane(D, s.pid, -1, {"B": "store_cold:Cold_Stores_1 hold", "C": "magazine:Munitions_Magazine_7 magazine:Munitions_Magazine_8?", "D": "magazine:Munitions_Magazine_9 store_dry:Ordnance_Stores_2 hold",
                        "E": "store_cold:Cold_Stores_2 hold store_dry", "F": "cargo_hold:Cargo_Hold_8 hold", "G": "hold", "H": "store_cold:Cold_Stores_3 hold?"}, FILL)
    lane(D, "PO0", -1, {"B": "pool cargo_hold hold", "C": "pool magazine hold", "D": "pool magazine store_dry hold", "E": "pool store_cold hold store_dry", "F": "pool cargo_hold hold store_dry",
                        "G": "pool cargo_hold hold", "H": "pool hold store_dry store_cold"}, FILL)
    lane(D, "SB0", +1, {"B": "pool cargo_hold hold", "C": "pool magazine hold", "D": "pool magazine store_dry hold", "E": "pool store_cold hold store_dry", "F": "pool cargo_hold hold store_dry",
                        "G": "pool cargo_hold hold", "H": "pool hold store_dry store_cold"}, FILL)


# ===================================================================================================================================================== Deck 11
def deck11(D) -> None:
    """Fabrication & Repair: the ship's own yard. Forward (B-C, under the Flight Deck's skirt): the repair bays and the fabrication shops, where a damaged part is made again; the machine
    shops; the second damage-control central (the first is on Deck 7, the third aft on Deck 8). D-E: the stores of spares; F-H: the stern's workshops and the crew that works them."""
    s = pieces(D)[0]
    FILL = ["store_s", "locker_s", "tech_s"]
    lane(D, s.pid, +1, {"B": "fab_shop:Fabrication_Shop_1 repair_bay:Repair_Bay_1?", "C": "dc_central:Damage-Control_Central_Fore fab_shop:Fabrication_Shop_2 workshop:Machine_Shop?",
                        "D": "workshop:Electronics_Shop hold:Spares_Store heads laundry", "E": "berthing:Fabricators'_Berthing store_dry:Spares_Store", "F": "workshop:Foundry_Shop hold?", "G": "hold store_dry?", "H": "hold"}, FILL)
    lane(D, s.pid, -1, {"B": "repair_bay:Repair_Bay_2 fab_shop:Fabrication_Shop_3", "C": "workshop:Welding_Shop workshop:Composites_Shop?", "D": "hold:Spares_Store store_dry heads laundry",
                        "E": "heads laundry store_dry", "F": "workshop:Optics_Shop hold", "G": "hold store_dry?", "H": "hold"}, FILL)
    lane(D, "PO0", -1, {"B": "pool fab_shop workshop", "C": "pool repair_bay workshop hold", "D": "pool hold store_dry", "E": "pool hold store_dry machinery", "F": "pool machinery hold",
                        "G": "pool hold machinery_b", "H": "pool hold machinery"}, FILL)
    lane(D, "SB0", +1, {"B": "pool fab_shop workshop", "C": "pool repair_bay workshop hold", "D": "pool hold store_dry", "E": "pool hold store_dry machinery", "F": "pool machinery hold",
                        "G": "pool hold machinery_b", "H": "pool hold machinery"}, FILL)


# ===================================================================================================================================================== Deck 12
def deck12(D) -> None:
    """The keel: the fuel, coolant and reaction-mass tanks along the bottom of the ship with the crawlway system (K tone) that serves them: the Keel Crawlway down the middle and a
    crawlway on each side, hubs where they cross. Nobody lives here; the damage-control stations and the pump rooms are the only crewed spaces."""
    sp = pieces(D)
    FILL = ["tank", "reaction_mass", "crawlway"]
    for p in sp:
        lane(D, p.pid, +1, {}, FILL)
        lane(D, p.pid, -1, {}, FILL)
    lane(D, "PO0", -1, {}, ["tank", "reaction_mass", "crawlway"])
    lane(D, "SB0", +1, {}, ["tank", "reaction_mass", "crawlway"])


DS.register(8, deck8)
DS.register(9, deck9)
DS.register(10, deck10)
DS.register(11, deck11)
DS.register(12, deck12)
