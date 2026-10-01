// ASTRA — a lift car and what stands at its landings (docs/ASCENSORI.md).
//
// AAstraLiftCar is the car: a real moving actor that carries the Captain (his CharacterMovement has its floor for a base, so he rides it as he would a
// moving platform) and the crew's bodies. It ticks its own brain (AstraLiftBrain.h) and only while something moves; at rest it costs nothing. The collision
// is boxes (floor, walls, door leaves) so the same car rides the same in the game and in the offline bench; the look is the kit's meshes (art/blender/
// ship_lift.py), with plain boxes in their place when the kit is not imported yet.
//
// The car's own frame: origin on the floor under its middle, +X the side of its doors (into the lobby), +Y across it (for the shuttle: along the line), +Z up.
//
// AAstraLiftLanding is a landing's doors, their frame, the call panel and its lamp; AAstraLiftShaft is a shaft's walls (instanced segments).

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AstraLiftBrain.h"
#include "AstraLiftData.h"
#include "AstraLiftCar.generated.h"

class UAstraLiftSubsystem;
class UBoxComponent;
class UInstancedStaticMeshComponent;
class UAudioComponent;
class UMaterialInstanceDynamic;
class UPointLightComponent;
class USoundBase;
class UTexture;
class UStaticMesh;
class UStaticMeshComponent;
class AAstraLiftLanding;
class UMaterialInstanceDynamic;
class UTextRenderComponent;

namespace AstraLiftKit
{
	/** A mesh of the lift kit (/Game/ASTRA/Kit/Lift/<name>), or null when it is not imported yet (the cars then stand in plain boxes). */
	ASTRA_API UStaticMesh* Mesh(const FString& Name);
	/** The engine's cube: the stand-in for a kit mesh that is not there. */
	ASTRA_API UStaticMesh* Cube();
}

/** The measures a car and its landings share (the kit's meshes are built to the same numbers: art/blender/ship_lift.py). */
struct ASTRA_API FAstraLiftSpec
{
	struct FOpening { float Y = 0.f; float Width = 140.f; float Height = 220.f; };

	float W = 240.f, D = 240.f, H = 260.f;     // inside the car
	TArray<FOpening> Openings;                 // the doors on the front wall (+X), along the car
	FVector ScreenCenter = FVector::ZeroVector; // the car's screen (car frame), facing into the car
	float ScreenYaw = 0.f;                     // degrees: the way it faces, in the car frame (0: +X)
	FVector2D ScreenSize = FVector2D(80.0, 50.0);
	float DoorLeaf = 6.f;                      // the leaves' thickness
	float WallT = 14.f, FloorT = 30.f, CeilT = 14.f;
	FString Suffix;                            // which kit meshes: "tl", "sv", "cg", "sh"
	/** The kit's meshes are modelled to the nominal measures of their kind (art/blender/ship_lift.py, KIT); a plan with other measures gets them scaled: the car's meshes by
	 *  Hull (X the depth, Y the width, Z the height), the doors' leaves and the landing's frame by Opening (Y the width, Z the height), the shaft's lining by Shaft (X, Y). */
	FVector Hull = FVector::OneVector;
	FVector2D Opening = FVector2D(1.0, 1.0);
	FVector2D Shaft = FVector2D(1.0, 1.0);

	static FAstraLiftSpec Make(const FAstraLiftLine& Line);
	/** The distance from the landing's door plane back to the car's front face (the sill gap). */
	static constexpr float SillGap = 3.f;
};

UCLASS()
class ASTRA_API AAstraLiftCar : public AActor
{
	GENERATED_BODY()

public:
	AAstraLiftCar();
	virtual void Tick(float DeltaTime) override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;

	/** Builds the car for a line and puts it at a stop. */
	void Setup(UAstraLiftSubsystem* InOwner, int32 InLine, const FAstraLiftLine& InData, int32 StartStop);
	/** The landings, in the line's stop order: the car drives the doors of the one it stands at. */
	void SetLandings(const TArray<AAstraLiftLanding*>& InLandings);

	FAstraLiftBrain Brain;

	const FAstraLiftSpec& Spec() const { return CarSpec; }
	int32 LineIndex() const { return Line; }
	UPrimitiveComponent* FloorComponent() const;
	/** Car frame <-> world. */
	FVector ToWorld(const FVector& Local) const { return GetActorTransform().TransformPosition(Local); }
	FVector ToLocal(const FVector& World) const { return GetActorTransform().InverseTransformPosition(World); }
	/** Whether a world point is inside the car (feet on the floor), with a margin in from the walls. */
	bool Contains(const FVector& World, float Margin = 10.f) const;
	/** The deck number the car is at, or the one just below while it is between decks. */
	int32 CurrentStop() const;
	/** The seats of the car's passengers (car frame): where a body stands when it boards; Slot 0.. */
	FVector SlotLocal(int32 Slot) const;
	int32 NumSlots() const { return Slots.Num(); }
	/** Wakes the car's own tick (a call came in). */
	void Wake();
	/** The Captain is near (inside, or within earshot): the cabin's light and the hum are on. */
	void SetNear(bool bNear);
	/** The screen's mesh: its material is the render target the subsystem paints. */
	UStaticMeshComponent* ScreenComponent() const { return Screen; }
	void SetScreenTexture(UTexture* Texture);

	/** The test bench's world has no listener: sounds and lights are left out. */
	bool bQuiet = false;

private:
	TWeakObjectPtr<UAstraLiftSubsystem> Owner;
	int32 Line = INDEX_NONE;
	FAstraLiftLine Data;
	FAstraLiftSpec CarSpec;
	TArray<TWeakObjectPtr<AAstraLiftLanding>> Landings;
	TArray<FVector> Slots;
	FVector LastLocation = FVector::ZeroVector;
	float LastDoor = -1.f;
	int32 LastLandingOpen = INDEX_NONE;
	bool bHumOn = false;

	UPROPERTY() TObjectPtr<UBoxComponent> Floor;
	UPROPERTY() TArray<TObjectPtr<UBoxComponent>> Walls;                    // every other collision box of the fixed shell
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> LeafMesh;          // per opening: two leaves
	UPROPERTY() TArray<TObjectPtr<UBoxComponent>> LeafBox;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Hull;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Glass;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Screen;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> ScreenMat;
	UPROPERTY() TObjectPtr<UPointLightComponent> Lamp;
	UPROPERTY() TObjectPtr<UAudioComponent> Hum;
	UPROPERTY() TObjectPtr<USoundBase> SndThump;
	UPROPERTY() TObjectPtr<USoundBase> SndChime;
	UPROPERTY() TObjectPtr<USoundBase> SndDoor;
	UPROPERTY() TObjectPtr<USoundBase> SndDoorShut;

	UBoxComponent* AddBox(const FName& Name, const FVector& Center, const FVector& Extent);
	UStaticMeshComponent* AddMesh(const FName& Name, UStaticMesh* Mesh, const FVector& Rel, const FVector& Scale);
	void BuildShell();
	void BuildLooks();
	void ApplyDoors(float Open);
	void ApplyBrain(float Dt);
	void DrainEvents();
	void UpdateHum();
	void Thump(float Volume);
	bool bNearNow = false;
	double LastMoveAt = -1.0e9;
	friend class UAstraLiftSubsystem;
};

/** A landing: the doors in the shaft's wall, the frame and the call panel. */
UCLASS()
class ASTRA_API AAstraLiftLanding : public AActor
{
	GENERATED_BODY()

public:
	AAstraLiftLanding();

	void Setup(const FAstraLiftLine& InLine, int32 InStop, const FAstraLiftSpec& InSpec);
	/** What the landing says: the deck sign over its doors, and the number on the shaft's back wall that the car's window shows as it passes. */
	void SetSigns(const FString& Label, int32 Deck);
	/** The doors' travel, 0 shut .. 1 open (the car at this landing drives it). */
	void SetOpen(float Alpha);
	float GetOpen() const { return OpenNow; }
	/** The call's lamp: lit when a car has been called here and is on its way. */
	void SetCalled(bool bOn);
	bool IsCalled() const { return bCalled; }
	int32 StopIndex() const { return Stop; }
	/** The call panel's place (world cm) and the middle of the opening. */
	FVector PanelCm() const;
	FVector DoorCm() const { return GetActorLocation(); }
	FVector Out() const { return OutDir; }
	bool HasDoors() const { return bDoors; }
	/** Whether a world point is in the doorway: across the opening and a little each side of the door plane. */
	bool InDoorway(const FVector& World, float Margin = 25.f) const;
	/** A pawn at this landing, near its call panel, on the lobby side. */
	bool Reaches(const FVector& Feet, float RangeCm = 260.f) const;
	bool bQuiet = false;

private:
	int32 Stop = INDEX_NONE;
	FVector OutDir = FVector::ForwardVector;
	FAstraLiftSpec Spec;
	bool bDoors = true;
	bool bCalled = false;
	float OpenNow = 0.f;
	FVector PanelLocal = FVector::ZeroVector;

	UPROPERTY() TObjectPtr<UStaticMeshComponent> Frame;
	UPROPERTY() TArray<TObjectPtr<UStaticMeshComponent>> LeafMesh;
	UPROPERTY() TArray<TObjectPtr<UBoxComponent>> LeafBox;
	UPROPERTY() TObjectPtr<UStaticMeshComponent> Lamp;
	UPROPERTY() TObjectPtr<UTextRenderComponent> SignText;
	UPROPERTY() TObjectPtr<UTextRenderComponent> ShaftText;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> SignMat;
	float ShaftBackCm = 280.f;                  // how far the shaft's back wall is behind the doors' plane
	void BuildLooks();
};

/** A shaft's walls: instances of the kit's segment up its whole height (one component, as many instances as it has segments). */
UCLASS()
class ASTRA_API AAstraLiftShaft : public AActor
{
	GENERATED_BODY()

public:
	AAstraLiftShaft();
	void Setup(const FAstraLiftLine& InLine, const FAstraLiftSpec& InSpec);
	int32 NumSegments() const { return Segments; }

private:
	int32 Segments = 0;
	UPROPERTY() TObjectPtr<UInstancedStaticMeshComponent> Seg;
	UPROPERTY() TObjectPtr<UInstancedStaticMeshComponent> Door;
};
