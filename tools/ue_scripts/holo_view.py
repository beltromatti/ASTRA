"""Testing: put the player in the game world at EYE (m) looking at LOOK (m) — e.g. to photograph the holo table.
Run during PIE: tools/ue.py py "EYE=(-1.7,1.5,1.05); LOOK=(-4.8,0,1.25); exec(open(\"tools/ue_scripts/holo_view.py\").read())" """
import unreal, math
w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_game_world()
pc = unreal.GameplayStatics.get_player_controller(w, 0)
pawn = pc.get_controlled_pawn()
eye = globals().get("EYE", (-1.7, 1.5, 1.05))
look = globals().get("LOOK", (-4.8, 0.0, 1.25))
pawn.set_actor_location(unreal.Vector(eye[0]*100, eye[1]*100, eye[2]*100), False, True)
dx, dy, dz = look[0]-eye[0], look[1]-eye[1], look[2]-(eye[2]+0.64)
yaw = math.degrees(math.atan2(dy, dx)); pitch = math.degrees(math.atan2(dz, math.hypot(dx, dy)))
pc.set_control_rotation(unreal.Rotator(roll=0, pitch=pitch, yaw=yaw))
print("view", round(yaw,1), round(pitch,1))
