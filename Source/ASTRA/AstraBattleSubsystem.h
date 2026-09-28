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
	bool bNegotiated = false;            // holding fire / withdrawing under terms agreed over the channel

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
	bool bDead = false;
	UPROPERTY() TObjectPtr<AStaticMeshActor> Actor = nullptr;
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
	UPROPERTY() TObjectPtr<AStaticMeshActor> Actor = nullptr;
	UPROPERTY() TObjectPtr<UMaterialInstanceDynamic> MID = nullptr;
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
	float Size = 1.f;                       // 1 capital, ~0.7 escort, ~0.55 small
	float Fade = 1.f;
	float RangeKm = 0.f;
	FString Name;
	FString Contact;
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
	/** The Aquila's weapons as fire control reports them (live: assignments, volleys left, VLS cycle, ammunition). */
	TSharedRef<FJsonObject> PlayerWeaponsJson() const;
	/** Everything the tactical plot should draw right now. */
	void GetHoloBlips(TArray<FAstraHoloBlip>& Out) const;
	/** A Mandate commander's decision (from their mind): continue_attack | hold_fire | withdraw | accept_surrender.
	 *  The senior surviving commander orders the whole strike group; any other captain only their own ship. */
	bool EnemyOrder(const FString& Order, const FString& Reason, const FString& Commander, FString& OutDetail);
	/** Contact id of the ship whose captain commands the Mandate forces now (Acheron, then Styx, Cocytus, Lethe). */
	FString MandateCommander() const;
	/** Where a live contact is from the Aquila, aimed at its lead point (for the helm's intercept). */
	bool ContactGeometry(const FString& ContactId, double& OutBearing, double& OutMark, double& OutRangeKm) const;
	void SetPlayerShields(bool bUp) { if (Ships.Num()) { Ships[0].bShieldsUp = bUp; } }
	/** Structure damage from inside (fires): hull points, no shields. */
	void PlayerInternalDamage(float Hull) { if (Ships.Num()) { Ships[0].Hull = FMath::Max(1.f, Ships[0].Hull - Hull); } }

	float PlayerHullFraction() const { return Ships.Num() ? Ships[0].Hull / Ships[0].HullMax : 1.f; }
	float PlayerShieldFraction() const { return Ships.Num() ? Ships[0].Shield / Ships[0].ShieldMax : 1.f; }
	bool IsScenarioOver() const { return bScenarioOver; }

	/** Camera shake request for the bridge (0..1), decays over time. */
	float ConsumeShake(float DeltaTime);

private:
	UPROPERTY() TArray<FAstraBattleShip> Ships;
	UPROPERTY() TArray<FAstraProjectile> Projectiles;
	UPROPERTY() TArray<FAstraFlash> Flashes;
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

	FVector ToWorld(const FVector& SystemPos) const;      // system frame (m) -> world (cm)
	FQuat ToWorldRot(const FQuat& SystemRot) const;
	void Report(const FString& Text, bool bReport = true);
	FString SideName(EAstraSide S) const;
	double BearingDeg(const FVector& From, const FVector& To) const;
	double MarkDeg(const FVector& From, const FVector& To) const;
};
