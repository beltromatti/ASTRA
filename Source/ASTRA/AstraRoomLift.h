// ASTRA — the lifts of the ship's first rooms. The Flight Deck and Main Engineering were built before the deck plan, each with a lift alcove for an
// entrance and two fixed leaves in it; the plan's lobbies that were to join them to the decks were never built, so both rooms could only be reached
// by the transporter (5 Oct). Each such entrance becomes a working lift: E at the alcove, or at the doors that now close the corridor's end on the
// deck, and a short ride (the doors, the hum, a fade) takes the Captain to the other end.
#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "Subsystems/WorldSubsystem.h"
#include "AstraRoomLift.generated.h"

class USoundBase;
class UTextRenderComponent;

UCLASS()
class ASTRA_API AAstraRoomLift : public AActor
{
	GENERATED_BODY()

public:
	AAstraRoomLift();

	/** The two ends (feet, world cm, and the way he faces on arrival) and where each one's doors are (for the reach). */
	FVector RoomFeet = FVector::ZeroVector, DeckFeet = FVector::ZeroVector;
	FVector RoomDoor = FVector::ZeroVector, DeckDoor = FVector::ZeroVector;
	float RoomYaw = 0.f, DeckYaw = 0.f;
	FString RoomName;       // "Flight Deck"
	int32 Deck = 0;         // the deck the corridor end is on

	UPROPERTY() TObjectPtr<USoundBase> SndThump;
	UPROPERTY() TObjectPtr<USoundBase> SndChime;
	UPROPERTY() TObjectPtr<USoundBase> SndHum;

	/** The alcove's doors, to be copied at the corridor's end: each piece's mesh, materials and place in the alcove's frame. */
	struct FLeaf
	{
		TWeakObjectPtr<class UStaticMesh> Mesh;
		TArray<TWeakObjectPtr<class UMaterialInterface>> Materials;
		FTransform Rel;
	};
	TArray<FLeaf> Leaves;
	FVector Corridor = FVector::ZeroVector;   // a place of the corridor on the lobby's side (world cm)
	FVector Out = FVector::ForwardVector;     // from the lobby towards that corridor
	FVector RoomIn = FVector::ForwardVector;  // from the alcove's doors into the room

	/** E: the Captain within reach of either end's doors rides to the other. True when it was his (the key is taken). */
	bool TryUse(APawn* Me);

	virtual void Tick(float DeltaTime) override;

private:
	enum class EStage : uint8 { Idle, Closing, Moving, Opening };
	EStage Stage = EStage::Idle;
	float T = 0.f;
	bool bToRoom = false;
	bool bHinted = false;
	TWeakObjectPtr<APawn> Rider;
	bool bDeckSettled = false;
	bool Near(const APawn* Me, const FVector& Door) const;
	void Arrive();
	/** Once the corridor's deck is in the world: its real end (the plan's lobby edge is a guess: Main Engineering's corridor ends 1.8 m short of it),
	 *  the doors and the sign there. */
	void SettleDeckEnd();
};

/** Makes the lifts at play's start, from the plan: every pre-plan room's entrance whose lobby was never built. */
UCLASS()
class ASTRA_API UAstraRoomLifts : public UWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	/** Each end of each lift, for whoever plans a route or tells the Captain the way. */
	const TArray<TWeakObjectPtr<AAstraRoomLift>>& GetLifts() const { return Lifts; }

private:
	TArray<TWeakObjectPtr<AAstraRoomLift>> Lifts;
	void Build(UWorld& W);
};
