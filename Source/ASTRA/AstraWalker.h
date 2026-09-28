// ASTRA — a crewman going about the ship: walks a round of waypoints (the corridors behind the bridge, the Medbay's
// aisle, the flight deck), stops at each for a while (a check, a word, a look at a screen) and moves on. A character
// with real movement: the mannequin's animation blueprint turns its speed into idle, walk and turn.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Character.h"
#include "AstraWalker.generated.h"

UCLASS()
class ASTRA_API AAstraWalker : public ACharacter
{
	GENERATED_BODY()

public:
	AAstraWalker();

	/** The round (world, cm): walked in order, then again from the first. */
	UPROPERTY(EditAnywhere, Category = "Walker")
	TArray<FVector> Route;

	/** Seconds at each stop (min, max). */
	UPROPERTY(EditAnywhere, Category = "Walker")
	FVector2D PauseRange = FVector2D(3.f, 9.f);

	UPROPERTY(EditAnywhere, Category = "Walker")
	float WalkSpeed = 135.f;

	UPROPERTY(EditAnywhere, Category = "Walker")
	bool bFemaleBody = false;

	/** The jacket: Command, Security, Science, Engineering, Flight, Medical. */
	UPROPERTY(EditAnywhere, Category = "Walker")
	FString Dept = TEXT("Command");

protected:
	virtual void BeginPlay() override;
	virtual void Tick(float DeltaSeconds) override;

private:
	int32 Next = 0;
	float Wait = 0.f;
	float Stuck = 0.f;
};
