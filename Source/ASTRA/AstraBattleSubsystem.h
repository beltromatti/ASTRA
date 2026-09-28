// ASTRA — the world outside the hull: ships of every side, their manoeuvres and weapons, projectiles, damage, the
// opening scenario. Simulated in the Aurelia system frame (metres, doubles) and drawn around the Aquila, which stays
// at the world origin (the bridge is the origin; the universe moves).

#pragma once

#include "CoreMinimal.h"
#include "Subsystems/WorldSubsystem.h"
#include "Dom/JsonObject.h"
#include "AstraBattleSubsystem.generated.h"

class AStaticMeshActor;
class UMaterialInstanceDynamic;
class UPointLightComponent;
class UStaticMesh;
class USoundBase;

UENUM()
enum class EAstraSide : uint8
{
	Astra,
	Mandate,
	Neutral
};

UENUM()
enum class EAstraShipMode : uint8
{
	Idle,       // holding position / drifting
	Cruise,     // following a course
	Attack,     // closing on and engaging a target
	Evade,      // breaking off
	Dead
};

USTRUCT()
struct FAstraBattleShip
{
	GENERATED_BODY()

	int32 Id = 0;
	FString ContactId;          // what the sensors call it (T-01...)
	FString Name;
	FString Class;
	FString Mesh;
	EAstraSide Side = EAstraSide::Neutral;
	bool bPlayer = false;

	FVector Pos = FVector::ZeroVector;   // m, system frame
	FVector Vel = FVector::ZeroVector;   // m/s
	FQuat Att = FQuat::Identity;
	float MaxAccel = 15.f;               // m/s^2
	float MaxTurnDeg = 3.f;              // deg/s
	float CruiseSpeed = 300.f;           // m/s
	float Radius = 150.f;                // m, hit sphere

	float Hull = 1000.f, HullMax = 1000.f;
	float Shield = 400.f, ShieldMax = 400.f, ShieldRegen = 4.f;
	bool bShieldsUp = true;

	float RailCd = 8.f, RailT = 3.f, RailRange = 8000.f, RailDamage = 55.f;
	int32 RailSlugs = 2;                 // slugs per volley
	float MissileCd = 30.f, MissileT = 10.f, MissileRange = 25000.f;
	int32 Missiles = 12;
	float PDRange = 2000.f, PDT = 0.f;
	int32 PDChannels = 2;                // missiles engaged per point-defence cycle

	// the player's fire control: orders become volleys fired at the weapons' cadence
	int32 FireTarget = -1;
	int32 RailVolleys = 0;
	int32 LaserShots = 0;
	float LaserT = 0.f;

	int32 TargetId = -1;
	EAstraShipMode Mode = EAstraShipMode::Idle;
	bool bHostile = false;
	bool bCold = false;                  // drives off, minimal emissions (hard to classify)
	bool bIdentified = true;
	bool bAlive = true;
	bool bFleeing = false;
	bool bHoldFire = false;              // ceasefire ordered by its commander
	// small craft (fighters, bombers, drones) launched from a carrier
	bool bCraft = false;
	int32 Squadron = -1;                 // index in Squadrons
	int32 CraftKind = 0;                 // 0 fighter, 1 bomber, 2 drone
	FString Mission;                     // cap | strike | escort | ew | recon | recall
	int32 MissionTarget = -1;            // ship id (strike/escort/ew/recon)
	int32 Torpedoes = 0;
	float GunT = 0.f;
	float OrbitPhase = 0.f;
	bool bJammed = false;                // an EW drone is degrading its fire control
	bool bNegotiated = false;            // holding fire / withdrawing under terms agreed over the channel
	bool bLeader = false;                // leads its group (the commander on the channel)

	UPROPERTY() TObjectPtr<AStaticMeshActor> Actor = nullptr;
	UPROPERTY() TObjectPtr<AStaticMeshActor> ShieldBubble = nullptr;
	UPROPERTY() TObjectPtr<AStaticMeshActor> DriveFlare = nullptr;   // engine plume, kept visible at long range
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> ShieldMID = nullptr;
	float ShieldFlash = 0.f;
	FVector ShieldFacing = FVector::ZeroVector;   // reinforced sector in the ship's frame (zero = balanced)
	float ShieldPower = 1.f;                       // power factor (the player's allocation and damage)
	float WeaponPower = 1.f;
};

UENUM()
enum class EAstraProjKind : uint8
{
	Rail,
	Missile
};

USTRUCT()
struct FAstraProjectile
{
	GENERATED_BODY()

	EAstraProjKind Kind = EAstraProjKind::Rail;
	FVector Pos = FVector::ZeroVector;
	FVector Vel = FVector::ZeroVector;
	int32 Owner = -1;
	int32 Target = -1;
	float Damage = 50.f;
	float Life = 10.f;
	float MaxSpeed = 1600.f;             // guided weapons: missiles 1600 m/s, torpedoes 900 m/s
	bool bTorpedo = false;
	bool bDead = false;
	UPROPERTY() TObjectPtr<AStaticMeshActor> Actor = nullptr;
	UPROPERTY() TObjectPtr<AStaticMeshActor> Trail = nullptr;   // guided weapons: the exhaust streak behind
};

USTRUCT()
struct FAstraFlash
{
	GENERATED_BODY()

	FVector Pos = FVector::ZeroVector;   // system frame
	float Age = 0.f, Life = 1.f, Size = 50.f, Intensity = 50.f;
	FLinearColor Color = FLinearColor::White;
	FVector BeamTo = FVector::ZeroVector; // lasers: flash drawn as a beam from Pos to BeamTo
	bool bBeam = false;
	bool bRing = false;                   // shockwave ring (expands in its plane)
	FVector Vel = FVector::ZeroVector;    // drifts with what exploded (m/s)
	FQuat Rot = FQuat::Identity;          // rings: orientation in the system frame
	UPROPERTY() TObjectPtr<AStaticMeshActor> Actor = nullptr;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> MID = nullptr;
};

/** A flight group of the Aquila (Flight Control). */
USTRUCT()
struct FAstraSquadron
{
	GENERATED_BODY()

	FString Name;            // alpha | bravo | drones (the crew's tool ids)
	FString CallSign;        // Falcon | Hammer | Wasp
	FString Mesh;
	int32 Kind = 0;          // 0 fighter, 1 bomber, 2 drone
	int32 Total = 0;         // aircraft still existing
	int32 OnDeck = 0;        // aircraft on the flight deck
	int32 ToLaunch = 0;      // queued for the current launch
	float LaunchT = 0.f;
	FString Mission;
	int32 TargetId = -1;
	float RearmT = 0.f;      // rearming after recovery
	int32 LostSinceReport = 0;
	float LastLossReport = -100.f;
	bool bAirborneReported = false;
	int32 Launched = 0;      // aircraft launched in this sortie
	int32 TorpedoesAway = 0; // released since the last report (one spoken report per torpedo run)
	float TorpedoReportAt = -1.f;
	FString TorpedoTarget;
	EAstraSide Side = EAstraSide::Astra;   // Mandate wings fly from their cruisers
	int32 CarrierId = -1;                  // the ship they launch from and land on
	int32 Rockets = 0;                     // per aircraft (Mandate strike fighters)
};

/** What the tactical plot shows of one object (the holo table draws these; positions in the Aquila's frame). */
struct FAstraHoloBlip
{
	FVector Rel = FVector::ZeroVector;      // cm, bridge-world axes, relative to the Aquila's centre
	FQuat Rot = FQuat::Identity;            // bridge-world orientation
	FVector VelDir = FVector::ZeroVector;   // bridge-world unit vector
	float Speed = 0.f;                      // m/s
	int32 Kind = 0;                         // 0 ship, 1 missile, 2 blast
	EAstraSide Side = EAstraSide::Neutral;
	bool bPlayer = false;
	bool bHostile = false;
	bool bUnknown = false;
	bool bRetreating = false;
	bool bHoldFire = false;
	bool bTargeted = false;                 // our fire control is on it
	bool bCraft = false;                    // fighter / bomber / drone
	bool bNoLabel = false;                  // only a flight group's leader is labelled
	float Size = 1.f;                       // 1 capital, ~0.7 escort, ~0.55 small
	float Fade = 1.f;
	float RangeKm = 0.f;
	FString Name;
	FString Contact;
};

/** What is left of a destroyed ship (a burnt hulk drifting and tumbling) or a piece of debris. */
USTRUCT()
struct FAstraWreck
{
	GENERATED_BODY()

	FVector Pos = FVector::ZeroVector;
	FVector Vel = FVector::ZeroVector;
	FQuat Att = FQuat::Identity;
	FVector SpinAxis = FVector::UpVector;
	float SpinDeg = 2.f;                  // deg/s
	float Life = -1.f;                    // debris fade away; hulks stay (-1)
	float Age = 0.f;
	float Scale = 1.f;
	UPROPERTY() TObjectPtr<AStaticMeshActor> Actor = nullptr;
};

UCLASS()
class ASTRA_API UAstraBattleSubsystem : public UTickableWorldSubsystem
{
	GENERATED_BODY()

public:
	virtual void OnWorldBeginPlay(UWorld& InWorld) override;
	virtual void Tick(float DeltaTime) override;
	virtual TStatId GetStatId() const override { RETURN_QUICK_DECLARE_CYCLE_STAT(UAstraBattleSubsystem, STATGROUP_Tickables); }
	virtual bool ShouldCreateSubsystem(UObject* Outer) const override;

	/** Contacts as the crew sees them (id, class, name when known, range, true bearing/mark, status, shields/hull when scanned). */
	TArray<TSharedPtr<FJsonValue>> ContactsJson() const;
	/** The battle as the Mandate commander knows it: the true state and orders of their own ships, and the ASTRA ships.
	 *  Private to the enemy minds (the crew never sees it). */
	TSharedRef<FJsonObject> MandateViewJson() const;

	/** The player's ship fires on a contact. */
	bool PlayerFire(const FString& Weapon, const FString& ContactId, int32 Salvo, FString& OutDetail);
	bool PlayerScan(const FString& ContactId, FString& OutDetail);
	bool PlayerHail(const FString& ContactId, FString& OutDetail);
	bool PlayerCeaseFire(FString& OutDetail);
	/** Flight Control: launch (or re-task an airborne) flight group on a mission; recall it to the flight deck. */
	bool LaunchSquadron(const FString& Name, const FString& Mission, const FString& ContactId, FString& OutDetail);
	bool RecallSquadron(const FString& Name, FString& OutDetail);
	/** Status line per flight group, for the crew's telemetry and the screens. */
	TSharedRef<FJsonObject> SquadronsJson() const;
	/** The Aquila's weapons as fire control reports them (live: assignments, volleys left, VLS cycle, ammunition). */
	TSharedRef<FJsonObject> PlayerWeaponsJson() const;
	/** Everything the tactical plot should draw right now. */
	void GetHoloBlips(TArray<FAstraHoloBlip>& Out) const;
	/** A Mandate commander's decision (from their mind): continue_attack | hold_fire | withdraw | accept_surrender.
	 *  The senior surviving commander orders the whole strike group; any other captain only their own ship. */
	bool EnemyOrder(const FString& Order, const FString& Reason, const FString& Commander, FString& OutDetail);
	/** Contact id of the ship whose captain commands the Mandate forces now: the group leader, else the biggest ship left. */
	FString MandateCommander() const;
	/** The war director's next beat (from the mind): raid | distress | reinforcements | resupply | calm. Contact ids are
	 *  assigned now (so the mind can give the new commanders a persona before they arrive). */
	bool StartBeat(const TSharedPtr<FJsonObject>& Beat, FString& OutDetail);
	/** Where a live contact is from the Aquila, aimed at its lead point (for the helm's intercept). */
	bool ContactGeometry(const FString& ContactId, double& OutBearing, double& OutMark, double& OutRangeKm) const;
	void SetPlayerShields(bool bUp) { if (Ships.Num()) { Ships[0].bShieldsUp = bUp; } }
	/** Structure damage from inside (fires): hull points, no shields. */
	void PlayerInternalDamage(float Hull) { if (Ships.Num()) { Ships[0].Hull = FMath::Max(1.f, Ships[0].Hull - Hull); } }

	float PlayerHullFraction() const { return Ships.Num() ? Ships[0].Hull / Ships[0].HullMax : 1.f; }
	/** The Aquila's fire control at a glance (bridge screens). */
	struct FFireControl
	{
		FString Target;          // contact id under fire control ("" = none)
		int32 RailVolleys = 0;
		float RailNext = 0.f;
		int32 LaserShots = 0;
		int32 Missiles = 0;
		float MissileCycle = 0.f;
		int32 OursInFlight = 0;
		int32 Inbound = 0;       // missiles flying at us
		float TargetRangeKm = 0.f;
	};
	FFireControl GetFireControl() const;
	float PlayerShieldFraction() const { return Ships.Num() ? Ships[0].Shield / Ships[0].ShieldMax : 1.f; }
	bool IsScenarioOver() const { return bScenarioOver; }

	/** Camera shake request for the bridge (0..1), decays over time. */
	float ConsumeShake(float DeltaTime);

private:
	UPROPERTY() TArray<FAstraBattleShip> Ships;
	UPROPERTY() TArray<FAstraProjectile> Projectiles;
	UPROPERTY() TArray<FAstraFlash> Flashes;
	UPROPERTY() TArray<FAstraSquadron> Squadrons;
	UPROPERTY() TArray<FAstraWreck> Wrecks;
	UPROPERTY() TObjectPtr<UStaticMesh> RingMesh;
	UPROPERTY() TObjectPtr<UMaterialInterface> BlastMat;
	UPROPERTY() TObjectPtr<UStaticMesh> CubeMesh;
	bool bBriefed = false;
	bool bEngagementActive = false;     // a fight is on: the outcome is evaluated
	int32 NextContact = 40;             // contact ids for ships the director brings in
	TArray<TPair<float, TSharedPtr<FJsonObject>>> PendingBeats;
	float RepairUntil = -1.f, RepairHullPerSec = 0.f;
	int32 RepairMissiles = 0;
	float CalmUntil = -1.f;
	void ArriveBeat(const TSharedPtr<FJsonObject>& Beat);
	int32 SpawnClass(const FString& Class, const FString& Contact, const FString& Name, const FVector& Pos, float HeadingDeg);
	UPROPERTY() TObjectPtr<UStaticMesh> SphereMesh;
	UPROPERTY() TObjectPtr<UStaticMesh> CylinderMesh;
	UPROPERTY() TObjectPtr<UMaterialInterface> GlowMat;
	UPROPERTY() TObjectPtr<UMaterialInterface> ShellMat;

	/** The bridge's position in the Aquila's hull frame (m): the world origin is the bridge, not the ship centre. */
	FVector BridgeOffset = FVector(172.0, 0.0, 62.0);

	float Time = 0.f;
	float Shake = 0.f;
	int32 InboundSinceReport = 0;       // missiles launched at us since the last spoken report
	float LastInboundReport = -100.f;
	int32 NextId = 1;
	int32 StageDone = 0;
	bool bScenarioOver = false;
	float TransmissionAt = -1.f;
	bool bSurrenderAccepted = false;    // the Mandate accepted the Aquila's surrender
	FVector LastWreckPos = FVector::ZeroVector;   // the last ASTRA ship lost (search and rescue)
	FString LastWreckName;
	FString TransmissionText;           // "T-21 — ...": who opens a channel to the Aquila, and why

	int32 AddShip(const FString& Contact, const FString& Name, const FString& Class, const FString& Mesh, EAstraSide Side,
	              const FVector& Pos, float HeadingDeg, float Speed, float Radius, float Hull, float Shield);
	FAstraBattleShip* FindByContact(const FString& Contact);
	FAstraBattleShip* FindById(int32 Id);
	void SpawnVisual(FAstraBattleShip& S);

	void TickPlayer(float Dt);
	void TickScenario(float Dt);
	void TickAI(FAstraBattleShip& S, float Dt);
	void TickWeapons(FAstraBattleShip& S, float Dt);
	void TickSquadrons(float Dt);
	void TickCraft(FAstraBattleShip& S, float Dt);
	int32 AirborneCount(int32 Squadron) const;
	/** A Mandate cruiser's strike wing (Harpy fighters) that launches after Delay seconds against the Aquila. */
	void AddEnemyWing(int32 CarrierIdx, int32 Count, float Delay);
	bool bMandateStandDown() const;   // the Mandate leader agreed to terms: their fighters break off
public:
	/** What the bridge knows about enemy small craft (for the crew's telemetry). */
	FString EnemyCraftSummary() const;
private:
	void FireTorpedo(FAstraBattleShip& From, FAstraBattleShip& To);
	void TickPlayerFire(FAstraBattleShip& P, float Dt);
	void TickProjectiles(float Dt);
	void TickFlashes(float Dt);
	void SyncVisuals();

	void FireRail(FAstraBattleShip& From, FAstraBattleShip& To, float Spread);
	void FireMissile(FAstraBattleShip& From, FAstraBattleShip& To);
	void FireLaser(FAstraBattleShip& From, FAstraBattleShip& To);
	void ApplyHit(FAstraBattleShip& To, const FVector& FromDir, float Damage, const FVector& HitPos);
	void Destroy(FAstraBattleShip& S);
	void BreakCeasefire(const FAstraBattleShip& Victim);
	/** The Mandate commander's ship is gone (destroyed or jumped out): the next captain in line takes over and calls. */
	void OnCommanderLost(const FAstraBattleShip& Old, const TCHAR* How);
	void AddFlash(const FVector& Pos, float Size, float Life, const FLinearColor& Color, float Intensity);
	void AddBeam(const FVector& A, const FVector& B, float Life, const FLinearColor& Color);
	void Explode(FAstraBattleShip& S);    // secondary blasts, shockwave, debris, and the hulk left behind
	void TickWrecks(float Dt);
	/** Our own guns and launchers, felt through the hull (rate-limited per sound). */
	void HullSound(const TCHAR* Name, float Volume, float MinInterval);
	UPROPERTY() TMap<FName, TObjectPtr<USoundBase>> Sounds;
	TMap<FName, float> SoundLast;

	FVector ToWorld(const FVector& SystemPos) const;      // system frame (m) -> world (cm)
	FQuat ToWorldRot(const FQuat& SystemRot) const;
	void Report(const FString& Text, bool bReport = true);
	FString SideName(EAstraSide S) const;
	double BearingDeg(const FVector& From, const FVector& To) const;
	double MarkDeg(const FVector& From, const FVector& To) const;
};
