// ASTRA — ABBORDAGGI: the fight inside the Aquila in the game (docs/ABBORDAGGI.md).
//
// The squad simulation (AstraBoardSim.*) is plain code over the ship's plan; this subsystem is its host. It reads the plan on a worker (as the damage model and VITA do),
// owns the simulation, starts a boarding (the Mandate's boarders cut in at a breach; the marines of VITA's roster take their rifles) and ends it, and turns what the
// simulation says into the game: the soldiers' bodies near the Captain (AstraCombatant.*), their rounds and wounds (AstraCombatFx.*), the pressure bulkheads that close
// and are cut through, the casualties of the roster (the wounded to the Medbay, the fallen with their names), the Captain's own wound and his fate (the damage model's
// chain: the XO's command, the abandon ship, the inquiry), the reports of the bridge and the marines' net, and the mind's words to the marines (orders to the squads).
//
// The Captain is a man of the fight: the simulation sees where he stands, and a round that reaches him is his wound. A round of his that strikes a soldier's body is
// the soldier's wound (UAstraFpsComponent calls PlayerHit).

#pragma once

#include "CoreMinimal.h"
#include "Async/Future.h"
#include "AstraBoardMap.h"
#include "AstraBoardSim.h"
#include "AstraDamageMap.h"
#include "Dom/JsonObject.h"
#include "Subsystems/WorldSubsystem.h"
#include "AstraBoardSubsystem.generated.h"

class AAstraBoardBreach;
class AAstraCombatant;
class UAstraCombatFx;
class UAstraLifeSubsystem;
class UAstraShipSubsystem;

UCLASS()
class ASTRA_API UAstraBoardSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Deinitialize() override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UAstraBoardSubsystem, STATGROUP_Tickables); }
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;

	/** The plan is read and the tactical map built (a few hundred milliseconds on a worker after the world begins). */
	bool IsReady() const { return Phase != EPhase::Loading && Phase != EPhase::Failed; }
	/** A boarding is on (from the alarm to the end, the cleaning up after it not counted). */
	bool IsActive() const { return Phase == EPhase::Active; }
	const FAstraBoardSim& Sim() const { return Fight; }
	const FAstraBoardMap* BoardMap() const { return Map.Get(); }

	/** What a boarding is made of. */
	struct FSpec
	{
		FString Breach;                // the plan's id of the compartment the boarders cut into; empty: the default place on Deck 7
		int32 Skiffs = 1;              // boarding craft that have docked: ten men each
		int32 Boarders = 0;            // or exactly this many (0: Skiffs * 10)
		FString Source;                // "the Mandate raider Cocytus": what the bridge says it came from
		bool bLockdown = true;         // the section bulkheads of the breach's deck close at once
		float WarnS = 45.f;            // the marines are called when the craft is seen; the boarders cut in this long after
	};
	/** Starts a boarding: the alarm, the lockdown, the marines called, the boarders on their way. False (and why) when the plan is not read or one is on. */
	bool StartBoarding(const FSpec& Spec, FString& OutDetail);
	/** Ends it (the test console, the end of a fight): the bulkheads open, the marines go back to their duty, the bodies are cleared away in a while. */
	void EndBoarding(const TCHAR* Why);

	// ------------------------------------------------------------------------------------------------ the Captain
	/** A round of the Captain's struck a soldier (Damage: what it does after the range, Head: it hit the head). The soldier's wound; false when it did not count (a marine of
	 *  ours, or nobody is fighting). From: where it was fired (the way he falls). */
	bool PlayerHit(AAstraCombatant* Who, float Damage, bool bHead, const FVector& From);
	/** The Captain's strength, 0..1 (1 whole), whether he is down, and how long ago and from where he was last hit (the weapon's screen reads these). */
	float CaptainStrength() const { return FMath::Clamp(CapHp / 100.f, 0.f, 1.f); }
	bool IsCaptainDown() const { return bCapDown; }
	double SinceCaptainHurt() const;
	FVector LastHurtFrom() const { return CapHurtFrom; }
	float LastHurtAmount() const { return CapHurtAmount; }
	/** The nearest able enemy that sees the Captain, distance (cm), or a negative number. */
	float NearestThreatCm() const { return ThreatCm; }

	// ------------------------------------------------------------------------------------------------ the minds
	/** The commands of the game's one entrance (UAstraShipSubsystem::ApplyCommand forwards "boarding", "marine_order" and "lockdown" here). */
	bool HandleCommand(const FString& Name, const TSharedPtr<FJsonObject>& Args, FString& OutDetail);
	/** What the minds read of the fight (ship_state.boarding): empty object when none is on. */
	TSharedRef<FJsonObject> Snapshot() const;
	/** One line for the console: the fight in numbers. */
	FString InfoText() const;
	/** The fight's own report to the marines' net: the squads, where, how many, in contact; the bulkheads. (The mind's context for the marines.) */
	TSharedRef<FJsonObject> MarinesPicture() const;

	/** Draws the simulation in the world (units, squads' places, the planned route, the openings the marines hold) when the console's `astra.board.debug` asks for it. */
	void DrawDebug() const;

	/** The tests: what the bodies are doing. */
	int32 NumBodies() const;

private:
	enum class EPhase : uint8 { Loading, Failed, Idle, Active, Over };

	EPhase Phase = EPhase::Loading;
	TFuture<TSharedPtr<FAstraBoardMap>> MapFuture;
	TSharedPtr<FAstraDamageMap> Dmg;
	TSharedPtr<FAstraBoardMap> Map;
	FAstraBoardSim Fight;
	TWeakObjectPtr<UAstraShipSubsystem> Ship;
	TWeakObjectPtr<UAstraLifeSubsystem> Life;
	TWeakObjectPtr<UAstraCombatFx> Fx;

	// --- the event
	FString Source;
	FString BreachText;
	FVector BreachAt = FVector::ZeroVector;
	float Since = 0.f;                               // game seconds since the start
	float AfterEnd = 0.f;
	bool bBreachOpen = false;
	float WarnLeft = 0.f;
	int32 PriorAlert = 0;
	bool bRaisedAlert = false;
	TSet<int32> SealedByUs;                          // doors of the damage map the fight has sealed (ours to open again)
	TArray<int32> MarineUnits;                       // the sim's units that are roster marines
	TMap<int32, int32> RosterOfUnit;                 // unit -> roster index
	TMap<int32, int32> PersonOfUnit;                 // unit -> VITA's person index
	TSet<int32> HarmTold;                            // roster people whose wound or death the roster has been told
	TSet<int32> ToldDown;                            // units whose fall has been told
	bool bToldContact = false;
	bool bToldTakeover = false;
	float TakeoverFuse = -1.f;
	float CasualtyT = 0.f;
	int32 ToldMarinesLost = 0, ToldMandateLost = 0;
	TArray<FString> Log;                             // what happened, newest last (the marines' net reads it)

	// --- the Captain
	float CapHp = 100.f;
	bool bCapDown = false;
	float CapBleedS = 0.f;
	double CapHurtAt = -100.0;
	FVector CapHurtFrom = FVector::ZeroVector;
	float CapHurtAmount = 0.f;
	float ThreatCm = -1.f;
	float CapRegenT = 0.f;
	bool bCaptainIn = false;
	int32 CaptainSquad = INDEX_NONE;

	// --- the bodies
	UPROPERTY() TArray<TObjectPtr<AAstraCombatant>> Pool[2];     // by side: 0 the marines', 1 the Mandate's
	TMap<int32, TObjectPtr<AAstraCombatant>> BodyOf;              // unit -> body
	UPROPERTY() TArray<TObjectPtr<UObject>> Warm;
	UPROPERTY() TObjectPtr<AAstraBoardBreach> Breach;
	float BodyT = 0.f;
	TArray<double> LastShotSound;                // by unit: when it last made a sound
	float ThreatT = 0.f;
	bool bChainDown = false;                     // the ship's chain has taken the Captain's fall (so a Captain who is up again was carried out)
	FVector BreachNormal = FVector::ForwardVector;
	float SoundBudget = 0.f;
	int32 TracesLeft = 0;
	bool bWarmed = false;

	void TryFinishLoading();
	// --- the beginning
	bool PickBreach(const FString& Id, int32& OutComp, FVector& OutAt, FString& OutWhy) const;
	void MobiliseMarines();
	void SealSections(int32 BreachComp, const FVector& At);
	void OpenSections();
	void SealDoor(int32 Door, bool bSealed);
	void MakeSightOverride();
	// --- the step
	void Step(float Dt);
	void SyncCaptain(float Dt);
	void SyncLife();
	void ProcessEvents(float Dt);
	void OnShot(const AstraBoard::FBoardEvent& E);
	void OnHit(const AstraBoard::FBoardEvent& E);
	void OnFall(const AstraBoard::FBoardEvent& E, bool bDied);
	void OnOutcome();
	void OnCaptainHit(const AstraBoard::FBoardEvent& E);
	void CaptainFate(float Dt);
	void OpenBreach();
	void Tell(const FString& Text, bool bReport);
	void ManageBodies(float Dt);
	AAstraCombatant* TakeBody(int32 Side);
	void ReleaseBody(int32 Unit);
	void ClearBodies();
	void Finish(const TCHAR* Why);
	FString NameOf(const AstraBoard::FUnit& U) const;
	FString PlaceOf(const AstraBoard::FUnit& U) const;
	UAstraShipSubsystem* ShipSub() const;
	UAstraLifeSubsystem* LifeSub() const;
	UAstraCombatFx* FxSub() const;
	bool CaptainFeet(FVector& OutFeet, float& OutYaw, bool& bOutLow, float& OutSpeed) const;
};

/** What the Mandate's cutting looks like from inside: a ring of glowing cut and a hot light at the breach, up for as long as the boarders come in by it. */
UCLASS()
class ASTRA_API AAstraBoardBreach : public AActor
{
	GENERATED_BODY()

public:
	AAstraBoardBreach();
	/** The hole: where it is (floor level, cm) and which way the wall faces (the unit vector into the room). */
	void Open(const FVector& At, const FVector& IntoRoom);
	void Close();
	bool IsOpen() const { return bOpen; }

protected:
	virtual void Tick(float DeltaSeconds) override;

private:
	bool bOpen = false;
	float Age = 0.f;
	FVector Centre = FVector::ZeroVector;
	FVector Normal = FVector::ForwardVector;
	UPROPERTY() TArray<TObjectPtr<class UStaticMeshComponent>> Ring;
	UPROPERTY() TArray<TObjectPtr<class UMaterialInstanceDynamic>> RingMIDs;
	UPROPERTY() TObjectPtr<class UPointLightComponent> Glow;
	UPROPERTY() TObjectPtr<class UStaticMesh> LineMesh;
	UPROPERTY() TObjectPtr<class UMaterialInterface> GlowMat;
	void Build();
};
