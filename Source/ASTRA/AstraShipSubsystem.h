// ASTRA — the ship simulation (authoritative). The crew's minds change the ship only through ApplyCommand.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Dom/JsonObject.h"
#include "AstraCrewRoster.h"
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

/** How a star system looks from the ship: its star, its main world, the tint of its sky (set on a Janus transit). */
struct FAstraSystemLook
{
	FString Name = TEXT("Aurelia");
	FString StarClass = TEXT("orange");     // red_dwarf | orange | yellow | blue_white
	FString PlanetType = TEXT("ocean");     // ocean | desert | ice | lava | gas_giant | barren
	FString PlanetName = TEXT("New Ravenna");
	FVector SunWorld = FVector(0.5f, 0.6f, 0.45f);      // where the star is, seen from the bridge now
	FVector PlanetWorld = FVector(0.8f, -0.5f, -0.1f);
	float PlanetSize = 0.28f;                           // angular radius (rad)
	float NebulaHue = 0.f;
	float NebulaSat = 1.f;
	float Seed = 0.f;
};

/** A system of the sector at war as the fleet knows it (sent by the mind's war map): owner, place on the plot, gates. */
struct FAstraSectorSystem
{
	FString Name;
	FString Owner;              // astra | mandate | guilds | contested | silent
	int32 Threat = 0;           // 0 quiet .. 3 front line
	FVector2D Pos = FVector2D::ZeroVector;   // light-years on the sector plot
	TArray<FString> Links;      // the systems its Janus Gate is bound to
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
	/** A new star system around the ship (Janus transit): star, sun light, planet, sky tint, location name. */
	void ApplySystem(const FAstraSystemLook& Look);
	FString GetLocationName() const { return LocationName; }
	FString GetSystemName() const { return SystemName; }
	/** Charted star systems, by name: a system's look is fixed the first time it is charted (the director's choice, or
	 *  derived from its name: the universe is seeded, the same name is always the same place). Aurelia is home. */
	FAstraSystemLook ChartSystem(const FString& Name, const FString& Star = FString(), const FString& Planet = FString(),
	                             const FString& PlanetName = FString());
	/** "Aurelia (orange star, ocean world New Ravenna); Cassia (...)" for the crew. */
	FString KnownSystemsLine() const;
	/** The sector at war (from the mind): gate links for the helm, the plot for the holo table. */
	const TArray<FAstraSectorSystem>& GetSector() const { return Sector; }
	const FAstraSectorSystem* FindSector(const FString& Name) const;
	/** What the holo table shows: "tactical" (the battle around the Aquila) or "sector" (the war map). */
	FString GetHoloMode() const { return HoloMode; }
	/** Autopilot (the Janus approach): the helm steers to a heading without the usual turn reports. */
	void SteerTo(float Heading, float Mark);
	void SetThrottle(float Pct) { ThrottlePct = FMath::Clamp(Pct, 0.f, 100.f); }
	void SetSpeedMps(float V) { SpeedMps = V; }
	/** The Janus lane has the ship: attitude and speed come from the gate's field until the transit. */
	void SetLaneControl(bool bOn) { bLaneControl = bOn; bAutoHelm = false; }
	void DriveExternally(float Heading, float Mark, float Speed);

	/** Effective power of a system as a fraction of nominal: the allocation, minus what damaged conduits lose (0..1.5). */
	float PowerFactor(const FString& System) const;

	/** Anything that happens to or around the ship; bReport = worth telling the Captain (the crew decides the words). */
	void PublishEvent(const FString& Text, bool bReport) { Event(Text, bReport); }
	/** Where the Captain is aboard, for the crew ("on the bridge", "on the flight deck"...). */
	FString CaptainAboard() const;

	/** The battle simulation reports a hit on our hull: compartments, lights, reports. */
	void OnHullHit(float HullDamage, float ShieldDamage, const FVector& FromDir);
	/** The campaign save: the system the Aquila is in, the crew's losses. */
	TSharedRef<FJsonObject> SaveJson() const;
	void ResumeFrom(const TSharedPtr<FJsonObject>& Save);

	/** One of our manned aircraft was shot down: who was flying it (for the flight report). */
	FString AircrewLost() { return Roster.AircrewLost(CasualtyRng); }
	const FAstraCrewRoster& GetRoster() const { return Roster; }

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
	FString LocationName = TEXT("Aurelia System, en route to New Ravenna high orbit");
	FString SystemName = TEXT("Aurelia");
	TMap<FString, FAstraSystemLook> Systems;   // charted systems
	TArray<FAstraSectorSystem> Sector;         // the sector at war (empty until the mind sends it)
	FString HoloMode = TEXT("tactical");
	FAstraSystemLook MakeLook(const FString& Name, const FString& Star, const FString& Planet, const FString& PlanetName) const;
	bool bLaneControl = false;                 // the Janus lane drives the ship
	bool bAutoHelm = false;                    // the gate approach autopilot steers (no turn reports)
	// the home sky as the level sets it, restored when the Aquila comes back to Aurelia
	TMap<FName, float> HomeScalars;
	TMap<FName, FLinearColor> HomeVectors;
	FVector HomeSunDir0 = FVector::ForwardVector;
	float HomeLux = 0.f, HomeKelvin = 0.f;
	bool bHomeCaptured = false;
	void CaptureHomeSky();
	int32 NextDamageId = 1;
	FAstraCrewRoster Roster;          // the 560 aboard, by name: the crew's cost
	UPROPERTY() TObjectPtr<class AAstraBridgeFX> BridgeFX;   // sparks and arcs on the bridge when we are hit hard
	FRandomStream CasualtyRng;
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
	// the star's light thrown back by the planet (earthshine): a soft fill from the planet on everything outside the
	// hull (lighting channel 1: it casts no shadow, so it must never reach inside)
	UPROPERTY() TObjectPtr<ADirectionalLight> PlanetLight;
	FLinearColor PlanetFill = FLinearColor(0.42f, 0.6f, 1.f);
	float PlanetFillGain = 1.f;
	void SetPlanetFill(const FString& PlanetType);
	void UpdatePlanetLight(const FVector& SunNow, const FVector Axes[3]);
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
