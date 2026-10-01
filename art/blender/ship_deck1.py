"""ASN Aquila plan: the Captain's ready room on Deck 1 (NAVE-2). The bridge complex is the older hand-built part of the ship (aquila_bridge.json, the SM_COR corridors placed by
tools/ue_scripts/build_bridge_v3.py); the ready room is the block between its two corridors (docs/BIBBIA.md §6). Here it gets what a built room of the kit gets: its
compartment with the spots and the lamps of its prefab (ship_spec.py "ready_room", ship_rooms_bridge.py), the placement of its mesh, a door in the port corridor's inner wall, the
name plate, and the nodes and edges that join it to the corridor. The old corridor kit has no door in a side wall: the window module of the port corridor is replaced by
`SM_SHIP_BridgeCorridorDoor` (the same module with the opening) and the Unreal script removes the actors the bridge builder placed there (its window shell and the first
inner-wall panels of that module).

Frame: the lane rooms' (origin at the corridor-side corner of the room, x along the corridor, y into the room, yaw 0: the room lies on the +y side of the port corridor).
"""
from __future__ import annotations

import ship_plan as P
import ship_spec as SP
from ship_layout import Builder, rnd

ORIGIN = (-20.8, -2.1)               # the room's corner: the corridors' aft end (their modules start at -20.8) and the outer face of the port corridor's inner wall; the forward end
                                     # (x -8.8) is the outer face of the bridge's back wall and the starboard corridor's face is at y +2.1
CORRIDOR_Y = -3.9                    # the port corridor's centre line
WALL_MID_Y = -2.2                    # the middle of that corridor's inner wall (0.2 m thick: -2.3 .. -2.1), where the door's leaves run
MODULE_X = -16.8                     # the aft end of the corridor module that has the door: the window module (the bridge builder: X_END - 8, X_END = back wall -8.5 - 0.3)
MODULE_MESH = "SM_SHIP_BridgeCorridorDoor"
PLATE_Z = 2.385                      # the centre of the name plate over the door (the wall is vertical up to 2.5 m: the chamfer starts there)


def build(B: Builder) -> None:
    """The ready room: compartment, placements, door, plate, graph nodes and edges."""
    spec = SP.PREFABS["ready_room"]
    L, D, h = spec["L"], spec["D"], spec["h"]
    o3 = (ORIGIN[0], ORIGIN[1], 0.0)
    stations = []
    for i, s in enumerate(spec["spots"]):
        w = P.place_local(o3, 0.0, s["x"], s["y"])
        stations.append({"id": f"ready_room.s{i}", "role": s["role"], "kind": s["kind"], "pos": [rnd(w[0]), rnd(w[1]), rnd(s.get("dz", 0.0))],
                         "yaw": rnd(s["yaw"] % 360.0, 1), "dept": s["dept"]})
    lights = []
    for i, l in enumerate(spec["lights"]):
        w = P.place_local(o3, 0.0, l["pos"][0], l["pos"][1], l["pos"][2])
        ld = dict(l)
        ld["pos"] = [rnd(w[0]), rnd(w[1]), rnd(w[2])]
        ld["id"] = f"ready_room.l{i}"
        lights.append(ld)
    wx0, wx1 = ORIGIN[0] + 0.25, ORIGIN[0] + L - 0.25                          # the finished faces: 0.25 m of wall and finish at either end, 0.05 on the corridor's side
    wy0, wy1 = ORIGIN[1] + 0.05, ORIGIN[1] + D - 0.25
    B.comp("ready_room", 1, spec["kind"], spec["name"], [wx0, wy0, wx1, wy1], (0.0, h + 0.3), section="A", dept=spec["dept"], prefab="ready_room", mesh=spec["mesh"],
           pos=[rnd(o3[0]), rnd(o3[1]), 0.0], yaw=0.0, systems=list(spec["systems"]), stations=stations, lights=lights, plate="ready_room", status="built", lane="special",
           size=[L, D, h], plane=1,
           note="the Captain's ready room: the block between the two corridors of Deck 1 (docs/BIBBIA.md §6); its door is cut in the port corridor's inner wall, in the module "
                f"{MODULE_MESH} that replaces the bridge builder's window module there")
    B.place(1, spec["mesh"], o3, 0.0, "Interior/Deck01/Rooms", "d1_ready_room", "room", comp="ready_room")
    B.place(1, MODULE_MESH, (MODULE_X, CORRIDOR_Y, 0.0), 0.0, "Interior/Deck01/Corridors", "d1_port_door_module", "module")
    dx = ORIGIN[0] + spec["doors"][0]["x"]
    B.place(1, f"SM_SHIP_Plate_{spec['plate']}", (dx, ORIGIN[1] - 0.2, PLATE_Z), -90.0, "Interior/Deck01/Plates", "d1_plate_ready_room", "plate")
    d = spec["doors"][0]
    B.door("ready_room_door", 1, (dx, WALL_MID_Y, 0.0), 90.0, d["w"], d["h"], "corridor_1a_port", "ready_room", kind="sliding", wall="near", side=1,
           note="a sliding door in the inner wall of the port corridor (the window module's first wall bay)")
    # the graph: a node of the corridor in front of the door (the corridor's own two nodes are 8 m apart), the node just inside, the hub and the spots
    B.node("corridor_1a_port.rr", 1, dx, CORRIDOR_Y, 0.0, "corridor", "corridor_1a_port")
    B.node("ready_room.in", 1, dx, ORIGIN[1] + 1.2, 0.0, "door_in", "ready_room")
    B.node("ready_room.hub", 1, (wx0 + wx1) / 2, (wy0 + wy1) / 2, 0.0, "room", "ready_room")
    B.link("corridor_1a_port.n0", "corridor_1a_port.rr", "walk", width=3.2)
    B.link("corridor_1a_port.rr", "corridor_1a_port.n1", "walk", width=3.2)
    B.link("corridor_1a_port.rr", "ready_room.in", "door", door="ready_room_door", width=d["w"])
    B.link("ready_room.in", "ready_room.hub", "walk", width=1.5)
    for st in stations:
        B.node(st["id"], 1, st["pos"][0], st["pos"][1], st["pos"][2], "station", "ready_room", role=st["role"], act=st["kind"], yaw=st["yaw"])
        B.link("ready_room.hub", st["id"], "walk", width=1.0)
