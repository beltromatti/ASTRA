// ASTRA — VITA in the world: the life simulation of the Aquila's 560 people (AstraLifeSim.*) running beside the ship (alert,
// incidents, the roster's wounded and killed), the bodies of those near the Captain (AstraLifeBody.*, a pooled few), and what
// the crew's minds need to know of them (who is within earshot, what they do, what they remember).
//
// The simulation costs a fraction of a millisecond a frame for everyone aboard; the bodies are the budget (docs/VITA.md).

#pragma once

#include "CoreMinimal.h"
#include "Async/Future.h"
#include "Dom/JsonObject.h"
#include "Subsystems/WorldSubsystem.h"
#include "AstraLifeSim.h"
#include "AstraLifeSubsystem.generated.h"

class AAstraLifeBody;
class UAstraShipPlan;
class UAstraShipSubsystem;

UCLASS()
class ASTRA_API UAstraLifeSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Deinitialize() override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UAstraLifeSubsystem, STATGROUP_Tickables); }
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;

	/** The life is simulating (the plan and the roster are in). */
	bool IsRunning() const { return State == EState::Running; }
	FAstraLifeSim& Sim() { return Life; }
	const FAstraLifeSim& Sim() const { return Life; }

	// ------------------------------------------------------------------------------------------------ the clock
	/** The ship's hour of the day ("14:32"), the watch that is on duty, the day. */
	FString ClockText() const;
	FString WatchOnDuty() const;
	void SetShipHour(float Hour);
	float GetTimeScale() const { return TimeScale; }
	void SetTimeScale(float S) { TimeScale = FMath::Clamp(S, 0.f, 600.f); }

	// ------------------------------------------------------------------------------------------------ for the ship and the minds
	/** The life of the ship as the crew's minds read it (ship_state.life): the clock, who is doing what, the damage-control parties, and
	 *  the people near the Captain (the ones who can hear). */
	TSharedRef<FJsonObject> SnapshotJson() const;

	/** The people near the Captain who could hear (body, within earshot), for the context that goes with the Captain's words (docs/VITA.md
	 *  §Integration): each {id (npc<N>, the body's station id), name, rank, gender, dept, job, doing, place, dist_m, angle_deg, memory[]}. */
	TArray<TSharedPtr<FJsonValue>> ListenersJson(const FVector& Eye, const FVector& Look, int32 Max = 6) const;

	/** One person as the mind sees them (identity, what they do now, what they remember). */
	TSharedRef<FJsonObject> PersonJson(int32 Person) const;

	/** What a damage-control party needs to get to an incident in a deck and section, in seconds: the number the ship should give as "on scene
	 *  in" when it dispatches a team (the repair then begins when the party is there). 0 when life is not running. */
	float RepairEtaSeconds(int32 Deck, TCHAR Section, int32 IncidentId) const { return IsRunning() ? Life.RepairEtaSeconds(Deck, Section, IncidentId) : 0.f; }

	/** The tests feed the simulation their own incidents: the ship's are not passed on while this is off. */
	void SetShipFeed(bool bOn) { bFeed = bOn; }

	/** The tests' own Captain (no pawn, no renderer needed): where the feet and the eye are, and which way they look. Bodies are made
	 *  and kept for them as for the real one. */
	void SetTestCaptain(const FVector& InFeet, const FVector& InEye, const FVector& InLook) { bTestCaptain = true; TestFeet = InFeet; TestEye = InEye; TestLook = InLook; }
	void ClearTestCaptain() { bTestCaptain = false; }
	/** Where a person's body is (null: no body), for the tests. */
	AAstraLifeBody* BodyOfPerson(int32 Person) const;

	/** Who is in a deck's section (fit, physically there): a hit there hurts them. Roster indices. Empty when life is not running. */
	TArray<int32> RosterIn(int32 Deck, TCHAR Section) const;

	/** The body that is this roster person (or null): a pooled actor. */
	AAstraLifeBody* BodyOfRoster(int32 RosterIdx) const;
	int32 NumBodies() const { return NumActiveBodies; }

	/** Drops every body now (a level change, the tests). */
	void ReleaseAllBodies();

	// ------------------------------------------------------------------------------------------------ measured
	struct FCost
	{
		double SimMs = 0.0, SimMsMax = 0.0, SimMsAvg = 0.0;      // the subsystem's tick (the whole simulation, routes included)
		double BodiesMs = 0.0, BodiesMsMax = 0.0;                // the bodies' manager
		int64 Ticks = 0;
	};
	const FCost& GetCost() const { return Cost; }
	FString InfoText() const;

	// the bodies read these
	UAstraShipPlan* GetPlan() const { return Plan.Get(); }
	const FVector& Eye() const { return EyeCm; }
	const FVector& Look() const { return LookDir; }
	const TArray<TObjectPtr<AAstraLifeBody>>& PoolView() const { return Pool; }

private:
	enum class EState : uint8 { Idle, Loading, WaitRoster, Running, Failed };
	EState State = EState::Idle;
	TFuture<TSharedPtr<FAstraLifeMap>> MapFuture;
	TSharedPtr<FAstraLifeMap> MapPtr;
	FAstraLifeSim Life;
	TWeakObjectPtr<UAstraShipSubsystem> Ship;
	TWeakObjectPtr<UAstraShipPlan> Plan;
	float TimeScale = 12.f;
	float PollT = 0.f;
	float PrewarmT = 0.f;
	float BodyT = 0.f;
	FCost Cost;
	int32 NumActiveBodies = 0;
	double RouteBudgetS = 0.00012;
	bool bFeed = true;
	bool bTestCaptain = false;
	FVector TestFeet = FVector::ZeroVector, TestEye = FVector::ZeroVector, TestLook = FVector::ForwardVector;

	// --- bodies
	UPROPERTY() TArray<TObjectPtr<AAstraLifeBody>> Pool;
	TMap<int32, int32> BodyOf;              // person -> pool index
	UPROPERTY() TArray<TObjectPtr<UObject>> Warm;     // the assets every body needs, loaded once at the start and kept
	bool bWarmed = false;
	FVector LastCaptain = FVector::ZeroVector;
	FVector EyeCm = FVector::ZeroVector;
	FVector LookDir = FVector::ForwardVector;
	bool bCaptainSeen = false;
	float JumpGraceS = 0.f;           // after a jump (a lift, a fade) the picture is still coming back: bodies are made in view, in a few frames
	int32 MaxBodiesNow() const;
	void ManageBodies();
	void PrewarmPool(float DeltaTime);
	bool CanAppearUnseen(const FVector& Where) const;
	AAstraLifeBody* TakeBody(bool bFemale);
	void ReleaseBody(int32 Person);

	void TryStart();
};
