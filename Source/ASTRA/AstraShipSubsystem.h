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

	FAstraShipEvent OnShipEvent;
	FAstraAlertChanged OnAlertChanged;

private:
	// --- state
	EAstraAlert Alert = EAstraAlert::Green;
	float HeadingDeg = 45.f, MarkDeg = 10.f, TargetHeadingDeg = 45.f, TargetMarkDeg = 10.f;
	float ThrottlePct = 60.f, SpeedMps = 412.f, ReactorPct = 78.f;
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
	bool bTurning = false;

	void Event(const FString& Text, bool bReport = false);
	const FAstraContact* FindContact(const FString& Id) const;
	void SetAlert(EAstraAlert NewAlert);

	// --- visuals
	UPROPERTY() TObjectPtr<UMaterialParameterCollection> ShipMPC;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> SkyMID;
	UPROPERTY() TObjectPtr<ADirectionalLight> Sun;
	UPROPERTY() TArray<TObjectPtr<ALight>> ShipLights;
	TArray<float> ShipLightBase;
	TArray<FLinearColor> ShipLightColorBase;
	FVector SkyAxis0[3];
	FVector SunDir0 = FVector::ForwardVector;
	float Heading0 = 45.f, Mark0 = 10.f;
	float AlertBlend = 0.f;   // 0 green .. 1 red (smoothed)
	float YellowBlend = 0.f;
	float AlertTime = 0.f;

	void CollectSceneRefs(UWorld& InWorld);
	void UpdateAttitudeVisuals();
	void UpdateAlertVisuals(float DeltaTime);
	void PlayAlertSound(EAstraAlert NewAlert);
};
