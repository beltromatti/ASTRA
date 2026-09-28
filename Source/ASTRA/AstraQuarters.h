// ASTRA — the Captain's quarters (Deck 1, behind the bridge): the cabin's lights come on when the Captain walks in,
// and the bunk lets the Captain rest. While the Captain sleeps the war runs faster (the XO has the conn) until
// something the Captain must hear happens — then the XO wakes them — or the rest is over.

#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AstraQuarters.generated.h"

class ALight;
class SWidget;

UCLASS()
class ASTRA_API AAstraQuarters : public AActor
{
	GENERATED_BODY()

public:
	AAstraQuarters();
	virtual void BeginPlay() override;
	virtual void EndPlay(const EEndPlayReason::Type Reason) override;
	virtual void Tick(float DeltaTime) override;

	/** Beside the bunk, where the Captain lies down and gets up (relative to this actor, cm). */
	UPROPERTY(EditAnywhere, Category = "Quarters")
	FVector BunkSpot = FVector(-145.f, -290.f, 0.f);

	/** The cabin (relative to this actor, cm). */
	UPROPERTY(EditAnywhere, Category = "Quarters")
	FVector CabinMin = FVector(-880.f, -470.f, -60.f);

	UPROPERTY(EditAnywhere, Category = "Quarters")
	FVector CabinMax = FVector(40.f, 470.f, 360.f);

	/** How much faster the world runs while the Captain sleeps, and the longest rest (real seconds). */
	UPROPERTY(EditAnywhere, Category = "Quarters")
	float RestDilation = 6.f;

	UPROPERTY(EditAnywhere, Category = "Quarters")
	float MaxRestSeconds = 150.f;

	bool IsPawnInside(const APawn* Pawn) const;
	bool IsResting() const { return Phase != EPhase::Awake; }
	/** E: beside the bunk, lie down; while resting, get up. False when the Captain is not at the bunk. */
	bool TryRest(APawn* Pawn);

private:
	enum class EPhase : uint8 { Awake, FallingAsleep, Asleep, Waking };
	EPhase Phase = EPhase::Awake;
	double PhaseT0 = 0.0;          // real seconds, when the phase began
	double AsleepWorldT = 0.0;     // world seconds when sleep began (the rest's length, in ship time)
	FString WakeReason;            // why the XO woke the Captain (empty: rested enough, or got up)
	TWeakObjectPtr<APawn> Sleeper;
	UPROPERTY() TArray<TObjectPtr<ALight>> Lights;
	bool bLightsOn = true;
	float CheckT = 0.f;
	TSharedPtr<SWidget> Caption;
	FDelegateHandle EventHandle;

	void Wake(const FString& Why);
	void SetPhase(EPhase P);
	void ShowCaption(bool bShow);
	void SetControl(bool bEnabled);
};
