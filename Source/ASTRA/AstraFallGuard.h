// ASTRA — the Captain never falls out of his ship. On foot he stands on the decks' floors and the rooms' meshes, not on the hull's outer skin
// (ASTRACharacter ignores it: the bridge lifts' shafts cross it), so a gap in a floor would drop him into space. When he is still falling after
// longer than any drop inside the ship takes (the Flight Deck's galleries to its floor, ~2 s), he is put back where he last stood, a step back from
// the edge he went over, and the log and the timeline say where the floor was missing: the gap is mended at its source (the room's mesh or the
// deck's build; `astra.debug.floors <deck>` lists such gaps), this only keeps a missing floor from ending the game.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "AstraFallGuard.generated.h"

UCLASS()
class ASTRA_API UAstraFallGuard : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool DoesSupportWorldType(const EWorldType::Type WorldType) const override { return WorldType == EWorldType::Game || WorldType == EWorldType::PIE; }
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override;
	virtual bool IsTickableInEditor() const override { return false; }

	/** How many times the Captain was caught falling out of the ship (the harness and the tests read it). */
	int32 NumCaught() const { return Caught; }

private:
	struct FStood
	{
		FVector Loc = FVector::ZeroVector;   // the capsule's centre, world cm
		double At = 0.0;
	};
	TArray<FStood> Stood;                   // where he stood on a floor, the last few seconds, oldest first
	double FallSince = -1.0;
	FVector Edge = FVector::ZeroVector;     // the last place he stood before this fall
	FVector FallFrom = FVector::ZeroVector; // where the fall began (far from Edge when something moved him there: a teleport, the harness)
	int32 Caught = 0;
};
