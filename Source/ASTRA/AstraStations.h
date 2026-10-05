// The bridge stations (docs/ARCHITETTURA.md §4): each station is an officer with a live console. It holds persistent
// modes — the intentions in force, one per aspect (tactical: engagement, shields, point defence, missiles) — and code runs
// them every tick: the helm keeps the bow on the target, fire control stays on it and moves to the next when it dies,
// the shields turn to the threat, the sensors sweep. The officers (the mind) set and change the modes with the `station`
// command and report; one day the Captain or another player sitting at a console will drive the same modes.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Tickable.h"
#include "AstraStations.generated.h"

class FJsonObject;
class UAstraShipSubsystem;
class UAstraBattleSubsystem;

/** One intention in force on a station: the mode, its parameters, when it ends, who set it. */
struct FAstraStationAspect
{
	FString Mode;
	TSharedPtr<FJsonObject> Params;
	FString Until = TEXT("order");      // done | target_lost | order | time:<s>
	FString SetBy = TEXT("default");   // captain | officer | xo | auto | default
	double Since = 0.0;                 // game time
	double Due = 0.0;                   // the executor's own timer (sweeps, jinks…)
	int32 Step = 0;                     // the executor's own counter
};

struct FAstraStation
{
	FString Id;                                   // helm | tactical | sensors | ops | engineering | comms | flight | xo
	FString Officer;                              // the crew id who mans it
	FString Delegation = TEXT("auto");            // manual | advise | auto
	TMap<FString, FAstraStationAspect> Aspects;   // aspect -> intention in force
	FString Status;                               // one line for the console and the crew
	TArray<FString> Actions;                      // the last things it did (newest last)
};

UCLASS()
class UAstraStationsSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UAstraStationsSubsystem, STATGROUP_Tickables); }

	/** The `station` command: {station, mode, params?, aspect?, until?, note?, delegation?}. By = who gave it. */
	bool SetMode(const TSharedPtr<FJsonObject>& Args, const FString& By, FString& OutDetail);
	/** Every station as the crew and the consoles read it (ship_state.state.stations). */
	TSharedRef<FJsonObject> StationsJson() const;
	const FAstraStation* Find(const FString& Id) const { return Stations.Find(Id); }
	/** The mode in force on a station's aspect ("" if none). */
	FString ModeOf(const FString& Station, const FString& Aspect) const;
	/** Its parameters (may be null). */
	TSharedPtr<FJsonObject> ParamsOf(const FString& Station, const FString& Aspect) const;
	/** The aspects of a station, in the order its console shows them. */
	static const TArray<FString>& AspectsOf(const FString& Station);
	/** The modes an aspect offers (the buttons of the console's control surface). */
	static const TArray<FString>& ModeChoices(const FString& Station, const FString& Aspect);
	/** A target parameter as the executors use it: "action" follows the fight (ActionTarget, re-read every tick). */
	FString Resolve(const FString& Target) const { return Target.Equals(TEXT("action"), ESearchCase::IgnoreCase) ? ActionTargetId : Target.ToUpper(); }
	/** The contact the fight is about for the bridge (tactical's target, else the nearest hostile known), "" if none. */
	FString ActionTarget() const { return ActionTargetId; }

private:
	TMap<FString, FAstraStation> Stations;
	double Now = 0.0;
	float Accum = 0.f;
	FString ActionTargetId;                 // for the helm's "bow on the action" and the viewscreen
	FString EngagedId;                      // the contact tactical is engaging now
	double LastSalvoAt = -1e9;              // when fire control last sent a missile salvo on its own
	FString LastShieldSector;
	double ShieldSectorSince = 0.0;
	TMap<FString, FString> SquadronTargets; // squadron -> contact its mission is about
	TMap<FString, FString> DefaultModes;    // "station.aspect" -> the mode it had at the start (a time limit goes back to it)

	void Defaults();
	UAstraShipSubsystem* Ship() const;
	UAstraBattleSubsystem* Battle() const;
	/** Which aspect of the station a mode belongs to ("" when unknown or ambiguous without an explicit aspect). */
	static FString AspectFor(const FString& Station, const FString& Mode);
	FAstraStationAspect* Aspect(const FString& Station, const FString& AspectName);
	void Act(const FString& Station, const FString& Text, bool bReport);
	bool Command(const FString& Name, const TSharedPtr<FJsonObject>& Args, FString& Detail);
	/** The mode has just been set: one-shot effects (a course, a power profile, a launch). */
	bool Enter(const FString& Station, const FString& AspectName, FAstraStationAspect& A, FString& Detail);
	void TickHelm();
	void TickTactical();
	void TickSensors();
	void TickEngineering();
	void TickFlight();
	void TickOps();
	/** The officers' own initiative on delegation auto (what a good officer does without being told, and says). */
	void TickReflexes();
	bool Reflex(const TCHAR* Station, const TCHAR* AspectName, const TCHAR* Mode, const FString& Report);
	double LastFightAt = -1e9;              // the last time the enemy was near or firing
	double LastDecoysAt = -1e9;
	double NextReflexAt = 0.0;
	double HelmAvoidTold = -1e9;           // the last time the helm said it was bending her course clear of a ship
	void Expire(const FString& Station, const FString& AspectName, const FString& Fallback, const FString& Why);
	void UpdateStatus();
};
