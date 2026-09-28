// ASTRA — the ship simulation (authoritative). The crew's minds change the ship only through ApplyCommand.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Dom/JsonObject.h"
#include "AstraShipSubsystem.generated.h"

class UMaterialInstanceDynamic;
class UMaterialParameterCollection;
class ALight;
class ADirectionalLight;

UENUM(BlueprintType)
enum class EAstraAlert : uint8
{
	Green,
	Yellow,
	Red
};

USTRUCT(BlueprintType)
struct FAstraContact
{
	GENERATED_BODY()

	UPROPERTY(BlueprintReadOnly) FString Id;
	UPROPERTY(BlueprintReadOnly) FString Class;
	UPROPERTY(BlueprintReadOnly) FString Name;
	UPROPERTY(BlueprintReadOnly) FString Status;
	UPROPERTY(BlueprintReadOnly) float RangeKm = 0.f;
	UPROPERTY(BlueprintReadOnly) float BearingDeg = 0.f;
};

/** One incident inside the hull (a hit's consequences) and the damage-control team working on it. */
struct FAstraDamage
{
	int32 Id = 0;
	int32 Deck = 1;
	TCHAR Section = TEXT('A');
	FString Kind;               // "hull breach" | "fire" | "conduit damage"
	FString System;             // conduit damage: the system that loses power through it
	int32 Team = -1;            // damage-control team on it (0..3), -1 = unattended
	float Travel = 0.f;         // s until the team is on scene
	float Work = 30.f;          // s of work on scene
	float Progress = 0.f;       // 0..1
	float SpreadT = 25.f;       // fires: next chance to spread / burn the structure
	FString Where() const { return FString::Printf(TEXT("deck %d section %c"), Deck, Section); }
};

DECLARE_MULTICAST_DELEGATE_TwoParams(FAstraShipEvent, const FString& /*Text*/, bool /*bReport: worth telling the Captain*/);
DECLARE_MULTICAST_DELEGATE_OneParam(FAstraAlertChanged, EAstraAlert /*NewAlert*/);

/**
 * Ship state + typed commands (the same tools the crew agent calls). Also drives what the ship state looks like:
 * alert lighting (material parameter collection + tagged lights, klaxon) and attitude (the sky and the star rotate
 * around the ship: the Aquila is the reference frame, the universe moves).
 */
UCLASS()
class ASTRA_API UAstraShipSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UAstraShipSubsystem, STATGROUP_Tickables); }
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;

	/** Executes a crew/player command. Returns success and a short, factual detail (fed back to the crew). */
	bool ApplyCommand(const FString& Name, const TSharedPtr<FJsonObject>& Args, FString& OutDetail);

	/** Live telemetry for the crew's minds. */
	TSharedRef<FJsonObject> Snapshot() const;

	EAstraAlert GetAlert() const { return Alert; }
	float GetHeadingDeg() const { return HeadingDeg; }
	float GetMarkDeg() const { return MarkDeg; }
	float GetSpeedMps() const { return SpeedMps; }
	bool AreShieldsUp() const { return bShieldsUp; }
	FString GetShieldMode() const { return ShieldMode; }
	// --- read access for the bridge screens
	float GetThrottlePct() const { return ThrottlePct; }
	float GetReactorPct() const { return ReactorPct; }
	const TMap<FString, float>& GetPowerPct() const { return PowerPct; }
	const TArray<FAstraDamage>& GetDamage() const { return Damage; }
	const TArray<FString>& GetRecentEvents() const { return RecentEvents; }
	FString GetInterceptId() const { return InterceptId; }
	double GetInterceptRangeKm() const { return InterceptRangeKm; }
	bool IsBroadside() const { return bBroadside; }
	bool IsTurning() const { return bTurning; }
	float GetTargetHeadingDeg() const { return TargetHeadingDeg; }
	float GetTargetMarkDeg() const { return TargetMarkDeg; }
	FString GetEmcon() const { return Emcon; }
	FString GetPointDefense() const { return PointDefense; }
	int32 GetNumDamageTeams() const { return NumDamageTeams; }
	float GetPowerBudget() const { return PowerBudget; }
	/** Effective power of a system as a fraction of nominal: the allocation, minus what damaged conduits lose (0..1.5). */
	float PowerFactor(const FString& System) const;

	/** Anything that happens to or around the ship; bReport = worth telling the Captain (the crew decides the words). */
	void PublishEvent(const FString& Text, bool bReport) { Event(Text, bReport); }

	/** The battle simulation reports a hit on our hull: compartments, lights, reports. */
	void OnHullHit(float HullDamage, float ShieldDamage, const FVector& FromDir);

	FAstraShipEvent OnShipEvent;
	FAstraAlertChanged OnAlertChanged;

private:
	// --- state
	EAstraAlert Alert = EAstraAlert::Green;
	float HeadingDeg = 45.f, MarkDeg = 0.f, TargetHeadingDeg = 45.f, TargetMarkDeg = 0.f;
	float ThrottlePct = 60.f, SpeedMps = 288.f, ReactorPct = 78.f;
	TMap<FString, float> PowerPct;
	FString ShieldMode = TEXT("balanced");
	bool bShieldsUp = true;
	TMap<FString, FString> Weapons;
	FString TargetId;
	FString Emcon = TEXT("restricted");
	FString PointDefense = TEXT("auto");
	TMap<FString, FString> Squadrons;
	TArray<FAstraContact> Contacts;
	TArray<FString> RecentEvents;
	TArray<FAstraDamage> Damage;      // open incidents inside the hull
	int32 NextDamageId = 1;
	static constexpr int32 NumDamageTeams = 4;
	static constexpr float PowerBudget = 700.f;   // six systems at 100% = 600; the reactor can give 100 more
	float HullPct = 100.f;
	double LastHitReport = -100.0;
	float FlickerTime = 0.f;
	bool bTurning = false;
	// helm intercept: the course follows a contact; at the standoff range the ship turns broadside and holds it
	FString InterceptId;
	float InterceptStandoffKm = 6.f;
	float InterceptRetargetT = 0.f;
	bool bBroadside = false;
	double InterceptRangeKm = 0.0;

	void Event(const FString& Text, bool bReport = false);
	const FAstraContact* FindContact(const FString& Id) const;
	void SetAlert(EAstraAlert NewAlert);
	void TickDamage(float DeltaTime);
	int32 FreeDamageTeam() const;
	FString DamageSummary() const;

	// --- visuals
	UPROPERTY() TObjectPtr<UMaterialParameterCollection> ShipMPC;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> SkyMID;
	UPROPERTY() TObjectPtr<ADirectionalLight> Sun;
	UPROPERTY() TArray<TObjectPtr<ALight>> ShipLights;
	TArray<float> ShipLightBase;
	TArray<FLinearColor> ShipLightColorBase;
	FVector SkyAxis0[3];
	FVector SunDir0 = FVector::ForwardVector;
	float Heading0 = 45.f, Mark0 = 0.f;
	float AlertBlend = 0.f;   // 0 green .. 1 red (smoothed)
	float YellowBlend = 0.f;
	float AlertTime = 0.f;

	void CollectSceneRefs(UWorld& InWorld);
	void UpdateAttitudeVisuals();
	void UpdateAlertVisuals(float DeltaTime);
	void PlayAlertSound(EAstraAlert NewAlert);
};
