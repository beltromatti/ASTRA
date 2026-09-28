// ASTRA — the score follows the war: calm on the bridge, tension when contacts close, the battle, the aftermath; the
// Janus lane's swell breaks exactly on the crossing. The music steps back whenever an officer speaks.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "AstraMusicSubsystem.generated.h"

class UAudioComponent;
class USoundBase;

UENUM()
enum class EAstraMood : uint8
{
	Silence,
	Calm,
	Tension,
	Battle,
	Aftermath
};

UCLASS()
class ASTRA_API UAstraMusicSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UAstraMusicSubsystem, STATGROUP_Tickables); }

	EAstraMood GetMood() const { return Mood; }

private:
	UPROPERTY() TMap<EAstraMood, TObjectPtr<USoundBase>> Cues;
	UPROPERTY() TObjectPtr<USoundBase> TransitCue;
	UPROPERTY() TObjectPtr<UAudioComponent> Current;
	UPROPERTY() TObjectPtr<UAudioComponent> Stinger;
	EAstraMood Mood = EAstraMood::Silence;
	float Since = 100.f;          // seconds in the current mood
	float EvalT = 0.f;
	float BattleHold = 0.f;       // the battle music outlasts the last shot for a while
	float Duck = 1.f;             // < 1 while an officer speaks
	bool bTransitPlayed = false;
	float AfterTransit = -1.f;    // seconds since the crossing (music resumes after the arrival)

	EAstraMood Wanted(float Dt);
	void Play(EAstraMood NewMood, float Fade);
};
