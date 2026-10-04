// ASTRA — ABBORDAGGI-2: the inside of a ship that is boarded, as real geometry (docs/brief/ABBORDAGGI-2.md §5).
//
// The Aquila's decks are in the level; another ship's are only a plan (AstraBoardPlans.*: the rooms as boxes, the doors and openings between them). When the Captain goes along with his
// marines the plan is made solid where he is: floors, ceilings, walls with the gaps of the doors and of the open ways, the frames of the doors, a leaf in each pressure bulkhead (shut when
// the fight has sealed it), strips of light, and a few lights that follow him: simple boxes of the instanced cube with the ship's own materials (STILE.md), built a few rooms at a time round
// him in a zone of the world nobody else uses (the same distance below the level as the planet's zone, further down), and gone when he is back aboard the Aquila. The same plan serves the
// fight (the simulation's rooms and doors are these) and the walking (the Captain's capsule stands on these floors, his rounds strike these walls), so a man the simulation says is in a
// room is in it.
//
// AstraBoardInterior::BuildComp is plain code (no world): the bench builds every class's plan and walks the simulation's own routes through it (a route that meets a wall is a bug of the
// builder). AAstraBoardInterior is the actor that holds the boxes in the world.

#pragma once

#include "CoreMinimal.h"
#include "AstraBoardMap.h"
#include "AstraBoardPlans.h"
#include "GameFramework/Actor.h"
#include "AstraBoardInterior.generated.h"

class UInstancedStaticMeshComponent;
class UMaterialInstanceDynamic;
class UMaterialInterface;
class UPointLightComponent;
class USpotLightComponent;
class UStaticMesh;
namespace AstraBoardDress { struct FFallen; }

namespace AstraBoardInterior
{
	enum class ESlab : uint8 { Wall, Floor, Ceiling, Frame, Leaf, Strip, Mark };       // (Mark: a lit square on the floor where stairs and lifts are: not a ceiling light)
	constexpr int32 NumSlabKinds = 7;

	/** One solid: an axis-aligned box (cm, the plan's frame). */
	struct FSlab
	{
		FVector Centre = FVector::ZeroVector;
		FVector Half = FVector::ZeroVector;
		ESlab Kind = ESlab::Wall;
		int32 Comp = INDEX_NONE;
		int32 Door = INDEX_NONE;          // Leaf: the damage map's door it closes
	};

	constexpr float WallCm = 12.f;          // a wall's thickness (inside the room's own box: two rooms' walls stand side by side)
	constexpr float FloorCm = 22.f;         // the slab under the floor
	constexpr float CeilingCm = 20.f;
	constexpr float DoorHeightCm = 222.f;
	constexpr float BlastHeightCm = 240.f;

	/** A gap in a wall: along it from S0 to S1, up from Bot to Top (cm above this room's floor: a door between a tall hall and a room on a higher deck stands where the higher floor is). */
	struct FOpening
	{
		double S0 = 0.0, S1 = 0.0, Bot = 0.0, Top = 0.0;
		int32 Portal = INDEX_NONE;
		bool bFramed = false;                      // a door or a pressure bulkhead (the open ways are not framed)
	};
	/** A stretch of a wall that stands alike all along it: Solid lists the heights above the floor that are wall there ((from, to) pairs: a stretch above a door is one, a stretch beside it another). */
	struct FWallRun
	{
		double S0 = 0.0, S1 = 0.0;
		TArray<FVector2D, TInlineAllocator<3>> Solid;
	};
	/** One face of a room, as BuildComp makes it and as the dressing (AstraBoardDress) dresses it: face 0 +X, 1 -X, 2 +Y, 3 -Y; Plane the face's coordinate along its axis (X for 0 and 1, Y for 2 and 3), Sign which
	 *  way it looks out of the room, T0..T1 its extent along the other axis, the openings (the gaps of its portals) and the runs of wall between them. */
	struct FFaceGeo
	{
		int32 Face = 0;
		bool bX = true;
		double Sign = 1.0, Plane = 0.0, T0 = 0.0, T1 = 0.0;
		TArray<FOpening> Opens;
		TArray<FWallRun> Runs;
	};
	ASTRA_API void FaceGeo(const FAstraBoardMap& Map, int32 Comp, int32 Face, FFaceGeo& Out);

	/** The solids of one compartment: its floor and ceiling, its four walls with the gaps of its portals (the doors, the open ways: the whole stretch the two rooms share), a frame round each door, a
	 *  leaf in each pressure bulkhead that this room is the first side of, and a strip of light. */
	ASTRA_API void BuildComp(const FAstraBoardMap& Map, int32 Comp, TArray<FSlab>& Out);
	/** Whether a segment (cm) passes through a slab of the set (the walls and the leaves that are shut: ShutDoors, the damage map's door indices, may be null: every leaf is shut). OutHit: the first slab in the way, for the bench's report. */
	ASTRA_API bool SegmentBlocked(const TArray<FSlab>& Slabs, const FVector& A, const FVector& B, const TSet<int32>* OpenDoors = nullptr, const FSlab** OutHit = nullptr);
}

/** What the walls, the floors and the lights are made of: a ship that has power has its lights on, a hulk is in the red of its emergency strips. */
enum class EAstraInteriorStyle : uint8 { Lit, Emergency };

UCLASS()
class ASTRA_API AAstraBoardInterior : public AActor
{
	GENERATED_BODY()

public:
	AAstraBoardInterior();

	/** The world's zone for the rooms of a boarded ship (cm): the plan's frame is put there. */
	static FVector ZoneOrigin();
	/** The zone of the little cabin of a boat the Captain rides in. */
	static FVector CabinOrigin();

	/** The plan to make solid, where in the world it stands (ZoneOrigin), and how it is lit. InMoods: how the rooms are that the war has left not as built (rooms without power are dark, rooms that burn
	 *  have their fire's light); null: all as built, lit by the style alone. InFallen: the crew she lost, where they fell (the war's picture of her: they lie where they fell). When the kit of the decks
	 *  (art/blender/board_kit.py, imported by tools/ue_scripts/import_board_kit.py) is in the content, the rooms are dressed as they are built (AstraBoardDress); when it is not, they stay plain boxes. */
	void Begin(TSharedPtr<FBoardShipPlan> InPlan, const FVector& InOffset, EAstraInteriorStyle InStyle, const TMap<int32, FBoardRoomMood>* InMoods = nullptr, const TArray<AstraBoardDress::FFallen>* InFallen = nullptr);
	/** A small room of a boat (benches, red light): where a Captain waits while the boat flies. Returns where to put him (feet, cm). */
	FVector BuildCabin();
	/** The rooms round a point of the plan (cm) are made solid (a few at each call). Returns true while there is more to build there. */
	bool EnsureAround(const FVector& PlanCm, int32 MaxRooms = 4);
	/** The leaves of the pressure bulkheads follow the fight's: ShutDoors lists the damage map's doors that are shut now. */
	void SetShut(const TSet<int32>& ShutDoors);
	/** Where the lights are, near the Captain (his eye, world cm) and the way he looks. */
	void Follow(const FVector& EyeWorld, const FVector& LookWorld);
	/** The stairs: where a pad of one deck is and where it leads (cm, the plan's frame); a pad within reach of a point. -1 when none. */
	int32 PadNear(const FVector& PlanCm, float ReachCm, FVector& OutTo, FString& OutText) const;
	/** The plan is made solid (Begin has been called and End has not). */
	bool IsBegun() const { return Plan.IsValid(); }
	int32 NumRooms() const { return Built.Num(); }
	int32 NumSlabs() const { return NumInstances; }
	/** What the dressing has put in the rooms built so far, in a line (the console's info): instances of the kit, props, bodies, lamps. Empty when the rooms are not dressed. */
	FString DescribeDress() const;
	/** Everything goes. */
	void End();

protected:
	virtual void Tick(float DeltaSeconds) override;

private:
	TSharedPtr<FBoardShipPlan> Plan;
	FVector Offset = FVector::ZeroVector;
	EAstraInteriorStyle Style = EAstraInteriorStyle::Emergency;
	TSet<int32> Built;                                         // the rooms made solid
	TMap<int32, int32> LeafInstance;                           // door -> its instance in the leaves
	TMap<int32, FTransform> LeafHome;                          // door -> where its leaf stands when shut (in the actor's frame: the actor stands at Offset)
	TSet<int32> ShutNow;
	int32 NumInstances = 0;
	TMap<int32, FBoardRoomMood> Moods;                         // the rooms the war has left not as built
	TArray<FVector> StripAt;                                   // the strips of light (plan frame, cm), for the lights that follow the Captain
	TArray<FVector> FireAt;                                    // the rooms that burn (plan frame, cm)
	bool bTorchOn = false;
	struct FPad { FVector Here; FVector To; int32 Comp = INDEX_NONE; FString Text; };
	TArray<FPad> Pads;
	TSet<int32> PadDone;

	UPROPERTY() TObjectPtr<UStaticMesh> Cube;
	UPROPERTY() TObjectPtr<UInstancedStaticMeshComponent> Walls;
	UPROPERTY() TObjectPtr<UInstancedStaticMeshComponent> Floors;
	UPROPERTY() TObjectPtr<UInstancedStaticMeshComponent> Frames;
	UPROPERTY() TObjectPtr<UInstancedStaticMeshComponent> Leaves;
	UPROPERTY() TObjectPtr<UInstancedStaticMeshComponent> Strips;
	UPROPERTY() TObjectPtr<UInstancedStaticMeshComponent> DeadStrips;       // the strips of the rooms with no power: the red of the emergency lighting, low
	UPROPERTY() TArray<TObjectPtr<UPointLightComponent>> Lights;
	UPROPERTY() TArray<TObjectPtr<UPointLightComponent>> FireLights;
	UPROPERTY() TObjectPtr<USpotLightComponent> Torch;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> StripMat;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> DeadStripMat;
	float LightT = 0.f;
	FVector LastEye = FVector::ZeroVector;
	FVector LastLook = FVector::ForwardVector;

	UInstancedStaticMeshComponent* MakeIsm(const TCHAR* Name, UMaterialInterface* Mat, bool bShadow);
	void AddSlabs(const TArray<AstraBoardInterior::FSlab>& Slabs);
	void MakePads(int32 Comp);
	void MoveLights();

	// ---- the dressing (AstraBoardInteriorDress.cpp): the kit's pieces as instanced meshes, the lamps that light, the signs, the flames and sparks
	struct FKitState;
	TSharedPtr<FKitState> Kit;
	UPROPERTY() TArray<TObjectPtr<UObject>> KitKeep;           // what the dressing's materials and pooled parts are made of (kept from the collector)
	bool DressBegin(const TArray<AstraBoardDress::FFallen>* InFallen);
	void DressBuilt(int32 Comp);
	void DressShut(const TSet<int32>& ShutDoors);
	void DressLights(const FVector& Eye);
	void DressTick(float Dt);
	void DressEnd();
};
