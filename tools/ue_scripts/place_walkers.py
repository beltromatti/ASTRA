"""The crew going about the ship (AAstraWalker): a round of waypoints each, in the corridors behind the bridge, the
Medbay's aisles, the flight deck and around the reactor. Idempotent: the "Walkers" folder is replaced. Not during PIE:
  tools/ue.py pyfile tools/ue_scripts/place_walkers.py
"""
import json
import math
import os

import unreal

ROOT = "/Users/beltromatti/Desktop/ASTRA"
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
M = 100.0
CAPSULE = 92.0
log = []


def data(name):
    return json.load(open(os.path.join(ROOT, "data", "ship", f"aquila_{name}.json")))


for a in eas.get_all_level_actors():
    if str(a.get_folder_path()).startswith("Walkers"):
        eas.destroy_actor(a)


def walker(label, route_m, floor_z_m, dept, female, pause=(3.0, 9.0), speed=135.0):
    pts = [unreal.Vector(x * M, y * M, floor_z_m * M + CAPSULE) for x, y in route_m]
    w = eas.spawn_actor_from_class(unreal.AstraWalker, pts[0], unreal.Rotator())
    w.set_editor_property("route", pts)
    w.set_editor_property("pause_range", unreal.Vector2D(*pause))
    w.set_editor_property("walk_speed", speed)
    w.set_editor_property("female_body", female)
    w.set_editor_property("dept", dept)
    w.set_actor_label(label)
    w.set_folder_path("Walkers")
    log.append(label)


# the corridors behind the bridge (floor 0; the bridge doors at x -8.65, the ends at -20.8)
walker("Walker_CorrPort", [(-10.0, -3.9), (-18.4, -3.9)], 0.0, "Command", False, pause=(4.0, 12.0))
walker("Walker_CorrStbd", [(-18.8, 3.9), (-10.2, 3.9)], 0.0, "Science", True, pause=(5.0, 14.0))

# the Medbay: a nurse on her round of the beds, along both aisles and past the theatre's door
med = data("medbay")
ox, oy, oz = med["world_origin"]
rnd = [(-5.4, -5.3), (-12.8, -5.3), (-20.6, -5.3), (-20.6, 5.3), (-12.8, 5.3), (-5.4, 5.3)]
walker("Walker_MedNurse", [(ox + x, oy + y) for x, y in rnd], oz, "Medical", True, pause=(4.0, 10.0), speed=120.0)

# the flight deck: two deck crew between the bays and the catapults
hg = data("hangar")
hx, hy, hz = hg["world_origin"]
walker("Walker_DeckA", [(hx + 20.0, hy - 8.0), (hx + 95.0, hy - 8.0), (hx + 95.0, hy - 3.0), (hx + 20.0, hy - 3.0)], hz, "Flight", False,
       pause=(2.0, 7.0), speed=150.0)
walker("Walker_DeckB", [(hx + 30.0, hy + 7.0), (hx + 110.0, hy + 7.0)], hz, "Flight", True, pause=(3.0, 8.0), speed=150.0)

# Main Engineering: a technician walking round the reactor's pit (clear of the master console)
en = data("engineering")
ex, ey, ez = en["world_origin"]
r = en["reactor"]
ring = [(ex + r["x"] + 9.2 * math.cos(2 * math.pi * k / 8), ey + r["y"] + 9.2 * math.sin(2 * math.pi * k / 8)) for k in range(8)]
walker("Walker_EngTech", ring, ez, "Engineering", False, pause=(2.0, 8.0), speed=125.0)

unreal.EditorLevelLibrary.save_current_level()
print(json.dumps(log))
