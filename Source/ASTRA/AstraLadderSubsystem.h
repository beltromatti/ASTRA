// ASTRA — the Jefferies trunks' ladders (docs/NAVE.md §8): the Captain climbs them by hand, deck to deck, through the holes in the floors.
//
// The ladders come from the ship's plan with the lifts (FAstraLiftNetwork::Ladders, read by UAstraLiftSubsystem): for every trunk, the spot where the
// climber's body goes in front of the rungs, the way he faces, and for every deck its floor, the walkway point to step off to and the niche's hole.
// The Captain takes a ladder with E near a niche, or by walking into it; W and S climb and go down (the character hands its walking input here
// while he is on it); E steps off at a deck, as do W at the top of the column and S at its bottom. While he climbs his movement is off (MOVE_None)
// and this subsystem places him: the rungs and the cage of the niche never push him around, and a long frame never drops him.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "AstraLiftData.h"
#include "AstraLadderSubsystem.generated.h"

class ACharacter;
class APawn;

UCLASS()
class ASTRA_API UAstraLadderSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override;
	virtual bool IsTickableInEditor() const override { return false; }

	/** E: on a ladder at a deck, step off; by a niche at a deck, take the ladder. True when the key was the ladder's. */
	bool Use(APawn* Pawn, FString& OutNotice);
	/** The walking input while the Captain climbs (Y forward +1 up, back -1 down): the character hands it here instead of walking. False when he is not on a ladder. */
	bool ClimbInput(const APawn* Pawn, const FVector2D& Axis);
	bool IsClimbing(const APawn* Pawn) const;
	int32 NumLadders() const { return Ladders.Num(); }
	/** A line for the log and the console: the ladders known, the one in use and where the climber is. */
	FString Describe() const;

private:
	TArray<FAstraLadder> Ladders;
	bool bLoaded = false;
	int32 On = INDEX_NONE;                     // the ladder being climbed
	TWeakObjectPtr<ACharacter> Climber;
	float Vz = 0.f;                            // cm/s, up positive
	float InputY = 0.f;
	double InputAt = -1.0;
	double EndHeldSince = -1.0;                // W at the top, S at the bottom: held this long steps off
	FVector2D SnapFrom = FVector2D::ZeroVector;
	float SnapT = 1.f;                         // 0..1: from where he took it to the spot in front of the rungs
	float TurnFrom = 0.f;
	double PushSince = -1.0;                   // a walker pushing into a niche: since when
	int32 PushLadder = INDEX_NONE;
	int32 DeckShown = 0;

	static float FeetZ(const ACharacter* C);
	/** The ladder whose niche is within Reach (cm) of the feet at one of its decks; OutStop: that deck. */
	int32 NearLadder(const FVector& Feet, float Reach, int32& OutStop) const;
	/** The stop whose floor is within Tol (cm) of the feet of the climber. */
	int32 StopAt(float Feet, float Tol) const;
	void Grab(ACharacter* C, int32 Ladder);
	bool StepOff(int32 Stop, FString& OutNotice);
	void Notice(const FString& Text, float Seconds) const;
};
