// ASTRA — the ship simulation (authoritative). The crew's minds change the ship only through ApplyCommand.

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Dom/JsonObject.h"
#include "AstraCrewRoster.h"
#include "AstraDamageTypes.h"
#include "AstraDamageModel.h"
#include "Async/Future.h"
#include "AstraShipSubsystem.generated.h"

class UMaterialInstanceDynamic;
class UMaterialParameterCollection;
class ALight;
class ADirectionalLight;
class APlayerController;

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
	float PopM = 0.f;           // millions of people on its main world (a city grows by the field)
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
	virtual void Deinitialize() override;
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

	// --- heat (M2): the ship's thermal load, 0..100 % of what she can hold (a little more before things break)
	float GetHeatPct() const { return HeatPct; }
	float GetHeatRate() const { return HeatRate; }         // %/s, smoothed
	bool AreRadiatorsOut() const { return bRadiatorsOut; }
	float GetRadiatorHealth() const { return RadiatorHealth; }
	int32 GetCoolantVents() const { return CoolantVents; }
	/** Heat from the battle: weapons fired, hits soaked by the shields, the drive (units: % of the capacity). */
	void AddHeat(float Pct) { HeatPct = FMath::Clamp(HeatPct + Pct, 0.f, 110.f); }   // (negative only from the test console)
	/** How hot systems still work: 1 up to 70 %, down to 0.55 at 100 % (weapons cadence, shield regeneration). */
	float HeatFactor() const;
	/** The radiators shed heat and glow: extended or the vent's plume make the Aquila easier to find (enemy detection). */
	float SignatureBoost() const { return (bRadiatorsOut ? 0.35f : 0.f) + (VentPlumeT > 0.f ? 1.f : 0.f); }
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
	/** Engineering's battle short: the reactor past its limits (budget 800%, heat +0.3%/s) or back to normal. */
	void SetBattleShort(bool bOn);
	bool IsBattleShort() const { return bBattleShort; }
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
	const TArray<FString>& GetSectorNews() const { return SectorNews; }
	/** The Captain is in the Mess Hall (Deck 4). */
	bool IsCaptainInMess() const;
	const FAstraSectorSystem* FindSector(const FString& Name) const;
	/** What the holo table shows: "tactical" (the battle around the Aquila) or "sector" (the war map). */
	FString GetHoloMode() const { return HoloMode; }
	/** The ship the holo table shows in "ship" mode: empty for the Aquila herself, else a contact id (a scanned ship). */
	FString GetHoloShipId() const { return HoloShipId; }
	/** Autopilot (the Janus approach): the helm steers to a heading without the usual turn reports. */
	void SteerTo(float Heading, float Mark);
	void SetThrottle(float Pct) { ThrottlePct = FMath::Clamp(Pct, -ReverseThrottlePct, 100.f); }
	/** Retro-thrust: the drive can back the ship off at up to this much of her full speed (a console holding a range uses it). */
	static constexpr float ReverseThrottlePct = 30.f;
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
	/** The same, as the Captain's datapad writes it ("DECK 4 · MESS HALL"). */
	FString CaptainPlace() const;
	/** Where the Captain's words go (protocol v2 `context`, docs/ARCHITETTURA.md §3): the place, the crew who hear them
	 *  (distance and walls), the one the Captain is looking at, the open channel, how the Captain is (on foot, seated...). */
	TSharedRef<FJsonObject> CaptainContext() const;
	/** What the main viewscreen shows now ("off (the bare window)" when it is off). */
	FString GetViewscreenDescription() const;
	/** The fill on the hulls comes from where the main viewscreen looks (its camera's direction, world). */
	void AimSpaceFill(const FVector& LookDir, float DeltaTime);
	FString LightInfo() const;
	/** The star's light on the hulls (lux): what the viewscreen's sensor fill is measured against. */
	float GetStarLux() const;
	/** The comms channel open now ("" when none): the other party's contact id. */
	const FString& GetChannelParty() const { return ChannelParty; }
	/** The Captain's standing orders in force ("tactical: weapons free on hostiles inside 10 km"), from the crew's mind. */
	const TArray<FString>& GetStandingOrders() const { return StandingOrders; }

	/** The Captain is on (or over) New Ravenna: the surface zone's sky, sky light, clouds and ground replace space
	 *  (the war goes on up there). The zone lies 1000 km below the bridge in the same world. */
	void SetPlanetside(bool bOn);
	bool IsPlanetside() const { return bPlanetside; }
	static FVector PlanetZone() { return FVector(0.0, 0.0, -1.0e8); }
	/** What the Captain is doing down there, for the crew (empty when back in space). */
	void SetCaptainPlanetside(const FString& What) { CaptainPlanetside = What; }
	/** Where the system's main world is, seen from the bridge now (world direction, unit). */
	FVector PlanetDirectionWorld() const { return PlanetDirNow; }
	/** The Captain can fly down: New Ravenna's hand-built zone at home, a world generated from its name elsewhere (any
	 *  world with ground: not a gas giant). */
	bool HasSurface() const;
	bool IsHomeWorld() const { return SystemName.Equals(TEXT("Aurelia"), ESearchCase::IgnoreCase); }
	/** The world below ("New Ravenna", "Cassia Prime"...), where ships set down on it (world, cm) and what it is called. */
	FString SurfaceWorldName() const;
	FVector SurfaceSite() const;
	FString SurfaceSiteName() const;
	/** Who holds the world below (astra | mandate | guilds | contested | silent; empty: uncharted). */
	FString SurfaceOwner() const;
	/** The level of the sea (world z, cm) on the world below; very low when it has none. */
	float SurfaceSeaZ() const;

	/** The battle simulation reports a blow on our hull that got through the shield, the plate and the structure (docs/DISTRUZIONE.md): the
	 *  damage model puts it in the compartments behind the plating where it struck; the lights, the bridge and the report follow. */
	void OnHullHit(const FAstraHullHit& Hit);
	/** A blow of HullDamage from a direction (a console test, the old callers): a point on the hull facing that way is chosen for it. */
	void OnHullHit(float HullDamage, float ShieldDamage, const FVector& FromDir);
	/** The damage model: the state of every compartment that is not as it was built, the incidents, the people hurt (docs/DISTRUZIONE.md). */
	const FAstraDamageModel& GetInterior() const { return Interior; }
	FAstraDamageModel& GetInterior() { return Interior; }
	/** The damage model's compartment a point (world cm) is in, or INDEX_NONE. */
	int32 InteriorCompOf(const FVector& Cm) const;
	/** Everything the damage model has in play is made whole at once (the console's test, a new command): the incidents it owns go, the bulkheads open. */
	void ResetInterior();
	/** What the damage model costs: milliseconds a tick, on average and at worst (the console's info). */
	void InteriorCost(float& OutAvgMs, float& OutMaxMs) const { OutAvgMs = InteriorMsAvg; OutMaxMs = InteriorMsMax; }
	/** The Captain's state under the air and the fire (the screens' vignette, the harness). */
	const FAstraDmgCaptain& GetCaptainHealth() const { return Interior.Captain(); }
	/** ABBORDAGGI (docs/ABBORDAGGI.md): what a fight inside the ship asks of the ship. A person of the roster is wounded or killed by gunfire (Cause "gunfire": the roster's
	 *  table of wounds): the roster's own words about them (empty when they were hurt already); the wounded go to the Medbay, the fallen are named. */
	FString HarmPerson(int32 RosterIdx, bool bKill, const FString& Cause);
	/** ABBORDAGGI: a pressure bulkhead of the plan is shut, or opened, by the fight (a lockdown against boarders; the boarders cutting through): the plan's door, the door
	 *  actor of the level (when its deck is in) and the people's routes follow, as when the damage model seals one. */
	void SealBulkhead(FName DoorId, bool bSealed);
	/** The tests' own Captain (no pawn needed): where the feet are while it is on; the air, the smoke and the fire work on them as on the real one. */
	void SetTestCaptain(bool bOn, const FVector& PosCm) { bTestCaptain = bOn; TestCaptainCm = PosCm; }
	int32 GetCaptainFate() const { return CaptainFate; }
	/** A plan door's actor (the sliding door in the level), found by where it stands; null when the level has none there (its deck is not loaded). */
	class AAstraDoor* DoorActorOf(FName DoorId);
	/** The bridge's spark effects (the damage effects throw their showers through it too). */
	class AAstraBridgeFX* GetBridgeFX() const;
	/** The campaign save: the system the Aquila is in, the crew's losses. */
	TSharedRef<FJsonObject> SaveJson() const;
	void ResumeFrom(const TSharedPtr<FJsonObject>& Save);

	/** Testing the Medbay: "admit" N wounded from random hits, or let the doctors' "care" run N minutes. */
	/** ABANDON SHIP: the Captain's order (bOrdered: her reactor is overloaded so the enemy cannot take her) or the
	 *  reactor's containment failing at the end of her hull. The crew goes to the lifepods (the sooner the order, the
	 *  more of them get off); the Captain boards one at a hatch off Corridor 1-A (BoardLifepod), or the XO hauls the
	 *  Captain into the last one; then the reactor breaches and the Aquila is gone. */
	bool StartAbandon(bool bOrdered, FString& OutDetail);
	void ReactorFailing() { FString D; if (!bAbandon) { StartAbandon(false, D); } }
	bool IsAbandoning() const { return bAbandon && !bShipLost; }
	/** Her hull number: CVC-01, or a sister's (CVC-03...) when the Captain took the name to a new command. */
	const FString& GetHullNumber() const { return HullNumber; }
	void SetHullNumber(const FString& N) { HullNumber = N; ApplyHullNumber(); }
	/** A railgun volley: the capacitors' draw makes the ship's lights sag for a moment (the power is visible). */
	void RailgunDraw() { RailDraw = 1.f; }
	bool IsShipLost() const { return bShipLost; }
	bool BoardLifepod(class AAstraLifepodHatch* Hatch, APlayerController* PC, bool bHauled = false);
	/** The way from an officer's place to the Captain's quarters (world cm, deck level); OutWaitAt: the point at the
	 *  cabin's door where they wait for the chime. */
	static TArray<FVector> VisitRouteFor(const class AAstraCrewMember* C, int32& OutWaitAt);
	void TestMedbay(const FString& What, int32 N);

	/** One of our manned aircraft was shot down: who was flying it (for the flight report). */
	FString AircrewLost() { return Roster.AircrewLost(CasualtyRng); }
	const FAstraCrewRoster& GetRoster() const { return Roster; }
	const TMap<FString, FString>& GetSquadrons() const { return Squadrons; }

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
	TArray<FString> StandingOrders;
	TArray<FAstraDamage> Damage;      // open incidents inside the hull
	FString LocationName = TEXT("Aurelia System, en route to New Ravenna high orbit");
	FString SystemName = TEXT("Aurelia");
	TMap<FString, FAstraSystemLook> Systems;   // charted systems
	TArray<FAstraSectorSystem> Sector;         // the sector at war (empty until the mind sends it)
	FString HoloMode = TEXT("tactical");
	FString HoloShipId;
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
	// --- DISTRUZIONE: the damage inside the hull
	FAstraDamageModel Interior;
	TFuture<TSharedPtr<FAstraDamageMap>> InteriorFuture;
	bool bInteriorLoading = false;
	float CaptainProbeT = 0.f;
	float GutT = 0.f;                 // the war's gutted sections are looked at once a second
	float InteriorMsAvg = 0.f, InteriorMsMax = 0.f;
	int32 GutDone = 0;                // the sections whose people and rooms are already lost (bit by section: bow, mid, stern)
	float ThermalStress = 0.f;        // overheated conduits: a failure when it reaches 1
	int32 ThermalSeq = 0;
	float RadiatorStress = 0.f;       // blows on the radiator wings: one is torn when it reaches 1
	struct FHitReport { TArray<FString> Lines; TArray<FString> People; int32 Hits = 0; double Since = -100.0; };
	FHitReport HitReport;             // what the last blows did, told in one report
	TMap<FName, TWeakObjectPtr<class AAstraDoor>> DoorActors;
	FDelegateHandle DoorPlacedHandle;
	TSet<int32> ExternalSeals;          // ABBORDAGGI: doors the fight has sealed (the damage model does not know them): they shut again when their deck streams in
	TMap<int32, bool> DoorLockMemory;   // plan door -> whether its actor was locked by the level before a bulkhead sealed it (a sealed one is shut; it goes back as it was)
	void OnDoorPlaced(class AAstraDoor* Door);
	void ShutBulkhead(FName Id, bool bSealed);   // the plan's door, its actor, the effects and the people's routes (the damage model's seal and the fight's)
	void ApplyDoorSeal(int32 DoorIndex, class AAstraDoor* Door, bool bSealed);
	// the Captain's fate under the hazards: down, carried to the Medbay, or dead
	int32 CaptainFate = 0;            // 0 well, 1 down, 2 dead
	bool bTestCaptain = false;
	FVector TestCaptainCm = FVector::ZeroVector;
	float CaptainFateT = 0.f;
	bool bCaptainFadeSet = false;
	void StartInterior();
	void TickInterior(float DeltaTime);
	void TickCaptainFate(float DeltaTime);
	void FlushHitReport(bool bForce);
	void RadiatorHit(const FAstraHullHit& Hit);
	FAstraCrewRoster Roster;          // the 560 aboard, by name: the crew's cost
	// heat
	float HeatPct = 12.f;
	float HeatRate = 0.f;
	float HeatPrev = 12.f;
	bool bRadiatorsOut = false;
	float RadiatorHealth = 1.f;       // 1 intact .. 0.25 (torn by hits), repaired by damage control
	int32 CoolantVents = 3;
	float VentPlumeT = 0.f;           // seconds the vent's plume still shows
	int32 HeatStage = 0;              // 0 nominal, 1 hot (70 %), 2 critical (90 %): reported once, with hysteresis
	float HeatHarmT = 0.f;            // at critical: the next conduit failure / burn
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> RadiatorGlow;
	// the generated world below (the system's main world when it is not New Ravenna), built at the first descent
	UPROPERTY() TObjectPtr<class AAstraWorldSurface> GeneratedWorld;
	const FAstraSystemLook* CurrentLook() const;
	class AAstraWorldSurface* WorldBelow();
	void TickHeat(float DeltaTime);
	float CareT = 0.f;                // the Medbay's rounds: every minute the wounded's conditions move on
	float WardSyncT = 0.f;
	int32 WardRev = -1;
	void SyncWard();                  // the beds in the Medbay follow the roster
	void SyncMess();                  // the off-duty watch at the Mess Hall's tables, from the roster
	TArray<int32> MessDiners;         // roster indices at the tables (mess1..mess12), INDEX_NONE for an empty place
	int32 MessWatch = -1;             // the half-hour watch they belong to
	float MessSyncT = 0.f;
	TArray<FString> SectorNews;       // the latest news on the fleet net (the mind's war map)
	// an officer come to the Captain's quarters in person (the mind decides when, and why)
	TWeakObjectPtr<class AAstraCrewMember> Visitor;
	FString VisitReason;
	bool bVisitAnnounced = false;
	bool bVisitChimed = false;
	float VisitSilentT = 0.f;         // since the visitor last spoke
	bool StartVisit(const FString& Who, const FString& Why, FString& OutDetail);
	void EndVisit(const TCHAR* Why, bool bHurry = false);
	// abandoning ship, and the loss
	bool bAbandon = false;
	bool bAbandonOrdered = false;
	bool bShipLost = false;
	float AbandonLeft = 0.f;          // to the reactor breach
	float AbandonT = 0.f;             // since the order
	float AbandonAlarmT = 0.f;
	float PodLaunchT = 0.f;
	float LostT = 0.f;                // since the breach began
	int32 AbandonCall = 0;            // the countdown's call-outs made (60, 30, 10 s)
	int32 LossStage = 0;
	float EvacFrac = 0.f;             // the crew in the pods
	FString LostSummary;              // who did not get off
	FString CaptainPodName;
	bool bCaptainHauled = false;
	TWeakObjectPtr<class AAstraLifepod> CaptainPod;
	struct FDriftPod { TWeakObjectPtr<AActor> Actor; FVector Vel = FVector::ZeroVector; FRotator Spin = FRotator::ZeroRotator; };
	TArray<FDriftPod> DriftPods;
	void TickAbandon(float DeltaTime);
	void LaunchOtherPod();
	void HaulCaptain();
	void DarkenAquila();
	AActor* AquilaHullActor() const;
	void TickVisit(float DeltaTime);
	UPROPERTY() TObjectPtr<class AAstraBridgeFX> BridgeFX;   // sparks and arcs on the bridge when we are hit hard
	UPROPERTY() TObjectPtr<class AAstraViewscreen> Viewscreen;   // the main viewscreen in front of the bow window
	FRandomStream CasualtyRng;
	static constexpr int32 NumDamageTeams = 4;
	float PowerBudget = 700.f;        // six systems at 100% = 600; the reactor can give 100 more (800 on a battle short)
	bool bBattleShort = false;        // the reactor's safety limits overridden: more power, more heat, a risk to the core
	float HullPct = 100.f;
	double LastHitReport = -100.0;
	double LastBridgeBurst = -100.0;
	double LastRadiatorTear = -100.0;   // the last radiator wing torn by a hit (game time)   // the last console or fixture that shorted out on the bridge (game time)
	float FlickerTime = 0.f;
	float RailDraw = 0.f;              // 1 at a railgun volley, fading: the lights sag
	FString HullNumber = TEXT("CVC-01");
	void ApplyHullNumber();            // the name on her flanks and the plate on the bridge carry her number
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
	UPROPERTY() TObjectPtr<ADirectionalLight> SpaceFill;      // the faint cool fill on the night side of hulls (channel 1)
	// New Ravenna's surface zone (tag ASTRA.Planet.NewRavenna) and what it replaces while the Captain is down there
	UPROPERTY() TArray<TObjectPtr<AActor>> PlanetActors;
	UPROPERTY() TObjectPtr<AActor> SpaceSkyActor;
	UPROPERTY() TObjectPtr<AActor> SpaceSkyLight;
	bool bPlanetside = false;
	float SpaceEV = 6.6f;
	FString CaptainPlanetside;
	FString ChannelParty;             // the channel open now (a hail, ours or theirs, until it is closed)
	FVector PlanetDirNow = FVector::DownVector;
	FLinearColor PlanetFill = FLinearColor(0.42f, 0.6f, 1.f);
	float PlanetFillGain = 1.f;
	void SetPlanetFill(const FString& PlanetType);
	void UpdatePlanetLight(const FVector& SunNow, const FVector Axes[3]);
	UPROPERTY() TArray<TObjectPtr<ALight>> ShipLights;
	TArray<float> ShipLightBase;
	TArray<FLinearColor> ShipLightColorBase;
	TArray<int32> ShipLightComp;        // the interior model's compartment each of the older rooms' lights is in (INDEX_NONE: none), found once the model is up
	TArray<float> ShipLightUnsteady;    // the flicker's factor of each, drawn at about 12 Hz
	float ShipLightFlickT = 0.f;
	bool bShipLightCompsKnown = false;
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
